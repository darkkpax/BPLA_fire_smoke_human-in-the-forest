"""Shared DTOs and schemas reused by module and ground runtimes."""

from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

from pydantic import BaseModel, ConfigDict, Field
from fire_uav.utils.time import utc_now


class WorldCoord(BaseModel):
    lat: float
    lon: float


class TelemetrySample(BaseModel):
    """
    Unified telemetry snapshot.

    The model keeps backward-compatible properties for legacy callers (alt_m,
    yaw_deg, etc.) while the canonical fields are alt/yaw/pitch/roll.
    """

    model_config = ConfigDict(populate_by_name=True)

    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: float = Field(..., ge=0, alias="alt_m", description="Altitude in world geo frame, m")
    alt_agl: float | None = Field(
        default=None,
        ge=0.0,
        alias="alt_agl_m",
        description="Altitude above local ground level, m",
    )
    yaw: float = Field(0.0, alias="yaw_deg", description="Heading/yaw angle in degrees")
    pitch: float = Field(0.0, alias="pitch_deg")
    roll: float = Field(0.0, alias="roll_deg")
    vx: float | None = None
    vy: float | None = None
    vz: float | None = None
    battery: float = Field(1.0, ge=0.0, le=1.0, description="Remaining battery, 0..1")
    battery_percent: float | None = Field(
        default=None, ge=0.0, le=100.0, description="Remaining battery, 0..100 (%)"
    )
    status: str | None = None
    flight_mode: str | None = None
    camera_mount_pitch_deg: float | None = None
    camera_mount_yaw_deg: float | None = None
    camera_mount_roll_deg: float | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    source: str | None = Field(
        default=None,
        description="Optional identifier of the telemetry source (autopilot channel, etc.)",
    )

    @property
    def alt_m(self) -> float:
        return self.alt

    @property
    def yaw_deg(self) -> float:
        return self.yaw

    @property
    def pitch_deg(self) -> float:
        return self.pitch

    @property
    def roll_deg(self) -> float:
        return self.roll


class Waypoint(BaseModel):
    lat: float
    lon: float
    alt: float


class Route(BaseModel):
    version: int
    waypoints: List[Waypoint]
    active_index: int | None = None

    def active_waypoint(self) -> Waypoint | None:
        if self.active_index is None:
            return None
        if 0 <= self.active_index < len(self.waypoints):
            return self.waypoints[self.active_index]
        return None


class GeoDetection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    object_id: str | None = None
    class_id: int
    confidence: float
    lat: float
    lon: float
    alt: float | None = None
    timestamp: datetime = Field(default_factory=utc_now, alias="captured_at")
    frame_id: str | None = Field(default=None, alias="source_frame")
    track_id: int | None = None

    @property
    def location(self) -> WorldCoord:
        return WorldCoord(lat=self.lat, lon=self.lon)

    @property
    def captured_at(self) -> datetime:
        return self.timestamp

    @property
    def source_frame(self) -> str | None:
        return self.frame_id


class Detection(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    camera_id: str
    class_id: int
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    world_coord: WorldCoord | None = None
    relative_angles: Tuple[float, float] | None = None  # az, el


class FrameMeta(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    camera_id: str
    width: int
    height: int


class DetectionsBatch(BaseModel):
    frame: FrameMeta
    detections: List[Detection]


__all__ = [
    "WorldCoord",
    "TelemetrySample",
    "Waypoint",
    "Route",
    "GeoDetection",
    "Detection",
    "DetectionsBatch",
    "FrameMeta",
]
