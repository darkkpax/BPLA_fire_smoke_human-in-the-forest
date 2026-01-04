"""Stable driver interface for UAV integrations."""

from __future__ import annotations

from typing import Protocol

from fire_uav.module_core.adapters.interfaces import IUavTelemetryConsumer
from fire_uav.module_core.contract.v1 import CapabilitiesV1, CommandV1, RouteV1
from fire_uav.module_core.schema import Route, TelemetrySample


class UavDriver(Protocol):
    async def connect(self, telemetry_callback: IUavTelemetryConsumer) -> None: ...

    async def disconnect(self) -> None: ...

    async def get_capabilities(self) -> CapabilitiesV1: ...

    async def read_telemetry(self) -> TelemetrySample | None: ...

    async def send_route(self, route: Route) -> None: ...

    async def send_route_v1(self, route: RouteV1) -> None: ...

    async def send_command(self, cmd: CommandV1) -> None: ...


__all__ = ["UavDriver"]
