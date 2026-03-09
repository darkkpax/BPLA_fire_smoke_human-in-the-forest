from __future__ import annotations

import logging
from typing import Any, List

from fire_uav.config import settings as app_settings
from fire_uav.module_core.factories import get_energy_model
from fire_uav.module_core.interfaces.energy import EnergyInsufficientError, IEnergyModel
from fire_uav.module_core.interfaces.route_planner import IRoutePlanner
from fire_uav.module_core.route.maneuvers import build_maneuver, build_rejoin
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint, WorldCoord
from fire_uav.module_core.route.planner import build_route

log = logging.getLogger(__name__)


class PythonRoutePlanner(IRoutePlanner):
    """Route planner backed by the existing grid/coverage generator."""

    def __init__(self, *, energy_model: IEnergyModel | None = None, settings: Any | None = None) -> None:
        self.energy_model = energy_model or get_energy_model(app_settings)
        self.settings = settings or app_settings
        self.latest_telemetry: TelemetrySample | None = None

    def _resolve_base_location(
        self, route: Route, telemetry: TelemetrySample | None
    ) -> WorldCoord | None:
        for lat_key, lon_key in (("home_lat", "home_lon"), ("base_lat", "base_lon")):
            lat = getattr(self.settings, lat_key, None)
            lon = getattr(self.settings, lon_key, None)
            if lat is not None and lon is not None:
                try:
                    return WorldCoord(lat=float(lat), lon=float(lon))
                except (TypeError, ValueError):
                    pass

        if route.waypoints:
            wp = route.waypoints[0]
            return WorldCoord(lat=wp.lat, lon=wp.lon)

        if telemetry is not None:
            return WorldCoord(lat=telemetry.lat, lon=telemetry.lon)

        center = getattr(self.settings, "map_center", None)
        if isinstance(center, (list, tuple)) and len(center) >= 2:
            try:
                return WorldCoord(lat=float(center[0]), lon=float(center[1]))
            except (TypeError, ValueError):
                pass
        return None

    def plan_route(self, geom_wkt: str, gsd_cm: int | float = 0) -> Route:
        missions = build_route(geom_wkt, int(gsd_cm) if gsd_cm else 0, settings=self.settings)
        wps: List[Waypoint] = [
            Waypoint(lat=lat, lon=lon, alt=alt) for mission in missions for (lat, lon, alt) in mission
        ]
        route = Route(version=1, waypoints=wps, active_index=0 if wps else None)
        telemetry = self.latest_telemetry
        if telemetry is None:
            return route

        base_location = self._resolve_base_location(route, telemetry)
        if base_location is None:
            log.warning("EnergyModel: base location unavailable; allowing route without checks.")
            return route

        try:
            estimate = self.energy_model.estimate_route_feasibility(telemetry, route, base_location)
        except Exception as exc:  # noqa: BLE001
            log.warning("EnergyModel: feasibility estimate failed; allowing route (%s)", exc)
            return route

        if not estimate.can_complete:
            available = telemetry.battery_percent
            available_str = "unknown" if available is None else f"{available:.1f}%"
            msg = (
                "EnergyModel: route is not feasible with current battery "
                f"(required {estimate.required_percent:.1f}%, available {available_str})"
            )
            log.warning(msg)
            raise EnergyInsufficientError(msg)

        return route

    def plan_maneuver(
        self,
        current_state: TelemetrySample,
        target_lat: float,
        target_lon: float,
        base_route: Route,
    ) -> Route | None:
        return build_maneuver(
            current_state=current_state,
            target_lat=target_lat,
            target_lon=target_lon,
            base_route=base_route,
            energy_model=self.energy_model,
            settings=self.settings,
        )

    def plan_rejoin(self, exit_wp: Waypoint, base_route: Route) -> list[Waypoint]:
        return build_rejoin(exit_wp, base_route)


__all__ = ["PythonRoutePlanner"]
