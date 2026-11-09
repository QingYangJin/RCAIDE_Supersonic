"""S3 分析器（s3_analysis.py）单元与端到端测试。

覆盖计划 §4.3/§4.5/§5/§6 与 R-S3-03/R-S3-04 裁定：
- prereg 强校验（canonical、digest、占位、绑定、数据边界、physical=0）；
- run_config/run_summary/data_manifest/model_manifest/gate 产物字段与预算校验；
- 评估记录 19 字段、预算记账（记录数=B、source 分布、索引 1..B）、boost 条件；
- 端点/统计/决策（tie-aware Wilcoxon 精确、Holm、bootstrap、6 档决策、ANIL）；
- SMOKE 端到端：合成证据树 + 40 runs（3,840 eval + 4 train）→ 7 CSV+aggregate+figure_status；
- fail-closed 负控：删字段/篡改 SHA/改 run_mode/删 smoke_overrides/删 comparator 等。

测试不读真实 holdout 数据、不训练、不调用求解器；fixture 全部由解析式与固定 seed 合成。
"""

from __future__ import annotations

import atexit
import dataclasses
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from research.concorde_metaopt.meta_learning import s3_analysis as an
from research.concorde_metaopt.meta_learning import s3_prereg as sp
from research.concorde_metaopt.meta_learning import task_family as tf

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_RUN_ID = "p4ra-s3-run-smoke-fixture"
FIXTURE_CREATED_UTC = "2026-11-07T06:30:00Z"
FIXTURE_CODE_SHA = "0123456789abcdef" * 4
FIXTURE_ANALYSIS_CODE_SHA = "fedcba9876543210" * 4
DELTA1_BASE = 0.20
SMOKE_OUTER_STEPS = 2
SMOKE_META_SEEDS = [0]
SMOKE_BUDGETS = [64, 128]
SMOKE_OPT_SEEDS = [0]
SMOKE_EVAL_TASKS = 4
SMOKE_KS = [0, 1, 3, 5]
ARM_FEASIBLE_RATIO = {
    "S3-BO-FOMAML-CON": 0.25,
    "S3-BO-FOMAML-OBJ": 0.55,
    "S3-BO-RANDOM": 0.65,
    "S3-BO-ANIL-CON": 0.35,
    "S3-DE": 0.50,
}


# ---------------------------------------------------------------------------
# fixture 构造（临时 repo_root 证据树 + 合成 SMOKE run）
# ---------------------------------------------------------------------------
def _canonical(payload):
    return sp.canonical_json(payload)


def _write_json(path, payload):
    data = (_canonical(payload) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _copy_hash_vectors(root):
    src = REPO_ROOT / sp.HASH_VECTORS_RELPATH
    dst = root / sp.HASH_VECTORS_RELPATH
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _write_episode_banks(root):
    files = []
    for meta_seed in sp.S3_MODEL_META_SEEDS:
        records = []
        for step in range(200):
            for slot in range(int(sp.S3_MODEL_CONFIG_TEMPLATE["tasks_per_batch"])):
                episode = {
                    "schema_version": sp.S3_EPISODE_BANK_SCHEMA_VERSION,
                    "meta_seed": int(meta_seed),
                    "outer_step": int(step),
                    "slot": int(slot),
                    "task_split": "meta_train",
                    "episode_digest": sp.sha256_text(str(meta_seed) + "|" + str(step) + "|" + str(slot)),
                }
                records.append(_canonical(episode))
        relpath = sp.S3_EPISODE_BANK_PATH_TEMPLATE.format(meta_seed=meta_seed)
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(records) + "\n", encoding="utf-8")
        files.append({"meta_seed": int(meta_seed), "path": relpath})
    return files


def _write_models(root, banks):
    models = {kind: [] for kind in sp.S3_MODEL_KINDS}
    for kind in sp.S3_MODEL_KINDS:
        for meta_seed in sp.S3_MODEL_META_SEEDS:
            config = dict(sp.S3_MODEL_CONFIG_TEMPLATE)
            config["hidden_sizes"] = list(config["hidden_sizes"])
            config["seed"] = int(meta_seed)
            config["head_only"] = kind == "anil"
            payload = {
                "schema_version": sp.S3_MODEL_FILE_SCHEMA_VERSION,
                "arm_type": kind,
                "meta_seed": int(meta_seed),
                "config": config,
                "parameters": [0.01 * (index + 1) for index in range(6)],
                "episode_bank_sha256": banks["meta_seed_" + str(meta_seed)],
                "final_train_loss": 0.5 + 0.01 * meta_seed,
            }
            relpath = sp.S3_MODEL_PATH_TEMPLATE.format(kind=kind, meta_seed=meta_seed)
            _write_json(root / relpath, payload)
            models[kind].append({"meta_seed": int(meta_seed), "path": relpath})
    return models

def _frozen_gate_payload():
    """M2 冻结 FD 门（R-S3-06 §2 / R-S3-07）：两模型各 32 坐标 + 三负控。"""
    coordinates = []
    for index in range(int(sp.S3_FD_GATE_COORDINATES_PER_MODEL)):
        relative = 1e-10 * (index + 1)
        coordinates.append(
            {
                "index": index,
                "param": "param_" + str(index).zfill(3),
                "analytic": 1.0 + index,
                "numeric": round(1.0 + index + relative, 15),
                "relative_error": relative,
            }
        )
    model_max = max(item["relative_error"] for item in coordinates)
    models = {}
    for key, arm_type in (("fomaml_meta_0", "fomaml"), ("anil_meta_0", "anil")):
        models[key] = {
            "arm_type": arm_type,
            "meta_seed": 0,
            "n_checked": len(coordinates),
            "status": "PASS",
            "max_relative_error": model_max,
            "coordinates": [dict(item) for item in coordinates],
        }
    return {
        "schema_version": sp.S3_FD_GATE_SCHEMA_VERSION,
        "created_utc": FIXTURE_CREATED_UTC,
        "status": "PASS",
        "physical_call_count": 0,
        "tolerance": sp.S3_FD_TOLERANCE,
        "epsilon_rule": sp.S3_FD_EPSILON_RULE,
        "coordinates_per_model": int(sp.S3_FD_GATE_COORDINATES_PER_MODEL),
        "coordinates_total": int(sp.S3_FD_GATE_COORDINATES_PER_MODEL)
        * len(sp.S3_FD_GATE_MODEL_KEYS),
        "models": models,
        "negatives": {key: "PASS" for key in sp.S3_FD_GATE_NEGATIVE_KEYS},
        "max_relative_error": model_max,
    }


def _write_frozen_gate(root):
    """写 M2 冻结 FD 门文件。

    注意：models 键序必须为 (fomaml_meta_0, anil_meta_0)，因此不能用
    _write_json（canonical 会 sort_keys 改变插入顺序）。
    """
    path = root / sp.S3_GATE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_frozen_gate_payload(), ensure_ascii=False, separators=(",", ":"))
    data = (text + "\n").encode("utf-8")
    path.write_bytes(data)
    return data


def _calibration_payload():
    return {
        "schema_version": sp.S3_CALIBRATION_SCHEMA_VERSION,
        "family_id": sp.S3_FAMILY_ID,
        "formula_version": sp.S3_FORMULA_VERSION,
        "created_utc": FIXTURE_CREATED_UTC,
        "validation_split": "meta_validation",
        "physical_call_count": 0,
        "accepted": True,
        "selected_delta1_base": DELTA1_BASE,
        "candidates": [
            {"delta1_base": 0.18, "accepted": False},
            {"delta1_base": 0.20, "accepted": True},
            {"delta1_base": 0.22, "accepted": False},
            {"delta1_base": 0.25, "accepted": False},
        ],
        "construction_stats": {"pooled_success": 0.5, "candidate_count": 4},
    }


def build_evidence_tree(root):
    root = Path(root)
    tasks = tf.build_s3_conflict_family(delta1_base=DELTA1_BASE)
    package = tf.build_s3_family_package(tasks, delta1_base=DELTA1_BASE, created_utc=FIXTURE_CREATED_UTC, code_sha=FIXTURE_CODE_SHA)
    package_path = root / sp.S3_FAMILY_PACKAGE_RELPATH
    package_path.parent.mkdir(parents=True, exist_ok=True)
    package_bytes = _write_json(package_path, package)
    sealed = tf.build_s3_references_sealed(tasks)
    sealed_path = root / sp.S3_REFERENCES_SEALED_RELPATH
    sealed_path.parent.mkdir(parents=True, exist_ok=True)
    sealed_bytes = _write_json(sealed_path, sealed)
    calibration_path = root / sp.S3_CALIBRATION_RELPATH
    calibration_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(calibration_path, _calibration_payload())
    _copy_hash_vectors(root)
    episode_files = _write_episode_banks(root)
    banks_sha = {}
    for entry in episode_files:
        path = root / entry["path"]
        banks_sha["meta_seed_" + str(entry["meta_seed"])] = sp.sha256_bytes(path.read_bytes())
    models = _write_models(root, banks_sha)
    _write_frozen_gate(root)
    prereg = sp.build_preregistration(
        repo_root=root,
        created_utc=FIXTURE_CREATED_UTC,
        episode_bank_files=episode_files,
        models=models,
        code_sha=FIXTURE_CODE_SHA,
        analysis_code_sha=FIXTURE_ANALYSIS_CODE_SHA,
    )
    prereg_path = root / "research/concorde_metaopt/evidence/s3/prereg/s3_preregistration_fixture.json"
    sp.write_preregistration(prereg_path, prereg)
    return {
        "root": root,
        "package_path": package_path,
        "package_sha256": sp.sha256_bytes(package_bytes),
        "sealed_path": sealed_path,
        "sealed_sha256": sp.sha256_bytes(sealed_bytes),
        "tasks": tasks,
        "prereg_path": prereg_path,
        "prereg": prereg,
    }


def _design(index):
    values = []
    for coordinate in range(12):
        value = (0.02 + 0.01 * coordinate + 0.003 * index) % 0.96
        values.append(round(value + 0.02, 6))
    return values


def _eval_rows(tasks, f_ref, split, phase):
    rows = []
    for task in tasks:
        task_id = task.task_id
        f_star = f_ref[task_id]
        for arm_id in sp.S3_ARMS:
            for budget in SMOKE_BUDGETS:
                threshold = max(1, int(round(ARM_FEASIBLE_RATIO[arm_id] * budget)))
                for meta_seed in SMOKE_META_SEEDS:
                    for opt_seed in SMOKE_OPT_SEEDS:
                        for index in range(1, budget + 1):
                            feasible = index > threshold
                            source = "support" if index <= 5 else ("initial" if index <= 8 else ("de" if arm_id == "S3-DE" else "bo"))
                            record = {
                                "schema_version": sp.S3_RECORD_SCHEMA_VERSION,
                                "run_id": FIXTURE_RUN_ID,
                                "task_id": task_id,
                                "split": split,
                                "arm_id": arm_id,
                                "budget": int(budget),
                                "opt_seed": int(opt_seed),
                                "meta_seed": int(meta_seed),
                                "evaluation_index": int(index),
                                "design": _design(index),
                                "f": round(f_star + 0.30 - 0.0007 * index, 9),
                                "g1": -1.0 if feasible else 1.0,
                                "g2": -1.0,
                                "feasible": bool(feasible),
                                "source": source,
                                "phase": phase,
                                "holdout_truth_read": phase == "EVAL",
                                "wall_s": 0.001 * index,
                            }
                            record["record_digest"] = sp.record_digest(record)
                            rows.append(record)
    return rows


def _train_rows():
    rows = []
    for step in range(SMOKE_OUTER_STEPS):
        for model_index, arm_type in enumerate(sp.S3_MODEL_KINDS):
            record = {
                "schema_version": sp.S3_RECORD_SCHEMA_VERSION,
                "run_id": FIXTURE_RUN_ID,
                "meta_seed": SMOKE_META_SEEDS[0],
                "outer_step": int(step),
                "loss": 0.5 - 0.01 * step + 0.001 * model_index,
                "wall_s": 0.01 * (step + 1) + 0.001 * model_index,
                "train_episode_digest": sp.sha256_text("train|" + arm_type + "|" + str(step)),
            }
            record["record_digest"] = sp.record_digest(record)
            rows.append(record)
    return rows


def build_smoke_run(evidence, run_dir):
    run = Path(run_dir)
    run.mkdir(parents=True, exist_ok=True)
    prereg = evidence["prereg"]
    package = json.loads(evidence["package_path"].read_text(encoding="utf-8"))
    validation_ids = [str(value) for value in package["splits"]["meta_validation"]][:SMOKE_EVAL_TASKS]
    tasks = [task for task in evidence["tasks"] if task.task_id in set(validation_ids)][:SMOKE_EVAL_TASKS]
    assert len(tasks) == SMOKE_EVAL_TASKS
    eval_split = "meta_validation"
    eval_phase = "DEV"
    sealed = json.loads(evidence["sealed_path"].read_text(encoding="utf-8"))
    f_ref = {str(record["task_id"]): float(record["f_star"]) for record in sealed["references"]}
    eval_rows = _eval_rows(tasks, f_ref, eval_split, eval_phase)
    train_rows = _train_rows()
    lines = [_canonical(record) for record in train_rows + eval_rows]
    records_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    (run / "run_records.jsonl").write_bytes(records_bytes)

    scope_notes = {
        "evidence_scope": sp.S3_EVIDENCE_SCOPE,
        "development_set": "meta_validation",
        "holdout_metrics_read": True,
        "physical_call_count": 0,
    }
    gate_payload = {
        "schema_version": sp.S3_GATE_SCHEMA_VERSION,
        "status": "PASS",
        "mode": sp.S3_FD_MODE,
        "created_utc": FIXTURE_CREATED_UTC,
        "max_relative_error": 1e-10,
        # A1 runner 形状：SMOKE 的 FD 坐标数 = smoke_overrides.fd_coordinates（8），非 FORMAL 的 32。
        "coordinates": [
            {"index": index, "analytic": 1.0 + index, "numeric": 1.0 + index + 1e-12, "relative_error": 1e-10}
            for index in range(8)
        ],
    }
    gate_bytes = _write_json(run / "fd_or_gradient_gate.json", gate_payload)
    gate_sha = sp.sha256_bytes(gate_bytes)

    split_ids = {split: [] for split in sp.S3_ALLOWED_SPLITS}
    for task in evidence["tasks"]:
        split_ids[task.split].append(task.task_id)
    split_sha = {split: sp.task_ids_sha256(ids) for split, ids in split_ids.items()}
    data_manifest = {
        "schema_version": sp.S3_DATA_MANIFEST_SCHEMA_VERSION,
        "run_id": FIXTURE_RUN_ID,
        "campaign_authorization_id": None,
        "campaign_authorization_utc": None,
        "data_boundary": {"flags": dict(prereg["data_boundary"]["flags"])},
        "split_task_ids": split_ids,
        "split_task_ids_sha256": split_sha,
        "references_sealed_sha256": prereg["references_sealed"]["sha256"],
        "holdout_truth_read_phase": "EVAL",
        "physical_call_count": 0,
        "solver_processes_started": 0,
        "synthetic_call_count": len(eval_rows),
        "artifact_sha256": {
            "run_records.jsonl": sp.sha256_bytes(records_bytes),
            "fd_or_gradient_gate.json": gate_sha,
        },
    }
    manifest_bytes = _write_json(run / "data_manifest.json", data_manifest)
    manifest_sha = sp.sha256_bytes(manifest_bytes)

    model_manifest = {
        "schema_version": sp.S3_MODEL_MANIFEST_SCHEMA_VERSION,
        "run_id": FIXTURE_RUN_ID,
        "models": [
            {
                "arm_type": kind,
                "meta_seed": 0,
                "config": dict(prereg["models"][kind]["config"]),
                "path": "research/concorde_metaopt/evidence/s3/models/placeholder.json",
                "sha256": "a" * 64,
                "train_wall_s": 0.5,
                "peak_memory_mb": 128.0,
                "episode_bank_sha256": "b" * 64,
                "final_train_loss": 0.5,
            }
            for kind in sp.S3_MODEL_KINDS
        ],
    }
    _write_json(run / "model_manifest.json", model_manifest)

    run_config = {
        "schema_version": sp.S3_RUN_CONFIG_SCHEMA_VERSION,
        "run_id": FIXTURE_RUN_ID,
        "run_mode": "SMOKE",
        "prereg_id": prereg["prereg_id"],
        "prereg_digest": prereg["prereg_digest"],
        "analysis_plan_digest": prereg["analysis_plan_digest"],
        "code_sha": prereg["code_sha"],
        # 计划 v1.3e / A5 B01：FORMAL campaign 授权字段为 run_config 必需键；SMOKE 允许 null。
        "campaign_authorization_id": None,
        "campaign_authorization_utc": None,
        "family_package": {"family_package_sha256": evidence["package_sha256"]},
        "task_ids_sha256": prereg["family"]["task_ids_sha256"],
        "references_sealed_sha256": prereg["references_sealed"]["sha256"],
        "data_boundary": {"flags": dict(prereg["data_boundary"]["flags"])},
        "models": {kind: {"sha256": prereg["models"][kind]["sha256"]} for kind in sp.S3_MODEL_KINDS},
        "arms": {"arms": list(sp.S3_ARMS)},
        "budgets": {"budgets": list(SMOKE_BUDGETS), "k_shot": sp.S3_K_SHOT},
        "seeds": {"opt_seeds": list(SMOKE_OPT_SEEDS), "meta_seeds": list(SMOKE_META_SEEDS), "k_shot": sp.S3_K_SHOT},
        "episode_bank": {"banks": {"meta_seed_0": "c" * 64}, "episodes_per_bank": 16},
        "evaluation_grid": {"tasks": [task.task_id for task in tasks], "split": eval_split, "k_sweep": list(SMOKE_KS)},
        # 计划 v1.3b / R-S3-08A(a)：run_config 顶层 k_sweep 必需；SMOKE 亦写 [5]
        "k_sweep": [int(value) for value in an.FORMAL_K_SWEEP],
        "fd_or_gradient_gate": {
            "status": "PASS",
            "mode": sp.S3_FD_MODE,
            "max_relative_error": 1e-10,
            "coordinates": 8,
            "n_checked": 8,
            "coordinates_requested": 8,
            "coordinates_available": 185,
            "fd_gate_sha256": gate_sha,
            "override": True,
            "pilot_artifacts": {},
        },
        "record_counts": {
            "train": len(train_rows),
            "eval": len(eval_rows),
            "total": len(train_rows) + len(eval_rows),
        },
        "record_schemas": {"train": list(sp.S3_TRAIN_RECORD_FIELDS), "eval": list(sp.S3_EVAL_RECORD_FIELDS)},
        "resource_limits": dict(sp.S3_RESOURCE_LIMITS),
        "physical_call_count": 0,
        "evidence_scope": sp.S3_EVIDENCE_SCOPE,
        "scope_notes": scope_notes,
        "smoke_overrides": {
            "outer_steps": SMOKE_OUTER_STEPS,
            "meta_seeds": list(SMOKE_META_SEEDS),
            "budgets": list(SMOKE_BUDGETS),
            "opt_seeds": list(SMOKE_OPT_SEEDS),
            "eval_tasks": SMOKE_EVAL_TASKS,
            "k_sweep": list(SMOKE_KS),
            "fd_coordinates": 8,
        },
    }
    _write_json(run / "run_config.json", run_config)

    run_summary = {
        "schema_version": sp.S3_RUN_SUMMARY_SCHEMA_VERSION,
        "run_id": FIXTURE_RUN_ID,
        "run_mode": "SMOKE",
        "created_utc": FIXTURE_CREATED_UTC,
        "status": "COMPLETED",
        "record_counts": {"train": len(train_rows), "eval": len(eval_rows), "total": len(train_rows) + len(eval_rows)},
        "status_counts": {
            "train": {"OK": len(train_rows), "FAILED": 0},
            "eval": {"OK": len(eval_rows), "FAILED": 0},
        },
        "per_run": {task.task_id: len(SMOKE_BUDGETS) * len(sp.S3_ARMS) for task in tasks},
        "models": {kind: {"sha256": prereg["models"][kind]["sha256"]} for kind in sp.S3_MODEL_KINDS},
        "resources": {
            "total_wall_s": float(sum(record["wall_s"] for record in eval_rows)),
            "max_wall_s": 0.2,
            "max_peak_memory_mb": 256.0,
        },
        "determinism": {"repeats": 3},
        "fd_or_gradient_gate_sha256": gate_sha,
        "data_manifest_sha256": manifest_sha,
        "negative_controls": {"available": False},
        "physical_call_count": 0,
        "evidence_scope": sp.S3_EVIDENCE_SCOPE,
        "environment": {"python": "3.11.17", "platform": "windows", "torch": "2.8.0+cpu"},
        "scope_notes": scope_notes,
    }
    _write_json(run / "run_summary.json", run_summary)
    return {"run_dir": run, "tasks": tasks, "f_ref": f_ref, "eval_rows": eval_rows, "train_rows": train_rows, "gate_sha": gate_sha, "manifest_sha": manifest_sha}


# ---------------------------------------------------------------------------
# 模块级缓存 workspace（一次构建，多个测试类共享）
# ---------------------------------------------------------------------------
_WORKSPACE = None


def workspace():
    global _WORKSPACE
    if _WORKSPACE is None:
        base = Path(tempfile.mkdtemp(prefix="p4ra-s3-tests-"))
        atexit.register(shutil.rmtree, str(base), True)
        evidence = build_evidence_tree(base / "repo")
        run = build_smoke_run(evidence, base / "run")
        _WORKSPACE = {"base": base, "evidence": evidence, "run": run}
    return _WORKSPACE


def load_fixture_prereg(checks=None):
    ws = workspace()
    return an.load_s3_prereg(
        ws["evidence"]["prereg_path"],
        repo_root=ws["evidence"]["root"],
        verify_code_sha=False,
        verify_analysis_digest=False,
        checks=[] if checks is None else checks,
    )


def load_fixture_run(prereg=None, run_dir=None, checks=None):
    ws = workspace()
    return an.load_s3_run(
        ws["run"]["run_dir"] if run_dir is None else run_dir,
        prereg if prereg is not None else load_fixture_prereg(),
        checks=[] if checks is None else checks,
    )


def copy_run(mutator, tag="mut"):
    """复制 fixture run 目录，应用 mutator(run_dir) 后返回新目录。"""
    ws = workspace()
    target = Path(tempfile.mkdtemp(prefix="p4ra-s3-" + tag + "-", dir=str(ws["base"]))) / "run"
    shutil.copytree(ws["run"]["run_dir"], target)
    mutator(target)
    return target


def patch_json(path, mutator):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    mutator(payload)
    Path(path).write_bytes((_canonical(payload) + "\n").encode("utf-8"))


def expect_error(testcase, code, callable_, *args, **kwargs):
    """断言调用抛出 S3AnalysisError 且错误码匹配；返回异常对象。"""
    with testcase.assertRaises(an.S3AnalysisError) as context:
        callable_(*args, **kwargs)
    error = context.exception
    testcase.assertEqual(error.code, code, msg="实际错误码=" + str(error.code) + " message=" + str(findattr(error, "message", "")))
    return error


def findattr(obj, name, default=""):
    return getattr(obj, name, default)


# ---------------------------------------------------------------------------
# 共用辅助：prereg 负载重封 / 临时落盘
# ---------------------------------------------------------------------------
def _workspace_prereg_payload():
    ws = workspace()
    return json.loads(ws["evidence"]["prereg_path"].read_text(encoding="utf-8"))


def _reseal(payload):
    """按 A1 接口契约重算 prereg_id/prereg_digest（canonical JSON 口径）。"""
    body = json.loads(json.dumps(payload))
    body.pop("prereg_id", None)
    body.pop("prereg_digest", None)
    digest = sp.prereg_digest(body)
    body["prereg_id"] = "p4ra-s3-prereg-" + digest[:16]
    body["prereg_digest"] = sp.prereg_digest(body)
    return body


def _write_prereg_payload(payload, tag):
    ws = workspace()
    target = ws["base"] / ("prereg-" + str(tag))
    target.mkdir(parents=True, exist_ok=True)
    path = target / "preregistration.json"
    path.write_bytes((sp.canonical_json(payload) + "\n").encode("utf-8"))
    return path


def _load_prereg_payload(path, checks=None):
    ws = workspace()
    return an.load_s3_prereg(
        path,
        repo_root=ws["evidence"]["root"],
        verify_code_sha=False,
        verify_analysis_digest=False,
        checks=[] if checks is None else checks,
    )


