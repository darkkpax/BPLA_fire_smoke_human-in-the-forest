from __future__ import annotations

from fire_uav.domain.video.camera import CameraParams
from fire_uav.module_core.fusion.python_projector import PythonGeoProjector
from fire_uav.module_core.geometry import haversine_m
from fire_uav.module_core.schema import TelemetrySample


def test_projector_center_ray_straight_down_hits_under_uav() -> None:
    projector = PythonGeoProjector(
        CameraParams(
            fov_deg=82.1,
            mount_pitch_deg=90.0,
            mount_yaw_deg=0.0,
            mount_roll_deg=0.0,
        )
    )
    telemetry = TelemetrySample(
        lat=56.0,
        lon=92.9,
        alt=100.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.8,
    )

    lat, lon = projector.project_bbox_to_ground(
        telemetry=telemetry,
        bbox=(960.0, 540.0, 960.0, 540.0),
        image_width=1920,
        image_height=1080,
    )

    distance_m = haversine_m((telemetry.lat, telemetry.lon), (lat, lon))
    assert distance_m < 0.5


def test_projector_forward_ray_hits_far_ground_point() -> None:
    projector = PythonGeoProjector(
        CameraParams(
            fov_deg=82.1,
            mount_pitch_deg=10.0,
            mount_yaw_deg=0.0,
            mount_roll_deg=0.0,
        )
    )
    telemetry = TelemetrySample(
        lat=0.0,
        lon=0.0,
        alt=100.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.8,
    )

    lat, lon = projector.project_bbox_to_ground(
        telemetry=telemetry,
        bbox=(960.0, 540.0, 960.0, 540.0),
        image_width=1920,
        image_height=1080,
    )

    distance_m = haversine_m((telemetry.lat, telemetry.lon), (lat, lon))
    assert distance_m > 500.0
    assert distance_m < 650.0
    assert lon > telemetry.lon
    assert abs(lat - telemetry.lat) < 1e-4


def test_projector_invalid_intersection_returns_none() -> None:
    projector = PythonGeoProjector(
        CameraParams(
            fov_deg=82.1,
            mount_pitch_deg=0.0,
            mount_yaw_deg=0.0,
            mount_roll_deg=0.0,
        )
    )
    telemetry = TelemetrySample(
        lat=56.0,
        lon=92.9,
        alt=100.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.8,
    )

    projected = projector.project_bbox_to_ground(
        telemetry=telemetry,
        bbox=(960.0, 540.0, 960.0, 540.0),
        image_width=1920,
        image_height=1080,
    )
    assert projected is None


def test_projector_prefers_runtime_camera_mount_from_telemetry() -> None:
    projector = PythonGeoProjector(
        CameraParams(
            fov_deg=82.1,
            mount_pitch_deg=0.0,
            mount_yaw_deg=0.0,
            mount_roll_deg=0.0,
        )
    )
    telemetry = TelemetrySample(
        lat=56.0,
        lon=92.9,
        alt=100.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.8,
        camera_mount_pitch_deg=90.0,
    )

    lat, lon = projector.project_bbox_to_ground(
        telemetry=telemetry,
        bbox=(960.0, 540.0, 960.0, 540.0),
        image_width=1920,
        image_height=1080,
    )

    distance_m = haversine_m((telemetry.lat, telemetry.lon), (lat, lon))
    assert distance_m < 0.5


def test_projector_prefers_alt_agl_over_absolute_altitude() -> None:
    projector = PythonGeoProjector(
        CameraParams(
            fov_deg=82.1,
            mount_pitch_deg=10.0,
            mount_yaw_deg=0.0,
            mount_roll_deg=0.0,
        )
    )
    telemetry = TelemetrySample(
        lat=0.0,
        lon=0.0,
        alt=450.0,
        alt_agl=100.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.8,
    )

    lat, lon = projector.project_bbox_to_ground(
        telemetry=telemetry,
        bbox=(960.0, 540.0, 960.0, 540.0),
        image_width=1920,
        image_height=1080,
    )

    distance_m = haversine_m((telemetry.lat, telemetry.lon), (lat, lon))
    assert distance_m > 500.0
    assert distance_m < 650.0
