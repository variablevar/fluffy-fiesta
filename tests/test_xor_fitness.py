"""Tests for candidate validation, fitness, and the XOR evaluator."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from rocksim.config import (
    HIGH_VOLTAGE,
    LOW_VOLTAGE,
    SignalLevels,
)
from rocksim.harvest.candidate import (
    Candidate,
    CandidateError,
    validate_candidate,
)
from rocksim.harvest.fitness import (
    evaluate_candidate,
    fitness_from_truth_table,
)
from rocksim.harvest.search import (
    SearchBudget,
    SearchProblem,
    random_search,
)
from rocksim.interface import (
    MaterialInterface,
    Measurement,
)


@dataclass
class _FakeMaterial:
    """In-memory fake for fitness tests. NOT used by the real simulator."""

    truth_table_voltages: dict[tuple[int, int], float]
    electrode_count: int = 4

    def evaluate(self, driven_voltages: dict) -> Measurement:
        a_bit = int(round(driven_voltages.get(0, LOW_VOLTAGE)))
        b_bit = int(round(driven_voltages.get(1, LOW_VOLTAGE)))
        v = self.truth_table_voltages.get((a_bit, b_bit), 0.0)
        voltages = {i: 0.0 for i in range(self.electrode_count)}
        currents = {i: 0.0 for i in range(self.electrode_count)}
        voltages[0] = float(driven_voltages.get(0, LOW_VOLTAGE))
        voltages[1] = float(driven_voltages.get(1, LOW_VOLTAGE))
        voltages[2] = v
        return Measurement(
            electrode_voltages=voltages, electrode_currents=currents,
        )


def test_validate_candidate_legal():
    cand = Candidate(
        input_a=0, input_b=1, output=2,
        biases={}, output_threshold=0.5,
    )
    validate_candidate(
        cand, electrode_count=4, bias_limit=1.0,
        low=LOW_VOLTAGE, high=HIGH_VOLTAGE,
    )


def test_validate_candidate_rejects_overlap():
    cand = Candidate(
        input_a=0, input_b=0, output=2,
        biases={}, output_threshold=0.5,
    )
    with pytest.raises(CandidateError):
        validate_candidate(
            cand, electrode_count=4, bias_limit=1.0,
            low=LOW_VOLTAGE, high=HIGH_VOLTAGE,
        )


def test_validate_candidate_rejects_bias_on_output():
    cand = Candidate(
        input_a=0, input_b=1, output=2,
        biases={2: 0.5}, output_threshold=0.5,
    )
    with pytest.raises(CandidateError):
        validate_candidate(
            cand, electrode_count=4, bias_limit=1.0,
            low=LOW_VOLTAGE, high=HIGH_VOLTAGE,
        )


def test_validate_candidate_rejects_bias_over_limit():
    cand = Candidate(
        input_a=0, input_b=1, output=2,
        biases={3: 1.5}, output_threshold=0.5,
    )
    with pytest.raises(CandidateError):
        validate_candidate(
            cand, electrode_count=4, bias_limit=1.0,
            low=LOW_VOLTAGE, high=HIGH_VOLTAGE,
        )


def test_evaluate_candidate_runs_all_four_rows():
    iface = _FakeMaterial(
        {(0, 0): 0.1, (0, 1): 0.9, (1, 0): 0.8, (1, 1): 0.2},
        electrode_count=4,
    )
    cand = Candidate(
        input_a=0, input_b=1, output=2,
        biases={3: 0.2}, output_threshold=0.5,
    )
    tt = evaluate_candidate(
        iface, cand, bias_limit=1.0, signal_levels=SignalLevels(),
    )
    assert len(tt.rows) == 4
    by_row = {(r.a_bit, r.b_bit): r for r in tt.rows}
    assert by_row[(0, 0)].v_out == 0.1
    assert by_row[(0, 1)].v_out == 0.9
    assert by_row[(1, 0)].v_out == 0.8
    assert by_row[(1, 1)].v_out == 0.2
    assert by_row[(0, 0)].predicted_bit == 0
    assert by_row[(0, 1)].predicted_bit == 1
    assert by_row[(1, 0)].predicted_bit == 1
    assert by_row[(1, 1)].predicted_bit == 0


def test_fitness_success_when_all_correct_with_margin():
    iface = _FakeMaterial(
        {(0, 0): 0.10, (0, 1): 0.85, (1, 0): 0.90, (1, 1): 0.20},
        electrode_count=4,
    )
    cand = Candidate(
        input_a=0, input_b=1, output=2,
        biases={}, output_threshold=0.5,
    )
    tt = evaluate_candidate(
        iface, cand, bias_limit=1.0, signal_levels=SignalLevels(),
    )
    fb = fitness_from_truth_table(tt, threshold=0.5, min_margin=0.05)
    assert fb.success is True
    assert fb.all_correct is True
    assert fb.margin_satisfied is True
    assert fb.n_correct == 4


def test_fitness_failure_with_insufficient_margin():
    # Margin is tiny around the threshold. Several bits misclassify,
    # so this must NOT be reported as a successful XOR.
    iface = _FakeMaterial(
        {(0, 0): 0.48, (0, 1): 0.52, (1, 0): 0.49, (1, 1): 0.51},
        electrode_count=4,
    )
    cand = Candidate(
        input_a=0, input_b=1, output=2,
        biases={}, output_threshold=0.5,
    )
    tt = evaluate_candidate(
        iface, cand, bias_limit=1.0, signal_levels=SignalLevels(),
    )
    fb = fitness_from_truth_table(tt, threshold=0.5, min_margin=0.05)
    assert fb.all_correct is False
    assert fb.success is False


def test_xor_real_material_smoke():
    """End-to-end smoke: build a real material and evaluate any candidate.

    We don't assert success; we only assert that the pipeline runs and
    that all four rows produce a finite, finite voltage.
    """
    from rocksim.interface import build_blackbox
    from rocksim.material.graph import MaterialBuildParams, build_material
    from rocksim.physics.solver import build_solver

    material = build_material(
        MaterialBuildParams(
            master_seed=42, n_hidden_nodes=80, model_name="nonlinear",
        )
    )
    solver = build_solver(material)
    iface = build_blackbox(material, solver)
    cand = Candidate(
        input_a=0, input_b=1, output=2,
        biases={3: 0.1}, output_threshold=0.5,
    )
    tt = evaluate_candidate(
        iface, cand, bias_limit=1.0, signal_levels=SignalLevels(),
    )
    fb = fitness_from_truth_table(tt, threshold=0.5, min_margin=0.05)
    for row in tt.rows:
        assert -2.0 < row.v_out < 4.0  # voltage must be reasonable
    assert fb.n_total == 4


def test_random_search_records_rich_fields_and_counters():
    """The random search must populate status, counters, and best outputs."""
    iface = _FakeMaterial(
        {(0, 0): 0.10, (0, 1): 0.85, (1, 0): 0.90, (1, 1): 0.20},
        electrode_count=4,
    )
    problem = SearchProblem(
        material_iface=iface,
        electrode_count=4,
        bias_limit=1.0,
        signal_levels=SignalLevels(),
        output_threshold=0.5,
        min_margin=0.05,
    )
    result = random_search(problem, SearchBudget(50), seed=1)
    # New fields present
    assert result.status in (
        "SEARCH_SUCCESS", "SEARCH_EXHAUSTED",
    )
    assert result.n_valid_evaluated >= 1
    # best_outputs always exposes the four rows
    for k in ("00", "01", "10", "11"):
        assert k in result.best_outputs
    # best_history rows (when present) carry the four outputs and a margin
    for row in result.history:
        for k in (
            "iteration", "best_fitness", "best_accuracy",
            "best_margin", "best_output_00", "best_output_01",
            "best_output_10", "best_output_11",
        ):
            assert k in row
    # If success, status is SEARCH_SUCCESS
    if result.success:
        assert result.status == "SEARCH_SUCCESS"
