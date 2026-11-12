"""Pre-registered real/mock pilot runner for D-REAL-001 (A2).

The pilot is *preregistered before execution*: plan.json freezes the run matrix
(arm x budget x seed), solver configuration hash, stop conditions, warm-start
configuration and the physical_solver_starts budget per run. approval.json is a
template by default and must be signed (approved=true) before a REAL backend may
run; mock/replay pilots run without approval and are labelled as non-evidence.

Every run is self-contained: run_config.json, evaluations.jsonl,
solver_attempts.jsonl, optimization_history.csv, anytime_curve.csv,
arm_summary.json, summary.json, data_manifest.json, SHA256SUMS.txt.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .arms import ArmResult, ArmSpec, WarmStartSpec, run_arm, _write_csv
from .cache import EvaluationCache, VisibleLabelStore
from .constants import (
    ADAPTIVE_ARM_IDS,
    ALPHA_PRIMARY_DEG,
    ALPHA_REFINE_DEG,
    ARM_IDS,
    BACKEND_MOCK,
    BACKEND_REAL,
    BACKEND_REPLAY,
    DIMENSION,
    INTERNAL_SOLVER_CASES_PER_START,
    MAX_STARTS_PER_DESIGN,
    STATUS_VALID,
)
from .evaluators import (
    EvaluationRecorder,
    MockLiftMatchEvaluator,
    RealVspaeroAdapter,
    ReplayEvaluator,
)
from .ledger import SolverStartLedger
from .records import canonical_json, sha256_bytes, sha256_file, utc_now, write_json_atomic
from .task import DRealTaskSpec, build_task

DEFAULT_DESIGN_SPACE_PATH = "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
PLAN_SCHEMA = "dreal001.prereg.v1"
APPROVAL_SCHEMA = "dreal001.approval.v1"
RUN_SUMMARY_SCHEMA = "dreal001.run_summary.v1"
DEFAULT_STOP_CONDITIONS = (
    "STOP file present in batch directory",
    "budget exhausted (starts_used == approved max_starts)",
    "invalid-design rate > 0.20 over first 16 evaluations",
    "valid_solve_rate < 0.50 over first 16 evaluations",
    "wall clock > approved max_wall_minutes",
    "solver version / geometry hash mismatch against run_config.json",
    "any accounting violation (SolverStartLedger accounting)",
)


class PilotError(RuntimeError):
    """Pilot configuration / state error."""


class PilotNotApproved(PilotError):
    """A REAL pilot was requested without an approved plan."""


class PilotStateError(PilotError):
    """Dirty or inconsistent batch directory."""


def current_git_sha(cwd: Optional[Any] = None) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=None if cwd is None else str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _sha_or_empty(path: Optional[Any]) -> str:
    if path is None:
        return ""
    candidate = Path(path)
    if not candidate.exists():
        return ""
    return sha256_file(candidate)


@dataclass(frozen=True)
class PreregistrationConfig:
    batch_id: str
    phase: str = "P2"
    backend: str = BACKEND_MOCK
    arms: Tuple[str, ...] = ARM_IDS
    budgets: Tuple[int, ...] = (64,)
    seeds: Tuple[int, ...] = (0, 1, 2)
    initial_designs: int = 5
    max_evaluations_factor: int = 4
    warmstart: WarmStartSpec = field(default_factory=lambda: WarmStartSpec(source="zero_shot_surrogate", support_size=16, candidate_pool_size=256, seed=42))
    design_space_path: str = DEFAULT_DESIGN_SPACE_PATH
    design_space_config_id: str = "design_space_12d_lifting_surfaces"
    stop_conditions: Tuple[str, ...] = DEFAULT_STOP_CONDITIONS
    references: Tuple[str, ...] = (
        "docs/planning/dreal001_vspaero_large_scale_optimization_20261110.md",
        "docs/planning/dreal001_execution_governance_20261110.md",
        "D-REAL-001 / GitHub Issue #9",
    )
    window_start_utc: str = ""
    window_end_utc: str = ""
    replay_records_path: str = ""
    max_total_starts: Optional[int] = None
    notes: str = ""

    def __post_init__(self) -> None:
        for arm in self.arms:
            if arm not in ARM_IDS:
                raise PilotError("unknown arm %r" % (arm,))
        if not self.arms or not self.budgets or not self.seeds:
            raise PilotError("arms, budgets and seeds must be non-empty")
        if any(int(b) < 1 for b in self.budgets):
            raise PilotError("budgets must be >= 1")
        if len(set(int(s) for s in self.seeds)) != len(self.seeds):
            raise PilotError("seeds must be unique")
        if self.backend not in (BACKEND_MOCK, BACKEND_REPLAY, BACKEND_REAL):
            raise PilotError("unknown backend %r" % (self.backend,))
        if self.backend == BACKEND_REPLAY and not self.replay_records_path:
            raise PilotError("replay backend needs replay_records_path")


def _budget_model(planned_starts: int) -> Dict[str, Any]:
    """A1 EVALUATOR_API v1.0 accounting model frozen into plan/approval.

    One vspaero.exe launch = 1 physical_solver_starts = 7 internal_solver_cases
    (fixed alpha grid, no per-alpha billing). One expected launch per design;
    at most MAX_STARTS_PER_DESIGN=2 (main + pre-registered refine).
    """
    starts = int(planned_starts)
    return {
        "budget_metric": "physical_solver_starts",
        "starts_per_design_expected": 1,
        "max_starts_per_design": int(MAX_STARTS_PER_DESIGN),
        "internal_solver_cases_per_start": int(INTERNAL_SOLVER_CASES_PER_START),
        "planned_internal_solver_cases": starts * int(INTERNAL_SOLVER_CASES_PER_START),
        #: every launch always runs the 7-case sweep, including a refine launch.
        "max_internal_solver_cases": starts * int(INTERNAL_SOLVER_CASES_PER_START),
        "min_distinct_designs_if_all_designs_refine": starts // int(MAX_STARTS_PER_DESIGN),
        "alpha_primary_deg": [float(value) for value in ALPHA_PRIMARY_DEG],
        "alpha_refine_deg": [float(value) for value in ALPHA_REFINE_DEG],
        "refine_policy": (
            "at most one pre-registered refine launch, only when the interpolated lift residual "
            "exceeds the tolerance; no adaptive alpha search. A1 v1.0 has no alpha override, so "
            "A2 currently does not spend the refine launch (reported gap)."
        ),
        "alpha_rows_are_not_billed": True,
    }


def _warmstart_dict(warm: Optional[WarmStartSpec]) -> Optional[Dict[str, Any]]:
    return None if warm is None else {
        "source": warm.source,
        "support_size": int(warm.support_size),
        "candidate_pool_size": int(warm.candidate_pool_size),
        "seed": int(warm.seed),
    }


def build_preregistration(
    config: PreregistrationConfig,
    *,
    task: Optional[DRealTaskSpec] = None,
    git_sha: str = "",
    created_ts_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a frozen plan dict (no approval; approval stays a template)."""
    task = build_task() if task is None else task
    matrix: List[Dict[str, Any]] = []
    for arm in config.arms:
        for budget in config.budgets:
            for seed in config.seeds:
                run_id = "%s__%s__B%03d__s%d" % (config.batch_id, arm.lower(), int(budget), int(seed))
                matrix.append(
                    {
                        "run_id": run_id,
                        "arm_id": arm,
                        "base_arm": "BO" if arm in ("BO", "ABO") else ("DE" if arm in ("DE", "ADE") else "PSO"),
                        "warmstart": arm in ADAPTIVE_ARM_IDS,
                        "budget_starts": int(budget),
                        "seed": int(seed),
                        "max_starts": int(budget),
                    }
                )
    planned_starts = int(sum(item["budget_starts"] for item in matrix))
    if config.max_total_starts is not None and planned_starts > int(config.max_total_starts):
        raise PilotError("planned_starts %d exceeds max_total_starts %d" % (planned_starts, int(config.max_total_starts)))
    per_arm: Dict[str, int] = {arm: 0 for arm in config.arms}
    for item in matrix:
        per_arm[item["arm_id"]] += int(item["budget_starts"])
    payload: Dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "batch_id": str(config.batch_id),
        "phase": str(config.phase),
        "backend": str(config.backend),
        "created_ts_utc": created_ts_utc or utc_now(),
        "git_sha": str(git_sha or current_git_sha()),
        "task_id": task.task_id,
        "task_version": task.version,
        "task_fingerprint": task.fingerprint(),
        "solver_config": dict(task.solver_config),
        "solver_config_sha256": task.solver_config_sha256,
        "task": task.to_dict(),
        "design_space_path": str(config.design_space_path),
        "design_space_config_id": str(config.design_space_config_id),
        "arms": list(config.arms),
        "budgets": [int(b) for b in config.budgets],
        "seeds": [int(s) for s in config.seeds],
        "planned_starts": planned_starts,
        "planned_starts_per_arm": per_arm,
        "initial_designs": int(config.initial_designs),
        "max_evaluations_factor": int(config.max_evaluations_factor),
        "warmstart": _warmstart_dict(config.warmstart),
        "warmstart_policy": "warm_start / surrogate scoring is label-free; A-arms see only in-run paid labels (VisibleLabelStore)",
        "budget_metric": "physical_solver_starts",
        "budget_model": _budget_model(planned_starts),
        "mock_metrics_note": "MOCK/REPLAY runs count simulated_solver_starts only; physical_solver_starts MUST be 0",
        "stop_conditions": list(config.stop_conditions),
        "references": list(config.references),
        "window": {"start_utc": str(config.window_start_utc), "end_utc": str(config.window_end_utc)},
        "replay_records_path": str(config.replay_records_path),
        "run_matrix": matrix,
        "run_matrix_sha256": sha256_bytes(canonical_json(matrix).encode("utf-8")),
        "fuel_burn_kg": None,
        "notes": str(config.notes),
    }
    payload["plan_sha256"] = sha256_bytes(canonical_json(payload).encode("utf-8"))
    return payload


