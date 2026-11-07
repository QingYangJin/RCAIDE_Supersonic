"""S3 十图渲染单元测试（A6 交付；计划 §5.3）。

覆盖：FIGURE_KEYS 契约、空状态全 NOT_RUN、最小状态按预期渲染/跳过、
PNG+数据 CSV 落盘、figure_generation_summary.json schema、非 mapping 输入 FigureError、
fig7 OOD / fig10 VSPAERO 门禁的条件渲染、图注 evidence_scope。
"""

from __future__ import annotations

import atexit
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.meta_learning import s3_figures as fig
from research.concorde_metaopt.meta_learning import s3_prereg as sp

ARMS = (
    "S3-BO-RANDOM",
    "S3-BO-FOMAML-OBJ",
    "S3-BO-FOMAML-CON",
    "S3-BO-ANIL-CON",
    "S3-DE",
)

_TMP_ROOT = tempfile.mkdtemp(prefix="p4ra-s3-figures-tests-")
atexit.register(shutil.rmtree, _TMP_ROOT, True)


def _output_dir(tag: str) -> Path:
    target = Path(_TMP_ROOT) / tag
    return target


def _endpoint_rows(endpoint: str, *, mean: float = 0.25) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for arm in ARMS:
        for budget in (64, 128):
            rows.append({
                "endpoint": endpoint,
                "endpoint_role": "inference" if endpoint in ("feasible_hit_rate", "gap_to_reference") else "descriptive",
                "arm_id": arm,
                "comparator": "S3-BO-FOMAML-OBJ",
                "budget": budget,
                "mean": mean,
                "median": mean,
                "ci_low": mean - 0.05,
                "ci_high": mean + 0.05,
                "n_tasks": 4,
                "n_null": 0,
            })
    return rows


def _cost_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for arm in ARMS:
        for budget in (64, 128):
            rows.append({
                "arm_id": arm,
                "budget": budget,
                "n_runs": 4,
                "total_cost_mean_s": 0.5 + budget / 1000.0,
                "total_cost_median_s": 0.5 + budget / 1000.0,
                "adaptation_cost_mean": 0.4,
                "cost_metric_note": "wall_s + 打分次数",
            })
    return rows


