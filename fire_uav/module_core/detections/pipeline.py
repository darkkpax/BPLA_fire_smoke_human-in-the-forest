from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable, List, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from fire_uav.config import settings
from fire_uav.domain.video.camera import CameraParams
from fire_uav.module_core.detections.aggregator import DetectionAggregator, DetectionEvent
from fire_uav.module_core.detections.manager import ObjectNotificationManager
from fire_uav.module_core.detections.notifications import JsonNotificationWriter
from fire_uav.module_core.detections.registry import ObjectRegistry
from fire_uav.module_core.detections.smoothing import build_smoother
from fire_uav.module_core.factories import get_geo_projector
from fire_uav.module_core.interfaces.geo import IGeoProjector
from fire_uav.module_core.schema import GeoDetection, TelemetrySample, WorldCoord
from fire_uav.services.telemetry.transmitter import Transmitter

logger = logging.getLogger(__name__)


class RawDetectionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    class_id: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: Tuple[int, int, int, int]
    frame_id: str
    timestamp: datetime
    track_id: int | None = None


class DetectionBatchPayload(BaseModel):
    frame_id: str
    frame_width: int = Field(..., gt=0)
    frame_height: int = Field(..., gt=0)
    captured_at: datetime
    telemetry: TelemetrySample
    detections: List[RawDetectionPayload]


class DetectionPipeline:
    """
    Связывает сырые детекции модели с телеметрией, выполняет агрегацию
    и отправляет подтверждённые цели на наземную станцию.
    """

    def __init__(
        self,
        *,
        aggregator: DetectionAggregator | None = None,
        projector: IGeoProjector | None = None,
        transmitter: Transmitter | None = None,
        camera_params: CameraParams | None = None,
        visualizer_adapter=None,
        loop=None,
        detection_callback: Callable[[datetime], None] | None = None,
    ) -> None:
        self.aggregator = aggregator or DetectionAggregator(
            window=settings.agg_window,
            votes_required=settings.agg_votes_required,
            min_confidence=settings.agg_min_confidence,
            max_distance_m=settings.agg_max_distance_m,
            ttl_seconds=settings.agg_ttl_seconds,
        )
        # Prefer native geo projector when available; falls back to Python implementation.
        self.projector = projector or get_geo_projector(settings)
        self.transmitter = transmitter
        self._smoother = build_smoother(settings)
        self._registry = ObjectRegistry()
        notifications_dir = Path(getattr(settings, "notifications_dir", "data/notifications"))
        self._notification_manager = ObjectNotificationManager(
            registry=self._registry,
            writer=JsonNotificationWriter(notifications_dir),
            logger=logger,
            uav_id=getattr(settings, "uav_id", None),
        )
        self._lock = Lock()
        self._visualizer = visualizer_adapter
        self._loop = loop
        self._detection_callback = detection_callback

    def process_batch(self, payload: DetectionBatchPayload) -> List[GeoDetection]:
        if not payload.detections:
            return []

        events: List[DetectionEvent] = []
        smoothed = self._smoother.assign_and_smooth(payload.detections)
        for det, smoothed_bbox, track_id in smoothed:
            lat, lon = self.projector.project_bbox_to_ground(
                payload.telemetry,
                smoothed_bbox,
                payload.frame_width,
                payload.frame_height,
            )
            coord = WorldCoord(lat=lat, lon=lon)
            events.append(
                DetectionEvent(
                    class_id=det.class_id,
                    confidence=det.confidence,
                    location=coord,
                    frame_id=det.frame_id or payload.frame_id,
                    timestamp=det.timestamp or payload.captured_at,
                    track_id=track_id,
                )
            )

        if self.aggregator is None:
            return []

        with self._lock:
            aggregated = self.aggregator.add_many(events)

        if aggregated:
            for det in aggregated:
                self._notification_manager.handle_confirmed_detection(det)
                self._publish_visualizer(det)
            if self._detection_callback:
                self._detection_callback(aggregated[-1].timestamp or datetime.utcnow())
        self._transmit(aggregated)
        return aggregated

    # ------------------------------------------------------------------ #
    def _transmit(self, detections: Sequence[GeoDetection]) -> None:
        if not self.transmitter or not detections:
            return
        for det in detections:
            payload = {
                "class_id": det.class_id,
                "confidence": det.confidence,
                "lat": det.lat,
                "lon": det.lon,
                "timestamp": det.timestamp.isoformat(),
                "frame": det.frame_id,
            }
            try:
                self.transmitter.send(payload)
                logger.info(
                    "Sent to ground station: cls=%s conf=%.2f lat=%.6f lon=%.6f",
                    det.class_id,
                    det.confidence,
                    det.lat,
                    det.lon,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Failed to transmit detection")

    def _publish_visualizer(self, det: GeoDetection) -> None:
        if not self._visualizer:
            return
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._visualizer.publish_object(det), self._loop)
        else:
            logger.debug("Visualizer adapter provided without event loop; skipping publish_object.")
