"""P4 元学习数据合同（MetaSample / 枚举 / split / 归档记录）。

设计依据：docs/planning/p4_meta_learning_design_20261102.md v1.1 §3.2/§3.3/§5.2/§6。

边界：本模块不导入 evaluation.low_fidelity、RCAIDE Mission、OpenVSP/VSPAERO/SU2/Gmsh
任何调用面；真实 evaluator 只允许 fail-closed 抛错。
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

__all__ = [
    "DataContractError",
    "SOURCE_KINDS",
    "PHYSICS_STATUSES",
    "SPLITS",
    "LABEL_STATUSES",
    "EXCLUDED_STATUSES",
    "EVALUATOR_ID_PATTERN",
    "CONSTRAINT_NAMES",
    "OBJECTIVE_NAME",
    "FEASIBILITY_TOLERANCE",
    "DESIGN_SET",
    "DESIGN_NAMES",
    "DESIGN_LOWER",
    "DESIGN_UPPER",
    "CONTEXT_NAMES",
    "MetaSample",
    "validate_split",
    "validate_sample",
    "require_valid",
    "split_by_task",
    "assert_task_disjoint",
    "support_query_split",
    "from_ledger_row",
    "to_archive_records",
    "archive_target_names",
    "ARCHIVE_SPLITS",
    "ARCHIVE_SPLIT_MAP",
    "archive_split_for",
    "to_archive_splits",
    "design_to_normalized",
    "design_from_normalized",
]

# ---------------------------------------------------------------------------
# 枚举与常量（与 maml_opt/data/dataset.py:14/:17 与 evaluation/contract.py 对齐）
# ---------------------------------------------------------------------------
SOURCE_KINDS = ("synthetic", "archived_real_lf", "validated_real_lf", "validated_real_hf")
PHYSICS_STATUSES = ("NOT_APPLICABLE", "NOT_VALIDATED", "PARTIAL", "VALIDATED")
SPLITS = ("meta_train", "meta_validation", "meta_test", "meta_test_ood", "negative_control")
LABEL_STATUSES = ("VALID", "FEASIBLE", "INFEASIBLE")
EXCLUDED_STATUSES = (
    "INVALID",
    "GEOMETRY_INVALID",
    "MISSION_FAILED",
    "MISSION_NOT_CONVERGED",
    "NONFINITE",
    "PARTIAL_RESULT",
)
EVALUATOR_ID_PATTERN = "<source_kind>__<fidelity>__<design_set>__<version>"
DESIGN_SET = "12d_lifting_surfaces"
# 离线合成阶段物理调用数硬约定（§1.3）：启动/结束双重断言
PHYSICAL_CALL_COUNT = 0
PHYSICS_GUARD_EXPECTED = 0

OBJECTIVE_NAME = "fuel_burn_kg"
FEASIBILITY_TOLERANCE = 1e-12
# 10 项物理约束名（顺序冻结，与 research/concorde_metaopt/evaluation/contract.py 一致）
CONSTRAINT_NAMES = (
    "geometry_invalid",
    "task_mass_balance",
    "fuel_capacity_excess",
    "zero_fuel_excess",
    "takeoff_excess",
    "fuel_remaining_deficit",
    "max_throttle",
    "cruise_range_error",
    "mission_convergence",
    "trim_attitude_limit",
)
# 12 维设计空间顺序与边界（§2.1；测试断言与 task_family / configs YAML 一致）
DESIGN_NAMES = (
    "wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3",
    "span_location_2", "span_location_3", "chord_ratio_2", "chord_ratio_3",
    "tip_twist", "vertical_tail_area", "vertical_tail_sweep_delta",
)
DESIGN_LOWER = (300.0, 1.5, 62.0, 40.0, 66.0, 0.35, 0.85, 0.30, 0.08, -4.0, 28.0, -10.0)
DESIGN_UPPER = (420.0, 2.2, 72.0, 56.0, 76.0, 0.58, 0.98, 0.50, 0.20, 4.0, 40.0, 10.0)
CONTEXT_NAMES = ("context_1", "context_2")

_DESIGN_LOWER_ARRAY = np.asarray(DESIGN_LOWER, dtype=np.float64)
_DESIGN_UPPER_ARRAY = np.asarray(DESIGN_UPPER, dtype=np.float64)
_EVALUATOR_RE = None
_ISO_UTC_RE = None


class DataContractError(ValueError):
    """数据合同/校验失败（错误信息必须清晰可落盘，不自动修复）。"""


def _evaluator_regex():
    global _EVALUATOR_RE
    if _EVALUATOR_RE is None:
        import re

        _EVALUATOR_RE = re.compile(r"^[a-z0-9_]+__[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+$")
    return _EVALUATOR_RE


def _iso_utc_regex():
    global _ISO_UTC_RE
    if _ISO_UTC_RE is None:
        import re

        _ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$")
    return _ISO_UTC_RE


def validate_split(split: str) -> None:
    """校验 split 枚举；非法值抛 DataContractError（§5.2）。"""
    if not isinstance(split, str) or split not in SPLITS:
        raise DataContractError(f"非法 split: {split!r}，允许 {SPLITS}")


def design_to_normalized(design: Sequence[float]) -> tuple[float, ...]:
    """物理 12 维 -> 单位坐标 u∈[0,1]^12（仅线性缩放，不做按任务统计重标定）。"""
    array = np.asarray(design, dtype=np.float64)
    if array.shape != (len(DESIGN_NAMES),):
        raise DataContractError(f"design 必须是 {len(DESIGN_NAMES)} 维，实际 shape={array.shape}")
    if not np.isfinite(array).all():
        raise DataContractError("design 含非有限值")
    fractions = (array - _DESIGN_LOWER_ARRAY) / (_DESIGN_UPPER_ARRAY - _DESIGN_LOWER_ARRAY)
    return tuple(float(value) for value in fractions)


def design_from_normalized(normalized: Sequence[float]) -> tuple[float, ...]:
    """单位坐标 -> 物理 12 维（唯一解码路径的 numpy 部分；expand 由 design_space 负责）。"""
    array = np.asarray(normalized, dtype=np.float64)
    if array.shape != (len(DESIGN_NAMES),):
        raise DataContractError(f"design_normalized 必须是 {len(DESIGN_NAMES)} 维，实际 shape={array.shape}")
    if not np.isfinite(array).all():
        raise DataContractError("design_normalized 含非有限值")
    if (array < -1e-12).any() or (array > 1.0 + 1e-12).any():
        raise DataContractError("design_normalized 必须位于 [0,1]^12")
    physical = _DESIGN_LOWER_ARRAY + np.clip(array, 0.0, 1.0) * (_DESIGN_UPPER_ARRAY - _DESIGN_LOWER_ARRAY)
    return tuple(float(value) for value in physical)


def _finite_or_none(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


@dataclass(frozen=True)
class MetaSample:
    """单条元学习样本（§3.2 全字段合同）。"""

    task_id: str
    fidelity: str
    evaluator_id: str
    design_set: str
    design: tuple[float, ...]
    design_normalized: tuple[float, ...]
    config_hash: str
    objective: float | None
    constraints: Mapping[str, float | None]
    status: str
    source_kind: str
    physics_validation_status: str
    git_sha: str
    seed: int
    physical_call_count: int
    split: str
    task_context: Mapping[str, float]
    created_utc: str
    design_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "design", tuple(float(v) for v in self.design))
        object.__setattr__(self, "design_normalized", tuple(float(v) for v in self.design_normalized))
        object.__setattr__(self, "task_context", {str(k): float(v) for k, v in dict(self.task_context).items()})
        object.__setattr__(self, "constraints", {str(k): (None if v is None else float(v)) for k, v in dict(self.constraints).items()})
        if not self.design_id:
            object.__setattr__(self, "design_id", _design_id(self.design))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "fidelity": self.fidelity,
            "evaluator_id": self.evaluator_id,
            "design_set": self.design_set,
            "design": list(self.design),
            "design_normalized": list(self.design_normalized),
            "config_hash": self.config_hash,
            "objective": self.objective,
            "constraints": dict(self.constraints),
            "status": self.status,
            "source_kind": self.source_kind,
            "physics_validation_status": self.physics_validation_status,
            "git_sha": self.git_sha,
            "seed": self.seed,
            "physical_call_count": self.physical_call_count,
            "split": self.split,
            "task_context": dict(self.task_context),
            "created_utc": self.created_utc,
            "design_id": self.design_id,
        }


def _design_id(design: Sequence[float]) -> str:
    payload = json.dumps([round(float(v), 12) for v in design], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def validate_sample(sample: MetaSample) -> list[str]:
    """返回错误列表（空列表=通过）；写 archive 前任何错误即整体失败（§5.2）。"""
    errors: list[str] = []

    def add(message: str) -> None:
        errors.append(message)

    if not isinstance(sample, MetaSample):
        return [f"sample 必须是 MetaSample，实际 {type(sample).__name__}"]
    if not isinstance(sample.task_id, str) or not sample.task_id.strip():
        add("task_id 必须是非空字符串")
    if not isinstance(sample.fidelity, str) or not sample.fidelity.strip():
        add("fidelity 必须是非空字符串")
    if sample.design_set != DESIGN_SET:
        add(f"design_set 必须是 {DESIGN_SET!r}，实际 {sample.design_set!r}")
    if not isinstance(sample.evaluator_id, str) or not _evaluator_regex().match(sample.evaluator_id or ""):
        add(f"evaluator_id 不符合同 {EVALUATOR_ID_PATTERN!r}，实际 {sample.evaluator_id!r}")
    elif sample.evaluator_id.split("__")[0] != sample.source_kind:
        add(f"evaluator_id 前缀 source_kind={sample.evaluator_id.split('__')[0]!r} 与 sample.source_kind={sample.source_kind!r} 不一致")
    if len(sample.design) != len(DESIGN_NAMES):
        add(f"design 必须是 {len(DESIGN_NAMES)} 维，实际 {len(sample.design)}")
    elif not all(math.isfinite(v) for v in sample.design):
        add("design 含非有限值")
    if len(sample.design_normalized) != len(DESIGN_NAMES):
        add(f"design_normalized 必须是 {len(DESIGN_NAMES)} 维，实际 {len(sample.design_normalized)}")
    else:
        if not all(math.isfinite(v) for v in sample.design_normalized):
            add("design_normalized 含非有限值")
        elif any(v < -1e-9 or v > 1.0 + 1e-9 for v in sample.design_normalized):
            add("design_normalized 必须位于 [0,1]^12")
        elif len(sample.design) == len(DESIGN_NAMES):
            expected = design_to_normalized(sample.design)
            max_delta = max(abs(a - b) for a, b in zip(expected, sample.design_normalized))
            if max_delta > 1e-9:
                add(f"design 与 design_normalized 不一致（最大偏差 {max_delta:.3e}，容差 1e-9）")
    if not isinstance(sample.config_hash, str) or not sample.config_hash.strip():
        add("config_hash 必须是非空字符串")
    if not isinstance(sample.status, str) or sample.status not in LABEL_STATUSES + EXCLUDED_STATUSES:
        add(f"非法 status: {sample.status!r}，允许 {LABEL_STATUSES + EXCLUDED_STATUSES}")
    if not _finite_or_none(sample.objective):
        add(f"objective 必须是有限数值或 None，实际 {sample.objective!r}")
    if sample.objective is not None and sample.status not in LABEL_STATUSES:
        add(f"objective 非空时 status 必须属于 {LABEL_STATUSES}，实际 {sample.status!r}")
    if not isinstance(sample.constraints, Mapping):
        add("constraints 必须是映射")
    else:
        keys = set(sample.constraints)
        if keys != set(CONSTRAINT_NAMES):
            missing = sorted(set(CONSTRAINT_NAMES) - keys)
            extra = sorted(keys - set(CONSTRAINT_NAMES))
            add(f"constraints 键集合必须恒等于 10 项物理约束名；缺失={missing} 多余={extra}")
        for name, value in dict(sample.constraints).items():
            if not _finite_or_none(value):
                add(f"constraints[{name!r}] 必须是有限数值或 None，实际 {value!r}")
    if not isinstance(sample.source_kind, str) or sample.source_kind not in SOURCE_KINDS:
        add(f"非法 source_kind: {sample.source_kind!r}，允许 {SOURCE_KINDS}")
    if not isinstance(sample.physics_validation_status, str) or sample.physics_validation_status not in PHYSICS_STATUSES:
        add(f"非法 physics_validation_status: {sample.physics_validation_status!r}，允许 {PHYSICS_STATUSES}")
    if sample.source_kind == "synthetic" and sample.physics_validation_status != "NOT_APPLICABLE":
        add("source_kind=synthetic 时 physics_validation_status 必须为 NOT_APPLICABLE")
    if sample.source_kind == "validated_real_hf" and sample.physics_validation_status != "VALIDATED":
        add("source_kind=validated_real_hf 时 physics_validation_status 必须为 VALIDATED")
    if not isinstance(sample.git_sha, str) or not sample.git_sha.strip():
        add("git_sha 必须是非空字符串（未知写 UNKNOWN）")
    if type(sample.seed) is not int or sample.seed < 0:
        add(f"seed 必须是非负整数，实际 {sample.seed!r}")
    if type(sample.physical_call_count) is not int or sample.physical_call_count < 0:
        add(f"physical_call_count 必须是非负整数，实际 {sample.physical_call_count!r}")
    try:
        validate_split(sample.split)
    except DataContractError as exc:
        add(str(exc))
    if not isinstance(sample.task_context, Mapping):
        add("task_context 必须是映射")
    else:
        for name, value in dict(sample.task_context).items():
            if not isinstance(name, str) or not name.strip():
                add("task_context 键必须是非空字符串")
            if not _finite_or_none(value):
                add(f"task_context[{name!r}] 必须是有限数值，实际 {value!r}")
        if sample.source_kind == "synthetic":
            if set(sample.task_context) != set(CONTEXT_NAMES):
                add(f"合成任务 task_context 必须是 {CONTEXT_NAMES}，实际 {sorted(sample.task_context)}")
    if not isinstance(sample.created_utc, str) or not _iso_utc_regex().match(sample.created_utc or ""):
        add(f"created_utc 必须是 ISO-8601 UTC（+00:00），实际 {sample.created_utc!r}")
    return errors


def require_valid(sample: MetaSample) -> None:
    """校验失败即抛 DataContractError（不自动修复；写 archive 前必须调用）。"""
    errors = validate_sample(sample)
    if errors:
        raise DataContractError("样本不满足数据合同：" + "；".join(errors))


def split_by_task(
    samples: Sequence[MetaSample],
    fractions: Mapping[str, float],
    seed: int,
) -> dict[str, list[MetaSample]]:
    """按 task_id 划分 split（同任务不跨集）；fractions 键必须属于 SPLITS 且和为 1。"""
    task_ids = sorted({sample.task_id for sample in samples})
    if not task_ids:
        raise DataContractError("split_by_task 需要至少一个任务")
    if set(fractions) - set(SPLITS):
        raise DataContractError(f"fractions 含非法 split 键: {sorted(set(fractions) - set(SPLITS))}")
    if not fractions:
        raise DataContractError("fractions 不能为空")
    total = sum(float(value) for value in fractions.values())
    if abs(total - 1.0) > 1e-9:
        raise DataContractError(f"fractions 之和必须为 1，实际 {total}")
    if any(float(value) < 0 for value in fractions.values()):
        raise DataContractError("fractions 不能含负数")
    order = list(task_ids)
    random.Random(int(seed)).shuffle(order)
    counts: dict[str, int] = {}
    assigned = 0
    for split, fraction in fractions.items():
        count = int(math.floor(fraction * len(order) + 0.5))
        counts[split] = count
        assigned += count
    # 最大余数修正，保证总数一致
    difference = len(order) - assigned
    ordered_splits = sorted(fractions)
    index = 0
    while difference != 0 and ordered_splits:
        split = ordered_splits[index % len(ordered_splits)]
        step = 1 if difference > 0 else -1
        if counts[split] + step >= 0:
            counts[split] += step
            difference -= step
        index += 1
        if index > 10000:  # pragma: no cover - 防御
            raise DataContractError("fractions 取整修正失败")
    assignment: dict[str, str] = {}
    cursor = 0
    for split in ordered_splits:
        for task_id in order[cursor : cursor + counts[split]]:
            assignment[task_id] = split
        cursor += counts[split]
    result: dict[str, list[MetaSample]] = {split: [] for split in ordered_splits}
    for sample in samples:
        split = assignment.get(sample.task_id)
        if split is None:  # pragma: no cover - 计数已覆盖全部任务
            raise DataContractError(f"任务 {sample.task_id} 未被分配 split")
        result[split].append(sample)
    return result


def assert_task_disjoint(*splits: Any) -> None:
    """断言各集合的 task_id 两两交集为空；支持 mapping[str, Iterable[MetaSample|str]] 或序列。

    非法重叠抛 DataContractError（测试必须 FAIL，不得降级 warning）。
    """
    if not splits:
        raise DataContractError("assert_task_disjoint 至少需要一个集合")
    normalized: list[tuple[str, set[str]]] = []
    for index, item in enumerate(splits):
        if isinstance(item, Mapping):
            for name, values in item.items():
                normalized.append((str(name), _task_ids_of(values)))
        else:
            normalized.append((f"split[{index}]", _task_ids_of(item)))
    for i in range(len(normalized)):
        for j in range(i + 1, len(normalized)):
            overlap = normalized[i][1] & normalized[j][1]
            if overlap:
                raise DataContractError(
                    f"任务 split 泄漏：{normalized[i][0]} 与 {normalized[j][0]} 共享 task_id {sorted(overlap)}"
                )


def _task_ids_of(values: Any) -> set[str]:
    if isinstance(values, str):
        return {values}
    result = set()
    for value in values:
        if isinstance(value, MetaSample):
            result.add(value.task_id)
        elif isinstance(value, str):
            result.add(value)
        else:
            raise DataContractError(f"无法从 {type(value).__name__} 提取 task_id")
    return result


def support_query_split(
    samples: Sequence[MetaSample],
    task_id: str,
    k_shot: int,
    query_size: int,
    seed: int,
) -> tuple[list[MetaSample], list[MetaSample]]:
    """任务内 support/query 划分（§6）：query 固定、K 只从 support 池按 seed 置换取前 K。

    - 同一任务同 seed 的 query 集合与 K 无关（跨臂公平）；
    - support 子集嵌套（K 增大只从池内追加），且 support∩query=∅（设计精确比较，容差 1e-12）。
    """
    task_samples = [sample for sample in samples if sample.task_id == task_id]
    if not task_samples:
        raise DataContractError(f"任务 {task_id} 没有样本")
    if type(k_shot) is not int or k_shot < 0:
        raise DataContractError(f"k_shot 必须是非负整数，实际 {k_shot!r}")
    if type(query_size) is not int or query_size < 1:
        raise DataContractError(f"query_size 必须是正整数，实际 {query_size!r}")
    ordered = sorted(task_samples, key=lambda sample: sample.design_id)
    if len(ordered) < query_size + k_shot:
        raise DataContractError(
            f"任务 {task_id} 只有 {len(ordered)} 条样本，不足以切出 query={query_size}+support={k_shot}"
        )
    rng = random.Random(f"{task_id}|{int(seed)}")
    order = list(range(len(ordered)))
    rng.shuffle(order)
    query_indices = order[:query_size]
    pool_indices = order[query_size:]
    query = [ordered[index] for index in query_indices]
    # support 子集嵌套：池先按 design_id 排序，再由独立 seed 置换后取前 K
    pool = sorted((ordered[index] for index in pool_indices), key=lambda sample: sample.design_id)
    pool_order = list(range(len(pool)))
    random.Random(f"{task_id}|{int(seed)}|support_pool").shuffle(pool_order)
    support = [pool[index] for index in pool_order[:k_shot]]
    _assert_designs_disjoint(support, query)
    return support, query


def _assert_designs_disjoint(support: Sequence[MetaSample], query: Sequence[MetaSample]) -> None:
    for left in support:
        for right in query:
            delta = max(abs(a - b) for a, b in zip(left.design_normalized, right.design_normalized))
            if delta <= 1e-12:
                raise DataContractError(
                    f"support/query 设计泄漏：task={left.task_id} design_id={left.design_id}（容差 1e-12）"
                )


def _constraints_vector(mapping: Any) -> dict[str, float | None]:
    if mapping is None:
        return {name: None for name in CONSTRAINT_NAMES}
    if not isinstance(mapping, Mapping):
        raise DataContractError("constraints_g_le_zero 必须是映射")
    unknown = set(mapping) - set(CONSTRAINT_NAMES)
    if unknown:
        raise DataContractError(f"constraints_g_le_zero 含未知约束名: {sorted(unknown)}")
    return {name: (None if mapping.get(name) is None else float(mapping[name])) for name in CONSTRAINT_NAMES}


def from_ledger_row(
    row: Mapping[str, Any],
    *,
    task_id: str,
    config_hash: str,
    git_sha: str,
    source_kind: str,
    physics_validation_status: str,
) -> MetaSample:
    """把 evaluator/ledger 行转换为 MetaSample（失败/无效行 objective 必须 None）。"""
    if not isinstance(row, Mapping):
        raise DataContractError("ledger row 必须是映射")
    design = row.get("design")
    if design is None:
        raise DataContractError("ledger row 缺少 design（物理 12 维）")
    design_tuple = tuple(float(value) for value in design)
    normalized = row.get("design_normalized", row.get("design_u"))
    if normalized is None:
        normalized_tuple = design_to_normalized(design_tuple)
    else:
        normalized_tuple = tuple(float(value) for value in normalized)
    status = row.get("status")
    valid = row.get("valid")
    if status not in LABEL_STATUSES + EXCLUDED_STATUSES:
        if valid is True and row.get("objective") is not None:
            status = "VALID"
        elif valid is False:
            status = "INVALID"
        else:
            raise DataContractError(f"ledger row 的 status 非法：{row.get('status')!r}")
    objective = row.get("objective")
    if objective is not None:
        objective = float(objective)
        if not math.isfinite(objective):
            objective = None
            status = "NONFINITE" if status in LABEL_STATUSES else status
    elif status in LABEL_STATUSES:
        # 标签状态必须带有限目标；否则按失败落盘（不填 0）
        status = "INVALID"
    constraints = _constraints_vector(row.get("constraints_g_le_zero", row.get("constraints")))
    created_utc = row.get("created_utc") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    context = row.get("task_context") or {}
    return MetaSample(
        task_id=str(task_id),
        fidelity=str(row.get("fidelity", "analytic")),
        evaluator_id=str(row.get("evaluator_id", f"{source_kind}__analytic__{DESIGN_SET}__v1")),
        design_set=DESIGN_SET,
        design=design_tuple,
        design_normalized=normalized_tuple,
        config_hash=str(config_hash),
        objective=objective,
        constraints=constraints,
        status=str(status),
        source_kind=str(source_kind),
        physics_validation_status=str(physics_validation_status),
        git_sha=str(git_sha),
        seed=int(row.get("seed", 0)),
        physical_call_count=int(row.get("physical_call_count", 0)),
        split=str(row.get("split", "meta_test")),
        task_context=context,
        created_utc=str(created_utc),
    )


# ---------------------------------------------------------------------------
# 归档 split 映射（Lead M-03 裁决）：内部五值 split，maml_opt schema-2 只有三值
# ---------------------------------------------------------------------------
ARCHIVE_SPLITS = ("train", "validation", "test")
ARCHIVE_SPLIT_MAP: dict[str, str | None] = {
    "meta_train": "train",
    "meta_validation": "validation",
    "meta_test": "test",
    # OOD 任务仅进入归档层的 test 分桶（存储用）；评估 split 语义仍由
    # MetaSample.split=meta_test_ood 保留，任何训练/结论都必须按原 split 过滤。
    "meta_test_ood": "test",
    # 负控制伪任务绝不进 schema-2 归档（Lead M-03）。
    "negative_control": None,
}


def archive_split_for(split: str) -> str | None:
    """内部五值 split -> schema-2 三值 split；negative_control 返回 None（不归档）。"""
    validate_split(split)
    return ARCHIVE_SPLIT_MAP[split]


def to_archive_splits(samples: Sequence[MetaSample]) -> dict[str, list[str]]:
    """按归档三值 split 分组 task_id（保持样本顺序、去重）。

    negative_control 样本被排除；返回的 dict 恒含 train/validation/test 三个键
    （可能为空列表），调用方需保证 train/validation/test 非空（TaskDataset 要求）。
    """
    if not samples:
        raise DataContractError("to_archive_splits 需要至少一条样本")
    grouped: dict[str, list[str]] = {split: [] for split in ARCHIVE_SPLITS}
    for sample in samples:
        require_valid(sample)
        archive_split = archive_split_for(sample.split)
        if archive_split is None:
            continue
        if sample.task_id not in grouped[archive_split]:
            grouped[archive_split].append(sample.task_id)
    return grouped


def archive_target_names(samples: Sequence[MetaSample]) -> tuple[str, ...]:
    """归档 target 名称：objective + 实际启用的约束槽位（未启用槽位不归档，保留 null 语义）。

    说明（CONTRACT_AMBIGUITY A4）：maml_opt schema-2 归档要求 targets 为有限数值，
    因此未启用约束（语义=未启用，不是满足）不写入归档，由 manifest 记录 slot 映射；
    绝不填入 0 冒充满足/不满足。
    """
    enabled: list[str] = []
    for sample in samples:
        for name in CONSTRAINT_NAMES:
            if sample.constraints.get(name) is not None and name not in enabled:
                enabled.append(name)
    return ("objective",) + tuple(enabled)


def to_archive_records(samples: Sequence[MetaSample], source_run_id: str = "p4-synthetic-meta-learning") -> list[dict[str, Any]]:
    """元学习样本 -> maml_opt schema-2 archive records（data_origin=SYNTHETIC_TEST）。"""
    if not samples:
        raise DataContractError("to_archive_records 需要至少一条样本")
    for sample in samples:
        require_valid(sample)
    target_names = archive_target_names(samples)
    context_names = list(CONTEXT_NAMES)
    records: list[dict[str, Any]] = []
    for sample in samples:
        if sample.objective is None:
            raise DataContractError(
                f"任务 {sample.task_id} 的样本 objective 为 null（status={sample.status}），"
                "P4 合成归档不沉淀无标签记录（禁止填 0 伪造目标）"
            )
        missing = [name for name in target_names[1:] if sample.constraints.get(name) is None]
        if missing:
            raise DataContractError(
                f"任务 {sample.task_id} 缺少归档约束值 {missing}（不同任务的启用槽位必须一致）"
            )
        targets = [float(sample.objective)] + [float(sample.constraints[name]) for name in target_names[1:]]
        features = list(sample.design) + [float(sample.task_context[name]) for name in context_names]
        records.append(
            {
                "observation_id": f"{sample.task_id}__{sample.design_id}",
                "task_id": sample.task_id,
                "design_id": sample.design_id,
                "features": features,
                "targets": targets,
                "status": sample.status,
                # analysis_calls 记录“分析评价次数”（合成解析评估=1 次/样本）；
                # physical_call_count 记录真实物理求解调用数（P4-CODE 恒 0）。二者不可混用：
                # maml_opt schema-2 要求 labeled 记录 analysis_calls>=1（CONTRACT_AMBIGUITY A10）。
                "analysis_calls": 1,
                "data_origin": "SYNTHETIC_TEST",
                "provenance": {
                    "source_run_id": source_run_id,
                    "source_record_id": f"{sample.task_id}__{sample.design_id}",
                    "request_id": f"p4-synthetic-{sample.task_id}-{sample.design_id}",
                    "attempt_id": "synthetic-analytic",
                    "backend": {
                        "platform": "SYNTHETIC_ANALYTIC",
                        "version": "p4-task-family-v1",
                        "model_fingerprint": "p4-synthetic-analytic-v1",
                        "data_origin": "SYNTHETIC_TEST",
                    },
                    "fidelity": sample.fidelity,
                    "task_fingerprint": hashlib.sha256(
                        json.dumps(dict(sample.task_context), sort_keys=True).encode("utf-8")
                    ).hexdigest()[:16],
                },
            }
        )
    return records
