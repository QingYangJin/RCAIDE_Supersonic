# -*- coding: utf-8 -*-
"""P4 路线A S1：任务族 v3 生成、冻结、隔离与预注册（fail-closed，零求解）。

依据：Issue #7（D-P4-003）S0/S1；docs/planning/p4_route_a_s0_2_decisions_20261105.md
（D-S0-2-01..07）；docs/planning/p4_route_a_s1_family_v3_design_20261105.md rev2。

本模块只构造**合成解析**任务与元数据（physical_call_count 恒为 0），
不调用 RCAIDE Mission / VSPAERO / SU2 / Gmsh，不运行任何真实优化。

硬约束（全部程序化 fail-closed）：
1. 包层 family_version=p4ra-family-v4（legacy p4ra-family-v3 只读兼容）；数学任务族仍是 p4ra-family-v3；formula_version=p4-task-family-v3；
2. task_id 唯一格式 ^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$，五 split 60/20/20/10/10；
3. 与旧 M2/M5/M6 任务清单 task_id/task_fingerprint 零交集（非空即抛错）；
4. family_fingerprint / split_hash / frozen sha256 / prereg sha256 全部可重算；
5. 双 digest：canonical（canonical JSON）与 raw（写盘实际 UTF-8 字节）。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from . import task_family as tf
from .data_contract import SPLITS

__all__ = [
    "FamilyV3Error",
    "FAMILY_ID",
    "FAMILY_VERSION",
    "LEGACY_FAMILY_VERSIONS",
    "TASK_FAMILY_VERSION",
    "FORMULA_VERSION",
    "FAMILY_SEED",
    "HOLDOUT_SEED",
    "HOLDOUT_SPLITS",
    "HOLDOUT_TASK_COUNT",
    "package_family_fingerprint",
    "TASK_ID_PREFIX",
    "TASK_ID_PATTERN",
    "SPLIT_ORDER",
    "SPLIT_CODES",
    "SPLIT_COUNTS",
    "TOTAL_TASKS",
    "TASK_SCHEMA_VERSION",
    "SPLIT_SCHEMA_VERSION",
    "FROZEN_SCHEMA_VERSION",
    "PREREGISTRATION_SCHEMA_VERSION",
    "ISOLATION_SCHEMA_VERSION",
    "DIGEST_MANIFEST_SCHEMA_VERSION",
    "PRIMARY_ENDPOINTS",
    "FORBIDDEN_ENDPOINT_ALIASES",
    "SECONDARY_ENDPOINTS",
    "SECONDARY_METRICS",
    "ENDPOINT_ROW_KEYS",
    "FAILURE_RULES",
    "MULTIPLE_COMPARISON",
    "ANALYSIS_PLAN",
    "ANALYSIS_PLAN_DIGEST",
    "PREREG_REQUIRED_FIELDS",
    "assert_endpoint_row_coverage",
    "compute_prereg_digest",
    "REFERENCE_SOLUTION",
    "GAP_DEFINITION",
    "NULL_POLICY",
    "STATISTICS_PLAN",
    "STOPPING_RULES",
    "META_TEST_TUNING_POLICY",
    "ARM_IDS",
    "BUDGETS",
    "K_VALUES",
    "INITIAL_DESIGN_COUNT",
    "canonical_json",
    "digest",
    "file_sha256",
    "package_code_sha",
    "build_v3_family_config",
    "assert_family_v3_identity",
    "validate_task_id",
    "parse_task_id",
    "assign_v3_task_ids",
    "task_fingerprint",
    "build_task_records",
    "build_split_manifest_v3",
    "verify_split_manifest_v3",
    "collect_legacy_task_ids",
    "assert_zero_intersection",
    "build_isolation_report",
    "verify_isolation_report",
    "normalize_stopping_rules",
    "normalize_endpoints",
    "build_frozen_family_v3",
    "verify_frozen_family_v3",
    "frozen_to_v3_config",
    "build_preregistration_v3",
    "verify_preregistration_v3",
    "write_json",
    "write_json_artifact",
    "build_digest_manifest",
    "build_freeze_bundle",
]

FAMILY_ID = tf.V3_FAMILY_ID
# 包/记录层版本（task-229 R-V4-01）：v4 只重播种 holdout 两类；
# 数学任务族版本仍是 p4ra-family-v3（任务参数/fingerprint 不漂移）。
FAMILY_VERSION = "p4ra-family-v4"
LEGACY_FAMILY_VERSIONS = (tf.V3_FAMILY_VERSION,)
TASK_FAMILY_VERSION = tf.V3_FAMILY_VERSION
FORMULA_VERSION = tf.V3_FORMULA_VERSION
FAMILY_SEED = tf.V3_FAMILY_SEED
HOLDOUT_SEED = tf.V4_HOLDOUT_SEED
HOLDOUT_SPLITS = ("meta_test", "meta_test_ood")
HOLDOUT_TASK_COUNT = 30
TASK_ID_PREFIX = tf.V3_TASK_ID_PREFIX
TASK_ID_PATTERN = re.compile(r"^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$")  # 合同 §7 精确字面量

SPLIT_ORDER: tuple[str, ...] = tuple(SPLITS)
SPLIT_CODES = {
    "meta_train": "TR",
    "meta_validation": "VA",
    "meta_test": "TE",
    "meta_test_ood": "OD",
    "negative_control": "NC",
}
SPLIT_COUNTS = {
    "meta_train": 60,
    "meta_validation": 20,
    "meta_test": 20,
    "meta_test_ood": 10,
    "negative_control": 10,
}
TOTAL_TASKS = sum(SPLIT_COUNTS.values())

TASK_SCHEMA_VERSION = "p4ra-task-v1"
SPLIT_SCHEMA_VERSION = "p4ra-split-v3-1"
FROZEN_SCHEMA_VERSION = "p4ra-frozen-v3-1"
PREREGISTRATION_SCHEMA_VERSION = "p4ra-prereg-v1"
ISOLATION_SCHEMA_VERSION = "p4ra-v3-isolation-1"
DIGEST_MANIFEST_SCHEMA_VERSION = "p4ra-digest-manifest-1"

# D-S0-2-02：端点规范 ID 唯一；first_feasible_evaluation_index 是禁用别名，不得静默映射。
PRIMARY_ENDPOINTS = (
    "best_feasible_value",
    "gap_to_reference",
    "first_feasible_eval_index",
    "feasible_hit_rate",
)
FORBIDDEN_ENDPOINT_ALIASES = ("first_feasible_evaluation_index",)
SECONDARY_ENDPOINTS = (
    "best_objective_raw",
    "min_constraint_violation_sum",
    "first_feasible_in_support",
    "first_feasible_after_support_index",
    "feasible_hit_rate_non_support",
    "true_evals_used",
    "cache_hits",
    "n_failed_evals",
    "wall_s",
)
# 合同 §7：secondary_metrics 为 [string]；与 SECONDARY_ENDPOINTS 同源但单独冻结，供统计分析脚本引用。
SECONDARY_METRICS = (
    "rmse_objective",
    "mae_objective",
    "feasible_hit_rate",
    "surrogate_fit_time_s",
    "peak_memory_mb",
)
# D-S0-2-02 / R-05：S1 分析 CSV/图表只允许读取这 9 个登记键（4 主端点 + 3 补充 + 2 覆盖统计）。
ENDPOINT_ROW_KEYS = (
    *PRIMARY_ENDPOINTS,
    "first_feasible_in_support",
    "first_feasible_after_support_index",
    "feasible_hit_rate_non_support",
    "n_nonnull",
    "null_rate",
)
FAILURE_RULES = (
    "任一冻结产物 sha256/fingerprint/split_hash 校验失败 -> 立即 fail-closed，不产出主结论。",
    "任一预算/K/CLONE 公平性校验失败 -> 该 run 作废，不得进入聚合。",
    "主端点 null 率 >70% -> 判 INCONCLUSIVE，不插补、不转 0。",
    "发现 meta_test/meta_test_ood 信息参与调参/选臂/选端点 -> 该阶段结果作废。",
)
MULTIPLE_COMPARISON = {
    "method": "Holm-Bonferroni",
    "family": "同 K 内臂对 x 预算 x 主端点（4 主端点）",
    "alpha": 0.05,
}
REFERENCE_SOLUTION = "c"
GAP_DEFINITION = "f(u_best)-f(u*)"

# D-S0-2-04：空值不插补、不计 0；主端点 null 率 >70% 判 INCONCLUSIVE。
NULL_POLICY = (
    "不可行/失败评价保留 objective=null 且计入预算；空值不插补、不转 0；"
    "主端点 null 率 >70% 时标 INCONCLUSIVE 并给出原因，不补假曲线。"
)
STATISTICS_PLAN = {
    "unit": "task",
    "seed_aggregation": "单 run -> (task,meta_seed) 内对 10 个 optimization seed 取均值；meta_seed 等权",
    "paired_differences": "(task, meta_seed, budget, K) 配对差；任务为一级统计单位",
    "main_population": "仅 meta_test 20 个任务进入主统计；meta_validation 只调参；OOD 单独描述层",
    "bootstrap_samples": 10000,
    "confidence": 0.95,
    "test": "wilcoxon_signed_rank",
    "effect_size": "paired_cohen_d / rank_biserial",
    "multiplicity": "Holm-Bonferroni（同 K 内臂对 x 预算 x 主端点）",
    "thresholds": {
        "best_feasible_value_relative_improvement": 0.01,
        "gap_to_reference_relative_improvement": 0.01,
        "feasible_hit_rate_absolute_difference": 0.05,
        "first_feasible_eval_index_improvement": "ceil(0.05*B)（仅同 K 内比较）",
    },
    "null_handling": NULL_POLICY,
}
# 合同 §7 analysis_plan_digest 绑定的 S1 分析计划（无绝对路径、确定性 canonical 载荷）。
ANALYSIS_PLAN = {
    "schema_version": "p4ra-analysis-plan-1",
    "endpoint_row_keys": list(ENDPOINT_ROW_KEYS),
    "primary_endpoints": list(PRIMARY_ENDPOINTS),
    "secondary_metrics": list(SECONDARY_METRICS),
    "statistics": dict(STATISTICS_PLAN),
    "null_policy": NULL_POLICY,
    "multiple_comparison": dict(MULTIPLE_COMPARISON),
    "main_population": "仅 meta_test 20 个任务进入主统计",
    "seed_aggregation": "单 run -> (task,meta_seed) 内对 optimization seed 取均值；meta_seed 等权；任务为一级统计单位",
    "bootstrap_seed": FAMILY_SEED,
    "csv_columns": list(ENDPOINT_ROW_KEYS),
    "fail_closed_rules": list(FAILURE_RULES),
    "analysis_script_requirement": "S1 分析脚本必须校验 ENDPOINT_ROW_KEYS 与 analysis_plan_digest 后才能读 CSV。",
}
STOPPING_RULES = (
    "阶段门禁：只有 frozen_family.json + meta_task_split.json + preregistration.json 三方 sha256/fingerprint/split_hash 全部校验通过后，才允许一次性构造并评估 meta_test/meta_test_ood。",
    "数据边界：禁止用 meta_test/meta_test_ood 的任何信息调参、选半径、选臂或改终点；meta_validation 仅用于调参与校准旁证。",
    "统计边界：主统计分母仅为 meta_test 的 20 个任务；负控制只做负控结论，不进主终点。",
    "失败即停：任何 hash/字段/预算校验失败立刻 fail-closed，不得用默认值静默填充。",
)
STOPPING_RULE_MIN_LENGTH = 2
META_TEST_TUNING_POLICY = (
    "禁止使用 meta_test/meta_test_ood 的任何信息（成功率/误差/gap/秩）调参、选半径、"
    "选臂或选终点；测试集只在 frozen_family + split_manifest + preregistration 的 "
    "sha256/fingerprint/split_hash 校验通过后一次性构造并评估一次。"
)

# S1 五臂（D-S0-2-03）与预算常量
ARM_IDS = (
    "RAND-BO",
    "PRETRAIN-KSHOT-BO",
    "FOMAML-ZERO-BO",
    "FOMAML-KSHOT-BO",
    "DE",
)
BUDGETS = (64, 128)
K_VALUES = (0, 1, 3, 5)
INITIAL_DESIGN_COUNT = 8


class FamilyV3Error(ValueError):
    """v3 任务族构造/冻结/隔离/预注册协议违规（信息直接落盘，不伪造数据）。"""


# ---------------------------------------------------------------------------
# 哈希与序列化（canonical 规则与 M5 feasible_v2 一致：键排序、无空白、UTF-8、禁 NaN）
# ---------------------------------------------------------------------------
def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        if not math.isfinite(number):
            raise FamilyV3Error("canonical JSON 禁止 NaN/Infinity")
        return number
    raise TypeError(f"不可序列化为 JSON 的对象: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


ANALYSIS_PLAN_DIGEST = digest(ANALYSIS_PLAN)


def file_sha256(path: str | Path) -> str:
    """文件实际 UTF-8 字节 sha256（raw digest，不做 CRLF 归一化）。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package_code_sha(directory: str | Path | None = None) -> str:
    root = Path(directory) if directory is not None else Path(__file__).resolve().parent
    entries = [
        {"name": path.name, "sha256": file_sha256(path)}
        for path in sorted(root.glob("*.py"), key=lambda item: item.name)
    ]
    return digest(entries)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    """确定性 JSON 写盘：pretty 缩进 + 键排序 + LF + 末尾换行（raw digest 可复现）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
    target.write_text(text + "\n", encoding="utf-8", newline="\n")
    return target


def write_json_artifact(path: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """写盘并返回 canonical + raw 双 digest（A5 m03/m04：逻辑文件名、无绝对路径、空 sha 不落 null）。"""
    target = write_json(path, payload)
    body = {key: value for key, value in payload.items() if key != "sha256"}
    artifact: dict[str, Any] = {
        "path": target.name,
        "bytes": target.stat().st_size,
        "canonical_sha256": digest(body),
        "raw_sha256": file_sha256(target),
    }
    stored = payload.get("sha256")
    if isinstance(stored, str):
        artifact["stored_sha256"] = stored
    return artifact


# ---------------------------------------------------------------------------
# v3 配置与恒等式
# ---------------------------------------------------------------------------
def _validate_holdout_seed(value: Any) -> int:
    if type(value) is not int or value < 0 or value > 2**31 - 1:
        raise FamilyV3Error(f"holdout_seed 必须是 [0, 2^31-1] 内的整数，实际 {value!r}")
    return int(value)


def package_family_fingerprint(
    config: tf.TaskFamilyConfig, *, holdout_seed: int = HOLDOUT_SEED
) -> str:
    """v4 包级 family_fingerprint（R-V4-01）：任务族指纹 + 包版本 + holdout 重播种声明。

    数学任务族指纹 tf.family_fingerprint(config) 保持 v3 逐位不变（train/val/NC 不漂移）；
    包级指纹单独覆盖 holdout seed/splits/count 与包版本，用于 v4 冻结包/预注册绑定。
    """
    if not isinstance(config, tf.TaskFamilyConfig):
        raise FamilyV3Error("package_family_fingerprint 需要 TaskFamilyConfig")
    seed = _validate_holdout_seed(holdout_seed)
    payload = {
        "schema_version": "p4ra-family-fingerprint-v4-1",
        "task_family_fingerprint": tf.family_fingerprint(config),
        "family_id": config.family_id,
        "family_version": FAMILY_VERSION,
        "task_family_version": TASK_FAMILY_VERSION,
        "formula_version": FORMULA_VERSION,
        "holdout_seed": seed,
        "holdout_splits": list(HOLDOUT_SPLITS),
        "holdout_task_count": HOLDOUT_TASK_COUNT,
    }
    return digest(payload)


def build_v3_family_config(**overrides: Any) -> tf.TaskFamilyConfig:
    """构造 v3 任务族配置（默认 60/20/20/10/10、seed=20261105、radius_base=0.32）。"""
    base: dict[str, Any] = dict(
        family_id=FAMILY_ID,
        design_dim=tf.DESIGN_DIM,
        context_names=tf.CONTEXT_NAMES,
        seed=FAMILY_SEED,
        train_tasks=SPLIT_COUNTS["meta_train"],
        validation_tasks=SPLIT_COUNTS["meta_validation"],
        test_tasks=SPLIT_COUNTS["meta_test"],
        ood_tasks=SPLIT_COUNTS["meta_test_ood"],
        negative_control_tasks=SPLIT_COUNTS["negative_control"],
        designs_per_task=192,
        support_pool_size=128,
        query_size=64,
        reference_tolerance=tf.REFERENCE_ABS_TOL,
        family_version=TASK_FAMILY_VERSION,
        radius_base=tf.V3_RADIUS_BASE_DEFAULT,
    )
    base.update(overrides)
    return tf.TaskFamilyConfig(**base)


def assert_family_v3_identity(config: tf.TaskFamilyConfig) -> None:
    """fail-closed：校验配置确实对应冻结的 v3 身份与五 split 规模。"""
    if not isinstance(config, tf.TaskFamilyConfig):
        raise FamilyV3Error("assert_family_v3_identity 需要 TaskFamilyConfig")
    if config.family_id != FAMILY_ID:
        raise FamilyV3Error(f"family_id 必须是 {FAMILY_ID!r}，实际 {config.family_id!r}")
    if config.family_version != TASK_FAMILY_VERSION:
        raise FamilyV3Error(
            f"数学任务族 family_version 必须是 {TASK_FAMILY_VERSION!r}，实际 {config.family_version!r}"
        )
    if int(config.seed) != FAMILY_SEED:
        raise FamilyV3Error(f"family seed 必须是 {FAMILY_SEED}，实际 {config.seed!r}")
    if config.radius_base is None:
        raise FamilyV3Error("v3 配置必须提供 radius_base")
    if not (tf.V3_RADIUS_MIN <= float(config.radius_base) <= tf.V3_RADIUS_MAX):
        raise FamilyV3Error(
            f"radius_base 必须位于 [{tf.V3_RADIUS_MIN}, {tf.V3_RADIUS_MAX}]，实际 {config.radius_base!r}"
        )
    for split in SPLIT_ORDER:
        field = {
            "meta_train": "train_tasks",
            "meta_validation": "validation_tasks",
            "meta_test": "test_tasks",
            "meta_test_ood": "ood_tasks",
            "negative_control": "negative_control_tasks",
        }[split]
        actual = int(getattr(config, field))
        expected = SPLIT_COUNTS[split]
        if actual != expected:
            raise FamilyV3Error(f"{split} 任务数必须是 {expected}，实际 {actual}")
    if config.designs_per_task != config.support_pool_size + config.query_size:
        raise FamilyV3Error("designs_per_task 必须等于 support_pool_size + query_size")


# ---------------------------------------------------------------------------
# task_id：^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$
# ---------------------------------------------------------------------------
def validate_task_id(task_id: str) -> None:
    if not isinstance(task_id, str):
        raise FamilyV3Error(f"task_id 必须是 str，实际 {type(task_id).__name__}")
    if not TASK_ID_PATTERN.match(task_id):
        raise FamilyV3Error(
            f"task_id 格式非法: {task_id!r}（必须匹配 {TASK_ID_PATTERN.pattern}）"
        )


def parse_task_id(task_id: str) -> tuple[str, int]:
    validate_task_id(task_id)
    match = TASK_ID_PATTERN.match(task_id)
    assert match is not None
    code = match.group(1)
    index = int(task_id[-3:])
    split = {value: key for key, value in SPLIT_CODES.items()}[code]
    return split, index


def assign_v3_task_ids(tasks: Sequence[tf.SyntheticTask]) -> list[tf.SyntheticTask]:
    """按生成顺序为每个 split 分配 TR/VA/TE/OD/NC 序号（000 起，逐 split 递增）。

    返回与输入同序的新任务列表；不修改输入对象。fail-closed：重复 split 序号、
    未知 split、index 溢出 999、task_id 重复或格式不符均抛 FamilyV3Error。
    """
    counters: dict[str, int] = {split: 0 for split in SPLIT_ORDER}
    assigned: list[tf.SyntheticTask] = []
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, tf.SyntheticTask):
            raise FamilyV3Error("assign_v3_task_ids 需要 SyntheticTask 序列")
        if task.split not in SPLIT_CODES:
            raise FamilyV3Error(f"未知 split: {task.split!r}（任务 {task.task_id}）")
        index = counters[task.split]
        if index > 999:
            raise FamilyV3Error(f"split {task.split} 任务数超过 999，无法生成 3 位序号")
        task_id = f"{TASK_ID_PREFIX}{SPLIT_CODES[task.split]}-{index:03d}"
        validate_task_id(task_id)
        if task_id in seen:
            raise FamilyV3Error(f"task_id 重复: {task_id}")
        seen.add(task_id)
        counters[task.split] += 1
        assigned.append(replace(task, task_id=task_id))
    return assigned


def task_fingerprint(task: tf.SyntheticTask) -> str:
    """任务内容指纹：覆盖 family/formula/params/context/constraint_slots，不含 split/index/seed。"""
    if not isinstance(task, tf.SyntheticTask):
        raise FamilyV3Error("task_fingerprint 需要 SyntheticTask")
    payload = {
        "family_id": task.family,
        "family_version": TASK_FAMILY_VERSION,
        "formula_version": FORMULA_VERSION,
        "design_dim": tf.DESIGN_DIM,
        "params": dict(task.params),
        "context": {name: float(value) for name, value in task.context.items()},
        "constraint_slots": list(task.enabled_constraint_names),
    }
    return digest(payload)


def build_task_records(tasks: Sequence[tf.SyntheticTask]) -> list[dict[str, Any]]:
    """tasks.json 记录（保持生成顺序）：schema + task_id + task_fingerprint + 参数摘要。"""
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_fps: set[str] = set()
    for task in tasks:
        validate_task_id(task.task_id)
        fingerprint = task_fingerprint(task)
        if task.task_id in seen_ids:
            raise FamilyV3Error(f"task_id 重复: {task.task_id}")
        if fingerprint in seen_fps:
            raise FamilyV3Error(f"task_fingerprint 重复: {fingerprint}（任务 {task.task_id}）")
        seen_ids.add(task.task_id)
        seen_fps.add(fingerprint)
        records.append(
            {
                "schema_version": TASK_SCHEMA_VERSION,
                "task_id": task.task_id,
                "task_fingerprint": fingerprint,
                "split": task.split,
                "family": task.family,
                "family_version": TASK_FAMILY_VERSION,
                "formula_version": FORMULA_VERSION,
                "design_dim": tf.DESIGN_DIM,
                "context": {name: float(value) for name, value in task.context.items()},
                "params": dict(task.params),
                "params_digest": digest(dict(task.params)),
                "seed": int(task.seed),
                "constraint_slots": list(task.enabled_constraint_names),
                "is_negative_control": bool(task.is_negative_control),
            }
        )
    return records


# ---------------------------------------------------------------------------
# split manifest / split_hash
# ---------------------------------------------------------------------------
def _split_hash_payload(split_task_ids: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """D-S0-2-01：split_hash 覆盖五个 split 的全部 task_id 有序列表（按 split 顺序）。"""
    ordered: dict[str, list[str]] = {}
    for split in SPLIT_ORDER:
        ids = [str(value) for value in split_task_ids.get(split, ())]
        ordered[split] = ids
    return {"split_order": list(SPLIT_ORDER), "task_ids": ordered}


def _task_summary(task: tf.SyntheticTask) -> dict[str, Any]:
    if task.is_negative_control:
        return {
            "family": task.family,
            "radius": None,
            "objective_star": None,
            "reference_kind": "NEGATIVE_CONTROL",
            "context": {name: float(value) for name, value in task.context.items()},
        }
    reference = task.reference()
    return {
        "family": task.family,
        "radius": float(task.params.get("r")),
        "objective_star": float(reference["objective_star"]),
        "reference_kind": str(reference.get("reference_kind", "")),
        "context": {name: float(value) for name, value in task.context.items()},
    }


def build_split_manifest_v3(
    tasks: Sequence[tf.SyntheticTask],
    *,
    family_config: tf.TaskFamilyConfig,
    holdout_seed: int | None = None,
) -> dict[str, Any]:
    """构造 meta_task_split.json 载荷：五 split 有序 task_id + 逐任务摘要 + split_hash。

    holdout_seed=None 为 legacy v3 载荷（逐位兼容旧包）；给定 holdout_seed 时为 v4 包
    （包层 family_version=p4ra-family-v4 + holdout_seed/splits/count + 包级指纹）。
    """
    if not tasks:
        raise FamilyV3Error("build_split_manifest_v3 需要非空任务列表")
    counts: dict[str, int] = {split: 0 for split in SPLIT_ORDER}
    task_ids: dict[str, list[str]] = {split: [] for split in SPLIT_ORDER}
    entries: dict[str, list[dict[str, Any]]] = {split: [] for split in SPLIT_ORDER}
    for task in tasks:
        if task.split not in SPLIT_CODES:
            raise FamilyV3Error(f"非法 split={task.split!r}（任务 {task.task_id}）")
        validate_task_id(task.task_id)
        counts[task.split] += 1
        task_ids[task.split].append(task.task_id)
        entries[task.split].append(
            {
                "task_id": task.task_id,
                "task_fingerprint": task_fingerprint(task),
                "seed": int(task.seed),
                "params_digest": digest(dict(task.params)),
                "params_summary": _task_summary(task),
            }
        )
    if holdout_seed is None:
        payload_family_version = TASK_FAMILY_VERSION
        family_fingerprint_value = tf.family_fingerprint(family_config)
        holdout_extra: dict[str, Any] = {}
    else:
        seed = _validate_holdout_seed(holdout_seed)
        payload_family_version = FAMILY_VERSION
        family_fingerprint_value = package_family_fingerprint(
            family_config, holdout_seed=seed
        )
        holdout_extra = {
            "task_family_version": TASK_FAMILY_VERSION,
            "holdout_seed": seed,
            "holdout_splits": list(HOLDOUT_SPLITS),
            "holdout_task_count": HOLDOUT_TASK_COUNT,
        }
    payload: dict[str, Any] = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "family_id": family_config.family_id,
        "family_version": payload_family_version,
        "family_seed": int(family_config.seed),
        "radius_base": float(family_config.radius_base),
        "family_fingerprint": family_fingerprint_value,
        "task_id_pattern": TASK_ID_PATTERN.pattern,
        "split_order": list(SPLIT_ORDER),
        "counts": counts,
        "total_tasks": int(sum(counts.values())),
        "task_ids": task_ids,
        "tasks": entries,
    }
    payload.update(holdout_extra)
    payload["split_hash"] = digest(_split_hash_payload(task_ids))
    return payload


def verify_split_manifest_v3(
    manifest: Mapping[str, Any],
    *,
    tasks: Sequence[tf.SyntheticTask] | None = None,
    family_config: tf.TaskFamilyConfig | None = None,
) -> bool:
    """校验 split manifest schema/split_hash；给定 tasks/config 时逐字重建并比对。"""
    if manifest.get("schema_version") != SPLIT_SCHEMA_VERSION:
        raise FamilyV3Error(f"split manifest schema 不符: {manifest.get('schema_version')!r}")
    task_ids = manifest.get("task_ids")
    if not isinstance(task_ids, Mapping):
        raise FamilyV3Error("split manifest 缺少 task_ids 映射")
    expected = digest(_split_hash_payload(task_ids))
    if manifest.get("split_hash") != expected:
        raise FamilyV3Error("split_hash 校验失败（split 被修改过）")
    counts = manifest.get("counts")
    if not isinstance(counts, Mapping):
        raise FamilyV3Error("split manifest 缺少 counts")
    for split in SPLIT_ORDER:
        if int(counts.get(split, -1)) != len(task_ids.get(split, ())):
            raise FamilyV3Error(f"split manifest counts 与 task_ids 不一致: {split}")
    manifest_version = manifest.get("family_version")
    if manifest_version == FAMILY_VERSION:
        if manifest.get("task_family_version") != TASK_FAMILY_VERSION:
            raise FamilyV3Error("v4 split manifest 缺少/错误 task_family_version")
        if list(manifest.get("holdout_splits", ())) != list(HOLDOUT_SPLITS):
            raise FamilyV3Error(f"v4 split manifest holdout_splits 必须为 {list(HOLDOUT_SPLITS)}")
        if int(manifest.get("holdout_task_count", -1)) != HOLDOUT_TASK_COUNT:
            raise FamilyV3Error(f"v4 split manifest holdout_task_count 必须为 {HOLDOUT_TASK_COUNT}")
        manifest_holdout_seed = _validate_holdout_seed(manifest.get("holdout_seed"))
        if manifest_holdout_seed != HOLDOUT_SEED:
            raise FamilyV3Error(
                f"v4 split manifest holdout_seed 必须为冻结值 {HOLDOUT_SEED}，实际 {manifest_holdout_seed}"
            )
    elif manifest_version in LEGACY_FAMILY_VERSIONS:
        if "task_family_version" in manifest:
            raise FamilyV3Error("legacy v3 split manifest 不得携带 task_family_version 包层字段")
        manifest_holdout_seed = None
    else:
        raise FamilyV3Error(f"split manifest family_version 非法: {manifest_version!r}")
    if family_config is not None:
        if family_config.family_version != TASK_FAMILY_VERSION:
            raise FamilyV3Error("split manifest 校验要求数学任务族 family_version=p4ra-family-v3")
        expected_fingerprint = (
            tf.family_fingerprint(family_config)
            if manifest_holdout_seed is None
            else package_family_fingerprint(family_config, holdout_seed=manifest_holdout_seed)
        )
        if manifest.get("family_fingerprint") != expected_fingerprint:
            raise FamilyV3Error("split manifest family_fingerprint 与当前配置不符")
        if manifest.get("family_id") != family_config.family_id:
            raise FamilyV3Error("split manifest family_id 与当前配置不符")
    if tasks is not None:
        if family_config is None:
            raise FamilyV3Error("verify_split_manifest_v3 比对 tasks 时必须给 family_config")
        rebuilt = build_split_manifest_v3(
            tasks, family_config=family_config, holdout_seed=manifest_holdout_seed
        )
        if rebuilt != dict(manifest):
            raise FamilyV3Error("split manifest 与当前任务/配置不一致（禁止静默改 split）")
    return True


# ---------------------------------------------------------------------------
# 与旧 M2/M5/M6 的 task_id / task_fingerprint 零交集
# ---------------------------------------------------------------------------
def _walk_collect(node: Any, ids: set[str], fingerprints: set[str]) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "task_id" and isinstance(value, str):
                ids.add(value)
            elif key == "task_fingerprint" and isinstance(value, str):
                fingerprints.add(value)
            elif key == "task_ids":
                if isinstance(value, Mapping):
                    for item in value.values():
                        if isinstance(item, (list, tuple)):
                            ids.update(str(entry) for entry in item)
                elif isinstance(value, (list, tuple)):
                    ids.update(str(entry) for entry in value)
            else:
                _walk_collect(value, ids, fingerprints)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _walk_collect(item, ids, fingerprints)


def collect_legacy_task_ids(
    paths: Sequence[str | Path], *, require_exists: bool = True
) -> dict[str, Any]:
    """只读解析旧 run JSON，递归收集 task_id 与 task_fingerprint（不修改任何文件）。"""
    ids: set[str] = set()
    fingerprints: set[str] = set()
    sources: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            if require_exists:
                raise FamilyV3Error(f"旧族清单文件不存在: {path}")
            sources.append({"path": str(path), "exists": False})
            continue
        before_ids, before_fps = len(ids), len(fingerprints)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FamilyV3Error(f"旧族清单无法解析: {path}") from exc
        _walk_collect(payload, ids, fingerprints)
        sources.append(
            {
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
                "task_id_count": len(ids) - before_ids,
                "task_fingerprint_count": len(fingerprints) - before_fps,
            }
        )
    return {
        "task_ids": sorted(ids),
        "task_fingerprints": sorted(fingerprints),
        "sources": sources,
    }


def assert_zero_intersection(legacy: Mapping[str, Any], *, v3_task_ids: Iterable[str],
                             v3_task_fingerprints: Iterable[str]) -> None:
    legacy_ids = set(str(value) for value in legacy.get("task_ids", ()))
    legacy_fps = set(str(value) for value in legacy.get("task_fingerprints", ()))
    overlap_ids = sorted(set(str(value) for value in v3_task_ids) & legacy_ids)
    overlap_fps = sorted(set(str(value) for value in v3_task_fingerprints) & legacy_fps)
    if overlap_ids:
        raise FamilyV3Error(f"v3 与旧族 task_id 存在交集（FC-06 fail-closed）: {overlap_ids[:5]}")
    if overlap_fps:
        raise FamilyV3Error(
            f"v3 与旧族 task_fingerprint 存在交集（FC-06 fail-closed）: {overlap_fps[:5]}"
        )


def build_isolation_report(
    *,
    v3_task_ids: Sequence[str],
    v3_task_fingerprints: Sequence[str],
    legacy: Mapping[str, Any],
    created_utc: str,
    holdout: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """生成 v3_isolation_report.json（R-06 fail-closed）。

    task_id 零交集（实质证据）与 task_fingerprint 零交集（旧源无指纹时不可判定）
    必须分列表述；全部无交集且计数一致才产出报告。
    """
    _validate_iso8601_utc(created_utc, "created_utc")
    assert_zero_intersection(
        legacy, v3_task_ids=v3_task_ids, v3_task_fingerprints=v3_task_fingerprints
    )
    v3_ids = sorted(str(value) for value in v3_task_ids)
    v3_fps = sorted(str(value) for value in v3_task_fingerprints)
    if len(v3_ids) != TOTAL_TASKS:
        raise FamilyV3Error(f"v3 task_id 数必须是 {TOTAL_TASKS}，实际 {len(v3_ids)}")
    if len(v3_fps) != TOTAL_TASKS:
        raise FamilyV3Error(f"v3 task_fingerprint 数必须是 {TOTAL_TASKS}，实际 {len(v3_fps)}")
    if len(set(v3_ids)) != len(v3_ids):
        raise FamilyV3Error("v3 task_id 存在重复")
    if len(set(v3_fps)) != len(v3_fps):
        raise FamilyV3Error("v3 task_fingerprint 存在重复")
    legacy_ids = sorted(str(value) for value in legacy.get("task_ids", ()))
    legacy_fps = sorted(str(value) for value in legacy.get("task_fingerprints", ()))
    id_overlap = sorted(set(v3_ids) & set(legacy_ids))
    fp_overlap = sorted(set(v3_fps) & set(legacy_fps))
    if id_overlap or fp_overlap:  # assert_zero_intersection 已 fail-closed，这里保留显式证据
        raise FamilyV3Error(f"v3 与旧族交集非空: ids={id_overlap[:5]} fps={fp_overlap[:5]}")
    task_id_block: dict[str, Any] = {
        "assertion": "TASK_ID_ZERO_INTERSECTION",
        "status": "PASS",
        "evidence_class": "SUBSTANTIVE",
        "v3_task_id_count": len(v3_ids),
        "legacy_task_id_count": len(legacy_ids),
        "overlap_count": 0,
        "overlap_sample": [],
        "note": "v3 120 个 task_id 与旧 M2/M5/M6 清单 task_id 实际集合交集为空。",
    }
    if legacy_fps:
        fingerprint_block: dict[str, Any] = {
            "assertion": "TASK_FINGERPRINT_ZERO_INTERSECTION",
            "status": "PASS",
            "evidence_class": "SUBSTANTIVE",
            "v3_task_fingerprint_count": len(v3_fps),
            "legacy_task_fingerprint_count": len(legacy_fps),
            "overlap_count": 0,
            "overlap_sample": [],
            "note": "旧源含 task_fingerprint，交集为空为实质证据。",
        }
    else:
        fingerprint_block = {
            "assertion": "TASK_FINGERPRINT_INTERSECTION_UNDETERMINABLE",
            "status": "NOT_DETERMINABLE",
            "evidence_class": "UNAVAILABLE",
            "v3_task_fingerprint_count": len(v3_fps),
            "legacy_task_fingerprint_count": 0,
            "overlap_count": 0,
            "overlap_sample": [],
            "note": "旧 M2/M5/M6 只读清单均无 task_fingerprint 字段；交集为空属平凡成立，不能证明指纹零交集。",
        }
    holdout_block: dict[str, Any] | None = None
    if holdout is not None:
        holdout_fps = sorted(str(value) for value in holdout.get("task_fingerprints", ()))
        reference_fps = sorted(
            str(value) for value in holdout.get("reference_task_fingerprints", ())
        )
        if len(holdout_fps) != HOLDOUT_TASK_COUNT:
            raise FamilyV3Error(
                f"v4 holdout task_fingerprint 数必须是 {HOLDOUT_TASK_COUNT}，实际 {len(holdout_fps)}"
            )
        if len(set(holdout_fps)) != len(holdout_fps):
            raise FamilyV3Error("v4 holdout task_fingerprint 存在重复")
        if len(reference_fps) != TOTAL_TASKS:
            raise FamilyV3Error(
                f"v3 参考 task_fingerprint 数必须是 {TOTAL_TASKS}，实际 {len(reference_fps)}"
            )
        holdout_overlap = sorted(set(holdout_fps) & set(reference_fps))
        if holdout_overlap:
            raise FamilyV3Error(
                f"v4 holdout 与 v3 参考 task_fingerprint 存在交集（R-V4-01 fail-closed）: {holdout_overlap[:5]}"
            )
        holdout_block = {
            "assertion": "HOLDOUT_FINGERPRINT_ZERO_INTERSECTION",
            "status": "PASS",
            "evidence_class": "SUBSTANTIVE",
            "holdout_task_count": len(holdout_fps),
            "holdout_splits": list(HOLDOUT_SPLITS),
            "v3_reference_task_fingerprint_count": len(reference_fps),
            "overlap_count": 0,
            "overlap_sample": [],
            "note": "v4 重播种的 meta_test/meta_test_ood 30 个 task_fingerprint 与 v3 官方包 120 个 task_fingerprint 零交集（实质证据）。",
        }
    package_version = FAMILY_VERSION if holdout is not None else TASK_FAMILY_VERSION
    payload: dict[str, Any] = {
        "schema_version": ISOLATION_SCHEMA_VERSION,
        "created_utc": created_utc,
        "family_id": FAMILY_ID,
        "family_version": package_version,
        "formula_version": FORMULA_VERSION,
        "family_seed": FAMILY_SEED,
        "task_id_pattern": TASK_ID_PATTERN.pattern,
        "v3": {
            "task_id_count": len(v3_ids),
            "task_fingerprint_count": len(v3_fps),
            "split_counts": dict(SPLIT_COUNTS),
        },
        "legacy": {
            "task_id_count": len(legacy_ids),
            "task_fingerprint_count": len(legacy_fps),
            "sources": [dict(source) for source in legacy.get("sources", ())],
        },
        "task_id_intersection": task_id_block,
        "task_fingerprint_intersection": fingerprint_block,
        "intersections": {"task_ids": [], "task_fingerprints": []},
        "limitations": [
            "task_fingerprint 交集的不可判定性来自旧源字段缺失，不是 v3 侧缺陷；补充旧源指纹后需重跑本报告。",
            "零交集只证明命名空间隔离，不证明任务难度/分布与旧族独立。",
        ],
        "assertion": "TASK_ID_ZERO_INTERSECTION",
        "status": "PASS",
        "physical_call_count": 0,
    }
    if holdout_block is not None:
        payload["holdout_fingerprint_intersection"] = holdout_block
        payload["limitations"].append(
            "旧 M2/M5/M6 legacy 清单无 task_fingerprint 字段；holdout 零交集断言只对 v3 官方包 "
            "120 个 task_fingerprint 实质成立，对 legacy 280 个 task_id 只能做 task_id 零交集。"
        )
    payload["sha256"] = digest(payload)
    return payload


def verify_isolation_report(payload: Mapping[str, Any]) -> bool:
    if payload.get("schema_version") != ISOLATION_SCHEMA_VERSION:
        raise FamilyV3Error(f"isolation report schema 不符: {payload.get('schema_version')!r}")
    body = {key: value for key, value in payload.items() if key != "sha256"}
    if payload.get("sha256") != digest(body):
        raise FamilyV3Error("isolation report sha256 校验失败")
    isolation_version = payload.get("family_version")
    if isolation_version not in (FAMILY_VERSION, *LEGACY_FAMILY_VERSIONS):
        raise FamilyV3Error(f"isolation report family_version 非法: {isolation_version!r}")
    if payload.get("status") != "PASS":
        raise FamilyV3Error(f"isolation report status 必须为 PASS，实际 {payload.get('status')!r}")
    if payload.get("assertion") != "TASK_ID_ZERO_INTERSECTION":
        raise FamilyV3Error("isolation report 顶层断言必须是 TASK_ID_ZERO_INTERSECTION")
    if int(payload.get("physical_call_count", -1)) != 0:
        raise FamilyV3Error("isolation report physical_call_count 必须为 0")
    v3_block = payload.get("v3")
    legacy_block = payload.get("legacy")
    if not isinstance(v3_block, Mapping) or not isinstance(legacy_block, Mapping):
        raise FamilyV3Error("isolation report 缺少 v3/legacy 计数块")
    task_id_block = payload.get("task_id_intersection")
    if not isinstance(task_id_block, Mapping):
        raise FamilyV3Error("isolation report 缺少 task_id_intersection 分列块")
    if task_id_block.get("assertion") != "TASK_ID_ZERO_INTERSECTION":
        raise FamilyV3Error("task_id_intersection assertion 不符")
    if task_id_block.get("status") != "PASS" or task_id_block.get("evidence_class") != "SUBSTANTIVE":
        raise FamilyV3Error("task_id_intersection 必须是 PASS/SUBSTANTIVE 实质证据")
    if int(task_id_block.get("overlap_count", -1)) != 0 or task_id_block.get("overlap_sample"):
        raise FamilyV3Error("task_id_intersection 交集非空")
    if int(task_id_block.get("v3_task_id_count", -1)) != int(v3_block.get("task_id_count", -2)):
        raise FamilyV3Error("task_id_intersection v3 计数不一致")
    if int(task_id_block.get("legacy_task_id_count", -1)) != int(legacy_block.get("task_id_count", -2)):
        raise FamilyV3Error("task_id_intersection legacy 计数不一致")
    fingerprint_block = payload.get("task_fingerprint_intersection")
    if not isinstance(fingerprint_block, Mapping):
        raise FamilyV3Error("isolation report 缺少 task_fingerprint_intersection 分列块")
    legacy_fp_count = int(legacy_block.get("task_fingerprint_count", -1))
    if int(fingerprint_block.get("legacy_task_fingerprint_count", -2)) != legacy_fp_count:
        raise FamilyV3Error("task_fingerprint_intersection legacy 计数不一致")
    if int(fingerprint_block.get("overlap_count", -1)) != 0 or fingerprint_block.get("overlap_sample"):
        raise FamilyV3Error("task_fingerprint_intersection 交集非空")
    if legacy_fp_count == 0:
        if fingerprint_block.get("status") != "NOT_DETERMINABLE" or fingerprint_block.get("evidence_class") != "UNAVAILABLE":
            raise FamilyV3Error("legacy 无指纹时 task_fingerprint_intersection 必须是 NOT_DETERMINABLE/UNAVAILABLE")
        if fingerprint_block.get("assertion") != "TASK_FINGERPRINT_INTERSECTION_UNDETERMINABLE":
            raise FamilyV3Error("legacy 无指纹时 assertion 必须是 TASK_FINGERPRINT_INTERSECTION_UNDETERMINABLE")
    else:
        if fingerprint_block.get("status") != "PASS" or fingerprint_block.get("evidence_class") != "SUBSTANTIVE":
            raise FamilyV3Error("legacy 含指纹且交集为空时 task_fingerprint_intersection 必须是 PASS/SUBSTANTIVE")
    intersections = payload.get("intersections", {})
    if intersections.get("task_ids") or intersections.get("task_fingerprints"):
        raise FamilyV3Error("isolation report 交集非空")
    if isolation_version == FAMILY_VERSION:
        holdout_block = payload.get("holdout_fingerprint_intersection")
        if not isinstance(holdout_block, Mapping):
            raise FamilyV3Error("v4 isolation report 缺少 holdout_fingerprint_intersection 分列块")
        if holdout_block.get("assertion") != "HOLDOUT_FINGERPRINT_ZERO_INTERSECTION":
            raise FamilyV3Error("holdout_fingerprint_intersection assertion 不符")
        if holdout_block.get("status") != "PASS" or holdout_block.get("evidence_class") != "SUBSTANTIVE":
            raise FamilyV3Error("holdout_fingerprint_intersection 必须是 PASS/SUBSTANTIVE 实质证据")
        if int(holdout_block.get("holdout_task_count", -1)) != HOLDOUT_TASK_COUNT:
            raise FamilyV3Error("holdout_fingerprint_intersection holdout_task_count 不符")
        if list(holdout_block.get("holdout_splits", ())) != list(HOLDOUT_SPLITS):
            raise FamilyV3Error("holdout_fingerprint_intersection holdout_splits 不符")
        if int(holdout_block.get("v3_reference_task_fingerprint_count", -1)) != TOTAL_TASKS:
            raise FamilyV3Error("holdout_fingerprint_intersection v3 参考指纹数不符")
        if int(holdout_block.get("overlap_count", -1)) != 0 or holdout_block.get("overlap_sample"):
            raise FamilyV3Error("holdout_fingerprint_intersection 交集非空")
    elif "holdout_fingerprint_intersection" in payload:
        raise FamilyV3Error("legacy v3 isolation report 不得携带 holdout 分列块")
    return True


# ---------------------------------------------------------------------------
# 端点与 stopping_rules 规范化
# ---------------------------------------------------------------------------
def normalize_endpoints(primary_endpoints: Sequence[str]) -> list[str]:
    """D-S0-2-02：只允许 4 个规范 ID，禁止旧别名静默映射；返回规范顺序。"""
    if isinstance(primary_endpoints, str) or not isinstance(primary_endpoints, (list, tuple)):
        raise FamilyV3Error("primary_endpoints 必须是 list[str]")
    values = [str(value) for value in primary_endpoints]
    for value in values:
        if value in FORBIDDEN_ENDPOINT_ALIASES:
            raise FamilyV3Error(
                f"primary_endpoints 含禁用别名 {value!r}；必须使用规范 ID {PRIMARY_ENDPOINTS}"
            )
    if len(set(values)) != len(values):
        raise FamilyV3Error("primary_endpoints 存在重复")
    if set(values) != set(PRIMARY_ENDPOINTS):
        raise FamilyV3Error(
            f"primary_endpoints 必须精确等于 {PRIMARY_ENDPOINTS}，实际 {tuple(values)}"
        )
    return list(PRIMARY_ENDPOINTS)


def assert_endpoint_row_coverage(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """R-05：S1 分析 CSV 行必须精确使用 ENDPOINT_ROW_KEYS，且主端点不得全 null。

    参考 M5 故障：主端点列全 null（4800/4800）导致分析无信息量。本函数 fail-closed：
    - rows 非空；
    - 每行键集合精确等于登记键（缺键/多键均抛错）；
    - 4 个主端点在所有行中至少各有一个非 null；
    返回 n_nonnull/null_rate 覆盖统计（供 analysis CSV 顶部 metadata）。
    """
    if isinstance(rows, Mapping) or not isinstance(rows, Sequence):
        raise FamilyV3Error("assert_endpoint_row_coverage 需要行序列（list[Mapping]）")
    if not rows:
        raise FamilyV3Error("端点 CSV 行不能为空")
    expected = set(ENDPOINT_ROW_KEYS)
    counts = {key: 0 for key in ENDPOINT_ROW_KEYS}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise FamilyV3Error(f"端点 CSV 第 {index} 行必须是 object")
        keys = set(row)
        if keys != expected:
            missing = sorted(expected - keys)
            extra = sorted(keys - expected)
            raise FamilyV3Error(
                f"端点 CSV 第 {index} 行键与 ENDPOINT_ROW_KEYS 不一致（缺 {missing}，多 {extra}）"
            )
        for key in ENDPOINT_ROW_KEYS:
            if row[key] is not None:
                counts[key] += 1
    total = len(rows)
    for endpoint in PRIMARY_ENDPOINTS:
        if counts[endpoint] == 0:
            raise FamilyV3Error(
                f"主端点 {endpoint} 在所有 {total} 行中均为 null（fail-closed，参考 M5 4800/4800 全 null 故障）"
            )
    return {
        "row_count": total,
        "nonnull_counts": dict(counts),
        "null_rates": {key: (total - counts[key]) / total for key in ENDPOINT_ROW_KEYS},
    }


def normalize_stopping_rules(value: Any) -> list[str]:
    """v3：stopping_rules 必须为非空 list[str]，每项 strip 后长度 >= 2；拒绝裸 str。"""
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise FamilyV3Error(
            "stopping_rules 必须是 list[str]（v3 fail-closed，禁止裸 str/逐字符数组）"
        )
    rules: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise FamilyV3Error(f"stopping_rules[{index}] 必须是 str，实际 {type(item).__name__}")
        stripped = item.strip()
        if not stripped:
            raise FamilyV3Error(f"stopping_rules[{index}] 不能为空字符串")
        if len(stripped) < STOPPING_RULE_MIN_LENGTH:
            raise FamilyV3Error(
                f"stopping_rules[{index}] strip 后长度必须 >= {STOPPING_RULE_MIN_LENGTH}（当前 {item!r}）"
            )
        rules.append(stripped)
    if not rules:
        raise FamilyV3Error("stopping_rules 不能为空列表")
    return rules


# ---------------------------------------------------------------------------
# frozen_family.json（v3）
# ---------------------------------------------------------------------------
FROZEN_REQUIRED_FIELDS = (
    "family_id",
    "family_version",
    "family_seed",
    "family_fingerprint",
    "family_config",
    "radius_base",
    "reference_solution",
    "gap_definition",
    "endpoint_row_keys",
    "analysis_plan_digest",
    "task_id_namespace",
    "task_id_pattern",
    "split",
    "primary_endpoints",
    "arms",
    "budgets",
    "k_values",
    "meta_test_tuning_policy",
    "physical_call_count",
)


def _serialize_v3_config(config: tf.TaskFamilyConfig) -> dict[str, Any]:
    return {
        "family_id": config.family_id,
        "design_dim": int(config.design_dim),
        "context_names": list(config.context_names),
        "seed": int(config.seed),
        "train_tasks": int(config.train_tasks),
        "validation_tasks": int(config.validation_tasks),
        "test_tasks": int(config.test_tasks),
        "ood_tasks": int(config.ood_tasks),
        "negative_control_tasks": int(config.negative_control_tasks),
        "designs_per_task": int(config.designs_per_task),
        "support_pool_size": int(config.support_pool_size),
        "query_size": int(config.query_size),
        "reference_tolerance": float(config.reference_tolerance),
        "family_version": config.family_version,
        "radius_base": None if config.radius_base is None else float(config.radius_base),
    }


def _deserialize_v3_config(payload: Any) -> tf.TaskFamilyConfig:
    if not isinstance(payload, Mapping):
        raise FamilyV3Error("frozen family_config 必须是 JSON 对象")
    data = dict(payload)
    if isinstance(data.get("context_names"), list):
        data["context_names"] = tuple(data["context_names"])
    try:
        return tf.TaskFamilyConfig(**data)
    except tf.TaskFamilyError as exc:
        raise FamilyV3Error(f"frozen family_config 非法: {exc}") from exc


def build_frozen_family_v3(
    family_config: tf.TaskFamilyConfig,
    *,
    split_manifest: Mapping[str, Any],
    holdout_seed: int | None = None,
    run_id: str,
    git_sha: str,
    created_utc: str,
    code_sha: str | None = None,
    radius_base: float | None = None,
    calibration_status: str = "PENDING_A2_CALIBRATION",
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    """构造 frozen_family.json（v3）载荷；created_utc 必须显式传入以保证确定性重跑。"""
    assert_family_v3_identity(family_config)
    if not isinstance(created_utc, str) or not created_utc.strip():
        raise FamilyV3Error("created_utc 必须是非空字符串（确定性重跑要求显式传入）")
    if not isinstance(run_id, str) or not run_id.strip():
        raise FamilyV3Error("run_id 必须是非空字符串")
    if not isinstance(git_sha, str) or not git_sha.strip():
        raise FamilyV3Error("git_sha 必须是非空字符串")
    verify_split_manifest_v3(split_manifest, family_config=family_config)
    selected_radius = float(family_config.radius_base if radius_base is None else radius_base)
    if abs(selected_radius - float(family_config.radius_base)) > 1e-12:
        raise FamilyV3Error(
            f"radius_base 与 family_config 不一致: {selected_radius!r} != {family_config.radius_base!r}"
        )
    if not (tf.V3_RADIUS_MIN <= selected_radius <= tf.V3_RADIUS_MAX):
        raise FamilyV3Error(f"radius_base 必须在 [{tf.V3_RADIUS_MIN}, {tf.V3_RADIUS_MAX}]")
    if calibration_status not in ("PENDING_A2_CALIBRATION", "CALIBRATED"):
        raise FamilyV3Error(f"未知 calibration_status: {calibration_status!r}")
    if holdout_seed is None:
        payload_family_version = TASK_FAMILY_VERSION
        family_fingerprint_value = tf.family_fingerprint(family_config)
        holdout_extra: dict[str, Any] = {}
    else:
        seed = _validate_holdout_seed(holdout_seed)
        if seed != HOLDOUT_SEED:
            raise FamilyV3Error(
                f"v4 冻结包 holdout_seed 必须为 {HOLDOUT_SEED}，实际 {seed}"
            )
        payload_family_version = FAMILY_VERSION
        family_fingerprint_value = package_family_fingerprint(
            family_config, holdout_seed=seed
        )
        holdout_extra = {
            "task_family_version": TASK_FAMILY_VERSION,
            "holdout_seed": seed,
            "holdout_splits": list(HOLDOUT_SPLITS),
            "holdout_task_count": HOLDOUT_TASK_COUNT,
            "holdout_reseed": {
                "policy": "R-V4-01",
                "holdout_seed": seed,
                "holdout_splits": list(HOLDOUT_SPLITS),
                "unchanged_splits": ["meta_train", "meta_validation", "negative_control"],
                "derivation": "seed=derive_seed(family,split,index,attempt,config.seed,'holdout',holdout_seed)",
            },
        }
    split_task_ids = {split: list(split_manifest.get("task_ids", {}).get(split, ())) for split in SPLIT_ORDER}
    if any(len(split_task_ids[split]) != SPLIT_COUNTS[split] for split in SPLIT_ORDER):
        raise FamilyV3Error("split manifest 的 split 任务数与冻结规模不一致")
    payload: dict[str, Any] = {
        "schema_version": FROZEN_SCHEMA_VERSION,
        "created_utc": created_utc,
        "run_id": run_id,
        "git_sha": git_sha,
        "code_sha": code_sha if code_sha is not None else package_code_sha(),
        "physical_call_count": 0,
        "family_id": FAMILY_ID,
        "family_version": payload_family_version,
        "formula_version": FORMULA_VERSION,
        "family_seed": FAMILY_SEED,
        "family_fingerprint": family_fingerprint_value,
        "family_config": _serialize_v3_config(family_config),
        "radius_base": selected_radius,
        "radius_mapping": {
            "formula": "clip(radius_base*(1+jitter*z), min, max)",
            "jitter": tf.V3_RADIUS_JITTER,
            "min": tf.V3_RADIUS_MIN,
            "max": tf.V3_RADIUS_MAX,
            "ood_radius_scale": tf.V3_OOD_RADIUS_SCALE,
            "z": "normal(0,1) from task seed",
        },
        "reference_solution": REFERENCE_SOLUTION,
        "gap_definition": GAP_DEFINITION,
        "param_distributions": dict(tf.V3_PARAM_DISTRIBUTIONS),
        "context_coupling": {
            "scale": tf.V3_CONTEXT_COUPLING_SCALE,
            "formula": "b_eff = b + scale*(context_1 + context_2 - 2.0)",
        },
        "ood_protocol": {
            "context_shift": tf.V3_OOD_CONTEXT_SHIFT,
            "radius_scale": tf.V3_OOD_RADIUS_SCALE,
        },
        "design": {
            "design_dim": tf.DESIGN_DIM,
            "design_names": list(tf.DESIGN_NAMES),
            "design_lower": [float(value) for value in tf.DESIGN_LOWER],
            "design_upper": [float(value) for value in tf.DESIGN_UPPER],
            "design_bounds": [
                [float(low), float(high)] for low, high in zip(tf.DESIGN_LOWER, tf.DESIGN_UPPER)
            ],
        },
        "task_id_namespace": TASK_ID_PREFIX,
        "task_id_pattern": TASK_ID_PATTERN.pattern,
        "split": {
            "manifest_sha256": digest(dict(split_manifest)),
            "split_hash": split_manifest["split_hash"],
            "counts": dict(split_manifest["counts"]),
            "split_order": list(SPLIT_ORDER),
            "task_ids": split_task_ids,
        },
        "primary_endpoints": list(PRIMARY_ENDPOINTS),
        "endpoint_row_keys": list(ENDPOINT_ROW_KEYS),
        "analysis_plan_digest": ANALYSIS_PLAN_DIGEST,
        "secondary_endpoints": list(SECONDARY_ENDPOINTS),
        "arms": list(ARM_IDS),
        "budgets": list(BUDGETS),
        "k_values": list(K_VALUES),
        "initial_design_count": INITIAL_DESIGN_COUNT,
        "support_policy": {
            "K_support_counted_in_B": True,
            "support_shared_by_all_arms": True,
            "initial_designs": INITIAL_DESIGN_COUNT,
            "main_search_evaluations": "-",
            "note": "K 个支持评价计入 B；阶段2 初始设计 8-K；阶段3 主搜索 B-8；合计精确 B。",
        },
        "calibration": {
            "status": calibration_status,
            "selected_radius_base": selected_radius,
            "radius_base_source": "design_default" if calibration_status == "PENDING_A2_CALIBRATION" else "A2_calibration",
            "note": "PENDING 状态下本冻结包为 S0-2 预校准冻结包；A2 若选出不同半径，必须重新生成任务并升 family fingerprint。",
        },
        "evaluator": "synthetic-analytic",
        "physics_validation_status": "NOT_APPLICABLE",
        "meta_test_tuning_policy": META_TEST_TUNING_POLICY,
        "notes": [str(note) for note in notes],
    }
    payload.update(holdout_extra)
    payload["sha256"] = digest(payload)
    return payload


def verify_frozen_family_v3(payload: Mapping[str, Any]) -> bool:
    """校验 frozen_family v3：schema/sha256/家族身份/半径/split/端点/预算/物理调用=0。"""
    if payload.get("schema_version") != FROZEN_SCHEMA_VERSION:
        raise FamilyV3Error(f"frozen schema 不符: {payload.get('schema_version')!r}")
    for name in FROZEN_REQUIRED_FIELDS:
        if name not in payload:
            raise FamilyV3Error(f"frozen_family 缺少必填字段 {name!r}")
    body = {key: value for key, value in payload.items() if key != "sha256"}
    if payload.get("sha256") != digest(body):
        raise FamilyV3Error("frozen_family sha256 校验失败（冻结后被修改）")
    if payload.get("family_id") != FAMILY_ID:
        raise FamilyV3Error("frozen_family 家族身份不符（family_id）")
    frozen_version = payload.get("family_version")
    if frozen_version == FAMILY_VERSION:
        if payload.get("task_family_version") != TASK_FAMILY_VERSION:
            raise FamilyV3Error("v4 frozen 缺少/错误 task_family_version")
        holdout_reseed = payload.get("holdout_reseed")
        if not isinstance(holdout_reseed, Mapping):
            raise FamilyV3Error("v4 frozen 缺少 holdout_reseed 声明块")
        if holdout_reseed.get("policy") != "R-V4-01":
            raise FamilyV3Error("v4 frozen holdout_reseed.policy 必须是 R-V4-01")
        holdout_seed_value = _validate_holdout_seed(payload.get("holdout_seed"))
        if holdout_seed_value != HOLDOUT_SEED:
            raise FamilyV3Error(f"v4 frozen holdout_seed 必须为 {HOLDOUT_SEED}")
        if int(holdout_reseed.get("holdout_seed", -1)) != holdout_seed_value:
            raise FamilyV3Error("v4 frozen holdout_reseed 与 holdout_seed 不一致")
        if list(payload.get("holdout_splits", ())) != list(HOLDOUT_SPLITS):
            raise FamilyV3Error("v4 frozen holdout_splits 不符")
        if int(payload.get("holdout_task_count", -1)) != HOLDOUT_TASK_COUNT:
            raise FamilyV3Error("v4 frozen holdout_task_count 不符")
        if list(holdout_reseed.get("holdout_splits", ())) != list(HOLDOUT_SPLITS):
            raise FamilyV3Error("v4 frozen holdout_reseed.holdout_splits 不符")
        if list(holdout_reseed.get("unchanged_splits", ())) != [
            "meta_train",
            "meta_validation",
            "negative_control",
        ]:
            raise FamilyV3Error("v4 frozen holdout_reseed.unchanged_splits 不符")
    elif frozen_version in LEGACY_FAMILY_VERSIONS:
        if "holdout_seed" in payload or "holdout_reseed" in payload:
            raise FamilyV3Error("legacy v3 frozen 不得携带 holdout 字段")
    else:
        raise FamilyV3Error(f"frozen_family family_version 非法: {frozen_version!r}")
    if payload.get("formula_version") != FORMULA_VERSION:
        raise FamilyV3Error("frozen_family formula_version 不符")
    if int(payload.get("family_seed", -1)) != FAMILY_SEED:
        raise FamilyV3Error("frozen_family family_seed 不符")
    config = _deserialize_v3_config(payload["family_config"])
    if config.family_version != TASK_FAMILY_VERSION:
        raise FamilyV3Error("frozen family_config.family_version 必须是 p4ra-family-v3（数学任务族）")
    expected_fingerprint = (
        tf.family_fingerprint(config)
        if frozen_version in LEGACY_FAMILY_VERSIONS
        else package_family_fingerprint(config, holdout_seed=holdout_seed_value)
    )
    if expected_fingerprint != payload.get("family_fingerprint"):
        raise FamilyV3Error("frozen family_fingerprint 与 family_config/包版本不符")
    if config.radius_base is None or abs(float(config.radius_base) - float(payload["radius_base"])) > 1e-12:
        raise FamilyV3Error("frozen radius_base 与 family_config.radius_base 不符")
    if payload.get("reference_solution") != REFERENCE_SOLUTION:
        raise FamilyV3Error(f"frozen reference_solution 必须是 {REFERENCE_SOLUTION!r}")
    if payload.get("gap_definition") != GAP_DEFINITION:
        raise FamilyV3Error(f"frozen gap_definition 必须是 {GAP_DEFINITION!r}")
    if payload.get("task_id_namespace") != TASK_ID_PREFIX or payload.get("task_id_pattern") != TASK_ID_PATTERN.pattern:
        raise FamilyV3Error("frozen task_id 命名空间/正则不符")
    split = payload.get("split")
    if not isinstance(split, Mapping):
        raise FamilyV3Error("frozen 缺少 split 块")
    if digest(_split_hash_payload(split.get("task_ids", {}))) != split.get("split_hash"):
        raise FamilyV3Error("frozen split_hash 校验失败")
    if dict(split.get("counts", {})) != dict(SPLIT_COUNTS):
        raise FamilyV3Error(f"frozen split counts 必须为 {SPLIT_COUNTS}")
    for split_name in SPLIT_ORDER:
        ids = list(split.get("task_ids", {}).get(split_name, ()))
        if len(ids) != SPLIT_COUNTS[split_name]:
            raise FamilyV3Error(f"frozen split {split_name} task_id 数不符")
        for task_id in ids:
            validate_task_id(task_id)
    if normalize_endpoints(tuple(payload.get("primary_endpoints", ()))) != list(PRIMARY_ENDPOINTS):
        raise FamilyV3Error("frozen primary_endpoints 不符")
    if list(payload.get("endpoint_row_keys", ())) != list(ENDPOINT_ROW_KEYS):
        raise FamilyV3Error("frozen endpoint_row_keys 不符")
    if payload.get("analysis_plan_digest") != ANALYSIS_PLAN_DIGEST:
        raise FamilyV3Error("frozen analysis_plan_digest 不符")
    if list(payload.get("secondary_endpoints", ())) != list(SECONDARY_ENDPOINTS):
        raise FamilyV3Error("frozen secondary_endpoints 不符")
    if tuple(payload.get("arms", ())) != ARM_IDS:
        raise FamilyV3Error(f"frozen arms 必须为 {ARM_IDS}")
    if tuple(payload.get("budgets", ())) != BUDGETS:
        raise FamilyV3Error(f"frozen budgets 必须为 {BUDGETS}")
    if tuple(payload.get("k_values", ())) != K_VALUES:
        raise FamilyV3Error(f"frozen k_values 必须为 {K_VALUES}")
    if int(payload.get("initial_design_count", -1)) != INITIAL_DESIGN_COUNT:
        raise FamilyV3Error("frozen initial_design_count 不符")
    if int(payload.get("physical_call_count", -1)) != 0:
        raise FamilyV3Error("frozen physical_call_count 必须为 0")
    if payload.get("evaluator") != "synthetic-analytic":
        raise FamilyV3Error("frozen evaluator 必须是 synthetic-analytic")
    if payload.get("physics_validation_status") != "NOT_APPLICABLE":
        raise FamilyV3Error("frozen physics_validation_status 必须是 NOT_APPLICABLE")
    if not payload.get("meta_test_tuning_policy"):
        raise FamilyV3Error("frozen 缺少 meta_test 调参禁止声明")
    return True


def frozen_to_v3_config(payload: Mapping[str, Any]) -> tf.TaskFamilyConfig:
    verify_frozen_family_v3(payload)
    return _deserialize_v3_config(payload["family_config"])


# ---------------------------------------------------------------------------
# preregistration.json（p4ra-prereg-v1）
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# preregistration.json（p4ra-prereg-v1，合同 §7 17 个规范字段 + 旧名别名）
# ---------------------------------------------------------------------------
PREREG_REQUIRED_FIELDS = (
    "schema_version",
    "prereg_id",
    "family_version",
    "split_counts",
    "split_digest",
    "task_id_regex",
    "frozen_at_utc",
    "primary_endpoints",
    "secondary_metrics",
    "budget_plan",
    "task_counts",
    "seeds",
    "stopping_rules",
    "failure_rules",
    "multiple_comparison",
    "analysis_plan_digest",
    "prereg_digest",
)
_PREREG_ID_PATTERN = re.compile(r"^p4ra-prereg-v3-[0-9a-f]{16}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _budget_fairness_module():
    """延迟导入：budget_fairness 顶层依赖本模块，避免循环导入。"""
    from . import budget_fairness as bf

    return bf


def _validate_iso8601_utc(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FamilyV3Error(f"{name} 必须是非空 ISO-8601 时间戳")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FamilyV3Error(f"{name} 必须是 ISO-8601 时间戳，实际 {value!r}") from exc
    if parsed.tzinfo is None:
        raise FamilyV3Error(f"{name} 必须带时区偏移（ISO-8601），实际 {value!r}")
    return text


def _normalize_string_list(value: Any, name: str, *, min_items: int = 1) -> list[str]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise FamilyV3Error(f"{name} 必须是 list[str]（禁止裸 str）")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise FamilyV3Error(f"{name}[{index}] 必须是 str，实际 {type(item).__name__}")
        text = item.strip()
        if not text:
            raise FamilyV3Error(f"{name}[{index}] 不能为空字符串")
        if len(text) < 2:
            raise FamilyV3Error(f"{name}[{index}] strip 后长度必须 >= 2，实际 {item!r}")
        result.append(text)
    if len(result) < min_items:
        raise FamilyV3Error(f"{name} 至少需要 {min_items} 项")
    if len(set(result)) != len(result):
        raise FamilyV3Error(f"{name} 存在重复项")
    return result


def _validate_multiple_comparison(value: Any) -> dict[str, Any]:
    if isinstance(value, str) or not isinstance(value, Mapping):
        raise FamilyV3Error("multiple_comparison 必须是 object（禁止 str）")
    payload = dict(value)
    method = payload.get("method")
    family = payload.get("family")
    if not isinstance(method, str) or not method.strip():
        raise FamilyV3Error("multiple_comparison.method 必须是非空 str")
    if not isinstance(family, str) or not family.strip():
        raise FamilyV3Error("multiple_comparison.family 必须是非空 str")
    alpha = payload.get("alpha")
    if alpha is not None and (not isinstance(alpha, (int, float)) or not (0.0 < float(alpha) < 1.0)):
        raise FamilyV3Error("multiple_comparison.alpha 必须在 (0,1)")
    return payload


def _validate_analysis_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise FamilyV3Error("analysis_plan 必须是 object")
    payload = dict(plan)
    if list(payload.get("endpoint_row_keys", ())) != list(ENDPOINT_ROW_KEYS):
        raise FamilyV3Error(
            f"analysis_plan.endpoint_row_keys 必须精确等于 ENDPOINT_ROW_KEYS={list(ENDPOINT_ROW_KEYS)}"
        )
    if list(payload.get("primary_endpoints", ())) != list(PRIMARY_ENDPOINTS):
        raise FamilyV3Error("analysis_plan.primary_endpoints 必须等于 4 个规范主端点")
    if list(payload.get("csv_columns", ())) != list(ENDPOINT_ROW_KEYS):
        raise FamilyV3Error("analysis_plan.csv_columns 必须等于 ENDPOINT_ROW_KEYS")
    if not isinstance(payload.get("statistics"), Mapping):
        raise FamilyV3Error("analysis_plan.statistics 必须是 object")
    if not isinstance(payload.get("null_policy"), str) or not payload["null_policy"].strip():
        raise FamilyV3Error("analysis_plan.null_policy 必须是非空 str")
    _validate_multiple_comparison(payload.get("multiple_comparison"))
    return payload


def _prereg_digest(payload: Mapping[str, Any]) -> str:
    """自身 digest：计算时 prereg_digest 置空、排除外层 sha256（合同 §7）。"""
    body = dict(payload)
    body.pop("sha256", None)
    body["prereg_digest"] = ""
    return digest(body)


def _budget_plan_payload(plans: Sequence[Mapping[str, Any]], bf: Any) -> dict[str, Any]:
    clone_pairs: list[dict[str, Any]] = []
    seen_pairs: set[tuple[int, str, str]] = set()
    for plan in plans:
        if plan.get("clone_of"):
            key = (int(plan["K"]), str(plan["arm"]), str(plan["clone_of"]))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            clone_pairs.append(
                {
                    "K": key[0],
                    "clone_arm": key[1],
                    "canonical_arm": key[2],
                }
            )
    clone_pairs.sort(key=lambda item: (item["K"], item["clone_arm"]))
    inference_excluded: dict[str, list[str]] = {}
    for k_shot in K_VALUES:
        excluded = sorted(bf.clone_map(k_shot))
        if excluded:
            inference_excluded[str(k_shot)] = excluded
    return {
        "schema_version": bf.FAIRNESS_SCHEMA_VERSION,
        "arms": list(ARM_IDS),
        "budgets": list(BUDGETS),
        "k_values": list(K_VALUES),
        "initial_designs": INITIAL_DESIGN_COUNT,
        "support_counted": True,
        "support_counted_in_B": True,
        "billable_rule": "所有臂 billable=B；阶段 support(K)+initial(8-K)+main(B-8)，K 个支持评价计入 B",
        "plan_count": len(plans),
        "plans_digest": digest(plans),
        "clone_pairs": clone_pairs,
        "inference_excluded": inference_excluded,
        "physical_call_count": 0,
    }


def build_preregistration_v3(
    frozen_family: Mapping[str, Any],
    *,
    run_id: str,
    created_utc: str,
    frozen_at_utc: str | None = None,
    arms: Sequence[str] = ARM_IDS,
    budgets: Sequence[int] = BUDGETS,
    k_values: Sequence[int] = K_VALUES,
    optimization_seeds: Sequence[int] = tuple(range(10)),
    meta_seeds: Sequence[int] = (0, 1, 2),
    primary_endpoints: Sequence[str] = PRIMARY_ENDPOINTS,
    secondary_endpoints: Sequence[str] = SECONDARY_ENDPOINTS,
    secondary_metrics: Sequence[str] = SECONDARY_METRICS,
    statistics: Mapping[str, Any] | None = None,
    null_policy: str = NULL_POLICY,
    stopping_rules: Sequence[str] = STOPPING_RULES,
    failure_rules: Sequence[str] = FAILURE_RULES,
    multiple_comparison: Mapping[str, Any] | None = None,
    analysis_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构造预注册载荷（写测试集前生成，绑定 frozen sha256/family/split）。

    合同 §7：17 个规范字段全部落盘；旧名 split_hash/task_id_pattern/created_utc/
    secondary_endpoints/split_counts/optimization_seeds/meta_seeds 作为附加别名保留。
    """
    verify_frozen_family_v3(frozen_family)
    created = _validate_iso8601_utc(created_utc, "created_utc")
    frozen_utc = (
        created if frozen_at_utc is None else _validate_iso8601_utc(frozen_at_utc, "frozen_at_utc")
    )
    if frozen_utc != created:
        raise FamilyV3Error(f"frozen_at_utc 必须等于 created_utc（确定性重跑）：{frozen_utc!r} != {created!r}")
    if not isinstance(run_id, str) or not run_id.strip():
        raise FamilyV3Error("run_id 必须是非空字符串")
    if tuple(arms) != ARM_IDS:
        raise FamilyV3Error(f"prereg arms 必须为 {ARM_IDS}，实际 {tuple(arms)}")
    if tuple(budgets) != BUDGETS:
        raise FamilyV3Error(f"prereg budgets 必须为 {BUDGETS}，实际 {tuple(budgets)}")
    if tuple(k_values) != K_VALUES:
        raise FamilyV3Error(f"prereg k_values 必须为 {K_VALUES}，实际 {tuple(k_values)}")
    opt_seeds = [int(value) for value in optimization_seeds]
    if len(opt_seeds) < 10 or len(set(opt_seeds)) != len(opt_seeds):
        raise FamilyV3Error("optimization_seeds 至少 10 个且不得重复")
    meta_seed_values = [int(value) for value in meta_seeds]
    if len(meta_seed_values) < 3 or len(set(meta_seed_values)) != len(meta_seed_values):
        raise FamilyV3Error("meta_train_seeds 至少 3 个且不得重复")
    endpoints = normalize_endpoints(primary_endpoints)
    rules = normalize_stopping_rules(stopping_rules)
    failures = _normalize_string_list(failure_rules, "failure_rules")
    metrics = _normalize_string_list(secondary_metrics, "secondary_metrics")
    multiple = _validate_multiple_comparison(
        MULTIPLE_COMPARISON if multiple_comparison is None else multiple_comparison
    )
    plan = _validate_analysis_plan(ANALYSIS_PLAN if analysis_plan is None else analysis_plan)
    plan_digest = digest(plan)
    bf = _budget_fairness_module()
    budget_plans = bf.build_all_budget_plans()
    bf.assert_budget_fairness(budget_plans)
    budget_plan = _budget_plan_payload(budget_plans, bf)
    fingerprint = str(frozen_family["family_fingerprint"])
    split_hash = str(frozen_family["split"]["split_hash"])
    frozen_version = frozen_family["family_version"]
    version_extra: dict[str, Any] = {}
    if frozen_version == FAMILY_VERSION:
        version_extra = {
            "task_family_version": frozen_family.get("task_family_version"),
            "holdout_seed": frozen_family.get("holdout_seed"),
            "holdout_splits": list(frozen_family.get("holdout_splits", ())),
            "holdout_task_count": frozen_family.get("holdout_task_count"),
        }
    elif frozen_version in LEGACY_FAMILY_VERSIONS:
        if "task_family_version" in frozen_family:
            raise FamilyV3Error("legacy v3 frozen 不得携带 task_family_version 包层字段")
    else:
        raise FamilyV3Error(f"未知 frozen family_version: {frozen_version!r}")
    payload: dict[str, Any] = {
        "schema_version": PREREGISTRATION_SCHEMA_VERSION,
        "prereg_id": f"p4ra-prereg-v3-{fingerprint[:16]}",
        "family_id": frozen_family["family_id"],
        "family_version": frozen_family["family_version"],
        "formula_version": frozen_family["formula_version"],
        "family_seed": frozen_family["family_seed"],
        "family_fingerprint": fingerprint,
        "radius_base": float(frozen_family["radius_base"]),
        "run_id": run_id,
        "physical_call_count": 0,
        "frozen_family_sha256": frozen_family["sha256"],
        "created_utc": created,
        "frozen_at_utc": frozen_utc,
        "task_id_namespace": frozen_family["task_id_namespace"],
        "task_id_regex": TASK_ID_PATTERN.pattern,
        "task_id_pattern": TASK_ID_PATTERN.pattern,
        "split_digest": split_hash,
        "split_hash": split_hash,
        "split_counts": dict(frozen_family["split"]["counts"]),
        "task_counts": dict(SPLIT_COUNTS),
        "primary_endpoints": endpoints,
        "secondary_metrics": metrics,
        "secondary_endpoints": list(secondary_endpoints),
        "arms": list(arms),
        "budgets": list(budgets),
        "k_values": list(k_values),
        "initial_design_count": INITIAL_DESIGN_COUNT,
        "seeds": {
            "meta_train_seeds": meta_seed_values,
            "optimization_seeds": opt_seeds,
        },
        "optimization_seeds": opt_seeds,
        "meta_seeds": meta_seed_values,
        "statistics": dict(statistics if statistics is not None else STATISTICS_PLAN),
        "null_policy": null_policy,
        "stopping_rules": rules,
        "failure_rules": failures,
        "multiple_comparison": multiple,
        "budget_plan": budget_plan,
        "analysis_plan": plan,
        "analysis_plan_digest": plan_digest,
        "evaluator": "synthetic-analytic",
        "physics_validation_status": "NOT_APPLICABLE",
        "reference_solution": frozen_family["reference_solution"],
        "gap_definition": frozen_family["gap_definition"],
        "meta_test_tuning_policy": frozen_family["meta_test_tuning_policy"],
        "notes": [
            "本预注册只绑定合成解析任务；physical_call_count=0；不代表真实飞机/CFD 性能。",
        ],
    }
    payload.update(version_extra)
    payload["prereg_digest"] = _prereg_digest(payload)
    payload["sha256"] = digest(payload)
    return payload


