"""Tests for material generation + electrode placement."""

from __future__ import annotations

import numpy as np
import pytest

from rocksim.material.geometry import GeometryParams, generate_coordinates
from rocksim.material.graph import (
    MaterialBuildParams,
    build_material,
)


def test_generate_coordinates_shape():
    g = GeometryParams(seed=7)
    coords = generate_coordinates(50, g)
    assert coords.shape == (50, 3)
    assert np.all(np.isfinite(coords))


def test_generate_coordinates_is_seed_deterministic():
    g_a = GeometryParams(seed=11)
    g_b = GeometryParams(seed=11)
    a = generate_coordinates(40, g_a)
    b = generate_coordinates(40, g_b)
    assert np.allclose(a, b)


def test_material_has_distinct_electrodes():
    m = build_material(
        MaterialBuildParams(master_seed=2, n_hidden_nodes=60)
    )
    assert m.n_hidden_nodes() == 60
    assert m.n_electrodes() == 32
    # Each electrode should have at least one attached hidden node.
    for e in m.electrodes:
        assert len(e.attached_nodes) >= 1
    # Electrode ids are unique.
    ids = [e.electrode_id for e in m.electrodes]
    assert sorted(ids) == list(range(32))


def test_material_is_seed_deterministic():
    m_a = build_material(
        MaterialBuildParams(master_seed=3, n_hidden_nodes=40)
    )
    m_b = build_material(
        MaterialBuildParams(master_seed=3, n_hidden_nodes=40)
    )
    assert np.allclose(m_a.coordinates, m_b.coordinates)
    assert len(m_a.edges) == len(m_b.edges)
    for (u1, v1, e1), (u2, v2, e2) in zip(m_a.edges, m_b.edges):
        assert (u1, v1) == (u2, v2)
        assert e1.conductance(0.0) == pytest.approx(e2.conductance(0.0))


def test_different_seeds_give_different_materials():
    m_a = build_material(
        MaterialBuildParams(master_seed=1, n_hidden_nodes=40)
    )
    m_b = build_material(
        MaterialBuildParams(master_seed=99, n_hidden_nodes=40)
    )
    assert not np.allclose(m_a.coordinates, m_b.coordinates)


def test_edges_are_positive_conductance():
    m = build_material(
        MaterialBuildParams(master_seed=5, n_hidden_nodes=40)
    )
    for _, _, e in m.edges:
        g = e.conductance(0.0)
        assert g > 0
