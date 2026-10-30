# Limitations and evidence levels

## Four evidence levels

A result in RockSim is always tagged with one of the following levels.
The project must never claim a result at a higher level than was actually
demonstrated.

| Level | What is shown |
|-------|---------------|
| 1 | Mathematical / Boolean existence. (e.g. "an XOR function exists.") |
| 2 | Numerical simulation of a physical network (this project lives here). |
| 3 | Laboratory measurement on a fabricated artificial material. |
| 4 | Behaviour observed in an untouched natural material (e.g. a real rock). |

**Default tag for any RockSim success: LEVEL 2.**

Level 3 and 4 require separate, dedicated work. We do not bootstrap
evidence from simulation to natural material.

## Scope limitations in version 0.1.0

- **Graph model is not geological microstructure.** It is a placeholder
  irregular 3-D point cloud; no grain boundaries, no mineralogy, no
  fractal statistics.
- **Quasi-static.** No capacitance, inductance, wave physics, or
  electromagnetic coupling. A frequency-dependent solver is on the
  roadmap.
- **Nonlinear model is hypothetical.** `G(V) = G0 · (1 + α · V²)` is a
  toy voltage-dependent conductance. It is *not* a model of an ordinary
  rock. It is *not* a transistor.
- **Electrode contact resistance simplified.** Each electrode couples to
  one or more hidden nodes through a fixed contact conductance.
  Spreading resistance, contact rectification, and double-layer
  capacitance are ignored.
- **No thermal model.** Power dissipation does not raise temperature.
- **No noise.** Real systems have 1/f, thermal, and shot noise. We will
  add a noise layer later; until then, "successful XOR" is an
  idealised finding.
- **No material aging.**
- **Defects are edge cuts only.** They do not cross-couple, leak, or
  drift.
- **Search budget is limited.** Hundreds or thousands of iterations per
  material. Real discovery could require vastly more. We do not draw
  asymptotic conclusions from 0.1.0 results.
- **No guarantee that the search cannot see through the boundary via
  measurement sequences.** The Protocol stops direct leaks; indirect
  inference is mitigated but not yet rigorously sealed off. This is
  documented as a known research risk (see `docs/roadmap.md`).
- **No claim about ordinary rock.** Any "XOR found in simulation" is
  exactly that — and that alone.

## Failure modes we explicitly accept as scientific results

- A linear material search never finds XOR within budget. ✓ Expected.
- A nonlinear material search also fails. Suggests the candidate encoding
  is too sparse or the search is too weak. Future versions should improve
  both.
- Damage recovery never finds a replacement configuration. Indicates the
  architecture has limited fault tolerance in 0.1.0 — design signal.

These are not bugs. They are evidence and they must remain in `results/`.

## Milestone 2 specific limitations

- The hill-climb searcher in 0.2.0 mutates one gene at a time and uses
  small initial random restarts. It is not a sophisticated optimiser.
  When a search returns `SEARCH_EXHAUSTED`, that means the *current*
  search methodology did not find XOR within the iteration budget; it
  is NOT a claim that XOR is impossible on that material.
- The 5-phase damage/recovery experiment assumes that Phase A
  succeeds. The honest outcome `DISCOVERY_FAILED` is preserved and
  reported; we do not lower the success criterion to make Phase E
  look like a recovery.
- The Blender export is human-readable JSON. A future Blender
  importer is out of scope. The contract is documented inline in
  `src/rocksim/export/blender_json.py` and in `docs/experiments.md`.
- The seed-sweep aggregator reports the "fraction of simulated
  material realisations where the current search discovered XOR". It
  is NOT a yield, NOT a probability that real material computes.
- Solver failures (e.g. Picard iteration not converging) are counted
  in `search_counters.n_solver_failures`. A seed whose evaluation
  repeatedly fails is reported as `SOLVER_FAILED` in the per-seed
  row and does NOT contribute to the success count.
- The `SOLVER_FAILED` count is part of the per-search record, not
  the per-material record. This means the same material can yield
  different counts across search methodologies. We do not retry a
  failed material under a different search; we report the result
  as-is.

## Anti-cheating rules (Milestone 2)

The original anti-cheating rules from Milestone 1 remain in force.
Additionally:

- A recovered candidate is reported as "discovered externally
  configured material response", never as "internal re-routing",
  unless the user has additional evidence of an internal path. The
  test `test_compare_candidates_flags_changes` ensures the summary
  reports differences in input A / B / OUT / bias electrodes / bias
  values; a successful Phase E with NO differences between old and
  new candidate is still labelled `RECOVERED` but the user is
  expected to inspect `comparison` before drawing strong conclusions.
- The black-box boundary test in
  `tests/test_blackbox_boundary.py::test_blender_export_cannot_be_reached_through_material_interface`
  explicitly asserts that the harvester cannot import the Blender
  exporter from `rocksim.interface` or `rocksim.material`.
- Search counters (`n_solver_failures`, `n_illegal_candidates`,
  `n_valid_evaluated`) are written into every saved record so the
  reader can spot a search that quietly discarded many candidates
  before reporting a result.
