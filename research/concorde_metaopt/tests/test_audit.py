"""Unit tests for the read-only P0 audit helpers.

These tests never launch a Mission, CFD case or external solver: discovery that
would touch the machine is replaced with fixtures or mocks.

Temporary data is written under tests/_tmp (ignored by git) because this
sandboxed host denies writes to the system temp directory and to directories
created by tempfile.mkdtemp, while ordinary mkdir + open works inside the
repository.
"""
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

from research.concorde_metaopt import audit

TMP_ROOT = Path(__file__).resolve().parent / "_tmp"


def make_tmp_dir() -> Path:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TMP_ROOT / ("case-" + uuid.uuid4().hex[:12])
    path.mkdir(parents=True, exist_ok=True)
    return path


class HelperTests(unittest.TestCase):
    def test_sha256_matches_known_digest(self):
        path = make_tmp_dir() / "a.txt"
        path.write_text("abc", encoding="utf-8")
        self.assertEqual(
            audit._sha256(path),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_md_table_renders_header_and_rows(self):
        text = audit._md_table(["a", "b"], [["1", "2"]])
        self.assertIn("| a | b |", text)
        self.assertIn("| 1 | 2 |", text)


class ConcordeScanTests(unittest.TestCase):
    def test_scan_concorde_uses_real_tutorial_identifiers(self):
        root = make_tmp_dir()
        target = root / "tutorials" / "Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission" / "Concorde.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "def main():",
            "    pass",
            "",
            "def vehicle_setup():",
            "    segment_6 = 1",
            "    append_segment(segment_6)",
            "    vertical_stabilizer = 2",
            "    fuselages = []",
        ]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        info = audit.scan_concorde(root)
        self.assertTrue(info["exists"])
        self.assertEqual(info["line_count"], len(lines))
        self.assertIn("vehicle_setup", {fn["name"] for fn in info["top_level_functions"]})
        self.assertEqual(info["term_counts"]["segment_6"], 2)
        self.assertGreaterEqual(info["term_counts"]["append_segment"], 1)
        self.assertGreaterEqual(info["term_counts"]["vertical_stabilizer"], 1)
        self.assertGreaterEqual(info["term_counts"]["fuselages"], 1)

    def test_scan_concorde_reports_missing_file(self):
        info = audit.scan_concorde(make_tmp_dir())
        self.assertFalse(info["exists"])
        self.assertTrue(info.get("error"))


class ConcordeStructureTests(unittest.TestCase):
    def test_component_counts_tags_and_duplicates(self):
        root = make_tmp_dir()
        target = root / "tutorials" / "Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission" / "Concorde.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "wing.append_segment(segment)",
            "wing.append_segment(segment)",
            "wing.tag = 'vertical_stabilizer'",
            "wing.append_segment(segment)",
            "fuselage.append_segment(segment)",
            "fuselage.append_segment(segment)",
            "segment.tag = 'segment_6'",
            "segment.tag = 'segment_6'",
            "mission.append_segment(segment)",
            "segment.tag = 'level_cruise'",
            "mission.append_segment(segment)",
            "mass_properties = wing.mass_properties",
            "area = wing.areas.reference",
        ]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        info = audit.scan_concorde(root)
        counts = info["component_segment_counts"]
        self.assertEqual(counts["main_wing_segments"], 2)
        self.assertEqual(counts["vertical_stabilizer_segments"], 1)
        self.assertEqual(counts["fuselage_segments"], 2)
        self.assertEqual(counts["mission_segments"], 2)
        self.assertIn("level_cruise", info["mission_segment_tags"])
        self.assertEqual(info["duplicate_segment_tags"].get("segment_6"), 2)
        self.assertEqual(info["level_cruise_lines"][0]["line"], 10)
        self.assertGreaterEqual(info["derived_quantity_counts"][".areas.reference"], 1)


class MamlScanTests(unittest.TestCase):
    def test_legacy_scan_roots_have_no_type_error(self):
        roots = audit._legacy_scan_roots(Path("D:/RCAIDE"))
        names = [Path(root).name for root in roots]
        self.assertIn("tutorials", names)
        self.assertIn("research", names)
        self.assertIn("MAML元学习", names)

    def test_find_maml_source_project_returns_empty_when_absent(self):
        self.assertEqual(audit._find_maml_source_project([Path("D:/RCAIDE/tutorials")]), [])


class ExternalToolTests(unittest.TestCase):
    def test_openvsp_sys_path_candidates_cover_package_and_deps(self):
        roots = audit.OPENVSP_API_PARENT_CANDIDATES
        self.assertGreaterEqual(len(roots), 4)
        joined = "|".join(roots)
        self.assertIn("python\\openvsp", joined)
        self.assertIn("python\\degen_geom", joined)
        self.assertIn("python\\utilities", joined)

    def test_discover_external_tools_does_not_mutate_global_state(self):
        before = json.loads(json.dumps(audit.EXTERNAL_TOOLS))
        fake = {"cmd": ["x"], "returncode": 0, "stdout": "ok", "stderr": "", "timed_out": False, "seconds": 0.0}
        with mock.patch.object(audit, "_run", return_value=dict(fake)):
            tools = audit.discover_external_tools(Path("."))
        self.assertEqual(before, audit.EXTERNAL_TOOLS)
        self.assertIn("su2_cfd", tools)
        self.assertIn("openvsp_gui", tools)


