from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from fire_uav.api.security import require_ws_api_key
from fire_uav.api.visualizer_api import app, last_objects, last_route, last_telemetry


@app.websocket("/ws/v1/stream")
async def stream_state(ws: WebSocket) -> None:
    """
    Live state stream for visualizers/dashboards.

    Query params:
      - uav_id: optional; if provided only that UAV's state is streamed.
    """
    if not await require_ws_api_key(ws):
        return
    await ws.accept()
    params = ws.query_params
    uav_id = params.get("uav_id")
    try:
        while True:
            if uav_id:
                payload: Any = {
                    "telemetry": last_telemetry.get(uav_id),
                    "route": last_route.get(uav_id),
                    "objects": list(last_objects.get(uav_id, {}).values()),
                }
            else:
                payload = {}
                for uid in set(last_telemetry.keys()) | set(last_route.keys()) | set(last_objects.keys()):
                    payload[uid] = {
                        "telemetry": last_telemetry.get(uid),
                        "route": last_route.get(uid),
                        "objects": list(last_objects.get(uid, {}).values()),
                    }
            await ws.send_text(json.dumps(payload, default=_json_default))
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except TypeError:
            return obj.model_dump()
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


__all__ = ["app"]
