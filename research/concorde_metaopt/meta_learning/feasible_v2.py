# -*- coding: utf-8 -*-
"""P4-M5：F-QE-feasible-v2 的校准、冻结与预注册（fail-closed）。

本模块只做**合成解析**层面的校准与元数据冻结，不调用任何真实求解器
（physical_call_count 恒为 0）。协议见
docs/planning/p4_m5_m6_plan_20261104.md §1：

1. 校准（--stage calibration）：只在 meta_train/meta_validation 的 8+8 cohort 上
   跑普通 BO（BO-random 同引擎，8 初始 + B=64），逐半径估计成功率；
   阶段内**不构造、不读取** meta_test/meta_test_ood/negative_control 任务。
2. 选半径（预注册规则，A13 裁决后加严）：**只用 meta_train 训练任务**，
   固定优化 seeds=(0,1,2)，按 (任务, seed) pooled 成功率落在 [0.30, 0.70]
   （安全落在 20–80% 验收带内）的格中选 feasible_hit_rate 中位数最接近 0.5
   的半径，并列取较小半径；禁止按 MAML 胜负或任何测试集表现选择。
3. 冻结（--stage holdout 前）：生成 frozen_family.json + meta_task_split.json +
   preregistration.json；任何 hash 不匹配/缺失即 fail-closed，不得开测试集。
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from . import task_family as tf
from .baseline_arms import ArmResult, make_synthetic_task_evaluator, run_bo_arm
from .data_contract import SPLITS
from .offline_runner import (
    iso_utc,
    load_design_space_12d,
    sha256_file_normalized,
    write_csv,
    write_json,
)

# ---------------------------------------------------------------------------
# 常量（全部写入 frozen_family / preregistration，冻结后不得静默改动）
# ---------------------------------------------------------------------------
CALIBRATION_STAGE = "calibration"
HOLDOUT_STAGE = "holdout"
STAGES = (CALIBRATION_STAGE, HOLDOUT_STAGE)

RADIUS_GRID = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00)
CALIBRATION_OPT_SEEDS = (0, 1, 2)
CALIBRATION_TRAIN_TASKS = 8
CALIBRATION_VALIDATION_TASKS = 8
CALIBRATION_BUDGET = 64
CALIBRATION_EMPIRICAL_SAMPLES = 256
# 验收带（验收软指标：普通 BO 成功率 20–80%，非统计硬指标）
ACCEPTANCE_SUCCESS_LOW = 0.20
ACCEPTANCE_SUCCESS_HIGH = 0.80
# 校准选中带（A13 裁决：pooled success 30–70%，安全落在验收带内）
TARGET_SUCCESS_LOW = 0.30
TARGET_SUCCESS_HIGH = 0.70
TARGET_HIT_RATE = 0.50
CALIBRATION_SPLITS = ("meta_train", "meta_validation")
CALIBRATION_SELECTION_SPLIT = "meta_train"
SEALED_SPLITS = ("meta_test", "meta_test_ood")
BO_RANDOM_ARM = "OPT-BO-rand"

# 参考解几何与 gap 定义（写入 frozen_family.json，A13 裁决要求）
REFERENCE_SOLUTION = "c"
GAP_DEFINITION = "f(u_best)-f(u*)"
META_TEST_TUNING_POLICY = (
    "禁止使用 meta_test/meta_test_ood 的任何信息（成功率/误差/gap）调参、"
    "选半径、选臂或选终点；测试集只在 frozen_family + preregistration 的 "
    "sha256/fingerprint/split_hash 校验通过后一次性构造并评估一次。"
)

# 12 维单位球体积 π^6/6!（解析近似，仅作记录，不作判据）
SPHERE_VOLUME_12 = math.pi ** 6 / math.factorial(6)

FROZEN_SCHEMA_VERSION = "p4-m5-frozen-v2-1"
SPLIT_SCHEMA_VERSION = "p4-m5-split-1"
PREREGISTRATION_SCHEMA_VERSION = "p4-m5-prereg-v2"
# 历史预注册 schema：旧 run 的 preregistration.json 按原样只读校验（不含 v2 的
# stopping_rules 类型强校验），避免历史工件因旧序列化缺陷被追溯判为不可验证。
LEGACY_PREREGISTRATION_SCHEMA_VERSIONS: tuple[str, ...] = ("p4-m5-prereg-v1",)
CALIBRATION_SCHEMA_VERSION = "p4-m5-calibration-1"

SELECTION_RULE = (
    "只在 meta_train 的 8 个校准任务上、固定优化 seeds=(0,1,2) 跑 B=64 "
    "BO-random；pooled success rate（成功 (任务,seed) 数 / (8×3)）落在 "
    "[0.30, 0.70] 的半径格为候选；候选中取 pooled feasible_hit_rate 中位数"
    "最接近 0.5 者，并列取较小 radius_base；meta_validation 仅作难度旁证，"
    "不参与选中判定；禁止按 MAML 胜负或任何测试集表现选择。"
)

M5_ARMS = (
    "M5-BO-random",
    "M5-BO-pretrain-init",
    "M5-BO-MAML-init",
    "M5-DE",
)
M5_BUDGETS = (64, 128)
M5_OPTIMIZATION_SEEDS = tuple(range(10))
M5_META_SEEDS = (0, 1, 2)

PRIMARY_ENDPOINTS = (
    "best_feasible_value",
    "gap_to_reference",
    "first_feasible_evaluation_index",
    "feasible_hit_rate",
)
SECONDARY_ENDPOINTS = (
    "best_objective_raw",
    "min_constraint_violation_sum",
    "true_evals_used",
    "cache_hits",
    "wall_s",
    "n_failed_evals",
)
NULL_POLICY = (
    "不可行/失败评价保留 objective=null 且计入预算；空值不插补、不转 0；"
    "非 null 样本占比 <70% 的终点标 INCONCLUSIVE 并给出原因，不补假曲线。"
)
STATISTICS_PLAN = {
    "unit": "task",
    "seed_aggregation": "优化 seed 在任务内先聚合，避免伪重复",
    "paired_differences": "(task, seed, budget) 配对差",
    "bootstrap_samples": 10000,
    "confidence": 0.95,
    "test": "wilcoxon_signed_rank",
    "effect_size": "paired_cohen_d / rank_biserial",
    "multiple_comparison": "Holm-Bonferroni（M5 6 臂对 × 2 预算 × 4 主终点）",
}
STOPPING_RULES = (
    "两阶段：calibration 只开 train/validation；holdout 仅在 frozen_family + "
    "preregistration 的 sha256 校验通过后一次性构造 meta_test/ood。",
)
STOPPING_RULE_MIN_LENGTH = 2
NON_CLAIMS = (
    "SYNTHETIC_ONLY：合成解析任务，不代表真实飞机/CFD 性能；"
    "physical_call_count=0；旧 F-QE 压力测试结果单独成表，不与 v2 混算绝对目标。",
)


class FeasibleV2Error(ValueError):
    """v2 校准/冻结/预注册协议违规。"""


# ---------------------------------------------------------------------------
# preregistration.stopping_rules 序列化与类型校验
# ---------------------------------------------------------------------------
def normalize_stopping_rules(value):
    """把 stopping_rules 规范化为非空 list[str]（fail-closed）。

    - 单个 str 视为一条规则（旧 API 允许直接传 STOPPING_RULES 常量）；
    - Sequence 逐项必须是 str，strip 后非空且长度 >= STOPPING_RULE_MIN_LENGTH；
    - 拒绝逐字符拆分形态（如 list(字符串) 产生的单字符数组）、空列表与
      非字符串元素，异常信息直接给出修复方向。

    根因背景：STOPPING_RULES 常量漏写尾逗号时是单个 str，旧实现
    list(stopping_rules) 会把中文逐字符拆成数组写进 preregistration.json。
    """
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raise FeasibleV2Error(
            "preregistration.stopping_rules 必须是 list[str] 或 str，实际 %s"
            % type(value).__name__
        )
    if not raw:
        raise FeasibleV2Error("preregistration.stopping_rules 不能为空")
    rules = []
    for index, item in enumerate(raw):
        if not isinstance(item, str):
            raise FeasibleV2Error(
                "preregistration.stopping_rules[%d] 必须是 str，实际 %s"
                % (index, type(item).__name__)
            )
        if not item.strip():
            raise FeasibleV2Error(
                "preregistration.stopping_rules[%d] 不能为空字符串" % index
            )
        if len(item.strip()) < STOPPING_RULE_MIN_LENGTH:
            raise FeasibleV2Error(
                "preregistration.stopping_rules[%d] 长度必须 >= %d（当前 %r）"
                "；疑似把字符串误用 list() 拆成单字符数组"
                % (index, STOPPING_RULE_MIN_LENGTH, item)
            )
        # 落盘前统一 strip（A5 m07：不允许残留首尾空白）
        rules.append(item.strip())
    return rules


def validate_preregistration_schema(prereg):
    """校验预注册 schema 版本与 stopping_rules 存储类型（fail-closed）。

    v2（当前 schema）要求 stopping_rules 已序列化为非空 JSON 数组，每项为
    非空且长度 >= 2 的 str；历史 schema 仅校验版本可识别，保持旧 run 兼容。
    """
    schema = prereg.get("schema_version")
    if schema == PREREGISTRATION_SCHEMA_VERSION:
        if "stopping_rules" not in prereg:
            raise FeasibleV2Error("preregistration 缺少 stopping_rules 字段")
        stored = prereg["stopping_rules"]
        if isinstance(stored, str) or not isinstance(stored, (list, tuple)):
            raise FeasibleV2Error(
                "preregistration.stopping_rules 必须序列化为 JSON 数组（list[str]），"
                "实际 %s" % type(stored).__name__
            )
        normalize_stopping_rules(stored)
        return
    if schema in LEGACY_PREREGISTRATION_SCHEMA_VERSIONS:
        return
    raise FeasibleV2Error("prereg schema 不符: %r" % (schema,))


# ---------------------------------------------------------------------------
# 序列化与哈希
# ---------------------------------------------------------------------------
def canonical_json(value: Any) -> str:
    """规范化 JSON（扁平 key 排序、无多余空白），用于哈希。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"无法序列化为 JSON 的类型: {type(value).__name__}")


