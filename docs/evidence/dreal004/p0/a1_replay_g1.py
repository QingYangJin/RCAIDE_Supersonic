
"""P0/A1: zero-physical replay of an adaptive alpha search on the 24 G1 cases.

Only rows that the original fixed sweep already evaluated are visible to the
replay; no new VSPAERO point is created and no new label is admitted.  The
output quantifies, per G1 case, whether the target lift is bracketed, whether
an *existing raw row* meets the strict 1e-3 tolerance, and how many real alpha
cases the fixed sweep charged versus how many probes the adaptive search would
consume.  Cases that need refinement beyond the existing grid are reported as
REQUIRES_NEW_ALPHA_ROWS (P1 physical work), never as successes.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.dreal001.geometry.adaptive_alpha import (  # noqa: E402
    AdaptiveAlphaSpec, replay_on_existing_rows, relative_cl_error)
from research.concorde_metaopt.dreal001.geometry.polar_rows import read_polar_rows  # noqa: E402

G1_RUN = Path("D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
OUT_DIR = Path(__file__).resolve().parent


def main() -> int:
    cases_dir = G1_RUN / "cases"
    rows_out = []
    for case_dir in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        case_id = case_dir.name
        spec_path = case_dir / "task_spec.json"
        polar_path = case_dir / ("%s.polar" % case_id)
        if not spec_path.exists() or not polar_path.exists():
            rows_out.append({"case_id": case_id, "verdict": "MISSING_INPUT",
                             "old_fixed_sweep_internal_cases": None,
                             "adaptive_replay_probes": None})
            continue
        task = json.loads(spec_path.read_text(encoding="utf-8"))
        mach = float(task["mach"])
        cl_target = float(task["cl_target"])
        raw_rows = read_polar_rows(polar_path, mach=mach)
        alphas = [r.alpha_deg for r in raw_rows]
        cls = [r.cl for r in raw_rows]
        min_err = min(relative_cl_error(cl, cl_target) for cl in cls)
        best_row = min(zip(alphas, cls), key=lambda pair: relative_cl_error(pair[1], cl_target))
        spec = AdaptiveAlphaSpec(cl_target=cl_target, tol_cl=1e-3,
                                 coarse_alphas=tuple(alphas),
                                 max_solver_cases=len(alphas),
                                 max_refine_steps=8,
                                 min_alpha_deg=min(alphas), max_alpha_deg=max(alphas))
        replay = replay_on_existing_rows(alphas, cls, spec)
        bracket = replay.bracket
        if replay.status == "RAW_POINT_MATCHED":
            verdict = "REPLAY_RAW_HIT_ON_EXISTING_ROW"
        elif bracket is not None:
            verdict = "REQUIRES_NEW_ALPHA_ROWS"
        else:
            verdict = "NO_BRACKET_ON_EXISTING_ROWS"
        rows_out.append({
            "case_id": case_id,
            "task_id": task.get("task_id"),
            "mach": mach,
            "cl_target": cl_target,
            "dynamic_pressure_pa": float(task.get("dynamic_pressure_pa", "nan")),
            "sref_m2": float(task.get("sref_m2", "nan")) if "sref_m2" in task else None,
            "old_fixed_sweep_internal_cases": len(raw_rows),
            "raw_rows": len(raw_rows),
            "alpha_min_deg": min(alphas),
            "alpha_max_deg": max(alphas),
            "best_existing_row_alpha_deg": best_row[0],
            "best_existing_row_cl": best_row[1],
            "min_relative_cl_error_on_existing_rows": min_err,
            "adaptive_replay_probes": replay.solver_cases,
            "adaptive_replay_status": replay.status,
            "bracket_alpha_deg": [bracket[0].alpha_deg, bracket[1].alpha_deg] if bracket else None,
            "estimate_alpha_deg": replay.estimate_alpha_deg,
            "verdict": verdict,
            "physical_solver_starts_used": 0,
        })

    counts = {}
    for row in rows_out:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    hit = [r for r in rows_out if r["verdict"] == "REPLAY_RAW_HIT_ON_EXISTING_ROW"]
    bracketed = [r for r in rows_out if r["verdict"] == "REQUIRES_NEW_ALPHA_ROWS"]
    fixed_cost = sum(r["old_fixed_sweep_internal_cases"] or 0 for r in rows_out)
    probes = sum(r["adaptive_replay_probes"] or 0 for r in rows_out)
    payload = {
        "schema": "dreal004.p0.a1_replay.v1",
        "source_run": str(G1_RUN),
        "case_count": len(rows_out),
        "verdict_counts": counts,
        "existing_raw_row_hits": len(hit),
        "bracketed_but_needs_new_rows": len(bracketed),
        "old_fixed_sweep_internal_cases_total": fixed_cost,
        "adaptive_replay_probes_total": probes,
        "physical_solver_starts_used": 0,
        "labels_created": 0,
        "note": ("Replay only queries alpha rows that the original fixed sweep already "
                 "evaluated. A RAW_HIT here would duplicate a row that G1's own audit "
                 "already had; REQUIRES_NEW_ALPHA_ROWS cases must be solved in P1 and "
                 "are not labels."),
        "cases": rows_out,
    }
    (OUT_DIR / "g1_alpha_replay.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    with (OUT_DIR / "g1_alpha_replay.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        for row in rows_out:
            writer.writerow(row)
    print(json.dumps({k: payload[k] for k in ("case_count", "verdict_counts",
                                             "existing_raw_row_hits",
                                             "bracketed_but_needs_new_rows",
                                             "old_fixed_sweep_internal_cases_total",
                                             "adaptive_replay_probes_total",
                                             "physical_solver_starts_used")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
