"""P3 DOE dataset schema.

A DOE candidate is a pure geometry sample from an explicitly versioned
12D fixed-fuselage or legacy 15D design space.
The row schema deliberately has no objective, constraint result or feasibility
field: P3 only screens geometry legality until a physical evaluation budget is
approved.  Mission/CFD results live in the evaluation ledger, never here, so a
reader can never mistake a screened candidate for a measured aircraft design.

Every row is a lossless record of the design vector (physical SI values in the
frozen variable order), its geometry screening result and a stable content
address.  The manifest (see generate_doe) records provenance: method, seed,
config hashes, git revision and real physical call count (always zero here).
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..aircraft.design_space import DesignSpace, DesignSpaceError

SCHEMA_VERSION = "p3-doe-1"
CANDIDATE_ID_PREFIX = "cand-"
CANDIDATES_FILENAME = "candidates.jsonl"
CANDIDATES_CSV_FILENAME = "candidates.csv"
MANIFEST_FILENAME = "data_manifest.json"
SUMMARY_FILENAME = "summary.json"
METHODS: Tuple[str, ...] = ("lhs", "sobol")
GEOMETRY_VALID = "valid"
GEOMETRY_INVALID = "invalid"
GEOMETRY_ERROR = "error"
GEOMETRY_STATUSES: Tuple[str, ...] = (GEOMETRY_VALID, GEOMETRY_INVALID, GEOMETRY_ERROR)
EVALUATION_NOT_RUN = "not_evaluated"

REQUIRED_FIELDS: Tuple[str, ...] = (
    "schema_version",
    "candidate_id",
    "batch_id",
    "batch_index",
    "sample_index",
    "method",
    "seed",
    "design",
    "design_units",
    "geometry_status",
    "geometry_error",
    "failed_checks",
    "warned_checks",
    "metrics",
    "evaluation_status",
    "physical_call_count",
)

FORBIDDEN_FIELDS: Tuple[str, ...] = ("objective", "feasible", "constraints", "fuel_burn_kg")

# Metrics copied into the compact candidate row (the rest stay in the geometry
# case artefacts / later datasets).  Keep this list explicit so a schema change
# is visible in review.
ROW_METRICS: Tuple[str, ...] = (
    "wing_area_m2",
    "wing_span_m",
    "wing_root_chord_m",
    "wing_mac_m",
    "wing_wetted_area_m2",
    "wing_tip_twist_deg",
    "tail_area_m2",
    "tail_span_m",
    "tail_root_chord_m",
    "fuselage_length_m",
    "fuselage_usable_volume_m3",
    "fuselage_volume_margin_m3",
    "cg_x_m",
    "static_margin",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_design(design: Mapping[str, float], names: Sequence[str]) -> str:
    return json.dumps(
        [float(design[name]) for name in names],
        separators=(",", ":"),
        allow_nan=False,
    )


def candidate_id(design: Mapping[str, float], names: Sequence[str]) -> str:
    digest = hashlib.sha256(canonical_design(design, names).encode("utf-8")).hexdigest()
    return CANDIDATE_ID_PREFIX + digest[:16]


def design_units(space: DesignSpace) -> Dict[str, str]:
    return {variable.name: variable.unit for variable in space.variables}


def row_metrics(metrics: Mapping[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for key in ROW_METRICS:
        value = metrics.get(key)
        row[key] = _finite_or_none(value)
    return row


def _finite_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def make_candidate_row(
    space: DesignSpace,
    design: Mapping[str, float],
    *,
    batch_id: str,
    batch_index: int,
    sample_index: int,
    method: str,
    seed: int,
    geometry_status: str,
    geometry_error: Optional[str] = None,
    failed_checks: Iterable[str] = (),
    warned_checks: Iterable[str] = (),
    metrics: Optional[Mapping[str, Any]] = None,
    wall_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    if method not in METHODS:
        raise ValueError("unknown DOE method %r" % method)
    if geometry_status not in GEOMETRY_STATUSES:
        raise ValueError("unknown geometry status %r" % geometry_status)
    names = space.names
    physical = {name: float(design[name]) for name in names}
    row: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id(physical, names),
        "batch_id": batch_id,
        "batch_index": int(batch_index),
        "sample_index": int(sample_index),
        "method": method,
        "seed": int(seed),
        "design": physical,
        "design_units": design_units(space),
        "geometry_status": geometry_status,
        "geometry_error": geometry_error,
        "failed_checks": list(dict.fromkeys(failed_checks)),
        "warned_checks": list(dict.fromkeys(warned_checks)),
        "metrics": row_metrics(metrics or {}),
        "evaluation_status": EVALUATION_NOT_RUN,
        "physical_call_count": 0,
    }
    if wall_seconds is not None:
        row["screening_wall_seconds"] = float(wall_seconds)
    return row


def check_candidate_row(
    row: Mapping[str, Any],
    space: Optional[DesignSpace] = None,
) -> List[str]:
    errors: List[str] = []
    if not isinstance(row, Mapping):
        return ["row is not a mapping"]
    for key in REQUIRED_FIELDS:
        if key not in row:
            errors.append("missing required field %r" % key)
    for key in FORBIDDEN_FIELDS:
        if key in row:
            errors.append("forbidden field %r present (DOE rows never carry objectives)" % key)
    if errors:
        return errors
    if row.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version %r != %r" % (row.get("schema_version"), SCHEMA_VERSION))
    if row.get("method") not in METHODS:
        errors.append("method %r is not one of %r" % (row.get("method"), METHODS))
    if row.get("geometry_status") not in GEOMETRY_STATUSES:
        errors.append("geometry_status %r is not one of %r" % (row.get("geometry_status"), GEOMETRY_STATUSES))
    if row.get("evaluation_status") != EVALUATION_NOT_RUN:
        errors.append("evaluation_status %r != %r" % (row.get("evaluation_status"), EVALUATION_NOT_RUN))
    if row.get("physical_call_count") not in (0, None):
        errors.append("physical_call_count %r must be 0 for a DOE screening row" % (row.get("physical_call_count"),))
    design = row.get("design")
    if not isinstance(design, Mapping):
        errors.append("design is not a mapping")
        return errors
    if space is not None:
        missing = [name for name in space.names if name not in design]
        extra = [name for name in design if name not in space.names]
        if missing:
            errors.append("design misses variables: %s" % ", ".join(missing))
        if extra:
            errors.append("design contains undeclared variables: %s" % ", ".join(extra))
        if not missing and not extra:
            for violation in space.check_physical(design):
                errors.append("design violation: " + violation)
            expected_id = candidate_id(design, space.names)
            if row.get("candidate_id") != expected_id:
                errors.append(
                    "candidate_id %r does not match content hash %r"
                    % (row.get("candidate_id"), expected_id)
                )
    for name, value in design.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append("design[%r] is not numeric: %r" % (name, value))
        elif not math.isfinite(float(value)):
            errors.append("design[%r] is not finite: %r" % (name, value))
    metrics = row.get("metrics")
    if not isinstance(metrics, Mapping):
        errors.append("metrics is not a mapping")
    else:
        for key, value in metrics.items():
            if value is not None and not math.isfinite(float(value)):
                errors.append("metrics[%r] is not finite: %r" % (key, value))
    for key in ("failed_checks", "warned_checks"):
        if not isinstance(row.get(key), list):
            errors.append("%s is not a list" % key)
    return errors


def schema_summary() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "methods": list(METHODS),
        "geometry_statuses": list(GEOMETRY_STATUSES),
        "row_metrics": list(ROW_METRICS),
        "required_fields": list(REQUIRED_FIELDS),
        "forbidden_fields": list(FORBIDDEN_FIELDS),
        "evaluation_status": EVALUATION_NOT_RUN,
        "note": "DOE screening rows are geometry samples only; no objective is ever stored here.",
    }
