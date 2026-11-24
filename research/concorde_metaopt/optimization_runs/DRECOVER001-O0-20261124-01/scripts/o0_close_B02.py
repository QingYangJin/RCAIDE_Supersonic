"""Close batch B02 of its own accord, and say why its exit looks like a crash.

B02 spent its whole spendable remainder: 11 further designs (12 including the one B01
aborted), 22 starts, 220 internal cases, 11 admitted labels, no failures. It then ended with
ProtocolError "run would exceed 12 design attempts" because the adaptive loop compared the
number of designs this process had recorded against the authorization-wide design cap without
subtracting the design already spent by B01. The ledger refusing the 13th design was correct;
the loop asking for it was the defect. That is recorded here instead of being left to look like
a scientific failure: no cap was exceeded, and the batch completed what the authorization allowed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    result = json.loads((RUN / "o0_result_B02.json").read_text(encoding="utf-8"))
    crash = json.loads((RUN / "o0_batch_crash_B02.json").read_text(encoding="utf-8"))
    accounting = json.loads((RUN / "o0_batch_accounting_B02.json").read_text(encoding="utf-8"))
    abort = json.loads((RUN / "o0_batch_abort_B01.json").read_text(encoding="utf-8"))
    attempts = result["attempts"]
    admitted = [a for a in attempts if a["status"] == "FEASIBLE_ADMITTED"]
    baseline = next(a for a in attempts if a["is_baseline"])
    non_base = [a for a in admitted if not a["is_baseline"]]
    best = min(non_base, key=lambda a: float(a["di_n"]))
    designs_total = int(abort["design_evaluations_actual"]) + len(attempts)
    starts_total = int(abort["charged_starts_actual"]) + sum(int(a["starts"]) for a in attempts)
    internal_total = (int(abort["internal_solver_cases_actual"])
                      + sum(int(a["internal"]) for a in attempts))
    caps = accounting["caps"]
    spendable_starts = caps["max_design_attempts"] * caps["max_starts_per_design"]
    spendable_internal = caps["max_design_attempts"] * caps["max_internal_per_design"]
    record = {
        "schema": "dreal005.o0_batch_close.v1",
        "run_id": "DRECOVER001-O0-20261124-01",
        "batch_id": result.get("protocol_id") and "DRECOVER001-O0-20261124-01-B02",
        "authorization_id": "AUTH-DREAL005-O0-20261124-01",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outcome": "COMPLETED_BY_EXHAUSTING_THE_AUTHORIZATION_DESIGN_CAP",
        "why_it_looks_like_a_crash": crash["exception_text"],
        "was_any_cap_exceeded": False,
        "defect": {"where": "run_bo_loop adaptive loop bound",
                   "what": ("the loop compares len(records) to the authorization-wide design cap "
                            "without subtracting the design attempts already carried forward from "
                            "B01, so after the last permitted design it asked the ledger for one "
                            "more and the ledger correctly refused"),
                   "who_caught_it": ("the ledger, not the loop: the charge path fails closed, which "
                                     "is why the batch stopped with an accounting error instead of "
                                     "spending a start it was not entitled to")},
        "batch_spend": {"designs": len(attempts),
                        "solver_starts": sum(int(a["starts"]) for a in attempts),
                        "internal_cases": sum(int(a["internal"]) for a in attempts),
                        "admitted_labels": len(admitted),
                        "failed_or_null": len(attempts) - len(admitted)},
        "authorization_spend": {"designs": designs_total, "solver_starts": starts_total,
                               "internal_cases": internal_total},
        "authorization_caps": {"designs": caps["max_design_attempts"],
                               "spendable_solver_starts": spendable_starts,
                               "spendable_internal_cases": spendable_internal},
        "design_cap_fully_used": designs_total == caps["max_design_attempts"],
        "baseline": {"design_index": baseline["design_index"],
                     "design_id": baseline["design_id"],
                     "di_n": baseline["di_n"], "alpha_deg": baseline["alpha_deg"],
                     "lift_rel_error": baseline["lift_rel_error"]},
        "best_non_baseline": {"design_index": best["design_index"],
                              "design_id": best["design_id"], "di_n": best["di_n"],
                              "alpha_deg": best["alpha_deg"],
                              "lift_rel_error": best["lift_rel_error"],
                              "sweep_1": best["x12"][2], "sweep_2": best["x12"][3]},
        "improvement_n": float(baseline["di_n"]) - float(best["di_n"]),
        "improvement_fraction_of_baseline": (float(baseline["di_n"]) - float(best["di_n"]))
                                            / float(baseline["di_n"]),
        "feedback_dependent": bool(result.get("feedback_dependent")),
        "artifact_sha256": {
            "o0_result_B02.json": sha256(RUN / "o0_result_B02.json"),
            "o0_batch_accounting_B02.json": sha256(RUN / "o0_batch_accounting_B02.json"),
            "o0_batch_crash_B02.json": sha256(RUN / "o0_batch_crash_B02.json"),
            "o0_go_record.json": sha256(RUN / "o0_go_record.json"),
        },
        "resource_summary": accounting["resource_summary"],
        "physical_solver_starts_actual_batch": accounting["physical_solver_starts_actual"],
        "internal_solver_cases_actual_batch": accounting["internal_solver_cases_actual"],
        "physics_validated": False,
        "physical_interpretation": accounting["physical_interpretation"],
    }
    out = RUN / "o0_batch_close_B02.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"out": str(out), "sha256": sha256(out),
                      "designs": designs_total, "starts": starts_total,
                      "internal": internal_total, "improvement_n": record["improvement_n"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())