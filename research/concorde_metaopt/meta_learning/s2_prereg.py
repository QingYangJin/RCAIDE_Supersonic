"""S2 预注册（prereg）构建与校验（S2 计划 §7）。

- canonical JSON：json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"；
- prereg_id：同时剔除 prereg_id/prereg_digest 后对 canonical 文本做 sha256，取前 16 hex，前缀 "p4ra-s2-prereg-"；
- prereg_digest：仅剔除 prereg_digest 后对 canonical 文本做 sha256（此时 prereg_id 已固定）；
- code_sha：按路径 Python sorted() 字典序，逐文件 path + "\n" + sha256(raw).hexdigest() + "\n" 拼接后 sha256；
- analysis_plan_digest：对 endpoints/comparison/statistical_plan/fd_gate 四节构成的 canonical JSON 做 sha256；
- 所有失败 fail-closed 并抛 S2PreregError，错误码写在消息前缀。

本模块零物理调用（不 import/调用任何求解器），只做文档、JSON、文件与哈希运算。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "p4ra-s2-prereg-v1"
PREREG_ID_PREFIX = "p4ra-s2-prereg-"
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PACKAGE_PATH = "research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z"
DEFAULT_PILOT_ARTIFACTS = {
    "micro": "research/concorde_metaopt/evidence/s2/s2_fd_pilot_micro.json",
    "full_size": "research/concorde_metaopt/evidence/s2/s2_fd_pilot_full.json",
}
CODE_SHA_FILES = (
    "research/concorde_metaopt/meta_learning/maml.py",
    "research/concorde_metaopt/meta_learning/s2_prereg.py",
    "research/concorde_metaopt/meta_learning/s2_runner.py",
)
ALLOWED_SPLITS = ("meta_train", "meta_validation")
FORBIDDEN_SPLITS = ("meta_test", "meta_test_ood", "negative_control")
EXPECTED_SPLIT_COUNTS = {
    "meta_train": 60,
    "meta_validation": 20,
    "meta_test": 20,
    "meta_test_ood": 10,
    "negative_control": 10,
}
EXPECTED_SUMS_ENTRIES = 9
PACKAGE_FAMILY_VERSION = "p4ra-family-v4"
TASK_FAMILY_VERSION = "p4ra-family-v3"
SEED_SCOPES = (
    "S2-train-support",
    "S2-train-query",
    "S2-train-order",
    "S2-eval-support",
    "S2-eval-query",
)
BASE_ARM_CONFIG = {
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
ARM_SPECS = (
    {"id": "FULL_MAML", "first_order": False},
    {"id": "FOMAML", "first_order": True},
)
TRAINING_BUDGET = {"outer_steps": 200, "meta_seeds": [0, 1, 2], "train_records_expected": 1200}
EVALUATION_GRID = {"meta_validation_tasks": 20, "K": [0, 1, 5, 10], "draws": 10, "eval_records_expected": 4800}
# v1.5 §7：固定资源上限（int，供 verify 机械核验并纳入 prereg_digest）
RESOURCE_LIMITS = {"per_seed_train_wall_s": 1200, "peak_memory_mb": 8192, "total_wall_s": 7200}
ENDPOINTS = {
    "primary": {"id": "post_adaptation_rmse_raw_k5", "direction": "lower_is_better", "K": 5, "space": "raw"},
    "secondary_inferential": [
        {"id": "post_adaptation_rmse_raw_k10", "direction": "lower_is_better", "K": 10, "space": "raw"}
    ],
    "descriptive": [
        "post_adaptation_rmse_raw_k0",
        "post_adaptation_rmse_raw_k1",
        "post_adaptation_rmse_std_k5",
        "post_adaptation_rmse_std_k10",
        "post_adaptation_mae_raw_k5",
        "train_wall_seconds_ratio",
        "peak_memory_mb",
    ],
}
COMPARISON = {
    "id": "C1",
    "arms": ["FULL_MAML", "FOMAML"],
    "difference": "FULL_MAML - FOMAML",
    "unit": "task",
    "aggregation": "mean over 3 meta_seeds x 10 draws per task",
}
STATISTICAL_PLAN = {
    "test": "wilcoxon_signed_rank_two_sided",
    "n_tasks": 20,
    "bootstrap": {"n_resamples": 10000, "seed": 20261105, "ci": 0.95},
    "multiple_comparison": {
        "family_id": "s2-primary-secondary-2tests",
        "family_key": "s2_primary_secondary",
        "method": "holm",
        "family_size": 2,
        "members": [
            {"comparison": "C1", "endpoint": "post_adaptation_rmse_raw_k5"},
            {"comparison": "C1", "endpoint": "post_adaptation_rmse_raw_k10"},
        ],
    },
    "decision_rules": {
        "benefit": "holm_p<0.05 and ci_excludes_zero and full<fomaml and relative_improvement>=0.01",
        "harm": "symmetric",
        "inconclusive": "null_rate>0.70",
        "else": "NO_EVIDENCE",
    },
    "evidence_scope": "DEVELOPMENT_VALIDATION_ONLY",
}
EPISODE_CONTRACT = {
    "train_support": 16,
    "train_query": 32,
    "eval_K": [0, 1, 5, 10],
    "eval_draws": 10,
    "eval_query": 64,
    "seed_scopes": list(SEED_SCOPES),
    "standardization": "raw_primary; standardized descriptive for K>=2 with support std>=1e-8 else null",
}
DETERMINISM = {
    "reruns": 2,
    "requires_byte_identical": ["train_episode_bank_manifest", "run_config", "run_records_core"],
    "fail_closed": True,
}
FAILURE_RULES = [
    "nonfinite_loss_or_grad -> arm/seed FAILED, stop, no retry",
    "resource_limit(per_seed_train_wall_s>1200 or peak_memory_mb>8192) -> RESOURCE_LIMIT, stop entire run, no retry",
    "any seed failed -> arm DEGRADED and primary INCONCLUSIVE",
]
STOPPING_RULES = [
    "stop_on_nonfinite",
    "stop_on_data_boundary_violation",
    "stop_on_fd_gate_failure",
    "stop_on_code_sha_mismatch",
    "total_wall_s>7200 -> stop, report partial products",
]
UPSTREAM = {"issue": "#7", "decision": "D-P4-003", "stage": "S2", "s1_receipt_comment_id": 6684142041}

# 错误码（写入异常消息前缀，供上层 fail-closed 判断）
S2_PREREG_DIGEST_MISMATCH = "S2_PREREG_DIGEST_MISMATCH"
S2_PREREG_PLACEHOLDER_REJECTED = "S2_PREREG_PLACEHOLDER_REJECTED"
S2_PREREG_SCHEMA_ERROR = "S2_PREREG_SCHEMA_ERROR"
S2_ARM_CONFIG_MISMATCH = "S2_ARM_CONFIG_MISMATCH"
S2_CODE_SHA_MISMATCH = "S2_CODE_SHA_MISMATCH"
S2_FROZEN_PACKAGE_MISMATCH = "S2_FROZEN_PACKAGE_MISMATCH"
S2_PILOT_ARTIFACT_INVALID = "S2_PILOT_ARTIFACT_INVALID"
S2_DATA_BOUNDARY_ERROR = "S2_DATA_BOUNDARY_ERROR"
S2_PREREG_RESOURCE_LIMITS_INVALID = "S2_PREREG_RESOURCE_LIMITS_INVALID"
S2_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_STRINGS = {"TBD", "TODO", "PENDING", "PLACEHOLDER", "REPLACE_ME"}
PLACEHOLDER_BRACKET_RE = re.compile(r"^<.*>$")


class S2PreregError(RuntimeError):
    """S2 prereg 构建/校验错误（fail-closed）。"""


# -- canonical JSON 与哈希 ---------------------------------------------------


def canonical_json(value: Any) -> str:
    """canonical JSON 文本（不含末尾换行）。"""
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise S2PreregError(f"{S2_PREREG_SCHEMA_ERROR}: 无法 canonical 序列化: {type(exc).__name__}: {exc}") from exc


def canonical_json_line(value: Any) -> str:
    """canonical JSON 文本 + 末尾换行（落盘与摘要输入均用此形态）。"""
    return canonical_json(value) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_sha256(value: Any) -> str:
    """canonical JSON + 末尾换行 的 sha256。"""
    return sha256_text(canonical_json_line(value))


def ids_sha256(ids: Iterable[str]) -> str:
    """task_id 集合摘要：sorted(ids) 以 "\n" join + 末尾 "\n" 后 sha256。"""
    values = [str(value) for value in ids]
    return sha256_text("\n".join(sorted(values)) + "\n")


def code_sha_for_files(paths: Sequence[str], repo_root: Path | str) -> str:
    """§7 code_sha 算法：sorted(paths) 逐文件 path+"\n"+sha256(raw).hexdigest()+"\n" 拼接后 sha256。"""
    root = Path(repo_root)
    digest = hashlib.sha256()
    for relative in sorted(str(path) for path in paths):
        file_path = root / relative
        if not file_path.is_file():
            raise S2PreregError(f"{S2_CODE_SHA_MISMATCH}: 缺少 code_sha 文件 {relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\n")
        digest.update(sha256_bytes(file_path.read_bytes()).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def compute_code_sha(repo_root: Path | str | None = None) -> str:
    """当前工作树的 code_sha（maml.py + s2_prereg.py + s2_runner.py）。"""
    root = DEFAULT_REPO_ROOT if repo_root is None else Path(repo_root)
    return code_sha_for_files(CODE_SHA_FILES, root)


def analysis_plan_digest(prereg: Mapping[str, Any]) -> str:
    """§7：对 endpoints/comparison/statistical_plan/fd_gate 四节做 canonical sha256。"""
    sections = {
        "endpoints": prereg.get("endpoints"),
        "comparison": prereg.get("comparison"),
        "statistical_plan": prereg.get("statistical_plan"),
        "fd_gate": prereg.get("fd_gate"),
    }
    return canonical_sha256(sections)


def compute_prereg_id(prereg: Mapping[str, Any]) -> str:
    base = {key: value for key, value in prereg.items() if key not in ("prereg_id", "prereg_digest")}
    return PREREG_ID_PREFIX + sha256_text(canonical_json_line(base))[:16]


def compute_prereg_digest(prereg: Mapping[str, Any]) -> str:
    base = {key: value for key, value in prereg.items() if key != "prereg_digest"}
    return sha256_text(canonical_json_line(base))


# -- 占位与结构检查 ----------------------------------------------------------


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_strings(item)


def find_placeholders(value: Any) -> list[str]:
    found: list[str] = []
    for text in iter_strings(value):
        stripped = text.strip()
        if stripped in PLACEHOLDER_STRINGS or PLACEHOLDER_BRACKET_RE.match(stripped):
            found.append(text)
    return found


def reject_placeholders(value: Any) -> None:
    found = find_placeholders(value)
    if found:
        raise S2PreregError(f"{S2_PREREG_PLACEHOLDER_REJECTED}: 发现占位符 {found[:5]}")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise S2PreregError(f"{code}: {message}")


def _require_hex64(value: Any, code: str, label: str) -> str:
    _require(isinstance(value, str) and bool(S2_HEX64_RE.match(value)), code, f"{label} 必须是 64 位小写 hex，实际 {value!r}")
    return value


# -- 冻结包检查 --------------------------------------------------------------


def parse_sha256sums(text: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        _require(len(parts) == 2, S2_FROZEN_PACKAGE_MISMATCH, f"SHA256SUMS 行格式非法: {line!r}")
        digest, name = parts[0].strip().lower(), parts[1].strip()
        if name.startswith("*"):
            name = name[1:]
        _require(bool(S2_HEX64_RE.match(digest)), S2_FROZEN_PACKAGE_MISMATCH, f"SHA256SUMS 摘要非法: {line!r}")
        entries.append((name, digest))
    return entries


def inspect_frozen_package(package_dir: Path | str) -> dict[str, Any]:
    """只读校验 S0-7 冻结包（SHA256SUMS 9/9 + tasks.json 划分 + freeze_summary 身份）。"""
    package = Path(package_dir)
    _require(package.is_dir(), S2_FROZEN_PACKAGE_MISMATCH, f"冻结包目录不存在: {package}")
    sums_path = package / "SHA256SUMS.txt"
    _require(sums_path.is_file(), S2_FROZEN_PACKAGE_MISMATCH, "冻结包缺少 SHA256SUMS.txt")
    raw_sums = sums_path.read_bytes()
    sha256sums_sha256 = sha256_bytes(raw_sums)
    entries = parse_sha256sums(raw_sums.decode("utf-8"))
    _require(
        len(entries) == EXPECTED_SUMS_ENTRIES,
        S2_FROZEN_PACKAGE_MISMATCH,
        f"SHA256SUMS 条目数应为 {EXPECTED_SUMS_ENTRIES}，实际 {len(entries)}",
    )
    for name, expected in entries:
        file_path = package / name
        _require(file_path.is_file(), S2_FROZEN_PACKAGE_MISMATCH, f"冻结包缺少 {name}")
        actual = sha256_file(file_path)
        _require(actual == expected, S2_FROZEN_PACKAGE_MISMATCH, f"{name} 摘要不匹配: 期望 {expected} 实际 {actual}")
    tasks_payload = json.loads((package / "tasks.json").read_text(encoding="utf-8"))
    _require(isinstance(tasks_payload, list) and tasks_payload, S2_FROZEN_PACKAGE_MISMATCH, "tasks.json 必须是非空数组")
    split_counts: dict[str, int] = {}
    task_ids: dict[str, list[str]] = {}
    task_family_versions: set[str] = set()
    for record in tasks_payload:
        _require(isinstance(record, Mapping), S2_FROZEN_PACKAGE_MISMATCH, "tasks.json 记录必须是对象")
        task_id = record.get("task_id")
        split = record.get("split")
        _require(isinstance(task_id, str) and task_id, S2_FROZEN_PACKAGE_MISMATCH, "tasks.json 记录缺少 task_id")
        _require(isinstance(split, str) and split, S2_FROZEN_PACKAGE_MISMATCH, "tasks.json 记录缺少 split")
        record_family_version = record.get("family_version")
        _require(
            isinstance(record_family_version, str) and record_family_version,
            S2_FROZEN_PACKAGE_MISMATCH,
            "tasks.json 记录缺少 family_version",
        )
        task_family_versions.add(record_family_version)
        split_counts[split] = split_counts.get(split, 0) + 1
        task_ids.setdefault(split, []).append(task_id)
    _require(
        task_family_versions == {TASK_FAMILY_VERSION},
        S2_FROZEN_PACKAGE_MISMATCH,
        f"tasks.json family_version 不唯一或非期望值: {sorted(task_family_versions)}",
    )
    _require(
        dict(sorted(split_counts.items())) == dict(sorted(EXPECTED_SPLIT_COUNTS.items())),
        S2_FROZEN_PACKAGE_MISMATCH,
        f"split 计数不匹配: 期望 {EXPECTED_SPLIT_COUNTS} 实际 {split_counts}",
    )
    summary_path = package / "freeze_summary.json"
    _require(summary_path.is_file(), S2_FROZEN_PACKAGE_MISMATCH, "冻结包缺少 freeze_summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    _require(
        str(summary.get("family_version")) == PACKAGE_FAMILY_VERSION,
        S2_FROZEN_PACKAGE_MISMATCH,
        f"冻结包 family_version 应为 {PACKAGE_FAMILY_VERSION}，实际 {summary.get('family_version')!r}",
    )
    return {
        "package_dir": package,
        "sha256sums_sha256": sha256sums_sha256,
        "split_counts": dict(sorted(split_counts.items())),
        "task_ids": {split: sorted(ids) for split, ids in task_ids.items()},
        "run_id": summary.get("run_id"),
        "code_sha": summary.get("code_sha"),
        "git_sha": summary.get("git_sha"),
        "package_family_version": PACKAGE_FAMILY_VERSION,
        "task_family_version": TASK_FAMILY_VERSION,
        "physical_call_count": summary.get("physical_call_count"),
    }


# -- 构建 --------------------------------------------------------------------


def _pilot_artifact_entries(
    repo_root: Path, pilot_paths: Mapping[str, str] | None
) -> dict[str, dict[str, str]]:
    paths = dict(DEFAULT_PILOT_ARTIFACTS if pilot_paths is None else pilot_paths)
    entries: dict[str, dict[str, str]] = {}
    root_resolved = repo_root.resolve()
    for name in ("micro", "full_size"):
        _require(name in paths, S2_PILOT_ARTIFACT_INVALID, f"pilot_artifacts 缺少 {name}")
        relative = Path(str(paths[name]))
        _require(not relative.is_absolute(), S2_PILOT_ARTIFACT_INVALID, f"pilot 路径必须是仓库根相对路径，实际 {relative}")
        resolved = (root_resolved / relative).resolve()
        _require(
            resolved == root_resolved or root_resolved in resolved.parents,
            S2_PILOT_ARTIFACT_INVALID,
            f"pilot 路径逃逸仓库根: {relative} -> {resolved}",
        )
        _require(resolved.is_file(), S2_PILOT_ARTIFACT_INVALID, f"pilot 文件不存在: {relative}")
        entries[name] = {"path": relative.as_posix(), "sha256": sha256_file(resolved)}
    return entries


def build_preregistration(
    *,
    repo_root: Path | str | None = None,
    package_path: str | None = None,
    created_utc: str | None = None,
    code_sha: str | None = None,
    train_episode_bank_sha256: str,
    pilot_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """构建完整 prereg payload（已含自洽的 prereg_id/prereg_digest）。

    所有输入来自仓库内既有冻结产物/代码与调用方提供的 bank 摘要；不做任何物理计算。
    """
    root = DEFAULT_REPO_ROOT if repo_root is None else Path(repo_root)
    relative_package = DEFAULT_PACKAGE_PATH if package_path is None else str(package_path)
    package = (root / relative_package).resolve()
    _require(
        package == root.resolve() or root.resolve() in package.parents,
        S2_FROZEN_PACKAGE_MISMATCH,
        f"冻结包路径逃逸仓库根: {relative_package}",
    )
    frozen = inspect_frozen_package(package)
    _require_hex64(train_episode_bank_sha256, S2_PREREG_SCHEMA_ERROR, "train_episode_bank_sha256")
    actual_created = (
        datetime.now(timezone.utc).isoformat(timespec="seconds") if created_utc is None else str(created_utc)
    )
    actual_code_sha = compute_code_sha(root) if code_sha is None else _require_hex64(code_sha, S2_CODE_SHA_MISMATCH, "code_sha")
    task_ids = frozen["task_ids"]
    holdout_ids: list[str] = []
    for split in FORBIDDEN_SPLITS:
        holdout_ids.extend(task_ids[split])
    pilot_artifacts = _pilot_artifact_entries(root, pilot_paths)
    prereg: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": actual_created,
        "upstream": dict(UPSTREAM),
        "frozen_package": {
            "run_id": frozen["run_id"],
            "package_path": relative_package,
            "sha256sums_sha256": frozen["sha256sums_sha256"],
            "code_sha": frozen["code_sha"],
            "git_sha": frozen["git_sha"],
            "package_family_version": frozen["package_family_version"],
            "task_family_version": frozen["task_family_version"],
        },
        "data_boundary": {
            "allowed_splits": list(ALLOWED_SPLITS),
            "forbidden_splits": list(FORBIDDEN_SPLITS),
            "split_counts": dict(frozen["split_counts"]),
            "meta_train_task_ids_sha256": ids_sha256(task_ids["meta_train"]),
            "meta_validation_task_ids_sha256": ids_sha256(task_ids["meta_validation"]),
            "holdout_task_ids_sha256": ids_sha256(holdout_ids),
            "holdout_rows_used": 0,
        },
        "episode_contract": {**EPISODE_CONTRACT, "train_episode_bank_sha256": train_episode_bank_sha256},
        "arms": [
            {"id": spec["id"], "first_order": spec["first_order"], "config": dict(BASE_ARM_CONFIG)}
            for spec in ARM_SPECS
        ],
        "training_budget": dict(TRAINING_BUDGET),
        "evaluation_grid": dict(EVALUATION_GRID),
        "resource_limits": dict(RESOURCE_LIMITS),
        "endpoints": json.loads(json.dumps(ENDPOINTS)),
        "comparison": json.loads(json.dumps(COMPARISON)),
        "statistical_plan": json.loads(json.dumps(STATISTICAL_PLAN)),
        "fd_gate": {
            "mode": "full",
            "max_relative_error": 1e-6,
            "coordinates": 32,
            "epsilon": "1e-6 * max(1, |theta_j|)",
            "denominator": "max(|numeric|, |analytic|, 1e-12)",
            "fail_closed": True,
            "pilot_artifacts": pilot_artifacts,
        },
        "determinism": json.loads(json.dumps(DETERMINISM)),
        "failure_rules": list(FAILURE_RULES),
        "stopping_rules": list(STOPPING_RULES),
        "physical_call_count": 0,
    }
    prereg["code_sha"] = actual_code_sha
    prereg["analysis_plan_digest"] = analysis_plan_digest(prereg)
    prereg["prereg_id"] = compute_prereg_id(prereg)
    prereg["prereg_digest"] = compute_prereg_digest(prereg)
    return prereg


# -- 校验 --------------------------------------------------------------------


REQUIRED_TOP_KEYS = (
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
    "resource_limits",
    "endpoints",
    "comparison",
    "statistical_plan",
    "fd_gate",
    "determinism",
    "failure_rules",
    "stopping_rules",
    "code_sha",
    "analysis_plan_digest",
    "physical_call_count",
    "prereg_digest",
)


FROZEN_PACKAGE_KEYS = (
    "run_id",
    "package_path",
    "sha256sums_sha256",
    "code_sha",
    "git_sha",
    "package_family_version",
    "task_family_version",
)


def _require_mapping(value: Any, code: str, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), code, f"{label} 必须是对象")
    return value


def _require_exact(value: Any, expected: Any, code: str, label: str) -> None:
    _require(value == expected, code, f"{label} 应为 {expected!r}，实际 {value!r}")


def _check_arm_fairness(arms: Any) -> None:
    _require(isinstance(arms, list) and len(arms) == 2, S2_ARM_CONFIG_MISMATCH, "arms 必须恰为 2 个")
    by_id: dict[str, Mapping[str, Any]] = {}
    for arm in arms:
        arm = _require_mapping(arm, S2_ARM_CONFIG_MISMATCH, "arm")
        _require(arm.get("id") in ("FULL_MAML", "FOMAML"), S2_ARM_CONFIG_MISMATCH, f"非法 arm id {arm.get('id')!r}")
        by_id[str(arm["id"])] = arm
    _require(set(by_id) == {"FULL_MAML", "FOMAML"}, S2_ARM_CONFIG_MISMATCH, "arms 必须恰为 FULL_MAML 与 FOMAML")
    _require_exact(by_id["FULL_MAML"].get("first_order"), False, S2_ARM_CONFIG_MISMATCH, "FULL_MAML.first_order")
    _require_exact(by_id["FOMAML"].get("first_order"), True, S2_ARM_CONFIG_MISMATCH, "FOMAML.first_order")
    configs = [dict(by_id["FULL_MAML"].get("config") or {}), dict(by_id["FOMAML"].get("config") or {})]
    _require(configs[0] == configs[1], S2_ARM_CONFIG_MISMATCH, "两臂 config 除 first_order 外层必须逐字段相同")
    _require_exact(configs[0], BASE_ARM_CONFIG, S2_ARM_CONFIG_MISMATCH, "arm config")
    _require_exact(by_id["FULL_MAML"].get("first_order"), False, S2_ARM_CONFIG_MISMATCH, "FULL_MAML.first_order")


def _check_resource_limits(value: Any) -> None:
    """v1.5 §7：resource_limits 必须恰为固定键集合与 int 数值，且纳入 digest 覆盖范围。"""
    code = S2_PREREG_RESOURCE_LIMITS_INVALID
    limits = _require_mapping(value, code, "resource_limits")
    _require(
        set(limits) == set(RESOURCE_LIMITS),
        code,
        f"resource_limits 键集合应为 {sorted(RESOURCE_LIMITS)}，实际 {sorted(limits)}",
    )
    for key, expected in RESOURCE_LIMITS.items():
        actual = limits[key]
        _require(type(actual) is int, code, f"resource_limits.{key} 必须是 int，实际 {type(actual).__name__}={actual!r}")
        _require(actual == expected, code, f"resource_limits.{key} 应为 {expected}，实际 {actual}")


def _check_fd_gate(fd_gate: Any, repo_root: Path) -> None:
    gate = _require_mapping(fd_gate, S2_PREREG_SCHEMA_ERROR, "fd_gate")
    _require_exact(gate.get("mode"), "full", S2_PREREG_SCHEMA_ERROR, "fd_gate.mode")
    _require_exact(gate.get("max_relative_error"), 1e-6, S2_PREREG_SCHEMA_ERROR, "fd_gate.max_relative_error")
    _require_exact(gate.get("coordinates"), 32, S2_PREREG_SCHEMA_ERROR, "fd_gate.coordinates")
    _require_exact(gate.get("epsilon"), "1e-6 * max(1, |theta_j|)", S2_PREREG_SCHEMA_ERROR, "fd_gate.epsilon")
    _require_exact(gate.get("denominator"), "max(|numeric|, |analytic|, 1e-12)", S2_PREREG_SCHEMA_ERROR, "fd_gate.denominator")
    _require_exact(gate.get("fail_closed"), True, S2_PREREG_SCHEMA_ERROR, "fd_gate.fail_closed")
    artifacts = _require_mapping(gate.get("pilot_artifacts"), S2_PILOT_ARTIFACT_INVALID, "fd_gate.pilot_artifacts")
    _require(set(artifacts) == {"micro", "full_size"}, S2_PILOT_ARTIFACT_INVALID, "pilot_artifacts 必须含 micro/full_size")
    root_resolved = (repo_root if repo_root.is_absolute() else repo_root.resolve()).resolve()
    for name, entry in artifacts.items():
        entry = _require_mapping(entry, S2_PILOT_ARTIFACT_INVALID, f"pilot_artifacts.{name}")
        _require(set(entry) == {"path", "sha256"}, S2_PILOT_ARTIFACT_INVALID, f"pilot_artifacts.{name} 必须恰含 path/sha256")
        relative = Path(str(entry["path"]))
        _require(not relative.is_absolute(), S2_PILOT_ARTIFACT_INVALID, f"pilot 路径不得为绝对路径: {relative}")
        resolved = (root_resolved / relative).resolve()
        _require(
            resolved == root_resolved or root_resolved in resolved.parents,
            S2_PILOT_ARTIFACT_INVALID,
            f"pilot 路径逃逸仓库根: {relative}",
        )
        _require(resolved.is_file(), S2_PILOT_ARTIFACT_INVALID, f"pilot 文件不存在: {relative}")
        _require_hex64(str(entry["sha256"]), S2_PILOT_ARTIFACT_INVALID, f"pilot_artifacts.{name}.sha256")
        actual = sha256_file(resolved)
        _require(actual == entry["sha256"], S2_PILOT_ARTIFACT_INVALID, f"pilot sha 不匹配: {relative} 期望 {entry['sha256']} 实际 {actual}")


def verify_preregistration(
    prereg: Any,
    *,
    repo_root: Path | str | None = None,
    expected_code_sha: str | None = None,
    verify_code_sha: bool = True,
    verify_frozen_package: bool = True,
) -> bool:
    """完整核验 prereg；任何不一致抛 S2PreregError（fail-closed），全部通过返回 True。"""
    root = DEFAULT_REPO_ROOT if repo_root is None else Path(repo_root)
    payload = _require_mapping(prereg, S2_PREREG_SCHEMA_ERROR, "prereg")
    reject_placeholders(payload)
    for key in REQUIRED_TOP_KEYS:
        _require(key in payload, S2_PREREG_SCHEMA_ERROR, f"缺少必填字段 {key}")
    _require_exact(payload.get("schema_version"), SCHEMA_VERSION, S2_PREREG_SCHEMA_ERROR, "schema_version")
    # 1) 文本字段非空
    for key in ("prereg_id", "created_utc", "code_sha", "analysis_plan_digest", "prereg_digest"):
        value = payload.get(key)
        _require(isinstance(value, str) and value, S2_PREREG_SCHEMA_ERROR, f"{key} 不得为空")
    _require(str(payload["prereg_id"]).startswith(PREREG_ID_PREFIX), S2_PREREG_SCHEMA_ERROR, "prereg_id 前缀非法")
    _require(bool(re.fullmatch(PREREG_ID_PREFIX + r"[0-9a-f]{16}", str(payload["prereg_id"]))), S2_PREREG_SCHEMA_ERROR, "prereg_id 格式非法")
    _require_hex64(str(payload["prereg_digest"]), S2_PREREG_DIGEST_MISMATCH, "prereg_digest")
    # 2) 摘要去循环复算
    expected_id = compute_prereg_id(payload)
    _require(expected_id == payload["prereg_id"], S2_PREREG_DIGEST_MISMATCH, f"prereg_id 复算不匹配: 期望 {expected_id} 实际 {payload['prereg_id']}")
    expected_digest = compute_prereg_digest(payload)
    _require(expected_digest == payload["prereg_digest"], S2_PREREG_DIGEST_MISMATCH, f"prereg_digest 复算不匹配: 期望 {expected_digest} 实际 {payload['prereg_digest']}")
    # 3) 固定节
    _require_exact(payload.get("upstream"), UPSTREAM, S2_PREREG_SCHEMA_ERROR, "upstream")
    _require_exact(payload.get("physical_call_count"), 0, S2_PREREG_SCHEMA_ERROR, "physical_call_count")
    _require_exact(payload.get("training_budget"), TRAINING_BUDGET, S2_PREREG_SCHEMA_ERROR, "training_budget")
    _require_exact(payload.get("evaluation_grid"), EVALUATION_GRID, S2_PREREG_SCHEMA_ERROR, "evaluation_grid")
    _require_exact(payload.get("endpoints"), ENDPOINTS, S2_PREREG_SCHEMA_ERROR, "endpoints")
    _require_exact(payload.get("comparison"), COMPARISON, S2_PREREG_SCHEMA_ERROR, "comparison")
    _require_exact(payload.get("statistical_plan"), STATISTICAL_PLAN, S2_PREREG_SCHEMA_ERROR, "statistical_plan")
    _require_exact(payload.get("determinism"), DETERMINISM, S2_PREREG_SCHEMA_ERROR, "determinism")
    _check_resource_limits(payload.get("resource_limits"))
    _require_exact(payload.get("failure_rules"), FAILURE_RULES, S2_PREREG_SCHEMA_ERROR, "failure_rules")
    _require_exact(payload.get("stopping_rules"), STOPPING_RULES, S2_PREREG_SCHEMA_ERROR, "stopping_rules")
    episode_contract = _require_mapping(payload.get("episode_contract"), S2_PREREG_SCHEMA_ERROR, "episode_contract")
    contract_body = {key: value for key, value in episode_contract.items() if key != "train_episode_bank_sha256"}
    _require_exact(contract_body, EPISODE_CONTRACT, S2_PREREG_SCHEMA_ERROR, "episode_contract")
    _require_hex64(str(episode_contract.get("train_episode_bank_sha256")), S2_PREREG_SCHEMA_ERROR, "episode_contract.train_episode_bank_sha256")
    _check_arm_fairness(payload.get("arms"))
    _check_fd_gate(payload.get("fd_gate"), root)
    # 4) code_sha / analysis_plan_digest
    _require_hex64(str(payload["code_sha"]), S2_CODE_SHA_MISMATCH, "code_sha")
    if expected_code_sha is not None:
        _require(str(payload["code_sha"]) == expected_code_sha, S2_CODE_SHA_MISMATCH, f"code_sha 与期望不一致: 期望 {expected_code_sha} 实际 {payload['code_sha']}")
    if verify_code_sha:
        current_code_sha = compute_code_sha(root)
        _require(str(payload["code_sha"]) == current_code_sha, S2_CODE_SHA_MISMATCH, f"code_sha 与当前工作树不一致: prereg {payload['code_sha']} 当前 {current_code_sha}")
    expected_plan_digest = analysis_plan_digest(payload)
    _require(str(payload["analysis_plan_digest"]) == expected_plan_digest, S2_PREREG_DIGEST_MISMATCH, f"analysis_plan_digest 复算不匹配: 期望 {expected_plan_digest} 实际 {payload['analysis_plan_digest']}")
    # 5) 冻结包身份与数据边界
    frozen = _require_mapping(payload.get("frozen_package"), S2_FROZEN_PACKAGE_MISMATCH, "frozen_package")
    _require(
        set(frozen) == set(FROZEN_PACKAGE_KEYS),
        S2_FROZEN_PACKAGE_MISMATCH,
        f"frozen_package 键应为 {sorted(FROZEN_PACKAGE_KEYS)}，实际 {sorted(frozen)}",
    )
    relative_package = str(frozen.get("package_path") or "")
    _require(bool(relative_package), S2_FROZEN_PACKAGE_MISMATCH, "frozen_package.package_path 不得为空")
    package = (root / relative_package).resolve()
    _require(package == root.resolve() or root.resolve() in package.parents, S2_FROZEN_PACKAGE_MISMATCH, "package_path 逃逸仓库根")
    if verify_frozen_package:
        actual = inspect_frozen_package(package)
        _require(str(frozen.get("sha256sums_sha256")) == actual["sha256sums_sha256"], S2_FROZEN_PACKAGE_MISMATCH, f"sha256sums_sha256 不匹配: 期望 {actual['sha256sums_sha256']} 实际 {frozen.get('sha256sums_sha256')}")
        _require(str(frozen.get("code_sha")) == str(actual["code_sha"]), S2_FROZEN_PACKAGE_MISMATCH, "frozen_package.code_sha 不匹配")
        _require(str(frozen.get("git_sha")) == str(actual["git_sha"]), S2_FROZEN_PACKAGE_MISMATCH, "frozen_package.git_sha 不匹配")
        _require(
            str(frozen.get("package_family_version")) == str(actual["package_family_version"]),
            S2_FROZEN_PACKAGE_MISMATCH,
            "frozen_package.package_family_version 不匹配",
        )
        _require(
            str(frozen.get("task_family_version")) == str(actual["task_family_version"]),
            S2_FROZEN_PACKAGE_MISMATCH,
            "frozen_package.task_family_version 不匹配",
        )
        _require(str(frozen.get("run_id")) == str(actual["run_id"]), S2_FROZEN_PACKAGE_MISMATCH, "frozen_package.run_id 不匹配")
        boundary = _require_mapping(payload.get("data_boundary"), S2_DATA_BOUNDARY_ERROR, "data_boundary")
        _require_exact(boundary.get("allowed_splits"), list(ALLOWED_SPLITS), S2_DATA_BOUNDARY_ERROR, "allowed_splits")
        _require_exact(boundary.get("forbidden_splits"), list(FORBIDDEN_SPLITS), S2_DATA_BOUNDARY_ERROR, "forbidden_splits")
        _require_exact(boundary.get("split_counts"), EXPECTED_SPLIT_COUNTS, S2_DATA_BOUNDARY_ERROR, "split_counts")
        _require_exact(boundary.get("holdout_rows_used"), 0, S2_DATA_BOUNDARY_ERROR, "holdout_rows_used")
        task_ids = actual["task_ids"]
        _require(str(boundary.get("meta_train_task_ids_sha256")) == ids_sha256(task_ids["meta_train"]), S2_DATA_BOUNDARY_ERROR, "meta_train_task_ids_sha256 不匹配")
        _require(str(boundary.get("meta_validation_task_ids_sha256")) == ids_sha256(task_ids["meta_validation"]), S2_DATA_BOUNDARY_ERROR, "meta_validation_task_ids_sha256 不匹配")
        holdout_ids = [task_id for split in FORBIDDEN_SPLITS for task_id in task_ids[split]]
        _require(str(boundary.get("holdout_task_ids_sha256")) == ids_sha256(holdout_ids), S2_DATA_BOUNDARY_ERROR, "holdout_task_ids_sha256 不匹配（holdout = 三个 forbidden split 的并集）")
    return True


# -- 读写 --------------------------------------------------------------------


def write_preregistration(prereg: Mapping[str, Any], path: Path | str) -> Path:
    """以 canonical JSON + 末尾换行落盘（不覆盖已存在文件，避免误改冻结 prereg）。"""
    target = Path(path)
    if target.exists():
        raise S2PreregError(f"{S2_PREREG_SCHEMA_ERROR}: 目标 prereg 已存在，拒绝覆盖: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json_line(dict(prereg)), encoding="utf-8", newline="\n")
    return target


def read_preregistration(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise S2PreregError(f"{S2_PREREG_SCHEMA_ERROR}: prereg 文件顶层必须是对象")
    return payload


__all__ = [
    "ALLOWED_SPLITS",
    "ARM_SPECS",
    "BASE_ARM_CONFIG",
    "CODE_SHA_FILES",
    "COMPARISON",
    "DEFAULT_PACKAGE_PATH",
    "DEFAULT_PILOT_ARTIFACTS",
    "DEFAULT_REPO_ROOT",
    "DETERMINISM",
    "ENDPOINTS",
    "EPISODE_CONTRACT",
    "EVALUATION_GRID",
    "EXPECTED_SPLIT_COUNTS",
    "FAILURE_RULES",
    "FORBIDDEN_SPLITS",
    "FROZEN_PACKAGE_KEYS",
    "PACKAGE_FAMILY_VERSION",
    "PREREG_ID_PREFIX",
    "RESOURCE_LIMITS",
    "SCHEMA_VERSION",
    "SEED_SCOPES",
    "STATISTICAL_PLAN",
    "STOPPING_RULES",
    "TASK_FAMILY_VERSION",
    "TRAINING_BUDGET",
    "UPSTREAM",
    "S2PreregError",
    "analysis_plan_digest",
    "build_preregistration",
    "canonical_json",
    "canonical_json_line",
    "canonical_sha256",
    "code_sha_for_files",
    "compute_code_sha",
    "compute_prereg_digest",
    "compute_prereg_id",
    "find_placeholders",
    "ids_sha256",
    "inspect_frozen_package",
    "parse_sha256sums",
    "read_preregistration",
    "reject_placeholders",
    "sha256_bytes",
    "sha256_file",
    "sha256_text",
    "verify_preregistration",
    "write_preregistration",
]