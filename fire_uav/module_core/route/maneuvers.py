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
    # ensure we end near entry point
    result.append(Waypoint(lat=target_lat, lon=target_lon, alt=altitude_m))
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
    for i in range(steps):
        angle = total_angle_rad * (i / steps)
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        lat, lon = offset_latlon(target_lat, target_lon, dx, dy)
        result.append(Waypoint(lat=lat, lon=lon, alt=altitude_m))
    result.append(Waypoint(lat=target_lat, lon=target_lon, alt=altitude_m))
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

    center = getattr(settings, "map_center", None)
    if isinstance(center, (list, tuple)) and len(center) >= 2:
        try:
            return WorldCoord(lat=float(center[0]), lon=float(center[1]))
        except (TypeError, ValueError):
            pass

    if base_route.waypoints:
        wp = base_route.waypoints[0]
        return WorldCoord(lat=wp.lat, lon=wp.lon)

    return WorldCoord(lat=current_state.lat, lon=current_state.lon)


def build_approach(current_pos: TelemetrySample | Waypoint, entry_wp: Waypoint) -> List[Waypoint]:
    start = _as_waypoint(current_pos, alt=entry_wp.alt)
    if haversine_m((start.lat, start.lon), (entry_wp.lat, entry_wp.lon)) < 0.5:
        return [entry_wp]
    return [start, entry_wp]


def build_rejoin(exit_wp: Waypoint, base_route: Route) -> List[Waypoint]:
    if not base_route.waypoints:
        return []

    closest_idx = 0
    closest_dist = float("inf")
    for idx, wp in enumerate(base_route.waypoints):
        dist = haversine_m((exit_wp.lat, exit_wp.lon), (wp.lat, wp.lon))
        if dist < closest_dist:
            closest_dist = dist
            closest_idx = idx

    path = [exit_wp]
    path.extend(base_route.waypoints[closest_idx:])
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
    entry_wp = Waypoint(lat=target_lat, lon=target_lon, alt=orbit_params.altitude_m)
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

    return_wp = Waypoint(
        lat=base_location.lat,
        lon=base_location.lon,
        alt=orbit_params.altitude_m,
    )
    minimal_route = Route(
        version=base_route.version if base_route.version is not None else 1,
        waypoints=approach + [return_wp],
        active_index=0 if approach else None,
    )
    if _is_feasible(minimal_route):
        log.warning("EnergyModel: skipping orbit; returning to base instead.")
        return minimal_route

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
    altitude = getattr(settings, "maneuver_alt_m", current_state.alt)
    radius = getattr(settings, "orbit_radius_m", 50.0)
    points_per_circle = getattr(settings, "orbit_points_per_circle", 12)
    loops = getattr(settings, "orbit_loops", 1)
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
