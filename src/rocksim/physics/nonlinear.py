"""Nonlinear solver via Picard / fixed-point iteration.

The element model in 0.1.0 is `NonlinearEdge` with
`G(V) = G0 * (1 + alpha * V^2)`. Because this is monotonically
non-decreasing in |V|, it is monotone -- which guarantees convergence
for the quasi-static nodal equations under mild conditions. The solver
nevertheless fails loudly when iteration does not converge.

Crucially, only the contact conductances of *driven* electrodes enter
the admittance matrix. This is the same convention used by the linear
solver, and it preserves the black-box boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

from rocksim.physics.errors import SolverDidNotConverge

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from rocksim.material.graph import Material


def _assemble_A(
    material: "Material",
    v_h: np.ndarray,
    driven_electrode_ids: Iterable[int] = (),
) -> lil_matrix:
    """Assemble the admittance matrix using conductances evaluated at v_h.

    Contact conductances are added only for the driven electrodes.
    """
    n = material.n_hidden_nodes()
    A = lil_matrix((n, n), dtype=float)
    for u, v, element in material.edges:
        g = float(element.conductance(v_h[v] - v_h[u]))
        A[u, v] -= g
        A[v, u] -= g
    for u, v, element in material.edges:
        g = float(element.conductance(v_h[v] - v_h[u]))
        A[u, u] += g
        A[v, v] += g
    driven_set = {int(x) for x in driven_electrode_ids}
    for e in material.electrodes:
        if e.electrode_id not in driven_set:
            continue
        for node, gc in zip(e.attached_nodes, e.contact_conductances()):
            A[node, node] += gc
    return A


def iterate_nonlinear_system(
    material: "Material",
    b: np.ndarray,
    tol: float,
    max_iter: int,
    driven_electrode_ids: Iterable[int] = (),
) -> np.ndarray:
    """Solve the nonlinear nodal system via Picard iteration."""
    n = material.n_hidden_nodes()
    if n == 0:
        return np.zeros(0, dtype=float)

    # Initial guess from the linear system at zero V (a reasonable start).
    from rocksim.physics.linear import build_linear_system_for_drives

    A0 = build_linear_system_for_drives(material, driven_electrode_ids)
    if A0.shape == (0, 0):
        v_h = np.zeros(0, dtype=float)
    else:
        v_h = spsolve(A0.tocsr(), b)

    if not np.all(np.isfinite(v_h)):
        raise SolverDidNotConverge(
            "nonlinear solver: non-finite initial guess"
        )

    last_change = np.inf
    for it in range(1, max_iter + 1):
        A = _assemble_A(material, v_h, driven_electrode_ids)
        v_new = spsolve(A.tocsr(), b)
        change = float(np.max(np.abs(v_new - v_h)))
        v_h = v_new
        if not np.all(np.isfinite(v_h)):
            raise SolverDidNotConverge(
                f"nonlinear solver: non-finite voltages after iter {it}"
            )
        if change <= tol:
            return v_h
        last_change = change

    raise SolverDidNotConverge(
        f"nonlinear solver did not converge in {max_iter} iterations "
        f"(last |dv|_inf = {last_change:.3e}, tol = {tol:.3e})"
    )


__all__ = ["iterate_nonlinear_system", "_assemble_A"]
