"""Tests for the complete 5-phase damage-recovery experiment."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

import pytest

from rocksim.config import (
    STATUS_BROKEN_BY_DAMAGE,
    STATUS_DISCOVERY_FAILED,
    STATUS_RECOVERED,
    STATUS_RECOVERY_FAILED,
    STATUS_SURVIVED_DAMAGE,
)
from rocksim.experiments.damage_recovery import (
    _candidate_from_dict,
    _compare_candidates,
    run_damage_recovery,
)
from rocksim.interface import (
    MaterialInterface,
    Measurement,
    build_blackbox,
)
from rocksim.material.graph import (
    MaterialBuildParams,
    build_material,
)
from rocksim.physics.solver import build_solver


def test_candidate_from_dict_round_trip():
    d = {
        "input_a": 1, "input_b": 2, "output": 3,
        "biases": {"4": 0.5, "5": -0.3},
        "output_threshold": 0.42,
    }
    cand = _candidate_from_dict(d)
    assert cand.input_a == 1
    assert cand.input_b == 2
    assert cand.output == 3
    assert cand.biases == {4: 0.5, 5: -0.3}
    assert cand.output_threshold == pytest.approx(0.42)


def test_compare_candidates_flags_changes():
    old = {
        "input_a": 0, "input_b": 1, "output": 2,
        "biases": {"3": 0.5},
        "output_threshold": 0.5,
    }
    new_same = dict(old)
    cmp = _compare_candidates(old, new_same)
    assert cmp["input_a_changed"] is False
    assert cmp["bias_electrodes_changed"] is False
    assert cmp["bias_values_changed"] is False
    new_diff = {
        "input_a": 5, "input_b": 1, "output": 2,
        "biases": {"3": 0.5, "4": 0.2},
        "output_threshold": 0.5,
    }
    cmp2 = _compare_candidates(old, new_diff)
    assert cmp2["input_a_changed"] is True
    assert cmp2["bias_electrodes_changed"] is True
    assert cmp2["bias_values_changed"] is True


def test_run_damage_recovery_completes_all_five_phases():
    """End-to-end with a small budget; check that all phase files exist.

    We do not require success; the experiment may legitimately
    end in DISCOVERY_FAILED, BROKEN_BY_DAMAGE, or RECOVERED.
    """
    with tempfile.TemporaryDirectory() as d:
        summary = run_damage_recovery(
            seed=1,
            damage_fraction=0.05,
            iterations=20,
            n_hidden_nodes=40,
            electrode_count=32,
            output_dir=os.path.join(d, "out"),
            blender_export_path=os.path.join(d, "blender.json"),
        )
        assert summary["experiment"] == "damage_recovery"
        assert summary["status"] in (
            STATUS_DISCOVERY_FAILED,
            STATUS_SURVIVED_DAMAGE,
            STATUS_BROKEN_BY_DAMAGE,
            STATUS_RECOVERED,
            STATUS_RECOVERY_FAILED,
        )
        # All five phase sub-records exist (when discovery succeeded;
        # otherwise only summary + base_dir).
        base = summary["base_dir"]
        if summary["status"] != STATUS_DISCOVERY_FAILED:
            assert os.path.exists(os.path.join(base, "phase_B_baseline.json"))
            assert os.path.exists(os.path.join(base, "phase_D_old_on_damaged.json"))
            assert os.path.exists(os.path.join(base, "phase_E_recovery.json"))
        # Researcher-only files are written when discovery succeeded.
        if summary["status"] != STATUS_DISCOVERY_FAILED:
            assert os.path.exists(
                os.path.join(base, "researcher_damage_map.json")
            )
            assert os.path.exists(os.path.join(d, "blender.json"))


def test_researcher_blender_export_writes_damaged_and_recovered_blocks():
    """The Blender export is researcher-only and includes the
    pristine, damaged, and (when recovered) recovered blocks.
    """
    import json
    from rocksim.export.blender_json import (
        export_researcher_ground_truth,
        write_blender_json,
    )
    material = build_material(
        MaterialBuildParams(master_seed=1, n_hidden_nodes=20)
    )
    damaged_material = build_material(
        MaterialBuildParams(master_seed=1, n_hidden_nodes=20)
    )
    from rocksim.material.defects import damage_material
    n = damage_material(damaged_material, 0.10, seed=1)
    edges_damaged = {
        (int(u), int(v)) if u < v else (int(v), int(u))
        for (u, v, e) in damaged_material.edges
        if e.conductance(0.0) == 0.0
    }
    cand = {"input_a": 0, "input_b": 1, "output": 2,
            "biases": {"3": 0.1}, "output_threshold": 0.5}
    exp = export_researcher_ground_truth(
        material=material,
        drive={0: 1.0, 1: 0.0},
        candidate=cand,
        damaged_edges=edges_damaged,
        damaged_material=damaged_material,
    )
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "blender.json")
        write_blender_json(exp, path)
        with open(path) as fh:
            payload = json.load(fh)
        # Pristine + damaged present, recovered absent.
        assert "pristine" in payload
        assert "damaged" in payload
        assert payload["recovered"] is None
        # Researcher fields present in each state.
        for state in ("pristine", "damaged"):
            for node in payload[state]["hidden_nodes"]:
                assert "voltage_V" in node
            for e in payload[state]["edges"]:
                assert "current_A_u_to_v" in e
                assert "power_W" in e
                assert "voltage_drop_V" in e
        # Damaged edges are marked.
        damaged_marks = [
            e for e in payload["damaged"]["edges"] if e.get("damaged")
        ]
        assert len(damaged_marks) > 0
        # Roles on electrodes.
        for state in ("pristine", "damaged"):
            roles = {e["electrode_id"]: e["role"] for e in payload[state]["electrodes"]}
            assert roles[0] == "A"
            assert roles[1] == "B"
            assert roles[2] == "OUTPUT"
            assert roles[3] == "BIAS"
