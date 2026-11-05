# -*- coding: utf-8 -*-
"""S0-2：F-QE-feasible-v3 任务族/冻结包/预注册/预算公平性单元测试（全合成，physical=0）。

覆盖 D-S0-2-01..07：
- 五 split 60/20/20/10/10、task_id 正则 ^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$、
  跨 split 唯一、序号连续；
- family fingerprint 稳定且对 radius/seed 敏感；task_fingerprint 不含 split/index/seed；
- split_hash 覆盖五 split 有序 task_id，篡改 fail-closed；
- 与旧 M2/M5/M6 的 task_id/task_fingerprint 零交集断言（含交集非空负控）；
- frozen/prereg 双 digest、显式 created_utc 确定性重跑（两次构建/写盘逐位一致）；
- 端点规范 ID（禁用 first_feasible_evaluation_index 别名）、stopping_rules list[str] 校验；
- 五臂 x K∈{0,1,3,5} x B∈{64,128} 预算 billable=B、K 计入 B、K=0 CLONE 排除推断。
"""
from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research.concorde_metaopt.meta_learning import budget_fairness as bf
from research.concorde_metaopt.meta_learning import family_v3 as f3
from research.concorde_metaopt.meta_learning import task_family as tf

GIT_SHA = "a331639e47015f1d07796e46dbe3f71beb97048c"
CREATED_UTC = "2026-11-05T00:00:00+00:00"
RUN_ID = "p4ra-s0-2-unittest"
CODE_SHA = "unit-test-code-sha"


def make_fake_legacy() -> dict:
    """旧族 fixture（形状与 M2/M5/M6 清单一致；不依赖外部文件）。"""
    return {
        "task_ids": ["m2-deadbeef0001", "m5-deadbeef0002"],
        "task_fingerprints": ["0" * 64],
        "sources": [{"path": "<fixture>", "bytes": 0, "sha256": "f" * 64}],
    }


def build_bundle(legacy: dict | None = None) -> dict:
    return f3.build_freeze_bundle(
        run_id=RUN_ID,
        git_sha=GIT_SHA,
        created_utc=CREATED_UTC,
        code_sha=CODE_SHA,
        legacy=legacy if legacy is not None else make_fake_legacy(),
    )


