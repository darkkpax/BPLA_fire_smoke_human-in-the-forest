.PHONY: install dev test lint run-ground run-module-unreal run-bridge fmt check-env check-env-detect

PY := poetry run

install:
	poetry install

dev:
	poetry install --with dev

test:
	$(PY) pytest

check-env:
	$(PY) python -m fire_uav.tools.env_check --profile module

check-env-detect:
	$(PY) python -m fire_uav.tools.env_check --profile module,detect

lint:
	$(PY) black --check .
	$(PY) ruff check .

fmt:
	$(PY) black .
	$(PY) ruff check . --fix

run-ground:
	FIRE_UAV_ROLE=ground $(PY) python -m fire_uav.main

run-module-unreal:
	FIRE_UAV_ROLE=module $(PY) python -m fire_uav.main

run-bridge:
	UNREAL_BRIDGE_PORT?=9000
	$(PY) python scripts/unreal_bridge_stub.py
