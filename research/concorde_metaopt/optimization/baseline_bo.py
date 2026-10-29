"""P4 ordinary constrained Bayesian-optimisation baseline on the RCAIDE evaluator.

The search mechanics are reused from the real maml-opt package
(ConstrainedBayesianOptimizer, run_search and generate_initial_designs); this
module only supplies the Concorde evaluator adapter, the shared true-evaluation
ledger and the run artefacts required by the issue contract.

The optimiser works in the unit hypercube [0, 1]^15. Every proposed unit vector
is decoded with the frozen design space before the RCAIDE mission is evaluated,
and every evaluation is charged against the same budget ledger that later
route-A and route-B experiments must use. No objective value is fabricated:
infeasible or failed designs are recorded with a null objective.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from maml_opt.bayesian import ConstrainedBayesianOptimizer, run_search
from maml_opt.initialization import generate_initial_designs

from ..aircraft.design_space import DesignSpace, load_design_space
from ..aircraft.geometry_checks import (
    _display_path,
    _git_sha,
    _software_versions,
    _write_csv,
    _write_json,
    _write_jsonl,
)
from ..aircraft.geometry_model import GEOMETRY_MODEL_VERSION
from ..evaluation.contract import (
    CONSTRAINT_NAMES,
    FEASIBILITY_TOLERANCE,
    STATUS_VALID,
    optimizer_constraints,
)
from ..evaluation.ledger import (
    BudgetExceeded,
    EvaluationLedger,
    design_id as design_identifier,
)
from ..evaluation.low_fidelity import SingleCruiseBackend
from ..run_paths import RunPathError, resolve_run_directory
from ..tasks.task_spec import TASK_SPEC_VERSION, FixedCruiseTask, load_task_spec

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"
STAGE = "P4"
METHOD = "ordinary_constrained_bo"
ALGORITHM = "bo"
BASELINE_VERSION = "p4-2026-10-29"
FIDELITY_SINGLE_CRUISE = "single_cruise"
DEFAULT_BUDGET = 30
DEFAULT_INITIAL_DESIGN_COUNT = 5
DEFAULT_STRATEGY = "bayesian"
ALLOWED_STRATEGIES = ("bayesian", "random")
TRACE_FILENAME = "opt_trace.jsonl"
OBSERVATIONS_FILENAME = "observations.csv"
EVALUATIONS_FILENAME = "evaluations.jsonl"


class BaselineError(RuntimeError):
    """Raised when the baseline run request is invalid."""


def _branch() -> Optional[str]:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _maml_opt_version() -> Optional[str]:
    try:
        from importlib.metadata import version

        return version("maml-opt")
    except Exception:
        return None


def _summary_base(run_id: str, git_sha: Optional[str]) -> Dict[str, Any]:
    versions = _software_versions()
    versions["maml-opt"] = _maml_opt_version()
    return {
        "run_id": run_id,
        "stage": STAGE,
        "task_id": None,
        "method": METHOD,
        "algorithm": ALGORITHM,
        "seed": None,
        "git_sha": git_sha,
        "branch": None,
        "solver_versions": versions,
        "design_dim": None,
        "status": "baseline_bo_running",
        "total_true_evaluations": 0,
        "low_fidelity_calls": 0,
        "su2_calls": 0,
        "invalid_count": 0,
        "failed_count": 0,
        "first_feasible_evaluation": None,
        "best_feasible_fuel_kg": None,
        "best_design_id": None,
        "wall_seconds": None,
        "cpu_seconds_if_available": None,
        "artifacts": {},
        "objective": {
            "name": "fuel_burn_kg",
            "unit": "kg",
            "sense": "minimize",
        },
        "budget": None,
        "baseline_bo": {
            "algorithm": ALGORITHM,
            "implementation": "maml_opt.bayesian.ConstrainedBayesianOptimizer",
            "version": BASELINE_VERSION,
        },
    }


def _environment(space: DesignSpace, task: FixedCruiseTask) -> Dict[str, Any]:
    import platform
    import sys

    versions = _software_versions()
    versions["maml-opt"] = _maml_opt_version()
    return {
        "python": sys.version.split()[0],
        "python_executable": _display_path(sys.executable),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "geometry_model_version": GEOMETRY_MODEL_VERSION,
        "task_spec_version": TASK_SPEC_VERSION,
        "baseline_version": BASELINE_VERSION,
        "task_id": task.task_id,
        "packages": versions,
        "design_space_config": _display_path(space.config_path),
        "task_config": _display_path(task.config_path) if getattr(task, "config_path", None) else None,
    }


class _DuplicateTolerantOptimizer(ConstrainedBayesianOptimizer):
    """BO optimizer that keeps a cached duplicate proposal from aborting the search.

    maml-opt refuses to record the same design twice. A cache hit returns a
    zero-call evaluation of an already recorded design, so the duplicate
    observation carries no new information: dropping it is safe and keeps the
    run (and its evidence bundle) alive. This is a subclass, not a proxy,
    because run_search() accepts only a real ConstrainedBayesianOptimizer.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.duplicates_ignored = 0

    def tell(self, design_vector: Any, result: Any, selection: Any = None) -> Any:
        try:
            return super().tell(design_vector, result, selection=selection)
        except ValueError as exc:
            if "already been recorded" not in str(exc):
                raise
            self.duplicates_ignored += 1
            return None


