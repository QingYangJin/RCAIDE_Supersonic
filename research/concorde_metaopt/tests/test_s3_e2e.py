"""S3 端到端测试（真 SMOKE，零物理求解）：两次同 run_id 运行 -> 产物校验 + 确定性对比。

边界：SMOKE 在 run 内重训微型模型并重算 FD 门，全部为纯解析合成评估；
不写仓库、不启动真实 solver（VLM/CFD/SU2/Gmsh 零调用）；physical_call_count=0。
"""
import unittest
from pathlib import Path
from unittest import mock

from research.concorde_metaopt.meta_learning import m5_arms as m5
from research.concorde_metaopt.meta_learning import s3_prereg as sp
from research.concorde_metaopt.meta_learning import s3_runner as runner
from research.concorde_metaopt.tests import test_s3_support as support


_RUN_ID = "s3-e2e-smoke"
_SMOKE = {
    "outer_steps": 1,
    "meta_seeds": [0],
    "budgets": [64],
    "opt_seeds": [0],
    "eval_tasks": 2,
    "k_sweep": [5],
    "fd_coordinates": 2,
}
_EXPECTED_MAIN_RUNS = 5 * 2 * 1 * 1 * 1  # 5 臂 x 2 eval task x 1 budget x 1 meta x 1 opt
_EXPECTED_EVAL_RECORDS = _EXPECTED_MAIN_RUNS * int(_SMOKE["budgets"][0])
_EXPECTED_TRAIN_RECORDS = len(sp.S3_MODEL_KINDS) * int(_SMOKE["outer_steps"])


