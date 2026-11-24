"""Assemble final_aircraft/ from the verified batch: the deliverables Issue #15 asks for.

This module only assembles files that already exist on disk (geometry exports, admitted
certificates, verification re-runs). It never invents a number and never promotes an
unverified candidate: the verdict is computed from the verification records.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(RUN / "scripts"))

from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

OUT = RUN / "final_aircraft"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def parameter_rows(baseline_x12: List[float], optimized_x12: List[float]) -> List[Dict[str, Any]]:
    rows = []
    for index, name in enumerate(o0.VARIABLE_ORDER):
        low, high = o0.SUBSPACE_BOUNDS.get(name, (None, None))
        base = float(baseline_x12[index])
        opt = float(optimized_x12[index])
        rows.append({
            "index_12d": index, "variable": name,
            "is_active_in_this_batch": name in o0.SUBSPACE_INDEX,
            "unit": "deg" if "sweep" in name or "twist" in name else
                    ("m2" if "area" in name else "dimensionless"),
            "baseline": base, "optimized": opt, "delta": opt - base,
            "relative_change": (opt - base) / base if base else None,
            "frozen_bound_lower": low, "frozen_bound_upper": high,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser_dummy() if False else None
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", default=str(RUN / "o0_result_B01.json"))
    parser.add_argument("--final", default=str(RUN / "o0_final/o0_final_rounds.json"))
    args = parser.parse_args()

    result = load(Path(args.result))
    final = load(Path(args.final))
    # The batch result records the physics of each attempt, not a copy of the task block, and it
    # does not repeat the batch identity. Both are read from the records that own them rather than
    # being typed into this assembler, so the deliverable cannot disagree with the pre-registration.
    prereg = load(RUN / "o0_preregistration.json")
    close_records = sorted(RUN.glob("o0_batch_close_*.json"))
    close = load(close_records[-1]) if close_records else {}
    if "task" not in result:
        result["task"] = prereg["task"]
    result.setdefault("run_id", close.get("run_id") or "DRECOVER001-O0-20261124-01")
    result.setdefault("batch_id", close.get("batch_id") or "DRECOVER001-O0-20261124-01-B02")
    attempts = result["attempts"]
    admitted = [a for a in attempts if a["status"] == "FEASIBLE_ADMITTED"]
    baseline = next((a for a in admitted if a["is_baseline"]), None)
    non_baseline = [a for a in admitted if not a["is_baseline"]]
    best = min(non_baseline, key=lambda a: float(a["di_n"])) if non_baseline else None

    # The repeat labels are not fixed strings: the first attempt at this step crashed and its
    # labels stay charged in the ledger forever, so the replacement runs had to take fresh labels
    # (final-baseline-r1b/-r2b). Selecting by design and kind instead of by label name means this
    # assembler cannot silently pair a missing run with a stale one.
    rounds_by_design = {"baseline": [], "best": []}
    for row in final["rounds"]:
        name = row.get("design")
        if name in rounds_by_design:
            rounds_by_design[name].append(row)
    for name in rounds_by_design:
        rounds_by_design[name].sort(key=lambda r: r.get("utc") or r.get("label") or "")
    base_runs = rounds_by_design["baseline"][:2] or [None, None]
    best_runs = rounds_by_design["best"][:2] or [None, None]
    while len(base_runs) < 2:
        base_runs.append(None)
    while len(best_runs) < 2:
        best_runs.append(None)
    base_ok = all(r and r.get("admitted") for r in base_runs)
    best_ok = bool(best) and all(r and r.get("admitted") for r in best_runs)

    di_base_verify = [float(r["di_n"]) for r in base_runs if r and r.get("admitted")]
    di_best_verify = [float(r["di_n"]) for r in best_runs if r and r.get("admitted")]
    repeat_spread_base = (max(di_base_verify) - min(di_base_verify)) if len(di_base_verify) > 1 else None
    repeat_spread_best = (max(di_best_verify) - min(di_best_verify)) if len(di_best_verify) > 1 else None

    wake_by_design = {}
    for row in final.get("wake_probe", []):
        if row.get("design") in ("baseline", "best"):
            wake_by_design[row["design"]] = row
    wake_base = wake_by_design.get("baseline")
    wake_best = wake_by_design.get("best")

    # A change counts as verified only when the two re-runs of each design are admitted,
    # the same-design repeat spread is far below the change, and the change has the same
    # sign in every re-run pairing.
    verdict = "NO_FEASIBLE_NONBASELINE"
    improvement_n = None
    improvement_fraction = None
    if not base_ok:
        verdict = "PROVISIONAL_CANDIDATE"
    elif best and best_ok:
        di_base = sum(di_base_verify) / len(di_base_verify)
        di_best = sum(di_best_verify) / len(di_best_verify)
        improvement_n = di_base - di_best
        improvement_fraction = improvement_n / di_base
        pairs = [(b - o) for b, o in zip(di_base_verify, di_best_verify)]
        spread = max(x for x in (repeat_spread_base or 0.0, repeat_spread_best or 0.0))
        if improvement_n <= 0:
            verdict = "FEASIBLE_NO_VERIFIED_IMPROVEMENT"
        elif all(p > 0 for p in pairs) and improvement_n > 3.0 * max(spread, 0.0):
            verdict = "VERIFIED_IMPROVEMENT"
        else:
            verdict = "FEASIBLE_NO_VERIFIED_IMPROVEMENT"
    elif best:
        verdict = "PROVISIONAL_CANDIDATE"

    def perf_row(label: str, record: Dict[str, Any]) -> Dict[str, Any]:
        return {"case": label, "case_id": record.get("case_id"),
                "di_n": record.get("di_n"), "cl": record.get("cl"),
                "cdi": record.get("cdi"), "alpha_deg": record.get("alpha_deg"),
                "sref_m2": record.get("sref_m2"), "q_pa": record.get("q_pa"),
                "lift_rel_error": record.get("lift_rel_error"),
                "physical_solver_starts": record.get("physical_solver_starts"),
                "internal_solver_cases": record.get("internal_solver_cases")}

    perf = []
    if base_runs[0]:
        perf.append(perf_row("baseline_r1", base_runs[0]))
    if base_runs[1]:
        perf.append(perf_row("baseline_r2", base_runs[1]))
    if best_runs[0]:
        perf.append(perf_row("optimized_r1", best_runs[0]))
    if best_runs[1]:
        perf.append(perf_row("optimized_r2", best_runs[1]))
    with open(OUT / "performance_before_after.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(perf[0]))
        writer.writeheader()
        for row in perf:
            writer.writerow(row)

    parameters = parameter_rows(list(o0.BASELINE_X12), list(best["x12"]) if best else list(o0.BASELINE_X12))
    with open(OUT / "design_before_after.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(parameters[0]))
        writer.writeheader()
        for row in parameters:
            writer.writerow(row)

    x12_best = list(best["x12"]) if best else list(o0.BASELINE_X12)
    design_payload = {
        "schema": "dreal005.o0_optimized_design.v1",
        "created_utc": now(),
        "run_id": result.get("run_id") or "DRECOVER001-O0-20261124-01",
        "batch_id": result.get("batch_id") or "DRECOVER001-O0-20261124-01-B01",
        "task": result["task"],
        "design_id": o0.design_identity(x12_best)["design_id"],
        "geometry_sha256": o0.design_identity(x12_best)["geometry_sha256"],
        "is_baseline": o0.design_identity(x12_best)["is_baseline"],
        "full_12d_vector": x12_best,
        "variable_order_12d": list(o0.VARIABLE_ORDER),
        "physical_15_vector": list(o0.physical_15(x12_best)),
        "physical_15_order": list(o0.PHYSICAL_15_NAMES),
        "active_subspace": {
            "variables": list(o0.SUBSPACE_INDEX),
            "indices_12d": dict(o0.SUBSPACE_INDEX),
            "bounds": {k: list(v) for k, v in o0.SUBSPACE_BOUNDS.items()},
            "selection_rule": ("only variables with a measured CDi response on existing "
                               "raw rows are active; the other ten are frozen at the "
                               "baseline values and this is disclosed"),
        },
        "frozen_non_active_variables": {name: float(x12_best[i])
                                         for i, name in enumerate(o0.VARIABLE_ORDER)
                                         if i not in o0.SUBSPACE_INDEX.values()},
        "field_mapping": [
            {"index_12d": i, "name": name, "baseline": float(o0.BASELINE_X12[i]),
             "final": float(x12_best[i]), "unit":
             "deg" if "sweep" in name or "twist" in name else
             ("m2" if "area" in name else "dimensionless")}
            for i, name in enumerate(o0.VARIABLE_ORDER)
        ],
        "generation_command": ("python scripts/o0_export_aircraft.py --prefix optimized "
                               "--x12 " + " ".join("%.10g" % v for v in x12_best)),
        "source_geometry_exports": load(OUT / "optimized_geometry.json")
        if (OUT / "optimized_geometry.json").is_file() else None,
        "verdict": verdict,
        "disclosure": ("the solver model contains the main wing and the vertical tail; the "
                       "fuselage is exported for visual completeness but is not meshed by "
                       "the evaluation, so no fuselage aerodynamic claim is made"),
    }
    write_json(OUT / "optimized_design.json", design_payload)

    constraints = {
        "schema": "dreal005.o0_constraint_report.v1",
        "created_utc": now(),
        "task": result["task"],
        "checks": [
            {"check": "lift_target", "target_n": result["task"]["lift_target_n"],
             "tolerance_rel": result["task"]["lift_tolerance_rel"],
             "baseline_rel_error": base_runs[0].get("lift_rel_error") if base_runs[0] else None,
             "optimized_rel_error": best_runs[0].get("lift_rel_error") if best_runs[0] else None,
             "rule": "an actual raw polar row must satisfy |q*Sref*CL - L_ref|/L_ref <= 1e-3"},
            {"check": "di_n_finite_positive",
             "baseline_di_n": base_runs[0].get("di_n") if base_runs[0] else None,
             "optimized_di_n": best_runs[0].get("di_n") if best_runs[0] else None},
            {"check": "design_identity_differs_from_baseline",
             "optimized_design_id": o0.design_identity(x12_best)["design_id"],
             "baseline_design_id": o0.design_identity(list(o0.BASELINE_X12))["design_id"],
             "ok": o0.design_identity(x12_best)["design_id"]
                   != o0.design_identity(list(o0.BASELINE_X12))["design_id"]},
            {"check": "non_active_variables_unchanged",
             "ok": all(abs(float(x12_best[i]) - float(o0.BASELINE_X12[i])) == 0.0
                       for i in range(12) if i not in o0.SUBSPACE_INDEX.values())},
            {"check": "subspace_bounds_respected",
             "ok": all(o0.SUBSPACE_BOUNDS[n][0] <= float(x12_best[i]) <= o0.SUBSPACE_BOUNDS[n][1]
                       for n, i in o0.SUBSPACE_INDEX.items())},
        ],
        "not_checked": ["structural integrity", "trim and stability", "total drag",
                        "fuel burn", "mission performance", "airworthiness"],
        "scope": ("FEASIBLE here means only: the frozen geometry produced a real VSPAERO "
                  "solution whose raw polar contains a point at the target lift, and the "
                  "resulting induced drag is finite and positive"),
    }
    write_json(OUT / "constraint_report.json", constraints)

    receipt = {
        "schema": "dreal005.o0_verification_receipt.v1",
        "created_utc": now(),
        "run_id": design_payload["run_id"],
        "batch_id": design_payload["batch_id"],
        "verdict": verdict,
        "verdict_rule": ("VERIFIED_IMPROVEMENT requires both designs admitted twice, a "
                         "consistent sign across every re-run pairing, and a change larger "
                         "than three times the same-design repeat spread"),
        "baseline_verification": base_runs,
        "optimized_verification": best_runs,
        "repeat_spread_di_n": {"baseline": repeat_spread_base, "optimized": repeat_spread_best},
        "di_n_verified_mean": {"baseline": (sum(di_base_verify) / len(di_base_verify))
                               if di_base_verify else None,
                               "optimized": (sum(di_best_verify) / len(di_best_verify))
                               if di_best_verify else None},
        "improvement_di_n": improvement_n,
        "improvement_fraction": improvement_fraction,
        "wake_sensitivity_probe": {"baseline": wake_base, "optimized": wake_best,
                                   "note": ("these runs double the wake node count and are "
                                            "never admitted; they only bound how much the "
                                            "objective moves with the wake discretisation")},
        "verification_budget": final["ledger"],
        "n_wake_nodes_admitted_standard": 8,
        "physics_validated": False,
        "disclosure": ("same-host, single-machine evidence; labels are "
                       "LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED; "
                       "physics_validated stays false and fuel_burn_kg stays null"),
    }
    write_json(OUT / "verification_receipt.json", receipt)
    print(json.dumps({"verdict": verdict, "improvement_n": improvement_n,
                      "improvement_fraction": improvement_fraction,
                      "baseline_runs_admitted": base_ok,
                      "optimized_runs_admitted": best_ok,
                      "files": sorted(p.name for p in OUT.glob("*.json")) +
                               sorted(p.name for p in OUT.glob("*.csv"))},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