class V3FamilyIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = f3.build_v3_family_config()
        cls.tasks = f3.assign_v3_task_ids(tf.build_task_family(cls.config))
        cls.records = f3.build_task_records(cls.tasks)
        cls.manifest = f3.build_split_manifest_v3(cls.tasks, family_config=cls.config)

    def test_01_config_identity(self):
        config = self.config
        self.assertEqual(config.family_id, "F-QE-feasible-v3")
        self.assertEqual(config.family_version, "v3")
        self.assertEqual(int(config.seed), 20261105)
        self.assertAlmostEqual(float(config.radius_base), 0.32, places=12)
        self.assertEqual(
            [
                config.train_tasks,
                config.validation_tasks,
                config.test_tasks,
                config.ood_tasks,
                config.negative_control_tasks,
            ],
            [60, 20, 20, 10, 10],
        )
        self.assertEqual(config.designs_per_task, config.support_pool_size + config.query_size)
        f3.assert_family_v3_identity(config)

    def test_02_identity_fail_closed(self):
        bad_seed = f3.build_v3_family_config(seed=1)
        with self.assertRaises(f3.FamilyV3Error):
            f3.assert_family_v3_identity(bad_seed)
        bad_count = f3.build_v3_family_config(train_tasks=59)
        with self.assertRaises(f3.FamilyV3Error):
            f3.assert_family_v3_identity(bad_count)
        # family_version 与 v3 不一致时 TaskFamilyConfig 构造即 fail-closed
        with self.assertRaises(tf.TaskFamilyError):
            f3.build_v3_family_config(family_version="v2")

    def test_03_split_counts_and_order(self):
        self.assertEqual(len(self.tasks), 120)
        counts = f3.SPLIT_COUNTS
        self.assertEqual(
            counts,
            {
                "meta_train": 60,
                "meta_validation": 20,
                "meta_test": 20,
                "meta_test_ood": 10,
                "negative_control": 10,
            },
        )
        expected_order = ["meta_train", "meta_validation", "meta_test", "meta_test_ood", "negative_control"]
        self.assertEqual(list(f3.SPLIT_ORDER), expected_order)
        self.assertEqual([task.split for task in self.tasks], [split for split in expected_order for _ in range(counts[split])])
        self.assertEqual(self.manifest["counts"], counts)
        self.assertEqual(self.manifest["total_tasks"], 120)
        self.assertEqual(self.manifest["split_order"], expected_order)

    def test_04_task_id_pattern_and_ordinals(self):
        ids = [task.task_id for task in self.tasks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(self.records), 120)
        counters: dict[str, int] = {split: 0 for split in f3.SPLIT_ORDER}
        for task in self.tasks:
            self.assertIsNotNone(f3.TASK_ID_PATTERN.match(task.task_id), task.task_id)
            split, index = f3.parse_task_id(task.task_id)
            self.assertEqual(split, task.split)
            self.assertEqual(index, counters[task.split])
            counters[task.split] += 1
        self.assertEqual(counters, dict(f3.SPLIT_COUNTS))
        self.assertEqual(self.manifest["task_ids"]["meta_train"][0], "p4ra-FQE3-v3-TR-000")
        self.assertEqual(self.manifest["task_ids"]["negative_control"][0], "p4ra-FQE3-v3-NC-000")

    def test_05_invalid_task_ids_rejected(self):
        bad_ids = [
            "",
            "p4ra-fqe3-v3-TR-000",
            "p4ra-FQE3-v2-TR-000",
            "p4ra-FQE3-v3-XX-000",
            "p4ra-FQE3-v3-TR-00",
            "p4ra-FQE3-v3-TR-0000",
            "p4ra-FQE3-v3-TR-000x",
            "p4ra-FQE3-v3-TR-000-extra",
        ]
        for bad in bad_ids:
            with self.subTest(bad=bad):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.validate_task_id(bad)
        with self.assertRaises(f3.FamilyV3Error):
            f3.validate_task_id(None)  # type: ignore[arg-type]

    def test_06_assign_rejects_unknown_split_or_overflow(self):
        unknown = dataclasses.replace(self.tasks[0], split="bogus")
        with self.assertRaises(f3.FamilyV3Error):
            f3.assign_v3_task_ids([unknown])
        overflow = dataclasses.replace(self.tasks[0], task_id="p4ra-FQE3-v3-TR-999")
        many = [dataclasses.replace(overflow, seed=index) for index in range(1001)]
        with self.assertRaises(f3.FamilyV3Error):
            f3.assign_v3_task_ids(many)

    def test_07_family_fingerprint_stable_and_sensitive(self):
        self.assertEqual(self.manifest["family_fingerprint"], tf.family_fingerprint(self.config))
        other_radius = f3.build_v3_family_config(radius_base=0.31)
        self.assertNotEqual(tf.family_fingerprint(other_radius), self.manifest["family_fingerprint"])
        other_seed = f3.build_v3_family_config(seed=20261106)
        self.assertNotEqual(tf.family_fingerprint(other_seed), self.manifest["family_fingerprint"])
        # v2 旧 fingerprint 保持不变是回归约束，此处 v3 与 v2 必须不同
        v2 = tf.TaskFamilyConfig(
            family_id=tf.V2_FAMILY_ID,
            design_dim=tf.DESIGN_DIM,
            context_names=tf.CONTEXT_NAMES,
            seed=20261102,
            train_tasks=2,
            validation_tasks=1,
            test_tasks=2,
            ood_tasks=1,
            negative_control_tasks=1,
            designs_per_task=12,
            support_pool_size=8,
            query_size=4,
            reference_tolerance=1e-10,
            family_version="v2",
            radius_base=0.80,
        )
        self.assertNotEqual(tf.family_fingerprint(v2), self.manifest["family_fingerprint"])

    def test_08_task_fingerprint_excludes_split_index_seed(self):
        task = self.tasks[0]
        fingerprint = f3.task_fingerprint(task)
        moved = dataclasses.replace(task, split="meta_validation", seed=task.seed + 7)
        self.assertEqual(f3.task_fingerprint(moved), fingerprint)
        # 参数改变则指纹改变
        params = dict(task.params)
        params["b"] = float(params["b"]) + 0.01
        changed = dataclasses.replace(task, params=params)
        self.assertNotEqual(f3.task_fingerprint(changed), fingerprint)
        self.assertEqual(self.records[0]["task_fingerprint"], fingerprint)

    def test_09_reference_certificate_all_tasks(self):
        residuals = tf.assert_reference_solutions(self.tasks)
        self.assertEqual(len(residuals), 110)
        for task in self.tasks:
            if task.is_negative_control:
                continue
            reference = task.reference()
            self.assertEqual(reference["reference_kind"], "ANALYTIC_RADIAL_PROJECTION")
            self.assertEqual(np.asarray(reference["u_star"]).shape, (12,))
            self.assertLessEqual(reference["assertion_residual"], 1e-10 * max(1.0, abs(reference["objective_star"])))
            self.assertTrue(reference["feasible"])
            for value in reference["constraints"].values():
                self.assertLessEqual(float(value), 0.0)
        for task_id, residual in residuals.items():
            self.assertLessEqual(residual, 1e-10, task_id)

    def test_10_negative_control_has_no_reference(self):
        nc_tasks = [task for task in self.tasks if task.is_negative_control]
        self.assertEqual(len(nc_tasks), 10)
        for task in nc_tasks:
            with self.assertRaises(tf.TaskFamilyError):
                task.reference()

    def test_11_split_manifest_verifies_and_rebuilds(self):
        self.assertTrue(
            f3.verify_split_manifest_v3(
                self.manifest, tasks=self.tasks, family_config=self.config
            )
        )
        self.assertEqual(
            self.manifest["split_hash"],
            f3.digest(f3._split_hash_payload(self.manifest["task_ids"])),
        )
        self.assertEqual(
            self.manifest["task_ids"]["meta_test"],
            [task.task_id for task in self.tasks if task.split == "meta_test"],
        )

    def test_12_split_manifest_tamper_rejected(self):
        tampered = json.loads(json.dumps(self.manifest))
        tampered["task_ids"]["meta_test"][0] = "p4ra-FQE3-v3-TE-999"
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_split_manifest_v3(tampered)
        counts_bad = json.loads(json.dumps(self.manifest))
        counts_bad["counts"]["meta_train"] = 59
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_split_manifest_v3(counts_bad)
        rebuilt_bad = json.loads(json.dumps(self.manifest))
        rebuilt_bad["tasks"]["meta_train"][0]["seed"] = 1
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_split_manifest_v3(rebuilt_bad, tasks=self.tasks, family_config=self.config)
        self.assertEqual(self.manifest["tasks"]["negative_control"][0]["params_summary"]["reference_kind"], "NEGATIVE_CONTROL")
        self.assertIsNone(self.manifest["tasks"]["negative_control"][0]["params_summary"]["objective_star"])


