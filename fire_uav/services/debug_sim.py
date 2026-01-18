from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fire_uav.ground_app.gui.debug_sim import DebugSimulationService as DebugSimulationService


def __getattr__(name: str):
    if name == "DebugSimulationService":
        from fire_uav.ground_app.gui.debug_sim import DebugSimulationService

        return DebugSimulationService
    raise AttributeError(name)


__all__ = ["DebugSimulationService"]
