# AGENTS.md

## Purpose

This repository contains the Skysight / fire_uav system: onboard CV module + ground application + API/visualizer + optional Unreal integration.  
This file defines practical rules for assistants (and contributors) so changes stay consistent, safe, and easy to review.

## Repo orientation

Typical structure (may vary slightly, follow the actual tree):

- `module_app/`  
  Runtime app that connects to a UAV adapter, processes telemetry/video/detections, pushes results to `visualizer_api`, emits events to the GUI.
- `module_core/`  
  Core domain logic: schema, detection pipeline, aggregation, geo binding, energy model, route planner, maneuvers, adapters interfaces.
- `ground_app/`  
  Ground station entrypoint / app wiring (often starts GUI + services).
- `gui/`  
  GUI layer (PySide/PyQt + QML). Do not redesign visuals.
- `api/`  
  `visualizer_api` FastAPI server and WS stream.
- `config/`  
  Settings model + defaults.
- `services/`  
  Event bus and cross-cutting services (notifications, recorder, monitors).

If something is not found at these paths, search by class/function names and follow existing conventions.

## Working rules

### 1) Do not redesign the GUI
- Preserve the current UI style: layout, spacing, typography, colors, control sizes.
- Reuse existing components (toasts, panels, toolbars, button styles).
- Add new controls only when necessary, and place them in existing areas (toolbar/menu/debug section).

### 2) Prefer additive, minimal diffs
- Avoid large refactors unless explicitly requested.
- Do not rename public endpoints, events, or shared models unless strictly necessary.
- Keep backward compatibility for external interfaces (API, JSON payloads, config keys) whenever possible.

### 3) Single source of truth
- Mission state should come from one state machine (not scattered booleans).
- Link and camera readiness should be derived from monitors (not random UI heuristics).
- Battery handling should be unified (real telemetry if available; virtual/sim only when missing).

### 4) Avoid spam and duplication
- Notifications must be deduplicated/rate-limited by key and cooldown.
- Confirmed objects should be emitted/saved once per object id (no “new object every second” flood).

## Code style expectations

- Python: follow existing style in repo (type hints, logging, small modules).
- Avoid heavy new dependencies unless necessary; prefer standard library + already-used libraries.
- Use `logging.getLogger(__name__)` and keep logs actionable.
- Keep JSON payloads stable and versionable.

## Event bus conventions

- Use `services.bus` as the central messaging layer between core/app and GUI.
- Prefer events with structured payloads (dicts with clear keys).
- For operator-facing warnings, use one generic toast event (or the existing pattern) and dedupe it.

## Data and persistence

When implementing storage:
- Put runtime artifacts under `data/` (or the repo’s existing storage dir).
- For flights, prefer a session directory per run:
  - `plan.json`
  - `telemetry.jsonl`
  - `objects.jsonl`
  - `events.jsonl`
  - `summary.json`

Write in append mode, keep it lightweight.

## API rules (visualizer_api)

- Do not change existing endpoints or response shapes without strong reason.
- Additive endpoints are OK (e.g., `map_snapshot`).
- Validate inputs and return useful HTTP errors (400/404) rather than 500.

## Simulation and debugging

Because development often happens without a drone:
- Provide a debug simulation mode that can generate:
  - telemetry (movement along route),
  - link connect/disconnect,
  - camera “frames” availability,
  - confirmed objects spawning.
- Simulation must feed into the same pipeline as real adapters so behavior matches production.

## Where to add new features

- Mission workflow/state machine: `module_core/mission/` or `services/` (pick one and keep it consistent).
- Link and camera monitors: `services/` or `module_core/mission/`.
- Battery unification: `module_core/battery/`.
- GUI gating and state-driven buttons: `gui/` (controller signals + QML bindings).
- Recording: `services/flight_recorder.py`.

Prefer a thin GUI layer: GUI should react to events and state, not implement business logic.

## How to verify changes

Minimum checks after changes:
- App starts in planning mode without UAV/sim connected.
- Route can be drawn/imported/exported without a link.
- Start flight is blocked if link/camera is missing, with a non-spammy toast.
- Debug sim can enable link + camera + objects and drive the UI states.
- Confirmed objects are not duplicated in logs/notifications.
- Flight session recording creates the expected folder and files.

## Notes for assistants

- If uncertain about an interface, search for existing usage patterns and mirror them.
- Keep changes small and testable.
- When adding new config keys, update both the settings model and the default JSON.