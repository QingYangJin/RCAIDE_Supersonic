"""Lift matching over a pre-registered alpha grid (governance v2 sec 12.5).

Adaptive alpha search is forbidden: the alpha lists are frozen in the TaskSpec /
preregistration, and matching is CL(alpha) interpolation. A single refine launch
with the pre-registered refine grid is allowed when the interpolation residual
exceeds the lift tolerance (max 2 launches per design).
"""
from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

import numpy as np

from .records import LiftMatchResult


def _bracket(alphas: np.ndarray, cl: np.ndarray, target: float) -> Optional[Tuple[int, int]]:
    order = np.argsort(alphas)
    sorted_cl = cl[order]
    for index in range(len(sorted_cl) - 1):
        low, high = sorted_cl[index], sorted_cl[index + 1]
        if (low - target) * (high - target) <= 0.0 and not np.isclose(low, high):
            return int(index), int(index + 1)
    return None


def interpolate_lift_match(
    samples: Sequence[Any],
    *,
    cl_target: float,
    lift_tol_rel: float,
    method: str = "linear_interpolation",
) -> LiftMatchResult:
    """Linearly interpolate CL / CDi / ... at the target lift."""
    usable = [item for item in samples if bool(getattr(item, "converged", True))]
    if len(usable) < 2:
        return LiftMatchResult(
            alpha_deg=None, cltot=None, cdi=None, cdtot=None, cdo=None, cm=None,
            lift_rel_error=None, converged=False,
            method=method + ":insufficient_samples", n_samples=len(usable),
        )
    alphas = np.asarray([float(item.alpha_deg) for item in usable], dtype=float)
    cls = np.asarray([float(item.cltot) for item in usable], dtype=float)
    if not np.all(np.isfinite(alphas)) or not np.all(np.isfinite(cls)):
        return LiftMatchResult(
            alpha_deg=None, cltot=None, cdi=None, cdtot=None, cdo=None, cm=None,
            lift_rel_error=None, converged=False, method=method + ":non_finite",
            n_samples=len(usable),
        )
    if not (np.min(cls) - 1e-12 <= cl_target <= np.max(cls) + 1e-12):
        return LiftMatchResult(
            alpha_deg=None, cltot=None, cdi=None, cdtot=None, cdo=None, cm=None,
            lift_rel_error=None, converged=False, method=method + ":target_outside_grid",
            n_samples=len(usable),
        )
    order = np.argsort(alphas)
    sorted_samples = [usable[int(index)] for index in order]
    bracket = _bracket(alphas, cls, cl_target)
    if bracket is None:
        return LiftMatchResult(
            alpha_deg=None, cltot=None, cdi=None, cdtot=None, cdo=None, cm=None,
            lift_rel_error=None, converged=False, method=method + ":no_bracket",
            n_samples=len(usable),
        )
    low, high = bracket
    sample_low = sorted_samples[low]
    sample_high = sorted_samples[high]
    cl_low, cl_high = float(sample_low.cltot), float(sample_high.cltot)
    weight = (cl_target - cl_low) / (cl_high - cl_low)
    alpha = float(sample_low.alpha_deg) + weight * (float(sample_high.alpha_deg) - float(sample_low.alpha_deg))

    def blend(name: str, default: float = 0.0) -> float:
        a = float(getattr(sample_low, name, default) or 0.0)
        b = float(getattr(sample_high, name, default) or 0.0)
        return float(a + weight * (b - a))

    cl_matched = float(cl_low + weight * (cl_high - cl_low))
    residual = abs(cl_matched - cl_target) / max(abs(cl_target), 1e-12)
    cm_low = tuple(float(v) for v in (getattr(sample_low, "cm", (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0)))
    cm_high = tuple(float(v) for v in (getattr(sample_high, "cm", (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0)))
    cm = tuple(a + weight * (b - a) for a, b in zip(cm_low, cm_high))
    return LiftMatchResult(
        alpha_deg=alpha,
        cltot=cl_matched,
        cdi=blend("cdi"),
        cdtot=blend("cdtot"),
        cdo=blend("cdo"),
        cm=cm,
        lift_rel_error=float(residual),
        converged=bool(residual <= float(lift_tol_rel)),
        method=method,
        n_samples=len(usable),
    )
