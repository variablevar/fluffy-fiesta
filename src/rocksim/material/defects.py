"""Hidden material defects.

Defects are modelled as edge cuts (set conductance to zero). They are
created *inside* the physics layer, never visible to the harvester.

`damage_material` is the one entry point used by the damage-recovery
experiment. It mutates the supplied `Material` in-place; the harvester
already holds only the public `MaterialInterface`, so this mutation is
invisible except through changed measurement responses.
"""

from __future__ import annotations

import numpy as np

from rocksim.material.elements import LinearEdge, NonlinearEdge
from rocksim.material.graph import Material


def damage_material(
    material: Material,
    fraction: float,
    seed: int,
) -> int:
    """Cut a fraction of internal edges at random.

    Returns the number of edges removed. Fraction is clamped to [0, 1].
    Defects are stored as a degenerate LinearEdge(0). The solver treats
    zero conductances as open circuits.
    """
    if fraction <= 0.0:
        return 0
    n_edges = len(material.edges)
    if n_edges == 0:
        return 0
    n_damage = int(round(max(0.0, min(1.0, fraction)) * n_edges))
    if n_damage == 0:
        return 0
    rng = np.random.default_rng(seed)
    chosen = rng.choice(n_edges, size=n_damage, replace=False)
    for idx in chosen:
        u, v, _ = material.edges[idx]
        g0 = 0.0  # open circuit
        # Replacement element type matches the model of the original edge.
        if material.model_name == "nonlinear":
            material.edges[idx] = (u, v, NonlinearEdge(g0=g0, alpha=0.0))
        else:
            material.edges[idx] = (u, v, LinearEdge(g0=g0))
    return int(n_damage)