def _mutated_prereg(mutator, *, reseal=True):
    payload = _workspace_prereg_payload()
    mutator(payload)
    return _reseal(payload) if reseal else payload


def _prereg_error(testcase, code, payload):
    path = _write_prereg_payload(payload, "neg-" + str(testcase.id()).split(".")[-1][:24])
    return expect_error(testcase, code, _load_prereg_payload, path)


# ---------------------------------------------------------------------------
# B 段：prereg 强校验（计划 §6、R-S3-04）
# ---------------------------------------------------------------------------
class PreregValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checks = []
        ws = workspace()
        cls.prereg = load_fixture_prereg(cls.checks)
        cls.evidence = ws["evidence"]

    def test_load_ok_identity(self):
        self.assertTrue(str(self.prereg.prereg_id).startswith("p4ra-s3-prereg-"))
        self.assertEqual(len(str(self.prereg.prereg_digest)), 64)
        self.assertEqual(self.prereg.prereg_digest, sp.prereg_digest(json.loads(self.prereg.raw.decode("utf-8"))))
        self.assertEqual(len(str(self.prereg.analysis_plan_digest)), 64)
        self.assertEqual(int(self.prereg.physical_call_count), 0)

    def test_load_checks_all_pass_or_disclosed(self):
        statuses = [str(item.get("status")) for item in self.checks]
        self.assertTrue(statuses, "prereg 加载应产出校验项")
        self.assertNotIn("FAIL", statuses)
        self.assertGreaterEqual(len(statuses), 15)

    def test_figures_ten_keys(self):
        self.assertEqual(set(self.prereg.figures.keys()), set(sp.S3_FIGURES.keys()))
        self.assertEqual(len(self.prereg.figures), 10)

    def test_split_counts_and_budgets(self):
        self.assertEqual(self.prereg.split_counts, dict(sp.S3_SPLIT_COUNTS))
        self.assertEqual(tuple(self.prereg.budgets_list), tuple(sp.S3_BUDGETS))
        family_raw = self.prereg.obj["family"]
        self.assertEqual(int(family_raw.get("FAMILY_SEED", family_raw.get("family_seed"))), int(sp.S3_FAMILY_SEED))
        self.assertEqual(str(self.prereg.family["family_id"]), sp.S3_FAMILY_ID)

    def test_data_boundary_allowed_splits(self):
        allowed = list(self.prereg.data_boundary["allowed_splits"])
        self.assertEqual(len(allowed), 6)
        self.assertIn("dev", allowed)
        self.assertIn("meta_test", allowed)

    def test_unknown_top_key_disclosed(self):
        payload = _mutated_prereg(lambda data: data.__setitem__("extra_note", "unexpected"))
        checks = []
        path = _write_prereg_payload(payload, "unknown-top")
        prereg = _load_prereg_payload(path, checks)
        self.assertTrue(prereg.prereg_id.startswith("p4ra-s3-prereg-"))
        disclosed = [item for item in checks if str(item.get("status")) == "DISCLOSED"]
        self.assertTrue(any("unknown" in str(item.get("check")) for item in disclosed), msg=str(disclosed))

    def test_digest_tamper_rejected(self):
        payload = _workspace_prereg_payload()
        payload["created_utc"] = "2026-11-07T07:00:00Z"
        _prereg_error(self, an.S3_ANALYSIS_PREREG_DIGEST_MISMATCH, payload)

    def test_missing_top_key_rejected(self):
        payload = _mutated_prereg(lambda data: data.pop("figures"))
        _prereg_error(self, an.S3_ANALYSIS_PREREG_SCHEMA_INVALID, payload)

    def test_placeholder_rejected(self):
        payload = _mutated_prereg(lambda data: data.__setitem__("created_utc", "<TBD>"))
        _prereg_error(self, an.S3_ANALYSIS_PREREG_PLACEHOLDER, payload)

    def test_physical_call_count_nonzero_rejected(self):
        payload = _mutated_prereg(lambda data: data.__setitem__("physical_call_count", 1))
        _prereg_error(self, an.S3_ANALYSIS_PREREG_PHYSICAL_CALLS, payload)

    def test_figures_missing_key_rejected(self):
        def drop_one(data):
            data["figures"].pop(next(iter(data["figures"])))

        payload = _mutated_prereg(drop_one)
        _prereg_error(self, an.S3_ANALYSIS_PREREG_SCHEMA_INVALID, payload)

    def test_holm_family_size_changed_rejected(self):
        payload = _mutated_prereg(lambda data: data["statistics"]["holm"].__setitem__("family_size", 3))
        _prereg_error(self, an.S3_ANALYSIS_PREREG_BINDING_MISMATCH, payload)

    def test_comparator_changed_rejected(self):
        payload = _mutated_prereg(lambda data: data["endpoints"]["C1"].__setitem__("comparator", "S3-BO-RANDOM"))
        _prereg_error(self, an.S3_ANALYSIS_COMPARATOR_MISMATCH, payload)

    def test_split_counts_changed_rejected(self):
        payload = _mutated_prereg(lambda data: data["family"]["split_counts"].__setitem__("meta_train", 59))
        _prereg_error(self, an.S3_ANALYSIS_PREREG_BINDING_MISMATCH, payload)

    def test_schema_version_changed_rejected(self):
        payload = _mutated_prereg(lambda data: data.__setitem__("schema_version", "p4ra-s3-prereg-v999"))
        _prereg_error(self, an.S3_ANALYSIS_PREREG_BINDING_MISMATCH, payload)

    def test_allowed_splits_removed_rejected(self):
        payload = _mutated_prereg(lambda data: data["data_boundary"]["allowed_splits"].remove("dev"))
        _prereg_error(self, an.S3_ANALYSIS_PREREG_BINDING_MISMATCH, payload)

    def test_code_sha_bad_format_rejected(self):
        payload = _mutated_prereg(lambda data: data.__setitem__("code_sha", "z" * 64))
        _prereg_error(self, an.S3_ANALYSIS_PREREG_SCHEMA_INVALID, payload)

    def test_non_canonical_file_rejected(self):
        payload = _reseal(_workspace_prereg_payload())
        ws = workspace()
        target = ws["base"] / "prereg-noncanonical"
        target.mkdir(parents=True, exist_ok=True)
        path = target / "preregistration.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        expect_error(self, an.S3_ANALYSIS_PREREG_FILE_INVALID, _load_prereg_payload, path)


class EvidenceLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ws = workspace()
        cls.root = ws["evidence"]["root"]
        cls.prereg = load_fixture_prereg()

    def test_load_references_sealed(self):
        checks = []
        references = an.load_references_sealed(self.prereg, repo_root=self.root, checks=checks)
        self.assertEqual(len(references), int(sp.S3_REFERENCE_COUNT))
        self.assertEqual(len(set(references.keys())), len(references))
        sample = references[sorted(references)[0]]
        self.assertIn("f_ref", sample)
        self.assertIn("reference_kind", sample)
        self.assertEqual(len(sample.get("u_star", [])), 12)
        self.assertTrue(any(str(item.get("status")) == "PASS" for item in checks))

    def test_load_family_package(self):
        checks = []
        package = an.load_family_package(self.prereg, repo_root=self.root, checks=checks)
        self.assertTrue(isinstance(package, dict), msg=type(package).__name__)
        self.assertEqual(str(package.get("family_id")), sp.S3_FAMILY_ID)
        self.assertEqual(int(package.get("split_counts", {}).get("meta_train")), int(sp.S3_SPLIT_COUNTS["meta_train"]))


# ---------------------------------------------------------------------------
# C 段：run 产物（run_config / summary / data_manifest / model_manifest / gate / records）
# ---------------------------------------------------------------------------
def _run_error(testcase, code, mutator, tag):
    run_dir = copy_run(mutator, tag=tag)
    return expect_error(testcase, code, load_fixture_run, None, run_dir)


def _mutate_json(name, mutator):
    def apply(run_dir):
        patch_json(Path(run_dir) / name, mutator)

    return apply


class RunArtifactValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checks = []
        cls.s3_run = load_fixture_run(checks=cls.checks)

    def test_load_ok_smoke_grid(self):
        self.assertEqual(self.s3_run.run_mode, "SMOKE")
        self.assertTrue(self.s3_run.is_smoke)
        self.assertEqual(len(self.s3_run.grid["task_ids"]), SMOKE_EVAL_TASKS)
        self.assertEqual(tuple(self.s3_run.grid["budgets"]), tuple(SMOKE_BUDGETS))
        self.assertEqual(tuple(self.s3_run.grid["opt_seeds"]), tuple(SMOKE_OPT_SEEDS))
        self.assertEqual(tuple(self.s3_run.grid["meta_seeds"]), tuple(SMOKE_META_SEEDS))
        self.assertEqual(int(self.s3_run.grid["run_count"]), 40)
        self.assertEqual(int(self.s3_run.grid["eval_records_expected"]), 3840)
        self.assertEqual(int(self.s3_run.grid["train_expected"]), 4)
        self.assertEqual(int(self.s3_run.grid["outer_steps"]), SMOKE_OUTER_STEPS)
        self.assertEqual(len(self.s3_run.per_run), 40)
        self.assertEqual(sum(int(item["hit_count"]) for item in self.s3_run.per_run) >= 0, True)

    def test_checks_include_run_artifacts(self):
        names = {str(item.get("check")) for item in self.checks}
        for expected in (
            "run_config_schema",
            "run_config_prereg_binding",
            "run_summary_schema",
            "run_records_budget",
            "data_manifest_boundary",
            "data_manifest_file_sha256",
            "model_manifest_schema",
            "fd_gate_artifact",
        ):
            self.assertIn(expected, names)
        self.assertNotIn("FAIL", [str(item.get("status")) for item in self.checks])

    def test_run_config_missing_arms_rejected(self):
        _run_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, _mutate_json("run_config.json", lambda data: data.pop("arms")), "cfg-no-arms")

    def test_run_config_formal_with_overrides_rejected(self):
        def mutate(data):
            data["run_mode"] = "FORMAL"

        _run_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, _mutate_json("run_config.json", mutate), "cfg-formal")

    def test_run_config_prereg_id_mismatch_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_RUN_BINDING_MISMATCH,
            _mutate_json("run_config.json", lambda data: data.__setitem__("prereg_id", "p4ra-s3-prereg-deadbeefdeadbeef")),
            "cfg-prereg-id",
        )

    def test_run_config_missing_smoke_overrides_rejected(self):
        _run_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, _mutate_json("run_config.json", lambda data: data.pop("smoke_overrides")), "cfg-no-smoke")

    def test_run_config_smoke_missing_eval_tasks_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
            _mutate_json("run_config.json", lambda data: data["smoke_overrides"].pop("eval_tasks")),
            "cfg-smoke-key",
        )

    def test_run_config_budget_mismatch_rejected(self):
        def mutate(data):
            data["budgets"]["budgets"] = [32, 128]

        _run_error(self, an.S3_ANALYSIS_BUDGET_MISMATCH, _mutate_json("run_config.json", mutate), "cfg-budget")

    def test_run_config_record_counts_mismatch_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_BUDGET_MISMATCH,
            _mutate_json("run_config.json", lambda data: data["record_counts"].__setitem__("eval", 3839)),
            "cfg-counts",
        )

    def test_run_config_train_expected_mismatch_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_BUDGET_MISMATCH,
            _mutate_json("run_config.json", lambda data: data["record_counts"].__setitem__("train_expected", 6)),
            "cfg-train-exp",
        )

    def test_run_config_fd_gate_fail_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", lambda data: data["fd_or_gradient_gate"].__setitem__("status", "FAIL")),
            "cfg-gate-fail",
        )

    def test_run_config_physical_nonzero_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_PREREG_PHYSICAL_CALLS,
            _mutate_json("run_config.json", lambda data: data.__setitem__("physical_call_count", 1)),
            "cfg-physical",
        )

    def test_run_summary_missing_resources_rejected(self):
        _run_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, _mutate_json("run_summary.json", lambda data: data.pop("resources")), "sum-no-res")

    def test_run_summary_run_mode_mismatch_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_RUN_BINDING_MISMATCH,
            _mutate_json("run_summary.json", lambda data: data.__setitem__("run_mode", "FORMAL")),
            "sum-mode",
        )

    def test_run_summary_bad_status_rejected(self):
        _run_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, _mutate_json("run_summary.json", lambda data: data.__setitem__("status", "BOGUS")), "sum-status")

    def test_run_summary_status_counts_missing_bucket_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
            _mutate_json("run_summary.json", lambda data: data["status_counts"]["eval"].pop("FAILED")),
            "sum-bucket",
        )

    def test_run_summary_physical_nonzero_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_PREREG_PHYSICAL_CALLS,
            _mutate_json("run_summary.json", lambda data: data.__setitem__("physical_call_count", 1)),
            "sum-physical",
        )

    def test_data_manifest_missing_field_rejected(self):
        _run_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, _mutate_json("data_manifest.json", lambda data: data.pop("artifact_sha256")), "man-field")

    def test_data_manifest_holdout_phase_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION,
            _mutate_json("data_manifest.json", lambda data: data.__setitem__("holdout_truth_read_phase", "DEV")),
            "man-phase",
        )

    def test_data_manifest_tampered_bytes_rejected(self):
        def mutate(run_dir):
            path = Path(run_dir) / "data_manifest.json"
            path.write_bytes(path.read_bytes() + b" ")

        _run_error(self, an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, mutate, "man-tamper")

    def test_model_manifest_duplicate_entry_rejected(self):
        def mutate(data):
            data["models"][1] = dict(data["models"][0])

        _run_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, _mutate_json("model_manifest.json", mutate), "model-dup")

    def test_gate_status_fail_rejected(self):
        _run_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, _mutate_json("fd_or_gradient_gate.json", lambda data: data.__setitem__("status", "FAIL")), "gate-fail")

    def test_gate_coordinate_count_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("fd_or_gradient_gate.json", lambda data: data["coordinates"].pop()),
            "gate-coords",
        )

    def test_gate_declared_max_error_rejected(self):
        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("fd_or_gradient_gate.json", lambda data: data.__setitem__("max_relative_error", 5e-6)),
            "gate-max",
        )

    def test_records_missing_line_rejected(self):
        def mutate(run_dir):
            path = Path(run_dir) / "run_records.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

        _run_error(self, an.S3_ANALYSIS_RECORD_INVALID, mutate, "rec-drop")

    def test_records_duplicate_index_rejected(self):
        def mutate(run_dir):
            path = Path(run_dir) / "run_records.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            payload = json.loads(lines[-1])
            payload["evaluation_index"] = 1
            payload["record_digest"] = sp.record_digest({key: value for key, value in payload.items() if key != "record_digest"})
            lines[-1] = _canonical(payload)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        _run_error(self, an.S3_ANALYSIS_RECORD_INVALID, mutate, "rec-dup")

    def test_records_feasible_inconsistent_rejected(self):
        def mutate(run_dir):
            path = Path(run_dir) / "run_records.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            payload = json.loads(lines[-1])
            payload["feasible"] = not bool(payload["feasible"])
            payload["record_digest"] = sp.record_digest({key: value for key, value in payload.items() if key != "record_digest"})
            lines[-1] = _canonical(payload)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        _run_error(self, an.S3_ANALYSIS_RECORD_INVALID, mutate, "rec-feas")

    def test_records_phase_split_mismatch_rejected(self):
        def mutate(run_dir):
            path = Path(run_dir) / "run_records.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            payload = json.loads(lines[-1])
            payload["phase"] = "EVAL"
            payload["holdout_truth_read"] = False
            payload["record_digest"] = sp.record_digest({key: value for key, value in payload.items() if key != "record_digest"})
            lines[-1] = _canonical(payload)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        _run_error(self, an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, mutate, "rec-phase")

    def test_records_design_dimension_rejected(self):
        def mutate(run_dir):
            path = Path(run_dir) / "run_records.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            payload = json.loads(lines[-1])
            payload["design"] = payload["design"][:11]
            payload["record_digest"] = sp.record_digest({key: value for key, value in payload.items() if key != "record_digest"})
            lines[-1] = _canonical(payload)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        _run_error(self, an.S3_ANALYSIS_RECORD_INVALID, mutate, "rec-design")

    def test_records_unknown_extra_field_disclosed_only(self):
        def mutate(run_dir):
            path = Path(run_dir) / "run_records.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            payload = json.loads(lines[-1])
            payload["extra_debug_note"] = "unexpected"
            payload["record_digest"] = sp.record_digest({key: value for key, value in payload.items() if key != "record_digest"})
            lines[-1] = _canonical(payload)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        run_dir = copy_run(mutate, tag="rec-extra")
        checks = []
        loaded = load_fixture_run(None, run_dir, checks)
        self.assertEqual(len(loaded.per_run), 40)
        self.assertNotIn("FAIL", [str(item.get("status")) for item in checks])
        self.assertTrue(any(str(item.get("status")) == "DISCLOSED" for item in checks))


