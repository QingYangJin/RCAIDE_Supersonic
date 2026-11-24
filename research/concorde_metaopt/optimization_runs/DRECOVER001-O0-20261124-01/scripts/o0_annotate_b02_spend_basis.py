"""Annotate the B02 crash record with the basis of each of its counters.

The crash record's ledger summary is not internally uniform: solver_starts_actual and
internal_solver_cases_actual are AUTHORIZATION-CUMULATIVE (23 and 227, which already include the
1 start and 7 internal cases B01 spent), while design_attempts is BATCH-LOCAL (11, the designs this
process recorded). A reader who summed these with the B01 abort record would bill 24 starts and
234 internal cases for an authorization that spent 23 and 227.

This script records that mixed basis in the record itself, together with the independent
recomputation, rather than leaving the next reader to discover it by arithmetic.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
sys.path.insert(0, str(RUN / "scripts"))

import o0_spend  # noqa: E402


def main() -> int:
    path = RUN / "o0_batch_crash_B02.json"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    row = json.loads(path.read_text(encoding="utf-8"))
    spend = o0_spend.authorization_spend(RUN)
    ledger = row.get("ledger") or {}
    row.setdefault("post_abort_annotations", {})["spend_basis"] = {
        "annotated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "why": ("the ledger summary this record quotes does not use one basis: starts and internal "
                "cases are authorization-cumulative, design_attempts is batch-local"),
        "fields": {
            "ledger.design_attempts": {
                "value": ledger.get("design_attempts"), "basis": "BATCH_LOCAL",
                "explanation": ("designs recorded by this process; the 1 design B01 spent is NOT "
                                "included, so the authorization total is this plus "
                                "ledger.carried_forward.design_attempts")},
            "ledger.solver_starts_actual": {
                "value": ledger.get("solver_starts_actual"), "basis": "AUTHORIZATION_CUMULATIVE",
                "explanation": ("already includes the 1 start B01 spent; adding the abort "
                                "record's start to this number double-counts it")},
            "ledger.internal_solver_cases_actual": {
                "value": ledger.get("internal_solver_cases_actual"),
                "basis": "AUTHORIZATION_CUMULATIVE",
                "explanation": ("already includes the 7 internal cases B01 spent; adding the "
                                "abort record's internal cases double-counts them")},
        },
        "independent_recomputation": {
            "rule": spend["rule"],
            "design_attempts": spend["design_attempts"],
            "solver_starts": spend["solver_starts"],
            "internal_solver_cases": spend["internal_solver_cases"],
            "basis_record": spend["basis_record"],
            "added_batch_local": spend["added_batch_local"],
            "code": "scripts/o0_spend.py",
        },
        "record_sha256_before_this_annotation": before,
    }
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    print(json.dumps({"record": str(path), "sha256_before": before,
                      "sha256_after": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "authorization_spend": {k: spend[k] for k in
                                              ("design_attempts", "solver_starts",
                                               "internal_solver_cases")}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
