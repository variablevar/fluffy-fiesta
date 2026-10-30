"""High-level experiment drivers. World B-side; never reach into material."""

from rocksim.experiments.xor_search import (
    run_budget_ladder,
    run_compare_models,
    run_seed_sweep,
    run_xor_experiment,
    save_xor_record,
)
from rocksim.experiments.damage_recovery import (
    run_damage_recovery,
    run_damage_sweep,
)
from rocksim.experiments.reproducibility import (
    build_experiment_record,
    check_record_identity,
    load_experiment_record,
    save_experiment_record,
)

__all__ = [
    "run_xor_experiment",
    "save_xor_record",
    "run_budget_ladder",
    "run_seed_sweep",
    "run_compare_models",
    "run_damage_recovery",
    "run_damage_sweep",
    "build_experiment_record",
    "save_experiment_record",
    "load_experiment_record",
    "check_record_identity",
]
