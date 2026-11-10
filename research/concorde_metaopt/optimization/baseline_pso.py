"""路线A：带真实值初始化约束的 PSO 后端。

与 baseline_de.py 保持同一套预算/可行性语义：
* 所有 pbest / gbest 只由真实评价结果更新，严禁用代理预测或采样器的
  predicted_objective / predicted_feasibility 设置 best；
* 初始群体可用外部热启动位置（initial_positions），但初始 pbest 来自
  对每个初始位置的首次真实评价，且全部计入预算；
* 边界、惯性权重、学习因子、最大速度比例与种子接口冻结为显式参数。

物理求解调用数始终为 0（本模块只接受合成 evaluator）。
"""
from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import numpy as np

from maml_opt.initialization import generate_initial_designs

from ..aircraft.design_space import DesignSpace
from ..aircraft.geometry_checks import _display_path, _git_sha, _software_versions, _write_csv, _write_json
from ..run_paths import RunPathError, resolve_run_directory

PSO_VERSION = "route-a-pso-2026-11-10"
METHOD = "ordinary_constrained_pso"
ALGORITHM = "pso"
STAGE = "D-NEXT-001-A"
MIN_SWARM_SIZE = 4
DEFAULT_SWARM_SIZE = 10
DEFAULT_INERTIA = 0.7298
DEFAULT_COGNITIVE = 1.49618
DEFAULT_SOCIAL = 1.49618
DEFAULT_MAX_VELOCITY_FRACTION = 0.20
MAX_GENERATIONS = 2000

Evaluator = Callable[[Sequence[float]], Mapping[str, Any]]


class PSOError(RuntimeError):
    """Raised when the PSO run request is invalid."""


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _constraint_violation(result: Mapping[str, Any]) -> float:
    if not bool(result.get("valid", False)):
        return math.inf
    total = 0.0
    for value in (result.get("constraints_g_le_zero") or {}).values():
        number = _finite(value)
        if number is None:
            return math.inf
        total += max(0.0, number)
    return total


def _is_feasible(result: Mapping[str, Any]) -> bool:
    if not bool(result.get("valid", False)):
        return False
    if _finite(result.get("objective")) is None:
        return False
    constraints = result.get("constraints_g_le_zero") or {}
    if not constraints:
        return False
    for value in constraints.values():
        number = _finite(value)
        if number is None or number > 0.0:
            return False
    return True


def _better(candidate: Mapping[str, Any], incumbent: Optional[Mapping[str, Any]]) -> bool:
    if incumbent is None:
        return _is_feasible(candidate) or bool(candidate.get("valid", False))
    candidate_feasible = _is_feasible(candidate)
    incumbent_feasible = _is_feasible(incumbent)
    if candidate_feasible and not incumbent_feasible:
        return True
    if not candidate_feasible and incumbent_feasible:
        return False
    if candidate_feasible and incumbent_feasible:
        return float(candidate["objective"]) < float(incumbent["objective"])
    return _constraint_violation(candidate) < _constraint_violation(incumbent)


def _diversity(positions: np.ndarray) -> float:
    if positions.shape[0] < 2:
        return 0.0
    diff = positions[:, None, :] - positions[None, :, :]
    distance = np.sqrt(np.sum(diff * diff, axis=2))
    upper = distance[np.triu_indices(positions.shape[0], k=1)]
    return float(np.mean(upper) / math.sqrt(positions.shape[1]))