# ---------------------------------------------------------------------------
# D 段：统计（Wilcoxon 精确/Pratt/置换、Holm、bootstrap、6 档决策、ANIL）
# ---------------------------------------------------------------------------
class StatisticsTests(unittest.TestCase):
    def test_average_ranks_with_ties(self):
        self.assertEqual(an._average_ranks([1.0, 3.0, -2.0, 2.0]), [1.0, 4.0, 2.5, 2.5])
        self.assertEqual(an._average_ranks([5.0]), [1.0])

    def test_doubled_rank_rejects_negative(self):
        self.assertEqual(an._doubled_rank(2.5), 5)
        expect_error(self, an.S3_ANALYSIS_INPUT_INVALID, an._doubled_rank, -0.5)

    def test_wilcoxon_exact_all_positive(self):
        result = an.wilcoxon_signed_rank_exact([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(result["method"], "exact_sign_flip_tie_aware")
        self.assertEqual(result["n_eff"], 10)
        self.assertEqual(result["n_zero"], 0)
        self.assertAlmostEqual(result["w_plus"], 55.0)
        self.assertAlmostEqual(result["p_two_sided"], 2.0 / 1024.0, places=15)
        self.assertEqual(result["zero_policy"], "DISCARDED")

    def test_wilcoxon_exact_zero_policy(self):
        result = an.wilcoxon_signed_rank_exact([0.0, 1.0, -2.0, 0.0, 3.0])
        self.assertEqual(result["n_total"], 5)
        self.assertEqual(result["n_zero"], 2)
        self.assertEqual(result["n_eff"], 3)
        self.assertGreater(result["p_two_sided"], 0.0)
        self.assertLessEqual(result["p_two_sided"], 1.0)

    def test_wilcoxon_exact_all_zero(self):
        result = an.wilcoxon_signed_rank_exact([0.0, 0.0, 0.0])
        self.assertEqual(result["n_eff"], 0)
        self.assertIsNone(result["p_two_sided"])

    def test_wilcoxon_exact_empty_rejected(self):
        expect_error(self, an.S3_ANALYSIS_INPUT_INVALID, an.wilcoxon_signed_rank_exact, [])

    def test_wilcoxon_exact_matches_bruteforce(self):
        cases = [
            [0.5 * index - 1.2 for index in range(10)],
            [1.0, -1.0, 2.0, -2.0, 3.0, -3.0, 0.4, -0.6],
            [1.0, 1.0, 2.0, 2.0, 3.0, -1.0, -2.0, 0.0, 4.0],
        ]
        for diffs in cases:
            exact = an.wilcoxon_signed_rank_exact(diffs)
            brute = an.wilcoxon_signed_rank_bruteforce(diffs)
            self.assertAlmostEqual(exact["p_two_sided"], brute["p_two_sided"], places=12)
            self.assertAlmostEqual(exact["w_plus"], brute["w_plus"], places=12)
            self.assertEqual(exact["n_eff"], brute["n_eff"])

    def test_wilcoxon_bruteforce_limit(self):
        diffs = [float(index + 1) for index in range(17)]
        expect_error(self, an.S3_ANALYSIS_INPUT_INVALID, an.wilcoxon_signed_rank_bruteforce, diffs)

    def test_wilcoxon_pratt_zero_included(self):
        result = an.wilcoxon_pratt([0.0, 1.0, 2.0, 3.0, 4.0])
        self.assertEqual(result["method"], "pratt_zero_included_rank")
        self.assertEqual(result["n_zero"], 1)
        self.assertEqual(result["n_eff"], 4)
        self.assertIsNotNone(result["p_two_sided"])

    def test_wilcoxon_permutation_deterministic(self):
        diffs = [0.5, -0.8, 1.2, -0.3, 0.9]
        first = an.wilcoxon_permutation(diffs)
        second = an.wilcoxon_permutation(diffs)
        self.assertEqual(first["method"], "sign_permutation")
        self.assertEqual(first["n_resamples"], 10000)
        self.assertEqual(first["seed"], 20261107)
        self.assertEqual(first["p_two_sided"], second["p_two_sided"])

    def test_holm_adjust_two_tests(self):
        rows = an.holm_adjust([("a", 0.01), ("b", 0.04)])
        self.assertEqual([row["rank"] for row in rows], [1, 2])
        self.assertAlmostEqual(rows[0]["p_holm"], 0.02, places=15)
        self.assertAlmostEqual(rows[1]["p_holm"], 0.04, places=15)
        self.assertTrue(rows[0]["reject"])
        self.assertTrue(rows[1]["reject"])
        missing = an.holm_adjust([("a", None), ("b", 0.01)])
        self.assertTrue(missing[0]["missing"])
        self.assertIsNone(missing[0]["p_holm"])

    def test_holm_rejects_bad_p(self):
        expect_error(self, an.S3_ANALYSIS_INPUT_INVALID, an.holm_adjust, [("a", 1.5)])

    def test_bootstrap_mean_ci(self):
        result = an.bootstrap_mean_ci([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(result["method"], "percentile_bootstrap_task_level")
        self.assertEqual(result["n_tasks"], 4)
        self.assertAlmostEqual(result["mean"], 2.5)
        self.assertAlmostEqual(result["median"], 2.5)
        self.assertLess(result["ci_low"], result["mean"])
        self.assertGreater(result["ci_high"], result["mean"])
        self.assertAlmostEqual(result["confidence_level"], 0.95)
        again = an.bootstrap_mean_ci([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(result["ci_low"], again["ci_low"])

    def test_bootstrap_mean_ci_missing_and_single(self):
        result = an.bootstrap_mean_ci([None, 2.0])
        self.assertEqual(result["n_tasks"], 1)
        self.assertEqual(result["n_missing"], 1)
        self.assertAlmostEqual(result["ci_low"], 2.0)
        empty = an.bootstrap_mean_ci([None, None])
        self.assertIsNone(empty["mean"])

    def test_bootstrap_median_ci(self):
        result = an.bootstrap_median_ci([1.0, 2.0, 3.0])
        self.assertAlmostEqual(result["median"], 2.0)
        self.assertLessEqual(result["ci_low"], result["ci_high"])

    def test_paired_summary(self):
        result = an.paired_summary([1.0, None, 3.0])
        self.assertEqual(result["n_total"], 3)
        self.assertEqual(result["n_missing"], 1)
        self.assertAlmostEqual(result["mean"], 2.0)
        self.assertAlmostEqual(result["min"], 1.0)
        self.assertAlmostEqual(result["max"], 3.0)

    def test_decide_layer_six_outcomes(self):
        base = {"threshold": 0.02, "benefit_direction": "positive", "n_eff": 20}
        self.assertEqual(an.decide_layer(p_value=0.01, effect=0.05, **base), an.D_SUPPORTED_BENEFIT)
        self.assertEqual(an.decide_layer(p_value=0.01, effect=-0.05, **base), an.D_SUPPORTED_HARM)
        self.assertEqual(an.decide_layer(p_value=0.01, effect=0.005, **base), an.D_NEGLIGIBLE_SIGNIFICANT)
        self.assertEqual(an.decide_layer(p_value=0.5, effect=-0.05, **base), an.D_DIRECTION_INCONSISTENT)
        self.assertEqual(an.decide_layer(p_value=0.5, effect=0.0, **base), an.D_NULL)
        self.assertEqual(an.decide_layer(p_value=0.01, effect=0.05, threshold=0.02, benefit_direction="positive", n_eff=10), an.D_INCONCLUSIVE)
        self.assertEqual(an.decide_layer(p_value=None, effect=0.05, **base), an.D_INCONCLUSIVE)

    def test_decide_layer_negative_direction(self):
        decision = an.decide_layer(p_value=0.01, effect=-0.05, threshold=0.01, benefit_direction="negative", n_eff=20)
        self.assertEqual(decision, an.D_SUPPORTED_BENEFIT)
        expect_error(self, an.S3_ANALYSIS_INPUT_INVALID, an.decide_layer, p_value=0.01, effect=0.0, threshold=0.01, benefit_direction="sideways", n_eff=20)

    def test_decide_overall_priority(self):
        benefit = an.D_SUPPORTED_BENEFIT
        null = an.D_NULL
        harmful = an.D_SUPPORTED_HARM
        inconsistent = an.D_DIRECTION_INCONSISTENT
        inconclusive = an.D_INCONCLUSIVE
        self.assertEqual(an.decide_overall({"B64": benefit, "B128": benefit}), an.O_BENEFIT)
        self.assertEqual(an.decide_overall({"B64": benefit, "B128": null}), an.O_NO_EVIDENCE)
        self.assertEqual(an.decide_overall({"B64": inconclusive, "B128": benefit}), an.O_INCONCLUSIVE)
        self.assertEqual(an.decide_overall({"B64": harmful, "B128": benefit}), an.O_HARM)
        self.assertEqual(an.decide_overall({"B64": inconsistent, "B128": null}), an.O_DIRECTION_INCONSISTENT)
        self.assertEqual(an.decide_overall({"B64": null, "B128": null}), an.O_NO_EVIDENCE)

    def test_decide_overall_invalid_inputs(self):
        expect_error(self, an.S3_ANALYSIS_INPUT_INVALID, an.decide_overall, {"B64": an.D_NULL})
        expect_error(self, an.S3_ANALYSIS_INPUT_INVALID, an.decide_overall, {"B64": an.D_NULL, "B128": "BOGUS"})

    def test_overall_decision_table_complete(self):
        table = an.overall_decision_table()
        self.assertEqual(len(an.LAYER_DECISIONS), 6)
        self.assertEqual(len(table), 36)
        allowed = {an.O_BENEFIT, an.O_HARM, an.O_DIRECTION_INCONSISTENT, an.O_INCONCLUSIVE, an.O_NO_EVIDENCE}
        self.assertTrue(set(table.values()) <= allowed)

    def test_anil_decision_branches(self):
        self.assertEqual(
            an.anil_decision(anil_mean=0.3, random_mean=0.3, anil_cost=1.0, con_cost=2.0),
            "ANIL_COST_EFFICIENT",
        )
        self.assertEqual(
            an.anil_decision(anil_mean=0.1, random_mean=0.3, anil_cost=1.0, con_cost=2.0, anil_minus_random_ci={"ci_high": -0.1}),
            "ANIL_INFERIOR",
        )
        self.assertEqual(
            an.anil_decision(anil_mean=0.1, random_mean=0.3, anil_cost=2.0, con_cost=2.0),
            "ANIL_INCONCLUSIVE",
        )
        self.assertEqual(
            an.anil_decision(anil_mean=None, random_mean=0.3, anil_cost=1.0, con_cost=2.0),
            "ANIL_INCONCLUSIVE",
        )


# ---------------------------------------------------------------------------
# 端点、聚合与辅助 builder
# ---------------------------------------------------------------------------
class EndpointBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s3_run = load_fixture_run()
        cls.references = an.load_references_sealed(
            load_fixture_prereg(), repo_root=workspace()["evidence"]["root"], checks=[]
        )
        cls.checks = []
        cls.endpoints = an.compute_run_endpoints(cls.s3_run, cls.references, checks=cls.checks)
        cls.main, cls.aux = an.split_main_and_aux(cls.endpoints)
        cls.tasks = sorted(cls.s3_run.grid["task_ids"])
        cls.grid = cls.s3_run.grid

    def test_compute_run_endpoints_count(self):
        self.assertEqual(len(self.endpoints), 40)
        self.assertEqual(len(self.main), 40)
        self.assertEqual(len(self.aux), 0)
        names = {str(item.get("check")) for item in self.checks}
        self.assertIn("gap_reference_coverage", names)
        self.assertIn("surrogate_error_metrics", names)

    def test_compute_run_endpoints_values(self):
        for item in self.endpoints:
            self.assertEqual(item["split"], "meta_validation")
            self.assertAlmostEqual(item["feasible_hit_rate"], item["feasible_count"] / float(item["budget"]))
            self.assertAlmostEqual(item["adaptation_cost"], item["total_cost"] + float(item["budget"]))
            self.assertEqual(item["scoring_count"], item["budget"])
            self.assertIsNone(item["surrogate_rmse"])
            self.assertIsNone(item["surrogate_mae"])
            if item["best_feasible_value"] is None:
                self.assertIsNone(item["gap_to_reference"])
            else:
                self.assertIsNotNone(item["gap_to_reference"])
                self.assertGreaterEqual(item["gap_to_reference"], 0.0)

    def test_split_main_and_aux_with_aux_rows(self):
        fake = [dict(self.main[0], split="meta_test_ood"), dict(self.main[1], split="meta_validation")]
        main, aux = an.split_main_and_aux(fake)
        self.assertEqual(len(main), 1)
        self.assertEqual(len(aux), 1)

    def test_aggregate_task_values(self):
        aggregated = an.aggregate_task_values(self.endpoints, endpoint_name="feasible_hit_rate")
        self.assertEqual(len(aggregated), 40)
        for key, entry in aggregated.items():
            self.assertEqual(len(key), 3)
            self.assertEqual(entry["n_total"], 1)
            self.assertEqual(entry["n_missing"], 0)
            self.assertIsNotNone(entry["value"])

    def test_aggregate_task_values_null_not_imputed(self):
        fake = [
            {"task_id": "t1", "budget": 64, "arm_id": "A", "feasible_hit_rate": None},
            {"task_id": "t1", "budget": 64, "arm_id": "A", "feasible_hit_rate": 0.5},
        ]
        aggregated = an.aggregate_task_values(fake, endpoint_name="feasible_hit_rate")
        entry = aggregated[("t1", 64, "A")]
        self.assertAlmostEqual(entry["value"], 0.5)
        self.assertEqual(entry["n_missing"], 1)
        self.assertEqual(entry["n_total"], 2)

    def test_build_endpoint_summary(self):
        checks = []
        summary = an.build_endpoint_summary(
            self.main,
            endpoints_to_report=an.INFERENCE_ENDPOINTS,
            tasks=self.tasks,
            grid=self.grid,
            checks=checks,
        )
        self.assertEqual(len(summary["rows"]), 2 * 5 * 2)
        self.assertEqual(len(summary["per_task_rows"]), 2 * 5 * 2 * len(self.tasks))
        self.assertEqual(set(summary["aggregated"]), set(an.INFERENCE_ENDPOINTS))
        row = summary["rows"][0]
        for field in ("endpoint", "endpoint_role", "budget", "arm_id", "n_tasks", "n_null", "null_ratio", "mean", "median", "ci_low", "ci_high", "bootstrap_resamples", "bootstrap_seed", "comparator"):
            self.assertIn(field, row)
        self.assertEqual(row["bootstrap_seed"], 20261107)
        self.assertEqual(row["n_tasks"], len(self.tasks))

    def test_build_inference(self):
        checks = []
        inference = an.build_inference(self.main, tasks=self.tasks, grid=self.grid, checks=checks)
        self.assertEqual(set(inference["families"]), {an.C1_FAMILY_ID, an.C2_FAMILY_ID})
        for family_rows in inference["families"].values():
            self.assertEqual(len(family_rows), 2)
            for row in family_rows:
                self.assertEqual(row["wilcoxon_method"], "exact_sign_flip_tie_aware")
                self.assertEqual(row["permutation_seed"], 20261107)
                self.assertEqual(row["arm_a"], "S3-BO-FOMAML-CON")
                self.assertEqual(row["arm_b"], "S3-BO-FOMAML-OBJ")
        self.assertEqual(len(inference["holm_rows"]), 4)
        self.assertEqual(set(inference["c1_decisions"]), {"B64", "B128"})
        self.assertEqual(set(inference["c2_decisions"]), {"B64", "B128"})
        self.assertEqual(inference["overall_decision"], an.O_INCONCLUSIVE)
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("c1_c2_comparator"), "PASS")

    def test_ensure_comparator_positive_and_negative(self):
        an._ensure_comparator("S3-BO-FOMAML-CON", "S3-BO-FOMAML-OBJ", test_id="C1a")
        error = expect_error(self, an.S3_ANALYSIS_COMPARATOR_MISMATCH, an._ensure_comparator, "S3-BO-FOMAML-OBJ", "S3-BO-FOMAML-CON", test_id="C1a")
        self.assertIn("CON", str(error.message))

    def test_build_null_disclosure(self):
        checks = []
        rows = an.build_null_disclosure(self.main, tasks=self.tasks, grid=self.grid, checks=checks)
        self.assertEqual(len(rows), (len(an.INFERENCE_ENDPOINTS) + len(an.DESCRIPTIVE_ENDPOINTS)) * 5 * 2)
        for row in rows:
            self.assertEqual(row["n_cells"], len(self.tasks))
            self.assertGreaterEqual(row["n_null"], 0)
            self.assertLessEqual(row["n_null"], len(self.tasks))
            self.assertAlmostEqual(row["null_ratio"], row["n_null"] / float(len(self.tasks)))
        self.assertIn("null_disclosure", {str(item.get("check")) for item in checks})

    def test_build_cost_rows(self):
        checks = []
        rows = an.build_cost_rows(self.endpoints, grid=self.grid, checks=checks)
        self.assertEqual(len(rows), 5 * 2)
        for row in rows:
            self.assertIn("total_cost_mean_s", row)
            self.assertIn("adaptation_cost_mean", row)
            self.assertEqual(row["n_runs"], len(self.tasks))

    def test_build_anil_row(self):
        checks = []
        row = an.build_anil_row(self.endpoints, tasks=self.tasks, grid=self.grid, checks=checks)
        self.assertEqual(len(row), 14)
        self.assertEqual(row["arm_id"], "S3-BO-ANIL-CON")
        self.assertEqual(row["comparison_arm"], "S3-BO-RANDOM")
        self.assertIn(row["decision"], ("ANIL_COST_EFFICIENT", "ANIL_INFERIOR", "ANIL_INCONCLUSIVE"))

    def test_build_negative_control_rows(self):
        checks = []
        rows = an.build_negative_control_rows(self.s3_run, self.endpoints, tasks=self.tasks, grid=self.grid, checks=checks)
        self.assertEqual(len(rows), 15)
        self.assertEqual([row["control_id"] for row in rows], ["NC-" + str(index).zfill(2) for index in range(1, 16)])
        self.assertTrue({str(row["status"]) for row in rows} <= {"PASS", "FAIL", "DISCLOSED"})

    def test_build_ood_and_determinism_rows(self):
        checks = []
        ood = an.build_ood_rows(self.s3_run, self.endpoints, grid=self.grid, checks=checks)
        self.assertEqual(len(ood), 5 * 2)
        self.assertTrue(all(row["status"] == "NOT_RUN" for row in ood))
        determinism = an.build_determinism_rows(self.s3_run, checks=checks)
        self.assertEqual(len(determinism), 1)
        self.assertEqual(determinism[0]["status"], "NOT_RUN")


# ---------------------------------------------------------------------------
# E 段：SMOKE 端到端（7 CSV + aggregate.json + figure_status.json）与 CLI
# ---------------------------------------------------------------------------
import csv  # noqa: E402  (仅测试辅助使用)


def _csv_rows(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


_E2E_CACHE = {}


def _e2e_runs():
    """缓存两套分析输出（figures on/off），避免重复跑统计。"""
    if _E2E_CACHE:
        return _E2E_CACHE
    ws = workspace()
    evidence = ws["evidence"]
    base = ws["base"]
    plain_dir = base / "analysis-no-figures"
    figures_dir = base / "analysis-figures"
    plain = an.analyze_s3_run(
        evidence["prereg_path"],
        ws["run"]["run_dir"],
        plain_dir,
        repo_root=evidence["root"],
        generate_figures=False,
    )
    rendered = an.analyze_s3_run(
        evidence["prereg_path"],
        ws["run"]["run_dir"],
        figures_dir,
        repo_root=evidence["root"],
        generate_figures=True,
    )
    _E2E_CACHE.update({"plain": plain, "plain_dir": plain_dir, "rendered": rendered, "rendered_dir": figures_dir, "ws": ws})
    return _E2E_CACHE


class AnalyzeEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = _e2e_runs()
        cls.plain = cls.cache["plain"]
        cls.rendered = cls.cache["rendered"]
        cls.plain_dir = cls.cache["plain_dir"]
        cls.rendered_dir = cls.cache["rendered_dir"]

    def test_analysis_status_and_artifacts(self):
        self.assertEqual(self.plain["status"], "PASS")
        self.assertEqual(self.plain["run_mode"], "SMOKE")
        self.assertEqual(len(self.plain["artifacts"]), 9)
        self.assertEqual(self.plain["n_tasks"], SMOKE_EVAL_TASKS)
        self.assertEqual(self.plain["record_counts"]["eval"], 3840)
        for name in ("aggregate.json", "figure_status.json", "s3_endpoint_tables.csv", "s3_per_task_endpoint_values.csv", "s3_holm_family.csv", "s3_null_disclosure.csv", "s3_negative_controls.csv", "s3_ood_descriptives.csv", "s3_cost_table.csv"):
            self.assertTrue((self.plain_dir / name).is_file(), msg=name)

    def test_aggregate_contract_fields(self):
        aggregate = json.loads((self.plain_dir / "aggregate.json").read_text(encoding="utf-8"))
        for field in ("schema_version", "run_id", "run_mode", "smoke", "endpoint_rows", "inference", "figure_status", "negative_controls", "outputs", "checks", "data_boundary", "record_counts", "run_grid"):
            self.assertIn(field, aggregate)
        self.assertEqual(aggregate["run_mode"], "SMOKE")
        self.assertTrue(aggregate["smoke"])
        self.assertEqual(aggregate["run_id"], FIXTURE_RUN_ID)
        self.assertEqual(len(aggregate["data_boundary"]["allowed_splits"]), 6)
        self.assertEqual(aggregate["overall_decision"], an.O_INCONCLUSIVE)
        self.assertEqual(aggregate["outputs"].__len__(), 8)
        self.assertEqual(aggregate["figure_status"]["summary"]["rendered"], 0)

    def test_checks_never_fail(self):
        aggregate = json.loads((self.plain_dir / "aggregate.json").read_text(encoding="utf-8"))
        statuses = [str(item.get("status")) for item in aggregate["checks"]]
        self.assertTrue(statuses)
        self.assertNotIn("FAIL", statuses)
        disclosed = {str(item.get("check")) for item in aggregate["disclosed_checks"]}
        self.assertIn("figures", disclosed)

    def test_negative_controls_rows(self):
        rows = _csv_rows(self.plain_dir / "s3_negative_controls.csv")
        self.assertEqual(len(rows), 15)
        self.assertEqual([row["control_id"] for row in rows], ["NC-" + str(index).zfill(2) for index in range(1, 16)])
        self.assertNotIn("FAIL", {row["status"] for row in rows})

    def test_inference_two_families_two_tests(self):
        aggregate = json.loads((self.plain_dir / "aggregate.json").read_text(encoding="utf-8"))
        inference = aggregate["inference"]
        self.assertEqual(set(inference["families"]), {an.C1_FAMILY_ID, an.C2_FAMILY_ID})
        for rows in inference["families"].values():
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["test_id"] for row in rows}, {"C1a", "C1b"} if rows[0]["family_id"] == an.C1_FAMILY_ID else {"C2a", "C2b"})
            is_c1 = rows[0]["family_id"] == an.C1_FAMILY_ID
            for row in rows:
                self.assertEqual(row["decision"], an.D_INCONCLUSIVE)
                self.assertTrue(row["n_eff_below_min"])
                self.assertEqual(row["n_paired"], SMOKE_EVAL_TASKS)
                if is_c1:
                    self.assertEqual(row["n_eff"], SMOKE_EVAL_TASKS)
                else:
                    # C2 的 fixture 各臂 gap 相同 → 差分为 0，零差全部丢弃
                    self.assertEqual(row["n_eff"], 0)
        self.assertEqual(len(aggregate["holms"]), 4)
        self.assertEqual(inference["overall_decision"], an.O_INCONCLUSIVE)
        self.assertEqual(set(inference["c1_decisions"].values()), {an.D_INCONCLUSIVE})

    def test_endpoint_tables_csv(self):
        rows = _csv_rows(self.plain_dir / "s3_endpoint_tables.csv")
        self.assertEqual(len(rows), 100)
        self.assertEqual({row["endpoint"] for row in rows}, set(an.INFERENCE_ENDPOINTS) | set(an.DESCRIPTIVE_ENDPOINTS))
        for row in rows:
            self.assertIn(row["endpoint_role"], ("inference", "descriptive"))
        per_task = _csv_rows(self.plain_dir / "s3_per_task_endpoint_values.csv")
        self.assertEqual(len(per_task), len(an.INFERENCE_ENDPOINTS) * 5 * 2 * SMOKE_EVAL_TASKS)

    def test_figure_status_when_disabled(self):
        status = json.loads((self.plain_dir / "figure_status.json").read_text(encoding="utf-8"))
        self.assertEqual(set(status["figures"]), set(an.FIGURE_KEYS))
        self.assertEqual(status["summary"]["rendered"], 0)
        self.assertEqual(status["summary"]["not_run"], 10)
        self.assertTrue(all(item["path"] is None for item in status["figures"].values()))

    def test_figures_rendered(self):
        status = json.loads((self.rendered_dir / "figure_status.json").read_text(encoding="utf-8"))
        self.assertEqual(len(status["figures"]), 10)
        for key in ("fig2_kshot_rmse_k0_k1_k3_k5", "fig7_ood_diagnostics", "fig10_vspaero_gate_status"):
            self.assertEqual(status["figures"][key]["status"], "NOT_RUN", msg=key)
        rendered = [key for key, item in status["figures"].items() if item["status"] == "RENDERED"]
        self.assertGreaterEqual(len(rendered), 6)
        self.assertEqual(status["summary"]["rendered"], len(rendered))
        for key in rendered:
            item = status["figures"][key]
            self.assertTrue(Path(item["path"]).is_file(), msg=key)
            self.assertTrue(Path(item["csv_path"]).is_file(), msg=key)
            self.assertEqual(Path(item["path"]).suffix, ".png")

    def test_figure_data_files_recorded(self):
        aggregate = json.loads((self.rendered_dir / "aggregate.json").read_text(encoding="utf-8"))
        files = aggregate["figure_data_files"]
        self.assertEqual(sum(1 for value in files.values() if value is not None), 7)
        self.assertEqual(len(files), 10)

    def test_scope_and_smoke_disclosure(self):
        aggregate = json.loads((self.plain_dir / "aggregate.json").read_text(encoding="utf-8"))
        self.assertEqual(aggregate["evidence_scope"], "DEVELOPMENT_VALIDATION_ONLY")
        self.assertEqual(aggregate["development_set"], "meta_validation")
        checks = {str(item.get("check")): str(item.get("status")) for item in aggregate["checks"]}
        self.assertEqual(checks.get("smoke_overrides"), "DISCLOSED")
        self.assertEqual(aggregate["prereg"]["prereg_id"], load_fixture_prereg().prereg_id)

    def test_output_dir_requires_overwrite(self):
        target = self.plain_dir
        expect_error(
            self,
            an.S3_ANALYSIS_OUTPUT_INVALID,
            an.analyze_s3_run,
            self.cache["ws"]["evidence"]["prereg_path"],
            self.cache["ws"]["run"]["run_dir"],
            target,
            repo_root=self.cache["ws"]["evidence"]["root"],
            generate_figures=False,
        )
        result = an.analyze_s3_run(
            self.cache["ws"]["evidence"]["prereg_path"],
            self.cache["ws"]["run"]["run_dir"],
            target,
            repo_root=self.cache["ws"]["evidence"]["root"],
            generate_figures=False,
            overwrite=True,
        )
        self.assertEqual(result["status"], "PASS")

    def test_cli_main(self):
        ws = self.cache["ws"]
        output = ws["base"] / "analysis-cli"
        code = an.main([
            "--prereg", str(ws["evidence"]["prereg_path"]),
            "--run-dir", str(ws["run"]["run_dir"]),
            "--output-dir", str(output),
            "--repo-root", str(ws["evidence"]["root"]),
            "--no-generate-figures",
            "--json",
        ])
        self.assertEqual(code, 0)
        self.assertTrue((output / "aggregate.json").is_file())

    def test_cli_missing_argument(self):
        with self.assertRaises(SystemExit):
            an.main(["--prereg", "x"])


# ---------------------------------------------------------------------------
# R-S3-05：R-S3-02 降网格 fallback 容错 + run 目录未知文件容忍
# ---------------------------------------------------------------------------
class RS302FallbackTests(unittest.TestCase):
    """执行层并行化（R-S3-05）后：主网格与 R-S3-02 降网格二者都接受，并披露实际 run/evals。"""

    @classmethod
    def setUpClass(cls):
        cls.prereg = load_fixture_prereg()

    def _formal_config(self, opt_count):
        return {
            "run_mode": "FORMAL",
            "arms": {"arms": [{"arm_id": arm} for arm in sp.S3_ARMS]},
            "budgets": {"budgets": list(sp.S3_BUDGETS)},
            "seeds": {
                "opt_seeds": list(range(int(opt_count))),
                "meta_seeds": list(sp.S3_MODEL_META_SEEDS),
                "k_shot": sp.S3_K_SHOT,
            },
            "evaluation_grid": {
                "tasks": [
                    "meta_test-task-" + str(index).zfill(3)
                    for index in range(int(sp.S3_SPLIT_COUNTS["meta_test"]))
                ],
                "K": list(an.FORMAL_K_SWEEP),
            },
        }

    def test_fallback_constants(self):
        fallback = an._rs3_02_fallback()
        self.assertEqual(fallback["opt_seeds"], 5)
        self.assertEqual(fallback["main_runs"], 3000)
        self.assertEqual(fallback["main_evals"], 288000)
        self.assertEqual(fallback["total_runs"], 3780)
        self.assertEqual(fallback["total_evals"], 362880)
        self.assertTrue(an.RS3_02_DISCLOSED_CODE.startswith("S3_ANALYSIS_"))

    def test_primary_budgets_contract_pass(self):
        section = json.loads(json.dumps(sp.S3_PREREG_BUDGETS))
        checks = []
        result = an._validate_budgets_section(section, checks)
        self.assertEqual(result["opt_seeds"], list(sp.S3_PREREG_BUDGETS["opt_seeds"]))
        statuses = {item["check"]: item["status"] for item in checks}
        self.assertEqual(statuses["budgets_contract"], "PASS")

    def test_nominal_ten_seed_budgets_section_rejected(self):
        # Lead m10061 / 计划 v1.3b：3,780/362,880 为唯一正式网格（opt_seeds=5）；6,900/662,400 仅名义上限，
        # 不得作为预注册正式预算段（10 opt seeds 一律拒绝）。
        section = json.loads(json.dumps(sp.S3_PREREG_BUDGETS))
        section["opt_seeds"] = list(range(10))
        section["main_runs"] = 6000
        section["main_evals"] = 576000
        expect_error(self, an.S3_ANALYSIS_PREREG_BINDING_MISMATCH, an._validate_budgets_section, section, [])

    def test_formal_primary_scale_accepted(self):
        checks = []
        primary = len(sp.S3_PREREG_BUDGETS["opt_seeds"])
        grid = an._derive_run_grid(self._formal_config(primary), self.prereg, checks=checks)
        self.assertEqual(grid["run_count"], int(sp.S3_PREREG_BUDGETS["main_runs"]))
        self.assertEqual(grid["eval_records_expected"], int(sp.S3_PREREG_BUDGETS["main_evals"]))
        self.assertTrue(grid["rs3_02_fallback_applied"] is False)
        statuses = {item["check"]: item["status"] for item in checks}
        self.assertEqual(statuses["run_grid_rs3_02"], "PASS")

    def test_formal_fallback_scale_disclosed(self):
        # 合成「名义 10 opt seeds 主网格」的 prereg，验证 5 seeds 降网格仍被接受并显式披露。
        nominal = dataclasses.replace(
            self.prereg,
            budgets={
                **dict(self.prereg.budgets),
                "opt_seeds": list(range(10)),
                "main_runs": 6000,
                "main_evals": 576000,
            },
        )
        checks = []
        grid = an._derive_run_grid(self._formal_config(5), nominal, checks=checks)
        self.assertEqual(grid["run_count"], 3000)
        self.assertEqual(grid["eval_records_expected"], 288000)
        # R-S3-07：FORMAL 加载冻结模型、不重训 → 训练期望恒为 0。
        self.assertEqual(grid["train_expected"], 0)
        self.assertTrue(grid["rs3_02_fallback_applied"])
        item = [entry for entry in checks if entry["check"] == "run_grid_rs3_02"][0]
        self.assertEqual(item["status"], "DISCLOSED")
        self.assertEqual(item["code"], an.RS3_02_DISCLOSED_CODE)

    def test_formal_other_opt_count_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_BUDGET_MISMATCH,
            an._derive_run_grid,
            self._formal_config(7),
            self.prereg,
            checks=[],
        )

    def test_run_unknown_file_tolerated(self):
        execution_report = {"parallelism": 8, "total_cpu_seconds": 123.0, "physical_call_count": 0}

        def mutator(run_dir):
            target = run_dir / "execution_report.json"
            target.write_bytes((_canonical(execution_report) + "\n").encode("utf-8"))
            digest = sp.sha256_file(target)
            patch_json(
                run_dir / "data_manifest.json",
                lambda payload: payload["artifact_sha256"].update({"execution_report": digest}),
            )
            # runner 侧会在写 run_summary 前把 data_manifest 加入 artifact_sha256，因此这里同步声明 sha。
            manifest_sha = sp.sha256_file(run_dir / "data_manifest.json")
            patch_json(
                run_dir / "run_summary.json",
                lambda payload: payload.__setitem__("data_manifest_sha256", manifest_sha),
            )

        run_dir = copy_run(mutator, tag="unknown-file")
        s3_run = load_fixture_run(run_dir=run_dir)
        self.assertEqual(len(s3_run.per_run), 40)
        self.assertNotIn("FAIL", [item["status"] for item in s3_run.checks])
        self.assertTrue((run_dir / "execution_report.json").is_file())

    def test_aggregate_execution_scale_disclosed(self):
        cache = _e2e_runs()
        aggregate = json.loads((cache["plain_dir"] / "aggregate.json").read_text(encoding="utf-8"))
        scale = aggregate["execution_scale"]
        self.assertEqual(scale["run_count"], 40)
        self.assertEqual(scale["eval_records_expected"], 3840)
        self.assertEqual(scale["opt_seeds"], len(SMOKE_OPT_SEEDS))
        self.assertFalse(scale["rs3_02_fallback_applied"])
        self.assertIn("rs3_02_fallback_applied", aggregate["run_grid"])
        self.assertIn("R-S3-05", scale["note"])


# ---------------------------------------------------------------------------
# G 段：与 A1 真 runner 产物布局兼容（R-S3-04/R-S3-05 联调口径）
# ---------------------------------------------------------------------------
def _mutate_records(mutator, tag):
    """改写 run_records.jsonl：mutator(eval_payloads, all_payloads) 原地修改。"""

    def apply(run_dir):
        path = Path(run_dir) / "run_records.jsonl"
        payloads = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        evalu = [payload for payload in payloads if "task_id" in payload]
        mutator(evalu, payloads)
        path.write_text("\n".join(_canonical(payload) for payload in payloads) + "\n", encoding="utf-8")

    return apply


class RunnerLayoutCompatTests(unittest.TestCase):
    """A1 真 runner 的 run_config/记录布局必须被接受；对应负控仍须 fail-closed。"""

    @classmethod
    def setUpClass(cls):
        cls.prereg = load_fixture_prereg()

    def _load(self, mutator, tag):
        checks = []
        run_dir = copy_run(mutator, tag=tag)
        return load_fixture_run(self.prereg, run_dir, checks), checks

    @staticmethod
    def _statuses(checks):
        return {str(item.get("check")): str(item.get("status")) for item in checks}

    @staticmethod
    def _no_fail(testcase, checks):
        testcase.assertNotIn("FAIL", [str(item.get("status")) for item in checks])

    def test_runner_grid_without_task_list_accepted(self):
        def mutate(data):
            data["evaluation_grid"] = {
                "eval_tasks": SMOKE_EVAL_TASKS,
                "eval_split": "meta_validation",
                "k_sweep": list(SMOKE_KS),
                "budgets": list(SMOKE_BUDGETS),
            }

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "runner-nolist")
        self._no_fail(self, checks)
        self.assertEqual(int(s3_run.grid["n_tasks"]), SMOKE_EVAL_TASKS)
        self.assertEqual(tuple(s3_run.grid["task_ids"]), ())
        self.assertEqual(str(s3_run.grid["eval_split"]), "meta_validation")
        self.assertEqual(len(s3_run.per_run), 40)
        self.assertEqual(self._statuses(checks).get("run_records_task_coverage"), "PASS")

    def test_runner_eval_tasks_five_rejected(self):
        def mutate(data):
            data["evaluation_grid"].pop("tasks", None)
            data["evaluation_grid"]["eval_tasks"] = SMOKE_EVAL_TASKS + 1
            data["smoke_overrides"]["eval_tasks"] = SMOKE_EVAL_TASKS + 1

        _run_error(self, an.S3_ANALYSIS_BUDGET_MISMATCH, _mutate_json("run_config.json", mutate), "runner-tasks5")

    def test_runner_eval_split_mismatch_rejected(self):
        def mutate(data):
            data["evaluation_grid"]["eval_split"] = "meta_test"

        _run_error(self, an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, _mutate_json("run_config.json", mutate), "runner-split")

    def test_runner_k_sweep_without_zero_disclosed(self):
        def mutate(data):
            data["smoke_overrides"]["k_sweep"] = [5]
            data["evaluation_grid"]["k_sweep"] = [5]

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "runner-ksweep")
        self._no_fail(self, checks)
        item = [entry for entry in checks if entry.get("check") == "smoke_overrides_k_sweep"][0]
        self.assertEqual(item["status"], "DISCLOSED")
        self.assertEqual(item["code"], an.SMOKE_DISCLOSED_CODE)
        self.assertEqual(tuple(s3_run.grid["smoke_overrides"]["k_sweep"]), (5,))

    def test_runner_arms_list_of_dicts_accepted(self):
        def mutate(data):
            data["arms"] = [
                {
                    "id": arm,
                    "engine_type": "bo" if arm != "S3-DE" else "de",
                    "surrogate": "none",
                    "score": "joint",
                    "head_only": arm == "S3-BO-ANIL-CON",
                    "first_order": arm != "S3-BO-FOMAML-OBJ",
                    "selection": "ei",
                    "joint_score": "f+10*(max(0,g1)^2+max(0,g2)^2)",
                    "rng": "numpy-default-rng",
                }
                for arm in sp.S3_ARMS
            ]

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "runner-arms")
        self._no_fail(self, checks)
        self.assertEqual(tuple(sorted(s3_run.grid["arms"])), tuple(sorted(sp.S3_ARMS)))

    def test_runner_gate_mode_fomaml_anil_accepted(self):
        def mutate(data):
            gate = data["fd_or_gradient_gate"]
            gate["mode"] = "fomaml+anil"
            gate["tolerance"] = 1e-6

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "runner-gatemode")
        self._no_fail(self, checks)
        statuses = self._statuses(checks)
        self.assertEqual(statuses.get("fd_gate_mode_disclosed"), "DISCLOSED")
        self.assertEqual(statuses.get("fd_gate_config"), "PASS")

    def test_runner_gate_formal_coordinate_count_rejected(self):
        def mutate(data):
            gate = data["fd_or_gradient_gate"]
            gate["coordinates"] = int(sp.S3_FD_MAX_COORDINATES)
            gate["n_checked"] = int(sp.S3_FD_MAX_COORDINATES)
            gate["coordinates_requested"] = int(sp.S3_FD_MAX_COORDINATES)

        _run_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, _mutate_json("run_config.json", mutate), "runner-gatecount")

    def test_runner_gate_mapping_coordinates_accepted(self):
        def mutate(data):
            gate = data["fd_or_gradient_gate"]
            gate["coordinates"] = {"fomaml_meta_0": int(gate["n_checked"])}
            gate["n_checked"] = int(data["fd_or_gradient_gate"]["n_checked"])

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "runner-gate-map")
        self._no_fail(self, checks)
        self.assertEqual(self._statuses(checks).get("fd_gate_config"), "PASS")

    def test_runner_gate_models_dict_coordinates_accepted(self):
        def mutate(data):
            gate = data["fd_or_gradient_gate"]
            expected = int(gate["coordinates"])
            gate.pop("coordinates", None)
            gate.pop("n_checked", None)
            gate["models"] = {"fomaml_meta_0": {"n_checked": expected}}

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "runner-gate-models")
        self._no_fail(self, checks)
        self.assertEqual(self._statuses(checks).get("fd_gate_config"), "PASS")

    def test_runner_gate_missing_mode_disclosed(self):
        def mutate(data):
            data["fd_or_gradient_gate"].pop("mode", None)

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "runner-gate-nomode")
        self._no_fail(self, checks)
        statuses = self._statuses(checks)
        self.assertEqual(statuses.get("fd_gate_mode_disclosed"), "DISCLOSED")
        self.assertEqual(statuses.get("fd_gate_config"), "PASS")

    def test_runner_gate_artifact_coordinate_count_rejected(self):
        def mutate(run_dir):
            gate_path = Path(run_dir) / "fd_or_gradient_gate.json"
            patched = json.loads(gate_path.read_text(encoding="utf-8"))
            patched["coordinates"] = patched["coordinates"][:7]
            gate_path.write_bytes((_canonical(patched) + "\n").encode("utf-8"))
            gate_sha = sp.sha256_file(gate_path)
            patch_json(
                Path(run_dir) / "run_summary.json",
                lambda payload: payload.__setitem__("fd_or_gradient_gate_sha256", gate_sha),
            )

        _run_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, mutate, "runner-gateartifact")

    def test_runner_models_sha_change_disclosed(self):
        def mutate(data):
            for kind in sp.S3_MODEL_KINDS:
                data["models"][kind]["sha256"] = "d" * 64

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "runner-modelsha")
        self._no_fail(self, checks)
        item = [entry for entry in checks if entry.get("check") == "models_retrained_in_run"][0]
        self.assertEqual(item["status"], "DISCLOSED")
        self.assertEqual(len(s3_run.train_records), 4)

    def test_runner_eval_record_run_id_non_prefix_rejected(self):
        def mutate(evalu, payloads):
            evalu[0]["run_id"] = "other-run-000"

        _run_error(self, an.S3_ANALYSIS_RECORD_INVALID, _mutate_records(mutate, "runner-runid"), "runner-runid")

    def test_runner_bucket_run_id_inconsistent_rejected(self):
        def mutate(evalu, payloads):
            first = evalu[0]
            key = (first["task_id"], first["arm_id"], first["budget"], first["opt_seed"], first["meta_seed"])
            for record in evalu[1:]:
                same = (
                    record["task_id"] == key[0]
                    and record["arm_id"] == key[1]
                    and int(record["budget"]) == int(key[2])
                    and int(record["opt_seed"]) == int(key[3])
                    and int(record["meta_seed"]) == int(key[4])
                )
                if same:
                    record["run_id"] = FIXTURE_RUN_ID + "--other-bucket"
                    return
            raise AssertionError("未找到同 bucket 的第二条记录")

        _run_error(self, an.S3_ANALYSIS_RECORD_INVALID, _mutate_records(mutate, "runner-bucketid"), "runner-bucketid")

    def test_runner_task_id_outside_declared_list_rejected(self):
        # 显式任务列表时，未知 task_id 立即 fail-closed。
        def mutate(evalu, payloads):
            evalu[0]["task_id"] = "meta_validation-task-999"

        _run_error(self, an.S3_ANALYSIS_RECORD_INVALID, _mutate_records(mutate, "runner-taskid"), "runner-taskid")

    def test_runner_task_coverage_extra_task_rejected(self):
        # 无任务列表（A1 runner 布局）时，整桶改名保留 1..B 连续，使实际任务集合变成 5 个。
        def rename_bucket(evalu):
            first = evalu[0]
            key = (first["task_id"], first["arm_id"], first["budget"], first["opt_seed"], first["meta_seed"])
            for record in evalu:
                if (
                    record["task_id"] == key[0]
                    and record["arm_id"] == key[1]
                    and int(record["budget"]) == int(key[2])
                    and int(record["opt_seed"]) == int(key[3])
                    and int(record["meta_seed"]) == int(key[4])
                ):
                    record["task_id"] = "meta_validation-task-999"

        def mutate(run_dir):
            patch_json(
                Path(run_dir) / "run_config.json",
                lambda data: data.__setitem__(
                    "evaluation_grid",
                    {"eval_tasks": SMOKE_EVAL_TASKS, "eval_split": "meta_validation", "k_sweep": list(SMOKE_KS)},
                ),
            )
            path = Path(run_dir) / "run_records.jsonl"
            payloads = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            rename_bucket([payload for payload in payloads if "task_id" in payload])
            path.write_text("\n".join(_canonical(payload) for payload in payloads) + "\n", encoding="utf-8")

        _run_error(self, an.S3_ANALYSIS_BUDGET_MISMATCH, mutate, "runner-taskcov")

    def test_runner_scope_notes_list_accepted(self):
        notes = ["evidence_scope=" + sp.S3_EVIDENCE_SCOPE, "physical_call_count=0", "development_set=meta_validation"]

        def mutate_config(data):
            data["scope_notes"] = list(notes)

        def mutate(run_dir):
            patch_json(Path(run_dir) / "run_config.json", mutate_config)
            patch_json(Path(run_dir) / "run_summary.json", lambda payload: payload.__setitem__("scope_notes", list(notes)))

        s3_run, checks = self._load(mutate, "runner-notes")
        self._no_fail(self, checks)
        self.assertEqual(list(s3_run.config["scope_notes"]), list(notes))

