# -*- coding: utf-8 -*-
"""P4-M5：F-QE-feasible-v2 校准/冻结/预注册协议的单元测试（全合成，physical=0）。

覆盖：v2 公式与参考解证书（u*=c、严格 margin>0、KKT=0）、校准选择规则
（只用 meta_train、seeds=(0,1,2)、pooled 30–70%）、split manifest 冻结、
frozen_family 必填字段与篡改检测、preregistration 绑定、holdout 门禁、
旧 F-QE fingerprint 逐位不变回归。
"""
from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from unittest import mock

from research.concorde_metaopt.meta_learning import feasible_v2 as fv
from research.concorde_metaopt.meta_learning import task_family as tf

# 旧 F-QE 默认配置的 family fingerprint（P4 v1 冻结常量，任何改动都是回归）
OLD_F_QE_FINGERPRINT = "f4afd17512558277fd898e2b2b5c19f00d15b9b0e8618126ce3876b2c3b7c4e2"


def make_v2_config(radius: float = 0.80, **overrides):
    """小型 v2 任务族配置（测试用，规模可覆盖全部五 split）。"""
    payload = dict(
        family_id=tf.V2_FAMILY_ID,
        design_dim=12,
        context_names=("context_1", "context_2"),
        seed=20261102,
        train_tasks=2,
        validation_tasks=1,
        test_tasks=2,
        ood_tasks=1,
        negative_control_tasks=1,
        designs_per_task=12,
        support_pool_size=8,
        query_size=4,
        family_version="v2",
        radius_base=float(radius),
    )
    payload.update(overrides)
    return tf.TaskFamilyConfig(**payload)


def make_calibration_cell(radius: float, pooled_success: float = 0.333, **overrides):
    payload = dict(
        radius_base=float(radius),
        success_rate_by_seed=(0.25, 0.25, 0.50),
        feasible_hit_rate_by_seed=(0.05, 0.04, 0.06),
        success_rate_median=0.25,
        feasible_hit_rate_median=0.05,
        pooled_success_train=float(pooled_success),
        pooled_hit_rate_train=0.05,
        validation_success_rate_median=0.0,
        all_seeds_in_acceptance=True,
        analytic_sphere_fraction=fv.analytic_sphere_fraction(radius),
        analytic_ellipsoid_fraction_median=0.02,
        feasible_volume_fraction=0.0123,
        n_tasks=5,
        budget=64,
        evaluations=15,
        n_null=0,
        wall_s=0.01,
    )
    payload.update(overrides)
    return fv.CalibrationCell(**payload)


def make_calibration_report(radius: float = 0.80, *, cohorts=None, cells=None, rows=()):
    calibration = fv.CalibrationConfig(
        radius_grid=(float(radius),),
        opt_seeds=(0, 1, 2),
        train_tasks=2,
        validation_tasks=1,
        budget=64,
        empirical_samples=16,
    )
    if cells is None:
        cells = (make_calibration_cell(radius),)
    if cohorts is None:
        cohorts = (
            {
                "radius_base": float(radius),
                "task_ids": {
                    "meta_train": ["train-a", "train-b"],
                    "meta_validation": ["val-a"],
                },
            },
        )
    return fv.CalibrationReport(
        schema_version=fv.CALIBRATION_SCHEMA_VERSION,
        created_utc="2026-11-04T00:00:00+00:00",
        calibration=calibration,
        cells=tuple(cells),
        rows=tuple(rows),
        cohorts=tuple(cohorts),
        reference_certificates=(),
        selected_radius_base=float(radius),
        selection_status="SELECTED",
        selection_rule=fv.SELECTION_RULE,
        notes=("unit-test",),
    )


class _FakeObservation:
    def __init__(self, objective, constraints=None):
        self.objective = objective
        self.constraints = constraints or {}


class _FakeArmResult:
    """最小 ArmResult 替身：只实现校准读取的字段。"""

    def __init__(self, *, success: bool, budget: int, physical_call_count: int = 0):
        self.feasible_count = 2 if success else 0
        self.first_feasible_eval_index = 1 if success else None
        self.best_feasible_value = -0.5 if success else None
        self.wall_s = 0.0
        self.observations = [
            _FakeObservation(0.5 if success else None, {}) for _ in range(budget)
        ]
        self._physical = physical_call_count

    def to_dict(self):
        return {"physical_call_count": self._physical}


