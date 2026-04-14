from __future__ import annotations

import logging

from fire_uav.domain.video.camera import CameraParams
from fire_uav.module_core.energy.python_energy_model import PythonEnergyModel
from fire_uav.module_core.fusion.python_projector import PythonGeoProjector
from fire_uav.module_core.interfaces.energy import IEnergyModel
from fire_uav.module_core.interfaces.geo import IGeoProjector
from fire_uav.module_core.native import NATIVE_AVAILABLE
from fire_uav.module_core.native.energy import NativeEnergyModel
from fire_uav.module_core.native.geo import NativeGeoProjector

log = logging.getLogger(__name__)


def build_camera_params(settings) -> CameraParams:  # noqa: ANN001
    return CameraParams(
        fov_deg=float(getattr(settings, "camera_fov_deg", 82.1) or 82.1),
        mount_pitch_deg=float(getattr(settings, "camera_mount_pitch_deg", 90.0) or 90.0),
        mount_yaw_deg=float(getattr(settings, "camera_mount_yaw_deg", 0.0) or 0.0),
        mount_roll_deg=float(getattr(settings, "camera_mount_roll_deg", 0.0) or 0.0),
    )


def get_geo_projector(settings, camera: CameraParams | None = None) -> IGeoProjector:  # noqa: ANN001
    if getattr(settings, "use_native_core", False) and NATIVE_AVAILABLE:
        log.info("Native core enabled for geo.")
        return NativeGeoProjector()
    if getattr(settings, "use_native_core", False) and not NATIVE_AVAILABLE:
        log.warning("Native core requested but unavailable, falling back to PythonGeoProjector.")
    else:
        log.info("Using PythonGeoProjector (native disabled).")
    return PythonGeoProjector(camera=camera or build_camera_params(settings))


def get_energy_model(settings) -> IEnergyModel:  # noqa: ANN001
    if getattr(settings, "use_native_core", False) and NATIVE_AVAILABLE:
        log.info("Native core enabled for energy.")
        return NativeEnergyModel(
            max_flight_distance_m=getattr(settings, "max_flight_distance_m", 15000.0),
            min_return_percent=getattr(settings, "min_return_percent", 20.0),
            critical_battery_percent=getattr(settings, "critical_battery_percent", 10.0),
        )
    if getattr(settings, "use_native_core", False) and not NATIVE_AVAILABLE:
        log.warning("Native core requested but unavailable, falling back to PythonEnergyModel.")
    else:
        log.info("Using PythonEnergyModel (native disabled).")
    return PythonEnergyModel(
        cruise_speed_mps=float(getattr(settings, "cruise_speed_mps", 12.0) or 12.0),
        power_cruise_w=float(getattr(settings, "power_cruise_w", 45.0) or 45.0),
        battery_wh=float(getattr(settings, "battery_wh", 27.0) or 27.0),
        max_flight_distance_m=getattr(settings, "max_flight_distance_m", 15000.0),
        min_return_percent=getattr(settings, "min_return_percent", 20.0),
        critical_battery_percent=getattr(settings, "critical_battery_percent", 10.0),
    )


__all__ = ["build_camera_params", "get_geo_projector", "get_energy_model"]
