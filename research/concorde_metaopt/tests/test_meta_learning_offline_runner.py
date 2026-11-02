"""P4 离线编排（offline_runner）测试（设计 §11 / §12-9 / §12-14 / §12-15 / §12-18）。

覆盖：正常 run 的全部 §11.2 产物可解析且一致；data_manifest sha256/bytes；
physical_call_count=0 与禁用模块检查；确定性重跑；物理守卫违例立即中止且
不写正常 0 计数 summary；solver_validation.csv 与 fig4 NOT_RUN；正式默认参数断言。

所有产物写入临时目录（仓库外），不触碰 outputs/ 与已跟踪文件。
"""
import csv
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

import numpy as np

from research.concorde_metaopt.meta_learning import baseline_arms as ba
from research.concorde_metaopt.meta_learning import offline_runner as orun
from research.concorde_metaopt.meta_learning import task_family as tf

ALLOWED_SOLVER_STATUSES = {"NOT_RUN", "NOT_APPLICABLE_THIS_STAGE"}


def small_family_payload():
    config = tf.default_task_family_config(
        train_tasks=2,
        validation_tasks=1,
        test_tasks=1,
        ood_tasks=1,
        negative_control_tasks=1,
        support_pool_size=8,
        query_size=4,
        designs_per_task=12,
    )
    return asdict(config)


def write_family_config(path):
    path.write_text(json.dumps(small_family_payload(), ensure_ascii=False, indent=2), encoding="utf-8")


def small_runner_config(temp_root, run_id="p4-synthetic-unittest", **overrides):
    config_dir = Path(temp_root) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    family_path = config_dir / "family.json"
    write_family_config(family_path)
    payload = dict(
        run_id=run_id,
        output_root=Path(temp_root) / "runs",
        family_config_path=family_path,
        ks=(0, 1),
        seed=42,
        max_meta_steps=2,
        budget_true_evaluations=8,
        bo_initial_designs=8,
        de_population=8,
        de_generations=8,
        maml_init_candidate_count=32,
        maml_init_initial_designs=8,
        maml_init_diversity_candidate_count=32,
        determinism_reruns=2,
        optimization_seeds=(0,),
    )
    payload.update(overrides)
    return orun.OfflineRunnerConfig(**payload)


class OfflineRunnerProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="p4-meta-unittest-")
        cls.config = small_runner_config(cls.temp.name)
        cls.summary = orun.run_offline_study(cls.config)
        cls.run_dir = Path(cls.temp.name) / "runs" / cls.config.run_id

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_01_status_valid_and_physical_zero(self):
        self.assertEqual(self.summary["status"], "VALID", self.summary.get("error"))
        self.assertEqual(self.summary["physical_call_count"], 0)
        guard = self.summary["physics_guard"]
        self.assertEqual(guard["status"], "PASS")
        self.assertEqual(guard["end_assertion"], "PASS")
        self.assertEqual(guard["forbidden_modules_loaded"], [])
        # full-discover 进程可能已被既有 P1–P3 测试合法加载 RCAIDE 等模块；
        # 以当前快照为基线，验证「无新增禁止模块 + 本包源码零耦合」。
        baseline = orun._forbidden_modules_present()
        fresh = orun.assert_no_forbidden_modules(baseline)
        self.assertEqual(fresh["forbidden_modules_loaded"], [])
        self.assertEqual(fresh["source_scan_violations"], [])

    def test_02_required_products_exist_and_parse(self):
        expected = [
            "run_config.json",
            "environment.json",
            "summary.json",
            "tasks.json",
            "reference_solutions.json",
            "evaluations.jsonl",
            "README.md",
            "solver_validation.csv",
            "finite_difference_check.json",
            "data_manifest.json",
            "figures/figure_status.json",
            "metrics/training_history.csv",
            "metrics/adaptation_results.csv",
            "metrics/metrics.csv",
            "metrics/optimization_history.csv",
            "metrics/optimization_summary.csv",
        ]
        for relative in expected:
            self.assertTrue((self.run_dir / relative).is_file(), f"缺少产物 {relative}")
        for name in (
            "run_config.json",
            "environment.json",
            "summary.json",
            "tasks.json",
            "reference_solutions.json",
            "finite_difference_check.json",
        ):
            payload = json.loads((self.run_dir / name).read_text(encoding="utf-8"))
            self.assertIsInstance(payload, dict)
        lines = (self.run_dir / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 0)
        for line in lines:
            item = json.loads(line)
            self.assertIsInstance(item, dict)
            self.assertGreaterEqual(int(item.get("eval_index", 0)), 1)

    def test_03_metrics_csv_headers(self):
        for name, columns in orun.REQUIRED_CSV_COLUMNS.items():
            path = self.run_dir / "metrics" / f"{name}.csv"
            with path.open("r", encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))
            self.assertEqual(tuple(header), tuple(columns), f"{name}.csv 列不符")

    def test_04_data_manifest_consistency(self):
        manifest = json.loads((self.run_dir / "data_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["hash_mode"], "CRLF->LF")
        self.assertEqual(manifest["file_count"], len(manifest["files"]))
        self.assertNotIn("data_manifest.json", [item["path"] for item in manifest["files"]])
        total = 0
        for item in manifest["files"]:
            path = self.run_dir / item["path"]
            digest, size = orun.sha256_file_normalized(path)
            self.assertEqual(digest, item["sha256"], item["path"])
            self.assertEqual(size, item["bytes"], item["path"])
            total += item["bytes"]
        self.assertEqual(total, manifest["total_bytes"])
        self.assertIn("data_manifest.json", self.summary["products"])

    def test_05_determinism_pass(self):
        determinism = self.summary["determinism"]
        self.assertEqual(determinism["status"], "PASS")
        self.assertEqual(determinism["reruns"], 2)
        self.assertEqual(determinism["mismatched_files"], [])
        self.assertEqual(
            determinism["compared_files"],
            list(orun.DETERMINISM_COMPARE_FILES),
        )

    def test_06_solver_validation_and_figures(self):
        path = self.run_dir / "solver_validation.csv"
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertIn(row["status"], ALLOWED_SOLVER_STATUSES)
            self.assertEqual(row["run_id"], self.config.run_id)
            self.assertTrue(str(row.get("note", "")).strip())
        notes = " ".join(row["note"] for row in rows)
        self.assertIn("Issue #4", notes)
        self.assertIn("D-12D-004", notes)
        status = json.loads((self.run_dir / "figures" / "figure_status.json").read_text(encoding="utf-8"))
        figures = status["figures"]
        self.assertIn("fig4_constraint_handling", figures)
        self.assertIn("NOT_RUN", figures["fig4_constraint_handling"])
        self.assertIn("D-12D-004", figures["fig4_constraint_handling"])
        self.assertFalse(list((self.run_dir / "figures").glob("fig4*.png")))

    def test_07_run_config_and_summary_fields(self):
        run_config = json.loads((self.run_dir / "run_config.json").read_text(encoding="utf-8"))
        self.assertEqual(run_config["stage"], "P4-CODE")
        self.assertEqual(run_config["data_origin"], "SYNTHETIC_TEST")
        self.assertTrue(run_config["synthetic_only"])
        self.assertEqual(run_config["physical_call_declaration"]["physical_call_count"], 0)
        self.assertEqual(run_config["primary_endpoint"], orun.PRIMARY_ENDPOINT)
        self.assertEqual(run_config["evaluator_id"], orun.EVALUATOR_ID)
        self.assertEqual(tuple(run_config["secondary_endpoints"]), orun.SECONDARY_ENDPOINTS)
        self.assertEqual(tuple(run_config["actual_seeds"]), (0,))
        self.assertEqual(run_config["statistics"]["bootstrap_samples"], 10000)
        self.assertEqual(len(run_config["not_approved"]), 3)
        self.assertEqual(self.summary["not_approved"], run_config["not_approved"])
        self.assertEqual(run_config["maml_init"]["candidate_count"], self.config.maml_init_candidate_count)
        self.assertEqual(run_config["maml_init"]["initial_design_count"], self.config.maml_init_initial_designs)
        self.assertEqual(
            run_config["maml_init"]["diversity_candidate_count"],
            self.config.maml_init_diversity_candidate_count,
        )
        self.assertEqual(run_config["maml_init"]["dedup_tolerance"], 1e-12)
        fd_check = self.summary["finite_difference_check"]
        self.assertEqual(fd_check["status"], "PASS")
        self.assertGreaterEqual(int(fd_check["n_checked"]), 3)
        self.assertLessEqual(float(fd_check["max_relative_error"]), float(fd_check["tolerance"]))

    def test_08_fallback_metrics_present(self):
        path = self.run_dir / "metrics" / "optimization_summary.csv"
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        # 2 个 M2 评估任务（meta_test + meta_test_ood）× 1 seed × 5 臂
        self.assertEqual(len(rows), 2 * len(self.config.optimization_seeds) * len(ba.ARMS))
        for row in rows:
            self.assertIn(row["feasibility_expected_zero"], ("true", "unknown"))
            for column in ("best_objective_raw", "min_constraint_violation_sum", "feasible_hit_rate"):
                self.assertIn(column, row)
            # 无可行解时 best_feasible_value 必须为空（null），不得写 0
            if row["best_feasible_value"] == "":
                self.assertEqual(row["status"], "NO_FEASIBLE_SOLUTION")
            else:
                self.assertNotEqual(float(row["best_feasible_value"]), 0.0)

    def test_09_archive_dataset(self):
        archive_info = self.summary["archive"]
        self.assertEqual(archive_info["schema_version"], 2)
        self.assertEqual(archive_info["data_origin"], "SYNTHETIC_TEST")
        manifest_path = self.run_dir / archive_info["manifest_path"]
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(set(manifest["task_splits"].keys()), {"train", "validation", "test"})
        self.assertEqual(len(manifest["feature_names"]), 14)
        self.assertEqual(set(manifest["target_map"].keys()), set(manifest["target_names"]))
        from maml_opt.data.dataset import TaskDataset

        dataset = TaskDataset.load(manifest_path)
        records = [record for split in ("train", "validation", "test") for record in dataset.records_for_split(split)]
        self.assertGreater(len(records), 0)
        origins = {record.data_origin for record in records}
        self.assertEqual(origins, {"SYNTHETIC_TEST"})
        for record in records:
            self.assertGreaterEqual(record.analysis_calls, 1)

    def test_10_tasks_and_reference_solutions(self):
        tasks_payload = json.loads((self.run_dir / "tasks.json").read_text(encoding="utf-8"))
        self.assertIn("tasks", tasks_payload)
        # 2 train + 1 validation + 1 test + 1 OOD + 1 negative control
        self.assertEqual(len(tasks_payload["tasks"]), 6)
        reference = json.loads((self.run_dir / "reference_solutions.json").read_text(encoding="utf-8"))
        self.assertLessEqual(reference["max_residual"], reference["tolerance"])


class PhysicsGuardViolationTests(unittest.TestCase):
    def test_14_physical_call_guard_aborts_run(self):
        with tempfile.TemporaryDirectory(prefix="p4-meta-guard-") as temp_root:
            config = small_runner_config(
                temp_root,
                run_id="p4-synthetic-guard",
                determinism_reruns=1,
                ks=(0,),
            )
            real_factory = ba.make_synthetic_task_evaluator

            class ViolatingEvaluator:
                def __init__(self, inner):
                    self._inner = inner
                    self.physical_call_count = 0

                def __call__(self, design_u):
                    result = dict(self._inner(design_u))
                    result["physical_call_count"] = 1
                    self.physical_call_count = 1
                    return result

                def __getattr__(self, item):
                    return getattr(self._inner, item)

            def violating_factory(task, design_space):
                return ViolatingEvaluator(real_factory(task, design_space))

            with mock.patch.object(orun, "make_synthetic_task_evaluator", side_effect=violating_factory):
                summary = orun.run_offline_study(config)
            self.assertEqual(summary["status"], "PHYSICS_GUARD_VIOLATION")
            self.assertIn("立即中止整次 run", summary["error"]["message"])
            self.assertEqual(summary["products_written"], ["summary.json"])
            run_dir = Path(temp_root) / "runs" / config.run_id
            self.assertTrue((run_dir / "summary.json").is_file())
            # 不得写任何正常产物（尤其不得写出 0 计数的正常 summary）
            self.assertFalse((run_dir / "run_config.json").exists())
            self.assertFalse((run_dir / "metrics").exists())
            written = {path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*") if path.is_file()}
            self.assertEqual(written, {"summary.json"})
            on_disk = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk["status"], "PHYSICS_GUARD_VIOLATION")
            self.assertGreaterEqual(on_disk["physical_call_count"], 1)
            self.assertNotEqual(on_disk["physical_call_count"], 0)


class FiniteDifferenceGateTests(unittest.TestCase):
    """§7.2：FD 门禁必须执行；FAIL 时 M2 不得启动且如实落盘失败状态。"""

    def test_15_fd_check_file_and_summary(self):
        with tempfile.TemporaryDirectory(prefix="p4-meta-fd-") as temp_root:
            config = small_runner_config(temp_root, run_id="p4-synthetic-fd-gate", determinism_reruns=1)
            summary = orun.run_offline_study(config)
            run_dir = Path(temp_root) / "runs" / config.run_id
            self.assertEqual(summary["status"], "VALID", summary.get("error"))
            path = run_dir / "finite_difference_check.json"
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["fd_point"], "adapted_parameters")
            self.assertEqual(payload["epsilon"], 1e-5)
            self.assertEqual(payload["tolerance"], 1e-4)
            self.assertFalse(payload["equivalence_claimed"])
            self.assertEqual(summary["finite_difference_check"]["status"], "PASS")
            self.assertIn("finite_difference_check.json", summary["products"])

    def test_16_fd_failure_blocks_m2(self):
        with tempfile.TemporaryDirectory(prefix="p4-meta-fd-fail-") as temp_root:
            config = small_runner_config(temp_root, run_id="p4-synthetic-fd-fail", determinism_reruns=1)
            fake = {"status": "FAIL", "max_relative_error": 1.0, "n_checked": 0}
            with mock.patch.object(orun, "run_finite_difference_gate", return_value=fake) as gate:
                summary = orun.run_offline_study(config)
            self.assertEqual(gate.call_count, 1)
            self.assertEqual(summary["status"], "FINITE_DIFFERENCE_FAILED")
            self.assertEqual(
                summary["products_written"],
                ["summary.json", "finite_difference_check.json"],
            )
            self.assertEqual(summary["finite_difference_check"]["status"], "FAIL")
            self.assertIsNone(summary["physical_call_count"])
            run_dir = Path(temp_root) / "runs" / config.run_id
            self.assertTrue((run_dir / "summary.json").is_file())
            self.assertTrue((run_dir / "finite_difference_check.json").is_file())
            # M2 不得启动：不得写任何优化产物
            self.assertFalse((run_dir / "metrics").exists())
            self.assertFalse((run_dir / "evaluations.jsonl").exists())
            on_disk = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk["status"], "FINITE_DIFFERENCE_FAILED")


