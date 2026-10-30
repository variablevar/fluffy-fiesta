# The harvester

The harvester is *only* the optimiser side. It does not know what is
inside the material. It receives a `MaterialInterface` Protocol-typed
object that exposes:

```python
class MaterialInterface(Protocol):
    @property
    def electrode_count(self) -> int: ...

    def evaluate(
        self,
        driven_voltages: dict[int, float],
    ) -> "Measurement": ...

    def reset(self) -> None: ...
```

A returned `Measurement` is a small dataclass:

```python
@dataclass
class Measurement:
    electrode_voltages: dict[int, float]   # V at each electrode
    electrode_currents: dict[int, float]   # A leaving each electrode
```

It contains nothing about the hidden graph.

## What the harvester may *not* do

- import `rocksim.material.*` or `rocksim.physics.*`
- call into `Measurement` methods that leak internal state
- access internal node ids
- recompute impedances from any sequence of measurements to "see through"
  the boundary (this is a research goal, not a guarantee of 0.1.0; we will
  add a more rigorous guarantee in a later version using known-noise
  injection)

## Candidate representation

```python
@dataclass
class Candidate:
    input_a: int
    input_b: int
    output: int
    biases: dict[int, float]
    output_threshold: float
```

Legality:

- `input_a`, `input_b`, `output` are distinct electrode ids in
  `range(electrode_count)`.
- `biases.keys()` does not contain `input_a`, `input_b`, or `output`.
- Each bias is in `[-bias_limit, +bias_limit]`.
- `output_threshold` is in `[LOW, HIGH]`.

These are checked by `Candidate.validate(...)` before evaluation.

## Fitness

Per evaluation:

- 4 measurements are taken, one per XOR row.
- Each gives an analog output voltage.
- Predicted bit = `(V_out >= threshold)`.
- Fitness rewards:

  - correct bits on all four rows (must-have)
  - margin from threshold on every row (have-want)
  - separation between the worst LOW-group voltage and the threshold,
    plus between threshold and worst HIGH-group voltage

- Optional penalties for total dissipated power. Off by default in 0.1.0.

The success criterion:

```
all four bits correct
AND
min_high > threshold + min_margin
AND
max_low  < threshold − min_margin
```

`min_margin` defaults to `0.05 V`.

## Search algorithms

- `random`: pure uniform random sampling.
- `hill_climb`: start from random, mutate one gene at a time, accept
  strict improvement.

Both are kept simple so the boundary stays auditable. CMA-ES, evolutionary
algorithms, Bayesian opt, simulated annealing are listed as
`SearchStrategy` Protocol implementations; adding them does not require
modifying the fitness, candidate, or material modules.

## Why so much discipline?

If anything in the search pipeline can see the hidden graph, the
project's central scientific question is no longer being asked. A
harvester that knows the internal structure trivially hand-crafts XOR by
selecting a NAND subgraph. The boundary exists precisely to prevent
that. The implementation enforces it both structurally and with tests.
