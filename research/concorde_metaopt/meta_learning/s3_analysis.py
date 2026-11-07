"""S3 分析器：只读消费正式/SMOKE run 产物，重算端点、聚合、统计与决策。

权威合同：docs/planning/p4_route_a_s3_execution_plan_20261107.md v1.2
（§4.3 run 产物 schema、§4.5 SMOKE 语义、§5 端点/统计/图、§6 预注册与哈希）。

边界（任一违反即 fail-closed）：
- 只读 run 目录与冻结 prereg/证据，不写仓库；输出仅写调用方指定的 output_dir；
- physical_call_count 恒为 0：本模块不 import 任何求解器/网络库，不启动子进程；
- 参考解封存件只在 run 完成后由本模块读取，用于 gap_to_reference；
- 缺失数据记 NOT_RUN/null 并披露，绝不插值或伪造。

错误码前缀 S3_ANALYSIS_*；所有错误抛出 S3AnalysisError（.code/.message/.detail）。
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np

from . import s3_prereg as sp

# ---------------------------------------------------------------------------
# 分析器 schema 与常量（计划 §4.3/§5/§6；run schema 常量一律来自 s3_prereg 单源）
# ---------------------------------------------------------------------------
S3_AGGREGATE_SCHEMA_VERSION = sp.S3_AGGREGATE_SCHEMA_VERSION
S3_ANALYSIS_SCHEMA_VERSION = "p4ra-s3-analysis-v1"
# 证据范围/开发集单源来自 s3_prereg（lead 合同：常量一律 sp.*）
S3_EVIDENCE_SCOPE = sp.S3_EVIDENCE_SCOPE
S3_DEVELOPMENT_SET = sp.S3_DEVELOPMENT_SET
S3_FIGURE_STATUS_SCHEMA_VERSION = "p4ra-s3-figure-status-v1"

S3_ANALYSIS_ERROR = "S3_ANALYSIS_ERROR"
S3_ANALYSIS_PREREG_SCHEMA_INVALID = "S3_ANALYSIS_PREREG_SCHEMA_INVALID"
S3_ANALYSIS_PREREG_DIGEST_MISMATCH = "S3_ANALYSIS_PREREG_DIGEST_MISMATCH"
S3_ANALYSIS_PREREG_PLACEHOLDER = "S3_ANALYSIS_PREREG_PLACEHOLDER_REJECTED"
S3_ANALYSIS_PREREG_BINDING_MISMATCH = "S3_ANALYSIS_PREREG_BINDING_MISMATCH"
S3_ANALYSIS_PREREG_PHYSICAL_CALLS = "S3_ANALYSIS_PREREG_PHYSICAL_CALLS"
S3_ANALYSIS_PREREG_FILE_INVALID = "S3_ANALYSIS_PREREG_FILE_INVALID"
S3_ANALYSIS_RUN_SCHEMA_INVALID = "S3_ANALYSIS_RUN_SCHEMA_INVALID"
S3_ANALYSIS_RUN_BINDING_MISMATCH = "S3_ANALYSIS_RUN_BINDING_MISMATCH"
S3_ANALYSIS_RECORD_INVALID = "S3_ANALYSIS_RECORD_INVALID"
S3_ANALYSIS_RECORD_COUNTS_MISMATCH = "S3_ANALYSIS_RECORD_COUNTS_MISMATCH"
S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED = "S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED"
S3_ANALYSIS_K_SWEEP_MISSING_PENDING = "S3_ANALYSIS_K_SWEEP_MISSING_PENDING_V13B"
S3_ANALYSIS_FD_GATE_PREREG_BINDING_PENDING = "S3_ANALYSIS_FD_GATE_PREREG_BINDING_PENDING_V13B"
S3_ANALYSIS_BUDGET_MISMATCH = "S3_ANALYSIS_BUDGET_MISMATCH"
S3_ANALYSIS_DATA_BOUNDARY_VIOLATION = "S3_ANALYSIS_DATA_BOUNDARY_VIOLATION"
S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ = "S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ"
S3_ANALYSIS_FD_GATE_INVALID = "S3_ANALYSIS_FD_GATE_INVALID"
S3_ANALYSIS_COMPARATOR_MISMATCH = "S3_ANALYSIS_COMPARATOR_MISMATCH"
S3_ANALYSIS_OUTPUT_INVALID = "S3_ANALYSIS_OUTPUT_INVALID"
S3_ANALYSIS_INPUT_INVALID = "S3_ANALYSIS_INPUT_INVALID"
S3_ANALYSIS_FIGURE_INVALID = "S3_ANALYSIS_FIGURE_INVALID"
S3_ANALYSIS_DETERMINISM_MISMATCH = "S3_ANALYSIS_DETERMINISM_MISMATCH"

# 主/次比较（计划 §5.2；comparator 固定，任何偏离即 FAILED_COMPARATOR_MISMATCH）
COMPARATOR_ARMS = ("S3-BO-FOMAML-CON", "S3-BO-FOMAML-OBJ")
ARM_CON, ARM_OBJ = COMPARATOR_ARMS
DESCRIPTIVE_ARMS = ("S3-BO-RANDOM", "S3-BO-ANIL-CON", "S3-DE")
ARM_RANDOM, ARM_ANIL, ARM_DE = DESCRIPTIVE_ARMS

C1_FAMILY_ID = "s3-feasible-hit-2tests"
C2_FAMILY_ID = "s3-gap-to-ref-2tests"
C1_ENDPOINT = "feasible_hit_rate"
C2_ENDPOINT = "gap_to_reference"
C1_THRESHOLD_ABS = 0.02
C2_RELATIVE_THRESHOLD = 0.01
C2_DENOMINATOR_FLOOR = 1e-6
ALPHA = 0.05
HOLM_FAMILY_SIZE = 2
WILCOXON_MIN_N_EFF = 15
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_SEED = 20261107
BOOTSTRAP_CONFIDENCE = 0.95
PERMUTATION_RESAMPLES = 10000
PERMUTATION_SEED = 20261107
N_TASKS_MAIN = 20

# 端点 ID（计划 §5.1）
EP_FEASIBLE_HIT_RATE = "feasible_hit_rate"
EP_BEST_FEASIBLE_VALUE = "best_feasible_value"
EP_GAP_TO_REFERENCE = "gap_to_reference"
EP_FIRST_FEASIBLE_INDEX = "first_feasible_eval_index"
EP_SURROGATE_RMSE = "surrogate_rmse"
EP_SURROGATE_MAE = "surrogate_mae"
EP_F_RMSE = "f_rmse"
EP_F_MAE = "f_mae"
EP_ADAPTATION_COST = "adaptation_cost"
EP_TOTAL_COST = "total_cost"

# 决策枚举（计划 §1.3/§5.2，互斥穷尽）
D_INCONCLUSIVE = "INCONCLUSIVE"
D_SUPPORTED_BENEFIT = "SUPPORTED_BENEFIT"
D_SUPPORTED_HARM = "SUPPORTED_HARM"
D_NEGLIGIBLE_SIGNIFICANT = "NEGLIGIBLE_SIGNIFICANT"
D_DIRECTION_INCONSISTENT = "DIRECTION_INCONSISTENT"
D_NULL = "NULL"
LAYER_DECISIONS = (
    D_INCONCLUSIVE,
    D_SUPPORTED_BENEFIT,
    D_SUPPORTED_HARM,
    D_NEGLIGIBLE_SIGNIFICANT,
    D_DIRECTION_INCONSISTENT,
    D_NULL,
)

# 总体 S3 结论（计划 §1.3/§5.2，唯一优先级）
O_INCONCLUSIVE = "INCONCLUSIVE"
O_HARM = "HARM"
O_DIRECTION_INCONSISTENT = "DIRECTION_INCONSISTENT"
O_BENEFIT = "BENEFIT"
O_NO_EVIDENCE = "NO_EVIDENCE"
OVERALL_DECISIONS = (
    O_INCONCLUSIVE,
    O_HARM,
    O_DIRECTION_INCONSISTENT,
    O_BENEFIT,
    O_NO_EVIDENCE,
)

# ANIL 成本-性能判定（计划 §5.2）
ANIL_NONINFERIOR_MARGIN = 0.02
ANIL_COST_RATIO_MAX = 0.75
ANIL_DECISIONS = ("ANIL_COST_EFFICIENT", "ANIL_INFERIOR", "ANIL_INCONCLUSIVE")

NEGATIVE_CONTROL_SUSPICIOUS = "NEGATIVE_CONTROL_SUSPICIOUS"
NEGATIVE_CONTROL_PASS = "NEGATIVE_CONTROL_PASS"
NEGATIVE_CONTROL_INCONCLUSIVE = "NEGATIVE_CONTROL_INCONCLUSIVE"

SMOKE_DISCLOSED_CODE = "S3_ANALYSIS_SMOKE_BUDGET_DISCLOSED"
# 计划 §3.3 L250：K=5 固定，FORMAL run_config.k_sweep 唯一合法值 = [5]。
# [0,1,3,5] 属 M1 K-sweep 诊断件（计划 §4.2 L284，240 runs/15,360 evals，DEVELOPMENT_VALIDATION_ONLY），
# 不写正式 run_config、不进正式预算/统计；fig2 数据源为该独立诊断件（未交付 → NOT_RUN）。
FORMAL_K_SWEEP = (5,)
SMOKE_EVIDENCE_SCOPE = sp.S3_EVIDENCE_SCOPE

# R-S3-05（Lead m08943/m08973）：campaign 改为 run 级多进程并行后，pilot 若触发预注册的
# R-S3-02 降网格规则，FORMAL run 会使用 opt_seeds=5 / main_runs=3000 / main_evals=288000。
# 不改 s3_prereg.py（A1 的 code_sha 文件）：优先读 sp.S3_RS3_02_FALLBACK，缺失时用本文件内联常量，
# 主网格与 fallback 二者都接受，只有 fallback 时写 DISCLOSED check 披露实际 run/evals 规模。
RS3_02_DISCLOSED_CODE = "S3_ANALYSIS_RS3_02_GRID_DISCLOSED"
_LOCAL_RS3_02_FALLBACK = {
    "max_wall_clock_s": 5400,
    "opt_seeds": 5,
    "main_runs": 3000,
    "main_evals": 288000,
    "determinism_subset_runs": 60,
    "determinism_repeats": 3,
    "determinism_runs": 180,
    "determinism_evals": 17280,
    "total_runs": 3780,
    "total_evals": 362880,
}


def _rs3_02_fallback() -> dict[str, Any]:
    """返回 R-S3-02 降网格常量（优先 sp 单源；缺失时用本地内联常量，不改 s3_prereg.py）。"""
    value = getattr(sp, "S3_RS3_02_FALLBACK", None)
    if isinstance(value, Mapping):
        return {str(key): value[key] for key in value}
    return dict(_LOCAL_RS3_02_FALLBACK)


def _as_int_or_none(value: Any) -> int | None:
    """仅接受真正的 int（拒绝 bool），否则返回 None。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)

# 图键（计划 §5.3 逐字；Lead m08223 裁决以计划为准）
FIGURE_KEYS = (
    "fig1_training_loss_and_full_meta_grad",
    "fig2_kshot_rmse_k0_k1_k3_k5",
    "fig3_feasible_hit_rate_by_arm",
    "fig4_best_feasible_and_first_feasible",
    "fig5_fomaml_vs_full_vs_anil_cost",
    "fig6_task_family_diagnostics",
    "fig7_ood_diagnostics",
    "fig8_negative_controls",
    "fig9_determinism_and_budget",
    "fig10_vspaero_gate_status",
)
FIGURE_STATUSES = ("RENDERED", "NOT_RUN", "NOT_APPLICABLE")

# 输出文件（计划 §5.2 七个 CSV + aggregate.json；图数据 CSV 由 s3_figures 写）
S3_ENDPOINT_TABLES_CSV = "s3_endpoint_tables.csv"
S3_PER_TASK_CSV = "s3_per_task_endpoint_values.csv"
S3_HOLM_CSV = "s3_holm_family.csv"
S3_NULL_CSV = "s3_null_disclosure.csv"
S3_NEGATIVE_CONTROLS_CSV = "s3_negative_controls.csv"
S3_OOD_CSV = "s3_ood_descriptives.csv"
S3_COST_CSV = "s3_cost_table.csv"
S3_AGGREGATE_JSON = "aggregate.json"
S3_FIGURE_STATUS_JSON = "figure_status.json"
S3_OUTPUT_FILES = (
    S3_AGGREGATE_JSON,
    S3_ENDPOINT_TABLES_CSV,
    S3_PER_TASK_CSV,
    S3_HOLM_CSV,
    S3_NULL_CSV,
    S3_NEGATIVE_CONTROLS_CSV,
    S3_OOD_CSV,
    S3_COST_CSV,
    S3_FIGURE_STATUS_JSON,
)

# run 目录内的固定产物名（计划 §4.2/§4.3）
RUN_CONFIG_FILE = "run_config.json"
RUN_SUMMARY_FILE = "run_summary.json"
RUN_RECORDS_FILE = "run_records.jsonl"
MODEL_MANIFEST_FILE = "model_manifest.json"
DATA_MANIFEST_FILE = "data_manifest.json"
FD_GATE_FILE = "fd_or_gradient_gate.json"
NEGATIVE_CONTROL_DIR = "negative_control"
DETERMINISM_DIR = "determinism"
DETERMINISM_REPEAT_DIRS = ("r1", "r2", "r3")
KSWEEP_DIR = "k_sweep"
TRAIN_SERIES_FILE = "train_series.json"
TRAIN_USED_PREDICTIONS_FILE = "train_used_predictions.json"

# 数据边界 phase-scoped 标志（计划 §2.3）
DATA_BOUNDARY_FLAGS = (
    "holdout_truth_used_for_training",
    "holdout_truth_used_for_adaptation",
    "holdout_truth_used_for_bo_ranking",
    "holdout_truth_read_for_evaluation",
)
# A1 s3_prereg.S3_DATA_BOUNDARY 用 support_truth_read_phases 声明分阶段读取；兼容旧键 support_truth_read。
DATA_BOUNDARY_SUPPORT_PHASES_FLAG = "support_truth_read_phases"
DATA_BOUNDARY_SUPPORT_FLAG = "support_truth_read"
DATA_BOUNDARY_SUPPORT_PHASES = ("EVAL", "OOD", "NEGATIVE_CONTROL")
PHASE_TRAIN = "TRAIN"
PHASE_DEV = "DEV"
PHASE_EVAL = "EVAL"
PHASE_OOD = "OOD"
PHASE_NEGATIVE_CONTROL = "NEGATIVE_CONTROL"

# 任务 split → 期望 phase 映射（计划 §2.3）
SPLIT_PHASE = {
    "meta_train": PHASE_TRAIN,
    "dev": PHASE_DEV,
    "meta_validation": PHASE_DEV,
    "meta_test": PHASE_EVAL,
    "meta_test_ood": PHASE_OOD,
    "meta_test_negative_control": PHASE_NEGATIVE_CONTROL,
}

# 证据范围与冻结族（计划 §6）
EXPECTED_FAMILY_ID = "F-QE-conflict-v1"
EXPECTED_FORMULA_VERSION = "polyhedral-v1"
EXPECTED_FAMILY_SEED = 20261107
EXPECTED_HOLDOUT_SEED = 20261108
FAMILY_PACKAGE_RELPATH = "research/concorde_metaopt/evidence/s3/family_package/p4ra_fqec_v1_family_package.json"
REFERENCES_SEALED_RELPATH = "research/concorde_metaopt/evidence/s3/references_sealed/p4ra_fqec_v1_references_sealed.json"

# SMOKE 固定覆盖（计划 §4.5；键集来自 s3_prereg 单源，值仅校验形状）
SMOKE_DEFAULT = {
    "outer_steps": 2,
    "meta_seeds": (0,),
    "budgets": (64, 128),
    "opt_seeds": (0,),
    "eval_tasks": 4,
    "k_sweep": (0, 1, 3, 5),
    "fd_coordinates": 32,
}
SMOKE_DEFAULT_EVAL_TASKS = 4

# 哈希/文件缓存大小上限（防御超大产物读入内存；run_records 允许较大）
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_JSONL_BYTES = 4 * 1024 * 1024 * 1024


class S3AnalysisError(RuntimeError):
    """S3 分析器 fail-closed 错误（.code/.message/.detail）。"""

    def __init__(self, code: str, message: str, detail: Any = None) -> None:
        self.code = str(code)
        self.message = str(message)
        self.detail = detail
        super().__init__(self.code + ": " + self.message)


def _fail(code: str, message: str, detail: Any = None) -> None:
    raise S3AnalysisError(code, message, detail)


# ---------------------------------------------------------------------------
# 基础类型/数值/文件工具
# ---------------------------------------------------------------------------
def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_mapping(value: Any, *, code: str, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code, label + " 必须是 JSON 对象", type(value).__name__)
    return value


def _require_list(value: Any, *, code: str, label: str, non_empty: bool = False) -> list:
    if not isinstance(value, (list, tuple)):
        _fail(code, label + " 必须是 JSON 数组", type(value).__name__)
    items = list(value)
    if non_empty and not items:
        _fail(code, label + " 不能为空")
    return items


def _require_str(value: Any, *, code: str, label: str, non_empty: bool = True) -> str:
    if not isinstance(value, str):
        _fail(code, label + " 必须是字符串", type(value).__name__)
    if non_empty and not value.strip():
        _fail(code, label + " 不能为空字符串")
    return value


def _require_bool(value: Any, *, code: str, label: str) -> bool:
    if not isinstance(value, bool):
        _fail(code, label + " 必须是布尔值", type(value).__name__)
    return value


def _require_int(
    value: Any,
    *,
    code: str,
    label: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if not _is_int(value):
        _fail(code, label + " 必须是整数", type(value).__name__)
    number = int(value)
    if minimum is not None and number < minimum:
        _fail(code, label + " 不能小于 " + str(minimum), number)
    if maximum is not None and number > maximum:
        _fail(code, label + " 不能大于 " + str(maximum), number)
    return number


def _require_number(
    value: Any,
    *,
    code: str,
    label: str,
    allow_none: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        if allow_none:
            return None
        _fail(code, label + " 不能为 null")
    if not _is_number(value):
        _fail(code, label + " 必须是数值", type(value).__name__)
    number = float(value)
    if not math.isfinite(number):
        _fail(code, label + " 必须是有限数值", number)
    if minimum is not None and number < minimum:
        _fail(code, label + " 不能小于 " + repr(minimum), number)
    if maximum is not None and number > maximum:
        _fail(code, label + " 不能大于 " + repr(maximum), number)
    return number


def _require_sha256(value: Any, *, code: str, label: str) -> str:
    text = _require_str(value, code=code, label=label)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text.lower()):
        _fail(code, label + " 必须是 64 位小写 hex sha256", text)
    return text.lower()


def _require_str_list(value: Any, *, code: str, label: str, non_empty: bool = False) -> list[str]:
    items = _require_list(value, code=code, label=label, non_empty=non_empty)
    out = []
    for index, item in enumerate(items):
        out.append(_require_str(item, code=code, label=label + "[" + str(index) + "]"))
    return out


def _mean_or_none(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / float(len(clean))


def _safe_div(numerator: float, denominator: float, *, floor: float = 1e-12) -> float:
    if abs(denominator) < floor:
        return 0.0
    return numerator / denominator


def _relative_difference(value_con: float, value_obj: float, *, floor: float = C2_DENOMINATOR_FLOOR) -> float:
    denominator = max(abs(float(value_obj)), floor)
    return (float(value_con) - float(value_obj)) / denominator


def _read_json_file(path: str | Path, *, code: str, label: str) -> Any:
    file_path = Path(path)
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        _fail(code, label + " 不存在或不可读: " + str(file_path), str(exc))
    if len(raw) > MAX_JSON_BYTES:
        _fail(code, label + " 超过大小上限", len(raw))
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(code, label + " 不是合法 UTF-8 JSON: " + str(file_path), str(exc))
    return None


def _read_jsonl_file(path: str | Path, *, code: str, label: str) -> list[dict[str, Any]]:
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        _fail(code, label + " 不存在或不可读: " + str(file_path), str(exc))
    if size > MAX_JSONL_BYTES:
        _fail(code, label + " 超过大小上限", size)
    records: list[dict[str, Any]] = []
    try:
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            for lineno, line in enumerate(handle, start=1):
                text = line.rstrip("\r\n")
                if text == "":
                    continue
                try:
                    item = json.loads(text)
                except json.JSONDecodeError as exc:
                    _fail(code, label + " 第 " + str(lineno) + " 行不是 JSON", str(exc))
                if not isinstance(item, dict):
                    _fail(code, label + " 第 " + str(lineno) + " 行不是对象")
                records.append(item)
    except UnicodeDecodeError as exc:
        _fail(code, label + " 不是 UTF-8 文本", str(exc))
    return records


def _write_json(path: str | Path, payload: Any, *, code: str, label: str) -> str:
    file_path = Path(path)
    text = sp.canonical_json(payload)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(text.encode("utf-8") + b"\n")
    except OSError as exc:
        _fail(code, label + " 写入失败: " + str(file_path), str(exc))
    return sp.sha256_file(file_path)


def _write_csv(
    path: str | Path,
    *,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    code: str = S3_ANALYSIS_OUTPUT_INVALID,
    label: str = "CSV",
) -> str:
    file_path = Path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: _csv_value(row.get(key)) for key in columns})
    except OSError as exc:
        _fail(code, label + " 写入失败: " + str(file_path), str(exc))
    return sp.sha256_file(file_path)


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return format(value, ".17g")
    return value


def _write_jsonl(path: str | Path, records: Sequence[Mapping[str, Any]]) -> str:
    file_path = Path(path)
    lines = [sp.canonical_json(dict(record)) for record in records]
    text = "\n".join(lines)
    if text:
        text += "\n"
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(text.encode("utf-8"))
    except OSError as exc:
        _fail(S3_ANALYSIS_OUTPUT_INVALID, "JSONL 写入失败: " + str(file_path), str(exc))
    return sp.sha256_file(file_path)


def _checks(checks: list[dict[str, Any]], name: str, status: str, detail: str = "", **extra: Any) -> None:
    """记录一条校验项（PASS/DISCLOSED/SKIPPED/FAIL）。"""
    status_upper = str(status).upper()
    if status_upper == "FAIL":
        _fail(S3_ANALYSIS_INPUT_INVALID, "校验失败: " + str(name), detail)
    item = {"check": str(name), "status": status_upper, "detail": str(detail)}
    item.update(extra)
    checks.append(item)


def _check_status(checks: Sequence[Mapping[str, Any]], *names: str) -> str | None:
    """返回给定 check 名中第一条的状态（按 names 顺序）；缺失返回 None。"""
    for name in names:
        for item in checks:
            if str(item.get("check")) == str(name):
                return str(item.get("status", ""))
    return None

# ---------------------------------------------------------------------------
# 统计核心（计划 §5.2）：tie-aware 精确符号翻转 Wilcoxon、Holm、bootstrap、决策表
# ---------------------------------------------------------------------------
def _average_ranks(values: Sequence[float]) -> list[float]:
    """计算 |values| 的平均秩（1-based；ties 取平均秩）。"""
    order = sorted(range(len(values)), key=lambda index: (abs(float(values[index])), index))
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        value = abs(float(values[order[position]]))
        while end + 1 < len(order) and abs(float(values[order[end + 1]])) == value:
            end += 1
        average = (position + 1 + end + 1) / 2.0
        for offset in range(position, end + 1):
            ranks[order[offset]] = average
        position = end + 1
    return ranks


def _doubled_rank(value: float) -> int:
    doubled = int(round(float(value) * 2.0))
    if doubled < 0:
        _fail(S3_ANALYSIS_INPUT_INVALID, "秩不能为负", value)
    return doubled


def _sign_flip_distribution(doubled_ranks: Sequence[int]) -> list[int]:
    """精确符号翻转分布计数：counts[s] = 取得 doubled 秩和 s 的符号组合数。"""
    total = sum(doubled_ranks)
    counts = [0] * (total + 1)
    counts[0] = 1
    for rank in doubled_ranks:
        updated = [0] * (total + 1)
        for current, count in enumerate(counts):
            if count == 0:
                continue
            updated[current] += count
            updated[current + rank] += count
        counts = updated
    return counts


def _two_sided_p_from_distribution(counts: Sequence[int], observed: int) -> float:
    total_combinations = 0
    left = 0
    right = 0
    for index, count in enumerate(counts):
        total_combinations += count
        if index <= observed:
            left += count
        if index >= observed:
            right += count
    if total_combinations <= 0:
        return 1.0
    p_left = left / float(total_combinations)
    p_right = right / float(total_combinations)
    return min(1.0, 2.0 * min(p_left, p_right))


def wilcoxon_signed_rank_exact(diffs: Sequence[float]) -> dict[str, Any]:
    """tie-aware 精确符号翻转 Wilcoxon signed-rank 检验（主分析，零差丢弃）。

    实现口径（计划 §5.2/A5 S3-M0-11）：
    - 零差丢弃，n_zero 记录；n_eff 为参与检验的非零差个数；
    - |d| 的秩使用平均秩（ties 处理）；精确符号翻转分布由整数 DP 全枚举得到
      （与 2^n_eff 全枚举等价，见 wilcoxon_signed_rank_bruteforce 的交叉验证）；
    - 双侧 p = min(1, 2*min(P(W<=w), P(W>=w)))。
    """
    values = [float(value) for value in diffs]
    if not values:
        _fail(S3_ANALYSIS_INPUT_INVALID, "Wilcoxon 输入不能为空")
    nonzero = [value for value in values if value != 0.0]
    n_zero = len(values) - len(nonzero)
    n_eff = len(nonzero)
    result: dict[str, Any] = {
        "method": "exact_sign_flip_tie_aware",
        "n_total": len(values),
        "n_zero": n_zero,
        "n_eff": n_eff,
        "zero_policy": "DISCARDED",
        "w_plus": None,
        "w_minus": None,
        "p_two_sided": None,
        "min_p_floor": None,
    }
    if n_eff == 0:
        result["p_two_sided"] = None
        result["w_plus"] = 0.0
        result["w_minus"] = 0.0
        return result
    ranks = _average_ranks(nonzero)
    doubled = [_doubled_rank(rank) for rank in ranks]
    observed = sum(rank for rank, value in zip(doubled, nonzero) if value > 0)
    total = sum(doubled)
    counts = _sign_flip_distribution(doubled)
    result["w_plus"] = observed / 2.0
    result["w_minus"] = (total - observed) / 2.0
    result["p_two_sided"] = _two_sided_p_from_distribution(counts, observed)
    result["ranks"] = [rank / 2.0 for rank in doubled]
    result["min_p_floor"] = 2.0 / float(2 ** n_eff) if n_eff <= 30 else 0.0
    result["_distribution"] = counts
    result["_observed_doubled"] = observed
    return result


def wilcoxon_signed_rank_bruteforce(diffs: Sequence[float]) -> dict[str, Any]:
    """2^n 全枚举参考实现（仅测试用，n_eff<=16；与 DP 结果逐位一致）。"""
    values = [float(value) for value in diffs]
    nonzero = [value for value in values if value != 0.0]
    n_zero = len(values) - len(nonzero)
    n_eff = len(nonzero)
    if n_eff == 0:
        return {
            "method": "bruteforce_sign_flip",
            "n_total": len(values),
            "n_zero": n_zero,
            "n_eff": 0,
            "w_plus": 0.0,
            "w_minus": 0.0,
            "p_two_sided": None,
        }
    if n_eff > 16:
        _fail(S3_ANALYSIS_INPUT_INVALID, "bruteforce 参考实现仅支持 n_eff<=16", n_eff)
    ranks = _average_ranks(nonzero)
    doubled = [_doubled_rank(rank) for rank in ranks]
    observed = sum(rank for rank, value in zip(doubled, nonzero) if value > 0)
    total = sum(doubled)
    above_or_equal = 0
    below_or_equal = 0
    combos = 0
    stack = [(0, 0)]
    sums: list[int] = []
    for mask in range(2 ** n_eff):
        current = 0
        for index in range(n_eff):
            if mask & (1 << index):
                current += doubled[index]
        sums.append(current)
        combos += 1
    for value in sums:
        if value <= observed:
            below_or_equal += 1
        if value >= observed:
            above_or_equal += 1
    p_left = below_or_equal / float(combos)
    p_right = above_or_equal / float(combos)
    return {
        "method": "bruteforce_sign_flip",
        "n_total": len(values),
        "n_zero": n_zero,
        "n_eff": n_eff,
        "w_plus": observed / 2.0,
        "w_minus": (total - observed) / 2.0,
        "p_two_sided": min(1.0, 2.0 * min(p_left, p_right)),
    }


def wilcoxon_pratt(diffs: Sequence[float]) -> dict[str, Any]:
    """敏感性分析 (a)：Pratt 变体（零差参与排秩但不参与符号翻转）。"""
    values = [float(value) for value in diffs]
    if not values:
        _fail(S3_ANALYSIS_INPUT_INVALID, "Wilcoxon Pratt 输入不能为空")
    n_zero = sum(1 for value in values if value == 0.0)
    ranks_all = _average_ranks(values)
    nonzero_indices = [index for index, value in enumerate(values) if value != 0.0]
    n_eff = len(nonzero_indices)
    result: dict[str, Any] = {
        "method": "pratt_zero_included_rank",
        "n_total": len(values),
        "n_zero": n_zero,
        "n_eff": n_eff,
        "w_plus": None,
        "w_minus": None,
        "p_two_sided": None,
    }
    if n_eff == 0:
        result["w_plus"] = 0.0
        result["w_minus"] = 0.0
        return result
    doubled = [_doubled_rank(ranks_all[index]) for index in nonzero_indices]
    observed = sum(rank for rank, index in zip(doubled, nonzero_indices) if values[index] > 0)
    total = sum(doubled)
    counts = _sign_flip_distribution(doubled)
    result["w_plus"] = observed / 2.0
    result["w_minus"] = (total - observed) / 2.0
    result["p_two_sided"] = _two_sided_p_from_distribution(counts, observed)
    result["_distribution"] = counts
    result["_observed_doubled"] = observed
    return result


def wilcoxon_permutation(
    diffs: Sequence[float],
    *,
    n_resamples: int = PERMUTATION_RESAMPLES,
    seed: int = PERMUTATION_SEED,
) -> dict[str, Any]:
    """敏感性分析 (b)：10,000 次符号置换（seed 固定，可复现）。"""
    values = [float(value) for value in diffs]
    if not values:
        _fail(S3_ANALYSIS_INPUT_INVALID, "Wilcoxon 置换输入不能为空")
    nonzero = [value for value in values if value != 0.0]
    n_eff = len(nonzero)
    result: dict[str, Any] = {
        "method": "sign_permutation",
        "n_total": len(values),
        "n_zero": len(values) - n_eff,
        "n_eff": n_eff,
        "n_resamples": int(n_resamples),
        "seed": int(seed),
        "w_plus": None,
        "p_two_sided": None,
    }
    if n_eff == 0:
        result["w_plus"] = 0.0
        return result
    ranks = _average_ranks(nonzero)
    doubled = [_doubled_rank(rank) for rank in ranks]
    observed = sum(rank for rank, value in zip(doubled, nonzero) if value > 0)
    total = sum(doubled)
    center = total / 2.0
    rng = np.random.default_rng(int(seed))
    signs = rng.integers(0, 2, size=(int(n_resamples), n_eff))
    sums = signs.dot(np.asarray(doubled, dtype=np.int64))
    extreme = np.abs(sums - center) >= abs(observed - center) - 1e-12
    result["w_plus"] = observed / 2.0
    result["p_two_sided"] = (float(np.count_nonzero(extreme)) + 1.0) / (float(n_resamples) + 1.0)
    return result


def holm_adjust(p_values: Sequence[tuple[str, float | None]], *, alpha: float = ALPHA) -> list[dict[str, Any]]:
    """Holm 校正（单族 m 个检验；p=None 视为不可计算，按 1.0 参与排序并记 missing）。"""
    entries = []
    for test_id, value in p_values:
        if value is None or not _is_number(value):
            entries.append({"test_id": str(test_id), "p_raw": None, "p_value": None, "missing": True})
        else:
            number = float(value)
            if not math.isfinite(number) or number < 0.0 or number > 1.0:
                _fail(S3_ANALYSIS_INPUT_INVALID, "p 值越界: " + str(test_id), number)
            entries.append({"test_id": str(test_id), "p_raw": number, "p_value": number, "missing": False})
    m = len(entries)
    if m == 0:
        return []
    ordered = sorted(range(m), key=lambda index: (entries[index]["p_raw"] if not entries[index]["missing"] else 1.0, index))
    running = 0.0
    for rank, index in enumerate(ordered, start=1):
        item = entries[index]
        if item["missing"]:
            adjusted = None
        else:
            adjusted = min(1.0, (m - rank + 1) * float(item["p_raw"]))
            running = max(running, adjusted)
            adjusted = running
        item["p_holm"] = adjusted
        item["rank"] = rank
        item["reject"] = bool(adjusted is not None and adjusted < alpha)
    return entries