def _evaluator_result(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert one ledger row into the result dict maml-opt tell() expects.

    The ledger already enforces the complete frozen constraint schema for a
    VALID row; this function re-checks it so a future ledger change cannot leak
    a partial mapping into the optimizer (an empty mapping would be treated as
    feasible by maml-opt). Constraint values are shifted by the contract
    feasibility tolerance because maml-opt tests g <= 0 exactly while the
    contract accepts |g| <= FEASIBILITY_TOLERANCE.
    """
    status = str(row.get("status", ""))
    constraints = row.get("constraints") or {}
    complete = all(constraints.get(name) is not None for name in CONSTRAINT_NAMES)
    valid = status == STATUS_VALID and complete and row.get("objective") is not None
    if status == STATUS_VALID and not complete:
        status = "INVALID_OR_MISSING_RESPONSE"
    shifted: Dict[str, float] = (
        optimizer_constraints(constraints) if valid else {}
    )
    physical = row.get("physical_call_count", 0)
    try:
        analysis_calls = int(physical)
    except (TypeError, ValueError):
        analysis_calls = 0
    result: Dict[str, Any] = {
        "status": status,
        "valid": bool(valid),
        "feasible": bool(row.get("feasible", False)) if valid else False,
        "objective": row.get("objective") if valid else None,
        "constraints_g_le_zero": shifted,
        "objective_model_eligible": True,
        "analysis_calls": analysis_calls,
        "analysis_calls_this_request": analysis_calls,
        "cache_hit": bool(row.get("cache_hit", False)),
        "design_id": row.get("design_id"),
    }
    if not valid:
        result["error"] = status
    return result


def _trace_row(
    observation: Mapping[str, Any],
    result: Mapping[str, Any],
    space: DesignSpace,
) -> Dict[str, Any]:
    unit_vector = [float(value) for value in observation.get("design_vector", [])]
    physical = space.from_unit_interval(unit_vector) if len(unit_vector) == len(space.variables) else {}
    selection = observation.get("selection") or {}
    row: Dict[str, Any] = {
        "iteration": observation.get("iteration"),
        "design_id": design_identifier(physical) if physical else None,
        "selection_method": selection.get("selection_method"),
        "model_status": selection.get("model_status"),
        "status": observation.get("status"),
        "valid": bool(observation.get("valid", False)),
        "feasible": bool(observation.get("feasible", False)),
        "objective": observation.get("objective"),
        "analysis_calls": observation.get("analysis_calls"),
        "objective_model_eligible": observation.get("objective_model_eligible", True),
        "design_vector_unit": unit_vector,
        "design": physical,
        "constraints_g_le_zero": result.get("constraints_g_le_zero", {}),
    }
    for key in ("acquisition_score", "probability_feasible", "expected_improvement", "initial_index"):
        if selection.get(key) is not None:
            row[key] = selection[key]
    return row


def _observations_rows(trace: Sequence[Mapping[str, Any]], space: DesignSpace) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in trace:
        row: Dict[str, Any] = {
            "iteration": item.get("iteration"),
            "design_id": item.get("design_id"),
            "selection_method": item.get("selection_method"),
            "status": item.get("status"),
            "feasible": item.get("feasible"),
            "objective": item.get("objective"),
            "analysis_calls": item.get("analysis_calls"),
        }
        design = item.get("design") or {}
        for variable in space.variables:
            row[variable.id] = design.get(variable.name)
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_manifest(run_dir: Path, relative_paths: Sequence[str]) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    for relative in relative_paths:
        path = run_dir / relative
        if path.is_file():
            files.append(
                {
                    "path": relative,
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return {
        "run_dir": _display_path(run_dir),
        "files": files,
        "note": "Hashes describe the committed small artefacts of this run.",
    }


def _index_summary(summary: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": summary.get("status"),
        "best_feasible_fuel_kg": summary.get("best_feasible_fuel_kg"),
        "total_true_evaluations": summary.get("total_true_evaluations"),
        "invalid_count": summary.get("invalid_count"),
        "failed_count": summary.get("failed_count"),
        "first_feasible_evaluation": summary.get("first_feasible_evaluation"),
        "algorithm": summary.get("algorithm"),
        "budget": summary.get("budget"),
    }


def _update_index(run_dir: Path, summary: Mapping[str, Any]) -> Path:
    index_path = run_dir.parent / "index.json"
    payload: Dict[str, Any] = {"runs": [], "updated_at": None}
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("runs"), list):
                payload = existing
        except json.JSONDecodeError:
            payload = {"runs": [], "updated_at": None}
    entries = [entry for entry in payload.get("runs", []) if entry.get("run_id") != summary["run_id"]]
    raw_status = str(summary.get("status") or "")
    if raw_status.startswith("baseline_bo_completed"):
        index_status = "completed"
    elif raw_status == "baseline_bo_no_feasible_solution":
        index_status = "no_feasible_solution"
    elif raw_status == "baseline_bo_failed":
        index_status = "failed"
    else:
        index_status = raw_status
    entries.append(
        {
            "run_id": summary["run_id"],
            "stage": STAGE,
            "task_id": summary.get("task_id"),
            "method": METHOD,
            "git_sha": summary.get("git_sha"),
            "status": index_status,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "path": run_dir.name,
            "summary": _index_summary(summary),
            "true_evaluations": summary.get("total_true_evaluations"),
        }
    )
    payload["runs"] = entries
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(index_path, payload, True)
    return index_path


def _run_readme(summary: Mapping[str, Any]) -> str:
    bo = summary.get("baseline_bo") or {}
    ledger = bo.get("ledger") or {}
    best = summary.get("best_feasible_fuel_kg")
    lines = [
        "# %s" % summary["run_id"],
        "",
        "P4 ordinary constrained Bayesian-optimisation baseline on the frozen P2",
        "single-cruise task. The optimiser is the real maml-opt constrained BO",
        "(GP surrogate, expected improvement times feasibility probability); the",
        "evaluator is the RCAIDE single-cruise mission with the ten frozen",
        "constraints. No SU2, CFD or learning-based initialisation was involved.",
        "",
        "- status: %s" % summary.get("status"),
        "- git_sha: %s (branch %s)" % (summary.get("git_sha"), summary.get("branch")),
        "- task: %s" % summary.get("task_id"),
        "- algorithm: %s (%s)" % (bo.get("implementation"), bo.get("strategy")),
        "- seed: %s" % summary.get("seed"),
        "- budget (max design evaluations): %s" % summary.get("budget"),
        "- initial designs: %s" % bo.get("initial_design_count"),
        "- true evaluations: %s" % summary.get("total_true_evaluations"),
        "- first feasible evaluation: %s" % summary.get("first_feasible_evaluation"),
        "- best feasible fuel burn: %s kg" % best,
        "- best design id: %s" % summary.get("best_design_id"),
        "- invalid designs (geometry): %s, failed evaluations: %s"
        % (summary.get("invalid_count"), summary.get("failed_count")),
        "- cache hits: %s" % ledger.get("cache_hits"),
        "- wall seconds: %.2f" % (summary.get("wall_seconds") or 0.0),
        "",
        "Artefacts: summary.json, run_config.json, environment.json,",
        "best_design.json, evaluations.jsonl, opt_trace.jsonl, observations.csv,",
        "data_manifest.json, figures/convergence.png, figures/feasibility_rate.png.",
        "",
        "The seed-42 initial design set includes the frozen baseline as its first",
        "point, so the first row of evaluations.jsonl is the baseline evaluation.",
        "Figures are drawn from opt_trace.jsonl and can be regenerated without new",
        "mission evaluations with:",
        "",
        "    ./run_rcaide.cmd -m research.concorde_metaopt.reports.figures %s" % summary["run_id"],
        "",
        "Limitations: the evaluator is the low-fidelity RCAIDE VLM plus turbojet",
        "deck, not a CFD result; no high-fidelity pairing exists yet, and the",
        "budget accounting here is only for the single-cruise mission calls.",
        "",
    ]
    return "\n".join(lines)


def run_baseline_bo(
    output_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    budget: int = DEFAULT_BUDGET,
    seed: int = 42,
    initial_design_count: int = DEFAULT_INITIAL_DESIGN_COUNT,
    strategy: str = DEFAULT_STRATEGY,
    design_space: Optional[DesignSpace] = None,
    task: Optional[FixedCruiseTask] = None,
    backend: Any = None,
    allow_existing: bool = False,
) -> Dict[str, Any]:
    """Run the ordinary constrained BO baseline and write the evidence bundle."""
    started = time.perf_counter()
    cpu_started = time.process_time()
    if type(budget) is not int or budget < 1:
        raise BaselineError("budget must be a positive integer")
    if type(initial_design_count) is not int or initial_design_count < 2:
        raise BaselineError("initial design count must be at least 2 (baseline plus one)")
    if initial_design_count > budget:
        raise BaselineError("initial design count must not exceed the evaluation budget")
    if strategy not in ALLOWED_STRATEGIES:
        raise BaselineError("strategy must be one of %s" % (ALLOWED_STRATEGIES,))
    if type(seed) is not int or seed < 0:
        raise BaselineError("seed must be a non-negative integer")

    space = design_space if design_space is not None else load_design_space()
    frozen_task = task if task is not None else load_task_spec()
    backend = backend if backend is not None else SingleCruiseBackend(
        design_space=space, task=frozen_task
    )
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    generated = (
        time.strftime("baseline-bo-p4-%Y%m%dT%H%M%S", time.gmtime())
        if run_id is None
        else run_id
    )
    try:
        run_dir = resolve_run_directory(root, generated, allow_existing=allow_existing)
    except RunPathError as exc:
        raise BaselineError(str(exc)) from exc
    (run_dir / "figures").mkdir(exist_ok=True)

    git_sha = _git_sha(REPO_ROOT)
    summary = _summary_base(generated, git_sha)
    summary["task_id"] = frozen_task.task_id
    summary["seed"] = int(seed)
    summary["branch"] = _branch()
    summary["design_dim"] = len(space.variables)
    summary["budget"] = int(budget)
    summary["baseline_bo"]["initial_design_count"] = int(initial_design_count)
    summary["baseline_bo"]["strategy"] = strategy
    summary["baseline_bo"]["starting_point"] = dict(space.baseline_dict())

    preflight = backend.preflight()
    preflight = json.loads(json.dumps(preflight, default=str))
    summary["baseline_bo"]["preflight"] = preflight

    _write_json(run_dir / "run_config.json", {
        "run_id": generated,
        "stage": STAGE,
        "method": METHOD,
        "algorithm": ALGORITHM,
        "version": BASELINE_VERSION,
        "git_sha": git_sha,
        "branch": summary["branch"],
        "seed": int(seed),
        "budget": int(budget),
        "initial_design_count": int(initial_design_count),
        "strategy": strategy,
        "fidelity": FIDELITY_SINGLE_CRUISE,
        "task_id": frozen_task.task_id,
        "task_fingerprint": frozen_task.fingerprint(),
        "design_space_config": _display_path(space.config_path),
        "cache_enabled": True,
        "optimizer": "maml_opt.bayesian.ConstrainedBayesianOptimizer",
        "note": "Ordinary constrained BO baseline; shared P2 evaluator and budget ledger.",
    }, True)
    _write_json(run_dir / "environment.json", _environment(space, frozen_task), True)

    ledger = EvaluationLedger(budget=budget, run_dir=run_dir, cache_enabled=True)
    trace: List[Dict[str, Any]] = []
    trace_path = run_dir / TRACE_FILENAME
    trace_handle = trace_path.open("w", encoding="utf-8")

    def evaluator(vector: np.ndarray) -> Dict[str, Any]:
        design = space.from_unit_interval([float(value) for value in np.asarray(vector, dtype=float)])
        try:
            row = ledger.evaluate(backend, design, frozen_task, fidelity=FIDELITY_SINGLE_CRUISE)
        except BudgetExceeded as exc:
            exc.analysis_calls = 0
            trace_handle.flush()
            raise
        return _evaluator_result(row)

    def on_observation(observation: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        row = _trace_row(observation, result, space)
        trace.append(row)
        trace_handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        trace_handle.flush()

    initial_designs = generate_initial_designs(
        np.zeros(len(space.variables), dtype=float),
        np.ones(len(space.variables), dtype=float),
        int(initial_design_count),
        seed=int(seed),
        baseline=np.asarray(space.to_unit_interval(space.baseline_dict()), dtype=float),
        method="lhs",
    )
    search_optimizer = _DuplicateTolerantOptimizer(
        lower_bounds=np.zeros(len(space.variables), dtype=float),
        upper_bounds=np.ones(len(space.variables), dtype=float),
        seed=int(seed),
    )
    try:
        search = run_search(
            search_optimizer,
            evaluator,
            initial_designs,
            int(budget),
            strategy=strategy,
            on_observation=on_observation,
        )
    finally:
        trace_handle.close()

    ledger_summary = ledger.summary()
    best = ledger.best()
    # The experiment status is derived from the ledger, not from the external
    # optimizer status: a cache hit, a failed evaluation or a tolerance-level
    # constraint must not turn an infeasible run into a "completed" one.
    valid_rows = [row for row in ledger.rows if str(row.get("status")) == STATUS_VALID]
    if not valid_rows:
        status = "baseline_bo_failed"
        outcome_note = "no VALID evaluation was recorded"
    elif best.get("best_feasible_objective") is None:
        status = "baseline_bo_no_feasible_solution"
        outcome_note = "valid evaluations exist but none satisfies every constraint"
    elif ledger_summary.get("failed_count"):
        status = "baseline_bo_completed_with_failures"
        outcome_note = "search completed with failed evaluations; the best feasible design is kept"
    else:
        status = "baseline_bo_completed"
        outcome_note = "search completed"

    elbow = time.perf_counter() - started
    cpu_elapsed = time.process_time() - cpu_started
    summary.update(
        {
            "status": status,
            "total_true_evaluations": ledger.physical_calls,
            "low_fidelity_calls": ledger.physical_calls,
            "su2_calls": 0,
            "invalid_count": ledger_summary.get("invalid_count", 0),
            "failed_count": ledger_summary.get("failed_count", 0),
            "first_feasible_evaluation": ledger_summary.get("first_feasible_evaluation"),
            "best_feasible_fuel_kg": best.get("best_feasible_objective"),
            "best_design_id": best.get("best_design_id"),
            "wall_seconds": round(elbow, 3),
            "cpu_seconds_if_available": round(cpu_elapsed, 3),
        }
    )
    baseline_row = ledger.rows[0] if ledger.rows else {}
    baseline_objective = baseline_row.get("objective")
    improvement = None
    if baseline_objective is not None and best.get("best_feasible_objective") is not None:
        improvement = round(float(baseline_objective) - float(best["best_feasible_objective"]), 9)

    best_design = {
        "run_id": generated,
        "stage": STAGE,
        "task_id": frozen_task.task_id,
        "method": METHOD,
        "algorithm": ALGORITHM,
        "best_feasible_objective": best.get("best_feasible_objective"),
        "objective_name": "fuel_burn_kg",
        "objective_unit": "kg",
        "best_design_id": best.get("best_design_id"),
        "best_design": best.get("best_design"),
        "first_feasible_evaluation": best.get("first_feasible_evaluation"),
        "baseline_design_id": baseline_row.get("design_id"),
        "baseline_objective": baseline_objective,
        "improvement_kg": improvement,
        "feasible": best.get("best_feasible_objective") is not None,
        "total_true_evaluations": ledger.physical_calls,
        "budget": int(budget),
        "starting_design": dict(space.baseline_dict()),
        "note": (
            "Best feasible design from the ordinary constrained BO baseline; the objective is "
            "the single-cruise fuel burn in kg. Predictions from any learned model are not used."
        ),
    }
    _write_json(run_dir / "best_design.json", best_design, True)
    observations = _observations_rows(trace, space)
    _write_csv(run_dir / OBSERVATIONS_FILENAME, observations)

    summary["baseline_bo"].update(
        {
            "search_status": search.get("status"),
            "termination_reason": search.get("termination_reason"),
            "design_evaluations": search.get("design_evaluations"),
            "valid_evaluations": search.get("valid_evaluations"),
            "feasible_evaluations": search.get("feasible_evaluations"),
            "objective_model_eligible_evaluations": search.get("objective_model_eligible_evaluations"),
            "optimizer_best_feasible": search.get("best_feasible"),
            "optimizer_iterations": len(search_optimizer.observations),
            "optimizer_raw_status": search.get("status"),
            "status_basis": "ledger",
            "outcome_note": outcome_note,
            "feasibility_tolerance": FEASIBILITY_TOLERANCE,
            "optimizer_constraint_shift": -FEASIBILITY_TOLERANCE,
            "duplicate_proposals_ignored": search_optimizer.duplicates_ignored,
            "budget_overruns": ledger_summary.get("budget_overruns"),
            "ledger": ledger_summary,
            "baseline_objective": baseline_objective,
            "improvement_kg": improvement,
            "trace_file": TRACE_FILENAME,
            "observations_file": OBSERVATIONS_FILENAME,
            "note": "Search mechanics from maml-opt; evaluator and budget ledger from this repository.",
        }
    )
    summary["artifacts"] = {
        "run_config": "run_config.json",
        "environment": "environment.json",
        "best_design": "best_design.json",
        "evaluations": EVALUATIONS_FILENAME,
        "opt_trace": TRACE_FILENAME,
        "observations": OBSERVATIONS_FILENAME,
        "data_manifest": "data_manifest.json",
        "figures_dir": "figures",
        "readme": "README.md",
    }
    _write_json(run_dir / "summary.json", summary, True)

    manifest_paths = [
        "summary.json",
        "run_config.json",
        "environment.json",
        "best_design.json",
        EVALUATIONS_FILENAME,
        TRACE_FILENAME,
        OBSERVATIONS_FILENAME,
    ]
    figure_error = None
    try:
        from ..reports.figures import plot_baseline_bo_artifacts

        figures = plot_baseline_bo_artifacts(run_dir)
        summary["artifacts"]["figures"] = figures
        manifest_paths.extend(figures.values())
    except Exception as exc:  # pragma: no cover - plotting must not kill the run
        figure_error = "%s: %s" % (type(exc).__name__, exc)
        summary["baseline_bo"]["figure_error"] = figure_error
    _write_json(run_dir / "summary.json", summary, True)
    _write_json(run_dir / "data_manifest.json", _artifact_manifest(run_dir, manifest_paths), True)
    (run_dir / "README.md").write_text(_run_readme(summary), encoding="utf-8")
    _update_index(run_dir, summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="P4 ordinary constrained BO baseline.")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--initial-designs", type=int, default=DEFAULT_INITIAL_DESIGN_COUNT)
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY, choices=list(ALLOWED_STRATEGIES))
    parser.add_argument("--allow-existing", action="store_true")
    args = parser.parse_args(argv)
    summary = run_baseline_bo(
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        budget=args.budget,
        seed=args.seed,
        initial_design_count=args.initial_designs,
        strategy=args.strategy,
        allow_existing=args.allow_existing,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if str(summary.get("status", "")).startswith("baseline_bo_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
