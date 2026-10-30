"""Project-wide configuration constants.

A single source of truth for signal levels, bias limits, default
geometries, default seeds, and version. Per-run overrides belong in
`config.json`, not in this module.
"""

from __future__ import annotations

from dataclasses import dataclass


# Public release identifier; also reported in experiment records.
__version__ = "0.2.0"


# Default Boolean signal levels (Volts) used to drive inputs A and B.
# These are configurable per experiment but the defaults are sane defaults
# for the XOR test.
LOW_VOLTAGE: float = 0.0
HIGH_VOLTAGE: float = 1.0

# Allowed range for control / bias voltages applied to non-input electrodes.
BIAS_LIMIT_ABS: float = 1.0

# Geometry defaults. Override via command-line flags or config files.
DEFAULT_HIDDEN_NODES: int = 500
DEFAULT_ELECTRODE_COUNT: int = 32

# Material graph generation defaults.
DEFAULT_KNN: int = 4                  # k-nearest neighbours per node
DEFAULT_CONDUCTANCE_LOG_MEAN: float = -3.0    # log10(S) mean
DEFAULT_CONDUCTANCE_LOG_STD: float = 0.7       # log10(S) std
DEFAULT_BOUNDING_RADIUS: float = 1.0           # approximate radius
DEFAULT_SHAPE_IRREGULARITY: float = 0.35       # 0 = sphere, 1 = rock-ish


# Electrode contact conductance (Siemens) from electrode terminal onto the
# nearest hidden node.
DEFAULT_CONTACT_CONDUCTANCE: float = 1.0


# Solver defaults.
LINEAR_TOL: float = 1e-9
NONLINEAR_TOL: float = 1e-9
NONLINEAR_MAX_ITER: int = 200


# XOR search defaults.
DEFAULT_XOR_OUTPUT_THRESHOLD: float = 0.5
DEFAULT_MIN_MARGIN: float = 0.05
DEFAULT_XOR_ITERATIONS: int = 10000
DEFAULT_SEARCH_STRATEGY: str = "hill_climb"


# Damage experiment.
DEFAULT_DAMAGE_FRACTION: float = 0.05


# Truth-table input combinations for XOR (A,B).
XOR_TRUTH_TABLE = (
    ((0, 0), 0),
    ((0, 1), 1),
    ((1, 0), 1),
    ((1, 1), 0),
)


# Result-status taxonomy used across all experiments. See CHANGELOG and
# docs/experiments.md for definitions. These are the ONLY allowed strings.
STATUS_SEARCH_SUCCESS = "SEARCH_SUCCESS"
STATUS_SEARCH_EXHAUSTED = "SEARCH_EXHAUSTED"
STATUS_SOLVER_FAILED = "SOLVER_FAILED"
STATUS_DISCOVERY_FAILED = "DISCOVERY_FAILED"
STATUS_SURVIVED_DAMAGE = "SURVIVED_DAMAGE"
STATUS_BROKEN_BY_DAMAGE = "BROKEN_BY_DAMAGE"
STATUS_RECOVERED = "RECOVERED"
STATUS_RECOVERY_FAILED = "RECOVERY_FAILED"



@dataclass(frozen=True)
class SignalLevels:
    """Voltage levels used to encode Boolean 0 / 1."""

    low: float = LOW_VOLTAGE
    high: float = HIGH_VOLTAGE

    def for_bit(self, bit: int) -> float:
        if bit not in (0, 1):
            raise ValueError(f"bit must be 0 or 1, got {bit!r}")
        return self.high if bit else self.low