if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# H 段：FORMAL 严格分流（Lead m09348：SMOKE 专属放宽不得泄漏到 FORMAL）
# ---------------------------------------------------------------------------


class FormalStrictnessTests(unittest.TestCase):
    """FORMAL 必须严格 fail-closed：K 集合固定、models sha 绑定预注册模型包。

    SMOKE 允许 runner 在 run 内重训模型、允许子集 K；FORMAL 不允许。
    """

    @classmethod
    def setUpClass(cls):
        cls.prereg = load_fixture_prereg()

    def _formal_config(self, **overrides):
        config = RS302FallbackTests._formal_config.__get__(self)(len(sp.S3_PREREG_BUDGETS["opt_seeds"]))
        config["evaluation_grid"] = dict(config["evaluation_grid"])
        config["evaluation_grid"].update(overrides)
        return config

    def _statuses(self, checks):
        return {item["check"]: item["status"] for item in checks}

    def test_formal_task_list_optional_with_manifest_binding(self):
        # A1 runner FORMAL 布局：evaluation_grid 只声明 eval_tasks + eval_split（无任务列表）；
        # 任务集合权威来源=data_manifest.split_task_ids，由 _cross_check_record_task_set 交叉校验。
        config = self._formal_config()
        config["evaluation_grid"].pop("tasks", None)
        config["evaluation_grid"]["eval_tasks"] = int(sp.S3_SPLIT_COUNTS["meta_test"])
        config["evaluation_grid"]["eval_split"] = "meta_test"
        checks = []
        grid = an._derive_run_grid(config, self.prereg, checks=checks)
        self.assertEqual(grid["n_tasks"], int(sp.S3_SPLIT_COUNTS["meta_test"]))
        self.assertEqual(grid["task_ids"], ())
        self.assertEqual(grid["run_count"], int(sp.S3_PREREG_BUDGETS["main_runs"]))

    def test_formal_no_task_list_requires_eval_split(self):
        config = self._formal_config()
        config["evaluation_grid"].pop("tasks", None)
        config["evaluation_grid"]["eval_tasks"] = int(sp.S3_SPLIT_COUNTS["meta_test"])
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
            an._derive_run_grid,
            config,
            self.prereg,
            checks=[],
        )

    def test_formal_no_task_list_requires_eval_tasks(self):
        config = self._formal_config()
        config["evaluation_grid"] = {"K": [5], "eval_split": "meta_test"}
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
            an._derive_run_grid,
            config,
            self.prereg,
            checks=[],
        )

    def test_record_task_set_matches_data_manifest(self):
        task_ids = ["meta_test-task-" + str(index).zfill(3) for index in range(int(sp.S3_SPLIT_COUNTS["meta_test"]))]
        manifest = {"split_task_ids": {"meta_test": task_ids}}
        records = [{"task_id": task_id} for task_id in reversed(task_ids)]
        checks = []
        an._cross_check_record_task_set(manifest, records, {"run_mode": "FORMAL", "eval_split": "meta_test", "task_ids": ()}, checks=checks)
        statuses = {item["check"]: item["status"] for item in checks}
        self.assertEqual(statuses["run_records_task_manifest_binding"], "PASS")

    def test_record_task_set_mismatch_rejected(self):
        task_ids = ["meta_test-task-" + str(index).zfill(3) for index in range(int(sp.S3_SPLIT_COUNTS["meta_test"]))]
        manifest = {"split_task_ids": {"meta_test": task_ids}}
        records = [{"task_id": task_id} for task_id in task_ids[:-1]]
        expect_error(
            self,
            an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION,
            an._cross_check_record_task_set,
            manifest,
            records,
            {"run_mode": "FORMAL", "eval_split": "meta_test", "task_ids": ()},
            checks=[],
        )

    def test_record_task_set_missing_manifest_split_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION,
            an._cross_check_record_task_set,
            {"split_task_ids": {"meta_validation": []}},
            [{"task_id": "meta_test-task-000"}],
            {"run_mode": "FORMAL", "eval_split": "meta_test", "task_ids": ()},
            checks=[],
        )

    def test_record_task_set_smoke_skipped(self):
        checks = []
        an._cross_check_record_task_set({}, [{"task_id": "x"}], {"run_mode": "SMOKE", "eval_split": "meta_validation"}, checks=checks)
        self.assertEqual(checks, [])

    def test_formal_k_sweep_check_pass(self):
        checks = []
        grid = an._derive_run_grid(self._formal_config(), self.prereg, checks=checks)
        self.assertEqual(grid["run_count"], int(sp.S3_PREREG_BUDGETS["main_runs"]))
        self.assertEqual(self._statuses(checks)["run_grid_formal_k_sweep"], "PASS")

    def test_formal_k_sweep_missing_rejected(self):
        config = self._formal_config()
        config["evaluation_grid"].pop("K", None)
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
            an._derive_run_grid,
            config,
            self.prereg,
            checks=[],
        )

    def test_formal_k_sweep_plan_value_only(self):
        # 计划 §3.3：K=5 固定，FORMAL 只接受 [5] 单元素集合
        self.assertEqual(tuple(an.FORMAL_K_SWEEP), (5,))

    def test_formal_k_sweep_m1_diagnostic_set_rejected(self):
        # [0,1,3,5] 是 M1 K-sweep 诊断件（计划 §4.2），不得写进正式 run_config
        config = self._formal_config(K=[0, 1, 3, 5])
        expect_error(
            self,
            an.S3_ANALYSIS_BUDGET_MISMATCH,
            an._derive_run_grid,
            config,
            self.prereg,
            checks=[],
        )

    def test_formal_k_sweep_duplicate_rejected(self):
        config = self._formal_config(K=[5, 5])
        expect_error(
            self,
            an.S3_ANALYSIS_BUDGET_MISMATCH,
            an._derive_run_grid,
            config,
            self.prereg,
            checks=[],
        )

    def _models_section(self, *, fomaml_sha=None, anil_sha=None):
        section = {}
        for name in ("fomaml", "anil"):
            sha = sp_models = self.prereg.models[name]["sha256"]
            if name == "fomaml" and fomaml_sha is not None:
                sha = fomaml_sha
            if name == "anil" and anil_sha is not None:
                sha = anil_sha
            section[name] = {"sha256": sha}
        return section

    def test_formal_models_sha_equal_accepted(self):
        checks = []
        an._validate_model_sha_binding(
            self._models_section(), self.prereg, run_mode="FORMAL", checks=checks
        )
        self.assertEqual(self._statuses(checks)["models_pre_registered_sha"], "PASS")
        self.assertNotIn("DISCLOSED", [item["status"] for item in checks])

    def test_formal_models_sha_mismatch_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_BINDING_MISMATCH,
            an._validate_model_sha_binding,
            self._models_section(fomaml_sha="0" * 64),
            self.prereg,
            run_mode="FORMAL",
            checks=[],
        )

    def test_smoke_models_sha_mismatch_disclosed(self):
        checks = []
        an._validate_model_sha_binding(
            self._models_section(anil_sha="1" * 64), self.prereg, run_mode="SMOKE", checks=checks
        )
        item = [entry for entry in checks if entry["check"] == "models_retrained_in_run"][0]
        self.assertEqual(item["status"], "DISCLOSED")

    def test_smoke_models_sha_equal_pass(self):
        checks = []
        an._validate_model_sha_binding(
            self._models_section(), self.prereg, run_mode="SMOKE", checks=checks
        )
        self.assertEqual(self._statuses(checks)["models_pre_registered_sha"], "PASS")


# ---------------------------------------------------------------------------
# R-S3-06 §2：FD/梯度门结构（每模型 32 坐标 × 2 模型 + negatives 三键）
# ---------------------------------------------------------------------------
def _gate_coords(count, *, rel=1e-10):
    return [
        {"index": index, "analytic": 1.0 + index, "numeric": 1.0 + index + rel, "relative_error": rel}
        for index in range(count)
    ]


def _gate_models(count=32, *, rel=1e-10, status="PASS", names=("fomaml", "anil")):
    return {
        name + "_meta_0": {
            "arm_type": name,
            "meta_seed": 0,
            "n_checked": count,
            "status": status,
            "max_relative_error": rel,
            "coordinates": _gate_coords(count, rel=rel),
        }
        for name in names
    }


def _new_shape_gate(models=None, *, rel=1e-10, negatives=None, n_checked=None, schema="p4ra-s3-fd-gate-v1"):
    models = _gate_models() if models is None else models
    if negatives is None:
        negatives = {"tamper": "PASS", "anil_body_frozen": "PASS", "k0_equivalence": "PASS"}
    gate = {
        "schema_version": schema,
        "created_utc": "2026-11-07T00:00:00Z",
        "tolerance": 1e-6,
        "epsilon_rule": "1e-6*max(1,|theta|)",
        "mode": "fomaml+anil",
        "status": "PASS",
        "max_relative_error": rel,
    }
    if models is not None:
        gate["models"] = models
    if n_checked is None:
        n_checked = 64 if models and len(models) == 2 else 32
    gate["n_checked"] = n_checked
    gate["negatives"] = negatives
    return gate


