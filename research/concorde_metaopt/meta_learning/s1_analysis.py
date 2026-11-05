"""P4 路线A S1 统计分析、冻结/端点/预算强校验与结论层（A6 实现）。

合同依据：
- docs/planning/p4_route_a_s1_execution_plan_20261105.md（v1.0，§4 数据合同、§5 端点、§6 统计、§8 图）
- docs/planning/p4_route_a_s1_statistical_plan_20261105.md（v1.1，预注册比较/阈值/判定）
- docs/planning/p4_route_a_s0_design_contract.md（v1.1，FC-01..13、端点 ID、预算映射）

边界（硬性）：
- 只读取冻结包与 run_records.jsonl，不执行 runner / BO / 任何真实求解器；
- 不 import Mission/SU2/VSPAERO/RCAIDE 等物理链模块；
- 唯一随机性为 bootstrap，固定 seed=20261105，输出确定性；
- fail-closed：冻结/端点/预算/CLONE/物理守卫任一不通过，则不产出聚合结论。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from . import family_v3

# ---------------------------------------------------------------------------
# 合同常量（从冻结的 family_v3 读取，禁止在本模块另造端点/臂名）
# ---------------------------------------------------------------------------
S1_ANALYSIS_SCHEMA_VERSION = "p4ra-s1-analysis-1"
S1_AGGREGATE_SCHEMA_VERSION = "p4ra-s1-aggregate-1"
S1_FIGURE_STATUS_SCHEMA_VERSION = "p4ra-s1-figure-status-1"
S1_ENDPOINT_TABLE_SCHEMA_VERSION = "p4ra-s1-endpoint-table-1"

MAIN_SPLIT = "meta_test"
DESCRIPTIVE_SPLITS = ("meta_test_ood", "negative_control")
RECORD_SPLITS = (MAIN_SPLIT,) + DESCRIPTIVE_SPLITS
SPLIT_CODE_TO_SPLIT = {code: split for split, code in family_v3.SPLIT_CODES.items()}
SPLIT_TO_CODE = dict(family_v3.SPLIT_CODES)

PRIMARY_ENDPOINTS = tuple(family_v3.PRIMARY_ENDPOINTS)
ENDPOINT_ROW_KEYS = tuple(family_v3.ENDPOINT_ROW_KEYS)
FORBIDDEN_ENDPOINT_ALIASES = tuple(family_v3.FORBIDDEN_ENDPOINT_ALIASES)
SECONDARY_ENDPOINTS = tuple(family_v3.SECONDARY_ENDPOINTS)
ARM_IDS = tuple(family_v3.ARM_IDS)
BUDGETS = tuple(int(value) for value in family_v3.BUDGETS)
K_VALUES = tuple(int(value) for value in family_v3.K_VALUES)
INITIAL_DESIGN_COUNT = int(family_v3.INITIAL_DESIGN_COUNT)
META_SEEDS = (0, 1, 2)
OPT_SEEDS = tuple(range(10))
# task-239：冻结身份五项（从冻结包派生；v3 legacy 与 v4 包共用同一分析代码，
# 禁止再把 v3 字面量当作唯一期望）。
IDENTITY_FIELDS = (
    "family_fingerprint",
    "split_hash",
    "prereg_digest",
    "analysis_plan_digest",
    "radius_base",
)
IDENTITY_SOURCE_PACKAGE = "package"
IDENTITY_SOURCE_EXPECTED = "expected_identity"
RADIUS_BASE_TOLERANCE = 1e-12
ALLOWED_FAMILY_VERSIONS = tuple(
    dict.fromkeys((family_v3.FAMILY_VERSION, *family_v3.LEGACY_FAMILY_VERSIONS))
)

# task-250（R-V4-08-01/03/04）：分析模式、正式/探索放行开关与冻结包合规校验。
ANALYSIS_MODE_FORMAL = "formal"
ANALYSIS_MODE_EXPLORATORY = "exploratory"
ANALYSIS_MODES = (ANALYSIS_MODE_FORMAL, ANALYSIS_MODE_EXPLORATORY)
CONFIRMATORY_FAMILY_VERSION = "p4ra-family-v4"
S1_ANALYSIS_LEGACY_PACKAGE = "S1_ANALYSIS_LEGACY_PACKAGE"
S1_ANALYSIS_CODE_SHA_DRIFT = "S1_ANALYSIS_CODE_SHA_DRIFT"
S1_ANALYSIS_PREREG_BLOCK_MISSING = "S1_ANALYSIS_PREREG_BLOCK_MISSING"
S1_ANALYSIS_PREREG_BLOCK_DRIFT = "S1_ANALYSIS_PREREG_BLOCK_DRIFT"
V4C_HOLDOUT_SPLIT_COUNTS = {"meta_test": 20, "meta_test_ood": 10}
V4C_HOLDOUT_TASK_COUNT = 30
V4C_HOLDOUT_PACKAGE_RUN_ID_RE = re.compile(r"^p4ra-s0-[0-9]+-freeze-[0-9]{8}T[0-9]{6}Z$")
V4C_HOLDOUT_PACKAGE_REQUIRED_FIELDS = (
    "run_id",
    "family_version",
    "holdout_seed",
    "split_counts",
    "task_count",
    "frozen_family_sha256",
    "package_path",
)
V4C_C5_POLICY = {
    "mode": "C5_B_STRUCTURAL_IDENTIFIABILITY",
    "overlap_threshold": 0.90,
    "c5_benefit_harm_inference": False,
    "c5_in_holm": False,
    "min_estimable_tasks": 10,
    "below_min_conclusion": "NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY",
}
V4C_STRUCTURAL_IDENTIFIABILITY = {
    "pair_overlap_threshold": 0.90,
    "pair_status_above_threshold": "STRUCTURALLY_IDENTICAL",
    "pair_status_below_threshold": "IDENTIFIABLE",
    "overlap_definition": "交集行数 / 较大集合行数",
    "exclude_from_benefit_harm_inference": True,
    "exclude_from_holm": True,
    "post_hoc_task_exclusion": False,
    "report_structural_exclusion_counts": True,
    "report_c5_estimable_task_count": True,
}
V4C_FLOAT_TOLERANCE = 1e-12


def _freeze_bundle_confirmatory_eligible(bundle: "FrozenBundle") -> bool:
    """R-V4-08-04：确认包必须显式 confirmatory_eligible=true（legacy/S0-2/S0-3 均无此字段）。"""
    observed = []
    for container in (bundle.freeze_summary, bundle.frozen_family, bundle.preregistration):
        if isinstance(container, Mapping) and isinstance(container.get("confirmatory_eligible"), bool):
            observed.append(bool(container["confirmatory_eligible"]))
    return bool(observed) and all(observed)


def _freeze_bundle_code_sha(bundle: "FrozenBundle") -> dict[str, Any]:
    frozen_code = bundle.frozen_family.get("code_sha")
    summary_code = bundle.freeze_summary.get("code_sha")
    return {
        "frozen_family_code_sha": frozen_code if isinstance(frozen_code, str) else None,
        "freeze_summary_code_sha": summary_code if isinstance(summary_code, str) else None,
    }


def _current_analysis_code_sha() -> str:
    """R-V4-08-03：分析进程当前代码的 package_code_sha()（与冻结包同一算法）。"""
    return str(family_v3.package_code_sha())


def _v4c_block_error(code: str, message: str) -> "S1FreezeValidationError":
    return S1FreezeValidationError(f"{code}: {message}")


def _require_v4c_block(prereg: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if name not in prereg:
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_MISSING,
            f"新冻结 prereg 缺必填块 {name}（R-V4-08-02）",
        )
    value = prereg[name]
    if not isinstance(value, Mapping):
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"prereg.{name} 必须是 object，实际 {type(value).__name__}",
        )
    return value


def _check_v4c_expected_fields(block: Mapping[str, Any], expected: Mapping[str, Any], label: str) -> None:
    for key, want in expected.items():
        if key not in block:
            raise _v4c_block_error(
                S1_ANALYSIS_PREREG_BLOCK_MISSING,
                f"{label} 缺字段 {key}（R-V4-08-02）",
            )
        got = block[key]
        if isinstance(want, float):
            if isinstance(got, bool) or not _is_number(got) or abs(float(got) - want) > V4C_FLOAT_TOLERANCE:
                raise _v4c_block_error(
                    S1_ANALYSIS_PREREG_BLOCK_DRIFT,
                    f"{label}.{key} 必须为 {want!r}，实际 {got!r}",
                )
        elif isinstance(want, bool):
            if not isinstance(got, bool) or bool(got) is not want:
                raise _v4c_block_error(
                    S1_ANALYSIS_PREREG_BLOCK_DRIFT,
                    f"{label}.{key} 必须为 {want!r}，实际 {got!r}",
                )
        else:
            if got != want:
                raise _v4c_block_error(
                    S1_ANALYSIS_PREREG_BLOCK_DRIFT,
                    f"{label}.{key} 必须为 {want!r}，实际 {got!r}",
                )


def verify_prereg_v4c_blocks(
    prereg: Mapping[str, Any],
    *,
    frozen: Mapping[str, Any],
    freeze_dir_name: str,
) -> dict[str, Any]:
    """R-V4-08-02：formal 模式强校验 prereg 的四个新块。

    holdout_splits（object）/holdout_package/c5_policy/structural_identifiability；
    任一缺失或漂移均抛 S1FreezeValidationError。
    """
    if not isinstance(prereg, Mapping):
        raise _v4c_block_error(S1_ANALYSIS_PREREG_BLOCK_DRIFT, "prereg 必须是 object")
    blocks = {
        name: _require_v4c_block(prereg, name)
        for name in ("holdout_splits", "holdout_package", "c5_policy", "structural_identifiability")
    }
    # holdout_splits：精确 object {meta_test:20, meta_test_ood:10}，与 split_counts/split task_count 自洽。
    holdout_splits = blocks["holdout_splits"]
    if set(holdout_splits) != set(V4C_HOLDOUT_SPLIT_COUNTS):
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"prereg.holdout_splits 键必须恰为 {sorted(V4C_HOLDOUT_SPLIT_COUNTS)}，实际 {sorted(holdout_splits)}",
        )
    for split_name, expected_count in V4C_HOLDOUT_SPLIT_COUNTS.items():
        value = holdout_splits.get(split_name)
        if isinstance(value, bool) or not _is_int(value) or int(value) != expected_count:
            raise _v4c_block_error(
                S1_ANALYSIS_PREREG_BLOCK_DRIFT,
                f"prereg.holdout_splits.{split_name} 必须为 {expected_count}，实际 {value!r}",
            )
    split_counts = prereg.get("split_counts")
    if isinstance(split_counts, Mapping):
        for split_name, expected_count in V4C_HOLDOUT_SPLIT_COUNTS.items():
            if split_counts.get(split_name) != expected_count:
                raise _v4c_block_error(
                    S1_ANALYSIS_PREREG_BLOCK_DRIFT,
                    f"prereg.split_counts.{split_name} 必须与 holdout_splits 一致（{expected_count}）",
                )
    if sum(int(value) for value in holdout_splits.values()) != V4C_HOLDOUT_TASK_COUNT:
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"holdout_splits 总数必须为 {V4C_HOLDOUT_TASK_COUNT}",
        )
    # holdout_package：run_id/包目录/家族版本/seed/split_counts/task_count/frozen sha/相对路径。
    holdout_package = blocks["holdout_package"]
    for name in V4C_HOLDOUT_PACKAGE_REQUIRED_FIELDS:
        if name not in holdout_package:
            raise _v4c_block_error(
                S1_ANALYSIS_PREREG_BLOCK_MISSING,
                f"prereg.holdout_package 缺字段 {name}",
            )
    run_id = holdout_package.get("run_id")
    if not isinstance(run_id, str) or not V4C_HOLDOUT_PACKAGE_RUN_ID_RE.match(run_id):
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"holdout_package.run_id 不符合 ^p4ra-s0-<n>-freeze-<UTC>Z$: {run_id!r}",
        )
    if run_id != str(freeze_dir_name):
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"holdout_package.run_id 必须等于冻结包目录名 {freeze_dir_name!r}，实际 {run_id!r}",
        )
    if holdout_package.get("family_version") != CONFIRMATORY_FAMILY_VERSION:
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"holdout_package.family_version 必须为 {CONFIRMATORY_FAMILY_VERSION!r}",
        )
    if holdout_package.get("holdout_seed") != prereg.get("holdout_seed"):
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            "holdout_package.holdout_seed 必须与 prereg.holdout_seed 一致",
        )
    package_split_counts = holdout_package.get("split_counts")
    if not isinstance(package_split_counts, Mapping) or dict(package_split_counts) != V4C_HOLDOUT_SPLIT_COUNTS:
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"holdout_package.split_counts 必须为 {V4C_HOLDOUT_SPLIT_COUNTS}",
        )
    if holdout_package.get("task_count") != V4C_HOLDOUT_TASK_COUNT:
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"holdout_package.task_count 必须为 {V4C_HOLDOUT_TASK_COUNT}",
        )
    frozen_sha = frozen.get("sha256")
    if holdout_package.get("frozen_family_sha256") != frozen_sha:
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            "holdout_package.frozen_family_sha256 必须等于 frozen_family.sha256",
        )
    package_path = holdout_package.get("package_path")
    if not isinstance(package_path, str) or not package_path:
        raise _v4c_block_error(S1_ANALYSIS_PREREG_BLOCK_DRIFT, "holdout_package.package_path 必须是非空字符串")
    normalized_path = package_path.replace("\\", "/")
    if normalized_path.startswith("/") or ":" in normalized_path.split("/")[0] or ".." in normalized_path.split("/"):
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"holdout_package.package_path 必须是仓库相对路径（不含盘符/绝对路径）：{package_path!r}",
        )
    if not normalized_path.rstrip("/").endswith(run_id):
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            f"holdout_package.package_path 必须以 run_id {run_id!r} 结尾",
        )
    # c5_policy / structural_identifiability：子集精确匹配（额外字段允许）。
    _check_v4c_expected_fields(blocks["c5_policy"], V4C_C5_POLICY, "prereg.c5_policy")
    _check_v4c_expected_fields(
        blocks["structural_identifiability"],
        V4C_STRUCTURAL_IDENTIFIABILITY,
        "prereg.structural_identifiability",
    )
    # c5_policy 阈值必须与 structural_identifiability 阈值一致。
    c5_threshold = blocks["c5_policy"].get("overlap_threshold")
    structural_threshold = blocks["structural_identifiability"].get("pair_overlap_threshold")
    if isinstance(c5_threshold, bool) or not _is_number(c5_threshold):
        raise _v4c_block_error(S1_ANALYSIS_PREREG_BLOCK_DRIFT, "prereg.c5_policy.overlap_threshold 必须是数值")
    if abs(float(c5_threshold) - float(structural_threshold)) > V4C_FLOAT_TOLERANCE:
        raise _v4c_block_error(
            S1_ANALYSIS_PREREG_BLOCK_DRIFT,
            "c5_policy.overlap_threshold 必须等于 structural_identifiability.pair_overlap_threshold",
        )
    return {
        "holdout_splits": dict(holdout_splits),
        "holdout_package_run_id": run_id,
        "holdout_package_package_path": package_path,
        "c5_policy": dict(blocks["c5_policy"]),
        "structural_identifiability": dict(blocks["structural_identifiability"]),
        "pair_overlap_threshold": float(c5_threshold),
        "c5_in_holm": bool(blocks["c5_policy"].get("c5_in_holm", True)),
        "min_estimable_tasks": int(blocks["c5_policy"].get("min_estimable_tasks", -1)),
    }


def verify_analysis_freeze(
    bundle: "FrozenBundle",
    *,
    analysis_mode: str,
    allow_code_delta: bool = False,
    allow_legacy: bool = False,
) -> dict[str, Any]:
    """R-V4-08-03/04 与 R-V4-08-02：按分析模式强校验冻结包合规性。

    formal：legacy/非确认包、code_sha 漂移、prereg 四块缺失/漂移均 fail-closed。
    exploratory：legacy 需 allow_legacy、code 漂移需 allow_code_delta，四块缺失降级为 warning；不得进入确认统计。
    """
    mode = str(analysis_mode)
    if mode not in ANALYSIS_MODES:
        raise S1AnalysisError(f"analysis_mode 必须属于 {list(ANALYSIS_MODES)}，实际 {analysis_mode!r}")
    family_version = bundle.family_version
    confirmatory_eligible = _freeze_bundle_confirmatory_eligible(bundle)
    is_legacy = (family_version != CONFIRMATORY_FAMILY_VERSION) or (not confirmatory_eligible)
    warnings: list[str] = []
    if is_legacy:
        details = (
            f"family_version={family_version!r}（需 {CONFIRMATORY_FAMILY_VERSION!r}），"
            f"confirmatory_eligible={confirmatory_eligible!r}（需 true）"
        )
        if mode == ANALYSIS_MODE_FORMAL:
            raise _v4c_block_error(
                S1_ANALYSIS_LEGACY_PACKAGE,
                f"formal 模式拒绝 legacy/非确认冻结包（R-V4-08-04）：{details}",
            )
        if not allow_legacy:
            raise _v4c_block_error(
                S1_ANALYSIS_LEGACY_PACKAGE,
                f"exploratory 模式使用 legacy/非确认冻结包必须显式 --allow-legacy：{details}",
            )
        warnings.append(f"legacy/非确认冻结包已由 --allow-legacy 放行（{details}）；本次不得进入确认统计")
    code_shas = _freeze_bundle_code_sha(bundle)
    current_code_sha = _current_analysis_code_sha()
    sha_values = [code_shas["frozen_family_code_sha"], code_shas["freeze_summary_code_sha"], current_code_sha]
    code_sha_ok = all(
        isinstance(value, str) and SHA256_RE.match(value) for value in sha_values
    ) and len(set(sha_values)) == 1
    if not code_sha_ok:
        code_message = (
            f"当前分析代码 package_code_sha()={current_code_sha}，"
            f"frozen_family.code_sha={code_shas['frozen_family_code_sha']}，"
            f"freeze_summary.code_sha={code_shas['freeze_summary_code_sha']}"
        )
        if mode == ANALYSIS_MODE_FORMAL or not allow_code_delta:
            raise _v4c_block_error(
                S1_ANALYSIS_CODE_SHA_DRIFT,
                f"formal 模式要求当前代码与冻结包 code_sha 一致（R-V4-08-03）：{code_message}",
            )
        warnings.append(f"code_sha 漂移已由 --allow-code-delta 放行：{code_message}")
    blocks: dict[str, Any] | None
    blocks_status: str
    try:
        blocks = verify_prereg_v4c_blocks(
            bundle.preregistration,
            frozen=bundle.frozen_family,
            freeze_dir_name=Path(bundle.freeze_dir).name,
        )
        blocks_status = "PASS"
    except S1FreezeValidationError as exc:
        if mode == ANALYSIS_MODE_FORMAL:
            raise
        blocks = None
        blocks_status = "NOT_VERIFIED_EXPLORATORY"
        warnings.append(f"prereg 四块未通过（exploratory 降级）：{exc}")
    confirmatory = bool(mode == ANALYSIS_MODE_FORMAL and not is_legacy and code_sha_ok and blocks is not None)
    return {
        "analysis_mode": mode,
        "confirmatory_eligible": confirmatory,
        "family_version": family_version,
        "confirmatory_package": bool(not is_legacy),
        "legacy_package": bool(is_legacy),
        "allow_legacy": bool(allow_legacy),
        "code_sha": {
            "current_package_code_sha": current_code_sha,
            "frozen_family_code_sha": code_shas["frozen_family_code_sha"],
            "freeze_summary_code_sha": code_shas["freeze_summary_code_sha"],
            "match": bool(code_sha_ok),
            "allow_code_delta": bool(allow_code_delta),
        },
        "prereg_v4c_blocks": {
            "status": blocks_status,
            "required": ["holdout_splits", "holdout_package", "c5_policy", "structural_identifiability"],
            "values": blocks,
            "rule": "R-V4-08-02",
        },
        "warnings": warnings,
    }


def _non_confirmatory_primary(primary: Mapping[str, Any], reason: str) -> dict[str, Any]:
    """R-V4-08-04：非确认分析的主结论必须降为 INCONCLUSIVE，不得进入确认统计。"""
    result = dict(primary)
    result["overall"] = OVERALL_INCONCLUSIVE
    result["confirmatory_eligible"] = False
    result["non_confirmatory_reason"] = reason
    return result



# task-241（A2-V4-B01）：S0-3 v4 冻结包 freeze_summary schema 升为 3。
# 已知 schema 1/2 维持既有校验；schema 3 按 v4 包实际字段逐项严格校验；未知版本 fail-closed。
FREEZE_SUMMARY_SCHEMAS_V1_V2 = ("p4ra-freeze-summary-1", "p4ra-freeze-summary-2")
FREEZE_SUMMARY_SCHEMA_V4 = "p4ra-freeze-summary-3"
ALLOWED_FREEZE_SUMMARY_SCHEMAS = FREEZE_SUMMARY_SCHEMAS_V1_V2 + (FREEZE_SUMMARY_SCHEMA_V4,)
FREEZE_SUMMARY_V4_REQUIRED_FIELDS = (
    "schema_version",
    "created_utc",
    "frozen_at_utc",
    "run_id",
    "git_sha",
    "code_sha",
    "family_id",
    "family_version",
    "family_seed",
    "formula_version",
    "radius_base",
    "calibration_status",
    "task_family_version",
    "holdout_seed",
    "holdout_splits",
    "holdout_task_count",
    "artifacts",
    "digest_manifest",
    "orchestration",
)
FREEZE_SUMMARY_V4_ALLOWED_FIELDS = frozenset(FREEZE_SUMMARY_V4_REQUIRED_FIELDS)
FREEZE_SUMMARY_V4_ORCHESTRATION_FIELDS = frozenset(
    (
        "physical_call_count",
        "family_fingerprint",
        "split_hash",
        "task_family_fingerprint",
        "prereg_digest",
        "analysis_plan_digest",
        "frozen_family_sha256",
        "preregistration_sha256",
        "budget_fairness_report_sha256",
        "isolation_report_sha256",
        "split_counts",
        "task_count",
        "task_id_intersection",
        "holdout_fingerprint_intersection",
        "task_fingerprint_intersection",
        "legacy",
    )
)
V4_HOLDOUT_SPLITS = (MAIN_SPLIT, "meta_test_ood")
V4_CALIBRATION_STATUSES = ("CALIBRATED", "PENDING_A2_CALIBRATION")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


# 预注册比较（C1 为主假设；C2..C5 为次要比较，不得升级为主结论）。
COMPARISONS: tuple[dict[str, str], ...] = (
    {"id": "C1", "arm": "FOMAML-KSHOT-BO", "reference": "PRETRAIN-KSHOT-BO", "role": "primary"},
    {"id": "C2", "arm": "FOMAML-KSHOT-BO", "reference": "RAND-BO", "role": "secondary"},
    {"id": "C3", "arm": "FOMAML-KSHOT-BO", "reference": "DE", "role": "secondary"},
    {"id": "C4", "arm": "PRETRAIN-KSHOT-BO", "reference": "RAND-BO", "role": "secondary"},
    {"id": "C5", "arm": "FOMAML-KSHOT-BO", "reference": "FOMAML-ZERO-BO", "role": "secondary"},
)
COMPARISON_BY_ID = {item["id"]: item for item in COMPARISONS}

# 端点方向：-1 表示越低越好，+1 表示越高越好。
ENDPOINT_DIRECTIONS = {
    "best_feasible_value": -1,
    "gap_to_reference": -1,
    "first_feasible_eval_index": -1,
    "feasible_hit_rate": +1,
}

# 主确认层：B=64、K>0（K=0 被 CLONE 排除）；B=128 为次级复现层，K=1 为探索层。
PRIMARY_CONFIRMATORY_BUDGET = 64
PRIMARY_CONFIRMATORY_KS = (3, 5)
MAIN_POPULATION_BUDGETS = (64, 128)

BOOTSTRAP_SAMPLES = 10000
BOOTSTRAP_SEED = 20261105
CONFIDENCE_LEVEL = 0.95
ALPHA = 0.05
WILCOXON_MIN_PAIRS = 10
NULL_RATE_INCONCLUSIVE = 0.70
HIT_RATE_ABSOLUTE_THRESHOLD = 0.05
RELATIVE_IMPROVEMENT_THRESHOLD = 0.01

# run_records 必填字段（合同 §4 表格）。
RECORD_REQUIRED_FIELDS = (
    "run_id",
    "run_group_id",
    "family_version",
    "family_fingerprint",
    "split_hash",
    "prereg_digest",
    "analysis_plan_digest",
    "split",
    "task_id",
    "arm",
    "budget_B",
    "K",
    "initial_designs",
    "bo_calls",
    "meta_seed",
    "opt_seed",
    "identifiability",
    "billable_evals",
    "support_evals",
    "initial_evals",
    "bo_evals",
    "endpoint_values",
    "fallback_values",
    "cost",
    "physics",
    "status",
    "failure_reason",
    "history_digest",
    "record_digest",
)
FAILURE_REASONS_REQUIRED_FOR = tuple(
    status for status in ("FAILED_BUDGET_MISMATCH", "FAILED_LEAKAGE", "FAILED_NONFINITE", "FAILED_OTHER")
)
RECORD_STATUSES = ("OK",) + FAILURE_REASONS_REQUIRED_FOR
CLONE_IDENTIFIABILITY = "CLONE_OF_FOMAML-ZERO-BO"
IDENTIFIABLE = "IDENTIFIABLE"
# 合同：CLONE 仅允许 K=0 时的 FOMAML-KSHOT-BO（与 FOMAML-ZERO-BO 同构）。
CLONE_ALLOWED = {"K": 0, "arm": "FOMAML-KSHOT-BO", "canonical_arm": "FOMAML-ZERO-BO"}
RUN_ID_RE = re.compile(
    r"^(?P<prefix>.+)--(?P<arm>RAND-BO|PRETRAIN-KSHOT-BO|FOMAML-ZERO-BO|FOMAML-KSHOT-BO|DE)"
    r"--B(?P<B>64|128)--K(?P<K>0|1|3|5)"
    r"--T(?P<task>p4ra-FQE3-v3-(?:TR|VA|TE|OD|NC)-[0-9]{3})"
    r"--MS(?P<ms>[0-2])--OS(?P<os>[0-9])$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

FROZEN_REQUIRED_FILES = (
    "tasks.json",
    "meta_task_split.json",
    "v3_isolation_report.json",
    "frozen_family.json",
    "preregistration.json",
    "budget_fairness_report.json",
    "digest_manifest.json",
    "freeze_summary.json",
)
FROZEN_PAYLOAD_FILES = tuple(name for name in FROZEN_REQUIRED_FILES if name not in ("digest_manifest.json", "freeze_summary.json"))


class S1AnalysisError(ValueError):
    """S1 分析合同违规的基类（错误直接暴露，不静默填充默认值）。"""


class S1FreezeValidationError(S1AnalysisError):
    """冻结包校验失败（hash/回显/身份/端点/预算任一不符）。"""


class S1RecordValidationError(S1AnalysisError):
    """run_records 记录级校验失败。"""


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------
def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return _is_number(value) and math.isfinite(float(value))


def _is_number_or_none(value: Any) -> bool:
    return value is None or _is_finite_number(value)


def _is_int_or_none(value: Any) -> bool:
    return value is None or _is_int(value)


def _is_bool_or_none(value: Any) -> bool:
    return value is None or isinstance(value, bool)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise S1AnalysisError(message)


def _read_json_file(path: Path, label: str) -> tuple[Any, bytes]:
    if not path.is_file():
        raise S1FreezeValidationError(f"冻结包缺少 {label}：{path.name}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise S1FreezeValidationError(f"{label} 不是 UTF-8：{exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise S1FreezeValidationError(f"{label} 不是合法 JSON：{exc}") from exc
    return payload, raw


def _raw_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_artifact_digest(payload: Any) -> str:
    """冻结产物 canonical digest：对象剔除 sha256 字段后取 canonical JSON sha256。"""
    if isinstance(payload, Mapping):
        body = {key: value for key, value in payload.items() if key != "sha256"}
        return family_v3.digest(body)
    return family_v3.digest(payload)


def _jsonable(value: Any) -> Any:
    """把 numpy 标量递归转成原生 JSON 类型，保证输出可确定性序列化。"""
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    text = json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _csv_value(row.get(name)) for name in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return repr(value)
    if isinstance(value, (list, tuple)):
        return json.dumps(_jsonable(list(value)), ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        return json.dumps(_jsonable(dict(value)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "" if value is None else value

# ---------------------------------------------------------------------------
# 冻结包加载与三方/五方强校验
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# task-239：冻结身份派生与 expected_identity 校验（v3 legacy / v4 共用）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FrozenIdentity:
    """从冻结包派生出的身份（五项 + family_version）。"""

    family_version: str
    family_fingerprint: str
    split_hash: str
    prereg_digest: str
    analysis_plan_digest: str
    radius_base: float

    def five(self) -> dict[str, Any]:
        """返回五项规范身份字段（expected_identity 的键集合）。"""
        return {name: getattr(self, name) for name in IDENTITY_FIELDS}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"family_version": self.family_version}
        payload.update(self.five())
        return payload


def _identity_digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.match(value):
        raise S1FreezeValidationError(f"{name} 必须是 64 位小写十六进制 sha256，实际 {value!r}")
    return value


def _derive_expected_identity(
    frozen: Mapping[str, Any],
    prereg: Mapping[str, Any],
    split: Mapping[str, Any],
) -> FrozenIdentity:
    """从冻结包载荷派生身份五项；载荷间不一致或类型非法即 fail-closed。

    唯一期望来自冻结包本身；每个载荷的内部自洽性已由 family_v3.verify_* 保证，
    载荷间一致性随后由 _cross_check_echo_chain 交叉校验。
    """
    family_version = frozen.get("family_version")
    if family_version not in ALLOWED_FAMILY_VERSIONS:
        raise S1FreezeValidationError(
            f"冻结包 family_version 非法：{family_version!r}（允许 {list(ALLOWED_FAMILY_VERSIONS)}）"
        )
    frozen_split = frozen.get("split")
    if not isinstance(frozen_split, Mapping):
        raise S1FreezeValidationError("frozen_family.split 必须是 object")
    if frozen_split.get("split_hash") != split.get("split_hash"):
        raise S1FreezeValidationError(
            "frozen_family.split.split_hash 与 meta_task_split.split_hash 不一致"
        )
    radius = frozen.get("radius_base")
    if not _is_finite_number(radius):
        raise S1FreezeValidationError(f"frozen_family.radius_base 必须是有限数，实际 {radius!r}")
    return FrozenIdentity(
        family_version=str(family_version),
        family_fingerprint=_identity_digest(
            frozen.get("family_fingerprint"), "frozen_family.family_fingerprint"
        ),
        split_hash=_identity_digest(
            split.get("split_hash"), "meta_task_split.split_hash"
        ),
        prereg_digest=_identity_digest(
            prereg.get("prereg_digest"), "preregistration.prereg_digest"
        ),
        analysis_plan_digest=_identity_digest(
            frozen.get("analysis_plan_digest"), "frozen_family.analysis_plan_digest"
        ),
        radius_base=float(radius),
    )


def verify_expected_identity(
    identity: FrozenIdentity,
    expected: Mapping[str, Any],
    *,
    source: str = "expected_identity",
) -> tuple[str, ...]:
    """逐项核对调用方提供的期望身份；任一不符/缺字段/未知字段即 fail-closed。

    返回已校验的字段顺序（合同五项，固定 IDENTITY_FIELDS 顺序）。
    """
    if not isinstance(expected, Mapping):
        raise S1FreezeValidationError(f"{source} 必须是 JSON object（Mapping），实际 {type(expected).__name__}")
    provided = set(expected)
    required = set(IDENTITY_FIELDS)
    missing = sorted(required - provided)
    extra = sorted(provided - required)
    if missing or extra:
        raise S1FreezeValidationError(
            f"{source} 字段必须恰为 {list(IDENTITY_FIELDS)}；缺 {missing}，多 {extra}"
        )
    for name in IDENTITY_FIELDS:
        value = expected[name]
        observed = getattr(identity, name)
        if name == "radius_base":
            if not _is_finite_number(value):
                raise S1FreezeValidationError(f"{source}.radius_base 必须是有限数，实际 {value!r}")
            if abs(float(value) - float(observed)) > RADIUS_BASE_TOLERANCE:
                raise S1FreezeValidationError(
                    f"{source}.radius_base 与冻结包不一致：expected={value!r} observed={observed!r}"
                )
        else:
            if not isinstance(value, str) or not SHA256_RE.match(value):
                raise S1FreezeValidationError(
                    f"{source}.{name} 必须是 64 位小写十六进制 sha256，实际 {value!r}"
                )
            if value != observed:
                raise S1FreezeValidationError(
                    f"{source}.{name} 与冻结包不一致：expected={value!r} observed={observed!r}"
                )
    return tuple(IDENTITY_FIELDS)


@dataclass(frozen=True)
class FrozenBundle:
    """已通过 fail-closed 校验的 S1 冻结包（只读内存视图）。"""

    freeze_dir: Path
    frozen_family: Mapping[str, Any]
    preregistration: Mapping[str, Any]
    split_manifest: Mapping[str, Any]
    tasks_payload: Any
    digest_manifest: Mapping[str, Any]
    freeze_summary: Mapping[str, Any]
    budget_fairness_report: Mapping[str, Any]
    identity: FrozenIdentity
    raw_sha256: Mapping[str, str] = field(default_factory=dict)
    canonical_sha256: Mapping[str, str] = field(default_factory=dict)
    sha256sums: Mapping[str, str] = field(default_factory=dict)
    identity_source: str = IDENTITY_SOURCE_PACKAGE
    expected_identity_fields: tuple[str, ...] = ()

    @property
    def family_id(self) -> str:
        return str(self.frozen_family["family_id"])

    @property
    def family_version(self) -> str:
        return str(self.frozen_family["family_version"])

    @property
    def family_fingerprint(self) -> str:
        return str(self.frozen_family["family_fingerprint"])

    @property
    def split_hash(self) -> str:
        return str(self.split_manifest["split_hash"])

    @property
    def prereg_digest(self) -> str:
        return str(self.preregistration["prereg_digest"])

    @property
    def analysis_plan_digest(self) -> str:
        return str(self.preregistration["analysis_plan_digest"])

    @property
    def radius_base(self) -> float:
        return float(self.frozen_family["radius_base"])

    @property
    def split_counts(self) -> dict[str, int]:
        return {str(key): int(value) for key, value in self.split_manifest["counts"].items()}

    @property
    def meta_seeds(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.preregistration["seeds"]["meta_train_seeds"])

    @property
    def opt_seeds(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.preregistration["seeds"]["optimization_seeds"])

    def task_ids_for(self, split: str) -> tuple[str, ...]:
        return tuple(str(value) for value in self.split_manifest["task_ids"][split])

    def all_task_ids(self) -> dict[str, tuple[str, ...]]:
        return {split: self.task_ids_for(split) for split in family_v3.SPLIT_ORDER}

    def expected_echo(self) -> dict[str, Any]:
        """run_records 每行必须逐字回显的冻结字段。"""
        return {
            "family_version": self.family_version,
            "family_fingerprint": self.family_fingerprint,
            "split_hash": self.split_hash,
            "prereg_digest": self.prereg_digest,
            "analysis_plan_digest": self.analysis_plan_digest,
        }

    def expected_endpoint_row_keys(self) -> tuple[str, ...]:
        return ENDPOINT_ROW_KEYS

    def identity_five(self) -> dict[str, Any]:
        """身份五项（family_fingerprint/split_hash/prereg_digest/analysis_plan_digest/radius_base）。"""
        return self.identity.five()

    def identity_payload(self) -> dict[str, Any]:
        """身份记录载荷：五项 + family_version + 来源与已校验字段。"""
        payload = self.identity.to_dict()
        payload["identity_source"] = self.identity_source
        payload["expected_identity_fields"] = list(self.expected_identity_fields)
        return payload

    def identity_csv_row(self) -> dict[str, Any]:
        """s1_freeze_identity.csv 的单行记录。"""
        row: dict[str, Any] = {
            "identity_source": self.identity_source,
            "family_version": self.identity.family_version,
        }
        row.update(self.identity.five())
        row["expected_identity_fields"] = ";".join(self.expected_identity_fields)
        return row


def _parse_sha256sums(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise S1FreezeValidationError(f"冻结包缺少 SHA256SUMS.txt：{path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise S1FreezeValidationError(f"SHA256SUMS.txt 不是 UTF-8：{exc}") from exc
    sums: dict[str, str] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^([0-9a-f]{64}) [ *]([^\s/\\]+)$", stripped)
        if not match:
            raise S1FreezeValidationError(f"SHA256SUMS.txt 第 {lineno} 行格式非法：{line!r}")
        digest_value, name = match.group(1), match.group(2)
        if name in sums:
            raise S1FreezeValidationError(f"SHA256SUMS.txt 重复条目：{name}")
        sums[name] = digest_value
    if not sums:
        raise S1FreezeValidationError("SHA256SUMS.txt 为空")
    return sums


def _verify_digest_manifest(
    manifest: Mapping[str, Any], payloads: Mapping[str, Any], raw: Mapping[str, bytes]
) -> dict[str, dict[str, Any]]:
    if manifest.get("schema_version") != family_v3.DIGEST_MANIFEST_SCHEMA_VERSION:
        raise S1FreezeValidationError(f"digest_manifest schema 不符：{manifest.get('schema_version')!r}")
    manifest_version = manifest.get("family_version")
    if manifest.get("family_id") != family_v3.FAMILY_ID or manifest_version not in ALLOWED_FAMILY_VERSIONS:
        raise S1FreezeValidationError(
            f"digest_manifest 家族身份不符：family_id={manifest.get('family_id')!r} family_version={manifest_version!r}"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise S1FreezeValidationError("digest_manifest.artifacts 必须是 list")
    entries: dict[str, dict[str, Any]] = {}
    for entry in artifacts:
        if not isinstance(entry, Mapping):
            raise S1FreezeValidationError("digest_manifest.artifacts 元素必须是 object")
        path = entry.get("path")
        if not isinstance(path, str) or path not in payloads:
            raise S1FreezeValidationError(f"digest_manifest 引用了未知产物：{path!r}")
        if path in entries:
            raise S1FreezeValidationError(f"digest_manifest 重复产物：{path}")
        for field_name in ("canonical_sha256", "raw_sha256"):
            if not isinstance(entry.get(field_name), str) or not SHA256_RE.match(entry[field_name]):
                raise S1FreezeValidationError(f"digest_manifest.{path}.{field_name} 必须是 64 位小写十六进制")
        if not _is_int(entry.get("bytes")) or int(entry["bytes"]) < 0:
            raise S1FreezeValidationError(f"digest_manifest.{path}.bytes 必须是非负整数")
        actual_raw = _raw_sha256(raw[path])
        if entry["raw_sha256"] != actual_raw:
            raise S1FreezeValidationError(f"digest_manifest.{path}.raw_sha256 与文件实际字节不符")
        if int(entry["bytes"]) != len(raw[path]):
            raise S1FreezeValidationError(f"digest_manifest.{path}.bytes 与文件大小不符")
        canonical = _canonical_artifact_digest(payloads[path])
        if entry["canonical_sha256"] != canonical:
            raise S1FreezeValidationError(f"digest_manifest.{path}.canonical_sha256 重算不一致")
        stored = entry.get("stored_sha256")
        payload_sha = payloads[path].get("sha256") if isinstance(payloads[path], Mapping) else None
        if stored is not None:
            if not isinstance(stored, str) or not SHA256_RE.match(stored):
                raise S1FreezeValidationError(f"digest_manifest.{path}.stored_sha256 非法")
            if payload_sha is not None and stored != payload_sha:
                raise S1FreezeValidationError(f"digest_manifest.{path}.stored_sha256 与载荷 sha256 不符")
        entries[path] = dict(entry)
    expected_paths = set(FROZEN_PAYLOAD_FILES)
    if set(entries) != expected_paths:
        missing = sorted(expected_paths - set(entries))
        extra = sorted(set(entries) - expected_paths)
        raise S1FreezeValidationError(f"digest_manifest 产物清单不符：missing={missing}, extra={extra}")
    return entries


def _verify_sha256sums(sums: Mapping[str, str], base: Path) -> None:
    required = set(FROZEN_REQUIRED_FILES)
    missing = sorted(required - set(sums))
    if missing:
        raise S1FreezeValidationError(f"SHA256SUMS.txt 缺少冻结产物：{missing}")
    for name, expected in sums.items():
        target = base / name
        if not target.is_file():
            raise S1FreezeValidationError(f"SHA256SUMS.txt 引用了不存在的文件：{name}")
        actual = _raw_sha256(target.read_bytes())
        if actual != expected:
            raise S1FreezeValidationError(f"SHA256SUMS.txt 校验失败：{name}（冻结后被修改）")


def _verify_freeze_summary(
    summary: Mapping[str, Any],
    *,
    payloads: Mapping[str, Any],
    raw: Mapping[str, bytes],
    expected_bundle_sha: Mapping[str, str],
) -> None:
    schema_version = summary.get("schema_version")
    if schema_version not in ALLOWED_FREEZE_SUMMARY_SCHEMAS:
        raise S1FreezeValidationError(f"freeze_summary schema 不符：{summary.get('schema_version')!r}")
    if summary.get("family_id") != family_v3.FAMILY_ID:
        raise S1FreezeValidationError("freeze_summary family_id 不符")
    summary_version = summary.get("family_version")
    if summary_version not in ALLOWED_FAMILY_VERSIONS:
        raise S1FreezeValidationError(
            f"freeze_summary family_version 不符：{summary_version!r}（允许 {list(ALLOWED_FAMILY_VERSIONS)}）"
        )
    if int(summary.get("family_seed", -1)) != family_v3.FAMILY_SEED:
        raise S1FreezeValidationError("freeze_summary family_seed 不符")
    if summary.get("formula_version") != family_v3.FORMULA_VERSION:
        raise S1FreezeValidationError("freeze_summary formula_version 不符")
    if not _is_finite_number(summary.get("radius_base")):
        raise S1FreezeValidationError("freeze_summary radius_base 必须是有限数")
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise S1FreezeValidationError("freeze_summary.artifacts 必须是 object")
    for name in FROZEN_PAYLOAD_FILES:
        entry = artifacts.get(name)
        if not isinstance(entry, Mapping):
            raise S1FreezeValidationError(f"freeze_summary.artifacts 缺少 {name}")
        if entry.get("raw_sha256") != _raw_sha256(raw[name]):
            raise S1FreezeValidationError(f"freeze_summary.artifacts.{name}.raw_sha256 不符")
        if entry.get("canonical_sha256") != _canonical_artifact_digest(payloads[name]):
            raise S1FreezeValidationError(f"freeze_summary.artifacts.{name}.canonical_sha256 不符")
        if not _is_int(entry.get("bytes")) or int(entry["bytes"]) != len(raw[name]):
            raise S1FreezeValidationError(f"freeze_summary.artifacts.{name}.bytes 不符")
    dm_ref = summary.get("digest_manifest")
    if isinstance(dm_ref, Mapping):
        if dm_ref.get("raw_sha256") not in (None, _raw_sha256(raw["digest_manifest.json"])):
            raise S1FreezeValidationError("freeze_summary.digest_manifest.raw_sha256 不符")
        expected_canonical = _canonical_artifact_digest(payloads["digest_manifest.json"])
        if dm_ref.get("canonical_sha256") not in (None, expected_canonical):
            raise S1FreezeValidationError("freeze_summary.digest_manifest.canonical_sha256 不符")
    elif isinstance(dm_ref, str):
        if dm_ref not in (_raw_sha256(raw["digest_manifest.json"]), _canonical_artifact_digest(payloads["digest_manifest.json"])):
            raise S1FreezeValidationError("freeze_summary.digest_manifest 引用不符")
    orchestration = summary.get("orchestration")
    if not isinstance(orchestration, Mapping):
        raise S1FreezeValidationError("freeze_summary.orchestration 必须是 object")
    if int(orchestration.get("physical_call_count", -1)) != 0:
        raise S1FreezeValidationError("freeze_summary 记录 physical_call_count 必须为 0")
    checksums = {
        "frozen_family_sha256": "frozen_family.json",
        "preregistration_sha256": "preregistration.json",
        "budget_fairness_report_sha256": "budget_fairness_report.json",
        "isolation_report_sha256": "v3_isolation_report.json",
    }
    for field_name, artifact_name in checksums.items():
        value = orchestration.get(field_name)
        if value != expected_bundle_sha[artifact_name]:
            raise S1FreezeValidationError(f"freeze_summary.orchestration.{field_name} 与实际产物不符")
    for field_name, artifact_name in (("prereg_digest", "preregistration.json"), ("analysis_plan_digest", "frozen_family.json")):
        if not isinstance(orchestration.get(field_name), str):
            raise S1FreezeValidationError(f"freeze_summary.orchestration 缺少 {field_name}")
    expected_split_counts = {split: int(count) for split, count in family_v3.SPLIT_COUNTS.items()}
    observed_counts = {str(key): int(value) for key, value in dict(orchestration.get("split_counts", {})).items()}
    if observed_counts != expected_split_counts:
        raise S1FreezeValidationError(f"freeze_summary.orchestration.split_counts 不符：{observed_counts}")
    if int(orchestration.get("task_count", -1)) != family_v3.TOTAL_TASKS:
        raise S1FreezeValidationError(f"freeze_summary.orchestration.task_count 必须为 {family_v3.TOTAL_TASKS}")
    dm_payload = payloads["digest_manifest.json"]
    if dm_ref is not None:
        expected_dm_raw = _raw_sha256(raw["digest_manifest.json"])
        expected_dm_canonical = _canonical_artifact_digest(dm_payload)
        if isinstance(dm_ref, Mapping):
            if dm_ref.get("raw_sha256") not in (None, expected_dm_raw):
                raise S1FreezeValidationError("freeze_summary.digest_manifest.raw_sha256 不符")
            if dm_ref.get("canonical_sha256") not in (None, expected_dm_canonical):
                raise S1FreezeValidationError("freeze_summary.digest_manifest.canonical_sha256 不符")
            if dm_ref.get("bytes") is not None and int(dm_ref["bytes"]) != len(raw["digest_manifest.json"]):
                raise S1FreezeValidationError("freeze_summary.digest_manifest.bytes 不符")
    if schema_version == FREEZE_SUMMARY_SCHEMA_V4:
        _verify_freeze_summary_v4(summary, payloads=payloads, raw=raw)


def _verify_freeze_summary_v4(
    summary: Mapping[str, Any],
    *,
    payloads: Mapping[str, Any],
    raw: Mapping[str, bytes],
) -> None:
    """schema 3（S0-3 v4 冻结包）严格校验。

    与 schema 1/2 一样保留通用校验；此处额外按 v4 包实际结构逐项核对字段集合、
    类型以及 freeze_summary 与冻结载荷（frozen_family / meta_task_split /
    preregistration）的一致性，任何缺失、未知或篡改都 fail-closed。
    """
    unknown = sorted(set(summary) - FREEZE_SUMMARY_V4_ALLOWED_FIELDS)
    if unknown:
        raise S1FreezeValidationError(f"freeze_summary(schema 3) 出现未登记字段：{unknown}")
    missing = sorted(set(FREEZE_SUMMARY_V4_REQUIRED_FIELDS) - set(summary))
    if missing:
        raise S1FreezeValidationError(f"freeze_summary(schema 3) 缺少字段：{missing}")

    frozen = payloads["frozen_family.json"]
    split = payloads["meta_task_split.json"]
    prereg = payloads["preregistration.json"]
    if not isinstance(frozen, Mapping) or not isinstance(split, Mapping) or not isinstance(prereg, Mapping):
        raise S1FreezeValidationError("freeze_summary(schema 3) 依赖的冻结载荷不是 object")

    def require_str(field: str) -> str:
        value = summary.get(field)
        if not isinstance(value, str) or not value:
            raise S1FreezeValidationError(f"freeze_summary(schema 3).{field} 必须是非空字符串")
        return value

    def require_str_field(container: Mapping[str, Any], field: str, where: str) -> str:
        value = container.get(field)
        if not isinstance(value, str) or not value:
            raise S1FreezeValidationError(f"{where}.{field} 必须是非空字符串")
        return value

    # 1) 冻结运行标识与时间戳：summary <=> frozen_family <=> preregistration。
    run_id = require_str("run_id")
    for name, payload in (("frozen_family", frozen), ("preregistration", prereg)):
        if payload.get("run_id") != run_id:
            raise S1FreezeValidationError(f"freeze_summary(schema 3).run_id 与 {name} 不一致")
    created_utc = require_str("created_utc")
    for name, payload in (("frozen_family", frozen), ("preregistration", prereg)):
        if payload.get("created_utc") != created_utc:
            raise S1FreezeValidationError(f"freeze_summary(schema 3).created_utc 与 {name} 不一致")
    frozen_at_utc = require_str("frozen_at_utc")
    if frozen_at_utc != prereg.get("frozen_at_utc"):
        raise S1FreezeValidationError("freeze_summary(schema 3).frozen_at_utc 与 preregistration 不一致")
    git_sha = require_str("git_sha")
    if not _HEX40_RE.match(git_sha):
        raise S1FreezeValidationError("freeze_summary(schema 3).git_sha 必须是 40 位小写 hex")
    if git_sha != frozen.get("git_sha"):
        raise S1FreezeValidationError("freeze_summary(schema 3).git_sha 与 frozen_family 不一致")
    code_sha = require_str("code_sha")
    if not SHA256_RE.match(code_sha):
        raise S1FreezeValidationError("freeze_summary(schema 3).code_sha 必须是 64 位小写 hex")
    if code_sha != frozen.get("code_sha"):
        raise S1FreezeValidationError("freeze_summary(schema 3).code_sha 与 frozen_family 不一致")

    # 2) 校准状态：必须与 frozen_family.calibration 一致且属于已知状态。
    calibration_status = require_str("calibration_status")
    if calibration_status not in V4_CALIBRATION_STATUSES:
        raise S1FreezeValidationError(
            f"freeze_summary(schema 3).calibration_status 非法：{calibration_status!r}"
        )
    calibration = frozen.get("calibration")
    if not isinstance(calibration, Mapping) or calibration.get("status") != calibration_status:
        raise S1FreezeValidationError("freeze_summary(schema 3).calibration_status 与 frozen_family 不一致")

    # 3) 家族身份与半径：summary <=> frozen_family（通用校验已核对契约常量）。
    for field in ("family_id", "family_version", "formula_version"):
        if summary.get(field) != frozen.get(field):
            raise S1FreezeValidationError(f"freeze_summary(schema 3).{field} 与 frozen_family 不一致")
    if int(summary.get("family_seed", -1)) != int(frozen.get("family_seed", -2)):
        raise S1FreezeValidationError("freeze_summary(schema 3).family_seed 与 frozen_family 不一致")
    if not _is_finite_number(frozen.get("radius_base")):
        raise S1FreezeValidationError("frozen_family.radius_base 必须是有限数")
    if abs(float(summary["radius_base"]) - float(frozen["radius_base"])) > RADIUS_BASE_TOLERANCE:
        raise S1FreezeValidationError("freeze_summary(schema 3).radius_base 与 frozen_family 不一致")

    # 4) 任务族版本与 holdout 重播种合同（R-V4-01）。
    task_family_version = require_str("task_family_version")
    expected_task_family_version = family_v3.TASK_FAMILY_VERSION
    if task_family_version != expected_task_family_version:
        raise S1FreezeValidationError(
            f"freeze_summary(schema 3).task_family_version 不符：{task_family_version!r}"
        )
    for name, payload in (("frozen_family", frozen), ("meta_task_split", split), ("preregistration", prereg)):
        if payload.get("task_family_version") != expected_task_family_version:
            raise S1FreezeValidationError(f"{name}.task_family_version 不符")
    holdout_seed = summary.get("holdout_seed")
    if not _is_int(holdout_seed) or int(holdout_seed) != int(family_v3.HOLDOUT_SEED):
        raise S1FreezeValidationError(
            f"freeze_summary(schema 3).holdout_seed 必须为 {int(family_v3.HOLDOUT_SEED)}"
        )
    for name, payload in (("frozen_family", frozen), ("meta_task_split", split), ("preregistration", prereg)):
        if int(payload.get("holdout_seed", -1)) != int(holdout_seed):
            raise S1FreezeValidationError(f"{name}.holdout_seed 与 freeze_summary 不一致")
    holdout_splits = summary.get("holdout_splits")
    if not isinstance(holdout_splits, list) or tuple(holdout_splits) != V4_HOLDOUT_SPLITS:
        raise S1FreezeValidationError(
            f"freeze_summary(schema 3).holdout_splits 必须为 {list(V4_HOLDOUT_SPLITS)}"
        )
    for name, payload in (("frozen_family", frozen), ("meta_task_split", split), ("preregistration", prereg)):
        if tuple(payload.get("holdout_splits") or ()) != V4_HOLDOUT_SPLITS:
            raise S1FreezeValidationError(f"{name}.holdout_splits 与 freeze_summary 不一致")
    holdout_task_count = summary.get("holdout_task_count")
    if not _is_int(holdout_task_count) or int(holdout_task_count) <= 0:
        raise S1FreezeValidationError("freeze_summary(schema 3).holdout_task_count 必须是正整数")
    split_counts = split.get("counts")
    if not isinstance(split_counts, Mapping):
        raise S1FreezeValidationError("meta_task_split.counts 必须是 object")
    observed_holdout_count = 0
    for split_name in V4_HOLDOUT_SPLITS:
        if not _is_int(split_counts.get(split_name)):
            raise S1FreezeValidationError(f"meta_task_split.counts 缺少 {split_name}")
        observed_holdout_count += int(split_counts[split_name])
    if observed_holdout_count != int(holdout_task_count):
        raise S1FreezeValidationError(
            "freeze_summary(schema 3).holdout_task_count 与 meta_task_split.counts 之和不一致"
        )
    for name, payload in (("frozen_family", frozen), ("preregistration", prereg)):
        if int(payload.get("holdout_task_count", -1)) != int(holdout_task_count):
            raise S1FreezeValidationError(f"{name}.holdout_task_count 与 freeze_summary 不一致")
    holdout_reseed = frozen.get("holdout_reseed")
    if not isinstance(holdout_reseed, Mapping):
        raise S1FreezeValidationError("frozen_family.holdout_reseed 必须是 object（schema 3 要求显式记录重播种）")
    if int(holdout_reseed.get("holdout_seed", -1)) != int(holdout_seed):
        raise S1FreezeValidationError("frozen_family.holdout_reseed.holdout_seed 与 freeze_summary 不一致")
    if tuple(holdout_reseed.get("holdout_splits") or ()) != V4_HOLDOUT_SPLITS:
        raise S1FreezeValidationError("frozen_family.holdout_reseed.holdout_splits 与 freeze_summary 不一致")
    require_str_field(holdout_reseed, "policy", "frozen_family.holdout_reseed")
    unchanged_splits = holdout_reseed.get("unchanged_splits")
    if not isinstance(unchanged_splits, list) or not unchanged_splits:
        raise S1FreezeValidationError("frozen_family.holdout_reseed.unchanged_splits 必须是非空列表")
    expected_unchanged = sorted(name for name in split_counts if name not in V4_HOLDOUT_SPLITS)
    if sorted(unchanged_splits) != expected_unchanged:
        raise S1FreezeValidationError(
            f"frozen_family.holdout_reseed.unchanged_splits 与 split 集合不一致：{sorted(unchanged_splits)}"
        )

    # 5) artifacts / digest_manifest 块：schema 3 要求带 path 与 stored_sha256，且集合恰好为六个载荷。
    artifacts = summary["artifacts"]
    if not isinstance(artifacts, Mapping):
        raise S1FreezeValidationError("freeze_summary(schema 3).artifacts 必须是 object")
    if set(artifacts) != set(FROZEN_PAYLOAD_FILES):
        raise S1FreezeValidationError(
            f"freeze_summary(schema 3).artifacts 产物清单不符：{sorted(artifacts)}"
        )
    for name in FROZEN_PAYLOAD_FILES:
        entry = artifacts[name]
        if not isinstance(entry, Mapping):
            raise S1FreezeValidationError(f"freeze_summary(schema 3).artifacts.{name} 必须是 object")
        if entry.get("path") != name:
            raise S1FreezeValidationError(f"freeze_summary(schema 3).artifacts.{name}.path 不符")
        stored = entry.get("stored_sha256")
        if stored is not None and (not isinstance(stored, str) or not SHA256_RE.match(stored)):
            raise S1FreezeValidationError(f"freeze_summary(schema 3).artifacts.{name}.stored_sha256 非法")
        payload = payloads[name]
        payload_sha = payload.get("sha256") if isinstance(payload, Mapping) else None
        if payload_sha is not None:
            if stored is None:
                raise S1FreezeValidationError(
                    f"freeze_summary(schema 3).artifacts.{name} 缺少 stored_sha256"
                )
            if stored != payload_sha:
                raise S1FreezeValidationError(
                    f"freeze_summary(schema 3).artifacts.{name}.stored_sha256 与载荷 sha256 不符"
                )
    digest_manifest_ref = summary["digest_manifest"]
    if not isinstance(digest_manifest_ref, Mapping):
        raise S1FreezeValidationError("freeze_summary(schema 3).digest_manifest 必须是 object")
    if digest_manifest_ref.get("path") != "digest_manifest.json":
        raise S1FreezeValidationError("freeze_summary(schema 3).digest_manifest.path 不符")
    if digest_manifest_ref.get("raw_sha256") != _raw_sha256(raw["digest_manifest.json"]):
        raise S1FreezeValidationError("freeze_summary(schema 3).digest_manifest.raw_sha256 不符")
    if digest_manifest_ref.get("canonical_sha256") != _canonical_artifact_digest(
        payloads["digest_manifest.json"]
    ):
        raise S1FreezeValidationError("freeze_summary(schema 3).digest_manifest.canonical_sha256 不符")
    if not _is_int(digest_manifest_ref.get("bytes")) or int(
        digest_manifest_ref["bytes"]
    ) != len(raw["digest_manifest.json"]):
        raise S1FreezeValidationError("freeze_summary(schema 3).digest_manifest.bytes 不符")

    # 6) orchestration 块：逐项核对与载荷一致，并校验交集/血缘断言。
    orchestration = summary["orchestration"]
    if not isinstance(orchestration, Mapping):
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration 必须是 object")
    unknown_orchestration = sorted(set(orchestration) - FREEZE_SUMMARY_V4_ORCHESTRATION_FIELDS)
    missing_orchestration = sorted(FREEZE_SUMMARY_V4_ORCHESTRATION_FIELDS - set(orchestration))
    if unknown_orchestration or missing_orchestration:
        raise S1FreezeValidationError(
            "freeze_summary(schema 3).orchestration 字段集合不符："
            f"missing={missing_orchestration}, unknown={unknown_orchestration}"
        )
    if int(orchestration.get("physical_call_count", -1)) != 0:
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.physical_call_count 必须为 0")
    if orchestration.get("family_fingerprint") != frozen.get("family_fingerprint"):
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.family_fingerprint 不符")
    if not isinstance(orchestration.get("task_family_fingerprint"), str) or not SHA256_RE.match(
        orchestration["task_family_fingerprint"]
    ):
        raise S1FreezeValidationError(
            "freeze_summary(schema 3).orchestration.task_family_fingerprint 必须是 64 位小写 hex"
        )
    if orchestration.get("split_hash") != split.get("split_hash"):
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.split_hash 不符")
    if orchestration.get("prereg_digest") != prereg.get("prereg_digest"):
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.prereg_digest 不符")
    for payload in (frozen, prereg):
        if orchestration.get("analysis_plan_digest") != payload.get("analysis_plan_digest"):
            raise S1FreezeValidationError(
                "freeze_summary(schema 3).orchestration.analysis_plan_digest 不符"
            )
    observed_split_counts = {
        str(key): int(value) for key, value in dict(orchestration.get("split_counts", {})).items()
    }
    expected_split_counts = {split_name: int(count) for split_name, count in split_counts.items()}
    if observed_split_counts != expected_split_counts:
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.split_counts 与 meta_task_split 载荷不符")
    if int(orchestration.get("task_count", -1)) != int(family_v3.TOTAL_TASKS):
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.task_count 不符")
    if split.get("total_tasks") is not None and int(split["total_tasks"]) != int(family_v3.TOTAL_TASKS):
        raise S1FreezeValidationError("meta_task_split.total_tasks 不符")

    task_id_intersection = orchestration.get("task_id_intersection")
    if not isinstance(task_id_intersection, Mapping):
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.task_id_intersection 必须是 object")
    if task_id_intersection.get("status") != "PASS":
        raise S1FreezeValidationError("task_id_intersection.status 必须为 PASS")
    if task_id_intersection.get("assertion") != "TASK_ID_ZERO_INTERSECTION":
        raise S1FreezeValidationError("task_id_intersection.assertion 不符")
    if int(task_id_intersection.get("overlap_count", -1)) != 0:
        raise S1FreezeValidationError("task_id_intersection.overlap_count 必须为 0")

    holdout_intersection = orchestration.get("holdout_fingerprint_intersection")
    if not isinstance(holdout_intersection, Mapping):
        raise S1FreezeValidationError(
            "freeze_summary(schema 3).orchestration.holdout_fingerprint_intersection 必须是 object"
        )
    if holdout_intersection.get("status") != "PASS":
        raise S1FreezeValidationError("holdout_fingerprint_intersection.status 必须为 PASS")
    if holdout_intersection.get("assertion") != "HOLDOUT_FINGERPRINT_ZERO_INTERSECTION":
        raise S1FreezeValidationError("holdout_fingerprint_intersection.assertion 不符")
    if int(holdout_intersection.get("overlap_count", -1)) != 0:
        raise S1FreezeValidationError("holdout_fingerprint_intersection.overlap_count 必须为 0")
    if int(holdout_intersection.get("holdout_task_count", -1)) != int(holdout_task_count):
        raise S1FreezeValidationError("holdout_fingerprint_intersection.holdout_task_count 不符")
    reference_count = holdout_intersection.get("v3_reference_task_fingerprint_count")
    if not _is_int(reference_count) or int(reference_count) < int(family_v3.TOTAL_TASKS):
        raise S1FreezeValidationError(
            "holdout_fingerprint_intersection.v3_reference_task_fingerprint_count 不足"
        )

    task_fp_intersection = orchestration.get("task_fingerprint_intersection")
    if not isinstance(task_fp_intersection, Mapping):
        raise S1FreezeValidationError(
            "freeze_summary(schema 3).orchestration.task_fingerprint_intersection 必须是 object"
        )
    if task_fp_intersection.get("status") not in ("PASS", "NOT_DETERMINABLE"):
        raise S1FreezeValidationError("task_fingerprint_intersection.status 非法")
    if task_fp_intersection.get("assertion") not in (
        "TASK_FINGERPRINT_ZERO_INTERSECTION",
        "TASK_FINGERPRINT_INTERSECTION_UNDETERMINABLE",
    ):
        raise S1FreezeValidationError("task_fingerprint_intersection.assertion 非法")
    if int(task_fp_intersection.get("overlap_count", -1)) != 0:
        raise S1FreezeValidationError("task_fingerprint_intersection.overlap_count 必须为 0")
    if not isinstance(task_fp_intersection.get("evidence_class"), str) or not task_fp_intersection[
        "evidence_class"
    ]:
        raise S1FreezeValidationError("task_fingerprint_intersection.evidence_class 必须是非空字符串")

    legacy = orchestration.get("legacy")
    if not isinstance(legacy, Mapping):
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.legacy 必须是 object")
    legacy_task_count = legacy.get("task_id_count")
    if not _is_int(legacy_task_count) or int(legacy_task_count) < 0:
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.legacy.task_id_count 必须是正整数")
    legacy_fp_count = legacy.get("task_fingerprint_count")
    if not _is_int(legacy_fp_count) or int(legacy_fp_count) < 0:
        raise S1FreezeValidationError(
            "freeze_summary(schema 3).orchestration.legacy.task_fingerprint_count 必须是非负整数"
        )
    legacy_sources = legacy.get("sources")
    if not isinstance(legacy_sources, list) or not legacy_sources:
        raise S1FreezeValidationError("freeze_summary(schema 3).orchestration.legacy.sources 必须是非空列表")
    observed_legacy_ids = 0
    observed_legacy_fps = 0
    for position, source in enumerate(legacy_sources):
        if not isinstance(source, Mapping):
            raise S1FreezeValidationError(f"legacy.sources[{position}] 必须是 object")
        for required_field in ("source", "input_name", "sha256"):
            if not isinstance(source.get(required_field), str) or not source[required_field]:
                raise S1FreezeValidationError(f"legacy.sources[{position}].{required_field} 必须是非空字符串")
        if not SHA256_RE.match(source["sha256"]):
            raise S1FreezeValidationError(f"legacy.sources[{position}].sha256 必须是 64 位小写 hex")
        if not _is_int(source.get("bytes")) or int(source["bytes"]) < 0:
            raise S1FreezeValidationError(f"legacy.sources[{position}].bytes 必须是非负整数")
        for count_field in ("task_id_count", "task_fingerprint_count"):
            if not _is_int(source.get(count_field)) or int(source[count_field]) < 0:
                raise S1FreezeValidationError(
                    f"legacy.sources[{position}].{count_field} 必须是非负整数"
                )
        observed_legacy_ids += int(source["task_id_count"])
        observed_legacy_fps += int(source["task_fingerprint_count"])
    if observed_legacy_ids != int(legacy_task_count):
        raise S1FreezeValidationError(
            "freeze_summary(schema 3).orchestration.legacy.task_id_count 与 sources 之和不一致"
        )
    if observed_legacy_fps != int(legacy_fp_count):
        raise S1FreezeValidationError(
            "freeze_summary(schema 3).orchestration.legacy.task_fingerprint_count 与 sources 之和不一致"
        )


def _verify_budget_fairness(report: Mapping[str, Any]) -> None:
    if report.get("schema_version") != "p4ra-budget-fairness-1":
        raise S1FreezeValidationError(f"budget_fairness_report schema 不符：{report.get('schema_version')!r}")
    if report.get("family_id") != family_v3.FAMILY_ID:
        raise S1FreezeValidationError("budget_fairness_report family_id 不符")
    payload_sha = report.get("sha256")
    if not isinstance(payload_sha, str) or not SHA256_RE.match(payload_sha):
        raise S1FreezeValidationError("budget_fairness_report.sha256 缺失或非法")
    if _canonical_artifact_digest(report) != payload_sha:
        raise S1FreezeValidationError("budget_fairness_report.sha256 自校验失败")
    if tuple(report.get("arms", ())) != ARM_IDS:
        raise S1FreezeValidationError("budget_fairness_report arms 不符")
    if tuple(int(value) for value in report.get("budgets", ())) != BUDGETS:
        raise S1FreezeValidationError("budget_fairness_report budgets 不符")
    if tuple(int(value) for value in report.get("k_values", ())) != K_VALUES:
        raise S1FreezeValidationError("budget_fairness_report k_values 不符")
    if int(report.get("initial_design_count", -1)) != INITIAL_DESIGN_COUNT:
        raise S1FreezeValidationError("budget_fairness_report initial_design_count 不符")
    if int(report.get("physical_call_count", -1)) != 0:
        raise S1FreezeValidationError("budget_fairness_report physical_call_count 必须为 0")
    if report.get("status") not in (None, "PASS"):
        raise S1FreezeValidationError(f"budget_fairness_report status 非 PASS：{report.get('status')!r}")
    clone_pairs = report.get("clone_pairs")
    if isinstance(clone_pairs, list) and clone_pairs:
        expected = {"K": 0, "clone_arm": CLONE_ALLOWED["arm"], "canonical_arm": CLONE_ALLOWED["canonical_arm"]}
        if dict(clone_pairs[0]) != expected:
            raise S1FreezeValidationError(f"budget_fairness_report.clone_pairs 不符：{clone_pairs[0]!r}")
    inference_eligible = report.get("inference_eligible")
    if isinstance(inference_eligible, Mapping):
        eligible = list(inference_eligible.get("0", ()))
        if CLONE_ALLOWED["arm"] in eligible:
            raise S1FreezeValidationError("budget_fairness_report.inference_eligible[0] 不得包含 K=0 CLONE 臂")
        if CLONE_ALLOWED["canonical_arm"] not in eligible:
            raise S1FreezeValidationError("budget_fairness_report.inference_eligible[0] 必须包含 CLONE 的 canonical 臂")
        if len(eligible) != len(ARM_IDS) - 1:
            raise S1FreezeValidationError("budget_fairness_report.inference_eligible[0] 臂数不符")
    if report.get("assertion") != "ALL_ARMS_BILLABLE_EQUALS_B_AND_K_COUNTED":
        raise S1FreezeValidationError("budget_fairness_report assertion 不符")


def _verify_tasks_payload(tasks_payload: Any, split_manifest: Mapping[str, Any]) -> None:
    if not isinstance(tasks_payload, list) or not tasks_payload:
        raise S1FreezeValidationError("tasks.json 必须是非空 list")
    seen: dict[str, str] = {}
    for index, task in enumerate(tasks_payload):
        if not isinstance(task, Mapping):
            raise S1FreezeValidationError(f"tasks.json 第 {index} 项必须是 object")
        task_id = task.get("task_id")
        split = task.get("split")
        if not isinstance(task_id, str) or not family_v3.TASK_ID_PATTERN.match(task_id):
            raise S1FreezeValidationError(f"tasks.json 第 {index} 项 task_id 非法：{task_id!r}")
        if split not in RECORD_SPLITS:
            # 冻结包同时包含 meta_train / meta_validation，任务生成阶段允许，但 run_records 不允许。
            if split not in family_v3.SPLIT_ORDER:
                raise S1FreezeValidationError(f"tasks.json 第 {index} 项 split 非法：{split!r}")
        if task_id in seen:
            raise S1FreezeValidationError(f"tasks.json task_id 重复：{task_id}")
        seen[task_id] = str(split)
    expected_ids = []
    for split in family_v3.SPLIT_ORDER:
        ids = list(split_manifest["task_ids"].get(split, ()))
        if len(ids) != len(set(ids)):
            raise S1FreezeValidationError(f"split_manifest.{split} task_ids 重复")
        expected_ids.extend(ids)
        for task_id in ids:
            if seen.get(task_id) != split:
                raise S1FreezeValidationError(f"tasks.json 中 {task_id} 的 split 与 split_manifest 不符")
    if set(seen) != set(expected_ids):
        raise S1FreezeValidationError("tasks.json 与 split_manifest task_ids 集合不一致（禁止静默改 split）")


def _cross_check_echo_chain(
    frozen: Mapping[str, Any],
    prereg: Mapping[str, Any],
    split: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    raw: Mapping[str, bytes],
    identity: FrozenIdentity | None = None,
) -> None:
    """三方/五方回显一致性：身份五项以冻结包派生值为唯一期望（task-239）。"""
    if identity is None:
        identity = _derive_expected_identity(frozen, prereg, split)
    orchestration = summary["orchestration"]
    family_ids = {
        frozen.get("family_id"),
        prereg.get("family_id"),
        split.get("family_id"),
        summary.get("family_id"),
    }
    if family_ids != {family_v3.FAMILY_ID}:
        raise S1FreezeValidationError(f"五方 family_id 不一致：{family_ids}")
    versions = {
        frozen.get("family_version"),
        prereg.get("family_version"),
        split.get("family_version"),
        summary.get("family_version"),
    }
    if versions != {identity.family_version}:
        raise S1FreezeValidationError(
            f"五方 family_version 不一致：{versions}（期望 {identity.family_version}）"
        )
    fingerprints = {
        frozen.get("family_fingerprint"),
        prereg.get("family_fingerprint"),
        split.get("family_fingerprint"),
        orchestration.get("family_fingerprint"),
    }
    if fingerprints != {identity.family_fingerprint}:
        raise S1FreezeValidationError(
            f"family_fingerprint 回显不一致：{fingerprints}（期望 {identity.family_fingerprint}）"
        )
    frozen_split_hash = frozen.get("split", {}).get("split_hash")
    split_hashes = {frozen_split_hash, prereg.get("split_hash"), split.get("split_hash"), orchestration.get("split_hash")}
    if split_hashes != {identity.split_hash}:
        raise S1FreezeValidationError(
            f"split_hash 回显不一致：{split_hashes}（期望 {identity.split_hash}）"
        )
    if prereg.get("split_digest") != identity.split_hash:
        raise S1FreezeValidationError("prereg.split_digest 与冻结 split_hash 不一致")
    if frozen.get("split", {}).get("manifest_sha256") != _canonical_artifact_digest(split):
        raise S1FreezeValidationError("frozen.split.manifest_sha256 与 split payload 不一致")
    if prereg.get("frozen_family_sha256") != frozen.get("sha256"):
        raise S1FreezeValidationError("prereg.frozen_family_sha256 与 frozen.sha256 不一致")
    prereg_digests = {prereg.get("prereg_digest"), orchestration.get("prereg_digest")}
    if prereg_digests != {identity.prereg_digest}:
        raise S1FreezeValidationError(
            f"prereg_digest 回显不一致：{prereg_digests}（期望 {identity.prereg_digest}）"
        )
    if family_v3.compute_prereg_digest(prereg) != identity.prereg_digest:
        raise S1FreezeValidationError("prereg_digest 重算不一致")
    plan_digests = {
        prereg.get("analysis_plan_digest"),
        frozen.get("analysis_plan_digest"),
        orchestration.get("analysis_plan_digest"),
        identity.analysis_plan_digest,
    }
    if plan_digests != {identity.analysis_plan_digest}:
        raise S1FreezeValidationError(
            f"analysis_plan_digest 回显不一致：{plan_digests}（期望 {identity.analysis_plan_digest}）"
        )
    analysis_plan = prereg.get("analysis_plan")
    if not isinstance(analysis_plan, Mapping) or family_v3.digest(analysis_plan) != identity.analysis_plan_digest:
        raise S1FreezeValidationError("prereg.analysis_plan 与 analysis_plan_digest 不一致")
    endpoint_sets = {
        tuple(frozen.get("endpoint_row_keys", ())),
        tuple(analysis_plan.get("endpoint_row_keys", ())),
        tuple(prereg.get("analysis_plan", {}).get("csv_columns", ())),
        ENDPOINT_ROW_KEYS,
    }
    if endpoint_sets != {ENDPOINT_ROW_KEYS}:
        raise S1FreezeValidationError(f"ENDPOINT_ROW_KEYS 回显不一致：{endpoint_sets}")
    primary_sets = {
        tuple(frozen.get("primary_endpoints", ())),
        tuple(analysis_plan.get("primary_endpoints", ())),
        tuple(prereg.get("primary_endpoints", ())),
        PRIMARY_ENDPOINTS,
    }
    if primary_sets != {PRIMARY_ENDPOINTS}:
        raise S1FreezeValidationError(f"primary_endpoints 回显不一致：{primary_sets}")
    for name, expected in (
        ("arms", ARM_IDS),
        ("budgets", BUDGETS),
        ("k_values", K_VALUES),
    ):
        observed = {
            tuple(frozen.get(name, ())),
            tuple(prereg.get(name, ())),
        }
        plan_values = prereg["budget_plan"].get(name)
        if plan_values:
            observed.add(
                tuple(str(value) for value in plan_values)
                if name == "arms"
                else tuple(int(value) for value in plan_values)
            )
        if observed != {expected}:
            raise S1FreezeValidationError(f"{name} 回显不一致：{observed}")
    if int(frozen.get("initial_design_count", -1)) != INITIAL_DESIGN_COUNT:
        raise S1FreezeValidationError("frozen initial_design_count 不符")
    if int(prereg.get("initial_design_count", -1)) != INITIAL_DESIGN_COUNT:
        raise S1FreezeValidationError("prereg initial_design_count 不符")
    counts = {
        "frozen": {str(key): int(value) for key, value in frozen.get("split", {}).get("counts", {}).items()},
        "split": {str(key): int(value) for key, value in split.get("counts", {}).items()},
        "prereg": {str(key): int(value) for key, value in prereg.get("split_counts", {}).items()},
        "summary": {str(key): int(value) for key, value in orchestration.get("split_counts", {}).items()},
    }
    expected_counts = {split_name: int(count) for split_name, count in family_v3.SPLIT_COUNTS.items()}
    for source, observed in counts.items():
        if observed != expected_counts:
            raise S1FreezeValidationError(f"{source} split counts 与冻结值不符：{observed}")
    radii = {
        float(frozen.get("radius_base", float("nan"))),
        float(split.get("radius_base", float("nan"))),
        float(prereg.get("radius_base", float("nan"))),
        float(summary.get("radius_base", float("nan"))),
        float(orchestration.get("radius_base", identity.radius_base)),
        float(identity.radius_base),
    }
    if len(radii) != 1 or abs(next(iter(radii)) - identity.radius_base) > RADIUS_BASE_TOLERANCE:
        raise S1FreezeValidationError(
            f"radius_base 回显不一致：{radii}（期望 {identity.radius_base}）"
        )
    if int(frozen.get("physical_call_count", -1)) != 0:
        raise S1FreezeValidationError("frozen physical_call_count 必须为 0")
    if int(prereg.get("physical_call_count", -1)) != 0:
        raise S1FreezeValidationError("prereg physical_call_count 必须为 0")
    if int(orchestration.get("physical_call_count", -1)) != 0:
        raise S1FreezeValidationError("freeze_summary physical_call_count 必须为 0")
    legacy_intersection = orchestration.get("task_id_intersection")
    if isinstance(legacy_intersection, Mapping) and legacy_intersection.get("status") not in (None, "PASS"):
        raise S1FreezeValidationError("旧任务族 task_id 零交集断言失败")
    meta_seeds = tuple(int(value) for value in prereg["seeds"]["meta_train_seeds"])
    opt_seeds = tuple(int(value) for value in prereg["seeds"]["optimization_seeds"])
    if meta_seeds != META_SEEDS:
        raise S1FreezeValidationError(f"meta seeds 不符：{meta_seeds}")
    if opt_seeds != OPT_SEEDS:
        raise S1FreezeValidationError(f"optimization seeds 不符：{opt_seeds}")


def load_frozen_bundle(
    freeze_dir: str | Path,
    *,
    verify_checksums: bool = True,
    verify_sha256sums: bool = True,
    expected_identity: Mapping[str, Any] | None = None,
    expected_identity_source: str | None = None,
) -> FrozenBundle:
    """加载并强校验 S1 冻结包；任一不通过抛 S1FreezeValidationError（fail-closed）。

    task-239：身份五项（family_fingerprint/split_hash/prereg_digest/
    analysis_plan_digest/radius_base）默认从冻结包派生（identity_source=package）；
    调用方（正式 run 由 run_config / CLI --expected-identity-json 传入）提供 expected_identity
    时必须逐项相等，否则 fail-closed（identity_source=expected_identity）。
    """
    base = Path(freeze_dir)
    if not base.is_dir():
        raise S1FreezeValidationError(f"冻结包目录不存在：{base}")
    payloads: dict[str, Any] = {}
    raw: dict[str, bytes] = {}
    raw_sha: dict[str, str] = {}
    for name in FROZEN_REQUIRED_FILES:
        payload, raw_bytes = _read_json_file(base / name, name)
        payloads[name] = payload
        raw[name] = raw_bytes
        raw_sha[name] = _raw_sha256(raw_bytes)
    sums: dict[str, str] = {}
    if verify_sha256sums:
        sums = _parse_sha256sums(base / "SHA256SUMS.txt")
        _verify_sha256sums(sums, base)
    entries: dict[str, dict[str, Any]] = {}
    if verify_checksums:
        entries = _verify_digest_manifest(payloads["digest_manifest.json"], payloads, raw)
    expected_bundle_sha = {name: _canonical_artifact_digest(payloads[name]) for name in FROZEN_PAYLOAD_FILES}
    _verify_freeze_summary(payloads["freeze_summary.json"], payloads=payloads, raw=raw, expected_bundle_sha=expected_bundle_sha)
    frozen = payloads["frozen_family.json"]
    prereg = payloads["preregistration.json"]
    split = payloads["meta_task_split.json"]
    # R-V4-08-02/04：旧 S0-3 等只读历史包缺三键，按 legacy schema 校验（由调用层在
    # analysis_mode=exploratory + --allow-legacy 下才允许进入分析；formal 由合规门禁拒绝）。
    legacy_prereg_schema = not all(
        name in prereg for name in ("holdout_package", "c5_policy", "structural_identifiability")
    )
    try:
        family_v3.verify_frozen_family_v3(frozen)
        family_v3.verify_preregistration_v3(
            prereg, frozen_family=frozen, allow_legacy_schema=legacy_prereg_schema
        )
        family_v3.verify_split_manifest_v3(split)
    except family_v3.FamilyV3Error as exc:
        raise S1FreezeValidationError(f"冻结载荷自校验失败：{exc}") from exc
    identity = _derive_expected_identity(frozen, prereg, split)
    provided_identity_fields: tuple[str, ...] = ()
    identity_source = IDENTITY_SOURCE_PACKAGE
    if expected_identity is not None:
        provided_identity_fields = verify_expected_identity(
            identity,
            expected_identity,
            source=expected_identity_source or "expected_identity",
        )
        identity_source = IDENTITY_SOURCE_EXPECTED
    if frozen.get("sha256") != _canonical_artifact_digest(frozen):
        raise S1FreezeValidationError("frozen_family.sha256 自校验失败")
    if prereg.get("sha256") != _canonical_artifact_digest(prereg):
        raise S1FreezeValidationError("preregistration.sha256 自校验失败")
    _verify_budget_fairness(payloads["budget_fairness_report.json"])
    _verify_tasks_payload(payloads["tasks.json"], split)
    _cross_check_echo_chain(
        frozen, prereg, split, payloads["freeze_summary.json"], raw=raw, identity=identity
    )
    canonical_sha = {name: _canonical_artifact_digest(payloads[name]) for name in FROZEN_REQUIRED_FILES}
    return FrozenBundle(
        freeze_dir=base,
        frozen_family=frozen,
        preregistration=prereg,
        split_manifest=split,
        tasks_payload=payloads["tasks.json"],
        digest_manifest=payloads["digest_manifest.json"],
        freeze_summary=payloads["freeze_summary.json"],
        budget_fairness_report=payloads["budget_fairness_report.json"],
        identity=identity,
        raw_sha256=raw_sha,
        canonical_sha256=canonical_sha,
        sha256sums=sums,
        identity_source=identity_source,
        expected_identity_fields=provided_identity_fields,
    )

# ---------------------------------------------------------------------------
# run_records 加载与记录级强校验
# ---------------------------------------------------------------------------
S1_RECORD_SCHEMA_VERSION = "p4ra-s1-run-record-1"
RECORD_KNOWN_FIELDS = set(RECORD_REQUIRED_FIELDS) | {
    "schema_version",
    "clone_of",
    "inference_eligible",
    # B01（task-226）：runner 的 formal 网格写 grid_stratum；分析端必须认识并校验，否则 formal run 无法分析。
    "grid_stratum",
    # B01 续（task-226）：runner 的可辨识性审计（task-227 / S1-B03）写两个可选字段；
    # formal run 记录会携带它们，分析端必须接受并做格式校验，否则仍无法分析。
    "initial_designs_sha256",
    "initial_design_row_digests",
}
FAILURE_REASONS = tuple(FAILURE_REASONS_REQUIRED_FOR)
TRUE_NULL_RATE_TOL = 1e-12

# formal 网格分层（与 s1_runner.py 的 FORMAL_GRID_STRATA 保持一致；此处只做只读校验，不 import runner）。
GRID_STRATUM_NAMES = ("main", "secondary", "exploratory")
GRID_STRATUM_RULES = {
    "main": {"budgets": (64,), "k_values": (0, 3, 5)},
    "secondary": {"budgets": (128,), "k_values": (3, 5)},
    "exploratory": {"budgets": (64, 128), "k_values": (1,)},
}


def expected_grid_stratum(budget_B: int, K: int) -> str | None:
    """按 formal 网格返回 (B,K) 所属分层；不属于 formal 网格返回 None。"""
    for name in GRID_STRATUM_NAMES:
        rule = GRID_STRATUM_RULES[name]
        if int(budget_B) in rule["budgets"] and int(K) in rule["k_values"]:
            return name
    return None


def _validate_grid_stratum(record: Mapping[str, Any], index: int) -> None:
    """B01：grid_stratum 若出现则必须是合法分层且与 (B,K) 一致；缺省/null 兼容 cartesian 记录。"""
    if "grid_stratum" not in record or record.get("grid_stratum") is None:
        return
    value = record.get("grid_stratum")
    if not isinstance(value, str):
        raise S1RecordValidationError(
            f"[{index}] grid_stratum 必须是 str 或 null（实际 {type(value).__name__}）"
        )
    if value not in GRID_STRATUM_NAMES:
        raise S1RecordValidationError(
            f"[{index}] grid_stratum 非法：{value!r}（允许 {GRID_STRATUM_NAMES}）"
        )
    expected = expected_grid_stratum(int(record["budget_B"]), int(record["K"]))
    if expected is None:
        raise S1RecordValidationError(
            f"[{index}] (budget_B={record['budget_B']}, K={record['K']}) 不属于 formal 网格，"
            f"不得登记 grid_stratum={value!r}"
        )
    if value != expected:
        raise S1RecordValidationError(
            f"[{index}] grid_stratum 与 (budget_B,K) 不一致：登记 {value!r}，按 formal 网格应为 {expected!r}"
        )


def _validate_design_identifiability_fields(record: Mapping[str, Any], index: int) -> None:
    """B01 续（task-226）：校验 runner 的可辨识性审计字段（可空，非空必须规范）。

    runner（task-227 / S1-B03）在模型打分臂上写：
    - initial_designs_sha256：新初始设计整体 sha256（64 位小写十六进制）；
    - initial_design_row_digests：逐行 sha256 列表。
    CONTRACT_AMBIGUITY（已报告 Lead）：字段名像「全部初始设计」，但 runner 实际记录的是
    支持集之外的新初始点，行数 = INITIAL_DESIGN_COUNT - K（8 个共享初始点中 K 个用于支持集）；
    因此校验按 8-K 行 fail-closed，而不是固定 8 行。
    analysis 只做格式/行数校验，不重算造型语义（由 runner 负责）。
    """
    prefix = f"[{index}] "
    sha = record.get("initial_designs_sha256")
    if sha is not None:
        if not isinstance(sha, str) or SHA256_RE.match(sha) is None:
            raise S1RecordValidationError(
                prefix + "initial_designs_sha256 必须为 null 或 64 位小写十六进制 sha256"
            )
    rows = record.get("initial_design_row_digests")
    if rows is not None:
        if not isinstance(rows, (list, tuple)):
            raise S1RecordValidationError(
                prefix + "initial_design_row_digests 必须为 null 或 sha256 列表"
            )
        k_shot = record.get("K")
        expected_rows = INITIAL_DESIGN_COUNT - k_shot if _is_int(k_shot) else None
        if expected_rows is None or expected_rows < 0:
            raise S1RecordValidationError(prefix + "K 缺失/非法，无法校验 initial_design_row_digests 行数")
        if len(rows) != expected_rows:
            raise S1RecordValidationError(
                prefix
                + f"initial_design_row_digests 必须为 null 或恰 {expected_rows} 行"
                + f"（INITIAL_DESIGN_COUNT({INITIAL_DESIGN_COUNT}) - K({k_shot})），实际 {len(rows)} 行"
            )
        for row_index, digest in enumerate(rows):
            if not isinstance(digest, str) or SHA256_RE.match(digest) is None:
                raise S1RecordValidationError(
                    prefix
                    + f"initial_design_row_digests[{row_index}] 必须为 64 位小写十六进制 sha256"
                )


@dataclass
class RecordValidation:
    """run_records 校验结果（通过后才允许进入统计层）。"""

    record_count: int
    run_group_ids: list[str]
    counts_by_split: dict[str, int]
    counts_by_arm: dict[str, int]
    counts_by_status: dict[str, int]
    counts_by_budget: dict[str, int]
    counts_by_k: dict[str, int]
    clone_count: int
    failed_count: int
    clone_equivalence_checked: int = 0
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": int(self.record_count),
            "run_group_ids": list(self.run_group_ids),
            "counts_by_split": dict(self.counts_by_split),
            "counts_by_arm": dict(self.counts_by_arm),
            "counts_by_status": dict(self.counts_by_status),
            "counts_by_budget": dict(self.counts_by_budget),
            "counts_by_k": dict(self.counts_by_k),
            "clone_count": int(self.clone_count),
            "failed_count": int(self.failed_count),
            "clone_equivalence_checked": int(self.clone_equivalence_checked),
            "sources": list(self.sources),
        }


def _canonical_record_digest(record: Mapping[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "record_digest"}
    return family_v3.digest(body)


def _discover_run_record_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise S1RecordValidationError(f"run_records 输入不存在：{path}")
    direct = path / "run_records.jsonl"
    if direct.is_file():
        return [direct]
    found = sorted(candidate for candidate in path.rglob("run_records.jsonl") if candidate.is_file())
    if not found:
        raise S1RecordValidationError(f"目录内未找到 run_records.jsonl：{path}")
    return found


def load_run_records(path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    """加载一个 run_records.jsonl，或递归加载目录下所有分片；重复 run_id 直接失败。"""
    target = Path(path)
    sources = [str(item) for item in _discover_run_record_files(target)]
    records: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for source in sources:
        raw = Path(source).read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise S1RecordValidationError(f"run_records 非 UTF-8：{source}：{exc}") from exc
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise S1RecordValidationError(f"{source}:{lineno} 不是合法 JSON：{exc}") from exc
            if not isinstance(record, dict):
                raise S1RecordValidationError(f"{source}:{lineno} 必须是 JSON object")
            run_id = record.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise S1RecordValidationError(f"{source}:{lineno} 缺少 run_id")
            if run_id in seen:
                raise S1RecordValidationError(f"run_id 重复：{run_id}（{seen[run_id]} 与 {source}:{lineno}）")
            seen[run_id] = f"{source}:{lineno}"
            records.append(record)
    if not records:
        raise S1RecordValidationError(f"run_records 为空：{target}")
    return records, sources


def _validate_physics(physics: Any, index: int) -> None:
    if not isinstance(physics, Mapping):
        raise S1RecordValidationError(f"[{index}] physics 必须是 object")
    if int(physics.get("physical_call_count", -1)) != 0:
        raise S1RecordValidationError(f"[{index}] physics.physical_call_count 必须为 0")
    if list(physics.get("physical_call_sources", ())) != []:
        raise S1RecordValidationError(f"[{index}] physics.physical_call_sources 必须为空 list")
    if physics.get("physics_guard") != "PASS":
        raise S1RecordValidationError(f"[{index}] physics.physics_guard 必须为 PASS")


def _validate_finite_json(value: Any, *, index: int, path: str) -> None:
    """校验嵌套成本明细为 JSON 值且数值有限（fail-closed，禁止 NaN/inf）。"""
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise S1RecordValidationError(f"[{index}] {path} 的数值必须有限（实际 {value!r}）")
        return
    if isinstance(value, str):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise S1RecordValidationError(f"[{index}] {path} 的键必须是 str（实际 {key!r}）")
            _validate_finite_json(item, index=index, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for position, item in enumerate(value):
            _validate_finite_json(item, index=index, path=f"{path}[{position}]")
        return
    raise S1RecordValidationError(f"[{index}] {path} 不是合法 JSON 值（{type(value).__name__}）")


def _validate_cost(cost: Any, index: int) -> None:
    if not isinstance(cost, Mapping):
        raise S1RecordValidationError(f"[{index}] cost 必须是 object")
    expected = {"adaptation_wall_s", "proxy_scoring_cost", "peak_memory_mb", "total_wall_s"}
    if set(cost) != expected:
        raise S1RecordValidationError(f"[{index}] cost 键必须为 {sorted(expected)}，实际 {sorted(cost)}")
    for name in expected:
        value = cost[name]
        # CONTRACT_AMBIGUITY（task-226，已报告 Lead）：合同示例把 proxy_scoring_cost 记为数值，
        # 但 runner 在 S1 模型打分臂上写嵌套映射（kind/initial_designs_sha256/model_scoring 明细）。
        # 分析端 fail-closed 地接受「非负有限数 | null | 有限 JSON 映射」，其余照旧拒绝。
        if name == "proxy_scoring_cost" and isinstance(value, Mapping):
            _validate_finite_json(value, index=index, path="cost.proxy_scoring_cost")
            continue
        if value is not None and (not _is_number(value) or not math.isfinite(float(value)) or float(value) < 0):
            raise S1RecordValidationError(f"[{index}] cost.{name} 必须是非负有限数、null 或有限 JSON 映射")


def _validate_endpoint_values(values: Any, *, status: str, budget_B: int, K: int, index: int) -> None:
    if not isinstance(values, Mapping):
        raise S1RecordValidationError(f"[{index}] endpoint_values 必须是 object")
    keys = set(values)
    alias_hits = sorted(set(FORBIDDEN_ENDPOINT_ALIASES) & keys)
    if alias_hits:
        raise S1RecordValidationError(f"[{index}] endpoint_values 使用了禁用别名：{alias_hits}")
    expected = set(ENDPOINT_ROW_KEYS)
    if status != "OK":
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        if missing or extra:
            raise S1RecordValidationError(f"[{index}] 失败记录也必须登记 9 键端点；missing={missing}, extra={extra}")
        return
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing or extra:
        raise S1RecordValidationError(f"[{index}] endpoint_values 键必须恰为 9 个规范键；missing={missing}, extra={extra}")
    main_values = [values[name] for name in PRIMARY_ENDPOINTS]
    for name in ENDPOINT_ROW_KEYS:
        value = values[name]
        if name in ("n_nonnull", "first_feasible_in_support"):
            continue
        if value is not None and not _is_finite_number(value):
            raise S1RecordValidationError(f"[{index}] endpoint_values.{name} 必须是有限数或 null")
    non_null = sum(1 for value in main_values if value is not None)
    n_nonnull = values["n_nonnull"]
    null_rate = values["null_rate"]
    if not _is_int(n_nonnull) or int(n_nonnull) != non_null:
        raise S1RecordValidationError(f"[{index}] endpoint_values.n_nonnull 必须等于 {non_null}")
    if not _is_finite_number(null_rate):
        raise S1RecordValidationError(f"[{index}] endpoint_values.null_rate 必须是有限数")
    expected_rate = (len(main_values) - non_null) / len(main_values)
    if abs(float(null_rate) - expected_rate) > TRUE_NULL_RATE_TOL:
        raise S1RecordValidationError(f"[{index}] endpoint_values.null_rate 必须等于 {expected_rate}")
    best = values["best_feasible_value"]
    gap = values["gap_to_reference"]
    if (best is None) != (gap is None):
        raise S1RecordValidationError(f"[{index}] best_feasible_value/gap_to_reference 必须同为 null 或同为数值")
    hit = values["feasible_hit_rate"]
    if hit is not None and not (0.0 <= float(hit) <= 1.0):
        raise S1RecordValidationError(f"[{index}] feasible_hit_rate 必须在 [0,1]")
    first = values["first_feasible_eval_index"]
    if first is not None:
        if not _is_number(first) or float(first) != int(first) or not (1 <= int(first) <= budget_B):
            raise S1RecordValidationError(f"[{index}] first_feasible_eval_index 必须是 1..B 的整数或 null")
        if int(first) <= K:
            expected_support = True
        else:
            expected_support = False
        if values["first_feasible_in_support"] is not expected_support:
            raise S1RecordValidationError(f"[{index}] first_feasible_in_support 与 first_feasible_eval_index/K 不一致")
        expected_after = None if int(first) <= K else int(first) - K
        if values["first_feasible_after_support_index"] != expected_after:
            raise S1RecordValidationError(f"[{index}] first_feasible_after_support_index 语义不符")
    else:
        if values["first_feasible_in_support"] is not None or values["first_feasible_after_support_index"] is not None:
            raise S1RecordValidationError(f"[{index}] 无首次可行点时附加首次可行字段必须为 null")
    hit_non_support = values["feasible_hit_rate_non_support"]
    if budget_B > K:
        if hit_non_support is not None and not (0.0 <= float(hit_non_support) <= 1.0):
            raise S1RecordValidationError(f"[{index}] feasible_hit_rate_non_support 必须在 [0,1]")
    else:
        if hit_non_support is not None:
            raise S1RecordValidationError(f"[{index}] B==K 时 feasible_hit_rate_non_support 必须为 null")


def _validate_fallback_values(values: Any, index: int) -> None:
    if not isinstance(values, Mapping):
        raise S1RecordValidationError(f"[{index}] fallback_values 必须是 object")
    expected = {"best_objective_raw", "min_constraint_violation_sum"}
    if set(values) != expected:
        raise S1RecordValidationError(f"[{index}] fallback_values 键必须为 {sorted(expected)}")
    for name, value in values.items():
        if value is not None:
            if not _is_finite_number(value):
                raise S1RecordValidationError(f"[{index}] fallback_values.{name} 必须是有限数或 null")
            if name == "min_constraint_violation_sum" and float(value) < 0:
                raise S1RecordValidationError(f"[{index}] min_constraint_violation_sum 不得为负")


def _validate_budget_fields(record: Mapping[str, Any], index: int) -> None:
    budget = record.get("budget_B")
    k_shot = record.get("K")
    if not _is_int(budget) or int(budget) not in BUDGETS:
        raise S1RecordValidationError(f"[{index}] budget_B 必须属于 {BUDGETS}")
    if not _is_int(k_shot) or int(k_shot) not in K_VALUES:
        raise S1RecordValidationError(f"[{index}] K 必须属于 {K_VALUES}")
    budget = int(budget)
    k_shot = int(k_shot)
    if k_shot > budget:
        raise S1RecordValidationError(f"[{index}] K 不得大于 budget_B")
    status = str(record.get("status", ""))
    expected = {
        "initial_designs": INITIAL_DESIGN_COUNT,
        "bo_calls": budget - INITIAL_DESIGN_COUNT,
        "support_evals": k_shot,
        "initial_evals": INITIAL_DESIGN_COUNT - k_shot,
        "bo_evals": budget - INITIAL_DESIGN_COUNT,
        "billable_evals": budget,
    }
    if k_shot + (INITIAL_DESIGN_COUNT - k_shot) + (budget - INITIAL_DESIGN_COUNT) != budget:
        raise S1RecordValidationError(f"[{index}] K+(8-K)+(B-8)!=B")
    if status != "OK":
        # 失败记录在 runner 中于 try 前只登记计划值；实际消耗字段允许为 0（未完成执行）。
        for name in ("initial_designs", "bo_calls"):
            actual = record.get(name)
            if not _is_int(actual) or int(actual) != int(expected[name]):
                raise S1RecordValidationError(f"[{index}] 失败记录 {name} 必须登记计划值 {expected[name]}（实际 {actual!r}）")
        for name in ("support_evals", "initial_evals", "bo_evals", "billable_evals"):
            actual = record.get(name)
            if not _is_int(actual) or int(actual) not in (0, int(expected[name])):
                raise S1RecordValidationError(f"[{index}] 失败记录 {name} 必须为 0 或计划值 {expected[name]}（实际 {actual!r}）")
        return
    for name, value in expected.items():
        actual = record.get(name)
        if not _is_int(actual) or int(actual) != int(value):
            raise S1RecordValidationError(f"[{index}] {name} 必须为 {value}（实际 {actual!r}），违反等预算合同")
    if k_shot != int(record["support_evals"]):
        raise S1RecordValidationError(f"[{index}] support_evals 必须等于 K")


def _validate_identifiability(record: Mapping[str, Any], index: int) -> None:
    arm = record.get("arm")
    k_shot = int(record.get("K", -1))
    label = record.get("identifiability")
    clone_of = record.get("clone_of")
    inference_eligible = record.get("inference_eligible")
    if arm == CLONE_ALLOWED["arm"] and k_shot == CLONE_ALLOWED["K"]:
        if label != CLONE_IDENTIFIABILITY:
            raise S1RecordValidationError(f"[{index}] K=0 FOMAML-KSHOT-BO 必须登记为 {CLONE_IDENTIFIABILITY}")
        if clone_of != CLONE_ALLOWED["canonical_arm"]:
            raise S1RecordValidationError(f"[{index}] K=0 CLONE 的 clone_of 必须是 {CLONE_ALLOWED['canonical_arm']}")
        if inference_eligible is not False:
            raise S1RecordValidationError(f"[{index}] K=0 CLONE 必须 inference_eligible=false（排除推断）")
        return
    if label != IDENTIFIABLE:
        raise S1RecordValidationError(f"[{index}] 非 K=0 CLONE 记录必须为 {IDENTIFIABLE}，实际 {label!r}")
    if clone_of is not None:
        raise S1RecordValidationError(f"[{index}] IDENTIFIABLE 记录 clone_of 必须为 null")
    if inference_eligible is not True:
        raise S1RecordValidationError(f"[{index}] IDENTIFIABLE 记录 inference_eligible 必须为 true")


def _validate_record_identity(
    record: Mapping[str, Any],
    index: int,
    *,
    bundle: FrozenBundle,
    split_task_ids: Mapping[str, set[str]],
) -> None:
    unknown = set(record) - RECORD_KNOWN_FIELDS
    if unknown:
        raise S1RecordValidationError(f"[{index}] 出现未登记字段（疑似 schema 漂移）：{sorted(unknown)}")
    for name, expected in bundle.expected_echo().items():
        if record.get(name) != expected:
            raise S1RecordValidationError(f"[{index}] {name} 必须回显冻结值 {expected}（实际 {record.get(name)!r}）")
    schema = record.get("schema_version")
    if schema is not None and schema != S1_RECORD_SCHEMA_VERSION:
        raise S1RecordValidationError(f"[{index}] schema_version 必须为 {S1_RECORD_SCHEMA_VERSION}")
    group = record.get("run_group_id")
    if not isinstance(group, str) or not group:
        raise S1RecordValidationError(f"[{index}] run_group_id 必须是非空 str")
    split = record.get("split")
    if split not in RECORD_SPLITS:
        raise S1RecordValidationError(f"[{index}] split 必须属于 {RECORD_SPLITS}，实际 {split!r}")
    task_id = record.get("task_id")
    if not isinstance(task_id, str) or not family_v3.TASK_ID_PATTERN.match(task_id):
        raise S1RecordValidationError(f"[{index}] task_id 不符合冻结正则：{task_id!r}")
    if task_id not in split_task_ids[str(split)]:
        raise S1RecordValidationError(f"[{index}] task_id {task_id} 不属于冻结 split {split}")
    arm = record.get("arm")
    if arm not in ARM_IDS:
        raise S1RecordValidationError(f"[{index}] arm 非法：{arm!r}")
    meta_seed = record.get("meta_seed")
    opt_seed = record.get("opt_seed")
    if not _is_int(meta_seed) or int(meta_seed) not in bundle.meta_seeds:
        raise S1RecordValidationError(f"[{index}] meta_seed 必须属于冻结 seeds")
    if not _is_int(opt_seed) or int(opt_seed) not in bundle.opt_seeds:
        raise S1RecordValidationError(f"[{index}] opt_seed 必须属于冻结 seeds")
    run_id = record.get("run_id")
    match = RUN_ID_RE.match(str(run_id))
    if not match:
        raise S1RecordValidationError(f"[{index}] run_id 不符合合同格式：{run_id!r}")
    parsed = match.groupdict()
    if (parsed["arm"], int(parsed["B"]), int(parsed["K"]), parsed["task"], int(parsed["ms"]), int(parsed["os"])) != (
        arm,
        int(record["budget_B"]),
        int(record["K"]),
        task_id,
        int(meta_seed),
        int(opt_seed),
    ):
        raise S1RecordValidationError(f"[{index}] run_id 与记录字段不一致：{run_id!r}")
    status = record.get("status")
    if status not in RECORD_STATUSES:
        raise S1RecordValidationError(f"[{index}] status 非法：{status!r}")
    failure_reason = record.get("failure_reason")
    if status == "OK":
        if failure_reason is not None:
            raise S1RecordValidationError(f"[{index}] status=OK 时 failure_reason 必须为 null")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            raise S1RecordValidationError(f"[{index}] status={status} 时 failure_reason 必须非空")
    record_digest = record.get("record_digest")
    if not isinstance(record_digest, str) or not SHA256_RE.match(record_digest):
        raise S1RecordValidationError(f"[{index}] record_digest 必须是 64 位小写十六进制")
    if record_digest != _canonical_record_digest(record):
        raise S1RecordValidationError(f"[{index}] record_digest 自校验失败（记录被篡改）")
    history_digest = record.get("history_digest")
    if status == "OK":
        if not isinstance(history_digest, str) or not SHA256_RE.match(history_digest):
            raise S1RecordValidationError(f"[{index}] status=OK 时 history_digest 必须是 64 位十六进制")
    elif history_digest is not None and (not isinstance(history_digest, str) or not SHA256_RE.match(history_digest)):
        raise S1RecordValidationError(f"[{index}] history_digest 格式非法")


def verify_clone_equivalence(records: Sequence[Mapping[str, Any]]) -> tuple[int, list[str]]:
    """K=0 时 FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 必须历史逐字节一致（CLONE 声明有效）。"""
    groups: dict[tuple[Any, ...], dict[str, Mapping[str, Any]]] = {}
    for record in records:
        if int(record.get("K", -1)) != 0:
            continue
        arm = record.get("arm")
        if arm not in (CLONE_ALLOWED["arm"], CLONE_ALLOWED["canonical_arm"]):
            continue
        key = (
            record.get("split"),
            int(record["budget_B"]),
            record.get("task_id"),
            int(record["meta_seed"]),
            int(record["opt_seed"]),
        )
        groups.setdefault(key, {})[str(arm)] = record
    mismatches: list[str] = []
    checked = 0
    for key, pair in sorted(groups.items(), key=lambda item: repr(item[0])):
        if set(pair) != {CLONE_ALLOWED["arm"], CLONE_ALLOWED["canonical_arm"]}:
            continue
        checked += 1
        clone = pair[CLONE_ALLOWED["arm"]]
        canonical = pair[CLONE_ALLOWED["canonical_arm"]]
        if clone.get("history_digest") != canonical.get("history_digest"):
            mismatches.append(f"history_digest 不一致：{key}")
        if clone.get("status") != canonical.get("status"):
            mismatches.append(f"status 不一致：{key}")
        if clone.get("endpoint_values") != canonical.get("endpoint_values"):
            mismatches.append(f"endpoint_values 不一致：{key}")
    if mismatches:
        raise S1RecordValidationError(f"K=0 CLONE 逐字节等价失败（{len(mismatches)} 项）：{mismatches[:5]}")
    return checked, mismatches


def validate_run_records(
    records: Sequence[Mapping[str, Any]],
    bundle: FrozenBundle,
    *,
    verify_clone: bool = True,
) -> RecordValidation:
    """逐行强校验；任一不符抛 S1RecordValidationError（fail-closed）。"""
    split_task_ids = {split: set(bundle.task_ids_for(split)) for split in family_v3.SPLIT_ORDER}
    groups: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise S1RecordValidationError(f"[{index}] 记录必须是 object")
        missing = [name for name in RECORD_REQUIRED_FIELDS if name not in record]
        if missing:
            raise S1RecordValidationError(f"[{index}] 缺少合同必填字段：{missing}")
        _validate_record_identity(record, index, bundle=bundle, split_task_ids=split_task_ids)
        if record.get("run_group_id") not in groups:
            groups.append(str(record["run_group_id"]))
        _validate_budget_fields(record, index)
        _validate_grid_stratum(record, index)
        _validate_identifiability(record, index)
        _validate_design_identifiability_fields(record, index)
        _validate_endpoint_values(
            record.get("endpoint_values"),
            status=str(record.get("status")),
            budget_B=int(record["budget_B"]),
            K=int(record["K"]),
            index=index,
        )
        _validate_fallback_values(record.get("fallback_values"), index)
        _validate_cost(record.get("cost"), index)
        _validate_physics(record.get("physics"), index)
    checked = 0
    if verify_clone:
        checked, _ = verify_clone_equivalence(records)
    counts_by_split = _count_values(records, "split")
    statuses = _count_values(records, "status")
    return RecordValidation(
        record_count=len(records),
        run_group_ids=groups,
        counts_by_split=counts_by_split,
        counts_by_arm=_count_values(records, "arm"),
        counts_by_status=statuses,
        counts_by_budget=_count_values(records, "budget_B"),
        counts_by_k=_count_values(records, "K"),
        clone_count=int(_count_values(records, "identifiability").get(CLONE_IDENTIFIABILITY, 0)),
        failed_count=int(len(records) - statuses.get("OK", 0)),
        clone_equivalence_checked=checked,
    )


def _count_values(records: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(key)
        text = str(int(value)) if _is_int(value) else str(value)
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items()))


def audit_budget_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """按 (split, arm, B, K) 汇总等预算审计表；任何 billable 偏移都已在记录校验阶段拒绝。"""
    buckets: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for record in records:
        key = (record.get("split"), str(record.get("arm")), int(record["budget_B"]), int(record["K"]))
        buckets.setdefault(key, []).append(record)
    rows: list[dict[str, Any]] = []
    for key in sorted(buckets):
        bucket = buckets[key]
        split, arm, budget, k_shot = key
        status_counts = _count_values(bucket, "status")
        rows.append(
            {
                "split": split,
                "arm": arm,
                "budget_B": budget,
                "K": int(k_shot),
                "n_runs": len(bucket),
                "expected_billable": budget,
                "billable_values": sorted({int(row["billable_evals"]) for row in bucket}),
                "support_values": sorted({int(row["support_evals"]) for row in bucket}),
                "initial_values": sorted({int(row["initial_evals"]) for row in bucket}),
                "bo_values": sorted({int(row["bo_evals"]) for row in bucket}),
                "n_ok": int(status_counts.get("OK", 0)),
                "n_failed": int(len(bucket) - status_counts.get("OK", 0)),
                "n_clone": sum(1 for row in bucket if row.get("identifiability") == CLONE_IDENTIFIABILITY),
                "inference_eligible": [
                    int(row["billable_evals"]) == budget
                    and row.get("identifiability") == IDENTIFIABLE
                    for row in bucket
                ].count(True),
            }
        )
    return rows


def audit_identifiability_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for record in records:
        key = (record.get("split"), str(record.get("arm")), int(record["budget_B"]), int(record["K"]))
        buckets.setdefault(key, []).append(record)
    rows: list[dict[str, Any]] = []
    for key in sorted(buckets):
        bucket = buckets[key]
        labels = _count_values(bucket, "identifiability")
        rows.append(
            {
                "split": key[0],
                "arm": key[1],
                "budget_B": key[2],
                "K": key[3],
                "n_runs": len(bucket),
                "labels": json.dumps(labels, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "n_identifiable": int(labels.get(IDENTIFIABLE, 0)),
                "n_clone": int(labels.get(CLONE_IDENTIFIABILITY, 0)),
                "inference_eligible": bool(
                    key[3] > 0 or key[1] != CLONE_ALLOWED["arm"]
                ),
                "note": (
                    "K=0 CLONE 仅描述，排除推断"
                    if key[3] == 0 and key[1] == CLONE_ALLOWED["arm"]
                    else "进入推断"
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 聚合：单 run -> (task, meta_seed) 内 opt seed 均值 -> meta_seed 等权 -> 任务级
# ---------------------------------------------------------------------------
@dataclass
class AggregatedCell:
    split: str
    budget_B: int
    K: int
    arm: str
    endpoint_per_task: dict[str, dict[str, float | None]]
    endpoint_per_meta_seed: dict[int, dict[str, dict[str, float | None]]]
    n_runs: dict[str, int]
    n_ok_runs: int
    n_failed_runs: int
    n_tasks: int

    def endpoint_values(self, endpoint: str) -> dict[str, float | None]:
        return {task: values.get(endpoint) for task, values in self.endpoint_per_task.items()}


def _mean_or_none(values: Sequence[float | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return float(sum(numbers) / len(numbers))


def aggregate_run_records(
    records: Sequence[Mapping[str, Any]],
    bundle: FrozenBundle,
    *,
    splits: Sequence[str] = RECORD_SPLITS,
) -> dict[tuple[str, int, int, str], AggregatedCell]:
    """按冻结规则聚合端点：仅 status=OK 记录进入端点聚合；失败记录只计数。"""
    split_set = set(splits)
    grouped: dict[tuple[str, int, int, str], list[Mapping[str, Any]]] = {}
    for record in records:
        split = str(record.get("split"))
        if split not in split_set:
            continue
        key = (split, int(record["budget_B"]), int(record["K"]), str(record["arm"]))
        grouped.setdefault(key, []).append(record)
    cells: dict[tuple[str, int, int, str], AggregatedCell] = {}
    for key in sorted(grouped):
        split, budget, k_shot, arm = key
        bucket = grouped[key]
        task_ids = list(bundle.task_ids_for(split))
        per_task: dict[str, dict[str, float | None]] = {}
        per_meta_seed: dict[int, dict[str, dict[str, float | None]]] = {}
        n_runs: dict[str, int] = {}
        for task_id in task_ids:
            per_task[task_id] = {}
            n_runs[task_id] = 0
        meta_seeds = sorted({int(record["meta_seed"]) for record in bucket})
        for meta_seed in meta_seeds:
            per_meta_seed[meta_seed] = {task_id: {} for task_id in task_ids}
            for task_id in task_ids:
                task_records = [
                    record
                    for record in bucket
                    if record.get("task_id") == task_id
                    and int(record["meta_seed"]) == meta_seed
                    and record.get("status") == "OK"
                ]
                n_runs[task_id] += sum(
                    1
                    for record in bucket
                    if record.get("task_id") == task_id and int(record["meta_seed"]) == meta_seed
                )
                for endpoint in ENDPOINT_ROW_KEYS:
                    values = [
                        float(record["endpoint_values"][endpoint])
                        if record["endpoint_values"].get(endpoint) is not None
                        else None
                        for record in task_records
                    ]
                    per_meta_seed[meta_seed][task_id][endpoint] = _mean_or_none(values)
        for task_id in task_ids:
            for endpoint in ENDPOINT_ROW_KEYS:
                values = [
                    per_meta_seed[meta_seed][task_id][endpoint]
                    for meta_seed in meta_seeds
                ]
                per_task[task_id][endpoint] = _mean_or_none(values)
        statuses = _count_values(bucket, "status")
        cells[key] = AggregatedCell(
            split=split,
            budget_B=budget,
            K=k_shot,
            arm=arm,
            endpoint_per_task=per_task,
            endpoint_per_meta_seed=per_meta_seed,
            n_runs=n_runs,
            n_ok_runs=int(statuses.get("OK", 0)),
            n_failed_runs=int(len(bucket) - statuses.get("OK", 0)),
            n_tasks=len(task_ids),
        )
    return cells


def expected_grid_units(bundle: FrozenBundle, split: str) -> dict[tuple[int, int, str], int]:
    """返回某 split 的预注册网格单元数：主层 B=64/K∈{0,3,5} 等，仅用于完整性审计。"""
    combos: list[tuple[int, int, str]] = []
    for arm in ARM_IDS:
        combos.append((64, 0, arm))
    for k_shot in (3, 5):
        for arm in ARM_IDS:
            combos.append((64, k_shot, arm))
            combos.append((128, k_shot, arm))
    for budget in BUDGETS:
        for arm in ARM_IDS:
            combos.append((budget, 1, arm))
    n_tasks = len(bundle.task_ids_for(split))
    n_meta = len(bundle.meta_seeds)
    n_opt = len(bundle.opt_seeds)
    return {combo: int(n_tasks * n_meta * n_opt) for combo in combos}


def validate_grid_completeness(
    records: Sequence[Mapping[str, Any]],
    bundle: FrozenBundle,
    *,
    splits: Sequence[str] = (MAIN_SPLIT,),
    allow_extra_units: bool = True,
) -> dict[str, Any]:
    """校验预注册网格单元齐全（每 (B,K,arm) 应恰有 tasks x meta x opt 条记录）；主分析 split 必须完整。"""
    expected = expected_grid_units(bundle, MAIN_SPLIT)
    for split in splits:
        counts: dict[tuple[int, int, str], int] = {}
        for record in records:
            if record.get("split") != split:
                continue
            key = (int(record["budget_B"]), int(record["K"]), str(record["arm"]))
            counts[key] = counts.get(key, 0) + 1
        missing_units = [combo for combo, total in expected.items() if counts.get(combo, 0) != total]
        if missing_units:
            raise S1RecordValidationError(
                f"split={split} 网格不完整：{len(missing_units)} 个 (B,K,arm) 单元数量不符；"
                f"示例 {missing_units[:5]}"
            )
    return {
        "split": list(splits),
        "expected_units": {f"B{budget}-K{k_shot}-{arm}": total for (budget, k_shot, arm), total in expected.items()},
        "status": "PASS",
    }


# ---------------------------------------------------------------------------
# 统计层：配对提取、Wilcoxon 符号秩、bootstrap、效应量、Holm、判定
# ---------------------------------------------------------------------------
DECISION_BENEFIT = "SUPPORTED_BENEFIT"
DECISION_HARM = "SUPPORTED_HARM"
DECISION_NONE = "NO_EVIDENCE"
DECISION_INCONCLUSIVE = "INCONCLUSIVE"
DECISION_CODES = (DECISION_BENEFIT, DECISION_HARM, DECISION_NONE, DECISION_INCONCLUSIVE)
OVERALL_ADVANTAGE = "SUPPORTED_IMPROVEMENT"
OVERALL_NONE = "NO_SIGNIFICANT_IMPROVEMENT"
OVERALL_HARM = "SUPPORTED_HARM"
OVERALL_INCONCLUSIVE = "INCONCLUSIVE"
OVERALL_CODES = (OVERALL_ADVANTAGE, OVERALL_NONE, OVERALL_HARM, OVERALL_INCONCLUSIVE)
REPRODUCED = "REPRODUCED"
NOT_REPRODUCED = "NOT_REPRODUCED"
REPRODUCTION_MIXED = "MIXED"
REPRODUCTION_NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass
class PairedEndpoint:
    """一个 (split, B, K, 比较, 端点) 的任务级配对样本。"""

    comparison_id: str
    split: str
    budget_B: int
    K: int
    endpoint: str
    treatment: str
    reference: str
    task_ids: list[str]
    treatment_values: list[float | None]
    reference_values: list[float | None]
    paired_task_ids: list[str] = field(default_factory=list)
    differences: list[float] = field(default_factory=list)
    structural_index_present: bool = False
    structural_exclusion_count: int = 0
    n_tasks_unpaired: int = 0

    @property
    def n_tasks(self) -> int:
        return len(self.task_ids)

    @property
    def n_pairs(self) -> int:
        return len(self.paired_task_ids)

    @property
    def null_rate_treatment(self) -> float:
        if not self.treatment_values:
            return 1.0
        return sum(1 for value in self.treatment_values if value is None) / len(self.treatment_values)

    @property
    def null_rate_reference(self) -> float:
        if not self.reference_values:
            return 1.0
        return sum(1 for value in self.reference_values if value is None) / len(self.reference_values)


def build_paired_endpoint(
    cells: Mapping[tuple[str, int, int, str], AggregatedCell],
    bundle: FrozenBundle,
    *,
    comparison_id: str,
    split: str,
    budget_B: int,
    K: int,
    endpoint: str,
    structural_index: "StructuralIdentifiabilityIndex | None" = None,
) -> PairedEndpoint | None:
    """构造任务级配对样本；缺少任一臂单元时返回 None（由调用方判定是否 fail-closed）。

    R-V4-02：当提供 structural_index 时，按 (task, meta_seed) 行级排除 STRUCTURALLY_IDENTICAL
    的臂对组（不做事后任务剔除）；任务值 = 剩余 meta_seed 的等权均值。
    """
    comparison = COMPARISON_BY_ID.get(comparison_id)
    if comparison is None:
        raise S1AnalysisError(f"未知比较：{comparison_id!r}")
    if endpoint not in PRIMARY_ENDPOINTS and endpoint not in SECONDARY_ENDPOINTS:
        raise S1AnalysisError(f"未知端点：{endpoint!r}")
    treatment_cell = cells.get((split, int(budget_B), int(K), comparison["arm"]))
    reference_cell = cells.get((split, int(budget_B), int(K), comparison["reference"]))
    if treatment_cell is None or reference_cell is None:
        return None
    task_ids = list(bundle.task_ids_for(split))
    structural_present = bool(structural_index is not None and structural_index.present)
    treatment_values: list[float | None] = []
    reference_values: list[float | None] = []
    paired: list[str] = []
    differences: list[float] = []
    exclusion_count = 0
    unpaired_tasks = 0
    for task_id in task_ids:
        if not structural_present:
            left = treatment_cell.endpoint_per_task.get(task_id, {}).get(endpoint)
            right = reference_cell.endpoint_per_task.get(task_id, {}).get(endpoint)
            treatment_values.append(left)
            reference_values.append(right)
            if left is not None and right is not None:
                paired.append(task_id)
                differences.append(float(left) - float(right))
            continue
        # R-V4-02 行级排除：只剔除被登记为 STRUCTURALLY_IDENTICAL 的 (task,B,K,meta_seed) 组，
        # 任务保留；任务值 = 剩余 meta_seed 的等权均值（不做事后任务剔除）。
        left_samples: list[float] = []
        right_samples: list[float] = []
        meta_seed_set = set(treatment_cell.endpoint_per_meta_seed) | set(
            reference_cell.endpoint_per_meta_seed
        )
        for meta_seed in sorted(meta_seed_set):
            if structural_index.is_structurally_identical(
                task_id,
                int(budget_B),
                int(K),
                int(meta_seed),
                str(comparison["arm"]),
                str(comparison["reference"]),
            ):
                exclusion_count += 1
                continue
            left_meta = (
                treatment_cell.endpoint_per_meta_seed.get(meta_seed, {})
                .get(task_id, {})
                .get(endpoint)
            )
            right_meta = (
                reference_cell.endpoint_per_meta_seed.get(meta_seed, {})
                .get(task_id, {})
                .get(endpoint)
            )
            if left_meta is not None and right_meta is not None:
                left_samples.append(float(left_meta))
                right_samples.append(float(right_meta))
        left_value = _mean_or_none(left_samples)
        right_value = _mean_or_none(right_samples)
        treatment_values.append(left_value)
        reference_values.append(right_value)
        if left_value is not None and right_value is not None:
            paired.append(task_id)
            differences.append(float(left_value) - float(right_value))
        else:
            unpaired_tasks += 1
    return PairedEndpoint(
        comparison_id=comparison_id,
        split=split,
        budget_B=int(budget_B),
        K=int(K),
        endpoint=endpoint,
        treatment=str(comparison["arm"]),
        reference=str(comparison["reference"]),
        task_ids=task_ids,
        treatment_values=treatment_values,
        reference_values=reference_values,
        paired_task_ids=paired,
        differences=differences,
        structural_index_present=structural_present,
        structural_exclusion_count=int(exclusion_count),
        n_tasks_unpaired=int(unpaired_tasks),
    )


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _rank_abs(values: Sequence[float]) -> tuple[list[float], list[int]]:
    """绝对值秩（并列取平均秩）；返回 ranks, tie_group_sizes。"""
    order = sorted(range(len(values)), key=lambda index: (abs(values[index]), index))
    ranks = [0.0] * len(values)
    tie_sizes: list[int] = []
    position = 0
    while position < len(order):
        end = position
        current = abs(values[order[position]])
        while end + 1 < len(order) and abs(values[order[end + 1]]) == current:
            end += 1
        size = end - position + 1
        tie_sizes.append(size)
        average_rank = (position + 1 + end + 1) / 2.0
        for spot in range(position, end + 1):
            ranks[order[spot]] = average_rank
        position = end + 1
    return ranks, tie_sizes


def wilcoxon_signed_rank(differences: Sequence[float]) -> dict[str, Any]:
    """双侧 Wilcoxon 符号秩检验（零差剔除）。

    n<=20 且无并列时用精确分布（DP 枚举符号翻转）；存在并列时用含并列修正与
    连续性修正的正态近似。返回 p 值、统计量与所用方法，便于审计。
    """
    values = [float(value) for value in differences]
    if any(not math.isfinite(value) for value in values):
        raise S1AnalysisError("Wilcoxon 输入必须全部有限；非有限应在记录校验层被拒绝")
    non_zero = [value for value in values if value != 0.0]
    n = len(non_zero)
    zero_count = len(values) - n
    if n == 0:
        return {
            "n_pairs": len(values),
            "n_effective": 0,
            "zero_count": zero_count,
            "w_plus": 0.0,
            "w_minus": 0.0,
            "statistic": 0.0,
            "p_value": 1.0,
            "method": "all_zero",
            "ties_present": False,
        }
    ranks, tie_sizes = _rank_abs(non_zero)
    w_plus = float(sum(rank for rank, value in zip(ranks, non_zero) if value > 0))
    total_rank = float(sum(ranks))
    w_minus = total_rank - w_plus
    statistic = min(w_plus, w_minus)
    ties_present = any(size > 1 for size in tie_sizes)
    if not ties_present and n <= 20:
        max_sum = int(n * (n + 1) / 2)
        counts = [0] * (max_sum + 1)
        counts[0] = 1
        current_max = 0
        for rank in range(1, n + 1):
            for value in range(current_max, -1, -1):
                if counts[value]:
                    counts[value + int(rank)] += counts[value]
            current_max += rank
        total = 2 ** n
        tail = sum(counts[: int(statistic) + 1])
        p_value = min(1.0, 2.0 * tail / total)
        method = "exact"
    else:
        mu = n * (n + 1) / 4.0
        tie_correction = sum(size ** 3 - size for size in tie_sizes)
        variance = (n * (n + 1) * (2 * n + 1) / 24.0) - tie_correction / 48.0
        if variance <= 0:
            p_value = 1.0
        else:
            sigma = math.sqrt(variance)
            z_low = (w_plus - mu + 0.5) / sigma
            z_high = (w_plus - mu - 0.5) / sigma
            p_low = _norm_cdf(z_low)
            p_high = 1.0 - _norm_cdf(z_high)
            p_value = min(1.0, 2.0 * min(p_low, p_high))
        method = "normal_approx_tie_corrected"
    return {
        "n_pairs": len(values),
        "n_effective": n,
        "zero_count": zero_count,
        "w_plus": w_plus,
        "w_minus": w_minus,
        "statistic": statistic,
        "p_value": float(p_value),
        "method": method,
        "ties_present": ties_present,
    }


def paired_effect_sizes(differences: Sequence[float]) -> dict[str, float | None]:
    """效应量：配对 Cohen's d（差值均值/差值样本标准差）与符号秩 rank-biserial。"""
    values = [float(value) for value in differences]
    n = len(values)
    if n < 2:
        return {"mean_difference": (values[0] if n == 1 else None), "median_difference": (values[0] if n == 1 else None), "cohens_d": None, "rank_biserial": None}
    mean_value = sum(values) / n
    variance = sum((value - mean_value) ** 2 for value in values) / (n - 1)
    sd = math.sqrt(variance)
    cohens_d = None if sd == 0 else mean_value / sd
    sorted_values = sorted(values)
    middle = n // 2
    median_value = (
        sorted_values[middle]
        if n % 2 == 1
        else (sorted_values[middle - 1] + sorted_values[middle]) / 2.0
    )
    ranks, _ = _rank_abs(values)
    positive = sum(rank for rank, value in zip(ranks, values) if value > 0)
    negative = sum(rank for rank, value in zip(ranks, values) if value < 0)
    total = positive + negative
    rank_biserial = None if total == 0 else (positive - negative) / total
    return {
        "mean_difference": float(mean_value),
        "median_difference": float(median_value),
        "cohens_d": None if cohens_d is None else float(cohens_d),
        "rank_biserial": None if rank_biserial is None else float(rank_biserial),
    }


