# How to add a new drone

This guide explains how to plug a new UAV into Skysight using the contract v1 models and driver registry.

## Steps
1) Implement the driver interface
   - Copy `fire_uav/module_core/drivers/templates/new_driver_template.py`.
   - Map the drone's telemetry into `TelemetryV1` and call the ingest callback.
   - Map routes and commands into the drone's protocol.

2) Map telemetry/route to the contract models
   - Use `fire_uav/module_core/contract/mappers.py` to convert between `TelemetryV1`/`RouteV1` and internal models.
   - Populate optional fields like `battery_percent` and `gps_fix` when available.

3) Register the driver
   - Add the driver to `fire_uav/module_core/drivers/registry.py`.
   - Pick a `driver_type` name (example: `"client_bridge"`).

4) Configure settings
   - Update `fire_uav/config/settings_default.json` with `driver_type`.
   - Or override with your runtime settings file.

5) Verify monitors and mission pipeline
   - Ensure link and camera readiness events update correctly.
   - Confirm mission state transitions (preflight -> in_flight -> rtl -> postflight).
   - Validate that the route polling endpoint returns the expected mission route.
