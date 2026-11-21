
"""Generate the P0-deliverable P1/P2/P3 preregistration (JSON) + split freeze.

All hashes are computed from files present in this worktree at generation time.
Nothing here authorises physics: P1 needs a fresh A5 review and a new Lead GO.
"""
from __future__ import annotations

import hashlib, json, platform, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
P0 = OUT


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


CODE = [
    "research/concorde_metaopt/dreal001/geometry/adaptive_alpha.py",
    "research/concorde_metaopt/dreal001/geometry/polar_rows.py",
    "research/concorde_metaopt/dreal001/meta/endpoint_analysis.py",
    "research/concorde_metaopt/tests/test_adaptive_alpha.py",
    "research/concorde_metaopt/tests/test_polar_rows.py",
    "research/concorde_metaopt/tests/test_endpoint_analysis.py",
    "docs/evidence/dreal004/p0/a1_replay_g1.py",
    "docs/evidence/dreal004/p0/a1_variable_response_audit.py",
    "docs/evidence/dreal004/p0/a2_g1_baseline_endpoints.py",
]
FILES = {path: sha256(ROOT / path) for path in CODE}
for name in ("g1_alpha_replay.json", "12d_variable_response_audit.json",
             "a2_g1_baseline_endpoints.json"):
    FILES["docs/evidence/dreal004/p0/" + name] = sha256(P0 / name)

VARIABLES = [
    {"index": 0, "name": "wing_area", "baseline": 358.25, "probe": "d01 +1% (361.8325)"},
    {"index": 1, "name": "aspect_ratio", "baseline": 1.83, "probe": "none in G1/G2"},
    {"index": 2, "name": "sweep_1", "baseline": 67.0, "probe": "d02 +0.5 / d04 -0.5"},
    {"index": 3, "name": "sweep_2", "baseline": 48.0, "probe": "d06 +0.5"},
    {"index": 4, "name": "sweep_3", "baseline": 71.0, "probe": "none"},
    {"index": 5, "name": "span_location_2", "baseline": 0.480469, "probe": "none"},
    {"index": 6, "name": "span_location_3", "baseline": 0.945313, "probe": "none"},
    {"index": 7, "name": "chord_ratio_2", "baseline": 0.408284, "probe": "none"},
    {"index": 8, "name": "chord_ratio_3", "baseline": 0.130178, "probe": "none"},
    {"index": 9, "name": "tip_twist", "baseline": 0.0, "probe": "none"},
    {"index": 10, "name": "vertical_tail_area", "baseline": 33.91,
     "probe": "d05 +2% (34.5882)", "status": "PASSIVE_AT_BETA_ZERO"},
    {"index": 11, "name": "vertical_tail_sweep_delta", "baseline": 0.0,
     "probe": "none", "status": "PASSIVE_AT_BETA_ZERO"},
    {"index": 12, "name": "fuselage_length", "baseline": 61.66, "probe": "d07 -1% (62.2766 is +1%)"},
    {"index": 13, "name": "fuselage_fineness", "baseline": 4.30, "probe": "none"},
    {"index": 14, "name": "fuselage_height_width_ratio", "baseline": 1.152778, "probe": "none"},
]

tasks = [
    {"task_id": "DREAL004-M140", "mach": 1.4, "split": "train", "designs": 8,
     "known_labels_g1": 0, "note": "G1 6 cases no bracket; diagnosis task"},
    {"task_id": "DREAL004-M160", "mach": 1.6, "split": "train", "designs": 8,
     "known_labels_g1": 0, "note": "G1 6 cases no bracket; may be excluded from training if labels stay insufficient"},
    {"task_id": "DREAL004-M180", "mach": 1.8, "split": "val", "designs": 8,
     "known_labels_g1": 2},
    {"task_id": "DREAL004-M200", "mach": 2.0, "split": "train", "designs": 8,
     "known_labels_g1": 0},
    {"task_id": "DREAL004-M202", "mach": 2.02, "split": "train", "designs": 8,
     "known_labels_g1": 3, "note": "reference TASK_SPEC Mach"},
    {"task_id": "DREAL004-M220", "mach": 2.2, "split": "val", "designs": 8,
     "known_labels_g1": 0},
    {"task_id": "DREAL004-M240", "mach": 2.4, "split": "test", "designs": 8,
     "known_labels_g1": 3, "note": "held out: no tuning"},
    {"task_id": "DREAL004-M260", "mach": 2.6, "split": "test", "designs": 8,
     "known_labels_g1": 0, "note": "held out: no tuning"},
]

