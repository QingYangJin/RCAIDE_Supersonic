"""Tests for the artefact-only run reporter (reports/summarize.py)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.reports import summarize


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _row(iteration, objective, status="VALID", feasible=True, physical=1, cache_hit=False, design_id=None):
    return {
        "iteration": iteration,
        "design_id": design_id or ("d-%012d" % iteration),
        "status": status,
        "objective": objective,
        "constraints": {"max_throttle": -0.05},
        "feasible": feasible,
        "fidelity": "single_cruise",
        "cache_hit": cache_hit,
        "physical_call_count": physical,
        "wall_seconds": 1.0,
        "cumulative_calls": iteration,
        "best_feasible_objective": None,
    }


def _make_run(
    root: Path,
    run_id: str,
    *,
    total_true_evaluations=4,
    best_feasible_fuel_kg=34000.0,
    first_feasible_evaluation=1,
    best_design_id="d-000000000002",
    artifacts=None,
    extra_summary=None,
    rows=None,
    best_design=None,
):
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if rows is None:
        rows = [
            _row(1, 34109.48257123768, design_id="d-000000000001"),
            _row(2, 34000.0, design_id="d-000000000002"),
            _row(3, 34035.332605355274, design_id="d-000000000003"),
            _row(4, None, status="MISSION_NOT_CONVERGED", feasible=False),
            _row(5, 34100.0, physical=0, cache_hit=True, design_id="d-000000000005"),
        ]
    _write_jsonl(run_dir / "evaluations.jsonl", rows)
    if artifacts is None:
        artifacts = {
            "summary": "summary.json",
            "evaluations": "evaluations.jsonl",
            "best_design": "best_design.json",
            "figures": ["figures/report_probe.png"],
        }
    (run_dir / "figures").mkdir(exist_ok=True)
    (run_dir / "figures" / "report_probe.png").write_bytes(b"png")
    if best_design is None:
        best_design = {
            "best_feasible_objective": best_feasible_fuel_kg,
            "best_design_id": best_design_id,
            "feasible": True,
        }
    _write_json(run_dir / "best_design.json", best_design)
    summary = {
        "run_id": run_id,
        "stage": "P4",
        "task_id": "concorde-fixed-cruise-p2-v1",
        "method": "ordinary_constrained_bo",
        "seed": 42,
        "git_sha": "0" * 40,
        "branch": "research/concorde-metaopt",
        "design_dim": 15,
        "status": "baseline_bo_completed",
        "total_true_evaluations": total_true_evaluations,
        "best_feasible_fuel_kg": best_feasible_fuel_kg,
        "first_feasible_evaluation": first_feasible_evaluation,
        "best_design_id": best_design_id,
        "wall_seconds": 12.5,
        "artifacts": artifacts,
        "constraints": {
            "names": ["max_throttle", "mission_convergence"],
            "all_g_le_zero": False,
            "all_g_le_zero_within_tolerance": True,
            "max_constraint_excess": 1.0e-15,
            "feasibility_tolerance": 1.0e-12,
            "positive_constraint_offenders": [{"constraint": "cruise_range_error", "value": 1.0e-15}],
        },
    }
    if extra_summary:
        summary.update(extra_summary)
    _write_json(run_dir / "summary.json", summary)
    return run_dir


class RecomputeTests(unittest.TestCase):
    def test_recompute_counts_and_best(self):
        rows = [
            _row(1, 34109.48),
            _row(2, 34000.0),
            _row(3, None, status="MISSION_FAILED", feasible=False),
            _row(4, 34050.0, physical=0, cache_hit=True),
            _row(5, None, status="GEOMETRY_INVALID", feasible=False),
        ]
        result = summarize.recompute_from_rows(rows)
        self.assertEqual(result["rows"], 5)
        # physical calls are charged for failed evaluations too; cache hits are free
        self.assertEqual(result["true_evaluations"], 4)
        self.assertEqual(result["cache_hits"], 1)
        self.assertEqual(result["valid_rows"], 3)
        self.assertEqual(result["feasible_rows"], 3)
        self.assertEqual(result["first_feasible_evaluation"], 1)
        self.assertAlmostEqual(result["best_feasible_objective"], 34000.0)
        self.assertEqual(result["best_design_id"], "d-000000000002")
        self.assertEqual(result["status_counts"]["MISSION_FAILED"], 1)

    def test_recompute_ignores_none_objective_for_best(self):
        result = summarize.recompute_from_rows([_row(1, None), _row(2, 34100.0)])
        self.assertAlmostEqual(result["best_feasible_objective"], 34100.0)

    def test_recompute_no_feasible_rows(self):
        result = summarize.recompute_from_rows([_row(1, None, status="MISSION_FAILED", feasible=False)])
        self.assertIsNone(result["best_feasible_objective"])
        self.assertIsNone(result["first_feasible_evaluation"])


class ReportRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="concorde-report-tests-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_clean_run_reports_completed(self):
        _make_run(self.tmp, "run-clean")
        result = summarize.run_report(run_dir=self.tmp / "run-clean", rewrite_figures=False)
        report = result["report"]
        self.assertEqual(report["report_status"], summarize.STATUS_COMPLETED)
        self.assertEqual(report["consistency_failures"], [])
        self.assertEqual(len(report["artifacts"]["missing"]), 0)
        self.assertEqual(report["artifacts"]["absolute_paths"], [])
        self.assertEqual(report["recomputed"]["true_evaluations"], 4)
        markdown = (self.tmp / "run-clean" / "report.md").read_text(encoding="utf-8")
        for heading in ("## Summary", "## Recomputed headline numbers", "## Consistency checks", "## Artefacts", "## Best design"):
            self.assertIn(heading, markdown)
        self.assertIn("34000.0", markdown)
        saved = json.loads((self.tmp / "run-clean" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["run_id"], "run-clean")
        self.assertEqual(saved["artifacts"]["missing"], [])

    def test_mismatched_summary_is_flagged(self):
        _make_run(self.tmp, "run-mismatch", total_true_evaluations=99, best_feasible_fuel_kg=33000.0)
        result = summarize.run_report(run_dir=self.tmp / "run-mismatch", rewrite_figures=False)
        report = result["report"]
        self.assertEqual(report["report_status"], summarize.STATUS_WITH_WARNINGS)
        self.assertIn("R01", report["consistency_failures"])
        self.assertIn("R02", report["consistency_failures"])

    def test_missing_and_absolute_artifacts_are_flagged(self):
        run_id = "run-artifacts"
        run_dir = _make_run(self.tmp, run_id)
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        summary["artifacts"]["missing_table"] = "optional_small_tables/absent.csv"
        summary["artifacts"]["absolute"] = "C:/RCAIDE/not/a/repo/path.csv"
        _write_json(run_dir / "summary.json", summary)
        result = summarize.run_report(run_dir=run_dir, rewrite_figures=False)
        report = result["report"]
        self.assertEqual([entry["path"] for entry in report["artifacts"]["missing"]], ["optional_small_tables/absent.csv"])
        self.assertEqual(report["artifacts"]["absolute_paths"], ["C:/RCAIDE/not/a/repo/path.csv"])
        self.assertEqual(report["report_status"], summarize.STATUS_WITH_WARNINGS)

    def test_missing_summary_raises(self):
        (self.tmp / "empty-run").mkdir(parents=True)
        with self.assertRaises(summarize.ReportError):
            summarize.run_report(run_dir=self.tmp / "empty-run", rewrite_figures=False)

    def test_comparison_table_written(self):
        _make_run(self.tmp, "run-a")
        _make_run(
            self.tmp,
            "run-b",
            total_true_evaluations=2,
            best_feasible_fuel_kg=34050.0,
            best_design_id="d-000000000002",
            extra_summary={"method": "ordinary_constrained_de", "stage": "P4", "status": "baseline_de_completed"},
            rows=[_row(1, 34100.0), _row(2, 34050.0)],
        )
        result = summarize.run_report(
            run_dir=self.tmp / "run-a",
            compare_run_ids=("run-b", "run-absent"),
            rewrite_figures=False,
        )
        report = result["report"]
        self.assertEqual(len(report["comparison"]), 3)
        self.assertEqual(report["comparison"][0]["run_id"], "run-a")
        self.assertEqual(report["comparison"][1]["method"], "ordinary_constrained_de")
        self.assertEqual(report["comparison"][2]["status"], "unavailable")
        comparison_csv = (self.tmp / "run-a" / summarize.COMPARISON_FILENAME).read_text(encoding="utf-8")
        self.assertIn("run-a", comparison_csv)
        self.assertIn("run-b", comparison_csv)
        markdown = (self.tmp / "run-a" / "report.md").read_text(encoding="utf-8")
        self.assertIn("## Method comparison", markdown)

    def test_no_figures_for_run_without_figure_sources(self):
        run_dir = _make_run(self.tmp, "run-nofigs", artifacts={"summary": "summary.json", "evaluations": "evaluations.jsonl"})
        result = summarize.run_report(run_dir=run_dir, rewrite_figures=True)
        self.assertEqual(result["report"]["figures"]["generated"], {})
        self.assertEqual(result["report"]["figures"]["errors"], [])

    def test_cli_returns_zero_for_clean_run(self):
        _make_run(self.tmp, "run-cli")
        code = summarize.main(["--run-id", "run-cli", "--output-root", str(self.tmp), "--no-figures"])
        self.assertEqual(code, 0)
        code = summarize.main(["--run-id", "run-missing", "--output-root", str(self.tmp), "--no-figures"])
        self.assertEqual(code, 1)

    def test_artifact_paths_are_not_absolute_in_report(self):
        _make_run(self.tmp, "run-paths")
        summarize.run_report(run_dir=self.tmp / "run-paths", rewrite_figures=False)
        report_json = json.loads((self.tmp / "run-paths" / "report.json").read_text(encoding="utf-8"))
        for entry in report_json["artifacts"]["present"]:
            self.assertFalse(Path(entry).is_absolute(), entry)


if __name__ == "__main__":
    unittest.main()
