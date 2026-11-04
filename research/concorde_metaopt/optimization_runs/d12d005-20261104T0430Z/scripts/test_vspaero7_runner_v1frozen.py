"""Unit tests for the D-12D-004 pre-gate runner (zero solver start).

Covers the five LD-001 failure branches required by D-12D-004 plus the A2
13-assertion readback contract.  No solver is started.  The project environment
has no pytest (README: tests run with unittest), so this file is unittest-based.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import vspaero7_runner as R  # noqa: E402


CANONICAL_SETUP = """Sref = 358.25
Cref = 18.489893
Bref = 25.604638
X_cg = 16.821978259514246
Y_cg = 0
Z_cg = 0
Mach = 2.02
AoA = 2
Beta = 0
ReCref = 89397005.8767656
Vinf = 596.0373972278921
Rho = 0.1153178340089936
Symmetry = 0
NumWakeNodes = 8
WakeIters = 5
WakeRelax = 1
FarDist = -1
1 2 0
NumberOfInlets = 0
NumberOfNozzles = 0
"""

POLAR_OK = """Beta Mach AoA Re/1e6 CL CDo CDi CDtot E
0 2.02 2 89.3970058767656 0.12 0.0068 0.001 0.0078 0.9
"""

HISTORY_OK = """Sref_ 358.25
Cref_ 18.489893
Bref_ 25.604638
Xcg_ 16.821978259514246
Ycg_ 0
Zcg_ 0
Mach_ 2.02
AoA_ 2
Beta_ 0
Rho_ 0.1153178340089936
Vinf_ 596.0373972278921
"""


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="vspaero7_runner_test_")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return path


class SetupFormatTests(Base):
    def test_parse_canonical_ok(self):
        parsed = R.parse_setup_text(CANONICAL_SETUP)
        self.assertFalse(parsed["legacy_lines"])
        self.assertFalse(parsed["malformed_lines"])
        self.assertEqual(parsed["fields"]["Mach"], "2.02")

    def test_normalize_legacy_equals(self):
        new_text, converted = R.normalize_legacy_text("Sref 358.25\nMach 2.02\n1 2 0\n")
        self.assertEqual(converted, 2)
        self.assertIn("Sref = 358.25", new_text)
        self.assertIn("Mach = 2.02", new_text)
        self.assertIn("1 2 0", new_text)

    def test_strict_mode_rejects_legacy(self):
        src = self.write("legacy.vspaero", "Mach 2.02\nSref 358.25\n")
        with self.assertRaises(R.SetupFormatError):
            R.inject_contract_fields(src, self.tmp / "out.vspaero", allow_legacy=False)

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(R.SetupFormatError):
            R.assert_canonical(R.parse_setup_text("Mach = 2.02\nMach = 2.02\n"))

    def test_malformed_line_rejected(self):
        src = self.write("bad.vspaero", CANONICAL_SETUP + "%%% not a setup line\n")
        with self.assertRaises(R.SetupFormatError):
            R.inject_contract_fields(src, self.tmp / "out.vspaero", allow_legacy=True)


class ReadbackTests(Base):
    def test_inject_and_readback_pass(self):
        src = self.write("in.vspaero", CANONICAL_SETUP)
        report = R.inject_contract_fields(src, self.tmp / "out.vspaero")
        self.assertEqual(report["status"], "PASS")
        self.assertGreaterEqual(report["assertions"], 13)
        self.assertEqual(report["legacy_lines_normalized"], 0)

    def test_readback_wrong_sref_fails(self):
        bad = CANONICAL_SETUP.replace("Sref = 358.25", "Sref = 400.0")
        with self.assertRaises(R.ContractViolation) as ctx:
            R.read_setup_file(self.write("bad.vspaero", bad))
        self.assertIn("Sref", str(ctx.exception))

    def test_default_leak_fails(self):
        bad = CANONICAL_SETUP.replace("Vinf = 596.0373972278921", "Vinf = 100")
        with self.assertRaises(R.ContractViolation) as ctx:
            R.read_setup_file(self.write("leak.vspaero", bad))
        self.assertIn("SETUP_DEFAULT_LEAK", str(ctx.exception))

    def test_thermo_inconsistent_expected_fails(self):
        expected = dict(R.CONTRACT_12D)
        expected["Vinf"] = 500.0
        with self.assertRaises(R.ContractViolation) as ctx:
            R.read_setup_file(self.write("s.vspaero", CANONICAL_SETUP), expected)
        self.assertIn("THERMO_INCONSISTENT", str(ctx.exception))


class SetupCommandGateTests(Base):
    def test_setup_rc_nonzero_fails(self):
        p = self.write("x.vspaero", CANONICAL_SETUP)
        with self.assertRaises(R.SetupCommandError):
            R.require_setup_success(1, p)

    def test_setup_artifact_missing_fails(self):
        with self.assertRaises(R.SetupCommandError):
            R.require_setup_success(0, self.tmp / "missing.vspaero")

    def test_setup_gate_pass(self):
        p = self.write("x.vspaero", CANONICAL_SETUP)
        self.assertEqual(R.require_setup_success(0, p)["status"], "PASS")


class PolarTests(Base):
    def test_polar_pass(self):
        report = R.validate_polar_file(self.write("ok.polar", POLAR_OK), R.CONTRACT_12D)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["rows"], 1)

    def test_polar_nan_fails(self):
        bad = POLAR_OK.replace("0.12", "NaN")
        with self.assertRaises(R.DataQualityError):
            R.validate_polar_file(self.write("nan.polar", bad), R.CONTRACT_12D)

    def test_polar_re_mismatch_fails(self):
        bad = POLAR_OK.replace("89.3970058767656", "10.0", 1)
        with self.assertRaises(R.DataQualityError) as ctx:
            R.validate_polar_file(self.write("re.polar", bad), R.CONTRACT_12D)
        self.assertIn("POLAR_RE_MISMATCH", str(ctx.exception))


class HistoryTests(Base):
    def test_history_pass(self):
        report = R.validate_history_file(self.write("ok.history", HISTORY_OK), R.CONTRACT_12D)
        self.assertEqual(report["status"], "PASS")

    def test_history_sref_mismatch_fails(self):
        bad = HISTORY_OK.replace("Sref_ 358.25", "Sref_ 400.0")
        with self.assertRaises(R.DataQualityError):
            R.validate_history_file(self.write("bad.history", bad), R.CONTRACT_12D)


class SolverIsolationTests(Base):
    def test_start_solver_refused(self):
        with self.assertRaises(R.SolverStartRefused):
            R.start_solver()

    def test_check_dir_detects_solver_artifacts(self):
        self.write("case.polar", POLAR_OK)
        with self.assertRaises(R.DataQualityError):
            R.assert_no_solver_artifacts(self.tmp)

    def test_assert_new_format_only_rejects_legacy(self):
        self.write("legacy.vspaero", "Mach 2.02\nSref 358.25\n")
        with self.assertRaises(R.FormatIsolationError):
            R.assert_new_format_only(self.tmp)

    def test_build_no_solver_evidence(self):
        evidence = R.build_no_solver_evidence("v0", Path("."), {"a": 1})
        self.assertEqual(evidence["solver_starts"], 0)
        self.assertEqual(evidence["billable_numerical_analysis_starts"], 0)
        self.assertEqual(evidence["solver_processes_started"], 0)


class CliTests(Base):
    def test_cli_smoke(self):
        src = self.write("in.vspaero", CANONICAL_SETUP)
        out = self.tmp / "out.vspaero"
        runner = str(HERE / "vspaero7_runner.py")

        norm = subprocess.run(
            [sys.executable, runner, "normalize", "--input", str(src), "--output", str(out)],
            capture_output=True, text=True,
        )
        self.assertEqual(norm.returncode, 0, norm.stderr)
        self.assertEqual(json.loads(norm.stdout)["status"], "PASS")

        ready = subprocess.run(
            [sys.executable, runner, "readback", "--setup", str(out)],
            capture_output=True, text=True,
        )
        self.assertEqual(ready.returncode, 0, ready.stderr)
        self.assertGreaterEqual(json.loads(ready.stdout)["assertions"], 13)

        refused = subprocess.run(
            [sys.executable, runner, "start-solver"], capture_output=True, text=True
        )
        self.assertEqual(refused.returncode, 3)
        self.assertEqual(json.loads(refused.stdout)["status"], "REFUSED")

        gate = subprocess.run(
            [sys.executable, runner, "setup-gate", "--rc", "0", "--setup", str(out)],
            capture_output=True, text=True,
        )
        self.assertEqual(gate.returncode, 0, gate.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
