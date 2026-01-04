from __future__ import annotations

import logging

from fire_uav.module_core.adapters.interfaces import IUavAdapter, IUavTelemetryConsumer
from fire_uav.module_core.schema import Route


class CustomSdkUavAdapter(IUavAdapter):
    """
    Template adapter for client-provided SDKs or bespoke flight software.

    This is intended to be the foundation for paid integration work where the
    client's software is bridged to our internal protocol.
    """

    def __init__(self, client_config: dict, logger: logging.Logger | None = None) -> None:
        """
        client_config may describe how to talk to the client's software:
          - host/port
          - auth tokens
          - protocol: HTTP/gRPC/ZeroMQ/etc.
        """
        self.client_config = client_config
        self.log = logger or logging.getLogger(self.__class__.__name__)
        self._telemetry_callback: IUavTelemetryConsumer | None = None
        self._running = False
        self._last_route: Route | None = None

    async def start(self, telemetry_callback: IUavTelemetryConsumer) -> None:
        """
        Start the adapter and register the telemetry consumer.

        This adapter does not spawn its own loops; telemetry is injected from the
        outside (e.g., via integration_service) and forwarded to the callback.
        """
        self._telemetry_callback = telemetry_callback
        self._running = True
        self.log.info("Custom SDK adapter started (config keys=%s)", list(self.client_config))

    async def stop(self) -> None:
        """Mark the adapter as stopped."""
        if not self._running:
            return
        self._running = False
        self.log.info("Custom SDK adapter stopped")

    async def push_route(self, route: Route) -> None:
        """
        Store the latest route; in the future this can be propagated to a client SDK.
        """
        self._last_route = route
        self.log.debug("Route received (waypoints=%d)", len(route.waypoints))

    async def send_simple_command(self, command: str, payload: dict | None = None) -> None:
        """
        Log a received command; downstream mapping can be added later.
        """
        self.log.info("CustomSdkUavAdapter command: %s payload=%s", command, payload)

    @property
    def telemetry_callback(self) -> IUavTelemetryConsumer | None:
        """Expose the registered telemetry callback for external injection paths."""
        return self._telemetry_callback

    @property
    def last_route(self) -> Route | None:
        """Return the last route pushed into the adapter."""
        return self._last_route


__all__ = ["CustomSdkUavAdapter"]
