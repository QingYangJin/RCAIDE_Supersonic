import hashlib, json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from research.concorde_metaopt.dreal001.geometry import solver_runner

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases")
OUT = Path(__file__).resolve().parent / "a1_per_case_flow_verification.json"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

cases = []
newly_matched = []
still_outside = []
for case in sorted(p for p in RUN.iterdir() if p.is_dir()):
    result_path = case / "case_result.json"
    if not result_path.exists():
        cases.append({"case_id": case.name, "status": "NO_CASE_RESULT_INTERRUPTED",
                      "physical_solver_starts": 0})
        continue
    result = json.loads(result_path.read_text(encoding="utf-8"))
    flow = solver_runner._case_flow_conditions(case, case.name)
    record = {"plan": {"run_id": result.get("attempt", {}).get("run_id"),
                       "case_id": case.name,
                       "geometry": {"sref_m2": flow["sref_m2"]}},
              "case_flow": flow,
              "exe_sha256": (result.get("solver") or {}).get("executable_sha256", ""),
              "argv": (result.get("solver") or {}).get("argv", []),
              "cwd": str(case)}
    ev = solver_runner.build_evaluation(record, result.get("process") or {},
                                        result.get("outputs") or {}, result.get("polar"),
                                        result.get("attempt", {}).get("attempt_id", case.name),
                                        result.get("attempt", {}).get("status", "SOLVED"))
    before = (result.get("evaluation") or {}).get("lift_match_status")
    after = ev.get("lift_match_status")
    if before != "LIFT_MATCHED_BY_INTERPOLATION" and after == "LIFT_MATCHED_BY_INTERPOLATION":
        newly_matched.append(case.name)
    if after == "CL_TARGET_OUTSIDE_POLAR":
        still_outside.append(case.name)
    cases.append({
        "case_id": case.name,
        "task_id": result.get("attempt", {}).get("task_id"),
        "status": "EVALUATED_ZERO_PHYSICAL",
        "case_flow": flow,
        "lift_match_status_before_fix": before,
        "lift_match_status_after_fix": after,
        "objective_value_after_fix": (ev.get("objective") or {}).get("value"),
        "reference_q_pa_after_fix": (ev.get("reference") or {}).get("q_pa"),
        "reference_mach_after_fix": (ev.get("reference") or {}).get("mach"),
        "physical_solver_starts": 0,
    })

payload = {
    "schema": "dreal003.a1_case_flow_verification.v1",
    "run_id": "DRECOVER001-R2-20261120-01",
    "source_files": {
        "solver_runner.py": sha(ROOT / "research/concorde_metaopt/dreal001/geometry/solver_runner.py"),
        "test_recovery_solver_runner.py": sha(ROOT / "research/concorde_metaopt/tests/test_recovery_solver_runner.py"),
    },
    "case_count": len(cases),
    "evaluated_count": sum(1 for c in cases if c["status"] == "EVALUATED_ZERO_PHYSICAL"),
    "newly_matched_after_fix": newly_matched,
    "still_outside_polar_after_fix": still_outside,
    "physical_solver_starts_added": 0,
    "note": "Read-only recomputation from existing polar files; historical case_result and raw bytes are not modified.",
    "cases": cases,
}
OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
print("cases", len(cases))
print("evaluated", payload["evaluated_count"])
print("newly_matched", len(newly_matched), newly_matched)
print("still_outside", len(still_outside))
