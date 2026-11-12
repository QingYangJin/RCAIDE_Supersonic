"""Design-space helpers: normalisation, Sref(x), geometric constraints."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

import numpy as np

from .constants import DIMENSION


def as_unit_vector(x12: Sequence[float]) -> np.ndarray:
    vector = np.asarray(x12, dtype=float).reshape(-1)
    if vector.size != DIMENSION:
        raise ValueError("x12 must have %d entries, got %d" % (DIMENSION, vector.size))
    if not np.all(np.isfinite(vector)):
        raise ValueError("x12 contains non-finite values")
    return vector


def clip_x12(x12: Sequence[float]) -> np.ndarray:
    return np.clip(as_unit_vector(x12), 0.0, 1.0)


def validate_x12(design_space: Any, x12: Sequence[float]) -> List[str]:
    """Bounds + geometry-model checks. Returns list of human-readable issues.

    The design_space geometry model is authoritative; a violation is INVALID and
    must consume zero solver starts.
    """
    vector = as_unit_vector(x12)
    issues: List[str] = []
    if np.any(vector < -1e-9) or np.any(vector > 1.0 + 1e-9):
        issues.append("unit_bounds")
        return issues
    clipped = np.clip(vector, 0.0, 1.0)
    try:
        physical = design_space.from_unit_interval([float(value) for value in clipped])
    except Exception as exc:  # noqa: BLE001 - geometry model validation is authoritative
        return ["physical_conversion_error: %s" % (exc,)]
    try:
        physical_issues = list(design_space.check_physical(physical))
    except Exception as exc:  # noqa: BLE001
        return ["physical_check_error: %s" % (exc,)]
    issues.extend(str(item) for item in physical_issues)
    return issues


def sref_from_physical(physical: Mapping[str, float], *, name: str = "wing_area") -> float:
    value = float(physical[name])
    if not (value > 0.0):
        raise ValueError("reference area must be positive, got %r" % (value,))
    return value


def sref_from_x12(design_space: Any, x12: Sequence[float], *, name: str = "wing_area") -> float:
    physical = design_space.from_unit_interval([float(value) for value in np.clip(as_unit_vector(x12), 0.0, 1.0)])
    return sref_from_physical(physical, name=name)


def geometric_constraint_g(design_space: Any, x12: Sequence[float]) -> Dict[str, float]:
    """Design-rule constraints as g <= 0 (informational; check_physical is authoritative)."""
    physical = design_space.from_unit_interval(
        [float(value) for value in np.clip(as_unit_vector(x12), 0.0, 1.0)]
    )
    values = {str(key): float(value) for key, value in physical.items()}
    g: Dict[str, float] = {}
    if "span_location_2" in values and "span_location_3" in values:
        g["C01_span_location_order"] = values["span_location_2"] - values["span_location_3"]
    return g


def constraint_violation_total(g: Mapping[str, float]) -> float:
    total = 0.0
    for value in g.values():
        number = float(value)
        if number > 0.0:
            total += number
    return total