class GateStructureTests(unittest.TestCase):
    FORMAL_CONFIG = {"run_mode": "FORMAL"}
    SMOKE_CONFIG = {"run_mode": "SMOKE", "smoke_overrides": {"fd_coordinates": 8}}

    def _validate(self, gate, config):
        checks = []
        result = an._validate_gate_artifact(gate, config, None, checks=checks)
        return result, {item["check"]: item["status"] for item in checks}

    def test_formal_new_shape_pass(self):
        result, statuses = self._validate(_new_shape_gate(), self.FORMAL_CONFIG)
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["fd_gate_artifact"], "PASS")
        self.assertEqual(statuses["fd_gate_artifact_models"], "PASS")
        self.assertEqual(statuses["fd_gate_negatives"], "PASS")

    def test_formal_new_shape_minimal_metadata_pass(self):
        gate = _new_shape_gate()
        del gate["mode"]
        del gate["created_utc"]
        del gate["tolerance"]
        del gate["epsilon_rule"]
        result, statuses = self._validate(gate, self.FORMAL_CONFIG)
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["fd_gate_artifact"], "PASS")
        self.assertEqual(statuses["fd_gate_mode_disclosed"], "DISCLOSED")

    def test_formal_epsilon_rule_invalid_rejected(self):
        gate = _new_shape_gate()
        gate["epsilon_rule"] = "1e-3*max(1,|theta|)"
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            gate,
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_model_key_alias_disclosed(self):
        models = _gate_models()
        alias = {name: models[name + "_meta_0"] for name in ("fomaml", "anil")}
        result, statuses = self._validate(_new_shape_gate(models=alias), self.FORMAL_CONFIG)
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["fd_gate_artifact"], "PASS")
        self.assertEqual(statuses["fd_gate_model_key_alias"], "DISCLOSED")

    def test_formal_missing_model_fails(self):
        models = _gate_models(names=("fomaml",))
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            _new_shape_gate(models=models, n_checked=32),
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_model_n_checked_mismatch_fails(self):
        models = _gate_models()
        models["anil_meta_0"]["n_checked"] = 31
        models["anil_meta_0"]["coordinates"] = _gate_coords(31)
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            _new_shape_gate(models=models),
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_coordinate_tolerance_exceeded_fails(self):
        models = _gate_models()
        models["fomaml_meta_0"]["coordinates"][7]["relative_error"] = 2e-6
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            _new_shape_gate(models=models),
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_model_status_fail_rejected(self):
        models = _gate_models()
        models["anil_meta_0"]["status"] = "FAIL"
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            _new_shape_gate(models=models),
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_negatives_missing_fails(self):
        gate = _new_shape_gate()
        gate["negatives"] = {"tamper": "PASS", "anil_body_frozen": "PASS"}
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            gate,
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_negatives_not_pass_fails(self):
        gate = _new_shape_gate(negatives={"tamper": "PASS", "anil_body_frozen": "FAIL", "k0_equivalence": "PASS"})
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            gate,
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_declared_max_mismatch_fails(self):
        gate = _new_shape_gate()
        gate["max_relative_error"] = 5e-10
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            gate,
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_interim_gates_shape_rejected(self):
        gate = _new_shape_gate()
        del gate["models"]
        gate["gates"] = {"fomaml": {"status": "PASS", "n_checked": 32}, "anil": {"status": "PASS", "n_checked": 32}}
        gate["coordinates"] = _gate_coords(32)
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            gate,
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_formal_legacy_flat_shape_rejected(self):
        gate = {
            "schema_version": sp.S3_GATE_SCHEMA_VERSION,
            "created_utc": "2026-11-07T00:00:00Z",
            "mode": "fomaml+anil",
            "status": "PASS",
            "tolerance": 1e-6,
            "max_relative_error": 1e-10,
            "coordinates": _gate_coords(32),
            "n_checked": 32,
        }
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            gate,
            self.FORMAL_CONFIG,
            None,
            checks=[],
        )

    def test_smoke_new_shape_one_model_pass(self):
        models = _gate_models(count=8, names=("fomaml",))
        gate = _new_shape_gate(models=models, n_checked=8)
        result, statuses = self._validate(gate, self.SMOKE_CONFIG)
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["fd_gate_artifact"], "PASS")

    def test_smoke_new_shape_three_models_rejected(self):
        models = _gate_models(count=8, names=("fomaml", "anil"))
        models["third_meta_0"] = models["fomaml_meta_0"]
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._validate_gate_artifact,
            _new_shape_gate(models=models, n_checked=8),
            self.SMOKE_CONFIG,
            None,
            checks=[],
        )

    def test_smoke_new_shape_negatives_disclosed(self):
        gate = _new_shape_gate(models=_gate_models(count=8), n_checked=8)
        gate["negatives"] = None
        result, statuses = self._validate(gate, self.SMOKE_CONFIG)
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["fd_gate_negatives"], "DISCLOSED")

    def test_smoke_legacy_flat_shape_accepted(self):
        gate = {
            "schema_version": sp.S3_GATE_SCHEMA_VERSION,
            "created_utc": "2026-11-07T00:00:00Z",
            "mode": "fomaml+anil",
            "status": "PASS",
            "tolerance": 1e-6,
            "max_relative_error": 1e-10,
            "coordinates": _gate_coords(8),
            "n_checked": 8,
        }
        result, statuses = self._validate(gate, self.SMOKE_CONFIG)
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["fd_gate_artifact"], "PASS")


# ---------------------------------------------------------------------------
# R-S3-07：FORMAL run_config FD 门声明形状 + 冻结 model_manifest 复制件
# ---------------------------------------------------------------------------
def _formal_gate_contract(*, per_model=32, total=64, mode="FORMAL", rel=1e-10, sha="a" * 64, model_sha="b" * 64):
    return {
        "sha256": sha,
        "coordinates_per_model": per_model,
        "coordinates_total": total,
        "mode": mode,
        "override": False,
        "models": {
            name + "_meta_0": {
                "path": "research/concorde_metaopt/evidence/s3/models/" + name + "_meta_0.json",
                "sha256": model_sha,
                "n_checked": 32,
                "status": "PASS",
                "max_relative_error": rel,
            }
            for name in ("fomaml", "anil")
        },
    }


def _formal_gate_config(contract=None, *, run_mode="FORMAL"):
    return {"run_mode": run_mode, "fd_or_gradient_gate": contract if contract is not None else _formal_gate_contract()}


def _model_manifest_entry(arm_type, *, meta_seed=0):
    return {
        "arm_type": arm_type,
        "meta_seed": meta_seed,
        "config": {"input_dim": 12, "output_dim": 3, "hidden_sizes": [64, 64]},
        "path": "research/concorde_metaopt/evidence/s3/models/" + arm_type + "_meta_0.json",
        "sha256": "b" * 64,
        "train_wall_s": 12.5,
        "peak_memory_mb": 64.0,
        "episode_bank_sha256": "c" * 64,
        "final_train_loss": 0.123,
    }


def _model_manifest(*, run_id="p4ra-s3-m2-frozen-run", verification=None):
    manifest = {
        "schema_version": sp.S3_MODEL_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "models": [_model_manifest_entry("fomaml"), _model_manifest_entry("anil")],
    }
    if verification is not None:
        manifest["verification"] = verification
    return manifest


class FormalRunGateContractTests(unittest.TestCase):
    """R-S3-07：FORMAL run_config.fd_or_gradient_gate 固定声明形状（值校验，不放宽）。"""

    def _validate(self, contract, *, config=None):
        checks = []
        an._require_run_gate_fields(contract, None, checks=checks, config=config if config is not None else _formal_gate_config(contract))
        return {item["check"]: item["status"] for item in checks}

    def test_valid_contract_pass(self):
        statuses = self._validate(_formal_gate_contract())
        self.assertEqual(statuses["fd_gate_config"], "PASS")
        self.assertEqual(statuses["fd_gate_models"], "PASS")
        self.assertEqual(statuses["fd_gate_total_coordinates"], "PASS")

    def test_formal_override_true_rejected(self):
        contract = _formal_gate_contract()
        contract["override"] = True
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_formal_override_missing_disclosed(self):
        contract = _formal_gate_contract()
        contract.pop("override")
        statuses = self._validate(contract)
        self.assertEqual(statuses.get("fd_gate_override_declaration"), "DISCLOSED")
        self.assertEqual(statuses.get("fd_gate_config"), "PASS")

    def test_missing_models_rejected(self):
        contract = _formal_gate_contract()
        del contract["models"]
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_missing_one_model_rejected(self):
        contract = _formal_gate_contract()
        contract["models"].pop("anil_meta_0")
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_per_model_not_32_rejected(self):
        contract = _formal_gate_contract(per_model=31)
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_total_not_64_rejected(self):
        contract = _formal_gate_contract(total=32)
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_mode_not_formal_rejected(self):
        contract = _formal_gate_contract(mode="SMOKE")
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_model_n_checked_not_32_rejected(self):
        contract = _formal_gate_contract()
        contract["models"]["fomaml_meta_0"]["n_checked"] = 31
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_model_status_fail_rejected(self):
        contract = _formal_gate_contract()
        contract["models"]["anil_meta_0"]["status"] = "FAIL"
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_model_max_rel_exceeded_rejected(self):
        contract = _formal_gate_contract()
        contract["models"]["anil_meta_0"]["max_relative_error"] = 2e-6
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_model_sha_not_hex_rejected(self):
        contract = _formal_gate_contract()
        contract["models"]["fomaml_meta_0"]["sha256"] = "not-a-sha"
        expect_error(self, an.S3_ANALYSIS_FD_GATE_INVALID, self._validate, contract)

    def test_unknown_field_disclosed(self):
        contract = _formal_gate_contract()
        contract["extra_note"] = "x"
        statuses = self._validate(contract)
        self.assertEqual(statuses["fd_gate_config_unknown_fields"], "DISCLOSED")

    def test_smoke_mode_still_uses_legacy_branch(self):
        config = {"run_mode": "SMOKE", "smoke_overrides": {"fd_coordinates": 8}}
        checks = []
        an._require_run_gate_fields(
            {"status": "PASS", "mode": "full", "max_relative_error": 1e-10, "coordinates": _gate_coords(8), "fd_gate_sha256": "d" * 64},
            None,
            checks=checks,
            config=config,
        )
        self.assertEqual({item["check"]: item["status"] for item in checks}["fd_gate_config"], "PASS")

    def test_cross_check_pass(self):
        checks = []
        contract = _formal_gate_contract()
        an._cross_check_run_gate_binding(_formal_gate_config(contract), _new_shape_gate(), gate_sha=contract["sha256"], checks=checks)
        self.assertEqual({item["check"]: item["status"] for item in checks}["fd_gate_declared_binding"], "PASS")

    def test_cross_check_sha_mismatch_rejected(self):
        contract = _formal_gate_contract()
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._cross_check_run_gate_binding,
            _formal_gate_config(contract),
            _new_shape_gate(),
            gate_sha="e" * 64,
            checks=[],
        )

    def test_cross_check_n_checked_mismatch_rejected(self):
        contract = _formal_gate_contract()
        models = _gate_models()
        models["anil_meta_0"]["n_checked"] = 31
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._cross_check_run_gate_binding,
            _formal_gate_config(contract),
            _new_shape_gate(models=models),
            gate_sha=contract["sha256"],
            checks=[],
        )

    def test_cross_check_max_rel_mismatch_rejected(self):
        contract = _formal_gate_contract()
        models = _gate_models()
        models["fomaml_meta_0"]["max_relative_error"] = 5e-10
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._cross_check_run_gate_binding,
            _formal_gate_config(contract),
            _new_shape_gate(models=models),
            gate_sha=contract["sha256"],
            checks=[],
        )


class ModelManifestVerificationTests(unittest.TestCase):
    """R-S3-07：FORMAL model_manifest 为冻结 manifest 复制件 + verification 块。"""

    def _validate(self, manifest, config=None):
        checks = []
        result = an._validate_model_manifest(manifest, config if config is not None else {"run_id": "p4ra-s3-run-formal-x"}, None, checks=checks)
        return result, {item["check"]: item["status"] for item in checks}

    def test_copied_manifest_run_id_mismatch_allowed(self):
        manifest = _model_manifest(
            verification={"loaded_from_prereg": True, "prereg_models_sha256": {"fomaml": "b" * 64, "anil": "b" * 64}, "verified_utc": "2026-11-07T00:00:00Z"}
        )
        result, statuses = self._validate(manifest)
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["model_manifest_copied_from_prereg"], "PASS")
        self.assertEqual(statuses["model_manifest_run_id"], "DISCLOSED")

    def test_run_id_mismatch_without_verification_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_BINDING_MISMATCH,
            self._validate,
            _model_manifest(run_id="some-other-run"),
        )

    def test_run_id_match_without_verification_pass(self):
        result, statuses = self._validate(_model_manifest(run_id="p4ra-s3-run-formal-x"))
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["model_manifest_schema"], "PASS")

    def test_loaded_false_disclosed(self):
        manifest = _model_manifest(run_id="p4ra-s3-run-formal-x", verification={"loaded_from_prereg": False})
        result, statuses = self._validate(manifest)
        self.assertIsInstance(result, dict)
        self.assertEqual(statuses["model_manifest_verification"], "DISCLOSED")

    def test_bad_prereg_models_sha_rejected(self):
        manifest = _model_manifest(verification={"loaded_from_prereg": True, "prereg_models_sha256": {"fomaml": "bad-sha"}})
        expect_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, self._validate, manifest)

    def test_missing_entry_field_still_rejected(self):
        manifest = _model_manifest(verification={"loaded_from_prereg": True})
        manifest["models"][0].pop("final_train_loss")
        expect_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, self._validate, manifest)


class R308AUnitTests(unittest.TestCase):
    """R-S3-08A / 计划 v1.3b：status_counts 披露、k_sweep 严格性、FD 门三方绑定的纯单元测试。

    不依赖 fixture（不构建证据树/run），用于在 A1 产物落盘前先把合同语义锁死。
    """

    @classmethod
    def setUpClass(cls):
        cls.fd_sha = "a" * 64
        cls.prereg_with_fd = SimpleNamespace(
            raw=(sp.canonical_json({"fd_gate_sha256": cls.fd_sha, "schema": "s3"}) + "\n").encode("utf-8")
        )
        cls.prereg_without_fd = SimpleNamespace(
            raw=(sp.canonical_json({"schema": "s3"}) + "\n").encode("utf-8")
        )

    @staticmethod
    def _statuses(checks):
        return {str(item.get("check")): str(item.get("status")) for item in checks}

    # ------------------------------------------------------------------
    # status_counts 披露（R-S3-08A）
    # ------------------------------------------------------------------
    def test_status_counts_constants(self):
        self.assertEqual(
            an.S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED,
            "S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED",
        )
        self.assertEqual(an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, "S3_ANALYSIS_RECORD_COUNTS_MISMATCH")

    def test_status_counts_disclosure_when_config_pass(self):
        disclosure = an._status_counts_disclosure(
            [{"check": "status_counts_config", "status": "PASS", "detail": "一致"}]
        )
        self.assertTrue(disclosure["config_provided"])
        self.assertFalse(disclosure["accepted_with_disclosure"])
        self.assertIsNone(disclosure["code"])

    def test_status_counts_disclosure_when_config_missing(self):
        disclosure = an._status_counts_disclosure(
            [
                {
                    "check": "status_counts_config",
                    "status": "DISCLOSED",
                    "detail": "run_config 未提供 status_counts",
                    "code": an.S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED,
                }
            ]
        )
        self.assertFalse(disclosure["config_provided"])
        self.assertTrue(disclosure["accepted_with_disclosure"])
        self.assertEqual(disclosure["code"], an.S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED)
        self.assertIn("status_counts", disclosure["detail"])

    def test_status_counts_disclosure_without_check_defaults_to_provided(self):
        disclosure = an._status_counts_disclosure([])
        self.assertTrue(disclosure["config_provided"])
        self.assertFalse(disclosure["accepted_with_disclosure"])

    # ------------------------------------------------------------------
    # FD 门三方绑定（计划 v1.3b）
    # ------------------------------------------------------------------
    def test_prereg_fd_gate_sha_reads_canonical_bytes(self):
        self.assertEqual(an._prereg_fd_gate_sha(self.prereg_with_fd), self.fd_sha)

    def test_prereg_fd_gate_sha_missing_returns_none(self):
        self.assertIsNone(an._prereg_fd_gate_sha(self.prereg_without_fd))

    def test_fd_gate_prereg_binding_formal_pass(self):
        checks = []
        result = an._validate_fd_gate_prereg_binding(
            {"sha256": self.fd_sha}, self.prereg_with_fd, run_mode="FORMAL", checks=checks
        )
        self.assertEqual(result, self.fd_sha)
        self.assertEqual(self._statuses(checks)["fd_gate_prereg_binding"], "PASS")

    def test_fd_gate_prereg_binding_formal_mismatch_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_BINDING_MISMATCH,
            an._validate_fd_gate_prereg_binding,
            {"sha256": "b" * 64},
            self.prereg_with_fd,
            run_mode="FORMAL",
            checks=[],
        )

    def test_fd_gate_prereg_binding_prereg_missing_disclosed(self):
        checks = []
        result = an._validate_fd_gate_prereg_binding(
            {"sha256": self.fd_sha}, self.prereg_without_fd, run_mode="FORMAL", checks=checks
        )
        self.assertIsNone(result)
        item = checks[0]
        self.assertEqual(item["status"], "DISCLOSED")
        self.assertEqual(item["code"], an.S3_ANALYSIS_FD_GATE_PREREG_BINDING_PENDING)

    def test_fd_gate_prereg_binding_smoke_disclosed(self):
        checks = []
        result = an._validate_fd_gate_prereg_binding(
            {"sha256": "b" * 64}, self.prereg_with_fd, run_mode="SMOKE", checks=checks
        )
        self.assertEqual(result, self.fd_sha)
        self.assertEqual(self._statuses(checks)["fd_gate_prereg_binding"], "DISCLOSED")

    def test_gate_file_prereg_binding_formal_pass(self):
        checks = []
        an._assert_gate_file_prereg_binding(
            self.fd_sha, self.prereg_with_fd, run_mode="FORMAL", checks=checks
        )
        self.assertEqual(self._statuses(checks)["fd_gate_file_prereg_binding"], "PASS")

    def test_gate_file_prereg_binding_formal_mismatch_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            an._assert_gate_file_prereg_binding,
            "b" * 64,
            self.prereg_with_fd,
            run_mode="FORMAL",
            checks=[],
        )

    def test_gate_file_prereg_binding_smoke_skipped(self):
        checks = []
        an._assert_gate_file_prereg_binding(
            "b" * 64, self.prereg_with_fd, run_mode="SMOKE", checks=checks
        )
        self.assertEqual(checks, [])

    # ------------------------------------------------------------------
    # run_config.k_sweep（计划 v1.3b）
    # ------------------------------------------------------------------
    def test_k_sweep_constant_required_by_schema(self):
        self.assertIn("k_sweep", set(sp.S3_RUN_CONFIG_REQUIRED_FIELDS))

    def test_k_sweep_formal_five_pass(self):
        checks = []
        result = an._validate_k_sweep({"k_sweep": [5]}, grid={"run_mode": "FORMAL"}, checks=checks)
        self.assertEqual(result, [5])
        self.assertEqual(self._statuses(checks)["k_sweep_config"], "PASS")

    def test_k_sweep_formal_m1_diagnostic_grid_rejected_as_budget_mismatch(self):
        error = expect_error(
            self,
            an.S3_ANALYSIS_BUDGET_MISMATCH,
            an._validate_k_sweep,
            {"k_sweep": [0, 1, 3, 5]},
            grid={"run_mode": "FORMAL"},
            checks=[],
        )
        self.assertIn("k_sweep", str(findattr(error, "message", "")))

    def test_k_sweep_non_integer_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
            an._validate_k_sweep,
            {"k_sweep": ["5"]},
            grid={"run_mode": "FORMAL"},
            checks=[],
        )

    def test_k_sweep_duplicate_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
            an._validate_k_sweep,
            {"k_sweep": [5, 5]},
            grid={"run_mode": "FORMAL"},
            checks=[],
        )

    def test_k_sweep_missing_formal_rejected(self):
        expect_error(
            self,
            an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
            an._validate_k_sweep,
            {},
            grid={"run_mode": "FORMAL"},
            checks=[],
        )

    def test_k_sweep_smoke_alternative_disclosed(self):
        checks = []
        result = an._validate_k_sweep({"k_sweep": [0, 1, 3, 5]}, grid={"run_mode": "SMOKE"}, checks=checks)
        self.assertEqual(result, [0, 1, 3, 5])
        self.assertEqual(self._statuses(checks)["k_sweep_config"], "DISCLOSED")

    def test_k_sweep_smoke_five_pass(self):
        checks = []
        an._validate_k_sweep({"k_sweep": [5]}, grid={"run_mode": "SMOKE"}, checks=checks)
        self.assertEqual(self._statuses(checks)["k_sweep_config"], "PASS")

class R308ARunLevelTests(unittest.TestCase):
    """R-S3-08/R-S3-08A/v1.3b：SMOKE 单流语义、status_counts 披露、k_sweep 严格性、FD 门绑定。

    fixture 为 SMOKE（40 runs / 3,840 eval / 4 train），不读真实 holdout。
    """

    @classmethod
    def setUpClass(cls):
        cls.ws = workspace()
        cls.prereg = load_fixture_prereg()
        cls.s3_run = load_fixture_run()
        cls.out_dir = cls.ws["base"] / "r308a-analysis"
        cls.result = an.analyze_s3_run(
            cls.ws["evidence"]["prereg_path"],
            cls.ws["run"]["run_dir"],
            cls.out_dir,
            repo_root=cls.ws["evidence"]["root"],
            generate_figures=False,
        )
        cls.aggregate = json.loads((cls.out_dir / "aggregate.json").read_text(encoding="utf-8"))

    def test_smoke_single_stream_not_applicable(self):
        statuses = {str(item.get("check")): str(item.get("status")) for item in self.s3_run.checks}
        self.assertEqual(statuses["record_streams"], "NOT_APPLICABLE")
        self.assertIn("main", self.s3_run.record_streams)
        self.assertIn("total", self.s3_run.record_streams)
        self.assertEqual(self.s3_run.record_streams["total"]["records"], 3840)
        self.assertEqual(self.s3_run.record_streams["total"]["runs"], 40)

    def test_status_counts_config_missing_disclosed(self):
        items = [item for item in self.s3_run.checks if item["check"] == "status_counts_config"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "DISCLOSED")
        self.assertEqual(items[0]["code"], an.S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED)

    def test_aggregate_status_counts_disclosure(self):
        disclosure = self.aggregate["status_counts_disclosure"]
        self.assertFalse(disclosure["config_provided"])
        self.assertTrue(disclosure["accepted_with_disclosure"])
        self.assertEqual(disclosure["code"], an.S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED)
        disclosed = {str(item.get("check")) for item in self.aggregate["disclosed_checks"]}
        self.assertIn("status_counts_config", disclosed)

    def test_aggregate_record_counts_by_stream(self):
        streams = self.aggregate["record_counts_by_stream"]
        self.assertEqual(streams["main"]["records"], 3840)
        self.assertEqual(streams["main"]["runs"], 40)
        self.assertEqual(streams["total"]["records"], 3840)
        self.assertEqual(streams["main"]["status_counts"], {"OK": 3840, "FAILED": 0})
        self.assertEqual(streams["total"]["status_counts"], {"OK": 3840, "FAILED": 0})

    def test_config_status_counts_equal_summary_passes(self):
        summary = json.loads((self.ws["run"]["run_dir"] / "run_summary.json").read_text(encoding="utf-8"))
        status_counts = summary["status_counts"]

        def mutator(run_dir):
            patch_json(run_dir / "run_config.json", lambda payload: payload.__setitem__("status_counts", status_counts))

        run_dir = copy_run(mutator, tag="r308a-status-equal")
        checks = []
        s3_run = load_fixture_run(run_dir=run_dir, checks=checks)
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses["status_counts_config"], "PASS")
        self.assertNotIn("FAIL", [str(item.get("status")) for item in s3_run.checks])

    def test_config_status_counts_mismatch_rejected(self):
        summary = json.loads((self.ws["run"]["run_dir"] / "run_summary.json").read_text(encoding="utf-8"))
        wrong = json.loads(json.dumps(summary["status_counts"]))
        wrong["eval"]["OK"] = int(wrong["eval"]["OK"]) - 1
        wrong["eval"]["FAILED"] = int(wrong["eval"]["FAILED"]) + 1

        def mutator(run_dir):
            patch_json(run_dir / "run_config.json", lambda payload: payload.__setitem__("status_counts", wrong))

        run_dir = copy_run(mutator, tag="r308a-status-mismatch")
        expect_error(
            self,
            an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH,
            load_fixture_run,
            run_dir=run_dir,
        )

    def test_run_config_k_sweep_missing_rejected(self):
        def mutator(run_dir):
            patch_json(run_dir / "run_config.json", lambda payload: payload.pop("k_sweep", None))

        run_dir = copy_run(mutator, tag="r308a-kmissing")
        expect_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, load_fixture_run, run_dir=run_dir)

    def test_smoke_k_sweep_m1_diagnostic_disclosed(self):
        def mutator(run_dir):
            patch_json(run_dir / "run_config.json", lambda payload: payload.__setitem__("k_sweep", [0, 1, 3, 5]))

        run_dir = copy_run(mutator, tag="r308a-kdiag")
        checks = []
        s3_run = load_fixture_run(run_dir=run_dir, checks=checks)
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses["k_sweep_config"], "DISCLOSED")
        self.assertNotIn("FAIL", [str(item.get("status")) for item in s3_run.checks])

    def test_prereg_fd_gate_sha_binds_frozen_gate_file(self):
        gate_path = Path(self.ws["evidence"]["root"]) / "research/concorde_metaopt/evidence/s3/gate/fd_or_gradient_gate.json"
        self.assertTrue(gate_path.is_file())
        gate_sha = sp.sha256_file(gate_path)
        self.assertEqual(an._prereg_fd_gate_sha(self.prereg), gate_sha)

