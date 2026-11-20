import math
import unittest
from pathlib import Path
from unittest.mock import patch

from research.concorde_metaopt.dreal001.geometry import solver_runner
from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC


def task_spec_payload(mach=1.6, q=12851.40843975621, sref=358.25,
                      lift=1333704.4, rho=0.1153178340089936,
                      vinf=472.1088294874393):
    return {
        "schema": "dreal001.r2_task_spec.v1",
        "task_id": "fixture-m160",
        "mach": mach,
        "dynamic_pressure_pa": q,
        "sref_m2": sref,
        "lift_target_n": lift,
        "lift_tolerance_rel": 0.001,
        "cref_m": 18.489893,
        "bref_m": 25.604638,
        "flow_conditions": {"rho_kg_m3": rho, "vinf_m_s": vinf},
    }


def reader(task_spec=None, case_inputs=None):
    def read(path):
        if path.name == "task_spec.json":
            return task_spec
        if path.name == "case_inputs.json":
            return case_inputs
        return None
    return read


PROCESS = {"exit_code": 0, "timed_out": False, "wall_s": 0.0,
           "stdout_sha256": "", "stderr_sha256": ""}


def row(alpha, cl, cdi):
    return {"Mach": 1.6, "AoA": alpha, "CLtot": cl, "CDi": cdi,
            "CDtot": cdi + 0.01, "CDo": 0.01, "_invalid_tokens": {}}


def preflight(case_flow):
    return {
        "plan": {
            "run_id": "fixture", "case_id": "fixture-case", "task_id": "fixture-m160",
            "purpose": "fixture", "solver": {}, "command": {},
            "geometry": {"sref_m2": 358.25},
        },
        "case_flow": case_flow,
        "exe_sha256": "0" * 64, "argv": [], "cwd": ".", "geometry_sha256": "1" * 64,
    }


class CaseFlowTests(unittest.TestCase):
    def test_prefers_case_task_spec(self):
        with patch.object(solver_runner, "_read_optional_json", reader(
                task_spec=task_spec_payload(),
                case_inputs={"sweep_input_readback": {"inputs_double": {
                    "MachStart": 2.02, "Sref": 999.0,
                    "Vinf": 596.0373972278921, "Rho": 0.1153178340089936}}})):
            flow = solver_runner._case_flow_conditions(Path("/fixture"), "fixture")
        self.assertEqual(flow["source"], "CASE_TASK_SPEC")
        self.assertAlmostEqual(flow["mach"], 1.6)
        self.assertAlmostEqual(flow["q_pa"], 12851.40843975621)
        self.assertAlmostEqual(flow["sref_m2"], 358.25)
        self.assertAlmostEqual(flow["lift_target_n"], 1333704.4)
        self.assertAlmostEqual(flow["lift_tolerance_rel"], 0.001)
        self.assertAlmostEqual(flow["cl_target"],
                               1333704.4 / (12851.40843975621 * 358.25))

    def test_falls_back_to_sweep_readback(self):
        rho = 0.1153178340089936
        vinf = math.sqrt(2.0 * 16265.063806566453 / rho)
        with patch.object(solver_runner, "_read_optional_json", reader(
                case_inputs={"sweep_input_readback": {"inputs_double": {
                    "MachStart": 1.8, "Sref": 358.25, "Vinf": vinf, "Rho": rho,
                    "Cref": 18.489893, "Bref": 25.604638}}})):
            flow = solver_runner._case_flow_conditions(Path("/fixture"), "fixture")
        self.assertEqual(flow["source"], "CASE_INPUTS_SWEEP_READBACK")
        self.assertAlmostEqual(flow["mach"], 1.8)
        self.assertAlmostEqual(flow["q_pa"], 16265.063806566453)
        self.assertAlmostEqual(flow["sref_m2"], 358.25)
        self.assertAlmostEqual(flow["lift_target_n"], TASK_SPEC.l_ref_n)

    def test_rejects_inconsistent_q(self):
        with patch.object(solver_runner, "_read_optional_json",
                          reader(task_spec=task_spec_payload(q=999.0))):
            with self.assertRaisesRegex(solver_runner.PreflightError,
                                        "case flow conditions disagree"):
                solver_runner._case_flow_conditions(Path("/fixture"), "fixture")


class BuildEvaluationTests(unittest.TestCase):
    def test_uses_case_flow_not_global(self):
        cl_target = 1333704.4 / (12851.40843975621 * 358.25)
        rows = [row(0.0, 0.10, 0.0100), row(5.0, 0.25, 0.0110),
                row(10.0, 0.40, 0.0120)]
        flow = {"mach": 1.6, "q_pa": 12851.40843975621, "sref_m2": 358.25,
                "lift_target_n": 1333704.4, "lift_tolerance_rel": 0.001,
                "rho_kg_m3": 0.1153178340089936, "vinf_m_s": 472.1088294874393,
                "cref_m": 18.489893, "bref_m": 25.604638,
                "cl_target": cl_target, "source": "CASE_TASK_SPEC"}
        evaluation = solver_runner.build_evaluation(
            preflight(flow), PROCESS, {}, {"unique_case_rows": rows},
            "fixture-attempt", "SOLVED")
        self.assertAlmostEqual(evaluation["reference"]["q_pa"], 12851.40843975621)
        self.assertAlmostEqual(evaluation["reference"]["mach"], 1.6)
        self.assertAlmostEqual(evaluation["reference"]["l_ref_n"], 1333704.4)
        self.assertEqual(evaluation["reference"]["case_flow_source"], "CASE_TASK_SPEC")
        self.assertAlmostEqual(evaluation["objective"]["sref_m2"], 358.25)
        self.assertAlmostEqual(evaluation["objective"]["q_pa"], 12851.40843975621)
        self.assertEqual(evaluation["lift_match_status"], "LIFT_MATCHED_BY_INTERPOLATION")
        self.assertAlmostEqual(
            evaluation["objective"]["value"],
            12851.40843975621 * 358.25 * evaluation["objective"]["cdi_at_matched_lift"])
        self.assertAlmostEqual(evaluation["lift_tolerance_rel"], 0.001)
        self.assertEqual(evaluation["physical_solver_starts"], 1)

    def test_marks_lift_within_case_tolerance(self):
        cl_target = 1333704.4 / (12851.40843975621 * 358.25)
        rows = [row(0.0, 0.0, 0.0100), row(6.0, cl_target, 0.0115),
                row(10.0, 0.40, 0.0120)]
        flow = {"mach": 1.6, "q_pa": 12851.40843975621, "sref_m2": 358.25,
                "lift_target_n": 1333704.4, "lift_tolerance_rel": 0.001,
                "source": "CASE_TASK_SPEC"}
        evaluation = solver_runner.build_evaluation(
            preflight(flow), PROCESS, {}, {"unique_case_rows": rows},
            "fixture-attempt", "SOLVED")
        matched = [item for item in evaluation["rows"]
                   if abs(item["CLtot"] - cl_target) < 1e-12]
        self.assertEqual(len(matched), 1)
        self.assertTrue(matched[0]["lift_match_initial_tol"])
        self.assertAlmostEqual(matched[0]["lift_rel_error_vs_Lref"], 0.0, places=12)


if __name__ == "__main__":
    unittest.main()
