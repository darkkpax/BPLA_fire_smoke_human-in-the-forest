"""Skysight UAV Contract v1 models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractBaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = 1
    uav_id: str
    timestamp: datetime


class TelemetryV1(ContractBaseV1):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: float
    yaw: float | None = None
    pitch: float | None = None
    roll: float | None = None
    ground_speed_mps: float | None = None
    vertical_speed_mps: float | None = None
    battery_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    gps_fix: int | None = None
    satellites: int | None = None


class CameraStatusV1(ContractBaseV1):
    available: bool
    streaming: bool
    fps: float | None = None
    last_frame_age_s: float | None = None
    error: str | None = None


class CapabilitiesV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supports_waypoints: bool
    supports_rtl: bool
    supports_orbit: bool
    supports_set_speed: bool
    supports_camera: bool
    max_waypoints: int | None = None
    notes: str | None = None


class HealthV1(ContractBaseV1):
    link_status: str
    camera_status: str
    battery_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    message: str | None = None


class WaypointV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: float
    speed_mps: float | None = None
    loiter_radius_m: float | None = None
    action: str | None = None


class RouteV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = 1
    uav_id: str
    route_id: str
    waypoints: list[WaypointV1]
    mode: str
    created_at: datetime


class CommandV1(ContractBaseV1):
    command_id: str
    type: str
    params: dict


class HandshakeRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uav_id: str
    client_type: str
    client_version: str | None = None
    capabilities: CapabilitiesV1 | None = None


class HandshakeResponseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    protocol_version: Literal[1] = 1
    server_time: datetime
    required_fields: dict
    assigned_uav_id: str
    notes: str | None = None


__all__ = [
    "ContractBaseV1",
    "TelemetryV1",
    "CameraStatusV1",
    "CapabilitiesV1",
    "HealthV1",
    "WaypointV1",
    "RouteV1",
    "CommandV1",
    "HandshakeRequestV1",
    "HandshakeResponseV1",
]
