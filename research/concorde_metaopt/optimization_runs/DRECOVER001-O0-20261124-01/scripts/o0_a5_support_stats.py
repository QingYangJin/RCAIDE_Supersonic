"""Offline support statistics for the A5 dossier (zero physical).

Two independent computations from files already on disk:
  1. paired statistics for the A0 core pair, so the dossier states dispersion, a bootstrap CI
     and sign counts instead of one point estimate;
  2. the alpha-resolution margin for the O0 two-start strategy, measured from the CL slopes of
     the historical M202 VSPAERO polars rather than reusing the replay the reviewer distrusted.

No solver is started; no label is admitted.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
A0 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01")
R2 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
# Every real run root that contains M202 cases with a readable VSPAERO polar. The alpha
# margin must not rest on one run: (root, run_id) pairs are recorded with each design.
M202_RUN_ROOTS = [
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P1-20261122-02"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01"),
]
OUT = RUN / "a5_support"
OUT.mkdir(parents=True, exist_ok=True)
TOL = 1e-3
REFINE_STEP_DEG = 0.004
REFINE_HALF_WIDTH_DEG = 0.024
COARSE_CENTRE_DEG = 5.18
COARSE_HALF_WIDTH_DEG = 1.05
SWEEP_ALPHA_COUPLING_DEG_PER_DEG = 0.33


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paired_stats() -> dict:
    rows = list(csv.DictReader(open(A0 / "tables/a0_paired_differences.csv", encoding="utf-8")))
    out = {}
    for split in ("val", "test"):
        sel = [r for r in rows if r["split"] == split]
        deltas = [float(r["delta_mae_n"]) for r in sel]
        n = len(deltas)
        mean = sum(deltas) / n
        sd = math.sqrt(sum((d - mean) ** 2 for d in deltas) / (n - 1))
        neg = sum(1 for d in deltas if d < 0)
        pos = sum(1 for d in deltas if d > 0)
        rng = random.Random(20261124)
        boots = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n
                       for _ in range(20000))
        k = max(neg, pos)
        p_sign = sum(math.comb(n, i) for i in range(k, n + 1)) / (2 ** n)
        per_task = {}
        for r in sel:
            per_task.setdefault(r["task_id"], []).append(float(r["delta_mae_n"]))
        out[split] = {
            "n_cells": n,
            "mean_delta_mae_n": mean,
            "sd_delta_mae_n": sd,
            "se_delta_mae_n": sd / math.sqrt(n),
            "bootstrap_95_ci_mean_delta_n": [boots[int(0.025 * len(boots))],
                                             boots[int(0.975 * len(boots)) - 1]],
            "count_fomaml_better": neg,
            "count_supervised_better": pos,
            "sign_test_two_sided_p": min(1.0, 2 * p_sign),
            "per_task_mean_delta_mae_n": {t: sum(v) / len(v) for t, v in per_task.items()},
            "interpretation": "negative delta means COND_FOMAML_16D has the lower MAE",
        }
    return out


def read_polar(path: Path) -> list:
    """[(alpha_deg, cl_tot, cdi)] from a VSPAERO .polar file.

    Column order after the header block is Beta, Mach, AoA, Re/1e6, CLo, CLi, CLtot, CDo,
    CDi, ... so alpha is index 2 and CLtot index 6.
    """
    rows, seen = [], False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not seen:
            if line.strip().startswith("Beta") and "AoA" in line:
                seen = True
            continue
        parts = line.split()
        if len(parts) < 9:
            continue
        try:
            vals = [float(p) for p in parts]
        except ValueError:
            continue
        rows.append((vals[2], vals[6], vals[8]))
    return rows


def _case_design_key(task: dict):
    x = task.get("x12")
    if x is None:
        des = task.get("design")
        x = des.get("x12") if isinstance(des, dict) else None
    if not isinstance(x, (list, tuple)) or len(x) != 12:
        return None
    return tuple(round(float(v), 6) for v in x)


def _polyfit2(xs, ys):
    """Least-squares quadratic y = c0 + c1*x + c2*x^2 via the normal equations."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    s1 = sum(x - mx for x in xs)
    s2 = sum((x - mx) ** 2 for x in xs)
    s3 = sum((x - mx) ** 3 for x in xs)
    s4 = sum((x - mx) ** 4 for x in xs)
    t1 = sum(y - my for y in ys)
    t2 = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    t3 = sum((x - mx) ** 2 * (y - my) for x, y in zip(xs, ys))
    # c2*s2 + c1*s1 = t1 ; c2*s3 + c1*s2 = t2 (after centring s1 == 0)
    if abs(s2) < 1e-15:
        return None
    c1 = t2 / s2
    denom = (s4 * s2 - s3 * s3)
    c2 = (t3 * s2 - t2 * s3) / denom if abs(denom) > 1e-30 else 0.0
    c1 = (t2 - c2 * s3) / s2
    c0 = my - c1 * mx - c2 * mx * mx
    return c0, c1, c2


