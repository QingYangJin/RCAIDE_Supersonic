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

GIT_SHA = "3ebd777595bf747edc855be5fb583f51cc17352f"
CREATED_UTC = "2026-11-05T00:00:00+00:00"
RUN_ID = "p4ra-s0-3-unittest"
CODE_SHA = "unit-test-code-sha"


V3_PACKAGE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "concorde_metaopt"
    / "optimization_runs"
    / "p4ra-s0-2-freeze-20261105T072500Z"
)
_V3_PACKAGE_RECORDS: list[dict] | None = None


def v3_package_records() -> list[dict]:
    """只读加载 S0-2 v3 官方冻结包 tasks.json（120 条记录，含 task_fingerprint）。"""
    global _V3_PACKAGE_RECORDS
    if _V3_PACKAGE_RECORDS is None:
        records = json.loads((V3_PACKAGE_ROOT / "tasks.json").read_text(encoding="utf-8"))
        if len(records) != 120:
            raise AssertionError("v3 package task count mismatch: " + str(len(records)))
        _V3_PACKAGE_RECORDS = records
    return _V3_PACKAGE_RECORDS


def v3_reference_fingerprints() -> tuple[str, ...]:
    """v3 官方包 120 个 task_fingerprint（v4 holdout 零交集断言的实质参照）。"""
    return tuple(record["task_fingerprint"] for record in v3_package_records())


def make_fake_legacy() -> dict:
    """旧族 fixture（形状与 M2/M5/M6 清单一致；不依赖外部文件）。"""
    return {
        "task_ids": ["m2-deadbeef0001", "m5-deadbeef0002"],
        "task_fingerprints": [],  # 真实旧 M2/M5/M6 清单无指纹字段（R-06）
        "sources": [{"path": "<fixture>", "bytes": 0, "sha256": "f" * 64}],
    }


def build_bundle(legacy: dict | None = None) -> dict:
    return f3.build_freeze_bundle(
        run_id=RUN_ID,
        git_sha=GIT_SHA,
        created_utc=CREATED_UTC,
        code_sha=CODE_SHA,
        legacy=legacy if legacy is not None else make_fake_legacy(),
        v3_reference_task_fingerprints=v3_reference_fingerprints(),
    )