def _fake_bo(success_fn, *, physical_call_count: int = 0):
    """构造可控 run_bo_arm 替身：success_fn(call_index)->bool。"""

    def fake_run_bo_arm(arm, evaluate, *, task_id, split, family, seed, budget, reference_objective=None, **kwargs):
        index = fake_run_bo_arm.calls
        fake_run_bo_arm.calls += 1
        return _FakeArmResult(
            success=bool(success_fn(index)), budget=budget, physical_call_count=physical_call_count
        )

    fake_run_bo_arm.calls = 0
    return fake_run_bo_arm


class FamilyVersionTests(unittest.TestCase):
    def test_01_old_f_qe_fingerprint_unchanged(self):
        """旧 F-QE（v1）fingerprint 逐位不变：v2 扩展不得改动 v1 路径。"""
        fingerprint = tf.family_fingerprint(tf.default_task_family_config())
        self.assertEqual(fingerprint, OLD_F_QE_FINGERPRINT)

    def test_02_v2_fingerprint_independent_of_v1(self):
        v1 = tf.default_task_family_config()
        v2 = make_v2_config(0.80)
        self.assertNotEqual(tf.family_fingerprint(v1), tf.family_fingerprint(v2))
        self.assertNotEqual(
            tf.family_fingerprint(v2), tf.family_fingerprint(make_v2_config(0.95))
        )

    def test_03_v2_config_requires_version_and_radius(self):
        with self.assertRaises(tf.TaskFamilyError):
            make_v2_config(0.80, family_version="v1")
        with self.assertRaises(tf.TaskFamilyError):
            make_v2_config(0.80, radius_base=None)
        with self.assertRaises(tf.TaskFamilyError):
            make_v2_config(0.80, radius_base=9.0)
        with self.assertRaises(tf.TaskFamilyError):
            tf.default_task_family_config(family_version="v1", radius_base=0.8)


class ReferenceCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = make_v2_config(0.80)
        cls.tasks = tuple(tf.build_task_family(cls.config))

    def test_04_reference_is_center_with_strict_margin(self):
        tasks = [task for task in self.tasks if not task.is_negative_control]
        certificates = fv.assert_reference_certificates(tasks)
        self.assertEqual(len(certificates), len(tasks))
        for task in tasks:
            reference = task.reference()
            self.assertEqual(reference["reference_kind"], "ANALYTIC_RADIAL_PROJECTION")
            np.testing.assert_allclose(
                np.asarray(reference["u_star"], dtype=float),
                np.asarray(task.params["c"], dtype=float),
                atol=1e-12,
            )
            certificate = certificates[task.task_id]
            self.assertGreater(certificate["min_margin"], 0.0)
            self.assertTrue(np.isfinite(certificate["objective_star"]))
            self.assertAlmostEqual(certificate["kkt_residual"], 0.0, places=12)

    def test_05_non_strict_margin_rejected(self):
        class BrokenTask:
            task_id = "broken-margin"
            params = {"c": [0.5] * 12}

            def reference(self):
                return {
                    "u_star": [0.5] * 12,
                    "objective_star": 1.0,
                    "reference_kind": "ANALYTIC_RADIAL_PROJECTION",
                    "constraints": {"synth_c01": 0.0},
                    "kkt_residual": 0.0,
                }

        with self.assertRaises(fv.FeasibleV2Error):
            fv.assert_reference_certificates([BrokenTask()])

    def test_06_reference_not_center_rejected(self):
        class OffCenterTask:
            task_id = "off-center"
            params = {"c": [0.5] * 12}

            def reference(self):
                return {
                    "u_star": [0.5] * 11 + [0.6],
                    "objective_star": 1.0,
                    "reference_kind": "ANALYTIC_RADIAL_PROJECTION",
                    "constraints": {"synth_c01": -0.1},
                    "kkt_residual": 0.0,
                }

        with self.assertRaises(fv.FeasibleV2Error):
            fv.assert_reference_certificates([OffCenterTask()])

    def test_04b_negative_control_certificate_rejected(self):
        negative = [task for task in self.tasks if task.is_negative_control]
        self.assertTrue(negative)
        with self.assertRaises(fv.FeasibleV2Error):
            fv.assert_reference_certificates(negative)

    def test_07_validation_of_calibration_splits(self):
        fv.assert_calibration_only([task for task in self.tasks if task.split in fv.CALIBRATION_SPLITS])
        test_task = next(task for task in self.tasks if task.split == "meta_test")
        with self.assertRaises(fv.FeasibleV2Error):
            fv.assert_calibration_only([test_task])


