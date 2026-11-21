
"""A2 baseline endpoints from the completed G1 limited-budget run (zero physical).

This does not run a sampler.  It replays the *recorded* G1 design sequence
(24 charged starts, 23 completed, 8 admitted labels) through the endpoint
analyzer so that P1 has a fixed, reproducible baseline for first-feasible
cost, hit rate and best-feasible-so-far.  No label is created or re-graded.
"""
from __future__ import annotations

import csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from research.concorde_metaopt.dreal001.meta.endpoint_analysis import (  # noqa: E402
    DesignEvaluation, summarize_run)

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
OUT = Path(__file__).resolve().parent
INTERNAL_PER_CASE = 17


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def start_order() -> list[str]:
    rows = read_rows(RUN / "attempt_ledger.csv")
    order = []
    for row in rows:
        if row["event"] == "start":
            order.append(row["case_id"])
    return order


def main() -> int:
    order = start_order()
    admitted = {row["case_id"]: row for row in read_rows(RUN / "admitted_labels.csv")}
    failed = {row["case_id"]: row for row in read_rows(RUN / "failed_or_null.csv")}
    records = []
    per_task: dict[str, list] = {}
    missing = []
    for case_id in order:
        if case_id in admitted:
            row = admitted[case_id]
            rec = DesignEvaluation(task_id=row["task_id"], design_id=row["design"],
                                   feasible=True, di_n=float(row["di_n"]),
                                   internal_solver_cases=int(row["internal_cases"] or INTERNAL_PER_CASE),
                                   design_starts=1)
        elif case_id in failed:
            row = failed[case_id]
            rec = DesignEvaluation(task_id=row["task_id"], design_id=row["design"],
                                   feasible=False,
                                   internal_solver_cases=int(row["internal_cases"] or 0),
                                   design_starts=1,
                                   failure_reason=row.get("failure_kind") or "NULL")
        else:
            missing.append(case_id)
            continue
        records.append(rec)
        per_task.setdefault(rec.task_id, []).append(rec)

    budgets = (4, 8, 16, 24)
    result = {
        "schema": "dreal004.a2_g1_baseline_endpoints.v1",
        "source_run": str(RUN),
        "source_tables": ["attempt_ledger.csv", "admitted_labels.csv", "failed_or_null.csv"],
        "physical_solver_starts_used": 0,
        "labels_created": 0,
        "charged_starts_in_ledger": len(order),
        "records_replayed": len(records),
        "unmatched_cases": missing,
        "global": summarize_run(records, budgets=budgets),
        "per_task": {task: summarize_run(recs, budgets=budgets)
                     for task, recs in sorted(per_task.items())},
        "admitted_labels": len(admitted),
        "note": ("G1 recorded 24 charged starts and 8 admitted labels.  One start "
                 "(m202-d05) has no solver result and contributes 0 internal cases.  "
                 "All 24 charged starts are replayed.  This is a historical baseline "
                 "only; it is not a new sampler run and creates no labels."),
    }
    total_starts = sum(r.design_starts for r in records)
    total_cases = sum(r.internal_solver_cases for r in records)
    result["consistency_with_batch_accounting"] = {
        "records_replayed": len(records),
        "batch_accounting_starts": 24,
        "total_internal_solver_cases_replayed": total_cases,
        "batch_accounting_internal_solver_cases": 391,
        "matches": len(records) == 24 and total_cases == 391,
    }
    result["cost_per_admitted_label"] = {
        "design_starts_per_label": total_starts / len(admitted),
        "internal_solver_cases_per_label": total_cases / len(admitted),
        "admitted_labels": len(admitted),
    }
    (OUT / "a2_g1_baseline_endpoints.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"records": len(records), "labels": len(admitted),
                      "first_feasible": result["global"]["first_feasible"],
                      "hit_rate": result["global"]["hit_rate"],
                      "cost_per_label": result["cost_per_admitted_label"]},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
