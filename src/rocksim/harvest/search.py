"""Search strategies for the harvester."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from rocksim.config import (
    BIAS_LIMIT_ABS,
    DEFAULT_MIN_MARGIN,
    DEFAULT_XOR_OUTPUT_THRESHOLD,
    SignalLevels,
    XOR_TRUTH_TABLE,
)
from rocksim.harvest.candidate import (
    Candidate,
    CandidateError,
    validate_candidate,
)
from rocksim.harvest.fitness import (
    FitnessBreakdown,
    TruthTable,
    evaluate_candidate,
    fitness_from_truth_table,
)
from rocksim.interface import MaterialInterface


SearchStrategy = Callable[
    ["SearchProblem", "SearchBudget", int],
    "SearchResult",
]


@dataclass
class SearchProblem:
    """The information a strategy needs (no internal material access!)."""

    material_iface: MaterialInterface
    electrode_count: int
    bias_limit: float = BIAS_LIMIT_ABS
    signal_levels: SignalLevels = field(default_factory=SignalLevels)
    output_threshold: float = DEFAULT_XOR_OUTPUT_THRESHOLD
    min_margin: float = DEFAULT_MIN_MARGIN

    def evaluate(
        self, candidate: Candidate,
    ) -> tuple[TruthTable, FitnessBreakdown]:
        """Evaluate a single candidate. May raise on solver failure."""
        validate_candidate(
            candidate,
            electrode_count=self.electrode_count,
            bias_limit=self.bias_limit,
            low=self.signal_levels.low,
            high=self.signal_levels.high,
        )
        tt = evaluate_candidate(
            material_iface=self.material_iface,
            candidate=candidate,
            bias_limit=self.bias_limit,
            signal_levels=self.signal_levels,
        )
        fb = fitness_from_truth_table(
            tt,
            threshold=self.output_threshold,
            min_margin=self.min_margin,
        )
        return tt, fb


@dataclass
class SearchBudget:
    max_iterations: int


@dataclass
class SearchResult:
    iterations: int
    best_candidate: Candidate
    best_fitness: float
    success: bool
    best_truth_table: TruthTable | None = None
    best_breakdown: FitnessBreakdown | None = None
    history: list[dict] = field(default_factory=list)
    n_solver_failures: int = 0
    n_illegal_candidates: int = 0
    n_valid_evaluated: int = 0
    best_outputs: dict[str, float] = field(default_factory=dict)
    best_margin: float = 0.0
    best_accuracy: int = 0
    status: str = ""


def _outputs_by_row(tt: TruthTable | None) -> dict[str, float]:
    """Return {00, 01, 10, 11} -> voltage mapping for a truth table."""
    out = {"00": 0.0, "01": 0.0, "10": 0.0, "11": 0.0}
    if tt is None:
        return out
    for row in tt.rows:
        out[f"{row.a_bit}{row.b_bit}"] = float(row.v_out)
    return out


def _row_dict(
    it: int,
    fb: FitnessBreakdown,
    accepted: int,
) -> dict:
    """Compact per-iteration history row."""
    return {
        "iteration": int(it),
        "fitness": float(fb.fitness),
        "accuracy": int(fb.n_correct),
        "margin": float(fb.margin),
    }


def _best_row_dict(it: int, fb: FitnessBreakdown, tt: TruthTable) -> dict:
    """Snapshot of the BEST so far after this iteration."""
    out = _outputs_by_row(tt)
    return {
        "iteration": int(it),
        "best_fitness": float(fb.fitness),
        "best_accuracy": int(fb.n_correct),
        "best_margin": float(fb.margin),
        "best_output_00": out["00"],
        "best_output_01": out["01"],
        "best_output_10": out["10"],
        "best_output_11": out["11"],
    }



def random_candidate(
    rng: np.random.Generator,
    electrode_count: int,
    bias_limit: float,
    low: float,
    high: float,
    output_threshold: float | None = None,
    max_bias_electrodes: int = 0,
    threshold_low: float | None = None,
    threshold_high: float | None = None,
) -> Candidate:
    """Build a uniformly random *legal* candidate."""
    if electrode_count < 3:
        raise CandidateError(
            f"need at least 3 electrodes, got {electrode_count}"
        )

    ids = list(range(electrode_count))
    chosen_a = int(rng.choice(ids))
    remaining = [i for i in ids if i != chosen_a]
    chosen_b = int(rng.choice(remaining))
    remaining = [i for i in remaining if i != chosen_b]
    chosen_out = int(rng.choice(remaining))

    forbidden = {chosen_a, chosen_b, chosen_out}
    available_for_bias = [i for i in ids if i not in forbidden]
    n_bias = (
        int(rng.integers(0, max(1, max_bias_electrodes + 1)))
        if max_bias_electrodes > 0
        else 0
    )
    n_bias = min(n_bias, len(available_for_bias))
    if n_bias > 0:
        bias_ids = list(
            rng.choice(available_for_bias, size=n_bias, replace=False)
        )
    else:
        bias_ids = []
    biases = {
        int(eid): float(rng.uniform(-bias_limit, bias_limit))
        for eid in bias_ids
    }

    t_lo = threshold_low if threshold_low is not None else low
    t_hi = threshold_high if threshold_high is not None else high
    thr = (
        float(rng.uniform(t_lo, t_hi))
        if output_threshold is None
        else float(output_threshold)
    )

    cand = Candidate(
        input_a=chosen_a,
        input_b=chosen_b,
        output=chosen_out,
        biases=biases,
        output_threshold=thr,
    )
    validate_candidate(
        cand,
        electrode_count=electrode_count,
        bias_limit=bias_limit,
        low=low,
        high=high,
    )
    return cand


def mutate_candidate(
    rng: np.random.Generator,
    cand: Candidate,
    electrode_count: int,
    bias_limit: float,
    low: float,
    high: float,
    p_swap_inputs: float = 0.10,
    p_swap_output: float = 0.10,
    p_jitter_bias: float = 0.40,
    p_jitter_threshold: float = 0.10,
    p_drop_bias: float = 0.05,
    p_add_bias: float = 0.05,
    max_bias_electrodes: int = 6,
) -> Candidate:
    """Mutate a candidate. Repairs and resamples if mutation is illegal."""
    new_a = cand.input_a
    new_b = cand.input_b
    new_out = cand.output
    new_biases = dict(cand.biases)
    new_thr = cand.output_threshold

    if rng.random() < p_swap_inputs:
        ids = list(range(electrode_count))
        if rng.random() < 0.5:
            choices = [i for i in ids if i not in (new_a, new_out)]
            new_b = int(rng.choice(choices))
        else:
            choices = [i for i in ids if i not in (new_b, new_out)]
            new_a = int(rng.choice(choices))

    if rng.random() < p_swap_output:
        ids = list(range(electrode_count))
        choices = [i for i in ids if i not in (new_a, new_b)]
        new_out = int(rng.choice(choices))

    if rng.random() < p_jitter_bias and new_biases:
        eid = int(rng.choice(list(new_biases.keys())))
        new_biases[eid] = float(
            np.clip(
                new_biases[eid] + rng.normal(0.0, 0.05 * bias_limit),
                -bias_limit,
                bias_limit,
            )
        )

    if rng.random() < p_drop_bias and new_biases:
        eid = int(rng.choice(list(new_biases.keys())))
        new_biases.pop(eid, None)

    if rng.random() < p_add_bias:
        forbidden = {new_a, new_b, new_out} | set(new_biases.keys())
        available = [
            i for i in range(electrode_count) if i not in forbidden
        ]
        if available and len(new_biases) < max_bias_electrodes:
            eid = int(rng.choice(available))
            new_biases[eid] = float(rng.uniform(-bias_limit, bias_limit))

    if rng.random() < p_jitter_threshold:
        new_thr = float(
            np.clip(
                new_thr + rng.normal(0.0, 0.02 * (high - low)),
                low,
                high,
            )
        )

    new_cand = Candidate(
        input_a=new_a,
        input_b=new_b,
        output=new_out,
        biases=new_biases,
        output_threshold=new_thr,
    )
    try:
        validate_candidate(
            new_cand,
            electrode_count=electrode_count,
            bias_limit=bias_limit,
            low=low,
            high=high,
        )
    except CandidateError:
        return random_candidate(
            rng=rng,
            electrode_count=electrode_count,
            bias_limit=bias_limit,
            low=low,
            high=high,
            output_threshold=new_thr,
            max_bias_electrodes=min(len(new_biases), max_bias_electrodes),
            threshold_low=low,
            threshold_high=high,
        )
    return new_cand


def _make_search_result(
    iterations: int,
    best_cand: Candidate | None,
    best_fitness: float,
    best_tt: TruthTable | None,
    best_fb: FitnessBreakdown | None,
    history: list[dict],
    n_solver_failures: int,
    n_illegal_candidates: int,
    n_valid_evaluated: int,
    status_success: bool,
    status_string: str,
) -> SearchResult:
    """Assemble a SearchResult, including the new rich fields."""
    if best_cand is None:
        # Defend against the empty-bug case.
        best_cand = Candidate(
            input_a=0, input_b=1, output=2,
            biases={}, output_threshold=0.5,
        )
    outs = _outputs_by_row(best_tt)
    return SearchResult(
        iterations=int(iterations),
        best_candidate=best_cand,
        best_fitness=float(best_fitness),
        success=bool(status_success),
        best_truth_table=best_tt,
        best_breakdown=best_fb,
        history=list(history),
        n_solver_failures=int(n_solver_failures),
        n_illegal_candidates=int(n_illegal_candidates),
        n_valid_evaluated=int(n_valid_evaluated),
        best_outputs=outs,
        best_margin=(
            float(best_fb.margin) if best_fb is not None else 0.0
        ),
        best_accuracy=(
            int(best_fb.n_correct) if best_fb is not None else 0
        ),
        status=str(status_string),
    )


def random_search(
    problem: SearchProblem,
    budget: SearchBudget,
    seed: int,
) -> SearchResult:
    """Pure random uniform search.

    History rows are the BEST-so-far snapshot. Per-iteration raw rows
    are intentionally omitted from history (would double the file size
    without aiding analysis); they are still counted via the
    n_valid_evaluated / n_solver_failures fields.
    """
    rng = np.random.default_rng(seed)
    history: list[dict] = []

    best_cand: Candidate | None = None
    best_fitness = -float("inf")
    best_tt: TruthTable | None = None
    best_fb: FitnessBreakdown | None = None

    n_solver_failures = 0
    n_illegal = 0
    n_valid = 0

    status = "SEARCH_EXHAUSTED"
    last_it = 0

    for it in range(int(budget.max_iterations)):
        last_it = it + 1
        try:
            cand = random_candidate(
                rng=rng,
                electrode_count=problem.electrode_count,
                bias_limit=problem.bias_limit,
                low=problem.signal_levels.low,
                high=problem.signal_levels.high,
                output_threshold=problem.output_threshold,
                max_bias_electrodes=4,
                threshold_low=problem.signal_levels.low,
                threshold_high=problem.signal_levels.high,
            )
        except CandidateError:
            n_illegal += 1
            continue

        try:
            tt, fb = problem.evaluate(cand)
        except Exception:  # noqa: BLE001
            n_solver_failures += 1
            continue

        n_valid += 1
        if fb.fitness > best_fitness:
            best_fitness = fb.fitness
            best_cand = cand
            best_tt = tt
            best_fb = fb
            history.append(_best_row_dict(it, fb, tt))
            if fb.success:
                return _make_search_result(
                    iterations=last_it,
                    best_cand=best_cand,
                    best_fitness=best_fitness,
                    best_tt=best_tt,
                    best_fb=best_fb,
                    history=history,
                    n_solver_failures=n_solver_failures,
                    n_illegal_candidates=n_illegal,
                    n_valid_evaluated=n_valid,
                    status_success=True,
                    status_string="SEARCH_SUCCESS",
                )

    return _make_search_result(
        iterations=last_it,
        best_cand=best_cand,
        best_fitness=best_fitness,
        best_tt=best_tt,
        best_fb=best_fb,
        history=history,
        n_solver_failures=n_solver_failures,
        n_illegal_candidates=n_illegal,
        n_valid_evaluated=n_valid,
        status_success=False,
        status_string=status,
    )


def hill_climb(
    problem: SearchProblem,
    budget: SearchBudget,
    seed: int,
) -> SearchResult:
    """Hill climb with random restarts."""
    rng = np.random.default_rng(seed)
    history: list[dict] = []

    best_cand: Candidate | None = None
    best_fitness = -float("inf")
    best_tt: TruthTable | None = None
    best_fb: FitnessBreakdown | None = None

    stall = max(50, int(budget.max_iterations) // 50)
    no_improve = 0

    n_solver_failures = 0
    n_illegal = 0
    n_valid = 0

    status = "SEARCH_EXHAUSTED"
    last_it = 0

    for it in range(int(budget.max_iterations)):
        last_it = it + 1
        is_restart = (it == 0 or no_improve >= stall)
        try:
            if is_restart:
                cand = random_candidate(
                    rng=rng,
                    electrode_count=problem.electrode_count,
                    bias_limit=problem.bias_limit,
                    low=problem.signal_levels.low,
                    high=problem.signal_levels.high,
                    output_threshold=problem.output_threshold,
                    max_bias_electrodes=4,
                    threshold_low=problem.signal_levels.low,
                    threshold_high=problem.signal_levels.high,
                )
            else:
                cand = mutate_candidate(
                    rng=rng,
                    cand=best_cand if best_cand is not None else Candidate(
                        input_a=0,
                        input_b=1,
                        output=2,
                    ),
                    electrode_count=problem.electrode_count,
                    bias_limit=problem.bias_limit,
                    low=problem.signal_levels.low,
                    high=problem.signal_levels.high,
                )
        except CandidateError:
            n_illegal += 1
            continue

        try:
            tt, fb = problem.evaluate(cand)
        except Exception:  # noqa: BLE001
            n_solver_failures += 1
            continue

        n_valid += 1
        improved = fb.fitness > best_fitness
        if improved:
            best_fitness = fb.fitness
            best_cand = cand
            best_tt = tt
            best_fb = fb
            history.append(_best_row_dict(it, fb, tt))
            no_improve = 0
        else:
            no_improve += 1

        if fb.success:
            return _make_search_result(
                iterations=last_it,
                best_cand=best_cand,
                best_fitness=best_fitness,
                best_tt=best_tt,
                best_fb=best_fb,
                history=history,
                n_solver_failures=n_solver_failures,
                n_illegal_candidates=n_illegal,
                n_valid_evaluated=n_valid,
                status_success=True,
                status_string="SEARCH_SUCCESS",
            )

    return _make_search_result(
        iterations=last_it,
        best_cand=best_cand,
        best_fitness=best_fitness,
        best_tt=best_tt,
        best_fb=best_fb,
        history=history,
        n_solver_failures=n_solver_failures,
        n_illegal_candidates=n_illegal,
        n_valid_evaluated=n_valid,
        status_success=False,
        status_string=status,
    )


STRATEGY_REGISTRY: dict[str, SearchStrategy] = {
    "random": random_search,
    "hill_climb": hill_climb,
}


__all__ = [
    "SearchStrategy",
    "SearchProblem",
    "SearchBudget",
    "SearchResult",
    "random_search",
    "hill_climb",
    "mutate_candidate",
    "random_candidate",
    "STRATEGY_REGISTRY",
]
