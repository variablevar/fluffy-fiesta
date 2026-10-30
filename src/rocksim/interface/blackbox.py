"""The concrete BlackBoxMaterial wrapper.

This module is the only file in `rocksim.interface` that is allowed to
KNOW about material/physics internals. It builds the wrapper around an
internal object and then immediately discards references to internal
fields, exposing only the Protocol surface.

Crucially: the wrapper does NOT re-expose the internal solver object,
graph object, or any attribute prefixed `_internal_*`. The harvester
receives the wrapper and nothing else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rocksim.interface.electrodes import MaterialInterface, Measurement

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from rocksim.material.graph import Material
    from rocksim.physics.solver import PhysicsSolver


class BlackBoxMaterialWrapper:
    """Concrete `MaterialInterface` that hides World A behind World B.

    Construction is the only moment a reference to the internal material
    is captured. After `build_blackbox` returns, the harvester sees only
    this object's `.evaluate`, `.electrode_count`, `.reset`, `.step`
    methods. Calling any other attribute raises `AttributeError`.
    """

    # Attribute names that may legitimately leak beyond the Protocol
    # boundary on this object. Kept deliberately short.
    _ALLOWED_ATTRS = {
        "evaluate",
        "electrode_count",
        "reset",
        "step",
        # Python protocol methods.
        "__class__",
        "__dict__",
        "__dir__",
        "__doc__",
        "__eq__",
        "__format__",
        "__ge__",
        "__getattribute__",
        "__gt__",
        "__hash__",
        "__init__",
        "__init_subclass__",
        "__le__",
        "__lt__",
        "__module__",
        "__ne__",
        "__new__",
        "__reduce__",
        "__reduce_ex__",
        "__repr__",
        "__setattr__",
        "__sizeof__",
        "__str__",
        "__subclasshook__",
        "__weakref__",
    }

    def __init__(
        self,
        material: "Material",
        solver: "PhysicsSolver",
        electrode_count: int,
    ) -> None:
        # The two internal handles are stored under private names.
        # Direct access from outside is blocked by `__getattribute__`.
        object.__setattr__(self, "_material", material)
        object.__setattr__(self, "_solver", solver)
        object.__setattr__(self, "_electrode_count", int(electrode_count))

    # -- Public Protocol surface -------------------------------------

    @property
    def electrode_count(self) -> int:
        # Bypass the boundary guard; this method is part of the wrapper
        # itself and needs to reach the internal handle.
        return object.__getattribute__(self, "_electrode_count")

    def evaluate(
        self,
        driven_voltages: dict[int, float],
    ) -> Measurement:
        voltages, currents = object.__getattribute__(
            self, "_solver"
        ).evaluate_electrodes(
            object.__getattribute__(self, "_material"),
            driven_voltages,
        )
        return Measurement(
            electrode_voltages=dict(voltages),
            electrode_currents=dict(currents),
        )

    def reset(self) -> None:
        # Reserved for future use (hysteretic / capacitive modules).
        return None

    def step(self, dt: float) -> None:
        # Reserved for future use.
        _ = dt  # explicit no-op
        return None

    # -- Boundary enforcement ----------------------------------------

    def __getattribute__(self, name: str):
        if name in BlackBoxMaterialWrapper._ALLOWED_ATTRS:
            return object.__getattribute__(self, name)
        raise AttributeError(
            f"BlackBoxMaterialWrapper hides attribute {name!r}: the "
            f"harvester protocol does not expose internal material state."
        )

    def __setattr__(self, name: str, value) -> None:
        if name in {"_material", "_solver", "_electrode_count"}:
            object.__setattr__(self, name, value)
            return
        raise AttributeError(
            f"BlackBoxMaterialWrapper attribute {name!r} is read-only."
        )


def build_blackbox(
    material: "Material",
    solver: "PhysicsSolver",
) -> MaterialInterface:
    """Construct the public black-box for an internal material + solver.

    Returns a value typed against `MaterialInterface`. Internally the
    object is a `BlackBoxMaterialWrapper`. The internal references are
    held only by the wrapper — they never reach the harvester.
    """
    return BlackBoxMaterialWrapper(
        material=material,
        solver=solver,
        electrode_count=len(material.electrodes),
    )
