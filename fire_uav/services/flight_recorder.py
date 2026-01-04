from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fire_uav.module_core.geometry import haversine_m
from fire_uav.module_core.schema import TelemetrySample
from fire_uav.services.bus import Event, bus

log = logging.getLogger(__name__)


@dataclass(slots=True)
class FlightSummary:
    started_at: str | None
    ended_at: str | None
    duration_s: float
    distance_m: float
    min_battery_percent: float | None
    confirmed_objects: int


class FlightRecorder:
    def __init__(self) -> None:
        self._session_dir: Path | None = None
        self._telemetry_fh = None
        self._objects_fh = None
        self._events_fh = None
        self._started_at: datetime | None = None
        self._last_telemetry: TelemetrySample | None = None
        self._distance_m = 0.0
        self._min_battery: float | None = None
        self._objects_seen: set[str] = set()
        self._event_handlers: list[object] = []
        self.last_summary: FlightSummary | None = None

        bus.subscribe(Event.FLIGHT_SESSION_STARTED, self._on_start)
        bus.subscribe(Event.FLIGHT_SESSION_ENDED, self._on_end)
        self._subscribe_event(Event.MISSION_STATE_CHANGED)
        self._subscribe_event(Event.UAV_LINK_STATUS_CHANGED)
        self._subscribe_event(Event.CAMERA_STATUS_CHANGED)
        self._subscribe_event(Event.WARNING_TOAST)
        bus.subscribe(Event.OBJECT_CONFIRMED_UI, self._on_object)

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    def record_telemetry(self, sample: TelemetrySample) -> None:
        if self._telemetry_fh is None:
            return
        payload = sample.model_dump(mode="json")
        self._telemetry_fh.write(json.dumps(payload) + "\n")
        if self._last_telemetry is not None:
            self._distance_m += haversine_m(
                (self._last_telemetry.lat, self._last_telemetry.lon),
                (sample.lat, sample.lon),
            )
        self._last_telemetry = sample
        battery_percent = sample.battery_percent
        if battery_percent is None:
            battery_percent = max(0.0, min(100.0, sample.battery * 100.0))
        if self._min_battery is None or battery_percent < self._min_battery:
            self._min_battery = battery_percent

    # ------------------------------------------------------------------ #
    def _on_start(self, payload: object) -> None:
        if self._session_dir is not None:
            return
        ts = datetime.utcnow()
        root_dir = Path(__file__).resolve().parents[2]
        self._session_dir = root_dir / "data" / "flights" / ts.strftime("%Y-%m-%d_%H-%M-%S")
        self._session_dir.mkdir(parents=True, exist_ok=True)
        plan = {}
        if isinstance(payload, dict):
            plan = {"path": payload.get("plan", [])}
        plan_path = self._session_dir / "plan.json"
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        self._telemetry_fh = (self._session_dir / "telemetry.jsonl").open("a", encoding="utf-8")
        self._objects_fh = (self._session_dir / "objects.jsonl").open("a", encoding="utf-8")
        self._events_fh = (self._session_dir / "events.jsonl").open("a", encoding="utf-8")
        self._started_at = ts
        self._last_telemetry = None
        self._distance_m = 0.0
        self._min_battery = None
        self._objects_seen.clear()
        self.last_summary = None
        self._record_event(Event.FLIGHT_SESSION_STARTED, payload)
        log.info("Flight recorder started at %s", self._session_dir)

    def _on_end(self, payload: object) -> None:
        if self._session_dir is None:
            return
        self._record_event(Event.FLIGHT_SESSION_ENDED, payload)
        ended_at = datetime.utcnow()
        summary = FlightSummary(
            started_at=self._started_at.isoformat() + "Z" if self._started_at else None,
            ended_at=ended_at.isoformat() + "Z",
            duration_s=(ended_at - self._started_at).total_seconds() if self._started_at else 0.0,
            distance_m=self._distance_m,
            min_battery_percent=self._min_battery,
            confirmed_objects=len(self._objects_seen),
        )
        summary_path = self._session_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary.__dict__, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.last_summary = summary
        self._close_files()
        log.info("Flight recorder stopped (%s)", self._session_dir)
        self._session_dir = None

    def _on_object(self, payload: object) -> None:
        if self._objects_fh is None or not isinstance(payload, dict):
            return
        obj_id = str(payload.get("object_id", ""))
        if not obj_id or obj_id in self._objects_seen:
            return
        self._objects_seen.add(obj_id)
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **payload,
        }
        self._objects_fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def _subscribe_event(self, event: Event) -> None:
        def _handler(payload: object) -> None:
            self._on_event(event, payload)

        self._event_handlers.append(_handler)
        bus.subscribe(event, _handler)

    def _on_event(self, event: Event, payload: object) -> None:
        if self._events_fh is None:
            return
        self._record_event(event, payload)

    def _record_event(self, event: Event, payload: object) -> None:
        event_payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": str(event),
            "payload": payload,
        }
        self._events_fh.write(json.dumps(event_payload, ensure_ascii=False, default=str) + "\n")

    def _close_files(self) -> None:
        for fh in (self._telemetry_fh, self._objects_fh, self._events_fh):
            if fh is None:
                continue
            try:
                fh.flush()
                fh.close()
            except Exception:  # noqa: BLE001
                pass
        self._telemetry_fh = None
        self._objects_fh = None
        self._events_fh = None


__all__ = ["FlightRecorder", "FlightSummary"]
