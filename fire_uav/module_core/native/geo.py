from __future__ import annotations

import logging
import math
from typing import Optional, Tuple

from fire_uav.module_core.interfaces.geo import IGeoProjector
from fire_uav.module_core.native import NATIVE_AVAILABLE, _native_core
from fire_uav.module_core.schema import TelemetrySample

log = logging.getLogger(__name__)


if NATIVE_AVAILABLE:

    class NativeGeoProjector(IGeoProjector):
        """Native-backed geo projector using pybind11 extension."""

        def compute_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            return float(_native_core.geo_distance_m(lat1, lon1, lat2, lon2))

        def project_bbox_to_ground(
            self,
            telemetry: TelemetrySample,
            bbox: tuple[float, float, float, float],
            image_width: int,
            image_height: int,
        ) -> Optional[tuple[float, float]]:
            x_min, y_min, x_max, y_max = bbox
            # Placeholder intrinsics; refine once camera calibration is exposed.
            fx = fy = 1.0
            cx = image_width / 2.0
            cy = image_height / 2.0
            lat, lon = _native_core.geo_project_bbox_to_ground(
                telemetry.lat,
                telemetry.lon,
                telemetry.alt,
                math.radians(telemetry.yaw),
                math.radians(telemetry.pitch),
                math.radians(telemetry.roll),
                fx,
                fy,
                cx,
                cy,
                x_min,
                y_min,
                x_max,
                y_max,
            )
            return float(lat), float(lon)

else:

    class NativeGeoProjector(IGeoProjector):  # type: ignore[misc]
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise RuntimeError("Native core is not available. Build the C++ extension or disable native usage.")

        def compute_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            raise RuntimeError("Native core is not available.")

        def project_bbox_to_ground(
            self,
            telemetry: TelemetrySample,
            bbox: tuple[float, float, float, float],
            image_width: int,
            image_height: int,
        ) -> Optional[Tuple[float, float]]:
            raise RuntimeError("Native core is not available.")


__all__ = ["NativeGeoProjector"]

