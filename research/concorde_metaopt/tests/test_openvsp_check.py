"""P1 tests for the OpenVSP geometry-export check.

No OpenVSP installation is required. The worker process is replaced by small
stand-in scripts that emit synthetic STL files and metrics, so the tests cover
request construction, sanitization, comparison statuses, failure handling and
artifact writing. The real OpenVSP integration is exercised by the evidence run
recorded under optimization_runs, not by this suite.
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
        boxes[name] = (31.5, component["span_m"], 2.99) if name == "main_wing" else (13.2, component["span_m"], 1.3)
    else:
        metrics[name] = {
            "name": name,
            "length_m": component["length_m"],
            "bbox_m": [1.0, 1.0, 1.0],
            "bbox_note": "synthetic",
        }
        boxes[name] = (component["length_m"], 3.3122883808, 3.3589447496)


def _write_stl(path, extents):
    mesh = trimesh.creation.box(extents=extents)
    mesh.export(str(path))
    return {"path": str(path), "bytes": path.stat().st_size}


exports = {"assembly": {}, "components": {}}
exports["assembly"]["stl"] = _write_stl(directory / (basename + ".stl"), (61.66, 25.604638252, 3.0))
for component in request["components"]:
    name = component["name"]
    entry = _write_stl(directory / (basename + "_" + name + ".stl"), boxes[name])
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
            "main_wing": {"extents_m": [31.5, 25.604638252, 2.99]},
            "vertical_tail": {"extents_m": [13.157616068, 5.0093312927, 1.31468402308]},
            "fuselage": {"extents_m": [61.66, 3.3122883808, 3.3589447496]},
            "assembly": {"extents_m": [61.66, 25.604638252, 3.0]},
        }

    def test_compare_passes_with_known_width_warning(self):
        rows = openvsp_check.compare_openvsp(self.geometry, self._worker_result(), self._stl_metrics())
        self.assertEqual(len(rows), 11)
        by_id = {row["check_id"]: row for row in rows}
        self.assertEqual(by_id["OV08_fuselage_width"]["status"], "warn")
        self.assertEqual(by_id["OV09_fuselage_height"]["status"], "pass")
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
            summary = openvsp_check.run_openvsp_check(
                output_root=self.root,
                export_root=self.exports,
                run_id=run_id,
                openvsp_python=sys.executable,
                openvsp_root=self.openvsp_root,
            )
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
            summary = openvsp_check.run_openvsp_check(
                output_root=self.root,
                export_root=self.exports,
                run_id=run_id,
                openvsp_python=sys.executable,
                openvsp_root=self.openvsp_root,
            )
        self.assertEqual(summary["status"], "openvsp_check_completed_with_warnings")
        self.assertEqual(summary["failed_count"], 0)
        self.assertEqual(summary["openvsp"]["warnings"], ["OV08_fuselage_width"])
        self.assertEqual(summary["openvsp"]["failures"], [])
        self.assertEqual(summary["design_dim"], 15)
        self.assertEqual(summary["total_true_evaluations"], 0)
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
        self.assertTrue(summary["external_artifacts"]["files"])
        for entry in summary["external_artifacts"]["files"]:
            self.assertTrue(entry["sha256"])
            self.assertGreater(entry["bytes"], 0)
            self.assertFalse(Path(entry["path"]).is_absolute())


if __name__ == "__main__":
    unittest.main()
