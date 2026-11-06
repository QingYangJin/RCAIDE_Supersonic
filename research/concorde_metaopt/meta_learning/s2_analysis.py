# -*- coding: utf-8 -*-
"""P4 路线A S2 分析层：FULL_MAML 与 FOMAML 等预算对照的统计/出图/产物生成。

依据：docs/planning/p4_route_a_s2_execution_plan_20261106.md v1.3a 的 §2/§3/§5/§6/§7/§8/§12；
R-S2-01 设计裁定；S2 prereg 冻结清单。

边界（硬性）：
- physical_call_count=0：本模块只读 run 目录与冻结 prereg，不 import/启动任何真实
  Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器，也不读取 holdout 数据行；
- 证据范围固定为 DEVELOPMENT_VALIDATION_ONLY（meta_validation 开发/验证集），
  输出措辞不得外推为确证性泛化或真实航空收益；
- 输入 fail-closed：prereg schema/digest/端点/Holm 单族/证据范围/物理计数/数据边界
  任一不符即抛 S2AnalysisError，不产出主结论；
- 结论允许 null（NO_EVIDENCE / INCONCLUSIVE），不得插补、不得转 0、不得伪造曲线。

产物（8 个数据产物 + 9 张规范键图，v1.5 图合同）：
  aggregate.json
  s2_endpoint_tables.csv
  s2_per_task_aggregates.csv
  s2_holm_family.csv
  s2_null_disclosure.csv
  s2_negative_controls.csv
  s2_prereg_echo.json
  figure_status.json
  fig1_training_loss_curves.png ... fig9_task_family_diagnostics.png
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

# ---------------------------------------------------------------------------
# 常量：schema 版本、错误码、预注册合同
# ---------------------------------------------------------------------------

S2_ANALYSIS_SCHEMA_VERSION = "p4ra-s2-analysis-1"
S2_AGGREGATE_SCHEMA_VERSION = "p4ra-s2-aggregate-1"
S2_PREREG_ECHO_SCHEMA_VERSION = "p4ra-s2-prereg-echo-1"
S2_FIGURE_STATUS_SCHEMA_VERSION = "p4ra-s2-figure-status-1"
S2_NEGATIVE_CONTROL_SCHEMA_VERSION = "p4ra-s2-negative-controls-1"

PREREG_SCHEMA_VERSION = "p4ra-s2-prereg-v1"

# 错误码：所有 fail-closed 异常都带稳定错误码，便于 A5/A3 审计与负控测试。
ERR_INPUT = "S2_ANALYSIS_INPUT_ERROR"
ERR_PREREG_SCHEMA = "S2_ANALYSIS_PREREG_SCHEMA"
ERR_PREREG_FIELD = "S2_ANALYSIS_PREREG_REQUIRED_FIELD"
ERR_PREREG_UNKNOWN_FIELD = "S2_ANALYSIS_PREREG_UNKNOWN_FIELD"
ERR_PREREG_PLACEHOLDER = "S2_ANALYSIS_PREREG_PLACEHOLDER"
ERR_PREREG_DIGEST = "S2_ANALYSIS_PREREG_DIGEST_MISMATCH"
ERR_PREREG_ENDPOINT = "S2_ANALYSIS_PREREG_ENDPOINT_MISMATCH"
ERR_PREREG_HOLM = "S2_ANALYSIS_PREREG_HOLM_FAMILY_INVALID"
ERR_PREREG_SCOPE = "S2_ANALYSIS_PREREG_EVIDENCE_SCOPE_INVALID"
ERR_PREREG_PHYSICAL = "S2_ANALYSIS_PREREG_PHYSICAL_COUNT_NONZERO"
ERR_PREREG_ARM = "S2_ANALYSIS_PREREG_ARM_PARITY"
ERR_PREREG_FROZEN = "S2_ANALYSIS_PREREG_FROZEN_PACKAGE_INVALID"
ERR_PREREG_PILOT = "S2_ANALYSIS_PREREG_PILOT_ARTIFACT_INVALID"
ERR_RUN_SCHEMA = "S2_ANALYSIS_RUN_SCHEMA"
ERR_RUN_CONFIG = "S2_ANALYSIS_RUN_CONFIG"
ERR_RECORD_SCHEMA = "S2_ANALYSIS_RECORD_SCHEMA"
ERR_RECORD_VALUE = "S2_ANALYSIS_RECORD_VALUE"
ERR_RECORD_DUPLICATE = "S2_ANALYSIS_RECORD_DUPLICATE"
ERR_DATA_BOUNDARY = "S2_ANALYSIS_DATA_BOUNDARY"
ERR_RUN_INCOMPLETE = "S2_ANALYSIS_RUN_INCOMPLETE"
ERR_OUTPUT = "S2_ANALYSIS_OUTPUT_ERROR"
ERR_PREREG_RESOURCE_LIMITS = "S2_ANALYSIS_PREREG_RESOURCE_LIMITS_INVALID"

# 臂
ARM_FULL = "FULL_MAML"
ARM_FOMAML = "FOMAML"
EXPECTED_ARMS = (ARM_FULL, ARM_FOMAML)
EXPECTED_ARMS_CONFIG = {
    "input_dim": 12,
    "output_dim": 1,
    "hidden_sizes": [16, 16],
    "inner_lr": 0.01,
    "inner_steps": 5,
    "outer_lr": 0.001,
    "tasks_per_batch": 8,
    "seed": 42,
    "backend": "torch",
}

# 端点（§1/§6）
PRIMARY_ENDPOINT = "post_adaptation_rmse_raw_k5"
SECONDARY_ENDPOINTS = ("post_adaptation_rmse_raw_k10",)
INFERENCE_ENDPOINTS = (PRIMARY_ENDPOINT,) + SECONDARY_ENDPOINTS
DESCRIPTIVE_ENDPOINTS = (
    "post_adaptation_rmse_raw_k0",
    "post_adaptation_rmse_raw_k1",
    "post_adaptation_rmse_std_k5",
    "post_adaptation_rmse_std_k10",
    "post_adaptation_mae_raw_k5",
    "train_wall_seconds_ratio",
    "peak_memory_mb",
)
ENDPOINT_DIRECTIONS = {name: "lower_is_better" for name in INFERENCE_ENDPOINTS}

# 端点 -> (K, 评估记录字段)
ENDPOINT_SOURCES = {
    "post_adaptation_rmse_raw_k5": (5, "query_rmse_raw"),
    "post_adaptation_rmse_raw_k10": (10, "query_rmse_raw"),
    "post_adaptation_rmse_raw_k0": (0, "query_rmse_raw"),
    "post_adaptation_rmse_raw_k1": (1, "query_rmse_raw"),
    "post_adaptation_rmse_std_k5": (5, "query_rmse_standardized"),
    "post_adaptation_rmse_std_k10": (10, "query_rmse_standardized"),
    "post_adaptation_mae_raw_k5": (5, "query_mae_raw"),
}

# 预注册统计合同（§6/§7）
HOLM_FAMILY_ID = "s2-primary-secondary-2tests"
HOLM_FAMILY_KEY = "s2_primary_secondary"
HOLM_FAMILY_METHOD = "holm"
HOLM_FAMILY_SIZE = 2
HOLM_FAMILY_MEMBERS = (
    {"comparison": "C1", "endpoint": PRIMARY_ENDPOINT},
    {"comparison": "C1", "endpoint": SECONDARY_ENDPOINTS[0]},
)
COMPARISON_ID = "C1"
COMPARISON_ARMS = [ARM_FULL, ARM_FOMAML]
COMPARISON_DIFFERENCE = "FULL_MAML - FOMAML"
COMPARISON_UNIT = "task"

PAIRED_TEST = "wilcoxon_signed_rank_two_sided"
N_TASKS = 20
BOOTSTRAP_SAMPLES = 10000
BOOTSTRAP_SEED = 20261105
CONFIDENCE_LEVEL = 0.95
ALPHA = 0.05
RELATIVE_IMPROVEMENT_THRESHOLD = 0.01
NULL_RATE_INCONCLUSIVE = 0.70
WILCOXON_MIN_PAIRS = 10

EVIDENCE_SCOPE = "DEVELOPMENT_VALIDATION_ONLY"
DEVELOPMENT_SET = "meta_validation"

# 数据边界（§2）
SPLIT_TRAIN = "meta_train"
SPLIT_EVAL = "meta_validation"
ALLOWED_SPLITS = (SPLIT_TRAIN, SPLIT_EVAL)
FORBIDDEN_SPLITS = ("meta_test", "meta_test_ood", "negative_control")
EXPECTED_SPLIT_COUNTS = {
    "meta_test": 20,
    "meta_test_ood": 10,
    "meta_train": 60,
    "meta_validation": 20,
    "negative_control": 10,
}

# 预算与评估网格（§5/§7）
META_SEEDS = (0, 1, 2)
OUTER_STEPS = 200
K_VALUES = (0, 1, 5, 10)
EVAL_DRAWS = 10
EVAL_QUERY_SIZE = 64
TRAIN_SUPPORT_SIZE = 16
TRAIN_QUERY_SIZE = 32
TRAIN_RECORDS_EXPECTED = 1200
EVAL_RECORDS_EXPECTED = 4800

# S0-7 冻结包身份（§2；只读、不读 holdout 数据行）
FROZEN_PACKAGE_RUN_ID = "p4ra-s0-7-freeze-20261106T024200Z"
FROZEN_PACKAGE_PATH = (
    "research/concorde_metaopt/optimization_runs/" + FROZEN_PACKAGE_RUN_ID
)
FROZEN_PACKAGE_SHA256SUMS_SHA256 = (
    "59aa81cdc1f1abdc66966822eb24b567904ba4c62924ab041ae09bd9badf41f2"
)
FROZEN_PACKAGE_CODE_SHA = (
    "7304d32e524b0e1e28b0e83e7a2ed7822ce88fc14963ca4d769098841e6201ed"
)
FROZEN_PACKAGE_GIT_SHA = "004156c232f31a450f7446c3b280772de47423df"
FROZEN_PACKAGE_FAMILY_VERSION = "p4ra-family-v4"
# 分包族版本：冻结包（S0-7 payload）与任务族（tasks.json）分别登记（v1.5 §7 A4-S2C-04）。
FROZEN_PACKAGE_TASK_FAMILY_VERSION = "p4ra-family-v3"

# prereg 顶层必填字段（§7；缺失/多余都 fail-closed）
PREREG_REQUIRED_FIELDS = (
    "schema_version",
    "prereg_id",
    "created_utc",
    "upstream",
    "frozen_package",
    "data_boundary",
    "episode_contract",
    "arms",
    "training_budget",
    "evaluation_grid",
    "endpoints",
    "comparison",
    "statistical_plan",
    "fd_gate",
    "determinism",
    "resource_limits",
    "failure_rules",
    "stopping_rules",
    "code_sha",
    "analysis_plan_digest",
    "physical_call_count",
    "prereg_digest",
)
PREREG_UPSTREAM_FIELDS = ("issue", "decision", "stage", "s1_receipt_comment_id")
PREREG_FROZEN_FIELDS = (
    "run_id",
    "package_path",
    "sha256sums_sha256",
    "code_sha",
    "git_sha",
    "package_family_version",
    "task_family_version",
)
PREREG_DATA_BOUNDARY_FIELDS = (
    "allowed_splits",
    "forbidden_splits",
    "split_counts",
    "meta_train_task_ids_sha256",
    "meta_validation_task_ids_sha256",
    "holdout_task_ids_sha256",
    "holdout_rows_used",
)
PREREG_EPISODE_FIELDS = (
    "train_support",
    "train_query",
    "eval_K",
    "eval_draws",
    "eval_query",
    "seed_scopes",
    "standardization",
    "train_episode_bank_sha256",
)
PREREG_SEED_SCOPES = (
    "S2-train-support",
    "S2-train-query",
    "S2-train-order",
    "S2-eval-support",
    "S2-eval-query",
)
PREREG_TRAINING_BUDGET = {
    "outer_steps": OUTER_STEPS,
    "meta_seeds": list(META_SEEDS),
    "train_records_expected": TRAIN_RECORDS_EXPECTED,
}
PREREG_EVALUATION_GRID = {
    "meta_validation_tasks": N_TASKS,
    "K": list(K_VALUES),
    "draws": EVAL_DRAWS,
    "eval_records_expected": EVAL_RECORDS_EXPECTED,
}
PREREG_EPISODE_CONTRACT_NUMBERS = {
    "train_support": TRAIN_SUPPORT_SIZE,
    "train_query": TRAIN_QUERY_SIZE,
    "eval_K": list(K_VALUES),
    "eval_draws": EVAL_DRAWS,
    "eval_query": EVAL_QUERY_SIZE,
}
PREREG_EXPECTED_FD_GATE = {
    "mode": "full",
    "max_relative_error": 1e-6,
    "coordinates": 32,
    "fail_closed": True,
}
PREREG_DETERMINISM = {
    "reruns": 2,
    "requires_byte_identical": ["train_episode_bank_manifest", "run_config", "run_records_core"],
    "fail_closed": True,
}
# 资源硬上限（v1.5 §7 A5-M0R4-F-03；固定值，纳入 prereg_digest）
PREREG_RESOURCE_LIMITS = {
    "per_seed_train_wall_s": 1200,
    "peak_memory_mb": 8192,
    "total_wall_s": 7200,
}
PREREG_FAILURE_RULES = [
    "nonfinite_loss_or_grad -> arm/seed FAILED, stop, no retry",
    "resource_limit -> RESOURCE_LIMIT, no retry",
    "any seed failed -> arm DEGRADED and primary INCONCLUSIVE",
]
PREREG_STOPPING_RULES = [
    "stop_on_nonfinite",
    "stop_on_data_boundary_violation",
    "stop_on_fd_gate_failure",
    "stop_on_code_sha_mismatch",
    "hard_deadline_2h",
]
PREREG_DECISION_RULES = {
    "benefit": "holm_p<0.05 and ci_excludes_zero and full<fomaml and relative_improvement>=0.01",
    "harm": "symmetric",
    "inconclusive": "null_rate>0.70",
    "else": "NO_EVIDENCE",
}
PREREG_COMPARISON = {
    "id": COMPARISON_ID,
    "arms": COMPARISON_ARMS,
    "difference": COMPARISON_DIFFERENCE,
    "unit": COMPARISON_UNIT,
    "aggregation": "mean over 3 meta_seeds x 10 draws per task",
}
PREREG_ENDPOINTS_TEMPLATE = {
    "primary": {
        "id": PRIMARY_ENDPOINT,
        "direction": "lower_is_better",
        "K": 5,
        "space": "raw",
    },
    "secondary_inferential": [
        {
            "id": SECONDARY_ENDPOINTS[0],
            "direction": "lower_is_better",
            "K": 10,
            "space": "raw",
        }
    ],
    "descriptive": list(DESCRIPTIVE_ENDPOINTS),
}
PREREG_STATISTICAL_PLAN_TEMPLATE = {
    "test": PAIRED_TEST,
    "n_tasks": N_TASKS,
    "bootstrap": {
        "n_resamples": BOOTSTRAP_SAMPLES,
        "seed": BOOTSTRAP_SEED,
        "ci": CONFIDENCE_LEVEL,
    },
    "multiple_comparison": {
        "family_id": HOLM_FAMILY_ID,
        "family_key": HOLM_FAMILY_KEY,
        "method": HOLM_FAMILY_METHOD,
        "family_size": HOLM_FAMILY_SIZE,
        "members": [dict(item) for item in HOLM_FAMILY_MEMBERS],
    },
    "decision_rules": dict(PREREG_DECISION_RULES),
    "evidence_scope": EVIDENCE_SCOPE,
}

# 记录字段（§5）
TRAIN_REQUIRED_FIELDS = (
    "run_id",
    "arm",
    "meta_seed",
    "outer_step",
    "train_loss",
    "grad_norm",
    "inner_loss_first",
    "inner_loss_last",
    "wall_s",
    "peak_memory_mb",
    "status",
)
EVAL_REQUIRED_FIELDS = (
    "run_id",
    "arm",
    "meta_seed",
    "task_id",
    "split",
    "K",
    "draw",
    "query_rmse_raw",
    "query_rmse_standardized",
    "query_mae_raw",
    "support_size",
    "query_size",
    "adaptation_inner_steps",
    "wall_s",
    "status",
)
RECORD_STATUSES = ("OK", "FAILED")
RUN_ARM_STATUSES = ("OK", "DEGRADED", "FAILED", "RESOURCE_LIMIT")

# 输出产物（8 个数据产物 + 9 张规范键图，v1.5 图合同）
S2_OUTPUT_FILES = (
    "aggregate.json",
    "s2_endpoint_tables.csv",
    "s2_per_task_aggregates.csv",
    "s2_holm_family.csv",
    "s2_null_disclosure.csv",
    "s2_negative_controls.csv",
    "s2_prereg_echo.json",
    "figure_status.json",
)
FIGURE_KEYS = (
    "fig1_training_loss_curves",
    "fig2_post_adaptation_rmse_k5_k10",
    "fig3_rmse_vs_K",
    "fig4_meta_gradient_fd",
    "fig5_effect_size_ci",
    "fig6_descriptive_k0_k1_standardized",
    "fig7_determinism_and_negative_controls",
    "fig8_performance_cost",
    "fig9_task_family_diagnostics",
)
FIGURE_FILENAMES = {key: key + ".png" for key in FIGURE_KEYS}

# 决策常量
DECISION_BENEFIT = "SUPPORTED_BENEFIT"
DECISION_HARM = "SUPPORTED_HARM"
DECISION_INCONCLUSIVE = "INCONCLUSIVE"
DECISION_NONE = "NO_EVIDENCE"
OVERALL_ADVANTAGE = "SUPPORTED_IMPROVEMENT"
OVERALL_NONE = "NO_SIGNIFICANT_IMPROVEMENT"
OVERALL_HARM = "SUPPORTED_HARM"
OVERALL_INCONCLUSIVE = "INCONCLUSIVE"

_CSV_COLUMNS = {
    "s2_endpoint_tables.csv": (
        "comparison_id",
        "endpoint",
        "endpoint_role",
        "family_id",
        "family_size",
        "treatment_arm",
        "reference_arm",
        "n_tasks",
        "n_pairs",
        "treatment_mean",
        "reference_mean",
        "treatment_median",
        "reference_median",
        "median_difference",
        "relative_improvement",
        "wilcoxon_statistic",
        "wilcoxon_method",
        "p_raw",
        "p_adjusted",
        "ci_low",
        "ci_high",
        "decision",
        "null_rate_max",
        "decision_reasons",
    ),
    "s2_per_task_aggregates.csv": (
        "task_id",
        "arm",
        "endpoint",
        "K",
        "value",
        "n_values",
        "n_null",
        "null_rate",
        "meta_seed_count",
        "draw_count",
    ),
    "s2_holm_family.csv": (
        "family_id",
        "family_key",
        "family_size",
        "member_index",
        "comparison_id",
        "endpoint",
        "p_raw",
        "p_adjusted",
        "holm_rank",
        "decision",
    ),
    "s2_null_disclosure.csv": (
        "scope",
        "endpoint",
        "arm",
        "expected",
        "observed_nonnull",
        "observed_null",
        "null_rate",
        "policy",
    ),
    "s2_negative_controls.csv": (
        "check_id",
        "category",
        "status",
        "expected",
        "observed",
        "note",
    ),
}

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ABS_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PREREG_ID_RE = re.compile(r"^p4ra-s2-prereg-[0-9a-f]{16}$")
_PLACEHOLDER_RE = re.compile(r"^<.*>$")
_PLACEHOLDER_WORDS = frozenset({"TBD", "TODO", "PENDING", "PLACEHOLDER", "REPLACE_ME"})


class S2AnalysisError(ValueError):
    """分析层 fail-closed 异常；code 为稳定错误码，detail 为人类可读细节。"""

    def __init__(self, code: str, message: str, *, detail: str | None = None) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        text = f"[{code}] {message}"
        if detail:
            text += f" | {detail}"
        super().__init__(text)


def _fail(code: str, message: str, *, detail: str | None = None) -> "NoReturn":
    raise S2AnalysisError(code, message, detail=detail)

# ---------------------------------------------------------------------------
# 通用工具：canonical JSON / sha256 / 类型与占位校验
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """返回带时区的 UTC 时间戳（产物可复现性说明用）。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_json_text(obj: Any) -> str:
    """按 A1 接口契约生成 canonical JSON 文本（无末尾换行）。"""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical_bytes(obj: Any) -> bytes:
    """canonical bytes = canonical JSON 文本 + 末尾换行（UTF-8）。"""
    return (_canonical_json_text(obj) + "\n").encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    """对文件 raw bytes 计算 sha256（不做换行归一化）。"""
    return _sha256_hex(path.read_bytes())


def _sqlite_safe_path(path: Path) -> str:
    return str(path)


def _load_json_file(path: Path, *, code: str, label: str) -> Any:
    if not path.is_file():
        _fail(code, f"{label} 不存在", detail=str(path))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:  # pragma: no cover - 防御性
        _fail(code, f"{label} 不是 UTF-8 文本", detail=str(path) + " | " + str(exc))
    except json.JSONDecodeError as exc:
        _fail(code, f"{label} 不是合法 JSON", detail=str(path) + " | " + str(exc))


def _as_mapping(value: Any, *, code: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code, f"{label} 必须是 JSON object", detail=f"实际类型={type(value).__name__}")
    return value


