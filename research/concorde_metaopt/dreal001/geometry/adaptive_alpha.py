
"""Target-lift driven adaptive angle-of-attack search (Issue #14 P0 / A1).

The module is deliberately solver-agnostic: the caller injects an evaluate
callback that performs one *real* VSPAERO alpha case and returns an
AlphaEvaluation.  Nothing in this module launches a solver or invents raw
points, so it is safe to unit test with synthetic curves and to replay
existing raw polar rows without new physical starts.

Contract highlights (docs/planning/dreal004_alpha_adaptive_and_meta_sampling_20261121.md):
  * a label may only be RAW_POINT_MATCHED when a *really evaluated* alpha point
    satisfies abs(CL - CL_target)/CL_target <= tol_cl;
  * interpolation is reported separately as INTERPOLATED_TARGET_ESTIMATE and is
    never mixed with raw labels;
  * every probe is counted as one internal solver case;
  * unbracketed, non-monotone, failed and budget-exhausted searches return an
    explicit NULL reason instead of extrapolating.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable, Optional, Sequence

RAW_POINT_MATCHED = "RAW_POINT_MATCHED"
INTERPOLATED_TARGET_ESTIMATE = "INTERPOLATED_TARGET_ESTIMATE"
NO_BRACKET = "NO_BRACKET"
NO_CONVERGENCE = "NO_CONVERGENCE"
INVALID_POLAR = "INVALID_POLAR"
SOLVER_FAILED = "SOLVER_FAILED"
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


def relative_cl_error(cl: float, cl_target: float) -> float:
    """Relative lift error used by the strict admission contract."""
    if not math.isfinite(cl) or not math.isfinite(cl_target) or cl_target <= 0.0:
        return math.inf
    return abs(cl - cl_target) / cl_target


@dataclass(frozen=True)
class AlphaEvaluation:
    alpha_deg: float
    cl: Optional[float]
    cdi: Optional[float] = None
    ok: bool = True
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.ok:
            if self.cl is None or not math.isfinite(self.cl):
                raise ValueError("successful evaluation requires finite cl")
        elif self.cl is not None:
            raise ValueError("failed evaluation must not carry cl")


@dataclass(frozen=True)
class AdaptiveAlphaSpec:
    cl_target: float
    tol_cl: float = 1e-3
    coarse_alphas: tuple[float, ...] = (4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0)
    max_solver_cases: int = 24
    max_refine_steps: int = 8
    min_alpha_deg: float = 2.0
    max_alpha_deg: float = 12.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.cl_target) or self.cl_target <= 0.0:
            raise ValueError("cl_target must be finite and positive")
        if not (0.0 < self.tol_cl < 1.0):
            raise ValueError("tol_cl must be in (0, 1)")
        if len(self.coarse_alphas) < 3:
            raise ValueError("coarse scan needs at least three alphas")
        if len(set(self.coarse_alphas)) != len(self.coarse_alphas):
            raise ValueError("coarse alphas must be unique")
        if any(not (self.min_alpha_deg <= a <= self.max_alpha_deg) for a in self.coarse_alphas):
            raise ValueError("coarse alphas must lie inside the search window")
        if self.max_solver_cases < len(self.coarse_alphas):
            raise ValueError("max_solver_cases cannot be smaller than the coarse scan")
        if self.max_refine_steps < 0:
            raise ValueError("max_refine_steps must be non-negative")


@dataclass
class AdaptiveAlphaResult:
    status: str
    cl_target: float
    tol_cl: float
    probes: list[AlphaEvaluation] = field(default_factory=list)
    matched: Optional[AlphaEvaluation] = None
    bracket: Optional[tuple[AlphaEvaluation, AlphaEvaluation]] = None
    estimate_alpha_deg: Optional[float] = None
    estimate_cl: Optional[float] = None
    best: Optional[AlphaEvaluation] = None
    reasons: list[str] = field(default_factory=list)

    @property
    def solver_cases(self) -> int:
        return len(self.probes)

    @property
    def raw_labelled(self) -> bool:
        return self.status == RAW_POINT_MATCHED

    def to_dict(self) -> dict:
        def ev(item: Optional[AlphaEvaluation]) -> Optional[dict]:
            if item is None:
                return None
            return {"alpha_deg": item.alpha_deg, "cl": item.cl, "cdi": item.cdi,
                    "ok": item.ok, "reason": item.reason}

        return {
            "status": self.status,
            "cl_target": self.cl_target,
            "tol_cl": self.tol_cl,
            "solver_cases": self.solver_cases,
            "raw_labelled": self.raw_labelled,
            "matched": ev(self.matched),
            "bracket": [ev(self.bracket[0]), ev(self.bracket[1])] if self.bracket else None,
            "estimate": {"alpha_deg": self.estimate_alpha_deg, "cl": self.estimate_cl}
            if self.estimate_alpha_deg is not None else None,
            "best": ev(self.best),
            "reasons": list(self.reasons),
            "probes": [ev(p) for p in self.probes],
        }


def _interpolate(a: AlphaEvaluation, b: AlphaEvaluation,
                 cl_target: float) -> tuple[float, float]:
    """Secant alpha estimate from two successful, bracketing evaluations."""
    slope = (b.cl - a.cl) / (b.alpha_deg - a.alpha_deg)
    alpha = a.alpha_deg + (cl_target - a.cl) / slope
    cl = a.cl + (alpha - a.alpha_deg) * slope
    return alpha, cl


class AdaptiveAlphaSolver:
    """Minimal-cost alpha search that only trusts real evaluated points."""

    def __init__(self, spec: AdaptiveAlphaSpec) -> None:
        self.spec = spec

    def run(self, evaluate: Callable[[float], AlphaEvaluation]) -> AdaptiveAlphaResult:
        spec = self.spec
        result = AdaptiveAlphaResult(status=NO_BRACKET, cl_target=spec.cl_target,
                                     tol_cl=spec.tol_cl)
        seen: dict[float, AlphaEvaluation] = {}

        def probe(alpha: float) -> AlphaEvaluation:
            key = round(float(alpha), 12)
            if key in seen:
                return seen[key]
            if len(result.probes) >= spec.max_solver_cases:
                raise _BudgetExhausted()
            if not (spec.min_alpha_deg - 1e-12 <= key <= spec.max_alpha_deg + 1e-12):
                raise _OutOfWindow()
            ev = evaluate(key)
            if ev.alpha_deg != key:
                raise ValueError("evaluator returned a different alpha than requested")
            result.probes.append(ev)
            seen[key] = ev
            return ev

        def match(ev: AlphaEvaluation) -> bool:
            return ev.ok and relative_cl_error(ev.cl, spec.cl_target) <= spec.tol_cl

        def track_best() -> None:
            for ev in result.probes:
                if not ev.ok or ev.cl is None:
                    continue
                if (result.best is None
                        or relative_cl_error(ev.cl, spec.cl_target)
                        < relative_cl_error(result.best.cl, spec.cl_target)):
                    result.best = ev

        try:
            coarse: list[AlphaEvaluation] = []
            for alpha in spec.coarse_alphas:
                ev = probe(alpha)
                coarse.append(ev)
                if match(ev):
                    result.matched = ev
                    result.status = RAW_POINT_MATCHED
                    track_best()
                    return result
            track_best()
            ok = [ev for ev in coarse if ev.ok]
            if len(ok) < 2:
                result.reasons.append("fewer than two successful coarse evaluations")
                result.status = SOLVER_FAILED
                return result

            # Locate every consecutive pair that brackets the target and is
            # locally increasing; a non-monotone stretch is never interpolated.
            candidates: list[tuple[AlphaEvaluation, AlphaEvaluation]] = []
            for left, right in zip(ok[:-1], ok[1:]):
                if right.cl > left.cl and left.cl <= spec.cl_target <= right.cl:
                    candidates.append((left, right))
            if not candidates:
                result.reasons.append("no monotone coarse bracket around cl_target")
                result.status = NO_BRACKET
                return result
            bracket = candidates[0]
            result.bracket = bracket

            for _ in range(spec.max_refine_steps):
                left, right = bracket
                guess, _estimate_cl = _interpolate(left, right, spec.cl_target)
                midpoint = 0.5 * (left.alpha_deg + right.alpha_deg)
                in_bracket = left.alpha_deg < guess < right.alpha_deg
                alpha = guess if in_bracket else midpoint
                if abs(right.alpha_deg - left.alpha_deg) <= 1e-9:
                    break
                ev = probe(alpha)
                if not ev.ok:
                    result.reasons.append("refinement solver failure at alpha=%.9f" % alpha)
                    result.bracket = bracket
                    continue
                if match(ev):
                    result.matched = ev
                    result.status = RAW_POINT_MATCHED
                    track_best()
                    return result
                if ev.cl < spec.cl_target:
                    if ev.cl <= left.cl:
                        result.reasons.append("non-monotone refinement point; stopping")
                        result.status = INVALID_POLAR
                        return result
                    bracket = (ev, right)
                else:
                    if ev.cl >= right.cl:
                        result.reasons.append("non-monotone refinement point; stopping")
                        result.status = INVALID_POLAR
                        return result
                    bracket = (left, ev)
                result.bracket = bracket
            track_best()

            left, right = result.bracket
            guess, estimate_cl = _interpolate(left, right, spec.cl_target)
            result.estimate_alpha_deg = guess
            result.estimate_cl = estimate_cl
            result.reasons.append(
                "no real point within tol_cl; best real relative error is %.6g"
                % (relative_cl_error(result.best.cl, spec.cl_target) if result.best else math.inf))
            result.status = NO_CONVERGENCE
            return result
        except _BudgetExhausted:
            track_best()
            result.reasons.append("max_solver_cases=%d exhausted" % spec.max_solver_cases)
            result.status = BUDGET_EXHAUSTED
            return result
        except _OutOfWindow:
            track_best()
            result.reasons.append("search reached the alpha window boundary")
            result.status = NO_BRACKET
            return result
        finally:
            result.probes = sorted(result.probes, key=lambda ev: ev.alpha_deg)


class _BudgetExhausted(RuntimeError):
    pass


class _OutOfWindow(RuntimeError):
    pass


def coarse_sweep_cost(spec: AdaptiveAlphaSpec) -> int:
    """Internal solver cases a fixed sweep with the same grid would charge."""
    return len(spec.coarse_alphas)


def replay_on_existing_rows(alphas: Sequence[float], cl_values: Sequence[float],
                            spec: AdaptiveAlphaSpec) -> AdaptiveAlphaResult:
    """Replay alpha *selection* on already existing real polar rows only.

    No new physical point is created: the callback can only return rows that
    the original fixed sweep already evaluated.  A requested alpha that is not
    one of the recorded rows fails closed, so the replay cannot fabricate a
    refined real solve.
    """
    rows = {round(float(a), 12): float(c) for a, c in zip(alphas, cl_values)}
    if len(rows) != len(alphas):
        raise ValueError("duplicate alpha rows in replay input")

    def evaluate(alpha: float) -> AlphaEvaluation:
        value = rows.get(round(float(alpha), 12))
        if value is None:
            return AlphaEvaluation(alpha_deg=alpha, cl=None, ok=False,
                                   reason="REPLAY_ROW_NOT_AVAILABLE")
        return AlphaEvaluation(alpha_deg=alpha, cl=value, ok=True)

    return AdaptiveAlphaSolver(spec).run(evaluate)
