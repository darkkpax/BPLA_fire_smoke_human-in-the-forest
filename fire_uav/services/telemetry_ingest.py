"""Shared telemetry ingest hook for adapters and sim_api."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from fire_uav.module_core.contract.mappers import telemetry_v1_to_sample
from fire_uav.module_core.contract.v1 import TelemetryV1
from fire_uav.module_core.schema import TelemetrySample


@dataclass(slots=True)
class TelemetryIngestContext:
    link_monitor: object | None = None
    planner: object | None = None
    health_state_updater: Callable[[datetime], None] | None = None
    flight_recorder: object | None = None
    visualizer: object | None = None
    on_sample: Callable[[TelemetrySample], None] | None = None


async def ingest_telemetry(
    sample: TelemetrySample | TelemetryV1, *, context: TelemetryIngestContext
) -> None:
    """Apply a telemetry sample to core services in a consistent order."""
    if isinstance(sample, TelemetryV1):
        sample = telemetry_v1_to_sample(sample)
    if context.planner is not None:
        try:
            context.planner.latest_telemetry = sample
        except Exception:
            pass
    if context.link_monitor is not None:
        try:
            context.link_monitor.on_telemetry(sample)
        except Exception:
            pass
    if context.health_state_updater is not None:
        try:
            context.health_state_updater(sample.timestamp)
        except Exception:
            pass
    if context.flight_recorder is not None:
        try:
            context.flight_recorder.record_telemetry(sample)
        except Exception:
            pass
    if context.on_sample is not None:
        try:
            context.on_sample(sample)
        except Exception:
            pass
    if context.visualizer is not None:
        try:
            await context.visualizer.publish_telemetry(sample)
        except Exception:
            pass


__all__ = ["TelemetryIngestContext", "ingest_telemetry"]