doc = {
    "schema": "dreal004.p1_p2_p3_preregistration.v1",
    "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "issue": "QingYangJin/RCAIDE_Supersonic#14",
    "branch": "research/dreal004-alpha-adaptive-meta-sampling",
    "base_commit": "af9871cd2b16a083c228ac2ecbced4c0344012a0",
    "baseline_commit_of_previous_stage": "409f09c8b31ce653873727217273805a16d5b422",
    "owner_instruction_ref": "m05968 / m08739 / issue #14 body",
    "physical_starts_used_so_far": 0,
    "current_authorization": "P0_CODE_AND_PROTOCOL_ONLY",
    "environment": {"python": platform.python_version(),
                    "solver": "D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe",
                    "solver_identity": "vspaero-3.55.0-v7.2.2-omp1",
                    "omp_threads": 1, "parallelism": 1},
    "code_shas": FILES,
    "geometry_contract_sha256": "5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15",
    "design_variables_12d_note": (
        "The frozen contract carries 15 named geometry variables; the meta-learning "
        "input vector remains the 12D design vector used by the TaskSpec contract "
        "(index 0-9 and 12-14 in P0/P1; vertical-tail indices 10-11 are passive at "
        "beta=0 and are excluded from the active optimisation dimensions, see "
        "12d_variable_response_audit.json)"),
    "design_variables": VARIABLES,
    "task_family_split": {
        "status": "FROZEN_FOR_P1_TO_P3",
        "frozen_reason": "task-level isolation must precede any hyperparameter choice",
        "tasks": tasks,
        "split_counts": {"train": 4, "val": 2, "test": 2},
        "support_designs": ["d00", "d01", "d02", "d03"],
        "query_designs": ["d04", "d05", "d06", "d07"],
        "unique_designs_per_task": 8,
        "coupling_rules": [
            "no task may move between splits after this freeze",
            "test tasks M240/M260 never tune hyperparameters or early stopping",
            "support/query partition per task is fixed; a design may not appear in both",
            "P1 pilot tasks are chosen from M202 only and are NOT training sets",
        ],
    },
    "endpoints": {
        "primary": [
            "N_first_feasible (design evaluations, design starts, internal alpha cases)",
            "best_feasible_Di_N(B) and anytime curve for B=4/8/16/32/64/128",
            "simple_regret(B) only if an independently established reference exists",
            "point_feasible_hit_rate and run_found_feasible",
            "cost_to_target(pre-registered Di_N improvement threshold)",
        ],
        "secondary": ["surrogate RMSE/MAE", "ranking correlation", "feasibility AUC",
                      "calibration", "OOD error"],
        "cost_keys": ["design_starts", "internal_solver_cases", "wall_clock_s"],
        "fairness": (
            "paired by (task, seed, budget); support points, initial samples, alpha "
            "solver cases, failures and retries all count; MAML amortised training "
            "cost reported before/after amortisation"),
        "statistics": (
            "task as the primary unit; paired differences, bootstrap/Wilcoxon, "
            "multiple-comparison correction; UNDERPOWERED is reported rather than "
            "over-claiming"),
        "reference_policy": (
            "no reference Di_N exists yet; simple_regret stays null until an "
            "independent sufficient search establishes one"),
    },
    "p0_replay_summary": {
        "g1_cases": 24,
        "raw_hit_on_existing_row": 8,
        "requires_new_alpha_rows": 7,
        "no_bracket_on_existing_rows": 8,
        "missing_input": 1,
        "g1_fixed_sweep_internal_cases": 391,
        "adaptive_replay_probes": 329,
        "physical_solver_starts_used": 0,
        "labels_created": 0,
    },
    "p0_12d_audit_summary": {
        "variables_checked": 15,
        "v01_vertical_tail_area_delta_cdi": 0.0,
        "v01_observation": ("beta=0 means the vertical tail does not load; Di_N=q*Sref*CDi "
                            "is exactly unchanged while CDo rises ~1.445e-5"),
        "v02_status": "RESPONSE_PENDING_P1_PROBE",
        "active_dimensions": 13,
        "passive_dimensions": 2,
        "disclosure": ("V01/V02 may only be claimed as active 12D dimensions once a "
                       "beta!=0 task family exists; P2/P3 must not claim their response"),
    },
    "a2_baseline": {
        "source": "G1 recorded sequence (24 charged starts, 8 admitted labels)",
        "first_feasible": {"design_starts": 10, "internal_solver_cases": 170,
                           "di_n": 146625.66015490517},
        "point_feasible_hit_rate": 0.3333333333333333,
        "design_starts_per_label": 3.0,
        "internal_solver_cases_per_label": 48.875,
        "note": "descriptive historical baseline, not a new sampler run",
    },
    "p1": {
        "status": "PREREGISTERED_NOT_AUTHORISED",
        "purpose": ("pilot: does adaptive alpha refinement reach a real raw row within "
                    "the frozen 1e-3 lift tolerance at acceptable internal alpha cost?"),
        "proposed_authorization_id": "AUTH-DREAL004-P1-20261122-01",
        "proposed_run_id": "DRECOVER001-P1-20261122-01",
        "target_task": "DREAL004-M202",
        "designs": ["d00", "d01", "d04", "d07"],
        "design_semantics": {"d00": "baseline", "d01": "wing_area +1%",
                             "d04": "sweep_1 -0.5 deg", "d07": "fuselage_length +1%"},
        "max_design_starts": 12,
        "max_starts_per_design": 3,
        "max_alpha_probes_per_start": 3,
        "max_internal_solver_cases": 36,
        "coarse_bracket_source": "existing G2 stage1 M202 raw polar rows (zero physical)",
        "refinement": "secant interpolation inside the bracket, half-width shrink, no extrapolation",
        "tolerance": {"tol_cl_rel": 1e-3, "may_not_be_relaxed": True,
                      "interpolated_target_never_counted_as_raw": True},
        "success_criteria": {
            "raw_point_hit_rate": ">= 0.70 over the 4 designs",
            "secondary": "median internal alpha cases per design reported; no widening of tol",
            "labels": "only raw rows within tolerance may be admitted; otherwise NULL_LABEL",
        },
        "stop_rules": [
            "3 starts per design exhausted -> NO_RAW_POINT for that design",
            "12 design starts total exhausted -> batch closes",
            "2 consecutive solver failures -> STOP",
            "wall clock >= 3600s -> STOP",
            "ledger accounting not conserved -> STOP_ACCOUNTING_VIOLATION",
            "upload/readback of each <=8-start mini-batch must pass before the next",
        ],
        "gates_before_start": ["A5 P1_PROTOCOL_AND_CODE_REVIEW_PASS",
                               "Lead issues a new P1 GO after A5",
                               "Owner budget for <=12 starts already stated in issue #14"],
        "not_a_training_batch": True,
        "outputs": ["raw_cases", "tables/alpha_refinement_history.csv",
                    "tables/all_evaluations.csv", "tables/admitted_labels.csv",
                    "tables/failed_or_null.csv", "tables/actual_solver_ledger.csv",
                    "metadata/*", "figures/*.png + figure_data.csv",
                    "SHA256SUMS.txt", "upload_receipt.json", "A5 verdict"],
    },
    "p2": {
        "status": "PREREGISTERED_NOT_AUTHORISED",
        "purpose": "expand real task family and train FOMAML/pretrain/context-pretrain",
        "capacity_new_design_starts": 240,
        "entry_gates": ["P1 accepted", "A5 review of the exact batch plan",
                        "Lead issues a new P2 GO", "each <=16-32-start mini-batch uploaded and read back"],
        "label_requirements": {
            "admission": "RealAdmissionManifest with raw SHA256 and di_n=q*Sref*CDi recomputation",
            "minimum_per_train_task": ">= 4 admitted labels (support+query)",
            "minimum_tasks": {"train": 4, "val": 2, "test": 2},
            "insufficient_labels": "expand data; synthetic labels may not substitute",
        },
        "training_arms": ["FOMAML K=1/3/5", "plain pooled pretrain",
                          "task-conditioned pretrain (16D context separate from 12D)",
                          "random initialisation", "full MAML as optional ablation"],
        "maml_requirements": [
            "initialisation learned from >=2 real training tasks",
            "test adaptation uses support only; query never updates parameters",
            "report before/after amortisation cost",
            "negative transfer is a reportable result, not hidden",
        ],
    },
    "p3": {
        "status": "PREREGISTERED_NOT_AUTHORISED",
        "purpose": "limited-budget sampling comparison with real feedback",
        "capacity_new_design_starts": 384,
        "entry_gates": ["P2 accepted", "A5 review", "Lead per-batch GO"],
        "samplers": ["Random", "LHS", "Sobol", "plain pretrain surrogate",
                     "FOMAML K-shot", "FOMAML zero-shot"],
        "backends": ["BO with one fixed GP/acquisition", "DE/PSO extension with unified budget"],
        "budgets": [4, 8, 16, 32, 64, 128],
        "mini_batch_max_starts": 32,
        "upload_readback_after_each_mini_batch": True,
        "fairness_rules": [
            "same support observations and same K for every method on a task",
            "same total design starts and internal solver cases per paired comparison",
            "all failures/retries/alpha cases charged",
            "no test-query tuning; multiple seeds; task-level statistics",
        ],
    },
    "forbidden": [
        "relaxing tol_CL=1e-3 or presenting interpolated estimates as raw hits",
        "using G1 null points as successes or rewriting historical labels",
        "hiding internal alpha cases behind design-start costs",
        "calling single-task different-seed runs cross-task MAML",
        "starting P1/P2/P3 without A5 review and a fresh Lead GO",
        "claiming V01/V02 12D response while beta=0",
        "reporting whole-aircraft drag or fuel burn from VSPAERO induced drag",
    ],
    "disclosures": [
        "P0 is zero-physical; G1 results are unchanged and not re-graded",
        "A5 reviews so far were deepseek-flash single-shot read-only, not human signatures",
        "same-host storage only; off-machine backup waived by Owner (m03569)",
        "M160 has zero G1 labels and 6 no-bracket replay cases",
        "G2 stopped at 102/240 starts under issue #14; no G2 receipt was issued",
    ],
}

(OUT / "p1_p2_p3_preregistration.json").write_text(
    json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"written": str(OUT / "p1_p2_p3_preregistration.json"),
                  "code_files_hashed": len(FILES),
                  "p1_starts": doc["p1"]["max_design_starts"]}, indent=2))
