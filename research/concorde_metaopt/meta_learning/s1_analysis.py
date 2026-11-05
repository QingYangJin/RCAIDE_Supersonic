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
PREREG_DIGEST = "6981f503fd6ea5a9fbe5de2d1825ae8993eb17e9fda5d2ff158e9248d88fd3df"
ANALYSIS_PLAN_DIGEST = family_v3.ANALYSIS_PLAN_DIGEST
FAMILY_VERSION = family_v3.FAMILY_VERSION
FAMILY_FINGERPRINT = "e56e6921be6b94e6611a24618a6e331cd7e4417597926d089d71b00da8c1c0c3"
SPLIT_HASH = "cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae"
RADIUS_BASE = 0.64

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
    raw_sha256: Mapping[str, str] = field(default_factory=dict)
    canonical_sha256: Mapping[str, str] = field(default_factory=dict)
    sha256sums: Mapping[str, str] = field(default_factory=dict)

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
    if manifest.get("family_id") != family_v3.FAMILY_ID or manifest.get("family_version") != family_v3.FAMILY_VERSION:
        raise S1FreezeValidationError("digest_manifest 家族身份不符")
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
    if summary.get("schema_version") not in ("p4ra-freeze-summary-2", "p4ra-freeze-summary-1"):
        raise S1FreezeValidationError(f"freeze_summary schema 不符：{summary.get('schema_version')!r}")
    if summary.get("family_id") != family_v3.FAMILY_ID:
        raise S1FreezeValidationError("freeze_summary family_id 不符")
    if summary.get("family_version") != family_v3.FAMILY_VERSION:
        raise S1FreezeValidationError("freeze_summary family_version 不符")
    if int(summary.get("family_seed", -1)) != family_v3.FAMILY_SEED:
        raise S1FreezeValidationError("freeze_summary family_seed 不符")
    if summary.get("formula_version") != family_v3.FORMULA_VERSION:
        raise S1FreezeValidationError("freeze_summary formula_version 不符")
    if not _is_finite_number(summary.get("radius_base")) or abs(float(summary["radius_base"]) - RADIUS_BASE) > 1e-12:
        raise S1FreezeValidationError(f"freeze_summary radius_base 必须为冻结值 {RADIUS_BASE}")
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
) -> None:
    """三方/五方回显一致性：family_fingerprint/split_hash/prereg_digest/analysis_plan_digest 等。"""
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
    if versions != {family_v3.FAMILY_VERSION}:
        raise S1FreezeValidationError(f"五方 family_version 不一致：{versions}")
    fingerprints = {
        frozen.get("family_fingerprint"),
        prereg.get("family_fingerprint"),
        split.get("family_fingerprint"),
        orchestration.get("family_fingerprint"),
    }
    if fingerprints != {FAMILY_FINGERPRINT}:
        raise S1FreezeValidationError(f"family_fingerprint 回显不一致：{fingerprints}")
    frozen_split_hash = frozen.get("split", {}).get("split_hash")
    split_hashes = {frozen_split_hash, prereg.get("split_hash"), split.get("split_hash"), orchestration.get("split_hash")}
    if split_hashes != {SPLIT_HASH}:
        raise S1FreezeValidationError(f"split_hash 回显不一致：{split_hashes}")
    if prereg.get("split_digest") != SPLIT_HASH:
        raise S1FreezeValidationError("prereg.split_digest 与冻结 split_hash 不一致")
    if frozen.get("split", {}).get("manifest_sha256") != _canonical_artifact_digest(split):
        raise S1FreezeValidationError("frozen.split.manifest_sha256 与 split payload 不一致")
    if prereg.get("frozen_family_sha256") != frozen.get("sha256"):
        raise S1FreezeValidationError("prereg.frozen_family_sha256 与 frozen.sha256 不一致")
    prereg_digests = {prereg.get("prereg_digest"), orchestration.get("prereg_digest")}
    if prereg_digests != {PREREG_DIGEST}:
        raise S1FreezeValidationError(f"prereg_digest 回显不一致：{prereg_digests}")
    if family_v3.compute_prereg_digest(prereg) != PREREG_DIGEST:
        raise S1FreezeValidationError("prereg_digest 重算不一致")
    plan_digests = {
        prereg.get("analysis_plan_digest"),
        frozen.get("analysis_plan_digest"),
        orchestration.get("analysis_plan_digest"),
        ANALYSIS_PLAN_DIGEST,
    }
    if plan_digests != {ANALYSIS_PLAN_DIGEST}:
        raise S1FreezeValidationError(f"analysis_plan_digest 回显不一致：{plan_digests}")
    analysis_plan = prereg.get("analysis_plan")
    if not isinstance(analysis_plan, Mapping) or family_v3.digest(analysis_plan) != ANALYSIS_PLAN_DIGEST:
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
        float(orchestration.get("radius_base", RADIUS_BASE)),
    }
    if len(radii) != 1 or abs(next(iter(radii)) - RADIUS_BASE) > 1e-12:
        raise S1FreezeValidationError(f"radius_base 回显不一致：{radii}")
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
) -> FrozenBundle:
    """加载并强校验 S1 冻结包；任一不通过抛 S1FreezeValidationError（fail-closed）。"""
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
    try:
        family_v3.verify_frozen_family_v3(frozen)
        family_v3.verify_preregistration_v3(prereg, frozen_family=frozen)
        family_v3.verify_split_manifest_v3(split)
    except family_v3.FamilyV3Error as exc:
        raise S1FreezeValidationError(f"冻结载荷自校验失败：{exc}") from exc
    if frozen.get("sha256") != _canonical_artifact_digest(frozen):
        raise S1FreezeValidationError("frozen_family.sha256 自校验失败")
    if prereg.get("sha256") != _canonical_artifact_digest(prereg):
        raise S1FreezeValidationError("preregistration.sha256 自校验失败")
    _verify_budget_fairness(payloads["budget_fairness_report.json"])
    _verify_tasks_payload(payloads["tasks.json"], split)
    _cross_check_echo_chain(frozen, prereg, split, payloads["freeze_summary.json"], raw=raw)
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
        raw_sha256=raw_sha,
        canonical_sha256=canonical_sha,
        sha256sums=sums,
    )

