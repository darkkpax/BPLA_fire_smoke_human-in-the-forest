from __future__ import annotations

from types import SimpleNamespace

from fire_uav.module_core.route.base_location import resolve_base_location
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint
from fire_uav.utils.time import utc_now


def _route(*points: tuple[float, float]) -> Route:
    return Route(
        version=1,
        active_index=0 if points else None,
        waypoints=[Waypoint(lat=lat, lon=lon, alt=120.0) for lat, lon in points],
    )


def _telemetry(lat: float, lon: float) -> TelemetrySample:
    return TelemetrySample(
        lat=lat,
        lon=lon,
        alt=120.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.8,
        battery_percent=80.0,
        timestamp=utc_now(),
    )


def test_resolve_base_location_prefers_nearby_home() -> None:
    settings = SimpleNamespace(
        home_lat=47.6061,
        home_lon=-122.3349,
        base_lat=55.75,
        base_lon=37.61,
        map_center=[56.02, 92.9],
    )

    resolved = resolve_base_location(
        settings,
        _route((47.6060, -122.3350), (47.6070, -122.3340)),
        _telemetry(47.6062, -122.3348),
    )

    assert resolved is not None
    assert resolved.lat == 47.6061
    assert resolved.lon == -122.3349


def test_resolve_base_location_ignores_stale_home_and_uses_route_start() -> None:
    settings = SimpleNamespace(
        home_lat=56.0153,
        home_lon=92.8932,
        base_lat=56.0200,
        base_lon=92.9100,
        map_center=[56.02, 92.9],
    )

    resolved = resolve_base_location(
        settings,
        _route((47.6060, -122.3350), (47.6070, -122.3340)),
        _telemetry(47.6062, -122.3348),
    )

    assert resolved is not None
    assert resolved.lat == 47.6060
    assert resolved.lon == -122.3350


def test_resolve_base_location_falls_back_to_telemetry_without_route() -> None:
    settings = SimpleNamespace(
        home_lat=None,
        home_lon=None,
        base_lat=None,
        base_lon=None,
        map_center=[56.02, 92.9],
    )

    resolved = resolve_base_location(settings, _route(), _telemetry(47.6062, -122.3348))

    assert resolved is not None
    assert resolved.lat == 47.6062
    assert resolved.lon == -122.3348


def test_resolve_base_location_uses_map_center_as_last_fallback() -> None:
    settings = SimpleNamespace(
        home_lat=None,
        home_lon=None,
        base_lat=None,
        base_lon=None,
        map_center=[56.02, 92.9],
    )

    resolved = resolve_base_location(settings, _route(), None)

    assert resolved is not None
    assert resolved.lat == 56.02
    assert resolved.lon == 92.9
