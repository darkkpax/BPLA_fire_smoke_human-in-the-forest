from __future__ import annotations

from fire_uav.core.protocol import TelemetryMessage
from fire_uav.module_core.schema import TelemetrySample
from fire_uav.utils.time import utc_now


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
    timestamp = getattr(msg, "timestamp", None) or utc_now()
    return TelemetrySample(
        lat=msg.lat,
        lon=msg.lon,
        alt=msg.alt,
        alt_agl=getattr(msg, "alt_agl", None),
        yaw=msg.yaw if msg.yaw is not None else 0.0,
        pitch=msg.pitch if getattr(msg, "pitch", None) is not None else 0.0,
        roll=msg.roll if getattr(msg, "roll", None) is not None else 0.0,
        battery=battery_fraction,
        battery_percent=battery_percent,
        status=getattr(msg, "status", None),
        flight_mode=getattr(msg, "flight_mode", None),
        camera_mount_pitch_deg=getattr(msg, "camera_mount_pitch_deg", None),
        camera_mount_yaw_deg=getattr(msg, "camera_mount_yaw_deg", None),
        camera_mount_roll_deg=getattr(msg, "camera_mount_roll_deg", None),
        timestamp=timestamp,
        vx=None,
        vy=None,
        vz=None,
    )


__all__ = ["normalize_battery_value", "coerce_battery_percent", "telemetry_sample_from_message"]
