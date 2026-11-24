"""O0: the first real feedback-driven aerodynamic optimization (D-REAL-EXP-003).

Issue #15 requires a genuine ask -> new geometry -> real VSPAERO -> strict raw-row
admission -> tell loop, with every attempt (including failures) charged, and it
requires that a counterfactual feedback change the next candidate. This module
holds the protocol and the bookkeeping; the physical evaluator is injected so the
loop can be tested with synthetic evaluations and then run for real.

Design of one design evaluation (fixed by the pre-registration):

* the 12D vector is only free along the validated local subspace (sweep_1, sweep_2);
  every other variable keeps its frozen baseline value;
* locating the fixed-lift angle of attack takes exactly two charged solver starts:
  a 7-point coarse bracket (0.35 deg step spanning 2.1 deg, i.e. +-1.05 deg around the
  guessed centre) and a 13-point refinement (0.004 deg step spanning 0.048 deg, i.e.
  +-0.024 deg) centred on the coarse quadratic prediction;
  CAPS["max_starts_per_design"] is 2, so AttemptLedger.charge() makes a third start
  on the same design architecturally impossible rather than merely discouraged;
* a design that cannot place a *raw* polar row within the 1e-3 lift tolerance is
  recorded as a failure with objective None; tolerance is never relaxed and an
  interpolated row is never promoted to a raw row;
* both starts and all internal alpha cases are charged, including the ones spent
  on a design that ends in failure.

Nothing in this module starts a solver by itself.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

SCHEMA = "dreal005.o0_short_bo.v1"
PROTOCOL_ID = "O0-SHORT-BO-20261124"

# Fixed task: one Mach/altitude/lift target, so the objective is comparable across designs.
TASK = {
    "task_id": "O0-M202",
    "mach": 2.02,
    "altitude_m": 18288.0,
    "lift_target_n": 1333704.4,
    "lift_tolerance_rel": 1e-3,
    "dynamic_pressure_pa": 20483.940233430174,
    "dimensionless": "LIFTING_SURFACE_ONLY_INDUCED_DRAG",
}

# Frozen 12D layout (order is contractual; see h0_contract).
VARIABLE_ORDER: Tuple[str, ...] = (
    "wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3",
    "span_location_2", "span_location_3", "chord_ratio_2", "chord_ratio_3",
    "tip_twist", "vertical_tail_area", "vertical_tail_sweep_delta",
)
BASELINE_X12: Tuple[float, ...] = (
    358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0,
    33.91, 0.0,
)
FIXED_15: Dict[str, float] = {
    "fuselage_length": 61.66,
    "fuselage_fineness": 4.3,
    "fuselage_height_width_ratio": 1.152778,
}
PHYSICAL_15_NAMES: Tuple[str, ...] = VARIABLE_ORDER + (
    "fuselage_length", "fuselage_fineness", "fuselage_height_width_ratio")

# Local optimization box: sweep_1 +/- 1.5 deg, sweep_2 +/- 1.5 deg around the
# frozen baseline. Chosen from the measured response audit, not from arm results.
SUBSPACE_INDEX: Dict[str, int] = {"sweep_1": 2, "sweep_2": 3}
SUBSPACE_BOUNDS: Dict[str, Tuple[float, float]] = {
    "sweep_1": (65.5, 68.5),
    "sweep_2": (46.5, 49.5),
}
# The GP backend works in *physical* subspace coordinates (no [0,1] squash):
# lower/upper are the frozen sweep bounds and ask() returns sweep values directly.
SUBSPACE_LOWER: Tuple[float, ...] = tuple(SUBSPACE_BOUNDS[n][0] for n in ("sweep_1", "sweep_2"))
SUBSPACE_UPPER: Tuple[float, ...] = tuple(SUBSPACE_BOUNDS[n][1] for n in ("sweep_1", "sweep_2"))

# Alpha search: sized so the two starts together stay inside the 20-internal-case cap.
#
# The coarse start has to be wide enough to bracket the fixed-lift angle of attack
# for *any* design in the frozen subspace. Measured on the G2 M202 raw polars, the
# fixed-lift alpha moves from 5.13 to 5.35 deg inside the historical d00-d07 spread,
# i.e. about 0.33 deg of alpha per degree of sweep_1; the +/-1.5 deg box can thus
# move the target by roughly one degree. A +/-1.05 deg window over 7 points covers
# that; the refinement then only has to absorb the interpolation error of a nearly
# linear lift curve, so +/-0.024 deg at 0.004 deg resolution (a CL step of ~1.4e-4,
# below the 1.8e-4 CL tolerance band) is enough.
COARSE_ALPHA_OFFSETS: Tuple[float, ...] = (-1.05, -0.70, -0.35, 0.0, 0.35, 0.70, 1.05)
COARSE_ALPHA_GUESS_DEG = 5.18
REFINE_HALF_WIDTH_DEG = 0.024
REFINE_STEP_DEG = 0.004
ALPHA_WINDOW_DEG: Tuple[float, float] = (-2.0, 10.0)

# Cap semantics, stated once so the dossier and the code cannot diverge:
# * max_design_attempts, bootstrap_attempts, max_adaptive_attempts and
#   max_starts_per_design count *different designs* (bootstrap draws plus adaptive
#   draws). They never authorize re-solving one design to look for a better number.
# * max_starts_per_design is the exact cost of one design evaluation (one coarse
#   start plus one refinement start); charge() raises before a third start exists.
# * max_internal_per_design is the exact alpha budget of those two starts
#   (7 coarse + 13 refine = 20), so a design cannot buy a wider grid.
CAPS = {
    "max_design_attempts": 12,
    "max_solver_starts": 36,
    "max_internal_cases": 240,
    "max_starts_per_design": 2,
    "max_internal_per_design": 20,
    "max_adaptive_attempts": 8,
    "bootstrap_attempts": 4,
    # Waste bound: after this many consecutive designs that fail to admit a raw row, the
    # batch stops instead of spending the rest of the cap on a protocol that is not
    # landing rows. Three designs is 6 of the 36 authorized starts.
    "max_consecutive_unadmitted_designs": 3,
    "solver_timeout_s": 600,
    "wall_clock_s": 3300,
    "parallelism": 1,
    "retries": 0,
}


def assert_execution_contract() -> None:
    """Refuse to run unless the serial, no-retry execution contract still holds."""
    if CAPS["parallelism"] != 1:
        raise ProtocolError("O0 is authorized with parallelism 1 only")
    if CAPS["retries"] != 0:
        raise ProtocolError("O0 is authorized with zero retries only")
    if CAPS["max_starts_per_design"] != 2:
        raise ProtocolError("one design evaluation is exactly 2 charged starts")
    if not 2 <= CAPS["max_consecutive_unadmitted_designs"] <= CAPS["max_design_attempts"]:
        raise ProtocolError("the unadmitted-streak stop must bite before the design cap")
    plan = alpha_plan()
    if plan["starts_per_design_max"] != CAPS["max_starts_per_design"]:
        raise ProtocolError("alpha plan and CAPS disagree on starts per design")
    if plan["max_internal_cases_per_design"] != CAPS["max_internal_per_design"]:
        raise ProtocolError("alpha plan and CAPS disagree on internal cases per design")


class ProtocolError(RuntimeError):
    """Raised when the O0 protocol invariants would be violated."""


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha_bytes(text.encode("utf-8"))


def design_identity(x12: Sequence[float]) -> Dict[str, Any]:
    """Stable identity for a 12D design, independent of the optimizer."""
    from research.concorde_metaopt.dreal001.geometry.design_identity import design_hash

    vector = [float(value) for value in x12]
    if len(vector) != 12:
        raise ProtocolError("design vector must have 12 entries")
    return {"x12": vector,
            "geometry_sha256": canonical_sha(vector),
            "design_id": design_hash(vector),
            "is_baseline": all(abs(a - b) <= 0.0 for a, b in zip(vector, BASELINE_X12))}


def physical_15(x12: Sequence[float]) -> List[float]:
    vector = [float(value) for value in x12]
    if len(vector) != 12:
        raise ProtocolError("design vector must have 12 entries")
    return vector + [FIXED_15[name] for name in
                     ("fuselage_length", "fuselage_fineness", "fuselage_height_width_ratio")]


def subspace_to_design(point: Sequence[float]) -> List[float]:
    """Map a 2D (sweep_1, sweep_2) point to the frozen 12D vector."""
    if len(point) != 2:
        raise ProtocolError("subspace coordinate must have 2 entries")
    x12 = list(BASELINE_X12)
    for axis, name in enumerate(("sweep_1", "sweep_2")):
        value = float(point[axis])
        lower, upper = SUBSPACE_BOUNDS[name]
        if not lower - 1e-12 <= value <= upper + 1e-12:
            raise ProtocolError("subspace coordinate %r outside the frozen local box %r"
                                % (value, (lower, upper)))
        x12[SUBSPACE_INDEX[name]] = min(max(value, lower), upper)
    return x12


def design_to_subspace(x12: Sequence[float]) -> List[float]:
    """Extract the 2D optimization coordinate from a 12D design."""
    return [float(x12[SUBSPACE_INDEX[name]]) for name in ("sweep_1", "sweep_2")]


def check_design(x12: Sequence[float]) -> None:
    """Fail closed on anything outside the frozen contract."""
    point = design_to_subspace(x12)
    for axis, value in enumerate(point):
        lower, upper = (SUBSPACE_LOWER[axis], SUBSPACE_UPPER[axis])
        if not lower <= value <= upper:
            raise ProtocolError(
                "subspace coordinate %r outside the frozen local box" % (value,))
    for index, name in enumerate(VARIABLE_ORDER):
        if name in SUBSPACE_INDEX:
            continue
        if abs(float(x12[index]) - BASELINE_X12[index]) > 0.0:
            raise ProtocolError(
                "variable %s is frozen in the O0 subspace but moved to %r"
                % (name, x12[index]))


def coarse_alphas() -> List[float]:
    return [round(COARSE_ALPHA_GUESS_DEG + offset, 6) for offset in COARSE_ALPHA_OFFSETS]


def refine_alphas(center_deg: float) -> List[float]:
    count = int(round(2 * REFINE_HALF_WIDTH_DEG / REFINE_STEP_DEG)) + 1
    start = center_deg - REFINE_HALF_WIDTH_DEG
    return [round(start + index * REFINE_STEP_DEG, 6) for index in range(count)]


def alpha_plan() -> Dict[str, Any]:
    coarse = coarse_alphas()
    refine = refine_alphas(COARSE_ALPHA_GUESS_DEG)
    return {
        "coarse_alphas_deg": coarse,
        "coarse_internal_cases": len(coarse),
        "refine_half_width_deg": REFINE_HALF_WIDTH_DEG,
        "refine_step_deg": REFINE_STEP_DEG,
        "refine_internal_cases": len(refine),
        "max_internal_cases_per_design": len(coarse) + len(refine),
        "starts_per_design_max": 2,
        "alpha_window_deg": [-2.0, 10.0],
    }


def _linear_fit(rows: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    """Ordinary least squares of CL against alpha on the coarse bracket."""
    points = [(float(a), float(b)) for a, b in rows]
    if len(points) < 3:
        raise ProtocolError("alpha bracket needs at least 3 raw points")
    n = float(len(points))
    mean_a = sum(p[0] for p in points) / n
    mean_b = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mean_a) ** 2 for p in points)
    if sxx <= 0.0:
        raise ProtocolError("alpha bracket is degenerate")
    sxy = sum((p[0] - mean_a) * (p[1] - mean_b) for p in points)
    slope = sxy / sxx
    intercept = mean_b - slope * mean_a
    ss_tot = sum((p[1] - mean_b) ** 2 for p in points)
    ss_res = sum((p[1] - (slope * p[0] + intercept)) ** 2 for p in points)
    r2 = 1.0 if ss_tot <= 0.0 else max(0.0, 1.0 - ss_res / ss_tot)
    return {"slope_per_deg": slope, "intercept": intercept, "r2": r2, "n_points": len(points)}


def _quadratic_fit(rows: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    """Least squares of CL = a + b*alpha + c*alpha^2 on the coarse bracket."""
    points = [(float(a), float(b)) for a, b in rows]
    if len(points) < 5:
        raise ProtocolError("quadratic bracket needs at least 5 raw points")
    # Centre alpha so the normal equations stay well conditioned over 4..6 deg.
    centre = sum(p[0] for p in points) / len(points)
    centred = [(p[0] - centre, p[1]) for p in points]
    sx = [sum(x ** k for x, _ in centred) for k in range(5)]
    sy = [sum(y * x ** k for x, y in centred) for k in range(3)]
    matrix = [[sx[0], sx[1], sx[2]], [sx[1], sx[2], sx[3]], [sx[2], sx[3], sx[4]]]
    rhs = [sy[0], sy[1], sy[2]]
    # Gaussian elimination with partial pivoting on the 3x4 augmented matrix.
    augmented = [row[:] + [value] for row, value in zip(matrix, rhs)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda r: abs(augmented[r][column]))
        if abs(augmented[pivot][column]) <= 0.0:
            raise ProtocolError("quadratic bracket is degenerate")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column] / pivot_value
            for col in range(column, 4):
                augmented[row][col] -= factor * augmented[column][col]
    solved = [augmented[i][3] / augmented[i][i] for i in range(3)]
    a, b, c = solved
    ss_tot = sum((y - sy[0] / len(points)) ** 2 for _, y in centred)
    ss_res = sum((y - (a + b * x + c * x * x)) ** 2 for x, y in centred)
    r2 = 1.0 if ss_tot <= 0.0 else max(0.0, 1.0 - ss_res / ss_tot)
    return {"a": a, "b": b, "c": c, "centre": centre, "r2": r2,
            "n_points": len(points), "evaluate": True}


def _solve_quadratic_alpha(fit: Dict[str, Any], cl_target: float) -> Optional[float]:
    """Invert CL = a + b*u + c*u^2 (u = alpha - centre) for the branch near the guess."""
    a = fit["a"] - cl_target
    b = fit["b"]
    c = fit["c"]
    if abs(c) <= 1e-18:
        if abs(b) <= 0.0:
            return None
        return fit["centre"] - a / b
    discriminant = b * b - 4.0 * c * a
    if discriminant < 0.0:
        return None
    root = math.sqrt(discriminant)
    candidates = [(-b + root) / (2.0 * c), (-b - root) / (2.0 * c)]
    candidates = [fit["centre"] + u for u in candidates]
    inside = [value for value in candidates
              if ALPHA_WINDOW_DEG[0] <= value <= ALPHA_WINDOW_DEG[1]]
    if not inside:
        return None
    inside.sort(key=lambda value: abs(value - COARSE_ALPHA_GUESS_DEG))
    return inside[0]


def predict_alpha(rows: Sequence[Tuple[float, float]], cl_target: float,
                  min_r2: float = 0.99) -> Dict[str, Any]:
    """Locate the fixed-lift alpha from a coarse bracket; fail closed on curvature.

    A straight line through a 2.1 deg bracket carries a systematic +0.003 deg bias
    on the measured M202 polars (the lift curve is slightly convex there), which is a
    third of the refinement half-width. The bracket is therefore fitted with a
    quadratic when it has enough points, and the linear fit is kept as the fallback
    and as the reported sanity check.
    """
    slopes = []
    ordered = sorted(rows)
    for left, right in zip(ordered, ordered[1:]):
        if right[0] - left[0] <= 0.0:
            raise ProtocolError("duplicate alpha in the coarse bracket")
        slopes.append((right[1] - left[1]) / (right[0] - left[0]))
    if any(slope <= 0.0 for slope in slopes):
        return {"ok": False, "reason": "CL is not monotonically increasing in alpha",
                "monotone_slopes": slopes}
    fit = _linear_fit(rows)
    if fit["r2"] < min_r2:
        return {"ok": False, "reason": "coarse bracket is not linear (r2=%.6f)" % fit["r2"],
                "fit": fit}
    if fit["slope_per_deg"] <= 0.0:
        return {"ok": False, "reason": "non-positive CL slope", "fit": fit}
    linear_alpha = (cl_target - fit["intercept"]) / fit["slope_per_deg"]
    quad = None
    quad_alpha = None
    if len(ordered) >= 5:
        try:
            quad = _quadratic_fit(ordered)
        except ProtocolError:
            quad = None
        if quad is not None and quad["r2"] >= min_r2:
            quad_alpha = _solve_quadratic_alpha(quad, cl_target)
    if quad_alpha is not None:
        method = "QUADRATIC_BRACKET"
        alpha = quad_alpha
    else:
        method = "LINEAR_BRACKET"
        alpha = linear_alpha
    if not ALPHA_WINDOW_DEG[0] <= alpha <= ALPHA_WINDOW_DEG[1]:
        return {"ok": False, "reason": "predicted alpha %r outside the frozen window" % alpha,
                "fit": fit, "predicted_alpha_deg": alpha, "method": method}
    return {"ok": True, "predicted_alpha_deg": alpha, "fit": fit, "method": method,
            "linear_alpha_deg": linear_alpha,
            "quadratic_fit": ({k: quad[k] for k in ("a", "b", "c", "centre", "r2", "n_points")}
                              if quad is not None else None),
            "quadratic_alpha_deg": quad_alpha,
            "slope_per_deg": fit["slope_per_deg"]}


def cl_from_row(q_pa: float, sref_m2: float, cltot: float) -> float:
    """CL as reported by the polar row (the polar is already normalised)."""
    if not (q_pa > 0.0 and sref_m2 > 0.0):
        raise ProtocolError("q and Sref must be positive")
    return float(cltot)


def di_n_from_row(q_pa: float, sref_m2: float, cdi: float) -> float:
    return float(q_pa) * float(sref_m2) * float(cdi)


@dataclass
class AttemptRecord:
    """One charged design attempt, success or failure."""

    design_index: int
    stage: str  # BOOTSTRAP | ADAPTIVE
    x12: List[float]
    design_id: str
    geometry_sha256: str
    is_baseline: bool
    starts: int = 0
    internal: int = 0
    status: str = "PENDING"
    objective: Optional[float] = None  # Di_N
    feasible: bool = False
    di_n: Optional[float] = None
    cl: Optional[float] = None
    cdi: Optional[float] = None
    alpha_deg: Optional[float] = None
    sref_m2: Optional[float] = None
    q_pa: Optional[float] = None
    lift_rel_error: Optional[float] = None
    failure_kind: Optional[str] = None
    detail: str = ""
    case_ids: List[str] = field(default_factory=list)
    coarse: Optional[Dict[str, Any]] = None
    refine: Optional[Dict[str, Any]] = None
    acquisition: Optional[Dict[str, Any]] = None
    admission_id: Optional[str] = None
    audit_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        payload = dict(self.__dict__)
        payload["objective_n"] = self.objective
        return payload


class AttemptLedger:
    """Append-only charge ledger; the only writer of the run counters.

    The caps are per authorization, not per process. When an earlier batch under the
    same authorization already spent starts (O0-B01 spent one start and seven internal
    cases before it was aborted by a code defect), that spend is carried in through
    the priors below so the remaining budget is what is actually left - a restarted
    process must not be able to spend the full cap again.
    """

    def __init__(self, caps: Optional[Dict[str, int]] = None, *,
                 prior_design_attempts: int = 0, prior_starts: int = 0,
                 prior_internal: int = 0) -> None:
        self.caps = dict(CAPS if caps is None else caps)
        self.attempts: List[AttemptRecord] = []
        self.prior_design_attempts = int(prior_design_attempts)
        self.prior_starts = int(prior_starts)
        self.prior_internal = int(prior_internal)
        if self.prior_starts > self.caps["max_solver_starts"]:
            raise ProtocolError("carried-forward starts exceed the authorization")
        if self.prior_internal > self.caps["max_internal_cases"]:
            raise ProtocolError("carried-forward internal cases exceed the authorization")
        if self.prior_design_attempts > self.caps["max_design_attempts"]:
            raise ProtocolError("carried-forward design attempts exceed the authorization")
        self.starts_used = self.prior_starts
        self.internal_used = self.prior_internal

    # -- charging ------------------------------------------------------------
    def charge(self, attempt: AttemptRecord, *, starts: int, internal: int) -> None:
        if starts < 0 or internal < 0:
            raise ProtocolError("charges must be non-negative")
        if attempt.starts + starts > self.caps["max_starts_per_design"]:
            raise ProtocolError(
                "design %s would exceed %d starts (has %d, +%d)"
                % (attempt.design_id, self.caps["max_starts_per_design"],
                   attempt.starts, starts))
        if attempt.internal + internal > self.caps["max_internal_per_design"]:
            raise ProtocolError(
                "design %s would exceed %d internal cases (has %d, +%d)"
                % (attempt.design_id, self.caps["max_internal_per_design"],
                   attempt.internal, internal))
        if self.starts_used + starts > self.caps["max_solver_starts"]:
            raise ProtocolError("run would exceed %d solver starts"
                                % self.caps["max_solver_starts"])
        if self.internal_used + internal > self.caps["max_internal_cases"]:
            raise ProtocolError("run would exceed %d internal cases"
                                % self.caps["max_internal_cases"])
        attempt.starts += starts
        attempt.internal += internal
        self.starts_used += starts
        self.internal_used += internal

    def remaining(self) -> Dict[str, int]:
        return {
            "attempts": (self.caps["max_design_attempts"] - self.prior_design_attempts
                         - len(self.attempts)),
            "solver_starts": self.caps["max_solver_starts"] - self.starts_used,
            "internal_cases": self.caps["max_internal_cases"] - self.internal_used,
        }

    # -- bookkeeping ---------------------------------------------------------
    def settle(self, attempt: AttemptRecord) -> None:
        """Adopt the consumption an evaluator declared, through the caps.

        The evaluator reports what it actually spent; the ledger is the only
        writer of the run counters, so an over-spending evaluator raises instead
        of silently exceeding the pre-registered budget.
        """
        starts = int(attempt.starts)
        internal = int(attempt.internal)
        attempt.starts = 0
        attempt.internal = 0
        self.charge(attempt, starts=starts, internal=internal)

    def add(self, attempt: AttemptRecord) -> AttemptRecord:
        if len(self.attempts) + self.prior_design_attempts >= self.caps["max_design_attempts"]:
            raise ProtocolError("run would exceed %d design attempts"
                                % self.caps["max_design_attempts"])
        self.attempts.append(attempt)
        return attempt

    def summary(self) -> Dict[str, Any]:
        ok = [a for a in self.attempts if a.feasible]
        return {
            "design_attempts": len(self.attempts),
            "solver_starts_actual": self.starts_used,
            "internal_solver_cases_actual": self.internal_used,
            "retries": 0,
            "feasible_designs": len(ok),
            "failed_designs": len(self.attempts) - len(ok),
            "physical_solver_starts_actual": self.starts_used,
            "carried_forward": {
                "design_attempts": self.prior_design_attempts,
                "solver_starts": self.prior_starts,
                "internal_solver_cases": self.prior_internal,
                "source": ("spent by earlier batches under the same authorization; see the "
                           "batch abort record, which is the authoritative witness"),
            },
            "caps": dict(self.caps),
            "remaining": self.remaining(),
        }


def bootstrap_designs(count: int = 4, *, seed: int = 20261124) -> List[List[float]]:
    """Deterministic bootstrap: the baseline plus a fixed low-discrepancy spread."""
    if count < 2:
        raise ProtocolError("bootstrap needs the baseline plus at least one new design")
    from research.concorde_metaopt.dreal001.optimizers.recovery_bo import (
        generate_initial_designs,
    )

    points = generate_initial_designs(SUBSPACE_LOWER, SUBSPACE_UPPER,
                                      count=count, seed=seed, method="lhs")
    designs = [subspace_to_design(point) for point in points]
    designs[0] = list(BASELINE_X12)  # the baseline is always measured first
    unique: List[List[float]] = []
    seen = set()
    for design in designs:
        key = design_identity(design)["geometry_sha256"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(design)
    if len(unique) < count:
        raise ProtocolError("bootstrap produced duplicate designs")
    return unique


def run_bo_loop(
    *,
    evaluate: Callable[[AttemptRecord], AttemptRecord],
    ledger: Optional[AttemptLedger] = None,
    passes: Optional[List[Dict[str, Any]]] = None,
    seed: int = 20261124,
    max_attempts: int = 12,
    bootstrap_count: int = 4,
) -> Dict[str, Any]:
    """Drive ask -> evaluate -> tell with a real (injected) evaluator.

    `evaluate` must return the same AttemptRecord with terminals filled in. It is
    the only place that is allowed to touch the solver, so this loop is testable
    without physical starts.
    """
    from research.concorde_metaopt.dreal001.optimizers.recovery_bo import (
        RecoveryGaussianProcessBO,
    )

    assert_execution_contract()
    book = ledger if ledger is not None else AttemptLedger()
    if book.attempts:
        raise ProtocolError("BO loop requires a fresh ledger")
    # The design cap belongs to the authorization, not to this process: a ledger that already
    # carries forward designs spent by an earlier aborted batch permits fewer than
    # caps["max_design_attempts"] new records. Bounding only by the cap made the loop ask for one
    # design too many and end with ProtocolError "run would exceed 12 design attempts" AFTER the
    # batch had already legitimately completed its whole remainder; the charge path refused it,
    # which is the correct behaviour, but the loop should never have asked.
    design_budget = book.caps["max_design_attempts"] - book.prior_design_attempts
    max_attempts = min(int(max_attempts), book.caps["max_design_attempts"], design_budget)

    bo = RecoveryGaussianProcessBO(SUBSPACE_LOWER, SUBSPACE_UPPER, seed=seed)
    records: List[AttemptRecord] = []
    asks: List[Dict[str, Any]] = []
    # Waste bound: a run of designs that each cost their 2 charged starts and still fail
    # to admit a raw row means the alpha strategy is not landing, so the batch stops with
    # budget left instead of grinding through all 12 designs. This is the named answer to
    # the objection "a bracket miss still burns the full budget".
    streak_limit = int(book.caps["max_consecutive_unadmitted_designs"])
    unadmitted_streak = 0
    stop_reason: Optional[str] = None

    def note_result(done: AttemptRecord) -> bool:
        """Count the unadmitted streak; True means the loop must stop now."""
        nonlocal unadmitted_streak, stop_reason
        if done.objective is None:
            unadmitted_streak += 1
        else:
            unadmitted_streak = 0
        if unadmitted_streak >= streak_limit:
            stop_reason = ("%d consecutive designs produced no admitted raw row; stopped "
                           "with budget left by pre-registered policy"
                           % unadmitted_streak)
            return True
        return False

    def record_ask(index: int, stage: str, x12: List[float],
                   acquisition: Optional[Dict[str, Any]]) -> AttemptRecord:
        identity = design_identity(x12)
        attempt = AttemptRecord(
            design_index=index, stage=stage, x12=identity["x12"],
            design_id=identity["design_id"], geometry_sha256=identity["geometry_sha256"],
            is_baseline=identity["is_baseline"], acquisition=acquisition)
        book.add(attempt)
        return attempt

    def evaluate_and_settle(attempt: AttemptRecord) -> AttemptRecord:
        """Charge what the evaluator declared, even when the evaluator dies.

        O0-B01 was aborted by a bug inside the evaluator after one start had already
        been spent; because the exception unwound before settle(), the run counters
        never saw that start. A design evaluation that raises therefore still settles
        its declared consumption through the caps before the exception propagates:
        the batch may die, the start may not disappear.
        """
        try:
            done = evaluate(attempt)
        except BaseException:
            declared = (int(attempt.starts), int(attempt.internal))
            try:
                book.settle(attempt)
            except ProtocolError as settle_error:
                # An evaluator that declares more than the pre-registered caps allows is
                # itself a protocol violation. Keep the original failure as the raised
                # error, restore the declared numbers so the abort record can still show
                # what was spent, and say why the charge could not be adopted.
                attempt.starts, attempt.internal = declared
                attempt.detail = ("%s | ledger could not settle the declared consumption "
                                  "%s start(s) / %s internal case(s): %s"
                                  % (attempt.detail or "", declared[0], declared[1],
                                     settle_error)).strip()
            raise
        book.settle(done)
        return done

    # -- bootstrap ----------------------------------------------------------
    for index, design in enumerate(bootstrap_designs(bootstrap_count, seed=seed)):
        if index >= max_attempts:
            break
        attempt = record_ask(index, "BOOTSTRAP", design, None)
        done = evaluate_and_settle(attempt)
        records.append(done)
        asks.append({"index": index, "stage": "BOOTSTRAP",
                     "design_id": done.design_id, "x12": done.x12,
                     "objective": done.objective, "status": done.status})
        bo.tell(design_to_subspace(done.x12), {
            "valid": done.objective is not None,
            "feasible": bool(done.feasible),
            "objective": done.objective,
        })
        if note_result(done):
            break

    # -- adaptive -----------------------------------------------------------
    while len(records) < max_attempts and stop_reason is None:
        ask = bo.ask()
        x12 = subspace_to_design(ask["design_vector"])
        check_design(x12)
        attempt = record_ask(len(records), "ADAPTIVE", x12, dict(ask["acquisition"]))
        done = evaluate_and_settle(attempt)
        records.append(done)
        asks.append({"index": done.design_index, "stage": "ADAPTIVE",
                     "design_id": done.design_id, "x12": done.x12,
                     "objective": done.objective, "status": done.status,
                     "acquisition": done.acquisition})
        bo.tell(design_to_subspace(done.x12), {
            "valid": done.objective is not None,
            "feasible": bool(done.feasible),
            "objective": done.objective,
        })
        if note_result(done):
            break
        if book.remaining()["solver_starts"] <= 0:
            break

    feasible = [r for r in records if r.feasible and r.objective is not None]
    best = min(feasible, key=lambda r: float(r.objective)) if feasible else None
    baseline = next((r for r in records if r.is_baseline and r.objective is not None), None)
    adaptive = [r for r in records if r.stage == "ADAPTIVE"]
    return {
        "schema": SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "task": dict(TASK),
        "subspace": {"variables": ["sweep_1", "sweep_2"],
                     "bounds": {name: list(SUBSPACE_BOUNDS[name])
                                for name in ("sweep_1", "sweep_2")},
                     "frozen_others": [name for name in VARIABLE_ORDER
                                       if name not in SUBSPACE_INDEX]},
        "alpha_plan": alpha_plan(),
        "ledger": book.summary(),
        "attempts": [r.as_dict() for r in records],
        "asks": asks,
        "baseline": baseline.as_dict() if baseline else None,
        "best_feasible": best.as_dict() if best else None,
        "best_feasible_di_n": float(best.objective) if best else None,
        "baseline_di_n": float(baseline.objective) if baseline else None,
        "improvement_n": (float(baseline.objective) - float(best.objective))
        if (baseline and best) else None,
        "improvement_fraction": ((float(baseline.objective) - float(best.objective))
                                 / float(baseline.objective))
        if (baseline and best) else None,
        "adaptive_attempts": len(adaptive),
        "stopped_by_unadmitted_streak": stop_reason,
        "unadmitted_streak_limit": streak_limit,
        "feedback_dependent": len(adaptive) >= 4,
        "non_baseline_feasible": any(
            r.feasible and not r.is_baseline for r in records),
        "physical_solver_starts_actual": book.starts_used,
        "internal_solver_cases_actual": book.internal_used,
        "physics_validated": False,
    }


def counterfactual_check(evaluate: Callable[[AttemptRecord], AttemptRecord], *,
                         seed: int = 20261124) -> Dict[str, Any]:
    """Prove the loop depends on real feedback, not on a fixed sequence.

    Runs the same protocol twice against a synthetic evaluator whose two lowest
    bootstrap objectives are swapped, and checks that the third adaptive ask moves.
    """
    def synthetic(fail_first: bool):
        calls: List[float] = []

        def evaluator(attempt: AttemptRecord) -> AttemptRecord:
            attempt.starts = 1
            attempt.internal = 20
            attempt.status = "SYNTHETIC"
            attempt.sref_m2 = 358.25
            attempt.q_pa = TASK["dynamic_pressure_pa"]
            table = {0: 200000.0, 1: 150000.0, 2: 250000.0, 3: 180000.0}
            value = table.get(attempt.design_index)
            if value is None:
                value = 240000.0 - 3000.0 * len(calls)
            if fail_first and attempt.design_index == 0:
                attempt.objective = None
                attempt.feasible = False
                attempt.failure_kind = "COUNTERFACTUAL_FAILURE"
                calls.append(float("nan"))
                return attempt
            attempt.objective = value
            attempt.feasible = True
            attempt.di_n = value
            calls.append(value)
            return attempt

        result = run_bo_loop(evaluate=evaluator, ledger=AttemptLedger(),
                             seed=seed, max_attempts=5, bootstrap_count=4)
        return result

    control = synthetic(False)
    shifted = synthetic(True)
    control_seq = [a["design_id"] for a in control["asks"]]
    shifted_seq = [a["design_id"] for a in shifted["asks"]]
    first_divergence = None
    for index, (left, right) in enumerate(zip(control_seq, shifted_seq)):
        if left != right:
            first_divergence = index
            break
    return {
        "control_sequence": control_seq,
        "counterfactual_sequence": shifted_seq,
        "first_divergence_index": first_divergence,
        "next_candidate_changed": first_divergence is not None
        and first_divergence >= control["ledger"]["design_attempts"] - 1,
        "protocol_ok": first_divergence is not None,
        "note": ("a failure in the first bootstrap changes a later ask, so the candidate "
                 "sequence is not pre-fixed"),
    }