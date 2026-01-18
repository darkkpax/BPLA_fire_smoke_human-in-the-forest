# Контракт Skysight UAV v1

Этот контракт определяет каноническую схему плоскости управления и телеметрии, используемую внутри Skysight. Он позволяет любому дрону или симулятору сопоставить свой нативный протокол со стабильным, версионируемым контрактом и делает остальную систему независимой от конкретного дрона.

## Правила версионирования
- `protocol_version` фиксируется на `1` для всех payload v1.
- Добавочные поля допускаются в минорном обновлении, но существующие поля не должны менять смысл.
- Ломающие изменения требуют новой версии контракта (v2) и нового пространства имен эндпоинтов.

## Минимальные требования к телеметрии
Телеметрия принимается при наличии полей:
- `uav_id`
- `timestamp` (UTC, ISO 8601)
- `lat`, `lon`, `alt`

Необязательные поля:
- `battery_percent`
- `yaw`, `pitch`, `roll`
- `ground_speed_mps`, `vertical_speed_mps`
- `gps_fix`, `satellites`

## Handshake возможностей
Используйте handshake, чтобы объявить, что умеет БПЛА. UI и логика управления используют эти флаги, чтобы включать или отключать действия без изменения компоновки GUI.

Примеры флагов возможностей:
- `supports_waypoints` (загрузка миссии/маршрута)
- `supports_rtl` (команда возврата домой)
- `supports_orbit` (маневр орбиты)
- `supports_camera` (готовность камеры)

## Примеры

### Телеметрия
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

### Маршрут
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

### Команда
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

### Запрос handshake
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

### Ответ handshake
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
