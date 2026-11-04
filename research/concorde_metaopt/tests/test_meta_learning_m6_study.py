"""P4-M6 快速适应 harness 单元测试（unittest；全部解析合成，不触发真实求解器）。

覆盖 Issue #5 D-P4-002 / 设计文档 §12 中与 M6 相关的检查：
- 三臂 R/P/M × K∈{0,1,5,10,20} 的 K-shot 矩阵可跑通，原始值与任务内标准化值都保留；
- OOD H1-H5 诊断结构、负控制 label-shuffle 协议、三层结论严格分离；
- 确定性重跑（排除 wall_s）与 SMOKE 不得下结论；
- physical_call_count=0 fail-closed、禁止真实求解器 import；
- 产物齐全且 data_manifest 的 sha256/bytes 与磁盘一致。
"""
from __future__ import annotations

import csv
import json
import math
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research.concorde_metaopt.meta_learning import adaptation as adaptation_module
from research.concorde_metaopt.meta_learning import feasible_v2 as fv2
from research.concorde_metaopt.meta_learning import m6_frozen
from research.concorde_metaopt.meta_learning import m6_study as m6
from research.concorde_metaopt.meta_learning import offline_runner as orun
from research.concorde_metaopt.meta_learning import task_family as tf
from research.concorde_metaopt.meta_learning.baseline_arms import PhysicsGuardViolation


_TMP_ROOT = Path(tempfile.mkdtemp(prefix="p4m6-test-"))
_RUN_CACHE: dict[str, object] = {}


def tearDownModule() -> None:
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


FROZEN_RADIUS = 0.75
_GATE: dict[str, object] = {}


def _calibration_config() -> fv2.CalibrationConfig:
    return fv2.CalibrationConfig(
        radius_grid=(FROZEN_RADIUS,),
        opt_seeds=(0,),
        train_tasks=2,
        validation_tasks=1,
        budget=8,
        family_seed=20261102,
        empirical_samples=16,
    )


def _fake_calibration_report(*, radius: float = FROZEN_RADIUS) -> fv2.CalibrationReport:
    """构造真实结构 + 真实 sha 的假校准报告（避免测试跑真实校准）。"""
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
        selected_radius_base=float(radius),
        selection_status="SELECTED",
        selection_rule=fv2.SELECTION_RULE,
        notes=("M6 单元测试假校准报告（非真实校准证据）",),
        physical_call_count=0,
    )


def _frozen_gate_dir() -> Path:
    """构造 tiny v2 冻结三件套（frozen_family / split manifest / preregistration）。"""
    if "dir" in _GATE:
        return Path(_GATE["dir"])
    gate_dir = _TMP_ROOT / "frozen-run"
    gate_dir.mkdir(parents=True, exist_ok=True)
    calibration = _calibration_config()
    family_config = fv2.calibration_family_config(FROZEN_RADIUS, calibration)
    tasks = tf.build_task_family(family_config)
    split_manifest = fv2.build_split_manifest(tasks, family_config=family_config)
    report = _fake_calibration_report()
    frozen = fv2.build_frozen_family(
        family_config,
        split_manifest=split_manifest,
        calibration_report=report,
        run_id="m6-frozen-fixture",
        git_sha="TEST",
    )
    preregistration = fv2.build_preregistration(
        frozen,
        run_id="m6-frozen-fixture",
        optimization_seeds=tuple(range(10)),
        meta_seeds=(0, 1, 2),
    )
    fv2.write_frozen_family(gate_dir / "frozen_family.json", frozen)
    orun.write_json(gate_dir / "meta_task_split.json", split_manifest)
    fv2.write_preregistration(gate_dir / "preregistration.json", preregistration, frozen)
    _GATE.update(
        dir=gate_dir,
        frozen=frozen,
        split_manifest=split_manifest,
        preregistration=preregistration,
        family_config=family_config,
    )
    return gate_dir


def _gate() -> m6_frozen.FrozenGate:
    """加载 tiny 冻结门禁（真实校验路径，非 mock）。"""
    return m6_frozen.load_frozen_gate(frozen_run_dir=_frozen_gate_dir())


def _tiny_config(output_root: Path | None = None, run_id: str = "test-m6-e2e", **overrides) -> m6.M6RunnerConfig:
    """tiny 规模配置：2/1/2/1/1 任务、support 8 / query 4、K={0,1,5}、1 个 meta seed。"""
    kwargs: dict[str, object] = {
        "run_id": run_id,
        "output_root": Path(output_root or (_TMP_ROOT / "runs")),
        "train_family": m6.TRAIN_FAMILY,
        "frozen_run_dir": _frozen_gate_dir(),
        "new_families": ("F-LIN", "F-MF"),
        "ks": (0, 1, 5),
        "meta_seeds": (0,),
        "max_meta_steps": 3,
        "inner_steps": 4,
        "train_tasks": 2,
        "validation_tasks": 1,
        "test_tasks": 2,
        "ood_tasks": 1,
        "negative_control_tasks": 1,
        "support_pool_size": 8,
        "query_size": 4,
        "determinism_reruns": 2,
    }
    kwargs.update(overrides)
    return m6.M6RunnerConfig(**kwargs)  # type: ignore[arg-type]


def _read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


def _shared_run() -> tuple[m6.M6RunnerConfig, dict]:
    """整个模块只跑一次端到端 M6（tiny SMOKE），后续测试复用结果。"""
    if "run" not in _RUN_CACHE:
        config = _tiny_config()
        result = m6.run_m6_study(config)
        _RUN_CACHE["config"] = config
        _RUN_CACHE["run"] = result
    return _RUN_CACHE["config"], _RUN_CACHE["run"]  # type: ignore[return-value]


