"""Shared physics-layer errors.

Lives in its own module to break the circular import between
`rocksim.physics.solver` and `rocksim.physics.nonlinear`.
"""


class SolverDidNotConverge(RuntimeError):
    """Raised by the nonlinear solver when iteration does not converge."""


__all__ = ["SolverDidNotConverge"]
