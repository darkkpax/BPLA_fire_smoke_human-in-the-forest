## Integration Service (мост для внешних клиентов)

Минимальный FastAPI-сервис, который даёт HTTP-точку входа для стороннего софта (свой автопилот/SDK) и прокидывает данные в общий протокол `fire_uav`.

### Эндпойнты `/ext/v1/*`
- `POST /telemetry` — `TelemetryMessage` JSON. Сохраняет последнее состояние и пересылает в `CustomSdkUavAdapter` как `TelemetrySample`.
- `POST /route` — `RouteMessage` JSON. Сохраняет маршрут и отдаёт его адаптеру.
- `POST /command` — `{ "uav_id": "...", "command": "ARM", "payload": {...} }`. Прокидывает простые команды.
- `GET /telemetry/{uav_id}` — вернуть последнюю телеметрию.
- `GET /route/{uav_id}` — вернуть последний маршрут.

Все модели берутся из `fire_uav.core.protocol` (`TelemetryMessage`, `RouteMessage`, `ObjectMessage`), чтобы не плодить собственные схемы.

### Запуск
```bash
export INTEGRATION_HOST=0.0.0.0
export INTEGRATION_PORT=8081
# опционально: добавить токен, чтобы требовать X-API-Key / Authorization
# export FIRE_UAV_API_TOKEN=change-me
python -m integration_service.app
```

### Поток интеграции
1) Клиент шлёт телеметрию и при необходимости маршрут/команды.
2) Сервис кладёт данные в `CustomSdkUavAdapter`.
3) Дальнейшая логика (планировщик, визуализатор, наземка) работает с этими данными так, как будто они пришли от настоящего UAV.

Адаптер сейчас хранит данные в памяти, но его можно расширить для реального железа, не меняя HTTP-контракт.
