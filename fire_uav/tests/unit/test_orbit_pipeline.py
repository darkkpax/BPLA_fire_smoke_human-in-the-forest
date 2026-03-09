from __future__ import annotations

import sys
import time
from datetime import datetime
from types import SimpleNamespace
from types import ModuleType

_debug_sim_stub = ModuleType("fire_uav.services.debug_sim")
_debug_sim_stub.DebugSimulationService = object
sys.modules.setdefault("fire_uav.services.debug_sim", _debug_sim_stub)

from fire_uav.gui.windows.main_window import AppController, OrbitFlowState
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint
from fire_uav.services.mission.state import MissionState
from fire_uav.services.objects_store import ConfirmedObject


class _Signal:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def emit(self, *args) -> None:
        self.calls.append(args)


class _Planner:
    def __init__(self, route: Route | None) -> None:
        self._route = route
        self.calls: list[tuple[float, float]] = []

    def plan_maneuver(
        self,
        *,
        current_state: TelemetrySample,
        target_lat: float,
        target_lon: float,
        base_route: Route,
    ) -> Route | None:
        self.calls.append((target_lat, target_lon))
        return self._route


class _UnrealLink:
    def __init__(self, *, send_route_ok: bool = True) -> None:
        self.send_route_ok = send_route_ok
        self.commands: list[tuple[str, dict | None]] = []
        self.routes: list[dict] = []

    def send_command(self, command: str, payload: dict | None = None) -> bool:
        self.commands.append((command, payload))
        return True

    def send_route(self, route: dict) -> bool:
        self.routes.append(route)
        return self.send_route_ok


class _MapBridge:
    def __init__(self) -> None:
        self.render_count = 0

    def render_map(self) -> None:
        self.render_count += 1


class _ActivePath:
    def __init__(self) -> None:
        self.mode = "NORMAL"
        self.orbit_paths: list[list[tuple[float, float]]] = []
        self.normal_count = 0

    def set_orbit(self, pts: list[tuple[float, float]] | None) -> None:
        self.mode = "ORBIT" if pts else "NORMAL"
        self.orbit_paths.append(list(pts or []))

    def set_normal(self) -> None:
        self.mode = "NORMAL"
        self.normal_count += 1


class _TargetTracker:
    def __init__(self) -> None:
        self.in_orbit: list[int] = []
        self.orbited: list[int] = []
        self.zones: list[tuple[float, float]] = []

    def mark_in_orbit(self, track_id: int) -> bool:
        self.in_orbit.append(track_id)
        return True

    def mark_orbited(self, track_id: int) -> bool:
        self.orbited.append(track_id)
        return True

    def add_suppression_zone(self, *, lat: float, lon: float) -> None:
        self.zones.append((lat, lon))


class _ObjectsStore:
    def __init__(self, target: ConfirmedObject) -> None:
        self._target = target

    def get(self, object_id: str) -> ConfirmedObject | None:
        if object_id == self._target.object_id:
            return self._target
        return None

    def latest(self) -> ConfirmedObject:
        return self._target


def _telemetry() -> TelemetrySample:
    return TelemetrySample(
        lat=47.6060,
        lon=-122.3350,
        alt=120.0,
        alt_agl=20.0,
        yaw=90.0,
        pitch=0.0,
        roll=0.0,
        battery=0.97,
        battery_percent=97.0,
        timestamp=datetime.utcnow(),
    )


def _confirmed_target() -> ConfirmedObject:
    return ConfirmedObject(
        object_id="track-1",
        class_id=1,
        confidence=0.9,
        lat=47.6065,
        lon=-122.3345,
        track_id=11,
        timestamp=datetime.utcnow(),
    )


def _orbit_route() -> Route:
    return Route(
        version=1,
        active_index=0,
        waypoints=[
            Waypoint(lat=47.6061, lon=-122.3349, alt=120.0),
            Waypoint(lat=47.6065, lon=-122.3341, alt=120.0),
            Waypoint(lat=47.6070, lon=-122.3340, alt=120.0),
        ],
    )


