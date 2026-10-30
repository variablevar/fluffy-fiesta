"""World B -- the harvester.

The harvester may import only from:

- `rocksim.config`
- `rocksim.interface`
- `rocksim.harvest`

It must NOT import from `rocksim.material` or `rocksim.physics`. This
is enforced by tests, not just by convention.
"""

from rocksim.harvest.candidate import Candidate, CandidateError, validate_candidate
from rocksim.harvest.fitness import (
    TruthTableRow,
    TruthTable,
    FitnessBreakdown,
    evaluate_candidate,
    fitness_from_truth_table,
)
from rocksim.harvest.search import (
    SearchStrategy,
    random_search,
    hill_climb,
    SearchResult,
)
from rocksim.harvest.xor import run_xor_search

__all__ = [
    "Candidate",
    "CandidateError",
    "validate_candidate",
    "TruthTableRow",
    "TruthTable",
    "FitnessBreakdown",
    "evaluate_candidate",
    "fitness_from_truth_table",
    "SearchStrategy",
    "random_search",
    "hill_climb",
    "SearchResult",
    "run_xor_search",
]
