# mypy: ignore-errors
from __future__ import annotations

import base64
import importlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

import fire_uav.infrastructure.providers as deps
from fire_uav.config import settings
from fire_uav.core.protocol import MapBounds
from fire_uav.module_core.geometry import haversine_m, interpolate_path_point
from fire_uav.module_core.route.base_location import resolve_base_location
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint

log = logging.getLogger(__name__)

_folium_module = None
_folium_draw_cls = None


def _get_folium():
    global _folium_module
    if _folium_module is None:
        _folium_module = importlib.import_module("folium")
    return _folium_module


def _get_folium_draw():
    global _folium_draw_cls
    if _folium_draw_cls is None:
        _folium_draw_cls = importlib.import_module("folium.plugins").Draw
    return _folium_draw_cls


def _spawn_debug_visuals_enabled() -> bool:
    """Hide temporary spawn/debug overlays by default while keeping logic active."""
    return bool(getattr(settings, "show_spawn_debug_visuals", False))

@runtime_checkable
class MapProvider(Protocol):
    """Protocol for interchangeable map backends."""

    def render_map(
        self, path: list[tuple[float, float]], token: int, path_kind: str | None = None
    ) -> Path: ...
    @property
    def bridge_script(self) -> str: ...
    def set_provider(self, provider: str, *, offline: bool, cache_dir: Path | None) -> None: ...


