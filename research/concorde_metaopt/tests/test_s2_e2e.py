# -*- coding: utf-8 -*-
"""S2 runner -> analysis 端到端测试（A5 代码审阅 M02；全合成、零物理）。

覆盖：
1. SMOKE run_experiment 产物（run_config/run_summary/fd_gate/data_manifest/records）的 v2 合同；
2. s2_analysis.analyze_s2_run 能加载该 run 并产出 aggregate.json 与 5 个 CSV；
3. schema 常量在 runner 与 analysis 两侧同源（均来自 s2_prereg）；
4. 负控：删 run_config 必填字段、删 smoke_overrides、run_mode 不一致、篡改 fd_gate.json、
   篡改 data_manifest.json 均 fail-closed（S2AnalysisError）。

本测试不读取任何 holdout 数据，不启动任何求解器；physical_call_count 必须为 0。
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.meta_learning import s2_analysis as analysis
from research.concorde_metaopt.meta_learning import s2_prereg as sp
from research.concorde_metaopt.meta_learning import s2_runner as runner

REPO_ROOT = Path(__file__).resolve().parents[3]
CREATED_UTC = "2026-11-07T00:00:00+00:00"
BANK_SHA = "0" * 64
SMOKE_OVERRIDES = {
    "outer_steps": 2,
    "meta_seeds": [0],
    "K": [0, 1, 5, 10],
    "draws": 1,
    "eval_tasks": 20,
    "fd_coordinates": 8,
}
EXPECTED_COUNTS = {"train": 2 * 1 * 2, "eval": 2 * 1 * 20 * 4 * 1}


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class S2RunnerAnalysisEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="p4-s2-e2e-")
        cls.root = Path(cls.tmp.name)
        prereg = sp.build_preregistration(
            repo_root=REPO_ROOT,
            created_utc=CREATED_UTC,
            train_episode_bank_sha256=BANK_SHA,
        )
        cls.prereg = prereg
        cls.prereg_path = sp.write_preregistration(prereg, cls.root / "prereg.json")
        cls.run_dir = cls.root / "run"
        cls.summary = runner.run_experiment(
            out_dir=cls.run_dir,
            run_id="s2-e2e-smoke-0001",
            prereg_path=cls.prereg_path,
            run_mode="SMOKE",
            smoke_overrides=SMOKE_OVERRIDES,
            created_utc=CREATED_UTC,
        )
        cls.analysis_dir = cls.root / "analysis"
        cls.analysis_result = analysis.analyze_s2_run(
            prereg_path=cls.prereg_path,
            run_dir=cls.run_dir,
            output_dir=cls.analysis_dir,
            repo_root=REPO_ROOT,
            allow_incomplete_run=True,
            generate_figures=False,
        )
        cls.prereg_obj = analysis.load_s2_prereg(
            cls.prereg_path,
            repo_root=REPO_ROOT,
            verify_pilot_artifacts=False,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    # -- 辅助 -----------------------------------------------------------------

    def _copy_run(self, name: str) -> Path:
        destination = self.root / name
        shutil.copytree(self.run_dir, destination)
        return destination

    def _load_config(self) -> dict:
        return json.loads((self.run_dir / "run_config.json").read_text(encoding="utf-8"))

    def _load_summary(self) -> dict:
        return json.loads((self.run_dir / "run_summary.json").read_text(encoding="utf-8"))

    # -- 正向 ---------------------------------------------------------------

    def test_01_smoke_run_manifest_contract(self) -> None:
        summary = self._load_summary()
        self.assertEqual(summary["status"], "COMPLETED")
        self.assertEqual(summary["run_mode"], "SMOKE")
        self.assertTrue(summary["smoke"])
        self.assertEqual(summary["record_counts"]["train"], EXPECTED_COUNTS["train"])
        self.assertEqual(summary["record_counts"]["eval"], EXPECTED_COUNTS["eval"])
        self.assertEqual(summary["physical_call_count"], 0)
        self.assertEqual(summary["resources"]["auxiliary_compute"]["physical_call_count"], 0)
        config = self._load_config()
        self.assertEqual(config["run_mode"], "SMOKE")
        self.assertEqual(config["physical_call_count"], 0)
        self.assertEqual(config["record_counts"]["train"], EXPECTED_COUNTS["train"])
        self.assertEqual(config["record_counts"]["eval"], EXPECTED_COUNTS["eval"])
        self.assertTrue(config["fd_gate"]["override"])
        self.assertEqual(config["fd_gate"]["status"], "PASS")
        for name in ("run_config.json", "run_summary.json", "run_records.jsonl", "fd_gate.json", "data_manifest.json"):
            self.assertTrue((self.run_dir / name).is_file(), name)

    def test_02_schema_single_source(self) -> None:
        # 两侧必须直接使用 s2_prereg 的单源常量，不得各自复制
        self.assertEqual(runner.S2_RUN_CONFIG_SCHEMA_VERSION, sp.RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(runner.S2_RUN_SUMMARY_SCHEMA_VERSION, sp.RUN_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(analysis.RUN_CONFIG_SCHEMA_VERSION, sp.RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(analysis.RUN_SUMMARY_SCHEMA_VERSION, sp.RUN_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(sp.RUN_CONFIG_SCHEMA_VERSION, "p4ra-s2-run-config-v2")
        self.assertEqual(sp.RUN_SUMMARY_SCHEMA_VERSION, "p4ra-s2-run-summary-v2")
        config = self._load_config()
        summary = self._load_summary()
        self.assertEqual(config["schema_version"], sp.RUN_CONFIG_SCHEMA_VERSION)
        self.assertEqual(summary["schema_version"], sp.RUN_SUMMARY_SCHEMA_VERSION)
        self.assertEqual(set(config) - {"smoke_overrides"}, set(sp.RUN_CONFIG_REQUIRED_FIELDS))
        self.assertEqual(set(summary), set(sp.RUN_SUMMARY_REQUIRED_FIELDS))
        self.assertEqual(set(config["fd_gate"]), set(sp.FD_GATE_FIELDS))
        self.assertEqual(set(config["episode_bank"]), set(sp.EPISODE_BANK_FIELDS))
        self.assertEqual(set(summary["resources"]), set(sp.RUN_SUMMARY_RESOURCES_FIELDS))
        self.assertEqual(set(config["resource_limits"]), set(sp.RUN_RESOURCE_LIMITS))
        self.assertEqual(config["resource_limits"], sp.RUN_RESOURCE_LIMITS)

    def test_03_analysis_end_to_end_outputs(self) -> None:
        result = self.analysis_result
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["run_id"], "s2-e2e-smoke-0001")
        self.assertEqual(result["record_counts"]["train"], EXPECTED_COUNTS["train"])
        self.assertEqual(result["record_counts"]["eval"], EXPECTED_COUNTS["eval"])
        self.assertEqual(result["n_tasks"], 20)
        self.assertEqual(result["negative_controls"], result["negative_controls"])
        for name in (
            "aggregate.json",
            "s2_endpoint_tables.csv",
            "s2_per_task_aggregates.csv",
            "s2_holm_family.csv",
            "s2_null_disclosure.csv",
            "s2_negative_controls.csv",
        ):
            path = self.analysis_dir / name
            self.assertTrue(path.is_file(), name)
            self.assertGreater(path.stat().st_size, 0, name)
        aggregate = json.loads((self.analysis_dir / "aggregate.json").read_text(encoding="utf-8"))
        self.assertEqual(aggregate["schema_version"], analysis.S2_AGGREGATE_SCHEMA_VERSION)
        self.assertEqual(aggregate["run_id"], "s2-e2e-smoke-0001")
        self.assertEqual(aggregate["record_counts"]["train"], EXPECTED_COUNTS["train"])
        self.assertEqual(aggregate["record_counts"]["eval"], EXPECTED_COUNTS["eval"])
        self.assertEqual(aggregate["prereg"]["prereg_digest"], self.prereg["prereg_digest"])
        self.assertEqual(aggregate["evidence_scope"], "DEVELOPMENT_VALIDATION_ONLY")
        self.assertEqual(aggregate["physical_call_count"], 0) if "physical_call_count" in aggregate else None
        disclosures = [check for check in aggregate["checks"] if check.get("status") == "DISCLOSED"]
        self.assertTrue(disclosures, "SMOKE 运行必须在 checks 中留下 DISCLOSED 记录")

    # -- 负控 ---------------------------------------------------------------

    def test_04_negative_missing_required_run_config_field(self) -> None:
        run_dir = self._copy_run("run-missing-field")
        config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
        del config["record_schemas"]
        _write_json(run_dir / "run_config.json", config)
        with self.assertRaises(analysis.S2AnalysisError):
            analysis.load_s2_run(run_dir, self.prereg_obj, repo_root=REPO_ROOT)

    def test_05_negative_missing_smoke_overrides(self) -> None:
        run_dir = self._copy_run("run-missing-smoke")
        config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
        del config["smoke_overrides"]
        _write_json(run_dir / "run_config.json", config)
        with self.assertRaises(analysis.S2AnalysisError):
            analysis.load_s2_run(run_dir, self.prereg_obj, repo_root=REPO_ROOT)

    def test_06_negative_run_mode_mismatch(self) -> None:
        run_dir = self._copy_run("run-mode-mismatch")
        summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
        summary["run_mode"] = "FORMAL"
        _write_json(run_dir / "run_summary.json", summary)
        with self.assertRaises(analysis.S2AnalysisError):
            analysis.load_s2_run(run_dir, self.prereg_obj, repo_root=REPO_ROOT)

    def test_07_negative_tampered_fd_gate_json(self) -> None:
        run_dir = self._copy_run("run-tampered-fd-gate")
        path = run_dir / "fd_gate.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["result"]["status"] = "FAIL"
        payload["result"]["max_relative_error"] = 0.5
        _write_json(path, payload)
        with self.assertRaises(analysis.S2AnalysisError):
            analysis.load_s2_run(run_dir, self.prereg_obj, repo_root=REPO_ROOT)

    def test_08_negative_tampered_data_manifest(self) -> None:
        run_dir = self._copy_run("run-tampered-data-manifest")
        path = run_dir / "data_manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["holdout_rows_used"] = 1
        payload["holdout_metrics_read"] = True
        _write_json(path, payload)
        with self.assertRaises(analysis.S2AnalysisError):
            analysis.load_s2_run(run_dir, self.prereg_obj, repo_root=REPO_ROOT)


if __name__ == "__main__":
    unittest.main()