def _minimal_state() -> dict[str, object]:
    rows = _endpoint_rows("feasible_hit_rate")
    rows += _endpoint_rows("gap_to_reference", mean=0.3)
    rows += _endpoint_rows("best_feasible_value", mean=0.2)
    rows += _endpoint_rows("first_feasible_eval_index", mean=3.0)
    return {
        "run_id": "p4ra-s3-run-smoke-fixture",
        "run_mode": "SMOKE",
        "arms": list(ARMS),
        "training": {"loss_by_meta_seed": {"0": [[1, 0.5], [2, 0.4]]}},
        "endpoint_rows": rows,
        "cost_rows": _cost_rows(),
        "task_families": {
            "rows": [
                {"task_id": "task-1", "f_ref": 0.04, "reference_kind": "POLYHEDRAL_KKT_CERTIFIED"},
                {"task_id": "task-2", "f_ref": 0.05, "reference_kind": "POLYHEDRAL_KKT_CERTIFIED"},
            ]
        },
        "negative_control_rows": [
            {"control_id": "NC-01", "status": "PASS"},
            {"control_id": "NC-02", "status": "DISCLOSED"},
        ],
        "determinism_rows": [{"pass": "r1", "n_records": 96}, {"pass": "r2", "n_records": 96}],
        "source_files": [{"name": "run_records.jsonl", "sha256": "a" * 64}],
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


class FigureContractTests(unittest.TestCase):
    def test_figure_keys_exact_ten(self):
        expected = (
            "fig1_training_loss_and_full_meta_grad",
            "fig2_kshot_rmse_k0_k1_k3_k5",
            "fig3_feasible_hit_rate_by_arm",
            "fig4_best_feasible_and_first_feasible",
            "fig5_fomaml_vs_full_vs_anil_cost",
            "fig6_task_family_diagnostics",
            "fig7_ood_diagnostics",
            "fig8_negative_controls",
            "fig9_determinism_and_budget",
            "fig10_vspaero_gate_status",
        )
        self.assertEqual(tuple(fig.FIGURE_KEYS), expected)
        self.assertEqual(len(fig.FIGURE_KEYS), 10)
        self.assertEqual(set(fig.FIGURE_KEYS), set(sp.S3_FIGURES.keys()))

    def test_evidence_scope_note(self):
        self.assertIn("DEVELOPMENT_VALIDATION_ONLY", fig.EVIDENCE_SCOPE_NOTE)
        self.assertIn("不作确证性结论", fig.EVIDENCE_SCOPE_NOTE)

    def test_non_mapping_state_raises_figure_error(self):
        with self.assertRaises(fig.FigureError) as context:
            fig.generate_figures([], output_dir=_output_dir("non-mapping"))
        self.assertEqual(context.exception.code, "S3_FIGURE_ERROR")
        self.assertIn("JSON 对象", context.exception.message)


class EmptyStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = _output_dir("empty")
        cls.results = fig.generate_figures({}, output_dir=cls.out)

    def test_all_figures_not_run(self):
        self.assertEqual(set(self.results), set(fig.FIGURE_KEYS))
        for key, item in self.results.items():
            self.assertEqual(item["status"], "NOT_RUN", msg=key)
            self.assertIsNone(item["path"], msg=key)
            self.assertIsNone(item["csv_path"], msg=key)
            self.assertTrue(str(item["reason"]), msg=key)

    def test_no_png_written(self):
        self.assertEqual(list(self.out.glob("*.png")), [])

    def test_summary_json_schema(self):
        path = self.out / "figure_generation_summary.json"
        self.assertTrue(path.is_file())
        summary = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], "p4ra-s3-figure-generation-1")
        self.assertEqual(summary["evidence_scope"], "DEVELOPMENT_VALIDATION_ONLY")
        self.assertEqual(int(summary["physical_call_count"]), 0)
        self.assertIn("cjk_font", summary)
        self.assertIsInstance(summary["cjk_font_available"], bool)
        self.assertEqual(set(summary["figures"]), set(fig.FIGURE_KEYS))
        for key, item in summary["figures"].items():
            self.assertEqual(item["status"], "NOT_RUN", msg=key)
            self.assertIsNone(item["path"], msg=key)


class MinimalStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = _output_dir("minimal")
        cls.results = fig.generate_figures(_minimal_state(), output_dir=cls.out)

    def test_expected_figures_rendered(self):
        for key in (
            "fig1_training_loss_and_full_meta_grad",
            "fig3_feasible_hit_rate_by_arm",
            "fig4_best_feasible_and_first_feasible",
            "fig5_fomaml_vs_full_vs_anil_cost",
            "fig6_task_family_diagnostics",
            "fig8_negative_controls",
            "fig9_determinism_and_budget",
        ):
            self.assertEqual(self.results[key]["status"], "RENDERED", msg=self.results[key]["reason"])
            self.assertTrue(Path(self.results[key]["path"]).is_file(), msg=key)
            self.assertTrue(Path(self.results[key]["csv_path"]).is_file(), msg=key)
            self.assertEqual(len(self.results[key]["data_sha256"]), 64)

    def test_missing_data_figures_not_run(self):
        for key in (
            "fig2_kshot_rmse_k0_k1_k3_k5",
            "fig7_ood_diagnostics",
            "fig10_vspaero_gate_status",
        ):
            self.assertEqual(self.results[key]["status"], "NOT_RUN", msg=key)
            self.assertIsNone(self.results[key]["path"], msg=key)

    def test_rendered_csv_has_rows(self):
        rows = _read_csv_rows(Path(self.results["fig3_feasible_hit_rate_by_arm"]["csv_path"]))
        self.assertEqual(len(rows), len(ARMS) * 2)
        self.assertEqual({row["arm_id"] for row in rows}, set(ARMS))
        fig1_rows = _read_csv_rows(Path(self.results["fig1_training_loss_and_full_meta_grad"]["csv_path"]))
        panels = {row["panel"] for row in fig1_rows}
        self.assertIn("training_loss", panels)
        self.assertIn("full_meta_grad", panels)

    def test_fig8_csv_reflects_negative_controls(self):
        rows = _read_csv_rows(Path(self.results["fig8_negative_controls"]["csv_path"]))
        self.assertEqual([row["control_id"] for row in rows], ["NC-01", "NC-02"])

    def test_summary_lists_rendered_paths(self):
        summary = json.loads((self.out / "figure_generation_summary.json").read_text(encoding="utf-8"))
        rendered = [key for key, item in summary["figures"].items() if item["status"] == "RENDERED"]
        self.assertEqual(len(rendered), 7)
        for key in rendered:
            self.assertTrue(Path(summary["figures"][key]["path"]).is_file(), msg=key)


