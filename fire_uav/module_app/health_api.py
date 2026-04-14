from __future__ import annotations

from datetime import datetime
from typing import Optional, Set

from fastapi import FastAPI, Response
from prometheus_client import REGISTRY, generate_latest
from fire_uav.utils.time import utc_now


class ModuleHealthState:
    """Tracks runtime health metrics for module_app."""

    def __init__(self) -> None:
        self.start_time: datetime = utc_now()
        self.last_telemetry: Optional[datetime] = None
        self.last_detection: Optional[datetime] = None
        self.unhealthy_reasons: Set[str] = set()

    def mark_start(self) -> None:
        self.start_time = utc_now()

    def update_telemetry(self, ts: Optional[datetime] = None) -> None:
        self.last_telemetry = ts or utc_now()

    def update_detection(self, ts: Optional[datetime] = None) -> None:
        self.last_detection = ts or utc_now()

    def mark_unhealthy(self, reason: str) -> None:
        self.unhealthy_reasons.add(reason)

    def clear_reason(self, reason: str) -> None:
        self.unhealthy_reasons.discard(reason)


class _HealthConfig:
    def __init__(
        self,
        telemetry_timeout_sec: float = 10.0,
        detection_timeout_sec: float = 60.0,
        expect_detections: bool = False,
    ) -> None:
        self.telemetry_timeout_sec = telemetry_timeout_sec
        self.detection_timeout_sec = detection_timeout_sec
        self.expect_detections = expect_detections


health_state = ModuleHealthState()
_health_config = _HealthConfig()

app = FastAPI(title="module_app_health", version="0.1.0")


def configure_health(
    telemetry_timeout_sec: float,
    detection_timeout_sec: float,
    expect_detections: bool,
) -> None:
    """Update thresholds used by the health endpoint."""
    global _health_config
    _health_config = _HealthConfig(
        telemetry_timeout_sec=telemetry_timeout_sec,
        detection_timeout_sec=detection_timeout_sec,
        expect_detections=expect_detections,
    )


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Lightweight health endpoint."""
    now = utc_now()
    telemetry_age = (
        (now - health_state.last_telemetry).total_seconds() if health_state.last_telemetry else None
    )
    detection_age = (
        (now - health_state.last_detection).total_seconds() if health_state.last_detection else None
    )

    status = "ok"
    reasons: Set[str] = set(health_state.unhealthy_reasons)

    if telemetry_age is None or telemetry_age > _health_config.telemetry_timeout_sec:
        reasons.add("telemetry_stale")
        status = "degraded"

    if _health_config.expect_detections:
        if detection_age is None or detection_age > _health_config.detection_timeout_sec:
            reasons.add("detections_stale")
            status = "degraded"

    if health_state.unhealthy_reasons:
        status = "error"

    return {
        "status": status,
        "uptime_sec": (now - health_state.start_time).total_seconds(),
        "last_telemetry": health_state.last_telemetry.isoformat() if health_state.last_telemetry else None,
        "last_detection": health_state.last_detection.isoformat() if health_state.last_detection else None,
        "telemetry_age_sec": telemetry_age,
        "detection_age_sec": detection_age,
        "reasons": sorted(reasons),
    }


@app.get("/metrics", tags=["metrics"])
async def metrics() -> Response:
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type="text/plain; version=0.0.4")


__all__ = ["app", "health_state", "configure_health"]
