# RockSim

> Can computation be discovered/configured from an irregular 3-D physical
> material *without* touching its internal structure?

RockSim is a research simulator that investigates this question at the
**simulation** level only. The material is treated as a black box. The
harvester interacts **only** through surface electrodes. The internal mesh is
**never inspected, polished, drilled, or rewired** by the optimiser.

```
        HARVESTER  (chooses electrodes + voltages)
              |
              |  voltages / measurements
              v
        SURFACE ELECTRODES
          o o o o o o
         /           \
        |   HIDDEN    |   <-- never seen by harvester
        |  3-D MESH   |
         \           /
          o o o o o o
```

---

## What this project is

- A deterministic, seeded simulator of irregular 3-D resistive / nonlinear
  material graphs with surface electrodes.
- A black-box optimisation framework that searches for electrode configurations
  that make the material emulate a target Boolean function (initially XOR).
- A control experiment comparing **linear** vs **nonlinear** material models,
  preserving negative results.
- A reproducibility system: every run writes its seeds, model, hyperparameters
  and measurements to disk.

## What this project is NOT

- Not a claim that real rock contains transistor-like elements.
- Not a physics-grade material model.
- Not a Blender plugin (yet — a JSON export is provided for downstream
  visualisation).
- Not a demonstration that natural material computes.

See [`docs/limitations.md`](docs/limitations.md) for the four evidence levels
and what kind of claim a given result supports.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Without an editable install:

```bash
pip install numpy scipy networkx matplotlib pytest
export PYTHONPATH=src
```

## Quickstart

```bash
# Generate a deterministic material and inspect it.
python -m rocksim.cli generate --seed 42
python -m rocksim.cli inspect  --seed 42

# Run the XOR black-box search.
python -m rocksim.cli xor-search --model nonlinear --seed 42 --iterations 5000
python -m rocksim.cli xor-search --model linear     --seed 42 --iterations 5000

# Milestone 2: budget ladder, seed sweep, model comparison.
python -m rocksim.cli xor-budget-ladder --model nonlinear --seed 42 --nodes 200 \
        --budgets 5000,10000,25000,50000
python -m rocksim.cli xor-seed-sweep --model nonlinear --seeds 0:19 \
        --iterations 10000 --nodes 200
python -m rocksim.cli compare-models --seed 42 --nodes 200 --iterations 10000

# Run a damage/recovery experiment.
python -m rocksim.cli damage-recovery --seed 42 --damage 0.05
python -m rocksim.cli damage-sweep --iterations 200 --nodes 100

# Export researcher-only data for downstream visualisation.
python -m rocksim.cli export-blender --seed 42 --output-file results/run.json

# Run the test suite.
pytest -q
```

## Architecture in one breath

Two worlds, structurally separated by Python visibility:

| World A — Physics / Material | World B — Harvester |
|-----------------------------|---------------------|
| Hidden nodes & edges        | Receives only an electrode protocol |
| Conductances, defects       | Sets voltages, reads electrode V/I   |
| Solves the field            | Optimises external electrode config  |

The harvester **cannot** import `rocksim.material.*` directly. It receives a
`MaterialInterface` (Protocol) object exposing only `evaluate()`,
`electrode_count`, `reset()`, and `step()`. The hidden graph is never returned
across this boundary. This is enforced by tests (`tests/test_blackbox_boundary.py`).

Read [`docs/architecture.md`](docs/architecture.md) for details.

## Status

This is **0.2.0 (alpha, Milestone 2)**. Pieces in this milestone:

- deterministic 3-D material generation
- surface electrode placement
- sparse quasi-static linear nodal solver (validated against analytic circuits)
- nonlinear material model with iteration-to-convergence solver
- black-box XOR candidate search with margin-based success criterion
- search history CSV with all four analog outputs, accuracy, margin
- result-status taxonomy: SEARCH_SUCCESS, SEARCH_EXHAUSTED, SOLVER_FAILED,
  DISCOVERY_FAILED, SURVIVED_DAMAGE, BROKEN_BY_DAMAGE, RECOVERED,
  RECOVERY_FAILED
- 5-phase damage/recovery experiment (Discovery → Baseline → Damage
  → Old-config test → Recovery) with researcher-only damage map
- researcher-only internal current/voltage/power export via Blender JSON
- extended Blender JSON contract with pristine/damaged/recovered blocks
- CLI: `generate`, `inspect`, `xor-search`, `damage-recovery`,
  `xor-budget-ladder`, `xor-seed-sweep`, `compare-models`,
  `damage-sweep`, `export-blender`

Planned: larger meshes, CMA-ES, evolutionary search, Blender importer,
hysteretic / directional elements. See [`docs/roadmap.md`](docs/roadmap.md).

## License

MIT — see [`LICENSE`](LICENSE).
