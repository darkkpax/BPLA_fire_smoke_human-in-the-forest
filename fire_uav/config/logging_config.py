from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fire_uav.config.settings import Settings


def setup_logging(settings: Settings) -> None:
    """
    Configure application logging based on provided settings.

    - Sets root level from settings.log_level.
    - Logs to stderr.
    - Optionally logs to a rotating file when settings.log_to_file is True.
    """
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)

    # Reset handlers to avoid duplicate logs on re-init.
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handlers = []

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    handlers.append(stream_handler)

    if getattr(settings, "log_to_file", False):
        log_file = Path(getattr(settings, "log_file", "data/logs/fire_uav.log"))
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=getattr(settings, "log_max_bytes", 5_000_000),
            backupCount=getattr(settings, "log_backup_count", 3),
        )
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)


__all__ = ["setup_logging"]
