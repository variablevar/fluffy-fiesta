"""Black-box boundary tests.

The harvester MUST NOT see any internal material state. These tests
prove that structural separation by stress-testing the protocol with
realistic and adversarial probes.
"""

from __future__ import annotations

import pytest

from rocksim.config import SignalLevels
from rocksim.interface import (
    MaterialInterface,
    Measurement,
    build_blackbox,
)
from rocksim.interface.blackbox import BlackBoxMaterialWrapper
from rocksim.material.graph import MaterialBuildParams, build_material
from rocksim.physics.solver import build_solver


def _make_wrapper(n_hidden_nodes: int = 30):
    material = build_material(
        MaterialBuildParams(master_seed=42, n_hidden_nodes=n_hidden_nodes)
    )
    solver = build_solver(material)
    return build_blackbox(material, solver), material


def test_wrapper_satisfies_protocol():
    iface, _ = _make_wrapper()
    # The Protocol itself is not runtime-checkable in our build, so we
    # assert the concrete type. Documented as a known limitation; a
    # future version of the project may re-enable @runtime_checkable.
    assert isinstance(iface, BlackBoxMaterialWrapper)
    # And that the public surface is exactly the Protocol's surface.
    assert hasattr(iface, "evaluate")
    assert hasattr(iface, "electrode_count")
    assert hasattr(iface, "reset")
    assert hasattr(iface, "step")


def test_evaluate_returns_only_external_fields():
    iface, _ = _make_wrapper()
    m = iface.evaluate({0: 0.5})
    assert isinstance(m, Measurement)
    assert set(m.electrode_voltages.keys()) == set(range(32))
    assert set(m.electrode_currents.keys()) == set(range(32))
    # Public surface; no hidden graph.
    assert not hasattr(m, "hidden_nodes")
    assert not hasattr(m, "hidden_edges")
    assert not hasattr(m, "coordinates")


def test_attributes_not_in_protocol_raise_attribute_error():
    iface, _ = _make_wrapper()
    # Allowed names:
    assert iface.electrode_count == 32
    m = iface.evaluate({})
    assert isinstance(m, Measurement)

    # Anything else is hidden:
    for forbidden in [
        "_material", "_solver", "_electrode_count",
        "edges", "nodes", "coordinates", "graph",
        "snapshots", "snapshot_internal",
        "internal_state", "raw", "_internal",
    ]:
        with pytest.raises(AttributeError):
            getattr(iface, forbidden)


def test_cannot_assign_via_protocol():
    iface, _ = _make_wrapper()
    with pytest.raises(AttributeError):
        iface.electrode_count = 99  # type: ignore[misc]
    with pytest.raises(AttributeError):
        iface.hidden = True  # type: ignore[attr-defined]


def test_evaluate_with_no_drive_returns_zero_signal():
    iface, _ = _make_wrapper()
    m = iface.evaluate({})
    # No electrode is driven; voltages should be exactly 0.0 (no hidden
    # state, no leakage).
    for v in m.electrode_voltages.values():
        assert v == pytest.approx(0.0, abs=1e-9)


def test_signal_levels_round_trip():
    iface, _ = _make_wrapper(n_hidden_nodes=20)
    levels = SignalLevels()
    v_low = iface.evaluate({0: levels.low}).electrode_voltages[0]
    v_high = iface.evaluate({0: levels.high}).electrode_voltages[0]
    assert v_low == pytest.approx(0.0)
    assert v_high == pytest.approx(1.0)


def test_can_not_access_internal_via_dataclass_getattr():
    iface, _ = _make_wrapper()
    m = iface.evaluate({0: 0.5})
    # Even with strict attribute access on the Measurement dataclass,
    # there is no hidden graph field.
    with pytest.raises(AttributeError):
        m.coordinates  # type: ignore[attr-defined]


def test_harvester_cannot_obtain_internal_currents_or_powers():
    """The wrapper must NOT expose any internal-state dump.

    A researcher-side export path exists via
    `rocksim.physics.solver.solve_with_internal_state` and the Blender
    exporter. The harvester must never reach that path.
    """
    iface, _ = _make_wrapper()
    # The wrapper has no such methods.
    for forbidden in (
        "hidden_node_voltages", "edge_currents", "edge_powers",
        "edge_drops", "internal_state", "internal_voltages",
    ):
        with pytest.raises(AttributeError):
            getattr(iface, forbidden)
    # The Measurement is the only object returned; it has no currents
    # or powers at all.
    m = iface.evaluate({0: 1.0})
    for forbidden in (
        "hidden_node_voltages", "edge_currents", "edge_powers",
    ):
        assert not hasattr(m, forbidden)


def test_blender_export_cannot_be_reached_through_material_interface():
    """The Blender export module is researcher-only and must not be
    importable from `rocksim.interface` or `rocksim.material`.
    """
    import rocksim.interface
    for forbidden in ("BlenderExport", "export_researcher_ground_truth"):
        assert not hasattr(rocksim.interface, forbidden), (
            f"rocksim.interface leaked researcher-only symbol {forbidden!r}"
        )
    import rocksim.material
    for forbidden in ("BlenderExport", "export_researcher_ground_truth"):
        assert not hasattr(rocksim.material, forbidden), (
            f"rocksim.material leaked researcher-only symbol {forbidden!r}"
        )
