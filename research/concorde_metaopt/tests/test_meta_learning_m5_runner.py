"""M5 运行器（m5_runner.py）单元测试：校准 / 冻结 / holdout 三阶段门禁与产物。

覆盖 task-115 要求（Issue #5 D-P4-002）：
1. calibration 阶段只在 meta_train/meta_validation 上校准，assert_calibration_only 拒绝 test/ood；
2. freeze/holdout 的 frozen_family.json / preregistration.json fail-closed
   （缺失校准报告、frozen/prereg/校准报告 sha/半径不一致一律拒绝开 holdout）；
3. physical_call_count>0 → status=PHYSICS_GUARD_VIOLATION 且只写失败 summary.json，不继续；
4. 等预算：每臂 true_evals_used == budget；每 run 前 8 次为共享/模型初始设计；
5. null 规则：无可行解时 best_feasible_value/gap/first_feasible 保留 null（不写 0），
   fallback 指标另行记录，summary 披露每端点 null 比例；
6. determinism：2 轮独立重跑逐组摘要逐位一致（PASS）；reruns<2 时如实 NOT_RUN；
7. 22 项产物齐全 + figure_status 键（无 PNG；fig2/fig6 标 NOT_APPLICABLE/NOT_RUN）；
8. run_config/preregistration_gate/counts 等关键字段。

全部使用解析合成任务族与解析 evaluator（physical_call_count 恒 0），
不访问网络、不调用任何真实求解器。
"""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from research.concorde_metaopt.meta_learning import feasible_v2 as fv2
from research.concorde_metaopt.meta_learning import m5_runner as m5
from research.concorde_metaopt.meta_learning import task_family as tf
from research.concorde_metaopt.meta_learning.baseline_arms import (
    FAILED_STATUS,
    NO_FEASIBLE_STATUS,
    VALID_STATUS,
)
from research.concorde_metaopt.meta_learning.offline_runner import (
    build_data_manifest,
    load_design_space_12d,
    sha256_file_normalized,
)

SELECTED_RADIUS = 0.75
HOLDOUT_TASKS = 2  # meta_test 1 + meta_test_ood 1
HOLDOUT_SEEDS = (0, 1)
HOLDOUT_BUDGETS = (8, 10)
META_SEEDS = (0,)
EXPECTED_GROUPS = HOLDOUT_TASKS * len(HOLDOUT_SEEDS)
EXPECTED_RUNS = EXPECTED_GROUPS * len(HOLDOUT_BUDGETS) * 4
EXPECTED_EVALUATIONS = EXPECTED_GROUPS * sum(4 * budget for budget in HOLDOUT_BUDGETS)
FIGURE_KEYS = (
    "fig1_meta_training_loss",
    "fig2_k_shot_adaptation",
    "fig3_feasible_rate",
    "fig4_equal_budget_gap",
    "fig5_fairness_audit",
    "fig6_airframe_gate_progress",
)

_TEMP_ROOTS: list[Path] = []
_STUDY: dict[str, object] = {}


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json_raw(path: Path, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _calibration_config() -> fv2.CalibrationConfig:
    return fv2.CalibrationConfig(
        radius_grid=(SELECTED_RADIUS,),
        opt_seeds=(0,),
        train_tasks=2,
        validation_tasks=1,
        budget=8,
        family_seed=20261102,
        empirical_samples=16,
    )


def _fake_calibration_report(
    *,
    radius: float = SELECTED_RADIUS,
    selected: bool = True,
    physical_call_count: int = 0,
) -> fv2.CalibrationReport:
    """构造真实结构、真实 sha 的假校准报告，避免测试跑 24 分钟真实校准。"""
    calibration = _calibration_config()
    cell = fv2.CalibrationCell(
        radius_base=float(radius),
        success_rate_by_seed=(0.5,),
        feasible_hit_rate_by_seed=(0.25,),
        success_rate_median=0.5,
        feasible_hit_rate_median=0.25,
        pooled_success_train=0.5,
        pooled_hit_rate_train=0.25,
        validation_success_rate_median=0.5,
        all_seeds_in_acceptance=True,
        analytic_sphere_fraction=fv2.analytic_sphere_fraction(radius),
        analytic_ellipsoid_fraction_median=1.0e-4,
        feasible_volume_fraction=1.0e-4,
        n_tasks=3,
        budget=8,
        evaluations=24,
        n_null=0,
        wall_s=0.0,
    )
    return fv2.CalibrationReport(
        schema_version=fv2.CALIBRATION_SCHEMA_VERSION,
        created_utc="2026-11-04T00:00:00+00:00",
        calibration=calibration,
        cells=(cell,),
        rows=(),
        cohorts=({"radius_base": float(radius), "task_ids": {"meta_train": [], "meta_validation": []}},),
        reference_certificates=({"task_id": "fixture", "min_margin": 0.1, "kkt_residual": 0.0},),
        selected_radius_base=(float(radius) if selected else None),
        selection_status=("SELECTED" if selected else "NO_CELL_IN_TARGET"),
        selection_rule=fv2.SELECTION_RULE,
        notes=("单元测试假校准报告（非真实校准证据）",),
        physical_call_count=int(physical_call_count),
    )


def _tiny_config(root: Path, *, stage: str, run_id: str, **overrides: object) -> m5.M5RunnerConfig:
    values = dict(
        run_id=run_id,
        output_root=root,
        stage=stage,
        family_seed=20261102,
        meta_train_tasks=2,
        meta_validation_tasks=1,
        meta_test_tasks=1,
        ood_tasks=1,
        negative_control_tasks=0,
        support_pool_size=8,
        query_size=4,
        budgets=HOLDOUT_BUDGETS,
        optimization_seeds=tuple(range(10)),
        meta_seeds=META_SEEDS,
        calibration=_calibration_config(),
        max_meta_steps=2,
        pretrain_steps=2,
        determinism_reruns=2,
    )
    values.update(overrides)
    return m5.M5RunnerConfig(**values)


def _new_root(prefix: str = "p4-m5-runner-tests-") -> Path:
    root = Path(tempfile.mkdtemp(prefix=prefix))
    _TEMP_ROOTS.append(root)
    return root


def _prepare_holdout_prerequisites(
    calibration_run_dir: Path, freeze_run_dir: Path, holdout_run_dir: Path
) -> None:
    """把 calibration/freeze 产物复制到独立 holdout run 目录（三阶段互不覆盖产物）。"""
    holdout_run_dir = Path(holdout_run_dir)
    (holdout_run_dir / "calibration").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        Path(calibration_run_dir) / "calibration" / "calibration_report.json",
        holdout_run_dir / "calibration" / "calibration_report.json",
    )
    for name in ("frozen_family.json", "meta_task_split.json", "preregistration.json"):
        shutil.copy2(Path(freeze_run_dir) / name, holdout_run_dir / name)


