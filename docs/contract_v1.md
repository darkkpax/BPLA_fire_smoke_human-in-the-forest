# Skysight UAV Contract v1

This contract defines the canonical control-plane and telemetry schema used inside Skysight. It lets any drone or simulator map their native protocol to a stable, versioned contract and keeps the rest of the system drone-agnostic.

## Versioning rules
- `protocol_version` is pinned to `1` for all v1 payloads.
- Additive fields are allowed in a minor update, but existing fields must not change meaning.
- Breaking changes require a new contract version (v2) and a new endpoint namespace.

## Minimal telemetry requirements
Telemetry is accepted when these fields are present:
- `uav_id`
- `timestamp` (UTC, ISO 8601)
- `lat`, `lon`, `alt`

Optional fields include:
- `battery_percent`
- `yaw`, `pitch`, `roll`
- `ground_speed_mps`, `vertical_speed_mps`
- `gps_fix`, `satellites`

## Capabilities handshake
Use the handshake to advertise what the UAV can do. The UI and control logic use these flags to enable or disable actions without changing the GUI layout.

Example capabilities flags:
- `supports_waypoints` (mission/route upload)
- `supports_rtl` (return-to-launch command)
- `supports_orbit` (orbit maneuver)
- `supports_camera` (camera readiness)

## Examples

### Telemetry
```json
{
  "protocol_version": 1,
  "uav_id": "uav-1",
  "timestamp": "2025-01-02T12:00:00Z",
  "lat": 56.02,
  "lon": 92.90,
  "alt": 120.5,
  "yaw": 180.0,
  "battery_percent": 72.5
}
```

### Route
```json
{
  "protocol_version": 1,
  "uav_id": "uav-1",
  "route_id": "route-abc123",
  "mode": "MISSION",
  "created_at": "2025-01-02T12:01:00Z",
  "waypoints": [
    {"lat": 56.02, "lon": 92.90, "alt": 120.0},
    {"lat": 56.03, "lon": 92.91, "alt": 120.0}
  ]
}
```

### Command
```json
{
  "protocol_version": 1,
  "uav_id": "uav-1",
  "timestamp": "2025-01-02T12:02:00Z",
  "command_id": "cmd-001",
  "type": "RTL",
  "params": {}
}
```

### Handshake request
```json
{
  "uav_id": "uav-1",
  "client_type": "drone_bridge",
  "client_version": "1.2.0",
  "capabilities": {
    "supports_waypoints": true,
    "supports_rtl": true,
    "supports_orbit": false,
    "supports_set_speed": false,
    "supports_camera": true,
    "max_waypoints": 60,
    "notes": "custom sdk"
  }
}
```

### Handshake response
```json
{
  "ok": true,
  "protocol_version": 1,
  "server_time": "2025-01-02T12:02:30Z",
  "required_fields": {
    "telemetry": ["uav_id", "timestamp", "lat", "lon", "alt"],
    "camera_status": ["uav_id", "timestamp", "available", "streaming"]
  },
  "assigned_uav_id": "uav-1",
  "notes": "contract_v1"
}
```
