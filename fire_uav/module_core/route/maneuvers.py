from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List

from fire_uav.module_core.geometry import haversine_m, offset_latlon
from fire_uav.module_core.interfaces.energy import IEnergyModel
from fire_uav.module_core.route.base_location import resolve_base_location
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
    resolved = resolve_base_location(settings, base_route, current_state)
    if resolved is not None:
        return resolved
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

    if start_idx >= len(base_route.waypoints) - 1:
        return [base_route.waypoints[start_idx]]

    def _to_local_m(lat: float, lon: float) -> tuple[float, float]:
        scale_lat = 111_320.0
        scale_lon = 111_320.0 * math.cos(math.radians(float(exit_wp.lat)))
        return (
            (float(lon) - float(exit_wp.lon)) * scale_lon,
            (float(lat) - float(exit_wp.lat)) * scale_lat,
        )

    best_point: Waypoint | None = None
    best_suffix_start = start_idx
    best_dist = float("inf")

    for idx in range(start_idx, len(base_route.waypoints) - 1):
        start_wp = base_route.waypoints[idx]
        end_wp = base_route.waypoints[idx + 1]
        sx, sy = _to_local_m(start_wp.lat, start_wp.lon)
        ex, ey = _to_local_m(end_wp.lat, end_wp.lon)
        dx = ex - sx
        dy = ey - sy
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 1e-6:
            candidates = (
                (start_wp, idx),
                (end_wp, idx + 1),
            )
        else:
            t = max(0.0, min(1.0, (-(sx * dx + sy * dy)) / seg_len_sq))
            candidates = (
                (
                    Waypoint(
                        lat=float(start_wp.lat) + (float(end_wp.lat) - float(start_wp.lat)) * t,
                        lon=float(start_wp.lon) + (float(end_wp.lon) - float(start_wp.lon)) * t,
                        alt=float(start_wp.alt) + (float(end_wp.alt) - float(start_wp.alt)) * t,
                    ),
                    idx + 1 if t > 1e-3 else idx,
                ),
            )

        for candidate, suffix_start in candidates:
            dist = haversine_m((exit_wp.lat, exit_wp.lon), (candidate.lat, candidate.lon))
            if dist < best_dist:
                best_dist = dist
                best_point = candidate
                best_suffix_start = suffix_start

    if best_point is None:
        return list(base_route.waypoints[start_idx:])

    suffix = list(base_route.waypoints[best_suffix_start:])
    if suffix and haversine_m((best_point.lat, best_point.lon), (suffix[0].lat, suffix[0].lon)) <= 0.5:
        return suffix
    return [best_point, *suffix]


def build_energy_aware_orbit(
    *,
    current_state: TelemetrySample,
    target_lat: float,
    target_lon: float,
    base_route: Route,
    base_location: WorldCoord,
    energy_model: IEnergyModel,
    orbit_params: OrbitParams,
    allow_unsafe: bool = False,
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

    radius_factors = [1.0, 0.8, 0.65, 0.5, 0.35]
    for radius_factor in radius_factors:
        radius_m = max(8.0, orbit_params.radius_m * radius_factor)
        for angle in reduced_angles:
            orbit = _build_orbit_arc(
                target_lat,
                target_lon,
                radius_m,
                orbit_params.altitude_m,
                orbit_params.points_per_circle,
                angle,
            )
            candidate = _assemble_route(orbit)
            if _is_feasible(candidate):
                log.warning(
                    "EnergyModel: reduced orbit to %.0f deg / %.1fm radius to fit remaining battery.",
                    angle,
                    radius_m,
                )
                return candidate

    log.warning("EnergyModel: insufficient battery for orbit maneuver.")
    if allow_unsafe:
        return route
    return None


def build_maneuver(
    current_state: TelemetrySample,
    target_lat: float,
    target_lon: float,
    base_route: Route,
    energy_model: IEnergyModel,
    settings,
    allow_unsafe: bool = False,
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
        allow_unsafe=allow_unsafe,
    )


__all__ = [
    "build_orbit",
    "build_approach",
    "build_rejoin",
    "build_energy_aware_orbit",
    "build_maneuver",
    "OrbitParams",
]
