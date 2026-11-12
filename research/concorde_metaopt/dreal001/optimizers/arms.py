"""Six-arm runners over a shared lift-matched D_i evaluator.

Arms: BO, DE, PSO (base) and ABO, ADE, APSO (warm-started with the Issue #8
warm_start sampler/proxy). Fair budget is physical_solver_starts: each arm gets
the same B; base-arm optimizers receive B as their budget and the harness stops
any launch beyond the ledger cap. A-arm warm-start sampling/proxy scoring is
free of real labels (physical_call_count=0) and only in-run paid labels (from
the run's VisibleLabelStore) are visible to the surrogate.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .constants import (
    ADAPTIVE_ARM_IDS,
    BACKEND_MOCK,
    BASE_ARM_OF,
    DIMENSION,
    LIFT_TOL_REL,
    STATUS_VALID,
)
from .design import clip_x12
from .evaluators import BaseLiftMatchEvaluator
from .ledger import SolverBudgetExceeded
from .records import canonical_x12, design_hash as compute_design_hash, utc_now, write_json_atomic

try:
    from ...optimization.baseline_de import DifferentialEvolutionBaseline
    from ...optimization.baseline_pso import ParticleSwarmBaseline
except Exception as exc:  # pragma: no cover - import guard for partial checkouts
    DifferentialEvolutionBaseline = None  # type: ignore[assignment]
    ParticleSwarmBaseline = None  # type: ignore[assignment]
    _OPT_IMPORT_ERROR = repr(exc)
else:
    _OPT_IMPORT_ERROR = ""

try:
    from maml_opt.bayesian import ConstrainedBayesianOptimizer
    from maml_opt.initialization import generate_initial_designs
except Exception as exc:  # pragma: no cover
    ConstrainedBayesianOptimizer = None  # type: ignore[assignment]
    generate_initial_designs = None  # type: ignore[assignment]
    _MAML_IMPORT_ERROR = repr(exc)
else:
    _MAML_IMPORT_ERROR = ""

try:
    from ...warm_start.sampler import WarmStartConfig, WarmStartSampler
    from ...warm_start.surrogate import zero_shot_snapshot
except Exception as exc:  # pragma: no cover
    WarmStartConfig = None  # type: ignore[assignment]
    WarmStartSampler = None  # type: ignore[assignment]
    zero_shot_snapshot = None  # type: ignore[assignment]
    _WARM_START_IMPORT_ERROR = repr(exc)
else:
    _WARM_START_IMPORT_ERROR = ""

HISTORY_FIELDS = (
    "arm_id", "run_id", "seed", "evaluation_index", "solver_start_index",
    "design_hash", "x12_unit", "status", "valid", "feasible",
    "objective_D_i_N", "L_N", "L_ref_N", "lift_rel_error", "alpha_deg",
    "CLtot", "CDi", "Sref_m2", "q_Pa", "backend", "source_kind",
    "cache_hit", "physical_solver_starts", "simulated_solver_starts",
    "labels_visible_to_arm", "error_code", "phase",
)


@dataclass(frozen=True)
class WarmStartSpec:
    """Issue #8 warm_start configuration for A-arms (label-free proposal)."""

    source: str = "zero_shot_surrogate"
    support_size: int = 0
    candidate_pool_size: int = 256
    seed: int = 42


