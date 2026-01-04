# mypy: ignore-errors
from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path
from datetime import datetime
from typing import Callable, Final

import cv2
import httpx
import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider

import fire_uav.infrastructure.providers as deps
from fire_uav.config import settings
from fire_uav.core.protocol import MapBounds
from fire_uav.gui.map_providers import (
    FoliumMapProvider,
    MapProvider,
    OpenLayersMapProvider,
    StaticImageMapProvider,
)
from fire_uav.gui.viewmodels.detector_vm import DetectorVM
from fire_uav.gui.viewmodels.planner_vm import PlannerVM
from fire_uav.module_core.factories import get_energy_model
from fire_uav.module_core.geometry import haversine_m
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint, WorldCoord
from fire_uav.services.components.camera import CameraThread
from fire_uav.services.bus import Event, bus
from fire_uav.services.debug_sim import DebugSimulationService
from fire_uav.services.flight_recorder import FlightRecorder, FlightSummary
from fire_uav.services.mission import CameraMonitor, CameraStatus, LinkMonitor, LinkStatus, MissionState, MissionStateMachine
from fire_uav.services.mission.action_policy import MissionActionPolicy
from fire_uav.services.mission.active_path import ActivePathController, ActivePathMode
from fire_uav.services.notifications import ToastDeduplicator
from fire_uav.services.objects_store import ConfirmedObject, ConfirmedObjectsStore
from fire_uav.services.ui_throttle import TelemetryStore