class SmokeCompactGateTests(unittest.TestCase):
    """R-S3-08B：A1 v1.3b runner 的 SMOKE 模型级 FD 门声明形状（顶层无 status）必须被接受，负控 fail-closed。"""

    @classmethod
    def setUpClass(cls):
        cls.prereg = load_fixture_prereg()

    def _load(self, mutator, tag):
        checks = []
        run_dir = copy_run(mutator, tag=tag)
        return load_fixture_run(self.prereg, run_dir, checks), checks

    @staticmethod
    def _statuses(checks):
        return {str(item.get('check')): str(item.get('status')) for item in checks}

    @staticmethod
    def _entry(sha, n_checked, *, status="PASS", max_rel=1e-10):
        return {
            "path": "fd_or_gradient_gate.json",
            "sha256": sha,
            "n_checked": int(n_checked),
            "status": status,
            "max_relative_error": max_rel,
        }

    def _compact(self, data, *, models=None, mutate=None):
        gate = data["fd_or_gradient_gate"]
        sha = gate["fd_gate_sha256"]
        n = int(data["smoke_overrides"]["fd_coordinates"])
        if models is None:
            models = {
                "fomaml_meta_0": self._entry(sha, n),
                "anil_meta_0": self._entry(sha, n),
            }
        compact = {
            "sha256": sha,
            "coordinates_per_model": n,
            "coordinates_total": n * len(models),
            "mode": "SMOKE",
            "override": True,
            "models": models,
        }
        if mutate is not None:
            mutate(compact)
        data["fd_or_gradient_gate"] = compact

    def test_smoke_compact_gate_accepted(self):
        s3_run, checks = self._load(_mutate_json("run_config.json", self._compact), "smoke-gate-compact")
        statuses = self._statuses(checks)
        self.assertNotIn("FAIL", list(statuses.values()))
        self.assertEqual(statuses.get("fd_gate_models"), "PASS")
        self.assertEqual(statuses.get("fd_gate_config"), "PASS")
        self.assertEqual(statuses.get("fd_gate_override"), "DISCLOSED")
        self.assertEqual(s3_run.run_mode, "SMOKE")

    def test_smoke_compact_gate_single_model_accepted(self):
        def mutate(data):
            gate = data["fd_or_gradient_gate"]
            sha = gate["fd_gate_sha256"]
            n = int(data["smoke_overrides"]["fd_coordinates"])
            self._compact(data, models={"fomaml_meta_0": self._entry(sha, n)})

        s3_run, checks = self._load(_mutate_json("run_config.json", mutate), "smoke-gate-one")
        self.assertNotIn("FAIL", [entry.get("status") for entry in checks])
        self.assertEqual(self._statuses(checks).get("fd_gate_models"), "PASS")

    def test_smoke_compact_gate_unknown_field_disclosed(self):
        def mutate(compact):
            compact["note"] = "extra"

        s3_run, checks = self._load(
            _mutate_json("run_config.json", lambda data: self._compact(data, mutate=mutate)),
            "smoke-gate-unknown",
        )
        statuses = self._statuses(checks)
        self.assertEqual(statuses.get("fd_gate_config_unknown_fields"), "DISCLOSED")
        self.assertNotIn("FAIL", list(statuses.values()))

    def test_smoke_compact_gate_missing_sha_rejected(self):
        def mutate(compact):
            compact.pop("sha256", None)

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", lambda data: self._compact(data, mutate=mutate)),
            "smoke-gate-nosha",
        )

    def test_smoke_compact_gate_mode_formal_rejected(self):
        def mutate(compact):
            compact["mode"] = "FORMAL"

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", lambda data: self._compact(data, mutate=mutate)),
            "smoke-gate-mode",
        )

    def test_smoke_compact_gate_per_model_mismatch_rejected(self):
        def mutate(compact):
            compact["coordinates_per_model"] = 7

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", lambda data: self._compact(data, mutate=mutate)),
            "smoke-gate-permodel",
        )

    def test_smoke_compact_gate_total_mismatch_rejected(self):
        def mutate(compact):
            compact["coordinates_total"] = 3

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", lambda data: self._compact(data, mutate=mutate)),
            "smoke-gate-total",
        )

    def test_smoke_compact_gate_three_models_rejected(self):
        def mutate(data):
            sha = data["fd_or_gradient_gate"]["fd_gate_sha256"]
            n = int(data["smoke_overrides"]["fd_coordinates"])
            models = {name: self._entry(sha, n) for name in ("fomaml_meta_0", "anil_meta_0", "extra_meta_0")}
            self._compact(data, models=models)

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", mutate),
            "smoke-gate-threemodels",
        )

    def test_smoke_compact_gate_entry_missing_field_rejected(self):
        def mutate(data):
            sha = data["fd_or_gradient_gate"]["fd_gate_sha256"]
            n = int(data["smoke_overrides"]["fd_coordinates"])
            entry = self._entry(sha, n)
            entry.pop("path", None)
            self._compact(data, models={"fomaml_meta_0": entry})

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", mutate),
            "smoke-gate-entrymissing",
        )

    def test_smoke_compact_gate_entry_n_checked_mismatch_rejected(self):
        def mutate(data):
            sha = data["fd_or_gradient_gate"]["fd_gate_sha256"]
            n = int(data["smoke_overrides"]["fd_coordinates"])
            self._compact(data, models={"fomaml_meta_0": self._entry(sha, n + 1)})

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", mutate),
            "smoke-gate-nchecked",
        )

    def test_smoke_compact_gate_entry_status_fail_rejected(self):
        def mutate(data):
            sha = data["fd_or_gradient_gate"]["fd_gate_sha256"]
            n = int(data["smoke_overrides"]["fd_coordinates"])
            self._compact(data, models={"fomaml_meta_0": self._entry(sha, n, status="FAIL")})

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", mutate),
            "smoke-gate-entrystatus",
        )

    def test_smoke_compact_gate_entry_tolerance_rejected(self):
        def mutate(data):
            sha = data["fd_or_gradient_gate"]["fd_gate_sha256"]
            n = int(data["smoke_overrides"]["fd_coordinates"])
            self._compact(data, models={"fomaml_meta_0": self._entry(sha, n, max_rel=2e-6)})

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", mutate),
            "smoke-gate-entrytol",
        )

    def test_smoke_compact_gate_override_false_rejected(self):
        def mutate(compact):
            compact["override"] = False

        _run_error(
            self,
            an.S3_ANALYSIS_FD_GATE_INVALID,
            _mutate_json("run_config.json", lambda data: self._compact(data, mutate=mutate)),
            "smoke-gate-override",
        )
# ---------------------------------------------------------------------------
# R 段：R-S3-08 五流辅助函数级覆盖（A5 M1 预答：FORMAL 辅助流路径）
# ---------------------------------------------------------------------------
def _stream_record(run_id, *, task_id="T000", arm="S3-BO-RANDOM", budget=64, index=1,
                    split="meta_test", phase="EVAL", f_value=1.0, extra=None):
    """构造一条 19 字段评估记录（测试辅助）。"""
    record = {
        "schema_version": sp.S3_RECORD_SCHEMA_VERSION,
        "run_id": run_id,
        "task_id": task_id,
        "split": split,
        "arm_id": arm,
        "budget": int(budget),
        "opt_seed": 0,
        "meta_seed": 0,
        "evaluation_index": int(index),
        "design": [0.5] * 12,
        "f": f_value,
        "g1": -1.0,
        "g2": -1.0,
        "feasible": f_value is not None,
        "source": "bo",
        "phase": phase,
        "holdout_truth_read": phase == "EVAL",
        "wall_s": 0.001,
    }
    if extra:
        record.update(extra)
    record["record_digest"] = sp.record_digest(record)
    return record


def _write_stream(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(_canonical(record) for record in records)
    path.write_bytes((text + "\n").encode("utf-8") if text else b"")
    return path


class R308StreamHelperUnitTests(unittest.TestCase):
    """R-S3-08 五流辅助函数单元覆盖（_scan_aux_streams/_validate_record_stream_counts 等）。"""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="p4ra-s3-stream-"))
        self.addCleanup(shutil.rmtree, self.base, True)

    def test_safe_div_floor_and_normal(self):
        self.assertEqual(an._safe_div(1.0, 2.0), 0.5)
        self.assertEqual(an._safe_div(3.0, 0.0), 0.0)
        self.assertEqual(an._safe_div(3.0, 5e-13), 0.0)
        self.assertAlmostEqual(an._safe_div(1.0, 3.0), 1.0 / 3.0)

    def test_relative_difference_floor_and_sign(self):
        self.assertAlmostEqual(an._relative_difference(1.1, 1.0), 0.1)
        self.assertAlmostEqual(an._relative_difference(0.9, 1.0), -0.1)
        self.assertAlmostEqual(an._relative_difference(5e-7, 0.0), 0.5)

    def test_read_jsonl_file_roundtrip(self):
        path = self.base / "records.jsonl"
        path.write_bytes(b'{"a": 1}\n\n{"b": 2}\n')
        records = an._read_jsonl_file(path, code=an.S3_ANALYSIS_RECORD_INVALID, label="records")
        self.assertEqual(records, [{"a": 1}, {"b": 2}])
        crlf = self.base / "crlf.jsonl"
        crlf.write_bytes(b'{"a": 1}\r\n\r\n{"b": 2}\r\n')
        records = an._read_jsonl_file(crlf, code=an.S3_ANALYSIS_RECORD_INVALID, label="records")
        self.assertEqual(records, [{"a": 1}, {"b": 2}])

    def test_read_jsonl_file_missing_error(self):
        expect_error(self, an.S3_ANALYSIS_RECORD_INVALID, lambda: an._read_jsonl_file(
            self.base / "missing.jsonl", code=an.S3_ANALYSIS_RECORD_INVALID, label="records"))

    def test_read_jsonl_file_invalid_json_error(self):
        path = self.base / "bad.jsonl"
        path.write_bytes(b"not-json\n")
        expect_error(self, an.S3_ANALYSIS_RECORD_INVALID, lambda: an._read_jsonl_file(
            path, code=an.S3_ANALYSIS_RECORD_INVALID, label="records"))

    def test_write_jsonl_canonical_and_sha(self):
        path = self.base / "out" / "w.jsonl"
        sha = an._write_jsonl(path, [{"b": 1, "a": 2}])
        self.assertRegex(sha, "^[0-9a-f]{64}$")
        self.assertEqual(path.read_text(encoding="utf-8"), sp.canonical_json({"a": 2, "b": 1}) + "\n")
        empty = self.base / "empty.jsonl"
        self.assertEqual(an._write_jsonl(empty, []), sp.sha256_file(empty))
        self.assertEqual(empty.read_bytes(), b"")

    def test_require_str_list_ok_and_negative(self):
        self.assertEqual(an._require_str_list(["a", "b"], code=an.S3_ANALYSIS_RUN_SCHEMA_INVALID, label="x"),
                         ["a", "b"])
        expect_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, lambda: an._require_str_list(
            ["a", 1], code=an.S3_ANALYSIS_RUN_SCHEMA_INVALID, label="x"))

    def test_require_hex_sha_list_ok_and_negative(self):
        mapping = {"s": ["a" * 64, "b" * 64]}
        self.assertEqual(
            an._require_hex_sha_list(mapping, ("s",), code=an.S3_ANALYSIS_RUN_SCHEMA_INVALID, label="s", count=2),
            ["a" * 64, "b" * 64],
        )
        expect_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, lambda: an._require_hex_sha_list(
            mapping, ("s",), code=an.S3_ANALYSIS_RUN_SCHEMA_INVALID, label="s", count=3))
        expect_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, lambda: an._require_hex_sha_list(
            {"s": ["zz"]}, ("s",), code=an.S3_ANALYSIS_RUN_SCHEMA_INVALID, label="s", count=1))

    def test_mean_budget_divisible_and_errors(self):
        self.assertEqual(an._mean_budget({"budgets": [64, 128]}), 96)
        expect_error(self, an.S3_ANALYSIS_BUDGET_MISMATCH, an._mean_budget, {"budgets": []})
        expect_error(self, an.S3_ANALYSIS_BUDGET_MISMATCH, an._mean_budget, {"budgets": [64, 127]})

    def test_expected_stream_counts_formal(self):
        prereg = SimpleNamespace(budgets={
            "negative_control_runs": 300, "negative_control_evals": 28800,
            "ood_runs": 300, "ood_evals": 28800,
            "determinism_subset_runs": 60, "determinism_repeats": 3,
            "determinism_runs": 180, "determinism_evals": 17280,
        })
        grid = {
            "run_mode": "FORMAL", "run_count": 3000, "eval_records_expected": 288000,
            "budgets": [64, 128], "rs3_02_fallback_applied": True,
        }
        stream = an._expected_stream_counts(grid, prereg)
        self.assertEqual(stream["main"], {"runs": 3000, "records": 288000})
        self.assertEqual(stream["nc"], {"runs": 300, "records": 28800})
        self.assertEqual(stream["ood"], {"runs": 300, "records": 28800})
        self.assertEqual(stream["det"]["repeats"], 3)
        self.assertEqual(stream["det"]["runs"], 180)
        self.assertEqual(stream["det"]["records"], 17280)
        self.assertEqual(stream["det"]["runs_per_repeat"], 60)
        self.assertEqual(stream["det"]["records_per_repeat"], 5760)
        self.assertEqual(stream["total"], {"runs": 3780, "records": 362880})

    def test_expected_stream_counts_smoke_single_stream(self):
        grid = {"run_mode": "SMOKE", "run_count": 40, "eval_records_expected": 3840, "budgets": [64, 128]}
        stream = an._expected_stream_counts(grid, SimpleNamespace(budgets={}))
        self.assertEqual(sorted(stream), ["main", "total"])
        self.assertEqual(stream["total"], {"runs": 40, "records": 3840})

    def test_normalize_artifact_key_and_artifact_covers(self):
        self.assertEqual(an._normalize_artifact_key(".\\determinism\\r1\\run_records.jsonl"),
                         "determinism/r1/run_records.jsonl")
        self.assertEqual(an._normalize_artifact_key("./negative_control_records.jsonl"),
                         "negative_control_records.jsonl")
        manifest = {
            "negative_control_records.jsonl": "a" * 64,
            "determinism/r1/run_records.jsonl": "b" * 64,
        }
        self.assertTrue(an._artifact_covers(manifest, "negative_control_records.jsonl"))
        self.assertTrue(an._artifact_covers(manifest, "determinism/r1/run_records.jsonl"))
        self.assertFalse(an._artifact_covers(manifest, "ood_records.jsonl"))

    def test_record_core_digest_ignores_wall_and_digest(self):
        base = _stream_record("run-1", f_value=1.0)
        variant = dict(base, wall_s=999.0, peak_memory_mb=123.0, record_digest="c" * 64)
        self.assertEqual(an._record_core_digest(base), an._record_core_digest(variant))
        changed = dict(base, f=base["f"] + 1.0)
        self.assertNotEqual(an._record_core_digest(base), an._record_core_digest(changed))

    def test_bucket_status_ok(self):
        self.assertTrue(an.bucket_status_ok({"status": "OK"}))
        self.assertTrue(an.bucket_status_ok({}))
        self.assertFalse(an.bucket_status_ok({"status": "FAILED"}))
        self.assertFalse(an.bucket_status_ok({"status": None}))

    def test_resolve_stream_file_prefers_first_existing_and_missing(self):
        first = _write_stream(self.base / "nc" / "records.jsonl", [_stream_record("r1")])
        resolved = an._resolve_stream_file([self.base / "missing.jsonl", first], label="nc")
        self.assertEqual(resolved, first)
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, an._resolve_stream_file,
                     [self.base / "no1.jsonl", self.base / "no2.jsonl"], label="nc")

    def test_assert_stream_split_phase_ok_and_negative(self):
        stream = {"split_counts": {"meta_test_negative_control": 3}, "phase_counts": {"NEGATIVE_CONTROL": 3}}
        an._assert_stream_split_phase("nc", stream, "meta_test_negative_control", "NEGATIVE_CONTROL")
        expect_error(self, an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, an._assert_stream_split_phase,
                     "nc", {"split_counts": {"meta_test_ood": 1}}, "meta_test_negative_control", "NEGATIVE_CONTROL")
        expect_error(self, an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, an._assert_stream_split_phase,
                     "nc", {"phase_counts": {"OOD": 1}}, "meta_test_negative_control", "NEGATIVE_CONTROL")

    def test_scan_record_stream_counts_and_unknown_disclosure(self):
        path = _write_stream(self.base / "nc.jsonl", [
            _stream_record("r1", index=1, split="meta_test_negative_control", phase="NEGATIVE_CONTROL"),
            _stream_record("r1", index=2, split="meta_test_negative_control", phase="NEGATIVE_CONTROL"),
            _stream_record("r2", index=3, split="meta_test_negative_control", phase="NEGATIVE_CONTROL",
                           f_value=None, extra={"status": "FAILED", "note": "failed"}),
        ])
        checks = []
        stream = an._scan_record_stream(path, label="nc", checks=checks)
        self.assertEqual(stream["records"], 3)
        self.assertEqual(stream["runs"], 2)
        self.assertEqual(stream["status_counts"], {"OK": 2, "FAILED": 1})
        self.assertEqual(stream["split_counts"], {"meta_test_negative_control": 3})
        self.assertEqual(stream["phase_counts"], {"NEGATIVE_CONTROL": 3})
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("record_stream_unknown_fields_nc"), "DISCLOSED")

    def test_iter_stream_records_missing_field_error(self):
        record = _stream_record("r1")
        record.pop("design")
        path = _write_stream(self.base / "bad.jsonl", [record])
        expect_error(self, an.S3_ANALYSIS_RECORD_INVALID, list,
                     an._iter_stream_records(path, label="nc"))

    def test_scan_aux_streams_smoke_not_applicable(self):
        checks = []
        result = an._scan_aux_streams(self.base, {"run_mode": "SMOKE"}, checks=checks)
        self.assertFalse(result["available"])
        self.assertEqual(result["aux_records"], 0)
        self.assertEqual(result["det"]["records"], 0)
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("record_streams"), "NOT_APPLICABLE")

    def _formal_run_dir(self):
        run_dir = self.base / "run"
        _write_stream(run_dir / an.NC_RECORDS_FILE, [
            _stream_record("nc-1", split="meta_test_negative_control", phase="NEGATIVE_CONTROL"),
            _stream_record("nc-2", split="meta_test_negative_control", phase="NEGATIVE_CONTROL", index=2),
        ])
        _write_stream(run_dir / an.OOD_RECORDS_FILE, [
            _stream_record("ood-1", split="meta_test_ood", phase="OOD"),
            _stream_record("ood-2", split="meta_test_ood", phase="OOD", index=2),
        ])
        for name in an.DETERMINISM_REPEAT_NAMES:
            _write_stream(run_dir / an.DETERMINISM_DIR / name / an.RUN_RECORDS_FILE, [
                _stream_record("det-" + name, split="meta_test", phase="EVAL"),
            ])
        return run_dir

    def test_scan_aux_streams_formal_layout(self):
        run_dir = self._formal_run_dir()
        checks = []
        result = an._scan_aux_streams(run_dir, {"run_mode": "FORMAL", "eval_split": "meta_test"}, checks=checks)
        self.assertTrue(result["available"])
        self.assertEqual(result["nc"]["records"], 2)
        self.assertEqual(result["ood"]["records"], 2)
        self.assertEqual(result["det"]["records"], 3)
        self.assertEqual(result["det"]["runs"], 3)
        self.assertEqual(len(result["det"]["repeats"]), 3)
        self.assertEqual(result["aux_records"], 7)
        self.assertEqual(sorted(result["sources"]), ["det_r1", "det_r2", "det_r3", "nc", "ood"])
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("record_streams"), "PASS")

    def test_scan_aux_streams_formal_wrong_split_error(self):
        run_dir = self._formal_run_dir()
        _write_stream(run_dir / an.NC_RECORDS_FILE, [
            _stream_record("nc-1", split="meta_test_ood", phase="NEGATIVE_CONTROL"),
        ])
        expect_error(self, an.S3_ANALYSIS_DATA_BOUNDARY_VIOLATION, an._scan_aux_streams,
                     run_dir, {"run_mode": "FORMAL", "eval_split": "meta_test"}, checks=[])

    def test_scan_aux_streams_formal_missing_stream_error(self):
        run_dir = self._formal_run_dir()
        (run_dir / an.OOD_RECORDS_FILE).unlink()
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, an._scan_aux_streams,
                     run_dir, {"run_mode": "FORMAL", "eval_split": "meta_test"}, checks=[])

# ---------------------------------------------------------------------------
# R 段（续）：五流记录计数与 FD 门中间形状（A5 M1 预答）
# ---------------------------------------------------------------------------
class R308StreamCountsUnitTests(unittest.TestCase):
    """R-S3-08/R-S3-08A：五流分段计数 fail-closed 语义（FORMAL 3,780/362,880；SMOKE 单流）。"""

    @staticmethod
    def _prereg():
        return SimpleNamespace(budgets={
            "negative_control_runs": 300, "negative_control_evals": 28800,
            "ood_runs": 300, "ood_evals": 28800,
            "determinism_subset_runs": 60, "determinism_repeats": 3,
            "determinism_runs": 180, "determinism_evals": 17280,
        })

    def _formal_case(self):
        counts = {"train": 0, "eval": 362880, "total": 362880}
        repeats = [
            {"name": name, "runs": 60, "records": 5760, "status_counts": {"OK": 5760, "FAILED": 0}}
            for name in ("r1", "r2", "r3")
        ]
        aux = {
            "nc": {"runs": 300, "records": 28800, "status_counts": {"OK": 28800, "FAILED": 0}},
            "ood": {"runs": 300, "records": 28800, "status_counts": {"OK": 28800, "FAILED": 0}},
            "det": {"repeats": repeats, "runs": 180, "records": 17280, "status_counts": {"OK": 17280, "FAILED": 0}},
        }
        manifest_keys = [
            an.NC_RECORDS_FILE,
            an.OOD_RECORDS_FILE,
            an.DETERMINISM_DIR + "/r1/" + an.RUN_RECORDS_FILE,
            an.DETERMINISM_DIR + "/r2/" + an.RUN_RECORDS_FILE,
            an.DETERMINISM_DIR + "/r3/" + an.RUN_RECORDS_FILE,
        ]
        return {
            "config": {"record_counts": dict(counts)},
            "summary": {
                "record_counts": dict(counts),
                "status_counts": {"train": {"OK": 0, "FAILED": 0}, "eval": {"OK": 362880, "FAILED": 0}},
            },
            "grid": {
                "run_mode": "FORMAL", "run_count": 3000, "eval_records_expected": 288000,
                "budgets": [64, 128], "eval_split": "meta_test", "rs3_02_fallback_applied": True,
            },
            "prereg": self._prereg(),
            "main_counts": {"eval": 288000, "eval_ok": 288000, "eval_failed": 0},
            "aux_streams": aux,
            "data_manifest": {"artifact_sha256": {name: "a" * 64 for name in manifest_keys}},
        }

    def _smoke_case(self):
        counts = {"train": 4, "eval": 3840, "total": 3844}
        return {
            "config": {"record_counts": dict(counts)},
            "summary": {
                "record_counts": dict(counts),
                "status_counts": {"train": {"OK": 4, "FAILED": 0}, "eval": {"OK": 3840, "FAILED": 0}},
            },
            "grid": {"run_mode": "SMOKE", "run_count": 40, "eval_records_expected": 3840, "budgets": [64, 128]},
            "prereg": SimpleNamespace(budgets={}),
            "main_counts": {"eval": 3840, "eval_ok": 3840, "eval_failed": 0},
            "aux_streams": {
                "nc": {}, "ood": {},
                "det": {"repeats": [], "records": 0, "runs": 0, "status_counts": {"OK": 0, "FAILED": 0}},
            },
            "data_manifest": {"artifact_sha256": {}},
        }

    @staticmethod
    def _call(checks, case):
        return an._validate_record_stream_counts(checks=checks, **case)

    def test_formal_five_stream_pass(self):
        checks = []
        by_stream = self._call(checks, self._formal_case())
        self.assertEqual(by_stream["main"]["records"], 288000)
        self.assertEqual(by_stream["det"]["records"], 17280)
        self.assertEqual(by_stream["total"], {"runs": 3780, "records": 362880,
                                                 "status_counts": {"OK": 362880, "FAILED": 0}})
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("record_stream_counts"), "PASS")
        self.assertEqual(statuses.get("record_streams_manifest"), "PASS")
        self.assertEqual(statuses.get("status_counts_config"), "DISCLOSED")

    def test_formal_config_status_counts_equal_pass(self):
        case = self._formal_case()
        case["config"]["status_counts"] = {"train": {"OK": 0, "FAILED": 0}, "eval": {"OK": 362880, "FAILED": 0}}
        checks = []
        self._call(checks, case)
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("status_counts_config"), "PASS")

    def test_formal_declared_eval_mismatch_error(self):
        case = self._formal_case()
        case["config"]["record_counts"]["eval"] = 362879
        case["config"]["record_counts"]["total"] = 362879
        case["summary"]["record_counts"] = dict(case["config"]["record_counts"])
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, self._call, [], case)

    def test_formal_config_summary_counts_mismatch_error(self):
        case = self._formal_case()
        case["summary"]["record_counts"] = {"train": 0, "eval": 288000, "total": 288000}
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, self._call, [], case)

    def test_formal_determinism_repeat_count_error(self):
        case = self._formal_case()
        case["aux_streams"]["det"]["repeats"] = case["aux_streams"]["det"]["repeats"][:2]
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, self._call, [], case)

    def test_formal_manifest_missing_stream_error(self):
        case = self._formal_case()
        case["data_manifest"]["artifact_sha256"].pop(an.OOD_RECORDS_FILE)
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, self._call, [], case)

    def test_formal_status_counts_mismatch_error(self):
        case = self._formal_case()
        case["summary"]["status_counts"]["eval"] = {"OK": 300000, "FAILED": 62880}
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, self._call, [], case)

    def test_formal_train_nonzero_error(self):
        case = self._formal_case()
        case["config"]["record_counts"]["train"] = 4
        case["summary"]["record_counts"]["train"] = 4
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, self._call, [], case)

    def test_formal_status_counts_missing_error(self):
        case = self._formal_case()
        case["summary"].pop("status_counts")
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, self._call, [], case)

    def test_smoke_single_stream_pass(self):
        checks = []
        by_stream = self._call(checks, self._smoke_case())
        self.assertEqual(sorted(by_stream), ["main", "total"])
        self.assertEqual(by_stream["total"]["records"], 3840)
        self.assertEqual(by_stream["total"]["runs"], 40)
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("record_stream_counts"), "PASS")

    def test_smoke_declared_eval_mismatch_error(self):
        case = self._smoke_case()
        case["config"]["record_counts"]["eval"] = 3839
        case["config"]["record_counts"]["total"] = 3843
        case["summary"]["record_counts"] = dict(case["config"]["record_counts"])
        expect_error(self, an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH, self._call, [], case)


