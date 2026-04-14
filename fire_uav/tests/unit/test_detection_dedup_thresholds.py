from __future__ import annotations

from fire_uav.module_core.detections.aggregator import DetectionAggregator, DetectionEvent
from fire_uav.module_core.detections.pipeline import DetectionPipeline
from fire_uav.module_core.detections.registry import ObjectRegistry
from fire_uav.module_core.schema import GeoDetection, WorldCoord
from fire_uav.utils.time import utc_now


def test_object_registry_merges_same_fire_when_track_changes_with_large_geo_jitter() -> None:
    registry = ObjectRegistry(spatial_match_radius_m=90.0)
    now = utc_now()
    first = registry.create_or_update(
        GeoDetection(
            class_id=1,
            confidence=0.62,
            lat=47.606000,
            lon=-122.335000,
            timestamp=now,
            track_id=10,
        ),
        uav_id="sim",
        track_id=10,
    )
    second = registry.create_or_update(
        GeoDetection(
            class_id=1,
            confidence=0.71,
            lat=47.606420,
            lon=-122.334820,
            timestamp=now,
            track_id=77,
        ),
        uav_id="sim",
        track_id=77,
    )

    assert second.object_id == first.object_id
    assert second.track_id == 77


def test_detection_pipeline_dedupes_same_fire_with_larger_bbox_and_geo_jitter() -> None:
    pipeline = DetectionPipeline.__new__(DetectionPipeline)
    now = utc_now()
    deduped = pipeline._dedupe_projected_events(
        [
            (
                DetectionEvent(
                    class_id=1,
                    confidence=0.88,
                    location=WorldCoord(lat=47.606000, lon=-122.335000),
                    frame_id="f1",
                    timestamp=now,
                    track_id=10,
                ),
                (500.0, 400.0, 620.0, 560.0),
            ),
            (
                DetectionEvent(
                    class_id=1,
                    confidence=0.74,
                    location=WorldCoord(lat=47.606330, lon=-122.334880),
                    frame_id="f1",
                    timestamp=now,
                    track_id=11,
                ),
                (540.0, 425.0, 655.0, 585.0),
            ),
        ]
    )

    assert len(deduped) == 1
    assert deduped[0].track_id == 10


def test_detection_aggregator_keeps_same_fire_in_one_cluster_with_larger_geo_jitter() -> None:
    now = utc_now()
    aggregator = DetectionAggregator(
        window=4,
        votes_required=2,
        min_confidence=0.4,
        max_distance_m=60.0,
        ttl_seconds=8.0,
    )

    first = aggregator.add_event(
        DetectionEvent(
            class_id=1,
            confidence=0.88,
            location=WorldCoord(lat=47.606000, lon=-122.335000),
            frame_id="f1",
            timestamp=now,
            track_id=10,
        )
    )
    second = aggregator.add_event(
        DetectionEvent(
            class_id=1,
            confidence=0.74,
            location=WorldCoord(lat=47.606420, lon=-122.334820),
            frame_id="f2",
            timestamp=now,
            track_id=11,
        )
    )

    assert first is None
    assert second is not None
    assert abs(second.lat - 47.606210) < 0.0002


def test_object_registry_keeps_reappeared_fire_as_new_object_after_moderate_shift() -> None:
    registry = ObjectRegistry(spatial_match_radius_m=45.0)
    now = utc_now()
    first = registry.create_or_update(
        GeoDetection(
            class_id=1,
            confidence=0.62,
            lat=47.606000,
            lon=-122.335000,
            timestamp=now,
            track_id=10,
        ),
        uav_id="sim",
        track_id=10,
    )
    second = registry.create_or_update(
        GeoDetection(
            class_id=1,
            confidence=0.71,
            lat=47.606500,
            lon=-122.334820,
            timestamp=now,
            track_id=77,
        ),
        uav_id="sim",
        track_id=77,
    )

    assert second.object_id != first.object_id
