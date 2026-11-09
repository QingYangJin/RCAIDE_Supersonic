"""S3 预注册（prereg）、共享 schema 常量与哈希算法（单源）。

本模块是计划 v1.2 §4.3/§6.1 的唯一权威实现：
- S3_*_SCHEMA_VERSION 常量与 run_config/run_summary/record/data_manifest/model_manifest
  字段清单，由 s3_runner.py、s3_analysis.py 直接 import，禁止复制字面量；
- canonical_json / code_sha / analysis_code_sha / task_ids_sha256 /
  task_fingerprint / analysis_plan_digest / record_digest / episode_digest /
  history_digest / prereg_digest / package_sha256 等哈希算法；
- 后续段落提供 build_preregistration / verify_preregistration / write/read。

边界：本模块只做纯计算与文件读取（哈希），不启动任何求解器、不访问网络、
不读取 meta_test/meta_test_ood/meta_test_negative_control 的数据行。
physical_call_count 恒为 0。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# schema 版本（计划 §4.3 单源）
# ---------------------------------------------------------------------------
S3_RUN_CONFIG_SCHEMA_VERSION = "p4ra-s3-run-config-v1"
S3_RUN_SUMMARY_SCHEMA_VERSION = "p4ra-s3-run-summary-v1"
S3_RECORD_SCHEMA_VERSION = "p4ra-s3-record-v1"
S3_AGGREGATE_SCHEMA_VERSION = "p4ra-s3-aggregate-v1"
S3_PREREG_SCHEMA_VERSION = "p4ra-s3-prereg-v1"
S3_DATA_MANIFEST_SCHEMA_VERSION = "p4ra-s3-data-manifest-v1"
S3_MODEL_MANIFEST_SCHEMA_VERSION = "p4ra-s3-model-manifest-v1"
S3_GATE_SCHEMA_VERSION = "p4ra-s3-gate-v1"

# ---------------------------------------------------------------------------
# 字段清单（计划 §4.3，逐项顺序即文档顺序；集合相等性由 verify 检查）
# ---------------------------------------------------------------------------
S3_RUN_CONFIG_REQUIRED_FIELDS = (
    "schema_version",
    "run_id",
    "run_mode",
    "prereg_id",
    "prereg_digest",
    "analysis_plan_digest",
    "code_sha",
    "campaign_authorization_id",
    "campaign_authorization_utc",
    "family_package",
    "task_ids_sha256",
    "references_sealed_sha256",
    "data_boundary",
    "models",
    "arms",
    "budgets",
    "seeds",
    "episode_bank",
    "evaluation_grid",
    "k_sweep",
    "fd_or_gradient_gate",
    "record_counts",
    "record_schemas",
    "resource_limits",
    "physical_call_count",
    "evidence_scope",
    "scope_notes",
)
S3_RUN_CONFIG_OPTIONAL_FIELDS = ("smoke_overrides",)

S3_RUN_SUMMARY_REQUIRED_FIELDS = (
    "schema_version",
    "run_id",
    "run_mode",
    "created_utc",
    "status",
    "record_counts",
    "status_counts",
    "per_run",
    "models",
    "resources",
    "determinism",
    "fd_or_gradient_gate_sha256",
    "data_manifest_sha256",
    "negative_controls",
    "physical_call_count",
    "evidence_scope",
    "environment",
    "scope_notes",
)

S3_EVAL_RECORD_FIELDS = (
    "schema_version",
    "run_id",
    "task_id",
    "split",
    "arm_id",
    "budget",
    "opt_seed",
    "meta_seed",
    "evaluation_index",
    "design",
    "f",
    "g1",
    "g2",
    "feasible",
    "source",
    "phase",
    "holdout_truth_read",
    "wall_s",
    "record_digest",
)

S3_TRAIN_RECORD_FIELDS = (
    "schema_version",
    "run_id",
    "meta_seed",
    "outer_step",
    "loss",
    "wall_s",
    "train_episode_digest",
    "record_digest",
)

S3_DATA_MANIFEST_FIELDS = (
    "schema_version",
    "run_id",
    "campaign_authorization_id",
    "campaign_authorization_utc",
    "data_boundary",
    "split_task_ids",
    "split_task_ids_sha256",
    "references_sealed_sha256",
    "holdout_truth_read_phase",
    "physical_call_count",
    "solver_processes_started",
    "synthetic_call_count",
    "artifact_sha256",
)

S3_MODEL_MANIFEST_FIELDS = (
    "schema_version",
    "run_id",
    "models",
)
S3_MODEL_ENTRY_FIELDS = (
    "arm_type",
    "meta_seed",
    "config",
    "path",
    "sha256",
    "train_wall_s",
    "peak_memory_mb",
    "episode_bank_sha256",
    "final_train_loss",
)

# ---------------------------------------------------------------------------
# 计划枚举与阈值
# ---------------------------------------------------------------------------
S3_RUN_MODES = ("FORMAL", "SMOKE")
S3_RECORD_STATUSES = ("OK", "FAILED")
S3_SOURCES = ("support", "initial", "bo", "de")
S3_PHASES = ("TRAIN", "DEV", "EVAL", "OOD", "NEGATIVE_CONTROL")
S3_ALLOWED_SPLITS = (
    "dev",
    "meta_train",
    "meta_validation",
    "meta_test",
    "meta_test_ood",
    "meta_test_negative_control",
)
S3_TRAIN_SPLITS = ("meta_train",)
S3_DEV_SPLITS = ("dev", "meta_validation")
S3_HOLDOUT_SPLITS = ("meta_test", "meta_test_ood", "meta_test_negative_control")
S3_SPLIT_COUNTS = {
    "meta_train": 60,
    "meta_validation": 20,
    "meta_test": 20,
    "meta_test_ood": 10,
    "meta_test_negative_control": 10,
}
S3_EVIDENCE_SCOPE = "DEVELOPMENT_VALIDATION_ONLY"
S3_DEVELOPMENT_SET = "meta_validation"

S3_ARMS = (
    "S3-BO-RANDOM",
    "S3-BO-FOMAML-OBJ",
    "S3-BO-FOMAML-CON",
    "S3-BO-ANIL-CON",
    "S3-DE",
)
S3_BUDGETS = (64, 128)
S3_K_SHOT = 5
S3_BO_INITIAL_DESIGN_COUNT = 3
S3_INITIAL_DESIGN_COUNT = 8
S3_RESOURCE_LIMITS = {
    "per_run_wall_s": 60,
    "peak_memory_mb": 8192,
    "total_wall_s": 7200,
    # Lead m07082：单核等效 Σ run wall 硬上限（≈1.2× 实测 23,400 s）；超限停止并交部分产物
    "sum_run_wall_limit_s": 28000,
}
S3_SMOKE_OVERRIDE_KEYS = (
    "outer_steps",
    "meta_seeds",
    "budgets",
    "opt_seeds",
    "eval_tasks",
    "k_sweep",
    "fd_coordinates",
)
S3_SMOKE_FIXED = {
    "outer_steps": 2,
    "meta_seeds": (0,),
    "eval_tasks": 4,
    "episode_bank_episodes": 16,
}
# SMOKE 网格：4 task x 5 arm x 2 budget x 1 opt x 1 meta = 40 runs
S3_SMOKE_RUNS = 40

S3_FD_MAX_COORDINATES = 32
S3_FD_RELATIVE_EPSILON = 1e-6
S3_FD_TOLERANCE = 1e-6
S3_FD_DENOMINATOR_FLOOR = 1e-12
S3_FD_EPISODE_COUNT = 4
S3_FD_MODE = "full"

S3_CODE_SHA_FILES = (
    "research/concorde_metaopt/meta_learning/m5_arms.py",
    "research/concorde_metaopt/meta_learning/maml.py",
    "research/concorde_metaopt/meta_learning/s3_analysis.py",
    "research/concorde_metaopt/meta_learning/s3_figures.py",
    "research/concorde_metaopt/meta_learning/s3_prereg.py",
    "research/concorde_metaopt/meta_learning/s3_runner.py",
    "research/concorde_metaopt/meta_learning/task_family.py",
)
S3_ANALYSIS_CODE_SHA_FILES = (
    "research/concorde_metaopt/meta_learning/s3_analysis.py",
    "research/concorde_metaopt/meta_learning/s3_figures.py",
)

# 计划 §6.2 固定向量的已提交哈希（只读常量；测试读 hash_vectors.json 对照）
HASH_VECTORS_RELPATH = "research/concorde_metaopt/evidence/s3/hash_vectors.json"
HASH_VECTORS_SHA256 = "bde487fb6ed49768ca76e328a31c0efab77d2bd39d41c0ac99def4bb8e876203"

# ---------------------------------------------------------------------------
# 错误码
# ---------------------------------------------------------------------------
S3_PREREG_ERROR = "S3_PREREG_ERROR"
S3_PREREG_SCHEMA_INVALID = "S3_PREREG_SCHEMA_INVALID"
S3_PREREG_DIGEST_MISMATCH = "S3_PREREG_DIGEST_MISMATCH"
S3_PREREG_PLACEHOLDER_REJECTED = "S3_PREREG_PLACEHOLDER_REJECTED"
S3_PREREG_CODE_SHA_MISMATCH = "S3_PREREG_CODE_SHA_MISMATCH"
S3_PREREG_FAMILY_MISMATCH = "S3_PREREG_FAMILY_MISMATCH"
S3_PREREG_HASH_VECTORS_MISMATCH = "S3_PREREG_HASH_VECTORS_MISMATCH"
S3_PREREG_REFERENCES_MISMATCH = "S3_PREREG_REFERENCES_MISMATCH"
S3_PREREG_RESOURCE_LIMITS_INVALID = "S3_PREREG_RESOURCE_LIMITS_INVALID"
S3_PREREG_DATA_BOUNDARY_ERROR = "S3_PREREG_DATA_BOUNDARY_ERROR"
S3_PREREG_BUDGET_MISMATCH = "S3_PREREG_BUDGET_MISMATCH"
S3_PREREG_FILE_ERROR = "S3_PREREG_FILE_ERROR"


class S3PreregError(RuntimeError):
    """S3 prer¬eg 构建/校验错误（fail-closed）。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        self.message = str(message)
        super().__init__(self.code + ": " + self.message)


# ---------------------------------------------------------------------------
# canonical JSON 与基础哈希（计划 §6.1）
# ---------------------------------------------------------------------------
def canonical_json(obj: Any) -> str:
    """计划 §6.1 唯一 canonical 形式（返回 UTF-8 文本，不含尾换行）。"""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_json_bytes(obj: Any) -> bytes:
    return canonical_json(obj).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_sha256(obj: Any) -> str:
    return sha256_bytes(canonical_json_bytes(obj))


def code_sha_from_files(files: Mapping[str, str]) -> str:
    """计划 §6.1 code_sha 行算法：'<path>\\t<hex>' 按 path 排序后换行连接再 sha256。

    files 为 {相对仓库路径: sha256 hex}；用于固定向量与机械复算（不读磁盘）。
    """
    entries: list[tuple[str, str]] = []
    for rel, digest in files.items():
        text = str(digest).lower()
        if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
            raise S3PreregError(
                S3_PREREG_SCHEMA_INVALID,
                "code_sha 输入不是 64 位小写 hex: " + str(rel),
            )
        entries.append((str(rel), text))
    entries.sort(key=lambda item: item[0])
    payload = "\n".join(path + "\t" + digest for path, digest in entries)
    return sha256_text(payload)


def code_sha_for_files(repo_root: str | Path, relpaths: Sequence[str]) -> str:
    """计划 §6.1 code_sha：读取实际文件字节后按 code_sha_from_files 计算。"""
    root = Path(repo_root)
    entries: dict[str, str] = {}
    for rel in relpaths:
        path = root / rel
        if not path.is_file():
            raise S3PreregError(
                S3_PREREG_FILE_ERROR,
                "code_sha 文件不存在: " + str(rel),
            )
        entries[str(rel)] = sha256_file(path)
    return code_sha_from_files(entries)


def compute_code_sha(repo_root: str | Path) -> str:
    return code_sha_for_files(repo_root, S3_CODE_SHA_FILES)


def compute_analysis_code_sha(repo_root: str | Path) -> str:
    return code_sha_for_files(repo_root, S3_ANALYSIS_CODE_SHA_FILES)


def task_ids_sha256(task_ids: Iterable[str]) -> str:
    ids = sorted(str(task_id) for task_id in task_ids)
    return sha256_text("\n".join(ids))


def task_fingerprint(
    *,
    family_id: str,
    formula_version: str,
    task_id: str,
    seed: int,
    params: Mapping[str, Any],
) -> str:
    payload = {
        "family_id": str(family_id),
        "formula_version": str(formula_version),
        "task_id": str(task_id),
        "seed": int(seed),
        "params": dict(params),
    }
    return canonical_sha256(payload)[:16]


def analysis_plan_digest(
    *,
    endpoints: Any,
    statistics: Any,
    figures: Any,
    analysis_code_sha: str,
) -> str:
    payload = {
        "endpoints": endpoints,
        "statistics": statistics,
        "figures": figures,
        "analysis_code_sha": str(analysis_code_sha),
    }
    return canonical_sha256(payload)


def record_digest(record: Mapping[str, Any]) -> str:
    body = {key: value for key, value in dict(record).items() if key != "record_digest"}
    return canonical_sha256(body)


def episode_digest(episode: Mapping[str, Any]) -> str:
    body = {key: value for key, value in dict(episode).items() if key != "episode_digest"}
    return canonical_sha256(body)


def history_digest(records: Sequence[Mapping[str, Any]]) -> str:
    digests = "\n".join(str(record["record_digest"]) for record in records)
    return sha256_text(digests)


def prereg_digest(prereg: Mapping[str, Any]) -> str:
    body = {
        key: value
        for key, value in dict(prereg).items()
        if key not in ("prereg_id", "prereg_digest")
    }
    return canonical_sha256(body)


def package_sha256(repo_root: str | Path) -> str:
    """计划 §6.1 package_sha256：evidence/s3 下全部文件（排除清单文件）。"""
    root = Path(repo_root) / "research" / "concorde_metaopt" / "evidence" / "s3"
    if not root.is_dir():
        raise S3PreregError(
            S3_PREREG_FILE_ERROR,
            "证据包目录不存在: " + str(root),
        )
    excluded = {"PACKAGE_MANIFEST.json", "SHA256SUMS.txt"}
    entries: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in excluded:
            continue
        entries.append((rel, sha256_file(path)))
    entries.sort(key=lambda item: item[0])
    payload = "\n".join(rel + "\t" + digest for rel, digest in entries)
    return sha256_text(payload)


