"""Helpers for the linear nodal solver."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from scipy.sparse import lil_matrix

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from rocksim.material.graph import Material


def _laplacian_incidence(material: "Material") -> lil_matrix:
    """Internal-edge incidence contribution to the admittance matrix."""
    n = material.n_hidden_nodes()
    A = lil_matrix((n, n), dtype=float)
    for u, v, element in material.edges:
        g = float(element.conductance(0.0))
        A[u, v] -= g
        A[v, u] -= g
    for u, v, element in material.edges:
        g = float(element.conductance(0.0))
        A[u, u] += g
        A[v, v] += g
    return A


def build_linear_system(
    material: "Material",
) -> lil_matrix:
    """Build admittance including ALL contact conductances.

    Provided for the researcher-side inspection helper
    `PhysicsSolver.sparse_laplacian`. For actual solving, use
    `build_linear_system_for_drives` so undriven electrodes do not act
    as sneak paths to ground.
    """
    A = _laplacian_incidence(material)
    n = material.n_hidden_nodes()
    for e in material.electrodes:
        for node, gc in zip(e.attached_nodes, e.contact_conductances()):
            A[node, node] += gc
    return A


def build_linear_system_for_drives(
    material: "Material",
    driven_electrode_ids: Iterable[int] = (),
) -> lil_matrix:
    """Build admittance, adding contact conductances ONLY for the
    driven electrodes. Undriven electrodes contribute nothing.
    """
    A = _laplacian_incidence(material)
    n = material.n_hidden_nodes()
    driven_set = {int(x) for x in driven_electrode_ids}
    for e in material.electrodes:
        if e.electrode_id not in driven_set:
            continue
        for node, gc in zip(e.attached_nodes, e.contact_conductances()):
            A[node, node] += gc
    return A


__all__ = ["build_linear_system", "build_linear_system_for_drives"]
