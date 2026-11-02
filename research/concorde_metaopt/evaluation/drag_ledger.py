"""Read-only, fail-closed accounting of RCAIDE drag coefficients at cruise end.

This is a *numerical ledger* for later LF/HF comparison, NOT a calibrated wing/
body interference model and NOT independent evidence of Mach-2 applicability.
Subcomponents such as wave.lift/volume are diagnostics included inside the
compressibility total, and must never be added twice.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Dict, Optional

_COMPONENTS = {
    "parasite": ("parasite", "total"),
    "induced": ("induced", "total"),
    "compressible": ("compressible", "total"),
    "miscellaneous": ("miscellaneous", "total"),
    "cooling": ("cooling", "total"),
    "trim": ("trim", "total"),
    "form": ("form", "total"),
    "increment": ("drag_coefficient_increment",),
}
_DIAGNOSTICS = {
    "wave_lift": ("compressible", "wave", "lift"),
    "wave_volume": ("compressible", "wave", "volume"),
}


def _field(root: Any, *parts: str) -> Any:
    value = root
    for part in parts:
        if isinstance(value, Mapping):
            if part not in value:
                return None
            value = value[part]
        else:
            value = getattr(value, part, None)
        if value is None:
            return None
    return value


def _finite_last(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        import numpy as np
        arr = np.asarray(value, dtype=float).reshape(-1)
        if not arr.size:
            return None
        x = float(arr[-1])
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def build_drag_ledger(
    conditions: Any,
    *,
    reference_area_m2: Optional[float] = None,
    trim_factor: Optional[float] = None,
) -> Dict[str, Any]:
    """Record available drag components without making unsupported assumptions.

    Dynamic pressure is sampled at the final cruise point; all dimensional
    component forces are positive *wind-axis drag magnitudes* in newtons.
    These are NOT signed body-axis X forces (an alpha transformation is needed).
    """
    area = _finite_last(reference_area_m2)
    if area is not None and area <= 0.0:
        area = None
    q = _finite_last(_field(conditions, "freestream", "dynamic_pressure"))
    if q is None:
        density = _finite_last(_field(conditions, "freestream", "density"))
        speed = _finite_last(_field(conditions, "freestream", "velocity"))
        if density is not None and speed is not None and density > 0 and speed > 0:
            q = 0.5 * density * speed * speed
    if q is not None and q <= 0.0:
        q = None

    drag = _field(conditions, "aerodynamics", "coefficients", "drag")
    total_cd = _finite_last(_field(drag, "total"))
    component_cd = {name: _finite_last(_field(drag, *path))
                    for name, path in _COMPONENTS.items()}
    diagnostic_cd = {name: _finite_last(_field(drag, *path))
                     for name, path in _DIAGNOSTICS.items()}
    missing = [name for name, value in component_cd.items() if value is None]
    scale = q * area if q is not None and area is not None else None
    forces_n = {name: (value * scale if value is not None and scale is not None else None)
                for name, value in component_cd.items()}
    factor = _finite_last(trim_factor)
    if factor is not None and factor <= 0.0:
        factor = None

    closure_cd = None
    if total_cd is not None and not missing and factor is not None:
        closure_cd = total_cd - factor * sum(component_cd.values())
    status = "ACCOUNTING_ONLY_UNVALIDATED" if (
        total_cd is not None and scale is not None and not missing and factor is not None
    ) else "PARTIAL_DATA_NOT_VALIDATED"
    return {
        "status": status,
        "model_validated": False,
        "body_interference_validated": False,
        "supersonic_validated": False,
        "reference_area_m2": area,
        "dynamic_pressure_pa": q,
        "trim_drag_factor": factor,
        "total_cd": total_cd,
        "total_drag_magnitude_n": total_cd * scale if total_cd is not None and scale is not None else None,
        "component_cd": component_cd,
        "component_drag_magnitude_n": forces_n,
        "diagnostic_subcomponents_cd_not_additive": diagnostic_cd,
        "missing_additive_components": missing,
        "numerical_closure_residual_cd": closure_cd,
        "numerical_closure_passed": (
            abs(closure_cd) <= 1e-8 if closure_cd is not None else None
        ),
        "axis_note": "positive wind-axis drag magnitude; not signed body-X force",
        "overlap_note": (
            "VLM Trefftz induced drag vs supersonic lift wave drag overlap is "
            "UNRESOLVED; numerical closure alone is NOT physical validation"
        ),
        "fuselage_note": (
            "Fixed fuselage has no independently calibrated, design-dependent "
            "body/wing interference correction: BODY-CORR is BLOCKED"
        ),
    }