# ---------------------------------------------------------------------------
# run_records 加载与记录级强校验
# ---------------------------------------------------------------------------
S1_RECORD_SCHEMA_VERSION = "p4ra-s1-run-record-1"
RECORD_KNOWN_FIELDS = set(RECORD_REQUIRED_FIELDS) | {"schema_version", "clone_of", "inference_eligible"}
FAILURE_REASONS = tuple(FAILURE_REASONS_REQUIRED_FOR)
TRUE_NULL_RATE_TOL = 1e-12


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


def _validate_cost(cost: Any, index: int) -> None:
    if not isinstance(cost, Mapping):
        raise S1RecordValidationError(f"[{index}] cost 必须是 object")
    expected = {"adaptation_wall_s", "proxy_scoring_cost", "peak_memory_mb", "total_wall_s"}
    if set(cost) != expected:
        raise S1RecordValidationError(f"[{index}] cost 键必须为 {sorted(expected)}，实际 {sorted(cost)}")
    for name in expected:
        value = cost[name]
        if value is not None and (not _is_number(value) or not math.isfinite(float(value)) or float(value) < 0):
            raise S1RecordValidationError(f"[{index}] cost.{name} 必须是非负有限数或 null")


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
        _validate_identifiability(record, index)
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
) -> PairedEndpoint | None:
    """构造任务级配对样本；缺少任一臂单元时返回 None（由调用方判定是否 fail-closed）。"""
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
    treatment_values: list[float | None] = []
    reference_values: list[float | None] = []
    paired: list[str] = []
    differences: list[float] = []
    for task_id in task_ids:
        left = treatment_cell.endpoint_per_task.get(task_id, {}).get(endpoint)
        right = reference_cell.endpoint_per_task.get(task_id, {}).get(endpoint)
        treatment_values.append(left)
        reference_values.append(right)
        if left is not None and right is not None:
            paired.append(task_id)
            differences.append(float(left) - float(right))
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