def digest(value: Any) -> str:
    """规范化 JSON 的 sha256。"""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    """按 CRLF->LF 规范化计算文件 sha256（与 data_manifest 的 hash_mode 一致）。"""
    return sha256_file_normalized(path)[0]


def package_code_sha(directory: str | Path | None = None) -> str:
    """meta_learning 包内全部 .py 文件的代码指纹（按文件名排序聚合）。"""
    root = Path(directory) if directory is not None else Path(__file__).resolve().parent
    entries = []
    for path in sorted(root.glob("*.py"), key=lambda item: item.name):
        entries.append({"name": path.name, "sha256": file_sha256(path)})
    return digest(entries)


def serialize_family_config(config: tf.TaskFamilyConfig) -> dict[str, Any]:
    """把 TaskFamilyConfig 全字段序列化为 JSON 可存储字典。"""
    payload: dict[str, Any] = {}
    for field in dataclasses.fields(tf.TaskFamilyConfig):
        value = getattr(config, field.name)
        if isinstance(value, tuple):
            payload[field.name] = list(value)
        else:
            payload[field.name] = value
    return payload


def deserialize_family_config(payload: Mapping[str, Any]) -> tf.TaskFamilyConfig:
    """从 frozen payload 还原 TaskFamilyConfig（字段必须完整，否则 fail-closed）。"""
    values = dict(payload)
    if "context_names" in values:
        values["context_names"] = tuple(values["context_names"])
    try:
        return tf.TaskFamilyConfig(**values)
    except TypeError as error:
        raise FeasibleV2Error(f"family_config 字段不匹配: {error}") from error


def split_order() -> tuple[str, ...]:
    """五 split 的固定顺序（与 data_contract.SPLITS 一致）。"""
    return tuple(SPLITS)