class FormalDefaultsTests(unittest.TestCase):
    def test_formal_defaults(self):
        config = orun.OfflineRunnerConfig(
            run_id="p4-synthetic-formal-defaults",
            output_root=Path(tempfile.gettempdir()) / "p4-formal-defaults",
            family_config_path=None,
        )
        self.assertEqual(config.optimization_seeds, (0, 1, 2, 3, 4))
        self.assertEqual(config.ks, (0, 1, 5, 10))
        self.assertEqual(config.budget_true_evaluations, 64)
        self.assertEqual(config.bo_initial_designs, 8)
        self.assertEqual((config.de_population, config.de_generations), (8, 8))
        self.assertEqual(
            (
                config.maml_init_candidate_count,
                config.maml_init_initial_designs,
                config.maml_init_diversity_candidate_count,
            ),
            (64, 8, 64),
        )
        self.assertEqual(config.determinism_reruns, 3)
        self.assertEqual(config.physical_guard_expected, 0)
        self.assertEqual(orun.S_ADAPT, 50)
        self.assertEqual(orun.M2_SEEDS, (0, 1, 2, 3, 4))

    def test_main_cli_small_config(self):
        with tempfile.TemporaryDirectory(prefix="p4-meta-main-") as temp_root:
            config_dir = Path(temp_root) / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            family_path = config_dir / "family.json"
            write_family_config(family_path)
            exit_code = orun.main(
                [
                    "--run-id",
                    "p4-synthetic-main",
                    "--output-root",
                    str(Path(temp_root) / "runs"),
                    "--family-config",
                    str(family_path),
                    "--max-meta-steps",
                    "1",
                    "--budget",
                    "8",
                    "--ks",
                    "0",
                    "--optimization-seeds",
                    "0",
                    "--determinism-reruns",
                    "1",
                ]
            )
            self.assertEqual(exit_code, 0)
            summary_path = Path(temp_root) / "runs" / "p4-synthetic-main" / "summary.json"
            self.assertTrue(summary_path.is_file())
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "VALID")
            self.assertEqual(payload["physical_call_count"], 0)


if __name__ == "__main__":
    unittest.main()