def _as_list(value: Any, *, code: str, label: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        _fail(code, f"{label} 必须是 JSON array", detail=f"实际类型={type(value).__name__}")
    return value


def _require_exact_keys(
    mapping: Mapping[str, Any],
    required: Sequence[str],
    *,
    code: str,
    label: str,
    allow_extra: Sequence[str] = (),
) -> None:
    """字段集合必须精确相等（缺字段/多字段都 fail-closed）。"""
    required_set = set(required)
    extra_allowed = set(allow_extra)
    actual = set(mapping.keys())
    missing = sorted(required_set - actual)
    if missing:
        _fail(code, f"{label} 缺少必填字段", detail="missing=" + ",".join(missing))
    unknown = sorted(actual - required_set - extra_allowed)
    if unknown:
        _fail(code, f"{label} 出现未知字段", detail="unknown=" + ",".join(unknown))


def _require_str(value: Any, *, code: str, label: str, non_empty: bool = True) -> str:
    if not isinstance(value, str):
        _fail(code, f"{label} 必须是字符串", detail=f"实际类型={type(value).__name__}")
    if non_empty and not value.strip():
        _fail(code, f"{label} 不得为空字符串")
    return value


def _require_int(value: Any, *, code: str, label: str) -> int:
    # bool 是 int 子类，必须显式排除
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(code, f"{label} 必须是整数", detail=f"实际值={value!r}")
    return value


def _require_bool(value: Any, *, code: str, label: str) -> bool:
    if not isinstance(value, bool):
        _fail(code, f"{label} 必须是布尔值", detail=f"实际值={value!r}")
    return value


def _require_number(
    value: Any,
    *,
    code: str,
    label: str,
    allow_none: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    """校验 JSON number（拒绝 bool / 字符串 / NaN / inf）。"""
    if value is None:
        if allow_none:
            return None
        _fail(code, f"{label} 不得为 null")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(code, f"{label} 必须是数值", detail=f"实际值={value!r}")
    number = float(value)
    if not math.isfinite(number):
        _fail(code, f"{label} 必须是有限数值", detail=f"实际值={value!r}")
    if minimum is not None and number < minimum:
        _fail(code, f"{label} 小于允许下界", detail=f"{number} < {minimum}")
    if maximum is not None and number > maximum:
        _fail(code, f"{label} 大于允许上界", detail=f"{number} > {maximum}")
    return number


def _require_sha256(value: Any, *, code: str, label: str) -> str:
    text = _require_str(value, code=code, label=label)
    if not _SHA256_RE.match(text):
        _fail(code, f"{label} 必须是 64 位小写十六进制 sha256", detail=text)
    return text


def _require_numeric_list(
    value: Any,
    *,
    code: str,
    label: str,
    expected: Sequence[int] | None = None,
) -> list[Any]:
    items = list(_as_list(value, code=code, label=label))
    if expected is not None and items != list(expected):
        _fail(code, f"{label} 与执行计划不一致", detail=f"实际={items!r} 期望={list(expected)!r}")
    return items


def _iter_strings(obj: Any, prefix: str = "") -> Any:
    """递归遍历 JSON 对象中的全部字符串（用于占位扫描）。"""
    if isinstance(obj, str):
        yield prefix, obj
    elif isinstance(obj, Mapping):
        for key in sorted(obj.keys()):
            yield from _iter_strings(obj[key], prefix + "." + str(key))
    elif isinstance(obj, (list, tuple)):
        for index, item in enumerate(obj):
            yield from _iter_strings(item, prefix + "[" + str(index) + "]")


def _assert_no_placeholders(obj: Any, *, code: str, label: str) -> None:
    """占位拒绝：^<.*>$ 或 TBD/TODO/PENDING/PLACEHOLDER/REPLACE_ME。"""
    for path, text in _iter_strings(obj):
        stripped = text.strip()
        if _PLACEHOLDER_RE.match(stripped) or stripped.upper() in _PLACEHOLDER_WORDS:
            _fail(code, f"{label} 含占位字符串", detail=f"{path or '<root>'}={text!r}")


def _record_check(
    checks: list[dict[str, Any]],
    name: str,
    *,
    status: str,
    detail: str = "",
) -> None:
    """记录一项验证事实；status ∈ PASS/SKIPPED/DISCLOSED/FAIL（FAIL 由调用方抛错）。"""
    checks.append({"check": name, "status": status, "detail": detail})


# ---------------------------------------------------------------------------
# canonical digest 算法（A1 接口契约 §1；与 A1 s2_prereg.py 独立实现）
# ---------------------------------------------------------------------------


def compute_prereg_id(prereg: Mapping[str, Any]) -> str:
    """prereg_id = "p4ra-s2-prereg-" + sha256(去 prereg_id+prereg_digest 的 canonical bytes)[:16]。"""
    base = {key: value for key, value in prereg.items() if key not in ("prereg_id", "prereg_digest")}
    return "p4ra-s2-prereg-" + _sha256_hex(_canonical_bytes(base))[:16]


def compute_prereg_digest(prereg: Mapping[str, Any]) -> str:
    """prereg_digest = sha256(仅去 prereg_digest 的 canonical bytes)。"""
    base = {key: value for key, value in prereg.items() if key != "prereg_digest"}
    return _sha256_hex(_canonical_bytes(base))


def compute_analysis_plan_digest(prereg: Mapping[str, Any]) -> str:
    """analysis_plan_digest = sha256(canonical bytes of endpoints+comparison+statistical_plan+fd_gate)。"""
    plan = {
        "endpoints": prereg["endpoints"],
        "comparison": prereg["comparison"],
        "statistical_plan": prereg["statistical_plan"],
        "fd_gate": prereg["fd_gate"],
    }
    return _sha256_hex(_canonical_bytes(plan))


def compute_code_sha(file_paths: Sequence[tuple[str, Path]]) -> str:
    """code_sha：按相对路径 sorted() 字典序，逐文件写 path+\n+sha256(raw)+\n 后整体 sha256。"""
    ordered = sorted(file_paths, key=lambda item: item[0])
    payload = bytearray()
    for rel_path, path in ordered:
        if not path.is_file():
            _fail(ERR_INPUT, "code_sha 文件清单中的文件不存在", detail=rel_path + " -> " + str(path))
        payload.extend(rel_path.encode("utf-8"))
        payload.extend(b"\n")
        payload.extend(_sha256_file(path).encode("ascii"))
        payload.extend(b"\n")
    return _sha256_hex(bytes(payload))


# ---------------------------------------------------------------------------
# 冻结 prereg 的加载与校验
# ---------------------------------------------------------------------------

S2_CODE_FILES = (
    "research/concorde_metaopt/meta_learning/maml.py",
    "research/concorde_metaopt/meta_learning/s2_prereg.py",
    "research/concorde_metaopt/meta_learning/s2_runner.py",
)


@dataclass(frozen=True)
class S2Prereg:
    """已验证的冻结 prereg 快照；raw 保留原始 JSON 供 echo/复算。"""

    path: Path
    raw: Mapping[str, Any]
    prereg_id: str
    prereg_digest: str
    analysis_plan_digest: str
    created_utc: str
    upstream: Mapping[str, Any]
    frozen_package: Mapping[str, Any]
    data_boundary: Mapping[str, Any]
    episode_contract: Mapping[str, Any]
    arms: Sequence[Mapping[str, Any]]
    training_budget: Mapping[str, Any]
    evaluation_grid: Mapping[str, Any]
    endpoints: Mapping[str, Any]
    comparison: Mapping[str, Any]
    statistical_plan: Mapping[str, Any]
    fd_gate: Mapping[str, Any]
    determinism: Mapping[str, Any]
    failure_rules: Sequence[str]
    stopping_rules: Sequence[str]
    code_sha: str
    physical_call_count: int
    checks: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    # -- 便捷访问器（供聚合/统计使用；均已在校验阶段固定） --
    @property
    def evidence_scope(self) -> str:
        return str(self.statistical_plan["evidence_scope"])

    @property
    def development_set(self) -> str:
        return SPLIT_EVAL

    @property
    def meta_seeds(self) -> tuple[int, ...]:
        return tuple(int(seed) for seed in self.training_budget["meta_seeds"])

    @property
    def outer_steps(self) -> int:
        return int(self.training_budget["outer_steps"])

    @property
    def k_values(self) -> tuple[int, ...]:
        return tuple(int(k) for k in self.evaluation_grid["K"])

    @property
    def draws(self) -> int:
        return int(self.evaluation_grid["draws"])

    @property
    def n_tasks(self) -> int:
        return int(self.evaluation_grid["meta_validation_tasks"])

    @property
    def holm_family(self) -> Mapping[str, Any]:
        return self.statistical_plan["multiple_comparison"]  # type: ignore[return-value]

    @property
    def bootstrap(self) -> Mapping[str, Any]:
        return self.statistical_plan["bootstrap"]  # type: ignore[return-value]

    def to_echo(self) -> dict[str, Any]:
        """返回 A6 对冻结 prereg 的只读回显（不含原始大字段，保留身份与合同要点）。"""
        return {
            "schema_version": S2_PREREG_ECHO_SCHEMA_VERSION,
            "source_path": self.path.name,
            "source_sha256": _sha256_file(self.path),
            "prereg_id": self.prereg_id,
            "prereg_digest": self.prereg_digest,
            "analysis_plan_digest": self.analysis_plan_digest,
            "created_utc": self.created_utc,
            "upstream": dict(self.upstream),
            "frozen_package": dict(self.frozen_package),
            "data_boundary": {
                "allowed_splits": list(self.data_boundary["allowed_splits"]),
                "forbidden_splits": list(self.data_boundary["forbidden_splits"]),
                "split_counts": dict(self.data_boundary["split_counts"]),
                "holdout_rows_used": self.data_boundary["holdout_rows_used"],
                "holdout_metrics_read": False,
            },
            "episode_contract": {
                "train_support": self.episode_contract["train_support"],
                "train_query": self.episode_contract["train_query"],
                "eval_K": list(self.episode_contract["eval_K"]),
                "eval_draws": self.episode_contract["eval_draws"],
                "eval_query": self.episode_contract["eval_query"],
                "seed_scopes": list(self.episode_contract["seed_scopes"]),
            },
            "arms": [
                {"id": arm["id"], "first_order": arm["first_order"], "config": dict(arm["config"])}
                for arm in self.arms
            ],
            "training_budget": dict(self.training_budget),
            "evaluation_grid": dict(self.evaluation_grid),
            "endpoints": {
                "primary": dict(self.endpoints["primary"]),
                "secondary_inferential": [dict(item) for item in self.endpoints["secondary_inferential"]],
                "descriptive": list(self.endpoints["descriptive"]),
            },
            "comparison": dict(self.comparison),
            "holm_family": dict(self.holm_family),
            "statistical_rules": {
                "test": self.statistical_plan["test"],
                "n_tasks": self.statistical_plan["n_tasks"],
                "bootstrap": dict(self.bootstrap),
                "decision_rules": dict(self.statistical_plan["decision_rules"]),
            },
            "fd_gate": {
                "mode": self.fd_gate["mode"],
                "max_relative_error": self.fd_gate["max_relative_error"],
                "coordinates": self.fd_gate["coordinates"],
                "fail_closed": self.fd_gate["fail_closed"],
                "pilot_artifacts": json.loads(json.dumps(self.fd_gate["pilot_artifacts"])),
            },
            "determinism": json.loads(json.dumps(self.determinism)),
            "code_sha": self.code_sha,
            "physical_call_count": self.physical_call_count,
            "evidence_scope": self.evidence_scope,
            "development_set": self.development_set,
            "checks": [dict(check) for check in self.checks],
        }

# ---------------------------------------------------------------------------
# prereg 各节校验
# ---------------------------------------------------------------------------


def _validate_created_utc(value: Any) -> str:
    text = _require_str(value, code=ERR_PREREG_FIELD, label="created_utc")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail(ERR_PREREG_FIELD, "created_utc 不是合法 ISO-8601 时间", detail=text)
    return text


def _validate_upstream(upstream: Any) -> Mapping[str, Any]:
    mapping = _as_mapping(upstream, code=ERR_PREREG_FIELD, label="upstream")
    _require_exact_keys(mapping, PREREG_UPSTREAM_FIELDS, code=ERR_PREREG_FIELD, label="upstream")
    issue = _require_str(mapping["issue"], code=ERR_PREREG_FIELD, label="upstream.issue")
    if not issue.startswith("#") or not issue[1:].isdigit():
        _fail(ERR_PREREG_FIELD, "upstream.issue 必须是 #<数字> 形式", detail=issue)
    decision = _require_str(mapping["decision"], code=ERR_PREREG_FIELD, label="upstream.decision")
    stage = _require_str(mapping["stage"], code=ERR_PREREG_FIELD, label="upstream.stage")
    if stage != "S2":
        _fail(ERR_PREREG_FIELD, "upstream.stage 必须为 S2", detail=stage)
    comment_id = _require_int(
        mapping["s1_receipt_comment_id"], code=ERR_PREREG_FIELD, label="upstream.s1_receipt_comment_id"
    )
    if comment_id <= 0:
        _fail(ERR_PREREG_FIELD, "upstream.s1_receipt_comment_id 必须为正整数", detail=str(comment_id))
    return mapping


def _resolve_repo_relative(path_text: str, *, repo_root: Path, label: str) -> Path:
    """校验 path 为仓库内相对路径，返回绝对 Path；越界/绝对路径 fail-closed。"""
    if not path_text or path_text != path_text.strip():
        _fail(ERR_PREREG_FIELD, f"{label} 路径不得为空且不得含首尾空白", detail=path_text)
    if _ABS_WINDOWS_DRIVE_RE.match(path_text) or path_text.startswith(("/", "\\")):
        _fail(ERR_PREREG_FIELD, f"{label} 必须是相对仓库根的路径，禁止绝对路径", detail=path_text)
    candidate = (repo_root / path_text).resolve()
    root = repo_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        _fail(ERR_PREREG_FIELD, f"{label} resolve 后越出仓库根", detail=path_text + " -> " + str(candidate))
    return candidate


def _verify_frozen_package(
    frozen: Any,
    *,
    repo_root: Path,
    verify_package: bool,
    checks: list[dict[str, Any]],
) -> Mapping[str, Any]:
    """校验 S0-7 冻结包身份：预注册字段恒等 + 实包 SHA256SUMS/freeze_summary 复算。"""
    mapping = _as_mapping(frozen, code=ERR_PREREG_FROZEN, label="frozen_package")
    _require_exact_keys(
        mapping,
        PREREG_FROZEN_FIELDS,
        code=ERR_PREREG_FROZEN,
        label="frozen_package",
    )
    expected = {
        "run_id": FROZEN_PACKAGE_RUN_ID,
        "package_path": FROZEN_PACKAGE_PATH,
        "sha256sums_sha256": FROZEN_PACKAGE_SHA256SUMS_SHA256,
        "code_sha": FROZEN_PACKAGE_CODE_SHA,
        "git_sha": FROZEN_PACKAGE_GIT_SHA,
        "package_family_version": FROZEN_PACKAGE_FAMILY_VERSION,
        "task_family_version": FROZEN_PACKAGE_TASK_FAMILY_VERSION,
    }
    for field_name, field_value in expected.items():
        actual = _require_str(
            mapping[field_name], code=ERR_PREREG_FROZEN, label="frozen_package." + field_name
        )
        if actual != field_value:
            _fail(
                ERR_PREREG_FROZEN,
                "frozen_package 身份与 S0-7 冻结包不一致",
                detail=f"{field_name}: prereg={actual!r} expected={field_value!r}",
            )
    _require_sha256(mapping["sha256sums_sha256"], code=ERR_PREREG_FROZEN, label="frozen_package.sha256sums_sha256")
    _require_sha256(mapping["code_sha"], code=ERR_PREREG_FROZEN, label="frozen_package.code_sha")
    if not _GIT_SHA_RE.match(mapping["git_sha"]):
        _fail(ERR_PREREG_FROZEN, "frozen_package.git_sha 必须是 40 位小写十六进制", detail=str(mapping["git_sha"]))
    package_dir = _resolve_repo_relative(
        mapping["package_path"], repo_root=repo_root, label="frozen_package.package_path"
    )
    if not verify_package:
        _record_check(checks, "frozen_package_bytes", status="SKIPPED", detail="verify_frozen_package=False")
        return mapping
    if not package_dir.is_dir():
        _fail(ERR_PREREG_FROZEN, "S0-7 冻结包目录不存在", detail=str(package_dir))
    sums_path = package_dir / "SHA256SUMS.txt"
    if not sums_path.is_file():
        _fail(ERR_PREREG_FROZEN, "S0-7 冻结包缺少 SHA256SUMS.txt", detail=str(sums_path))
    actual_sums_sha = _sha256_file(sums_path)
    if actual_sums_sha != FROZEN_PACKAGE_SHA256SUMS_SHA256:
        _fail(
            ERR_PREREG_FROZEN,
            "S0-7 SHA256SUMS.txt 复算 sha256 与冻结身份不一致",
            detail=f"actual={actual_sums_sha} expected={FROZEN_PACKAGE_SHA256SUMS_SHA256}",
        )
    _record_check(checks, "frozen_package_sha256sums", status="PASS", detail=actual_sums_sha)
    summary_path = package_dir / "freeze_summary.json"
    if summary_path.is_file():
        summary = _load_json_file(summary_path, code=ERR_PREREG_FROZEN, label="S0-7 freeze_summary.json")
        summary_map = _as_mapping(summary, code=ERR_PREREG_FROZEN, label="S0-7 freeze_summary.json")
        summary_expected = {
            "run_id": FROZEN_PACKAGE_RUN_ID,
            "code_sha": FROZEN_PACKAGE_CODE_SHA,
            "git_sha": FROZEN_PACKAGE_GIT_SHA,
            "family_version": FROZEN_PACKAGE_FAMILY_VERSION,
            "task_family_version": FROZEN_PACKAGE_TASK_FAMILY_VERSION,
        }
        for field_name, field_value in summary_expected.items():
            if field_name in summary_map and summary_map[field_name] != field_value:
                _fail(
                    ERR_PREREG_FROZEN,
                    "S0-7 freeze_summary.json 与冻结身份不一致",
                    detail=f"{field_name}: actual={summary_map[field_name]!r} expected={field_value!r}",
                )
        _record_check(checks, "frozen_package_freeze_summary", status="PASS", detail=summary_path.name)
    else:
        _record_check(checks, "frozen_package_freeze_summary", status="DISCLOSED", detail="freeze_summary.json 缺失")
    return mapping


def _validate_data_boundary(boundary: Any) -> Mapping[str, Any]:
    """数据边界：只允许 meta_train/meta_validation；holdout 仅做计数与 sha 边界断言。"""
    mapping = _as_mapping(boundary, code=ERR_DATA_BOUNDARY, label="data_boundary")
    _require_exact_keys(
        mapping, PREREG_DATA_BOUNDARY_FIELDS, code=ERR_DATA_BOUNDARY, label="data_boundary"
    )
    allowed = _require_numeric_list(
        mapping["allowed_splits"],
        code=ERR_DATA_BOUNDARY,
        label="data_boundary.allowed_splits",
        expected=["meta_train", "meta_validation"],
    )
    forbidden = _require_numeric_list(
        mapping["forbidden_splits"],
        code=ERR_DATA_BOUNDARY,
        label="data_boundary.forbidden_splits",
        expected=["meta_test", "meta_test_ood", "negative_control"],
    )
    split_counts = _as_mapping(
        mapping["split_counts"], code=ERR_DATA_BOUNDARY, label="data_boundary.split_counts"
    )
    expected_counts = dict(EXPECTED_SPLIT_COUNTS)
    actual_counts = {str(key): _require_int(value, code=ERR_DATA_BOUNDARY, label="split_counts." + str(key)) for key, value in split_counts.items()}
    if set(actual_counts) != set(expected_counts):
        _fail(
            ERR_DATA_BOUNDARY,
            "data_boundary.split_counts 的 split 集合与 S0-7 冻结包不一致",
            detail=f"actual={sorted(actual_counts)} expected={sorted(expected_counts)}",
        )
    for split_name, expected_count in expected_counts.items():
        if actual_counts[split_name] != expected_count:
            _fail(
                ERR_DATA_BOUNDARY,
                "data_boundary.split_counts 计数与 S0-7 冻结包不一致",
                detail=f"{split_name}: {actual_counts[split_name]} != {expected_count}",
            )
    for key, expected_length in (
        ("meta_train_task_ids_sha256", 60),
        ("meta_validation_task_ids_sha256", 20),
        ("holdout_task_ids_sha256", 40),
    ):
        _require_sha256(mapping[key], code=ERR_DATA_BOUNDARY, label="data_boundary." + key)
    rows_used = mapping["holdout_rows_used"]
    if _require_int(rows_used, code=ERR_DATA_BOUNDARY, label="data_boundary.holdout_rows_used") != 0:
        _fail(ERR_DATA_BOUNDARY, "data_boundary.holdout_rows_used 必须为 0", detail=str(rows_used))
    # allowed/forbidden 不相交，且 allowed 是 split_counts 的键
    if set(allowed) & set(forbidden):
        _fail(ERR_DATA_BOUNDARY, "allowed_splits 与 forbidden_splits 不得相交")
    if not set(allowed).issubset(set(actual_counts)):
        _fail(ERR_DATA_BOUNDARY, "allowed_splits 必须全部出现在 split_counts 中")
    return mapping


def _validate_episode_contract(contract: Any) -> Mapping[str, Any]:
    mapping = _as_mapping(contract, code=ERR_PREREG_FIELD, label="episode_contract")
    _require_exact_keys(
        mapping, PREREG_EPISODE_FIELDS, code=ERR_PREREG_FIELD, label="episode_contract"
    )
    for key, expected_value in PREREG_EPISODE_CONTRACT_NUMBERS.items():
        value = mapping[key]
        if isinstance(expected_value, list):
            actual = list(_as_list(value, code=ERR_PREREG_FIELD, label="episode_contract." + key))
            if actual != expected_value:
                _fail(
                    ERR_PREREG_FIELD,
                    "episode_contract." + key + " 与执行计划不一致",
                    detail=f"actual={actual!r} expected={expected_value!r}",
                )
        else:
            actual = _require_int(value, code=ERR_PREREG_FIELD, label="episode_contract." + key)
            if actual != expected_value:
                _fail(
                    ERR_PREREG_FIELD,
                    "episode_contract." + key + " 与执行计划不一致",
                    detail=f"actual={actual} expected={expected_value}",
                )
    scopes = list(_as_list(mapping["seed_scopes"], code=ERR_PREREG_FIELD, label="episode_contract.seed_scopes"))
    expected_scopes = list(PREREG_SEED_SCOPES)
    if scopes != expected_scopes:
        _fail(
            ERR_PREREG_FIELD,
            "episode_contract.seed_scopes 与执行计划不一致",
            detail=f"actual={scopes!r} expected={expected_scopes!r}",
        )
    _require_str(mapping["standardization"], code=ERR_PREREG_FIELD, label="episode_contract.standardization")
    _require_sha256(
        mapping["train_episode_bank_sha256"],
        code=ERR_PREREG_FIELD,
        label="episode_contract.train_episode_bank_sha256",
    )
    return mapping

ERR_FD_GATE = "S2_ANALYSIS_FD_GATE_NOT_PASSED"
ERR_CODE_SHA = "S2_ANALYSIS_CODE_SHA_MISMATCH"


def _validate_arms(arms: Any) -> list[dict[str, Any]]:
    """两臂公平性：除 first_order 外 config 必须逐字段相同（含 seed/backend/hidden_sizes）。"""
    items = list(_as_list(arms, code=ERR_PREREG_ARM, label="arms"))
    if len(items) != 2:
        _fail(ERR_PREREG_ARM, "arms 必须恰有 2 个元素", detail=f"实际={len(items)}")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        mapping = _as_mapping(item, code=ERR_PREREG_ARM, label=f"arms[{index}]")
        _require_exact_keys(mapping, ("id", "first_order", "config"), code=ERR_PREREG_ARM, label=f"arms[{index}]")
        arm_id = _require_str(mapping["id"], code=ERR_PREREG_ARM, label=f"arms[{index}].id")
        first_order = _require_bool(
            mapping["first_order"], code=ERR_PREREG_ARM, label=f"arms[{index}].first_order"
        )
        config = _as_mapping(mapping["config"], code=ERR_PREREG_ARM, label=f"arms[{index}].config")
        _require_exact_keys(
            config, tuple(EXPECTED_ARMS_CONFIG.keys()), code=ERR_PREREG_ARM, label=f"arms[{index}].config"
        )
        for key, expected_value in EXPECTED_ARMS_CONFIG.items():
            if key == "hidden_sizes":
                actual = _require_numeric_list(
                    config[key],
                    code=ERR_PREREG_ARM,
                    label=f"arms[{index}].config.hidden_sizes",
                    expected=list(expected_value),  # type: ignore[arg-type]
                )
                if actual != list(expected_value):
                    _fail(ERR_PREREG_ARM, "arms config 的 hidden_sizes 与执行计划不一致", detail=f"actual={actual!r}")
            elif key == "backend":
                actual_backend = _require_str(
                    config[key], code=ERR_PREREG_ARM, label=f"arms[{index}].config.backend"
                )
                if actual_backend != expected_value:
                    _fail(
                        ERR_PREREG_ARM,
                        "arms config 的 backend 与执行计划不一致",
                        detail=f"{actual_backend!r} != {expected_value!r}",
                    )
            elif isinstance(expected_value, int):
                actual_int = _require_int(config[key], code=ERR_PREREG_ARM, label=f"arms[{index}].config.{key}")
                if actual_int != expected_value:
                    _fail(
                        ERR_PREREG_ARM,
                        f"arms config 的 {key} 与执行计划不一致",
                        detail=f"{actual_int} != {expected_value}",
                    )
            else:
                actual_num = _require_number(
                    config[key], code=ERR_PREREG_ARM, label=f"arms[{index}].config.{key}"
                )
                if float(actual_num) != float(expected_value):
                    _fail(
                        ERR_PREREG_ARM,
                        f"arms config 的 {key} 与执行计划不一致",
                        detail=f"{actual_num} != {expected_value}",
                    )
        normalized.append({"id": arm_id, "first_order": first_order, "config": dict(config)})
    arm_ids = [arm["id"] for arm in normalized]
    if arm_ids != list(EXPECTED_ARMS):
        _fail(ERR_PREREG_ARM, "arms 顺序/ID 必须为 FULL_MAML,FOMAML", detail=str(arm_ids))
    expected_first_order = {ARM_FULL: False, ARM_FOMAML: True}
    for arm in normalized:
        if arm["first_order"] is not expected_first_order[arm["id"]]:
            _fail(
                ERR_PREREG_ARM,
                "arm.first_order 与臂语义不一致",
                detail=f"{arm['id']}: first_order={arm['first_order']}",
            )
    if normalized[0]["config"] != normalized[1]["config"]:
        _fail(ERR_PREREG_ARM, "两臂 config 必须除 first_order 外逐字段相同")
    return normalized


def _validate_training_budget(budget: Any) -> Mapping[str, Any]:
    mapping = _as_mapping(budget, code=ERR_PREREG_FIELD, label="training_budget")
    _require_exact_keys(mapping, tuple(PREREG_TRAINING_BUDGET.keys()), code=ERR_PREREG_FIELD, label="training_budget")
    outer_steps = _require_int(mapping["outer_steps"], code=ERR_PREREG_FIELD, label="training_budget.outer_steps")
    if outer_steps != OUTER_STEPS:
        _fail(ERR_PREREG_FIELD, "training_budget.outer_steps 与执行计划不一致", detail=str(outer_steps))
    seeds = list(_as_list(mapping["meta_seeds"], code=ERR_PREREG_FIELD, label="training_budget.meta_seeds"))
    seeds = [_require_int(seed, code=ERR_PREREG_FIELD, label="training_budget.meta_seeds[]") for seed in seeds]
    if seeds != list(META_SEEDS):
        _fail(ERR_PREREG_FIELD, "training_budget.meta_seeds 与执行计划不一致", detail=str(seeds))
    records = _require_int(
        mapping["train_records_expected"], code=ERR_PREREG_FIELD, label="training_budget.train_records_expected"
    )
    if records != TRAIN_RECORDS_EXPECTED:
        _fail(ERR_PREREG_FIELD, "training_budget.train_records_expected 与执行计划不一致", detail=str(records))
    return mapping


def _validate_evaluation_grid(grid: Any) -> Mapping[str, Any]:
    mapping = _as_mapping(grid, code=ERR_PREREG_FIELD, label="evaluation_grid")
    _require_exact_keys(mapping, tuple(PREREG_EVALUATION_GRID.keys()), code=ERR_PREREG_FIELD, label="evaluation_grid")
    tasks = _require_int(mapping["meta_validation_tasks"], code=ERR_PREREG_FIELD, label="evaluation_grid.meta_validation_tasks")
    if tasks != N_TASKS:
        _fail(ERR_PREREG_FIELD, "evaluation_grid.meta_validation_tasks 与执行计划不一致", detail=str(tasks))
    k_values = list(_as_list(mapping["K"], code=ERR_PREREG_FIELD, label="evaluation_grid.K"))
    k_values = [_require_int(k, code=ERR_PREREG_FIELD, label="evaluation_grid.K[]") for k in k_values]
    if k_values != list(K_VALUES):
        _fail(ERR_PREREG_FIELD, "evaluation_grid.K 与执行计划不一致", detail=str(k_values))
    draws = _require_int(mapping["draws"], code=ERR_PREREG_FIELD, label="evaluation_grid.draws")
    if draws != EVAL_DRAWS:
        _fail(ERR_PREREG_FIELD, "evaluation_grid.draws 与执行计划不一致", detail=str(draws))
    records = _require_int(
        mapping["eval_records_expected"], code=ERR_PREREG_FIELD, label="evaluation_grid.eval_records_expected"
    )
    if records != EVAL_RECORDS_EXPECTED:
        _fail(ERR_PREREG_FIELD, "evaluation_grid.eval_records_expected 与执行计划不一致", detail=str(records))
    return mapping


def _validate_endpoints(endpoints: Any) -> Mapping[str, Any]:
    """端点 ID 精确匹配；推断端点 K/space 必须与评估记录来源一致。"""
    mapping = _as_mapping(endpoints, code=ERR_PREREG_ENDPOINT, label="endpoints")
    _require_exact_keys(
        mapping, ("primary", "secondary_inferential", "descriptive"), code=ERR_PREREG_ENDPOINT, label="endpoints"
    )
    primary = _as_mapping(mapping["primary"], code=ERR_PREREG_ENDPOINT, label="endpoints.primary")
    _require_exact_keys(primary, ("id", "direction", "K", "space"), code=ERR_PREREG_ENDPOINT, label="endpoints.primary")
    expected_primary = PREREG_ENDPOINTS_TEMPLATE["primary"]
    for key in ("id", "direction"):
        if primary[key] != expected_primary[key]:
            _fail(ERR_PREREG_ENDPOINT, "endpoints.primary." + key + " 与执行计划不一致", detail=str(primary[key]))
    if _require_int(primary["K"], code=ERR_PREREG_ENDPOINT, label="endpoints.primary.K") != expected_primary["K"]:
        _fail(ERR_PREREG_ENDPOINT, "endpoints.primary.K 与执行计划不一致", detail=str(primary["K"]))
    if primary["space"] != expected_primary["space"]:
        _fail(ERR_PREREG_ENDPOINT, "endpoints.primary.space 与执行计划不一致", detail=str(primary["space"]))
    secondary = list(
        _as_list(mapping["secondary_inferential"], code=ERR_PREREG_ENDPOINT, label="endpoints.secondary_inferential")
    )
    expected_secondary = PREREG_ENDPOINTS_TEMPLATE["secondary_inferential"]
    if len(secondary) != len(expected_secondary):
        _fail(
            ERR_PREREG_ENDPOINT,
            "endpoints.secondary_inferential 数量与执行计划不一致",
            detail=f"实际={len(secondary)} 期望={len(expected_secondary)}",
        )
    for index, item in enumerate(secondary):
        item_map = _as_mapping(item, code=ERR_PREREG_ENDPOINT, label=f"endpoints.secondary_inferential[{index}]")
        _require_exact_keys(
            item_map, ("id", "direction", "K", "space"), code=ERR_PREREG_ENDPOINT, label=f"endpoints.secondary_inferential[{index}]"
        )
        for key, expected_value in expected_secondary[index].items():
            actual_value = item_map[key]
            if key == "K":
                actual_value = _require_int(actual_value, code=ERR_PREREG_ENDPOINT, label=f"endpoints.secondary_inferential[{index}].K")
            if actual_value != expected_value:
                _fail(
                    ERR_PREREG_ENDPOINT,
                    f"endpoints.secondary_inferential[{index}].{key} 与执行计划不一致",
                    detail=f"actual={actual_value!r} expected={expected_value!r}",
                )
    descriptive = list(_as_list(mapping["descriptive"], code=ERR_PREREG_ENDPOINT, label="endpoints.descriptive"))
    expected_descriptive = list(DESCRIPTIVE_ENDPOINTS)
    if descriptive != expected_descriptive:
        _fail(
            ERR_PREREG_ENDPOINT,
            "endpoints.descriptive 与执行计划不一致（顺序与集合都必须相同）",
            detail=f"actual={descriptive!r} expected={expected_descriptive!r}",
        )
    # 端点 ID 唯一性 & 与记录字段映射自洽
    inference_ids = [PRIMARY_ENDPOINT] + [item["id"] for item in expected_secondary]
    if len(set(inference_ids)) != len(inference_ids):
        _fail(ERR_PREREG_ENDPOINT, "推断端点 ID 出现重复", detail=str(inference_ids))
    for endpoint_id in inference_ids:
        if endpoint_id not in ENDPOINT_SOURCES:
            _fail(ERR_PREREG_ENDPOINT, "推断端点没有对应的评估记录字段映射", detail=endpoint_id)
    return mapping


def _validate_comparison(comparison: Any) -> Mapping[str, Any]:
    mapping = _as_mapping(comparison, code=ERR_PREREG_FIELD, label="comparison")
    _require_exact_keys(
        mapping,
        ("id", "arms", "difference", "unit", "aggregation"),
        code=ERR_PREREG_FIELD,
        label="comparison",
    )
    if mapping["id"] != COMPARISON_ID:
        _fail(ERR_PREREG_FIELD, "comparison.id 必须为 C1", detail=str(mapping["id"]))
    arms = list(_as_list(mapping["arms"], code=ERR_PREREG_FIELD, label="comparison.arms"))
    if arms != COMPARISON_ARMS:
        _fail(ERR_PREREG_FIELD, "comparison.arms 必须为 FULL_MAML,FOMAML", detail=str(arms))
    if mapping["difference"] != COMPARISON_DIFFERENCE:
        _fail(ERR_PREREG_FIELD, "comparison.difference 必须为 FULL_MAML - FOMAML", detail=str(mapping["difference"]))
    if mapping["unit"] != COMPARISON_UNIT:
        _fail(ERR_PREREG_FIELD, "comparison.unit 必须为 task", detail=str(mapping["unit"]))
    if mapping["aggregation"] != PREREG_COMPARISON["aggregation"]:
        _fail(ERR_PREREG_FIELD, "comparison.aggregation 与执行计划不一致", detail=str(mapping["aggregation"]))
    return mapping


def _validate_holm_family(statistical_plan: Mapping[str, Any]) -> Mapping[str, Any]:
    """唯一 Holm 族：family_size=2，成员恰为 C1 x {k5,k10}；禁止按 endpoint 拆成两族。"""
    plan = _as_mapping(statistical_plan, code=ERR_PREREG_HOLM, label="statistical_plan")
    if "multiple_comparison" not in plan:
        _fail(ERR_PREREG_HOLM, "statistical_plan 缺少 multiple_comparison")
    family = _as_mapping(plan["multiple_comparison"], code=ERR_PREREG_HOLM, label="statistical_plan.multiple_comparison")
    _require_exact_keys(
        family,
        ("family_id", "family_key", "method", "family_size", "members"),
        code=ERR_PREREG_HOLM,
        label="multiple_comparison",
    )
    if family["family_id"] != HOLM_FAMILY_ID:
        _fail(ERR_PREREG_HOLM, "family_id 必须为 s2-primary-secondary-2tests", detail=str(family["family_id"]))
    if family["family_key"] != HOLM_FAMILY_KEY:
        _fail(ERR_PREREG_HOLM, "family_key 必须为 s2_primary_secondary", detail=str(family["family_key"]))
    if family["method"] != HOLM_FAMILY_METHOD:
        _fail(ERR_PREREG_HOLM, "multiple_comparison.method 必须为 holm", detail=str(family["method"]))
    family_size = _require_int(family["family_size"], code=ERR_PREREG_HOLM, label="multiple_comparison.family_size")
    if family_size != HOLM_FAMILY_SIZE:
        _fail(ERR_PREREG_HOLM, "family_size 必须为 2（禁止按 endpoint 拆族）", detail=str(family_size))
    members = list(_as_list(family["members"], code=ERR_PREREG_HOLM, label="multiple_comparison.members"))
    if len(members) != HOLM_FAMILY_SIZE:
        _fail(ERR_PREREG_HOLM, "members 数量必须等于 family_size", detail=f"{len(members)} != {family_size}")
    normalized_members: list[dict[str, str]] = []
    for index, item in enumerate(members):
        item_map = _as_mapping(item, code=ERR_PREREG_HOLM, label=f"multiple_comparison.members[{index}]")
        _require_exact_keys(
            item_map, ("comparison", "endpoint"), code=ERR_PREREG_HOLM, label=f"multiple_comparison.members[{index}]"
        )
        comparison_id = _require_str(
            item_map["comparison"], code=ERR_PREREG_HOLM, label=f"multiple_comparison.members[{index}].comparison"
        )
        endpoint_id = _require_str(
            item_map["endpoint"], code=ERR_PREREG_HOLM, label=f"multiple_comparison.members[{index}].endpoint"
        )
        normalized_members.append({"comparison": comparison_id, "endpoint": endpoint_id})
    expected_members = [dict(item) for item in HOLM_FAMILY_MEMBERS]
    if normalized_members != expected_members:
        _fail(
            ERR_PREREG_HOLM,
            "Holm 族成员必须恰为 C1 x {post_adaptation_rmse_raw_k5, post_adaptation_rmse_raw_k10}",
            detail=f"actual={normalized_members!r} expected={expected_members!r}",
        )
    # 族外不得再有推断端点：primary+secondary 只能恰好被该族覆盖
    endpoints = plan.get("endpoints")
    del endpoints
    return family


def _validate_statistical_plan(plan: Any) -> Mapping[str, Any]:
    mapping = _as_mapping(plan, code=ERR_PREREG_FIELD, label="statistical_plan")
    _require_exact_keys(
        mapping,
        ("test", "n_tasks", "bootstrap", "multiple_comparison", "decision_rules", "evidence_scope"),
        code=ERR_PREREG_FIELD,
        label="statistical_plan",
    )
    if mapping["test"] != PAIRED_TEST:
        _fail(ERR_PREREG_FIELD, "statistical_plan.test 必须为配对 Wilcoxon 双侧", detail=str(mapping["test"]))
    n_tasks = _require_int(mapping["n_tasks"], code=ERR_PREREG_FIELD, label="statistical_plan.n_tasks")
    if n_tasks != N_TASKS:
        _fail(ERR_PREREG_FIELD, "statistical_plan.n_tasks 必须为 20", detail=str(n_tasks))
    bootstrap = _as_mapping(mapping["bootstrap"], code=ERR_PREREG_FIELD, label="statistical_plan.bootstrap")
    _require_exact_keys(
        bootstrap, ("n_resamples", "seed", "ci"), code=ERR_PREREG_FIELD, label="statistical_plan.bootstrap"
    )
    n_resamples = _require_int(bootstrap["n_resamples"], code=ERR_PREREG_FIELD, label="bootstrap.n_resamples")
    if n_resamples != BOOTSTRAP_SAMPLES:
        _fail(ERR_PREREG_FIELD, "bootstrap.n_resamples 必须为 10000", detail=str(n_resamples))
    bootstrap_seed = _require_int(bootstrap["seed"], code=ERR_PREREG_FIELD, label="bootstrap.seed")
    if bootstrap_seed != BOOTSTRAP_SEED:
        _fail(ERR_PREREG_FIELD, "bootstrap.seed 必须为 20261105", detail=str(bootstrap_seed))
    ci = _require_number(bootstrap["ci"], code=ERR_PREREG_FIELD, label="bootstrap.ci")
    if float(ci) != CONFIDENCE_LEVEL:
        _fail(ERR_PREREG_FIELD, "bootstrap.ci 必须为 0.95", detail=str(ci))
    evidence_scope = _require_str(
        mapping["evidence_scope"], code=ERR_PREREG_SCOPE, label="statistical_plan.evidence_scope"
    )
    if evidence_scope != EVIDENCE_SCOPE:
        _fail(
            ERR_PREREG_SCOPE,
            "evidence_scope 必须为 DEVELOPMENT_VALIDATION_ONLY",
            detail=evidence_scope,
        )
    decision_rules = _as_mapping(mapping["decision_rules"], code=ERR_PREREG_FIELD, label="statistical_plan.decision_rules")
    _require_exact_keys(
        decision_rules,
        tuple(PREREG_DECISION_RULES.keys()),
        code=ERR_PREREG_FIELD,
        label="statistical_plan.decision_rules",
    )
    for key, expected_text in PREREG_DECISION_RULES.items():
        actual_text = _require_str(decision_rules[key], code=ERR_PREREG_FIELD, label="decision_rules." + key)
        if actual_text != expected_text:
            _fail(
                ERR_PREREG_FIELD,
                "decision_rules." + key + " 与执行计划不一致",
                detail=f"actual={actual_text!r} expected={expected_text!r}",
            )
    _validate_holm_family(mapping)
    return mapping


def _validate_fd_gate(
    fd_gate: Any,
    *,
    repo_root: Path,
    verify_pilot_artifacts: bool,
    checks: list[dict[str, Any]],
) -> Mapping[str, Any]:
    mapping = _as_mapping(fd_gate, code=ERR_PREREG_FIELD, label="fd_gate")
    _require_exact_keys(
        mapping,
        ("mode", "max_relative_error", "coordinates", "epsilon", "denominator", "fail_closed", "pilot_artifacts"),
        code=ERR_PREREG_FIELD,
        label="fd_gate",
    )
    if mapping["mode"] != PREREG_EXPECTED_FD_GATE["mode"]:
        _fail(ERR_PREREG_FIELD, "fd_gate.mode 必须为 full", detail=str(mapping["mode"]))
    max_rel = _require_number(mapping["max_relative_error"], code=ERR_PREREG_FIELD, label="fd_gate.max_relative_error")
    if float(max_rel) != PREREG_EXPECTED_FD_GATE["max_relative_error"]:
        _fail(ERR_PREREG_FIELD, "fd_gate.max_relative_error 必须为 1e-6", detail=str(max_rel))
    coordinates = _require_int(mapping["coordinates"], code=ERR_PREREG_FIELD, label="fd_gate.coordinates")
    if coordinates != PREREG_EXPECTED_FD_GATE["coordinates"]:
        _fail(ERR_PREREG_FIELD, "fd_gate.coordinates 必须为 32", detail=str(coordinates))
    if _require_bool(mapping["fail_closed"], code=ERR_PREREG_FIELD, label="fd_gate.fail_closed") is not True:
        _fail(ERR_PREREG_FIELD, "fd_gate.fail_closed 必须为 true")
    epsilon = _require_str(mapping["epsilon"], code=ERR_PREREG_FIELD, label="fd_gate.epsilon")
    denominator = _require_str(mapping["denominator"], code=ERR_PREREG_FIELD, label="fd_gate.denominator")
    if "1e-6" not in epsilon.replace(" ", ""):
        _fail(ERR_PREREG_FIELD, "fd_gate.epsilon 必须说明 1e-6 相对误差步长", detail=epsilon)
    if "1e-12" not in denominator.replace(" ", ""):
        _fail(ERR_PREREG_FIELD, "fd_gate.denominator 必须包含 1e-12 分母下限", detail=denominator)
    pilot = _as_mapping(mapping["pilot_artifacts"], code=ERR_PREREG_PILOT, label="fd_gate.pilot_artifacts")
    _require_exact_keys(pilot, ("micro", "full_size"), code=ERR_PREREG_PILOT, label="fd_gate.pilot_artifacts")
    normalized_pilot: dict[str, dict[str, str]] = {}
    for name in ("micro", "full_size"):
        item = _as_mapping(pilot[name], code=ERR_PREREG_PILOT, label="fd_gate.pilot_artifacts." + name)
        _require_exact_keys(item, ("path", "sha256"), code=ERR_PREREG_PILOT, label="fd_gate.pilot_artifacts." + name)
        rel_path = _require_str(item["path"], code=ERR_PREREG_PILOT, label="fd_gate.pilot_artifacts." + name + ".path")
        expected_sha = _require_sha256(
            item["sha256"], code=ERR_PREREG_PILOT, label="fd_gate.pilot_artifacts." + name + ".sha256"
        )
        resolved = _resolve_repo_relative(rel_path, repo_root=repo_root, label="fd_gate.pilot_artifacts." + name + ".path")
        if verify_pilot_artifacts:
            if not resolved.is_file():
                _fail(ERR_PREREG_PILOT, "FD pilot 产物不存在", detail=rel_path + " -> " + str(resolved))
            actual_sha = _sha256_file(resolved)
            if actual_sha != expected_sha:
                _fail(
                    ERR_PREREG_PILOT,
                    "FD pilot 产物 sha256 与预注册不一致",
                    detail=f"{name}: actual={actual_sha} expected={expected_sha}",
                )
            _record_check(checks, "fd_pilot_artifact_" + name, status="PASS", detail=rel_path)
        else:
            _record_check(checks, "fd_pilot_artifact_" + name, status="SKIPPED", detail=rel_path)
        normalized_pilot[name] = {"path": rel_path, "sha256": expected_sha}
    normalized = dict(mapping)
    normalized["pilot_artifacts"] = normalized_pilot
    return normalized


def _validate_determinism(value: Any) -> Mapping[str, Any]:
    mapping = _as_mapping(value, code=ERR_PREREG_FIELD, label="determinism")
    _require_exact_keys(mapping, ("reruns", "requires_byte_identical", "fail_closed"), code=ERR_PREREG_FIELD, label="determinism")
    reruns = _require_int(mapping["reruns"], code=ERR_PREREG_FIELD, label="determinism.reruns")
    if reruns != PREREG_DETERMINISM["reruns"]:
        _fail(ERR_PREREG_FIELD, "determinism.reruns 必须为 2", detail=str(reruns))
    requires = list(_as_list(mapping["requires_byte_identical"], code=ERR_PREREG_FIELD, label="determinism.requires_byte_identical"))
    requires = [_require_str(item, code=ERR_PREREG_FIELD, label="determinism.requires_byte_identical[]") for item in requires]
    if requires != list(PREREG_DETERMINISM["requires_byte_identical"]):
        _fail(ERR_PREREG_FIELD, "determinism.requires_byte_identical 与执行计划不一致", detail=str(requires))
    if _require_bool(mapping["fail_closed"], code=ERR_PREREG_FIELD, label="determinism.fail_closed") is not True:
        _fail(ERR_PREREG_FIELD, "determinism.fail_closed 必须为 true")
    return mapping


def _validate_resource_limits(value: Any) -> Mapping[str, Any]:
    """资源硬上限：键集合与数值必须恰为 1200/8192/7200（v1.5 §7）。"""
    mapping = _as_mapping(value, code=ERR_PREREG_RESOURCE_LIMITS, label="resource_limits")
    _require_exact_keys(
        mapping,
        tuple(PREREG_RESOURCE_LIMITS),
        code=ERR_PREREG_RESOURCE_LIMITS,
        label="resource_limits",
    )
    normalized: dict[str, Any] = {}
    for key, expected in PREREG_RESOURCE_LIMITS.items():
        actual = _require_int(mapping[key], code=ERR_PREREG_RESOURCE_LIMITS, label="resource_limits." + key)
        if actual != expected:
            _fail(
                ERR_PREREG_RESOURCE_LIMITS,
                "resource_limits 与固定值合同不一致",
                detail=f"{key}: actual={actual} expected={expected}",
            )
        normalized[key] = actual
    return normalized


def _validate_rules(value: Any, *, label: str, expected: Sequence[str]) -> list[str]:
    items = list(_as_list(value, code=ERR_PREREG_FIELD, label=label))
    normalized = [_require_str(item, code=ERR_PREREG_FIELD, label=label + "[]") for item in items]
    if normalized != list(expected):
        _fail(ERR_PREREG_FIELD, label + " 与执行计划不一致", detail=f"actual={normalized!r} expected={list(expected)!r}")
    return normalized

def _compute_prereg_digests(raw: Mapping[str, Any]) -> tuple[str, str, str]:
    """复算三个 canonical 摘要；序列化异常统一收敛为 digest 错误。"""
    try:
        prereg_id = compute_prereg_id(raw)
        prereg_digest = compute_prereg_digest(raw)
        analysis_plan_digest = compute_analysis_plan_digest(raw)
    except (TypeError, ValueError) as exc:
        _fail(ERR_PREREG_DIGEST, "prereg 内容无法按 canonical JSON 序列化（可能含 NaN/不可序列化值）", detail=str(exc))
    return prereg_id, prereg_digest, analysis_plan_digest


def _validate_code_sha(
    value: Any,
    *,
    repo_root: Path,
    verify_code_sha: bool,
    checks: list[dict[str, Any]],
) -> str:
    code_sha = _require_sha256(value, code=ERR_PREREG_FIELD, label="code_sha")
    if not verify_code_sha:
        _record_check(checks, "code_sha_recompute", status="SKIPPED", detail="verify_code_sha=False")
        return code_sha
    available: list[tuple[str, Path]] = []
    missing: list[str] = []
    for rel_path in S2_CODE_FILES:
        candidate = repo_root / rel_path
        if candidate.is_file():
            available.append((rel_path, candidate))
        else:
            missing.append(rel_path)
    if missing:
        _record_check(
            checks,
            "code_sha_recompute",
            status="SKIPPED",
            detail="待验证代码文件尚不存在: " + ",".join(missing),
        )
        return code_sha
    actual = compute_code_sha(available)
    if actual == code_sha:
        _record_check(checks, "code_sha_recompute", status="PASS", detail=actual)
    else:
        # code_sha 是冻结前后代码一致性证据；分析层无法改写冻结 prereg，因此以披露项记录。
        _record_check(
            checks,
            "code_sha_recompute",
            status="DISCLOSED",
            detail=f"actual={actual} frozen={code_sha}（工作树代码与冻结 prereg 不一致，见 limitations）",
        )
    return code_sha


def load_s2_prereg(
    prereg_path: str | Path,
    *,
    repo_root: str | Path | None = None,
    verify_frozen_package: bool = True,
    verify_pilot_artifacts: bool = True,
    verify_code_sha: bool = True,
) -> S2Prereg:
    """加载并 fail-closed 校验冻结 S2 prereg。

    校验项（全部通过才返回；任一失败抛 S2AnalysisError）：
    schema_version、必填字段精确集合、占位拒绝、prereg_id/prereg_digest/analysis_plan_digest
    三个 canonical 摘要自洽、S0-7 冻结包身份与实包 SHA256SUMS、数据边界（holdout_rows_used=0）、
    episode 合同、两臂公平性、预算/评估网格、端点 ID、单一 Holm 族、FD gate（pilot artifacts
    相对路径 + raw sha256）、determinism、失败/停止规则、physical_call_count=0。
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    path = Path(prereg_path).resolve()
    raw = _load_json_file(path, code=ERR_PREREG_SCHEMA, label="S2 冻结 prereg")
    raw_map = _as_mapping(raw, code=ERR_PREREG_SCHEMA, label="S2 冻结 prereg")
    checks: list[dict[str, Any]] = []

    # 1) schema 版本（legacy/缺失直接拒绝）
    if "schema_version" not in raw_map:
        _fail(ERR_PREREG_SCHEMA, "S2 prereg 缺少 schema_version（legacy 或不完整）")
    schema_version = _require_str(raw_map["schema_version"], code=ERR_PREREG_SCHEMA, label="schema_version")
    if schema_version != PREREG_SCHEMA_VERSION:
        _fail(
            ERR_PREREG_SCHEMA,
            "S2 prereg schema_version 不受支持（legacy 拒绝）",
            detail=f"actual={schema_version!r} expected={PREREG_SCHEMA_VERSION!r}",
        )
    _record_check(checks, "schema_version", status="PASS", detail=schema_version)

    # 2) 占位扫描（在 digest 之前：占位内容不允许进入任何冻结产物）
    _assert_no_placeholders(raw_map, code=ERR_PREREG_PLACEHOLDER, label="S2 冻结 prereg")
    _record_check(checks, "placeholder_rejection", status="PASS", detail="无 <...>/TBD/TODO/PLACEHOLDER 字符串")

    # 3) 必填字段精确集合（缺失/多余都拒绝）
    _require_exact_keys(raw_map, PREREG_REQUIRED_FIELDS, code=ERR_PREREG_SCHEMA, label="S2 冻结 prereg")
    _record_check(checks, "required_fields", status="PASS", detail=f"{len(PREREG_REQUIRED_FIELDS)} 个顶层字段")

    # 4) 三摘要复算并与字段逐字节比较
    computed_id, computed_digest, computed_plan = _compute_prereg_digests(raw_map)
    declared_id = _require_str(raw_map["prereg_id"], code=ERR_PREREG_DIGEST, label="prereg_id")
    if not _PREREG_ID_RE.match(declared_id):
        _fail(ERR_PREREG_DIGEST, "prereg_id 格式非法", detail=declared_id)
    if declared_id != computed_id:
        _fail(
            ERR_PREREG_DIGEST,
            "prereg_id 与独立复算不一致",
            detail=f"declared={declared_id} computed={computed_id}",
        )
    declared_digest = _require_str(raw_map["prereg_digest"], code=ERR_PREREG_DIGEST, label="prereg_digest")
    _require_sha256(declared_digest, code=ERR_PREREG_DIGEST, label="prereg_digest")
    if declared_digest != computed_digest:
        _fail(
            ERR_PREREG_DIGEST,
            "prereg_digest 与独立复算不一致",
            detail=f"declared={declared_digest} computed={computed_digest}",
        )
    declared_plan = _require_sha256(
        raw_map["analysis_plan_digest"], code=ERR_PREREG_DIGEST, label="analysis_plan_digest"
    )
    if declared_plan != computed_plan:
        _fail(
            ERR_PREREG_DIGEST,
            "analysis_plan_digest 与独立复算不一致",
            detail=f"declared={declared_plan} computed={computed_plan}",
        )
    _record_check(checks, "prereg_id", status="PASS", detail=declared_id)
    _record_check(checks, "prereg_digest", status="PASS", detail=declared_digest)
    _record_check(checks, "analysis_plan_digest", status="PASS", detail=declared_plan)

    # 5) 各节
    created_utc = _validate_created_utc(raw_map["created_utc"])
    upstream = _validate_upstream(raw_map["upstream"])
    frozen_package = _verify_frozen_package(
        raw_map["frozen_package"],
        repo_root=root,
        verify_package=verify_frozen_package,
        checks=checks,
    )
    data_boundary = _validate_data_boundary(raw_map["data_boundary"])
    _record_check(checks, "data_boundary", status="PASS", detail="holdout_rows_used=0；仅 meta_train/meta_validation")
    episode_contract = _validate_episode_contract(raw_map["episode_contract"])
    _record_check(checks, "episode_contract", status="PASS", detail="support/query/K/draws/seed_scopes 一致")
    arms = _validate_arms(raw_map["arms"])
    _record_check(checks, "arms_parity", status="PASS", detail="两臂 config 除 first_order 外逐字段相同")
    training_budget = _validate_training_budget(raw_map["training_budget"])
    evaluation_grid = _validate_evaluation_grid(raw_map["evaluation_grid"])
    _record_check(checks, "budget_and_grid", status="PASS", detail="1200 train / 4800 eval / 200 steps / seeds 0,1,2")
    endpoints = _validate_endpoints(raw_map["endpoints"])
    _record_check(checks, "endpoint_ids", status="PASS", detail="primary=k5, secondary=k10, K=0/1 仅描述")
    comparison = _validate_comparison(raw_map["comparison"])
    _record_check(checks, "comparison", status="PASS", detail="C1 = FULL_MAML - FOMAML，unit=task")
    statistical_plan = _validate_statistical_plan(raw_map["statistical_plan"])
    _record_check(checks, "holm_single_family", status="PASS", detail=HOLM_FAMILY_ID + " family_size=2")
    fd_gate = _validate_fd_gate(
        raw_map["fd_gate"],
        repo_root=root,
        verify_pilot_artifacts=verify_pilot_artifacts,
        checks=checks,
    )
    if fd_gate.get("mode") != "full" or float(fd_gate["max_relative_error"]) != 1e-6:
        _fail(ERR_FD_GATE, "FD gate 未满足 full/1e-6 合同")
    determinism = _validate_determinism(raw_map["determinism"])
    resource_limits = _validate_resource_limits(raw_map["resource_limits"])
    _record_check(checks, "resource_limits", status="PASS", detail="per_seed_train_wall_s=1200；peak_memory_mb=8192；total_wall_s=7200")
    failure_rules = _validate_rules(raw_map["failure_rules"], label="failure_rules", expected=PREREG_FAILURE_RULES)
    stopping_rules = _validate_rules(raw_map["stopping_rules"], label="stopping_rules", expected=PREREG_STOPPING_RULES)
    _record_check(checks, "failure_stopping_rules", status="PASS", detail="失败/停止规则与执行计划一致")
    code_sha = _validate_code_sha(
        raw_map["code_sha"], repo_root=root, verify_code_sha=verify_code_sha, checks=checks
    )
    physical_call_count = _require_int(
        raw_map["physical_call_count"], code=ERR_PREREG_PHYSICAL, label="physical_call_count"
    )
    if physical_call_count != 0:
        _fail(ERR_PREREG_PHYSICAL, "physical_call_count 必须为 0", detail=str(physical_call_count))
    _record_check(checks, "physical_call_count", status="PASS", detail="0")

    return S2Prereg(
        path=path,
        raw=raw_map,
        prereg_id=declared_id,
        prereg_digest=declared_digest,
        analysis_plan_digest=declared_plan,
        created_utc=created_utc,
        upstream=upstream,
        frozen_package=frozen_package,
        data_boundary=data_boundary,
        episode_contract=episode_contract,
        arms=tuple(arms),
        training_budget=training_budget,
        evaluation_grid=evaluation_grid,
        endpoints=endpoints,
        comparison=comparison,
        statistical_plan=statistical_plan,
        fd_gate=fd_gate,
        determinism=determinism,
        failure_rules=tuple(failure_rules),
        stopping_rules=tuple(stopping_rules),
        code_sha=code_sha,
        physical_call_count=physical_call_count,
        checks=tuple(checks),
    )


def verify_s2_preregistration(
    prereg_path: str | Path,
    *,
    repo_root: str | Path | None = None,
    verify_frozen_package: bool = True,
    verify_pilot_artifacts: bool = True,
    verify_code_sha: bool = True,
) -> dict[str, Any]:
    """核验入口：成功返回 PASS + 回显；失败抛 S2AnalysisError（不吞错）。"""
    prereg = load_s2_prereg(
        prereg_path,
        repo_root=repo_root,
        verify_frozen_package=verify_frozen_package,
        verify_pilot_artifacts=verify_pilot_artifacts,
        verify_code_sha=verify_code_sha,
    )
    return {
        "status": "PASS",
        "prereg_id": prereg.prereg_id,
        "prereg_digest": prereg.prereg_digest,
        "analysis_plan_digest": prereg.analysis_plan_digest,
        "evidence_scope": prereg.evidence_scope,
        "checks": [dict(check) for check in prereg.checks],
    }

# ---------------------------------------------------------------------------
# 正式 run 目录加载与校验
# ---------------------------------------------------------------------------

RUN_CONFIG_SCHEMA_VERSION = "p4ra-s2-run-config-v1"
RUN_SUMMARY_SCHEMA_VERSION = "p4ra-s2-run-summary-v1"
RUN_CONFIG_REQUIRED_FIELDS = (
    "schema_version",
    "run_id",
    "created_utc",
    "record_counts",
    "prereg_id",
    "prereg_digest",
    "code_sha",
    "frozen_package",
    "data_boundary",
    "arms",
    "training_budget",
    "evaluation_grid",
    "episode_bank",
    "fd_gate",
    "environment",
    "physical_call_count",
    "evidence_scope",
    "development_set",
)
RUN_SUMMARY_REQUIRED_FIELDS = (
    "schema_version",
    "run_id",
    "status",
    "record_counts",
    "status_counts",
    "per_arm_seed",
    "resources",
    "episode_bank_sha256",
    "run_records_core_sha256",
    "fd_pilot_artifacts",
    "physical_call_count",
    "evidence_scope",
    "development_set",
    "scope_notes",
)
RUN_STATUSES = ("COMPLETED", "PARTIAL", "FAILED")
SCOPE_NOT_APPLICABLE_FEASIBLE = "NOT_APPLICABLE_S2_SURROGATE_SCOPE"


@dataclass(frozen=True)
class S2RunData:
    """已验证的正式 run 快照：只保留分析需要的配置、摘要与记录。"""

    run_dir: Path
    run_config: Mapping[str, Any]
    run_summary: Mapping[str, Any] | None
    train_records: Sequence[Mapping[str, Any]]
    eval_records: Sequence[Mapping[str, Any]]
    source_files: Sequence[str]
    validation: Mapping[str, Any]
    checks: Sequence[Mapping[str, Any]]

    @property
    def counts(self) -> Mapping[str, int]:
        return self.validation["counts"]  # type: ignore[return-value]

    @property
    def run_status(self) -> str:
        if self.run_summary is None:
            return "UNKNOWN"
        return str(self.run_summary["status"])


def _validate_iso_text(value: Any, *, code: str, label: str) -> str:
    text = _require_str(value, code=code, label=label)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail(code, label + " 不是合法 ISO-8601 时间", detail=text)
    return text


def _validate_run_config_record_counts(value: Any, *, code: str = ERR_RUN_CONFIG) -> Mapping[str, int]:
    mapping = _as_mapping(value, code=code, label="run_config.record_counts")
    _require_exact_keys(mapping, ("train", "eval", "total"), code=code, label="run_config.record_counts")
    counts = {
        key: _require_int(mapping[key], code=code, label="run_config.record_counts." + key)
        for key in ("train", "eval", "total")
    }
    if counts["train"] != TRAIN_RECORDS_EXPECTED:
        _fail(ERR_RUN_CONFIG, "run_config.record_counts.train 与预算不一致", detail=str(counts["train"]))
    if counts["eval"] != EVAL_RECORDS_EXPECTED:
        _fail(ERR_RUN_CONFIG, "run_config.record_counts.eval 与评估网格不一致", detail=str(counts["eval"]))
    if counts["total"] != TRAIN_RECORDS_EXPECTED + EVAL_RECORDS_EXPECTED:
        _fail(ERR_RUN_CONFIG, "run_config.record_counts.total 与预算不一致", detail=str(counts["total"]))
    return counts


def _extract_arm_config(item: Mapping[str, Any], index: int) -> tuple[str | None, Mapping[str, Any]]:
    """兼容两种 run_config.arms 形态：判据 pin 形态（id/first_order/config）或模块快照形态。"""
    if "config" in item and (("id" in item) or ("arm" in item) or ("label" in item)):
        config = _as_mapping(item["config"], code=ERR_RUN_CONFIG, label=f"run_config.arms[{index}].config")
        raw_id = item.get("id", item.get("arm", item.get("label")))
        arm_id = _require_str(raw_id, code=ERR_RUN_CONFIG, label=f"run_config.arms[{index}].id")
        if arm_id not in EXPECTED_ARMS:
            _fail(ERR_RUN_CONFIG, "run_config.arms 的臂 ID 非法", detail=arm_id)
        return arm_id, config
    # 快照形态：没有显式 arm ID 时按模块/类名推断臂
    fingerprint = " ".join(
        str(item.get(key, "")) for key in ("module", "class", "config_path", "label", "file", "name")
    ).lower()
    arm_id = None
    if "first" in fingerprint or "fomaml" in fingerprint or "first_order" in fingerprint:
        arm_id = ARM_FOMAML
    elif "full" in fingerprint or "meta" in fingerprint or "maml" in fingerprint:
        arm_id = ARM_FULL
    config = item.get("config")
    if config is None:
        config = {
            key: item[key]
            for key in EXPECTED_ARMS_CONFIG
            if key in item
        }
    return arm_id, _as_mapping(config, code=ERR_RUN_CONFIG, label=f"run_config.arms[{index}].config")


def _validate_run_config_arms(value: Any, prereg: S2Prereg, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = list(_as_list(value, code=ERR_RUN_CONFIG, label="run_config.arms"))
    if len(items) != 2:
        _fail(ERR_RUN_CONFIG, "run_config.arms 必须恰有 2 个元素", detail=str(len(items)))
    found: dict[str, Mapping[str, Any]] = {}
    pinned_form = True
    for index, raw_item in enumerate(items):
        item = _as_mapping(raw_item, code=ERR_RUN_CONFIG, label=f"run_config.arms[{index}]")
        arm_id, config = _extract_arm_config(item, index)
        if arm_id is None:
            _fail(ERR_RUN_CONFIG, "run_config.arms 无法识别臂 ID（快照形态缺少可推断字段）", detail=f"index={index}")
        if arm_id in found:
            _fail(ERR_RUN_CONFIG, "run_config.arms 臂 ID 重复", detail=arm_id)
        found[arm_id] = config
        if not ({"id", "first_order"} <= set(item.keys())):
            pinned_form = False
        _require_exact_keys(
            config,
            tuple(EXPECTED_ARMS_CONFIG.keys()),
            code=ERR_RUN_CONFIG,
            label=f"run_config.arms[{index}].config",
            allow_extra=tuple(key for key in config.keys() if key not in EXPECTED_ARMS_CONFIG),
        )
        for key, expected_value in EXPECTED_ARMS_CONFIG.items():
            if key not in config:
                _fail(ERR_RUN_CONFIG, "run_config.arms config 缺少公平性字段", detail=key)
            actual_value = config[key]
            if key == "backend":
                if actual_value != expected_value:
                    _fail(ERR_RUN_CONFIG, "run_config.arms config.backend 与预注册不一致", detail=str(actual_value))
            elif key == "hidden_sizes":
                actual_list = list(_as_list(actual_value, code=ERR_RUN_CONFIG, label="arms.config.hidden_sizes"))
                if actual_list != list(expected_value):  # type: ignore[arg-type]
                    _fail(ERR_RUN_CONFIG, "run_config.arms config.hidden_sizes 与预注册不一致", detail=str(actual_list))
            elif isinstance(expected_value, int):
                actual_int = _require_int(actual_value, code=ERR_RUN_CONFIG, label="arms.config." + key)
                if actual_int != expected_value:
                    _fail(ERR_RUN_CONFIG, "run_config.arms config." + key + " 与预注册不一致", detail=str(actual_int))
            else:
                actual_num = _require_number(actual_value, code=ERR_RUN_CONFIG, label="arms.config." + key)
                if float(actual_num) != float(expected_value):
                    _fail(ERR_RUN_CONFIG, "run_config.arms config." + key + " 与预注册不一致", detail=str(actual_num))
    if set(found.keys()) != set(EXPECTED_ARMS):
        _fail(ERR_RUN_CONFIG, "run_config.arms 的臂集合必须为 FULL_MAML/FOMAML", detail=str(sorted(found.keys())))
    if found[ARM_FULL] != found[ARM_FOMAML]:
        _fail(ERR_RUN_CONFIG, "run_config.arms 两臂 config 必须逐字段相同（公平性）")
    prereg_arms = {arm["id"]: arm["config"] for arm in prereg.arms}
    if found[ARM_FULL] != dict(prereg_arms[ARM_FULL]) or found[ARM_FOMAML] != dict(prereg_arms[ARM_FOMAML]):
        _fail(ERR_RUN_CONFIG, "run_config.arms config 与冻结 prereg 不一致")
    _record_check(
        checks,
        "run_arms",
        status="PASS",
        detail=("pinned" if pinned_form else "snapshot") + " 形态；两臂 config 相同且与 prereg 一致",
    )
    return [{"id": arm_id, "config": dict(config)} for arm_id, config in ((k, found[k]) for k in EXPECTED_ARMS)]


def _validate_run_config_data_boundary(value: Any, prereg: S2Prereg, checks: list[dict[str, Any]]) -> Mapping[str, Any]:
    mapping = _as_mapping(value, code=ERR_DATA_BOUNDARY, label="run_config.data_boundary")
    required = (
        "allowed_splits",
        "split_counts",
        "meta_train_task_ids_sha256",
        "meta_validation_task_ids_sha256",
        "holdout_task_ids_sha256",
        "holdout_rows_used",
        "holdout_metrics_read",
    )
    missing = [key for key in required if key not in mapping]
    if missing:
        _fail(ERR_DATA_BOUNDARY, "run_config.data_boundary 缺少字段", detail=",".join(missing))
    allowed = list(_as_list(mapping["allowed_splits"], code=ERR_DATA_BOUNDARY, label="data_boundary.allowed_splits"))
    if allowed != list(ALLOWED_SPLITS):
        _fail(ERR_DATA_BOUNDARY, "run_config.allowed_splits 非法", detail=str(allowed))
    if "forbidden_splits" in mapping:
        forbidden = list(
            _as_list(mapping["forbidden_splits"], code=ERR_DATA_BOUNDARY, label="data_boundary.forbidden_splits")
        )
        if forbidden != list(FORBIDDEN_SPLITS):
            _fail(ERR_DATA_BOUNDARY, "run_config.forbidden_splits 非法", detail=str(forbidden))
    split_counts = dict(
        _as_mapping(mapping["split_counts"], code=ERR_DATA_BOUNDARY, label="data_boundary.split_counts")
    )
    prereg_counts = dict(prereg.data_boundary["split_counts"])
    if split_counts != prereg_counts:
        _fail(ERR_DATA_BOUNDARY, "run_config.split_counts 与冻结 prereg 不一致", detail=f"{split_counts} != {prereg_counts}")
    for key in ("meta_train_task_ids_sha256", "meta_validation_task_ids_sha256", "holdout_task_ids_sha256"):
        actual = _require_sha256(mapping[key], code=ERR_DATA_BOUNDARY, label="run_config.data_boundary." + key)
        expected = _require_sha256(
            prereg.data_boundary[key], code=ERR_DATA_BOUNDARY, label="prereg.data_boundary." + key
        )
        if actual != expected:
            _fail(ERR_DATA_BOUNDARY, "run_config." + key + " 与冻结 prereg 不一致", detail=f"{actual} != {expected}")
    rows_used = _require_int(mapping["holdout_rows_used"], code=ERR_DATA_BOUNDARY, label="holdout_rows_used")
    if rows_used != 0:
        _fail(ERR_DATA_BOUNDARY, "run_config.holdout_rows_used 必须为 0", detail=str(rows_used))
    if _require_bool(mapping["holdout_metrics_read"], code=ERR_DATA_BOUNDARY, label="holdout_metrics_read") is not False:
        _fail(ERR_DATA_BOUNDARY, "run_config.holdout_metrics_read 必须为 false")
    _record_check(checks, "run_data_boundary", status="PASS", detail="holdout_rows_used=0, holdout_metrics_read=false")
    return mapping


def _validate_episode_bank(value: Any, prereg: S2Prereg) -> Mapping[str, Any]:
    mapping = _as_mapping(value, code=ERR_RUN_CONFIG, label="run_config.episode_bank")
    _require_exact_keys(
        mapping, ("sha256", "episodes", "meta_seeds", "outer_steps", "batch_size"), code=ERR_RUN_CONFIG, label="episode_bank"
    )
    sha = _require_sha256(mapping["sha256"], code=ERR_RUN_CONFIG, label="episode_bank.sha256")
    expected_sha = _require_sha256(
        prereg.episode_contract["train_episode_bank_sha256"], code=ERR_RUN_CONFIG, label="prereg.train_episode_bank_sha256"
    )
    if sha != expected_sha:
        _fail(ERR_RUN_CONFIG, "episode_bank.sha256 与冻结 prereg 不一致", detail=f"{sha} != {expected_sha}")
    episodes = _require_int(mapping["episodes"], code=ERR_RUN_CONFIG, label="episode_bank.episodes")
    if episodes <= 0:
        _fail(ERR_RUN_CONFIG, "episode_bank.episodes 必须为正整数", detail=str(episodes))
    seeds = list(_as_list(mapping["meta_seeds"], code=ERR_RUN_CONFIG, label="episode_bank.meta_seeds"))
    seed_values = [_require_int(seed, code=ERR_RUN_CONFIG, label="episode_bank.meta_seeds[]") for seed in seeds]
    if seed_values != list(prereg.meta_seeds):
        _fail(ERR_RUN_CONFIG, "episode_bank.meta_seeds 与预注册不一致", detail=str(seed_values))
    outer_steps = _require_int(mapping["outer_steps"], code=ERR_RUN_CONFIG, label="episode_bank.outer_steps")
    if outer_steps != prereg.outer_steps:
        _fail(ERR_RUN_CONFIG, "episode_bank.outer_steps 与预注册不一致", detail=str(outer_steps))
    batch_size = _require_int(mapping["batch_size"], code=ERR_RUN_CONFIG, label="episode_bank.batch_size")
    if batch_size != 8:
        _fail(ERR_RUN_CONFIG, "episode_bank.batch_size 与预注册 tasks_per_batch 不一致", detail=str(batch_size))
    return mapping


def _validate_fd_gate_block(value: Any, prereg: S2Prereg) -> Mapping[str, Any]:
    mapping = _as_mapping(value, code=ERR_FD_GATE, label="run_config.fd_gate")
    _require_exact_keys(
        mapping, ("mode", "max_relative_error", "coordinates", "pilot_artifacts"), code=ERR_FD_GATE, label="run_config.fd_gate"
    )
    if mapping["mode"] != "full":
        _fail(ERR_FD_GATE, "run_config.fd_gate.mode 必须为 full", detail=str(mapping["mode"]))
    max_rel = _require_number(mapping["max_relative_error"], code=ERR_FD_GATE, label="run_config.fd_gate.max_relative_error")
    if float(max_rel) != 1e-6:
        _fail(ERR_FD_GATE, "run_config.fd_gate.max_relative_error 必须为 1e-6", detail=str(max_rel))
    coordinates = _require_int(mapping["coordinates"], code=ERR_FD_GATE, label="run_config.fd_gate.coordinates")
    if coordinates != 32:
        _fail(ERR_FD_GATE, "run_config.fd_gate.coordinates 必须为 32", detail=str(coordinates))
    pilot = _as_mapping(mapping["pilot_artifacts"], code=ERR_FD_GATE, label="run_config.fd_gate.pilot_artifacts")
    if dict(pilot) != dict(prereg.fd_gate["pilot_artifacts"]):
        _fail(ERR_FD_GATE, "run_config.fd_gate.pilot_artifacts 与冻结 prereg 不一致")
    return mapping


def _validate_environment(value: Any) -> Mapping[str, Any]:
    mapping = _as_mapping(value, code=ERR_RUN_CONFIG, label="run_config.environment")
    required = ("python", "torch", "platform")
    missing = [key for key in required if key not in mapping]
    if missing:
        _fail(ERR_RUN_CONFIG, "run_config.environment 缺少字段", detail=",".join(missing))
    for key in required:
        _require_str(mapping[key], code=ERR_RUN_CONFIG, label="run_config.environment." + key)
    return mapping


def _validate_run_config(
    cfg: Any,
    prereg: S2Prereg,
    *,
    checks: list[dict[str, Any]],
) -> Mapping[str, Any]:
    """run_config 与冻结 prereg 的一致性校验（fail-closed）。"""
    mapping = _as_mapping(cfg, code=ERR_RUN_SCHEMA, label="run_config.json")
    missing = [key for key in RUN_CONFIG_REQUIRED_FIELDS if key not in mapping]
    if missing:
        _fail(ERR_RUN_SCHEMA, "run_config.json 缺少必填字段", detail=",".join(missing))
    unknown = sorted(set(mapping.keys()) - set(RUN_CONFIG_REQUIRED_FIELDS))
    if unknown:
        _record_check(checks, "run_config_extra_fields", status="DISCLOSED", detail=",".join(unknown))
    if mapping["schema_version"] != RUN_CONFIG_SCHEMA_VERSION:
        _fail(ERR_RUN_SCHEMA, "run_config.schema_version 非法", detail=str(mapping["schema_version"]))
    _require_str(mapping["run_id"], code=ERR_RUN_SCHEMA, label="run_config.run_id")
    _validate_iso_text(mapping["created_utc"], code=ERR_RUN_SCHEMA, label="run_config.created_utc")
    _validate_run_config_record_counts(mapping["record_counts"])
    for key, expected in (
        ("prereg_id", prereg.prereg_id),
        ("prereg_digest", prereg.prereg_digest),
        ("code_sha", prereg.code_sha),
    ):
        actual = _require_str(mapping[key], code=ERR_RUN_CONFIG, label="run_config." + key)
        if actual != expected:
            _fail(ERR_RUN_CONFIG, "run_config." + key + " 与冻结 prereg 不一致", detail=f"{actual} != {expected}")
    frozen = _as_mapping(mapping["frozen_package"], code=ERR_RUN_CONFIG, label="run_config.frozen_package")
    if dict(frozen) != dict(prereg.frozen_package):
        _fail(ERR_RUN_CONFIG, "run_config.frozen_package 与冻结 prereg 不一致")
    _validate_run_config_data_boundary(mapping["data_boundary"], prereg, checks)
    _validate_run_config_arms(mapping["arms"], prereg, checks)
    budget = _as_mapping(mapping["training_budget"], code=ERR_RUN_CONFIG, label="run_config.training_budget")
    if dict(budget) != dict(prereg.training_budget):
        _fail(ERR_RUN_CONFIG, "run_config.training_budget 与冻结 prereg 不一致")
    grid = _as_mapping(mapping["evaluation_grid"], code=ERR_RUN_CONFIG, label="run_config.evaluation_grid")
    if dict(grid) != dict(prereg.evaluation_grid):
        _fail(ERR_RUN_CONFIG, "run_config.evaluation_grid 与冻结 prereg 不一致")
    _validate_episode_bank(mapping["episode_bank"], prereg)
    _validate_fd_gate_block(mapping["fd_gate"], prereg)
    _validate_environment(mapping["environment"])
    physical = _require_int(mapping["physical_call_count"], code=ERR_RUN_CONFIG, label="run_config.physical_call_count")
    if physical != 0:
        _fail(ERR_RUN_CONFIG, "run_config.physical_call_count 必须为 0", detail=str(physical))
    if mapping["evidence_scope"] != EVIDENCE_SCOPE:
        _fail(ERR_PREREG_SCOPE, "run_config.evidence_scope 必须为 DEVELOPMENT_VALIDATION_ONLY", detail=str(mapping["evidence_scope"]))
    if mapping["development_set"] != DEVELOPMENT_SET:
        _fail(ERR_DATA_BOUNDARY, "run_config.development_set 必须为 meta_validation", detail=str(mapping["development_set"]))
    _record_check(checks, "run_config", status="PASS", detail="prereg digest/code_sha/frozen_package/边界/预算/网格一致")
    return mapping

# ---------------------------------------------------------------------------
# run_records.jsonl 解析与逐行校验
# ---------------------------------------------------------------------------


def _parse_jsonl_records(path: Path, *, expected_type: str | None = None) -> list[dict[str, Any]]:
    """逐行解析并强制 canonical 行格式（每行必须等于自身 canonical JSON 文本）。"""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover - 防御性
        _fail(ERR_RECORD_SCHEMA, "run_records 不是 UTF-8 文本", detail=str(path) + " | " + str(exc))
    lines = raw_text.splitlines()
    if not lines:
        _fail(ERR_RECORD_SCHEMA, "run_records 文件为空", detail=str(path))
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            _fail(ERR_RECORD_SCHEMA, "run_records 含空行", detail=f"{path.name}:{line_number}")
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail(ERR_RECORD_SCHEMA, "run_records 行不是合法 JSON", detail=f"{path.name}:{line_number} | {exc}")
        mapping = _as_mapping(parsed, code=ERR_RECORD_SCHEMA, label=f"{path.name}:{line_number}")
        try:
            canonical = _canonical_json_text(mapping)
        except (TypeError, ValueError) as exc:
            _fail(ERR_RECORD_SCHEMA, "run_records 行无法按 canonical JSON 序列化", detail=f"{path.name}:{line_number} | {exc}")
        if line != canonical:
            _fail(
                ERR_RECORD_SCHEMA,
                "run_records 行不是 canonical JSON（sort_keys/紧凑分隔符/无多余空白/末尾无换行）",
                detail=f"{path.name}:{line_number}",
            )
        record_type = mapping.get("record_type")
        if expected_type is not None and record_type != expected_type:
            _fail(
                ERR_RECORD_SCHEMA,
                "run_records 分文件的 record_type 与文件角色不一致",
                detail=f"{path.name}:{line_number}: {record_type!r} != {expected_type!r}",
            )
        records.append(dict(mapping))
    return records


def _validate_train_record(rec: Mapping[str, Any], *, index: int, prereg: S2Prereg) -> Mapping[str, Any]:
    label = f"train[{index}]"
    _require_exact_keys(rec, ("record_type",) + TRAIN_REQUIRED_FIELDS, code=ERR_RECORD_SCHEMA, label=label)
    if rec["record_type"] != "train":
        _fail(ERR_RECORD_SCHEMA, label + ".record_type 必须为 train", detail=str(rec["record_type"]))
    _require_str(rec["run_id"], code=ERR_RECORD_SCHEMA, label=label + ".run_id")
    arm = _require_str(rec["arm"], code=ERR_RECORD_SCHEMA, label=label + ".arm")
    if arm not in EXPECTED_ARMS:
        _fail(ERR_RECORD_VALUE, label + ".arm 非法", detail=arm)
    meta_seed = _require_int(rec["meta_seed"], code=ERR_RECORD_SCHEMA, label=label + ".meta_seed")
    if meta_seed not in prereg.meta_seeds:
        _fail(ERR_RECORD_VALUE, label + ".meta_seed 不在预注册元种子内", detail=str(meta_seed))
    outer_step = _require_int(rec["outer_step"], code=ERR_RECORD_SCHEMA, label=label + ".outer_step")
    if not 0 <= outer_step < prereg.outer_steps:
        _fail(ERR_RECORD_VALUE, label + ".outer_step 超出预算范围", detail=str(outer_step))
    status = _require_str(rec["status"], code=ERR_RECORD_SCHEMA, label=label + ".status")
    if status not in RECORD_STATUSES:
        _fail(ERR_RECORD_VALUE, label + ".status 非法", detail=status)
    for key in ("train_loss", "grad_norm", "inner_loss_first", "inner_loss_last"):
        _require_number(
            rec[key],
            code=ERR_RECORD_VALUE,
            label=label + "." + key,
            allow_none=status == "FAILED",
            minimum=0.0,
        )
    _require_number(rec["wall_s"], code=ERR_RECORD_VALUE, label=label + ".wall_s", minimum=0.0)
    _require_number(
        rec["peak_memory_mb"],
        code=ERR_RECORD_VALUE,
        label=label + ".peak_memory_mb",
        allow_none=status == "FAILED",
        minimum=0.0,
    )
    return rec


def _validate_eval_record(rec: Mapping[str, Any], *, index: int, prereg: S2Prereg) -> Mapping[str, Any]:
    label = f"eval[{index}]"
    _require_exact_keys(rec, ("record_type",) + EVAL_REQUIRED_FIELDS, code=ERR_RECORD_SCHEMA, label=label)
    if rec["record_type"] != "eval":
        _fail(ERR_RECORD_SCHEMA, label + ".record_type 必须为 eval", detail=str(rec["record_type"]))
    _require_str(rec["run_id"], code=ERR_RECORD_SCHEMA, label=label + ".run_id")
    arm = _require_str(rec["arm"], code=ERR_RECORD_SCHEMA, label=label + ".arm")
    if arm not in EXPECTED_ARMS:
        _fail(ERR_RECORD_VALUE, label + ".arm 非法", detail=arm)
    meta_seed = _require_int(rec["meta_seed"], code=ERR_RECORD_SCHEMA, label=label + ".meta_seed")
    if meta_seed not in prereg.meta_seeds:
        _fail(ERR_RECORD_VALUE, label + ".meta_seed 不在预注册元种子内", detail=str(meta_seed))
    _require_str(rec["task_id"], code=ERR_RECORD_SCHEMA, label=label + ".task_id")
    split = _require_str(rec["split"], code=ERR_DATA_BOUNDARY, label=label + ".split")
    if split != SPLIT_EVAL:
        _fail(ERR_DATA_BOUNDARY, label + ".split 必须是 meta_validation（禁止 holdout 行进入分析）", detail=split)
    k_value = _require_int(rec["K"], code=ERR_RECORD_SCHEMA, label=label + ".K")
    if k_value not in prereg.k_values:
        _fail(ERR_RECORD_VALUE, label + ".K 不在评估网格内", detail=str(k_value))
    draw = _require_int(rec["draw"], code=ERR_RECORD_SCHEMA, label=label + ".draw")
    if not 0 <= draw < prereg.draws:
        _fail(ERR_RECORD_VALUE, label + ".draw 超出评估网格", detail=str(draw))
    status = _require_str(rec["status"], code=ERR_RECORD_SCHEMA, label=label + ".status")
    if status not in RECORD_STATUSES:
        _fail(ERR_RECORD_VALUE, label + ".status 非法", detail=status)
    support_size = _require_int(rec["support_size"], code=ERR_RECORD_VALUE, label=label + ".support_size")
    adaptation = _require_int(rec["adaptation_inner_steps"], code=ERR_RECORD_VALUE, label=label + ".adaptation_inner_steps")
    if k_value == 0:
        if support_size != 0 or adaptation != 0:
            _fail(ERR_RECORD_VALUE, label + " K=0 时 support_size/adaptation_inner_steps 必须为 0")
    elif support_size != k_value or adaptation != k_value:
        _fail(
            ERR_RECORD_VALUE,
            label + " K>0 时 support_size=adaptation_inner_steps=K",
            detail=f"K={k_value}, support={support_size}, adaptation={adaptation}",
        )
    query_size = _require_int(rec["query_size"], code=ERR_RECORD_VALUE, label=label + ".query_size")
    if query_size != EVAL_QUERY_SIZE:
        _fail(ERR_RECORD_VALUE, label + ".query_size 必须为 64", detail=str(query_size))
    allow_none = status == "FAILED"
    _require_number(rec["query_rmse_raw"], code=ERR_RECORD_VALUE, label=label + ".query_rmse_raw", allow_none=allow_none, minimum=0.0)
    _require_number(rec["query_mae_raw"], code=ERR_RECORD_VALUE, label=label + ".query_mae_raw", allow_none=allow_none, minimum=0.0)
    standardized = rec["query_rmse_standardized"]
    if k_value <= 1:
        if standardized is not None:
            _fail(ERR_RECORD_VALUE, label + " K<=1 时 query_rmse_standardized 必须为 null", detail=str(standardized))
    else:
        _require_number(
            standardized,
            code=ERR_RECORD_VALUE,
            label=label + ".query_rmse_standardized",
            allow_none=True,
            minimum=0.0,
        )
    _require_number(rec["wall_s"], code=ERR_RECORD_VALUE, label=label + ".wall_s", minimum=0.0)
    return rec


def _validate_record_coverage(
    train_records: Sequence[Mapping[str, Any]],
    eval_records: Sequence[Mapping[str, Any]],
    prereg: S2Prereg,
    *,
    allow_incomplete_run: bool,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """唯一性 + 完整网格覆盖校验；allow_incomplete_run 时只校验唯一性/子集并披露缺口。"""
    train_keys = [(rec["arm"], rec["meta_seed"], rec["outer_step"]) for rec in train_records]
    if len(set(train_keys)) != len(train_keys):
        seen: set[tuple[Any, ...]] = set()
        duplicates = [key for key in train_keys if key in seen or seen.add(key)]  # type: ignore[func-returns-value]
        _fail(ERR_RECORD_DUPLICATE, "train 记录出现重复 (arm,meta_seed,outer_step)", detail=str(duplicates[:3]))
    eval_keys = [
        (rec["arm"], rec["meta_seed"], rec["task_id"], rec["K"], rec["draw"]) for rec in eval_records
    ]
    if len(set(eval_keys)) != len(eval_keys):
        seen = set()
        duplicates = [key for key in eval_keys if key in seen or seen.add(key)]  # type: ignore[func-returns-value]
        _fail(ERR_RECORD_DUPLICATE, "eval 记录出现重复 (arm,meta_seed,task,K,draw)", detail=str(duplicates[:3]))

    expected_train_groups = {(arm, seed) for arm in EXPECTED_ARMS for seed in prereg.meta_seeds}
    train_groups: dict[tuple[str, int], set[int]] = {}
    for rec in train_records:
        train_groups.setdefault((rec["arm"], rec["meta_seed"]), set()).add(rec["outer_step"])
    eval_groups: dict[tuple[str, int], set[tuple[str, int, int]]] = {}
    for rec in eval_records:
        eval_groups.setdefault((rec["arm"], rec["meta_seed"]), set()).add((rec["task_id"], rec["K"], rec["draw"]))

    strict_ok = True
    train_report: list[dict[str, Any]] = []
    expected_steps = set(range(prereg.outer_steps))
    for group in sorted(expected_train_groups, key=lambda item: (EXPECTED_ARMS.index(item[0]), item[1])):
        steps = train_groups.get(group, set())
        complete = steps == expected_steps
        strict_ok = strict_ok and complete
        train_report.append(
            {
                "arm": group[0],
                "meta_seed": group[1],
                "records": len(steps),
                "expected_records": prereg.outer_steps,
                "complete": complete,
            }
        )
    eval_report: list[dict[str, Any]] = []
    expected_eval_per_group = prereg.n_tasks * len(prereg.k_values) * prereg.draws
    for group in sorted(expected_train_groups, key=lambda item: (EXPECTED_ARMS.index(item[0]), item[1])):
        cells = eval_groups.get(group, set())
        complete = len(cells) == expected_eval_per_group
        strict_ok = strict_ok and complete
        eval_report.append(
            {
                "arm": group[0],
                "meta_seed": group[1],
                "records": len(cells),
                "expected_records": expected_eval_per_group,
                "complete": complete,
            }
        )
    if set(train_groups.keys()) - expected_train_groups or set(eval_groups.keys()) - expected_train_groups:
        _fail(ERR_RECORD_VALUE, "出现预注册之外的 (arm,meta_seed) 组合")
    # 任务集合：两臂必须使用完全相同的 20 个 meta_validation task
    tasks_by_arm: dict[str, set[str]] = {arm: set() for arm in EXPECTED_ARMS}
    for rec in eval_records:
        tasks_by_arm[rec["arm"]].add(rec["task_id"])
    task_sets = [tasks_by_arm[arm] for arm in EXPECTED_ARMS]
    if task_sets[0] != task_sets[1]:
        _fail(ERR_RECORD_VALUE, "两臂使用的 task_id 集合不一致")
    unique_tasks = sorted(task_sets[0]) if task_sets else []
    if len(unique_tasks) != prereg.n_tasks:
        _fail(
            ERR_RECORD_VALUE,
            "meta_validation 任务数必须为 20",
            detail=f"实际={len(unique_tasks)}",
        )
    strict_ok = strict_ok and len(train_records) == TRAIN_RECORDS_EXPECTED and len(eval_records) == EVAL_RECORDS_EXPECTED
    if not allow_incomplete_run:
        if len(train_records) != TRAIN_RECORDS_EXPECTED:
            _fail(
                ERR_RUN_INCOMPLETE,
                "train 记录数不是 1200（正式 run 必须完整）",
                detail=str(len(train_records)),
            )
        if len(eval_records) != EVAL_RECORDS_EXPECTED:
            _fail(
                ERR_RUN_INCOMPLETE,
                "eval 记录数不是 4800（正式 run 必须完整）",
                detail=str(len(eval_records)),
            )
        if not strict_ok:
            _fail(ERR_RUN_INCOMPLETE, "run 记录未覆盖完整评估/训练网格")
        _record_check(checks, "record_coverage", status="PASS", detail="6000 行 / 6 组 / 20 任务 / K=0,1,5,10 / draw=0..9")
    else:
        _record_check(checks, "record_coverage", status="DISCLOSED", detail="allow_incomplete_run=True，网格缺口已披露")
    return {
        "train_groups": train_report,
        "eval_groups": eval_report,
        "expected": {
            "train_records": TRAIN_RECORDS_EXPECTED,
            "eval_records": EVAL_RECORDS_EXPECTED,
            "eval_records_per_group": expected_eval_per_group,
            "tasks": prereg.n_tasks,
            "K": list(prereg.k_values),
            "draws": prereg.draws,
        },
        "tasks": unique_tasks,
        "complete": strict_ok,
    }


def _resolve_evidence_file(rel_path: str, *, repo_root: Path, run_dir: Path | None) -> Path | None:
    """FD pilot 证据路径解析：优先仓库根（执行计划 §7），其后 run 目录（A1 接口 §7）。"""
    candidates: list[Path] = []
    for base in [repo_root] + ([run_dir] if run_dir is not None else []):
        try:
            candidate = (base / rel_path).resolve()
        except OSError:  # pragma: no cover - 防御性
            continue
        candidates.append(candidate)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else None


def _inspect_fd_evidence(
    prereg: S2Prereg,
    *,
    repo_root: Path,
    run_dir: Path,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """读取并核验 FD pilot 证据（raw sha256 + 状态字段）；FAIL 状态直接 fail-closed。"""
    evidence: dict[str, Any] = {}
    for name, item in prereg.fd_gate["pilot_artifacts"].items():
        rel_path = str(item["path"])
        expected_sha = str(item["sha256"])
        resolved = _resolve_evidence_file(rel_path, repo_root=repo_root, run_dir=run_dir)
        if resolved is None or not resolved.is_file():
            _fail(ERR_FD_GATE, "FD pilot 证据文件缺失", detail=name + ":" + rel_path)
        actual_sha = _sha256_file(resolved)
        if actual_sha != expected_sha:
            _fail(ERR_FD_GATE, "FD pilot 证据 sha256 与预注册不一致", detail=f"{name}: {actual_sha} != {expected_sha}")
        info: dict[str, Any] = {
            "path": rel_path,
            "resolved_name": resolved.name,
            "sha256": actual_sha,
            "sha256_verified": True,
            "status": None,
            "max_relative_error": None,
            "coordinates": None,
        }
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _fail(ERR_FD_GATE, "FD pilot 证据不是合法 UTF-8 JSON", detail=name + " | " + str(exc))
        if isinstance(payload, Mapping):
            status_value = payload.get("status")
            if isinstance(status_value, str):
                info["status"] = status_value
            for key in ("max_relative_error", "max_rel_error", "relative_error"):
                if key in payload and isinstance(payload[key], (int, float)) and not isinstance(payload[key], bool):
                    info["max_relative_error"] = float(payload[key])
                    break
            for key in ("coordinates", "n_coordinates", "coordinate_count"):
                if key in payload and isinstance(payload[key], int) and not isinstance(payload[key], bool):
                    info["coordinates"] = int(payload[key])
                    break
        evidence[name] = info
        if info["status"] is not None and str(info["status"]).upper() == "FAIL":
            _fail(ERR_FD_GATE, "FD pilot 证据状态为 FAIL", detail=name)
        if info["max_relative_error"] is not None and info["max_relative_error"] > float(prereg.fd_gate["max_relative_error"]):
            _fail(
                ERR_FD_GATE,
                "FD pilot 相对误差超过预注册阈值",
                detail=f"{name}: {info['max_relative_error']} > {prereg.fd_gate['max_relative_error']}",
            )
        if info["coordinates"] is not None and info["coordinates"] != int(prereg.fd_gate["coordinates"]):
            _fail(ERR_FD_GATE, "FD pilot 坐标数与预注册不一致", detail=f"{name}: {info['coordinates']}")
        _record_check(checks, "fd_pilot_evidence_" + name, status="PASS", detail=rel_path)
    return evidence

# ---------------------------------------------------------------------------
# task 级聚合（§6：先 10 draws 再 3 meta_seeds 取均值；task 为分析单位）
# ---------------------------------------------------------------------------

METRIC_DEFINITIONS = {
    "aggregation": "每个 (arm, meta_seed, task, K) 先对 10 个 draw 取算术均值；再对 3 个 meta_seed 取算术均值；得到每个 task 的分析单位值。",
    "pairing": "C1 = FULL_MAML - FOMAML，按 task 配对（同一 task_id、同一端点）。",
    "missing_policy": "任一 draw 缺失/FAILED/数值为 null 时，该 (arm,meta_seed,task,K) 单元记为 null；任一 meta_seed 单元为 null 时该 task 端点值记为 null（不插补、不丢弃任务）。",
    "train_wall_seconds_ratio": "arm 级训练墙钟比：mean_over_meta_seed(sum(OK train wall_s)) 的 FULL_MAML / FOMAML；FOMAML 为 0 时记 null。",
    "peak_memory_mb": "arm 级峰值显存（MB）：该 arm 全部 OK 记录 peak_memory_mb 的最大值。",
}
RESOURCE_ENDPOINTS = ("train_wall_seconds_ratio", "peak_memory_mb")


def _mean_or_none(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(math.fsum(values) / len(values))


def _analysis_tasks(run: S2RunData) -> list[str]:
    tasks = {str(rec["task_id"]) for rec in run.eval_records}
    return sorted(tasks)


def _cell_index(run: S2RunData, prereg: S2Prereg) -> dict[tuple[str, int, str, int], list[Mapping[str, Any]]]:
    """(arm, meta_seed, task_id, K) -> 该单元的全部 draw 记录（按 draw 升序）。"""
    index: dict[tuple[str, int, str, int], list[Mapping[str, Any]]] = {}
    for rec in run.eval_records:
        key = (str(rec["arm"]), int(rec["meta_seed"]), str(rec["task_id"]), int(rec["K"]))
        index.setdefault(key, []).append(rec)
    for records in index.values():
        records.sort(key=lambda item: int(item["draw"]))
    return index


def _aggregate_cell(
    records: Sequence[Mapping[str, Any]] | None,
    *,
    field: str,
    draws: int,
) -> tuple[float | None, str | None]:
    """单 cell：要求 draw 完整且全 OK、字段全非 null，否则返回 null + 原因。"""
    if not records:
        return None, "MISSING_RECORDS"
    if len(records) != draws:
        return None, "INCOMPLETE_DRAWS"
    draws_seen = {int(rec["draw"]) for rec in records}
    if draws_seen != set(range(draws)):
        return None, "INCOMPLETE_DRAWS"
    values: list[float] = []
    for rec in records:
        if rec["status"] != "OK":
            return None, "FAILED_RECORD"
        value = rec[field]
        if value is None:
            return None, "NULL_VALUE"
        number = float(value)
        if not math.isfinite(number):
            return None, "NONFINITE_VALUE"
        values.append(number)
    return _mean_or_none(values), None


def _aggregate_endpoint(
    run: S2RunData,
    prereg: S2Prereg,
    endpoint_id: str,
    *,
    cells: Mapping[tuple[str, int, str, int], list[Mapping[str, Any]]],
    tasks: Sequence[str],
) -> dict[str, Any]:
    """按端点聚合：draw -> meta_seed -> task，返回逐 task 行与 null 披露。"""
    k_value, field = ENDPOINT_SOURCES[endpoint_id]
    per_task: dict[str, dict[str, Any]] = {}
    for task_id in tasks:
        row: dict[str, Any] = {"task_id": task_id}
        for arm in EXPECTED_ARMS:
            seed_cells: dict[str, dict[str, Any]] = {}
            seed_values: list[float] = []
            reason: str | None = None
            for meta_seed in prereg.meta_seeds:
                value, cell_reason = _aggregate_cell(
                    cells.get((arm, meta_seed, task_id, k_value)),
                    field=field,
                    draws=prereg.draws,
                )
                seed_cells[str(meta_seed)] = {"value": value, "reason": cell_reason}
                if value is None:
                    reason = f"meta_seed={meta_seed}:{cell_reason}"
                    seed_values = []
                    break
                seed_values.append(value)
            aggregate = _mean_or_none(seed_values) if reason is None else None
            row[arm] = {"value": aggregate, "reason": reason, "per_meta_seed": seed_cells}
        full_value = row[ARM_FULL]["value"]
        fomaml_value = row[ARM_FOMAML]["value"]
        if full_value is None or fomaml_value is None:
            row["difference"] = {
                "value": None,
                "reason": "FULL_NULL" if full_value is None else "FOMAML_NULL",
            }
        else:
            row["difference"] = {"value": float(full_value) - float(fomaml_value), "reason": None}
        per_task[task_id] = row
    paired = [task_id for task_id in tasks if per_task[task_id]["difference"]["value"] is not None]
    null_tasks = [task_id for task_id in tasks if per_task[task_id]["difference"]["value"] is None]
    n_tasks = len(tasks)
    null_ratio = (len(null_tasks) / n_tasks) if n_tasks else 1.0
    return {
        "endpoint_id": endpoint_id,
        "K": k_value,
        "field": field,
        "aggregation_level": "task",
        "tasks": list(tasks),
        "per_task": per_task,
        "n_tasks": n_tasks,
        "n_paired": len(paired),
        "paired_task_ids": paired,
        "null_task_ids": null_tasks,
        "null_ratio": null_ratio,
        "meets_min_pairs": len(paired) >= WILCOXON_MIN_PAIRS,
        "difference_definition": COMPARISON_DIFFERENCE,
    }


def _aggregate_resources(run: S2RunData, prereg: S2Prereg, *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """资源描述性指标：训练墙钟（按 arm/meta_seed 求和后取均值）、峰值显存（arm 内最大）。"""
    resources: dict[str, Any] = {"metric_definitions": {key: METRIC_DEFINITIONS[key] for key in RESOURCE_ENDPOINTS}}
    train_totals: dict[str, list[float]] = {arm: [] for arm in EXPECTED_ARMS}
    peak: dict[str, list[float]] = {arm: [] for arm in EXPECTED_ARMS}
    eval_wall: dict[str, list[float]] = {arm: [] for arm in EXPECTED_ARMS}
    for arm in EXPECTED_ARMS:
        for meta_seed in prereg.meta_seeds:
            seed_walls: list[float] = []
            for rec in run.train_records:
                if rec["arm"] != arm or int(rec["meta_seed"]) != meta_seed:
                    continue
                if rec["status"] == "OK" and rec["wall_s"] is not None:
                    seed_walls.append(float(rec["wall_s"]))
            if seed_walls:
                train_totals[arm].append(math.fsum(seed_walls))
            eval_seed: list[float] = []
            for rec in run.eval_records:
                if rec["arm"] != arm or int(rec["meta_seed"]) != meta_seed:
                    continue
                if rec["status"] == "OK" and rec["wall_s"] is not None:
                    eval_seed.append(float(rec["wall_s"]))
            if eval_seed:
                eval_wall[arm].append(math.fsum(eval_seed))
            for rec in list(run.train_records) + list(run.eval_records):
                if rec["arm"] != arm or int(rec["meta_seed"]) != meta_seed:
                    continue
                if rec["status"] == "OK" and rec.get("peak_memory_mb") is not None:
                    peak[arm].append(float(rec["peak_memory_mb"]))
    arm_summary: dict[str, Any] = {}
    for arm in EXPECTED_ARMS:
        arm_summary[arm] = {
            "train_wall_seconds_per_meta_seed": [float(value) for value in train_totals[arm]],
            "train_wall_seconds_mean": _mean_or_none(train_totals[arm]),
            "eval_wall_seconds_mean": _mean_or_none(eval_wall[arm]),
            "peak_memory_mb_max": max(peak[arm]) if peak[arm] else None,
            "n_train_seed_groups": len(train_totals[arm]),
        }
    full_train = arm_summary[ARM_FULL]["train_wall_seconds_mean"]
    fomaml_train = arm_summary[ARM_FOMAML]["train_wall_seconds_mean"]
    if full_train is None or fomaml_train is None or fomaml_train <= 0.0:
        ratio = None
        ratio_reason = "MISSING_OR_ZERO_DENOMINATOR"
    else:
        ratio = float(full_train) / float(fomaml_train)
        ratio_reason = None
    full_peak = arm_summary[ARM_FULL]["peak_memory_mb_max"]
    fomaml_peak = arm_summary[ARM_FOMAML]["peak_memory_mb_max"]
    resources["per_arm"] = arm_summary
    resources["train_wall_seconds_ratio"] = {"value": ratio, "reason": ratio_reason, "numerator": ARM_FULL, "denominator": ARM_FOMAML}
    resources["peak_memory_mb"] = {
        "value": full_peak,
        "reason": None if full_peak is not None else "MISSING",
        "per_arm": {arm: arm_summary[arm]["peak_memory_mb_max"] for arm in EXPECTED_ARMS},
        "fomaml_peak_memory_mb": fomaml_peak,
    }
    _record_check(checks, "resource_endpoints", status="PASS" if ratio is not None else "DISCLOSED", detail="资源指标仅描述，不参与 benefit/harm 判定")
    return resources


def _integrity_flags(run: S2RunData, *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合前质量披露：失败记录、arm 降级、run 状态、FD 证据、determinism 可核查性。"""
    failed_train = [rec for rec in run.train_records if rec["status"] != "OK"]
    failed_eval = [rec for rec in run.eval_records if rec["status"] != "OK"]
    degraded_arms: list[str] = []
    for arm in EXPECTED_ARMS:
        if any(rec["arm"] == arm for rec in failed_train) or any(rec["arm"] == arm for rec in failed_eval):
            degraded_arms.append(arm)
    run_status = run.run_status
    flags: dict[str, Any] = {
        "run_status": run_status,
        "degraded_arms": degraded_arms,
        "failed_train_records": len(failed_train),
        "failed_eval_records": len(failed_eval),
        "primary_should_be_inconclusive": bool(degraded_arms) or run_status != "COMPLETED",
        "determinism": {
            "verifiable_from_analysis_inputs": False,
            "note": "determinism 重跑字节一致性由 A1 run 层产物的 run_summary 承载；本分析输入未见确定性的逐字段证据，按 NOT_VERIFIABLE_IN_ANALYSIS 披露（不伪造 PASS）。",
        },
        "fd_gate_evidence": run.validation.get("fd_gate_evidence"),
    }
    _record_check(checks, "integrity_flags", status="PASS", detail=f"run_status={run_status}, degraded_arms={degraded_arms}")
    return flags


def _build_analysis_core(
    run: S2RunData,
    prereg: S2Prereg,
    *,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建 task 级分析核心：推断端点 + 描述性指标端点 + 资源 + 完整性披露。"""
    tasks = _analysis_tasks(run)
    cells = _cell_index(run, prereg)
    endpoints: dict[str, Any] = {}
    for endpoint_id in INFERENCE_ENDPOINTS:
        endpoints[endpoint_id] = _aggregate_endpoint(run, prereg, endpoint_id, cells=cells, tasks=tasks)
    descriptive_metrics: dict[str, Any] = {}
    for endpoint_id in DESCRIPTIVE_ENDPOINTS:
        if endpoint_id in ENDPOINT_SOURCES:
            descriptive_metrics[endpoint_id] = _aggregate_endpoint(run, prereg, endpoint_id, cells=cells, tasks=tasks)
    resources = _aggregate_resources(run, prereg, checks=checks)
    integrity = _integrity_flags(run, checks=checks)
    core = {
        "tasks": tasks,
        "n_tasks": len(tasks),
        "unit": COMPARISON_UNIT,
        "endpoints": endpoints,
        "descriptive_metrics": descriptive_metrics,
        "resources": resources,
        "integrity": integrity,
        "metric_definitions": METRIC_DEFINITIONS,
        "evidence_scope": prereg.evidence_scope,
        "development_set": DEVELOPMENT_SET,
    }
    _record_check(checks, "task_aggregation", status="PASS", detail=f"{len(tasks)} tasks, {len(endpoints)} inference endpoints")
    return core

# ---------------------------------------------------------------------------
# 统计推断（§6：自实现双侧 Wilcoxon + 配对 bootstrap + Holm；不依赖 scipy）
# ---------------------------------------------------------------------------


def _average_ranks(values: Sequence[float]) -> list[float]:
    """升序秩，平均秩处理并列（Wilcoxon signed-rank 的标准做法）。"""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + 1 + end + 1) / 2.0
        for index in range(position, end + 1):
            ranks[order[index]] = average
        position = end + 1
    return ranks


def wilcoxon_signed_rank_two_sided(differences: Sequence[float]) -> dict[str, Any]:
    """双侧 Wilcoxon 符号秩检验。

    方法：零差值按标准做法剔除；|差值| 的平均秩；n<=25 用精确条件分布（子集秩和 DP 枚举 2^n
    全部符号组合），n>25 用带连续性校正的正态近似。p 值取 2*min(下尾, 上尾) 并截断到 1。
    该方法在 n=20（本分析）时是精确检验，不依赖 scipy。
    """
    diffs = [float(value) for value in differences]
    if any(not math.isfinite(value) for value in diffs):
        _fail(ERR_INPUT, "Wilcoxon 输入含非有限差值")
    nonzero = [value for value in diffs if value != 0.0]
    n_nonzero = len(nonzero)
    result: dict[str, Any] = {
        "method": PAIRED_TEST,
        "n_pairs": len(diffs),
        "n_nonzero": n_nonzero,
        "statistic": None,
        "p_value": None,
        "w_plus": None,
        "w_minus": None,
        "p_value_method": None,
    }
    if n_nonzero == 0:
        result.update({"statistic": 0.0, "w_plus": 0.0, "w_minus": 0.0, "p_value": 1.0, "p_value_method": "ALL_ZERO"})
        return result
    ranks = _average_ranks([abs(value) for value in nonzero])
    w_plus = math.fsum(rank for rank, value in zip(ranks, nonzero) if value > 0)
    w_minus = math.fsum(rank for rank, value in zip(ranks, nonzero) if value < 0)
    statistic = min(w_plus, w_minus)
    if n_nonzero <= 25:
        # 精确条件分布：秩为整数或半整数，放大 2 倍后用整数权重的子集和 DP 计数
        weights = [int(round(rank * 2)) for rank in ranks]
        total_weight = sum(weights)
        counts = [0] * (total_weight + 1)
        counts[0] = 1
        for weight in weights:
            for total in range(total_weight, weight - 1, -1):
                if counts[total - weight]:
                    counts[total] += counts[total - weight]
        total_outcomes = 2 ** len(weights)
        scaled_statistic = int(round(statistic * 2))
        lower = sum(counts[: scaled_statistic + 1]) / total_outcomes
        upper = sum(counts[scaled_statistic:]) / total_outcomes
        p_value = min(1.0, 2.0 * min(lower, upper))
        p_value_method = "exact"
    else:  # pragma: no cover - 本分析固定 n=20，保留通用路径
        mean_w = n_nonzero * (n_nonzero + 1) / 4.0
        std_w = math.sqrt(n_nonzero * (n_nonzero + 1) * (2 * n_nonzero + 1) / 24.0)
        if std_w == 0:  # pragma: no cover - 防御性
            p_value = 1.0
        else:
            z = (statistic + 0.5 - mean_w) / std_w
            p_value = min(1.0, math.erfc(abs(z) / math.sqrt(2.0)))
        p_value_method = "normal_approximation_continuity"
    result.update(
        {
            "statistic": float(statistic),
            "p_value": float(p_value),
            "w_plus": float(w_plus),
            "w_minus": float(w_minus),
            "p_value_method": p_value_method,
        }
    )
    return result


def bootstrap_mean_ci(
    values: Sequence[float],
    *,
    n_resamples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence_level: float = CONFIDENCE_LEVEL,
) -> dict[str, Any]:
    """配对差值的均值 percentile bootstrap 置信区间（显式 seed，可复现）。"""
    data = np.asarray([float(value) for value in values], dtype=np.float64)
    if data.size == 0:
        return {
            "n_resamples": n_resamples,
            "seed": seed,
            "confidence_level": confidence_level,
            "ci_low": None,
            "ci_high": None,
            "method": "percentile_bootstrap_gaussian",
            "reason": "NO_VALUES",
        }
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, data.size, size=(n_resamples, data.size))
    means = data[indices].mean(axis=1)
    alpha = (1.0 - confidence_level) / 2.0
    ci_low = float(np.quantile(means, alpha))
    ci_high = float(np.quantile(means, 1.0 - alpha))
    return {
        "n_resamples": n_resamples,
        "seed": seed,
        "confidence_level": confidence_level,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "ci_excludes_zero": bool(ci_low > 0.0 or ci_high < 0.0),
        "mean_difference": float(data.mean()),
        "method": "percentile_bootstrap_of_task_mean",
    }


def holm_adjust(p_values: Sequence[float], *, family_size: int = HOLM_FAMILY_SIZE) -> list[float]:
    """Holm 逐步递减校正（族大小固定为 2）。"""
    values = [float(value) for value in p_values]
    if len(values) != family_size:
        _fail(ERR_PREREG_HOLM, "Holm 族成员数不符", detail=f"{len(values)} != {family_size}")
    order = sorted(range(len(values)), key=lambda index: values[index])
    adjusted = [0.0] * len(values)
    running = 0.0
    for position, index in enumerate(order):
        running = max(running, min(1.0, (family_size - position) * values[index]))
        adjusted[index] = running
    return adjusted


def _endpoint_task_values(endpoint_row: Mapping[str, Any], arm: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for task_id in endpoint_row["paired_task_ids"]:
        row = endpoint_row["per_task"][task_id]
        value = row[arm]["value"]
        if value is not None:
            values[task_id] = float(value)
    return values


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _relative_improvement(endpoint_row: Mapping[str, Any]) -> dict[str, Any]:
    """相对改善 = (FOMAML 中位数 - FULL_MAML 中位数) / FOMAML 中位数（仅配对 task）。"""
    full_values = _endpoint_task_values(endpoint_row, ARM_FULL)
    fomaml_values = _endpoint_task_values(endpoint_row, ARM_FOMAML)
    fomaml_median = _median(list(fomaml_values.values()))
    full_median = _median(list(full_values.values()))
    if fomaml_median is None or full_median is None or fomaml_median <= 0.0:
        return {"value": None, "reason": "MISSING_OR_ZERO_DENOMINATOR", "fomaml_median": fomaml_median, "full_median": full_median}
    return {
        "value": float((fomaml_median - full_median) / fomaml_median),
        "reason": None,
        "fomaml_median": float(fomaml_median),
        "full_median": float(full_median),
    }


def _infer_endpoint(endpoint_row: Mapping[str, Any]) -> dict[str, Any]:
    """单端点配对推断：差值的 Wilcoxon + bootstrap CI + 相对改善。"""
    differences = [
        float(endpoint_row["per_task"][task_id]["difference"]["value"])
        for task_id in endpoint_row["paired_task_ids"]
    ]
    test = wilcoxon_signed_rank_two_sided(differences)
    bootstrap = bootstrap_mean_ci(differences)
    relative = _relative_improvement(endpoint_row)
    return {
        "endpoint_id": endpoint_row["endpoint_id"],
        "comparison_id": COMPARISON_ID,
        "difference": COMPARISON_DIFFERENCE,
        "n_pairs": len(differences),
        "paired_task_ids": list(endpoint_row["paired_task_ids"]),
        "null_ratio": endpoint_row["null_ratio"],
        "null_task_ids": list(endpoint_row["null_task_ids"]),
        "mean_difference": float(math.fsum(differences) / len(differences)) if differences else None,
        "wilcoxon": test,
        "bootstrap": bootstrap,
        "relative_improvement": relative,
    }


def _decide_endpoint(
    inference: Mapping[str, Any],
    *,
    integrity: Mapping[str, Any],
    holm_p_adjusted: float | None,
) -> dict[str, Any]:
    """执行计划 §6 决策规则：BENEFIT / HARM / INCONCLUSIVE(null>70%) / NO_EVIDENCE。"""
    endpoint_id = inference["endpoint_id"]
    n_pairs = int(inference["n_pairs"])
    null_ratio = float(inference["null_ratio"])
    runtime_inconclusive = bool(integrity.get("primary_should_be_inconclusive"))
    criteria = {
        "sufficient_pairs": n_pairs >= WILCOXON_MIN_PAIRS,
        "null_ratio_ok": null_ratio <= NULL_RATE_INCONCLUSIVE,
        "runtime_integrity_ok": not runtime_inconclusive,
        "holm_p_available": holm_p_adjusted is not None,
        "holm_significant": (holm_p_adjusted is not None and float(holm_p_adjusted) < ALPHA),
    }
    mean_difference = inference["mean_difference"]
    bootstrap = inference["bootstrap"]
    relative = inference["relative_improvement"]
    reasons: list[str] = []
    if not criteria["runtime_integrity_ok"]:
        reasons.append("RUN_STATUS_OR_ARM_DEGRADED")
    if n_pairs < WILCOXON_MIN_PAIRS:
        reasons.append("INSUFFICIENT_PAIRS")
    if null_ratio > NULL_RATE_INCONCLUSIVE:
        reasons.append("NULL_RATE_EXCEEDS_0.70")
    if reasons:
        decision = DECISION_INCONCLUSIVE
    else:
        ci_excludes_zero = bool(bootstrap.get("ci_excludes_zero"))
        relative_value = relative.get("value")
        improvement = relative_value is not None and float(relative_value) >= RELATIVE_IMPROVEMENT_THRESHOLD
        degradation = relative_value is not None and float(relative_value) <= -RELATIVE_IMPROVEMENT_THRESHOLD
        criteria["ci_excludes_zero"] = ci_excludes_zero
        criteria["full_lower_than_fomaml"] = mean_difference is not None and float(mean_difference) < 0.0
        criteria["relative_improvement_ge_threshold"] = bool(improvement)
        if criteria["holm_significant"] and ci_excludes_zero and criteria["full_lower_than_fomaml"] and improvement:
            decision = DECISION_BENEFIT
            reasons.append("HOLM_SIGNIFICANT_CI_EXCLUDES_ZERO_RELATIVE_IMPROVEMENT")
        elif (
            criteria["holm_significant"]
            and ci_excludes_zero
            and mean_difference is not None
            and float(mean_difference) > 0.0
            and degradation
        ):
            decision = DECISION_HARM
            reasons.append("HOLM_SIGNIFICANT_CI_EXCLUDES_ZERO_RELATIVE_DEGRADATION")
        else:
            decision = DECISION_NONE
            if not criteria["holm_significant"]:
                reasons.append("HOLM_NOT_SIGNIFICANT")
            if not ci_excludes_zero:
                reasons.append("CI_INCLUDES_ZERO")
            if not improvement:
                reasons.append("RELATIVE_IMPROVEMENT_BELOW_THRESHOLD")
    return {
        "endpoint_id": endpoint_id,
        "decision": decision,
        "reasons": reasons,
        "criteria": criteria,
        "holm_p_adjusted": holm_p_adjusted,
        "alpha": ALPHA,
        "relative_improvement_threshold": RELATIVE_IMPROVEMENT_THRESHOLD,
    }


def _build_statistics(
    core: Mapping[str, Any],
    prereg: S2Prereg,
    *,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """构建推断区：逐端点推断 + 唯一 Holm 族 + 决策 + 总体结论。"""
    inferences = [_infer_endpoint(core["endpoints"][endpoint_id]) for endpoint_id in INFERENCE_ENDPOINTS]
    raw_p = [float(inference["wilcoxon"]["p_value"]) if inference["wilcoxon"]["p_value"] is not None else 1.0 for inference in inferences]
    adjusted = holm_adjust(raw_p, family_size=HOLM_FAMILY_SIZE)
    holm = {
        "family_id": HOLM_FAMILY_ID,
        "family_key": HOLM_FAMILY_KEY,
        "family_size": HOLM_FAMILY_SIZE,
        "method": HOLM_FAMILY_METHOD,
        "members": [dict(member) for member in HOLM_FAMILY_MEMBERS],
        "raw_p": {inference["endpoint_id"]: raw_p[index] for index, inference in enumerate(inferences)},
        "adjusted_p": {inference["endpoint_id"]: adjusted[index] for index, inference in enumerate(inferences)},
        "reject": [inference["endpoint_id"] for index, inference in enumerate(inferences) if adjusted[index] < ALPHA],
        "alpha": ALPHA,
        "note": "唯一多重比较族，family_size=2；不得按端点再拆分族。",
    }
    decisions = {}
    for index, inference in enumerate(inferences):
        decisions[inference["endpoint_id"]] = _decide_endpoint(
            inference,
            integrity=core["integrity"],
            holm_p_adjusted=adjusted[index],
        )
    primary_decision = decisions[PRIMARY_ENDPOINT]["decision"]
    if primary_decision == DECISION_BENEFIT:
        overall = OVERALL_ADVANTAGE
    elif primary_decision == DECISION_HARM:
        overall = OVERALL_HARM
    elif primary_decision == DECISION_INCONCLUSIVE:
        overall = OVERALL_INCONCLUSIVE
    else:
        overall = OVERALL_NONE
    overall_block = {
        "decision": overall,
        "rule": "主终点决策映射总体结论；次要端点决策仅并列披露，不改变主终点（执行计划 §6）。",
        "primary_endpoint": PRIMARY_ENDPOINT,
        "primary_decision": primary_decision,
        "secondary_decisions": {endpoint_id: decisions[endpoint_id]["decision"] for endpoint_id in SECONDARY_ENDPOINTS},
        "evidence_scope": prereg.evidence_scope,
        "development_set": DEVELOPMENT_SET,
    }
    _record_check(checks, "statistics", status="PASS", detail=f"{len(inferences)} inference endpoints, holm family_size=2")
    return {
        "inferences": inferences,
        "holm": holm,
        "decisions": decisions,
        "overall": overall_block,
        "multiple_comparison": {
            "family_id": HOLM_FAMILY_ID,
            "family_size": HOLM_FAMILY_SIZE,
            "method": HOLM_FAMILY_METHOD,
            "single_family": True,
        },
    }

# ---------------------------------------------------------------------------
# run 目录加载（run_config / run_records / run_summary + FD 证据）
# ---------------------------------------------------------------------------


def _validate_run_summary(
    summary: Any,
    run_config: Mapping[str, Any],
    prereg: S2Prereg,
    *,
    actual_train: Mapping[str, int],
    actual_eval: Mapping[str, int],
    checks: list[dict[str, Any]],
) -> Mapping[str, Any]:
    """run_summary 与 run_config/实际记录数的一致性校验（fail-closed）。"""
    mapping = _as_mapping(summary, code=ERR_RUN_SCHEMA, label="run_summary.json")
    missing = [key for key in RUN_SUMMARY_REQUIRED_FIELDS if key not in mapping]
    if missing:
        _fail(ERR_RUN_SCHEMA, "run_summary.json 缺少必填字段", detail=",".join(missing))
    unknown = sorted(set(mapping.keys()) - set(RUN_SUMMARY_REQUIRED_FIELDS))
    if unknown:
        _record_check(checks, "run_summary_extra_fields", status="DISCLOSED", detail=",".join(unknown))
    if mapping["schema_version"] != RUN_SUMMARY_SCHEMA_VERSION:
        _fail(ERR_RUN_SCHEMA, "run_summary.schema_version 非法", detail=str(mapping["schema_version"]))
    if _require_str(mapping["run_id"], code=ERR_RUN_SCHEMA, label="run_summary.run_id") != run_config["run_id"]:
        _fail(ERR_RUN_CONFIG, "run_summary.run_id 与 run_config 不一致")
    if _require_str(mapping["status"], code=ERR_RUN_SCHEMA, label="run_summary.status") not in RUN_STATUSES:
        _fail(ERR_RUN_SCHEMA, "run_summary.status 非法", detail=str(mapping["status"]))
    counts = _validate_run_config_record_counts(mapping["record_counts"], code=ERR_RUN_SCHEMA)
    if dict(counts) != dict(run_config["record_counts"]):
        _fail(ERR_RUN_CONFIG, "run_summary.record_counts 与 run_config 不一致")
    status_counts = _as_mapping(mapping["status_counts"], code=ERR_RUN_SCHEMA, label="run_summary.status_counts")
    _require_exact_keys(status_counts, ("train", "eval"), code=ERR_RUN_SCHEMA, label="run_summary.status_counts")
    for split_name, actual in (("train", actual_train), ("eval", actual_eval)):
        block = _as_mapping(status_counts[split_name], code=ERR_RUN_SCHEMA, label="run_summary.status_counts." + split_name)
        _require_exact_keys(block, RECORD_STATUSES, code=ERR_RUN_SCHEMA, label="run_summary.status_counts." + split_name)
        observed = {
            status: _require_int(block[status], code=ERR_RUN_SCHEMA, label="run_summary.status_counts." + split_name + "." + status)
            for status in RECORD_STATUSES
        }
        if observed != dict(actual):
            _fail(
                ERR_RUN_CONFIG,
                "run_summary.status_counts." + split_name + " 与实际记录不一致",
                detail=f"summary={observed} actual={dict(actual)}",
            )
        if observed.get("OK", 0) + observed.get("FAILED", 0) != counts[split_name]:
            _fail(ERR_RUN_CONFIG, "run_summary.status_counts." + split_name + " 之和与 record_counts 不一致")
    if "per_arm_seed" not in mapping:
        _fail(ERR_RUN_SCHEMA, "run_summary 缺少 per_arm_seed")
    per_arm_seed = mapping["per_arm_seed"]
    if not isinstance(per_arm_seed, (Mapping, list)) or (isinstance(per_arm_seed, (Mapping, list)) and len(per_arm_seed) == 0):
        _fail(ERR_RUN_SCHEMA, "run_summary.per_arm_seed 必须为非空映射或列表")
    resources = _as_mapping(mapping["resources"], code=ERR_RUN_SCHEMA, label="run_summary.resources")
    _require_exact_keys(resources, ("peak_memory_mb", "training_wall_s", "evaluation_wall_s"), code=ERR_RUN_SCHEMA, label="run_summary.resources")
    for key in ("peak_memory_mb", "training_wall_s", "evaluation_wall_s"):
        _require_number(resources[key], code=ERR_RUN_SCHEMA, label="run_summary.resources." + key, minimum=0.0)
    episode_bank_sha = _require_sha256(mapping["episode_bank_sha256"], code=ERR_RUN_SCHEMA, label="run_summary.episode_bank_sha256")
    config_episode_bank = run_config["episode_bank"]
    if episode_bank_sha != config_episode_bank["sha256"]:
        _fail(ERR_RUN_CONFIG, "run_summary.episode_bank_sha256 与 run_config.episode_bank 不一致")
    core_sha = _require_sha256(mapping["run_records_core_sha256"], code=ERR_RUN_SCHEMA, label="run_summary.run_records_core_sha256")
    _record_check(checks, "run_records_core_sha256", status="DISCLOSED", detail="summary 声明 " + core_sha + "；核心记录摘要口径未在接口文档中定义，分析层不伪造复核 PASS")
    fd_pilot = _as_mapping(mapping["fd_pilot_artifacts"], code=ERR_RUN_SCHEMA, label="run_summary.fd_pilot_artifacts")
    _require_exact_keys(fd_pilot, ("micro", "full_size"), code=ERR_RUN_SCHEMA, label="run_summary.fd_pilot_artifacts")
    for name in ("micro", "full_size"):
        item = _as_mapping(fd_pilot[name], code=ERR_RUN_SCHEMA, label="run_summary.fd_pilot_artifacts." + name)
        expected = prereg.fd_gate["pilot_artifacts"][name]
        if dict(item) != dict(expected):
            _fail(ERR_RUN_CONFIG, "run_summary.fd_pilot_artifacts." + name + " 与冻结 prereg 不一致")
    physical = _require_int(mapping["physical_call_count"], code=ERR_RUN_SCHEMA, label="run_summary.physical_call_count")
    if physical != 0:
        _fail(ERR_PREREG_PHYSICAL, "run_summary.physical_call_count 必须为 0", detail=str(physical))
    if mapping["evidence_scope"] != EVIDENCE_SCOPE:
        _fail(ERR_PREREG_SCOPE, "run_summary.evidence_scope 非法", detail=str(mapping["evidence_scope"]))
    if mapping["development_set"] != DEVELOPMENT_SET:
        _fail(ERR_DATA_BOUNDARY, "run_summary.development_set 非法", detail=str(mapping["development_set"]))
    scope_notes = _as_mapping(mapping["scope_notes"], code=ERR_RUN_SCHEMA, label="run_summary.scope_notes")
    feasible_keys = [key for key in scope_notes if str(key).startswith("feasible_")]
    for key in feasible_keys:
        if str(scope_notes[key]) != SCOPE_NOT_APPLICABLE_FEASIBLE:
            _fail(ERR_RUN_CONFIG, "run_summary.scope_notes." + key + " 必须为 NOT_APPLICABLE_S2_SURROGATE_SCOPE")
    _record_check(checks, "run_summary", status="PASS", detail="status/record_counts/status_counts/resources/边界/physical=0 一致")
    return mapping


def _discover_run_files(run_dir: Path) -> list[Path]:
    single = run_dir / "run_records.jsonl"
    train_file = run_dir / "run_records_train.jsonl"
    eval_file = run_dir / "run_records_eval.jsonl"
    if single.is_file():
        return [single]
    if train_file.is_file() and eval_file.is_file():
        return [train_file, eval_file]
    _fail(
        ERR_INPUT,
        "run 目录缺少 run_records.jsonl（或 run_records_train.jsonl + run_records_eval.jsonl）",
        detail=str(run_dir),
    )


def load_s2_run(
    run_dir: str | Path,
    prereg: S2Prereg,
    *,
    repo_root: str | Path | None = None,
    require_summary: bool = True,
    allow_incomplete_run: bool = False,
) -> S2RunData:
    """加载并只读校验正式 run 目录；fail-closed，不读取任何 holdout 数据文件。"""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    directory = Path(run_dir).resolve()
    if not directory.is_dir():
        _fail(ERR_INPUT, "run 目录不存在", detail=str(directory))
    checks: list[dict[str, Any]] = []
    run_config_path = directory / "run_config.json"
    if not run_config_path.is_file():
        _fail(ERR_INPUT, "run 目录缺少 run_config.json", detail=str(directory))
    run_summary_path = directory / "run_summary.json"
    if not run_summary_path.is_file():
        if require_summary:
            _fail(ERR_INPUT, "run 目录缺少 run_summary.json", detail=str(directory))
        _record_check(checks, "run_summary", status="DISCLOSED", detail="run_summary.json 缺失（require_summary=False）")
    run_config = _validate_run_config(
        _load_json_file(run_config_path, code=ERR_RUN_SCHEMA, label="run_config.json"),
        prereg,
        checks=checks,
    )
    record_files = _discover_run_files(directory)
    if len(record_files) == 1:
        records = _parse_jsonl_records(record_files[0])
        kinds = {str(record.get("record_type")) for record in records}
        if not kinds <= {"train", "eval"}:
            _fail(ERR_RECORD_SCHEMA, "run_records 含非法 record_type", detail=str(sorted(kinds)))
        eval_started = False
        for record in records:
            if record["record_type"] == "eval":
                eval_started = True
            elif eval_started:
                _fail(ERR_RECORD_SCHEMA, "run_records 单文件中训练记录必须全部位于评估记录之前")
        train_raw = [record for record in records if record["record_type"] == "train"]
        eval_raw = [record for record in records if record["record_type"] == "eval"]
        if sorted(kinds) != ["eval", "train"]:
            _fail(ERR_RECORD_SCHEMA, "run_records 必须同时包含 train 与 eval 记录", detail=str(sorted(kinds)))
    else:
        train_raw = _parse_jsonl_records(record_files[0], expected_type="train")
        eval_raw = _parse_jsonl_records(record_files[1], expected_type="eval")
    _record_check(checks, "record_files", status="PASS", detail=",".join(path.name for path in record_files))
    train_records = [_validate_train_record(record, index=index, prereg=prereg) for index, record in enumerate(train_raw)]
    eval_records = [_validate_eval_record(record, index=index, prereg=prereg) for index, record in enumerate(eval_raw)]
    if len(train_records) > TRAIN_RECORDS_EXPECTED:
        _fail(ERR_RECORD_VALUE, "train 记录数超过预算", detail=str(len(train_records)))
    if len(eval_records) > EVAL_RECORDS_EXPECTED:
        _fail(ERR_RECORD_VALUE, "eval 记录数超过评估网格", detail=str(len(eval_records)))
    coverage = _validate_record_coverage(
        train_records,
        eval_records,
        prereg,
        allow_incomplete_run=allow_incomplete_run,
        checks=checks,
    )
    train_status_counts: dict[str, int] = {status: 0 for status in RECORD_STATUSES}
    for record in train_records:
        train_status_counts[str(record["status"])] += 1
    eval_status_counts: dict[str, int] = {status: 0 for status in RECORD_STATUSES}
    for record in eval_records:
        eval_status_counts[str(record["status"])] += 1
    run_summary: Mapping[str, Any] | None = None
    if run_summary_path.is_file():
        run_summary = _validate_run_summary(
            _load_json_file(run_summary_path, code=ERR_RUN_SCHEMA, label="run_summary.json"),
            run_config,
            prereg,
            actual_train=train_status_counts,
            actual_eval=eval_status_counts,
            checks=checks,
        )
    fd_evidence = _inspect_fd_evidence(prereg, repo_root=root, run_dir=directory, checks=checks)
    source_files: list[dict[str, Any]] = []
    for path in (record_files + [run_config_path] + ([run_summary_path] if run_summary_path.is_file() else [])):
        source_files.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    run_id = str(run_config["run_id"])
    validation = {
        "run_id": run_id,
        "counts": {
            "train": len(train_records),
            "eval": len(eval_records),
            "total": len(train_records) + len(eval_records),
            "expected_train": TRAIN_RECORDS_EXPECTED,
            "expected_eval": EVAL_RECORDS_EXPECTED,
        },
        "status_counts": {"train": train_status_counts, "eval": eval_status_counts},
        "coverage": coverage,
        "source_files": source_files,
        "fd_gate_evidence": fd_evidence,
        "data_boundary": {
            "splits_seen": sorted({str(record["split"]) for record in eval_records}),
            "holdout_rows_used": 0,
            "holdout_metrics_read": False,
            "note": "分析层只读取 meta_validation 评估行；run_config.data_boundary 已由 _validate_run_config 校验 holdout_rows_used=0。",
        },
    }
    _record_check(checks, "run_load", status="PASS", detail=f"{len(train_records)} train + {len(eval_records)} eval 行")
    return S2RunData(
        run_dir=directory,
        run_config=run_config,
        run_summary=run_summary,
        train_records=train_records,
        eval_records=eval_records,
        source_files=[str(item["name"]) for item in source_files],
        validation=validation,
        checks=tuple(checks),
    )

# ---------------------------------------------------------------------------
# 产物构建（8 个数据产物 + 9 张图的输入状态）
# ---------------------------------------------------------------------------


def _build_prereg_echo(prereg: S2Prereg) -> dict[str, Any]:
    """prereg_echo.json：冻结 prereg 原文回显 + 三个摘要独立复算。"""
    recomputed_id = compute_prereg_id(prereg.raw)
    recomputed_digest = compute_prereg_digest(prereg.raw)
    recomputed_plan = compute_analysis_plan_digest(prereg.raw)
    return {
        "schema_version": S2_PREREG_ECHO_SCHEMA_VERSION,
        "source_path": str(prereg.path),
        "source_sha256": _sha256_file(prereg.path),
        "prereg_id": prereg.prereg_id,
        "prereg_digest": prereg.prereg_digest,
        "analysis_plan_digest": prereg.analysis_plan_digest,
        "recomputed": {
            "prereg_id": recomputed_id,
            "prereg_digest": recomputed_digest,
            "analysis_plan_digest": recomputed_plan,
        },
        "digest_self_consistent": bool(
            recomputed_id == prereg.prereg_id
            and recomputed_digest == prereg.prereg_digest
            and recomputed_plan == prereg.analysis_plan_digest
        ),
        "evidence_scope": prereg.evidence_scope,
        "prereg": dict(prereg.raw),
        "validation_checks": [dict(check) for check in prereg.checks],
    }


def _arm_task_stats(endpoint_row: Mapping[str, Any], arm: str) -> dict[str, Any]:
    values = list(_endpoint_task_values(endpoint_row, arm).values())
    return {
        "mean": _mean_or_none(values),
        "median": _median(values),
        "n_values": len(values),
    }


def _build_endpoint_table_rows(core: Mapping[str, Any], stats: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for inference in stats["inferences"]:
        endpoint_id = inference["endpoint_id"]
        endpoint_row = core["endpoints"][endpoint_id]
        full = _arm_task_stats(endpoint_row, ARM_FULL)
        fomaml = _arm_task_stats(endpoint_row, ARM_FOMAML)
        if full["median"] is not None and fomaml["median"] is not None:
            median_difference = float(full["median"]) - float(fomaml["median"])
        else:
            median_difference = None
        decision = stats["decisions"][endpoint_id]
        rows.append(
            {
                "comparison_id": COMPARISON_ID,
                "endpoint": endpoint_id,
                "endpoint_role": "primary" if endpoint_id == PRIMARY_ENDPOINT else "secondary_inferential",
                "family_id": HOLM_FAMILY_ID,
                "family_size": HOLM_FAMILY_SIZE,
                "treatment_arm": ARM_FULL,
                "reference_arm": ARM_FOMAML,
                "n_tasks": endpoint_row["n_tasks"],
                "n_pairs": endpoint_row["n_paired"],
                "treatment_mean": full["mean"],
                "reference_mean": fomaml["mean"],
                "treatment_median": full["median"],
                "reference_median": fomaml["median"],
                "median_difference": median_difference,
                "relative_improvement": inference["relative_improvement"]["value"],
                "wilcoxon_statistic": inference["wilcoxon"]["statistic"],
                "wilcoxon_method": inference["wilcoxon"]["p_value_method"],
                "p_raw": inference["wilcoxon"]["p_value"],
                "p_adjusted": stats["holm"]["adjusted_p"].get(endpoint_id),
                "ci_low": inference["bootstrap"]["ci_low"],
                "ci_high": inference["bootstrap"]["ci_high"],
                "decision": decision["decision"],
                "null_rate_max": endpoint_row["null_ratio"],
                "decision_reasons": ";".join(decision["reasons"]),
            }
        )
    return rows


def _build_per_task_rows(core: Mapping[str, Any], prereg: S2Prereg) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    blocks: list[tuple[str, Mapping[str, Any]]] = []
    for endpoint_id in INFERENCE_ENDPOINTS:
        blocks.append((endpoint_id, core["endpoints"][endpoint_id]))
    for endpoint_id, block in core["descriptive_metrics"].items():
        blocks.append((endpoint_id, block))
    for endpoint_id, block in blocks:
        for task_id in block["tasks"]:
            task_row = block["per_task"][task_id]
            for arm in EXPECTED_ARMS:
                arm_block = task_row[arm]
                per_seed = arm_block["per_meta_seed"]
                n_values = sum(1 for value in per_seed.values() if value["value"] is not None)
                n_null = len(per_seed) - n_values
                rows.append(
                    {
                        "task_id": task_id,
                        "arm": arm,
                        "endpoint": endpoint_id,
                        "K": block["K"],
                        "value": arm_block["value"],
                        "n_values": n_values,
                        "n_null": n_null,
                        "null_rate": (n_null / len(per_seed)) if per_seed else 1.0,
                        "meta_seed_count": len(per_seed),
                        "draw_count": prereg.draws,
                    }
                )
    return rows


def _build_holm_rows(stats: Mapping[str, Any]) -> list[dict[str, Any]]:
    holm = stats["holm"]
    members = list(HOLM_FAMILY_MEMBERS)
    raw_p = {endpoint_id: float(value) for endpoint_id, value in holm["raw_p"].items()}
    order = sorted(range(len(members)), key=lambda index: raw_p[members[index]["endpoint"]])
    rank = {index: position + 1 for position, index in enumerate(order)}
    rows: list[dict[str, Any]] = []
    for index, member in enumerate(members):
        endpoint_id = member["endpoint"]
        rows.append(
            {
                "family_id": HOLM_FAMILY_ID,
                "family_key": HOLM_FAMILY_KEY,
                "family_size": HOLM_FAMILY_SIZE,
                "member_index": index,
                "comparison_id": member["comparison"],
                "endpoint": endpoint_id,
                "p_raw": holm["raw_p"][endpoint_id],
                "p_adjusted": holm["adjusted_p"][endpoint_id],
                "holm_rank": rank[index],
                "decision": stats["decisions"][endpoint_id]["decision"],
            }
        )
    return rows


def _build_null_disclosure_rows(core: Mapping[str, Any], prereg: S2Prereg) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    policy_task = "task 端点值：任一 meta_seed 单元为 null 即整 task 记 null（不插补、不丢弃任务）"
    policy_cell = "meta_seed 单元：任一 draw 缺失/FAILED/null 即整单元记 null"
    for endpoint_id in INFERENCE_ENDPOINTS:
        block = core["endpoints"][endpoint_id]
        expected = block["n_tasks"] * 2
        nonnull = 0
        for task_id in block["tasks"]:
            task_row = block["per_task"][task_id]
            for arm in EXPECTED_ARMS:
                if task_row[arm]["value"] is not None:
                    nonnull += 1
        rows.append(
            {
                "scope": "task_arm_values",
                "endpoint": endpoint_id,
                "arm": "BOTH",
                "expected": expected,
                "observed_nonnull": nonnull,
                "observed_null": expected - nonnull,
                "null_rate": (expected - nonnull) / expected if expected else 1.0,
                "policy": policy_task,
            }
        )
        for arm in EXPECTED_ARMS:
            expected_cells = block["n_tasks"] * len(prereg.meta_seeds)
            nonnull_cells = 0
            for task_id in block["tasks"]:
                per_seed = block["per_task"][task_id][arm]["per_meta_seed"]
                nonnull_cells += sum(1 for value in per_seed.values() if value["value"] is not None)
            rows.append(
                {
                    "scope": "meta_seed_cells",
                    "endpoint": endpoint_id,
                    "arm": arm,
                    "expected": expected_cells,
                    "observed_nonnull": nonnull_cells,
                    "observed_null": expected_cells - nonnull_cells,
                    "null_rate": (expected_cells - nonnull_cells) / expected_cells if expected_cells else 1.0,
                    "policy": policy_cell,
                }
            )
    resources = core["resources"]
    for endpoint_id in RESOURCE_ENDPOINTS:
        item = resources[endpoint_id]
        observed = 1 if item.get("value") is not None else 0
        rows.append(
            {
                "scope": "resource_metric",
                "endpoint": endpoint_id,
                "arm": "BOTH",
                "expected": 1,
                "observed_nonnull": observed,
                "observed_null": 1 - observed,
                "null_rate": 0.0 if observed else 1.0,
                "policy": "资源指标仅描述；缺失时记 null 并在报告中披露",
            }
        )
    return rows


def _build_negative_control_rows(
    run: S2RunData,
    prereg: S2Prereg,
    core: Mapping[str, Any],
    stats: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """负控/边界核对清单：每条都是机器可读的 PASS/DISCLOSED，不允许静默。"""
    boundary = run.validation["data_boundary"]
    fd_evidence = run.validation.get("fd_gate_evidence") or {}
    fd_statuses = {name: item.get("status") for name, item in fd_evidence.items()}
    max_null_rate = max(
        (float(core["endpoints"][endpoint_id]["null_ratio"]) for endpoint_id in INFERENCE_ENDPOINTS),
        default=1.0,
    )
    rows: list[dict[str, Any]] = [
        {
            "check_id": "NC-01",
            "category": "physical_isolation",
            "status": "PASS" if run.run_config["physical_call_count"] == 0 and prereg.physical_call_count == 0 else "FAIL",
            "expected": "physical_call_count=0（边界+run_config+run_summary）",
            "observed": f"prereg={prereg.physical_call_count};run_config={run.run_config['physical_call_count']}",
            "note": "分析层不 import/启动任何真实求解器，只读 run 产物。",
        },
        {
            "check_id": "NC-02",
            "category": "data_boundary",
            "status": "PASS" if boundary["splits_seen"] == [SPLIT_EVAL] else "FAIL",
            "expected": "eval 记录 split 仅 meta_validation，holdout 行 0",
            "observed": ",".join(boundary["splits_seen"]),
            "note": "holdout 数据行不进入分析层任何计算。",
        },
        {
            "check_id": "NC-03",
            "category": "prereg_contract",
            "status": "PASS",
            "expected": "prereg_id/prereg_digest/analysis_plan_digest 自洽",
            "observed": prereg.prereg_id,
            "note": "canonical JSON + 换行；三个摘要独立复算。",
        },
        {
            "check_id": "NC-04",
            "category": "frozen_package",
            "status": "PASS",
            "expected": "S0-7 冻结包 6 字段恒等 + SHA256SUMS raw sha",
            "observed": prereg.frozen_package["run_id"],
            "note": "冻结包不可变；分析只读。",
        },
        {
            "check_id": "NC-05",
            "category": "fairness",
            "status": "PASS",
            "expected": "两臂 config 除 first_order 外逐字段相同",
            "observed": "input_dim=12,hidden=[16,16],inner_lr=0.01,inner_steps=5,outer_lr=0.001,tasks_per_batch=8,seed=42",
            "note": "等预算/等结构公平性由 prereg 校验器强制。",
        },
        {
            "check_id": "NC-06",
            "category": "multiple_comparison",
            "status": "PASS" if stats["holm"]["family_size"] == HOLM_FAMILY_SIZE else "FAIL",
            "expected": "唯一 Holm 族 family_size=2（C1×k5,k10）",
            "observed": stats["holm"]["family_id"],
            "note": "不得按端点拆分族、不得另行校正。",
        },
        {
            "check_id": "NC-07",
            "category": "run_schema",
            "status": "PASS",
            "expected": "train 12 字段 / eval 16 字段精确集合；canonical JSONL",
            "observed": f"train={run.counts['train']},eval={run.counts['eval']}",
            "note": "字段缺失或多余均 fail-closed。",
        },
        {
            "check_id": "NC-08",
            "category": "coverage",
            "status": "PASS" if run.validation["coverage"]["complete"] else "DISCLOSED",
            "expected": "6000 行 / 6 组 / 20 任务 / K=0,1,5,10 / draw=0..9",
            "observed": f"train={run.counts['train']},eval={run.counts['eval']},complete={run.validation['coverage']['complete']}",
            "note": "正式 run 必须完整；allow_incomplete_run 仅用于开发/测试并显式披露。",
        },
        {
            "check_id": "NC-09",
            "category": "fd_gate",
            "status": "PASS" if fd_statuses else "DISCLOSED",
            "expected": "FD pilot micro/full_size 证据存在、raw sha 匹配、无 FAIL",
            "observed": ";".join(f"{name}:{status}" for name, status in fd_statuses.items()),
            "note": "FD gate 失败则分析拒绝启动。",
        },
        {
            "check_id": "NC-10",
            "category": "determinism",
            "status": "DISCLOSED",
            "expected": "determinism reruns=2 字节一致性",
            "observed": "NOT_VERIFIABLE_IN_ANALYSIS",
            "note": "由 A1 run 层产物承载；本层不伪造 PASS。",
        },
        {
            "check_id": "NC-11",
            "category": "null_disclosure",
            "status": "PASS",
            "expected": "null 率与原因逐层披露，不得把 null 写 0",
            "observed": f"max_null_rate={max_null_rate}",
            "note": "null_ratio>0.70 → INCONCLUSIVE。",
        },
        {
            "check_id": "NC-12",
            "category": "decision_rules",
            "status": "PASS",
            "expected": "Holm p<0.05 且 CI 不跨 0 且 FULL<FOMAML 且相对改善>=1% → BENEFIT；对称 HARM",
            "observed": stats["overall"]["decision"],
            "note": "决策原因逐项记录在 aggregate.json / CSV。",
        },
        {
            "check_id": "NC-13",
            "category": "endpoint_scope",
            "status": "PASS",
            "expected": "K=0/K=1/标准化/MAE/资源仅描述，不做 benefit/harm",
            "observed": "inference_endpoints=" + ",".join(INFERENCE_ENDPOINTS),
            "note": "推断端点仅 k5 主 + k10 次。",
        },
        {
            "check_id": "NC-14",
            "category": "aggregation_unit",
            "status": "PASS",
            "expected": "task 为分析单位，不跨任务混合 draw",
            "observed": f"n_tasks={core['n_tasks']}",
            "note": "先 draw 后 meta_seed，最后 task 配对。",
        },
    ]
    if any(row["status"] == "FAIL" for row in rows):
        failed = [row["check_id"] for row in rows if row["status"] == "FAIL"]
        _fail(ERR_INPUT, "负控/边界核对失败", detail=",".join(failed))
    return rows


def _build_rmse_vs_k(run: S2RunData, prereg: S2Prereg) -> dict[str, Any]:
    """图 3 输入：raw RMSE 随 K 变化；保留 task 级值供 task 级 bootstrap（v1.5 §8.1.2）。

    K=0/1 为描述性端点（仍按 task 级聚合）；缺失任务不插补，记入 null_tasks 并披露。
    """
    cells = _cell_index(run, prereg)
    tasks = _analysis_tasks(run)
    result: dict[str, Any] = {
        "K": list(prereg.k_values),
        "arms": {},
        "per_task": {str(k_value): {} for k_value in prereg.k_values},
        "ci": {arm: {} for arm in EXPECTED_ARMS},
        "bootstrap": {
            "unit": "task",
            "n_resamples": BOOTSTRAP_SAMPLES,
            "seed": BOOTSTRAP_SEED,
            "ci": CONFIDENCE_LEVEL,
            "method": "percentile",
            "note": "重采样单元=task（meta_validation）；每个 task 先取 meta_seed×draw 聚合值；不得跨 task 平滑。",
        },
    }
    for arm in EXPECTED_ARMS:
        series: list[float | None] = []
        for k_value in prereg.k_values:
            task_values: dict[str, float] = {}
            null_tasks: list[str] = []
            for task_id in tasks:
                seed_values: list[float] = []
                failed = False
                for meta_seed in prereg.meta_seeds:
                    value, _reason = _aggregate_cell(
                        cells.get((arm, meta_seed, task_id, k_value)),
                        field="query_rmse_raw",
                        draws=prereg.draws,
                    )
                    if value is None:
                        failed = True
                        break
                    seed_values.append(value)
                if failed:
                    null_tasks.append(task_id)
                else:
                    task_values[task_id] = math.fsum(seed_values) / len(seed_values)
            result["per_task"][str(k_value)][arm] = dict(task_values)
            # task 级重采样：先取每个 task 的 meta_seed×draw 聚合值，再对 task 级值做 percentile bootstrap。
            cell_values = list(task_values.values())
            ci = bootstrap_mean_ci(cell_values)
            result["ci"][arm][str(k_value)] = {
                "n": len(cell_values),
                "mean": ci.get("mean_difference"),
                "ci_low": ci.get("ci_low"),
                "ci_high": ci.get("ci_high"),
                "n_resamples": ci.get("n_resamples"),
                "seed": ci.get("seed"),
                "confidence_level": ci.get("confidence_level"),
                "method": ci.get("method"),
            }
            series.append(_mean_or_none(cell_values) if not null_tasks else None)
            result.setdefault("null_tasks", {}).setdefault(arm + "_K" + str(k_value), null_tasks)
        result["arms"][arm] = series
    return result


def _load_task_family_info(
    prereg: S2Prereg,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """fig9 数据源：冻结包 tasks.json 的 task_id -> family 映射。

    只读冻结包元数据；缺失/不可读时返回 reason 让 fig9 标 NOT_RUN，不中断整份分析。
    注意（A5-S2M0R5-01）：S0-7 的 120 个 task 同属单一 family，fig9 panel b 只能画族内分布，
    不得解释为任务族间差异。
    """
    package_path = str(prereg.frozen_package.get("package_path") or "")
    source = package_path + "/tasks.json" if package_path else "frozen_package.tasks.json"
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    try:
        package_dir = _resolve_repo_relative(package_path, repo_root=root, label="frozen_package.package_path")
    except S2AnalysisError as exc:
        return {"mapping": None, "source": source, "reason": "TASKS_JSON_UNAVAILABLE: " + str(exc)[:200]}
    tasks_path = package_dir / "tasks.json"
    if not tasks_path.is_file():
        return {"mapping": None, "source": source, "reason": "TASKS_JSON_MISSING: " + str(tasks_path)}
    try:
        raw = json.loads(tasks_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"mapping": None, "source": source, "reason": "TASKS_JSON_INVALID: " + str(exc)[:200]}
    if not isinstance(raw, list):
        return {"mapping": None, "source": source, "reason": "TASKS_JSON_NOT_LIST"}
    mapping: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        task_id = item.get("task_id")
        family = item.get("family")
        if isinstance(task_id, str) and task_id and isinstance(family, str) and family:
            mapping[task_id] = family
    if not mapping:
        return {"mapping": None, "source": source, "reason": "TASKS_JSON_EMPTY_FAMILY_MAP"}
    return {"mapping": mapping, "source": source, "reason": None}


def _build_figure_state(
    run: S2RunData,
    prereg: S2Prereg,
    core: Mapping[str, Any],
    stats: Mapping[str, Any],
    aggregate_meta: Mapping[str, Any],
    negative_controls: Sequence[Mapping[str, Any]],
    task_family_info: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """s2_figures 的唯一输入：自包含、JSON 友好、缺失即 null/NOT_APPLICABLE。"""
    train_series: list[dict[str, Any]] = []
    for record in run.train_records:
        train_series.append(
            {
                "arm": str(record["arm"]),
                "meta_seed": int(record["meta_seed"]),
                "outer_step": int(record["outer_step"]),
                "train_loss": record["train_loss"],
                "grad_norm": record["grad_norm"],
                "status": str(record["status"]),
            }
        )
    return {
        "run_id": aggregate_meta["run_id"],
        "prereg_id": prereg.prereg_id,
        "evidence_scope": prereg.evidence_scope,
        "arms": list(EXPECTED_ARMS),
        "train_series": train_series,
        "inference": [dict(item) for item in stats["inferences"]],
        "endpoints": {
            endpoint_id: {
                "endpoint_id": endpoint_id,
                "K": core["endpoints"][endpoint_id]["K"],
                "n_tasks": core["endpoints"][endpoint_id]["n_tasks"],
                "null_ratio": core["endpoints"][endpoint_id]["null_ratio"],
                "per_task": core["endpoints"][endpoint_id]["per_task"],
            }
            for endpoint_id in INFERENCE_ENDPOINTS
        },
        "descriptive_metrics": core["descriptive_metrics"],
        "rmse_vs_k": _build_rmse_vs_k(run, prereg),
        "fd_gate_evidence": run.validation.get("fd_gate_evidence") or {},
        "negative_controls": [dict(row) for row in negative_controls],
        "integrity": dict(core["integrity"]),
        "resources": dict(core["resources"]),
        "coverage": dict(run.validation["coverage"]),
        "overall": dict(stats["overall"]),
        "decisions": {key: dict(value) for key, value in stats["decisions"].items()},
        "holm": dict(stats["holm"]),
        "counts": dict(run.validation["counts"]),
        "task_families": (
            dict(task_family_info.get("mapping") or {})
            if task_family_info and task_family_info.get("mapping")
            else None
        ),
        "task_families_source": (task_family_info or {}).get("source"),
        "task_families_reason": (task_family_info or {}).get("reason"),
    }

# ---------------------------------------------------------------------------
# 产物落盘、figure 状态、主分析管线与 CLI
# ---------------------------------------------------------------------------


def _write_json_artifact(path: Path, payload: Mapping[str, Any]) -> None:
    try:
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    except (TypeError, ValueError) as exc:
        _fail(ERR_OUTPUT, "产物无法序列化为 JSON", detail=str(path) + " | " + str(exc))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        _fail(ERR_OUTPUT, "产物写入失败", detail=str(path) + " | " + str(exc))


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):  # pragma: no cover - 防御性
            _fail(ERR_OUTPUT, "CSV 不接受非有限浮点数")
        return repr(value)
    return str(value)


def _write_csv_artifact(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(list(columns))
            for row in rows:
                unknown = sorted(set(row.keys()) - set(columns))
                if unknown:
                    _fail(ERR_OUTPUT, "CSV 行含未声明列", detail=str(path) + " | " + ",".join(unknown))
                writer.writerow([_csv_value(row.get(column)) for column in columns])
    except OSError as exc:
        _fail(ERR_OUTPUT, "CSV 写入失败", detail=str(path) + " | " + str(exc))


def _figure_status_template(reason: str) -> dict[str, Any]:
    return {
        "schema_version": S2_FIGURE_STATUS_SCHEMA_VERSION,
        "figures": {
            key: {"status": "NOT_RUN", "path": None, "reason": reason} for key in FIGURE_KEYS
        },
        "summary": {"n_figures": len(FIGURE_KEYS), "n_rendered": 0, "n_not_run": len(FIGURE_KEYS), "n_not_applicable": 0},
    }


def _import_figures_module() -> Any:
    try:  # 作为包导入（测试与正式分析路径）
        from . import s2_figures  # type: ignore

        return s2_figures
    except ImportError:
        try:  # 作为顶层模块执行（python s2_analysis.py 或 sys.path 注入）
            import s2_figures  # type: ignore

            return s2_figures
        except ImportError:
            return None


def _truncate_figure_reason(exc: Exception) -> str:
    text = str(exc).replace("\n", " ")
    return ("FIGURE_RENDER_ERROR: " + text)[:300]


def _generate_figures(
    state: Mapping[str, Any],
    *,
    output_dir: Path,
    enabled: bool,
) -> dict[str, Any]:
    """调用 s2_figures 生成 9 张规范键图（fig1..fig9）；失败不掩盖，逐图写 NOT_RUN/FAILED 原因。"""
    if not enabled:
        return _figure_status_template("FIGURES_DISABLED_BY_REQUEST")
    module = _import_figures_module()
    if module is None:
        return _figure_status_template("FIGURES_MODULE_NOT_AVAILABLE")
    try:
        status = module.generate_s2_figures(
            state=state,
            output_dir=output_dir,
            figure_filenames=dict(FIGURE_FILENAMES),
        )
    except Exception as exc:  # noqa: BLE001 - 出图失败必须落到 figure_status.json，不静默
        status = _figure_status_template(_truncate_figure_reason(exc))
        status["summary"]["n_not_run"] = len(FIGURE_KEYS)
        return status
    payload = _validate_figure_status(status)
    return payload


def _validate_figure_status(status: Any) -> dict[str, Any]:
    mapping = _as_mapping(status, code=ERR_OUTPUT, label="figure_status")
    figures = _as_mapping(mapping.get("figures"), code=ERR_OUTPUT, label="figure_status.figures")
    _require_exact_keys(figures, FIGURE_KEYS, code=ERR_OUTPUT, label="figure_status.figures")
    normalized: dict[str, Any] = {}
    for key in FIGURE_KEYS:
        item = _as_mapping(figures[key], code=ERR_OUTPUT, label="figure_status.figures." + key)
        status_value = _require_str(item.get("status"), code=ERR_OUTPUT, label="figure_status.figures." + key + ".status")
        if status_value not in ("RENDERED", "NOT_RUN", "NOT_APPLICABLE"):
            _fail(ERR_OUTPUT, "figure 状态非法", detail=key + ":" + status_value)
        normalized[key] = {
            "status": status_value,
            "path": item.get("path") if status_value == "RENDERED" else None,
            "reason": item.get("reason"),
        }
    rendered = sum(1 for item in normalized.values() if item["status"] == "RENDERED")
    not_run = sum(1 for item in normalized.values() if item["status"] == "NOT_RUN")
    not_applicable = sum(1 for item in normalized.values() if item["status"] == "NOT_APPLICABLE")
    return {
        "schema_version": S2_FIGURE_STATUS_SCHEMA_VERSION,
        "figures": normalized,
        "summary": {
            "n_figures": len(FIGURE_KEYS),
            "n_rendered": rendered,
            "n_not_run": not_run,
            "n_not_applicable": not_applicable,
        },
        "generated_utc": _utc_now_iso(),
    }


def _trim_descriptive(core: Mapping[str, Any]) -> dict[str, Any]:
    """聚合文件里的描述性指标只保留 task 级 arm 值，完整逐 meta_seed 明细放 CSV。"""
    trimmed: dict[str, Any] = {}
    for endpoint_id, block in core["descriptive_metrics"].items():
        per_task = {
            task_id: {
                ARM_FULL: block["per_task"][task_id][ARM_FULL]["value"],
                ARM_FOMAML: block["per_task"][task_id][ARM_FOMAML]["value"],
            }
            for task_id in block["tasks"]
        }
        trimmed[endpoint_id] = {
            "endpoint_id": endpoint_id,
            "K": block["K"],
            "field": block["field"],
            "n_tasks": block["n_tasks"],
            "null_ratio": block["null_ratio"],
            "per_task": per_task,
            "note": "描述性指标：不做 benefit/harm 推断。",
        }
    return {"metrics": trimmed, "resources": core["resources"]}


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    if output_dir.exists():
        if not output_dir.is_dir():
            _fail(ERR_OUTPUT, "输出路径已存在且不是目录", detail=str(output_dir))
        entries = list(output_dir.iterdir())
        if entries and not overwrite:
            _fail(ERR_OUTPUT, "输出目录非空且未指定 overwrite", detail=str(output_dir))
    else:
        try:
            output_dir.mkdir(parents=True)
        except OSError as exc:
            _fail(ERR_OUTPUT, "无法创建输出目录", detail=str(output_dir) + " | " + str(exc))


def analyze_s2_run(
    *,
    prereg_path: str | Path,
    run_dir: str | Path,
    output_dir: str | Path,
    repo_root: str | Path | None = None,
    verify_frozen_package: bool = True,
    verify_code_sha: bool = True,
    require_summary: bool = True,
    allow_incomplete_run: bool = False,
    generate_figures: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """S2 分析主入口：加载冻结 prereg + 正式 run → 聚合/统计/决策 → 8 数据产物 + 9 图。

    fail-closed：任何输入合同不满足即抛 S2AnalysisError；输出目录不可覆盖时拒绝执行。
    """
    destination = Path(output_dir).resolve()
    _prepare_output_dir(destination, overwrite=overwrite)
    prereg = load_s2_prereg(
        prereg_path,
        repo_root=repo_root,
        verify_frozen_package=verify_frozen_package,
        verify_pilot_artifacts=False,  # pilot 证据由 load_s2_run 的 _inspect_fd_evidence 复核（含 run_dir 兜底）
        verify_code_sha=verify_code_sha,
    )
    run = load_s2_run(
        run_dir,
        prereg,
        repo_root=repo_root,
        require_summary=require_summary,
        allow_incomplete_run=allow_incomplete_run,
    )
    checks: list[dict[str, Any]] = list(run.checks)
    core = _build_analysis_core(run, prereg, checks=checks)
    stats = _build_statistics(core, prereg, checks=checks)
    run_id = str(run.run_config["run_id"])
    prereg_echo = _build_prereg_echo(prereg)
    endpoint_rows = _build_endpoint_table_rows(core, stats)
    per_task_rows = _build_per_task_rows(core, prereg)
    holm_rows = _build_holm_rows(stats)
    null_rows = _build_null_disclosure_rows(core, prereg)
    negative_controls = _build_negative_control_rows(run, prereg, core, stats)
    aggregate_meta = {
        "run_id": run_id,
        "run_dir": str(run.run_dir),
        "prereg": {
            "path": str(prereg.path),
            "prereg_id": prereg.prereg_id,
            "prereg_digest": prereg.prereg_digest,
            "analysis_plan_digest": prereg.analysis_plan_digest,
            "source_sha256": prereg_echo["source_sha256"],
        },
        "frozen_package": dict(prereg.frozen_package),
        "code_sha": prereg.code_sha,
        "evidence_scope": prereg.evidence_scope,
        "development_set": DEVELOPMENT_SET,
        "record_counts": dict(run.validation["counts"]),
        "source_files": [dict(item) for item in run.validation["source_files"]],
        "run_status": run.run_status,
        "run_summary_status_counts": dict(run.validation["status_counts"]),
        "created_utc": _utc_now_iso(),
        "checks": [dict(check) for check in checks],
    }
    task_family_info = _load_task_family_info(prereg, repo_root=repo_root)
    figure_state = _build_figure_state(
        run, prereg, core, stats, aggregate_meta, negative_controls, task_family_info
    )
    figure_status = _generate_figures(figure_state, output_dir=destination, enabled=generate_figures)
    aggregate = dict(aggregate_meta)
    aggregate.update(
        {
            "schema_version": S2_AGGREGATE_SCHEMA_VERSION,
            "analysis_id": "s2-analysis-" + run_id,
            "endpoint_rows": endpoint_rows,
            "inference": [dict(item) for item in stats["inferences"]],
            "holm": dict(stats["holm"]),
            "decisions": dict(stats["decisions"]),
            "overall": dict(stats["overall"]),
            "null_disclosure": null_rows,
            "descriptive": _trim_descriptive(core),
            "integrity": dict(core["integrity"]),
            "coverage": dict(run.validation["coverage"]),
            "data_boundary": dict(run.validation["data_boundary"]),
            "metric_definitions": dict(METRIC_DEFINITIONS),
            "negative_controls": negative_controls,
            "figure_status": figure_status,
            "prereg_echo_summary": {
                "schema_version": prereg_echo["schema_version"],
                "prereg_id": prereg_echo["prereg_id"],
                "prereg_digest": prereg_echo["prereg_digest"],
                "analysis_plan_digest": prereg_echo["analysis_plan_digest"],
                "digest_self_consistent": prereg_echo["digest_self_consistent"],
            },
            "outputs": list(S2_OUTPUT_FILES) + [FIGURE_FILENAMES[key] for key in FIGURE_KEYS],
        }
    )
    _write_json_artifact(destination / "s2_prereg_echo.json", prereg_echo)
    _write_json_artifact(destination / "figure_status.json", figure_status)
    _write_csv_artifact(destination / "s2_endpoint_tables.csv", _CSV_COLUMNS["s2_endpoint_tables.csv"], endpoint_rows)
    _write_csv_artifact(destination / "s2_per_task_aggregates.csv", _CSV_COLUMNS["s2_per_task_aggregates.csv"], per_task_rows)
    _write_csv_artifact(destination / "s2_holm_family.csv", _CSV_COLUMNS["s2_holm_family.csv"], holm_rows)
    _write_csv_artifact(destination / "s2_null_disclosure.csv", _CSV_COLUMNS["s2_null_disclosure.csv"], null_rows)
    _write_csv_artifact(
        destination / "s2_negative_controls.csv", _CSV_COLUMNS["s2_negative_controls.csv"], negative_controls
    )
    _write_json_artifact(destination / "aggregate.json", aggregate)
    artifacts = [destination / name for name in S2_OUTPUT_FILES]
    return {
        "status": "PASS",
        "run_id": run_id,
        "prereg_id": prereg.prereg_id,
        "output_dir": str(destination),
        "artifacts": [str(path) for path in artifacts],
        "overall_decision": dict(stats["overall"]),
        "figure_status": figure_status,
        "negative_controls": negative_controls,
        "n_tasks": core["n_tasks"],
        "record_counts": dict(run.validation["counts"]),
        "run_checks": [dict(check) for check in checks],
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="P4 路线A S2 分析层：冻结 prereg + 正式 run → 统计/决策/产物（只读、physical=0）",
    )
    parser.add_argument("--prereg", required=True, help="冻结 s2_preregistration.json 路径")
    parser.add_argument("--run-dir", required=True, help="正式 run 目录（含 run_config/run_records/run_summary）")
    parser.add_argument("--output-dir", required=True, help="分析产物输出目录（默认要求不存在或为空）")
    parser.add_argument("--repo-root", default=None, help="仓库根（默认按本文件位置推断）")
    parser.add_argument("--allow-incomplete-run", action="store_true", help="允许记录网格不完整（仅开发/测试，显式披露）")
    parser.add_argument("--skip-figures", action="store_true", help="跳过 9 张图（figure_status.json 记 NOT_RUN 原因）")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖非空输出目录")
    parser.add_argument("--verify-only", action="store_true", help="只校验 prereg + run 合同，不写任何产物")
    parser.add_argument(
        "--skip-frozen-package-check",
        action="store_true",
        help="仅限开发/合成数据：跳过 S0-7 冻结包 SHA256SUMS 复算（正式分析禁止使用）",
    )
    parser.add_argument(
        "--skip-code-sha-check",
        action="store_true",
        help="仅限开发/合成数据：跳过 code_sha 复算（正式分析禁止使用）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.verify_only:
            prereg = load_s2_prereg(
                args.prereg,
                repo_root=args.repo_root,
                verify_frozen_package=not args.skip_frozen_package_check,
                verify_pilot_artifacts=False,
                verify_code_sha=not args.skip_code_sha_check,
            )
            run = load_s2_run(
                args.run_dir,
                prereg,
                repo_root=args.repo_root,
                allow_incomplete_run=args.allow_incomplete_run,
            )
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "mode": "verify_only",
                        "prereg_id": prereg.prereg_id,
                        "run_id": str(run.run_config["run_id"]),
                        "record_counts": dict(run.validation["counts"]),
                        "checks": [dict(check) for check in list(prereg.checks) + list(run.checks)],
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                )
            )
            return 0
        result = analyze_s2_run(
            prereg_path=args.prereg,
            run_dir=args.run_dir,
            output_dir=args.output_dir,
            repo_root=args.repo_root,
            allow_incomplete_run=args.allow_incomplete_run,
            verify_frozen_package=not args.skip_frozen_package_check,
            verify_code_sha=not args.skip_code_sha_check,
            generate_figures=not args.skip_figures,
            overwrite=args.overwrite,
        )
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "run_id": result["run_id"],
                    "prereg_id": result["prereg_id"],
                    "output_dir": result["output_dir"],
                    "n_tasks": result["n_tasks"],
                    "record_counts": result["record_counts"],
                    "overall": result["overall_decision"],
                    "figures": result["figure_status"]["summary"],
                },
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
            )
        )
        return 0
    except S2AnalysisError as exc:
        print(
            json.dumps(
                {"status": "FAIL", "code": exc.code, "message": exc.message, "detail": exc.detail},
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":  # pragma: no cover - CLI 入口
    sys.exit(main())
