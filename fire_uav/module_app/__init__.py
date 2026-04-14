from __future__ import annotations

from fire_uav.module_app.config import load_module_settings


def main() -> None:
    from fire_uav.module_app.main_module import main as _main

    _main()


__all__ = ["main", "load_module_settings"]
