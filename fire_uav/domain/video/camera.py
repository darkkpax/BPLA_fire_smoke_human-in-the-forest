from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final


@dataclass(slots=True)
class CameraParams:
    """
    Camera intrinsics/extrinsics used for geo-projection.

    `fov_deg` follows Unreal SceneCapture2D `FOVAngle` semantics (horizontal FOV).
    """

    sensor_width_mm: float = 6.3
    resolution_px: int = 8_064
    focal_length_mm: float = 5.7
    fov_deg: float = 82.1
    mount_pitch_deg: float = 90.0
    mount_yaw_deg: float = 0.0
    mount_roll_deg: float = 0.0

    def gsd_cm_per_px(self, altitude_m: float) -> float:
        """Ground-sampling distance in cm/px for nadir approximation."""
        return 100 * altitude_m * self.sensor_width_mm / (self.focal_length_mm * self.resolution_px)

    def swath_m(self, altitude_m: float) -> float:
        """Horizontal swath width at altitude in meters."""
        return 2 * altitude_m * math.tan(math.radians(self.fov_deg / 2.0))

    def focal_lengths_px(self, image_width: int, image_height: int) -> tuple[float, float]:
        """Compute focal lengths (fx, fy) in pixels from horizontal FOV and image size."""
        width = max(1.0, float(image_width))
        height = max(1.0, float(image_height))
        fov_rad = math.radians(max(1e-3, float(self.fov_deg)))
        fx = width / (2.0 * math.tan(fov_rad / 2.0))
        fy = fx
        if height > 0.0:
            fy = fx
        return fx, fy

    @staticmethod
    def principal_point_px(image_width: int, image_height: int) -> tuple[float, float]:
        return image_width / 2.0, image_height / 2.0


class Camera:
    """Minimal camera stub used by tests (`open`, `close`, `is_open`)."""

    _DEFAULT_NAME: Final[str] = "Camera"

    def __init__(self, params: CameraParams | None = None) -> None:
        self.params: CameraParams = params or CameraParams()
        self._opened: bool = False

    def open(self) -> None:
        """Open camera (stub)."""
        self._opened = True

    def close(self) -> None:
        """Close camera (stub)."""
        self._opened = False

    @property
    def is_open(self) -> bool:
        """True when camera is open."""
        return self._opened


__all__ = ["Camera", "CameraParams"]
