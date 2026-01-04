from __future__ import annotations

from dataclasses import dataclass

from fire_uav.services.mission.active_path import ActivePathMode
from fire_uav.services.mission.state import MissionState


@dataclass(frozen=True)
class MissionActionPolicy:
    can_confirm_plan: bool
    can_start_flight: bool
    can_edit_route: bool
    can_apply_route_edits: bool
    can_orbit: bool
    can_rtl: bool
    can_send_rtl_route: bool
    can_complete_landing: bool
    can_abort_to_preflight: bool

    @classmethod
    def evaluate(
        cls,
        *,
        mission_state: MissionState,
        link_ok: bool,
        camera_ok: bool,
        commands_enabled: bool,
        has_confirmed_plan: bool,
        active_path_mode: ActivePathMode,
        confirmed_object_count: int,
        selected_object_id: str | None,
        route_edit_mode: bool,
        allow_unsafe_start: bool,
        supports_waypoints: bool,
        supports_orbit: bool,
        supports_rtl: bool,
    ) -> "MissionActionPolicy":
        can_confirm_plan = (
            mission_state in (MissionState.PREFLIGHT, MissionState.READY)
            and not has_confirmed_plan
            and supports_waypoints
        )
        can_start_flight = (
            mission_state in (MissionState.PREFLIGHT, MissionState.READY)
            and has_confirmed_plan
            and (allow_unsafe_start or (link_ok and camera_ok))
        )
        can_edit_route = (
            mission_state == MissionState.IN_FLIGHT
            and commands_enabled
            and active_path_mode == ActivePathMode.NORMAL
            and supports_waypoints
        )
        can_apply_route_edits = (
            mission_state == MissionState.IN_FLIGHT
            and commands_enabled
            and route_edit_mode
            and active_path_mode == ActivePathMode.NORMAL
            and supports_waypoints
        )
        can_orbit = (
            mission_state == MissionState.IN_FLIGHT
            and commands_enabled
            and camera_ok
            and confirmed_object_count > 0
            and (confirmed_object_count == 1 or selected_object_id is not None)
            and supports_orbit
        )
        can_rtl = mission_state == MissionState.IN_FLIGHT and commands_enabled and link_ok and supports_rtl
        can_send_rtl_route = mission_state == MissionState.RTL and link_ok and supports_waypoints
        can_complete_landing = mission_state == MissionState.RTL
        can_abort_to_preflight = mission_state in (MissionState.IN_FLIGHT, MissionState.RTL)
        return cls(
            can_confirm_plan=can_confirm_plan,
            can_start_flight=can_start_flight,
            can_edit_route=can_edit_route,
            can_apply_route_edits=can_apply_route_edits,
            can_orbit=can_orbit,
            can_rtl=can_rtl,
            can_send_rtl_route=can_send_rtl_route,
            can_complete_landing=can_complete_landing,
            can_abort_to_preflight=can_abort_to_preflight,
        )


__all__ = ["MissionActionPolicy"]
