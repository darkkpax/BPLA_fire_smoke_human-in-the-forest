from __future__ import annotations

import asyncio
from datetime import timedelta

from fire_uav.module_app import health_api
from fire_uav.module_app.health_api import ModuleHealthState
from fire_uav.utils.time import utc_now


def _fresh_state() -> ModuleHealthState:
    state = ModuleHealthState()
    state.start_time = utc_now() - timedelta(seconds=5)
    return state


def test_health_reports_degraded_when_telemetry_is_stale(monkeypatch) -> None:
    state = _fresh_state()
    monkeypatch.setattr(health_api, "health_state", state)
    health_api.configure_health(telemetry_timeout_sec=10.0, detection_timeout_sec=60.0, expect_detections=False)

    payload = asyncio.run(health_api.health())

    assert payload["status"] == "degraded"
    assert "telemetry_stale" in payload["reasons"]


def test_health_reports_ok_with_fresh_telemetry_when_detections_not_required(monkeypatch) -> None:
    state = _fresh_state()
    state.update_telemetry(utc_now())
    monkeypatch.setattr(health_api, "health_state", state)
    health_api.configure_health(telemetry_timeout_sec=10.0, detection_timeout_sec=60.0, expect_detections=False)

    payload = asyncio.run(health_api.health())

    assert payload["status"] == "ok"
    assert payload["reasons"] == []


def test_health_reports_detection_staleness_when_expected(monkeypatch) -> None:
    state = _fresh_state()
    state.update_telemetry(utc_now())
    state.update_detection(utc_now() - timedelta(seconds=90))
    monkeypatch.setattr(health_api, "health_state", state)
    health_api.configure_health(telemetry_timeout_sec=10.0, detection_timeout_sec=60.0, expect_detections=True)

    payload = asyncio.run(health_api.health())

    assert payload["status"] == "degraded"
    assert "detections_stale" in payload["reasons"]
    assert "telemetry_stale" not in payload["reasons"]


def test_health_reports_error_when_marked_unhealthy(monkeypatch) -> None:
    state = _fresh_state()
    state.update_telemetry(utc_now())
    state.mark_unhealthy("pipeline_crashed")
    monkeypatch.setattr(health_api, "health_state", state)
    health_api.configure_health(telemetry_timeout_sec=10.0, detection_timeout_sec=60.0, expect_detections=False)

    payload = asyncio.run(health_api.health())

    assert payload["status"] == "error"
    assert "pipeline_crashed" in payload["reasons"]
