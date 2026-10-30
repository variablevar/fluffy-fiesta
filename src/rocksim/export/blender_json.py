"""Blender-friendly JSON export for researcher visualisation.

This module is the single source of truth for the on-disk contract
that a future Blender importer will consume. The contract has three
sub-views:

  1. `pristine`   — the material at the moment XOR was discovered.
  2. `damaged`    — the same material after a fraction of internal
                    edges have been cut.
  3. `recovered`  — the same material after the harvester has
                    discovered a new XOR configuration.

Each sub-view contains:

  - the internal mesh (nodes + edges)
  - researcher-only edge currents, edge power, edge voltage drop
  - hidden node voltages
  - electrodes with explicit roles ("A" / "B" / "OUTPUT" / "BIAS" /
    "UNUSED")
  - damaged edges (subset of edges)
  - the analog truth table that the discovered candidate produces

This file is intended to be human-readable; a Blender importer is
out of scope. The harvester pipeline must never consume it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np

from rocksim.config import __version__ as ROCKSIM_VERSION
from rocksim.material.graph import Material
from rocksim.physics.solver import solve_with_internal_state


ROLE_A = "A"
ROLE_B = "B"
ROLE_OUTPUT = "OUTPUT"
ROLE_BIAS = "BIAS"
ROLE_UNUSED = "UNUSED"

VALID_ROLES = {ROLE_A, ROLE_B, ROLE_OUTPUT, ROLE_BIAS, ROLE_UNUSED}


@dataclass
class BlenderExportOptions:
    """Controls what gets serialised to the Blender JSON."""

    include_node_voltages: bool = True
    include_edge_currents: bool = True
    include_edge_powers: bool = True
    include_edge_drops: bool = True
    include_damaged_edges: bool = True
    extra_metadata: dict = field(default_factory=dict)


@dataclass
class StateSnapshot:
    """One snapshot of the material under a particular drive pattern."""

    drive_pattern: dict[int, float]
    analog_outputs: dict[int, float]
    analog_truth_table: list[dict]
    internal_state: dict
    electrode_roles: dict[int, str] = field(default_factory=dict)


@dataclass
class BlenderExport:
    """Top-level researcher export."""

    version: str
    rocksim_version: str
    metadata: dict
    pristine: dict
    damaged: dict | None
    recovered: dict | None


def _default_drive(material: Material) -> dict[int, float]:
    """Drive every electrode at 0 V (trivial solution)."""
    return {e.electrode_id: 0.0 for e in material.electrodes}


def _roles_from_candidate(candidate: Mapping | None) -> dict[int, str]:
    """Build a {electrode_id -> role} map from a candidate dict."""
    if not candidate:
        return {}
    out: dict[int, str] = {}
    for k in ("input_a", "input_b", "output"):
        v = candidate.get(k)
        if v is None:
            continue
        try:
            eid = int(v)
        except (TypeError, ValueError):
            continue
        out[eid] = (
            ROLE_A if k == "input_a"
            else ROLE_B if k == "input_b"
            else ROLE_OUTPUT
        )
    for k in (candidate.get("biases") or {}).keys():
        try:
            out[int(k)] = ROLE_BIAS
        except (TypeError, ValueError):
            pass
    return out


def _material_state_dict(
    material: Material,
    drive: dict[int, float],
    damaged_edges: set[tuple[int, int]] | None,
    roles: dict[int, str],
    analog_outputs: dict[int, float] | None = None,
    analog_truth_table: list[dict] | None = None,
    options: BlenderExportOptions | None = None,
) -> dict:
    """Render one state snapshot (pristine / damaged / recovered)."""
    options = options or BlenderExportOptions()
    internal = solve_with_internal_state(material, drive)
    coords = np.asarray(material.coordinates)

    edges_payload: list[dict] = []
    drops_by_index = {
        e["edge_index"]: e for e in internal["edge_drops"]
    }
    cur_by_index = {
        e["edge_index"]: e for e in internal["edge_currents"]
    }
    pow_by_index = {
        e["edge_index"]: e for e in internal["edge_powers"]
    }
    for idx, (u, v, element) in enumerate(material.edges):
        entry: dict = {
            "edge_index": int(idx),
            "u": int(u),
            "v": int(v),
            "g0": float(element.conductance(0.0)),
            "model": type(element).__name__,
        }
        if options.include_damaged_edges and damaged_edges is not None:
            key = (int(u), int(v)) if u < v else (int(v), int(u))
            entry["damaged"] = key in damaged_edges
        if options.include_edge_drops:
            d = drops_by_index.get(idx, {})
            entry["voltage_drop_V"] = d.get("voltage_drop_V", 0.0)
        if options.include_edge_currents:
            c = cur_by_index.get(idx, {})
            entry["current_A_u_to_v"] = c.get("direction_u_to_v", 0.0)
        if options.include_edge_powers:
            p = pow_by_index.get(idx, {})
            entry["power_W"] = p.get("power_W", 0.0)
        edges_payload.append(entry)

    electrodes_payload: list[dict] = []
    for e in material.electrodes:
        electrodes_payload.append(
            {
                "electrode_id": int(e.electrode_id),
                "role": roles.get(int(e.electrode_id), ROLE_UNUSED),
                "drive_V": float(drive.get(e.electrode_id, 0.0)),
                "measured_V": float(
                    internal["electrode_voltages"].get(
                        e.electrode_id, 0.0,
                    )
                ),
                "attached_hidden_nodes": list(e.attached_nodes),
                "contact_conductance": float(e.contact_conductance),
            }
        )

    nodes_payload: list[dict] = []
    v_h = internal["hidden_node_voltages"]
    for i in range(coords.shape[0]):
        entry = {
            "id": int(i),
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "z": float(coords[i, 2]),
        }
        if options.include_node_voltages:
            entry["voltage_V"] = float(v_h[i])
        nodes_payload.append(entry)

    out: dict = {
        "model_name": material.model_name,
        "n_hidden_nodes": int(material.n_hidden_nodes()),
        "n_hidden_edges": int(material.n_hidden_edges()),
        "n_electrodes": int(material.n_electrodes()),
        "drive_pattern": {
            int(k): float(v) for k, v in drive.items()
        },
        "electrode_voltages": {
            int(k): float(v) for k, v in internal[
                "electrode_voltages"
            ].items()
        },
        "edges": edges_payload,
        "hidden_nodes": nodes_payload,
        "electrodes": electrodes_payload,
    }
    if analog_outputs is not None:
        out["analog_outputs"] = {
            int(k): float(v) for k, v in analog_outputs.items()
        }
    if analog_truth_table is not None:
        out["analog_truth_table"] = analog_truth_table
    return out


def _recovered_drive(
    recovered_candidate: dict,
    original_drive: dict[int, float],
) -> dict[int, float]:
    """Reconstruct a full drive pattern from a recovered candidate.

    The recovered candidate contains the new A/B/OUT ids and a biases
    dict; we combine those with `original_drive` to produce a consistent
    drive snapshot.
    """
    drive = dict(original_drive)
    for k, v in (recovered_candidate.get("biases") or {}).items():
        try:
            drive[int(k)] = float(v)
        except (TypeError, ValueError):
            pass
    return drive


def export_researcher_ground_truth(
    material: Material,
    drive: dict[int, float] | None = None,
    candidate: dict | None = None,
    damaged_edges: set[tuple[int, int]] | None = None,
    damaged_material: Material | None = None,
    recovered_candidate: dict | None = None,
    recovered_material: Material | None = None,
    options: BlenderExportOptions | None = None,
) -> BlenderExport:
    """Build a researcher-only export for the pristine material and
    optionally its damaged and recovered states.

    The contract is:

        pristine:  visible internal state of `material` at `drive`
                   with the candidate's electrode roles annotated.
        damaged:   visible internal state of `damaged_material` (if
                   provided) at the same `drive`. Only present if the
                   caller supplies it.
        recovered: visible internal state of `recovered_material` (if
                   provided) at the recovered drive pattern. Only
                   present if the caller supplies it.

    The export is researcher-only. The harvester cannot reach it
    through `MaterialInterface`.
    """
    options = options or BlenderExportOptions()
    drive = drive or _default_drive(material)
    roles = _roles_from_candidate(candidate)
    pristine = _material_state_dict(
        material=material,
        drive=drive,
        damaged_edges=None,
        roles=roles,
        options=options,
    )

    damaged_block = None
    if damaged_material is not None:
        damaged_block = _material_state_dict(
            material=damaged_material,
            drive=drive,
            damaged_edges=damaged_edges,
            roles=roles,
            options=options,
        )

    recovered_block = None
    if recovered_material is not None and recovered_candidate is not None:
        recovered_roles = _roles_from_candidate(recovered_candidate)
        recovered_drive = _recovered_drive(recovered_candidate, drive)
        recovered_block = _material_state_dict(
            material=recovered_material,
            drive=recovered_drive,
            damaged_edges=damaged_edges,
            roles=recovered_roles,
            options=options,
        )

    metadata = {
        "version": "0.2.0",
        "rocksim_version": ROCKSIM_VERSION,
        "n_damaged_edges": (
            int(len(damaged_edges)) if damaged_edges is not None else 0
        ),
        "warning": (
            "RESEARCHER-ONLY. Includes hidden mesh + internal voltages, "
            "currents, and power. Never consume from the harvester."
        ),
    }
    if options.extra_metadata:
        metadata.update(options.extra_metadata)

    return BlenderExport(
        version="0.2.0",
        rocksim_version=ROCKSIM_VERSION,
        metadata=metadata,
        pristine=pristine,
        damaged=damaged_block,
        recovered=recovered_block,
    )


def write_blender_json(
    export: BlenderExport,
    output_path: str,
) -> str:
    """Write the export to JSON. Returns the absolute path written."""
    payload = {
        "version": export.version,
        "rocksim_version": export.rocksim_version,
        "metadata": export.metadata,
        "pristine": export.pristine,
        "damaged": export.damaged,
        "recovered": export.recovered,
    }
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return output_path


__all__ = [
    "BlenderExportOptions",
    "BlenderExport",
    "StateSnapshot",
    "export_researcher_ground_truth",
    "write_blender_json",
    "ROLE_A",
    "ROLE_B",
    "ROLE_OUTPUT",
    "ROLE_BIAS",
    "ROLE_UNUSED",
]