def verify_preregistration_v3(
    payload: Mapping[str, Any], frozen_family: Mapping[str, Any] | None = None
) -> bool:
    """严格校验 p4ra-prereg-v1（合同 §7）：缺字段/别名缺规范名/错类型/自 digest 不符均 fail-closed。"""
    if payload.get("schema_version") != PREREGISTRATION_SCHEMA_VERSION:
        raise FamilyV3Error(f"prereg schema 不符: {payload.get('schema_version')!r}")
    for name in PREREG_REQUIRED_FIELDS:
        if name not in payload:
            raise FamilyV3Error(f"prereg 缺少合同 §7 必填字段 {name!r}")
    body = {key: value for key, value in payload.items() if key != "sha256"}
    if payload.get("sha256") != digest(body):
        raise FamilyV3Error("preregistration sha256 校验失败（预注册被修改）")
    prereg_digest = payload.get("prereg_digest")
    if not isinstance(prereg_digest, str) or not _SHA256_PATTERN.match(prereg_digest):
        raise FamilyV3Error("prereg_digest 必须是 64 位小写十六进制 sha256")
    if prereg_digest != _prereg_digest(payload):
        raise FamilyV3Error("prereg_digest 重算不一致（预注册被修改）")
    fingerprint = payload.get("family_fingerprint")
    if not isinstance(fingerprint, str) or not _SHA256_PATTERN.match(fingerprint):
        raise FamilyV3Error("family_fingerprint 必须是 64 位小写十六进制 sha256")
    expected_prereg_id = f"p4ra-prereg-v3-{fingerprint[:16]}"
    if payload.get("prereg_id") != expected_prereg_id:
        raise FamilyV3Error(f"prereg_id 必须为 {expected_prereg_id!r}（与 family_fingerprint 关联）")
    prereg_version = payload.get("family_version")
    if prereg_version == FAMILY_VERSION:
        if payload.get("task_family_version") != TASK_FAMILY_VERSION:
            raise FamilyV3Error("v4 prereg 缺少/错误 task_family_version")
        prereg_holdout_seed = _validate_holdout_seed(payload.get("holdout_seed"))
        if prereg_holdout_seed != HOLDOUT_SEED:
            raise FamilyV3Error(f"v4 prereg holdout_seed 必须为 {HOLDOUT_SEED}")
        if list(payload.get("holdout_splits", ())) != list(HOLDOUT_SPLITS):
            raise FamilyV3Error("v4 prereg holdout_splits 不符")
        if int(payload.get("holdout_task_count", -1)) != HOLDOUT_TASK_COUNT:
            raise FamilyV3Error("v4 prereg holdout_task_count 不符")
    elif prereg_version in LEGACY_FAMILY_VERSIONS:
        if "holdout_seed" in payload or "holdout_splits" in payload:
            raise FamilyV3Error("legacy v3 prereg 不得携带 v4 holdout 字段")
    else:
        raise FamilyV3Error(f"prereg family_version 非法: {prereg_version!r}")
    created = _validate_iso8601_utc(payload.get("created_utc"), "created_utc")
    frozen_utc = _validate_iso8601_utc(payload.get("frozen_at_utc"), "frozen_at_utc")
    if created != frozen_utc:
        raise FamilyV3Error("prereg created_utc 与 frozen_at_utc 必须一致")
    split_counts = payload.get("split_counts")
    if not isinstance(split_counts, Mapping) or dict(split_counts) != dict(SPLIT_COUNTS):
        raise FamilyV3Error("prereg split_counts 不符")
    task_counts = payload.get("task_counts")
    if not isinstance(task_counts, Mapping) or dict(task_counts) != dict(SPLIT_COUNTS):
        raise FamilyV3Error("prereg task_counts 不符（必须与 split_counts 一致，meta_test=20）")
    split_digest = payload.get("split_digest")
    split_hash = payload.get("split_hash")
    if not isinstance(split_digest, str) or not _SHA256_PATTERN.match(split_digest):
        raise FamilyV3Error("split_digest 必须是 64 位小写十六进制 sha256")
    if split_hash != split_digest:
        raise FamilyV3Error("split_hash 别名必须等于 split_digest")
    if payload.get("task_id_regex") != TASK_ID_PATTERN.pattern:
        raise FamilyV3Error("task_id_regex 必须精确等于合同冻结字面量")
    if payload.get("task_id_pattern") != TASK_ID_PATTERN.pattern:
        raise FamilyV3Error("task_id_pattern 别名必须等于 task_id_regex")
    if payload.get("task_id_namespace") != TASK_ID_PREFIX:
        raise FamilyV3Error("task_id_namespace 不符")
    if normalize_endpoints(tuple(payload.get("primary_endpoints", ()))) != list(PRIMARY_ENDPOINTS):
        raise FamilyV3Error("prereg primary_endpoints 不符（禁止别名）")
    metrics = _normalize_string_list(payload.get("secondary_metrics"), "secondary_metrics")
    if metrics != list(SECONDARY_METRICS):
        raise FamilyV3Error(f"secondary_metrics 必须为 {list(SECONDARY_METRICS)}")
    if list(payload.get("secondary_endpoints", ())) != list(SECONDARY_ENDPOINTS):
        raise FamilyV3Error("secondary_endpoints 别名不符")
    if tuple(payload.get("arms", ())) != ARM_IDS:
        raise FamilyV3Error(f"prereg arms 必须为 {ARM_IDS}")
    if tuple(payload.get("budgets", ())) != BUDGETS:
        raise FamilyV3Error(f"prereg budgets 必须为 {BUDGETS}")
    if tuple(payload.get("k_values", ())) != K_VALUES:
        raise FamilyV3Error(f"prereg k_values 必须为 {K_VALUES}")
    if int(payload.get("initial_design_count", -1)) != INITIAL_DESIGN_COUNT:
        raise FamilyV3Error("prereg initial_design_count 不符")
    if int(payload.get("physical_call_count", -1)) != 0:
        raise FamilyV3Error("prereg physical_call_count 必须为 0")
    if payload.get("evaluator") != "synthetic-analytic":
        raise FamilyV3Error("prereg evaluator 必须是 synthetic-analytic")
    if payload.get("physics_validation_status") != "NOT_APPLICABLE":
        raise FamilyV3Error("prereg physics_validation_status 必须是 NOT_APPLICABLE")
    if not payload.get("meta_test_tuning_policy"):
        raise FamilyV3Error("prereg 缺少 meta_test 调参禁止声明")
    bf = _budget_fairness_module()
    budget_plan = payload.get("budget_plan")
    if not isinstance(budget_plan, Mapping):
        raise FamilyV3Error("budget_plan 必须是 object")
    budget_plans = bf.build_all_budget_plans()
    bf.assert_budget_fairness(budget_plans)
    if int(budget_plan.get("plan_count", -1)) != len(budget_plans):
        raise FamilyV3Error("budget_plan.plan_count 不符")
    if budget_plan.get("plans_digest") != digest(budget_plans):
        raise FamilyV3Error("budget_plan.plans_digest 重算不一致")
    if budget_plan.get("schema_version") != bf.FAIRNESS_SCHEMA_VERSION:
        raise FamilyV3Error("budget_plan.schema_version 不符")
    if tuple(budget_plan.get("arms", ())) != ARM_IDS:
        raise FamilyV3Error("budget_plan.arms 不符")
    if tuple(budget_plan.get("budgets", ())) != BUDGETS:
        raise FamilyV3Error("budget_plan.budgets 不符")
    if tuple(budget_plan.get("k_values", ())) != K_VALUES:
        raise FamilyV3Error("budget_plan.k_values 不符")
    if int(budget_plan.get("initial_designs", -1)) != INITIAL_DESIGN_COUNT:
        raise FamilyV3Error("budget_plan.initial_designs 不符")
    if budget_plan.get("support_counted") is not True:
        raise FamilyV3Error("budget_plan.support_counted 必须为 True（K 个支持评价计入 B）")
    expected_clone_pairs = [
        {"K": 0, "clone_arm": bf.K0_CLONE_ARM, "canonical_arm": bf.ZERO_SHOT_ARM}
    ]
    if [dict(item) for item in budget_plan.get("clone_pairs", ())] != expected_clone_pairs:
        raise FamilyV3Error("budget_plan.clone_pairs 必须登记 K=0 的 FOMAML-KSHOT-BO=CLONE")
    if budget_plan.get("inference_excluded", {}).get("0") != [bf.K0_CLONE_ARM]:
        raise FamilyV3Error("budget_plan.inference_excluded 必须排除 K=0 CLONE 臂")
    seeds = payload.get("seeds")
    if not isinstance(seeds, Mapping) or set(seeds) != {"meta_train_seeds", "optimization_seeds"}:
        raise FamilyV3Error("seeds 必须是仅含 meta_train_seeds/optimization_seeds 的 object")
    meta_train_seeds = [int(value) for value in seeds["meta_train_seeds"]]
    optimization_seeds = [int(value) for value in seeds["optimization_seeds"]]
    if len(meta_train_seeds) < 3 or len(set(meta_train_seeds)) != len(meta_train_seeds):
        raise FamilyV3Error("seeds.meta_train_seeds 至少 3 个且不得重复")
    if len(optimization_seeds) < 10 or len(set(optimization_seeds)) != len(optimization_seeds):
        raise FamilyV3Error("seeds.optimization_seeds 至少 10 个且不得重复")
    if list(payload.get("optimization_seeds", ())) != optimization_seeds:
        raise FamilyV3Error("optimization_seeds 别名必须等于 seeds.optimization_seeds")
    if list(payload.get("meta_seeds", ())) != meta_train_seeds:
        raise FamilyV3Error("meta_seeds 别名必须等于 seeds.meta_train_seeds")
    rules = normalize_stopping_rules(payload.get("stopping_rules"))
    if list(payload.get("stopping_rules", ())) != rules:
        raise FamilyV3Error("stopping_rules 必须已 strip 为规范 list[str]")
    _normalize_string_list(payload.get("failure_rules"), "failure_rules")
    multiple = _validate_multiple_comparison(payload.get("multiple_comparison"))
    plan = _validate_analysis_plan(payload.get("analysis_plan"))
    plan_digest = payload.get("analysis_plan_digest")
    if not isinstance(plan_digest, str) or not _SHA256_PATTERN.match(plan_digest):
        raise FamilyV3Error("analysis_plan_digest 必须是 64 位小写十六进制 sha256")
    if digest(plan) != plan_digest:
        raise FamilyV3Error("analysis_plan_digest 重算不一致")
    if plan.get("multiple_comparison") != multiple:
        raise FamilyV3Error("analysis_plan.multiple_comparison 与 prereg 不一致")
    if frozen_family is not None:
        verify_frozen_family_v3(frozen_family)
        if payload.get("frozen_family_sha256") != frozen_family.get("sha256"):
            raise FamilyV3Error("prereg 未正确绑定 frozen_family sha256")
        for name in (
            "family_id",
            "family_version",
            "formula_version",
            "family_seed",
            "family_fingerprint",
            "radius_base",
            "reference_solution",
            "gap_definition",
            "meta_test_tuning_policy",
        ):
            if payload.get(name) != frozen_family.get(name):
                raise FamilyV3Error(f"prereg 与 frozen 的 {name} 不一致")
        if payload.get("family_version") == FAMILY_VERSION:
            for name in (
                "task_family_version",
                "holdout_seed",
                "holdout_splits",
                "holdout_task_count",
            ):
                if payload.get(name) != frozen_family.get(name):
                    raise FamilyV3Error(f"prereg 与 frozen 的 {name} 不一致")
        frozen_split_hash = frozen_family.get("split", {}).get("split_hash")
        if payload.get("split_digest") != frozen_split_hash:
            raise FamilyV3Error("prereg 与 frozen 的 split_hash 不一致")
        if split_digest != digest(_split_hash_payload(frozen_family["split"]["task_ids"])):
            raise FamilyV3Error("split_digest 与 frozen split task_ids 重算不一致")
        if dict(payload.get("split_counts", {})) != dict(frozen_family["split"]["counts"]):
            raise FamilyV3Error("prereg 与 frozen 的 split counts 不一致")
    return True


