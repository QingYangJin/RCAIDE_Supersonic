"""D-REAL-001 P0R tooling-smoke plan builder (zero solver starts).

Builds the single-start TOOLING_SMOKE batch that replaces the ENV_SMOKE evidence
lost in the 2026-11-10 directory deletion.  It consumes the zero-physical preflight
record for the production thin 12x25 configuration, copies the four solver input
pieces plus the .vsp3 into the case input directory and writes plan.json with
status PENDING_APPROVAL.  Nothing here starts vspaero.exe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from .design_identity import design_hash as compute_design_hash
from .mesh_identity import MAX_MESH_ATTEMPTS, family_label
from .p1_preflight import DESIGN_SPACE_CONFIG
from .task_spec import TASK_SPEC

REPO_ROOT = Path(__file__).resolve().parents[4]
TASK_SPEC_RELATIVE = "configs/dreal001_task_fixed_cruise_REAL.json"
TASK_SPEC_PATH = REPO_ROOT / TASK_SPEC_RELATIVE
FREEZE_ARTIFACT = Path(__file__).resolve().parent / "design_space_freeze.json"

PLAN_SCHEMA = "dreal001.solver_plan.v1"
P0R_SCHEMA = "dreal001.p0r_inputs.v1"
DEFAULT_RUN_ID = "DREAL001-P0R-20261110-01"
CONFIG_ID = "CFG-01-thin-12x25"
TASK_ID = "TOOLING"
PURPOSE = "TOOLING_SMOKE_NOT_AERO_EVIDENCE"
SOLVER_PATH = Path(r"D:\OpenVSP-3.55.0\OpenVSP-3.55.0-win64\vspaero.exe")
SOLVER_VERSION = "VSPAERO v7.2.2 (compiled 2026-10-12)"
TIMEOUT_SECONDS = 600
OMP_THREADS = 1
BASENAME = "concorde_baseline"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def task_spec_canonical_sha256() -> str:
    payload = json.dumps(TASK_SPEC.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def solver_config_hash(geometry_set: str, tess_u: float, tess_w: float,
                       timeout_s: float) -> str:
    from .evaluator import solver_config_hash as _hash
    return _hash(geometry_set, tess_u, tess_w, timeout_s)


def _copytree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if item.is_file():
            shutil.copy2(item, dst / item.name)


def build_p0r_plan(run_dir: str | Path,
                   config_id: str = CONFIG_ID) -> Dict[str, Any]:
    """Write plan.json for the P0R TOOLING_SMOKE batch (no solver start)."""
    run_dir = Path(run_dir)
    preflight_dir = run_dir / "preflight" / config_id
    preflight_path = preflight_dir / "preflight.json"
    if not preflight_path.is_file():
        raise SystemExit("missing zero-physical preflight record: %s" % preflight_path)
    index_path = run_dir / "preflight" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    record = json.loads(preflight_path.read_text(encoding="utf-8"))
    if not record.get("all_ok") or not index.get("all_ok"):
        raise SystemExit("preflight is not clean; refusing to write a plan")
    pieces = record.get("input_pieces") or {}
    for label in ("vspgeom", "vkey", "vspaero", "csf"):
        if label not in pieces:
            raise SystemExit("preflight record is missing the %s piece" % label)
    run_id = run_dir.name
    case_id = run_id + "-ENV_SMOKE"
    case_dir = run_dir / "cases" / case_id / "inputs"
    _copytree(preflight_dir, case_dir)
    basename = str(record.get("case_inputs_record") or "case_inputs.json")
    case_inputs = case_dir / basename
    if not case_inputs.is_file():
        raise SystemExit("preflight did not leave %s" % case_inputs)
    inputs = json.loads(case_inputs.read_text(encoding="utf-8"))
    x12 = inputs.get("x12") or inputs.get("design_vector")
    files: Dict[str, Any] = {}
    for label in ("vspgeom", "vkey", "vspaero", "csf"):
        path = Path(str(pieces[label]["path"]))
        target = case_dir / (BASENAME + "." + label)
        if not target.is_file():
            raise SystemExit("missing copied input piece %s" % target)
        files[label] = {"bytes": target.stat().st_size, "sha256": sha256_file(target)}
    vsp3 = case_dir / (BASENAME + ".vsp3")
    if vsp3.is_file():
        files["vsp3"] = {"bytes": vsp3.stat().st_size, "sha256": sha256_file(vsp3)}
    mesh = (record.get("sweep_input_readback") or {}).get("inputs_int") or {}
    mesh_identity = record.get("mesh") or {}
    plan: Dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "batch_id": run_id,
        "run_id": run_id,
        "case_id": case_id,
        "task_id": TASK_ID,
        "purpose": PURPOSE,
        "requested_by": "a1-aviation-f (A1), recovery batch after the 2026-11-10 deletion",
        "status": "PENDING_APPROVAL",
        "requested_window_cst": {
            "start": None,
            "end": None,
            "exclusive_solver_slot": True,
            "note": "window is assigned by the Lead; approval.json must carry a valid token",
        },
        "approval": {
            "approval_owner": "lead",
            "approval_file": "approval.json",
            "max_starts": 1,
            "approved_by": None,
            "window_token": None,
            "status": "NOT_APPROVED",
            "note": "PENDING_APPROVAL is a document state, not a permission: no start until the Lead writes approval.json.",
        },
        "budget": {
            "physical_solver_starts_planned": 1,
            "physical_solver_starts_max": 1,
            "retries": 0,
            "note": "single start; no retry inside the window",
        },
        "task_spec": {
            "path": TASK_SPEC_RELATIVE,
            "raw_sha256": (sha256_file(TASK_SPEC_PATH) if TASK_SPEC_PATH.is_file() else None),
            "canonical_sha256": task_spec_canonical_sha256(),
            "hash_scope": {
                "raw_sha256": "sha256 of the bytes of configs/dreal001_task_fixed_cruise_REAL.json",
                "canonical_sha256": "sha256 of json.dumps(TASK_SPEC.to_dict(), sort_keys=True, "
                                    "separators=(',', ':')) with no trailing newline",
                "comparability": "raw and canonical digests cover different byte strings and must "
                                 "never be compared with each other",
            },
        },
        "frozen_design_space": {
            "config_path": DESIGN_SPACE_CONFIG.relative_to(REPO_ROOT).as_posix(),
            "config_sha256": sha256_file(DESIGN_SPACE_CONFIG),
            "freeze_artifact_path": "research/concorde_metaopt/dreal001/geometry/"
                                    "design_space_freeze.json",
            "freeze_artifact_sha256": (sha256_file(FREEZE_ARTIFACT)
                                       if FREEZE_ARTIFACT.is_file() else None),
            "frozen": True,
            "bounds_status": "frozen_for_dreal001_20261110",
            "freeze_decision_commit": "3624db7",
        },
        "solver": {
            "path": str(SOLVER_PATH),
            "sha256": sha256_file(SOLVER_PATH) if SOLVER_PATH.is_file() else None,
            "version_banner": SOLVER_VERSION,
            "omp_threads": OMP_THREADS,
            "timeout_s": TIMEOUT_SECONDS,
            "solver_config_hash": solver_config_hash(
                str(record.get("geometry_set") or "thin"),
                float((record.get("tessellation") or {}).get("tess_u", 12)),
                float((record.get("tessellation") or {}).get("tess_w", 25)),
                float(TIMEOUT_SECONDS)),
            "cwd": str(case_dir.relative_to(run_dir.parents[2]) if False else case_dir),
        },
        "command": {
            "argv": [str(SOLVER_PATH), "-omp", str(OMP_THREADS), BASENAME],
            "note": "the .vspaero file carries Mach 2.02 / 7 alpha / Vinf / Rho / ReCref; no -fs/-mach/-alpha/-beta",
            "forbidden_flags": ["-fs", "-mach", "-alpha", "-beta"],
        },
        "geometry": {
            "source": "baseline 12D design vector (design_space_12d_lifting_surfaces.yaml), solver components = main_wing + vertical_tail, no fuselage",
            "geometry_set": str(record.get("geometry_set")),
            "geometry_set_codes": record.get("geometry_set_codes"),
            "tessellation": record.get("tessellation"),
            "alpha_list_deg": record.get("alpha_list_deg"),
            "mach_list": record.get("mach_list"),
            "sref_m2": record.get("sref_m2"),
            "cref_m": float(TASK_SPEC.cref_m),
            "bref_m": float(TASK_SPEC.bref_m),
            "xcg_m": float(TASK_SPEC.xcg_m),
            "reference_frame": "WING_AC",
            "files": files,
            "geometry_sha256": files["vspgeom"]["sha256"],
            "mesh_identity": {
                "target_mesh_family": mesh_identity.get("target_family"),
                "expected_nodes": mesh_identity.get("nodes"),
                "expected_elements": mesh_identity.get("elements"),
                "expected_canonical_mesh_sha256": mesh_identity.get("canonical_mesh_sha256"),
                "max_mesh_attempts": 12,
                "fail_closed": True,
            },
            "internal_solver_cases_expected": record.get("internal_solver_cases_expected"),
            "num_wake_nodes": mesh.get("NumWakeNodes"),
            "files_note": "four-piece input set is as-prepared by the zero-physical preflight; VSPAERO object IDs are not reproducible byte-for-byte, the canonical topology hash is the reproducible identity",
        },
        "design": {
            "design_hash": compute_design_hash(x12) if x12 else None,
            "x12": x12,
            "case_inputs_record": str(case_inputs),
        },
        "preflight": {
            "config_id": config_id,
            "record_path": str(preflight_path),
            "record_sha256": sha256_file(preflight_path),
            "index_sha256": sha256_file(index_path),
            "all_ok": bool(record.get("all_ok")),
            "physical_solver_starts": 0,
        },
        "expected_outputs": [
            BASENAME + ".polar", BASENAME + ".history", BASENAME + ".lod",
            BASENAME + ".groups", "stdout/stderr logs",
        ],
        "pass_criteria": {
            "solver_loop_verified_enough_for_tooling_smoke": "vspaero exits 0, .polar exists and is non-empty, parser reads 7 alpha rows (-2..10), CL/CDi/CDtot columns finite, header echoes Mach 2.02 / Sref 358.25 / Cref 18.489893 / Bref 25.604638 / X_cg 16.821978259514246",
            "not_evidence_for": "aero accuracy, physical drag, optimization gain, fuel burn (fuel_burn_kg stays null), trim or stability",
            "note": "negative or non-physical CDi would still be a TOOLING smoke result but MUST be reported as an anomaly, not hidden",
        },
        "stop_conditions": [
            "no second start inside this window; if the single start fails, stop and report",
            "timeout 600 s -> kill process, record status TIMEOUT, count 1 start, no retry",
            "missing .polar or empty .polar -> FAIL, no retry",
            "if the solver reports missing .vkey/.vspgeom -> pipeline defect, no retry",
            "mesh family other than the target 543/472 -> FAIL_CLOSED, never switch family",
        ],
        "accounting": {
            "solver_attempts_file": "solver_attempts.jsonl",
            "planned_record": {
                "run_id": run_id,
                "task_id": TASK_ID,
                "case_id": case_id,
                "purpose": PURPOSE,
                "physical_solver_starts": 1,
            },
        },
        "what_this_does_not_prove": [
            "nothing about VSPAERO 7.2.2 supersonic accuracy or convergence at Mach 2.02",
            "no full-aircraft drag, no trim, no stability, no fuel burn",
            "the thin VLM set may show a negative-CDi anomaly; this smoke only proves the toolchain runs and the polar parses",
            "the historical ENV_SMOKE SHA256 values are NOT_RECOVERABLE and are not reused here",
        ],
    }
    plan_bytes = (json.dumps(plan, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    (run_dir / "plan.json").write_bytes(plan_bytes)
    preflight_summary = {
        "schema": P0R_SCHEMA,
        "run_id": run_id,
        "config_id": config_id,
        "physical_solver_starts": 0,
        "solver_started": False,
        "all_ok": bool(record.get("all_ok")),
        "preflight_record": str(preflight_path),
        "preflight_record_sha256": sha256_file(preflight_path),
        "index_sha256": sha256_file(index_path),
        "case_inputs": str(case_inputs),
        "four_piece": files,
        "sweep_readback_check": record.get("sweep_readback_check"),
        "note": "Zero-physical preflight only. No vspaero.exe execution and no .polar/.history exist in this run directory.",
    }
    (run_dir / "preflight.json").write_bytes(
        (json.dumps(preflight_summary, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return {"plan": plan, "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "plan_bytes": len(plan_bytes), "preflight_summary": preflight_summary}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P0R tooling-smoke plan builder (zero starts)")
    default_run_dir = Path(__file__).resolve().parent / "runs" / DEFAULT_RUN_ID
    parser.add_argument("--run-dir", default=str(default_run_dir))
    parser.add_argument("--config-id", default=CONFIG_ID)
    args = parser.parse_args(argv)
    result = build_p0r_plan(args.run_dir, config_id=args.config_id)
    print(json.dumps({"run_dir": args.run_dir,
                      "status": result["plan"]["status"],
                      "plan_sha256": result["plan_sha256"],
                      "plan_bytes": result["plan_bytes"],
                      "starts": 1,
                      "internal_cases": result["plan"]["geometry"]["internal_solver_cases_expected"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())