class CalibrationConfigTests(unittest.TestCase):
    def test_08_default_calibration_seeds_fixed(self):
        self.assertEqual(fv.CALIBRATION_OPT_SEEDS, (0, 1, 2))
        self.assertEqual(fv.CALIBRATION_SELECTION_SPLIT, "meta_train")
        self.assertEqual(fv.TARGET_SUCCESS_LOW, 0.30)
        self.assertEqual(fv.TARGET_SUCCESS_HIGH, 0.70)
        self.assertEqual(fv.ACCEPTANCE_SUCCESS_LOW, 0.20)
        self.assertEqual(fv.ACCEPTANCE_SUCCESS_HIGH, 0.80)

    def test_09_invalid_calibration_configs(self):
        with self.assertRaises(fv.FeasibleV2Error):
            fv.CalibrationConfig(radius_grid=())
        with self.assertRaises(fv.FeasibleV2Error):
            fv.CalibrationConfig(radius_grid=(0.8, 0.8))
        with self.assertRaises(fv.FeasibleV2Error):
            fv.CalibrationConfig(radius_grid=(-0.5,))
        with self.assertRaises(fv.FeasibleV2Error):
            fv.CalibrationConfig(opt_seeds=(0, 0))
        with self.assertRaises(fv.FeasibleV2Error):
            fv.CalibrationConfig(opt_seeds=(-1,))
        with self.assertRaises(fv.FeasibleV2Error):
            fv.CalibrationConfig(budget=1)
        with self.assertRaises(fv.FeasibleV2Error):
            fv.CalibrationConfig(train_tasks=0)

    def test_10_calibration_family_config_has_no_test_splits(self):
        calibration = fv.CalibrationConfig(radius_grid=(0.8,), opt_seeds=(0,), train_tasks=2, validation_tasks=1, budget=8)
        config = fv.calibration_family_config(0.8, calibration)
        self.assertEqual(config.family_id, tf.V2_FAMILY_ID)
        self.assertEqual(config.family_version, "v2")
        self.assertEqual(config.radius_base, 0.8)
        self.assertEqual((config.test_tasks, config.ood_tasks, config.negative_control_tasks), (0, 0, 0))