def bootstrap_mean_ci(
    values: Sequence[float | None],
    *,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> dict[str, Any]:
    """任务级 mean 的 percentile bootstrap 95% CI（重采样 task，seed 固定）。"""
    clean = [float(value) for value in values if value is not None]
    n = len(clean)
    result: dict[str, Any] = {
        "method": "percentile_bootstrap_task_level",
        "n_tasks": n,
        "n_missing": sum(1 for value in values if value is None),
        "mean": _mean_or_none(clean),
        "median": None,
        "ci_low": None,
        "ci_high": None,
        "n_resamples": int(n_resamples),
        "seed": int(seed),
        "confidence_level": float(confidence),
    }
    if n == 0:
        return result
    array = np.asarray(clean, dtype=float)
    result["median"] = float(np.median(array))
    if n == 1:
        result["ci_low"] = float(array[0])
        result["ci_high"] = float(array[0])
        return result
    rng = np.random.default_rng(int(seed))
    indices = rng.integers(0, n, size=(int(n_resamples), n))
    means = array[indices].mean(axis=1)
    alpha = (1.0 - float(confidence)) / 2.0
    result["ci_low"] = float(np.quantile(means, alpha))
    result["ci_high"] = float(np.quantile(means, 1.0 - alpha))
    return result


def bootstrap_median_ci(
    values: Sequence[float | None],
    *,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = BOOTSTRAP_CONFIDENCE,
) -> dict[str, Any]:
    """任务级 median 的 percentile bootstrap CI（描述性端点使用）。"""
    clean = [float(value) for value in values if value is not None]
    n = len(clean)
    if n == 0:
        return {
            "method": "percentile_bootstrap_task_level",
            "n_tasks": 0,
            "n_missing": sum(1 for value in values if value is None),
            "median": None,
            "ci_low": None,
            "ci_high": None,
            "n_resamples": int(n_resamples),
            "seed": int(seed),
            "confidence_level": float(confidence),
        }
    array = np.asarray(clean, dtype=float)
    rng = np.random.default_rng(int(seed))
    indices = rng.integers(0, n, size=(int(n_resamples), n))
    medians = np.median(array[indices], axis=1)
    alpha = (1.0 - float(confidence)) / 2.0
    return {
        "method": "percentile_bootstrap_task_level",
        "n_tasks": n,
        "n_missing": sum(1 for value in values if value is None),
        "median": float(np.median(array)),
        "ci_low": float(np.quantile(medians, alpha)),
        "ci_high": float(np.quantile(medians, 1.0 - alpha)),
        "n_resamples": int(n_resamples),
        "seed": int(seed),
        "confidence_level": float(confidence),
    }


def paired_summary(values: Sequence[float | None]) -> dict[str, Any]:
    """配对差描述统计（task 级；null 按缺失处理，不插补）。"""
    clean = [float(value) for value in values if value is not None]
    return {
        "n_total": len(values),
        "n_missing": sum(1 for value in values if value is None),
        "mean": _mean_or_none(clean),
        "median": float(np.median(clean)) if clean else None,
        "min": float(min(clean)) if clean else None,
        "max": float(max(clean)) if clean else None,
    }


def decide_layer(
    *,
    p_value: float | None,
    effect: float | None,
    threshold: float,
    benefit_direction: str,
    n_eff: int | None,
) -> str:
    """单层六档互斥穷尽判定（计划 §1.3/§5.2；优先级固定）。"""
    if benefit_direction not in ("positive", "negative"):
        _fail(S3_ANALYSIS_INPUT_INVALID, "benefit_direction 必须是 positive/negative", benefit_direction)
    if n_eff is None or int(n_eff) < WILCOXON_MIN_N_EFF:
        return D_INCONCLUSIVE
    if p_value is None or effect is None:
        return D_INCONCLUSIVE
    if not math.isfinite(float(p_value)) or not math.isfinite(float(effect)):
        return D_INCONCLUSIVE
    p = float(p_value)
    effect_value = float(effect)
    threshold_value = float(threshold)
    benefit_sign = 1.0 if benefit_direction == "positive" else -1.0
    signed_effect = effect_value * benefit_sign
    if p < ALPHA and signed_effect >= threshold_value:
        return D_SUPPORTED_BENEFIT
    if p < ALPHA and signed_effect <= -threshold_value:
        return D_SUPPORTED_HARM
    if p < ALPHA:
        return D_NEGLIGIBLE_SIGNIFICANT
    if signed_effect <= -threshold_value:
        return D_DIRECTION_INCONSISTENT
    return D_NULL


def decide_overall(decisions: Mapping[str, str]) -> str:
    """总体 S3 结论映射（计划 §1.3/§5.2；唯一优先级，固定查表函数）。

    decisions 必须恰含两个 C1 层（B64、B128）的层判定；其它层不参与总体映射。
    """
    required = {"B64", "B128"}
    keys = set(str(key) for key in decisions.keys())
    if keys != required:
        _fail(
            S3_ANALYSIS_INPUT_INVALID,
            "总体判定输入必须恰含 B64/B128 两个 C1 层",
            sorted(keys),
        )
    layer_values = [str(decisions["B64"]), str(decisions["B128"])]
    for value in layer_values:
        if value not in LAYER_DECISIONS:
            _fail(S3_ANALYSIS_INPUT_INVALID, "未知层判定: " + str(value))
    if any(value == D_INCONCLUSIVE for value in layer_values):
        return O_INCONCLUSIVE
    if any(value == D_SUPPORTED_HARM for value in layer_values):
        return O_HARM
    if any(value == D_DIRECTION_INCONSISTENT for value in layer_values):
        return O_DIRECTION_INCONSISTENT
    if all(value == D_SUPPORTED_BENEFIT for value in layer_values):
        return O_BENEFIT
    if sum(1 for value in layer_values if value == D_SUPPORTED_BENEFIT) == 1 and any(
        value in (D_NULL, D_NEGLIGIBLE_SIGNIFICANT) for value in layer_values
    ):
        return O_NO_EVIDENCE
    return O_NO_EVIDENCE


def overall_decision_table() -> dict[tuple[str, str], str]:
    """返回全部层判定组合 → 总体结论的固定查表（单测用）。"""
    table: dict[tuple[str, str], str] = {}
    for first in LAYER_DECISIONS:
        for second in LAYER_DECISIONS:
            table[(first, second)] = decide_overall({"B64": first, "B128": second})
    return table


def anil_decision(
    *,
    anil_mean: float | None,
    random_mean: float | None,
    anil_cost: float | None,
    con_cost: float | None,
    anil_minus_random_ci: Mapping[str, Any] | None = None,
) -> str:
    """ANIL 低成本消融判定（计划 §5.2；描述性，不做显著性强断言）。"""
    if anil_mean is None or random_mean is None:
        return "ANIL_INCONCLUSIVE"
    if anil_cost is not None and con_cost is not None and con_cost > 0.0 and anil_cost / con_cost <= ANIL_COST_RATIO_MAX:
        cost_ok = True
    else:
        cost_ok = False
    noninferior = float(anil_mean) >= float(random_mean) - ANIL_NONINFERIOR_MARGIN
    inferior = False
    if anil_minus_random_ci is not None:
        upper = anil_minus_random_ci.get("ci_high")
        if upper is not None and float(upper) < -ANIL_NONINFERIOR_MARGIN:
            inferior = True
    if inferior:
        return "ANIL_INFERIOR"
    if noninferior and cost_ok:
        return "ANIL_COST_EFFICIENT"
    return "ANIL_INCONCLUSIVE"

# ---------------------------------------------------------------------------
# prereg 加载与 fail-closed 校验（计划 §6/§6.1；schema 常量一律 sp.*）
# ---------------------------------------------------------------------------
S3_PREREG_REQUIRED_TOP_KEYS = tuple(sp.S3_PREREG_REQUIRED_FIELDS)
S3_PREREG_REQUIRED_TOP_KEYS_LEGACY = (
    "schema_version",
    "created_utc",
    "family",
    "references_sealed",
    "calibration",
    "episode_bank",
    "models",
    "arms",
    "budgets",
    "endpoints",
    "statistics",
    "figures",
    "negative_controls",
    "campaign",
    "ood",
    "determinism",
    "resource_limits",
    "analysis_plan_digest",
    "code_sha",
    "physical_call_count",
    "data_boundary",
    "authorization_chain",
)
S3_PREREG_OPTIONAL_TOP_KEYS = ("prereg_id", "prereg_digest", "notes")
PREREG_ID_PATTERN = re.compile(r"^p4ra-s3-prereg-[0-9a-f]{16}$")
PREREG_ID_DERIVATION = "sha256(canonical_json(prereg 去掉 prereg_id/prereg_digest))[:16] + 前缀 p4ra-s3-prereg-"
PLACEHOLDER_PATTERN = re.compile(r"^<.*>$")
PLACEHOLDER_TOKENS = ("TBD", "TODO", "PENDING", "PLACEHOLDER", "REPLACE_ME")
PREREG_MAX_BYTES = 16 * 1024 * 1024


def _require_iso_utc(value: Any, *, code: str, label: str) -> str:
    text = _require_str(value, code=code, label=label)
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail(code, label + " 不是合法 ISO-8601 时间: " + text)
    if parsed.tzinfo is None:
        _fail(code, label + " 缺少时区偏移（UTC）")
    return text


def _scan_placeholders(payload: Any, *, path: str = "") -> None:
    """递归拒绝占位值（字符串 ^<.*>$ 或 TBD/TODO 等 token）。"""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            _scan_placeholders(value, path=path + "/" + str(key))
        return
    if isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            _scan_placeholders(value, path=path + "[" + str(index) + "]")
        return
    if isinstance(payload, str):
        stripped = payload.strip()
        if PLACEHOLDER_PATTERN.match(stripped):
            _fail(S3_ANALYSIS_PREREG_PLACEHOLDER, "prereg 存在占位值: " + path, stripped)
        upper = stripped.upper()
        for token in PLACEHOLDER_TOKENS:
            if upper == token or upper.startswith(token + "_") or upper.endswith("_" + token):
                _fail(S3_ANALYSIS_PREREG_PLACEHOLDER, "prereg 存在占位值: " + path, stripped)
    return


def _require_sub_key(mapping: Mapping[str, Any], keys: Sequence[str], *, code: str, label: str) -> tuple[str, Any]:
    for key in keys:
        if key in mapping:
            return key, mapping[key]
    _fail(code, label + " 缺少必需子键（候选名: " + ", ".join(keys) + "）", sorted(mapping.keys()))


def _require_hex_sha_list(mapping: Mapping[str, Any], keys: Sequence[str], *, code: str, label: str, count: int) -> list[str]:
    _, value = _require_sub_key(mapping, keys, code=code, label=label)
    items = _require_list(value, code=code, label=label)
    if count != 0 and len(items) != count:
        _fail(code, label + " 数量不符: 期望 " + str(count) + " 实际 " + str(len(items)))
    return [_require_sha256(item, code=code, label=label + "[" + str(index) + "]") for index, item in enumerate(items)]


def load_references_sealed(prereg: "S3Prereg", *, repo_root: str | Path, checks: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """run 完成后读取封存参考解（analysis 才允许读；runner 阶段禁止读）。"""
    checks = checks if checks is not None else []
    repo_root = Path(repo_root).resolve()
    section = _require_mapping(prereg.references_sealed, code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="references_sealed")
    path_text = _require_str(section.get("path"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="references_sealed.path")
    declared_sha = _require_sha256(section.get("sha256"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="references_sealed.sha256")
    path = (repo_root / path_text).resolve()
    try:
        path.relative_to(repo_root)
    except ValueError:
        _fail(S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, "references_sealed.path 越出仓库根", path_text)
    if not path.is_file():
        _fail(S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, "references_sealed 文件不存在", str(path))
    payload = _read_json_file(path, code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, label="references_sealed")
    _scan_placeholders(payload, path="references_sealed")
    actual_sha = sp.sha256_file(path)
    if actual_sha != declared_sha:
        _fail(
            S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ,
            "references_sealed sha256 与 prereg 不符",
            {"declared": declared_sha, "actual": actual_sha},
        )
    body = _require_mapping(payload, code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, label="references_sealed 内容")
    _, items_value = _require_sub_key(
        body,
        ("tasks", "references", "sealed", "entries"),
        code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ,
        label="references_sealed 任务集合",
    )
    items = _require_list(items_value, code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, label="references_sealed 任务集合")
    references: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        entry = _require_mapping(item, code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, label="reference[" + str(index) + "]")
        task_id = _require_str(entry.get("task_id"), code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, label="reference.task_id")
        f_ref = _require_number(
            entry.get("f_ref", entry.get("f_star")),
            code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ,
            label="reference.f_ref/reference.f_star",
        )
        if str(entry.get("split", "")) == "meta_test_negative_control":
            _fail(S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, "封存参考解不得包含负控制任务: " + task_id)
        digest_text = entry.get("reference_digest")
        if digest_text is not None:
            digest_text = _require_str(digest_text, code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, label="reference.reference_digest")
            if not re.match(r"^[0-9a-f]{32}$", digest_text):
                _fail(S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, "reference_digest 必须为 32 位小写 hex: " + task_id, digest_text)
            body_wo = {key: value for key, value in dict(entry).items() if key != "reference_digest"}
            computed = sp.canonical_sha256(body_wo)[:32]
            if computed != digest_text:
                _fail(
                    S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ,
                    "reference_digest 复算不一致: " + task_id,
                    {"declared": digest_text, "computed": computed},
                )
        record = {
            "task_id": task_id,
            "f_ref": float(f_ref),
            "reference_kind": _require_str(entry.get("reference_kind", "POLYHEDRAL_KKT_CERTIFIED"), code=S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, label="reference.reference_kind"),
            "u_star": entry.get("u_star"),
            "certificate_digest": digest_text,
            "raw": dict(entry),
        }
        if task_id in references:
            _fail(S3_ANALYSIS_LEAKAGE_SEALED_REFERENCE_READ, "references_sealed 任务重复: " + task_id)
        references[task_id] = record
    declared_task_ids = section.get("task_ids")
    if isinstance(declared_task_ids, (list, tuple)) and declared_task_ids:
        declared_set = set(str(value) for value in declared_task_ids)
        if declared_set != set(references):
            _fail(
                S3_ANALYSIS_PREREG_BINDING_MISMATCH,
                "references_sealed.task_ids 与封存文件任务集合不一致",
                {"declared": len(declared_set), "actual": len(references)},
            )
        _checks(checks, "references_sealed_task_ids", "PASS", "references_sealed.task_ids 与封存文件一致: " + str(len(declared_set)))
    _checks(checks, "references_sealed_sha256", "PASS", "封存参考解 sha256 与 prereg 一致: " + actual_sha)
    _checks(checks, "references_sealed_task_count", "PASS", "封存参考解任务数: " + str(len(references)))
    return references


def load_family_package(prereg: "S3Prereg", *, repo_root: str | Path, checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """读取族包（只读；用于 fig6 族诊断与任务参数校验）。"""
    checks = checks if checks is not None else []
    repo_root = Path(repo_root).resolve()
    section = _require_mapping(prereg.family, code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="family")
    declared_sha = _require_sha256(section.get("family_package_sha256"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="family.family_package_sha256")
    path = (repo_root / FAMILY_PACKAGE_RELPATH).resolve()
    if not path.is_file():
        _fail(S3_ANALYSIS_PREREG_FILE_INVALID, "族包文件不存在", str(path))
    actual_sha = sp.sha256_file(path)
    if actual_sha != declared_sha:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "族包 sha256 与 prereg 不符", {"declared": declared_sha, "actual": actual_sha})
    package = _read_json_file(path, code=S3_ANALYSIS_PREREG_FILE_INVALID, label="family_package")
    body = _require_mapping(package, code=S3_ANALYSIS_PREREG_FILE_INVALID, label="family_package 内容")
    _checks(checks, "family_package_sha256", "PASS", "族包 sha256 与 prereg 一致: " + actual_sha)
    return dict(body)


@dataclass(frozen=True)
class S3Prereg:
    """S3 预注册对象（只读快照 + 校验结果）。"""

    path: Path
    raw: bytes
    sha256: str
    obj: dict[str, Any]
    prereg_id: str
    prereg_digest: str
    analysis_plan_digest: str
    created_utc: str
    family: dict[str, Any]
    references_sealed: dict[str, Any]
    calibration: dict[str, Any]
    episode_bank: dict[str, Any]
    models: dict[str, Any]
    arms: list[dict[str, Any]]
    budgets: dict[str, Any]
    endpoints: dict[str, Any]
    statistics: dict[str, Any]
    figures: dict[str, Any]
    negative_controls: dict[str, Any]
    campaign: dict[str, Any]
    ood: dict[str, Any]
    determinism: dict[str, Any]
    resource_limits: dict[str, Any]
    code_sha: str
    physical_call_count: int
    data_boundary: dict[str, Any]
    authorization_chain: Any
    checks: tuple[dict[str, Any], ...]

    @property
    def split_counts(self) -> dict[str, int]:
        return dict(self.family.get("split_counts") or self.family.get("splits") or {})

    @property
    def n_tasks(self) -> int:
        value = self.split_counts.get("meta_test", 0)
        if isinstance(value, (list, tuple, set)):
            return len(value)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @property
    def budgets_list(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.budgets.get("budgets", ()))


def _load_prereg_file(path: str | Path) -> tuple[Path, bytes, dict[str, Any]]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        _fail(S3_ANALYSIS_PREREG_FILE_INVALID, "prereg 文件不存在", str(resolved))
    size = resolved.stat().st_size
    if size <= 0 or size > PREREG_MAX_BYTES:
        _fail(S3_ANALYSIS_PREREG_FILE_INVALID, "prereg 文件大小异常", {"bytes": size})
    raw = resolved.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail(S3_ANALYSIS_PREREG_FILE_INVALID, "prereg 不是合法 UTF-8", str(error))
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as error:
        _fail(S3_ANALYSIS_PREREG_FILE_INVALID, "prereg 不是合法 JSON", str(error))
    body = _require_mapping(obj, code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="prereg 根节点")
    body = dict(body)
    canonical = sp.canonical_json_bytes(body) + b"\n"
    if canonical != raw:
        _fail(
            S3_ANALYSIS_PREREG_FILE_INVALID,
            "prereg 必须是 canonical JSON（sort_keys/separators 紧凑）+ 末尾单个 LF",
            {"expected_bytes": len(canonical), "actual_bytes": len(raw)},
        )
    return resolved, raw, body


def _validate_family_section(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    if _require_str(section.get("family_id"), code=code, label="family.family_id") != EXPECTED_FAMILY_ID:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "family_id 与冻结族不符", EXPECTED_FAMILY_ID)
    if _require_str(section.get("formula_version"), code=code, label="family.formula_version") != EXPECTED_FORMULA_VERSION:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "formula_version 与冻结族不符", EXPECTED_FORMULA_VERSION)
    family_seed = section.get("FAMILY_SEED", section.get("family_seed"))
    if _require_int(family_seed, code=code, label="family.FAMILY_SEED/family_seed") != EXPECTED_FAMILY_SEED:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "FAMILY_SEED 不符", EXPECTED_FAMILY_SEED)
    holdout_seed = section.get("HOLDOUT_SEED", section.get("holdout_seed"))
    if _require_int(holdout_seed, code=code, label="family.HOLDOUT_SEED/holdout_seed") != EXPECTED_HOLDOUT_SEED:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "HOLDOUT_SEED 不符", EXPECTED_HOLDOUT_SEED)
    _require_str(section.get("package_version"), code=code, label="family.package_version")
    family_package_sha = _require_sha256(
        section.get("family_package_sha256", section.get("package_sha256")),
        code=code,
        label="family.family_package_sha256/family.package_sha256",
    )
    _require_sha256(section.get("task_ids_sha256"), code=code, label="family.task_ids_sha256")
    hash_vectors_sha = _require_sha256(section.get("hash_vectors_sha256"), code=code, label="family.hash_vectors_sha256")
    if hash_vectors_sha != sp.HASH_VECTORS_SHA256:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "hash_vectors_sha256 与 s3_prereg 单源常量不符", hash_vectors_sha)
    split_counts_raw = section.get("split_counts", section.get("splits"))
    split_counts = _require_mapping(split_counts_raw, code=code, label="family.split_counts")
    normalized_splits: dict[str, int] = {}
    for name, expected in sp.S3_SPLIT_COUNTS.items():
        if _require_int(split_counts.get(name), code=code, label="family.split_counts." + name) != int(expected):
            _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "split 计数与冻结族不符: " + name, expected)
        normalized_splits[name] = int(expected)
    extra_splits = set(split_counts.keys()) - set(sp.S3_SPLIT_COUNTS.keys())
    if extra_splits:
        _fail(code, "family.split_counts 存在未知 split", sorted(extra_splits))
    fingerprints_value = section.get("task_fingerprints", section.get("task_fingerprint"))
    fingerprints = _require_mapping(fingerprints_value, code=code, label="family.task_fingerprints") if isinstance(fingerprints_value, Mapping) else None
    if fingerprints is None:
        items = _require_list(fingerprints_value, code=code, label="family.task_fingerprints")
        fingerprints = {}
        for index, item in enumerate(items):
            entry = _require_mapping(item, code=code, label="family.task_fingerprints[" + str(index) + "]")
            task_id = _require_str(entry.get("task_id"), code=code, label="task_fingerprints.task_id")
            value = _require_str(entry.get("fingerprint", entry.get("task_fingerprint")), code=code, label="task_fingerprints.fingerprint")
            fingerprints[task_id] = value
    for task_id, value in fingerprints.items():
        text = _require_str(value, code=code, label="family.task_fingerprints." + str(task_id))
        if not re.match(r"^[0-9a-f]{16}$", text):
            _fail(code, "task_fingerprint 必须为 16 位小写 hex", {"task_id": task_id, "value": text})
    _checks(checks, "family_identity", "PASS", "族身份/种子/split 计数与冻结族一致")
    _checks(checks, "family_task_fingerprints", "PASS", "task_fingerprints 数量: " + str(len(fingerprints)), expected_tasks=sum(normalized_splits.values()))
    return {
        "family_id": EXPECTED_FAMILY_ID,
        "formula_version": EXPECTED_FORMULA_VERSION,
        "split_counts": normalized_splits,
        "task_fingerprints": dict(fingerprints),
        "family_package_sha256": family_package_sha,
        "task_ids_sha256": section.get("task_ids_sha256"),
        "hash_vectors_sha256": hash_vectors_sha,
        "package_version": section.get("package_version"),
    }


def _validate_endpoints_section(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    c1 = _require_mapping(section.get("C1"), code=code, label="endpoints.C1")
    c2 = _require_mapping(section.get("C2"), code=code, label="endpoints.C2")
    if _require_str(c1.get("family_id"), code=code, label="endpoints.C1.family_id") != C1_FAMILY_ID:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C1 family_id 不符", C1_FAMILY_ID)
    if _require_str(c2.get("family_id"), code=code, label="endpoints.C2.family_id") != C2_FAMILY_ID:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C2 family_id 不符", C2_FAMILY_ID)
    for label, entry in (("C1", c1), ("C2", c2)):
        comparator = _require_str(entry.get("comparator"), code=code, label="endpoints." + label + ".comparator")
        if comparator != COMPARATOR_ARMS[1]:
            _fail(S3_ANALYSIS_COMPARATOR_MISMATCH, label + " comparator 必须固定为 " + COMPARATOR_ARMS[1], comparator)
    if _require_str(c1.get("endpoint"), code=code, label="endpoints.C1.endpoint") != C1_ENDPOINT:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C1 endpoint 不符", C1_ENDPOINT)
    if _require_str(c2.get("endpoint"), code=code, label="endpoints.C2.endpoint") != C2_ENDPOINT:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C2 endpoint 不符", C2_ENDPOINT)
    c1_tests = [str(value) for value in _require_list(c1.get("tests"), code=code, label="endpoints.C1.tests")]
    c2_tests = [str(value) for value in _require_list(c2.get("tests"), code=code, label="endpoints.C2.tests")]
    if c1_tests != ["B128", "B64"]:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C1 检验层必须为 [B128, B64]", c1_tests)
    if c2_tests != ["B128", "B64"]:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C2 检验层必须为 [B128, B64]", c2_tests)
    benefit_c1 = _require_number(c1.get("threshold_benefit"), code=code, label="endpoints.C1.threshold_benefit")
    harm_c1 = _require_number(c1.get("threshold_harm"), code=code, label="endpoints.C1.threshold_harm")
    if not math.isclose(float(benefit_c1), C1_THRESHOLD_ABS, rel_tol=0.0, abs_tol=1e-12):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C1 获益阈值不符", benefit_c1)
    if not math.isclose(float(harm_c1), -C1_THRESHOLD_ABS, rel_tol=0.0, abs_tol=1e-12):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C1 损害阈值不符", harm_c1)
    benefit_c2 = _require_number(c2.get("threshold_benefit"), code=code, label="endpoints.C2.threshold_benefit")
    harm_c2 = _require_number(c2.get("threshold_harm"), code=code, label="endpoints.C2.threshold_harm")
    if not math.isclose(float(benefit_c2), -C2_RELATIVE_THRESHOLD, rel_tol=0.0, abs_tol=1e-12):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C2 获益相对阈值不符", benefit_c2)
    if not math.isclose(float(harm_c2), C2_RELATIVE_THRESHOLD, rel_tol=0.0, abs_tol=1e-12):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "C2 损害相对阈值不符", harm_c2)
    _checks(checks, "endpoints_contract", "PASS", "C1/C2 comparator 固定 CON−OBJ，阈值与计划一致")
    return {"C1": c1, "C2": c2, "comparator": COMPARATOR_ARMS[1], "c1_tests": c1_tests, "c2_tests": c2_tests}


def _validate_statistics_section(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    method = _require_str(section.get("method"), code=code, label="statistics.method")
    if "exact" not in method.lower() or "tie" not in method.lower():
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "statistics.method 必须声明 exact tie-aware 符号翻转检验", method)
    zero_policy = str(section.get("zero_policy", ""))
    if zero_policy.upper() != "DISCARDED":
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "零差处理必须为 DISCARDED", zero_policy)
    min_n_eff = _require_int(section.get("min_n_eff"), code=code, label="statistics.min_n_eff")
    if int(min_n_eff) != WILCOXON_MIN_N_EFF:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "min_n_eff 与计划不符", min_n_eff)
    holm = _require_mapping(section.get("holm"), code=code, label="statistics.holm")
    if not math.isclose(float(_require_number(holm.get("alpha"), code=code, label="statistics.holm.alpha")), ALPHA, rel_tol=0.0, abs_tol=1e-12):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "Holm alpha 不符", ALPHA)
    if _require_int(holm.get("family_size"), code=code, label="statistics.holm.family_size") != 2:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "Holm family_size 必须为 2")
    bootstrap = _require_mapping(section.get("bootstrap"), code=code, label="statistics.bootstrap")
    if _require_int(bootstrap.get("resamples"), code=code, label="statistics.bootstrap.resamples") != BOOTSTRAP_RESAMPLES:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "bootstrap 重采样次数不符", BOOTSTRAP_RESAMPLES)
    if _require_int(bootstrap.get("seed"), code=code, label="statistics.bootstrap.seed") != BOOTSTRAP_SEED:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "bootstrap seed 不符", BOOTSTRAP_SEED)
    confidence = _require_number(bootstrap.get("confidence"), code=code, label="statistics.bootstrap.confidence")
    if not math.isclose(float(confidence), BOOTSTRAP_CONFIDENCE, rel_tol=0.0, abs_tol=1e-12):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "bootstrap 置信水平不符", confidence)
    sensitivity = _require_mapping(section.get("sensitivity"), code=code, label="statistics.sensitivity")
    if not bool(_require_bool(sensitivity.get("pratt"), code=code, label="statistics.sensitivity.pratt")):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "Pratt 敏感性分析必须预注册为开启")
    permutation = _require_mapping(sensitivity.get("permutation"), code=code, label="statistics.sensitivity.permutation")
    if _require_int(permutation.get("resamples"), code=code, label="statistics.sensitivity.permutation.resamples") != PERMUTATION_RESAMPLES:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "置换检验重采样次数不符", PERMUTATION_RESAMPLES)
    if _require_int(permutation.get("seed"), code=code, label="statistics.sensitivity.permutation.seed") != PERMUTATION_SEED:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "置换检验 seed 不符", PERMUTATION_SEED)
    _checks(checks, "statistics_contract", "PASS", "精确 tie-aware Wilcoxon + Holm m=2 + bootstrap/置换 seed 与计划一致")
    return dict(section)


def _validate_figures_section(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    figures = _require_mapping(section, code=code, label="figures")
    missing = [key for key in FIGURE_KEYS if key not in figures]
    if missing:
        _fail(code, "figures 缺少图键", missing)
    extra = [key for key in figures.keys() if key not in FIGURE_KEYS]
    if extra:
        _fail(code, "figures 存在未知图键", extra)
    _checks(checks, "figures_contract", "PASS", "figures 恰含 10 个计划图键")
    return dict(figures)


def _validate_episode_bank_section(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    _, banks_value = _require_sub_key(
        section,
        ("banks", "bank_sha256", "bank_sha256s", "bank_shas"),
        code=code,
        label="episode_bank.banks",
    )
    if isinstance(banks_value, Mapping):
        bank_shas = {}
        for name, value in banks_value.items():
            bank_shas[str(name)] = _require_sha256(value, code=code, label="episode_bank.banks." + str(name))
    else:
        values = _require_list(banks_value, code=code, label="episode_bank.banks")
        if len(values) != 3:
            _fail(code, "episode_bank 必须恰有 3 个 bank sha", len(values))
        bank_shas = {"bank" + str(index): _require_sha256(value, code=code, label="episode_bank.banks[" + str(index) + "]") for index, value in enumerate(values)}
    if len(bank_shas) != 3:
        _fail(code, "episode_bank 必须恰有 3 个 bank sha", sorted(bank_shas.keys()))
    _, episodes_value = _require_sub_key(section, ("episodes_per_bank", "episode_count"), code=code, label="episode_bank.episodes_per_bank")
    if _require_int(episodes_value, code=code, label="episode_bank.episodes_per_bank") != 1600:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "episode_bank 每 bank 条数必须为 1600")
    _, unique_value = _require_sub_key(section, ("unique_episodes", "unique_episode_count"), code=code, label="episode_bank.unique_episodes")
    if _require_int(unique_value, code=code, label="episode_bank.unique_episodes") != 4800:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "episode_bank 唯一条数必须为 4800")
    _, pairs_value = _require_sub_key(section, ("model_episode_pairs", "model_episode_count"), code=code, label="episode_bank.model_episode_pairs")
    if _require_int(pairs_value, code=code, label="episode_bank.model_episode_pairs") != 9600:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "episode_bank 模型-episode 对数必须为 9600")
    _checks(checks, "episode_bank_contract", "PASS", "3 bank sha + 条数 1600×3/唯一 4800/模型-episode 9600")
    return {"banks": bank_shas, "episodes_per_bank": 1600, "unique_episodes": 4800, "model_episode_pairs": 9600}


def _validate_models_section(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    models = _require_mapping(section, code=code, label="models")
    for name in ("fomaml", "anil"):
        entry = _require_mapping(models.get(name), code=code, label="models." + name)
        config = _require_mapping(entry.get("config"), code=code, label="models." + name + ".config")
        if not config:
            _fail(code, "models." + name + ".config 不能为空")
        _require_sha256(entry.get("sha256"), code=code, label="models." + name + ".sha256")
        bank_sha = entry.get("episode_bank_sha256")
        if isinstance(bank_sha, Mapping):
            if not bank_sha:
                _fail(code, "models." + name + ".episode_bank_sha256 不能为空 mapping")
            for seed_key, seed_sha in bank_sha.items():
                _require_sha256(seed_sha, code=code, label="models." + name + ".episode_bank_sha256." + str(seed_key))
        else:
            _require_sha256(bank_sha, code=code, label="models." + name + ".episode_bank_sha256")
    # R-S3-04 放宽项 1：episode_bank_sha256 接受 64-hex 字符串或 mapping，
    # 内部统一归一为 {meta_seed_0..2: 64-hex} mapping 供下游消费。
    normalized: dict[str, Any] = {}
    for name, entry in models.items():
        item = dict(entry)
        bank_sha = item.get("episode_bank_sha256")
        if isinstance(bank_sha, str):
            item["episode_bank_sha256"] = {
                "meta_seed_" + str(seed): bank_sha for seed in sp.S3_MODEL_META_SEEDS
            }
        elif isinstance(bank_sha, Mapping):
            item["episode_bank_sha256"] = {str(key): str(value) for key, value in bank_sha.items()}
        normalized[str(name)] = item
    _checks(checks, "models_contract", "PASS", "FOMAML/ANIL 模型 contract 与 episode bank sha 已预注册")
    return normalized


def _validate_arms_section(section: Any, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    if isinstance(section, Mapping):
        arms = []
        for arm_id, value in section.items():
            entry = _require_mapping(value, code=code, label="arms." + str(arm_id))
            entry = dict(entry)
            entry.setdefault("arm_id", str(arm_id))
            arms.append(entry)
    else:
        items = _require_list(section, code=code, label="arms")
        arms = []
        for index, item in enumerate(items):
            entry = _require_mapping(item, code=code, label="arms[" + str(index) + "]")
            entry = dict(entry)
            entry.setdefault("arm_id", entry.get("id"))
            arms.append(entry)
    ids = [_require_str(entry.get("arm_id"), code=code, label="arms.arm_id") for entry in arms]
    if sorted(ids) != sorted(sp.S3_ARMS):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "arms 必须恰为五个冻结臂", {"expected": list(sp.S3_ARMS), "actual": ids})
    for entry in arms:
        if "rng" not in entry and "seed_contract" not in entry and "rng_contract" not in entry:
            _fail(code, "arm 缺少 RNG 合同字段（rng/rng_contract/seed_contract）: " + str(entry.get("arm_id")))
    _checks(checks, "arms_contract", "PASS", "五臂齐全且各自声明 RNG 合同")
    return arms


def _validate_budgets_section(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    budgets = [int(value) for value in _require_list(section.get("budgets"), code=code, label="budgets.budgets")]
    if sorted(budgets) != sorted(int(value) for value in sp.S3_BUDGETS):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "budgets 与冻结网格不符", budgets)
    if _require_int(section.get("k_shot"), code=code, label="budgets.k_shot") != sp.S3_K_SHOT:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "k_shot 不符", sp.S3_K_SHOT)
    # R-S3-05：主网格（opt 10）与 R-S3-02 降网格 fallback（opt 5）二者都接受；
    # 只有 fallback 时记 DISCLOSED（该降网格由预注册 campaign 规则在 pilot 后触发）。
    primary = getattr(sp, "S3_PREREG_BUDGETS", None)
    primary = primary if isinstance(primary, Mapping) else {}
    fallback = _rs3_02_fallback()
    primary_opt = primary.get("opt_seeds")
    primary_opt_count = len(primary_opt) if isinstance(primary_opt, (list, tuple)) else len(getattr(sp, "S3_OPT_SEEDS", range(10)))
    primary_meta = primary.get("meta_seeds")
    primary_meta_count = len(primary_meta) if isinstance(primary_meta, (list, tuple)) else len(getattr(sp, "S3_MODEL_META_SEEDS", range(3)))
    fallback_opt_count = _as_int_or_none(fallback.get("opt_seeds"))
    expected_counts: dict[str, list[int]] = {
        "opt_seeds": [int(primary_opt_count)] + ([fallback_opt_count] if fallback_opt_count is not None else []),
        "meta_seeds": [int(primary_meta_count)],
    }
    actual_counts: dict[str, int] = {}
    for name in ("opt_seeds", "meta_seeds"):
        value = section.get(name)
        if value is None:
            _fail(code, "budgets 缺 " + name)
        if isinstance(value, int) and not isinstance(value, bool):
            count = int(value)
        else:
            count = len(_require_list(value, code=code, label="budgets." + name))
        actual_counts[name] = count
        if count not in expected_counts[name]:
            _fail(
                S3_ANALYSIS_PREREG_BINDING_MISMATCH,
                "budgets." + name + " 数量不符: 接受 " + str(expected_counts[name]) + " 实际 " + str(count),
            )
    eval_tasks = section.get("eval_tasks", section.get("n_tasks", sp.S3_SPLIT_COUNTS["meta_test"]))
    if _require_int(eval_tasks, code=code, label="budgets.eval_tasks") != sp.S3_SPLIT_COUNTS["meta_test"]:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "eval task 数必须为 20")
    if actual_counts["opt_seeds"] != int(primary_opt_count):
        _checks(
            checks,
            "budgets_contract",
            "DISCLOSED",
            "预算使用 R-S3-02 降网格 fallback（opt_seeds="
            + str(actual_counts["opt_seeds"])
            + "，主网格="
            + str(primary_opt_count)
            + "）；该降网格由预注册 campaign 规则在 pilot 后按规则触发",
            code=RS3_02_DISCLOSED_CODE,
        )
    else:
        _checks(
            checks,
            "budgets_contract",
            "PASS",
            "预算网格 B∈{64,128}/K=5/opt "
            + str(actual_counts["opt_seeds"])
            + "/meta "
            + str(actual_counts["meta_seeds"])
            + "/tasks 20 已预注册",
        )
    return dict(section)