def _study() -> dict[str, object]:
    """共享 tiny 端到端 study：fake 校准 → freeze → holdout（三阶段独立 run 目录，只跑一次）。"""
    if _STUDY:
        return _STUDY
    root = _new_root()
    design_space = load_design_space_12d()
    report = _fake_calibration_report()
    calibration_config = _tiny_config(root, stage="calibration", run_id="m5-runner-cal")
    calibration = m5.run_calibration_stage(
        calibration_config, design_space=design_space, calibration_report=report
    )
    report_path = calibration_config.run_dir / "calibration" / "calibration_report.json"
    freeze_config = _tiny_config(
        root, stage="freeze", run_id="m5-runner-freeze", calibration_report_path=report_path
    )
    freeze = m5.run_freeze_stage(freeze_config, design_space=design_space)
    holdout_config = _tiny_config(
        root,
        stage="holdout",
        run_id="m5-runner-holdout",
        calibration_report_path=report_path,
        optimization_seeds=HOLDOUT_SEEDS,
        determinism_reruns=2,
    )
    _prepare_holdout_prerequisites(
        calibration_config.run_dir, freeze_config.run_dir, holdout_config.run_dir
    )
    holdout = m5.run_holdout_stage(holdout_config, workers=1)
    _STUDY.update(
        root=root,
        run_dir=holdout_config.run_dir,
        design_space=design_space,
        report=report,
        report_path=report_path,
        calibration_config=calibration_config,
        calibration=calibration,
        freeze_config=freeze_config,
        freeze=freeze,
        holdout_config=holdout_config,
        holdout=holdout,
    )
    return _STUDY


def _copy_prerequisites(source: Path, destination: Path) -> None:
    """复制 frozen/prereg/split/校准报告到新 run 目录（用于失败路径变体）。"""
    destination = Path(destination)
    (destination / "calibration").mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(source) / "calibration" / "calibration_report.json", destination / "calibration" / "calibration_report.json")
    for name in ("frozen_family.json", "meta_task_split.json", "preregistration.json"):
        shutil.copy2(Path(source) / name, destination / name)


def _variant_config(base: m5.M5RunnerConfig, *, root: Path, run_id: str, **overrides: object) -> m5.M5RunnerConfig:
    return replace(base, output_root=root, run_id=run_id, **overrides)


def _variant_paths(base: m5.M5RunnerConfig, *, root: Path, run_id: str, destination: Path) -> m5.M5RunnerConfig:
    """把四方门禁输入显式指向副本目录（避免误读共享 study 的原始文件）。"""
    return replace(
        base,
        output_root=root,
        run_id=run_id,
        calibration_report_path=Path(destination) / "calibration" / "calibration_report.json",
        frozen_family_path=Path(destination) / "frozen_family.json",
        preregistration_path=Path(destination) / "preregistration.json",
        split_manifest_path=Path(destination) / "meta_task_split.json",
    )


def tearDownModule() -> None:
    for root in _TEMP_ROOTS:
        shutil.rmtree(root, ignore_errors=True)
    _TEMP_ROOTS.clear()
    _STUDY.clear()


class M5RunnerConfigTests(unittest.TestCase):
    """配置契约：规模判定、非法输入 fail-closed。"""

    def test_01_tiny_config_is_smoke_scale(self) -> None:
        root = _new_root()
        config = _tiny_config(root, stage="holdout", run_id="cfg-tiny")
        self.assertEqual(config.study_scale, "SMOKE")
        self.assertEqual(config.run_dir, root / "cfg-tiny")
        self.assertEqual(config.designs_per_task, 12)
        payload = config.to_dict()
        self.assertEqual(payload["stage"], "holdout")
        self.assertEqual(payload["split_counts"]["meta_train"], 2)
        self.assertEqual(payload["split_counts"]["meta_test"], 1)
        self.assertEqual(list(payload["budgets"]), list(HOLDOUT_BUDGETS))
        self.assertEqual(list(payload["optimization_seeds"]), list(range(10)))

    def test_02_default_scale_is_formal_but_tiny_is_not(self) -> None:
        root = _new_root()
        formal = m5.M5RunnerConfig(run_id="cfg-formal", output_root=root)
        self.assertEqual(formal.study_scale, "FORMAL")
        self.assertEqual(formal.study_scale == "FORMAL", True)
        # 任一正式规模条件不满足即降级 SMOKE（不得把小规模结果当正式结论）
        downgraded = replace(formal, meta_test_tasks=19)
        self.assertEqual(downgraded.study_scale, "SMOKE")

    def test_03_invalid_config_rejected(self) -> None:
        root = _new_root()
        bad_values = [
            dict(stage="unknown"),
            dict(physical_guard_expected=1),
            dict(budgets=(4,)),
            dict(run_id="a/b"),
            dict(meta_train_tasks=1),
            dict(optimization_seeds=(0, 0)),
        ]
        for index, overrides in enumerate(bad_values):
            values = dict(run_id="cfg-bad", output_root=root, stage="holdout")
            values.update(overrides)
            with self.subTest(case=index):
                with self.assertRaises(m5.M5RunnerError):
                    m5.M5RunnerConfig(**values)


class M5CalibrationStageTests(unittest.TestCase):
    """calibration 阶段：只校准 train/val、写证据、物理守卫。"""

    def test_04_calibration_only_uses_train_and_validation(self) -> None:
        calibration = _calibration_config()
        config = fv2.calibration_family_config(SELECTED_RADIUS, calibration)
        tasks = tf.build_task_family(config)
        self.assertTrue(tasks)
        splits = {task.split for task in tasks}
        self.assertEqual(splits, {"meta_train", "meta_validation"})
        self.assertEqual(fv2.assert_calibration_only(tasks), None)
        # 允许的 split 外任务必须被拒绝（防止用测试集调半径）
        leaky = tf.TaskFamilyConfig(
            family_id=tf.V2_FAMILY_ID,
            design_dim=12,
            context_names=tf.CONTEXT_NAMES,
            seed=20261102,
            train_tasks=1,
            validation_tasks=0,
            test_tasks=1,
            ood_tasks=0,
            negative_control_tasks=0,
            designs_per_task=12,
            support_pool_size=8,
            query_size=4,
            family_version="v2",
            radius_base=SELECTED_RADIUS,
        )
        with self.assertRaises(fv2.FeasibleV2Error):
            fv2.assert_calibration_only(tf.build_task_family(leaky))

    def test_05_calibration_stage_writes_report_and_evidence(self) -> None:
        study = _study()
        result = study["calibration"]
        self.assertEqual(result["status"], "CALIBRATED")
        self.assertEqual(result["stage"], "calibration")
        run_dir = Path(result["run_dir"])
        calibration_dir = run_dir / "calibration"
        for name in (
            "calibration_report.json",
            "calibration_report.csv",
            "calibration_cells.csv",
            "calibration_evidence.json",
        ):
            self.assertTrue((calibration_dir / name).is_file(), name)
        for name in ("run_config.json", "environment.json", "summary.json", "README.md", "data_manifest.json"):
            self.assertTrue((run_dir / name).is_file(), name)
        report = _read_json(calibration_dir / "calibration_report.json")
        self.assertEqual(report["selected_radius_base"], SELECTED_RADIUS)
        self.assertEqual(list(report["calibration"]["opt_seeds"]), [0])
        self.assertEqual(report["physical_call_count"], 0)
        summary = _read_json(run_dir / "summary.json")
        self.assertEqual(summary["status"], "CALIBRATED")
        self.assertEqual(summary["physical_call_count"], 0)
        self.assertEqual(summary["physics_guard"]["status"], "PASS")
        self.assertIn("stage", summary)

    def test_06_calibration_physical_guard_violation(self) -> None:
        root = _new_root()
        config = _tiny_config(root, stage="calibration", run_id="cal-guard")
        bad_report = _fake_calibration_report(physical_call_count=1)
        result = m5.run_calibration_stage(
            config, design_space=load_design_space_12d(), calibration_report=bad_report
        )
        self.assertEqual(result["status"], "PHYSICS_GUARD_VIOLATION")
        self.assertEqual(result["products_written"], ["summary.json"])
        self.assertFalse((config.run_dir / "calibration" / "calibration_report.json").exists())
        summary = _read_json(config.run_dir / "summary.json")
        self.assertEqual(summary["status"], "PHYSICS_GUARD_VIOLATION")
        self.assertEqual(summary["physical_call_count"], 1)
        self.assertEqual(summary["physics_guard"]["status"], "VIOLATED")


