from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List

from fire_uav.module_core.geometry import haversine_m, offset_latlon
from fire_uav.module_core.interfaces.energy import IEnergyModel
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint, WorldCoord

log = logging.getLogger(__name__)


@dataclass(slots=True)
class OrbitParams:
    radius_m: float
    altitude_m: float
    points_per_circle: int
    loops: int


def _as_waypoint(current: TelemetrySample | Waypoint, *, alt: float | None = None) -> Waypoint:
    if isinstance(current, Waypoint):
        return current
    return Waypoint(lat=current.lat, lon=current.lon, alt=alt if alt is not None else current.alt)


def build_orbit(
    target_lat: float,
    target_lon: float,
    radius_m: float,
    altitude_m: float,
    points_per_circle: int,
    loops: int,
) -> List[Waypoint]:
    steps = max(3, points_per_circle)
    result: List[Waypoint] = []
    total = loops * steps
    for i in range(total):
        angle = 2 * math.pi * (i / steps)
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        lat, lon = offset_latlon(target_lat, target_lon, dx, dy)
        result.append(Waypoint(lat=lat, lon=lon, alt=altitude_m))
    return result


def _build_orbit_arc(
    target_lat: float,
    target_lon: float,
    radius_m: float,
    altitude_m: float,
    points_per_circle: int,
    total_angle_deg: float,
) -> List[Waypoint]:
    steps = max(3, int(points_per_circle * max(0.1, total_angle_deg / 360.0)))
    total_angle_rad = math.radians(max(0.0, total_angle_deg))
    result: List[Waypoint] = []
    for i in range(steps + 1):
        angle = total_angle_rad * (i / steps)
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        lat, lon = offset_latlon(target_lat, target_lon, dx, dy)
        result.append(Waypoint(lat=lat, lon=lon, alt=altitude_m))
    return result


def _resolve_base_location(
    settings,
    base_route: Route,
    current_state: TelemetrySample,
) -> WorldCoord:
    for lat_key, lon_key in (("home_lat", "home_lon"), ("base_lat", "base_lon")):
        lat = getattr(settings, lat_key, None)
        lon = getattr(settings, lon_key, None)
        if lat is not None and lon is not None:
            try:
                return WorldCoord(lat=float(lat), lon=float(lon))
            except (TypeError, ValueError):
                pass

    if base_route.waypoints:
        wp = base_route.waypoints[0]
        return WorldCoord(lat=wp.lat, lon=wp.lon)

    if math.isfinite(float(current_state.lat)) and math.isfinite(float(current_state.lon)):
        return WorldCoord(lat=current_state.lat, lon=current_state.lon)

    center = getattr(settings, "map_center", None)
    if isinstance(center, (list, tuple)) and len(center) >= 2:
        try:
            return WorldCoord(lat=float(center[0]), lon=float(center[1]))
        except (TypeError, ValueError):
            pass

    return WorldCoord(lat=current_state.lat, lon=current_state.lon)


def build_approach(current_pos: TelemetrySample | Waypoint, entry_wp: Waypoint) -> List[Waypoint]:
    start = _as_waypoint(current_pos, alt=entry_wp.alt)
    if haversine_m((start.lat, start.lon), (entry_wp.lat, entry_wp.lon)) < 0.5:
        return [entry_wp]
    return [start, entry_wp]


def build_rejoin(exit_wp: Waypoint, base_route: Route) -> List[Waypoint]:
    if not base_route.waypoints:
        return []

    start_idx = 0
    if base_route.active_index is not None:
        start_idx = max(0, min(int(base_route.active_index), len(base_route.waypoints) - 1))

    closest_idx = start_idx
    closest_dist = float("inf")
    for idx in range(start_idx, len(base_route.waypoints)):
        wp = base_route.waypoints[idx]
        dist = haversine_m((exit_wp.lat, exit_wp.lon), (wp.lat, wp.lon))
        if dist < closest_dist:
            closest_dist = dist
            closest_idx = idx

    path = list(base_route.waypoints[closest_idx:])
    return path