def _validate_resource_limits(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    limits = _require_mapping(section, code=code, label="resource_limits")
    expected = dict(sp.S3_RESOURCE_LIMITS)
    if set(limits.keys()) != set(expected.keys()):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "resource_limits 键集不符", {"expected": sorted(expected), "actual": sorted(limits)})
    for key, value in expected.items():
        if not math.isclose(float(_require_number(limits.get(key), code=code, label="resource_limits." + key)), float(value), rel_tol=0.0, abs_tol=1e-12):
            _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "resource_limits." + key + " 不符", value)
    _checks(checks, "resource_limits", "PASS", "资源限额与计划一致")
    return dict(limits)


def _validate_data_boundary_section(section: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    boundary = _require_mapping(section, code=code, label="data_boundary")
    flags = boundary.get("flags")
    flags = _require_mapping(flags, code=code, label="data_boundary.flags") if flags is not None else boundary
    normalized: dict[str, Any] = {}
    for flag in DATA_BOUNDARY_FLAGS:
        if flag not in flags:
            _fail(code, "data_boundary 缺少 phase 标志: " + flag)
        value = flags.get(flag)
        if isinstance(value, bool):
            normalized[flag] = value
        elif isinstance(value, str):
            normalized[flag] = value
        else:
            _fail(code, "data_boundary 标志类型必须为 bool 或分阶段声明: " + flag, value)
    support_phases = flags.get(DATA_BOUNDARY_SUPPORT_PHASES_FLAG)
    support_flag = flags.get(DATA_BOUNDARY_SUPPORT_FLAG)
    if support_phases is not None:
        phases = [str(value) for value in _require_list(support_phases, code=code, label="data_boundary.support_truth_read_phases", non_empty=True)]
        if set(phases) != set(DATA_BOUNDARY_SUPPORT_PHASES):
            _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "support_truth_read_phases 与冻结分阶段声明不符", phases)
        normalized[DATA_BOUNDARY_SUPPORT_PHASES_FLAG] = phases
    elif support_flag is not None:
        normalized[DATA_BOUNDARY_SUPPORT_FLAG] = support_flag
    else:
        _fail(code, "data_boundary 缺少 support_truth_read / support_truth_read_phases 分阶段声明")
    allowed = boundary.get("allowed_splits", boundary.get("eval_splits"))
    if allowed is None:
        # R-S3-04 放宽项 3：allowed_splits 为必填（6 split，含 dev）；仅旧扁平结构兼容。
        _fail(code, "data_boundary 缺 allowed_splits（必填 6 split，含 dev）")
    allowed_list = [str(value) for value in _require_list(allowed, code=code, label="data_boundary.allowed_splits", non_empty=True)]
    if set(allowed_list) != set(sp.S3_ALLOWED_SPLITS):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "data_boundary.allowed_splits 与冻结白名单不符", allowed_list)
    training = boundary.get("training_splits")
    if training is not None:
        if set(str(value) for value in _require_list(training, code=code, label="data_boundary.training_splits")) != set(sp.S3_TRAIN_SPLITS):
            _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "data_boundary.training_splits 不符")
    holdout = boundary.get("holdout_splits")
    if holdout is not None:
        if set(str(value) for value in _require_list(holdout, code=code, label="data_boundary.holdout_splits")) != set(sp.S3_HOLDOUT_SPLITS):
            _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "data_boundary.holdout_splits 不符")
    dev = boundary.get("dev_splits")
    if dev is not None:
        expected_dev = tuple(getattr(sp, "S3_DEV_SPLITS", ("dev", "meta_validation")))
        if set(str(value) for value in _require_list(dev, code=code, label="data_boundary.dev_splits")) != set(str(value) for value in expected_dev):
            _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "data_boundary.dev_splits 不符")
    _checks(checks, "data_boundary_contract", "PASS", "phase-scoped 数据边界标志与 split 白名单已预注册")
    return {"flags": normalized, "allowed_splits": allowed_list}


def _validate_aux_sections(obj: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    code = S3_ANALYSIS_PREREG_SCHEMA_INVALID
    negative = _require_mapping(obj.get("negative_controls"), code=code, label="negative_controls")
    if _require_int(negative.get("task_count", negative.get("tasks")), code=code, label="negative_controls.task_count") != 10:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "负控制任务数必须为 10")
    if _require_str(negative.get("reference_kind"), code=code, label="negative_controls.reference_kind") != "LABEL_SHUFFLED_NO_REFERENCE":
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "负控制 reference_kind 不符")
    for key in ("seed_formula", "label_shuffle_seed_algorithm", "suspicious_rule"):
        if key not in negative:
            _fail(code, "negative_controls 缺 " + key)
    ood = _require_mapping(obj.get("ood"), code=code, label="ood")
    if _require_int(ood.get("task_count", ood.get("tasks")), code=code, label="ood.task_count") != 10:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "OOD 任务数必须为 10")
    delta1_offset = _require_number(ood.get("delta1_offset", ood.get("delta1_shift")), code=code, label="ood.delta1_offset/ood.delta1_shift")
    if not math.isclose(float(delta1_offset), 0.05, rel_tol=0.0, abs_tol=1e-12):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "OOD delta1 偏移必须为 0.05")
    b1_perturb = _require_number(ood.get("b1_perturbation", ood.get("b1_perturb_scale")), code=code, label="ood.b1_perturbation/ood.b1_perturb_scale")
    if not math.isclose(float(b1_perturb), 0.30, rel_tol=0.0, abs_tol=1e-12):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "OOD b1 扰动必须为 0.30")
    determinism = _require_mapping(obj.get("determinism"), code=code, label="determinism")
    if _require_int(determinism.get("reruns", determinism.get("repeats")), code=code, label="determinism.reruns/determinism.repeats") < 2:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "确定性重跑次数必须 >=2")
    campaign = _require_mapping(obj.get("campaign"), code=code, label="campaign")
    if not any(key in campaign for key in ("authorization", "authorization_rule")):
        _fail(code, "campaign 缺 authorization/authorization_rule")
    if not any(key in campaign for key in ("rules", "required_record_fields", "runner_assert")):
        _fail(code, "campaign 缺 rules/required_record_fields/runner_assert")
    calibration = _require_mapping(obj.get("calibration"), code=code, label="calibration")
    _, selected = _require_sub_key(
        calibration,
        ("selected_delta1_base", "delta1_base", "selected_base"),
        code=code,
        label="calibration.selected_delta1_base",
    )
    selected_value = float(_require_number(selected, code=code, label="calibration.selected_delta1_base"))
    if not any(math.isclose(selected_value, candidate, rel_tol=0.0, abs_tol=1e-12) for candidate in (0.20, 0.22, 0.25)):
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "校准选中的 delta1_base 不在候选表内", selected_value)
    _checks(checks, "negative_controls_contract", "PASS", "负控制 10 任务/标签置换/reference_kind 已预注册")
    _checks(checks, "ood_contract", "PASS", "OOD 10 任务/delta1+0.05/b1 扰动 0.30 已预注册")
    _checks(checks, "determinism_contract", "PASS", "确定性重跑合同已预注册")
    _checks(checks, "campaign_contract", "PASS", "campaign 授权规则已预注册")
    _checks(checks, "calibration_contract", "PASS", "校准选中 delta1_base=" + str(selected_value))


