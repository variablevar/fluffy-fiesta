# Experiments

All experiments write to `results/<experiment-name>/run_<NNNNNN>/`. Each
run directory contains:

```
config.json                 — model id, seeds, hyperparameters
material_summary.json       — counts, ranges (no hidden topology leaked here)
best_candidate.json         — candidate parameters and analog truth table
search_history.csv          — per-iteration fitness, accepted flag, etc.
researcher_ground_truth.json (optional) — internal mesh, voltages, currents.
                                          Only emitted via export-blender.
```

## Reproducibility schema

`config.json` minimum keys:

- `timestamp_utc`
- `rocksim_version`
- `git_commit_hash` (or `null`)
- `master_seed`
- `material_seed`
- `search_seed`
- `material_model` ∈ {"linear", "nonlinear"}
- `material_params` (dict)
- `electrode_count`
- `hidden_node_count`
- `signal_levels` = {`low`, `high`}
- `bias_limit`
- `output_threshold`
- `min_margin`
- `iterations`
- `search` ∈ {"random", "hill_climb"}

A experiment is **reproducible** iff running the same config produces the
same `best_candidate.json` and `truth_table`. We test this property in
`tests/test_reproducibility.py`.

## XOR search experiment

```
python -m rocksim.cli xor-search \
  --model nonlinear --seed 42 --iterations 10000 \
  --output results/xor_nonlinear_42
```

Default search strategy: `hill_climb` with random restarts.

## Control experiment

```
python -m rocksim.cli xor-search --model linear     --seed 42 --iterations 10000
python -m rocksim.cli xor-search --model nonlinear  --seed 42 --iterations 10000
```

Run with the same `master_seed` to keep the material identical between
runs and isolate the effect of the model.

The linear run is *expected* to underperform. That negative result is a
scientific claim about the architecture (a passive linear network
generally cannot be coerced into a single-output XOR via electrode choice
alone) and is preserved.

## Damage / recovery experiment

```
python -m rocksim.cli damage-recovery --seed 42 --damage 0.05
```

1. Generate material with `master_seed`.
2. Run XOR search → candidate C0.
3. Hide-defect: remove (1 − survivor_fraction) of internal edges chosen by
   a damage RNG seeded from `--damage-seed`.
4. Re-evaluate the *old* candidate C0 against the damaged material —
   measure truth-table and success criterion.
5. Run a fresh XOR search against the damaged material → candidate C1.
6. Compare C0 vs C1.
7. Save all six records.

## Reproduction script

`scripts/run_reproducibility_check.py` re-evaluates a saved candidate from
its `config.json` and asserts the recorded truth-table numbers within a
small tolerance.

## Result-status taxonomy (Milestone 2)

Every experiment now returns ONE of the following status strings. The
strings are part of the package API and must not be renamed without
a major version bump.

    SEARCH_SUCCESS        — black-box search found a candidate that
                            passes all four XOR rows and the minimum
                            margin.
    SEARCH_EXHAUSTED      — search budget was used up without finding
                            a successful candidate.
    SOLVER_FAILED         — at least one iteration's evaluation
                            raised a non-recoverable solver error.
                            Failure count is reported separately.
    DISCOVERY_FAILED      — XOR could not be found in the pristine
                            material. Damage/recovery trial stops
                            here honestly.
    SURVIVED_DAMAGE       — the pristine XOR configuration still
                            satisfies the truth table on the
                            damaged material.
    BROKEN_BY_DAMAGE      — the pristine XOR configuration no longer
                            satisfies the truth table on the
                            damaged material.
    RECOVERED             — a fresh black-box search found a
                            DIFFERENT externally configured material
                            response that satisfies the truth table
                            on the damaged material.
    RECOVERY_FAILED       — neither the pristine configuration
                            survives, nor can a fresh search find a
                            new one within budget.

## Search history schema

`search_history.csv` written by every XOR search has these columns:

    iteration, best_fitness, best_accuracy, best_margin,
    best_output_00, best_output_01, best_output_10, best_output_11

`best_*` is the best snapshot at that iteration. The CSV does NOT
expose hidden material information.

## XOR budget ladder (Milestone 2)

