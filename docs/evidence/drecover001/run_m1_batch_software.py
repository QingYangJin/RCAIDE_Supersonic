"""Offline M1 batch control-path rehearsal with the real six-task family.

Zero physical starts. The evaluator is a deterministic software fixture, and the
authorisation object is a STRUCTURAL FIXTURE: no A5 review exists and no Lead GO
was issued. This receipt exists to prove the runner refuses unauthorised physics,
honours finite batch controls, and keeps the six accounting bases separate.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.dreal001.m1 import task_evaluator as te
from research.concorde_metaopt.dreal001.meta import m1_batch as batch
from research.concorde_metaopt.dreal001.optimizers.ledger import SolverStartLedger

EVIDENCE = Path(__file__).resolve().parent


class FixtureEvaluator:
    """Deterministic software response; never reaches a solver."""

    def __call__(self, item):
        digest = hashlib.sha256((item.task_id + "|" + item.design_hash).encode("utf-8")).hexdigest()
        di_n = 6500.0 + float(int(digest[:6], 16) % 300)
        return batch.EvaluationSample(
            status="ok",
            solver_started=True,
            internal_solver_cases=batch.INTERNAL_CASES_PER_START,
            di_n=di_n,
            cl=0.17,
            cdi=0.0012,
            raw_path="SOFTWARE_FIXTURE/no_solver_raw.json",
            raw_sha256=digest,
            detail="SOFTWARE_FIXTURE_RESPONSE",
            wall_s=0.02,
        )


def main() -> int:
    authorization = batch.BatchAuthorization(
        run_id="DRECOVER001-M1-SOFTWARE-20261118T000000Z",
        batch_id="FIXTURE-BATCH-0001",
        authorization_id="FIXTURE-AUTH-0001",
        approval_id="FIXTURE-APPROVAL-0001",
        a5_review_id="A5-FIXTURE-STRUCTURAL-0001",
        a5_verdict="R2_FIXED_LOOP_GATE_APPROVED_WITH_DISCLOSURE",
        lead_go_id="LEAD-FIXTURE-STRUCTURAL-0001",
        physical_go=True,
        issued_utc="2026-11-18T00:00:00Z",
        max_starts=24,
        solver_timeout_s=600,
        retries=1,
        parallel=1,
        max_batch_wall_s=7200,
    )
    items = []
    for task in te.TASK_DEFINITIONS:
        for design in te.REFERENCE_DESIGNS:
            items.append(batch.WorkItem(
                task_id=task.task_id,
                design_id=design.design_id,
                design_hash=design.design_hash,
                design_x12=tuple(float(value) for value in getattr(
                    design, "x12", te.BASELINE_X12)),
                task_fingerprint=te.task_fingerprint(task),
            ))
    plan = batch.build_plan(authorization, items)
    ledger = SolverStartLedger(
        run_dir=None,
        batch_id=authorization.batch_id,
        run_id=authorization.run_id,
        max_starts=authorization.max_starts,
        backend="SOFTWARE_FIXTURE",
        task_id="M1_SOFTWARE_FIXTURE",
        solver_config_sha256=hashlib.sha256(batch.SCOPE.encode("utf-8")).hexdigest(),
    )
    result = batch.run_batch(plan, evaluator=FixtureEvaluator(), ledger=ledger)
    result_path = EVIDENCE / "m1_batch_software_result.json"
    result_info = batch.write_result(result, result_path)
    receipt = {
        "schema": "drecover001.m1_batch_software_rehearsal.v1",
        "scope": batch.SCOPE,
        "run_id": authorization.run_id,
        "batch_id": authorization.batch_id,
        "authorization_kind": "STRUCTURAL_SOFTWARE_FIXTURE_NOT_A_REAL_GO",
        "a5_independent_review": "NOT_PERFORMED",
        "physical_go": "NOT_ISSUED",
        "real_admission": False,
        "admitted_real_labels": 0,
        "solver_executable_used": None,
        "task_family": [
            {"task_id": task.task_id, "split": task.split, "mach": task.mach,
             "cl_target": task.cl_target,
             "task_fingerprint": te.task_fingerprint(task)}
            for task in te.TASK_DEFINITIONS
        ],
        "design_family": [
            {"design_id": design.design_id, "design_hash": design.design_hash}
            for design in te.REFERENCE_DESIGNS
        ],
        "controls": result["controls"],
        "authorization_sha256": authorization.sha256,
        "plan_sha256": plan.plan_sha256,
        "accounting": result["accounting"],
        "result_status": result["status"],
        "result_sha256": result["result_sha256"],
        "result_file": {"path": result_path.name, **result_info},
        "code_sha256": batch.module_source_sha256(),
        "note": ("Control-path rehearsal only. The evaluator is a software fixture, so "
                 "these numbers are not solver evidence and grant no budget."),
    }
    target = EVIDENCE / "m1_batch_software_rehearsal_receipt.json"
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + chr(10),
                      encoding="utf-8")
    print(json.dumps({"receipt": str(target), "status": result["status"],
                      "accounting": result["accounting"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