class M6ConfigTests(unittest.TestCase):
    """M6RunnerConfig 规模判定与 fail-closed 校验。"""

    def test_smoke_config_scale_and_conclusions(self) -> None:
        config = _tiny_config()
        self.assertEqual(config.study_scale, "SMOKE")
        self.assertFalse(config.conclusions_allowed)
        payload = config.to_dict()
        self.assertEqual(payload["split_counts"]["meta_train"], 2)
        self.assertEqual(payload["designs_per_task"], 12)
        self.assertEqual(payload["physical_guard_expected"], 0)
        self.assertEqual(payload["ks"], [0, 1, 5])
        self.assertFalse(payload["conclusions_allowed"])

    def test_formal_config_scale(self) -> None:
        config = _tiny_config(
            run_id="test-formal",
            ks=(0, 1, 5, 10, 20),
            meta_seeds=(0, 1, 2),
            max_meta_steps=200,
            train_tasks=60,
            validation_tasks=20,
            test_tasks=20,
            ood_tasks=10,
            negative_control_tasks=10,
            support_pool_size=128,
            query_size=64,
        )
        self.assertEqual(config.study_scale, "FORMAL")
        self.assertTrue(config.conclusions_allowed)

    def test_formal_requires_three_meta_seeds(self) -> None:
        config = _tiny_config(
            run_id="test-formal-2",
            ks=(0, 1, 5, 10, 20),
            meta_seeds=(0, 1),
            max_meta_steps=200,
            train_tasks=60,
            validation_tasks=20,
            test_tasks=20,
            ood_tasks=10,
            negative_control_tasks=10,
            support_pool_size=128,
            query_size=64,
        )
        # 元训练 seed 不足 3 个 -> 只能算 SMOKE，不允许下结论（前序压缩块中的教训）
        self.assertEqual(config.study_scale, "SMOKE")
        self.assertFalse(config.conclusions_allowed)

    def test_config_rejects_invalid(self) -> None:
        invalid_overrides = [
            {"run_id": "bad/run"},
            {"run_id": ""},
            {"train_family": "F-QQ"},
            {"new_families": ("F-LIN", m6.TRAIN_FAMILY)},
            {"new_families": ("F-LIN", "F-LIN")},
            {"ks": (1, 5)},
            {"ks": (0, 5, 1)},
            {"ks": (0, 5, 5)},
            {"ks": (-1, 0)},
            {"support_pool_size": 4},
            {"physical_guard_expected": 1},
            {"determinism_reruns": 0},
            {"test_tasks": 0},
            {"train_tasks": 0},
            {"meta_seeds": (0, 0)},
            # A5M6-09：显式省略的 K 不得与 ks 冲突
            {"k_omissions": (0,)},
            {"k_omissions": (20, 20)},
        ]
        base = {
            "run_id": "test-config",
            "output_root": _TMP_ROOT / "runs",
            "frozen_run_dir": _frozen_gate_dir(),
            "ks": (0, 1, 5),
            "meta_seeds": (0,),
            "train_tasks": 2,
            "validation_tasks": 1,
            "test_tasks": 2,
            "ood_tasks": 1,
            "negative_control_tasks": 1,
            "support_pool_size": 8,
            "query_size": 4,
        }
        for override in invalid_overrides:
            with self.subTest(override=override):
                kwargs = dict(base)
                kwargs.update(override)
                with self.assertRaises(m6.M6Error):
                    m6.M6RunnerConfig(**kwargs)  # type: ignore[arg-type]

    def test_m6_constants_contract(self) -> None:
        self.assertEqual(m6.M6_ARMS, ("M", "P", "R"))
        self.assertEqual(m6.M6_METHODS, {"M": "maml", "P": "fine_tuning", "R": "from_scratch"})
        for k_shot in (0, 1, 5, 10, 20):
            self.assertIn(k_shot, m6.M6_KS)
        self.assertEqual(m6.MIN_TASKS_FOR_STATS, 5)
        self.assertEqual(len({m6.L1_LAYER, m6.L2_LAYER, m6.L3_LAYER}), 3)
        for row in m6.SOLVER_VALIDATION_ROWS:
            self.assertIn(row["status"], {"NOT_RUN", "NOT_APPLICABLE_THIS_STAGE"})
        self.assertEqual(m6.PHYSICAL_CALL_COUNT, 0)