# ---------------------------------------------------------------------------
# 校准配置与 cohort
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CalibrationConfig:
    """校准协议配置（跨半径固定，写入报告）。"""

    radius_grid: tuple[float, ...] = RADIUS_GRID
    opt_seeds: tuple[int, ...] = CALIBRATION_OPT_SEEDS
    train_tasks: int = CALIBRATION_TRAIN_TASKS
    validation_tasks: int = CALIBRATION_VALIDATION_TASKS
    budget: int = CALIBRATION_BUDGET
    family_seed: int = 42
    empirical_samples: int = CALIBRATION_EMPIRICAL_SAMPLES

    def __post_init__(self) -> None:
        grid = tuple(float(value) for value in self.radius_grid)
        if not grid:
            raise FeasibleV2Error("radius_grid 不能为空")
        for value in grid:
            if not math.isfinite(value) or value <= 0.0:
                raise FeasibleV2Error(f"radius_grid 必须为正有限数，实际 {value!r}")
        if len(set(grid)) != len(grid):
            raise FeasibleV2Error("radius_grid 不能重复")
        object.__setattr__(self, "radius_grid", grid)
        seeds = tuple(int(value) for value in self.opt_seeds)
        if not seeds:
            raise FeasibleV2Error("opt_seeds 不能为空")
        if any(value < 0 for value in seeds) or len(set(seeds)) != len(seeds):
            raise FeasibleV2Error(f"opt_seeds 必须为非负且不重复，实际 {seeds}")
        object.__setattr__(self, "opt_seeds", seeds)
        for name in ("train_tasks", "validation_tasks", "empirical_samples"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise FeasibleV2Error(f"{name} 必须是正整数，实际 {value!r}")
        if type(self.budget) is not int or self.budget < 2:
            raise FeasibleV2Error(f"budget 必须是 >=2 的整数，实际 {self.budget!r}")
        if type(self.family_seed) is not int or self.family_seed < 0:
            raise FeasibleV2Error(f"family_seed 必须是非负整数，实际 {self.family_seed!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "radius_grid": list(self.radius_grid),
            "opt_seeds": list(self.opt_seeds),
            "train_tasks": self.train_tasks,
            "validation_tasks": self.validation_tasks,
            "budget": self.budget,
            "family_seed": self.family_seed,
            "empirical_samples": self.empirical_samples,
        }


def calibration_family_config(radius_base: float, calibration: CalibrationConfig) -> tf.TaskFamilyConfig:
    """构造只含 meta_train/meta_validation 的校准 v2 配置（不产生 test/ood/负控制）。"""
    return tf.TaskFamilyConfig(
        family_id=tf.V2_FAMILY_ID,
        design_dim=12,
        context_names=("context_1", "context_2"),
        seed=calibration.family_seed,
        train_tasks=calibration.train_tasks,
        validation_tasks=calibration.validation_tasks,
        test_tasks=0,
        ood_tasks=0,
        negative_control_tasks=0,
        designs_per_task=24,
        support_pool_size=16,
        query_size=8,
        family_version="v2",
        radius_base=float(radius_base),
    )


def assert_calibration_only(tasks: Sequence[tf.SyntheticTask]) -> None:
    """fail-closed：校准阶段只允许 meta_train/meta_validation。"""
    for task in tasks:
        if task.split not in CALIBRATION_SPLITS:
            raise FeasibleV2Error(
                f"校准阶段禁止构造/使用 split={task.split!r} 的任务 {task.task_id}"
            )
        if task.is_negative_control:
            raise FeasibleV2Error(f"校准阶段禁止负控制任务 {task.task_id}")
    if not tasks:
        raise FeasibleV2Error("校准 cohort 为空")


def build_calibration_cohort(
    radius_base: float, calibration: CalibrationConfig
) -> tuple[tf.TaskFamilyConfig, tuple[tf.SyntheticTask, ...]]:
    """按半径构造校准 cohort：返回 (config, 任务元组)，并断言不含测试集。"""
    config = calibration_family_config(radius_base, calibration)
    tasks = tuple(tf.build_task_family(config))
    assert_calibration_only(tasks)
    expected = calibration.train_tasks + calibration.validation_tasks
    if len(tasks) != expected:
        raise FeasibleV2Error(f"校准 cohort 任务数 {len(tasks)} != 期望 {expected}")
    return config, tasks


def assert_reference_certificates(tasks: Sequence[tf.SyntheticTask]) -> dict[str, dict[str, Any]]:
    """fail-closed：u*=c 处全部约束严格可行（margin>0）、objective 有限、KKT=0。"""
    if not tasks:
        raise FeasibleV2Error("assert_reference_certificates 需要非空任务列表")
    certificates: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if getattr(task, "is_negative_control", False):
            raise FeasibleV2Error(f"负控制任务 {task.task_id} 没有参考解，不能做参考解证书")
        reference = task.reference()
        u_star = np.asarray(reference["u_star"], dtype=float)
        center = np.asarray(task.params["c"], dtype=float)
        objective = float(reference["objective_star"])
        if not np.isfinite(objective):
            raise FeasibleV2Error(f"{task.task_id}: 参考目标非有限 {objective!r}")
        if np.max(np.abs(u_star - center)) > 1e-12:
            raise FeasibleV2Error(f"{task.task_id}: u* 不等于中心点 c（v2 参考解应为 c）")
        constraints = dict(reference.get("constraints") or {})
        if not constraints:
            raise FeasibleV2Error(f"{task.task_id}: 参考解缺少约束值")
        margins = {name: -float(value) for name, value in constraints.items()}
        if any(not math.isfinite(value) for value in margins.values()):
            raise FeasibleV2Error(f"{task.task_id}: 参考解约束值非有限 {constraints}")
        min_margin = float(min(margins.values()))
        if min_margin <= 0.0:
            raise FeasibleV2Error(
                f"{task.task_id}: u*=c 处约束未严格可行，最小 margin={min_margin:.3e}（要求 >0）"
            )
        kkt = float(reference.get("kkt_residual", 0.0) or 0.0)
        if abs(kkt) > tf.REFERENCE_ABS_TOL:
            raise FeasibleV2Error(f"{task.task_id}: 参考解 KKT 残差 {kkt:.3e} 超容差")
        certificates[task.task_id] = {
            "objective_star": objective,
            "min_margin": min_margin,
            "kkt_residual": kkt,
            "constraints": constraints,
        }
    return certificates


# ---------------------------------------------------------------------------
# 可行体积的解析近似与固定 seed MC 估计（双记录，仅作难度记录）
# ---------------------------------------------------------------------------
def analytic_sphere_fraction(radius: float) -> float:
    """12 维单位球体积近似 p≈V_12·r^12（未计椭球权重，偏低/偏高均可能）。"""
    if radius <= 0.0:
        raise FeasibleV2Error(f"radius 必须为正，实际 {radius!r}")
    return float(min(1.0, SPHERE_VOLUME_12 * float(radius) ** 12))


def analytic_ellipsoid_fraction(radius: float, w: Sequence[float]) -> float:
    """椭球体积近似 p≈V_12·r^12 / sqrt(prod w)，并截断到 [0,1]。"""
    weights = np.asarray(list(w), dtype=float)
    if weights.shape != (12,) or not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        raise FeasibleV2Error(f"w 必须是 12 个正有限数，实际 {w!r}")
    value = SPHERE_VOLUME_12 * float(radius) ** 12 / math.sqrt(float(np.prod(weights)))
    return float(min(1.0, value))


def feasible_volume_fraction_mc(
    tasks: Sequence[tf.SyntheticTask], *, samples: int, seed: int
) -> float:
    """固定 seed 的均匀 MC 可行体积分数估计（非求解器，仅作难度记录/冻结字段）。"""
    if not tasks:
        raise FeasibleV2Error("feasible_volume_fraction_mc 需要非空任务列表")
    if samples < 1:
        raise FeasibleV2Error(f"samples 必须为正整数，实际 {samples!r}")
    rng = np.random.default_rng(int(seed))
    feasible = 0
    total = 0
    for task in tasks:
        designs = rng.uniform(0.0, 1.0, size=(int(samples), 12))
        mask = np.asarray(task.truth(designs)["feasibility"], dtype=bool)
        feasible += int(np.sum(mask))
        total += int(samples)
    return float(feasible / total)


def empirical_feasible_fraction(
    tasks: Sequence[tf.SyntheticTask], *, samples: int, seed: int
) -> float:
    """兼容旧名：逐任务 LHS 经验可行率的中位数（诊断用）。"""
    if not tasks:
        raise FeasibleV2Error("empirical_feasible_fraction 需要非空任务列表")
    fractions = []
    for index, task in enumerate(tasks):
        designs = tf.sample_designs(task, samples, "lhs", seed=int(seed) + index)
        feasibility = np.asarray(task.truth(designs)["feasibility"], dtype=bool)
        fractions.append(float(np.mean(feasibility)))
    return float(np.median(fractions))


# ---------------------------------------------------------------------------
# 校准结果行
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CalibrationTaskRow:
    """单个 (radius, seed, task) 的 BO-random 校准记录。"""

    radius_base: float
    opt_seed: int
    task_id: str
    split: str
    success: bool
    feasible_count: int
    first_feasible_eval_index: int | None
    best_feasible_value: float | None
    best_objective_raw: float | None
    min_constraint_violation_sum: float | None
    n_null: int
    evaluations: int
    wall_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "radius_base": self.radius_base,
            "opt_seed": self.opt_seed,
            "task_id": self.task_id,
            "split": self.split,
            "success": self.success,
            "feasible_count": self.feasible_count,
            "first_feasible_eval_index": self.first_feasible_eval_index,
            "best_feasible_value": self.best_feasible_value,
            "best_objective_raw": self.best_objective_raw,
            "min_constraint_violation_sum": self.min_constraint_violation_sum,
            "n_null": self.n_null,
            "evaluations": self.evaluations,
            "wall_s": self.wall_s,
        }


