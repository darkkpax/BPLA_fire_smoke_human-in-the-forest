from __future__ import annotations

from typing import Any

from fire_uav.gui.services.unreal_link_service import _Backoff, UnrealLinkService


def _new_service() -> UnrealLinkService:
    svc = UnrealLinkService.__new__(UnrealLinkService)
    svc._object_emit_ts = {}
    svc._camera_info_fetched = False
    svc._on_camera_info = None
    return svc


def test_parse_bounds_dict_accepts_pascal_case_keys() -> None:
    bounds = UnrealLinkService._parse_bounds_dict(
        {
            "LatMin": "55.1000",
            "LonMin": 36.2,
            "LatMax": 55.9,
            "LonMax": "36.99",
        }
    )
    assert bounds is not None
    assert bounds.lat_min == 55.1
    assert bounds.lon_min == 36.2
    assert bounds.lat_max == 55.9
    assert bounds.lon_max == 36.99


def test_normalize_detections_maps_class_name_and_stable_source_id() -> None:
    svc = _new_service()
    batch, objects = svc._normalize_detections(
        [
            {"class": "Fire", "lat": 55.12345678, "lon": 37.76543219},
            {"class": "Human", "source_id": "track-7", "lat": 55.2, "lon": 37.3},
            {"cls": "9", "lat": 55.3, "lon": 37.4},
        ]
    )

    assert [det.class_id for det in batch.detections] == [1, 2, 9]
    assert objects[0]["source_id"] == "auto:1:55.123457:37.765432"
    assert objects[0]["object_id"] == "auto:1:55.123457:37.765432"
    assert objects[1]["source_id"] == "track-7"
    assert objects[1]["class_id"] == 2
    assert objects[2]["class_id"] == 9


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"{}" if payload is not None else b""

    def json(self) -> dict[str, Any]:
        return self._payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def get(self, _url: str) -> _FakeResponse:
        return self._response


class _RouteClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str) -> _FakeResponse:
        self.calls.append(url)
        if url.endswith("/sim/v1/telemetry"):
            return _FakeResponse(
                200,
                {
                    "uav_id": "sim",
                    "timestamp": "2026-03-03T00:00:00Z",
                    "lat": 56.0,
                    "lon": 92.9,
                    "alt": 100.0,
                    "yaw": 0.0,
                    "pitch": 0.0,
                    "roll": 0.0,
                    "battery": 50.0,
                },
            )
        if url.endswith("/sim/v1/camera_info"):
            return _FakeResponse(
                200,
                {
                    "FOVAngle": 80.0,
                    "base_mount_pitch_deg": -95.0,
                    "mount_yaw_deg": 1.0,
                    "mount_roll_deg": -2.0,
                },
            )
        return _FakeResponse(404, {})


def test_poll_telemetry_503_sets_waiting_for_route_without_disconnect() -> None:
    svc = _new_service()
    svc.base_url = "http://localhost:9000"
    svc._client = _FakeClient(_FakeResponse(503, {"heading": 42.0}))
    svc._telemetry_backoff = _Backoff()
    svc._on_telemetry = None
    svc._on_link_status = None
    svc._last_status = "connected"

    svc._poll_telemetry()

    assert svc._last_status == "waiting_for_route"


def test_normalize_camera_info_payload_accepts_unreal_aliases() -> None:
    payload = UnrealLinkService._normalize_camera_info_payload(
        {
            "FOVAngle": "79.5",
            "camera_mount_pitch_deg": -92.0,
            "camera_mount_yaw_deg": "-3.5",
            "camera_mount_roll_deg": 0.25,
        }
    )
    assert payload == {
        "fov_deg": 79.5,
        "mount_pitch_deg": 92.0,
        "mount_yaw_deg": -3.5,
        "mount_roll_deg": 0.25,
    }


def test_poll_telemetry_fetches_camera_info_once() -> None:
    svc = _new_service()
    svc.base_url = "http://localhost:9000"
    svc._client = _RouteClient()
    svc._telemetry_backoff = _Backoff()
    svc._on_telemetry = None
    svc._on_link_status = None
    captured: list[dict[str, Any]] = []
    svc._on_camera_info = lambda payload: captured.append(payload)
    svc._last_status = "disconnected"

    svc._poll_telemetry()
    svc._poll_telemetry()

    assert svc._camera_info_fetched is True
    assert len(captured) == 1
    assert captured[0]["fov_deg"] == 80.0
    assert captured[0]["mount_pitch_deg"] == 95.0