def _bootstrap_rng(seed_key: Sequence[Any]) -> np.random.Generator:
    digest = hashlib.sha256("|".join(str(item) for item in seed_key).encode("utf-8")).hexdigest()
    sequence = np.random.SeedSequence([BOOTSTRAP_SEED, int(digest[:16], 16)])
    return np.random.default_rng(sequence)


def bootstrap_mean_ci(
    values: Sequence[float],
    *,
    seed_key: Sequence[Any],
    samples: int = BOOTSTRAP_SAMPLES,
    confidence: float = CONFIDENCE_LEVEL,
) -> dict[str, Any]:
    """配对差值均值的百分位 bootstrap CI（固定 seed=20261105，按 seed_key 派生独立流）。"""
    numbers = [float(value) for value in values]
    if len(numbers) < 2:
        return {"samples": 0, "confidence": confidence, "low": None, "high": None, "mean": (numbers[0] if numbers else None), "method": "percentile"}
    if samples <= 0:
        raise S1AnalysisError("bootstrap samples 必须为正整数")
    array = np.asarray(numbers, dtype=np.float64)
    rng = _bootstrap_rng(seed_key)
    indices = rng.integers(0, array.size, size=(int(samples), array.size))
    means = array[indices].mean(axis=1)
    alpha = (1.0 - float(confidence)) / 2.0
    low, high = np.percentile(means, [100.0 * alpha, 100.0 * (1.0 - alpha)])
    return {
        "samples": int(samples),
        "confidence": float(confidence),
        "low": float(low),
        "high": float(high),
        "mean": float(array.mean()),
        "method": "percentile",
    }


