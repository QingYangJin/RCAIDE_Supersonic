"""Evaluation ledger: budget accounting, caching and the per-run JSONL record.

The ledger is the single place that counts true (physical) evaluations, so the
budget argument in the CLI is authoritative. A cache hit never consumes budget
and is marked as such; only valid evaluations are cached so a transient mission
failure is not silently reused.

Two files are written:

- evaluations.jsonl: one compact row per request (the Issue-mandated schema).
- evaluations_detail.jsonl: one row per true (physical) evaluation, carrying the
  full backend record (responses, geometry cross-check, mass contract, design).
  Cache hits are not repeated here because they made no physical call.

The detail file keeps the evidence auditable without inflating the compact row
with nested mission output; every value is JSON-safe (non-finite -> null).
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .contract import (
    STATUS_INVALID_OR_MISSING_RESPONSE,
    STATUS_VALID,
    feasibility,
)

EVALUATIONS_FILENAME = "evaluations.jsonl"
DETAILS_FILENAME = "evaluations_detail.jsonl"

STATUS_BACKEND_ERROR = "BACKEND_ERROR"


class BudgetExceeded(RuntimeError):
    """Raised when a request would exceed the approved true-evaluation budget."""

    def __init__(self, budget: int, used: int) -> None:
        super().__init__(
            "true-evaluation budget exhausted: budget=%s used=%s" % (budget, used)
        )
        self.budget = budget
        self.used = used


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _sanitize_record(record: Mapping[str, Any], fidelity_name: str) -> Dict[str, Any]:
    """Fail-closed view of a backend record.

    Only a VALID record with a finite objective and a non-empty finite
    constraint mapping can contribute an objective or a feasible flag. Anything
    else keeps its physical-call accounting but never leaks a fabricated
    objective into the ledger, best-so-far tracking or the cache.
    """
    raw_status = record.get("status")
    status = str(raw_status) if raw_status is not None else "MISSING_STATUS"
    diagnostics = [str(item) for item in record.get("diagnostics") or []]
    constraints_in = record.get("constraints")
    constraints: Dict[str, Optional[float]] = {}
    if isinstance(constraints_in, Mapping):
        for name, value in constraints_in.items():
            if value is None:
                constraints[str(name)] = None
            elif _finite_number(value):
                constraints[str(name)] = float(value)
            else:
                constraints[str(name)] = None
    objective = record.get("objective")
    feasible = False
    if status == STATUS_VALID:
        if not _finite_number(objective):
            status = STATUS_INVALID_OR_MISSING_RESPONSE
            diagnostics.append("VALID status without a finite objective was rejected")
            objective = None
        elif not constraints:
            status = STATUS_INVALID_OR_MISSING_RESPONSE
            diagnostics.append("VALID status without constraint values was rejected")
            objective = None
        else:
            objective = float(objective)
            feasible = feasibility(constraints)
    else:
        objective = None
    return {
        "status": status,
        "objective": objective,
        "feasible": bool(feasible),
        "constraints": constraints,
        "diagnostics": diagnostics,
        "fidelity": record.get("fidelity", fidelity_name),
    }


def canonical_design(design: Mapping[str, float]) -> str:
    payload = {str(name): float(value) for name, value in design.items()}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def design_id(design: Mapping[str, float]) -> str:
    return "d-" + hashlib.sha256(canonical_design(design).encode("utf-8")).hexdigest()[:12]


def json_safe(value: Any) -> Any:
    """Recursively convert a backend value to something json.dumps accepts.

    Non-finite floats become None so a failed or partially populated record can
    still be written without allow_nan (NaN/Infinity are not valid JSON).
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return json_safe(tolist())
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)