def _build_controller(*, planner_route: Route | None, send_route_ok: bool = True) -> tuple[AppController, _UnrealLink]:
    controller = AppController.__new__(AppController)
    controller._mission_state = MissionState.IN_FLIGHT
    controller._commands_enabled = True
    controller._latest_telemetry = _telemetry()
    controller._backend = "unreal"
    controller._unreal_uav_id = "sim"
    controller._unreal_link = _UnrealLink(send_route_ok=send_route_ok)
    controller._plan_vm = SimpleNamespace(
        _route_planner=_Planner(planner_route),
        get_path=lambda: [(47.6060, -122.3350), (47.6070, -122.3340)],
    )
    controller._mission = SimpleNamespace(confirmed_plan=[(47.6060, -122.3350), (47.6070, -122.3340)])
    controller._reaction_target_id = None
    controller._reaction_started_monotonic = 0.0
    controller._reaction_speed_override_active = False
    controller._orbit_active = False
    controller._orbit_rejoin_wp = None
    controller._orbit_rejoin_close_hits = 0
    controller._orbit_rejoin_threshold_m = 15.0
    controller._orbit_target_track_ids = set()
    controller._orbit_target_centers = []
    controller._orbit_flow_state = OrbitFlowState.NORMAL_FLIGHT
    controller._pending_orbit_queue = []
    controller._pending_orbit_ids = set()
    controller._auto_orbit_enabled = False
    controller._reaction_window_s = 0.01
    controller._reaction_slow_speed_mps = 1.0
    controller._active_path = _ActivePath()
    controller._target_tracker = _TargetTracker()
    controller._objects_store = _ObjectsStore(_confirmed_target())
    controller.toastRequested = _Signal()
    controller.map_bridge = _MapBridge()
    controller._emit_warning = lambda **kwargs: None
    return controller, controller._unreal_link


def test_manual_orbit_pipeline_sends_route_and_enters_orbit() -> None:
    controller, unreal = _build_controller(planner_route=_orbit_route())
    target = _confirmed_target()

    controller._orbit_targets([target], source="manual")

    assert len(unreal.routes) == 1
    assert unreal.routes[0]["orbit_target"]["lat"] == target.lat
    assert unreal.routes[0]["orbit_target"]["lon"] == target.lon
    assert ("RESUME", None) in unreal.commands
    assert controller._orbit_active is True
    assert controller._orbit_flow_state == OrbitFlowState.ORBIT_ACTIVE
    assert controller._active_path.mode == "ORBIT"
    assert controller._reaction_speed_override_active is False
    assert controller._target_tracker.in_orbit == [11]


def test_auto_orbit_failure_recovers_from_slowdown() -> None:
    controller, unreal = _build_controller(planner_route=None)
    target = _confirmed_target()
    controller._auto_orbit_enabled = True

    controller._start_reaction_window(target)
    controller._objects_store = _ObjectsStore(target)
    controller._reaction_started_monotonic = time.monotonic() - 1.0
    controller._tick_reaction_window()

    assert ("SET_SPEED", {"speed_mps": float(controller._reaction_slow_speed_mps)}) in unreal.commands
    assert any(cmd == "CLEAR_VELOCITY_OVERRIDE" for cmd, _ in unreal.commands)
    assert controller._reaction_speed_override_active is False
    assert controller._orbit_active is False
    assert controller._orbit_flow_state == OrbitFlowState.NORMAL_FLIGHT


def test_failed_route_send_does_not_leave_orbit_or_slowdown_active() -> None:
    controller, unreal = _build_controller(planner_route=_orbit_route(), send_route_ok=False)
    target = _confirmed_target()
    controller._reaction_speed_override_active = True

    controller._orbit_targets([target], source="manual")

    assert len(unreal.routes) == 1
    assert any(cmd == "CLEAR_VELOCITY_OVERRIDE" for cmd, _ in unreal.commands)
    assert controller._reaction_speed_override_active is False
    assert controller._orbit_active is False
    assert controller._orbit_flow_state == OrbitFlowState.NORMAL_FLIGHT
    assert controller._active_path.mode == "NORMAL"


def test_orbit_rejoin_stops_orbit_and_restores_normal_path() -> None:
    controller, unreal = _build_controller(planner_route=_orbit_route())
    target = _confirmed_target()
    controller._orbit_targets([target], source="manual")
    controller._orbit_rejoin_wp = Waypoint(lat=47.6070, lon=-122.3340, alt=120.0)

    near_rejoin = TelemetrySample(
        lat=47.6070,
        lon=-122.3340,
        alt=120.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.9,
        battery_percent=90.0,
        timestamp=datetime.utcnow(),
    )

    controller._maybe_restore_route_after_orbit(near_rejoin)
    controller._maybe_restore_route_after_orbit(near_rejoin)

    assert any(cmd == "ORBIT_STOP" for cmd, _ in unreal.commands)
    assert controller._orbit_active is False
    assert controller._orbit_flow_state == OrbitFlowState.NORMAL_FLIGHT
    assert controller._active_path.mode == "NORMAL"
    assert controller._target_tracker.orbited == [11]
