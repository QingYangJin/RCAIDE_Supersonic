#!/usr/bin/env python
"""A0 v2 setup 生成器单元测试（D-12D-005 Batch2，零求解器）。

覆盖：
  1) mach-aware Gate2 解析公式（2D Ackeret / 一阶有限展长）与 S6 预期带；
  2) 旧亚声速 Helmbold 带与 S3 shortfall 复算；
  3) 8-case 计划与合同一致性（12D / 标准翼 / S6）；
  4) Gate2 repair 注册内容（post-hoc 披露、观测值、废止数值带）；
  5) expected_v2 逻辑（std 有 CL 带、d12 无独立参考）；
  6) 负控制 helper（字段改写/缺字段报错）与 repeatability 判定逻辑；
  7) 生成证据产物（若已运行生成）：8 case/17-17 readback/parity/负控制/零 solver。

运行：D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/test_a0_generate_setups_v2.py
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GENERATOR = SCRIPT_DIR / "a0_generate_setups_v2.py"
REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_generator():
    spec = importlib.util.spec_from_file_location("a0_generate_setups_v2", GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 %s" % (GENERATOR,))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A0 = _load_generator()

MACH = 2.02
AR = 4.0
BETA = math.sqrt(MACH * MACH - 1.0)
CL_ALPHA_2D = 4.0 / BETA
CL_ALPHA_3D = CL_ALPHA_2D / (1.0 + CL_ALPHA_2D / (math.pi * AR))


class MachAwareFormulaTests(unittest.TestCase):
    def test_01_ackeret_2d_values(self):
        theory = A0.mach_aware_cl(MACH, 2.0, AR)
        self.assertAlmostEqual(theory["beta"], BETA, places=12)
        self.assertAlmostEqual(theory["CL_alpha_2d_per_rad"], CL_ALPHA_2D, places=12)
        self.assertAlmostEqual(theory["CL_2d"], 2.0 * math.pi / 180.0 * CL_ALPHA_2D, places=12)
        # 预注册值：2D Ackeret CL(2deg) = 0.079554
        self.assertAlmostEqual(theory["CL_2d"], 0.07955432537008524, places=12)

    def test_02_finite_wing_values(self):
        theory = A0.mach_aware_cl(MACH, 2.0, AR)
        self.assertAlmostEqual(theory["CL_alpha_3d_first_order_per_rad"], CL_ALPHA_3D, places=12)
        # 预注册值：一阶有限展长 CL(2deg) = 0.067341
        self.assertAlmostEqual(theory["CL_3d_first_order"], 0.06734118557858278, places=12)

    def test_03_3d_below_2d_and_in_range(self):
        theory = A0.mach_aware_cl(MACH, 2.0, AR)
        self.assertLess(theory["CL_3d_first_order"], theory["CL_2d"])
        low, high = A0.GATE2_DIAGNOSTIC_CL_RANGE
        self.assertLessEqual(low, theory["CL_3d_first_order"])
        self.assertLessEqual(theory["CL_3d_first_order"], high)
        self.assertLessEqual(low, theory["CL_2d"])
        self.assertLessEqual(theory["CL_2d"], high)

    def test_04_s6_aoa1_is_half(self):
        two = A0.mach_aware_cl(MACH, 2.0, AR)
        one = A0.mach_aware_cl(MACH, 1.0, AR)
        self.assertAlmostEqual(one["CL_2d"], two["CL_2d"] / 2.0, places=12)
        self.assertAlmostEqual(one["CL_3d_first_order"], two["CL_3d_first_order"] / 2.0, places=12)
        low, high = A0.S6_EXPECTED_CL_RANGE
        self.assertLessEqual(low, one["CL_3d_first_order"])
        self.assertLessEqual(one["CL_3d_first_order"], high)
        self.assertAlmostEqual(one["CL_3d_first_order"], 0.03367059278929139, places=12)


class LegacyHelmboldTests(unittest.TestCase):
    def test_01_old_band(self):
        old = A0.subsonic_helmbold_cl(MACH, 2.0, AR)
        cl = old["CL"]
        self.assertAlmostEqual(cl, 0.13554, places=4)
        low, high = old["CL_expected_range"]
        self.assertAlmostEqual(low, round(0.8 * cl, 6), places=9)
        self.assertAlmostEqual(high, round(1.2 * cl, 6), places=9)
        self.assertGreater(low, 0.10)
        self.assertLess(low, 0.12)

    def test_02_s3_shortfall_recomputed(self):
        old = A0.subsonic_helmbold_cl(MACH, 2.0, AR)
        low = old["CL_expected_range"][0]
        shortfall = (1.0 - A0.OBSERVED_S3["CLtot"] / low) * 100.0
        registration = A0.build_gate2_registration()
        registered = registration["old_registration"]["S3_shortfall_vs_lower_bound_pct"]
        self.assertAlmostEqual(shortfall, registered, places=2)
        self.assertAlmostEqual(registered, 31.528, places=3)

    def test_03_observed_values_registered(self):
        registration = A0.build_gate2_registration()
        s3 = registration["observed"]["S3_STD_M2p02_base"]
        s4 = registration["observed"]["S4_STD_M2p02_wn128"]
        self.assertAlmostEqual(s3["CLtot"], 0.074251031783, places=12)
        self.assertAlmostEqual(s3["CDi"], 0.002606540227, places=12)
        self.assertAlmostEqual(s3["CDtot"], 0.013789407924, places=12)
        self.assertAlmostEqual(s4["CLtot"], 0.074250958215, places=12)
        self.assertTrue(s3["in_diagnostic_range"])
        self.assertTrue(s4["in_diagnostic_range"])


class CasePlanTests(unittest.TestCase):
    def test_01_eight_cases(self):
        self.assertEqual(len(A0.CASES), 8)
        ids = [case["case_id"] for case in A0.CASES]
        self.assertEqual(ids, [
            "B2-01", "B2-02", "B2-03", "B2-04", "B2-05", "B2-06", "B2-07",
            "S6_STD_M2p02_aoa1",
        ])
        self.assertEqual(len(set(ids)), 8)

    def test_02_tess_and_repeat(self):
        lookup = {case["case_id"]: case for case in A0.CASES}
        self.assertEqual(lookup["B2-01"]["tess"], 3.0)
        self.assertEqual(lookup["B2-02"]["tess"], 6.0)
        self.assertEqual(lookup["B2-03"]["tess"], 12.0)
        self.assertEqual(lookup["B2-04"]["tess"], 12.0)
        self.assertEqual(lookup["B2-07"]["repeat_of"], "B2-03")
        self.assertEqual(lookup["B2-07"]["design"], {})
        self.assertEqual(lookup["S6_STD_M2p02_aoa1"]["kind"], "std")
        self.assertEqual(lookup["S6_STD_M2p02_aoa1"]["contract"], "std_mach2p02_aoa1")
        self.assertEqual(A0.NEGATIVE_CONTROL_CASE, "B2-03")

    def test_03_single_factor_designs(self):
        lookup = {case["case_id"]: case for case in A0.CASES}
        self.assertEqual(lookup["B2-04"]["design"], {"wing_area": 376.1625})
        self.assertEqual(lookup["B2-05"]["design"], {"sweep_1": 69.0})
        self.assertEqual(lookup["B2-06"]["design"], {"tip_twist": 2.0})
        for case_id in ("B2-01", "B2-02", "B2-03", "B2-07"):
            self.assertEqual(lookup[case_id]["design"], {})
            self.assertEqual(lookup[case_id]["kind"], "d12")


class ContractTests(unittest.TestCase):
    def test_01_d12_contract_fields(self):
        contract = A0.D12_CONTRACT
        self.assertEqual(len(contract), 17)
        self.assertEqual(contract["Sref"], 358.25)
        self.assertEqual(contract["Cref"], 18.489893)
        self.assertEqual(contract["Bref"], 25.604638)
        self.assertEqual(contract["Mach"], 2.02)
        self.assertEqual(contract["AoA"], 2.0)
        self.assertEqual(contract["NumWakeNodes"], 8)
        self.assertEqual(contract["WakeIters"], 5)
        self.assertAlmostEqual(contract["X_cg"], 16.821978259514246, places=12)
        self.assertAlmostEqual(contract["ReCref"], 89397005.8767656, places=6)
        self.assertAlmostEqual(contract["Vinf"], 596.0373972278921, places=10)

    def test_02_std_contract(self):
        std = A0.std_contract(2.02, 8, 5)
        self.assertEqual(len(std), 17)
        self.assertEqual(std["Sref"], 4.0)
        self.assertEqual(std["Cref"], 1.0)
        self.assertEqual(std["Bref"], 4.0)
        self.assertEqual(std["Mach"], 2.02)
        self.assertEqual(std["AoA"], 2.0)
        self.assertAlmostEqual(std["Vinf"], 2.02 * A0.A_SOUND, places=12)
        self.assertAlmostEqual(std["ReCref"], A0.RHO * std["Vinf"] * 1.0 / A0.MU, places=6)

    def test_03_s6_contract(self):
        lookup = {case["case_id"]: case for case in A0.CASES}
        contract = A0.case_contract(lookup["S6_STD_M2p02_aoa1"])
        self.assertEqual(contract["AoA"], 1.0)
        self.assertEqual(contract["Mach"], 2.02)
        self.assertEqual(contract["Sref"], 4.0)
        self.assertEqual(contract["NumWakeNodes"], 8)
        self.assertEqual(set(contract), set(A0.D12_CONTRACT))

    def test_04_d12_case_contract(self):
        lookup = {case["case_id"]: case for case in A0.CASES}
        self.assertEqual(A0.case_contract(lookup["B2-03"]), A0.D12_CONTRACT)
        self.assertIsNot(A0.case_contract(lookup["B2-03"]), A0.D12_CONTRACT)


class Gate2RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.registration = A0.build_gate2_registration()

    def test_01_structure(self):
        registration = self.registration
        self.assertEqual(registration["schema_version"], "d12d005-a0v2-gate2-repair-1")
        self.assertEqual(registration["status"], "REGISTERED_POST_HOC_DIAGNOSTIC")
        self.assertEqual(registration["solver_processes_started"], 0)
        self.assertEqual(registration["physical_call_count"], 0)
        self.assertEqual(registration["run_id"], A0.RUN_DIR.name)

    def test_02_disclosure(self):
        disclosure = self.registration["disclosure"]
        self.assertTrue(disclosure["post_hoc_correction"])
        self.assertTrue(disclosure["a5_had_already_assessed"])
        self.assertIn("S6_STD_M2p02_aoa1", disclosure["independence"])
        self.assertIn("不修改", disclosure["no_retroactive_relabeling"])

    def test_03_bands_and_gates(self):
        replacement = self.registration["replacement_bands"]
        self.assertEqual(replacement["CL_diagnostic_range"], [0.060, 0.090])
        self.assertEqual(replacement["CDi_CDtot_numeric_bands"].split("（")[0], "VOID")
        self.assertEqual(len(replacement["CDi_CDtot_qualitative_gates"]), 4)
        old = self.registration["old_registration"]
        self.assertEqual(old["status"], "VOID_FOR_SUPERSONIC_CASES")
        self.assertGreater(old["CL_expected_range"][0], 0.10)

    def test_04_written_artifact_matches(self):
        path = A0.GATE2_PATH
        if not path.is_file():
            self.skipTest("gate2 注册文件尚未生成（先运行生成器）")
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written["schema_version"], self.registration["schema_version"])
        self.assertEqual(written["status"], self.registration["status"])
        self.assertEqual(written["observed"]["S3_STD_M2p02_base"]["CLtot"],
                         self.registration["observed"]["S3_STD_M2p02_base"]["CLtot"])
        self.assertEqual(written["replacement_bands"]["CL_diagnostic_range"], [0.060, 0.090])


class ExpectedPayloadTests(unittest.TestCase):
    def _case(self, case_id):
        return {case["case_id"]: case for case in A0.CASES}[case_id]

    def test_01_std_payload_has_cl_range(self):
        case = self._case("S6_STD_M2p02_aoa1")
        contract = A0.case_contract(case)
        payload = A0.build_expected_payload(case, contract, {"assertions": 17})
        self.assertEqual(payload["schema_version"], "d12d005-a0v2-expected-1")
        self.assertEqual(payload["readback_assertions"], 17)
        analytic = payload["analytic_expectations"]
        self.assertEqual(analytic["CL_expected_range"], [0.030, 0.045])
        self.assertTrue(analytic["independent_confirmation"])
        self.assertAlmostEqual(analytic["CL_3d_first_order"], 0.03367059278929139, places=12)
        self.assertLessEqual(0.030, analytic["CL_3d_first_order"])
        self.assertLessEqual(analytic["CL_3d_first_order"], 0.045)
        self.assertEqual(payload["solver_processes_started"], 0)

    def test_02_d12_payload_no_independent_reference(self):
        case = self._case("B2-03")
        contract = A0.case_contract(case)
        payload = A0.build_expected_payload(case, contract, {"assertions": 17})
        self.assertIsNone(payload["analytic_expectations"]["cl_expected_range"])
        self.assertFalse(payload["analytic_expectations"]["independent_confirmation"])
        self.assertEqual(payload["analytic_expectations"]["cl_expected_range"], None)


class RewriteSetupFieldTests(unittest.TestCase):
    def test_01_rewrite(self):
        text = "Sref = 4.0\nMach = 2.02\nNumWakeNodes = 8\n"
        rewritten = A0.rewrite_setup_field(text, "Sref", "100.0")
        self.assertIn("Sref = 100.0", rewritten)
        self.assertIn("Mach = 2.02", rewritten)
        self.assertIn("NumWakeNodes = 8", rewritten)
        rewritten_wake = A0.rewrite_setup_field(text, "NumWakeNodes", "999")
        self.assertIn("NumWakeNodes = 999", rewritten_wake)

    def test_02_missing_field_raises(self):
        with self.assertRaises(A0.A0V2Error):
            A0.rewrite_setup_field("Sref = 4.0\n", "NumWakeNodes", "999")


class RepeatabilityLogicTests(unittest.TestCase):
    def _geometry(self, area=358.25):
        return {
            "area_m2": area, "span_m": 25.604638251691824, "mac_m": 18.489892944055953,
            "root_chord_m": 29.901818514349216, "tip_twist_deg": 0.0,
            "chords_m": [29.901818514349216, 12.208434070312554, 3.892558930560952, 0.9731361054965724],
            "qc_sweep_deg": [67.0, 48.00000000000002, 71.00000000000001],
            "sect_tess_u": [12.0, 12.0, 12.0, 12.0],
        }

    def _case(self, root, case_id, digest, geometry):
        case_dir = Path(root) / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        contract = case_dir / "contract.vspaero"
        contract.write_text("Sref = 358.25\nMach = 2.02\n", encoding="utf-8", newline="\n")
        return {
            "case_dir": str(case_dir),
            "thin_geometry": {"sha256": digest},
            "raw_setup": {"sha256": "raw" + digest},
            "contract_setup": {"name": contract.name, "sha256": "contract"},
            "csf": {"sha256": "csf"},
            "vkey": {"sha256": "vkey-" + case_id},
            "model": {"sha256": "model-" + case_id},
            "model_readback": {
                "readback": geometry,
                "sect_tess_u_readback": [12.0, 12.0, 12.0, 12.0],
            },
        }

    def test_01_pass_when_artifacts_equal(self):
        with tempfile.TemporaryDirectory() as root:
            cases = {
                "B2-03": self._case(root, "B2-03", "d071", self._geometry()),
                "B2-07": self._case(root, "B2-07", "d071", self._geometry()),
            }
            result = A0.repeatability_check(cases)
            self.assertEqual(result["status"], "PASS", result["failed"])
            self.assertEqual(result["failed"], [])
            self.assertTrue(result["judgment_inputs"]["thin_geometry_equal"])
            self.assertTrue(result["judgment_inputs"]["readback_geometry_equal"])
            model_row = [row for row in result["comparisons"] if row["artifact"] == "model_vsp3"][0]
            self.assertFalse(model_row["equal"])
            self.assertIn("不可复现", model_row["note"])

    def test_02_fail_when_thin_geometry_differs(self):
        with tempfile.TemporaryDirectory() as root:
            cases = {
                "B2-03": self._case(root, "B2-03", "d071", self._geometry()),
                "B2-07": self._case(root, "B2-07", "dead", self._geometry()),
            }
            result = A0.repeatability_check(cases)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("thin_geometry_equal", result["failed"])

    def test_03_geometry_equality(self):
        first = self._geometry()
        second = self._geometry()
        self.assertTrue(A0._readback_geometry_equal(first, second))
        second["mac_m"] = second["mac_m"] * (1.0 + 1e-6)
        self.assertFalse(A0._readback_geometry_equal(first, second))


class EvidenceArtifactTests(unittest.TestCase):
    """生成证据产物测试（未运行生成器时跳过）。"""

    def setUp(self):
        self.evidence_path = A0.EVIDENCE_PATH
        if not self.evidence_path.is_file():
            self.skipTest("setup_generation_v2.json 尚未生成")
        self.evidence = json.loads(self.evidence_path.read_text(encoding="utf-8"))

    def test_01_schema_and_status(self):
        evidence = self.evidence
        self.assertEqual(evidence["schema_version"], "d12d005-a0v2-setup-generation-1")
        self.assertEqual(evidence["status"], "A0V2_SETUP_READY_NO_SOLVER")
        self.assertEqual(evidence["solver_processes_started"], 0)
        self.assertEqual(evidence["stop_before_run"], 1)
        summary = evidence["summary"]
        self.assertEqual(summary["case_count"], 8)
        self.assertEqual(summary["readback_pass"], 8)
        self.assertTrue(summary["parity_pass"])
        self.assertTrue(summary["std_parity_pass"])
        self.assertTrue(summary["repeatability_pass"])
        self.assertTrue(summary["negative_controls_pass"])
        self.assertEqual(summary["solver_starts"], 0)

    def test_02_cases_readback_and_external_artifacts(self):
        for case in self.evidence["cases"]:
            self.assertEqual(case["readback_status"], "PASS", case["case_id"])
            self.assertEqual(case["readback_assertions"], 17, case["case_id"])
            self.assertEqual(case["solver_artifacts_present"], [])
            thin = case["thin_geometry"]
            self.assertTrue(thin["outside_git"])
            external = Path(thin["external_path"])
            self.assertTrue(external.is_file(), case["case_id"])
            self.assertFalse((Path(case["case_dir"]) / external.name).exists())
            expected = Path(case["case_dir"]) / "expected_v2.json"
            self.assertTrue(expected.is_file(), case["case_id"])
            payload = json.loads(expected.read_text(encoding="utf-8"))
            self.assertEqual(payload["case_id"], case["case_id"])
            if case["kind"] == "std":
                self.assertEqual(payload["analytic_expectations"]["CL_expected_range"], [0.030, 0.045])
            else:
                self.assertIsNone(payload["analytic_expectations"]["cl_expected_range"])

    def test_03_thin_geometry_sha_and_parity(self):
        lookup = {case["case_id"]: case for case in self.evidence["cases"]}
        self.assertEqual(lookup["B2-02"]["thin_geometry"]["sha256"],
                         A0.ARCHIVED_D12_BASELINE_VSPGEOM_SHA256)
        self.assertEqual(lookup["S6_STD_M2p02_aoa1"]["thin_geometry"]["sha256"],
                         A0.ARCHIVED_STD_VSPGEOM_SHA256)
        self.assertEqual(lookup["B2-03"]["thin_geometry"]["sha256"],
                         lookup["B2-07"]["thin_geometry"]["sha256"])
        self.assertEqual(self.evidence["parity"]["metric_comparison"]["status"], "PASS")
        archive = self.evidence["parity"]["v1_archive_vspgeom"][0]
        self.assertEqual(archive["actual_sha256"], A0.ARCHIVED_D12_BASELINE_VSPGEOM_SHA256)
        self.assertEqual(self.evidence["repeatability"]["status"], "PASS")

    def test_04_negative_controls(self):
        controls = self.evidence["negative_controls"]
        self.assertEqual(len(controls), 1)
        self.assertTrue(controls[0]["all_rejected"])
        results = {item["control"]: item["result"] for item in controls[0]["checks"]}
        self.assertEqual(results, {
            "wrong_sref": "REJECTED",
            "legacy_no_equals": "REJECTED",
            "wake_node_mismatch": "REJECTED",
        })

    def test_05_no_solver_artifacts_and_readme(self):
        self.assertEqual(self.evidence["runtime_s"] > 0, True)
        readme = A0.README_PATH
        self.assertTrue(readme.is_file())
        text = readme.read_text(encoding="utf-8")
        self.assertIn("零求解器", text)
        self.assertIn("solver", text)
        setup_root = A0.SETUP_ROOT
        patterns = ("*.adb", "*.history", "*.polar", "*.lod", "*.groups", "*.fem")
        for pattern in patterns:
            self.assertEqual(list(setup_root.rglob(pattern)), [], pattern)
        for case in self.evidence["cases"]:
            self.assertEqual(case["solver_artifacts_present"], [])
            self.assertTrue(Path(case["case_dir"]).is_dir())


if __name__ == "__main__":
    unittest.main(verbosity=2)
