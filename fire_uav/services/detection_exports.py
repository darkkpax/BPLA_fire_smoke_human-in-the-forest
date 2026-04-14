from __future__ import annotations

from datetime import datetime

from fire_uav.module_core.schema import TelemetrySample


def _isoformat(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001
            return None
    if value is None:
        return None
    return str(value)


def telemetry_snapshot_payload(sample: TelemetrySample | None) -> dict[str, object] | None:
    if sample is None:
        return None
    return {
        "position": {
            "lat": sample.lat,
            "lon": sample.lon,
            "alt": sample.alt,
            "alt_agl": sample.alt_agl,
        },
        "orientation": {
            "yaw": sample.yaw,
            "pitch": sample.pitch,
            "roll": sample.roll,
        },
        "camera_mount": {
            "pitch_deg": sample.camera_mount_pitch_deg,
            "yaw_deg": sample.camera_mount_yaw_deg,
            "roll_deg": sample.camera_mount_roll_deg,
        },
        "captured_at": _isoformat(sample.timestamp),
        "source": sample.source,
    }


def make_raw_detection_log_entry(
    *,
    timestamp: str,
    detections: list[dict[str, object]],
    count: int,
    best_confidence: float,
    best_bbox: list[int] | None,
    classes: list[int],
    telemetry: TelemetrySample | None,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "count": count,
        "best_confidence": best_confidence,
        "best_bbox": best_bbox,
        "classes": classes,
        "detections": detections,
        "summary": {
            "raw_detection_count": count,
            "classes": classes,
            "best_detection": {
                "confidence": best_confidence,
                "bbox": best_bbox,
            },
        },
        "telemetry": telemetry_snapshot_payload(telemetry),
    }


def make_confirmed_detection_log_entry(
    payload: dict[str, object],
    *,
    telemetry: TelemetrySample | None,
) -> dict[str, object]:
    return {
        "object": {
            "id": str(payload.get("object_id", "") or ""),
            "class_id": int(payload.get("class_id", -1) or -1),
            "track_id": payload.get("track_id"),
            "source_id": payload.get("source_id"),
        },
        "geolocation": {
            "lat": float(payload.get("lat", 0.0) or 0.0),
            "lon": float(payload.get("lon", 0.0) or 0.0),
            "alt": payload.get("alt"),
        },
        "confidence": float(payload.get("confidence", 0.0) or 0.0),
        "time": {
            "detected_at": _isoformat(payload.get("timestamp")),
        },
        "telemetry": telemetry_snapshot_payload(telemetry),
    }


__all__ = [
    "make_confirmed_detection_log_entry",
    "make_raw_detection_log_entry",
    "telemetry_snapshot_payload",
]