class EvaluationLedger:
    """Writes evaluations.jsonl and enforces the physical-call budget."""

    def __init__(
        self,
        budget: int,
        run_dir: Path,
        cache_enabled: bool = True,
        evaluations_filename: str = EVALUATIONS_FILENAME,
        details_filename: Optional[str] = DETAILS_FILENAME,
    ) -> None:
        self.budget = int(budget)
        if self.budget < 0:
            raise ValueError("budget must be non-negative")
        self.run_dir = Path(run_dir)
        self.cache_enabled = bool(cache_enabled)
        self.rows: List[Dict[str, Any]] = []
        self.records: List[Dict[str, Any]] = []
        self.physical_calls = 0
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._best_objective: Optional[float] = None
        self._best_design_id: Optional[str] = None
        self._best_design: Optional[Dict[str, float]] = None
        self._first_feasible: Optional[int] = None
        self._path = self.run_dir / evaluations_filename
        self._details_path = self.run_dir / details_filename if details_filename else None
        self.run_dir.mkdir(parents=True, exist_ok=True)

    # -- properties -------------------------------------------------------
    @property
    def remaining(self) -> int:
        return max(self.budget - self.physical_calls, 0)

    def _cache_key(self, task_fingerprint: str, fidelity: str, design: Mapping[str, float]) -> str:
        return "%s|%s|%s" % (task_fingerprint, fidelity, canonical_design(design))

    # -- evaluation -------------------------------------------------------
    def evaluate(
        self,
        backend: Any,
        design: Mapping[str, float],
        task: Any,
        fidelity: Optional[str] = None,
        purpose: str = "search",
    ) -> Dict[str, Any]:
        """Evaluate one design and append its ledger row.

        Returns the ledger row. The full backend record is kept in self.records.
        """
        task_fingerprint = task.fingerprint() if hasattr(task, "fingerprint") else str(getattr(task, "task_id", "task"))
        fidelity_name = fidelity or getattr(backend, "fidelity", None) or "single_cruise"
        key = self._cache_key(task_fingerprint, fidelity_name, design)
        iteration = len(self.rows) + 1
        did = design_id(design)

        cached = self._cache.get(key) if self.cache_enabled else None
        if cached is not None:
            row = {
                "iteration": iteration,
                "design_id": did,
                "x": {name: float(design[name]) for name in design},
                "status": cached["status"],
                "objective": cached["objective"],
                "constraints": dict(cached["constraints"]),
                "feasible": cached["feasible"],
                "fidelity": cached["fidelity"],
                "cache_hit": True,
                "physical_call_count": 0,
                "wall_seconds": 0.0,
                "cumulative_calls": self.physical_calls,
                "best_feasible_objective": self._best_objective,
                "diagnostics": list(cached.get("diagnostics", [])),
            }
            self.rows.append(row)
            self._append(row)
            return row

        if self.physical_calls >= self.budget:
            raise BudgetExceeded(self.budget, self.physical_calls)

        started = time.perf_counter()
        error: Optional[BaseException] = None
        record: Dict[str, Any]
        try:
            record = backend.evaluate(design, task=task, fidelity=fidelity_name, purpose=purpose)
        except BudgetExceeded:
            raise
        except Exception as exc:  # pragma: no cover - defensive boundary
            error = exc
            record = {
                "status": STATUS_BACKEND_ERROR,
                "objective": None,
                "constraints": {},
                "feasible": False,
                "fidelity": fidelity_name,
                "diagnostics": ["backend error: %s: %s" % (type(exc).__name__, exc)],
                "physical_call_count": getattr(backend, "last_physical_call_count", 1),
            }
        wall = time.perf_counter() - started

        try:
            physical = int(record.get("physical_call_count", 1) or 0)
        except (TypeError, ValueError):
            physical = 1
        if physical < 0:
            physical = 0
        self.physical_calls += physical
        self.records.append(record)

        sanitized = _sanitize_record(record, fidelity_name)
        objective = sanitized["objective"]
        feasible = bool(sanitized["feasible"]) and objective is not None
        if feasible and objective is not None:
            value = float(objective)
            if self._best_objective is None or value < self._best_objective:
                self._best_objective = value
                self._best_design_id = did
                self._best_design = {name: float(design[name]) for name in design}
            if self._first_feasible is None:
                self._first_feasible = iteration

        row = {
            "iteration": iteration,
            "design_id": did,
            "x": {name: float(design[name]) for name in design},
            "status": STATUS_BACKEND_ERROR if error is not None else sanitized["status"],
            "objective": None if objective is None else float(objective),
            "constraints": dict(sanitized["constraints"]),
            "feasible": feasible,
            "fidelity": sanitized["fidelity"],
            "cache_hit": False,
            "physical_call_count": physical,
            "wall_seconds": round(wall, 6),
            "cumulative_calls": self.physical_calls,
            "best_feasible_objective": self._best_objective,
            "diagnostics": list(sanitized["diagnostics"]),
        }
        if error is not None:
            row["objective"] = None
            row["feasible"] = False
        self.rows.append(row)
        self._append(row)
        self._append_detail(row, record)

        if self.cache_enabled and row["status"] == STATUS_VALID:
            self._cache[key] = {
                "status": row["status"],
                "objective": row["objective"],
                "constraints": dict(row["constraints"]),
                "feasible": row["feasible"],
                "fidelity": row["fidelity"],
                "diagnostics": list(row["diagnostics"]),
            }
        return row

    def _append(self, row: Mapping[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")

    def _append_detail(self, row: Mapping[str, Any], record: Mapping[str, Any]) -> None:
        if self._details_path is None:
            return
        detail = {
            "iteration": row["iteration"],
            "design_id": row["design_id"],
            "task_id": record.get("task_id"),
            "task_fingerprint": record.get("task_fingerprint"),
            "fidelity": row["fidelity"],
            "purpose": record.get("purpose"),
            "status": row["status"],
            "objective": row["objective"],
            "feasible": row["feasible"],
            "constraints": row["constraints"],
            "design": record.get("design") or row["x"],
            "geometry_summary": record.get("geometry_summary"),
            "geometry_cross_check": record.get("geometry_cross_check"),
            "mass_contract": record.get("mass_contract"),
            "responses": record.get("responses"),
            "diagnostics": row["diagnostics"],
            "physical_call_count": row["physical_call_count"],
            "wall_seconds": row["wall_seconds"],
        }
        safe = json_safe(detail)
        with self._details_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, sort_keys=True, allow_nan=False) + "\n")

    # -- reporting --------------------------------------------------------
    def best(self) -> Dict[str, Any]:
        return {
            "best_feasible_objective": self._best_objective,
            "best_design_id": self._best_design_id,
            "best_design": self._best_design,
            "first_feasible_evaluation": self._first_feasible,
        }

    def summary(self) -> Dict[str, Any]:
        invalid = 0
        failed = 0
        for row in self.rows:
            status = str(row.get("status", ""))
            if status.startswith("GEOMETRY"):
                invalid += 1
            elif status != "VALID":
                failed += 1
        return {
            "total_true_evaluations": self.physical_calls,
            "total_requests": len(self.rows),
            "cache_hits": sum(1 for row in self.rows if row.get("cache_hit")),
            "invalid_count": invalid,
            "failed_count": failed,
            "first_feasible_evaluation": self._first_feasible,
            "best_feasible_fuel_kg": self._best_objective,
            "best_design_id": self._best_design_id,
            "budget": self.budget,
            "budget_remaining": self.remaining,
        }