def build_energy_aware_orbit(
    *,
    current_state: TelemetrySample,
    target_lat: float,
    target_lon: float,
    base_route: Route,
    base_location: WorldCoord,
    energy_model: IEnergyModel,
    orbit_params: OrbitParams,
) -> Route | None:
    preview_orbit = _build_orbit_arc(
        target_lat,
        target_lon,
        orbit_params.radius_m,
        orbit_params.altitude_m,
        orbit_params.points_per_circle,
        360.0 * max(1, orbit_params.loops),
    )
    entry_wp = preview_orbit[0] if preview_orbit else Waypoint(
        lat=target_lat,
        lon=target_lon,
        alt=orbit_params.altitude_m,
    )
    approach = build_approach(current_state, entry_wp)

    def _assemble_route(orbit: List[Waypoint]) -> Route:
        exit_wp = orbit[-1] if orbit else entry_wp
        rejoin_path = build_rejoin(exit_wp, base_route)
        waypoints = approach + orbit + rejoin_path
        return Route(
            version=base_route.version if base_route.version is not None else 1,
            waypoints=waypoints,
            active_index=0 if waypoints else None,
        )

    def _is_feasible(route: Route) -> bool:
        try:
            estimate = energy_model.estimate_route_feasibility(current_state, route, base_location)
            return estimate.can_complete
        except Exception as exc:  # noqa: BLE001
            log.warning("EnergyModel: orbit feasibility failed; allowing maneuver (%s)", exc)
            return True

    total_angle_deg = 360.0 * max(1, orbit_params.loops)
    orbit = _build_orbit_arc(
        target_lat,
        target_lon,
        orbit_params.radius_m,
        orbit_params.altitude_m,
        orbit_params.points_per_circle,
        total_angle_deg,
    )
    route = _assemble_route(orbit)
    if _is_feasible(route):
        return route

    reduced_angles: list[float] = []
    if orbit_params.loops > 1:
        for loops in range(orbit_params.loops - 1, 0, -1):
            reduced_angles.append(360.0 * loops)
    reduced_angles.extend([180.0, 90.0])

    for angle in reduced_angles:
        orbit = _build_orbit_arc(
            target_lat,
            target_lon,
            orbit_params.radius_m,
            orbit_params.altitude_m,
            orbit_params.points_per_circle,
            angle,
        )
        candidate = _assemble_route(orbit)
        if _is_feasible(candidate):
            log.warning("EnergyModel: reduced orbit to %.0f deg to fit remaining battery.", angle)
            return candidate

    log.warning("EnergyModel: insufficient battery for orbit maneuver.")
    return None


def build_maneuver(
    current_state: TelemetrySample,
    target_lat: float,
    target_lon: float,
    base_route: Route,
    energy_model: IEnergyModel,
    settings,
) -> Route | None:
    raw_altitude = getattr(settings, "maneuver_alt_m", None)
    try:
        altitude = float(raw_altitude) if raw_altitude is not None else float(current_state.alt)
    except (TypeError, ValueError):
        altitude = float(current_state.alt)
    altitude = max(0.0, altitude)

    try:
        radius = max(1.0, float(getattr(settings, "orbit_radius_m", 50.0) or 50.0))
    except (TypeError, ValueError):
        radius = 50.0
    try:
        points_per_circle = max(3, int(getattr(settings, "orbit_points_per_circle", 12) or 12))
    except (TypeError, ValueError):
        points_per_circle = 12
    try:
        loops = max(1, int(getattr(settings, "orbit_loops", 1) or 1))
    except (TypeError, ValueError):
        loops = 1
    orbit_params = OrbitParams(
        radius_m=radius,
        altitude_m=altitude,
        points_per_circle=points_per_circle,
        loops=loops,
    )
    base_location = _resolve_base_location(settings, base_route, current_state)
    return build_energy_aware_orbit(
        current_state=current_state,
        target_lat=target_lat,
        target_lon=target_lon,
        base_route=base_route,
        base_location=base_location,
        energy_model=energy_model,
        orbit_params=orbit_params,
    )


__all__ = [
    "build_orbit",
    "build_approach",
    "build_rejoin",
    "build_energy_aware_orbit",
    "build_maneuver",
    "OrbitParams",
]
