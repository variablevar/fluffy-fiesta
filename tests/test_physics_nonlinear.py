"""Tests for the nonlinear solver."""

from __future__ import annotations

import numpy as np
import pytest

from rocksim.material.elements import NonlinearEdge
from rocksim.material.graph import (
    ElectrodeAttachment,
    Material,
)
from rocksim.physics.errors import SolverDidNotConverge
from rocksim.physics.solver import build_solver


def _make_simple_material(edges, electrode_nodes, contact_conductance=1.0):
    n_hidden = max(max(u, v) for u, v, _ in edges) + 1
    coords = np.zeros((n_hidden, 3), dtype=float)
    for i in range(n_hidden):
        coords[i] = (float(i), 0.0, 0.0)
    electrodes = [
        ElectrodeAttachment(
            electrode_id=eid,
            attached_nodes=[nid],
            contact_conductance=contact_conductance,
        )
        for eid, nid in electrode_nodes.items()
    ]
    return Material(
        coordinates=coords,
        edges=edges,
        electrodes=electrodes,
        model_name="nonlinear",
        params={"synthetic": True},
    )


def test_nonlinear_converges_to_linear_when_alpha_zero():
    """When alpha = 0, the nonlinear solver should match the linear one."""
    edges_lin = [
        (0, 1, NonlinearEdge(g0=1.0, alpha=0.0)),
        (1, 2, NonlinearEdge(g0=1.0, alpha=0.0)),
    ]
    material = _make_simple_material(edges_lin, {0: 0, 1: 1, 2: 2})
    solver = build_solver(material)
    voltages, _ = solver.evaluate_electrodes(
        material, {0: 1.0, 2: 0.0}
    )
    assert voltages[1] == pytest.approx(0.5, abs=1e-6)
    assert voltages[2] == pytest.approx(0.0, abs=1e-9)


def test_nonlinear_changes_conductance_with_voltage():
    """Asymmetric nonlinearity shifts the divider midpoint from 0.5 V.

    A symmetric setup always gives V1 = 0.5 because both branches see the
    same |V|. To make the nonlinearity observable we use one linear edge
    and one nonlinear edge; the conductances then differ.
    """
    edges = [
        (0, 1, NonlinearEdge(g0=1.0, alpha=20.0)),  # strongly nonlinear
        (1, 2, NonlinearEdge(g0=1.0, alpha=0.0)),  # linear
    ]
    material = _make_simple_material(
        edges, {0: 0, 1: 1, 2: 2}, contact_conductance=0.1,
    )
    solver = build_solver(material)
    voltages, _ = solver.evaluate_electrodes(
        material, {0: 1.0, 2: 0.0}
    )
    # Midpoint differs measurably from 0.5 V.
    assert abs(voltages[1] - 0.5) > 5e-4


def test_nonlinear_does_not_crash_for_harmless_drives():
    edges = [
        (0, 1, NonlinearEdge(g0=1.0, alpha=1.0)),
        (1, 2, NonlinearEdge(g0=1.0, alpha=1.0)),
    ]
    material = _make_simple_material(edges, {0: 0, 1: 1, 2: 2})
    solver = build_solver(material)
    voltages, _ = solver.evaluate_electrodes(
        material, {0: 1.0, 2: 0.0}
    )
    for v in voltages.values():
        assert np.isfinite(v)
        assert 0.0 <= v <= 1.0