def holm_adjust(p_values: Sequence[float]) -> list[float | None]:
    """Holm-Bonferroni 调整；None 表示未参与检验（保持 None）。"""
    indexed = [(index, float(value)) for index, value in enumerate(p_values) if value is not None]
    adjusted: list[float | None] = [None] * len(p_values)
    if not indexed:
        return adjusted
    ordered = sorted(indexed, key=lambda item: (item[1], item[0]))
    m = len(ordered)
    running = 0.0
    for position, (index, value) in enumerate(ordered):
        candidate = min(1.0, (m - position) * value)
        running = max(running, candidate)
        adjusted[index] = float(min(1.0, running))
    return adjusted


def _endpoint_threshold(endpoint: str, budget_B: int) -> float:
    if endpoint == "feasible_hit_rate":
        return HIT_RATE_ABSOLUTE_THRESHOLD
    if endpoint == "first_feasible_eval_index":
        return float(math.ceil(0.05 * int(budget_B)))
    return RELATIVE_IMPROVEMENT_THRESHOLD


def _median(values: Sequence[float]) -> float | None:
    """样本中位数（偶数取中间两值均值）；空序列返回 None。"""
    ordered = sorted(float(value) for value in values)
    count = len(ordered)
    if count == 0:
        return None
    middle = count // 2
    if count % 2 == 1:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2.0)


