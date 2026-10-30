"""Damage / recovery experiment driver (5 phases).

PHASE A — DISCOVERY
PHASE B — BASELINE
PHASE C — DAMAGE (hidden)
PHASE D — OLD CONFIGURATION TEST
PHASE E — RECOVERY

Categories: SEARCH_SUCCESS, SEARCH_EXHAUSTED, SOLVER_FAILED,
DISCOVERY_FAILED, SURVIVED_DAMAGE, BROKEN_BY_DAMAGE, RECOVERED,
RECOVERY_FAILED.
"""

from __future__ import annotations

import json
import os
from typing import Mapping

from rocksim.config import (
    BIAS_LIMIT_ABS,
    DEFAULT_DAMAGE_FRACTION,
    DEFAULT_ELECTRODE_COUNT,
    DEFAULT_HIDDEN_NODES,
    DEFAULT_MIN_MARGIN,
    DEFAULT_XOR_ITERATIONS,
    DEFAULT_XOR_OUTPUT_THRESHOLD,
    STATUS_BROKEN_BY_DAMAGE,
    STATUS_DISCOVERY_FAILED,
    STATUS_RECOVERED,
    STATUS_RECOVERY_FAILED,
    STATUS_SEARCH_SUCCESS,
    STATUS_SURVIVED_DAMAGE,
    SignalLevels,
)
from rocksim.export.blender_json import (
    export_researcher_ground_truth,
    write_blender_json,
)
from rocksim.harvest.candidate import Candidate
from rocksim.harvest.fitness import (
    evaluate_candidate,
    fitness_from_truth_table,
)
from rocksim.interface import (
    MaterialInterface,
    build_blackbox,
)
from rocksim.material.defects import damage_material
from rocksim.material.graph import (
    Material,
    MaterialBuildParams,
    build_material,
)
from rocksim.physics.solver import build_solver


def _candidate_from_dict(d: Mapping) -> Candidate:
    """Reconstruct a Candidate dataclass from a saved dict."""
    biases = {
        int(k): float(v) for k, v in (d.get("biases") or {}).items()
    }
    return Candidate(
        input_a=int(d["input_a"]),
        input_b=int(d["input_b"]),
        output=int(d["output"]),
        biases=biases,
        output_threshold=float(d["output_threshold"]),
    )


def _evaluate_against(
    material_iface: MaterialInterface,
    cand: Candidate,
) -> tuple[dict, dict]:
    """Run a candidate through a black-box material; return analog outputs and a fitness dict."""
    tt = evaluate_candidate(
        material_iface=material_iface,
        candidate=cand,
        bias_limit=BIAS_LIMIT_ABS,
        signal_levels=SignalLevels(),
    )
    fb = fitness_from_truth_table(
        tt, cand.output_threshold, DEFAULT_MIN_MARGIN,
    )
    by_row = {(r.a_bit, r.b_bit): r.v_out for r in tt.rows}
    analog_out = {
        "00": by_row.get((0, 0), 0.0),
        "01": by_row.get((0, 1), 0.0),
        "10": by_row.get((1, 0), 0.0),
        "11": by_row.get((1, 1), 0.0),
    }
    return analog_out, fb.as_dict()


def _run_discovery(
    iface: MaterialInterface,
    iterations: int,
    strategy: str,
    seed: int,
) -> tuple[dict, Candidate, dict, bool]:
    """Run the XOR search and return (analog_outputs, cand, fitness_dict, success)."""
    from rocksim.harvest.search import (
        SearchBudget,
        SearchProblem,
        STRATEGY_REGISTRY,
    )
    problem = SearchProblem(
        material_iface=iface,
        electrode_count=iface.electrode_count,
        bias_limit=BIAS_LIMIT_ABS,
        output_threshold=DEFAULT_XOR_OUTPUT_THRESHOLD,
        min_margin=DEFAULT_MIN_MARGIN,
    )
    strat = STRATEGY_REGISTRY[strategy]
    result = strat(problem, SearchBudget(int(iterations)), int(seed))
    cand = result.best_candidate
    if result.best_truth_table is None:
        analog = {"00": 0.0, "01": 0.0, "10": 0.0, "11": 0.0}
    else:
        by_row = {(r.a_bit, r.b_bit): r.v_out for r in result.best_truth_table.rows}
        analog = {
            "00": by_row.get((0, 0), 0.0),
            "01": by_row.get((0, 1), 0.0),
            "10": by_row.get((1, 0), 0.0),
            "11": by_row.get((1, 1), 0.0),
        }
    return (
        analog, cand,
        result.best_breakdown.as_dict() if result.best_breakdown else {},
        bool(result.success),
    )


