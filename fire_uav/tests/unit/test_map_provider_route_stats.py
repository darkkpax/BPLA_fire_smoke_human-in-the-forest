from __future__ import annotations

from types import SimpleNamespace

from fire_uav.gui import map_providers
from fire_uav.gui.map_providers import OpenLayersMapProvider


def test_route_stats_payload_prefers_runtime_route_stats(monkeypatch) -> None:
    provider = OpenLayersMapProvider()
    telemetry = SimpleNamespace(
        lat=47.6062,
        lon=-122.3348,
        alt=120.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.75,
        battery_percent=75.0,
    )
    monkeypatch.setattr(
        map_providers.deps,
        "route_stats",
        {
            "max_distance_m": 4200.0,
            "reserved_percent": 30.0,
            "available_percent": 75.0,
            "base": [-122.3333, 47.6055],
        },
        raising=False,
    )

    payload = provider._route_stats_payload([(47.6060, -122.3350), (47.6070, -122.3340)], telemetry)

    assert payload == {
        "max_distance_m": 4200.0,
        "reserved_percent": 30.0,
        "available_percent": 75.0,
        "base": [-122.3333, 47.6055],
    }


def test_route_stats_payload_ignores_stale_home_and_uses_route_start(monkeypatch) -> None:
    provider = OpenLayersMapProvider()
    telemetry = SimpleNamespace(
        lat=47.6062,
        lon=-122.3348,
        alt=120.0,
        yaw=0.0,
        pitch=0.0,
        roll=0.0,
        battery=0.81,
        battery_percent=81.0,
    )
    monkeypatch.setattr(map_providers.deps, "route_stats", None, raising=False)
    monkeypatch.setattr(map_providers.settings, "home_lat", 56.0153, raising=False)
    monkeypatch.setattr(map_providers.settings, "home_lon", 92.8932, raising=False)
    monkeypatch.setattr(map_providers.settings, "base_lat", 56.0200, raising=False)
    monkeypatch.setattr(map_providers.settings, "base_lon", 92.9100, raising=False)
    monkeypatch.setattr(map_providers.settings, "max_flight_distance_m", 0.0, raising=False)
    monkeypatch.setattr(map_providers.settings, "min_return_percent", 20.0, raising=False)

    payload = provider._route_stats_payload([(47.6060, -122.3350), (47.6070, -122.3340)], telemetry)

    assert payload["available_percent"] == 81.0
    assert payload["base"] == [-122.3350, 47.6060]


def test_route_stats_payload_falls_back_to_map_center_without_route_or_telemetry(monkeypatch) -> None:
    provider = OpenLayersMapProvider()
    monkeypatch.setattr(map_providers.deps, "route_stats", None, raising=False)
    monkeypatch.setattr(map_providers.settings, "home_lat", None, raising=False)
    monkeypatch.setattr(map_providers.settings, "home_lon", None, raising=False)
    monkeypatch.setattr(map_providers.settings, "base_lat", None, raising=False)
    monkeypatch.setattr(map_providers.settings, "base_lon", None, raising=False)
    monkeypatch.setattr(map_providers.settings, "map_center", [56.02, 92.9], raising=False)
    monkeypatch.setattr(map_providers.settings, "max_flight_distance_m", 15000.0, raising=False)
    monkeypatch.setattr(map_providers.settings, "min_return_percent", 20.0, raising=False)

    payload = provider._route_stats_payload([], None)

    assert payload["base"] == [92.9, 56.02]
    assert payload["available_percent"] == 100.0
