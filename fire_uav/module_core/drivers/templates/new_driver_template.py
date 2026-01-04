"""Template for adding a new UAV driver.

Copy this file and implement the TODO sections.
"""

from __future__ import annotations

import logging

from fire_uav.module_core.adapters.interfaces import IUavAdapter, IUavTelemetryConsumer
from fire_uav.module_core.contract.v1 import CommandV1, RouteV1, TelemetryV1
from fire_uav.module_core.contract.mappers import telemetry_v1_to_sample, route_v1_to_internal
from fire_uav.module_core.schema import Route


class NewDroneDriver(IUavAdapter):
    """TODO: Replace with a real driver name and implementation."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self.log = logger or logging.getLogger(self.__class__.__name__)
        self._telemetry_callback: IUavTelemetryConsumer | None = None

    async def start(self, telemetry_callback: IUavTelemetryConsumer) -> None:
        """Connect to the drone and start streaming telemetry."""
        self._telemetry_callback = telemetry_callback
        # TODO: connect to drone transport (serial/udp/http/etc).
        # TODO: start background task that reads telemetry and calls _handle_raw_telemetry().

    async def stop(self) -> None:
        """Disconnect from the drone and stop telemetry streaming."""
        # TODO: stop background tasks and close transports.

    async def push_route(self, route: Route) -> None:
        """Send an internal Route to the drone."""
        # TODO: map Route to your drone protocol and upload mission.
        self.log.debug("Route received (waypoints=%d)", len(route.waypoints))

    async def send_simple_command(self, command: str, payload: dict | None = None) -> None:
        """Send a simple command to the drone."""
        # TODO: map command string/payload into your drone API.
        self.log.info("Command: %s payload=%s", command, payload)

    # --- optional helpers for contract v1 --- #
    async def send_route_v1(self, route: RouteV1) -> None:
        """Accept RouteV1 directly and map to internal Route."""
        await self.push_route(route_v1_to_internal(route))

    async def send_command(self, cmd: CommandV1) -> None:
        """Accept CommandV1 and map to your drone protocol."""
        await self.send_simple_command(cmd.type, cmd.params)

    def _handle_raw_telemetry(self, msg: TelemetryV1) -> None:
        """Convert contract telemetry into TelemetrySample and forward to core."""
        if self._telemetry_callback is None:
            return
        sample = telemetry_v1_to_sample(msg)
        # TODO: If this is an async callback, await it from your telemetry loop.
        self.log.debug("Telemetry: lat=%.6f lon=%.6f", sample.lat, sample.lon)


__all__ = ["NewDroneDriver"]
