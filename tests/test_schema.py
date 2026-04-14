from __future__ import annotations

from datetime import datetime

from fire_uav.module_core.schema import GeoDetection, Route, TelemetrySample, Waypoint
from fire_uav.utils.time import utc_now


def test_telemetry_sample_creation() -> None:
    ts = TelemetrySample(
        lat=55.0,
        lon=37.0,
        alt=120.0,
        yaw=90.0,
        battery=0.75,
    )
    assert ts.lat == 55.0
    assert ts.alt_m == 120.0
    assert ts.yaw_deg == 90.0
    assert ts.battery == 0.75


def test_route_roundtrip() -> None:
    waypoints = [
        Waypoint(lat=55.0, lon=37.0, alt=120.0),
        Waypoint(lat=55.001, lon=37.001, alt=110.0),
    ]
    route = Route(version=1, waypoints=waypoints, active_index=0)
    # Pydantic model_dump / parse_obj roundtrip
    dumped = route.model_dump()
    restored = Route(**dumped)
    assert restored.version == route.version
    assert restored.active_index == 0
    assert len(restored.waypoints) == 2
    assert restored.waypoints[1].alt == 110.0
    assert restored.active_waypoint() == restored.waypoints[0]


def test_geo_detection_creation() -> None:
    now = utc_now()
    det = GeoDetection(
        class_id=1,
        confidence=0.9,
        lat=55.0,
        lon=37.0,
        alt=100.0,
        timestamp=now,
        frame_id="frame_001",
    )
    assert det.location.lat == 55.0
    assert det.captured_at == now
    assert det.frame_id == "frame_001"
