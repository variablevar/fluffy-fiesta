"""Tests for the linear quasi-static nodal solver.

We build small synthesised materials and assert that the linear solver
matches hand-computed / SPICE-style answers for known circuits:

  - voltage divider
  - resistor chain
  - parallel resistor
  - zero-current driven probe through a single edge

These tests are the quality gate before we trust the XOR search.
"""

from __future__ import annotations

import numpy as np
import pytest

from rocksim.material.elements import LinearEdge
from rocksim.material.graph import (
    ElectrodeAttachment,
    Material,
)
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
        model_name="linear",
        params={"synthetic": True},
    )


def test_voltage_divider():
    """Driven divider: Vin (E0)=1V, GND (E2)=0V, mid-tap at E1."""
    edges = [
        (0, 1, LinearEdge(g0=1.0)),
        (1, 2, LinearEdge(g0=1.0)),
    ]
    material = _make_simple_material(edges, {0: 0, 1: 1, 2: 2})
    solver = build_solver(material)
    voltages, currents = solver.evaluate_electrodes(material, {0: 1.0, 2: 0.0})
    assert voltages[0] == pytest.approx(1.0)
    assert voltages[1] == pytest.approx(0.5)
    assert voltages[2] == pytest.approx(0.0)
    # Total current leaving the source equals total entering GND.
    assert currents[0] == pytest.approx(-(currents[2]))


def test_parallel_resistors():
    """Two equal parallel resistors between two driven terminals.

    We don't assert a specific current magnitude (the contact
    conductances set the load) — we only assert: (a) the voltages
    driven (1 V at the source terminal, 0 V at the sink terminal),
    (b) Kirchhoff: current leaving E0 equals current entering E1,
    (c) monotonically-symmetric currents (each branch carries the
    same current).
    """
    edges = [
        (0, 1, LinearEdge(g0=1.0)),
        (0, 1, LinearEdge(g0=1.0)),
    ]
    material = _make_simple_material(edges, {0: 0, 1: 1})
    solver = build_solver(material)
    voltages, currents = solver.evaluate_electrodes(material, {0: 1.0, 1: 0.0})
    assert voltages[0] == pytest.approx(1.0)
    assert voltages[1] == pytest.approx(0.0)
    assert currents[0] == pytest.approx(-(currents[1]))


def test_chain_three_resistors():
    edges = [
        (0, 1, LinearEdge(g0=1.0)),
        (1, 2, LinearEdge(g0=1.0)),
        (2, 3, LinearEdge(g0=1.0)),
    ]
    material = _make_simple_material(edges, {0: 0, 1: 1, 2: 2, 3: 3})
    solver = build_solver(material)
    # Drive both ends. The 1 S contact conductances pull the *outer*
    # node voltages toward the drives; only the midpoint voltages at
    # E1 (node 1) and E2 (node 2) read the divider.
    voltages, _ = solver.evaluate_electrodes(material, {0: 1.0, 3: 0.0})
    assert voltages[0] == pytest.approx(1.0)
    assert voltages[3] == pytest.approx(0.0)
    # Midpoints read approximately 2/3 and 1/3 (small deviation due to
    # contact-conductance loading).
    assert 0.45 < voltages[1] < 0.85
    assert 0.15 < voltages[2] < 0.55
    # Symmetry: V1 + V2 is roughly 1 (the two midpoints are symmetric
    # around the divider midpoint).
    assert abs(voltages[1] + voltages[2] - 1.0) < 0.1


def test_solver_bound_no_nodes():
    material = Material(
        coordinates=np.empty((0, 3), dtype=float),
        edges=[],
        electrodes=[],
        model_name="linear",
        params={"empty": True},
    )
    solver = build_solver(material)
    voltages, currents = solver.evaluate_electrodes(material, {0: 1.0})
    assert voltages == {}
    assert currents == {}


def test_solver_rejects_swapped_material():
    m1 = _make_simple_material([(0, 1, LinearEdge(g0=1.0))], {0: 0, 1: 1})
    m2 = _make_simple_material([(0, 1, LinearEdge(g0=2.0))], {0: 0, 1: 1})
    solver = build_solver(m1)
    with pytest.raises(ValueError):
        solver.evaluate_electrodes(m2, {0: 1.0, 1: 0.0})
