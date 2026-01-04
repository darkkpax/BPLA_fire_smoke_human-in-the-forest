"""HTTP driver that speaks the sim_api control plane."""

from __future__ import annotations

import logging

import httpx

from fire_uav.module_core.contract.v1 import CameraStatusV1, RouteV1, TelemetryV1


class SimHttpDriver:
    def __init__(
        self,
        *,
        base_url: str,
        logger: logging.Logger | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.log = logger or logging.getLogger(self.__class__.__name__)
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def close(self) -> None:
        await self._client.aclose()

    async def post_telemetry(self, msg: TelemetryV1) -> None:
        resp = await self._client.post(f"{self.base_url}/sim/v1/telemetry", json=msg.model_dump())
        resp.raise_for_status()

    async def post_camera_status(self, msg: CameraStatusV1) -> None:
        resp = await self._client.post(
            f"{self.base_url}/sim/v1/camera_status", json=msg.model_dump()
        )
        resp.raise_for_status()

    async def poll_route(self, uav_id: str) -> RouteV1 | None:
        resp = await self._client.get(f"{self.base_url}/sim/v1/route/{uav_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return RouteV1(**resp.json())


__all__ = ["SimHttpDriver"]