@dataclass(frozen=True)
class CalibrationCell:
    """单个 radius_base 格的汇总（逐 seed 成功率 + 中位数 + 经验可行率）。"""

    radius_base: float
    success_rate_by_seed: tuple[float, ...]
    feasible_hit_rate_by_seed: tuple[float, ...]
    success_rate_median: float
    feasible_hit_rate_median: float
    pooled_success_train: float
    pooled_hit_rate_train: float
    validation_success_rate_median: float
    all_seeds_in_acceptance: bool
    analytic_sphere_fraction: float
    analytic_ellipsoid_fraction_median: float
    feasible_volume_fraction: float
    n_tasks: int
    budget: int
    evaluations: int
    n_null: int
    wall_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "radius_base": self.radius_base,
            "success_rate_by_seed": list(self.success_rate_by_seed),
            "feasible_hit_rate_by_seed": list(self.feasible_hit_rate_by_seed),
            "success_rate_median": self.success_rate_median,
            "feasible_hit_rate_median": self.feasible_hit_rate_median,
            "pooled_success_train": self.pooled_success_train,
            "pooled_hit_rate_train": self.pooled_hit_rate_train,
            "validation_success_rate_median": self.validation_success_rate_median,
            "all_seeds_in_acceptance": self.all_seeds_in_acceptance,
            "analytic_sphere_fraction": self.analytic_sphere_fraction,
            "analytic_ellipsoid_fraction_median": self.analytic_ellipsoid_fraction_median,
            "feasible_volume_fraction": self.feasible_volume_fraction,
            "n_tasks": self.n_tasks,
            "budget": self.budget,
            "evaluations": self.evaluations,
            "n_null": self.n_null,
            "wall_s": self.wall_s,
        }


def _fallback_metrics_from_observations(observations: Sequence[Any]) -> tuple[float | None, float | None, int]:
    """A7 fallback：最小原始目标、对应设计的正违反总和、null 目标个数。"""
    objective = None
    violation = None
    null_count = 0
    for observation in observations:
        value = observation.objective
        if value is None or not math.isfinite(float(value)):
            null_count += 1
            continue
        value = float(value)
        if objective is None or value < objective:
            objective = value
            constraints = observation.constraints or {}
            violation = float(sum(max(0.0, float(item)) for item in constraints.values()))
    return objective, violation, null_count


def _calibration_row(radius: float, seed: int, task: tf.SyntheticTask, result: ArmResult) -> CalibrationTaskRow:
    best_raw, violation, null_count = _fallback_metrics_from_observations(result.observations)
    return CalibrationTaskRow(
        radius_base=float(radius),
        opt_seed=int(seed),
        task_id=task.task_id,
        split=task.split,
        success=bool(result.feasible_count > 0),
        feasible_count=int(result.feasible_count),
        first_feasible_eval_index=result.first_feasible_eval_index,
        best_feasible_value=result.best_feasible_value,
        best_objective_raw=best_raw,
        min_constraint_violation_sum=violation,
        n_null=int(null_count),
        evaluations=int(len(result.observations)),
        wall_s=float(result.wall_s),
    )


@dataclass(frozen=True)
class CalibrationReport:
    """完整校准报告（逐任务行 + 逐格汇总 + 选择结果）。"""

    schema_version: str
    created_utc: str
    calibration: CalibrationConfig
    cells: tuple[CalibrationCell, ...]
    rows: tuple[CalibrationTaskRow, ...]
    cohorts: tuple[dict[str, Any], ...]
    reference_certificates: tuple[dict[str, Any], ...]
    selected_radius_base: float | None
    selection_status: str
    selection_rule: str
    notes: tuple[str, ...]
    physical_call_count: int = 0

    @property
    def selected_cell(self) -> CalibrationCell | None:
        if self.selected_radius_base is None:
            return None
        for cell in self.cells:
            if cell.radius_base == self.selected_radius_base:
                return cell
        return None

    def selected_cohort(self) -> dict[str, list[str]]:
        if self.selected_radius_base is None:
            raise FeasibleV2Error("校准未选出半径，不能取 cohort")
        for cohort in self.cohorts:
            if float(cohort["radius_base"]) == float(self.selected_radius_base):
                return {split: list(ids) for split, ids in cohort["task_ids"].items()}
        raise FeasibleV2Error("selected_radius_base 不在 cohorts 中")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_utc": self.created_utc,
            "physical_call_count": self.physical_call_count,
            "calibration": self.calibration.to_dict(),
            "selection_rule": self.selection_rule,
            "selection_status": self.selection_status,
            "selected_radius_base": self.selected_radius_base,
            "selected_cell": None if self.selected_cell is None else self.selected_cell.to_dict(),
            "cells": [cell.to_dict() for cell in self.cells],
            "cohorts": [dict(cohort) for cohort in self.cohorts],
            "reference_certificates": [dict(item) for item in self.reference_certificates],
            "task_rows": [row.to_dict() for row in self.rows],
            "notes": list(self.notes),
        }

    @property
    def sha256(self) -> str:
        return digest(self.to_dict())


def _seed_rates(rows: Sequence[CalibrationTaskRow], seed: int, n_tasks: int, budget: int) -> tuple[float, float]:
    selected = [row for row in rows if row.opt_seed == seed]
    if len(selected) != n_tasks:
        raise FeasibleV2Error(f"seed={seed} 的校准行数 {len(selected)} != {n_tasks}")
    success = sum(1 for row in selected if row.success) / n_tasks
    hit = sum(row.feasible_count for row in selected) / (n_tasks * budget)
    return float(success), float(hit)


def _pooled_train_rates(
    rows: Sequence[CalibrationTaskRow], n_train_tasks: int, n_seeds: int, budget: int
) -> tuple[float, float]:
    """只用 meta_train 任务、跨 3 个优化 seed 的 pooled 成功率与命中率。"""
    selected = [row for row in rows if row.split == CALIBRATION_SELECTION_SPLIT]
    if len(selected) != n_train_tasks * n_seeds:
        raise FeasibleV2Error(
            f"meta_train 校准行数 {len(selected)} != {n_train_tasks}×{n_seeds}"
        )
    success = sum(1 for row in selected if row.success) / len(selected)
    hit = sum(row.feasible_count for row in selected) / (len(selected) * budget)
    return float(success), float(hit)


