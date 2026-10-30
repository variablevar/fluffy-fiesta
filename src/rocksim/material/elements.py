"""Element models for edges in the hidden material graph.

Two types ship in 0.1.0:

- `LinearEdge`: conductance is constant in voltage. This is the
  placeholder / control model.
- `NonlinearEdge`: conductance = G0 * (1 + alpha * V^2). Hypothetical
  computational material element. Documented in docs/physics-model.md.

Both expose a `conductance(voltage_difference)` method. The solver uses
the same call pattern for both, ensuring symmetry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class EdgeElement(ABC):
    """An abstract internal element between two hidden nodes."""

    @abstractmethod
    def conductance(self, voltage_difference: float) -> float:
        """Conductance (Siemens) at the given instantaneous voltage drop."""

    def current(
        self,
        voltage_difference: float,
    ) -> float:
        """Quasi-static current through the element."""
        return float(self.conductance(voltage_difference) * voltage_difference)


@dataclass
class LinearEdge(EdgeElement):
    """A purely passive resistive element.

    `g0 = 0` represents an open circuit (used for defects).
    """

    g0: float

    def conductance(self, voltage_difference: float) -> float:  # noqa: ARG002
        if self.g0 < 0:
            raise ValueError("LinearEdge.g0 must be >= 0.")
        return float(self.g0)


@dataclass
class NonlinearEdge(EdgeElement):
    """A hypothetical nonlinear element.

    Conductance: G(V) = G0 * (1 + alpha * V^2).

    This is a toy voltage-dependent conductance. It is documented as a
    computational material model — not a model of ordinary rock.
    """

    g0: float
    alpha: float = 1.0

    def conductance(self, voltage_difference: float) -> float:
        if self.g0 < 0:
            raise ValueError("NonlinearEdge.g0 must be >= 0.")
        if self.alpha < 0:
            raise ValueError("NonlinearEdge.alpha must be >= 0.")
        return float(self.g0 * (1.0 + self.alpha * voltage_difference ** 2))
