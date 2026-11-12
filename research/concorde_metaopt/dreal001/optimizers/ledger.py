"""Solver-start accounting (governance v2 sec 5/6/7).

The primary fair-budget currency is physical_solver_starts. This ledger is
fail-closed: a launch must be reserved before it happens, and the number of
starts reported after the call must not exceed the reservation. MOCK runs write
their own append-only solver_attempts.jsonl rows with backend=MOCK,
physical_solver_starts=0 and simulated_solver_starts=1; they must never enter a
real evidence table. For REAL_VSPAERO runs A1 owns solver_attempts.jsonl and this
ledger only verifies its rows (no double counting).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .constants import BACKEND_REAL
from .records import SolverAttempt, append_jsonl, read_jsonl, write_json_atomic

try:  # make the base arm loops stop cleanly on budget exhaustion
    from ...f_line.budget import BudgetExceeded as _LineBudgetExceeded
except Exception:  # pragma: no cover - import guard only
    _LineBudgetExceeded = RuntimeError


class SolverBudgetExceeded(_LineBudgetExceeded):  # type: ignore[misc,valid-type]
    """Raised when a launch cannot be authorised inside the approved budget."""

    def __init__(self, message: str = "solver start budget exhausted", *, budget: int = 0, used: int = 0, requested: int = 1) -> None:
        RuntimeError.__init__(self, str(message))
        self.message = str(message)
        self.budget = int(budget)
        self.used = int(used)
        self.requested = int(requested)


class AccountingViolation(RuntimeError):
    """Raised when actual solver starts exceed the fail-closed reservation."""


@dataclass
class Reservation:
    reservation_id: int
    n_starts: int
    settled: bool = False
    used: int = 0


class SolverStartLedger:
    def __init__(
        self,
        run_dir: Optional[Any],
        *,
        batch_id: str,
        run_id: str,
        max_starts: int,
        backend: str,
        task_id: str = "",
        solver_config_sha256: str = "",
        write_attempts: Optional[bool] = None,
        attempts_path: Optional[Any] = None,
        mode: Optional[str] = None,
    ) -> None:
        if int(max_starts) < 0:
            raise ValueError("max_starts must be >= 0")
        self.run_dir = None if run_dir is None else Path(run_dir)
        self.batch_id = str(batch_id)
        self.run_id = str(run_id)
        self.task_id = str(task_id)
        self.solver_config_sha256 = str(solver_config_sha256)
        self.max_starts = int(max_starts)
        self.backend = str(backend)
        self.mode = str(mode or ("REAL" if backend == BACKEND_REAL else "SIMULATED"))
        if write_attempts is None:
            write_attempts = backend != BACKEND_REAL
        self.write_attempts = bool(write_attempts)
        if attempts_path is not None:
            self.attempts_path = Path(attempts_path)
        elif self.run_dir is not None:
            self.attempts_path = self.run_dir / "solver_attempts.jsonl"
        else:
            self.attempts_path = None
        self.evaluations_path = None if self.run_dir is None else self.run_dir / "evaluations.jsonl"

        self.physical_solver_starts = 0
        self.simulated_solver_starts = 0
        self.internal_solver_cases = 0
        self.evaluations_requested = 0
        self.unique_design_evals = 0
        self.cached_reads = 0
        self.invalid_design_evals = 0
        self.solver_started_evals = 0
        self.valid_evals = 0
        self._reservations: Dict[int, Reservation] = {}
        self._next_reservation = 1
        self._attempt_rows_written = 0

    # -- budget ---------------------------------------------------------
    @property
    def starts_used(self) -> int:
        return int(self.physical_solver_starts) + int(self.simulated_solver_starts)

    @property
    def starts_reserved(self) -> int:
        return sum(item.n_starts for item in self._reservations.values() if not item.settled)

    @property
    def remaining_starts(self) -> int:
        return int(self.max_starts) - self.starts_used

    def reserve(self, n_starts: int = 1) -> Reservation:
        requested = int(n_starts)
        if requested < 1:
            raise ValueError("reserve() needs at least 1 start")
        available = int(self.max_starts) - self.starts_used - self.starts_reserved
        if available <= 0:
            raise SolverBudgetExceeded(
                "budget exhausted for run %s: used=%d/%d reserved=%d"
                % (self.run_id, self.starts_used, self.max_starts, self.starts_reserved)
            )
        granted = min(requested, available)
        reservation = Reservation(reservation_id=self._next_reservation, n_starts=granted)
        self._next_reservation += 1
        self._reservations[reservation.reservation_id] = reservation
        return reservation

    def settle(self, reservation: Reservation, used: int, *, internal_solver_cases: int = 0) -> None:
        if reservation.reservation_id not in self._reservations:
            raise AccountingViolation("unknown reservation %r" % (reservation,))
        if reservation.settled:
            raise AccountingViolation("reservation %d settled twice" % reservation.reservation_id)
        count = int(used)
        if count < 0:
            raise AccountingViolation("negative solver-start usage: %d" % count)
        if count > reservation.n_starts:
            raise AccountingViolation(
                "actual solver starts (%d) exceed fail-closed reservation (%d) in run %s"
                % (count, reservation.n_starts, self.run_id)
            )
        reservation.used = count
        reservation.settled = True
        self.internal_solver_cases += int(internal_solver_cases)
        if self.mode == "REAL":
            self.physical_solver_starts += count
        else:
            self.simulated_solver_starts += count

    def cancel(self, reservation: Reservation) -> None:
        if reservation.settled:
            return
        reservation.settled = True
        reservation.used = 0

    # -- evaluations ----------------------------------------------------
    def register_evaluation(self, *, cache_hit: bool, started: bool, valid: bool) -> None:
        self.evaluations_requested += 1
        if cache_hit:
            self.cached_reads += 1
        else:
            self.unique_design_evals += 1
        if started:
            self.solver_started_evals += 1
        if valid:
            self.valid_evals += 1

    def register_invalid_design(self) -> None:
        self.invalid_design_evals += 1

    # -- attempts -------------------------------------------------------
    def next_attempt_id(self, case_id: str) -> Tuple[str, int]:
        sequence = self._attempt_rows_written + 1
        self._attempt_rows_written = sequence
        return "%s-a%02d" % (case_id, sequence), sequence

    def record_attempt(self, attempt: SolverAttempt) -> None:
        if not self.write_attempts:
            raise AccountingViolation(
                "ledger for backend %s must not write solver_attempts.jsonl (A1 owns it)" % self.backend
            )
        if self.attempts_path is None:
            raise AccountingViolation("no attempts_path configured for this ledger")
        append_jsonl(self.attempts_path, attempt.as_dict())

    def read_attempts(self) -> List[Dict[str, Any]]:
        if self.attempts_path is None:
            return []
        return read_jsonl(self.attempts_path)

    def physical_solver_starts_from_attempts(self) -> int:
        return int(sum(int(row.get("physical_solver_starts", 0)) for row in self.read_attempts()))

    def simulated_solver_starts_from_attempts(self) -> int:
        return int(sum(int(row.get("simulated_solver_starts", 0)) for row in self.read_attempts()))

    def verify_external_attempts(
        self,
        *,
        design_hash: Optional[str] = None,
        case_sha256: Optional[str] = None,
        expected_starts: Optional[int] = None,
    ) -> int:
        """Verify A1-owned solver_attempts.jsonl rows (REAL backend only)."""
        if self.attempts_path is None:
            raise AccountingViolation("REAL backend needs A1 solver_attempts.jsonl path to verify")
        rows = read_jsonl(self.attempts_path)
        selected = []
        for row in rows:
            if design_hash is not None and str(row.get("design_hash", "")) != str(design_hash):
                continue
            if case_sha256 is not None and str(row.get("case_sha256", "")) != str(case_sha256):
                continue
            selected.append(row)
        counted = int(sum(int(row.get("physical_solver_starts", 0)) for row in selected))
        if expected_starts is not None and counted != int(expected_starts):
            raise AccountingViolation(
                "A1 attempts ledger mismatch for run %s: rows=%d counted=%d expected=%d"
                % (self.run_id, len(selected), counted, int(expected_starts))
            )
        return counted

    # -- summary --------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        attempts = self.read_attempts()
        physical_from_file = int(sum(int(row.get("physical_solver_starts", 0)) for row in attempts))
        simulated_from_file = int(sum(int(row.get("simulated_solver_starts", 0)) for row in attempts))
        conservation_ok = int(self.evaluations_requested) == int(self.unique_design_evals) + int(self.cached_reads)
        return {
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "backend": self.backend,
            "mode": self.mode,
            "task_id": self.task_id,
            "solver_config_sha256": self.solver_config_sha256,
            "approved_max_starts": int(self.max_starts),
            "physical_solver_starts": int(self.physical_solver_starts),
            "simulated_solver_starts": int(self.simulated_solver_starts),
            "starts_used": int(self.starts_used),
            "remaining_starts": int(self.remaining_starts),
            "internal_solver_cases": int(self.internal_solver_cases),
            "evaluations_requested": int(self.evaluations_requested),
            "unique_design_evals": int(self.unique_design_evals),
            "cached_reads": int(self.cached_reads),
            "invalid_design_evals": int(self.invalid_design_evals),
            "solver_started_evals": int(self.solver_started_evals),
            "valid_evals": int(self.valid_evals),
            "attempt_rows": len(attempts),
            "physical_solver_starts_from_attempts": physical_from_file,
            "simulated_solver_starts_from_attempts": simulated_from_file,
            "attempts_file": "" if self.attempts_path is None else str(self.attempts_path),
            "conservation_ok": bool(conservation_ok),
            "budget_ok": bool(self.starts_used <= self.max_starts),
            "evaluations_conservation": "%d = %d unique + %d cached" % (
                self.evaluations_requested, self.unique_design_evals, self.cached_reads,
            ),
        }

    def assert_conserved(self) -> None:
        summary = self.summary()
        if not summary["conservation_ok"]:
            raise AccountingViolation("evaluation conservation broken: %s" % summary["evaluations_conservation"])
        if not summary["budget_ok"]:
            raise AccountingViolation("solver-start budget exceeded: %d > %d" % (self.starts_used, self.max_starts))

    def write_summary_json(self, path: Optional[Any] = None) -> Path:
        target = Path(path) if path is not None else (self.run_dir / "ledger_summary.json")
        return write_json_atomic(target, self.summary())