class V3IsolationTests(unittest.TestCase):
    def test_01_zero_intersection_pass(self):
        legacy = make_fake_legacy()
        v3_ids = [f"p4ra-FQE3-v3-TR-{index:03d}" for index in range(120)]
        v3_fps = [f"ab{index:062x}" for index in range(120)]
        report = f3.build_isolation_report(
            v3_task_ids=v3_ids,
            v3_task_fingerprints=v3_fps,
            legacy=legacy,
            created_utc=CREATED_UTC,
        )
        self.assertEqual(report["schema_version"], f3.ISOLATION_SCHEMA_VERSION)
        self.assertEqual(report["assertion"], "ZERO_INTERSECTION")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["physical_call_count"], 0)
        self.assertEqual(report["v3"]["task_id_count"], 120)
        self.assertEqual(report["v3"]["task_fingerprint_count"], 120)
        self.assertEqual(report["legacy"]["task_id_count"], 2)
        self.assertTrue(f3.verify_isolation_report(report))
        tampered = dict(report)
        tampered["v3"] = dict(report["v3"])
        tampered["v3"]["task_id_count"] = 121
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_isolation_report(tampered)

    def test_02_overlap_ids_fail_closed(self):
        legacy = make_fake_legacy()
        legacy["task_ids"] = ["p4ra-FQE3-v3-TR-000"]
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_isolation_report(
                v3_task_ids=["p4ra-FQE3-v3-TR-000"],
                v3_task_fingerprints=[],
                legacy=legacy,
                created_utc=CREATED_UTC,
            )
        with self.assertRaises(f3.FamilyV3Error):
            f3.assert_zero_intersection(
                legacy,
                v3_task_ids=["p4ra-FQE3-v3-TR-000"],
                v3_task_fingerprints=[],
            )

    def test_03_overlap_fingerprints_fail_closed(self):
        legacy = make_fake_legacy()
        legacy["task_fingerprints"] = ["a" * 64]
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_isolation_report(
                v3_task_ids=[],
                v3_task_fingerprints=["a" * 64],
                legacy=legacy,
                created_utc=CREATED_UTC,
            )

    def test_04_collect_legacy_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks_path = root / "tasks.json"
            tasks_path.write_text(
                json.dumps({"tasks": [{"task_id": "m5-abc"}, {"task_id": "m5-def"}]}),
                encoding="utf-8",
            )
            split_path = root / "meta_task_split.json"
            split_path.write_text(
                json.dumps({"task_ids": {"meta_train": ["m2-1"], "meta_test": ["m2-2"]}}),
                encoding="utf-8",
            )
            legacy = f3.collect_legacy_task_ids([tasks_path, split_path, root / "missing.json"], require_exists=False)
            self.assertEqual(legacy["task_ids"], ["m2-1", "m2-2", "m5-abc", "m5-def"])
            self.assertEqual(legacy["task_fingerprints"], [])
            self.assertEqual(len(legacy["sources"]), 3)
            self.assertFalse(legacy["sources"][2]["exists"])
            self.assertEqual(legacy["sources"][0]["task_id_count"], 2)
            self.assertEqual(legacy["sources"][1]["task_id_count"], 2)
            self.assertEqual(legacy["sources"][0]["sha256"], f3.file_sha256(tasks_path))
            with self.assertRaises(f3.FamilyV3Error):
                f3.collect_legacy_task_ids([root / "missing.json"])
            bad_path = root / "bad.json"
            bad_path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(f3.FamilyV3Error):
                f3.collect_legacy_task_ids([bad_path])