class R308GateInterimShapeTests(unittest.TestCase):
    """A1 06:40 SMOKE FD 门中间形状（gates{模型级}+顶层扁平 coordinates）解析与负控。"""

    CODE = an.S3_ANALYSIS_FD_GATE_INVALID

    @staticmethod
    def _coordinates(n=8, rel=1e-10):
        return [
            {"index": index, "analytic": 1.0 + index, "numeric": 1.0 + index + rel * (index + 1),
             "relative_error": rel * (index + 1)}
            for index in range(n)
        ]

    def _gate(self, *, models=None, coordinates=None):
        if models is None:
            models = {"fomaml": {"status": "PASS", "n_checked": 8, "tolerance": 1e-6}}
        if coordinates is None:
            coordinates = self._coordinates()
        return {"gates": models, "coordinates": coordinates}

    def _validate(self, gate, checks=None, *, expected_n=8):
        return an._validate_gate_interim_shape(
            gate, expected_n=expected_n, tolerance=1e-6, code=self.CODE, checks=[] if checks is None else checks
        )

    def test_interim_shape_pass(self):
        checks = []
        max_rel = self._validate(self._gate(), checks)
        self.assertAlmostEqual(max_rel, 8e-10)
        self.assertEqual(checks, [])

    def test_interim_three_models_error(self):
        models = {name: {"status": "PASS"} for name in ("a", "b", "c")}
        expect_error(self, self.CODE, self._validate, self._gate(models=models))

    def test_interim_entry_status_fail_error(self):
        expect_error(self, self.CODE, self._validate, self._gate(models={"fomaml": {"status": "FAIL"}}))

    def test_interim_n_checked_mismatch_error(self):
        expect_error(self, self.CODE, self._validate, self._gate(models={"fomaml": {"status": "PASS", "n_checked": 7}}))

    def test_interim_tolerance_over_frozen_error(self):
        expect_error(self, self.CODE, self._validate,
                     self._gate(models={"fomaml": {"status": "PASS", "tolerance": 2e-6}}))

    def test_interim_coordinate_rel_error_over_error(self):
        coordinates = self._coordinates(rel=2e-6)
        expect_error(self, self.CODE, self._validate, self._gate(coordinates=coordinates))

    def test_interim_coordinate_count_mismatch_error(self):
        expect_error(self, self.CODE, self._validate, self._gate(coordinates=self._coordinates(7)))


class S3RunDataPropertiesTests(unittest.TestCase):
    """S3RunData 便捷属性（n_tasks/arms/budgets/opt_seeds/meta_seeds 等）覆盖。"""

    @classmethod
    def setUpClass(cls):
        cls.prereg = load_fixture_prereg()
        cls.s3_run = load_fixture_run(cls.prereg)

    def test_run_data_properties(self):
        self.assertEqual(self.s3_run.run_mode, "SMOKE")
        self.assertTrue(self.s3_run.is_smoke)
        self.assertEqual(self.s3_run.run_id, FIXTURE_RUN_ID)
        self.assertEqual(int(self.s3_run.n_tasks), SMOKE_EVAL_TASKS)
        self.assertEqual(len(self.s3_run.arms), len(sp.S3_ARMS))
        self.assertEqual(set(self.s3_run.arms), set(sp.S3_ARMS))
        self.assertEqual(tuple(self.s3_run.budgets), tuple(SMOKE_BUDGETS))
        self.assertEqual(tuple(self.s3_run.opt_seeds), tuple(SMOKE_OPT_SEEDS))
        self.assertEqual(tuple(self.s3_run.meta_seeds), tuple(SMOKE_META_SEEDS))
        self.assertEqual(int(self.s3_run.record_counts["eval"]), 3840)


class AuxLoaderAndBuilderTests(unittest.TestCase):
    """负控/确定性 loader 与 OOD/确定性行构造（补覆盖率，不依赖真实 run 目录产物）。"""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="p4ra-s3-aux-"))
        self.base = self._tmp

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _eval_record(self, *, f=1.0, wall_s=0.1, digest="a" * 64, evaluation_index=1, **overrides):
        record = {
            "schema_version": sp.S3_RECORD_SCHEMA_VERSION,
            "run_id": "p4ra-s3-run-aux",
            "task_id": "t0",
            "split": "meta_test",
            "arm_id": sp.S3_ARMS[0],
            "budget": 64,
            "opt_seed": 0,
            "meta_seed": 0,
            "evaluation_index": evaluation_index,
            "design": [0.5] * 12,
            "f": f,
            "g1": 1.0,
            "g2": 1.0,
            "feasible": False,
            "source": "bo",
            "phase": "EVAL",
            "holdout_truth_read": True,
            "wall_s": wall_s,
            "record_digest": digest,
        }
        record.update(overrides)
        return record

    def _write_stream(self, path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(sp.canonical_json(record) for record in records) + "\n"
        path.write_bytes(payload.encode("utf-8"))

    # ---- negative_control loader ----
    def test_load_negative_control_missing_dir_disclosed(self):
        checks = []
        result = an._load_negative_control(self.base, grid={}, checks=checks)
        self.assertEqual(result, {"records": [], "summary": {}, "available": False})
        self.assertTrue(any(item["check"] == "negative_control_artifacts" and item["status"] == "DISCLOSED" for item in checks))

    def test_load_negative_control_with_artifacts(self):
        directory = self.base / "negative_control"
        self._write_stream(directory / "records.jsonl", [self._eval_record()])
        (directory / "summary.json").write_bytes(b'{"runs": 300, "label_shuffled": true}')
        checks = []
        result = an._load_negative_control(self.base, grid={}, checks=checks)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["summary"], {"runs": 300, "label_shuffled": True})
        self.assertTrue(any(item["check"] == "negative_control_artifacts" and item["status"] == "PASS" for item in checks))

    def test_load_negative_control_bad_summary_schema(self):
        directory = self.base / "negative_control"
        directory.mkdir(parents=True)
        (directory / "summary.json").write_bytes(b"[]")
        expect_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID,
                     lambda: an._load_negative_control(self.base, grid={}, checks=[]))

    def test_load_negative_control_run_root_layout(self):
        # A1 runner FORMAL 布局：摘要/记录在 run 根，不在 negative_control/ 子目录
        (self.base / "negative_control_summary.json").write_bytes(b'{"runs": 300, "shuffled_con_minus_obj_feasible_hit_rate": 0.01}')
        self._write_stream(self.base / "negative_control_records.jsonl", [self._eval_record(split="meta_test_negative_control", phase="NEGATIVE_CONTROL")])
        checks = []
        result = an._load_negative_control(self.base, grid={}, checks=checks)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["summary"]["runs"], 300)
        self.assertTrue(any(item["check"] == "negative_control_artifacts" and item["status"] == "PASS" for item in checks))

    # ---- determinism loader ----
    def test_load_determinism_missing_dir_disclosed(self):
        checks = []
        result = an._load_determinism(self.base, grid={}, checks=checks)
        self.assertFalse(result["available"])
        self.assertIsNone(result["core_digest_equal"])
        self.assertTrue(any(item["check"] == "determinism_artifacts" and item["status"] == "DISCLOSED" for item in checks))

    def test_load_determinism_equal_passes_ignores_volatile_fields(self):
        r1 = self._eval_record(f=1.0, wall_s=0.1)
        # r2 只改 wall_s / record_digest（core digest 排除的字段），核心一致
        r2 = self._eval_record(f=1.0, wall_s=9.9, digest="b" * 64)
        for name, records in (("r1", [r1]), ("r2", [r2]), ("r3", [r1])):
            self._write_stream(self.base / "determinism" / name / "run_records.jsonl", records)
        checks = []
        result = an._load_determinism(self.base, grid={}, checks=checks)
        self.assertTrue(result["available"])
        self.assertEqual([item["name"] for item in result["passes"]], ["r1", "r2", "r3"])
        self.assertTrue(result["core_digest_equal"])
        self.assertTrue(any(item["check"] == "determinism_core_digest" and item["status"] == "PASS" for item in checks))

    def test_load_determinism_missing_single_pass_disclosed(self):
        reference = [self._eval_record(f=1.0)]
        self._write_stream(self.base / "determinism" / "r1" / "run_records.jsonl", reference)
        self._write_stream(self.base / "determinism" / "r3" / "run_records.jsonl", reference)
        checks = []
        result = an._load_determinism(self.base, grid={}, checks=checks)
        self.assertEqual([item["name"] for item in result["passes"]], ["r1", "r3"])
        self.assertTrue(result["core_digest_equal"])
        self.assertTrue(any(item["check"] == "determinism_r2" and item["status"] == "DISCLOSED" for item in checks))

    def test_load_determinism_core_mismatch_error(self):
        self._write_stream(self.base / "determinism" / "r1" / "run_records.jsonl", [self._eval_record(f=1.0)])
        self._write_stream(self.base / "determinism" / "r2" / "run_records.jsonl", [self._eval_record(f=3.0)])
        self._write_stream(self.base / "determinism" / "r3" / "run_records.jsonl", [self._eval_record(f=1.0)])
        expect_error(self, an.S3_ANALYSIS_DETERMINISM_MISMATCH,
                     lambda: an._load_determinism(self.base, grid={}, checks=[]))

    # ---- determinism rows ----
    def test_build_determinism_rows_not_run(self):
        checks = []
        rows = an.build_determinism_rows(SimpleNamespace(determinism={"available": False}), checks=checks)
        self.assertEqual(rows, [{"pass": "r1", "status": "NOT_RUN", "reason": "run 目录无 determinism/"}])
        self.assertTrue(any(item["check"] == "determinism_rows" and item["status"] == "DISCLOSED" for item in checks))

    def test_build_determinism_rows_ok(self):
        checks = []
        determinism = {
            "available": True,
            "passes": [{"name": "r1", "records": 2, "eval_core_digests": ["d1", "d2"]},
                       {"name": "r2", "records": 2, "eval_core_digests": ["d1", "d2"]}],
            "core_digest_equal": True,
        }
        rows = an.build_determinism_rows(SimpleNamespace(determinism=determinism), checks=checks)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "OK")
        self.assertEqual(rows[0]["n_eval_core_digests"], 2)
        self.assertTrue(rows[0]["core_digest_equal"])
        self.assertTrue(any(item["check"] == "determinism_rows" and item["status"] == "PASS" for item in checks))

    # ---- OOD rows ----
    OOD_GRID = {"arms": list(sp.S3_ARMS), "budgets": [64, 128]}

    def test_build_ood_rows_without_segment_not_run(self):
        checks = []
        rows = an.build_ood_rows(SimpleNamespace(), [], grid=self.OOD_GRID, checks=checks)
        self.assertEqual(len(rows), len(sp.S3_ARMS) * 2)
        self.assertTrue(all(row["status"] == "NOT_RUN" for row in rows))
        self.assertTrue(any(item["check"] == "ood_artifacts" and item["status"] == "DISCLOSED" for item in checks))

    def test_build_ood_rows_with_segment_ok(self):
        endpoints = []
        for task in ("t0", "t1"):
            for arm in sp.S3_ARMS:
                for budget in (64, 128):
                    endpoints.append({"task_id": task, "split": "meta_test_ood", "arm_id": arm,
                                      "budget": budget, an.C1_ENDPOINT: 0.5})
        checks = []
        rows = an.build_ood_rows(SimpleNamespace(), endpoints, grid=self.OOD_GRID, checks=checks)
        self.assertEqual(len(rows), len(sp.S3_ARMS) * 2)
        self.assertTrue(all(row["status"] == "OK" for row in rows))
        self.assertTrue(all(row["n_tasks"] == 2 for row in rows))
        self.assertTrue(all(row["feasible_hit_rate_mean"] == 0.5 for row in rows))
        self.assertTrue(any(item["check"] == "ood_artifacts" and item["status"] == "PASS" for item in checks))

    # ---- S3Prereg.n_tasks property ----
    def test_prereg_n_tasks_property(self):
        prereg = object.__new__(an.S3Prereg)
        object.__setattr__(prereg, "family", {"split_counts": {"meta_test": 20}})
        self.assertEqual(prereg.n_tasks, 20)
        object.__setattr__(prereg, "family", {"splits": {"meta_test": ["a", "b"]}})
        self.assertEqual(prereg.n_tasks, 2)
        object.__setattr__(prereg, "family", {})
        self.assertEqual(prereg.n_tasks, 0)


class QuickHelperTests(unittest.TestCase):
    """基础校验/读写 helper 的边界单元测试。"""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="p4ra-s3-helper-"))
        self.base = self._tmp

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_require_number_bounds(self):
        code = an.S3_ANALYSIS_RUN_SCHEMA_INVALID
        self.assertEqual(an._require_number(3.5, code=code, label="x"), 3.5)
        self.assertEqual(an._require_number(2, code=code, label="x", minimum=2, maximum=2), 2.0)
        self.assertIsNone(an._require_number(None, code=code, label="x", allow_none=True))
        expect_error(self, code, lambda: an._require_number(None, code=code, label="x"))
        expect_error(self, code, lambda: an._require_number("1", code=code, label="x"))
        expect_error(self, code, lambda: an._require_number(float("nan"), code=code, label="x"))
        expect_error(self, code, lambda: an._require_number(1.0, code=code, label="x", minimum=2))
        expect_error(self, code, lambda: an._require_number(3.0, code=code, label="x", maximum=2))

    def test_require_int_rejects_non_int(self):
        code = an.S3_ANALYSIS_RUN_SCHEMA_INVALID
        self.assertEqual(an._require_int(3, code=code, label="k"), 3)
        expect_error(self, code, lambda: an._require_int(3.5, code=code, label="k"))
        expect_error(self, code, lambda: an._require_int("3", code=code, label="k"))
        expect_error(self, code, lambda: an._require_int(-1, code=code, label="k", minimum=0))

    def test_as_sha256_or_none(self):
        self.assertEqual(an._as_sha256_or_none("A" * 64), "a" * 64)
        self.assertIsNone(an._as_sha256_or_none(None))
        self.assertIsNone(an._as_sha256_or_none("A" * 63))
        self.assertIsNone(an._as_sha256_or_none("g" * 64))

    def test_accepted_fd_gate_modes(self):
        modes = an._accepted_fd_gate_modes()
        self.assertEqual(modes[0], sp.S3_FD_MODE)
        for item in ("fomaml+anil", "fomaml", "anil"):
            self.assertIn(item, modes)

    def test_rs3_02_fallback(self):
        fallback = an._rs3_02_fallback()
        self.assertIsInstance(fallback, dict)
        self.assertIn("main_runs", fallback)
        self.assertEqual(int(fallback["main_runs"]), 3000)

    def test_read_json_file_ok_and_errors(self):
        code = an.S3_ANALYSIS_RUN_SCHEMA_INVALID
        path = self.base / "ok.json"
        path.write_bytes(b'{"a": 1}')
        self.assertEqual(an._read_json_file(path, code=code, label="ok"), {"a": 1})
        expect_error(self, code, lambda: an._read_json_file(self.base / "missing.json", code=code, label="x"))
        bad = self.base / "bad.json"
        bad.write_bytes(b"\xff\xfe\x00")
        expect_error(self, code, lambda: an._read_json_file(bad, code=code, label="bad"))

    def test_write_csv_roundtrip(self):
        path = self.base / "nested" / "out.csv"
        sha = an._write_csv(path, columns=["a", "b"], rows=[{"a": 1, "b": None}, {"a": 2, "b": 3}])
        self.assertRegex(sha, "^[0-9a-f]{64}$")
        text = path.read_text(encoding="utf-8")
        self.assertIn("a,b", text)
        self.assertIn("1,", text)
        self.assertIn("2,3", text)