def endpoint_improvement(paired: PairedEndpoint) -> float | None:
    """正数表示处理臂优于参考臂（按端点方向统一符号）。

    - best_feasible_value / gap_to_reference：相对改善 =(参考均值 - 处理均值)/max(|参考均值|,1e-12)
    - feasible_hit_rate：绝对改善 = 处理均值 - 参考均值
    - first_feasible_eval_index：绝对改善 = 参考均值 - 处理均值（评价次数越少越好）
    """
    if paired.n_pairs == 0:
        return None
    treatment = [value for value in paired.treatment_values if value is not None]
    reference = [value for value in paired.reference_values if value is not None]
    if not treatment or not reference:
        return None
    treatment_mean = sum(treatment) / len(treatment)
    reference_mean = sum(reference) / len(reference)
    if paired.endpoint in ("best_feasible_value", "gap_to_reference"):
        return float((reference_mean - treatment_mean) / max(abs(reference_mean), 1e-12))
    if paired.endpoint == "feasible_hit_rate":
        return float(treatment_mean - reference_mean)
    if paired.endpoint == "first_feasible_eval_index":
        return float(reference_mean - treatment_mean)
    raise S1AnalysisError(f"端点 {paired.endpoint!r} 不属于 4 个主端点")


def decide_endpoint(
    paired: PairedEndpoint,
    *,
    test: Mapping[str, Any],
    p_adjusted: float | None,
    improvement: float | None,
) -> dict[str, Any]:
    """按预注册阈值给出单端点判定（fail-closed：缺信息一律 INCONCLUSIVE）。"""
    endpoint = paired.endpoint
    budget = paired.budget_B
    threshold = _endpoint_threshold(endpoint, budget)
    reasons: list[str] = []
    null_rates = {
        "treatment": paired.null_rate_treatment,
        "reference": paired.null_rate_reference,
    }
    max_null_rate = max(null_rates.values()) if null_rates else 1.0
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
    elif float(p_adjusted) < ALPHA and float(improvement) >= threshold:
        decision = DECISION_BENEFIT
        reasons.append(f"p_adj={float(p_adjusted):.6g} < {ALPHA} 且改善 {float(improvement):.6g} >= 阈值 {threshold:.6g}")
    elif float(p_adjusted) < ALPHA and float(improvement) <= -threshold:
        decision = DECISION_HARM
        reasons.append(f"p_adj={float(p_adjusted):.6g} < {ALPHA} 且恶化 {float(improvement):.6g} <= -阈值 {-threshold:.6g}")
    else:
        reasons.append(f"p_adj={p_adjusted if p_adjusted is None else format(float(p_adjusted), '.6g')} 或改善 {improvement if improvement is None else format(float(improvement), '.6g')} 未达显著/阈值")
    return {
        "decision": decision,
        "decision_reasons": reasons,
        "threshold": float(threshold),
        "improvement": None if improvement is None else float(improvement),
        "p_adjusted": None if p_adjusted is None else float(p_adjusted),
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
    decision = decide_endpoint(paired, test=test, p_adjusted=p_adjusted, improvement=improvement)
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
        "ci_low": ci["low"],
        "ci_high": ci["high"],
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
    }
    return row