def _paired_endpoint_values(paired: PairedEndpoint) -> tuple[list[float], list[float]]:
    """取两臂均非 null 的配对子集（与 Wilcoxon/CI 使用同一配对规则，不做单臂插补）。"""
    treatment: list[float] = []
    reference: list[float] = []
    for left, right in zip(paired.treatment_values, paired.reference_values):
        if left is None or right is None:
            continue
        treatment.append(float(left))
        reference.append(float(right))
    return treatment, reference


def _ci_supports_direction(endpoint: str, ci_low: float, ci_high: float, *, beneficial: bool) -> bool:
    """B02（task-226）：bootstrap CI 必须与端点方向一致且不跨 0。

    配对差值定义为 treatment - reference：
    - feasible_hit_rate 越大越好 -> BENEFIT 要求 CI 下界 > 0；HARM 要求 CI 上界 < 0；
    - best_feasible_value / gap_to_reference / first_feasible_eval_index 越小越好
      -> BENEFIT 要求 CI 上界 < 0；HARM 要求 CI 下界 > 0。
    """
    if endpoint == "feasible_hit_rate":
        return ci_low > 0.0 if beneficial else ci_high < 0.0
    return ci_high < 0.0 if beneficial else ci_low > 0.0


def endpoint_improvement(paired: PairedEndpoint) -> float | None:
    """预注册改善量：在配对（两臂均非 null）子集上取中位数，正数表示处理臂更优。

    M01（task-226）：统计计划要求效应量用中位数而非均值；
    - best_feasible_value / gap_to_reference：相对改善 =(参考中位数 - 处理中位数)/max(|参考中位数|,1e-12)
    - feasible_hit_rate：绝对改善 = 处理中位数 - 参考中位数
    - first_feasible_eval_index：绝对改善 = 参考中位数 - 处理中位数（评价次数越少越好）
    """
    if paired.n_pairs == 0:
        return None
    treatment, reference = _paired_endpoint_values(paired)
    if not treatment or not reference:
        return None
    treatment_median = _median(treatment)
    reference_median = _median(reference)
    if treatment_median is None or reference_median is None:
        return None
    if paired.endpoint in ("best_feasible_value", "gap_to_reference"):
        return float((reference_median - treatment_median) / max(abs(reference_median), 1e-12))
    if paired.endpoint == "feasible_hit_rate":
        return float(treatment_median - reference_median)
    if paired.endpoint == "first_feasible_eval_index":
        return float(reference_median - treatment_median)
    raise S1AnalysisError(f"端点 {paired.endpoint!r} 不属于 4 个主端点")