# ---------------------------------------------------------------------------
# F 段：A5-S3M1-B01 —— Holm 校正后决策回填（raw p 不参与判定）
# ---------------------------------------------------------------------------
def _csv_rows(path):
    import csv

    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _json_file(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _holmb01_mock_wilcoxon(testcase, p_values):
    """把精确 Wilcoxon 替换为受控 p 值序列（仅用于决策回填单测）。"""
    import unittest.mock as mock

    side_effect = [
        {
            "p_two_sided": float(p),
            "n_zero": 0,
            "n_eff": 20,
            "w_plus": 10.0,
            "method": "exact_sign_flip_tie_aware",
        }
        for p in p_values
    ]
    return mock.patch.object(an, "wilcoxon_signed_rank_exact", side_effect=side_effect)


def _holmb01_endpoints(tasks, *, c1_delta=0.10, c2_delta=-0.05):
    """构造受控端点行：C1（feasible_hit_rate，CON−OBJ 均值=c1_delta）、C2（gap，相对效应由 c2_delta 决定）。"""
    rows = []
    for budget in (64, 128):
        for task in tasks:
            for arm in sp.S3_ARMS:
                if arm == "S3-BO-FOMAML-CON":
                    c1 = 0.50 + c1_delta
                    c2 = 0.10 + c2_delta
                else:
                    c1 = 0.50
                    c2 = 0.10
                rows.append(
                    {
                        "task_id": str(task),
                        "budget": int(budget),
                        "arm_id": str(arm),
                        "split": "meta_test",
                        "feasible_hit_rate": float(c1),
                        "gap_to_reference": float(c2),
                    }
                )
    return rows


class HolmCorrectedDecisionTests(unittest.TestCase):
    """A5-S3M1-B01：所有 test/层/overall 决策都必须由 Holm 校正后的 p_holm 经 decide_layer 重算。"""

    @classmethod
    def setUpClass(cls):
        cls.s3_run = load_fixture_run()
        cls.grid = dict(cls.s3_run.grid)
        cls.tasks = sorted(cls.grid["task_ids"])

    def _infer(self, endpoints, p_values):
        checks = []
        with _holmb01_mock_wilcoxon(self, p_values):
            inference = an.build_inference(endpoints, tasks=self.tasks, grid=self.grid, checks=checks)
        return inference, checks

    def _holm_by_id(self, inference):
        return {row["test_id"]: row for row in inference["holm_rows"]}

    def test_holm_row_contract_has_p_raw_p_holm_decision(self):
        inference, checks = self._infer(_holmb01_endpoints(self.tasks), [0.04, 0.02, 0.04, 0.02])
        self.assertEqual(len(inference["holm_rows"]), 4)
        for row in inference["holm_rows"]:
            for field in ("p_raw", "p_holm", "decision", "family_id", "test_id", "rank", "reject"):
                self.assertIn(field, row)
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("holm_decision_recomputed"), "PASS")

    def test_raw_004_becomes_holm_008_not_significant(self):
        # 族内 m=2：raw 0.04 → p_holm 0.08 ≥ 0.05 → B64 层不得 BENEFIT/HARM；overall 不得 BENEFIT/HARM。
        inference, _ = self._infer(_holmb01_endpoints(self.tasks), [0.04, 0.06, 0.02, 0.02])
        rows = self._holm_by_id(inference)
        self.assertAlmostEqual(rows["C1b"]["p_raw"], 0.04)
        # Holm（m=2，step-down）：min raw 0.04 x2 = 0.08；max raw 0.06 取 max(0.06, 0.08)=0.08。
        self.assertAlmostEqual(rows["C1b"]["p_holm"], 0.08)
        self.assertAlmostEqual(rows["C1a"]["p_holm"], 0.08)
        self.assertNotIn(inference["c1_decisions"]["B64"], (an.D_SUPPORTED_BENEFIT, an.D_SUPPORTED_HARM))
        self.assertEqual(inference["c1_decisions"]["B64"], an.D_NULL)
        self.assertEqual(rows["C1b"]["decision"], an.D_NULL)
        self.assertNotIn(inference["overall_decision"], (an.O_BENEFIT, an.O_HARM))

    def test_raw_002_becomes_holm_004_significant(self):
        # raw 0.02 → p_holm 0.04 < 0.05 → 按效应方向显著（positive → BENEFIT）。
        inference, _ = self._infer(_holmb01_endpoints(self.tasks), [0.02, 0.02, 0.02, 0.02])
        rows = self._holm_by_id(inference)
        self.assertAlmostEqual(rows["C1a"]["p_holm"], 0.04)
        self.assertEqual(inference["c1_decisions"]["B64"], an.D_SUPPORTED_BENEFIT)
        self.assertEqual(inference["c1_decisions"]["B128"], an.D_SUPPORTED_BENEFIT)
        self.assertEqual(inference["overall_decision"], an.O_BENEFIT)
        self.assertEqual(rows["C1b"]["decision"], an.D_SUPPORTED_BENEFIT)

    def test_p_holm_equal_005_not_significant(self):
        # raw 0.025 → p_holm==0.05，严格小于才显著（边界测试）。
        inference, _ = self._infer(_holmb01_endpoints(self.tasks), [0.025, 0.05, 0.025, 0.05])
        rows = self._holm_by_id(inference)
        self.assertEqual(float(rows["C1b"]["p_holm"]), 0.05)
        self.assertEqual(inference["c1_decisions"]["B64"], an.D_NULL)
        self.assertEqual(an.decide_layer(p_value=0.05, effect=1.0, threshold=0.02, benefit_direction="positive", n_eff=20), an.D_NULL)
        self.assertEqual(
            an.decide_layer(p_value=0.049999, effect=1.0, threshold=0.02, benefit_direction="positive", n_eff=20),
            an.D_SUPPORTED_BENEFIT,
        )

    def test_decision_is_function_of_p_holm_invariant(self):
        # 不变量：每个 test 的 decision == decide_layer(p_holm, effect, threshold, direction, n_eff)。
        inference, _ = self._infer(_holmb01_endpoints(self.tasks), [0.04, 0.02, 0.04, 0.02])
        for tests in inference["families"].values():
            for item in tests:
                expected = an.decide_layer(
                    p_value=item["p_holm"],
                    effect=item["effect"],
                    threshold=item["threshold"],
                    benefit_direction=item["benefit_direction"],
                    n_eff=item["n_eff"],
                )
                self.assertEqual(item["decision"], expected, msg=item["test_id"])
        for row in inference["holm_rows"]:
            self.assertEqual(row["decision"], self._holm_by_id(inference)[row["test_id"]]["decision"])

    def test_decision_is_function_of_p_holm_invariant_real_fixture(self):
        # 真实统计（n_eff<15 → 全 INCONCLUSIVE）下不变量仍成立，且 holm 行与 family 行一致。
        checks = []
        endpoints = an.compute_run_endpoints(self.s3_run, an.load_references_sealed(load_fixture_prereg(), repo_root=workspace()["evidence"]["root"], checks=[]), checks=checks)
        main, _ = an.split_main_and_aux(endpoints)
        inference = an.build_inference(main, tasks=self.tasks, grid=self.grid, checks=checks)
        for row in inference["holm_rows"]:
            tests = inference["families"][row["family_id"]]
            item = [value for value in tests if value["test_id"] == row["test_id"]][0]
            expected = an.decide_layer(
                p_value=item["p_holm"],
                effect=item["effect"],
                threshold=item["threshold"],
                benefit_direction=item["benefit_direction"],
                n_eff=item["n_eff"],
            )
            self.assertEqual(item["decision"], expected)
            self.assertEqual(row["decision"], expected)

    def test_harm_direction_after_holm(self):
        # C1 反向（CON 比 OBJ 低 0.10）→ raw 0.02 → p_holm 0.04 → HARM；overall 也为 HARM。
        inference, _ = self._infer(_holmb01_endpoints(self.tasks, c1_delta=-0.10, c2_delta=0.05), [0.02, 0.02, 0.02, 0.02])
        self.assertEqual(inference["c1_decisions"]["B64"], an.D_SUPPORTED_HARM)
        self.assertEqual(inference["c1_decisions"]["B128"], an.D_SUPPORTED_HARM)
        self.assertEqual(inference["overall_decision"], an.O_HARM)
        self.assertEqual(inference["c2_decisions"]["B64"], an.D_SUPPORTED_HARM)

    def test_harm_direction_not_reported_when_holm_not_significant(self):
        # 同反向数据但 raw 0.04（p_holm 0.08）→ 不得判 HARM（B64=NULL），overall 不得 HARM。
        inference, _ = self._infer(_holmb01_endpoints(self.tasks, c1_delta=-0.10, c2_delta=0.05), [0.04, 0.06, 0.04, 0.06])
        self.assertEqual(inference["c1_decisions"]["B64"], an.D_DIRECTION_INCONSISTENT)
        self.assertNotEqual(inference["overall_decision"], an.O_HARM)
        self.assertNotEqual(inference["c1_decisions"]["B64"], an.D_SUPPORTED_HARM)
        self.assertEqual(inference["overall_decision"], an.O_DIRECTION_INCONSISTENT)

    def test_overall_only_uses_c1_pair(self):
        # C2 显著不影响 overall：C1 两层均为 NULL 时 overall 恒 NO_EVIDENCE，即使 C2=BENEFIT。
        inference, _ = self._infer(_holmb01_endpoints(self.tasks), [0.04, 0.04, 0.02, 0.02])
        self.assertEqual(inference["c1_decisions"], {"B64": an.D_NULL, "B128": an.D_NULL})
        self.assertEqual(inference["c2_decisions"]["B64"], an.D_SUPPORTED_BENEFIT)
        self.assertEqual(inference["overall_decision"], an.O_NO_EVIDENCE)

    def test_overall_decision_priority_matrix(self):
        # 3×3（B64/B128 层判定组合）固定优先级：INCONCLUSIVE > HARM > DIRECTION_INCONSISTENT > 双层 BENEFIT > 其余 NO_EVIDENCE。
        pairs = [
            ((an.D_SUPPORTED_BENEFIT, an.D_SUPPORTED_BENEFIT), an.O_BENEFIT),
            ((an.D_SUPPORTED_BENEFIT, an.D_NULL), an.O_NO_EVIDENCE),
            ((an.D_SUPPORTED_BENEFIT, an.D_NEGLIGIBLE_SIGNIFICANT), an.O_NO_EVIDENCE),
            ((an.D_SUPPORTED_BENEFIT, an.D_INCONCLUSIVE), an.O_INCONCLUSIVE),
            ((an.D_SUPPORTED_HARM, an.D_SUPPORTED_BENEFIT), an.O_HARM),
            ((an.D_SUPPORTED_HARM, an.D_INCONCLUSIVE), an.O_INCONCLUSIVE),
            ((an.D_DIRECTION_INCONSISTENT, an.D_SUPPORTED_BENEFIT), an.O_DIRECTION_INCONSISTENT),
            ((an.D_NULL, an.D_NULL), an.O_NO_EVIDENCE),
            ((an.D_NEGLIGIBLE_SIGNIFICANT, an.D_NEGLIGIBLE_SIGNIFICANT), an.O_NO_EVIDENCE),
        ]
        for pair, expected in pairs:
            self.assertEqual(an.decide_overall({"B64": pair[0], "B128": pair[1]}), expected, msg=str(pair))

    def test_decision_layer_requires_holm_p_less_than_alpha(self):
        # decide_layer 单独语义：p_holm≥0.05 时任何正向大效应都只能是 NULL（only-p 决定显著性）。
        for effect in (0.02, 0.10, 1.00):
            self.assertEqual(an.decide_layer(p_value=0.05, effect=effect, threshold=0.02, benefit_direction="positive", n_eff=20), an.D_NULL)
        self.assertEqual(an.decide_layer(p_value=None, effect=1.0, threshold=0.02, benefit_direction="positive", n_eff=20), an.D_INCONCLUSIVE)
        self.assertEqual(an.decide_layer(p_value=0.01, effect=1.0, threshold=0.02, benefit_direction="positive", n_eff=14), an.D_INCONCLUSIVE)

    def test_aggregate_and_csv_expose_holm_decision(self):
        # aggregate.json 与 s3_holm_family.csv 每个 test 同时含 p_raw/p_holm/decision。
        runs = _e2e_runs()
        aggregate = _json_file(Path(runs["plain_dir"]) / an.S3_AGGREGATE_JSON)
        for row in aggregate["inference"]["families"][an.C1_FAMILY_ID]:
            for field in ("p_raw", "p_holm", "decision"):
                self.assertIn(field, row)
        self.assertTrue(all("decision" in row for row in aggregate["inference"]["holm_rows"]))
        csv_rows = _csv_rows(Path(runs["plain_dir"]) / "s3_holm_family.csv")
        self.assertTrue(csv_rows)
        for field in ("p_raw", "p_holm", "decision"):
            self.assertIn(field, csv_rows[0])


# ---------------------------------------------------------------------------
# G 段：A5-S3M1-m04 —— FORMAL 形状结构级 e2e（不物化 362,880 行记录）
# ---------------------------------------------------------------------------
class FormalShapeStructuralTests(unittest.TestCase):
    """FORMAL 形状 config/summary/manifest/gate 结构级校验链。

    说明（如实披露）：FORMAL 网格固定 20 tasks × 5 arms × 2 budgets × 5 opt × 3 meta（3,000 runs）
    以及 NC/OOD/DET 辅助流合计 362,880 条评估记录；为在单测内可运行，这里物化 FORMAL 形状的
    run_config/run_summary/data_manifest/model_manifest/FD gate 最小文件（不写 362,880 行记录），
    然后直接调用 load_s3_run 内部同源校验函数链（_validate_run_config → _derive_run_grid →
    _validate_run_summary → _validate_data_manifest → _validate_model_manifest → _validate_gate_artifact
    → _validate_record_stream_counts）做结构级断言；记录级 362,880 行校验由正式 run 保证。
    """

    @classmethod
    def setUpClass(cls):
        ws = workspace()
        cls.ws = ws
        cls.prereg = load_fixture_prereg()
        cls.run_dir = ws["run"]["run_dir"]
        cls.base_config = json.loads((cls.run_dir / "run_config.json").read_text(encoding="utf-8"))
        cls.base_summary = json.loads((cls.run_dir / "run_summary.json").read_text(encoding="utf-8"))
        cls.base_manifest = json.loads((cls.run_dir / "data_manifest.json").read_text(encoding="utf-8"))
        cls.base_model_manifest = json.loads((cls.run_dir / "model_manifest.json").read_text(encoding="utf-8"))
        cls.formal_config = cls._formal_config()
        cls.formal_summary = cls._formal_summary()
        cls.formal_data_manifest = cls._formal_data_manifest()
        cls.formal_model_manifest = cls._formal_model_manifest()
        cls.formal_gate = cls._formal_gate_artifact()
        cls.formal_dir = ws["base"] / "formal-shape"
        cls.formal_dir.mkdir(parents=True, exist_ok=True)
        _write_json(cls.formal_dir / "run_config.json", cls.formal_config)
        _write_json(cls.formal_dir / "run_summary.json", cls.formal_summary)
        _write_json(cls.formal_dir / "data_manifest.json", cls.formal_data_manifest)
        _write_json(cls.formal_dir / "model_manifest.json", cls.formal_model_manifest)
        _write_json(cls.formal_dir / "fd_or_gradient_gate.json", cls.formal_gate)
        (cls.formal_dir / "run_records.jsonl").write_bytes(b"")

    # --- FORMAL 形状构造 ---------------------------------------------------
    @classmethod
    def _formal_config(cls):
        config = json.loads(json.dumps(cls.base_config))
        config["run_mode"] = "FORMAL"
        config.pop("smoke_overrides", None)
        config["budgets"] = {"budgets": list(sp.S3_BUDGETS), "k_shot": sp.S3_K_SHOT}
        config["seeds"] = {"opt_seeds": [0, 1, 2, 3, 4], "meta_seeds": [0, 1, 2], "k_shot": sp.S3_K_SHOT}
        config["evaluation_grid"] = {
            "eval_split": sp.S3_EVAL_SPLIT,
            "eval_tasks": 20,
            "budgets": list(sp.S3_BUDGETS),
            "K": [sp.S3_K_SHOT],
            "meta_seeds": [0, 1, 2],
            "opt_seeds": [0, 1, 2, 3, 4],
            "main_runs": 3000,
            "main_evals": 288000,
        }
        config["episode_bank"] = {
            "banks": dict(cls.prereg.obj["episode_bank"]["banks"]),
            "episodes": int(sp.S3_EPISODE_BANK_EPISODES_PER_BANK),
        }
        config["k_sweep"] = [int(sp.S3_K_SHOT)]
        config["record_counts"] = {
            "train": 0,
            "eval": 362880,
            "total": 362880,
            "train_expected": 0,
            "eval_expected": 362880,
        }
        config["fd_or_gradient_gate"] = {
            "sha256": str(cls.prereg.obj["fd_gate_sha256"]),
            "coordinates_per_model": int(sp.S3_FD_MAX_COORDINATES),
            "coordinates_total": 64,
            "mode": "FORMAL",
            "override": False,
            "models": {
                "fomaml_meta_0": {
                    "path": sp.S3_GATE_RELPATH,
                    "sha256": "b" * 64,
                    "n_checked": int(sp.S3_FD_MAX_COORDINATES),
                    "status": "PASS",
                    "max_relative_error": 3.2e-09,
                },
                "anil_meta_0": {
                    "path": sp.S3_GATE_RELPATH,
                    "sha256": "b" * 64,
                    "n_checked": int(sp.S3_FD_MAX_COORDINATES),
                    "status": "PASS",
                    "max_relative_error": 3.2e-09,
                },
            },
        }
        return config

    @classmethod
    def _formal_summary(cls):
        summary = json.loads(json.dumps(cls.base_summary))
        summary["run_mode"] = "FORMAL"
        summary["record_counts"] = {"train": 0, "eval": 362880, "total": 362880}
        summary["status_counts"] = {
            "train": {"OK": 0, "FAILED": 0},
            "eval": {"OK": 362880, "FAILED": 0},
        }
        return summary

    @classmethod
    def _formal_data_manifest(cls):
        manifest = json.loads(json.dumps(cls.base_manifest))
        artifact = dict(manifest.get("artifact_sha256") or {})
        artifact["negative_control_records.jsonl"] = "1" * 64
        artifact["ood_records.jsonl"] = "2" * 64
        for name in an.DETERMINISM_REPEAT_NAMES:
            artifact[an.DETERMINISM_DIR + "/" + str(name) + "/" + an.RUN_RECORDS_FILE] = "3" * 64
        manifest["artifact_sha256"] = artifact
        return manifest

    @classmethod
    def _formal_model_manifest(cls):
        manifest = json.loads(json.dumps(cls.base_model_manifest))
        manifest["run_id"] = "p4ra-s3-m2-frozen-run"
        manifest["verification"] = {
            "loaded_from_prereg": True,
            "prereg_models_sha256": "d" * 64,
            "verified_utc": FIXTURE_CREATED_UTC,
        }
        for entry in manifest["models"]:
            entry["meta_seed"] = int(entry["meta_seed"])
        return manifest

    @classmethod
    def _formal_gate_artifact(cls):
        coordinates = [
            {
                "index": index,
                "param": "param_%03d" % index,
                "analytic": 1.0 + index,
                "numeric": 1.0 + index + 1e-10 * (index + 1),
                "relative_error": 1e-10 * (index + 1),
            }
            for index in range(int(sp.S3_FD_MAX_COORDINATES))
        ]
        return {
            "schema_version": "p4ra-s3-fd-gate-v1",
            "created_utc": FIXTURE_CREATED_UTC,
            "status": "PASS",
            "mode": sp.S3_FD_MODE,
            "tolerance": 1e-06,
            "epsilon_rule": "1e-6*max(1,|theta|)",
            "coordinates_per_model": int(sp.S3_FD_MAX_COORDINATES),
            "coordinates_total": 64,
            "max_relative_error": 3.2e-09,
            "models": {
                "fomaml_meta_0": {
                    "arm_type": "fomaml",
                    "meta_seed": 0,
                    "n_checked": int(sp.S3_FD_MAX_COORDINATES),
                    "status": "PASS",
                    "max_relative_error": 3.2e-09,
                    "coordinates": [dict(item) for item in coordinates],
                },
                "anil_meta_0": {
                    "arm_type": "anil",
                    "meta_seed": 0,
                    "n_checked": int(sp.S3_FD_MAX_COORDINATES),
                    "status": "PASS",
                    "max_relative_error": 3.2e-09,
                    "coordinates": [dict(item) for item in coordinates],
                },
            },
            "negatives": {"tamper": "PASS", "anil_body_frozen": "PASS", "k0_equivalence": "PASS"},
            "physical_call_count": 0,
        }

    @classmethod
    def _streams(cls, grid):
        expected = an._expected_stream_counts(grid, cls.prereg)
        aux = {
            "available": True,
            "nc": {
                "runs": int(expected["nc"]["runs"]),
                "records": int(expected["nc"]["records"]),
                "status_counts": {"OK": int(expected["nc"]["records"]), "FAILED": 0},
            },
            "ood": {
                "runs": int(expected["ood"]["runs"]),
                "records": int(expected["ood"]["records"]),
                "status_counts": {"OK": int(expected["ood"]["records"]), "FAILED": 0},
            },
            "det": {
                "repeats": [
                    {
                        "name": name,
                        "runs": int(expected["det"]["runs_per_repeat"]),
                        "records": int(expected["det"]["records_per_repeat"]),
                        "status_counts": {"OK": int(expected["det"]["records_per_repeat"]), "FAILED": 0},
                    }
                    for name in an.DETERMINISM_REPEAT_NAMES
                ],
                "runs": int(expected["det"]["runs"]),
                "records": int(expected["det"]["records"]),
                "status_counts": {"OK": int(expected["det"]["records"]), "FAILED": 0},
            },
        }
        return expected, aux

    # --- 测试 --------------------------------------------------------------
    def test_formal_config_and_grid_structural_pass(self):
        checks = []
        config = an._validate_run_config(json.loads(json.dumps(self.formal_config)), self.prereg, checks=checks)
        grid = an._derive_run_grid(config, self.prereg, checks=checks)
        self.assertEqual(grid["run_mode"], "FORMAL")
        self.assertEqual(grid["train_expected"], 0)
        self.assertEqual(grid["outer_steps"], 200)
        self.assertEqual(grid["run_count"], 3000)
        self.assertEqual(grid["eval_records_expected"], 288000)
        self.assertEqual(grid["eval_tasks"], 20)
        self.assertEqual(tuple(grid["budgets"]), tuple(sp.S3_BUDGETS))
        names = {str(item.get("check")) for item in checks}
        for name in ("run_grid_formal_k_sweep", "run_grid_formal_train0", "fd_gate_config", "k_sweep_config", "record_counts"):
            self.assertIn(name, names)

    def test_formal_summary_manifests_and_gate_structural_pass(self):
        checks = []
        config = an._validate_run_config(json.loads(json.dumps(self.formal_config)), self.prereg, checks=checks)
        grid = an._derive_run_grid(config, self.prereg, checks=checks)
        summary = an._validate_run_summary(
            json.loads(json.dumps(self.formal_summary)),
            config,
            self.prereg,
            grid,
            actual_counts={"train": 0, "eval": 362880, "total": 362880},
            checks=checks,
        )
        self.assertEqual(summary["status_counts"]["train"], {"OK": 0, "FAILED": 0})
        an._validate_data_manifest(json.loads(json.dumps(self.formal_data_manifest)), config, self.prereg, grid, checks=checks)
        an._validate_model_manifest(json.loads(json.dumps(self.formal_model_manifest)), config, self.prereg, checks=checks)
        an._validate_gate_artifact(json.loads(json.dumps(self.formal_gate)), config, self.prereg, checks=checks)
        names = {str(item.get("check")) for item in checks}
        for name in ("run_summary_schema", "data_manifest_boundary", "fd_gate_artifact", "fd_gate_negatives", "fd_gate_artifact_models"):
            self.assertIn(name, names)
        self.assertFalse({str(item.get("status")) for item in checks} & {"FAIL"})

    def test_formal_five_record_streams_pass(self):
        checks = []
        config = an._validate_run_config(json.loads(json.dumps(self.formal_config)), self.prereg, checks=checks)
        grid = an._derive_run_grid(config, self.prereg, checks=checks)
        expected, aux = self._streams(grid)
        self.assertEqual(int(expected["total"]["records"]), 362880)
        self.assertEqual(int(expected["total"]["runs"]), 3780)
        self.assertEqual(int(expected["main"]["records"]), 288000)
        self.assertEqual(int(expected["nc"]["records"]), 28800)
        self.assertEqual(int(expected["ood"]["records"]), 28800)
        self.assertEqual(int(expected["det"]["records"]), 17280)
        stream_config = json.loads(json.dumps(config))
        stream_config["record_counts"] = {"train": 0, "eval": 362880, "total": 362880}
        by_stream = an._validate_record_stream_counts(
            config=stream_config,
            summary=json.loads(json.dumps(self.formal_summary)),
            grid=grid,
            prereg=self.prereg,
            main_counts={"train": 0, "eval": 288000, "eval_ok": 288000, "eval_failed": 0},
            aux_streams=aux,
            data_manifest=json.loads(json.dumps(self.formal_data_manifest)),
            checks=checks,
        )
        self.assertEqual(int(by_stream["total"]["records"]), 362880)
        self.assertEqual(int(by_stream["total"]["runs"]), 3780)
        self.assertEqual(by_stream["total"]["status_counts"], {"OK": 362880, "FAILED": 0})
        statuses = {str(item.get("check")): str(item.get("status")) for item in checks}
        self.assertEqual(statuses.get("record_stream_counts"), "PASS")

    def test_formal_record_counts_361000_fail_closed(self):
        checks = []
        config = an._validate_run_config(json.loads(json.dumps(self.formal_config)), self.prereg, checks=checks)
        grid = an._derive_run_grid(config, self.prereg, checks=checks)
        _, aux = self._streams(grid)
        bad_config = json.loads(json.dumps(config))
        bad_summary = json.loads(json.dumps(self.formal_summary))
        bad_config["record_counts"] = {"train": 0, "eval": 361000, "total": 361000}
        bad_summary["record_counts"] = {"train": 0, "eval": 361000, "total": 361000}
        bad_summary["status_counts"] = {"train": {"OK": 0, "FAILED": 0}, "eval": {"OK": 361000, "FAILED": 0}}
        error = expect_error(
            self,
            an.S3_ANALYSIS_RECORD_COUNTS_MISMATCH,
            lambda: an._validate_record_stream_counts(
                config=bad_config,
                summary=bad_summary,
                grid=grid,
                prereg=self.prereg,
                main_counts={"train": 0, "eval": 288000, "eval_ok": 288000, "eval_failed": 0},
                aux_streams=aux,
                data_manifest=json.loads(json.dumps(self.formal_data_manifest)),
                checks=[],
            ),
        )
        self.assertIn("361000", str(findattr(error, "detail", "")))

    def test_formal_train_records_nonzero_rejected(self):
        checks = []
        config = json.loads(json.dumps(self.formal_config))
        config["record_counts"] = {"train": 4, "eval": 362880, "total": 362884, "train_expected": 0, "eval_expected": 362880}
        error = expect_error(self, an.S3_ANALYSIS_RECORD_INVALID, lambda: an._validate_run_config(config, self.prereg, checks=checks))
        self.assertIn("训练记录", str(error.message))

    def test_formal_k_sweep_must_be_five(self):
        config = json.loads(json.dumps(self.formal_config))
        config["k_sweep"] = [0, 1, 3, 5]
        expect_error(self, an.S3_ANALYSIS_BUDGET_MISMATCH, lambda: an._validate_run_config(config, self.prereg, checks=[]))
        config = json.loads(json.dumps(self.formal_config))
        config["k_sweep"] = [5, 5]
        expect_error(self, an.S3_ANALYSIS_RUN_SCHEMA_INVALID, lambda: an._validate_run_config(config, self.prereg, checks=[]))

    def test_formal_gate_prereg_binding_fail_closed(self):
        config = json.loads(json.dumps(self.formal_config))
        config["fd_or_gradient_gate"]["sha256"] = "e" * 64
        expect_error(self, an.S3_ANALYSIS_RUN_BINDING_MISMATCH, lambda: an._validate_run_config(config, self.prereg, checks=[]))

    def test_formal_status_counts_semantics(self):
        checks = []
        config = an._validate_run_config(json.loads(json.dumps(self.formal_config)), self.prereg, checks=checks)
        grid = an._derive_run_grid(config, self.prereg, checks=checks)
        bad = json.loads(json.dumps(self.formal_summary))
        bad["status_counts"]["train"] = {"OK": 1, "FAILED": 0}
        expect_error(
            self,
            an.S3_ANALYSIS_RECORD_INVALID,
            lambda: an._validate_run_summary(
                bad, config, self.prereg, grid, actual_counts={"train": 0, "eval": 362880, "total": 362880}, checks=[]
            ),
        )

    def test_formal_shape_files_written(self):
        for name in ("run_config.json", "run_summary.json", "data_manifest.json", "model_manifest.json", "fd_or_gradient_gate.json", "run_records.jsonl"):
            path = self.formal_dir / name
            self.assertTrue(path.is_file(), msg=name)
        config = json.loads((self.formal_dir / "run_config.json").read_text(encoding="utf-8"))
        summary = json.loads((self.formal_dir / "run_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(config["run_mode"], "FORMAL")
        self.assertEqual(config["record_counts"]["train"], 0)
        self.assertEqual(summary["record_counts"]["eval"], 362880)
        self.assertEqual((self.formal_dir / "run_records.jsonl").stat().st_size, 0)

    def test_smoke_run_still_fully_analyzed(self):
        runs = _e2e_runs()
        plain = runs["plain"]
        self.assertEqual(plain["status"], "PASS")
        self.assertEqual(len(plain["artifacts"]), 9)
        self.assertEqual(plain["overall_decision"], an.O_INCONCLUSIVE)
        aggregate = _json_file(Path(runs["plain_dir"]) / an.S3_AGGREGATE_JSON)
        self.assertEqual(aggregate["run_mode"], "SMOKE")
        self.assertEqual(aggregate["record_counts_by_stream"]["total"]["records"], 3840)
