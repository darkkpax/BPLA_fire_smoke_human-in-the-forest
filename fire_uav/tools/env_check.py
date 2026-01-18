from __future__ import annotations

import argparse
import importlib
import sys
from importlib import metadata


BASE_REQUIREMENTS: list[tuple[str, str]] = [
    ("pydantic", "pydantic"),
    ("numpy", "numpy"),
    ("shapely", "shapely"),
    ("ortools", "ortools"),
    ("httpx", "httpx"),
    ("requests", "requests"),
    ("prometheus-client", "prometheus_client"),
]

REQUIREMENTS: dict[str, list[tuple[str, str]]] = {
    "module": [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("orjson", "orjson"),
        ("prometheus-fastapi-instrumentator", "prometheus_fastapi_instrumentator"),
        ("opencv-python-headless", "cv2"),
    ],
    "detect": [
        ("ultralytics", "ultralytics"),
        ("torch", "torch"),
    ],
    "ground": [
        ("PySide6", "PySide6"),
        ("PySide6-Addons", "PySide6"),
        ("PySide6-Essentials", "PySide6"),
        ("folium", "folium"),
        ("branca", "branca"),
        ("opencv-python-headless", "cv2"),
    ],
    "dev": [
        ("pytest", "pytest"),
        ("ruff", "ruff"),
        ("mypy", "mypy"),
    ],
}


def _resolve_profiles(raw: str) -> list[str]:
    profiles = [p.strip().lower() for p in (raw or "").split(",") if p.strip()]
    if not profiles:
        return ["module"]
    unknown = [p for p in profiles if p not in REQUIREMENTS]
    if unknown:
        raise SystemExit(f"Unknown profile(s): {', '.join(unknown)}")
    return profiles


def _check_package(dist_name: str, import_name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(import_name)
    except Exception:
        return False, "missing"
    try:
        return True, metadata.version(dist_name)
    except Exception:
        return True, "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate fire_uav environment dependencies.")
    parser.add_argument(
        "--profile",
        default="module",
        help="Comma-separated profiles: module, detect, ground, dev",
    )
    args = parser.parse_args(argv)

    profiles = _resolve_profiles(args.profile)
    required: list[tuple[str, str]] = list(BASE_REQUIREMENTS)
    for profile in profiles:
        required.extend(REQUIREMENTS[profile])

    seen: set[str] = set()
    missing: list[str] = []
    print(f"Profiles: {', '.join(profiles)}")
    print(f"Python: {sys.version.split()[0]}")

    for dist_name, import_name in required:
        if dist_name in seen:
            continue
        seen.add(dist_name)
        ok, info = _check_package(dist_name, import_name)
        if ok:
            print(f"OK   {dist_name} ({info})")
        else:
            missing.append(dist_name)
            print(f"MISS {dist_name}")

    if missing:
        print("Missing packages:", ", ".join(missing))
        return 1
    print("Environment OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
