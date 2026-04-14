from __future__ import annotations

from datetime import datetime
import json

from fire_uav.api.ws_stream import _json_default
from fire_uav.core.protocol import TelemetryMessage
from fire_uav.core.telemetry import (
    coerce_battery_percent,
    normalize_battery_value,
    telemetry_sample_from_message,
)
from fire_uav.module_core.energy.python_energy_model import PythonEnergyModel
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint, WorldCoord
from fire_uav.utils.time import utc_now


def test_normalize_battery_value_fraction() -> None:
    fraction, percent = normalize_battery_value(0.5)
    assert fraction == 0.5
    assert percent == 50.0


def test_normalize_battery_value_percent() -> None:
    fraction, percent = normalize_battery_value(75.0)
    assert fraction == 0.75
    assert percent == 75.0


def test_telemetry_sample_from_message() -> None:
    msg = TelemetryMessage(
        uav_id="test",
        timestamp=utc_now(),
        lat=55.0,
        lon=37.0,
        alt=120.0,
        yaw=90.0,
        battery=80.0,
    )
    sample = telemetry_sample_from_message(msg)
    assert sample.battery == 0.8
    assert sample.battery_percent == 80.0


def test_coerce_battery_percent() -> None:
    assert coerce_battery_percent(0.4, None) == 40.0
    assert coerce_battery_percent(0.4, 55.0) == 55.0


def test_energy_model_fallback_percent() -> None:
    model = PythonEnergyModel(max_flight_distance_m=1000.0, min_return_percent=0.0)
    telemetry = TelemetrySample(
        lat=55.0,
        lon=37.0,
        alt=120.0,
        yaw=0.0,
        battery=0.5,
        battery_percent=None,
    )
    route = Route(
        version=1,
        waypoints=[
            Waypoint(lat=55.0, lon=37.0, alt=120.0),
            Waypoint(lat=55.0005, lon=37.0005, alt=120.0),
        ],
    )
    base = WorldCoord(lat=55.0, lon=37.0)
    estimate = model.estimate_route_feasibility(telemetry, route, base)
    assert estimate.required_percent >= 0.0
    assert estimate.can_complete


def test_ws_json_default_handles_datetime() -> None:
    msg = TelemetryMessage(
        uav_id="test",
        timestamp=utc_now(),
        lat=55.0,
        lon=37.0,
        alt=120.0,
        yaw=90.0,
        battery=0.8,
    )
    payload = {"msg": msg, "ts": utc_now()}
    encoded = json.dumps(payload, default=_json_default)
    assert '"telemetry"' in encoded
    assert '"timestamp"' in encoded
