"""The harvester's candidate representation.

A `Candidate` selects:

- which surface electrode receives input A
- which surface electrode receives input B
- which surface electrode is the output
- a dict of {electrode_id: bias_voltage} for any other electrodes
- the output analog threshold for classifying the output bit

Legality rules (see `validate_candidate`):

- input_a, input_b, output are distinct integers in
  [0, electrode_count).
- biases.keys() does not contain input_a, input_b, or output.
- each bias voltage is in [-bias_limit, +bias_limit].
- output_threshold is in [LOW, HIGH].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


class CandidateError(ValueError):
    """An illegal candidate was supplied."""


@dataclass
class Candidate:
    """A candidate electrode configuration.

    Immutable; mutators return new instances.
    """

    input_a: int
    input_b: int
    output: int
    biases: dict[int, float] = field(default_factory=dict)
    output_threshold: float = 0.5

    def with_bias(self, electrode_id: int, voltage: float) -> "Candidate":
        new_biases = dict(self.biases)
        new_biases[int(electrode_id)] = float(voltage)
        return Candidate(
            input_a=self.input_a,
            input_b=self.input_b,
            output=self.output,
            biases=new_biases,
            output_threshold=self.output_threshold,
        )

    def with_threshold(self, threshold: float) -> "Candidate":
        return Candidate(
            input_a=self.input_a,
            input_b=self.input_b,
            output=self.output,
            biases=dict(self.biases),
            output_threshold=float(threshold),
        )

    def with_inputs(
        self, input_a: int, input_b: int, output: int,
    ) -> "Candidate":
        return Candidate(
            input_a=int(input_a),
            input_b=int(input_b),
            output=int(output),
            biases=dict(self.biases),
            output_threshold=self.output_threshold,
        )

    def to_dict(self) -> dict:
        return {
            "input_a": int(self.input_a),
            "input_b": int(self.input_b),
            "output": int(self.output),
            "biases": {str(k): float(v) for k, v in self.biases.items()},
            "output_threshold": float(self.output_threshold),
        }


def validate_candidate(
    candidate: Candidate,
    electrode_count: int,
    bias_limit: float,
    low: float,
    high: float,
) -> None:
    """Raise `CandidateError` if the candidate is illegal."""
    if electrode_count <= 0:
        raise CandidateError("electrode_count must be positive")
    for name in ("input_a", "input_b", "output"):
        value = getattr(candidate, name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise CandidateError(f"{name} must be an int electrode id")
        if not (0 <= value < electrode_count):
            raise CandidateError(
                f"{name}={value} out of range [0, {electrode_count})"
            )
    if len({candidate.input_a, candidate.input_b, candidate.output}) != 3:
        raise CandidateError(
            "input_a, input_b and output must be distinct electrode ids"
        )
    for eid in candidate.biases:
        if not isinstance(eid, int) or isinstance(eid, bool):
            raise CandidateError(f"bias electrode id {eid!r} must be an int")
        if not (0 <= eid < electrode_count):
            raise CandidateError(
                f"bias electrode {eid} out of range [0, {electrode_count})"
            )
        if eid in (candidate.input_a, candidate.input_b, candidate.output):
            raise CandidateError(
                f"bias electrode {eid} must not equal A/B/OUT"
            )
        v = float(candidate.biases[eid])
        if abs(v) > float(bias_limit) + 1e-12:
            raise CandidateError(
                f"bias at electrode {eid}={v} exceeds |bias_limit|={bias_limit}"
            )
    thr = float(candidate.output_threshold)
    if not (min(low, high) - 1e-12 <= thr <= max(low, high) + 1e-12):
        raise CandidateError(
            f"output_threshold {thr} outside [{low}, {high}]"
        )


def controlled_electrode_ids(
    candidate: Candidate,
    electrode_count: int,
) -> list[int]:
    """Return all electrode ids the candidate influences, sorted."""
    all_ids = {candidate.input_a, candidate.input_b, candidate.output}
    all_ids.update(int(k) for k in candidate.biases.keys())
    return sorted(all_ids)


def assert_no_unexpected_overlap(
    candidate: Candidate,
    electrode_count: int,
) -> None:
    """Sanity check for distinct electrodes; called after validation."""
    s = {
        candidate.input_a,
        candidate.input_b,
        candidate.output,
    }
    if len(s) != 3:
        raise CandidateError(
            f"overlap detected among A/B/OUT: {sorted(s)}"
        )
    for k in range(electrode_count):
        _ = k  # range check already done in validation