class ToolchainEvidenceTests(unittest.TestCase):
    def test_toolchain_marks_unprobed_distributions(self):
        root = make_tmp_dir()
        environment = {
            "git": {"branch": "b", "head_sha": "c" * 40, "dirty": False, "status_lines": []},
            "python": {"version": "3.11"},
            "packages": {
                "distributions": {"pandas": {"version": "3.0", "location": "site-packages"}, "numpy": {"version": "2.4"}},
                "imports": {"numpy": {"ok": True, "version_attr": "2.4", "error": None}},
            },
            "external_tools": {},
            "concorde": {"relative_path": "x", "sha256": "y", "line_count": 1},
            "maml_opt": {"api": {}},
            "rcaide_cfd": {},
            "rcaide": {},
            "blockers": [],
            "checks": {"pip_check": {"cmd": ["python", "-m", "pip", "check"], "returncode": 0, "stdout": "No broken requirements found."}},
        }
        audit._write_evidence(root, environment, root)
        text = (root / "evidence" / "toolchain_table.md").read_text(encoding="utf-8")
        self.assertIn("not_probed", text)
        self.assertNotIn("| pandas | 3.0 | failed |", text)


class BlockerTests(unittest.TestCase):
    def test_build_blockers_shape_and_conditional_ids(self):
        environment = {
            "packages": {"imports": {}},
            "external_tools": {"openvsp_python_binding": {}, "gmsh_python_binding": {}},
            "rcaide_cfd": {"evidence": {}},
            "maml_opt": {"distribution": {}, "legacy_13d_scan": {"hits": []}},
            "concorde": {"exists": True, "relative_path": "tutorials/x/Concorde.py", "line_count": 10},
            "git": {"dirty": False},
            "python": {},
        }
        blockers = audit.build_blockers(environment)
        ids = {b["id"] for b in blockers}
        self.assertIn("B-P1-CONCORDE-ADAPTER", ids)
        self.assertIn("B-P1-OPENVSP-BINDING", ids)
        self.assertIn("B-P3-GMSH-BINDING", ids)
        self.assertIn("B-GOV-BUDGET", ids)
        self.assertNotIn("B-P0-DIRTY-WORKTREE", ids)
        for blocker in blockers:
            self.assertTrue(blocker["id"])
            self.assertTrue(blocker["severity"])
            self.assertTrue(blocker["statement"])
            self.assertIn("evidence", blocker)

    def test_dirty_worktree_is_reported(self):
        environment = {
            "packages": {"imports": {}},
            "external_tools": {},
            "rcaide_cfd": {},
            "maml_opt": {"legacy_13d_scan": {"hits": ["x"]}},
            "concorde": {"exists": True},
            "git": {"dirty": True, "status_lines": [" M a"]},
            "python": {},
        }
        ids = {b["id"] for b in audit.build_blockers(environment)}
        self.assertIn("B-P0-DIRTY-WORKTREE", ids)


    def test_maml_source_blocker_when_direct_url_missing(self):
        environment = {
            "packages": {"imports": {}},
            "external_tools": {},
            "rcaide_cfd": {},
            "maml_opt": {
                "distribution": {"direct_url": None, "location": "site-packages", "version": "0.1.0"},
                "legacy_13d_scan": {"hits": [], "scanned_files": 12},
                "scan_roots": ["tutorials", "research"],
            },
            "concorde": {"exists": True},
            "git": {"dirty": False},
            "python": {},
        }
        blockers = audit.build_blockers(environment)
        ids = {b["id"] for b in blockers}
        self.assertIn("B-P5-MAML-SOURCE", ids)
        legacy = [b for b in blockers if b["id"] == "B-P5-LEGACY-13D-APP"][0]
        self.assertIn("12 files", legacy["statement"])
        self.assertIn("no hit", legacy["statement"])
        self.assertNotIn("not located in bounded scans", legacy["statement"])

    def test_legacy_blocker_distinguishes_index_hits_from_application_source(self):
        environment = {
            "packages": {"imports": {}},
            "external_tools": {},
            "rcaide_cfd": {},
            "maml_opt": {
                "distribution": {"direct_url": "https://example.invalid", "location": "site-packages", "version": "0.1.0"},
                "legacy_13d_scan": {"hits": [{"path": "tutorials/tutorial_index.json", "line": 1, "term": "concorde"}],
                                    "scanned_files": 137, "truncated": True},
                "scan_roots": ["tutorials"],
                "source_project": [],
            },
            "concorde": {"exists": True},
            "git": {"dirty": False},
            "python": {},
        }
        blockers = audit.build_blockers(environment)
        legacy = [b for b in blockers if b["id"] == "B-P5-LEGACY-13D-APP"][0]
        self.assertIn("137 files", legacy["statement"])
        self.assertIn("1 textual hits", legacy["statement"])
        self.assertIn("remains unlocated", legacy["statement"])
        self.assertIn("tutorial_index.json", " ".join(legacy["evidence"]["hit_files"]))

    def test_openvsp_blocker_is_minor_when_external_worker_works(self):
        environment = {
            "packages": {"imports": {}},
            "external_tools": {
                "openvsp_python_binding": {
                    "project_interpreter_import": {"ok": False, "error": "ModuleNotFoundError"},
                    "external_interpreters": [
                        {"python": "D:/Anaconda/envs/SUAVE/python.exe",
                         "probe": {"stdout": "OPENVSP_IMPORT_OK D:/OpenVSP/openvsp/__init__.py \n"}}
                    ],
                }
            },
            "rcaide_cfd": {},
            "maml_opt": {"legacy_13d_scan": {"hits": ["x"]}},
            "concorde": {"exists": True},
            "git": {"dirty": False},
            "python": {},
        }
        blockers = audit.build_blockers(environment)
        openvsp = [b for b in blockers if b["id"] == "B-P1-OPENVSP-BINDING"][0]
        self.assertEqual(openvsp["severity"], "minor")
        self.assertIn("worker", openvsp["statement"])