@dataclass(frozen=True)
class ArmSpec:
    arm_id: str
    budget_starts: int
    seed: int = 0
    batch_id: str = ""
    run_id: str = ""
    initial_designs: int = 5
    population_size: Optional[int] = None
    swarm_size: Optional[int] = None
    warmstart: Optional[WarmStartSpec] = None
    max_evaluations_factor: int = 4

    def __post_init__(self) -> None:
        if self.arm_id not in BASE_ARM_OF:
            raise ValueError("unknown arm_id %r (expected one of %s)" % (self.arm_id, tuple(BASE_ARM_OF)))
        if int(self.budget_starts) < 1:
            raise ValueError("budget_starts must be >= 1")

    @property
    def base_arm(self) -> str:
        return BASE_ARM_OF[self.arm_id]

    @property
    def is_adaptive(self) -> bool:
        return self.arm_id in ADAPTIVE_ARM_IDS

    def de_population_size(self) -> int:
        if self.population_size is not None:
            return int(self.population_size)
        return max(8, min(20, int(self.budget_starts) // 4))

    def pso_swarm_size(self) -> int:
        if self.swarm_size is not None:
            return int(self.swarm_size)
        return max(6, min(16, int(self.budget_starts) // 4))

    def bo_initial_designs(self) -> int:
        return max(2, min(int(self.initial_designs), max(2, int(self.budget_starts) // 2)))


@dataclass
class ArmResult:
    arm_id: str
    run_id: str
    batch_id: str
    seed: int
    budget_starts: int
    backend: str
    status: str
    evaluations_requested: int
    unique_design_evals: int
    cached_reads: int
    physical_solver_starts: int
    simulated_solver_starts: int
    starts_used: int
    valid_evals: int
    valid_solve_rate: float
    first_feasible_solver_start: Optional[int]
    best_valid_D_i_N: Optional[float]
    best_design_unit: Optional[List[float]]
    anytime: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    warmstart: Dict[str, Any] = field(default_factory=dict)
    optimizer: Dict[str, Any] = field(default_factory=dict)
    ledger_summary: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["created_ts_utc"] = utc_now()
        payload["fuel_burn_kg"] = None
        return payload

    def write_artifacts(self, output_dir: Any) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        write_json_atomic(out / "arm_summary.json", self.to_dict())
        _write_csv(out / "optimization_history.csv", HISTORY_FIELDS, self.history)
        _write_csv(
            out / "anytime_curve.csv",
            ("arm_id", "seed", "solver_starts", "evaluation_index", "best_valid_D_i_N", "last_status", "valid"),
            self.anytime,
        )
        return out


class ArmHarness:
    """Evaluator wrapper that enforces the start budget and records the trace."""

    def __init__(self, spec: ArmSpec, task: Any, design_space: Any, evaluator: BaseLiftMatchEvaluator) -> None:
        self.spec = spec
        self.task = task
        self.design_space = design_space
        self.evaluator = evaluator
        self.history: List[Dict[str, Any]] = []
        self.anytime: List[Dict[str, Any]] = []
        self.evaluation_index = 0
        self.best_D_i: Optional[float] = None
        self.best_vector: Optional[np.ndarray] = None
        self.first_feasible_solver_start: Optional[int] = None
        self.max_evaluations = int(spec.max_evaluations_factor) * int(spec.budget_starts)
        self.budget_exhausted = False
        self._starts_before = int(evaluator.ledger.starts_used)

    # -- budget ---------------------------------------------------------
    def _guard(self) -> None:
        ledger = self.evaluator.ledger
        if self.evaluator.requires_starts and ledger.remaining_starts <= 0:
            raise SolverBudgetExceeded(
                "arm %s reached its %d-start budget" % (self.spec.arm_id, ledger.max_starts)
            )
        if not self.evaluator.requires_starts and ledger.evaluations_requested >= int(self.spec.budget_starts):
            raise SolverBudgetExceeded(
                "arm %s reached replay evaluation budget %d" % (self.spec.arm_id, self.spec.budget_starts)
            )
        if len(self.history) >= self.max_evaluations:
            raise SolverBudgetExceeded("arm %s reached evaluation-request cap %d" % (self.spec.arm_id, self.max_evaluations))

    # -- evaluate -------------------------------------------------------
    def evaluate(self, unit_vector: Sequence[float], *, phase: str = "search") -> Dict[str, Any]:
        self._guard()
        vector = clip_x12(unit_vector)
        evaluation = self.evaluator.evaluate(vector)
        self.evaluation_index += 1
        ledger = self.evaluator.ledger
        starts_now = int(ledger.starts_used)
        row = {
            "arm_id": self.spec.arm_id,
            "run_id": self.spec.run_id,
            "seed": int(self.spec.seed),
            "evaluation_index": self.evaluation_index,
            "solver_start_index": starts_now,
            "design_hash": evaluation.design_hash,
            "x12_unit": [float(value) for value in vector],
            "status": evaluation.status,
            "valid": bool(evaluation.status == STATUS_VALID),
            "feasible": bool(
                evaluation.status == STATUS_VALID
                and (evaluation.lift_rel_error is None or float(evaluation.lift_rel_error) <= LIFT_TOL_REL)
            ),
            "objective_D_i_N": evaluation.D_i_N,
            "L_N": evaluation.L_N,
            "L_ref_N": evaluation.L_ref_N,
            "lift_rel_error": evaluation.lift_rel_error,
            "alpha_deg": evaluation.alpha_deg,
            "CLtot": evaluation.CLtot,
            "CDi": evaluation.CDi,
            "Sref_m2": evaluation.Sref_m2,
            "q_Pa": evaluation.q_Pa,
            "backend": evaluation.backend,
            "source_kind": evaluation.source_kind,
            "cache_hit": bool(evaluation.cache_hit),
            "physical_solver_starts": int(evaluation.physical_solver_starts),
            "simulated_solver_starts": int(evaluation.simulated_solver_starts),
            "labels_visible_to_arm": bool(evaluation.labels_visible_to_arm),
            "error_code": evaluation.error_code,
            "phase": str(phase),
        }
        self.history.append(row)
        if row["valid"] and row["objective_D_i_N"] is not None:
            value = float(row["objective_D_i_N"])
            if self.best_D_i is None or value < self.best_D_i:
                self.best_D_i = value
                self.best_vector = np.array(vector, dtype=float)
        if row["feasible"] and self.first_feasible_solver_start is None:
            self.first_feasible_solver_start = starts_now
        self.anytime.append(
            {
                "arm_id": self.spec.arm_id,
                "seed": int(self.spec.seed),
                "solver_starts": starts_now,
                "evaluation_index": self.evaluation_index,
                "best_valid_D_i_N": self.best_D_i,
                "last_status": evaluation.status,
                "valid": bool(row["valid"]),
            }
        )
        return {
            "status": evaluation.status,
            "valid": bool(row["valid"]),
            "feasible": bool(row["feasible"]),
            "objective": row["objective_D_i_N"],
            "constraints_g_le_zero": {
                "C00_lift_match_rel_error": (
                    float(evaluation.lift_rel_error) - LIFT_TOL_REL
                    if evaluation.lift_rel_error is not None
                    else (0.0 if row["valid"] else 1.0)
                )
            },
            "analysis_calls": int(evaluation.physical_solver_starts + evaluation.simulated_solver_starts),
            "cache_hit": bool(evaluation.cache_hit),
            "design_id": evaluation.design_hash,
            "error": evaluation.error_code,
        }

    # -- result ---------------------------------------------------------
    def result(self, *, status: str, warmstart: Mapping[str, Any], optimizer: Mapping[str, Any], notes: str = "") -> ArmResult:
        ledger = self.evaluator.ledger
        summary = ledger.summary()
        valid_count = sum(1 for row in self.history if row["valid"])
        return ArmResult(
            arm_id=self.spec.arm_id,
            run_id=self.spec.run_id,
            batch_id=self.spec.batch_id,
            seed=int(self.spec.seed),
            budget_starts=int(self.spec.budget_starts),
            backend=str(self.evaluator.backend),
            status=str(status),
            evaluations_requested=int(summary["evaluations_requested"]),
            unique_design_evals=int(summary["unique_design_evals"]),
            cached_reads=int(summary["cached_reads"]),
            physical_solver_starts=int(summary["physical_solver_starts"]),
            simulated_solver_starts=int(summary["simulated_solver_starts"]),
            starts_used=int(summary["starts_used"]),
            valid_evals=int(valid_count),
            valid_solve_rate=float(valid_count / max(1, len(self.history))),
            first_feasible_solver_start=self.first_feasible_solver_start,
            best_valid_D_i_N=self.best_D_i,
            best_design_unit=None if self.best_vector is None else [float(v) for v in self.best_vector],
            anytime=list(self.anytime),
            history=list(self.history),
            warmstart=dict(warmstart),
            optimizer=dict(optimizer),
            ledger_summary=summary,
            notes=str(notes),
        )


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


# ---------------------------------------------------------------------------
# warm-start initialisation (label free)
# ---------------------------------------------------------------------------

def _fallback_lhs(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed))
    return rng.random((max(1, int(n)), DIMENSION))


def warmstart_designs(
    spec: ArmSpec,
    task: Any,
    design_space: Any,
    n: int,
    *,
    label_store: Any = None,
    support: Any = None,
    require_support: bool = False,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Propose n initial designs for an A-arm. Never produces real labels.

    `support` is the frozen P2A-R1 `WarmStartSupport` loaded from A1's
    p2a_warmstart_support.json. When it is absent the A-arm may only use in-run
    VisibleLabelStore labels (empty on the first call), and require_support=True
    fails closed instead of silently running without the pre-registered history.
    """
    n = max(1, int(n))
    info: Dict[str, Any] = {
        "enabled": bool(spec.is_adaptive and spec.warmstart is not None),
        "arm_id": spec.arm_id,
        "n_requested": n,
        "source": "none",
        "physical_call_count": 0,
        "in_run_labels_visible": 0,
        "import_error": _WARM_START_IMPORT_ERROR,
        "historical_support": "NONE",
        "historical_support_sha256": "",
        "historical_support_n_designs": 0,
    }
    if not (spec.is_adaptive and spec.warmstart is not None):
        return _fallback_lhs(n, spec.seed), info
    warm = spec.warmstart
    info["source"] = str(warm.source)
    info["in_run_labels_visible"] = 0 if label_store is None else int(len(label_store))
    observed = None
    if support is not None:
        observed = support.to_observed_support() if hasattr(support, "to_observed_support") else dict(support)
        info.update(
            {
                "historical_support": "FROZEN_A1_ARTIFACT",
                "historical_support_sha256": str(getattr(support, "sha256", "") or ""),
                "historical_support_n_designs": int(len(observed.get("designs", []))),
                "historical_support_path": str(getattr(support, "path", "") or ""),
                "support_append_during_run": False,
                "support_cache_used": False,
            }
        )
        if label_store is not None and len(label_store) > 0:
            # frozen history + THIS run's paid labels only; never another run's.
            in_run = label_store.to_support()
            info["in_run_labels_used"] = int(len(in_run.get("designs", [])))
            observed = {
                "designs": list(observed.get("designs", [])) + list(in_run.get("designs", [])),
                "records": list(observed.get("records", [])) + list(in_run.get("records", [])),
            }
    elif label_store is not None and len(label_store) > 0:
        observed = label_store.to_support()
        info["historical_support"] = "IN_RUN_LABELS_ONLY"
    if require_support and observed is None:
        from .p2a_support import WarmStartSupportError

        raise WarmStartSupportError(
            "P2A-R1: A-arm %s requires the frozen p2a_warmstart_support.json; no support supplied and no in-run labels yet" % (spec.arm_id,)
        )
    support = observed
    try:
        if WarmStartSampler is None or WarmStartConfig is None:
            raise RuntimeError("warm_start unavailable: %s" % _WARM_START_IMPORT_ERROR)
        snapshot = None
        if warm.source != "random":
            if zero_shot_snapshot is None:
                raise RuntimeError("zero_shot_snapshot unavailable")
            snapshot = zero_shot_snapshot(seed=int(warm.seed) + int(spec.seed))
        config = WarmStartConfig(
            source=str(warm.source),
            support_size=(
                int(warm.support_size)
                if support is None
                else int(len(support.get("designs", [])))
            ),
            candidate_pool_size=int(warm.candidate_pool_size),
            seed=int(warm.seed) + int(spec.seed),
        )
        sampler = WarmStartSampler(config, snapshot=snapshot)
        proposal = sampler.propose(
            task.task_context(),
            int(DIMENSION),
            observed_support=support,
            n_new=n,
            seed=int(spec.seed),
        )
        designs = np.asarray(proposal.X_init, dtype=float).reshape(-1, DIMENSION)
        provenance = dict(getattr(proposal, "provenance", {}) or {})
        info.update(
            {
                "source": str(getattr(proposal, "source", warm.source)),
                "model_sha": getattr(proposal, "model_sha", ""),
                "sample_budget": getattr(proposal, "sample_budget", None),
                "physical_call_count": int(provenance.get("physical_call_count", 0) or 0),
                "label_free": bool(int(provenance.get("physical_call_count", 0) or 0) == 0),
                "n_proposed": int(designs.shape[0]),
                "surrogate_kind": getattr(snapshot, "kind", None) if snapshot is not None else None,
                "seed": int(getattr(proposal, "seed", spec.seed)),
            }
        )
        return np.clip(designs, 0.0, 1.0), info
    except Exception as exc:  # noqa: BLE001 - warm-start failure must not leak labels
        info["error"] = "%s: %s" % (type(exc).__name__, exc)
        info["label_free"] = True
        return _fallback_lhs(n, spec.seed), info


# ---------------------------------------------------------------------------
# base optimizers
# ---------------------------------------------------------------------------

def _run_bo(spec: ArmSpec, harness: ArmHarness, design_space: Any) -> Dict[str, Any]:
    if ConstrainedBayesianOptimizer is None or generate_initial_designs is None:
        raise RuntimeError("maml_opt unavailable: %s" % _MAML_IMPORT_ERROR)
    lower = np.zeros(DIMENSION)
    upper = np.ones(DIMENSION)
    n_initial = spec.bo_initial_designs()
    warm_info: Dict[str, Any] = {}
    if spec.is_adaptive and spec.warmstart is not None:
        initial, warm_info = warmstart_designs(spec, harness.task, design_space, n_initial, label_store=harness.evaluator.label_store)
    else:
        initial = np.asarray(
            generate_initial_designs(lower, upper, count=n_initial, seed=int(spec.seed), method="lhs"), dtype=float
        ).reshape(-1, DIMENSION)
    for vector in initial:
        try:
            harness.evaluate(vector, phase="initial")
        except SolverBudgetExceeded:
            if harness.evaluator.ledger.starts_used < int(spec.budget_starts):
                harness.budget_exhausted = True
            return {"optimizer": "bo", "initial_designs": n_initial, "initial_evaluated": int(len(initial)), "warmstart": warm_info}
    optimizer = ConstrainedBayesianOptimizer(lower, upper, seed=int(spec.seed))
    acquisitions = 0
    skipped_duplicates = 0
    while True:
        try:
            harness._guard()
        except SolverBudgetExceeded:
            if harness.evaluator.ledger.starts_used < int(spec.budget_starts):
                harness.budget_exhausted = True
            break
        try:
            proposal = optimizer.ask()
        except Exception:  # noqa: BLE001 - maml_opt internal failure stops the arm
            break
        vector = clip_x12(proposal["design_vector"])
        try:
            result = harness.evaluate(vector, phase="bo")
        except SolverBudgetExceeded:
            if harness.evaluator.ledger.starts_used < int(spec.budget_starts):
                harness.budget_exhausted = True
            break
        acquisitions += 1
        try:
            optimizer.tell(vector, result)
        except ValueError:
            skipped_duplicates += 1
        except Exception:  # noqa: BLE001
            break
    return {
        "optimizer": "bo",
        "initial_designs": n_initial,
        "acquisitions": acquisitions,
        "skipped_duplicates": skipped_duplicates,
        "warmstart": warm_info,
    }


def _run_de(spec: ArmSpec, harness: ArmHarness, design_space: Any) -> Dict[str, Any]:
    if DifferentialEvolutionBaseline is None:
        raise RuntimeError("baseline_de unavailable: %s" % _OPT_IMPORT_ERROR)
    population = spec.de_population_size()
    initial = None
    warm_info: Dict[str, Any] = {}
    if spec.is_adaptive and spec.warmstart is not None:
        warm_X, warm_info = warmstart_designs(spec, harness.task, design_space, population, label_store=harness.evaluator.label_store)
        initial = np.asarray(warm_X, dtype=float)
    optimizer = DifferentialEvolutionBaseline(
        dimension=DIMENSION,
        budget=int(spec.budget_starts),
        seed=int(spec.seed),
        population_size=population,
        lower_bounds=np.zeros(DIMENSION),
        upper_bounds=np.ones(DIMENSION),
        initial_population=initial,
    )
    try:
        report = optimizer.run(harness.evaluate)
    except SolverBudgetExceeded:
        harness.budget_exhausted = True
        report = {"status": "BUDGET_EXHAUSTED"}
    except Exception as exc:  # noqa: BLE001
        report = {"status": "OPTIMIZER_ERROR", "error": "%s: %s" % (type(exc).__name__, exc)}
    return {
        "optimizer": "de",
        "population_size": population,
        "status": report.get("status", ""),
        "generations_completed": report.get("generations_completed"),
        "initial_population_source": report.get("initial_population_source", "warmstart" if initial is not None else "lhs"),
        "first_feasible_evaluation": report.get("first_feasible_evaluation"),
        "warmstart": warm_info,
    }


def _run_pso(spec: ArmSpec, harness: ArmHarness, design_space: Any) -> Dict[str, Any]:
    if ParticleSwarmBaseline is None:
        raise RuntimeError("baseline_pso unavailable: %s" % _OPT_IMPORT_ERROR)
    swarm = spec.pso_swarm_size()
    initial = None
    warm_info: Dict[str, Any] = {}
    if spec.is_adaptive and spec.warmstart is not None:
        warm_X, warm_info = warmstart_designs(spec, harness.task, design_space, swarm, label_store=harness.evaluator.label_store)
        initial = np.asarray(warm_X, dtype=float)
    optimizer = ParticleSwarmBaseline(
        dimension=DIMENSION,
        budget=int(spec.budget_starts),
        seed=int(spec.seed),
        swarm_size=swarm,
        lower_bounds=np.zeros(DIMENSION),
        upper_bounds=np.ones(DIMENSION),
        initial_positions=initial,
    )
    try:
        report = optimizer.run(harness.evaluate)
    except SolverBudgetExceeded:
        harness.budget_exhausted = True
        report = {"status": "BUDGET_EXHAUSTED"}
    except Exception as exc:  # noqa: BLE001
        report = {"status": "OPTIMIZER_ERROR", "error": "%s: %s" % (type(exc).__name__, exc)}
    return {
        "optimizer": "pso",
        "swarm_size": swarm,
        "status": report.get("status", ""),
        "generations_completed": report.get("generations_completed"),
        "initial_positions_source": "warmstart" if initial is not None else "random",
        "first_feasible_evaluation": report.get("first_feasible_evaluation"),
        "warmstart": warm_info,
    }


def run_arm(spec: ArmSpec, task: Any, design_space: Any, evaluator: BaseLiftMatchEvaluator) -> ArmResult:
    """Run one arm with a fail-closed B-start budget; returns ArmResult."""
    harness = ArmHarness(spec, task, design_space, evaluator)
    warm_info: Dict[str, Any] = {}
    optimizer_info: Dict[str, Any] = {}
    status = "COMPLETED"
    try:
        if spec.base_arm == "BO":
            optimizer_info = _run_bo(spec, harness, design_space)
            warm_info = dict(optimizer_info.get("warmstart") or {})
        elif spec.base_arm == "DE":
            optimizer_info = _run_de(spec, harness, design_space)
            warm_info = dict(optimizer_info.get("warmstart") or {})
        elif spec.base_arm == "PSO":
            optimizer_info = _run_pso(spec, harness, design_space)
            warm_info = dict(optimizer_info.get("warmstart") or {})
        else:  # pragma: no cover - ArmSpec validates arm ids
            raise ValueError("unsupported arm %r" % spec.arm_id)
    except SolverBudgetExceeded:
        harness.budget_exhausted = True
        status = "BUDGET_EXHAUSTED"
    except Exception as exc:  # noqa: BLE001 - one arm must not kill a batch
        status = "ARM_ERROR"
        optimizer_info["error"] = "%s: %s" % (type(exc).__name__, exc)
    if harness.budget_exhausted and status == "COMPLETED":
        status = "BUDGET_EXHAUSTED"
    notes = "" if spec.warmstart is not None or not spec.is_adaptive else "adaptive arm without warmstart spec"
    return harness.result(status=status, warmstart=warm_info, optimizer=optimizer_info, notes=notes)