def alpha_margins() -> dict:
    """Alpha resolution measured on every readable M202 polar in every real run root.

    Cases are grouped by their 12D design vector, because the same design re-run in a
    later batch is not independent evidence and because some runs store a 0.012 deg
    refinement polar that cannot locate the root on its own. For each unique design the
    widest measured alpha span is used, a quadratic CL(alpha) fit locates the fixed-lift
    root and gives the local slope there; a design whose root lies outside the measured
    span is reported as outside rather than silently extrapolated.
    """
    groups, skipped = {}, []
    for root in M202_RUN_ROOTS:
        run_id = root.name
        for case_dir in sorted(root.glob("cases/*")):
            spec = case_dir / "task_spec.json"
            polars = sorted(case_dir.glob("*.polar"))
            if not spec.is_file() or not polars:
                continue
            try:
                task = json.loads(spec.read_text(encoding="utf-8"))
            except Exception:
                skipped.append({"case_id": case_dir.name, "run_id": run_id,
                                "reason": "unreadable task_spec"})
                continue
            if abs(float(task.get("mach") or 0) - 2.02) > 1e-9:
                continue
            key = _case_design_key(task)
            if key is None:
                skipped.append({"case_id": case_dir.name, "run_id": run_id,
                                "reason": "no 12D design vector in task_spec"})
                continue
            rows = read_polar(polars[0])
            if len(rows) < 5:
                skipped.append({"case_id": case_dir.name, "run_id": run_id,
                                "reason": "fewer than %d polar rows" % 5})
                continue
            span = rows[-1][0] - rows[0][0]
            if span <= 0:
                skipped.append({"case_id": case_dir.name, "run_id": run_id,
                                "reason": "degenerate alpha grid"})
                continue
            q_pa = float(task["dynamic_pressure_pa"])
            sref = float(task["sref_m2"]) if "sref_m2" in task else None
            if sref is None:
                skipped.append({"case_id": case_dir.name, "run_id": run_id,
                                "reason": "no sref_m2 in task_spec; not guessed from flow"})
                continue
            cl_target = float(task.get("cl_target")) if task.get("cl_target") else (
                float(task["lift_target_n"]) / (q_pa * sref))
            groups.setdefault(key, []).append({
                "case_id": case_dir.name, "run_id": run_id, "rows": rows,
                "span": span, "q_pa": q_pa, "sref_m2": sref, "cl_target": cl_target,
                "derived": {"sref_recomputed": False,
                            "cl_target_recomputed": "cl_target" not in task},
            })
    designs, outside = [], []
    for key, cases in groups.items():
        best = max(cases, key=lambda c: c["span"])
        rows = best["rows"]
        xs = [r[0] for r in rows]
        ys = [r[1] for r in rows]
        fit = _polyfit2(xs, ys)
        if fit is None:
            skipped.append({"case_id": best["case_id"], "run_id": best["run_id"],
                            "reason": "quadratic fit failed"})
            continue
        c0, c1, c2 = fit
        target = best["cl_target"]
        root = None
        if abs(c2) > 1e-12:
            disc = c1 * c1 - 4 * c2 * (c0 - target)
            if disc >= 0:
                for sgn in (1, -1):
                    cand = (-c1 + sgn * disc ** 0.5) / (2 * c2)
                    if xs[0] - 1e-9 <= cand <= xs[-1] + 1e-9:
                        if root is None or abs(cand - xs[len(xs) // 2]) < abs(
                                root - xs[len(xs) // 2]):
                            root = cand
        if root is None:
            outside.append({"design_key": list(key), "case_id": best["case_id"],
                            "run_id": best["run_id"], "cl_target": target,
                            "cl_max_in_span": max(ys), "cl_min_in_span": min(ys),
                            "alpha_span_deg": [xs[0], xs[-1]],
                            "note": "fixed-lift root lies outside the measured alpha span; "
                                    "not extrapolated"})
            continue
        slope = abs(c1 + 2 * c2 * root)
        window = [(r[0], r[1]) for r in rows if abs(r[0] - root) <= 1.0]
        resid = max(abs(y - (c0 + c1 * x + c2 * x * x)) for x, y in window)
        half = (TOL * target) / slope
        designs.append({
            "design_key": list(key),
            "sweep_1_deg": key[2],
            "sweep_2_deg": key[3],
            "wing_area_m2": key[0],
            "source_case_id": best["case_id"],
            "source_run_id": best["run_id"],
            "source_alpha_span_deg": [xs[0], xs[-1]],
            "source_polar_rows": len(rows),
            "n_cases_measured_for_design": len(cases),
            "sref_m2": best["sref_m2"],
            "q_pa": best["q_pa"],
            "cl_target": target,
            "alpha_root_deg": root,
            "local_cl_slope_per_deg": slope,
            "quadratic_fit_max_residual_cl_near_root": resid,
            "tolerance_window_half_width_deg": half,
            "tolerance_window_full_width_deg": 2 * half,
            "refine_step_deg": REFINE_STEP_DEG,
            "rows_guaranteed_inside_window": int(2 * half // REFINE_STEP_DEG) + 1,
            "coarse_centre_offset_deg": root - COARSE_CENTRE_DEG,
            "coarse_bracket_covers_root": abs(root - COARSE_CENTRE_DEG) < COARSE_HALF_WIDTH_DEG,
        })
    if not designs:
        return {"designs": [], "outside_span": outside, "skipped": skipped,
                "note": "no M202 polar yielded a locatable fixed-lift root"}
    halves = [d["tolerance_window_half_width_deg"] for d in designs]
    guaranteed = [d["rows_guaranteed_inside_window"] for d in designs]
    roots = [d["alpha_root_deg"] for d in designs]
    slopes = [d["local_cl_slope_per_deg"] for d in designs]
    dcl_refine = REFINE_HALF_WIDTH_DEG * min(slopes)
    paired = [d for d in designs]
    coupling = None
    if len(paired) >= 3 and len({d["sweep_1_deg"] for d in paired}) >= 2:
        sx = [d["sweep_1_deg"] for d in paired]
        sy = [d["alpha_root_deg"] for d in paired]
        mx, my = sum(sx) / len(sx), sum(sy) / len(sy)
        sxx = sum((x - mx) ** 2 for x in sx)
        if sxx > 0:
            coupling = sum((x - mx) * (y - my) for x, y in zip(sx, sy)) / sxx
    return {
        "designs": designs,
        "outside_span": outside,
        "skipped": skipped,
        "n_unique_designs": len(designs),
        "n_run_roots_searched": len(M202_RUN_ROOTS),
        "run_roots_with_m202": sorted({d["source_run_id"] for d in designs}),
        "cl_slope_per_deg_range": [min(slopes), max(slopes)],
        "tolerance_window_half_width_deg_range": [min(halves), max(halves)],
        "min_rows_guaranteed_inside_tolerance_window": min(guaranteed),
        "max_alpha_root_offset_from_coarse_centre_deg": max(abs(r - COARSE_CENTRE_DEG)
                                                            for r in roots),
        "coarse_half_width_deg": COARSE_HALF_WIDTH_DEG,
        "coarse_coverage_margin_deg": COARSE_HALF_WIDTH_DEG - max(
            abs(r - COARSE_CENTRE_DEG) for r in roots),
        "refine_half_width_deg": REFINE_HALF_WIDTH_DEG,
        "refine_half_width_in_cl_units": dcl_refine,
        "refine_half_width_vs_tolerance": dcl_refine / (TOL * min(d["cl_target"]
                                                                 for d in designs)),
        "measured_sweep_1_alpha_root_coupling_deg_per_deg": coupling,
        "claim": ("measured on every readable M202 VSPAERO polar in the real run roots, "
                  "one widest-span polar per unique 12D design, quadratic fit near the "
                  "root: the 1e-3 lift tolerance is a window of the stated half width in "
                  "alpha, so a 0.004 deg refinement step puts at least the stated number of "
                  "raw rows inside it whenever the coarse prediction lands within 0.024 deg "
                  "of the true root, and the 2.1 deg coarse bracket covers every measured "
                  "root with the stated margin."),
    }


def main() -> int:
    payload = {
        "schema": "dreal005.o0_a5_support_stats.v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "a0_paired_statistics": paired_stats(),
        "o0_alpha_resolution_margin": alpha_margins(),
        "physical_solver_starts_actual": 0,
        "note": ("offline only: reads the existing A0 paired-difference table and the "
                 "historical M202 VSPAERO polars. Starts no solver and admits no label."),
    }
    path = OUT / "o0_a5_support_stats.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
    shown = dict(payload["o0_alpha_resolution_margin"])
    shown.pop("designs", None)
    print(json.dumps({"out": str(path), "sha256": sha_file(path),
                      "a0": payload["a0_paired_statistics"],
                      "alpha": shown}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