class M5FreezeStageTests(unittest.TestCase):
    """freeze 阶段：frozen/prereg fail-closed，冻结后 holdout 四方门禁。"""

    def test_07_freeze_writes_frozen_split_and_preregistration(self) -> None:
        study = _study()
        result = study["freeze"]
        self.assertEqual(result["status"], "FROZEN")
        run_dir = Path(result["run_dir"])
        for name in (
            "frozen_family.json",
            "meta_task_split.json",
            "preregistration.json",
            "tasks.json",
            "reference_solutions.json",
        ):
            self.assertTrue((run_dir / name).is_file(), name)
        frozen = fv2.load_frozen_family(run_dir / "frozen_family.json")
        self.assertEqual(frozen["family_version"], "v2")
        self.assertEqual(frozen["radius_base"], SELECTED_RADIUS)
        self.assertEqual(frozen["reference_solution"], "c")
        self.assertEqual(frozen["gap_definition"], "f(u_best)-f(u*)")
        self.assertEqual(frozen["calibration_seeds"], [0])
        for name in (
            "radius_base",
            "reference_solution",
            "gap_definition",
            "calibration_seeds",
            "pooled_success",
            "feasible_volume_fraction",
            "meta_test_tuning_policy",
        ):
            self.assertIn(name, frozen)
        self.assertEqual(frozen["split"]["counts"]["meta_test"], 1)
        self.assertEqual(frozen["split"]["counts"]["negative_control"], 0)
        split_manifest = _read_json(run_dir / "meta_task_split.json")
        self.assertTrue(fv2.verify_split_manifest(split_manifest, family_config=result["family_config"]))
        preregistration = fv2.load_preregistration(run_dir / "preregistration.json")
        self.assertEqual(preregistration["frozen_family_sha256"], frozen["sha256"])
        self.assertEqual(preregistration["split_hash"], frozen["split"]["split_hash"])
        self.assertEqual(list(preregistration["budgets"]), list(HOLDOUT_BUDGETS))
        self.assertEqual(len(preregistration["optimization_seeds"]), 10)
        self.assertEqual(preregistration["arms"], list(fv2.M5_ARMS))
        self.assertTrue(fv2.verify_preregistration(preregistration, frozen))
        summary = _read_json(run_dir / "summary.json")
        self.assertEqual(summary["status"], "FROZEN")
        self.assertEqual(summary["physical_call_count"], 0)

    def test_08_freeze_without_calibration_report_fails_closed(self) -> None:
        root = _new_root()
        config = _tiny_config(root, stage="freeze", run_id="freeze-missing-report")
        result = m5.run_freeze_stage(config, design_space=load_design_space_12d())
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["products_written"], ["summary.json"])
        summary = _read_json(config.run_dir / "summary.json")
        self.assertEqual(summary["status"], "FAILED")
        self.assertIn("校准报告", summary["error"]["message"])
        self.assertFalse((config.run_dir / "frozen_family.json").exists())

    def test_09_freeze_with_no_selected_cell_does_not_freeze(self) -> None:
        root = _new_root()
        run_id = "freeze-no-cell"
        calibration_config = _tiny_config(root, stage="calibration", run_id=run_id)
        report = _fake_calibration_report(selected=False)
        m5.run_calibration_stage(
            calibration_config, design_space=load_design_space_12d(), calibration_report=report
        )
        freeze_config = replace(calibration_config, stage="freeze")
        result = m5.run_freeze_stage(freeze_config, design_space=load_design_space_12d())
        self.assertEqual(result["status"], "NO_CELL_IN_TARGET")
        self.assertFalse((freeze_config.run_dir / "frozen_family.json").exists())
        self.assertFalse((freeze_config.run_dir / "preregistration.json").exists())
        summary = _read_json(freeze_config.run_dir / "summary.json")
        self.assertEqual(summary["status"], "NO_CELL_IN_TARGET")
        self.assertEqual(summary["physical_call_count"], 0)
        note = json.dumps(summary, ensure_ascii=False)
        self.assertIn("NO_CELL_IN_TARGET", note)

    def test_10_holdout_prerequisites_reject_tampered_chain(self) -> None:
        study = _study()
        source = Path(study["run_dir"])
        base_config = study["holdout_config"]
        design_space = study["design_space"]

        # 变体 1：frozen_family.json 被改但 sha256 未重签 → 拒绝
        root = _new_root()
        destination = root / "tamper-frozen"
        _copy_prerequisites(source, destination)
        frozen_path = destination / "frozen_family.json"
        payload = _read_json(frozen_path)
        payload["radius_base"] = SELECTED_RADIUS + 0.01
        _write_json_raw(frozen_path, payload)
        config = _variant_paths(base_config, root=root, run_id="tamper-frozen", destination=destination)
        with self.assertRaises(fv2.FeasibleV2Error):
            m5.load_holdout_prerequisites(config)

        # 变体 2：preregistration.json 的 frozen_family_sha256 被改 → 拒绝
        root = _new_root()
        destination = root / "tamper-prereg"
        _copy_prerequisites(source, destination)
        prereg_path = destination / "preregistration.json"
        payload = _read_json(prereg_path)
        payload["frozen_family_sha256"] = "0" * 64
        _write_json_raw(prereg_path, payload)
        config = _variant_paths(base_config, root=root, run_id="tamper-prereg", destination=destination)
        with self.assertRaises(fv2.FeasibleV2Error):
            m5.load_holdout_prerequisites(config)

        # 变体 3：校准报告被改（半径/hash 不一致）→ 拒绝
        root = _new_root()
        destination = root / "tamper-calibration"
        _copy_prerequisites(source, destination)
        report_path = destination / "calibration" / "calibration_report.json"
        payload = _read_json(report_path)
        payload["selected_radius_base"] = SELECTED_RADIUS + 0.02
        _write_json_raw(report_path, payload)
        config = _variant_paths(base_config, root=root, run_id="tamper-calibration", destination=destination)
        with self.assertRaises(fv2.FeasibleV2Error):
            m5.load_holdout_prerequisites(config)

        # 变体 4：未跑完 freeze（门禁未解锁）时 holdout 必须拒绝
        root = _new_root()
        config = _variant_config(base_config, root=root, run_id="holdout-before-freeze")
        result = m5.run_holdout_stage(config, workers=1)
        self.assertEqual(result["status"], "PREREGISTRATION_NOT_FROZEN")
        self.assertEqual(result["products_written"], ["summary.json"])
        summary = _read_json(config.run_dir / "summary.json")
        self.assertEqual(summary["status"], "PREREGISTRATION_NOT_FROZEN")
        self.assertFalse((config.run_dir / "metrics").exists())



