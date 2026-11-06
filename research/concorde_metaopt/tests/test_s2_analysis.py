# -*- coding: utf-8 -*-
"""P4 路线A S2 分析层单元测试（合成数据；不读 holdout、不启动任何求解器、physical_call_count=0）。

覆盖：prereg 强校验负控、run 合同/记录负控、task 级聚合、单 Holm 族 2 检验、
K=0/1 仅描述、7 张规范键图与 NOT_RUN 不伪造、CLI 退出码。
所有随机/数值均由本文件合成；bootstrap 种子固定为预注册值。
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.meta_learning import s2_analysis as s2

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="p4-s2-analysis-tests-"))
_BASE_ROOT = _TMP_ROOT / "repo"
_TASKS = ["S2VAL-%03d" % index for index in range(20)]
_RUN_ID = "s2-synthetic-run-0001"
_EVIDENCE_SCOPE = "DEVELOPMENT_VALIDATION_ONLY"
_BASE: dict = {}


def tearDownModule() -> None:
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


def _task_sha(ids):
    return hashlib.sha256(("\n".join(sorted(str(item) for item in ids)) + "\n").encode("utf-8")).hexdigest()


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _pilot_payload(*, max_relative_error=5e-9, n_checked=32, status="PASS"):
    """FD pilot 证据 payload（A1 契约：顶层 fd_gate 嵌套对象，micro=32 / full_size=8 坐标）。"""
    return {
        "fd_gate": {
            "schema_version": "p4-s2-fd-gate-pilot-1",
            "status": status,
            "mode": "full",
            "tolerance": 1e-6,
            "n_checked": int(n_checked),
            "coordinates_requested": int(n_checked),
            "coordinates_available": 185 if int(n_checked) >= 32 else 497,
            "max_relative_error": float(max_relative_error),
        }
    }


def _make_pilot_files(root: Path, *, max_relative_error=5e-9, status="PASS", coordinates=None):
    """写 FD pilot 证据文件并返回 prereg.pilot_artifacts（paths 相对仓库根 + raw sha256）。"""
    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, filename, default_n in (
        ("micro", "s2_fd_pilot_micro.json", 32),
        ("full_size", "s2_fd_pilot_full.json", 8),
    ):
        n_checked = int(coordinates) if coordinates is not None else default_n
        path = evidence / filename
        payload = _pilot_payload(max_relative_error=max_relative_error, n_checked=n_checked, status=status)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        files[name] = {"path": "evidence/" + filename, "sha256": s2._sha256_file(path)}
    return files


def _prereg_raw(root: Path, *, pilot=None):
    pilot = pilot if pilot is not None else _make_pilot_files(root)
    return {
        "schema_version": s2.PREREG_SCHEMA_VERSION,
        "created_utc": "2026-11-06T12:00:00Z",
        "upstream": {
            "issue": "#259",
            "decision": "P4 路线 A S2 执行计划 v1.4",
            "stage": "S2",
            "s1_receipt_comment_id": 7001,
        },
        "frozen_package": {
            "run_id": s2.FROZEN_PACKAGE_RUN_ID,
            "package_path": s2.FROZEN_PACKAGE_PATH,
            "sha256sums_sha256": s2.FROZEN_PACKAGE_SHA256SUMS_SHA256,
            "code_sha": s2.FROZEN_PACKAGE_CODE_SHA,
            "git_sha": s2.FROZEN_PACKAGE_GIT_SHA,
            "package_family_version": s2.FROZEN_PACKAGE_FAMILY_VERSION,
            "task_family_version": s2.FROZEN_PACKAGE_TASK_FAMILY_VERSION,
        },
        "data_boundary": {
            "allowed_splits": ["meta_train", "meta_validation"],
            "forbidden_splits": ["meta_test", "meta_test_ood", "negative_control"],
            "split_counts": {
                "meta_train": 60,
                "meta_validation": 20,
                "meta_test": 20,
                "meta_test_ood": 10,
                "negative_control": 10,
            },
            "meta_train_task_ids_sha256": _task_sha(["S2TR-%03d" % index for index in range(60)]),
            "meta_validation_task_ids_sha256": _task_sha(_TASKS),
            "holdout_task_ids_sha256": _task_sha(["S2HO-%03d" % index for index in range(40)]),
            "holdout_rows_used": 0,
        },
        "episode_contract": {
            "train_support": 16,
            "train_query": 32,
            "eval_K": [0, 1, 5, 10],
            "eval_draws": 10,
            "eval_query": 64,
            "seed_scopes": list(s2.PREREG_SEED_SCOPES),
            "standardization": "按 support 集 query 方差归一化；K=0/1 不做标准化",
            "train_episode_bank_sha256": "d" * 64,
        },
        "arms": [
            {"id": "FULL_MAML", "first_order": False, "config": copy.deepcopy(s2.EXPECTED_ARMS_CONFIG)},
            {"id": "FOMAML", "first_order": True, "config": copy.deepcopy(s2.EXPECTED_ARMS_CONFIG)},
        ],
        "training_budget": copy.deepcopy(s2.PREREG_TRAINING_BUDGET),
        "evaluation_grid": copy.deepcopy(s2.PREREG_EVALUATION_GRID),
        "endpoints": copy.deepcopy(s2.PREREG_ENDPOINTS_TEMPLATE),
        "comparison": copy.deepcopy(s2.PREREG_COMPARISON),
        "statistical_plan": copy.deepcopy(s2.PREREG_STATISTICAL_PLAN_TEMPLATE),
        "fd_gate": {
            "mode": "full",
            "max_relative_error": 1e-6,
            "coordinates": 32,
            "epsilon": "相对步长 = 1e-6 * max(1, |theta_j|)",
            "denominator": "max(|numeric|, |analytic|, 1e-12)",
            "fail_closed": True,
            "pilot_artifacts": copy.deepcopy(pilot),
        },
        "determinism": copy.deepcopy(s2.PREREG_DETERMINISM),
        "resource_limits": copy.deepcopy(s2.PREREG_RESOURCE_LIMITS),
        "failure_rules": list(s2.PREREG_FAILURE_RULES),
        "stopping_rules": list(s2.PREREG_STOPPING_RULES),
        "code_sha": "e" * 64,
        "physical_call_count": 0,
    }


def _finalize_prereg(raw):
    raw = copy.deepcopy(raw)
    # 顺序必须与 A1 契约一致：先 analysis_plan_digest（被 id/digest 覆盖），再 prereg_id，最后 prereg_digest。
    raw["analysis_plan_digest"] = s2.compute_analysis_plan_digest(raw)
    raw["prereg_id"] = s2.compute_prereg_id(raw)
    raw["prereg_digest"] = s2.compute_prereg_digest(raw)
    return raw


def _write_prereg(root: Path, raw) -> Path:
    path = root / "s2_preregistration.json"
    path.write_text(s2._canonical_json_text(raw) + "\n", encoding="utf-8", newline="\n")
    return path


def _prereg_variant(name, mutate=None, *, pilot_kwargs=None, finalized_tamper=None):
    root = _TMP_ROOT / name
    root.mkdir(parents=True, exist_ok=True)
    raw = _prereg_raw(root, pilot=_make_pilot_files(root, **(pilot_kwargs or {})))
    if mutate is not None:
        mutate(raw)
    raw = _finalize_prereg(raw)
    if finalized_tamper is not None:
        finalized_tamper(raw)
    path = _write_prereg(root, raw)
    return path, root, raw


def _base_prereg():
    if "prereg" not in _BASE:
        root = _BASE_ROOT
        root.mkdir(parents=True, exist_ok=True)
        raw = _prereg_raw(root)
        raw = _finalize_prereg(raw)
        path = _write_prereg(root, raw)
        _BASE["prereg"] = (path, raw)
    return _BASE["prereg"]


def _base_prereg_object():
    path, raw = _base_prereg()
    return s2.load_s2_prereg(
        path,
        repo_root=_BASE_ROOT,
        verify_frozen_package=False,
        verify_pilot_artifacts=True,
        verify_code_sha=False,
    )


def _load_prereg(path, root, **overrides):
    options = dict(
        repo_root=root,
        verify_frozen_package=False,
        verify_pilot_artifacts=True,
        verify_code_sha=False,
    )
    options.update(overrides)
    return s2.load_s2_prereg(path, **options)


def _train_rows(run_id=_RUN_ID, steps=200, seeds=(0, 1, 2)):
    rows = []
    for arm in s2.EXPECTED_ARMS:
        for seed in seeds:
            for step in range(steps):
                rows.append(
                    {
                        "record_type": "train",
                        "run_id": run_id,
                        "arm": arm,
                        "meta_seed": int(seed),
                        "outer_step": step,
                        "train_loss": 0.5 * math.exp(-step / 50.0) + 0.05 + 0.001 * int(seed),
                        "grad_norm": 0.01 + 0.0001 * step,
                        "inner_loss_first": 0.8,
                        "inner_loss_last": 0.1,
                        "wall_s": 0.001,
                        "peak_memory_mb": 100.0 + int(seed),
                        "status": "OK",
                    }
                )
    return rows


def _eval_rows(run_id=_RUN_ID, tasks=_TASKS, draws=10, seeds=(0, 1, 2), k_values=(0, 1, 5, 10)):
    rows = []
    for arm in s2.EXPECTED_ARMS:
        base = 0.90 if arm == "FULL_MAML" else 1.00
        for seed in seeds:
            for task_index, task_id in enumerate(sorted(tasks)):
                for k_value in k_values:
                    for draw in range(draws):
                        if k_value == 0:
                            value = 2.0 + 0.01 * task_index + 1e-6 * draw
                        elif k_value == 1:
                            value = 1.5 + 0.01 * task_index + 1e-6 * draw
                        elif k_value == 5:
                            value = base + 0.01 * task_index + 1e-6 * draw
                        else:
                            value = base + 0.10 + 0.01 * task_index + 1e-6 * draw
                        standardized = None if k_value <= 1 else value / 2.0
                        rows.append(
                            {
                                "record_type": "eval",
                                "run_id": run_id,
                                "arm": arm,
                                "meta_seed": int(seed),
                                "task_id": task_id,
                                "split": "meta_validation",
                                "K": int(k_value),
                                "draw": draw,
                                "query_rmse_raw": value,
                                "query_rmse_standardized": standardized,
                                "query_mae_raw": value * 0.8,
                                "support_size": int(k_value),
                                "query_size": 64,
                                "adaptation_inner_steps": int(k_value),
                                "wall_s": 0.002,
                                "status": "OK",
                            }
                        )
    return rows


_TRAIN_FIELDS = ("record_type",) + tuple(s2.TRAIN_REQUIRED_FIELDS)
_EVAL_FIELDS = ("record_type",) + tuple(s2.EVAL_REQUIRED_FIELDS)


def _scope_notes():
    return {
        "objective_source": "S2 合成代理任务（零物理调用）",
        "lifting_surfaces_only": "NOT_APPLICABLE（S2 无 VLM/CFD 气动求解）",
        "holdout_metrics_read": False,
        "physical_call_count": 0,
    }


def _fd_gate_payload(*, n_checked=32, max_relative_error=1e-9):
    """fd_gate.json 产物 payload（A1 契约：fd_gate_sha256 为自排除 canonical 摘要）。"""
    result = {
        "status": "PASS",
        "mode": "full",
        "tolerance": 1e-6,
        "n_checked": int(n_checked),
        "coordinates_requested": int(n_checked),
        "coordinates_available": max(int(n_checked), 64),
        "max_relative_error": float(max_relative_error),
    }
    payload = {
        "schema_version": "p4-s2-fd-gate-artifact-1",
        "mode": "full",
        "meta_seed": 0,
        "outer_step": 0,
        "batch_size": 8,
        "support_size": 16,
        "query_size": 32,
        "episode_keys_sha256": "a" * 64,
        "result": result,
        "physical_call_count": 0,
    }
    payload["fd_gate_sha256"] = s2._sha256_hex(s2._canonical_bytes(payload))
    return payload


def _fd_gate_block(payload, prereg_raw, *, override=False):
    result = payload["result"]
    return {
        "mode": "full",
        "tolerance": 1e-6,
        "coordinates": int(result["n_checked"]),
        "coordinates_requested": int(result["coordinates_requested"]),
        "coordinates_available": int(result["coordinates_available"]),
        "n_checked": int(result["n_checked"]),
        "status": "PASS",
        "max_relative_error": float(result["max_relative_error"]),
        "fd_gate_sha256": str(payload["fd_gate_sha256"]),
        "override": bool(override),
        "pilot_artifacts": copy.deepcopy(prereg_raw["fd_gate"]["pilot_artifacts"]),
    }


def _smoke_plan(overrides):
    """由 smoke_overrides 派生 SMOKE 预算/网格（与 runner resolve_budget 语义一致）。"""
    seeds = [int(seed) for seed in overrides["meta_seeds"]]
    outer_steps = int(overrides["outer_steps"])
    tasks = int(overrides["eval_tasks"])
    k_values = [int(k) for k in overrides["K"]]
    draws = int(overrides["draws"])
    budget = {
        "meta_seeds": seeds,
        "outer_steps": outer_steps,
        "train_records_expected": 2 * len(seeds) * outer_steps,
    }
    grid = {
        "meta_validation_tasks": tasks,
        "K": k_values,
        "draws": draws,
        "eval_records_expected": 2 * len(seeds) * tasks * len(k_values) * draws,
    }
    return budget, grid


def _run_config(
    run_id,
    prereg_raw,
    *,
    train_rows,
    eval_rows,
    run_mode="FORMAL",
    smoke_overrides=None,
    fd_payload,
):
    boundary = prereg_raw["data_boundary"]
    if run_mode == "SMOKE":
        overrides = dict(smoke_overrides)
        budget, grid = _smoke_plan(overrides)
        seeds = list(budget["meta_seeds"])
        outer_steps = int(budget["outer_steps"])
        batch_size = int(overrides.get("batch_size", 8))
        support_size = int(overrides.get("support_size", 16))
        query_size = int(overrides.get("query_size", 32))
        bank_sha = "b" * 64
        fd_block = _fd_gate_block(fd_payload, prereg_raw, override=True)
    else:
        budget = copy.deepcopy(prereg_raw["training_budget"])
        grid = copy.deepcopy(prereg_raw["evaluation_grid"])
        seeds = [int(seed) for seed in budget["meta_seeds"]]
        outer_steps = int(budget["outer_steps"])
        batch_size = 8
        support_size = 16
        query_size = 32
        bank_sha = prereg_raw["episode_contract"]["train_episode_bank_sha256"]
        fd_block = _fd_gate_block(fd_payload, prereg_raw, override=False)
    return {
        "schema_version": s2.sp.RUN_CONFIG_SCHEMA_VERSION,
        "run_id": run_id,
        "run_mode": run_mode,
        "prereg_id": prereg_raw["prereg_id"],
        "prereg_digest": prereg_raw["prereg_digest"],
        "analysis_plan_digest": prereg_raw["analysis_plan_digest"],
        "code_sha": prereg_raw["code_sha"],
        "frozen_package": copy.deepcopy(prereg_raw["frozen_package"]),
        "data_boundary": {
            "allowed_splits": ["meta_train", "meta_validation"],
            "forbidden_splits": copy.deepcopy(boundary["forbidden_splits"]),
            "split_counts": copy.deepcopy(boundary["split_counts"]),
            "meta_train_task_ids_sha256": boundary["meta_train_task_ids_sha256"],
            "meta_validation_task_ids_sha256": boundary["meta_validation_task_ids_sha256"],
            "holdout_task_ids_sha256": boundary["holdout_task_ids_sha256"],
            "holdout_rows_used": 0,
            "holdout_metrics_read": False,
        },
        "arms": copy.deepcopy(prereg_raw["arms"]),
        "training_budget": budget,
        "evaluation_grid": grid,
        "episode_bank": {
            "sha256": bank_sha,
            "episodes": 1200 if run_mode == "FORMAL" else max(8, len(train_rows)),
            "meta_seeds": seeds,
            "outer_steps": outer_steps,
            "batch_size": batch_size,
            "support_size": support_size,
            "query_size": query_size,
        },
        "fd_gate": fd_block,
        "determinism": copy.deepcopy(prereg_raw["determinism"]),
        "record_counts": {
            "train": len(train_rows),
            "eval": len(eval_rows),
            "total": len(train_rows) + len(eval_rows),
            "train_expected": int(budget["train_records_expected"]),
            "eval_expected": int(grid["eval_records_expected"]),
            "total_expected": int(budget["train_records_expected"]) + int(grid["eval_records_expected"]),
        },
        "record_schemas": {"train": list(_TRAIN_FIELDS), "eval": list(_EVAL_FIELDS)},
        "resource_limits": copy.deepcopy(s2.sp.RUN_RESOURCE_LIMITS),
        "physical_call_count": 0,
        "evidence_scope": _EVIDENCE_SCOPE,
        "development_set": "meta_validation",
        "scope_notes": _scope_notes(),
        **({"smoke_overrides": dict(smoke_overrides)} if run_mode == "SMOKE" else {}),
    }


def _data_manifest(run_config, prereg_raw):
    boundary = prereg_raw["data_boundary"]
    frozen = prereg_raw["frozen_package"]
    return {
        "schema_version": s2.DATA_MANIFEST_SCHEMA_VERSION,
        "frozen_package": {
            "run_id": frozen["run_id"],
            "package_path": frozen["package_path"],
            "sha256sums_sha256": frozen["sha256sums_sha256"],
            "code_sha": frozen["code_sha"],
            "git_sha": frozen["git_sha"],
        },
        "split_counts": copy.deepcopy(boundary["split_counts"]),
        "meta_train_task_ids": ["S2TR-%03d" % index for index in range(60)],
        "meta_validation_task_ids": list(_TASKS),
        "holdout_task_ids_sha256": boundary["holdout_task_ids_sha256"],
        "holdout_rows_used": 0,
        "holdout_metrics_read": False,
        "episode_bank_sha256": run_config["episode_bank"]["sha256"],
        "physical_call_count": 0,
    }


def _run_summary(
    run_id,
    run_config,
    train_rows,
    eval_rows,
    *,
    config_sha,
    records_sha,
    fd_gate_sha,
    manifest_sha,
    run_mode="FORMAL",
):
    def _status_counts(rows):
        return {
            "OK": sum(1 for row in rows if row["status"] == "OK"),
            "FAILED": sum(1 for row in rows if row["status"] == "FAILED"),
        }

    seeds = [int(seed) for seed in run_config["training_budget"]["meta_seeds"]]
    per_seed = []
    per_arm = {}
    for arm in s2.EXPECTED_ARMS:
        per_arm[arm] = {
            "meta_seeds": list(seeds),
            "train_wall_seconds_per_meta_seed": {str(seed): 0.5 for seed in seeds},
            "train_wall_seconds_mean": 0.5,
            "peak_memory_mb_max": 100.0,
        }
        for seed in seeds:
            per_seed.append(
                {
                    "arm": arm,
                    "meta_seed": seed,
                    "status": "OK",
                    "training_wall_s": 0.5,
                    "peak_memory_mb": 100.0,
                }
            )
    timing = []
    return {
        "schema_version": s2.sp.RUN_SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "run_mode": run_mode,
        "status": "COMPLETED",
        "created_utc": "2026-11-06T12:30:00+00:00",
        "prereg_id": run_config["prereg_id"],
        "prereg_digest": run_config["prereg_digest"],
        "code_sha": run_config["code_sha"],
        "record_counts": {
            "train": len(train_rows),
            "eval": len(eval_rows),
            "total": len(train_rows) + len(eval_rows),
        },
        "status_counts": {"train": _status_counts(train_rows), "eval": _status_counts(eval_rows)},
        "failures": [],
        "resource_stop": None,
        "episode_bank_sha256": run_config["episode_bank"]["sha256"],
        "run_config_sha256": config_sha,
        "run_records_sha256": records_sha,
        "run_records_core_sha256": "c" * 64,
        "fd_gate_sha256": fd_gate_sha,
        "data_manifest_sha256": manifest_sha,
        "outer_step_timing": timing,
        "per_arm_seed": {arm: list(seeds) for arm in s2.EXPECTED_ARMS},
        "fd_pilot_artifacts": copy.deepcopy(run_config["fd_gate"]["pilot_artifacts"]),
        "scope_notes": copy.deepcopy(run_config["scope_notes"]),
        "resources": {
            "per_seed": per_seed,
            "per_arm": per_arm,
            "train_wall_seconds_ratio": 1.0,
            "run_wall_s": 2.0,
            "resource_limits": copy.deepcopy(s2.sp.RUN_RESOURCE_LIMITS),
            "auxiliary_compute": {
                "outer_step_timing_measurements": len(timing),
                "physical_call_count": 0,
                "note": "测试合成摘要（零物理）",
            },
        },
        "resource_limits": copy.deepcopy(s2.sp.RUN_RESOURCE_LIMITS),
        "torch_threads": 1,
        "environment": {
            "python": "3.11.17",
            "numpy": "2.4.6",
            "torch": "2.8.0+cpu",
            "platform": "Windows-11-test",
        },
        "physical_call_count": 0,
        "evidence_scope": _EVIDENCE_SCOPE,
        "development_set": "meta_validation",
        "smoke": run_mode == "SMOKE",
    }


def _write_run(
    run_dir,
    prereg_raw,
    *,
    train_rows=None,
    eval_rows=None,
    summary=True,
    config_mutate=None,
    summary_mutate=None,
    run_mode="FORMAL",
    smoke_overrides=None,
):
    run_dir.mkdir(parents=True, exist_ok=True)
    train_rows = _train_rows() if train_rows is None else list(train_rows)
    eval_rows = _eval_rows() if eval_rows is None else list(eval_rows)
    _write_records(run_dir, train_rows + eval_rows)
    records_sha = s2._sha256_file(run_dir / "run_records.jsonl")
    if run_mode == "SMOKE":
        fd_n = int((smoke_overrides or {}).get("fd_coordinates", 8))
    else:
        fd_n = 32
    fd_payload = _fd_gate_payload(n_checked=fd_n)
    (run_dir / "fd_gate.json").write_text(
        s2._canonical_json_text(fd_payload) + "\n", encoding="utf-8", newline="\n"
    )
    fd_gate_sha = s2._sha256_file(run_dir / "fd_gate.json")
    config = _run_config(
        _RUN_ID,
        prereg_raw,
        train_rows=train_rows,
        eval_rows=eval_rows,
        run_mode=run_mode,
        smoke_overrides=smoke_overrides,
        fd_payload=fd_payload,
    )
    if config_mutate is not None:
        config_mutate(config)
    _write_json(run_dir / "run_config.json", config)
    config_sha = s2._sha256_file(run_dir / "run_config.json")
    manifest = _data_manifest(config, prereg_raw)
    _write_json(run_dir / "data_manifest.json", manifest)
    manifest_sha = s2._sha256_file(run_dir / "data_manifest.json")
    if summary:
        payload = _run_summary(
            _RUN_ID,
            config,
            train_rows,
            eval_rows,
            config_sha=config_sha,
            records_sha=records_sha,
            fd_gate_sha=fd_gate_sha,
            manifest_sha=manifest_sha,
            run_mode=run_mode,
        )
        if summary_mutate is not None:
            summary_mutate(payload)
        _write_json(run_dir / "run_summary.json", payload)
    return run_dir


def _base_run():
    if "run" not in _BASE:
        _prereg_path, prereg_raw = _base_prereg()
        run_dir = _TMP_ROOT / "base-run"
        _write_run(run_dir, prereg_raw)
        _BASE["run"] = run_dir
    return _BASE["run"]


_SMOKE_OVERRIDES = {
    "outer_steps": 2,
    "meta_seeds": [0],
    "K": [0, 1, 5, 10],
    "draws": 1,
    "eval_tasks": 20,
    "fd_coordinates": 8,
}


def _base_smoke_run():
    if "smoke_run" not in _BASE:
        _prereg_path, prereg_raw = _base_prereg()
        run_dir = _TMP_ROOT / "base-smoke-run"
        _write_run(
            run_dir,
            prereg_raw,
            train_rows=_train_rows(steps=2, seeds=(0,)),
            eval_rows=_eval_rows(draws=1, seeds=(0,)),
            run_mode="SMOKE",
            smoke_overrides=_SMOKE_OVERRIDES,
        )
        _BASE["smoke_run"] = run_dir
    return _BASE["smoke_run"]


def _copy_run(name):
    destination = _TMP_ROOT / name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(_base_run(), destination)
    return destination


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_json(run_dir: Path, filename: str, mutate) -> None:
    path = run_dir / filename
    payload = _read_json(path)
    mutate(payload)
    _write_json(path, payload)


def _read_records(run_dir: Path):
    path = run_dir / "run_records.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_records(run_dir: Path, records) -> None:
    path = run_dir / "run_records.jsonl"
    path.write_text("\n".join(s2._canonical_json_text(row) for row in records) + "\n", encoding="utf-8", newline="\n")


def _patch_records(run_dir: Path, mutate) -> None:
    records = _read_records(run_dir)
    records = mutate(records)
    _write_records(run_dir, records)


def _load_run(run_dir, *, require_summary=True, allow_incomplete_run=False, prereg=None):
    prereg = _base_prereg_object() if prereg is None else prereg
    return s2.load_s2_run(
        run_dir,
        prereg,
        repo_root=_BASE_ROOT,
        require_summary=require_summary,
        allow_incomplete_run=allow_incomplete_run,
    )


class _S2TestBase(unittest.TestCase):
    def assert_error(self, code, function, *args, **kwargs):
        with self.assertRaises(s2.S2AnalysisError) as context:
            function(*args, **kwargs)
        self.assertEqual(context.exception.code, code)
        return context.exception


class PreregValidationTests(_S2TestBase):
    """冻结 prereg 强校验：正例 + 负控（占位/摘要/端点/Holm 族/scope/physical/arm/冻结包/pilot）。"""

    def test_valid_prereg_passes(self):
        path, root, raw = _prereg_variant("prereg-valid")
        prereg = _load_prereg(path, root)
        self.assertEqual(prereg.prereg_id, raw["prereg_id"])
        self.assertEqual(prereg.evidence_scope, _EVIDENCE_SCOPE)
        self.assertEqual(prereg.n_tasks, 20)
        self.assertEqual(list(prereg.meta_seeds), [0, 1, 2])
        verified = s2.verify_s2_preregistration(
            path,
            repo_root=root,
            verify_frozen_package=False,
            verify_pilot_artifacts=True,
            verify_code_sha=False,
        )
        self.assertEqual(verified["status"], "PASS")
        self.assertEqual(verified["prereg_digest"], raw["prereg_digest"])

    def test_schema_version_mismatch_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-schema", lambda raw: raw.__setitem__("schema_version", "p4ra-s2-prereg-v0")
        )
        self.assert_error(s2.ERR_PREREG_SCHEMA, _load_prereg, path, root)

    def test_missing_required_field_rejected(self):
        path, root, _raw = _prereg_variant("prereg-missing", lambda raw: raw.pop("determinism"))
        # 实现按“顶层字段精确集合”在 schema 阶段 fail-closed（缺失/多余同一错误码）。
        self.assert_error(s2.ERR_PREREG_SCHEMA, _load_prereg, path, root)

    def test_unknown_top_level_field_rejected(self):
        path, root, _raw = _prereg_variant("prereg-unknown", lambda raw: raw.__setitem__("unexpected_field", 1))
        self.assert_error(s2.ERR_PREREG_SCHEMA, _load_prereg, path, root)

    def test_placeholder_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-placeholder", lambda raw: raw["upstream"].__setitem__("decision", "TBD")
        )
        self.assert_error(s2.ERR_PREREG_PLACEHOLDER, _load_prereg, path, root)

    def test_digest_mismatch_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-digest",
            finalized_tamper=lambda raw: raw.__setitem__("created_utc", "2026-11-07T00:00:00Z"),
        )
        self.assert_error(s2.ERR_PREREG_DIGEST, _load_prereg, path, root)

    def test_holm_family_split_rejected(self):
        def mutate(raw):
            plan = raw["statistical_plan"]["multiple_comparison"]
            plan["family_size"] = 1
            plan["members"] = [plan["members"][0]]

        path, root, _raw = _prereg_variant("prereg-holm", mutate)
        self.assert_error(s2.ERR_PREREG_HOLM, _load_prereg, path, root)

    def test_holm_members_must_be_exactly_two_endpoints(self):
        def mutate(raw):
            raw["statistical_plan"]["multiple_comparison"]["members"].append(
                {"comparison": "C1", "endpoint": "post_adaptation_rmse_raw_k0"}
            )

        path, root, _raw = _prereg_variant("prereg-holm-members", mutate)
        self.assert_error(s2.ERR_PREREG_HOLM, _load_prereg, path, root)

    def test_primary_endpoint_mismatch_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-endpoint",
            lambda raw: raw["endpoints"]["primary"].__setitem__("id", "post_adaptation_rmse_raw_k10"),
        )
        self.assert_error(s2.ERR_PREREG_ENDPOINT, _load_prereg, path, root)

    def test_evidence_scope_violation_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-scope",
            lambda raw: raw["statistical_plan"].__setitem__("evidence_scope", "CONFIRMATORY_GENERALIZATION"),
        )
        self.assert_error(s2.ERR_PREREG_SCOPE, _load_prereg, path, root)

    def test_physical_call_count_nonzero_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-physical", lambda raw: raw.__setitem__("physical_call_count", 1)
        )
        self.assert_error(s2.ERR_PREREG_PHYSICAL, _load_prereg, path, root)

    def test_arm_parity_violation_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-arm", lambda raw: raw["arms"][1]["config"].__setitem__("inner_lr", 0.02)
        )
        self.assert_error(s2.ERR_PREREG_ARM, _load_prereg, path, root)

    def test_frozen_package_identity_mismatch_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-frozen", lambda raw: raw["frozen_package"].__setitem__("git_sha", "0" * 64)
        )
        self.assert_error(
            s2.ERR_PREREG_FROZEN,
            s2.load_s2_prereg,
            path,
            repo_root=root,
            verify_frozen_package=True,
            verify_pilot_artifacts=False,
            verify_code_sha=False,
        )

    def test_pilot_artifact_sha_mismatch_rejected(self):
        path, root, raw = _prereg_variant("prereg-pilot-sha")
        pilot_path = root / raw["fd_gate"]["pilot_artifacts"]["micro"]["path"]
        pilot_path.write_text('{"status": "PASS", "max_relative_error": 1e-9, "coordinates": 32}\n', encoding="utf-8")
        self.assert_error(s2.ERR_PREREG_PILOT, _load_prereg, path, root)

    def test_pilot_artifact_missing_rejected(self):
        path, root, raw = _prereg_variant("prereg-pilot-missing")
        (root / raw["fd_gate"]["pilot_artifacts"]["full_size"]["path"]).unlink()
        self.assert_error(s2.ERR_PREREG_PILOT, _load_prereg, path, root)

    def test_determinism_reruns_mismatch_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-determinism", lambda raw: raw["determinism"].__setitem__("reruns", 3)
        )
        self.assert_error(s2.ERR_PREREG_FIELD, _load_prereg, path, root)

    def test_failure_rules_tampered_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-rules", lambda raw: raw["failure_rules"].append("extra_rule_not_in_contract")
        )
        self.assert_error(s2.ERR_PREREG_FIELD, _load_prereg, path, root)

    def test_data_boundary_holdout_rows_nonzero_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-boundary", lambda raw: raw["data_boundary"].__setitem__("holdout_rows_used", 3)
        )
        self.assert_error(s2.ERR_DATA_BOUNDARY, _load_prereg, path, root)


    def test_resource_limits_missing_rejected(self):
        # 缺失必填键由 schema 精确集合先拦截（S2_ANALYSIS_PREREG_SCHEMA）；不属于 resource_limits 数值校验。
        path, root, _raw = _prereg_variant("prereg-resource-missing", lambda raw: raw.pop("resource_limits"))
        self.assert_error(s2.ERR_PREREG_SCHEMA, _load_prereg, path, root)

    def test_resource_limits_value_mismatch_rejected(self):
        def mutate(raw):
            raw["resource_limits"]["per_seed_train_wall_s"] = 1201

        path, root, _raw = _prereg_variant("prereg-resource-mismatch", mutate)
        self.assert_error(s2.ERR_PREREG_RESOURCE_LIMITS, _load_prereg, path, root)

    def test_resource_limits_extra_key_rejected(self):
        def mutate(raw):
            raw["resource_limits"]["gpu_memory_mb"] = 1

        path, root, _raw = _prereg_variant("prereg-resource-extra", mutate)
        self.assert_error(s2.ERR_PREREG_RESOURCE_LIMITS, _load_prereg, path, root)

    def test_frozen_package_task_family_version_mismatch_rejected(self):
        path, root, _raw = _prereg_variant(
            "prereg-frozen-task-family",
            lambda raw: raw["frozen_package"].__setitem__("task_family_version", "p4ra-family-v2"),
        )
        self.assert_error(s2.ERR_PREREG_FROZEN, _load_prereg, path, root)


class RunValidationTests(_S2TestBase):
    """正式 run 合同与记录校验：正例 + 负控（字段/摘要/边界/记录/覆盖/summary/FD 证据）。"""

    def test_full_run_loads_and_counts(self):
        run = _load_run(_base_run())
        self.assertEqual(run.counts["train"], 1200)
        self.assertEqual(run.counts["eval"], 4800)
        self.assertTrue(run.validation["coverage"]["complete"])
        self.assertEqual(run.validation["data_boundary"]["holdout_rows_used"], 0)
        self.assertFalse(run.validation["data_boundary"]["holdout_metrics_read"])
        self.assertEqual(len(run.validation["source_files"]), 3)
        self.assertEqual(run.validation["fd_gate_evidence"]["micro"]["status"], "PASS")
        self.assertTrue(run.validation["fd_gate_evidence"]["micro"]["sha256_verified"])

    def test_config_missing_required_field_rejected(self):
        run_dir = _copy_run("run-config-missing")
        _patch_json(run_dir, "run_config.json", lambda cfg: cfg.pop("run_mode"))
        self.assert_error(s2.ERR_RUN_SCHEMA, _load_run, run_dir)

    def test_config_record_counts_mismatch_rejected(self):
        run_dir = _copy_run("run-config-counts")
        _patch_json(run_dir, "run_config.json", lambda cfg: cfg["record_counts"].update({"eval": 4000}))
        self.assert_error(s2.ERR_RUN_CONFIG, _load_run, run_dir)

    def test_config_prereg_digest_mismatch_rejected(self):
        run_dir = _copy_run("run-config-digest")
        _patch_json(run_dir, "run_config.json", lambda cfg: cfg.__setitem__("prereg_digest", "0" * 64))
        self.assert_error(s2.ERR_RUN_CONFIG, _load_run, run_dir)

    def test_config_physical_count_nonzero_rejected(self):
        run_dir = _copy_run("run-config-physical")
        _patch_json(run_dir, "run_config.json", lambda cfg: cfg.__setitem__("physical_call_count", 2))
        self.assert_error(s2.ERR_RUN_CONFIG, _load_run, run_dir)

    def test_config_holdout_metrics_read_rejected(self):
        run_dir = _copy_run("run-config-holdout")
        _patch_json(run_dir, "run_config.json", lambda cfg: cfg["data_boundary"].__setitem__("holdout_metrics_read", True))
        self.assert_error(s2.ERR_DATA_BOUNDARY, _load_run, run_dir)

    def test_config_episode_bank_sha_mismatch_rejected(self):
        run_dir = _copy_run("run-config-bank")
        _patch_json(run_dir, "run_config.json", lambda cfg: cfg["episode_bank"].__setitem__("sha256", "f" * 64))
        self.assert_error(s2.ERR_RUN_CONFIG, _load_run, run_dir)

    def test_record_line_not_canonical_rejected(self):
        run_dir = _copy_run("run-record-noncanonical")
        path = run_dir / "run_records.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        lines[0] = json.dumps(first, sort_keys=True)  # 默认 separators 含空格 -> 非 canonical
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        self.assert_error(s2.ERR_RECORD_SCHEMA, _load_run, run_dir)

    def test_train_record_extra_field_rejected(self):
        run_dir = _copy_run("run-record-extra")
        _patch_records(run_dir, lambda records: records[:1] + [{**records[0], "unexpected": 1}] + records[2:])
        self.assert_error(s2.ERR_RECORD_SCHEMA, _load_run, run_dir)

    def test_eval_record_split_holdout_rejected(self):
        run_dir = _copy_run("run-record-split")

        def mutate(records):
            for record in records:
                if record["record_type"] == "eval":
                    record["split"] = "meta_test"
                    break
            return records

        _patch_records(run_dir, mutate)
        self.assert_error(s2.ERR_DATA_BOUNDARY, _load_run, run_dir)

    def test_eval_record_k0_support_nonzero_rejected(self):
        run_dir = _copy_run("run-record-k0")

        def mutate(records):
            for record in records:
                if record["record_type"] == "eval" and record["K"] == 0:
                    record["support_size"] = 1
                    break
            return records

        _patch_records(run_dir, mutate)
        self.assert_error(s2.ERR_RECORD_VALUE, _load_run, run_dir)

    def test_eval_record_k1_standardized_nonnull_rejected(self):
        run_dir = _copy_run("run-record-std")

        def mutate(records):
            for record in records:
                if record["record_type"] == "eval" and record["K"] == 1:
                    record["query_rmse_standardized"] = 0.5
                    break
            return records

        _patch_records(run_dir, mutate)
        self.assert_error(s2.ERR_RECORD_VALUE, _load_run, run_dir)

    def test_eval_record_duplicate_rejected(self):
        run_dir = _copy_run("run-record-duplicate")

        def mutate(records):
            eval_indexes = [index for index, record in enumerate(records) if record["record_type"] == "eval"]
            records[eval_indexes[-1]] = copy.deepcopy(records[eval_indexes[0]])
            return records

        _patch_records(run_dir, mutate)
        self.assert_error(s2.ERR_RECORD_DUPLICATE, _load_run, run_dir)

    def test_incomplete_grid_strict_rejected_and_allowed_with_disclosure(self):
        run_dir = _copy_run("run-incomplete")
        _patch_records(
            run_dir,
            lambda records: [
                record
                for record in records
                if not (
                    record["record_type"] == "eval"
                    and record["arm"] == "FULL_MAML"
                    and record["meta_seed"] == 0
                    and record["task_id"] == _TASKS[0]
                    and record["K"] == 5
                    and record["draw"] >= 5
                )
            ],
        )
        (run_dir / "run_summary.json").unlink()
        with self.assertRaises(s2.S2AnalysisError):
            _load_run(run_dir, require_summary=False, allow_incomplete_run=False)
        run = _load_run(run_dir, require_summary=False, allow_incomplete_run=True)
        self.assertFalse(run.validation["coverage"]["complete"])
        self.assertEqual(run.counts["eval"], 4795)

    def test_summary_missing_rejected(self):
        run_dir = _copy_run("run-summary-missing")
        (run_dir / "run_summary.json").unlink()
        self.assert_error(s2.ERR_INPUT, _load_run, run_dir)

    def test_summary_status_counts_mismatch_rejected(self):
        run_dir = _copy_run("run-summary-counts")
        _patch_json(
            run_dir,
            "run_summary.json",
            lambda summary: summary["status_counts"]["train"].__setitem__("OK", 1199),
        )
        self.assert_error(s2.ERR_RUN_CONFIG, _load_run, run_dir)

    def test_summary_episode_bank_sha_mismatch_rejected(self):
        run_dir = _copy_run("run-summary-bank")
        _patch_json(
            run_dir,
            "run_summary.json",
            lambda summary: summary.__setitem__("episode_bank_sha256", "f" * 64),
        )
        self.assert_error(s2.ERR_RUN_CONFIG, _load_run, run_dir)


class FdEvidenceTests(_S2TestBase):
    """FD pilot 证据：run 加载阶段 raw sha 复算 + 状态/误差/坐标 fail-closed。"""

    def _prereg_and_run(self, name, **pilot_kwargs):
        path, root, raw = _prereg_variant(name, pilot_kwargs=pilot_kwargs)
        prereg = _load_prereg(path, root, verify_pilot_artifacts=False)
        run_dir = _TMP_ROOT / (name + "-run")
        _write_run(run_dir, raw)
        return prereg, root, run_dir

    def test_fd_fail_status_rejected(self):
        prereg, root, run_dir = self._prereg_and_run("fd-fail", status="FAIL")
        self.assert_error(
            s2.ERR_FD_GATE,
            s2.load_s2_run,
            run_dir,
            prereg,
            repo_root=root,
            require_summary=True,
        )

    def test_fd_relative_error_too_large_rejected(self):
        prereg, root, run_dir = self._prereg_and_run("fd-error", max_relative_error=1e-4)
        self.assert_error(
            s2.ERR_FD_GATE,
            s2.load_s2_run,
            run_dir,
            prereg,
            repo_root=root,
            require_summary=True,
        )

    def test_fd_coordinates_mismatch_rejected(self):
        prereg, root, run_dir = self._prereg_and_run("fd-coordinates", coordinates=16)
        self.assert_error(
            s2.ERR_FD_GATE,
            s2.load_s2_run,
            run_dir,
            prereg,
            repo_root=root,
            require_summary=True,
        )


def _copy_smoke_run(name):
    destination = _TMP_ROOT / name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(_base_smoke_run(), destination)
    return destination


class SmokeRunSemanticsTests(_S2TestBase):
    """SMOKE 模式合同（Lead rev20）：预算/网格由 smoke_overrides 派生、显式披露、不得冒充 FORMAL。"""

    def test_smoke_run_loads_with_derived_grid(self):
        run = _load_run(_base_smoke_run())
        self.assertEqual(run.run_config["run_mode"], "SMOKE")
        self.assertEqual(run.counts["train"], 4)
        self.assertEqual(run.counts["eval"], 160)
        self.assertEqual(run.counts["total"], 164)
        self.assertEqual(run.counts["expected_train"], 4)
        self.assertEqual(run.counts["expected_eval"], 160)
        self.assertEqual(run.grid["run_mode"], "SMOKE")
        self.assertEqual(run.grid["meta_seeds"], (0,))
        self.assertEqual(run.grid["outer_steps"], 2)
        self.assertEqual(run.grid["eval_tasks"], 20)
        self.assertEqual(run.grid["draws"], 1)
        self.assertTrue(run.validation["coverage"]["complete"])
        smoke_checks = [item for item in run.checks if item.get("check") == "smoke_budget"]
        self.assertEqual(len(smoke_checks), 1)
        self.assertEqual(smoke_checks[0]["status"], "DISCLOSED")

    def test_smoke_analysis_marks_run_mode_and_disclosures(self):
        prereg_path, _raw = _base_prereg()
        output_dir = _TMP_ROOT / "smoke-e2e-out"
        result = s2.analyze_s2_run(
            prereg_path=prereg_path,
            run_dir=_base_smoke_run(),
            output_dir=output_dir,
            repo_root=_BASE_ROOT,
            verify_frozen_package=False,
            verify_code_sha=False,
            allow_incomplete_run=True,
            generate_figures=False,
        )
        self.assertEqual(result["status"], "PASS")
        aggregate = _read_json(output_dir / "aggregate.json")
        self.assertEqual(aggregate["run_mode"], "SMOKE")
        self.assertTrue(aggregate["smoke"])
        disclosed = {item["check"] for item in aggregate["disclosed_checks"]}
        self.assertIn("smoke_budget", disclosed)
        self.assertEqual(aggregate["run_grid"]["outer_steps"], 2)
        self.assertEqual(aggregate["run_grid"]["eval_tasks"], 20)
        self.assertEqual(aggregate["run_grid"]["meta_seeds"], [0])
        figure_status = _read_json(output_dir / "figure_status.json")
        for payload in figure_status["figures"].values():
            self.assertNotEqual(payload["status"], "RENDERED")
            self.assertIsNone(payload["path"])

    def test_smoke_missing_overrides_rejected(self):
        run_dir = _copy_smoke_run("smoke-no-overrides")
        _patch_json(run_dir, "run_config.json", lambda config: config.pop("smoke_overrides"))
        self.assert_error(s2.ERR_RUN_SCHEMA, _load_run, run_dir)

    def test_smoke_summary_run_mode_mismatch_rejected(self):
        run_dir = _copy_smoke_run("smoke-summary-mode")
        _patch_json(run_dir, "run_summary.json", lambda summary: summary.__setitem__("run_mode", "FORMAL"))
        self.assert_error(s2.ERR_RUN_CONFIG, _load_run, run_dir)

    def test_smoke_budget_inconsistent_rejected(self):
        run_dir = _copy_smoke_run("smoke-budget")
        _patch_json(
            run_dir,
            "run_config.json",
            lambda config: config["training_budget"].__setitem__("outer_steps", 3),
        )
        self.assert_error(s2.ERR_RUN_CONFIG, _load_run, run_dir)

    def test_smoke_fd_override_false_rejected(self):
        run_dir = _copy_smoke_run("smoke-fd-override")
        _patch_json(run_dir, "run_config.json", lambda config: config["fd_gate"].__setitem__("override", False))
        self.assert_error(s2.ERR_FD_GATE, _load_run, run_dir)

    def test_formal_fd_override_true_rejected(self):
        run_dir = _copy_run("formal-fd-override")
        _patch_json(run_dir, "run_config.json", lambda config: config["fd_gate"].__setitem__("override", True))
        self.assert_error(s2.ERR_FD_GATE, _load_run, run_dir)


class RunArtifactIntegrityTests(_S2TestBase):
    """A5 M02 负控：run 目录 fd_gate.json / data_manifest.json 被篡改或缺失必须 fail-closed。"""

    def test_fd_gate_result_status_tamper_rejected(self):
        run_dir = _copy_run("artifact-fd-status")
        _patch_json(run_dir, "fd_gate.json", lambda payload: payload["result"].__setitem__("status", "FAIL"))
        self.assert_error(s2.ERR_FD_GATE, _load_run, run_dir)

    def test_fd_gate_config_digest_tamper_rejected(self):
        run_dir = _copy_run("artifact-fd-digest")
        _patch_json(
            run_dir,
            "run_config.json",
            lambda config: config["fd_gate"].__setitem__("fd_gate_sha256", "e" * 64),
        )
        self.assert_error(s2.ERR_FD_GATE, _load_run, run_dir)

    def test_fd_gate_artifact_missing_rejected(self):
        run_dir = _copy_run("artifact-fd-missing")
        (run_dir / "fd_gate.json").unlink()
        self.assert_error(s2.ERR_FD_GATE, _load_run, run_dir)

    def test_data_manifest_holdout_rows_tamper_rejected(self):
        run_dir = _copy_run("artifact-manifest-holdout")
        _patch_json(run_dir, "data_manifest.json", lambda payload: payload.__setitem__("holdout_rows_used", 1))
        self.assert_error(s2.ERR_DATA_BOUNDARY, _load_run, run_dir)

    def test_data_manifest_task_count_tamper_rejected(self):
        run_dir = _copy_run("artifact-manifest-tasks")
        _patch_json(
            run_dir,
            "data_manifest.json",
            lambda payload: payload.__setitem__("meta_validation_task_ids", payload["meta_validation_task_ids"][:-1]),
        )
        self.assert_error(s2.ERR_DATA_BOUNDARY, _load_run, run_dir)

    def test_data_manifest_raw_bytes_tamper_rejected(self):
        run_dir = _copy_run("artifact-manifest-sha")
        path = run_dir / "data_manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
        self.assert_error(s2.ERR_DATA_BOUNDARY, _load_run, run_dir)

    def test_data_manifest_missing_rejected(self):
        run_dir = _copy_run("artifact-manifest-missing")
        (run_dir / "data_manifest.json").unlink()
        self.assert_error(s2.ERR_DATA_BOUNDARY, _load_run, run_dir)


class NegativeControlDerivationTests(_S2TestBase):
    """S2C-08：负控状态必须由实际证据派生（PASS/DISCLOSED/FAIL），不得硬编码 PASS。"""

    def _context(self):
        run = _load_run(_base_run())
        prereg = _base_prereg_object()
        checks: list = []
        core = s2._build_analysis_core(run, prereg, checks=checks)
        stats = s2._build_statistics(core, prereg, checks=checks)
        rows = {row["check_id"]: row for row in s2._build_negative_control_rows(run, prereg, core, stats)}
        return run, prereg, core, stats, rows

    def test_nc09_pass_when_evidence_and_artifact_pass(self):
        _run, _prereg, _core, _stats, rows = self._context()
        self.assertEqual(rows["NC-09"]["status"], "PASS")
        self.assertIn("micro:PASS", rows["NC-09"]["observed"])
        self.assertIn("artifact=PASS", rows["NC-09"]["observed"])

    def test_nc09_disclosed_when_only_digests_verifiable(self):
        run, prereg, core, stats, _rows = self._context()
        stripped = dataclasses.replace(
            run,
            validation={**run.validation, "fd_gate_evidence": {}},
            checks=[item for item in run.checks if item.get("check") != "fd_gate_artifact"],
        )
        rows = {row["check_id"]: row for row in s2._build_negative_control_rows(stripped, prereg, core, stats)}
        self.assertEqual(rows["NC-09"]["status"], "DISCLOSED")

    def test_nc09_fail_closed_when_evidence_fail(self):
        run, prereg, core, stats, _rows = self._context()
        broken = {
            name: {**item, "status": "FAIL"}
            for name, item in run.validation["fd_gate_evidence"].items()
        }
        tampered = dataclasses.replace(run, validation={**run.validation, "fd_gate_evidence": broken})
        with self.assertRaises(s2.S2AnalysisError) as context:
            s2._build_negative_control_rows(tampered, prereg, core, stats)
        self.assertEqual(context.exception.code, s2.ERR_INPUT)

    def test_nc03_disclosed_when_prereg_digest_check_unavailable(self):
        run, prereg, core, stats, _rows = self._context()
        stripped = dataclasses.replace(
            prereg,
            checks=[item for item in prereg.checks if item.get("check") != "prereg_digest"],
        )
        rows = {row["check_id"]: row for row in s2._build_negative_control_rows(run, stripped, core, stats)}
        self.assertEqual(rows["NC-03"]["status"], "DISCLOSED")

    def test_nc04_disclosed_when_frozen_package_check_skipped(self):
        run, prereg, core, stats, _rows = self._context()
        stripped = dataclasses.replace(prereg, checks=[])
        run_stripped = dataclasses.replace(
            run,
            checks=[item for item in run.checks if item.get("check") != "frozen_package_sha256sums"],
        )
        rows = {row["check_id"]: row for row in s2._build_negative_control_rows(run_stripped, stripped, core, stats)}
        self.assertEqual(rows["NC-04"]["status"], "DISCLOSED")


class StatisticsTests(unittest.TestCase):
    """统计实现边界：Wilcoxon 精确/近似、bootstrap 可复现、Holm、决策四类。"""

    def test_wilcoxon_exact_small_sample(self):
        result = s2.wilcoxon_signed_rank_two_sided([1, 2, 3, 4, 5])
        self.assertEqual(result["n_pairs"], 5)
        self.assertEqual(result["n_nonzero"], 5)
        self.assertAlmostEqual(result["p_value"], 0.0625, places=12)
        self.assertAlmostEqual(result["statistic"], 0.0, places=12)
        self.assertAlmostEqual(result["w_plus"], 15.0, places=12)

    def test_wilcoxon_zeros_removed(self):
        result = s2.wilcoxon_signed_rank_two_sided([1, 0, -1])
        self.assertEqual(result["n_nonzero"], 2)
        self.assertAlmostEqual(result["p_value"], 1.0, places=12)

    def test_wilcoxon_all_zero(self):
        result = s2.wilcoxon_signed_rank_two_sided([0.0, 0.0, 0.0])
        self.assertEqual(result["n_pairs"], 3)
        self.assertEqual(result["n_nonzero"], 0)
        self.assertEqual(result["p_value_method"], "ALL_ZERO")
        self.assertAlmostEqual(result["p_value"], 1.0, places=12)

    def test_wilcoxon_normal_approximation_direction(self):
        result = s2.wilcoxon_signed_rank_two_sided([0.1] * 30)
        self.assertEqual(result["n_nonzero"], 30)
        self.assertIn("normal_approximation", result["p_value_method"])
        self.assertLess(result["p_value"], 1e-5)

    def test_bootstrap_reproducible_and_excludes_zero(self):
        values = [-0.10 - 0.001 * index for index in range(20)]
        first = s2.bootstrap_mean_ci(values)
        second = s2.bootstrap_mean_ci(values)
        self.assertEqual(first["n_resamples"], 10000)
        self.assertEqual(first["seed"], 20261105)
        self.assertEqual(first["ci_low"], second["ci_low"])
        self.assertEqual(first["ci_high"], second["ci_high"])
        self.assertLess(first["ci_low"], 0.0)
        self.assertLess(first["ci_high"], 0.0)
        self.assertTrue(first["ci_excludes_zero"])

    def test_holm_adjust_known_vector(self):
        adjusted = s2.holm_adjust([0.01, 0.04], family_size=2)
        self.assertAlmostEqual(adjusted[0], 0.02, places=12)
        self.assertAlmostEqual(adjusted[1], 0.04, places=12)
        reversed_adjusted = s2.holm_adjust([0.04, 0.01], family_size=2)
        self.assertAlmostEqual(reversed_adjusted[0], 0.04, places=12)
        self.assertAlmostEqual(reversed_adjusted[1], 0.02, places=12)

    @staticmethod
    def _inference(mean_difference, ci_low, ci_high, relative, *, n_pairs=20, null_ratio=0.0):
        return {
            "endpoint_id": "post_adaptation_rmse_raw_k5",
            "n_pairs": n_pairs,
            "null_ratio": null_ratio,
            "mean_difference": mean_difference,
            "bootstrap": {
                "ci_low": ci_low,
                "ci_high": ci_high,
                "ci_excludes_zero": ci_low > 0.0 or ci_high < 0.0,
            },
            "relative_improvement": {"value": relative},
        }

    def test_decision_benefit(self):
        decision = s2._decide_endpoint(
            self._inference(-0.10, -0.12, -0.08, 0.10),
            integrity={},
            holm_p_adjusted=1e-6,
        )
        self.assertEqual(decision["decision"], "SUPPORTED_BENEFIT")

    def test_decision_harm(self):
        decision = s2._decide_endpoint(
            self._inference(0.10, 0.08, 0.12, -0.10),
            integrity={},
            holm_p_adjusted=1e-6,
        )
        self.assertEqual(decision["decision"], "SUPPORTED_HARM")

    def test_decision_inconclusive_on_null_ratio(self):
        decision = s2._decide_endpoint(
            self._inference(-0.10, -0.12, -0.08, 0.10, null_ratio=0.80),
            integrity={},
            holm_p_adjusted=1e-6,
        )
        self.assertEqual(decision["decision"], "INCONCLUSIVE")

    def test_decision_inconclusive_on_insufficient_pairs(self):
        decision = s2._decide_endpoint(
            self._inference(-0.10, -0.12, -0.08, 0.10, n_pairs=5),
            integrity={},
            holm_p_adjusted=1e-6,
        )
        self.assertEqual(decision["decision"], "INCONCLUSIVE")

    def test_decision_inconclusive_on_runtime_degraded(self):
        decision = s2._decide_endpoint(
            self._inference(-0.10, -0.12, -0.08, 0.10),
            integrity={"primary_should_be_inconclusive": True},
            holm_p_adjusted=1e-6,
        )
        self.assertEqual(decision["decision"], "INCONCLUSIVE")

    def test_decision_no_evidence_when_holm_not_significant(self):
        decision = s2._decide_endpoint(
            self._inference(-0.10, -0.12, -0.08, 0.10),
            integrity={},
            holm_p_adjusted=0.5,
        )
        self.assertEqual(decision["decision"], "NO_EVIDENCE")


import csv
import io
from contextlib import redirect_stderr, redirect_stdout

_E2E = {}


def _read_csv_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _e2e_without_figures():
    if "no_figures" not in _E2E:
        prereg_path, _raw = _base_prereg()
        output_dir = _TMP_ROOT / "e2e-out-no-figures"
        result = s2.analyze_s2_run(
            prereg_path=prereg_path,
            run_dir=_base_run(),
            output_dir=output_dir,
            repo_root=_BASE_ROOT,
            verify_frozen_package=False,
            verify_code_sha=False,
            generate_figures=False,
        )
        _E2E["no_figures"] = (result, output_dir)
    return _E2E["no_figures"]


def _e2e_with_figures():
    if "figures" not in _E2E:
        prereg_path, _raw = _base_prereg()
        output_dir = _TMP_ROOT / "e2e-out-figures"
        result = s2.analyze_s2_run(
            prereg_path=prereg_path,
            run_dir=_base_run(),
            output_dir=output_dir,
            repo_root=_BASE_ROOT,
            verify_frozen_package=False,
            verify_code_sha=False,
            generate_figures=True,
        )
        _E2E["figures"] = (result, output_dir)
    return _E2E["figures"]


class EndToEndAnalysisTests(_S2TestBase):
    """端到端：合成正式 run → 8 数据产物 + task 级聚合 + 单 Holm 族 + K=0/1 描述。"""

    def test_all_eight_artifacts_written(self):
        result, output_dir = _e2e_without_figures()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["artifacts"]), 8)
        for name in s2.S2_OUTPUT_FILES:
            path = output_dir / name
            self.assertTrue(path.is_file(), name)
            self.assertGreater(path.stat().st_size, 0, name)
        self.assertEqual(result["n_tasks"], 20)
        self.assertEqual(result["record_counts"]["train"], 1200)
        self.assertEqual(result["record_counts"]["eval"], 4800)

    def test_single_holm_family_of_two(self):
        _result, output_dir = _e2e_without_figures()
        aggregate = _read_json(output_dir / "aggregate.json")
        holm = aggregate["holm"]
        self.assertEqual(holm["family_id"], "s2-primary-secondary-2tests")
        self.assertEqual(holm["family_key"], "s2_primary_secondary")
        self.assertEqual(holm["family_size"], 2)
        self.assertEqual(len(holm["members"]), 2)
        self.assertEqual(sorted(holm["adjusted_p"]), ["post_adaptation_rmse_raw_k10", "post_adaptation_rmse_raw_k5"])
        self.assertNotIn("post_adaptation_rmse_raw_k0", holm["raw_p"])
        rows = _read_csv_rows(output_dir / "s2_holm_family.csv")
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["family_size"] for row in rows}, {"2"})
        self.assertEqual({row["family_id"] for row in rows}, {"s2-primary-secondary-2tests"})

    def test_primary_and_secondary_decisions(self):
        result, output_dir = _e2e_without_figures()
        aggregate = _read_json(output_dir / "aggregate.json")
        decisions = aggregate["decisions"]
        self.assertEqual(decisions["post_adaptation_rmse_raw_k5"]["decision"], "SUPPORTED_BENEFIT")
        self.assertEqual(decisions["post_adaptation_rmse_raw_k10"]["decision"], "SUPPORTED_BENEFIT")
        self.assertEqual(aggregate["overall"]["decision"], "SUPPORTED_IMPROVEMENT")
        self.assertEqual(result["overall_decision"]["decision"], "SUPPORTED_IMPROVEMENT")
        inference = {item["endpoint_id"]: item for item in aggregate["inference"]}
        primary = inference["post_adaptation_rmse_raw_k5"]
        self.assertEqual(primary["n_pairs"], 20)
        self.assertAlmostEqual(primary["mean_difference"], -0.10, places=12)
        self.assertTrue(primary["bootstrap"]["ci_excludes_zero"])
        self.assertAlmostEqual(primary["relative_improvement"]["value"], 0.10 / (1.095 + 4.5e-6), places=12)

    def test_task_level_aggregation_not_mixed(self):
        _result, output_dir = _e2e_without_figures()
        rows = _read_csv_rows(output_dir / "s2_per_task_aggregates.csv")
        by_key = {(row["task_id"], row["arm"], row["endpoint"]): row for row in rows}
        for task_index, task_id in enumerate(_TASKS):
            full = by_key[(task_id, "FULL_MAML", "post_adaptation_rmse_raw_k5")]
            fomaml = by_key[(task_id, "FOMAML", "post_adaptation_rmse_raw_k5")]
            self.assertEqual(int(full["meta_seed_count"]), 3)
            self.assertEqual(int(full["draw_count"]), 10)
            self.assertAlmostEqual(float(full["value"]), 0.90 + 4.5e-6 + 0.01 * task_index, places=12)
            self.assertAlmostEqual(float(fomaml["value"]), 1.00 + 4.5e-6 + 0.01 * task_index, places=12)
            self.assertEqual(int(full["n_values"]), 3)  # 每 (task,arm) 3 个 meta_seed 聚合值
            self.assertEqual(int(full["n_null"]), 0)

    def test_k0_k1_descriptive_only(self):
        _result, output_dir = _e2e_without_figures()
        aggregate = _read_json(output_dir / "aggregate.json")
        metrics = aggregate["descriptive"]["metrics"]
        self.assertIn("post_adaptation_rmse_raw_k0", metrics)
        self.assertIn("post_adaptation_rmse_raw_k1", metrics)
        self.assertEqual(metrics["post_adaptation_rmse_raw_k0"]["note"], "描述性指标：不做 benefit/harm 推断。")
        inference_ids = {item["endpoint_id"] for item in aggregate["inference"]}
        self.assertEqual(inference_ids, {"post_adaptation_rmse_raw_k5", "post_adaptation_rmse_raw_k10"})
        decisions_ids = set(aggregate["decisions"])
        self.assertNotIn("post_adaptation_rmse_raw_k0", decisions_ids)
        self.assertNotIn("post_adaptation_rmse_raw_k1", decisions_ids)
        self.assertTrue(metrics["post_adaptation_rmse_raw_k0"]["K"] == 0)
        self.assertTrue(metrics["post_adaptation_rmse_raw_k1"]["K"] == 1)

    def test_negative_controls_and_prereg_echo(self):
        _result, output_dir = _e2e_without_figures()
        controls = _read_csv_rows(output_dir / "s2_negative_controls.csv")
        self.assertGreaterEqual(len(controls), 14)
        self.assertNotIn("FAIL", {row["status"] for row in controls})
        echo = _read_json(output_dir / "s2_prereg_echo.json")
        self.assertTrue(echo["digest_self_consistent"])
        self.assertEqual(echo["prereg_id"], _base_prereg()[1]["prereg_id"])
        self.assertEqual(echo["evidence_scope"], _EVIDENCE_SCOPE)

    def test_figures_disabled_reason(self):
        result, output_dir = _e2e_without_figures()
        status = result["figure_status"]
        self.assertEqual(status["summary"]["n_rendered"], 0)
        self.assertEqual(status["summary"]["n_not_run"], 9)
        self.assertEqual(set(status["figures"]), set(s2.FIGURE_KEYS))
        for key in s2.FIGURE_KEYS:
            self.assertEqual(status["figures"][key]["status"], "NOT_RUN")
            self.assertIsNone(status["figures"][key]["path"])

    def test_output_dir_refuses_nonempty_without_overwrite(self):
        prereg_path, _raw = _base_prereg()
        output_dir = _TMP_ROOT / "e2e-out-refuse"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "keep.txt").write_text("x", encoding="utf-8")
        self.assert_error(
            s2.ERR_OUTPUT,
            s2.analyze_s2_run,
            prereg_path=prereg_path,
            run_dir=_base_run(),
            output_dir=output_dir,
            repo_root=_BASE_ROOT,
            verify_frozen_package=False,
            verify_code_sha=False,
            generate_figures=False,
        )


class FigureGenerationTests(_S2TestBase):
    """9 张规范键图：RENDERED 文件存在、图注标注 evidence_scope、支撑 CSV、NOT_APPLICABLE 不伪造。"""

    def test_all_nine_figures_rendered_with_scope_annotation(self):
        result, output_dir = _e2e_with_figures()
        status = result["figure_status"]
        self.assertEqual(status["summary"]["n_figures"], 9)
        self.assertEqual(status["summary"]["n_rendered"], 9, status)
        for key in s2.FIGURE_KEYS:
            item = status["figures"][key]
            self.assertEqual(item["status"], "RENDERED", (key, item))
            path = output_dir / str(item["path"])
            self.assertTrue(path.is_file(), key)
            self.assertGreater(path.stat().st_size, 1000, key)
        self.assertIn("evidence_scope=", s2._import_figures_module()._evidence_scope_note({"evidence_scope": _EVIDENCE_SCOPE}))

    def test_figure_caption_scope_and_support_csv(self):
        _result, output_dir = _e2e_with_figures()
        for key in s2.FIGURE_KEYS:
            support = output_dir / (key + "_support.csv")
            self.assertTrue(support.is_file(), key)
            rows = _read_csv_rows(support)
            self.assertGreaterEqual(len(rows), 1, key)
            self.assertIn("evidence_scope", rows[0])
            self.assertEqual({row["evidence_scope"] for row in rows}, {"evidence_scope=" + _EVIDENCE_SCOPE}, key)
            self.assertEqual({row["figure_key"] for row in rows}, {key})

    def test_evidence_scope_note_unknown_when_missing(self):
        figures = s2._import_figures_module()
        note = figures._evidence_scope_note({})
        self.assertIn("evidence_scope=UNKNOWN", note)
        note_none = figures._evidence_scope_note({"evidence_scope": None})
        self.assertIn("evidence_scope=UNKNOWN", note_none)

    def test_empty_state_does_not_fabricate(self):
        figures = s2._import_figures_module()
        output_dir = _TMP_ROOT / "figures-empty"
        status = figures.generate_s2_figures(state={}, output_dir=output_dir, figure_filenames=dict(s2.FIGURE_FILENAMES))
        self.assertEqual(set(status["figures"]), set(s2.FIGURE_KEYS))
        for key in s2.FIGURE_KEYS:
            item = status["figures"][key]
            self.assertIn(item["status"], ("NOT_RUN", "NOT_APPLICABLE"), (key, item))
            self.assertIsNone(item["path"], key)
        for key in s2.FIGURE_KEYS:
            rows = _read_csv_rows(output_dir / (key + "_support.csv"))
            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(rows[0]["evidence_scope"], "evidence_scope=UNKNOWN")


def _k5_figure_state(families=None):
    """fig9/fig3 单测用最小 state：K=5 task 级值齐全，可选 task→family 映射。"""
    per_task = {}
    for index, task_id in enumerate(_TASKS):
        per_task[task_id] = {
            "FULL_MAML": {"value": 0.90 + 0.01 * index, "null_ratio": 0.0},
            "FOMAML": {"value": 1.00 + 0.01 * index, "null_ratio": 0.0},
        }
    state = {
        "evidence_scope": _EVIDENCE_SCOPE,
        "endpoints": {
            "post_adaptation_rmse_raw_k5": {
                "per_task": per_task,
                "n_tasks": len(_TASKS),
                "null_ratio": 0.0,
            }
        },
    }
    if families is not None:
        state["task_families"] = families
        state["task_families_source"] = "fake/tasks.json"
        state["task_families_reason"] = None
    return state


class V15FigureContractTests(_S2TestBase):
    """v1.5 图合同：fig8 性能-成本、fig9 任务族诊断、fig3 task 级 CI、NOT_RUN 不伪造。

    A5-S2M0R5-01：S0-7 全部 task 同属单一 family，fig9 panel b 仅为族内分布，
    图注/报告不得解释为任务族间差异。
    """

    def test_fig8_fig9_keys_registered(self):
        self.assertIn("fig8_performance_cost", s2.FIGURE_KEYS)
        self.assertIn("fig9_task_family_diagnostics", s2.FIGURE_KEYS)
        self.assertEqual(len(s2.FIGURE_KEYS), 9)
        self.assertEqual(len(set(s2.FIGURE_KEYS)), 9)

    def test_fig8_not_run_without_resource_records(self):
        figures = s2._import_figures_module()
        output_dir = _TMP_ROOT / "figures-v15-fig8-notrun"
        status = figures.generate_s2_figures(
            state=_k5_figure_state(), output_dir=output_dir, figure_filenames=dict(s2.FIGURE_FILENAMES)
        )
        item = status["figures"]["fig8_performance_cost"]
        self.assertEqual(item["status"], "NOT_RUN", item)
        self.assertIsNone(item["path"])
        self.assertIn("NOT_RUN", str(item["reason"]))

    def test_fig9_not_run_without_k5_task_rows(self):
        figures = s2._import_figures_module()
        output_dir = _TMP_ROOT / "figures-v15-fig9-notrun"
        status = figures.generate_s2_figures(
            state={"evidence_scope": _EVIDENCE_SCOPE, "endpoints": {}},
            output_dir=output_dir,
            figure_filenames=dict(s2.FIGURE_FILENAMES),
        )
        item = status["figures"]["fig9_task_family_diagnostics"]
        self.assertEqual(item["status"], "NOT_RUN", item)
        self.assertIsNone(item["path"])

    def test_fig9_single_family_note_and_within_family_distribution(self):
        figures = s2._import_figures_module()
        families = {task_id: "F-QE-feasible-v3" for task_id in _TASKS}
        output_dir = _TMP_ROOT / "figures-v15-fig9-single-family"
        status = figures.generate_s2_figures(
            state=_k5_figure_state(families),
            output_dir=output_dir,
            figure_filenames=dict(s2.FIGURE_FILENAMES),
        )
        item = status["figures"]["fig9_task_family_diagnostics"]
        self.assertEqual(item["status"], "RENDERED", item)
        self.assertTrue((output_dir / "fig9_task_family_diagnostics.png").is_file())
        rows = _read_csv_rows(output_dir / "fig9_task_family_diagnostics_support.csv")
        texts = [row["y"] for row in rows]
        self.assertTrue(any("不声称任务族间差异" in text for text in texts), texts)
        self.assertTrue(any("NOT_APPLICABLE_S2_NO_OOD_SPLIT" in text for text in texts), texts)
        self.assertTrue(any("NOT_APPLICABLE_S2_SURROGATE_SCOPE" in text for text in texts), texts)
        family_rows = [row for row in rows if row["series"].startswith("family/")]
        self.assertEqual(len(family_rows), 2)  # 单族 × 两臂
        self.assertTrue(all("F-QE-feasible-v3" == row["x"] for row in family_rows))
        self.assertEqual({row["evidence_scope"] for row in rows}, {"evidence_scope=" + _EVIDENCE_SCOPE})

    def test_fig9_missing_family_mapping_keeps_panel_a(self):
        figures = s2._import_figures_module()
        output_dir = _TMP_ROOT / "figures-v15-fig9-no-family"
        status = figures.generate_s2_figures(
            state=_k5_figure_state(), output_dir=output_dir, figure_filenames=dict(s2.FIGURE_FILENAMES)
        )
        item = status["figures"]["fig9_task_family_diagnostics"]
        self.assertEqual(item["status"], "RENDERED", item)
        rows = _read_csv_rows(output_dir / "fig9_task_family_diagnostics_support.csv")
        self.assertFalse(any(row["series"].startswith("family/") for row in rows))
        self.assertGreaterEqual(len([row for row in rows if row["series"] in ("FULL_MAML", "FOMAML")]), 2 * len(_TASKS))

    def test_fig8_support_csv_resources_descriptive_only(self):
        _result, output_dir = _e2e_with_figures()
        rows = _read_csv_rows(output_dir / "fig8_performance_cost_support.csv")
        series = {row["series"] for row in rows}
        self.assertIn("FULL_MAML/train_wall_per_meta_seed", series)
        self.assertIn("FOMAML/train_wall_per_meta_seed", series)
        self.assertIn("FULL_MAML/peak_memory_mb_max", series)
        self.assertIn("train_wall_seconds_ratio", series)
        ratio_rows = [row for row in rows if row["series"] == "train_wall_seconds_ratio"]
        self.assertEqual(len(ratio_rows), 1)
        self.assertAlmostEqual(float(ratio_rows[0]["y"]), 1.0, places=9)

    def test_fig3_support_csv_ci_is_task_level(self):
        _result, output_dir = _e2e_with_figures()
        rows = _read_csv_rows(output_dir / "fig3_rmse_vs_K_support.csv")
        series = {row["series"] for row in rows}
        for arm in ("FULL_MAML", "FOMAML"):
            for suffix in ("ci_low", "ci_high", "n"):
                self.assertIn(arm + "/" + suffix, series)
        n_values = {row["y"] for row in rows if row["series"] == "FULL_MAML/n"}
        self.assertEqual(n_values, {"20"})  # 重采样单元=task，不是 meta_seed/draw 记录
        lows = [float(row["y"]) for row in rows if row["series"] == "FULL_MAML/ci_low"]
        highs = [float(row["y"]) for row in rows if row["series"] == "FULL_MAML/ci_high"]
        self.assertEqual(len(lows), 4)
        self.assertEqual(len(highs), 4)
        for low, high in zip(lows, highs):
            self.assertLessEqual(low, high)

    def test_fig3_ci_state_deterministic(self):
        prereg_path, _raw = _base_prereg()
        prereg = _load_prereg(prereg_path, _BASE_ROOT)
        run = s2.load_s2_run(_base_run(), prereg, repo_root=_BASE_ROOT)
        first = s2._build_rmse_vs_k(run, prereg)
        second = s2._build_rmse_vs_k(run, prereg)
        self.assertEqual(first, second)
        for arm in ("FULL_MAML", "FOMAML"):
            for k_value in ("0", "1", "5", "10"):
                cell = first["ci"][arm][k_value]
                self.assertEqual(cell["n"], 20)
                self.assertEqual(cell["n_resamples"], 10000)
                self.assertEqual(cell["seed"], 20261105)
                self.assertEqual(cell["confidence_level"], 0.95)
                if k_value in ("5", "10"):
                    self.assertLess(cell["ci_low"], cell["ci_high"])
        # 每 task 的 K=5 值是 meta_seed×draw 的聚合结果。
        task_id = _TASKS[0]
        self.assertAlmostEqual(
            first["per_task"]["5"]["FULL_MAML"][task_id], 0.90 + 4.5e-6, places=12
        )


class FigureStatusValidationTests(_S2TestBase):
    """figure_status 结构 fail-closed：缺键/非法状态/非 RENDERED path 归一。"""

    @staticmethod
    def _payload(**overrides):
        figures = {
            key: {"status": "NOT_RUN", "path": None, "reason": "NO_DATA"} for key in s2.FIGURE_KEYS
        }
        figures.update(overrides)
        return {"figures": figures}

    def test_valid_status_normalized(self):
        payload = self._payload(fig1_training_loss_curves={"status": "RENDERED", "path": "fig1.png", "reason": None})
        validated = s2._validate_figure_status(payload)
        self.assertEqual(validated["schema_version"], s2.S2_FIGURE_STATUS_SCHEMA_VERSION)
        self.assertEqual(validated["summary"]["n_rendered"], 1)
        self.assertEqual(validated["summary"]["n_not_run"], 8)
        self.assertEqual(validated["figures"]["fig1_training_loss_curves"]["path"], "fig1.png")

    def test_missing_figure_key_rejected(self):
        payload = self._payload()
        payload["figures"].pop("fig7_determinism_and_negative_controls")
        self.assert_error(s2.ERR_OUTPUT, s2._validate_figure_status, payload)

    def test_illegal_status_rejected(self):
        payload = self._payload(fig1_training_loss_curves={"status": "DONE", "path": "fig1.png", "reason": None})
        self.assert_error(s2.ERR_OUTPUT, s2._validate_figure_status, payload)

    def test_non_rendered_path_dropped(self):
        payload = self._payload(fig1_training_loss_curves={"status": "NOT_RUN", "path": "fig1.png", "reason": "X"})
        validated = s2._validate_figure_status(payload)
        self.assertIsNone(validated["figures"]["fig1_training_loss_curves"]["path"])


class CliTests(_S2TestBase):
    """CLI：verify-only 不建目录、成功路径退出 0、失败退出 2 且 stderr 为 JSON。"""

    def _run_cli(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = s2.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_verify_only_does_not_create_output_dir(self):
        prereg_path, _raw = _base_prereg()
        output_dir = _TMP_ROOT / "cli-verify-only"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        code, stdout, stderr = self._run_cli(
            [
                "--prereg",
                str(prereg_path),
                "--run-dir",
                str(_base_run()),
                "--output-dir",
                str(output_dir),
                "--repo-root",
                str(_BASE_ROOT),
                "--skip-frozen-package-check",
                "--skip-code-sha-check",
                "--verify-only",
            ]
        )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["mode"], "verify_only")
        self.assertFalse(output_dir.exists())

    def test_success_path_returns_zero(self):
        prereg_path, _raw = _base_prereg()
        output_dir = _TMP_ROOT / "cli-success"
        code, stdout, stderr = self._run_cli(
            [
                "--prereg",
                str(prereg_path),
                "--run-dir",
                str(_base_run()),
                "--output-dir",
                str(output_dir),
                "--repo-root",
                str(_BASE_ROOT),
                "--skip-frozen-package-check",
                "--skip-code-sha-check",
                "--skip-figures",
            ]
        )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual((output_dir / "aggregate.json").is_file(), True)

    def test_failure_returns_two_with_json_code(self):
        output_dir = _TMP_ROOT / "cli-failure"
        code, _stdout, stderr = self._run_cli(
            [
                "--prereg",
                str(_TMP_ROOT / "missing-prereg.json"),
                "--run-dir",
                str(_base_run()),
                "--output-dir",
                str(output_dir),
                "--repo-root",
                str(_BASE_ROOT),
                "--skip-frozen-package-check",
                "--skip-code-sha-check",
                "--skip-figures",
            ]
        )
        self.assertEqual(code, 2)
        payload = json.loads(stderr)
        self.assertEqual(payload["status"], "FAIL")
        self.assertEqual(payload["code"], s2.ERR_PREREG_SCHEMA)

    def test_overwrite_flag_allows_nonempty_output(self):
        prereg_path, _raw = _base_prereg()
        output_dir = _TMP_ROOT / "cli-overwrite"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "keep.txt").write_text("x", encoding="utf-8")
        code, _stdout, stderr = self._run_cli(
            [
                "--prereg",
                str(prereg_path),
                "--run-dir",
                str(_base_run()),
                "--output-dir",
                str(output_dir),
                "--repo-root",
                str(_BASE_ROOT),
                "--skip-frozen-package-check",
                "--skip-code-sha-check",
                "--skip-figures",
                "--overwrite",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue((output_dir / "aggregate.json").is_file())
