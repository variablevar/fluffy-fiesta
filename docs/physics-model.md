# Physics model

RockSim is **quasi-static**. We solve for steady-state voltages assuming
applied electrode voltages are held constant during one evaluation. There
is no time integration, no wave physics, no thermal coupling, no
electromagnetism beyond the electro-quasistatic approximation.

## Linear material model

Edges are linear conductances `G_e > 0`. Given:

- `N_h` hidden internal nodes with unknown voltages `V_h ∈ ℝᴺʰ`.
- `N_e` electrode contact conductances `G_c,k > 0` coupling electrode `k` to
  one (or a few) hidden nodes.

Applying Kirchhoff's Current Law at each hidden node gives the nodal
equation

```
    Σ_e   G_e  (V_j − V_i)    for each internal node i
 +  Σ_k   G_c,k (V_drive,k − V_i)  for electrodes k coupled to i
   = 0
```

Stacking all `N_h` equations yields a sparse symmetric positive-definite
linear system `A · v_h = b`, where:

- `A` is the nodal admittance matrix (Laplacian plus contact conductances)
- `b` is the current injected by the driven electrodes into the hidden mesh
- `v_h` are the unknown hidden-node voltages

Electrode currents are recovered from

```
    I_k = Σ_{(i,k)} G_c,k (V_drive,k − v_i)
```

where the sum is over hidden nodes `i` coupled to electrode `k`.

We use `scipy.sparse.linalg.spsolve`. SPD-ness is guaranteed because the
diagonal of `A` strictly dominates each row (every edge is shared by two
nodes, every contact injects strictly positive conductance on the diagonal).
The matrix is built once and reused across evaluations; only `b` changes
when the electrode pattern changes. A cached Cholesky-style factor is
*not* used in 0.1.0 because material sizes are small.

## Nonlinear material model

Edges have voltage-dependent conductance

```
    G_e(V_e) = G0_e · (1 + α · V_e²)
```

where `V_e = v_j − v_i`, `G0_e > 0` is the linear reference conductance,
and `α ≥ 0` is the nonlinearity coefficient. This is a hypothetical
**computational material model**. It is *not* a model of ordinary
geological rock. It is deliberately mild so the system is well-conditioned
and converges cleanly.

Solver (Picard / fixed-point iteration):

1. Start with the linear solution at the current electrode pattern.
2. Recompute each edge conductance using the current `V_e`.
3. Rebuild `A` and `b`, solve.
4. Repeat until `‖v_h^{(t+1)} − v_h^{(t)}‖_∞ < tol` or max iterations.
5. On non-convergence, raise `SolverDidNotConverge` and *do not* fabricate a
   result.

The nonlinear material can support XOR in principle because its I–V curve
is non-monotonic in the local sense (conductance rises with |V|, so paths
with high bias pull disproportionately). The architecture project needs
this nonlinearity to realistically harbour Boolean computation — a purely
linear network cannot encode XOR across a single physical output node
without external thresholding magic.

## Common assumptions

- All conductances are real-valued, positive, finite.
- No floating nodes.
- Electrode contact conductances are fixed and known to the solver but
  *not* to the harvester.
- Defects (in the damage experiment) are modelled as edge conductance set
  to zero. The defect map is hidden.
- The simulation is quasi-static: no time constants, no wave behaviour.
