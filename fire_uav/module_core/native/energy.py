from __future__ import annotations

import logging

from fire_uav.core.telemetry import coerce_battery_percent
from fire_uav.module_core.geometry import haversine_m
from fire_uav.module_core.interfaces.energy import EnergyEstimate, IEnergyModel
from fire_uav.module_core.native import NATIVE_AVAILABLE, _native_core
from fire_uav.module_core.schema import Route, TelemetrySample, WorldCoord

log = logging.getLogger(__name__)


BATTERY_WH_PLACEHOLDER = 100.0  # TODO: pull from platform config or UAV telemetry


if NATIVE_AVAILABLE:

    class NativeEnergyModel(IEnergyModel):
        """Native-backed energy estimator."""

        def __init__(
            self,
            *,
            max_flight_distance_m: float = 15000.0,
            min_return_percent: float = 20.0,
            critical_battery_percent: float = 10.0,
        ) -> None:
            self.max_flight_distance_m = max_flight_distance_m
            self.min_return_percent = min_return_percent
            self.critical_battery_percent = critical_battery_percent

        def energy_cost(self, route: Route) -> float:
            lats = [wp.lat for wp in route.waypoints]
            lons = [wp.lon for wp in route.waypoints]
            alts = [wp.alt for wp in route.waypoints]
            return float(_native_core.route_energy_cost(lats, lons, alts, 1.0, 1.0))

        def remaining_energy(self, telemetry: TelemetrySample) -> float:
            remaining = telemetry.battery * BATTERY_WH_PLACEHOLDER
            # TODO: refine with actual battery telemetry metrics.
            return float(remaining)

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
            distance = 0.0
            for prev, cur in zip(route.waypoints, route.waypoints[1:]):
                distance += haversine_m((prev.lat, prev.lon), (cur.lat, cur.lon))

            if route.waypoints:
                end_lat, end_lon = route.waypoints[-1].lat, route.waypoints[-1].lon
            else:
                end_lat, end_lon = telemetry.lat, telemetry.lon

            return_leg = haversine_m((end_lat, end_lon), (base_location.lat, base_location.lon))
            total_distance = distance + return_leg
            required_percent = (total_distance / self.max_flight_distance_m) * 100.0
            reserved = max(0.0, self.min_return_percent)
            can_complete = battery_percent >= required_percent + reserved
            margin = battery_percent - (required_percent + reserved)
            return EnergyEstimate(
                can_complete=can_complete,
                required_percent=required_percent,
                margin_percent=margin,
            )

else:

    class NativeEnergyModel(IEnergyModel):  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise RuntimeError("Native core is not available. Build the C++ extension or disable native usage.")

        def energy_cost(self, route: Route) -> float:
            raise RuntimeError("Native core is not available.")

        def remaining_energy(self, telemetry: TelemetrySample) -> float:
            raise RuntimeError("Native core is not available.")

        def estimate_route_feasibility(
            self,
            telemetry: TelemetrySample,
            route: Route,
            base_location: WorldCoord,
        ) -> EnergyEstimate:
            raise RuntimeError("Native core is not available.")


__all__ = ["NativeEnergyModel", "BATTERY_WH_PLACEHOLDER"]