def _compare_candidates(
    old: Mapping, new: Mapping,
) -> dict:
    """Describe the differences between two candidates.

    Returns a dict whose boolean keys are the *kinds* of difference
    (input_a_changed, etc.) plus a side-by-side of both candidates.

    Note: even if no gene changed, the same external configuration
    on a different material realisation is NOT a recovery; this
    function only describes *candidate* differences. The summary
    distinguishes "no external difference" from "external difference
    discovered" through the per-row status of the new candidate.
    """
    return {
        "input_a_changed": int(old["input_a"]) != int(new["input_a"]),
        "input_b_changed": int(old["input_b"]) != int(new["input_b"]),
        "output_changed": int(old["output"]) != int(new["output"]),
        "bias_electrodes_changed": (
            set(int(k) for k in (old.get("biases") or {}).keys())
            != set(int(k) for k in (new.get("biases") or {}).keys())
        ),
        "bias_values_changed": (
            {
                int(k): float(v)
                for k, v in (old.get("biases") or {}).items()
            }
            != {
                int(k): float(v)
                for k, v in (new.get("biases") or {}).items()
            }
        ),
        "old_candidate": dict(old),
        "new_candidate": dict(new),
    }


def run_damage_recovery(
    seed: int,
    damage_fraction: float = DEFAULT_DAMAGE_FRACTION,
    damage_seed: int | None = None,
    iterations: int = DEFAULT_XOR_ITERATIONS,
    strategy: str = "hill_climb",
    n_hidden_nodes: int = DEFAULT_HIDDEN_NODES,
    electrode_count: int = DEFAULT_ELECTRODE_COUNT,
    output_dir: str | None = None,
    blender_export_path: str | None = None,
) -> dict:
    """Run the full damage/recovery experiment, returning a JSON-ready dict."""
    base_dir = output_dir or (
        f"results/damage_recovery/dmg_{damage_fraction:.3f}/seed_{seed}"
    )
    os.makedirs(base_dir, exist_ok=True)
    d_seed = int(damage_seed) if damage_seed is not None else int(seed) + 7919

    build_params = MaterialBuildParams(
        master_seed=int(seed),
        n_hidden_nodes=n_hidden_nodes,
        electrode_count=electrode_count,
        model_name="nonlinear",
    )

    # ---- PHASE A: DISCOVERY (on a fresh pristine material). ---------
    pristine_material: Material = build_material(build_params)
    pristine_solver = build_solver(pristine_material)
    pristine_iface = build_blackbox(pristine_material, pristine_solver)
    (
        analog_pristine, cand_pristine, fb_pristine, success_pristine,
    ) = _run_discovery(
        pristine_iface,
        iterations=int(iterations),
        strategy=strategy,
        seed=int(seed),
    )
    if not success_pristine:
        summary = {
            "experiment": "damage_recovery",
            "status": STATUS_DISCOVERY_FAILED,
            "seed": int(seed),
            "damage_fraction": float(damage_fraction),
            "n_hidden_nodes": int(n_hidden_nodes),
            "electrode_count": int(electrode_count),
            "iterations": int(iterations),
            "base_dir": base_dir,
            "evidence_level": 2,
            "evidence_note": (
                "LEVEL 2. Discovery failed within budget; trial stops."
            ),
            "pristine_best_fitness": float(
                fb_pristine.get("fitness", 0.0)
            ),
            "pristine_accuracy": int(fb_pristine.get("n_correct", 0)),
            "n_damaged_edges": 0,
        }
        with open(
            os.path.join(base_dir, "summary.json"), "w", encoding="utf-8",
        ) as fh:
            json.dump(summary, fh, indent=2)
        return summary

    cand_pristine_dict = {
        "input_a": cand_pristine.input_a,
        "input_b": cand_pristine.input_b,
        "output": cand_pristine.output,
        "biases": {
            str(int(k)): float(v)
            for k, v in cand_pristine.biases.items()
        },
        "output_threshold": float(cand_pristine.output_threshold),
    }
    analog_baseline = analog_pristine

    # ---- PHASE B: BASELINE. -----------------------------------------
    baseline_record = {
        "candidate": cand_pristine_dict,
        "analog_outputs": analog_baseline,
        "fitness": fb_pristine,
    }
    with open(
        os.path.join(base_dir, "phase_B_baseline.json"),
        "w", encoding="utf-8",
    ) as fh:
        json.dump(baseline_record, fh, indent=2)

    # ---- PHASE C: DAMAGE (hidden). ----------------------------------
    damaged_material: Material = build_material(build_params)
    n_damaged = damage_material(
        damaged_material, float(damage_fraction), int(d_seed),
    )
    damaged_edges: set[tuple[int, int]] = set()
    for (u, v, e) in damaged_material.edges:
        if float(e.conductance(0.0)) == 0.0:
            key = (int(u), int(v)) if u < v else (int(v), int(u))
            damaged_edges.add(key)
    damaged_solver = build_solver(damaged_material)
    damaged_iface = build_blackbox(damaged_material, damaged_solver)

    # ---- PHASE D: OLD CONFIG on damaged material. ------------------
    cand_for_eval = _candidate_from_dict(cand_pristine_dict)
    analog_old_on_damaged, fb_old_on_damaged = _evaluate_against(
        damaged_iface, cand_for_eval,
    )
    survived = bool(fb_old_on_damaged.get("success", False))
    if survived:
        phase_d_status = STATUS_SURVIVED_DAMAGE
    else:
        phase_d_status = STATUS_BROKEN_BY_DAMAGE
    phase_d_record = {
        "status": phase_d_status,
        "candidate": cand_pristine_dict,
        "analog_outputs": analog_old_on_damaged,
        "fitness": fb_old_on_damaged,
        "baseline_analog_outputs": analog_baseline,
    }
    with open(
        os.path.join(base_dir, "phase_D_old_on_damaged.json"),
        "w", encoding="utf-8",
    ) as fh:
        json.dump(phase_d_record, fh, indent=2)

    # ---- PHASE E: RECOVERY (if broken). ----------------------------
    if not survived:
        (
            analog_recovered, cand_recovered,
            fb_recovered, success_recovered,
        ) = _run_discovery(
            damaged_iface,
            iterations=int(iterations),
            strategy=strategy,
            seed=int(seed) + 1,
        )
        if success_recovered:
            cand_recovered_dict = {
                "input_a": cand_recovered.input_a,
                "input_b": cand_recovered.input_b,
                "output": cand_recovered.output,
                "biases": {
                    str(int(k)): float(v)
                    for k, v in cand_recovered.biases.items()
                },
                "output_threshold": float(cand_recovered.output_threshold),
            }
            phase_e_status = STATUS_RECOVERED
            phase_e_record = {
                "status": phase_e_status,
                "candidate": cand_recovered_dict,
                "analog_outputs": analog_recovered,
                "fitness": fb_recovered,
            }
            comparison = _compare_candidates(
                cand_pristine_dict, cand_recovered_dict,
            )
        else:
            phase_e_status = STATUS_RECOVERY_FAILED
            phase_e_record = {
                "status": phase_e_status,
                "best_fitness": float(fb_recovered.get("fitness", 0.0)),
                "accuracy": int(fb_recovered.get("n_correct", 0)),
            }
            cand_recovered_dict = None
            comparison = None
    else:
        phase_e_status = STATUS_SURVIVED_DAMAGE
        phase_e_record = {
            "status": phase_e_status,
            "note": "Old candidate survived damage; recovery not attempted.",
        }
        cand_recovered_dict = None
        comparison = None

    with open(
        os.path.join(base_dir, "phase_E_recovery.json"),
        "w", encoding="utf-8",
    ) as fh:
        json.dump(phase_e_record, fh, indent=2)

    # ---- Researcher-only damage map. -------------------------------
    with open(
        os.path.join(base_dir, "researcher_damage_map.json"),
        "w", encoding="utf-8",
    ) as fh:
        json.dump(
            {
                "label": "RESEARCHER-ONLY damage map",
                "warning": (
                    "Hidden defect map. The harvester pipeline never "
                    "receives this file."
                ),
                "damage_seed": int(d_seed),
                "damage_fraction_requested": float(damage_fraction),
                "n_damaged_edges": int(n_damaged),
                "damaged_edges": [
                    list(e) for e in sorted(damaged_edges)
                ],
            },
            fh,
            indent=2,
        )

    # ---- Optional Blender export. ---------------------------------
    if blender_export_path is not None:
        try:
            recovered_mat = (
                damaged_material if cand_recovered_dict is not None
                else None
            )
            export = export_researcher_ground_truth(
                material=pristine_material,
                drive={0: 1.0, 1: 0.0},
                candidate=cand_pristine_dict,
                damaged_edges=damaged_edges,
                damaged_material=damaged_material,
                recovered_candidate=cand_recovered_dict,
                recovered_material=recovered_mat,
            )
            write_blender_json(export, blender_export_path)
        except Exception as exc:  # noqa: BLE001
            with open(
                os.path.join(base_dir, "blender_export_error.txt"),
                "w", encoding="utf-8",
            ) as fh:
                fh.write(f"{type(exc).__name__}: {exc}\n")

    # ---- Summary. --------------------------------------------------
    if phase_e_status == STATUS_RECOVERED:
        overall = STATUS_RECOVERED
    elif phase_d_status == STATUS_SURVIVED_DAMAGE:
        overall = STATUS_SURVIVED_DAMAGE
    elif phase_e_status == STATUS_RECOVERY_FAILED:
        overall = STATUS_RECOVERY_FAILED
    else:
        overall = STATUS_BROKEN_BY_DAMAGE

    summary = {
        "experiment": "damage_recovery",
        "status": overall,
        "seed": int(seed),
        "damage_fraction": float(damage_fraction),
        "damage_seed": int(d_seed),
        "n_damaged_edges": int(n_damaged),
        "n_hidden_nodes": int(n_hidden_nodes),
        "electrode_count": int(electrode_count),
        "iterations": int(iterations),
        "phases": {
            "A_discovery": {
                "status": STATUS_SEARCH_SUCCESS,
                "best_candidate": cand_pristine_dict,
                "fitness": fb_pristine,
                "analog_outputs": analog_baseline,
            },
            "B_baseline": {"analog_outputs": analog_baseline},
            "C_damage": {
                "n_damaged_edges": int(n_damaged),
                "damage_seed": int(d_seed),
            },
            "D_old_on_damaged": {
                "status": phase_d_status,
                "analog_outputs": analog_old_on_damaged,
                "fitness": fb_old_on_damaged,
            },
            "E_recovery": {
                "status": phase_e_status,
                "candidate": cand_recovered_dict,
                "comparison": comparison,
            },
        },
        "base_dir": base_dir,
        "evidence_level": 2,
        "evidence_note": (
            "LEVEL 2 result. Damage is a hidden internal edge cut; "
            "the harvester never observes the defect map. Recovery is "
            "a fresh black-box search that may have used the SAME "
            "electrodes or DIFFERENT electrodes than the original; "
            "this is a discovered externally configured material "
            "response, not a re-routing of an internal path."
        ),
    }
    with open(
        os.path.join(base_dir, "summary.json"), "w", encoding="utf-8",
    ) as fh:
        json.dump(summary, fh, indent=2)
    return summary