class M5HoldoutStageTests(unittest.TestCase):
    """holdout 阶段：四方门禁、等预算、null 披露、确定性、物理守卫。"""

    def test_11_holdout_success_gate_and_counts(self) -> None:
        study = _study()
        result = study["holdout"]
        run_dir = Path(result["run_dir"])
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["stage"], "holdout")
        self.assertEqual(result["physical_call_count"], 0)
        self.assertEqual(result["study_scale"], "SMOKE")
        self.assertFalse(result["conclusions_allowed"])
        self.assertEqual(result["groups"], EXPECTED_GROUPS)
        self.assertEqual(result["runs_completed"], EXPECTED_RUNS)
        self.assertEqual(result["true_evaluations"], EXPECTED_EVALUATIONS)
        self.assertEqual(sorted(result["products_written"]), sorted(m5.HOLDOUT_PRODUCT_FILES))
        fairness = result["fairness"]
        self.assertEqual(fairness["status"], "PASS")
        self.assertEqual(fairness["records"], EXPECTED_RUNS)
        self.assertEqual(fairness["initial_design_count"], 8)
        identifiability = result["identifiability"]
        self.assertIn("status", identifiability)
        self.assertEqual(identifiability["physical_call_count"], 0)
        self.assertEqual(
            set(identifiability["arms_present"]),
            set(m5.M5_ARM_ORDER),
        )

        summary = _read_json(run_dir / "summary.json")
        self.assertEqual(summary["status"], "VALID")
        self.assertEqual(summary["gate"]["status"], "UNLOCKED")
        self.assertEqual(summary["physical_call_count"], 0)
        self.assertEqual(summary["physics_guard"]["status"], "PASS")
        self.assertEqual(summary["counts"]["runs"], EXPECTED_RUNS)
        self.assertEqual(summary["counts"]["true_evaluations"], EXPECTED_EVALUATIONS)
        self.assertIn("SYNTHETIC_ONLY", summary["message"])
        self.assertIn("fallback", summary["fallback_metrics_note"])

        run_config = _read_json(run_dir / "run_config.json")
        self.assertEqual(run_config["stage"], "holdout")
        self.assertEqual(run_config["study_scale"], "SMOKE")
        self.assertFalse(run_config["conclusions_allowed"])
        self.assertEqual(run_config["evaluation_splits"], ["meta_test", "meta_test_ood"])
        self.assertEqual(
            [int(v) for v in run_config["budgets"]["true_evaluation_budget"]],
            list(HOLDOUT_BUDGETS),
        )
        self.assertEqual([int(v) for v in run_config["optimization_seeds"]], list(HOLDOUT_SEEDS))
        gate = run_config["preregistration_gate"]
        self.assertEqual(gate["status"], "UNLOCKED")
        self.assertEqual(gate["radius_base"], SELECTED_RADIUS)
        self.assertEqual(gate["split_hash"], _read_json(run_dir / "frozen_family.json")["split"]["split_hash"])
        self.assertEqual(run_config["determinism"]["status"], "PASS")
        self.assertEqual(run_config["counts"]["holdout_groups"], EXPECTED_GROUPS)
        self.assertEqual(run_config["counts"]["history_rows"], EXPECTED_EVALUATIONS)
        self.assertEqual(run_config["products"], list(m5.HOLDOUT_PRODUCT_FILES))
        declaration = run_config["physical_call_declaration"]
        self.assertEqual(declaration["expected"], 0)
        self.assertEqual(declaration["data_origin"], "SYNTHETIC_TEST")
        self.assertIn("fail-closed", declaration["policy"])

    def test_11b_multi_meta_seed_records_not_duplicates(self) -> None:
        """回归：多 meta seed 的模型打分臂记录不得被公平性审计误判为重复组。

        正式 M5 holdout（meta_seeds=(0,1,2)）在 3 个 determinism pass 跑完后曾因
        assert_m5_fairness 以 (task, seed, budget) 为键而抛出“重复组”失败：
        pretrain-init / MAML-init 每 meta seed 各一条记录属预注册设计。修复后
        公平性键包含 meta_seed，且本 tiny 端到端多 meta seed run 必须 VALID。
        """
        study = _study()
        root = _new_root()
        run_id = "m5-multi-meta-holdout"
        holdout_dir = root / run_id
        _prepare_holdout_prerequisites(
            Path(study["calibration_config"].run_dir),
            Path(study["freeze_config"].run_dir),
            holdout_dir,
        )
        base = study["holdout_config"]
        config = replace(
            base,
            output_root=root,
            run_id=run_id,
            meta_seeds=(0, 1),
            calibration_report_path=None,
            frozen_family_path=None,
            preregistration_path=None,
            split_manifest_path=None,
        )
        result = m5.run_holdout_stage(config, workers=1)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["physical_call_count"], 0)
        expected_groups = HOLDOUT_TASKS * len(HOLDOUT_SEEDS)
        expected_runs = expected_groups * len(HOLDOUT_BUDGETS) * (2 + 2 * 2)
        self.assertEqual(result["groups"], expected_groups)
        self.assertEqual(result["runs_completed"], expected_runs)
        fairness = result["fairness"]
        self.assertEqual(fairness["status"], "PASS")
        self.assertEqual(fairness["records"], expected_runs)
        # 键为 (task, seed, budget, meta_seed)：None + 两个 meta seed = 3 个键/组。
        self.assertEqual(fairness["groups"], expected_groups * len(HOLDOUT_BUDGETS) * 3)
        self.assertEqual(fairness["group_key_fields"], ["task_id", "seed", "budget", "meta_seed"])
        summary = _read_json(Path(result["run_dir"]) / "summary.json")
        self.assertEqual(summary["status"], "VALID")
        self.assertEqual(summary["fairness"]["records"], expected_runs)
        self.assertEqual(summary["fairness"]["groups"], fairness["groups"])
        self.assertEqual(sorted(result["products_written"]), sorted(m5.HOLDOUT_PRODUCT_FILES))

    def test_12_products_complete_and_data_manifest(self) -> None:
        run_dir = Path(_study()["holdout"]["run_dir"])
        for name in m5.HOLDOUT_PRODUCT_FILES:
            self.assertTrue((run_dir / name).is_file(), name)
        manifest = _read_json(run_dir / "data_manifest.json")
        self.assertEqual(manifest["hash_mode"], "CRLF->LF")
        self.assertIn("data_manifest.json", manifest["excluded"])
        files = manifest["files"]
        self.assertEqual(manifest["file_count"], len(files))
        self.assertEqual(manifest["total_bytes"], sum(int(item["bytes"]) for item in files))
        self.assertEqual(manifest["file_count"], len([path for path in run_dir.rglob("*") if path.is_file()]) - 1)
        for item in files:
            path = run_dir / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            digest, size = sha256_file_normalized(path)
            self.assertEqual(item["sha256"], digest, item["path"])
            self.assertEqual(int(item["bytes"]), size, item["path"])
        self.assertNotIn("data_manifest.json", [item["path"] for item in files])
        # M5 不产生 M6 的 K-shot 适应数据：该 CSV 只允许表头（不伪造数据）
        adaptation_lines = (run_dir / "metrics" / "adaptation_results.csv").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(adaptation_lines), 1)
        self.assertIn("rmse_norm", adaptation_lines[0])
        self.assertEqual(_read_csv(run_dir / "metrics" / "adaptation_results.csv"), [])
        solver = _read_csv(run_dir / "solver_validation.csv")
        self.assertEqual(len(solver), 3)
        self.assertTrue(all(row["status"] in ("NOT_RUN", "NOT_APPLICABLE_THIS_STAGE") for row in solver))

    def test_13_figure_status_keys_and_no_fake_png(self) -> None:
        run_dir = Path(_study()["holdout"]["run_dir"])
        status_payload = _read_json(run_dir / "figures" / "figure_status.json")
        figures = status_payload["figures"]
        self.assertEqual(set(figures), set(FIGURE_KEYS))
        for name, item in figures.items():
            self.assertIsInstance(item, dict, name)
            self.assertIn(item["status"], ("DATA_READY", "NOT_AVAILABLE", "NOT_RUN", "NOT_APPLICABLE_THIS_STAGE"))
        self.assertEqual(figures["fig1_meta_training_loss"]["status"], "DATA_READY")
        self.assertEqual(figures["fig2_k_shot_adaptation"]["status"], "NOT_APPLICABLE_THIS_STAGE")
        self.assertEqual(figures["fig6_airframe_gate_progress"]["status"], "NOT_RUN")
        for name in ("fig3_feasible_rate", "fig4_equal_budget_gap", "fig5_fairness_audit"):
            self.assertIn(figures[name]["status"], ("DATA_READY", "NOT_AVAILABLE"), name)
        self.assertIn("NOT_RUN", status_payload["note"])
        data = _read_json(run_dir / "figures" / "figure_data.json")
        self.assertEqual(set(data["figures"]), set(FIGURE_KEYS))
        summary = _read_json(run_dir / "summary.json")
        self.assertEqual(set(summary["figures"]), set(FIGURE_KEYS))
        self.assertIn("禁止假图", summary["figures_note"])
        pngs = sorted((run_dir / "figures").glob("*.png"))
        self.assertEqual(pngs, [])

    def test_14_equal_budget_and_initial_designs(self) -> None:
        run_dir = Path(_study()["holdout"]["run_dir"])
        summary_rows = _read_csv(run_dir / "metrics" / "optimization_summary.csv")
        self.assertEqual(len(summary_rows), EXPECTED_RUNS)
        allowed = {VALID_STATUS, NO_FEASIBLE_STATUS, FAILED_STATUS}
        run_keys = set()
        for row in summary_rows:
            budget = int(row["budget"])
            self.assertIn(budget, HOLDOUT_BUDGETS)
            self.assertEqual(int(row["true_evals_used"]), budget, row["arm"])
            self.assertGreaterEqual(int(row["requested_evaluations"]), budget)
            self.assertGreaterEqual(int(row["cache_hits"]), 0)
            self.assertGreaterEqual(int(row["failed_evals"]), 0)
            self.assertIn(row["status"], allowed)
            self.assertTrue(row["initializer"])
            self.assertTrue(row["implementation"])
            self.assertEqual(row["physical_call_count"], "0")
            self.assertTrue(row["reference_objective"])
            run_keys.add((row["arm"], budget, row["task_id"], row["split"], row["seed"]))
        self.assertEqual(len(run_keys), EXPECTED_RUNS)
        self.assertEqual({key[0] for key in run_keys}, set(m5.M5_ARM_ORDER))

        history_rows = _read_csv(run_dir / "metrics" / "optimization_history.csv")
        self.assertEqual(len(history_rows), EXPECTED_EVALUATIONS)
        grouped: dict[tuple[str, ...], list[dict[str, str]]] = {}
        for row in history_rows:
            key = (row["arm"], row["budget"], row["task_id"], row["split"], row["seed"], row["meta_seed"])
            grouped.setdefault(key, []).append(row)
        self.assertEqual(len(grouped), EXPECTED_RUNS)
        for key, rows in grouped.items():
            self.assertEqual(len(rows), int(key[1]), key)
            self.assertEqual([row["initial_design"] for row in rows[:8]], ["true"] * 8, key)
            self.assertEqual([row["initial_design"] for row in rows[8:]], ["false"] * (len(rows) - 8), key)
            self.assertEqual([int(row["eval_index"]) for row in rows], list(range(1, len(rows) + 1)), key)
            self.assertIn(rows[-1]["status"], ("VALID", "INFEASIBLE", "GEOMETRY_INVALID", "NONFINITE"), key)

        arm_rows = _read_csv(run_dir / "metrics" / "arm_audit.csv")
        self.assertEqual(len(arm_rows), EXPECTED_RUNS)
        for row in arm_rows:
            self.assertEqual(int(row["true_evals_used"]), int(row["budget"]))
            self.assertRegex(row["initial_designs_sha256"], r"^[0-9a-f]{64}$")

    def test_15_null_rules_and_fallback_disclosure(self) -> None:
        run_dir = Path(_study()["holdout"]["run_dir"])
        summary_rows = _read_csv(run_dir / "metrics" / "optimization_summary.csv")
        null_feasible = 0
        null_raw = 0
        for row in summary_rows:
            feasible_count = int(row["feasible_count"])
            if feasible_count == 0:
                null_feasible += 1
                # 不可行不得写成 0 / 惩罚常数：必须留空（null）
                self.assertEqual(row["best_feasible_value"], "", row["arm"])
                self.assertEqual(row["gap_to_reference"], "", row["arm"])
                self.assertEqual(row["first_feasible_evaluation_index"], "", row["arm"])
                for key in ("best_feasible_value", "gap_to_reference", "first_feasible_evaluation_index"):
                    self.assertNotEqual(row[key], "0", (row["arm"], key))
            else:
                self.assertTrue(row["best_feasible_value"], row["arm"])
                self.assertTrue(row["first_feasible_evaluation_index"], row["arm"])
            if not row["best_objective_raw"]:
                null_raw += 1
                self.assertEqual(row["min_constraint_violation_sum"], "", row["arm"])
            self.assertIn(row["feasibility_expected_zero"], ("true", "false"))
            self.assertTrue(row["feasible_hit_rate"] or feasible_count == 0)

        summary = _read_json(run_dir / "summary.json")
        disclosure = summary["null_disclosure"]
        self.assertIn("best_feasible_value", disclosure)
        entry = disclosure["best_feasible_value"]
        self.assertEqual(entry["n_runs"], EXPECTED_RUNS)
        self.assertEqual(entry["n_null"], null_feasible)
        self.assertAlmostEqual(entry["null_rate"], null_feasible / EXPECTED_RUNS, places=12)
        self.assertEqual(disclosure["best_objective_raw"]["n_null"], null_raw)
        self.assertEqual(summary["null_disclosure"]["feasible_hit_rate"]["n_runs"], EXPECTED_RUNS)
        # fallback 只能用于描述，不得被当作主终点
        self.assertIn("禁止", summary["fallback_metrics_note"])
        self.assertIn("fallback", summary["fallback_metrics_note"])
        primary = summary["primary_endpoint_summary"]
        self.assertTrue(primary)
        for split_payload in primary.values():
            for budget_payload in split_payload.values():
                for arm_payload in budget_payload.values():
                    self.assertIn("best_feasible_value", arm_payload)
                    self.assertIn("null_rate", arm_payload["best_feasible_value"])

    def test_16_determinism_pass_and_comparison_logic(self) -> None:
        study = _study()
        run_dir = Path(study["holdout"]["run_dir"])
        determinism = study["holdout"]["determinism"]
        self.assertEqual(determinism["status"], "PASS")
        self.assertEqual(int(determinism["reruns"]), 2)
        self.assertEqual(int(determinism["groups_compared"]), EXPECTED_GROUPS)
        self.assertEqual(int(determinism["mismatch_count"]), 0)
        self.assertIn("wall_s", determinism["excluded_columns"])
        self.assertIn("proxy_scoring_cost_json", determinism["excluded_columns"])
        summary = _read_json(run_dir / "summary.json")
        self.assertEqual(summary["determinism"]["status"], "PASS")
        self.assertFalse(summary["conclusions_allowed"])
        # 比较逻辑本身：篡改任一组的摘要必须 FAIL（不得静默通过）
        passes = [
            {"pass": 0, "digests": {"g1": {"history": "a", "summary": "b"}}},
            {"pass": 1, "digests": {"g1": {"history": "a", "summary": "b"}}},
        ]
        same = m5.compare_determinism(passes)
        self.assertEqual(same["status"], "PASS")
        self.assertEqual(same["mismatch_count"], 0)
        passes[1]["digests"]["g1"]["summary"] = "TAMPERED"
        differing = m5.compare_determinism(passes)
        self.assertEqual(differing["status"], "FAIL")
        self.assertEqual(differing["mismatch_count"], 1)
        self.assertEqual(m5.compare_determinism([])["status"], "NOT_RUN")

    def test_17_holdout_determinism_not_run_when_reruns_lt_2(self) -> None:
        study = _study()
        root = _new_root()
        destination = root / "det-rerun-1"
        _copy_prerequisites(Path(study["run_dir"]), destination)
        config = _variant_config(
            study["holdout_config"],
            root=root,
            run_id="det-rerun-1",
            determinism_reruns=1,
        )
        result = m5.run_holdout_stage(config, workers=1)
        self.assertEqual(result["status"], "VALID")
        determinism = result["determinism"]
        self.assertEqual(determinism["status"], "NOT_RUN")
        self.assertEqual(int(determinism["reruns"]), 1)
        self.assertIn("不冒充", determinism["note"])
        self.assertFalse(result["conclusions_allowed"])
        summary = _read_json(destination / "summary.json")
        self.assertEqual(summary["status"], "VALID")
        self.assertEqual(summary["determinism"]["status"], "NOT_RUN")
        self.assertFalse(summary["conclusions_allowed"])
        run_config = _read_json(destination / "run_config.json")
        self.assertEqual(run_config["determinism"]["status"], "NOT_RUN")

    def test_18_physics_guard_aborts_holdout_with_failure_summary(self) -> None:
        study = _study()
        root = _new_root()
        destination = root / "holdout-physics-guard"
        _copy_prerequisites(Path(study["run_dir"]), destination)
        config = _variant_config(study["holdout_config"], root=root, run_id="holdout-physics-guard")
        real_factory = m5.make_synthetic_task_evaluator

        def _tampered_factory(task: object, design_space: object) -> object:
            inner = real_factory(task, design_space)

            def _evaluate(design_u: object) -> dict:
                payload = dict(inner(design_u))
                payload["physical_call_count"] = 1  # 非法：模拟误接真实求解器
                return payload

            _evaluate.physical_call_count = 0  # type: ignore[attr-defined]
            return _evaluate

        with mock.patch.object(m5, "make_synthetic_task_evaluator", _tampered_factory):
            result = m5.run_holdout_stage(config, workers=1)
        self.assertEqual(result["status"], "PHYSICS_GUARD_VIOLATION")
        self.assertEqual(result["products_written"], ["summary.json"])
        self.assertGreaterEqual(int(result["physical_call_count"]), 1)
        summary_path = destination / "summary.json"
        self.assertTrue(summary_path.is_file())
        summary = _read_json(summary_path)
        self.assertEqual(summary["status"], "PHYSICS_GUARD_VIOLATION")
        self.assertEqual(summary["physics_guard"]["status"], "VIOLATED")
        self.assertEqual(int(summary["physical_call_count"]), 1)
        self.assertEqual(summary["products_written"], ["summary.json"])
        self.assertFalse((destination / "metrics").exists())
        self.assertFalse((destination / "optimization_history.csv").exists())
        self.assertFalse((destination / "figures").exists())