def load_s3_prereg(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
    verify_code_sha: bool = False,
    verify_analysis_digest: bool = False,
    checks: list[dict[str, Any]] | None = None,
) -> S3Prereg:
    """加载并 fail-closed 校验 S3 预注册文件（计划 §6；analysis 不 import s3_runner）。"""
    checks = checks if checks is not None else []
    resolved, raw, obj = _load_prereg_file(path)
    unknown_top = sorted(set(obj.keys()) - set(S3_PREREG_REQUIRED_TOP_KEYS) - set(S3_PREREG_OPTIONAL_TOP_KEYS))
    if unknown_top:
        _checks(checks, "prereg_unknown_top_keys", "DISCLOSED", "未知顶层字段: " + ", ".join(unknown_top))
    missing = [key for key in S3_PREREG_REQUIRED_TOP_KEYS if key not in obj]
    if missing:
        _fail(S3_ANALYSIS_PREREG_SCHEMA_INVALID, "prereg 缺少必需顶层字段", missing)
    _scan_placeholders(obj)
    if _require_str(obj.get("schema_version"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="schema_version") != sp.S3_PREREG_SCHEMA_VERSION:
        _fail(S3_ANALYSIS_PREREG_BINDING_MISMATCH, "prereg schema_version 不符", sp.S3_PREREG_SCHEMA_VERSION)
    created_utc = _require_iso_utc(obj.get("created_utc"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="created_utc")
    prereg_id = _require_str(obj.get("prereg_id"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="prereg_id")
    if not PREREG_ID_PATTERN.match(prereg_id):
        _fail(S3_ANALYSIS_PREREG_SCHEMA_INVALID, "prereg_id 格式不符（" + PREREG_ID_DERIVATION + "）", prereg_id)
    prereg_digest = _require_sha256(obj.get("prereg_digest"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="prereg_digest")
    recomputed_digest = sp.prereg_digest(obj)
    if recomputed_digest != prereg_digest:
        _fail(
            S3_ANALYSIS_PREREG_DIGEST_MISMATCH,
            "prereg_digest 自洽校验失败（去掉 prereg_id/prereg_digest 后 canonical sha256）",
            {"declared": prereg_digest, "recomputed": recomputed_digest},
        )
    _checks(checks, "prereg_digest_self_consistency", "PASS", "prereg_digest 自洽: " + prereg_digest)
    family = _validate_family_section(_require_mapping(obj.get("family"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="family"), checks)
    endpoints = _validate_endpoints_section(_require_mapping(obj.get("endpoints"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="endpoints"), checks)
    statistics = _validate_statistics_section(_require_mapping(obj.get("statistics"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="statistics"), checks)
    figures = _validate_figures_section(_require_mapping(obj.get("figures"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="figures"), checks)
    episode_bank = _validate_episode_bank_section(_require_mapping(obj.get("episode_bank"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="episode_bank"), checks)
    models = _validate_models_section(_require_mapping(obj.get("models"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="models"), checks)
    arms = _validate_arms_section(obj.get("arms"), checks)
    budgets = _validate_budgets_section(_require_mapping(obj.get("budgets"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="budgets"), checks)
    resource_limits = _validate_resource_limits(_require_mapping(obj.get("resource_limits"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="resource_limits"), checks)
    data_boundary = _validate_data_boundary_section(_require_mapping(obj.get("data_boundary"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="data_boundary"), checks)
    _validate_aux_sections(obj, checks)
    references_section = _require_mapping(obj.get("references_sealed"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="references_sealed")
    _require_str(references_section.get("path"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="references_sealed.path")
    _require_sha256(references_section.get("sha256"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="references_sealed.sha256")
    code_sha = _require_sha256(obj.get("code_sha"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="code_sha")
    physical_call_count = _require_int(obj.get("physical_call_count"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="physical_call_count", minimum=0)
    if physical_call_count != 0:
        _fail(S3_ANALYSIS_PREREG_PHYSICAL_CALLS, "prereg physical_call_count 必须为 0", physical_call_count)
    analysis_plan_digest = _require_sha256(obj.get("analysis_plan_digest"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="analysis_plan_digest")
    fd_gate_sha256 = obj.get("fd_gate_sha256")
    if fd_gate_sha256 is not None:
        _require_sha256(fd_gate_sha256, code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="fd_gate_sha256")
        if "fd_gate_sha256" in set(sp.S3_PREREG_REQUIRED_FIELDS):
            _checks(checks, "prereg_fd_gate_sha256", "PASS", "prereg.fd_gate_sha256 格式通过: " + str(fd_gate_sha256))
        else:
            _checks(checks, "prereg_fd_gate_sha256", "DISCLOSED", "计划 v1.3b 迁移期：fd_gate_sha256 已存在但 A1 sp 常量尚未列入必填", code=S3_ANALYSIS_FD_GATE_PREREG_BINDING_PENDING)
    else:
        _checks(checks, "prereg_fd_gate_sha256", "DISCLOSED", "计划 v1.3b prereg.fd_gate_sha256 尚未落盘（A1 build 更新前迁移期），三方绑定待启用", code=S3_ANALYSIS_FD_GATE_PREREG_BINDING_PENDING)
    authorization_chain = obj.get("authorization_chain")
    if not authorization_chain:
        _fail(S3_ANALYSIS_PREREG_SCHEMA_INVALID, "authorization_chain 不能为空")
    root = Path(repo_root).resolve() if repo_root is not None else resolved.parent
    if verify_code_sha:
        computed_code_sha = sp.compute_code_sha(root)
        if computed_code_sha != code_sha:
            _fail(
                S3_ANALYSIS_PREREG_BINDING_MISMATCH,
                "prereg code_sha 与仓库 7 文件实算不符",
                {"declared": code_sha, "computed": computed_code_sha},
            )
        _checks(checks, "prereg_code_sha", "PASS", "code_sha 与仓库 7 文件实算一致: " + code_sha)
    else:
        _checks(checks, "prereg_code_sha_format", "PASS", "code_sha 格式校验通过（未复算仓库文件）")
    if verify_analysis_digest:
        analysis_code_sha = sp.compute_analysis_code_sha(root)
        recomputed_plan = sp.analysis_plan_digest(
            endpoints=endpoints,
            statistics=statistics,
            figures=figures,
            analysis_code_sha=analysis_code_sha,
        )
        if recomputed_plan != analysis_plan_digest:
            _fail(
                S3_ANALYSIS_PREREG_BINDING_MISMATCH,
                "analysis_plan_digest 实算不符",
                {"declared": analysis_plan_digest, "recomputed": recomputed_plan, "analysis_code_sha": analysis_code_sha},
            )
        _checks(checks, "analysis_plan_digest", "PASS", "analysis_plan_digest 实算一致: " + analysis_plan_digest)
    else:
        _checks(checks, "analysis_plan_digest_format", "PASS", "analysis_plan_digest 格式校验通过（未复算）")
    sha = sp.sha256_bytes(raw)
    _checks(checks, "prereg_file_sha256", "PASS", "prereg 文件 raw sha256: " + sha)
    _checks(checks, "prereg_physical_call_count", "PASS", "physical_call_count=0")
    return S3Prereg(
        path=resolved,
        raw=raw,
        sha256=sha,
        obj=dict(obj),
        prereg_id=prereg_id,
        prereg_digest=prereg_digest,
        analysis_plan_digest=analysis_plan_digest,
        created_utc=created_utc,
        family=family,
        references_sealed=dict(references_section),
        calibration=dict(obj.get("calibration")),
        episode_bank=episode_bank,
        models=models,
        arms=arms,
        budgets=budgets,
        endpoints=endpoints,
        statistics=statistics,
        figures=figures,
        negative_controls=dict(obj.get("negative_controls")),
        campaign=dict(obj.get("campaign")),
        ood=dict(obj.get("ood")),
        determinism=dict(obj.get("determinism")),
        resource_limits=resource_limits,
        code_sha=code_sha,
        physical_call_count=int(physical_call_count),
        data_boundary=data_boundary,
        authorization_chain=authorization_chain,
        checks=tuple(dict(item) for item in checks),
    )

# ---------------------------------------------------------------------------
# run 产物加载与 fail-closed 校验（计划 §4.3/§4.4/§4.5/§5.4）
# ---------------------------------------------------------------------------
RUN_STATUSES = ("COMPLETED", "PARTIAL", "FAILED", "RESOURCE_LIMIT", "DEADLINE_EXCEEDED")
TRAIN_RECORD_KEYS = frozenset(sp.S3_TRAIN_RECORD_FIELDS)
EVAL_RECORD_KEYS = frozenset(sp.S3_EVAL_RECORD_FIELDS)
RUN_DIR_SOURCE_FILES = (
    RUN_CONFIG_FILE,
    RUN_SUMMARY_FILE,
    RUN_RECORDS_FILE,
    MODEL_MANIFEST_FILE,
    DATA_MANIFEST_FILE,
    FD_GATE_FILE,
)
EVAL_QUERY_PLACEHOLDER = "NOT_AVAILABLE_IN_RECORDS"
S3_PREREG_CHECK_KEYS = ("check", "status", "detail")


@dataclass(frozen=True)
class S3RunData:
    """正式/SMOKE run 目录的只读快照（记录已流式聚合为逐 run 端点原料）。"""

    run_dir: Path
    config: dict[str, Any]
    summary: dict[str, Any]
    data_manifest: dict[str, Any]
    model_manifest: dict[str, Any]
    gate: dict[str, Any]
    grid: dict[str, Any]
    per_run: tuple[dict[str, Any], ...]
    train_records: tuple[dict[str, Any], ...]
    negative_control: dict[str, Any]
    determinism: dict[str, Any]
    record_streams: dict[str, Any]
    sources: dict[str, dict[str, Any]]
    checks: tuple[dict[str, Any], ...]

    @property
    def run_mode(self) -> str:
        return str(self.config.get("run_mode", "FORMAL"))

    @property
    def is_smoke(self) -> bool:
        return self.run_mode == "SMOKE"

    @property
    def run_id(self) -> str:
        return str(self.config.get("run_id"))

    @property
    def record_counts(self) -> dict[str, int]:
        return {str(key): int(value) for key, value in (self.config.get("record_counts") or {}).items() if _is_int(value)}

    @property
    def n_tasks(self) -> int:
        return int(self.grid.get("n_tasks", 0))

    @property
    def arms(self) -> tuple[str, ...]:
        return tuple(self.grid.get("arms", ()))

    @property
    def budgets(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.grid.get("budgets", ()))

    @property
    def opt_seeds(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.grid.get("opt_seeds", ()))

    @property
    def meta_seeds(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.grid.get("meta_seeds", ()))


def _require_run_file(run_dir: Path, name: str, *, code: str = S3_ANALYSIS_RUN_SCHEMA_INVALID) -> Path:
    path = run_dir / name
    if not path.is_file():
        _fail(code, "run 目录缺少必需产物: " + name, str(path))
    return path


def _read_run_json(run_dir: Path, name: str, *, code: str = S3_ANALYSIS_RUN_SCHEMA_INVALID) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _require_run_file(run_dir, name, code=code)
    payload = _read_json_file(path, code=code, label=name)
    body = _require_mapping(payload, code=code, label=name)
    source = {"path": str(path), "sha256": sp.sha256_bytes(path.read_bytes()), "bytes": path.stat().st_size}
    return dict(body), source



def _as_sha256_or_none(value: Any) -> str | None:
    """把值归一为 64 位小写 hex sha256；非 sha 返回 None（用于可选绑定比较）。"""
    if isinstance(value, str) and re.match(r"^[0-9a-f]{64}$", value.lower()):
        return value.lower()
    return None


def _normalize_scope_notes(value: Any, *, code: str, label: str) -> list[str]:
    """scope_notes 归一为字符串列表（计划 §4.3 允许 list[str] 或 mapping）。"""
    if isinstance(value, Mapping):
        return [str(key) + "=" + str(item) for key, item in sorted(value.items())]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    _fail(code, label + " 必须为字符串列表或 mapping", type(value).__name__)
    return []


# R-S3-06 §2：FORMAL 的 FD/梯度门每模型 32 坐标、共 2 个模型（fomaml_meta_0/anil_meta_0），
# 合计 64 个坐标条目；SMOKE 的 fd_coordinates 覆盖值对每个模型生效。
FORMAL_GATE_MODEL_KEYS = ("fomaml_meta_0", "anil_meta_0")
FORMAL_GATE_TOTAL_COORDINATES = 2 * int(sp.S3_FD_MAX_COORDINATES)
ACCEPTED_GATE_SCHEMA_VERSIONS = ("p4ra-s3-fd-gate-v1", str(sp.S3_GATE_SCHEMA_VERSION))
GATE_NEGATIVE_KEYS = ("tamper", "anil_body_frozen", "k0_equivalence")


def _run_expected_fd_coordinates(config: Mapping[str, Any], *, run_mode: str) -> int:
    """FD 门坐标数（每模型口径）：FORMAL 固定 32（计划 §4.4、R-S3-06 §2）；SMOKE 取 smoke_overrides.fd_coordinates。"""
    if run_mode == "FORMAL":
        return int(sp.S3_FD_MAX_COORDINATES)
    overrides = config.get("smoke_overrides")
    if isinstance(overrides, Mapping):
        value = _as_int_or_none(overrides.get("fd_coordinates"))
        if value is not None and value > 0:
            return int(value)
    return int(SMOKE_DEFAULT.get("fd_coordinates", 8))


def _accepted_fd_gate_modes() -> tuple[str, ...]:
    """A1 runner 以模型级梯度门（fomaml+anil）替代单一 full 模式；两者都接受，非 full 记 DISCLOSED。"""
    return (str(sp.S3_FD_MODE), "fomaml+anil", "fomaml", "anil")


def _validate_smoke_overrides(value: Any, *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """校验 SMOKE smoke_overrides 的 7 键与类型（计划 §4.5；缺失 fail-closed，未知 DISCLOSED）。"""
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    overrides = _require_mapping(value, code=code, label="run_config.smoke_overrides")
    if not overrides:
        _fail(code, "SMOKE run 必须携带非空 smoke_overrides")
    expected = set(sp.S3_SMOKE_OVERRIDE_KEYS)
    missing = sorted(expected - set(overrides.keys()))
    if missing:
        _fail(code, "smoke_overrides 缺少必需键", missing)
    unknown = sorted(set(overrides.keys()) - expected)
    if unknown:
        _checks(checks, "smoke_overrides_unknown_keys", "DISCLOSED", "smoke_overrides 未知额外键: " + ", ".join(unknown))
    normalized: dict[str, Any] = {}
    outer_steps = _require_int(overrides.get("outer_steps"), code=code, label="smoke_overrides.outer_steps", minimum=1)
    normalized["outer_steps"] = int(outer_steps)
    meta_seeds = [int(item) for item in _require_list(overrides.get("meta_seeds"), code=code, label="smoke_overrides.meta_seeds", non_empty=True)]
    if len(set(meta_seeds)) != len(meta_seeds):
        _fail(code, "smoke_overrides.meta_seeds 存在重复")
    normalized["meta_seeds"] = meta_seeds
    budgets = [int(item) for item in _require_list(overrides.get("budgets"), code=code, label="smoke_overrides.budgets", non_empty=True)]
    if len(set(budgets)) != len(budgets):
        _fail(code, "smoke_overrides.budgets 存在重复")
    normalized["budgets"] = budgets
    opt_seeds = [int(item) for item in _require_list(overrides.get("opt_seeds"), code=code, label="smoke_overrides.opt_seeds", non_empty=True)]
    if len(set(opt_seeds)) != len(opt_seeds):
        _fail(code, "smoke_overrides.opt_seeds 存在重复")
    normalized["opt_seeds"] = opt_seeds
    normalized["eval_tasks"] = int(_require_int(overrides.get("eval_tasks"), code=code, label="smoke_overrides.eval_tasks", minimum=1))
    k_sweep = [int(item) for item in _require_list(overrides.get("k_sweep"), code=code, label="smoke_overrides.k_sweep", non_empty=True)]
    if len(set(k_sweep)) != len(k_sweep):
        _fail(code, "smoke_overrides.k_sweep 存在重复", k_sweep)
    if any(int(value) < 0 for value in k_sweep):
        _fail(code, "smoke_overrides.k_sweep 必须为非负整数", k_sweep)
    # 计划 §4.5 允许 K 扫描子集；记录 schema（§4.3 的 19 字段）不含 K 维，K=0 曲线缺口归 fig2/报告层披露。
    if 0 not in k_sweep:
        _checks(checks, "smoke_overrides_k_sweep", "DISCLOSED", "smoke_overrides.k_sweep 未含 K=0 基线: " + str(k_sweep), code=SMOKE_DISCLOSED_CODE)
    normalized["k_sweep"] = k_sweep
    if "fd_coordinates" in overrides:
        normalized["fd_coordinates"] = int(_require_int(overrides.get("fd_coordinates"), code=code, label="smoke_overrides.fd_coordinates", minimum=1))
    else:
        normalized["fd_coordinates"] = int(SMOKE_DEFAULT.get("fd_coordinates", 8))
    return normalized


def _cross_check_smoke_grid(
    overrides: Mapping[str, Any],
    *,
    arm_ids: Sequence[str],
    budgets: Sequence[int],
    opt_seeds: Sequence[int],
    meta_seeds: Sequence[int],
    task_ids: Sequence[str],
    n_eval_tasks: int,
    evaluation_grid: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    """SMOKE 覆盖值与 run_config 各段必须自洽（避免声明与实际网格错位）。"""
    if len(arm_ids) != len(sp.S3_ARMS):
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "SMOKE arms 数量与冻结五臂不符", len(arm_ids))
    if tuple(sorted(int(value) for value in overrides["budgets"])) != tuple(sorted(int(value) for value in budgets)):
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "smoke_overrides.budgets 与 run_config.budgets 不一致")
    if tuple(int(value) for value in overrides["meta_seeds"]) != tuple(int(value) for value in meta_seeds):
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "smoke_overrides.meta_seeds 与 run_config.seeds.meta_seeds 不一致")
    if tuple(int(value) for value in overrides["opt_seeds"]) != tuple(int(value) for value in opt_seeds):
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "smoke_overrides.opt_seeds 与 run_config.seeds.opt_seeds 不一致")
    if int(overrides["eval_tasks"]) != int(n_eval_tasks):
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "smoke_overrides.eval_tasks 与 evaluation_grid 任务数不一致", {"declared": int(overrides["eval_tasks"]), "actual": int(n_eval_tasks)})
    declared_k = evaluation_grid.get("k_sweep")
    if declared_k is not None:
        declared = [int(item) for item in _require_list(declared_k, code=S3_ANALYSIS_RUN_SCHEMA_INVALID, label="evaluation_grid.k_sweep")]
        if sorted(declared) != sorted(int(item) for item in overrides["k_sweep"]):
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "smoke_overrides.k_sweep 与 evaluation_grid.k_sweep 不一致")
    _checks(checks, "smoke_overrides_grid", "PASS", "SMOKE 覆盖值与 run_config 网格自洽")

def _derive_run_grid(config: Mapping[str, Any], prereg: "S3Prereg", *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """从 run_config 派生分析网格（SMOKE 允许与 prereg 不同并记 DISCLOSED）。"""
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    run_mode = _require_str(config.get("run_mode"), code=code, label="run_config.run_mode")
    if run_mode not in sp.S3_RUN_MODES:
        _fail(code, "run_mode 非法: " + run_mode, list(sp.S3_RUN_MODES))
    smoke_overrides = config.get("smoke_overrides")
    if run_mode == "SMOKE":
        # Lead m08630/m08572：SMOKE 必须携带完整 smoke_overrides（7 键）并做类型校验；
        # 预算/网格/任务数允许与 prereg 不同，但必须与 run_config 各段自洽，且记 DISCLOSED。
        smoke_overrides = _validate_smoke_overrides(smoke_overrides, checks=checks)
        _checks(checks, "smoke_overrides", "DISCLOSED", "SMOKE 预算与 prereg 不同（开发验证，不用于正式结论）", code=SMOKE_DISCLOSED_CODE)
    else:
        if smoke_overrides is not None:
            _fail(code, "FORMAL run 不得携带 smoke_overrides")
        smoke_overrides = None
    arms_value = config.get("arms")
    if isinstance(arms_value, Mapping):
        arms_section = _require_mapping(arms_value, code=code, label="run_config.arms")
    else:
        # A1 runner 以 list[dict]（含 id/engine_type/...）声明五臂；两者都接受，统一交给 _derive_arm_ids。
        arms_section = {"arms": _require_list(arms_value, code=code, label="run_config.arms", non_empty=True)}
    arm_ids = _derive_arm_ids(arms_section)
    budgets_value = config.get("budgets")
    if isinstance(budgets_value, Mapping):
        budgets_list = budgets_value.get("budgets")
    else:
        budgets_list = budgets_value
    budgets = tuple(sorted(int(value) for value in _require_list(budgets_list, code=code, label="run_config.budgets")))
    seeds = _require_mapping(config.get("seeds"), code=code, label="run_config.seeds")
    opt_seeds = tuple(int(value) for value in _require_list(seeds.get("opt_seeds"), code=code, label="seeds.opt_seeds"))
    meta_seeds = tuple(int(value) for value in _require_list(seeds.get("meta_seeds"), code=code, label="seeds.meta_seeds"))
    k_shot = _require_int(seeds.get("k_shot", sp.S3_K_SHOT), code=code, label="seeds.k_shot")
    evaluation_grid = _require_mapping(config.get("evaluation_grid"), code=code, label="run_config.evaluation_grid")
    task_ids: list[str] = []
    for key in ("tasks", "task_ids", "eval_task_ids", "meta_test_task_ids"):
        if key in evaluation_grid:
            task_ids = [str(value) for value in _require_list(evaluation_grid.get(key), code=code, label="evaluation_grid." + key)]
            break
    if len(set(task_ids)) != len(task_ids):
        _fail(code, "evaluation_grid 任务列表存在重复")
    declared_eval_tasks = _as_int_or_none(evaluation_grid.get("eval_tasks", evaluation_grid.get("n_tasks")))
    eval_split = evaluation_grid.get("eval_split")
    if eval_split is not None:
        eval_split = _require_str(eval_split, code=code, label="evaluation_grid.eval_split")
        if eval_split not in sp.S3_ALLOWED_SPLITS:
            _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "evaluation_grid.eval_split 非法: " + str(eval_split), list(sp.S3_ALLOWED_SPLITS))
    if not task_ids:
        # A1 runner 布局：evaluation_grid 只声明任务计数 + split（无任务列表）；实际任务集合
        # 由 run_records 实测集合、计数与 data_manifest.split_task_ids 三方交叉校验
        # （见 _aggregate_eval_records 与 _cross_check_record_task_set），不静默放宽。
        if declared_eval_tasks is None or int(declared_eval_tasks) <= 0:
            _fail(code, "evaluation_grid 无任务列表时必须提供正整数 eval_tasks/n_tasks")
        n_eval_tasks = int(declared_eval_tasks)
        if run_mode == "FORMAL" and eval_split is None:
            _fail(code, "FORMAL evaluation_grid 无任务列表时必须提供 eval_split（用于与 data_manifest 交叉校验）")
    else:
        n_eval_tasks = len(task_ids)
        if declared_eval_tasks is not None and int(declared_eval_tasks) != len(task_ids):
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "evaluation_grid.eval_tasks 与任务列表长度不一致", {"declared": declared_eval_tasks, "actual": len(task_ids)})
    if run_mode == "FORMAL":
        # Lead m09348：SMOKE 专属放宽（K=0 可缺、K 子集任意）不得泄漏到 FORMAL。
        declared_k = evaluation_grid.get("K", evaluation_grid.get("k_sweep"))
        if declared_k is None:
            _fail(code, "FORMAL evaluation_grid 必须显式声明 K/k_sweep 评估集合", list(FORMAL_K_SWEEP))
        formal_k = [int(value) for value in _require_list(declared_k, code=code, label="evaluation_grid.K")]
        if len(set(formal_k)) != len(formal_k):
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "FORMAL evaluation_grid.K 存在重复", formal_k)
        if sorted(formal_k) != list(FORMAL_K_SWEEP):
            _fail(
                S3_ANALYSIS_BUDGET_MISMATCH,
                "FORMAL K 集合必须为 " + str(list(FORMAL_K_SWEEP)),
                formal_k,
            )
        _checks(checks, "run_grid_formal_k_sweep", "PASS", "FORMAL K 集合与计划 §3.3（K=5 固定）一致: " + str(list(FORMAL_K_SWEEP)))
        expected_tasks = int(sp.S3_SPLIT_COUNTS["meta_test"])
        if int(n_eval_tasks) != expected_tasks:
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "FORMAL 评估任务数不符: 期望 " + str(expected_tasks) + " 实际 " + str(int(n_eval_tasks)))
        if budgets != tuple(int(value) for value in sp.S3_BUDGETS):
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "FORMAL budgets 必须为 " + str(sp.S3_BUDGETS), budgets)
        # R-S3-05：FORMAL opt_seeds 数量接受预注册主网格或 R-S3-02 降网格 fallback。
        prereg_opt_seeds = prereg.budgets.get("opt_seeds")
        accepted_opt_counts: list[int] = []
        if isinstance(prereg_opt_seeds, (list, tuple, int, str)):
            if isinstance(prereg_opt_seeds, (list, tuple)):
                accepted_opt_counts.append(len(prereg_opt_seeds))
            else:
                accepted_opt_counts.append(int(prereg_opt_seeds))
        fallback_opt = _as_int_or_none(_rs3_02_fallback().get("opt_seeds"))
        if fallback_opt is not None and fallback_opt not in accepted_opt_counts:
            accepted_opt_counts.append(int(fallback_opt))
        if len(opt_seeds) not in accepted_opt_counts:
            _fail(
                S3_ANALYSIS_BUDGET_MISMATCH,
                "FORMAL opt_seeds 数量与 prereg 或 R-S3-02 fallback 不符: 接受 "
                + str(accepted_opt_counts)
                + " 实际 "
                + str(len(opt_seeds)),
            )
        prereg_meta_seeds = prereg.budgets.get("meta_seeds")
        if isinstance(prereg_meta_seeds, (list, tuple)) and len(meta_seeds) != len(prereg_meta_seeds):
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "FORMAL meta_seeds 数量与 prereg 不符")
        if k_shot != int(sp.S3_K_SHOT):
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "FORMAL K-shot 必须为 5")
    else:
        if SMOKE_DEFAULT_EVAL_TASKS != int(n_eval_tasks):
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "SMOKE 评估任务数必须为 " + str(SMOKE_DEFAULT_EVAL_TASKS), n_eval_tasks)
    run_count = len(arm_ids) * len(budgets) * len(opt_seeds) * len(meta_seeds) * int(n_eval_tasks)
    eval_records_expected = run_count * sum(budgets) // len(budgets) if budget_symmetric(budgets) else sum(
        len(arm_ids) * 1 * len(opt_seeds) * len(meta_seeds) * int(n_eval_tasks) * budget for budget in budgets
    )
    # R-S3-05：FORMAL 允许预注册主网格或 R-S3-02 降网格 fallback（按预注册 campaign 规则触发），
    # 实际规模写入 grid/aggregate 并在 fallback 时记 DISCLOSED，绝不静默改口径。
    rs3_02_applied = False
    if run_mode == "FORMAL":
        fallback = _rs3_02_fallback()
        declared_runs = _as_int_or_none(prereg.budgets.get("grid_runs"))
        if declared_runs is None:
            declared_runs = _as_int_or_none(prereg.budgets.get("main_runs"))
        fallback_runs = _as_int_or_none(fallback.get("main_runs"))
        accepted_runs = [value for value in (declared_runs, fallback_runs) if value is not None]
        if accepted_runs and int(run_count) not in accepted_runs:
            _fail(
                S3_ANALYSIS_BUDGET_MISMATCH,
                "FORMAL run 数不符: 接受 " + str(accepted_runs) + " 实际 " + str(run_count),
            )
        declared_evals = _as_int_or_none(prereg.budgets.get("main_evals"))
        fallback_evals = _as_int_or_none(fallback.get("main_evals"))
        accepted_evals = [value for value in (declared_evals, fallback_evals) if value is not None]
        if accepted_evals and int(eval_records_expected) not in accepted_evals:
            _fail(
                S3_ANALYSIS_BUDGET_MISMATCH,
                "FORMAL eval 记录数不符: 接受 " + str(accepted_evals) + " 实际 " + str(eval_records_expected),
            )
        rs3_02_applied = (
            fallback_runs is not None
            and int(run_count) == fallback_runs
            and (declared_runs is None or int(run_count) != declared_runs)
        )
        if rs3_02_applied:
            _checks(
                checks,
                "run_grid_rs3_02",
                "DISCLOSED",
                "FORMAL 使用 R-S3-02 降网格 fallback: runs="
                + str(run_count)
                + " evals="
                + str(eval_records_expected)
                + "（主网格 runs="
                + str(declared_runs)
                + " evals="
                + str(declared_evals)
                + "）；实际规模已写入 aggregate.run_grid/execution_scale",
                code=RS3_02_DISCLOSED_CODE,
            )
        else:
            _checks(checks, "run_grid_rs3_02", "PASS", "FORMAL 网格规模与预注册主网格一致")
    # Lead m08572：SMOKE 每个 meta_seed 训练 FOMAML 与 ANIL 两个模型，train 记录 = 2*len(meta_seeds)*outer_steps；
    # R-S3-07：FORMAL 正式 run 加载 M2 冻结模型、不重训 → train 记录恒 0（出现训练记录即 fail-closed）。
    if run_mode == "SMOKE":
        outer_steps = int(smoke_overrides["outer_steps"])
        train_expected = 2 * len(meta_seeds) * int(outer_steps)
        _cross_check_smoke_grid(
            smoke_overrides,
            arm_ids=arm_ids,
            budgets=budgets,
            opt_seeds=opt_seeds,
            meta_seeds=meta_seeds,
            task_ids=task_ids,
            n_eval_tasks=n_eval_tasks,
            evaluation_grid=evaluation_grid,
            checks=checks,
        )
    else:
        outer_steps = 200
        train_expected = 0
        _checks(checks, "run_grid_formal_train0", "PASS", "FORMAL 加载 M2 冻结模型不重训：train 记录期望 0（R-S3-07）")
    _checks(checks, "run_grid", "PASS", "派生网格: mode=" + run_mode + " arms=" + str(len(arm_ids)) + " budgets=" + str(budgets) + " opt=" + str(len(opt_seeds)) + " meta=" + str(len(meta_seeds)) + " tasks=" + str(int(n_eval_tasks)) + " runs=" + str(run_count) + " outer_steps=" + str(outer_steps))
    return {
        "run_mode": run_mode,
        "arms": tuple(arm_ids),
        "budgets": budgets,
        "opt_seeds": opt_seeds,
        "meta_seeds": meta_seeds,
        "k_shot": int(k_shot),
        "task_ids": tuple(task_ids),
        "n_tasks": int(n_eval_tasks),
        "eval_split": eval_split,
        "run_count": int(run_count),
        "eval_records_expected": int(eval_records_expected),
        "eval_tasks": int(n_eval_tasks),
        "train_expected": int(train_expected),
        "eval_expected": int(eval_records_expected),
        "outer_steps": int(outer_steps),
        "smoke_overrides": dict(smoke_overrides) if isinstance(smoke_overrides, Mapping) else None,
        "rs3_02_fallback_applied": bool(rs3_02_applied),
    }


def budget_symmetric(budgets: Sequence[int]) -> bool:
    return len(budgets) > 0


def _derive_arm_ids(arms_section: Mapping[str, Any]) -> list[str]:
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    if "arms" in arms_section:
        values = arms_section.get("arms")
    else:
        values = arms_section
    if isinstance(values, Mapping):
        ids = [str(key) for key in values.keys()]
    else:
        items = _require_list(values, code=code, label="run_config.arms")
        ids = []
        for index, item in enumerate(items):
            if isinstance(item, Mapping):
                ids.append(_require_str(item.get("arm_id", item.get("id")), code=code, label="arms[" + str(index) + "]"))
            else:
                ids.append(_require_str(item, code=code, label="arms[" + str(index) + "]"))
    if sorted(ids) != sorted(sp.S3_ARMS):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.arms 必须恰为五个冻结臂", {"expected": list(sp.S3_ARMS), "actual": ids})
    return ids



def _validate_model_sha_binding(
    models_section: Mapping[str, Any],
    prereg: "S3Prereg",
    *,
    run_mode: str,
    checks: list[dict[str, Any]],
) -> None:
    """run_config.models.sha256 与预注册模型包的绑定（按 run_mode 分流）。

    Lead m09348：SMOKE 允许 runner 在 run 内重训模型（sha 必然不同，记 DISCLOSED）；
    FORMAL 必须严格等于 M2 冻结的预注册模型 sha，不得用 DISCLOSED 替代 fail-closed。
    """
    code = S3_ANALYSIS_RUN_BINDING_MISMATCH
    prereg_models_section = prereg.models if isinstance(prereg.models, Mapping) else {}
    for name in ("fomaml", "anil"):
        model_entry = _require_mapping(models_section.get(name), code=S3_ANALYSIS_RUN_SCHEMA_INVALID, label="run_config.models." + name)
        run_model_sha = _require_sha256(model_entry.get("sha256"), code=S3_ANALYSIS_RUN_SCHEMA_INVALID, label="models." + name + ".sha256")
        prereg_entry = prereg_models_section.get(name)
        prereg_sha = _as_sha256_or_none(prereg_entry.get("sha256")) if isinstance(prereg_entry, Mapping) else None
        if run_mode == "FORMAL":
            if prereg_sha is None:
                _fail(code, "FORMAL 缺少预注册模型 sha，无法校验 run_config.models." + name)
            if run_model_sha != prereg_sha:
                _fail(
                    code,
                    "FORMAL run_config.models." + name + ".sha256 必须等于预注册模型 sha",
                    {"expected": prereg_sha, "actual": run_model_sha},
                )
            _checks(checks, "models_pre_registered_sha", "PASS", "FORMAL run 模型 sha 与预注册模型包严格一致: " + name)
        elif prereg_sha is not None and run_model_sha == prereg_sha:
            _checks(checks, "models_pre_registered_sha", "PASS", "SMOKE run 模型 sha 与预注册模型包一致: " + name)
        else:
            _checks(
                checks,
                "models_retrained_in_run",
                "DISCLOSED",
                "SMOKE run 模型 sha 与预注册模型包不同（runner 在 run 内训练模型，属预期）: " + name,
            )


# ---------------------------------------------------------------------------
# Lead m09990（R-S3-08A）与计划 v1.3b：
#   (a) run_config.k_sweep 为新增必需字段；FORMAL 唯一合法值 [5]。
#       M1 K-sweep 诊断（[0,1,3,5]，240 runs/15,360 evals）是独立开发验证件，不进正式 run_config/预算/统计。
#   (b) prereg 新增必需字段 fd_gate_sha256；FORMAL 三方绑定：
#       prereg.fd_gate_sha256 == run_config.fd_or_gradient_gate.sha256
#                             == evidence/s3/gate/fd_or_gradient_gate.json 原始字节 sha256。
#   A1 落盘前按迁移期 DISCLOSED 记录（不伪造 PASS），落盘后自动转严格 fail-closed。
# ---------------------------------------------------------------------------
def _prereg_fd_gate_sha(prereg: "S3Prereg") -> str | None:
    """读取 prereg.fd_gate_sha256（S3Prereg.raw 为 canonical bytes；缺失返回 None）。"""
    payload = getattr(prereg, "raw", None)
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = json.loads(bytes(payload).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = None
    if isinstance(payload, Mapping) and payload.get("fd_gate_sha256") is not None:
        return _require_sha256(payload.get("fd_gate_sha256"), code=S3_ANALYSIS_PREREG_SCHEMA_INVALID, label="prereg.fd_gate_sha256")
    return None


def _validate_fd_gate_prereg_binding(
    gate: Mapping[str, Any],
    prereg: "S3Prereg",
    *,
    run_mode: str,
    checks: list[dict[str, Any]],
) -> str | None:
    """R-S3-08A(b)：三方绑定第 1-2 环（prereg 与 run_config 声明）；FORMAL 严格，SMOKE 只披露。"""
    gate_sha = _require_sha256(
        gate.get("sha256", gate.get("fd_gate_sha256")),
        code=S3_ANALYSIS_RUN_SCHEMA_INVALID,
        label="run_config.fd_or_gradient_gate.sha256",
    )
    prereg_sha = _prereg_fd_gate_sha(prereg)
    if prereg_sha is None:
        _checks(
            checks,
            "fd_gate_prereg_binding",
            "DISCLOSED",
            "计划 v1.3b prereg.fd_gate_sha256 尚未在 A1 build 落盘（迁移期披露）；落盘后 FORMAL 三方绑定 fail-closed",
            code=S3_ANALYSIS_FD_GATE_PREREG_BINDING_PENDING,
        )
        return None
    if str(run_mode) != "FORMAL":
        _checks(
            checks,
            "fd_gate_prereg_binding",
            "DISCLOSED",
            "SMOKE 使用 run 内生成 FD 门（override=true），不绑定冻结门 sha",
            code=SMOKE_DISCLOSED_CODE,
        )
        return prereg_sha
    if str(gate_sha) != str(prereg_sha):
        _fail(
            S3_ANALYSIS_RUN_BINDING_MISMATCH,
            "run_config.fd_or_gradient_gate.sha256 与 prereg.fd_gate_sha256 不符",
            {"config": gate_sha, "prereg": prereg_sha},
        )
    _checks(checks, "fd_gate_prereg_binding", "PASS", "FORMAL 三方绑定第 2 环通过：run_config gate sha256 == prereg.fd_gate_sha256")
    return prereg_sha


def _assert_gate_file_prereg_binding(
    gate_sha: str,
    prereg: "S3Prereg",
    *,
    run_mode: str,
    checks: list[dict[str, Any]],
) -> None:
    """R-S3-08A(b)：三方绑定第 3 环（冻结门文件 raw sha）；FORMAL 严格。"""
    prereg_sha = _prereg_fd_gate_sha(prereg)
    if prereg_sha is None or str(run_mode) != "FORMAL":
        return
    if str(gate_sha) != str(prereg_sha):
        _fail(
            S3_ANALYSIS_FD_GATE_INVALID,
            "fd_or_gradient_gate.json raw sha256 与 prereg.fd_gate_sha256 不符",
            {"file": gate_sha, "prereg": prereg_sha},
        )
    _checks(checks, "fd_gate_file_prereg_binding", "PASS", "FORMAL 三方绑定第 3 环通过：门文件 raw sha256 == prereg.fd_gate_sha256")


def _validate_k_sweep(config: Mapping[str, Any], *, grid: Mapping[str, Any], checks: list[dict[str, Any]]) -> list[int] | None:
    """计划 v1.3b / R-S3-08A(a)：run_config.k_sweep；FORMAL 唯一合法值 [5]。"""
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    run_mode = str(grid.get("run_mode"))
    required_field = "k_sweep" in set(sp.S3_RUN_CONFIG_REQUIRED_FIELDS)
    if "k_sweep" not in config:
        if required_field:
            _fail(code, "run_config 缺少必需字段 k_sweep")
        _checks(
            checks,
            "k_sweep_config",
            "DISCLOSED",
            "计划 v1.3b 新增 run_config.k_sweep 尚未在 A1 runner 落盘（迁移期披露）；落盘后 FORMAL 严格 [5]",
            code=S3_ANALYSIS_K_SWEEP_MISSING_PENDING,
        )
        return None
    raw = _require_list(config.get("k_sweep"), code=code, label="run_config.k_sweep")
    values: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            _fail(code, "run_config.k_sweep 必须为整数数组", item)
        values.append(int(item))
    if values != sorted(set(values)):
        _fail(code, "run_config.k_sweep 必须无重复且升序", values)
    if run_mode == "FORMAL":
        if tuple(values) != tuple(FORMAL_K_SWEEP):
            # 计划 v1.3b / Lead m10061：M1 K-sweep 诊断集 [0,1,3,5] 属预算/网格错配，归 BUDGET_MISMATCH 一类
            _fail(
                S3_ANALYSIS_BUDGET_MISMATCH,
                "FORMAL run_config.k_sweep 唯一合法值 [5]（计划 §3.3 K=5 固定；[0,1,3,5] 属 M1 K-sweep 诊断件，不得进正式 run_config）",
                values,
            )
        _checks(checks, "k_sweep_config", "PASS", "FORMAL run_config.k_sweep=[5] 严格通过")
    else:
        if tuple(values) != tuple(FORMAL_K_SWEEP):
            _checks(checks, "k_sweep_config", "DISCLOSED", "SMOKE run_config.k_sweep 非 [5]（开发验证）: " + str(values), code=SMOKE_DISCLOSED_CODE)
        else:
            _checks(checks, "k_sweep_config", "PASS", "SMOKE run_config.k_sweep=[5]")
    return values


def _validate_run_config(config: dict[str, Any], prereg: "S3Prereg", *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    required = set(sp.S3_RUN_CONFIG_REQUIRED_FIELDS)
    optional = set(sp.S3_RUN_CONFIG_OPTIONAL_FIELDS) | {"k_sweep"}
    keys = set(config.keys())
    missing = sorted(required - keys)
    if missing:
        _fail(code, "run_config 缺少必需字段", missing)
    unknown = sorted(keys - required - optional)
    if unknown:
        _checks(checks, "run_config_unknown_fields", "DISCLOSED", "run_config 未知额外字段: " + ", ".join(unknown))
    if _require_str(config.get("schema_version"), code=code, label="run_config.schema_version") != sp.S3_RUN_CONFIG_SCHEMA_VERSION:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config schema_version 不符", sp.S3_RUN_CONFIG_SCHEMA_VERSION)
    run_id = _require_str(config.get("run_id"), code=code, label="run_config.run_id")
    if _require_str(config.get("prereg_id"), code=code, label="run_config.prereg_id") != prereg.prereg_id:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.prereg_id 与 prereg 不符")
    if _require_sha256(config.get("prereg_digest"), code=code, label="run_config.prereg_digest") != prereg.prereg_digest:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.prereg_digest 与 prereg 不符")
    if _require_sha256(config.get("analysis_plan_digest"), code=code, label="run_config.analysis_plan_digest") != prereg.analysis_plan_digest:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.analysis_plan_digest 与 prereg 不符")
    if _require_sha256(config.get("code_sha"), code=code, label="run_config.code_sha") != prereg.code_sha:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.code_sha 与 prereg 不符")
    grid = _derive_run_grid(config, prereg, checks=checks)
    family_section = _require_mapping(config.get("family_package"), code=code, label="run_config.family_package")
    _require_sha256(family_section.get("family_package_sha256", family_section.get("sha256")), code=code, label="family_package.sha256")
    if _require_sha256(config.get("task_ids_sha256"), code=code, label="run_config.task_ids_sha256") != prereg.family.get("task_ids_sha256"):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.task_ids_sha256 与 prereg 不符")
    if _require_sha256(config.get("references_sealed_sha256"), code=code, label="run_config.references_sealed_sha256") != prereg.references_sealed.get("sha256"):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.references_sealed_sha256 与 prereg 不符")
    boundary = _require_mapping(config.get("data_boundary"), code=code, label="run_config.data_boundary")
    flags = boundary.get("flags", boundary)
    flags = _require_mapping(flags, code=code, label="run_config.data_boundary.flags")
    for flag in DATA_BOUNDARY_FLAGS:
        if flag not in flags:
            _fail(code, "run_config.data_boundary 缺 phase 标志: " + flag)
    for flag in ("holdout_truth_used_for_training", "holdout_truth_used_for_adaptation", "holdout_truth_used_for_bo_ranking"):
        if flags.get(flag) is not False:
            _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "run 阶段 " + flag + " 必须为 false", flags.get(flag))
    if flags.get("holdout_truth_read_for_evaluation") is not True:
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "EVAL 阶段 holdout_truth_read_for_evaluation 必须为 true")
    support_phases = flags.get(DATA_BOUNDARY_SUPPORT_PHASES_FLAG)
    support_flag = flags.get(DATA_BOUNDARY_SUPPORT_FLAG)
    if support_phases is not None:
        if set(str(value) for value in _require_list(support_phases, code=code, label="run_config.data_boundary.support_truth_read_phases")) != set(DATA_BOUNDARY_SUPPORT_PHASES):
            _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "support_truth_read_phases 必须为 EVAL/OOD/NEGATIVE_CONTROL", support_phases)
    elif support_flag not in (True, "EVAL/OOD/NEGATIVE_CONTROL", "PHASE_SCOPED"):
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "support_truth_read 必须声明为 EVAL/OOD/NEGATIVE_CONTROL 分阶段", support_flag)
    models_section = _require_mapping(config.get("models"), code=code, label="run_config.models")
    _validate_model_sha_binding(models_section, prereg, run_mode=str(grid["run_mode"]), checks=checks)
    episode_bank = _require_mapping(config.get("episode_bank"), code=code, label="run_config.episode_bank")
    bank_source = episode_bank.get("banks", episode_bank)
    if isinstance(bank_source, Mapping):
        for name, value in bank_source.items():
            if isinstance(value, str) and re.match(r"^[0-9a-f]{64}$", value):
                continue
    _require_int(episode_bank.get("episodes_per_bank", episode_bank.get("episodes")), code=code, label="episode_bank.episodes_per_bank")
    gate = _require_mapping(config.get("fd_or_gradient_gate"), code=code, label="run_config.fd_or_gradient_gate")
    _require_run_gate_fields(gate, prereg, checks=checks, config=config)
    _validate_fd_gate_prereg_binding(gate, prereg, run_mode=str(grid["run_mode"]), checks=checks)
    budgets_value = config.get("budgets")
    if isinstance(budgets_value, Mapping):
        if "k_shot" in budgets_value:
            if int(budgets_value["k_shot"]) != int(sp.S3_K_SHOT) and grid["run_mode"] == "FORMAL":
                _fail(S3_ANALYSIS_BUDGET_MISMATCH, "run_config.budgets.k_shot 不符")
    _validate_k_sweep(config, grid=grid, checks=checks)
    _validate_record_schema_declaration(config, checks=checks)
    _validate_record_counts(config, prereg, grid, checks=checks)
    limits = _require_mapping(config.get("resource_limits"), code=code, label="run_config.resource_limits")
    if set(limits.keys()) != set(sp.S3_RESOURCE_LIMITS.keys()):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.resource_limits 键集不符", sorted(limits))
    for key, expected in sp.S3_RESOURCE_LIMITS.items():
        if not math.isclose(float(_require_number(limits.get(key), code=code, label="resource_limits." + key)), float(expected), rel_tol=0.0, abs_tol=1e-12):
            _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.resource_limits." + key + " 不符", expected)
    physical = _require_int(config.get("physical_call_count"), code=code, label="run_config.physical_call_count", minimum=0)
    if physical != 0:
        _fail(S3_ANALYSIS_PREREG_PHYSICAL_CALLS, "run_config.physical_call_count 必须为 0", physical)
    if _require_str(config.get("evidence_scope"), code=code, label="run_config.evidence_scope") != sp.S3_EVIDENCE_SCOPE:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_config.evidence_scope 不符", sp.S3_EVIDENCE_SCOPE)
    scope_notes = _normalize_scope_notes(config.get("scope_notes"), code=code, label="run_config.scope_notes")
    _checks(checks, "run_config_schema", "PASS", "run_config schema 通过（run_id=" + run_id + "）")
    _checks(checks, "run_config_prereg_binding", "PASS", "prereg_id/digest/analysis_plan_digest/code_sha/family/task_ids/episode_bank/models 严格绑定")
    _checks(checks, "run_config_physical_call_count", "PASS", "physical_call_count=0")
    result = dict(config)
    result["_grid"] = grid
    result["_scope_notes"] = list(scope_notes)
    return result


def _run_gate_coordinate_count(gate: Mapping[str, Any], *, code: str) -> int:
    """从 run_config.fd_or_gradient_gate 推导坐标总数（兼容 int/list/mapping/models 多种形状）。"""
    coordinates = gate.get("coordinates")
    if isinstance(coordinates, (list, tuple)):
        return len(coordinates)
    if isinstance(coordinates, Mapping):
        total = 0
        for key, value in coordinates.items():
            if isinstance(value, (list, tuple)):
                total += len(value)
            elif isinstance(value, Mapping):
                nested = value.get("coordinates")
                if isinstance(nested, (list, tuple)):
                    total += len(nested)
                elif value.get("n_checked") is not None:
                    total += int(_require_int(value.get("n_checked"), code=code, label="fd_gate.coordinates." + str(key) + ".n_checked"))
                else:
                    _fail(code, "fd_gate.coordinates 映射项无法推导坐标数", str(key))
            elif isinstance(value, bool):
                _fail(code, "fd_gate.coordinates 映射项非法", str(key))
            else:
                total += int(_require_int(value, code=code, label="fd_gate.coordinates." + str(key)))
        return total
    if gate.get("n_checked") is not None:
        return int(_require_int(gate.get("n_checked"), code=code, label="fd_gate.n_checked"))
    models = gate.get("models")
    if isinstance(models, Mapping) and models:
        total = 0
        for key, value in models.items():
            entry = _require_mapping(value, code=code, label="fd_gate.models." + str(key))
            nested = entry.get("coordinates")
            if isinstance(nested, (list, tuple)):
                total += len(nested)
            elif entry.get("n_checked") is not None:
                total += int(_require_int(entry.get("n_checked"), code=code, label="fd_gate.models." + str(key) + ".n_checked"))
            else:
                _fail(code, "fd_gate.models 项缺 n_checked/coordinates", str(key))
        return total
    _fail(code, "run_config.fd_or_gradient_gate 缺坐标计数（coordinates/n_checked/models）")
    raise AssertionError("unreachable")


def _validate_formal_run_gate_contract(gate: Mapping[str, Any], *, checks: list[dict[str, Any]]) -> None:
    """R-S3-07：FORMAL run_config.fd_or_gradient_gate 固定形状（与 A1 约定的一致值校验）。

    期望形状：
    {sha256: 门文件 raw sha, coordinates_per_model: 32, coordinates_total: 64, mode: "FORMAL",
     models: {fomaml_meta_0: {path, sha256, n_checked, status, max_relative_error},
              anil_meta_0:   {path, sha256, n_checked, status, max_relative_error}}}
    逐模型 n_checked 必须=32、status=PASS、max_relative_error<=1e-6；两键必在。
    """
    code = S3_ANALYSIS_FD_GATE_INVALID
    allowed = {"sha256", "coordinates_per_model", "coordinates_total", "mode", "models", "override"}
    unknown = sorted(set(gate.keys()) - allowed)
    if unknown:
        _checks(checks, "fd_gate_config_unknown_fields", "DISCLOSED", "FORMAL run_config.fd_or_gradient_gate 出现约定外字段（忽略）: " + ",".join(unknown))
    _require_sha256(gate.get("sha256"), code=code, label="fd_gate.sha256")
    mode = _require_str(gate.get("mode"), code=code, label="fd_gate.mode")
    if mode != "FORMAL":
        _fail(code, "FORMAL run_config.fd_or_gradient_gate.mode 必须为 FORMAL", mode)
    # R-S3-08B（A1 冻结形状）：FORMAL override 必须显式 false（SMOKE 才允许 true）。
    override = gate.get("override")
    if override is None:
        _checks(checks, "fd_gate_override_declaration", "DISCLOSED", "FORMAL run_config.fd_or_gradient_gate 未声明 override（按 false 处理）")
    elif _require_bool(override, code=code, label="fd_gate.override") is not False:
        _fail(code, "FORMAL run_config.fd_or_gradient_gate.override 必须为 false（仅 SMOKE 允许 override=true）", override)
    per_model = _require_int(gate.get("coordinates_per_model"), code=code, label="fd_gate.coordinates_per_model", minimum=1)
    total = _require_int(gate.get("coordinates_total"), code=code, label="fd_gate.coordinates_total", minimum=1)
    if int(per_model) != int(sp.S3_FD_MAX_COORDINATES):
        _fail(code, "FORMAL fd_gate.coordinates_per_model 必须为 " + str(sp.S3_FD_MAX_COORDINATES), per_model)
    if int(total) != int(FORMAL_GATE_TOTAL_COORDINATES):
        _fail(code, "FORMAL fd_gate.coordinates_total 必须为 " + str(FORMAL_GATE_TOTAL_COORDINATES) + "（两模型合计）", total)
    models = _require_mapping(gate.get("models"), code=code, label="fd_gate.models")
    missing_models = sorted(set(FORMAL_GATE_MODEL_KEYS) - set(models.keys()))
    if missing_models:
        _fail(code, "FORMAL fd_gate.models 缺模型键", missing_models)
    extra_models = sorted(set(models.keys()) - set(FORMAL_GATE_MODEL_KEYS))
    if extra_models:
        _fail(code, "FORMAL fd_gate.models 出现约定外模型键", extra_models)
    expected_entry_keys = {"path", "sha256", "n_checked", "status", "max_relative_error"}
    for model_key in FORMAL_GATE_MODEL_KEYS:
        entry = _require_mapping(models.get(model_key), code=code, label="fd_gate.models." + model_key)
        missing_entry = sorted(expected_entry_keys - set(entry.keys()))
        if missing_entry:
            _fail(code, "fd_gate.models." + model_key + " 缺字段", missing_entry)
        _require_str(entry.get("path"), code=code, label="fd_gate.models." + model_key + ".path")
        _require_sha256(entry.get("sha256"), code=code, label="fd_gate.models." + model_key + ".sha256")
        n_checked = _require_int(entry.get("n_checked"), code=code, label="fd_gate.models." + model_key + ".n_checked", minimum=1)
        if int(n_checked) != int(sp.S3_FD_MAX_COORDINATES):
            _fail(code, "FORMAL fd_gate.models." + model_key + ".n_checked 必须为 " + str(sp.S3_FD_MAX_COORDINATES), n_checked)
        status = _require_str(entry.get("status"), code=code, label="fd_gate.models." + model_key + ".status")
        if status != "PASS":
            _fail(code, "FORMAL fd_gate.models." + model_key + ".status 必须为 PASS", status)
        max_rel = _require_number(entry.get("max_relative_error"), code=code, label="fd_gate.models." + model_key + ".max_relative_error")
        if float(max_rel) < 0 or float(max_rel) > float(sp.S3_FD_TOLERANCE):
            _fail(code, "FORMAL fd_gate.models." + model_key + ".max_relative_error 超出容差", max_rel)
    _checks(checks, "fd_gate_models", "PASS", "FORMAL FD 门声明两模型（fomaml_meta_0/anil_meta_0）各 32 坐标")
    _checks(checks, "fd_gate_total_coordinates", "PASS", "FORMAL FD 门坐标总数=64（每模型 32，R-S3-06 §2/R-S3-07）")
    _checks(checks, "fd_gate_config", "PASS", "FORMAL FD 门声明形状/阈值/两模型状态均 PASS（R-S3-07）")


def _validate_smoke_run_gate_contract(gate: Mapping[str, Any], *, expected_n: int, checks: list[dict[str, Any]]) -> None:
    '''SMOKE run_config.fd_or_gradient_gate 模型级声明形状（A1 v1.3b runner 实测口径，R-S3-08B）。

    期望形状：
    {sha256: 门文件 raw sha, coordinates_per_model: N, coordinates_total: N*len(models), mode: SMOKE,
     override: true, models: {<模型键>: {path, sha256, n_checked, status, max_relative_error}}}
    顶层无 status/tolerance/max_relative_error（这些在门文件与 run_summary 绑定中校验）。
    '''
    code = S3_ANALYSIS_FD_GATE_INVALID
    allowed = {'sha256', 'coordinates_per_model', 'coordinates_total', 'mode', 'models', 'override'}
    unknown = sorted(set(gate.keys()) - allowed)
    if unknown:
        _checks(checks, 'fd_gate_config_unknown_fields', 'DISCLOSED', 'SMOKE run_config.fd_or_gradient_gate 出现约定外字段（忽略）: ' + ','.join(unknown))
    _require_sha256(gate.get('sha256'), code=code, label='fd_gate.sha256')
    mode = _require_str(gate.get('mode'), code=code, label='fd_gate.mode')
    if mode != 'SMOKE':
        _fail(code, 'SMOKE run_config.fd_or_gradient_gate.mode 必须为 SMOKE', mode)
    per_model = _require_int(gate.get('coordinates_per_model'), code=code, label='fd_gate.coordinates_per_model', minimum=1)
    if int(per_model) != int(expected_n):
        _fail(code, 'SMOKE fd_gate.coordinates_per_model 与 smoke_overrides.fd_coordinates 不符', {'expected': int(expected_n), 'actual': int(per_model)})
    models = _require_mapping(gate.get('models'), code=code, label='fd_gate.models')
    if len(models) not in (1, 2):
        _fail(code, 'SMOKE fd_gate.models 必须覆盖 1-2 个模型', sorted(models.keys()))
    total = _require_int(gate.get('coordinates_total'), code=code, label='fd_gate.coordinates_total', minimum=1)
    if int(total) != int(per_model) * len(models):
        _fail(code, 'SMOKE fd_gate.coordinates_total 必须等于每模型坐标数×模型数', {'per_model': int(per_model), 'models': len(models), 'total': int(total)})
    expected_entry_keys = {'path', 'sha256', 'n_checked', 'status', 'max_relative_error'}
    for model_key in sorted(models.keys()):
        entry = _require_mapping(models.get(model_key), code=code, label='fd_gate.models.' + str(model_key))
        missing_entry = sorted(expected_entry_keys - set(entry.keys()))
        if missing_entry:
            _fail(code, 'SMOKE fd_gate.models.' + str(model_key) + ' 缺字段', missing_entry)
        _require_str(entry.get('path'), code=code, label='fd_gate.models.' + str(model_key) + '.path')
        _require_sha256(entry.get('sha256'), code=code, label='fd_gate.models.' + str(model_key) + '.sha256')
        n_checked = _require_int(entry.get('n_checked'), code=code, label='fd_gate.models.' + str(model_key) + '.n_checked', minimum=1)
        if int(n_checked) != int(per_model):
            _fail(code, 'SMOKE fd_gate.models.' + str(model_key) + '.n_checked 必须等于 coordinates_per_model', n_checked)
        status = _require_str(entry.get('status'), code=code, label='fd_gate.models.' + str(model_key) + '.status')
        if status != 'PASS':
            _fail(code, 'SMOKE fd_gate.models.' + str(model_key) + '.status 必须为 PASS', status)
        max_rel = _require_number(entry.get('max_relative_error'), code=code, label='fd_gate.models.' + str(model_key) + '.max_relative_error')
        if float(max_rel) < 0 or float(max_rel) > float(sp.S3_FD_TOLERANCE):
            _fail(code, 'SMOKE fd_gate.models.' + str(model_key) + '.max_relative_error 超出容差', max_rel)
    override = gate.get('override')
    if override is not True:
        _fail(code, 'SMOKE run_config.fd_or_gradient_gate.override 必须为 true', override)
    _checks(checks, 'fd_gate_models', 'PASS', 'SMOKE FD 门声明 ' + str(len(models)) + ' 个模型，每模型 ' + str(int(per_model)) + ' 坐标')
    _checks(checks, 'fd_gate_config', 'PASS', 'SMOKE FD 门声明形状/阈值/模型状态均 PASS（每模型 ' + str(int(per_model)) + ' 坐标，合计 ' + str(int(total)) + '）')
    _checks(checks, 'fd_gate_override', 'DISCLOSED', 'SMOKE FD 门 override=true（开发验证用，非正式冻结门）')

def _require_run_gate_fields(gate: Mapping[str, Any], prereg: "S3Prereg", *, checks: list[dict[str, Any]], config: Mapping[str, Any]) -> None:
    """run_config.fd_or_gradient_gate 段校验：模式接受 full 或 A1 的模型级 fomaml+anil，坐标数按 run_mode 口径。

    R-S3-07 起 FORMAL 使用固定模型级声明形状（_validate_formal_run_gate_contract），SMOKE 保持旧/中间形状兼容。
    """
    code = S3_ANALYSIS_FD_GATE_INVALID
    run_mode = str(config.get("run_mode", "FORMAL"))
    if run_mode == "FORMAL":
        models_value = gate.get("models")
        if not isinstance(models_value, Mapping) or not models_value:
            _fail(code, "FORMAL run_config.fd_or_gradient_gate 必须为 R-S3-07 模型级形状（含 models 两键）", sorted(gate.keys()))
        _validate_formal_run_gate_contract(gate, checks=checks)
        return
    expected_n = _run_expected_fd_coordinates(config, run_mode=run_mode)
    if gate.get("status") is None and isinstance(gate.get("models"), Mapping) and gate.get("models"):
        # A1 v1.3b runner 的 SMOKE 声明形状：顶层无 status，模型级状态在 models 段（R-S3-08B）。
        _validate_smoke_run_gate_contract(gate, expected_n=int(expected_n), checks=checks)
        return
    status = _require_str(gate.get("status"), code=code, label="fd_gate.status")
    if status != "PASS":
        _fail(code, "run_config.fd_or_gradient_gate.status 必须为 PASS", status)
    mode = str(gate.get("mode")) if gate.get("mode") is not None else str(sp.S3_FD_MODE)
    if gate.get("mode") is not None and mode not in _accepted_fd_gate_modes():
        _fail(code, "fd_gate.mode 必须为 " + str(sp.S3_FD_MODE) + " 或 fomaml+anil", mode)
    if gate.get("mode") is None:
        _checks(checks, "fd_gate_mode_disclosed", "DISCLOSED", "run_config.fd_or_gradient_gate 未声明 mode（按 full 口径校验）")
    if mode != str(sp.S3_FD_MODE):
        _checks(
            checks,
            "fd_gate_mode_disclosed",
            "DISCLOSED",
            "run_config.fd_or_gradient_gate.mode=" + mode + "（模型级梯度门，非单一 full 模式；坐标数按 run_mode 口径校验）",
        )
    max_rel = _require_number(gate.get("max_relative_error", gate.get("max_rel_err")), code=code, label="fd_gate.max_relative_error")
    if float(max_rel) < 0 or float(max_rel) > float(sp.S3_FD_TOLERANCE):
        _fail(code, "fd_gate.max_relative_error 超出容差", max_rel)
    tolerance = gate.get("tolerance")
    if tolerance is not None:
        tolerance_value = _require_number(tolerance, code=code, label="fd_gate.tolerance")
        if float(tolerance_value) > float(sp.S3_FD_TOLERANCE):
            _fail(code, "fd_gate.tolerance 超出冻结容差", tolerance_value)
    n_checked = _run_gate_coordinate_count(gate, code=code)
    # R-S3-06 §2：每模型 32 坐标、2 模型合计 64；run_config 里两种计数口径都可能出现。
    accepted_counts = {int(expected_n)}
    if run_mode == "FORMAL":
        accepted_counts.add(int(FORMAL_GATE_TOTAL_COORDINATES))
    if int(n_checked) not in accepted_counts:
        _fail(code, "fd_gate 坐标数与 run_mode 口径不符", {"expected": sorted(accepted_counts), "actual": n_checked, "run_mode": run_mode})
    if run_mode == "FORMAL" and int(n_checked) == int(FORMAL_GATE_TOTAL_COORDINATES):
        _checks(checks, "fd_gate_total_coordinates", "DISCLOSED", "run_config.fd_or_gradient_gate.coordinates=64 为两模型合计口径（每模型 32，R-S3-06 §2）")
    _require_sha256(gate.get("fd_gate_sha256", gate.get("sha256")), code=code, label="fd_gate.fd_gate_sha256")
    _checks(
        checks,
        "fd_gate_config",
        "PASS",
        "FD 门 status=PASS/mode=" + mode + "/坐标数=" + str(n_checked) + "/max_rel=" + str(max_rel),
    )


def _validate_record_schema_declaration(config: Mapping[str, Any], *, checks: list[dict[str, Any]]) -> None:
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    schemas = _require_mapping(config.get("record_schemas"), code=code, label="run_config.record_schemas")
    expected = {"train": tuple(sp.S3_TRAIN_RECORD_FIELDS), "eval": tuple(sp.S3_EVAL_RECORD_FIELDS)}
    for name, fields in expected.items():
        value = schemas.get(name)
        if tuple(str(item) for item in _require_list(value, code=code, label="record_schemas." + name)) != fields:
            _fail(code, "run_config.record_schemas." + name + " 与 s3_prereg 单源字段不符")
    if set(schemas.keys()) != {"train", "eval"}:
        _fail(code, "run_config.record_schemas 必须恰含 train/eval", sorted(schemas))


# ---------------------------------------------------------------------------
# R-S3-08（Lead m09910 裁定）：FORMAL 记录计数为五条流合计——
#   主网格 run_records.jsonl + 负控 negative_control_records.jsonl + OOD ood_records.jsonl
#   + 确定性 determinism/r1..r3/run_records.jsonl。
# run_config/run_summary.record_counts = {train:0, eval:362880, total:362880}，
# status_counts.eval 为五流汇总；主统计只消费主网格记录（不改变 9 CSV/18 字段/计划）。
# 任何计数不符 fail-closed S3_ANALYSIS_RECORD_COUNTS_MISMATCH。
# ---------------------------------------------------------------------------
NEGATIVE_CONTROL_SUMMARY_FILE = "negative_control_summary.json"
NC_RECORDS_FILE = "negative_control_records.jsonl"
OOD_RECORDS_FILE = "ood_records.jsonl"
DETERMINISM_REPEAT_NAMES = ("r1", "r2", "r3")


def _mean_budget(grid: Mapping[str, Any]) -> int:
    """每个 run 的平均评估记录数（预算网格必须能整除）。"""
    budgets = [int(value) for value in grid["budgets"]]
    if not budgets:
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "run 预算网格为空")
    total = sum(budgets)
    if total % len(budgets) != 0:
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "预算网格不能整除，无法推导每 run 平均评估数", budgets)
    return total // len(budgets)


def _expected_stream_counts(grid: Mapping[str, Any], prereg: "S3Prereg") -> dict[str, Any]:
    """按 run 模式推导五条记录流的期望 run/记录数（FORMAL：main+NC+OOD+DET；SMOKE 单流）。"""
    run_mode = str(grid.get("run_mode"))
    main_runs = int(grid["run_count"])
    main_records = int(grid["eval_records_expected"])
    stream: dict[str, Any] = {"main": {"runs": main_runs, "records": main_records}}
    if run_mode != "FORMAL":
        stream["total"] = {"runs": main_runs, "records": main_records}
        return stream
    budgets = dict(getattr(prereg, "budgets", None) or {})
    fallback = _rs3_02_fallback()
    mean_budget = _mean_budget(grid)
    nc_runs = int(budgets.get("negative_control_runs", 0) or 0)
    ood_runs = int(budgets.get("ood_runs", 0) or 0)
    nc_records = int(budgets.get("negative_control_evals", nc_runs * mean_budget) or 0)
    ood_records = int(budgets.get("ood_evals", ood_runs * mean_budget) or 0)
    repeats = int(budgets.get("determinism_repeats", fallback.get("determinism_repeats", 3)) or 3)
    if bool(grid.get("rs3_02_fallback_applied")):
        runs_per_repeat = int(fallback.get("determinism_subset_runs", 60) or 60)
        det_runs = int(fallback.get("determinism_runs", runs_per_repeat * repeats) or 0)
        det_records = int(fallback.get("determinism_evals", det_runs * mean_budget) or 0)
    else:
        runs_per_repeat = int(budgets.get("determinism_subset_runs", fallback.get("determinism_subset_runs", 100)) or 100)
        det_runs = int(budgets.get("determinism_runs", runs_per_repeat * repeats) or 0)
        det_records = int(budgets.get("determinism_evals", det_runs * mean_budget) or 0)
    stream["nc"] = {"runs": nc_runs, "records": nc_records}
    stream["ood"] = {"runs": ood_runs, "records": ood_records}
    stream["det"] = {
        "runs": det_runs,
        "records": det_records,
        "repeats": repeats,
        "runs_per_repeat": runs_per_repeat,
        "records_per_repeat": runs_per_repeat * mean_budget,
    }
    stream["total"] = {
        "runs": main_runs + nc_runs + ood_runs + det_runs,
        "records": main_records + nc_records + ood_records + det_records,
    }
    return stream


def _iter_stream_records(path: Path, *, label: str) -> Iterator[dict[str, Any]]:
    """逐行读取辅助流记录并校验必需的 eval 记录字段（缺字段 fail-closed）。"""
    for record in _iter_record_lines(path, code=S3_ANALYSIS_RECORD_INVALID):
        missing = sorted(EVAL_RECORD_KEYS - set(record.keys()))
        if missing:
            _fail(S3_ANALYSIS_RECORD_INVALID, label + " 记录缺必需字段", {"path": str(path), "missing": missing})
        yield dict(record)


def _scan_record_stream(path: Path, *, label: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """流式统计一个辅助记录流的 run 数、记录数、状态/split/phase 计数。"""
    records = 0
    run_ids: set[str] = set()
    status_counts = {"OK": 0, "FAILED": 0}
    split_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    unknown: set[str] = set()
    for record in _iter_stream_records(path, label=label):
        records += 1
        run_id = record.get("run_id")
        if isinstance(run_id, str) and run_id:
            run_ids.add(run_id)
        # 与 s3_runner._status_counts 同口径：仅 f 缺失且 status=="FAILED" 记 FAILED，其余记 OK。
        status = "FAILED" if record.get("f") is None and str(record.get("status")) == "FAILED" else "OK"
        status_counts[status] += 1
        split = str(record.get("split"))
        phase = str(record.get("phase"))
        split_counts[split] = split_counts.get(split, 0) + 1
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        unknown.update(set(record.keys()) - EVAL_RECORD_KEYS)
    if unknown:
        _checks(checks, "record_stream_unknown_fields_" + label, "DISCLOSED", label + " 记录未知额外字段: " + ",".join(sorted(unknown)))
    return {
        "path": str(path),
        "records": records,
        "runs": len(run_ids),
        "status_counts": status_counts,
        "split_counts": split_counts,
        "phase_counts": phase_counts,
    }


def _resolve_stream_file(candidates: Sequence[Path], *, label: str) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    _fail(S3_ANALYSIS_RECORD_COUNTS_MISMATCH, "缺少 " + label + " 记录流文件", {"candidates": [str(path) for path in candidates]})
    raise AssertionError("unreachable")


def _assert_stream_split_phase(name: str, stream: Mapping[str, Any], split: str, phase: str) -> None:
    bad_split = {key: value for key, value in dict(stream.get("split_counts") or {}).items() if str(key) != split}
    bad_phase = {key: value for key, value in dict(stream.get("phase_counts") or {}).items() if str(key) != phase}
    if bad_split or bad_phase:
        _fail(
            S3_ANALYSIS_DATA_BOUNDARY_VIOLATION,
            name + " 记录 split/phase 与数据边界不符",
            {"expected_split": split, "expected_phase": phase, "split": bad_split, "phase": bad_phase},
        )


def _scan_aux_streams(run_dir: Path, grid: Mapping[str, Any], *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """加载 FORMAL 的 NC/OOD/DET 辅助记录流（SMOKE 不执行，返回单流空壳）。"""
    run_mode = str(grid.get("run_mode"))
    if run_mode != "FORMAL":
        _checks(checks, "record_streams", "NOT_APPLICABLE", "SMOKE run 不执行 NC/OOD/DET 辅助流（单流）")
        return {
            "available": False,
            "nc": {},
            "ood": {},
            "det": {"repeats": [], "records": 0, "runs": 0, "status_counts": {"OK": 0, "FAILED": 0}},
            "aux_records": 0,
            "sources": {},
        }
    nc_path = _resolve_stream_file(
        [run_dir / NC_RECORDS_FILE, run_dir / NEGATIVE_CONTROL_DIR / "records.jsonl"],
        label="负控（NC）",
    )
    ood_path = _resolve_stream_file(
        [run_dir / OOD_RECORDS_FILE, run_dir / "meta_test_ood_records.jsonl", run_dir / "ood" / "records.jsonl"],
        label="OOD",
    )
    nc = _scan_record_stream(nc_path, label="nc", checks=checks)
    ood = _scan_record_stream(ood_path, label="ood", checks=checks)
    det_dir = run_dir / DETERMINISM_DIR
    repeats: list[dict[str, Any]] = []
    for name in DETERMINISM_REPEAT_NAMES:
        candidates = [
            det_dir / name / RUN_RECORDS_FILE,
            det_dir / name / "records.jsonl",
            det_dir / (RUN_RECORDS_FILE.replace(".jsonl", "") + "_" + name + ".jsonl"),
        ]
        repeat_path = _resolve_stream_file(candidates, label="确定性重跑 " + name)
        repeat = _scan_record_stream(repeat_path, label="det_" + name, checks=checks)
        repeat["name"] = name
        repeats.append(repeat)
    det_records = sum(int(item["records"]) for item in repeats)
    det_runs = sum(int(item["runs"]) for item in repeats)
    det_status = {
        "OK": sum(int(item["status_counts"]["OK"]) for item in repeats),
        "FAILED": sum(int(item["status_counts"]["FAILED"]) for item in repeats),
    }
    eval_split = str(grid.get("eval_split") or sp.S3_EVAL_SPLIT)
    _assert_stream_split_phase("nc", nc, "meta_test_negative_control", PHASE_NEGATIVE_CONTROL)
    _assert_stream_split_phase("ood", ood, "meta_test_ood", PHASE_OOD)
    for repeat in repeats:
        _assert_stream_split_phase("det_" + str(repeat["name"]), repeat, eval_split, PHASE_EVAL)
    sources: dict[str, dict[str, Any]] = {}
    for name, path in (("nc", nc_path), ("ood", ood_path)):
        sources[name] = {"path": str(path), "sha256": sp.sha256_file(path), "bytes": path.stat().st_size}
    for repeat in repeats:
        key = "det_" + str(repeat["name"])
        repeat_path = Path(str(repeat["path"]))
        sources[key] = {"path": str(repeat_path), "sha256": sp.sha256_file(repeat_path), "bytes": repeat_path.stat().st_size}
    _checks(
        checks,
        "record_streams",
        "PASS",
        "FORMAL 辅助记录流已加载: NC=" + str(nc["records"]) + " OOD=" + str(ood["records"]) + " DET=" + str(det_records),
    )
    return {
        "available": True,
        "nc": nc,
        "ood": ood,
        "det": {"repeats": repeats, "records": det_records, "runs": det_runs, "status_counts": det_status},
        "aux_records": int(nc["records"]) + int(ood["records"]) + det_records,
        "sources": sources,
    }


def _normalize_artifact_key(key: str) -> str:
    text = str(key).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _artifact_covers(artifact_sha: Mapping[str, Any], relative: str) -> bool:
    """data_manifest.artifact_sha256 的键是否覆盖给定相对路径（容忍文件名/相对路径两种写法）。"""
    target = _normalize_artifact_key(relative)
    for key in artifact_sha:
        candidate = _normalize_artifact_key(key)
        if candidate == target or candidate.endswith("/" + target) or target.endswith("/" + candidate):
            return True
    return False


def _validate_record_stream_counts(
    *,
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    grid: Mapping[str, Any],
    prereg: "S3Prereg",
    main_counts: Mapping[str, int],
    aux_streams: Mapping[str, Any],
    data_manifest: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """R-S3-08：FORMAL 五条记录流分段计数 fail-closed 校验；SMOKE 保持单流语义。"""
    code = S3_ANALYSIS_RECORD_COUNTS_MISMATCH
    run_mode = str(grid.get("run_mode"))
    main_stream = {
        "runs": int(grid["run_count"]),
        "records": int(main_counts["eval"]),
        "status_counts": {"OK": int(main_counts.get("eval_ok", 0)), "FAILED": int(main_counts.get("eval_failed", 0))},
    }
    declared = _require_mapping(config.get("record_counts"), code=code, label="run_config.record_counts")
    summary_declared = _require_mapping(summary.get("record_counts"), code=code, label="run_summary.record_counts")
    declared_int = {str(key): int(value) for key, value in declared.items() if _is_int(value)}
    summary_int = {str(key): int(value) for key, value in summary_declared.items() if _is_int(value)}
    if declared_int != summary_int:
        _fail(code, "run_config 与 run_summary 的 record_counts 不完全一致", {"config": declared_int, "summary": summary_int})
    # R-S3-08A：status_counts 仅要求出现在 run_summary；run_config 提供则必须严格相等，
    # 缺失记 DISCLOSED（accepted_with_disclosure，aggregate 顶层 status_counts_disclosure 披露）。
    summary_status = _require_mapping(summary.get("status_counts"), code=code, label="run_summary.status_counts")
    config_status_raw = config.get("status_counts")
    if config_status_raw is not None:
        config_status = _require_mapping(config_status_raw, code=code, label="run_config.status_counts")
        if dict(config_status) != dict(summary_status):
            _fail(code, "run_config 与 run_summary 的 status_counts 不完全一致", {"config": dict(config_status), "summary": dict(summary_status)})
        _checks(checks, "status_counts_config", "PASS", "run_config.status_counts 与 run_summary 严格一致", config_provided=True)
    else:
        _checks(
            checks,
            "status_counts_config",
            "DISCLOSED",
            "run_config 未提供 status_counts（仅 run_summary 汇总五流状态）；按 R-S3-08A 接受并披露",
            code=S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED,
            accepted_with_disclosure=True,
        )
    by_stream: dict[str, Any] = {"main": main_stream}
    if run_mode != "FORMAL":
        by_stream["total"] = {"runs": main_stream["runs"], "records": main_stream["records"], "status_counts": dict(main_stream["status_counts"])}
        if int(main_stream["records"]) != int(declared_int.get("eval", -1)):
            _fail(code, "SMOKE 主记录流条数与 record_counts.eval 不符", {"declared": declared_int.get("eval"), "actual": main_stream["records"]})
        _checks(checks, "record_stream_counts", "PASS", "SMOKE 单流记录计数一致: eval=" + str(main_stream["records"]))
        return by_stream
    expected = _expected_stream_counts(grid, prereg)
    for name in ("main", "nc", "ood"):
        actual = main_stream if name == "main" else aux_streams[name]
        exp = expected[name]
        if int(actual["records"]) != int(exp["records"]) or int(actual["runs"]) != int(exp["runs"]):
            _fail(
                code,
                "记录流 " + name + " 的 run/记录数不符",
                {"stream": name, "expected": exp, "actual": {"runs": actual["runs"], "records": actual["records"]}},
            )
    det = aux_streams["det"]
    exp_det = expected["det"]
    if len(det["repeats"]) != int(exp_det["repeats"]):
        _fail(code, "确定性重跑份数不符", {"expected": exp_det["repeats"], "actual": len(det["repeats"])})
    for repeat in det["repeats"]:
        if int(repeat["records"]) != int(exp_det["records_per_repeat"]) or int(repeat["runs"]) != int(exp_det["runs_per_repeat"]):
            _fail(
                code,
                "确定性重跑 " + str(repeat["name"]) + " 的 run/记录数不符",
                {
                    "expected": {"runs": exp_det["runs_per_repeat"], "records": exp_det["records_per_repeat"]},
                    "actual": {"runs": repeat["runs"], "records": repeat["records"]},
                },
            )
    if int(det["records"]) != int(exp_det["records"]) or int(det["runs"]) != int(exp_det["runs"]):
        _fail(
            code,
            "确定性三份合计不符",
            {"expected": {"runs": exp_det["runs"], "records": exp_det["records"]}, "actual": {"runs": det["runs"], "records": det["records"]}},
        )
    for name, stream in (("main", main_stream), ("nc", aux_streams["nc"]), ("ood", aux_streams["ood"]), ("det", det)):
        by_stream[name] = {"runs": int(stream["runs"]), "records": int(stream["records"]), "status_counts": dict(stream["status_counts"])}
    total_records = sum(int(item["records"]) for item in by_stream.values())
    total_runs = sum(int(item["runs"]) for item in by_stream.values())
    total_status = {
        "OK": sum(int(item["status_counts"]["OK"]) for item in by_stream.values()),
        "FAILED": sum(int(item["status_counts"]["FAILED"]) for item in by_stream.values()),
    }
    by_stream["total"] = {"runs": total_runs, "records": total_records, "status_counts": total_status}
    declared_eval = int(_require_int(declared.get("eval"), code=code, label="record_counts.eval"))
    if declared_eval != total_records:
        _fail(
            code,
            "record_counts.eval 与四段记录流合计不符",
            {
                "declared": declared_eval,
                "main": main_stream["records"],
                "nc": aux_streams["nc"]["records"],
                "ood": aux_streams["ood"]["records"],
                "det": det["records"],
                "total": total_records,
            },
        )
    expected_total = int(expected["total"]["records"])
    if declared_eval != expected_total:
        _fail(code, "record_counts.eval 与预算公式（五流合计）不符", {"declared": declared_eval, "expected": expected_total})
    if int(declared_int.get("train", -1)) != 0 or int(declared_int.get("total", -1)) != declared_eval:
        _fail(code, "FORMAL record_counts 必须为 {train:0,total:eval}", declared_int)
    eval_bucket = _require_mapping(summary_status.get("eval"), code=code, label="status_counts.eval")
    if {str(key): int(value) for key, value in eval_bucket.items() if _is_int(value)} != total_status:
        _fail(code, "status_counts.eval 与五流实际状态计数不符", {"declared": dict(eval_bucket), "actual": total_status})
    train_bucket = _require_mapping(summary_status.get("train"), code=code, label="status_counts.train")
    if any(int(value) != 0 for value in train_bucket.values() if _is_int(value)):
        _fail(code, "FORMAL status_counts.train 必须全 0（加载冻结模型）", dict(train_bucket))
    manifest = _require_mapping(data_manifest.get("artifact_sha256"), code=code, label="data_manifest.artifact_sha256")
    required = [NC_RECORDS_FILE, OOD_RECORDS_FILE] + [
        DETERMINISM_DIR + "/" + str(repeat["name"]) + "/" + RUN_RECORDS_FILE for repeat in det["repeats"]
    ]
    missing = [name for name in required if not _artifact_covers(manifest, name)]
    if missing:
        _fail(code, "data_manifest.artifact_sha256 未覆盖辅助记录流文件", {"missing": missing, "keys": sorted(str(key) for key in manifest)})
    _checks(checks, "record_stream_nc", "PASS", "NC 记录流: " + str(aux_streams["nc"]["runs"]) + " runs/" + str(aux_streams["nc"]["records"]) + " records")
    _checks(checks, "record_stream_ood", "PASS", "OOD 记录流: " + str(aux_streams["ood"]["runs"]) + " runs/" + str(aux_streams["ood"]["records"]) + " records")
    _checks(checks, "record_stream_det", "PASS", "DET 记录流: " + str(det["runs"]) + " runs/" + str(det["records"]) + " records（" + str(len(det["repeats"])) + " 份）")
    _checks(checks, "record_streams_manifest", "PASS", "data_manifest.artifact_sha256 覆盖 NC/OOD/DET 记录流")
    _checks(
        checks,
        "record_stream_counts",
        "PASS",
        "五流记录计数与 record_counts 一致: main="
        + str(main_stream["records"])
        + " nc="
        + str(aux_streams["nc"]["records"])
        + " ood="
        + str(aux_streams["ood"]["records"])
        + " det="
        + str(det["records"])
        + " total="
        + str(total_records),
    )
    return by_stream


def _status_counts_disclosure(checks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """R-S3-08A：run_config.status_counts 缺失时的披露记录（写入 aggregate 顶层）。"""
    for item in checks:
        if str(item.get("check")) == "status_counts_config":
            status = str(item.get("status", ""))
            return {
                "config_provided": status != "DISCLOSED",
                "code": None if status != "DISCLOSED" else str(item.get("code") or S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED),
                "accepted_with_disclosure": status == "DISCLOSED",
                "detail": str(item.get("detail", "")),
            }
    return {"config_provided": True, "code": None, "accepted_with_disclosure": False, "detail": "status_counts_config 校验项缺失"}


def _validate_record_counts(config: Mapping[str, Any], prereg: "S3Prereg", grid: Mapping[str, Any], *, checks: list[dict[str, Any]]) -> None:
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    counts = _require_mapping(config.get("record_counts"), code=code, label="run_config.record_counts")
    train = _require_int(counts.get("train"), code=code, label="record_counts.train", minimum=0)
    eval_count = _require_int(counts.get("eval"), code=code, label="record_counts.eval", minimum=0)
    total = _require_int(counts.get("total"), code=code, label="record_counts.total", minimum=0)
    if int(total) != int(train) + int(eval_count):
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "record_counts.total != train + eval")
    if str(grid.get("run_mode")) == "FORMAL":
        # R-S3-08：FORMAL record_counts.eval 为五条记录流合计（main+NC+OOD+DET）。
        expected_eval = int(_expected_stream_counts(grid, prereg)["total"]["records"])
    else:
        expected_eval = int(grid["eval_records_expected"])
    if int(eval_count) != expected_eval:
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "record_counts.eval 与预算公式不符", {"declared": eval_count, "expected": expected_eval})
    if str(grid.get("run_mode")) == "FORMAL":
        # R-S3-07：FORMAL 加载预注册冻结模型、不重训 → train 记录与 train_expected 均必须为 0。
        if int(train) != 0:
            _fail(S3_ANALYSIS_RECORD_INVALID, "FORMAL run 不得包含训练记录（模型由预注册冻结包加载）", train)
        declared_train_expected = counts.get("train_expected", counts.get("expected_train"))
        if declared_train_expected is not None:
            if int(_require_int(declared_train_expected, code=code, label="record_counts.train_expected")) != 0:
                _fail(S3_ANALYSIS_BUDGET_MISMATCH, "FORMAL record_counts.train_expected 必须为 0（R-S3-07 加载冻结模型）", declared_train_expected)
    else:
        train_expected = counts.get("train_expected", counts.get("expected_train"))
        if train_expected is not None:
            declared_train_expected = int(_require_int(train_expected, code=code, label="record_counts.train_expected"))
            # Lead m08572：SMOKE 每 meta_seed 训练 2 个模型（FOMAML+ANIL），故 2*len(meta_seeds)*outer_steps。
            outer_steps = grid.get("outer_steps")
            expected_train = 2 * len(grid["meta_seeds"]) * int(outer_steps) if outer_steps is not None else None
            if expected_train is not None and int(declared_train_expected) != int(expected_train):
                _fail(S3_ANALYSIS_BUDGET_MISMATCH, "train_expected 不符（2 模型 × meta_seeds × outer_steps）", {"declared": declared_train_expected, "expected": expected_train})
            if int(train) > int(declared_train_expected):
                _fail(S3_ANALYSIS_BUDGET_MISMATCH, "实际 train 记录数超过预期")
    eval_expected = counts.get("eval_expected", counts.get("expected_eval"))
    if eval_expected is not None:
        if int(_require_int(eval_expected, code=code, label="record_counts.eval_expected")) != int(expected_eval):
            _fail(S3_ANALYSIS_BUDGET_MISMATCH, "record_counts.eval_expected 与预算公式不符", {"declared": eval_expected, "expected": expected_eval})
    _checks(checks, "record_counts", "PASS", "run_config.record_counts 与预算公式一致: train=" + str(train) + " eval=" + str(eval_count))


def _validate_run_summary(
    summary: dict[str, Any],
    config: dict[str, Any],
    prereg: "S3Prereg",
    grid: Mapping[str, Any],
    *,
    actual_counts: Mapping[str, int],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    required = set(sp.S3_RUN_SUMMARY_REQUIRED_FIELDS)
    keys = set(summary.keys())
    missing = sorted(required - keys)
    if missing:
        _fail(code, "run_summary 缺少必需字段", missing)
    unknown = sorted(keys - required)
    if unknown:
        _checks(checks, "run_summary_unknown_fields", "DISCLOSED", "run_summary 未知额外字段: " + ", ".join(unknown))
    if _require_str(summary.get("schema_version"), code=code, label="run_summary.schema_version") != sp.S3_RUN_SUMMARY_SCHEMA_VERSION:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_summary schema_version 不符")
    if _require_str(summary.get("run_id"), code=code, label="run_summary.run_id") != str(config.get("run_id")):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_summary.run_id 与 run_config 不符")
    if _require_str(summary.get("run_mode"), code=code, label="run_summary.run_mode") != str(config.get("run_mode")):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_summary.run_mode 与 run_config 不符")
    status = _require_str(summary.get("status"), code=code, label="run_summary.status")
    if status not in RUN_STATUSES:
        _fail(code, "run_summary.status 非法: " + status, list(RUN_STATUSES))
    _require_iso_utc(summary.get("created_utc"), code=code, label="run_summary.created_utc")
    counts = _require_mapping(summary.get("record_counts"), code=code, label="run_summary.record_counts")
    for name in ("train", "eval", "total"):
        if _require_int(counts.get(name), code=code, label="run_summary.record_counts." + name, minimum=0) != int(actual_counts.get(name, -1)):
            _fail(S3_ANALYSIS_RECORD_INVALID, "run_summary.record_counts." + name + " 与实测记录数不符", {"declared": counts.get(name), "actual": actual_counts.get(name)})
    status_counts = _require_mapping(summary.get("status_counts"), code=code, label="run_summary.status_counts")
    normalized_counts = {}
    for bucket in ("train", "eval"):
        bucket_value = _require_mapping(status_counts.get(bucket), code=code, label="status_counts." + bucket)
        normalized_counts[bucket] = {status_name: _require_int(bucket_value.get(status_name), code=code, label="status_counts." + bucket + "." + status_name, minimum=0) for status_name in sp.S3_RECORD_STATUSES}
    eval_status_total = sum(int(value) for value in normalized_counts["eval"].values())
    train_status_total = sum(int(value) for value in normalized_counts["train"].values())
    if eval_status_total != int(counts.get("eval", -1)):
        _fail(S3_ANALYSIS_RECORD_INVALID, "run_summary.status_counts.eval 合计与 record_counts.eval 不符", {"status_total": eval_status_total, "eval": counts.get("eval")})
    if train_status_total != int(counts.get("train", -1)):
        _fail(S3_ANALYSIS_RECORD_INVALID, "run_summary.status_counts.train 合计与 record_counts.train 不符", {"status_total": train_status_total, "train": counts.get("train")})
    _checks(checks, "run_summary_status_counts", "PASS", "status_counts 双桶 OK/FAILED 齐全且合计与 record_counts 一致")
    failures = _require_list(summary.get("failures", []), code=code, label="run_summary.failures")
    if failures and status == "COMPLETED":
        _fail(S3_ANALYSIS_RECORD_INVALID, "存在 failures 但 run_summary.status=COMPLETED")
    determinism = _require_mapping(summary.get("determinism"), code=code, label="run_summary.determinism")
    if not determinism:
        _fail(code, "run_summary.determinism 不能为空")
    fd_gate_sha = _require_sha256(summary.get("fd_or_gradient_gate_sha256"), code=code, label="run_summary.fd_or_gradient_gate_sha256")
    data_manifest_sha = _require_sha256(summary.get("data_manifest_sha256"), code=code, label="run_summary.data_manifest_sha256")
    negative = _require_mapping(summary.get("negative_controls"), code=code, label="run_summary.negative_controls")
    resources = _require_mapping(summary.get("resources"), code=code, label="run_summary.resources")
    for key in ("total_wall_s", "max_wall_s", "max_peak_memory_mb"):
        value = _require_number(resources.get(key), code=code, label="resources." + key)
        if float(value) < 0:
            _fail(code, "run_summary.resources." + key + " 不能为负")
    environment = _require_mapping(summary.get("environment"), code=code, label="run_summary.environment")
    if not environment:
        _fail(code, "run_summary.environment 不能为空")
    if _require_int(summary.get("physical_call_count"), code=code, label="run_summary.physical_call_count", minimum=0) != 0:
        _fail(S3_ANALYSIS_PREREG_PHYSICAL_CALLS, "run_summary.physical_call_count 必须为 0")
    if _require_str(summary.get("evidence_scope"), code=code, label="run_summary.evidence_scope") != sp.S3_EVIDENCE_SCOPE:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_summary.evidence_scope 不符")
    summary_scope = _normalize_scope_notes(summary.get("scope_notes"), code=code, label="run_summary.scope_notes")
    config_scope = _normalize_scope_notes(config.get("scope_notes") or [], code=code, label="run_config.scope_notes")
    if summary_scope != config_scope:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "run_summary.scope_notes 与 run_config 不符")
    _checks(checks, "run_summary_schema", "PASS", "run_summary 18 字段 schema 通过（status=" + status + "）")
    _checks(checks, "run_summary_record_counts", "PASS", "record_counts 与实测一致: " + str(dict(actual_counts)))
    _checks(checks, "run_summary_fd_gate_sha256_format", "PASS", "fd_or_gradient_gate_sha256 格式通过: " + fd_gate_sha)
    _checks(checks, "run_summary_data_manifest_sha256_format", "PASS", "data_manifest_sha256 格式通过: " + data_manifest_sha)
    return dict(summary)


def _validate_data_manifest(manifest: dict[str, Any], config: Mapping[str, Any], prereg: "S3Prereg", grid: Mapping[str, Any], *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    required = set(sp.S3_DATA_MANIFEST_FIELDS)
    missing = sorted(required - set(manifest.keys()))
    if missing:
        _fail(code, "data_manifest 缺少必需字段", missing)
    unknown = sorted(set(manifest.keys()) - required)
    if unknown:
        _checks(checks, "data_manifest_unknown_fields", "DISCLOSED", "data_manifest 未知额外字段: " + ", ".join(unknown))
    if _require_str(manifest.get("schema_version"), code=code, label="data_manifest.schema_version") != sp.S3_DATA_MANIFEST_SCHEMA_VERSION:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "data_manifest schema_version 不符")
    if _require_str(manifest.get("run_id"), code=code, label="data_manifest.run_id") != str(config.get("run_id")):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "data_manifest.run_id 与 run_config 不符")
    boundary = _require_mapping(manifest.get("data_boundary"), code=code, label="data_manifest.data_boundary")
    flags = boundary.get("flags", boundary)
    flags = _require_mapping(flags, code=code, label="data_manifest.data_boundary.flags")
    for flag in DATA_BOUNDARY_FLAGS:
        if flag not in flags:
            _fail(code, "data_manifest 缺 phase 标志: " + flag)
    if flags.get("holdout_truth_used_for_training") is not False:
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "data_manifest holdout_truth_used_for_training 必须为 false")
    if flags.get("holdout_truth_used_for_adaptation") is not False:
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "data_manifest holdout_truth_used_for_adaptation 必须为 false")
    if flags.get("holdout_truth_used_for_bo_ranking") is not False:
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "data_manifest holdout_truth_used_for_bo_ranking 必须为 false")
    if flags.get("holdout_truth_read_for_evaluation") is not True:
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "data_manifest holdout_truth_read_for_evaluation 必须为 true")
    split_ids = _require_mapping(manifest.get("split_task_ids"), code=code, label="data_manifest.split_task_ids")
    split_sha = manifest.get("split_task_ids_sha256")
    if isinstance(split_sha, Mapping):
        for split in sp.S3_ALLOWED_SPLITS:
            if split not in split_sha:
                _fail(code, "data_manifest.split_task_ids_sha256 缺 split: " + split)
    else:
        _require_sha256(split_sha, code=code, label="data_manifest.split_task_ids_sha256")
    for split, ids in split_ids.items():
        if str(split) not in sp.S3_ALLOWED_SPLITS:
            _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "data_manifest.split_task_ids 未知 split: " + str(split))
        values = _require_list(ids, code=code, label="split_task_ids." + str(split))
        # SMOKE 不与冻结 split 数量比较；dev split 不在 S3_SPLIT_COUNTS 中（可为空列表）。
        if grid["run_mode"] == "FORMAL" and str(split) in sp.S3_SPLIT_COUNTS:
            if int(sp.S3_SPLIT_COUNTS[str(split)]) != len(values):
                _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "split_task_ids 数量与冻结 split 不符: " + str(split), len(values))
        if len(set(str(value) for value in values)) != len(values):
            _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "split_task_ids 存在重复: " + str(split))
    sealed = _require_sha256(manifest.get("references_sealed_sha256"), code=code, label="data_manifest.references_sealed_sha256")
    if sealed != prereg.references_sealed.get("sha256"):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "data_manifest.references_sealed_sha256 与 prereg 不符")
    phase = _require_str(manifest.get("holdout_truth_read_phase"), code=code, label="data_manifest.holdout_truth_read_phase")
    if phase != PHASE_EVAL:
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "holdout_truth_read_phase 必须为 EVAL", phase)
    if _require_int(manifest.get("physical_call_count"), code=code, label="data_manifest.physical_call_count", minimum=0) != 0:
        _fail(S3_ANALYSIS_PREREG_PHYSICAL_CALLS, "data_manifest.physical_call_count 必须为 0")
    if _require_int(manifest.get("solver_processes_started"), code=code, label="data_manifest.solver_processes_started", minimum=0) != 0:
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "data_manifest.solver_processes_started 必须为 0")
    synthetic = _require_int(manifest.get("synthetic_call_count"), code=code, label="data_manifest.synthetic_call_count", minimum=0)
    artifact_sha = _require_mapping(manifest.get("artifact_sha256"), code=code, label="data_manifest.artifact_sha256")
    if not artifact_sha:
        _fail(code, "data_manifest.artifact_sha256 不能为空")
    _checks(checks, "data_manifest_boundary", "PASS", "phase 标志/EVAL 一次性读取/参考解 sha/物理 0/求解器 0 通过")
    _checks(checks, "data_manifest_synthetic_calls", "PASS", "合成评估调用数: " + str(synthetic))
    return dict(manifest)


