"""Frozen Phase I fixed-cruise evaluation contract.

Every constraint is written as g_j <= 0. A design is feasible only when all
constraints are present and non-positive. Geometric infeasibility and solver
failures are reported as separate statuses, never as fake large objective
values, so no model can learn from an invented penalty.

The objective is the fuel burnt during the fixed cruise segment:
fuel_burn_kg = mass_start_kg - mass_end_kg (kg). It is deliberately not called
TSFC.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional, Tuple

OBJECTIVE_NAME = "fuel_burn_kg"
OBJECTIVE_UNIT = "kg"

STATUS_VALID = "VALID"
STATUS_GEOMETRY_INVALID = "GEOMETRY_INVALID"
STATUS_GEOMETRY_MISMATCH = "GEOMETRY_MISMATCH"
STATUS_MISSION_BUILD_FAILED = "MISSION_BUILD_FAILED"
STATUS_MISSION_FAILED = "MISSION_FAILED"
STATUS_MISSION_NOT_CONVERGED = "MISSION_NOT_CONVERGED"
STATUS_INVALID_OR_MISSING_RESPONSE = "INVALID_OR_MISSING_RESPONSE"

# Constraints in a frozen order. Changing the order changes the fingerprint of
# the evaluation protocol and must be treated as a protocol change.
CONSTRAINT_NAMES = (
    "geometry_invalid",
    "task_mass_balance",
    "fuel_capacity_excess",
    "zero_fuel_excess",
    "takeoff_excess",
    "fuel_remaining_deficit",
    "max_throttle",
    "cruise_range_error",
    "mission_convergence",
    "trim_attitude_limit",
)

CONSTRAINT_UNITS = {
    "geometry_invalid": "1",
    "task_mass_balance": "1",
    "fuel_capacity_excess": "1",
    "zero_fuel_excess": "1",
    "takeoff_excess": "1",
    "fuel_remaining_deficit": "1",
    "max_throttle": "1",
    "cruise_range_error": "1",
    "mission_convergence": "1",
    "trim_attitude_limit": "1",
}

# Constraints are normalised with the corresponding task quantity so that all
# values are order 1 and comparable in a GP model.
FEASIBILITY_TOLERANCE = 1.0e-12

# Maximum accepted residual norm for a converged segment. Matches the value
# already used by the historical maml-opt Concorde application.
RESIDUAL_LIMIT = 1.0e-4

# Attitude guard for the force-balance-only cruise solution. Phase I has no
# moment trim, so the linear attitude range is checked explicitly.
MAX_ATTITUDE_DEG = 12.0


def empty_constraints(geometry_invalid: Optional[float] = None) -> Dict[str, Optional[float]]:
    """Return all constraint keys with null values, optionally flagging geometry."""
    constraints: Dict[str, Optional[float]] = {name: None for name in CONSTRAINT_NAMES}
    constraints["geometry_invalid"] = geometry_invalid
    return constraints


def _finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("constraint input %s is not a number: %r" % (name, value)) from exc
    if not math.isfinite(number):
        raise ValueError("constraint input %s is not finite: %r" % (name, value))
    return number


def evaluate_constraints(
    task: Any,
    observations: Mapping[str, Any],
    geometry_valid: bool = True,
) -> Dict[str, float]:
    """Compute the ten frozen constraints from one evaluated mission."""
    if not geometry_valid:
        raise ValueError("constraints cannot be computed for a geometry-invalid design")
    required = (
        "mass_start_kg",
        "mass_end_kg",
        "fuel_burn_kg",
        "range_span_m",
        "max_throttle",
        "converged",
        "solver_converged",
        "residual_max",
        "alpha_end_deg",
    )
    missing = [name for name in required if name not in observations]
    if missing:
        raise ValueError("observations miss required keys: %s" % ", ".join(missing))

    max_fuel = _finite(task.max_fuel_kg, "task.max_fuel_kg")
    max_zero_fuel = _finite(task.max_zero_fuel_kg, "task.max_zero_fuel_kg")
    max_takeoff = _finite(task.max_takeoff_kg, "task.max_takeoff_kg")
    distance = _finite(task.cruise_distance_m, "task.cruise_distance_m")
    start_mass = _finite(task.start_mass_kg, "task.start_mass_kg")
    zfw = _finite(task.zero_fuel_mass_kg, "task.zero_fuel_mass_kg")
    fuel_loaded = _finite(task.fuel_loaded_kg, "task.fuel_loaded_kg")

    mass_start = _finite(observations["mass_start_kg"], "mass_start_kg")
    mass_end = _finite(observations["mass_end_kg"], "mass_end_kg")
    fuel_burn = _finite(observations["fuel_burn_kg"], "fuel_burn_kg")
    range_span = _finite(observations["range_span_m"], "range_span_m")
    max_throttle = _finite(observations["max_throttle"], "max_throttle")
    residual_max = _finite(observations["residual_max"], "residual_max")
    alpha_end_deg = _finite(observations["alpha_end_deg"], "alpha_end_deg")

    converged = bool(observations["converged"])
    solver_converged = bool(observations["solver_converged"])

    constraints: Dict[str, float] = {}
    constraints["geometry_invalid"] = 0.0
    constraints["task_mass_balance"] = abs(mass_start - start_mass) / start_mass
    constraints["fuel_capacity_excess"] = (max(fuel_burn, fuel_loaded) - max_fuel) / max_fuel
    constraints["zero_fuel_excess"] = (zfw - max_zero_fuel) / max_zero_fuel
    constraints["takeoff_excess"] = (
        max(mass_start, zfw + fuel_loaded) - max_takeoff
    ) / max_takeoff
    constraints["fuel_remaining_deficit"] = (zfw - mass_end) / max_fuel
    constraints["max_throttle"] = max_throttle - 1.0
    constraints["cruise_range_error"] = abs(range_span - distance) / distance
    converged_ok = converged and solver_converged and residual_max <= RESIDUAL_LIMIT
    constraints["mission_convergence"] = 0.0 if converged_ok else 1.0
    constraints["trim_attitude_limit"] = (
        abs(alpha_end_deg) - MAX_ATTITUDE_DEG
    ) / MAX_ATTITUDE_DEG
    return constraints


def feasibility(constraints: Mapping[str, Optional[float]]) -> bool:
    """Return True only when every frozen constraint is present and g <= 0."""
    for name in CONSTRAINT_NAMES:
        if name not in constraints:
            return False
        value = constraints[name]
        if value is None:
            return False
        if not math.isfinite(float(value)):
            return False
        if float(value) > FEASIBILITY_TOLERANCE:
            return False
    return True


def optimizer_constraints(
    constraints: Mapping[str, Optional[float]],
) -> Dict[str, float]:
    """Return constraints shifted so an exact g <= 0 test matches the contract.

    The frozen contract treats |g| <= FEASIBILITY_TOLERANCE as feasible, while
    the external maml-opt optimizer tests g <= 0 exactly. Shifting every value
    down by the same tolerance makes both tests agree on signed values without
    changing the ranking of designs. The shift is tiny (1e-12) and is recorded
    in the run summary under the feasibility tolerance fields.
    """
    shifted: Dict[str, float] = {}
    for name in CONSTRAINT_NAMES:
        value = constraints.get(name)
        if value is None:
            raise ValueError("constraint %r is missing from the evaluation" % (name,))
        shifted[name] = float(value) - FEASIBILITY_TOLERANCE
    return shifted


def violated_constraints(
    constraints: Mapping[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    """Return the subset of constraints with positive values (diagnostics only)."""
    return {
        name: constraints.get(name)
        for name in CONSTRAINT_NAMES
        if constraints.get(name) is not None and float(constraints[name]) > FEASIBILITY_TOLERANCE
    }


# -- physical-call accounting -------------------------------------------------
# A backend request is not a physical evaluation. Truly billable calls are only
# solver attempts: a request rejected before the mission solver, a geometry
# rejection and a mission-build failure must all be traceable while costing 0.
CALL_ACCOUNTING_SCHEMA_VERSION = 1

CALL_ACCOUNTING_OUTCOMES = (
    "request_rejected",
    "geometry_rejected",
    "mission_build_failed",
    "mission_solve_attempted",
)

CALL_ACCOUNTING_FLAGS = (
    "request",
    "cache_hit",
    "request_rejected",
    "geometry_rejected",
    "mission_build_failed",
    "mission_solve_attempted",
    "mission_solve_completed",
    "billable_physical_calls",
)


def new_call_accounting() -> Dict[str, Any]:
    """Return a fresh per-request accounting block with no solver attempt yet."""
    return {
        "schema_version": CALL_ACCOUNTING_SCHEMA_VERSION,
        "request": 1,
        "cache_hit": 0,
        "request_rejected": 0,
        "geometry_rejected": 0,
        "mission_build_failed": 0,
        "mission_solve_attempted": 0,
        "mission_solve_completed": 0,
        "billable_physical_calls": 0,
        "failure_stage": None,
    }


def validate_call_accounting(
    raw: Any,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Validate an explicit backend accounting block (fail-closed).

    Returns (normalized, None) when valid and (None, reason) otherwise. Exactly
    one outcome must be described so a request cannot be both rejected and
    billed; billable calls must equal solver attempts.
    """
    if not isinstance(raw, Mapping):
        return None, "call_accounting is not a mapping"
    if raw.get("schema_version") != CALL_ACCOUNTING_SCHEMA_VERSION:
        return None, "unsupported call_accounting schema_version: %r" % (
            raw.get("schema_version"),
        )
    normalized: Dict[str, Any] = {"schema_version": CALL_ACCOUNTING_SCHEMA_VERSION}
    for name in CALL_ACCOUNTING_FLAGS:
        value = raw.get(name)
        if type(value) is not int or value not in (0, 1):
            return None, "call_accounting[%r] must be 0 or 1, got %r" % (name, value)
        normalized[name] = int(value)
    stage = raw.get("failure_stage")
    if stage is not None and not isinstance(stage, str):
        return None, "call_accounting['failure_stage'] must be a string or null"
    normalized["failure_stage"] = stage
    if normalized["request"] != 1:
        return None, "call_accounting['request'] must be 1"
    if normalized["cache_hit"] != 0:
        return None, "backend records cannot be cache hits; the ledger marks cache hits itself"
    outcomes = sum(normalized[name] for name in CALL_ACCOUNTING_OUTCOMES)
    if outcomes != 1:
        return None, "call_accounting must describe exactly one outcome, saw %d" % (outcomes,)
    if normalized["billable_physical_calls"] != normalized["mission_solve_attempted"]:
        return None, "billable_physical_calls must equal mission_solve_attempted"
    if normalized["mission_solve_completed"] > normalized["mission_solve_attempted"]:
        return None, "mission_solve_completed requires mission_solve_attempted"
    return normalized, None
