# mypy: ignore-errors
from __future__ import annotations

import queue
from datetime import datetime

import numpy as np

import fire_uav.services.components.detect as detect_mod
from fire_uav.services.bus import Event, bus
from fire_uav.services.components.base import State


class _DummyEngine:  # заменяем тяжёлый YOLO
    def __init__(self, *_, **__) -> None: ...

    def infer(self, frame, *, camera_id="cam0", return_batch=True):
        return {"ok": True, "shape": frame.shape}


def test_detect_thread(monkeypatch) -> None:
    """Поток берёт кадр из очереди и кладёт результат в выходную."""
    monkeypatch.setattr(detect_mod, "DetectionEngine", _DummyEngine)

    in_q: queue.Queue[np.ndarray | None] = queue.Queue()
    out_q: queue.Queue[dict] = queue.Queue()

    thr = detect_mod.DetectThread(in_q=in_q, out_q=out_q)
    thr.start()

    in_q.put(np.zeros((2, 2, 3), dtype=np.uint8))

    res = out_q.get(timeout=1.0)
    assert res["ok"] is True
    assert res["shape"] == (2, 2, 3)

    thr.stop()
    thr.join(timeout=1.0)
    assert thr.state is State.STOPPED


class _Batch:
    def __init__(self, timestamp: datetime) -> None:
        self.frame = type("FrameMeta", (), {"timestamp": timestamp})()
        self.detections = []


class _DummyBatchEngine:
    def __init__(self, *_, **__) -> None: ...

    def infer(self, frame, *, camera_id="cam0", return_batch=True):
        assert camera_id == "unreal_local"
        return _Batch(datetime(2000, 1, 1))


def test_detect_thread_propagates_packet_timestamp(monkeypatch) -> None:
    monkeypatch.setattr(detect_mod, "DetectionEngine", _DummyBatchEngine)

    in_q: queue.Queue[object | None] = queue.Queue()
    out_q: queue.Queue[object] = queue.Queue()
    captured_at = datetime(2026, 3, 8, 12, 0, 0)

    thr = detect_mod.DetectThread(in_q=in_q, out_q=out_q)
    thr.start()

    in_q.put(
        {
            "frame": np.zeros((2, 2, 3), dtype=np.uint8),
            "camera_id": "unreal_local",
            "timestamp": captured_at,
        }
    )

    res = out_q.get(timeout=1.0)
    assert res.frame.timestamp == captured_at

    thr.stop()
    thr.join(timeout=1.0)
    assert thr.state is State.STOPPED


def test_detect_thread_pause_and_resume_via_bus(monkeypatch) -> None:
    monkeypatch.setattr(detect_mod, "DetectionEngine", _DummyEngine)

    in_q: queue.Queue[np.ndarray | None] = queue.Queue()
    out_q: queue.Queue[dict] = queue.Queue()

    thr = detect_mod.DetectThread(in_q=in_q, out_q=out_q)
    thr.start()

    bus.emit(Event.DETECTOR_STOP)
    in_q.put(np.zeros((2, 2, 3), dtype=np.uint8))

    try:
        paused_result = out_q.get(timeout=0.3)
    except queue.Empty:
        paused_result = None
    assert paused_result is None

    bus.emit(Event.DETECTOR_START)
    in_q.put(np.zeros((2, 2, 3), dtype=np.uint8))

    resumed_result = out_q.get(timeout=1.0)
    assert resumed_result["ok"] is True

    thr.stop()
    thr.join(timeout=1.0)
    assert thr.state is State.STOPPED
