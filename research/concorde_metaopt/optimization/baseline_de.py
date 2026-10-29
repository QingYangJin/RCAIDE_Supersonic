"""P4 constrained differential-evolution baseline on the shared RCAIDE evaluator.

The differential evolution (DE/rand/1/bin) loop is implemented here because the
maml-opt package ships a Bayesian optimiser but no DE; the existing tutorial DE
code is a parallel process-pool driver for a different RCAIDE Nexus and cannot
be reused for the frozen 15D single-cruise evaluator without rewriting it. This
module therefore provides a small deterministic, single-process DE that consumes
the same budget ledger, the same frozen design space and the same ten g <= 0
constraints as the Bayesian baseline, so the two algorithms can be compared at
equal true-evaluation budgets.

The optimiser works in the unit hypercube [0, 1]^15 and decodes every candidate
with the frozen design space before the mission is evaluated. No objective value
is fabricated: designs whose mission fails or is invalid stay infeasible with a
null objective in the ledger and in the trace.

Selection uses the standard feasibility rules: a feasible candidate beats an
infeasible incumbent; between two infeasible designs the smaller total positive
constraint violation wins; between two feasible designs the smaller fuel burn
wins. Invalid/failed evaluations never replace an incumbent.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import numpy as np

from maml_opt.initialization import generate_initial_designs

from ..aircraft.design_space import DesignSpace, load_design_space
from ..aircraft.geometry_checks import (
    _display_path,
    _git_sha,
    _software_versions,
    _write_csv,
    _write_json,
)
from ..aircraft.geometry_model import GEOMETRY_MODEL_VERSION
from ..evaluation.ledger import (
    BudgetExceeded,
    EvaluationLedger,
    design_id as design_identifier,
)
from ..evaluation.low_fidelity import SingleCruiseBackend
from ..tasks.task_spec import TASK_SPEC_VERSION, FixedCruiseTask, load_task_spec
from .baseline_bo import (
    BaselineError,
    _artifact_manifest,
    _branch,
    _sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"
STAGE = "P4"
METHOD = "ordinary_differential_evolution"
ALGORITHM = "de"
BASELINE_VERSION = "p4-2026-10-29"
FIDELITY_SINGLE_CRUISE = "single_cruise"
DEFAULT_BUDGET = 30
DEFAULT_POPULATION_SIZE = 15
MIN_POPULATION_SIZE = 4
DEFAULT_MUTATION_FACTOR = 0.5
DEFAULT_CROSSOVER_RATE = 0.7
TRACE_FILENAME = "opt_trace.jsonl"
OBSERVATIONS_FILENAME = "observations.csv"
EVALUATIONS_FILENAME = "evaluations.jsonl"
MAX_REQUESTS_PER_BUDGET = 4.0

TraceCallback = Callable[[Dict[str, Any]], None]
Evaluator = Callable[[List[float]], Mapping[str, Any]]


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _constraint_violation(result: Mapping[str, Any]) -> float:
    constraints = result.get("constraints_g_le_zero") or {}
    total = 0.0
    for value in constraints.values():
        number = _finite(value)
        if number is not None and number > 0.0:
            total += number
    return total


def _is_feasible(result: Mapping[str, Any]) -> bool:
    return bool(result.get("valid")) and bool(result.get("feasible"))


def _is_usable(result: Mapping[str, Any]) -> bool:
    return _is_feasible(result) or (
        bool(result.get("valid")) and _finite(result.get("objective")) is not None
    )


def _better(candidate: Mapping[str, Any], incumbent: Mapping[str, Any]) -> bool:
    """Standard DE feasibility rules for constrained minimisation."""
    if not _is_usable(candidate):
        return False
    candidate_feasible = _is_feasible(candidate)
    incumbent_feasible = _is_feasible(incumbent)
    if candidate_feasible and not incumbent_feasible:
        return True
    if incumbent_feasible and not candidate_feasible:
        return False
    if candidate_feasible and incumbent_feasible:
        candidate_objective = _finite(candidate.get("objective"))
        incumbent_objective = _finite(incumbent.get("objective"))
        if candidate_objective is None or incumbent_objective is None:
            return False
        return candidate_objective < incumbent_objective
    return _constraint_violation(candidate) < _constraint_violation(incumbent)


class DifferentialEvolutionBaseline:
    """Deterministic DE/rand/1/bin over a bounded unit hypercube."""

    def __init__(
        self,
        dimension: int,
        budget: int,
        seed: int = 42,
        population_size: Optional[int] = None,
        mutation_factor: float = DEFAULT_MUTATION_FACTOR,
        crossover_rate: float = DEFAULT_CROSSOVER_RATE,
        lower_bounds: Optional[Sequence[float]] = None,
        upper_bounds: Optional[Sequence[float]] = None,
    ) -> None:
        if type(dimension) is not int or dimension < 1:
            raise BaselineError("dimension must be a positive integer")
        if type(budget) is not int or budget < MIN_POPULATION_SIZE:
            raise BaselineError("budget must be an integer of at least %d" % MIN_POPULATION_SIZE)
        if type(seed) is not int or seed < 0:
            raise BaselineError("seed must be a non-negative integer")
        size = min(DEFAULT_POPULATION_SIZE, budget) if population_size is None else int(population_size)
        if size < MIN_POPULATION_SIZE:
            raise BaselineError("population size must be at least %d" % MIN_POPULATION_SIZE)
        if size > budget:
            raise BaselineError("population size must not exceed the evaluation budget")
        factor = float(mutation_factor)
        rate = float(crossover_rate)
        if not 0.0 < factor <= 1.0:
            raise BaselineError("mutation factor must be in (0, 1]")
        if not 0.0 <= rate <= 1.0:
            raise BaselineError("crossover rate must be in [0, 1]")
        self.dimension = dimension
        self.budget = budget
        self.seed = seed
        self.population_size = size
        self.mutation_factor = factor
        self.crossover_rate = rate
        self.lower_bounds = np.zeros(dimension) if lower_bounds is None else np.asarray(lower_bounds, dtype=float)
        self.upper_bounds = np.ones(dimension) if upper_bounds is None else np.asarray(upper_bounds, dtype=float)
        if self.lower_bounds.shape != (dimension,) or self.upper_bounds.shape != (dimension,):
            raise BaselineError("bounds must have one entry per dimension")
        if np.any(self.lower_bounds >= self.upper_bounds):
            raise BaselineError("every lower bound must be below its upper bound")
        self.rng = np.random.default_rng(seed)
        self._requests = 0
        self._physical_calls = 0
        self._evaluations_used = 0

    def _budget_left(self) -> bool:
        return (
            self._physical_calls < self.budget
            and self._requests < int(MAX_REQUESTS_PER_BUDGET * self.budget)
        )

    def _evaluate(
        self,
        evaluate: Evaluator,
        vector: np.ndarray,
        phase: str,
        generation: int,
        target_index: Optional[int],
    ) -> Dict[str, Any]:
        unit_vector = np.clip(np.asarray(vector, dtype=float), self.lower_bounds, self.upper_bounds)
        self._requests += 1
        try:
            result = dict(evaluate([float(value) for value in unit_vector]))
        except BudgetExceeded:
            self._requests -= 1
            raise
        self._evaluations_used += 1
        calls = result.get("analysis_calls")
        calls = int(calls) if isinstance(calls, int) and calls >= 0 else 0
        self._physical_calls += calls
        record = {
            "iteration": self._evaluations_used - 1,
            "phase": phase,
            "generation": generation,
            "target_index": target_index,
            "status": result.get("status"),
            "valid": bool(result.get("valid", False)),
            "feasible": bool(result.get("feasible", False)),
            "objective": _finite(result.get("objective")),
            "analysis_calls": calls,
            "constraint_violation": _constraint_violation(result),
            "unit_vector": [float(value) for value in unit_vector],
            "constraints_g_le_zero": {
                str(name): _finite(value) for name, value in (result.get("constraints_g_le_zero") or {}).items()
            },
        }
        if record["objective"] is None:
            record["objective"] = None
        return record

    def run(
        self,
        evaluate: Evaluator,
        on_record: Optional[TraceCallback] = None,
        baseline_vector: Optional[Sequence[float]] = None,
    ) -> Dict[str, Any]:
        initial = generate_initial_designs(
            self.lower_bounds,
            self.upper_bounds,
            self.population_size,
            seed=self.seed,
            baseline=np.asarray(baseline_vector, dtype=float) if baseline_vector is not None else None,
            method="lhs",
        )
        population: List[Dict[str, Any]] = []
        trace: List[Dict[str, Any]] = []
        stop_reason = None
        for index, vector in enumerate(initial):
            if not self._budget_left():
                stop_reason = "budget_exhausted"
                break
            record = self._evaluate(evaluate, np.asarray(vector, dtype=float), "initialisation", 0, index)
            record["accepted"] = True
            trace.append(record)
            if on_record is not None:
                on_record(record)
            population.append(
                {
                    "vector": np.asarray(vector, dtype=float),
                    "result": record,
                }
            )
        generations_completed = 0
        accepted_trials = 0
        rejected_trials = 0
        if stop_reason is None:
            generation = 1
            while True:
                if not self._budget_left():
                    stop_reason = "budget_exhausted"
                    break
                generation_accepted = 0
                for target_index in range(self.population_size):
                    if not self._budget_left():
                        stop_reason = "budget_exhausted"
                        break
                    picks = [index for index in range(self.population_size) if index != target_index]
                    r1, r2, r3 = (int(value) for value in self.rng.choice(picks, size=3, replace=False))
                    mutant = np.clip(
                        population[r1]["vector"]
                        + self.mutation_factor * (population[r2]["vector"] - population[r3]["vector"]),
                        self.lower_bounds,
                        self.upper_bounds,
                    )
                    trial = np.array(
                        [
                            mutant[index]
                            if self.rng.random() < self.crossover_rate or index == int(self.rng.integers(0, self.dimension))
                            else population[target_index]["vector"][index]
                            for index in range(self.dimension)
                        ],
                        dtype=float,
                    )
                    record = self._evaluate(evaluate, trial, "generation", generation, target_index)
                    accepted = _better(record, population[target_index]["result"])
                    record["accepted"] = bool(accepted)
                    trace.append(record)
                    if on_record is not None:
                        on_record(record)
                    if accepted:
                        accepted_trials += 1
                        generation_accepted += 1
                        population[target_index] = {"vector": trial, "result": record}
                    else:
                        rejected_trials += 1
                if stop_reason is not None:
                    break
                generations_completed = generation
                if generation_accepted == 0:
                    stop_reason = "no_accepted_trial_in_generation"
                    break
                generation += 1

        feasible_records = [record for record in trace if record["feasible"] and record["objective"] is not None]
        best_record = min(feasible_records, key=lambda record: record["objective"]) if feasible_records else None
        first_feasible = next(
            (record["iteration"] + 1 for record in trace if record["feasible"] and record["objective"] is not None),
            None,
        )
        invalid_count = sum(1 for record in trace if str(record.get("status", "")).startswith("GEOMETRY"))
        if not trace:
            status = "failed"
        elif best_record is None:
            status = "no_feasible_solution"
        elif stop_reason in (None,):
            status = "completed"
        else:
            status = "completed"
        return {
            "status": status,
            "termination_reason": stop_reason or "search_finished",
            "evaluations": len(trace),
            "physical_calls": self._physical_calls,
            "population_size": self.population_size,
            "generations_completed": generations_completed,
            "accepted_trials": accepted_trials,
            "rejected_trials": rejected_trials,
            "invalid_count": invalid_count,
            "first_feasible_evaluation": first_feasible,
            "best_feasible": (
                {
                    "objective": best_record["objective"],
                    "iteration": best_record["iteration"],
                    "unit_vector": best_record["unit_vector"],
                }
                if best_record is not None
                else None
            ),
            "iteration_best_feasible_objective": [
                (
                    min(
                        (
                            record["objective"]
                            for record in trace[: index + 1]
                            if record["feasible"] and record["objective"] is not None
                        ),
                        default=None,
                    )
                )
                for index in range(len(trace))
            ],
            "trace": trace,
            "final_population": [
                {"unit_vector": [float(value) for value in item["vector"]], "result": item["result"]}
                for item in population
            ],
        }


def _summary_base(run_id: str, git_sha: Optional[str]) -> Dict[str, Any]:
    versions = _software_versions()
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
        "status": "baseline_de_running",
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
        "objective": {"name": "fuel_burn_kg", "unit": "kg", "sense": "minimize"},
        "budget": None,
        "baseline_de": {
            "algorithm": ALGORITHM,
            "implementation": "P4 deterministic DE/rand/1/bin on the shared ledger",
            "version": BASELINE_VERSION,
        },
    }


def _environment(space: DesignSpace, task: FixedCruiseTask) -> Dict[str, Any]:
    import platform
    import sys

    return {
        "python": sys.version.split()[0],
        "python_executable": _display_path(sys.executable),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "geometry_model_version": GEOMETRY_MODEL_VERSION,
        "task_spec_version": TASK_SPEC_VERSION,
        "baseline_version": BASELINE_VERSION,
        "task_id": task.task_id,
        "packages": _software_versions(),
        "design_space_config": _display_path(space.config_path),
        "task_config": _display_path(task.config_path) if getattr(task, "config_path", None) else None,
    }


def _trace_rows(trace: Sequence[Mapping[str, Any]], space: DesignSpace) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in trace:
        unit_vector = list(record.get("unit_vector") or [])
        physical = space.from_unit_interval(unit_vector) if len(unit_vector) == len(space.variables) else {}
        row = {
            "iteration": record.get("iteration"),
            "phase": record.get("phase"),
            "generation": record.get("generation"),
            "target_index": record.get("target_index"),
            "design_id": design_identifier(physical) if physical else None,
            "selection_method": "lhs_initial" if record.get("phase") == "initialisation" else "de_trial",
            "status": record.get("status"),
            "valid": bool(record.get("valid", False)),
            "feasible": bool(record.get("feasible", False)),
            "objective": record.get("objective"),
            "analysis_calls": record.get("analysis_calls"),
            "constraint_violation": record.get("constraint_violation"),
            "accepted": record.get("accepted"),
            "design_vector_unit": unit_vector,
            "design": physical,
            "constraints_g_le_zero": record.get("constraints_g_le_zero") or {},
        }
        rows.append(row)
    return rows


def _observations_rows(trace_rows: Sequence[Mapping[str, Any]], space: DesignSpace) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in trace_rows:
        row: Dict[str, Any] = {
            "iteration": item.get("iteration"),
            "phase": item.get("phase"),
            "generation": item.get("generation"),
            "design_id": item.get("design_id"),
            "selection_method": item.get("selection_method"),
            "status": item.get("status"),
            "feasible": item.get("feasible"),
            "objective": item.get("objective"),
            "analysis_calls": item.get("analysis_calls"),
            "constraint_violation": item.get("constraint_violation"),
            "accepted": item.get("accepted"),
        }
        design = item.get("design") or {}
        for variable in space.variables:
            row[variable.id] = design.get(variable.name)
        rows.append(row)
    return rows


def _index_entry(run_dir: Path, summary: Mapping[str, Any]) -> Path:
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
    if raw_status.startswith("baseline_de_completed"):
        index_status = "completed"
    elif raw_status == "baseline_de_no_feasible_solution":
        index_status = "no_feasible_solution"
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
            "summary": {
                "status": summary.get("status"),
                "best_feasible_fuel_kg": summary.get("best_feasible_fuel_kg"),
                "total_true_evaluations": summary.get("total_true_evaluations"),
                "invalid_count": summary.get("invalid_count"),
                "failed_count": summary.get("failed_count"),
                "first_feasible_evaluation": summary.get("first_feasible_evaluation"),
                "algorithm": summary.get("algorithm"),
                "budget": summary.get("budget"),
            },
            "true_evaluations": summary.get("total_true_evaluations"),
        }
    )
    payload["runs"] = entries
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(index_path, payload, True)
    return index_path


def _run_readme(summary: Mapping[str, Any]) -> str:
    de = summary.get("baseline_de") or {}
    ledger = de.get("ledger") or {}
    best = summary.get("best_feasible_fuel_kg")
    return "\n".join(
        [
            "# %s" % summary["run_id"],
            "",
            "P4 differential-evolution baseline (DE/rand/1/bin) on the frozen P2",
            "single-cruise task. The evaluator and the budget ledger are the same",
            "ones used by the ordinary constrained BO baseline, so the two",
            "algorithms are compared at equal true-evaluation budgets. No SU2, CFD",
            "or learning-based initialisation was involved.",
            "",
            "- status: %s" % summary.get("status"),
            "- git_sha: %s (branch %s)" % (summary.get("git_sha"), summary.get("branch")),
            "- task: %s" % summary.get("task_id"),
            "- population size: %s, mutation factor F=%s, crossover CR=%s"
            % (de.get("population_size"), de.get("mutation_factor"), de.get("crossover_rate")),
            "- seed: %s" % summary.get("seed"),
            "- budget (true evaluations): %s" % summary.get("budget"),
            "- evaluations recorded: %s, generations completed: %s"
            % (summary.get("total_true_evaluations"), de.get("generations_completed")),
            "- termination reason: %s" % de.get("termination_reason"),
            "- first feasible evaluation: %s" % summary.get("first_feasible_evaluation"),
            "- best feasible fuel burn: %s kg" % best,
            "- best design id: %s" % summary.get("best_design_id"),
            "- invalid designs (geometry): %s, failed evaluations: %s"
            % (summary.get("invalid_count"), summary.get("failed_count")),
            "- cache hits: %s" % ledger.get("cache_hits"),
            "- wall seconds: %.2f" % (summary.get("wall_seconds") or 0.0),
            "",
            "Selection uses the standard DE feasibility rules: feasible beats",
            "infeasible, smaller positive violation beats larger between infeasible",
            "designs, and smaller fuel burn beats larger between feasible designs.",
            "Invalid or failed evaluations never replace an incumbent and are",
            "recorded with a null objective.",
            "",
            "Artefacts: summary.json, run_config.json, environment.json,",
            "best_design.json, evaluations.jsonl, opt_trace.jsonl, observations.csv,",
            "data_manifest.json, figures/convergence.png, figures/feasibility_rate.png.",
            "",
            "Figures are drawn from opt_trace.jsonl and can be regenerated without",
            "new mission evaluations with:",
            "",
            "    ./run_rcaide.cmd -m research.concorde_metaopt.reports.figures %s"
            % summary["run_id"],
            "",
        ]
    )


def run_baseline_de(
    output_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    budget: int = DEFAULT_BUDGET,
    seed: int = 42,
    population_size: Optional[int] = None,
    mutation_factor: float = DEFAULT_MUTATION_FACTOR,
    crossover_rate: float = DEFAULT_CROSSOVER_RATE,
    design_space: Optional[DesignSpace] = None,
    task: Optional[FixedCruiseTask] = None,
    backend: Any = None,
    allow_existing: bool = False,
) -> Dict[str, Any]:
    """Run the constrained DE baseline and write the evidence bundle."""
    started = time.perf_counter()
    cpu_started = time.process_time()
    space = design_space if design_space is not None else load_design_space()
    frozen_task = task if task is not None else load_task_spec()
    backend = backend if backend is not None else SingleCruiseBackend(
        design_space=space, task=frozen_task
    )
    search = DifferentialEvolutionBaseline(
        dimension=len(space.variables),
        budget=budget,
        seed=seed,
        population_size=population_size,
        mutation_factor=mutation_factor,
        crossover_rate=crossover_rate,
    )
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    generated = run_id or time.strftime("baseline-de-p4-%Y%m%dT%H%M%S", time.gmtime())
    run_dir = root / generated
    if run_dir.exists() and not allow_existing:
        raise FileExistsError("run directory already exists: %s" % run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "figures").mkdir(exist_ok=True)

    git_sha = _git_sha(REPO_ROOT)
    summary = _summary_base(generated, git_sha)
    summary["task_id"] = frozen_task.task_id
    summary["seed"] = int(seed)
    summary["branch"] = _branch()
    summary["design_dim"] = len(space.variables)
    summary["budget"] = int(budget)
    summary["baseline_de"].update(
        {
            "population_size": search.population_size,
            "mutation_factor": search.mutation_factor,
            "crossover_rate": search.crossover_rate,
            "starting_point": dict(space.baseline_dict()),
        }
    )
    preflight = backend.preflight()
    summary["baseline_de"]["preflight"] = json.loads(json.dumps(preflight, default=str))

    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": generated,
            "stage": STAGE,
            "method": METHOD,
            "algorithm": ALGORITHM,
            "version": BASELINE_VERSION,
            "git_sha": git_sha,
            "branch": summary["branch"],
            "seed": int(seed),
            "budget": int(budget),
            "population_size": search.population_size,
            "mutation_factor": search.mutation_factor,
            "crossover_rate": search.crossover_rate,
            "fidelity": FIDELITY_SINGLE_CRUISE,
            "task_id": frozen_task.task_id,
            "task_fingerprint": frozen_task.fingerprint(),
            "design_space_config": _display_path(space.config_path),
            "cache_enabled": True,
            "optimizer": "P4 deterministic DE/rand/1/bin on the shared ledger",
            "note": "Ordinary constrained DE baseline; shared P2 evaluator and budget ledger.",
        },
        True,
    )
    _write_json(run_dir / "environment.json", _environment(space, frozen_task), True)

    ledger = EvaluationLedger(budget=budget, run_dir=run_dir, cache_enabled=True)
    physical_calls = 0

    def evaluate(unit_vector: List[float]) -> Dict[str, Any]:
        nonlocal physical_calls
        if physical_calls >= budget:
            raise BudgetExceeded(budget, physical_calls)
        design = space.from_unit_interval(unit_vector)
        row = ledger.evaluate(backend, design, frozen_task, fidelity=FIDELITY_SINGLE_CRUISE)
        physical_calls += int(row.get("physical_call_count", 0) or 0)
        return {
            "status": row.get("status"),
            "valid": str(row.get("status")) == "VALID",
            "feasible": bool(row.get("feasible", False)),
            "objective": row.get("objective"),
            "constraints_g_le_zero": {
                str(name): value
                for name, value in (row.get("constraints") or {}).items()
                if value is not None
            },
            "analysis_calls": int(row.get("physical_call_count", 0) or 0),
        }

    baseline_vector = space.to_unit_interval(space.baseline_dict())
    try:
        search_result = search.run(evaluate, baseline_vector=baseline_vector)
    except BudgetExceeded:
        search_result = {
            "status": "interrupted",
            "termination_reason": "budget_exhausted",
            "evaluations": len(ledger.rows),
            "physical_calls": physical_calls,
            "population_size": search.population_size,
            "generations_completed": 0,
            "accepted_trials": 0,
            "rejected_trials": 0,
            "invalid_count": 0,
            "first_feasible_evaluation": None,
            "best_feasible": None,
            "trace": [],
        }

    trace_rows = _trace_rows(search_result.get("trace") or [], space)
    trace_path = run_dir / TRACE_FILENAME
    with trace_path.open("w", encoding="utf-8") as handle:
        for row in trace_rows:
            handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    _write_csv(run_dir / OBSERVATIONS_FILENAME, _observations_rows(trace_rows, space))

    ledger_summary = ledger.summary()
    best = ledger.best()
    valid_evaluations = sum(1 for row in ledger.rows if str(row.get("status")) == "VALID")
    feasible_evaluations = sum(1 for row in ledger.rows if bool(row.get("feasible")))
    if not ledger.rows:
        status = "baseline_de_failed"
    elif str(search_result.get("status")) == "no_feasible_solution" or best.get(
        "best_feasible_objective"
    ) is None:
        status = "baseline_de_no_feasible_solution"
    elif str(search_result.get("status")) == "interrupted":
        status = "baseline_de_interrupted"
    else:
        status = "baseline_de_completed"

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
            "Best feasible design from the ordinary constrained DE baseline; the objective is "
            "the single-cruise fuel burn in kg. No learned model is involved."
        ),
    }
    _write_json(run_dir / "best_design.json", best_design, True)
    summary["baseline_de"].update(
        {
            "search_status": search_result.get("status"),
            "valid_evaluations": valid_evaluations,
            "feasible_evaluations": feasible_evaluations,
            "termination_reason": search_result.get("termination_reason"),
            "generations_completed": search_result.get("generations_completed"),
            "accepted_trials": search_result.get("accepted_trials"),
            "rejected_trials": search_result.get("rejected_trials"),
            "ledger": ledger_summary,
            "baseline_objective": baseline_objective,
            "improvement_kg": improvement,
            "trace_file": TRACE_FILENAME,
            "observations_file": OBSERVATIONS_FILENAME,
            "note": "Deterministic single-process DE with the shared P2 evaluator and budget ledger.",
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
    try:
        from ..reports.figures import plot_optimizer_trace_artifacts

        figures = plot_optimizer_trace_artifacts(run_dir)
        summary["artifacts"]["figures"] = figures
        manifest_paths.extend(figures.values())
    except Exception as exc:  # pragma: no cover - plotting must not kill the run
        summary["baseline_de"]["figure_error"] = "%s: %s" % (type(exc).__name__, exc)
    _write_json(run_dir / "summary.json", summary, True)
    _write_json(run_dir / "data_manifest.json", _artifact_manifest(run_dir, manifest_paths), True)
    (run_dir / "README.md").write_text(_run_readme(summary), encoding="utf-8")
    _index_entry(run_dir, summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="P4 constrained differential-evolution baseline.")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--population-size", type=int, default=None)
    parser.add_argument("--mutation-factor", type=float, default=DEFAULT_MUTATION_FACTOR)
    parser.add_argument("--crossover-rate", type=float, default=DEFAULT_CROSSOVER_RATE)
    parser.add_argument("--allow-existing", action="store_true")
    args = parser.parse_args(argv)
    summary = run_baseline_de(
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        budget=args.budget,
        seed=args.seed,
        population_size=args.population_size,
        mutation_factor=args.mutation_factor,
        crossover_rate=args.crossover_rate,
        allow_existing=args.allow_existing,
    )
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if str(summary.get("status", "")).startswith("baseline_de_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
