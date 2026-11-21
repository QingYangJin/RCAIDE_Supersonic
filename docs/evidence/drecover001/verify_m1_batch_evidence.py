"""Reproduce the software M1 batch receipt from its own bytes.

No solver, no admission: this only proves the archived fixture rehearsal is
internally consistent and still matches the checked-out control-path module.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.dreal001.meta import m1_batch as batch

EVIDENCE = Path(__file__).resolve().parent
RECEIPT = EVIDENCE / "m1_batch_software_rehearsal_receipt.json"
RESULT = EVIDENCE / "m1_batch_software_result.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    batch.verify_result(result)

    checks = {}

    def check(name, condition, detail=None):
        checks[name] = {"status": "PASS" if condition else "FAIL"}
        if detail is not None:
            checks[name]["detail"] = detail

    check("schema", receipt["schema"] == "drecover001.m1_batch_software_rehearsal.v1")
    check("scope", receipt["scope"] == batch.SCOPE and result["scope"] == batch.SCOPE)
    check("authorization_kind",
          receipt["authorization_kind"] == "STRUCTURAL_SOFTWARE_FIXTURE_NOT_A_REAL_GO")
    check("a5_not_performed", receipt["a5_independent_review"] == "NOT_PERFORMED")
    check("no_real_go", receipt["physical_go"] == "NOT_ISSUED" and receipt["real_admission"] is False)
    check("solver_not_used", receipt["solver_executable_used"] is None)
    check("result_sha_matches_receipt",
          receipt["result_sha256"] == result["result_sha256"])
    check("plan_sha_matches_result",
          receipt["plan_sha256"] == result["plan_sha256"])
    check("authorization_sha_matches_result",
          receipt["authorization_sha256"] == result["authorization_sha256"])
    check("result_file_bytes", receipt["result_file"]["sha256"] == file_sha256(RESULT),
          receipt["result_file"]["sha256"])
    check("code_still_current", receipt["code_sha256"] == batch.module_source_sha256(),
          batch.module_source_sha256())
    check("evidence_grade", result["evidence_grade"] == "SOFTWARE_CONTROL_PATH_ONLY")

    accounting = result["accounting"]
    check("physical_zero", accounting["physical_solver_starts_actual"] == 0)
    check("simulated_matches_plan", accounting["simulated_solver_starts_actual"] == result["item_count"])
    check("internal_equals_simulated_times_cases",
          accounting["internal_solver_cases_actual"]
          == accounting["simulated_solver_starts_actual"] * batch.INTERNAL_CASES_PER_START)
    check("charged_matches_plan", accounting["charged_planned_reserved"] == result["item_count"])
    check("no_failed_no_retry",
          accounting["failed_evaluations"] == 0 and accounting["retries_used"] == 0)
    check("status_complete", result["status"] == "COMPLETE" and result["item_count"] == 18)
    check("receipt_accounting_copied", receipt["accounting"] == accounting)
    check("all_ok_objects", all(
        item["objective"] is not None and item["status"] == "ok" for item in result["items"]))

    failed = [name for name, entry in checks.items() if entry["status"] == "FAIL"]
    verification = {
        "schema": "drecover001.m1_batch_software_verification.v1",
        "scope": batch.SCOPE,
        "receipt": RECEIPT.name,
        "result": RESULT.name,
        "checks": checks,
        "check_count": len(checks),
        "failures": failed,
        "status": "M1_BATCH_EVIDENCE_INTERNALLY_CONSISTENT" if not failed else "FAILED",
        "disclosure": ("Software fixture evidence only. No A5 review, no Lead GO, no real "
                       "admission, no solver start, no physical budget."),
    }
    target = EVIDENCE / "m1_batch_software_verification.json"
    target.write_text(json.dumps(verification, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps({"status": verification["status"], "check_count": len(checks),
                      "failures": failed}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
