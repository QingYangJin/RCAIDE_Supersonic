"""P2a pre-registration package for D-REAL-001 (A2, zero physical).

Builds the frozen P2a batch proposal: plan.json, PREREGISTRATION.md,
approval.DRAFT.json, identity_binding.json, dry_run.json, RUNNER_COMMANDS.md,
SHA256SUMS.txt.  No solver is ever launched; A2 physical_call_count=0.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .constants import (
    ALPHA_PRIMARY_DEG,
    BACKEND_REAL,
    DIMENSION,
    INTERNAL_SOLVER_CASES_PER_START,
    LIFT_TOL_REL,
    L_REF_N,
    MAX_STARTS_PER_DESIGN,
    Q_PA_DEFAULT,
    REFERENCE_FRAME,
    XCG_M,
)
from .p2a_binding import (
    a1_code_binding,
    a1_task_spec_binding,
    frozen_design_space_binding,
    legacy_solver_config_keys,
    probe_a1_fail_closed,
    probe_a2_adapter_fail_closed,
)
from .p2a_support import (
    EXPECTED_DESIGNS as SUPPORT_EXPECTED_DESIGNS,
    WarmStartSupportError,
    load_warmstart_support,
    support_candidates,
)
from .records import canonical_json, sha256_bytes, sha256_file, utc_now, write_json_atomic
from .task import build_task

P2A_PLAN_SCHEMA = "dreal001.prereg.v2.p2a"
P2A_APPROVAL_SCHEMA = "dreal001.approval.v2"
P2A_BATCH_ID = "DREAL001-P2-20261111-01"
BATCH_ID_RE = re.compile(r"^DREAL001-(?:P0|P1|P2|P3|P4|PERF)-\d{8}-\d{2}$")
RUN_ID_RE = re.compile(r"^DREAL001-(?:P0|P1|P2|P3|P4|PERF)-\d{8}-\d{2}-(?:BO|DE|PSO|ABO|ADE|APSO|ENV|REPLAY)-B\d{2,4}-s\d+$")
ARMS: Tuple[str, ...] = ("BO", "DE", "PSO", "ABO", "ADE", "APSO")
BASE_ARM_OF = {"BO": "BO", "DE": "DE", "PSO": "PSO", "ABO": "BO", "ADE": "DE", "APSO": "PSO"}
ADAPTIVE_ARMS = ("ABO", "ADE", "APSO")
SEED = 42
BUDGET_STARTS = 64
PLANNED_STARTS = len(ARMS) * BUDGET_STARTS
MAX_STARTS = 384
EXPECTED_INTERNAL_CASES = PLANNED_STARTS * INTERNAL_SOLVER_CASES_PER_START
MAX_INTERNAL_CASES = 2688
MAX_REFINE_STARTS = 0
PER_CASE_TIMEOUT_S = 60.0
MAX_WALL_MINUTES = 180
INITIAL_DESIGNS = 3
MAX_EVALUATIONS_FACTOR = 4
WINDOW_START_UTC = "2026-11-10T21:00:00Z"
WINDOW_END_UTC = "2026-11-11T01:00:00Z"
WINDOW_TOKEN = "WINDOW_OK-P2A-20261110T2100Z-20261111T0100Z"
WINDOW_LOCAL_NOTE = "本地 CST 2026-11-11 05:00-09:00；UTC 为唯一权威源。"

#: P2a solver/task configuration: THIN 12x25 tessellation, 7 fixed alphas,
#: NO refine, NO wake-node/iteration overrides (Lead m00591 P2A-07).
P2A_SOLVER_CONFIG: Dict[str, Any] = {
    "solver": "vspaero",
    "version": "7.2.2",
    "openvsp_version": "3.55.0",
    "mach": 2.02,
    "geom_set": "thin",
    "geometry_components": ["main_wing", "vertical_tail"],
    "includes_fuselage": False,
    "sref_policy": "design_dependent_from_geometry",
    "cref_m": 18.489893,
    "bref_m": 25.604638,
    "xcg_m": 16.821978259514246,
    "reference_frame": "WING_AC",
    "reference_area": "main_wing_reference",
    "alpha_primary_deg": [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
    "refine_allowed": False,
    "refine_starts": 0,
    "tess_u": 12.0,
    "tess_w": 25.0,
    "omp_threads": 1,
    "flags": ["-omp", "1"],
    "status": "P2A_THIN_12x25_7ALPHA_ZERO_REFINE",
}
P2A_TASK_VERSION = "p2a-dreal001-thin-v1"

#: P2A-08 conservation: three ledgers, one source of truth, nothing hardcoded
#: (Lead m00591; A5 checklist P2A-08).
CONSERVATION_POLICY: Dict[str, Any] = {
    "ledger_units": {
        "physical_solver_starts": "one vspaero.exe process = 1 start (7 alpha rows inside it)",
        "internal_solver_cases": "7 fixed alpha rows = 7 internal cases per start",
        "evaluations": "one design evaluation per start; alpha rows are NOT separate evaluations",
    },
    "one_start_equals": {"physical_solver_starts": 1, "internal_solver_cases": int(INTERNAL_SOLVER_CASES_PER_START), "evaluations": 1},
    "conservation_relations": [
        "sum(record.physical_solver_starts) == planner.planned_starts on clean completion",
        "sum(record.internal_solver_cases) == 7 * sum(record.physical_solver_starts)",
        "sum(record.evaluations) == sum(record.physical_solver_starts)",
    ],
    "planned_vs_max": {
        "planned_starts": PLANNED_STARTS,
        "max_starts": MAX_STARTS,
        "planned_internal_cases": EXPECTED_INTERNAL_CASES,
        "max_internal_cases": MAX_INTERNAL_CASES,
        "planned_breakdown": {arm: BUDGET_STARTS for arm in ARMS},
        "max_equals_planned": MAX_STARTS == PLANNED_STARTS and MAX_INTERNAL_CASES == EXPECTED_INTERNAL_CASES,
    },
    "refine": {"allowed": False, "planned_refine_starts": 0, "max_refine_starts": MAX_REFINE_STARTS},
    "alpha_rows_are_not_billed": True,
    "billing": "every attempt incl TIMEOUT / EXIT!=0 is 1 physical_solver_start and 7 internal cases",
    "source_of_truth": "A1 append-only solver_attempts.jsonl; start/end pairs and attempt_id are paired per case after the run",
    "computed_at_execution_not_hardcoded": True,
    "historical_support_counted_separately": "15 P1C designs are prior labels, never billed as P2a starts",
    "physical_call_count_a2": 0,
}
AUTHORIZATION = "GitHub Issue #9 [D-REAL-001][12D][宽预算] + Lead P2a 指令 2026-11-10"
FENCE = chr(96) * 3
PREREG_PATH_REL = "docs/dreal001/p2a/PREREGISTRATION.md"
DEFAULT_BATCH_DIR = Path("research/concorde_metaopt/dreal001/runs") / P2A_BATCH_ID

STOP_CONDITIONS: Tuple[Dict[str, str], ...] = (
    {"code": "S1", "trigger": "any case settles TIMEOUT or non-SOLVED beyond the pre-registered lift-match failure rule", "action": "stop the whole batch immediately; no retry; every attempt is billed"},
    {"code": "S1L", "trigger": "three consecutive LIFT_MATCH_FAILED results for one solver configuration", "action": "stop the batch (A1 P2 draft failure rule); no penalty substitution"},
    {"code": "S2", "trigger": "physical_solver_starts used would exceed approval.max_starts", "action": "refuse the launch; stop the batch; incident"},
    {"code": "S3", "trigger": "ledger mismatch (solver_attempts rows != physical_solver_starts, or internal cases > cap)", "action": "stop the batch; A5 audit; no silent repair"},
    {"code": "S4", "trigger": "two consecutive solver failures of the same configuration", "action": "stop the batch; root cause before any restart"},
    {"code": "S5", "trigger": "wall clock > 180 min or outside approval window", "action": "stop the batch"},
    {"code": "S6", "trigger": "STOP file present, git SHA / plan SHA / solver config hash mismatch, or approval missing", "action": "fail closed; refuse to start"},
    {"code": "S7", "trigger": "disk free < 50 GB or canonical-roundtrip build fail-closed for a design (0 starts spent)", "action": "stop the batch; NOT_RUN record"},
)

MESH_POLICY: Dict[str, Any] = {
    "geometry": "main_wing + vertical_stabilizer (no fuselage); result is wing-surface D_i, not full-aircraft drag",
    "geometry_set": "thin",
    "tessellation": {"u": 12.0, "w": 25.0},
    "alpha_list_deg": [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
    "mesh_policy": "canonical_roundtrip_native_family",
    "canonical_roundtrip_path": (
        "x12 -> canonical OpenVSP build -> write .vsp3 -> Clear -> Read -> ComputeGeometry -> .vspgeom; "
        "one deterministic build per design; no target-family search, no modal matching, no retry with a different family"
    ),
    "target_mesh_family": None,
    "no_target_family": True,
    "modal_family_search": "REMOVED: the direct/modal path was rejected by the A1 zero-physical probe (bimodal families, 0.61 reproduction rate, 40% modal agreement)",
    "single_build": True,
    "max_build_attempts_per_design": 1,
    "fail_closed_0_start": True,
    "actual_family_recorded_per_design": True,
    "family_covariate": "actual mesh_family is recorded per design and used as a stratification covariate, never as a numeric cross-family comparator",
    "determinism_evidence": {
        "status": "PENDING_A1_V1_VALIDATION",
        "a1_probe_commit": "",
        "a1_probe_artifact": "",
        "reference": "Lead m00801: A1 zero-physical deterministic probe of the canonical roundtrip path; the direct path (方案A) was rejected",
        "bind_at_final_build": "A1 probe commit/SHA + determinism evidence must be bound before the final plan build",
    },
    "mesh_strategy": "canonical roundtrip -> native family per design (single build)",
    "max_mesh_attempts": 1,
    "fail_closed": True,
    "thick_mesh": "FORBIDDEN in P2a (no thick 48x97)",
    "cross_family_numeric_comparison": "FORBIDDEN; cross-family numeric ranking is NOT_COMPARABLE/NOT_RUN",
    "final_mesh_policy_status": "PENDING_A1_V1_VALIDATION: canonical-roundtrip native-family policy selected by Lead m00801; final build only after A1 EVALUATOR_API v1.2 + p2a_warmstart_support.json + V1 determinism validation pass",
}

#: Endpoint wording (Lead m00801; single seed + cross-family => descriptive only).
ENDPOINT_POLICY: Dict[str, Any] = {
    "E1_anytime_best_D_i": "DESCRIPTIVE_ONLY; per arm and per actual mesh_family; no significance claim",
    "E2_best_D_i_at_B": "DESCRIPTIVE_ONLY; every best value must carry its actual mesh_family label; CROSS_FAMILY_NUMERIC_NOT_COMPARABLE",
    "E3_six_arm_ranking_or_winner": "NOT_COMPARABLE across actual mesh families; NOT_RUN if family labels differ; no total winner",
    "E4_convergence_starts_and_AUC": "DESCRIPTIVE_ONLY",
    "E5_significance_or_overall_winner": "NOT_COMPUTABLE (single seed=42, cross-family families, screening only)",
    "E6_failure_classification_and_feasible_rate": "DESCRIPTIVE_ONLY",
    "cross_family_rule": "numeric comparison across actual mesh families is forbidden; report stratified by family",
    "winner_policy": "NO_TOTAL_WINNER: single seed and cross-family; report direction only",
    "family_label_required": True,
}

WARMSTART_POLICY: Dict[str, Any] = {
    "arms": "A-arms ABO/ADE/APSO use the Issue #8 warm-start sampler (label-free); BO/DE/PSO are cold-start baselines",
    "initial_designs": INITIAL_DESIGNS,
    "initial_designs_rule": "same K=3 initial design count for all six arms; A-arms propose with the sampler, baselines draw with LHS and the same seed",
    "historical_support": "A-arms may use only the 15 already-committed P1C REAL designs (zero new labels, no leakage)",
    "support_loader_status": "PENDING_IMPLEMENTATION_P2A_R1: arms.warmstart_designs exposes only in-run VisibleLabelStore labels; historical-support loader + leakage test required before execution",
    "surrogate_scoring": "label-free, 0 physical starts; predictions are never written into real observations",
}

OBJECTIVE: Dict[str, Any] = {
    "name": "min D_i_N at matched wing lift",
    "D_i_N": "q * Sref(x) * CDi(x, alpha_matched)",
    "L_ref_N": float(L_REF_N),
    "L_ref_formula": "136000 kg * 9.80665 m/s^2",
    "lift_tolerance_rel": float(LIFT_TOL_REL),
    "q_Pa": float(Q_PA_DEFAULT),
    "q_source": "Mach 2.02 / 18288 m ISA",
    "reference_frame": REFERENCE_FRAME,
    "xcg_m": float(XCG_M),
    "xcg_note": "WING_AC reference, not the geometric full-aircraft CG (28.287395109126685 m)",
    "mass_note": "136000 kg single-cruise entry mass; 184880 kg geometric MTOW not used",
    "fuel_burn_kg": None,
    "physical_validation_status": "NOT_VALIDATED",
}


def _git_head(cwd: Optional[Path] = None) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=None if cwd is None else str(cwd), capture_output=True, text=True, check=False)
        return out.stdout.strip()
    except Exception:
        return ""


def _sha_of_json(payload: Any) -> str:
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return str(path)


def _worktree_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _a1_root_default() -> Path:
    env = os.environ.get("DREAL001_A1_ROOT")
    if env:
        return Path(env)
    return _worktree_root().parent / "wt-real-a1-geometry-solver"


def build_run_matrix() -> List[Dict[str, Any]]:
    runs: List[Dict[str, Any]] = []
    for arm in ARMS:
        runs.append({
            "run_id": "%s-%s-B%d-s%d" % (P2A_BATCH_ID, arm, BUDGET_STARTS, SEED),
            "arm_id": arm,
            "base_arm": BASE_ARM_OF[arm],
            "warmstart": arm in ADAPTIVE_ARMS,
            "budget_starts": BUDGET_STARTS,
            "max_starts": BUDGET_STARTS,
            "seed": SEED,
            "backend": BACKEND_REAL,
            "initial_designs": INITIAL_DESIGNS,
        })
    return runs


def _case_row(run: Mapping[str, Any], index: int) -> Dict[str, Any]:
    run_id = str(run["run_id"])
    slot = index + 1
    return {
        "case_slot_id": "%s-c%04d" % (run_id, slot),
        "case_id_template": "%s-c%04d-<design_hash8>" % (run_id, slot),
        "case_id_resolved_at": "execution",
        "run_id": run_id,
        "arm_id": str(run["arm_id"]),
        "seed": int(run["seed"]),
        "budget_slot": slot,
        "design_source": ("A_WARM_START" if run.get("warmstart") else "COLD_START"),
        "design_binding": "design_hash = sha256(canonical x12)[:16] at execution",
        "expected_starts": 1,
        "max_starts": 1,
        "expected_internal_cases": int(INTERNAL_SOLVER_CASES_PER_START),
        "internal_case_breakdown": {
            "mach_list": [2.02],
            "alpha_list_deg": [float(v) for v in ALPHA_PRIMARY_DEG],
            "beta_list_deg": [0.0],
            "counts": {"mach": 1, "alpha": len(ALPHA_PRIMARY_DEG), "beta": 1},
        },
        "timeout_seconds": float(PER_CASE_TIMEOUT_S),
        "refine_allowed": False,
        "preflight_required": True,
        "mesh_target_family": None,
        "mesh_policy": MESH_POLICY["mesh_policy"],
        "actual_family_recorded_at_execution": True,
        "physical_solver_starts_at_plan_time": 0,
    }


def build_case_matrix(run_matrix: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for run in run_matrix:
        for index in range(int(run["budget_starts"])):
            cases.append(_case_row(run, index))
    return cases


PROJECTED_FIELDS = (
    "case_slot_id", "run_id", "arm_id", "seed", "budget_slot",
    "expected_starts", "expected_internal_cases", "design_source", "timeout_seconds",
)


def case_matrix_digest(cases: Sequence[Mapping[str, Any]], fields: Sequence[str] = PROJECTED_FIELDS) -> str:
    return _sha_of_json([{field: row.get(field) for field in fields} for row in cases])


SUPPORT_SCHEMA_REQUIREMENT: Dict[str, Any] = {
    "schema": "dreal001.p2a_warmstart_support.v1",
    "required_top_level": ["schema", "records"],
    "recommended_top_level": ["batch_id", "task_spec_sha256", "solver_config_sha256", "source_batch_ids", "n_used", "exclusion_reasons"],
    "target_mesh_family_field": "optional: canonical-roundtrip policy records the actual native family per record; a single fixed target family is no longer required",
    "required_record_fields": ["design (12 physical x12)", "design_hash (sha256(canonical x12)[:16])", "native_family", "D_i_N", "source_record_sha"],
    "recommended_record_fields": ["source_run_id", "source_batch_id", "solver_status", "mesh_family", "solver_config_sha256", "same_family"],
    "expected_designs": SUPPORT_EXPECTED_DESIGNS,
    "rules": [
        "read-only; no append/backfill during the P2a run",
        "no test/target/future/query labels and no predictions may appear",
        "the raw byte SHA256 is bound in plan/approval/identity_binding",
        "the 15 historical designs are counted separately from the 384 P2a starts",
    ],
}


def _support_path(a1_root: Path, support_path: Optional[Any]) -> Optional[Path]:
    explicit = support_path if support_path is not None else os.environ.get("DREAL001_P2A_SUPPORT")
    if explicit:
        candidate = Path(str(explicit))
        return candidate if candidate.is_absolute() else (_worktree_root() / candidate)
    for candidate in support_candidates(a1_root):
        if candidate.is_file():
            return candidate
    return None


def support_binding(
    a1_root: Optional[Path] = None,
    support_path: Optional[Any] = None,
    *,
    expected_support_sha256: Optional[str] = None,
    expected_task_spec_sha256: Optional[str] = None,
    expected_solver_config_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    root = _a1_root_default() if a1_root is None else Path(a1_root)
    geometry_root = root / "research" / "concorde_metaopt" / "dreal001" / "geometry"
    legacy = {
        "P1C": geometry_root / "runs" / "DREAL001-P1C-20261110-01" / "evaluations.jsonl",
        "P1R": geometry_root / "runs" / "DREAL001-P1R-20261110-01" / "evaluations.jsonl",
    }
    files: List[Dict[str, Any]] = []
    for label, legacy_path in legacy.items():
        if legacy_path.exists():
            files.append({"label": label, "path": _rel(legacy_path, _worktree_root()), "sha256": sha256_file(legacy_path), "bytes": int(legacy_path.stat().st_size)})
    target = _support_path(root, support_path)
    disclosures = [
        "The 15 committed P1C designs are the ONLY external observed_support for A-arms; no new physical labels are bought.",
        "V01/V02 sensitivity is NOT_VALIDATED; the A-arm support may be effectively 10D-active.",
        "P1C/P1R results are cross-family; cross-family numeric comparison is forbidden, so support labels are a weak prior only.",
        "A-arm labels are visible only to A-arms; VisibleLabelStore is per run_id and the cross-run cache is pre-registered/forbidden for REAL reuse.",
    ]
    if target is None:
        n_legacy = 0
        if legacy["P1C"].exists():
            try:
                rows = [json.loads(line) for line in legacy["P1C"].read_text(encoding="utf-8").splitlines() if line.strip()]
                n_legacy = len({str(row.get("design_hash", "")) for row in rows if row.get("design_hash")})
            except Exception:
                n_legacy = 0
        return {
            "status": "PENDING_A1_ARTIFACT",
            "path": "",
            "sha256": "",
            "n_designs": int(n_legacy),
            "expected_designs": SUPPORT_EXPECTED_DESIGNS,
            "schema_requirement": SUPPORT_SCHEMA_REQUIREMENT,
            "search_paths": [_rel(candidate, _worktree_root()) for candidate in support_candidates(root)],
            "legacy_p1c": {"path": _rel(legacy["P1C"], _worktree_root()) if legacy["P1C"].exists() else str(legacy["P1C"]), "sha256": sha256_file(legacy["P1C"]) if legacy["P1C"].exists() else "", "n_designs": n_legacy},
            "source_kind": "REAL_VSPAERO",
            "batch_labels": ["DREAL001-P1C-20261110-01", "DREAL001-P1R-20261110-01"],
            "zero_new_labels": True,
            "files": files,
            "disclosures": disclosures + ["P2A-R1 loader is implemented; A1 has not yet delivered p2a_warmstart_support.json, so the plan is NOT executable."],
        }
    try:
        support = load_warmstart_support(
            target,
            expected_sha256=expected_support_sha256,
            expected_designs=SUPPORT_EXPECTED_DESIGNS,
            expected_task_spec_sha256=expected_task_spec_sha256,
            expected_solver_config_sha256=expected_solver_config_sha256,
        )
    except WarmStartSupportError as exc:
        return {
            "status": "INVALID_A1_ARTIFACT",
            "path": _rel(target, _worktree_root()),
            "sha256": sha256_file(target) if target.is_file() else "",
            "error": str(exc),
            "schema_requirement": SUPPORT_SCHEMA_REQUIREMENT,
            "files": files,
            "disclosures": disclosures,
        }
    payload = support.to_dict()
    payload.update(
        {
            "status": "BOUND",
            "path": _rel(target, _worktree_root()),
            "source_kind": "REAL_VSPAERO",
            "schema_requirement": SUPPORT_SCHEMA_REQUIREMENT,
            "files": files,
            "disclosures": disclosures,
            "support_append_during_run": False,
            "cache_used": False,
            "counted_separately_from_p2a_starts": True,
        }
    )
    return payload


def evaluator_binding(a1_root: Optional[Path] = None, production_template_path: Optional[str] = None) -> Dict[str, Any]:
    root = _a1_root_default() if a1_root is None else Path(a1_root)
    geometry_root = root / "research" / "concorde_metaopt" / "dreal001" / "geometry"
    evaluator_path = geometry_root / "evaluator.py"
    contract_path = geometry_root / "p2a_contract.py"
    api_path = geometry_root / "EVALUATOR_API.md"
    api_text = api_path.read_text(encoding="utf-8") if api_path.exists() else ""
    detected = "v1.1" if "v1.1" in api_text else ("v1.0" if "v1.0" in api_text else "UNKNOWN")
    code = a1_code_binding(root)
    contract_text = contract_path.read_text(encoding="utf-8") if contract_path.exists() else ""
    thin_bound = all(token in contract_text for token in ('geometry_set: str = "thin"', "tess_u: float = 12.0", "tess_w: float = 25.0"))
    return {
        "module": "research.concorde_metaopt.dreal001.geometry.evaluator",
        "class": "AeroEvaluator",
        "record_schema": "dreal001.aero_eval.v1",
        "api_version_detected_in_a1_tree": detected,
        "api_version_requested": "v1.1",
        "status": "EVALUATOR_PENDING_A1_V1_1" if production_template_path is None else "EVALUATOR_V1_1_TEMPLATE_BOUND",
        "evaluator_source_path": _rel(evaluator_path, _worktree_root()) if evaluator_path.exists() else str(evaluator_path),
        "evaluator_source_sha256": sha256_file(evaluator_path) if evaluator_path.exists() else "",
        "p2a_contract_path": _rel(contract_path, _worktree_root()) if contract_path.exists() else str(contract_path),
        "p2a_contract_sha256": sha256_file(contract_path) if contract_path.exists() else "",
        "p2a_contract_thin_12x25_bound": bool(thin_bound),
        "api_doc_path": _rel(api_path, _worktree_root()) if api_path.exists() else str(api_path),
        "api_doc_sha256": sha256_file(api_path) if api_path.exists() else "",
        "a1_code_files": code["files"],
        "production_template_path": production_template_path,
        "physical_call_count_in_a2": 0,
        "a2_never_launches_solver": True,
    }


def _identity_block(*, plan_rel: str, prereg_path: str, prereg_sha: str, task: Any, evaluator: Mapping[str, Any], support: Mapping[str, Any], a1_task: Mapping[str, Any], frozen_space: Mapping[str, Any], case_digest: str, case_full_digest: str) -> Dict[str, Any]:
    l_ref = {
        "value_N": float(task.lift_reference_N),
        "formula": "136000 kg * 9.80665",
        "reference_mass_kg": 136000.0,
        "g0_m_s2": 9.80665,
        "lift_tol_rel": float(task.lift_tol_rel),
        "q_Pa": float(task.q_Pa),
        "reference_frame": str(task.reference_frame),
    }
    return {
        "rule": "plan/prereg/evaluator/L_ref/task_spec/solver_config jointly bound; approval binds sha256(plan.json raw bytes) + case_matrix_digest",
        "plan_sha256": None,
        "plan_sha256_note": "self-referential; raw SHA256 of plan.json is recorded in approval.DRAFT.json and SHA256SUMS.txt",
        "plan_path": plan_rel,
        "preregistration": {"path": prereg_path, "sha256": prereg_sha, "status": "BOUND" if prereg_sha else "PENDING"},
        "evaluator": dict(evaluator),
        "task_spec": {
            "module": "research.concorde_metaopt.dreal001.optimizers.task",
            "task_id": task.task_id,
            "version": task.version,
            "fingerprint": task.fingerprint(),
            "canonical_to_dict_sha256": _sha_of_json(task.to_dict()),
            "thin_12x25_7alpha": True,
            "legacy_keys_present": legacy_solver_config_keys(task.solver_config),
        },
        "a1_task_spec": dict(a1_task),
        "frozen_design_space": dict(frozen_space),
        "l_ref": dict(l_ref, canonical_sha256=_sha_of_json(l_ref)),
        "solver_config": {
            "sha256": task.solver_config_sha256,
            "solver": "VSPAERO 7.2.2",
            "openvsp": "3.55.0",
            "omp_threads": 1,
            "argv_template": ["<OPENVSP_ROOT>/vspaero.exe", "-omp", "1", "<basename>"],
            "forbidden_flags": ["-fs", "-mach", "-alpha", "-beta"],
        },
        "geometry_reconstructor": {
            "source": "A1 canonical x12 -> OpenVSP geometry path",
            "a1_module": "research.concorde_metaopt.dreal001.geometry",
            "status": "PENDING_A1_PRODUCTION_TEMPLATE" if evaluator.get("production_template_path") is None else "BOUND",
        },
        "support": dict(support),
        "case_matrix_digest": case_digest,
        "case_matrix_digest_full_canonical": case_full_digest,
        "digest_scope": (
            "case_matrix_digest = sha256(canonical JSON of 384 projected case slots over fields %s; design_hash/x12 resolved at execution); "
            "case_matrix_digest_full_canonical = sha256(canonical JSON of the complete 384 declared rows; "
            "the runtime case matrix with resolved case_id/design_hash/x12 is emitted as case_matrix_runtime.json after a run and is not a pre-approval gate"
        ) % (list(PROJECTED_FIELDS),),
    }


def build_plan(*, batch_dir: Path = DEFAULT_BATCH_DIR, a1_root: Optional[Path] = None, support_path: Optional[Any] = None, production_template_path: Optional[str] = None, git_sha: str = "", prereg_path: str = PREREG_PATH_REL, prereg_sha: str = "") -> Dict[str, Any]:
    worktree = _worktree_root()
    # P2A-07: THIN 12x25/7-alpha/no-refine task, NOT the legacy thick default.
    task = build_task(
        task_id="concorde_fixed_cruise_12d",
        version=P2A_TASK_VERSION,
        description="D-REAL-001 P2a thin-wing VSPAERO lift-matched induced-drag minimisation (7 fixed alpha, no refine)",
        solver_config=dict(P2A_SOLVER_CONFIG),
        alpha_refine_deg=(),
        max_refine_sweeps=0,
        max_launches_per_design=1,
        source_kind=BACKEND_REAL,
    )
    # build_task back-fills alpha_refine_deg/max_refine_sweeps into solver_config;
    # P2a forbids both, so strip them and rebind the config hash to the sanitized dict.
    sanitized_config = {
        key: value
        for key, value in dict(task.solver_config).items()
        if key not in ("alpha_refine_deg", "max_refine_sweeps")
    }
    task = task.with_solver_config(sanitized_config)
    runs = build_run_matrix()
    cases = build_case_matrix(runs)
    projected = case_matrix_digest(cases)
    full_canonical = _sha_of_json(cases)
    evaluator = evaluator_binding(a1_root, production_template_path)
    a1_task = a1_task_spec_binding(a1_root) if a1_root is not None else a1_task_spec_binding(_a1_root_default())
    frozen_space = frozen_design_space_binding(a1_root) if a1_root is not None else frozen_design_space_binding(_a1_root_default())
    support_expected_task = a1_task.get("canonical_sha256") or None
    support = support_binding(
        a1_root,
        support_path,
        expected_task_spec_sha256=support_expected_task,
        expected_solver_config_sha256=task.solver_config_sha256,
    )
    budget = {
        "budget_metric": "physical_solver_starts",
        "planned_starts": PLANNED_STARTS,
        "max_starts": MAX_STARTS,
        "planned_internal_cases": EXPECTED_INTERNAL_CASES,
        "max_internal_cases": MAX_INTERNAL_CASES,
        "expected_internal_cases": EXPECTED_INTERNAL_CASES,
        "internal_solver_cases_per_start": int(INTERNAL_SOLVER_CASES_PER_START),
        "starts_per_design_expected": 1,
        "max_starts_per_design": int(MAX_STARTS_PER_DESIGN),
        "max_refine_starts": MAX_REFINE_STARTS,
        "refine_policy": "NO_REFINE: P2a forbids refine launches; a lift-mismatch is classified, not retried",
        "alpha_rows_are_not_billed": True,
        "planned_breakdown": {arm: BUDGET_STARTS for arm in ARMS},
    }
    timeouts = {
        "per_case_seconds": float(PER_CASE_TIMEOUT_S),
        "timeout_overrides": {},
        "batch_wall_minutes": int(MAX_WALL_MINUTES),
        "timeout_policy": "any TIMEOUT stops the whole batch per S1; infra_retries_allowed=0; the timed-out attempt is still billed",
    }
    plan: Dict[str, Any] = {
        "schema": P2A_PLAN_SCHEMA,
        "schema_version": P2A_PLAN_SCHEMA,
        "batch_id": P2A_BATCH_ID,
        "canonical_batch_id": P2A_BATCH_ID,
        "batch_id_naming_exception": "",
        "phase": "P2",
        "purpose": "P2a real six-arm optimizer pilot: single-seed (42) screening at B=64 starts per arm; descriptive only, no significance claim",
        "layer_claim": "SOLVER_LOOP_VERIFIED candidate; INTERNAL_AERO_OPTIMIZATION_GAIN descriptive only; EXTERNAL_PHYSICS_SUPPORTED NOT_CLAIMED",
        "backend": BACKEND_REAL,
        "created_ts_utc": utc_now(),
        "git_sha": str(git_sha or _git_head(worktree)),
        "authorization": AUTHORIZATION,
        "task_id": task.task_id,
        "task_version": task.version,
        "task_fingerprint": task.fingerprint(),
        "task": task.to_dict(),
        "a1_task_spec": dict(a1_task),
        "frozen_design_space": dict(frozen_space),
        "conservation": dict(CONSERVATION_POLICY),
        "solver_config": dict(task.solver_config),
        "solver_config_sha256": task.solver_config_sha256,
        "solver_config_legacy_keys": legacy_solver_config_keys(task.solver_config),
        "objective": dict(OBJECTIVE),
        "l_ref": dict(OBJECTIVE),
        "design_space_path": "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
        "design_space_config_id": "design_space_12d_lifting_surfaces",
        "dimension": DIMENSION,
        "arms": list(ARMS),
        "seeds": [SEED],
        "budget_B": BUDGET_STARTS,
        "planned_starts": PLANNED_STARTS,
        "planned_starts_per_arm": {arm: BUDGET_STARTS for arm in ARMS},
        "initial_designs": INITIAL_DESIGNS,
        "max_evaluations_factor": MAX_EVALUATIONS_FACTOR,
        "warmstart": {"source": "zero_shot_surrogate", "support_size": 15, "candidate_pool_size": 256, "seed": 42, "policy": dict(WARMSTART_POLICY), "historical_support_status": support.get("status")},
        "warmstart_policy": dict(WARMSTART_POLICY),
        "warmstart_support_status": support.get("status"),
        "budget": budget,
        "budget_metric": "physical_solver_starts",
        "budget_model": budget,
        "timeouts": timeouts,
        "timeout_seconds_per_case": float(PER_CASE_TIMEOUT_S),
        "retry_policy": {
            "automatic_numeric_retry": False,
            "infra_retries_allowed": 0,
            "infra_retry_condition": "NONE: any non-SOLVED result stops the batch per S1",
            "timeout_retry": "NO_RETRY_S1_STOP",
            "refine_allowed": False,
            "billing": "every attempt incl TIMEOUT/EXIT!=0 is 1 physical_solver_start and 7 internal cases",
        },
        "concurrency": {"processes": 1, "omp_threads_per_process": 1, "parallelism": "1x1"},
        "limits": {
            "max_wall_minutes": MAX_WALL_MINUTES,
            "max_starts": MAX_STARTS,
            "max_internal_cases": MAX_INTERNAL_CASES,
            "max_refine_starts": MAX_REFINE_STARTS,
            "expected_disk_bytes": PLANNED_STARTS * 7_500_000,
            "max_disk_bytes": PLANNED_STARTS * 9_000_000,
            "min_free_disk_gb": 50,
        },
        "mesh_policy": dict(MESH_POLICY),
        "mesh_target_family": None,
        "endpoint_policy": dict(ENDPOINT_POLICY),
        "fairness": {
            "budget_metric": "physical_solver_starts",
            "budget_per_arm": BUDGET_STARTS,
            "same_task": True,
            "same_mesh_policy": True,
            "same_timeout": True,
            "same_initial_design_count": INITIAL_DESIGNS,
            "same_seed": SEED,
            "baseline_cold_start": True,
            "a_arm_historical_support": "15 committed P1C REAL designs only; zero new labels",
            "a_arm_extra_surrogate_cost": "0 physical starts; reported separately",
        },
        "stop_conditions": [dict(item) for item in STOP_CONDITIONS],
        "stop_conditions_text": ["%s: %s -> %s" % (i["code"], i["trigger"], i["action"]) for i in STOP_CONDITIONS],
        "case_count": len(cases),
        "starts_total": PLANNED_STARTS,
        "internal_cases_total": EXPECTED_INTERNAL_CASES,
        "run_matrix": runs,
        "run_matrix_sha256": _sha_of_json(runs),
        "case_matrix": cases,
        "case_matrix_digest": projected,
        "case_matrix_digest_full_canonical": full_canonical,
        "digest_scope": (
            "case_matrix_digest covers ONLY the projected case-slot fields %s (sha256 of their canonical JSON); "
            "design_hash/x12 are resolved at execution and are NOT in this digest. "
            "case_matrix_digest_full_canonical covers the complete 384 declared rows in plan.case_matrix "
            "(sha256 of canonical JSON). Both values are bound in plan and approval.DRAFT; "
            "the runtime case matrix with resolved case_id/design_hash/x12 is emitted as case_matrix_runtime.json after a run "
            "and is not a pre-approval gate."
        ) % (list(PROJECTED_FIELDS),),
        "preregistration": {"path": prereg_path, "sha256": prereg_sha, "version": "P2A-PREREG-v1", "status": "BOUND" if prereg_sha else "PENDING"},
        "physical_solver_starts": 0,
        "solver_started": False,
        "approval": {"required": True, "approved": False, "draft_path": "approval.DRAFT.json", "note": "REAL refused until Lead signs approval.json; A5 PASS precedes the signature"},
        "phase_status": {
            "P0": "PASS",
            "P1R": "INCOMPLETE_S1_STOPPED_WITH_PROTOCOL_DEVIATION",
            "P1C": "SOLVER_INTERNAL_PASS_CONTINUATION (A5 signed)",
            "P1_overall": "UNSIGNED",
            "P2": "NOT_AUTHORIZED before A5 PASS + Lead approval",
            "12D_ACTIVE": "NOT_VALIDATED (A5 P1C verdict; V01/V02 may be inactive)",
        },
        "disclosures": [
            "Single seed=42: descriptive screening only; no significance, confidence interval or power claim.",
            "P1R stopped at S1 after two TIMEOUTs; D-P1R-TIMEOUT-RETRY is disclosed and must not repeat: P2a has infra_retries_allowed=0 and TIMEOUT->S1.",
            "V01/V02 sensitivity NOT_VALIDATED; P2a may be effectively 10D-active.",
            "Mesh families differ across P1 batches; cross-family numeric comparison is forbidden; mesh_family is a covariate.",
            "A-arm historical support (15 P1C designs) is real but cross-family and V01/V02-uncertain; weak prior only.",
            "fuel_burn_kg=null; VSPAERO internal CDi is not a fuel-burn claim; LF-M2.02=NOT_VALIDATED and BODY-CORR=BLOCKED.",
            "A2 never launches vspaero.exe; physical starts require A1 ledgered spawn + signed approval.",
        ],
        "references": [
            "docs/planning/dreal001_vspaero_large_scale_optimization_20261110.md",
            "docs/planning/dreal001_execution_governance_20261110.md",
            "GitHub Issue #9 [D-REAL-001][12D][宽预算]",
            "A1 EVALUATOR_API (v1.0 observed; v1.1 requested)",
        ],
        "fuel_burn_kg": None,
        "notes": "P2a pre-registration only; zero physical starts; " + ("A1 EVALUATOR_API v1.1 + production template bound (only the path is referenced, never copied)." if evaluator.get("status") == "EVALUATOR_V1_1_TEMPLATE_BOUND" else "EVALUATOR_PENDING_A1_V1_1 until A1 v1.1 + production template are bound."),
    }
    plan["identity_binding"] = _identity_block(
        plan_rel=_rel(batch_dir / "plan.json", worktree),
        prereg_path=prereg_path,
        prereg_sha=prereg_sha,
        task=task,
        evaluator=evaluator,
        support=support,
        a1_task=a1_task,
        frozen_space=frozen_space,
        case_digest=projected,
        case_full_digest=full_canonical,
    )
    return plan


def render_preregistration(plan: Mapping[str, Any]) -> str:
    lines = [
        "# D-REAL-001 P2a 预注册（真实六臂优化 pilot，单 seed 筛选）",
        "",
        "- 版本：P2A-PREREG-v1（草案，待 A5 复核 + Lead 批准）",
        "- 批次：" + plan["batch_id"] + "（canonical_batch_id 同值，无命名例外）",
        "- 阶段：P2（工程/早期样本效率 pilot，不是 P3 规模化证据）",
        "- 授权：" + plan["authorization"],
        "- 基线 commit：" + (plan.get("git_sha") or ""),
        "- 本文件编写时真实 VSPAERO 启动：0（A2 physical_call_count=0）",
        "",
        "## 1. 目的与结论边界",
        "",
        "P2a 在 A1 真实升力匹配评价器上用同一物理预算比较六臂 BO/DE/PSO/ABO/ADE/APSO 的早期样本效率。单 seed=42、B=64：只输出描述性指标（AUC、best D_i、收敛 starts、可行率、失败分类），不作显著性声明；P2b 才扩到 ≥3 seeds。",
        "",
        "三层结论：SOLVER_LOOP_VERIFIED 为候选；INTERNAL_AERO_OPTIMIZATION_GAIN 仅描述性；EXTERNAL_PHYSICS_SUPPORTED=NOT_CLAIMED；fuel_burn_kg=null；LF-M2.02=NOT_VALIDATED、BODY-CORR=BLOCKED。",
        "",
        "阶段状态（不得改写）：P0=PASS；P1R=INCOMPLETE_S1_STOPPED_WITH_PROTOCOL_DEVIATION；P1C=SOLVER_INTERNAL_PASS_CONTINUATION（A5 签）；P1 整体=UNSIGNED；P2=未授权；12D_ACTIVE=NOT_VALIDATED。",
        "",
        "## 2. 批次矩阵与物理预算",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        "| 臂 | BO / DE / PSO / ABO / ADE / APSO（六臂） |",
        "| seed | 42（单 seed） |",
        "| 每臂 B | %d physical_solver_starts |" % BUDGET_STARTS,
        "| run 数 | 6（每臂 1 run） |",
        "| planned / max starts | %d / %d |" % (PLANNED_STARTS, MAX_STARTS),
        "| 每 start internal cases | %d |" % INTERNAL_SOLVER_CASES_PER_START,
        "| planned / max internal | %d / %d |" % (EXPECTED_INTERNAL_CASES, MAX_INTERNAL_CASES),
        "| refine starts | 0 |",
        "| 单 case timeout | %.0f s，无 overrides |" % PER_CASE_TIMEOUT_S,
        "| 批墙钟上限 | %d min |" % MAX_WALL_MINUTES,
        "| 并发 | 1 进程 × 1 OMP 线程 |",
        "| 窗口（UTC 权威） | %s – %s |" % (WINDOW_START_UTC, WINDOW_END_UTC),
        "| window token | " + WINDOW_TOKEN + " |",
        "",
        "run_id 按治理 §3：" + plan["batch_id"] + "-BO-B64-s42 等；case_id 执行时解析为 <run_id>-c<index4>-<design_hash8>。",
        "",
        "## 3. 公平性定义",
        "",
        "- 主预算 physical_solver_starts；六臂同 B=64、同 TaskSpec、同 seed、同 mesh、同 timeout。",
        "- 六臂初始设计数一致 K=3：A 臂 sampler 产生（label-free，0 物理启动），基线臂同 seed LHS；不得给 A 臂额外真实标签。",
        "- A 臂仅可用 P1C/P1R 已提交的 15 个真实设计（零新增标签）；基线臂冷启动无历史标签。",
        "- 代理/采样成本单列，不计入 B；预测不写回真实观测；缓存命中记 cached_reads 不替代预算。",
        "",
        "## 4. A 臂历史支持边界",
        "",
        "- 来源：" + (plan["identity_binding"]["support"].get("path") or "PENDING_A1_ARTIFACT") + "（%d 个 design_hash；期望 15）。" % plan["identity_binding"]["support"]["n_designs"],
        "- 加载状态：" + str(plan.get("warmstart_support_status")) + "（P2A-R1 loader；工件 schema=" + SUPPORT_SCHEMA_REQUIREMENT["schema"] + "）。",
        "- 只读、SHA 绑定、运行中不追加/不回填；只用于 warm-start 先验/校准；零新增真实启动；15 个历史设计不与 384 starts 混计。",
        "- 加载器校验：15 条记录、逐条 design_hash 复算、raw byte SHA256、schema 白名单（无 test/target/future/query/prediction 列）；A1 工件另带 n_used 与 exclusion_reasons，任何被排除的设计不得回填。",
        "- V01/V02 仍 NOT_VALIDATED，支持集可能 10D-active；P1C/P1R 跨族，支持标签只作弱先验，不得跨族排序。",
        "- 泄漏边界：历史支持只有 A 臂可见；基线臂冷启动；VisibleLabelStore 按 run_id 隔离；禁止跨 run 复用 REAL 结果。",
        "",
        "## 5. 目标函数与任务",
        "",
        "- min D_i_N = q · Sref(x) · CDi(x, α_matched)，同升力匹配。",
        "- L_ref = %.1f N = 136000 kg × 9.80665；q = %.12g Pa；升力相对容差 ≤ %.3g。" % (L_REF_N, Q_PA_DEFAULT, LIFT_TOL_REL),
        "- 参考系 WING_AC，X_cg = %.12f m（机翼 AC，非全机 CG 28.287395109126685 m）。" % XCG_M,
        "- 主翼+垂尾，不含机身；D_i 是翼面内部诱导阻力，非全机阻力。",
        "- 136000 kg 为单巡航进入质量；184880 kg 几何 MTOW 不作 L_ref。",
        "- 固定 α：" + str([float(v) for v in ALPHA_PRIMARY_DEG]) + "；禁止自适应 α 与 refine。",
        "- 固定 Mach/β 2.02/0.0；1 进程 = 1 start = 7 internal cases。",
        "- P2A-07 绑定：thin 几何集、tess 12×25、7 个固定 α、refine=0；旧 thick/20×20/wake32/rho/Vinf 字段已移除，legacy key 检查为空。",
        "- TaskSpec 绑定：A1 v1.2 task_spec.py raw SHA256 + canonical TASK_SPEC.to_dict() SHA256；A2 TaskSpec fingerprint 同列。",
        "- 网格口径：canonical roundtrip 得到的实际 native family 逐设计记录；D_i 只在该 family 内解释，跨族数值不可比。",
        "",
        "## 5b. 记账守恒口径（P2A-08）",
        "",
        "- 三口径：physical_solver_starts（1 进程 = 1）／internal_solver_cases（7 个 α = 7）／evaluations（每次 start 1 个设计评价）。",
        "- 守恒关系：Σstarts=planned；Σinternal=7×Σstarts；Σevaluations=Σstarts；由 A1 append-only solver_attempts.jsonl 计算，执行时生成，不得硬编码。",
        "- planned vs max：starts 384/384；internal 2688/2688；refine 0/0；六臂各 64。",
        "- TIMEOUT/EXIT≠0 同样计 1 start + 7 internal；α 行不计费；历史 15 设计不计入 P2a 预算。",
        "",
        "## 5c. 端点口径（Lead m00801）",
        "",
        "- E1 anytime best D_i：DESCRIPTIVE_ONLY（按臂、按实际 family 分层）。",
        "- E2 best D_i（B=64）：DESCRIPTIVE_ONLY；每个 best 必带 actual mesh_family 标签；CROSS_FAMILY_NUMERIC_NOT_COMPARABLE。",
        "- E3 六臂排序/winner：跨 family NOT_COMPARABLE；family 标签不同则 NOT_RUN；不产生总 winner。",
        "- E4 收敛 starts / AUC：DESCRIPTIVE_ONLY。",
        "- E5 显著性/总体 winner：NOT_COMPUTABLE（单 seed 42 + 跨族，仅筛查）。",
        "- E6 失败分类/可行率：DESCRIPTIVE_ONLY；缺失一律 NOT_RUN。",
        "",
        "## 6. Mesh 策略（canonical roundtrip，Lead m00801 裁定）",
        "",
        "- 政策：mesh_policy=canonical_roundtrip_native_family；thin 几何集 + tess 12×25；七固定 α；refine=0。",
        "- 路径：x12 → canonical OpenVSP 构建 → 写 .vsp3 → Clear → Read → ComputeGeometry → .vspgeom；每设计单次构建、不追目标族、不做 modal 匹配、不换族重试。",
        "- 不设目标族：fixed-family 543/472 与 direct/modal 路径已否决（A1 零物理探针：双峰族、复现率 0.61、modal 一致率 40%）。",
        "- fail-closed：构建失败 → 0 starts → NOT_RUN/S7 停批；单次构建上限 1 次。",
        "- 确定性证据：引用 A1 canonical roundtrip 零物理探针的 commit/SHA 与复现率/一致率；该字段 status=PENDING_A1_V1_VALIDATION，最终 build 前必须绑定。",
        "- 协变量与口径：逐设计记录 actual mesh_family/nodes/elements/vspgeom_sha256/canonical_mesh_sha256；family 仅作分层协变量，跨族数值比较禁止（NOT_COMPARABLE）。",
        "- 结论口径：E1/E2/E4/E6 描述性；E3 NOT_COMPARABLE/NOT_RUN；E5 NOT_COMPUTABLE；不做总体 winner（单 seed 已 DESCRIPTIVE_ONLY）。",
        "- 禁止 thick 48x97；P1R TIMEOUT 配置不复用。"
        "",
        "## 7. 超时、重试与停机条件（S1–S7）",
        "",
        "- 单 case timeout %.0f s，无 overrides；TIMEOUT/EXIT≠0/无 polar → S1 立即停批。" % PER_CASE_TIMEOUT_S,
        "- 无自动重试、infra_retries_allowed=0，覆盖 P1R 的至多 1 次 infra retry；TIMEOUT 也计 1 start。",
        "- 同配置连续 3 次 LIFT_MATCH_FAILED → S1L；同配置连续 2 次 solver failure → S4。",
        "- canonical roundtrip 构建失败（0 starts）→ S7 fail-closed / NOT_RUN；不得换族重试或改用 fixed-family。",
        "- 预算越界/台账不符 → S2/S3；wall>180 min 或窗口外 → S5；SHA/git/approval 不符 → S6；磁盘<50 GB 或 mesh fail-closed → S7。",
        "",
        "停机条件（与 plan.json 一致）：",
    ]
    for item in STOP_CONDITIONS:
        lines.append("- " + item["code"] + "：" + item["trigger"] + " → " + item["action"])
    lines += [
        "",
        "## 8. 失败分类与 NOT_RUN",
        "",
        "SOLVED_VALID / SOLVER_FAILED / TIMEOUT / GEOMETRY_INVALID / LIFT_MATCH_FAILED / MESH_FAMILY_FAIL_CLOSED / NOT_RUN / BUDGET_REFUSED。",
        "- 缺失数据一律 NOT_RUN，不得默认 PASS；不得用惩罚数值伪造目标。",
        "- 失败/超时同样写 solver_attempts 并计预算；partial polar 不作科学证据。",
        "- 停机批次按 FAIL/NOT_RUN 归档，不签 PASS；失败 run 投影指标标 NOT_VALIDATED 且禁止引用。",
        "",
        "## 9. 统计立场（单 seed）",
        "",
        "- 指标：anytime best D_i（按 starts 归一）、first/best start、收敛 starts、valid/失败率、AUC，均描述性。",
        "- 单 seed 只报点估计与同预算配对差，不报 p 值/置信区间/显著优于。",
        "- 不因结果增删 seed、不改 B；P2b 的 3 seeds 另立批次。",
        "",
        "## 10. 与 P2b/P3 的区别",
        "",
        "- P2a：单 seed、B=64 工程筛选，检查真实链路与方向性。",
        "- P2b：≥3 seeds 描述性扩展；P3：B=128/256/512、≥5 seeds 规模化比较。",
        "- P2a 的 A 臂优势不得升级为阶段结论，须 P2b/P3 + A5 复核。",
        "",
        "## 11. 审批链与执行前置",
        "",
        "1. A5 预审 prereg + plan + approval.DRAFT（零物理）。",
        "2. Lead 书面批准并写 approval.json（approved=true、approved_by=lead、plan_sha256、case_matrix_digest、digest_scope、window token）。",
        "3. 执行前：A1 v1.1 + production 模板绑定（identity_binding.bindings.a1_task_spec / evaluator 已绑定 SHA）；P2A-R1 支持加载器 + 泄漏测试完成（dry_run.warmstart_support_bound=PASS）；dry-run PASS（含 A1/A2 fail-closed 探针、code_sha、守恒三口径）。",
        "4. 审批晚于 A5 签署且窗口 open；窗口内启动，超窗/S1 即停。",
        "5. 任一未满足 → REAL 路径 fail-closed。",
        "",
        "## 12. 产物",
        "",
        "批次目录 research/concorde_metaopt/dreal001/runs/" + plan["batch_id"] + "：plan.json、PREREGISTRATION、approval.DRAFT.json、identity_binding.json、dry_run.json、RUNNER_COMMANDS.md、SHA256SUMS.txt；执行后追加 approval.json、runs/<run_id>/、batch_summary.json、data_manifest.json、solver_attempts.jsonl。",
        "",
        "## 13. 风险与披露",
        "",
        "- 单 seed 方差未知，六臂差异可能被 seed 噪声主导（故只描述）。",
        "- P1R TIMEOUT/重试偏差已入事故；P2a 用 60 s + 无重试 + S1 停批，但 60 s 对大网格不足——P2a 禁用 thick。",
        "- A 臂历史支持跨族、V01/V02 不确定；若 A 臂更好，不能排除先验样效应，需 P2b 干净冷启动对照。",
        "- A1 v1.1 未到前 evaluator 标 EVALUATOR_PENDING_A1_V1_1，不得启动真实批次。",
        "- 12D_ACTIVE=NOT_VALIDATED，P2a 不得声称 12 维全部有效。",
        "",
        "## 14. 变更记录",
        "",
        "- P2A-PREREG-v1（2026-11-10）：首版；6 臂 × seed 42 × B=64=384 starts；timeout 60 s；无重试；单 seed 描述性。",
    ]
    return "\n".join(lines) + "\n"


def build_approval_draft(plan: Mapping[str, Any], plan_sha256: str) -> Dict[str, Any]:
    return {
        "schema": P2A_APPROVAL_SCHEMA,
        "run_id": None,
        "run_id_note": "batch approval covers the six run_ids listed below",
        "run_ids": [str(run["run_id"]) for run in plan["run_matrix"]],
        "batch_id": plan["batch_id"],
        "canonical_batch_id": plan["canonical_batch_id"],
        "phase": plan["phase"],
        "backend": plan["backend"],
        "purpose": plan["purpose"],
        "authorization": plan["authorization"],
        "approval_ref": "DRAFT_PENDING_A5_P2A_PRE",
        "approved": False,
        "approved_by": "",
        "approved_at_utc": "",
        "max_starts": MAX_STARTS,
        "planned_starts": PLANNED_STARTS,
        "planned_breakdown": {arm: BUDGET_STARTS for arm in ARMS},
        "max_internal_solver_cases": MAX_INTERNAL_CASES,
        "expected_internal_cases": EXPECTED_INTERNAL_CASES,
        "max_refine_starts": MAX_REFINE_STARTS,
        "plan_sha256": str(plan_sha256),
        "case_matrix_digest": str(plan["case_matrix_digest"]),
        "case_matrix_digest_full_canonical": str(plan["case_matrix_digest_full_canonical"]),
        "digest_scope": plan["digest_scope"],
        "solver_config_hash": plan["solver_config_sha256"],
        "task_spec": {
            "a2_task_id": plan["task_id"],
            "a2_version": plan["task_version"],
            "a2_fingerprint": plan["task_fingerprint"],
            "a1_schema": plan.get("a1_task_spec", {}).get("schema", ""),
            "a1_raw_sha256": plan.get("a1_task_spec", {}).get("raw_sha256", ""),
            "a1_canonical_sha256": plan.get("a1_task_spec", {}).get("canonical_sha256", ""),
            "a1_status": plan.get("a1_task_spec", {}).get("status", ""),
            "thin_12x25_7alpha": True,
            "l_ref_N": float(L_REF_N),
            "q_Pa": float(Q_PA_DEFAULT),
            "lift_tol_rel": float(LIFT_TOL_REL),
        },
        "frozen_design_space": {
            "raw_sha256": plan.get("frozen_design_space", {}).get("raw_sha256", ""),
            "canonical_sha256": plan.get("frozen_design_space", {}).get("canonical_sha256", ""),
            "bounds_sha256": plan.get("frozen_design_space", {}).get("bounds_sha256", ""),
            "n_variables": plan.get("frozen_design_space", {}).get("n_variables", 0),
            "status": plan.get("frozen_design_space", {}).get("status", ""),
            "source_config": plan.get("frozen_design_space", {}).get("source_config", {}),
        },
        "conservation": dict(plan["conservation"]),
        "solver": {
            "version": "VSPAERO 7.2.2 / OpenVSP 3.55.0",
            "executable": "D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe",
            "parallelism": "1 process x 1 omp thread",
            "argv_template": ["<OPENVSP_ROOT>/vspaero.exe", "-omp", "1", "<basename>"],
            "forbidden_flags": ["-fs", "-mach", "-alpha", "-beta"],
        },
        "timeouts": {"per_case_seconds": float(PER_CASE_TIMEOUT_S), "overrides": {}, "batch_wall_minutes": MAX_WALL_MINUTES, "window_span_minutes": 240},
        "limits": dict(plan["limits"]),
        "references": {
            "L_ref_N": float(L_REF_N),
            "L_ref_formula": "136000 kg * 9.80665",
            "lift_tol_rel": float(LIFT_TOL_REL),
            "q_Pa": float(Q_PA_DEFAULT),
            "sref_policy": "design-dependent Sref(x); report N-dimension D_i with q and Sref",
            "reference_frame": REFERENCE_FRAME,
            "mass_note": "136000 kg single-cruise entry mass; 184880 kg geometric MTOW not used",
            "reconstruction": "A1 canonical x12 -> OpenVSP -> write .vsp3 -> Clear -> Read -> ComputeGeometry -> .vspgeom; native family per design, single build, fail-closed (0 starts); no target family",
        },
        "mesh_policy": dict(MESH_POLICY),
        "endpoint_policy": dict(ENDPOINT_POLICY),
        "stop_conditions": [dict(item) for item in STOP_CONDITIONS],
        "window": {"start_utc": WINDOW_START_UTC, "end_utc": WINDOW_END_UTC, "token": WINDOW_TOKEN, "local_note": WINDOW_LOCAL_NOTE},
        "conditions": [
            "A5 P2a preregistration/plan/approval.DRAFT pre-review PASS",
            "P0 PASS and P1C SOLVER_INTERNAL_PASS_CONTINUATION on file; P1R incompleteness disclosed",
            "A1 EVALUATOR_API v1.2 + p2a_warmstart_support.json bound and V1 determinism validation PASS (v1.1 template only; blocks execution)",
            "P2A-R1 historical-support loader + leakage regression test complete",
            "dry-run fail-closed check PASS; no concurrent real solver batch",
            "Lead signature (approved=true, approved_by=lead, approved_at_utc) after A5 PASS",
            "approved_at_utc inside window; first start >= approved_at_utc",
        ],
        "amendment_log": [
            {
                "amendment": "P2A-PREREG-v1 superseded build",
                "superseded_plan_sha256": "c8eb7d28e895b3979fa52a8f8134cd87895a2aca6b7a19c0b14cbce3a5a37e3f",
                "superseded_at_utc": "2026-11-11T02:19:31Z",
                "reason": "P2A-03/P2A-07/P2A-08/P2A-09 blockers: historical-support loader, thin TaskSpec binding, conservation ledger, real A1 dry-run path",
                "physical_solver_starts": 0,
                "plan_bytes_unchanged": False,
            }
        ],
        "note": "DRAFT ONLY: REAL execution refused until approved=true; A2 never launches vspaero.exe.",
        "physical_solver_starts": 0,
        "solver_started": False,
    }


def _write_sha256sums(directory: Path, files: Sequence[Mapping[str, Any]], name: str = "SHA256SUMS.txt") -> Path:
    target = directory / name
    target.write_text("\n".join("%s  %s" % (row["sha256"], row["path"]) for row in files) + "\n", encoding="utf-8")
    return target


def _manifest(directory: Path, exclude: Sequence[str] = ("SHA256SUMS.txt", "verify.json")) -> List[Dict[str, Any]]:
    skip = set(exclude)
    rows: List[Dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(directory).as_posix()
        if rel in skip:
            continue
        rows.append({"path": rel, "bytes": int(path.stat().st_size), "sha256": sha256_file(path)})
    return rows


def write_p2a_batch(batch_dir: Path = DEFAULT_BATCH_DIR, *, a1_root: Optional[Path] = None, support_path: Optional[Any] = None, production_template_path: Optional[str] = None, docs_dir: Optional[Path] = None) -> Dict[str, Any]:
    worktree = _worktree_root()
    batch_dir = Path(batch_dir)
    if not batch_dir.is_absolute():
        batch_dir = worktree / batch_dir
    docs_dir = (worktree / "docs" / "dreal001" / "p2a") if docs_dir is None else Path(docs_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    plan = build_plan(batch_dir=batch_dir, a1_root=a1_root, support_path=support_path, production_template_path=production_template_path)
    prereg_file = docs_dir / "PREREGISTRATION.md"
    prereg_file.write_text(render_preregistration(plan), encoding="utf-8")
    plan["preregistration"] = {"path": _rel(prereg_file, worktree), "sha256": sha256_file(prereg_file), "version": "P2A-PREREG-v1", "status": "BOUND"}
    plan["identity_binding"]["preregistration"] = dict(plan["preregistration"])

    plan_path = batch_dir / "plan.json"
    plan_path.write_text(canonical_json(plan) + "\n", encoding="utf-8")
    plan_sha = sha256_file(plan_path)
    approval = build_approval_draft(plan, plan_sha)
    approval_path = batch_dir / "approval.DRAFT.json"
    write_json_atomic(approval_path, approval)

    binding = {
        "schema": "dreal001.identity_binding.v1",
        "batch_id": plan["batch_id"],
        "created_ts_utc": utc_now(),
        "physical_solver_starts": 0,
        "files": {
            "plan": {"path": "plan.json", "sha256": plan_sha},
            "preregistration": {"path": plan["preregistration"]["path"], "sha256": plan["preregistration"]["sha256"]},
            "approval_draft": {"path": "approval.DRAFT.json", "sha256": sha256_file(approval_path)},
        },
        "bindings": {
            "plan_sha256": plan_sha,
            "case_matrix_digest": plan["case_matrix_digest"],
            "case_matrix_digest_full_canonical": plan["case_matrix_digest_full_canonical"],
            "digest_scope": plan["digest_scope"],
            "task_spec": plan["identity_binding"]["task_spec"],
            "a1_task_spec": plan["identity_binding"]["a1_task_spec"],
            "frozen_design_space": plan["identity_binding"]["frozen_design_space"],
            "conservation": plan["conservation"],
            "l_ref": plan["identity_binding"]["l_ref"],
            "solver_config_sha256": plan["solver_config_sha256"],
            "evaluator": plan["identity_binding"]["evaluator"],
            "support": plan["identity_binding"]["support"],
            "run_matrix_sha256": plan["run_matrix_sha256"],
        },
        "status": "PENDING_A5_PRE_REVIEW_AND_LEAD_SIGNATURE",
    }
    write_json_atomic(batch_dir / "identity_binding.json", binding)

    dry = dry_run(batch_dir, a1_root=a1_root)
    _write_runner_commands(docs_dir, batch_dir)
    files = _manifest(batch_dir)
    _write_sha256sums(batch_dir, files)
    return {"batch_dir": str(batch_dir), "plan_path": str(plan_path), "plan_sha256": plan_sha, "approval_draft_path": str(approval_path), "approval_draft_sha256": sha256_file(approval_path), "prereg_path": str(prereg_file), "identity_binding_path": str(batch_dir / "identity_binding.json"), "dry_run": dry, "n_files": len(files)}


def _write_runner_commands(docs_dir: Path, batch_dir: Path) -> None:
    worktree = _worktree_root()
    rel_batch = _rel(batch_dir, worktree)
    code = FENCE + "powershell"
    pycode = FENCE + "python"
    end = FENCE
    text = "\n".join([
        "# P2a runner commands（零物理预检模板）",
        "",
        "所有命令在 A2 worktree " + str(worktree) + " 下运行；Python 固定 D:/RCAIDE/envs/RCAIDE/python.exe。",
        "",
        "## 1. 生成/刷新预注册包（零物理）",
        "",
        code,
        "& D:/RCAIDE/envs/RCAIDE/python.exe -m research.concorde_metaopt.dreal001.optimizers.p2a build",
        end,
        "",
        "历史支持工件（P2A-R1）路径：默认读 env DREAL001_P2A_SUPPORT，或显式 --support-path；工件 schema=dreal001.p2a_warmstart_support.v1（15 设计），其 SHA256 写入 plan/approval.DRAFT/identity_binding。",
        "TaskSpec：thin 12x25、7 个固定 alpha、refine=0；A1 v1.1 task_spec.py + design_space_freeze.json 的 raw/canonical SHA 已绑定。",
        "",
        "## 2. 复核 SHA 与绑定（零物理）",
        "",
        code,
        "& D:/RCAIDE/envs/RCAIDE/python.exe -m research.concorde_metaopt.dreal001.optimizers.p2a verify",
        end,
        "",
        "## 3. dry-run（REAL 路径 fail-closed）",
        "",
        code,
        "& D:/RCAIDE/envs/RCAIDE/python.exe -m research.concorde_metaopt.dreal001.optimizers.p2a dry-run",
        end,
        "",
        "预期：status=BLOCKED_FAIL_CLOSED、physical_solver_starts=0、solver_started=false；approval.DRAFT.approved=false 时 validate_approval 抛 PilotNotApproved；A1 make_evaluate_fn 在构造 evaluator 前以 APPROVAL_MISSING_OR_NOT_APPROVED 拒绝；A2 build_real_adapter 在 spawn 前拒绝；A1/A2 探针 physical_call_count=0。",
        "dry_run.json 记录 plan/approval SHA、window_open/remaining_s、384/2688、code_sha（executor blob + A1 code files + A2 binding modules）、无 cases/无台账/无 vspaero 进程。",
        "",
        "## 4. 执行（仅 A5 PASS + Lead 签 approval + 窗口 open 后）",
        "",
        "- approval.json 存在且 approved=true、plan_sha256 与 plan 原始字节 SHA 一致、batch_id 一致、max_starts>=384；",
        "- 窗口 " + WINDOW_START_UTC + " – " + WINDOW_END_UTC + "，token " + WINDOW_TOKEN + "，UTC 唯一权威；",
        "- A1 v1.1 + production 模板已绑定（identity_binding.json.bindings.evaluator.status 不为 EVALUATOR_PENDING_A1_V1_1）；",
        "- P2A-R1 历史支持加载器与泄漏测试完成；",
        "- 注入 A1 ledgered spawn 的 real_adapter_factory，allow_physical_starts=True；A2 绝不直接 subprocess vspaero.exe。",
        "",
        "runner 骨架（不自动执行）：",
        "",
        pycode,
        "from pathlib import Path",
        "from research.concorde_metaopt.dreal001.optimizers.p2a import load_bound_plan",
        "from research.concorde_metaopt.dreal001.optimizers.pilot import run_pilot, load_approval",
        "from research.concorde_metaopt.dreal001.optimizers.real_backend import pilot_real_adapter_factory",
        "",
        "batch = Path(\"" + rel_batch + "\")",
        "plan = load_bound_plan(batch / \"plan.json\")",
        "approval = load_approval(batch / \"approval.json\")",
        "factory = pilot_real_adapter_factory(spawn=a1_ledgered_spawn, allow_physical_starts=True)",
        "summary = run_pilot(batch.parent, plan, approval=approval, backend=\"REAL_VSPAERO\", real_adapter_factory=factory, resume=True)",
        end,
        "",
        "未获批时上述调用必须在第一处 validate_approval 失败并零启动退出。",
        "",
    ])
    (docs_dir / "RUNNER_COMMANDS.md").write_text(text, encoding="utf-8")


def load_bound_plan(path: Path) -> Dict[str, Any]:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    plan["plan_sha256"] = sha256_file(Path(path))
    return plan


def dry_run(batch_dir: Path = DEFAULT_BATCH_DIR, *, a1_root: Optional[Path] = None) -> Dict[str, Any]:
    worktree = _worktree_root()
    root = _a1_root_default() if a1_root is None else Path(a1_root)
    batch_dir = Path(batch_dir)
    if not batch_dir.is_absolute():
        batch_dir = worktree / batch_dir
    plan_path = batch_dir / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    approval = json.loads((batch_dir / "approval.DRAFT.json").read_text(encoding="utf-8"))
    plan_sha = sha256_file(plan_path)
    approval_sha = sha256_file(batch_dir / "approval.DRAFT.json")
    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    check("batch_id_naming", bool(BATCH_ID_RE.match(str(plan.get("batch_id", "")))), plan.get("batch_id"))
    run_ids = [str(run.get("run_id")) for run in plan.get("run_matrix", [])]
    check("run_id_naming", all(RUN_ID_RE.match(rid) for rid in run_ids), run_ids)
    check("run_count", len(run_ids) == 6, len(run_ids))
    check("planned_starts", int(plan.get("planned_starts", 0)) == MAX_STARTS and sum(int(r.get("budget_starts", 0)) for r in plan.get("run_matrix", [])) == MAX_STARTS, plan.get("planned_starts"))
    check("case_count", len(plan.get("case_matrix", [])) == MAX_STARTS, len(plan.get("case_matrix", [])))
    recomputed = case_matrix_digest(plan["case_matrix"])
    check("case_matrix_digest", recomputed == plan.get("case_matrix_digest"), {"recomputed": recomputed, "declared": plan.get("case_matrix_digest")})
    check("internal_cases", int(plan.get("budget", {}).get("max_internal_cases", 0)) == MAX_INTERNAL_CASES, plan.get("budget", {}).get("max_internal_cases"))
    check("per_case_timeout", float(plan.get("timeout_seconds_per_case", 0)) == PER_CASE_TIMEOUT_S, plan.get("timeout_seconds_per_case"))
    check("refine_forbidden", int(plan.get("budget", {}).get("max_refine_starts", -1)) == 0, plan.get("budget", {}).get("max_refine_starts"))
    check("stop_conditions", {item["code"] for item in plan.get("stop_conditions", [])} >= {"S1", "S2", "S3", "S4", "S5"}, [item["code"] for item in plan.get("stop_conditions", [])])
    check("approval_is_draft", approval.get("approved") is False and not approval.get("approved_by"), {"approved": approval.get("approved")})
    check("approval_binds_plan", str(approval.get("plan_sha256")) == plan_sha, {"approval": approval.get("plan_sha256"), "plan_raw": plan_sha})
    check("approval_digest_scope", bool(approval.get("digest_scope")) and str(approval.get("case_matrix_digest")) == str(plan.get("case_matrix_digest")), approval.get("case_matrix_digest"))
    check("window_utc", approval.get("window", {}).get("start_utc") == WINDOW_START_UTC and approval.get("window", {}).get("end_utc") == WINDOW_END_UTC and approval.get("window", {}).get("token") == WINDOW_TOKEN, approval.get("window"))
    a1_task = plan.get("a1_task_spec", {})
    frozen = plan.get("frozen_design_space", {})
    evaluator = plan.get("identity_binding", {}).get("evaluator", {})
    check("a1_task_spec_bound", a1_task.get("status") == "BOUND", {"status": a1_task.get("status"), "a1_raw": a1_task.get("raw_sha256"), "a1_canonical": a1_task.get("canonical_sha256")})
    legacy = list(plan.get("solver_config_legacy_keys") or [])
    solver_config = plan.get("task", {}).get("solver_config", {})
    thin_ok = (
        not legacy
        and str(solver_config.get("geom_set")) == "thin"
        and float(solver_config.get("tess_u", 0)) == 12.0
        and float(solver_config.get("tess_w", 0)) == 25.0
        and [float(v) for v in solver_config.get("alpha_primary_deg", [])] == [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
        and int(solver_config.get("refine_starts", -1)) == 0
    )
    check("task_spec_thin_12x25_7alpha", thin_ok, {"legacy_keys": legacy, "geom_set": solver_config.get("geom_set"), "tess": [solver_config.get("tess_u"), solver_config.get("tess_w")], "alpha": solver_config.get("alpha_primary_deg"), "refine_starts": solver_config.get("refine_starts")})
    check("p2a_contract_thin_bound", bool(evaluator.get("p2a_contract_thin_12x25_bound")), {"contract": evaluator.get("p2a_contract_sha256"), "api": evaluator.get("api_version_detected_in_a1_tree")})
    check("frozen_design_space_bound", frozen.get("status") == "BOUND" and int(frozen.get("n_variables", 0)) == 12, {"status": frozen.get("status"), "n": frozen.get("n_variables"), "raw": frozen.get("raw_sha256"), "canonical": frozen.get("canonical_sha256"), "bounds": frozen.get("bounds_sha256")})
    conservation = plan.get("conservation", {})
    check(
        "conservation_three_ledgers",
        bool(conservation.get("one_start_equals"))
        and int(conservation.get("one_start_equals", {}).get("internal_solver_cases", 0)) == int(INTERNAL_SOLVER_CASES_PER_START)
        and len(conservation.get("conservation_relations", [])) >= 3
        and bool(conservation.get("planned_vs_max"))
        and conservation.get("refine", {}).get("max_refine_starts") == 0,
        {"units": conservation.get("ledger_units"), "relations": conservation.get("conservation_relations"), "source_of_truth": conservation.get("source_of_truth")},
    )
    check(
        "digest_scope_two_values",
        bool(plan.get("case_matrix_digest"))
        and bool(plan.get("case_matrix_digest_full_canonical"))
        and str(plan.get("case_matrix_digest")) != str(plan.get("case_matrix_digest_full_canonical"))
        and bool(approval.get("case_matrix_digest_full_canonical"))
        and bool(approval.get("digest_scope")),
        {"projected": plan.get("case_matrix_digest"), "full": plan.get("case_matrix_digest_full_canonical")},
    )
    mesh_policy = plan.get("mesh_policy", {})
    check(
        "mesh_policy_canonical_roundtrip",
        mesh_policy.get("mesh_policy") == "canonical_roundtrip_native_family"
        and mesh_policy.get("no_target_family") is True
        and mesh_policy.get("single_build") is True
        and mesh_policy.get("fail_closed_0_start") is True,
        {"policy": mesh_policy.get("mesh_policy"), "target": mesh_policy.get("target_mesh_family"), "single_build": mesh_policy.get("single_build"), "fail_closed_0_start": mesh_policy.get("fail_closed_0_start"), "determinism_evidence": mesh_policy.get("determinism_evidence", {}).get("status")},
    )
    endpoint_policy = plan.get("endpoint_policy", {})
    check(
        "endpoint_policy_declared",
        endpoint_policy.get("E3_six_arm_ranking_or_winner", "").startswith("NOT_COMPARABLE")
        and endpoint_policy.get("E5_significance_or_overall_winner", "").startswith("NOT_COMPUTABLE")
        and endpoint_policy.get("family_label_required") is True,
        {"E2": endpoint_policy.get("E2_best_D_i_at_B"), "E3": endpoint_policy.get("E3_six_arm_ranking_or_winner"), "E5": endpoint_policy.get("E5_significance_or_overall_winner")},
    )
    check("warmstart_support_bound", plan.get("warmstart_support_status") == "BOUND", {"status": plan.get("warmstart_support_status")})
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(WINDOW_START_UTC.replace("Z", "+00:00"))
    end = datetime.fromisoformat(WINDOW_END_UTC.replace("Z", "+00:00"))
    window_open = start <= now <= end
    remaining_s = int((end - now).total_seconds())
    check("window_bounds_sane", end > start and window_open in (True, False), {"start_utc": WINDOW_START_UTC, "end_utc": WINDOW_END_UTC, "window_open_now": window_open, "remaining_s": remaining_s})
    try:
        from .pilot import validate_approval
        validate_approval(dict(plan, plan_sha256=plan_sha), approval)
        real_path = {"status": "APPROVED_UNEXPECTED", "reason": "approval draft passed validation"}
    except Exception as exc:
        real_path = {"status": "BLOCKED_FAIL_CLOSED", "reason": "%s: %s" % (type(exc).__name__, exc)}
    check("real_path_fail_closed", real_path["status"] == "BLOCKED_FAIL_CLOSED", real_path["reason"])

    a1_probe = probe_a1_fail_closed(root, approval)
    check(
        "a1_fail_closed_before_solver",
        a1_probe.get("status") == "REFUSED_BEFORE_SOLVER" and bool(a1_probe.get("expected_code_present")) and int(a1_probe.get("physical_call_count", 0)) == 0,
        {"status": a1_probe.get("status"), "exception": a1_probe.get("exception"), "message": a1_probe.get("message"), "physical_call_count": a1_probe.get("physical_call_count", 0)},
    )
    a2_probe = probe_a2_adapter_fail_closed(approval)
    check(
        "a2_adapter_fail_closed_before_spawn",
        a2_probe.get("status") == "REFUSED_BEFORE_SPAWN" and int(a2_probe.get("physical_call_count", 0)) == 0,
        {"status": a2_probe.get("status"), "exception": a2_probe.get("exception"), "message": a2_probe.get("message"), "physical_call_count": a2_probe.get("physical_call_count", 0)},
    )
    try:
        from .real_backend import load_a1_evaluator_class
        load_a1_evaluator_class()
        a1_status = {"importable": True, "detail": "A1 evaluator module importable", "physical_call_count": 0}
    except Exception as exc:
        a1_status = {"importable": False, "detail": "%s: %s" % (type(exc).__name__, exc), "physical_call_count": 0}
    check("a1_evaluator_probe", True, a1_status["detail"])
    executor_path = Path(__file__).resolve()
    code_sha = sha256_file(executor_path)
    executor_blob = {
        "path": _rel(executor_path, worktree),
        "sha256": code_sha,
        "bytes": int(executor_path.stat().st_size),
        "a1_code_files": list(evaluator.get("a1_code_files") or []),
        "a2_binding_modules": [
            {"path": "research/concorde_metaopt/dreal001/optimizers/p2a_binding.py", "sha256": sha256_file(Path(__file__).resolve().parent / "p2a_binding.py")},
            {"path": "research/concorde_metaopt/dreal001/optimizers/p2a_support.py", "sha256": sha256_file(Path(__file__).resolve().parent / "p2a_support.py")},
        ],
    }
    runtime_files = [name for name in ("solver_attempts.jsonl", "approval.json", "case_matrix_runtime.json") if (batch_dir / name).exists()]
    check("no_runtime_artifacts", not runtime_files and plan.get("physical_solver_starts") == 0 and plan.get("solver_started") is False, {"runtime_files": runtime_files, "physical_solver_starts": plan.get("physical_solver_starts")})

    report = {
        "schema": "dreal001.p2a.dry_run.v1",
        "batch_id": plan.get("batch_id"),
        "created_ts_utc": utc_now(),
        "status": "DRY_RUN_BLOCKED_FAIL_CLOSED",
        "physical_solver_starts": 0,
        "physical_call_count": 0,
        "solver_started": False,
        "real_path": real_path,
        "a1_evaluator": a1_status,
        "plan_sha256": plan_sha,
        "approval_draft_sha256": approval_sha,
        "approval_approved": bool(approval.get("approved")),
        "max_starts": int(plan.get("budget", {}).get("max_starts", 0)),
        "planned_starts": int(plan.get("planned_starts", 0)),
        "max_internal_cases": int(plan.get("budget", {}).get("max_internal_cases", 0)),
        "window": {"start_utc": WINDOW_START_UTC, "end_utc": WINDOW_END_UTC, "token": WINDOW_TOKEN, "window_open_now": window_open, "remaining_s": remaining_s, "source": "UTC"},
        "code_sha": code_sha,
        "executor_blob": executor_blob,
        "a1_probe": a1_probe,
        "a2_probe": a2_probe,
        "cases_emitted": 0,
        "ledger_created": False,
        "solver_processes": 0,
        "checks": checks,
        "n_checks": len(checks),
        "n_failed": sum(1 for item in checks if item["status"] == "FAIL"),
        "note": "dry run only: plan/prereg/approval.DRAFT validated; REAL refused until A5 PASS + Lead approval + A1 v1.2 + support artifact + window open",
    }
    write_json_atomic(batch_dir / "dry_run.json", report)
    _write_sha256sums(batch_dir, _manifest(batch_dir))
    return report


def verify(batch_dir: Path = DEFAULT_BATCH_DIR) -> Dict[str, Any]:
    worktree = _worktree_root()
    batch_dir = Path(batch_dir)
    if not batch_dir.is_absolute():
        batch_dir = worktree / batch_dir
    plan_path = batch_dir / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    approval = json.loads((batch_dir / "approval.DRAFT.json").read_text(encoding="utf-8"))
    results: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        results.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    plan_sha = sha256_file(plan_path)
    add("plan_sha256_vs_approval", str(approval.get("plan_sha256")) == plan_sha, {"plan_raw": plan_sha, "approval": approval.get("plan_sha256")})
    add("planned_starts", int(plan.get("planned_starts", -1)) == MAX_STARTS, plan.get("planned_starts"))
    add("case_matrix_digest", case_matrix_digest(plan["case_matrix"]) == plan.get("case_matrix_digest"), plan.get("case_matrix_digest"))
    add("case_matrix_full_digest", _sha_of_json(plan["case_matrix"]) == plan.get("case_matrix_digest_full_canonical"), plan.get("case_matrix_digest_full_canonical"))
    add("run_matrix_digest", _sha_of_json(plan["run_matrix"]) == plan.get("run_matrix_sha256"), plan.get("run_matrix_sha256"))
    add("prereg_sha", sha256_file(worktree / plan["preregistration"]["path"]) == plan["preregistration"]["sha256"], plan["preregistration"]["sha256"])
    sum_path = batch_dir / "SHA256SUMS.txt"
    sha_rows = 0
    sha_ok = True
    problems: List[str] = []
    if sum_path.exists():
        for line in sum_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, name = line.split("  ", 1)
            target = batch_dir / name
            if not target.exists():
                sha_ok = False
                problems.append("missing:" + name)
                continue
            if sha256_file(target) != digest:
                sha_ok = False
                problems.append("mismatch:" + name)
            sha_rows += 1
    add("sha256sums", sha_ok and sha_rows > 0, {"rows": sha_rows, "problems": problems})
    add("observability_fields", all(k in plan for k in ("timeouts", "stop_conditions", "mesh_policy", "l_ref", "identity_binding")), "ok")
    status = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    report = {"schema": "dreal001.p2a.verify.v1", "batch_id": plan.get("batch_id"), "status": status, "checks": results, "physical_solver_starts": 0}
    write_json_atomic(batch_dir / "verify.json", report)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="D-REAL-001 P2a pre-registration package (zero physical)")
    parser.add_argument("command", choices=("build", "dry-run", "verify"), nargs="?", default="build")
    parser.add_argument("--batch-dir", default=str(DEFAULT_BATCH_DIR))
    parser.add_argument("--a1-root", default=None)
    parser.add_argument("--production-template-path", default=None)
    parser.add_argument("--support-path", default=None)
    args = parser.parse_args(argv)
    batch_dir = Path(args.batch_dir)
    if args.command == "build":
        result = write_p2a_batch(batch_dir, a1_root=None if args.a1_root is None else Path(args.a1_root), support_path=args.support_path, production_template_path=args.production_template_path)
        print(json.dumps({key: result[key] for key in ("batch_dir", "plan_sha256", "approval_draft_sha256", "n_files")}, ensure_ascii=False, indent=1))
        print("dry_run_status=%s failed=%d physical=%d" % (result["dry_run"]["status"], result["dry_run"]["n_failed"], result["dry_run"]["physical_solver_starts"]))
        return 0
    if args.command == "dry-run":
        report = dry_run(batch_dir, a1_root=None if args.a1_root is None else Path(args.a1_root))
        print(json.dumps({"status": report["status"], "n_failed": report["n_failed"], "real_path": report["real_path"], "physical_solver_starts": report["physical_solver_starts"]}, ensure_ascii=False, indent=1))
        return 0 if report["n_failed"] == 0 else 2
    report = verify(batch_dir)
    print(json.dumps({"status": report["status"], "checks": report["checks"]}, ensure_ascii=False, indent=1))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