class ParticleSwarmBaseline:
    """Deterministic PSO with feasibility-rule pbest/gbest (true values only)."""

    def __init__(
        self,
        dimension: int,
        budget: int,
        seed: int = 42,
        swarm_size: Optional[int] = None,
        inertia: float = DEFAULT_INERTIA,
        cognitive: float = DEFAULT_COGNITIVE,
        social: float = DEFAULT_SOCIAL,
        lower_bounds: Optional[Sequence[float]] = None,
        upper_bounds: Optional[Sequence[float]] = None,
        initial_positions: Optional[Any] = None,
        initial_velocities: Optional[Any] = None,
        max_velocity_fraction: float = DEFAULT_MAX_VELOCITY_FRACTION,
    ) -> None:
        if type(dimension) is not int or dimension < 1:
            raise PSOError("dimension must be a positive integer")
        if type(budget) is not int or budget < MIN_SWARM_SIZE:
            raise PSOError("budget must be an integer of at least %d" % MIN_SWARM_SIZE)
        if type(seed) is not int or seed < 0:
            raise PSOError("seed must be a non-negative integer")
        size = min(DEFAULT_SWARM_SIZE, budget) if swarm_size is None else int(swarm_size)
        if size < MIN_SWARM_SIZE:
            raise PSOError("swarm size must be at least %d" % MIN_SWARM_SIZE)
        if size > budget:
            raise PSOError("swarm size must not exceed the evaluation budget")
        inertia = float(inertia)
        cognitive = float(cognitive)
        social = float(social)
        fraction = float(max_velocity_fraction)
        if not 0.0 < inertia <= 1.0:
            raise PSOError("inertia must be in (0, 1]")
        if cognitive < 0.0 or social < 0.0 or not math.isfinite(cognitive + social):
            raise PSOError("learning factors must be finite and non-negative")
        if not 0.0 < fraction <= 1.0:
            raise PSOError("max velocity fraction must be in (0, 1]")
        self.dimension = dimension
        self.budget = budget
        self.seed = seed
        self.swarm_size = size
        self.inertia = inertia
        self.cognitive = cognitive
        self.social = social
        self.lower_bounds = np.zeros(dimension) if lower_bounds is None else np.asarray(lower_bounds, dtype=float)
        self.upper_bounds = np.ones(dimension) if upper_bounds is None else np.asarray(upper_bounds, dtype=float)
        if self.lower_bounds.shape != (dimension,) or self.upper_bounds.shape != (dimension,):
            raise PSOError("bounds must have one entry per dimension")
        if np.any(self.lower_bounds >= self.upper_bounds):
            raise PSOError("every lower bound must be below its upper bound")
        self.max_velocity_fraction = fraction
        self.max_velocity = fraction * (self.upper_bounds - self.lower_bounds)
        self.rng = np.random.default_rng(seed)
        self.initial_positions = self._validate_positions(initial_positions, "initial positions")
        self.initial_velocities = self._validate_velocities(initial_velocities)
        if self.initial_positions is not None and self.initial_positions.shape[0] != size:
            raise PSOError("initial positions row count must equal swarm size")
        self._requests = 0
        self._physical_calls = 0
        self._evaluations_used = 0

    def _validate_positions(self, positions: Optional[Any], label: str) -> Optional[np.ndarray]:
        if positions is None:
            return None
        matrix = np.asarray(positions, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != self.dimension:
            raise PSOError("%s must be a (n, dimension) matrix" % label)
        if not np.all(np.isfinite(matrix)):
            raise PSOError("%s must be finite" % label)
        if np.any(matrix < -1e-9) or np.any(matrix > 1.0 + 1e-9):
            raise PSOError("%s must lie in the unit hypercube [0, 1]" % label)
        return np.clip(matrix, 0.0, 1.0)

    def _validate_velocities(self, velocities: Optional[Any]) -> Optional[np.ndarray]:
        if velocities is None:
            return None
        matrix = np.asarray(velocities, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != self.dimension:
            raise PSOError("initial velocities must be a (n, dimension) matrix")
        if not np.all(np.isfinite(matrix)):
            raise PSOError("initial velocities must be finite")
        if np.any(np.abs(matrix) > self.max_velocity + 1e-12):
            raise PSOError("initial velocities exceed the frozen max velocity")
        return matrix

    def _evaluate(self, evaluate: Evaluator, position: np.ndarray, phase: str, generation: int, particle: int) -> Dict[str, Any]:
        clipped = np.clip(np.asarray(position, dtype=float), self.lower_bounds, self.upper_bounds)
        self._requests += 1
        result = dict(evaluate([float(value) for value in clipped]))
        self._evaluations_used += 1
        calls = result.get("analysis_calls")
        calls = int(calls) if isinstance(calls, int) and calls >= 0 else 0
        self._physical_calls += calls
        violation = _constraint_violation(result)
        return {
            "iteration": self._evaluations_used - 1,
            "phase": phase,
            "generation": int(generation),
            "particle_index": int(particle),
            "status": result.get("status"),
            "valid": bool(result.get("valid", False)),
            "feasible": _is_feasible(result),
            "objective": _finite(result.get("objective")),
            "analysis_calls": calls,
            "constraint_violation": violation if math.isfinite(violation) else None,
            "position": [float(value) for value in clipped],
            "constraints_g_le_zero": {
                str(name): _finite(value) for name, value in (result.get("constraints_g_le_zero") or {}).items()
            },
        }

    def run(
        self,
        evaluate: Evaluator,
        on_record: Optional[Callable[[Dict[str, Any]], None]] = None,
        baseline_position: Optional[Sequence[float]] = None,
    ) -> Dict[str, Any]:
        if self.initial_positions is not None:
            if baseline_position is not None:
                raise PSOError("baseline_position cannot be combined with initial positions")
            positions = self.initial_positions.copy()
        else:
            generated = generate_initial_designs(
                self.lower_bounds,
                self.upper_bounds,
                self.swarm_size,
                seed=self.seed,
                baseline=np.asarray(baseline_position, dtype=float) if baseline_position is not None else None,
                method="lhs",
            )
            positions = np.asarray(generated, dtype=float)
        if self.initial_velocities is not None:
            velocities = self.initial_velocities.copy()
        else:
            velocities = self.rng.uniform(-1.0, 1.0, size=(self.swarm_size, self.dimension)) * self.max_velocity

        trace: List[Dict[str, Any]] = []
        pbest_positions = positions.copy()
        pbest_records: List[Dict[str, Any]] = []
        for index in range(self.swarm_size):
            record = self._evaluate(evaluate, positions[index], "initialisation", 0, index)
            trace.append(record)
            if on_record is not None:
                on_record(record)
            pbest_records.append(record)
        gbest_index = 0
        for index in range(1, self.swarm_size):
            if _better(pbest_records[index], pbest_records[gbest_index]):
                gbest_index = index
        gbest_position = pbest_positions[gbest_index].copy()
        gbest_record = pbest_records[gbest_index]
        initial_gbest = dict(gbest_record)

        generation = 0
        generation_diversity: List[float] = []
        while self._evaluations_used < self.budget:
            for index in range(self.swarm_size):
                if self._evaluations_used >= self.budget:
                    break
                r1 = self.rng.random(self.dimension)
                r2 = self.rng.random(self.dimension)
                velocities[index] = (
                    self.inertia * velocities[index]
                    + self.cognitive * r1 * (pbest_positions[index] - positions[index])
                    + self.social * r2 * (gbest_position - positions[index])
                )
                velocities[index] = np.clip(velocities[index], -self.max_velocity, self.max_velocity)
                positions[index] = np.clip(positions[index] + velocities[index], self.lower_bounds, self.upper_bounds)
                record = self._evaluate(evaluate, positions[index], "iteration", generation, index)
                trace.append(record)
                if on_record is not None:
                    on_record(record)
                if _better(record, pbest_records[index]):
                    pbest_positions[index] = positions[index].copy()
                    pbest_records[index] = record
                    if _better(record, gbest_record):
                        gbest_position = positions[index].copy()
                        gbest_record = record
            generation += 1
            generation_diversity.append(_diversity(positions))

        feasible_records = [record for record in trace if record["feasible"] and record["objective"] is not None]
        best_record = min(feasible_records, key=lambda record: record["objective"]) if feasible_records else None
        first_feasible = next(
            (record["iteration"] + 1 for record in trace if record["feasible"] and record["objective"] is not None),
            None,
        )
        status = "no_feasible_solution" if best_record is None else "completed"
        return {
            "status": status,
            "termination_reason": "budget_exhausted" if self._evaluations_used >= self.budget else "search_finished",
            "evaluations": len(trace),
            "physical_calls": self._physical_calls,
            "swarm_size": self.swarm_size,
            "generations_completed": generation,
            "inertia": self.inertia,
            "cognitive": self.cognitive,
            "social": self.social,
            "max_velocity_fraction": self.max_velocity_fraction,
            "initial_positions_source": "external" if self.initial_positions is not None else "lhs",
            "initial_gbest": {
                "feasible": bool(initial_gbest["feasible"]),
                "objective": initial_gbest["objective"],
                "position": initial_gbest["position"],
            },
            "first_feasible_evaluation": first_feasible,
            "best_feasible": (
                {
                    "objective": best_record["objective"],
                    "iteration": best_record["iteration"],
                    "position": best_record["position"],
                }
                if best_record is not None
                else None
            ),
            "iteration_best_feasible_objective": [
                min(
                    (
                        record["objective"]
                        for record in trace[: index + 1]
                        if record["feasible"] and record["objective"] is not None
                    ),
                    default=None,
                )
                for index in range(len(trace))
            ],
            "generation_diversity": generation_diversity,
            "final_swarm_diversity": _diversity(positions),
            "trace": trace,
            "final_swarm": [
                {
                    "position": [float(value) for value in positions[index]],
                    "pbest_objective": pbest_records[index]["objective"],
                    "pbest_feasible": bool(pbest_records[index]["feasible"]),
                    "pbest_position": [float(value) for value in pbest_positions[index]],
                }
                for index in range(self.swarm_size)
            ],
        }


def run_baseline_pso(
    output_root: Any,
    run_id: str,
    budget: int,
    seed: int,
    design_space: DesignSpace,
    task: Any,
    backend: Any = None,
    swarm_size: Optional[int] = None,
    inertia: float = DEFAULT_INERTIA,
    cognitive: float = DEFAULT_COGNITIVE,
    social: float = DEFAULT_SOCIAL,
    initial_population: Optional[Any] = None,
    allow_existing: bool = False,
) -> Dict[str, Any]:
    """Run the PSO baseline and write run artefacts (synthetic, physical_call_count=0)."""
    started = time.time()
    root = Path(output_root)
    try:
        run_dir = resolve_run_directory(root, run_id, allow_existing=bool(allow_existing))
    except RunPathError as exc:  # pragma: no cover
        raise PSOError(str(exc)) from exc
    if len(design_space.variables) != 12:
        raise PSOError("PSO baseline expects the 12D unit design space")
    lower = np.zeros(12)
    upper = np.ones(12)

    def evaluate(unit_vector: Sequence[float]) -> Dict[str, Any]:
        return dict(task.evaluate_unit(np.asarray(unit_vector, dtype=float)))

    optimizer = ParticleSwarmBaseline(
        dimension=12,
        budget=int(budget),
        seed=int(seed),
        swarm_size=swarm_size,
        inertia=inertia,
        cognitive=cognitive,
        social=social,
        lower_bounds=lower,
        upper_bounds=upper,
        initial_positions=initial_population,
    )
    result = optimizer.run(evaluate)
    summary = dict(result)
    summary.update(
        {
            "run_id": run_id,
            "stage": STAGE,
            "method": METHOD,
            "algorithm": ALGORITHM,
            "pso_version": PSO_VERSION,
            "run_dir": _display_path(run_dir),
            "git_sha": _git_sha(),
            "software_versions": _software_versions(),
            "budget": int(budget),
            "seed": int(seed),
            "design_dim": 12,
            "physical_call_count": 0,
            "source_kind": "SYNTHETIC_ANALOGUE",
            "wall_seconds": round(time.time() - started, 3),
        }
    )
    _write_json(run_dir / "run_summary.json", summary)
    _write_csv(run_dir / "trace.csv", result["trace"], list(result["trace"][0].keys()) if result["trace"] else [])
    return summary
