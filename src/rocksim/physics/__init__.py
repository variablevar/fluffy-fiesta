"""World A -- physics solvers."""

from rocksim.physics.errors import SolverDidNotConverge
from rocksim.physics.solver import (
    PhysicsSolver,
    build_solver,
)

__all__ = ["PhysicsSolver", "SolverDidNotConverge", "build_solver"]