def decide_endpoint(
    paired: PairedEndpoint,
    *,
    test: Mapping[str, Any],
    p_adjusted: float | None,
    improvement: float | None,
    ci_low: float | None = None,
    ci_high: float | None = None,
) -> dict[str, Any]:
    """按预注册阈值给出单端点判定（fail-closed：缺信息一律 INCONCLUSIVE）。

    B02（task-226）：统计计划要求 SUPPORTED_BENEFIT 同时满足
    Holm p<0.05、95% bootstrap CI 不跨 0 且方向与端点一致、方向有利且达到阈值；
    CI 缺失/非有限 → INCONCLUSIVE；CI 跨 0/方向不一致 → 不得判 SUPPORTED_*（NO_EVIDENCE）。
    """
    endpoint = paired.endpoint
    budget = paired.budget_B
    threshold = _endpoint_threshold(endpoint, budget)
    reasons: list[str] = []
    null_rates = {
        "treatment": paired.null_rate_treatment,
        "reference": paired.null_rate_reference,
    }
    max_null_rate = max(null_rates.values()) if null_rates else 1.0
    ci_defined = (
        ci_low is not None
        and ci_high is not None
        and _is_finite_number(ci_low)
        and _is_finite_number(ci_high)
    )
    ci_low_value = float(ci_low) if ci_defined else None
    ci_high_value = float(ci_high) if ci_defined else None
    decision = DECISION_NONE
    if paired.n_pairs < WILCOXON_MIN_PAIRS:
        decision = DECISION_INCONCLUSIVE
        reasons.append(f"配对样本 {paired.n_pairs} < {WILCOXON_MIN_PAIRS}")
    elif max_null_rate > NULL_RATE_INCONCLUSIVE:
        decision = DECISION_INCONCLUSIVE
        reasons.append(f"端点 null 率 {max_null_rate:.4f} > {NULL_RATE_INCONCLUSIVE}")
    elif test.get("n_effective", 0) == 0:
        decision = DECISION_INCONCLUSIVE
        reasons.append("配对差值全为 0（无法检验）")
    elif p_adjusted is None or improvement is None or not math.isfinite(float(improvement)):
        decision = DECISION_INCONCLUSIVE
        reasons.append("调整后 p 值或改善量缺失/非有限")
    elif not ci_defined:
        decision = DECISION_INCONCLUSIVE
        reasons.append("95% bootstrap CI 缺失/非有限（CI 必须参与判定）")
    elif float(p_adjusted) < ALPHA and float(improvement) >= threshold:
        if ci_low_value is not None and ci_high_value is not None and _ci_supports_direction(
            endpoint, ci_low_value, ci_high_value, beneficial=True
        ):
            decision = DECISION_BENEFIT
            reasons.append(
                f"p_adj={float(p_adjusted):.6g} < {ALPHA}、改善 {float(improvement):.6g} >= 阈值 {threshold:.6g} "
                f"且 95% CI [{ci_low_value:.6g}, {ci_high_value:.6g}] 不跨 0 且方向有利（{endpoint}）"
            )
        else:
            decision = DECISION_NONE
            reasons.append(
                f"p_adj={float(p_adjusted):.6g} 显著且改善达阈值，但 95% CI [{ci_low_value:.6g}, {ci_high_value:.6g}] 跨 0 或方向与端点不一致（{endpoint}），"
                "不得判 SUPPORTED_BENEFIT"
            )
    elif float(p_adjusted) < ALPHA and float(improvement) <= -threshold:
        if ci_low_value is not None and ci_high_value is not None and _ci_supports_direction(
            endpoint, ci_low_value, ci_high_value, beneficial=False
        ):
            decision = DECISION_HARM
            reasons.append(
                f"p_adj={float(p_adjusted):.6g} < {ALPHA}、恶化 {float(improvement):.6g} <= -阈值 {-threshold:.6g} "
                f"且 95% CI [{ci_low_value:.6g}, {ci_high_value:.6g}] 不跨 0 且方向不利（{endpoint}）"
            )
        else:
            decision = DECISION_NONE
            reasons.append(
                f"p_adj={float(p_adjusted):.6g} 显著且恶化达阈值，但 95% CI [{ci_low_value:.6g}, {ci_high_value:.6g}] 跨 0 或方向与端点不一致（{endpoint}），"
                "不得判 SUPPORTED_HARM"
            )
    elif float(p_adjusted) >= ALPHA:
        reasons.append(
            f"p_adj={float(p_adjusted):.6g} >= {ALPHA}（Holm 后不显著）；"
            f"改善 {float(improvement):.6g}，阈值 {threshold:.6g}"
        )
    else:
        reasons.append(
            f"p_adj={float(p_adjusted):.6g} 显著但改善 {float(improvement):.6g} 未达阈值 {threshold:.6g}"
        )
    return {
        "decision": decision,
        "decision_reasons": reasons,
        "threshold": float(threshold),
        "improvement": None if improvement is None else float(improvement),
        "p_adjusted": None if p_adjusted is None else float(p_adjusted),
        "ci_low": ci_low_value,
        "ci_high": ci_high_value,
        "ci_defined": bool(ci_defined),
        "n_pairs": paired.n_pairs,
        "max_null_rate": float(max_null_rate),
        "null_rate_treatment": float(null_rates["treatment"]),
        "null_rate_reference": float(null_rates["reference"]),
    }


def analyze_pair(
    paired: PairedEndpoint,
    *,
    p_adjusted: float | None = None,
) -> dict[str, Any]:
    """完整分析一个配对样本：检验 + 效应量 + bootstrap CI + 改善量 + 判定。"""
    test = wilcoxon_signed_rank(paired.differences)
    effects = paired_effect_sizes(paired.differences)
    ci = bootstrap_mean_ci(
        paired.differences,
        seed_key=(
            "s1-bootstrap",
            paired.split,
            paired.comparison_id,
            paired.budget_B,
            paired.K,
            paired.endpoint,
        ),
    )
    improvement = endpoint_improvement(paired)
    decision = decide_endpoint(
        paired,
        test=test,
        p_adjusted=p_adjusted,
        improvement=improvement,
        ci_low=ci["low"],
        ci_high=ci["high"],
    )
    row: dict[str, Any] = {
        "comparison_id": paired.comparison_id,
        "role": str(COMPARISON_BY_ID[paired.comparison_id]["role"]),
        "split": paired.split,
        "budget_B": int(paired.budget_B),
        "K": int(paired.K),
        "endpoint": paired.endpoint,
        "treatment": paired.treatment,
        "reference": paired.reference,
        "n_tasks": paired.n_tasks,
        "n_pairs": paired.n_pairs,
        "null_rate_treatment": float(paired.null_rate_treatment),
        "null_rate_reference": float(paired.null_rate_reference),
        "mean_difference": effects["mean_difference"],
        "median_difference": effects["median_difference"],
        "cohens_d": effects["cohens_d"],
        "rank_biserial": effects["rank_biserial"],
        "improvement": improvement,
        "improvement_method": "median_paired_subset",
        "ci_low": ci["low"],
        "ci_high": ci["high"],
        "ci_method": ci["method"],
        "wilcoxon_statistic": test["statistic"],
        "wilcoxon_w_plus": test["w_plus"],
        "wilcoxon_w_minus": test["w_minus"],
        "p_raw": float(test["p_value"]),
        "p_adjusted": None if p_adjusted is None else float(p_adjusted),
        "test_method": test["method"],
        "zero_count": int(test["zero_count"]),
        "decision": decision["decision"],
        "decision_reasons": "；".join(decision["decision_reasons"]),
        "threshold": decision["threshold"],
        "max_null_rate": decision["max_null_rate"],
        "structural_index_present": bool(paired.structural_index_present),
        "structural_excluded_groups": int(paired.structural_exclusion_count),
        "n_tasks_unpaired": int(paired.n_tasks_unpaired),
    }
    return row


