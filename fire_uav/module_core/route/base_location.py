from __future__ import annotations

import math

from fire_uav.module_core.geometry import haversine_m
from fire_uav.module_core.schema import Route, TelemetrySample, WorldCoord

STALE_BASE_DISTANCE_M = 5_000.0


def _world_coord(lat: object, lon: object) -> WorldCoord | None:
    if lat is None or lon is None:
        return None
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat_f) and math.isfinite(lon_f)):
        return None
    return WorldCoord(lat=lat_f, lon=lon_f)


def _is_stale_candidate(
    candidate: WorldCoord,
    *,
    route: Route,
    telemetry: TelemetrySample | None,
) -> bool:
    anchors: list[tuple[float, float]] = []
    if route.waypoints:
        start = route.waypoints[0]
        anchors.append((start.lat, start.lon))
    if telemetry is not None:
        anchors.append((telemetry.lat, telemetry.lon))
    if not anchors:
        return False
    min_distance = min(haversine_m((candidate.lat, candidate.lon), anchor) for anchor in anchors)
    return min_distance > STALE_BASE_DISTANCE_M


def resolve_base_location(
    settings,
    route: Route,
    telemetry: TelemetrySample | None,
) -> WorldCoord | None:
    for lat_key, lon_key in (("home_lat", "home_lon"), ("base_lat", "base_lon")):
        candidate = _world_coord(getattr(settings, lat_key, None), getattr(settings, lon_key, None))
        if candidate is not None and not _is_stale_candidate(candidate, route=route, telemetry=telemetry):
            return candidate

    if route.waypoints:
        wp = route.waypoints[0]
        return WorldCoord(lat=wp.lat, lon=wp.lon)

    if telemetry is not None:
        return WorldCoord(lat=telemetry.lat, lon=telemetry.lon)

    center = getattr(settings, "map_center", None)
    if isinstance(center, (list, tuple)) and len(center) >= 2:
        return _world_coord(center[0], center[1])

    return None


__all__ = ["STALE_BASE_DISTANCE_M", "resolve_base_location"]
