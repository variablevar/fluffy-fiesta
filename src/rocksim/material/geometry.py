"""Irregular 3-D point-cloud generator.

Generates points inside a roughly rock-shaped volume. The shape is the
union of several jittered ellipsoids around a centre; this breaks the
sphere symmetry so electrodes end up distributed over a realistic
silhouette.

The generator never touches the harvester. All output is consumed only
by `material.graph`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from rocksim.config import (
    DEFAULT_BOUNDING_RADIUS,
    DEFAULT_SHAPE_IRREGULARITY,
)


@dataclass(frozen=True)
class GeometryParams:
    """Tunable geometry parameters."""

    bounding_radius: float = DEFAULT_BOUNDING_RADIUS
    irregularity: float = DEFAULT_SHAPE_IRREGULARITY
    # Number of jittered ellipsoids used to form the rock volume.
    n_ellipsoids: int = 6
    # Seed for reproducibility.
    seed: int = 0


def _sample_ellipsoid_points(
    rng: np.random.Generator,
    n_ellipsoids: int,
    bounding_radius: float,
    irregularity: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate irregular ellipsoid centres and shape parameters."""
    centres = rng.uniform(
        low=-0.20 * bounding_radius,
        high=+0.20 * bounding_radius,
        size=(n_ellipsoids, 3),
    )
    # Aspect ratios between 0.6 and 1.4 — anisotropic, not pathological.
    aspects = rng.uniform(
        low=max(0.10, 1.0 - irregularity),
        high=1.0 + irregularity,
        size=(n_ellipsoids, 3),
    )
    return centres, aspects


def _inside_union_of_ellipsoids(
    points: np.ndarray,
    centres: np.ndarray,
    aspects: np.ndarray,
    bounding_radius: float,
) -> np.ndarray:
    """Return boolean mask of points inside the union of ellipsoids."""
    inside = np.zeros(points.shape[0], dtype=bool)
    for k in range(centres.shape[0]):
        c = centres[k]
        a = aspects[k] * bounding_radius
        d = points - c
        # Mahalanobis-like distance with anisotropic scaling.
        scaled = d / np.where(a > 0, a, bounding_radius)
        m = np.linalg.norm(scaled, axis=1)
        inside |= m <= 1.0
    return inside


def generate_coordinates(
    n_points: int,
    params: GeometryParams,
) -> np.ndarray:
    """Return an (n_points, 3) array of coordinates inside a rock-like
    volume.

    Rejection-sampled. Reproducible from `params.seed`.
    """
    if n_points <= 0:
        return np.empty((0, 3), dtype=float)
    rng = np.random.default_rng(params.seed)
    centres, aspects = _sample_ellipsoid_points(
        rng,
        params.n_ellipsoids,
        params.bounding_radius,
        params.irregularity,
    )

    # Bounding cube for rejection sampling.
    bound = params.bounding_radius * 1.05
    out: list[np.ndarray] = []
    attempts = 0
    while sum(p.shape[0] for p in out) < n_points and attempts < 200:
        needed = (n_points - sum(p.shape[0] for p in out)) * 2
        needed = max(needed, n_points)
        candidates = rng.uniform(low=-bound, high=bound, size=(needed, 3))
        mask = _inside_union_of_ellipsoids(
            candidates, centres, aspects, params.bounding_radius,
        )
        accepted = candidates[mask]
        if accepted.shape[0]:
            out.append(accepted)
        attempts += 1

    coords = (
        np.concatenate(out, axis=0)
        if out
        else np.empty((0, 3), dtype=float)
    )
    coords = coords[:n_points]
    if coords.shape[0] < n_points:
        # If rejection was too strict, top up with sphere-shell points so
        # we always return at least n_points. Better than crashing.
        topup = _top_up_with_shell(
            rng,
            n_points - coords.shape[0],
            params.bounding_radius,
        )
        coords = np.concatenate([coords, topup], axis=0)
    return coords[:n_points]


def _top_up_with_shell(
    rng: np.random.Generator,
    n_needed: int,
    bounding_radius: float,
) -> np.ndarray:
    if n_needed <= 0:
        return np.empty((0, 3), dtype=float)
    dirs = rng.normal(size=(n_needed, 3))
    norms = np.linalg.norm(dirs, axis=1, keepdims=True)
    norms = np.where(norms > 0, norms, 1.0)
    dirs = dirs / norms
    radii = rng.uniform(0.0, bounding_radius, size=(n_needed, 1))
    return (dirs * radii).astype(float)