def collect_hypotheses(
    cells: Mapping[tuple[str, int, int, str], AggregatedCell],
    bundle: FrozenBundle,
    *,
    split: str,
    inference_ks: Sequence[int] = (1, 3, 5),
    structural_index: "StructuralIdentifiabilityIndex | None" = None,
) -> dict[str, Any]:
    """构造全部可检验配对（C1..C4 x B x K x 4 主端点），并按预注册做 Holm。

    R-V4-08-01（唯一口径）：Holm 族键 =(主端点, 预算_B, K)；族成员 = 该族键下全部
    可推断臂对比较 C1–C4（唯一来源 INFERENCE_COMPARISON_IDS）；C5 永不进族、不做
    benefit/harm。pair-level STRUCTURALLY_IDENTICAL 行级排除后族大小可 <4，必须动态
    记录（holm_family_size_counts / holm_family_sizes / holm_family_members），禁止写死 4。
    R-V4-02（task-230）：C5 仅由 c5_structural_summary 描述；其余比较在构造配对时按
    pair-level STRUCTURALLY_IDENTICAL 行级排除（不剔除任务）。
    """
    pairs: list[PairedEndpoint] = []
    inference_comparisons = [
        item for item in COMPARISONS if str(item["id"]) in INFERENCE_COMPARISON_IDS
    ]
    for K in inference_ks:
        for budget in MAIN_POPULATION_BUDGETS:
            for comparison in inference_comparisons:
                for endpoint in PRIMARY_ENDPOINTS:
                    paired = build_paired_endpoint(
                        cells,
                        bundle,
                        comparison_id=str(comparison["id"]),
                        split=split,
                        budget_B=int(budget),
                        K=int(K),
                        endpoint=endpoint,
                        structural_index=structural_index,
                    )
                    if paired is not None:
                        pairs.append(paired)
    # 先原始 p 值，再按 (端点, 预算, K) 分组 Holm（M02：每族 4 个可推断比较；C5 不在族内）。
    raw: list[tuple[PairedEndpoint, dict[str, Any]]] = []
    for paired in pairs:
        test = wilcoxon_signed_rank(paired.differences)
        raw.append((paired, test))
    by_family: dict[tuple[str, int, int], list[int]] = {}
    for index, (paired, _test) in enumerate(raw):
        key = (str(paired.endpoint), int(paired.budget_B), int(paired.K))
        by_family.setdefault(key, []).append(index)
    adjusted = [None] * len(raw)
    family_sizes: dict[str, int] = {}
    family_members: dict[str, list[str]] = {}
    family_raw_p: dict[str, list[float]] = {}
    for key in sorted(by_family):
        indices = by_family[key]
        label = f"{key[0]}|B{key[1]}|K{key[2]}"
        family_sizes[label] = len(indices)
        family_members[label] = sorted(
            str(raw[index][0].comparison_id) for index in indices
        )
        family_raw_p[label] = [float(raw[index][1]["p_value"]) for index in indices]
        values = [raw[index][1]["p_value"] for index in indices]
        for index, value in zip(indices, holm_adjust(values)):
            adjusted[index] = value
    size_values = sorted(family_sizes.values())
    family_size_counts = {
        str(size): int(size_values.count(size)) for size in sorted(set(size_values))
    }
    rows: list[dict[str, Any]] = []
    for index, (paired, _test) in enumerate(raw):
        rows.append(analyze_pair(paired, p_adjusted=adjusted[index]))
    return {
        "split": split,
        "n_hypotheses": len(rows),
        "holm_family_definition": (
            "唯一 Holm 族（R-V4-08-01）：族键=(主端点, 预算_B, K)，成员=该族键下全部可推断比较"
            "（C1–C4；C5 永不进族）；pair-level STRUCTURALLY_IDENTICAL 行级排除后族大小可 <4，动态记录"
        ),
        "holm_family_key_fields": ["primary_endpoint", "budget_B", "K"],
        "holm_family_size_dynamic": True,
        "holm_family_max_size": len(INFERENCE_COMPARISON_IDS),
        "holm_family_size_min": size_values[0] if size_values else 0,
        "holm_family_size_max": size_values[-1] if size_values else 0,
        "holm_family_size_counts": family_size_counts,
        "holm_family_members": family_members,
        "holm_family_raw_p": family_raw_p,
        "holm_family_count": len(by_family),
        "holm_family_sizes": family_sizes,
        "inference_comparison_ids": list(INFERENCE_COMPARISON_IDS),
        "excluded_comparison_ids": [C5_COMPARISON_ID],
        "structural_index_present": bool(
            structural_index is not None and structural_index.present
        ),
        "structural_exclusion_total": int(
            sum(
                1
                for paired in pairs
                if paired.structural_exclusion_count > 0
            )
        ),
        "rows": rows,
        "pairs": pairs,
    }


def summarize_layer(rows: Sequence[Mapping[str, Any]], *, comparison_id: str, budget_B: int, K: int) -> dict[str, Any]:
    """汇总某一层（比较 x 预算 x K x 主端点）的判定计数。"""
    layer_rows = [
        row
        for row in rows
        if row["comparison_id"] == comparison_id and int(row["budget_B"]) == budget_B and int(row["K"]) == K
    ]
    counts = {code: 0 for code in DECISION_CODES}
    for row in layer_rows:
        counts[str(row["decision"])] = counts.get(str(row["decision"]), 0) + 1
    return {
        "comparison_id": comparison_id,
        "budget_B": int(budget_B),
        "K": int(K),
        "n_endpoints": len(layer_rows),
        "n_benefit": int(counts[DECISION_BENEFIT]),
        "n_harm": int(counts[DECISION_HARM]),
        "n_no_evidence": int(counts[DECISION_NONE]),
        "n_inconclusive": int(counts[DECISION_INCONCLUSIVE]),
        "endpoint_decisions": {
            str(row["endpoint"]): str(row["decision"]) for row in layer_rows
        },
        "layer_rule": "逐端点判定；BENEFIT>=2 且 HARM==0 视为该层支持",
        "layer_supported": bool(counts[DECISION_BENEFIT] >= 2 and counts[DECISION_HARM] == 0),
    }


def primary_conclusion(
    rows: Sequence[Mapping[str, Any]],
    *,
    budget_B: int = PRIMARY_CONFIRMATORY_BUDGET,
    ks: Sequence[int] = PRIMARY_CONFIRMATORY_KS,
) -> dict[str, Any]:
    """C1 主结论：主确认层每个 K 各自需 BENEFIT>=2 且 HARM==0。

    CONTRACT_AMBIGUITY：执行计划只规定单层规则（C1 4 主端点 >=2 BENEFIT 且 0 HARM），
    未规定 K=3 与 K=5 两层如何合成；本实现采用保守规则（两层都满足才算 SUPPORTED_IMPROVEMENT），
    并在 aggregate.json 中披露该规则，待 Lead 裁决。
    """
    layers = [summarize_layer(rows, comparison_id="C1", budget_B=budget_B, K=int(K)) for K in ks]
    all_inconclusive = all(int(layer["n_inconclusive"]) == int(layer["n_endpoints"]) for layer in layers)
    any_harm = any(int(layer["n_harm"]) >= 2 for layer in layers)
    if all_inconclusive:
        overall = OVERALL_INCONCLUSIVE
    elif any_harm:
        overall = OVERALL_HARM
    elif all(layer["layer_supported"] for layer in layers):
        overall = OVERALL_ADVANTAGE
    else:
        overall = OVERALL_NONE
    return {
        "comparison_id": "C1",
        "budget_B": int(budget_B),
        "ks": [int(K) for K in ks],
        "layers": layers,
        "overall": overall,
        "rule": "C1 4 主端点逐层：BENEFIT>=2 且 HARM==0 为层支持；两层均支持才判 SUPPORTED_IMPROVEMENT",
        "contract_ambiguity": "跨 K 合成规则未在合同中规定；本实现取保守合取，需 Lead 裁决",
        "any_layer_harm": bool(any_harm),
        "all_endpoints_inconclusive": bool(all_inconclusive),
    }


def secondary_reproduction_conclusion(
    rows: Sequence[Mapping[str, Any]],
    *,
    budget_B: int = 128,
    ks: Sequence[int] = PRIMARY_CONFIRMATORY_KS,
) -> dict[str, Any]:
    """次级复现层（B=128）C1 结论；仅描述是否复现主层模式，不升级主结论。"""
    layers = [summarize_layer(rows, comparison_id="C1", budget_B=budget_B, K=int(K)) for K in ks]
    available = [layer for layer in layers if int(layer["n_endpoints"]) > 0]
    if not available:
        status = REPRODUCTION_NOT_AVAILABLE
    elif all(layer["layer_supported"] for layer in available) and not any(int(layer["n_harm"]) >= 2 for layer in available):
        status = REPRODUCED
    elif any(int(layer["n_harm"]) >= 2 for layer in available):
        status = REPRODUCTION_MIXED
    else:
        status = NOT_REPRODUCED
    return {
        "comparison_id": "C1",
        "budget_B": int(budget_B),
        "ks": [int(K) for K in ks],
        "layers": layers,
        "status": status,
        "role": "次级复现层，只描述不升级主结论",
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# R-V4-02 / R-V4-04（task-230）：pair-level 结构可辨识性消费层
# ---------------------------------------------------------------------------
INFERENCE_COMPARISON_IDS: tuple[str, ...] = ("C1", "C2", "C3", "C4")
C5_COMPARISON_ID = "C5"
MODEL_SCORED_ARMS: tuple[str, ...] = (
    "PRETRAIN-KSHOT-BO",
    "FOMAML-ZERO-BO",
    "FOMAML-KSHOT-BO",
)
IDENTIFIABILITY_REPORT_FILENAME = "identifiability_report.json"
IDENTIFIABILITY_SCHEMA_VERSION_V4 = "p4ra-s1-identifiability-2"
IDENTIFIABILITY_SCHEMA_VERSIONS: tuple[str, ...] = (
    "p4ra-s1-identifiability-1",
    "p4ra-s1-identifiability-2",
)
IDENTIFIABILITY_OVERLAP_THRESHOLD = 0.90
IDENTIFIABILITY_REQUIRED_PAIRS: tuple[tuple[str, str], ...] = (
    ("FOMAML-ZERO-BO", "FOMAML-KSHOT-BO"),
    ("PRETRAIN-KSHOT-BO", "FOMAML-ZERO-BO"),
    ("PRETRAIN-KSHOT-BO", "FOMAML-KSHOT-BO"),
)
STRUCTURAL_IDENTIFIABLE = "IDENTIFIABLE"
STRUCTURAL_IDENTICAL = "STRUCTURALLY_IDENTICAL"
PAIR_STATUS_NOT_REPORTED = "PAIR_STATUS_NOT_REPORTED"
C5_NOT_ESTIMABLE = "NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY"
C5_DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
C5_ESTIMABLE_MIN_TASKS = 10
IDENTIFIABILITY_MODE_FORMAL = "formal"
IDENTIFIABILITY_MODE_EXPLORATORY = "exploratory"
IDENTIFIABILITY_MODES = (IDENTIFIABILITY_MODE_FORMAL, IDENTIFIABILITY_MODE_EXPLORATORY)
PAIR_LEVEL_FIELDS_SOURCE_RUNNER = "RUNNER_PAIRWISE_FIELDS"
PAIR_LEVEL_FIELDS_SOURCE_DERIVED = "DERIVED_FROM_OVERLAP_RATE_LEGACY_SCHEMA"
PAIR_LEVEL_FIELDS_SOURCE_NONE = "NO_REPORT"
S1_STRUCTURAL_SCHEMA_VERSION = "p4ra-s1-structural-identifiability-1"


# ---------------------------------------------------------------------------
# R-V4-02 / R-V4-04（task-230）：pair-level 结构可辨识性
# ---------------------------------------------------------------------------
def _pair_label(arm_a: str, arm_b: str) -> str:
    """臂对的规范标签：两个臂名排序后以竖线连接（与 runner pair_status_counts 一致）。"""
    return "|".join(sorted((str(arm_a), str(arm_b))))


def _pair_key(arm_a: str, arm_b: str) -> tuple[str, str]:
    """臂对规范键（排序元组），用于 report 组内查表。"""
    return tuple(sorted((str(arm_a), str(arm_b))))


def _canonical_pair_counts(counts: Mapping[Any, Any]) -> dict[str, dict[str, int]]:
    """把 pair_status_counts 规范化为 {arm_a|arm_b: {status: count}}。"""
    normalised: dict[str, dict[str, int]] = {}
    for label, value in counts.items():
        key = str(label)
        if not isinstance(value, Mapping):
            raise S1AnalysisError("identifiability_report.pair_status_counts 的值必须是 object")
        bucket: dict[str, int] = {}
        for status, number in value.items():
            if not _is_int(number):
                raise S1AnalysisError("identifiability_report.pair_status_counts 计数必须是整数")
            bucket[str(status)] = int(number)
        normalised[key] = bucket
    return normalised


@dataclass
class StructuralPairStatus:
    """单个 (task, B, K, meta_seed) 组内一个臂对的结构可辨识性状态。"""

    arm_a: str
    arm_b: str
    overlap_rate: float | None
    threshold: float
    structural_status: str
    pair_identifiable: bool
    schema_source: str

    @property
    def pair_label(self) -> str:
        return _pair_label(self.arm_a, self.arm_b)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm_a": self.arm_a,
            "arm_b": self.arm_b,
            "overlap_rate": self.overlap_rate,
            "threshold": float(self.threshold),
            "pair_identifiable": bool(self.pair_identifiable),
            "structural_status": self.structural_status,
            "schema_source": self.schema_source,
        }


@dataclass
class StructuralIdentifiabilityIndex:
    """消费 runner identifiability_report.json 的只读索引（pair-level）。"""

    present: bool
    mode: str
    schema_versions: list[str]
    threshold: float | None
    groups: dict[tuple[str, int, int, int], dict[tuple[str, str], StructuralPairStatus]]
    source_names: list[str]
    pair_status_counts: dict[str, dict[str, int]]
    pair_level_fields_source: str
    warnings: list[str]
    coverage: dict[str, Any]
    report_group_count: int

    def status_for(
        self,
        task_id: str,
        budget_B: int,
        K: int,
        meta_seed: int,
        arm_a: str,
        arm_b: str,
    ) -> str:
        """返回某组内臂对的 pair-level 状态；无报告时返回 PAIR_STATUS_NOT_REPORTED。"""
        group = self.groups.get((str(task_id), int(budget_B), int(K), int(meta_seed)))
        if not group:
            return PAIR_STATUS_NOT_REPORTED
        status = group.get(_pair_key(arm_a, arm_b))
        return PAIR_STATUS_NOT_REPORTED if status is None else status.structural_status

    def is_structurally_identical(
        self,
        task_id: str,
        budget_B: int,
        K: int,
        meta_seed: int,
        arm_a: str,
        arm_b: str,
    ) -> bool:
        return self.status_for(task_id, budget_B, K, meta_seed, arm_a, arm_b) == STRUCTURAL_IDENTICAL

    def structural_exclusion_counts(self) -> dict[str, int]:
        """按臂对输出 STRUCTURALLY_IDENTICAL 的组数（排除计数）。"""
        counts: dict[str, int] = {}
        for label in sorted(self.pair_status_counts):
            counts[label] = int(self.pair_status_counts[label].get(STRUCTURAL_IDENTICAL, 0))
        return counts

    def to_dict(self) -> dict[str, Any]:
        report_groups = 0
        pair_statuses = 0
        for group in self.groups.values():
            report_groups += 1
            pair_statuses += len(group)
        return {
            "schema_version": S1_STRUCTURAL_SCHEMA_VERSION,
            "present": bool(self.present),
            "mode": self.mode,
            "report_schema_versions": list(self.schema_versions),
            "pair_level_fields_source": self.pair_level_fields_source,
            "threshold": self.threshold,
            "source_names": list(self.source_names),
            "report_group_count": int(self.report_group_count),
            "indexed_group_count": int(report_groups),
            "indexed_pair_status_count": int(pair_statuses),
            "pair_status_counts": {
                label: {status: int(number) for status, number in sorted(counts.items())}
                for label, counts in sorted(self.pair_status_counts.items())
            },
            "structural_exclusion_counts": self.structural_exclusion_counts(),
            "coverage": dict(self.coverage),
            "warnings": list(self.warnings),
            "note": (
                "pair-level 规则来自 R-V4-02/R-V4-04：overlap_rate>=threshold 判 STRUCTURALLY_IDENTICAL，"
                "该臂对在该 (task,B,K,meta_seed) 组不进入 benefit/harm 推断，只描述；不做事后任务剔除"
            ),
        }


def _validate_structural_pairwise(
    pairwise: Any,
    *,
    index: int,
    report_threshold: float,
    schema_version: str,
) -> StructuralPairStatus:
    """校验并解析一个 pairwise 元素（兼容 v1 旧报告：从 overlap_rate 派生 pair 级状态）。"""
    if not isinstance(pairwise, Mapping):
        raise S1AnalysisError(f"identifiability_report.groups[{index}].pairwise 元素必须是 object")
    arm_a = pairwise.get("arm_a")
    arm_b = pairwise.get("arm_b")
    if not isinstance(arm_a, str) or not arm_a:
        raise S1AnalysisError(f"identifiability_report.groups[{index}].pairwise 缺 arm_a")
    if not isinstance(arm_b, str) or not arm_b:
        raise S1AnalysisError(f"identifiability_report.groups[{index}].pairwise 缺 arm_b")
    overlap = pairwise.get("overlap_rate")
    if not _is_finite_number(overlap) or not (0.0 <= float(overlap) <= 1.0):
        raise S1AnalysisError(
            f"identifiability_report.groups[{index}].pairwise.overlap_rate 必须是 [0,1] 内有限数"
        )
    has_pair_fields = ("pair_identifiable" in pairwise) or ("structural_status" in pairwise)
    if schema_version == IDENTIFIABILITY_SCHEMA_VERSION_V4 or has_pair_fields:
        # R-V4-04：新 schema 必须带 pair 级字段，且与 overlap_rate/threshold 自洽。
        if not isinstance(pairwise.get("pair_identifiable"), bool):
            raise S1AnalysisError(
                f"identifiability_report.groups[{index}].pairwise.pair_identifiable 必须是 bool（v4 schema）"
            )
        structural_status = pairwise.get("structural_status")
        if structural_status not in (STRUCTURAL_IDENTIFIABLE, STRUCTURAL_IDENTICAL):
            raise S1AnalysisError(
                f"identifiability_report.groups[{index}].pairwise.structural_status 必须是 "
                f"{STRUCTURAL_IDENTIFIABLE}/{STRUCTURAL_IDENTICAL}（v4 schema）"
            )
        pair_threshold = pairwise.get("threshold")
        if not _is_finite_number(pair_threshold) or not (0.0 < float(pair_threshold) <= 1.0):
            raise S1AnalysisError(
                f"identifiability_report.groups[{index}].pairwise.threshold 必须在 (0,1]（v4 schema）"
            )
        if abs(float(pair_threshold) - float(report_threshold)) > 1e-12:
            raise S1AnalysisError(
                f"identifiability_report.groups[{index}].pairwise.threshold 与 report.threshold 不一致"
            )
        expected_status = (
            STRUCTURAL_IDENTICAL
            if float(overlap) >= float(report_threshold)
            else STRUCTURAL_IDENTIFIABLE
        )
        if structural_status != expected_status:
            raise S1AnalysisError(
                f"identifiability_report.groups[{index}].pairwise.structural_status 与 "
                f"overlap_rate/threshold 不一致（{structural_status} vs {expected_status}）"
            )
        if bool(pairwise.get("pair_identifiable")) != (structural_status == STRUCTURAL_IDENTIFIABLE):
            raise S1AnalysisError(
                f"identifiability_report.groups[{index}].pairwise.pair_identifiable 与 structural_status 不一致"
            )
        source = PAIR_LEVEL_FIELDS_SOURCE_RUNNER
    else:
        # 兼容旧 v1 report（无 pair 级字段）：按预注册规则从 overlap_rate 派生，并在 aggregate 披露。
        expected_status = (
            STRUCTURAL_IDENTICAL
            if float(overlap) >= float(report_threshold)
            else STRUCTURAL_IDENTIFIABLE
        )
        structural_status = expected_status
        source = PAIR_LEVEL_FIELDS_SOURCE_DERIVED
    return StructuralPairStatus(
        arm_a=str(arm_a),
        arm_b=str(arm_b),
        overlap_rate=float(overlap),
        threshold=float(report_threshold),
        structural_status=str(structural_status),
        pair_identifiable=bool(structural_status == STRUCTURAL_IDENTIFIABLE),
        schema_source=source,
    )


def load_identifiability_report(path: str | Path) -> dict[str, Any]:
    """加载并校验单个 identifiability_report.json（schema/threshold/组/pairwise/顶层计数）。"""
    target = Path(path)
    payload, _raw = _read_json_file(target, "identifiability_report")
    if not isinstance(payload, Mapping):
        raise S1AnalysisError("identifiability_report.json 必须是 JSON object")
    schema_version = payload.get("schema_version")
    if schema_version not in IDENTIFIABILITY_SCHEMA_VERSIONS:
        raise S1AnalysisError(
            "identifiability_report.schema_version 不受支持："
            + repr(schema_version)
            + "；期望 "
            + repr(list(IDENTIFIABILITY_SCHEMA_VERSIONS))
        )
    threshold = payload.get("threshold")
    if not _is_finite_number(threshold) or not (0.0 < float(threshold) <= 1.0):
        raise S1AnalysisError("identifiability_report.threshold 必须在 (0,1] 内")
    groups_payload = payload.get("groups")
    if not isinstance(groups_payload, list):
        raise S1AnalysisError("identifiability_report.groups 必须是 list")
    groups: dict[tuple[str, int, int, int], dict[tuple[str, str], StructuralPairStatus]] = {}
    computed_counts: dict[str, dict[str, int]] = {}
    for index, group in enumerate(groups_payload):
        if not isinstance(group, Mapping):
            raise S1AnalysisError(f"identifiability_report.groups[{index}] 必须是 object")
        task_id = group.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise S1AnalysisError(f"identifiability_report.groups[{index}].task_id 必须是非空字符串")
        budget = group.get("budget_B")
        k_shot = group.get("K")
        meta_seed = group.get("meta_seed")
        if not _is_int(budget) or not _is_int(k_shot) or not _is_int(meta_seed):
            raise S1AnalysisError(
                f"identifiability_report.groups[{index}] 的 budget_B/K/meta_seed 必须是整数"
            )
        pairwise_payload = group.get("pairwise")
        if not isinstance(pairwise_payload, list) or not pairwise_payload:
            raise S1AnalysisError(
                f"identifiability_report.groups[{index}].pairwise 必须是非空 list"
            )
        key = (task_id, int(budget), int(k_shot), int(meta_seed))
        if key in groups:
            raise S1AnalysisError(
                "identifiability_report 组重复：" + "|".join(str(item) for item in key)
            )
        statuses: dict[tuple[str, str], StructuralPairStatus] = {}
        for pair in pairwise_payload:
            status = _validate_structural_pairwise(
                pair,
                index=index,
                report_threshold=float(threshold),
                schema_version=str(schema_version),
            )
            pair_key = _pair_key(status.arm_a, status.arm_b)
            if pair_key in statuses:
                raise S1AnalysisError(
                    f"identifiability_report.groups[{index}].pairwise 臂对重复：{status.pair_label}"
                )
            statuses[pair_key] = status
            bucket = computed_counts.setdefault(status.pair_label, {})
            bucket[status.structural_status] = bucket.get(status.structural_status, 0) + 1
        arms_listed = group.get("arms")
        if arms_listed is not None:
            if not isinstance(arms_listed, list) or any(
                not isinstance(item, str) for item in arms_listed
            ):
                raise S1AnalysisError(
                    f"identifiability_report.groups[{index}].arms 必须是字符串 list"
                )
            reported_arms = set(arms_listed)
            known_arms = {
                arm for pair in statuses.values() for arm in (pair.arm_a, pair.arm_b)
            }
            if not known_arms <= reported_arms:
                raise S1AnalysisError(
                    f"identifiability_report.groups[{index}].arms 与 pairwise 不一致"
                )
        groups[key] = statuses
    declared_counts = payload.get("pair_status_counts")
    if declared_counts is not None:
        declared = _canonical_pair_counts(declared_counts)
        for label in sorted(set(declared) | set(computed_counts)):
            declared_bucket = declared.get(label, {})
            computed_bucket = computed_counts.get(label, {})
            filtered_declared = {
                key: int(value) for key, value in declared_bucket.items() if int(value) != 0
            }
            filtered_computed = {
                key: int(value) for key, value in computed_bucket.items() if int(value) != 0
            }
            if filtered_declared != filtered_computed:
                raise S1AnalysisError(
                    "identifiability_report.pair_status_counts 与实际 pairwise 计数不一致：" + label
                )
    elif schema_version == IDENTIFIABILITY_SCHEMA_VERSION_V4:
        raise S1AnalysisError(
            "v4 identifiability_report 必须提供顶层 pair_status_counts（R-V4-04）"
        )
    declared_group_count = payload.get("group_count")
    if declared_group_count is not None:
        if not _is_int(declared_group_count) or int(declared_group_count) != len(groups):
            raise S1AnalysisError(
                "identifiability_report.group_count 与 groups 实际数量不一致"
            )
    declared_status_counts = payload.get("status_counts")
    if declared_status_counts is not None and not isinstance(declared_status_counts, Mapping):
        raise S1AnalysisError("identifiability_report.status_counts 必须是 object")
    return {
        "schema_version": str(schema_version),
        "threshold": float(threshold),
        "groups": groups,
        "pair_status_counts": computed_counts,
        "source": target.name,
    }


def _report_dirs_from_sources(sources: Sequence[Any]) -> list[Path]:
    """从 run_records 来源路径推导 run 目录（用于定位 identifiability_report.json）。"""
    dirs: list[Path] = []
    seen: set[str] = set()
    for source in sources:
        path = Path(source)
        directory = path if path.is_dir() else path.parent
        key = str(directory.resolve())
        if key not in seen:
            seen.add(key)
            dirs.append(directory)
    return dirs


def resolve_identifiability_report_paths(
    sources: Sequence[Any],
    *,
    explicit_paths: Sequence[Any] | None = None,
) -> tuple[list[Path], list[Path]]:
    """解析 report 路径：返回 (已存在的 report 路径, 缺 report 的 run 目录）。"""
    report_paths: list[Path] = []
    seen_paths: set[str] = set()
    if explicit_paths is not None:
        for item in explicit_paths:
            path = Path(item)
            if not path.is_file():
                raise S1AnalysisError(f"显式指定的 identifiability_report 不存在：{path.name}")
            key = str(path.resolve())
            if key not in seen_paths:
                seen_paths.add(key)
                report_paths.append(path)
    missing_dirs: list[Path] = []
    for directory in _report_dirs_from_sources(sources):
        candidate = directory / IDENTIFIABILITY_REPORT_FILENAME
        if candidate.is_file():
            key = str(candidate.resolve())
            if key not in seen_paths:
                seen_paths.add(key)
                report_paths.append(candidate)
        else:
            missing_dirs.append(directory)
    return report_paths, missing_dirs


def _empty_structural_index(mode: str, *, warnings: Sequence[str], coverage: Mapping[str, Any]) -> StructuralIdentifiabilityIndex:
    """构造「无报告」索引（exploratory 允许缺失时使用；formal 永远 fail-closed）。"""
    return StructuralIdentifiabilityIndex(
        present=False,
        mode=str(mode),
        schema_versions=[],
        threshold=None,
        groups={},
        source_names=[],
        pair_status_counts={},
        pair_level_fields_source=PAIR_LEVEL_FIELDS_SOURCE_NONE,
        warnings=[str(item) for item in warnings],
        coverage=dict(coverage),
        report_group_count=0,
    )


def _merge_structural_reports(
    report_paths: Sequence[Path],
    *,
    mode: str,
) -> dict[str, Any]:
    """加载并合并多个 report（同组跨 report 必须完全一致）。"""
    merged: dict[tuple[str, int, int, int], dict[tuple[str, str], StructuralPairStatus]] = {}
    schema_versions: set[str] = set()
    thresholds: set[float] = set()
    source_names: list[str] = []
    report_group_count = 0
    sources_seen: set[str] = set()
    pair_level_sources: set[str] = set()
    for path in report_paths:
        loaded = load_identifiability_report(path)
        schema_versions.add(loaded["schema_version"])
        thresholds.add(float(loaded["threshold"]))
        report_group_count += len(loaded["groups"])
        if path.name not in sources_seen:
            sources_seen.add(path.name)
            source_names.append(path.name)
        for key, statuses in loaded["groups"].items():
            if key in merged:
                existing = {
                    pair_key: status.to_dict() for pair_key, status in merged[key].items()
                }
                incoming = {
                    pair_key: status.to_dict() for pair_key, status in statuses.items()
                }
                if existing != incoming:
                    raise S1AnalysisError(
                        "同组 report 在多个文件中不一致："
                        + "|".join(str(item) for item in key)
                    )
                continue
            merged[key] = dict(statuses)
            pair_level_sources.update(status.schema_source for status in statuses.values())
    if len(thresholds) > 1:
        raise S1AnalysisError(
            "多个 identifiability_report 的 threshold 不一致：" + repr(sorted(thresholds))
        )
    if pair_level_sources == {PAIR_LEVEL_FIELDS_SOURCE_RUNNER}:
        fields_source = PAIR_LEVEL_FIELDS_SOURCE_RUNNER
    elif pair_level_sources == {PAIR_LEVEL_FIELDS_SOURCE_DERIVED}:
        fields_source = PAIR_LEVEL_FIELDS_SOURCE_DERIVED
    elif pair_level_sources:
        fields_source = "MIXED"
    else:
        fields_source = PAIR_LEVEL_FIELDS_SOURCE_NONE
    return {
        "groups": merged,
        "schema_versions": sorted(schema_versions),
        "threshold": min(thresholds) if thresholds else None,
        "source_names": sorted(source_names),
        "report_group_count": int(report_group_count),
        "pair_level_fields_source": fields_source,
        "mode": str(mode),
    }


