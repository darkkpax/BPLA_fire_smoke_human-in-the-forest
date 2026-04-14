from __future__ import annotations

import json
import importlib
from types import SimpleNamespace
from pathlib import Path

import pytest

from fire_uav.module_core.adapters import (
    CustomSdkUavAdapter,
    MavlinkUavAdapter,
    StubUavAdapter,
    UnrealSimUavAdapter,
)
from fire_uav.module_core.drivers.registry import create_driver, resolve_driver_type

settings_module = importlib.import_module("fire_uav.config.settings")


def _make_cfg(**overrides) -> SimpleNamespace:
    base = {
        "driver_type": "",
        "uav_backend": "stub",
        "map_center": [55.5, 66.6],
        "mavlink_connection_string": "udp:127.0.0.1:14550",
        "unreal_base_url": "http://127.0.0.1:9000/",
        "uav_id": None,
        "custom_sdk_config": {"token": "secret"},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_resolve_driver_type_prefers_driver_type() -> None:
    cfg = _make_cfg(driver_type="MAVLINK", uav_backend="stub")
    assert resolve_driver_type(cfg) == "mavlink"


def test_resolve_driver_type_falls_back_to_backend() -> None:
    cfg = _make_cfg(driver_type=" ", uav_backend="Unreal")
    assert resolve_driver_type(cfg) == "unreal"


def test_resolve_driver_type_defaults_to_stub() -> None:
    cfg = _make_cfg(driver_type="", uav_backend="")
    assert resolve_driver_type(cfg) == "stub"


def test_create_driver_stub_uses_map_center() -> None:
    cfg = _make_cfg(driver_type="stub", map_center=[12.34, 56.78])
    adapter = create_driver(cfg)
    assert isinstance(adapter, StubUavAdapter)
    assert adapter.default_lat == 12.34
    assert adapter.default_lon == 56.78


def test_create_driver_mavlink_uses_connection_string() -> None:
    cfg = _make_cfg(driver_type="mavlink", mavlink_connection_string="udp:10.0.0.1:14550")
    adapter = create_driver(cfg)
    assert isinstance(adapter, MavlinkUavAdapter)
    assert adapter.connection_string == "udp:10.0.0.1:14550"


def test_create_driver_unreal_uses_defaults() -> None:
    cfg = _make_cfg(driver_type="unreal", unreal_base_url="http://host:9000/")
    adapter = create_driver(cfg)
    assert isinstance(adapter, UnrealSimUavAdapter)
    assert adapter.base_url == "http://host:9000"
    assert adapter.uav_id == "sim"


def test_create_driver_custom_uses_sdk_config() -> None:
    cfg = _make_cfg(driver_type="custom", custom_sdk_config={"endpoint": "http://sdk"})
    adapter = create_driver(cfg)
    assert isinstance(adapter, CustomSdkUavAdapter)
    assert adapter.client_config == {"endpoint": "http://sdk"}


def test_create_driver_unknown_raises() -> None:
    cfg = _make_cfg(driver_type="unknown")
    with pytest.raises(ValueError):
        create_driver(cfg)


def test_apply_profile_overrides_does_not_clobber_explicit_values() -> None:
    data = {"log_level": "WARNING", "visualizer_enabled": True, "use_native_core": False}
    result = settings_module._apply_profile_overrides(data, "jetson")
    assert result["log_level"] == "WARNING"
    assert result["visualizer_enabled"] is True
    assert result["use_native_core"] is False


def test_load_settings_applies_jetson_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_load() -> dict:
        return {"profile": "dev"}

    monkeypatch.setenv("FIRE_UAV_PROFILE", "jetson")
    monkeypatch.setattr(settings_module, "_load_settings", _fake_load)
    settings = settings_module.load_settings()
    assert settings.profile == "jetson"
    assert settings.use_native_core is True
    assert settings.visualizer_enabled is False
    assert settings.log_level == "INFO"


def test_settings_defaults_match_settings_default_json() -> None:
    raw = json.loads(Path("fire_uav/config/settings_default.json").read_text(encoding="utf-8"))
    defaults = settings_module.Settings()

    expected = {
        "unreal_video_mode": "h264_stream",
        "unreal_video_target_fps": 60.0,
        "unreal_camera_hz": 60.0,
        "unreal_telemetry_hz": 60.0,
        "visualizer_enabled": True,
        "log_level": "WARNING",
        "map_center": [56.02, 92.9],
        "home_lat": None,
        "home_lon": None,
        "base_lat": None,
        "base_lon": None,
        "cruise_speed_mps": 12.0,
        "power_cruise_w": 45.0,
        "battery_wh": 77.0,
        "max_flight_distance_m": 0.0,
        "yolo_model": "data/models/best_yolo11.pt",
        "yolo_conf": 0.15,
        "yolo_classes": [0, 1],
        "agg_window": 3,
        "agg_votes_required": 1,
        "agg_min_confidence": 0.4,
    }

    for key, value in expected.items():
        assert raw[key] == value
        assert getattr(defaults, key) == value