The SAME material is reused across an increasing iteration budget:

    5,000
    10,000
    25,000
    50,000

This tests whether the search budget — not the material — is the
limiting factor. The material is not regenerated between budgets.

CLI:

    python -m rocksim.cli xor-budget-ladder \
        --seed 42 --model nonlinear --nodes 200 \
        --budgets 5000,10000,25000,50000

## XOR seed sweep (Milestone 2)

Runs the XOR search on a list of seeds and reports:

    n_seeds_tested
    n_xor_found
    n_xor_not_found
    n_solver_failed
    fraction_simulated_realisations_xor_found
    total_runtime_seconds

The fraction is explicitly named "fraction of simulated material
realisations where the current search discovered XOR". It is NOT a
yield, NOT a probability that real material computes.

CLI:

    python -m rocksim.cli xor-seed-sweep \
        --model nonlinear --seeds 0:19 --iterations 10000 --nodes 200

## Linear vs nonlinear comparison (Milestone 2)

Runs the exact same geometry seed under both `linear` and `nonlinear`
models, side-by-side. The geometry is shared; only the edge response
model changes.

CLI:

    python -m rocksim.cli compare-models \
        --seed 42 --nodes 200 --iterations 10000

The question addressed is: "does adding the explicitly defined
nonlinear edge response make XOR-like material behaviour more
discoverable in this simulation?" It is NOT "can rock compute XOR?".

## Damage / recovery experiment (Milestone 2 — full 5-phase)

The experiment driver `run_damage_recovery` implements the complete
5-phase procedure:

    PHASE A — DISCOVERY
        Generate a hidden material, wrap it behind MaterialInterface,
        search for XOR using only surface measurements. If no XOR is
        found, report DISCOVERY_FAILED honestly and stop.

    PHASE B — BASELINE
        Re-evaluate the successful candidate to obtain its analog
        truth table on the pristine material.

    PHASE C — DAMAGE
        Disable a fraction of internal edges inside World A. The
        harvester receives no defect map. The defect map is recorded
        only in a researcher-only file.

    PHASE D — OLD CONFIGURATION TEST
        Apply the EXACT pre-damage electrode configuration. Report
        SURVIVED_DAMAGE or BROKEN_BY_DAMAGE with before/after analog
        truth tables.

    PHASE E — RECOVERY
        If broken, run a black-box search again. The optimiser may
        use ONLY electrode measurements. If a new XOR configuration
        is found, report RECOVERED. If not, report RECOVERY_FAILED.

The summary contains all five phase sub-records. The new candidate
is compared to the old via `_compare_candidates` (input A / B / OUT
changes, bias electrode changes, bias value changes). The summary
explicitly says "discovered externally configured material response",
not "internal re-routing", unless the user has additional evidence.

## Damage sweep (Milestone 2)

Runs the full 5-phase experiment for each (damage, seed) pair:

    damage_fractions = (0.0, 0.01, 0.02, 0.05, 0.10, 0.20)
    seeds            = (0, 1, 2, 3, 4)

Categorises each trial into one of the eight statuses and reports
them separately. Categories are NOT merged.

CLI:

    python -m rocksim.cli damage-sweep \
        --iterations 200 --nodes 100

## Blender JSON contract (Milestone 2)

The exporter writes three blocks (when the relevant material is
supplied):

    pristine:  the material at the moment XOR was discovered, with
               electrode roles A / B / OUTPUT / BIAS / UNUSED.
    damaged:   the same material after damage, at the same drive
               pattern. Damaged edges are flagged in each edge's
               `damaged` field.
    recovered: the same material after a fresh black-box search
               discovered a new XOR configuration. New electrode
               roles and new drive pattern are recorded.

Each block contains:

    hidden_nodes: x, y, z, voltage_V
    edges:        u, v, g0, model, current_A_u_to_v, power_W,
                  voltage_drop_V, damaged
    electrodes:   electrode_id, role, drive_V, measured_V,
                  attached_hidden_nodes, contact_conductance

The file is the single on-disk contract for a future Blender
importer. The harvester pipeline never consumes it. See the
`test_blender_export_cannot_be_reached_through_material_interface`
boundary test.