def load_structural_identifiability(
    sources: Sequence[Any],
    records: Sequence[Mapping[str, Any]],
    *,
    mode: str = "formal",
    allow_missing: bool = False,
    explicit_report_paths: Sequence[Any] | None = None,
) -> StructuralIdentifiabilityIndex:
    """加载 run 目录的 identifiability_report.json 并校验与 run_records 的组/臂覆盖一致。

    R-V4-02/R-V4-04：
      - formal 模式：report 缺失、组覆盖不全或臂覆盖不全 → fail-closed（不得出结论）。
      - exploratory 模式：仅当 allow_missing=True 时允许缺失，降级为 warning。
      - 规则在读取数据前固定：overlap_rate >= threshold 即 STRUCTURALLY_IDENTICAL，
        该 (task,B,K,meta_seed) 组的该臂对不进入 benefit/harm 推断，但不做事后任务剔除。
    """
    if mode not in IDENTIFIABILITY_MODES:
        raise S1AnalysisError(
            "identifiability_mode 必须是 " + "/".join(IDENTIFIABILITY_MODES) + "： " + repr(mode)
        )
    if mode == "formal" and allow_missing:
        raise S1AnalysisError(
            "formal 模式不允许 allow_missing_identifiability_report=True（缺失必须 fail-closed）"
        )
    report_paths, missing_dirs = resolve_identifiability_report_paths(
        sources, explicit_paths=explicit_report_paths
    )
    warnings: list[str] = []
    if missing_dirs:
        names = ", ".join(sorted(directory.name for directory in missing_dirs))
        message = (
            f"{len(missing_dirs)} 个 run 目录缺少 {IDENTIFIABILITY_REPORT_FILENAME}：{names}"
        )
        if mode == "formal":
            raise S1AnalysisError(
                message + "；formal 模式必须 fail-closed（R-V4-04），拒绝产出推断结论"
            )
        if not allow_missing:
            raise S1AnalysisError(
                message + "；exploratory 模式需显式 allow_missing_identifiability_report=True"
            )
        warnings.append(message + "；exploratory 模式按 allow_missing 降级，pair 级规则不可用")
    merged = _merge_structural_reports(report_paths, mode=mode) if report_paths else {
        "groups": {},
        "schema_versions": [],
        "threshold": None,
        "source_names": [],
        "report_group_count": 0,
        "pair_level_fields_source": PAIR_LEVEL_FIELDS_SOURCE_NONE,
        "mode": str(mode),
    }
    groups = merged["groups"]
    # 从 run_records 推导期望组：凡出现任一 model-scored 臂的 (task,B,K,meta_seed)。
    expected_arms: dict[tuple[str, int, int, int], set[str]] = {}
    for item in records:
        arm = item.get("arm")
        if arm not in MODEL_SCORED_ARMS:
            continue
        task_id = item.get("task_id")
        budget = item.get("budget_B")
        k_shot = item.get("K")
        meta_seed = item.get("meta_seed")
        if not isinstance(task_id, str):
            continue
        if not _is_int(budget) or not _is_int(k_shot) or not _is_int(meta_seed):
            continue
        key = (task_id, int(budget), int(k_shot), int(meta_seed))
        expected_arms.setdefault(key, set()).add(str(arm))
    missing_groups = sorted({key for key in expected_arms if key not in groups}, key=str)
    arm_gaps: list[str] = []
    for key, arms in expected_arms.items():
        statuses = groups.get(key)
        if not statuses:
            continue
        reported_arms = {arm for pair in statuses.values() for arm in (pair.arm_a, pair.arm_b)}
        if not arms <= reported_arms:
            arm_gaps.append("|".join(str(item) for item in key))
    extra_groups = len(set(groups) - set(expected_arms))
    pair_gaps: list[str] = []
    for key, arms in expected_arms.items():
        statuses = groups.get(key)
        if not statuses:
            continue
        order = sorted(arms)
        for first_index in range(len(order)):
            for second_index in range(first_index + 1, len(order)):
                if _pair_key(order[first_index], order[second_index]) not in statuses:
                    pair_gaps.append(
                        "|".join(str(item) for item in key) + "::" + _pair_label(order[first_index], order[second_index])
                    )
    coverage = {
        "model_scored_arms": list(MODEL_SCORED_ARMS),
        "records_model_scored_groups": len(expected_arms),
        "report_group_count": int(merged["report_group_count"]),
        "indexed_group_count": len(groups),
        "missing_group_count": len(missing_groups),
        "missing_groups_sample": ["|".join(str(item) for item in key) for key in missing_groups[:5]],
        "arm_gap_count": len(arm_gaps),
        "arm_gaps_sample": arm_gaps[:5],
        "pair_gap_count": len(pair_gaps),
        "pair_gaps_sample": pair_gaps[:5],
        "extra_group_count": int(extra_groups),
        "missing_report_run_dirs": len(missing_dirs),
        "threshold": merged["threshold"],
        "pair_level_fields_source": merged["pair_level_fields_source"],
        "rule": "overlap_rate>=threshold => STRUCTURALLY_IDENTICAL；该组该臂对不进入 benefit/harm 推断；不做事后任务剔除",
    }
    problems: list[str] = []
    if missing_groups:
        problems.append(
            f"identifiability_report 组覆盖不全：缺 {len(missing_groups)} 组（前 5：{coverage['missing_groups_sample']}）"
        )
    if arm_gaps:
        problems.append(
            f"identifiability_report 臂覆盖不全：{len(arm_gaps)} 组（前 5：{coverage['arm_gaps_sample']}）"
        )
    if pair_gaps:
        problems.append(
            f"identifiability_report 臂对覆盖不全：{len(pair_gaps)} 组（前 5：{coverage['pair_gaps_sample']}）"
        )
    if problems:
        message = "；".join(problems)
        if mode == "formal":
            raise S1AnalysisError(
                message + "；与 run_records 不一致，formal 模式 fail-closed（R-V4-04）"
            )
        if not allow_missing:
            raise S1AnalysisError(
                message + "；exploratory 模式需显式 allow_missing_identifiability_report=True"
            )
        warnings.append(message + "；exploratory 模式按 allow_missing 降级")
    if merged["pair_level_fields_source"] == PAIR_LEVEL_FIELDS_SOURCE_DERIVED:
        warnings.append(
            "identifiability_report 为 v1 旧 schema（无 pair 级字段）；已按预注册规则由 overlap_rate>=threshold 派生，"
            "正式 v4 工件应由 runner 直接写入 pair_identifiable/structural_status"
        )
    pair_status_counts: dict[str, dict[str, int]] = {}
    for statuses in groups.values():
        for status in statuses.values():
            bucket = pair_status_counts.setdefault(status.pair_label, {})
            bucket[status.structural_status] = bucket.get(status.structural_status, 0) + 1
    return StructuralIdentifiabilityIndex(
        present=bool(groups),
        mode=str(mode),
        schema_versions=list(merged["schema_versions"]),
        threshold=merged["threshold"],
        groups=groups,
        source_names=list(merged["source_names"]),
        pair_status_counts=pair_status_counts,
        pair_level_fields_source=str(merged["pair_level_fields_source"]),
        warnings=warnings,
        coverage=coverage,
        report_group_count=int(merged["report_group_count"]),
    )


def comparison_structural_exclusion_counts(
    index: StructuralIdentifiabilityIndex,
    *,
    comparisons: Sequence[Mapping[str, str]] = COMPARISONS,
) -> dict[str, Any]:
    """按预注册比较输出 pair-level STRUCTURALLY_IDENTICAL 组数（R-V4-04 披露要求）。"""
    by_pair = index.structural_exclusion_counts()
    by_comparison: dict[str, int] = {}
    for item in comparisons:
        label = _pair_label(item["arm"], item["reference"])
        by_comparison[str(item["id"])] = int(by_pair.get(label, 0))
    return {
        "by_pair": {label: int(value) for label, value in sorted(by_pair.items())},
        "by_comparison": {key: by_comparison[key] for key in sorted(by_comparison)},
        "total": int(sum(by_pair.values())),
        "rule": "pair-level：overlap_rate>=threshold => STRUCTURALLY_IDENTICAL；仅排除该 (task,B,K,meta_seed) 组的该臂对，不剔除任务",
    }


def _c5_pair_status(
    index: StructuralIdentifiabilityIndex,
    task_id: str,
    budget: int,
    k_shot: int,
    meta_seed: int,
) -> str:
    comparison = COMPARISON_BY_ID[C5_COMPARISON_ID]
    return index.status_for(
        task_id, budget, k_shot, meta_seed, comparison["arm"], comparison["reference"]
    )


def c5_structural_summary(
    cells: Mapping[tuple[str, int, int, str], AggregatedCell],
    bundle: FrozenBundle,
    index: StructuralIdentifiabilityIndex,
    *,
    split: str = MAIN_SPLIT,
    budgets: Sequence[int] = MAIN_POPULATION_BUDGETS,
    inference_ks: Sequence[int] | None = None,
) -> dict[str, Any]:
    """C5（FOMAML-KSHOT-BO vs FOMAML-ZERO-BO）描述层：不进 Holm、不做 benefit/harm 判定。

    R-V4-02：C5 只报告结构性克隆率与描述性数值；若可估计任务数 < C5_ESTIMABLE_MIN_TASKS（10），
    固定 NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY，不得声称适应增益/损害。
    """
    if inference_ks is None:
        inference_ks = INFERENCE_KS
    comparison = COMPARISON_BY_ID[C5_COMPARISON_ID]
    treatment = str(comparison["arm"])
    reference = str(comparison["reference"])
    split_tasks = list(bundle.task_ids_for(split))
    split_task_set = set(split_tasks)
    pair_label = _pair_label(treatment, reference)
    layers: list[dict[str, Any]] = []
    estimable_tasks: set[str] = set()
    total_groups = 0
    identical_groups = 0
    for budget in budgets:
        for k_shot in inference_ks:
            layer = {
                "budget_B": int(budget),
                "K": int(k_shot),
                "pair_label": pair_label,
                "total_groups": 0,
                "structurally_identical_groups": 0,
                "estimable_tasks": 0,
                "estimable_task_ids": [],
                "clone_rate": None,
            }
            treatment_cell = cells.get((split, int(budget), int(k_shot), treatment))
            reference_cell = cells.get((split, int(budget), int(k_shot), reference))
            for task_id in split_tasks:
                usable = False
                for meta_seed in bundle.meta_seeds:
                    status = _c5_pair_status(index, task_id, int(budget), int(k_shot), int(meta_seed))
                    if status == PAIR_STATUS_NOT_REPORTED:
                        continue
                    layer["total_groups"] += 1
                    total_groups += 1
                    if status == STRUCTURAL_IDENTICAL:
                        layer["structurally_identical_groups"] += 1
                        identical_groups += 1
                    else:
                        usable = True
                if usable:
                    layer["estimable_tasks"] += 1
                    layer["estimable_task_ids"].append(task_id)
                    estimable_tasks.add(task_id)
            if layer["total_groups"]:
                layer["clone_rate"] = float(
                    layer["structurally_identical_groups"] / layer["total_groups"]
                )
            for endpoint in PRIMARY_ENDPOINTS:
                treatment_values = [
                    treatment_cell.endpoint_per_task.get(task_id, {}).get(endpoint)
                    for task_id in layer["estimable_task_ids"]
                ] if treatment_cell is not None else []
                reference_values = [
                    reference_cell.endpoint_per_task.get(task_id, {}).get(endpoint)
                    for task_id in layer["estimable_task_ids"]
                ] if reference_cell is not None else []
                paired = [
                    (float(item[0]), float(item[1]))
                    for item in zip(treatment_values, reference_values)
                    if item[0] is not None and item[1] is not None
                ]
                treatment_mean = (
                    float(sum(item[0] for item in paired) / len(paired)) if paired else None
                )
                reference_mean = (
                    float(sum(item[1] for item in paired) / len(paired)) if paired else None
                )
                mean_difference = (
                    float(treatment_mean - reference_mean)
                    if treatment_mean is not None and reference_mean is not None
                    else None
                )
                layer.setdefault("descriptive_rows", []).append(
                    {
                        "comparison_id": C5_COMPARISON_ID,
                        "split": split,
                        "budget_B": int(budget),
                        "K": int(k_shot),
                        "endpoint": endpoint,
                        "treatment": treatment,
                        "reference": reference,
                        "n_tasks_estimable": int(len(paired)),
                        "treatment_mean": treatment_mean,
                        "reference_mean": reference_mean,
                        "mean_difference": mean_difference,
                        "inference": False,
                        "note": (
                            "C5 仅描述：不进 Holm、不做 benefit/harm 判定、无 p 值与 CI；"
                            "STRUCTURALLY_IDENTICAL 的 (task,B,K,meta_seed) 组不参与均值"
                        ),
                    }
                )
            layers.append(layer)
    estimable_count = len(estimable_tasks)
    clone_rate = float(identical_groups / total_groups) if total_groups else None
    if (not index.present) or estimable_count < C5_ESTIMABLE_MIN_TASKS:
        status = C5_NOT_ESTIMABLE
        if not index.present:
            reason = "identifiability_report 缺失，C5 结构可辨识性不可得"
        else:
            reason = (
                f"C5 可估计任务数 {estimable_count} < {C5_ESTIMABLE_MIN_TASKS}（R-V4-02），"
                "固定 NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY，不得声称适应增益/损害"
            )
    else:
        status = C5_DESCRIPTIVE_ONLY
        reason = (
            f"C5 可估计任务数 {estimable_count} >= {C5_ESTIMABLE_MIN_TASKS}；"
            "按 R-V4-02 仅作描述性报告（不进 Holm、不做 benefit/harm 判定）"
        )
    descriptive_rows = [
        row for layer in layers for row in layer.get("descriptive_rows", [])
    ]
    return {
        "schema_version": S1_STRUCTURAL_SCHEMA_VERSION,
        "comparison_id": C5_COMPARISON_ID,
        "treatment": treatment,
        "reference": reference,
        "split": split,
        "status": status,
        "estimable_tasks": int(estimable_count),
        "total_tasks": int(len(split_tasks)),
        "min_estimable_tasks": int(C5_ESTIMABLE_MIN_TASKS),
        "total_groups": int(total_groups),
        "structurally_identical_groups": int(identical_groups),
        "clone_rate": clone_rate,
        "structural_exclusion_count": int(
            index.structural_exclusion_counts().get(pair_label, 0)
        ),
        "in_holm": False,
        "benefit_harm_decision": None,
        "layers": layers,
        "descriptive_rows": descriptive_rows,
        "reason": reason,
        "rule": "C5 不进 Holm 族、不做 benefit/harm；STRUCTURALLY_IDENTICAL 组仅描述；不做事后任务剔除",
    }


def _split_for_task(bundle: FrozenBundle, task_id: str) -> str | None:
    for split in RECORD_SPLITS:
        if task_id in set(bundle.task_ids_for(split)):
            return str(split)
    return None


def _inference_pair_labels() -> set[str]:
    return {
        _pair_label(item["arm"], item["reference"])
        for item in COMPARISONS
        if str(item["id"]) in INFERENCE_COMPARISON_IDS
    }


