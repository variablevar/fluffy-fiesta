"""Tests for damage application.

The harvester must NOT receive a defect map. Damage is a hidden
mutation applied inside World A.
"""

from __future__ import annotations

import numpy as np

from rocksim.material.defects import damage_material
from rocksim.material.graph import (
    MaterialBuildParams,
    build_material,
)


def test_damage_zero_is_noop():
    m = build_material(
        MaterialBuildParams(master_seed=4, n_hidden_nodes=30)
    )
    g_before = [e.conductance(0.0) for _, _, e in m.edges]
    n = damage_material(m, fraction=0.0, seed=4)
    assert n == 0
    g_after = [e.conductance(0.0) for _, _, e in m.edges]
    assert g_before == g_after


def test_damage_cuts_some_edges():
    m = build_material(
        MaterialBuildParams(master_seed=5, n_hidden_nodes=40)
    )
    g_before = np.array([e.conductance(0.0) for _, _, e in m.edges])
    n = damage_material(m, fraction=0.20, seed=2)
    assert n == int(round(0.20 * len(m.edges)))
    g_after = np.array([e.conductance(0.0) for _, _, e in m.edges])
    # The conductance of damaged edges should be exactly zero.
    diffs = g_before - g_after
    n_zeroed = int(np.sum(diffs > 0))
    assert n_zeroed == n


def test_damage_changes_observed_measurement_only_through_public_api():
    """Damage is invisible except through changed Measurement values.

    We compare two measurements: one before damage and one after. The
    only thing the harvester sees is the change in electrode voltages.
    """
    from rocksim.interface import build_blackbox
    from rocksim.physics.solver import build_solver

    def measure(seed):
        m = build_material(
            MaterialBuildParams(
                master_seed=seed, n_hidden_nodes=30,
            )
        )
        solver = build_solver(m)
        iface = build_blackbox(m, solver)
        return iface.evaluate({0: 1.0, 1: 0.0})

    before = measure(7)
    m2 = build_material(MaterialBuildParams(master_seed=7, n_hidden_nodes=30))
    damage_material(m2, fraction=0.30, seed=11)
    solver = build_solver(m2)
    iface = build_blackbox(m2, solver)
    after = iface.evaluate({0: 1.0, 1: 0.0})

    # At least one electrode voltage must differ between before and
    # after, even with the same external drive.
    keys = sorted(before.electrode_voltages.keys())
    any_change = False
    for k in keys:
        if before.electrode_voltages[k] != after.electrode_voltages[k]:
            any_change = True
            break
    assert any_change