class V3FreezeBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build_bundle()

    def test_01_freeze_bundle_verifies(self):
        bundle = self.bundle
        self.assertTrue(tf.family_fingerprint(bundle["config"]))
        records = bundle["task_records"]
        self.assertEqual(len(records), 120)
        self.assertEqual(records[0]["schema_version"], f3.TASK_SCHEMA_VERSION)
        self.assertTrue(f3.verify_split_manifest_v3(bundle["split_manifest"], tasks=bundle["tasks"], family_config=bundle["config"]))
        self.assertTrue(f3.verify_isolation_report(bundle["isolation_report"]))
        self.assertTrue(f3.verify_frozen_family_v3(bundle["frozen_family"]))
        self.assertTrue(f3.verify_preregistration_v3(bundle["preregistration"], bundle["frozen_family"]))
        frozen = bundle["frozen_family"]
        self.assertEqual(frozen["schema_version"], f3.FROZEN_SCHEMA_VERSION)
        self.assertEqual(frozen["physical_call_count"], 0)
        self.assertEqual(frozen["evaluator"], "synthetic-analytic")
        self.assertEqual(frozen["physics_validation_status"], "NOT_APPLICABLE")
        self.assertEqual(frozen["family_version"], "v3")
        self.assertEqual(frozen["task_id_pattern"], f3.TASK_ID_PATTERN.pattern)
        self.assertEqual(frozen["split"]["split_hash"], bundle["split_manifest"]["split_hash"])
        self.assertEqual(frozen["split"]["counts"], dict(f3.SPLIT_COUNTS))
        self.assertEqual(frozen["primary_endpoints"], list(f3.PRIMARY_ENDPOINTS))
        self.assertEqual(frozen["arms"], list(f3.ARM_IDS))
        self.assertEqual(frozen["budgets"], list(f3.BUDGETS))
        self.assertEqual(frozen["k_values"], list(f3.K_VALUES))

    def test_02_prereg_binding_and_endpoints(self):
        prereg = self.bundle["preregistration"]
        frozen = self.bundle["frozen_family"]
        self.assertEqual(prereg["schema_version"], f3.PREREGISTRATION_SCHEMA_VERSION)
        self.assertEqual(prereg["frozen_family_sha256"], frozen["sha256"])
        self.assertEqual(prereg["split_hash"], frozen["split"]["split_hash"])
        self.assertEqual(prereg["family_fingerprint"], frozen["family_fingerprint"])
        self.assertEqual(prereg["radius_base"], frozen["radius_base"])
        self.assertEqual(prereg["primary_endpoints"], ["best_feasible_value", "gap_to_reference", "first_feasible_eval_index", "feasible_hit_rate"])
        self.assertIsInstance(prereg["stopping_rules"], list)
        self.assertTrue(all(isinstance(item, str) and len(item.strip()) >= 2 for item in prereg["stopping_rules"]))
        self.assertEqual(prereg["optimization_seeds"], list(range(10)))
        self.assertEqual(prereg["meta_seeds"], [0, 1, 2])
        self.assertEqual(prereg["physical_call_count"], 0)

    def test_03_deterministic_rebuild(self):
        second = build_bundle()
        self.assertEqual(second["frozen_family"], self.bundle["frozen_family"])
        self.assertEqual(second["preregistration"], self.bundle["preregistration"])
        self.assertEqual(second["split_manifest"], self.bundle["split_manifest"])
        self.assertEqual(second["isolation_report"], self.bundle["isolation_report"])
        self.assertEqual(second["task_records"], self.bundle["task_records"])
        self.assertEqual(
            f3.canonical_json(second["frozen_family"]), f3.canonical_json(self.bundle["frozen_family"])
        )
        self.assertEqual(f3.digest(second["frozen_family"]), f3.digest(self.bundle["frozen_family"]))

    @staticmethod
    def _write_artifact(path, payload):
        """tasks.json 是 JSON 数组（非 Mapping），这里按同一 canonical/raw 规则补一个写盘助手。"""
        if isinstance(payload, dict):
            return f3.write_json_artifact(path, payload)
        target = f3.write_json(path, payload)
        return {
            "path": str(target.resolve()),
            "bytes": target.stat().st_size,
            "canonical_sha256": f3.digest(payload),
            "raw_sha256": f3.file_sha256(target),
        }

    def test_04_write_artifacts_deterministic(self):
        payloads = {
            "tasks.json": self.bundle["task_records"],
            "meta_task_split.json": self.bundle["split_manifest"],
            "v3_isolation_report.json": self.bundle["isolation_report"],
            "frozen_family.json": self.bundle["frozen_family"],
            "preregistration.json": self.bundle["preregistration"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            first_root = Path(tmp) / "run1"
            second_root = Path(tmp) / "run2"
            first = {name: self._write_artifact(first_root / name, payload) for name, payload in payloads.items()}
            second = {name: self._write_artifact(second_root / name, payload) for name, payload in payloads.items()}
            for name in payloads:
                self.assertEqual(first[name]["bytes"], second[name]["bytes"], name)
                self.assertEqual(first[name]["raw_sha256"], second[name]["raw_sha256"], name)
                self.assertEqual(first[name]["canonical_sha256"], second[name]["canonical_sha256"], name)
                self.assertEqual((first_root / name).read_bytes(), (second_root / name).read_bytes())
                if isinstance(payloads[name], dict) and "sha256" in payloads[name]:
                    self.assertEqual(first[name]["stored_sha256"], payloads[name]["sha256"])
            manifest = f3.build_digest_manifest(list(first.values()), created_utc=CREATED_UTC)
            self.assertEqual(manifest["schema_version"], f3.DIGEST_MANIFEST_SCHEMA_VERSION)
            self.assertEqual(len(manifest["artifacts"]), len(payloads))
            for entry in manifest["artifacts"]:
                self.assertTrue({"path", "bytes", "canonical_sha256", "raw_sha256"} <= set(entry))

    def test_05_requires_legacy_source(self):
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_freeze_bundle(run_id=RUN_ID, git_sha=GIT_SHA, created_utc=CREATED_UTC)
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_freeze_bundle(run_id=RUN_ID, git_sha=GIT_SHA, created_utc="")
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_freeze_bundle(run_id="", git_sha=GIT_SHA, created_utc=CREATED_UTC, legacy=make_fake_legacy())
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_isolation_report(v3_task_ids=[], v3_task_fingerprints=[], legacy=make_fake_legacy(), created_utc="")

    def test_06_frozen_tamper_rejected(self):
        frozen = json.loads(json.dumps(self.bundle["frozen_family"]))
        frozen["physical_call_count"] = 1
        body = {key: value for key, value in frozen.items() if key != "sha256"}
        frozen["sha256"] = f3.digest(body)
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_frozen_family_v3(frozen)
        for mutation in (
            lambda payload: payload.update({"split": {**payload["split"], "split_hash": "0" * 64}}),
            lambda payload: payload["split"]["task_ids"]["meta_train"].pop(),
            lambda payload: payload.update({"radius_base": 0.99}),
            lambda payload: payload["arms"].append("X"),
            lambda payload: payload.update({"reference_solution": "d"}),
            lambda payload: payload.update({"task_id_pattern": "^.*$"}),
        ):
            payload = json.loads(json.dumps(self.bundle["frozen_family"]))
            mutation(payload)
            body = {key: value for key, value in payload.items() if key != "sha256"}
            payload["sha256"] = f3.digest(body)
            with self.subTest(mutation=mutation):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.verify_frozen_family_v3(payload)

    def test_07_prereg_tamper_and_alias_rejected(self):
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_preregistration_v3(
                self.bundle["frozen_family"],
                run_id=RUN_ID,
                created_utc=CREATED_UTC,
                primary_endpoints=["first_feasible_evaluation_index", "best_feasible_value", "gap_to_reference", "feasible_hit_rate"],
            )
        with self.assertRaises(f3.FamilyV3Error):
            f3.normalize_endpoints(["best_feasible_value", "best_feasible_value", "gap_to_reference", "feasible_hit_rate"])
        with self.assertRaises(f3.FamilyV3Error):
            f3.normalize_endpoints(["best_feasible_value", "gap_to_reference", "first_feasible_eval_index"])
        fresh = self.bundle["preregistration"]
        mutations = (
            lambda payload: payload.update({"radius_base": 0.31}),
            lambda payload: payload.update({"physical_call_count": 1}),
            lambda payload: payload.pop("stopping_rules"),
            lambda payload: payload.update({"primary_endpoints": list(f3.FORBIDDEN_ENDPOINT_ALIASES) + ["best_feasible_value"]}),
            lambda payload: payload.update({"arms": ["RAND-BO"]}),
        )
        for mutation in mutations:
            payload = json.loads(json.dumps(fresh))
            mutation(payload)
            body = {key: value for key, value in payload.items() if key != "sha256"}
            payload["sha256"] = f3.digest(body)
            with self.subTest(mutation=mutation):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.verify_preregistration_v3(payload, self.bundle["frozen_family"])
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_preregistration_v3(
                self.bundle["frozen_family"], run_id=RUN_ID, created_utc=CREATED_UTC, optimization_seeds=(0, 0, 1)
            )
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_preregistration_v3(
                self.bundle["frozen_family"], run_id=RUN_ID, created_utc=CREATED_UTC, meta_seeds=(0, 1)
            )
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_preregistration_v3(
                self.bundle["frozen_family"], run_id=RUN_ID, created_utc=CREATED_UTC, stopping_rules="单条字符串"
            )
        self.assertEqual(f3.normalize_stopping_rules(["  规则文本  "]), ["规则文本"])
        for bad in ([], [""], ["x"], [1], None):
            with self.subTest(bad=bad):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.normalize_stopping_rules(bad)


class BudgetFairnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans = bf.build_all_budget_plans()
        cls.report = bf.build_fairness_report(cls.plans, created_utc=CREATED_UTC)

    def test_01_forty_plans_billable_equals_budget(self):
        self.assertEqual(len(self.plans), 40)
        for plan in self.plans:
            budget = plan["B"]
            self.assertEqual(plan["evaluations"]["billable"], budget)
            self.assertEqual(plan["evaluations"]["non_billable"], 0)
            self.assertEqual(plan["evaluations"]["physical_call_count"], 0)
            self.assertEqual(sum(stage["evaluations"] for stage in plan["stages"]), budget)
            self.assertTrue(all(stage["counted_in_billable"] is True for stage in plan["stages"]))
            self.assertEqual(plan["support_evaluations"], plan["K"])
            self.assertEqual(plan["initial_design_evaluations"], 8 - plan["K"])
            self.assertEqual(plan["main_search_evaluations"], budget - 8)
            self.assertTrue(plan["budget"]["support_evaluations_counted"])
            self.assertTrue(plan["support"]["counted_in_billable"])
            self.assertTrue(plan["support"]["shared_by_all_arms"])
        self.assertTrue(bf.assert_budget_fairness(self.plans))

    def test_02_all_arms_share_budget(self):
        for k_shot in bf.K_VALUES:
            for budget in bf.BUDGETS:
                group = [plan for plan in self.plans if plan["K"] == k_shot and plan["B"] == budget]
                self.assertEqual({plan["arm"] for plan in group}, set(bf.ARM_IDS))
                self.assertEqual({plan["evaluations"]["billable"] for plan in group}, {budget})
                self.assertEqual(len(group), 5)

    def test_03_k_not_counted_fail_closed(self):
        plan = json.loads(json.dumps(self.plans[0]))
        plan["budget"]["support_evaluations_counted"] = False
        with self.assertRaises(bf.BudgetFairnessError):
            bf.assert_budget_fairness([plan])
        stage_bad = json.loads(json.dumps(self.plans[0]))
        stage_bad["stages"][0]["counted_in_billable"] = False
        with self.assertRaises(bf.BudgetFairnessError):
            bf.assert_budget_fairness([stage_bad])

    def test_04_unequal_budget_fail_closed(self):
        plan = json.loads(json.dumps(self.plans[0]))
        plan["evaluations"]["billable"] = plan["B"] + 1
        with self.assertRaises(bf.BudgetFairnessError):
            bf.assert_budget_fairness([plan])
        # 缺一个计划（分组不完整）也 fail-closed
        with self.assertRaises(bf.BudgetFairnessError):
            bf.assert_budget_fairness(self.plans[:-1])

    def test_05_bad_keys_rejected(self):
        for arm, k_shot, budget in (("X", 0, 64), ("RAND-BO", 2, 64), ("RAND-BO", 0, 32), ("RAND-BO", True, 64), ("RAND-BO", 0, True)):
            with self.subTest(arm=arm, k=k_shot, b=budget):
                with self.assertRaises(bf.BudgetFairnessError):
                    bf.build_budget_plan(arm, k_shot, budget)

    def test_06_k0_clone_registered_and_excluded(self):
        self.assertEqual(bf.clone_map(0), {"FOMAML-KSHOT-BO": "FOMAML-ZERO-BO"})
        self.assertNotIn("FOMAML-KSHOT-BO", bf.inference_eligible_arms(0))
        self.assertIn("FOMAML-ZERO-BO", bf.inference_eligible_arms(0))
        for plan in self.plans:
            if plan["K"] == 0 and plan["arm"] == "FOMAML-KSHOT-BO":
                self.assertEqual(plan["clone_of"], "FOMAML-ZERO-BO")
                self.assertFalse(plan["inference_eligible"])
                self.assertTrue(plan["notes"])
            else:
                self.assertIsNone(plan["clone_of"], (plan["arm"], plan["K"]))
                self.assertTrue(plan["inference_eligible"], (plan["arm"], plan["K"]))
        self.assertEqual(bf.clone_map(1), {})
        self.assertEqual(len(bf.inference_eligible_arms(1)), 5)
        self.assertEqual(len(bf.inference_eligible_arms(5)), 5)

    def test_07_clone_mismatch_fail_closed(self):
        plan = json.loads(json.dumps(next(item for item in self.plans if item["arm"] == "FOMAML-KSHOT-BO" and item["K"] == 1)))
        plan["clone_of"] = "FOMAML-ZERO-BO"
        plan["inference_eligible"] = False
        with self.assertRaises(bf.BudgetFairnessError):
            bf.assert_budget_fairness([plan])
        k0 = json.loads(json.dumps(next(item for item in self.plans if item["arm"] == "FOMAML-KSHOT-BO" and item["K"] == 0)))
        k0["inference_eligible"] = True
        with self.assertRaises(bf.BudgetFairnessError):
            bf.assert_budget_fairness([k0])

    def test_08_fairness_report(self):
        report = self.report
        self.assertEqual(report["schema_version"], bf.FAIRNESS_SCHEMA_VERSION)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["plan_count"], 40)
        self.assertEqual(report["physical_call_count"], 0)
        self.assertEqual(report["clone_pairs"], [{"K": 0, "clone_arm": "FOMAML-KSHOT-BO", "canonical_arm": "FOMAML-ZERO-BO"}])
        self.assertEqual(report["inference_eligible"]["0"], ["RAND-BO", "PRETRAIN-KSHOT-BO", "FOMAML-ZERO-BO", "DE"])
        body = {key: value for key, value in report.items() if key != "sha256"}
        self.assertEqual(report["sha256"], f3.digest(body))
        with self.assertRaises(bf.BudgetFairnessError):
            bf.build_fairness_report(created_utc="")


if __name__ == "__main__":
    unittest.main()
