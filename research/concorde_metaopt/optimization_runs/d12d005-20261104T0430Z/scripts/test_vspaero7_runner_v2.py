# -*- coding: utf-8 -*-
"""Regression tests for vspaero7_runner_v2 (LD-001 / LD-002). Zero solver start.

Run from the d12d005 run directory:
  D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m unittest discover -s scripts -p "test_vspaero7_runner_v2.py" -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import vspaero7_runner_v2 as R

NL = chr(10)


def _fmt(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return "%.17g" % float(value)


def setup_text(expected):
    return "\n".join("%s = %s" % (key, _fmt(value)) for key, value in expected.items()) + "\n"


def polar_row(mach=2.02, re_million=89.3970058767656, cltot=0.111, cdtot=0.0078, **overrides):
    values = {name: 0.0 for name in R.POLAR_722_COLUMNS}
    values.update(
        {
            "Beta": 0.0,
            "Mach": mach,
            "AoA": 2.0,
            "Re/1e6": re_million,
            "CLo": 0.001,
            "CLi": 0.110,
            "CLtot": cltot,
            "CDo": 0.0068,
            "CDi": 0.0010,
            "CDtot": cdtot,
            "E": 14.0,
            "CMztot": 0.02,
        }
    )
    values.update(overrides)
    return "  ".join("%.12f" % values[name] for name in R.POLAR_722_COLUMNS)


def polar_text(rows=None, header=None):
    rows = rows if rows is not None else [polar_row(), polar_row(cltot=0.221, cdtot=0.0102)]
    tokens = list(header) if header is not None else list(R.POLAR_722_COLUMNS)
    text = "   Surface Integration Forces and Moments -->\n"
    text += "Surf-Surf-Wing  Surf-Surf-Wing  Surf-Surf-Wing\n"
    text += "  ".join(tokens) + "\n"
    for row in rows:
        text += row + "\n"
    return text


def make_case(root):
    """Create a fully valid thin-wing case dir + setup-generation evidence JSON."""
    root = Path(root)
    case = root / "CASE_X"
    case.mkdir(parents=True)
    expected = dict(R.CONTRACT_12D)
    setup = case / "CASE_X_contract.vspaero"
    setup.write_text(setup_text(expected), encoding="utf-8")
    vspgeom = root / "CASE_X.vspgeom"
    vspgeom.write_bytes(b"fake-vspgeom-bytes-for-gate-test")
    (case / "CASE_X_model.vkey").write_text(
        "# VSPGEOM v3 Tag Key File\n%s\n2\n" % vspgeom, encoding="utf-8"
    )
    (case / "CASE_X_model.csf").write_text("0 Control Surfaces\r\n", encoding="utf-8")
    (case / "geom_result_thin.csv").write_text(
        "Results_Name,VSPAERO_Geom\nGeometrySet,-1\nThinGeometrySet,0\nVSPGeomFileName,%s\n" % vspgeom,
        encoding="utf-8",
    )
    (case / "expected.json").write_text(json.dumps({"contract": expected}), encoding="utf-8")
    evidence = root / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "artifact_kind": "D12D005_A0_SETUP_GENERATION",
                "status": "A0_SETUP_READY_NO_SOLVER",
                "stop_before_run": 1,
                "solver_processes_started": 0,
                "cases": [
                    {
                        "case_id": "CASE_X",
                        "case_dir": str(case),
                        "execution_bundle": {
                            "vspgeom_external_path": str(vspgeom),
                            "vspgeom_sha256": R.sha256_file(vspgeom),
                            "vspgeom_bytes": vspgeom.stat().st_size,
                        },
                        "thin_geometry": {"external_path": str(vspgeom)},
                        "wrapper": {"wrapper_timeout_s": 600, "wall_seconds": 120.0, "returncode": 0, "completed": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return case, evidence


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="v2_runner_test_")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class SetupFormatTests(TempDirTestCase):
    def test_legacy_lines_are_detected(self):
        legacy = "Sref 358.25\nMach 2.02\nAoA 2.0\n"
        parsed = R.parse_setup_text(legacy, source="<legacy>")
        self.assertEqual(len(parsed["legacy_lines"]), 3)
        self.assertEqual(parsed["equals_lines"], [])

    def test_legacy_dir_rejected_by_format_isolation(self):
        path = self.tmp / "legacy.vspaero"
        path.write_text("Sref 358.25\nMach 2.02\n", encoding="utf-8")
        with self.assertRaises(R.FormatIsolationError) as ctx:
            R.assert_new_format_only(self.tmp)
        self.assertIn("LEGACY_FORMAT_IN_NEW_RUN_DIR", str(ctx.exception))

    def test_legacy_normalized_then_readback_passes(self):
        src = self.tmp / "legacy.vspaero"
        legacy = "\n".join("%s %s" % (key, _fmt(value)) for key, value in R.CONTRACT_12D.items()) + "\n"
        src.write_text(legacy, encoding="utf-8")
        dst = self.tmp / "canonical.vspaero"
        report = R.inject_contract_fields(src, dst, dict(R.CONTRACT_12D), allow_legacy=True)
        self.assertEqual(report["assertions"], 17)
        readback = R.read_setup_file(dst, dict(R.CONTRACT_12D))
        self.assertEqual(readback["status"], "PASS")

    def test_legacy_rejected_when_strict(self):
        src = self.tmp / "legacy.vspaero"
        src.write_text("Sref 358.25\nMach 2.02\n", encoding="utf-8")
        with self.assertRaises(R.SetupFormatError):
            R.inject_contract_fields(src, self.tmp / "out.vspaero", dict(R.CONTRACT_12D), allow_legacy=False)


class ReadbackTests(TempDirTestCase):
    def _write(self, expected):
        path = self.tmp / "setup.vspaero"
        path.write_text(setup_text(expected), encoding="utf-8")
        return path

    def test_canonical_setup_passes_with_17_assertions(self):
        report = R.read_setup_file(self._write(dict(R.CONTRACT_12D)))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["assertions"], 17)

    def test_wrong_sref_rejected(self):
        expected = dict(R.CONTRACT_12D)
        expected["Sref"] = 360.0
        with self.assertRaises(R.ContractViolation) as ctx:
            R.read_setup_file(self._write(expected))
        self.assertIn("Sref", str(ctx.exception))

    def test_default_value_leak_rejected(self):
        expected = dict(R.CONTRACT_12D)
        expected["ReCref"] = 1.0e7
        with self.assertRaises(R.ContractViolation) as ctx:
            R.read_setup_file(self._write(expected))
        self.assertIn("LEAK", str(ctx.exception).upper())

    def test_default_vinf_leak_rejected(self):
        expected = dict(R.CONTRACT_12D)
        expected["Vinf"] = 100.0
        with self.assertRaises(R.ContractViolation) as ctx:
            R.read_setup_file(self._write(expected))
        self.assertIn("LEAK", str(ctx.exception).upper())

    def test_setup_gate_rc_nonzero_fails(self):
        path = self._write(dict(R.CONTRACT_12D))
        with self.assertRaises(R.SetupCommandError) as ctx:
            R.require_setup_success(1, path)
        self.assertIn("SETUP_RETURNCODE_FAIL", str(ctx.exception))

    def test_setup_gate_missing_artifact_fails(self):
        with self.assertRaises(R.SetupCommandError) as ctx:
            R.require_setup_success(0, self.tmp / "absent.vspaero")
        self.assertIn("SETUP_ARTIFACT_MISSING", str(ctx.exception))


class Polar722Tests(TempDirTestCase):
    def _write(self, text):
        path = self.tmp / "case.polar"
        path.write_text(text, encoding="utf-8")
        return path

    def test_good_polar_parses_48_columns(self):
        report = R.validate_polar_file(self._write(polar_text()), dict(R.CONTRACT_12D))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["header_token_count"], 48)
        self.assertEqual(report["rows"], 2)
        self.assertAlmostEqual(report["checks"][0]["CLtot"], 0.111)
        self.assertAlmostEqual(report["checks"][1]["CDtot"], 0.0102)

    def test_legacy_62_header_rejected(self):
        legacy_header = " ".join(R.LEGACY_62_POLAR_COLUMNS)
        row = "  ".join("%.6E" % 0.0 for _ in R.LEGACY_62_POLAR_COLUMNS)
        path = self._write("  " + legacy_header + "\n" + row + "\n")
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(path, dict(R.CONTRACT_12D))
        self.assertIn("POLAR_LEGACY_62_HEADER_REJECTED", str(ctx.exception))

    def test_missing_column_rejected(self):
        header = list(R.POLAR_722_COLUMNS)[:-1]
        row = "  ".join("%.12f" % 0.0 for _ in header)
        path = self._write(polar_text(rows=[row], header=header))
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(path, dict(R.CONTRACT_12D))
        self.assertIn("POLAR_", str(ctx.exception))

    def test_nan_rejected(self):
        text = polar_text().replace(polar_row().split("  ")[6], "NAN", 1)
        path = self._write(text)
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(path, dict(R.CONTRACT_12D))
        self.assertIn("POLAR_NONFINITE", str(ctx.exception))

    def test_ind_rejected(self):
        text = polar_text().replace(polar_row().split("  ")[6], "IND", 1)
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(self._write(text), dict(R.CONTRACT_12D))
        self.assertIn("POLAR_NONFINITE", str(ctx.exception))

    def test_wrong_re_rejected(self):
        bad = polar_row(re_million=1.0e7 / 1.0e6)
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(self._write(polar_text(rows=[bad])), dict(R.CONTRACT_12D))
        self.assertIn("POLAR_RE_MISMATCH", str(ctx.exception))

    def test_wrong_mach_rejected(self):
        bad = polar_row(mach=1.5)
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(self._write(polar_text(rows=[bad])), dict(R.CONTRACT_12D))
        self.assertIn("POLAR_MACH_MISMATCH", str(ctx.exception))

    def test_nonphysical_cltot_rejected(self):
        bad = polar_row(cltot=999.0)
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(self._write(polar_text(rows=[bad])), dict(R.CONTRACT_12D))
        self.assertIn("POLAR_NONPHYSICAL", str(ctx.exception))

    def test_no_data_rows_rejected(self):
        text = polar_text(rows=[])
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(self._write(text), dict(R.CONTRACT_12D))
        self.assertIn("POLAR_NO_DATA_ROWS", str(ctx.exception))

    def test_missing_header_rejected(self):
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(self._write("no header here\n1 2 3\n"), dict(R.CONTRACT_12D))
        self.assertIn("POLAR_HEADER_MISSING", str(ctx.exception))


class CaseGateTests(TempDirTestCase):
    def test_valid_case_passes(self):
        case, evidence = make_case(self.tmp)
        report = R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["setup"]["readback_assertions"], 17)
        self.assertEqual(report["stop_before_run"], 1)
        self.assertEqual(report["solver_processes_started"], 0)
        self.assertEqual(report["geom_result"]["GeometrySet"], "-1")
        self.assertEqual(report["geom_result"]["ThinGeometrySet"], "0")
        self.assertEqual(Path(report["vspgeom"]["path"]).name, "CASE_X.vspgeom")

    def test_missing_vkey_rejected(self):
        case, evidence = make_case(self.tmp)
        (case / "CASE_X_model.vkey").unlink()
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_VKEY_MISSING")

    def test_missing_csf_rejected(self):
        case, evidence = make_case(self.tmp)
        (case / "CASE_X_model.csf").unlink()
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_CSF_MISSING")

    def test_thick_geometry_record_rejected(self):
        case, evidence = make_case(self.tmp)
        (case / "geom_result_thin.csv").write_text(
            "Results_Name,VSPAERO_Geom\nGeometrySet,0\nThinGeometrySet,1\n", encoding="utf-8"
        )
        with self.assertRaises(R.DataQualityError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertIn("CASE_THIN_GEOMETRY_MISMATCH", str(ctx.exception))

    def test_missing_vspgeom_rejected(self):
        case, evidence = make_case(self.tmp)
        (self.tmp / "CASE_X.vspgeom").unlink()
        data = json.loads(Path(evidence).read_text(encoding="utf-8"))
        data["cases"][0].pop("execution_bundle")
        data["cases"][0].pop("thin_geometry")
        Path(evidence).write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_VSPGEOM_MISSING")

    def test_missing_stop_before_run_evidence_rejected(self):
        case, _ = make_case(self.tmp)
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case)
        self.assertEqual(ctx.exception.code, "CASE_STOP_BEFORE_RUN_EVIDENCE_MISSING")

    def test_stop_before_run_zero_rejected(self):
        case, evidence = make_case(self.tmp)
        data = json.loads(Path(evidence).read_text(encoding="utf-8"))
        data["stop_before_run"] = 0
        Path(evidence).write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_STOP_BEFORE_RUN_MISSING")

    def test_vkey_geom_mismatch_rejected(self):
        case, evidence = make_case(self.tmp)
        other = self.tmp / "other.vspgeom"
        other.write_bytes(b"x")
        (case / "CASE_X_model.vkey").write_text("# VSPGEOM v3 Tag Key File\n%s\n2\n" % other, encoding="utf-8")
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_VKEY_GEOM_MISMATCH")

    def test_short_wrapper_timeout_rejected(self):
        case, evidence = make_case(self.tmp)
        data = json.loads(Path(evidence).read_text(encoding="utf-8"))
        data["cases"][0]["wrapper"] = {"wrapper_timeout_s": 120, "wall_seconds": 120.0, "returncode": 0}
        Path(evidence).write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_WRAPPER_TIMEOUT_TOO_SHORT")

    def test_residual_solver_artifact_rejected(self):
        case, evidence = make_case(self.tmp)
        (case / "CASE_X_DegenGeom.polar").write_text("stale\n", encoding="utf-8")
        with self.assertRaises(R.RunnerError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertIn("SOLVER_ARTIFACT", str(ctx.exception).upper())


class WrapperGateTests(unittest.TestCase):
    def test_wrapper_120s_rejected(self):
        with self.assertRaises(R.WrapperGateError) as ctx:
            R.validate_wrapper_outcome({"wrapper_timeout_s": 120, "wall_seconds": 120.0, "returncode": -1, "killed": True})
        self.assertEqual(ctx.exception.code, "CASE_WRAPPER_TIMEOUT_TOO_SHORT")

    def test_wrapper_killed_rejected(self):
        with self.assertRaises(R.WrapperGateError) as ctx:
            R.validate_wrapper_outcome({"wrapper_timeout_s": 600, "wall_seconds": 600.0, "returncode": 0, "killed": True})
        self.assertEqual(ctx.exception.code, "CASE_WRAPPER_KILLED_AT_TIMEOUT")

    def test_wrapper_missing_returncode_rejected(self):
        with self.assertRaises(R.WrapperGateError) as ctx:
            R.validate_wrapper_outcome({"wrapper_timeout_s": 600, "wall_seconds": 42.0, "returncode": None})
        self.assertEqual(ctx.exception.code, "CASE_KILLED_BY_WRAPPER")

    def test_wrapper_no_timeout_field_rejected(self):
        with self.assertRaises(R.WrapperGateError) as ctx:
            R.validate_wrapper_outcome({"wall_seconds": 42.0, "returncode": 0})
        self.assertEqual(ctx.exception.code, "CASE_WRAPPER_TIMEOUT_MISSING")

    def test_wrapper_complete_passes(self):
        report = R.validate_wrapper_outcome(
            {"wrapper_timeout_s": 600, "wall_seconds": 120.5, "returncode": 0, "killed": False, "completed": True}
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["returncode"], 0)


class CliTests(TempDirTestCase):
    def test_cli_check_case_dir_passes(self):
        case, evidence = make_case(self.tmp)
        proc = subprocess.run(
            [sys.executable, "-E", "-s", "-B", str(HERE / "vspaero7_runner_v2.py"), "check-case-dir",
             "--dir", str(case), "--evidence", str(evidence), "--case-id", "CASE_X"],
            capture_output=True,
            text=True,
            cwd=str(self.tmp),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "PASS")

    def test_cli_check_case_dir_failure_is_rc2(self):
        case, evidence = make_case(self.tmp)
        (case / "CASE_X_model.csf").unlink()
        proc = subprocess.run(
            [sys.executable, "-E", "-s", "-B", str(HERE / "vspaero7_runner_v2.py"), "check-case-dir",
             "--dir", str(case), "--evidence", str(evidence), "--case-id", "CASE_X"],
            capture_output=True,
            text=True,
            cwd=str(self.tmp),
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("CASE_CSF_MISSING", proc.stdout)

    def test_cli_verify_polar_passes(self):
        polar = self.tmp / "case.polar"
        polar.write_text(polar_text(), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-E", "-s", "-B", str(HERE / "vspaero7_runner_v2.py"), "verify-polar", "--polar", str(polar)],
            capture_output=True,
            text=True,
            cwd=str(self.tmp),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["header_token_count"], 48)


if __name__ == "__main__":
    unittest.main()


class CaseGateHardeningTests(TempDirTestCase):
    """A5 task-103 V2-M01/M02/M03 and minor hardening regressions."""

    def _local_vspgeom_case(self, *, tamper=False):
        case, evidence = make_case(self.tmp)
        local = case / "CASE_X.vspgeom"
        payload = b"fake-vspgeom-bytes-for-gate-test"
        local.write_bytes(b"tampered-bytes" if tamper else payload)
        (case / "CASE_X_model.vkey").write_text(
            "# VSPGEOM v3 Tag Key File%s%s%s2%s" % (NL, local, NL, NL), encoding="utf-8"
        )
        (case / "geom_result_thin.csv").write_text(
            "Results_Name,VSPAERO_Geom%sGeometrySet,-1%sThinGeometrySet,0%sVSPGeomFileName,%s%s"
            % (NL, NL, NL, local, NL),
            encoding="utf-8",
        )
        return case, evidence, local

    def test_vkey_nonexistent_target_rejected(self):
        case, evidence = make_case(self.tmp)
        (case / "CASE_X_model.vkey").write_text(
            "# VSPGEOM v3 Tag Key File%s%s%s2%s" % (NL, self.tmp / "missing.vspgeom", NL, NL),
            encoding="utf-8",
        )
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_VKEY_GEOM_MISMATCH")

    def test_vkey_same_basename_other_dir_rejected(self):
        case, evidence = make_case(self.tmp)
        sibling = self.tmp / "sibling"
        sibling.mkdir()
        other = sibling / "CASE_X.vspgeom"
        other.write_bytes(b"same-basename-other-dir")
        (case / "CASE_X_model.vkey").write_text(
            "# VSPGEOM v3 Tag Key File%s%s%s2%s" % (NL, other, NL, NL), encoding="utf-8"
        )
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_VKEY_GEOM_MISMATCH")

    def test_local_vspgeom_tampered_rejected(self):
        case, evidence, _ = self._local_vspgeom_case(tamper=True)
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_VSPGEOM_SHA_MISMATCH")

    def test_local_vspgeom_matching_record_passes(self):
        case, evidence, local = self._local_vspgeom_case(tamper=False)
        report = R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(report["vspgeom"]["source"], "case_dir")
        self.assertTrue(report["vspgeom"]["evidence_record_verified"])
        self.assertEqual(Path(report["vspgeom"]["path"]), local.resolve())

    def test_missing_solver_processes_started_rejected(self):
        case, evidence = make_case(self.tmp)
        data = json.loads(Path(evidence).read_text(encoding="utf-8"))
        data.pop("solver_processes_started")
        Path(evidence).write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(R.CaseGateError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertEqual(ctx.exception.code, "CASE_SOLVER_PROCESS_EVIDENCE_MISSING")

    def test_csf_trailing_content_rejected(self):
        case, evidence = make_case(self.tmp)
        (case / "CASE_X_model.csf").write_text(
            "0 Control Surfaces%s1 Control Surface%s" % (NL, NL), encoding="utf-8"
        )
        with self.assertRaises(R.RunnerError) as ctx:
            R.check_case_dir(case, evidence=evidence, case_id="CASE_X")
        self.assertIn("CASE_CSF_INVALID", str(ctx.exception))

    def test_polar_header_row_shift_rejected(self):
        path = self.tmp / "shifted.polar"
        path.write_text("padding line" + NL + polar_text(), encoding="utf-8")
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(path, dict(R.CONTRACT_12D))
        self.assertIn("POLAR_HEADER_ROW_UNEXPECTED", str(ctx.exception))

    def test_structure_only_accepts_nonphysical_polar(self):
        path = self.tmp / "archived_v7_00.polar"
        path.write_text(
            polar_text(rows=[polar_row(cltot=-2801.885568189672, cdtot=-376.365943305457)]),
            encoding="utf-8",
        )
        payload = R.parse_polar_structure(path, dict(R.CONTRACT_12D))
        self.assertEqual(payload["status"], "PASS_STRUCTURE_ONLY")
        self.assertEqual(payload["rows"], 1)
        self.assertAlmostEqual(payload["rows_preview"][0]["CLtot"], -2801.885568189672)
        self.assertEqual(payload["physical_validation"], "NOT_APPLIED")
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(path, dict(R.CONTRACT_12D))
        self.assertIn("POLAR_NONPHYSICAL", str(ctx.exception))

