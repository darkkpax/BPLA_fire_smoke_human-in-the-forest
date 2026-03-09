from __future__ import annotations

from datetime import datetime

from fire_uav.module_core.energy.python_energy_model import PythonEnergyModel
from fire_uav.module_core.interfaces.energy import EnergyEstimate
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint, WorldCoord


def test_python_energy_model_uses_derived_range_when_configured_distance_disabled() -> None:
    model = PythonEnergyModel(
        cruise_speed_mps=10.0,
        power_cruise_w=100.0,
        battery_wh=50.0,
        max_flight_distance_m=0.0,
        min_return_percent=20.0,
    )
    telemetry = TelemetrySample(
        lat=56.0,
        lon=92.9,
        alt=100.0,
        yaw=0.0,
        battery=0.5,
        battery_percent=50.0,
        timestamp=datetime.utcnow(),
    )
    route = Route(
        version=1,
        active_index=0,
        waypoints=[
            Waypoint(lat=56.0, lon=92.9, alt=100.0),
            Waypoint(lat=56.0, lon=92.918, alt=100.0),
        ],
    )

    estimate = model.estimate_route_feasibility(
        telemetry,
        route,
        WorldCoord(lat=56.0, lon=92.9),
    )

    assert isinstance(estimate, EnergyEstimate)
    assert model.max_range_m() > 0.0
    assert estimate.required_percent > 0.0