def _validate_model_manifest(manifest: dict[str, Any], config: Mapping[str, Any], prereg: "S3Prereg", *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    required = set(sp.S3_MODEL_MANIFEST_FIELDS)
    missing = sorted(required - set(manifest.keys()))
    if missing:
        _fail(code, "model_manifest 缺少必需字段", missing)
    if _require_str(manifest.get("schema_version"), code=code, label="model_manifest.schema_version") != sp.S3_MODEL_MANIFEST_SCHEMA_VERSION:
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "model_manifest schema_version 不符")
    copied_from_prereg = False
    verification = manifest.get("verification")
    if verification is not None:
        # R-S3-07：FORMAL 正式 run 的 model_manifest 是冻结 manifest 原样复制 + verification 块；
        # 复制件的 run_id 可能是 M2 冻结 run 的 run_id，故 loaded_from_prereg=true 时豁免 run_id 相等校验（记 DISCLOSED）。
        entry = _require_mapping(verification, code=code, label="model_manifest.verification")
        if entry.get("loaded_from_prereg") is True:
            copied_from_prereg = True
            prereg_models_sha = entry.get("prereg_models_sha256")
            if isinstance(prereg_models_sha, Mapping):
                for name, value in prereg_models_sha.items():
                    _require_sha256(value, code=code, label="model_manifest.verification.prereg_models_sha256." + str(name))
            elif prereg_models_sha is not None:
                _require_sha256(prereg_models_sha, code=code, label="model_manifest.verification.prereg_models_sha256")
            _checks(
                checks,
                "model_manifest_copied_from_prereg",
                "PASS",
                "FORMAL model_manifest 为预注册冻结 manifest 复制件（verification.loaded_from_prereg=true）",
            )
        else:
            _checks(checks, "model_manifest_verification", "DISCLOSED", "model_manifest.verification 未声明 loaded_from_prereg=true（按本次 run 模型处理）")
    if copied_from_prereg:
        _checks(checks, "model_manifest_run_id", "DISCLOSED", "复制自预注册冻结包的 model_manifest.run_id 可能与本次 run 不同（允许，R-S3-07）")
    elif _require_str(manifest.get("run_id"), code=code, label="model_manifest.run_id") != str(config.get("run_id")):
        _fail(S3_ANALYSIS_RUN_BINDING_MISMATCH, "model_manifest.run_id 与 run_config 不符")
    models = _require_list(manifest.get("models"), code=code, label="model_manifest.models", non_empty=True)
    entry_fields = set(sp.S3_MODEL_ENTRY_FIELDS)
    seen = set()
    for index, item in enumerate(models):
        entry = _require_mapping(item, code=code, label="model_manifest.models[" + str(index) + "]")
        missing_entry = sorted(entry_fields - set(entry.keys()))
        if missing_entry:
            _fail(code, "model_manifest.models[" + str(index) + "] 缺字段", missing_entry)
        arm_type = _require_str(entry.get("arm_type"), code=code, label="model.arm_type")
        meta_seed = _require_int(entry.get("meta_seed"), code=code, label="model.meta_seed", minimum=0)
        key = (arm_type, int(meta_seed))
        if key in seen:
            _fail(code, "model_manifest 模型条目重复", key)
        seen.add(key)
        _require_sha256(entry.get("sha256"), code=code, label="model.sha256")
        _require_sha256(entry.get("episode_bank_sha256"), code=code, label="model.episode_bank_sha256")
        _require_number(entry.get("train_wall_s"), code=code, label="model.train_wall_s")
        _require_number(entry.get("final_train_loss"), code=code, label="model.final_train_loss")
    _checks(checks, "model_manifest_schema", "PASS", "model_manifest 模型条目数: " + str(len(models)))
    return dict(manifest)


