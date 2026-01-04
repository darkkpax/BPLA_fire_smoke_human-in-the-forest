from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class ToastDeduplicator:
    _last: dict[str, float] = field(default_factory=dict)

    def should_show(self, key: str, cooldown_s: float) -> bool:
        now = time.monotonic()
        last = self._last.get(key)
        if last is not None and (now - last) < cooldown_s:
            return False
        self._last[key] = now
        return True


__all__ = ["ToastDeduplicator"]