def approval_template(plan: Mapping[str, Any], *, max_starts: Optional[int] = None, max_wall_minutes: int = 240) -> Dict[str, Any]:
    return {
        "schema_version": APPROVAL_SCHEMA,
        "batch_id": plan["batch_id"],
        "phase": plan["phase"],
        "backend": plan["backend"],
        "plan_sha256": plan["plan_sha256"],
        "run_matrix_sha256": plan["run_matrix_sha256"],
        "approved": False,
        "approved_by": "",
        "approved_ts_utc": "",
        "max_starts": int(max_starts if max_starts is not None else plan["planned_starts"]),
        "max_internal_solver_cases": int(
            (max_starts if max_starts is not None else plan["planned_starts"])
            * int(INTERNAL_SOLVER_CASES_PER_START)
        ),
        "budget_model": dict(plan.get("budget_model") or _budget_model(int(max_starts if max_starts is not None else plan["planned_starts"]))),
        "max_wall_minutes": int(max_wall_minutes),
        "conditions": [
            "P0 engineering freeze PASS",
            "P1 numerical/physics SOLVER_INTERNAL_PASS signed (A5)",
            "approval.json approved=true and plan_sha256 matches plan.json",
            "no concurrent real solver batch scheduled by the Lead",
        ],
        "note": "TEMPLATE ONLY: REAL runs are refused until approved=true; mock/replay pilots do not need approval but are not physical evidence.",
    }