class M5OldRunImmutabilityGateTests(unittest.TestCase):
    """F02：旧 48,000 评价 M2 run 不可变性门禁（PASS/FAIL/NOT_AVAILABLE 三态）。"""

    def _fabricate_old_run(self, root: Path, *, tamper: bool = False) -> Path:
        run_dir = root / m5.OLD_M2_RUN_ID
        run_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "metrics/metrics.csv": "arm,budget,value\nOPT-BO-rand,64,1.0\n".encode("utf-8"),
            "summary.json": json.dumps({"status": "VALID", "physical_call_count": 0}, sort_keys=True).encode(
                "utf-8"
            ),
        }
        entries = []
        for rel, data in files.items():
            path = run_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            canonical = data.replace(bytes([13, 10]), bytes([10]))
            entries.append(
                {
                    "path": rel,
                    "hash_mode": "canonical_lf",
                    "bytes": len(canonical),
                    "sha256": m5.hashlib.sha256(canonical).hexdigest(),
                }
            )
        manifest = {
            "schema_version": "2.0.0",
            "file_count": len(entries),
            "total_bytes": sum(int(entry["bytes"]) for entry in entries),
            "files": entries,
        }
        (run_dir / "data_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
        )
        if tamper:
            (run_dir / "summary.json").write_bytes(files["summary.json"].replace(b"VALID", b"TAMPER"))
        return run_dir

    def test_19_gate_pass_and_enforced(self) -> None:
        root = _new_root()
        self._fabricate_old_run(root)
        before = m5.snapshot_old_m2_run(root)
        self.assertEqual(before["status"], "PASS")
        self.assertEqual(int(before["mismatch_count"]), 0)
        config = _tiny_config(root, stage="calibration", run_id="gate-pass")
        gate = m5.prepare_old_run_gate(config, before=before, stage="calibration")
        self.assertEqual(gate["status"], "PASS")
        self.assertTrue(gate["enforced"])
        self.assertEqual(gate["enforcement"], "ENFORCED")
        self.assertTrue((config.run_dir / m5.OLD_RUN_GATE_FILE).is_file())
        m5.assert_old_run_unchanged_after_write(config, gate=gate, stage="calibration")

    def test_20_gate_fail_closed_on_tamper(self) -> None:
        root = _new_root()
        self._fabricate_old_run(root, tamper=True)
        before = m5.snapshot_old_m2_run(root)
        self.assertEqual(before["status"], "FAIL")
        self.assertGreaterEqual(int(before["mismatch_count"]), 1)
        config = _tiny_config(root, stage="calibration", run_id="gate-fail")
        with self.assertRaises(m5.M5RunnerError):
            m5.prepare_old_run_gate(config, before=before, stage="calibration")

    def test_21_gate_not_available_is_disclosed_not_enforced(self) -> None:
        root = _new_root()
        before = m5.snapshot_old_m2_run(root)
        self.assertEqual(before["status"], "NOT_AVAILABLE")
        config = _tiny_config(root, stage="calibration", run_id="gate-na")
        gate = m5.prepare_old_run_gate(config, before=before, stage="calibration")
        self.assertEqual(gate["status"], "NOT_AVAILABLE")
        self.assertFalse(gate["enforced"])
        self.assertEqual(gate["enforcement"], "NOT_ENFORCED_OLD_RUN_UNAVAILABLE")
        payload = _read_json(config.run_dir / m5.OLD_RUN_GATE_FILE)
        self.assertFalse(payload["enforced"])

    def test_22_gate_manifest_change_between_snapshots_fails(self) -> None:
        root = _new_root()
        run_dir = self._fabricate_old_run(root)
        before = m5.snapshot_old_m2_run(root)
        self.assertEqual(before["status"], "PASS")
        manifest_path = run_dir / "data_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["note"] = "changed between snapshots"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        config = _tiny_config(root, stage="calibration", run_id="gate-change")
        with self.assertRaises(m5.M5RunnerError):
            m5.prepare_old_run_gate(config, before=before, stage="calibration")


