from fire_uav.services.mission.route_edit import dedupe_path, split_route_for_edit


def test_split_route_for_edit_returns_locked_prefix_and_remaining_tail() -> None:
    path = [
        (55.0000, 37.0000),
        (55.0005, 37.0005),
        (55.0010, 37.0010),
        (55.0015, 37.0015),
    ]
    anchor = (55.0007, 37.0007)

    locked, tail = split_route_for_edit(path, anchor)

    assert locked[0] == path[0]
    assert locked[-1] == anchor
    assert tail[0] == anchor
    assert tail[1:] == path[2:]


def test_split_route_for_edit_keeps_at_least_anchor_placeholder() -> None:
    path = [
        (55.0000, 37.0000),
        (55.0005, 37.0005),
    ]
    anchor = (55.0005, 37.0005)

    locked, tail = split_route_for_edit(path, anchor)

    assert locked[-1] == anchor
    assert tail == [anchor, anchor]


def test_dedupe_path_drops_consecutive_duplicates() -> None:
    points = [
        (55.0, 37.0),
        (55.0, 37.0),
        (55.0005, 37.0005),
    ]

    assert dedupe_path(points) == [(55.0, 37.0), (55.0005, 37.0005)]


def test_edit_route_split_keeps_original_plan_storage_untouched() -> None:
    from types import SimpleNamespace

    import fire_uav.infrastructure.providers as deps
    from fire_uav.gui.windows.main_window import AppController
    from fire_uav.module_core.schema import TelemetrySample
    from fire_uav.services.mission.state import MissionState
    from fire_uav.utils.time import utc_now

    class _Signal:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def emit(self, *args) -> None:
            self.calls.append(args)

    class _MapBridge:
        def __init__(self) -> None:
            self.render_count = 0

        def render_map(self) -> None:
            self.render_count += 1

    previous_plan = deps.plan_data
    previous_anchor = getattr(deps, "route_edit_anchor", None)
    previous_preview = getattr(deps, "route_edit_preview_path", None)
    previous_locked = getattr(deps, "route_edit_locked_path", None)
    previous_orbit = deps.debug_orbit_path
    previous_rtl = deps.rtl_path
    deps.plan_data = {
        "path": [(55.0000, 37.0000), (55.0005, 37.0005), (55.0010, 37.0010)],
        "path_kind": "mission",
    }
    deps.debug_orbit_path = None
    deps.rtl_path = None
    try:
        controller = AppController.__new__(AppController)
        controller._mission_state = MissionState.IN_FLIGHT
        controller._latest_telemetry = TelemetrySample(
            lat=55.0004,
            lon=37.0004,
            alt=120.0,
            yaw=0.0,
            pitch=0.0,
            roll=0.0,
            battery=0.9,
            battery_percent=90.0,
            timestamp=utc_now(),
        )
        controller._mission = SimpleNamespace(
            confirmed_plan=list(deps.plan_data["path"]),
        )
        controller._plan_vm = SimpleNamespace(get_path=lambda: list(deps.plan_data["path"]))
        controller._backend = "sim"
        controller._unreal_link = None
        controller.map_bridge = _MapBridge()
        controller.toastRequested = _Signal()
        controller.flightControlsChanged = _Signal()

        controller.editRoute()

        assert deps.plan_data["path"] == [
            (55.0000, 37.0000),
            (55.0005, 37.0005),
            (55.0010, 37.0010),
        ]
        assert getattr(deps, "route_edit_preview_path", None)
        assert controller.map_bridge.render_count == 1
    finally:
        deps.plan_data = previous_plan
        setattr(deps, "route_edit_anchor", previous_anchor)
        setattr(deps, "route_edit_preview_path", previous_preview)
        setattr(deps, "route_edit_locked_path", previous_locked)
        deps.debug_orbit_path = previous_orbit
        deps.rtl_path = previous_rtl
