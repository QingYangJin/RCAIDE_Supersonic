"""P1 tests for the OpenVSP geometry-export check.

No OpenVSP installation is required. The worker process is replaced by small
stand-in scripts that emit synthetic STL files and metrics, so the tests cover
request construction, sanitization, comparison statuses, failure handling,
placement checks and artifact writing. The real OpenVSP integration is exercised
by the evidence run recorded under optimization_runs, not by this suite.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research.concorde_metaopt.aircraft import openvsp_check
from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.aircraft.geometry_builder import build_geometry_from_design_space

CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "design_space_15d.yaml"
REPO_ROOT = Path(__file__).resolve().parents[3]
TMP_ROOT = Path(tempfile.mkdtemp(prefix="concorde-openvsp-tests-"))

FAKE_FAILURE_WORKER = '''
import json
import sys
from pathlib import Path

result_path = Path(sys.argv[sys.argv.index("--result") + 1])
result_path.write_text(json.dumps({"status": "failed", "error": "fake worker failure"}), encoding="utf-8")
sys.exit(1)
'''

FAKE_SUCCESS_WORKER = '''
import json
import sys
from pathlib import Path

import trimesh


def _arg(name):
    return sys.argv[sys.argv.index(name) + 1]


request = json.loads(Path(_arg("--request")).read_text(encoding="utf-8"))
result_path = Path(_arg("--result"))
export = request["export"]
directory = Path(export["directory"])
basename = export["basename"]

metrics = {}
boxes = {}
for component in request["components"]:
    name = component["name"]
    if component["kind"] == "wing":
        sections = component["sections"]
        semispan = component["span_m"] / 2.0 if component["symmetric"] else component["span_m"]
        area = 0.0
        for first, second in zip(sections, sections[1:]):
            area += (
                0.5
                * (first["chord_m"] + second["chord_m"])
                * (second["percent_span_location"] - first["percent_span_location"])
                * semispan
            )
        if component["symmetric"]:
            area *= 2.0
        metrics[name] = {
            "name": name,
            "total_area_m2": area,
            "total_span_m": component["span_m"],
            "bbox_m": [1.0, 1.0, 1.0],
        }
        if name == "main_wing":
            span = component["span_m"]
            boxes[name] = ((31.5, span, 2.99), (0.0, -span / 2.0, -2.99 / 2.0))
        else:
            span = component["span_m"]
            boxes[name] = ((13.2, span, 1.3), (0.0, 0.0, -0.65))
    else:
        metrics[name] = {
            "name": name,
            "length_m": component["length_m"],
            "bbox_m": [1.0, 1.0, 1.0],
            "bbox_note": "synthetic",
        }
        width = 3.3122883808
        height = 3.3589447496
        boxes[name] = (
            (component["length_m"], width, height),
            (0.0, -width / 2.0, -height / 2.0),
        )


def _write_stl(path, extents, min_corner):
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(
        (
            min_corner[0] + 0.5 * extents[0],
            min_corner[1] + 0.5 * extents[1],
            min_corner[2] + 0.5 * extents[2],
        )
    )
    mesh.export(str(path))
    return {"path": str(path), "bytes": path.stat().st_size}


exports = {"assembly": {}, "components": {}}
exports["assembly"]["stl"] = _write_stl(
    directory / (basename + ".stl"), (61.66, 25.604638252, 3.0), (0.0, -12.802319, -1.679472)
)
for component in request["components"]:
    name = component["name"]
    extents, min_corner = boxes[name]
    entry = _write_stl(directory / (basename + "_" + name + ".stl"), extents, min_corner)
    exports["components"][name] = {"kind": component["kind"], "path": entry["path"], "bytes": entry["bytes"]}

result = {
    "status": "ok",
    "python_version": sys.version.split()[0],
    "openvsp_module": "fake",
    "components": {component["name"]: {"kind": component["kind"]} for component in request["components"]},
    "metrics": metrics,
    "exports": exports,
}
result_path.write_text(json.dumps(result), encoding="utf-8")
'''


def make_fake_root(base: Path, version: str = "9.9.9") -> Path:
    root = base / ("OpenVSP-" + version + "-win64")
    (root / "python" / "openvsp").mkdir(parents=True, exist_ok=True)
    return root


def make_worker(base: Path, name: str, source: str) -> Path:
    path = base / name
    path.write_text(source, encoding="utf-8")
    return path


class PathAndRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.space = load_design_space(CONFIG_PATH)
        cls.geometry = build_geometry_from_design_space(cls.space)

    def test_version_from_root(self):
        self.assertEqual(openvsp_check.openvsp_version_from_root(Path("OpenVSP-3.26.1-win64")), "3.26.1")
        self.assertEqual(openvsp_check.openvsp_version_from_root(Path("x/OpenVSP-3.26.1-win64-Python3.9")), "3.26.1")
        self.assertIsNone(openvsp_check.openvsp_version_from_root(Path("openvsp")))

    def test_resolve_requires_configuration(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(openvsp_check.OpenVSPSetupError):
                openvsp_check.resolve_openvsp_paths(None, None)

    def test_resolve_rejects_missing_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            with self.assertRaises(openvsp_check.OpenVSPSetupError):
                openvsp_check.resolve_openvsp_paths(str(base / "missing.exe"), str(base / "root"))
            python = base / "python.exe"
            python.write_text("", encoding="utf-8")
            with self.assertRaises(openvsp_check.OpenVSPSetupError):
                openvsp_check.resolve_openvsp_paths(str(python), str(make_fake_root(base).parent))

    def test_build_request(self):
        export_dir = TMP_ROOT / "request-export"
        request = openvsp_check.build_openvsp_request(self.geometry, export_dir)
        self.assertIsNone(request["openvsp_root"])
        self.assertEqual(request["export"]["formats"], ["stl", "step", "vsp3"])
        self.assertEqual(Path(request["export"]["directory"]), export_dir.resolve())
        components = {component["name"]: component for component in request["components"]}
        self.assertEqual(sorted(components), ["fuselage", "main_wing", "vertical_tail"])
        self.assertEqual(len(components["main_wing"]["sections"]), 4)
        self.assertEqual(len(components["vertical_tail"]["sections"]), 3)
        self.assertEqual(len(components["fuselage"]["stations"]), 8)
        self.assertTrue(components["main_wing"]["symmetric"])
        self.assertFalse(components["vertical_tail"]["symmetric"])
        self.assertEqual(components["vertical_tail"]["rotation"], [90.0, 0.0, 0.0])
        self.assertAlmostEqual(components["main_wing"]["span_m"], self.geometry.wing.span_m, places=12)
        self.assertAlmostEqual(components["main_wing"]["sections"][1]["chord_m"], self.geometry.wing.sections[1].chord_m, places=12)

    def test_safe_path_and_sanitize(self):
        inside = REPO_ROOT / "research" / "concorde_metaopt" / "cli.py"
        self.assertEqual(openvsp_check._safe_path(inside), "research/concorde_metaopt/cli.py")
        self.assertTrue(str(openvsp_check._safe_path(TMP_ROOT / "x.stl")).startswith("<external>/"))
        export_dir = TMP_ROOT / "sanitize-export"
        request = openvsp_check.build_openvsp_request(self.geometry, export_dir)
        request["openvsp_root"] = "C:/OpenVSP"
        clean = openvsp_check._sanitize_request(request)
        self.assertEqual(clean["openvsp_root"], "<openvsp_root>")
        self.assertEqual(clean["export"]["directory"], "<export_directory>")
        self.assertNotIn(str(TMP_ROOT), json.dumps(clean))

    def test_comparison_statuses(self):
        passed = openvsp_check._comparison("C1", "s", 10.0, 10.0, 0.005)
        self.assertEqual(passed["status"], "pass")
        warned = openvsp_check._comparison("C2", "s", 10.0, 10.5, 0.02, warn_status=True)
        self.assertEqual(warned["status"], "warn")
        failed = openvsp_check._comparison("C3", "s", 10.0, 10.5, 0.02)
        self.assertEqual(failed["status"], "fail")
        missing = openvsp_check._comparison("C4", "s", None, 10.5, 0.02)
        self.assertEqual(missing["status"], "skip")
        self.assertIsNone(missing["relative_delta"])
        zero_model = openvsp_check._comparison("C5", "s", 0.0, 1.0, 0.02)
        self.assertEqual(zero_model["status"], "skip")
        self.assertIsNone(zero_model["relative_delta"])

    def test_abs_comparison_statuses(self):
        passed = openvsp_check._abs_comparison("A1", "s", 14.0, 14.01, 0.02)
        self.assertEqual(passed["status"], "pass")
        self.assertIsNone(passed["relative_delta"])
        self.assertAlmostEqual(passed["absolute_delta"], 0.01)
        failed = openvsp_check._abs_comparison("A2", "s", 14.0, 14.5, 0.02)
        self.assertEqual(failed["status"], "fail")
        missing = openvsp_check._abs_comparison("A3", "s", 14.0, None, 0.02)
        self.assertEqual(missing["status"], "skip")

    def test_status_from_comparisons(self):
        self.assertEqual(openvsp_check._status_from_comparisons([{"status": "pass"}]), "openvsp_check_completed")
        self.assertEqual(
            openvsp_check._status_from_comparisons([{"status": "pass"}, {"status": "warn"}]),
            "openvsp_check_completed_with_warnings",
        )
        self.assertEqual(openvsp_check._status_from_comparisons([{"status": "fail"}]), "openvsp_check_failed")
        self.assertEqual(openvsp_check._status_from_comparisons([]), "openvsp_check_completed")


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geometry = build_geometry_from_design_space(load_design_space(CONFIG_PATH))

    def _worker_result(self):
        return {
            "metrics": {
                "main_wing": {
                    "total_area_m2": 358.25,
                    "total_span_m": 25.604638251691824,
                },
                "vertical_tail": {
                    "total_area_m2": 33.91,
                    "total_span_m": 5.0093312926976585,
                },
                "fuselage": {"length_m": 61.66},
            }
        }

    def _stl_metrics(self):
        return {
            "main_wing": {
                "extents_m": [31.5, 25.604638252, 2.99],
                "bounds_m": [[0.0, -12.802319126, -1.495], [31.5, 12.802319126, 1.495]],
            },
            "vertical_tail": {
                "extents_m": [13.157616068, 5.0093312927, 1.31468402308],
                "bounds_m": [[0.0, 0.0, -0.65734201154], [13.157616068, 5.0093312927, 0.65734201154]],
            },
            "fuselage": {
                "extents_m": [61.66, 3.3122883808, 3.3589447496],
                "bounds_m": [[0.0, -1.6561441904, -1.6794723748], [61.66, 1.6561441904, 1.6794723748]],
            },
            "assembly": {
                "extents_m": [61.66, 25.604638252, 3.0],
                "bounds_m": [[0.0, -12.802319126, -1.6794723748], [61.66, 12.802319126, 1.6794723748]],
            },
            "assembly_composed": {
                "extents_m": [61.66, 25.604638252, 8.303198],
                "bounds_m": [[0.0, -12.802319126, -2.295], [61.66, 12.802319126, 6.009331]],
                "component_bounds_m": {
                    "main_wing": [[14.0, -12.802319126, -2.295], [45.5, 12.802319126, 0.695]],
                    "vertical_tail": [[42.0, -0.65734201154, 1.0], [55.157616068, 0.65734201154, 6.009331]],
                    "fuselage": [[0.0, -1.6561441904, -1.6794723748], [61.66, 1.6561441904, 1.6794723748]],
                },
            },
        }

    def test_compare_passes_with_known_width_warning(self):
        rows = openvsp_check.compare_openvsp(self.geometry, self._worker_result(), self._stl_metrics())
        self.assertEqual(len(rows), 21)
        by_id = {row["check_id"]: row for row in rows}
        self.assertEqual(by_id["OV08_fuselage_width"]["status"], "warn")
        self.assertEqual(by_id["OV09_fuselage_height"]["status"], "pass")
        for check_id in (
            "OV12_wing_x_origin",
            "OV13_wing_z_center",
            "OV14_tail_x_origin",
            "OV15_tail_z_origin",
            "OV16_tail_z_extent",
            "OV17_assembly_x_origin",
            "OV18_assembly_x_extent",
            "OV19_assembly_y_extent",
            "OV20_assembly_z_max",
            "OV21_assembly_z_min",
        ):
            self.assertIn(check_id, by_id)
            self.assertEqual(by_id[check_id]["status"], "pass", check_id)
        self.assertEqual(
            openvsp_check._status_from_comparisons(rows), "openvsp_check_completed_with_warnings"
        )
        self.assertTrue(all(row["status"] == "pass" for key, row in by_id.items() if key != "OV08_fuselage_width"))

    def test_compare_detects_area_failure(self):
        result = self._worker_result()
        result["metrics"]["main_wing"]["total_area_m2"] = 365.0
        rows = openvsp_check.compare_openvsp(self.geometry, result, self._stl_metrics())
        by_id = {row["check_id"]: row for row in rows}
        self.assertEqual(by_id["OV01_wing_area"]["status"], "fail")
        self.assertEqual(openvsp_check._status_from_comparisons(rows), "openvsp_check_failed")

    def test_compare_detects_lost_placement(self):
        metrics = self._stl_metrics()
        metrics["assembly_composed"]["component_bounds_m"]["main_wing"] = [
            [0.0, -12.802319126, -2.295],
            [31.5, 12.802319126, 0.695],
        ]
        rows = openvsp_check.compare_openvsp(self.geometry, self._worker_result(), metrics)
        by_id = {row["check_id"]: row for row in rows}
        self.assertEqual(by_id["OV12_wing_x_origin"]["status"], "fail")
        self.assertEqual(openvsp_check._status_from_comparisons(rows), "openvsp_check_failed")

    def test_compare_marks_missing_metrics_skip(self):
        rows = openvsp_check.compare_openvsp(self.geometry, {}, {})
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["status"] == "skip" for row in rows))
        self.assertEqual(openvsp_check._status_from_comparisons(rows), "openvsp_check_completed")


class ArtifactRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = TMP_ROOT / "runs"
        cls.exports = TMP_ROOT / "exports"
        cls.openvsp_root = make_fake_root(TMP_ROOT / "fake-openvsp")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def _run(self, run_id, **kwargs):
        defaults = dict(
            output_root=self.root,
            export_root=self.exports,
            run_id=run_id,
            openvsp_python=sys.executable,
            openvsp_root=self.openvsp_root,
        )
        defaults.update(kwargs)
        return openvsp_check.run_openvsp_check(**defaults)

    def test_measure_stl_matches_box(self):
        import trimesh

        path = TMP_ROOT / "measure.stl"
        mesh = trimesh.creation.box(extents=(1.0, 2.0, 3.0))
        mesh.export(str(path))
        measured = openvsp_check.measure_stl(path)
        for expected, actual in zip((1.0, 2.0, 3.0), measured["extents_m"]):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertGreater(measured["faces"], 0)

    def test_run_unavailable_writes_summary(self):
        run_id = "unavailable"
        with mock.patch.dict(os.environ, {}, clear=True):
            summary = openvsp_check.run_openvsp_check(
                output_root=self.root,
                export_root=self.exports,
                run_id=run_id,
                openvsp_python=None,
                openvsp_root=None,
            )
        self.assertEqual(summary["status"], "openvsp_check_unavailable")
        self.assertEqual(summary["total_true_evaluations"], 0)
        run_dir = self.root / run_id
        self.assertTrue((run_dir / "summary.json").is_file())
        self.assertTrue((run_dir / "README.md").is_file())
        self.assertIn("not configured", summary["error"])

    def test_run_worker_failure_is_recorded(self):
        run_id = "worker-failure"
        worker = make_worker(TMP_ROOT, "failure_worker.py", FAKE_FAILURE_WORKER)
        with mock.patch.object(openvsp_check, "DEFAULT_WORKER", worker):
            summary = self._run(run_id)
        self.assertEqual(summary["status"], "openvsp_check_worker_failed")
        self.assertIn("fake worker failure", summary["error"])
        run_dir = self.root / run_id
        self.assertTrue((run_dir / "worker_result.json").is_file())
        self.assertTrue((run_dir / "summary.json").is_file())
        worker_result = json.loads((run_dir / "worker_result.json").read_text(encoding="utf-8"))
        self.assertEqual(worker_result["status"], "failed")

    def test_run_success_writes_artifacts(self):
        run_id = "success"
        worker = make_worker(TMP_ROOT, "success_worker.py", FAKE_SUCCESS_WORKER)
        with mock.patch.object(openvsp_check, "DEFAULT_WORKER", worker):
            summary = self._run(run_id)
        self.assertEqual(summary["status"], "openvsp_check_completed_with_warnings")
        self.assertEqual(summary["failed_count"], 0)
        self.assertEqual(summary["openvsp"]["warnings"], ["OV08_fuselage_width"])
        self.assertEqual(summary["openvsp"]["failures"], [])
        self.assertEqual(summary["openvsp"]["measurement_failures"], [])
        self.assertIsNotNone(summary["openvsp"]["composed_assembly"])
        self.assertTrue(summary["openvsp"]["composed_assembly"].endswith(openvsp_check.COMPOSED_ASSEMBLY_FILENAME))
        self.assertEqual(summary["design_dim"], 15)
        self.assertEqual(summary["total_true_evaluations"], 0)
        self.assertIn(summary["git_dirty"], (True, False, None))
        run_dir = self.root / run_id
        for artifact in summary["artifacts"].values():
            self.assertTrue((run_dir / artifact).is_file(), artifact)
        self.assertTrue((run_dir / "README.md").is_file())
        environment = json.loads((run_dir / "environment.json").read_text(encoding="utf-8"))
        self.assertEqual(environment["geometry_model_version"], openvsp_check.GEOMETRY_MODEL_VERSION)
        self.assertEqual(environment["openvsp"]["root_name"], self.openvsp_root.name)
        text = json.dumps(summary)
        self.assertNotIn(str(TMP_ROOT).replace(os.sep, "/"), text)
        self.assertNotIn(chr(92) + chr(92), text)
        self.assertIn("<external>/", text)
        files = summary["external_artifacts"]["files"]
        self.assertEqual(summary["external_artifacts"]["deleted"], False)
        self.assertEqual(summary["external_artifacts"]["ignored_files"], [])
        self.assertTrue(any(entry["kind"] == "assembly_composed" for entry in files))
        self.assertTrue(any(entry["kind"] == "component" for entry in files))
        self.assertTrue(any(entry["kind"] == "worker" for entry in files))
        for entry in files:
            self.assertTrue(entry["sha256"])
            self.assertGreater(entry["bytes"], 0)
            self.assertFalse(Path(entry["path"]).is_absolute())

    def test_measurement_failure_fails_the_check(self):
        run_id = "measurement-failure"
        worker = make_worker(TMP_ROOT, "measurement_worker.py", FAKE_SUCCESS_WORKER)
        with mock.patch.object(openvsp_check, "DEFAULT_WORKER", worker):
            with mock.patch.object(openvsp_check, "measure_stl", side_effect=RuntimeError("unreadable STL")):
                summary = self._run(run_id)
        self.assertEqual(summary["status"], "openvsp_check_failed")
        self.assertGreaterEqual(summary["failed_count"], 1)
        self.assertTrue(summary["openvsp"]["measurement_failures"])
        self.assertIn("unreadable STL", " ".join(summary["openvsp"]["measurement_failures"]))

    def test_measurement_failure_makes_cli_exit_non_zero(self):
        run_id = "measurement-cli"
        worker = make_worker(TMP_ROOT, "measurement_cli_worker.py", FAKE_SUCCESS_WORKER)
        argv = [
            "--run-id",
            run_id,
            "--output-root",
            str(self.root),
            "--export-root",
            str(self.exports),
            "--openvsp-python",
            sys.executable,
            "--openvsp-root",
            str(self.openvsp_root),
        ]
        with mock.patch.object(openvsp_check, "DEFAULT_WORKER", worker):
            with mock.patch.object(openvsp_check, "measure_stl", side_effect=RuntimeError("unreadable STL")):
                rc = openvsp_check.main(argv)
        self.assertEqual(rc, 1)

    def test_delete_exports_removes_raw_files(self):
        run_id = "delete-exports"
        worker = make_worker(TMP_ROOT, "delete_worker.py", FAKE_SUCCESS_WORKER)
        with mock.patch.object(openvsp_check, "DEFAULT_WORKER", worker):
            summary = self._run(run_id, delete_exports=True)
        self.assertEqual(summary["status"], "openvsp_check_completed_with_warnings")
        self.assertTrue(summary["external_artifacts"]["deleted"])
        self.assertFalse((self.exports / run_id / "openvsp").exists())

    def test_existing_export_directory_is_rejected_without_flag(self):
        run_id = "existing-export"
        worker = make_worker(TMP_ROOT, "existing_worker.py", FAKE_SUCCESS_WORKER)
        with mock.patch.object(openvsp_check, "DEFAULT_WORKER", worker):
            self._run(run_id)
            with self.assertRaises(FileExistsError):
                self._run(run_id)
            summary = self._run(run_id, allow_existing=True)
        self.assertEqual(summary["status"], "openvsp_check_completed_with_warnings")


@unittest.skipUnless(
    os.environ.get("CONCORDE_OPENVSP_PYTHON") and os.environ.get("CONCORDE_OPENVSP_ROOT"),
    "CONCORDE_OPENVSP_PYTHON and CONCORDE_OPENVSP_ROOT are required for the real OpenVSP integration test",
)
class RealOpenVSPIntegrationTests(unittest.TestCase):
    def test_real_worker_composes_placement_checked_assembly(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            summary = openvsp_check.run_openvsp_check(
                output_root=base / "runs",
                export_root=base / "exports",
                run_id="real-integration",
                openvsp_python=os.environ["CONCORDE_OPENVSP_PYTHON"],
                openvsp_root=os.environ["CONCORDE_OPENVSP_ROOT"],
                timeout_s=900.0,
            )
            self.assertTrue(summary["status"].startswith("openvsp_check_completed"), summary["status"])
            check_ids = {row["check_id"] for row in summary["openvsp"]["comparisons"]}
            self.assertIn("OV14_tail_x_origin", check_ids)
            self.assertIn("OV12_wing_x_origin", check_ids)
            self.assertTrue(summary["openvsp"]["composed_assembly"])
            self.assertEqual(summary["total_true_evaluations"], 0)


if __name__ == "__main__":
    unittest.main()
