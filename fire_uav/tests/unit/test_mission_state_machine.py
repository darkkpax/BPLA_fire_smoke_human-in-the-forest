from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace

from fire_uav.services.bus import Event, bus
from fire_uav.services.mission.state import MissionState, MissionStateMachine


def _capture_bus(monkeypatch) -> list[tuple[Event, dict]]:
    events: list[tuple[Event, dict]] = []
    monkeypatch.setattr(bus, "_subs", defaultdict(list))

    def _record(payload, event: Event) -> None:
        events.append((event, payload))

    for event in (
        Event.MISSION_STATE_CHANGED,
        Event.FLIGHT_SESSION_STARTED,
        Event.FLIGHT_SESSION_ENDED,
    ):
        bus.subscribe(event, lambda payload, event=event: _record(payload, event))
    return events


def test_confirm_plan_rejects_too_short_route() -> None:
    machine = MissionStateMachine(
        link_monitor=SimpleNamespace(is_link_ok=lambda: True),
        camera_monitor=SimpleNamespace(is_camera_ok=lambda: True),
    )

    ok = machine.confirm_plan([(47.6060, -122.3350)])

    assert ok is False
    assert machine.plan_confirmed is False
    assert machine.current_state == MissionState.PREFLIGHT


def test_confirm_plan_and_readiness_transition_to_ready(monkeypatch) -> None:
    events = _capture_bus(monkeypatch)
    machine = MissionStateMachine(
        link_monitor=SimpleNamespace(is_link_ok=lambda: True),
        camera_monitor=SimpleNamespace(is_camera_ok=lambda: True),
    )

    ok = machine.confirm_plan([(47.6060, -122.3350), (47.6070, -122.3340)])

    assert ok is True
    assert machine.plan_confirmed is True
    assert machine.current_state == MissionState.READY
    assert events[-1][0] == Event.MISSION_STATE_CHANGED
    assert events[-1][1]["state"] == "READY"


def test_start_flight_emits_session_started(monkeypatch) -> None:
    events = _capture_bus(monkeypatch)
    machine = MissionStateMachine(
        link_monitor=SimpleNamespace(is_link_ok=lambda: True),
        camera_monitor=SimpleNamespace(is_camera_ok=lambda: True),
    )
    machine.confirm_plan([(47.6060, -122.3350), (47.6070, -122.3340)])

    ok = machine.start_flight()

    assert ok is True
    assert machine.current_state == MissionState.IN_FLIGHT
    session_started = [payload for event, payload in events if event == Event.FLIGHT_SESSION_STARTED]
    assert len(session_started) == 1
    assert session_started[0]["plan"] == [(47.6060, -122.3350), (47.6070, -122.3340)]


def test_land_complete_emits_session_ended(monkeypatch) -> None:
    events = _capture_bus(monkeypatch)
    machine = MissionStateMachine(
        link_monitor=SimpleNamespace(is_link_ok=lambda: True),
        camera_monitor=SimpleNamespace(is_camera_ok=lambda: True),
    )
    machine.confirm_plan([(47.6060, -122.3350), (47.6070, -122.3340)])
    machine.start_flight()

    machine.land_complete()

    assert machine.current_state == MissionState.POSTFLIGHT
    session_ended = [payload for event, payload in events if event == Event.FLIGHT_SESSION_ENDED]
    assert len(session_ended) == 1
    assert session_ended[0]["reason"] == "land_complete"


def test_abort_to_preflight_clears_plan_and_emits_session_end(monkeypatch) -> None:
    events = _capture_bus(monkeypatch)
    machine = MissionStateMachine(
        link_monitor=SimpleNamespace(is_link_ok=lambda: True),
        camera_monitor=SimpleNamespace(is_camera_ok=lambda: True),
    )
    machine.confirm_plan([(47.6060, -122.3350), (47.6070, -122.3340)])
    machine.start_flight()

    machine.abort_to_preflight(reason="operator_abort")

    assert machine.current_state == MissionState.PREFLIGHT
    assert machine.plan_confirmed is False
    session_ended = [payload for event, payload in events if event == Event.FLIGHT_SESSION_ENDED]
    assert len(session_ended) == 1
    assert session_ended[0]["reason"] == "operator_abort"
