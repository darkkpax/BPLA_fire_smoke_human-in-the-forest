from __future__ import annotations

from collections import deque
from datetime import datetime
from types import SimpleNamespace

from fire_uav.gui.windows import main_window as main_window_module
from fire_uav.gui.windows.main_window import AppController, RecoverableMissionSnapshot
from fire_uav.module_core.detections.aggregator import DetectionEvent
from fire_uav.module_core.detections.pipeline import DetectionPipeline
from fire_uav.module_core.detections.registry import ObjectRegistry
from fire_uav.module_core.schema import GeoDetection, TelemetrySample, WorldCoord
from fire_uav.services.bus import Event
from fire_uav.utils.time import utc_now


class _Signal:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def emit(self, *args) -> None:
        self.calls.append(args)


class _ObjectsStore:
    def __init__(self) -> None:
        self.cleared = 0
        self.selected_ids: list[str | None] = []

    def clear(self) -> None:
        self.cleared += 1

    def set_selected(self, object_id: str | None) -> None:
        self.selected_ids.append(object_id)


def _timestamp() -> datetime:
    return utc_now()


def _telemetry() -> TelemetrySample:
    return TelemetrySample(
        lat=47.6060,
        lon=-122.3350,
        alt=120.0,
        alt_agl=20.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.95,
        battery_percent=95.0,
        timestamp=_timestamp(),
    )


def test_object_registry_merges_close_fire_with_new_track_id() -> None:
    registry = ObjectRegistry()
    first = registry.create_or_update(
        GeoDetection(
            class_id=1,
            confidence=0.62,
            lat=47.606000,
            lon=-122.335000,
            timestamp=_timestamp(),
            track_id=10,
        ),
        uav_id="sim",
        track_id=10,
    )
    second = registry.create_or_update(
        GeoDetection(
            class_id=1,
            confidence=0.71,
            lat=47.606030,
            lon=-122.334980,
            timestamp=_timestamp(),
            track_id=77,
        ),
        uav_id="sim",
        track_id=77,
    )

    assert second.object_id == first.object_id
    assert second.track_id == 77
    assert registry.find_by_track(77, 1) is second


def test_object_registry_merges_same_fire_even_when_geo_shift_is_tens_of_meters() -> None:
    registry = ObjectRegistry(spatial_match_radius_m=90.0)
    first = registry.create_or_update(
        GeoDetection(
            class_id=1,
            confidence=0.62,
            lat=47.606000,
            lon=-122.335000,
            timestamp=_timestamp(),
            track_id=10,
        ),
        uav_id="sim",
        track_id=10,
    )
    second = registry.create_or_update(
        GeoDetection(
            class_id=1,
            confidence=0.71,
            lat=47.606420,
            lon=-122.334820,
            timestamp=_timestamp(),
            track_id=77,
        ),
        uav_id="sim",
        track_id=77,
    )

    assert second.object_id == first.object_id
    assert second.track_id == 77


def test_detection_pipeline_dedupes_close_same_fire_events() -> None:
    pipeline = DetectionPipeline.__new__(DetectionPipeline)
    now = _timestamp()
    deduped = pipeline._dedupe_projected_events(
        [
            (
                DetectionEvent(
                    class_id=1,
                    confidence=0.88,
                    location=WorldCoord(lat=47.606000, lon=-122.335000),
                    frame_id="f1",
                    timestamp=now,
                    track_id=10,
                ),
                (500.0, 400.0, 620.0, 560.0),
            ),
            (
                DetectionEvent(
                    class_id=1,
                    confidence=0.74,
                    location=WorldCoord(lat=47.606040, lon=-122.334990),
                    frame_id="f1",
                    timestamp=now,
                    track_id=11,
                ),
                (518.0, 412.0, 640.0, 575.0),
            ),
        ]
    )

    assert len(deduped) == 1
    assert deduped[0].track_id == 10


def test_detection_pipeline_keeps_far_fire_events_separate() -> None:
    pipeline = DetectionPipeline.__new__(DetectionPipeline)
    now = _timestamp()
    deduped = pipeline._dedupe_projected_events(
        [
            (
                DetectionEvent(
                    class_id=1,
                    confidence=0.88,
                    location=WorldCoord(lat=47.606000, lon=-122.335000),
                    frame_id="f1",
                    timestamp=now,
                    track_id=10,
                ),
                (500.0, 400.0, 620.0, 560.0),
            ),
            (
                DetectionEvent(
                    class_id=1,
                    confidence=0.74,
                    location=WorldCoord(lat=47.607400, lon=-122.333200),
                    frame_id="f1",
                    timestamp=now,
                    track_id=11,
                ),
                (900.0, 420.0, 1040.0, 580.0),
            ),
        ]
    )

    assert len(deduped) == 2


