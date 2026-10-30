# Roadmap

## Past

- 0.1.0 (this release) — foundational skeleton, linear + nonlinear
  physics, XOR search, damage/recovery, Blender JSON export.

## Next

### 0.2.0 — Search scale and honesty
- CMA-ES for continuous bias voltages; mixed-integer outer loop for
  electrode ids.
- Deterministic noise injection in the measurement to discourage
  information leakage across the boundary and to test robustness of
  "found" candidates.
- Reproducibility-script that re-simulates a saved candidate and
  confirms identity to `1e-6 V`.

### 0.3.0 — Richer physics
- Hysteretic / memristive edge elements.
- Directional / diode-like elements.
- A *deliberately documented* crystalline vs amorphous material switch.

### 0.4.0 — Better failures
- Larger meshes (≥ 5k hidden nodes) with sparse direct solver.
- Benchmark suite: how often does XOR get found at varying seed,
  varying material size, varying damage fraction.

### 1.0.0 — Multi-function targets
- AND, OR, NAND, half-adder, parity on 3 bits.
- Structured search by candidate gene-pool seeding.
- Multi-output materials.

## Later

- Blender importer (`tools/import_blender.py`).
- Capacitive / inductive add-on module.
- Optional GPU-backed solver for very large meshes.
- An "honest benchmark" report comparing:
  - random uniform materials
  - structured materials
  - geometries inspired by statistical rock samples (still simulation).

## Out of scope unless scope changes

- Real-rock experiments. We do not currently have a Level 3 / Level 4
  pipeline and will not pretend otherwise. See `docs/limitations.md`.

## Milestone 2 (0.2.0) — completed

Completed in 0.2.0:

- result-status taxonomy
- search history with all four analog outputs and counters
- XOR budget ladder (5,000 / 10,000 / 25,000 / 50,000)
- 20-seed XOR sweep
- linear vs nonlinear comparison
- 5-phase damage / recovery experiment
- damage sweep (0% / 1% / 2% / 5% / 10% / 20%)
- researcher-only internal current / voltage / power map
- extended Blender JSON contract with pristine/damaged/recovered blocks

## Milestone 3 (planned)

- larger meshes (≥ 5k hidden nodes) with sparse direct solver
- CMA-ES, evolutionary algorithms, simulated annealing
- Blended memristive / hysteretic / directional element models
- dedicated 3-bit / 4-bit parity benchmarks
- A real Blender importer (out of scope here)
- more aggressive ground-truth stress tests (defect map comparison)
- additional success criteria (power, dissipation, robustness to
  ambient drift in a noise module)