__all__ = ["run_damage_recovery"]



def run_damage_sweep(
    damage_fractions: tuple[float, ...] = (0.0, 0.01, 0.02, 0.05, 0.10, 0.20),
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
    iterations: int = DEFAULT_XOR_ITERATIONS,
    n_hidden_nodes: int = DEFAULT_HIDDEN_NODES,
    electrode_count: int = DEFAULT_ELECTRODE_COUNT,
    output_dir: str | None = None,
) -> dict:
    """Run the damage-recovery experiment for each (damage, seed) pair.

    Categories are NOT merged. Each trial lands in exactly one of:
    DISCOVERY_FAILED, SURVIVED_DAMAGE, BROKEN_BY_DAMAGE, RECOVERED,
    RECOVERY_FAILED.
    """
    rows: list[dict] = []
    counts: dict[str, int] = {
        STATUS_DISCOVERY_FAILED: 0,
        STATUS_SURVIVED_DAMAGE: 0,
        STATUS_BROKEN_BY_DAMAGE: 0,
        STATUS_RECOVERED: 0,
        STATUS_RECOVERY_FAILED: 0,
    }
    for s in seeds:
        for f in damage_fractions:
            sub = run_damage_recovery(
                seed=int(s),
                damage_fraction=float(f),
                iterations=int(iterations),
                n_hidden_nodes=int(n_hidden_nodes),
                electrode_count=int(electrode_count),
            )
            row = {
                "seed": int(s),
                "damage_fraction": float(f),
                "status": sub.get("status", "UNKNOWN"),
                "n_damaged_edges": int(sub.get("n_damaged_edges", 0)),
            }
            rows.append(row)
            status = row["status"]
            counts[status] = counts.get(status, 0) + 1

    summary = {
        "experiment": "damage_sweep",
        "iterations": int(iterations),
        "n_hidden_nodes": int(n_hidden_nodes),
        "electrode_count": int(electrode_count),
        "n_trials": int(len(rows)),
        "category_counts": counts,
        "rows": rows,
        "evidence_level": 2,
        "evidence_note": (
            "LEVEL 2. Each trial is a separate hidden material realisation."
        ),
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
            fh.write("seed,damage_fraction,status,n_damaged_edges\n")
            for r in rows:
                fh.write(
                    f"{int(r['seed'])},"
                    f"{float(r['damage_fraction']):.3f},"
                    f"{r['status']},"
                    f"{int(r['n_damaged_edges'])}\n"
                )
        summary["_output_dir"] = output_dir
    return summary


__all__ = ["run_damage_recovery", "run_damage_sweep"]