class GitProbeTests(unittest.TestCase):
    def test_shell_probe_overrides_denied_subprocess(self):
        denied = {"returncode": None, "stdout": "", "stderr": "PermissionError: [WinError 5]", "seconds": 0.0}
        probes = {
            "git": {
                "head_sha": "a" * 40,
                "branch": "research/concorde-metaopt",
                "status_lines": [" M .gitignore"],
                "returncodes": {"head": 0, "branch": 0, "status": 0},
            }
        }
        with mock.patch.object(audit, "_run", return_value=dict(denied)):
            git = audit.discover_git(Path("."), shell_probes=probes)
        self.assertEqual(git["head_sha"], "a" * 40)
        self.assertEqual(git["branch"], "research/concorde-metaopt")
        self.assertTrue(git["dirty"])
        self.assertEqual(git["probe_source"], "shell_probe")
        self.assertIsNone(git["status_error"])


class RunAuditTests(unittest.TestCase):
    def test_run_audit_writes_summary_and_evidence_without_simulation(self):
        root = make_tmp_dir()
        output_root = root / "runs"
        patches = [
            mock.patch.object(audit, "discover_git", return_value={
                "head_sha": "b" * 40, "branch": "test-branch", "dirty": False,
                "status_lines": [], "probe_source": "test"}),
            mock.patch.object(audit, "discover_python", return_value={"executable": "python", "version": "3.11"}),
            mock.patch.object(audit, "discover_packages", return_value={"imports": {}, "distributions": {}}),
            mock.patch.object(audit, "discover_external_tools", return_value={}),
            mock.patch.object(audit, "discover_checks", return_value={
                "pip_check": {"cmd": ["python", "-m", "pip", "check"], "returncode": 0,
                              "stdout": "No broken requirements found.", "stderr": "", "timed_out": False},
                "package_tests": {},
            }),
            mock.patch.object(audit, "scan_concorde", return_value={
                "exists": True, "relative_path": "tutorials/x/Concorde.py", "line_count": 3}),
            mock.patch.object(audit, "discover_maml_opt", return_value={"distribution": {}}),
            mock.patch.object(audit, "discover_rcaide_cfd", return_value={"evidence": {}}),
            mock.patch.object(audit, "discover_rcaide", return_value={}),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        result = audit.run_audit(repo_root=root, output_root=output_root, run_id="audit-test")
        summary = result["summary"]
        run_dir = output_root / "audit-test"
        self.assertEqual(summary["run_id"], "audit-test")
        self.assertEqual(summary["stage"], "P0")
        self.assertEqual(summary["status"], "audit_completed")
        self.assertEqual(summary["total_true_evaluations"], 0)
        self.assertIsNone(summary["design_dim"])
        self.assertTrue(summary["git_sha"])
        for name in ["environment.json", "summary.json", "README.md", "evidence/blocker_list.md", "evidence/checks.json"]:
            self.assertTrue((run_dir / name).exists(), name)
        environment = json.loads((run_dir / "environment.json").read_text(encoding="utf-8"))
        self.assertEqual(environment["stage"], "P0")
        self.assertEqual(result["output_dir"], str(run_dir.resolve()))
        notes = " ".join(environment["notes"]).lower()
        self.assertIn("no mission", notes)
        raw = (run_dir / "environment.json").read_text(encoding="utf-8")
        self.assertIn("<repo_root>", raw)
        self.assertNotIn(str(root.resolve()), raw)


if __name__ == "__main__":
    unittest.main()
