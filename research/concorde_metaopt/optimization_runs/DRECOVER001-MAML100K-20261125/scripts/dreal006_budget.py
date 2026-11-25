"""Dreal006 evaluation budget: the five independent counters and the 100k split.

The unit is one charged evaluation attempt of one design under one task, one
backend and one lattice - including attempts that fail.  It is not an SGD step,
a network prediction, an angle-of-attack iteration or a repeated certificate.
"""
from __future__ import annotations

import argparse
import json
import pathlib

TOTAL = 100000

# name: (charged attempts, what the money buys, counting rule)
STAGES = {
    "S0_repair_and_calibration": (2000, "backend repair, zero-physics tests, lattice calibration, BO smoke", "every calibration evaluation of a real deck"),
    "S1_meta_training": (8192, "24 train tasks x 256 designs", "charged attempts; the 24x256 grid is the full charge"),
    "S2_meta_test": (1536, "12 unseen tasks x 128 designs", "charged attempts on the held-out tasks"),
    "S3_model_selection": (3072, "4 val tasks x 3 methods x 4 repeats x 64 designs", "charged attempts of the frozen comparison"),
    "S4_online_bo": (69120, "12 new test tasks x 10 paired repeats x 3 arms x 192 evaluations", "the dominant spend; 16 init + up to 176 BO candidates per arm-task-repeat"),
    "S5_baseline_optimisers": (9216, "DE/PSO: 2 backends x 4 tasks x 3 repeats x 3 sampling methods x 128 evaluations", "charged attempts of the classical baselines"),
    "S6_final_report": (2000, "final geometry recheck, statistics and cost report", "charged attempts of the closing audit"),
    "R_reserve": (4864, "retry and rework reserve", "spent only against a recorded failure, never pre-assigned"),
}

INNER_VLM_CAP_PER_DESIGN = 16
GLOBAL_INNER_VLM_GUARD = 1600000
SOLVES_PER_EVALUATION_20X10 = 5


def build() -> dict:
    stages = {
        name: {
            "charged_attempts": charged,
            "share_of_total": charged / TOTAL,
            "buys": buys,
            "counting_rule": rule,
        }
        for name, (charged, buys, rule) in STAGES.items()
    }
    total = sum(v["charged_attempts"] for v in stages.values())
    if total != TOTAL:
        raise SystemExit("budget does not sum to %d: %d" % (TOTAL, total))
    if any(v["charged_attempts"] <= 0 for v in stages.values()):
        raise SystemExit("every stage must be charged a positive budget")
    payload = {
        "schema": "dreal006.evaluation_budget.v1",
        "unit": "one charged evaluation attempt of one design under one task, one backend and one lattice, including attempts that fail",
        "not_a_unit": ["SGD update", "network forward pass", "angle-of-attack iteration", "repeated certificate", "cache hit"],
        "total": TOTAL,
        "stages": stages,
        "counters": {
            "evaluation_attempts_charged": "every call that reaches the evaluator, VALID or not",
            "fresh_evaluator_attempts": "those that actually built a vehicle and ran a solve",
            "unique_task_design_labels": "distinct (task, design) pairs with a VALID label",
            "vlm_inner_solves_actual": "inner VLM solves performed, reported separately and never counted as budget units",
            "cache_hits": "repeat requests served from the in-run cache; reported, never charged",
        },
        "per_design_inner_solve_cap": INNER_VLM_CAP_PER_DESIGN,
        "global_inner_solve_guard": GLOBAL_INNER_VLM_GUARD,
        "nominal_solves_per_evaluation_at_20x10": SOLVES_PER_EVALUATION_20X10,
        "per_task_initial_timeout_s": 120,
        "automatic_retries": 0,
        "budget_assertion": "sum(stages) == total == %d" % TOTAL,
    }
    assert sum(v["charged_attempts"] for v in payload["stages"].values()) == payload["total"]
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parents[1] / "metadata" / "evaluation_budget.json"))
    args = parser.parse_args(argv)
    payload = build()
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, stage in payload["stages"].items():
        print("%-28s %7d  %5.1f%%" % (name, stage["charged_attempts"], 100.0 * stage["share_of_total"]))
    print("total %d" % payload["total"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
