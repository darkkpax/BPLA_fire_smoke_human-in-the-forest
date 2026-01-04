"""
Lightweight HTTP bridge stub that mimics the Unreal-side API expected by
`UnrealSimUavAdapter`.

Endpoints (match docs/unreal_visualizer_api.md):
  - GET  /sim/v1/telemetry  -> latest TelemetryMessage
  - POST /sim/v1/route      -> RouteMessage; starts moving along waypoints
  - POST /sim/v1/command    -> simple command logger (RESET resets position)

This is meant for local testing or as a reference implementation for a
Blueprint/C++ bridge inside Unreal.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from fire_uav.core.protocol import RouteMessage, TelemetryMessage, Waypoint

log = logging.getLogger("unreal_bridge_stub")

app = FastAPI(title="Unreal Bridge Stub", version="0.1.0")

EARTH_RADIUS_M = 6_371_000.0


class Command(BaseModel):
    uav_id: str | None = None
    command: str
    payload: dict | None = None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(min(1.0, math.sqrt(a)))
    return EARTH_RADIUS_M * c


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute heading from point1 to point2."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(lat2_r)
    x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def _offset_latlon(lat_deg: float, lon_deg: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    """Offset lat/lon by dx/dy metres in ENU approximation."""
    d_lat = dy_m / EARTH_RADIUS_M
    d_lon = dx_m / (EARTH_RADIUS_M * math.cos(math.radians(lat_deg)))
    return lat_deg + math.degrees(d_lat), lon_deg + math.degrees(d_lon)


class _SimState:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._route: RouteMessage | None = None
        self._active_idx: int = 0
        self._task: asyncio.Task | None = None
        self._speed_mps: float = 12.0
        self._uav_id: str = "sim"
        self.telemetry = TelemetryMessage(
            uav_id=self._uav_id,
            timestamp=datetime.utcnow(),
            lat=55.0,
            lon=37.0,
            alt=120.0,
            yaw=90.0,
            battery=0.9,
        )

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            log.info("Sim state loop started (speed=%.1f m/s)", self._speed_mps)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            log.info("Sim state loop stopped")

    async def set_route(self, route: RouteMessage) -> None:
        async with self._lock:
            self._route = route
            self._active_idx = route.active_index or 0
            self._uav_id = route.uav_id
            self.telemetry = self.telemetry.model_copy(
                update={"uav_id": route.uav_id, "timestamp": datetime.utcnow()}
            )
        log.info("Route received: %d waypoints", len(route.waypoints))

    async def handle_command(self, cmd: Command) -> None:
        command = cmd.command.upper()
        if command == "RESET":
            async with self._lock:
                self._active_idx = 0
                if self._route and self._route.waypoints:
                    wp = self._route.waypoints[0]
                    self.telemetry = self.telemetry.model_copy(
                        update={"lat": wp.lat, "lon": wp.lon, "alt": wp.alt, "yaw": 0.0}
                    )
            log.info("RESET command processed")
        else:
            log.info("Command received: %s payload=%s", command, cmd.payload)

    async def _loop(self) -> None:
        """Move towards active waypoint, looping every 0.1 s."""
        dt = 0.1
        while True:
            await asyncio.sleep(dt)
            async with self._lock:
                if not self._route or not self._route.waypoints:
                    continue
                wp = self._route.waypoints[self._active_idx]
                cur = self.telemetry
                dist = _haversine_m(cur.lat, cur.lon, wp.lat, wp.lon)
                if dist < 1.0:
                    # advance to next wp or hold
                    if self._active_idx < len(self._route.waypoints) - 1:
                        self._active_idx += 1
                        wp = self._route.waypoints[self._active_idx]
                        dist = _haversine_m(cur.lat, cur.lon, wp.lat, wp.lon)
                    else:
                        continue

                step = min(self._speed_mps * dt, dist)
                bearing = _bearing_deg(cur.lat, cur.lon, wp.lat, wp.lon)
                # Convert bearing to dx/dy in metres (ENU: X east, Y north)
                rad = math.radians(bearing)
                dx = math.sin(rad) * step
                dy = math.cos(rad) * step
                lat, lon = _offset_latlon(cur.lat, cur.lon, dx, dy)
                self.telemetry = TelemetryMessage(
                    uav_id=self._uav_id,
                    timestamp=datetime.utcnow(),
                    lat=lat,
                    lon=lon,
                    alt=wp.alt,
                    yaw=bearing,
                    battery=max(0.0, cur.battery - step * 1e-6),
                )


sim_state = _SimState()


@app.on_event("startup")
async def _startup() -> None:
    await sim_state.start()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await sim_state.stop()


@app.get("/sim/v1/telemetry", response_model=TelemetryMessage)
async def get_telemetry() -> TelemetryMessage:
    return sim_state.telemetry


@app.post("/sim/v1/route")
async def post_route(route: RouteMessage) -> dict[str, str]:
    await sim_state.set_route(route)
    return {"status": "ok"}


@app.post("/sim/v1/command")
async def post_command(cmd: Command) -> dict[str, str]:
    await sim_state.handle_command(cmd)
    return {"status": "ok"}


if __name__ == "__main__":  # pragma: no cover
    host = os.getenv("UNREAL_BRIDGE_HOST", "0.0.0.0")
    port = int(os.getenv("UNREAL_BRIDGE_PORT", "9000"))
    uvicorn.run("scripts.unreal_bridge_stub:app", host=host, port=port, reload=False)
