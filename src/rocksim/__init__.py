"""RockSim — black-box simulator for computation-discovery in an untouched 3-D material.

Importing subpackages here is kept minimal to preserve the architectural
boundary between the harvester and the material/physics internals.

Public, low-level import order:

    rocksim.config           -- version, signal levels, geometry defaults
    rocksim.interface        -- MaterialInterface Protocol + Measurement
    rocksim.harvest          -- candidate, fitness, search strategies
    rocksim.experiments      -- high-level experiment drivers
    rocksim.cli              -- command-line entry point
"""

from rocksim import config

__all__ = ["config"]
__version__ = "0.2.0"
