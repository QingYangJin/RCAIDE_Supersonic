"""F1 最小 E2E：12D 设计 -> evaluator -> BO/DE ask-tell，并落盘可审计产物。

两条驱动：
* BO：maml_opt.bayesian.ConstrainedBayesianOptimizer（ask/tell 接口），初始设计用
  maml_opt.initialization.generate_initial_designs（LHS）；在单位盒 [0,1]^12 上搜索。
* DE：本模块自写的 MiniDE（DE/rand/1/bin + 可行性优先选择），显式 ask/tell，
  因为 P2 的 DifferentialEvolutionBaseline 把 budget 当成"物理调用"并允许 4x 请求
  （MAX_REQUESTS_PER_BUDGET=4.0），不适合作为零求解阶段的限量驱动。

共同约束：
* 所有评价都经 BudgetLedger 记账；MockEvaluator/ArchiveReplayEvaluator 的
  physical_call_count 恒为 0，因此 run 记录 physical_call_count=0。
* 合成目标不是物理证据；产物里 metrics.csv 的物理相关列全部写 NOT_RUN。
* 每次 run 落盘：run_config.json / evaluations.jsonl / optimization_history.csv /
  metrics.csv / data_manifest.json / SHA256SUMS.txt / figures/README.md。
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from maml_opt.bayesian import ConstrainedBayesianOptimizer
from maml_opt.initialization import generate_initial_designs

from ..aircraft.design_space import DesignSpace
from .budget import BudgetLedger
from .records import (
    CONSTRAINT_NAMES,
    EvaluationRecord,
    STATUS_VALID,
    is_feasible,
)

DEFAULT_BO_INITIAL_DESIGNS = 5
DEFAULT_BO_REQUESTS = 10
DEFAULT_DE_POPULATION = 6
DEFAULT_DE_REQUESTS = 12

HISTORY_COLUMNS: Tuple[str, ...] = (
    "iteration",
    "phase",
    "generation",
    "design_sha256",
    "status",
    "valid",
    "feasible",
    "objective",
    "physical_call_count",
    "cache_hit",
    "unit_vector",
)


# --------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------
def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha(start: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(start),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def code_sha256() -> str:
    """f_line 包内所有 .py 源文件的内容指纹（排序后拼接再 SHA-256）。"""
    directory = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def total_violation(constraints: Mapping[str, float]) -> float:
    """10 项 g<=0 约束的违反量之和（不可行解的选择依据）。"""
    total = 0.0
    for name in CONSTRAINT_NAMES:
        value = float(constraints.get(name, 0.0))
        if value > 0.0:
            total += value
    return total


def _result_payload(record: EvaluationRecord) -> Dict[str, Any]:
    """转成 maml_opt tell() 接受的 result 字典（与 baseline_bo 的契约一致）。"""
    return {
        "status": record.status,
        "valid": record.status == STATUS_VALID,
        "feasible": bool(record.feasible),
        "objective": None if record.objective is None else float(record.objective),
        "constraints_g_le_zero": dict(record.constraints),
        "analysis_calls": int(record.physical_call_count),
        "cache_hit": bool(record.provenance.get("cache_hit", False)),
        "design_id": record.design_sha256[:12],
        "error": None if record.status == STATUS_VALID else record.status,
    }


def _history_row(
    record: EvaluationRecord,
    iteration: int,
    phase: str,
    generation: Optional[int] = None,
    unit_vector: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    return {
        "iteration": int(iteration),
        "phase": str(phase),
        "generation": "" if generation is None else int(generation),
        "design_sha256": record.design_sha256,
        "status": record.status,
        "valid": bool(record.status == STATUS_VALID),
        "feasible": bool(record.feasible),
        "objective": "" if record.objective is None else float(record.objective),
        "physical_call_count": int(record.physical_call_count),
        "cache_hit": bool(record.provenance.get("cache_hit", False)),
        "unit_vector": json.dumps([round(float(value), 9) for value in list(unit_vector)]) if unit_vector is not None else "",
    }


def _best_feasible(records: Sequence[EvaluationRecord], history: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    best: Optional[EvaluationRecord] = None
    for record in records:
        if record.status != STATUS_VALID or not record.feasible:
            continue
        if best is None or (record.objective is not None and record.objective < (best.objective or math.inf)):
            best = record
    if best is None:
        return None
    iteration = None
    for row in history:
        if row["design_sha256"] == best.design_sha256:
            iteration = row["iteration"]
            break
    return {
        "design_sha256": best.design_sha256,
        "objective": None if best.objective is None else float(best.objective),
        "iteration": iteration,
        "design": dict(best.design),
        "evaluator_id": best.evaluator_id,
        "source_kind": best.source_kind,
        "physical_validation_status": best.physical_validation_status,
        "physical_call_count": int(best.physical_call_count),
    }


# --------------------------------------------------------------------------
# BO 驱动
# --------------------------------------------------------------------------
def run_bo_search(
    evaluator: Any,
    ledger: BudgetLedger,
    design_space: DesignSpace,
    task: Any = None,
    run_id: str = "f1-bo",
    requests: int = DEFAULT_BO_REQUESTS,
    initial_designs: int = DEFAULT_BO_INITIAL_DESIGNS,
    seed: int = 42,
    strategy: str = "bayesian",
) -> Dict[str, Any]:
    """在单位盒上跑 BO，返回 run 摘要（不落盘）。"""
    if strategy not in ("bayesian", "random"):
        raise ValueError("strategy must be 'bayesian' or 'random'")
    dimension = design_space.design_dim
    if initial_designs < 1:
        raise ValueError("initial_designs must be >= 1")
    if requests < initial_designs:
        raise ValueError("requests must be >= initial_designs")
    lower = np.zeros(dimension, dtype=float)
    upper = np.ones(dimension, dtype=float)
    initial = generate_initial_designs(
        lower, upper, count=initial_designs, seed=int(seed), method="lhs"
    )
    # 初始设计必须包含冻结基线：否则 run 里没有与基线可比的记录。
    initial = np.asarray(initial, dtype=float).copy()
    initial[0] = np.asarray(
        design_space.to_unit_interval(design_space.baseline_dict()), dtype=float
    )
    optimizer = ConstrainedBayesianOptimizer(lower, upper, seed=int(seed))
    history: List[Dict[str, Any]] = []
    start_requests = ledger.requests
    start_records = len(ledger.records)
    iteration = 0

    def evaluate(vector: Sequence[float], phase: str) -> EvaluationRecord:
        nonlocal iteration
        design = design_space.from_unit_interval([float(value) for value in vector])
        record = ledger.evaluate(evaluator, design, task=task, fidelity=evaluator.fidelity)
        history.append(_history_row(record, iteration, phase, unit_vector=vector))
        iteration += 1
        return record

    for row, vector in enumerate(initial):
        record = evaluate(vector, "initial")
        try:
            optimizer.tell(np.asarray(vector, dtype=float), _result_payload(record))
        except ValueError as exc:
            if "already been recorded" not in str(exc):
                raise
    remaining = int(requests) - len(history)
    attempts = 0
    max_attempts = max(remaining, 0) * 4 + 8
    while len(history) < int(requests) and attempts < max_attempts:
        attempts += 1
        if ledger.requests - start_requests >= int(requests):
            break
        selection = optimizer.ask()
        if selection is None:
            break
        vector = np.asarray(selection["design_vector"], dtype=float)
        record = evaluate(vector, "bo" if strategy == "bayesian" else "random")
        try:
            optimizer.tell(vector, _result_payload(record), selection=selection)
        except ValueError as exc:
            if "already been recorded" not in str(exc):
                raise
    if ledger.requests - start_requests > int(requests):
        raise RuntimeError(
            "BO driver exceeded its request budget: %d > %d"
            % (ledger.requests - start_requests, int(requests))
        )
    return {
        "run_id": str(run_id),
        "driver": "bo",
        "optimizer": "maml_opt.ConstrainedBayesianOptimizer",
        "strategy": strategy,
        "seed": int(seed),
        "initial_designs": int(initial_designs),
        "requests": int(requests),
        "iterations": len(history),
        "history": history,
        "best_feasible": _best_feasible(ledger.records[start_records:], history),
        "physical_call_count": int(ledger.physical_calls),
    }


# --------------------------------------------------------------------------
# DE 驱动（自写 MiniDE）
# --------------------------------------------------------------------------
class MiniDE:
    """最小 DE/rand/1/bin，显式 ask/tell，可行性优先选择。

    设计取舍：不用 P2 的 DifferentialEvolutionBaseline，因为它把 budget 解释成
    物理调用数并允许 4x 请求；F1 阶段物理调用恒为 0，需要"请求数"作为真实上限。
    """

    def __init__(
        self,
        dimension: int,
        lower_bounds: Sequence[float],
        upper_bounds: Sequence[float],
        population_size: int = DEFAULT_DE_POPULATION,
        seed: int = 42,
        mutation_factor: float = 0.5,
        crossover_rate: float = 0.7,
        initial_population: Optional[Sequence[Sequence[float]]] = None,
    ) -> None:
        if dimension < 2:
            raise ValueError("dimension must be >= 2")
        if population_size < 4:
            raise ValueError("population_size must be >= 4 (DE/rand/1 needs 3 distinct donors)")
        self.dimension = int(dimension)
        self.lower_bounds = np.asarray(lower_bounds, dtype=float)
        self.upper_bounds = np.asarray(upper_bounds, dtype=float)
        if self.lower_bounds.shape != (self.dimension,) or self.upper_bounds.shape != (self.dimension,):
            raise ValueError("bounds must have shape (%d,)" % self.dimension)
        self.population_size = int(population_size)
        self.mutation_factor = float(mutation_factor)
        self.crossover_rate = float(crossover_rate)
        self.seed = int(seed)
        self._rng = np.random.default_rng(int(seed))
        if initial_population is None:
            population = generate_initial_designs(
                self.lower_bounds,
                self.upper_bounds,
                count=self.population_size,
                seed=int(seed),
                method="lhs",
            )
        else:
            population = np.asarray(initial_population, dtype=float)
            if population.shape != (self.population_size, self.dimension):
                raise ValueError(
                    "initial_population must have shape (%d, %d)"
                    % (self.population_size, self.dimension)
                )
        self.population = np.clip(population, self.lower_bounds, self.upper_bounds)
        # 每条个体的排序键：(不可行标志, objective 或 违反量)
        self.ranks: List[Tuple[int, float]] = [(1, math.inf)] * self.population_size
        self.generation = 0
        self.evaluations = 0
        self._order: List[int] = []
        self._pending: List[int] = []

    # -- 排序规则 ---------------------------------------------------------
    @staticmethod
    def rank_of(record: EvaluationRecord) -> Tuple[int, float]:
        if record.status == STATUS_VALID and record.feasible and record.objective is not None:
            return (0, float(record.objective))
        return (1, total_violation(record.constraints))

    def _next_generation(self) -> None:
        self.generation += 1
        self._order = list(self._rng.permutation(self.population_size))
        self._pending = list(self._order)
        self._order.reverse()

    def ask(self) -> Dict[str, Any]:
        if not self._pending:
            self._next_generation()
        target = self._pending.pop()
        indices = [index for index in range(self.population_size) if index != target]
        donors = self._rng.choice(indices, size=3, replace=False)
        r1, r2, r3 = (int(value) for value in donors)
        mutant = self.population[r1] + self.mutation_factor * (self.population[r2] - self.population[r3])
        mutant = np.clip(mutant, self.lower_bounds, self.upper_bounds)
        trial = self.population[target].copy()
        jrand = int(self._rng.integers(0, self.dimension))
        for j in range(self.dimension):
            if self._rng.random() < self.crossover_rate or j == jrand:
                trial[j] = mutant[j]
        return {
            "target_index": target,
            "generation": self.generation,
            "trial_vector": trial.tolist(),
            "target_vector": self.population[target].tolist(),
        }

    def tell(self, step: Mapping[str, Any], record: EvaluationRecord) -> bool:
        target = int(step["target_index"])
        trial = np.asarray(step["trial_vector"], dtype=float)
        trial_rank = self.rank_of(record)
        self.evaluations += 1
        replaced = False
        if trial_rank < self.ranks[target]:
            self.population[target] = trial
            self.ranks[target] = trial_rank
            replaced = True
        return replaced

    @property
    def best_rank(self) -> Tuple[int, float]:
        return min(self.ranks)


def run_de_search(
    evaluator: Any,
    ledger: BudgetLedger,
    design_space: DesignSpace,
    task: Any = None,
    run_id: str = "f1-de",
    requests: int = DEFAULT_DE_REQUESTS,
    population_size: int = DEFAULT_DE_POPULATION,
    seed: int = 42,
) -> Dict[str, Any]:
    """MiniDE 驱动：初始种群 + 逐代 ask/tell，全部经 BudgetLedger 记账。"""
    dimension = design_space.design_dim
    if requests < population_size:
        raise ValueError("requests must be >= population_size")
    lower = np.zeros(dimension, dtype=float)
    upper = np.ones(dimension, dtype=float)
    population = generate_initial_designs(
        lower, upper, count=population_size, seed=int(seed), method="lhs"
    )
    population = np.asarray(population, dtype=float).copy()
    population[0] = np.asarray(
        design_space.to_unit_interval(design_space.baseline_dict()), dtype=float
    )
    de = MiniDE(
        dimension,
        lower,
        upper,
        population_size=population_size,
        seed=int(seed),
        initial_population=population,
    )
    history: List[Dict[str, Any]] = []
    start_requests = ledger.requests
    start_records = len(ledger.records)
    iteration = 0
    for index, vector in enumerate(population):
        design = design_space.from_unit_interval([float(value) for value in vector])
        record = ledger.evaluate(evaluator, design, task=task, fidelity=evaluator.fidelity)
        de.ranks[index] = MiniDE.rank_of(record)
        de.evaluations += 1
        history.append(_history_row(record, iteration, "initial", generation=0, unit_vector=vector))
        iteration += 1

    guard = 0
    max_steps = (int(requests) - population_size) * 3 + 16
    while ledger.requests - start_requests < int(requests) and guard < max_steps:
        guard += 1
        step = de.ask()
        design = design_space.from_unit_interval(step["trial_vector"])
        record = ledger.evaluate(evaluator, design, task=task, fidelity=evaluator.fidelity)
        de.tell(step, record)
        history.append(
            _history_row(
                record,
                iteration,
                "de",
                generation=step["generation"],
                unit_vector=step["trial_vector"],
            )
        )
        iteration += 1
    if ledger.requests - start_requests > int(requests):
        raise RuntimeError(
            "DE driver exceeded its request budget: %d > %d"
            % (ledger.requests - start_requests, int(requests))
        )
    return {
        "run_id": str(run_id),
        "driver": "de",
        "optimizer": "f_line.MiniDE",
        "strategy": "de_rand_1_bin",
        "seed": int(seed),
        "initial_designs": int(population_size),
        "requests": int(requests),
        "iterations": len(history),
        "generations": int(de.generation),
        "history": history,
        "population_best_rank": list(de.best_rank),
        "best_feasible": _best_feasible(ledger.records[start_records:], history),
        "physical_call_count": int(ledger.physical_calls),
    }


# --------------------------------------------------------------------------
# 产物落盘
# --------------------------------------------------------------------------
def write_run_artifacts(
    output_dir: Path,
    summary: Mapping[str, Any],
    ledger: BudgetLedger,
    design_space: DesignSpace,
    task: Any,
    evaluator: Any,
    repo_root: Optional[Path] = None,
) -> Dict[str, str]:
    """写出 run 的 7 类产物，返回 {相对路径: sha256}。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    history: List[Dict[str, Any]] = list(summary.get("history") or [])
    repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]

    run_config = {
        "run_id": summary.get("run_id"),
        "driver": summary.get("driver"),
        "optimizer": summary.get("optimizer"),
        "strategy": summary.get("strategy"),
        "git_sha": _git_sha(repo_root),
        "code_sha": code_sha256(),
        "task_id": str(getattr(task, "task_id", "")),
        "task_fingerprint": getattr(task, "fingerprint", lambda: None)(),
        "design_set": design_space.design_set,
        "design_dim": design_space.design_dim,
        "design_dim": design_space.design_dim,
        "design_space_config": design_space.config_path,
        "design_space_frozen": design_space.frozen,
        "design_space_bounds_status": design_space.bounds_status,
        "evaluator_id": evaluator.evaluator_id,
        "fidelity": evaluator.fidelity,
        "source_kind": evaluator.source_kind,
        "physical_validation_status": evaluator.physical_validation_status,
        "solver_version": evaluator.solver_version,
        "budget_B": ledger.physical_budget,
        "K": summary.get("requests"),
        "initial_population_size": summary.get("initial_designs"),
        "seed": summary.get("seed"),
        "physical_call_count": ledger.physical_calls,
        "zero_physical_run": ledger.physical_calls == 0,
        "capability_note": (
            "F1 软件闭环：合成/归档 replay 评价，physical_call_count=0；"
            "不代表任何物理验证或阻力/油耗结论"
        ),
        "created_utc": _utc_now(),
    }
    _write_json(output_dir / "run_config.json", run_config)
    ledger.evaluations_jsonl(output_dir / "evaluations.jsonl")
    _write_history_csv(output_dir / "optimization_history.csv", history)
    _write_metrics_csv(output_dir / "metrics.csv", summary, ledger)
    (figures_dir / "README.md").write_text(
        "本 run 的 figures 目录为空：\n"
        "\n"
        "- 本 run 为 F1 零求解软件闭环，physical_call_count=0，没有任何真实气动数据。\n"
        "- 因此所有计划中的物理图（阻力极曲线、配平曲线、收敛历史等）状态均为 NOT_RUN。\n"
        "- 这里不生成占位图或伪造数据点（禁止造假图）。\n"
        "- 若后续 Tier0 真实 VSPAERO 启动获批，再按 Issue #8 合同补图并标注来源。\n",
        encoding="utf-8",
    )
    manifest_entries = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        relative = path.relative_to(output_dir).as_posix()
        manifest_entries.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256_file(path)}
        )
    _write_json(
        output_dir / "data_manifest.json",
        {
            "run_id": summary.get("run_id"),
            "generated_utc": _utc_now(),
            "physical_call_count": ledger.physical_calls,
            "files": manifest_entries,
            "note": "F1 零求解 run：全部记录 source_kind 为 SYNTHETIC_MOCK 或 ARCHIVE_REPLAY",
        },
    )
    # SHA256SUMS 覆盖其余全部产物（含 data_manifest.json），放在最后写。
    sums_lines = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        relative = path.relative_to(output_dir).as_posix()
        sums_lines.append("%s  %s" % (_sha256_file(path), relative))
    (output_dir / "SHA256SUMS.txt").write_text("\n".join(sums_lines) + "\n", encoding="utf-8")
    return {item["path"]: item["sha256"] for item in manifest_entries}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _write_history_csv(path: Path, history: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(HISTORY_COLUMNS))
        writer.writeheader()
        for row in history:
            writer.writerow({column: row.get(column, "") for column in HISTORY_COLUMNS})


def _write_metrics_csv(path: Path, summary: Mapping[str, Any], ledger: BudgetLedger) -> None:
    counts = ledger.status_counts()
    best = summary.get("best_feasible") or {}
    row = {
        "run_id": summary.get("run_id"),
        "driver": summary.get("driver"),
        "requests": ledger.requests,
        "records": len(ledger.records),
        "valid_records": counts.get(STATUS_VALID, 0),
        "failures": len(ledger.records) - counts.get(STATUS_VALID, 0),
        "physical_call_count": ledger.physical_calls,
        "zero_physical_run": ledger.physical_calls == 0,
        "best_feasible_objective_kg": best.get("objective", ""),
        "best_feasible_design_sha256": best.get("design_sha256", ""),
        "physical_validation_status": "NOT_VALIDATED",
        "drag_polar": "NOT_RUN",
        "trim_curve": "NOT_RUN",
        "fuel_burn_physical": "NOT_RUN",
        "note": "合成/归档 replay 结果，不得作为物理结论",
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
