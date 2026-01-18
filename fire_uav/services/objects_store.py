from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from fire_uav.services.bus import Event, bus

@dataclass(slots=True)
class ConfirmedObject:
    object_id: str
    class_id: int
    confidence: float
    lat: float
    lon: float
    track_id: int | None
    timestamp: datetime | None


log = logging.getLogger(__name__)

class ConfirmedObjectsStore:
    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._objects: dict[str, ConfirmedObject] = {}
        self._order: list[str] = []
        self._selected_id: str | None = None
        self._on_change = on_change
        bus.subscribe(Event.OBJECT_CONFIRMED_UI, self._on_confirmed)

    def all(self) -> list[ConfirmedObject]:
        return [self._objects[obj_id] for obj_id in self._order if obj_id in self._objects]

    def count(self) -> int:
        return len(self._objects)

    def get(self, object_id: str) -> ConfirmedObject | None:
        return self._objects.get(object_id)

    def selected(self) -> ConfirmedObject | None:
        if self._selected_id is None:
            return None
        return self._objects.get(self._selected_id)

    def set_selected(self, object_id: str | None) -> None:
        self._selected_id = object_id if object_id in self._objects else None

    def latest(self) -> ConfirmedObject | None:
        if not self._order:
            return None
        return self._objects.get(self._order[-1])

    def clear(self) -> None:
        self._objects.clear()
        self._order.clear()
        self._selected_id = None
        if self._on_change:
            self._on_change()

    # ------------------------------------------------------------------ #
    def _on_confirmed(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        object_id = str(payload.get("object_id", ""))
        if not object_id:
            return
        obj = ConfirmedObject(
            object_id=object_id,
            class_id=int(payload.get("class_id", -1)),
            confidence=float(payload.get("confidence", 0.0)),
            lat=float(payload.get("lat", 0.0)),
            lon=float(payload.get("lon", 0.0)),
            track_id=payload.get("track_id"),
            timestamp=payload.get("timestamp"),
        )
        is_new = object_id not in self._objects
        self._objects[object_id] = obj
        if is_new:
            self._order.append(object_id)
            if object_id.startswith("manual-"):
                log.info(
                    "MANUAL_SPAWN stored id=%s total=%s",
                    object_id,
                    self.count(),
                )
        if self._on_change:
            self._on_change()


__all__ = ["ConfirmedObjectsStore", "ConfirmedObject"]
