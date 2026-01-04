from __future__ import annotations

import json
from pathlib import Path

from fire_uav.module_core.detections.notifications import JsonNotificationWriter
from fire_uav.module_core.detections.registry import ObjectRegistry
from fire_uav.module_core.schema import GeoDetection


def test_notification_writer_creates_file(tmp_path: Path) -> None:
    registry = ObjectRegistry()
    writer = JsonNotificationWriter(tmp_path)

    detection = GeoDetection(
        class_id=2,
        confidence=0.88,
        lat=55.0,
        lon=37.0,
        alt=120.0,
        frame_id="frame_10",
    )

    state = registry.create_or_update(detection, uav_id="uav1", track_id=1)
    path = writer.write_notification(state)

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["object_id"] == state.object_id
    assert data["class_id"] == 2
    assert data["lat"] == 55.0
    assert data["lon"] == 37.0
    assert data["uav_id"] == "uav1"
