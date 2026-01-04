## UAV Visualizer API (for Unreal / tools)

The visualizer API exposes lightweight UAV state (telemetry, route, confirmed objects) for external engines such as Unreal. Run it on the ground machine (e.g. `uvicorn fire_uav.api.visualizer_api:app --host 0.0.0.0 --port 8000`).

Base URL: `http://127.0.0.1:8000`

### Endpoints

- `GET /api/v1/telemetry/{uav_id}` – latest telemetry  
  Example response:
  ```json
  {
    "type": "telemetry",
    "uav_id": "uav1",
    "timestamp": "2024-01-01T12:00:00Z",
    "lat": 55.0,
    "lon": 37.0,
    "alt": 120.0,
    "yaw": 90.0,
    "battery": 0.82
  }
  ```

- `GET /api/v1/route/{uav_id}` – current route  
  ```json
  {
    "type": "route",
    "uav_id": "uav1",
    "version": 1,
    "waypoints": [
      { "lat": 55.0, "lon": 37.0, "alt": 120.0 },
      { "lat": 55.001, "lon": 37.002, "alt": 120.0 }
    ],
    "active_index": 0
  }
  ```

- `GET /api/v1/objects/{uav_id}` – confirmed objects list  
  ```json
  [
    {
      "type": "object",
      "uav_id": "uav1",
      "object_id": "obj_000001",
      "class_id": 1,
      "confidence": 0.91,
      "lat": 55.0005,
      "lon": 37.0005,
      "alt": 90.0,
      "status": "confirmed"
    }
  ]
  ```

### Map Snapshot

Use these endpoints to register a static map image (PNG/JPG) with known geographic bounds.

- `POST /api/v1/map_snapshot` – register/update map snapshot metadata  
  Body:
  ```json
  {
    "uav_id": "uav_1",
    "image_path": "/path/to/snapshot.png",
    "bounds": {
      "lat_min": 55.0000,
      "lon_min": 37.0000,
      "lat_max": 55.0100,
      "lon_max": 37.0100
    }
  }
  ```
  Behavior:
  - Registers or updates the snapshot for the given UAV.
  - `image_path` must point to a PNG/JPEG file accessible to `visualizer_api`.

- `GET /api/v1/map_snapshot/{uav_id}` – fetch current snapshot  
  Example response:
  ```json
  {
    "uav_id": "uav_1",
    "image_path": "/path/to/snapshot.png",
    "bounds": {
      "lat_min": 55.0000,
      "lon_min": 37.0000,
      "lat_max": 55.0100,
      "lon_max": 37.0100
    },
    "timestamp": "2025-01-01T12:00:00Z"
  }
  ```

Suggested Unreal flow:
1. Capture a top-down orthographic screenshot and save it to disk.
2. Call `POST /api/v1/map_snapshot` with the image path and known bounds.
3. Set `map_provider="static_image"` in the GUI settings to render the snapshot.

### Message fields
- **TelemetryMessage:** `type`, `uav_id`, `timestamp`, `lat`, `lon`, `alt`, `yaw`, `battery`.
- **RouteMessage:** `type`, `uav_id`, `version`, `waypoints[] {lat, lon, alt}`, `active_index`.
- **ObjectMessage:** `type`, `uav_id`, `object_id`, `class_id`, `confidence`, `lat`, `lon`, `alt`, `status`.

### Using with Unreal Engine Blueprints
1. Add an HTTP plugin (e.g. VaRest). Poll endpoints every 0.1–0.2 s.
2. Parse JSON into Blueprint structs (TelemetryMessage, RouteMessage, ObjectMessage).
3. Move your UAV actor along `route.waypoints`, highlighting `active_index`.
4. Spawn markers/decals for entries from `/objects/{uav_id}`.

Flat-earth lat/lon → Unreal mapping (choose reference `lat0`, `lon0` at level load):
- `dLat = lat - lat0`
- `dLon = lon - lon0`
- `y_m = dLat * 111000`
- `x_m = dLon * 111000 * cos(lat0 radians)`
- Map to Unreal (1 UU = 1 cm): `X = x_m * 100`, `Y = y_m * 100`, `Z = alt * 100`.

The API is read-only for visualization; mission logic stays in Python (module/ground apps).

## Unreal simulation control API

The UnrealSimUavAdapter (Python) talks to a separate Unreal-side bridge over HTTP to drive a simulated UAV. The bridge can be implemented in Blueprints, C++, or a small Python service.

Base URL: `http://127.0.0.1:9000` (matches `settings.unreal_base_url`).

- `GET /sim/v1/telemetry` – returns a `TelemetryMessage` JSON:
  ```json
  {
    "type": "telemetry",
    "uav_id": "sim",
    "timestamp": "2024-01-01T12:00:00Z",
    "lat": 55.0,
    "lon": 37.0,
    "alt": 120.0,
    "yaw": 90.0,
    "battery": 0.82
  }
  ```
- `POST /sim/v1/route` – accepts a `RouteMessage` JSON with `waypoints[]` and `active_index` to move the simulated UAV along a path.
- `POST /sim/v1/command` – accepts:
  ```json
  { "uav_id": "sim", "command": "RESET", "payload": {} }
  ```

This control API is independent from the read-only `visualizer_api`: it drives the simulation (telemetry polling + route/command pushes), while `visualizer_api` stays for visualization of real flights.

### Local testing bridge (Python)

The repository ships a minimal bridge stub that implements the same `/sim/v1/*` contract and simulates a UAV moving along uploaded waypoints. It is useful when Unreal is not available yet or as a reference for Blueprint/C++ code.

```bash
UNREAL_BRIDGE_PORT=9000 python scripts/unreal_bridge_stub.py
# or: uvicorn scripts.unreal_bridge_stub:app --host 0.0.0.0 --port 9000
```

Steps to try end-to-end with the module runtime:
1. Start the stub (see above).
2. Set `uav_backend=unreal` and `unreal_base_url=http://127.0.0.1:9000` (in `fire_uav/config/settings_default.json` or via `FIRE_UAV_SETTINGS`) and run the module: `FIRE_UAV_ROLE=module poetry run python -m fire_uav.main`.
3. POST a `RouteMessage` to the stub (or call `UnrealSimUavAdapter.push_route(...)` from your flow) to make the simulated UAV “fly” and emit telemetry along the path.
4. Poll telemetry from `visualizer_api` or subscribe to `/ws/v1/stream` to render in Unreal.