class V3FamilyIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = f3.build_v3_family_config()
        cls.tasks = f3.assign_v3_task_ids(
            tf.build_task_family(cls.config, holdout_seed=f3.HOLDOUT_SEED)
        )
        cls.records = f3.build_task_records(cls.tasks)
        cls.manifest = f3.build_split_manifest_v3(
            cls.tasks, family_config=cls.config, holdout_seed=f3.HOLDOUT_SEED
        )

    def test_01_config_identity(self):
        config = self.config
        self.assertEqual(config.family_id, "F-QE-feasible-v3")
        # 任务参数层仍为 p4ra-family-v3（数学任务族未变）；包/记录层升 p4ra-family-v4
        self.assertEqual(config.family_version, "p4ra-family-v3")
        self.assertEqual(config.family_version, f3.TASK_FAMILY_VERSION)
        self.assertEqual(config.family_version, tf.V3_FAMILY_VERSION)
        self.assertEqual(f3.FAMILY_VERSION, "p4ra-family-v4")
        self.assertEqual(f3.LEGACY_FAMILY_VERSIONS, ("p4ra-family-v3",))
        self.assertEqual(f3.HOLDOUT_SEED, tf.V4_HOLDOUT_SEED)
        self.assertEqual(f3.HOLDOUT_SPLITS, ("meta_test", "meta_test_ood"))
        self.assertEqual(f3.HOLDOUT_TASK_COUNT, 30)
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
        self.assertEqual(self.manifest["family_fingerprint"], f3.package_family_fingerprint(self.config))
        self.assertNotEqual(f3.package_family_fingerprint(self.config), tf.family_fingerprint(self.config))
        other_radius = f3.build_v3_family_config(radius_base=0.31)
        self.assertNotEqual(f3.package_family_fingerprint(other_radius), self.manifest["family_fingerprint"])
        other_seed = f3.build_v3_family_config(seed=20261106)
        self.assertNotEqual(f3.package_family_fingerprint(other_seed), self.manifest["family_fingerprint"])
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
        self.assertNotEqual(tf.family_fingerprint(v2), tf.family_fingerprint(self.config))
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
        self.assertEqual(report["assertion"], "TASK_ID_ZERO_INTERSECTION")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["physical_call_count"], 0)
        task_id_block = report["task_id_intersection"]
        self.assertEqual(task_id_block["assertion"], "TASK_ID_ZERO_INTERSECTION")
        self.assertEqual(task_id_block["status"], "PASS")
        self.assertEqual(task_id_block["evidence_class"], "SUBSTANTIVE")
        self.assertEqual(task_id_block["overlap_count"], 0)
        self.assertEqual(task_id_block["v3_task_id_count"], 120)
        self.assertEqual(task_id_block["legacy_task_id_count"], 2)
        fingerprint_block = report["task_fingerprint_intersection"]
        self.assertEqual(fingerprint_block["assertion"], "TASK_FINGERPRINT_INTERSECTION_UNDETERMINABLE")
        self.assertEqual(fingerprint_block["status"], "NOT_DETERMINABLE")
        self.assertEqual(fingerprint_block["evidence_class"], "UNAVAILABLE")
        self.assertEqual(fingerprint_block["legacy_task_fingerprint_count"], 0)
        self.assertEqual(report["intersections"], {"task_ids": [], "task_fingerprints": []})
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
        self.assertEqual(frozen["family_version"], "p4ra-family-v4")
        self.assertEqual(frozen["family_version"], f3.FAMILY_VERSION)
        self.assertEqual(frozen["task_family_version"], f3.TASK_FAMILY_VERSION)
        self.assertEqual(frozen["holdout_seed"], f3.HOLDOUT_SEED)
        self.assertEqual(frozen["holdout_splits"], list(f3.HOLDOUT_SPLITS))
        self.assertEqual(frozen["holdout_task_count"], 30)
        self.assertEqual(frozen["holdout_reseed"]["policy"], "R-V4-01")
        self.assertEqual(frozen["holdout_reseed"]["unchanged_splits"], ["meta_train", "meta_validation", "negative_control"])
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



