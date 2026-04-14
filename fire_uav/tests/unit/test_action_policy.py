from fire_uav.services.mission.action_policy import MissionActionPolicy
from fire_uav.services.mission.active_path import ActivePathMode
from fire_uav.services.mission.state import MissionState


def test_orbit_actions_are_blocked_during_route_edit() -> None:
    policy = MissionActionPolicy.evaluate(
        mission_state=MissionState.IN_FLIGHT,
        link_ok=True,
        camera_ok=True,
        commands_enabled=True,
        has_confirmed_plan=True,
        active_path_mode=ActivePathMode.NORMAL,
        confirmed_object_count=1,
        selected_object_id="track-1",
        route_edit_mode=True,
        allow_unsafe_start=False,
        supports_waypoints=True,
        supports_orbit=True,
        supports_rtl=True,
        telemetry_available=True,
        at_home=False,
    )

    assert policy.can_open_orbit is False
    assert policy.can_orbit is False
