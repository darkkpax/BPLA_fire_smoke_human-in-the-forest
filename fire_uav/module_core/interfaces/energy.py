from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from fire_uav.module_core.schema import Route, TelemetrySample, WorldCoord


@dataclass(slots=True)
class EnergyEstimate:
    can_complete: bool
    required_percent: float
    margin_percent: float


class EnergyInsufficientError(RuntimeError):
    """Raised when a route cannot be completed with available battery."""


class IEnergyModel(ABC):
    """Abstract interface for estimating energy usage and remaining energy."""

    @abstractmethod
    def energy_cost(self, route: Route) -> float:
        """Estimate energy needed for this route."""

    @abstractmethod
    def remaining_energy(self, telemetry: TelemetrySample) -> float:
        """Estimate remaining energy in the same units as energy_cost."""

    @abstractmethod
    def estimate_route_feasibility(
        self,
        telemetry: TelemetrySample,
        route: Route,
        base_location: WorldCoord,
    ) -> EnergyEstimate:
        """
        Estimate whether the UAV can complete the given route and still
        return safely to base (base_location) from the route end.
        """


__all__ = ["EnergyEstimate", "EnergyInsufficientError", "IEnergyModel"]