def calibrate_radius_base(
    calibration: CalibrationConfig | None = None,
    *,
    design_space: Any | None = None,
    progress: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> CalibrationReport:
    """逐半径跑 BO-random 校准，按 A13 加严规则选 radius_base（不触测试集）。"""
    calibration = calibration or CalibrationConfig()
    space = design_space if design_space is not None else load_design_space_12d()
    cells: list[CalibrationCell] = []
    rows: list[CalibrationTaskRow] = []
    cohorts: list[dict[str, Any]] = []
    certificates: list[dict[str, Any]] = []
    n_tasks = calibration.train_tasks + calibration.validation_tasks
    n_seeds = len(calibration.opt_seeds)
    for radius in calibration.radius_grid:
        started = time.perf_counter()
        _config, tasks = build_calibration_cohort(radius, calibration)
        for task_id, certificate in assert_reference_certificates(tasks).items():
            certificates.append({"radius_base": float(radius), "task_id": task_id, **certificate})
        cohorts.append(
            {
                "radius_base": float(radius),
                "task_ids": {
                    split: [task.task_id for task in tasks if task.split == split]
                    for split in CALIBRATION_SPLITS
                },
            }
        )
        cell_rows: list[CalibrationTaskRow] = []
        for opt_seed in calibration.opt_seeds:
            for task in tasks:
                evaluate = make_synthetic_task_evaluator(task, space)
                reference = task.reference()
                result = run_bo_arm(
                    BO_RANDOM_ARM,
                    evaluate,
                    task_id=task.task_id,
                    split=task.split,
                    family=task.family,
                    seed=int(opt_seed),
                    budget=calibration.budget,
                    reference_objective=float(reference["objective_star"]),
                )
                if int(result.to_dict().get("physical_call_count", 0)) != 0:
                    raise FeasibleV2Error("校准 evaluator 报告了非零 physical_call_count")
                cell_rows.append(_calibration_row(radius, opt_seed, task, result))
        rows.extend(cell_rows)
        success_rates = []
        hit_rates = []
        for opt_seed in calibration.opt_seeds:
            success, hit = _seed_rates(cell_rows, int(opt_seed), n_tasks, calibration.budget)
            success_rates.append(success)
            hit_rates.append(hit)
        pooled_success, pooled_hit = _pooled_train_rates(
            cell_rows, calibration.train_tasks, n_seeds, calibration.budget
        )
        validation_rates = []
        for opt_seed in calibration.opt_seeds:
            selected = [
                row
                for row in cell_rows
                if row.opt_seed == int(opt_seed) and row.split == "meta_validation"
            ]
            if len(selected) != calibration.validation_tasks:
                raise FeasibleV2Error("meta_validation 行数不符")
            validation_rates.append(
                sum(1 for row in selected if row.success) / calibration.validation_tasks
            )
        ellipsoid = [
            analytic_ellipsoid_fraction(float(radius), task.params["w"]) for task in tasks
        ]
        volume = feasible_volume_fraction_mc(
            tasks,
            samples=calibration.empirical_samples,
            seed=tf.derive_seed("calibration", "feasible_volume", float(radius)),
        )
        all_seeds_in_acceptance = all(
            ACCEPTANCE_SUCCESS_LOW <= rate <= ACCEPTANCE_SUCCESS_HIGH for rate in success_rates
        )
        cell = CalibrationCell(
            radius_base=float(radius),
            success_rate_by_seed=tuple(success_rates),
            feasible_hit_rate_by_seed=tuple(hit_rates),
            success_rate_median=float(np.median(success_rates)),
            feasible_hit_rate_median=float(np.median(hit_rates)),
            pooled_success_train=float(pooled_success),
            pooled_hit_rate_train=float(pooled_hit),
            validation_success_rate_median=float(np.median(validation_rates)),
            all_seeds_in_acceptance=bool(all_seeds_in_acceptance),
            analytic_sphere_fraction=analytic_sphere_fraction(float(radius)),
            analytic_ellipsoid_fraction_median=float(np.median(ellipsoid)),
            feasible_volume_fraction=float(volume),
            n_tasks=n_tasks,
            budget=calibration.budget,
            evaluations=int(len(cell_rows)),
            n_null=int(sum(row.n_null for row in cell_rows)),
            wall_s=float(time.perf_counter() - started),
        )
        cells.append(cell)
        if progress is not None:
            progress("calibration_cell", {"radius_base": float(radius), **cell.to_dict()})
    eligible = [
        cell
        for cell in cells
        if TARGET_SUCCESS_LOW <= cell.pooled_success_train <= TARGET_SUCCESS_HIGH
    ]
    notes: list[str] = []
    if eligible:
        chosen = min(
            eligible,
            key=lambda cell: (abs(cell.pooled_hit_rate_train - TARGET_HIT_RATE), cell.radius_base),
        )
        selected: float | None = float(chosen.radius_base)
        status = "SELECTED"
        notes.append(
            f"选中 radius_base={selected:.3f}: pooled_success_train="
            f"{chosen.pooled_success_train:.4f}, pooled_hit_train="
            f"{chosen.pooled_hit_rate_train:.4f}, success_by_seed={list(chosen.success_rate_by_seed)}"
        )
    else:
        selected = None
        status = "NO_CELL_IN_TARGET"
        notes.append(
            "没有任何半径格的 meta_train pooled 成功率落在 [0.30,0.70]：按 §10-R1 处理"
            "（不得改测试集；可换 v2a 线性约束变体或保留 INCONCLUSIVE），需要 Lead 裁决。"
        )
    return CalibrationReport(
        schema_version=CALIBRATION_SCHEMA_VERSION,
        created_utc=iso_utc(),
        calibration=calibration,
        cells=tuple(cells),
        rows=tuple(rows),
        cohorts=tuple(cohorts),
        reference_certificates=tuple(certificates),
        selected_radius_base=selected,
        selection_status=status,
        selection_rule=SELECTION_RULE,
        notes=tuple(notes),
    )


CALIBRATION_TASK_COLUMNS = (
    "radius_base",
    "opt_seed",
    "task_id",
    "split",
    "success",
    "feasible_count",
    "first_feasible_eval_index",
    "best_feasible_value",
    "best_objective_raw",
    "min_constraint_violation_sum",
    "n_null",
    "evaluations",
    "wall_s",
)
CALIBRATION_CELL_COLUMNS = (
    "radius_base",
    "success_rate_by_seed",
    "feasible_hit_rate_by_seed",
    "success_rate_median",
    "feasible_hit_rate_median",
    "pooled_success_train",
    "pooled_hit_rate_train",
    "validation_success_rate_median",
    "all_seeds_in_acceptance",
    "analytic_sphere_fraction",
    "analytic_ellipsoid_fraction_median",
    "feasible_volume_fraction",
    "n_tasks",
    "budget",
    "evaluations",
    "n_null",
    "wall_s",
)


def write_calibration_report(directory: str | Path, report: CalibrationReport) -> dict[str, Any]:
    """写出 calibration_report.json / calibration_report.csv / calibration_cells.csv。"""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    json_path = write_json(root / "calibration_report.json", report.to_dict())
    task_path = write_csv(
        root / "calibration_report.csv",
        [row.to_dict() for row in report.rows],
        columns=CALIBRATION_TASK_COLUMNS,
    )
    cell_rows = []
    for cell in report.cells:
        payload = cell.to_dict()
        payload["success_rate_by_seed"] = " ".join(f"{value:.6f}" for value in cell.success_rate_by_seed)
        payload["feasible_hit_rate_by_seed"] = " ".join(
            f"{value:.6f}" for value in cell.feasible_hit_rate_by_seed
        )
        cell_rows.append(payload)
    cell_path = write_csv(root / "calibration_cells.csv", cell_rows, columns=CALIBRATION_CELL_COLUMNS)
    return {
        "json": str(json_path),
        "tasks_csv": str(task_path),
        "cells_csv": str(cell_path),
        "sha256": report.sha256,
    }


# ---------------------------------------------------------------------------
# split manifest（五集合 task_id + split_hash）
# ---------------------------------------------------------------------------
def _split_payload(tasks: Sequence[tf.SyntheticTask], family_config: tf.TaskFamilyConfig) -> dict[str, Any]:
    counts: dict[str, int] = {split: 0 for split in SPLITS}
    task_ids: dict[str, list[str]] = {split: [] for split in SPLITS}
    entries: dict[str, list[dict[str, Any]]] = {split: [] for split in SPLITS}
    for task in tasks:
        if task.split not in counts:
            raise FeasibleV2Error(f"非法 split={task.split!r}（任务 {task.task_id}）")
        counts[task.split] += 1
        task_ids[task.split].append(task.task_id)
        params = dict(task.params)
        if task.is_negative_control:
            summary = {
                "family": task.family,
                "radius": None,
                "objective_star": None,
                "reference_kind": "NEGATIVE_CONTROL",
                "context": {name: float(value) for name, value in task.context.items()},
            }
        else:
            reference = task.reference()
            summary = {
                "family": task.family,
                "radius": float(params.get("r", float("nan"))),
                "objective_star": float(reference["objective_star"]),
                "reference_kind": str(reference.get("reference_kind", "")),
                "context": {name: float(value) for name, value in task.context.items()},
            }
        entries[task.split].append(
            {
                "task_id": task.task_id,
                "seed": int(task.seed),
                "params_digest": digest(params),
                "params_summary": summary,
            }
        )
    for split in SPLITS:
        entries[split].sort(key=lambda item: item["task_id"])
        task_ids[split].sort()
    return {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "family_id": family_config.family_id,
        "family_version": family_config.family_version,
        "radius_base": None if family_config.radius_base is None else float(family_config.radius_base),
        "family_fingerprint": tf.family_fingerprint(family_config),
        "counts": counts,
        "task_ids": task_ids,
        "tasks": entries,
    }


def build_split_manifest(tasks: Sequence[tf.SyntheticTask], *, family_config: tf.TaskFamilyConfig) -> dict[str, Any]:
    """构造 meta_task_split 载荷：五 split 任务清单 + 逐任务参数摘要 + split_hash。"""
    if not tasks:
        raise FeasibleV2Error("build_split_manifest 需要非空任务列表")
    payload = _split_payload(tasks, family_config)
    payload["split_hash"] = digest(payload)
    return payload


def verify_split_manifest(
    manifest: Mapping[str, Any],
    *,
    tasks: Sequence[tf.SyntheticTask] | None = None,
    family_config: tf.TaskFamilyConfig | None = None,
) -> bool:
    """校验 split_hash；若给定 tasks/family_config 则逐字重建并比对（fail-closed）。"""
    if manifest.get("schema_version") != SPLIT_SCHEMA_VERSION:
        raise FeasibleV2Error(f"split manifest schema 不符: {manifest.get('schema_version')!r}")
    body = {key: value for key, value in manifest.items() if key != "split_hash"}
    expected = digest(body)
    if manifest.get("split_hash") != expected:
        raise FeasibleV2Error("split manifest hash 校验失败（split 被修改过）")
    if tasks is not None:
        if family_config is None:
            raise FeasibleV2Error("verify_split_manifest 比对 tasks 时必须给 family_config")
        rebuilt = _split_payload(tasks, family_config)
        if rebuilt != body:
            raise FeasibleV2Error("split manifest 与当前任务/配置不一致（禁止静默改 split）")
    if family_config is not None:
        expected_fingerprint = tf.family_fingerprint(family_config)
        if manifest.get("family_fingerprint") != expected_fingerprint:
            raise FeasibleV2Error("split manifest family_fingerprint 与当前配置不符")
    return True


# ---------------------------------------------------------------------------
# frozen_family.json
# ---------------------------------------------------------------------------
FROZEN_REQUIRED_FIELDS = (
    "family_version",
    "radius_base",
    "reference_solution",
    "gap_definition",
    "calibration_seeds",
    "pooled_success",
    "feasible_volume_fraction",
    "meta_test_tuning_policy",
)


def build_frozen_family(
    family_config: tf.TaskFamilyConfig,
    *,
    split_manifest: Mapping[str, Any],
    calibration_report: CalibrationReport,
    run_id: str,
    git_sha: str,
    code_sha: str | None = None,
    design_space: Any | None = None,
    created_utc: str | None = None,
) -> dict[str, Any]:
    """构造 frozen_family 载荷（含 A13 要求的全部字段），返回带 sha256 的 dict。"""
    if family_config.family_version != "v2":
        raise FeasibleV2Error(f"冻结只允许 v2，实际 family_version={family_config.family_version!r}")
    if calibration_report.selected_radius_base is None:
        raise FeasibleV2Error("校准未选出半径，禁止冻结")
    if family_config.radius_base is None:
        raise FeasibleV2Error("family_config.radius_base 缺失")
    if abs(float(family_config.radius_base) - float(calibration_report.selected_radius_base)) > 1e-12:
        raise FeasibleV2Error(
            "family_config.radius_base 与校准选中半径不一致："
            f"{family_config.radius_base!r} != {calibration_report.selected_radius_base!r}"
        )
    verify_split_manifest(split_manifest, family_config=family_config)
    cell = calibration_report.selected_cell
    if cell is None:
        raise FeasibleV2Error("校准报告缺少 selected_cell")
    space = design_space if design_space is not None else load_design_space_12d()
    design_path = getattr(space, "config_path", None)
    config_sha = file_sha256(design_path) if design_path is not None else None
    fingerprint = tf.family_fingerprint(family_config)
    payload: dict[str, Any] = {
        "schema_version": FROZEN_SCHEMA_VERSION,
        "created_utc": created_utc or iso_utc(),
        "run_id": run_id,
        "git_sha": git_sha,
        "code_sha": code_sha or package_code_sha(),
        "physical_call_count": 0,
        "family_id": family_config.family_id,
        "family_version": family_config.family_version,
        "family_fingerprint": fingerprint,
        "family_config": serialize_family_config(family_config),
        "radius_base": float(family_config.radius_base),
        "radius_mapping": {
            "formula": "r_v2 = clip(radius_base*(1+0.15*z), r_min, r_max), z~N(0,1)",
            "r_min": 0.20,
            "r_max": 1.20,
        },
        "reference_solution": REFERENCE_SOLUTION,
        "gap_definition": GAP_DEFINITION,
        # Lead A13 要求的顶层字段（与 calibration 块内同值，便于审阅/校验）
        "calibration_seeds": list(calibration_report.calibration.opt_seeds),
        "pooled_success": float(cell.pooled_success_train),
        "feasible_volume_fraction": float(cell.feasible_volume_fraction),
        "param_distributions": getattr(tf, "_PARAM_DISTRIBUTIONS", {}),
        "context_coupling": {
            "scale": tf.CONTEXT_COUPLING_SCALE,
            "description": "b_eff = b + scale*((context_1+context_2)/2 - 1)",
            "context_names": list(family_config.context_names),
        },
        "design": {
            "design_set": getattr(space, "design_set", None),
            "design_dim": int(getattr(space, "design_dim", 12)),
            "config_path": str(design_path) if design_path is not None else None,
            "design_config_sha256": config_sha,
        },
        "split": {
            "manifest_sha256": digest(dict(split_manifest)),
            "split_hash": split_manifest["split_hash"],
            "counts": dict(split_manifest["counts"]),
        },
        "calibration": {
            "report_sha256": calibration_report.sha256,
            "selected_radius_base": float(calibration_report.selected_radius_base),
            "selection_status": calibration_report.selection_status,
            "selection_rule": calibration_report.selection_rule,
            "calibration_seeds": list(calibration_report.calibration.opt_seeds),
            "pooled_success": float(cell.pooled_success_train),
            "pooled_hit_rate": float(cell.pooled_hit_rate_train),
            "feasible_volume_fraction": float(cell.feasible_volume_fraction),
            "calibration_budget": int(calibration_report.calibration.budget),
            "calibration_train_tasks": int(calibration_report.calibration.train_tasks),
            "calibration_validation_tasks": int(calibration_report.calibration.validation_tasks),
            "analytic_ellipsoid_fraction_median": float(cell.analytic_ellipsoid_fraction_median),
            "reference_certificates_sha256": digest(list(calibration_report.reference_certificates)),
        },
        "meta_test_tuning_policy": META_TEST_TUNING_POLICY,
        "notes": list(calibration_report.notes),
    }
    payload["sha256"] = digest(payload)
    return payload


def verify_frozen_payload(payload: Mapping[str, Any]) -> bool:
    """校验 frozen_family 必填字段、sha256 与 v2 版本（fail-closed）。"""
    if payload.get("schema_version") != FROZEN_SCHEMA_VERSION:
        raise FeasibleV2Error(f"frozen schema 不符: {payload.get('schema_version')!r}")
    for name in FROZEN_REQUIRED_FIELDS:
        if name not in payload:
            raise FeasibleV2Error(f"frozen_family 缺少必填字段 {name!r}")
    body = {key: value for key, value in payload.items() if key != "sha256"}
    if payload.get("sha256") != digest(body):
        raise FeasibleV2Error("frozen_family sha256 校验失败（冻结后被修改）")
    if payload.get("family_version") != "v2":
        raise FeasibleV2Error(f"frozen family_version 必须为 v2，实际 {payload.get('family_version')!r}")
    if float(payload["radius_base"]) <= 0.0:
        raise FeasibleV2Error("frozen radius_base 必须为正")
    if payload.get("reference_solution") != REFERENCE_SOLUTION:
        raise FeasibleV2Error("frozen reference_solution 必须是 'c'")
    if payload.get("gap_definition") != GAP_DEFINITION:
        raise FeasibleV2Error(f"frozen gap_definition 必须是 {GAP_DEFINITION!r}")
    if not payload.get("meta_test_tuning_policy"):
        raise FeasibleV2Error("frozen 缺少 meta_test 调参禁止声明")
    if not payload.get("calibration_seeds"):
        raise FeasibleV2Error("frozen 缺少 calibration_seeds")
    if not isinstance(payload.get("pooled_success"), (int, float)):
        raise FeasibleV2Error("frozen 缺少数值型 pooled_success")
    if not isinstance(payload.get("feasible_volume_fraction"), (int, float)):
        raise FeasibleV2Error("frozen 缺少数值型 feasible_volume_fraction")
    config = deserialize_family_config(payload["family_config"])
    if tf.family_fingerprint(config) != payload.get("family_fingerprint"):
        raise FeasibleV2Error("frozen family_fingerprint 与 family_config 不符")
    if config.radius_base is None or abs(float(config.radius_base) - float(payload["radius_base"])) > 1e-12:
        raise FeasibleV2Error("frozen radius_base 与 family_config.radius_base 不符")
    return True


def frozen_to_config(payload: Mapping[str, Any]) -> tf.TaskFamilyConfig:
    """从 frozen payload 还原 v2 family 配置。"""
    verify_frozen_payload(payload)
    return deserialize_family_config(payload["family_config"])


def load_frozen_family(path: str | Path) -> dict[str, Any]:
    """读取并校验 frozen_family.json。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    verify_frozen_payload(payload)
    return payload


def write_frozen_family(path: str | Path, payload: Mapping[str, Any]) -> Path:
    """校验后写出 frozen_family.json（不允许写未校验的 payload）。"""
    verify_frozen_payload(payload)
    return write_json(path, dict(payload))


def frozen_split_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """从 frozen payload 取 split 引用信息（用于开测试集前比对）。"""
    verify_frozen_payload(payload)
    return dict(payload["split"])


# ---------------------------------------------------------------------------
# preregistration.json
# ---------------------------------------------------------------------------
def build_preregistration(
    frozen_family: Mapping[str, Any],
    *,
    run_id: str,
    arms: Sequence[str] = M5_ARMS,
    budgets: Sequence[int] = M5_BUDGETS,
    optimization_seeds: Sequence[int] = M5_OPTIMIZATION_SEEDS,
    meta_seeds: Sequence[int] = M5_META_SEEDS,
    primary_endpoints: Sequence[str] = PRIMARY_ENDPOINTS,
    secondary_endpoints: Sequence[str] = SECONDARY_ENDPOINTS,
    statistics: Mapping[str, Any] | None = None,
    null_policy: str = NULL_POLICY,
    stopping_rules: str | Sequence[str] = STOPPING_RULES,
    multiple_comparison: str | None = None,
    created_utc: str | None = None,
) -> dict[str, Any]:
    """构造预注册载荷（写测试集前生成，含 frozen sha256 绑定）。"""
    verify_frozen_payload(frozen_family)
    if not arms:
        raise FeasibleV2Error("preregistration.arms 不能为空")
    budget_values = sorted({int(value) for value in budgets})
    if not budget_values or min(budget_values) < 2:
        raise FeasibleV2Error(f"预算配置非法: {budget_values!r}")
    seeds = [int(value) for value in optimization_seeds]
    if len(seeds) < 10 or len(set(seeds)) != len(seeds):
        raise FeasibleV2Error("正式 M5 要求 >=10 个互异优化 seed")
    payload: dict[str, Any] = {
        "schema_version": PREREGISTRATION_SCHEMA_VERSION,
        "created_utc": created_utc or iso_utc(),
        "run_id": run_id,
        "physical_call_count": 0,
        "frozen_family_sha256": frozen_family["sha256"],
        "family_id": frozen_family["family_id"],
        "family_version": frozen_family["family_version"],
        "family_fingerprint": frozen_family["family_fingerprint"],
        "radius_base": frozen_family["radius_base"],
        "split_hash": frozen_family["split"]["split_hash"],
        "split_counts": dict(frozen_family["split"]["counts"]),
        "arms": list(arms),
        "budgets": budget_values,
        "optimization_seeds": seeds,
        "meta_seeds": [int(value) for value in meta_seeds],
        "primary_endpoints": list(primary_endpoints),
        "secondary_endpoints": list(secondary_endpoints),
        "statistics": dict(statistics or STATISTICS_PLAN),
        "null_policy": null_policy,
        "stopping_rules": normalize_stopping_rules(stopping_rules),
        "multiple_comparison": multiple_comparison or STATISTICS_PLAN["multiple_comparison"],
        "reference_solution": frozen_family["reference_solution"],
        "gap_definition": frozen_family["gap_definition"],
        "meta_test_tuning_policy": frozen_family["meta_test_tuning_policy"],
    }
    payload["sha256"] = digest(payload)
    return payload


def verify_preregistration(prereg: Mapping[str, Any], frozen_family: Mapping[str, Any]) -> bool:
    """校验预注册 hash 与 frozen 绑定；任一不符 → fail-closed（禁止开测试集）。"""
    verify_frozen_payload(frozen_family)
    schema = prereg.get("schema_version")
    if schema not in (PREREGISTRATION_SCHEMA_VERSION, *LEGACY_PREREGISTRATION_SCHEMA_VERSIONS):
        raise FeasibleV2Error(f"prereg schema 不符: {schema!r}")
    validate_preregistration_schema(prereg)
    body = {key: value for key, value in prereg.items() if key != "sha256"}
    if prereg.get("sha256") != digest(body):
        raise FeasibleV2Error("preregistration sha256 校验失败（预注册被修改）")
    if prereg.get("frozen_family_sha256") != frozen_family.get("sha256"):
        raise FeasibleV2Error("preregistration 与 frozen_family 的 sha256 不绑定")
    for name, key in (
        ("family_fingerprint", "family_fingerprint"),
        ("radius_base", "radius_base"),
        ("family_id", "family_id"),
        ("family_version", "family_version"),
    ):
        left = prereg.get(name)
        right = frozen_family.get(key)
        if left != right:
            raise FeasibleV2Error(f"preregistration.{name} 与 frozen 不符: {left!r} != {right!r}")
    if prereg.get("split_hash") != frozen_family["split"]["split_hash"]:
        raise FeasibleV2Error("preregistration.split_hash 与 frozen 不符")
    if prereg.get("meta_test_tuning_policy") != frozen_family.get("meta_test_tuning_policy"):
        raise FeasibleV2Error("preregistration 缺少一致的 meta_test 调参禁止声明")
    return True


def write_preregistration(path: str | Path, prereg: Mapping[str, Any], frozen_family: Mapping[str, Any]) -> Path:
    """校验后写出 preregistration.json。"""
    verify_preregistration(prereg, frozen_family)
    return write_json(path, dict(prereg))


def load_preregistration(path: str | Path) -> dict[str, Any]:
    """读取 preregistration.json（hash 校验在 verify_preregistration 中做）。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 开测试集前的统一门禁
# ---------------------------------------------------------------------------
def assert_holdout_unlocked(
    *,
    frozen_family: Mapping[str, Any],
    preregistration: Mapping[str, Any],
    split_manifest: Mapping[str, Any],
    calibration_report: CalibrationReport,
) -> dict[str, Any]:
    """holdout 阶段入口门禁：frozen/prereg/split/校准 四方一致才允许构造 test/ood。"""
    verify_frozen_payload(frozen_family)
    verify_preregistration(preregistration, frozen_family)
    verify_split_manifest(split_manifest, family_config=frozen_to_config(frozen_family))
    if calibration_report.selected_radius_base is None:
        raise FeasibleV2Error("校准未选出半径，禁止开测试集")
    if abs(float(frozen_family["radius_base"]) - float(calibration_report.selected_radius_base)) > 1e-12:
        raise FeasibleV2Error("frozen radius 与校准选中半径不符")
    if frozen_family["split"]["split_hash"] != split_manifest.get("split_hash"):
        raise FeasibleV2Error("frozen split_hash 与当前 split manifest 不符")
    if calibration_report.sha256 != frozen_family["calibration"]["report_sha256"]:
        raise FeasibleV2Error("frozen 校准报告 sha256 与当前报告不符")
    return {
        "status": "UNLOCKED",
        "frozen_family_sha256": frozen_family["sha256"],
        "preregistration_sha256": preregistration["sha256"],
        "split_hash": split_manifest["split_hash"],
        "radius_base": float(frozen_family["radius_base"]),
    }


__all__ = [
    "CALIBRATION_STAGE",
    "HOLDOUT_STAGE",
    "STAGES",
    "RADIUS_GRID",
    "CALIBRATION_OPT_SEEDS",
    "CALIBRATION_BUDGET",
    "CALIBRATION_SPLITS",
    "CALIBRATION_SELECTION_SPLIT",
    "SEALED_SPLITS",
    "BO_RANDOM_ARM",
    "TARGET_SUCCESS_LOW",
    "TARGET_SUCCESS_HIGH",
    "ACCEPTANCE_SUCCESS_LOW",
    "ACCEPTANCE_SUCCESS_HIGH",
    "REFERENCE_SOLUTION",
    "GAP_DEFINITION",
    "META_TEST_TUNING_POLICY",
    "M5_ARMS",
    "M5_BUDGETS",
    "M5_OPTIMIZATION_SEEDS",
    "M5_META_SEEDS",
    "PRIMARY_ENDPOINTS",
    "SECONDARY_ENDPOINTS",
    "NULL_POLICY",
    "STATISTICS_PLAN",
    "STOPPING_RULES",
    "NON_CLAIMS",
    "FROZEN_SCHEMA_VERSION",
    "SPLIT_SCHEMA_VERSION",
    "PREREGISTRATION_SCHEMA_VERSION",
    "LEGACY_PREREGISTRATION_SCHEMA_VERSIONS",
    "STOPPING_RULE_MIN_LENGTH",
    "normalize_stopping_rules",
    "validate_preregistration_schema",
    "CALIBRATION_SCHEMA_VERSION",
    "FeasibleV2Error",
    "canonical_json",
    "digest",
    "file_sha256",
    "package_code_sha",
    "serialize_family_config",
    "deserialize_family_config",
    "split_order",
    "CalibrationConfig",
    "calibration_family_config",
    "assert_calibration_only",
    "build_calibration_cohort",
    "assert_reference_certificates",
    "analytic_sphere_fraction",
    "analytic_ellipsoid_fraction",
    "feasible_volume_fraction_mc",
    "empirical_feasible_fraction",
    "CalibrationTaskRow",
    "CalibrationCell",
    "CalibrationReport",
    "calibrate_radius_base",
    "write_calibration_report",
    "build_split_manifest",
    "verify_split_manifest",
    "build_frozen_family",
    "verify_frozen_payload",
    "frozen_to_config",
    "load_frozen_family",
    "write_frozen_family",
    "build_preregistration",
    "verify_preregistration",
    "write_preregistration",
    "load_preregistration",
    "assert_holdout_unlocked",
]
