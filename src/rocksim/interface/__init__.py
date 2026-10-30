"""External-facing interface for the harvester.

Nothing inside this package may import `rocksim.material.*` or
`rocksim.physics.*`. That constraint is structural: it is what makes
the black-box boundary enforceable.
"""

from rocksim.interface.electrodes import (
    MaterialInterface,
    Measurement,
    BlackBoxMaterial,
)
from rocksim.interface.blackbox import build_blackbox

__all__ = [
    "MaterialInterface",
    "Measurement",
    "BlackBoxMaterial",
    "build_blackbox",
]
