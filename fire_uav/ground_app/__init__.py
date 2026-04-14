from __future__ import annotations

from fire_uav.ground_app.config import load_ground_settings


def main() -> None:
    from fire_uav.ground_app.main_ground import main as _main

    _main()


__all__ = ["main", "load_ground_settings"]