class FoliumMapProvider:
    """
    Leaflet/Folium map provider with tile caching/offline toggle and provider switch.
    """

    TILESETS: dict[str, tuple[str, str]] = {
        "de": ("https://tile.openstreetmap.de/{z}/{x}/{y}.png", "OpenStreetMap.de"),
        "hot": ("https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", "OSM Humanitarian"),
        "osmfr": ("https://a.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png", "OpenStreetMap France"),
        "topo": ("https://tile.opentopomap.org/{z}/{x}/{y}.png", "OpenTopoMap"),
        "carto": ("https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", "Carto Light"),
    }

    _BRIDGE_JS = """\
(() => {
  if (!window.L) { console.error('Leaflet failed to load'); return; }
  const map = window.__map || Object.values(window).find(v => v instanceof L.Map);
  if (!map) { return; }

  function sendPath(gj) { console.log('PY_PATH ' + JSON.stringify(gj)); }
  function sendTarget(gj) { console.log('PY_TARGET ' + JSON.stringify(gj)); }
  function sendHome(lat, lon) { console.log('PY_HOME ' + JSON.stringify({lat, lon})); }
  function sendObject(payload) { console.log('PY_OBJECT ' + JSON.stringify(payload)); }

  const homeCoord = window.__homeCoord && typeof window.__homeCoord.lat === 'number'
      && typeof window.__homeCoord.lon === 'number'
      ? L.latLng(window.__homeCoord.lat, window.__homeCoord.lon)
      : null;
  const homeSnapThresholdM = 100.0;

  let spawnMode = false;
  let homeMode = false;
  function setObjectSpawnMode(enabled) { spawnMode = !!enabled; }
  function setHomeMode(enabled) { homeMode = !!enabled; }

  const screenToGeo = (x, y) => {
      if (!map || typeof map.containerPointToLatLng !== 'function') return null;
      const latlng = map.containerPointToLatLng([x, y]);
      if (!latlng) return null;
      return { lat: latlng.lat, lon: latlng.lng };
  };

  const objectLayer = L.layerGroup().addTo(map);
  function setObjects(objects) {
      objectLayer.clearLayers();
      if (!Array.isArray(objects)) return;
      objects.forEach(obj => {
          if (!obj) return;
          const lat = Number(obj.lat);
          const lon = Number(obj.lon);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
          const objectId = obj.object_id || '';
          const isSelected = !!obj.selected;
          const marker = L.circleMarker([lat, lon], {
              radius: 6,
              color: '#000000',
              fill: true,
              fillColor: '#ffffff',
              weight: isSelected ? 3 : 2
          });
          marker.on('click', () => sendObject({ object_id: objectId, lat, lon }));
          marker.addTo(objectLayer);
      });
  }

  map.on(L.Draw.Event.CREATED, e => {
      if (e.layerType === 'polyline') {
          sendPath(e.layer.toGeoJSON().geometry);
      } else if (e.layerType === 'marker') {
          sendTarget(e.layer.toGeoJSON().geometry);
      }
  });

  map.on(L.Draw.Event.EDITED, e => {
      e.layers.eachLayer(l => {
          if (l instanceof L.Polyline) {
              sendPath(l.toGeoJSON().geometry);
          } else if (l instanceof L.Marker) {
              sendTarget(l.toGeoJSON().geometry);
          }
      });
  });

  map.on(L.Draw.Event.DELETED, e => {
      let clearedPath = false;
      e.layers.eachLayer(l => {
          if (l instanceof L.Polyline) {
              clearedPath = true;
          } else if (l instanceof L.Marker) {
              sendTarget({type:'Point', coordinates:[]});
          }
      });
      if (clearedPath) {
          sendPath({type:'LineString', coordinates:[]});
      }
  });

  map.on('click', e => {
      if (!e || !e.latlng) return;
      if (homeMode) {
          sendHome(e.latlng.lat, e.latlng.lng);
          homeMode = false;
          return;
      }
      if (!spawnMode) return;
  });

  let activeDraw = null;
  map.on(L.Draw.Event.DRAWSTART, e => {
      if (e.layerType !== 'polyline') return;
      const toolbar = map._drawControl && map._drawControl._toolbars && map._drawControl._toolbars.draw;
      if (toolbar && toolbar._modes && toolbar._modes.polyline) {
          activeDraw = toolbar._modes.polyline.handler;
      }
  });
  map.on(L.Draw.Event.DRAWSTOP, () => { activeDraw = null; });
  map.on(L.Draw.Event.DRAWVERTEX, () => {
      if (!activeDraw || !homeCoord) return;
      const poly = activeDraw._poly;
      if (!poly || !poly.getLatLngs) return;
      const latlngs = poly.getLatLngs();
      if (!latlngs || !latlngs.length) return;
      const first = latlngs[0];
      if (!first) return;
      if (map.distance(first, homeCoord) > homeSnapThresholdM) return;
      latlngs[0] = homeCoord;
      poly.setLatLngs(latlngs);
  });

  map.on('tileerror', e => {
      const src = e && e.tile ? e.tile.src : '';
      console.error('Tile load failed' + (src ? (': ' + src) : ''));
  });

  window.__mapTools = window.__mapTools || {};
  window.__mapTools.screenToGeo = screenToGeo;
  window.__mapTools.setObjectSpawnMode = setObjectSpawnMode;
  window.__mapTools.setHomeMode = setHomeMode;
  window.__mapTools.setObjects = setObjects;

  const uavMarkers = new Map();
  const uavAnim = new Map();

  function ensureUavStyle() {
      if (document.getElementById('uav-style')) return;
      const style = document.createElement('style');
      style.id = 'uav-style';
      style.textContent = `
        .uav-marker {
          background: transparent;
          border: none;
        }
        .uav-icon {
          width: 22px;
          height: 22px;
          transform: translateZ(0);
        }
        .uav-icon svg {
          width: 100%;
          height: 100%;
          transform-origin: 50% 50%;
        }
        .uav-icon .uav-shape {
          fill: #ffffff;
          stroke: #000000;
          stroke-width: 2.5;
        }
      `;
      document.head.appendChild(style);
  }

  function buildUavIcon() {
      ensureUavStyle();
      const svg = '<div class="uav-icon"><svg viewBox="0 0 24 24" aria-hidden="true">' +
                  '<polygon class="uav-shape" points="12,2 22,22 2,22"></polygon>' +
                  '</svg></div>';
      return L.divIcon({
          className: 'uav-marker',
          html: svg,
          iconSize: [22, 22],
          iconAnchor: [11, 11]
      });
  }

  function updateUavRotation(marker, heading) {
      if (!marker || !marker._icon) return;
      const svg = marker._icon.querySelector('.uav-icon svg');
      if (!svg) return;
      const angle = (typeof heading === 'number') ? heading : 0;
      svg.style.transform = 'rotate(' + angle + 'deg)';
  }

  function normalizePose(payload) {
      if (!payload) return null;
      if (Array.isArray(payload) && payload.length >= 2) {
          return { id: 'uav', lat: payload[0], lon: payload[1], heading: payload[2] };
      }
      if (typeof payload !== 'object') return null;
      const lat = payload.lat ?? payload.latitude;
      const lon = payload.lon ?? payload.longitude;
      if (typeof lat !== 'number' || typeof lon !== 'number') return null;
      const id = payload.id || payload.uav_id || 'uav';
      const heading = typeof payload.heading === 'number' ? payload.heading : null;
      return { id, lat, lon, heading };
  }

  function angleDelta(a, b) {
      return ((b - a + 540) % 360) - 180;
  }

  function animateMarker(id, marker, from, to, headingFrom, headingTo) {
      const duration = 220;
      const start = performance.now();
      if (uavAnim.has(id)) {
          cancelAnimationFrame(uavAnim.get(id));
      }
      function step(now) {
          const t = Math.min(1, (now - start) / duration);
          const lat = from[0] + (to[0] - from[0]) * t;
          const lon = from[1] + (to[1] - from[1]) * t;
          marker.setLatLng([lat, lon]);
          if (headingFrom !== null && headingTo !== null) {
              const delta = angleDelta(headingFrom, headingTo);
              marker.__heading = headingFrom + delta * t;
              updateUavRotation(marker, marker.__heading);
          }
          if (t < 1) {
              uavAnim.set(id, requestAnimationFrame(step));
          }
      }
      uavAnim.set(id, requestAnimationFrame(step));
  }

  function setUavPose(payload) {
      const pose = normalizePose(payload);
      if (!pose) return;
      const id = String(pose.id || 'uav');
      const lat = pose.lat;
      const lon = pose.lon;
      const heading = typeof pose.heading === 'number' ? pose.heading : null;
      let entry = uavMarkers.get(id);
      if (!entry) {
          const marker = L.marker([lat, lon], {
              icon: buildUavIcon(),
              interactive: false
          }).addTo(map);
          marker.setZIndexOffset(1000);
          entry = { marker, lat, lon, heading };
          uavMarkers.set(id, entry);
          updateUavRotation(marker, heading);
          return;
      }
      const from = [entry.lat, entry.lon];
      const to = [lat, lon];
      const headingFrom = entry.heading;
      const headingTo = heading;
      entry.lat = lat;
      entry.lon = lon;
      entry.heading = heading;
      updateUavRotation(entry.marker, headingTo);
      animateMarker(id, entry.marker, from, to, headingFrom, headingTo);
  }

  window.__mapTools = window.__mapTools || {};
  window.__mapTools.setUavPose = setUavPose;
  window.__mapTools.setObjectSpawnMode = setObjectSpawnMode;
  window.__mapTools.setHomeMode = setHomeMode;
  window.__mapTools.screenToGeo = screenToGeo;
  if (window.__initialUavPose) {
      setUavPose(window.__initialUavPose);
  }

  const attr = document.querySelector('.leaflet-control-attribution');
  if (map.attributionControl) map.attributionControl.remove();
  if (attr) attr.remove();
})();"""

    def __init__(
        self,
        provider: str = "osm",
        *,
        offline: bool = False,
        cache_dir: Path | None = None,
    ) -> None:
        self._map_path: Path = Path(tempfile.gettempdir()) / "plan_map.html"
        self._radius_px = 18  # match QML card radius
        self._provider = provider if provider in self.TILESETS else "de"
        self._offline = offline
        self._cache_dir = cache_dir or Path(tempfile.gettempdir()) / "tile-cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def bridge_script(self) -> str:
        return self._BRIDGE_JS

    def set_provider(self, provider: str, *, offline: bool, cache_dir: Path | None = None) -> None:
        self._provider = provider if provider in self.TILESETS else "de"
        self._offline = offline
        if cache_dir:
            self._cache_dir = cache_dir
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _tile_layer(self) -> tuple[str, str]:
        if self._offline:
            url = f"file://{self._cache_dir.as_posix()}" + "/{z}/{x}/{y}.png"
            return url, f"Offline cache ({self._provider})"
        url, attr = self.TILESETS.get(self._provider, self.TILESETS["de"])
        return url, attr

    def render_map(
        self, path: list[tuple[float, float]], token: int, path_kind: str | None = None
    ) -> Path:
        folium = _get_folium()
        draw_cls = _get_folium_draw()
        center = path[0] if path else (56.02, 92.9)
        tiles_url, attr = self._tile_layer()
        telemetry = getattr(deps, "latest_telemetry", None)
        mission_state = str(getattr(deps, "mission_state", "") or "")
        show_drone = mission_state in ("IN_FLIGHT", "RTL")
        drone_pos = None
        heading = None
        if telemetry is not None and hasattr(telemetry, "lat") and hasattr(telemetry, "lon"):
            try:
                drone_pos = (float(telemetry.lat), float(telemetry.lon))
                if hasattr(telemetry, "yaw"):
                    heading = float(telemetry.yaw)
            except Exception:
                drone_pos = None
        if drone_pos is None:
            drone_pos = interpolate_path_point(path, getattr(deps, "debug_flight_progress", 0.0))

        fmap = folium.Map(
            center,
            zoom_start=13,
            control_scale=False,
            zoom_control=True,
            prefer_canvas=True,
            tiles=None,
            attributionControl=False,
        )

        fmap.get_root().script.add_child(
            folium.Element(f"window.__map = {fmap.get_name()};")
        )

        folium.raster_layers.TileLayer(
            tiles=tiles_url,
            attr=attr,
            name=self._provider,
            overlay=False,
            control=False,
        ).add_to(fmap)

        draw_cls(
            export=False,
            draw_options={
                "polyline": {"shapeOptions": {"color": "#000000"}},
                "polygon": False,
                "rectangle": False,
                "circle": False,
                "circlemarker": False,
                "marker": {"repeatMode": False},
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(fmap)

        if path:
            folium.PolyLine(path, color="#000000", weight=3).add_to(fmap)
            folium.CircleMarker(
                location=path[0],
                radius=7,
                color="#000000",
                fill=True,
                fill_color="#ffffff",
                weight=2,
                tooltip="Start",
            ).add_to(fmap)
            folium.CircleMarker(
                location=path[-1],
                radius=7,
                color="#000000",
                fill=True,
                fill_color="#ffffff",
                weight=2,
                tooltip="Finish",
            ).add_to(fmap)

        anchor = getattr(deps, "route_edit_anchor", None)
        if mission_state == "IN_FLIGHT" and isinstance(anchor, dict):
            lat = anchor.get("lat")
            lon = anchor.get("lon")
            if lat is not None and lon is not None:
                try:
                    anchor_loc = (float(lat), float(lon))
                except (TypeError, ValueError):
                    anchor_loc = None
                if anchor_loc is not None:
                    folium.CircleMarker(
                        location=anchor_loc,
                        radius=7,
                        color="#000000",
                        fill=True,
                        fill_color="#ffffff",
                        weight=2,
                        tooltip="Edit start",
                    ).add_to(fmap)

        if drone_pos and show_drone:
            heading = None
            if telemetry is not None and hasattr(telemetry, "yaw"):
                try:
                    heading = float(telemetry.yaw)
                except Exception:
                    heading = None
            uav_id = None
            source = getattr(telemetry, "source", None) if telemetry is not None else None
            if source:
                uav_id = str(source)
            if not uav_id:
                uav_id = str(getattr(settings, "uav_id", None) or "uav")
            payload = json.dumps(
                {"id": uav_id, "lat": drone_pos[0], "lon": drone_pos[1], "heading": heading}
            )
            fmap.get_root().html.add_child(
                folium.Element(f"<script>window.__initialUavPose = {payload};</script>")
            )

        home = getattr(deps, "home_location", None)
        if isinstance(home, dict):
            lat = home.get("lat")
            lon = home.get("lon")
            if lat is not None and lon is not None:
                try:
                    home_payload = json.dumps({"lat": float(lat), "lon": float(lon)})
                except (TypeError, ValueError):
                    home_payload = None
                if home_payload:
                    fmap.get_root().html.add_child(
                        folium.Element(f"<script>window.__homeCoord = {home_payload};</script>")
                    )

        if _spawn_debug_visuals_enabled() and deps.debug_target:
            lat = deps.debug_target.get("lat")
            lon = deps.debug_target.get("lon")
            if lat is not None and lon is not None:
                folium.CircleMarker(
                    location=(lat, lon),
                    radius=6,
                    color="#000000",
                    fill=True,
                    fill_color="#ffffff",
                    weight=2,
                ).add_to(fmap)

        home = getattr(deps, "home_location", None)
        if isinstance(home, dict):
            lat = home.get("lat")
            lon = home.get("lon")
            if lat is not None and lon is not None:
                folium.CircleMarker(
                    location=(lat, lon),
                    radius=7,
                    color="#000000",
                    fill=True,
                    fill_color="#7bc6ff",
                    weight=3,
                    tooltip="Home",
                ).add_to(fmap)

        if _spawn_debug_visuals_enabled() and deps.debug_orbit_path and deps.debug_orbit_path != path:
            folium.PolyLine(
                locations=[(lat, lon) for lat, lon in deps.debug_orbit_path],
                color="orange",
                weight=2,
            ).add_to(fmap)

        preview_paths = getattr(deps, "debug_orbit_preview_paths", []) or []
        for raw_path in preview_paths:
            coords = []
            for lat, lon in raw_path or []:
                try:
                    coords.append((float(lat), float(lon)))
                except (TypeError, ValueError):
                    continue
            if len(coords) < 2:
                continue
            folium.PolyLine(
                locations=coords,
                color="#7bc6ff",
                weight=2,
                dash_array="12 8",
                opacity=0.9,
            ).add_to(fmap)

        for lat, lon in (getattr(deps, "debug_orbit_targets", []) or []):
            try:
                center = (float(lat), float(lon))
            except (TypeError, ValueError):
                continue
            folium.Circle(
                location=center,
                radius=float(getattr(settings, "orbit_radius_m", 50.0) or 50.0),
                color="#7bc6ff",
                weight=2,
                fill=True,
                fill_opacity=0.06,
                dash_array="10 8",
            ).add_to(fmap)

        sequence_coords = []
        for lat, lon in (getattr(deps, "debug_orbit_sequence", []) or []):
            try:
                sequence_coords.append((float(lat), float(lon)))
            except (TypeError, ValueError):
                continue
        if len(sequence_coords) >= 2:
            folium.PolyLine(
                locations=sequence_coords,
                color="#ffd666",
                weight=3,
                dash_array="8 10",
                opacity=0.8,
            ).add_to(fmap)

        fmap.get_root().header.add_child(
            folium.Element(
                f"""
<style>
.folium-map, .leaflet-container {{
    border-radius: {self._radius_px}px !important;
    overflow: hidden !important;
    background: transparent !important;
}}
.leaflet-pane, .leaflet-map-pane {{
    border-radius: {self._radius_px}px !important;
    overflow: hidden !important;
    background: transparent !important;
}}
.leaflet-control-attribution {{
    display: none !important;
}}
html, body {{
    background: transparent !important;
    margin: 0;
}}
</style>
"""
            )
        )

        fmap.save(self._map_path)
        return self._map_path


class OpenLayersMapProvider:
    """OpenLayers map provider with simple draw/edit tooling."""

    TILESETS: dict[str, tuple[str, str]] = {
        "de": ("https://tile.openstreetmap.de/{z}/{x}/{y}.png", "OpenStreetMap.de"),
        "hot": ("https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", "OSM Humanitarian"),
        "osmfr": ("https://a.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png", "OpenStreetMap France"),
        "topo": ("https://tile.opentopomap.org/{z}/{x}/{y}.png", "OpenTopoMap"),
        "carto": ("https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", "Carto Light"),
    }

    def __init__(
        self,
        provider: str = "openlayers_de",
        *,
        offline: bool = False,
        cache_dir: Path | None = None,
        static_image_path: str | None = None,
        static_bounds: MapBounds | None = None,
    ) -> None:
        self._map_path: Path = Path(tempfile.gettempdir()) / "plan_map.html"
        self._radius_px = 18  # match QML card radius
        self._provider = self._normalize_provider(provider)
        self._offline = offline
        self._cache_dir = cache_dir
        self._static_image_path = static_image_path
        self._static_bounds = static_bounds

    @property
    def bridge_script(self) -> str:
        return ""

    def set_provider(self, provider: str, *, offline: bool, cache_dir: Path | None = None) -> None:
        self._provider = self._normalize_provider(provider)
        self._offline = offline
        self._cache_dir = cache_dir

    def _normalize_provider(self, provider: str) -> str:
        name = (provider or "").lower()
        if name.startswith("openlayers_"):
            name = name.split("openlayers_", 1)[1]
        elif name.startswith("ol_"):
            name = name.split("ol_", 1)[1]
        return name if name in self.TILESETS else "de"

    def _tile_layer(self) -> tuple[str, str]:
        url, attr = self.TILESETS.get(self._provider, self.TILESETS["de"])
        return url, attr

    def _asset_urls(self) -> tuple[str, str]:
        assets_dir = Path(__file__).resolve().parent / "assets" / "ol"
        css_path = assets_dir / "ol.css"
        js_path = assets_dir / "ol.js"
        if css_path.exists() and js_path.exists():
            return css_path.resolve().as_uri(), js_path.resolve().as_uri()
        return (
            "https://cdn.jsdelivr.net/npm/ol@7.5.2/ol.css",
            "https://cdn.jsdelivr.net/npm/ol@7.5.2/dist/ol.js",
        )

    def _route_stats_payload(
        self,
        path: list[tuple[float, float]],
        telemetry: object | None,
    ) -> dict:
        raw_stats = getattr(deps, "route_stats", None)
        stats = dict(raw_stats) if isinstance(raw_stats, dict) else {}

        max_distance_m = stats.get("max_distance_m")
        if not isinstance(max_distance_m, (int, float)):
            max_distance_m = float(getattr(settings, "max_flight_distance_m", 15000.0) or 0.0)

        reserved_percent = stats.get("reserved_percent")
        if not isinstance(reserved_percent, (int, float)):
            reserved_percent = float(getattr(settings, "min_return_percent", 20.0) or 0.0)

        available_percent = stats.get("available_percent")
        if not isinstance(available_percent, (int, float)):
            available_percent = 100.0
            if telemetry is not None and getattr(telemetry, "battery_percent", None) is not None:
                try:
                    available_percent = float(telemetry.battery_percent)
                except (TypeError, ValueError):
                    pass

        base = stats.get("base")
        base_lonlat = None
        if isinstance(base, (list, tuple)) and len(base) >= 2:
            try:
                base_lonlat = [float(base[0]), float(base[1])]
            except (TypeError, ValueError):
                base_lonlat = None

        if base_lonlat is None:
            route = Route(
                version=1,
                waypoints=[Waypoint(lat=lat, lon=lon, alt=0.0) for lat, lon in path],
                active_index=0 if path else None,
            )
            telemetry_sample = None
            if telemetry is not None and hasattr(telemetry, "lat") and hasattr(telemetry, "lon"):
                try:
                    payload = {
                        "lat": float(telemetry.lat),
                        "lon": float(telemetry.lon),
                        "alt": float(getattr(telemetry, "alt", 0.0) or 0.0),
                        "yaw": float(getattr(telemetry, "yaw", 0.0) or 0.0),
                        "pitch": float(getattr(telemetry, "pitch", 0.0) or 0.0),
                        "roll": float(getattr(telemetry, "roll", 0.0) or 0.0),
                        "battery": float(getattr(telemetry, "battery", 1.0) or 1.0),
                        "battery_percent": getattr(telemetry, "battery_percent", None),
                    }
                    timestamp = getattr(telemetry, "timestamp", None)
                    if timestamp is not None:
                        payload["timestamp"] = timestamp
                    telemetry_sample = TelemetrySample(**payload)
                except Exception:
                    telemetry_sample = None
            resolved = resolve_base_location(settings, route, telemetry_sample)
            if resolved is not None:
                base_lonlat = [float(resolved.lon), float(resolved.lat)]

        return {
            "max_distance_m": max_distance_m,
            "reserved_percent": reserved_percent,
            "available_percent": available_percent,
            "base": base_lonlat,
        }

    def render_map(
        self, path: list[tuple[float, float]], token: int, path_kind: str | None = None
    ) -> Path:
        preview_path = getattr(deps, "route_edit_preview_path", None)
        if isinstance(preview_path, list):
            path = [(float(lat), float(lon)) for lat, lon in preview_path]
        center = path[0] if path else (56.02, 92.9)
        tiles_url, attr = self._tile_layer()
        css_url, js_url = self._asset_urls()
        telemetry = getattr(deps, "latest_telemetry", None)
        mission_state = str(getattr(deps, "mission_state", "") or "")
        drone_pos = None
        heading = None
        if telemetry is not None and hasattr(telemetry, "lat") and hasattr(telemetry, "lon"):
            try:
                drone_pos = (float(telemetry.lat), float(telemetry.lon))
            except Exception:
                drone_pos = None
            if drone_pos is not None and hasattr(telemetry, "yaw"):
                try:
                    heading = float(telemetry.yaw)
                except Exception:
                    heading = None
        if drone_pos is None:
            drone_pos = interpolate_path_point(path, getattr(deps, "debug_flight_progress", 0.0))
        show_drone = mission_state in ("IN_FLIGHT", "RTL")

        path_coords = [[lon, lat] for lat, lon in path]
        path_done: list[list[float]] = []
        path_remaining: list[list[float]] = []
        if path and getattr(deps, "debug_flight_enabled", False):
            try:
                progress = float(getattr(deps, "debug_flight_progress", 0.0))
            except Exception:
                progress = 0.0
            progress = max(0.0, min(1.0, progress))
            done_pts: list[tuple[float, float]] = []
            remaining_pts: list[tuple[float, float]] = []
            if progress <= 0.0:
                remaining_pts = path[:]
            elif progress >= 1.0:
                done_pts = path[:]
            else:
                total = 0.0
                for a, b in zip(path[:-1], path[1:]):
                    total += haversine_m(a, b)
                if total <= 0:
                    done_pts = path[:]
                else:
                    target = total * progress
                    accum = 0.0
                    done_pts = [path[0]]
                    for idx in range(len(path) - 1):
                        a = path[idx]
                        b = path[idx + 1]
                        seg = haversine_m(a, b)
                        if accum + seg < target:
                            done_pts.append(b)
                            accum += seg
                            continue
                        if seg <= 0:
                            continue
                        frac = max(0.0, min(1.0, (target - accum) / seg))
                        interp = (
                            a[0] + (b[0] - a[0]) * frac,
                            a[1] + (b[1] - a[1]) * frac,
                        )
                        done_pts.append(interp)
                        remaining_pts = [interp] + path[idx + 1 :]
                        break
            path_done = [[lon, lat] for lat, lon in done_pts]
            path_remaining = [[lon, lat] for lat, lon in remaining_pts]
        debug_orbit_coords = []
        if _spawn_debug_visuals_enabled():
            debug_orbit_coords = [
                [lon, lat] for lat, lon in (getattr(deps, "debug_orbit_path", []) or [])
            ]
        orbit_targets = []
        for lat, lon in (getattr(deps, "debug_orbit_targets", []) or []):
            try:
                orbit_targets.append([float(lon), float(lat)])
            except (TypeError, ValueError):
                continue
        orbit_sequence = []
        for lat, lon in (getattr(deps, "debug_orbit_sequence", []) or []):
            try:
                orbit_sequence.append([float(lon), float(lat)])
            except (TypeError, ValueError):
                continue
        orbit_preview_paths = []
        for raw_path in (getattr(deps, "debug_orbit_preview_paths", []) or []):
            coords = []
            for lat, lon in raw_path or []:
                try:
                    coords.append([float(lon), float(lat)])
                except (TypeError, ValueError):
                    continue
            if len(coords) >= 2:
                orbit_preview_paths.append(coords)
        target = None
        if _spawn_debug_visuals_enabled() and deps.debug_target:
            lat = deps.debug_target.get("lat")
            lon = deps.debug_target.get("lon")
            if lat is not None and lon is not None:
                target = [float(lon), float(lat)]

        objects = []
        for obj in getattr(deps, "confirmed_objects", []) or []:
            try:
                lat = float(obj.get("lat"))
                lon = float(obj.get("lon"))
            except Exception:
                continue
            objects.append(
                {
                    "object_id": str(obj.get("object_id", "")),
                    "display_index": int(obj.get("display_index", obj.get("object_index", 0)) or 0),
                    "lat": lat,
                    "lon": lon,
                    "selected": bool(obj.get("selected", False)),
                }
            )
        selected_id = str(getattr(deps, "selected_object_id", "") or "")
        home = getattr(deps, "home_location", None)
        home_coord = None
        if isinstance(home, dict):
            lat = home.get("lat")
            lon = home.get("lon")
            if lat is not None and lon is not None:
                try:
                    home_coord = [float(lon), float(lat)]
                except (TypeError, ValueError):
                    home_coord = None
        route_edit_anchor = None
        anchor_data = getattr(deps, "route_edit_anchor", None)
        if isinstance(anchor_data, dict):
            lat = anchor_data.get("lat")
            lon = anchor_data.get("lon")
            if lat is not None and lon is not None:
                try:
                    route_edit_anchor = [float(lon), float(lat)]
                except (TypeError, ValueError):
                    route_edit_anchor = None
        route_edit_locked = []
        for lat, lon in (getattr(deps, "route_edit_locked_path", None) or []):
            try:
                route_edit_locked.append([float(lon), float(lat)])
            except (TypeError, ValueError):
                continue

        uav_id = None
        source = getattr(telemetry, "source", None) if telemetry is not None else None
        if source:
            uav_id = str(source)
        if not uav_id:
            uav_id = str(getattr(settings, "uav_id", None) or "uav")

        resolved_path_kind = path_kind if path_kind in ("mission", "maneuver") else None
        if resolved_path_kind is None:
            active_kind = getattr(deps, "active_path_kind", "mission")
            resolved_path_kind = active_kind if active_kind in ("mission", "maneuver") else "mission"

        payload = {
            "center": [float(center[1]), float(center[0])],
            "tiles_url": tiles_url,
            "attribution": attr,
            "path": path_coords,
            "path_kind": resolved_path_kind,
            "path_done": path_done,
            "path_remaining": path_remaining,
            "debug_orbit": debug_orbit_coords,
            "orbit_targets": orbit_targets,
            "orbit_sequence": orbit_sequence,
            "orbit_preview_paths": orbit_preview_paths,
            "orbit_radius_m": float(getattr(settings, "orbit_radius_m", 50.0) or 50.0),
            "route_edit_anchor": route_edit_anchor,
            "route_edit_locked": route_edit_locked,
            "drone": [float(drone_pos[1]), float(drone_pos[0])] if (drone_pos and show_drone) else None,
            "uav_id": uav_id,
            "heading": heading,
            "target": target,
            "objects": objects,
            "selected_id": selected_id,
            "home": home_coord,
            "radius_px": self._radius_px,
            "route_stats": self._route_stats_payload(path, telemetry),
        }
        if self._static_image_path and self._static_bounds:
            image_url = None
            try:
                image_url = Path(self._static_image_path).expanduser().resolve().as_uri()
            except Exception:
                image_url = str(self._static_image_path)
            payload["static_image"] = image_url
            payload["static_bounds"] = {
                "lat_min": float(self._static_bounds.lat_min),
                "lon_min": float(self._static_bounds.lon_min),
                "lat_max": float(self._static_bounds.lat_max),
                "lon_max": float(self._static_bounds.lon_max),
            }

        html = f"""\
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="stylesheet" href="{css_url}" />
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background: #000000;
    }}
    #map {{
      width: 100%;
      height: 100%;
      border-radius: {payload["radius_px"]}px;
      overflow: hidden;
      background: #000000;
    }}
    .ol-control, .ol-zoom, .ol-rotate, .ol-attribution {{
      display: none !important;
    }}
  </style>
  <script src="{js_url}"></script>
</head>
<body>
  <div id="map"></div>
  <script>
  (() => {{
    window.addEventListener('error', (event) => {{
      const msg = event && event.message ? event.message : 'Unknown error';
      console.error('JS error', msg);
    }});
    window.addEventListener('unhandledrejection', (event) => {{
      const reason = event && event.reason ? event.reason : 'Unknown rejection';
      console.error('JS rejection', reason);
    }});
    try {{
      if (!window.ol) {{
        console.error('OpenLayers failed to load');
        return;
      }}
      const data = {json.dumps(payload)};
      const view = new ol.View({{
        center: ol.proj.fromLonLat(data.center),
        zoom: 13
      }});

      let baseLayer = null;
      let staticExtent = null;
      if (data.static_image && data.static_bounds) {{
        const sw = ol.proj.fromLonLat([data.static_bounds.lon_min, data.static_bounds.lat_min]);
        const ne = ol.proj.fromLonLat([data.static_bounds.lon_max, data.static_bounds.lat_max]);
        staticExtent = [sw[0], sw[1], ne[0], ne[1]];
        const imageSource = new ol.source.ImageStatic({{
          url: data.static_image,
          imageExtent: staticExtent,
          projection: view.getProjection()
        }});
        baseLayer = new ol.layer.Image({{ source: imageSource }});
      }} else {{
        const tileSource = new ol.source.XYZ({{
          url: data.tiles_url,
          attributions: data.attribution
        }});
        tileSource.on('tileloaderror', () => {{
          console.error('Tile load failed');
        }});
        baseLayer = new ol.layer.Tile({{ source: tileSource }});
      }}
      const drawSource = new ol.source.Vector();
      const overlaySource = new ol.source.Vector();

    const styles = {{
      path: new ol.style.Style({{
        stroke: new ol.style.Stroke({{ color: '#000000', width: 3 }})
      }}),
      lockedPath: new ol.style.Style({{
        stroke: new ol.style.Stroke({{ color: 'rgba(0,0,0,0.28)', width: 3, lineDash: [8, 8] }})
      }}),
      pathDone: new ol.style.Style({{
        stroke: new ol.style.Stroke({{ color: 'rgba(255,255,255,0.35)', width: 4 }})
      }}),
      pathRemaining: new ol.style.Style({{
        stroke: new ol.style.Stroke({{ color: 'rgba(0,0,0,0.95)', width: 4 }})
      }}),
      orbit: new ol.style.Style({{
        stroke: new ol.style.Stroke({{ color: '#000000', width: 2 }})
      }}),
      start: new ol.style.Style({{
        image: new ol.style.Circle({{
          radius: 6,
          fill: new ol.style.Fill({{ color: '#ffffff' }}),
          stroke: new ol.style.Stroke({{ color: '#000000', width: 2 }})
        }})
      }}),
      finish: new ol.style.Style({{
        image: new ol.style.Circle({{
          radius: 6,
          fill: new ol.style.Fill({{ color: '#ffffff' }}),
          stroke: new ol.style.Stroke({{ color: '#000000', width: 2 }})
        }})
      }}),
      drone: new ol.style.Style({{
        image: new ol.style.RegularShape({{
          points: 3,
          radius: 9,
          rotation: Math.PI / 2,
          fill: new ol.style.Fill({{ color: '#ffffff' }}),
          stroke: new ol.style.Stroke({{ color: '#000000', width: 3 }})
        }})
      }}),
      target: new ol.style.Style({{
        image: new ol.style.Circle({{
          radius: 6,
          fill: new ol.style.Fill({{ color: '#ffffff' }}),
          stroke: new ol.style.Stroke({{ color: '#000000', width: 2 }})
        }})
      }}),
      home: new ol.style.Style({{
        image: new ol.style.Circle({{
          radius: 7,
          fill: new ol.style.Fill({{ color: '#7bc6ff' }}),
          stroke: new ol.style.Stroke({{ color: '#000000', width: 3 }})
        }})
      }}),
      editAnchor: new ol.style.Style({{
        image: new ol.style.Circle({{
          radius: 7,
          fill: new ol.style.Fill({{ color: '#ffffff' }}),
          stroke: new ol.style.Stroke({{ color: '#000000', width: 3 }})
        }})
      }}),
      object: new ol.style.Style({{
        image: new ol.style.Circle({{
          radius: 11,
          fill: new ol.style.Fill({{ color: '#ffffff' }}),
          stroke: new ol.style.Stroke({{ color: '#000000', width: 2 }})
        }}),
        text: new ol.style.Text({{
          text: '',
          font: '600 11px Inter',
          fill: new ol.style.Fill({{ color: '#000000' }}),
          textAlign: 'center',
          textBaseline: 'middle'
        }})
      }}),
      objectSelected: new ol.style.Style({{
        image: new ol.style.Circle({{
          radius: 12,
          fill: new ol.style.Fill({{ color: '#ffffff' }}),
          stroke: new ol.style.Stroke({{ color: '#000000', width: 3 }})
        }}),
        text: new ol.style.Text({{
          text: '',
          font: '700 11px Inter',
          fill: new ol.style.Fill({{ color: '#000000' }}),
          textAlign: 'center',
          textBaseline: 'middle'
        }})
      }})
    }};

    const routeStats = data.route_stats || {{}};
    const pathKind = data.path_kind === 'maneuver' ? 'maneuver' : 'mission';
    const maxDistanceM = typeof routeStats.max_distance_m === 'number' ? routeStats.max_distance_m : 0;
    const reservedPercent = typeof routeStats.reserved_percent === 'number' ? routeStats.reserved_percent : 0;
    const availablePercent = typeof routeStats.available_percent === 'number' ? routeStats.available_percent : 100;
    const baseCoord = Array.isArray(routeStats.base) && routeStats.base.length >= 2 ? routeStats.base : null;
    const clampEnabled = routeStats.clamp_enabled === true;

    function clamp(value, min, max) {{
      return Math.max(min, Math.min(max, value));
    }}

    function haversineM(a, b) {{
      if (!a || !b) return 0;
      const toRad = deg => deg * Math.PI / 180;
      const lat1 = toRad(a[1]);
      const lat2 = toRad(b[1]);
      const dlat = lat2 - lat1;
      const dlon = toRad(b[0] - a[0]);
      const sinDlat = Math.sin(dlat / 2);
      const sinDlon = Math.sin(dlon / 2);
      const h = sinDlat * sinDlat + Math.cos(lat1) * Math.cos(lat2) * sinDlon * sinDlon;
      return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(h)));
    }}

    function estimateRemainingPercent(routeMeters, endCoord) {{
      if (!maxDistanceM || maxDistanceM <= 0) return null;
      const returnLeg = baseCoord ? haversineM(endCoord, baseCoord) : 0;
      const required = ((routeMeters + returnLeg) / maxDistanceM) * 100.0;
      return availablePercent - (required + reservedPercent);
    }}

    function estimateRouteRemainingPercent(routeMeters) {{
      if (!maxDistanceM || maxDistanceM <= 0) return null;
      const required = (routeMeters / maxDistanceM) * 100.0;
      return 100.0 - required;
    }}

    function clampPathToBattery(coords) {{
      if (!clampEnabled) return coords;
      if (!coords || coords.length < 2) return coords;
      if (!maxDistanceM || maxDistanceM <= 0) return coords;
      let cumulative = 0;
      const clamped = [coords[0]];
      for (let i = 0; i < coords.length - 1; i++) {{
        const a = coords[i];
        const b = coords[i + 1];
        const seg = haversineM(a, b);
        if (!seg || seg <= 0) continue;
        const cumulativeNext = cumulative + seg;
        const remainingNext = estimateRemainingPercent(cumulativeNext, b);
        if (remainingNext === null) {{
          clamped.push(b);
          cumulative = cumulativeNext;
          continue;
        }}
        if (remainingNext <= 0) {{
          const remainingPrev = estimateRemainingPercent(cumulative, a) ?? remainingNext;
          let t = 0.0;
          if (remainingPrev > remainingNext) {{
            t = remainingPrev / (remainingPrev - remainingNext);
          }}
          t = clamp(t, 0, 1);
          const interp = [
            a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t
          ];
          clamped.push(interp);
          return clamped;
        }}
        clamped.push(b);
        cumulative = cumulativeNext;
      }}
      return clamped;
    }}

    function colorForRemaining(remaining) {{
      if (remaining === null || Number.isNaN(remaining)) return '#94a3b8';
      const t = clamp(remaining / 100.0, 0, 1);
      const r = Math.round(248 + (52 - 248) * t);
      const g = Math.round(113 + (211 - 113) * t);
      const b = Math.round(113 + (153 - 113) * t);
      return `rgb(${{r}}, ${{g}}, ${{b}})`;
    }}

    function segmentStyle(feature) {{
      const remaining = feature.get('remaining');
      return new ol.style.Style({{
        stroke: new ol.style.Stroke({{
          color: '#000000',
          width: 4
        }})
      }});
    }}

    function segmentLabelStyle(feature) {{
      const label = feature.get('label');
      if (!label) return null;
      const remaining = feature.get('remaining');
      const angle = feature.get('angle');
      return new ol.style.Style({{
        text: new ol.style.Text({{
          text: label,
          font: '11px Inter, sans-serif',
          fill: new ol.style.Fill({{ color: colorForRemaining(remaining) }}),
          stroke: new ol.style.Stroke({{ color: 'rgba(10,16,24,0.55)', width: 2 }}),
          rotation: typeof angle === 'number' ? angle : 0,
          rotateWithView: true,
          textAlign: 'center',
          textBaseline: 'middle'
        }})
      }});
    }}

    function styleForFeature(feature) {{
      const kind = feature.get('kind');
      if (kind === 'drone') {{
        const heading = feature.get('heading');
        if (typeof heading === 'number') {{
          return new ol.style.Style({{
            image: new ol.style.RegularShape({{
              points: 3,
              radius: 9,
              rotation: (heading * Math.PI / 180) + Math.PI / 2,
              fill: new ol.style.Fill({{ color: '#ffffff' }}),
              stroke: new ol.style.Stroke({{ color: '#000000', width: 3 }})
            }})
          }});
        }}
        return styles.drone;
      }}
      if (kind === 'object') {{
        const selected = feature.get('selected');
        const objectId = feature.get('object_id') || '';
        const baseStyle = (selected === true)
          ? styles.objectSelected.clone()
          : ((selected === false) ? styles.object.clone() : (objectId && objectId === data.selected_id ? styles.objectSelected.clone() : styles.object.clone()));
        const label = feature.get('object_index');
        if (baseStyle.getText()) {{
          baseStyle.getText().setText(label ? String(label) : '');
        }}
        return baseStyle;
      }}
      if (kind === 'orbitTarget') {{
        return new ol.style.Style({{
          stroke: new ol.style.Stroke({{
            color: 'rgba(123, 198, 255, 0.85)',
            width: 2,
            lineDash: [10, 8]
          }}),
          fill: new ol.style.Fill({{
            color: 'rgba(123, 198, 255, 0.08)'
          }})
        }});
      }}
      if (kind === 'orbitSequence') {{
        return new ol.style.Style({{
          stroke: new ol.style.Stroke({{
            color: 'rgba(255, 214, 102, 0.78)',
            width: 3,
            lineDash: [8, 10]
          }})
        }});
      }}
      if (kind === 'orbitPreview') {{
        return new ol.style.Style({{
          stroke: new ol.style.Stroke({{
            color: 'rgba(123, 198, 255, 0.92)',
            width: 2.5,
            lineDash: [14, 8]
          }})
        }});
      }}
      if (kind === 'segment') {{
        return segmentStyle(feature);
      }}
      if (kind === 'segmentLabel') {{
        return segmentLabelStyle(feature);
      }}
      return styles[kind] || styles.path;
    }}

    const drawLayer = new ol.layer.Vector({{
      source: drawSource,
      style: styleForFeature
    }});
    const overlayLayer = new ol.layer.Vector({{
      source: overlaySource,
      style: styleForFeature
    }});

      const mapOptions = {{
        target: 'map',
        layers: [baseLayer, drawLayer, overlayLayer],
        view
      }};
      if (ol.control && typeof ol.control.defaults === 'function') {{
        mapOptions.controls = ol.control.defaults({{ attribution: false }});
      }}
      const map = new ol.Map(mapOptions);
      if (staticExtent) {{
        view.fit(staticExtent, {{ padding: [24, 24, 24, 24], size: map.getSize() }});
      }}
      window.screenToGeo = function(x, y) {{
        if (!map) return null;
        const coord = map.getCoordinateFromPixel([x, y]);
        if (!coord) return null;
        const lonLat = ol.proj.toLonLat(coord);
        return {{ lat: lonLat[1], lon: lonLat[0] }};
      }};

    const geojson = new ol.format.GeoJSON();
    let suppressEmit = true;

    const uavStates = new Map();
    const uavAnims = new Map();
    let spawnMode = false;
    let homeMode = false;

    function normalizePose(payload) {{
      if (!payload) return null;
      if (Array.isArray(payload) && payload.length >= 2) {{
        return {{ id: 'uav', coord: [payload[0], payload[1]], heading: payload[2] }};
      }}
      if (typeof payload !== 'object') return null;
      const lat = payload.lat ?? payload.latitude;
      const lon = payload.lon ?? payload.longitude;
      if (typeof lat !== 'number' || typeof lon !== 'number') return null;
      const id = payload.id || payload.uav_id || 'uav';
      const heading = typeof payload.heading === 'number' ? payload.heading : null;
      return {{ id: String(id), coord: [lon, lat], heading }};
    }}

    function angleDelta(a, b) {{
      return ((b - a + 540) % 360) - 180;
    }}

    function findDroneFeature(uavId) {{
      return overlaySource.getFeatures().find(f => f.get('kind') === 'drone' && f.get('uav_id') === uavId);
    }}

    function ensureDroneFeature(uavId) {{
      let feature = findDroneFeature(uavId);
      if (!feature) {{
        feature = new ol.Feature({{ kind: 'drone', uav_id: uavId }});
        feature.setGeometry(new ol.geom.Point([0, 0]));
        overlaySource.addFeature(feature);
      }}
      return feature;
    }}

    function animateDrone(uavId, fromCoord, toCoord, headingFrom, headingTo) {{
      const feature = ensureDroneFeature(uavId);
      const duration = 220;
      const start = performance.now();
      if (uavAnims.has(uavId)) {{
        cancelAnimationFrame(uavAnims.get(uavId));
      }}
      function step(now) {{
        const t = Math.min(1, (now - start) / duration);
        const lon = fromCoord[0] + (toCoord[0] - fromCoord[0]) * t;
        const lat = fromCoord[1] + (toCoord[1] - fromCoord[1]) * t;
        feature.getGeometry().setCoordinates(ol.proj.fromLonLat([lon, lat]));
        if (headingFrom !== null && headingTo !== null) {{
          const delta = angleDelta(headingFrom, headingTo);
          feature.set('heading', headingFrom + delta * t);
        }}
        if (t < 1) {{
          uavAnims.set(uavId, requestAnimationFrame(step));
        }}
      }}
      uavAnims.set(uavId, requestAnimationFrame(step));
    }}

    function setUavPose(payload, animate = true) {{
      const pose = normalizePose(payload);
      if (!pose) return;
      const uavId = pose.id || 'uav';
      const coord = pose.coord;
      const heading = pose.heading;
      const state = uavStates.get(uavId);
      const feature = ensureDroneFeature(uavId);
      if (!state || !state.coord || !animate) {{
        feature.getGeometry().setCoordinates(ol.proj.fromLonLat(coord));
        if (typeof heading === 'number') {{
          feature.set('heading', heading);
        }}
        uavStates.set(uavId, {{ coord, heading }});
        return;
      }}
      const headingFrom = typeof state.heading === 'number' ? state.heading : null;
      const headingTo = typeof heading === 'number' ? heading : headingFrom;
      uavStates.set(uavId, {{ coord, heading: headingTo }});
      animateDrone(uavId, state.coord, coord, headingFrom, headingTo);
    }}

    function removeByType(type) {{
      drawSource.getFeatures().forEach(f => {{
        if (f.getGeometry().getType() === type) drawSource.removeFeature(f);
      }});
    }}

    function setEditableLine(coords) {{
      removeByType('LineString');
      if (!coords || coords.length < 2) return;
      const line = new ol.geom.LineString(coords.map(c => ol.proj.fromLonLat(c)));
      const feature = new ol.Feature({{ geometry: line, kind: 'path' }});
      drawSource.addFeature(feature);
    }}

    function setEditableTarget(coord) {{
      removeByType('Point');
      if (!coord) return;
      const point = new ol.geom.Point(ol.proj.fromLonLat(coord));
      const feature = new ol.Feature({{ geometry: point, kind: 'target' }});
      drawSource.addFeature(feature);
    }}

    function addOverlayPoint(coord, kind, props) {{
      if (!coord) return;
      const point = new ol.geom.Point(ol.proj.fromLonLat(coord));
      const feature = new ol.Feature(Object.assign({{ geometry: point, kind }}, props || {{}}));
      overlaySource.addFeature(feature);
    }}

    function addOverlayLine(coords, kind, props) {{
      if (!coords || coords.length < 2) return;
      const line = new ol.geom.LineString(coords.map(c => ol.proj.fromLonLat(c)));
      const feature = new ol.Feature(Object.assign({{ geometry: line, kind }}, props || {{}}));
      overlaySource.addFeature(feature);
    }}

    function addOverlayCircle(coord, radiusM, kind, props) {{
      if (!coord || !Number.isFinite(radiusM) || radiusM <= 0) return;
      const center3857 = ol.proj.fromLonLat(coord);
      const circle = new ol.geom.Circle(center3857, radiusM);
      const feature = new ol.Feature(Object.assign({{ geometry: circle, kind }}, props || {{}}));
      overlaySource.addFeature(feature);
    }}

    function removeOverlayKinds(kinds) {{
      const toRemove = [];
      overlaySource.getFeatures().forEach(f => {{
        if (kinds.includes(f.get('kind'))) toRemove.push(f);
      }});
      toRemove.forEach(f => overlaySource.removeFeature(f));
    }}

    function setObjects(objects) {{
      removeOverlayKinds(['object', 'orbitTarget', 'orbitSequence', 'orbitPreview']);
      if (!Array.isArray(objects)) return;
      objects.forEach(obj => {{
        if (!obj) return;
        const lat = Number(obj.lat);
        const lon = Number(obj.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        addOverlayPoint([lon, lat], 'object', {{
          object_id: obj.object_id || '',
          object_index: Number(obj.display_index || obj.object_index || 0),
          lat,
          lon,
          selected: obj.selected === true
        }});
      }});
      if (Array.isArray(data.orbit_targets)) {{
        const radiusM = Number(data.orbit_radius_m || 0);
        data.orbit_targets.forEach(coord => {{
          if (!Array.isArray(coord) || coord.length < 2) return;
          addOverlayCircle(coord, radiusM, 'orbitTarget');
        }});
      }}
      if (Array.isArray(data.orbit_sequence) && data.orbit_sequence.length >= 2) {{
        addOverlayLine(data.orbit_sequence, 'orbitSequence');
      }}
      if (Array.isArray(data.orbit_preview_paths)) {{
        data.orbit_preview_paths.forEach(coords => {{
          if (!Array.isArray(coords) || coords.length < 2) return;
          addOverlayLine(coords, 'orbitPreview');
        }});
      }}
    }}


    function lineCoordsFromFeature(feature) {{
      if (!feature) return [];
      const geom = feature.getGeometry();
      if (!geom) return [];
      return geom.getCoordinates().map(c => ol.proj.toLonLat(c));
    }}

    function updateSegmentOverlays(coords, kind) {{
      removeOverlayKinds(['segment', 'segmentLabel']);
      if (!coords || coords.length < 2) return;
      let cumulative = 0;
      for (let i = 0; i < coords.length - 1; i++) {{
        const a = coords[i];
        const b = coords[i + 1];
        const segLen = haversineM(a, b);
        const cumulativeNext = cumulative + segLen;
        const remaining = estimateRemainingPercent(cumulativeNext, b);
        const displayRemaining = remaining === null ? null : clamp(remaining, 0, 100);
        addOverlayLine([a, b], 'segment', {{ remaining: displayRemaining }});
        cumulative = cumulativeNext;
      }}
    }}

    const frameScheduler = window.requestAnimationFrame
      ? window.requestAnimationFrame.bind(window)
      : (cb) => window.setTimeout(cb, 16);
    let segmentOverlayHandle = null;
    let pendingSegmentOverlayCoords = null;

    function scheduleSegmentOverlayUpdate(coords) {{
      pendingSegmentOverlayCoords = Array.isArray(coords) ? coords.slice() : [];
      if (segmentOverlayHandle !== null) {{
        return;
      }}
      segmentOverlayHandle = frameScheduler(() => {{
        segmentOverlayHandle = null;
        const coordsToUpdate = pendingSegmentOverlayCoords;
        pendingSegmentOverlayCoords = null;
        updateSegmentOverlays(coordsToUpdate, pathKind);
      }});
    }}

    function getLineFeature() {{
      return drawSource.getFeatures().find(f => f.getGeometry().getType() === 'LineString');
    }}

    function getPointFeature() {{
      return drawSource.getFeatures().find(f => f.getGeometry().getType() === 'Point');
    }}

    function emitPath(feature) {{
      if (suppressEmit) return;
      const line = feature || getLineFeature();
      if (!line) {{
        console.log('PY_PATH ' + JSON.stringify({{ type: 'LineString', coordinates: [] }}));
        return;
      }}
      const gj = geojson.writeGeometryObject(line.getGeometry(), {{
        featureProjection: 'EPSG:3857',
        dataProjection: 'EPSG:4326'
      }});
      console.log('PY_PATH ' + JSON.stringify(gj));
    }}

    function emitTarget() {{
      if (suppressEmit) return;
      const point = getPointFeature();
      if (!point) {{
        console.log('PY_TARGET ' + JSON.stringify({{ type: 'Point', coordinates: [] }}));
        return;
      }}
      const gj = geojson.writeGeometryObject(point.getGeometry(), {{
        featureProjection: 'EPSG:3857',
        dataProjection: 'EPSG:4326'
      }});
      console.log('PY_TARGET ' + JSON.stringify(gj));
    }}

    setEditableLine(data.path);
    setEditableTarget(data.target);
    if (data.path && data.path.length) {{
      addOverlayPoint(data.path[0], 'start');
      addOverlayPoint(data.path[data.path.length - 1], 'finish');
    }}
    addOverlayLine(data.route_edit_locked, 'lockedPath');
    if (data.route_edit_anchor && data.route_edit_anchor.length >= 2) {{
      addOverlayPoint(data.route_edit_anchor, 'editAnchor');
    }}
    updateSegmentOverlays(data.path, pathKind);
    addOverlayLine(data.path_done, 'pathDone');
    addOverlayLine(data.path_remaining, 'pathRemaining');
    addOverlayLine(data.debug_orbit, 'orbit');
    if (data.home && data.home.length >= 2) {{
      addOverlayPoint(data.home, 'home');
    }}
    if (data.drone && data.drone.length >= 2) {{
      setUavPose({{
        id: data.uav_id || 'uav',
        lat: data.drone[1],
        lon: data.drone[0],
        heading: data.heading
      }}, false);
    }}

    (data.objects || []).forEach(obj => {{
      if (!obj) return;
      const lat = Number(obj.lat);
      const lon = Number(obj.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      addOverlayPoint([lon, lat], 'object', {{
        object_id: obj.object_id || '',
        object_index: Number(obj.display_index || obj.object_index || 0),
        lat,
        lon,
        selected: obj.selected === true
      }});
    }});

    const modify = new ol.interaction.Modify({{ source: drawSource }});
    map.addInteraction(modify);
    modify.setActive(false);
    modify.on('modifystart', () => {{
      const line = getLineFeature();
      watchLine(line);
      updateSegmentOverlays(lineCoordsFromFeature(line), pathKind);
    }});
    modify.on('modifyend', () => {{
      const line = getLineFeature();
      if (line) {{
        const geom = line.getGeometry();
        const coords = lineCoordsFromFeature(line);
        let nextCoords = clampPathToBattery(coords);
        nextCoords = applyRouteEditAnchor(nextCoords);
        if (geom && nextCoords && nextCoords.length >= 2 && JSON.stringify(nextCoords) !== JSON.stringify(coords)) {{
          geom.setCoordinates(nextCoords.map(c => ol.proj.fromLonLat(c)));
        }}
      }}
      emitPath();
      emitTarget();
      unwatchLine();
      updateSegmentOverlays(lineCoordsFromFeature(getLineFeature()));
    }});

    let drawInteraction = null;
    let activeMode = '';
    let liveGeomKey = null;
    let appendMode = false;
    let appendBaseCoords = null;
    let removeMode = false;

    function unwatchLine() {{
      if (liveGeomKey && ol.Observable && typeof ol.Observable.unByKey === 'function') {{
        ol.Observable.unByKey(liveGeomKey);
      }}
      liveGeomKey = null;
    }}

    let isClamping = false;
    let isSnapping = false;
    const homeSnapCoord = Array.isArray(data.home) && data.home.length >= 2 ? data.home : null;
    const routeEditAnchorCoord = Array.isArray(data.route_edit_anchor) && data.route_edit_anchor.length >= 2
      ? data.route_edit_anchor
      : null;
    const homeSnapThresholdM = 100.0;

    function maybeSnapToHome(coords) {{
      if (!homeSnapCoord || !coords || !coords.length) return coords;
      if (appendMode) return coords;
      const first = coords[0];
      if (!first) return coords;
      if (haversineM(first, homeSnapCoord) > homeSnapThresholdM) return coords;
      if (first[0] === homeSnapCoord[0] && first[1] === homeSnapCoord[1]) return coords;
      const snapped = coords.slice();
      snapped[0] = [homeSnapCoord[0], homeSnapCoord[1]];
      return snapped;
    }}

    function applyRouteEditAnchor(coords) {{
      if (!routeEditAnchorCoord || !coords || !coords.length) return coords;
      const snapped = coords.slice();
      snapped[0] = [routeEditAnchorCoord[0], routeEditAnchorCoord[1]];
      if (snapped.length < 2) {{
        snapped.push([routeEditAnchorCoord[0], routeEditAnchorCoord[1]]);
      }}
      return snapped;
    }}

    function watchLine(feature) {{
      unwatchLine();
      if (!feature) return;
      const geom = feature.getGeometry();
      if (!geom) return;
      liveGeomKey = geom.on('change', () => {{
        if (isClamping || isSnapping) return;
        const coords = lineCoordsFromFeature(feature);
        let nextCoords = coords;
        const clamped = clampPathToBattery(coords);
        if (clamped && clamped.length >= 2 && JSON.stringify(clamped) !== JSON.stringify(coords)) {{
          nextCoords = clamped;
        }}
        nextCoords = maybeSnapToHome(nextCoords);
        nextCoords = applyRouteEditAnchor(nextCoords);
        if (JSON.stringify(nextCoords) !== JSON.stringify(coords)) {{
          isSnapping = true;
          geom.setCoordinates(nextCoords.map(c => ol.proj.fromLonLat(c)));
          isSnapping = false;
        }}
        scheduleSegmentOverlayUpdate(nextCoords);
      }});
    }}

    function enableDraw(mode) {{
      if (drawInteraction) {{
        map.removeInteraction(drawInteraction);
        drawInteraction = null;
      }}
      if (!mode) {{
        activeMode = '';
        unwatchLine();
        return;
      }}
      activeMode = mode;
      drawInteraction = new ol.interaction.Draw({{ source: drawSource, type: mode }});
      drawInteraction.on('drawstart', (evt) => {{
        if (mode === 'Point') removeByType('Point');
        if (mode === 'LineString') {{
          appendBaseCoords = null;
          if (appendMode) {{
            const existing = getLineFeature();
            if (existing && existing !== evt.feature) {{
              appendBaseCoords = lineCoordsFromFeature(existing);
            }}
          }}
          watchLine(evt.feature);
          updateSegmentOverlays(lineCoordsFromFeature(evt.feature));
        }}
      }});
    drawInteraction.on('drawend', (evt) => {{
      if (mode === 'LineString' && evt && evt.feature) {{
        const geom = evt.feature.getGeometry();
        let coords = lineCoordsFromFeature(evt.feature);
        if (appendMode && appendBaseCoords && appendBaseCoords.length) {{
          const merged = appendBaseCoords.slice();
          if (coords.length) {{
            const last = merged[merged.length - 1];
            const first = coords[0];
            if (last && first && haversineM(last, first) < 1.0) {{
              coords = coords.slice(1);
            }}
            merged.push(...coords);
          }}
          coords = merged;
        }}
        coords = maybeSnapToHome(coords);
        coords = applyRouteEditAnchor(coords);
        const clamped = clampPathToBattery(coords);
        if (geom && clamped && clamped.length >= 2 && JSON.stringify(clamped) !== JSON.stringify(coords)) {{
          coords = clamped;
        }}
        coords = applyRouteEditAnchor(coords);
        if (geom) {{
          geom.setCoordinates(coords.map(c => ol.proj.fromLonLat(c)));
        }}
      }}
      const keep = evt && evt.feature ? evt.feature : null;
      if (mode === 'LineString') {{
        drawSource.getFeatures().forEach(f => {{
          if (f !== keep && f.getGeometry().getType() === 'LineString') {{
            drawSource.removeFeature(f);
            }}
          }});
        }}
        if (mode === 'Point') {{
          drawSource.getFeatures().forEach(f => {{
            if (f !== keep && f.getGeometry().getType() === 'Point') {{
              drawSource.removeFeature(f);
            }}
          }});
        }}
      unwatchLine();
      appendBaseCoords = null;
      updateSegmentOverlays(lineCoordsFromFeature(getLineFeature()));
      emitPath(keep);
      emitTarget();
    }});
      map.addInteraction(drawInteraction);
    }}

    function closestSegmentIndex(coords, point) {{
      if (!coords || coords.length < 2 || !point) return null;
      const p = ol.proj.fromLonLat(point);
      let bestIdx = null;
      let bestDist = Infinity;
      for (let i = 0; i < coords.length - 1; i++) {{
        const a = ol.proj.fromLonLat(coords[i]);
        const b = ol.proj.fromLonLat(coords[i + 1]);
        const vx = b[0] - a[0];
        const vy = b[1] - a[1];
        const wx = p[0] - a[0];
        const wy = p[1] - a[1];
        const len2 = vx * vx + vy * vy;
        let t = 0.0;
        if (len2 > 0) {{
          t = (wx * vx + wy * vy) / len2;
          t = Math.max(0, Math.min(1, t));
        }}
        const projx = a[0] + t * vx;
        const projy = a[1] + t * vy;
        const dx = p[0] - projx;
        const dy = p[1] - projy;
        const dist = Math.hypot(dx, dy);
        if (dist < bestDist) {{
          bestDist = dist;
          bestIdx = i;
        }}
      }}
      return bestIdx;
    }}

    function closestVertexIndex(coords, pixel) {{
      if (!coords || !coords.length || !pixel) return null;
      let bestIdx = null;
      let bestDist = Infinity;
      for (let i = 0; i < coords.length; i++) {{
        const vertexPixel = map.getPixelFromCoordinate(ol.proj.fromLonLat(coords[i]));
        if (!vertexPixel) continue;
        const dx = pixel[0] - vertexPixel[0];
        const dy = pixel[1] - vertexPixel[1];
        const dist = Math.hypot(dx, dy);
        if (dist < bestDist) {{
          bestDist = dist;
          bestIdx = i;
        }}
      }}
      if (bestDist > 14) return null;
      return bestIdx;
    }}

    function removePointAtPixel(pixel) {{
      const line = getLineFeature();
      if (!line) return;
      let coords = lineCoordsFromFeature(line);
      if (!coords || !coords.length) {{
        removeByType('LineString');
        updateSegmentOverlays([]);
        emitPath();
        return;
      }}
      const idx = closestVertexIndex(coords, pixel);
      if (idx === null) {{
        return;
      }}
      if (routeEditAnchorCoord && idx === 0) {{
        console.log('PY_TOAST ' + JSON.stringify({{ message: 'Cannot remove route start under drone' }}));
        return;
      }}
      coords = coords.slice();
      coords.splice(idx, 1);
      coords = applyRouteEditAnchor(coords);
      if (coords.length < 2) {{
        removeByType('LineString');
        updateSegmentOverlays([]);
        emitPath();
        return;
      }}
      const geom = line.getGeometry();
      if (geom) {{
        geom.setCoordinates(coords.map(c => ol.proj.fromLonLat(c)));
      }}
      updateSegmentOverlays(coords);
      emitPath(line);
    }}

    window.__mapTools = {{
      setUavPose: (pose) => setUavPose(pose),
      zoomIn: () => {{
        const view = map.getView();
        const zoom = view.getZoom();
        if (zoom !== undefined && zoom !== null) {{
          view.animate({{ zoom: zoom + 1, duration: 160 }});
        }} else {{
          const res = view.getResolution();
          if (res) view.setResolution(res / 2);
        }}
      }},
      zoomOut: () => {{
        const view = map.getView();
        const zoom = view.getZoom();
        if (zoom !== undefined && zoom !== null) {{
          view.animate({{ zoom: zoom - 1, duration: 160 }});
        }} else {{
          const res = view.getResolution();
          if (res) view.setResolution(res * 2);
        }}
      }},
      resetView: () => {{
        const view = map.getView();
        view.setCenter(ol.proj.fromLonLat(data.center));
        view.setZoom(13);
      }},
      drawPath: () => {{
        removeMode = false;
        enableDraw('LineString');
      }},
      stopDraw: () => {{
        removeMode = false;
        enableDraw('');
      }},
      setRemoveMode: (flag) => {{
        removeMode = !!flag;
        if (removeMode) {{
          enableDraw('');
        }}
      }},
      setAppendMode: (flag) => {{
        appendMode = !!flag;
        modify.setActive(appendMode);
      }},
      setObjectSpawnMode: (flag) => {{
        spawnMode = !!flag;
      }},
      setObjects: (objects) => {{
        setObjects(objects);
      }},
      setHomeMode: (flag) => {{
        homeMode = !!flag;
      }},
      screenToGeo: (x, y) => (window.screenToGeo ? window.screenToGeo(x, y) : null),
    }};

    map.on('singleclick', evt => {{
      if (drawInteraction) return;
      if (removeMode) {{
        removePointAtPixel(evt.pixel);
        return;
      }}
      if (homeMode) {{
        const lonLat = ol.proj.toLonLat(evt.coordinate);
        const payload = {{
          lat: lonLat[1],
          lon: lonLat[0]
        }};
        console.log('PY_HOME ' + JSON.stringify(payload));
        homeMode = false;
        return;
      }}
      if (spawnMode) {{
        return;
      }}
      map.forEachFeatureAtPixel(evt.pixel, feature => {{
        if (feature.get('kind') === 'object') {{
          const lonLat = ol.proj.toLonLat(feature.getGeometry().getCoordinates());
          const payload = {{
            object_id: feature.get('object_id') || '',
            lat: lonLat[1],
            lon: lonLat[0]
          }};
          console.log('PY_OBJECT ' + JSON.stringify(payload));
          return true;
        }}
        return false;
      }});
    }});

    suppressEmit = false;
    }} catch (err) {{
      console.error('Map init failed', err);
    }}
  }})();
  </script>
</body>
</html>
"""

        self._map_path.write_text(html, encoding="utf-8")
        return self._map_path


class StaticImageMapProvider:
    """Leaflet/Folium provider that renders a single georeferenced image overlay."""

    _BRIDGE_JS = FoliumMapProvider._BRIDGE_JS

    def __init__(self, image_path: str, bounds: MapBounds) -> None:
        self._map_path: Path = Path(tempfile.gettempdir()) / "plan_map.html"
        resolved_path = Path(image_path).expanduser().resolve()
        self.image_path = str(resolved_path)
        self.bounds = bounds
        self._radius_px = 18  # match QML card radius

    @property
    def bridge_script(self) -> str:
        return self._BRIDGE_JS

    def set_provider(self, provider: str, *, offline: bool, cache_dir: Path | None = None) -> None:
        return

    def latlon_to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        lon_min = self.bounds.lon_min
        lat_min = self.bounds.lat_min
        denom_lon = self.bounds.lon_max - lon_min
        denom_lat = self.bounds.lat_max - lat_min
        if denom_lon == 0 or denom_lat == 0:
            return 0.0, 0.0
        x_norm = (lon - lon_min) / denom_lon
        y_norm = (lat - lat_min) / denom_lat
        return (
            min(max(x_norm, 0.0), 1.0),
            min(max(y_norm, 0.0), 1.0),
        )

    def render_map(
        self, path: list[tuple[float, float]], token: int, path_kind: str | None = None
    ) -> Path:
        folium = _get_folium()
        draw_cls = _get_folium_draw()
        lat_min = self.bounds.lat_min
        lon_min = self.bounds.lon_min
        lat_max = self.bounds.lat_max
        lon_max = self.bounds.lon_max
        center = ((lat_min + lat_max) / 2.0, (lon_min + lon_max) / 2.0)
        bounds = [[lat_min, lon_min], [lat_max, lon_max]]
        telemetry = getattr(deps, "latest_telemetry", None)
        mission_state = str(getattr(deps, "mission_state", "") or "")
        drone_pos = None
        if telemetry is not None and hasattr(telemetry, "lat") and hasattr(telemetry, "lon"):
            try:
                drone_pos = (float(telemetry.lat), float(telemetry.lon))
            except Exception:
                drone_pos = None
        if drone_pos is None:
            drone_pos = interpolate_path_point(path, getattr(deps, "debug_flight_progress", 0.0))
        show_drone = mission_state in ("IN_FLIGHT", "RTL")

        fmap = folium.Map(
            center,
            zoom_start=13,
            control_scale=False,
            zoom_control=True,
            prefer_canvas=True,
            tiles=None,
            attributionControl=False,
        )

        fmap.get_root().script.add_child(
            folium.Element(f"window.__map = {fmap.get_name()};")
        )

        image_url = None
        fallback_url = None
        try:
            image_url = Path(self.image_path).resolve().as_uri()
            log.info("Static map overlay using file URI: %s", image_url)
        except Exception as exc:  # noqa: BLE001
            log.warning("Static map image path resolve failed: %s", exc)
        try:
            image_bytes = Path(self.image_path).read_bytes()
            encoded = base64.b64encode(image_bytes).decode("ascii")
            fallback_url = f"data:image/png;base64,{encoded}"
            log.info("Static map overlay data URI prepared (%d bytes)", len(image_bytes))
        except Exception as exc:  # noqa: BLE001
            log.warning("Static map image read failed: %s", exc)
        if image_url is None:
            image_url = fallback_url or self.image_path
        fallback_src = fallback_url or image_url or self.image_path

        overlay = folium.raster_layers.ImageOverlay(
            image=image_url,
            bounds=bounds,
            opacity=1.0,
            name="Static map",
            interactive=False,
            cross_origin=False,
            zindex=1,
        )
        overlay.add_to(fmap)
        if fallback_url:
            fmap.get_root().html.add_child(
                folium.Element(
                    f"<script>window.__staticOverlayFallbackUrl = {json.dumps(fallback_url)};</script>"
                )
            )
        fmap.get_root().script.add_child(
            folium.Element(
                """
(function() {
  if (!window.L) { console.error('Leaflet failed to load'); return; }
  var tries = 0;
  var maxTries = 40;
  function resolveMap() {
    var map = window.__map || Object.values(window).find(function(v) { return v instanceof L.Map; });
    if (!map) {
      tries += 1;
      if (tries >= maxTries) {
        console.error('Map instance not found');
        return;
      }
      setTimeout(resolveMap, 50);
      return;
    }
    map.whenReady(function() {
      var overlays = [];
      for (var key in map._layers) {
        if (!Object.prototype.hasOwnProperty.call(map._layers, key)) continue;
        var layer = map._layers[key];
        if (layer instanceof L.ImageOverlay) overlays.push(layer);
      }
      if (!overlays.length) {
        console.error('Static overlay not found');
        return;
      }
      overlays.forEach(function(overlay) {
        overlay.on('load', function() { console.log('Static overlay loaded'); });
        overlay.on('error', function() {
          console.error('Static overlay failed');
          if (window.__staticOverlayFallbackUrl) {
            overlay.setUrl(window.__staticOverlayFallbackUrl);
          }
        });
      });
    });
  }
  resolveMap();
})();
"""
            )
        )
        fmap.fit_bounds(bounds)

        draw_cls(
            export=False,
            draw_options={
                "polyline": {"shapeOptions": {"color": "#000000"}},
                "polygon": False,
                "rectangle": False,
                "circle": False,
                "circlemarker": False,
                "marker": {"repeatMode": False},
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(fmap)

        if path:
            folium.PolyLine(path, color="#000000", weight=3).add_to(fmap)
            folium.CircleMarker(
                location=path[0],
                radius=7,
                color="#000000",
                fill=True,
                fill_color="#ffffff",
                weight=2,
                tooltip="Start",
            ).add_to(fmap)
            folium.CircleMarker(
                location=path[-1],
                radius=7,
                color="#000000",
                fill=True,
                fill_color="#ffffff",
                weight=2,
                tooltip="Finish",
            ).add_to(fmap)

        if drone_pos and show_drone:
            heading = None
            if telemetry is not None and hasattr(telemetry, "yaw"):
                try:
                    heading = float(telemetry.yaw)
                except Exception:
                    heading = None
            uav_id = None
            source = getattr(telemetry, "source", None) if telemetry is not None else None
            if source:
                uav_id = str(source)
            if not uav_id:
                uav_id = str(getattr(settings, "uav_id", None) or "uav")
            payload = json.dumps(
                {"id": uav_id, "lat": drone_pos[0], "lon": drone_pos[1], "heading": heading}
            )
            fmap.get_root().html.add_child(
                folium.Element(f"<script>window.__initialUavPose = {payload};</script>")
            )

        if _spawn_debug_visuals_enabled() and deps.debug_target:
            lat = deps.debug_target.get("lat")
            lon = deps.debug_target.get("lon")
            if lat is not None and lon is not None:
                folium.CircleMarker(
                    location=(lat, lon),
                    radius=6,
                    color="#000000",
                    fill=True,
                    fill_color="#ffffff",
                    weight=2,
                ).add_to(fmap)

        if _spawn_debug_visuals_enabled() and deps.debug_orbit_path and deps.debug_orbit_path != path:
            folium.PolyLine(
                locations=[(lat, lon) for lat, lon in deps.debug_orbit_path],
                color="orange",
                weight=2,
            ).add_to(fmap)

        fmap.get_root().header.add_child(
            folium.Element(
                f"""
<style>
.folium-map, .leaflet-container {{
    border-radius: {self._radius_px}px !important;
    overflow: hidden !important;
    background: transparent !important;
    background-image: url({json.dumps(fallback_src)});
    background-size: cover !important;
    background-position: center !important;
}}
.leaflet-pane, .leaflet-map-pane {{
    border-radius: {self._radius_px}px !important;
    overflow: hidden !important;
    background: transparent !important;
}}
.leaflet-control-attribution {{
    display: none !important;
}}
html, body {{
    background: transparent !important;
    margin: 0;
}}
</style>
"""
            )
        )

        fmap.save(self._map_path)
        return self._map_path


class UnrealMapProvider(StaticImageMapProvider):
    """Static image provider alias for Unreal-style snapshots."""

    def __init__(self, image_path: str, bounds: MapBounds) -> None:
        super().__init__(image_path=image_path, bounds=bounds)