def collect_hypotheses(
    cells: Mapping[tuple[str, int, int, str], AggregatedCell],
    bundle: FrozenBundle,
    *,
    split: str,
    inference_ks: Sequence[int] = (1, 3, 5),
) -> dict[str, Any]:
    """构造全部可检验配对（C1..C5 x B x K x 4 主端点），并做 Holm（族=K）。"""
    pairs: list[PairedEndpoint] = []
    for K in inference_ks:
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
                    if paired is not None:
                        pairs.append(paired)
    # 先原始 p 值，再按 K 分组 Holm。
    raw: list[tuple[PairedEndpoint, dict[str, Any]]] = []
    for paired in pairs:
        test = wilcoxon_signed_rank(paired.differences)
        raw.append((paired, test))
    by_k: dict[int, list[int]] = {}
    for index, (paired, _) in enumerate(raw):
        by_k.setdefault(int(paired.K), []).append(index)
    adjusted = [None] * len(raw)
    for K in sorted(by_k):
        indices = by_k[K]
        values = [raw[index][1]["p_value"] for index in indices]
        for index, value in zip(indices, holm_adjust(values)):
            adjusted[index] = value
    rows: list[dict[str, Any]] = []
    for index, (paired, _test) in enumerate(raw):
        rows.append(analyze_pair(paired, p_adjusted=adjusted[index]))
    return {
        "split": split,
        "n_hypotheses": len(rows),
        "holm_family_definition": "同 K 内全部比较 x 2 预算 x 4 主端点",
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
# 输出层：聚合产物、CSV、figure_status 与 CLI
# ---------------------------------------------------------------------------
S1_OUTPUT_FILES = (
    "aggregate.json",
    "s1_endpoint_tables.csv",
    "s1_identifiability_table.csv",
    "s1_budget_audit.csv",
    "s1_negative_controls.csv",
    "figure_status.json",
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
) -> list[dict[str, Any]]:
    collected = collect_hypotheses(cells, bundle, split=MAIN_SPLIT, inference_ks=INFERENCE_KS)
    return list(collected["rows"])


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
) -> dict[str, Any]:
    return {
        "freeze_dir_name": bundle.freeze_dir.name,
        "freeze_raw_sha256": {name: str(value) for name, value in sorted(bundle.raw_sha256.items())},
        "run_records_files": [Path(source).name for source in sources],
        "n_run_record_files": len(sources),
        "record_count": int(record_count),
        "meta_training_log_name": None if meta_training_log is None else Path(meta_training_log).name,
        "determinism_report_name": None if determinism_report is None else Path(determinism_report).name,
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
) -> dict[str, Any]:
    """S1 只读分析入口：校验 -> 聚合 -> 统计 -> 判定 -> 写出合同产物。

    fail-closed：冻结包、run_records、CLONE 等价性、主 split 网格完整性任一失败即抛
    S1AnalysisError/S1FreezeValidationError/S1RecordValidationError，不产出部分结论。
    """
    bundle = load_frozen_bundle(
        freeze_dir,
        verify_checksums=verify_checksums,
        verify_sha256sums=verify_sha256sums,
    )
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
    cells = aggregate_run_records(all_records, bundle)
    hypotheses = _hypothesis_rows(cells, bundle)
    endpoint_rows = _endpoint_table_rows(cells, bundle, hypotheses)
    primary = primary_conclusion(hypotheses)
    reproduction = secondary_reproduction_conclusion(hypotheses)
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
        "input": _input_manifest(
            bundle,
            all_sources,
            len(all_records),
            meta_training_log=meta_training_log,
            determinism_report=determinism_report,
        ),
        "freeze_echo": {
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
            "holm_family": "同 K 内全部比较 x 2 预算 x 4 主端点",
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
        "statistical_rules": {
            "unit": "task",
            "aggregation": "opt seed -> (task, meta_seed) 均值；meta_seed 等权 -> 任务级",
            "test": "双侧 Wilcoxon 符号秩（n<=20 无并列用精确分布；并列用正态近似+并列/连续性修正）",
            "multiple_comparison": "Holm-Bonferroni（族=同 K 内比较 x 预算 x 4 主端点）",
            "ci": "配对差值均值的百分位 bootstrap（10000 次，seed=20261105）",
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
        ],
        "contract_ambiguities": [
            "执行计划 §6 只规定 C1 单层规则（>=2 BENEFIT 且 0 HARM），未规定 K=3 与 K=5 如何合成；"
            "本实现取保守合取并在 primary_conclusion 中披露，待 Lead 裁决",
            "first_feasible_eval_index 的改善阈值按 ceil(0.05*B) 取整；"
            "合同写“仅同 K 内比较”，本实现按任务级配对差判定",
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
    aggregate["figure_status"] = figure_status
    _write_json(output_dir_path / "aggregate.json", aggregate)
    _write_csv(output_dir_path / "s1_endpoint_tables.csv", endpoint_rows, ENDPOINT_TABLE_COLUMNS)
    _write_csv(output_dir_path / "s1_identifiability_table.csv", identifiability_rows, IDENTIFIABILITY_COLUMNS)
    _write_csv(output_dir_path / "s1_budget_audit.csv", budget_rows, BUDGET_AUDIT_COLUMNS)
    _write_csv(output_dir_path / "s1_negative_controls.csv", negative["rows"], NEGATIVE_CONTROL_COLUMNS)
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
    args = parser.parse_args(argv)
    try:
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
        )
    except S1AnalysisError as exc:
        print(f"S1_ANALYSIS_FAILED: {exc}", file=sys.stderr)
        return 2
    summary = {
        "status": "PASS",
        "n_records": int(aggregate["validation"]["record_count"]),
        "primary_overall": aggregate["primary_conclusion"]["overall"],
        "secondary_reproduction": aggregate["secondary_reproduction"]["status"],
        "negative_controls": aggregate["negative_controls"]["status"],
        "output_dir": str(Path(args.output_dir)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