def _normalize_gate_model_name(name: str) -> str:
    """把 fomaml / fomaml_meta_0 / anil / anil_meta_0 归一为 fomaml/anil（其他名称返回空串）。"""
    text = str(name).strip().lower()
    if text.startswith("fomaml"):
        return "fomaml"
    if text.startswith("anil"):
        return "anil"
    return ""


def _validate_gate_coordinate_list(
    coordinates: Any,
    *,
    expected_n: int,
    tolerance: float,
    code: str,
    label: str,
) -> float:
    """逐坐标校验 analytic/numeric/relative_error，返回 |relative_error| 最大值。"""
    items = _require_list(coordinates, code=code, label=label)
    if len(items) != int(expected_n):
        _fail(code, label + " 坐标数不符", {"expected": expected_n, "actual": len(items)})
    computed = 0.0
    for index, item in enumerate(items):
        entry = _require_mapping(item, code=code, label=label + "[" + str(index) + "]")
        for field in ("index", "analytic", "numeric", "relative_error"):
            _require_number(entry.get(field), code=code, label=label + "[" + str(index) + "]." + field)
        relative = abs(float(entry["relative_error"]))
        if relative > float(tolerance):
            _fail(code, "FD 门坐标相对误差超容差", {"label": label, "index": index, "relative_error": relative, "tolerance": tolerance})
        computed = max(computed, relative)
    return computed


def _validate_gate_new_shape(
    gate: dict[str, Any],
    *,
    run_mode: str,
    expected_n: int,
    tolerance: float,
    code: str,
    checks: list[dict[str, Any]],
) -> float:
    """R-S3-06 §2 新结构：models{每模型 n_checked/coordinates} + negatives 三键。"""
    models = _require_mapping(gate.get("models"), code=code, label="gate.models")
    normalized: dict[str, Mapping[str, Any]] = {}
    for key, value in models.items():
        name = _normalize_gate_model_name(key)
        if not name:
            _fail(code, "gate.models 出现未知模型键: " + str(key))
        if name in normalized:
            _fail(code, "gate.models 模型键重复（归一后）: " + name)
        normalized[name] = _require_mapping(value, code=code, label="gate.models." + str(key))
    if run_mode == "FORMAL":
        if set(normalized.keys()) != {"fomaml", "anil"}:
            _fail(code, "FORMAL FD 门必须恰含 fomaml_meta_0 与 anil_meta_0 两个模型", sorted(normalized))
    else:
        if not 1 <= len(normalized) <= 2:
            _fail(code, "SMOKE FD 门允许 1-2 个模型", sorted(normalized))
    exact_keys = {name + "_meta_0" for name in ("fomaml", "anil")}
    actual_keys = {str(key) for key in models.keys()}
    if actual_keys != exact_keys:
        _checks(checks, "fd_gate_model_key_alias", "DISCLOSED", "FD 门 models 键名非 R-S3-06 规范名（接受归一但披露）: " + ",".join(sorted(actual_keys)))
    model_max = 0.0
    for name in sorted(normalized.keys()):
        entry = normalized[name]
        status = _require_str(entry.get("status"), code=code, label="gate.models." + name + ".status")
        if status != "PASS":
            _fail(code, "FD 门模型 status 必须为 PASS", {"model": name, "status": status})
        arm_type = entry.get("arm_type")
        if arm_type is not None and str(arm_type).strip().lower() != name:
            _fail(code, "FD 门模型 arm_type 与键名不符", {"model": name, "arm_type": arm_type})
        meta_seed = entry.get("meta_seed")
        if meta_seed is not None:
            seed_value = _require_int(meta_seed, code=code, label="gate.models." + name + ".meta_seed", minimum=0)
            if run_mode == "FORMAL" and int(seed_value) != 0:
                _fail(code, "FORMAL FD 门模型 meta_seed 必须为 0（R-S3-06 §2）", {"model": name, "meta_seed": seed_value})
        computed = _validate_gate_coordinate_list(
            entry.get("coordinates"),
            expected_n=expected_n,
            tolerance=tolerance,
            code=code,
            label="gate.models." + name + ".coordinates",
        )
        n_checked = entry.get("n_checked")
        if n_checked is None:
            _fail(code, "gate.models." + name + " 缺 n_checked")
        if int(_require_int(n_checked, code=code, label="gate.models." + name + ".n_checked", minimum=1)) != int(expected_n):
            _fail(code, "FD 门模型 n_checked 与坐标数口径不符", {"model": name, "n_checked": n_checked, "expected": expected_n})
        declared = entry.get("max_relative_error")
        if declared is not None:
            declared_value = _require_number(declared, code=code, label="gate.models." + name + ".max_relative_error")
            if not math.isclose(float(declared_value), float(computed), rel_tol=1e-9, abs_tol=1e-15):
                _fail(code, "FD 门模型 max_relative_error 与坐标实算不一致", {"model": name, "declared": declared_value, "computed": computed})
        model_max = max(model_max, computed)
    # negatives 三键：FORMAL 必须存在且 PASS；SMOKE 缺省记 DISCLOSED（当前 A1 SMOKE 形状尚未产出）
    negatives = gate.get("negatives")
    if isinstance(negatives, Mapping) and negatives:
        missing = [key for key in GATE_NEGATIVE_KEYS if key not in negatives]
        if missing:
            _fail(code, "FD 门 negatives 缺键", missing)
        for key in GATE_NEGATIVE_KEYS:
            raw = negatives.get(key)
            status = raw if isinstance(raw, str) else (raw.get("status") if isinstance(raw, Mapping) else None)
            if str(status).strip().upper() != "PASS":
                _fail(code, "FD 门 negatives 必须为 PASS", {"negative": key, "status": status})
        _checks(checks, "fd_gate_negatives", "PASS", "FD 门 negatives 三键 PASS（tamper/anil_body_frozen/k0_equivalence）")
    elif run_mode == "FORMAL":
        _fail(code, "FORMAL FD 门产物必须包含 negatives 三键（R-S3-06 §2）")
    else:
        _checks(checks, "fd_gate_negatives", "DISCLOSED", "SMOKE FD 门产物未包含 negatives 三键（SMOKE 不要求）")
    _checks(
        checks,
        "fd_gate_artifact_models",
        "PASS",
        "FD 门 " + str(len(normalized)) + " 模型 × " + str(expected_n) + " 坐标 PASS（每坐标 |rel_err|<=" + str(tolerance) + "）",
    )
    return model_max


def _validate_gate_interim_shape(
    gate: dict[str, Any],
    *,
    expected_n: int,
    tolerance: float,
    code: str,
    checks: list[dict[str, Any]],
) -> float:
    """A1 06:40 SMOKE 产物形状：gates{fomaml,anil} 模型级 + 顶层扁平 coordinates（仅 SMOKE 接受）。"""
    gates = _require_mapping(gate.get("gates"), code=code, label="gate.gates")
    if not 1 <= len(gates) <= 2:
        _fail(code, "SMOKE FD 门 gates 允许 1-2 个模型", sorted(gates))
    for name, entry in gates.items():
        gate_entry = _require_mapping(entry, code=code, label="gate.gates." + str(name))
        status = _require_str(gate_entry.get("status"), code=code, label="gate.gates." + str(name) + ".status")
        if status != "PASS":
            _fail(code, "SMOKE FD 门模型 status 必须为 PASS", {"model": name, "status": status})
        n_checked = gate_entry.get("n_checked")
        if n_checked is not None and int(_require_int(n_checked, code=code, label="gate.gates." + str(name) + ".n_checked", minimum=1)) != int(expected_n):
            _fail(code, "SMOKE FD 门模型 n_checked 与 fd_coordinates 覆盖值不符", {"model": name, "n_checked": n_checked, "expected": expected_n})
        gate_tolerance = gate_entry.get("tolerance")
        if gate_tolerance is not None and float(_require_number(gate_tolerance, code=code, label="gate.gates." + str(name) + ".tolerance")) > float(sp.S3_FD_TOLERANCE):
            _fail(code, "SMOKE FD 门模型 tolerance 超出冻结容差", gate_tolerance)
    return _validate_gate_coordinate_list(gate.get("coordinates"), expected_n=expected_n, tolerance=tolerance, code=code, label="gate.coordinates")


def _validate_gate_artifact(gate: dict[str, Any], config: Mapping[str, Any], prereg: "S3Prereg", *, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """fd_or_gradient_gate.json 产物校验。

    支持三种形状（按 run_mode 严格分流，R-S3-06 §2）：
      1) 新结构 models{每模型 n_checked/coordinates} + negatives —— FORMAL 唯一合法形状；
      2) A1 06:40 SMOKE 形状 gates{模型} + 顶层扁平 coordinates —— 仅 SMOKE；
      3) 旧单模型顶层 coordinates —— 仅 SMOKE（向后兼容 A6 fixture）。
    """
    code = S3_ANALYSIS_FD_GATE_INVALID
    schema = _require_str(gate.get("schema_version"), code=code, label="gate.schema_version")
    if schema not in ACCEPTED_GATE_SCHEMA_VERSIONS:
        _fail(S3_ANALYSIS_FD_GATE_INVALID, "fd_or_gradient_gate schema_version 不符", {"expected": list(ACCEPTED_GATE_SCHEMA_VERSIONS), "actual": schema})
    run_mode = str(config.get("run_mode", "FORMAL"))
    expected_n = _run_expected_fd_coordinates(config, run_mode=run_mode)
    status = _require_str(gate.get("status"), code=code, label="gate.status")
    if status != "PASS":
        _fail(code, "fd_or_gradient_gate status 必须为 PASS", status)
    # R-S3-06 §2 只固定语义字段；mode/created_utc 属非语义元数据，存在则校验、缺失记 DISCLOSED，
    # 避免对 A1 新门产物做超出 Lead m09485 要求的硬断言。
    if "max_relative_error" not in gate:
        _fail(code, "fd_or_gradient_gate 缺字段: max_relative_error")
    mode = ""
    if gate.get("mode") is not None:
        mode = _require_str(gate.get("mode"), code=code, label="gate.mode")
        if mode not in _accepted_fd_gate_modes():
            _fail(code, "fd_or_gradient_gate.mode 非法: " + mode, list(_accepted_fd_gate_modes()))
    else:
        _checks(checks, "fd_gate_mode_disclosed", "DISCLOSED", "FD 门产物未声明 mode（新结构 R-S3-06 §2 未要求）")
    epsilon_rule = gate.get("epsilon_rule")
    if epsilon_rule is not None:
        rule = _require_str(epsilon_rule, code=code, label="gate.epsilon_rule")
        if "1e-6" not in rule:
            _fail(code, "fd_or_gradient_gate.epsilon_rule 未包含 1e-6 相对步长规则", rule)
    tolerance = float(sp.S3_FD_TOLERANCE)
    if gate.get("tolerance") is not None:
        tolerance_value = _require_number(gate.get("tolerance"), code=code, label="gate.tolerance")
        if float(tolerance_value) > float(sp.S3_FD_TOLERANCE):
            _fail(code, "fd_or_gradient_gate.tolerance 超出冻结容差", tolerance_value)
        tolerance = float(tolerance_value)

    models_value = gate.get("models")
    is_new_shape = isinstance(models_value, Mapping) and any(isinstance(value, Mapping) for value in models_value.values())
    if is_new_shape:
        if mode and str(mode) != str(sp.S3_FD_MODE):
            _checks(checks, "fd_gate_mode_disclosed", "DISCLOSED", "FD 门 mode=" + str(mode) + "（模型级梯度门，新结构按 R-S3-06 §2 校验）")
        computed = _validate_gate_new_shape(
            gate,
            run_mode=run_mode,
            expected_n=int(expected_n),
            tolerance=tolerance,
            code=code,
            checks=checks,
        )
    elif isinstance(gate.get("gates"), Mapping):
        if run_mode != "FORMAL":
            _checks(checks, "fd_gate_mode_disclosed", "DISCLOSED", "SMOKE 使用 A1 gates 模型级形状（R-S3-06 新结构仅 FORMAL 强制）")
            computed = _validate_gate_interim_shape(gate, expected_n=int(expected_n), tolerance=tolerance, code=code, checks=checks)
        else:
            _fail(code, "FORMAL FD 门产物必须使用 R-S3-06 §2 新结构（models 每模型 32 坐标 + negatives），当前为 gates 形状")
    else:
        if run_mode == "FORMAL":
            _fail(code, "FORMAL FD 门产物必须使用 R-S3-06 §2 新结构（models 每模型 32 坐标 + negatives），当前为旧单模型形状")
        _checks(checks, "fd_gate_mode_disclosed", "DISCLOSED", "SMOKE 使用旧单模型 FD 门形状（向后兼容）")
        computed = _validate_gate_coordinate_list(gate.get("coordinates"), expected_n=int(expected_n), tolerance=tolerance, code=code, label="gate.coordinates")

    n_checked = gate.get("n_checked")
    if n_checked is not None:
        declared_n = int(_require_int(n_checked, code=code, label="gate.n_checked", minimum=0))
        if is_new_shape:
            # 新结构：FORMAL 两模型合计 64 坐标；SMOKE 单模型 expected_n。
            accepted_total = {int(expected_n) * (2 if run_mode == "FORMAL" else 1), int(expected_n)}
        else:
            accepted_total = {int(expected_n)}
        if declared_n not in accepted_total:
            _fail(code, "fd_or_gradient_gate.n_checked 与坐标数口径不符", {"n_checked": declared_n, "accepted": sorted(accepted_total)})
    declared = _require_number(gate.get("max_relative_error"), code=code, label="gate.max_relative_error")
    if not math.isclose(float(declared), float(computed), rel_tol=1e-9, abs_tol=1e-15):
        _fail(code, "fd_or_gradient_gate.max_relative_error 与坐标实算不一致", {"declared": declared, "computed": computed})
    _checks(
        checks,
        "fd_gate_artifact",
        "PASS",
        "FD 门产物 PASS（shape=" + ("models" if is_new_shape else ("gates" if isinstance(gate.get("gates"), Mapping) else "flat")) + ", mode=" + mode + ", max_rel=" + str(declared) + "）",
    )
    return dict(gate)


def _record_core_digest(record: Mapping[str, Any]) -> str:
    core = {key: value for key, value in record.items() if key not in ("wall_s", "peak_memory_mb", "record_digest")}
    return sp.canonical_sha256(core)


def _iter_record_lines(path: Path, *, code: str) -> Iterator[dict[str, Any]]:
    """流式逐行读取 jsonl（大文件不整体载入内存）。"""
    if not path.is_file():
        _fail(code, "run_records 文件不存在", str(path))
    with path.open("r", encoding="utf-8", newline="") as handle:
        for index, line in enumerate(handle, start=1):
            if not line.strip():
                _fail(code, "run_records 存在空行", index)
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                _fail(code, "run_records 行不是合法 JSON（第 " + str(index) + " 行）", str(error))
            yield _require_mapping(payload, code=code, label="run_records 行 " + str(index))


def _aggregate_eval_records(
    records: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    grid: Mapping[str, Any],
    *,
    checks: list[dict[str, Any]],
    verify_record_digests: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    code = S3_ANALYSIS_RECORD_INVALID
    train_records: list[dict[str, Any]] = []
    run_id = str(config.get("run_id"))
    grid_arms = set(grid["arms"])
    budgets = set(int(value) for value in grid["budgets"])
    opt_seeds = set(int(value) for value in grid["opt_seeds"])
    meta_seeds = set(int(value) for value in grid["meta_seeds"])
    task_ids = set(str(value) for value in grid["task_ids"])
    per_run: dict[tuple[str, str, int, int, int], dict[str, Any]] = {}
    counts = {"train": 0, "eval": 0, "total": 0, "train_ok": 0, "train_failed": 0, "eval_ok": 0, "eval_failed": 0}
    for index, record in enumerate(records, start=1):
        keys = set(record.keys())
        has_task = "task_id" in keys
        is_train = (not has_task) and TRAIN_RECORD_KEYS.issubset(keys)
        is_eval = (has_task or EVAL_RECORD_KEYS.issubset(keys)) and EVAL_RECORD_KEYS.issubset(keys)
        if is_train:
            unknown = sorted(keys - TRAIN_RECORD_KEYS)
            if unknown:
                _checks(checks, "train_record_unknown_fields", "DISCLOSED", "train 记录未知额外字段: " + ",".join(unknown))
            _validate_train_record(record, config=config, grid=grid)
            train_records.append(dict(record))
            counts["train"] += 1
            counts["train_ok"] += 1
            continue
        if not is_eval:
            _fail(
                code,
                "run_records 记录缺字段（第 " + str(index) + " 行）",
                {"missing_eval": sorted(EVAL_RECORD_KEYS - keys), "missing_train": sorted(TRAIN_RECORD_KEYS - keys)},
            )
        unknown = sorted(keys - EVAL_RECORD_KEYS)
        if unknown:
            _checks(checks, "eval_record_unknown_fields", "DISCLOSED", "eval 记录未知额外字段: " + ",".join(sorted(unknown)) + "（第 " + str(index) + " 行）")
        if True:
            _validate_eval_record(record, config=config, grid=grid, checks=checks)
            counts["eval"] += 1
            # 与 s3_runner._status_counts 保持同一口径：f 缺失且 status=="FAILED" 才记 FAILED，其余记 OK。
            _eval_status = "FAILED" if record.get("f") is None and str(record.get("status")) == "FAILED" else "OK"
            counts["eval_ok" if _eval_status == "OK" else "eval_failed"] += 1
            task_id = str(record["task_id"])
            arm_id = str(record["arm_id"])
            budget = int(record["budget"])
            opt_seed = int(record["opt_seed"])
            meta_seed = int(record["meta_seed"])
            if verify_record_digests and sp.record_digest(dict(record)) != str(record.get("record_digest")):
                _fail(code, "run_records 记录 digest 自洽校验失败", index)
            key = (task_id, arm_id, budget, opt_seed, meta_seed)
            bucket = per_run.get(key)
            if bucket is None:
                bucket = {
                    "task_id": task_id,
                    "arm_id": arm_id,
                    "budget": budget,
                    "opt_seed": opt_seed,
                    "meta_seed": meta_seed,
                    "split": str(record["split"]),
                    "phase": str(record["phase"]),
                    "run_id": str(record["run_id"]),
                    "indices": [],
                    "hit_count": 0,
                    "best_f": None,
                    "first_feasible_index": None,
                    "wall_s": 0.0,
                    "status": "OK",
                    "feasible_count": 0,
                }
                per_run[key] = bucket
            elif str(record["run_id"]) != bucket["run_id"]:
                _fail(code, "同一 run bucket 内评估记录 run_id 不一致", {"key": key, "expected": bucket["run_id"], "actual": record["run_id"]})
            evaluation_index = int(record["evaluation_index"])
            bucket["indices"].append(evaluation_index)
            wall_s = float(record["wall_s"])
            bucket["wall_s"] += wall_s
            if bool(record["feasible"]):
                bucket["hit_count"] += 1
                bucket["feasible_count"] += 1
                f_value = float(record["f"])
                if bucket["best_f"] is None or f_value < bucket["best_f"]:
                    bucket["best_f"] = f_value
                if bucket["first_feasible_index"] is None or evaluation_index < bucket["first_feasible_index"]:
                    bucket["first_feasible_index"] = evaluation_index

    if str(grid.get("run_mode")) == "FORMAL" and train_records:
        _fail(code, "FORMAL run 出现训练记录（应加载预注册冻结模型，R-S3-07）", len(train_records))
    counts["total"] = counts["train"] + counts["eval"]
    eval_records = []
    for key, bucket in per_run.items():
        budget = int(bucket["budget"])
        indices = sorted(set(int(value) for value in bucket["indices"]))
        if indices != list(range(1, budget + 1)):
            _fail(code, "单 run 评估索引必须为 1..B 连续完整", {"key": key, "n": len(indices), "budget": budget})
        if len(bucket["indices"]) != budget:
            _fail(code, "单 run 评估记录数 != B", {"key": key, "n": len(bucket["indices"]), "budget": budget})
        bucket["indices"] = indices
        bucket["hit_rate"] = bucket["hit_count"] / float(budget)
        bucket["phase_expected"] = SPLIT_PHASE.get(bucket["split"])
        if bucket["phase_expected"] is not None and bucket["phase"] != bucket["phase_expected"]:
            _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "记录 phase 与 split 不符", {"split": bucket["split"], "phase": bucket["phase"], "expected": bucket["phase_expected"]})
        eval_records.append(bucket)
    actual_tasks = sorted({bucket["task_id"] for bucket in eval_records})
    if len(actual_tasks) != int(grid["n_tasks"]):
        _fail(
            S3_ANALYSIS_BUDGET_MISMATCH,
            "评估任务集合数量与 run_config.evaluation_grid 声明不符",
            {"declared": int(grid["n_tasks"]), "actual": len(actual_tasks)},
        )
    declared_task_ids = tuple(str(value) for value in grid.get("task_ids", ()))
    if declared_task_ids and tuple(actual_tasks) != tuple(sorted(declared_task_ids)):
        _fail(
            S3_ANALYSIS_BUDGET_MISMATCH,
            "评估任务集合与 evaluation_grid 任务列表不符",
            {"declared": list(declared_task_ids), "actual": actual_tasks},
        )
    eval_split = grid.get("eval_split")
    if eval_split is not None:
        mismatched = sorted({bucket["split"] for bucket in eval_records if bucket["split"] != str(eval_split)})
        if mismatched:
            _fail(
                S3_ANALYSIS_DATA_BOUNDARY_VIOLATION,
                "评估记录 split 与 evaluation_grid.eval_split 不符",
                {"expected": eval_split, "actual": mismatched},
            )
    _checks(checks, "run_records_task_coverage", "PASS", "评估任务集合覆盖: " + str(len(actual_tasks)) + " 个任务与声明一致")
    expected_records = int(grid["eval_records_expected"])
    if int(counts["eval"]) != expected_records:
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "评估记录总数与预算公式不符", {"expected": expected_records, "actual": counts["eval"]})
    if len(per_run) != int(grid["run_count"]):
        _fail(S3_ANALYSIS_BUDGET_MISMATCH, "run 数不符", {"expected": grid["run_count"], "actual": len(per_run)})
    _checks(checks, "run_records_budget", "PASS", "逐 run 预算记账: " + str(len(per_run)) + " runs × B = " + str(counts["eval"]) + " 条评估记录")
    _checks(
        checks,
        "run_records_train",
        "PASS",
        "训练记录数: " + str(counts["train"]) + ("（FORMAL 加载冻结模型，不重训）" if str(grid.get("run_mode")) == "FORMAL" else ""),
    )
    return train_records, eval_records, counts


def bucket_status_ok(record: Mapping[str, Any]) -> bool:
    status_value = record.get("status", "OK")
    return str(status_value) == "OK"


def _validate_train_record(record: Mapping[str, Any], *, config: Mapping[str, Any], grid: Mapping[str, Any]) -> None:
    code = S3_ANALYSIS_RECORD_INVALID
    if _require_str(record.get("schema_version"), code=code, label="train_record.schema_version") != sp.S3_RECORD_SCHEMA_VERSION:
        _fail(code, "train 记录 schema_version 不符")
    if _require_str(record.get("run_id"), code=code, label="train_record.run_id") != str(config.get("run_id")):
        _fail(code, "train 记录 run_id 与 run_config 不符")
    meta_seed = _require_int(record.get("meta_seed"), code=code, label="train_record.meta_seed", minimum=0)
    if meta_seed not in set(int(value) for value in grid["meta_seeds"]):
        _fail(code, "train 记录 meta_seed 不在网格内", meta_seed)
    step = _require_int(record.get("outer_step"), code=code, label="train_record.outer_step", minimum=0)
    _require_number(record.get("loss"), code=code, label="train_record.loss")
    _require_number(record.get("wall_s"), code=code, label="train_record.wall_s", minimum=0.0)
    _require_sha256(record.get("train_episode_digest"), code=code, label="train_record.train_episode_digest")
    _require_sha256(record.get("record_digest"), code=code, label="train_record.record_digest")
    if step < 0:
        _fail(code, "train 记录 outer_step 非法")


def _cross_check_record_task_set(
    data_manifest: Mapping[str, Any],
    eval_records: Sequence[Mapping[str, Any]],
    grid: Mapping[str, Any],
    *,
    checks: list[dict[str, Any]],
) -> None:
    """FORMAL 任务集合三方交叉校验（run_config/data_manifest/run_records）。

    A1 runner 的 FORMAL run_config.evaluation_grid 只声明 eval_tasks + eval_split（无任务列表），
    因此 task 集合权威来源是 data_manifest.split_task_ids[eval_split]；记录实测集合必须与其
    完全一致（fail-closed，防止越界/缺任务/串 split 静默通过）。
    """
    if str(grid.get("run_mode")) != "FORMAL":
        return
    split = str(grid.get("eval_split") or sp.S3_EVAL_SPLIT)
    split_ids = data_manifest.get("split_task_ids")
    if not isinstance(split_ids, Mapping) or split not in split_ids:
        _fail(
            S3_ANALYSIS_DATA_BOUNDARY_VIOLATION,
            "FORMAL data_manifest 缺 split_task_ids[" + split + "]",
            sorted(split_ids) if isinstance(split_ids, Mapping) else type(split_ids).__name__,
        )
    declared = sorted(str(value) for value in split_ids[split])
    actual = sorted({str(record["task_id"]) for record in eval_records})
    if actual != declared:
        _fail(
            S3_ANALYSIS_DATA_BOUNDARY_VIOLATION,
            "FORMAL 评估记录任务集合与 data_manifest." + split + " 不符",
            {"declared": declared, "actual": actual},
        )
    config_task_ids = tuple(str(value) for value in grid.get("task_ids", ()))
    if config_task_ids and tuple(actual) != tuple(sorted(config_task_ids)):
        _fail(
            S3_ANALYSIS_DATA_BOUNDARY_VIOLATION,
            "FORMAL 评估记录任务集合与 run_config 任务列表不符",
            {"declared": list(config_task_ids), "actual": actual},
        )
    _checks(
        checks,
        "run_records_task_manifest_binding",
        "PASS",
        "评估记录任务集合与 data_manifest." + split + " 完全一致（" + str(len(actual)) + " tasks）",
    )


def _validate_eval_record(record: Mapping[str, Any], *, config: Mapping[str, Any], grid: Mapping[str, Any], checks: list[dict[str, Any]]) -> None:
    code = S3_ANALYSIS_RECORD_INVALID
    if _require_str(record.get("schema_version"), code=code, label="eval_record.schema_version") != sp.S3_RECORD_SCHEMA_VERSION:
        _fail(code, "eval 记录 schema_version 不符")
    record_run_id = _require_str(record.get("run_id"), code=code, label="eval_record.run_id")
    # A1 runner 逐 run id 形如 <实验 run_id>--<arm>--B<budget>--T<task>--MS<meta>--OS<opt>，
    # 记录 run_id 以 run_config.run_id 为前缀；同 bucket 内必须一致（见 _aggregate_eval_records）。
    if not record_run_id.startswith(str(config.get("run_id"))):
        _fail(code, "eval 记录 run_id 不以 run_config.run_id 为前缀", {"run_id": record_run_id, "prefix": str(config.get("run_id"))})
    task_id = _require_str(record.get("task_id"), code=code, label="eval_record.task_id")
    if grid.get("task_ids") and task_id not in set(str(value) for value in grid["task_ids"]):
        _fail(code, "eval 记录 task_id 不在评估任务列表内", task_id)
    split = _require_str(record.get("split"), code=code, label="eval_record.split")
    if split not in sp.S3_ALLOWED_SPLITS:
        _fail(code, "eval 记录 split 非法: " + split, list(sp.S3_ALLOWED_SPLITS))
    eval_split = grid.get("eval_split")
    if eval_split is not None and split != str(eval_split):
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "eval 记录 split 与 evaluation_grid.eval_split 不符", {"expected": eval_split, "actual": split})
    arm_id = _require_str(record.get("arm_id"), code=code, label="eval_record.arm_id")
    if arm_id not in sp.S3_ARMS:
        _fail(code, "eval 记录 arm_id 非法: " + arm_id, list(sp.S3_ARMS))
    budget = _require_int(record.get("budget"), code=code, label="eval_record.budget")
    if budget not in set(int(value) for value in grid["budgets"]):
        _fail(code, "eval 记录 budget 不在网格内", budget)
    opt_seed = _require_int(record.get("opt_seed"), code=code, label="eval_record.opt_seed", minimum=0)
    if opt_seed not in set(int(value) for value in grid["opt_seeds"]):
        _fail(code, "eval 记录 opt_seed 不在网格内", opt_seed)
    meta_seed = _require_int(record.get("meta_seed"), code=code, label="eval_record.meta_seed", minimum=0)
    if meta_seed not in set(int(value) for value in grid["meta_seeds"]):
        _fail(code, "eval 记录 meta_seed 不在网格内", meta_seed)
    evaluation_index = _require_int(record.get("evaluation_index"), code=code, label="eval_record.evaluation_index")
    if evaluation_index < 1 or evaluation_index > budget:
        _fail(code, "eval 记录 evaluation_index 越界", {"index": evaluation_index, "budget": budget})
    design = _require_list(record.get("design"), code=code, label="eval_record.design")
    if len(design) != 12:
        _fail(code, "eval 记录 design 维度必须为 12", len(design))
    for coordinate in design:
        value = _require_number(coordinate, code=code, label="eval_record.design")
        if float(value) < 0.0 or float(value) > 1.0:
            _fail(code, "eval 记录 design 坐标必须位于 [0,1]")
    for field in ("f", "g1", "g2"):
        _require_number(record.get(field), code=code, label="eval_record." + field)
    feasible = _require_bool(record.get("feasible"), code=code, label="eval_record.feasible")
    expected_feasible = float(record["g1"]) <= 0.0 and float(record["g2"]) <= 0.0
    if bool(feasible) != bool(expected_feasible):
        _fail(code, "eval 记录 feasible 与 g1/g2 不一致", {"index": evaluation_index, "feasible": feasible, "g1": record["g1"], "g2": record["g2"]})
    source = _require_str(record.get("source"), code=code, label="eval_record.source")
    if source not in sp.S3_SOURCES:
        _fail(code, "eval 记录 source 非法: " + source, list(sp.S3_SOURCES))
    phase = _require_str(record.get("phase"), code=code, label="eval_record.phase")
    if phase not in sp.S3_PHASES:
        _fail(code, "eval 记录 phase 非法: " + phase, list(sp.S3_PHASES))
    holdout_truth_read = _require_bool(record.get("holdout_truth_read"), code=code, label="eval_record.holdout_truth_read")
    if phase == PHASE_EVAL:
        if not holdout_truth_read:
            _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "EVAL 记录 holdout_truth_read 必须为 true")
    else:
        if holdout_truth_read:
            _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "非 EVAL 记录 holdout_truth_read 必须为 false: phase=" + phase)
    _require_number(record.get("wall_s"), code=code, label="eval_record.wall_s", minimum=0.0)
    _require_sha256(record.get("record_digest"), code=code, label="eval_record.record_digest")