class S3SmokeEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = support.SyntheticRepoCase()
        cls.info = cls.case.get_repo()
        cls.tmp = support.tempfile.TemporaryDirectory(prefix="s3-e2e-out-")
        base = Path(cls.tmp.name)
        cls.run_a = base / "run_a"
        cls.run_b = base / "run_b"
        cls.result_a = runner.run_experiment(
            out_dir=cls.run_a,
            run_id=_RUN_ID,
            prereg_path=cls.info["prereg_path"],
            repo_root=cls.info["repo"],
            run_mode="SMOKE",
            smoke_overrides=_SMOKE,
            parallel_workers=1,
            created_utc=support.CREATED_UTC,
            verify_code_sha=False,
        )
        cls.result_b = runner.run_experiment(
            out_dir=cls.run_b,
            run_id=_RUN_ID,
            prereg_path=cls.info["prereg_path"],
            repo_root=cls.info["repo"],
            run_mode="SMOKE",
            smoke_overrides=_SMOKE,
            parallel_workers=1,
            created_utc=support.CREATED_UTC,
            verify_code_sha=False,
        )
        cls.config = runner.read_json_file(cls.run_a / runner.S3_RUNNER_CONFIG_FILE)
        cls.summary = cls.result_a["summary"]
        cls.data_manifest = runner.read_json_file(cls.run_a / runner.S3_RUNNER_DATA_MANIFEST_FILE)
        cls.execution_report = cls.result_a["execution_report"]
        cls.gate = runner.read_json_file(cls.run_a / runner.S3_RUNNER_GATE_FILE)
        cls.model_manifest = runner.read_json_file(cls.run_a / runner.S3_RUNNER_MODEL_MANIFEST_FILE)
        cls.records = runner.read_jsonl(cls.run_a / runner.S3_RUNNER_RECORD_FILE)

    @classmethod
    def tearDownClass(cls):
        cls.case.cleanup_repo()
        cls.tmp.cleanup()

    # -- 基础产物与 schema ---------------------------------------------------
    def test_required_artifacts_exist(self):
        for name in runner.S3_RUNNER_REQUIRED_ARTIFACTS:
            self.assertTrue((self.run_a / name).is_file(), name)
        for name in (
            "models/fomaml_meta_0.json",
            "models/anil_meta_0.json",
            "models/episode_bank_meta_0.jsonl",
        ):
            self.assertTrue((self.run_a / name).is_file(), name)

    def test_run_config_fields_and_grid(self):
        self.assertEqual(
            set(self.config),
            set(sp.S3_RUN_CONFIG_REQUIRED_FIELDS) | set(sp.S3_RUN_CONFIG_OPTIONAL_FIELDS),
        )
        self.assertEqual(self.config["schema_version"], sp.S3_RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(self.config["run_id"], _RUN_ID)
        self.assertEqual(self.config["run_mode"], "SMOKE")
        self.assertEqual(self.config["smoke_overrides"], _SMOKE)
        self.assertEqual(self.config["prereg_digest"], self.info["prereg"]["prereg_digest"])
        self.assertEqual(self.config["physical_call_count"], 0)
        self.assertEqual(self.config["evidence_scope"], sp.S3_EVIDENCE_SCOPE)
        self.assertEqual(self.config["k_sweep"], [5])
        grid = self.config["evaluation_grid"]
        self.assertEqual(grid["eval_split"], "meta_validation")
        self.assertEqual(grid["eval_tasks"], 2)
        self.assertEqual(grid["budgets"], [64])
        self.assertEqual(grid["meta_seeds"], [0])
        self.assertEqual(grid["opt_seeds"], [0])
        self.assertEqual(grid["main_runs"], _EXPECTED_MAIN_RUNS)
        self.assertEqual(grid["main_evals"], _EXPECTED_EVAL_RECORDS)
        self.assertEqual(
            self.config["record_counts"],
            {
                "train": _EXPECTED_TRAIN_RECORDS,
                "eval": _EXPECTED_EVAL_RECORDS,
                "total": _EXPECTED_TRAIN_RECORDS + _EXPECTED_EVAL_RECORDS,
            },
        )
        self.assertEqual(set(self.config["models"]), set(sp.S3_MODEL_KINDS))
        self.assertEqual(len(self.config["models"]["fomaml"]["models"]), 1)

    def test_gate_config_binding(self):
        gate_config = self.config["fd_or_gradient_gate"]
        self.assertEqual(gate_config["sha256"], sp.sha256_file(self.run_a / runner.S3_RUNNER_GATE_FILE))
        self.assertEqual(gate_config["mode"], "SMOKE")
        self.assertTrue(gate_config["override"])
        self.assertEqual(gate_config["coordinates_per_model"], 2)
        self.assertEqual(gate_config["coordinates_total"], 4)
        self.assertEqual(set(gate_config["models"]), set(sp.S3_FD_GATE_MODEL_KEYS))
        self.assertEqual(gate_config["models"]["fomaml_meta_0"]["path"], runner.S3_RUNNER_GATE_FILE)
        self.assertEqual(gate_config["models"]["fomaml_meta_0"]["n_checked"], 2)
        self.assertEqual(gate_config["models"]["fomaml_meta_0"]["status"], "PASS")
        self.assertLessEqual(gate_config["models"]["fomaml_meta_0"]["max_relative_error"], 1e-6)

    def test_gate_payload(self):
        self.assertEqual(self.gate["schema_version"], sp.S3_FD_GATE_SCHEMA_VERSION)
        self.assertEqual(self.gate["status"], "PASS")
        self.assertEqual(self.gate["physical_call_count"], 0)
        self.assertTrue(self.gate["override"])
        self.assertEqual(self.gate["coordinates_per_model"], 2)
        self.assertEqual(self.gate["coordinates_total"], 4)
        self.assertEqual(set(self.gate["models"]), set(sp.S3_FD_GATE_MODEL_KEYS))
        for block in self.gate["models"].values():
            self.assertEqual(block["status"], "PASS")
            self.assertEqual(block["n_checked"], 2)
            self.assertLessEqual(block["max_relative_error"], 1e-6)

    def test_summary_shape(self):
        self.assertEqual(
            set(self.summary),
            set(sp.S3_RUN_SUMMARY_REQUIRED_FIELDS) | {"failures"},
        )
        self.assertEqual(self.summary["schema_version"], sp.S3_RUN_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(self.summary["run_id"], _RUN_ID)
        self.assertEqual(self.summary["run_mode"], "SMOKE")
        self.assertEqual(self.summary["status"], "COMPLETED")
        self.assertEqual(self.summary["failures"], [])
        self.assertEqual(self.summary["physical_call_count"], 0)
        self.assertEqual(self.summary["evidence_scope"], sp.S3_EVIDENCE_SCOPE)
        self.assertEqual(
            self.summary["record_counts"],
            {
                "train": _EXPECTED_TRAIN_RECORDS,
                "eval": _EXPECTED_EVAL_RECORDS,
                "total": _EXPECTED_TRAIN_RECORDS + _EXPECTED_EVAL_RECORDS,
            },
        )
        counts = self.summary["status_counts"]
        self.assertEqual(set(counts), {"train", "eval"})
        self.assertEqual(set(counts["train"]), set(sp.S3_RECORD_STATUSES))
        self.assertEqual(set(counts["eval"]), set(sp.S3_RECORD_STATUSES))
        self.assertEqual(counts["train"]["OK"], _EXPECTED_TRAIN_RECORDS)
        self.assertEqual(counts["eval"]["OK"], _EXPECTED_EVAL_RECORDS)
        self.assertEqual(self.summary["fd_or_gradient_gate_sha256"], self.config["fd_or_gradient_gate"]["sha256"])
        self.assertEqual(self.summary["data_manifest_sha256"], sp.sha256_file(self.run_a / runner.S3_RUNNER_DATA_MANIFEST_FILE))
        self.assertEqual(self.summary["models"], self.config["models"])
        self.assertEqual(self.summary["scope_notes"], self.config["scope_notes"])
        self.assertFalse(self.summary["determinism"]["executed"])
        self.assertEqual(self.summary["determinism"]["reruns"], 0)
        self.assertFalse(self.summary["negative_controls"]["executed"])
        self.assertEqual(self.summary["negative_controls"]["reason"], "SMOKE 不执行负控/OOD/确定性子集")
        resources = self.summary["resources"]
        self.assertGreater(resources["total_wall_s"], 0.0)
        self.assertGreater(resources["max_wall_s"], 0.0)
        self.assertEqual(resources["sum_run_wall_limit_s"], int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]))
        self.assertEqual(dict(resources["resource_limits"]), dict(sp.S3_RESOURCE_LIMITS))
        self.assertEqual(resources["auxiliary_compute"]["models_source"], "RETRAINED_IN_RUN")
        self.assertEqual(resources["auxiliary_compute"]["physical_call_count"], 0)
        self.assertEqual(self.summary["environment"]["runner_schema_version"], runner.S3_RUNNER_SCHEMA_VERSION)

    def test_scope_notes_content(self):
        notes = "\n".join(self.config["scope_notes"])
        self.assertIn("DEVELOPMENT_VALIDATION_ONLY", notes)
        self.assertIn("physical_call_count=0", notes)
        self.assertIn("SMOKE", notes)
        self.assertIn("parallel_workers=1", notes)
        self.assertEqual(self.config["scope_notes"], self.summary["scope_notes"])

    # -- 产物校验（runner 自带 fail-closed 校验） ----------------------------
    def test_runner_validation_passes(self):
        validation = self.result_a["validation"]
        self.assertTrue(validation["ok"], {k: v for k, v in validation["checks"].items() if not v["ok"]})
        failed = {key: value for key, value in validation["checks"].items() if not value["ok"]}
        self.assertEqual(failed, {})
        self.assertEqual(validation["run_status"], "COMPLETED")
        self.assertEqual(validation["record_counts"], self.summary["record_counts"])
        self.assertGreaterEqual(len(validation["checks"]), 25)
        for name in (
            "required_artifacts",
            "run_config_schema",
            "run_config_fields",
            "summary_fields",
            "physical_zero",
            "solver_processes_started_zero",
            "record_digests",
            "gate_payload",
            "execution_report_fields",
            "data_manifest_fields",
            "budget_distribution",
            "record_counts_vs_summary",
        ):
            self.assertIn(name, validation["checks"])
            self.assertTrue(validation["checks"][name]["ok"], name)

    def test_execution_report(self):
        report = self.execution_report
        self.assertEqual(set(report), set(runner.S3_EXECUTION_REPORT_FIELDS))
        self.assertEqual(report["schema_version"], runner.S3_EXECUTION_REPORT_SCHEMA_VERSION)
        self.assertEqual(report["campaign_id"], _RUN_ID)
        self.assertEqual(report["run_mode"], "SMOKE")
        self.assertEqual(report["parallel_workers"], 1)
        self.assertEqual(len(report["per_shard_counts"]), 1)
        self.assertEqual(report["run_count_requested"], _EXPECTED_MAIN_RUNS)
        self.assertEqual(report["run_count_completed"], _EXPECTED_MAIN_RUNS)
        self.assertEqual(report["physical_call_count"], 0)
        self.assertIsNone(report["stop_reason"])
        self.assertEqual(report["sum_run_wall_limit_s"], int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]))
        self.assertGreaterEqual(report["sum_run_wall_seconds"], report["max_run_wall_s"])
        self.assertEqual(report["max_peak_memory_mb"], self.summary["resources"]["max_peak_memory_mb"])
        self.assertIsInstance(report["parallel_note"], str)
        self.assertTrue(report["parallel_note"])

    def test_model_manifest(self):
        self.assertEqual(self.model_manifest["schema_version"], sp.S3_MODEL_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(self.model_manifest["run_id"], _RUN_ID)
        self.assertEqual(
            len(self.model_manifest["models"]),
            len(sp.S3_MODEL_KINDS) * len(_SMOKE["meta_seeds"]),
        )
        for row in self.model_manifest["models"]:
            self.assertEqual(set(row), set(sp.S3_MODEL_ENTRY_FIELDS))
        # SMOKE 在 run 内重训模型：manifest 为本次训练产物，不含 FORMAL 冻结块的 verification 段。
        self.assertNotIn("verification", self.model_manifest)

    def test_data_manifest(self):
        manifest = self.data_manifest
        self.assertEqual(set(manifest), set(sp.S3_DATA_MANIFEST_FIELDS))
        self.assertEqual(manifest["schema_version"], sp.S3_DATA_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(manifest["run_id"], _RUN_ID)
        self.assertEqual(manifest["physical_call_count"], 0)
        self.assertEqual(manifest["solver_processes_started"], 0)
        self.assertEqual(manifest["synthetic_call_count"], _EXPECTED_EVAL_RECORDS)
        self.assertEqual(manifest["holdout_truth_read_phase"], "EVAL")
        self.assertEqual(manifest["references_sealed_sha256"], self.info["prereg"]["references_sealed"]["sha256"])
        counts = {split: len(ids) for split, ids in manifest["split_task_ids"].items()}
        for split, expected in sp.S3_SPLIT_COUNTS.items():
            self.assertEqual(counts[split], int(expected), split)
        self.assertEqual(counts["dev"], 0)
        self.assertEqual(
            manifest["split_task_ids_sha256"]["meta_test"],
            sp.canonical_sha256(manifest["split_task_ids"]["meta_test"]),
        )
        artifacts = manifest["artifact_sha256"]
        for name in (
            runner.S3_RUNNER_RECORD_FILE,
            runner.S3_RUNNER_MODEL_MANIFEST_FILE,
            runner.S3_RUNNER_GATE_FILE,
            runner.S3_RUNNER_EXECUTION_REPORT_FILE,
        ):
            self.assertEqual(artifacts[name], sp.sha256_file(self.run_a / name), name)
        # SMOKE 重算 episode bank/FD 门（与 prereg 冻结件不同）：与 run_config 绑定值比较。
        for seed in _SMOKE["meta_seeds"]:
            self.assertEqual(
                artifacts["models/episode_bank_meta_%d.jsonl" % seed],
                self.config["episode_bank"]["banks"]["meta_seed_%d" % seed],
            )
            for kind in sp.S3_MODEL_KINDS:
                self.assertIn("models/%s_meta_%d.json" % (kind, seed), artifacts)

    # -- 记录流 --------------------------------------------------------------
    def test_record_stream(self):
        self.assertEqual(len(self.records), _EXPECTED_TRAIN_RECORDS + _EXPECTED_EVAL_RECORDS)
        train_fields = set(sp.S3_TRAIN_RECORD_FIELDS)
        eval_fields = set(sp.S3_EVAL_RECORD_FIELDS)
        train_rows = [row for row in self.records if set(row) == train_fields]
        eval_rows = [row for row in self.records if set(row) == eval_fields]
        self.assertEqual(len(train_rows), _EXPECTED_TRAIN_RECORDS)
        self.assertEqual(len(eval_rows), _EXPECTED_EVAL_RECORDS)
        for row in train_rows:
            self.assertEqual(row["run_id"], _RUN_ID)
            self.assertEqual(row["record_digest"], runner.train_record_digest(row))
        by_run = {}
        for row in eval_rows:
            self.assertEqual(row["record_digest"], runner.eval_record_digest(row))
            self.assertEqual(row["split"], "meta_validation")
            self.assertEqual(row["phase"], runner.eval_phase_for_split("meta_validation"))
            # SMOKE 在 meta_validation（开发集）上评估，holdout 真值未读取。
            self.assertFalse(row["holdout_truth_read"])
            self.assertEqual(row["budget"], 64)
            self.assertEqual(row["meta_seed"], 0)
            self.assertEqual(row["opt_seed"], 0)
            self.assertIn(row["arm_id"], m5.S3_ARM_IDS)
            by_run.setdefault(row["run_id"], []).append(row)
        self.assertEqual(len(by_run), _EXPECTED_MAIN_RUNS)
        for run_id, rows in by_run.items():
            self.assertEqual(len(rows), 64)
            sources = {}
            for row in rows:
                sources[row["source"]] = sources.get(row["source"], 0) + 1
            self.assertEqual(sources.get("support"), int(sp.S3_K_SHOT))
            self.assertEqual(sources.get("initial"), int(sp.S3_INITIAL_DESIGN_COUNT) - int(sp.S3_K_SHOT))
            indexes = sorted(row["evaluation_index"] for row in rows)
            # evaluation_index 为 1 基（1..B），与 runner 记录口径一致。
            self.assertEqual(indexes, list(range(1, 65)))

    # -- 确定性 --------------------------------------------------------------
    def test_rerun_refuses_existing_output(self):
        with self.assertRaises(runner.S3RunnerError) as ctx:
            runner.run_experiment(
                out_dir=self.run_a,
                run_id=_RUN_ID,
                prereg_path=self.info["prereg_path"],
                repo_root=self.info["repo"],
                run_mode="SMOKE",
                smoke_overrides=_SMOKE,
                parallel_workers=1,
                created_utc=support.CREATED_UTC,
                verify_code_sha=False,
            )
        self.assertEqual(ctx.exception.code, runner.S3_RUNNER_FILE_ERROR)

    def test_deterministic_runs_byte_identical(self):
        comparison = runner.compare_deterministic_runs(self.run_a, self.run_b)
        self.assertTrue(comparison["ok"], comparison)
        self.assertTrue(comparison["run_config_byte_identical"])
        self.assertTrue(comparison["record_core_equal"])
        self.assertTrue(comparison["record_counts_equal"])
        self.assertTrue(comparison["episode_bank_sha256_equal"])
        self.assertTrue(comparison["model_sha256_equal"])
        self.assertTrue(comparison["fd_gate_sha256_equal"])
        core_a = runner._record_core_list(self.records)
        core_b = runner.read_jsonl(self.run_b / runner.S3_RUNNER_RECORD_FILE)
        self.assertEqual(comparison["record_core_sha256"], sp.canonical_sha256(core_a))
        self.assertEqual(comparison["record_core_sha256"], sp.canonical_sha256(runner._record_core_list(core_b)))

    def test_run_b_validation_and_summary(self):
        validation_b = self.result_b["validation"]
        self.assertTrue(validation_b["ok"], {k: v for k, v in validation_b["checks"].items() if not v["ok"]})
        summary_b = self.result_b["summary"]
        self.assertEqual(summary_b["status"], "COMPLETED")
        self.assertEqual(summary_b["record_counts"], self.summary["record_counts"])
        self.assertEqual(summary_b["fd_or_gradient_gate_sha256"], self.summary["fd_or_gradient_gate_sha256"])
        self.assertEqual(self.result_a["run_config_sha256"], self.result_b["run_config_sha256"])
        # run_records.jsonl 含 wall_s/peak_memory_mb 等运行时字段，原始 sha 允许不同；
        # 确定性以 record_core（排除运行时段）比较为准（见 test_deterministic_runs_byte_identical）。
        self.assertNotEqual(self.result_a["run_records_sha256"], self.result_b["run_records_sha256"])

    def test_main_nonstoppable_failure_fail_closed(self):
        """A5-S3M1-m02：main campaign 未资源停止却有非 OK run -> fail-closed（S3_RUNNER_RESOURCE_ERROR）。"""
        fake_main = {
            "results": [
                {
                    "run": {"run_id": "fake-run", "wall_s": 0.5, "peak_memory_mb": 1.0},
                    "status": "FAILED",
                    "error": "synthetic failure",
                    "records": [],
                }
            ],
            "execution_report": {"stop_reason": None},
        }
        out = Path(self.tmp.name) / "run_m02_fail_closed"
        with mock.patch.object(runner, "execute_campaign", return_value=fake_main):
            with self.assertRaises(runner.S3RunnerError) as caught:
                runner.run_experiment(
                    out_dir=out,
                    run_id=_RUN_ID,
                    prereg_path=self.info["prereg_path"],
                    repo_root=self.info["repo"],
                    run_mode="SMOKE",
                    smoke_overrides=_SMOKE,
                    parallel_workers=1,
                    created_utc=support.CREATED_UTC,
                    verify_code_sha=False,
                )
        self.assertEqual(caught.exception.code, runner.S3_RUNNER_RESOURCE_ERROR)
        self.assertFalse((out / runner.S3_RUNNER_SUMMARY_FILE).exists())


class S3SmokeResourceStopEndToEndTests(unittest.TestCase):
    """A5-S3M1-M01/M02/m03：SMOKE 真 run 的资源停止（per_run_wall_s 注入 0，不真 sleep）。"""

    @classmethod
    def setUpClass(cls):
        cls.case = support.SyntheticRepoCase()
        cls.info = cls.case.get_repo()
        cls.tmp = support.tempfile.TemporaryDirectory(prefix="s3-e2e-stop-")
        cls.run_dir = Path(cls.tmp.name) / "run_stop"
        # 预注册结构校验要求 resource_limits 与默认结构一致，故在预注册加载/校验通过之后再收紧
        # per-run 墙钟上限（0s），以便在不真实 sleep 的情况下触发资源停止路径。
        original_limits = dict(sp.S3_RESOURCE_LIMITS)
        real_resolve = runner._resolve_prereg_and_family

        def resolve_then_tighten(*args, **kwargs):
            resolved = real_resolve(*args, **kwargs)
            sp.S3_RESOURCE_LIMITS["per_run_wall_s"] = 0.0
            return resolved

        try:
            with mock.patch.object(runner, "_resolve_prereg_and_family", side_effect=resolve_then_tighten):
                cls.result = runner.run_experiment(
                    out_dir=cls.run_dir,
                    run_id="s3-e2e-stop",
                    prereg_path=cls.info["prereg_path"],
                    repo_root=cls.info["repo"],
                    run_mode="SMOKE",
                    smoke_overrides=_SMOKE,
                    parallel_workers=1,
                    created_utc=support.CREATED_UTC,
                    verify_code_sha=False,
                )
        finally:
            sp.S3_RESOURCE_LIMITS.clear()
            sp.S3_RESOURCE_LIMITS.update(original_limits)
        cls.summary = cls.result["summary"]
        cls.report = cls.result["execution_report"]

    @classmethod
    def tearDownClass(cls):
        cls.case.cleanup_repo()
        cls.tmp.cleanup()

    def test_resource_stop_status_and_report(self):
        self.assertEqual(self.summary["status"], "RESOURCE_LIMIT")
        self.assertEqual(self.report["stop_reason"], runner.S3_RUNNER_RESOURCE_LIMIT)
        self.assertEqual(self.report["run_count_completed"], 1)
        self.assertEqual(self.report["run_count_requested"], _EXPECTED_MAIN_RUNS)
        failed = {key: value for key, value in self.result["validation"]["checks"].items() if not value["ok"]}
        self.assertTrue(self.result["validation"]["ok"], failed)
        resources = self.summary["resources"]
        # m03：execution_report 与 run_summary.resources 完全一致。
        self.assertEqual(resources["stop_reason"], self.report["stop_reason"])
        self.assertEqual(resources["sum_run_wall_seconds"], self.report["sum_run_wall_seconds"])
        self.assertEqual(resources["parallel_workers"], self.report["parallel_workers"])
        self.assertEqual(self.report["sum_run_wall_seconds"], self.report["max_run_wall_s"])

    def test_no_aux_campaigns_and_determinism_not_executed(self):
        self.assertFalse(self.summary["determinism"]["executed"])
        self.assertFalse(self.summary["negative_controls"]["executed"])
        for name in (
            runner.S3_RUNNER_NC_RECORDS_FILE,
            runner.S3_RUNNER_OOD_RECORDS_FILE,
            runner.S3_RUNNER_DET_CHECK_FILE,
        ):
            self.assertFalse((self.run_dir / name).is_file(), name)


class S3FormalCampaignPropagationTests(unittest.TestCase):
    """A5-S3M1-M01/m03/m04：FORMAL 多 campaign 停止传播 + FORMAL 形状（不跑 3,780 run 全网格）。"""

    _RUN_ID = "s3-e2e-formal-stop"

    @classmethod
    def setUpClass(cls):
        cls.case = support.SyntheticRepoCase()
        cls.info = cls.case.get_repo()
        cls.tmp = support.tempfile.TemporaryDirectory(prefix="s3-e2e-formal-stop-")
        cls.run_dir = Path(cls.tmp.name) / "run_formal_stop"
        cls.calls = []
        real_campaign = runner.execute_campaign
        def pick_fair_group(specs):
            by_key = {}
            for spec in specs:
                key = (
                    str(spec["task_id"]),
                    int(spec["budget"]),
                    int(spec["opt_seed"]),
                    int(spec["meta_seed"]),
                )
                by_key.setdefault(key, {})[str(spec["arm"])] = spec
            for key in sorted(by_key):
                arms = by_key[key]
                if set(arms) == set(m5.S3_ARM_IDS):
                    return [arms[arm] for arm in m5.S3_ARM_IDS]
            raise AssertionError("主网格中找不到完整臂组")


        def stop_report(campaign_id):
            return {
                "schema_version": runner.S3_EXECUTION_REPORT_SCHEMA_VERSION,
                "campaign_id": str(campaign_id),
                "run_mode": "FORMAL",
                "created_utc": support.CREATED_UTC,
                "parallel_workers": 1,
                "execution_rule": "mock",
                "shard_runs_sha256": "0" * 64,
                "per_shard_counts": [0],
                "run_count_requested": 1,
                "run_count_completed": 0,
                "campaign_wall_s": 0.0,
                "sum_run_wall_seconds": 0.0,
                "max_run_wall_s": 0.0,
                "max_peak_memory_mb": 0.0,
                "sum_run_wall_limit_s": int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]),
                "stop_reason": runner.S3_RUNNER_RESOURCE_LIMIT,
                "physical_call_count": 0,
                "parallel_note": "mock",
            }

        def fake_campaign(specs, **kwargs):
            campaign_id = str(kwargs.get("campaign_id"))
            cls.calls.append(campaign_id)
            if campaign_id == cls._RUN_ID:
                # 主 campaign 只真实执行“一个完整臂组”（同一 task/budget/opt/meta 的 5 臂），
                # 满足公平性断言的同时不跑 3,000 run 全网格。
                return real_campaign(pick_fair_group(list(specs)), **kwargs)
            if campaign_id.endswith("--NC"):
                return {"results": [], "execution_report": stop_report(campaign_id)}
            raise AssertionError("资源停止后不应启动后续 campaign: " + campaign_id)

        real_load_frozen_models = runner.load_frozen_models

        def load_transposed_fixture(**kwargs):
            # 披露（fixture 限制，非 runner 缺陷）：test_s3_support 的合成冻结模型按
            # torch Linear 布局 (out,in) 生成，而 maml.ParameterSet/m5_arms.S3ModelScorer
            # 的前向约定为 (in,out)；真实 M2 冻结模型由 maml 训练产出即 (in,out)。
            # 故此处仅在加载后转置合成张量，以打通 FORMAL 形状级 e2e（不写回任何文件）。
            models = real_load_frozen_models(**kwargs)
            fixed = {}
            for key, entry in models.items():
                parameters = entry["parameters"]
                tensors = [
                    (tensor.T if getattr(tensor, "ndim", 0) == 2 else tensor)
                    for tensor in parameters.tensors
                ]
                updated = dict(entry)
                updated["parameters"] = type(parameters)(tensors)
                fixed[key] = updated
            return fixed

        with mock.patch.object(runner, "load_frozen_models", side_effect=load_transposed_fixture), mock.patch.object(
            runner, "execute_campaign", side_effect=fake_campaign
        ):
            cls.result = runner.run_experiment(
                out_dir=cls.run_dir,
                run_id=cls._RUN_ID,
                prereg_path=cls.info["prereg_path"],
                repo_root=cls.info["repo"],
                run_mode="FORMAL",
                parallel_workers=1,
                created_utc=support.CREATED_UTC,
                verify_code_sha=False,
            )
        cls.summary = cls.result["summary"]
        cls.report = cls.result["execution_report"]
        cls.config = runner.read_json_file(cls.run_dir / runner.S3_RUNNER_CONFIG_FILE)

    @classmethod
    def tearDownClass(cls):
        cls.case.cleanup_repo()
        cls.tmp.cleanup()

    def test_campaign_stop_propagation(self):
        self.assertEqual(self.calls, [self._RUN_ID, self._RUN_ID + "--NC"])
        self.assertEqual(self.summary["status"], "RESOURCE_LIMIT")
        self.assertEqual(self.report["stop_reason"], runner.S3_RUNNER_RESOURCE_LIMIT)
        self.assertEqual(self.summary["resources"]["stop_reason"], runner.S3_RUNNER_RESOURCE_LIMIT)
        self.assertFalse(self.summary["determinism"]["executed"])
        failed = {key: value for key, value in self.result["validation"]["checks"].items() if not value["ok"]}
        self.assertTrue(self.result["validation"]["ok"], failed)
        self.assertFalse((self.run_dir / runner.S3_RUNNER_OOD_RECORDS_FILE).is_file())
        self.assertFalse((self.run_dir / runner.S3_RUNNER_DET_CHECK_FILE).is_file())

    def test_formal_shape_without_full_grid(self):
        self.assertEqual(self.config["run_mode"], "FORMAL")
        self.assertEqual(self.config["k_sweep"], [5])
        gate = self.config["fd_or_gradient_gate"]
        self.assertEqual(gate["mode"], "FORMAL")
        self.assertFalse(gate["override"])
        self.assertEqual(gate["coordinates_per_model"], int(sp.S3_FD_GATE_COORDINATES_PER_MODEL))
        self.assertEqual(
            gate["coordinates_total"],
            int(sp.S3_FD_GATE_COORDINATES_PER_MODEL) * len(sp.S3_FD_GATE_MODEL_KEYS),
        )
        self.assertEqual(self.config["record_counts"]["train"], 0)
        grid = self.config["evaluation_grid"]
        self.assertEqual(grid["main_runs"], int(sp.S3_MAIN_RUNS))
        self.assertEqual(grid["main_evals"], int(sp.S3_MAIN_EVALS))
        self.assertEqual(tuple(self.report), runner.S3_EXECUTION_REPORT_FIELDS)
        self.assertEqual(self.report["run_mode"], "FORMAL")
        # 披露：本测试为形状级 e2e（主 campaign 仅执行 2 run 后由 NC 停止），
        # 正式全网格 3,780 runs / 362,880 evals 未执行，仅为常量级断言。
        self.assertEqual(int(sp.S3_TOTAL_RUNS), 3780)
        self.assertEqual(int(sp.S3_TOTAL_EVALS), 362880)
        self.assertLess(self.config["record_counts"]["eval"], int(sp.S3_TOTAL_EVALS))


if __name__ == "__main__":
    unittest.main()
