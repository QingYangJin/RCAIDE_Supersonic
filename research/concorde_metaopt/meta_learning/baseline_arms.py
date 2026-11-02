"""P4-CODE 合成离线优化对照臂（§8/§8.1/§8.2/§10）。

本模块只做“组合”：在单位超立方体 [0,1]^12 上运行等预算优化臂，并复用 maml-opt
0.1.0 的公开 API（ConstrainedBayesianOptimizer / run_search /
generate_initial_designs / select_model_scored_initial_designs）。评估器由调用方注入，
在 P4-CODE 阶段必须是解析合成 evaluator（offline_runner 负责构造，physical_call_count=0）；
本模块不 import 任何真实 Mission / SU2 / VSPAERO / OpenVSP / RCAIDE 求解器入口。

契约要点：
- 五个臂（§10）：OPT-BO-rand / OPT-BO-pretrain / OPT-BO-MAML / OPT-BO-MAML-init / OPT-DE；
  统一 true_evaluation_budget=64、初始 8 点、可行性判据 g<=0（容差 1e-12）。
- 预测标签只允许用于“先评估哪些点”的排序（MAML-init 的 model-scored initial designs），
  绝不写入 BO observations；observations 只由真实（合成）评估结果增长。
- MAML-init 冻结参数（§8.2）：candidate_count=64、initial_design_count=8、
  diversity_candidate_count=64、seed 由任务 seed 显式派生（禁止静默使用默认 42），
  候选去重容差 1e-12；不足 8 个唯一候选时整臂 FAIL。
- 单位门禁（§8）：合成设计空间 feature units 必须全为 "1"；物理 SI 设计空间不得误入
  MAML-init 打分路径。

CONTRACT_AMBIGUITY（已上报 Lead，不自行改合同）：
1. §8.1 要求复用 optimization/baseline_de.py 的 DifferentialEvolutionBaseline，但
   baseline_de.py 在模块级 import ..evaluation.low_fidelity（进而 import
   aircraft.concorde_adapter / evaluation.mission 的真实物理入口）；§1.3 禁止
   meta_learning/* 出现该 import 链。因此本模块**不 import baseline_de**，而是按
   baseline_de.DifferentialEvolutionBaseline 的 DE/rand/1/bin 语义（变异因子 0.5、
   交叉率 0.7、可行性优先选优规则）独立实现。
2. §10 的 OPT-BO-pretrain / OPT-BO-MAML 要求“代理来源=条件预训练/MAML 代理”，但
   maml_opt 的公开 API 只有 initial designs 可以注入模型先验，没有在 BO 采集阶段
   注入代理提前排序候选点的公开入口。P4-CODE 阶段这两个臂与 OPT-BO-rand 共享同一
   BO 机制与同一 8 初始点，仅记录 proxy 元数据；代理先验真正进入采集排序需 M2 阶段
   由 Lead 裁决（不得调用私有 API，不得改 baseline_bo.py）。
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from maml_opt.bayesian import ConstrainedBayesianOptimizer, run_search
from maml_opt.initialization import (
    generate_initial_designs,
    select_model_scored_initial_designs,
)

from ..aircraft.design_space import DesignSpace
from ..evaluation.contract import CONSTRAINT_NAMES, FEASIBILITY_TOLERANCE
from .adaptation import adapt_and_predict
from .data_contract import PHYSICAL_CALL_COUNT, PHYSICS_GUARD_EXPECTED
from .surrogate import encode_features

STAGE = "P4-CODE"
ARMS = ("OPT-BO-rand", "OPT-BO-pretrain", "OPT-BO-MAML", "OPT-BO-MAML-init", "OPT-DE")
BO_ARMS = ("OPT-BO-rand", "OPT-BO-pretrain", "OPT-BO-MAML", "OPT-BO-MAML-init")
MAML_INIT_ARM = "OPT-BO-MAML-init"
DE_ARM = "OPT-DE"

TRUE_EVALUATION_BUDGET = 64
BO_INITIAL_DESIGN_COUNT = 8
DE_POPULATION_SIZE = 8
DE_GENERATIONS = 8
DE_MUTATION_FACTOR = 0.5
DE_CROSSOVER_RATE = 0.7

MAML_INIT_CANDIDATE_COUNT = 64
MAML_INIT_INITIAL_DESIGN_COUNT = 8
MAML_INIT_DIVERSITY_CANDIDATE_COUNT = 64
DEDUP_TOLERANCE = 1e-12
UNIT_FEATURE_UNIT = "1"

DESIGN_DIM = 12
STAGE_IMPLEMENTATION = {
    "OPT-BO-rand": "reuse:maml_opt.bayesian:run_search",
    "OPT-BO-pretrain": "reuse:maml_opt.bayesian:run_search",
    "OPT-BO-MAML": "reuse:maml_opt.bayesian:run_search",
    "OPT-BO-MAML-init": (
        "reuse:maml_opt.initialization:select_model_scored_initial_designs"
    ),
    "OPT-DE": (
        "reuse_semantics:research.concorde_metaopt.optimization.baseline_de:"
        "DifferentialEvolutionBaseline"
    ),
}

PHYSICAL_GUARD_STATUS = "PHYSICS_GUARD_VIOLATION"
VALID_STATUS = "VALID"
NO_FEASIBLE_STATUS = "NO_FEASIBLE_SOLUTION"
FAILED_STATUS = "FAILED"


class BaselineArmError(ValueError):
    """优化对照臂输入/状态错误。"""


class PhysicsGuardViolation(RuntimeError):
    """合成评估器报告了非零物理调用次数，必须立即中止整次 run。"""

    def __init__(self, message: str, *, physical_call_count: int) -> None:
        super().__init__(message)
        self.physical_call_count = int(physical_call_count)


def _stable_seed(*parts: Any) -> int:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**31 - 1)


def derive_arm_seed(task_id: str, seed: int, *parts: Any) -> int:
    """由任务 seed 显式派生臂/候选池 seed（禁止默认 42 静默）。"""
    if not isinstance(task_id, str) or not task_id:
        raise BaselineArmError("task_id 必须是非空字符串")
    if type(seed) is not int or seed < 0:
        raise BaselineArmError(f"seed 必须是非负整数，实际 {seed!r}")
    return _stable_seed("baseline_arm", task_id, seed, *parts)


def assert_synthetic_feature_units(feature_units: Sequence[Any], *, label: str = "feature_units") -> None:
    """单位门禁：合成数据集 feature units 必须全为 "1"（§8）。"""
    if not isinstance(feature_units, (list, tuple)) or not feature_units:
        raise BaselineArmError(f"{label} 必须是非空序列，实际 {type(feature_units).__name__}")
    for index, unit in enumerate(feature_units):
        if str(unit) != UNIT_FEATURE_UNIT:
            raise BaselineArmError(
                f"合成设计空间 {label} 必须全为 {UNIT_FEATURE_UNIT!r}，"
                f"第 {index} 项为 {unit!r}；物理 SI 设计空间不得误入合成路径"
            )


def assert_synthetic_design_space(design_space: DesignSpace) -> None:
    """校验 12D 显式设计空间（§2.3/§8），并禁止 SI 单位误入合成 MAML-init。"""
    if not isinstance(design_space, DesignSpace):
        raise BaselineArmError("design_space 必须是 DesignSpace 实例")
    if design_space.design_dim != DESIGN_DIM:
        raise BaselineArmError(
            f"P4 合成优化臂要求 12D 设计空间，实际 design_dim={design_space.design_dim}"
        )
    if design_space.design_set != "12d_lifting_surfaces":
        raise BaselineArmError(
            f"P4 合成优化臂要求 design_set='12d_lifting_surfaces'，实际 {design_space.design_set!r}"
        )
    if str(design_space.units).upper() not in ("", "SI"):
        raise BaselineArmError(f"设计空间 units 非法: {design_space.units!r}")


def _design_bounds(design_space: DesignSpace) -> tuple[np.ndarray, np.ndarray]:
    lower = np.asarray([variable.lower for variable in design_space.variables], dtype=float)
    upper = np.asarray([variable.upper for variable in design_space.variables], dtype=float)
    if lower.shape != (DESIGN_DIM,) or upper.shape != (DESIGN_DIM,):
        raise BaselineArmError("设计空间变量维度与 12D 不一致")
    if np.any(lower >= upper) or not np.all(np.isfinite(lower)) or not np.all(np.isfinite(upper)):
        raise BaselineArmError("设计空间 bounds 非有限或下界不小于上界")
    return lower, upper


def _unit_bounds() -> tuple[np.ndarray, np.ndarray]:
    return np.zeros(DESIGN_DIM, dtype=float), np.ones(DESIGN_DIM, dtype=float)


def shared_initial_designs(
    task_id: str,
    seed: int,
    *,
    count: int = BO_INITIAL_DESIGN_COUNT,
) -> np.ndarray:
    """同一 (task, seed) 的共享 LHS 初始点（§10），臂间逐位可复现。"""
    if type(count) is not int or count < 1:
        raise BaselineArmError(f"count 必须是正整数，实际 {count!r}")
    lower, upper = _unit_bounds()
    designs = generate_initial_designs(
        lower,
        upper,
        count,
        seed=derive_arm_seed(task_id, seed, "shared_initial"),
        method="lhs",
    )
    return np.asarray(designs, dtype=float)


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _constraints_or_none(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise BaselineArmError(f"constraints_g_le_zero 必须是映射，实际 {type(value).__name__}")
    result: dict[str, float] = {}
    for name, item in value.items():
        number = _finite_or_none(item)
        result[str(name)] = float(number) if number is not None else float("nan")
    return result


def _is_feasible(objective: float | None, constraints: Mapping[str, float] | None) -> bool:
    if objective is None or constraints is None or not constraints:
        return False
    return all(
        math.isfinite(value) and value <= FEASIBILITY_TOLERANCE
        for value in constraints.values()
    )


@dataclass(frozen=True)
class EvaluationRecord:
    """单次真实（合成）评估记录，对应 optimization_history.csv 一行。"""

    eval_index: int
    design_u: tuple[float, ...]
    objective: float | None
    feasible: bool | None
    constraints: Mapping[str, float] | None
    status: str
    cache_hit: bool = False
    billable: bool = True
    error: str | None = None
    design_physical: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.eval_index) is not int or self.eval_index < 1:
            raise BaselineArmError(f"eval_index 必须是正整数，实际 {self.eval_index!r}")
        if len(self.design_u) != DESIGN_DIM:
            raise BaselineArmError(f"design_u 必须为 12 维，实际 {len(self.design_u)}")
        if not all(math.isfinite(value) for value in self.design_u):
            raise BaselineArmError("design_u 必须有限")
        if self.objective is not None and not math.isfinite(self.objective):
            raise BaselineArmError("objective 要么是有限值，要么是 None（禁止 NaN/inf 冒充失败）")
        if not isinstance(self.status, str) or not self.status:
            raise BaselineArmError("status 必须是非空字符串")

    @property
    def valid(self) -> bool:
        return self.objective is not None

    def to_history_row(
        self,
        *,
        run_id: str,
        task_id: str,
        split: str,
        family: str,
        arm: str,
        seed: int,
        wall_s: float = 0.0,
        best_feasible_so_far: float | None = None,
        best_value_so_far: float | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "run_id": run_id,
            "task_id": task_id,
            "split": split,
            "family": family,
            "arm": arm,
            "seed": seed,
            "eval_index": self.eval_index,
            "objective": self.objective,
            "feasible": self.feasible,
            "constraints_json": json.dumps(dict(self.constraints or {}), sort_keys=True),
            "cache_hit": self.cache_hit,
            "billable": self.billable,
            "status": self.status,
            "wall_s": float(wall_s),
            "best_feasible_so_far": best_feasible_so_far,
            "best_value_so_far": best_value_so_far,
        }
        for index, value in enumerate(self.design_u):
            row["design_u_%d" % index] = float(value)
        return row


@dataclass(frozen=True)
class ArmResult:
    """单臂单任务单 seed 的等预算优化结果。"""

    arm: str
    task_id: str
    split: str
    family: str
    seed: int
    budget: int
    observations: tuple[EvaluationRecord, ...]
    requested_evaluations: int
    true_evals_used: int
    cache_hits: int
    failed_evals: int
    best_feasible_value: float | None
    best_design_u: tuple[float, ...] | None
    first_feasible_eval_index: int | None
    feasible_count: int
    violation_rate: float | None
    wall_s: float
    status: str
    termination_reason: str
    initial_feasible_count: int
    implementation: str
    proxy_scoring_cost: Mapping[str, Any] = field(default_factory=dict)
    reference_objective: float | None = None

    @property
    def gap_to_reference(self) -> float | None:
        if self.best_feasible_value is None or self.reference_objective is None:
            return None
        return float(self.best_feasible_value - self.reference_objective)

    def to_summary_row(self, *, run_id: str = "") -> dict[str, Any]:
        """optimization_summary.csv 行（列名与 A2 p4_schemas.json 一致）。"""
        return {
            "run_id": run_id,
            "task_id": self.task_id,
            "split": self.split,
            "family": self.family,
            "arm": self.arm,
            "seed": self.seed,
            "budget": self.budget,
            "true_evals_used": self.true_evals_used,
            "cache_hits": self.cache_hits,
            "failed_evals": self.failed_evals,
            "best_feasible_value": self.best_feasible_value,
            "gap_to_reference": self.gap_to_reference,
            "first_feasible_eval_index": self.first_feasible_eval_index,
            "feasible_count": self.feasible_count,
            "violation_rate": self.violation_rate,
            "wall_s": self.wall_s,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "task_id": self.task_id,
            "split": self.split,
            "family": self.family,
            "seed": self.seed,
            "budget": self.budget,
            "requested_evaluations": self.requested_evaluations,
            "true_evals_used": self.true_evals_used,
            "cache_hits": self.cache_hits,
            "failed_evals": self.failed_evals,
            "best_feasible_value": self.best_feasible_value,
            "best_design_u": list(self.best_design_u) if self.best_design_u is not None else None,
            "gap_to_reference": self.gap_to_reference,
            "first_feasible_eval_index": self.first_feasible_eval_index,
            "feasible_count": self.feasible_count,
            "initial_feasible_count": self.initial_feasible_count,
            "violation_rate": self.violation_rate,
            "wall_s": self.wall_s,
            "status": self.status,
            "termination_reason": self.termination_reason,
            "proxy_scoring_cost": dict(self.proxy_scoring_cost),
            "implementation": self.implementation,
            "physical_call_count": PHYSICAL_CALL_COUNT,
        }



def _record_from_result(
    *,
    eval_index: int,
    design_u: np.ndarray,
    result: Mapping[str, Any] | None,
    fallback_status: str,
) -> EvaluationRecord:
    if result is None:
        return EvaluationRecord(
            eval_index=eval_index,
            design_u=tuple(float(value) for value in np.asarray(design_u, dtype=float)),
            objective=None,
            feasible=False,
            constraints=None,
            status=fallback_status,
            cache_hit=False,
            billable=True,
            error="evaluator returned None",
        )
    if not isinstance(result, Mapping):
        raise BaselineArmError(f"评估器必须返回映射，实际 {type(result).__name__}")
    objective = _finite_or_none(result.get("objective"))
    constraints = _constraints_or_none(result.get("constraints_g_le_zero"))
    status = str(result.get("status") or fallback_status)
    cache_hit = bool(result.get("cache_hit", False))
    billable = bool(result.get("billable", not cache_hit))
    physical = result.get("design_physical")
    design_physical = (
        tuple(float(value) for value in np.asarray(physical, dtype=float))
        if physical is not None
        else None
    )
    if objective is None:
        feasible = False
    elif result.get("feasible") is not None:
        feasible = bool(result.get("feasible"))
    else:
        feasible = _is_feasible(objective, constraints)
    return EvaluationRecord(
        eval_index=eval_index,
        design_u=tuple(float(value) for value in np.asarray(design_u, dtype=float)),
        objective=objective,
        feasible=feasible,
        constraints=constraints,
        status=status,
        cache_hit=cache_hit,
        billable=billable,
        error=result.get("error") if result.get("error") is not None else None,
        design_physical=design_physical,
    )


def _summarize_arm(
    *,
    arm: str,
    task_id: str,
    split: str,
    family: str,
    seed: int,
    budget: int,
    observations: Sequence[EvaluationRecord],
    wall_s: float,
    termination_reason: str,
    implementation: str,
    initial_count: int,
    proxy_scoring_cost: Mapping[str, Any] | None,
    reference_objective: float | None,
) -> ArmResult:
    records = tuple(observations)
    if not records:
        raise BaselineArmError("优化臂没有任何评估记录，无法汇总")
    for index, record in enumerate(records, start=1):
        if record.eval_index != index:
            raise BaselineArmError(f"评估记录序号不连续：第 {index} 条为 {record.eval_index}")
    valid_records = [record for record in records if record.valid]
    feasible_records = [record for record in valid_records if record.feasible]
    billable = [record for record in records if record.billable]
    cache_hits = sum(1 for record in records if record.cache_hit)
    failed = sum(1 for record in records if not record.valid)
    best_record = (
        min(feasible_records, key=lambda record: (record.objective, record.eval_index))
        if feasible_records
        else None
    )
    first_feasible = feasible_records[0].eval_index if feasible_records else None
    initial = records[:initial_count]
    initial_feasible = sum(1 for record in initial if record.valid and record.feasible)
    if valid_records:
        violated = sum(
            1
            for record in valid_records
            if record.constraints
            and any(
                value > FEASIBILITY_TOLERANCE or not math.isfinite(value)
                for value in record.constraints.values()
            )
        )
        violation_rate = float(violated / len(valid_records))
    else:
        violation_rate = None
    if best_record is not None:
        status = VALID_STATUS
    elif valid_records:
        status = NO_FEASIBLE_STATUS
    else:
        status = FAILED_STATUS
    return ArmResult(
        arm=arm,
        task_id=task_id,
        split=split,
        family=family,
        seed=seed,
        budget=budget,
        observations=records,
        requested_evaluations=len(records),
        true_evals_used=len(billable),
        cache_hits=cache_hits,
        failed_evals=failed,
        best_feasible_value=float(best_record.objective) if best_record is not None else None,
        best_design_u=tuple(best_record.design_u) if best_record is not None else None,
        first_feasible_eval_index=first_feasible,
        feasible_count=len(feasible_records),
        violation_rate=violation_rate,
        wall_s=float(wall_s),
        status=status,
        termination_reason=termination_reason,
        initial_feasible_count=int(initial_feasible),
        implementation=implementation,
        proxy_scoring_cost=dict(proxy_scoring_cost or {}),
        reference_objective=reference_objective,
    )


def run_bo_arm(
    arm: str,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task_id: str,
    split: str,
    family: str,
    seed: int,
    budget: int = TRUE_EVALUATION_BUDGET,
    initial_designs: Sequence[Sequence[float]] | np.ndarray | None = None,
    initial_design_metadata: Sequence[Mapping[str, Any]] | None = None,
    strategy: str = "bayesian",
    reference_objective: float | None = None,
    candidate_count: int = 512,
    run_id: str = "",
    proxy_scoring_cost: Mapping[str, Any] | None = None,
) -> ArmResult:
    """运行一个 BO 臂；评估器由调用方注入（P4-CODE 阶段为解析合成 evaluator）。"""
    if arm not in BO_ARMS:
        raise BaselineArmError(f"arm 必须是 {BO_ARMS} 之一，实际 {arm!r}")
    if strategy not in ("bayesian", "random"):
        raise BaselineArmError(f"strategy 必须为 'bayesian' 或 'random'，实际 {strategy!r}")
    if not callable(evaluate):
        raise BaselineArmError("evaluate 必须可调用")
    if type(budget) is not int or budget < 1:
        raise BaselineArmError(f"budget 必须是正整数，实际 {budget!r}")
    if arm == MAML_INIT_ARM and initial_designs is None:
        raise BaselineArmError(
            "OPT-BO-MAML-init 必须提供由 MAML 代理打分选出的 initial_designs（§8.2）"
        )
    if initial_designs is None:
        initial_designs = shared_initial_designs(task_id, seed)
    designs = np.asarray(initial_designs, dtype=float)
    if designs.ndim != 2 or designs.shape[1] != DESIGN_DIM:
        raise BaselineArmError(f"initial_designs 必须为 (n, 12)，实际 {designs.shape}")
    if not np.all(np.isfinite(designs)) or np.any(designs < 0.0) or np.any(designs > 1.0):
        raise BaselineArmError("initial_designs 必须有限且位于 [0,1]^12")
    if initial_design_metadata is not None and len(initial_design_metadata) != designs.shape[0]:
        raise BaselineArmError("initial_design_metadata 长度必须与 initial_designs 一致")
    if type(seed) is not int or seed < 0:
        raise BaselineArmError(f"seed 必须是非负整数，实际 {seed!r}")

    lower, upper = _unit_bounds()
    optimizer = ConstrainedBayesianOptimizer(
        lower,
        upper,
        seed=derive_arm_seed(task_id, seed, "bo", arm),
        candidate_count=candidate_count,
    )
    records: list[EvaluationRecord] = []
    wall_start = time.perf_counter()

    def on_observation(observation: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        design_u = np.asarray(observation.get("design_vector"), dtype=float)
        record = _record_from_result(
            eval_index=len(records) + 1,
            design_u=design_u,
            result=result,
            fallback_status="EVALUATION_FAILED",
        )
        records.append(record)

    try:
        search = run_search(
            optimizer,
            evaluate,
            designs,
            budget,
            strategy=strategy,
            on_observation=on_observation,
            initial_design_metadata=initial_design_metadata,
        )
    except RuntimeError as exc:
        # maml_opt.run_search 会把评估器异常统一包成 RuntimeError（它要求异常自带
        # analysis_calls 才能继续）。物理守卫违例必须原样上抛，否则 offline_runner
        # 无法识别为 PHYSICS_GUARD_VIOLATION 并立即中止整次 run（§12-14）。
        cause = exc.__cause__
        while cause is not None:
            if isinstance(cause, PhysicsGuardViolation):
                raise cause from exc
            cause = cause.__cause__
        raise
    wall_s = time.perf_counter() - wall_start
    termination = str(search.get("termination_reason") or "MAX_DESIGN_EVALUATIONS")
    return _summarize_arm(
        arm=arm,
        task_id=task_id,
        split=split,
        family=family,
        seed=seed,
        budget=budget,
        observations=records,
        wall_s=wall_s,
        termination_reason=termination,
        implementation=STAGE_IMPLEMENTATION[arm],
        initial_count=designs.shape[0],
        proxy_scoring_cost=proxy_scoring_cost,
        reference_objective=reference_objective,
    )


def _de_feasible(result: Mapping[str, Any]) -> bool:
    objective = _finite_or_none(result.get("objective"))
    constraints = _constraints_or_none(result.get("constraints_g_le_zero"))
    return bool(result.get("valid")) and _is_feasible(objective, constraints)


def _de_usable(result: Mapping[str, Any]) -> bool:
    return bool(result.get("valid")) and _finite_or_none(result.get("objective")) is not None


def _de_constraint_violation(result: Mapping[str, Any]) -> float:
    constraints = _constraints_or_none(result.get("constraints_g_le_zero")) or {}
    total = 0.0
    for value in constraints.values():
        if math.isfinite(value) and value > 0.0:
            total += value
    return total


def _de_better(candidate: Mapping[str, Any], incumbent: Mapping[str, Any]) -> bool:
    """与 baseline_de._better 相同的可行性优先选优规则。"""
    if not _de_usable(candidate):
        return False
    candidate_feasible = _de_feasible(candidate)
    incumbent_feasible = _de_feasible(incumbent)
    if candidate_feasible and not incumbent_feasible:
        return True
    if incumbent_feasible and not candidate_feasible:
        return False
    if candidate_feasible and incumbent_feasible:
        candidate_objective = _finite_or_none(candidate.get("objective"))
        incumbent_objective = _finite_or_none(incumbent.get("objective"))
        if candidate_objective is None or incumbent_objective is None:
            return False
        return candidate_objective < incumbent_objective
    return _de_constraint_violation(candidate) < _de_constraint_violation(incumbent)


def run_de_arm(
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task_id: str,
    split: str,
    family: str,
    seed: int,
    budget: int = TRUE_EVALUATION_BUDGET,
    population_size: int = DE_POPULATION_SIZE,
    mutation_factor: float = DE_MUTATION_FACTOR,
    crossover_rate: float = DE_CROSSOVER_RATE,
    reference_objective: float | None = None,
    run_id: str = "",
) -> ArmResult:
    """运行 OPT-DE：DE/rand/1/bin、8 个体 × 8 代、恰好 budget 次真实评价。

    初始种群复用与 BO 臂相同的共享 8 点（同一 (task, seed) LHS），见 §10。
    """
    if not callable(evaluate):
        raise BaselineArmError("evaluate 必须可调用")
    if type(budget) is not int or budget < population_size:
        raise BaselineArmError(f"budget 必须 >= population_size，实际 {budget!r}")
    if type(population_size) is not int or population_size < 4:
        raise BaselineArmError(f"population_size 必须 >= 4，实际 {population_size!r}")
    if not 0.0 < mutation_factor <= 1.0:
        raise BaselineArmError(f"mutation_factor 必须在 (0,1]，实际 {mutation_factor!r}")
    if not 0.0 <= crossover_rate <= 1.0:
        raise BaselineArmError(f"crossover_rate 必须在 [0,1]，实际 {crossover_rate!r}")
    if population_size == DE_POPULATION_SIZE:
        initial = shared_initial_designs(task_id, seed, count=DE_POPULATION_SIZE)
    else:
        initial = generate_initial_designs(
            *_unit_bounds(),
            population_size,
            seed=derive_arm_seed(task_id, seed, "shared_initial"),
            method="lhs",
        )
    rng = np.random.default_rng(derive_arm_seed(task_id, seed, "de"))
    records: list[EvaluationRecord] = []
    wall_start = time.perf_counter()

    def _evaluate(vector: np.ndarray, phase: str, generation: int, target_index: int) -> dict[str, Any]:
        clipped = np.clip(np.asarray(vector, dtype=float), 0.0, 1.0)
        result = evaluate(clipped.copy())
        if not isinstance(result, Mapping):
            raise BaselineArmError(f"评估器必须返回映射，实际 {type(result).__name__}")
        record = _record_from_result(
            eval_index=len(records) + 1,
            design_u=clipped,
            result=result,
            fallback_status="EVALUATION_FAILED",
        )
        records.append(record)
        return {
            "vector": clipped,
            "result": dict(result),
            "record": record,
            "phase": phase,
            "generation": generation,
            "target_index": target_index,
        }

    population: list[dict[str, Any]] = []
    for index, vector in enumerate(initial):
        population.append(_evaluate(np.asarray(vector, dtype=float), "initialisation", 0, index))
    generation = 1
    accepted_trials = 0
    rejected_trials = 0
    generations_completed = 0
    stagnation_generations = 0
    termination_reason = "search_finished"
    while True:
        if len(records) >= budget:
            termination_reason = "budget_exhausted"
            break
        generation_accepted = 0
        for target_index in range(population_size):
            if len(records) >= budget:
                termination_reason = "budget_exhausted"
                break
            picks = [index for index in range(population_size) if index != target_index]
            r1, r2, r3 = (int(value) for value in rng.choice(picks, size=3, replace=False))
            mutant = np.clip(
                population[r1]["vector"]
                + mutation_factor * (population[r2]["vector"] - population[r3]["vector"]),
                0.0,
                1.0,
            )
            forced_index = int(rng.integers(0, DESIGN_DIM))
            trial = np.array(
                [
                    mutant[index]
                    if rng.random() < crossover_rate or index == forced_index
                    else population[target_index]["vector"][index]
                    for index in range(DESIGN_DIM)
                ],
                dtype=float,
            )
            candidate = _evaluate(trial, "generation", generation, target_index)
            accepted = _de_better(candidate["result"], population[target_index]["result"])
            candidate["accepted"] = bool(accepted)
            if accepted:
                accepted_trials += 1
                generation_accepted += 1
                population[target_index] = candidate
            else:
                rejected_trials += 1
        if termination_reason == "budget_exhausted":
            break
        generations_completed = generation
        if generation_accepted == 0:
            # DE 可能出现整代无改进（已收敛或步长过小）；此处只累计停滞代数、
            # 不提前终止：§10 要求每 run 恰好 budget 次真实评价（等预算比较），
            # 提前 break 会使 true_evals_used < budget 并破坏五臂可比性。
            stagnation_generations += 1
        generation += 1
    wall_s = time.perf_counter() - wall_start
    return _summarize_arm(
        arm=DE_ARM,
        task_id=task_id,
        split=split,
        family=family,
        seed=seed,
        budget=budget,
        observations=records,
        wall_s=wall_s,
        termination_reason=termination_reason,
        implementation=STAGE_IMPLEMENTATION[DE_ARM],
        initial_count=min(population_size, len(records)),
        proxy_scoring_cost={
            "population_size": population_size,
            "generations_requested": DE_GENERATIONS,
            "generations_completed": generations_completed,
            "accepted_trials": accepted_trials,
            "rejected_trials": rejected_trials,
            "stagnation_generations": stagnation_generations,
        },
        reference_objective=reference_objective,
    )



class SyntheticTaskEvaluator:
    """解析合成 evaluator 工厂：u∈[0,1]^12 -> 限制/约束真值，物理调用恒为 0。

    解码唯一路径（§2.3）：u -> DesignSpace.from_unit_interval -> 12 名物理值
    -> DesignSpace.expand -> 15 名 -> check_bounds/check_cross_constraints。
    P4-CODE 阶段禁止任何真实求解器调用；若 result 中出现非零 physical_call_count，
    调用方（offline_runner）必须立即中止并写 PHYSICS_GUARD_VIOLATION。
    """

    def __init__(self, task: Any, design_space: DesignSpace) -> None:
        from .task_family import SyntheticTask

        if not isinstance(task, SyntheticTask):
            raise BaselineArmError("task 必须是 SyntheticTask")
        assert_synthetic_design_space(design_space)
        self.task = task
        self.design_space = design_space
        self.requested = 0
        self.billable = 0
        self.cache_hits = 0
        self.physical_call_count = 0
        self.records: list[dict[str, Any]] = []

    def decode(
        self, design_u: np.ndarray
    ) -> tuple[dict[str, float], dict[str, float], tuple[str, ...]]:
        unit = np.asarray(design_u, dtype=float).reshape(-1)
        if unit.shape != (DESIGN_DIM,):
            raise BaselineArmError(f"design_u 必须为 12 维，实际 {unit.shape}")
        if not np.all(np.isfinite(unit)) or np.any(unit < 0.0) or np.any(unit > 1.0):
            raise BaselineArmError("design_u 必须有限且位于 [0,1]^12")
        physical = dict(self.design_space.from_unit_interval(unit.tolist()))
        expanded = self.design_space.expand(physical)
        # check_bounds/check_cross_constraints 接收 12 名设计变量映射，内部自行 expand 固定机身
        errors = list(self.design_space.check_bounds(physical))
        errors.extend(self.design_space.check_cross_constraints(physical))
        return physical, expanded, tuple(errors)

    def __call__(self, design_u: np.ndarray) -> dict[str, Any]:
        unit = np.clip(np.asarray(design_u, dtype=float).reshape(-1), 0.0, 1.0)
        if unit.shape != (DESIGN_DIM,):
            raise BaselineArmError(f"design_u 必须为 12 维，实际 {unit.shape}")
        self.requested += 1
        physical, _expanded, geometry_errors = self.decode(unit)
        physical_vector = tuple(
            float(physical[name]) for name in self.design_space.names
        )
        base = {
            "analysis_calls": 1,
            "physical_call_count": self.physical_call_count,
            "cache_hit": False,
            "billable": True,
            "design_physical": physical_vector,
        }
        self.billable += 1
        if geometry_errors:
            result = {
                "valid": False,
                "feasible": False,
                "status": "GEOMETRY_INVALID",
                "objective": None,
                "constraints_g_le_zero": None,
                "error": "; ".join(geometry_errors),
                **base,
            }
            self.records.append(dict(result, design_u=tuple(float(value) for value in unit)))
            return result
        labels = self.task.truth(unit.reshape(1, DESIGN_DIM))
        objective = float(labels["objective"][0])
        constraints = {
            name: float(labels[name][0]) for name in self.task.enabled_constraint_names
        }
        if not math.isfinite(objective) or any(
            not math.isfinite(value) for value in constraints.values()
        ):
            result = {
                "valid": False,
                "feasible": False,
                "status": "NONFINITE",
                "objective": None,
                "constraints_g_le_zero": None,
                "error": "合成真值出现非有限数值",
                **base,
            }
            self.records.append(dict(result, design_u=tuple(float(value) for value in unit)))
            return result
        feasible = all(value <= FEASIBILITY_TOLERANCE for value in constraints.values())
        result = {
            "valid": True,
            "feasible": feasible,
            "status": "VALID" if feasible else "INFEASIBLE",
            "objective": objective,
            "constraints_g_le_zero": constraints,
            **base,
        }
        self.records.append(dict(result, design_u=tuple(float(value) for value in unit)))
        return result


def make_synthetic_task_evaluator(task: Any, design_space: DesignSpace) -> SyntheticTaskEvaluator:
    """构造解析合成 evaluator（P4-CODE 唯一允许的评估入口）。"""
    return SyntheticTaskEvaluator(task, design_space)


def _artifact_parts(artifact: Any) -> tuple[Any, Any]:
    """提取 artifact 的参数与配置（支持 meta_train 输出/字典/对象）。"""
    from .maml import MAMLConfig, ParameterSet

    if isinstance(artifact, Mapping):
        payload = dict(artifact)
    elif hasattr(artifact, "parameters") and hasattr(artifact, "config"):
        payload = {"parameters": artifact.parameters, "config": artifact.config}
    else:
        raise BaselineArmError(f"无法识别的 artifact 类型: {type(artifact).__name__}")
    parameters = payload.get("parameters", payload.get("final_parameters"))
    if parameters is None:
        raise BaselineArmError("artifact 缺少 parameters/final_parameters")
    if isinstance(parameters, Mapping):
        parameters = ParameterSet.from_dict(parameters)
    if not isinstance(parameters, ParameterSet):
        raise BaselineArmError("artifact 参数必须是 ParameterSet 或参数字典")
    config = payload.get("config")
    if isinstance(config, Mapping):
        config = MAMLConfig(**config)
    if config is None:
        config = MAMLConfig(
            input_dim=int(parameters.tensors[0].shape[0]),
            output_dim=int(parameters.tensors[-1].shape[1]),
            inner_steps=5,
        )
    if not isinstance(config, MAMLConfig):
        raise BaselineArmError("artifact config 必须是 MAMLConfig 或配置字典")
    return parameters, config


def predict_proxy_targets(
    artifact: Any,
    features: np.ndarray,
    *,
    method: str = "maml",
    support_features: np.ndarray | None = None,
    support_targets: np.ndarray | None = None,
    k_shot: int = 0,
) -> np.ndarray:
    """用（可能已适应的）代理模型做候选点预测；不消耗真实评估预算。"""
    from .adaptation import predict_parameters
    from .maml import TaskEpisode, init_parameters, inner_adapt

    parameters, config = _artifact_parts(artifact)
    matrix = np.asarray(features, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise BaselineArmError(f"features 必须为非空二维数组，实际 {matrix.shape}")
    if matrix.shape[1] != config.input_dim:
        raise BaselineArmError(
            f"候选特征维度 {matrix.shape[1]} 与代理 input_dim {config.input_dim} 不一致"
        )
    if method not in ("none", "maml", "fine_tuning", "from_scratch"):
        raise BaselineArmError(f"未知代理方法: {method!r}")
    if k_shot > 0:
        if support_features is None or support_targets is None:
            raise BaselineArmError("k_shot>0 时必须提供 support_features/support_targets")
        sx = np.asarray(support_features, dtype=float)
        sy = np.asarray(support_targets, dtype=float)
        if sy.ndim == 1:
            sy = sy[:, None]
        if sx.shape[0] != k_shot or sx.shape[1] != config.input_dim or sy.shape[0] != k_shot:
            raise BaselineArmError("support 形状与 k_shot/代理 input_dim 不一致")
        episode = TaskEpisode(sx, sy, sx, sy)
        if method == "maml":
            adapted, _ = inner_adapt(parameters, episode, config)
        elif method == "fine_tuning":
            tune = MAMLConfig(
                input_dim=config.input_dim,
                output_dim=config.output_dim,
                hidden_sizes=config.hidden_sizes,
                inner_lr=config.inner_lr,
                inner_steps=max(1, config.inner_steps),
                outer_lr=config.outer_lr,
                tasks_per_batch=1,
                first_order=True,
                seed=config.seed,
            )
            adapted, _ = inner_adapt(parameters, episode, tune)
        else:
            fresh = MAMLConfig(
                input_dim=config.input_dim,
                output_dim=config.output_dim,
                hidden_sizes=config.hidden_sizes,
                inner_lr=config.inner_lr,
                inner_steps=max(1, config.inner_steps),
                outer_lr=config.outer_lr,
                tasks_per_batch=1,
                first_order=True,
                seed=_stable_seed(config.seed, "from_scratch") % (2**31),
            )
            adapted = init_parameters(fresh)
            adapted, _ = inner_adapt(adapted, episode, fresh)
        parameters = adapted
    predictions = predict_parameters(parameters, matrix, config.output_dim)
    return np.asarray(predictions, dtype=float)


def score_maml_init_designs(
    artifact: Any,
    design_space: DesignSpace,
    task: Any,
    *,
    seed: int,
    candidate_count: int = MAML_INIT_CANDIDATE_COUNT,
    initial_design_count: int = MAML_INIT_INITIAL_DESIGN_COUNT,
    diversity_candidate_count: int = MAML_INIT_DIVERSITY_CANDIDATE_COUNT,
    method: str = "maml",
    k_shot: int = 0,
    support_features: np.ndarray | None = None,
    support_targets: np.ndarray | None = None,
    target_names: Sequence[str] | None = None,
    context_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """MAML 代理为候选池打分并选出初始 8 点（§8.2 冻结参数）。

    预测标签只用于“先评估哪些点”的排序，绝不写入 BO observations。
    """
    from .data_contract import CONTEXT_NAMES as DEFAULT_CONTEXT_NAMES
    from .surrogate import encode_features

    assert_synthetic_design_space(design_space)
    if type(seed) is not int or seed < 0:
        raise BaselineArmError(f"seed 必须是非负整数，实际 {seed!r}")
    if type(candidate_count) is not int or candidate_count < 1:
        raise BaselineArmError(f"candidate_count 必须是正整数，实际 {candidate_count!r}")
    if type(initial_design_count) is not int or initial_design_count < 1:
        raise BaselineArmError("initial_design_count 必须是正整数")
    if diversity_candidate_count < initial_design_count:
        raise BaselineArmError("diversity_candidate_count 必须 >= initial_design_count")
    context = dict(getattr(task, "context", {}))
    names = tuple(context_names or DEFAULT_CONTEXT_NAMES)
    if target_names is None:
        enabled = tuple(getattr(task, "enabled_constraint_names", ()))
        target_names = ("objective",) + enabled
    target_names = tuple(str(name) for name in target_names)
    if len(target_names) < 2:
        raise BaselineArmError("MAML-init 至少需要 objective 与一个约束目标列")
    candidates = generate_initial_designs(
        *_unit_bounds(),
        candidate_count,
        seed=derive_arm_seed(str(task.task_id), seed, "maml_init_pool"),
        method="lhs",
    )
    features = encode_features(candidates, context, names)
    wall_start = time.perf_counter()
    predictions = predict_proxy_targets(
        artifact,
        features,
        method=method,
        support_features=support_features,
        support_targets=support_targets,
        k_shot=k_shot,
    )
    if predictions.ndim == 1:
        predictions = predictions[:, None]
    if predictions.shape != (candidates.shape[0], len(target_names)):
        raise BaselineArmError(
            "代理预测列数必须与 target_names 一致："
            f"{predictions.shape} vs ({candidates.shape[0]}, {len(target_names)})"
        )
    selection = select_model_scored_initial_designs(
        candidates,
        predictions,
        list(target_names),
        objective_target_name="objective",
        constraint_target_names=list(target_names[1:]),
        design_lower_bounds=np.zeros(DESIGN_DIM),
        design_upper_bounds=np.ones(DESIGN_DIM),
        initial_design_count=initial_design_count,
        diversity_candidate_count=diversity_candidate_count,
    )
    proxy_wall_s = time.perf_counter() - wall_start
    return {
        "designs": np.asarray(selection["designs"], dtype=float),
        "selections": list(selection["selections"]),
        "candidate_indices": list(selection["candidate_indices"]),
        "candidate_designs": candidates,
        "predictions": predictions,
        "target_names": target_names,
        "candidate_count": candidate_count,
        "initial_design_count": initial_design_count,
        "diversity_candidate_count": diversity_candidate_count,
        "proxy_scoring_cost": {
            "candidates_scored": int(candidates.shape[0]),
            "model_forward_predictions": int(predictions.size),
            "adaptation_k_shot": int(k_shot),
            "wall_s": float(proxy_wall_s),
            "true_evaluation_budget_used": 0,
        },
        "method": "maml_init",
        "adaptation_method": method,
    }


def run_maml_init_arm(
    artifact: Any,
    design_space: DesignSpace,
    task: Any,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    seed: int,
    budget: int = TRUE_EVALUATION_BUDGET,
    candidate_count: int = MAML_INIT_CANDIDATE_COUNT,
    initial_design_count: int = MAML_INIT_INITIAL_DESIGN_COUNT,
    diversity_candidate_count: int = MAML_INIT_DIVERSITY_CANDIDATE_COUNT,
    method: str = "maml",
    k_shot: int = 0,
    support_features: np.ndarray | None = None,
    support_targets: np.ndarray | None = None,
    target_names: Sequence[str] | None = None,
    reference_objective: float | None = None,
    run_id: str = "",
) -> ArmResult:
    """OPT-BO-MAML-init：代理打分 8 初始点 + 同预算 BO 采集。"""
    scoring = score_maml_init_designs(
        artifact,
        design_space,
        task,
        seed=seed,
        candidate_count=candidate_count,
        initial_design_count=initial_design_count,
        diversity_candidate_count=diversity_candidate_count,
        method=method,
        k_shot=k_shot,
        support_features=support_features,
        support_targets=support_targets,
        target_names=target_names,
    )
    return run_bo_arm(
        MAML_INIT_ARM,
        evaluate,
        task_id=str(task.task_id),
        split=str(task.split),
        family=str(task.family),
        seed=seed,
        budget=budget,
        initial_designs=scoring["designs"],
        initial_design_metadata=scoring["selections"],
        reference_objective=reference_objective,
        run_id=run_id,
        proxy_scoring_cost=scoring["proxy_scoring_cost"],
    )


def compare_initializers(
    design_space: DesignSpace,
    artifact: Any,
    tasks: Sequence[Any],
    methods: Sequence[str],
    budget: int = TRUE_EVALUATION_BUDGET,
    seed: int = 0,
) -> dict[str, Any]:
    """§8 初始化对照：对任务 × 方法运行等预算优化并汇总。"""
    if not tasks:
        raise BaselineArmError("tasks 不能为空")
    if set(methods) - set(ARMS):
        raise BaselineArmError(f"methods 只允许 {ARMS}，实际 {tuple(methods)}")
    results: list[ArmResult] = []
    for task in tasks:
        reference = float(task.reference()["objective_star"])
        for arm in methods:
            evaluator = make_synthetic_task_evaluator(task, design_space)
            if arm == MAML_INIT_ARM:
                result = run_maml_init_arm(
                    artifact,
                    design_space,
                    task,
                    evaluator,
                    seed=seed,
                    budget=budget,
                    reference_objective=reference,
                )
            elif arm == DE_ARM:
                result = run_de_arm(
                    evaluator,
                    task_id=str(task.task_id),
                    split=str(task.split),
                    family=str(task.family),
                    seed=seed,
                    budget=budget,
                    reference_objective=reference,
                )
            else:
                result = run_bo_arm(
                    arm,
                    evaluator,
                    task_id=str(task.task_id),
                    split=str(task.split),
                    family=str(task.family),
                    seed=seed,
                    budget=budget,
                    reference_objective=reference,
                )
            if evaluator.physical_call_count != PHYSICS_GUARD_EXPECTED:
                raise PhysicsGuardViolation(
                    f"合成评估器报告 physical_call_count={evaluator.physical_call_count}",
                    physical_call_count=evaluator.physical_call_count,
                )
            results.append(result)
    return {
        "status": VALID_STATUS,
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "results": results,
        "summaries": [result.to_summary_row() for result in results],
    }


def paired_statistics(
    differences: Sequence[float],
    *,
    seed: int = 42,
    bootstrap_samples: int = 10000,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """配对差的中位差 + bootstrap 95% CI + Wilcoxon 符号秩（§10 统计）。"""
    values = np.asarray([float(value) for value in differences], dtype=float)
    if values.size == 0:
        raise BaselineArmError("配对差数组不能为空")
    finite = values[np.isfinite(values)]
    if finite.size != values.size:
        raise BaselineArmError("配对差必须全部有限")
    median = float(np.median(finite))
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, finite.size, size=(int(bootstrap_samples), finite.size))
    bootstrap_medians = np.median(finite[indices], axis=1)
    alpha = (1.0 - float(confidence)) / 2.0
    ci_low = float(np.quantile(bootstrap_medians, alpha))
    ci_high = float(np.quantile(bootstrap_medians, 1.0 - alpha))
    result: dict[str, Any] = {
        "n": int(finite.size),
        "median_diff": median,
        "mean_diff": float(np.mean(finite)),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "confidence": float(confidence),
        "bootstrap_samples": int(bootstrap_samples),
        "seed": int(seed),
        "wilcoxon_statistic": None,
        "wilcoxon_pvalue": None,
    }
    if finite.size >= 5 and np.any(finite != 0.0):
        try:
            from scipy.stats import wilcoxon

            statistic, pvalue = wilcoxon(finite, zero_method="wilcox", alternative="two-sided")
            result["wilcoxon_statistic"] = float(statistic)
            result["wilcoxon_pvalue"] = float(pvalue)
        except ValueError:
            result["wilcoxon_statistic"] = None
            result["wilcoxon_pvalue"] = None
    return result


def grouped_metric_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    metric: str = "rmse",
    group_field: str = "arm",
    aggregation_level: str = "per_task",
) -> dict[str, dict[str, Any]]:
    """按 arm（或任意字段）分组汇总指标，供 metrics.csv 的 group_mean/std/ci95 使用。"""
    groups: dict[str, list[float]] = {}
    for row in rows:
        value = row.get(metric)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        groups.setdefault(str(row.get(group_field, "")), []).append(number)
    summary: dict[str, dict[str, Any]] = {}
    for key, values in groups.items():
        array = np.asarray(values, dtype=float)
        stats = paired_statistics(array, seed=0, bootstrap_samples=1000)
        summary[key] = {
            "aggregation_level": aggregation_level,
            "n": int(array.size),
            "mean": float(np.mean(array)),
            "std": float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
            "median": float(np.median(array)),
            "min": float(np.min(array)),
            "max": float(np.max(array)),
            "ci95_low": stats["ci_low"],
            "ci95_high": stats["ci_high"],
        }
    return summary


def summarize_arm_results(results: Sequence[ArmResult], *, run_id: str = "") -> dict[str, Any]:
    """汇总一批臂结果：状态计数、物理调用计数、每任务汇总行。"""
    if not results:
        raise BaselineArmError("results 不能为空")
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
    return {
        "run_id": run_id,
        "n_results": len(results),
        "status_counts": status_counts,
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "true_evals_used_total": int(sum(result.true_evals_used for result in results)),
        "summary_rows": [result.to_summary_row(run_id=run_id) for result in results],
    }


__all__ = [
    "ARMS",
    "BO_ARMS",
    "DE_ARM",
    "MAML_INIT_ARM",
    "DE_GENERATIONS",
    "DE_POPULATION_SIZE",
    "MAML_INIT_CANDIDATE_COUNT",
    "MAML_INIT_DIVERSITY_CANDIDATE_COUNT",
    "MAML_INIT_INITIAL_DESIGN_COUNT",
    "TRUE_EVALUATION_BUDGET",
    "ArmResult",
    "BaselineArmError",
    "EvaluationRecord",
    "PhysicsGuardViolation",
    "SyntheticTaskEvaluator",
    "assert_synthetic_design_space",
    "assert_synthetic_feature_units",
    "compare_initializers",
    "derive_arm_seed",
    "grouped_metric_summary",
    "make_synthetic_task_evaluator",
    "paired_statistics",
    "predict_proxy_targets",
    "run_bo_arm",
    "run_de_arm",
    "run_maml_init_arm",
    "score_maml_init_designs",
    "shared_initial_designs",
    "summarize_arm_results",
]