def write_preregistration(
    output_dir: Any,
    config: PreregistrationConfig,
    *,
    task: Optional[DRealTaskSpec] = None,
    git_sha: str = "",
) -> Dict[str, Any]:
    """Write plan.json + approval.json (template) and bind plan_sha256 to file bytes."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan = build_preregistration(config, task=task, git_sha=git_sha)
    plan_path = out / "plan.json"
    plan_path.write_text(canonical_json(plan) + "\n", encoding="utf-8")
    plan["plan_path"] = str(plan_path)
    plan["plan_sha256"] = sha256_file(plan_path)
    plan_path.write_text(canonical_json(plan) + "\n", encoding="utf-8")
    approval = approval_template(plan)
    approval_path = out / "approval.json"
    write_json_atomic(approval_path, approval)
    return {
        "plan": plan,
        "plan_path": str(plan_path),
        "plan_sha256": plan["plan_sha256"],
        "approval": approval,
        "approval_path": str(approval_path),
        "approval_sha256": sha256_file(approval_path),
        "batch_dir": str(out),
    }


def load_plan(path: Any) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_approval(path: Any) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_approval(plan: Mapping[str, Any], approval: Optional[Mapping[str, Any]]) -> None:
    """Fail closed: REAL execution requires a matching signed approval."""
    if not approval:
        raise PilotNotApproved("REAL pilot requires approval.json with approved=true")
    if not bool(approval.get("approved")):
        raise PilotNotApproved("approval.json approved is not true")
    if str(approval.get("plan_sha256", "")) != str(plan.get("plan_sha256", "")):
        raise PilotNotApproved("approval plan_sha256 does not match plan")
    if str(approval.get("batch_id", "")) != str(plan.get("batch_id", "")):
        raise PilotNotApproved("approval batch_id does not match plan")
    approved_max = int(approval.get("max_starts", 0) or 0)
    needed = int(plan.get("planned_starts", 0))
    if approved_max < needed:
        raise PilotNotApproved("approval max_starts %d < planned_starts %d" % (approved_max, needed))


def _manifest(directory: Path, exclude: Sequence[str]) -> List[Dict[str, Any]]:
    skip = {str(name) for name in exclude}
    rows: List[Dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(directory).as_posix()
        if rel in skip:
            continue
        rows.append({"path": rel, "bytes": int(path.stat().st_size), "sha256": sha256_file(path)})
    return rows


def _write_sha256sums(directory: Path, files: Sequence[Mapping[str, Any]], name: str = "SHA256SUMS.txt") -> Path:
    target = directory / name
    lines = ["%s  %s" % (row["sha256"], row["path"]) for row in files]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


def _run_evaluator(
    *,
    backend: str,
    design_space: Any,
    task: DRealTaskSpec,
    ledger: SolverStartLedger,
    run_dir: Path,
    batch_id: str,
    run_id: str,
    arm_id: str,
    seed: int,
    cache: EvaluationCache,
    label_store: VisibleLabelStore,
    recorder: EvaluationRecorder,
    plan: Mapping[str, Any],
    approval: Optional[Mapping[str, Any]],
    real_adapter_factory: Optional[Callable[..., Any]],
) -> Any:
    kwargs = dict(
        design_space=design_space,
        task=task,
        ledger=ledger,
        batch_id=batch_id,
        run_id=run_id,
        arm_id=arm_id,
        seed=seed,
        cache=cache,
        label_store=label_store,
        recorder=recorder,
        run_dir=run_dir,
    )
    if backend == BACKEND_MOCK:
        return MockLiftMatchEvaluator(**kwargs)
    if backend == BACKEND_REPLAY:
        return ReplayEvaluator(records_path=plan.get("replay_records_path") or None, **kwargs)
    if backend == BACKEND_REAL:
        validate_approval(plan, approval)
        if real_adapter_factory is not None:
            evaluator = real_adapter_factory(kwargs=kwargs, plan=plan, approval=approval)
        else:
            # Default wiring: import A1's AeroEvaluator read-only and stay
            # zero-physical (allow_physical_starts=False). P2a must inject a
            # factory with A1's ledgered spawn; A2 never launches vspaero.exe.
            from .real_backend import build_real_adapter

            forwarded = {
                key: value
                for key, value in kwargs.items()
                if key not in ("design_space", "task", "ledger", "run_dir")
            }
            evaluator = build_real_adapter(
                design_space=design_space,
                task=task,
                ledger=ledger,
                run_dir=run_dir,
                approval=approval,
                allow_physical_starts=False,
                **forwarded,
            )
        return evaluator
    raise PilotError("unknown backend %r" % (backend,))


def _write_run_artifacts(
    *,
    run_dir: Path,
    run_config: Mapping[str, Any],
    result: ArmResult,
    ledger: SolverStartLedger,
    label_store: VisibleLabelStore,
    cache: EvaluationCache,
    task: DRealTaskSpec,
    plan: Mapping[str, Any],
    approval: Optional[Mapping[str, Any]],
    backend: str,
) -> Dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(run_dir / "run_config.json", dict(run_config))
    result.write_artifacts(run_dir)
    cache.save(run_dir / "evaluation_cache.json")
    ledger.write_summary_json(run_dir / "ledger_summary.json")
    write_json_atomic(run_dir / "label_store.json", label_store.as_dict())
    attempt_rows = ledger.read_attempts()
    physical_from_attempts = ledger.physical_solver_starts_from_attempts()
    summary = {
        "schema_version": RUN_SUMMARY_SCHEMA,
        "batch_id": run_config["batch_id"],
        "run_id": run_config["run_id"],
        "arm_id": run_config["arm_id"],
        "seed": int(run_config["seed"]),
        "budget_starts": int(run_config["budget_starts"]),
        "backend": backend,
        "status": result.status,
        "physical_solver_starts": int(result.physical_solver_starts),
        "simulated_solver_starts": int(result.simulated_solver_starts),
        "starts_used": int(result.starts_used),
        "physical_solver_starts_from_attempts": int(physical_from_attempts),
        "physical_starts_authorized": bool(run_config.get("real_starts_authorized", False)),
        "internal_solver_cases": int(ledger.internal_solver_cases),
        "evaluations_requested": int(result.evaluations_requested),
        "unique_design_evals": int(result.unique_design_evals),
        "cached_reads": int(result.cached_reads),
        "valid_evals": int(result.valid_evals),
        "valid_solve_rate": float(result.valid_solve_rate),
        "first_feasible_solver_start": result.first_feasible_solver_start,
        "best_valid_D_i_N": result.best_valid_D_i_N,
        "best_design_unit": result.best_design_unit,
        "warmstart": dict(result.warmstart),
        "optimizer": dict(result.optimizer),
        "ledger": dict(result.ledger_summary),
        "n_solver_attempt_rows": len(attempt_rows),
        "n_label_rows_visible": len(label_store),
        "n_cache_entries": len(cache),
        "fuel_burn_kg": None,
        "evidence_class": "MOCK_SIMULATED" if backend == BACKEND_MOCK else ("ARCHIVE_REPLAY" if backend == BACKEND_REPLAY else "REAL_VSPAERO"),
        "synthetic_not_real_solver": bool(backend != BACKEND_REAL),
        "evidence_statement": (
            "SYNTHETIC_NOT_REAL_SOLVER" if backend != BACKEND_REAL else "REAL_VSPAERO_PENDING_INDEPENDENT_VALIDATION"
        ),
        "physical_validation_status": "NOT_VALIDATED" if backend != BACKEND_REAL else str(run_config.get("physical_validation_status", "PENDING_INDEPENDENT_VALIDATION")),
        "plan_sha256": str(plan.get("plan_sha256", "")),
        "approval_sha256": "" if approval is None else sha256_bytes(canonical_json(approval).encode("utf-8")),
        "git_sha": str(run_config.get("git_sha", "")),
        "created_ts_utc": utc_now(),
    }
    write_json_atomic(run_dir / "summary.json", summary)
    manifest = _manifest(run_dir, exclude=("data_manifest.json", "SHA256SUMS.txt"))
    write_json_atomic(
        run_dir / "data_manifest.json",
        {
            "schema_version": "dreal001.data_manifest.v1",
            "run_id": run_config["run_id"],
            "files": manifest,
            "n_files": len(manifest),
            "physical_solver_starts": int(result.physical_solver_starts),
            "simulated_solver_starts": int(result.simulated_solver_starts),
            "created_ts_utc": utc_now(),
        },
    )
    files = _manifest(run_dir, exclude=("SHA256SUMS.txt",))
    _write_sha256sums(run_dir, files)
    return summary


def run_pilot(
    output_root: Any,
    plan: Mapping[str, Any],
    *,
    task: Optional[DRealTaskSpec] = None,
    design_space: Any = None,
    backend: Optional[str] = None,
    approval: Optional[Mapping[str, Any]] = None,
    approval_path: Optional[Any] = None,
    resume: bool = True,
    force: bool = False,
    max_runs: Optional[int] = None,
    stop_file_name: str = "STOP",
    real_adapter_factory: Optional[Callable[..., Any]] = None,
    git_sha: str = "",
    created_ts_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the frozen plan matrix; resumable and stop-file aware."""
    from ...aircraft.design_space import load_design_space

    if task is None:
        task = build_task()
    if design_space is None:
        design_space = load_design_space(plan.get("design_space_path") or DEFAULT_DESIGN_SPACE_PATH)
    design_dim = int(getattr(design_space, "design_dim", 0) or 0)
    if design_dim != DIMENSION:
        raise PilotError("pilot requires the %dD design space, got design_dim=%r" % (DIMENSION, design_dim))
    backend = str(backend or plan.get("backend", BACKEND_MOCK))
    if backend not in (BACKEND_MOCK, BACKEND_REPLAY, BACKEND_REAL):
        raise PilotError("unknown backend %r" % (backend,))
    plan = dict(plan)
    plan.setdefault("plan_sha256", "")
    if plan.get("task_fingerprint") and str(plan["task_fingerprint"]) != task.fingerprint():
        raise PilotError("plan task fingerprint does not match task")
    if backend == BACKEND_REAL:
        validate_approval(plan, approval)
    batch_dir = Path(output_root) / str(plan["batch_id"])
    batch_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = batch_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    if approval_path is not None and approval is None:
        approval = load_approval(approval_path)
    if approval is None:
        approval_path_obj = batch_dir / "approval.json"
        if approval_path_obj.exists():
            approval = load_approval(approval_path_obj)
    approval_sha = "" if approval is None else sha256_bytes(canonical_json(approval).encode("utf-8"))
    stop_file = batch_dir / stop_file_name
    progress_path = batch_dir / "progress.jsonl"
    git = str(git_sha or plan.get("git_sha") or current_git_sha())
    from .records import append_jsonl

    executed: List[str] = []
    skipped: List[str] = []
    errors: List[Dict[str, Any]] = []
    stopped_early = False
    for entry in plan["run_matrix"]:
        if max_runs is not None and len(executed) >= int(max_runs):
            stopped_early = True
            break
        run_id = str(entry["run_id"])
        run_dir = runs_dir / run_id
        summary_path = run_dir / "summary.json"
        if resume and summary_path.exists():
            skipped.append(run_id)
            append_jsonl(progress_path, {"run_id": run_id, "status": "SKIPPED_EXISTING", "ts_utc": utc_now()})
            continue
        if run_dir.exists() and any(run_dir.iterdir()):
            if not force:
                raise PilotStateError(
                    "run dir %s has files but no summary.json; pass force=True or clean it" % run_dir
                )
            stale = runs_dir / ("_stale_%s_%s" % (run_id, utc_now().replace(":", "")))
            shutil.move(str(run_dir), str(stale))
        if stop_file.exists():
            stopped_early = True
            append_jsonl(progress_path, {"run_id": run_id, "status": "STOPPED_BY_FILE", "ts_utc": utc_now()})
            break
        budget = int(entry["budget_starts"])
        arm_id = str(entry["arm_id"])
        seed = int(entry["seed"])
        run_dir.mkdir(parents=True, exist_ok=True)
        ledger = SolverStartLedger(
            run_dir,
            batch_id=str(plan["batch_id"]),
            run_id=run_id,
            max_starts=budget,
            backend=backend,
            task_id=task.task_id,
            solver_config_sha256=task.solver_config_sha256,
            write_attempts=(backend != BACKEND_REAL),
        )
        cache = EvaluationCache(run_dir / "evaluation_cache.json")
        label_store = VisibleLabelStore(run_id)
        recorder = EvaluationRecorder(run_dir)
        warm_dict = plan.get("warmstart") if entry.get("warmstart") else None
        warm_spec = None if warm_dict is None else WarmStartSpec(
            source=str(warm_dict.get("source", "zero_shot_surrogate")),
            support_size=int(warm_dict.get("support_size", 0)),
            candidate_pool_size=int(warm_dict.get("candidate_pool_size", 256)),
            seed=int(warm_dict.get("seed", 42)),
        )
        spec = ArmSpec(
            arm_id=arm_id,
            budget_starts=budget,
            seed=seed,
            batch_id=str(plan["batch_id"]),
            run_id=run_id,
            initial_designs=int(plan.get("initial_designs", 5)),
            warmstart=warm_spec,
            max_evaluations_factor=int(plan.get("max_evaluations_factor", 4)),
        )
        run_config = {
            "schema_version": "dreal001.run_config.v1",
            "batch_id": str(plan["batch_id"]),
            "run_id": run_id,
            "arm_id": arm_id,
            "base_arm": spec.base_arm,
            "seed": seed,
            "budget_starts": budget,
            "max_starts": budget,
            "backend": backend,
            "phase": str(plan.get("phase", "")),
            "task_id": task.task_id,
            "task_version": task.version,
            "task_fingerprint": task.fingerprint(),
            "task": task.to_dict(),
            "solver_config": dict(task.solver_config),
            "solver_config_sha256": task.solver_config_sha256,
            "design_space_path": str(plan.get("design_space_path", "")),
            "design_space_sha256": _sha_or_empty(plan.get("design_space_path") or None),
            "design_space_config_id": str(plan.get("design_space_config_id", "")),
            "cache": {
                "enabled": True,
                "policy": "per_run_isolated",
                "cross_run_reuse": "forbidden" if backend == BACKEND_REAL else "not_applicable",
                "design_key": "sha256(canonical_x12||task_fingerprint||solver_config_sha256)",
                "real_entry_key": (
                    "sha256(design_key||mesh_family||normalized_geometry_hash)"
                    if backend == BACKEND_REAL
                    else None
                ),
                "mesh_family_stratified": backend == BACKEND_REAL,
                "ambiguous_family_policy": (
                    "re-measure; never mix mesh-family variants of one design"
                    if backend == BACKEND_REAL
                    else None
                ),
                "foreign_run_labels_visible": False,
            },
            "mesh_covariates": {
                "recorded": True,
                "fields": [
                    "mesh_family",
                    "mesh_nodes",
                    "mesh_elements",
                    "normalized_geometry_hash",
                    "vspgeom_sha256",
                ],
                "cross_family_numeric_comparison": "forbidden",
            },
            "budget_model": dict(plan.get("budget_model") or _budget_model(budget)),
            "a1_evaluator_contract": {
                "schema_version": "dreal001.aero_eval.v1",
                "module": "research.concorde_metaopt.dreal001.geometry.evaluator",
                "class": "AeroEvaluator",
                "evaluate_signature": "evaluate(x12_physical, case_id=..., meta=...) -> record dict",
                "x12_input": "12 physical values, frozen order W01..W10,V01,V02 (F01-F03 injected by A1)",
                "one_launch_is": {
                    "physical_solver_starts": 1,
                    "internal_solver_cases": int(INTERNAL_SOLVER_CASES_PER_START),
                    "alpha_rows_billed_separately": False,
                },
                "results_keys": ["alpha_deg", "cltot", "cdi", "cdo", "cdtot", "cmy"],
                "required_geometry_covariates_for_solved_valid": [
                    "mesh_family",
                    "normalized_geometry_hash",
                ],
                "attempt_ledger": "A1-owned solver_attempts.jsonl; A2 verifies design_hash rows against record physical_solver_starts",
                "real_starts_authorized": False,
                "authorization_note": (
                    "A2 never launches vspaero.exe; physical starts require Lead-approved batch, "
                    "A1 ledgered spawn and allow_physical_starts=True injected via real_adapter_factory"
                ),
            },
            "labels": {
                "policy": "in_run_paid_only",
                "visible_store": "VisibleLabelStore(run_id)",
                "warmstart_labels": "none at init; label-free prior only",
            },
            "warmstart": _warmstart_dict(warm_spec),
            "optimizer": {
                "type": spec.base_arm,
                "max_evaluations": int(spec.max_evaluations_factor) * budget,
                "population_size": spec.de_population_size() if spec.base_arm == "DE" else None,
                "swarm_size": spec.pso_swarm_size() if spec.base_arm == "PSO" else None,
                "initial_designs": spec.bo_initial_designs() if spec.base_arm == "BO" else None,
            },
            "physical_solver_starts_policy": "ledger-enforced; one launch per uncached design evaluation (max_launches_per_design=%d)" % int(task.max_launches_per_design),
            "approval": {
                "required": backend == BACKEND_REAL,
                "approved": bool(approval.get("approved")) if approval else False,
                "approval_sha256": approval_sha,
                "plan_sha256": str(plan.get("plan_sha256", "")),
            },
            "plan_sha256": str(plan.get("plan_sha256", "")),
            "git_sha": git,
            "fuel_burn_kg": None,
            "created_ts_utc": created_ts_utc or utc_now(),
        }
        write_json_atomic(run_dir / "run_config.json", run_config)
        try:
            evaluator = _run_evaluator(
                backend=backend,
                design_space=design_space,
                task=task,
                ledger=ledger,
                run_dir=run_dir,
                batch_id=str(plan["batch_id"]),
                run_id=run_id,
                arm_id=arm_id,
                seed=seed,
                cache=cache,
                label_store=label_store,
                recorder=recorder,
                plan=plan,
                approval=approval,
                real_adapter_factory=real_adapter_factory,
            )
            # The adapter factory decides whether A1 physical starts were
            # authorized; record the effective state (P2a: always false here).
            run_config["real_starts_authorized"] = bool(getattr(evaluator, "allow_physical_starts", False))
            write_json_atomic(run_dir / "run_config.json", run_config)
            result = run_arm(spec, task, design_space, evaluator)
            summary = _write_run_artifacts(
                run_dir=run_dir,
                run_config=run_config,
                result=result,
                ledger=ledger,
                label_store=label_store,
                cache=cache,
                task=task,
                plan=plan,
                approval=approval,
                backend=backend,
            )
            executed.append(run_id)
            append_jsonl(
                progress_path,
                {
                    "run_id": run_id,
                    "arm_id": arm_id,
                    "seed": seed,
                    "budget_starts": budget,
                    "status": "COMPLETED",
                    "physical_solver_starts": summary["physical_solver_starts"],
                    "simulated_solver_starts": summary["simulated_solver_starts"],
                    "best_valid_D_i_N": summary["best_valid_D_i_N"],
                    "ts_utc": utc_now(),
                },
            )
        except Exception as exc:  # noqa: BLE001 - batch continues, errors recorded
            errors.append({"run_id": run_id, "error": "%s: %s" % (type(exc).__name__, exc)})
            append_jsonl(progress_path, {"run_id": run_id, "status": "ERROR", "error": errors[-1]["error"], "ts_utc": utc_now()})
    batch_summary = _write_batch_summary(
        batch_dir=batch_dir,
        plan=plan,
        backend=backend,
        executed=executed,
        skipped=skipped,
        errors=errors,
        stopped_early=stopped_early,
        approval_sha256=approval_sha,
        git_sha=git,
    )
    return batch_summary


