# mypy: ignore-errors
from __future__ import annotations

import logging
from queue import Queue

import cv2

import fire_uav.infrastructure.providers as deps
from fire_uav.services.bus import Event, bus
from fire_uav.services.components.camera import CameraThread
from fire_uav.services.components.detect import DetectThread
from fire_uav.services.lifecycle.manager import LifecycleManager

_log = logging.getLogger(__name__)


def _camera_available(index: int | str = 0) -> bool:
    cap = cv2.VideoCapture(index)
    ok = cap.isOpened()
    cap.release()
    return ok


def init_module_core(*, fps: int = 30) -> None:
    if deps.lifecycle_manager is not None:
        return

    deps.frame_queue = Queue(maxsize=5)
    deps.dets_queue = Queue(maxsize=5)

    if _camera_available():
        deps.camera_factory = lambda: CameraThread(
            index=0,
            fps=fps,
            out_queue=deps.frame_queue,
        )
        deps.detect_factory = lambda: DetectThread(
            in_q=deps.frame_queue,
            out_q=deps.dets_queue,
        )
    else:
        deps.camera_factory = None
        deps.detect_factory = None

        _log.warning("Camera not found — GUI will start without live feed")

    deps.lifecycle_manager = LifecycleManager()
    bus.subscribe(Event.APP_START, lambda *_: deps.get_lifecycle().start_all())
    bus.subscribe(Event.APP_STOP, lambda *_: deps.get_lifecycle().stop_all())


def init_ground_core(*, fps: int = 30) -> None:
    if deps.lifecycle_manager is not None:
        return

    from fire_uav.ground_app.gui.camera_qt import CameraThread as QtCameraThread

    deps.frame_queue = Queue(maxsize=5)
    deps.dets_queue = Queue(maxsize=5)

    if _camera_available():
        deps.camera_factory = lambda: QtCameraThread(
            index=0,
            fps=fps,
            out_queue=deps.frame_queue,
        )
        deps.detect_factory = lambda: DetectThread(
            in_q=deps.frame_queue,
            out_q=deps.dets_queue,
        )
    else:
        deps.camera_factory = None
        deps.detect_factory = None
        _log.warning("Camera not found - GUI will start without live feed")

    deps.lifecycle_manager = LifecycleManager()
    bus.subscribe(Event.APP_START, lambda *_: deps.get_lifecycle().start_all())
    bus.subscribe(Event.APP_STOP, lambda *_: deps.get_lifecycle().stop_all())


def init_core(*, fps: int = 30) -> None:
    """Backward-compatible alias for the headless module init."""
    init_module_core(fps=fps)