class M5InferenceExclusionFigureTests(unittest.TestCase):
    """P4R2-F01/F02/F03/F04：clone 臂不得进入 fig3/fig4 与统计比较，fig5 保留全量审计。"""

    CLONE_ARM = m5.M5_BO_PRETRAIN_INIT

    def setUp(self) -> None:
        self.config = _tiny_config(_new_root(), stage="holdout", run_id="m5-fig-exclusion")

    def _summary_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for arm in (m5.M5_BO_RANDOM, self.CLONE_ARM, m5.M5_DE):
            for task_id in ("task-a", "task-b"):
                rows.append(
                    {
                        "arm": arm,
                        "budget": 8,
                        "split": "meta_test",
                        "task_id": task_id,
                        "seed": 0,
                        "best_feasible_value": 1.0,
                        "gap_to_reference": 0.1,
                        "first_feasible_evaluation_index": 2.0,
                        "feasible_hit_rate": 0.5,
                        "best_objective_raw": 1.0,
                        "min_constraint_violation_sum": 0.0,
                        "proxy_scoring_cost_json": '{"wall_s": 0.5}',
                    }
                )
        return rows

    def _curve_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for arm in (m5.M5_BO_RANDOM, self.CLONE_ARM, m5.M5_DE):
            rows.append(
                {
                    "arm": arm,
                    "budget": 8,
                    "split": "meta_test",
                    "task_id": "task-a",
                    "seed": 0,
                    "eval_index": (1, 2),
                    "best_feasible_so_far": (1.0, 0.9),
                    "gap_to_reference_so_far": (0.1, 0.05),
                }
            )
        return rows

    def _arm_audit_rows(self) -> list[dict[str, object]]:
        return [
            {
                "arm": arm,
                "initial_designs_sha256": "sha",
                "code_path": "m5_arms",
                "implementation": "impl",
            }
            for arm in (m5.M5_BO_RANDOM, self.CLONE_ARM, m5.M5_DE)
        ]

    def _figures(self) -> dict[str, object]:
        return m5.build_figure_data(
            config=self.config,
            run_id="m5-fig-exclusion",
            training_rows=(),
            summary_rows=self._summary_rows(),
            curve_rows=self._curve_rows(),
            arm_audit_rows=self._arm_audit_rows(),
            clone_rows=(),
            excluded_arms=(self.CLONE_ARM,),
        )

    def test_01_fig3_and_fig4_exclude_clone_arm_and_fig5_keeps_audit(self) -> None:
        figures = self._figures()
        fig3 = figures["figures"]["fig3_feasible_rate"]["series"]
        fig4 = figures["figures"]["fig4_equal_budget_gap"]["series"]
        self.assertTrue(fig3)
        self.assertTrue(fig4)
        self.assertFalse(any(self.CLONE_ARM in key for key in fig3))
        self.assertFalse(any(self.CLONE_ARM in key for key in fig4))
        self.assertIn(m5.M5_BO_RANDOM, figures["figures"]["fig5_fairness_audit"]["arms"])
        self.assertIn(self.CLONE_ARM, figures["figures"]["fig5_fairness_audit"]["arms"])
        self.assertEqual(figures["excluded_from_inference"], [self.CLONE_ARM])

    def test_02_inference_comparisons_drop_pairs_with_clone_arm(self) -> None:
        kept, dropped = m5.inference_comparisons_excluding_clones(
            m5.PREREGISTERED_COMPARISONS, (self.CLONE_ARM,)
        )
        self.assertTrue(kept)
        self.assertFalse(any(self.CLONE_ARM in pair for pair in kept))
        self.assertEqual(len(kept) + len(dropped), len(m5.PREREGISTERED_COMPARISONS))
        self.assertTrue(dropped)
        for pair in dropped:
            self.assertIn(self.CLONE_ARM, pair)

    def test_03_statistics_rows_have_no_clone_arm_comparison(self) -> None:
        kept, _ = m5.inference_comparisons_excluding_clones(
            m5.PREREGISTERED_COMPARISONS, (self.CLONE_ARM,)
        )
        rows = m5.paired_statistics_rows(self._summary_rows(), budgets=(8,), comparisons=kept)
        self.assertTrue(rows)
        for row in rows:
            self.assertNotEqual(row["arm"], self.CLONE_ARM)
            self.assertNotEqual(row["reference"], self.CLONE_ARM)

    def test_04_de_arm_metadata_matches_actual_code_path(self) -> None:
        from research.concorde_metaopt.meta_learning import m5_arms

        implementation = m5_arms.ARM_IMPLEMENTATIONS[m5_arms.M5_DE]
        self.assertIn("m5_arms.run_m5_de_arm", implementation)
        self.assertIn("baseline_arms.run_de_arm", implementation)
        self.assertNotIn("baseline_de:", implementation)
        self.assertEqual(
            m5_arms.ARM_CODE_PATHS[m5_arms.M5_DE],
            "m5_arms.run_m5_de_arm->baseline_arms.run_de_arm[DE/rand/1/bin]",
        )

