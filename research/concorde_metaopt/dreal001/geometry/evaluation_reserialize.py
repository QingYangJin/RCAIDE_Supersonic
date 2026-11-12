"""F-ENV-02: one-row-per-evaluation re-serialization (NO solver start).

The immutable case_result.json (written by the one approved real start) holds the raw
polar and the stored evaluation.  This module rebuilds evaluations.jsonl so that every
line is ONE evaluation (one unique flow condition: Mach/AoA/Beta) with scalar alpha,
per the governance v2 section 6 evaluation schema, plus a run-level
evaluation_summary.json for the matched-lift objective.  It never touches the solver:
physical_solver_starts on each line is 0 because the single attempt is counted once in
solver_attempts.jsonl and in batch_summary.json; the row carries the attributed attempt id.

Row policy: .polar carries duplicated blocks (VSPAERO 7.2.2 merges a command-line -fs list
with the .vspaero lists).  One evaluation row is emitted per unique (Mach, AoA, Beta),
using the LAST occurrence of that case (polar_parser.unique_case_rows), and the duplicate
multiplicity is recorded per row instead of being silently averaged.

Usage:
  python -m research.concorde_metaopt.dreal001.geometry.evaluation_reserialize --run-dir <runs/RUN>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import design_identity, polar_parser, solver_runner
from .task_spec import TASK_SPEC

RESERIALIZE_SCHEMA = "dreal001.evaluation_reserialization.v1"
EVALUATION_SCHEMA = solver_runner.EVALUATION_SCHEMA
SUMMARY_FILENAME = "evaluation_summary.json"
LABELS_VISIBLE = ["alpha_deg", "mach", "beta_deg", "CLtot", "CDi", "CDtot", "CMz",
                  "L_N", "D_i_N", "lift_rel_error", "status"]
LABELS_HIDDEN = ["fuel_burn_kg", "external_physics_supported"]
REQUIRED_FIELDS = ("record_id", "batch_id", "run_id", "task_id", "design_hash",
                   "x12_canonical", "source_kind", "attempt_ids", "physical_solver_starts",
                   "cache_hit", "cache_key", "alpha_deg", "mach", "beta_deg", "CLtot",
                   "CDi", "CDtot", "CM", "L_N", "D_i_N", "q_Pa", "Sref_m2", "L_ref_N",
                   "lift_rel_error", "status", "solver_config_hash",
                   "labels_visible_to_arm", "created_ts_utc")


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_x12(x12: Sequence[Any]) -> str:
    """Canonical JSON for the 12D design vector (no spaces, fixed order)."""
    return json.dumps([float(value) for value in x12], separators=(",", ":"), sort_keys=True)


def task_spec_sha256() -> str:
    payload = json.dumps(TASK_SPEC.to_dict(), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_cache_key(x12: Sequence[Any], solver_config_sha256: str,
                      task_sha256: Optional[str] = None) -> str:
    """governance section 6: sha256(canonical x12 || task_spec_sha256 || solver_config_hash)."""
    payload = "%s||%s||%s" % (canonical_x12(x12), task_sha256 or task_spec_sha256(),
                              solver_config_sha256)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _ledger_events(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    path = run_dir / "solver_attempts.jsonl"
    events: Dict[str, Dict[str, Any]] = {}
    if not path.is_file():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        attempt_id = entry.get("attempt_id")
        if not attempt_id:
            continue
        events.setdefault(attempt_id, {})[entry.get("event", "?")] = entry
    return events


def _multiplicity(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    counts: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = polar_parser.case_key(row)
        label = "Mach=%g,AoA=%g,Beta=%g" % key
        entry = counts.setdefault(label, {"case_key": list(key), "row_count": 0,
                                          "polar_lines": []})
        entry["row_count"] += 1
        entry["polar_lines"].append(row.get("_line"))
    return counts


def _case_attempt_id(case_result: Dict[str, Any]) -> Optional[str]:
    evaluation = case_result.get("evaluation") or {}
    attempt = (case_result.get("attempt") or {}).get("start") or {}
    return evaluation.get("attempt_id") or attempt.get("attempt_id")


def build_evaluation_rows(plan: Dict[str, Any], case_result: Dict[str, Any],
                          case_result_relative: str,
                          ledger_events: Optional[Dict[str, Dict[str, Any]]] = None,
                          task_sha256: Optional[str] = None) -> List[Dict[str, Any]]:
    """One evaluation row per unique flow condition; scalar alpha, no nested rows."""
    stored = case_result.get("evaluation") or {}
    polar = case_result.get("polar") or {}
    raw_rows = polar.get("rows") or []
    unique_rows = polar_parser.unique_case_rows(raw_rows)
    multiplicity = _multiplicity(raw_rows)
    multiplicity_total = sum(int((entry or {}).get("row_count") or 0)
                             for entry in multiplicity.values())
    case_inputs_path = Path(case_result["_source_path"]).parent / "case_inputs.json"
    case_inputs = json.loads(case_inputs_path.read_text(encoding="utf-8")) \
        if case_inputs_path.is_file() else {}
    x12 = (case_inputs.get("design") or {}).get("x12") or []
    attempt_id = _case_attempt_id(case_result)
    attempt_events = (ledger_events or {}).get(str(attempt_id), {})
    created_ts = (attempt_events.get("end") or attempt_events.get("start") or {}).get("ts_utc")
    reference = stored.get("reference") or {}
    sref = float(reference.get("sref_m2") or TASK_SPEC.sref_baseline_m2)
    q_pa = float(reference.get("q_pa") or TASK_SPEC.q_pa)
    l_ref = float(reference.get("l_ref_n") or TASK_SPEC.l_ref_n)
    cl_target = float(reference.get("cl_target") or l_ref / (q_pa * sref))
    solver_config_sha256 = str(stored.get("solver_config_sha256")
                               or (stored.get("solver") or {}).get("solver_config_sha256") or "")
    geometry_sha256 = stored.get("geometry_sha256") or (case_inputs.get("geometry_sha256"))
    case_id = plan.get("case_id") or stored.get("case_id")
    batch_id = plan.get("batch_id") or plan.get("run_id") or stored.get("run_id")
    cache_key = compute_cache_key(x12, solver_config_sha256, task_sha256) if x12 else None
    tolerance = float(stored.get("lift_tolerance_rel") or TASK_SPEC.lift_tolerance_rel)
    lift_match = stored.get("lift_match") or {}
    rows: List[Dict[str, Any]] = []
    for index, row in enumerate(unique_rows):
        mach = float(row.get("Mach"))
        alpha = float(row.get("AoA"))
        beta = float(row.get("Beta") or 0.0)
        cl = row.get("CLtot")
        cdi = row.get("CDi")
        cdtot = row.get("CDtot")
        cm = row.get("CMoz", row.get("CM"))
        lift_n = q_pa * sref * float(cl) if cl is not None else None
        d_i_n = q_pa * sref * float(cdi) if cdi is not None else None
        lift_rel_error = (abs(lift_n - l_ref) / l_ref) if lift_n is not None else None
        label = "Mach=%g,AoA=%g,Beta=%g" % (mach, alpha, beta)
        row_multiplicity = multiplicity.get(label, {})
        record_id = "%s-eval-%04d" % (case_id, index)
        rows.append({
            "schema": EVALUATION_SCHEMA,
            "record_id": record_id,
            "batch_id": batch_id,
            "run_id": plan.get("run_id") or stored.get("run_id"),
            "case_id": case_id,
            "task_id": plan.get("task_id") or stored.get("task_id"),
            "purpose": plan.get("purpose"),
            "design_hash": design_hash(x12) if x12 else None,
            "design_hash_definition": design_identity.DESIGN_HASH_DEFINITION,
            "geometry_sha256": geometry_sha256,
            "geometry_sha256_definition": "sha256(raw bytes of the case .vspgeom); the "
                                          "geometry identity, kept separately from design_hash",
            "x12_canonical": canonical_x12(x12) if x12 else None,
            "source_kind": "REAL_VSPAERO",
            "attempt_ids": [attempt_id] if attempt_id else [],
            "physical_solver_starts": 0,
            "physical_solver_starts_note": (
                "this derived evaluation row added no start; the single attempt start is "
                "counted once in solver_attempts.jsonl and batch_summary.json"),
            "attempt_physical_solver_starts": int(stored.get("physical_solver_starts", 1)),
            "counts_toward_start_budget": False,
            "cache_hit": False,
            "cache_key": cache_key,
            "alpha_deg": alpha,
            "mach": mach,
            "beta_deg": beta,
            "Re_per_million": row.get("Re/1e6"),
            "CLtot": _finite(cl),
            "CLo": _finite(row.get("CLo")),
            "CLi": _finite(row.get("CLi")),
            "CDo": _finite(row.get("CDo")),
            "CDi": _finite(cdi),
            "CDtot": _finite(cdtot),
            "CSo": _finite(row.get("CSo")),
            "CSi": _finite(row.get("CSi")),
            "CStot": _finite(row.get("CStot")),
            "CM": _finite(cm),
            "CMz": _finite(row.get("CMoz", cm)),
            "L_over_D": _finite(row.get("L/D")),
            "L_N": _finite(lift_n),
            "D_i_N": _finite(d_i_n),
            "q_Pa": q_pa,
            "Sref_m2": sref,
            "L_ref_N": l_ref,
            "lift_rel_error": _finite(lift_rel_error),
            "lift_match_at_this_alpha": bool(lift_rel_error is not None
                                             and lift_rel_error <= tolerance),
            "status": "SOLVED",
            "solver_config_hash": solver_config_sha256,
            "solver_version": (stored.get("solver") or {}).get("version"),
            "labels_visible_to_arm": list(LABELS_VISIBLE),
            "labels_hidden_from_arm": list(LABELS_HIDDEN),
            "created_ts_utc": created_ts,
            "reference": {
                "sref_m2": sref, "cref_m": reference.get("cref_m"),
                "bref_m": reference.get("bref_m"), "xcg_m": reference.get("xcg_m"),
                "reference_frame": reference.get("frame") or "WING_AC",
                "q_pa": q_pa, "l_ref_n": l_ref, "cl_target": cl_target,
                "cm_trimming": TASK_SPEC.cm_trimming_disabled,
            },
            "objective": {"name": "D_i_N_at_flow_condition", "value": _finite(d_i_n)},
            "constraints": {
                "drag_positive": bool(cdi is not None and float(cdi) >= 0.0),
                "alpha_in_preregistered_window": bool(
                    TASK_SPEC.alpha_window_deg[0] <= alpha <= TASK_SPEC.alpha_window_deg[1]),
                "lift_matched_at_this_alpha": bool(lift_rel_error is not None
                                                  and lift_rel_error <= tolerance),
            },
            "evidence_split": {
                "solver_loop_verified": "ELIGIBLE_AFTER_P0_P1",
                "internal_aero_optimization_gain": "NOT_CLAIMED",
                "external_physics_supported": "NOT_CLAIMED",
                "fuel_burn_kg": None,
                "scope": "SOLVER_LOOP_VERIFIED_ONLY",
            },
            "provenance": {
                "source_case_result": case_result_relative,
                "source_case_result_sha256": sha256_file(case_result["_source_path"])
                if case_result.get("_source_path") else None,
                "source_polar_sha256": _polar_sha256(case_result),
                "polar_row_line": row.get("_line"),
                "case_multiplicity": row_multiplicity,
                "row_policy": "last_occurrence_per_unique_Mach_AoA_Beta",
            },
            "accounting": {
                "physical_solver_starts": 0,
                "attempt_physical_solver_starts": int(stored.get("physical_solver_starts", 1)),
                "unique_flow_conditions_total": len(unique_rows),
                "internal_solver_cases_total": stored.get("internal_solver_cases"),
                "internal_solver_cases_this_condition": row_multiplicity.get("row_count"),
                "expected_internal_cases": (plan.get("budget") or {}).get(
                    "expected_internal_cases"),
                "max_internal_cases": (plan.get("budget") or {}).get("max_internal_cases"),
            },
        })
    return rows


def build_evaluation_summary(plan: Dict[str, Any], case_result: Dict[str, Any],
                             rows: Sequence[Dict[str, Any]],
                             case_result_relative: str,
                             internal_solver_cases: Optional[int] = None) -> Dict[str, Any]:
    """Run-level matched-lift summary (the old single aggregate record, now separate)."""
    stored = case_result.get("evaluation") or {}
    polar = case_result.get("polar") or {}
    raw_rows = polar.get("rows") or []
    unique_rows = polar_parser.unique_case_rows(raw_rows)
    reference = stored.get("reference") or {}
    sref = float(reference.get("sref_m2") or TASK_SPEC.sref_baseline_m2)
    q_pa = float(reference.get("q_pa") or TASK_SPEC.q_pa)
    cl_target = float(reference.get("cl_target") or TASK_SPEC.l_ref_n / (q_pa * sref))
    match = stored.get("lift_match") or {}
    if not match:
        match = solver_runner._interp_alpha(unique_rows, cl_target) if unique_rows else \
            {"status": "NO_POLAR"}
    objective: Dict[str, Any] = {"name": "D_i_N_at_matched_lift", "value": None}
    constraints: Dict[str, Any] = {"lift_matched": False, "alpha_in_window": False,
                                   "drag_positive": None}
    if match.get("status") == "LIFT_MATCHED_BY_INTERPOLATION":
        alpha_match = float(match["alpha_deg"])
        cdi = solver_runner._interp_field_at_alpha(unique_rows, alpha_match, "CDi")
        cdtot = solver_runner._interp_field_at_alpha(unique_rows, alpha_match, "CDtot")
        cl = solver_runner._interp_field_at_alpha(unique_rows, alpha_match, "CLtot")
        if cdi is not None:
            objective = {"name": "D_i_N_at_matched_lift", "value": q_pa * sref * cdi,
                         "cdi_at_matched_lift": cdi, "cdtot_at_matched_lift": cdtot,
                         "cltot_at_matched_lift": cl, "alpha_deg": alpha_match,
                         "sref_m2": sref, "q_pa": q_pa, "lift_rel_error": 0.0,
                         "note": "interpolated inside the single stored polar; no new start"}
        constraints = {"lift_matched": True,
                       "alpha_in_window": bool(match.get("alpha_in_preregistered_window")),
                       "drag_positive": bool(cdi is not None and cdi >= 0.0),
                       "cm_trimming": TASK_SPEC.cm_trimming_disabled}
    if internal_solver_cases is None:
        internal_solver_cases = stored.get("internal_solver_cases")
    attempt_events: Dict[str, Dict[str, Any]] = {}
    budget = plan.get("budget") or {}
    return {
        "schema": EVALUATION_SCHEMA,
        "record_id": "%s-summary" % (plan.get("case_id") or stored.get("case_id")),
        "batch_id": plan.get("batch_id") or plan.get("run_id"),
        "run_id": plan.get("run_id") or stored.get("run_id"),
        "case_id": plan.get("case_id") or stored.get("case_id"),
        "task_id": plan.get("task_id") or stored.get("task_id"),
        "source_kind": "REAL_VSPAERO",
        "attempt_ids": [stored.get("attempt_id")] if stored.get("attempt_id") else [],
        "physical_solver_starts": int(stored.get("physical_solver_starts", 1)),
        "evaluations_rows": len(rows),
        "unique_flow_conditions": len(unique_rows),
        "raw_polar_rows": len(raw_rows),
        "internal_solver_cases": internal_solver_cases,
        "status": stored.get("status"),
        "objective": objective,
        "constraints": constraints,
        "lift_match": match,
        "reference": reference,
        "evidence_split": stored.get("evidence_split") or {
            "solver_loop_verified": "ELIGIBLE_AFTER_P0_P1",
            "internal_aero_optimization_gain": "NOT_CLAIMED",
            "external_physics_supported": "NOT_CLAIMED",
            "fuel_burn_kg": None,
        },
        "accounting": {
            "physical_solver_starts": int(stored.get("physical_solver_starts", 1)),
            "evaluations_rows": len(rows),
            "unique_flow_conditions": len(unique_rows),
            "raw_polar_rows": len(raw_rows),
            "internal_solver_cases": internal_solver_cases,
            "internal_case_breakdown_source": "derived_from_<base>.adb.cases",
            "expected_internal_cases": budget.get("expected_internal_cases"),
            "max_internal_cases": budget.get("max_internal_cases"),
            "accounting_note": (
                "ENV_SMOKE ran before governance v3 section 12.10; the ledger end line "
                "predates internal_solver_cases, so the internal count is derived from "
                "<base>.adb.cases and disclosed as pre-v3"),
        },
        "reserialization": {
            "schema": RESERIALIZE_SCHEMA,
            "source_case_result": case_result_relative,
            "source_case_result_sha256": sha256_file(case_result["_source_path"])
            if case_result.get("_source_path") else None,
            "physical_solver_starts_added": 0,
            "note": "schema completion only (F-ENV-02); no solver process, no new start",
        },
    }


def _internal_case_count(case_result: Dict[str, Any]) -> Optional[int]:
    stored = case_result.get("evaluation") or {}
    if stored.get("internal_solver_cases") is not None:
        return int(stored["internal_solver_cases"])
    inputs_dir = Path(case_result["_source_path"]).parent
    adb_cases = sorted(inputs_dir.glob("*.adb.cases"))
    if adb_cases:
        return len([line for line in adb_cases[0].read_text(
            encoding="utf-8", errors="replace").splitlines() if line.strip()])
    polar = case_result.get("polar") or {}
    return int(polar.get("row_count") or 0)


def reserialize_run(run_dir: str | Path) -> Dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    events = _ledger_events(run_dir)
    task_sha = task_spec_sha256()
    case_results = sorted(run_dir.glob("cases/*/inputs/case_result.json"))
    rows: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    for path in case_results:
        case_result = json.loads(path.read_text(encoding="utf-8"))
        case_result["_source_path"] = str(path)
        relative = path.relative_to(run_dir).as_posix()
        case_rows = build_evaluation_rows(plan, case_result, relative, events, task_sha)
        internal = _internal_case_count(case_result)
        rows.extend(case_rows)
        summaries.append(build_evaluation_summary(plan, case_result, case_rows, relative,
                                                 internal))
    evaluations_path = run_dir / "evaluations.jsonl"
    with open(evaluations_path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    summary_path = run_dir / SUMMARY_FILENAME
    summary_payload = {
        "schema": "dreal001.evaluation_summary.v1",
        "run_id": plan.get("run_id"),
        "batch_id": plan.get("batch_id"),
        "case_count": len(summaries),
        "evaluation_count": len(rows),
        "physical_solver_starts": sum(int(item.get("physical_solver_starts") or 0)
                                      for item in summaries),
        "cases": summaries,
        "note": "matched-lift objective lives here; evaluations.jsonl holds one row per "
                "unique flow condition (F-ENV-02)",
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False,
                                       allow_nan=False) + "\n", encoding="utf-8")
    return {"run_dir": str(run_dir), "evaluations": str(evaluations_path),
            "evaluation_summary": str(summary_path),
            "case_count": len(summaries), "evaluation_count": len(rows),
            "physical_solver_starts": 0,
            "note": "re-serialization only; the ledger remains the physical-start authority"}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild evaluations.jsonl without solver starts")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(reserialize_run(args.run_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
