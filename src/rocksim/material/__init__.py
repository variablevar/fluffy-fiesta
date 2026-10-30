"""World A — hidden physical material.

This package is on the OPPOSITE side of the boundary from the harvester.
It must never be imported from `rocksim.harvest` or
`rocksim.experiments` directly; the harvester interacts only via the
`MaterialInterface` returned by `rocksim.interface.build_blackbox`.
"""

from rocksim.material.elements import (
    EdgeElement,
    LinearEdge,
    NonlinearEdge,
)
from rocksim.material.geometry import generate_coordinates
from rocksim.material.graph import Material, build_material
from rocksim.material.defects import damage_material

__all__ = [
    "EdgeElement",
    "LinearEdge",
    "NonlinearEdge",
    "generate_coordinates",
    "Material",
    "build_material",
    "damage_material",
]