__all__ = [
    "S3_AGGREGATE_SCHEMA_VERSION",
    "S3_ALLOWED_SPLITS",
    "S3_ANALYSIS_CODE_SHA_FILES",
    "S3_ARMS",
    "S3_BO_INITIAL_DESIGN_COUNT",
    "S3_BUDGETS",
    "S3_CODE_SHA_FILES",
    "S3_DATA_MANIFEST_FIELDS",
    "S3_DATA_MANIFEST_SCHEMA_VERSION",
    "S3_DEVELOPMENT_SET",
    "S3_EVAL_RECORD_FIELDS",
    "S3_EVIDENCE_SCOPE",
    "S3_FD_DENOMINATOR_FLOOR",
    "S3_FD_EPISODE_COUNT",
    "S3_FD_MAX_COORDINATES",
    "S3_FD_MODE",
    "S3_FD_RELATIVE_EPSILON",
    "S3_FD_TOLERANCE",
    "S3_GATE_SCHEMA_VERSION",
    "S3_HOLDOUT_SPLITS",
    "S3_INITIAL_DESIGN_COUNT",
    "S3_K_SHOT",
    "S3_MODEL_ENTRY_FIELDS",
    "S3_MODEL_MANIFEST_FIELDS",
    "S3_MODEL_MANIFEST_SCHEMA_VERSION",
    "S3_PHASES",
    "S3_PREREG_BUDGET_MISMATCH",
    "S3_PREREG_CODE_SHA_MISMATCH",
    "S3_PREREG_DATA_BOUNDARY_ERROR",
    "S3_PREREG_DIGEST_MISMATCH",
    "S3_PREREG_ERROR",
    "S3_PREREG_FAMILY_MISMATCH",
    "S3_PREREG_FILE_ERROR",
    "S3_PREREG_HASH_VECTORS_MISMATCH",
    "S3_PREREG_PLACEHOLDER_REJECTED",
    "S3_PREREG_REFERENCES_MISMATCH",
    "S3_PREREG_RESOURCE_LIMITS_INVALID",
    "S3_PREREG_SCHEMA_INVALID",
    "S3_PREREG_SCHEMA_VERSION",
    "S3_RECORD_SCHEMA_VERSION",
    "S3_RECORD_STATUSES",
    "S3_RESOURCE_LIMITS",
    "S3_RUN_CONFIG_OPTIONAL_FIELDS",
    "S3_RUN_CONFIG_REQUIRED_FIELDS",
    "S3_RUN_CONFIG_SCHEMA_VERSION",
    "S3_RUN_MODES",
    "S3_RUN_SUMMARY_REQUIRED_FIELDS",
    "S3_RUN_SUMMARY_SCHEMA_VERSION",
    "S3_SMOKE_FIXED",
    "S3_SMOKE_OVERRIDE_KEYS",
    "S3_SMOKE_RUNS",
    "S3_SOURCES",
    "S3_SPLIT_COUNTS",
    "S3_TRAIN_RECORD_FIELDS",
    "S3_TRAIN_SPLITS",
    "S3_DEV_SPLITS",
    "HASH_VECTORS_RELPATH",
    "HASH_VECTORS_SHA256",
    "S3PreregError",
    "analysis_plan_digest",
    "canonical_json",
    "determinism_subset_run_keys",
    "determinism_run_keys_sha256",
    "select_determinism_run_keys",
    "determinism_quota_map",
    "validate_determinism_run_keys",
    "S3_DETERMINISM_QUOTA_A_BUDGET_COUNTS",
    "S3_DETERMINISM_QUOTA_B_BUDGET_COUNTS",
    "S3_DETERMINISM_BUDGET_COUNTS",
    "S3_DETERMINISM_EVALS_PER_ROUND",
    "expected_determinism_section",
    "canonical_json_bytes",
    "canonical_sha256",
    "code_sha_for_files",
    "code_sha_from_files",
    "compute_analysis_code_sha",
    "compute_code_sha",
    "episode_digest",
    "history_digest",
    "package_sha256",
    "prereg_digest",
    "record_digest",
    "sha256_bytes",
    "sha256_file",
    "sha256_text",
    "task_fingerprint",
    "task_ids_sha256",
    "S3_PREREG_ID_PREFIX",
    "S3_PREREG_RELPATH",
    "S3_EVIDENCE_ROOT_RELPATH",
    "S3_FAMILY_PACKAGE_RELPATH",
    "S3_REFERENCES_SEALED_RELPATH",
    "S3_CALIBRATION_RELPATH",
    "S3_GATE_RELPATH",
    "S3_MODELS_DIR_RELPATH",
    "S3_MODEL_MANIFEST_RELPATH",
    "S3_W8_PILOT_GATE_SCHEMA_VERSION",
    "S3_W8_PILOT_GATE_RELPATH",
    "S3_W8_PILOT_TASKS",
    "S3_W8_PILOT_BUDGET",
    "S3_W8_PILOT_OPT_SEED",
    "S3_W8_PILOT_META_SEED",
    "S3_W8_PILOT_RUNS_PER_CAMPAIGN",
    "S3_W8_PILOT_TOTAL_RUNS",
    "S3_W8_PILOT_EVALS_PER_CAMPAIGN",
    "S3_W8_PILOT_TOTAL_EVALS",
    "S3_W8_PILOT_WORKERS",
    "S3_FD_GATE_SCHEMA_VERSION",
    "S3_FD_GATE_MODEL_KEYS",
    "S3_FD_GATE_NEGATIVE_KEYS",
    "S3_FD_GATE_COORDINATES_PER_MODEL",
    "S3_FD_EPSILON_RULE",
    "S3_FAMILY_PACKAGE_SCHEMA_VERSION",
    "S3_REFERENCES_SEALED_SCHEMA_VERSION",
    "S3_CALIBRATION_SCHEMA_VERSION",
    "S3_EPISODE_BANK_SCHEMA_VERSION",
    "S3_MODEL_FILE_SCHEMA_VERSION",
    "S3_FAMILY_ID",
    "S3_FORMULA_VERSION",
    "S3_FAMILY_SEED",
    "S3_HOLDOUT_SEED",
    "S3_DESIGN_DIM",
    "S3_DESIGN_LOWER",
    "S3_DESIGN_UPPER",
    "S3_SUPPORT_POOL_SIZE",
    "S3_QUERY_SIZE",
    "S3_DELTA1_CANDIDATES",
    "S3_DELTA1_CANDIDATES_EXTENDED",
    "S3_PACKAGE_VERSION",
    "S3_TASK_FINGERPRINT_ALGORITHM",
    "S3_TASK_FINGERPRINT_PARAM_KEYS",
    "S3_REFERENCE_COUNT",
    "S3_REQUIRED_META_TEST_TASKS",
    "S3_MODEL_META_SEEDS",
    "S3_MODEL_KINDS",
    "S3_EPISODE_BANK_EPISODES_PER_BANK",
    "S3_EPISODE_BANK_UNIQUE",
    "S3_MODEL_EPISODE_PAIRS",
    "S3_MODEL_CONFIG_FIELDS",
    "S3_MODEL_CONFIG_TEMPLATE",
    "S3_PREREG_REQUIRED_FIELDS",
    "S3_OPT_SEEDS",
    "S3_EVAL_TASKS",
    "S3_EVAL_SPLIT",
    "S3_MAIN_RUNS",
    "S3_MAIN_EVALS",
    "S3_NEGATIVE_CONTROL_TASKS",
    "S3_NEGATIVE_CONTROL_RUNS",
    "S3_NEGATIVE_CONTROL_EVALS",
    "S3_OOD_TASKS",
    "S3_OOD_RUNS",
    "S3_OOD_EVALS",
    "S3_DETERMINISM_SUBSET_RUNS",
    "S3_DETERMINISM_SHARD_COUNT",
    "S3_DETERMINISM_REPEATS",
    "S3_DETERMINISM_RUNS",
    "S3_DETERMINISM_EVALS",
    "S3_TOTAL_RUNS",
    "S3_TOTAL_EVALS",
    "S3_RS3_02_FALLBACK",
    "S3_DETERMINISM_EXCLUDED_FIELDS",
    "S3_DATA_BOUNDARY",
    "S3_ENDPOINTS",
    "S3_STATISTICS",
    "S3_FIGURES",
    "S3_NEGATIVE_CONTROLS",
    "S3_CAMPAIGN",
    "S3_OOD",
    "S3_DETERMINISM",
    "S3_PREREG_BUDGETS",
    "S3_SHARED_CANDIDATE_POOL_SIZE",
    "S3_BO_CANDIDATE_COUNT",
    "S3_RNG_CONTRACT",
    "S3_ARM_SPECS",
    "S3_AUTHORIZATION_CHAIN",
    "S3_PLACEHOLDER_PATTERNS",
    "S3_PREREG_ARTIFACT_INVALID",
    "S3_PREREG_AUTHORIZATION_MISMATCH",
    "S3_EPISODE_BANK_PATH_TEMPLATE",
    "S3_MODEL_PATH_TEMPLATE",
    "default_episode_bank_files",
    "default_models",
    "reject_placeholders",
    "resolve_evidence_path",
    "normalize_family_package",
    "normalize_references_sealed",
    "normalize_calibration",
    "normalize_episode_bank",
    "normalize_models",
    "build_preregistration",
    "verify_preregistration",
    "write_preregistration",
    "read_preregistration",
]

# ===========================================================================
# 预注册（prereg）常量、默认结构与冻结产物绑定（计划 v1.2b §6 / §6.1）
# ===========================================================================
# 本段只做纯 JSON/文件哈希与结构校验：不读取任何 holdout 数据行
# （meta_test/meta_test_ood/meta_test_negative_control 的 support/query/truth），
# 不启动求解器、不访问网络；physical_call_count 恒为 0。
# 所有证据文件路径均为相对仓库根路径，且必须位于
# research/concorde_metaopt/evidence/s3/ 之下（fail-closed）。

S3_PREREG_ID_PREFIX = "p4ra-s3-prereg-"
S3_PREREG_RELPATH = "research/concorde_metaopt/evidence/s3/s3_preregistration.json"
S3_EVIDENCE_ROOT_RELPATH = "research/concorde_metaopt/evidence/s3"
S3_FAMILY_PACKAGE_RELPATH = (
    S3_EVIDENCE_ROOT_RELPATH + "/family_package/p4ra_fqec_v1_family_package.json"
)
S3_REFERENCES_SEALED_RELPATH = (
    S3_EVIDENCE_ROOT_RELPATH + "/references_sealed/p4ra_fqec_v1_references_sealed.json"
)
S3_CALIBRATION_RELPATH = (
    S3_EVIDENCE_ROOT_RELPATH + "/calibration/family_calibration_m1.json"
)
S3_GATE_RELPATH = S3_EVIDENCE_ROOT_RELPATH + "/gate/fd_or_gradient_gate.json"
S3_MODELS_DIR_RELPATH = S3_EVIDENCE_ROOT_RELPATH + "/models"
S3_MODEL_MANIFEST_RELPATH = S3_MODELS_DIR_RELPATH + "/model_manifest.json"

# --- M2 W=8 试点门（run 级并行确定性；Lead m07341 item4 / m07491 item5） ------
S3_W8_PILOT_GATE_SCHEMA_VERSION = "p4ra-s3-w8-pilot-gate-v1"
S3_W8_PILOT_GATE_RELPATH = S3_EVIDENCE_ROOT_RELPATH + "/gate/w8_pilot_gate.json"
S3_W8_PILOT_TASKS = 3
S3_W8_PILOT_BUDGET = 128
S3_W8_PILOT_OPT_SEED = 0
S3_W8_PILOT_META_SEED = 0
S3_W8_PILOT_RUNS_PER_CAMPAIGN = 15
S3_W8_PILOT_TOTAL_RUNS = 30
S3_W8_PILOT_EVALS_PER_CAMPAIGN = 1920
S3_W8_PILOT_TOTAL_EVALS = 3840
S3_W8_PILOT_WORKERS = (1, 8)

# R-S3-07（Lead m07285 Q2/Q4）：M2 冻结的 FD/梯度门是唯一正式门产物，
# 正式 run 只读该文件、不重新生成；schema/每模型坐标数/负控结果均固定。
S3_FD_GATE_SCHEMA_VERSION = "p4ra-s3-fd-gate-v1"
S3_FD_GATE_MODEL_KEYS = ("fomaml_meta_0", "anil_meta_0")
S3_FD_GATE_NEGATIVE_KEYS = ("tamper", "anil_body_frozen", "k0_equivalence")
S3_FD_GATE_COORDINATES_PER_MODEL = S3_FD_MAX_COORDINATES
S3_FD_EPSILON_RULE = "1e-6*max(1,|theta|)"

# 与 task_family.py 中族包/参考封存件 schema 的单源对齐（测试断言相等）。
S3_FAMILY_PACKAGE_SCHEMA_VERSION = "p4ra-s3-family-package-v1"
S3_REFERENCES_SEALED_SCHEMA_VERSION = "p4ra-s3-references-sealed-v1"
S3_CALIBRATION_SCHEMA_VERSION = "p4ra-s3-family-calibration-v1"
S3_EPISODE_BANK_SCHEMA_VERSION = "p4ra-s3-episode-bank-v1"
S3_MODEL_FILE_SCHEMA_VERSION = "p4ra-s3-model-v1"

S3_FAMILY_ID = "F-QE-conflict-v1"
S3_FORMULA_VERSION = "polyhedral-v1"
S3_FAMILY_SEED = 20261107
S3_HOLDOUT_SEED = 20261108
S3_DESIGN_DIM = 12
S3_DESIGN_LOWER = 0.02
S3_DESIGN_UPPER = 0.98
S3_SUPPORT_POOL_SIZE = 128
S3_QUERY_SIZE = 64
S3_DELTA1_CANDIDATES = (0.20, 0.22, 0.25)
S3_DELTA1_CANDIDATES_EXTENDED = (0.18, 0.28, 0.30)
S3_PACKAGE_VERSION = "p4ra-fqec-v1-package-v1"
S3_TASK_FINGERPRINT_ALGORITHM = (
    'sha256(canonical_json({family_id, formula_version, task_id, seed, params}))[:16]'
)
S3_TASK_FINGERPRINT_PARAM_KEYS = (
    "a",
    "c",
    "b1",
    "b2",
    "delta1",
    "delta2",
    "m2",
)
S3_REFERENCE_COUNT = 110
S3_REQUIRED_META_TEST_TASKS = 20
S3_MODEL_META_SEEDS = (0, 1, 2)
S3_MODEL_KINDS = ("fomaml", "anil")
S3_EPISODE_BANK_EPISODES_PER_BANK = 1600
S3_EPISODE_BANK_UNIQUE = 4800
S3_MODEL_EPISODE_PAIRS = 9600
S3_MODEL_CONFIG_FIELDS = (
    "input_dim",
    "output_dim",
    "hidden_sizes",
    "inner_lr",
    "inner_steps",
    "outer_lr",
    "tasks_per_batch",
    "first_order",
    "seed",
    "backend",
    "head_only",
)
S3_MODEL_CONFIG_TEMPLATE = {
    "input_dim": 12,
    "output_dim": 3,
    "hidden_sizes": (64, 64),
    "inner_lr": 0.01,
    "inner_steps": 5,
    "outer_lr": 0.001,
    "tasks_per_batch": 8,
    "first_order": True,
    "backend": "torch",
}

# 顶层 23 必填字段（计划 §6；A6 分析器同口径；v1.3b 新增 fd_gate_sha256）。顺序即文档顺序。
S3_PREREG_REQUIRED_FIELDS = (
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
    "fd_gate_sha256",
    "resource_limits",
    "analysis_plan_digest",
    "code_sha",
    "physical_call_count",
    "data_boundary",
    "authorization_chain",
)

