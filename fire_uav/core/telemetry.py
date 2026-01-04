from __future__ import annotations

from datetime import datetime

from fire_uav.core.protocol import TelemetryMessage
from fire_uav.module_core.schema import TelemetrySample


def normalize_battery_value(battery: float | None) -> tuple[float, float | None]:
    if battery is None:
        return 1.0, None
    if battery <= 1.0:
        fraction = max(0.0, min(1.0, float(battery)))
        return fraction, fraction * 100.0
    percent = max(0.0, min(100.0, float(battery)))
    return percent / 100.0, percent


def coerce_battery_percent(battery: float, battery_percent: float | None) -> float | None:
    if battery_percent is None:
        return max(0.0, min(100.0, float(battery) * 100.0))
    return max(0.0, min(100.0, float(battery_percent)))


def telemetry_sample_from_message(msg: TelemetryMessage) -> TelemetrySample:
    battery_fraction, battery_percent = normalize_battery_value(getattr(msg, "battery", None))
    timestamp = getattr(msg, "timestamp", None) or datetime.utcnow()
    return TelemetrySample(
        lat=msg.lat,
        lon=msg.lon,
        alt=msg.alt,
        yaw=msg.yaw,
        battery=battery_fraction,
        battery_percent=battery_percent,
        timestamp=timestamp,
        pitch=0.0,
        roll=0.0,
        vx=None,
        vy=None,
        vz=None,
    )


__all__ = ["normalize_battery_value", "coerce_battery_percent", "telemetry_sample_from_message"]
