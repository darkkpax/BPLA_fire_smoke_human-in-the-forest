from __future__ import annotations

from dataclasses import dataclass

from fire_uav.module_core.schema import TelemetrySample


@dataclass
class TelemetryEnvelope:
    uav_id: str
    sample: TelemetrySample


class TelemetryStore:
    """Keeps the latest telemetry per UAV for UI throttling."""

    def __init__(self) -> None:
        self._latest: dict[str, TelemetrySample] = {}

    def update(self, uav_id: str, sample: TelemetrySample) -> None:
        self._latest[uav_id] = sample

    def items(self) -> list[TelemetryEnvelope]:
        return [TelemetryEnvelope(uav_id, sample) for uav_id, sample in self._latest.items()]
