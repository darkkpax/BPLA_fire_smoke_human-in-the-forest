# fire_uav

**Fire Smoke Human Detection & UAV Mission Planning**

## Headless install (pip)
```bash
pip install -e ".[module]"
pip install -e ".[module,detect]"
python -m fire_uav.module_app.main_module
```

## Environment check
```bash
python -m fire_uav.tools.env_check --profile module
python -m fire_uav.tools.env_check --profile module,detect
```

## Local checks
```bash
pytest -q
python -m fire_uav.tools.env_check --profile module
python -m fire_uav.tools.env_check --profile module,detect
```

Инструментарий для обнаружения дыма/огня/людей и планирования миссий БПЛА. Используются Ultralytics YOLOv11 (PyTorch), OR-Tools + Shapely для маршрутов, FastAPI для REST, и GUI на PySide6/Qt WebEngine.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_env.ps1
```
```bash
bash scripts/setup_env.sh  # macOS/Linux
```
Скрипт создаст `.venv`, установит зависимости через Poetry и проверит доступность Qt WebEngine. Добавьте флаг `-RuntimeOnly` (Windows) или `--runtime-only` (macOS/Linux), если не нужны dev-зависимости (pytest, pre-commit).

## Запуск GUI
```powershell
poetry run python -m fire_uav.main
```
По умолчанию стартует ground GUI (роль `ground`). Для запуска бортового модуля задайте `FIRE_UAV_ROLE=module` или поменяйте `role` в `fire_uav/config/settings_default.json`.

## Операторский workflow
Короткое описание миссий, проверок готовности, режима симуляции и логов полёта — в `docs/operator_workflow.md`.

## Запуск CLI (обработка видео/картинки)
powershell
poetry run python -m fire_uav.bootstrap detect `
  --input path\to\video.mp4 `
  --model data\models\fire_detector.pt `
  --output data\outputs\results.mp4
```

## Запуск REST API + метрики
```powershell
poetry run uvicorn fire_uav.api.main_rest:app --host 0.0.0.0 --port 8000
```
Эндпоинты: `POST /start`, `POST /stop`, `GET /status`, `GET /plan`, `GET /metrics` (Prometheus).

## UAV backend
- По умолчанию включён `uav_backend=stub`, который шлёт фейковую телеметрию, чтобы модуль работал без MAVLink.
- Для реального подключения задайте `uav_backend=mavlink` и строку `mavlink_connection_string`, либо `uav_backend=unreal` с `unreal_base_url`.
- Меняйте `fire_uav/config/settings_default.json` или пробросьте свой JSON через переменную окружения `FIRE_UAV_SETTINGS`.
- Для быстрой проверки Unreal-моста без самого движка можно поднять локальный HTTP-стаб: `UNREAL_BRIDGE_PORT=9000 python scripts/unreal_bridge_stub.py` (реализует `/sim/v1/telemetry|route|command`, как ожидает адаптер).
- Опциональная защита API: выставьте `FIRE_UAV_API_TOKEN` (в `.env` или окружении) — все FastAPI-эндпоинты потребуют `X-API-Key` или `Authorization: Bearer ...`.
- Метрики HTTP: FastAPI-приложения экспортируют Prometheus метрики на `/metrics` через `prometheus-fastapi-instrumentator`.

## Тесты
```powershell
poetry run pytest --cov=fire_uav --cov-report=term-missing
```

## Полезные команды (Makefile)
- `make install` / `make dev` — установка зависимостей (prod/dev).
- `make test` — pytest.
- `make lint` / `make fmt` — проверка/исправление стиля (black + ruff).
- `make run-ground` — GUI.
- `make run-module-unreal` — бортовой режим с текущей конфигурацией.
- `make run-bridge` — запустить локальный HTTP-стаб Unreal `/sim/v1/*`.

## Native core (C++ ускорения)
- Модуль `cpp/native_core` даёт быстрые гео-утилиты: расстояние, проекция bbox→земля с yaw/pitch/roll и `offset_latlon`.  
- `fire_uav/module_core/detections/pipeline.py` использует `NativeGeoProjector`, когда собран модуль и включён флаг `use_native_core` в `config/settings_default.json` (иначе остаётся Python-реализация); планировщик аналогично переключает `NativeEnergyModel`.
- Трекинг детекций может работать через `native_core.BBoxTracker` (переключение тем же флагом `use_native_core`); в Python остаётся тот же интерфейс `assign_and_smooth`.
- Сборка на Jetson/ARM64:
  ```bash
  cd cpp/native_core
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
  cmake --build build
  # добавить собранный .so в PYTHONPATH или скопировать рядом с fire_uav/module_core/native_core.*.so
  ```
- Зависимости для сборки на Jetson: `sudo apt install cmake libpython3-dev`, `pip install pybind11`; при сборке внутри venv убедитесь, что активированы нужные include-пути Python.
- Включение в рантайме: поставьте `use_native_core` в `config/settings_default.json` в `true` или пробросьте переменную окружения `FIRE_UAV_ROLE`/конфиг с тем же ключом, чтобы пайплайн и планировщик автоматически выбрали native-модули.

## Deployment (ARM)
- Полный гайд см. в `docs/DEPLOYMENT_ARM.md`. Ниже — краткий чеклист.
- Подготовка:
  - Нужен Docker с включённым Buildx. Для Jetson — NVIDIA Container Runtime.
  - Выберите профиль: `jetson` (GPU), `dev/demo` (CPU), либо свой через `fire_uav/config/settings_default.json` или переменную `FIRE_UAV_SETTINGS`.
- Сборка образа:
  - Jetson (использует L4T PyTorch, не ставит torch из `requirements.txt`):
    ```bash
    docker buildx build --platform linux/arm64 \
      --build-arg BASE_IMAGE=nvcr.io/nvidia/l4t-pytorch:r35.4.1-pth2.3-py3 \
      --build-arg INSTALL_TORCH=0 \
      -t fire-uav:jetson .
    ```
  - Rockchip/CPU arm64:
    ```bash
    docker buildx build --platform linux/arm64 -t fire-uav:arm64 .
    ```
- Запуск (модульный режим, host network):
  - Jetson:
    ```bash
    docker run --rm --name fire-uav \
      --network host --ipc host \
      --runtime nvidia --gpus all \
      -e FIRE_UAV_ROLE=module \
      -e FIRE_UAV_PROFILE=jetson \
      fire-uav:jetson
    ```
  - Rockchip/CPU:
    ```bash
    docker run --rm --name fire-uav \
      --network host --ipc host \
      -e FIRE_UAV_ROLE=module \
      -e FIRE_UAV_PROFILE=dev \
      fire-uav:arm64
    ```
  - Для постоянных данных и конфигов добавьте тома: `-v /var/lib/fire-uav/config:/app/fire_uav/config/user:ro -v /var/lib/fire-uav/data:/app/data`.
- Автозапуск через systemd:
  ```bash
  sudo cp scripts/fire_uav.service.example /etc/systemd/system/fire_uav.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now fire_uav.service
  ```
  В unit-файле переключите `FIRE_UAV_PROFILE` под свою платформу и раскомментируйте `--runtime nvidia --gpus all` для Jetson.
