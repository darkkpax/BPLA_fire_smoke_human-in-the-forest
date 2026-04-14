from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

import httpx

from fire_uav.core.protocol import ObjectMessage, RouteMessage, TelemetryMessage, Waypoint
from fire_uav.utils.time import utc_now


class VisualizerClient:
    def __init__(self, base_url: str, uav_id: str, timeout: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.uav_id = uav_id
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        self._log = logging.getLogger(__name__)

    async def _post_json(self, path: str, payload: dict) -> None:
        url = f"{self.base_url}{path}"
        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            self._log.warning("Failed to POST to %s: %s", url, exc)

    async def send_telemetry(
        self, timestamp: datetime, lat: float, lon: float, alt: float, yaw: float, battery: float
    ) -> None:
        msg = TelemetryMessage(
            uav_id=self.uav_id,
            timestamp=timestamp,
            lat=lat,
            lon=lon,
            alt=alt,
            yaw=yaw,
            battery=battery,
        )
        await self._post_json("/api/v1/telemetry", msg.model_dump())

    async def send_route(self, version: int, waypoints: List[Waypoint], active_index: Optional[int]) -> None:
        msg = RouteMessage(
            uav_id=self.uav_id,
            version=version,
            waypoints=waypoints,
            active_index=active_index,
        )
        await self._post_json("/api/v1/route", msg.model_dump())

    async def send_object(
        self,
        object_id: str,
        class_id: int,
        confidence: float,
        lat: float,
        lon: float,
        alt: Optional[float],
        status: str = "confirmed",
    ) -> None:
        msg = ObjectMessage(
            uav_id=self.uav_id,
            object_id=object_id,
            class_id=class_id,
            confidence=confidence,
            lat=lat,
            lon=lon,
            alt=alt,
            status=status,
        )
        await self._post_json("/api/v1/object", msg.model_dump())

    async def aclose(self) -> None:
        await self._client.aclose()


async def _demo() -> None:
    client = VisualizerClient("http://127.0.0.1:8000", uav_id="demo_uav")
    await client.send_telemetry(
        timestamp=utc_now(),
        lat=55.0,
        lon=37.0,
        alt=100.0,
        yaw=90.0,
        battery=0.8,
    )
    wps = [Waypoint(lat=55.0, lon=37.0, alt=100.0), Waypoint(lat=55.001, lon=37.002, alt=120.0)]
    await client.send_route(version=1, waypoints=wps, active_index=0)
    await client.send_object(
        object_id="demo_obj",
        class_id=1,
        confidence=0.9,
        lat=55.0005,
        lon=37.0005,
        alt=90.0,
        status="confirmed",
    )
    await client.aclose()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_demo())

