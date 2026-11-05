"""P4-M6 冻结门禁：加载 M5 冻结家族 / 预注册 / split，并复用旧 M2 run 不可变快照。

A5M6-01 / A5M6-02 / A5M6-03 的修复落点：

* 元训练家族必须是 M5 冻结的 F-QE-feasible-v2（family_version=v2、radius_base 来自校准），
  禁止静默回落到 v1 的 F-QE；
* holdout 前必须加载 frozen_family.json / preregistration.json / meta_task_split.json，
  逐项校验 schema + sha256 + family fingerprint + radius + split_hash；缺文件或任何不一致即
  M6FrozenGateError（fail-closed，PREREGISTRATION_NOT_FROZEN），不进入数据集构建；
* M6 产物目录内复制一份冻结输入（gate/），保证结论可追溯到冻结版本；
* 旧 M2 run（48,000 次合成的不可变基线）在 M6 运行前后各做一次快照校验，任何变化
  fail-closed；旧 run 不在当前 output_root 下时如实降级 NOT_AVAILABLE（enforced=false），
  不得表述为"已通过"。

本模块只做只读校验与写新 run 目录，绝不修改冻结输入或旧 run。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import feasible_v2 as fv2
from . import task_family as tf
from .m5_runner import (
    OLD_M2_RUN_ID,
    OLD_RUN_GATE_FILE,
    OLD_RUN_GATE_RULE,
    snapshot_old_m2_run,
)
from .offline_runner import iso_utc, write_json

#: 门禁 schema（M6 自有版本，便于报告层区分 M5 的 p4-m5-*）
GATE_SCHEMA_VERSION = "p4-m6-frozen-gate-1"
#: M6 元训练家族必须是冻结版 v2；旧 v1 F-QE 只能作为历史对照，不得默认
TRAIN_FAMILY = tf.V2_FAMILY_ID
#: 冻结输入三件套的文件名（M5 正式 run 目录内的相对路径）
GATE_FILES = {
    "frozen_family": "frozen_family.json",
    "preregistration": "preregistration.json",
    "split_manifest": "meta_task_split.json",
}
#: 新 run 内存放冻结输入副本的子目录
GATE_SUBDIR = "gate"
#: 旧 M2 run 不可变门禁（M6 自有 schema，快照语义复用 M5）
OLD_RUN_GATE_SCHEMA_VERSION = "p4-m6-old-run-gate-1"
OLD_M2_RUN_GATE_FILE = OLD_RUN_GATE_FILE
#: 冻结家族必须含有的参考解 / 区间定义，防止"冻结了但口径不对"
EXPECTED_REFERENCE_SOLUTION = "c"
EXPECTED_GAP_DEFINITION = "f(u_best)-f(u*)"


class M6FrozenGateError(RuntimeError):
    """冻结门禁失败（缺失/篡改/规模不符）；fail-closed 中止整次 M6 run。"""


def _sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path | str, label: str) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise M6FrozenGateError(
            "冻结门禁缺少 %s 文件：%s（必须先完成 M5 calibration + freeze 阶段）"
            % (label, target)
        )
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise M6FrozenGateError("冻结门禁无法解析 %s：%s（%s）" % (label, target, error)) from error
    if not isinstance(payload, dict):
        raise M6FrozenGateError("冻结门禁 %s 内容不是 JSON 对象：%s" % (label, target))
    return payload


def old_run_dir(output_root: Path | str) -> Path:
    """旧 M2 run 目录（只读）。"""
    return Path(output_root) / OLD_M2_RUN_ID


def _resolve_gate_file(
    label: str,
    explicit: Path | str | None,
    run_dir: Path | None,
    filename: str,
) -> Path:
    if explicit:
        path = Path(explicit)
        if path.is_dir():
            path = path / filename
        if not path.is_file():
            raise M6FrozenGateError("冻结门禁输入不存在：%s -> %s" % (label, path))
        return path
    if run_dir is not None:
        for candidate in (
            Path(run_dir) / filename,
            Path(run_dir) / GATE_SUBDIR / filename,
        ):
            if candidate.is_file():
                return candidate
    raise M6FrozenGateError(
        "冻结门禁输入未提供：%s（需要 frozen_run_dir 或显式路径；缺省不得回落到 v1 F-QE）"
        % label
    )


def resolve_gate_paths(
    *,
    frozen_run_dir: Path | str | None = None,
    frozen_family_path: Path | str | None = None,
    preregistration_path: Path | str | None = None,
    split_manifest_path: Path | str | None = None,
) -> dict[str, Path]:
    """解析冻结三件套的路径；显式路径优先，其次在 frozen_run_dir 下查找。"""
    run_dir = Path(frozen_run_dir) if frozen_run_dir else None
    if run_dir is not None and not run_dir.is_dir():
        raise M6FrozenGateError("冻结 run 目录不存在：%s" % run_dir)
    return {
        "frozen_family": _resolve_gate_file(
            "frozen_family", frozen_family_path, run_dir, GATE_FILES["frozen_family"]
        ),
        "preregistration": _resolve_gate_file(
            "preregistration", preregistration_path, run_dir, GATE_FILES["preregistration"]
        ),
        "split_manifest": _resolve_gate_file(
            "split_manifest", split_manifest_path, run_dir, GATE_FILES["split_manifest"]
        ),
    }

@dataclass(frozen=True)
class FrozenGate:
    """冻结门禁载荷：三份冻结输入 + 反序列化后的 v2 任务族配置。"""

    frozen_path: Path
    preregistration_path: Path
    split_manifest_path: Path
    frozen: Mapping[str, Any]
    preregistration: Mapping[str, Any]
    split_manifest: Mapping[str, Any]
    family_config: tf.TaskFamilyConfig
    frozen_sha256: str
    preregistration_sha256: str
    split_manifest_sha256: str
    legacy_warnings: tuple[str, ...] = ()

    @property
    def family_id(self) -> str:
        return str(self.frozen["family_id"])

    @property
    def family_version(self) -> str:
        return str(self.frozen["family_version"])

    @property
    def family_fingerprint(self) -> str:
        return str(self.frozen["family_fingerprint"])

    @property
    def radius_base(self) -> float:
        return float(self.frozen["radius_base"])

    @property
    def split_hash(self) -> str:
        return str(self.split_manifest["split_hash"])

    @property
    def split_counts(self) -> dict[str, int]:
        counts = self.frozen.get("split", {}).get("counts", {})
        return {str(name): int(value) for name, value in counts.items()}

    @property
    def reference_solution(self) -> str:
        return str(self.frozen.get("reference_solution"))

    @property
    def gap_definition(self) -> str:
        return str(self.frozen.get("gap_definition"))

    @property
    def calibration_seeds(self) -> list[int]:
        return [int(item) for item in self.frozen.get("calibration_seeds") or ()]

    @property
    def pooled_success(self) -> float | None:
        value = self.frozen.get("pooled_success")
        return None if value is None else float(value)

    @property
    def feasible_volume_fraction(self) -> float | None:
        value = self.frozen.get("feasible_volume_fraction")
        return None if value is None else float(value)

    @property
    def meta_test_tuning_policy(self) -> str:
        return str(self.frozen.get("meta_test_tuning_policy") or "")

    def to_dict(self) -> dict[str, Any]:
        """JSON 安全摘要（供 summary / run_config 引用，不内联 family_config 全量）。"""
        return {
            "schema_version": GATE_SCHEMA_VERSION,
            "status": "PASS",
            "train_family": TRAIN_FAMILY,
            "family_id": self.family_id,
            "family_version": self.family_version,
            "family_fingerprint": self.family_fingerprint,
            "radius_base": self.radius_base,
            "radius_mapping": self.frozen.get("radius_mapping"),
            "reference_solution": self.reference_solution,
            "gap_definition": self.gap_definition,
            "calibration_seeds": self.calibration_seeds,
            "pooled_success": self.pooled_success,
            "feasible_volume_fraction": self.feasible_volume_fraction,
            "split_hash": self.split_hash,
            "split_counts": self.split_counts,
            "meta_test_tuning_policy": self.meta_test_tuning_policy,
            "calibration_report_sha256": (self.frozen.get("calibration") or {}).get("report_sha256"),
            "frozen_family_path": str(self.frozen_path),
            "preregistration_path": str(self.preregistration_path),
            "split_manifest_path": str(self.split_manifest_path),
            "frozen_family_sha256": self.frozen_sha256,
            "preregistration_sha256": self.preregistration_sha256,
            "split_manifest_sha256": self.split_manifest_sha256,
            "preregistration_schema_version": str(self.preregistration.get("schema_version") or ""),
            "preregistration_legacy_warnings": list(self.legacy_warnings),
            "physical_call_count": 0,
            "preregistered_arms": list(self.preregistration.get("arms") or ()),
            "preregistered_budgets": list(self.preregistration.get("budgets") or ()),
            "preregistered_optimization_seeds": list(self.preregistration.get("optimization_seeds") or ()),
            "preregistered_meta_seeds": list(self.preregistration.get("meta_seeds") or ()),
            "note": "冻结输入只读；M6 产物内 gate/ 为逐字节副本，任何不一致即 fail-closed",
        }

    def write_gate_directory(self, run_dir: Path | str) -> dict[str, Any]:
        """把冻结输入逐字节复制进新 run 的 gate/ 目录（不写冻结源）。"""
        target_dir = Path(run_dir) / GATE_SUBDIR
        target_dir.mkdir(parents=True, exist_ok=True)
        copies: dict[str, Any] = {}
        for name, source, expected_sha in (
            ("frozen_family", self.frozen_path, self.frozen_sha256),
            ("preregistration", self.preregistration_path, self.preregistration_sha256),
            ("split_manifest", self.split_manifest_path, self.split_manifest_sha256),
        ):
            destination = target_dir / GATE_FILES[name]
            shutil.copyfile(Path(source), destination)
            actual_sha = _sha256_file(destination)
            if actual_sha != expected_sha:
                raise M6FrozenGateError(
                    "冻结输入复制后校验失败：%s（期望 %s，实际 %s）" % (destination, expected_sha, actual_sha)
                )
            copies[name] = {
                "path": destination.relative_to(Path(run_dir)).as_posix(),
                "sha256": actual_sha,
                "bytes": destination.stat().st_size,
                "source": str(source),
            }
        return {"gate_directory": GATE_SUBDIR, "files": copies}


def load_frozen_gate(
    *,
    frozen_run_dir: Path | str | None = None,
    frozen_family_path: Path | str | None = None,
    preregistration_path: Path | str | None = None,
    split_manifest_path: Path | str | None = None,
) -> FrozenGate:
    """加载并校验冻结门禁；任何缺失/篡改/规模不符都抛 M6FrozenGateError。"""
    paths = resolve_gate_paths(
        frozen_run_dir=frozen_run_dir,
        frozen_family_path=frozen_family_path,
        preregistration_path=preregistration_path,
        split_manifest_path=split_manifest_path,
    );
    frozen = _load_json(paths["frozen_family"], "frozen_family")
    preregistration = _load_json(paths["preregistration"], "preregistration")
    split_manifest = _load_json(paths["split_manifest"], "split_manifest")

    try:
        if fv2.verify_frozen_payload(frozen) is False:
            raise M6FrozenGateError("frozen_family 校验返回 False")
    except M6FrozenGateError:
        raise
    except Exception as error:
        raise M6FrozenGateError("frozen_family 校验失败：%s" % error) from error
    if str(frozen.get("family_id")) != TRAIN_FAMILY:
        raise M6FrozenGateError(
            "M6 元训练家族必须是冻结的 %s，实际 %r（禁止静默回落到 v1 F-QE）"
            % (TRAIN_FAMILY, frozen.get("family_id"))
        )
    if str(frozen.get("family_version")) != "v2":
        raise M6FrozenGateError("frozen_family.family_version 必须为 v2，实际 %r" % frozen.get("family_version"))
    if str(frozen.get("reference_solution")) != EXPECTED_REFERENCE_SOLUTION:
        raise M6FrozenGateError(
            "frozen_family.reference_solution 必须为 %r，实际 %r"
            % (EXPECTED_REFERENCE_SOLUTION, frozen.get("reference_solution"))
        )
    if str(frozen.get("gap_definition")) != EXPECTED_GAP_DEFINITION:
        raise M6FrozenGateError(
            "frozen_family.gap_definition 必须为 %r，实际 %r"
            % (EXPECTED_GAP_DEFINITION, frozen.get("gap_definition"))
        )
    try:
        family_config = fv2.frozen_to_config(frozen)
    except Exception as error:
        raise M6FrozenGateError("frozen_family.family_config 反序列化失败：%s" % error) from error
    if str(family_config.family_id) != TRAIN_FAMILY or str(family_config.family_version) != "v2":
        raise M6FrozenGateError("frozen_family.family_config 不是 v2 冻结家族")
    if family_config.radius_base is None or float(family_config.radius_base) != float(frozen["radius_base"]):
        raise M6FrozenGateError("frozen_family.family_config.radius_base 与顶层 radius_base 不一致")
    if not (float(frozen["radius_base"]) > 0.0):
        raise M6FrozenGateError("frozen_family.radius_base 必须为正数")

    # 历史只读路径：M6 门禁读取旧 M5 run 的 p4-m5-prereg-v1，必须显式
    # allow_legacy=True 并保留 legacy_warning；新 schema 仍走同一条严格校验链。
    legacy_warnings: list[str] = []
    try:
        if fv2.verify_preregistration(
            preregistration,
            frozen,
            allow_legacy=True,
            legacy_warnings=legacy_warnings,
        ) is False:
            raise M6FrozenGateError("preregistration 校验返回 False")
    except M6FrozenGateError:
        raise
    except Exception as error:
        legacy = getattr(error, "legacy_warning", None)
        detail = "preregistration 校验失败：%s" % error
        if legacy:
            detail += "（legacy_warning=%s）" % legacy
        raise M6FrozenGateError(detail) from error
    for key in ("arms", "budgets", "optimization_seeds", "meta_seeds"):
        if not preregistration.get(key):
            raise M6FrozenGateError("preregistration 缺少 %s（未预注册不得开 holdout）" % key)
    if len(set(int(item) for item in preregistration["optimization_seeds"])) < 10:
        raise M6FrozenGateError("preregistration.optimization_seeds 必须 >=10 个互异值")

    try:
        fv2.verify_split_manifest(split_manifest)
    except Exception as error:
        raise M6FrozenGateError("meta_task_split.json 校验失败：%s" % error) from error
    frozen_split = frozen.get("split") or {}
    if str(split_manifest.get("split_hash")) != str(frozen_split.get("split_hash")):
        raise M6FrozenGateError("meta_task_split.split_hash 与 frozen_family.split.split_hash 不一致")
    if str(split_manifest.get("family_fingerprint")) != str(frozen.get("family_fingerprint")):
        raise M6FrozenGateError("meta_task_split.family_fingerprint 与 frozen_family 不一致")
    manifest_counts = {str(k): int(v) for k, v in (split_manifest.get("counts") or {}).items()}
    if manifest_counts != {str(k): int(v) for k, v in (frozen_split.get("counts") or {}).items()}:
        raise M6FrozenGateError("meta_task_split.counts 与 frozen_family.split.counts 不一致")
    if abs(float(split_manifest.get("radius_base", -1.0)) - float(frozen["radius_base"])) > 1e-12:
        raise M6FrozenGateError("meta_task_split.radius_base 与 frozen_family.radius_base 不一致")

    return FrozenGate(
        frozen_path=Path(paths["frozen_family"]),
        preregistration_path=Path(paths["preregistration"]),
        split_manifest_path=Path(paths["split_manifest"]),
        frozen=frozen,
        preregistration=preregistration,
        split_manifest=split_manifest,
        family_config=family_config,
        frozen_sha256=_sha256_file(paths["frozen_family"]),
        preregistration_sha256=_sha256_file(paths["preregistration"]),
        split_manifest_sha256=_sha256_file(paths["split_manifest"]),
        legacy_warnings=tuple(legacy_warnings),
    )

# ---------------------------------------------------------------------------
# 冻结规模与任务一致性
# ---------------------------------------------------------------------------
_SPLIT_COUNT_FIELDS = {
    "meta_train": "train_tasks",
    "meta_validation": "validation_tasks",
    "meta_test": "test_tasks",
    "meta_test_ood": "ood_tasks",
    "negative_control": "negative_control_tasks",
}


def family_config_for_m6(
    gate: FrozenGate,
    *,
    train_tasks: int,
    validation_tasks: int,
    test_tasks: int,
    ood_tasks: int,
    negative_control_tasks: int,
    support_pool_size: int,
    query_size: int,
    family_seed: int,
    full_scale: bool,
) -> tf.TaskFamilyConfig:
    """由冻结家族配置派生 M6 元训练族。

    * FORMAL：split 规模、支持池、query、种子必须与冻结家族逐项相同，直接用冻结配置，
      任何不一致 fail-closed（A5M6-01：禁止用 v1 或改动规模的"伪 v2"）；
    * SMOKE：允许缩小任务数/支持池（成本原因），但家族 id/version/radius/fingerprint
      必须仍是冻结 v2，并在 summary 中披露 study_scale=SMOKE。
    """
    base = gate.family_config
    if int(family_seed) != int(base.seed):
        raise M6FrozenGateError(
            "M6 元训练族 seed 必须等于冻结家族 seed=%d，实际 %d（禁止用不同任务集冒充冻结 split）"
            % (int(base.seed), int(family_seed))
        )
    requested = {
        "meta_train": int(train_tasks),
        "meta_validation": int(validation_tasks),
        "meta_test": int(test_tasks),
        "meta_test_ood": int(ood_tasks),
        "negative_control": int(negative_control_tasks),
    }
    if full_scale:
        mismatched: list[str] = []
        for split_name, field_name in _SPLIT_COUNT_FIELDS.items():
            expected = int(getattr(base, field_name))
            if requested[split_name] != expected:
                mismatched.append("%s:%d!=%d" % (split_name, requested[split_name], expected))
        if mismatched:
            raise M6FrozenGateError(
                "FORMAL 规模必须与冻结 split 一致（%s）" % "；".join(mismatched)
            )
        if int(support_pool_size) != int(base.support_pool_size):
            raise M6FrozenGateError(
                "FORMAL support_pool_size 必须等于冻结值 %d，实际 %d"
                % (int(base.support_pool_size), int(support_pool_size))
            )
        if int(query_size) != int(base.query_size):
            raise M6FrozenGateError(
                "FORMAL query_size 必须等于冻结值 %d，实际 %d" % (int(base.query_size), int(query_size))
            )
        return base
    return dataclasses.replace(
        base,
        train_tasks=requested["meta_train"],
        validation_tasks=requested["meta_validation"],
        test_tasks=requested["meta_test"],
        ood_tasks=requested["meta_test_ood"],
        negative_control_tasks=requested["negative_control"],
        designs_per_task=int(support_pool_size) + int(query_size),
        support_pool_size=int(support_pool_size),
        query_size=int(query_size),
    )


def _manifest_task_map(split_manifest: Mapping[str, Any], split: str) -> dict[str, dict[str, Any]]:
    entries = (split_manifest.get("tasks") or {}).get(split) or ()
    return {str(entry.get("task_id")): dict(entry) for entry in entries if isinstance(entry, Mapping)}


def verify_datasets(gate: FrozenGate, datasets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """FORMAL 下逐 split 校验 M6 重建的任务与冻结 split manifest 逐位一致。"""
    train_family = TRAIN_FAMILY
    if train_family not in datasets:
        raise M6FrozenGateError("M6 数据集缺少冻结元训练族 %s" % train_family)
    dataset = datasets[train_family]
    splits = dataset.get("splits") or {}
    manifest = gate.split_manifest
    manifest_task_ids = manifest.get("task_ids") or {}
    detail: dict[str, Any] = {}
    mismatched: list[str] = []
    tasks_checked = 0
    for split in _SPLIT_COUNT_FIELDS:
        expected_ids = [str(item) for item in manifest_task_ids.get(split) or ()]
        actual_ids = sorted(str(task.task_id) for task in splits.get(split) or ())
        expected_sorted = sorted(expected_ids)
        ids_match = actual_ids == expected_sorted
        expected_tasks = _manifest_task_map(manifest, split)
        seeds_match = True
        digests_match = True
        for task in splits.get(split) or ():
            tasks_checked += 1
            entry = expected_tasks.get(str(task.task_id))
            if entry is None:
                seeds_match = False
                digests_match = False
                continue
            if int(entry.get("seed")) != int(task.seed):
                seeds_match = False
            params_digest = fv2.digest(dict(task.params))
            if str(entry.get("params_digest")) != params_digest:
                digests_match = False
        passed = bool(ids_match and seeds_match and digests_match)
        if not passed:
            mismatched.append(split)
        detail[split] = {
            "manifest_tasks": len(expected_ids),
            "m6_tasks": len(actual_ids),
            "task_ids_match": ids_match,
            "seeds_match": seeds_match,
            "params_digest_match": digests_match,
            "status": "PASS" if passed else "FAIL",
        }
    if mismatched:
        raise M6FrozenGateError(
            "M6 重建任务与冻结 split manifest 不一致：%s（fail-closed，不得用自造 split 下结论）"
            % ", ".join(mismatched)
        )
    return {
        "status": "PASS",
        "family_id": train_family,
        "family_fingerprint": gate.family_fingerprint,
        "split_hash": gate.split_hash,
        "splits": detail,
        "tasks_checked": tasks_checked,
    }


# ---------------------------------------------------------------------------
# 旧 M2 run 不可变门禁（快照语义复用 m5_runner.snapshot_old_m2_run）
# ---------------------------------------------------------------------------
def begin_old_run_gate(output_root: Path | str, run_dir: Path | str) -> dict[str, Any]:
    """运行前快照旧 M2 run 并写入新 run 目录（绝不写旧 run）。"""
    before = snapshot_old_m2_run(Path(output_root))
    payload = {
        "schema_version": OLD_RUN_GATE_SCHEMA_VERSION,
        "gate": "OLD_M2_RUN_IMMUTABILITY",
        "stage": "m6_before",
        "status": str(before.get("status")),
        "enforced": str(before.get("status")) == "PASS",
        "enforcement": (
            "ENFORCED" if str(before.get("status")) == "PASS" else "NOT_ENFORCED_OLD_RUN_UNAVAILABLE"
        ),
        "read_only": True,
        "rule": OLD_RUN_GATE_RULE,
        "before": dict(before),
        "after": None,
        "manifest_sha256_same_before_after": None,
        "created_utc": iso_utc(),
        "physical_call_count": 0,
        "note": (
            "旧 M2 run（48,000 次合成评价）为不可变基线；本文件落在新 run 目录。"
            "status=NOT_AVAILABLE 表示旧 run 不在此 output_root 下，门禁未执行（enforced=false），"
            "禁止表述为已通过"
        ),
    }
    target = Path(run_dir) / OLD_M2_RUN_GATE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, payload)
    return payload


def finish_old_run_gate(
    output_root: Path | str,
    run_dir: Path | str,
    gate: Mapping[str, Any],
    *,
    stage: str = "m6_after_products",
) -> dict[str, Any]:
    """产物写出后复核旧 run 未变化并更新门禁文件（fail-closed）。"""
    before = dict(gate.get("before") or {})
    after = snapshot_old_m2_run(Path(output_root))
    before_status = str(before.get("status"))
    after_status = str(after.get("status"))
    same_manifest = before.get("manifest_sha256") == after.get("manifest_sha256")
    if after_status == "FAIL":
        raise M6FrozenGateError(
            "旧 M2 run 不可变性门禁失败（stage=%s）：before=%s after=%s" % (stage, before_status, after_status)
        )
    if before_status == "PASS" and after_status == "PASS" and not same_manifest:
        raise M6FrozenGateError("旧 M2 run 的 data_manifest.json 在 stage=%s 期间发生变化" % stage)
    enforced = before_status == "PASS" and after_status == "PASS" and same_manifest
    if enforced:
        enforcement = "ENFORCED"
    elif after_status == "NOT_AVAILABLE":
        enforcement = "NOT_ENFORCED_OLD_RUN_UNAVAILABLE"
    else:
        enforcement = "NOT_ENFORCED_BEFORE_UNAVAILABLE"
    payload = {
        "schema_version": OLD_RUN_GATE_SCHEMA_VERSION,
        "gate": "OLD_M2_RUN_IMMUTABILITY",
        "stage": stage,
        "status": after_status,
        "enforced": enforced,
        "enforcement": enforcement,
        "read_only": True,
        "rule": OLD_RUN_GATE_RULE,
        "before": before,
        "after": dict(after),
        "manifest_sha256_same_before_after": same_manifest,
        "updated_utc": iso_utc(),
        "physical_call_count": 0,
        "note": "运行前后各快照一次；status=FAIL 立即中止，NOT_AVAILABLE 如实降级披露",
    }
    write_json(Path(run_dir) / OLD_M2_RUN_GATE_FILE, payload)
    return payload


def assert_old_run_unchanged(
    output_root: Path | str,
    gate: Mapping[str, Any],
    *,
    stage: str = "m6_after_products",
) -> dict[str, Any]:
    """静默复核旧 M2 run 仍与门禁快照一致（不写盘；A5M6-03）。"""
    before = dict(gate.get("before") or {})
    after = snapshot_old_m2_run(Path(output_root))
    before_status = str(before.get("status"))
    after_status = str(after.get("status"))
    same_manifest = before.get("manifest_sha256") == after.get("manifest_sha256")
    if after_status == "FAIL":
        raise M6FrozenGateError("旧 M2 run 不可变性复核失败（stage=%s）：status=FAIL" % stage)
    if before_status == "PASS" and after_status == "PASS" and not same_manifest:
        raise M6FrozenGateError("旧 M2 run 的 data_manifest.json 在 stage=%s 期间发生变化" % stage)
    enforced = before_status == "PASS" and after_status == "PASS"
    return {
        "status": after_status,
        "stage": stage,
        "enforced": enforced,
        "enforcement": "ENFORCED" if enforced else "NOT_ENFORCED_OLD_RUN_UNAVAILABLE",
        "manifest_sha256_same_before_after": same_manifest,
        "physical_call_count": 0,
    }


__all__ = [
    "EXPECTED_GAP_DEFINITION",
    "EXPECTED_REFERENCE_SOLUTION",
    "FrozenGate",
    "GATE_FILES",
    "GATE_SCHEMA_VERSION",
    "GATE_SUBDIR",
    "M6FrozenGateError",
    "OLD_M2_RUN_GATE_FILE",
    "OLD_M2_RUN_ID",
    "OLD_RUN_GATE_SCHEMA_VERSION",
    "TRAIN_FAMILY",
    "assert_old_run_unchanged",
    "begin_old_run_gate",
    "family_config_for_m6",
    "finish_old_run_gate",
    "load_frozen_gate",
    "old_run_dir",
    "resolve_gate_paths",
    "verify_datasets",
]
