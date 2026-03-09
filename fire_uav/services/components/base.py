"""
Базовый класс для всех управляемых компонентов (потоков).

▪ Реализует единый жизненный цикл: IDLE → RUNNING → STOPPING → STOPPED / ERROR
▪ Поддерживает graceful‐shutdown через `stop_event`.
▪ Ловит необработанные исключения и переводит компонент в состояние ERROR.
"""

from __future__ import annotations

import logging
import threading
import traceback
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Final


class State(Enum):
    """Текущее состояние ManagedComponent."""

    IDLE = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()

    def __str__(self) -> str:  # красивый вывод в логи
        return self.name


class ManagedComponent(threading.Thread, ABC):
    """
    Поток с единым интерфейсом `start/stop/join`.

    Наследнику нужно переопределить **только** метод `loop()`.
    """

    #: сколько секунд ждать join'а по умолчанию
    JOIN_TIMEOUT_DEFAULT: Final[float | None] = 5.0

    def __init__(self, *, name: str) -> None:
        super().__init__(name=name, daemon=True)
        self.state: State = State.IDLE
        self._stop_event = threading.Event()
        self._log = logging.getLogger(name)

    # ───────────── API для наследников ───────────── #
    @abstractmethod
    def loop(self) -> None: ...

    # ───────────── threading.Thread overrides ────── #
    def run(self) -> None:  # noqa: D401 — Thread API
        self._log.debug("enter run()")
        self.state = State.RUNNING
        try:
            self.loop()
        except Exception as exc:  # noqa: BLE001
            self.state = State.ERROR
            self._log.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
        finally:
            if self.state not in (State.ERROR, State.STOPPED):
                self.state = State.STOPPED
            self._log.debug("leave run() -> %s", self.state)

    # ───────────── публичный API ─────────────────── #
    def stop(self) -> None:
        """Запрашивает остановку (idempotent)."""
        if not self._stop_event.is_set():
            self._log.debug("Stop requested")
            self.state = State.STOPPING
            self._stop_event.set()

    def join(self, timeout: float | None = JOIN_TIMEOUT_DEFAULT) -> None:
        if self.ident is None:
            self._log.debug("Join skipped for non-started thread")
            return
        super().join(timeout)
        self._log.debug("Joined (%s)", "timed-out" if self.is_alive() else "clean")
