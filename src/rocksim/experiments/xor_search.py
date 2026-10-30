"""XOR experiment driver."""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import time
from datetime import datetime, timezone

from rocksim.config import (
    __version__ as ROCKSIM_VERSION,
)
from rocksim.config import (
    DEFAULT_ELECTRODE_COUNT,
    DEFAULT_HIDDEN_NODES,
    DEFAULT_MIN_MARGIN,
    DEFAULT_XOR_ITERATIONS,
    DEFAULT_XOR_OUTPUT_THRESHOLD,
    BIAS_LIMIT_ABS,
    STATUS_SEARCH_SUCCESS,
)
from rocksim.harvest.xor import (
    XorRunConfig,
    run_xor_search,
)
from rocksim.harvest.search import SearchProblem
from rocksim.interface import build_blackbox
from rocksim.material.graph import (
    Material,
    MaterialBuildParams,
    build_material,
)
from rocksim.physics.solver import build_solver


def _git_commit_hash() -> str | None:
    try:
        h = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return h or None
    except Exception:
        return None


def _environment() -> dict:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
    }


def run_xor_experiment(
    seed: int,
    material_model: str = "nonlinear",
    iterations: int = DEFAULT_XOR_ITERATIONS,
    strategy: str = "hill_climb",
    n_hidden_nodes: int = DEFAULT_HIDDEN_NODES,
    electrode_count: int = DEFAULT_ELECTRODE_COUNT,
    output_threshold: float = DEFAULT_XOR_OUTPUT_THRESHOLD,
    min_margin: float = DEFAULT_MIN_MARGIN,
    bias_limit: float = BIAS_LIMIT_ABS,
    damage_fraction: float = 0.0,
    damage_seed: int | None = None,
) -> dict:
    """End-to-end XOR experiment. JSON-ready dict, no hidden topology."""
    if material_model not in {"linear", "nonlinear"}:
        raise ValueError("material_model must be 'linear' or 'nonlinear'")

    build_params = MaterialBuildParams(
        master_seed=seed,
        n_hidden_nodes=n_hidden_nodes,
        electrode_count=electrode_count,
        model_name=material_model,
    )
    material: Material = build_material(build_params)

    n_damage = 0
    if damage_fraction > 0.0:
        from rocksim.material.defects import damage_material
        d_seed = damage_seed if damage_seed is not None else seed + 999
        n_damage = damage_material(material, damage_fraction, d_seed)

    solver = build_solver(material)
    material_iface = build_blackbox(material, solver)

    cfg = XorRunConfig(
        iterations=int(iterations),
        strategy=strategy,
        bias_limit=float(bias_limit),
        output_threshold=float(output_threshold),
        min_margin=float(min_margin),
        search_seed=int(seed),
    )
    started_at = time.time()
    result = run_xor_search(material_iface, cfg)
    wallclock = time.time() - started_at

    record = {
        "timestamp_utc": datetime.now(tz=timezone.utc).isoformat(),
        "rocksim_version": ROCKSIM_VERSION,
        "git_commit_hash": _git_commit_hash(),
        "environment": _environment(),
        "master_seed": int(seed),
        "material_seed": int(seed),
        "search_seed": int(seed),
        "material_model": material_model,
        "material_params": build_params.as_params_dict(),
        "electrode_count": electrode_count,
        "hidden_node_count": n_hidden_nodes,
        "signal_levels": {
            "low": cfg.signal_levels.low,
            "high": cfg.signal_levels.high,
        },
        "bias_limit": float(bias_limit),
        "output_threshold": float(output_threshold),
        "min_margin": float(min_margin),
        "iterations": int(iterations),
        "search": strategy,
        "search_runtime_seconds": float(wallclock),
        "material_summary": {
            "n_hidden_nodes": n_hidden_nodes,
            "n_hidden_edges": len(material.edges),
            "n_electrodes": electrode_count,
            "model_name": material_model,
            "edge_conductance_stats": _edge_stats(material),
            "n_damaged_edges": int(n_damage),
            "damage_fraction": float(damage_fraction),
            "damage_seed": (
                int(damage_seed)
                if damage_seed is not None
                else int(seed) + 999
            ),
        },
        "result": {
            "iterations": result.iterations,
            "best_fitness": result.best_fitness,
            "best_accuracy": result.best_accuracy,
            "best_margin": result.best_margin,
            "best_outputs": result.best_outputs,
            "status": result.status,
            "success": result.success,
            "search_counters": {
                "n_solver_failures": result.n_solver_failures,
                "n_illegal_candidates": result.n_illegal_candidates,
                "n_valid_evaluated": result.n_valid_evaluated,
            },
            "best_candidate": result.best_candidate.to_dict(),
            "best_truth_table": (
                result.best_truth_table.as_list()
                if result.best_truth_table is not None
                else []
            ),
            "best_breakdown": (
                result.best_breakdown.as_dict()
                if result.best_breakdown is not None
                else None
            ),
            "history": result.history,
        },
        "evidence_level": 2,
        "evidence_note": (
            "LEVEL 2 result (numerical simulation of a physical "
            "network). This is NOT evidence that real rock computes."
        ),
    }
    return record


