from __future__ import annotations

import os
from typing import Dict

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

from fire_uav.api.security import require_api_key
from fire_uav.core.protocol import (
    MapBounds,
    MapSnapshotInfo,
    ObjectMessage,
    RouteMessage,
    TelemetryMessage,
    make_map_snapshot_info,
)

app = FastAPI(
    title="UAV Visualizer API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    dependencies=[Depends(require_api_key)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=512)
Instrumentator().instrument(app).expose(app)

last_telemetry: dict[str, TelemetryMessage] = {}
last_route: dict[str, RouteMessage] = {}
last_objects: dict[str, dict[str, ObjectMessage]] = {}
current_map_snapshot: Dict[str, MapSnapshotInfo] = {}


class MapSnapshotRequest(BaseModel):
    uav_id: str
    image_path: str
    bounds: MapBounds


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "uav_visualizer_api"}


@app.get("/health", tags=["health"])
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "uav_count": len(last_telemetry),
        "routes": len(last_route),
        "objects": sum(len(bucket) for bucket in last_objects.values()),
        "last_updates": {
            uid: msg.timestamp.isoformat() for uid, msg in last_telemetry.items()
        },
    }


@app.post("/api/v1/telemetry")
def ingest_telemetry(msg: TelemetryMessage) -> dict[str, str]:
    last_telemetry[msg.uav_id] = msg
    return {"status": "ok"}


@app.post("/api/v1/route")
def ingest_route(msg: RouteMessage) -> dict[str, str]:
    last_route[msg.uav_id] = msg
    return {"status": "ok"}


@app.post("/api/v1/object")
def ingest_object(msg: ObjectMessage) -> dict[str, str]:
    bucket = last_objects.setdefault(msg.uav_id, {})
    bucket[msg.object_id] = msg
    return {"status": "ok"}


@app.post("/api/v1/map_snapshot")
async def ingest_map_snapshot(req: MapSnapshotRequest) -> dict[str, str]:
    """
    Register or update a static map snapshot for a given UAV.

    The image file must already exist at req.image_path and be accessible
    to this service.
    """
    if not (req.bounds.lat_min < req.bounds.lat_max and req.bounds.lon_min < req.bounds.lon_max):
        raise HTTPException(
            status_code=400, detail="invalid bounds: lat_min/lat_max or lon_min/lon_max"
        )
    if not os.path.exists(req.image_path):
        raise HTTPException(
            status_code=400, detail=f"image_path does not exist: {req.image_path}"
        )
    info = make_map_snapshot_info(
        uav_id=req.uav_id,
        image_path=req.image_path,
        bounds=req.bounds,
    )
    current_map_snapshot[req.uav_id] = info
    return {"status": "ok", "uav_id": req.uav_id, "timestamp": info.timestamp.isoformat()}


@app.get("/api/v1/telemetry/{uav_id}")
def get_telemetry(uav_id: str) -> TelemetryMessage:
    if uav_id not in last_telemetry:
        raise HTTPException(status_code=404, detail="telemetry not found")
    return last_telemetry[uav_id]


@app.get("/api/v1/route/{uav_id}")
def get_route(uav_id: str) -> RouteMessage:
    if uav_id not in last_route:
        raise HTTPException(status_code=404, detail="route not found")
    return last_route[uav_id]


@app.get("/api/v1/objects/{uav_id}")
def get_objects(uav_id: str) -> list[ObjectMessage]:
    bucket = last_objects.get(uav_id, {})
    return list(bucket.values())


@app.get("/api/v1/map_snapshot/{uav_id}", response_model=MapSnapshotInfo)
async def get_map_snapshot(uav_id: str) -> MapSnapshotInfo:
    """
    Return the latest registered map snapshot for the given UAV.
    """
    info = current_map_snapshot.get(uav_id)
    if info is None:
        raise HTTPException(status_code=404, detail="map snapshot not found")
    return info


__all__ = [
    "app",
    "last_telemetry",
    "last_route",
    "last_objects",
    "current_map_snapshot",
]
