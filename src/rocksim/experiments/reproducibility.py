"""Reproducibility helpers.

A saved experiment record is **reproducible** iff re-running the search
with the same seeds and the same model produces the same
`best_candidate.json` numbers within tolerance.
"""

from __future__ import annotations

import json
import os
from typing import Mapping

from rocksim.experiments.xor_search import run_xor_experiment


def build_experiment_record(
    seed: int,
    material_model: str = "nonlinear",
    iterations: int = 10_000,
    strategy: str = "hill_climb",
    n_hidden_nodes: int = 500,
    electrode_count: int = 32,
    output_threshold: float = 0.5,
    min_margin: float = 0.05,
    bias_limit: float = 1.0,
    damage_fraction: float = 0.0,
    damage_seed: int | None = None,
) -> dict:
    """Thin wrapper around the driver; one call -> full record."""
    return run_xor_experiment(
        seed=int(seed),
        material_model=material_model,
        iterations=int(iterations),
        strategy=strategy,
        n_hidden_nodes=int(n_hidden_nodes),
        electrode_count=int(electrode_count),
        output_threshold=output_threshold,
        min_margin=min_margin,
        bias_limit=bias_limit,
        damage_fraction=damage_fraction,
        damage_seed=damage_seed,
    )


def save_experiment_record(record: dict, output_dir: str) -> dict:
    """Persist the record using the canonical sub-file layout."""
    from rocksim.experiments.xor_search import save_xor_record
    return save_xor_record(record, output_dir)


def load_experiment_record(directory: str) -> dict:
    """Reload a record from the canonical sub-file layout."""
    with open(os.path.join(directory, "config.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    with open(
        os.path.join(directory, "material_summary.json"), encoding="utf-8",
    ) as fh:
        summary = json.load(fh)
    with open(
        os.path.join(directory, "best_candidate.json"), encoding="utf-8",
    ) as fh:
        cand = json.load(fh)
    with open(
        os.path.join(directory, "truth_table.json"), encoding="utf-8",
    ) as fh:
        truth = json.load(fh)
    history_path = os.path.join(directory, "search_history.csv")
    history = []
    if os.path.exists(history_path):
        with open(history_path, encoding="utf-8") as fh:
            lines = fh.readlines()
        for line in lines[1:]:
            parts = line.strip().split(",")
            if len(parts) == 5:
                history.append(
                    {
                        "iteration": int(parts[0]),
                        "fitness": float(parts[1]),
                        "n_correct": int(parts[2]),
                        "success": int(parts[3]),
                        "accepted": int(parts[4]),
                    }
                )
    return {
        "config": cfg,
        "material_summary": summary,
        "best_candidate": cand,
        "truth_table": truth,
        "history": history,
    }


def check_record_identity(
    saved_dir: str,
    seed: int,
    rel_tol: float = 1e-6,
) -> tuple[bool, str]:
    """Verify the saved record is reproducible from its config alone."""
    record = load_experiment_record(saved_dir)
    cfg = record["config"]
    regenerated = build_experiment_record(
        seed=seed,
        material_model=cfg["material_model"],
        iterations=cfg["iterations"],
        strategy=cfg["search"],
        n_hidden_nodes=cfg["hidden_node_count"],
        electrode_count=cfg["electrode_count"],
        output_threshold=cfg["output_threshold"],
        min_margin=cfg["min_margin"],
        bias_limit=cfg["bias_limit"],
    )
    saved_truth = record["truth_table"]
    regen_truth = regenerated["result"]["best_truth_table"]
    if len(saved_truth) != len(regen_truth):
        return False, f"row count mismatch: {len(saved_truth)} vs {len(regen_truth)}"
    for s, r in zip(saved_truth, regen_truth):
        if abs(float(s["v_out"]) - float(r["v_out"])) > rel_tol:
            return False, (
                f"v_out mismatch on row (a={s['a']}, b={s['b']}): "
                f"saved={s['v_out']} regen={r['v_out']}"
            )
    return True, "identical within tolerance"


__all__ = [
    "build_experiment_record",
    "save_experiment_record",
    "load_experiment_record",
    "check_record_identity",
]