class ConditionalFigureTests(unittest.TestCase):
    def test_fig1_not_run_without_training(self):
        results = fig.generate_figures({"arms": list(ARMS)}, output_dir=_output_dir("no-training"))
        self.assertEqual(results["fig1_training_loss_and_full_meta_grad"]["status"], "NOT_RUN")
        self.assertIn("train record", results["fig1_training_loss_and_full_meta_grad"]["reason"])

    def test_fig3_not_run_without_endpoint_rows(self):
        results = fig.generate_figures({"arms": list(ARMS)}, output_dir=_output_dir("no-endpoints"))
        self.assertEqual(results["fig3_feasible_hit_rate_by_arm"]["status"], "NOT_RUN")
        self.assertIn("feasible_hit_rate", results["fig3_feasible_hit_rate_by_arm"]["reason"])

    def test_fig7_rendered_with_ood_rows(self):
        state = {
            "ood_rows": [
                {"arm_id": "S3-BO-FOMAML-CON", "feasible_hit_rate_mean": 0.2, "status": "OK"},
                {"arm_id": "S3-BO-FOMAML-OBJ", "feasible_hit_rate_mean": 0.3, "status": "OK"},
            ]
        }
        results = fig.generate_figures(state, output_dir=_output_dir("ood"))
        self.assertEqual(results["fig7_ood_diagnostics"]["status"], "RENDERED")
        rows = _read_csv_rows(Path(results["fig7_ood_diagnostics"]["csv_path"]))
        self.assertEqual(len(rows), 2)

    def test_fig7_not_run_when_all_rows_not_run(self):
        state = {"ood_rows": [{"arm_id": "S3-BO-FOMAML-CON", "status": "NOT_RUN"}]}
        results = fig.generate_figures(state, output_dir=_output_dir("ood-not-run"))
        self.assertEqual(results["fig7_ood_diagnostics"]["status"], "NOT_RUN")

    def test_fig10_rendered_with_gate_archive(self):
        state = {
            "vspaero_gate": {
                "status": "OK",
                "path": "research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/summary.json",
                "sha256": "b" * 64,
                "gates": {
                    "GEO-12D": "PARTIAL",
                    "LF-M2.02": "NOT_VALIDATED / LF_PROVISIONAL",
                    "HF-M2.02": "PARTIAL",
                    "BODY-CORR": "BLOCKED",
                },
            }
        }
        results = fig.generate_figures(state, output_dir=_output_dir("gate"))
        self.assertEqual(results["fig10_vspaero_gate_status"]["status"], "RENDERED")
        rows = _read_csv_rows(Path(results["fig10_vspaero_gate_status"]["csv_path"]))
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["gate"] for row in rows}, {"GEO-12D", "LF-M2.02", "HF-M2.02", "BODY-CORR"})

    def test_fig10_not_run_without_gate(self):
        results = fig.generate_figures({}, output_dir=_output_dir("gate-missing"))
        self.assertEqual(results["fig10_vspaero_gate_status"]["status"], "NOT_RUN")
        self.assertIn("VSPAERO", results["fig10_vspaero_gate_status"]["reason"])

    def test_fig10_not_run_when_gate_status_not_ok(self):
        state = {"vspaero_gate": {"status": "MISSING", "reason": "归档不存在"}}
        results = fig.generate_figures(state, output_dir=_output_dir("gate-bad"))
        self.assertEqual(results["fig10_vspaero_gate_status"]["status"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
