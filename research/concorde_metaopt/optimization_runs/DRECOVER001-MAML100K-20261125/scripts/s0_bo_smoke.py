"""S0 ordinary BO smoke: a real ask -> evaluate -> tell trajectory (contract 3.2).

The point is not to optimise anything; it is to prove the loop closes on the
real VLM deck: an evaluation is told back, the surrogate refits, and the next
ask differs from the design just evaluated.  A failing evaluation is told as a
failure and must not fabricate an objective.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from maml_opt.bayesian import ConstrainedBayesianOptimizer

from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend

CONFIG = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
META = pathlib.Path(__file__).resolve().parents[1] / "metadata"
BASE_LIFT_N = 1344778.5


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, default=24)
    parser.add_argument("--initial", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--out", default=str(META / "bo_smoke.json"))
    args = parser.parse_args(argv)

    names = json.loads((META / "active_subspace.json").read_text(encoding="utf-8"))["active_names"]
    backend = SupersonicVLMBackend(REPO_ROOT, CONFIG, mach=2.02, altitude_m=18288.0,
                                   lift_target_mode="force", lift_target_n=BASE_LIFT_N,
                                   lattice=(20, 10), design_names=names,
                                   task_fingerprint="s0-bo-smoke")
    lower, upper = [], []
    for name in names:
        variable = backend.space.variables[backend.space.names.index(name)]
        lower.append(float(variable.lower))
        upper.append(float(variable.upper))
    lower, upper = np.array(lower), np.array(upper)

    def to_design(unit):
        unit = np.clip(np.asarray(unit, dtype=float), 0.0, 1.0)
        return {name: float(lower[i] + unit[i] * (upper[i] - lower[i])) for i, name in enumerate(names)}

    seed = np.random.default_rng(args.seed)
    optimizer = ConstrainedBayesianOptimizer(np.zeros(len(names)), np.ones(len(names)),
                                             seed=args.seed, candidate_count=256)
    started = time.time()
    trace = []
    charged = fresh = failed = cached = 0
    changed_flags = []

    for step in range(args.budget):
        if step < args.initial:
            unit = seed.random(len(names))
            source = "initial_space_filling"
        else:
            selection = optimizer.ask()
            unit = np.asarray(selection["design_vector"], dtype=float)
            source = "bo_ask:" + str(selection["selection_method"])
        design = to_design(unit)
        record = backend.evaluate(design)
        charged += 1
        cached += int(bool(record.get("cached")))
        fresh += int(not record.get("cached"))
        ok = record.get("status") == "VALID" and record.get("objective") is not None
        failed += int(not ok)

        # One charged analysis call per fresh evaluation; a cache hit charges none.
        charged_calls = 0 if record.get("cached") else 1
        if ok:
            optimizer.tell(unit, {
                "objective": float(record["objective"]),
                "valid": True,
                "constraints_g_le_zero": {},
                "analysis_calls": charged_calls,
            })
        else:
            # A failed evaluation is told as a failure: it must not invent a value.
            optimizer.tell(unit, {"valid": False, "status": record.get("status"),
                                  "analysis_calls": charged_calls,
                                  "error": "backend returned %s" % record.get("status")})

        next_selection = optimizer.ask() if step + 1 < args.budget else None
        next_unit = None if next_selection is None else np.asarray(next_selection["design_vector"], dtype=float)
        changed = None if next_unit is None else bool(np.linalg.norm(next_unit - unit) > 1e-6)
        if changed is not None:
            changed_flags.append(changed)
        trace.append({
            "step": step,
            "source": source,
            "unit": [float(v) for v in unit],
            "design": design,
            "status": record.get("status"),
            "objective": record.get("objective"),
            "cl_target": record.get("cl_target"),
            "cl_actual": record.get("cl_actual"),
            "lift_residual": record.get("lift_residual"),
            "alpha_deg": record.get("alpha_deg"),
            "cached": bool(record.get("cached")),
            "next_ask_differs": changed,
        })
        print("step %2d %-32s %-10s obj=%s wall=%.2fs next_differs=%s"
              % (step, source, record.get("status"), record.get("objective"),
                 record.get("wall_seconds") or 0.0, changed))

    objectives = [row["objective"] for row in trace if row["objective"] is not None]
    payload = {
        "schema": "dreal006.bo_smoke.v1",
        "purpose": "prove the ask/evaluate/tell loop closes on the real deck before any 100k spend",
        "budget": args.budget,
        "initial": args.initial,
        "seed": args.seed,
        "lattice": [20, 10],
        "active_names": names,
        "counters": {
            "evaluation_attempts_charged": charged,
            "fresh_evaluator_attempts": fresh,
            "cache_hits": cached,
            "failed_attempts": failed,
            "valid_labels": len(objectives),
        },
        "best_objective": min(objectives) if objectives else None,
        "worst_objective": max(objectives) if objectives else None,
        "feedback_changed_the_next_ask": bool(changed_flags) and all(changed_flags),
        "distinct_asks_checked": len(changed_flags),
        "failure_rows_have_no_objective": all(row["objective"] is None for row in trace if row["status"] != "VALID"),
        "solver_solves": backend.solve_count,
        "wall_seconds": round(time.time() - started, 2),
        "trace": trace,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("counters", "best_objective", "worst_objective",
                                              "feedback_changed_the_next_ask", "failure_rows_have_no_objective",
                                              "solver_solves", "wall_seconds")}, indent=2))
    if not payload["failure_rows_have_no_objective"]:
        raise SystemExit("a failed evaluation carried an objective")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
