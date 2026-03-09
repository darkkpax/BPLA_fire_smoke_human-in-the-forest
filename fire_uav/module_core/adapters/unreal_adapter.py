from __future__ import annotations

import asyncio
import logging

import httpx

from fire_uav.core.protocol import RouteMessage, TelemetryMessage, Waypoint as ProtocolWaypoint
from fire_uav.core.telemetry import telemetry_sample_from_message
from fire_uav.module_core.metrics import (
    telemetry_ingest_errors_total,
    telemetry_ingest_total,
)
from fire_uav.module_core.adapters.interfaces import IUavAdapter, IUavTelemetryConsumer
from fire_uav.module_core.schema import Route


class UnrealSimUavAdapter(IUavAdapter):
    """
    Adapter for Unreal-based simulators.

    Talks to an external Unreal bridge process over HTTP.
    Polls telemetry and pushes it into module_core as TelemetrySample.
    Sends routes and simple commands from module_core to Unreal.
    """

    def __init__(
        self,
        base_url: str,
        uav_id: str | None = None,
        logger: logging.Logger | None = None,
        poll_interval_sec: float = 0.1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.uav_id = uav_id or "sim"
        self.log = logger or logging.getLogger(self.__class__.__name__)
        self._client: httpx.AsyncClient | None = None
        self._telemetry_task: asyncio.Task | None = None
        self._telemetry_callback: IUavTelemetryConsumer | None = None
        self._running = False
        self._poll_interval_sec = poll_interval_sec

    async def start(self, telemetry_callback: IUavTelemetryConsumer) -> None:
        """
        Start polling telemetry from the Unreal bridge.
        """
        if self._running:
            return
        self._telemetry_callback = telemetry_callback
        self._client = httpx.AsyncClient()
        self._running = True
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        self.log.info(
            "UnrealSimUavAdapter started (base_url=%s, uav_id=%s)", self.base_url, self.uav_id
        )

    async def stop(self) -> None:
        """
        Stop polling and close HTTP resources.
        """
        if not self._running:
            return
        self._running = False
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
            self._telemetry_task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        self.log.info("UnrealSimUavAdapter stopped")

    async def _telemetry_loop(self) -> None:
        """
        Periodically fetch telemetry from Unreal and forward it to the consumer.
        """
        if self._client is None:
            return
        url = f"{self.base_url}/sim/v1/telemetry"
        while self._running:
            try:
                resp = await self._client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if data.get("yaw") is None:
                    data["yaw"] = 0.0
                msg = TelemetryMessage(**data)
                sample = telemetry_sample_from_message(msg)
                if self._telemetry_callback is not None:
                    await self._telemetry_callback.on_telemetry(sample)
                telemetry_ingest_total.labels("unreal").inc()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                telemetry_ingest_errors_total.labels("unreal").inc()
                self.log.warning("Unreal telemetry poll failed: %s", exc)
            await asyncio.sleep(self._poll_interval_sec)

    async def push_route(self, route: Route) -> None:
        """
        Send the current route to Unreal bridge.
        """
        waypoints = [
            ProtocolWaypoint(lat=wp.lat, lon=wp.lon, alt=wp.alt) for wp in route.waypoints
        ]
        route_msg = RouteMessage(
            uav_id=self.uav_id,
            version=route.version,
            waypoints=waypoints,
            active_index=route.active_index,
        )
        payload = route_msg.model_dump()
        client = self._client
        own_client = False
        if client is None:
            client = httpx.AsyncClient()
            own_client = True
        try:
            resp = await client.post(f"{self.base_url}/sim/v1/route", json=payload)
            resp.raise_for_status()
            self.log.debug("Route pushed to Unreal (waypoints=%d)", len(route.waypoints))
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Failed to push route to Unreal: %s", exc)
        finally:
            if own_client:
                await client.aclose()

    async def send_simple_command(self, command: str, payload: dict | None = None) -> None:
        """
        Send a simple control command to Unreal bridge.
        """
        body = {"uav_id": self.uav_id, "command": command, "payload": payload or {}}
        client = self._client
        own_client = False
        if client is None:
            client = httpx.AsyncClient()
            own_client = True
        try:
            resp = await client.post(f"{self.base_url}/sim/v1/command", json=body)
            resp.raise_for_status()
            self.log.debug("Sent command to Unreal: %s", command)
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Failed to send command to Unreal: %s", exc)
        finally:
            if own_client:
                await client.aclose()


__all__ = ["UnrealSimUavAdapter"]
