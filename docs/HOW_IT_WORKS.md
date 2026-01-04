# Как устроен проект

Документ коротко описывает реальные потоки данных в `fire_uav`, чтобы было понятно, что запускается в каждом режиме и где искать код.

## Режимы запуска и роли
- Единственная точка входа — `poetry run python -m fire_uav.main`.
- Роль определяется `FIRE_UAV_ROLE` или полем `role` в `fire_uav/config/settings_default.json`.
  - `ground` (по умолчанию) — десктопный GUI на PySide6/Qt Quick.
  - `module` — бортовой headless-режим с телеметрией, планировщиком маршрутов и watchdog.

## Ground (GUI)
- Вход: `fire_uav/ground_app/main_ground.py`.
- Qt WebEngine/QML UI (`fire_uav/gui/qml/main.qml`), управляется через ViewModel из `fire_uav/gui`.
- Инициализация `init_core()` из `fire_uav/bootstrap.py`:
  - Создаёт очереди кадров/детекций и `LifecycleManager`.
  - Подписывает шину событий (`fire_uav/services/bus.py`) на `APP_START/APP_STOP`.
  - Если камера доступна — поднимает `CameraThread` и `DetectThread` (YOLO) из `fire_uav/services/components`.
- REST (`fire_uav/api/main_rest.py`) использует те же очереди и шину:
  - `POST /api/camera/start|stop` — старт/стоп потоков.
  - `POST /api/detections` — принимает сырые детекции+телеметрию, прогоняет через пайплайн (агрегация голосованием K из N, геопроекция) и возвращает подтверждённые цели.
  - `GET /metrics` — Prometheus.

## Module (борт)
- Вход: `fire_uav/module_app/main_module.py` (выбирается автоматом при `role=module`).
- Шаги запуска:
  1) Чтение настроек и логов (`fire_uav/config/settings.py`, `logging_config`).
  2) Инициализация базовых очередей (`init_core()`), создание моделей: `PythonEnergyModel`, `PythonRoutePlanner`, `GeoProjector` (Python или native C++).
  3) Сборка `DetectionPipeline` (агрегатор подтверждает цели, transmitter отправляет на наземную станцию, опционально визуализатор).
  4) Выбор адаптера UAV (`fire_uav/module_core/adapters/*`):
     - `stub` (по умолчанию) — генерирует фиктивную телеметрию.
     - `mavlink` — заглушка под pymavlink/DroneKit.
     - `unreal` — HTTP-мост к симулятору.
     - `custom` — внешний SDK через HTTP/gRPC (инъекция телеметрии извне).
  5) Health-сервер на Uvicorn (`/health`) + watchdog, который ругается, если нет телеметрии/детекций дольше порогов.
- События `APP_START/APP_STOP` пробрасываются в шину, чтобы корректно останавливать компоненты.

## Интеграции
- **Integration service** (`integration_service/app.py`): лёгкий FastAPI-брокер, чтобы внешние клиенты слали телеметрию/маршрут/команды. Он заполняет `CustomSdkUavAdapter`.
- **Ground station**: если включено `ground_station_enabled`, `Transmitter` отправляет подтверждённые детекции по UDP/TCP.
- **Visualizer**: `VisualizerAdapter` умеет публиковать телеметрию/объекты во внешний визуализатор (выключен по умолчанию).
- **API защита и метрики**: если выставить `FIRE_UAV_API_TOKEN`, все FastAPI-приложения (REST, visualizer, integration_service) потребуют `X-API-Key`/`Authorization`. HTTP метрики FastAPI доступны на `/metrics/http` (REST) и `/metrics` (прочие).

## Конфигурация
- Базовые параметры: `fire_uav/config/settings_default.json`.
- Переопределения через `FIRE_UAV_SETTINGS` (путь к JSON) и `FIRE_UAV_PROFILE` (`dev/demo/jetson`).
- Ключевые поля: `role`, `uav_backend`, `mavlink_connection_string`, `unreal_base_url`, `use_native_core`, `visualizer_enabled`, таймауты watchdog.

## Native ускорения
- Директория `cpp/native_core`: pybind11-модуль для быстрой геопроекции, трекера bbox и энергомодели.
- Если собрать `.so` и выставить `use_native_core=true`, фабрики (`fire_uav/module_core/factories.py`) автоматически возьмут native-реализацию.

## Где искать логику
- Шина событий: `fire_uav/services/bus.py`.
- Метрики: `fire_uav/services/metrics.py`.
- Пайплайн детекций и агрегации: `fire_uav/module_core/detections/*`.
- Планировщик маршрутов: `fire_uav/module_core/route/*`.
- Адаптеры UAV: `fire_uav/module_core/adapters/*`.
- Запуск GUI: `fire_uav/ground_app/main_ground.py`; борт: `fire_uav/module_app/main_module.py`.