class CalibrationSelectionTests(unittest.TestCase):
    def test_11_pooled_meta_train_selection(self):
        calibration = fv.CalibrationConfig(
            radius_grid=(0.80, 1.20), opt_seeds=(0, 1, 2), train_tasks=4, validation_tasks=1, budget=4
        )

        def success_fn(index):
            # 第一格（radius=0.80）全部成功 → pooled=1.0 被排除；
            # 第二格仅 seed=0 成功 → 训练 pooled=4/12≈0.333 入选。
            if index < 15:
                return True
            return ((index - 15) // 5) == 0

        fake = _fake_bo(success_fn)
        with unittest.mock.patch.object(fv, "run_bo_arm", fake):
            report = fv.calibrate_radius_base(calibration)
        self.assertEqual(report.selection_status, "SELECTED")
        self.assertEqual(report.selected_radius_base, 1.20)
        selected = report.selected_cell
        self.assertAlmostEqual(selected.pooled_success_train, 4.0 / 12.0, places=12)
        self.assertTrue(fv.TARGET_SUCCESS_LOW <= selected.pooled_success_train <= fv.TARGET_SUCCESS_HIGH)
        self.assertEqual(len(report.reference_certificates), 2 * 5)
        self.assertEqual(report.physical_call_count, 0)
        self.assertEqual(len(report.rows), 2 * 15)
        for row in report.rows:
            self.assertIn(row.split, fv.CALIBRATION_SPLITS)
        # 每个半径都有一格，且 calibration_report 可 JSON 序列化
        self.assertEqual(len(report.cells), 2)
        json.dumps(report.to_dict(), ensure_ascii=False)

    def test_12_no_cell_in_target_is_honest(self):
        calibration = fv.CalibrationConfig(
            radius_grid=(0.60, 0.90), opt_seeds=(0, 1, 2), train_tasks=2, validation_tasks=1, budget=4
        )
        fake = _fake_bo(lambda index: False)
        with unittest.mock.patch.object(fv, "run_bo_arm", fake):
            report = fv.calibrate_radius_base(calibration)
        self.assertIsNone(report.selected_radius_base)
        self.assertEqual(report.selection_status, "NO_CELL_IN_TARGET")
        self.assertIsNone(report.selected_cell)
        with self.assertRaises(fv.FeasibleV2Error):
            report.selected_cohort()

    def test_13_physics_guard_violation_rejected(self):
        calibration = fv.CalibrationConfig(
            radius_grid=(0.80,), opt_seeds=(0,), train_tasks=2, validation_tasks=1, budget=4
        )
        fake = _fake_bo(lambda index: True, physical_call_count=1)
        with unittest.mock.patch.object(fv, "run_bo_arm", fake):
            with self.assertRaises(fv.FeasibleV2Error):
                fv.calibrate_radius_base(calibration)

    def test_14_selection_rule_mentions_meta_train_only(self):
        self.assertIn("meta_train", fv.SELECTION_RULE)
        self.assertIn("0.30, 0.70", fv.SELECTION_RULE)
        self.assertIn("禁止按 MAML", fv.SELECTION_RULE)


class SplitManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = make_v2_config(0.80)
        cls.tasks = tuple(tf.build_task_family(cls.config))
        cls.manifest = fv.build_split_manifest(cls.tasks, family_config=cls.config)

    def test_15_split_manifest_covers_five_splits(self):
        self.assertEqual(self.manifest["schema_version"], fv.SPLIT_SCHEMA_VERSION)
        self.assertEqual(set(self.manifest["counts"]), set(fv.SPLITS))
        self.assertEqual(self.manifest["counts"]["meta_train"], 2)
        self.assertEqual(self.manifest["counts"]["negative_control"], 1)
        nc_ids = self.manifest["task_ids"]["negative_control"]
        self.assertEqual(len(nc_ids), 1)
        self.assertTrue(nc_ids[0].startswith("NC-"))
        self.assertTrue(fv.verify_split_manifest(self.manifest, tasks=self.tasks, family_config=self.config))

    def test_16_tampered_split_rejected(self):
        tampered = dict(self.manifest)
        tampered["counts"] = dict(self.manifest["counts"])
        tampered["counts"]["meta_test"] = 99
        with self.assertRaises(fv.FeasibleV2Error):
            fv.verify_split_manifest(tampered)
        # 用另一份任务/配置重建比对也必须失败
        other = make_v2_config(0.95)
        other_tasks = tuple(tf.build_task_family(other))
        with self.assertRaises(fv.FeasibleV2Error):
            fv.verify_split_manifest(self.manifest, tasks=other_tasks, family_config=other)

    def test_17_negative_control_has_no_reference_summary(self):
        entry = self.manifest["tasks"]["negative_control"][0]
        self.assertEqual(entry["params_summary"]["reference_kind"], "NEGATIVE_CONTROL")
        self.assertIsNone(entry["params_summary"]["objective_star"])
        self.assertIsNone(entry["params_summary"]["radius"])
        non_nc = self.manifest["tasks"]["meta_train"][0]
        self.assertTrue(np.isfinite(non_nc["params_summary"]["objective_star"]))


class FrozenFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = make_v2_config(0.80)
        cls.tasks = tuple(tf.build_task_family(cls.config))
        cls.manifest = fv.build_split_manifest(cls.tasks, family_config=cls.config)
        cls.calibration = make_calibration_report(0.80)
        cls.frozen = fv.build_frozen_family(
            cls.config,
            split_manifest=cls.manifest,
            calibration_report=cls.calibration,
            run_id="test-run",
            git_sha="deadbeef",
        )

    def test_18_frozen_contains_required_a13_fields(self):
        for name in fv.FROZEN_REQUIRED_FIELDS:
            self.assertIn(name, self.frozen)
        self.assertEqual(self.frozen["family_version"], "v2")
        self.assertEqual(self.frozen["radius_base"], 0.80)
        self.assertEqual(self.frozen["reference_solution"], "c")
        self.assertEqual(self.frozen["gap_definition"], "f(u_best)-f(u*)")
        self.assertEqual(self.frozen["calibration_seeds"], [0, 1, 2])
        self.assertAlmostEqual(self.frozen["pooled_success"], 0.333, places=12)
        self.assertAlmostEqual(self.frozen["feasible_volume_fraction"], 0.0123, places=12)
        self.assertIn("禁止使用 meta_test", self.frozen["meta_test_tuning_policy"])
        self.assertEqual(self.frozen["physical_call_count"], 0)
        self.assertTrue(fv.verify_frozen_payload(self.frozen))

    def test_19_frozen_roundtrip_and_config(self):
        restored = fv.frozen_to_config(self.frozen)
        self.assertEqual(restored, self.config)
        self.assertEqual(restored.radius_base, self.frozen["radius_base"])

    def test_20_frozen_tamper_rejected(self):
        bad = dict(self.frozen)
        bad["radius_base"] = 0.95
        with self.assertRaises(fv.FeasibleV2Error):
            fv.verify_frozen_payload(bad)
        missing = dict(self.frozen)
        del missing["calibration_seeds"]
        with self.assertRaises(fv.FeasibleV2Error):
            fv.verify_frozen_payload(missing)
        wrong_gap = dict(self.frozen)
        wrong_gap["gap_definition"] = "f(u*)"
        with self.assertRaises(fv.FeasibleV2Error):
            fv.verify_frozen_payload(wrong_gap)

    def test_21_non_v2_frozen_rejected(self):
        v1 = tf.default_task_family_config()
        v1_tasks = tf.build_task_family(v1)
        v1_manifest = fv.build_split_manifest(v1_tasks, family_config=v1)
        with self.assertRaises(fv.FeasibleV2Error):
            fv.build_frozen_family(
                v1,
                split_manifest=v1_manifest,
                calibration_report=self.calibration,
                run_id="x",
                git_sha="y",
            )
        # 半径与校准不一致必须拒绝冻结
        with self.assertRaises(fv.FeasibleV2Error):
            fv.build_frozen_family(
                make_v2_config(0.95),
                split_manifest=self.manifest,
                calibration_report=self.calibration,
                run_id="x",
                git_sha="y",
            )

    def test_22_frozen_write_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frozen_family.json"
            fv.write_frozen_family(path, self.frozen)
            loaded = fv.load_frozen_family(path)
            self.assertEqual(loaded["sha256"], self.frozen["sha256"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["sha256"], self.frozen["sha256"])


class PreregistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = make_v2_config(0.80)
        cls.tasks = tuple(tf.build_task_family(cls.config))
        cls.manifest = fv.build_split_manifest(cls.tasks, family_config=cls.config)
        cls.calibration = make_calibration_report(0.80)
        cls.frozen = fv.build_frozen_family(
            cls.config,
            split_manifest=cls.manifest,
            calibration_report=cls.calibration,
            run_id="test-run",
            git_sha="deadbeef",
        )

    def test_23_preregistration_binds_frozen(self):
        prereg = fv.build_preregistration(self.frozen, run_id="test-run")
        self.assertEqual(prereg["frozen_family_sha256"], self.frozen["sha256"])
        self.assertEqual(prereg["split_hash"], self.manifest["split_hash"])
        self.assertEqual(prereg["radius_base"], 0.80)
        self.assertEqual(prereg["arms"], list(fv.M5_ARMS))
        self.assertEqual(prereg["budgets"], list(fv.M5_BUDGETS))
        self.assertEqual(len(prereg["optimization_seeds"]), 10)
        self.assertTrue(fv.verify_preregistration(prereg, self.frozen))
        json.dumps(prereg, ensure_ascii=False)

    def test_24_preregistration_tamper_and_mismatch_rejected(self):
        prereg = fv.build_preregistration(self.frozen, run_id="test-run")
        tampered = dict(prereg)
        tampered["radius_base"] = 0.95
        with self.assertRaises(fv.FeasibleV2Error):
            fv.verify_preregistration(tampered, self.frozen)
        other_frozen = dict(self.frozen)
        other_frozen["sha256"] = "0" * 64
        with self.assertRaises(fv.FeasibleV2Error):
            fv.verify_preregistration(prereg, other_frozen)

    def test_25_preregistration_requires_ten_seeds(self):
        with self.assertRaises(fv.FeasibleV2Error):
            fv.build_preregistration(
                self.frozen, run_id="x", optimization_seeds=(0, 1, 2)
            )

    def test_26_preregistration_write_load(self):
        prereg = fv.build_preregistration(self.frozen, run_id="test-run")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preregistration.json"
            fv.write_preregistration(path, prereg, self.frozen)
            loaded = fv.load_preregistration(path)
            self.assertTrue(fv.verify_preregistration(loaded, self.frozen))

    # -- 26a-26e：stopping_rules 序列化缺陷修复与旧 run 兼容回归 ------------
    def test_26a_stopping_rules_constant_and_payload(self):
        """常量必须是 tuple/list[str]（修复前是缺尾逗号的单个 str）。"""
        self.assertIsInstance(fv.STOPPING_RULES, tuple)
        self.assertGreaterEqual(len(fv.STOPPING_RULES), 1)
        self.assertTrue(all(isinstance(item, str) for item in fv.STOPPING_RULES))
        self.assertTrue(
            all(len(item.strip()) >= fv.STOPPING_RULE_MIN_LENGTH for item in fv.STOPPING_RULES)
        )
        prereg = fv.build_preregistration(self.frozen, run_id="test-run")
        self.assertEqual(prereg["schema_version"], fv.PREREGISTRATION_SCHEMA_VERSION)
        stored = prereg["stopping_rules"]
        self.assertIsInstance(stored, list)
        self.assertEqual(stored, list(fv.STOPPING_RULES))
        self.assertTrue(
            all(isinstance(item, str) and len(item.strip()) >= fv.STOPPING_RULE_MIN_LENGTH for item in stored)
        )
        self.assertTrue(fv.verify_preregistration(prereg, self.frozen))

    def test_26b_stopping_rules_str_accepted_and_normalized(self):
        """旧 API 传单个 str 时规范化为单元素 list（不再逐字符拆分）。"""
        prereg = fv.build_preregistration(
            self.frozen, run_id="test-run", stopping_rules=fv.STOPPING_RULES[0]
        )
        self.assertEqual(prereg["stopping_rules"], list(fv.STOPPING_RULES))
        self.assertTrue(fv.verify_preregistration(prereg, self.frozen))

    def test_26c_stopping_rules_invalid_build_inputs_rejected(self):
        """负控：空列表/逐字符形态/空串/过短/非 str 元素必须 fail-closed。"""
        bad_values = [
            [],
            list(fv.STOPPING_RULES[0]),  # 旧坏数据形态：逐字符数组
            [""],
            ["x"],
            ["合法规则文本", 1],
            None,
        ]
        for bad in bad_values:
            with self.subTest(bad=repr(bad)[:40]):
                with self.assertRaises(fv.FeasibleV2Error):
                    fv.build_preregistration(
                        self.frozen, run_id="test-run", stopping_rules=bad
                    )

    def test_26d_tampered_new_schema_stopping_rules_rejected(self):
        """负控：v2 schema 的已签名载荷篡改 stopping_rules 后必须拒绝。"""
        prereg = fv.build_preregistration(self.frozen, run_id="test-run")
        bad_values = [
            [],
            list(prereg["stopping_rules"][0]),
            [""],
            ["x"],
            ["合法规则文本", 1],
            prereg["stopping_rules"][0],  # 字符串而非 JSON 数组
        ]
        for bad in bad_values:
            payload = dict(prereg)
            payload["stopping_rules"] = bad
            body = {key: value for key, value in payload.items() if key != "sha256"}
            payload["sha256"] = fv.digest(body)
            with self.subTest(bad=repr(bad)[:40]):
                with self.assertRaises(fv.FeasibleV2Error):
                    fv.verify_preregistration(payload, self.frozen)

    def test_26f_v2_missing_stopping_rules_rejected(self):
        """负控（A5 m08）：v2 schema 缺少 stopping_rules 字段必须 fail-closed。"""
        prereg = fv.build_preregistration(self.frozen, run_id="test-run")
        payload = dict(prereg)
        payload.pop("stopping_rules")
        body = {key: value for key, value in payload.items() if key != "sha256"}
        payload["sha256"] = fv.digest(body)
        with self.assertRaises(fv.FeasibleV2Error):
            fv.verify_preregistration(payload, self.frozen)

    def test_26g_stopping_rules_items_are_stripped(self):
        """A5 m07：落盘 stopping_rules 每项去除首尾空白（不再原样保留）。"""
        prereg = fv.build_preregistration(
            self.frozen, run_id="test-run", stopping_rules=["  合法规则文本  "]
        )
        self.assertEqual(prereg["stopping_rules"], ["合法规则文本"])
        self.assertTrue(fv.verify_preregistration(prereg, self.frozen))

    def test_26e_legacy_v1_bad_stopping_rules_still_verifies(self):
        """旧 run 兼容：p4-m5-prereg-v1 历史工件（含逐字符数组）仍可验证。"""
        legacy = dict(fv.build_preregistration(self.frozen, run_id="test-run"))
        legacy["schema_version"] = fv.LEGACY_PREREGISTRATION_SCHEMA_VERSIONS[0]
        legacy["stopping_rules"] = list(legacy["stopping_rules"][0])
        body = {key: value for key, value in legacy.items() if key != "sha256"}
        legacy["sha256"] = fv.digest(body)
        self.assertTrue(fv.verify_preregistration(legacy, self.frozen))
        fv.validate_preregistration_schema(legacy)  # 不抛异常



class HoldoutGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = make_v2_config(0.80)
        cls.tasks = tuple(tf.build_task_family(cls.config))
        cls.manifest = fv.build_split_manifest(cls.tasks, family_config=cls.config)
        cls.calibration = make_calibration_report(0.80)
        cls.frozen = fv.build_frozen_family(
            cls.config,
            split_manifest=cls.manifest,
            calibration_report=cls.calibration,
            run_id="test-run",
            git_sha="deadbeef",
        )
        cls.prereg = fv.build_preregistration(cls.frozen, run_id="test-run")

    def test_27_holdout_unlocks_when_consistent(self):
        result = fv.assert_holdout_unlocked(
            frozen_family=self.frozen,
            preregistration=self.prereg,
            split_manifest=self.manifest,
            calibration_report=self.calibration,
        )
        self.assertEqual(result["status"], "UNLOCKED")
        self.assertEqual(result["radius_base"], 0.80)
        self.assertEqual(result["split_hash"], self.manifest["split_hash"])

    def test_28_holdout_blocked_on_calibration_mismatch(self):
        other = make_calibration_report(0.80, cells=(make_calibration_cell(0.80, feasible_volume_fraction=0.5),))
        with self.assertRaises(fv.FeasibleV2Error):
            fv.assert_holdout_unlocked(
                frozen_family=self.frozen,
                preregistration=self.prereg,
                split_manifest=self.manifest,
                calibration_report=other,
            )

    def test_29_holdout_blocked_on_split_mismatch(self):
        tampered = dict(self.manifest)
        tampered["split_hash"] = "0" * 64
        with self.assertRaises(fv.FeasibleV2Error):
            fv.assert_holdout_unlocked(
                frozen_family=self.frozen,
                preregistration=self.prereg,
                split_manifest=tampered,
                calibration_report=self.calibration,
            )


if __name__ == "__main__":
    unittest.main()
