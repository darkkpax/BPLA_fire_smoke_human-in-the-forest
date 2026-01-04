# Развёртывание на Jetson и Rockchip

Краткий план, как собрать единый образ и запускать его как сервис на ARM‑платформах (Jetson, Rockchip RK3588) и на x86_64.

## Multi-arch Docker
- Dockerfile теперь принимает аргументы:
  - `BASE_IMAGE` (по умолчанию `python:3.11-slim`) — можно подменить на L4T/L4T-PyTorch для Jetson.
  - `INSTALL_TORCH` — ставить ли `torch/torchvision` из `requirements.txt` (`0` — пропустить, если они уже есть в базовом образе).
- Пример универсальной сборки (x86_64 + arm64, подходит для Rockchip/CPU):
  ```bash
  docker buildx create --use --name fire-uav-builder
  docker buildx build --platform linux/amd64,linux/arm64 \
    -t fire-uav:multiarch \
    -f Dockerfile \
    .
  ```
- Jetson с GPU: используйте L4T-PyTorch, чтобы не собирать PyTorch самостоятельно, и пропустите установку torch из `requirements.txt`:
  ```bash
  docker buildx build --platform linux/arm64 \
    --build-arg BASE_IMAGE=nvcr.io/nvidia/l4t-pytorch:r35.4.1-pth2.3-py3 \
    --build-arg INSTALL_TORCH=0 \
    -t fire-uav:jetson \
    .
  # для JetPack 6.* выберите соответствующий тег r36.x.*
  ```
- Rockchip RK3588/ARM64 без GPU: достаточно базового образа, сборка arm64:
  ```bash
  docker buildx build --platform linux/arm64 \
    -t fire-uav:arm64 \
    .
  ```
- При желании пушьте в регистри и забирайте на устройство: `docker buildx build ... --push -t <registry>/fire-uav:arm64`.

## Запуск контейнера
- Jetson (GPU), модульный режим, профиль `jetson`:
  ```bash
  docker run --rm --name fire-uav \
    --network host --ipc host \
    --runtime nvidia --gpus all \
    -e FIRE_UAV_ROLE=module \
    -e FIRE_UAV_PROFILE=jetson \
    fire-uav:jetson
  ```
- Rockchip / CPU arm64:
  ```bash
  docker run --rm --name fire-uav \
    --network host --ipc host \
    -e FIRE_UAV_ROLE=module \
    -e FIRE_UAV_PROFILE=dev \
    fire-uav:arm64
  ```
- Для постоянных данных смонтируйте каталоги: `-v /var/lib/fire-uav/config:/app/fire_uav/config/user:ro -v /var/lib/fire-uav/data:/app/data`.

## Systemd-сервис (универсально)
- В `scripts/fire_uav.service.example` лежит unit, который разворачивает контейнер с автоперезапуском.
- Установить:
  ```bash
  sudo cp scripts/fire_uav.service.example /etc/systemd/system/fire_uav.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now fire_uav.service
  ```
- В файле можно переключать профиль (`FIRE_UAV_PROFILE=jetson` или `dev`/`demo`), настроить API token и, для Jetson, раскомментировать строки `--runtime nvidia --gpus all`.

## Производительность
- Для Jetson включайте профиль `jetson` и флаг `use_native_core=true` (в конфиге или окружении) — модуль автоматически возьмёт C++ ускорения, если собран `cpp/native_core`.
- На Rockchip упор идёт в CPU, поэтому используйте arm64 сборку с `INSTALL_TORCH=1`; при наличии NPU можно вынести инференс в внешний сервис и кормить `/api/detections`.