def test_detection_pipeline_dedupes_same_fire_with_larger_geo_jitter() -> None:
    pipeline = DetectionPipeline.__new__(DetectionPipeline)
    now = _timestamp()
    deduped = pipeline._dedupe_projected_events(
        [
            (
                DetectionEvent(
                    class_id=1,
                    confidence=0.88,
                    location=WorldCoord(lat=47.606000, lon=-122.335000),
                    frame_id="f1",
                    timestamp=now,
                    track_id=10,
                ),
                (500.0, 400.0, 620.0, 560.0),
            ),
            (
                DetectionEvent(
                    class_id=1,
                    confidence=0.74,
                    location=WorldCoord(lat=47.606330, lon=-122.334880),
                    frame_id="f1",
                    timestamp=now,
                    track_id=11,
                ),
                (540.0, 425.0, 655.0, 585.0),
            ),
        ]
    )

    assert len(deduped) == 1


def test_restore_recoverable_mission_resends_route_and_objects(monkeypatch) -> None:
    controller = AppController.__new__(AppController)
    controller._backend = "unreal"
    sent_routes: list[dict] = []
    controller._unreal_link = SimpleNamespace(send_route=lambda payload: sent_routes.append(payload) or True)
    controller._unreal_uav_id = "sim"
    controller._latest_telemetry = _telemetry()
    saved_plans: list[list[tuple[float, float]]] = []
    controller._plan_vm = SimpleNamespace(save_plan=lambda path: saved_plans.append(list(path)))
    mission_state = {"confirmed_plan": []}

    def _confirm_plan(path: list[tuple[float, float]]) -> None:
        mission_state["confirmed_plan"] = list(path)

    controller._mission = SimpleNamespace(confirm_plan=_confirm_plan, confirmed_plan=[])
    controller._objects_store = _ObjectsStore()
    controller._target_tracker = SimpleNamespace(reset=lambda: None)
    controller._known_confirmed_ids = set()
    controller._pending_orbit_queue = []
    controller._pending_orbit_ids = set()
    controller._orbit_target_track_ids = set()
    controller._orbit_target_centers = []
    controller._reaction_target_id = None
    controller._unreal_local_telemetry_by_frame_id = {}
    controller._unreal_local_frame_order = deque()
    controller.planConfirmedChanged = _Signal()
    controller.flightControlsChanged = _Signal()
    controller.recoverableMissionChanged = _Signal()
    controller.toastRequested = _Signal()
    controller.map_bridge = SimpleNamespace(render_map=lambda: None)
    restored_homes: list[tuple[float, float]] = []
    controller._set_home_location = lambda lat, lon: restored_homes.append((lat, lon))
    scheduled: list[bool] = []
    controller._schedule_unreal_autostart = lambda: scheduled.append(True)
    emitted: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        main_window_module.bus,
        "emit",
        lambda event, payload=None: emitted.append((str(event), payload)),
    )
    main_window_module.deps.home_location = None
    main_window_module.deps.confirmed_objects = []
    main_window_module.deps.selected_object_id = None
    controller._recoverable_mission = RecoverableMissionSnapshot(
        path=[(47.6060, -122.3350), (47.6070, -122.3340)],
        home={"lat": 47.6055, "lon": -122.3360},
        confirmed_objects=[
            {
                "object_id": "track-1",
                "class_id": 1,
                "confidence": 0.83,
                "lat": 47.6063,
                "lon": -122.3347,
                "track_id": 11,
                "timestamp": _timestamp(),
            }
        ],
        selected_object_id="track-1",
    )

    controller.restoreRecoverableMission()

    assert saved_plans == [[(47.6060, -122.3350), (47.6070, -122.3340)]]
    assert mission_state["confirmed_plan"] == [(47.6060, -122.3350), (47.6070, -122.3340)]
    assert restored_homes == [(47.6055, -122.3360)]
    assert controller._objects_store.cleared == 1
    assert controller._objects_store.selected_ids == ["track-1"]
    assert any(event == str(Event.OBJECT_CONFIRMED_UI) for event, _payload in emitted)
    assert len(sent_routes) == 1
    assert sent_routes[0]["waypoints"][0]["lat"] == 47.6060
    assert scheduled == [True]
    assert controller._recoverable_mission is None
