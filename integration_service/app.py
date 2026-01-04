from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from fire_uav.api.security import require_api_key
from fire_uav.core.protocol import ObjectMessage, RouteMessage, TelemetryMessage
from fire_uav.core.telemetry import telemetry_sample_from_message
from fire_uav.module_core.adapters.custom_sdk_adapter import CustomSdkUavAdapter
from fire_uav.module_core.metrics import (
    telemetry_ingest_errors_total,
    telemetry_ingest_total,
)
from fire_uav.module_core.schema import Route, TelemetrySample, Waypoint

log = logging.getLogger("integration_service")

app = FastAPI(
    title="Integration Service",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    dependencies=[Depends(require_api_key)],
)
app.add_middleware(GZipMiddleware, minimum_size=512)
Instrumentator().instrument(app).expose(app)

# In-memory storage for latest messages per UAV.
last_telemetry: Dict[str, TelemetryMessage] = {}
last_route: Dict[str, RouteMessage] = {}
_started_at = datetime.utcnow()


class CommandRequest(BaseModel):
    uav_id: str
    command: str
    payload: dict | None = None


class _TelemetrySink:
    """Minimal telemetry consumer that stores the last sample."""

    def __init__(self) -> None:
        self.latest: TelemetrySample | None = None

    async def on_telemetry(self, sample: TelemetrySample) -> None:
        self.latest = sample
        log.debug(
            "Telemetry forwarded | lat=%.6f lon=%.6f alt=%.1f yaw=%.1f",
            sample.lat,
            sample.lon,
            sample.alt,
            sample.yaw,
        )


telemetry_sink = _TelemetrySink()

# Adapter instance shared by the service.
adapter = CustomSdkUavAdapter(client_config={}, logger=log)


@app.on_event("startup")
async def _startup() -> None:
    await adapter.start(telemetry_sink)
    log.info("Integration service started with CustomSdkUavAdapter")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await adapter.stop()
    log.info("Integration service stopped")


@app.post("/ext/v1/telemetry")
async def post_telemetry(msg: TelemetryMessage) -> dict:
    """
    Receive telemetry from external client software and forward it internally.
    """
    last_telemetry[msg.uav_id] = msg
    try:
        sample = telemetry_sample_from_message(msg)
    except Exception as exc:  # noqa: BLE001
        telemetry_ingest_errors_total.labels("integration").inc()
        raise HTTPException(status_code=422, detail=f"Invalid telemetry payload: {exc}") from exc
    if adapter.telemetry_callback is not None:
        await adapter.telemetry_callback.on_telemetry(sample)
    telemetry_ingest_total.labels("integration").inc()
    return {"status": "ok"}


@app.post("/ext/v1/route")
async def post_route(msg: RouteMessage) -> dict:
    """
    Receive a route from external clients and store it.
    """
    last_route[msg.uav_id] = msg
    route = Route(
        version=msg.version,
        waypoints=[Waypoint(lat=wp.lat, lon=wp.lon, alt=wp.alt) for wp in msg.waypoints],
        active_index=msg.active_index,
    )
    await adapter.push_route(route)
    return {"status": "ok"}


@app.post("/ext/v1/command")
async def post_command(cmd: CommandRequest) -> dict:
    """
    Relay simple commands to the adapter.
    """
    await adapter.send_simple_command(cmd.command, cmd.payload)
    return {"status": "ok"}


@app.get("/ext/v1/telemetry/{uav_id}")
async def get_telemetry(uav_id: str) -> dict:
    msg = last_telemetry.get(uav_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Telemetry not found")
    return msg.model_dump()


@app.get("/ext/v1/route/{uav_id}")
async def get_route(uav_id: str) -> dict:
    msg = last_route.get(uav_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Route not found")
    return msg.model_dump()


@app.get("/health")
async def health() -> dict:
    latest_ts = None
    if last_telemetry:
        latest_ts = max(msg.timestamp for msg in last_telemetry.values())
    return {
        "status": "ok",
        "uptime_sec": (datetime.utcnow() - _started_at).total_seconds(),
        "uav_count": len(last_telemetry),
        "last_telemetry_at": latest_ts.isoformat() if latest_ts else None,
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    host = os.getenv("INTEGRATION_HOST", "0.0.0.0")
    port = int(os.getenv("INTEGRATION_PORT", "8081"))
    uvicorn.run("integration_service.app:app", host=host, port=port, reload=False)
