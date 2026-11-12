"""Append-only accounting for real VSPAERO solver starts (D-REAL-001, A1).

Every real solver process start is recorded twice, in a single JSONL file:

* an event="start" line BEFORE the process is spawned, carrying
  physical_solver_starts=1 (the budget unit) and the full provenance
  (plan/approval digests, window token, executable, input hashes, argv, cwd);
* an event="end" line AFTER the process settles, carrying exit code, status,
  wall time and raw-output hashes, with physical_solver_starts=0 so that only
  genuine starts ever increment the budget.

Replay (P0 history replay, parsing of archived polars) must NEVER create a
start line; ReplayLedger is provided for that path and always reports zero
physical starts.  The ledger is fail-closed: an attempt is refused when the
approval is missing, the window is closed, the plan digest differs, the
attempt id is already present, or the batch budget is exhausted.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ATTEMPT_SCHEMA = "dreal001.solver_attempt.v1"
EVALUATION_SCHEMA = "dreal001.aero_eval.v1"
REPLAY_SCHEMA = "dreal001.replay_entry.v1"


class AccountingError(RuntimeError):
    """Raised when an attempt would break the pre-registered accounting contract."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: Optional[datetime] = None) -> str:
    return (moment or utc_now()).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_iso_utc(text: str) -> datetime:
    cleaned = text.strip().replace("Z", "+00:00")
    moment = datetime.fromisoformat(cleaned)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def approval_window_token(approval: Dict[str, Any]) -> Optional[str]:
    """Window token, accepted either at top level or nested under window.token (A5 B23).

    Lead approvals write both; older P0 approvals only wrote the top-level key.  The
    resolver is shared by the ledger, the batch driver and the case-approval builder so
    execution checks and ledger records always use one definition.
    """
    if not approval:
        return None
    token = approval.get("window_token")
    nested = (approval.get("window") or {}).get("token")
    return token or nested or None


