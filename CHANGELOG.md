# Changelog

All notable changes to RockSim are recorded here. Versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] — Milestone 2: damage / recovery, seed sweep, budget ladder

### Added
- Result-status taxonomy: `SEARCH_SUCCESS`, `SEARCH_EXHAUSTED`,
  `SOLVER_FAILED`, `DISCOVERY_FAILED`, `SURVIVED_DAMAGE`,
  `BROKEN_BY_DAMAGE`, `RECOVERED`, `RECOVERY_FAILED`.
- `SearchResult` now carries the four best analog outputs, search status,
  and counters (`n_valid_evaluated`, `n_illegal_candidates`,
  `n_solver_failures`).
- `search_history.csv` schema: `iteration, best_fitness, best_accuracy,
  best_margin, best_output_00, best_output_01, best_output_10,
  best_output_11`.
- New experiment drivers:
  - `run_budget_ladder` — same material, increasing iteration budget.
  - `run_seed_sweep` — runs the search across a list of seeds and
    reports the fraction of simulated realisations where XOR was
    found.
  - `run_compare_models` — same geometry seed under linear and
    nonlinear models, side-by-side.
  - `run_damage_sweep` — 5-phase experiment over a matrix of
    (damage_fraction, seed) pairs, with separate category counts.
- Complete 5-phase damage/recovery experiment (Discovery → Baseline
  → Damage → Old-config test → Recovery) with researcher-only damage
  map and Blender export.
- Researcher-only `solve_with_internal_state` in the physics layer
  (node voltages, edge currents, edge power). Reachable only via
  `rocksim.export.blender_json`. The harvester pipeline cannot reach
  it (boundary test added).
- Blender export contract now contains `pristine`, `damaged`,
  `recovered` blocks with internal currents, powers, electrode roles
  (A / B / OUTPUT / BIAS / UNUSED), and damaged-edge flags.
- New CLI subcommands: `xor-budget-ladder`, `xor-seed-sweep`,
  `compare-models`, `damage-sweep`.
- New tests: rich search-result fields, harvester cannot read
  internal currents/powers, Blender export cannot leak through
  MaterialInterface, damage-recovery phases, seed sweep and
  compare-models.

### Changed
- `search.py` now writes the BEST-so-far snapshot per history row
  (not per-evaluation raw row), to keep CSV size manageable.
- `xor_search.py` records `search_counters` and the new `status`
  string in the saved JSON.
- `damage_recovery.py` rewritten end-to-end; all five phase files
  are always written when discovery succeeds.

### Known limitations
See `docs/limitations.md`. Quasi-static only. No capacitance,
inductance, electromagnetic coupling, or thermal effects. Defects
are simple edge cuts. Recovered configurations are reported as
"discovered externally configured material response", never as
"internal re-routing".

## [0.1.0] — Initial simulation skeleton

### Added
- Repository scaffolding (pyproject, LICENSE, .gitignore).
- Architecture, physics-model, harvester, experiments, limitations
  and roadmap documents under `docs/`.
- Material layer: deterministic irregular 3-D graph generation with
  surface electrode placement.
- Black-box `MaterialInterface` Protocol. Harvester cannot import
  internal material modules.
- Linear quasi-static nodal solver using SciPy sparse matrices,
  validated against analytic voltage divider / chain / parallel-
  resistor cases.
- Explicitly documented nonlinear material model
  `G(V) = G0·(1 + α·V²)` with Picard iteration to convergence.
- XOR candidate + margin-based fitness + random/hill-climb black-box
  search.
- Linear vs nonlinear **control** experiment.
- Damage/recovery experiment: hidden edges broken, harvester only
  sees the changed measurements.
- Reproducible experiment records (JSON) with seeds, model id, git
  hash, timestamps, truth-table measurements.
- Blender JSON export for researcher-side visualisation (labelled
  clearly).
- CLI: `generate`, `inspect`, `xor-search`, `damage-recovery`,
  `export-blender`.
- Pytest suite with strict black-box boundary tests.

### Known limitations
See `docs/limitations.md`. Quasi-static only. No capacitance,
inductance, electromagnetic coupling, or thermal effects. Defects are
simple edge cuts.
