## API визуализатора БПЛА (для Unreal / инструментов)

API визуализатора отдает легковесное состояние БПЛА (телеметрия, маршрут, подтвержденные объекты) для внешних движков вроде Unreal. Запускайте его на наземной машине (например, `uvicorn fire_uav.api.visualizer_api:app --host 0.0.0.0 --port 8000`).

Базовый URL: `http://127.0.0.1:8000`

### Эндпоинты

- `GET /api/v1/telemetry/{uav_id}` - последняя телеметрия
  Пример ответа:
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

- `GET /api/v1/route/{uav_id}` - текущий маршрут
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

- `GET /api/v1/objects/{uav_id}` - список подтвержденных объектов
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

### Снимок карты

Используйте эти эндпоинты, чтобы зарегистрировать статическое изображение карты (PNG/JPG) с известными географическими границами.

- `POST /api/v1/map_snapshot` - зарегистрировать/обновить метаданные снимка карты
  Тело:
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
  Поведение:
  - Регистрирует или обновляет снимок для данного БПЛА.
  - `image_path` должен указывать на PNG/JPEG файл, доступный для `visualizer_api`.

- `GET /api/v1/map_snapshot/{uav_id}` - получить текущий снимок
  Пример ответа:
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

Рекомендуемый сценарий в Unreal:
1. Сделайте ортографический скриншот сверху и сохраните его на диск.
2. Вызовите `POST /api/v1/map_snapshot`, передав путь к изображению и известные границы.
3. Установите `map_provider="static_image"` в настройках GUI, чтобы отрисовать снимок.

### Поля сообщений
- **TelemetryMessage:** `type`, `uav_id`, `timestamp`, `lat`, `lon`, `alt`, `yaw`, `battery`.
- **RouteMessage:** `type`, `uav_id`, `version`, `waypoints[] {lat, lon, alt}`, `active_index`.
- **ObjectMessage:** `type`, `uav_id`, `object_id`, `class_id`, `confidence`, `lat`, `lon`, `alt`, `status`.

### Использование с Unreal Engine Blueprints
1. Добавьте HTTP-плагин (например, VaRest). Опрос эндпоинтов каждые 0.1-0.2 с.
2. Парсите JSON в структуры Blueprint (TelemetryMessage, RouteMessage, ObjectMessage).
3. Перемещайте актор БПЛА вдоль `route.waypoints`, подсвечивая `active_index`.
4. Создавайте маркеры/декали для элементов из `/objects/{uav_id}`.

Плоская модель Земли: преобразование lat/lon в Unreal (выберите опорные `lat0`, `lon0` при загрузке уровня):
- `dLat = lat - lat0`
- `dLon = lon - lon0`
- `y_m = dLat * 111000`
- `x_m = dLon * 111000 * cos(lat0 radians)`
- Перевод в Unreal (1 UU = 1 см): `X = x_m * 100`, `Y = y_m * 100`, `Z = alt * 100`.

Этот API только для визуализации (read-only); логика миссий остается в Python (приложения module/ground).

## API управления симуляцией в Unreal

UnrealSimUavAdapter (Python) общается с отдельным мостом на стороне Unreal по HTTP, чтобы управлять симулированным БПЛА. Мост можно реализовать на Blueprints, C++ или в виде небольшого Python-сервиса.

Базовый URL: `http://127.0.0.1:9000` (соответствует `settings.unreal_base_url`).

- `GET /sim/v1/telemetry` - возвращает JSON `TelemetryMessage`:
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
- `POST /sim/v1/route` - принимает JSON `RouteMessage` с `waypoints[]` и `active_index`, чтобы двигать симулированный БПЛА вдоль маршрута.
- `POST /sim/v1/command` - принимает:
  ```json
  { "uav_id": "sim", "command": "RESET", "payload": {} }
  ```

Этот API управления независим от read-only `visualizer_api`: он двигает симуляцию (опрос телеметрии + пуш маршрутов/команд), а `visualizer_api` остается для визуализации реальных полетов.

### Локальный тестовый мост (Python)

В репозитории есть минимальный stub-мост, который реализует тот же контракт `/sim/v1/*` и симулирует движение БПЛА по загруженным точкам. Он полезен, когда Unreal еще недоступен, или как референс для Blueprint/C++ кода.

```bash
UNREAL_BRIDGE_PORT=9000 python scripts/unreal_bridge_stub.py
# or: uvicorn scripts.unreal_bridge_stub:app --host 0.0.0.0 --port 9000
```

Шаги, чтобы проверить сквозной сценарий с рантаймом модуля:
1. Запустите stub (см. выше).
2. Установите `uav_backend=unreal` и `unreal_base_url=http://127.0.0.1:9000` (в `fire_uav/config/settings_default.json` или через `FIRE_UAV_SETTINGS`) и запустите модуль: `FIRE_UAV_ROLE=module poetry run python -m fire_uav.main`.
3. Отправьте `RouteMessage` в stub через POST (или вызовите `UnrealSimUavAdapter.push_route(...)` из вашего сценария), чтобы симулированный БПЛА полетел и начал отдавать телеметрию по маршруту.
4. Опросите телеметрию из `visualizer_api` или подпишитесь на `/ws/v1/stream`, чтобы отрисовать в Unreal.