_log: Final = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#                            Video helpers
# --------------------------------------------------------------------------- #
class VideoFrameProvider(QQuickImageProvider):
    """Simple QML image provider that keeps last rendered frame."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._image = QImage()

    def requestImage(self, _id, size, requestedSize):  # type: ignore[override]
        if not self._image.isNull():
            if size is not None:
                size.setWidth(self._image.width())
                size.setHeight(self._image.height())
            return self._image

        # fallback placeholder to avoid QML warnings
        placeholder = QImage(
            requestedSize.width() if requestedSize else 1280,
            requestedSize.height() if requestedSize else 720,
            QImage.Format.Format_ARGB32,
        )
        placeholder.fill(QColor("#0a111b"))
        return placeholder

    def set_image(self, image: QImage) -> None:
        self._image = image


class VideoBridge(QObject):
    """Stores last frame + bboxes and notifies QML to refresh the Image."""

    frameReady = Signal(str)

    def __init__(self, provider: VideoFrameProvider) -> None:
        super().__init__()
        self._provider = provider
        self._last_frame: NDArray[np.uint8] | None = None
        self._bboxes: list[tuple[int, int, int, int]] = []
        self._counter = 0

    @Slot(object)
    def set_bboxes(self, boxes: list[tuple[int, int, int, int]] | None) -> None:
        self._bboxes = boxes or []
        self._render()

    def update_frame(self, frame: NDArray[np.uint8]) -> None:
        self._last_frame = frame
        self._render()

    # ---------- internal ---------- #
    def _render(self) -> None:
        if self._last_frame is None:
            return

        h, w, _ = self._last_frame.shape
        img = QImage(self._last_frame.data, w, h, 3 * w, QImage.Format.Format_BGR888).copy()

        if self._bboxes:
            painter = QPainter(img)
            pen = QPen(QColor("#70e0ff"), 2)
            painter.setPen(pen)
            for x1, y1, x2, y2 in self._bboxes:
                painter.drawRect(x1, y1, x2 - x1, y2 - y1)
            painter.end()

        self._provider.set_image(img)
        self._counter += 1
        self.frameReady.emit(f"image://video/live?{self._counter}")


# --------------------------------------------------------------------------- #
#                             UAV state
# --------------------------------------------------------------------------- #
class UavState(QObject):
    """Persistent QObject per UAV to avoid rebuilding UI models."""

    positionChanged = Signal()
    headingChanged = Signal()
    batteryChanged = Signal()

    def __init__(self, uav_id: str) -> None:
        super().__init__()
        self._uav_id = uav_id
        self._lat = 0.0
        self._lon = 0.0
        self._heading = 0.0
        self._battery_percent = -1.0

    @Property(str, constant=True)
    def uavId(self) -> str:
        return self._uav_id

    @Property(float, notify=positionChanged)
    def lat(self) -> float:
        return self._lat

    @Property(float, notify=positionChanged)
    def lon(self) -> float:
        return self._lon

    @Property(float, notify=headingChanged)
    def heading(self) -> float:
        return self._heading

    @Property(float, notify=batteryChanged)
    def batteryPercent(self) -> float:
        return self._battery_percent

    def update_from_sample(self, sample: TelemetrySample) -> None:
        lat = float(sample.lat)
        lon = float(sample.lon)
        heading = float(getattr(sample, "yaw", 0.0) or 0.0)
        battery = getattr(sample, "battery_percent", None)
        battery_percent = float(battery) if battery is not None else -1.0
        if lat != self._lat or lon != self._lon:
            self._lat = lat
            self._lon = lon
            self.positionChanged.emit()
        if heading != self._heading:
            self._heading = heading
            self.headingChanged.emit()
        if battery_percent != self._battery_percent:
            self._battery_percent = battery_percent
            self.batteryChanged.emit()


# --------------------------------------------------------------------------- #
#                             Logging bridge
# --------------------------------------------------------------------------- #
class QmlLogHandler(logging.Handler, QObject):
    message = Signal(str)

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            self.message.emit(self.format(record))
        except Exception:  # noqa: BLE001
            pass


class MapBridge(QObject):
    """Generates Folium map with draw controls and bridges JS→Python via console logs."""

    urlChanged = Signal(QUrl)
    toastRequested = Signal(str)
    planChanged = Signal(list)
    objectSelected = Signal(str, float, float)

    def __init__(self, vm: PlannerVM, provider: MapProvider | None = None) -> None:
        super().__init__()
        self._vm = vm
        cache_dir = Path(__file__).resolve().parents[2] / "data" / "cache" / "tiles"
        self._default_cache_dir = cache_dir
        self._provider: MapProvider = provider or self._select_provider()
        self._map_path: Path = Path(tempfile.gettempdir()) / "plan_map.html"
        self._token = 0
        self._last_render_progress: float | None = None
        self._last_telemetry_pos: tuple[float, float] | None = None
        self._last_render_ts: float | None = None
        self.render_map()

    # ----- properties exposed to QML ----- #
    @Property(QUrl, notify=urlChanged)
    def url(self) -> QUrl:
        url = QUrl.fromLocalFile(str(self._map_path))
        url.setQuery(f"v={self._token}")
        return url

    @Property(str, constant=True)
    def bridgeScript(self) -> str:
        return getattr(self._provider, "bridge_script", "")

    # ----- slots for QML ----- #
    @Slot()
    def render_map(self) -> None:
        path = self._vm.get_active_path()
        self._map_path = self._provider.render_map(path, self._token)
        self._token += 1
        self._last_render_ts = time.monotonic()
        try:
            self._last_render_progress = float(getattr(deps, "debug_flight_progress", 0.0))
        except Exception:
            self._last_render_progress = 0.0
        try:
            tel = getattr(deps, "latest_telemetry", None)
            if tel is not None and hasattr(tel, "lat") and hasattr(tel, "lon"):
                self._last_telemetry_pos = (float(tel.lat), float(tel.lon))
        except Exception:
            self._last_telemetry_pos = None
        self.urlChanged.emit(self.url)

    @Slot(str)
    def handle_console(self, message: str) -> None:
        if message.startswith("PY_TOAST "):
            try:
                payload = json.loads(message.split(" ", 1)[1])
            except Exception:
                return
            msg = str(payload.get("message", "") or "")
            if msg:
                self.toastRequested.emit(msg)
            return
        if message.startswith("PY_PATH "):
            gj = json.loads(message.split(" ", 1)[1])
            pts = [(lat, lon) for lon, lat in gj.get("coordinates", [])]
            if pts:
                self._vm.save_plan(pts)
            else:
                self._vm.clear_plan()
            deps.debug_target = None
            deps.debug_orbit_path = None
            self._after_path_changed()
            self.toastRequested.emit("Path updated" if pts else "Path cleared")
            return

        if message.startswith("PY_TARGET "):
            gj = json.loads(message.split(" ", 1)[1])
            coords = gj.get("coordinates") or []
            if len(coords) == 2:
                try:
                    lon, lat = coords
                    self._vm.set_debug_target(lat, lon)
                    self._vm.compute_orbit_preview()
                    self.render_map()
                    self.toastRequested.emit("Debug target set, orbit preview updated")
                except Exception as exc:  # noqa: BLE001
                    self.toastRequested.emit(f"Orbit preview error: {exc}")
            else:
                self._vm.clear_debug_target()
                self.render_map()
                self.toastRequested.emit("Debug target cleared")
            return

        if message.startswith("PY_OBJECT "):
            try:
                payload = json.loads(message.split(" ", 1)[1])
            except Exception:
                return
            object_id = str(payload.get("object_id", ""))
            lat = payload.get("lat")
            lon = payload.get("lon")
            if object_id and lat is not None and lon is not None:
                self.objectSelected.emit(object_id, float(lat), float(lon))
            return

    @Slot()
    def generate_path(self) -> None:
        try:
            fn = self._vm.generate_path()
            rel = fn
            try:
                rel = fn.relative_to(fn.parents[1])
            except Exception:
                pass
            self.toastRequested.emit(f"Path saved -> {rel}")
        except Exception as exc:  # noqa: BLE001
            self.toastRequested.emit(str(exc))

    @Slot()
    def save_plan(self) -> None:
        try:
            fn = self._vm.export_qgc_plan(alt_m=120.0)
            self.toastRequested.emit(f"Mission saved → {fn.relative_to(fn.parents[1])}")
        except Exception as exc:  # noqa: BLE001
            self.toastRequested.emit(str(exc))

    @Slot(str)
    def import_geojson(self, fn: str) -> None:
        if not fn:
            return
        try:
            self._vm.import_geojson(Path(fn))
            self._after_path_changed()
            self.toastRequested.emit("Polyline imported")
        except Exception as exc:  # noqa: BLE001
            self.toastRequested.emit(f"Error: {exc}")

    @Slot(str)
    def import_kml(self, fn: str) -> None:
        if not fn:
            return
        try:
            pts = self._parse_kml(Path(fn))
            self._vm.save_plan(pts)
            self._after_path_changed()
            self.toastRequested.emit("KML imported")
        except Exception as exc:  # noqa: BLE001
            self.toastRequested.emit(f"Error: {exc}")

    @Slot(str, bool, str)
    def set_provider(self, provider: str, offline: bool, cache_dir: str = "") -> None:
        provider = (provider or "osm").lower()
        cd = Path(cache_dir) if cache_dir else self._default_cache_dir
        if provider == "static_image":
            static_provider = self._build_static_provider()
            if static_provider:
                self._provider = static_provider
                self.render_map()
            else:
                _log.warning("Static image provider unavailable; keeping current map provider")
            return
        if provider.startswith("openlayers") or provider.startswith("ol_"):
            if isinstance(self._provider, OpenLayersMapProvider):
                self._provider.set_provider(provider, offline=offline, cache_dir=cd)
            else:
                self._provider = OpenLayersMapProvider(provider=provider)
            self.render_map()
            return
        if isinstance(self._provider, StaticImageMapProvider):
            self._provider = FoliumMapProvider(provider=provider, offline=offline, cache_dir=cd)
            self.render_map()
            return
        if isinstance(self._provider, OpenLayersMapProvider):
            self._provider = FoliumMapProvider(provider=provider, offline=offline, cache_dir=cd)
            self.render_map()
            return
        self._provider.set_provider(provider, offline=offline, cache_dir=cd)
        self.render_map()

    @Slot()
    def recomputeOrbitPreview(self) -> None:
        """Rebuild orbit preview around current debug target and refresh the map."""
        if deps.debug_target is None:
            self.toastRequested.emit("Set a debug target marker first")
            return
        if not self._vm.get_path():
            self.toastRequested.emit("Draw a main route first")
            return
        try:
            self._vm.compute_orbit_preview()
            self.render_map()
            if deps.debug_orbit_path:
                self.toastRequested.emit("Orbit preview recomputed")
            else:
                self.toastRequested.emit("Orbit preview unavailable (energy/route?)")
        except Exception as exc:  # noqa: BLE001
            self.toastRequested.emit(f"Orbit preview error: {exc}")

    @Slot()
    def clearDebugTarget(self) -> None:
        """Clear debug target marker and orbit overlay."""
        self._vm.clear_debug_target()
        self.render_map()
        self.toastRequested.emit("Debug target cleared")

    @Slot()
    def refresh_drone(self) -> None:
        """Rerender map if drone progress changed enough to matter."""
        if getattr(deps, "debug_map_manual_refresh", False):
            return
        if getattr(deps, "debug_flight_enabled", False):
            now = time.monotonic()
            if self._last_render_ts is not None and (now - self._last_render_ts) < 2.5:
                return
        tel = getattr(deps, "latest_telemetry", None)
        if tel is not None and hasattr(tel, "lat") and hasattr(tel, "lon"):
            try:
                pos = (float(tel.lat), float(tel.lon))
            except Exception:
                pos = None
            if pos is not None:
                if self._last_telemetry_pos is None or haversine_m(pos, self._last_telemetry_pos) >= 5.0:
                    self.render_map()
                return
        try:
            prog = float(getattr(deps, "debug_flight_progress", 0.0))
        except Exception:
            prog = 0.0
        if self._last_render_progress is None or abs(prog - self._last_render_progress) >= 0.02:
            self.render_map()

    # ----- helpers ----- #
    def _parse_kml(self, fn: Path) -> list[tuple[float, float]]:
        text = fn.read_text(encoding="utf-8", errors="ignore")
        if "<coordinates" not in text:
            raise RuntimeError("Coordinates not found in KML")
        coords_block = (
            text.split("<coordinates", 1)[1].split(">", 1)[1].split("</coordinates>", 1)[0]
        )
        pts: list[tuple[float, float]] = []
        for raw in coords_block.strip().replace("\n", " ").split():
            parts = raw.split(",")
            if len(parts) < 2:
                continue
            lon, lat = float(parts[0]), float(parts[1])
            pts.append((lat, lon))
        if not pts:
            raise RuntimeError("No valid points in KML")
        return pts

    def _after_path_changed(self) -> None:
        """Reset sim position and rebuild orbit preview if needed after path edits."""
        deps.debug_flight_progress = 0.0
        if deps.debug_target:
            try:
                self._vm.compute_orbit_preview()
            except Exception:
                pass
        self.render_map()
        self.planChanged.emit(self._vm.get_path())

    def _select_provider(self) -> MapProvider:
        provider = str(getattr(settings, "map_provider", "osm") or "osm").lower()
        if provider == "static_image":
            static_provider = self._build_static_provider()
            if static_provider:
                return static_provider
            _log.warning("Static image provider requested but unavailable; falling back to OSM")
        if provider.startswith("openlayers") or provider.startswith("ol_"):
            return OpenLayersMapProvider(provider=provider)
        return FoliumMapProvider(cache_dir=self._default_cache_dir)

    def _fetch_snapshot_info(self) -> tuple[str, MapBounds] | None:
        base_url = str(getattr(settings, "visualizer_url", "http://127.0.0.1:8000")).rstrip("/")
        uav_id = getattr(settings, "uav_id", None) or "uav"
        url = f"{base_url}/api/v1/map_snapshot/{uav_id}"
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 404:
                _log.warning("Map snapshot not found for UAV %s at %s", uav_id, url)
                return None
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            _log.warning("Failed to fetch map snapshot from %s: %s", url, exc)
            return None
        image_path = payload.get("image_path")
        bounds_raw = payload.get("bounds")
        if not image_path or not bounds_raw:
            _log.warning("Map snapshot payload missing image_path or bounds")
            return None
        try:
            bounds = bounds_raw if isinstance(bounds_raw, MapBounds) else MapBounds(**bounds_raw)
        except Exception:  # noqa: BLE001
            _log.warning("Map snapshot bounds invalid")
            return None
        return str(image_path), bounds

    def _build_static_provider(self) -> StaticImageMapProvider | None:
        image_path = getattr(settings, "static_map_image_path", None)
        bounds = getattr(settings, "static_map_bounds", None)
        if not image_path or not bounds:
            fetched = self._fetch_snapshot_info()
            if fetched:
                image_path, bounds = fetched
            else:
                _log.warning("Static map config missing image_path or bounds")
                return None
        if isinstance(bounds, dict):
            try:
                bounds = MapBounds(**bounds)
            except Exception:
                _log.warning("Static map bounds invalid")
                return None
        if not isinstance(bounds, MapBounds):
            _log.warning("Static map bounds invalid")
            return None
        if bounds.lat_min >= bounds.lat_max or bounds.lon_min >= bounds.lon_max:
            _log.warning("Static map bounds invalid: min must be < max")
            return None
        image_path = Path(str(image_path)).expanduser()
        if not image_path.exists():
            _log.warning("Static map image not found at %s", image_path)
            return None
        return StaticImageMapProvider(image_path=str(image_path), bounds=bounds)


# --------------------------------------------------------------------------- #
#                             App controller (QML-facing)
# --------------------------------------------------------------------------- #
class AppController(QObject):
    toastRequested = Signal(str)
    objectNotificationReceived = Signal(str, int, float, str, object)
    frameReady = Signal(str)
    mapUrlChanged = Signal(QUrl)
    logsChanged = Signal()
    confidenceChanged = Signal()
    detectorRunningChanged = Signal()
    cameraAvailableChanged = Signal()
    statsChanged = Signal()
    debugModeChanged = Signal()
    simCameraEnabledChanged = Signal()
    bridgeModeChanged = Signal()
    bridgeBatteryProfileChanged = Signal()
    unsafeStartChanged = Signal()
    routeBatteryChanged = Signal()
    confirmedObjectsChanged = Signal()
    missionStateChanged = Signal()
    planConfirmedChanged = Signal()
    linkStatusChanged = Signal()
    cameraStatusChanged = Signal()
    flightControlsChanged = Signal()
    flightSummaryChanged = Signal()
    mapUavPoseUpdated = Signal(str, float, float, float)
    uavStatesChanged = Signal()

    def __init__(
        self,
        det_vm: DetectorVM,
        map_bridge: MapBridge,
        video_bridge: VideoBridge,
        camera_available: bool,
        camera_switcher: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.det_vm = det_vm
        self.map_bridge = map_bridge
        self.video_bridge = video_bridge
        self._camera_switcher = camera_switcher

        self._logs: list[str] = []
        self._confidence = getattr(settings, "yolo_conf", 0.25)
        self._detector_running = False
        self._camera_available = camera_available
        self._fps = 0.0
        self._latency_ms = 0.0
        self._bus_alive = False
        self._detection_conf = 0.0
        self._last_frame_ts: float | None = None
        self._last_detection_ts: float | None = None
        self._ground_station_enabled = bool(getattr(settings, "ground_station_enabled", False))
        self._det_json_path = Path(getattr(settings, "output_root", Path("data/outputs"))) / (
            "detections.jsonl"
        )
        self._log_history_path = (
            Path(__file__).resolve().parents[3] / "data" / "artifacts" / "logs" / "fire_uav_debug.log"
        )
        self._plan_vm = map_bridge._vm  # internal access for debug helpers
        self._tile_cache_dir = Path(__file__).resolve().parents[2] / "data" / "cache" / "tiles"
        self._link_monitor = LinkMonitor()
        self._camera_monitor = CameraMonitor()
        self._mission = MissionStateMachine(
            link_monitor=self._link_monitor,
            camera_monitor=self._camera_monitor,
        )
        self._link_status = LinkStatus.DISCONNECTED
        self._camera_status = CameraStatus.NOT_READY
        self._mission_state = self._mission.current_state
        self._allow_unsafe_start = False
        self._mission.set_allow_unsafe_start(self._allow_unsafe_start)
        self._commands_enabled = True
        self._capabilities = {
            "supports_waypoints": True,
            "supports_rtl": True,
            "supports_orbit": True,
            "supports_set_speed": True,
            "supports_camera": True,
        }
        self._route_edit_mode = False
        self._staged_plan: list[tuple[float, float]] | None = None
        self._latest_telemetry: TelemetrySample | None = None
        self._uav_states: dict[str, UavState] = {}
        self._telemetry_store = TelemetryStore()
        self._last_sent_pose: dict[str, tuple[float, float, float]] = {}
        self._map_update_timer = QTimer(self)
        self._map_update_timer.setInterval(250)
        self._map_update_timer.timeout.connect(self._emit_map_updates)
        self._map_update_timer.start()
        self._active_path = ActivePathController(
            confirmed_path_provider=self.get_confirmed_path,
            draft_path_provider=self._plan_vm.get_path,
            mission_state_provider=lambda: self._mission_state,
            plan_confirmed_provider=lambda: self._mission.plan_confirmed,
            on_change=self._on_active_path_changed,
        )
        self._energy_model = get_energy_model(settings)
        self._toast_dedupe = ToastDeduplicator()
        self._flight_recorder = FlightRecorder()
        self._objects_store = ConfirmedObjectsStore(on_change=self._on_objects_changed)
        self._debug_sim: DebugSimulationService | None = None
        self._rtl_forced = False
        self._rtl_route_sent = False
        self._flight_summary: FlightSummary | None = None
        self._bridge_mode_enabled = False
        self._bridge_profiles = self._load_bridge_profiles()
        self._bridge_profile_id = next(iter(self._bridge_profiles.keys()), "default")
        self._bridge_battery_wh = float(
            self._bridge_profiles.get(self._bridge_profile_id, {}).get("battery_wh", 4500.0)
        )
        self._bridge_speed_mps = float(
            self._bridge_profiles.get(self._bridge_profile_id, {}).get("speed_mps", 8.0)
        )
        self._route_battery_text = "Route: --"
        self._route_battery_remaining_text = "Remaining: --"
        self._route_battery_warning = False
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(500)
        self._status_timer.timeout.connect(self._on_status_tick)
        self._status_timer.start()

        # wire signals
        self.det_vm.detection.connect(self._on_detections)
        self.det_vm.bboxes.connect(self.video_bridge.set_bboxes)
        self.video_bridge.frameReady.connect(self.frameReady)
        self.map_bridge.urlChanged.connect(self.mapUrlChanged)
        self.map_bridge.toastRequested.connect(self.toastRequested)
        self.map_bridge.planChanged.connect(self._on_plan_changed)
        self.map_bridge.objectSelected.connect(self._on_object_selected)

        # logging to QML
        self._log_handler = QmlLogHandler()
        self._log_handler.setLevel(logging.DEBUG)
        self._log_handler.message.connect(self._append_log)
        root = logging.getLogger()
        root.addHandler(self._log_handler)
        self._load_log_history()
        bus.subscribe(Event.OBJECT_CONFIRMED_UI, self._on_object_confirmed)
        bus.subscribe(Event.MISSION_STATE_CHANGED, self._on_mission_state)
        bus.subscribe(Event.UAV_LINK_STATUS_CHANGED, self._on_link_status)
        bus.subscribe(Event.CAMERA_STATUS_CHANGED, self._on_camera_status)
        bus.subscribe(Event.CAPABILITIES_UPDATED, self._on_capabilities_updated)
        bus.subscribe(Event.WARNING_TOAST, self._on_warning_toast)
        bus.subscribe(Event.FLIGHT_SESSION_ENDED, self._on_flight_session_ended)
        self._update_route_estimate(self._active_path.get_active_path())
        self.map_bridge.render_map()

    # ---------- properties ---------- #
    @Property("QStringList", notify=logsChanged)
    def logs(self) -> list[str]:
        return self._logs

    @Property(float, notify=confidenceChanged)
    def confidence(self) -> float:
        return self._confidence

    @Property(bool, notify=detectorRunningChanged)
    def detectorRunning(self) -> bool:
        return self._detector_running

    @Property(bool, notify=cameraAvailableChanged)
    def cameraAvailable(self) -> bool:
        return self._camera_available

    @Property(str, notify=missionStateChanged)
    def missionState(self) -> str:
        return self._mission_state.value

    @Property(bool, notify=planConfirmedChanged)
    def planConfirmed(self) -> bool:
        return self._mission.plan_confirmed

    @Property(str, notify=linkStatusChanged)
    def linkStatus(self) -> str:
        return self._link_status.value

    @Property(str, notify=cameraStatusChanged)
    def cameraStatus(self) -> str:
        return self._camera_status.value

    @Property(bool, notify=flightControlsChanged)
    def linkOk(self) -> bool:
        return self._link_monitor.is_link_ok()

    @Property(bool, notify=flightControlsChanged)
    def cameraOk(self) -> bool:
        return self._camera_monitor.is_camera_ok()

    @Property(bool, notify=flightControlsChanged)
    def startFlightEnabled(self) -> bool:
        return self._current_action_policy().can_start_flight

    @Property(bool, notify=flightControlsChanged)
    def canConfirmPlan(self) -> bool:
        return self._current_action_policy().can_confirm_plan

    @Property(bool, notify=flightControlsChanged)
    def canStartFlight(self) -> bool:
        return self._current_action_policy().can_start_flight

    @Property(bool, notify=flightControlsChanged)
    def canEditRoute(self) -> bool:
        return self._current_action_policy().can_edit_route

    @Property(bool, notify=flightControlsChanged)
    def canApplyRouteEdits(self) -> bool:
        return self._current_action_policy().can_apply_route_edits

    @Property(bool, notify=flightControlsChanged)
    def canOrbit(self) -> bool:
        return self._current_action_policy().can_orbit

    @Property(bool, notify=flightControlsChanged)
    def canRtl(self) -> bool:
        return self._current_action_policy().can_rtl

    @Property(bool, notify=flightControlsChanged)
    def canSendRtlRoute(self) -> bool:
        return self._current_action_policy().can_send_rtl_route

    @Property(bool, notify=flightControlsChanged)
    def canCompleteLanding(self) -> bool:
        return self._current_action_policy().can_complete_landing

    @Property(bool, notify=flightControlsChanged)
    def canAbortToPreflight(self) -> bool:
        return self._current_action_policy().can_abort_to_preflight

    @Property(bool, notify=flightControlsChanged)
    def flightCommandsEnabled(self) -> bool:
        return self._commands_enabled

    @Property(bool, notify=flightControlsChanged)
    def routeEditMode(self) -> bool:
        return self._route_edit_mode

    @Property(int, notify=flightControlsChanged)
    def confirmedObjectCount(self) -> int:
        return self._objects_store.count()

    @Property(bool, notify=flightControlsChanged)
    def orbitAvailable(self) -> bool:
        return self._current_action_policy().can_orbit

    @Property("QVariantList", notify=confirmedObjectsChanged)
    def confirmedObjects(self) -> list[dict[str, object]]:
        return [
            {
                "object_id": obj.object_id,
                "class_id": obj.class_id,
                "confidence": obj.confidence,
                "lat": obj.lat,
                "lon": obj.lon,
                "track_id": obj.track_id,
            }
            for obj in self._objects_store.all()
        ]

    @Property("QVariantList", notify=uavStatesChanged)
    def uavStates(self) -> list[UavState]:
        return list(self._uav_states.values())

    @Property(str, notify=flightSummaryChanged)
    def flightSummaryDuration(self) -> str:
        if not self._flight_summary or self._flight_summary.duration_s <= 0:
            return "0s"
        return self._format_duration(self._flight_summary.duration_s)

    @Property(str, notify=flightSummaryChanged)
    def flightSummaryDistance(self) -> str:
        if not self._flight_summary:
            return "0 m"
        return f"{self._flight_summary.distance_m:.0f} m"

    @Property(str, notify=flightSummaryChanged)
    def flightSummaryMinBattery(self) -> str:
        if not self._flight_summary or self._flight_summary.min_battery_percent is None:
            return "n/a"
        return f"{self._flight_summary.min_battery_percent:.1f}%"

    @Property(int, notify=flightSummaryChanged)
    def flightSummaryObjects(self) -> int:
        if not self._flight_summary:
            return 0
        return self._flight_summary.confirmed_objects

    @Property(QUrl, notify=mapUrlChanged)
    def mapUrl(self) -> QUrl:
        return self.map_bridge.url

    @Property(str, constant=True)
    def mapBridgeScript(self) -> str:
        return self.map_bridge.bridgeScript

    @Property(float, notify=statsChanged)
    def fps(self) -> float:
        return self._fps

    @Property(float, notify=statsChanged)
    def latencyMs(self) -> float:
        return self._latency_ms

    @Property(float, notify=statsChanged)
    def detectionConfidence(self) -> float:
        return self._detection_conf

    @Property(str, notify=statsChanged)
    def currentBatteryText(self) -> str:
        if self._latest_telemetry and self._latest_telemetry.battery_percent is not None:
            return f"Battery: {float(self._latest_telemetry.battery_percent):.1f}%"
        return "Battery: --"

    @Property(bool, notify=statsChanged)
    def busAlive(self) -> bool:
        return self._bus_alive

    @Property(bool, notify=statsChanged)
    def groundStationEnabled(self) -> bool:
        return self._ground_station_enabled

    @Property(float, notify=statsChanged)
    def debugFlightProgress(self) -> float:
        return float(getattr(deps, "debug_flight_progress", 0.0))

    @Property(bool, notify=debugModeChanged)
    def debugMode(self) -> bool:
        if self._debug_sim is None:
            return False
        return self._debug_sim.telemetry_enabled()

    @Property(bool, notify=bridgeModeChanged)
    def bridgeModeEnabled(self) -> bool:
        return self._bridge_mode_enabled

    @Property(str, notify=bridgeBatteryProfileChanged)
    def bridgeBatteryProfileId(self) -> str:
        return self._bridge_profile_id

    @Property(bool, notify=unsafeStartChanged)
    def allowUnsafeStart(self) -> bool:
        return self._allow_unsafe_start

    @Property(str, notify=routeBatteryChanged)
    def routeBatteryText(self) -> str:
        return self._route_battery_text

    @Property(str, notify=routeBatteryChanged)
    def routeBatteryRemainingText(self) -> str:
        return self._route_battery_remaining_text

    @Property(bool, notify=routeBatteryChanged)
    def routeBatteryWarning(self) -> bool:
        return self._route_battery_warning

    @Property(bool, notify=simCameraEnabledChanged)
    def simCameraEnabled(self) -> bool:
        if self._debug_sim is None:
            return False
        return self._debug_sim.camera_enabled()

    @Property(str, constant=True)
    def tileCacheDir(self) -> str:
        return str(self._tile_cache_dir)

    # ---------- slots ---------- #
    @Slot()
    def cycleCamera(self) -> None:
        if self._camera_switcher is None:
            return
        self._camera_switcher()

    @Slot()
    def startDetector(self) -> None:
        self.det_vm.start()
        self._detector_running = True
        self.detectorRunningChanged.emit()

    @Slot()
    def stopDetector(self) -> None:
        self.det_vm.stop()
        self._detector_running = False
        self.detectorRunningChanged.emit()

    @Slot(float)
    def setConfidence(self, value: float) -> None:
        self._confidence = float(value)
        self.det_vm.set_conf(self._confidence)
        self.confidenceChanged.emit()

    @Slot(str)
    def handleMapConsole(self, message: str) -> None:
        self.map_bridge.handle_console(message)

    @Slot()
    def regenerateMap(self) -> None:
        self.map_bridge.render_map()

    @Slot()
    def refreshMapView(self) -> None:
        self.map_bridge.render_map()

    @Slot()
    def generatePath(self) -> None:
        self.map_bridge.generate_path()

    @Slot()
    def savePlan(self) -> None:
        self.map_bridge.save_plan()

    @Slot(str)
    def importGeoJson(self, filename: str) -> None:
        self.map_bridge.import_geojson(filename)

    @Slot(str)
    def importKml(self, filename: str) -> None:
        self.map_bridge.import_kml(filename)

    @Slot(str, bool, str)
    def setMapProvider(self, provider: str, offline: bool, cacheDir: str = "") -> None:
        self.map_bridge.set_provider(provider, offline=offline, cache_dir=cacheDir or None)

    @Slot()
    def confirmPlan(self) -> None:
        path = self._plan_vm.get_path()
        if not path:
            self.toastRequested.emit("Draw/generate a route first")
            return
        if not self._mission.confirm_plan(path):
            self.toastRequested.emit("Route invalid; cannot confirm")
            return
        self._active_path.set_normal()
        self._update_route_estimate(self._active_path.get_active_path())
        self.planConfirmedChanged.emit()
        self.flightControlsChanged.emit()
        if self._latest_telemetry:
            if not self._route_energy_ok(path):
                self._emit_warning(
                    key="battery_route_insufficient",
                    message="Insufficient battery for planned route",
                    severity="warn",
                    cooldown_s=8,
                )
        self.toastRequested.emit("Plan confirmed")

    @Slot()
    def startFlight(self) -> None:
        if not self._mission.plan_confirmed:
            self.toastRequested.emit("Confirm the plan first")
            return
        if not self._link_monitor.is_link_ok():
            self._emit_warning(
                key="uav_link_missing",
                message="UAV link missing; cannot start flight",
                severity="warn",
                cooldown_s=6,
            )
            if not self._allow_unsafe_start:
                return
        if not self._camera_monitor.is_camera_ok():
            self._emit_warning(
                key="camera_missing",
                message="Camera not ready; cannot start flight",
                severity="warn",
                cooldown_s=6,
            )
            if not self._allow_unsafe_start:
                return
        if self._latest_telemetry and not self._route_energy_ok(self._mission.confirmed_plan or []):
            self._emit_warning(
                key="battery_route_insufficient",
                message="Insufficient battery for planned route",
                severity="warn",
                cooldown_s=8,
            )
            return
        if self._mission.start_flight(skip_checks=False):
            self._commands_enabled = True
            self._rtl_forced = False
            self._rtl_route_sent = False
            deps.rtl_path = None
            deps.debug_orbit_path = None
            self._active_path.clear_overrides_on_new_flight()
            self.flightControlsChanged.emit()
            self.toastRequested.emit("Flight started")

    @Slot()
    def editRoute(self) -> None:
        if self._mission_state != MissionState.IN_FLIGHT:
            return
        self._route_edit_mode = True
        self._staged_plan = None
        self.toastRequested.emit("Edit mode: draw a new path on the map, double-click to finish, then Apply")
        self.flightControlsChanged.emit()

    @Slot()
    def applyRouteEdits(self) -> None:
        if not self._route_edit_mode:
            return
        if not self._staged_plan:
            self.toastRequested.emit("No staged route to apply")
            return
        self._mission.confirm_plan(self._staged_plan)
        deps.rtl_path = None
        deps.debug_orbit_path = None
        self._active_path.set_normal()
        self._update_route_estimate(self._active_path.get_active_path())
        self._route_edit_mode = False
        self._staged_plan = None
        self.planConfirmedChanged.emit()
        self.flightControlsChanged.emit()
        self.toastRequested.emit("Route updates applied")

    @Slot()
    def returnToHome(self) -> None:
        if self._mission_state != MissionState.IN_FLIGHT:
            return
        if not self._current_action_policy().can_rtl:
            if not self._link_monitor.is_link_ok():
                self._emit_warning(
                    key="uav_link_missing",
                    message="UAV link missing; RTL unavailable",
                    severity="warn",
                    cooldown_s=6,
                )
            return
        if not self._send_rtl_route():
            return
        self._mission.trigger_rtl("operator_rtl")
        self.toastRequested.emit("Return-to-home initiated")

    @Slot()
    def sendRtlRoute(self) -> None:
        if not self._current_action_policy().can_send_rtl_route:
            if not self._link_monitor.is_link_ok():
                self._emit_warning(
                    key="uav_link_missing",
                    message="UAV link missing; RTL unavailable",
                    severity="warn",
                    cooldown_s=6,
                )
            return
        self._send_rtl_route()

    @Slot()
    def completeLanding(self) -> None:
        if not self._current_action_policy().can_complete_landing:
            return
        self._mission.land_complete("operator_land")
        self._rtl_route_sent = False
        self.toastRequested.emit("Landing confirmed")

    @Slot()
    def abortToPreflight(self) -> None:
        if not self._current_action_policy().can_abort_to_preflight:
            return
        self._mission.abort_to_preflight("operator_abort")
        deps.rtl_path = None
        deps.debug_orbit_path = None
        self._rtl_route_sent = False
        self._active_path.set_normal()
        self.map_bridge.render_map()
        self.planConfirmedChanged.emit()
        self.flightControlsChanged.emit()
        self.toastRequested.emit("Mission aborted to preflight")

    @Slot()
    def backToPlanning(self) -> None:
        self._mission.set_preflight("postflight_reset")
        self._mission.invalidate_plan("postflight_reset")
        deps.rtl_path = None
        deps.debug_orbit_path = None
        self.planConfirmedChanged.emit()
        self.flightControlsChanged.emit()
        self.toastRequested.emit("Back to planning")

    @Slot()
    def orbitConfirmedObject(self) -> None:
        if self._objects_store.count() == 0:
            self.toastRequested.emit("No confirmed objects available")
            return
        target = self._objects_store.selected()
        if target is None and self._objects_store.count() > 1:
            self.toastRequested.emit("Select an object on the map first")
            return
        if target is None:
            target = self._objects_store.latest()
        if target is None:
            return
        self._orbit_targets([target])

    @Slot("QVariantList")
    def orbitSelectedObjects(self, object_ids: list) -> None:
        ids = [str(obj_id) for obj_id in object_ids or [] if str(obj_id)]
        if not ids:
            self.toastRequested.emit("Select at least one object")
            return
        targets = [self._objects_store.get(object_id) for object_id in ids]
        targets = [target for target in targets if target is not None]
        if not targets:
            self.toastRequested.emit("Selected objects unavailable")
            return
        self._orbit_targets(targets)

    @Slot(bool)
    def setSimTelemetryEnabled(self, enabled: bool) -> None:
        if self._debug_sim is None:
            return
        if enabled and not (self._mission.confirmed_plan or self._plan_vm.get_path()):
            self.toastRequested.emit("Draw/generate a route first")
            return
        self._debug_sim.set_telemetry_enabled(enabled)
        deps.debug_flight_enabled = enabled
        deps.debug_map_manual_refresh = bool(enabled)
        self.debugModeChanged.emit()
        self.statsChanged.emit()

    @Slot(bool)
    def setSimCameraEnabled(self, enabled: bool) -> None:
        if self._debug_sim is None:
            return
        self._debug_sim.set_camera_enabled(enabled)
        if enabled:
            self.set_camera_available(True)
        self.simCameraEnabledChanged.emit()
        self.statsChanged.emit()

    @Slot(bool)
    def setBridgeModeEnabled(self, enabled: bool) -> None:
        self._bridge_mode_enabled = bool(enabled)
        self.bridgeModeChanged.emit()
        self.flightControlsChanged.emit()
        self._update_route_estimate()

    @Slot(str)
    def setBridgeBatteryProfile(self, profile_id: str) -> None:
        if not profile_id:
            return
        profile = self._bridge_profiles.get(profile_id)
        if not profile:
            return
        self._bridge_profile_id = profile_id
        self._bridge_battery_wh = float(profile.get("battery_wh", self._bridge_battery_wh))
        self._bridge_speed_mps = float(profile.get("speed_mps", self._bridge_speed_mps))
        if self._debug_sim is not None:
            self._debug_sim.set_speed_mps(self._bridge_speed_mps)
        self.bridgeBatteryProfileChanged.emit()
        self._update_route_estimate()

    @Slot(bool)
    def setAllowUnsafeStart(self, enabled: bool) -> None:
        self._allow_unsafe_start = bool(enabled)
        self._mission.set_allow_unsafe_start(self._allow_unsafe_start)
        self.unsafeStartChanged.emit()
        self.flightControlsChanged.emit()
    @Slot()
    def spawnConfirmedObject(self) -> None:
        if self._debug_sim is None:
            return
        det = self._debug_sim.spawn_confirmed_object()
        self.toastRequested.emit(f"Spawned object at {det.lat:.4f}, {det.lon:.4f}")

    @Slot()
    def startFlightDebugMode(self) -> None:
        self.setSimTelemetryEnabled(True)
        self.toastRequested.emit("Sim telemetry ON")

    @Slot()
    def stopFlightDebugMode(self) -> None:
        self.setSimTelemetryEnabled(False)
        self.toastRequested.emit("Sim telemetry OFF")

    @Slot()
    def resetFlightDebugProgress(self) -> None:
        if self._debug_sim is None:
            return
        self._debug_sim.reset_progress()
        deps.debug_flight_progress = 0.0
        self.statsChanged.emit()

    @Slot()
    def orbitTarget(self) -> None:
        if not self._plan_vm.get_path():
            self.toastRequested.emit("Draw/generate a route first")
            return
        self.map_bridge.generate_path()
        self.map_bridge.recomputeOrbitPreview()

    @Slot()
    def clearDebugTarget(self) -> None:
        self.map_bridge.clearDebugTarget()

    @Slot()
    def rebuildRoute(self) -> None:
        try:
            self._plan_vm.rebuild_route_from_current_geom(None)
            self.map_bridge.render_map()
            self.toastRequested.emit("Route rebuild triggered (debug stub)")
        except Exception as exc:  # noqa: BLE001
            self.toastRequested.emit(str(exc))

    @Slot()
    def recomputeOrbitPreview(self) -> None:
        self.map_bridge.recomputeOrbitPreview()

    @Slot(str)
    def showToast(self, message: str) -> None:
        self.toastRequested.emit(message or "Debug notification")

    # ---------- helpers ---------- #
    def on_frame(self, frame: NDArray[np.uint8]) -> None:
        now = time.perf_counter()
        if self._last_frame_ts is not None:
            dt = now - self._last_frame_ts
            if dt > 0:
                inst_fps = 1.0 / dt
                self._fps = 0.85 * self._fps + 0.15 * inst_fps if self._fps else inst_fps
        self._last_frame_ts = now
        self._camera_monitor.on_frame()
        if not self._camera_available:
            self.set_camera_available(True)
        self._update_stats()
        self.video_bridge.update_frame(frame)

    def on_telemetry(self, sample: TelemetrySample) -> None:
        self._latest_telemetry = sample
        deps.latest_telemetry = sample
        uav_id = self._resolve_uav_id(sample)
        self._telemetry_store.update(uav_id, sample)
        state = self._uav_states.get(uav_id)
        if state is None:
            state = UavState(uav_id)
            self._uav_states[uav_id] = state
            self.uavStatesChanged.emit()
        state.update_from_sample(sample)
        self._link_monitor.on_telemetry(sample)
        self._flight_recorder.record_telemetry(sample)
        self._handle_battery(sample)
        self._update_route_estimate()
        self.statsChanged.emit()

    def set_camera_available(self, flag: bool) -> None:
        self._camera_available = flag
        self.cameraAvailableChanged.emit()

    def _on_detections(self, dets) -> None:  # noqa: ANN001
        det_list = getattr(dets, "detections", [])
        if not det_list:
            self._detection_conf = 0.0
            self._last_detection_ts = None
            self._update_stats()
            return
        best_conf = max(getattr(d, "score", getattr(d, "confidence", 0.0)) for d in det_list)
        bbox = getattr(det_list[0], "bbox", None)
        if bbox is None and all(hasattr(det_list[0], k) for k in ("x1", "y1", "x2", "y2")):
            bbox = (
                getattr(det_list[0], "x1"),
                getattr(det_list[0], "y1"),
                getattr(det_list[0], "x2"),
                getattr(det_list[0], "y2"),
            )
        stable_count = getattr(self.det_vm, "last_stable_count", 0)
        stable_conf = getattr(self.det_vm, "last_stable_conf", 0.0)
        eff_conf = stable_conf if stable_count > 0 else best_conf
        self._detection_conf = eff_conf
        _log.info(
            "GUI detection event: raw=%d best=%.2f stable=%d stable_conf=%.2f bbox=%s",
            len(det_list),
            best_conf,
            stable_count,
            stable_conf,
            bbox,
        )
        if stable_count > 0:
            self.toastRequested.emit(f"Confirmed: {stable_count} (avg {stable_conf:.2f})")
        else:
            self.toastRequested.emit(f"Detections: {len(det_list)} (best {best_conf:.2f})")
        self._log_detection_event(det_list, eff_conf, bbox)

        now = time.perf_counter()
        self._last_detection_ts = now
        if self._last_frame_ts is not None:
            self._latency_ms = max(0.0, (now - self._last_frame_ts) * 1000)
        self._update_stats()

    def _append_log(self, line: str) -> None:
        self._logs.append(line)
        self._trim_logs()
        self.logsChanged.emit()

    def _on_object_confirmed(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        obj_id = str(payload.get("object_id", ""))
        cls_id = int(payload.get("class_id", -1))
        conf = float(payload.get("confidence", 0.0))
        track_id = payload.get("track_id")
        track_str = f", track {track_id}" if track_id is not None else ""
        msg = f"Object {obj_id} (class {cls_id}{track_str}, conf {conf:.2f}) detected"
        self.objectNotificationReceived.emit(obj_id, cls_id, conf, msg, track_id)

    def attach_debug_sim(self, sim: DebugSimulationService) -> None:
        self._debug_sim = sim
        self._debug_sim.set_speed_mps(self._bridge_speed_mps)

    def get_confirmed_path(self) -> list[tuple[float, float]]:
        return self._mission.confirmed_plan or self._plan_vm.get_path()

    def get_active_path_for_sim(self) -> list[tuple[float, float]]:
        return self._active_path.get_active_path()

    def _on_active_path_changed(self, _mode: ActivePathMode) -> None:
        self._update_route_estimate(self._active_path.get_active_path())
        try:
            self.map_bridge.render_map()
        except Exception:
            pass
        self.flightControlsChanged.emit()

    def _on_status_tick(self) -> None:
        self._link_monitor.check()
        self._camera_monitor.check()
        self._mission.refresh_readiness("status_tick")
        self.flightControlsChanged.emit()

    def _on_mission_state(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        state_raw = payload.get("state")
        try:
            new_state = MissionState(str(state_raw))
        except Exception:
            return
        if new_state == self._mission_state:
            return
        self._mission_state = new_state
        if new_state in (MissionState.PREFLIGHT, MissionState.READY):
            self._route_edit_mode = False
            self._staged_plan = None
            self._commands_enabled = True
            self._rtl_forced = False
            self._rtl_route_sent = False
            deps.rtl_path = None
            deps.debug_orbit_path = None
            deps.selected_object_id = None
            deps.debug_target = None
            if new_state == MissionState.PREFLIGHT:
                self._flight_summary = None
                self.flightSummaryChanged.emit()
        if new_state == MissionState.IN_FLIGHT:
            self._commands_enabled = self._link_monitor.is_link_ok()
            if self._bridge_mode_enabled and self._debug_sim is not None:
                if not self._debug_sim.telemetry_enabled():
                    self.setSimTelemetryEnabled(True)
        if new_state == MissionState.RTL:
            self._commands_enabled = self._link_monitor.is_link_ok()
        if new_state == MissionState.POSTFLIGHT:
            self._route_edit_mode = False
            self._staged_plan = None
            deps.rtl_path = None
            deps.debug_orbit_path = None
        if new_state in (MissionState.PREFLIGHT, MissionState.READY, MissionState.POSTFLIGHT):
            self._active_path.set_normal()
        self.missionStateChanged.emit()
        self.flightControlsChanged.emit()

    def _on_link_status(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        status_raw = payload.get("status")
        try:
            self._link_status = LinkStatus(str(status_raw))
        except Exception:
            return
        if self._mission_state == MissionState.IN_FLIGHT:
            if self._link_status == LinkStatus.DISCONNECTED:
                self._commands_enabled = False
                self.toastRequested.emit("Link lost; commands disabled")
            elif self._link_status == LinkStatus.CONNECTED:
                self._commands_enabled = True
        if self._link_status == LinkStatus.DISCONNECTED:
            self._emit_warning(
                key="uav_link_missing",
                message="UAV link missing / telemetry lost",
                severity="warn",
                cooldown_s=6,
            )
        elif self._link_status == LinkStatus.DEGRADED:
            self._emit_warning(
                key="uav_link_stale",
                message="Telemetry stale; check UAV link",
                severity="warn",
                cooldown_s=6,
            )
        self._mission.refresh_readiness("link_status")
        self.linkStatusChanged.emit()
        self.flightControlsChanged.emit()

    def _on_camera_status(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        status_raw = payload.get("status")
        try:
            self._camera_status = CameraStatus(str(status_raw))
        except Exception:
            return
        if self._camera_status == CameraStatus.NOT_READY:
            self._emit_warning(
                key="camera_missing",
                message="Camera not ready / not streaming",
                severity="warn",
                cooldown_s=6,
            )
            self.set_camera_available(False)
        elif self._camera_status == CameraStatus.READY:
            self.set_camera_available(True)
        self._mission.refresh_readiness("camera_status")
        self.cameraStatusChanged.emit()
        self.flightControlsChanged.emit()

    def _on_capabilities_updated(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        caps = payload.get("capabilities")
        if hasattr(caps, "model_dump"):
            caps = caps.model_dump()
        if not isinstance(caps, dict):
            return
        self._capabilities.update(caps)
        self.flightControlsChanged.emit()

    def _on_warning_toast(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        key = str(payload.get("key", "warning"))
        message = str(payload.get("message", "Warning"))
        cooldown_s = float(payload.get("cooldown_s", 5))
        if self._toast_dedupe.should_show(key, cooldown_s):
            self.toastRequested.emit(message)

    def _on_flight_session_ended(self, _payload: object) -> None:
        summary = getattr(self._flight_recorder, "last_summary", None)
        if summary is None:
            return
        self._flight_summary = summary
        self.flightSummaryChanged.emit()

    def _on_plan_changed(self, pts: list) -> None:
        path = [(float(lat), float(lon)) for lat, lon in pts]
        if self._mission_state == MissionState.IN_FLIGHT:
            if not self._route_edit_mode:
                self._route_edit_mode = True
                self.toastRequested.emit("Route edit mode enabled")
            self._staged_plan = path
            self.flightControlsChanged.emit()
            return
        self._mission.invalidate_plan("plan_changed")
        deps.rtl_path = None
        self.planConfirmedChanged.emit()
        self.flightControlsChanged.emit()
        self._update_route_estimate(path)

    def _on_object_selected(self, object_id: str, lat: float, lon: float) -> None:
        deps.selected_object_id = object_id
        self._objects_store.set_selected(object_id)
        deps.debug_target = {"lat": lat, "lon": lon}
        self.map_bridge.render_map()
        self.flightControlsChanged.emit()

    def _on_objects_changed(self) -> None:
        deps.confirmed_objects = [
            {
                "object_id": obj.object_id,
                "class_id": obj.class_id,
                "confidence": obj.confidence,
                "lat": obj.lat,
                "lon": obj.lon,
                "track_id": obj.track_id,
            }
            for obj in self._objects_store.all()
        ]
        self.confirmedObjectsChanged.emit()
        self.flightControlsChanged.emit()
        try:
            self.map_bridge.render_map()
        except Exception:
            pass

    def _current_action_policy(self) -> MissionActionPolicy:
        selected = self._objects_store.selected()
        selected_id = selected.object_id if selected else None
        supports_waypoints = bool(self._capabilities.get("supports_waypoints", True))
        supports_orbit = bool(self._capabilities.get("supports_orbit", True))
        supports_rtl = bool(self._capabilities.get("supports_rtl", True))
        return MissionActionPolicy.evaluate(
            mission_state=self._mission_state,
            link_ok=self._link_monitor.is_link_ok(),
            camera_ok=self._camera_monitor.is_camera_ok(),
            commands_enabled=self._commands_enabled,
            has_confirmed_plan=self._mission.plan_confirmed,
            active_path_mode=self._active_path.mode,
            confirmed_object_count=self._objects_store.count(),
            selected_object_id=selected_id,
            route_edit_mode=self._route_edit_mode,
            allow_unsafe_start=self._allow_unsafe_start,
            supports_waypoints=supports_waypoints,
            supports_orbit=supports_orbit,
            supports_rtl=supports_rtl,
        )

    def _emit_warning(self, *, key: str, message: str, severity: str, cooldown_s: float) -> None:
        bus.emit(
            Event.WARNING_TOAST,
            {
                "key": key,
                "message": message,
                "severity": severity,
                "cooldown_s": cooldown_s,
            },
        )

    def _update_route_estimate(self, path: list[tuple[float, float]] | None = None) -> None:
        if path is None:
            path = self._active_path.get_active_path()
        max_distance_m = self._resolve_max_distance_m()
        reserved = float(getattr(settings, "min_return_percent", 20.0) or 0.0)
        available = 100.0
        if self._latest_telemetry and self._latest_telemetry.battery_percent is not None:
            available = float(self._latest_telemetry.battery_percent)
        route_available = available
        if self._mission_state in (MissionState.PREFLIGHT, MissionState.READY):
            route_available = 100.0
        fallback_lat, fallback_lon = (0.0, 0.0)
        if path:
            fallback_lat, fallback_lon = path[-1]
        else:
            center = getattr(settings, "map_center", None)
            if isinstance(center, (list, tuple)) and len(center) >= 2:
                try:
                    fallback_lat, fallback_lon = float(center[0]), float(center[1])
                except (TypeError, ValueError):
                    pass
        telemetry = self._latest_telemetry or TelemetrySample(
            lat=fallback_lat,
            lon=fallback_lon,
            alt=120.0,
            battery=1.0,
            battery_percent=available,
            timestamp=datetime.utcnow(),
        )
        base_route = self._route_from_points(path) or Route(version=1, waypoints=[], active_index=None)
        base = self._resolve_base_location(base_route, telemetry)
        deps.route_stats = {
            "max_distance_m": max_distance_m,
            "available_percent": route_available,
            "reserved_percent": reserved,
            "base": [base.lon, base.lat] if base else None,
            "clamp_enabled": self._mission_state in (MissionState.IN_FLIGHT, MissionState.RTL),
        }
        if len(path) < 2:
            self._route_battery_text = "Route: --"
            self._route_battery_remaining_text = "Remaining: --"
            self._route_battery_warning = False
            self.routeBatteryChanged.emit()
            return

        route_distance = 0.0
        for a, b in zip(path[:-1], path[1:]):
            route_distance += haversine_m(a, b)

        end_lat, end_lon = path[-1]
        return_leg = 0.0
        if base is not None:
            return_leg = haversine_m((end_lat, end_lon), (base.lat, base.lon))
        total_distance = route_distance + return_leg

        if max_distance_m <= 0:
            self._route_battery_text = "Route: n/a"
            self._route_battery_remaining_text = "Remaining: n/a"
            self._route_battery_warning = False
            self.routeBatteryChanged.emit()
            return

        route_percent = (route_distance / max_distance_m) * 100.0
        required_percent = (total_distance / max_distance_m) * 100.0
        total_required = required_percent + reserved
        remaining = available - total_required

        if not self._link_monitor.is_link_ok() and not self._bridge_mode_enabled:
            self._emit_warning(
                key="no_uav_stub_battery",
                message="UAV link missing; using stub battery model",
                severity="warn",
                cooldown_s=12,
            )

        if remaining < 0:
            self._route_battery_warning = True
            self._emit_warning(
                key="route_energy_insufficient",
                message="Insufficient battery for return to home",
                severity="warn",
                cooldown_s=8,
            )
        else:
            self._route_battery_warning = False

        remaining_display = max(0.0, 100.0 - route_percent)
        self._route_battery_remaining_text = f"Remaining: {remaining_display:.1f}%"
        self._route_battery_text = f"Route: {route_percent:.1f}%" if route_percent > 0 else "Route: --"
        self.routeBatteryChanged.emit()

    def _orbit_targets(self, targets: list[ConfirmedObject]) -> None:
        if self._mission_state != MissionState.IN_FLIGHT:
            return
        if not self._commands_enabled:
            self.toastRequested.emit("Link lost; commands disabled")
            return
        if not self._latest_telemetry:
            self.toastRequested.emit("No telemetry available for orbit")
            return
        base_path = self._mission.confirmed_plan or self._plan_vm.get_path()
        base_route = self._route_from_points(base_path)
        if base_route is None:
            self.toastRequested.emit("Confirm a route before orbiting")
            return
        combined: list[Waypoint] = []
        for target in targets:
            route = self._plan_vm._route_planner.plan_maneuver(
                current_state=self._latest_telemetry,
                target_lat=target.lat,
                target_lon=target.lon,
                base_route=base_route,
            )
            if route is None:
                self._emit_warning(
                    key="battery_orbit_insufficient",
                    message="Insufficient battery for orbit",
                    severity="warn",
                    cooldown_s=8,
                )
                return
            combined.extend(route.waypoints)
        if not combined:
            self.toastRequested.emit("Orbit route unavailable")
            return
        deps.debug_target = {"lat": targets[-1].lat, "lon": targets[-1].lon}
        deps.debug_orbit_path = [(wp.lat, wp.lon) for wp in combined]
        self._active_path.set_orbit(deps.debug_orbit_path)
        self.map_bridge.render_map()
        self.toastRequested.emit("Orbit route staged")

    def _handle_battery(self, sample: TelemetrySample) -> None:
        if self._mission_state not in (MissionState.IN_FLIGHT, MissionState.READY):
            return
        if self._rtl_forced:
            return
        try:
            critical = self._energy_model.is_critical(sample)
        except Exception:
            critical = False
        if not critical:
            return
        self._rtl_forced = True
        bus.emit(Event.BATTERY_CRITICAL, {"battery_percent": sample.battery_percent})
        self._emit_warning(
            key="battery_critical",
            message="Critical battery; forcing return-to-home",
            severity="error",
            cooldown_s=10,
        )
        if self._mission_state == MissionState.IN_FLIGHT:
            self._send_rtl_route()
            self._mission.trigger_rtl("battery_critical")

    def _route_energy_ok(self, pts: list[tuple[float, float]]) -> bool:
        if not self._latest_telemetry:
            return True
        route = self._route_from_points(pts)
        if route is None:
            return True
        base = self._resolve_base_location(route, self._latest_telemetry)
        if base is None:
            return True
        try:
            estimate = self._energy_model.estimate_route_feasibility(self._latest_telemetry, route, base)
        except Exception:
            return True
        return bool(estimate.can_complete)

    def _route_from_points(self, pts: list[tuple[float, float]]) -> Route | None:
        if len(pts) < 2:
            return None
        alt = self._latest_telemetry.alt if self._latest_telemetry else 120.0
        waypoints = [Waypoint(lat=lat, lon=lon, alt=alt) for lat, lon in pts]
        return Route(version=1, waypoints=waypoints, active_index=0)

    def _resolve_max_distance_m(self) -> float:
        max_distance_m = float(getattr(settings, "max_flight_distance_m", 15000.0) or 0.0)
        if max_distance_m > 0:
            return max_distance_m
        battery_wh = self._bridge_battery_wh or float(getattr(settings, "battery_wh", 4500.0) or 4500.0)
        cruise_speed = float(getattr(settings, "cruise_speed_mps", 12.0) or 12.0)
        power_w = float(getattr(settings, "power_cruise_w", 45.0) or 45.0)
        if power_w <= 0 or cruise_speed <= 0:
            return float(getattr(settings, "max_flight_distance_m", 15000.0) or 0.0)
        return (battery_wh / power_w) * cruise_speed * 3600.0

    def _resolve_base_location(self, route: Route, telemetry: TelemetrySample) -> WorldCoord | None:
        for lat_key, lon_key in (("home_lat", "home_lon"), ("base_lat", "base_lon")):
            lat = getattr(settings, lat_key, None)
            lon = getattr(settings, lon_key, None)
            if lat is not None and lon is not None:
                try:
                    return WorldCoord(lat=float(lat), lon=float(lon))
                except (TypeError, ValueError):
                    pass
        center = getattr(settings, "map_center", None)
        if isinstance(center, (list, tuple)) and len(center) >= 2:
            try:
                return WorldCoord(lat=float(center[0]), lon=float(center[1]))
            except (TypeError, ValueError):
                pass
        if route.waypoints:
            wp = route.waypoints[0]
            return WorldCoord(lat=wp.lat, lon=wp.lon)
        return WorldCoord(lat=telemetry.lat, lon=telemetry.lon)

    def _resolve_uav_id(self, sample: TelemetrySample) -> str:
        source = getattr(sample, "source", None)
        if source:
            return str(source)
        return str(getattr(settings, "uav_id", None) or "uav")

    def _should_emit_uav_pose(
        self,
        uav_id: str,
        lat: float,
        lon: float,
        heading: float,
    ) -> bool:
        last = self._last_sent_pose.get(uav_id)
        if last is None:
            return True
        last_lat, last_lon, last_heading = last
        if haversine_m((lat, lon), (last_lat, last_lon)) >= 2.0:
            return True
        delta = abs(((heading - last_heading + 180.0) % 360.0) - 180.0)
        return delta >= 3.0

    def _emit_map_updates(self) -> None:
        for envelope in self._telemetry_store.items():
            sample = envelope.sample
            try:
                lat = float(sample.lat)
                lon = float(sample.lon)
                heading = float(getattr(sample, "yaw", 0.0) or 0.0)
            except Exception:
                continue
            if not self._should_emit_uav_pose(envelope.uav_id, lat, lon, heading):
                continue
            self._last_sent_pose[envelope.uav_id] = (lat, lon, heading)
            self.mapUavPoseUpdated.emit(envelope.uav_id, lat, lon, heading)

    def _send_rtl_route(self) -> bool:
        route = self._build_rtl_route()
        if route is None:
            return False
        self._rtl_route_sent = True
        deps.rtl_path = [(wp.lat, wp.lon) for wp in route.waypoints]
        deps.debug_orbit_path = None
        self._active_path.set_rtl(deps.rtl_path)
        self.map_bridge.render_map()
        return True

    def _build_rtl_route(self) -> Route | None:
        if self._latest_telemetry is None:
            self.toastRequested.emit("No telemetry available for RTL")
            return None
        base = self._resolve_base_location(Route(version=1, waypoints=[], active_index=None), self._latest_telemetry)
        if base is None:
            self.toastRequested.emit("Home location unavailable")
            return None
        alt = self._latest_telemetry.alt
        waypoints = [
            Waypoint(lat=self._latest_telemetry.lat, lon=self._latest_telemetry.lon, alt=alt),
            Waypoint(lat=base.lat, lon=base.lon, alt=alt),
        ]
        route = Route(version=1, waypoints=waypoints, active_index=0)
        try:
            estimate = self._energy_model.estimate_route_feasibility(self._latest_telemetry, route, base)
            if not estimate.can_complete:
                self._emit_warning(
                    key="battery_rtl_insufficient",
                    message="Battery low for RTL; attempting best-effort return",
                    severity="error",
                    cooldown_s=10,
                )
        except Exception:
            pass
        return route

    def _can_start_flight(self) -> bool:
        if self._mission_state not in (MissionState.PREFLIGHT, MissionState.READY):
            return False
        if not self._mission.plan_confirmed:
            return False
        if self._allow_unsafe_start:
            return True
        return self._link_monitor.is_link_ok() and self._camera_monitor.is_camera_ok()

    def _can_orbit(self) -> bool:
        return self._current_action_policy().can_orbit

    @staticmethod
    def _format_duration(duration_s: float) -> str:
        mins, secs = divmod(int(duration_s), 60)
        if mins:
            return f"{mins}m {secs}s"
        return f"{secs}s"

    @staticmethod
    def _load_bridge_profiles() -> dict[str, dict[str, object]]:
        return {
            "mavic3": {"label": "DJI Mavic 3 (77 Wh)", "battery_wh": 77.0, "speed_mps": 15.0},
            "mini4": {"label": "DJI Mini 4 Pro (29 Wh)", "battery_wh": 29.0, "speed_mps": 12.0},
            "matrice30": {"label": "DJI Matrice 30T (263 Wh)", "battery_wh": 263.0, "speed_mps": 16.0},
            "autel_evo": {"label": "Autel EVO II (82 Wh)", "battery_wh": 82.0, "speed_mps": 16.0},
            "skydio_x2": {"label": "Skydio X2 (49 Wh)", "battery_wh": 49.0, "speed_mps": 13.0},
        }

    def _update_stats(self) -> None:
        now = time.perf_counter()
        if self._last_detection_ts is not None and (now - self._last_detection_ts) > 2.0:
            self._detection_conf = 0.0
        bus_alive = self._last_detection_ts is not None and (now - self._last_detection_ts) < 2.0
        if bus_alive != self._bus_alive:
            self._bus_alive = bus_alive
        self.statsChanged.emit()

    def _trim_logs(self) -> None:
        if len(self._logs) > 400:
            self._logs = self._logs[-400:]

    def _load_log_history(self, limit: int = 200) -> None:
        try:
            if not self._log_history_path.exists():
                return
            lines = self._log_history_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if limit:
                lines = lines[-limit:]
            self._logs.extend(lines)
            self._trim_logs()
            if lines:
                self.logsChanged.emit()
        except Exception:  # noqa: BLE001
            _log.exception("Failed to preload log history")

    # ---------- detection logging helpers ---------- #
    def _log_detection_event(
        self, detections: list[object], best_conf: float, bbox: tuple[int, int, int, int] | None
    ) -> None:
        classes = [
            int(getattr(d, "class_id", getattr(d, "cls", -1)))
            for d in detections
            if hasattr(d, "class_id") or hasattr(d, "cls")
        ]
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "count": len(detections),
            "best_confidence": round(float(best_conf), 4),
            "best_bbox": list(bbox) if bbox else None,
            "classes": classes,
            "detections": [self._serialize_detection(d) for d in detections],
        }
        _log.info(
            "Detection summary | count=%d best=%.2f classes=%s bbox=%s",
            len(detections),
            best_conf,
            classes or "n/a",
            bbox,
        )
        _log.info("Detection JSON %s", json.dumps(payload, ensure_ascii=False))
        self._write_detection_json(payload)

    def _serialize_detection(self, det: object) -> dict[str, object]:
        bbox = getattr(det, "bbox", None)
        if bbox is None and all(hasattr(det, k) for k in ("x1", "y1", "x2", "y2")):
            bbox = (
                getattr(det, "x1"),
                getattr(det, "y1"),
                getattr(det, "x2"),
                getattr(det, "y2"),
            )
        ts = getattr(det, "timestamp", None)
        ts_iso = None
        if hasattr(ts, "isoformat"):
            try:
                ts_iso = ts.isoformat()
            except Exception:  # noqa: BLE001
                ts_iso = None
        return {
            "class_id": getattr(det, "class_id", getattr(det, "cls", None)),
            "confidence": float(getattr(det, "confidence", getattr(det, "score", 0.0))),
            "bbox": list(bbox) if bbox else None,
            "camera_id": getattr(det, "camera_id", None),
            "timestamp": ts_iso,
        }

    def _write_detection_json(self, payload: dict[str, object]) -> None:
        try:
            self._det_json_path.parent.mkdir(parents=True, exist_ok=True)
            with self._det_json_path.open("a", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
                fh.write("\n")
        except Exception:  # noqa: BLE001
            _log.exception("Failed to write detection JSON")


# --------------------------------------------------------------------------- #
#                               MainWindow facade
# --------------------------------------------------------------------------- #
class MainWindow(QObject):
    """QML-driven UI facade that keeps the existing lifecycle wiring."""

    def __init__(self) -> None:
        super().__init__()
        self.det_vm = DetectorVM()
        self.plan_vm = PlannerVM()
        self._frame_q = deps.frame_queue
        self._cam_fps = getattr(settings, "camera_fps", 30)
        self._camera_index = 0
        self._camera_candidates: list[int] = self._probe_cameras()

        # Optional camera/detector threads
        try:
            self.cam_thr = deps.get_camera()
            self.det_thr = deps.get_detector()
            self._have_camera = True
            self._camera_index = getattr(self.cam_thr, "index", 0)
            if self._camera_index not in self._camera_candidates:
                self._camera_candidates.insert(0, self._camera_index)
            self.cam_thr.frame.connect(self._on_frame)
            self.cam_thr.error.connect(lambda msg: self.app.toastRequested.emit(msg))
        except RuntimeError:
            self.cam_thr = None
            self.det_thr = None
            self._have_camera = False

        # Register components before QML triggers APP_START so start_all() sees them.
        deps.get_lifecycle().register(self.cam_thr, self.det_thr)

        # Bridges exposed to QML
        self._video_provider = VideoFrameProvider()
        self._video_bridge = VideoBridge(self._video_provider)
        self._map_bridge = MapBridge(self.plan_vm)
        self.app = AppController(
            self.det_vm,
            self._map_bridge,
            self._video_bridge,
            camera_available=self._have_camera,
            camera_switcher=self._cycle_camera,
        )
        self._debug_sim = DebugSimulationService(
            route_provider=self.app.get_active_path_for_sim,
            telemetry_callback=self.app.on_telemetry,
            frame_callback=self._on_frame,
        )
        self.app.attach_debug_sim(self._debug_sim)

        # QML engine + context
        self._engine = QQmlApplicationEngine()
        self._engine.addImageProvider("video", self._video_provider)
        self._engine.rootContext().setContextProperty("app", self.app)

        qml_path = Path(__file__).resolve().parents[1] / "qml" / "main.qml"
        _log.info("Loading QML UI from %s", qml_path)
        self._engine.load(QUrl.fromLocalFile(str(qml_path)))
        if not self._engine.rootObjects():
            raise RuntimeError("Failed to load QML UI")
        self._window = self._engine.rootObjects()[0]

    # ---------- facade API ---------- #
    def show(self) -> None:
        if self._window is not None:
            self._window.show()

    # ---------- slots from threads ---------- #
    def _on_frame(self, frame: NDArray[np.uint8]) -> None:
        if self._frame_q is not None:
            try:
                self._frame_q.put_nowait(frame)
            except Exception:
                pass
        self.app.on_frame(frame)

    # ---------- camera helpers ---------- #
    def _probe_cameras(self, limit: int = 5) -> list[int]:
        found: list[int] = []
        for idx in range(limit):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                found.append(idx)
            cap.release()
        return found

    def _camera_available(self, index: int) -> bool:
        cap = cv2.VideoCapture(index)
        ok = cap.isOpened()
        cap.release()
        return ok

    def _cycle_camera(self) -> bool:
        # Refresh candidate list each time to catch hotplug devices.
        self._camera_candidates = self._probe_cameras()
        if len(self._camera_candidates) <= 1:
            self.app.toastRequested.emit("No alternate camera found")
            return False

        current = (
            self._camera_index
            if self._camera_index in self._camera_candidates
            else self._camera_candidates[0]
        )
        next_idx = self._camera_candidates[
            (self._camera_candidates.index(current) + 1) % len(self._camera_candidates)
        ]
        if next_idx == current and len(self._camera_candidates) == 1:
            self.app.toastRequested.emit("No alternate camera found")
            return False

        return self._switch_camera(next_idx)

    def _switch_camera(self, index: int) -> bool:
        if not self._camera_available(index):
            self._have_camera = False
            self.app.set_camera_available(False)
            self.app.toastRequested.emit(f"Camera #{index} is not available")
            return False

        old_cam = getattr(self, "cam_thr", None)
        if old_cam is not None:
            try:
                old_cam.stop()
                old_cam.join(timeout=2.0)
            except Exception:  # noqa: BLE001
                pass

        try:
            new_cam = CameraThread(index=index, fps=self._cam_fps, out_queue=self._frame_q)
        except Exception as exc:  # noqa: BLE001
            self.cam_thr = None
            self._have_camera = False
            self.app.set_camera_available(False)
            self.app.toastRequested.emit(f"Failed to init camera #{index}: {exc}")
            return False

        new_cam.frame.connect(self._on_frame)
        new_cam.error.connect(lambda msg: self.app.toastRequested.emit(msg))
        deps.get_lifecycle().register(new_cam)
        new_cam.start()

        self.cam_thr = new_cam
        self._camera_index = index
        self._have_camera = True
        self.app.set_camera_available(True)
        self.app.toastRequested.emit(f"Camera switched to #{index}")
        return True
