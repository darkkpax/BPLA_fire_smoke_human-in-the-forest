# Operator workflow

## Mission states
- PREFLIGHT: plan routes, import/export, confirm plan; link/camera can be offline.
- READY: plan confirmed and prerequisites satisfied; start flight available.
- IN_FLIGHT: flight controls active (edit route, orbit object, return home).
- RTL: return-to-home flow with minimal controls.
- POSTFLIGHT: summary shown, return to planning.
  - Use "Land complete" in RTL to finish a flight and generate the summary.

## Readiness checks
- UAV link status is based on telemetry freshness:
  - CONNECTED: telemetry age <= 2s
  - DEGRADED: 2s < age <= 5s
  - DISCONNECTED: > 5s or never seen
- Camera status is based on frame activity (stale after 2s).
- Start Flight is blocked unless link is CONNECTED, camera is READY, and a plan is confirmed.

## Debug simulation
Open the Debug Console from the main UI:
- Sim telemetry: generates 10Hz telemetry along the confirmed route (or a small circle).
- Sim camera: generates frames to drive the camera readiness state.
- Spawn object: injects a confirmed object through the normal notification path.

## Flight logs
Each flight session is recorded to:
- `data/flights/<YYYY-MM-DD_HH-MM-SS>/`
  - `plan.json` (confirmed plan)
  - `telemetry.jsonl`
  - `objects.jsonl`
  - `events.jsonl`
  - `summary.json`