def compute_prereg_digest(payload: Mapping[str, Any]) -> str:
    """公开辅助：重算 prereg 自身 digest（prereg_digest 置空）。"""
    return _prereg_digest(payload)


# ---------------------------------------------------------------------------
# 双 digest manifest 与冻结包组装
# ---------------------------------------------------------------------------
def build_digest_manifest(
    artifacts: Sequence[Mapping[str, Any]], *, created_utc: str
) -> dict[str, Any]:
    """汇总各冻结产物的 canonical/raw 双 digest（供确定性重跑逐位比对）。"""
    _validate_iso8601_utc(created_utc, "created_utc")
    entries = []
    for artifact in artifacts:
        entry = {key: artifact[key] for key in ("path", "bytes", "canonical_sha256", "raw_sha256")}
        if artifact.get("stored_sha256") is not None:
            entry["stored_sha256"] = artifact["stored_sha256"]
        entries.append(entry)
    payload: dict[str, Any] = {
        "schema_version": DIGEST_MANIFEST_SCHEMA_VERSION,
        "created_utc": created_utc,
        "family_id": FAMILY_ID,
        "family_version": FAMILY_VERSION,
        "artifacts": entries,
    }
    return payload


def build_freeze_bundle(
    *,
    config: tf.TaskFamilyConfig | None = None,
    run_id: str,
    git_sha: str,
    created_utc: str,
    code_sha: str | None = None,
    legacy_paths: Sequence[str | Path] = (),
    legacy: Mapping[str, Any] | None = None,
    calibration_status: str = "PENDING_A2_CALIBRATION",
    radius_base: float | None = None,
    holdout_seed: int | None = HOLDOUT_SEED,
    v3_reference_task_fingerprints: Sequence[str] = (),
) -> dict[str, Any]:
    """一次构造 tasks/split/frozen/prereg/isolation 五个载荷（不写盘，纯确定性）。

    radius_base：A2 校准后冻结值由 CLI 显式传入（R-02 = 0.64）；config=None 时用它
    构造 v3 配置，config 已提供时必须一致（否则 fail-closed）。
    """
    if legacy is None:
        if not legacy_paths:
            raise FamilyV3Error("build_freeze_bundle 必须提供 legacy_paths 或 legacy 集合（零交集断言）")
        legacy = collect_legacy_task_ids(legacy_paths)
    if config is None:
        overrides: dict[str, Any] = {}
        if radius_base is not None:
            overrides["radius_base"] = float(radius_base)
        family_config = build_v3_family_config(**overrides)
    else:
        family_config = config
        if radius_base is not None and abs(float(radius_base) - float(family_config.radius_base)) > 1e-12:
            raise FamilyV3Error("radius_base 参数与 config.radius_base 不一致")
    assert_family_v3_identity(family_config)
    selected_radius = float(family_config.radius_base)
    if holdout_seed is not None:
        _validate_holdout_seed(holdout_seed)
        if holdout_seed != HOLDOUT_SEED:
            raise FamilyV3Error(f"冻结包 holdout_seed 必须为 {HOLDOUT_SEED}，实际 {holdout_seed}")
        reference_fps = [str(value) for value in v3_reference_task_fingerprints]
        if len(reference_fps) != TOTAL_TASKS:
            raise FamilyV3Error(
                "v4 冻结包必须提供 v3 官方包 120 个参考 task_fingerprint（holdout 零交集断言），"
                f"实际 {len(reference_fps)}"
            )
    else:
        reference_fps = []
    tasks = assign_v3_task_ids(tf.build_task_family(family_config, holdout_seed=holdout_seed))
    records = build_task_records(tasks)
    split_manifest = build_split_manifest_v3(
        tasks, family_config=family_config, holdout_seed=holdout_seed
    )
    v3_ids = [record["task_id"] for record in records]
    v3_fps = [record["task_fingerprint"] for record in records]
    holdout_payload: dict[str, Any] | None = None
    if holdout_seed is not None:
        holdout_tasks = [
            task for split in HOLDOUT_SPLITS for task in tasks if task.split == split
        ]
        if len(holdout_tasks) != HOLDOUT_TASK_COUNT:
            raise FamilyV3Error(
                f"holdout 任务数必须是 {HOLDOUT_TASK_COUNT}，实际 {len(holdout_tasks)}"
            )
        holdout_payload = {
            "task_fingerprints": [task_fingerprint(task) for task in holdout_tasks],
            "reference_task_fingerprints": reference_fps,
        }
    isolation_report = build_isolation_report(
        v3_task_ids=v3_ids,
        v3_task_fingerprints=v3_fps,
        legacy=legacy,
        created_utc=created_utc,
        holdout=holdout_payload,
    )
    frozen = build_frozen_family_v3(
        family_config,
        split_manifest=split_manifest,
        holdout_seed=holdout_seed,
        run_id=run_id,
        git_sha=git_sha,
        created_utc=created_utc,
        code_sha=code_sha,
        radius_base=selected_radius,
        calibration_status=calibration_status,
    )
    preregistration = build_preregistration_v3(
        frozen, run_id=run_id, created_utc=created_utc
    )
    verify_split_manifest_v3(split_manifest, tasks=tasks, family_config=family_config)
    verify_isolation_report(isolation_report)
    verify_frozen_family_v3(frozen)
    verify_preregistration_v3(preregistration, frozen)
    return {
        "config": family_config,
        "tasks": tasks,
        "task_records": records,
        "split_manifest": split_manifest,
        "isolation_report": isolation_report,
        "frozen_family": frozen,
        "preregistration": preregistration,
    }
