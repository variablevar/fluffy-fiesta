"""Command-line interface for RockSim.

Subcommands:
  generate         -- generate a material and dump a researcher file.
  inspect          -- print the harvester-visible surface for a material.
  xor-search       -- run the XOR black-box search.
  damage-recovery  -- run the damage / recovery experiment.
  export-blender   -- write researcher-only Blender JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from rocksim.config import (
    BIAS_LIMIT_ABS,
    DEFAULT_DAMAGE_FRACTION,
    DEFAULT_ELECTRODE_COUNT,
    DEFAULT_HIDDEN_NODES,
    DEFAULT_MIN_MARGIN,
    DEFAULT_SEARCH_STRATEGY,
    DEFAULT_XOR_ITERATIONS,
    DEFAULT_XOR_OUTPUT_THRESHOLD,
    HIGH_VOLTAGE,
    LOW_VOLTAGE,
    __version__ as ROCKSIM_VERSION,
)
from rocksim.export.blender_json import (
    export_researcher_ground_truth,
    write_blender_json,
)
from rocksim.experiments.damage_recovery import run_damage_recovery
from rocksim.experiments.xor_search import (
    run_budget_ladder,
    run_compare_models,
    run_seed_sweep,
    run_xor_experiment,
    save_xor_record,
)
from rocksim.interface import build_blackbox
from rocksim.material.geometry import GeometryParams
from rocksim.material.graph import (
    MaterialBuildParams,
    build_material,
)
from rocksim.physics.solver import build_solver


def _print_candidate_block(record: dict) -> None:
    r = record["result"]
    c = r["best_candidate"]
    print()
    print(
        f"Candidate #{r['iterations']}  "
        f"(status={r.get('status', '?')}, success={r['success']})"
    )
    print(f"  A electrode:   {c['input_a']}")
    print(f"  B electrode:   {c['input_b']}")
    print(f"  OUT electrode: {c['output']}")
    if c["biases"]:
        print("  Bias:")
        for k, v in c["biases"].items():
            print(f"    E{int(k):>3} = {float(v):+0.3f} V")
    print()
    print("  A B | Vout   | predicted | expected")
    print("  ------------------------------------")
    for row in r["best_truth_table"]:
        print(
            f"  {row['a']} {row['b']} | "
            f"{row['v_out']:0.3f} V |    "
            f"{row['predicted']}      |    {row['expected']}"
        )
    bd = r["best_breakdown"]
    print()
    print(f"  accuracy : {bd['n_correct']}/{bd['n_total']}")
    print(f"  margin   : {bd['margin']:0.4f} V")
    print(f"  fitness  : {bd['fitness']:0.4f}")
    sc = r.get("search_counters", {})
    print(
        f"  counters : valid={sc.get('n_valid_evaluated', '?')}, "
        f"illegal={sc.get('n_illegal_candidates', '?')}, "
        f"solver_failures={sc.get('n_solver_failures', '?')}"
    )
    print()


def cmd_generate(args: argparse.Namespace) -> int:
    build_params = MaterialBuildParams(
        master_seed=args.seed,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
        model_name=args.model,
        geometry=GeometryParams(seed=args.seed),
    )
    material = build_material(build_params)
    out_path = args.output or (
        f"results/generate/seed_{args.seed}_material.json"
    )
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    payload = {
        "version": ROCKSIM_VERSION,
        "label": "RESEARCHER-ONLY ground truth",
        "warning": (
            "Includes hidden mesh + electrode attachments. Do not "
            "consume from the harvester pipeline."
        ),
        "snapshot": material.snapshot_internal(),
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"Wrote material snapshot to {out_path}")
    print(
        f"Hidden nodes: {material.n_hidden_nodes()}    "
        f"hidden edges: {material.n_hidden_edges()}    "
        f"electrodes: {material.n_electrodes()}"
    )
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    """Print the harvester-side surface view of a material.

    The CLI uses the BLACK-BOX; it does NOT inspect the internal mesh.
    This proves the command respects the boundary.
    """
    build_params = MaterialBuildParams(
        master_seed=args.seed,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
        model_name=args.model,
        geometry=GeometryParams(seed=args.seed),
    )
    material = build_material(build_params)
    solver = build_solver(material)
    iface = build_blackbox(material, solver)
    print(f"Material version (model) : {material.model_name}")
    print(f"Electrodes (harvester)   : {iface.electrode_count}")
    measurement = iface.evaluate({})
    example_eid = 0
    print(
        f"Drive none, V_e{example_eid} = "
        f"{measurement.electrode_voltages[example_eid]:0.4f} V"
    )
    a = 0
    b = min(1, iface.electrode_count - 1)
    o = min(2, iface.electrode_count - 1)
    if a == b or b == o or a == o:
        print("(trivially small electrode_count; skipping drive probe)")
        return 0
    meas = iface.evaluate({a: HIGH_VOLTAGE, b: LOW_VOLTAGE})
    print(
        f"Drive E{a}={HIGH_VOLTAGE:.2f} V, E{b}={LOW_VOLTAGE:.2f} V, "
        f"read E{o}={meas.electrode_voltages[o]:0.4f} V"
    )
    return 0


def cmd_xor_search(args: argparse.Namespace) -> int:
    out_dir = args.output or (
        f"results/xor_{args.model}_seed{args.seed}_iter{args.iterations}"
    )
    record = run_xor_experiment(
        seed=args.seed,
        material_model=args.model,
        iterations=args.iterations,
        strategy=args.strategy,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
        output_threshold=args.threshold,
        min_margin=args.min_margin,
        bias_limit=args.bias_limit,
    )
    save_xor_record(record, out_dir)
    _print_candidate_block(record)
    print(f"Wrote record to {out_dir}")
    print(
        f"Evidence level: {record['evidence_level']}  "
        f"({record['evidence_note']})"
    )
    return 0 if record["result"]["success"] else 2


def cmd_damage_recovery(args: argparse.Namespace) -> int:
    summary = run_damage_recovery(
        seed=args.seed,
        damage_fraction=args.damage,
        damage_seed=args.damage_seed,
        iterations=args.iterations,
        strategy=args.strategy,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
    )
    print(json.dumps(summary, indent=2))
    return 0


def _parse_seeds(spec: str) -> list[int]:
    """Parse 'a:b' (inclusive range) or 'a,b,c' (list) into a list of seeds."""
    if ":" in spec:
        a, b = spec.split(":", 1)
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",") if x.strip()]


def _parse_budgets(spec: str) -> tuple[int, ...]:
    return tuple(int(x) for x in spec.split(",") if x.strip())


def cmd_xor_budget_ladder(args: argparse.Namespace) -> int:
    budgets = _parse_budgets(args.budgets)
    out_dir = args.output or (
        f"results/budget_ladder/{args.model}_seed{args.seed}_n{args.nodes}"
    )
    record = run_budget_ladder(
        seed=args.seed,
        material_model=args.model,
        budgets=budgets,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
        output_threshold=args.threshold,
        min_margin=args.min_margin,
        bias_limit=args.bias_limit,
        output_dir=out_dir,
    )
    print(f"Budget ladder: model={args.model} seed={args.seed} "
          f"n={args.nodes}")
    print(f"  budgets = {list(budgets)}")
    print(
        f"  {'budget':>8}  {'status':<18}  "
        f"{'fit':>8}  {'acc':>3}  {'margin':>8}  {'runtime':>8}"
    )
    for row in record["rows"]:
        print(
            f"  {int(row['budget']):>8}  {row['status']:<18}  "
            f"{row['best_fitness']:>8.3f}  {row['accuracy']:>3}  "
            f"{row['margin']:>8.4f}  {row['runtime_seconds']:>7.1f}s"
        )
    print(f"Wrote {out_dir}/ladder.json and ladder.csv")
    return 0


def cmd_xor_seed_sweep(args: argparse.Namespace) -> int:
    seeds = _parse_seeds(args.seeds)
    out_dir = args.output or (
        f"results/seed_sweep/{args.model}_iter{args.iterations}_n{args.nodes}"
    )
    summary = run_seed_sweep(
        seeds=seeds,
        material_model=args.model,
        iterations=args.iterations,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
        output_threshold=args.threshold,
        min_margin=args.min_margin,
        bias_limit=args.bias_limit,
        output_dir=out_dir,
    )
    print(
        f"Seed sweep: model={args.model} iterations={args.iterations} "
        f"n={args.nodes}"
    )
    print(f"  seeds tested       = {summary['n_seeds_tested']}")
    print(f"  XOR found          = {summary['n_xor_found']}")
    print(f"  XOR not found      = {summary['n_xor_not_found']}")
    print(f"  solver failed      = {summary['n_solver_failed']}")
    print(
        f"  fraction_simulated_realisations_xor_found = "
        f"{summary['fraction_simulated_realisations_xor_found']:.3f}"
    )
    print(
        f"  total runtime      = "
        f"{summary['total_runtime_seconds']:.1f}s"
    )
    print(
        f"  Note: {summary['evidence_note']}"
    )
    print(f"Wrote {out_dir}/summary.json and rows.csv")
    return 0


def cmd_damage_sweep(args: argparse.Namespace) -> int:
    damages = tuple(float(x) for x in args.damages.split(",") if x.strip())
    seeds = _parse_seeds(args.seeds)
    out_dir = args.output or (
        f"results/damage_sweep/iter{args.iterations}_n{args.nodes}"
    )
    from rocksim.experiments.damage_recovery import run_damage_sweep
    summary = run_damage_sweep(
        damage_fractions=damages,
        seeds=seeds,
        iterations=args.iterations,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
        output_dir=out_dir,
    )
    print(f"Damage sweep: {len(damages)} damage x {len(seeds)} seeds = "
          f"{summary['n_trials']} trials")
    print("  Category counts (separately reported, NEVER merged):")
    for k, v in summary["category_counts"].items():
        print(f"    {k:>22}: {v}")
    print(f"  total trials: {summary['n_trials']}")
    print(
        f"  Note: {summary['evidence_note']}"
    )
    print(f"Wrote {out_dir}/summary.json and rows.csv")
    return 0


def cmd_compare_models(args: argparse.Namespace) -> int:
    out_dir = args.output or (
        f"results/compare_models/seed{args.seed}_n{args.nodes}_"
        f"iter{args.iterations}"
    )
    out = run_compare_models(
        seed=args.seed,
        iterations=args.iterations,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
        output_threshold=args.threshold,
        min_margin=args.min_margin,
        bias_limit=args.bias_limit,
        output_dir=out_dir,
    )
    lin, non = out["linear"], out["nonlinear"]
    print(
        f"compare-models: seed={args.seed} n={args.nodes} "
        f"iterations={args.iterations}"
    )
    print()
    print("  Linear")
    print(f"    status    = {lin['status']}")
    print(f"    success   = {lin['success']}")
    print(f"    fitness   = {lin['best_fitness']:.4f}")
    print(f"    accuracy  = {lin['accuracy']}/4")
    print(f"    margin    = {lin['margin']:.4f} V")
    print(
        "    V(00,01,10,11) = "
        f"{lin['best_outputs'].get('00', 0):+.3f}, "
        f"{lin['best_outputs'].get('01', 0):+.3f}, "
        f"{lin['best_outputs'].get('10', 0):+.3f}, "
        f"{lin['best_outputs'].get('11', 0):+.3f} V"
    )
    print(f"    runtime   = {lin['runtime_seconds']:.1f}s")
    print()
    print("  Nonlinear")
    print(f"    status    = {non['status']}")
    print(f"    success   = {non['success']}")
    print(f"    fitness   = {non['best_fitness']:.4f}")
    print(f"    accuracy  = {non['accuracy']}/4")
    print(f"    margin    = {non['margin']:.4f} V")
    print(
        "    V(00,01,10,11) = "
        f"{non['best_outputs'].get('00', 0):+.3f}, "
        f"{non['best_outputs'].get('01', 0):+.3f}, "
        f"{non['best_outputs'].get('10', 0):+.3f}, "
        f"{non['best_outputs'].get('11', 0):+.3f} V"
    )
    print(f"    runtime   = {non['runtime_seconds']:.1f}s")
    print()
    print(
        "Question addressed: does adding the explicitly defined "
        "nonlinear edge response make XOR-like material behaviour "
        "more discoverable in this simulation? (NOT 'can rock compute XOR'.)"
    )
    print(f"Wrote {out_dir}/compare.json")
    return 0


def cmd_export_blender(args: argparse.Namespace) -> int:
    build_params = MaterialBuildParams(
        master_seed=args.seed,
        n_hidden_nodes=args.nodes,
        electrode_count=args.electrodes,
        model_name=args.model,
        geometry=GeometryParams(seed=args.seed),
    )
    material = build_material(build_params)
    roles: dict[int, str] = {}
    if args.input_a is not None:
        roles[args.input_a] = "A"
    if args.input_b is not None:
        roles[args.input_b] = "B"
    if args.output_electrode is not None:
        roles[args.output_electrode] = "OUT"
    export = export_researcher_ground_truth(
        material=material,
        candidate_roles=roles,
    )
    abs_path = os.path.abspath(args.output_file)
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    write_blender_json(export, abs_path)
    print(f"Wrote Blender research export to {abs_path}")
    print(
        "Reminder: this file is RESEARCHER-ONLY and contains hidden "
        "graph internals; the harvester must never read it."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rocksim",
        description=(
            "RockSim -- black-box simulator for computation-discovery in "
            "an untouched 3-D material."
        ),
    )
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser(
        "generate",
        help="Generate a material and dump a researcher file.",
    )
    p_gen.add_argument("--seed", type=int, default=42)
    p_gen.add_argument(
        "--model", choices=["linear", "nonlinear"], default="nonlinear",
    )
    p_gen.add_argument("--nodes", type=int, default=DEFAULT_HIDDEN_NODES)
    p_gen.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_gen.add_argument("--output", default=None)
    p_gen.set_defaults(func=cmd_generate)

    p_ins = sub.add_parser(
        "inspect",
        help="Print the harvester-side surface view (black-box).",
    )
    p_ins.add_argument("--seed", type=int, default=42)
    p_ins.add_argument(
        "--model", choices=["linear", "nonlinear"], default="nonlinear",
    )
    p_ins.add_argument("--nodes", type=int, default=DEFAULT_HIDDEN_NODES)
    p_ins.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_ins.set_defaults(func=cmd_inspect)

    p_xor = sub.add_parser(
        "xor-search", help="Run the XOR black-box search.",
    )
    p_xor.add_argument("--seed", type=int, default=42)
    p_xor.add_argument(
        "--model", choices=["linear", "nonlinear"], default="nonlinear",
    )
    p_xor.add_argument(
        "--iterations", type=int, default=DEFAULT_XOR_ITERATIONS,
    )
    p_xor.add_argument(
        "--strategy",
        choices=["random", "hill_climb"],
        default=DEFAULT_SEARCH_STRATEGY,
    )
    p_xor.add_argument("--nodes", type=int, default=DEFAULT_HIDDEN_NODES)
    p_xor.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_xor.add_argument(
        "--threshold", type=float, default=DEFAULT_XOR_OUTPUT_THRESHOLD,
    )
    p_xor.add_argument(
        "--min-margin", type=float, default=DEFAULT_MIN_MARGIN,
    )
    p_xor.add_argument("--bias-limit", type=float, default=BIAS_LIMIT_ABS)
    p_xor.add_argument("--output", default=None)
    p_xor.set_defaults(func=cmd_xor_search)

    p_dmg = sub.add_parser(
        "damage-recovery", help="Run the damage/recovery experiment.",
    )
    p_dmg.add_argument("--seed", type=int, default=42)
    p_dmg.add_argument(
        "--damage", type=float, default=DEFAULT_DAMAGE_FRACTION,
    )
    p_dmg.add_argument("--damage-seed", type=int, default=None)
    p_dmg.add_argument(
        "--iterations", type=int, default=DEFAULT_XOR_ITERATIONS,
    )
    p_dmg.add_argument(
        "--strategy",
        choices=["random", "hill_climb"],
        default=DEFAULT_SEARCH_STRATEGY,
    )
    p_dmg.add_argument("--nodes", type=int, default=DEFAULT_HIDDEN_NODES)
    p_dmg.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_dmg.set_defaults(func=cmd_damage_recovery)

    p_dmg_sweep = sub.add_parser(
        "damage-sweep",
        help=(
            "Run the full 5-phase experiment over a matrix of "
            "damage fractions and seeds."
        ),
    )
    p_dmg_sweep.add_argument(
        "--damages", default="0.0,0.01,0.02,0.05,0.10,0.20",
        help="Comma-separated damage fractions.",
    )
    p_dmg_sweep.add_argument(
        "--seeds", default="0,1,2,3,4",
        help=(
            "Seeds. Either 'a:b' for inclusive range, or "
            "'a,b,c' for a comma-separated list."
        ),
    )
    p_dmg_sweep.add_argument(
        "--iterations", type=int, default=DEFAULT_XOR_ITERATIONS,
    )
    p_dmg_sweep.add_argument(
        "--nodes", type=int, default=DEFAULT_HIDDEN_NODES,
    )
    p_dmg_sweep.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_dmg_sweep.add_argument("--output", default=None)
    p_dmg_sweep.set_defaults(func=cmd_damage_sweep)

    p_ladder = sub.add_parser(
        "xor-budget-ladder",
        help=(
            "Run the same material across an increasing iteration "
            "budget ladder."
        ),
    )
    p_ladder.add_argument("--seed", type=int, default=42)
    p_ladder.add_argument(
        "--model", choices=["linear", "nonlinear"], default="nonlinear",
    )
    p_ladder.add_argument(
        "--budgets", default="5000,10000,25000,50000",
        help="Comma-separated iteration budgets.",
    )
    p_ladder.add_argument("--nodes", type=int, default=DEFAULT_HIDDEN_NODES)
    p_ladder.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_ladder.add_argument(
        "--threshold", type=float, default=DEFAULT_XOR_OUTPUT_THRESHOLD,
    )
    p_ladder.add_argument(
        "--min-margin", type=float, default=DEFAULT_MIN_MARGIN,
    )
    p_ladder.add_argument("--bias-limit", type=float, default=BIAS_LIMIT_ABS)
    p_ladder.add_argument("--output", default=None)
    p_ladder.set_defaults(func=cmd_xor_budget_ladder)

    p_sweep = sub.add_parser(
        "xor-seed-sweep",
        help=(
            "Run the XOR search on a range of seeds; aggregate the "
            "fraction of simulated realisations where XOR was found."
        ),
    )
    p_sweep.add_argument(
        "--model", choices=["linear", "nonlinear"], default="nonlinear",
    )
    p_sweep.add_argument(
        "--seeds", default="0:20",
        help=(
            "Seeds to run. Either 'a:b' for inclusive range, or "
            "'a,b,c' for a comma-separated list."
        ),
    )
    p_sweep.add_argument(
        "--iterations", type=int, default=DEFAULT_XOR_ITERATIONS,
    )
    p_sweep.add_argument("--nodes", type=int, default=DEFAULT_HIDDEN_NODES)
    p_sweep.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_sweep.add_argument(
        "--threshold", type=float, default=DEFAULT_XOR_OUTPUT_THRESHOLD,
    )
    p_sweep.add_argument(
        "--min-margin", type=float, default=DEFAULT_MIN_MARGIN,
    )
    p_sweep.add_argument("--bias-limit", type=float, default=BIAS_LIMIT_ABS)
    p_sweep.add_argument("--output", default=None)
    p_sweep.set_defaults(func=cmd_xor_seed_sweep)

    p_cmp = sub.add_parser(
        "compare-models",
        help=(
            "Run the same geometry seed under both linear and "
            "nonlinear material models; print a side-by-side report."
        ),
    )
    p_cmp.add_argument("--seed", type=int, default=42)
    p_cmp.add_argument(
        "--iterations", type=int, default=10_000,
    )
    p_cmp.add_argument("--nodes", type=int, default=DEFAULT_HIDDEN_NODES)
    p_cmp.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_cmp.add_argument(
        "--threshold", type=float, default=DEFAULT_XOR_OUTPUT_THRESHOLD,
    )
    p_cmp.add_argument(
        "--min-margin", type=float, default=DEFAULT_MIN_MARGIN,
    )
    p_cmp.add_argument("--bias-limit", type=float, default=BIAS_LIMIT_ABS)
    p_cmp.add_argument("--output", default=None)
    p_cmp.set_defaults(func=cmd_compare_models)

    p_exp = sub.add_parser(
        "export-blender",
        help="Export researcher-only Blender JSON (internal mesh).",
    )
    p_exp.add_argument("--seed", type=int, default=42)
    p_exp.add_argument(
        "--model", choices=["linear", "nonlinear"], default="nonlinear",
    )
    p_exp.add_argument("--nodes", type=int, default=DEFAULT_HIDDEN_NODES)
    p_exp.add_argument(
        "--electrodes", type=int, default=DEFAULT_ELECTRODE_COUNT,
    )
    p_exp.add_argument("--input-a", type=int, default=None)
    p_exp.add_argument("--input-b", type=int, default=None)
    p_exp.add_argument(
        "--output-electrode", type=int, default=None,
        help="Electrode id for output role.",
    )
    p_exp.add_argument(
        "--output-file", dest="output_file", default="rock.json",
    )
    p_exp.set_defaults(func=cmd_export_blender)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "version", False):
        print(ROCKSIM_VERSION)
        return 0
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
