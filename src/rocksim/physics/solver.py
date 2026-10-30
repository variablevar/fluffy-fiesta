"""Physics solver -- internal to World A.

This module owns the quasi-static nodal solver. Its public surface is:

- `PhysicsSolver` (constructor configured with a `Material`)
- `evaluate_electrodes(material, driven_voltages)` returning
  `(voltages, currents)` dicts.

The interface layer (`rocksim.interface.blackbox`) is the only thing that
calls this module. The harvester never sees `PhysicsSolver` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from scipy.sparse import csr_matrix, lil_matrix
from scipy.sparse.linalg import spsolve

from rocksim.config import (
    LINEAR_TOL,
    NONLINEAR_MAX_ITER,
    NONLINEAR_TOL,
)
from rocksim.physics.linear import build_linear_system
from rocksim.physics.nonlinear import iterate_nonlinear_system
from rocksim.physics.errors import SolverDidNotConverge  # re-export

if TYPE_CHECKING:  # pragma: no cover - typing aid only
    from rocksim.material.graph import Material


class PhysicsSolver:
    """Internal physics solver.

    The solver is built around a fixed `Material`. We avoid rebuilding
    the linear system between evaluations when the underlying material
    (and therefore its topology / base conductances) does not change.
    """

    def __init__(
        self,
        material: "Material",
        linear_tol: float = LINEAR_TOL,
        nonlinear_tol: float = NONLINEAR_TOL,
        nonlinear_max_iter: int = NONLINEAR_MAX_ITER,
    ) -> None:
        self._material = material
        self._linear_tol = float(linear_tol)
        self._nonlinear_tol = float(nonlinear_tol)
        self._nonlinear_max_iter = int(nonlinear_max_iter)
        # Pre-build the sparse Laplacian + contact bookkeeping for the
        # *linear* form. Nonlinear iterations reuse the same indices.
        self._A_template = build_linear_system(material)

    @property
    def model_name(self) -> str:
        return self._material.model_name

    def evaluate_electrodes(
        self,
        material: "Material",
        driven_voltages: dict[int, float],
    ) -> tuple[dict[int, float], dict[int, float]]:
        """Solve the quasi-static problem for the supplied electrode drives.

        Undriven electrodes are left floating (i.e. their contact branches
        carry zero current). This is the conventional KCL formulation: we
        do not enforce a "ground" electrode unless the caller explicitly
        drives one. The unique solvability of the system arises from the
        contact-conductance regularisation on driven electrodes.
        """
        if material is not self._material:
            raise ValueError(
                "PhysicsSolver is bound to a different material"
            )

        n = self._material.n_hidden_nodes()
        if n == 0:
            voltages = {e.electrode_id: 0.0 for e in material.electrodes}
            currents = {e.electrode_id: 0.0 for e in material.electrodes}
            return voltages, currents

        # Build b: the injected-current vector.
        b = np.zeros(n, dtype=float)
        electrode_node_groups: list[tuple[int, list[int]]] = []
        for e in material.electrodes:
            if e.electrode_id not in driven_voltages:
                continue
            v_drive = float(driven_voltages[e.electrode_id])
            att = list(e.attached_nodes)
            electrode_node_groups.append((e.electrode_id, att))
            for node, gc in zip(att, e.contact_conductances()):
                b[node] += gc * v_drive

        # Solve. NOTE: only the contact branches of driven electrodes
        # contribute to the admittance matrix. Undriven electrodes are
        # floating (no current source, no extra path) so they do not act
        # as sneak paths to ground. This avoids the well-known bug where
        # an undriven probe through a 1 S contact silently grounds an
        # otherwise perfectly isolated node.
        if material.model_name == "linear":
            A = self._build_A_for_drives(
                [e.electrode_id for e in material.electrodes
                 if e.electrode_id in driven_voltages]
            )
            v_h = spsolve(A.tocsr(), b)
        elif material.model_name == "nonlinear":
            v_h = iterate_nonlinear_system(
                material=material,
                b=b,
                tol=self._nonlinear_tol,
                max_iter=self._nonlinear_max_iter,
                driven_electrode_ids=[
                    e.electrode_id for e in material.electrodes
                    if e.electrode_id in driven_voltages
                ],
            )
        else:
            raise ValueError(
                f"unknown material_model: {material.model_name!r}"
            )
# Voltages and currents at electrodes.
        voltages: dict[int, float] = {}
        currents: dict[int, float] = {}

        for eid, att in electrode_node_groups:
            voltages[eid] = float(driven_voltages[eid])

        for e in material.electrodes:
            if e.electrode_id in voltages:
                v_drive = float(voltages[e.electrode_id])
                i_sum = 0.0
                for node, gc in zip(
                    e.attached_nodes, e.contact_conductances()
                ):
                    i_sum += gc * (v_drive - v_h[node])
                currents[e.electrode_id] = float(i_sum)
            else:
                if e.attached_nodes:
                    voltages[e.electrode_id] = float(
                        np.mean([v_h[i] for i in e.attached_nodes])
                    )
                else:
                    voltages[e.electrode_id] = 0.0
                currents[e.electrode_id] = 0.0

        return voltages, currents

    # -- Internals ----------------------------------------------------

    def _build_static_A(self) -> lil_matrix:
        """Rebuild the static (non-piecewise) admittance matrix including
        ALL contact conductances. Used as a research-only inspection
        helper. For actual solving use `_build_A_for_drives` so the
        undriven electrodes do not ground hidden nodes through sneak
        paths.
        """
        n = self._material.n_hidden_nodes()
        A = lil_matrix((n, n), dtype=float)
        for u, v, element in self._material.edges:
            g = float(element.conductance(0.0))
            A[u, v] -= g
            A[v, u] -= g
        for u, v, element in self._material.edges:
            g = float(element.conductance(0.0))
            A[u, u] += g
            A[v, v] += g
        for e in self._material.electrodes:
            for node, gc in zip(e.attached_nodes, e.contact_conductances()):
                A[node, node] += gc
        return A

    def _build_A_for_drives(
        self, driven_electrode_ids,
    ) -> lil_matrix:
        """Build admittance, including contact conductances ONLY for the
        driven electrodes. Undriven electrodes contribute no source and
        no contact branch, so their attached hidden nodes are truly
        floating.
        """
        n = self._material.n_hidden_nodes()
        A = lil_matrix((n, n), dtype=float)
        for u, v, element in self._material.edges:
            g = float(element.conductance(0.0))
            A[u, v] -= g
            A[v, u] -= g
        for u, v, element in self._material.edges:
            g = float(element.conductance(0.0))
            A[u, u] += g
            A[v, v] += g
        driven_set = {int(x) for x in driven_electrode_ids}
        for e in self._material.electrodes:
            if e.electrode_id not in driven_set:
                continue
            for node, gc in zip(e.attached_nodes, e.contact_conductances()):
                A[node, node] += gc
        return A

    def sparse_laplacian(self) -> csr_matrix:
        """Researcher-only inspection helper for the admittance matrix."""
        return self._A_template.tocsr()


def build_solver(
    material: "Material",
    linear_tol: float = LINEAR_TOL,
    nonlinear_tol: float = NONLINEAR_TOL,
    nonlinear_max_iter: int = NONLINEAR_MAX_ITER,
) -> PhysicsSolver:
    """Factory used by `interface.blackbox` to construct a solver."""
    return PhysicsSolver(
        material=material,
        linear_tol=linear_tol,
        nonlinear_tol=nonlinear_tol,
        nonlinear_max_iter=nonlinear_max_iter,
    )




class SolverDidNotConverge(RuntimeError):
    """Raised by the nonlinear solver when iteration does not converge."""


# ----------------------------------------------------------------------
# Researcher-only internal-state dump.
#
# These helpers compute node voltages, edge currents, and edge power
# dissipation for a given drive pattern. They are NOT exposed through
# `MaterialInterface` and therefore cannot be reached by the harvester.
# They are exposed via the researcher-only export pipeline (Blender JSON,
# `researcher_ground_truth.json`).
# ----------------------------------------------------------------------


def solve_with_internal_state(
    material: "Material",
    driven_voltages: dict[int, float],
    solver: "PhysicsSolver | None" = None,
) -> dict:
    """Solve the system and return researcher-only internals.

    Returns a dict with:

        hidden_node_voltages: list[float], length n_hidden_nodes
        edge_currents: list[dict] per internal edge
        edge_powers: list[dict] per internal edge
        edge_drops: list[dict] per internal edge

    This function is the SINGLE source of truth for internal currents
    / voltages / powers used by the Blender exporter and the
    researcher-ground-truth file. It is never wired to the
    `MaterialInterface` and the harvester pipeline never sees it.
    """
    if solver is None:
        solver = build_solver(material)
    voltages, _ = solver.evaluate_electrodes(material, driven_voltages)
    # Hidden node voltages. Solver wrote these into the (u, v, element)
    # loop, but evaluate_electrodes does not return them. We re-solve
    # here through the private path. To keep this efficient and avoid
    # changing the public solver API, we re-use the same
    # `_evaluate_electrodes` private machinery by replicating the b
    # construction and one solve per drive pattern (the same solve the
    # wrapper performed). For researchers using a few drive patterns
    # this is acceptable.
    n = material.n_hidden_nodes()
    b = np.zeros(n, dtype=float)
    for e in material.electrodes:
        if e.electrode_id not in driven_voltages:
            continue
        v_drive = float(driven_voltages[e.electrode_id])
        for node, gc in zip(
            e.attached_nodes, e.contact_conductances(),
        ):
            b[node] += gc * v_drive
    if material.model_name == "linear":
        A = solver._build_A_for_drives(
            [e.electrode_id for e in material.electrodes
             if e.electrode_id in driven_voltages]
        )
        v_h = spsolve(A.tocsr(), b)
    else:
        v_h = iterate_nonlinear_system(
            material=material,
            b=b,
            tol=solver._nonlinear_tol,
            max_iter=solver._nonlinear_max_iter,
            driven_electrode_ids=[
                e.electrode_id for e in material.electrodes
                if e.electrode_id in driven_voltages
            ],
        )

    edge_drops: list[dict] = []
    edge_currents: list[dict] = []
    edge_powers: list[dict] = []
    for idx, (u, v, element) in enumerate(material.edges):
        v_drop = float(v_h[v] - v_h[u])
        # Use the local conductance evaluated at the actual V_drop to
        # be honest for nonlinear materials. This is the same call
        # the solver uses internally.
        g_e = float(element.conductance(v_drop))
        current = float(g_e * v_drop)
        power = float(current * v_drop)
        edge_drops.append({
            "edge_index": int(idx),
            "u": int(u),
            "v": int(v),
            "voltage_drop_V": v_drop,
        })
        edge_currents.append({
            "edge_index": int(idx),
            "u": int(u),
            "v": int(v),
            "current_A": current,
            "direction_u_to_v": current,  # positive = u to v
        })
        edge_powers.append({
            "edge_index": int(idx),
            "u": int(u),
            "v": int(v),
            "power_W": power,
        })

    return {
        "hidden_node_voltages": [float(x) for x in v_h],
        "edge_drops": edge_drops,
        "edge_currents": edge_currents,
        "edge_powers": edge_powers,
        "electrode_voltages": dict(voltages),
        "driven_voltages": dict(driven_voltages),
        "warning": (
            "RESEARCHER-ONLY internal state. Never consume this from "
            "the harvester pipeline."
        ),
    }


__all__ = [
    "PhysicsSolver",
    "SolverDidNotConverge",
    "build_solver",
    "solve_with_internal_state",
]
