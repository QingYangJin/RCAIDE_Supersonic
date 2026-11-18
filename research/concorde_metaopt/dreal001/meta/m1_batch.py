"""Offline M1 batch skeleton: plan, authorise, account, stop.

This module is the software half of the M1 batch runner required by Issue #12:
finite per-batch limits, an explicit new-gate authorisation object, fail-closed
accounting against an injected ledger, failure objectives as None, a single
retry, parallel=1 and hard stop conditions.

It never imports a process launcher or a geometry tool. The physical evaluation
is injected as a callable, so an offline fake evaluator can exercise the whole
control path with zero physical starts, and the real A1 evaluator can only be
wired in after a Lead batch GO exists.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Tuple

SCHEMA_PLAN = "drecover001.m1_batch_plan.v1"
SCHEMA_RESULT = "drecover001.m1_batch_result.v1"
SCOPE = "OFFLINE_BATCH_SKELETON_ONLY"

MAX_STARTS_PER_BATCH = 24
MIN_SOLVER_TIMEOUT_S = 30
MAX_SOLVER_TIMEOUT_S = 600
MAX_RETRIES = 1
MAX_PARALLEL = 1
INTERNAL_CASES_PER_START = 7
MAX_BATCH_WALL_S = 7200

RETRYABLE_FAILURES = ("SOLVER_NONCONVERGED", "SOLVER_FAILED",
                      "LIFT_TARGET_UNREACHABLE")
INVALID_DESIGN_FAILURES = ("GEOMETRY_INVALID", "DECK_INVALID")
A5_APPROVED_VERDICTS = (
    "R2_FIXED_LOOP_GATE_APPROVED_WITH_DISCLOSURE",
    "RESTORED_FIXED_LOOP_PASS_WITH_DISCLOSURE",
)
PLACEHOLDER_TOKENS = ("", "NOT_PERFORMED", "NOT_ISSUED", "NO_PHYSICAL_GO",
                      "PENDING", "PLACEHOLDER", "TODO", "TBD")


class BatchContractError(ValueError):
    """Malformed batch plan, sample or result."""


class BatchNotAuthorized(RuntimeError):
    """Raised when a batch is asked to run without a complete new-gate GO."""


def canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BatchContractError(name + " must be a non-empty string")
    return value.strip()


def _require_int(name: str, value: Any, low: int, high: Optional[int] = None,
                 *, allow_none: bool = False) -> Optional[int]:
    if value is None and allow_none:
        return None
    if type(value) is not int:
        raise BatchContractError(name + " must be an integer")
    if value < low or (high is not None and value > high):
        raise BatchContractError(
            "%s out of range: %r not in [%d, %s]" % (name, value, low, high))
    return int(value)


def _hex_text(name: str, value: Any, *, minimum: int = 8) -> str:
    text = _require_text(name, value)
    if len(text) < minimum or len(text) > 64:
        raise BatchContractError(name + " must be 8..64 characters")
    if any(ch not in "0123456789abcdef" for ch in text):
        raise BatchContractError(name + " must be lowercase hex")
    return text


def _finite(name: str, value: Any, *, minimum: Optional[float] = None) -> float:
    if type(value) is not float or not math.isfinite(value):
        raise BatchContractError(name + " must be a finite float")
    if minimum is not None and value < minimum:
        raise BatchContractError(name + " must be >= %r" % (minimum,))
    return float(value)


@dataclass(frozen=True)
class BatchAuthorization:
    """Explicit new-gate authorisation; structural only, signatures stay external."""

    run_id: str
    batch_id: str
    authorization_id: str
    approval_id: str
    a5_review_id: str
    a5_verdict: str
    lead_go_id: str
    physical_go: bool
    issued_utc: str
    max_starts: int = MAX_STARTS_PER_BATCH
    solver_timeout_s: int = MAX_SOLVER_TIMEOUT_S
    retries: int = MAX_RETRIES
    parallel: int = MAX_PARALLEL
    max_batch_wall_s: Optional[int] = MAX_BATCH_WALL_S
    new_r2_gate: bool = True

    def __post_init__(self) -> None:
        for name in ("run_id", "batch_id", "authorization_id", "approval_id",
                     "a5_review_id", "a5_verdict", "lead_go_id", "issued_utc"):
            _require_text(name, getattr(self, name))
        if type(self.physical_go) is not bool:
            raise BatchContractError("physical_go must be a bool")
        if type(self.new_r2_gate) is not bool:
            raise BatchContractError("new_r2_gate must be a bool")
        if self.new_r2_gate is not True:
            raise BatchContractError(
                "batch must be authorised by a NEW R2 gate, not a reused #9/#10 approval")
        _require_int("max_starts", self.max_starts, 1, MAX_STARTS_PER_BATCH)
        _require_int("solver_timeout_s", self.solver_timeout_s,
                     MIN_SOLVER_TIMEOUT_S, MAX_SOLVER_TIMEOUT_S)
        _require_int("retries", self.retries, 0, MAX_RETRIES)
        _require_int("parallel", self.parallel, MAX_PARALLEL, MAX_PARALLEL)
        _require_int("max_batch_wall_s", self.max_batch_wall_s, 60,
                     MAX_BATCH_WALL_S, allow_none=True)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "authorization_id": self.authorization_id,
            "approval_id": self.approval_id,
            "a5_review_id": self.a5_review_id,
            "a5_verdict": self.a5_verdict,
            "lead_go_id": self.lead_go_id,
            "physical_go": self.physical_go,
            "issued_utc": self.issued_utc,
            "max_starts": self.max_starts,
            "solver_timeout_s": self.solver_timeout_s,
            "retries": self.retries,
            "parallel": self.parallel,
            "max_batch_wall_s": self.max_batch_wall_s,
            "new_r2_gate": self.new_r2_gate,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha(self.as_dict())

    def blocking_reasons(self) -> Tuple[str, ...]:
        reasons: List[str] = []
        if self.physical_go is not True:
            reasons.append("PHYSICAL_GO_NOT_ISSUED")
        if self.a5_verdict not in A5_APPROVED_VERDICTS:
            reasons.append("A5_VERDICT_NOT_APPROVED: " + self.a5_verdict)
        if self.a5_review_id.strip().upper() in PLACEHOLDER_TOKENS:
            reasons.append("A5_REVIEW_ID_IS_PLACEHOLDER")
        if self.lead_go_id.strip().upper() in PLACEHOLDER_TOKENS:
            reasons.append("LEAD_GO_ID_IS_PLACEHOLDER")
        if self.new_r2_gate is not True:
            reasons.append("NOT_A_NEW_R2_GATE")
        return tuple(reasons)

    def require_executable(self) -> None:
        reasons = self.blocking_reasons()
        if reasons:
            raise BatchNotAuthorized("batch not authorised: " + "; ".join(reasons))


@dataclass(frozen=True)
class WorkItem:
    task_id: str
    design_id: str
    design_hash: str
    design_x12: Optional[Tuple[float, ...]] = None
    task_fingerprint: Optional[str] = None

    def __post_init__(self) -> None:
        _require_text("task_id", self.task_id)
        _require_text("design_id", self.design_id)
        _hex_text("design_hash", self.design_hash)
        if self.design_x12 is not None:
            values = tuple(self.design_x12)
            if len(values) != 12:
                raise BatchContractError("design_x12 must have 12 entries")
            for value in values:
                _finite("design_x12 entry", value)
            object.__setattr__(self, "design_x12", values)
        if self.task_fingerprint is not None:
            _hex_text("task_fingerprint", self.task_fingerprint)

    def key(self) -> Tuple[str, str]:
        return (self.task_id, self.design_hash)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "design_id": self.design_id,
            "design_hash": self.design_hash,
            "design_x12": None if self.design_x12 is None else list(self.design_x12),
            "task_fingerprint": self.task_fingerprint,
        }


@dataclass(frozen=True)
class BatchPlan:
    authorization: BatchAuthorization
    items: Tuple[WorkItem, ...]
    internal_cases_per_start: int = INTERNAL_CASES_PER_START
    allow_duplicate_work_items: bool = False
    schema: str = SCHEMA_PLAN
    scope: str = SCOPE

    def __post_init__(self) -> None:
        if not isinstance(self.authorization, BatchAuthorization):
            raise BatchContractError("plan needs a BatchAuthorization")
        items = tuple(self.items)
        if not items:
            raise BatchContractError("batch plan cannot be empty")
        for item in items:
            if not isinstance(item, WorkItem):
                raise BatchContractError("plan items must be WorkItem instances")
        if type(self.allow_duplicate_work_items) is not bool:
            raise BatchContractError("allow_duplicate_work_items must be a bool")
        keys = [item.key() for item in items]
        if len(set(keys)) != len(keys) and not self.allow_duplicate_work_items:
            raise BatchContractError(
                "plan contains duplicate (task_id, design_hash); duplicates only "
                "exercise the evaluation cache and never replace repeatability runs")
        if len(items) > self.authorization.max_starts:
            raise BatchContractError(
                "plan has %d items but authorisation allows %d starts"
                % (len(items), self.authorization.max_starts))
        _require_int("internal_cases_per_start", self.internal_cases_per_start,
                     0, 1000)
        object.__setattr__(self, "items", items)

    def payload(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "scope": self.scope,
            "authorization": self.authorization.as_dict(),
            "authorization_sha256": self.authorization.sha256,
            "internal_cases_per_start": self.internal_cases_per_start,
            "allow_duplicate_work_items": self.allow_duplicate_work_items,
            "items": [item.as_dict() for item in self.items],
        }

    @property
    def plan_sha256(self) -> str:
        return canonical_sha(self.payload())


def build_plan(authorization: BatchAuthorization, items: List[WorkItem],
               *, internal_cases_per_start: int = INTERNAL_CASES_PER_START) -> BatchPlan:
    return BatchPlan(authorization=authorization, items=tuple(items),
                     internal_cases_per_start=internal_cases_per_start)


@dataclass(frozen=True)
class EvaluationSample:
    status: str
    solver_started: bool
    internal_solver_cases: int = 0
    di_n: Optional[float] = None
    cl: Optional[float] = None
    cdi: Optional[float] = None
    raw_path: Optional[str] = None
    raw_sha256: Optional[str] = None
    failure_kind: Optional[str] = None
    detail: Optional[str] = None
    wall_s: float = 0.0

    def __post_init__(self) -> None:
        if self.status not in ("ok", "failed"):
            raise BatchContractError("sample status must be ok or failed")
        if type(self.solver_started) is not bool:
            raise BatchContractError("solver_started must be a bool")
        _require_int("internal_solver_cases", self.internal_solver_cases, 0, 100)
        if not self.solver_started and self.internal_solver_cases != 0:
            raise BatchContractError(
                "a sample without solver start cannot report internal solver cases")
        _finite("wall_s", self.wall_s, minimum=0.0)
        if self.raw_sha256 is not None:
            _hex_text("raw_sha256", self.raw_sha256, minimum=16)
        if self.status == "ok":
            _finite("di_n", self.di_n, minimum=0.0)
            for name in ("cl", "cdi"):
                if getattr(self, name) is not None:
                    _finite(name, getattr(self, name))
            if self.failure_kind is not None:
                raise BatchContractError("a successful sample cannot carry failure_kind")
        else:
            if self.di_n is not None or self.cl is not None or self.cdi is not None:
                raise BatchContractError(
                    "a failed sample must have objective fields None, never invented values")
            _require_text("failure_kind", self.failure_kind)

    @property
    def objective(self) -> Optional[float]:
        return None if self.status != "ok" else float(self.di_n)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "solver_started": self.solver_started,
            "internal_solver_cases": self.internal_solver_cases,
            "di_n": self.di_n,
            "cl": self.cl,
            "cdi": self.cdi,
            "raw_path": self.raw_path,
            "raw_sha256": self.raw_sha256,
            "failure_kind": self.failure_kind,
            "detail": self.detail,
            "wall_s": self.wall_s,
            "objective": self.objective,
        }


class LedgerPort(Protocol):
    def reserve(self, n_starts: int = 1) -> Any: ...
    def settle(self, reservation: Any, used: int, *,
               internal_solver_cases: int = 0) -> None: ...
    def cancel(self, reservation: Any) -> None: ...
    def register_evaluation(self, *, cache_hit: bool, started: bool,
                            valid: bool) -> None: ...


def _reservation_id(reservation: Any) -> Optional[int]:
    value = getattr(reservation, "reservation_id", None)
    return int(value) if type(value) is int else None


def _stop_reservation(ledger: Any, reservation: Any, *, reason: str) -> None:
    if getattr(reservation, "settled", False):
        return
    quarantine = getattr(ledger, "quarantine", None)
    if callable(quarantine):
        quarantine(reservation, reason=reason)
        return
    try:
        ledger.settle(reservation, 0)
    except Exception:
        ledger.cancel(reservation)


def _row(item: WorkItem, index: int, attempt: int, sample: Optional[EvaluationSample],
         *, reservation_id: Optional[int], cached: bool,
         failure_kind: Optional[str] = None, detail: Optional[str] = None) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "index": int(index),
        "attempt": int(attempt),
        "task_id": item.task_id,
        "design_id": item.design_id,
        "design_hash": item.design_hash,
        "cached": bool(cached),
        "reservation_id": reservation_id,
        "objective": None,
        "status": "failed",
        "solver_started": None,
        "internal_solver_cases": 0,
        "di_n": None,
        "cl": None,
        "cdi": None,
        "raw_path": None,
        "raw_sha256": None,
        "failure_kind": failure_kind,
        "detail": detail,
        "wall_s": 0.0,
    }
    if sample is not None:
        base.update({
            "status": sample.status,
            "solver_started": sample.solver_started,
            "internal_solver_cases": int(sample.internal_solver_cases),
            "di_n": sample.di_n,
            "cl": sample.cl,
            "cdi": sample.cdi,
            "raw_path": sample.raw_path,
            "raw_sha256": sample.raw_sha256,
            "failure_kind": sample.failure_kind,
            "detail": sample.detail,
            "wall_s": sample.wall_s,
            "objective": sample.objective,
        })
    if failure_kind is not None:
        base.update({
            "status": "failed",
            "objective": None,
            "di_n": None,
            "cl": None,
            "cdi": None,
            "failure_kind": failure_kind,
        })
        if detail is not None:
            base["detail"] = detail
    return base


def run_batch(plan: BatchPlan, *, evaluator: Callable[[WorkItem], EvaluationSample],
              ledger: LedgerPort, clock: Callable[[], float] = time.monotonic) -> Dict[str, Any]:
    """Execute a planned batch against an injected evaluator and ledger.

    The caller owns evaluator and ledger lifetimes. Nothing here knows how to
    launch a solver; a missing GO, a mismatched ledger budget or an unauthorised
    batch stops before the first reservation.
    """
    if not isinstance(plan, BatchPlan):
        raise BatchContractError("run_batch needs a BatchPlan")
    plan.authorization.require_executable()
    if not callable(evaluator):
        raise BatchContractError("evaluator must be callable")
    for name in ("reserve", "settle", "cancel", "register_evaluation"):
        if not callable(getattr(ledger, name, None)):
            raise BatchContractError("ledger missing callable " + name)
    ledger_budget = getattr(ledger, "max_starts", plan.authorization.max_starts)
    if type(ledger_budget) is int and ledger_budget != plan.authorization.max_starts:
        raise BatchContractError(
            "ledger max_starts %d does not match authorised %d"
            % (ledger_budget, plan.authorization.max_starts))

    started_clock = float(clock())
    rows: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str], Dict[str, Any]] = {}
    charged = 0
    starts_issued = 0
    retries_used = 0
    status = "COMPLETE"
    stop_reason: Optional[str] = None
    stop_batch = False

    for index, item in enumerate(plan.items):
        if stop_batch:
            break
        now = float(clock())
        wall_limit = plan.authorization.max_batch_wall_s
        if wall_limit is not None and (now - started_clock) > wall_limit:
            status = "STOPPED_WALL_CLOCK"
            stop_reason = ("batch wall clock exceeded: %.3f s > %d s"
                           % (now - started_clock, wall_limit))
            break
        key = item.key()
        if key in seen:
            previous = seen[key]
            ledger.register_evaluation(cache_hit=True, started=False,
                                       valid=previous["status"] == "ok")
            cached_row = dict(previous)
            cached_row.update({"index": index, "cached": True,
                               "attempt": 0, "reservation_id": None})
            rows.append(cached_row)
            continue
        attempt = 0
        while True:
            try:
                reservation = ledger.reserve(1)
            except Exception as exc:
                status = "STOPPED_BUDGET_EXHAUSTED"
                stop_reason = "reserve failed: %s: %s" % (type(exc).__name__, exc)
                stop_batch = True
                break
            charged += 1
            reservation_id = _reservation_id(reservation)
            try:
                sample = evaluator(item)
                if not isinstance(sample, EvaluationSample):
                    raise BatchContractError("evaluator must return EvaluationSample")
            except Exception as exc:
                reason = ("evaluator raised before accounting settled: %s: %s"
                          % (type(exc).__name__, exc))
                try:
                    _stop_reservation(ledger, reservation, reason=reason)
                except Exception as stop_exc:
                    stop_reason = reason + "; reservation stop failed: %s: %s" % (
                        type(stop_exc).__name__, stop_exc)
                    rows.append(_row(item, index, attempt, None,
                                     reservation_id=reservation_id, cached=False,
                                     failure_kind="ACCOUNTING_VIOLATION",
                                     detail=stop_reason[:300]))
                    status = "STOPPED_ACCOUNTING_VIOLATION"
                    stop_batch = True
                    break
                rows.append(_row(item, index, attempt, None,
                                 reservation_id=reservation_id, cached=False,
                                 failure_kind="INFRA_ERROR",
                                 detail=reason[:300]))
                status = "STOPPED_INFRA_ERROR"
                stop_reason = reason[:300]
                stop_batch = True
                break
            try:
                if sample.solver_started:
                    if sample.internal_solver_cases:
                        ledger.settle(reservation, 1,
                                      internal_solver_cases=sample.internal_solver_cases)
                    else:
                        ledger.settle(reservation, 1)
                    starts_issued += 1
                else:
                    ledger.cancel(reservation)
                ledger.register_evaluation(cache_hit=False,
                                           started=sample.solver_started,
                                           valid=sample.status == "ok")
            except Exception as exc:
                status = "STOPPED_ACCOUNTING_VIOLATION"
                stop_reason = "accounting rejected the sample: %s: %s" % (
                    type(exc).__name__, exc)
                if not getattr(reservation, "settled", False):
                    try:
                        _stop_reservation(ledger, reservation,
                                          reason=stop_reason[:300])
                    except Exception as stop_exc:
                        stop_reason += "; reservation stop failed: %s: %s" % (
                            type(stop_exc).__name__, stop_exc)
                rows.append(_row(item, index, attempt, sample,
                                 reservation_id=reservation_id, cached=False,
                                 failure_kind="ACCOUNTING_VIOLATION",
                                 detail=stop_reason[:300]))
                stop_batch = True
                break
            if (sample.status == "failed"
                    and sample.failure_kind in INVALID_DESIGN_FAILURES
                    and callable(getattr(ledger, "register_invalid_design", None))):
                ledger.register_invalid_design()
            row = _row(item, index, attempt, sample,
                       reservation_id=reservation_id, cached=False)
            rows.append(row)
            retryable = (sample.status == "failed"
                         and sample.failure_kind in RETRYABLE_FAILURES
                         and attempt < plan.authorization.retries
                         and starts_issued < plan.authorization.max_starts)
            if retryable:
                attempt += 1
                retries_used += 1
                continue
            seen[key] = row
            break

    finished_clock = float(clock())
    physical = int(getattr(ledger, "physical_solver_starts", 0))
    simulated = int(getattr(ledger, "simulated_solver_starts", 0))
    ledger_internal = int(getattr(ledger, "internal_solver_cases", 0))
    result: Dict[str, Any] = {
        "schema": SCHEMA_RESULT,
        "scope": SCOPE,
        "run_id": plan.authorization.run_id,
        "batch_id": plan.authorization.batch_id,
        "authorization_id": plan.authorization.authorization_id,
        "authorization_sha256": plan.authorization.sha256,
        "plan_sha256": plan.plan_sha256,
        "status": status,
        "stop_reason": stop_reason,
        "controls": {
            "max_starts": plan.authorization.max_starts,
            "solver_timeout_s": plan.authorization.solver_timeout_s,
            "retries": plan.authorization.retries,
            "parallel": plan.authorization.parallel,
            "max_batch_wall_s": plan.authorization.max_batch_wall_s,
            "physical_go": plan.authorization.physical_go,
            "a5_verdict": plan.authorization.a5_verdict,
            "new_r2_gate": plan.authorization.new_r2_gate,
        },
        "accounting": {
            "physical_solver_starts_actual": physical,
            "simulated_solver_starts_actual": simulated,
            "internal_solver_cases_actual": ledger_internal,
            "charged_planned_reserved": charged,
            "planned_reserved": charged,
            "design_evaluations": sum(1 for row in rows if not row["cached"]),
            "cached_reads": sum(1 for row in rows if row["cached"]),
            "failed_evaluations": sum(1 for row in rows if row["status"] == "failed"),
            "retries_used": retries_used,
            "starts_issued": starts_issued,
        },
        "items": rows,
        "item_count": len(plan.items),
        "evaluator": getattr(evaluator, "__qualname__", type(evaluator).__name__),
        "wall_s": round(finished_clock - started_clock, 6),
        "evidence_grade": "SOFTWARE_CONTROL_PATH_ONLY",
    }
    result["result_sha256"] = canonical_sha(result)
    return result


def verify_result(result: Mapping[str, Any]) -> None:
    if not isinstance(result, Mapping):
        raise BatchContractError("result must be a mapping")
    if result.get("schema") != SCHEMA_RESULT:
        raise BatchContractError("unexpected result schema")
    claimed = result.get("result_sha256")
    payload = {key: value for key, value in result.items() if key != "result_sha256"}
    if claimed != canonical_sha(payload):
        raise BatchContractError("result_sha256 does not match its payload")
    accounting = result.get("accounting") or {}
    if int(accounting.get("physical_solver_starts_actual", 0)) != 0 and result.get("scope") == SCOPE:
        raise BatchContractError(
            "offline skeleton result cannot report physical solver starts")


def write_result(result: Mapping[str, Any], path: str | Path) -> Dict[str, Any]:
    verify_result(result)
    raw = json.dumps(dict(result), sort_keys=True, indent=2,
                     ensure_ascii=False, allow_nan=False) + chr(10)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw.encode("utf-8"))
    return {"path": str(target), "bytes": len(raw.encode("utf-8")),
            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}


def load_result(path: str | Path) -> Dict[str, Any]:
    target = Path(path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    verify_result(payload)
    return payload


def module_source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
