from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Final

import folium
from folium.plugins import Draw
from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

import fire_uav.infrastructure.providers as deps
from fire_uav.config import settings
from fire_uav.gui.utils.gui_toast import show_toast
from fire_uav.gui.viewmodels.planner_vm import PlannerVM
from fire_uav.module_core.route.base_location import resolve_base_location
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint

# mypy: disable-error-code=call-arg


_log: Final = logging.getLogger(__name__)


class _Page(QWebEnginePage):
    consoleMessage = Signal(int, str, int, str)  # level, msg, line, source

    def javaScriptConsoleMessage(self, level: int, msg: str, line: int, source: str) -> None:
        """Перехват сообщений из JS-консоли и эмит в Qt."""
        self.consoleMessage.emit(level, msg, line, source)


class PlanWidget(QWidget):
    """Карта с полилинией и трёхкнопочным интерфейсом."""

    def __init__(self, vm: PlannerVM) -> None:
        super().__init__()
        self._vm = vm
        self._tmp_html: Path = Path(tempfile.gettempdir()) / "plan_map.html"

        self.setObjectName("planWidgetRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._btn_gen = QPushButton("Generate Path")
        self._btn_save = QPushButton("Save Plan")
        self._btn_imp = QPushButton("Import GeoJSON")

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 8)
        top.setSpacing(10)
        top.addWidget(self._btn_gen)
        top.addWidget(self._btn_save)
        top.addWidget(self._btn_imp)
        top.addStretch()

        # Map view
        self._view = QWebEngineView()
        self._page = _Page(self._view)
        self._view.setPage(self._page)
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            True,
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self._view)

        # Signals
        self._btn_gen.clicked.connect(self._on_generate)
        self._btn_save.clicked.connect(self._on_save)
        self._btn_imp.clicked.connect(self._on_import)

        self._page.consoleMessage.connect(self._js_bridge)
        self._view.loadFinished.connect(self._after_load)

        self._render_map()

    def _render_map(self) -> None:
        """Создаёт карту с рисованием и сохраняет её во временный HTML."""
        path = self._vm.get_path()
        center = path[0] if path else (56.02, 92.9)

        fmap = folium.Map(
            center,
            zoom_start=13,
            control_scale=False,
            zoom_control=True,
            prefer_canvas=True,
            attributionControl=False,
        )

        Draw(
            export=False,
            draw_options={
                "polyline": {"shapeOptions": {"color": "#000000"}},
                "polygon": False,
                "rectangle": False,
                "circle": False,
                "circlemarker": False,
                "marker": False,
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(fmap)

        if path:
            folium.PolyLine(path, color="#000000", weight=4).add_to(fmap)

        fmap.get_root().header.add_child(
            folium.Element(
                """
<style>
.leaflet-control-attribution { display: none !important; }
.segment-percent-label {
  font: 12px/1.1 "Helvetica Neue", Arial, sans-serif;
  color: #1b1b1b;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(0, 0, 0, 0.15);
  border-radius: 4px;
  padding: 2px 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
  white-space: nowrap;
  pointer-events: none;
}
.segment-percent-icon {
  background: none;
  border: none;
}
.leaflet-editing-icon {
  background: #ffffff;
  border: 2px solid #000000;
  border-radius: 50%;
}
</style>
"""
            )
        )

        fmap.save(self._tmp_html)
        self._view.setUrl(QUrl.fromLocalFile(str(self._tmp_html)))

    def _fallback_base_latlng(self, path: list[tuple[float, float]]) -> list[float] | None:
        route = Route(
            version=1,
            waypoints=[Waypoint(lat=lat, lon=lon, alt=0.0) for lat, lon in path],
            active_index=0 if path else None,
        )
        latest = getattr(deps, "latest_telemetry", None)
        telemetry = None
        if latest is not None and hasattr(latest, "lat") and hasattr(latest, "lon"):
            try:
                telemetry = TelemetrySample(
                    lat=float(latest.lat),
                    lon=float(latest.lon),
                    alt=float(getattr(latest, "alt", 0.0) or 0.0),
                    yaw=float(getattr(latest, "yaw", 0.0) or 0.0),
                    pitch=float(getattr(latest, "pitch", 0.0) or 0.0),
                    roll=float(getattr(latest, "roll", 0.0) or 0.0),
                    battery=float(getattr(latest, "battery", 1.0) or 1.0),
                    battery_percent=getattr(latest, "battery_percent", None),
                )
            except Exception:
                telemetry = None
        resolved = resolve_base_location(settings, route, telemetry)
        if resolved is None:
            return None
        return [float(resolved.lat), float(resolved.lon)]

    def _route_stats_payload(self, path: list[tuple[float, float]]) -> dict:
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
            latest = getattr(deps, "latest_telemetry", None)
            if latest is not None and getattr(latest, "battery_percent", None) is not None:
                try:
                    available_percent = float(latest.battery_percent)
                except (TypeError, ValueError):
                    pass

        base_latlng = None
        base = stats.get("base")
        if isinstance(base, (list, tuple)) and len(base) >= 2:
            try:
                base_latlng = [float(base[1]), float(base[0])]
            except (TypeError, ValueError):
                base_latlng = None
        if base_latlng is None:
            base_latlng = self._fallback_base_latlng(path)

        return {
            "max_distance_m": max_distance_m,
            "reserved_percent": reserved_percent,
            "available_percent": available_percent,
            "base_latlng": base_latlng,
        }

    @Slot(int, str, int, str)
    def _js_bridge(self, level: int, message: str, line: int, source: str) -> None:
        """
        JS → Python bridge: ловим сообщения 'PY_PATH ' + GeoJSON
        и сохраняем план.
        """
        if message.startswith("PY_PATH "):
            gj = json.loads(message.split(" ", 1)[1])
            pts = [(lat, lon) for lon, lat in gj["coordinates"]]
            if pts:
                self._vm.save_plan(pts)
            else:
                self._vm.clear_plan()
            self._render_map()

    def _after_load(self, ok: bool) -> None:
        """После загрузки HTML устанавливаем JS-обработчики."""
        if not ok:
            _log.error("Map load failed")
            return

        stats = self._route_stats_payload(self._vm.get_path())
        stats_json = json.dumps(stats, ensure_ascii=True)
        js = """\
(() => {
  if (!window.L) { console.error('Leaflet failed to load'); return; }
  const map = Object.values(window).find(v => v instanceof L.Map);
  if (!map) { console.error('Map instance not found'); return; }

  const routeStats = __ROUTE_STATS__;
  const maxDistanceM = typeof routeStats.max_distance_m === 'number' ? routeStats.max_distance_m : 0;
  const availablePercent = typeof routeStats.available_percent === 'number' ? routeStats.available_percent : 100;

  function send(gj) { console.log('PY_PATH ' + JSON.stringify(gj)); }

  const labelLayer = L.layerGroup().addTo(map);
  let activeDraw = null;

  function toRad(deg) { return deg * Math.PI / 180; }
  function bearingDeg(a, b) {
      const lat1 = toRad(a.lat);
      const lat2 = toRad(b.lat);
      const dLon = toRad(b.lng - a.lng);
      const y = Math.sin(dLon) * Math.cos(lat2);
      const x = Math.cos(lat1) * Math.sin(lat2) -
          Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
      let brng = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
      if (brng > 90 && brng < 270) brng -= 180;
      return brng;
  }

  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }

  function estimateRemainingPercent(routeMeters) {
      if (!maxDistanceM || maxDistanceM <= 0) return null;
      const required = (routeMeters / maxDistanceM) * 100.0;
      return availablePercent - required;
  }

  function updateLabels(latlngs) {
      labelLayer.clearLayers();
      if (!latlngs || latlngs.length < 2) return;
      let cumulative = 0;
      const segs = [];
      for (let i = 1; i < latlngs.length; i++) {
          const a = latlngs[i - 1];
          const b = latlngs[i];
          const len = map.distance(a, b);
          segs.push({a, b, len});
          cumulative += len;
      }
      if (!cumulative) return;
      let walked = 0;
      segs.forEach(seg => {
          walked += seg.len;
          const mid = L.latLng((seg.a.lat + seg.b.lat) / 2, (seg.a.lng + seg.b.lng) / 2);
          const angle = bearingDeg(seg.a, seg.b);
          const remaining = estimateRemainingPercent(walked);
          const displayRemaining = remaining === null ? null : clamp(remaining, 0, 100);
          if (displayRemaining === null) return;
          const html = `<div class="segment-percent-label" ` +
              `style="transform: translate(-50%, -50%) rotate(${angle}deg) translate(0, 24px);">` +
              `${displayRemaining.toFixed(1)}%</div>`;
          const icon = L.divIcon({className: 'segment-percent-icon', html: html, iconSize: [0, 0]});
          L.marker(mid, {icon}).addTo(labelLayer);
      });
  }

  map.on(L.Draw.Event.CREATED, e => {
      if (e.layerType === 'polyline') {
          updateLabels(e.layer.getLatLngs());
          send(e.layer.toGeoJSON().geometry);
      }
  });

  map.on(L.Draw.Event.EDITED, e => {
      e.layers.eachLayer(l => {
          if (l instanceof L.Polyline) {
              updateLabels(l.getLatLngs());
              send(l.toGeoJSON().geometry);
          }
      });
  });

  map.on(L.Draw.Event.EDITVERTEX, e => {
      if (e && e.layers) {
          e.layers.eachLayer(l => {
              if (l instanceof L.Polyline)
                  updateLabels(l.getLatLngs());
          });
          return;
      }
      map.eachLayer(l => {
          if (l instanceof L.Polyline && !(l instanceof L.Polygon))
              updateLabels(l.getLatLngs());
      });
  });

  map.on(L.Draw.Event.DRAWSTART, e => {
      if (e.layerType !== 'polyline') return;
      labelLayer.clearLayers();
      const toolbar = map._drawControl && map._drawControl._toolbars && map._drawControl._toolbars.draw;
      if (toolbar && toolbar._modes && toolbar._modes.polyline)
          activeDraw = toolbar._modes.polyline.handler;
  });

  map.on(L.Draw.Event.DRAWVERTEX, () => {
      if (!activeDraw || !activeDraw._poly) return;
      updateLabels(activeDraw._poly.getLatLngs());
  });

  map.on(L.Draw.Event.DRAWSTOP, () => {
      activeDraw = null;
  });

  map.on(L.Draw.Event.DELETED, () => {
      labelLayer.clearLayers();
      send({type:'LineString', coordinates:[]});
  });

  map.eachLayer(l => {
      if (l instanceof L.Polyline && !(l instanceof L.Polygon)) {
          updateLabels(l.getLatLngs());
      }
  });

  const attr = document.querySelector('.leaflet-control-attribution');
  if (map.attributionControl) map.attributionControl.remove();
  if (attr) attr.remove();
})();"""
        js = js.replace("__ROUTE_STATS__", stats_json)
        self._view.page().runJavaScript(js)

    def _on_generate(self) -> None:
        """Генерация пути по current polygon."""
        try:
            fn = self._vm.generate_path()
            rel = fn
            try:
                rel = fn.relative_to(fn.parents[1])
            except Exception:
                pass
            show_toast(self, f"Path saved -> {rel}")
        except Exception as exc:
            show_toast(self, str(exc))

    def _on_save(self) -> None:
        """Экспорт плана в формат QGC и сохранение файла."""
        try:
            fn = self._vm.export_qgc_plan(alt_m=120.0)
            show_toast(self, f"Mission saved → {fn.relative_to(fn.parents[1])}")
        except Exception as exc:
            show_toast(self, str(exc))

    def _on_import(self) -> None:
        """Импорт GeoJSON and re-render."""
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Import GeoJSON",
            filter="GeoJSON (*.geojson *.json)",
        )
        if not fn:
            return
        try:
            self._vm.import_geojson(Path(fn))
            self._render_map()
            show_toast(self, "Polyline imported")
        except Exception as exc:
            show_toast(self, f"Error: {exc}")
