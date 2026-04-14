"""Entry point for the alternate single-window tactical GUI."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")

import PySide6.QtWebEngineQuick  # noqa: F401
from PySide6.QtGui import QGuiApplication

try:
    from PySide6.QtWebEngine import QtWebEngine
except ImportError:
    try:
        from PySide6.QtWebEngineQuick import QtWebEngineQuick as QtWebEngine
    except ImportError as exc:
        raise RuntimeError(
            "PySide6 WebEngine is missing. Reinstall with Qt WebEngine support (poetry install or pip install PySide6-Addons)."
        ) from exc

import fire_uav.infrastructure.providers as deps
from fire_uav.bootstrap import init_ground_core
from fire_uav.config.logging_config import setup_logging
from fire_uav.ground_app.config import load_ground_settings
from fire_uav.gui.windows.main_window import MainWindow


def main() -> None:
    cfg = load_ground_settings()
    setup_logging(cfg)
    init_ground_core()

    QtWebEngine.initialize()
    app = QGuiApplication(sys.argv)

    app.aboutToQuit.connect(lambda: deps.get_lifecycle().stop_all())  # type: ignore[arg-type]
    win = MainWindow(qml_file="additional.qml")
    app.aboutToQuit.connect(lambda: win.stop_services())  # type: ignore[arg-type]

    for comp in (getattr(win, "cam_thr", None), getattr(win, "det_thr", None)):
        if comp is not None:
            deps.get_lifecycle().register(comp)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    main()
