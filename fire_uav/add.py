"""Alternate GUI launcher: `python -m fire_uav.add`."""

from __future__ import annotations


def main() -> None:
    from fire_uav.ground_app.main_additional import main as _main

    _main()


if __name__ == "__main__":  # pragma: no cover
    main()