S3_OPT_SEEDS = tuple(range(5))
S3_EVAL_TASKS = 20
S3_EVAL_SPLIT = "meta_test"
S3_MAIN_RUNS = 3000
S3_MAIN_EVALS = 288000
S3_NEGATIVE_CONTROL_TASKS = 10
S3_NEGATIVE_CONTROL_RUNS = 300
S3_NEGATIVE_CONTROL_EVALS = 28800
S3_OOD_TASKS = 10
S3_OOD_RUNS = 300
S3_OOD_EVALS = 28800
S3_DETERMINISM_SUBSET_RUNS = 60
S3_DETERMINISM_REPEATS = 3
S3_DETERMINISM_RUNS = 180
S3_DETERMINISM_EVALS = 17280
S3_TOTAL_RUNS = 3780
S3_TOTAL_EVALS = 362880
S3_DETERMINISM_SHARD_COUNT = 8
S3_DETERMINISM_QUOTA_A_BUDGET_COUNTS = {"64": 20, "128": 20}
S3_DETERMINISM_QUOTA_B_BUDGET_COUNTS = {"64": 10, "128": 10}
S3_DETERMINISM_BUDGET_COUNTS = {"64": 30, "128": 30}
S3_DETERMINISM_EVALS_PER_ROUND = sum(
    int(budget) * int(count) for budget, count in S3_DETERMINISM_BUDGET_COUNTS.items()
)
S3_RS3_02_FALLBACK = {
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
S3_DETERMINISM_EXCLUDED_FIELDS = ("wall_s", "peak_memory_mb")

S3_DATA_BOUNDARY = {
    "flags": {
        "holdout_truth_used_for_training": False,
        "holdout_truth_used_for_adaptation": False,
        "support_truth_read": "EVAL/OOD/NEGATIVE_CONTROL",
        "holdout_truth_used_for_bo_ranking": False,
        "holdout_truth_read_for_evaluation": True,
    },
    "allowed_splits": list(S3_ALLOWED_SPLITS),
    "training_splits": list(S3_TRAIN_SPLITS),
    "dev_splits": list(S3_DEV_SPLITS),
    "holdout_splits": list(S3_HOLDOUT_SPLITS),
    "dev_note": "dev 保留 0 任务；SMOKE/DEV 训练使用 meta_validation 前 4 task（计划 §4.5）",
    "phase_policy": "TRAIN/DEV 禁读 holdout truth；support truth 仅 EVAL/OOD/NEGATIVE_CONTROL；query truth 仅端点计算读取一次",
}

S3_ENDPOINTS = {
    "C1": {
        "family_id": "s3-feasible-hit-2tests",
        "comparator": "S3-BO-FOMAML-OBJ",
        "treatment": "S3-BO-FOMAML-CON",
        "endpoint": "feasible_hit_rate",
        "tests": ["B128", "B64"],
        "direction": "higher_is_better",
        "threshold_benefit": 0.02,
        "threshold_harm": -0.02,
        "inference": "exact_wilcoxon_two_sided_holm",
    },
    "C2": {
        "family_id": "s3-gap-to-ref-2tests",
        "comparator": "S3-BO-FOMAML-OBJ",
        "treatment": "S3-BO-FOMAML-CON",
        "endpoint": "gap_to_reference",
        "tests": ["B128", "B64"],
        "direction": "lower_is_better",
        "relative": True,
        "threshold_benefit": -0.01,
        "threshold_harm": 0.01,
        "denominator_floor": 1e-6,
        "inference": "exact_wilcoxon_two_sided_holm",
    },
}

S3_STATISTICS = {
    "method": "exact_sign_flip_tie_aware",
    "zero_policy": "DISCARDED",
    "min_n_eff": 15,
    "holm": {"alpha": 0.05, "family_size": 2},
    "bootstrap": {"resamples": 10000, "seed": 20261107, "confidence": 0.95},
    "sensitivity": {
        "pratt": True,
        "permutation": {"resamples": 10000, "seed": 20261107},
    },
    "decision_rules": {
        "endpoint_level": [
            "INCONCLUSIVE: n_eff<15 或不可计算",
            "SUPPORTED_BENEFIT: p<0.05 且效应>=获益阈值",
            "SUPPORTED_HARM: p<0.05 且效应<=-损害阈值",
            "NEGLIGIBLE_SIGNIFICANT: p<0.05 且 |效应|<阈值",
            "DIRECTION_INCONSISTENT: p>=0.05 且效应<=-阈值",
            "NULL: 其余",
        ],
        "overall_priority": [
            "INCONCLUSIVE",
            "HARM",
            "DIRECTION_INCONSISTENT",
            "BENEFIT",
            "NO_EVIDENCE",
        ],
    },
    "anil_decision_rules": [
        "ANIL_COST_EFFICIENT: feasible_hit_rate >= RANDOM-0.02 且成本<=FOMAML-CON 的 75%",
        "ANIL_INFERIOR: 描述性 CI 上界 < -0.02（相对 RANDOM）",
        "ANIL_INCONCLUSIVE: 其余",
    ],
}

S3_FIGURES = {
    "fig1_training_loss_and_full_meta_grad": {
        "title": "训练 loss 与全元目标梯度 FD 门",
        "data_source": "model_manifest、fd_or_gradient_gate.json",
    },
    "fig2_kshot_rmse_k0_k1_k3_k5": {
        "title": "K-shot 后 query RMSE（f/g1/g2）",
        "data_source": "K-sweep 诊断（M1，DEVELOPMENT_VALIDATION_ONLY）",
    },
    "fig3_feasible_hit_rate_by_arm": {
        "title": "五臂 feasible_hit_rate 分布",
        "data_source": "aggregate/per-task CSV",
    },
    "fig4_best_feasible_and_first_feasible": {
        "title": "best_feasible_value / gap / first_feasible 分布",
        "data_source": "per-task CSV",
    },
    "fig5_fomaml_vs_full_vs_anil_cost": {
        "title": "FOMAML/FullMAML/ANIL 成本-性能",
        "data_source": "S2 归档 aggregate + S3 cost CSV",
    },
    "fig6_task_family_diagnostics": {
        "title": "任务族几何诊断",
        "data_source": "family package 只读字段 + calibration",
    },
    "fig7_ood_diagnostics": {
        "title": "OOD 段与 ID 段描述性对比",
        "data_source": "OOD records",
    },
    "fig8_negative_controls": {
        "title": "负控制置换前后对比",
        "data_source": "negative_control summary",
    },
    "fig9_determinism_and_budget": {
        "title": "确定性一致性与预算记账",
        "data_source": "determinism + run_summary",
    },
    "fig10_vspaero_gate_status": {
        "title": "VSPAERO 门禁状态（只读）",
        "data_source": "S2/D-12D 归档门禁 JSON（只读）",
    },
}

S3_NEGATIVE_CONTROLS = {
    "tasks": 10,
    "task_count": 10,
    "source_split": "meta_test",
    "split": "meta_test_negative_control",
    "label_shuffle_seed_algorithm": (
        'sha256(f"{FAMILY_SEED}|{task_id}|label-shuffle")[:8] % (2**31)'
    ),
    "seed_formula": 'sha256(f"{FAMILY_SEED}|{task_id}|label-shuffle")[:8] % (2**31)',
    "permutation": "query 标签行 3 维整体置换（不改几何/support/参考解）",
    "shuffled_dimensions": 3,
    "reference_kind": "LABEL_SHUFFLED_NO_REFERENCE",
    "runs": 300,
    "evaluation_mode": "descriptive_only",
    "suspicious_rule": "打乱后 CON-OBJ 差异 >= 真实差异的 50% -> NEGATIVE_CONTROL_SUSPICIOUS",
}

S3_CAMPAIGN = {
    "authorization": "每次 FORMAL campaign 执行（一次 run_experiment 调用/一个输出目录，覆盖该 campaign 内全部 task 的预注册 runs）由 Lead 一次性书面授权，run 级记录该授权",
    "rules": {
        "required_record_fields": ["campaign_authorization_id", "campaign_authorization_utc"],
        "single_evaluation_campaign_per_task": True,
    },
    "authorization_rule": "每次 FORMAL campaign 执行前一次性书面授权，写 campaign_authorization_id 与 campaign_authorization_utc",
    "required_record_fields": ["campaign_authorization_id", "campaign_authorization_utc"],
    "runner_assert": True,
    "holdout_phase": "EVAL",
    "single_evaluation_campaign_per_task": True,
}

S3_OOD = {
    "tasks": 10,
    "task_count": 10,
    "split": "meta_test_ood",
    "delta1_shift": 0.05,
    "delta1_offset": 0.05,
    "b1_perturb_scale": 0.30,
    "b1_perturbation": 0.30,
    "direction_seed_scope": "ood-direction",
    "direction_seed_algorithm": "derive_seed(HOLDOUT_SEED, 'ood-direction', task_index)",
    "runs": 300,
    "evaluation_mode": "descriptive_only",
}

S3_DETERMINISM = {
    "subset_runs": S3_DETERMINISM_SUBSET_RUNS,
    "repeats": S3_DETERMINISM_REPEATS,
    "reruns": S3_DETERMINISM_REPEATS,
    "total_runs": S3_DETERMINISM_RUNS,
    "shard_count": S3_DETERMINISM_SHARD_COUNT,
    "subset_rule": (
        "计划 v1.3c §4.2：(a) 每臂 8 shard 按 sha256(arm_id|shard|det-budget) 升序，前 4 shard 强制 B=64、后 4 强制 B=128；"
        "每个 (arm, shard, budget) 桶在未选 run 中按 canonical run_key 的 sha256 升序取第一个，桶空 fail-closed；5 臂共 40 个（20 B64 + 20 B128）；"
        "(b) 每臂每 budget 共 10 组，在去除已选 run 后按同一 sha256 升序取前 2 个，共 20 个（10 B64 + 10 B128，重复则顺延）；"
        "(a)+(b)=60 个唯一 run（30 B64 + 30 B128，每轮 5,760 evals）；固定按 (arm, task_id, budget, opt_seed, meta_seed, phase, split) 排序"
    ),
    "subset_budget_counts": {"64": 30, "128": 30},
    "subset_quota_a_budget_counts": {"64": 20, "128": 20},
    "subset_quota_b_budget_counts": {"64": 10, "128": 10},
    "subset_evals_per_round": S3_DETERMINISM_EVALS_PER_ROUND,
    "subset_run_keys_sha256": "",
    "grids_required_equal": True,
    "record_digest_excluded_fields": list(S3_DETERMINISM_EXCLUDED_FIELDS),
    "byte_identical_artifacts": [
        "run_config",
        "episode_bank_sha256",
        "model_sha256",
        "fd_or_gradient_gate_sha256",
        "record_core",
    ],
}

S3_PREREG_BUDGETS = {
    "budgets": list(S3_BUDGETS),
    "k_shot": S3_K_SHOT,
    "initial_designs": S3_INITIAL_DESIGN_COUNT,
    "bo_initial_designs": S3_BO_INITIAL_DESIGN_COUNT,
    "opt_seeds": list(S3_OPT_SEEDS),
    "meta_seeds": list(S3_MODEL_META_SEEDS),
    "eval_tasks": S3_EVAL_TASKS,
    "eval_split": S3_EVAL_SPLIT,
    "main_runs": S3_MAIN_RUNS,
    "main_evals": S3_MAIN_EVALS,
    "negative_control_tasks": S3_NEGATIVE_CONTROL_TASKS,
    "negative_control_runs": S3_NEGATIVE_CONTROL_RUNS,
    "negative_control_evals": S3_NEGATIVE_CONTROL_EVALS,
    "ood_tasks": S3_OOD_TASKS,
    "ood_runs": S3_OOD_RUNS,
    "ood_evals": S3_OOD_EVALS,
    "determinism_subset_runs": S3_DETERMINISM_SUBSET_RUNS,
    "determinism_repeats": S3_DETERMINISM_REPEATS,
    "determinism_runs": S3_DETERMINISM_RUNS,
    "determinism_evals": S3_DETERMINISM_EVALS,
    "total_runs": S3_TOTAL_RUNS,
    "total_evals": S3_TOTAL_EVALS,
    "rs3_02_fallback": dict(S3_RS3_02_FALLBACK),
}

def _determinism_run_key(
    *,
    arm: str,
    task_id: str,
    budget: int,
    opt_seed: int,
    meta_seed: int,
) -> dict[str, Any]:
    """确定性 run_key 形状（与 s3_runner.canonical_run_key 逐字段一致）。"""
    return {
        "arm": str(arm),
        "budget": int(budget),
        "meta_seed": int(meta_seed),
        "opt_seed": int(opt_seed),
        "phase": "EVAL",
        "split": S3_EVAL_SPLIT,
        "task_id": str(task_id),
    }


def _determinism_run_shard(run_key: Mapping[str, Any], *, shard_count: int) -> int:
    return int(sha256_text(canonical_json(run_key))[:8], 16) % int(shard_count)


def _determinism_sort_key(run_key: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(run_key["arm"]),
        str(run_key["task_id"]),
        int(run_key["budget"]),
        int(run_key["opt_seed"]),
        int(run_key["meta_seed"]),
        str(run_key["phase"]),
        str(run_key["split"]),
    )


def determinism_quota_map(
    arms: Sequence[str],
    *,
    shard_count: int = S3_DETERMINISM_SHARD_COUNT,
) -> dict[tuple[str, int], int]:
    """计划 v1.3c：每臂 shard 按 sha256(arm|shard|det-budget) 升序，前半强制 B=64、后半强制 B=128。"""
    shards = int(shard_count)
    budgets = [int(value) for value in S3_BUDGETS]
    _require(shards > 0 and shards % 2 == 0, S3_PREREG_SCHEMA_INVALID, "shard_count 必须为正偶数")
    _require(len(budgets) >= 2, S3_PREREG_SCHEMA_INVALID, "S3_BUDGETS 至少两档")
    half = shards // 2
    quota: dict[tuple[str, int], int] = {}
    for arm in sorted({str(item) for item in arms}):
        ranked = sorted(
            range(shards),
            key=lambda shard: (
                sha256_text(str(arm) + "|" + str(shard) + "|det-budget"),
                int(shard),
            ),
        )
        for position, shard in enumerate(ranked):
            quota[(str(arm), int(shard))] = budgets[0] if position < half else budgets[1]
    return quota


def validate_determinism_run_keys(
    rows: Sequence[Mapping[str, Any]],
    *,
    shard_count: int = S3_DETERMINISM_SHARD_COUNT,
) -> list[dict[str, Any]]:
    """校验 60-run 配额规则：规模/唯一/budget 分布/(arm,shard) 覆盖/(arm,budget) 配额/每轮 evals。"""
    shards = int(shard_count)
    _require(
        shards == int(S3_DETERMINISM_SHARD_COUNT),
        S3_PREREG_SCHEMA_INVALID,
        "确定性子集 shard_count 必须等于 " + str(S3_DETERMINISM_SHARD_COUNT),
    )
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        try:
            item = {
                "arm": str(raw["arm"]),
                "budget": int(raw["budget"]),
                "meta_seed": int(raw["meta_seed"]),
                "opt_seed": int(raw["opt_seed"]),
                "phase": str(raw["phase"]),
                "split": str(raw["split"]),
                "task_id": str(raw["task_id"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise S3PreregError(
                S3_PREREG_SCHEMA_INVALID,
                "确定性子集 run_key 字段非法: " + str(exc),
            ) from exc
        normalized.append(item)
    _require(
        len(normalized) == int(S3_DETERMINISM_SUBSET_RUNS),
        S3_PREREG_SCHEMA_INVALID,
        "确定性子集大小必须为 " + str(S3_DETERMINISM_SUBSET_RUNS),
    )
    texts = [canonical_json(item) for item in normalized]
    _require(len(set(texts)) == len(texts), S3_PREREG_SCHEMA_INVALID, "确定性子集 run 不唯一")
    budget_counts: dict[int, int] = {}
    for item in normalized:
        budget_counts[item["budget"]] = budget_counts.get(item["budget"], 0) + 1
    expected_counts = {
        int(budget): int(count) for budget, count in S3_DETERMINISM_BUDGET_COUNTS.items()
    }
    _require(
        budget_counts == expected_counts,
        S3_PREREG_SCHEMA_INVALID,
        "确定性子集 budget 配额不符: " + repr(budget_counts),
    )
    evals = sum(item["budget"] for item in normalized)
    _require(
        evals == int(S3_DETERMINISM_EVALS_PER_ROUND),
        S3_PREREG_SCHEMA_INVALID,
        "确定性每轮 evals 不符: " + str(evals),
    )
    arms = sorted({item["arm"] for item in normalized})
    _require(
        len(arms) * shards <= len(normalized),
        S3_PREREG_SCHEMA_INVALID,
        "确定性子集 arm 数非法",
    )
    quota = determinism_quota_map(arms, shard_count=shards)
    quota_a_counts = {int(budget): 0 for budget in S3_BUDGETS}
    for arm in arms:
        for shard in range(shards):
            budget = int(quota[(arm, shard)])
            covered = [
                item
                for item in normalized
                if item["arm"] == arm
                and int(item["budget"]) == budget
                and _determinism_run_shard(item, shard_count=shards) == shard
            ]
            _require(
                len(covered) >= 1,
                S3_PREREG_SCHEMA_INVALID,
                "确定性子集 (arm, shard) 配额桶空: " + arm + "/" + str(shard),
            )
            quota_a_counts[budget] += 1
    expected_a = {
        int(budget): int(count)
        for budget, count in S3_DETERMINISM_QUOTA_A_BUDGET_COUNTS.items()
    }
    _require(
        quota_a_counts == expected_a,
        S3_PREREG_SCHEMA_INVALID,
        "确定性配额 (a) budget 分布不符: " + repr(quota_a_counts),
    )
    expected_per_arm_budget = shards // 2 + 2
    for arm in arms:
        for budget in S3_BUDGETS:
            total = sum(
                1
                for item in normalized
                if item["arm"] == arm and item["budget"] == int(budget)
            )
            _require(
                total == expected_per_arm_budget,
                S3_PREREG_SCHEMA_INVALID,
                "确定性 (arm, budget) 配额不符: " + arm + "/" + str(budget) + "=" + str(total),
            )
    return sorted(normalized, key=_determinism_sort_key)


def select_determinism_run_keys(
    run_keys: Sequence[Mapping[str, Any]],
    *,
    shard_count: int = S3_DETERMINISM_SHARD_COUNT,
) -> list[dict[str, Any]]:
    """按计划 v1.3c 选 60-run 确定性子集：40 个 (arm, shard, 配额 budget) + 每 (arm, budget) 补 2。"""
    shards = int(shard_count)
    _require(shards > 0, S3_PREREG_SCHEMA_INVALID, "shard_count 必须为正")
    unique: dict[str, dict[str, Any]] = {}
    for raw in run_keys:
        try:
            key = {
                "arm": str(raw["arm"]),
                "budget": int(raw["budget"]),
                "meta_seed": int(raw["meta_seed"]),
                "opt_seed": int(raw["opt_seed"]),
                "phase": str(raw["phase"]),
                "split": str(raw["split"]),
                "task_id": str(raw["task_id"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise S3PreregError(
                S3_PREREG_SCHEMA_INVALID,
                "确定性子集输入 run_key 字段非法: " + str(exc),
            ) from exc
        unique[canonical_json(key)] = key
    keys = [unique[item] for item in sorted(unique)]
    _require(len(keys) > 0, S3_PREREG_SCHEMA_INVALID, "确定性子集输入 run_key 为空")
    digest_by_text = {
        canonical_json(key): sha256_text(canonical_json(key)) for key in keys
    }
    digest_order = sorted(
        keys,
        key=lambda key: (digest_by_text[canonical_json(key)], canonical_json(key)),
    )
    arms = sorted({key["arm"] for key in keys})
    quota = determinism_quota_map(arms, shard_count=shards)
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    quota_a_counts = {int(budget): 0 for budget in S3_BUDGETS}
    for arm in arms:
        for shard in range(shards):
            budget = int(quota[(arm, shard)])
            bucket = [
                key
                for key in digest_order
                if key["arm"] == arm
                and int(key["budget"]) == budget
                and _determinism_run_shard(key, shard_count=shards) == shard
                and canonical_json(key) not in used
            ]
            _require(
                bool(bucket),
                S3_PREREG_SCHEMA_INVALID,
                "确定性子集桶空: " + arm + " shard=" + str(shard) + " budget=" + str(budget),
            )
            pick = bucket[0]
            selected.append(pick)
            used.add(canonical_json(pick))
            quota_a_counts[budget] += 1
    expected_a = {
        int(budget): int(count)
        for budget, count in S3_DETERMINISM_QUOTA_A_BUDGET_COUNTS.items()
    }
    _require(
        quota_a_counts == expected_a,
        S3_PREREG_SCHEMA_INVALID,
        "确定性配额 (a) 不足: " + repr(quota_a_counts),
    )
    for arm in arms:
        for budget in S3_BUDGETS:
            extras: list[dict[str, Any]] = []
            for key in digest_order:
                text = canonical_json(key)
                if text in used or key["arm"] != arm or int(key["budget"]) != int(budget):
                    continue
                extras.append(key)
                used.add(text)
                if len(extras) == 2:
                    break
            _require(
                len(extras) == 2,
                S3_PREREG_SCHEMA_INVALID,
                "确定性子集补点不足: " + arm + " budget=" + str(budget),
            )
            selected.extend(extras)
    return validate_determinism_run_keys(selected, shard_count=shards)


def determinism_run_keys_sha256(run_keys: Sequence[Mapping[str, Any]]) -> str:
    return sha256_text(canonical_json([dict(key) for key in run_keys]))


def determinism_subset_run_keys(
    family: Mapping[str, Any],
    *,
    shard_count: int = S3_DETERMINISM_SHARD_COUNT,
) -> list[dict[str, Any]]:
    """从族包 meta_test 20 任务 + 主网格预算构造 run_key 全集并选确定性子集。"""
    fingerprints = family.get("task_fingerprints") or []
    task_ids = sorted(str(item["task_id"]) for item in fingerprints)
    _require(len(task_ids) == int(S3_EVAL_TASKS), S3_PREREG_SCHEMA_INVALID, "确定性子集需要 20 个 meta_test 任务")
    grid = [
        _determinism_run_key(arm=arm, task_id=task_id, budget=budget, opt_seed=opt_seed, meta_seed=meta_seed)
        for arm in S3_ARMS
        for budget in S3_BUDGETS
        for opt_seed in S3_OPT_SEEDS
        for meta_seed in S3_MODEL_META_SEEDS
        for task_id in task_ids
    ]
    _require(len(grid) == int(S3_MAIN_RUNS), S3_PREREG_SCHEMA_INVALID, "确定性子集主网格 run 数不符")
    return select_determinism_run_keys(grid, shard_count=shard_count)


def expected_determinism_section(family: Mapping[str, Any]) -> dict[str, Any]:
    section = _deep_copy_json(S3_DETERMINISM)
    keys = determinism_subset_run_keys(family)
    section["subset_run_keys_sha256"] = determinism_run_keys_sha256(keys)
    return section


S3_SHARED_CANDIDATE_POOL_SIZE = 123
S3_BO_CANDIDATE_COUNT = 512
S3_RNG_CONTRACT = {
    "bo_engine_seed_algorithm": (
        'int.from_bytes(sha256(f"{task_id}|{opt_seed}|{meta_seed}|s3-bo-engine")'
        ".digest()[:8], 'big') % (2**31)"
    ),
    "de_seed_algorithm": (
        'int.from_bytes(sha256(f"{task_id}|{opt_seed}|{meta_seed}|s3-de")'
        ".digest()[:8], 'big') % (2**31)"
    ),
    "seed_excludes_arm_and_budget": True,
    "shared_candidate_pool_size": S3_SHARED_CANDIDATE_POOL_SIZE,
    "shared_candidate_pool_rule": "support_pool(128 点) 去掉该 task 的 5 个 K-shot support 设计 = 123 点",
    "shared_initial_designs_scope": "shared-init",
    "shared_initial_designs_count": S3_INITIAL_DESIGN_COUNT,
    "bo_candidate_count": S3_BO_CANDIDATE_COUNT,
    "shared_engine_fields_required_equal": [
        "engine_seed",
        "candidate_pool_sha256",
        "candidate_count",
        "bo_config_sha256",
    ],
    "bo_engine_draws_sha256_required_equal": True,
    "bo_trace_first_divergence_index_required": True,
}
S3_ARM_SPECS = (
    {
        "id": "S3-BO-RANDOM",
        "engine_type": "bo",
        "surrogate": None,
        "score": "random",
        "head_only": False,
        "first_order": True,
        "selection": "shared_initial_index_order",
        "joint_score": False,
        "rng": {
            "engine_seed_scope": "s3-bo-engine",
            "exclude_arm_budget_from_seed": True,
        },
    },
    {
        "id": "S3-BO-FOMAML-OBJ",
        "engine_type": "bo",
        "surrogate": "fomaml",
        "score": "objective",
        "head_only": False,
        "first_order": True,
        "selection": "surrogate_score_asc_then_index",
        "joint_score": False,
        "rng": {
            "engine_seed_scope": "s3-bo-engine",
            "exclude_arm_budget_from_seed": True,
        },
    },
    {
        "id": "S3-BO-FOMAML-CON",
        "engine_type": "bo",
        "surrogate": "fomaml",
        "score": "joint",
        "head_only": False,
        "first_order": True,
        "selection": "surrogate_score_asc_then_index",
        "joint_score": True,
        "rng": {
            "engine_seed_scope": "s3-bo-engine",
            "exclude_arm_budget_from_seed": True,
        },
    },
    {
        "id": "S3-BO-ANIL-CON",
        "engine_type": "bo",
        "surrogate": "anil",
        "score": "joint",
        "head_only": True,
        "first_order": True,
        "selection": "surrogate_score_asc_then_index",
        "joint_score": True,
        "rng": {
            "engine_seed_scope": "s3-bo-engine",
            "exclude_arm_budget_from_seed": True,
        },
    },
    {
        "id": "S3-DE",
        "engine_type": "de",
        "surrogate": None,
        "score": "objective",
        "head_only": False,
        "first_order": True,
        "selection": "differential_evolution",
        "joint_score": False,
        "rng": {
            "engine_seed_scope": "s3-de",
            "exclude_arm_budget_from_seed": True,
        },
    },
)

S3_AUTHORIZATION_CHAIN = {
    "issue": "#7",
    "decision": "D-P4-003",
    "stage": "S3",
    "references": ["R-S3-01", "R-S3-02"],
    "gate_chain": ["M0", "M0R2", "M1", "M2", "M3"],
}

# 允许出现在文字字段中的占位符模式（拒绝 TBD/TODO/尖括号占位等）
S3_PLACEHOLDER_PATTERNS = (
    "TBD",
    "TODO",
    "PENDING",
    "PLACEHOLDER",
    "REPLACE_ME",
    "FIXME",
    "XXX",
)

# 额外错误码（预注册构建/校验）
S3_PREREG_ARTIFACT_INVALID = "S3_PREREG_ARTIFACT_INVALID"
S3_PREREG_AUTHORIZATION_MISMATCH = "S3_PREREG_AUTHORIZATION_MISMATCH"


def _require(condition: Any, code: str, message: str) -> None:
    if not condition:
        raise S3PreregError(code, message)


def _require_str(value: Any, code: str, label: str) -> str:
    _require(isinstance(value, str) and value.strip() != "", code, label + " 必须是非空字符串")
    return value


def _require_int(value: Any, code: str, label: str) -> int:
    _require(type(value) is int, code, label + " 必须是 int")
    return int(value)


def _require_hex64(value: Any, code: str, label: str) -> str:
    text = _require_str(value, code, label)
    _require(
        len(text) == 64 and all(ch in "0123456789abcdef" for ch in text),
        code,
        label + " 必须是 64 位小写 hex",
    )
    return text


def _require_mapping(value: Any, code: str, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), code, label + " 必须是 mapping")
    return value


def _require_exact_keys(
    value: Any,
    expected: Sequence[str],
    code: str,
    label: str,
    *,
    allow_extra: bool = False,
) -> Mapping[str, Any]:
    mapping = _require_mapping(value, code, label)
    actual = set(str(key) for key in mapping)
    expected_set = set(expected)
    missing = sorted(expected_set - actual)
    _require(not missing, code, label + " 缺少字段: " + ",".join(missing))
    if not allow_extra:
        extra = sorted(actual - expected_set)
        _require(not extra, code, label + " 含未知字段: " + ",".join(extra))
    return mapping


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _iter_strings(key)
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def reject_placeholders(value: Any, label: str = "prereg") -> None:
    """拒绝 TBD/TODO/尖括号占位等，避免冻结未定内容。"""
    for text in _iter_strings(value):
        stripped = text.strip()
        upper = stripped.upper()
        for pattern in S3_PLACEHOLDER_PATTERNS:
            if upper == pattern or upper.startswith(pattern + " ") or upper.startswith(pattern + ":"):
                raise S3PreregError(
                    S3_PREREG_PLACEHOLDER_REJECTED,
                    label + " 含占位符 " + pattern + ": " + stripped,
                )
        if len(stripped) >= 2 and stripped.startswith("<") and stripped.endswith(">"):
            raise S3PreregError(
                S3_PREREG_PLACEHOLDER_REJECTED,
                label + " 含尖括号占位符: " + stripped,
            )


def _repo_root_or_default(repo_root: str | Path | None) -> Path:
    if repo_root is None:
        return Path(__file__).resolve().parents[3]
    return Path(repo_root).resolve()


def resolve_evidence_path(repo_root: str | Path, relpath: str) -> Path:
    """把仓库相对路径解析为 evidence/s3 下的绝对路径（拒绝绝对路径/越界/缺失）。"""
    root = _repo_root_or_default(repo_root)
    text = _require_str(relpath, S3_PREREG_FILE_ERROR, "证据路径")
    candidate = Path(text)
    _require(
        not candidate.is_absolute(),
        S3_PREREG_FILE_ERROR,
        "证据路径必须是仓库相对路径（禁止绝对路径）: " + text,
    )
    _require(
        ".." not in candidate.parts,
        S3_PREREG_FILE_ERROR,
        "证据路径不得包含 '..': " + text,
    )
    evidence_root = (root / S3_EVIDENCE_ROOT_RELPATH).resolve()
    resolved = (root / candidate).resolve()
    _require(
        resolved == evidence_root or evidence_root in resolved.parents,
        S3_PREREG_FILE_ERROR,
        "证据路径必须位于 research/concorde_metaopt/evidence/s3 之下: " + text,
    )
    _require(resolved.is_file(), S3_PREREG_FILE_ERROR, "证据文件不存在: " + text)
    return resolved


def _read_json(relpath: str, repo_root: str | Path, label: str) -> tuple[Path, bytes, Any]:
    path = resolve_evidence_path(repo_root, relpath)
    data = path.read_bytes()
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S3PreregError(
            S3_PREREG_ARTIFACT_INVALID,
            label + " 不是合法 UTF-8 JSON: " + str(exc),
        ) from exc
    return path, data, payload


# ---------------------------------------------------------------------------
# 冻结证据产物读取与规范化（族包 / 封存参考 / 校准 / episode bank / 模型）
# ---------------------------------------------------------------------------
def _read_hash_vectors(repo_root: str | Path) -> dict[str, Any]:
    path = _repo_root_or_default(repo_root) / HASH_VECTORS_RELPATH
    _require(path.is_file(), S3_PREREG_FILE_ERROR, "hash_vectors.json 不存在: " + str(path))
    data = path.read_bytes()
    actual = sha256_bytes(data)
    if actual != HASH_VECTORS_SHA256:
        raise S3PreregError(
            S3_PREREG_HASH_VECTORS_MISMATCH,
            "hash_vectors.json 原始字节 sha 与固定值不一致: " + actual,
        )
    return {
        "path": HASH_VECTORS_RELPATH,
        "sha256": actual,
        "bytes": len(data),
    }


def normalize_family_package(relpath: str, repo_root: str | Path) -> dict[str, Any]:
    path, data, payload = _read_json(relpath, repo_root, "族冻结包")
    _require_mapping(payload, S3_PREREG_FAMILY_MISMATCH, "族冻结包")
    _require(
        payload.get("schema_version") == S3_FAMILY_PACKAGE_SCHEMA_VERSION,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 schema_version 不符: " + repr(payload.get("schema_version")),
    )
    _require(
        payload.get("family_id") == S3_FAMILY_ID,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 family_id 不符: " + repr(payload.get("family_id")),
    )
    _require(
        payload.get("formula_version") == S3_FORMULA_VERSION,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 formula_version 不符: " + repr(payload.get("formula_version")),
    )
    _require(
        payload.get("family_seed") == S3_FAMILY_SEED,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 family_seed 不符",
    )
    _require(
        payload.get("holdout_seed") == S3_HOLDOUT_SEED,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 holdout_seed 不符",
    )
    _require(
        payload.get("design_dim") == S3_DESIGN_DIM,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 design_dim 不符",
    )
    _require(
        list(payload.get("design_box") or []) == [S3_DESIGN_LOWER, S3_DESIGN_UPPER],
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 design_box 不符",
    )
    _require(
        payload.get("support_pool_size") == S3_SUPPORT_POOL_SIZE,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 support_pool_size 不符",
    )
    _require(
        payload.get("query_size") == S3_QUERY_SIZE,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 query_size 不符",
    )
    _require(
        payload.get("physical_call_count") == 0,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 physical_call_count 必须为 0",
    )
    split_counts = payload.get("split_counts")
    _require(
        isinstance(split_counts, Mapping)
        and dict(split_counts) == dict(S3_SPLIT_COUNTS),
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 split_counts 不符: " + repr(split_counts),
    )
    tasks = payload.get("tasks")
    _require(isinstance(tasks, list), S3_PREREG_FAMILY_MISMATCH, "族冻结包 tasks 必须是 list")
    _require(
        len(tasks) == sum(S3_SPLIT_COUNTS.values()),
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包任务数不符: " + str(len(tasks)),
    )
    seen_ids: set[str] = set()
    split_tasks: dict[str, list[Mapping[str, Any]]] = {split: [] for split in S3_SPLIT_COUNTS}
    for task in tasks:
        _require_mapping(task, S3_PREREG_FAMILY_MISMATCH, "族任务记录")
        task_id = _require_str(task.get("task_id"), S3_PREREG_FAMILY_MISMATCH, "task_id")
        _require(
            task_id not in seen_ids,
            S3_PREREG_FAMILY_MISMATCH,
            "族冻结包 task_id 重复: " + task_id,
        )
        seen_ids.add(task_id)
        split = _require_str(task.get("split"), S3_PREREG_FAMILY_MISMATCH, "split")
        _require(
            split in split_tasks,
            S3_PREREG_FAMILY_MISMATCH,
            "族冻结包未知 split: " + split,
        )
        _require(
            task.get("family") == S3_FAMILY_ID and task.get("formula_version") == S3_FORMULA_VERSION,
            S3_PREREG_FAMILY_MISMATCH,
            "族任务 family/formula_version 不符: " + task_id,
        )
        _require_int(task.get("seed"), S3_PREREG_FAMILY_MISMATCH, "task.seed")
        fingerprint_text = _require_str(
            task.get("task_fingerprint"),
            S3_PREREG_FAMILY_MISMATCH,
            "task.task_fingerprint",
        )
        _require(
            len(fingerprint_text) == 16
            and all(ch in "0123456789abcdef" for ch in fingerprint_text),
            S3_PREREG_FAMILY_MISMATCH,
            "task.task_fingerprint 必须是 16 位小写 hex: " + fingerprint_text,
        )
        split_tasks[split].append(task)
    for split, count in S3_SPLIT_COUNTS.items():
        _require(
            len(split_tasks[split]) == count,
            S3_PREREG_FAMILY_MISMATCH,
            "族冻结包 split 计数不符 " + split + ": " + str(len(split_tasks[split])),
        )
    splits_field = payload.get("splits")
    _require(
        isinstance(splits_field, Mapping),
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 splits 必须是 mapping",
    )
    for split in S3_SPLIT_COUNTS:
        expected_ids = sorted(str(task["task_id"]) for task in split_tasks[split])
        actual_ids = sorted(str(item) for item in (splits_field.get(split) or []))
        _require(
            actual_ids == expected_ids,
            S3_PREREG_FAMILY_MISMATCH,
            "族冻结包 splits[" + split + "] 与 tasks 不一致",
        )
    all_ids = sorted(seen_ids)
    computed_ids_sha = task_ids_sha256(all_ids)
    _require(
        payload.get("task_ids_sha256") == computed_ids_sha,
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 task_ids_sha256 复算不一致",
    )
    base = payload.get("delta1_base")
    _require(
        isinstance(base, (int, float)) and not isinstance(base, bool),
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 delta1_base 必须是数值",
    )
    candidates = payload.get("delta1_candidates")
    _require(
        isinstance(candidates, list)
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in candidates),
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 delta1_candidates 必须是数值列表",
    )
    _require(
        any(abs(float(base) - float(item)) <= 1e-12 for item in candidates),
        S3_PREREG_FAMILY_MISMATCH,
        "族冻结包 delta1_base 不在候选集合内: " + repr(base),
    )
    fingerprints: list[dict[str, str]] = []
    for task in split_tasks["meta_test"]:
        params = task.get("params")
        _require(
            isinstance(params, Mapping),
            S3_PREREG_FAMILY_MISMATCH,
            "meta_test 任务 params 必须是 mapping: " + str(task["task_id"]),
        )
        missing = [key for key in S3_TASK_FINGERPRINT_PARAM_KEYS if key not in params]
        _require(
            not missing,
            S3_PREREG_FAMILY_MISMATCH,
            "meta_test 任务 params 缺少键: " + ",".join(missing),
        )
        subset = {key: params[key] for key in S3_TASK_FINGERPRINT_PARAM_KEYS}
        computed = task_fingerprint(
            family_id=str(task["family"]),
            formula_version=str(task["formula_version"]),
            task_id=str(task["task_id"]),
            seed=int(task["seed"]),
            params=subset,
        )
        _require(
            computed == task["task_fingerprint"],
            S3_PREREG_FAMILY_MISMATCH,
            "meta_test 任务指纹复算不一致: " + str(task["task_id"]),
        )
        fingerprints.append(
            {"task_id": str(task["task_id"]), "fingerprint": computed}
        )
    _require(
        len(fingerprints) == S3_REQUIRED_META_TEST_TASKS,
        S3_PREREG_FAMILY_MISMATCH,
        "meta_test 任务数必须为 20: " + str(len(fingerprints)),
    )
    fingerprints.sort(key=lambda item: item["task_id"])
    hash_vectors = _read_hash_vectors(repo_root)
    return {
        "family_id": S3_FAMILY_ID,
        "formula_version": S3_FORMULA_VERSION,
        "FAMILY_SEED": S3_FAMILY_SEED,
        "HOLDOUT_SEED": S3_HOLDOUT_SEED,
        "package_version": _require_str(
            payload.get("package_version"),
            S3_PREREG_FAMILY_MISMATCH,
            "族冻结包 package_version",
        ),
        "package_path": str(relpath),
        "family_package_sha256": sha256_bytes(data),
        "package_bytes": len(data),
        "package_code_sha": _require_hex64(
            payload.get("code_sha"), S3_PREREG_FAMILY_MISMATCH, "族冻结包 code_sha"
        ),
        "task_ids_sha256": computed_ids_sha,
        "hash_vectors_path": hash_vectors["path"],
        "hash_vectors_sha256": hash_vectors["sha256"],
        "task_fingerprint_algorithm": S3_TASK_FINGERPRINT_ALGORITHM,
        "task_fingerprint_param_keys": list(S3_TASK_FINGERPRINT_PARAM_KEYS),
        "task_fingerprints": fingerprints,
        "split_counts": dict(S3_SPLIT_COUNTS),
        "design_dim": S3_DESIGN_DIM,
        "design_box": [S3_DESIGN_LOWER, S3_DESIGN_UPPER],
        "delta1_base": float(base),
        "delta1_candidates": [float(item) for item in candidates],
        "support_pool_size": S3_SUPPORT_POOL_SIZE,
        "query_size": S3_QUERY_SIZE,
        "n_tasks": len(tasks),
        "physical_call_count": 0,
        "created_utc": str(payload.get("created_utc")),
    }


def normalize_references_sealed(
    relpath: str,
    repo_root: str | Path,
    family: Mapping[str, Any],
) -> dict[str, Any]:
    """读取封存参考解（只记录 path/sha/每任务 digest，不把 f_ref/u* 写入 prereg）。"""
    path, data, payload = _read_json(relpath, repo_root, "封存参考解")
    _require_mapping(payload, S3_PREREG_REFERENCES_MISMATCH, "封存参考解")
    _require(
        payload.get("schema_version") == S3_REFERENCES_SEALED_SCHEMA_VERSION,
        S3_PREREG_REFERENCES_MISMATCH,
        "封存参考解 schema_version 不符",
    )
    for key, expected in (
        ("family_id", S3_FAMILY_ID),
        ("formula_version", S3_FORMULA_VERSION),
        ("family_seed", S3_FAMILY_SEED),
        ("holdout_seed", S3_HOLDOUT_SEED),
    ):
        _require(
            payload.get(key) == expected,
            S3_PREREG_REFERENCES_MISMATCH,
            "封存参考解 " + key + " 不符",
        )
    _require(
        payload.get("physical_call_count") == 0,
        S3_PREREG_REFERENCES_MISMATCH,
        "封存参考解 physical_call_count 必须为 0",
    )
    references = payload.get("references")
    _require(
        isinstance(references, list) and len(references) == S3_REFERENCE_COUNT,
        S3_PREREG_REFERENCES_MISMATCH,
        "封存参考解条数必须为 110: " + str(len(references) if isinstance(references, list) else None),
    )
    _require(
        payload.get("n_references") == S3_REFERENCE_COUNT,
        S3_PREREG_REFERENCES_MISMATCH,
        "封存参考解 n_references 必须为 110",
    )
    digests: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for record in references:
        _require_mapping(record, S3_PREREG_REFERENCES_MISMATCH, "封存参考记录")
        task_id = _require_str(
            record.get("task_id"), S3_PREREG_REFERENCES_MISMATCH, "reference.task_id"
        )
        _require(
            task_id not in seen_ids,
            S3_PREREG_REFERENCES_MISMATCH,
            "封存参考解 task_id 重复: " + task_id,
        )
        seen_ids.add(task_id)
        digest = _require_str(
            record.get("reference_digest"),
            S3_PREREG_REFERENCES_MISMATCH,
            "reference.reference_digest",
        )
        _require(
            len(digest) == 32 and all(ch in "0123456789abcdef" for ch in digest),
            S3_PREREG_REFERENCES_MISMATCH,
            "reference_digest 必须是 32 位小写 hex",
        )
        body = {key: value for key, value in dict(record).items() if key != "reference_digest"}
        computed = canonical_sha256(body)[:32]
        _require(
            computed == digest,
            S3_PREREG_REFERENCES_MISMATCH,
            "封存参考解 reference_digest 复算不一致: " + task_id,
        )
        digests.append({"task_id": task_id, "reference_digest": digest})
    _require(
        not any(
            str(record.get("split")) == "meta_test_negative_control" for record in references
        ),
        S3_PREREG_REFERENCES_MISMATCH,
        "封存参考解不得包含负控制任务",
    )
    digests.sort(key=lambda item: item["task_id"])
    return {
        "path": str(relpath),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "schema_version": S3_REFERENCES_SEALED_SCHEMA_VERSION,
        "n_references": S3_REFERENCE_COUNT,
        "task_ids": sorted(seen_ids),
        "task_ids_sha256": task_ids_sha256(sorted(seen_ids)),
        "references": digests,
        "physical_call_count": 0,
    }


def normalize_calibration(relpath: str, repo_root: str | Path) -> dict[str, Any]:
    """读取族校准报告（结构见 S3_CALIBRATION_SCHEMA_VERSION）；只做结构校验。"""
    path, data, payload = _read_json(relpath, repo_root, "族校准报告")
    _require_mapping(payload, S3_PREREG_ARTIFACT_INVALID, "族校准报告")
    _require(
        payload.get("schema_version") == S3_CALIBRATION_SCHEMA_VERSION,
        S3_PREREG_ARTIFACT_INVALID,
        "族校准报告 schema_version 不符: " + repr(payload.get("schema_version")),
    )
    _require(
        payload.get("family_id") == S3_FAMILY_ID
        and payload.get("formula_version") == S3_FORMULA_VERSION,
        S3_PREREG_ARTIFACT_INVALID,
        "族校准报告 family/formula_version 不符",
    )
    _require(
        payload.get("validation_split") == "meta_validation",
        S3_PREREG_ARTIFACT_INVALID,
        "族校准报告 validation_split 必须是 meta_validation",
    )
    _require(
        payload.get("physical_call_count") == 0,
        S3_PREREG_ARTIFACT_INVALID,
        "族校准报告 physical_call_count 必须为 0",
    )
    _require(
        payload.get("accepted") is True,
        S3_PREREG_ARTIFACT_INVALID,
        "族校准报告 accepted 必须为 True（未通过校准不得冻结 prereg）",
    )
    candidates = payload.get("candidates")
    _require(
        isinstance(candidates, list) and len(candidates) >= 1,
        S3_PREREG_ARTIFACT_INVALID,
        "族校准报告 candidates 必须是非空 list",
    )
    candidate_bases: list[float] = []
    for candidate in candidates:
        _require_mapping(candidate, S3_PREREG_ARTIFACT_INVALID, "校准候选")
        value = candidate.get("delta1_base")
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool),
            S3_PREREG_ARTIFACT_INVALID,
            "校准候选 delta1_base 必须是数值",
        )
        candidate_bases.append(float(value))
    selected = payload.get("selected_delta1_base")
    _require(
        isinstance(selected, (int, float)) and not isinstance(selected, bool),
        S3_PREREG_ARTIFACT_INVALID,
        "校准报告 selected_delta1_base 必须是数值",
    )
    _require(
        any(abs(float(selected) - base) <= 1e-12 for base in candidate_bases),
        S3_PREREG_ARTIFACT_INVALID,
        "校准报告 selected_delta1_base 不在候选表内",
    )
    construction_stats = payload.get("construction_stats")
    _require(
        isinstance(construction_stats, Mapping),
        S3_PREREG_ARTIFACT_INVALID,
        "校准报告 construction_stats 必须是 mapping",
    )
    return {
        "path": str(relpath),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "schema_version": S3_CALIBRATION_SCHEMA_VERSION,
        "created_utc": str(payload.get("created_utc")),
        "validation_split": "meta_validation",
        "accepted": True,
        "selected_delta1_base": float(selected),
        "candidates": [dict(candidate) for candidate in candidates],
        "construction_stats": dict(construction_stats),
        "physical_call_count": 0,
    }


def _deep_copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def normalize_episode_bank(
    files: Sequence[Mapping[str, Any]],
    repo_root: str | Path,
) -> dict[str, Any]:
    """读取 3 个 episode bank（每 meta_seed 一个），校验 1600 条/唯一 (step,slot)。"""
    _require(
        isinstance(files, Sequence) and not isinstance(files, (str, bytes)),
        S3_PREREG_ARTIFACT_INVALID,
        "episode_bank_files 必须是 list",
    )
    seen_seeds: set[int] = set()
    normalized_files: list[dict[str, Any]] = []
    for entry in files:
        _require_mapping(entry, S3_PREREG_ARTIFACT_INVALID, "episode_bank 文件条目")
        relpath = _require_str(
            entry.get("path"), S3_PREREG_ARTIFACT_INVALID, "episode_bank.path"
        )
        meta_seed = _require_int(
            entry.get("meta_seed"), S3_PREREG_ARTIFACT_INVALID, "episode_bank.meta_seed"
        )
        _require(
            meta_seed in S3_MODEL_META_SEEDS,
            S3_PREREG_ARTIFACT_INVALID,
            "episode_bank.meta_seed 必须是 0/1/2: " + str(meta_seed),
        )
        _require(
            meta_seed not in seen_seeds,
            S3_PREREG_ARTIFACT_INVALID,
            "episode_bank.meta_seed 重复: " + str(meta_seed),
        )
        seen_seeds.add(meta_seed)
        path = resolve_evidence_path(repo_root, relpath)
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise S3PreregError(
                S3_PREREG_ARTIFACT_INVALID,
                "episode bank 不是 UTF-8: " + str(exc),
            ) from exc
        lines = [line for line in text.splitlines() if line.strip()]
        _require(
            len(lines) == S3_EPISODE_BANK_EPISODES_PER_BANK,
            S3_PREREG_ARTIFACT_INVALID,
            "episode bank 条数必须为 1600: "
            + relpath
            + " -> "
            + str(len(lines)),
        )
        seen_slots: set[tuple[int, int]] = set()
        for line in lines:
            try:
                episode = json.loads(line)
            except json.JSONDecodeError as exc:
                raise S3PreregError(
                    S3_PREREG_ARTIFACT_INVALID,
                    "episode bank 行不是合法 JSON: " + relpath,
                ) from exc
            _require_mapping(episode, S3_PREREG_ARTIFACT_INVALID, "episode 行")
            _require(
                episode.get("schema_version") == S3_EPISODE_BANK_SCHEMA_VERSION,
                S3_PREREG_ARTIFACT_INVALID,
                "episode 行 schema_version 不符: " + relpath,
            )
            _require(
                episode.get("meta_seed") == meta_seed,
                S3_PREREG_ARTIFACT_INVALID,
                "episode 行 meta_seed 不符: " + relpath,
            )
            step = _require_int(episode.get("outer_step"), S3_PREREG_ARTIFACT_INVALID, "outer_step")
            slot = _require_int(episode.get("slot"), S3_PREREG_ARTIFACT_INVALID, "slot")
            _require(
                0 <= step < 200 and 0 <= slot < 8,
                S3_PREREG_ARTIFACT_INVALID,
                "episode 行 outer_step/slot 越界: " + relpath,
            )
            key = (step, slot)
            _require(
                key not in seen_slots,
                S3_PREREG_ARTIFACT_INVALID,
                "episode bank (outer_step, slot) 重复: " + relpath + " " + repr(key),
            )
            seen_slots.add(key)
            _require(
                episode.get("task_split") == "meta_train",
                S3_PREREG_ARTIFACT_INVALID,
                "episode 行 task_split 必须是 meta_train: " + relpath,
            )
            digest = _require_str(
                episode.get("episode_digest"), S3_PREREG_ARTIFACT_INVALID, "episode_digest"
            )
            _require(
                len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest),
                S3_PREREG_ARTIFACT_INVALID,
                "episode_digest 必须是 64 位小写 hex: " + relpath,
            )
        _require(
            len(seen_slots) == S3_EPISODE_BANK_EPISODES_PER_BANK,
            S3_PREREG_ARTIFACT_INVALID,
            "episode bank 唯一 (step,slot) 数不是 1600: " + relpath,
        )
        normalized_files.append(
            {
                "meta_seed": meta_seed,
                "path": str(relpath),
                "sha256": sha256_bytes(data),
                "bytes": len(data),
                "episodes": len(lines),
            }
        )
    _require(
        seen_seeds == set(S3_MODEL_META_SEEDS),
        S3_PREREG_ARTIFACT_INVALID,
        "episode_bank_files 必须恰好覆盖 meta_seeds 0/1/2: " + repr(sorted(seen_seeds)),
    )
    normalized_files.sort(key=lambda item: item["meta_seed"])
    banks = {
        "meta_seed_" + str(item["meta_seed"]): item["sha256"] for item in normalized_files
    }
    return {
        "schema_version": S3_EPISODE_BANK_SCHEMA_VERSION,
        "banks": banks,
        "files": normalized_files,
        "episodes_per_bank": S3_EPISODE_BANK_EPISODES_PER_BANK,
        "unique_episodes": S3_EPISODE_BANK_UNIQUE,
        "model_episode_pairs": S3_MODEL_EPISODE_PAIRS,
        "model_episode_pair_rule": "每个 meta_seed bank 的 1600 个 episode 同时供 FOMAML 与 ANIL 训练（1600x3x2=9600）",
        "physical_call_count": 0,
    }


def _validate_model_config(
    config: Any,
    *,
    arm_type: str,
    meta_seed: int,
) -> dict[str, Any]:
    mapping = _require_exact_keys(
        config,
        S3_MODEL_CONFIG_FIELDS,
        S3_PREREG_ARTIFACT_INVALID,
        "模型 config",
    )
    expected = dict(S3_MODEL_CONFIG_TEMPLATE)
    expected["seed"] = int(meta_seed)
    expected["head_only"] = arm_type == "anil"
    for key, expected_value in expected.items():
        actual_value = mapping[key]
        if isinstance(expected_value, bool):
            _require(
                type(actual_value) is bool and actual_value == expected_value,
                S3_PREREG_ARTIFACT_INVALID,
                "模型 config." + key + " 不符: " + repr(actual_value),
            )
        elif isinstance(expected_value, tuple):
            _require(
                isinstance(actual_value, (list, tuple))
                and [int(item) for item in actual_value] == list(expected_value),
                S3_PREREG_ARTIFACT_INVALID,
                "模型 config." + key + " 不符: " + repr(actual_value),
            )
        elif isinstance(expected_value, str):
            _require(
                actual_value == expected_value,
                S3_PREREG_ARTIFACT_INVALID,
                "模型 config." + key + " 不符: " + repr(actual_value),
            )
        elif isinstance(expected_value, int):
            _require(
                type(actual_value) is int and actual_value == expected_value,
                S3_PREREG_ARTIFACT_INVALID,
                "模型 config." + key + " 不符: " + repr(actual_value),
            )
        else:
            _require(
                isinstance(actual_value, (int, float))
                and not isinstance(actual_value, bool)
                and abs(float(actual_value) - float(expected_value)) <= 1e-15,
                S3_PREREG_ARTIFACT_INVALID,
                "模型 config." + key + " 不符: " + repr(actual_value),
            )
    return dict(mapping)


def normalize_models(
    models: Any,
    repo_root: str | Path,
    episode_bank: Mapping[str, Any],
) -> dict[str, Any]:
    """读取 6 个模型文件（fomaml/anil x meta_seed 0/1/2），返回 prereg.models。"""
    entries_raw: list[Mapping[str, Any]] = []
    if isinstance(models, Mapping):
        for arm_type in S3_MODEL_KINDS:
            group = models.get(arm_type)
            _require(
                isinstance(group, Sequence) and not isinstance(group, (str, bytes)),
                S3_PREREG_ARTIFACT_INVALID,
                "models[" + arm_type + "] 必须是 list",
            )
            for entry in group:
                _require_mapping(entry, S3_PREREG_ARTIFACT_INVALID, "模型条目")
                item = dict(entry)
                item["arm_type"] = arm_type
                entries_raw.append(item)
    elif isinstance(models, Sequence) and not isinstance(models, (str, bytes)):
        for entry in models:
            _require_mapping(entry, S3_PREREG_ARTIFACT_INVALID, "模型条目")
            entries_raw.append(dict(entry))
    else:
        raise S3PreregError(
            S3_PREREG_ARTIFACT_INVALID,
            "models 必须是 {fomaml:[...],anil:[...]} 或模型条目 list",
        )
    bank_shas = dict(episode_bank["banks"])
    entries_by_kind: dict[str, list[dict[str, Any]]] = {kind: [] for kind in S3_MODEL_KINDS}
    seen: set[tuple[str, int]] = set()
    for entry in entries_raw:
        arm_type = _require_str(
            entry.get("arm_type"), S3_PREREG_ARTIFACT_INVALID, "模型 arm_type"
        )
        _require(
            arm_type in S3_MODEL_KINDS,
            S3_PREREG_ARTIFACT_INVALID,
            "模型 arm_type 必须是 fomaml/anil: " + arm_type,
        )
        meta_seed = _require_int(
            entry.get("meta_seed"), S3_PREREG_ARTIFACT_INVALID, "模型 meta_seed"
        )
        _require(
            meta_seed in S3_MODEL_META_SEEDS,
            S3_PREREG_ARTIFACT_INVALID,
            "模型 meta_seed 必须是 0/1/2: " + str(meta_seed),
        )
        key = (arm_type, meta_seed)
        _require(key not in seen, S3_PREREG_ARTIFACT_INVALID, "模型条目重复: " + repr(key))
        seen.add(key)
        relpath = _require_str(entry.get("path"), S3_PREREG_ARTIFACT_INVALID, "模型 path")
        path = resolve_evidence_path(repo_root, relpath)
        data = path.read_bytes()
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise S3PreregError(
                S3_PREREG_ARTIFACT_INVALID,
                "模型文件不是合法 UTF-8 JSON: " + relpath,
            ) from exc
        _require_mapping(payload, S3_PREREG_ARTIFACT_INVALID, "模型文件")
        _require(
            payload.get("schema_version") == S3_MODEL_FILE_SCHEMA_VERSION,
            S3_PREREG_ARTIFACT_INVALID,
            "模型文件 schema_version 不符: " + relpath,
        )
        _require(
            payload.get("arm_type") == arm_type,
            S3_PREREG_ARTIFACT_INVALID,
            "模型文件 arm_type 与清单不符: " + relpath,
        )
        _require(
            payload.get("meta_seed") == meta_seed,
            S3_PREREG_ARTIFACT_INVALID,
            "模型文件 meta_seed 与清单不符: " + relpath,
        )
        config = _validate_model_config(
            payload.get("config"), arm_type=arm_type, meta_seed=meta_seed
        )
        parameters = payload.get("parameters")
        _require(
            isinstance(parameters, list) and len(parameters) >= 6,
            S3_PREREG_ARTIFACT_INVALID,
            "模型文件 parameters 必须是非空 list: " + relpath,
        )
        bank_sha = _require_hex64(
            payload.get("episode_bank_sha256"),
            S3_PREREG_ARTIFACT_INVALID,
            "模型 episode_bank_sha256",
        )
        _require(
            bank_sha == bank_shas["meta_seed_" + str(meta_seed)],
            S3_PREREG_ARTIFACT_INVALID,
            "模型 episode_bank_sha256 与该 meta_seed bank 不一致: " + relpath,
        )
        final_loss = payload.get("final_train_loss")
        _require(
            isinstance(final_loss, (int, float))
            and not isinstance(final_loss, bool)
            and math.isfinite(float(final_loss)),
            S3_PREREG_ARTIFACT_INVALID,
            "模型 final_train_loss 必须是有限数值: " + relpath,
        )
        entries_by_kind[arm_type].append(
            {
                "meta_seed": meta_seed,
                "path": str(relpath),
                "sha256": sha256_bytes(data),
                "bytes": len(data),
                "config": config,
                "episode_bank_sha256": bank_sha,
                "final_train_loss": float(final_loss),
            }
        )
    for arm_type in S3_MODEL_KINDS:
        _require(
            sorted(item["meta_seed"] for item in entries_by_kind[arm_type])
            == list(S3_MODEL_META_SEEDS),
            S3_PREREG_ARTIFACT_INVALID,
            "models[" + arm_type + "] 必须覆盖 meta_seeds 0/1/2",
        )
        entries_by_kind[arm_type].sort(key=lambda item: item["meta_seed"])
    normalized: dict[str, Any] = {}
    for arm_type in S3_MODEL_KINDS:
        entries = entries_by_kind[arm_type]
        base_config = dict(entries[0]["config"])
        normalized[arm_type] = {
            "kind": arm_type,
            "config": base_config,
            "sha256": canonical_sha256(entries),
            "meta_seeds": [item["meta_seed"] for item in entries],
            "models": entries,
            "episode_bank_sha256": {
                "meta_seed_" + str(item["meta_seed"]): item["episode_bank_sha256"]
                for item in entries
            },
            "config_note": "config 为 meta_seed=0 模型配置模板；逐 seed 配置见 models[*].models[*].config",
        }
    return normalized


# ---------------------------------------------------------------------------
# 预注册结构校验、构建、冻结写盘与校验（计划 v1.2b §6 / §6.1）
# ---------------------------------------------------------------------------
S3_EPISODE_BANK_PATH_TEMPLATE = S3_MODELS_DIR_RELPATH + "/episode_bank_meta_{meta_seed}.jsonl"
S3_MODEL_PATH_TEMPLATE = S3_MODELS_DIR_RELPATH + "/{kind}_meta_{meta_seed}.json"


def default_episode_bank_files() -> list[dict[str, Any]]:
    return [
        {
            "meta_seed": meta_seed,
            "path": S3_EPISODE_BANK_PATH_TEMPLATE.format(meta_seed=meta_seed),
        }
        for meta_seed in S3_MODEL_META_SEEDS
    ]


def default_models() -> dict[str, list[dict[str, Any]]]:
    return {
        kind: [
            {
                "meta_seed": meta_seed,
                "path": S3_MODEL_PATH_TEMPLATE.format(kind=kind, meta_seed=meta_seed),
            }
            for meta_seed in S3_MODEL_META_SEEDS
        ]
        for kind in S3_MODEL_KINDS
    }


def _json_equal(left: Any, right: Any) -> bool:
    return canonical_json(left) == canonical_json(right)


def _require_json_equal(value: Any, expected: Any, code: str, label: str) -> None:
    _require(_json_equal(value, expected), code, label + " 与冻结默认结构不一致")


_UTC_TIMESTAMP_RE = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"


def _require_utc_timestamp(value: Any, code: str, label: str) -> str:
    text = _require_str(value, code, label)
    _require(
        re.match(_UTC_TIMESTAMP_RE, text) is not None,
        code,
        label + " 必须是 ISO-8601 UTC 时间戳: " + text,
    )
    return text


def _require_number(value: Any, code: str, label: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        code,
        label + " 必须是数值",
    )
    number = float(value)
    _require(math.isfinite(number), code, label + " 必须是有限数值")
    return number


def _validate_family_structure(family: Any) -> Mapping[str, Any]:
    expected_keys = (
        "family_id",
        "formula_version",
        "FAMILY_SEED",
        "HOLDOUT_SEED",
        "package_version",
        "package_path",
        "family_package_sha256",
        "package_bytes",
        "package_code_sha",
        "task_ids_sha256",
        "hash_vectors_path",
        "hash_vectors_sha256",
        "task_fingerprint_algorithm",
        "task_fingerprint_param_keys",
        "task_fingerprints",
        "split_counts",
        "design_dim",
        "design_box",
        "delta1_base",
        "delta1_candidates",
        "support_pool_size",
        "query_size",
        "n_tasks",
        "physical_call_count",
        "created_utc",
    )
    code = S3_PREREG_SCHEMA_INVALID
    mapping = _require_exact_keys(family, expected_keys, code, "prereg.family")
    _require(mapping["family_id"] == S3_FAMILY_ID, code, "family.family_id 不符")
    _require(mapping["formula_version"] == S3_FORMULA_VERSION, code, "family.formula_version 不符")
    _require(mapping["FAMILY_SEED"] == S3_FAMILY_SEED, code, "family.FAMILY_SEED 不符")
    _require(mapping["HOLDOUT_SEED"] == S3_HOLDOUT_SEED, code, "family.HOLDOUT_SEED 不符")
    _require_str(mapping["package_version"], code, "family.package_version")
    _require_str(mapping["package_path"], code, "family.package_path")
    _require_hex64(mapping["family_package_sha256"], code, "family.family_package_sha256")
    _require_int(mapping["package_bytes"], code, "family.package_bytes")
    _require(mapping["package_bytes"] > 0, code, "family.package_bytes 必须 > 0")
    _require_hex64(mapping["package_code_sha"], code, "family.package_code_sha")
    _require_hex64(mapping["task_ids_sha256"], code, "family.task_ids_sha256")
    _require(
        mapping["hash_vectors_path"] == HASH_VECTORS_RELPATH,
        code,
        "family.hash_vectors_path 不符",
    )
    _require(
        mapping["hash_vectors_sha256"] == HASH_VECTORS_SHA256,
        code,
        "family.hash_vectors_sha256 不符",
    )
    _require(
        mapping["task_fingerprint_algorithm"] == S3_TASK_FINGERPRINT_ALGORITHM,
        code,
        "family.task_fingerprint_algorithm 不符",
    )
    _require(
        isinstance(mapping["task_fingerprint_param_keys"], (list, tuple))
        and [str(item) for item in mapping["task_fingerprint_param_keys"]]
        == list(S3_TASK_FINGERPRINT_PARAM_KEYS),
        code,
        "family.task_fingerprint_param_keys 不符",
    )
    fingerprints = mapping["task_fingerprints"]
    _require(isinstance(fingerprints, list), code, "family.task_fingerprints 必须是 list")
    _require(
        len(fingerprints) == S3_REQUIRED_META_TEST_TASKS,
        code,
        "family.task_fingerprints 必须为 20 项",
    )
    seen_ids: set[str] = set()
    previous_id = ""
    for item in fingerprints:
        record = _require_exact_keys(
            item, ("task_id", "fingerprint"), code, "family.task_fingerprints 项"
        )
        task_id = _require_str(record["task_id"], code, "task_fingerprints.task_id")
        _require(task_id not in seen_ids, code, "task_fingerprints task_id 重复: " + task_id)
        _require(task_id > previous_id, code, "task_fingerprints 必须按 task_id 升序")
        previous_id = task_id
        seen_ids.add(task_id)
        fingerprint = _require_str(
            record["fingerprint"], code, "task_fingerprints.fingerprint"
        )
        _require(
            len(fingerprint) == 16 and all(ch in "0123456789abcdef" for ch in fingerprint),
            code,
            "task_fingerprints.fingerprint 必须是 16 位小写 hex",
        )
    _require_json_equal(mapping["split_counts"], S3_SPLIT_COUNTS, code, "family.split_counts")
    _require(mapping["design_dim"] == S3_DESIGN_DIM, code, "family.design_dim 不符")
    _require_json_equal(
        mapping["design_box"], [S3_DESIGN_LOWER, S3_DESIGN_UPPER], code, "family.design_box"
    )
    candidates = mapping["delta1_candidates"]
    _require(
        isinstance(candidates, list) and len(candidates) >= 1,
        code,
        "family.delta1_candidates 必须是非空 list",
    )
    candidate_values = [_require_number(item, code, "family.delta1_candidates[]") for item in candidates]
    base = _require_number(mapping["delta1_base"], code, "family.delta1_base")
    _require(
        any(abs(base - item) <= 1e-12 for item in candidate_values),
        code,
        "family.delta1_base 不在候选集合内",
    )
    _require(mapping["support_pool_size"] == S3_SUPPORT_POOL_SIZE, code, "family.support_pool_size 不符")
    _require(mapping["query_size"] == S3_QUERY_SIZE, code, "family.query_size 不符")
    _require(mapping["n_tasks"] == sum(S3_SPLIT_COUNTS.values()), code, "family.n_tasks 不符")
    _require(mapping["physical_call_count"] == 0, code, "family.physical_call_count 必须为 0")
    _require_utc_timestamp(mapping["created_utc"], code, "family.created_utc")
    return mapping


def _validate_references_structure(references: Any) -> Mapping[str, Any]:
    code = S3_PREREG_SCHEMA_INVALID
    expected_keys = (
        "path",
        "sha256",
        "bytes",
        "schema_version",
        "n_references",
        "task_ids",
        "task_ids_sha256",
        "references",
        "physical_call_count",
    )
    mapping = _require_exact_keys(references, expected_keys, code, "prereg.references_sealed")
    _require_str(mapping["path"], code, "references_sealed.path")
    _require_hex64(mapping["sha256"], code, "references_sealed.sha256")
    _require_int(mapping["bytes"], code, "references_sealed.bytes")
    _require(
        mapping["schema_version"] == S3_REFERENCES_SEALED_SCHEMA_VERSION,
        code,
        "references_sealed.schema_version 不符",
    )
    _require(
        mapping["n_references"] == S3_REFERENCE_COUNT,
        code,
        "references_sealed.n_references 不符",
    )
    task_ids = mapping["task_ids"]
    _require(isinstance(task_ids, list), code, "references_sealed.task_ids 必须是 list")
    _require(
        len(task_ids) == S3_REFERENCE_COUNT,
        code,
        "references_sealed.task_ids 必须为 110 项",
    )
    ids = [_require_str(item, code, "references_sealed.task_ids[]") for item in task_ids]
    _require(ids == sorted(ids), code, "references_sealed.task_ids 必须升序")
    _require(len(set(ids)) == len(ids), code, "references_sealed.task_ids 不得重复")
    _require(
        mapping["task_ids_sha256"] == task_ids_sha256(ids),
        code,
        "references_sealed.task_ids_sha256 复算不一致",
    )
    records = mapping["references"]
    _require(isinstance(records, list), code, "references_sealed.references 必须是 list")
    _require(
        len(records) == S3_REFERENCE_COUNT,
        code,
        "references_sealed.references 必须为 110 项",
    )
    record_ids: list[str] = []
    for item in records:
        record = _require_exact_keys(
            item, ("task_id", "reference_digest"), code, "references_sealed.references 项"
        )
        record_ids.append(_require_str(record["task_id"], code, "references.task_id"))
        digest = _require_str(record["reference_digest"], code, "references.reference_digest")
        _require(
            len(digest) == 32 and all(ch in "0123456789abcdef" for ch in digest),
            code,
            "references.reference_digest 必须是 32 位小写 hex",
        )
    _require(
        record_ids == sorted(record_ids) and sorted(record_ids) == ids,
        code,
        "references_sealed.references 与 task_ids 不一致",
    )
    _require(mapping["physical_call_count"] == 0, code, "references_sealed.physical_call_count 必须为 0")
    return mapping


def _validate_calibration_structure(calibration: Any) -> Mapping[str, Any]:
    code = S3_PREREG_SCHEMA_INVALID
    expected_keys = (
        "path",
        "sha256",
        "bytes",
        "schema_version",
        "created_utc",
        "validation_split",
        "accepted",
        "selected_delta1_base",
        "candidates",
        "construction_stats",
        "physical_call_count",
    )
    mapping = _require_exact_keys(calibration, expected_keys, code, "prereg.calibration")
    _require_str(mapping["path"], code, "calibration.path")
    _require_hex64(mapping["sha256"], code, "calibration.sha256")
    _require_int(mapping["bytes"], code, "calibration.bytes")
    _require(
        mapping["schema_version"] == S3_CALIBRATION_SCHEMA_VERSION,
        code,
        "calibration.schema_version 不符",
    )
    _require_utc_timestamp(mapping["created_utc"], code, "calibration.created_utc")
    _require(
        mapping["validation_split"] == "meta_validation",
        code,
        "calibration.validation_split 必须是 meta_validation",
    )
    _require(mapping["accepted"] is True, code, "calibration.accepted 必须为 True")
    _require(
        isinstance(mapping["candidates"], list) and len(mapping["candidates"]) >= 1,
        code,
        "calibration.candidates 必须是非空 list",
    )
    bases = [
        _require_number(candidate.get("delta1_base"), code, "calibration.candidates[].delta1_base")
        for candidate in mapping["candidates"]
        if isinstance(candidate, Mapping)
    ]
    _require(len(bases) == len(mapping["candidates"]), code, "calibration.candidates 项必须是 mapping")
    selected = _require_number(mapping["selected_delta1_base"], code, "calibration.selected_delta1_base")
    _require(
        any(abs(selected - base) <= 1e-12 for base in bases),
        code,
        "calibration.selected_delta1_base 不在候选表内",
    )
    _require(
        isinstance(mapping["construction_stats"], Mapping),
        code,
        "calibration.construction_stats 必须是 mapping",
    )
    _require(mapping["physical_call_count"] == 0, code, "calibration.physical_call_count 必须为 0")
    return mapping


def _validate_episode_bank_structure(episode_bank: Any) -> Mapping[str, Any]:
    code = S3_PREREG_SCHEMA_INVALID
    expected_keys = (
        "schema_version",
        "banks",
        "files",
        "episodes_per_bank",
        "unique_episodes",
        "model_episode_pairs",
        "model_episode_pair_rule",
        "physical_call_count",
    )
    mapping = _require_exact_keys(episode_bank, expected_keys, code, "prereg.episode_bank")
    _require(
        mapping["schema_version"] == S3_EPISODE_BANK_SCHEMA_VERSION,
        code,
        "episode_bank.schema_version 不符",
    )
    banks = _require_mapping(mapping["banks"], code, "episode_bank.banks")
    expected_bank_keys = {"meta_seed_" + str(seed) for seed in S3_MODEL_META_SEEDS}
    _require(set(banks) == expected_bank_keys, code, "episode_bank.banks 键集合不符")
    for key, value in banks.items():
        _require_hex64(value, code, "episode_bank.banks." + key)
    files = mapping["files"]
    _require(isinstance(files, list) and len(files) == 3, code, "episode_bank.files 必须为 3 项")
    seen_seeds: set[int] = set()
    for item in files:
        record = _require_exact_keys(
            item,
            ("meta_seed", "path", "sha256", "bytes", "episodes"),
            code,
            "episode_bank.files 项",
        )
        meta_seed = _require_int(record["meta_seed"], code, "episode_bank.files[].meta_seed")
        _require(meta_seed in S3_MODEL_META_SEEDS, code, "episode_bank.meta_seed 越界")
        _require(meta_seed not in seen_seeds, code, "episode_bank.meta_seed 重复")
        seen_seeds.add(meta_seed)
        _require_str(record["path"], code, "episode_bank.files[].path")
        _require_hex64(record["sha256"], code, "episode_bank.files[].sha256")
        _require_int(record["bytes"], code, "episode_bank.files[].bytes")
        _require(
            record["episodes"] == S3_EPISODE_BANK_EPISODES_PER_BANK,
            code,
            "episode_bank.files[].episodes 必须为 1600",
        )
        _require(
            record["sha256"] == banks["meta_seed_" + str(meta_seed)],
            code,
            "episode_bank.files 与 banks sha 不一致",
        )
    _require(
        mapping["episodes_per_bank"] == S3_EPISODE_BANK_EPISODES_PER_BANK,
        code,
        "episode_bank.episodes_per_bank 不符",
    )
    _require(
        mapping["unique_episodes"] == S3_EPISODE_BANK_UNIQUE,
        code,
        "episode_bank.unique_episodes 不符",
    )
    _require(
        mapping["model_episode_pairs"] == S3_MODEL_EPISODE_PAIRS,
        code,
        "episode_bank.model_episode_pairs 不符",
    )
    _require_str(mapping["model_episode_pair_rule"], code, "episode_bank.model_episode_pair_rule")
    _require(mapping["physical_call_count"] == 0, code, "episode_bank.physical_call_count 必须为 0")
    return mapping


def _validate_models_structure(models: Any, episode_bank: Mapping[str, Any]) -> Mapping[str, Any]:
    code = S3_PREREG_SCHEMA_INVALID
    mapping = _require_exact_keys(models, S3_MODEL_KINDS, code, "prereg.models")
    banks = dict(episode_bank["banks"])
    for kind in S3_MODEL_KINDS:
        entry = _require_exact_keys(
            mapping[kind],
            (
                "kind",
                "config",
                "sha256",
                "meta_seeds",
                "models",
                "episode_bank_sha256",
                "config_note",
            ),
            code,
            "prereg.models." + kind,
        )
        _require(entry["kind"] == kind, code, "models." + kind + ".kind 不符")
        config = _validate_model_config(entry["config"], arm_type=kind, meta_seed=0)
        _require_hex64(entry["sha256"], code, "models." + kind + ".sha256")
        _require(
            [int(item) for item in entry["meta_seeds"]] == list(S3_MODEL_META_SEEDS),
            code,
            "models." + kind + ".meta_seeds 必须为 [0,1,2]",
        )
        per_seed = entry["models"]
        _require(
            isinstance(per_seed, list) and len(per_seed) == len(S3_MODEL_META_SEEDS),
            code,
            "models." + kind + ".models 必须为 3 项",
        )
        seen_seeds: list[int] = []
        for model in per_seed:
            record = _require_exact_keys(
                model,
                (
                    "meta_seed",
                    "path",
                    "sha256",
                    "bytes",
                    "config",
                    "episode_bank_sha256",
                    "final_train_loss",
                ),
                code,
                "models." + kind + ".models 项",
            )
            meta_seed = _require_int(record["meta_seed"], code, "models.models[].meta_seed")
            _require(meta_seed in S3_MODEL_META_SEEDS, code, "models.models[].meta_seed 越界")
            seen_seeds.append(meta_seed)
            _require_str(record["path"], code, "models.models[].path")
            _require_hex64(record["sha256"], code, "models.models[].sha256")
            _require_int(record["bytes"], code, "models.models[].bytes")
            _validate_model_config(record["config"], arm_type=kind, meta_seed=meta_seed)
            bank_sha = _require_hex64(
                record["episode_bank_sha256"], code, "models.models[].episode_bank_sha256"
            )
            _require(
                bank_sha == banks["meta_seed_" + str(meta_seed)],
                code,
                "models.models[].episode_bank_sha256 与 bank 不一致",
            )
            _require_number(record["final_train_loss"], code, "models.models[].final_train_loss")
        _require(seen_seeds == list(S3_MODEL_META_SEEDS), code, "models.models meta_seed 顺序不符")
        _require(
            _json_equal(entry["episode_bank_sha256"], {key: banks[key] for key in banks}),
            code,
            "models." + kind + ".episode_bank_sha256 与 episode_bank 不一致",
        )
        _require_str(entry["config_note"], code, "models." + kind + ".config_note")
        computed = canonical_sha256(entry["models"])
        _require(computed == entry["sha256"], code, "models." + kind + ".sha256 复算不一致")
        _require_json_equal(entry["config"], config, code, "models." + kind + ".config")
    return mapping


def _validate_preregistration_structure(prereg: Any) -> Mapping[str, Any]:
    """校验 prereg 顶层/子结构/冻结默认值/digest/id（不读证据文件、不重算 code_sha）。"""
    code = S3_PREREG_SCHEMA_INVALID
    expected_top_keys = S3_PREREG_REQUIRED_FIELDS + ("prereg_id", "prereg_digest")
    mapping = _require_exact_keys(prereg, expected_top_keys, code, "prereg")
    _require(
        mapping["schema_version"] == S3_PREREG_SCHEMA_VERSION,
        code,
        "prereg.schema_version 不符",
    )
    _require_utc_timestamp(mapping["created_utc"], code, "prereg.created_utc")
    _require_hex64(mapping["code_sha"], code, "prereg.code_sha")
    _require_hex64(mapping["analysis_plan_digest"], code, "prereg.analysis_plan_digest")
    _require_hex64(mapping["fd_gate_sha256"], code, "prereg.fd_gate_sha256")
    _require(
        type(mapping["physical_call_count"]) is int and mapping["physical_call_count"] == 0,
        code,
        "prereg.physical_call_count 必须为 int 0",
    )
    family = _validate_family_structure(mapping["family"])
    references = _validate_references_structure(mapping["references_sealed"])
    _require(
        references["task_ids_sha256"] != family["task_ids_sha256"],
        code,
        "references task_ids_sha256 不应等于全族 task_ids_sha256（前者不含负控制）",
    )
    _validate_calibration_structure(mapping["calibration"])
    _require(
        abs(
            float(mapping["calibration"]["selected_delta1_base"])
            - float(family["delta1_base"])
        )
        <= 1e-12,
        S3_PREREG_FAMILY_MISMATCH,
        "校准 selected_delta1_base 与族包 delta1_base 不一致",
    )
    episode_bank = _validate_episode_bank_structure(mapping["episode_bank"])
    _validate_models_structure(mapping["models"], episode_bank)
    expected_arms = [dict(spec) for spec in S3_ARM_SPECS]
    _require_json_equal(mapping["arms"], expected_arms, code, "prereg.arms")
    _require(
        [item["id"] for item in mapping["arms"]] == list(S3_ARMS),
        code,
        "prereg.arms id 顺序不符",
    )
    _require_json_equal(mapping["budgets"], S3_PREREG_BUDGETS, code, "prereg.budgets")
    _require_json_equal(mapping["endpoints"], S3_ENDPOINTS, code, "prereg.endpoints")
    _require_json_equal(mapping["statistics"], S3_STATISTICS, code, "prereg.statistics")
    _require_json_equal(mapping["figures"], S3_FIGURES, code, "prereg.figures")
    _require_json_equal(
        mapping["negative_controls"], S3_NEGATIVE_CONTROLS, code, "prereg.negative_controls"
    )
    _require_json_equal(mapping["campaign"], S3_CAMPAIGN, code, "prereg.campaign")
    _require_json_equal(mapping["ood"], S3_OOD, code, "prereg.ood")
    _require_json_equal(mapping["determinism"], expected_determinism_section(mapping["family"]), code, "prereg.determinism")
    _require_json_equal(
        mapping["resource_limits"], S3_RESOURCE_LIMITS, S3_PREREG_RESOURCE_LIMITS_INVALID, "prereg.resource_limits"
    )
    for key, value in mapping["resource_limits"].items():
        _require(
            type(value) is int,
            S3_PREREG_RESOURCE_LIMITS_INVALID,
            "resource_limits." + key + " 必须是 int",
        )
    _require_json_equal(
        mapping["data_boundary"], S3_DATA_BOUNDARY, S3_PREREG_DATA_BOUNDARY_ERROR, "prereg.data_boundary"
    )
    _require_json_equal(
        mapping["authorization_chain"],
        S3_AUTHORIZATION_CHAIN,
        S3_PREREG_AUTHORIZATION_MISMATCH,
        "prereg.authorization_chain",
    )
    reject_placeholders(mapping, "prereg")
    digest = prereg_digest(mapping)
    _require(
        mapping["prereg_digest"] == digest,
        S3_PREREG_DIGEST_MISMATCH,
        "prereg.prereg_digest 复算不一致",
    )
    expected_id = S3_PREREG_ID_PREFIX + digest[:16]
    _require(
        mapping["prereg_id"] == expected_id,
        S3_PREREG_DIGEST_MISMATCH,
        "prereg.prereg_id 与 digest 不一致: " + str(mapping["prereg_id"]),
    )
    return mapping


def _verify_artifact_bindings(prereg: Mapping[str, Any], repo_root: str | Path) -> None:
    root = _repo_root_or_default(repo_root)
    code = S3_PREREG_ARTIFACT_INVALID
    family = _validate_family_structure(prereg["family"])
    family_again = normalize_family_package(family["package_path"], root)
    _require(
        family_again["family_package_sha256"] == family["family_package_sha256"],
        code,
        "族包文件 sha 与 prereg 不一致（族包已变更或路径错）",
    )
    _require(
        family_again["task_ids_sha256"] == family["task_ids_sha256"],
        S3_PREREG_FAMILY_MISMATCH,
        "族包 task_ids_sha256 与 prereg 不一致",
    )
    _require(
        family_again["hash_vectors_sha256"] == family["hash_vectors_sha256"],
        S3_PREREG_HASH_VECTORS_MISMATCH,
        "hash_vectors.json 与 prereg 不一致",
    )
    references = _validate_references_structure(prereg["references_sealed"])
    references_again = normalize_references_sealed(references["path"], root, family)
    _require(
        references_again["sha256"] == references["sha256"],
        S3_PREREG_REFERENCES_MISMATCH,
        "封存参考解 sha 与 prereg 不一致",
    )
    _require(
        references_again["task_ids_sha256"] == references["task_ids_sha256"],
        S3_PREREG_REFERENCES_MISMATCH,
        "封存参考解 task_ids_sha256 与 prereg 不一致",
    )
    calibration = _validate_calibration_structure(prereg["calibration"])
    calibration_again = normalize_calibration(calibration["path"], root)
    _require(
        calibration_again["sha256"] == calibration["sha256"],
        code,
        "校准报告 sha 与 prereg 不一致",
    )
    episode_bank = _validate_episode_bank_structure(prereg["episode_bank"])
    bank_files = [
        {"meta_seed": item["meta_seed"], "path": item["path"]}
        for item in episode_bank["files"]
    ]
    episode_bank_again = normalize_episode_bank(bank_files, root)
    for seed in S3_MODEL_META_SEEDS:
        key = "meta_seed_" + str(seed)
        _require(
            episode_bank_again["banks"][key] == episode_bank["banks"][key],
            code,
            "episode bank 文件 sha 与 prereg 不一致: " + key,
        )
    model_entries = {
        kind: [
            {"meta_seed": item["meta_seed"], "path": item["path"]}
            for item in prereg["models"][kind]["models"]
        ]
        for kind in S3_MODEL_KINDS
    }
    models_again = normalize_models(model_entries, root, episode_bank_again)
    for kind in S3_MODEL_KINDS:
        _require(
            models_again[kind]["sha256"] == prereg["models"][kind]["sha256"],
            code,
            "模型文件清单 sha 与 prereg 不一致: " + kind,
        )
    # R-S3-07 Q2 + v1.3b：M2 冻结 FD 梯度门必须存在、结构 PASS 且 raw sha 与 prereg 绑定一致
    gate_info = frozen_fd_gate_info(root)
    _require(
        gate_info["sha256"] == prereg["fd_gate_sha256"],
        code,
        "FD 梯度门文件 raw sha 与 prereg.fd_gate_sha256 不一致",
    )


def build_preregistration(
    *,
    repo_root: str | Path | None = None,
    created_utc: str,
    family_package: str = S3_FAMILY_PACKAGE_RELPATH,
    references_sealed: str = S3_REFERENCES_SEALED_RELPATH,
    calibration: str = S3_CALIBRATION_RELPATH,
    episode_bank_files: Sequence[Mapping[str, Any]] | None = None,
    models: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    arms: Sequence[Mapping[str, Any]] | None = None,
    budgets: Mapping[str, Any] | None = None,
    endpoints: Mapping[str, Any] | None = None,
    statistics: Mapping[str, Any] | None = None,
    figures: Mapping[str, Any] | None = None,
    negative_controls: Mapping[str, Any] | None = None,
    campaign: Mapping[str, Any] | None = None,
    ood: Mapping[str, Any] | None = None,
    determinism: Mapping[str, Any] | None = None,
    resource_limits: Mapping[str, Any] | None = None,
    data_boundary: Mapping[str, Any] | None = None,
    authorization_chain: Mapping[str, Any] | None = None,
    code_sha: str | None = None,
    analysis_code_sha: str | None = None,
    physical_call_count: int = 0,
    verify: bool = True,
) -> dict[str, Any]:
    """构建 S3 预注册（只读证据文件；不训练、不评估、不读 holdout 数据行）。"""
    root = _repo_root_or_default(repo_root)
    _require(
        type(physical_call_count) is int and physical_call_count == 0,
        S3_PREREG_SCHEMA_INVALID,
        "physical_call_count 必须为 int 0",
    )
    created = _require_utc_timestamp(created_utc, S3_PREREG_SCHEMA_INVALID, "created_utc")
    # R-S3-07 Q2 + v1.3b：M2 冻结 FD 梯度门必须存在、结构 PASS 且 raw sha 绑定进 prereg
    gate_info = frozen_fd_gate_info(root)
    family = normalize_family_package(family_package, root)
    references = normalize_references_sealed(references_sealed, root, family)
    calibration_record = normalize_calibration(calibration, root)
    if episode_bank_files is None:
        episode_bank_files = default_episode_bank_files()
    episode_bank = normalize_episode_bank(episode_bank_files, root)
    if models is None:
        models = default_models()
    models_record = normalize_models(models, root, episode_bank)
    arms_record = [dict(spec) for spec in S3_ARM_SPECS] if arms is None else arms
    budgets_record = _deep_copy_json(S3_PREREG_BUDGETS) if budgets is None else budgets
    endpoints_record = _deep_copy_json(S3_ENDPOINTS) if endpoints is None else endpoints
    statistics_record = _deep_copy_json(S3_STATISTICS) if statistics is None else statistics
    figures_record = _deep_copy_json(S3_FIGURES) if figures is None else figures
    negative_record = (
        _deep_copy_json(S3_NEGATIVE_CONTROLS) if negative_controls is None else negative_controls
    )
    campaign_record = _deep_copy_json(S3_CAMPAIGN) if campaign is None else campaign
    ood_record = _deep_copy_json(S3_OOD) if ood is None else ood
    determinism_record = expected_determinism_section(family) if determinism is None else determinism
    limits_record = dict(S3_RESOURCE_LIMITS) if resource_limits is None else resource_limits
    boundary_record = _deep_copy_json(S3_DATA_BOUNDARY) if data_boundary is None else data_boundary
    authorization_record = (
        _deep_copy_json(S3_AUTHORIZATION_CHAIN)
        if authorization_chain is None
        else authorization_chain
    )
    _require_json_equal(arms_record, [dict(spec) for spec in S3_ARM_SPECS], S3_PREREG_SCHEMA_INVALID, "arms")
    _require_json_equal(budgets_record, S3_PREREG_BUDGETS, S3_PREREG_BUDGET_MISMATCH, "budgets")
    _require_json_equal(endpoints_record, S3_ENDPOINTS, S3_PREREG_SCHEMA_INVALID, "endpoints")
    _require_json_equal(statistics_record, S3_STATISTICS, S3_PREREG_SCHEMA_INVALID, "statistics")
    _require_json_equal(figures_record, S3_FIGURES, S3_PREREG_SCHEMA_INVALID, "figures")
    _require_json_equal(
        negative_record, S3_NEGATIVE_CONTROLS, S3_PREREG_SCHEMA_INVALID, "negative_controls"
    )
    _require_json_equal(campaign_record, S3_CAMPAIGN, S3_PREREG_SCHEMA_INVALID, "campaign")
    _require_json_equal(ood_record, S3_OOD, S3_PREREG_SCHEMA_INVALID, "ood")
    _require_json_equal(
        determinism_record, expected_determinism_section(family), S3_PREREG_SCHEMA_INVALID, "determinism"
    )
    _require_json_equal(
        limits_record, S3_RESOURCE_LIMITS, S3_PREREG_RESOURCE_LIMITS_INVALID, "resource_limits"
    )
    _require_json_equal(
        boundary_record, S3_DATA_BOUNDARY, S3_PREREG_DATA_BOUNDARY_ERROR, "data_boundary"
    )
    _require_json_equal(
        authorization_record,
        S3_AUTHORIZATION_CHAIN,
        S3_PREREG_AUTHORIZATION_MISMATCH,
        "authorization_chain",
    )
    for key, value in limits_record.items():
        _require(
            type(value) is int,
            S3_PREREG_RESOURCE_LIMITS_INVALID,
            "resource_limits." + key + " 必须是 int",
        )
    if code_sha is None:
        code_sha_value = compute_code_sha(root)
    else:
        code_sha_value = _require_hex64(code_sha, S3_PREREG_CODE_SHA_MISMATCH, "code_sha")
    if analysis_code_sha is None:
        analysis_code_sha_value = compute_analysis_code_sha(root)
    else:
        analysis_code_sha_value = _require_hex64(
            analysis_code_sha, S3_PREREG_CODE_SHA_MISMATCH, "analysis_code_sha"
        )
    plan_digest = analysis_plan_digest(
        endpoints=endpoints_record,
        statistics=statistics_record,
        figures=figures_record,
        analysis_code_sha=analysis_code_sha_value,
    )
    payload: dict[str, Any] = {
        "schema_version": S3_PREREG_SCHEMA_VERSION,
        "created_utc": created,
        "family": family,
        "references_sealed": references,
        "calibration": calibration_record,
        "episode_bank": episode_bank,
        "models": models_record,
        "arms": arms_record,
        "budgets": budgets_record,
        "endpoints": endpoints_record,
        "statistics": statistics_record,
        "figures": figures_record,
        "negative_controls": negative_record,
        "campaign": campaign_record,
        "ood": ood_record,
        "determinism": determinism_record,
        "fd_gate_sha256": str(gate_info["sha256"]),
        "resource_limits": limits_record,
        "analysis_plan_digest": plan_digest,
        "code_sha": code_sha_value,
        "physical_call_count": 0,
        "data_boundary": boundary_record,
        "authorization_chain": authorization_record,
    }
    digest = prereg_digest(payload)
    payload["prereg_id"] = S3_PREREG_ID_PREFIX + digest[:16]
    payload["prereg_digest"] = digest
    if verify:
        _validate_preregistration_structure(payload)
        if analysis_code_sha is not None:
            expected_digest = analysis_plan_digest(
                endpoints=payload["endpoints"],
                statistics=payload["statistics"],
                figures=payload["figures"],
                analysis_code_sha=analysis_code_sha_value,
            )
            _require(
                expected_digest == payload["analysis_plan_digest"],
                S3_PREREG_DIGEST_MISMATCH,
                "analysis_plan_digest 复算不一致",
            )
    return payload


def verify_preregistration(
    prereg: Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    expected_code_sha: str | None = None,
    verify_code_sha: bool = True,
    verify_hash_vectors: bool = True,
    verify_artifacts: bool = True,
) -> bool:
    """校验预注册：结构/digest/id + 证据文件绑定 + 可选 code_sha/analysis digest 重算。"""
    root = _repo_root_or_default(repo_root)
    mapping = _validate_preregistration_structure(prereg)
    if expected_code_sha is not None:
        expected = _require_hex64(
            expected_code_sha, S3_PREREG_CODE_SHA_MISMATCH, "expected_code_sha"
        )
        _require(
            mapping["code_sha"] == expected,
            S3_PREREG_CODE_SHA_MISMATCH,
            "prereg.code_sha 与期望值不一致: " + mapping["code_sha"],
        )
    if verify_hash_vectors:
        hash_vectors = _read_hash_vectors(root)
        _require(
            hash_vectors["sha256"] == mapping["family"]["hash_vectors_sha256"],
            S3_PREREG_HASH_VECTORS_MISMATCH,
            "hash_vectors.json sha 与 prereg 不一致",
        )
    if verify_artifacts:
        _verify_artifact_bindings(mapping, root)
    if verify_code_sha:
        actual_code_sha = compute_code_sha(root)
        _require(
            actual_code_sha == mapping["code_sha"],
            S3_PREREG_CODE_SHA_MISMATCH,
            "当前 7 文件 code_sha 与 prereg 不一致: " + actual_code_sha,
        )
        actual_analysis_sha = compute_analysis_code_sha(root)
        expected_plan_digest = analysis_plan_digest(
            endpoints=mapping["endpoints"],
            statistics=mapping["statistics"],
            figures=mapping["figures"],
            analysis_code_sha=actual_analysis_sha,
        )
        _require(
            expected_plan_digest == mapping["analysis_plan_digest"],
            S3_PREREG_DIGEST_MISMATCH,
            "analysis_plan_digest 与当前 2 个分析文件复算不一致",
        )
    return True


def write_preregistration(path: str | Path, prereg: Mapping[str, Any]) -> dict[str, Any]:
    """把 prereg 以 canonical JSON + LF 冻结写盘（拒绝覆盖已有文件）。"""
    _validate_preregistration_structure(prereg)
    target = Path(path)
    _require(
        not target.exists(),
        S3_PREREG_FILE_ERROR,
        "预注册文件已存在，拒绝覆盖: " + str(target),
    )
    data = canonical_json(prereg).encode("utf-8") + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": str(target), "bytes": len(data), "sha256": sha256_bytes(data)}


def read_preregistration(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    _require(target.is_file(), S3_PREREG_FILE_ERROR, "预注册文件不存在: " + str(target))
    data = target.read_bytes()
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S3PreregError(
            S3_PREREG_SCHEMA_INVALID,
            "预注册文件不是合法 UTF-8 JSON: " + str(exc),
        ) from exc
    return _require_mapping(payload, S3_PREREG_SCHEMA_INVALID, "prereg")

# ---------------------------------------------------------------------------
# R-S3-07（Lead m07285 Q2）：M2 冻结 FD/梯度门的结构校验
# ---------------------------------------------------------------------------
def _fd_gate_error(message: str, *, relpath: str = S3_GATE_RELPATH) -> None:
    raise S3PreregError(
        S3_PREREG_ARTIFACT_INVALID,
        "FD 梯度门不符合 M2 冻结合同（" + str(relpath) + "）：" + str(message),
    )


def _fd_gate_number(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        S3_PREREG_ARTIFACT_INVALID,
        "FD 梯度门字段必须是数值: " + str(label),
    )
    number = float(value)
    _require(math.isfinite(number), S3_PREREG_ARTIFACT_INVALID, "FD 梯度门数值非有限: " + str(label))
    return number


def _validate_fd_gate_payload(payload: Any, *, relpath: str = S3_GATE_RELPATH) -> Mapping[str, Any]:
    """校验 M2 冻结 FD 门文件结构（fail-closed；不重算梯度，只做结构/数值边界）。"""
    if not isinstance(payload, Mapping):
        _fd_gate_error("必须是 JSON object", relpath=relpath)
    if payload.get("schema_version") != S3_FD_GATE_SCHEMA_VERSION:
        _fd_gate_error("schema_version 必须为 " + S3_FD_GATE_SCHEMA_VERSION, relpath=relpath)
    if str(payload.get("status")) != "PASS":
        _fd_gate_error("status 必须为 PASS", relpath=relpath)
    if int(payload.get("physical_call_count", -1)) != 0:
        _fd_gate_error("physical_call_count 必须为 0", relpath=relpath)
    if abs(_fd_gate_number(payload.get("tolerance"), "tolerance") - float(S3_FD_TOLERANCE)) > 0.0:
        _fd_gate_error("tolerance 必须为 " + repr(S3_FD_TOLERANCE), relpath=relpath)
    if str(payload.get("epsilon_rule")) != S3_FD_EPSILON_RULE:
        _fd_gate_error("epsilon_rule 必须为 " + S3_FD_EPSILON_RULE, relpath=relpath)
    per_model = int(payload.get("coordinates_per_model", -1))
    if per_model != int(S3_FD_GATE_COORDINATES_PER_MODEL):
        _fd_gate_error("coordinates_per_model 必须为 " + str(S3_FD_GATE_COORDINATES_PER_MODEL), relpath=relpath)
    if int(payload.get("coordinates_total", -1)) != per_model * len(S3_FD_GATE_MODEL_KEYS):
        _fd_gate_error("coordinates_total 必须为 " + str(per_model * len(S3_FD_GATE_MODEL_KEYS)), relpath=relpath)
    models = payload.get("models")
    if not isinstance(models, Mapping) or set(models) != set(S3_FD_GATE_MODEL_KEYS):
        _fd_gate_error("models 键必须恰为 " + repr(S3_FD_GATE_MODEL_KEYS), relpath=relpath)
    overall = 0.0
    for key in S3_FD_GATE_MODEL_KEYS:
        block = models[key]
        if not isinstance(block, Mapping):
            _fd_gate_error("models." + key + " 必须是 mapping", relpath=relpath)
        if str(block.get("status")) != "PASS":
            _fd_gate_error("models." + key + ".status 必须为 PASS", relpath=relpath)
        if str(block.get("arm_type")) not in S3_MODEL_KINDS:
            _fd_gate_error("models." + key + ".arm_type 非法", relpath=relpath)
        n_checked = int(block.get("n_checked", -1))
        if n_checked != per_model:
            _fd_gate_error("models." + key + ".n_checked 必须为 " + str(per_model), relpath=relpath)
        coordinates = block.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != n_checked:
            _fd_gate_error("models." + key + ".coordinates 长度必须为 " + str(n_checked), relpath=relpath)
        block_max = 0.0
        for item in coordinates:
            if not isinstance(item, Mapping):
                _fd_gate_error("coordinates 条目必须是 mapping", relpath=relpath)
            if not {"index", "param", "analytic", "numeric", "relative_error"} <= set(item):
                _fd_gate_error("coordinates 条目缺少必需键", relpath=relpath)
            relative = abs(_fd_gate_number(item.get("relative_error"), "relative_error"))
            if relative > float(S3_FD_TOLERANCE):
                _fd_gate_error("坐标相对误差超过 tolerance", relpath=relpath)
            block_max = max(block_max, relative)
        if abs(_fd_gate_number(block.get("max_relative_error"), "max_relative_error") - block_max) > 1e-15:
            _fd_gate_error("models." + key + ".max_relative_error 与坐标实算不一致", relpath=relpath)
        overall = max(overall, block_max)
    if abs(_fd_gate_number(payload.get("max_relative_error"), "max_relative_error") - overall) > 1e-15:
        _fd_gate_error("顶层 max_relative_error 与坐标实算不一致", relpath=relpath)
    negatives = payload.get("negatives")
    if not isinstance(negatives, Mapping) or set(negatives) != set(S3_FD_GATE_NEGATIVE_KEYS):
        _fd_gate_error("negatives 键必须恰为 " + repr(S3_FD_GATE_NEGATIVE_KEYS), relpath=relpath)
    for key in S3_FD_GATE_NEGATIVE_KEYS:
        if str(negatives[key]) != "PASS":
            _fd_gate_error("negatives." + key + " 必须为 PASS", relpath=relpath)
    return payload


def frozen_fd_gate_info(repo_root: str | Path | None = None) -> dict[str, Any]:
    """读取并校验 M2 冻结 FD 门（Q2）；缺失/结构不符 → S3_PREREG_ARTIFACT_INVALID。"""
    root = _repo_root_or_default(repo_root)
    path = root / S3_GATE_RELPATH
    _require(path.is_file(), S3_PREREG_ARTIFACT_INVALID, "缺少 M2 冻结 FD 梯度门: " + S3_GATE_RELPATH)
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S3PreregError(
            S3_PREREG_ARTIFACT_INVALID,
            "FD 梯度门不是合法 UTF-8 JSON: " + str(exc),
        ) from exc
    data = path.read_bytes()
    _validate_fd_gate_payload(payload)
    return {"path": S3_GATE_RELPATH, "sha256": sha256_bytes(data), "bytes": len(data), "payload": payload}
