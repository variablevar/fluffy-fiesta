# Architecture

RockSim is split into two worlds with a one-way information flow.

```
        ┌─────────────────────────────────────────┐
        │              World B                    │
        │             HARVESTER                   │
        │                                         │
        │  - candidate generator                  │
        │  - fitness function                     │
        │  - search algorithm (random, HC, EA,   │
        │                   CMA-ES, BO, SA, ...)  │
        │                                         │
        │  Only sees: MaterialInterface protocol │
        └────────────────────┬────────────────────┘
                             │  set voltages / read V,I
                             ▼
        ┌─────────────────────────────────────────┐
        │              World A                    │
        │           PHYSICS / MATERIAL            │
        │                                         │
        │  - hidden internal 3-D graph            │
        │  - conductances / nonlinear elements    │
        │  - defects (only World A knows about)   │
        │  - nodal solver (linear / nonlinear)    │
        │  - electrode attachment model           │
        └─────────────────────────────────────────┘
```

## The hard boundary

The harvester receives an object that satisfies a `MaterialInterface`
Protocol and nothing more. The Protocol exposes:

- `electrode_count` (property)
- `evaluate(driven_voltages: dict[int, float]) -> Measurement`
- `reset()` / `step(dt)`

`Measurement` exposes only `electrode_voltages` and `electrode_currents` —
arrays indexed by electrode id. **No** hidden graph, hidden node ids, hidden
coordinates, hidden component types, or hidden defects cross this boundary.

This boundary is enforced in three ways:

1. **Import isolation.** `rocksim.interface` and `rocksim.harvest` do not
   import `rocksim.material` or `rocksim.physics`. The interface wraps any
   internal object behind the Protocol.
2. **Type narrowing.** The harvester is given the Protocol-typed object, not
   the concrete material class.
3. **Test.** `tests/test_blackbox_boundary.py` builds a fake internal model
   that tries to leak internal fields across the boundary and asserts the
   Protocol hides them.

## Material generation

A deterministic, seeded process generates an irregular 3-D point cloud
inside a roughly rock-shaped volume (union of jittered spheres, no
axis-aligned geometry). Edges connect spatially nearby nodes by k-NN in
3-D space. Conductances are drawn from a log-normal distribution to make
the network neither perfectly uniform nor pathologically sparse.

Surface electrodes are placed by selecting the outermost hidden nodes along
distributed directions (Fibonacci sphere), then taking the nearest hidden
node(s) to each direction. Each electrode couples to one or more hidden nodes
through a configurable contact conductance.

The exact generation logic lives in `rocksim.material.geometry` and
`rocksim.material.graph`. It is reproducible: same seed → same material.

## Search

The harvester tries:

- `input_a` electrode id
- `input_b` electrode id
- `output` electrode id
- bias voltages for any number of remaining electrodes (configurable)
- output threshold

All candidate configurations must respect legality rules (see
`docs/harvester.md`). Default `LOW=0.0 V`, `HIGH=1.0 V`, bias in `[-1, +1] V`.
These live in `rocksim.config`.

A candidate **counts as XOR found** iff all four truth-table rows are
classified correctly AND the analog outputs in the LOW group sit below the
threshold − margin and outputs in the HIGH group sit above the threshold +
margin. Margin is configurable (default 0.05 V).

## Negative-result discipline

The control experiment runs the *same* XOR search twice — once with
`material_model="linear"` and once with `material_model="nonlinear"`. We
expect the linear run to usually fail; that is a valuable empirical
observation about the architecture, not a bug. The result is stored with
`success=False` and remains committed in `results/`.