class M6DatasetTests(unittest.TestCase):
    """任务族构建、split 计数、跨族 task_id 互斥与评估单元组成。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _tiny_config(run_id="test-datasets")
        cls.gate = _gate()
        cls.datasets = m6.build_m6_datasets(cls.config, gate=cls.gate)

    def test_dataset_split_counts(self) -> None:
        train_family = self.datasets[m6.TRAIN_FAMILY]
        counts = {split: len(tasks) for split, tasks in train_family["splits"].items()}
        self.assertEqual(counts["meta_train"], 2)
        self.assertEqual(counts["meta_validation"], 1)
        self.assertEqual(counts["meta_test"], 2)
        self.assertEqual(counts["meta_test_ood"], 1)
        self.assertEqual(counts["negative_control"], 1)
        for family_id in ("F-LIN", "F-MF"):
            family = self.datasets[family_id]
            self.assertEqual(len(family["splits"]["meta_test"]), 2)
            self.assertEqual(len(family["splits"]["meta_train"]), 0)
            self.assertEqual(len(family["splits"]["meta_train"]), 0)

    def test_task_ids_globally_unique(self) -> None:
        task_ids: list[str] = []
        for family in self.datasets.values():
            task_ids.extend(task.task_id for task in family["tasks"])
        self.assertEqual(len(task_ids), len(set(task_ids)))

    def test_study_units_composition(self) -> None:
        units = m6.study_units(self.config, self.datasets)
        counts = {study: 0 for study in m6.STUDY_ORDER}
        for unit in units:
            counts[unit["study"]] += 1
            self.assertIn(unit["study"], m6.STUDY_ORDER)
            self.assertTrue(unit["task"].task_id)
        self.assertEqual(counts["in_dist"], 2)
        self.assertEqual(counts["ood"], 1)
        self.assertEqual(counts["new_family"], 4)
        self.assertEqual(counts["negative_control"], 1)
        order = [m6.STUDY_ORDER.index(unit["study"]) for unit in units]
        self.assertEqual(order, sorted(order))

    def test_cross_family_duplicate_task_id_rejected(self) -> None:
        tasks = list(self.datasets[m6.TRAIN_FAMILY]["tasks"])
        with mock.patch.object(m6.tf, "build_task_family", side_effect=[tasks[:2], tasks[:2]]):
            with self.assertRaises(m6.M6Error):
                m6.build_m6_datasets(self.config, gate=self.gate)

    def test_frozen_gate_seed_and_family_are_gating(self) -> None:
        # A5M6-01：训练族必须是冻结 v2；错误 family / seed 必须在构建数据集前 fail-closed
        with self.assertRaises(m6.M6Error):
            m6.build_m6_family_configs(
                _tiny_config(run_id="test-wrong-family", train_family="F-LIN"), self.gate
            )
        with self.assertRaises(m6_frozen.M6FrozenGateError):
            m6.build_m6_family_configs(
                _tiny_config(run_id="test-wrong-seed", family_seed=123), self.gate
            )

    def test_formal_scale_rejects_nonfrozen_counts(self) -> None:
        # A5M6-01：FORMAL 规模必须与冻结 split 一致，不得用缩小任务集冒充正式结论
        with self.assertRaises(m6_frozen.M6FrozenGateError):
            m6_frozen.family_config_for_m6(
                self.gate,
                train_tasks=60,
                validation_tasks=20,
                test_tasks=20,
                ood_tasks=10,
                negative_control_tasks=10,
                support_pool_size=128,
                query_size=64,
                family_seed=int(self.gate.family_config.seed),
                full_scale=True,
            )

class M6EndToEndTests(unittest.TestCase):
    """tiny SMOKE 端到端：产物、确定性、诊断结构与标准化保留。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config, cls.study_result = _shared_run()

    def test_run_status_and_physical_guard(self) -> None:
        run = self.study_result
        self.assertEqual(run["status"], "VALID")
        self.assertEqual(run["physical_call_count"], 0)
        self.assertEqual(run["study_scale"], "SMOKE")
        self.assertFalse(run["conclusions_allowed"])
        summary = run["summary"]
        self.assertEqual(summary["physics_guard"]["status"], "PASS")
        self.assertEqual(summary["physical_call_count"], 0)
        self.assertEqual(summary["evaluator_id"], m6.EVALUATOR_ID)
        self.assertEqual(summary["data_origin"], "SYNTHETIC_TEST")
        self.assertIn("SYNTHETIC_ONLY", summary["message"])
        self.assertEqual(len(summary["not_approved"]), 3)
        # 8 个评估单元 × 3 个 K × 1 个 meta seed × 3 臂 = 72 次适应（纯解析，无真实评价）
        self.assertEqual(summary["counts"]["evaluation_units"], 8)
        self.assertEqual(summary["counts"]["adaptation_runs"], 72)
        self.assertEqual(summary["counts"]["adaptation_rows"], 72)
        # A5M6-11：adaptation_runs 是 pass0 行数；实际执行次数须含确定性重跑
        self.assertEqual(summary["counts"]["determinism_passes"], 2)
        self.assertEqual(summary["counts"]["total_adaptation_executions"], 144)
        self.assertEqual(summary["counts"]["nonfinite_rows"], 0)
        # A5M6-01/02：冻结门禁与旧 run 门禁必须出现在 summary
        self.assertEqual(summary["frozen_gate"]["status"], "PASS")
        self.assertEqual(summary["frozen_gate"]["family_id"], m6.TRAIN_FAMILY)
        self.assertEqual(summary["frozen_gate"]["radius_base"], FROZEN_RADIUS)
        self.assertEqual(summary["frozen_split_verification"]["status"], "NOT_APPLICABLE_SMOKE")
        self.assertIn(summary["old_run_gate"]["status"], {"PASS", "NOT_AVAILABLE"})

    def test_products_complete_and_manifest_consistent(self) -> None:
        run_dir = Path(self.study_result["run_dir"])
        for relative in m6.M6_PRODUCT_FILES:
            self.assertTrue((run_dir / relative).is_file(), relative)
        # A5M6-02：冻结三件套逐字节副本 + 门禁摘要
        for relative in (
            "gate/frozen_family.json",
            "gate/preregistration.json",
            "gate/meta_task_split.json",
            "gate/frozen_gate.json",
            "old_m2_run_immutability.json",
        ):
            self.assertTrue((run_dir / relative).is_file(), relative)
        gate_payload = _read_json(run_dir / "gate" / "frozen_gate.json")
        self.assertEqual(gate_payload["status"], "PASS")
        self.assertEqual(gate_payload["physical_call_count"], 0)
        self.assertEqual(
            gate_payload["gate_directory"]["files"]["frozen_family"]["sha256"],
            gate_payload["frozen_family_sha256"],
        )
        old_run = _read_json(run_dir / "old_m2_run_immutability.json")
        self.assertEqual(old_run["gate"], "OLD_M2_RUN_IMMUTABILITY")
        self.assertIn(old_run["status"], {"PASS", "NOT_AVAILABLE"})
        self.assertIn("enforced", old_run)
        for relative in (
            "run_config.json",
            "environment.json",
            "tasks.json",
            "reference_solutions.json",
            "meta_task_split.json",
            "determinism_check.json",
            "figures/figure_data.json",
            "figures/figure_status.json",
            "summary.json",
        ):
            self.assertIsInstance(_read_json(run_dir / relative), dict)
        manifest = _read_json(run_dir / "data_manifest.json")
        self.assertEqual(manifest["hash_mode"], "CRLF->LF")
        self.assertIn("data_manifest.json", manifest["excluded"])
        actual = sorted(
            path.relative_to(run_dir).as_posix()
            for path in run_dir.rglob("*")
            if path.is_file() and path.name != "data_manifest.json"
        )
        self.assertEqual(sorted(entry["path"] for entry in manifest["files"]), actual)
        self.assertEqual(manifest["file_count"], len(actual))
        for entry in manifest["files"]:
            digest, _normalized = orun.sha256_file_normalized(run_dir / entry["path"])
            self.assertEqual(entry["sha256"], digest, entry["path"])
            self.assertEqual(entry["bytes"], (run_dir / entry["path"]).stat().st_size, entry["path"])

    def test_determinism_passed_with_two_reruns(self) -> None:
        determinism = self.study_result["summary"]["determinism"]
        self.assertEqual(determinism["status"], "PASS")
        self.assertEqual(determinism["reruns"], 2)
        self.assertEqual(determinism["distinct_digests"], 1)
        self.assertEqual(len(set(determinism["digests"])), 1)
        self.assertIn("wall_s", determinism["excluded_columns"])
        disk = _read_json(Path(self.study_result["run_dir"]) / "determinism_check.json")
        self.assertEqual(disk["status"], "PASS")
        self.assertEqual(disk["physical_call_count"], 0)

    def test_negative_control_small_sample_is_inconclusive(self) -> None:
        negative = self.study_result["summary"]["negative_control"]
        checks = {check["id"]: check for check in negative["checks"]}
        self.assertEqual(set(checks), {"NC1", "NC2"})
        # tiny 规模只有 1 个负控制任务 < MIN_TASKS_FOR_STATS：如实 INCONCLUSIVE，不误判泄漏
        self.assertEqual(checks["NC1"]["status"], "INCONCLUSIVE")
        evidence = checks["NC1"]["evidence"]
        self.assertEqual(evidence["min_paired_tasks"], m6.MIN_TASKS_FOR_STATS)
        self.assertIn("small_sample_rule", evidence)
        self.assertEqual(negative["physical_call_count"], 0)
        self.assertIn("禁止进入主终点", negative["note"])

    def test_ood_diagnostics_structure(self) -> None:
        diagnostics = self.study_result["summary"]["ood_diagnostics"]
        self.assertIn(diagnostics["status"], {"PASS", "CONFOUNDED", "INSUFFICIENT_SPLITS"})
        self.assertEqual(diagnostics["conclusion_allowed"], diagnostics["status"] == "PASS")
        if diagnostics["status"] != "INSUFFICIENT_SPLITS":
            ids = [check["id"] for check in diagnostics["checks"]]
            self.assertEqual(ids, ["H1", "H2", "H3", "H4", "H5"])
        self.assertEqual(self.study_result["summary"]["physical_call_count"], 0)
        tolerances = diagnostics["tolerances"]
        self.assertEqual(tolerances["confound_relative_difference"], m6.CONFOUND_TOLERANCE)
        self.assertEqual(tolerances["ood_context_shift"], m6.OOD_STRONG_SHIFT)
        # A5M6-04：必须给出逐任务难度协变量表与匹配结果
        self.assertEqual(
            sorted({row["split"] for row in diagnostics["difficulty_table"]}),
            ["meta_test", "meta_test_ood"],
        )
        matching = diagnostics["difficulty_matching"]
        self.assertIn(matching["status"], {"MATCHED", "POOR_MATCH", "INSUFFICIENT_TASKS", "NOT_AVAILABLE"})
        if matching["status"] != "NOT_AVAILABLE":
            self.assertIn("matching_keys", matching)
            self.assertIn("max_abs_imbalance", matching)
            self.assertIn("metric_deltas", matching)
        self.assertIn("attribution_rule", diagnostics)

    def test_three_layer_conclusions_separated(self) -> None:
        conclusions = self.study_result["summary"]["three_layer_conclusions"]
        self.assertEqual(set(conclusions["layers"]), {m6.L1_LAYER, m6.L2_LAYER, m6.L3_LAYER})
        self.assertTrue(conclusions["cross_layer_inference_forbidden"])
        self.assertIn("禁止", conclusions["separation"])
        l2 = conclusions["layers"][m6.L2_LAYER]
        self.assertEqual(l2["status"], "NOT_EVALUATED_IN_M6")
        self.assertEqual(l2["m5_reference"]["status"], "PENDING_M5_HOLDOUT")
        l1 = conclusions["layers"][m6.L1_LAYER]
        self.assertIn(l1["status"], {"SIGNIFICANT_ADVANTAGE", "NO_SIGNIFICANT_ADVANTAGE", "INCONCLUSIVE"})
        l3 = conclusions["layers"][m6.L3_LAYER]
        self.assertIn(
            l3["status"],
            {
                "OOD_ADVANTAGE_OBSERVED_CONDITIONAL",
                "OOD_ADVANTAGE_NOT_ATTRIBUTABLE",
                "OOD_NO_SIGNIFICANT_ADVANTAGE",
                "INCONCLUSIVE",
            },
        )
        self.assertEqual(l3["diagnostics_status"], self.study_result["summary"]["ood_diagnostics"]["status"])
        # A5M6-06：L3 必须同时报告 OOD 与新函数族分层
        self.assertTrue(l3["reports_both_ood_and_new_family"])
        self.assertTrue(conclusions["l3_reports_both_layers"])
        self.assertIn(
            l3["new_family_status"],
            {"NEW_FAMILY_ADVANTAGE_OBSERVED", "NO_SIGNIFICANT_ADVANTAGE", "INCONCLUSIVE"},
        )
        self.assertTrue(l3["combined_status"])
        self.assertEqual(
            l3["difficulty_matching_status"],
            self.study_result["summary"]["ood_diagnostics"]["difficulty_matching"]["status"],
        )
        self.assertIn("attribution_gate", l3)

    def test_figures_data_ready_and_no_fake_png(self) -> None:
        run_dir = Path(self.study_result["run_dir"])
        status = _read_json(run_dir / "figures" / "figure_status.json")
        self.assertEqual(status["status"], "PARTIAL")
        self.assertEqual(status["figures"]["fig1_meta_training_loss"], "READY")
        self.assertEqual(status["figures"]["fig2_k_shot_adaptation"], "READY")
        for name in (
            "fig3_feasible_rate",
            "fig4_equal_budget_gap",
            "fig5_fairness_audit",
            "fig6_airframe_gate_progress",
        ):
            self.assertEqual(status["figures"][name], "NOT_RUN")
        self.assertEqual(list((run_dir / "figures").glob("*.png")), [])
        # A5M6-10：六图 preflight 必须显式声明规范图键
        self.assertEqual(tuple(status["canonical_figures"]), m6.M6_CANONICAL_FIGURES)
        self.assertEqual(status["missing_canonical_figures"], [])
        self.assertEqual(status["preflight"]["status"], "PASS")
        figure_data = _read_json(run_dir / "figures" / "figure_data.json")
        fig1 = figure_data["figures"]["fig1_meta_training_loss"]
        self.assertEqual(fig1["status"], "READY")
        self.assertIn("meta0-M", fig1["series"])
        self.assertIn("meta0-P", fig1["series"])
        series = fig1["series"]["meta0-M"]
        self.assertEqual(series["x"], sorted(series["x"]))
        fig2 = figure_data["figures"]["fig2_k_shot_adaptation"]
        self.assertEqual(fig2["status"], "READY")
        self.assertTrue(fig2["rows"])
        degradation = fig2["degradation_diagnostic"]
        for metric in ("rmse_raw", "rmse_norm"):
            self.assertIn(metric, degradation)
            self.assertIn("ood_over_in_dist_ratio", degradation[metric])

    def test_standardization_keeps_raw_and_normalized(self) -> None:
        run_dir = Path(self.study_result["run_dir"])
        header, rows = _read_csv_rows(run_dir / "metrics" / "adaptation_results.csv")
        self.assertEqual(tuple(header), m6.ADAPTATION_RESULT_COLUMNS)
        self.assertEqual(len(rows), 72)
        for row in rows:
            for key in ("rmse_raw", "rmse_norm", "mae_raw", "mae_norm"):
                self.assertNotEqual(row[key], "", key)
                self.assertTrue(math.isfinite(float(row[key])), key)
            self.assertEqual(row["status"], "VALID")
        by_family: dict[str, list[float]] = {}
        for row in rows:
            by_family.setdefault(row["source_family"], []).append(float(row["rmse_raw"]))
        self.assertEqual(set(by_family), {m6.TRAIN_FAMILY, "F-LIN", "F-MF"})
        medians = {family: _median(values) for family, values in by_family.items()}
        # 不同族原始目标尺度不同（原始值必须保留、不得混合比较）；标准化值另行给出
        self.assertGreater(len({round(value, 6) for value in medians.values()}), 1)
        # metrics.csv 每个任务的 per_task 行同时保留 raw 与 norm
        _m_header, metrics_rows = _read_csv_rows(run_dir / "metrics" / "metrics.csv")
        per_task = [row for row in metrics_rows if row["aggregation"] == "per_task"]
        self.assertTrue(per_task)
        seen: dict[tuple[str, str, str, str], set[str]] = {}
        for row in per_task:
            self.assertTrue(row["task_id"])
            seen.setdefault((row["study"], row["task_id"], row["arm"], row["K"]), set()).add(row["metric"])
        for key, metric_names in seen.items():
            self.assertEqual(metric_names, {"rmse_raw", "rmse_norm"}, key)
        group_rows = [row for row in metrics_rows if row["aggregation"] == "group_mean"]
        self.assertTrue(group_rows)
        self.assertIn("rmse_norm", {row["metric"] for row in group_rows})

    def test_run_config_and_readme(self) -> None:
        run_dir = Path(self.study_result["run_dir"])
        run_config = _read_json(run_dir / "run_config.json")
        self.assertEqual(run_config.get("study_scale"), "SMOKE")
        self.assertFalse(run_config.get("conclusions_allowed", False))
        self.assertEqual(run_config.get("physical_call_count"), 0)
        self.assertTrue(run_config.get("not_approved"))
        environment = _read_json(run_dir / "environment.json")
        self.assertEqual(environment["physical_call_count"], 0)
        self.assertEqual(environment["data_origin"], "SYNTHETIC_TEST")
        readme = (run_dir / "README.md").read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC_ONLY", readme)
        self.assertIn("physical_call_count = 0", readme)
        self.assertIn("conclusions_allowed=False", readme)

    def test_smoke_scale_never_allows_conclusions(self) -> None:
        self.assertFalse(self.config.conclusions_allowed)
        self.assertFalse(self.study_result["summary"]["conclusions_allowed"])
        self.assertEqual(self.study_result["summary"]["study_scale"], "SMOKE")


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    size = len(ordered)
    if size % 2:
        return ordered[size // 2]
    return 0.5 * (ordered[size // 2 - 1] + ordered[size // 2])


def _stats_row(**overrides) -> dict:
    base = {
        "study": "in_dist",
        "source_family": m6.TRAIN_FAMILY,
        "arm": "M",
        "reference": "R",
        "K": 5,
        "metric": "rmse_norm",
        "n_pairs": 20,
        "median_diff": -1.0,
        "mean_diff": -1.0,
        "status": "VALID",
    }
    base.update(overrides)
    return base


def _summary_row(arm: str, mean: float, *, study: str = "in_dist", k_shot: int = 0) -> dict:
    return {
        "study": study,
        "source_family": m6.TRAIN_FAMILY,
        "arm": arm,
        "K": k_shot,
        "metric": "rmse_norm",
        "mean": mean,
        "median": mean,
        "status": "VALID",
    }


class M6DiagnosticsUnitTests(unittest.TestCase):
    """负控制/统计/确定性函数的边界与阈值。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _tiny_config(run_id="test-unit")

    def test_nc1_small_sample_guard(self) -> None:
        summary_rows = [
            _summary_row("M", 1.0),
            _summary_row("P", 2.0),
            _summary_row("R", 3.0),
        ]
        invisible = m6.negative_control_check(self.config, [], summary_rows)
        nc1 = invisible["checks"][0]
        self.assertEqual(nc1["status"], "INCONCLUSIVE")
        self.assertEqual(invisible["status"], "INCONCLUSIVE")

        # 配对任务数不足（行本身 INSUFFICIENT_TASKS）：不得判泄漏
        insufficient = [
            _stats_row(),
            _stats_row(study="negative_control", n_pairs=1, status="INSUFFICIENT_TASKS", median_diff=-0.1),
        ]
        result = m6.negative_control_check(self.config, insufficient, summary_rows)
        self.assertEqual(result["checks"][0]["status"], "INCONCLUSIVE")
        self.assertEqual(result["checks"][0]["evidence"]["paired_tasks"], 1)

    def test_nc1_thresholds(self) -> None:
        summary_rows = [
            _summary_row("M", 1.0),
            _summary_row("P", 2.0),
            _summary_row("R", 3.0),
        ]
        # control 优势 = 0.2 <= 0.5 * in_dist 优势 1.0 -> PASS
        pass_rows = [_stats_row(), _stats_row(study="negative_control", median_diff=-0.2)]
        self.assertEqual(m6.negative_control_check(self.config, pass_rows, summary_rows)["checks"][0]["status"], "PASS")
        # control 优势 = 0.9 > 0.5 -> FAIL（label-shuffle 后优势未回落，须查泄漏）
        fail_rows = [_stats_row(), _stats_row(study="negative_control", median_diff=-0.9)]
        failed = m6.negative_control_check(self.config, fail_rows, summary_rows)
        self.assertEqual(failed["checks"][0]["status"], "FAIL")
        self.assertEqual(failed["status"], "FAIL")

    def test_nc2_random_arm_worst(self) -> None:
        summary_rows = [
            _summary_row("M", 1.0),
            _summary_row("P", 1.2),
            _summary_row("R", 2.0),
        ]
        result = m6.negative_control_check(self.config, [], summary_rows)
        nc2 = {check["id"]: check for check in result["checks"]}["NC2"]
        self.assertEqual(nc2["status"], "PASS")
        # 随机臂不是最差 -> FAIL
        bad_rows = [
            _summary_row("M", 3.0),
            _summary_row("P", 1.2),
            _summary_row("R", 1.0),
        ]
        bad = m6.negative_control_check(self.config, [], bad_rows)
        self.assertEqual({check["id"]: check for check in bad["checks"]}["NC2"]["status"], "FAIL")

    def test_holm_bonferroni(self) -> None:
        adjusted = m6.holm_bonferroni([0.001, 0.02, 0.5])
        self.assertAlmostEqual(adjusted[0][0], 0.003)
        self.assertAlmostEqual(adjusted[1][0], 0.04)
        self.assertAlmostEqual(adjusted[2][0], 0.5)
        self.assertEqual([reject for _p, reject in adjusted], [True, True, False])
        self.assertEqual(m6.holm_bonferroni([]), [])
        self.assertEqual(m6.holm_bonferroni([None]), [(None, None)])
        self.assertEqual(m6.holm_bonferroni([None, 0.01]), [(None, None), (0.01, True)])

    def test_paired_comparison_rows_valid(self) -> None:
        rows = []
        for index in range(6):
            for meta_seed in (0, 1):
                rows.append(
                    {
                        "study": "in_dist",
                        "source_family": "F-QE",
                        "arm": "M",
                        "K": 5,
                        "task_id": f"task-{index}",
                        "meta_seed": meta_seed,
                        "rmse_norm": 1.0 + 0.05 * index,
                    }
                )
                rows.append(
                    {
                        "study": "in_dist",
                        "source_family": "F-QE",
                        "arm": "R",
                        "K": 5,
                        "task_id": f"task-{index}",
                        "meta_seed": meta_seed,
                        "rmse_norm": 1.5,
                    }
                )
        stats = m6.paired_comparison_rows(
            self.config, rows, metrics=("rmse_norm",), comparisons=(("M", "R"),)
        )
        self.assertEqual(len(stats), 1)
        row = stats[0]
        self.assertEqual(row["n_pairs"], 6)
        self.assertAlmostEqual(row["median_diff"], -0.375, places=12)
        self.assertEqual(row["status"], "VALID")
        self.assertIsNotNone(row["p_holm"])
        self.assertEqual(row["reject_holm"], True)
        self.assertGreaterEqual(row["p_holm"], row["wilcoxon_pvalue"])

    def test_paired_comparison_rows_holm_scope(self) -> None:
        # 两个 (study, 族, K, 指标) 家族各 2 个比较：Holm 在家族内校正，p_holm = 2 * p
        rows = []
        for study in ("in_dist", "ood"):
            for family in ("F-QE", "F-LIN"):
                for index in range(6):
                    for arm, value in (("M", 1.0 + 0.1 * index), ("P", 1.3), ("R", 1.6)):
                        rows.append(
                            {
                                "study": study,
                                "source_family": family,
                                "arm": arm,
                                "K": 5,
                                "task_id": f"{study}-{family}-{index}",
                                "meta_seed": 0,
                                "rmse_norm": value,
                            }
                        )
        stats = m6.paired_comparison_rows(
            self.config, rows, metrics=("rmse_norm",), comparisons=(("M", "P"), ("M", "R"))
        )
        self.assertEqual(len(stats), 8)
        for row in stats:
            self.assertIsNotNone(row["p_holm"])
        # 每个家族内只有 2 个比较 -> 校正因子至多 2（受下界 1.0 限制）
        for row in stats:
            self.assertLessEqual(row["p_holm"], min(1.0, 2.0 * row["wilcoxon_pvalue"]) + 1e-12)

    def test_adaptation_summary_inconclusive_on_null_rate(self) -> None:
        base = {
            "run_id": self.config.run_id,
            "study": "in_dist",
            "source_family": "F-QE",
            "arm": "M",
            "K": 5,
            "meta_seed": 0,
            "rmse_norm": 1.0,
            "rmse_raw": 1.0,
            "mae_raw": 1.0,
            "mae_norm": 1.0,
            "r2": 0.0,
            "max_abs_err": 1.0,
            "loss_final": 1.0,
            "loss_std": 0.0,
            "loss_monotonic_fraction": 1.0,
            "wall_s": 0.0,
        }
        rows = []
        for index in range(4):
            row = dict(base, task_id=f"task-{index}")
            if index >= 2:
                row["rmse_norm"] = None
            rows.append(row)
        summary = m6.adaptation_summary_rows(self.config, rows)
        rmse_norm_rows = [row for row in summary if row["metric"] == "rmse_norm"]
        self.assertEqual(len(rmse_norm_rows), 1)
        self.assertEqual(rmse_norm_rows[0]["status"], "INCONCLUSIVE")
        self.assertEqual(rmse_norm_rows[0]["n_nonnull"], 2)
        # 全部为 null 的指标标 MISSING，不补假值
        for row in rows:
            row["mae_raw"] = None
        summary = m6.adaptation_summary_rows(self.config, rows)
        mae_rows = [row for row in summary if row["metric"] == "mae_raw"]
        self.assertEqual(mae_rows[0]["status"], "MISSING")
        self.assertIsNone(mae_rows[0]["mean"])

    def test_determinism_check_statuses(self) -> None:
        single = m6.determinism_check(self.config, [{"digest": "a", "artifact_sha256": {}}])
        self.assertEqual(single["status"], "NOT_RUN")
        self.assertEqual(single["reruns"], 1)
        self.assertIn("未做独立重跑", single["note"])
        same = m6.determinism_check(
            self.config,
            [
                {"digest": "a", "artifact_sha256": {"0": {"M": "x"}}},
                {"digest": "a", "artifact_sha256": {"0": {"M": "x"}}},
            ],
        )
        self.assertEqual(same["status"], "PASS")
        different = m6.determinism_check(
            self.config,
            [{"digest": "a", "artifact_sha256": {}}, {"digest": "b", "artifact_sha256": {}}],
        )
        self.assertEqual(different["status"], "FAIL")
        self.assertEqual(different["distinct_digests"], 2)


class M6FrozenGateTests(unittest.TestCase):
    """A5M6-01/02/03：冻结 v2 家族门禁、未冻结 fail-closed、旧 run 不可变门禁。"""

    def test_default_config_requires_frozen_inputs(self) -> None:
        with self.assertRaises(m6.M6Error):
            m6.M6RunnerConfig(run_id="test-no-gate", output_root=_TMP_ROOT / "no-gate")

    def test_missing_frozen_inputs_fail_closed(self) -> None:
        config = _tiny_config(
            output_root=_TMP_ROOT / "missing-gate-runs",
            run_id="test-missing-gate",
            frozen_run_dir=_TMP_ROOT / "does-not-exist",
        )
        with self.assertRaises(m6_frozen.M6FrozenGateError):
            m6.run_m6_study(config)
        summary = _read_json(config.run_dir / "summary.json")
        self.assertEqual(summary["status"], "PREREGISTRATION_NOT_FROZEN")
        self.assertEqual(summary["products_written"], ["summary.json"])

    def test_tampered_frozen_family_rejected(self) -> None:
        tampered = _TMP_ROOT / "tampered-gate"
        if tampered.exists():
            shutil.rmtree(tampered)
        shutil.copytree(_frozen_gate_dir(), tampered)
        payload = _read_json(tampered / "frozen_family.json")
        payload["sha256"] = "0" * 64
        orun.write_json(tampered / "frozen_family.json", payload)
        config = _tiny_config(
            output_root=_TMP_ROOT / "tampered-runs",
            run_id="test-tampered-gate",
            frozen_run_dir=tampered,
        )
        with self.assertRaises(m6_frozen.M6FrozenGateError):
            m6.run_m6_study(config)
        summary = _read_json(config.run_dir / "summary.json")
        self.assertEqual(summary["status"], "PREREGISTRATION_NOT_FROZEN")

    def test_old_run_gate_recorded_and_not_available_is_honest(self) -> None:
        _config, study = _shared_run()
        run_dir = Path(study["run_dir"])
        payload = _read_json(run_dir / "old_m2_run_immutability.json")
        self.assertEqual(payload["physical_call_count"], 0)
        self.assertTrue(payload["read_only"])
        if payload["status"] == "NOT_AVAILABLE":
            self.assertFalse(payload["enforced"])
            self.assertIn("NOT_ENFORCED", payload["enforcement"])

    def test_assert_old_run_unchanged_returns_status(self) -> None:
        gate = m6_frozen.begin_old_run_gate(_TMP_ROOT / "old-run-root", _TMP_ROOT / "old-run-root" / "run")
        report = m6_frozen.assert_old_run_unchanged(_TMP_ROOT / "old-run-root", gate)
        self.assertIn(report["status"], {"PASS", "NOT_AVAILABLE"})
        self.assertEqual(report["physical_call_count"], 0)


class M6EffectSizeTests(unittest.TestCase):
    """A5M6-05：P-R 第三对预注册比较 + Cohen d / rank-biserial 效应量。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _tiny_config(run_id="test-effects")

    def _rows(self) -> list[dict]:
        rows = []
        for index in range(6):
            for arm, value in (("M", 1.0 + 0.05 * index), ("P", 1.2), ("R", 1.6)):
                rows.append(
                    {
                        "study": "in_dist",
                        "source_family": m6.TRAIN_FAMILY,
                        "arm": arm,
                        "K": 5,
                        "task_id": f"task-{index}",
                        "meta_seed": 0,
                        "rmse_norm": value,
                    }
                )
        return rows

    def test_default_comparisons_include_p_r_and_effect_sizes(self) -> None:
        stats = m6.paired_comparison_rows(self.config, self._rows(), metrics=("rmse_norm",))
        pairs = {(row["arm"], row["reference"]) for row in stats}
        self.assertEqual(pairs, {("M", "P"), ("M", "R"), ("P", "R")})
        for row in stats:
            self.assertIn("cohens_d", row)
            self.assertIn("rank_biserial", row)
        mr = next(row for row in stats if (row["arm"], row["reference"]) == ("M", "R"))
        self.assertLess(mr["cohens_d"], 0.0)
        self.assertLess(mr["rank_biserial"], 0.0)

    def test_effect_size_helpers(self) -> None:
        effect = m6._effect_sizes([-1.0, -2.0, -3.0])
        self.assertAlmostEqual(effect["rank_biserial"], -1.0)
        self.assertLess(effect["cohens_d"], 0.0)
        self.assertEqual(m6._effect_sizes([5.0]), {"cohens_d": None, "rank_biserial": None})

    def test_holm_family_scales_with_three_comparisons(self) -> None:
        stats = m6.paired_comparison_rows(self.config, self._rows(), metrics=("rmse_norm",))
        for row in stats:
            self.assertIsNotNone(row["p_holm"])
            self.assertLessEqual(row["p_holm"], min(1.0, 3.0 * row["wilcoxon_pvalue"]) + 1e-12)


class M6OodMatchingUnitTests(unittest.TestCase):
    """A5M6-04：逐任务难度匹配与匹配集误差差。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _tiny_config(run_id="test-ood-match")

    @staticmethod
    def _row(task_id: str, split: str, value: float) -> dict:
        return {
            "task_id": task_id,
            "split": split,
            "family": m6.TRAIN_FAMILY,
            "query_objective_std": value,
            "mean_curvature": 1.0,
            "radius": 0.75,
            "context_shift_norm": 0.1,
        }

    def test_matched_when_difficulty_identical(self) -> None:
        table = [
            self._row("t1", "meta_test", 1.0),
            self._row("t2", "meta_test", 2.0),
            self._row("o1", "meta_test_ood", 1.0),
        ]
        matching = m6._match_ood_to_indist(table)
        self.assertEqual(matching["status"], "MATCHED")
        self.assertEqual(matching["n_pairs"], 1)
        self.assertEqual(matching["pairs"][0]["ood_task_id"], "o1")
        self.assertAlmostEqual(matching["max_abs_imbalance"], 0.0)

    def test_poor_match_when_shifted_far(self) -> None:
        table = [
            self._row("t1", "meta_test", 1.0),
            self._row("t2", "meta_test", 2.0),
            self._row("o1", "meta_test_ood", 50.0),
        ]
        matching = m6._match_ood_to_indist(table)
        self.assertEqual(matching["status"], "POOR_MATCH")
        self.assertGreater(matching["max_abs_imbalance"], matching["tolerance"])

    def test_matched_metric_deltas(self) -> None:
        pairs = [{"ood_task_id": "o1", "in_dist_task_id": "t1"}]
        rows = [
            {"task_id": "o1", "arm": "M", "K": 5, "rmse_raw": 2.0, "rmse_norm": 2.0},
            {"task_id": "t1", "arm": "M", "K": 5, "rmse_raw": 1.0, "rmse_norm": 1.0},
            {"task_id": "o1", "arm": "R", "K": 5, "rmse_raw": 4.0, "rmse_norm": 4.0},
            {"task_id": "t1", "arm": "R", "K": 5, "rmse_raw": 3.0, "rmse_norm": 3.0},
        ]
        deltas = m6._matched_metric_deltas(rows, pairs)
        self.assertEqual(deltas["status"], "COMPUTED")
        self.assertAlmostEqual(deltas["metrics"]["rmse_norm"]["M"]["mean_delta"], 1.0)
        self.assertAlmostEqual(deltas["metrics"]["rmse_norm"]["R"]["mean_delta"], 1.0)
        self.assertEqual(deltas["n_pairs"], 1)


class M6StatusPropagationTests(unittest.TestCase):
    """A5M6-08/09/11：非有限传播、K=20 预注册省略、实际执行次数。"""

    def test_summary_status_propagates_nonfinite_and_determinism(self) -> None:
        self.assertEqual(
            m6._summary_status({"status": "VALID", "rows": [{"status": "NONFINITE"}]}, {"status": "PASS"}),
            "VALID_WITH_NONFINITE",
        )
        self.assertEqual(
            m6._summary_status({"status": "VALID_WITH_NONFINITE", "rows": []}, {"status": "PASS"}),
            "VALID_WITH_NONFINITE",
        )
        self.assertEqual(
            m6._summary_status({"status": "VALID", "rows": []}, {"status": "FAIL"}),
            "DETERMINISM_FAILED",
        )
        self.assertEqual(m6._summary_status({"status": "VALID", "rows": []}, {"status": "PASS"}), "VALID")

    def test_k20_requirement_or_explicit_omission(self) -> None:
        formal_values = dict(
            ks=(0, 1, 5, 10),
            meta_seeds=(0, 1, 2),
            max_meta_steps=200,
            train_tasks=60,
            validation_tasks=20,
            test_tasks=20,
            ood_tasks=10,
            negative_control_tasks=10,
            support_pool_size=128,
            query_size=64,
        )
        without = _tiny_config(run_id="test-k20-missing", **formal_values)
        self.assertEqual(without.study_scale, "SMOKE")
        with_omission = _tiny_config(run_id="test-k20-omitted", k_omissions=(20,), **formal_values)
        self.assertEqual(with_omission.study_scale, "FORMAL")
        self.assertEqual(with_omission.to_dict()["k_omissions"], [20])


class M6FailClosedTests(unittest.TestCase):
    """物理守卫、真实求解器隔离与失败落盘（fail-closed）。"""

    @classmethod
    def setUpClass(cls) -> None:
        _shared_run()

    def test_forbidden_imports_absent(self) -> None:
        baseline = orun._forbidden_modules_present()
        report = orun.assert_no_forbidden_modules(baseline)
        self.assertEqual(report["forbidden_modules_loaded"], [])
        self.assertEqual(report["source_scan_violations"], [])
        source = Path(m6.__file__).read_text(encoding="utf-8")
        pattern = re.compile(r"^\s*(?:from|import)\s+(?:RCAIDE|SU2|VSPAERO|OpenVSP|openvsp|Gmsh|gmsh|su2)\b", re.MULTILINE)
        self.assertEqual(pattern.findall(source), [])

    def test_physics_guard_violation_aborts_run(self) -> None:
        config = _tiny_config(output_root=_TMP_ROOT / "guard", run_id="test-m6-guard")
        with mock.patch.object(
            adaptation_module,
            "adapt_and_predict",
            side_effect=PhysicsGuardViolation("注入物理守卫违规（测试）", physical_call_count=1),
        ):
            with self.assertRaises(PhysicsGuardViolation):
                m6.run_m6_study(config)
        run_dir = config.run_dir
        summary = _read_json(run_dir / "summary.json")
        self.assertEqual(summary["status"], "PHYSICS_GUARD_VIOLATION")
        self.assertEqual(summary["physical_call_count"], 1)
        self.assertEqual(summary["physics_guard"]["status"], "VIOLATED")
        self.assertNotIn("metrics", [path.name for path in run_dir.iterdir()])
        self.assertEqual(
            summary["products_written"],
            ["summary.json"],
        )

    def test_failure_summary_written_for_generic_error(self) -> None:
        config = _tiny_config(output_root=_TMP_ROOT / "failure", run_id="test-m6-failure")
        with mock.patch.object(m6, "build_m6_datasets", side_effect=m6.M6Error("注入失败（测试）")):
            with self.assertRaises(m6.M6Error):
                m6.run_m6_study(config)
        summary = _read_json(config.run_dir / "summary.json")
        self.assertEqual(summary["status"], "FAILED")
        self.assertIn("注入失败", summary["error"]["message"])
        self.assertIsNone(summary["physical_call_count"])


# ---------------------------------------------------------------------------
# A5M6R-01：正式规模 preflight（真实执行计数，禁止配置层面的“声称”）
# ---------------------------------------------------------------------------
_FORMAL_GATE: dict[str, object] = {}


def _formal_family_config() -> tf.TaskFamilyConfig:
    """正式规模 v2 冻结族配置（与 M5 冻结产物同规模：60/20/20/10/10，support128/query64）。"""
    return tf.TaskFamilyConfig(
        family_id=tf.V2_FAMILY_ID,
        design_dim=tf.DESIGN_DIM,
        context_names=tf.CONTEXT_NAMES,
        seed=20261102,
        train_tasks=60,
        validation_tasks=20,
        test_tasks=20,
        ood_tasks=10,
        negative_control_tasks=10,
        designs_per_task=192,
        support_pool_size=128,
        query_size=64,
        family_version="v2",
        radius_base=FROZEN_RADIUS,
    )


def _formal_gate_dir() -> Path:
    """构造正式规模 v2 冻结三件套（真实 TaskFamilyConfig/真实冻结校验路径）。"""
    if "dir" in _FORMAL_GATE:
        return Path(_FORMAL_GATE["dir"])
    gate_dir = _TMP_ROOT / "frozen-formal"
    gate_dir.mkdir(parents=True, exist_ok=True)
    family_config = _formal_family_config()
    tasks = tf.build_task_family(family_config)
    split_manifest = fv2.build_split_manifest(tasks, family_config=family_config)
    report = _fake_calibration_report()
    frozen = fv2.build_frozen_family(
        family_config,
        split_manifest=split_manifest,
        calibration_report=report,
        run_id="m6-formal-fixture",
        git_sha="TEST",
    )
    preregistration = fv2.build_preregistration(
        frozen,
        run_id="m6-formal-fixture",
        optimization_seeds=tuple(range(10)),
        meta_seeds=(0, 1, 2),
    )
    fv2.write_frozen_family(gate_dir / "frozen_family.json", frozen)
    orun.write_json(gate_dir / "meta_task_split.json", split_manifest)
    fv2.write_preregistration(gate_dir / "preregistration.json", preregistration, frozen)
    _FORMAL_GATE.update(
        dir=gate_dir,
        frozen=frozen,
        split_manifest=split_manifest,
        preregistration=preregistration,
        family_config=family_config,
        tasks=tasks,
    )
    return gate_dir


def _formal_config(run_id: str = "test-m6-formal", output_root: Path | None = None) -> m6.M6RunnerConfig:
    """正式规模 M6 配置（冻结门禁、K=0/1/5/10/20、3 个 meta seed、3 次确定性重跑）。"""
    return m6.M6RunnerConfig(
        run_id=run_id,
        output_root=Path(output_root or (_TMP_ROOT / "runs")),
        train_family=m6.TRAIN_FAMILY,
        frozen_run_dir=_formal_gate_dir(),
        new_families=("F-LIN", "F-MF"),
        ks=m6.M6_KS,
        meta_seeds=(0, 1, 2),
        max_meta_steps=200,
        inner_steps=m6.S_ADAPT,
        train_tasks=60,
        validation_tasks=20,
        test_tasks=20,
        ood_tasks=10,
        negative_control_tasks=10,
        support_pool_size=128,
        query_size=64,
        determinism_reruns=3,
    )


def _preflight_artifacts_stub(config: m6.M6RunnerConfig, datasets, *, progress=None):
    """用未训练占位参数替换真实 M/N 训练（只暴露执行计数，不用于结论）。"""
    return m6._preflight_standin_artifacts(config)


def _fake_scale_plan() -> dict:
    """构造与预注册常量一致的正式规模计划（供门禁单测使用）。"""
    units = [{"study": name} for name, count in m6.FORMAL_EXPECTED_UNITS_BY_STUDY.items() for _ in range(count)]
    return {
        "units_by_study": dict(m6.FORMAL_EXPECTED_UNITS_BY_STUDY),
        "units_total": len(units),
        "rows_per_pass": len(units) * len(m6.M6_KS) * 3 * len(m6.M6_ARMS),
        "determinism_passes": 3,
        "total_adaptation_executions": 10800,
        "runs_per_budget": 8,
        "expected": {
            "units_by_study": dict(m6.FORMAL_EXPECTED_UNITS_BY_STUDY),
            "units_total": m6.FORMAL_EXPECTED_UNITS_TOTAL,
            "rows_per_pass": m6.FORMAL_EXPECTED_ROWS_PER_PASS,
            "determinism_passes": m6.FORMAL_EXPECTED_DETERMINISM_PASSES,
            "total_adaptation_executions": m6.FORMAL_EXPECTED_TOTAL_EXECUTIONS,
            "runs_per_budget": m6.FORMAL_EXPECTED_RUNS_PER_BUDGET,
        },
    }


class M6FormalScalePreflightTests(unittest.TestCase):
    """A5M6R-01：正式规模 preflight 必须由实际执行（80 units / 3600 行每 pass / 3 pass = 10800）生成。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _formal_config()
        counter: dict[str, int] = {"calls": 0}
        cls.counter = counter
        mock_adapt = m6._preflight_mock_adapt(counter)
        with mock.patch.object(m6, "build_m6_artifacts", side_effect=_preflight_artifacts_stub):
            with mock.patch.object(adaptation_module, "adapt_and_predict", mock_adapt):
                cls.result = m6.run_m6_study(cls.config)
        cls.summary = cls.result["summary"]
        cls.run_dir = Path(cls.result["run_dir"])
        cls.preflight = _read_json(cls.run_dir / "preflight" / "formal_scale_preflight.json")

    def test_plan_units_and_runs_per_budget(self) -> None:
        plan = self.preflight["plan"]
        self.assertEqual(
            plan["units_by_study"],
            {"in_dist": 20, "ood": 10, "new_family": 40, "negative_control": 10},
        )
        self.assertEqual(plan["units_total"], 80)
        self.assertEqual(plan["rows_per_pass"], 3600)
        self.assertEqual(plan["runs_per_budget"], 8)
        self.assertEqual(plan["determinism_passes"], 3)
        self.assertEqual(plan["total_adaptation_executions"], 10800)
        self.assertEqual(self.preflight["plan_gate"]["status"], "PASS")
        self.assertEqual(self.preflight["plan_gate"]["n_checks"], 10)
        self.assertTrue(all(self.preflight["plan_gate"]["requirements"].values()))

    def test_executed_counts_from_real_loop(self) -> None:
        executed = self.preflight["executed"]
        self.assertEqual(executed["rows_per_pass"], 3600)
        self.assertEqual(executed["determinism_passes"], 3)
        self.assertEqual(executed["total_adaptation_executions"], 10800)
        # 正常 run 不传 mock 计数（只有 dry-run 才传）；mock 适应函数确实被调用了 10800 次
        self.assertIsNone(self.preflight["mock_adaptation_calls"])
        self.assertEqual(self.counter["calls"], 10800)
        self.assertEqual(self.preflight["status"], "PASS")
        self.assertFalse(self.preflight["dry_run"])
        self.assertEqual(self.preflight["mismatches"], [])
        self.assertEqual(self.preflight["physical_call_count"], 0)

    def test_summary_propagates_preflight_and_counts(self) -> None:
        counts = self.summary["counts"]
        self.assertEqual(counts["evaluation_units"], 80)
        self.assertEqual(counts["adaptation_runs"], 3600)
        self.assertEqual(counts["adaptation_rows"], 3600)
        self.assertEqual(counts["determinism_passes"], 3)
        self.assertEqual(counts["total_adaptation_executions"], 10800)
        preflight = self.summary["scale_preflight"]
        self.assertEqual(preflight["status"], "PASS")
        self.assertEqual(preflight["executed"]["rows_per_pass"], 3600)
        self.assertEqual(preflight["executed"]["total_adaptation_executions"], 10800)
        self.assertEqual(preflight["plan"]["units_total"], 80)
        self.assertEqual(self.summary["frozen_split_verification"]["status"], "PASS")
        self.assertEqual(self.summary["physical_call_count"], 0)
        product = self.run_dir / "preflight" / "formal_scale_preflight.json"
        self.assertTrue(product.exists())
        self.assertIn("preflight/formal_scale_preflight.json", m6.M6_PRODUCT_FILES)
        self.assertEqual(self.result["scale_preflight"]["units_total"], 80)

    def test_documented_formal_command_has_required_args(self) -> None:
        readme = (self.run_dir / "README.md").read_text(encoding="utf-8")
        self.assertIn("--frozen-run-dir", readme)
        self.assertIn("--old-run-output-root", readme)
        self.assertIn("--preflight-only", readme)
        self.assertIn("--ks 0,1,5,10,20", readme)
        self.assertIn("--meta-seeds 0,1,2", readme)
        self.assertIn("--determinism-reruns 3", readme)
        # 文档命令必须能在不写产物的情况下做 dry-run（完整命令见 rev2 回执/EXT 证据）
        self.assertIn("m6_study", readme)


class M6FormalScaleFailClosedTests(unittest.TestCase):
    """A5M6R-01/A5M6R-04：计数漂移 fail-closed 与逐族聚合规则。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _formal_config(run_id="test-m6-formal-failclosed")

    def test_plan_gate_passes_for_formal_config(self) -> None:
        units = [{"study": name} for name, count in m6.FORMAL_EXPECTED_UNITS_BY_STUDY.items() for _ in range(count)]
        plan = m6.formal_scale_plan(self.config, units)
        gate = m6._assert_formal_scale_plan(self.config, plan)
        self.assertEqual(gate["status"], "PASS")

    def test_plan_drift_fails_closed(self) -> None:
        # 负控：把预注册行数常量改成 3599，真实计划 3600 必须 fail-closed（该断言在测试内可复现）
        with mock.patch.object(m6, "FORMAL_EXPECTED_ROWS_PER_PASS", 3599):
            drift_plan = _fake_scale_plan()
            with self.assertRaises(m6.M6Error):
                m6._assert_formal_scale_plan(self.config, drift_plan)
            self.assertEqual(
                drift_plan["rows_per_pass"], m6.FORMAL_EXPECTED_ROWS_PER_PASS + 1
            )

    def test_scale_preflight_detects_executed_row_drift(self) -> None:
        plan = _fake_scale_plan()
        gate = {"status": "PASS", "n_checks": 10}
        with self.assertRaises(m6.M6Error):
            m6._build_scale_preflight(self.config, plan, gate, [3600, 3599, 3600])

    def test_k20_omission_declaration(self) -> None:
        config = _tiny_config(
            run_id="test-m6-k20",
            ks=(0, 1, 5, 10),
            k_omissions=(20,),
            support_pool_size=64,
            query_size=16,
        )
        self.assertEqual(config.to_dict()["k_omissions"], [20])
        with self.assertRaises(m6.M6Error):
            _tiny_config(run_id="test-m6-k20-bad", k_omissions=(5,))

    def test_new_family_per_family_status_and_aggregation(self) -> None:
        rows = [
            _stats_row(study="new_family", source_family="F-LIN", median_diff=-1.0, reject_holm=True),
            _stats_row(study="new_family", source_family="F-MF", median_diff=0.2, reject_holm=False),
        ]
        conclusions = {
            "layers": {
                m6.L3_LAYER: {"status": "OOD_NO_SIGNIFICANT_ADVANTAGE"},
            }
        }
        payload = m6.attach_new_family_layer(
            self.config,
            stats_rows=rows,
            conclusions=conclusions,
            ood_diagnostic={"difficulty_matching": {"status": "MATCHED"}},
        )
        l3 = payload["layers"][m6.L3_LAYER]
        self.assertEqual(l3["new_family_status"], "PER_FAMILY_MIXED")
        self.assertEqual(
            {item["source_family"]: item["status"] for item in l3["new_family_per_family_status"]},
            {"F-LIN": "NEW_FAMILY_ADVANTAGE_OBSERVED", "F-MF": "NO_SIGNIFICANT_ADVANTAGE"},
        )
        self.assertIn("禁止以最后一个族", l3["new_family_aggregation_rule"])
        self.assertEqual(l3["combined_status"], "NEW_FAMILY_MIXED")
