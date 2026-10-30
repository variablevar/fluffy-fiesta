"""The black-box electrode API.

`MaterialInterface` is a `typing.Protocol`. The harvester holds a value
typed against this Protocol and therefore cannot reach beyond
`evaluate()` / `electrode_count` / `reset()`.

`Measurement` is the only result type returned across the boundary.

`BlackBoxMaterial` is a concrete wrapper: it owns a `Material` /
`PhysicsSolver` private to World A and exposes only the Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Measurement:
    """The ONLY object that crosses the harvester-physics boundary.

    Only externally measurable quantities are exposed. Anything hidden
    inside the material (nodes, edges, defects, internal coordinates)
    must NEVER appear on this object.
    """

    electrode_voltages: dict[int, float]
    electrode_currents: dict[int, float]


class MaterialInterface(Protocol):
    """The harvester-side view of a physical material.

    Methods:

    - evaluate: drive some electrodes, get the resulting voltages /
      currents back. The harvester supplies driven voltages for any
      subset of electrodes; other electrodes are left floating from
      the harvester's view but the solver internally grounds them
      (zero current) just so the system stays uniquely solvable.
    - reset: undo any internal accumulation of state. (The current
      quasi-static solver has no state, but the API is reserved for
      future hysteretic / capacitive modules.)
    - step: advance internal time by dt. Reserved for future use;
      in 0.1.0 it is a no-op.
    """

    @property
    def electrode_count(self) -> int: ...

    def evaluate(
        self,
        driven_voltages: dict[int, float],
    ) -> Measurement: ...

    def reset(self) -> None: ...

    def step(self, dt: float) -> None: ...


# A friendly alias used in modules that benefit from explicit naming.
BlackBoxMaterial = MaterialInterface
