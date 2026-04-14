from __future__ import annotations

from fire_uav.module_core.geometry import haversine_m
from fire_uav.module_core.route.maneuvers import build_maneuver, build_orbit, build_rejoin
from fire_uav.module_core.energy.python_energy_model import PythonEnergyModel
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint


def test_build_orbit_does_not_end_in_target_center() -> None:
    target_lat = 56.0
    target_lon = 92.9
    radius_m = 50.0
    orbit = build_orbit(
        target_lat=target_lat,
        target_lon=target_lon,
        radius_m=radius_m,
        altitude_m=120.0,
        points_per_circle=12,
        loops=1,
    )
    assert orbit
    last = orbit[-1]
    dist_to_center = haversine_m((last.lat, last.lon), (target_lat, target_lon))
    assert dist_to_center > 20.0


def test_build_rejoin_does_not_jump_back_to_completed_segment() -> None:
    route = Route(
        version=1,
        active_index=2,
        waypoints=[
            Waypoint(lat=56.0000, lon=92.9000, alt=120.0),
            Waypoint(lat=56.0005, lon=92.9005, alt=120.0),
            Waypoint(lat=56.0010, lon=92.9010, alt=120.0),
            Waypoint(lat=56.0015, lon=92.9015, alt=120.0),
        ],
    )
    exit_wp = Waypoint(lat=56.00055, lon=92.90055, alt=120.0)

    rejoin = build_rejoin(exit_wp, route)

    assert rejoin
    assert rejoin[0] == route.waypoints[2]
    assert rejoin[1] == route.waypoints[3]


def test_build_rejoin_uses_forward_segment_point_instead_of_far_old_waypoint() -> None:
    route = Route(
        version=1,
        active_index=0,
        waypoints=[
            Waypoint(lat=56.0000, lon=92.9000, alt=120.0),
            Waypoint(lat=56.0000, lon=92.9100, alt=120.0),
            Waypoint(lat=56.0000, lon=92.9200, alt=120.0),
        ],
    )
    exit_wp = Waypoint(lat=56.0001, lon=92.9150, alt=120.0)

    rejoin = build_rejoin(exit_wp, route)

    assert rejoin
    assert len(rejoin) >= 2
    assert haversine_m((exit_wp.lat, exit_wp.lon), (rejoin[0].lat, rejoin[0].lon)) < 100.0
    assert rejoin[-1] == route.waypoints[-1]


def test_build_maneuver_falls_back_to_current_altitude_when_setting_is_none() -> None:
    class _Settings:
        maneuver_alt_m = None
        orbit_radius_m = 50.0
        orbit_points_per_circle = 12
        orbit_loops = 1
        home_lat = None
        home_lon = None
        base_lat = None
        base_lon = None
        map_center = (56.0, 92.9)

    current = TelemetrySample(
        lat=56.0,
        lon=92.9,
        alt=120.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=1.0,
        battery_percent=100.0,
    )
    route = Route(
        version=1,
        active_index=0,
        waypoints=[
            Waypoint(lat=56.0, lon=92.9, alt=120.0),
            Waypoint(lat=56.001, lon=92.901, alt=120.0),
        ],
    )

    maneuver = build_maneuver(
        current_state=current,
        target_lat=56.0005,
        target_lon=92.9005,
        base_route=route,
        energy_model=PythonEnergyModel(max_flight_distance_m=100000.0),
        settings=_Settings(),
    )

    assert maneuver is not None
    assert maneuver.waypoints
    assert all(wp.alt == 120.0 for wp in maneuver.waypoints)


def test_build_maneuver_uses_route_start_before_far_map_center_for_energy_base() -> None:
    class _Settings:
        maneuver_alt_m = None
        orbit_radius_m = 50.0
        orbit_points_per_circle = 12
        orbit_loops = 1
        home_lat = None
        home_lon = None
        base_lat = None
        base_lon = None
        map_center = (56.02, 92.9)

    current = TelemetrySample(
        lat=47.6060,
        lon=-122.3350,
        alt=120.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=1.0,
        battery_percent=97.0,
    )
    route = Route(
        version=1,
        active_index=0,
        waypoints=[
            Waypoint(lat=47.6060, lon=-122.3350, alt=120.0),
            Waypoint(lat=47.6070, lon=-122.3340, alt=120.0),
        ],
    )

    maneuver = build_maneuver(
        current_state=current,
        target_lat=47.6065,
        target_lon=-122.3345,
        base_route=route,
        energy_model=PythonEnergyModel(max_flight_distance_m=15000.0),
        settings=_Settings(),
    )

    assert maneuver is not None
    assert len(maneuver.waypoints) > len(route.waypoints)


def test_build_maneuver_ignores_stale_home_from_other_region() -> None:
    class _Settings:
        maneuver_alt_m = None
        orbit_radius_m = 50.0
        orbit_points_per_circle = 12
        orbit_loops = 1
        home_lat = 56.01419
        home_lon = 92.843638
        base_lat = None
        base_lon = None
        map_center = (56.02, 92.9)

    current = TelemetrySample(
        lat=47.6081,
        lon=-122.3358,
        alt=120.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.82,
        battery_percent=82.0,
    )
    route = Route(
        version=1,
        active_index=1,
        waypoints=[
            Waypoint(lat=47.6054, lon=-122.3352, alt=120.0),
            Waypoint(lat=47.6082, lon=-122.3358, alt=120.0),
            Waypoint(lat=47.6080, lon=-122.3260, alt=120.0),
            Waypoint(lat=47.6047, lon=-122.3270, alt=120.0),
        ],
    )

    maneuver = build_maneuver(
        current_state=current,
        target_lat=47.6085,
        target_lon=-122.3357,
        base_route=route,
        energy_model=PythonEnergyModel(max_flight_distance_m=15000.0, min_return_percent=20.0),
        settings=_Settings(),
    )

    assert maneuver is not None
    assert maneuver.waypoints


def test_build_maneuver_returns_none_when_orbit_is_not_energy_feasible() -> None:
    class _Settings:
        maneuver_alt_m = None
        orbit_radius_m = 80.0
        orbit_points_per_circle = 12
        orbit_loops = 1
        home_lat = None
        home_lon = None
        base_lat = None
        base_lon = None
        map_center = (47.6060, -122.3350)

    current = TelemetrySample(
        lat=47.6060,
        lon=-122.3350,
        alt=120.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=1.0,
        battery_percent=25.0,
    )
    route = Route(
        version=1,
        active_index=0,
        waypoints=[
            Waypoint(lat=47.6060, lon=-122.3350, alt=120.0),
            Waypoint(lat=47.6070, lon=-122.3340, alt=120.0),
        ],
    )

    maneuver = build_maneuver(
        current_state=current,
        target_lat=47.6160,
        target_lon=-122.3250,
        base_route=route,
        energy_model=PythonEnergyModel(max_flight_distance_m=1000.0, min_return_percent=20.0),
        settings=_Settings(),
    )

    assert maneuver is None