class M5EndpointAndCloneColumnRegressionTests(unittest.TestCase):
    """A5-M5-01/02 回归：first_feasible 端点别名与 clone_audit 列非空。

    正式 run 的 summary 行由 ArmResult.to_summary_row 产生（键
    first_feasible_eval_index），而端点/CSV 列名为 first_feasible_evaluation_index；
    修复前该主终点整体读成 null、clone_audit.csv 的 budget/reference 两列全空。
    """

    @staticmethod
    def _rows(*, with_null: bool = False):
        rows = []
        for arm, base in (("M5-BO-random", 1), ("M5-DE", 3)):
            for task_id in ("task-a", "task-b"):
                for seed in (0, 1):
                    value = base + seed
                    rows.append(
                        {
                            "arm": arm,
                            "budget": 8,
                            "split": "meta_test",
                            "task_id": task_id,
                            "seed": seed,
                            "first_feasible_eval_index": value,
                        }
                    )
        if with_null:
            rows[0]["first_feasible_eval_index"] = None
        return rows

    def test_01_endpoint_row_key_alias(self) -> None:
        self.assertEqual(
            m5.endpoint_row_key("first_feasible_evaluation_index"),
            "first_feasible_eval_index",
        )
        self.assertEqual(m5.endpoint_row_key("n_failed_evals"), "failed_evals")
        self.assertEqual(m5.endpoint_row_key("best_feasible_value"), "best_feasible_value")

    def test_02_optimization_summary_rows_backfill_alias(self) -> None:
        rows = [
            {"first_feasible_eval_index": 3, "best_feasible_value": 0.5},
            {"first_feasible_evaluation_index": 7},
            {"best_feasible_value": None},
        ]
        projected = m5.optimization_summary_rows(rows)
        self.assertEqual(projected[0]["first_feasible_evaluation_index"], 3)
        self.assertEqual(projected[1]["first_feasible_evaluation_index"], 7)
        self.assertIsNone(projected[2]["first_feasible_evaluation_index"])

    def test_03_endpoint_summary_and_null_disclosure_use_alias(self) -> None:
        rows = self._rows()
        endpoint_rows = m5.endpoint_summary_rows(
            rows,
            splits=("meta_test",),
            budgets=(8,),
            endpoints=("first_feasible_evaluation_index",),
        )
        by_arm = {row["arm"]: row for row in endpoint_rows}
        self.assertEqual(by_arm["M5-BO-random"]["n_nonnull"], 2)
        self.assertEqual(by_arm["M5-BO-random"]["null_rate"], 0.0)
        self.assertAlmostEqual(by_arm["M5-BO-random"]["median"], 1.5, places=12)
        self.assertAlmostEqual(by_arm["M5-DE"]["median"], 3.5, places=12)

        disclosure = m5._null_disclosure(rows)["first_feasible_evaluation_index"]
        self.assertEqual(disclosure["n_runs"], len(rows))
        self.assertEqual(disclosure["n_null"], 0)
        null_disclosure = m5._null_disclosure(self._rows(with_null=True))
        self.assertEqual(null_disclosure["first_feasible_evaluation_index"]["n_null"], 1)

    def test_04_paired_statistics_use_alias(self) -> None:
        rows = self._rows()
        statistics = m5.paired_statistics_rows(
            rows,
            splits=("meta_test",),
            budgets=(8,),
            comparisons=(("M5-DE", "M5-BO-random"),),
            bootstrap_samples=200,
        )
        feasible_rows = [
            row
            for row in statistics
            if row["endpoint"] == "first_feasible_evaluation_index"
        ]
        self.assertEqual(len(feasible_rows), 1)
        row = feasible_rows[0]
        self.assertEqual(row["arm"], "M5-DE")
        self.assertEqual(row["reference"], "M5-BO-random")
        self.assertEqual(row["n_nonnull"], 2)
        self.assertEqual(row["n_pairs"], 2)
        self.assertAlmostEqual(row["median_diff"], 2.0, places=12)
        self.assertEqual(row["status"], "REPORTED")

    def test_05_clone_audit_rows_fill_reference_and_budget(self) -> None:
        audit_rows = [
            {
                "arm": "M5-BO-MAML-init",
                "reference_arm": "M5-BO-random",
                "budget": "64,128",
                "budget_scope": "aggregate_all_budgets",
                "groups_compared": 6,
                "mean_initial_overlap": 0.25,
                "max_initial_overlap": 0.5,
                "fraction_groups_at_threshold": 0.0,
                "clone": False,
                "label": "IDENTIFIABLE",
            }
        ]
        rows = m5.clone_audit_rows(audit_rows)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["reference"], "M5-BO-random")
        self.assertEqual(row["budget"], "64,128")
        self.assertEqual(row["budget_scope"], "aggregate_all_budgets")
        self.assertEqual(tuple(row.keys()), m5.CLONE_AUDIT_COLUMNS)
        self.assertEqual(len(row), len(m5.CLONE_AUDIT_COLUMNS))
