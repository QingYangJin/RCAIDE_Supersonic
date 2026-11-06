"""S2 runner 单测（A1 所有；零物理，全部在临时目录内运行）。

覆盖：工具函数固定向量、数据边界负控、episode/bank 确定性（含跨进程）、FD 门禁、
训练/评估记录合同、资源停止路径、SMOKE 端到端两次独立 run 的确定性/产物校验/CLI。
"""
from __future__ import annotations

import copy
import dataclasses
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from research.concorde_metaopt.meta_learning import maml
from research.concorde_metaopt.meta_learning import s2_prereg as sp
from research.concorde_metaopt.meta_learning import s2_runner as runner

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = REPO_ROOT / sp.DEFAULT_PACKAGE_PATH
CREATED_UTC = "2026-11-07T00:00:00+00:00"
BANK_SHA = "0" * 64
RESOURCE_LIMITS = {"per_seed_train_wall_s": 1200, "peak_memory_mb": 8192, "total_wall_s": 7200}
SMOKE_OVERRIDES = {
    "outer_steps": 1,
    "meta_seeds": [0],
    "K": [0, 5],
    "draws": 1,
    "eval_tasks": 2,
    "batch_size": 2,
    "support_size": 4,
    "query_size": 8,
    "eval_query_size": 16,
    "fd_coordinates": 2,
}


def build_base_prereg() -> dict:
    return sp.build_preregistration(
        repo_root=REPO_ROOT,
        created_utc=CREATED_UTC,
        train_episode_bank_sha256=BANK_SHA,
    )


class RunnerUtilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prereg = build_base_prereg()

    def test_01_resource_limit_constants_are_ints(self) -> None:
        self.assertEqual(runner.RUN_RESOURCE_LIMITS, RESOURCE_LIMITS)
        for key, value in runner.RUN_RESOURCE_LIMITS.items():
            self.assertIsInstance(value, int)
            self.assertNotIsInstance(value, bool)
        self.assertEqual(runner.SEED_WALL_CLOCK_LIMIT_S, 1200)
        self.assertEqual(runner.PEAK_MEMORY_LIMIT_MB, 8192)
        self.assertEqual(runner.RUN_HARD_DEADLINE_S, 7200)

    def test_02_resource_limits_from_prereg(self) -> None:
        self.assertEqual(runner._resource_limits_from_prereg(self.prereg), RESOURCE_LIMITS)
        for mutate in ("missing", "extra", "float", "bool", "value"):
            payload = copy.deepcopy(self.prereg)
            if mutate == "missing":
                del payload["resource_limits"]["total_wall_s"]
            elif mutate == "extra":
                payload["resource_limits"]["extra"] = 1
            elif mutate == "float":
                payload["resource_limits"]["peak_memory_mb"] = 8192.0
            elif mutate == "bool":
                payload["resource_limits"]["peak_memory_mb"] = True
            else:
                payload["resource_limits"]["total_wall_s"] = 7201
            with self.assertRaises(runner.S2RunnerError):
                runner._resource_limits_from_prereg(payload)

    def test_03_canonical_hash_contract(self) -> None:
        expected = sp.sha256_text('{"a":1}\n')
        self.assertEqual(runner.canonical_sha256({"a": 1}), expected)
        self.assertEqual(sp.canonical_sha256({"a": 1}), expected)

    def test_04_record_core_excludes_timing(self) -> None:
        record = {"record_type": "train", "arm": "FOMAML", "wall_s": 1.5, "peak_memory_mb": 12.0}
        core = runner.record_core(record)
        self.assertEqual(core, {"record_type": "train", "arm": "FOMAML"})
        changed = dict(record)
        changed["wall_s"] = 99.0
        self.assertEqual(runner.record_core(changed), core)
        first = runner.records_core_sha256([record])
        second = runner.records_core_sha256([changed])
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_05_write_helpers_raw_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {"b": 2, "a": 1}
            written = root / "payload.json"
            sha = runner.write_json_canonical(written, payload)
            self.assertEqual(sha, sp.sha256_file(written))
            self.assertEqual(written.read_bytes(), ('{"a":1,"b":2}\n').encode("utf-8"))
            records = [{"record_type": "train", "x": 1.0}, {"record_type": "train", "x": 2.0}]
            path = root / "records.jsonl"
            lines_sha = runner.write_jsonl(path, records)
            self.assertEqual(lines_sha, sp.sha256_file(path))
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            for line, expected in zip(lines, records):
                self.assertEqual(line, sp.canonical_json(expected))

    def test_06_peak_memory_measured(self) -> None:
        value = runner.peak_memory_mb()
        self.assertIsInstance(value, float)
        self.assertGreater(value, 0.0)

    def test_07_config_from_arm(self) -> None:
        self.assertEqual([arm["id"] for arm in self.prereg["arms"]], ["FULL_MAML", "FOMAML"])
        configs = {str(arm["id"]): runner.config_from_arm(arm) for arm in self.prereg["arms"]}
        full = configs["FULL_MAML"]
        fomaml = configs["FOMAML"]
        self.assertFalse(full.first_order)
        self.assertTrue(fomaml.first_order)
        self.assertEqual(full, dataclasses.replace(fomaml, first_order=False))
        expected = maml.MAMLConfig(
            input_dim=12,
            output_dim=1,
            hidden_sizes=(16, 16),
            inner_lr=0.01,
            inner_steps=5,
            outer_lr=0.001,
            tasks_per_batch=8,
            first_order=False,
            seed=42,
            backend="torch",
        )
        self.assertEqual(full, expected)

    def test_08_array_rows_sha(self) -> None:
        features = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
        targets = np.asarray([0.5, -0.5], dtype=np.float64)
        manual = sp.sha256_bytes(
            b"".join(np.asarray(features, dtype="<f8").tobytes() for _ in [0])
        )
        self.assertEqual(runner.array_sha256(features), manual)
        first = runner.rows_sha256(features, targets)
        self.assertEqual(first, runner.rows_sha256(features.copy(), targets.copy()))
        self.assertEqual(len(first), 64)
        changed = targets.copy()
        changed[0] += 1.0
        self.assertNotEqual(first, runner.rows_sha256(features, changed))

    def test_09_v15_rules_fixed_in_prereg(self) -> None:
        self.assertEqual(self.prereg["resource_limits"], RESOURCE_LIMITS)
        self.assertEqual(list(self.prereg["failure_rules"]), list(sp.FAILURE_RULES))
        self.assertEqual(len(self.prereg["failure_rules"]), 3)
        self.assertIn("RESOURCE_LIMIT", self.prereg["failure_rules"][1])
        self.assertIn("no retry", self.prereg["failure_rules"][1])
        self.assertEqual(list(self.prereg["stopping_rules"]), list(sp.STOPPING_RULES))
        self.assertIn("total_wall_s>7200", self.prereg["stopping_rules"][-1])
        tampered = copy.deepcopy(self.prereg)
        tampered["resource_limits"]["peak_memory_mb"] = 8193
        self.assertNotEqual(sp.compute_prereg_digest(tampered), self.prereg["prereg_digest"])
        self.assertNotEqual(sp.compute_prereg_id(tampered), self.prereg["prereg_id"])


    def test_10_status_counts_always_two_buckets(self) -> None:
        counts = runner._status_counts(
            [
                {"record_type": "train", "status": "OK"},
                {"record_type": "train", "status": "FAILED"},
            ]
        )
        self.assertEqual(counts, {"train": {"OK": 1, "FAILED": 1}, "eval": {"OK": 0, "FAILED": 0}})
        empty = runner._status_counts([])
        self.assertEqual(empty, {"train": {"OK": 0, "FAILED": 0}, "eval": {"OK": 0, "FAILED": 0}})


class DataBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prereg = build_base_prereg()
        cls.tasks = runner.load_s2_tasks(PACKAGE)

    def test_01_split_counts_and_identity(self) -> None:
        self.assertEqual(len(self.tasks.meta_train), 60)
        self.assertEqual(len(self.tasks.meta_validation), 20)
        self.assertEqual(self.tasks.split_counts, dict(sp.EXPECTED_SPLIT_COUNTS))
        self.assertTrue(all(task.split == "meta_train" for task in self.tasks.meta_train))
        self.assertTrue(all(task.split == "meta_validation" for task in self.tasks.meta_validation))
        train_ids = {task.task_id for task in self.tasks.meta_train}
        validation_ids = {task.task_id for task in self.tasks.meta_validation}
        self.assertFalse(train_ids & validation_ids)

    def test_02_task_ids_sha_match_prereg(self) -> None:
        boundary = self.prereg["data_boundary"]
        self.assertEqual(self.tasks.meta_train_task_ids_sha256, boundary["meta_train_task_ids_sha256"])
        self.assertEqual(self.tasks.meta_validation_task_ids_sha256, boundary["meta_validation_task_ids_sha256"])
        self.assertEqual(self.tasks.holdout_task_ids_sha256, boundary["holdout_task_ids_sha256"])

    def test_03_expected_boundary_passes(self) -> None:
        loaded = runner.load_s2_tasks(PACKAGE, expected_boundary=self.prereg["data_boundary"])
        self.assertEqual(len(loaded.meta_train), 60)

    def test_04_expected_boundary_mismatch_rejected(self) -> None:
        boundary = copy.deepcopy(self.prereg["data_boundary"])
        boundary["holdout_task_ids_sha256"] = "f" * 64
        with self.assertRaises(runner.S2RunnerError) as caught:
            runner.load_s2_tasks(PACKAGE, expected_boundary=boundary)
        self.assertIn(sp.S2_DATA_BOUNDARY_ERROR, str(caught.exception))

    def test_05_unknown_split_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            records = [
                {"task_id": "x-1", "split": "bogus", "family": "F", "context": {}, "params": {}, "seed": 1}
            ]
            (package / "tasks.json").write_text(json.dumps(records), encoding="utf-8")
            with mock.patch.object(sp, "inspect_frozen_package", return_value={}):
                with self.assertRaises(runner.S2RunnerError) as caught:
                    runner.load_s2_tasks(package)
        self.assertIn(sp.S2_DATA_BOUNDARY_ERROR, str(caught.exception))

    def test_06_duplicate_task_id_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            records = [
                {"task_id": "dup", "split": "meta_train", "family": "F", "context": {}, "params": {}, "seed": 1},
                {"task_id": "dup", "split": "meta_train", "family": "F", "context": {}, "params": {}, "seed": 2},
            ]
            (package / "tasks.json").write_text(json.dumps(records), encoding="utf-8")
            with mock.patch.object(sp, "inspect_frozen_package", return_value={}):
                with self.assertRaises(runner.S2RunnerError) as caught:
                    runner.load_s2_tasks(package)
        self.assertIn(runner.S2_RUNNER_BANK_ERROR, str(caught.exception))

    def test_07_assert_allowed_split(self) -> None:
        runner.assert_allowed_split("meta_train")
        runner.assert_allowed_split("meta_validation")
        for split in sp.FORBIDDEN_SPLITS:
            with self.assertRaises(runner.S2RunnerError):
                runner.assert_allowed_split(split, task_id="t")

    def test_08_eval_episode_rejects_train_task(self) -> None:
        with self.assertRaises(runner.S2RunnerError) as caught:
            runner.build_eval_episode(self.tasks.meta_train[0], 0, 0, 0)
        self.assertIn(sp.S2_DATA_BOUNDARY_ERROR, str(caught.exception))

    def test_09_split_counts_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            records = [
                {"task_id": "only", "split": "meta_train", "family": "F", "context": {}, "params": {}, "seed": 1}
            ]
            (package / "tasks.json").write_text(json.dumps(records), encoding="utf-8")
            with mock.patch.object(sp, "inspect_frozen_package", return_value={}):
                with self.assertRaises(runner.S2RunnerError) as caught:
                    runner.load_s2_tasks(package)
        self.assertIn(sp.S2_DATA_BOUNDARY_ERROR, str(caught.exception))


class EpisodeBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = runner.load_s2_tasks(PACKAGE)

    def test_01_build_train_batch_deterministic(self) -> None:
        first_episodes, first_entries = runner.build_train_batch(
            self.tasks.meta_train, 0, 0, batch_size=2, support_size=4, query_size=8
        )
        second_episodes, second_entries = runner.build_train_batch(
            self.tasks.meta_train, 0, 0, batch_size=2, support_size=4, query_size=8
        )
        self.assertEqual(first_entries, second_entries)
        self.assertEqual(len(first_entries), 2)
        self.assertEqual([entry["position"] for entry in first_entries], [0, 1])
        self.assertTrue(all(entry["split"] == "meta_train" for entry in first_entries))
        for entry in first_entries:
            self.assertEqual(len(entry["support_rows_sha256"]), 64)
            self.assertEqual(len(entry["query_rows_sha256"]), 64)
        for first, second in zip(first_episodes, second_episodes):
            self.assertEqual(first.support_features.shape, (4, 12))
            self.assertEqual(first.query_features.shape, (8, 12))
            self.assertEqual(first.support_targets.shape, (4, 1))
            np.testing.assert_array_equal(first.support_features, second.support_features)
            np.testing.assert_array_equal(first.query_targets, second.query_targets)

    def test_02_build_train_batch_seed_sensitive(self) -> None:
        _, entries_a = runner.build_train_batch(self.tasks.meta_train, 0, 0, batch_size=2, support_size=4, query_size=8)
        _, entries_b = runner.build_train_batch(self.tasks.meta_train, 1, 0, batch_size=2, support_size=4, query_size=8)
        _, entries_c = runner.build_train_batch(self.tasks.meta_train, 0, 1, batch_size=2, support_size=4, query_size=8)
        self.assertNotEqual(
            [entry["support_rows_sha256"] for entry in entries_a],
            [entry["support_rows_sha256"] for entry in entries_b],
        )
        self.assertNotEqual(
            [entry["support_rows_sha256"] for entry in entries_a],
            [entry["support_rows_sha256"] for entry in entries_c],
        )

    def test_03_bank_manifest_shape_and_determinism(self) -> None:
        kwargs = dict(meta_seeds=[0, 1], outer_steps=2, batch_size=2, support_size=4, query_size=8)
        first = runner.build_train_episode_bank(self.tasks.meta_train, **kwargs)
        second = runner.build_train_episode_bank(self.tasks.meta_train, **kwargs)
        self.assertEqual(first["schema_version"], runner.S2_EPISODE_BANK_SCHEMA_VERSION)
        self.assertEqual(len(first["episodes"]), 2 * 2 * 2)
        self.assertEqual(first, second)
        first_sha = runner.episode_bank_sha256(first)
        self.assertEqual(first_sha, runner.episode_bank_sha256(second))
        self.assertEqual(len(first_sha), 64)

    def test_04_bank_cross_process_byte_identity(self) -> None:
        script = (
            "import json\n"
            "from pathlib import Path\n"
            "from research.concorde_metaopt.meta_learning import s2_runner as runner\n"
            "tasks = runner.load_s2_tasks(Path('research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z'))\n"
            "bank = runner.build_train_episode_bank(tasks.meta_train, meta_seeds=[0], outer_steps=2,"
            " batch_size=2, support_size=4, query_size=8)\n"
            "print(runner.episode_bank_sha256(bank))\n"
        )
        outputs = []
        for _ in range(2):
            completed = subprocess.run(
                [sys.executable, "-E", "-s", "-B", "-c", script],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            outputs.append(completed.stdout.strip())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(len(outputs[0]), 64)

    def test_05_bank_validation(self) -> None:
        with self.assertRaises(runner.S2RunnerError):
            runner.build_train_episode_bank(self.tasks.meta_train, meta_seeds=[0], outer_steps=0, batch_size=2, support_size=4, query_size=8)
        with self.assertRaises(runner.S2RunnerError):
            runner.build_train_episode_bank(self.tasks.meta_train, meta_seeds=[], outer_steps=1, batch_size=2, support_size=4, query_size=8)
        with self.assertRaises(runner.S2RunnerError):
            runner.build_train_batch(self.tasks.meta_train, 0, 0, batch_size=61, support_size=4, query_size=8)


class EvalEpisodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = runner.load_s2_tasks(PACKAGE)

    def test_01_k0_no_support_and_query_only_sampling(self) -> None:
        calls = []
        real = runner.sample_designs

        def spy(task, count, kind, seed):
            calls.append((count, kind))
            return real(task, count, kind, seed)

        task = self.tasks.meta_validation[0]
        with mock.patch.object(runner, "sample_designs", side_effect=spy):
            support, support_targets, query, query_targets = runner.build_eval_episode(task, 0, 0, 0, query_size=16)
        self.assertIsNone(support)
        self.assertIsNone(support_targets)
        self.assertEqual(query.shape, (16, 12))
        self.assertEqual(query_targets.shape, (16,))
        self.assertEqual([kind for _, kind in calls], ["query"])

    def test_02_k1_support_shape(self) -> None:
        task = self.tasks.meta_validation[0]
        support, support_targets, query, query_targets = runner.build_eval_episode(
            task, 0, 1, 0, query_size=64
        )
        self.assertEqual(support.shape, (1, 12))
        self.assertEqual(support_targets.shape, (1,))
        self.assertEqual(query.shape, (64, 12))
        self.assertEqual(query_targets.shape, (64,))

    def test_03_replay_and_draw_sensitivity(self) -> None:
        task = self.tasks.meta_validation[1]
        first = runner.build_eval_episode(task, 0, 5, 0, query_size=16)
        second = runner.build_eval_episode(task, 0, 5, 0, query_size=16)
        third = runner.build_eval_episode(task, 0, 5, 1, query_size=16)
        np.testing.assert_array_equal(first[0], second[0])
        np.testing.assert_array_equal(first[2], second[2])
        self.assertNotEqual(runner.array_sha256(first[2]), runner.array_sha256(third[2]))

    def test_04_negative_k_rejected(self) -> None:
        with self.assertRaises(runner.S2RunnerError):
            runner.build_eval_episode(self.tasks.meta_validation[0], 0, -1, 0)


class FDGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prereg = build_base_prereg()
        cls.tasks = runner.load_s2_tasks(PACKAGE)
        cls.configs = {str(arm["id"]): runner.config_from_arm(arm) for arm in cls.prereg["arms"]}

    def test_01_fd_gate_pass(self) -> None:
        payload = runner.run_fd_gate(
            self.tasks.meta_train,
            config=self.configs["FULL_MAML"],
            batch_size=2,
            support_size=4,
            query_size=8,
            max_coordinates=2,
            tolerance=1e-6,
        )
        self.assertEqual(payload["schema_version"], runner.S2_FD_GATE_SCHEMA_VERSION)
        self.assertEqual(payload["mode"], "full")
        self.assertEqual(payload["physical_call_count"], 0)
        result = payload["result"]
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["n_checked"], 2)
        self.assertLessEqual(result["max_relative_error"], 1e-6)
        self.assertEqual(len(payload["fd_gate_sha256"]), 64)

    def test_02_summarize_fd_gate(self) -> None:
        payload = runner.run_fd_gate(
            self.tasks.meta_train,
            config=self.configs["FULL_MAML"],
            batch_size=2,
            support_size=4,
            query_size=8,
            max_coordinates=2,
            tolerance=1e-6,
        )
        summary = runner.summarize_fd_gate(payload)
        self.assertEqual(summary["mode"], "full")
        self.assertEqual(summary["coordinates"], 2)
        self.assertEqual(summary["n_checked"], 2)
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["fd_gate_sha256"], payload["fd_gate_sha256"])
        self.assertLessEqual(summary["max_relative_error"], 1e-6)

    def test_03_fd_requires_full_maml(self) -> None:
        with self.assertRaises(runner.S2RunnerError):
            runner.run_fd_gate(
                self.tasks.meta_train,
                config=self.configs["FOMAML"],
                batch_size=2,
                support_size=4,
                query_size=8,
                max_coordinates=2,
            )

    def test_04_fd_payload_deterministic(self) -> None:
        kwargs = dict(
            config=self.configs["FULL_MAML"],
            batch_size=2,
            support_size=4,
            query_size=8,
            max_coordinates=2,
        )
        first = runner.run_fd_gate(self.tasks.meta_train, **kwargs)
        second = runner.run_fd_gate(self.tasks.meta_train, **kwargs)
        self.assertEqual(first["fd_gate_sha256"], second["fd_gate_sha256"])
        self.assertEqual(first["episode_keys_sha256"], second["episode_keys_sha256"])


class TrainEvaluateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prereg = build_base_prereg()
        cls.tasks = runner.load_s2_tasks(PACKAGE)
        cls.configs = {str(arm["id"]): runner.config_from_arm(arm) for arm in cls.prereg["arms"]}
        cls.base_trained = runner.train_arm(
            arm_id="FOMAML",
            run_id="unit-train",
            task_set=cls.tasks,
            config=cls.configs["FOMAML"],
            meta_seed=0,
            outer_steps=1,
            batch_size=2,
            support_size=4,
            query_size=8,
        )

    def test_01_train_fomaml_ok(self) -> None:
        result = self.base_trained
        self.assertEqual(result["status"], "OK")
        self.assertIsNone(result["failure"])
        self.assertEqual(len(result["records"]), 1)
        self.assertIsNotNone(result["parameters"])
        self.assertGreater(result["training_wall_s"], 0.0)
        self.assertGreater(result["peak_memory_mb"], 0.0)
        record = result["records"][0]
        self.assertEqual(set(record.keys()), set(runner.TRAIN_RECORD_FIELDS))
        for key in ("train_loss", "grad_norm", "inner_loss_first", "inner_loss_last"):
            self.assertTrue(np.isfinite(record[key]))
        self.assertEqual(record["status"], "OK")
        self.assertEqual(record["record_type"], "train")

    def test_02_train_full_maml_ok(self) -> None:
        result = runner.train_arm(
            arm_id="FULL_MAML",
            run_id="unit-train-full",
            task_set=self.tasks,
            config=self.configs["FULL_MAML"],
            meta_seed=0,
            outer_steps=1,
            batch_size=2,
            support_size=4,
            query_size=8,
        )
        self.assertEqual(result["status"], "OK")
        self.assertIsNotNone(result["parameters"])
        self.assertTrue(np.isfinite(result["records"][0]["train_loss"]))
        self.assertEqual(result["records"][0]["arm"], "FULL_MAML")

    def test_03_train_memory_resource_stop(self) -> None:
        with mock.patch.object(runner, "peak_memory_mb", return_value=9000.0):
            result = runner.train_arm(
                arm_id="FOMAML",
                run_id="unit-resource",
                task_set=self.tasks,
                config=self.configs["FOMAML"],
                meta_seed=0,
                outer_steps=2,
                batch_size=2,
                support_size=4,
                query_size=8,
                memory_limit_mb=8192,
            )
        self.assertEqual(result["status"], "RESOURCE_LIMIT")
        self.assertIn("RESOURCE_LIMIT", result["failure"])
        self.assertIsNone(result["parameters"])
        self.assertIsNone(result["peak_memory_mb"])
        self.assertEqual(len(result["records"]), 1)

    def test_04_train_failure_rows_have_null_metrics(self) -> None:
        with mock.patch.object(maml, "meta_train_step", side_effect=RuntimeError("boom")):
            result = runner.train_arm(
                arm_id="FOMAML",
                run_id="unit-failure",
                task_set=self.tasks,
                config=self.configs["FOMAML"],
                meta_seed=0,
                outer_steps=2,
                batch_size=2,
                support_size=4,
                query_size=8,
            )
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("boom", result["failure"])
        self.assertIsNone(result["parameters"])
        self.assertEqual(len(result["records"]), 1)
        record = result["records"][0]
        self.assertEqual(record["status"], "FAILED")
        for key in ("train_loss", "grad_norm", "inner_loss_first", "inner_loss_last", "peak_memory_mb"):
            self.assertIsNone(record[key])

    def test_05_train_deadline_exceeded(self) -> None:
        result = runner.train_arm(
            arm_id="FOMAML",
            run_id="unit-deadline",
            task_set=self.tasks,
            config=self.configs["FOMAML"],
            meta_seed=0,
            outer_steps=2,
            batch_size=2,
            support_size=4,
            query_size=8,
            run_started=time.perf_counter() - 100.0,
            hard_deadline_s=1.0,
        )
        self.assertEqual(result["status"], "DEADLINE_EXCEEDED")
        self.assertEqual(result["records"], [])

    def test_06_evaluate_records_contract(self) -> None:
        subset = dataclasses.replace(self.tasks, meta_validation=tuple(self.tasks.meta_validation[:2]))
        records = runner.evaluate_arm(
            arm_id="FOMAML",
            run_id="unit-eval",
            task_set=subset,
            parameters=self.base_trained["parameters"],
            config=self.configs["FOMAML"],
            meta_seed=0,
            k_values=[0, 5],
            draws=1,
            query_size=16,
        )
        self.assertEqual(len(records), 2 * 2 * 1)
        for record in records:
            self.assertEqual(set(record.keys()), set(runner.EVAL_RECORD_FIELDS))
            self.assertEqual(record["split"], "meta_validation")
            self.assertEqual(record["status"], "OK")
            self.assertEqual(record["support_size"], record["K"])
            self.assertEqual(record["adaptation_inner_steps"], record["K"])
            self.assertEqual(record["query_size"], 16)
            self.assertGreaterEqual(record["query_rmse_raw"], 0.0)
            if record["K"] < 2:
                self.assertIsNone(record["query_rmse_standardized"])
        k0 = [record for record in records if record["K"] == 0]
        self.assertTrue(k0)
        self.assertTrue(all(record["support_size"] == 0 for record in k0))

    def test_07_evaluate_standardized_rules(self) -> None:
        subset = dataclasses.replace(self.tasks, meta_validation=tuple(self.tasks.meta_validation[:1]))
        records = runner.evaluate_arm(
            arm_id="FOMAML",
            run_id="unit-eval-k2",
            task_set=subset,
            parameters=self.base_trained["parameters"],
            config=self.configs["FOMAML"],
            meta_seed=0,
            k_values=[2],
            draws=1,
            query_size=8,
        )
        self.assertEqual(len(records), 1)
        standardized = records[0]["query_rmse_standardized"]
        self.assertTrue(standardized is None or standardized >= 0.0)
        self.assertEqual(records[0]["adaptation_inner_steps"], 2)

    def test_08_measure_outer_step_timing(self) -> None:
        timing = runner.measure_outer_step_timing(
            self.tasks,
            arm={"id": "FOMAML", "first_order": True, "config": dict(self.prereg["arms"][1]["config"])},
            meta_seed=0,
            outer_step=0,
            batch_size=2,
            support_size=4,
            query_size=8,
        )
        self.assertEqual(timing["arm"], "FOMAML")
        self.assertEqual(timing["meta_seed"], 0)
        self.assertEqual(timing["outer_step"], 0)
        self.assertTrue(timing["first_order"])
        self.assertGreater(timing["wall_s"], 0.0)
        self.assertTrue(np.isfinite(timing["outer_loss"]))
        self.assertTrue(np.isfinite(timing["grad_norm"]))


class ResolveBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prereg = build_base_prereg()

    def test_01_formal_budget_from_prereg(self) -> None:
        budget = runner.resolve_budget(self.prereg, run_mode="FORMAL")
        self.assertEqual(budget["meta_seeds"], [0, 1, 2])
        self.assertEqual(budget["outer_steps"], 200)
        self.assertEqual(budget["k_values"], [0, 1, 5, 10])
        self.assertEqual(budget["draws"], 10)
        self.assertEqual(budget["fd_coordinates"], 32)
        self.assertEqual(budget["resource_limits"], RESOURCE_LIMITS)
        self.assertFalse(budget["smoke"])

    def test_02_smoke_requires_overrides(self) -> None:
        with self.assertRaises(runner.S2RunnerError) as caught:
            runner.resolve_budget(self.prereg, run_mode="SMOKE", smoke_overrides={"outer_steps": 1})
        self.assertIn(runner.S2_RUNNER_VALIDATION_ERROR, str(caught.exception))
        with self.assertRaises(runner.S2RunnerError):
            runner.resolve_budget(
                self.prereg,
                run_mode="SMOKE",
                smoke_overrides={**SMOKE_OVERRIDES, "unknown_key": 1},
            )

    def test_03_smoke_budget_recorded(self) -> None:
        budget = runner.resolve_budget(self.prereg, run_mode="SMOKE", smoke_overrides=SMOKE_OVERRIDES)
        self.assertTrue(budget["smoke"])
        self.assertEqual(budget["batch_size"], 2)
        self.assertEqual(budget["support_size"], 4)
        self.assertEqual(budget["query_size"], 8)
        self.assertEqual(budget["eval_query_size"], 16)
        self.assertEqual(budget["eval_task_limit"], 2)
        self.assertEqual(budget["fd_coordinates"], 2)
        self.assertEqual(budget["resource_limits"], RESOURCE_LIMITS)


class SmokeRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.prereg = build_base_prereg()
        cls.prereg_path = sp.write_preregistration(cls.prereg, root / "prereg.json")
        cls.run_a = root / "run_a"
        cls.run_b = root / "run_b"
        cls.summary_a = runner.run_experiment(
            out_dir=cls.run_a,
            run_id="smoke-a",
            prereg_path=cls.prereg_path,
            run_mode="SMOKE",
            smoke_overrides=SMOKE_OVERRIDES,
            created_utc=CREATED_UTC,
        )
        cls.summary_b = runner.run_experiment(
            out_dir=cls.run_b,
            run_id="smoke-a",
            prereg_path=cls.prereg_path,
            run_mode="SMOKE",
            smoke_overrides=SMOKE_OVERRIDES,
            created_utc=CREATED_UTC,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_01_summary_completed(self) -> None:
        summary = self.summary_a
        self.assertEqual(summary["status"], "COMPLETED")
        self.assertEqual(summary["record_counts"], {"train": 2, "eval": 8, "total": 10})
        self.assertEqual(summary["physical_call_count"], 0)
        self.assertEqual(summary["evidence_scope"], "DEVELOPMENT_VALIDATION_ONLY")
        self.assertEqual(summary["development_set"], "meta_validation")
        self.assertTrue(summary["smoke"])
        self.assertEqual(summary["resources"]["resource_limits"], RESOURCE_LIMITS)
        self.assertEqual(summary["resource_limits"], RESOURCE_LIMITS)
        self.assertEqual(summary["torch_threads"], 1)
        self.assertEqual(len(summary["outer_step_timing"]), 2)

    def test_02_run_config_contract(self) -> None:
        config = json.loads((self.run_a / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["schema_version"], runner.S2_RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(config["run_mode"], "SMOKE")
        self.assertEqual(config["physical_call_count"], 0)
        self.assertEqual(config["resource_limits"], RESOURCE_LIMITS)
        self.assertEqual(config["record_counts"]["train"], 2)
        self.assertEqual(config["record_counts"]["eval"], 8)
        self.assertEqual(config["record_counts"]["total"], 10)
        self.assertEqual(config["training_budget"]["meta_seeds"], [0])
        self.assertEqual(config["training_budget"]["outer_steps"], 1)
        self.assertEqual(config["evaluation_grid"]["K"], [0, 5])
        self.assertEqual(config["evaluation_grid"]["draws"], 1)
        self.assertEqual(config["evaluation_grid"]["meta_validation_tasks"], 2)
        self.assertEqual(config["data_boundary"]["holdout_rows_used"], 0)
        self.assertFalse(config["data_boundary"]["holdout_metrics_read"])
        self.assertEqual(config["record_schemas"]["train"], list(runner.TRAIN_RECORD_FIELDS))
        self.assertEqual(config["record_schemas"]["eval"], list(runner.EVAL_RECORD_FIELDS))
        self.assertEqual(config["fd_gate"]["mode"], "full")
        self.assertEqual(config["fd_gate"]["status"], "PASS")
        self.assertEqual(config["fd_gate"]["n_checked"], 2)
        self.assertTrue(config["fd_gate"]["override"])
        self.assertEqual(config["smoke_overrides"]["K"], [0, 5])
        self.assertEqual(config["episode_bank"]["episodes"], 2)
        arms = {str(arm["id"]): arm for arm in config["arms"]}
        self.assertEqual(set(arms), {"FULL_MAML", "FOMAML"})
        self.assertFalse(arms["FULL_MAML"]["first_order"])
        self.assertTrue(arms["FOMAML"]["first_order"])
        self.assertEqual(arms["FULL_MAML"]["config"], arms["FOMAML"]["config"])

    def test_03_validate_artifacts_ok(self) -> None:
        result = runner.validate_run_artifacts(self.run_a)
        self.assertTrue(result["ok"], [check for check in result["checks"] if not check["ok"]])
        names = {check["name"] for check in result["checks"]}
        for required in (
            "required_artifacts",
            "run_config_schema",
            "run_summary_schema",
            "physical_call_count_zero",
            "resource_limits_fixed",
            "data_boundary_holdout_untouched",
            "fd_gate_pass",
            "fd_gate_mode_full",
            "fd_gate_tolerance",
            "arms_exactly_two",
            "record_counts_match",
            "record_counts_expected",
            "record_fields",
            "record_values",
            "summary_run_config_sha",
            "summary_run_records_sha",
            "summary_run_records_core_sha",
            "summary_fd_gate_sha",
            "summary_data_manifest_sha",
            "summary_episode_bank_sha",
            "run_config_fields",
            "run_summary_fields",
            "run_summary_resources_fields",
            "status_counts_ok_failed",
            "summary_fields_v2",
        ):
            self.assertIn(required, names)
        self.assertEqual(result["run_status"], "COMPLETED")

    def test_04_compare_deterministic_runs(self) -> None:
        comparison = runner.compare_deterministic_runs(self.run_a, self.run_b)
        self.assertTrue(comparison["ok"], comparison)
        for key in (
            "run_config_byte_identical",
            "episode_bank_sha256_equal",
            "fd_gate_sha256_equal",
            "run_records_core_equal",
            "run_records_core_sha256_equal",
            "record_counts_equal",
        ):
            self.assertTrue(comparison[key], key)

    def test_05_records_contract_and_holdout_untouched(self) -> None:
        records = [
            json.loads(line)
            for line in (self.run_a / "run_records.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(len(records), 10)
        train = [record for record in records if record["record_type"] == "train"]
        evaluation = [record for record in records if record["record_type"] == "eval"]
        self.assertEqual(len(train), 2)
        self.assertEqual(len(evaluation), 8)
        for record in train:
            self.assertEqual(set(record.keys()), set(runner.TRAIN_RECORD_FIELDS))
        for record in evaluation:
            self.assertEqual(set(record.keys()), set(runner.EVAL_RECORD_FIELDS))
            self.assertEqual(record["split"], "meta_validation")
            self.assertIn(record["K"], (0, 5))
            if record["K"] == 0:
                self.assertIsNone(record["query_rmse_standardized"])
        self.assertEqual({record["K"] for record in evaluation}, {0, 5})
        manifest = json.loads((self.run_a / "data_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["holdout_rows_used"], 0)
        self.assertFalse(manifest["holdout_metrics_read"])
        self.assertEqual(manifest["physical_call_count"], 0)
        self.assertEqual(len(manifest["meta_train_task_ids"]), 60)
        self.assertEqual(len(manifest["meta_validation_task_ids"]), 2)

    def test_06_fig8_fig9_data_sources(self) -> None:
        summary = self.summary_a
        per_arm = summary["resources"]["per_arm"]
        self.assertIn("train_wall_seconds_ratio", summary["resources"])
        self.assertEqual(set(per_arm), {"FULL_MAML", "FOMAML"})
        for arm_stats in per_arm.values():
            self.assertEqual(set(arm_stats), set(
                ["meta_seeds", "train_wall_seconds_per_meta_seed", "train_wall_seconds_mean", "peak_memory_mb_max"]
            ))
            self.assertEqual(arm_stats["meta_seeds"], [0])
            self.assertEqual(list(arm_stats["train_wall_seconds_per_meta_seed"]), ["0"])
            self.assertGreater(arm_stats["train_wall_seconds_mean"], 0.0)
            self.assertGreater(arm_stats["peak_memory_mb_max"], 0.0)
        ratio = summary["resources"]["train_wall_seconds_ratio"]
        self.assertIsInstance(ratio, float)
        self.assertGreater(ratio, 0.0)
        records = [
            json.loads(line)
            for line in (self.run_a / "run_records.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        k5 = [record for record in records if record["record_type"] == "eval" and record["K"] == 5]
        self.assertEqual(len(k5), 4)
        for record in k5:
            for key in ("arm", "task_id", "K", "query_rmse_raw"):
                self.assertIn(key, record)
        task_ids = {record["task_id"] for record in k5}
        self.assertEqual(len(task_ids), 2)

    def test_07_negative_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "run_broken"
            shutil.copytree(self.run_a, broken)
            (broken / "fd_gate.json").unlink()
            result = runner.validate_run_artifacts(broken)
            self.assertFalse(result["ok"])
            self.assertEqual(result["checks"][0]["name"], "required_artifacts")
            self.assertFalse(result["checks"][0]["ok"])

    def test_08_negative_tampered_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "run_tampered"
            shutil.copytree(self.run_a, broken)
            path = broken / "run_records.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
            result = runner.validate_run_artifacts(broken)
            self.assertFalse(result["ok"])
            failed = {check["name"] for check in result["checks"] if not check["ok"]}
            self.assertIn("summary_run_records_sha", failed)

    def test_09_cli_validate_and_compare(self) -> None:
        module = "research.concorde_metaopt.meta_learning.s2_runner"
        valid = subprocess.run(
            [sys.executable, "-E", "-s", "-B", "-m", module, "validate", "--run-dir", str(self.run_a)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertTrue(json.loads(valid.stdout)["ok"])
        comparison = subprocess.run(
            [sys.executable, "-E", "-s", "-B", "-m", module, "compare", "--dir-a", str(self.run_a), "--dir-b", str(self.run_b)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(comparison.returncode, 0, comparison.stderr)
        self.assertTrue(json.loads(comparison.stdout)["ok"])
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            broken = subprocess.run(
                [sys.executable, "-E", "-s", "-B", "-m", module, "validate", "--run-dir", str(empty)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=300,
            )
        self.assertEqual(broken.returncode, 1)
        self.assertFalse(json.loads(broken.stdout)["ok"])

    def test_10_preflight_smoke(self) -> None:
        pre = runner.preflight(
            prereg_path=self.prereg_path,
            run_mode="SMOKE",
            smoke_overrides=SMOKE_OVERRIDES,
        )
        self.assertEqual(len(pre["task_set"].meta_train), 60)
        self.assertEqual(len(pre["eval_tasks"]), 2)
        self.assertEqual(len(pre["bank_manifest"]["episodes"]), 2)
        self.assertFalse(pre["bank_sha256_matches_prereg"])
        self.assertEqual(pre["fd_payload"]["result"]["status"], "PASS")
        self.assertEqual(pre["fd_payload"]["result"]["n_checked"], 2)
        self.assertEqual(set(pre["configs"]), {"FULL_MAML", "FOMAML"})
        self.assertEqual(pre["budget"]["resource_limits"], RESOURCE_LIMITS)

    def test_11_refuse_overwrite(self) -> None:
        with self.assertRaises(runner.S2RunnerError):
            runner.run_experiment(
                out_dir=self.run_a,
                run_id="smoke-a2",
                prereg_path=self.prereg_path,
                run_mode="SMOKE",
                smoke_overrides=SMOKE_OVERRIDES,
                created_utc=CREATED_UTC,
            )

    def test_12_summary_v2_contract(self) -> None:
        summary = self.summary_a
        config = json.loads((self.run_a / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], sp.RUN_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(set(summary), set(sp.RUN_SUMMARY_REQUIRED_FIELDS))
        self.assertEqual(summary["run_mode"], "SMOKE")
        self.assertTrue(summary["smoke"])
        self.assertEqual(
            summary["status_counts"],
            {"train": {"OK": 2, "FAILED": 0}, "eval": {"OK": 8, "FAILED": 0}},
        )
        self.assertEqual(summary["per_arm_seed"], {"FULL_MAML": [0], "FOMAML": [0]})
        self.assertEqual(summary["per_arm_seed"], runner.per_arm_seed_from_summary(summary))
        self.assertEqual(summary["fd_pilot_artifacts"], config["fd_gate"]["pilot_artifacts"])
        self.assertEqual(summary["scope_notes"], config["scope_notes"])
        auxiliary = summary["resources"]["auxiliary_compute"]
        self.assertEqual(set(auxiliary), set(sp.AUXILIARY_COMPUTE_FIELDS))
        self.assertEqual(auxiliary["outer_step_timing_measurements"], len(summary["outer_step_timing"]))
        self.assertEqual(auxiliary["physical_call_count"], 0)
        self.assertIsInstance(auxiliary["note"], str)
        self.assertTrue(auxiliary["note"])

    def test_13_resources_v2_contract(self) -> None:
        resources = self.summary_a["resources"]
        self.assertEqual(set(resources), set(sp.RUN_SUMMARY_RESOURCES_FIELDS))
        self.assertEqual(resources["resource_limits"], RESOURCE_LIMITS)
        self.assertGreater(resources["run_wall_s"], 0.0)
        self.assertIsInstance(resources["train_wall_seconds_ratio"], float)
        self.assertEqual(len(resources["per_seed"]), 2)
        for item in resources["per_seed"]:
            self.assertEqual(set(item), set(sp.PER_SEED_RESOURCE_FIELDS))
        self.assertEqual(set(resources["per_arm"]), {"FULL_MAML", "FOMAML"})
        for arm_stats in resources["per_arm"].values():
            self.assertEqual(set(arm_stats), set(sp.PER_ARM_RESOURCE_FIELDS))
        self.assertEqual(
            set(resources["auxiliary_compute"]),
            set(sp.AUXILIARY_COMPUTE_FIELDS),
        )

    def test_14_run_config_v2_contract(self) -> None:
        config = json.loads((self.run_a / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["schema_version"], sp.RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(set(config), set(sp.RUN_CONFIG_REQUIRED_FIELDS) | set(sp.RUN_CONFIG_OPTIONAL_FIELDS))
        self.assertEqual(config["run_mode"], "SMOKE")
        self.assertEqual(set(config["fd_gate"]), set(sp.FD_GATE_FIELDS))
        self.assertEqual(set(config["episode_bank"]), set(sp.EPISODE_BANK_FIELDS))
        self.assertTrue(config["fd_gate"]["override"])
        self.assertEqual(config["smoke_overrides"]["outer_steps"], 1)
        self.assertEqual(config["smoke_overrides"]["meta_seeds"], [0])
        self.assertEqual(config["smoke_overrides"]["K"], [0, 5])
        self.assertEqual(config["smoke_overrides"]["draws"], 1)
        self.assertEqual(config["smoke_overrides"]["eval_tasks"], 2)
        self.assertEqual(config["smoke_overrides"]["fd_coordinates"], 2)

    def test_15_runner_schema_constants_single_source(self) -> None:
        self.assertEqual(runner.S2_RUN_CONFIG_SCHEMA_VERSION, sp.RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(runner.S2_RUN_SUMMARY_SCHEMA_VERSION, sp.RUN_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(runner.RUN_RESOURCE_LIMITS, dict(sp.RUN_RESOURCE_LIMITS))
        self.assertEqual(runner.RUN_STATUSES, sp.RUN_STATUSES)
        self.assertEqual(runner.SEED_STATUSES, sp.SEED_STATUSES)
        self.assertEqual(runner.RECORD_STATUS_COUNTS, sp.RECORD_STATUS_COUNTS)
        self.assertEqual(runner.S2_RUN_CONFIG_SCHEMA_VERSION, "p4ra-s2-run-config-v2")

    def _tampered_run(self, root: str, mutate_config=None, mutate_summary=None) -> Path:
        broken = Path(root) / "run_tampered_v2"
        shutil.copytree(self.run_a, broken)
        if mutate_config is not None:
            config = json.loads((broken / "run_config.json").read_text(encoding="utf-8"))
            mutate_config(config)
            payload = json.dumps(config, ensure_ascii=False) + chr(10)
            (broken / "run_config.json").write_text(payload, encoding="utf-8")
        if mutate_summary is not None:
            summary = json.loads((broken / "run_summary.json").read_text(encoding="utf-8"))
            mutate_summary(summary)
            payload = json.dumps(summary, ensure_ascii=False) + chr(10)
            (broken / "run_summary.json").write_text(payload, encoding="utf-8")
        return broken

    def _assert_check_fails(self, broken: Path, expected_check: str) -> dict:
        result = runner.validate_run_artifacts(broken)
        self.assertFalse(result["ok"])
        failed = {check["name"] for check in result["checks"] if not check["ok"]}
        self.assertIn(expected_check, failed, sorted(failed))
        return result

    def test_16_negative_v2_schema_fail_closed(self) -> None:
        cases = [
            ("run_config_fields", lambda config: config.pop("determinism"), None),
            ("run_config_schema", lambda config: config.__setitem__("schema_version", "p4ra-s2-run-config-v1"), None),
            ("run_summary_fields", None, lambda summary: summary.pop("run_mode")),
            ("run_summary_schema", None, lambda summary: summary.__setitem__("schema_version", "p4ra-s2-run-summary-v1")),
            ("run_summary_resources_fields", None, lambda summary: summary["resources"].pop("auxiliary_compute")),
            ("status_counts_ok_failed", None, lambda summary: summary["status_counts"]["train"].pop("FAILED")),
            ("summary_fields_v2", None, lambda summary: summary.__setitem__("per_arm_seed", {})),
        ]
        for expected_check, mutate_config, mutate_summary in cases:
            with tempfile.TemporaryDirectory() as tmp:
                broken = self._tampered_run(tmp, mutate_config=mutate_config, mutate_summary=mutate_summary)
                self._assert_check_fails(broken, expected_check)

    def test_17_formal_run_summary_run_mode(self) -> None:
        prereg = self.prereg
        task_set = runner.load_s2_tasks(PACKAGE)
        budget = runner.resolve_budget(prereg, run_mode="FORMAL")
        configs = {str(arm["id"]): runner.config_from_arm(arm) for arm in prereg["arms"]}
        fake_bank = {
            "episodes": [],
            "meta_seeds": [0, 1, 2],
            "outer_steps": 200,
            "batch_size": 8,
            "support_size": 16,
            "query_size": 32,
        }
        fake_fd = {
            "result": {
                "mode": "full",
                "tolerance": 1e-6,
                "status": "PASS",
                "n_checked": 32,
                "coordinates_requested": 32,
                "coordinates_available": 185,
                "max_relative_error": 1e-9,
            },
            "fd_gate_sha256": "f" * 64,
        }
        pre = {
            "prereg": prereg,
            "budget": budget,
            "task_set": task_set,
            "eval_tasks": list(task_set.meta_validation),
            "bank_manifest": fake_bank,
            "bank_sha256": BANK_SHA,
            "fd_payload": fake_fd,
            "arms": prereg["arms"],
            "configs": configs,
        }

        def fake_timing(_task_set, **kwargs):
            return {
                "arm": str(kwargs.get("arm") if isinstance(kwargs.get("arm"), str) else "FULL_MAML"),
                "meta_seed": int(kwargs.get("meta_seed", 0)),
                "outer_step": int(kwargs.get("outer_step", 0)),
                "wall_s": 0.5,
                "outer_loss": 1.0,
                "grad_norm": 0.1,
                "first_order": False,
            }

        def fake_train(**kwargs):
            records = [
                {
                    "record_type": "train",
                    "arm": kwargs["arm_id"],
                    "meta_seed": kwargs["meta_seed"],
                    "outer_step": step,
                    "status": "OK",
                }
                for step in range(200)
            ]
            return {
                "arm": kwargs["arm_id"],
                "meta_seed": kwargs["meta_seed"],
                "status": "OK",
                "failure": None,
                "records": records,
                "parameters": {"w": 0.0},
                "training_wall_s": 0.1,
                "peak_memory_mb": 1.0,
                "seed_elapsed_s": 0.1,
            }

        def fake_eval(**kwargs):
            records = []
            for task in kwargs["task_set"].meta_validation:
                for k_shot in kwargs["k_values"]:
                    for draw in range(kwargs["draws"]):
                        records.append(
                            {
                                "record_type": "eval",
                                "arm": kwargs["arm_id"],
                                "meta_seed": kwargs["meta_seed"],
                                "task_id": task.task_id,
                                "split": "meta_validation",
                                "K": k_shot,
                                "draw": draw,
                                "status": "OK",
                            }
                        )
            return records

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            with mock.patch.object(runner, "preflight", return_value=pre), mock.patch.object(
                runner, "measure_outer_step_timing", side_effect=fake_timing
            ), mock.patch.object(runner, "train_arm", side_effect=fake_train), mock.patch.object(
                runner, "evaluate_arm", side_effect=fake_eval
            ):
                summary = runner.run_experiment(
                    out_dir=tmp_root / "formal_mock",
                    run_id="formal-mock",
                    prereg_path=tmp_root / "prereg.json",
                    run_mode="FORMAL",
                    created_utc=CREATED_UTC,
                )
                config = json.loads((tmp_root / "formal_mock" / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["run_mode"], "FORMAL")
        self.assertFalse(summary["smoke"])
        self.assertEqual(summary["record_counts"], {"train": 1200, "eval": 4800, "total": 6000})
        self.assertEqual(set(summary), set(sp.RUN_SUMMARY_REQUIRED_FIELDS))
        self.assertEqual(
            summary["status_counts"],
            {"train": {"OK": 1200, "FAILED": 0}, "eval": {"OK": 4800, "FAILED": 0}},
        )
        self.assertEqual(summary["per_arm_seed"], {"FULL_MAML": [0, 1, 2], "FOMAML": [0, 1, 2]})
        self.assertEqual(config["run_mode"], "FORMAL")
        self.assertNotIn("smoke_overrides", config)
        self.assertEqual(set(config), set(sp.RUN_CONFIG_REQUIRED_FIELDS))
        self.assertEqual(set(config["fd_gate"]), set(sp.FD_GATE_FIELDS))
        self.assertEqual(set(config["episode_bank"]), set(sp.EPISODE_BANK_FIELDS))
        self.assertEqual(config["training_budget"]["outer_steps"], 200)
        self.assertEqual(config["training_budget"]["train_records_expected"], 1200)
        self.assertEqual(config["evaluation_grid"]["meta_validation_tasks"], 20)
        self.assertEqual(config["evaluation_grid"]["eval_records_expected"], 4800)


if __name__ == "__main__":
    unittest.main()