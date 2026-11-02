
"""Run the 4 authorised RCAIDE_LF starts (LFV-04, LFV-05, E2E-00, E2E-01).

Each case is one single-cruise RCAIDE Mission evaluation through the project
SingleCruiseBackend (frozen 136 t mass contract, 12D lifting-surface design
space).  Budget: one RCAIDE_LF start per case, recorded in the D-12D-002
approval ledger before the solver is invoked.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("D:/RCAIDE")
EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
OUT = EXT / "lf_mission"
LEDGER = EXT / "lead" / "ledger.py"
PY = r"D:/RCAIDE/envs/RCAIDE/python.exe"
CONFIG = REPO / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"


def ledger(cmd_args):
    cmd = [PY, "-E", "-s", "-B", str(LEDGER)] + cmd_args
    p = subprocess.run(cmd, capture_output=True, text=True)
    print("LEDGER:", (p.stdout or "").strip(), (p.stderr or "").strip()[:300], flush=True)
    return p.returncode == 0


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    os.chdir(str(REPO))
    sys.path.insert(0, str(REPO))
    from research.concorde_metaopt.aircraft.design_space import load_design_space
    from research.concorde_metaopt.tasks.task_spec import load_task_spec
    from research.concorde_metaopt.evaluation.low_fidelity import SingleCruiseBackend

    space = load_design_space(CONFIG)
    task = load_task_spec()
    print("design_set", space.design_set, "dim", space.design_dim, "names", space.names, flush=True)
    print("task", task.task_id, task.fingerprint()[:16], "mach", task.cruise_mach,
          "alt", task.cruise_altitude_m, "range", task.cruise_distance_m, flush=True)
    base = dict(space.baseline_dict())
    print("baseline", base, flush=True)

    if not ledger(["note", "policy", "RCAIDE_LF phase beginning: 4 authorised single-cruise Mission starts (LFV-04 V01+1%, LFV-05 V02+2deg, E2E-00 baseline instrumented chain, E2E-01 W10+2deg instrumented chain); no external body correction injected because WAVE_AREA_RULE is NOT_VALIDATED"]):
        raise SystemExit("ledger note failed")

    cases = {
        "LFV-04": dict(base, vertical_tail_area=round(base["vertical_tail_area"] * 1.01, 6)),
        "LFV-05": dict(base, vertical_tail_sweep_delta=2.0),
        "E2E-00": dict(base),
        "E2E-01": dict(base, tip_twist=2.0),
    }
    desc = {
        "LFV-04": "V01 vertical_tail_area +1% (34.2491 m2) zero-sideslip sensitivity",
        "LFV-05": "V02 vertical_tail_sweep_delta +2 deg zero-sideslip sensitivity",
        "E2E-00": "12D baseline through instrumented single-cruise chain (drag ledger, no unvalidated correction)",
        "E2E-01": "W10 tip_twist +2 deg through instrumented single-cruise chain (drag ledger)",
    }

    backend = SingleCruiseBackend(design_space=space, task=task, repo_root=REPO, verify_tutorial_hash=True)
    results = {}
    for case_id, design in cases.items():
        print("=" * 70, flush=True)
        print("CASE", case_id, desc[case_id], flush=True)
        if not ledger(["start", "RCAIDE_LF", case_id, desc[case_id],
                       "research.concorde_metaopt.evaluation.low_fidelity.SingleCruiseBackend.evaluate (RCAIDE 1.5.0 tutorial VLM single cruise)"]):
            print("REFUSED", case_id, flush=True)
            results[case_id] = {"status": "BUDGET_REFUSED"}
            continue
        t0 = time.time()
        try:
            record = backend.evaluate(design, purpose="fullchain-" + case_id)
            rc = 0
        except Exception as exc:  # keep the ledger closed even on crash
            record = {"status": "EXCEPTION", "exception": "%s: %s" % (type(exc).__name__, exc)}
            rc = 1
        wall = time.time() - t0
        target = OUT / (case_id + ".json")
        target.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        results[case_id] = record
        ok = ledger(["finish", case_id, "SOLVED" if rc == 0 else "FAILED", "%.3f" % wall, str(rc),
                     "--files", "%s:%d" % (target.name, target.stat().st_size),
                     "--note", "record status %s" % record.get("status")])
        print("CASE", case_id, "status", record.get("status"), "objective", record.get("objective"),
              "wall %.1f s" % wall, "ledger_closed", ok, flush=True)

    (OUT / "reconcile_input.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