class V3PreregContractSchemaTests(unittest.TestCase):
    """合同 §7：17 个规范字段 + 别名 + 严格 fail-closed 负控（B02/R-03）。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = build_bundle()
        cls.prereg = cls.bundle["preregistration"]
        cls.frozen = cls.bundle["frozen_family"]

    @staticmethod
    def _resign(payload: dict) -> dict:
        """按真实规则重算 prereg_digest 与 sha256（用于隔离被测字段）。"""
        body = {key: value for key, value in payload.items() if key != "sha256"}
        payload["prereg_digest"] = f3.compute_prereg_digest(body)
        payload["sha256"] = f3.digest(payload)
        return payload

    def _resigned_copy(self) -> dict:
        return json.loads(json.dumps(self.prereg))

    def test_01_seventeen_contract_fields_present(self):
        prereg = self.prereg
        self.assertEqual(len(f3.PREREG_REQUIRED_FIELDS), 17)
        expected = {
            "schema_version",
            "prereg_id",
            "family_version",
            "split_counts",
            "split_digest",
            "task_id_regex",
            "frozen_at_utc",
            "primary_endpoints",
            "secondary_metrics",
            "budget_plan",
            "task_counts",
            "seeds",
            "stopping_rules",
            "failure_rules",
            "multiple_comparison",
            "analysis_plan_digest",
            "prereg_digest",
        }
        self.assertEqual(set(f3.PREREG_REQUIRED_FIELDS), expected)
        for name in expected:
            self.assertIn(name, prereg)
        self.assertEqual(prereg["schema_version"], f3.PREREGISTRATION_SCHEMA_VERSION)
        self.assertTrue(f3._PREREG_ID_PATTERN.match(prereg["prereg_id"]))
        self.assertEqual(prereg["family_version"], "p4ra-family-v4")
        self.assertEqual(prereg["family_version"], f3.FAMILY_VERSION)
        self.assertEqual(prereg["task_family_version"], f3.TASK_FAMILY_VERSION)
        self.assertEqual(prereg["holdout_seed"], f3.HOLDOUT_SEED)
        self.assertEqual(prereg["holdout_splits"], list(f3.HOLDOUT_SPLITS))
        self.assertEqual(prereg["holdout_task_count"], 30)
        self.assertEqual(prereg["split_counts"], dict(f3.SPLIT_COUNTS))
        self.assertEqual(prereg["task_counts"], dict(f3.SPLIT_COUNTS))
        self.assertEqual(len(prereg["split_digest"]), 64)
        self.assertEqual(prereg["task_id_regex"], f3.TASK_ID_PATTERN.pattern)
        self.assertEqual(prereg["frozen_at_utc"], prereg["created_utc"])
        self.assertEqual(prereg["primary_endpoints"], list(f3.PRIMARY_ENDPOINTS))
        self.assertEqual(prereg["secondary_metrics"], list(f3.SECONDARY_METRICS))
        self.assertIsInstance(prereg["budget_plan"], dict)
        self.assertEqual(set(prereg["seeds"]), {"meta_train_seeds", "optimization_seeds"})
        self.assertGreaterEqual(len(prereg["seeds"]["meta_train_seeds"]), 3)
        self.assertGreaterEqual(len(prereg["seeds"]["optimization_seeds"]), 10)
        self.assertIsInstance(prereg["multiple_comparison"], dict)
        self.assertEqual(len(prereg["analysis_plan_digest"]), 64)
        self.assertEqual(len(prereg["prereg_digest"]), 64)
        self.assertTrue(f3.verify_preregistration_v3(prereg, self.frozen))

    def test_02_contract_literals_and_aliases(self):
        prereg = self.prereg
        self.assertEqual(
            prereg["task_id_regex"],
            "^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$",
        )
        self.assertEqual(prereg["task_id_pattern"], prereg["task_id_regex"])
        self.assertEqual(prereg["split_digest"], prereg["split_hash"])
        self.assertEqual(prereg["task_counts"], prereg["split_counts"])
        self.assertEqual(prereg["frozen_at_utc"], prereg["created_utc"])
        self.assertEqual(prereg["seeds"]["optimization_seeds"], prereg["optimization_seeds"])
        self.assertEqual(prereg["seeds"]["meta_train_seeds"], prereg["meta_seeds"])
        self.assertEqual(prereg["multiple_comparison"], f3.MULTIPLE_COMPARISON)
        self.assertEqual(prereg["analysis_plan_digest"], f3.ANALYSIS_PLAN_DIGEST)
        self.assertEqual(prereg["analysis_plan_digest"], f3.digest(prereg["analysis_plan"]))
        self.assertEqual(prereg["analysis_plan"]["endpoint_row_keys"], list(f3.ENDPOINT_ROW_KEYS))

    def test_03_budget_plan_contract(self):
        budget_plan = self.prereg["budget_plan"]
        self.assertEqual(budget_plan["plan_count"], 40)
        self.assertEqual(budget_plan["initial_designs"], 8)
        self.assertTrue(budget_plan["support_counted"])
        self.assertEqual(budget_plan["arms"], list(f3.ARM_IDS))
        self.assertEqual(budget_plan["budgets"], list(f3.BUDGETS))
        self.assertEqual(budget_plan["k_values"], list(f3.K_VALUES))
        self.assertEqual(budget_plan["physical_call_count"], 0)
        self.assertEqual(
            budget_plan["clone_pairs"],
            [{"K": 0, "clone_arm": "FOMAML-KSHOT-BO", "canonical_arm": "FOMAML-ZERO-BO"}],
        )
        self.assertEqual(budget_plan["inference_excluded"], {"0": ["FOMAML-KSHOT-BO"]})
        plans = bf.build_all_budget_plans()
        self.assertEqual(budget_plan["plans_digest"], f3.digest(plans))
        self.assertTrue(bf.assert_budget_fairness(plans))

    def test_04_prereg_digest_self_excluded(self):
        body = {key: value for key, value in self.prereg.items() if key != "sha256"}
        self.assertEqual(self.prereg["prereg_digest"], f3.compute_prereg_digest(body))
        # prereg_digest 计算时自身置空、且排除 sha256
        blanked = dict(body)
        blanked["prereg_digest"] = ""
        self.assertEqual(self.prereg["prereg_digest"], f3.digest(blanked))

    def test_05_missing_any_contract_field_fail_closed(self):
        for name in f3.PREREG_REQUIRED_FIELDS:
            payload = self._resigned_copy()
            payload.pop(name)
            body = {key: value for key, value in payload.items() if key != "sha256"}
            payload["sha256"] = f3.digest(body)
            with self.subTest(field=name):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.verify_preregistration_v3(payload, self.frozen)

    def test_06_alias_only_without_canonical_fail_closed(self):
        pairs = (
            ("split_digest", "split_hash"),
            ("task_id_regex", "task_id_pattern"),
            ("frozen_at_utc", "created_utc"),
            ("task_counts", "split_counts"),
        )
        for canonical, alias in pairs:
            payload = self._resigned_copy()
            self.assertIn(alias, payload)
            payload.pop(canonical)
            payload = self._resign(payload)
            with self.subTest(canonical=canonical, alias=alias):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.verify_preregistration_v3(payload, self.frozen)

    def test_07_wrong_types_and_values_fail_closed(self):
        def mutate(mutation):
            payload = self._resigned_copy()
            mutation(payload)
            return self._resign(payload)

        cases = {
            "multiple_comparison_str": lambda p: p.update({"multiple_comparison": "Holm-Bonferroni"}),
            "split_counts_list": lambda p: p.update({"split_counts": [60, 20, 20, 10, 10]}),
            "stopping_rules_str": lambda p: p.update({"stopping_rules": "单条"}),
            "seeds_list": lambda p: p.update({"seeds": [0, 1, 2]}),
            "budget_plan_list": lambda p: p.update({"budget_plan": []}),
            "task_id_regex_modified": lambda p: p.update({"task_id_regex": "^.*$"}),
            "forbidden_endpoint": lambda p: p.update(
                {"primary_endpoints": ["first_feasible_evaluation_index", "best_feasible_value", "gap_to_reference", "feasible_hit_rate"]}
            ),
            "frozen_at_mismatch": lambda p: p.update({"frozen_at_utc": "2026-11-05T00:00:01+00:00"}),
            "split_digest_mismatch": lambda p: p.update({"split_digest": "0" * 64}),
            "analysis_plan_digest_mismatch": lambda p: p.update({"analysis_plan_digest": "0" * 64}),
        }
        for name, mutation in cases.items():
            payload = mutate(mutation)
            with self.subTest(case=name):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.verify_preregistration_v3(payload, self.frozen)
        # prereg_digest 篡改（不重算自身）必须 fail-closed
        payload = self._resigned_copy()
        payload["prereg_digest"] = "0" * 64
        body = {key: value for key, value in payload.items() if key != "sha256"}
        payload["sha256"] = f3.digest(body)
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_preregistration_v3(payload, self.frozen)

    def test_08_build_rejects_bad_inputs(self):
        build_kwargs = dict(run_id=RUN_ID, created_utc=CREATED_UTC)
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_preregistration_v3(self.frozen, frozen_at_utc="2026-11-05T00:00:01+00:00", **build_kwargs)
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_preregistration_v3(self.frozen, multiple_comparison="Holm-Bonferroni", **build_kwargs)
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_preregistration_v3(self.frozen, failure_rules=[], **build_kwargs)
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_preregistration_v3(self.frozen, secondary_metrics=[], **build_kwargs)


class V3EndpointRowKeyTests(unittest.TestCase):
    """R-05：ENDPOINT_ROW_KEYS 9 键登记 + 分析 CSV 覆盖 fail-closed。"""

    @staticmethod
    def _row(**overrides):
        row = {key: 1.0 for key in f3.ENDPOINT_ROW_KEYS}
        row.update(overrides)
        return row

    def test_01_registry_is_nine_keys(self):
        self.assertEqual(len(f3.ENDPOINT_ROW_KEYS), 9)
        self.assertEqual(len(set(f3.ENDPOINT_ROW_KEYS)), 9)
        self.assertEqual(list(f3.ENDPOINT_ROW_KEYS[:4]), list(f3.PRIMARY_ENDPOINTS))
        self.assertEqual(
            list(f3.ENDPOINT_ROW_KEYS[4:]),
            [
                "first_feasible_in_support",
                "first_feasible_after_support_index",
                "feasible_hit_rate_non_support",
                "n_nonnull",
                "null_rate",
            ],
        )
        self.assertEqual(f3.ANALYSIS_PLAN["csv_columns"], list(f3.ENDPOINT_ROW_KEYS))
        self.assertEqual(f3.ANALYSIS_PLAN["endpoint_row_keys"], list(f3.ENDPOINT_ROW_KEYS))

    def test_02_coverage_accepts_registered_rows(self):
        rows = [self._row(), self._row(**{"gap_to_reference": None}), self._row(**{"n_nonnull": None})]
        coverage = f3.assert_endpoint_row_coverage(rows)
        self.assertEqual(coverage["row_count"], 3)
        self.assertEqual(set(coverage["nonnull_counts"]), set(f3.ENDPOINT_ROW_KEYS))
        self.assertEqual(coverage["nonnull_counts"]["gap_to_reference"], 2)
        self.assertEqual(coverage["nonnull_counts"]["n_nonnull"], 2)
        self.assertAlmostEqual(coverage["null_rates"]["gap_to_reference"], 1.0 / 3.0)
        self.assertEqual(coverage["null_rates"]["best_feasible_value"], 0.0)

    def test_03_missing_or_extra_keys_fail_closed(self):
        missing = self._row()
        missing.pop("null_rate")
        with self.assertRaises(f3.FamilyV3Error):
            f3.assert_endpoint_row_coverage([missing])
        extra = self._row()
        extra["first_feasible_evaluation_index"] = 1
        with self.assertRaises(f3.FamilyV3Error):
            f3.assert_endpoint_row_coverage([extra])
        renamed = self._row()
        renamed["first_feasible_evaluation_index"] = renamed.pop("first_feasible_eval_index")
        with self.assertRaises(f3.FamilyV3Error):
            f3.assert_endpoint_row_coverage([renamed])

    def test_04_all_null_main_endpoint_fail_closed(self):
        for endpoint in f3.PRIMARY_ENDPOINTS:
            rows = [self._row(**{endpoint: None}) for _ in range(3)]
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.assert_endpoint_row_coverage(rows)
        # 主端点也有非 null 行时通过（M5 全 null 故障负控）
        rows = [self._row(**{"best_feasible_value": None}), self._row()]
        self.assertEqual(f3.assert_endpoint_row_coverage(rows)["row_count"], 2)

    def test_05_empty_or_non_mapping_rows_fail_closed(self):
        for bad in ([], {}, "rows", [{"x": 1}], [1, 2]):
            with self.subTest(bad=bad):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.assert_endpoint_row_coverage(bad)


class V3IsolationEvidenceClassTests(unittest.TestCase):
    """R-06：task_id 实质零交集与 fingerprint 不可判定必须分列表述。"""

    @classmethod
    def setUpClass(cls):
        cls.v3_ids = [f"p4ra-FQE3-v3-TR-{index:03d}" for index in range(120)]
        cls.v3_fps = [f"ab{index:062x}" for index in range(120)]

    def _report(self, legacy):
        return f3.build_isolation_report(
            v3_task_ids=self.v3_ids,
            v3_task_fingerprints=self.v3_fps,
            legacy=legacy,
            created_utc=CREATED_UTC,
        )

    @staticmethod
    def _resign(report: dict) -> dict:
        body = {key: value for key, value in report.items() if key != "sha256"}
        report["sha256"] = f3.digest(body)
        return report

    def test_01_legacy_without_fingerprints_is_not_determinable(self):
        report = self._report(make_fake_legacy())
        self.assertEqual(report["task_id_intersection"]["status"], "PASS")
        self.assertEqual(report["task_fingerprint_intersection"]["status"], "NOT_DETERMINABLE")
        self.assertEqual(report["task_fingerprint_intersection"]["evidence_class"], "UNAVAILABLE")
        self.assertIn("limitations", report)
        self.assertEqual(len(report["limitations"]), 2)
        self.assertTrue(f3.verify_isolation_report(report))

    def test_02_forged_pass_fail_closed(self):
        report = self._report(make_fake_legacy())
        forged = json.loads(json.dumps(report))
        forged["task_fingerprint_intersection"].update(
            {"assertion": "TASK_FINGERPRINT_ZERO_INTERSECTION", "status": "PASS", "evidence_class": "SUBSTANTIVE"}
        )
        self._resign(forged)
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_isolation_report(forged)

    def test_03_legacy_with_fingerprints_substantive_pass(self):
        legacy = make_fake_legacy()
        legacy["task_fingerprints"] = ["0" * 64]
        report = self._report(legacy)
        block = report["task_fingerprint_intersection"]
        self.assertEqual(block["status"], "PASS")
        self.assertEqual(block["evidence_class"], "SUBSTANTIVE")
        self.assertEqual(block["legacy_task_fingerprint_count"], 1)
        self.assertTrue(f3.verify_isolation_report(report))

    def test_04_counts_consistent_in_verify(self):
        report = self._report(make_fake_legacy())
        tampered = json.loads(json.dumps(report))
        tampered["task_id_intersection"]["v3_task_id_count"] = 119
        self._resign(tampered)
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_isolation_report(tampered)
        tampered = json.loads(json.dumps(report))
        tampered["task_id_intersection"]["legacy_task_id_count"] = 3
        self._resign(tampered)
        with self.assertRaises(f3.FamilyV3Error):
            f3.verify_isolation_report(tampered)


class V3RadiusCalibrationTests(unittest.TestCase):
    """R-02：radius_base=0.64（A2 校准）必须显式传入并绑定 frozen/prereg。"""

    @classmethod
    def setUpClass(cls):
        cls.calibrated = f3.build_freeze_bundle(
            run_id=RUN_ID,
            git_sha=GIT_SHA,
            created_utc=CREATED_UTC,
            code_sha=CODE_SHA,
            legacy=make_fake_legacy(),
            radius_base=0.64,
            calibration_status="CALIBRATED",
            v3_reference_task_fingerprints=v3_reference_fingerprints(),
        )
        cls.default = build_bundle()

    def test_01_radius_bound_through_frozen_and_prereg(self):
        frozen = self.calibrated["frozen_family"]
        prereg = self.calibrated["preregistration"]
        self.assertAlmostEqual(float(frozen["radius_base"]), 0.64, places=12)
        self.assertAlmostEqual(float(prereg["radius_base"]), 0.64, places=12)
        self.assertAlmostEqual(float(self.calibrated["config"].radius_base), 0.64, places=12)
        calibration = frozen["calibration"]
        self.assertEqual(calibration["status"], "CALIBRATED")
        self.assertAlmostEqual(float(calibration["selected_radius_base"]), 0.64, places=12)
        self.assertEqual(calibration["radius_base_source"], "A2_calibration")
        self.assertTrue(f3.verify_frozen_family_v3(frozen))
        self.assertTrue(f3.verify_preregistration_v3(prereg, frozen))

    def test_02_radius_changes_fingerprint_not_split_hash(self):
        calibrated = self.calibrated["frozen_family"]
        default = self.default["frozen_family"]
        self.assertNotEqual(calibrated["family_fingerprint"], default["family_fingerprint"])
        self.assertEqual(calibrated["split"]["split_hash"], default["split"]["split_hash"])
        self.assertEqual(
            calibrated["family_fingerprint"], f3.package_family_fingerprint(self.calibrated["config"])
        )

    def test_03_config_supplied_must_match_radius(self):
        config = f3.build_v3_family_config(radius_base=0.32)
        with self.assertRaises(f3.FamilyV3Error):
            f3.build_freeze_bundle(
                config=config,
                run_id=RUN_ID,
                git_sha=GIT_SHA,
                created_utc=CREATED_UTC,
                legacy=make_fake_legacy(),
                radius_base=0.64,
                calibration_status="CALIBRATED",
            )


class V4HoldoutReseedTests(unittest.TestCase):
    """R-V4-01：仅 meta_test/meta_test_ood 重播种为 v4 族；train/val/NC 逐项不变。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = f3.build_freeze_bundle(
            run_id=RUN_ID,
            git_sha=GIT_SHA,
            created_utc=CREATED_UTC,
            code_sha=CODE_SHA,
            legacy=make_fake_legacy(),
            radius_base=0.64,
            calibration_status="CALIBRATED",
            v3_reference_task_fingerprints=v3_reference_fingerprints(),
        )
        cls.v3_records = v3_package_records()
        cls.v3_by_id = {record["task_id"]: record for record in cls.v3_records}
        cls.v4_records = cls.bundle["task_records"]
        cls.v3_manifest = json.loads(
            (V3_PACKAGE_ROOT / "meta_task_split.json").read_text(encoding="utf-8")
        )
        cls.v3_frozen = json.loads(
            (V3_PACKAGE_ROOT / "frozen_family.json").read_text(encoding="utf-8")
        )
        cls.v3_prereg = json.loads(
            (V3_PACKAGE_ROOT / "preregistration.json").read_text(encoding="utf-8")
        )

    def test_01_non_holdout_fingerprints_unchanged(self):
        for record in self.v4_records:
            if record["split"] in f3.HOLDOUT_SPLITS:
                continue
            reference = self.v3_by_id[record["task_id"]]
            self.assertEqual(record["task_fingerprint"], reference["task_fingerprint"], record["task_id"])
            self.assertEqual(record["params_digest"], reference["params_digest"], record["task_id"])
            self.assertEqual(record["seed"], reference["seed"], record["task_id"])
        holdout = [r for r in self.v4_records if r["split"] in f3.HOLDOUT_SPLITS]
        self.assertEqual(len(holdout), 30)

    def test_02_holdout_fingerprints_all_changed_and_zero_intersection(self):
        holdout = [r for r in self.v4_records if r["split"] in f3.HOLDOUT_SPLITS]
        v4_holdout_fps = {r["task_fingerprint"] for r in holdout}
        self.assertEqual(len(v4_holdout_fps), 30)
        for record in holdout:
            self.assertNotEqual(record["task_fingerprint"], self.v3_by_id[record["task_id"]]["task_fingerprint"], record["task_id"])
        v3_fps = {record["task_fingerprint"] for record in self.v3_records}
        self.assertEqual(v3_fps & v4_holdout_fps, set())
        holdout_block = self.bundle["isolation_report"]["holdout_fingerprint_intersection"]
        self.assertEqual(holdout_block["assertion"], "HOLDOUT_FINGERPRINT_ZERO_INTERSECTION")
        self.assertEqual(holdout_block["status"], "PASS")
        self.assertEqual(holdout_block["evidence_class"], "SUBSTANTIVE")
        self.assertEqual(holdout_block["holdout_task_count"], 30)
        self.assertEqual(holdout_block["v3_reference_task_fingerprint_count"], 120)
        self.assertEqual(holdout_block["overlap_count"], 0)
        self.assertTrue(f3.verify_isolation_report(self.bundle["isolation_report"]))

    def test_03_split_hash_unchanged_task_id_namespace_stable(self):
        ids = [task.task_id for task in self.bundle["tasks"]]
        self.assertEqual(len(ids), 120)
        self.assertEqual(len(set(ids)), 120)
        self.assertEqual(len(set(ids) & set(self.v3_by_id)), 120)
        self.assertEqual(
            self.bundle["split_manifest"]["split_hash"],
            self.v3_manifest["split_hash"],
        )
        self.assertEqual(self.bundle["split_manifest"]["family_version"], f3.FAMILY_VERSION)
        self.assertEqual(self.bundle["split_manifest"]["task_family_version"], f3.TASK_FAMILY_VERSION)

    def test_04_legacy_v3_package_still_verifies(self):
        self.assertTrue(f3.verify_frozen_family_v3(self.v3_frozen))
        self.assertTrue(f3.verify_preregistration_v3(self.v3_prereg, self.v3_frozen))
        self.assertTrue(f3.verify_split_manifest_v3(self.v3_manifest))
        self.assertEqual(self.v3_frozen["family_version"], "p4ra-family-v3")
        self.assertNotIn("holdout_fingerprint_intersection", f3.build_isolation_report(
            v3_task_ids=[record["task_id"] for record in self.v3_records],
            v3_task_fingerprints=[record["task_fingerprint"] for record in self.v3_records],
            legacy=make_fake_legacy(),
            created_utc=CREATED_UTC,
        ))

    def test_05_v4_tamper_fail_closed(self):
        for mutation in (
            lambda payload: payload.update({"holdout_seed": 20261107}),
            lambda payload: payload.update({"holdout_splits": ["meta_test"]}),
            lambda payload: payload.update({"task_family_version": "p4ra-family-v4"}),
            lambda payload: payload.update({"holdout_task_count": 20}),
            lambda payload: payload["holdout_reseed"].update({"policy": "R-V4-99"}),
        ):
            payload = json.loads(json.dumps(self.bundle["frozen_family"]))
            mutation(payload)
            body = {key: value for key, value in payload.items() if key != "sha256"}
            payload["sha256"] = f3.digest(body)
            with self.subTest(mutation=mutation):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.verify_frozen_family_v3(payload)
        for mutation in (
            lambda payload: payload.update({"holdout_seed": 20261107}),
            lambda payload: payload.update({"holdout_splits": ["meta_test"]}),
            lambda payload: payload.update({"task_family_version": "p4ra-family-v4"}),
        ):
            payload = json.loads(json.dumps(self.bundle["preregistration"]))
            mutation(payload)
            body = {key: value for key, value in payload.items() if key != "sha256"}
            payload["prereg_digest"] = f3.compute_prereg_digest(body | {"sha256": None})
            body = {key: value for key, value in payload.items() if key != "sha256"}
            payload["sha256"] = f3.digest(body)
            with self.subTest(mutation=mutation):
                with self.assertRaises(f3.FamilyV3Error):
                    f3.verify_preregistration_v3(payload, self.bundle["frozen_family"])

    def test_06_v4_identity_bound_across_artifacts(self):
        frozen = self.bundle["frozen_family"]
        prereg = self.bundle["preregistration"]
        manifest = self.bundle["split_manifest"]
        self.assertEqual(manifest["family_fingerprint"], frozen["family_fingerprint"])
        self.assertEqual(prereg["family_fingerprint"], frozen["family_fingerprint"])
        self.assertEqual(prereg["split_hash"], frozen["split"]["split_hash"])
        self.assertEqual(prereg["frozen_family_sha256"], frozen["sha256"])
        self.assertEqual(frozen["holdout_seed"], prereg["holdout_seed"])
        self.assertEqual(frozen["holdout_splits"], prereg["holdout_splits"])


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
