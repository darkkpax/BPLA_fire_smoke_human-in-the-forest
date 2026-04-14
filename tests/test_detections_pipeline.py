from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fire_uav.config import settings
from fire_uav.module_core.detections import DetectionAggregator, DetectionBatchPayload, RawDetectionPayload
from fire_uav.module_core.detections.pipeline import DetectionPipeline
from fire_uav.module_core.schema import TelemetrySample
from fire_uav.utils.time import utc_now


class DummyProjector:
    def project_bbox_to_ground(self, telemetry: TelemetrySample, bbox, width: int, height: int):
        # Straight passthrough for tests
        return telemetry.lat, telemetry.lon


class FakeTransmitter:
    def __init__(self) -> None:
        self.sent = []

    def send(self, payload) -> None:
        self.sent.append(payload)


def _make_batch(frame_id: str, ts: datetime, telemetry: TelemetrySample) -> DetectionBatchPayload:
    det = RawDetectionPayload(
        class_id=1,
        confidence=0.9,
        bbox=(0, 0, 10, 10),
        frame_id=frame_id,
        timestamp=ts,
    )
    return DetectionBatchPayload(
        frame_id=frame_id,
        frame_width=640,
        frame_height=480,
        captured_at=ts,
        telemetry=telemetry,
        detections=[det],
    )


def test_detection_pipeline_creates_notifications(tmp_path: Path) -> None:
    # Point notifications dir to a temp location for the pipeline instance.
    original_notifications = getattr(settings, "notifications_dir", None)
    settings.notifications_dir = tmp_path

    aggregator = DetectionAggregator(
        window=2,
        votes_required=2,
        min_confidence=0.1,
        max_distance_m=50.0,
        ttl_seconds=10.0,
    )
    tx = FakeTransmitter()
    pipeline = DetectionPipeline(
        aggregator=aggregator,
        projector=DummyProjector(),
        transmitter=tx,
        visualizer_adapter=None,
        loop=None,
    )

    telemetry = TelemetrySample(
        lat=55.0,
        lon=37.0,
        alt=120.0,
        yaw=45.0,
        battery=0.9,
    )
    t0 = utc_now()

    # First batch does not meet votes_required yet
    pipeline.process_batch(_make_batch("frame_1", t0, telemetry))
    # Second batch should trigger aggregation and notification
    pipeline.process_batch(_make_batch("frame_2", t0 + timedelta(seconds=1), telemetry))

    notifications = list(tmp_path.rglob("*.json"))
    assert len(notifications) == 1, "Expected one notification JSON file"
    assert tx.sent, "Transmitter should record at least one payload"

    # Registry should contain a single object marked as notified
    registry = pipeline._notification_manager.registry  # type: ignore[attr-defined]
    assert len(registry._objects) == 1
    state = next(iter(registry._objects.values()))
    assert state.notified is True
    assert state.class_id == 1
    assert state.track_id is not None

    # Restore original notification dir to avoid side effects
    if original_notifications is not None:
        settings.notifications_dir = original_notifications
