"""Internal hidden material graph: nodes, edges, electrodes.

This module is *World A*. The harvester must never see a `Material`
instance, or any of its attributes.

A `Material` aggregates:

- `coordinates`: hidden node positions in 3-D.
- `edges`: pairs of node indices, plus an `EdgeElement` model.
- `electrodes`: which subset of nodes each surface electrode is attached
  to, plus a contact conductance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from rocksim.config import (
    DEFAULT_CONTACT_CONDUCTANCE,
    DEFAULT_CONDUCTANCE_LOG_MEAN,
    DEFAULT_CONDUCTANCE_LOG_STD,
    DEFAULT_ELECTRODE_COUNT,
    DEFAULT_HIDDEN_NODES,
    DEFAULT_KNN,
)
from rocksim.material.elements import (
    EdgeElement,
    LinearEdge,
    NonlinearEdge,
)
from rocksim.material.geometry import GeometryParams, generate_coordinates


@dataclass
class ElectrodeAttachment:
    """Describes how one surface electrode connects to hidden nodes."""

    electrode_id: int
    # Hidden node indices this electrode is in contact with.
    attached_nodes: list[int] = field(default_factory=list)
    # Contact conductance in Siemens (per attached node).
    contact_conductance: float = DEFAULT_CONTACT_CONDUCTANCE

    def contact_conductances(self) -> list[float]:
        return [self.contact_conductance for _ in self.attached_nodes]


@dataclass
class Material:
    """The hidden 3-D network. World A only."""

    coordinates: np.ndarray
    edges: list[tuple[int, int, EdgeElement]]
    electrodes: list[ElectrodeAttachment]
    model_name: str
    params: dict

    def n_hidden_nodes(self) -> int:
        return int(self.coordinates.shape[0])

    def n_hidden_edges(self) -> int:
        return int(len(self.edges))

    def n_electrodes(self) -> int:
        return int(len(self.electrodes))

    def electrode_node_summary(self) -> list[dict]:
        """Compact electrode->node summary for researcher-side display."""
        return [
            {
                "electrode_id": att.electrode_id,
                "attached_hidden_nodes": list(att.attached_nodes),
            }
            for att in self.electrodes
        ]

    def snapshot_internal(self) -> dict:
        """Full internal state. RESEARCHER ONLY.

        Anything reading from this is being explicitly labelled as a
        researcher, not a harvester. Do not import this method from the
        harvest package.
        """
        return {
            "model_name": self.model_name,
            "coordinates": self.coordinates.tolist(),
            "edges": [
                (int(u), int(v), _serialise_element(e))
                for (u, v, e) in self.edges
            ],
            "electrodes": [
                {
                    "electrode_id": att.electrode_id,
                    "attached_nodes": list(att.attached_nodes),
                    "contact_conductance": float(att.contact_conductance),
                }
                for att in self.electrodes
            ],
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class MaterialBuildParams:
    """Hyperparameters for material generation."""

    master_seed: int = 0
    n_hidden_nodes: int = DEFAULT_HIDDEN_NODES
    electrode_count: int = DEFAULT_ELECTRODE_COUNT
    knn: int = DEFAULT_KNN
    conductance_log_mean: float = DEFAULT_CONDUCTANCE_LOG_MEAN
    conductance_log_std: float = DEFAULT_CONDUCTANCE_LOG_STD
    geometry: GeometryParams = field(default_factory=GeometryParams)
    contact_conductance: float = DEFAULT_CONTACT_CONDUCTANCE
    model_name: str = "linear"
    nonlinear_alpha: float = 1.0

    def as_params_dict(self) -> dict:
        """Serialise to a JSON-friendly dict for experiment records."""
        return {
            "master_seed": self.master_seed,
            "n_hidden_nodes": self.n_hidden_nodes,
            "electrode_count": self.electrode_count,
            "knn": self.knn,
            "conductance_log_mean": self.conductance_log_mean,
            "conductance_log_std": self.conductance_log_std,
            "model_name": self.model_name,
            "nonlinear_alpha": self.nonlinear_alpha,
            "bounding_radius": self.geometry.bounding_radius,
            "irregularity": self.geometry.irregularity,
            "n_ellipsoids": self.geometry.n_ellipsoids,
            "contact_conductance": self.contact_conductance,
        }


def _neighbour_indices_by_knn(coords: np.ndarray, k: int) -> list[list[int]]:
    """Plain k-NN by Euclidean distance. O(n^2) -- fine for n <= a few thousand."""
    n = coords.shape[0]
    if n == 0:
        return []
    diffs = coords[:, None, :] - coords[None, :, :]
    d2 = np.sum(diffs * diffs, axis=-1)
    np.fill_diagonal(d2, np.inf)
    idx = np.argpartition(d2, kth=min(k, n - 1), axis=1)[:, :k]
    return [list(map(int, row)) for row in idx]


def _electrode_attachment(
    coords: np.ndarray,
    electrode_count: int,
    rng: np.random.Generator,
    contact_conductance: float,
    knn: int,
) -> list[ElectrodeAttachment]:
    """Place electrodes on/near the surface.

    Strategy: pick `electrode_count` Fibonacci-sphere directions; for
    each, find the hidden node whose coordinate has the largest
    projection onto that direction (a robust proxy for "on the
    surface"). Attach the electrode to that node plus, optionally, the
    nearest neighbour(s).

    The harvester never sees *which* node was picked for which electrode;
    the only thing exposed across the boundary is the electrode id.
    """
    if coords.shape[0] == 0:
        return [
            ElectrodeAttachment(
                electrode_id=k,
                attached_nodes=[],
                contact_conductance=contact_conductance,
            )
            for k in range(electrode_count)
        ]

    indices: list[int] = []
    if electrode_count == 1:
        norms = np.linalg.norm(coords, axis=1)
        indices = [int(np.argmax(norms))]
    else:
        golden = np.pi * (3.0 - np.sqrt(5.0))
        for k in range(electrode_count):
            y = 1.0 - (k / max(1, electrode_count - 1)) * 2.0
            r = np.sqrt(max(0.0, 1.0 - y * y))
            theta = golden * k
            dir_ = np.array([np.cos(theta) * r, y, np.sin(theta) * r])
            norms = coords @ dir_
            argmax = int(np.argmax(norms))
            indices.append(argmax)

    nbrs_cache = _neighbour_indices_by_knn(coords, knn)
    attachments = []
    for electrode_id, node_idx in enumerate(indices):
        attach = [int(node_idx)]
        extras = list(nbrs_cache[node_idx])
        extras = [n for n in extras if n != node_idx]
        attach.extend(extras[:2])
        attachments.append(
            ElectrodeAttachment(
                electrode_id=electrode_id,
                attached_nodes=attach,
                contact_conductance=contact_conductance,
            )
        )
    _ = rng  # reserved for future stochastic electrode jitter
    return attachments


def _edge_pair_key(u: int, v: int) -> tuple[int, int]:
    return (u, v) if u < v else (v, u)


def build_material(params: MaterialBuildParams) -> Material:
    """Build a deterministic hidden material given the parameters."""
    geom = GeometryParams(
        bounding_radius=params.geometry.bounding_radius,
        irregularity=params.geometry.irregularity,
        n_ellipsoids=params.geometry.n_ellipsoids,
        seed=params.master_seed,
    )
    coords = generate_coordinates(params.n_hidden_nodes, geom)

    nbrs = _neighbour_indices_by_knn(coords, params.knn)

    rng = np.random.default_rng(params.master_seed + 1)

    log_g = rng.normal(
        loc=params.conductance_log_mean,
        scale=params.conductance_log_std,
        size=coords.shape[0],
    )
    g_per_node = np.power(10.0, log_g)

    edges_set: set[tuple[int, int]] = set()
    edges: list[tuple[int, int, EdgeElement]] = []
    for u, neigh in enumerate(nbrs):
        for v in neigh:
            key = _edge_pair_key(u, v)
            if key in edges_set or key[0] == key[1]:
                continue
            edges_set.add(key)
            g_uv = float(np.sqrt(g_per_node[u] * g_per_node[v]))
            if params.model_name == "nonlinear":
                element: EdgeElement = NonlinearEdge(
                    g0=g_uv, alpha=params.nonlinear_alpha,
                )
            else:
                element = LinearEdge(g0=g_uv)
            edges.append((key[0], key[1], element))

    electrodes = _electrode_attachment(
        coords=coords,
        electrode_count=params.electrode_count,
        rng=rng,
        contact_conductance=params.contact_conductance,
        knn=params.knn,
    )

    return Material(
        coordinates=coords,
        edges=edges,
        electrodes=electrodes,
        model_name=params.model_name,
        params={
            "master_seed": params.master_seed,
            "n_hidden_nodes": params.n_hidden_nodes,
            "electrode_count": params.electrode_count,
            "knn": params.knn,
            "conductance_log_mean": params.conductance_log_mean,
            "conductance_log_std": params.conductance_log_std,
            "model_name": params.model_name,
            "nonlinear_alpha": params.nonlinear_alpha,
            "bounding_radius": params.geometry.bounding_radius,
            "irregularity": params.geometry.irregularity,
            "n_ellipsoids": params.geometry.n_ellipsoids,
            "contact_conductance": params.contact_conductance,
        },
    )


def edges_of(material: Material) -> Iterable[tuple[int, int, EdgeElement]]:
    return iter(material.edges)

