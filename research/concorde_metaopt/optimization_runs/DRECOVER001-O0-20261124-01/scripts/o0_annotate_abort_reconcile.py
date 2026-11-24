"""Annotate the B01 abort record so its caps block cannot be misread as a remainder.

The abort record was written against the stored ceilings (36 starts, 240 internal cases).
The O0 design cap binds first: 12 designs x 2 starts = 24 spendable starts, so 35 is not a
number this authorization can ever spend. Rather than edit a historical witness, append the
reconciliation and leave every original field exactly as it was recorded.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
ABORT = RUN / "o0_batch_abort_B01.json"
PRE = RUN / "o0_preregistration.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    caps = pre["caps"]
    per_design_starts = caps["max_starts_per_design"]
    per_design_internal = caps["max_internal_per_design"]
    designs = caps["max_design_attempts"]
    spendable_starts = min(caps["max_solver_starts"], designs * per_design_starts)
    spendable_internal = min(caps["max_internal_cases"], designs * per_design_internal)
    record = json.loads(ABORT.read_text(encoding="utf-8"))
    spent_starts = int(record["charged_starts_actual"])
    spent_internal = int(record["internal_solver_cases_actual"])
    block = {
        "annotated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "why": ("the caps_after_this_abort block above subtracts the spend from the STORED "
                "ceilings (36 starts, 240 internal cases). Those ceilings are not what a GO "
                "authorizes: the design cap allows at most %d designs x %d starts = %d starts "
                "and %d x %d = %d internal cases, so %d starts can never be spent and 35 was "
                "never a remainder. The spendable remainder is derived here and is the only "
                "number a reader should carry forward.") % (designs, per_design_starts,
                                                             spendable_starts, designs,
                                                             per_design_internal,
                                                             spendable_internal,
                                                             caps["max_solver_starts"]),
        "stored_ceilings": {"max_solver_starts": caps["max_solver_starts"],
                            "max_internal_cases": caps["max_internal_cases"],
                            "max_design_attempts": caps["max_design_attempts"],
                            "max_starts_per_design": per_design_starts,
                            "max_internal_per_design": per_design_internal},
        "spendable_under_the_design_cap": {"solver_starts": spendable_starts,
                                           "internal_cases": spendable_internal,
                                           "derivation": ("min(stored ceiling, designs x "
                                                          "per-design cap)")},
        "spent_by_this_abort": {"solver_starts": spent_starts,
                                "internal_cases": spent_internal},
        "spendable_remainder": {"solver_starts": spendable_starts - spent_starts,
                                "internal_cases": spendable_internal - spent_internal,
                                "designs": designs - int(record["design_evaluations_actual"])},
        "original_fields_unchanged": True,
    }
    record.setdefault("post_abort_annotations", {})["caps_reconciliation"] = block
    record["post_abort_annotations"]["annotation_order"] = [
        "relocation", "lock", "caps_reconciliation"]
    data = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    ABORT.write_bytes(data)
    print(json.dumps({"abort_record_sha256": hashlib.sha256(data).hexdigest(),
                      "spendable_remainder": block["spendable_remainder"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())