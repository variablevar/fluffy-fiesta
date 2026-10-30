"""Run a full XOR experiment on a black-box material interface.

The harvester is given a `MaterialInterface`. The internal material and
solver remain private. This module:

- constructs the search problem,
- runs the search strategy,
- returns a structured record ready to be serialised by the
  experiment drivers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from rocksim.config import (
    BIAS_LIMIT_ABS,
    DEFAULT_MIN_MARGIN,
    DEFAULT_XOR_ITERATIONS,
    DEFAULT_XOR_OUTPUT_THRESHOLD,
    SignalLevels,
)
from rocksim.harvest.search import (
    SearchBudget,
    SearchProblem,
    SearchResult,
    STRATEGY_REGISTRY,
)
from rocksim.interface import MaterialInterface


@dataclass
class XorRunConfig:
    iterations: int = DEFAULT_XOR_ITERATIONS
    strategy: str = "hill_climb"
    bias_limit: float = BIAS_LIMIT_ABS
    output_threshold: float = DEFAULT_XOR_OUTPUT_THRESHOLD
    min_margin: float = DEFAULT_MIN_MARGIN
    signal_levels: SignalLevels = field(default_factory=SignalLevels)
    search_seed: int = 0
    extra_metadata: dict = field(default_factory=dict)


def run_xor_search(
    material_iface: MaterialInterface,
    config: XorRunConfig,
) -> SearchResult:
    """Run an XOR black-box search against `material_iface`."""
    if config.strategy not in STRATEGY_REGISTRY:
        raise ValueError(
            f"unknown strategy {config.strategy!r}; "
            f"available: {sorted(STRATEGY_REGISTRY)}"
        )
    problem = SearchProblem(
        material_iface=material_iface,
        electrode_count=material_iface.electrode_count,
        bias_limit=config.bias_limit,
        signal_levels=config.signal_levels,
        output_threshold=config.output_threshold,
        min_margin=config.min_margin,
    )
    budget = SearchBudget(max_iterations=int(config.iterations))
    strategy = STRATEGY_REGISTRY[config.strategy]
    return strategy(problem, budget, int(config.search_seed))


def serialise_search_result(
    result: SearchResult,
) -> dict:
    """Serialise a `SearchResult` to a JSON-friendly dict.

    Returns a dict shaped for the experiment record writer.
    """
    return {
        "iterations": int(result.iterations),
        "best_fitness": float(result.best_fitness),
        "success": bool(result.success),
        "best_candidate": result.best_candidate.to_dict(),
        "best_truth_table": (
            result.best_truth_table.as_list()
            if result.best_truth_table is not None
            else None
        ),
        "best_breakdown": (
            result.best_breakdown.as_dict()
            if result.best_breakdown is not None
            else None
        ),
    }


__all__ = [
    "XorRunConfig",
    "run_xor_search",
    "serialise_search_result",
]