def _write_batch_summary(
    *,
    batch_dir: Path,
    plan: Mapping[str, Any],
    backend: str,
    executed: Sequence[str],
    skipped: Sequence[str],
    errors: Sequence[Mapping[str, Any]],
    stopped_early: bool,
    approval_sha256: str,
    git_sha: str,
) -> Dict[str, Any]:
    run_rows: List[Dict[str, Any]] = []
    runs_dir = batch_dir / "runs"
    expected_run_ids = {str(entry["run_id"]) for entry in plan.get("run_matrix", [])}
    for summary_path in sorted(runs_dir.glob("*/summary.json")):
        if summary_path.parent.name.startswith("_stale_"):
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if expected_run_ids and str(summary.get("run_id", "")) not in expected_run_ids:
            continue
        run_rows.append(
            {
                "run_id": summary["run_id"],
                "arm_id": summary["arm_id"],
                "seed": summary["seed"],
                "budget_starts": summary["budget_starts"],
                "backend": summary["backend"],
                "status": summary["status"],
                "starts_used": summary["starts_used"],
                "physical_solver_starts": summary["physical_solver_starts"],
                "simulated_solver_starts": summary["simulated_solver_starts"],
                "cached_reads": summary["cached_reads"],
                "valid_solve_rate": summary["valid_solve_rate"],
                "best_valid_D_i_N": summary["best_valid_D_i_N"],
                "first_feasible_solver_start": summary["first_feasible_solver_start"],
                "evidence_class": summary["evidence_class"],
                "fuel_burn_kg": None,
            }
        )
    metrics_fields = (
        "run_id", "arm_id", "seed", "budget_starts", "backend", "status",
        "starts_used", "physical_solver_starts", "simulated_solver_starts",
        "cached_reads", "valid_solve_rate", "best_valid_D_i_N",
        "first_feasible_solver_start", "evidence_class",
    )
    _write_csv(batch_dir / "batch_metrics.csv", metrics_fields, run_rows)
    total_physical = int(sum(int(row["physical_solver_starts"]) for row in run_rows))
    total_simulated = int(sum(int(row["simulated_solver_starts"]) for row in run_rows))
    batch_summary = {
        "schema_version": "dreal001.batch_summary.v1",
        "batch_id": plan["batch_id"],
        "phase": plan.get("phase", ""),
        "backend": backend,
        "plan_sha256": plan.get("plan_sha256", ""),
        "approval_sha256": approval_sha256,
        "git_sha": git_sha,
        "run_matrix_size": len(plan.get("run_matrix", [])),
        "executed_runs": list(executed),
        "skipped_existing_runs": list(skipped),
        "errors": list(errors),
        "stopped_early": bool(stopped_early),
        "n_runs_with_summary": len(run_rows),
        "physical_solver_starts": total_physical,
        "simulated_solver_starts": total_simulated,
        "planned_starts": int(plan.get("planned_starts", 0)),
        "budget_conserved": bool(total_physical + total_simulated <= int(plan.get("planned_starts", 0))),
        "backend_is_real_evidence": backend == BACKEND_REAL,
        "synthetic_not_real_solver": bool(backend != BACKEND_REAL),
        "evidence_statement": (
            "SYNTHETIC_NOT_REAL_SOLVER" if backend != BACKEND_REAL else "REAL_VSPAERO_PENDING_INDEPENDENT_VALIDATION"
        ),
        "fuel_burn_kg": None,
        "runs": run_rows,
        "created_ts_utc": utc_now(),
    }
    write_json_atomic(batch_dir / "batch_summary.json", batch_summary)
    manifest = _manifest(batch_dir, exclude=("data_manifest.json", "SHA256SUMS.txt", "batch_SHA256SUMS.txt"))
    write_json_atomic(
        batch_dir / "data_manifest.json",
        {
            "schema_version": "dreal001.batch_manifest.v1",
            "batch_id": plan["batch_id"],
            "files": manifest,
            "n_files": len(manifest),
            "physical_solver_starts": total_physical,
            "simulated_solver_starts": total_simulated,
            "created_ts_utc": utc_now(),
        },
    )
    files = _manifest(batch_dir, exclude=("batch_SHA256SUMS.txt",))
    _write_sha256sums(batch_dir, files, name="batch_SHA256SUMS.txt")
    return batch_summary


def preregistration_for_p2(batch_id: str, *, backend: str = BACKEND_MOCK, task: Optional[DRealTaskSpec] = None, design_space_path: str = "", seeds: Tuple[int, ...] = (0, 1, 2)) -> Dict[str, Any]:
    """P2 template: six arms, B=64/128, >=3 seeds (approval stays unsigned)."""
    config = PreregistrationConfig(
        batch_id=batch_id,
        phase="P2",
        backend=backend,
        arms=ARM_IDS,
        budgets=(64, 128),
        seeds=seeds,
        design_space_path=design_space_path,
        notes="P2 preregistered pilot template; not executable against REAL until approval.json approved=true",
    )
    return build_preregistration(config, task=task)
