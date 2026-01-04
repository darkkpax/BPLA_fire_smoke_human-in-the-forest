from __future__ import annotations

import logging

from fire_uav.core.telemetry import coerce_battery_percent
from fire_uav.module_core.geometry import haversine_m
from fire_uav.module_core.interfaces.energy import EnergyEstimate, IEnergyModel
from fire_uav.module_core.schema import Route, TelemetrySample, WorldCoord

log = logging.getLogger(__name__)


class PythonEnergyModel(IEnergyModel):
    """Simple cruise-based energy estimator."""

    def __init__(
        self,
        cruise_speed_mps: float = 12.0,
        power_cruise_w: float = 45.0,
        battery_wh: float = 27.0,
        max_flight_distance_m: float = 15000.0,
        min_return_percent: float = 20.0,
        critical_battery_percent: float = 10.0,
    ) -> None:
        self.cruise_speed_mps = cruise_speed_mps
        self.power_cruise_w = power_cruise_w
        self.battery_wh = battery_wh
        self.max_flight_distance_m = max_flight_distance_m
        self.min_return_percent = min_return_percent
        self.critical_battery_percent = critical_battery_percent

    def _route_distance_m(self, route: Route) -> float:
        distance = 0.0
        for prev, cur in zip(route.waypoints, route.waypoints[1:]):
            distance += haversine_m((prev.lat, prev.lon), (cur.lat, cur.lon))
        return distance

    def energy_cost(self, route: Route) -> float:
        distance = self._route_distance_m(route)
        if self.cruise_speed_mps <= 0:
            return float("inf")
        cruise_time_s = distance / self.cruise_speed_mps
        return cruise_time_s / 3600.0 * self.power_cruise_w

    def remaining_energy(self, telemetry: TelemetrySample) -> float:
        battery_fraction = max(0.0, min(1.0, telemetry.battery))
        return battery_fraction * self.battery_wh

    def estimate_route_feasibility(
        self,
        telemetry: TelemetrySample,
        route: Route,
        base_location: WorldCoord,
    ) -> EnergyEstimate:
        battery_percent = coerce_battery_percent(telemetry.battery, telemetry.battery_percent)

        if self.max_flight_distance_m <= 0:
            log.warning("EnergyModel: max_flight_distance_m invalid; allowing route without checks.")
            return EnergyEstimate(can_complete=True, required_percent=100.0, margin_percent=0.0)

        battery_percent = max(0.0, min(100.0, float(battery_percent)))
        route_length = self._route_distance_m(route)

        if route.waypoints:
            end_lat, end_lon = route.waypoints[-1].lat, route.waypoints[-1].lon
        else:
            end_lat, end_lon = telemetry.lat, telemetry.lon

        return_leg = haversine_m((end_lat, end_lon), (base_location.lat, base_location.lon))
        total_distance = route_length + return_leg
        required_percent = (total_distance / self.max_flight_distance_m) * 100.0
        reserved = max(0.0, self.min_return_percent)
        can_complete = battery_percent >= required_percent + reserved
        margin = battery_percent - (required_percent + reserved)
        return EnergyEstimate(
            can_complete=can_complete,
            required_percent=required_percent,
            margin_percent=margin,
        )

    def is_critical(self, telemetry: TelemetrySample) -> bool:
        """
        Return True if battery is at or below critical threshold.
        If telemetry.battery_percent is None, return False.
        """
        if telemetry.battery_percent is None:
            return False
        return float(telemetry.battery_percent) <= float(self.critical_battery_percent)


__all__ = ["PythonEnergyModel"]
