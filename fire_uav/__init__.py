"""
fire_uav – UAV toolkit: fire/smoke detection + flight-planner.
"""

from __future__ import annotations

# ── public API -------------------------------------------------------------
from fire_uav.domain.video.camera import CameraParams
from fire_uav.module_core.detect.detection import DetectionEngine
from fire_uav.module_core.route import FlightPlanner
from fire_uav.module_core.route.energy import EnergyModel
from fire_uav.module_core.schema import Detection, DetectionsBatch, WorldCoord
from fire_uav.module_core.geometry import haversine_m, offset_latlon

__all__ = (
    "haversine_m",
    "offset_latlon",
    "CameraParams",
    "DetectionEngine",
    "Detection",
    "WorldCoord",
    "DetectionsBatch",
    "FlightPlanner",
    "EnergyModel",
)
