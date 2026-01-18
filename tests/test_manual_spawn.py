from fire_uav.services.bus import Event, bus
from fire_uav.services.objects_store import ConfirmedObjectsStore


def test_manual_spawn_updates_store() -> None:
    """ConfirmedObjectsStore should record payloads emitted by manual spawn."""
    changes: list[str] = []
    store = ConfirmedObjectsStore(on_change=lambda: changes.append("updated"))

    payload = {
        "object_id": "manual-test-1",
        "class_id": 2,
        "confidence": 0.95,
        "lat": 10.5,
        "lon": 20.25,
        "track_id": None,
        "timestamp": None,
    }
    store._on_confirmed(payload)

    obj = store.get(payload["object_id"])
    assert obj is not None
    assert obj.lat == payload["lat"]
    assert obj.lon == payload["lon"]
    assert changes == ["updated"]
    assert store.count() == 1

    listeners = bus._subs.get(str(Event.OBJECT_CONFIRMED_UI), [])
    if store._on_confirmed in listeners:
        listeners.remove(store._on_confirmed)