def window_status(approval: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Return whether the approved solver window is open (fail-closed on any doubt)."""
    window = approval.get("window") or {}
    token = approval_window_token(approval)
    moment = (now or utc_now()).astimezone(timezone.utc)
    try:
        start = parse_iso_utc(window["start_utc"])
        end = parse_iso_utc(window["end_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        return {"open": False, "reason": "window.start_utc/end_utc missing or invalid: %r" % (exc,),
                "now_utc": iso_utc(moment), "token": token}
    open_now = start <= moment <= end
    remaining_s = (end - moment).total_seconds()
    return {
        "open": bool(open_now),
        "reason": "open" if open_now else "outside approved window",
        "now_utc": iso_utc(moment),
        "start_utc": iso_utc(start),
        "end_utc": iso_utc(end),
        "remaining_s": round(remaining_s, 3),
        "token": token,
        "token_source": ("window.token" if ((approval.get("window") or {}).get("token")
                                            and not approval.get("window_token")) else "window_token"),
    }


class SolverLedger:
    """Real-mode ledger: every start is a budgeted physical solver start."""

    mode = "real"

    def __init__(self, run_dir: str | Path, run_id: str, task_id: str) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.task_id = task_id
        self.attempts_path = self.run_dir / "solver_attempts.jsonl"
        self.evaluations_path = self.run_dir / "evaluations.jsonl"

    # -- read side ------------------------------------------------------
    def entries(self) -> List[Dict[str, Any]]:
        if not self.attempts_path.is_file():
            return []
        records: List[Dict[str, Any]] = []
        for line in self.attempts_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    def count_starts(self) -> int:
        return sum(1 for record in self.entries()
                   if record.get("event") == "start" and int(record.get("physical_solver_starts", 0)) > 0)

    def count_attempts(self) -> int:
        return len({record.get("attempt_id") for record in self.entries() if record.get("event") == "start"})

    def attempt_ids(self) -> List[str]:
        return sorted({str(record.get("attempt_id")) for record in self.entries()
                       if record.get("event") == "start"})

    def summary(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "attempts_path": str(self.attempts_path),
            "evaluations_path": str(self.evaluations_path),
            "physical_solver_starts": self.count_starts(),
            "attempt_count": self.count_attempts(),
        }

    # -- write side -----------------------------------------------------
    def _append(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, sort_keys=False)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def begin_attempt(
        self,
        attempt_id: str,
        case_id: str,
        argv: Sequence[str],
        cwd: str | Path,
        approval: Dict[str, Any],
        plan_sha256: str,
        approval_sha256: str,
        input_hashes: Dict[str, Any],
        exe_sha256: str,
        max_starts: int,
        extra: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
        batch_id: Optional[str] = None,
        design_hash: Optional[str] = None,
        x12: Optional[Sequence[float]] = None,
        geometry_source: Optional[str] = None,
        solver_version: Optional[str] = None,
        stdout_path: Optional[str] = None,
        stderr_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a start line or raise AccountingError without spawning anything.

        A5 B21: the start line carries the full case identity (batch_id, design_hash, x12,
        geometry_source, solver_version), the log paths, and start_ts_utc in addition to
        the legacy ts_utc field; window_token accepts the nested approval.window.token.
        """
        if not attempt_id:
            raise AccountingError("attempt_id is required for every solver start")
        if not approval or approval.get("approved") is not True:
            raise AccountingError("approval is missing or not approved")
        status = window_status(approval, now=now)
        if not status["open"]:
            raise AccountingError("solver window is not open: %s (%s)" % (status["reason"], status))
        approved_plan = approval.get("plan_sha256")
        if approved_plan and approved_plan != plan_sha256:
            raise AccountingError("plan sha256 %s != approved %s" % (plan_sha256, approved_plan))
        if approval.get("max_starts") is not None:
            max_starts = min(int(max_starts), int(approval["max_starts"]))
        if attempt_id in self.attempt_ids():
            raise AccountingError("attempt_id %s already recorded (no silent retries)" % attempt_id)
        starts = self.count_starts()
        if starts >= max_starts:
            raise AccountingError("budget exhausted: %d start(s) >= max_starts %d" % (starts, max_starts))
        started_utc = iso_utc(now)
        record = {
            "schema": ATTEMPT_SCHEMA,
            "event": "start",
            "attempt_id": attempt_id,
            "case_id": case_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "mode": self.mode,
            "ts_utc": started_utc,
            "start_ts_utc": started_utc,
            "physical_solver_starts": 1,
            "physical_solver_start": True,
            "batch_id": batch_id or approval.get("batch_id") or self.run_id,
            "design_hash": design_hash,
            "x12": list(x12) if x12 is not None else None,
            "geometry_source": geometry_source,
            "solver_version": solver_version,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "argv": list(argv),
            "cwd": str(cwd),
            "executable_sha256": exe_sha256,
            "plan_sha256": plan_sha256,
            "approval_sha256": approval_sha256,
            "window_token": approval_window_token(approval),
            "window": {key: status[key] for key in ("start_utc", "end_utc", "remaining_s")},
            "input_hashes": input_hashes,
            "starts_before": starts,
            "max_starts": max_starts,
            "starts_after": starts + 1,
        }
        if extra:
            record.update(extra)
        self._append(self.attempts_path, record)
        return record

    def end_attempt(
        self,
        attempt_id: str,
        exit_code: Optional[int],
        status: str,
        wall_s: float,
        outputs: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        internal_solver_cases: Optional[int] = None,
        internal_case_breakdown: Optional[Dict[str, Any]] = None,
        unique_flow_conditions: Optional[int] = None,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        settled_utc = iso_utc()
        record = {
            "schema": ATTEMPT_SCHEMA,
            "event": "end",
            "attempt_id": attempt_id,
            "case_id": case_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "mode": self.mode,
            "ts_utc": settled_utc,
            "end_ts_utc": settled_utc,
            "physical_solver_starts": 0,
            "exit_code": exit_code,
            "status": str(status),
            "wall_s": round(float(wall_s), 3),
            "outputs": outputs or {},
        }
        if internal_solver_cases is not None:
            record["internal_solver_cases"] = int(internal_solver_cases)
        if internal_case_breakdown is not None:
            record["internal_case_breakdown"] = internal_case_breakdown
        if unique_flow_conditions is not None:
            record["unique_flow_conditions"] = int(unique_flow_conditions)
        if note:
            record["note"] = note
        if extra:
            record.update(extra)
        self._append(self.attempts_path, record)
        return record

    def write_evaluation(self, record: Dict[str, Any]) -> None:
        payload = dict(record)
        payload.setdefault("schema", EVALUATION_SCHEMA)
        payload.setdefault("run_id", self.run_id)
        payload.setdefault("task_id", self.task_id)
        payload.setdefault("ts_utc", iso_utc())
        self._append(self.evaluations_path, payload)


class ReplayLedger(SolverLedger):
    """Zero-physical-start ledger used by the P0 history replay (never writes starts)."""

    mode = "replay"

    def begin_attempt(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:  # type: ignore[override]
        raise AccountingError("ReplayLedger forbids real solver starts by construction")

    def count_starts(self) -> int:
        return 0

    def write_replay_entry(self, record: Dict[str, Any]) -> None:
        payload = dict(record)
        payload.setdefault("schema", REPLAY_SCHEMA)
        payload.setdefault("mode", self.mode)
        payload.setdefault("source_kind", "REPLAY_HISTORICAL_POLAR")
        payload.setdefault("cache_hit", True)
        payload.setdefault("physical_solver_starts", 0)
        payload.setdefault("internal_solver_cases", 0)
        payload.setdefault("evidence_tier", "PARSER_AND_ACCOUNTING_REPLAY_ONLY")
        payload.setdefault("ts_utc", iso_utc())
        self._append(self.evaluations_path, payload)

