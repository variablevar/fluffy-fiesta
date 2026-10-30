"""XOR truth-table evaluation and fitness calculation."""

from __future__ import annotations

from dataclasses import dataclass, field

from rocksim.config import (
    DEFAULT_MIN_MARGIN,
    SignalLevels,
    XOR_TRUTH_TABLE,
)
from rocksim.harvest.candidate import Candidate
from rocksim.interface import MaterialInterface, Measurement


@dataclass(frozen=True)
class TruthTableRow:
    a_bit: int
    b_bit: int
    v_out: float
    expected_bit: int
    predicted_bit: int

    def correct(self) -> bool:
        return int(self.predicted_bit) == int(self.expected_bit)


@dataclass
class TruthTable:
    rows: list[TruthTableRow] = field(default_factory=list)

    def all_correct(self) -> bool:
        return all(r.correct() for r in self.rows)

    def n_correct(self) -> int:
        return sum(1 for r in self.rows if r.correct())

    def as_list(self) -> list[dict]:
        return [
            {
                "a": r.a_bit,
                "b": r.b_bit,
                "v_out": r.v_out,
                "expected": r.expected_bit,
                "predicted": r.predicted_bit,
                "correct": bool(r.correct()),
            }
            for r in self.rows
        ]


@dataclass
class FitnessBreakdown:
    n_correct: int
    n_total: int
    margin: float
    min_high: float | None
    max_low: float | None
    fitness: float
    all_correct: bool
    margin_satisfied: bool
    success: bool

    def as_dict(self) -> dict:
        return {
            "n_correct": self.n_correct,
            "n_total": self.n_total,
            "margin": self.margin,
            "min_high": self.min_high,
            "max_low": self.max_low,
            "fitness": self.fitness,
            "all_correct": bool(self.all_correct),
            "margin_satisfied": bool(self.margin_satisfied),
            "success": bool(self.success),
        }

def evaluate_candidate(
    material_iface: MaterialInterface,
    candidate: Candidate,
    bias_limit: float,
    signal_levels: SignalLevels | None = None,
) -> TruthTable:
    """Run the candidate against all four XOR rows.

    Returns a `TruthTable`. Does not raise on bad candidates -- caller
    should call `validate_candidate` first.
    """
    levels = signal_levels or SignalLevels()
    rows: list[TruthTableRow] = []
    for (a_bit, b_bit), expected in XOR_TRUTH_TABLE:
        drives = dict(candidate.biases)
        drives[candidate.input_a] = levels.for_bit(a_bit)
        drives[candidate.input_b] = levels.for_bit(b_bit)
        if candidate.output in drives:
            drives.pop(candidate.output, None)

        measurement: Measurement = material_iface.evaluate(drives)
        v_out = float(
            measurement.electrode_voltages.get(candidate.output, 0.0)
        )
        predicted = 1 if v_out >= candidate.output_threshold else 0
        rows.append(
            TruthTableRow(
                a_bit=a_bit,
                b_bit=b_bit,
                v_out=v_out,
                expected_bit=int(expected),
                predicted_bit=int(predicted),
            )
        )
    _ = bias_limit
    return TruthTable(rows=rows)


def fitness_from_truth_table(
    truth_table: TruthTable,
    threshold: float,
    min_margin: float = DEFAULT_MIN_MARGIN,
) -> FitnessBreakdown:
    """Compute the scalar fitness and success flag.

    Success requires:
        - all four bits correct
        - min_high > threshold + min_margin
        - max_low  < threshold - min_margin
    """
    rows = truth_table.rows
    n_correct = sum(1 for r in rows if r.correct())
    n_total = len(rows)
    if n_total == 0:
        return FitnessBreakdown(
            n_correct=0,
            n_total=0,
            margin=0.0,
            min_high=None,
            max_low=None,
            fitness=-1.0,
            all_correct=False,
            margin_satisfied=False,
            success=False,
        )

    lows = [r.v_out for r in rows if r.expected_bit == 0]
    highs = [r.v_out for r in rows if r.expected_bit == 1]

    if lows and highs:
        max_low = max(lows)
        min_high = min(highs)
        margin = min(min_high - threshold, threshold - max_low)
    else:
        max_low = None
        min_high = None
        margin = -abs(threshold - float(rows[0].v_out))

    margin_term = max(0.0, float(margin))
    correct_term = float(n_correct)
    penalty = 0.0
    if n_correct < n_total:
        penalty = 1.0 + (n_total - n_correct) * 2.0

    fitness = correct_term + margin_term - penalty

    all_correct = n_correct == n_total
    margin_satisfied = bool(
        lows
        and highs
        and max_low < threshold - min_margin
        and min_high > threshold + min_margin
    )
    success = bool(all_correct and margin_satisfied)

    return FitnessBreakdown(
        n_correct=n_correct,
        n_total=n_total,
        margin=float(margin),
        min_high=min_high,
        max_low=max_low,
        fitness=float(fitness),
        all_correct=all_correct,
        margin_satisfied=bool(margin_satisfied),
        success=success,
    )


__all__ = [
    "TruthTableRow",
    "TruthTable",
    "FitnessBreakdown",
    "evaluate_candidate",
    "fitness_from_truth_table",
]
