"""F-ENV-03: run_config.json, batch_summary.json and corrections (NO solver start).

Pure post-processing of the immutable P0 evidence:

* run_config.json  - immutable configuration of the approved TOOLING batch (approval/plan/
                     ledger/input SHAs, solver, argv, reference quantities, labels).  Written
                     AFTER the run as a declaration; it adds no solver start.
* batch_summary.json - batch-level closeout: attempts, starts, internal cases, evaluations,
                     outputs and retention, plus actual-vs-approved budget.
* corrections/correction_NNN.json - governance section 12.7 defect records; superseded files
                     are never overwritten, only disclosed with old and new SHA256.

All counts that matter (physical_solver_starts, internal_solver_cases) are computed from
solver_attempts.jsonl, never typed by hand.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import evidence_manifest, evaluation_reserialize
from .task_spec import TASK_SPEC

RUN_CONFIG_SCHEMA = "dreal001.run_config.v1"
BATCH_SUMMARY_SCHEMA = "dreal001.batch_summary.v1"
CORRECTION_SCHEMA = "dreal001.correction.v1"
TASK_SPEC_CONFIG_RELATIVE = "configs/dreal001_task_fixed_cruise_REAL.json"
EXPECTED_TASK_SPEC_RAW_SHA256 = \
    "028086a56f466c1639432218f6928deb6d479160a13db597fef1aa7284e1f0f7"
EXPECTED_TASK_SPEC_GIT_BLOB_SHA1 = "3f831d4b"

AUDITED_EVALUATIONS = {
    "sha256": "201d3ce07098caf20c06667fd5dc4d4a4095d298050fd391cd3b5cc4888539b2",
    "bytes": 16075,
    "label": "evaluations.jsonl as independently audited by A5 on 2026-11-10T09:10Z",
    "retention_status": "NOT_RETAINED",
    "retention_note": "the 16,075 B audited copy lives only in the pre-incident P0 run "
                      "directory, which was destroyed on 2026-11-10; it was never committed "
                      "and is NOT_RECOVERABLE. The SHA256 stays quoted for the audit record.",
}
INTERIM_EVALUATIONS = {
    "sha256": "141b9af229a54e6a207a2cb4cdefa5589d8fc398999f189ecf2de1777cae2db0",
    "bytes": 21537,
    "label": "interim one-case-one-line re-serialization (alpha nested rows)",
    "retention_status": "RETAINED_IN_GIT_HISTORY",
    "retention_note": "recoverable from commit b5dcbbc of the pre-incident worktree via "
                      "git show b5dcbbc:<path>; the file itself is not in the current tree.",
}


def repo_root() -> Path:
    """Repository root of this worktree (geometry -> dreal001 -> concorde_metaopt -> research -> root)."""
    return Path(__file__).resolve().parents[4]


def task_spec_hash_scope() -> Dict[str, Any]:
    """Disclose the three TaskSpec hash scopes (A5 F-ENV-03 / L-03)."""
    path = repo_root() / TASK_SPEC_CONFIG_RELATIVE
    raw_sha = None
    raw_bytes = None
    git_blob = None
    if path.is_file():
        raw = path.read_bytes()
        raw_sha = hashlib.sha256(raw).hexdigest()
        raw_bytes = len(raw)
        try:
            proc = subprocess.run(["git", "hash-object", str(path)], capture_output=True,
                                  text=True, timeout=30, check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                git_blob = proc.stdout.strip()
        except Exception:
            git_blob = None
    return {
        "canonical_sha256": evaluation_reserialize.task_spec_sha256(),
        "canonical_definition": "sha256 of json.dumps(TASK_SPEC.to_dict(), sort_keys=True, "
                                "separators=(',', ':')) — canonical form, not the file bytes",
        "raw_sha256": raw_sha,
        "raw_config_path": TASK_SPEC_CONFIG_RELATIVE,
        "raw_bytes": raw_bytes,
        "git_blob_sha1": git_blob,
        "comparison_rule": "the three scopes are not interchangeable: only identical scope and "
                           "identical bytes may be compared; canonical hash equality does not "
                           "imply raw-file equality",
    }


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _ledger(run_dir: Path) -> List[Dict[str, Any]]:
    path = run_dir / "solver_attempts.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _relative(path: Any, root: Path) -> Optional[str]:
    if not path:
        return None
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return str(path)


def write_run_config(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir).resolve()
    plan = _read_json(run_dir / "plan.json")
    approval = _read_json(run_dir / "approval.json")
    events = _ledger(run_dir)
    starts = [entry for entry in events if entry.get("event") == "start"]
    ends = {str(entry.get("attempt_id")): entry for entry in events
            if entry.get("event") == "end"}
    case_inputs = _read_json(next((run_dir / "cases").glob("*/inputs/case_inputs.json"),
                                  Path("__missing__")))
    case_results = sorted((run_dir / "cases").glob("*/inputs/case_result.json"))
    stored = _read_json(case_results[0]).get("evaluation", {}) if case_results else {}
    input_hashes = starts[0].get("input_hashes", {}) if starts else {}
    payload = {
        "schema": RUN_CONFIG_SCHEMA,
        "post_hoc_derived": True,
        "added_physical_solver_starts": 0,
        "batch_id": plan.get("batch_id"),
        "run_id": plan.get("run_id"),
        "case_id": plan.get("case_id"),
        "task_id": plan.get("task_id"),
        "aero_task_id": TASK_SPEC.task_id,
        "purpose": plan.get("purpose"),
        "requested_by": plan.get("requested_by"),
        "status": "EXECUTED",
        "actual_start_utc": starts[0].get("ts_utc") if starts else None,
        "actual_end_utc": (ends.get(str(starts[0].get("attempt_id"))) or {}).get("ts_utc")
        if starts else None,
        "window_token": starts[0].get("window_token") if starts else None,
        "window": starts[0].get("window") if starts else None,
        "approval": {
            "approval_file": "approval.json",
            "approval_sha256": evidence_manifest.sha256_file(run_dir / "approval.json")
            if (run_dir / "approval.json").is_file() else None,
            "approved_by": approval.get("approved_by"),
            "approved_at_utc": approval.get("approved_at_utc")
            or approval.get("approved_at"),
            "max_starts": (approval.get("budget") or {}).get("max_starts")
            or approval.get("max_starts"),
            "plan_sha256": plan.get("approval", {}).get("plan_sha256")
            or evidence_manifest.sha256_file(run_dir / "plan.json")
            if (run_dir / "plan.json").is_file() else None,
        },
        "plan": {
            "plan_file": "plan.json",
            "plan_sha256": evidence_manifest.sha256_file(run_dir / "plan.json")
            if (run_dir / "plan.json").is_file() else None,
            "budget": plan.get("budget"),
            "status_field": plan.get("status"),
            "status_note": (
                "plan.status is the pre-approval PENDING_LEAD_APPROVAL value and is kept "
                "unmodified (F-ENV-06) so the audited plan_sha256 does not drift; the "
                "effective approval is approval.json"),
        },
        "git": plan.get("git"),
        "solver": {
            "path": (plan.get("solver") or {}).get("path"),
            "sha256": (plan.get("solver") or {}).get("sha256"),
            "version_banner": (plan.get("solver") or {}).get("version_banner"),
            "omp_threads": (plan.get("solver") or {}).get("omp_threads"),
            "timeout_s": (plan.get("solver") or {}).get("timeout_s"),
            "cwd": (plan.get("solver") or {}).get("cwd"),
        },
        "command": plan.get("command"),
        "legacy_cli_list": {
            "fs_cli_used": any(str(item) == "-fs" for item in
                               (plan.get("command") or {}).get("argv", [])),
            "disclosure": (
                "ENV_SMOKE was executed before governance v3 section 12.10; a legacy -fs "
                "alpha list was used and it duplicated cases (F-ENV-01, DISCLOSED_PRE_V3). "
                "P1 forbids -fs/-mach/-alpha/-beta and writes lists into .vspaero."),
        },
        "geometry": {
            "source": (plan.get("geometry") or {}).get("source"),
            "geometry_set": (plan.get("geometry") or {}).get("geometry_set"),
            "tessellation": (plan.get("geometry") or {}).get("tessellation"),
            "solver_includes_fuselage": False,
            "solver_geometry_components": case_inputs.get("solver_geometry_components"),
            "input_hashes": {key: {"bytes": value.get("bytes"), "sha256": value.get("sha256")}
                             for key, value in input_hashes.items()},
            "vsp3_sha256": (input_hashes.get("vsp3") or {}).get("sha256"),
        },
        "reference_quantities": {
            "sref_m2": (plan.get("geometry") or {}).get("sref_m2"),
            "cref_m": (plan.get("geometry") or {}).get("cref_m"),
            "bref_m": (plan.get("geometry") or {}).get("bref_m"),
            "xcg_m": (plan.get("geometry") or {}).get("xcg_m"),
            "reference_frame": (plan.get("geometry") or {}).get("reference_frame"),
            "q_pa": TASK_SPEC.q_pa,
            "l_ref_n": TASK_SPEC.l_ref_n,
            "cl_target": (stored.get("reference") or {}).get("cl_target"),
            "ref_flag": TASK_SPEC.ref_flag,
            "task_spec_sha256": evaluation_reserialize.task_spec_sha256(),
            "task_spec_config": TASK_SPEC_CONFIG_RELATIVE,
            "task_spec_hash_scope": task_spec_hash_scope(),
        },
        "labels": {
            "labels_visible_to_arm": evaluation_reserialize.LABELS_VISIBLE,
            "labels_hidden_from_arm": evaluation_reserialize.LABELS_HIDDEN,
            "fuel_burn_kg": None,
        },
        "evidence_scope": {
            "source_kind": "REAL_VSPAERO",
            "physical_validation_status": "NOT_VALIDATED",
            "solver_loop_verified": "ELIGIBLE_AFTER_P0_P1",
            "internal_aero_optimization_gain": "NOT_CLAIMED",
            "external_physics_supported": "NOT_CLAIMED",
            "note": "TOOLING smoke; not aero or fuel-burn evidence",
        },
        "environment": {
            "python_version": case_inputs.get("python_version"),
            "openvsp_version": case_inputs.get("openvsp_version"),
            "openvsp_root": case_inputs.get("openvsp_root"),
        },
        "ledger_sha256": evidence_manifest.sha256_file(run_dir / "solver_attempts.jsonl")
        if (run_dir / "solver_attempts.jsonl").is_file() else None,
    }
    path = run_dir / "run_config.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")
    return path


def write_batch_summary(run_dir: str | Path,
                        retention_entries: Optional[List[Dict[str, Any]]] = None) -> Path:
    run_dir = Path(run_dir).resolve()
    plan = _read_json(run_dir / "plan.json")
    approval = _read_json(run_dir / "approval.json")
    events = _ledger(run_dir)
    starts = [entry for entry in events if entry.get("event") == "start"]
    ends = {str(entry.get("attempt_id")): entry for entry in events
            if entry.get("event") == "end"}
    totals = evidence_manifest.ledger_totals(run_dir / "solver_attempts.jsonl", run_dir)
    evaluation_summary = _read_json(run_dir / evaluation_reserialize.SUMMARY_FILENAME)
    evaluations_rows = 0
    if (run_dir / "evaluations.jsonl").is_file():
        evaluations_rows = len([line for line in
                                (run_dir / "evaluations.jsonl").read_text(
                                    encoding="utf-8").splitlines() if line.strip()])
    cases: List[Dict[str, Any]] = []
    for start in starts:
        attempt_id = str(start.get("attempt_id"))
        end = ends.get(attempt_id) or {}
        case_id = start.get("case_id")
        summary = next((item for item in evaluation_summary.get("cases", [])
                        if item.get("case_id") == case_id), {})
        outputs = end.get("outputs") or {}
        cases.append({
            "case_id": case_id,
            "attempt_id": attempt_id,
            "start_ts_utc": start.get("ts_utc"),
            "end_ts_utc": end.get("ts_utc"),
            "wall_s": end.get("wall_s"),
            "exit_code": end.get("exit_code"),
            "status": end.get("status"),
            "physical_solver_starts": 1,
            "internal_solver_cases": totals["attempts"][0]["internal_solver_cases"]
            if totals["attempts"] else summary.get("internal_solver_cases"),
            "internal_solver_cases_source": (
                totals["attempts"][0]["internal_solver_cases_source"]
                if totals["attempts"] else "MISSING"),
            "expected_internal_cases": summary.get("accounting", {}).get(
                "expected_internal_cases"),
            "max_internal_cases": summary.get("accounting", {}).get(
                "max_internal_cases"),
            "evaluations_rows": summary.get("evaluations_rows"),
            "unique_flow_conditions": summary.get("unique_flow_conditions"),
            "objective": summary.get("objective"),
            "outputs": {name: {"bytes": value.get("bytes"), "sha256": value.get("sha256")}
                        for name, value in outputs.items()},
        })
    approved = (approval.get("budget") or {}).get("max_starts") \
        or (plan.get("budget") or {}).get("physical_solver_starts_max")
    payload = {
        "schema": BATCH_SUMMARY_SCHEMA,
        "post_hoc_derived": True,
        "added_physical_solver_starts": 0,
        "batch_id": plan.get("batch_id"),
        "run_id": plan.get("run_id"),
        "task_id": plan.get("task_id"),
        "purpose": plan.get("purpose"),
        "source_kind": "REAL_VSPAERO",
        "physical_validation_status": "NOT_VALIDATED",
        "cases": cases,
        "totals": {
            "attempts": len(starts),
            "physical_solver_starts": totals["physical_solver_starts"],
            "internal_solver_cases": totals["internal_solver_cases"],
            "evaluations_rows": evaluations_rows,
            "unique_flow_conditions": evaluation_summary.get("evaluation_count"),
            "retention_entries": len(retention_entries or []),
            "retained_bytes": sum(int(item.get("bytes") or 0)
                                  for item in (retention_entries or [])),
        },
        "budget_actual_vs_approved": {
            "approved_max_starts": approved,
            "starts_used": totals["physical_solver_starts"],
            "within_approved_starts": (totals["physical_solver_starts"] <= int(approved))
            if approved is not None else None,
            "approved_retries": (plan.get("budget") or {}).get("retries"),
            "retries_used": 0,
            "expected_internal_cases": None,
            "max_internal_cases": None,
            "internal_limit_note": (
                "ENV_SMOKE predates governance v3 section 12.10: no expected/max "
                "internal-case budget was approved, so internal_solver_cases=%d is "
                "disclosed as F-ENV-01 / DISCLOSED_PRE_V3 and is not a budget overrun "
                "(the approved unit was process starts)" % totals["internal_solver_cases"]),
        },
        "disclosures": {
            "F_ENV_01": {
                "status": "DISCLOSED_PRE_V3",
                "text": "1 approved process start expanded to 32 internal solver cases "
                        "because VSPAERO 7.2.2 merged the legacy -fs list into .vspaero; "
                        "P1 must declare expected/max internal cases and preflight with "
                        "StopBeforeRun=1.",
            },
            "F_ENV_06": {
                "status": "DISCLOSED",
                "text": "plan.status=PENDING_LEAD_APPROVAL is a stale pre-approval field; "
                        "it is not rewritten so plan_sha256 keeps matching the audited hash.",
            },
            "F_ENV_05": {
                "status": "DISCLOSED",
                "text": "case_result.json stores 36 Infinity tokens (non-strict JSON); the "
                        "file is immutable and is not rewritten. evaluations.jsonl and "
                        "evaluation_summary.json substitute null and are written with "
                        "allow_nan=False.",
            },
        },
        "approval_sha256": evidence_manifest.sha256_file(run_dir / "approval.json")
        if (run_dir / "approval.json").is_file() else None,
        "plan_sha256": evidence_manifest.sha256_file(run_dir / "plan.json")
        if (run_dir / "plan.json").is_file() else None,
        "ledger_sha256": totals["ledger_sha256"],
    }
    path = run_dir / "batch_summary.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8")
    return path


def write_correction_001(run_dir: str | Path) -> Path:
    """Governance 12.7: disclose the superseded evaluations.jsonl instead of overwriting it."""
    run_dir = Path(run_dir).resolve()
    path = run_dir / "evaluations.jsonl"
    new_sha = evidence_manifest.sha256_file(path) if path.is_file() else None
    new_bytes = path.stat().st_size if path.is_file() else None
    corrections = run_dir / "corrections"
    corrections.mkdir(exist_ok=True)
    payload = {
        "schema": CORRECTION_SCHEMA,
        "correction_id": "correction_001",
        "batch_id": "DREAL001-P0-20261110-01",
        "run_id": "DREAL001-P0-20261110-01",
        "created_by": "a1-aviation-f (A1)",
        "created_at_utc": "2026-11-10T09:20:00Z",
        "issue": "F-ENV-02",
        "correction_type": "RESERIALIZATION_SUPERSEDE",
        "target": "evaluations.jsonl",
        "governance": "docs/planning/dreal001_execution_governance_20261110.md section 12.7",
        "defect": "F-ENV-02: evaluations.jsonl held one aggregated case row with nested "
                  "alpha rows and null record_id/batch_id/alpha_list_deg/cache_key, instead "
                  "of one row per evaluation with a scalar alpha.",
        "authority": "A5 audit docs/reviews/dreal001_a5_env_smoke_audit_20261110.md F-ENV-02",
        "action": "rebuild evaluations.jsonl as one row per unique flow condition with the "
                  "governance section 6 schema fields; matched-lift aggregate moved to "
                  "evaluation_summary.json",
        "superseded": [AUDITED_EVALUATIONS, INTERIM_EVALUATIONS],
        "superseded_note": "neither superseded version is rewritten or deleted; the A5-audited "
                           "16,075 B copy is NOT_RETAINED (pre-incident run directory lost) and "
                           "the 21,537 B interim copy is RETAINED_IN_GIT_HISTORY (b5dcbbc); both "
                           "SHA256 values stay quoted in the audit record",
        "new": {"sha256": new_sha, "bytes": new_bytes,
                "evaluations_rows": len([line for line in path.read_text(
                    encoding="utf-8").splitlines() if line.strip()]) if path.is_file() else 0},
        "physical_solver_starts_added": 0,
        "solver_started_by_correction": False,
        "verification": "recompute sha256 of evaluations.jsonl and compare with new.sha256; "
                        "re-parse with allow_nan=False",
    }
    out = corrections / "correction_001.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                   encoding="utf-8")
    return out


def write_closeout(run_dir: str | Path,
                   retention_entries: Optional[List[Dict[str, Any]]] = None) -> Dict[str, str]:
    run_dir = Path(run_dir).resolve()
    if retention_entries is None:
        retention_entries = evidence_manifest.read_retention(run_dir)
    config = write_run_config(run_dir)
    summary = write_batch_summary(run_dir, retention_entries)
    correction = write_correction_001(run_dir)
    return {"run_config": str(config), "batch_summary": str(summary),
            "correction": str(correction)}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D-REAL-001 run closeout (no solver)")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(write_closeout(args.run_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
