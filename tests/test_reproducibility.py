"""Tests for experiment reproducibility.

A 0.1.0 result is "reproducible" iff re-running the experiment from
its saved seeds and config yields the same hidden node voltages
(within numerical tolerance) and the same best-candidate mapping.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np

from rocksim.experiments.reproducibility import (
    check_record_identity,
    load_experiment_record,
    save_experiment_record,
)
from rocksim.experiments.xor_search import run_xor_experiment


def test_material_is_deterministic():
    from rocksim.material.graph import MaterialBuildParams, build_material

    a = build_material(MaterialBuildParams(master_seed=42, n_hidden_nodes=80))
    b = build_material(MaterialBuildParams(master_seed=42, n_hidden_nodes=80))
    assert np.allclose(a.coordinates, b.coordinates)


def test_experiment_record_round_trip():
    record = run_xor_experiment(
        seed=42, material_model="nonlinear", iterations=20,
        n_hidden_nodes=40,
    )
    with tempfile.TemporaryDirectory() as d:
        out_dir = os.path.join(d, "run")
        save_experiment_record(record, out_dir)
        loaded = load_experiment_record(out_dir)
        assert loaded["config"]["master_seed"] == 42
        assert loaded["config"]["material_model"] == "nonlinear"
        # truth table should have 4 rows
        assert len(loaded["truth_table"]) == 4


def test_experiment_record_is_reproducible_from_config():
    record = run_xor_experiment(
        seed=7, material_model="nonlinear", iterations=30,
        n_hidden_nodes=40,
    )
    with tempfile.TemporaryDirectory() as d:
        out_dir = os.path.join(d, "run")
        save_experiment_record(record, out_dir)
        ok, msg = check_record_identity(out_dir, seed=7)
        assert ok, msg