def structural_identifiability_rows(
    index: StructuralIdentifiabilityIndex,
    bundle: FrozenBundle,
    c5_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """生成 s1_structural_identifiability.csv 行（R-V4-04：披露 pair 级排除与 C5 可估计任务数）。"""
    inference_labels = _inference_pair_labels()
    c5_label = _pair_label(c5_summary["treatment"], c5_summary["reference"])
    rows: list[dict[str, Any]] = []
    for key in sorted(index.groups, key=str):
        task_id, budget, k_shot, meta_seed = key
        split = _split_for_task(bundle, task_id)
        for pair_key in sorted(index.groups[key]):
            status = index.groups[key][pair_key]
            identical = status.structural_status == STRUCTURAL_IDENTICAL
            if status.pair_label == c5_label:
                inference_role = "C5_DESCRIPTIVE_ONLY"
                used_in_inference = False
            elif status.pair_label in inference_labels:
                inference_role = "INFERENCE_PREREGISTERED"
                used_in_inference = not identical
            else:
                inference_role = "DESCRIPTIVE"
                used_in_inference = False
            rows.append(
                {
                    "row_type": "pair_group",
                    "split": split,
                    "budget_B": int(budget),
                    "K": int(k_shot),
                    "task_id": task_id,
                    "meta_seed": int(meta_seed),
                    "arm_a": status.arm_a,
                    "arm_b": status.arm_b,
                    "overlap_rate": status.overlap_rate,
                    "threshold": status.threshold,
                    "pair_identifiable": status.pair_identifiable,
                    "structural_status": status.structural_status,
                    "inference_role": inference_role,
                    "used_in_inference": bool(used_in_inference),
                    "n_groups": None,
                    "n_structurally_identical": None,
                    "n_identifiable": None,
                    "exclusion_rate": None,
                    "c5_estimable_tasks": None,
                    "status": status.structural_status,
                    "note": (
                        "pair-level 排除规则（R-V4-02/R-V4-04）：STRUCTURALLY_IDENTICAL 组不进入 benefit/harm 推断；"
                        "不做事后任务剔除"
                    ),
                }
            )
    pair_counts: dict[str, dict[str, int]] = index.pair_status_counts
    for label in sorted(pair_counts):
        bucket = pair_counts[label]
        total = int(sum(bucket.values()))
        identical = int(bucket.get(STRUCTURAL_IDENTICAL, 0))
        identifiable = int(bucket.get(STRUCTURAL_IDENTIFIABLE, 0))
        arms = label.split("|")
        if label == c5_label:
            inference_role = "C5_DESCRIPTIVE_ONLY"
        elif label in inference_labels:
            inference_role = "INFERENCE_PREREGISTERED"
        else:
            inference_role = "DESCRIPTIVE"
        rows.append(
            {
                "row_type": "exclusion_summary",
                "split": None,
                "budget_B": None,
                "K": None,
                "task_id": None,
                "meta_seed": None,
                "arm_a": arms[0] if len(arms) > 0 else None,
                "arm_b": arms[1] if len(arms) > 1 else None,
                "overlap_rate": None,
                "threshold": index.threshold,
                "pair_identifiable": None,
                "structural_status": None,
                "inference_role": inference_role,
                "used_in_inference": None,
                "n_groups": total,
                "n_structurally_identical": identical,
                "n_identifiable": identifiable,
                "exclusion_rate": float(identical / total) if total else None,
                "c5_estimable_tasks": None,
                "status": "EXCLUSION_SUMMARY",
                "note": "按臂对聚合的 STRUCTURALLY_IDENTICAL 组数（R-V4-04 structural_exclusion_counts）",
            }
        )
    for layer in c5_summary.get("layers", []):
        rows.append(
            {
                "row_type": "c5_summary",
                "split": c5_summary.get("split"),
                "budget_B": int(layer["budget_B"]),
                "K": int(layer["K"]),
                "task_id": None,
                "meta_seed": None,
                "arm_a": c5_summary["treatment"],
                "arm_b": c5_summary["reference"],
                "overlap_rate": None,
                "threshold": index.threshold,
                "pair_identifiable": None,
                "structural_status": None,
                "inference_role": "C5_DESCRIPTIVE_ONLY",
                "used_in_inference": False,
                "n_groups": int(layer["total_groups"]),
                "n_structurally_identical": int(layer["structurally_identical_groups"]),
                "n_identifiable": int(
                    layer["total_groups"] - layer["structurally_identical_groups"]
                ),
                "exclusion_rate": layer.get("clone_rate"),
                "c5_estimable_tasks": int(layer["estimable_tasks"]),
                "status": c5_summary.get("status"),
                "note": "C5 仅描述（不进 Holm、无 p 值/CI/benefit-harm 判定）：" + str(
                    c5_summary.get("reason")
                ),
            }
        )
    return rows


# 输出层：聚合产物、CSV、figure_status 与 CLI
# ---------------------------------------------------------------------------
S1_OUTPUT_FILES = (
    "aggregate.json",
    "s1_endpoint_tables.csv",
    "s1_identifiability_table.csv",
    "s1_structural_identifiability.csv",
    "s1_budget_audit.csv",
    "s1_negative_controls.csv",
    "s1_freeze_identity.csv",
    "figure_status.json",
)
# task-239：冻结身份（五项 + 来源）记录列；正式 run 必须由 run_config 传入期望值。
FREEZE_IDENTITY_COLUMNS = (
    "identity_source",
    "family_version",
    "family_fingerprint",
    "split_hash",
    "prereg_digest",
    "analysis_plan_digest",
    "radius_base",
    "expected_identity_fields",
)
FIGURE_KEYS = (
    "fig1_meta_training_loss",
    "fig2_k_shot_adaptation",
    "fig3_feasible_rate",
    "fig4_equal_budget_gap",
    "fig5_fairness_audit",
    "fig6_k_sweep_delta",
    "fig7_negative_control_and_determinism",
)
ENDPOINT_TABLE_COLUMNS = (
    "row_type",
    "split",
    "budget_B",
    "K",
    "comparison_id",
    "role",
    "arm",
    "reference",
    "endpoint",
    "n_tasks",
    "n_nonnull",
    "null_rate",
    "mean",
    "median",
    "sd",
    "min",
    "max",
    "n_pairs",
    "mean_difference",
    "median_difference",
    "cohens_d",
    "rank_biserial",
    "improvement",
    "ci_low",
    "ci_high",
    "wilcoxon_statistic",
    "wilcoxon_w_plus",
    "wilcoxon_w_minus",
    "p_raw",
    "p_adjusted",
    "test_method",
    "zero_count",
    "threshold",
    "max_null_rate",
    "decision",
    "decision_reasons",
    "note",
)
NEGATIVE_CONTROL_COLUMNS = (
    "check",
    "split",
    "comparison_id",
    "budget_B",
    "K",
    "endpoint",
    "treatment",
    "reference",
    "n_tasks",
    "n_pairs",
    "null_rate_treatment",
    "null_rate_reference",
    "mean_difference",
    "improvement",
    "p_raw",
    "decision",
    "expected",
    "status",
    "note",
)
IDENTIFIABILITY_COLUMNS = (
    "split",
    "arm",
    "budget_B",
    "K",
    "n_runs",
    "labels",
    "n_identifiable",
    "n_clone",
    "inference_eligible",
    "note",
)
STRUCTURAL_IDENTIFIABILITY_COLUMNS = (
    "row_type",
    "split",
    "budget_B",
    "K",
    "task_id",
    "meta_seed",
    "arm_a",
    "arm_b",
    "overlap_rate",
    "threshold",
    "pair_identifiable",
    "structural_status",
    "inference_role",
    "used_in_inference",
    "n_groups",
    "n_structurally_identical",
    "n_identifiable",
    "exclusion_rate",
    "c5_estimable_tasks",
    "status",
    "note",
)
BUDGET_AUDIT_COLUMNS = (
    "split",
    "arm",
    "budget_B",
    "K",
    "n_runs",
    "expected_billable",
    "billable_values",
    "support_values",
    "initial_values",
    "bo_values",
    "n_ok",
    "n_failed",
    "n_clone",
    "inference_eligible",
)
NON_INFERENTIAL_NOTE = "K=0 CLONE 仅描述、排除推断"
PRIMARY_KS = (3, 5)
EXPLORATORY_KS = (1,)
INFERENCE_KS = EXPLORATORY_KS + PRIMARY_KS




def _stats(values: Sequence[float]) -> dict[str, float | None]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {"mean": None, "median": None, "sd": None, "min": None, "max": None}
    n = len(numbers)
    mean_value = sum(numbers) / n
    sorted_values = sorted(numbers)
    middle = n // 2
    median_value = sorted_values[middle] if n % 2 == 1 else (sorted_values[middle - 1] + sorted_values[middle]) / 2.0
    sd = None
    if n >= 2:
        variance = sum((value - mean_value) ** 2 for value in numbers) / (n - 1)
        sd = math.sqrt(variance)
    return {
        "mean": float(mean_value),
        "median": float(median_value),
        "sd": None if sd is None else float(sd),
        "min": float(min(numbers)),
        "max": float(max(numbers)),
    }


def build_arm_summary_rows(
    cells: Mapping[tuple[str, int, int, str], AggregatedCell],
    bundle: FrozenBundle,
    *,
    split: str,
) -> list[dict[str, Any]]:
    """每个 (B, K, arm) x 端点 的任务级描述统计行（含 K=0 描述层）。"""
    rows: list[dict[str, Any]] = []
    for key in sorted(cells):
        cell = cells[key]
        if cell.split != split:
            continue
        task_ids = list(bundle.task_ids_for(split))
        for endpoint in tuple(PRIMARY_ENDPOINTS) + tuple(SECONDARY_ENDPOINTS):
            raw = [cell.endpoint_per_task.get(task_id, {}).get(endpoint) for task_id in task_ids]
            values = [value for value in raw if value is not None]
            null_rate = (len(raw) - len(values)) / len(raw) if raw else 1.0
            stats = _stats(values)
            clone = cell.K == 0 and cell.arm == CLONE_ALLOWED["arm"]
            row = {
                "row_type": "arm_summary",
                "split": split,
                "budget_B": int(cell.budget_B),
                "K": int(cell.K),
                "comparison_id": "",
                "role": "descriptive",
                "arm": cell.arm,
                "reference": "",
                "endpoint": endpoint,
                "n_tasks": int(cell.n_tasks),
                "n_nonnull": int(len(values)),
                "null_rate": float(null_rate),
                "mean": stats["mean"],
                "median": stats["median"],
                "sd": stats["sd"],
                "min": stats["min"],
                "max": stats["max"],
                "n_pairs": "",
                "mean_difference": "",
                "median_difference": "",
                "cohens_d": "",
                "rank_biserial": "",
                "improvement": "",
                "ci_low": "",
                "ci_high": "",
                "wilcoxon_statistic": "",
                "wilcoxon_w_plus": "",
                "wilcoxon_w_minus": "",
                "p_raw": "",
                "p_adjusted": "",
                "test_method": "",
                "zero_count": "",
                "threshold": "",
                "max_null_rate": "",
                "decision": "DESCRIPTIVE",
                "decision_reasons": "",
                "note": (
                    NON_INFERENTIAL_NOTE
                    if clone
                    else ("描述统计（无推断）" if endpoint in SECONDARY_ENDPOINTS else "端点描述统计")
                ),
            }
            rows.append(row)
    return rows


def _hypothesis_rows(
    cells: Mapping[tuple[str, int, int, str], AggregatedCell],
    bundle: FrozenBundle,
    structural_index: "StructuralIdentifiabilityIndex | None" = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """返回假设行与 Holm 族信息（M02：族大小、族计数必须随 aggregate 输出）。"""
    collected = collect_hypotheses(
        cells,
        bundle,
        split=MAIN_SPLIT,
        inference_ks=INFERENCE_KS,
        structural_index=structural_index,
    )
    family_info = {
        "holm_family_definition": collected["holm_family_definition"],
        "holm_family_key_fields": list(collected["holm_family_key_fields"]),
        "holm_family_size_dynamic": bool(collected["holm_family_size_dynamic"]),
        "holm_family_max_size": int(collected["holm_family_max_size"]),
        "holm_family_size_min": int(collected["holm_family_size_min"]),
        "holm_family_size_max": int(collected["holm_family_size_max"]),
        "holm_family_size_counts": dict(collected["holm_family_size_counts"]),
        "holm_family_count": collected["holm_family_count"],
        "holm_family_sizes": collected["holm_family_sizes"],
        "inference_comparison_ids": list(collected["inference_comparison_ids"]),
        "excluded_comparison_ids": collected["excluded_comparison_ids"],
        "structural_index_present": collected["structural_index_present"],
        "structural_exclusion_total": collected["structural_exclusion_total"],
    }
    return list(collected["rows"]), family_info


def _endpoint_table_rows(
    cells: Mapping[tuple[str, int, int, str], AggregatedCell],
    bundle: FrozenBundle,
    hypothesis_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split in RECORD_SPLITS:
        rows.extend(build_arm_summary_rows(cells, bundle, split=split))
    for hypothesis in hypothesis_rows:
        row = dict(hypothesis)
        row.update(
            {
                "row_type": "comparison",
                "role": str(COMPARISON_BY_ID[str(hypothesis["comparison_id"])]["role"]),
                "note": (
                    "主假设"
                    if hypothesis["comparison_id"] == "C1"
                    else "次要比较（不得升级为主结论）"
                ),
            }
        )
        rows.append(row)
    return rows


def _negative_control_payload(
    cells: Mapping[tuple[str, int, int, str], AggregatedCell],
    bundle: FrozenBundle,
    *,
    clone_equivalence_checked: int,
    determinism_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """负控检验：negative_control split 不应出现显著优势；K=0 CLONE 等价性；可选确定性报告。"""
    split = "negative_control"
    rows: list[dict[str, Any]] = []
    has_split = any(key[0] == split for key in cells)
    if has_split:
        for K in PRIMARY_KS:
            for budget in MAIN_POPULATION_BUDGETS:
                for comparison in COMPARISONS:
                    for endpoint in PRIMARY_ENDPOINTS:
                        paired = build_paired_endpoint(
                            cells,
                            bundle,
                            comparison_id=str(comparison["id"]),
                            split=split,
                            budget_B=int(budget),
                            K=int(K),
                            endpoint=endpoint,
                        )
                        if paired is None:
                            continue
                        row = analyze_pair(paired)
                        fails = row["decision"] == DECISION_BENEFIT
                        status = "FAIL" if fails else ("INCONCLUSIVE" if row["decision"] == DECISION_INCONCLUSIVE else "PASS")
                        rows.append(
                            {
                                "check": "negative_control_split",
                                "split": split,
                                "comparison_id": row["comparison_id"],
                                "budget_B": row["budget_B"],
                                "K": row["K"],
                                "endpoint": row["endpoint"],
                                "treatment": row["treatment"],
                                "reference": row["reference"],
                                "n_tasks": row["n_tasks"],
                                "n_pairs": row["n_pairs"],
                                "null_rate_treatment": row["null_rate_treatment"],
                                "null_rate_reference": row["null_rate_reference"],
                                "mean_difference": row["mean_difference"],
                                "improvement": row["improvement"],
                                "p_raw": row["p_raw"],
                                "decision": row["decision"],
                                "expected": "负控 split 不应出现显著优势",
                                "status": status,
                                "note": "描述性负控，不做 Holm 校正",
                            }
                        )
    clone_status = "PASS" if clone_equivalence_checked >= 0 else "NOT_AVAILABLE"
    rows.append(
        {
            "check": "clone_k0_equivalence",
            "split": "",
            "comparison_id": "",
            "budget_B": "",
            "K": 0,
            "endpoint": "",
            "treatment": CLONE_ALLOWED["arm"],
            "reference": CLONE_ALLOWED["canonical_arm"],
            "n_tasks": "",
            "n_pairs": int(clone_equivalence_checked),
            "null_rate_treatment": "",
            "null_rate_reference": "",
            "mean_difference": "",
            "improvement": "",
            "p_raw": "",
            "decision": "",
            "expected": "K=0 两臂历史逐字节一致",
            "status": clone_status,
            "note": f"已校验 {clone_equivalence_checked} 组 CLONE 配对",
        }
    )
    if determinism_report is None:
        determinism_status = "NOT_AVAILABLE"
        determinism_note = "未提供 determinism_report.json（A1/A2 输出后接入）"
        determinism_details: dict[str, Any] = {}
    else:
        status_value = str(determinism_report.get("status", "UNKNOWN"))
        determinism_status = "PASS" if status_value.upper().endswith("PASS") else "FAIL"
        determinism_note = f"determinism_report.status={status_value}"
        determinism_details = {
            key: determinism_report.get(key)
            for key in ("status", "n_runs", "n_reruns", "n_compared", "mismatches", "comparison_scope")
        }
    rows.append(
        {
            "check": "determinism",
            "split": "",
            "comparison_id": "",
            "budget_B": "",
            "K": "",
            "endpoint": "",
            "treatment": "",
            "reference": "",
            "n_tasks": "",
            "n_pairs": "",
            "null_rate_treatment": "",
            "null_rate_reference": "",
            "mean_difference": "",
            "improvement": "",
            "p_raw": "",
            "decision": "",
            "expected": "确定性重跑逐字段一致（排除 cost/record_digest）",
            "status": determinism_status,
            "note": determinism_note,
        }
    )
    split_rows = [row for row in rows if row["check"] == "negative_control_split"]
    split_failures = [row for row in split_rows if row["status"] == "FAIL"]
    determinism_failed = determinism_status == "FAIL"
    failures = [row for row in rows if row["status"] == "FAIL"]
    if failures or determinism_failed:
        overall = "FAIL"
    elif not split_rows:
        overall = "NOT_AVAILABLE"
    elif determinism_status == "PASS" and not split_failures:
        overall = "PASS"
    else:
        overall = "INCONCLUSIVE"
    return {
        "rows": rows,
        "status": overall,
        "n_checks": len(rows),
        "n_fail": len(failures),
        "determinism": {"status": determinism_status, "note": determinism_note, "details": determinism_details},
        "clone_k0": {"status": clone_status, "checked": int(clone_equivalence_checked)},
        "negative_control_split_available": bool(has_split),
    }


def _load_optional_json(path: str | Path | None, label: str, *, expect_mapping: bool = True) -> Any:
    if path is None:
        return None
    target = Path(path)
    if not target.is_file():
        raise S1AnalysisError(f"{label} 指定但文件不存在：{target.name}")
    payload, _raw = _read_json_file(target, label)
    if expect_mapping:
        if not isinstance(payload, Mapping):
            raise S1AnalysisError(f"{label} 必须是 JSON object")
        return dict(payload)
    return payload


def _input_manifest(
    bundle: FrozenBundle,
    sources: Sequence[str],
    record_count: int,
    *,
    meta_training_log: str | Path | None,
    determinism_report: str | Path | None,
    structural_index: "StructuralIdentifiabilityIndex | None" = None,
    expected_identity_source: str | None = None,
) -> dict[str, Any]:
    index = structural_index
    return {
        "freeze_dir_name": bundle.freeze_dir.name,
        "identity_source": bundle.identity_source,
        "identity_five": bundle.identity_five(),
        "identity_expected_fields": list(bundle.expected_identity_fields),
        "expected_identity_source": expected_identity_source,
        "freeze_raw_sha256": {name: str(value) for name, value in sorted(bundle.raw_sha256.items())},
        "run_records_files": [Path(source).name for source in sources],
        "n_run_record_files": len(sources),
        "record_count": int(record_count),
        "meta_training_log_name": None if meta_training_log is None else Path(meta_training_log).name,
        "determinism_report_name": None if determinism_report is None else Path(determinism_report).name,
        "identifiability_report_files": [] if index is None else list(index.source_names),
        "identifiability_mode": None if index is None else str(index.mode),
        "identifiability_pair_level_fields_source": (
            None if index is None else str(index.pair_level_fields_source)
        ),
    }


def run_s1_analysis(
    freeze_dir: str | Path,
    run_records: str | Path | Sequence[str | Path],
    output_dir: str | Path,
    *,
    make_figures: bool = True,
    meta_training_log: str | Path | None = None,
    determinism_report: str | Path | None = None,
    require_complete_grid: bool = True,
    verify_checksums: bool = True,
    verify_sha256sums: bool = True,
    identifiability_mode: str = IDENTIFIABILITY_MODE_FORMAL,
    allow_missing_identifiability_report: bool = False,
    identifiability_reports: Sequence[str | Path] | None = None,
    expected_identity: Mapping[str, Any] | None = None,
    expected_identity_source: str | None = None,
    analysis_mode: str = ANALYSIS_MODE_FORMAL,
    allow_code_delta: bool = False,
    allow_legacy: bool = False,
) -> dict[str, Any]:
    """S1 只读分析入口：校验 -> 聚合 -> 统计 -> 判定 -> 写出合同产物。

    fail-closed：冻结包、run_records、CLONE 等价性、主 split 网格完整性任一失败即抛
    S1AnalysisError/S1FreezeValidationError/S1RecordValidationError，不产出部分结论。

    R-V4-02/R-V4-04（task-230）：必须加载每个 source run 目录的 identifiability_report.json，
    校验 schema/组覆盖/与 run_records 的 (task,B,K,meta_seed,arm) 一致；formal 缺失即 fail-closed；
    pair-level STRUCTURALLY_IDENTICAL 从 benefit/harm 推断排除（不做事后任务剔除）；
    C5 仅描述、不进 Holm；aggregate/CSV 披露排除计数与 C5 可估计任务数。

    task-250（R-V4-08-01/03/04）：formal（默认）要求冻结包为 confirmatory v4
    （family_version=p4ra-family-v4 且 confirmatory_eligible=true）、当前代码
    package_code_sha() 与包内 frozen_family/summary 的 code_sha 三者一致、并按
    R-V4-08-02 强校验 prereg 的 holdout_splits/holdout_package/c5_policy/
    structural_identifiability 四块；任一不满足 fail-closed。exploratory 模式可用
    allow_legacy/allow_code_delta 显式放行，但 confirmatory_eligible=false 且主结论
    强制 INCONCLUSIVE、不得进入确证统计。Holm 族按 R-V4-08-01 唯一口径动态计数。
    """
    bundle = load_frozen_bundle(
        freeze_dir,
        verify_checksums=verify_checksums,
        verify_sha256sums=verify_sha256sums,
        expected_identity=expected_identity,
        expected_identity_source=expected_identity_source,
    )
    # task-250：在读取任何 run_records/统计前先固定合规门禁（fail-closed）。
    freeze_compliance = verify_analysis_freeze(
        bundle,
        analysis_mode=analysis_mode,
        allow_code_delta=allow_code_delta,
        allow_legacy=allow_legacy,
    )
    confirmatory_eligible = bool(freeze_compliance["confirmatory_eligible"])
    paths = [run_records] if isinstance(run_records, (str, Path)) else list(run_records)
    if not paths:
        raise S1AnalysisError("至少需要一个 run_records 路径")
    all_records: list[dict[str, Any]] = []
    all_sources: list[str] = []
    for path in paths:
        records, sources = load_run_records(path)
        all_records.extend(records)
        all_sources.extend(sources)
    seen: dict[str, int] = {}
    for record in all_records:
        run_id = str(record["run_id"])
        seen[run_id] = seen.get(run_id, 0) + 1
    duplicated = sorted(run_id for run_id, count in seen.items() if count > 1)
    if duplicated:
        raise S1RecordValidationError(f"跨文件 run_id 重复：{duplicated[:5]}")
    validation = validate_run_records(all_records, bundle)
    grid = (
        validate_grid_completeness(all_records, bundle, splits=(MAIN_SPLIT,))
        if require_complete_grid
        else {"status": "SKIPPED_BY_CALLER", "split": [MAIN_SPLIT]}
    )
    # R-V4-02：在读取数据后、任何统计前固定 pair-level 排除规则；formal 缺失报告即 fail-closed。
    structural_index = load_structural_identifiability(
        all_sources,
        all_records,
        mode=identifiability_mode,
        allow_missing=allow_missing_identifiability_report,
        explicit_report_paths=identifiability_reports,
    )
    cells = aggregate_run_records(all_records, bundle)
    hypotheses, holm_family_info = _hypothesis_rows(cells, bundle, structural_index)
    endpoint_rows = _endpoint_table_rows(cells, bundle, hypotheses)
    c5_summary = c5_structural_summary(cells, bundle, structural_index)
    structural_exclusions = comparison_structural_exclusion_counts(structural_index)
    structural_rows = structural_identifiability_rows(structural_index, bundle, c5_summary)
    primary = primary_conclusion(hypotheses)
    reproduction = secondary_reproduction_conclusion(hypotheses)
    if not confirmatory_eligible:
        # R-V4-08-04：exploratory/legacy/code-delta 放行的分析不得进入确证统计。
        reason = (
            "analysis_mode=exploratory" if freeze_compliance["analysis_mode"] != ANALYSIS_MODE_FORMAL else "freeze compliance gate"
        )
        primary = _non_confirmatory_primary(primary, reason)
        reproduction = dict(reproduction)
        reproduction["status"] = REPRODUCTION_NOT_AVAILABLE
        reproduction["confirmatory_eligible"] = False
        reproduction["non_confirmatory_reason"] = reason
    exploratory = [
        summarize_layer(hypotheses, comparison_id="C1", budget_B=int(budget), K=1)
        for budget in MAIN_POPULATION_BUDGETS
    ]
    ood_available = any(key[0] == "meta_test_ood" for key in cells)
    ood_summary: dict[str, Any] = {
        "available": bool(ood_available),
        "status": "DESCRIPTIVE_ONLY" if ood_available else "NOT_AVAILABLE",
        "note": "OOD 为描述层，不进入主统计",
        "cells": sorted(
            [
                {"budget_B": key[1], "K": key[2], "arm": key[3], "n_ok": cells[key].n_ok_runs, "n_failed": cells[key].n_failed_runs}
                for key in cells
                if key[0] == "meta_test_ood"
            ],
            key=lambda item: (item["budget_B"], item["K"], item["arm"]),
        ),
    }
    determinism_payload = _load_optional_json(determinism_report, "determinism_report")
    negative = _negative_control_payload(
        cells,
        bundle,
        clone_equivalence_checked=validation.clone_equivalence_checked,
        determinism_report=determinism_payload,
    )
    budget_rows = audit_budget_rows(all_records)
    identifiability_rows = audit_identifiability_rows(all_records)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    aggregate: dict[str, Any] = {
        "schema_version": S1_AGGREGATE_SCHEMA_VERSION,
        "analysis_schema_version": S1_ANALYSIS_SCHEMA_VERSION,
        "figure_status_schema_version": S1_FIGURE_STATUS_SCHEMA_VERSION,
        "endpoint_table_schema_version": S1_ENDPOINT_TABLE_SCHEMA_VERSION,
        "analysis_mode": freeze_compliance["analysis_mode"],
        "confirmatory_eligible": confirmatory_eligible,
        "freeze_compliance": freeze_compliance,
        "input": _input_manifest(
            bundle,
            all_sources,
            len(all_records),
            meta_training_log=meta_training_log,
            determinism_report=determinism_report,
            structural_index=structural_index,
            expected_identity_source=expected_identity_source,
        ),
        "freeze_echo": {
            "identity_source": bundle.identity_source,
            "identity_five": bundle.identity_five(),
            "identity_expected_fields": list(bundle.expected_identity_fields),
            "confirmatory_eligible": confirmatory_eligible,
            "code_sha": freeze_compliance["code_sha"]["frozen_family_code_sha"],
            "family_id": bundle.family_id,
            "family_version": bundle.family_version,
            "family_fingerprint": bundle.family_fingerprint,
            "split_hash": bundle.split_hash,
            "prereg_digest": bundle.prereg_digest,
            "analysis_plan_digest": bundle.analysis_plan_digest,
            "radius_base": bundle.radius_base,
            "split_counts": bundle.split_counts,
            "meta_seeds": list(bundle.meta_seeds),
            "opt_seeds": list(bundle.opt_seeds),
        },
        "validation": validation.to_dict(),
        "grid": grid,
        "main_split": MAIN_SPLIT,
        "primary_population": {
            "split": MAIN_SPLIT,
            "comparison": "C1",
            "primary_confirmatory_budget": PRIMARY_CONFIRMATORY_BUDGET,
            "primary_confirmatory_ks": list(PRIMARY_CONFIRMATORY_KS),
            "inference_ks": list(INFERENCE_KS),
            "exploratory_ks": list(EXPLORATORY_KS),
            "excluded_ks": [0],
            "excluded_note": "K=0 时 FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 同构（CLONE），排除推断",
            "holm_family": holm_family_info["holm_family_definition"],
            "holm_family_key_fields": list(holm_family_info["holm_family_key_fields"]),
            "holm_family_size_dynamic": bool(holm_family_info["holm_family_size_dynamic"]),
            "holm_family_max_size": int(holm_family_info["holm_family_max_size"]),
            "holm_family_size_min": int(holm_family_info["holm_family_size_min"]),
            "holm_family_size_max": int(holm_family_info["holm_family_size_max"]),
            "holm_family_size_counts": dict(holm_family_info["holm_family_size_counts"]),
            "holm_family_count": holm_family_info["holm_family_count"],
            "inference_comparison_ids": list(holm_family_info["inference_comparison_ids"]),
            "excluded_comparison_ids": list(holm_family_info["excluded_comparison_ids"]),
            "structural_exclusion_total": int(holm_family_info["structural_exclusion_total"]),
            "structural_identifiability_rule": (
                "pair-level：identifiability_report 中 overlap_rate>=threshold 判 STRUCTURALLY_IDENTICAL，"
                "该 (task,B,K,meta_seed) 组的该臂对不进入 benefit/harm 推断；不做事后任务剔除"
            ),
            "alpha": ALPHA,
            "bootstrap": {"samples": BOOTSTRAP_SAMPLES, "seed": BOOTSTRAP_SEED, "confidence": CONFIDENCE_LEVEL},
        },
        "primary_conclusion": primary,
        "secondary_reproduction": reproduction,
        "exploratory_layers": exploratory,
        "ood": ood_summary,
        "endpoint_rows": endpoint_rows,
        "negative_controls": negative,
        "budget_audit": budget_rows,
        "identifiability": identifiability_rows,
        "structural_identifiability": structural_index.to_dict(),
        "structural_exclusion_counts": structural_exclusions,
        "excluded_pair_counts": structural_index.structural_exclusion_counts(),
        "c5_structural_identifiability": c5_summary,
        "statistical_rules": {
            "unit": "task",
            "aggregation": "opt seed -> (task, meta_seed) 均值；meta_seed 等权 -> 任务级",
            "test": "双侧 Wilcoxon 符号秩（n<=20 无并列用精确分布；并列用正态近似+并列/连续性修正）",
            "multiple_comparison": (
                "Holm-Bonferroni（唯一口径 R-V4-08-01：族键=(主端点, 预算_B, K)，"
                "成员=该族键下全部可推断比较 C1–C4；C5 永不进族；pair-level 排除后族大小可 <4，动态记录）"
            ),
            "holm_family_key_fields": list(holm_family_info["holm_family_key_fields"]),
            "holm_family_max_size": int(holm_family_info["holm_family_max_size"]),
            "holm_family_size_counts": dict(holm_family_info["holm_family_size_counts"]),
            "holm_family_sizes": holm_family_info["holm_family_sizes"],
            "structural_identifiability": (
                "R-V4-02/R-V4-04：消费每个 run 的 identifiability_report.json（schema/组覆盖/臂覆盖强校验）；"
                "pair-level STRUCTURALLY_IDENTICAL 组从 benefit/harm 推断排除，不剔除任务；排除计数披露于 "
                "structural_exclusion_counts 与 s1_structural_identifiability.csv"
            ),
            "c5_policy": (
                "C5（FOMAML-KSHOT-BO vs FOMAML-ZERO-BO）仅描述：不进 Holm、不做 benefit/harm 判定、无 p 值/CI；"
                "可估计任务数<10 固定 NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY"
            ),
            "improvement": "预注册中位数（配对且两臂均非 null 的子集；best/gap 相对改善，hit/first 绝对差）",
            "ci": "配对差值均值的百分位 bootstrap（10000 次，seed=20261105）",
            "ci_decision_rule": "SUPPORTED_* 需 Holm p<0.05 且 95% bootstrap CI 不跨 0 且方向有利且达阈值；CI 缺失→INCONCLUSIVE",
            "null_policy": "null 不插补、不转 0；主端点 null 率>70% 判 INCONCLUSIVE",
            "min_pairs": WILCOXON_MIN_PAIRS,
            "thresholds": {
                "best_feasible_value_relative_improvement": RELATIVE_IMPROVEMENT_THRESHOLD,
                "gap_to_reference_relative_improvement": RELATIVE_IMPROVEMENT_THRESHOLD,
                "feasible_hit_rate_absolute_difference": HIT_RATE_ABSOLUTE_THRESHOLD,
                "first_feasible_eval_index_improvement": "ceil(0.05*B)（同 K 内比较）",
            },
        },
        "limitations": [
            "全部任务为解析合成任务，未调用任何真实物理求解器（physical_call_count=0）",
            "K=0 FOMAML-KSHOT-BO 为 CLONE，已从推断排除",
            "K=1 为探索层，不进入主结论",
            "B=128 为次级复现层，只描述不升级主结论",
            "OOD 与 negative_control 仅描述，不进入主统计",
            "跨 K=3/K=5 合成规则采用保守合取（合同未规定）",
            "pair-level 结构不可辨识（STRUCTURALLY_IDENTICAL）组已从 benefit/harm 推断排除，但任务保留、不做事后剔除",
            "C5 仅描述性报告（不进 Holm、不做 benefit/harm），可估计任务数<10 时为 NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY",
            "R-V4-01 的 v4 holdout（p4ra-family-v4）环境未重建；本分析消费调用方提供的冻结包与 run_records",
            (
                "R-V4-08-03/04：formal 模式要求 confirmatory v4 包（confirmatory_eligible=true）且当前代码 "
                "package_code_sha() 与冻结包 code_sha 一致；本次 analysis_mode="
                + freeze_compliance["analysis_mode"]
                + "，confirmatory_eligible="
                + str(confirmatory_eligible)
            ),
            (
                "R-V4-08-01：Holm 族为动态大小（族键=(主端点,B,K)，成员=C1–C4；C5 永不进族），"
                "pair-level 排除后族大小可 <4"
            ),
        ],
        "contract_ambiguities": [
            "执行计划 §6 只规定 C1 单层规则（>=2 BENEFIT 且 0 HARM），未规定 K=3 与 K=5 如何合成；"
            "本实现取保守合取并在 primary_conclusion 中披露，待 Lead 裁决",
            "first_feasible_eval_index 的改善阈值按 ceil(0.05*B) 取整；"
            "合同写“仅同 K 内比较”，本实现按任务级配对差判定",
            "R-V4-04 未规定 identifiability_report 的臂对覆盖是否为全部 3 对；本实现按 run_records 中实际出现的 "
            "model-scored 臂全集做覆盖校验，缺任一对即 fail-closed（exploratory 可显式 allow_missing 降级）",
            "旧 v1 identifiability_report（p4ra-s1-identifiability-1）无 pair 级字段；本实现按预注册规则由 "
            "overlap_rate>=threshold 派生并在 aggregate 披露 pair_level_fields_source，待 A1 落 v4 schema 后切换",
        ],
    }
    figure_status: dict[str, Any]
    if make_figures:
        from . import s1_figures

        figure_status = s1_figures.render_figures(
            aggregate,
            output_dir_path,
            meta_training_log=_load_optional_json(meta_training_log, "meta_training_log", expect_mapping=False),
        )
    else:
        figure_status = {
            "schema_version": S1_FIGURE_STATUS_SCHEMA_VERSION,
            "figures": {key: "NOT_RUN" for key in FIGURE_KEYS},
            "note": "调用方指定 make_figures=False",
        }
    # C5 结构可辨识性同步进 figure_status（s1_figures 不绘制 C5 图；此处只披露状态，不伪造曲线）。
    figure_status["c5_structural_identifiability"] = {
        "status": str(c5_summary["status"]),
        "estimable_tasks": int(c5_summary["estimable_tasks"]),
        "total_groups": int(c5_summary["total_groups"]),
        "structurally_identical_groups": int(c5_summary["structurally_identical_groups"]),
        "clone_rate": c5_summary["clone_rate"],
        "note": "C5 不绘制（仅描述）；状态来自 identifiability_report pair-level 规则",
    }
    notes = list(figure_status.get("notes") or [])
    notes.append("C5 仅描述（不进 Holm、不做 benefit/harm），s1_figures 不绘制 C5 曲线")
    figure_status["notes"] = notes
    aggregate["figure_status"] = figure_status
    _write_json(output_dir_path / "aggregate.json", aggregate)
    _write_csv(output_dir_path / "s1_endpoint_tables.csv", endpoint_rows, ENDPOINT_TABLE_COLUMNS)
    _write_csv(output_dir_path / "s1_identifiability_table.csv", identifiability_rows, IDENTIFIABILITY_COLUMNS)
    _write_csv(
        output_dir_path / "s1_structural_identifiability.csv",
        structural_rows,
        STRUCTURAL_IDENTIFIABILITY_COLUMNS,
    )
    _write_csv(output_dir_path / "s1_budget_audit.csv", budget_rows, BUDGET_AUDIT_COLUMNS)
    _write_csv(output_dir_path / "s1_negative_controls.csv", negative["rows"], NEGATIVE_CONTROL_COLUMNS)
    _write_csv(
        output_dir_path / "s1_freeze_identity.csv",
        [bundle.identity_csv_row()],
        FREEZE_IDENTITY_COLUMNS,
    )
    _write_json(output_dir_path / "figure_status.json", figure_status)
    return aggregate


def main(argv: Sequence[str] | None = None) -> int:
    """CLI：只读分析，不执行 runner/BO/物理求解器。"""
    parser = argparse.ArgumentParser(
        prog="s1_analysis",
        description="P4 路线A S1 只读统计分析（冻结包 + run_records -> 合同产物）",
    )
    parser.add_argument("--freeze-dir", required=True, help="S1 冻结包目录")
    parser.add_argument("--run-records", required=True, nargs="+", help="run_records.jsonl 文件或目录（可多个）")
    parser.add_argument("--output-dir", required=True, help="输出目录（不存在则创建）")
    parser.add_argument("--meta-training-log", default=None, help="可选：meta 训练损失日志 JSON（fig1）")
    parser.add_argument("--determinism-report", default=None, help="可选：确定性报告 JSON（负控/fig7）")
    parser.add_argument("--no-figures", action="store_true", help="不生成图（仅数据产物）")
    parser.add_argument("--allow-incomplete-grid", action="store_true", help="允许主 split 网格不完整（仅调试）")
    parser.add_argument("--skip-checksums", action="store_true", help="跳过 digest_manifest/SHA256SUMS 校验（仅调试）")
    parser.add_argument(
        "--identifiability-mode",
        default=IDENTIFIABILITY_MODE_FORMAL,
        choices=list(IDENTIFIABILITY_MODES),
        help="结构可辨识性报告模式：formal（缺失即 fail-closed，默认）/ exploratory",
    )
    parser.add_argument(
        "--allow-missing-identifiability-report",
        action="store_true",
        help="仅 exploratory 模式允许缺 identifiability_report.json（降级为 warning）",
    )
    parser.add_argument(
        "--identifiability-report",
        action="append",
        default=None,
        help="显式指定 identifiability_report.json（可多次；默认从 run 目录自动发现）",
    )
    parser.add_argument(
        "--expected-identity-json",
        default=None,
        help=(
            "可选：期望冻结身份 JSON（五项 family_fingerprint/split_hash/prereg_digest/"
            "analysis_plan_digest/radius_base）；正式 run 由 run_config 传入，提供时必须逐项相等"
        ),
    )
    parser.add_argument(
        "--analysis-mode",
        default=ANALYSIS_MODE_FORMAL,
        choices=list(ANALYSIS_MODES),
        help="分析模式：formal（默认；confirmatory v4 包 + code_sha 绑定 + prereg 四块强校验）/ exploratory",
    )
    parser.add_argument(
        "--allow-code-delta",
        action="store_true",
        help="仅 exploratory：允许当前代码 package_code_sha() 与冻结包 code_sha 不一致（记录 warning）",
    )
    parser.add_argument(
        "--allow-legacy",
        action="store_true",
        help="仅 exploratory：允许 legacy/非确认冻结包（输出 confirmatory_eligible=false，不进入确证统计）",
    )
    args = parser.parse_args(argv)
    try:
        expected_identity = None
        expected_identity_source = None
        if args.expected_identity_json is not None:
            identity_path = Path(args.expected_identity_json)
            if not identity_path.is_file():
                raise S1AnalysisError(f"expected_identity JSON 不存在：{identity_path}")
            identity_payload, _identity_raw = _read_json_file(identity_path, "expected_identity")
            if not isinstance(identity_payload, Mapping):
                raise S1AnalysisError("expected_identity JSON 必须是 object")
            expected_identity = dict(identity_payload)
            expected_identity_source = identity_path.name
        aggregate = run_s1_analysis(
            args.freeze_dir,
            args.run_records,
            args.output_dir,
            make_figures=not args.no_figures,
            meta_training_log=args.meta_training_log,
            determinism_report=args.determinism_report,
            require_complete_grid=not args.allow_incomplete_grid,
            verify_checksums=not args.skip_checksums,
            verify_sha256sums=not args.skip_checksums,
            identifiability_mode=args.identifiability_mode,
            allow_missing_identifiability_report=args.allow_missing_identifiability_report,
            identifiability_reports=args.identifiability_report,
            expected_identity=expected_identity,
            expected_identity_source=expected_identity_source,
            analysis_mode=args.analysis_mode,
            allow_code_delta=args.allow_code_delta,
            allow_legacy=args.allow_legacy,
        )
    except S1AnalysisError as exc:
        print(f"S1_ANALYSIS_FAILED: {exc}", file=sys.stderr)
        return 2
    summary = {
        "status": "PASS",
        "identity_source": aggregate["freeze_echo"]["identity_source"],
        "analysis_mode": aggregate["analysis_mode"],
        "confirmatory_eligible": bool(aggregate["confirmatory_eligible"]),
        "n_records": int(aggregate["validation"]["record_count"]),
        "primary_overall": aggregate["primary_conclusion"]["overall"],
        "secondary_reproduction": aggregate["secondary_reproduction"]["status"],
        "negative_controls": aggregate["negative_controls"]["status"],
        "c5_structural_identifiability": aggregate["c5_structural_identifiability"]["status"],
        "c5_estimable_tasks": aggregate["c5_structural_identifiability"]["estimable_tasks"],
        "structural_exclusion_total": aggregate["structural_exclusion_counts"]["total"],
        "output_dir": str(Path(args.output_dir)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