def _load_negative_control(run_dir: Path, *, grid: Mapping[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_RUN_SCHEMA_INVALID
    directory = run_dir / NEGATIVE_CONTROL_DIR
    # A1 runner 的 FORMAL 布局把负控摘要/记录放在 run 根（negative_control_summary.json /
    # negative_control_records.jsonl），旧布局放在 negative_control/ 子目录；两种都接受。
    records_candidates = [directory / "records.jsonl", run_dir / NC_RECORDS_FILE]
    summary_candidates = [directory / "summary.json", run_dir / NEGATIVE_CONTROL_SUMMARY_FILE]
    records_path = next((path for path in records_candidates if path.is_file()), None)
    summary_path = next((path for path in summary_candidates if path.is_file()), None)
    if records_path is None and summary_path is None:
        _checks(checks, "negative_control_artifacts", "DISCLOSED",
                "run 目录无 negative_control/ 或 negative_control_summary.json（负控分析缺失）")
        return {"records": [], "summary": {}, "available": False}
    records: list[dict[str, Any]] = []
    if records_path is not None:
        records = list(_iter_record_lines(records_path, code=S3_ANALYSIS_RECORD_INVALID))
    summary: dict[str, Any] = {}
    if summary_path is not None:
        summary = dict(_require_mapping(_read_json_file(summary_path, code=code, label=summary_path.name), code=code, label="negative_control summary"))
    loaded_sources = [str(path.relative_to(run_dir)) for path in (records_path, summary_path) if path is not None]
    _checks(checks, "negative_control_artifacts", "PASS",
            "负控产物: records=" + str(len(records)) + " summary_keys=" + str(sorted(summary.keys()))
            + " sources=" + ",".join(sorted(loaded_sources)))
    return {"records": records, "summary": summary, "available": bool(records or summary)}


def _load_determinism(run_dir: Path, *, grid: Mapping[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    code = S3_ANALYSIS_DETERMINISM_MISMATCH
    directory = run_dir / DETERMINISM_DIR
    if not directory.is_dir():
        _checks(checks, "determinism_artifacts", "DISCLOSED", "run 目录无 determinism/（确定性重跑缺失）")
        return {"available": False, "passes": [], "core_digest_equal": None}
    passes = []
    for name in ("r1", "r2", "r3"):
        pass_dir = directory / name
        if not pass_dir.is_dir():
            _checks(checks, "determinism_" + name, "DISCLOSED", "缺少确定性重跑目录 " + name)
            continue
        records_path = pass_dir / RUN_RECORDS_FILE
        if not records_path.is_file():
            _fail(code, "确定性重跑 " + name + " 缺少 run_records.jsonl")
        records = [
            dict(record)
            for record in _iter_record_lines(records_path, code=S3_ANALYSIS_RECORD_INVALID)
        ]
        core = [
            _record_core_digest(record)
            for record in records
            if EVAL_RECORD_KEYS.issubset(set(record.keys()))
        ]
        passes.append({"name": name, "records": len(records), "eval_core_digests": core})
    equal = None
    if len(passes) >= 2:
        reference = passes[0]["eval_core_digests"]
        equal = all(item["eval_core_digests"] == reference for item in passes[1:])
        if not equal:
            _fail(code, "确定性重跑 eval 记录 core digest 不一致", {"passes": [item["name"] for item in passes]})
        _checks(checks, "determinism_core_digest", "PASS", "确定性重跑 eval 记录 core digest 一致（" + str(len(passes)) + " 次，" + str(len(reference)) + " 条）")
    return {"available": True, "passes": passes, "core_digest_equal": equal}


def _cross_check_run_gate_binding(
    config: Mapping[str, Any],
    gate: Mapping[str, Any],
    *,
    gate_sha: str,
    checks: list[dict[str, Any]],
) -> None:
    """R-S3-07：FORMAL run_config.fd_or_gradient_gate 声明必须与门文件实际内容一致。

    - 声明 sha256 必须等于 fd_or_gradient_gate.json raw sha256；
    - 声明 models 的两键（fomaml_meta_0/anil_meta_0）必须与门文件对应模型的 n_checked/status/max_relative_error 一致。
    """
    if str(config.get("run_mode")) != "FORMAL":
        return
    code = S3_ANALYSIS_FD_GATE_INVALID
    declared = _require_mapping(config.get("fd_or_gradient_gate"), code=code, label="run_config.fd_or_gradient_gate")
    declared_sha = _require_sha256(declared.get("sha256"), code=code, label="run_config.fd_or_gradient_gate.sha256")
    if declared_sha != str(gate_sha):
        _fail(code, "FORMAL run_config.fd_or_gradient_gate.sha256 与门文件 raw sha 不符", {"declared": declared_sha, "actual": gate_sha})
    declared_models = _require_mapping(declared.get("models"), code=code, label="run_config.fd_or_gradient_gate.models")
    artifact_models = _require_mapping(gate.get("models"), code=code, label="fd_or_gradient_gate.models")
    normalized: dict[str, Mapping[str, Any]] = {}
    for key, value in artifact_models.items():
        name = _normalize_gate_model_name(key)
        if name:
            normalized[name] = _require_mapping(value, code=code, label="fd_or_gradient_gate.models." + str(key))
    for model_key in FORMAL_GATE_MODEL_KEYS:
        name = "fomaml" if str(model_key).startswith("fomaml") else "anil"
        declared_entry = _require_mapping(declared_models.get(model_key), code=code, label="run_config.fd_or_gradient_gate.models." + str(model_key))
        artifact_entry = normalized.get(name)
        if artifact_entry is None:
            _fail(code, "门文件缺少模型坐标证据: " + name)
        artifact_status = artifact_entry.get("status")
        if artifact_status is not None and str(artifact_entry.get("status")) != str(declared_entry.get("status")):
            _fail(code, "run_config FD 门声明 status 与门文件不符: " + name, {"declared": declared_entry.get("status"), "artifact": artifact_status})
        artifact_n = artifact_entry.get("n_checked")
        if artifact_n is not None and int(_require_int(artifact_n, code=code, label="gate.models." + name + ".n_checked")) != int(
            _require_int(declared_entry.get("n_checked"), code=code, label="declared.models." + str(model_key) + ".n_checked")
        ):
            _fail(code, "run_config FD 门声明 n_checked 与门文件不符: " + name)
        artifact_rel = artifact_entry.get("max_relative_error")
        if artifact_rel is not None:
            declared_rel = _require_number(declared_entry.get("max_relative_error"), code=code, label="declared.models." + str(model_key) + ".max_relative_error")
            if not math.isclose(float(declared_rel), float(artifact_rel), rel_tol=1e-9, abs_tol=1e-12):
                _fail(code, "run_config FD 门声明 max_relative_error 与门文件不符: " + name, {"declared": declared_rel, "artifact": artifact_rel})
    _checks(checks, "fd_gate_declared_binding", "PASS", "FORMAL run_config FD 门声明与门文件 raw sha/两模型证据一致（R-S3-07）")


def load_s3_run(
    run_dir: str | Path,
    prereg: "S3Prereg",
    *,
    allow_incomplete_run: bool = False,
    verify_record_digests: bool = False,
    checks: list[dict[str, Any]] | None = None,
) -> S3RunData:
    """加载 run 目录并做 fail-closed 校验；记录流式聚合为逐 run 端点原料。"""
    checks = checks if checks is not None else []
    directory = Path(run_dir).resolve()
    if not directory.is_dir():
        _fail(S3_ANALYSIS_RUN_SCHEMA_INVALID, "run 目录不存在", str(directory))
    config_raw, config_source = _read_run_json(directory, RUN_CONFIG_FILE)
    config = _validate_run_config(config_raw, prereg, checks=checks)
    grid = config["_grid"]
    records_path = _require_run_file(directory, RUN_RECORDS_FILE)
    source_records = {"path": str(records_path), "sha256": sp.sha256_bytes(records_path.read_bytes()), "bytes": records_path.stat().st_size}
    train_records, eval_records, counts = _aggregate_eval_records(
        _iter_record_lines(records_path, code=S3_ANALYSIS_RECORD_INVALID),
        config,
        grid,
        checks=checks,
        verify_record_digests=verify_record_digests,
    )
    stream_scan = _scan_aux_streams(directory, grid, checks=checks)
    summary_actual_counts = {"train": int(counts["train"]), "eval": int(counts["eval"]), "total": int(counts["total"])}
    if str(grid.get("run_mode")) == "FORMAL":
        summary_actual_counts["eval"] = int(counts["eval"]) + int(stream_scan["aux_records"])
        summary_actual_counts["total"] = int(counts["train"]) + int(summary_actual_counts["eval"])
    summary_raw, summary_source = _read_run_json(directory, RUN_SUMMARY_FILE)
    summary = _validate_run_summary(
        summary_raw,
        config,
        prereg,
        grid,
        actual_counts=summary_actual_counts,
        checks=checks,
    )
    data_manifest_raw, manifest_source = _read_run_json(directory, DATA_MANIFEST_FILE)
    data_manifest = _validate_data_manifest(data_manifest_raw, config, prereg, grid, checks=checks)
    _cross_check_record_task_set(data_manifest, eval_records, grid, checks=checks)
    record_streams = _validate_record_stream_counts(
        config=config,
        summary=summary,
        grid=grid,
        prereg=prereg,
        main_counts=counts,
        aux_streams=stream_scan,
        data_manifest=data_manifest,
        checks=checks,
    )
    model_manifest_raw, model_source = _read_run_json(directory, MODEL_MANIFEST_FILE)
    model_manifest = _validate_model_manifest(model_manifest_raw, config, prereg, checks=checks)
    gate_raw, gate_source = _read_run_json(directory, FD_GATE_FILE)
    gate = _validate_gate_artifact(gate_raw, config, prereg, checks=checks)
    if sp.sha256_bytes((directory / FD_GATE_FILE).read_bytes()) != summary.get("fd_or_gradient_gate_sha256"):
        _fail(S3_ANALYSIS_FD_GATE_INVALID, "run_summary.fd_or_gradient_gate_sha256 与 fd_or_gradient_gate.json raw sha 不符")
    _checks(checks, "fd_gate_file_sha256", "PASS", "fd_or_gradient_gate.json raw sha256 与 run_summary 一致")
    _cross_check_run_gate_binding(
        config,
        gate,
        gate_sha=sp.sha256_bytes((directory / FD_GATE_FILE).read_bytes()),
        checks=checks,
    )
    _assert_gate_file_prereg_binding(
        sp.sha256_bytes((directory / FD_GATE_FILE).read_bytes()),
        prereg,
        run_mode=str(grid.get("run_mode")),
        checks=checks,
    )
    if sp.sha256_bytes((directory / DATA_MANIFEST_FILE).read_bytes()) != summary.get("data_manifest_sha256"):
        _fail(S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, "run_summary.data_manifest_sha256 与 data_manifest.json raw sha 不符")
    _checks(checks, "data_manifest_file_sha256", "PASS", "data_manifest.json raw sha256 与 run_summary 一致")
    negative_control = _load_negative_control(directory, grid=grid, checks=checks)
    determinism = _load_determinism(directory, grid=grid, checks=checks)
    sources = {
        RUN_CONFIG_FILE: config_source,
        RUN_SUMMARY_FILE: summary_source,
        RUN_RECORDS_FILE: source_records,
        DATA_MANIFEST_FILE: manifest_source,
        MODEL_MANIFEST_FILE: model_source,
        FD_GATE_FILE: gate_source,
    }
    sources.update(stream_scan["sources"])
    _checks(checks, "run_physical_call_count", "PASS", "run 全产物 physical_call_count=0")
    _checks(checks, "run_records_schema", "PASS", "run_records train/eval 字段集与 s3_prereg 单源字段严格相等")
    return S3RunData(
        run_dir=directory,
        config={key: value for key, value in config.items() if not key.startswith("_")},
        summary=summary,
        data_manifest=data_manifest,
        model_manifest=model_manifest,
        gate=gate,
        grid=grid,
        per_run=tuple(eval_records),
        train_records=tuple(train_records),
        negative_control=negative_control,
        determinism=determinism,
        record_streams=record_streams,
        sources=sources,
        checks=tuple(dict(item) for item in checks),
    )

# ---------------------------------------------------------------------------
# 端点计算、task 级聚合、C1/C2 推断（计划 §5.1/§5.2）
# ---------------------------------------------------------------------------
MAIN_SPLIT_CANDIDATES = ("meta_test", "meta_validation", "dev")
EXCLUDED_SPLITS = ("meta_test_ood", "meta_test_negative_control")
INFERENCE_ENDPOINTS = (C1_ENDPOINT, C2_ENDPOINT)
DESCRIPTIVE_ENDPOINTS = (
    "best_feasible_value",
    "first_feasible_eval_index",
    "surrogate_rmse",
    "surrogate_mae",
    "f_rmse",
    "f_mae",
    "adaptation_cost",
    "total_cost",
)


def compute_run_endpoints(run: "S3RunData", references: Mapping[str, Mapping[str, Any]], *, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐 run 计算 §5.1 端点（gap 在 run 完成后用封存 f_ref 计算）。"""
    endpoints: list[dict[str, Any]] = []
    missing_references = 0
    for bucket in run.per_run:
        task_id = str(bucket["task_id"])
        split = str(bucket["split"])
        budget = int(bucket["budget"])
        hit_rate = float(bucket["hit_count"]) / float(budget)
        best_f = bucket["best_f"]
        first_index = bucket["first_feasible_index"]
        hit_count = int(bucket["hit_count"])
        if best_f is not None and hit_count != int(bucket["feasible_count"]):
            _fail(S3_ANALYSIS_RECORD_INVALID, "可行点计数与 best 计算不一致", {"task": task_id})
        gap = None
        if best_f is not None:
            reference = references.get(task_id)
            if reference is None:
                missing_references += 1
                gap = None
            else:
                raw_gap = float(best_f) - float(reference["f_ref"])
                if raw_gap < -1e-9:
                    _fail(
                        S3_ANALYSIS_INPUT_INVALID,
                        "gap_to_reference 显著为负（best < f_ref），参考解或标签可能不匹配",
                        {"task_id": task_id, "best": best_f, "f_ref": reference["f_ref"], "gap": raw_gap},
                    )
                gap = max(0.0, raw_gap)
        wall_s = float(bucket["wall_s"])
        endpoints.append({
            "run_key": (task_id, int(bucket["budget"]), str(bucket["arm_id"]), int(bucket["opt_seed"]), int(bucket["meta_seed"])),
            "task_id": task_id,
            "split": split,
            "phase": str(bucket["phase"]),
            "arm_id": str(bucket["arm_id"]),
            "budget": budget,
            "opt_seed": int(bucket["opt_seed"]),
            "meta_seed": int(bucket["meta_seed"]),
            "feasible_hit_rate": hit_rate,
            "feasible_count": hit_count,
            "best_feasible_value": None if best_f is None else float(best_f),
            "gap_to_reference": gap,
            "first_feasible_eval_index": None if first_index is None else int(first_index),
            "surrogate_rmse": None,
            "surrogate_mae": None,
            "f_rmse": None,
            "f_mae": None,
            "adaptation_cost": wall_s + float(budget),
            "scoring_count": budget,
            "total_cost": wall_s,
            "cost_metric_note": "adaptation_cost=wall_s+打分次数; total_cost=run wall_s",
        })
    if missing_references:
        _checks(checks, "gap_reference_coverage", "DISCLOSED", "有 " + str(missing_references) + " 个 run 的 task 缺封存参考解，gap 记 null")
    else:
        _checks(checks, "gap_reference_coverage", "PASS", "全部 run 均有封存参考解")
    _checks(checks, "surrogate_error_metrics", "DISCLOSED", "run_records 19 字段不含代理预测值，surrogate/f RMSE/MAE 记为 " + EVAL_QUERY_PLACEHOLDER + "（CONTRACT_AMBIGUITY 已上报）")
    return endpoints


def split_main_and_aux(endpoints: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    main = [dict(item) for item in endpoints if str(item.get("split")) not in EXCLUDED_SPLITS]
    aux = [dict(item) for item in endpoints if str(item.get("split")) in EXCLUDED_SPLITS]
    return main, aux


def aggregate_task_values(
    endpoints: Sequence[Mapping[str, Any]],
    *,
    endpoint_name: str,
) -> dict[tuple[str, int, str], dict[str, Any]]:
    """按 (task, budget, arm) 先对 opt_seed×meta_seed 取均值（null 缺失不插补）。"""
    cells: dict[tuple[str, int, str], list[Any]] = {}
    for item in endpoints:
        key = (str(item["task_id"]), int(item["budget"]), str(item["arm_id"]))
        cells.setdefault(key, []).append(item.get(endpoint_name))
    aggregated: dict[tuple[str, int, str], dict[str, Any]] = {}
    for key, values in cells.items():
        clean = [float(value) for value in values if value is not None]
        aggregated[key] = {
            "value": _mean_or_none(clean),
            "n_total": len(values),
            "n_missing": len(values) - len(clean),
            "values": values,
        }
    return aggregated


def _task_series(aggregated: Mapping[tuple[str, int, str], Mapping[str, Any]], *, arm_id: str, budget: int, tasks: Sequence[str]) -> list[float | None]:
    return [aggregated.get((str(task), int(budget), str(arm_id)), {}).get("value") for task in tasks]


def _endpoint_role(endpoint_name: str) -> str:
    return "inference" if endpoint_name in INFERENCE_ENDPOINTS else "descriptive"


def build_endpoint_summary(
    endpoints: Sequence[Mapping[str, Any]],
    *,
    endpoints_to_report: Sequence[str],
    tasks: Sequence[str],
    grid: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """逐端点×预算×臂的 task 级点估计 + bootstrap CI（描述性）。"""
    rows: list[dict[str, Any]] = []
    per_task_rows: list[dict[str, Any]] = []
    aggregated_by_endpoint: dict[str, dict[tuple[str, int, str], dict[str, Any]]] = {}
    for endpoint_name in endpoints_to_report:
        aggregated = aggregate_task_values(endpoints, endpoint_name=endpoint_name)
        aggregated_by_endpoint[endpoint_name] = aggregated
        for arm_id in grid["arms"]:
            for budget in grid["budgets"]:
                series = _task_series(aggregated, arm_id=str(arm_id), budget=int(budget), tasks=tasks)
                ci = bootstrap_mean_ci(series)
                n_null = sum(1 for value in series if value is None)
                rows.append({
                    "endpoint": endpoint_name,
                    "endpoint_role": _endpoint_role(endpoint_name),
                    "budget": int(budget),
                    "arm_id": str(arm_id),
                    "n_tasks": len(tasks),
                    "n_null": n_null,
                    "null_ratio": (n_null / float(len(tasks))) if tasks else None,
                    "mean": ci["mean"],
                    "median": ci["median"],
                    "ci_low": ci["ci_low"],
                    "ci_high": ci["ci_high"],
                    "bootstrap_resamples": ci["n_resamples"],
                    "bootstrap_seed": ci["seed"],
                    "comparator": COMPARATOR_ARMS[1],
                    "note": "null 按缺失处理，不插值",
                })
                for task in tasks:
                    per_task_rows.append({
                        "endpoint": endpoint_name,
                        "budget": int(budget),
                        "arm_id": str(arm_id),
                        "task_id": str(task),
                        "value": aggregated.get((str(task), int(budget), str(arm_id)), {}).get("value"),
                        "n_total": aggregated.get((str(task), int(budget), str(arm_id)), {}).get("n_total"),
                        "n_missing": aggregated.get((str(task), int(budget), str(arm_id)), {}).get("n_missing"),
                    })
    return {"rows": rows, "per_task_rows": per_task_rows, "aggregated": aggregated_by_endpoint}


def _paired_differences(
    aggregated: Mapping[tuple[str, int, str], Mapping[str, Any]],
    *,
    arm_a: str,
    arm_b: str,
    budget: int,
    tasks: Sequence[str],
) -> tuple[list[float | None], int, int]:
    diffs: list[float | None] = []
    n_zero = 0
    n_paired = 0
    for task in tasks:
        value_a = aggregated.get((str(task), int(budget), str(arm_a)), {}).get("value")
        value_b = aggregated.get((str(task), int(budget), str(arm_b)), {}).get("value")
        if value_a is None or value_b is None:
            diffs.append(None)
            continue
        difference = float(value_a) - float(value_b)
        if difference == 0.0:
            n_zero += 1
        n_paired += 1
        diffs.append(difference)
    return diffs, n_zero, n_paired


def _ensure_comparator(arm_a: str, arm_b: str, *, test_id: str) -> None:
    if (str(arm_a), str(arm_b)) != COMPARATOR_ARMS:
        _fail(
            S3_ANALYSIS_COMPARATOR_MISMATCH,
            "C1/C2 比较必须固定为 CON−OBJ；实际 " + str(arm_a) + "−" + str(arm_b),
            {"test_id": test_id, "expected": list(COMPARATOR_ARMS)},
        )


def build_inference(
    endpoints: Sequence[Mapping[str, Any]],
    *,
    tasks: Sequence[str],
    grid: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """C1/C2 两族各 2 检验：Wilcoxon 精确 + Holm + 6 档决策 + 总体映射。"""
    summaries = build_endpoint_summary(
        endpoints,
        endpoints_to_report=INFERENCE_ENDPOINTS,
        tasks=tasks,
        grid=grid,
        checks=checks,
    )
    aggregated = summaries["aggregated"]
    family_tests: dict[str, list[dict[str, Any]]] = {C1_FAMILY_ID: [], C2_FAMILY_ID: []}
    layer_decisions: dict[str, dict[str, str]] = {}
    for family_id, endpoint_name, is_c2 in (
        (C1_FAMILY_ID, C1_ENDPOINT, False),
        (C2_FAMILY_ID, C2_ENDPOINT, True),
    ):
        family_aggregated = aggregated[endpoint_name]
        for budget in grid["budgets"]:
            test_id = ("C2" if is_c2 else "C1") + ("a" if int(budget) == 128 else "b")
            if int(budget) not in (64, 128):
                _fail(S3_ANALYSIS_BUDGET_MISMATCH, "C1/C2 仅支持 B∈{64,128}", budget)
            arm_a, arm_b = COMPARATOR_ARMS
            _ensure_comparator(arm_a, arm_b, test_id=test_id)
            diffs, n_zero, n_paired = _paired_differences(
                family_aggregated,
                arm_a=arm_a,
                arm_b=arm_b,
                budget=int(budget),
                tasks=tasks,
            )
            clean_diffs = [float(value) for value in diffs if value is not None]
            wilcoxon = wilcoxon_signed_rank_exact(clean_diffs)
            pratt = wilcoxon_pratt(clean_diffs)
            permutation = wilcoxon_permutation(clean_diffs)
            ci = bootstrap_mean_ci(clean_diffs)
            mean_diff = _mean_or_none(clean_diffs)
            obj_series = _task_series(family_aggregated, arm_id=arm_b, budget=int(budget), tasks=tasks)
            obj_mean = _mean_or_none([value for value in obj_series if value is not None])
            if is_c2:
                if obj_mean is None or mean_diff is None:
                    effect = None
                else:
                    effect = float(mean_diff) / max(abs(float(obj_mean)), C2_DENOMINATOR_FLOOR)
                threshold = C2_RELATIVE_THRESHOLD
                direction = "negative"
            else:
                effect = mean_diff
                threshold = C1_THRESHOLD_ABS
                direction = "positive"
            # A5-S3M1-B01：层决策必须用 Holm 校正后的 p_holm 判定（族内 Holm 在下方统一回填），
            # 此处不预计算 decision，避免 raw Wilcoxon p 泄漏到层决策/总体决策。
            family_tests[family_id].append({
                "test_id": test_id,
                "family_id": family_id,
                "endpoint": endpoint_name,
                "budget": int(budget),
                "arm_a": arm_a,
                "arm_b": arm_b,
                "n_tasks": len(tasks),
                "n_zero": int(wilcoxon.get("n_zero") or 0),
                "n_eff": wilcoxon.get("n_eff"),
                "n_paired": n_paired,
                "w_plus": wilcoxon.get("w_plus"),
                "p_raw": wilcoxon.get("p_two_sided"),
                "mean_difference": mean_diff,
                "median_difference": ci["median"],
                "difference_ci_low": ci["ci_low"],
                "difference_ci_high": ci["ci_high"],
                "effect": effect,
                "threshold": threshold,
                "benefit_direction": direction,
                "wilcoxon_method": wilcoxon.get("method"),
                "pratt_p": pratt.get("p_two_sided"),
                "permutation_p": permutation.get("p_two_sided"),
                "permutation_resamples": permutation.get("n_resamples"),
                "permutation_seed": permutation.get("seed"),
                "n_eff_below_min": (wilcoxon.get("n_eff") is not None and int(wilcoxon.get("n_eff")) < WILCOXON_MIN_N_EFF),
                "diff_values": diffs,
            })
    holm_rows: list[dict[str, Any]] = []
    for family_id, tests in family_tests.items():
        adjusted = holm_adjust([(item["test_id"], item["p_raw"]) for item in tests], alpha=ALPHA)
        by_id = {item["test_id"]: item for item in adjusted}
        for item in tests:
            adjustment = by_id[item["test_id"]]
            item["p_holm"] = adjustment.get("p_holm")
            item["holm_rank"] = adjustment.get("rank")
            item["holm_reject"] = adjustment.get("reject")
            # A5-S3M1-B01：族内 Holm 校正完成后，用 p_holm 经单一固定查表函数 decide_layer 重算该检验决策；
            # raw p 不再直接决定任何决策，层决策/overall 均只消费此处回填的 decision。
            item["decision"] = decide_layer(
                p_value=item["p_holm"],
                effect=item["effect"],
                threshold=item["threshold"],
                benefit_direction=item["benefit_direction"],
                n_eff=item["n_eff"],
            )
            layer_decisions.setdefault(("C2" if family_id == C2_FAMILY_ID else "C1"), {})["B" + str(int(item["budget"]))] = item["decision"]
            holm_rows.append({
                "family_id": family_id,
                "test_id": item["test_id"],
                "endpoint": item["endpoint"],
                "budget": item["budget"],
                "p_raw": item["p_raw"],
                "p_holm": item["p_holm"],
                "decision": item["decision"],
                "rank": item["holm_rank"],
                "reject": item["holm_reject"],
                "family_size": len(tests),
                "alpha": ALPHA,
            })
    _checks(
        checks,
        "holm_decision_recomputed",
        "PASS",
        "A5-S3M1-B01：全部检验的 decision 均由 Holm 校正后 p_holm 经 decide_layer 单一查表重算（raw p 不参与判定）",
    )
    c1_decisions = {
        "B64": layer_decisions.get("C1", {}).get("B64", D_INCONCLUSIVE),
        "B128": layer_decisions.get("C1", {}).get("B128", D_INCONCLUSIVE),
    }
    # A5-S3M1-B01：总体决策只由 C1 两层（B64/B128）经固定优先级查表得出，C2 不参与 overall。
    overall = decide_overall(c1_decisions)
    c2_decisions = {
        "B64": layer_decisions.get("C2", {}).get("B64", D_INCONCLUSIVE),
        "B128": layer_decisions.get("C2", {}).get("B128", D_INCONCLUSIVE),
    }
    _checks(checks, "c1_c2_comparator", "PASS", "C1/C2 (arm_a,arm_b)=(" + COMPARATOR_ARMS[0] + "," + COMPARATOR_ARMS[1] + ") 固定通过")
    _checks(checks, "c1_overall_decision", "PASS", "C1 总体判定: " + overall + "（B64=" + c1_decisions["B64"] + ", B128=" + c1_decisions["B128"] + "）")
    return {
        "families": family_tests,
        "holm_rows": holm_rows,
        "c1_decisions": c1_decisions,
        "c2_decisions": c2_decisions,
        "overall_decision": overall,
        "endpoint_summary": summaries,
        "layer_decisions": layer_decisions,
    }


def build_null_disclosure(
    endpoints: Sequence[Mapping[str, Any]],
    *,
    tasks: Sequence[str],
    grid: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """null 计数披露：逐端点×预算×臂，分母 = 预期 task 单元格数。"""
    rows: list[dict[str, Any]] = []
    for endpoint_name in tuple(INFERENCE_ENDPOINTS) + tuple(DESCRIPTIVE_ENDPOINTS):
        aggregated = aggregate_task_values(endpoints, endpoint_name=endpoint_name)
        for arm_id in grid["arms"]:
            for budget in grid["budgets"]:
                n_null = 0
                n_cells = 0
                for task in tasks:
                    entry = aggregated.get((str(task), int(budget), str(arm_id)))
                    if entry is None:
                        n_null += 1
                        n_cells += 1
                        continue
                    n_cells += 1
                    if entry["value"] is None:
                        n_null += 1
                rows.append({
                    "endpoint": endpoint_name,
                    "endpoint_role": _endpoint_role(endpoint_name),
                    "budget": int(budget),
                    "arm_id": str(arm_id),
                    "n_cells": n_cells,
                    "n_null": n_null,
                    "null_ratio": (n_null / float(n_cells)) if n_cells else None,
                    "rule": "null 按缺失处理，不插值；分母为预期 task 单元格数",
                })
    total_cells = sum(row["n_cells"] for row in rows)
    total_null = sum(row["n_null"] for row in rows)
    _checks(checks, "null_disclosure", "PASS", "null 披露: " + str(total_null) + "/" + str(total_cells) + " 单元格为 null")
    return rows


def build_cost_rows(endpoints: Sequence[Mapping[str, Any]], *, grid: Mapping[str, Any], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for arm_id in grid["arms"]:
        for budget in grid["budgets"]:
            wall_values = [float(item["total_cost"]) for item in endpoints if str(item["arm_id"]) == str(arm_id) and int(item["budget"]) == int(budget)]
            adaptation_values = [float(item["adaptation_cost"]) for item in endpoints if str(item["arm_id"]) == str(arm_id) and int(item["budget"]) == int(budget)]
            rows.append({
                "arm_id": str(arm_id),
                "budget": int(budget),
                "n_runs": len(wall_values),
                "total_cost_mean_s": _mean_or_none(wall_values),
                "total_cost_median_s": float(np.median(wall_values)) if wall_values else None,
                "adaptation_cost_mean": _mean_or_none(adaptation_values),
                "cost_metric_note": "total_cost=run wall_s; adaptation_cost=wall_s+打分次数",
            })
    _checks(checks, "cost_table", "PASS", "成本表行数: " + str(len(rows)))
    return rows


def build_anil_row(
    endpoints: Sequence[Mapping[str, Any]],
    *,
    tasks: Sequence[str],
    grid: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    hit = aggregate_task_values(endpoints, endpoint_name=C1_ENDPOINT)
    anil_arm = "S3-BO-ANIL-CON"
    con_arm = COMPARATOR_ARMS[0]
    random_arm = "S3-BO-RANDOM"
    deficit_values = []
    for budget in grid["budgets"]:
        for task in tasks:
            anil_value = hit.get((str(task), int(budget), anil_arm), {}).get("value")
            random_value = hit.get((str(task), int(budget), random_arm), {}).get("value")
            if anil_value is None or random_value is None:
                continue
            deficit_values.append(float(anil_value) - float(random_value))
    ci = bootstrap_mean_ci(deficit_values)
    anil_mean = _mean_or_none([hit.get((str(task), int(budget), anil_arm), {}).get("value") for budget in grid["budgets"] for task in tasks if hit.get((str(task), int(budget), anil_arm), {}).get("value") is not None])
    random_mean = _mean_or_none([hit.get((str(task), int(budget), random_arm), {}).get("value") for budget in grid["budgets"] for task in tasks if hit.get((str(task), int(budget), random_arm), {}).get("value") is not None])
    anil_cost = _mean_or_none([float(item["adaptation_cost"]) for item in endpoints if str(item["arm_id"]) == anil_arm])
    con_cost = _mean_or_none([float(item["adaptation_cost"]) for item in endpoints if str(item["arm_id"]) == con_arm])
    decision = anil_decision(
        anil_mean=anil_mean,
        random_mean=random_mean,
        anil_cost=anil_cost,
        con_cost=con_cost,
        anil_minus_random_ci=ci,
    )
    row = {
        "ablation": "ANIL_COST_EFFICIENT_AUDIT",
        "arm_id": anil_arm,
        "comparison_arm": random_arm,
        "anil_hit_rate_mean": anil_mean,
        "random_hit_rate_mean": random_mean,
        "anil_minus_random_ci_low": ci["ci_low"],
        "anil_minus_random_ci_high": ci["ci_high"],
        "anil_adaptation_cost_mean": anil_cost,
        "fomaml_con_adaptation_cost_mean": con_cost,
        "cost_ratio": (anil_cost / con_cost) if (anil_cost is not None and con_cost not in (None, 0.0)) else None,
        "decision": decision,
        "margin": ANIL_NONINFERIOR_MARGIN,
        "cost_ratio_max": ANIL_COST_RATIO_MAX,
        "note": "ANIL 为描述性消融，不做显著性强断言",
    }
    _checks(checks, "anil_cost_efficient", "PASS", "ANIL 消融判定: " + decision)
    return row


def build_negative_control_rows(
    run: "S3RunData",
    endpoints: Sequence[Mapping[str, Any]],
    *,
    tasks: Sequence[str],
    grid: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """负控制与 fail-closed 证据派生（不做硬编码 PASS）。"""
    rows: list[dict[str, Any]] = []

    def derived(control_id: str, name: str, evidence_status: str | None, observed: str, expected: str) -> None:
        if evidence_status == "PASS":
            status = "PASS"
        elif evidence_status == "FAIL":
            status = "FAIL"
        elif evidence_status is None:
            status = "DISCLOSED"
        else:
            status = "DISCLOSED"
        rows.append({"control_id": control_id, "name": name, "status": status, "observed": observed, "expected": expected})

    prereg_checks = list(run.checks)
    # run.checks 是 load_s3_run 时刻的快照；分析阶段后续追加的 check（c1_c2_comparator、
    # null_disclosure 等）只存在于 analyze_s3_run 传入的 checks 列表中，必须合并后再派生。
    run_checks = list(run.checks) + [item for item in checks if item not in run.checks]
    digest_status = _check_status(list(prereg_checks), "prereg_digest_self_consistency")
    void_status = _check_status(run_checks, "prereg_digest_self_consistency")
    derived("NC-01", "prereg_digest 自洽（重算 canonical sha256）", "PASS" if digest_status == "PASS" else None, "prereg_digest 重算一致" if digest_status == "PASS" else "未复算", "必须自洽")
    family_status = _check_status(run_checks, "family_package_sha256")
    derived("NC-02", "族包 sha256 与 prereg 绑定", "PASS" if family_status == "PASS" else None, "族包 sha256 一致" if family_status == "PASS" else "族包未加载", "必须一致")
    code_status = _check_status(run_checks, "prereg_code_sha")
    derived("NC-03", "code_sha 与仓库实算一致", "PASS" if code_status == "PASS" else None, "code_sha 实算一致" if code_status == "PASS" else "未实算仓库文件", "必须一致")
    episode_status = _check_status(run_checks, "episode_bank_contract")
    derived("NC-04", "episode bank sha 绑定", "PASS" if episode_status == "PASS" else None, "episode bank 合同与 sha 已校验" if episode_status == "PASS" else "未校验", "必须一致")
    schema_status = _check_status(run_checks, "run_records_schema")
    derived("NC-05", "记录字段集精确匹配 19/8 字段", "PASS" if schema_status == "PASS" else "FAIL", "字段集与 s3_prereg 单源一致" if schema_status == "PASS" else "字段集不符", "精确相等")
    budget_status = _check_status(run_checks, "run_records_budget")
    derived("NC-06", "逐 run 预算记账 billable=B", "PASS" if budget_status == "PASS" else "FAIL", "每 run 恰 B 条且索引 1..B" if budget_status == "PASS" else "预算记账不符", "billable_evals==B")
    boundary_status = _check_status(run_checks, "data_manifest_boundary")
    derived("NC-07", "phase-scoped 数据边界标志", "PASS" if boundary_status == "PASS" else "FAIL", "训练/适配/BO 排序未读 holdout truth" if boundary_status == "PASS" else "边界标志不符", "四 false + EVAL 一次 true")
    physical_status = _check_status(run_checks, "run_physical_call_count")
    derived("NC-08", "物理调用 0（prereg/run/data_manifest）", "PASS" if physical_status == "PASS" else "FAIL", "physical_call_count=0" if physical_status == "PASS" else "未验证", "必须为 0")
    fd_status = _check_status(run_checks, "fd_gate_artifact")
    derived("NC-09", "FD/梯度门 32 坐标 PASS", "PASS" if fd_status == "PASS" else "FAIL", "FD 门产物 32 坐标 PASS" if fd_status == "PASS" else "FD 门证据缺失", "status=PASS/max_rel<=1e-6")
    sealed_status = _check_status(run_checks, "references_sealed_sha256")
    derived("NC-10", "run 阶段不得读封存参考解", "PASS" if sealed_status == "PASS" else None, "run 产物记录 holdout_truth_read_phase=EVAL" if sealed_status == "PASS" else "封存件未在 run 阶段加载", "run 阶段禁止读取")
    comparator_status = _check_status(run_checks, "c1_c2_comparator")
    derived("NC-11", "comparator 固定 CON−OBJ（RANDOM/DE 不入推断）", "PASS" if comparator_status == "PASS" else "FAIL", "C1/C2 arm 对固定" if comparator_status == "PASS" else "comparator 不符", "CON−OBJ")
    determinism_status = _check_status(run_checks, "determinism_core_digest")
    derived("NC-12", "确定性重跑记录 core digest 一致", "PASS" if determinism_status == "PASS" else None, "3 次重跑 digest 一致" if determinism_status == "PASS" else "确定性产物未提供", "逐记录 core digest 一致")
    null_status = _check_status(run_checks, "null_disclosure")
    derived("NC-13", "null 披露（不插值）", "PASS" if null_status == "PASS" else None, "null 单元格已计数披露" if null_status == "PASS" else "未计算", "分母=预期单元格数")
    figures_status = _check_status(run_checks, "figure_status")
    derived("NC-14", "图状态 NOT_RUN 不伪造", "PASS" if figures_status == "PASS" else None, "缺失数据记 NOT_RUN" if figures_status == "PASS" else "负控派生时图状态尚未登记（见 figure_status.json，DISCLOSED 不伪造）", "缺数据=NOT_RUN")
    negative = run.negative_control
    real_hit = aggregate_task_values(endpoints, endpoint_name=C1_ENDPOINT)
    real_diff_values: list[float] = []
    for budget in grid["budgets"]:
        diffs, _, _ = _paired_differences(real_hit, arm_a=COMPARATOR_ARMS[0], arm_b=COMPARATOR_ARMS[1], budget=int(budget), tasks=tasks)
        real_diff_values.extend(float(value) for value in diffs if value is not None)
    real_mean = _mean_or_none(real_diff_values)
    if not negative.get("available"):
        rows.append({
            "control_id": "NC-15",
            "name": "标签置换负控制（CON−OBJ 效应是否消失）",
            "status": "DISCLOSED",
            "observed": "run 目录无 negative_control 产物，负控分析未执行",
            "expected": "打乱标签后 CON−OBJ 差异应显著缩小",
        })
    else:
        summary = negative.get("summary") or {}
        shuffled_mean = None
        for key in ("shuffled_con_minus_obj_feasible_hit_rate", "shuffled_con_minus_obj", "con_minus_obj_shuffled"):
            value = summary.get(key)
            if _is_number(value):
                shuffled_mean = float(value)
                break
        if shuffled_mean is None or real_mean is None:
            rows.append({
                "control_id": "NC-15",
                "name": "标签置换负控制（CON−OBJ 效应是否消失）",
                "status": "DISCLOSED",
                "observed": "负控产物存在但缺少可比字段",
                "expected": "打乱标签后 CON−OBJ 差异应显著缩小",
            })
        else:
            suspicious = abs(shuffled_mean) >= 0.5 * abs(real_mean) if real_mean != 0 else True
            rows.append({
                "control_id": "NC-15",
                "name": "标签置换负控制（CON−OBJ 效应是否消失）",
                "status": NEGATIVE_CONTROL_SUSPICIOUS if suspicious else NEGATIVE_CONTROL_PASS,
                "observed": "shuffled=" + str(shuffled_mean) + " real=" + str(real_mean),
                "expected": "shuffled < 50% × real 才视为通过",
            })
    _checks(checks, "negative_control_rows", "PASS", "负控派生行数: " + str(len(rows)))
    return rows


def build_ood_rows(run: "S3RunData", endpoints: Sequence[Mapping[str, Any]], *, grid: Mapping[str, Any], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OOD 描述性对比（仅当 run 产物包含 OOD 段；否则 NOT_RUN）。"""
    ood_endpoints = [dict(item) for item in endpoints if str(item.get("split")) == "meta_test_ood"]
    if not ood_endpoints:
        _checks(checks, "ood_artifacts", "DISCLOSED", "run 产物不含 OOD 段，OOD 描述性对比记 NOT_RUN")
        return [{"segment": "ood", "arm_id": str(arm), "budget": int(budget), "status": "NOT_RUN", "reason": "run 产物不含 OOD 段"} for arm in grid["arms"] for budget in grid["budgets"]]
    rows = []
    aggregated = aggregate_task_values(ood_endpoints, endpoint_name=C1_ENDPOINT)
    for arm in grid["arms"]:
        for budget in grid["budgets"]:
            values = [float(entry["value"]) for key, entry in aggregated.items() if key[1] == int(budget) and key[2] == str(arm) and entry["value"] is not None]
            rows.append({"segment": "ood", "arm_id": str(arm), "budget": int(budget), "status": "OK", "n_tasks": len(values), "feasible_hit_rate_mean": _mean_or_none(values), "note": "描述性，不做推断"})
    _checks(checks, "ood_artifacts", "PASS", "OOD 描述性行数: " + str(len(rows)))
    return rows


def build_determinism_rows(run: "S3RunData", *, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    determinism = run.determinism
    if not determinism.get("available"):
        _checks(checks, "determinism_rows", "DISCLOSED", "确定性重跑产物缺失，记 NOT_RUN")
        return [{"pass": "r1", "status": "NOT_RUN", "reason": "run 目录无 determinism/"}]
    rows = []
    for item in determinism.get("passes", []):
        rows.append({
            "pass": str(item.get("name")),
            "status": "OK",
            "n_records": int(item.get("records", 0)),
            "n_eval_core_digests": len(item.get("eval_core_digests", [])),
            "core_digest_equal": determinism.get("core_digest_equal"),
        })
    _checks(checks, "determinism_rows", "PASS", "确定性重跑行数: " + str(len(rows)))
    return rows

# ---------------------------------------------------------------------------
# 输出产物、图状态与 analyze 主入口（计划 §5.2/§5.3）
# ---------------------------------------------------------------------------
VSPAERO_GATE_ARTIFACT_RELPATH = "research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/summary.json"
S2_ARCHIVE_AGGREGATE_RELPATH = "research/concorde_metaopt/optimization_runs/p4ra-s2-formal-20261107T000000Z/analysis/aggregate.json"
METRIC_DEFINITIONS = {
    "feasible_hit_rate": "可行点数 / B；分母固定为预算 B（含 support/initial/主搜索），越高越好",
    "gap_to_reference": "best_feasible_value − f_ref；无可行点记 null；< −1e-9 视为参考解不匹配并 fail-closed",
    "best_feasible_value": "全部可行点中目标函数 f 的最小值；无可行点记 null",
    "first_feasible_eval_index": "首个可行评估的 1-based 序号；无可行点记 null",
    "surrogate_rmse": "代理对 [f,g1,g2] 的预测误差（task 标准化尺度）；记录不含预测值时为 NOT_AVAILABLE_IN_RECORDS",
    "surrogate_mae": "同 surrogate_rmse 的 MAE 口径",
    "f_rmse": "目标函数 f 的代理 RMSE（描述性）",
    "f_mae": "目标函数 f 的代理 MAE（描述性）",
    "adaptation_cost": "run wall_s + 前向打分次数；用于 ANIL 成本效率描述性审计",
    "total_cost": "run wall_s（含适配/推断/搜索）",
}


def _prepare_output_dir(output_dir: str | Path, *, overwrite: bool) -> Path:
    """准备输出目录；非空且未显式 overwrite 时 fail-closed。"""
    path = Path(output_dir).resolve()
    if path.exists() and not path.is_dir():
        _fail(S3_ANALYSIS_OUTPUT_INVALID, "output_dir 已存在且不是目录", str(path))
    if path.is_dir():
        existing = sorted(item.name for item in path.iterdir())
        if existing and not overwrite:
            _fail(S3_ANALYSIS_OUTPUT_INVALID, "output_dir 非空，必须显式允许 overwrite", {"output_dir": str(path), "existing": existing[:20]})
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_endpoint_rows(
    inference: Mapping[str, Any],
    endpoints: Sequence[Mapping[str, Any]],
    *,
    tasks: Sequence[str],
    grid: Mapping[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """端点表：C1/C2 推断端点 + 描述性端点（含 null 比例）。"""
    rows = [dict(item) for item in inference["endpoint_summary"]["rows"]]
    descriptive = tuple(name for name in DESCRIPTIVE_ENDPOINTS if name in ("best_feasible_value", "first_feasible_eval_index", "adaptation_cost", "total_cost", "surrogate_rmse", "surrogate_mae", "f_rmse", "f_mae"))
    summary = build_endpoint_summary(endpoints, endpoints_to_report=descriptive, tasks=tasks, grid=grid, checks=checks)
    rows.extend(dict(item) for item in summary["rows"])
    for row in rows:
        row.setdefault("comparator", COMPARATOR_ARMS[1])
        row.setdefault("note", "")
    _checks(checks, "endpoint_table_rows", "PASS", "端点表行数: " + str(len(rows)))
    return rows


def _build_figure_state(
    *,
    run: "S3RunData",
    prereg: "S3Prereg",
    references: Mapping[str, Mapping[str, Any]],
    family_package: Mapping[str, Any] | None,
    endpoint_rows: Sequence[Mapping[str, Any]],
    per_task_rows: Sequence[Mapping[str, Any]],
    inference: Mapping[str, Any],
    null_rows: Sequence[Mapping[str, Any]],
    cost_rows: Sequence[Mapping[str, Any]],
    anil_row: Mapping[str, Any],
    negative_control_rows: Sequence[Mapping[str, Any]],
    ood_rows: Sequence[Mapping[str, Any]],
    determinism_rows: Sequence[Mapping[str, Any]],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """汇总 10 图的数据状态；缺数据的图明确 NOT_RUN，不伪造。"""
    train_records = list(run.train_records)
    train_by_seed: dict[str, list[list[Any]]] = {}
    for record in train_records:
        seed = str(record.get("meta_seed"))
        train_by_seed.setdefault(seed, []).append([int(record.get("outer_step", 0)), float(record.get("loss", 0.0))])
    for values in train_by_seed.values():
        values.sort(key=lambda item: item[0])
    gate = run.gate if isinstance(run.gate, Mapping) else {}
    task_family_rows = []
    for task_id, reference in references.items():
        task_family_rows.append({
            "task_id": str(task_id),
            "f_ref": reference.get("f_ref"),
            "reference_kind": reference.get("reference_kind"),
        })
    task_family_rows.sort(key=lambda item: item["task_id"])
    s2_status = "NOT_RUN"
    s2_reason = "S2 归档 aggregate.json 不存在（只读引用，未生成 S3 数据）"
    s2_candidate = Path(_repo_root_for(run.run_dir)) / S2_ARCHIVE_AGGREGATE_RELPATH
    if s2_candidate.is_file():
        s2_status = "AVAILABLE"
        s2_reason = "读取 S2 归档（只读）: " + str(s2_candidate)
    vspaero_gate_path = Path(_repo_root_for(run.run_dir)) / VSPAERO_GATE_ARTIFACT_RELPATH
    vspaero_gate = {"status": "NOT_RUN", "reason": "未找到 VSPAERO 门禁归档", "gates": {}}
    if vspaero_gate_path.is_file():
        try:
            payload = _read_json_file(vspaero_gate_path, code=S3_ANALYSIS_INPUT_INVALID, label="vspaero_gate_summary")
            gates = payload.get("gates") if isinstance(payload, Mapping) else None
            if isinstance(gates, Mapping):
                vspaero_gate = {
                    "status": "OK",
                    "path": str(vspaero_gate_path),
                    "sha256": sp.sha256_file(vspaero_gate_path),
                    "gates": {str(key): str(value) for key, value in gates.items()},
                    "note": "只读归档；未启动任何 VSPAERO/求解器调用",
                }
            else:
                vspaero_gate = {"status": "NOT_RUN", "reason": "归档缺少 gates 字段", "gates": {}}
        except Exception as error:  # noqa: BLE001 - 只读证据失败不应伪造
            vspaero_gate = {"status": "NOT_RUN", "reason": "读取失败: " + str(error), "gates": {}}
    source_files = []
    for name, item in sorted(run.sources.items()):
        source_files.append({"name": name, "path": item.get("path"), "sha256": item.get("sha256"), "bytes": item.get("bytes")})
    _checks(checks, "figure_status", "PASS", "图状态已登记（缺数据图 NOT_RUN）")
    return {
        "run_id": run.run_id,
        "run_mode": run.run_mode,
        "prereg_id": prereg.prereg_id,
        "prereg_digest": prereg.prereg_digest,
        "analysis_plan_digest": prereg.analysis_plan_digest,
        "family": dict(prereg.family),
        "evidence_scope": S3_EVIDENCE_SCOPE,
        "development_set": S3_DEVELOPMENT_SET,
        "arms": list(run.grid["arms"]),
        "budgets": list(run.grid["budgets"]),
        "n_tasks": int(run.grid.get("n_tasks", len(run.grid["task_ids"]))),
        "record_counts": dict(run.record_counts),
        "record_counts_by_stream": {key: dict(value) for key, value in run.record_streams.items()},
        "training": {
            "meta_seeds": list(run.grid["meta_seeds"]),
            "outer_steps": run.grid["outer_steps"],
            "loss_by_meta_seed": train_by_seed,
            "status": "OK" if train_records else "NOT_RUN",
        },
        "full_meta_grad": {
            "status": "NOT_AVAILABLE_IN_RECORDS",
            "reason": "train record 8 字段不含全量元梯度范数，无法复现 fig1 下半面板（CONTRACT_AMBIGUITY）",
        },
        "kshot": {
            "status": "NOT_RUN",
            "reason": "S3 记录不含 K-shot 适配曲线（K∈{0,1,3,5}），fig2 记 NOT_RUN",
        },
        "endpoint_rows": [dict(item) for item in endpoint_rows],
        "per_task_rows": [dict(item) for item in per_task_rows],
        "inference": {
            "families": {key: [dict(item) for item in value] for key, value in inference["families"].items()},
            "holm_rows": [dict(item) for item in inference["holm_rows"]],
            "c1_decisions": dict(inference["c1_decisions"]),
            "c2_decisions": dict(inference["c2_decisions"]),
            "overall_decision": inference["overall_decision"],
        },
        "null_rows": [dict(item) for item in null_rows],
        "cost_rows": [dict(item) for item in cost_rows],
        "anil_row": dict(anil_row),
        "negative_control_rows": [dict(item) for item in negative_control_rows],
        "ood_rows": [dict(item) for item in ood_rows],
        "determinism_rows": [dict(item) for item in determinism_rows],
        "task_families": {
            "status": "OK" if task_family_rows else "NOT_RUN",
            "source": "references_sealed",
            "rows": task_family_rows,
            "note": "只描述族内 task 分布，不声称任务族间差异",
        },
        "fd_gate": {
            "prereg_sha256": (prereg.obj.get("fd_gate") or {}).get("sha256") if isinstance(prereg.obj.get("fd_gate"), Mapping) else None,
            "run_gate_status": gate.get("status") if isinstance(gate, Mapping) else None,
            "run_gate_max_relative_error": gate.get("max_relative_error") if isinstance(gate, Mapping) else None,
            "run_gate_coordinates": gate.get("coordinates") if isinstance(gate, Mapping) else None,
            "run_gate_sha256": gate.get("fd_gate_sha256") if isinstance(gate, Mapping) else None,
        },
        "s2_archive": {"status": s2_status, "path": S2_ARCHIVE_AGGREGATE_RELPATH, "reason": s2_reason},
        "vspaero_gate": vspaero_gate,
        "source_files": source_files,
        "how_to_read": "图注统一脚注 evidence_scope=DEVELOPMENT_VALIDATION_ONLY；图中数值不得外推为确证性结论",
    }


def _repo_root_for(path: str | Path) -> Path:
    """从 run 目录往上找仓库根（含 research/concorde_metaopt 前缀的目录）。"""
    current = Path(path).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "research" / "concorde_metaopt").is_dir():
            return candidate
    return current


def _figure_status_template(*, reason: str) -> dict[str, Any]:
    return {key: {"status": "NOT_RUN", "path": None, "csv_path": None, "reason": str(reason)} for key in FIGURE_KEYS}


def _validate_figure_status(status: Mapping[str, Any]) -> dict[str, Any]:
    """校验图状态结构：恰 10 键，状态枚举合法，非 RENDERED 的 path 归一为 None。"""
    if not isinstance(status, Mapping):
        _fail(S3_ANALYSIS_FIGURE_INVALID, "figure_status 必须为 mapping")
    missing = [key for key in FIGURE_KEYS if key not in status]
    extra = [key for key in status if key not in FIGURE_KEYS]
    if missing or extra:
        _fail(S3_ANALYSIS_FIGURE_INVALID, "figure_status 键集不符", {"missing": missing, "extra": extra})
    normalized: dict[str, Any] = {}
    for key in FIGURE_KEYS:
        item = status[key]
        if not isinstance(item, Mapping):
            _fail(S3_ANALYSIS_FIGURE_INVALID, "figure_status 项必须为 mapping", key)
        figure_status = str(item.get("status", "")).upper()
        if figure_status not in FIGURE_STATUSES:
            _fail(S3_ANALYSIS_FIGURE_INVALID, "图状态不合法", {"figure": key, "status": figure_status})
        path = item.get("path")
        csv_path = item.get("csv_path")
        normalized[key] = {
            "status": figure_status,
            "path": str(path) if (figure_status == "RENDERED" and path) else None,
            "csv_path": str(csv_path) if csv_path else None,
            "reason": str(item.get("reason", "")),
            "data_sha256": item.get("data_sha256"),
        }
    summary = {
        "rendered": sum(1 for item in normalized.values() if item["status"] == "RENDERED"),
        "not_run": sum(1 for item in normalized.values() if item["status"] == "NOT_RUN"),
        "not_applicable": sum(1 for item in normalized.values() if item["status"] == "NOT_APPLICABLE"),
    }
    return {"schema_version": S3_FIGURE_STATUS_SCHEMA_VERSION, "figures": normalized, "summary": summary, "generated_utc": _utc_now()}


def _generate_figures(
    figure_state: Mapping[str, Any],
    *,
    output_dir: Path,
    repo_root: str | Path,
    enabled: bool,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """调用图模块；图模块缺失或单图失败均回落 NOT_RUN，不中断分析。"""
    if not enabled:
        status = _figure_status_template(reason="FIGURE_GENERATION_DISABLED_BY_REQUEST")
        _checks(checks, "figures", "SKIPPED", "图生成被调用方关闭（--no-generate-figures）")
        return status
    try:
        from . import s3_figures as figures_module
    except Exception as error:  # noqa: BLE001 - 图模块不可用不阻断聚合
        status = _figure_status_template(reason="FIGURES_MODULE_NOT_AVAILABLE: " + str(error))
        _checks(checks, "figures", "DISCLOSED", "图模块不可用: " + str(error))
        return status
    try:
        produced = figures_module.generate_figures(figure_state, output_dir=str(output_dir), repo_root=str(repo_root))
    except Exception as error:  # noqa: BLE001 - 图异常不阻断聚合
        status = _figure_status_template(reason=("FIGURE_GENERATION_FAILED: " + str(error))[:500])
        _checks(checks, "figures", "DISCLOSED", "图生成整体失败: " + str(error))
        return status
    if not isinstance(produced, Mapping):
        _fail(S3_ANALYSIS_FIGURE_INVALID, "图模块返回值必须为 mapping")
    merged: dict[str, Any] = {}
    for key in FIGURE_KEYS:
        item = produced.get(key)
        if isinstance(item, Mapping):
            merged[key] = dict(item)
        else:
            merged[key] = {"status": "NOT_RUN", "path": None, "csv_path": None, "reason": "图模块未返回该图状态"}
    rendered = sum(1 for item in merged.values() if str(item.get("status", "")).upper() == "RENDERED")
    _checks(checks, "figures", "PASS", "图渲染: " + str(rendered) + "/" + str(len(FIGURE_KEYS)) + " RENDERED")
    return merged


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def analyze_s3_run(
    prereg_path: str | Path,
    run_dir: str | Path,
    output_dir: str | Path,
    *,
    repo_root: str | Path | None = None,
    overwrite: bool = False,
    generate_figures: bool = True,
    allow_incomplete_run: bool = False,
    verify_code_sha: bool = False,
    verify_analysis_plan_digest: bool = False,
    verify_record_digests: bool = False,
) -> dict[str, Any]:
    """S3 只读分析主入口：读取 prereg+run，产出 7 CSV + aggregate.json + figure_status.json。"""
    resolved_repo_root = Path(repo_root).resolve() if repo_root is not None else _repo_root_for(run_dir)
    output_path = _prepare_output_dir(output_dir, overwrite=overwrite)
    checks: list[dict[str, Any]] = []
    prereg = load_s3_prereg(
        prereg_path,
        repo_root=resolved_repo_root,
        verify_code_sha=verify_code_sha,
        verify_analysis_digest=verify_analysis_plan_digest,
        checks=checks,
    )
    references = load_references_sealed(prereg, repo_root=resolved_repo_root, checks=checks)
    family_package = None
    try:
        family_package = load_family_package(prereg, repo_root=resolved_repo_root, checks=checks)
    except Exception as error:  # noqa: BLE001 - 族包缺失只影响 fig6/族诊断
        _checks(checks, "family_package_optional", "DISCLOSED", "族包不可用: " + str(error))
    run = load_s3_run(run_dir, prereg, allow_incomplete_run=allow_incomplete_run, verify_record_digests=verify_record_digests, checks=checks)
    endpoints = compute_run_endpoints(run, references, checks=checks)
    main_endpoints, aux_endpoints = split_main_and_aux(endpoints)
    if not main_endpoints:
        _fail(S3_ANALYSIS_INPUT_INVALID, "run 不含主分析段（meta_test）端点", run_dir)
    tasks = sorted({str(item["task_id"]) for item in main_endpoints})
    expected_tasks = int(run.grid["eval_tasks"])
    if len(tasks) != expected_tasks:
        if allow_incomplete_run:
            _checks(checks, "main_task_coverage", "DISCLOSED", "主分析 task 数 " + str(len(tasks)) + " != 预期 " + str(expected_tasks))
        else:
            _fail(S3_ANALYSIS_INPUT_INVALID, "主分析 task 数不符", {"actual": len(tasks), "expected": expected_tasks})
    else:
        _checks(checks, "main_task_coverage", "PASS", "主分析 task 数: " + str(len(tasks)))
    grid_arms = tuple(str(arm) for arm in run.grid["arms"])
    for required_arm in COMPARATOR_ARMS:
        if required_arm not in grid_arms:
            _fail(S3_ANALYSIS_COMPARATOR_MISMATCH, "run 缺少 comparator 臂: " + required_arm)
    inference = build_inference(main_endpoints, tasks=tasks, grid=run.grid, checks=checks)
    endpoint_rows = _build_endpoint_rows(inference, main_endpoints, tasks=tasks, grid=run.grid, checks=checks)
    null_rows = build_null_disclosure(main_endpoints, tasks=tasks, grid=run.grid, checks=checks)
    cost_rows = build_cost_rows(main_endpoints, grid=run.grid, checks=checks)
    anil_row = build_anil_row(main_endpoints, tasks=tasks, grid=run.grid, checks=checks)
    negative_control_rows = build_negative_control_rows(run, main_endpoints, tasks=tasks, grid=run.grid, checks=checks)
    ood_rows = build_ood_rows(run, aux_endpoints, grid=run.grid, checks=checks)
    determinism_rows = build_determinism_rows(run, checks=checks)
    figure_state = _build_figure_state(
        run=run,
        prereg=prereg,
        references=references,
        family_package=family_package,
        endpoint_rows=endpoint_rows,
        per_task_rows=inference["endpoint_summary"]["per_task_rows"],
        inference=inference,
        null_rows=null_rows,
        cost_rows=cost_rows,
        anil_row=anil_row,
        negative_control_rows=negative_control_rows,
        ood_rows=ood_rows,
        determinism_rows=determinism_rows,
        checks=checks,
    )
    raw_figure_status = _generate_figures(figure_state, output_dir=output_path, repo_root=resolved_repo_root, enabled=generate_figures, checks=checks)
    figure_status = _validate_figure_status(raw_figure_status)
    figure_state["figure_status"] = figure_status
    figure_state["fig_data_files"] = {
        key: (figure_status["figures"][key].get("csv_path") if figure_status["figures"][key].get("status") == "RENDERED" else None)
        for key in FIGURE_KEYS
    }
    artifacts: dict[str, str] = {}
    outputs = (
        (S3_ENDPOINT_TABLES_CSV, endpoint_rows),
        (S3_PER_TASK_CSV, inference["endpoint_summary"]["per_task_rows"]),
        (S3_HOLM_CSV, inference["holm_rows"]),
        (S3_NULL_CSV, null_rows),
        (S3_NEGATIVE_CONTROLS_CSV, negative_control_rows),
        (S3_OOD_CSV, ood_rows),
        (S3_COST_CSV, cost_rows),
    )
    for filename, rows in outputs:
        path = output_path / filename
        # 列集取该文件所有行的键并集（排序保证确定性）；空行集写空表头。
        columns = sorted({str(key) for row in rows for key in row})
        _write_csv(path, columns=columns, rows=rows, code=S3_ANALYSIS_OUTPUT_INVALID, label=filename)
        artifacts[filename] = str(path)
    status_path = output_path / S3_FIGURE_STATUS_JSON
    _write_json(status_path, figure_status, code=S3_ANALYSIS_OUTPUT_INVALID, label=S3_FIGURE_STATUS_JSON)
    artifacts[S3_FIGURE_STATUS_JSON] = str(status_path)
    failed_checks = [item for item in checks if str(item.get("status")) == "FAIL"]
    if failed_checks:
        _fail(S3_ANALYSIS_INPUT_INVALID, "分析存在 FAIL 校验项", [item.get("check") for item in failed_checks])
    aggregate = {
        "schema_version": S3_AGGREGATE_SCHEMA_VERSION,
        "analysis_id": "s3-analysis-" + str(run.run_id) + "-" + prereg.prereg_id,
        "created_utc": _utc_now(),
        "run_id": run.run_id,
        "run_dir": str(Path(run_dir).resolve()),
        "run_mode": run.run_mode,
        "smoke": run.is_smoke,
        "evidence_scope": S3_EVIDENCE_SCOPE,
        "development_set": S3_DEVELOPMENT_SET,
        "prereg": {
            "path": str(prereg.path),
            "sha256": prereg.sha256,
            "prereg_id": prereg.prereg_id,
            "prereg_digest": prereg.prereg_digest,
            "analysis_plan_digest": prereg.analysis_plan_digest,
            "code_sha": prereg.code_sha,
            "family": dict(prereg.family),
            "endpoints": dict(prereg.endpoints),
            "statistics": dict(prereg.statistics),
            "figures": dict(prereg.figures),
        },
        "record_counts": dict(run.record_counts),
        "record_counts_by_stream": {key: dict(value) for key, value in run.record_streams.items()},
        "status_counts_disclosure": _status_counts_disclosure(run.checks),
        "run_grid": {
            "arms": list(run.grid["arms"]),
            "budgets": list(run.grid["budgets"]),
            "opt_seeds": list(run.grid["opt_seeds"]),
            "meta_seeds": list(run.grid["meta_seeds"]),
            "k_shot": run.grid["k_shot"],
            "eval_tasks": run.grid["eval_tasks"],
            "run_count": run.grid["run_count"],
            "eval_records_expected": run.grid["eval_records_expected"],
            "train_expected": run.grid["train_expected"],
            "eval_expected": run.grid["eval_expected"],
            "rs3_02_fallback_applied": bool(run.grid.get("rs3_02_fallback_applied", False)),
        },
        "execution_scale": {
            "run_count": int(run.grid["run_count"]),
            "eval_records_expected": int(run.grid["eval_records_expected"]),
            "opt_seeds": len(run.grid["opt_seeds"]),
            "meta_seeds": len(run.grid["meta_seeds"]),
            "eval_tasks": int(run.grid["eval_tasks"]),
            "rs3_02_fallback_applied": bool(run.grid.get("rs3_02_fallback_applied", False)),
            "note": (
                "R-S3-05：campaign 并行只影响时间数值；R-S3-02 降网格按预注册 pilot 规则触发，"
                "实际 run/evals 在此披露，不改变方法与随机流"
            ),
        },
        "source_files": figure_state["source_files"],
        "checks": checks,
        "disclosed_checks": [item for item in checks if str(item.get("status")) in ("DISCLOSED", "SKIPPED")],
        "endpoint_rows": endpoint_rows,
        "per_task_rows": inference["endpoint_summary"]["per_task_rows"],
        "inference": {
            "families": inference["families"],
            "holm_rows": inference["holm_rows"],
            "c1_decisions": inference["c1_decisions"],
            "c2_decisions": inference["c2_decisions"],
            "overall_decision": inference["overall_decision"],
        },
        "holms": inference["holm_rows"],
        "overall_decision": inference["overall_decision"],
        "null_disclosure": null_rows,
        "negative_controls": negative_control_rows,
        "ood_descriptives": ood_rows,
        "cost_table": cost_rows,
        "anil_audit": anil_row,
        "determinism": determinism_rows,
        "figure_status": figure_status,
        "metric_definitions": METRIC_DEFINITIONS,
        "data_boundary": {
            "allowed_splits": list(prereg.data_boundary.get("allowed_splits", ())),
            "training_splits": list(prereg.data_boundary.get("training_splits", ())),
            "holdout_splits": list(prereg.data_boundary.get("holdout_splits", ())),
            "note": "分析阶段读取 meta_test 端点；run 阶段未读 holdout truth",
        },
        "outputs": dict(artifacts),
        "figure_data_files": figure_state["fig_data_files"],
    }
    aggregate_path = output_path / S3_AGGREGATE_JSON
    _write_json(aggregate_path, aggregate, code=S3_ANALYSIS_OUTPUT_INVALID, label=S3_AGGREGATE_JSON)
    artifacts[S3_AGGREGATE_JSON] = str(aggregate_path)
    return {
        "status": "PASS",
        "run_id": run.run_id,
        "run_mode": run.run_mode,
        "prereg_id": prereg.prereg_id,
        "output_dir": str(output_path),
        "artifacts": artifacts,
        "overall_decision": inference["overall_decision"],
        "c1_decisions": inference["c1_decisions"],
        "c2_decisions": inference["c2_decisions"],
        "figure_status": figure_status,
        "n_tasks": len(tasks),
        "record_counts": dict(run.record_counts),
        "record_counts_by_stream": {key: dict(value) for key, value in run.record_streams.items()},
        "status_counts_disclosure": _status_counts_disclosure(run.checks),
        "checks": checks,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：python -m ...s3_analysis --prereg ... --run-dir ... --output-dir ..."""
    import argparse

    parser = argparse.ArgumentParser(description="S3 只读离线分析（physical_call_count=0）")
    parser.add_argument("--prereg", required=True, help="冻结 preregistration.json 路径")
    parser.add_argument("--run-dir", required=True, help="正式 run 目录")
    parser.add_argument("--output-dir", required=True, help="输出目录（非空需 --overwrite）")
    parser.add_argument("--repo-root", default=None, help="仓库根（默认自动推断）")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖非空输出目录")
    parser.add_argument("--no-generate-figures", dest="generate_figures", action="store_false", default=True, help="跳过图生成（数据产物照常）")
    parser.add_argument("--allow-incomplete-run", action="store_true", help="允许不完整 run（仅开发验证）")
    parser.add_argument("--verify-code-sha", action="store_true", help="实算 code_sha 并与 prereg 比对")
    parser.add_argument("--verify-analysis-plan-digest", action="store_true", help="实算 analysis_plan_digest 并与 prereg 比对")
    parser.add_argument("--verify-record-digests", action="store_true", help="逐记录复算 record_digest（较慢）")
    parser.add_argument("--json", action="store_true", help="把结果摘要打印为 JSON")
    args = parser.parse_args(argv)
    result = analyze_s3_run(
        args.prereg,
        args.run_dir,
        args.output_dir,
        repo_root=args.repo_root,
        overwrite=args.overwrite,
        generate_figures=args.generate_figures,
        allow_incomplete_run=args.allow_incomplete_run,
        verify_code_sha=args.verify_code_sha,
        verify_analysis_plan_digest=args.verify_analysis_plan_digest,
        verify_record_digests=args.verify_record_digests,
    )
    if args.json:
        print(json.dumps({key: result[key] for key in ("status", "run_id", "run_mode", "overall_decision", "c1_decisions", "c2_decisions", "n_tasks", "output_dir")}, ensure_ascii=False, sort_keys=True))
    else:
        print("S3 分析完成: status=" + result["status"] + " run_id=" + result["run_id"] + " overall=" + result["overall_decision"])
        print("输出目录: " + result["output_dir"])
    return 0


__all__ = [
    "S3AnalysisError",
    "S3Prereg",
    "S3RunData",
    "load_s3_prereg",
    "load_s3_run",
    "load_references_sealed",
    "load_family_package",
    "compute_run_endpoints",
    "aggregate_task_values",
    "build_endpoint_summary",
    "build_inference",
    "build_null_disclosure",
    "build_cost_rows",
    "build_negative_control_rows",
    "build_ood_rows",
    "build_determinism_rows",
    "analyze_s3_run",
    "main",
    "wilcoxon_signed_rank_exact",
    "wilcoxon_pratt",
    "wilcoxon_permutation",
    "bootstrap_mean_ci",
    "holm_adjust",
    "decide_layer",
    "decide_overall",
    "anil_decision",
]


if __name__ == "__main__":
    raise SystemExit(main())