def _edge_stats(material: Material) -> dict:
    gs = []
    for _, _, element in material.edges:
        gs.append(float(element.conductance(0.0)))
    if not gs:
        return {
            "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "n": 0,
        }
    arr = sorted(gs)
    n = len(arr)

    def pct(q: float) -> float:
        i = max(0, min(n - 1, int(round(q * (n - 1)))))
        return arr[i]

    return {
        "min": arr[0],
        "max": arr[-1],
        "mean": sum(arr) / n,
        "median": pct(0.5),
        "n": n,
    }


def save_xor_record(record: dict, output_dir: str) -> dict:
    """Write the record (and sub-files) to disk; return the same record
    annotated with file paths.
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    paths: dict[str, str] = {}
    for key in (
        "config.json", "material_summary.json", "best_candidate.json",
        "truth_table.json", "search_history.csv",
    ):
        paths[key] = os.path.join(output_dir, key)
    with open(paths["config.json"], "w", encoding="utf-8") as fh:
        json.dump(
            {
                "timestamp_utc": record["timestamp_utc"],
                "rocksim_version": record["rocksim_version"],
                "git_commit_hash": record["git_commit_hash"],
                "environment": record["environment"],
                "master_seed": record["master_seed"],
                "material_seed": record["material_seed"],
                "search_seed": record["search_seed"],
                "material_model": record["material_model"],
                "material_params": record["material_params"],
                "electrode_count": record["electrode_count"],
                "hidden_node_count": record["hidden_node_count"],
                "signal_levels": record["signal_levels"],
                "bias_limit": record["bias_limit"],
                "output_threshold": record["output_threshold"],
                "min_margin": record["min_margin"],
                "iterations": record["iterations"],
                "search": record["search"],
                "evidence_level": record["evidence_level"],
                "evidence_note": record["evidence_note"],
                "search_runtime_seconds": record["search_runtime_seconds"],
            },
            fh,
            indent=2,
        )
    with open(paths["material_summary.json"], "w", encoding="utf-8") as fh:
        json.dump(record["material_summary"], fh, indent=2)
    with open(paths["best_candidate.json"], "w", encoding="utf-8") as fh:
        json.dump(
            {
                "candidate": record["result"]["best_candidate"],
                "breakdown": record["result"]["best_breakdown"],
            },
            fh,
            indent=2,
        )
    with open(paths["truth_table.json"], "w", encoding="utf-8") as fh:
        json.dump(record["result"]["best_truth_table"], fh, indent=2)
    with open(paths["search_history.csv"], "w", encoding="utf-8") as fh:
        fh.write(
            "iteration,best_fitness,best_accuracy,best_margin,"
            "best_output_00,best_output_01,best_output_10,best_output_11\n"
        )
        for row in record["result"]["history"]:
            fh.write(
                f"{int(row['iteration'])},"
                f"{float(row.get('best_fitness', 0.0)):.6f},"
                f"{int(row.get('best_accuracy', 0))},"
                f"{float(row.get('best_margin', 0.0)):.6f},"
                f"{float(row.get('best_output_00', 0.0)):.6f},"
                f"{float(row.get('best_output_01', 0.0)):.6f},"
                f"{float(row.get('best_output_10', 0.0)):.6f},"
                f"{float(row.get('best_output_11', 0.0)):.6f}\n"
            )
    record["_paths"] = paths
    record["_output_dir"] = output_dir
    return record


__all__ = [
    "run_xor_experiment",
    "save_xor_record",
    "run_budget_ladder",
    "run_seed_sweep",
    "run_compare_models",
]


def np_random_state_for_search(seed: int):
    """Return a fresh numpy Generator seeded with `seed`.

    Used by the budget ladder to support deterministic continuation.
    """
    import numpy as np
    return np.random.default_rng(int(seed))


def run_search_with_state(
    strategy: str,
    problem,
    max_iterations: int,
    rng_state,
):
    """Run the given strategy using a pre-existing numpy Generator."""
    from rocksim.harvest.search import (
        SearchBudget,
        STRATEGY_REGISTRY,
    )
    strat = STRATEGY_REGISTRY[strategy]
    # The strategies accept a *seed* int and create a Generator
    # internally. We approximate deterministic continuation by
    # forward-seeding: pass the existing state as the seed via
    # bit-derivation. In practice this is good enough for the
    # "same material, larger budget" study because the material
    # is the same; the RNG state only affects the candidate
    # sequence, not the search result quality (which is what we
    # care about).
    derived_seed = int(rng_state.integers(0, 2**31 - 1))
    return strat(problem, SearchBudget(int(max_iterations)), derived_seed)


def _ladder_row(budget: int, result, wallclock: float) -> dict:
    return {
        "budget": int(budget),
        "status": result.status,
        "success": bool(result.success),
        "best_fitness": float(result.best_fitness),
        "accuracy": int(result.best_accuracy),
        "margin": float(result.best_margin),
        "best_outputs": dict(result.best_outputs),
        "n_solver_failures": int(result.n_solver_failures),
        "n_illegal_candidates": int(result.n_illegal_candidates),
        "n_valid_evaluated": int(result.n_valid_evaluated),
        "runtime_seconds": float(wallclock),
    }


def run_budget_ladder(
    seed: int,
    material_model: str = "nonlinear",
    budgets: tuple[int, ...] = (5_000, 10_000, 25_000, 50_000),
    n_hidden_nodes: int = DEFAULT_HIDDEN_NODES,
    electrode_count: int = DEFAULT_ELECTRODE_COUNT,
    output_threshold: float = DEFAULT_XOR_OUTPUT_THRESHOLD,
    min_margin: float = DEFAULT_MIN_MARGIN,
    bias_limit: float = BIAS_LIMIT_ABS,
    output_dir: str | None = None,
) -> dict:
    """Run the SAME material across an increasing iteration budget.

    The material is generated ONCE and reused. The search RNG is
    reseeded for each row from the same master seed so the comparison
    is interpretable. Returns a JSON-ready dict with one row per
    budget and writes ladder.json + ladder.csv.
    """
    if material_model not in {"linear", "nonlinear"}:
        raise ValueError("material_model must be 'linear' or 'nonlinear'")

    build_params = MaterialBuildParams(
        master_seed=seed,
        n_hidden_nodes=n_hidden_nodes,
        electrode_count=electrode_count,
        model_name=material_model,
    )
    material = build_material(build_params)
    solver = build_solver(material)
    iface = build_blackbox(material, solver)

    ladder: list[dict] = []
    for budget in budgets:
        problem = SearchProblem(
            material_iface=iface,
            electrode_count=electrode_count,
            bias_limit=bias_limit,
            output_threshold=output_threshold,
            min_margin=min_margin,
        )
        started = time.time()
        result = run_search_with_state(
            strategy="hill_climb",
            problem=problem,
            max_iterations=int(budget),
            rng_state=np_random_state_for_search(seed),
        )
        wallclock = time.time() - started
        ladder.append(_ladder_row(budget, result, wallclock))

    out_dir = output_dir or (
        f"results/budget_ladder/{material_model}_seed{seed}_n{n_hidden_nodes}"
    )
    os.makedirs(out_dir, exist_ok=True)
    record = {
        "experiment": "xor_budget_ladder",
        "seed": int(seed),
        "material_model": material_model,
        "n_hidden_nodes": n_hidden_nodes,
        "electrode_count": electrode_count,
        "evidence_level": 2,
        "evidence_note": (
            "LEVEL 2 result. The material is reused across budgets; "
            "no material is regenerated between rows."
        ),
        "rows": ladder,
    }
    with open(
        os.path.join(out_dir, "ladder.json"), "w", encoding="utf-8",
    ) as fh:
        json.dump(record, fh, indent=2)
    with open(
        os.path.join(out_dir, "ladder.csv"), "w", encoding="utf-8",
    ) as fh:
        fh.write(
            "budget,status,success,best_fitness,accuracy,margin,runtime_s\n"
        )
        for row in ladder:
            fh.write(
                f"{int(row['budget'])},{row['status']},"
                f"{int(row['success'])},"
                f"{float(row['best_fitness']):.6f},"
                f"{int(row['accuracy'])},"
                f"{float(row['margin']):.6f},"
                f"{float(row['runtime_seconds']):.3f}\n"
            )
    record["_output_dir"] = out_dir
    return record


def run_seed_sweep(
    seeds: list[int],
    material_model: str = "nonlinear",
    iterations: int = DEFAULT_XOR_ITERATIONS,
    n_hidden_nodes: int = DEFAULT_HIDDEN_NODES,
    electrode_count: int = DEFAULT_ELECTRODE_COUNT,
    output_threshold: float = DEFAULT_XOR_OUTPUT_THRESHOLD,
    min_margin: float = DEFAULT_MIN_MARGIN,
    bias_limit: float = BIAS_LIMIT_ABS,
    output_dir: str | None = None,
) -> dict:
    """Run the XOR search on each seed in `seeds` and aggregate.

    The aggregator reports the "fraction of simulated material
    realisations where the current search discovered XOR". It is
    NOT a yield, NOT a probability that real material computes.
    """
    rows: list[dict] = []
    n_success = 0
    n_total = 0
    n_solver_failed = 0
    total_runtime = 0.0
    for s in seeds:
        record = run_xor_experiment(
            seed=int(s),
            material_model=material_model,
            iterations=int(iterations),
            n_hidden_nodes=int(n_hidden_nodes),
            electrode_count=int(electrode_count),
            output_threshold=output_threshold,
            min_margin=min_margin,
            bias_limit=bias_limit,
        )
        r = record["result"]
        rows.append(
            {
                "seed": int(s),
                "status": r["status"],
                "success": bool(r["success"]),
                "best_fitness": float(r["best_fitness"]),
                "accuracy": int(r["best_accuracy"]),
                "margin": float(r["best_margin"]),
                "best_outputs": r.get("best_outputs", {}),
                "n_solver_failures": r["search_counters"][
                    "n_solver_failures"
                ],
                "runtime_seconds": float(
                    record["search_runtime_seconds"]
                ),
            }
        )
        n_total += 1
        total_runtime += rows[-1]["runtime_seconds"]
        if r["status"] == "SOLVER_FAILED":
            n_solver_failed += 1
        if r["success"]:
            n_success += 1

    summary = {
        "experiment": "xor_seed_sweep",
        "material_model": material_model,
        "iterations": int(iterations),
        "n_hidden_nodes": int(n_hidden_nodes),
        "electrode_count": int(electrode_count),
        "n_seeds_tested": int(n_total),
        "n_xor_found": int(n_success),
        "n_xor_not_found": int(n_total - n_success),
        "n_solver_failed": int(n_solver_failed),
        "fraction_simulated_realisations_xor_found": (
            float(n_success) / float(n_total) if n_total > 0 else 0.0
        ),
        "total_runtime_seconds": float(total_runtime),
        "evidence_level": 2,
        "evidence_note": (
            "LEVEL 2 result. This fraction is a property of the "
            "simulated material realisations under the current "
            "search methodology. It is NOT evidence that any "
            "natural material computes."
        ),
        "rows": rows,
    }

    if output_dir is not None:
        os.makedirs(output_dir, exist_ok=True)
        with open(
            os.path.join(output_dir, "summary.json"), "w", encoding="utf-8",
        ) as fh:
            json.dump(summary, fh, indent=2)
        with open(
            os.path.join(output_dir, "rows.csv"), "w", encoding="utf-8",
        ) as fh:
            fh.write(
                "seed,status,success,best_fitness,accuracy,margin,runtime_s\n"
            )
            for row in rows:
                fh.write(
                    f"{int(row['seed'])},{row['status']},"
                    f"{int(row['success'])},"
                    f"{float(row['best_fitness']):.6f},"
                    f"{int(row['accuracy'])},"
                    f"{float(row['margin']):.6f},"
                    f"{float(row['runtime_seconds']):.3f}\n"
                )
        summary["_output_dir"] = output_dir
    return summary


# ----------------------------------------------------------------------
# Linear vs nonlinear comparison
# ----------------------------------------------------------------------


def run_compare_models(
    seed: int,
    iterations: int = 10_000,
    n_hidden_nodes: int = DEFAULT_HIDDEN_NODES,
    electrode_count: int = DEFAULT_ELECTRODE_COUNT,
    output_threshold: float = DEFAULT_XOR_OUTPUT_THRESHOLD,
    min_margin: float = DEFAULT_MIN_MARGIN,
    bias_limit: float = BIAS_LIMIT_ABS,
    output_dir: str | None = None,
) -> dict:
    """Run the SAME geometry seed under both linear and nonlinear models.

    Geometry is the same; the only difference is the edge response
    model. This isolates the contribution of the nonlinear edge
    response, *not* the contribution of any physical material.
    """
    linear_record = run_xor_experiment(
        seed=seed,
        material_model="linear",
        iterations=iterations,
        n_hidden_nodes=n_hidden_nodes,
        electrode_count=electrode_count,
        output_threshold=output_threshold,
        min_margin=min_margin,
        bias_limit=bias_limit,
    )
    nonlinear_record = run_xor_experiment(
        seed=seed,
        material_model="nonlinear",
        iterations=iterations,
        n_hidden_nodes=n_hidden_nodes,
        electrode_count=electrode_count,
        output_threshold=output_threshold,
        min_margin=min_margin,
        bias_limit=bias_limit,
    )

    def _row(record: dict) -> dict:
        r = record["result"]
        return {
            "status": r["status"],
            "success": bool(r["success"]),
            "best_fitness": float(r["best_fitness"]),
            "accuracy": int(r["best_accuracy"]),
            "margin": float(r["best_margin"]),
            "best_outputs": r.get("best_outputs", {}),
            "best_candidate": r["best_candidate"],
            "runtime_seconds": float(record["search_runtime_seconds"]),
        }

    out = {
        "experiment": "compare_models",
        "seed": int(seed),
        "n_hidden_nodes": int(n_hidden_nodes),
        "electrode_count": int(electrode_count),
        "iterations": int(iterations),
        "linear": _row(linear_record),
        "nonlinear": _row(nonlinear_record),
        "evidence_level": 2,
        "evidence_note": (
            "LEVEL 2 result. The geometry is shared across both "
            "models; only the edge response model changes. This is "
            "not a claim about any natural material."
        ),
    }

    if output_dir is not None:
        os.makedirs(output_dir, exist_ok=True)
        with open(
            os.path.join(output_dir, "compare.json"), "w", encoding="utf-8",
        ) as fh:
            json.dump(out, fh, indent=2)
        out["_output_dir"] = output_dir
    return out
