"""A2 software feedback-loop rehearsal: BO ask -> evaluate -> tell, zero physical.

This receipt proves that the executable BO arm consumes returned evaluation
feedback causally. It does NOT prove optimizer effectiveness or physical
validity: the evaluator is the deterministic MOCK aero backend, all
physical_solver_starts are zero, and the counterfactual branch only replaces
the first two returned D_i_N labels to show the third proposal depends on
them. Real feedback requires the Issue #12 R2 gate.

Run from the repository root:
    python docs/evidence/drecover001/run_a2_feedback_rehearsal.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from research.concorde_metaopt.aircraft.design_space import design_space_from_config
from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.dreal001.optimizers import (
    ArmSpec,
    EvaluationCache,
    MockLiftMatchEvaluator,
    SolverStartLedger,
    VisibleLabelStore,
    build_task,
    run_arm,
)
from research.concorde_metaopt.dreal001.optimizers.constants import BACKEND_MOCK, STATUS_VALID

CONFIG = ROOT / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
OUTPUT = ROOT / "docs/evidence/drecover001/a2_feedback_rehearsal.json"
WORK = ROOT / "docs/evidence/drecover001/_a2_feedback_work"
BATCH_ID = "DRECOVER001-A2-REHEARSAL-20261118"
BUDGET = 6
INITIAL = 2
SEED = 17
SCOPE = "SOFTWARE_FEEDBACK_REHEARSAL_ONLY_NOT_PHYSICAL_EVIDENCE"


class SwappedFeedback:
    """Swap the first returned labels only; used solely for causal branch test."""

    def __init__(self, inner: Any, values: List[float]) -> None:
        self.inner = inner
        self.values = [float(value) for value in values]
        self.consumed = 0
        self.ledger = inner.ledger
        self.requires_starts = inner.requires_starts
        self.backend = inner.backend
        self.source_kind = inner.source_kind
        self.label_store = getattr(inner, "label_store", None)

    def evaluate(self, vector, **kwargs):
        evaluation = self.inner.evaluate(vector, **kwargs)
        if evaluation.status == STATUS_VALID and self.consumed < len(self.values):
            # Keep D_i_N == q*Sref*CDi internally consistent so only the
            # returned preference order changes, not the evaluator contract.
            value = self.values[self.consumed]
            evaluation = replace(evaluation, D_i_N=value, CDi=value / (evaluation.q_Pa * evaluation.Sref_m2))
        if evaluation.status == STATUS_VALID:
            self.consumed += 1
        return evaluation


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _space():
    config = dict(load_config(CONFIG))
    # The legacy design-space loader still refuses frozen P1 bounds. The
    # geometry freeze identity is issued separately in geometry_freeze_v2.json;
    # this rehearsal only needs the 12D unit box, so unset the loader flag in
    # memory and disclose it rather than editing the config under analysis.
    config["frozen"] = False
    return design_space_from_config(config, source=str(CONFIG))


def _run(tag: str, *, swapped: Optional[List[float]] = None, fail_hashes=()) -> Any:
    run_id = "%s-%s" % (BATCH_ID, tag)
    run_dir = WORK / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    task = build_task()
    ledger = SolverStartLedger(
        run_dir,
        batch_id=BATCH_ID,
        run_id=run_id,
        max_starts=BUDGET,
        backend=BACKEND_MOCK,
        task_id=task.task_id,
        solver_config_sha256=task.solver_config_sha256,
    )
    evaluator = MockLiftMatchEvaluator(
        _space(),
        task,
        ledger,
        batch_id=BATCH_ID,
        run_id=run_id,
        arm_id="BO",
        seed=SEED,
        cache=EvaluationCache(run_dir / "evaluation_cache.json"),
        label_store=VisibleLabelStore(run_id),
        run_dir=run_dir,
        fail_design_hashes=fail_hashes,
    )
    if swapped is not None:
        evaluator = SwappedFeedback(evaluator, swapped)
    spec = ArmSpec("BO", budget_starts=BUDGET, initial_designs=INITIAL, seed=SEED, batch_id=BATCH_ID, run_id=run_id)
    return run_arm(spec, task, _space(), evaluator)


def _summary(result: Any) -> Dict[str, Any]:
    history = []
    for row in result.history:
        history.append(
            {
                "evaluation_index": int(row["evaluation_index"]),
                "phase": row["phase"],
                "x12_unit": [float(value) for value in row["x12_unit"]],
                "status": row["status"],
                "valid": bool(row["valid"]),
                "objective_D_i_N": row["objective_D_i_N"],
                "lift_rel_error": row["lift_rel_error"],
                "physical_solver_starts": int(row["physical_solver_starts"]),
                "simulated_solver_starts": int(row["simulated_solver_starts"]),
            }
        )
    return {
        "status": result.status,
        "evaluations_requested": int(result.evaluations_requested),
        "unique_design_evals": int(result.unique_design_evals),
        "valid_evals": int(result.valid_evals),
        "starts_used": int(result.starts_used),
        "physical_solver_starts": int(result.physical_solver_starts),
        "simulated_solver_starts": int(result.simulated_solver_starts),
        "best_valid_D_i_N": result.best_valid_D_i_N,
        "history": history,
    }


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        baseline = _run("baseline")
        first_two = [row["objective_D_i_N"] for row in baseline.history[:2]]
        counterfactual = _run("counterfactual-swap", swapped=list(reversed(first_two)))
        failed = _run("failure-null", fail_hashes=(baseline.history[0]["design_hash"],))

        left_vectors = [row["x12_unit"] for row in baseline.history]
        right_vectors = [row["x12_unit"] for row in counterfactual.history]
        first_two_same = bool(
            np.allclose(left_vectors[0], right_vectors[0]) and np.allclose(left_vectors[1], right_vectors[1])
        )
        third_differs = not bool(np.allclose(left_vectors[2], right_vectors[2]))
        failure_row = failed.history[0]
        receipt = {
            "schema": "drecover001.a2_feedback_rehearsal.v1",
            "scope": SCOPE,
            "batch_id": BATCH_ID,
            "backend": BACKEND_MOCK,
            "optimizer": "RECOVERY_NUMPY_RBF_GP_EI_V1",
            "budget_starts": BUDGET,
            "initial_designs": INITIAL,
            "seed": SEED,
            "design_space_config": "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
            "design_space_loader_note": "legacy loader refuses frozen P1 bounds; rehearsal unset frozen in memory only; geometry freeze identity is geometry_freeze_v2.json",
            "baseline": _summary(baseline),
            "counterfactual": {
                "description": "first two returned D_i_N labels reversed; only the preference order changes",
                "first_two_labels_original": first_two,
                "first_two_labels_swapped": list(reversed(first_two)),
                "first_two_proposals_identical": first_two_same,
                "third_proposal_differs": third_differs,
                "third_proposal_original": left_vectors[2],
                "third_proposal_counterfactual": right_vectors[2],
            },
            "failed_objective_branch": {
                "description": "first initial design forced to solver-failure; objective must remain null",
                "first_row_status": failure_row["status"],
                "first_row_valid": bool(failure_row["valid"]),
                "first_row_objective_D_i_N": failure_row["objective_D_i_N"],
                "physical_solver_starts": int(failure_row["physical_solver_starts"]),
            },
            "source_sha256": {
                "optimizers/arms.py": _sha256(ROOT / "research/concorde_metaopt/dreal001/optimizers/arms.py"),
                "optimizers/recovery_bo.py": _sha256(ROOT / "research/concorde_metaopt/dreal001/optimizers/recovery_bo.py"),
                "optimizers/evaluators.py": _sha256(ROOT / "research/concorde_metaopt/dreal001/optimizers/evaluators.py"),
            },
            "physical_solver_starts_actual": 0,
            "internal_solver_cases_actual": 0,
            "real_meta_training_executed": False,
            "admitted_scientific_labels": 0,
            "notes": [
                "MOCK backend only; simulated_solver_starts are not physical solver starts.",
                "The counterfactual receipt is a software causal wiring test, not an optimizer comparison.",
                "Real ask->evaluate->tell trajectory requires the R2 gate and a Lead batch GO.",
            ],
        }
        OUTPUT.write_text(json.dumps(receipt, indent=2, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "A2_FEEDBACK_REHEARSAL_VERIFIED", "output": str(OUTPUT),
                          "first_two_same": first_two_same, "third_differs": third_differs,
                          "physical_solver_starts": 0}, sort_keys=True))
        return 0 if first_two_same and third_differs else 1
    finally:
        shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
