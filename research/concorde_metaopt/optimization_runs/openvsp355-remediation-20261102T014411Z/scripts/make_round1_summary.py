# Build summary.json for the D-12D-003 Round-1 package from evidence files already in this run.
# No solver is started; this script only reads package JSON and writes one JSON file.
import json
import time
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]

def load(rel):
    return json.loads((RUN / rel).read_text(encoding="utf-8"))

install = load("install_provenance.json")
setup = load("evidence/vspaero7_setup_generation.json")
par = load("evidence/geometry_parity_355_vs_326.json")
asm = load("evidence/geometry_parity_assembled_355_vs_326.json")
asm_sha = asm["provenance"]["source_external_sha256"]
api = load("evidence/api_compat_355.json")
events = load("evidence/tooling_events.json")
budget = load("budget_request_round2.json")

ev = events["events"]
ev_ids = [e.get("event_id") for e in ev]
solver_starts = sum(int(e.get("solver_starts", 0)) for e in ev)
th, tn = setup["variants"]["thick"], setup["variants"]["thin"]
fus = par["wing_body"]["components"]["fuselage"]
sns = fus["only_new_nn_stats"]
bins = {
    "le_1e-6": sns["le_1e-6"],
    "gt_1e-6_le_1mm": sns["le_1mm"] - sns["le_1e-6"],
    "gt_1mm_le_10mm": sns["le_10mm"] - sns["le_1mm"],
    "gt_10mm_le_30_1mm": sns["le_30_1mm"] - sns["le_10mm"],
}

cats = {c["id"]: c for c in budget["categories"]}
summary = {
    "schema_version": 1,
    "run_id": RUN.name,
    "stage": "P1-P3 D-12D-003 Round-1: OpenVSP 3.55.0 side-install, API/geometry compatibility, archived VSPAERO diagnosis, offline area rule, Round-2 budget proposal, P4 plan-only draft",
    "approval": "Issue #4 / D-12D-003 (comment 6566994749)",
    "round": "Round-1 of at most two (D-12D-003); zero solver cases, one unbillable no-model vspaero.exe usage-banner probe (TG-008)",
    "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "git_sha_at_run_start": "5dcb0bf09335fd6f73363d0280a667286d6d20f9",
    "branch": "research/concorde-metaopt",
    "status": "ROUND1_EVIDENCE_COMPLETE_NO_GATE_APPROVED",
    "scope": {
        "new_physical_solver_starts": 0,
        "numerical_analysis_starts": 0,
        "solver_cases": 0,
        "billable_numerical_analyses": 0,
        "unbillable_version_probe_processes": 1,
        "process_level_proof_limitation": "no 4688/USN/ETW audit trail and Prefetch EPERM; the package proves zero solver cases / zero billable analyses, not process-level absence of any solver process (A1 F6)", 
        "budget_carryover": False,
        "d12d002_budget": {"cap": 23, "used": 23, "remaining": 0, "status": "CLOSED"},
        "d12d003_budget": {"approved": 0, "proposed": 23, "status": "AWAITING_OWNER_APPROVAL"},
        "p4_p6": "FROZEN",
        "pr_3": "open, not merged",
        "main_branch_untouched": True,
        "gate_approved": False,
    },
    "toolchain": {
        "archive": install["archive"],
        "new_install": {
            "root": install["new_install"]["root"],
            "version_reported": install["new_install"]["version_reported"],
            "vspaero_version_reported": install["new_install"]["vspaero_version_reported"],
            "python_version": install["new_install"]["python_version"],
            "vspaero_exe": setup["binaries"]["new_3_55_0_vspaero_install_root"],
            "no_global_install": install["new_install"]["no_global_install"],
            "path_or_site_packages_modified": install["new_install"]["path_or_site_packages_modified"],
            "expanded_archive": {"files": 491, "bytes": 149488735, "source": "role_reviews/a3/install_audit.md"},
            "expanded_after_first_import": {"files": 504, "bytes": 150078455, "note": "+13 .pyc runtime side effect (A1 F5)"},
        },
        "old_install_preserved": {
            "vspaero_exe": setup["binaries"]["old_3_26_1_vspaero"],
            "version_banner": setup["binaries"]["old_version_banner"],
            "untouched": True,
        },
        "isolation_verdict": "PASS (role_reviews/a3/install_audit.md): authentic archive, 491/491 expansion, API and vspaero version match, old installs unchanged, no PATH/registry/site-packages pollution; rollback static-only NOT_RUN",
    },
    "tooling_events": {
        "file": "evidence/tooling_events.json",
        "count": len(ev),
        "event_ids": ev_ids,
        "solver_starts": solver_starts,
        "note": "geometry export, API probes, setup generation (3 attempts), source retrieval and one no-model usage-banner probe (TG-008: 1 actual process launch, unbillable, no numerical analysis). All other events are non-billable tooling; zero solver cases",
    },
    "geometry_parity_355_vs_326": {
        "file": "evidence/geometry_parity_355_vs_326.json",
        "assembled_file": "evidence/geometry_parity_assembled_355_vs_326.json",
        "assembled_source_external_sha256": asm_sha,
        "method": par["method"],
        "wing": {
            "baseline_unique_vertices_old": par["wing_only"]["baseline"]["old"]["unique_old"],
            "baseline_unique_vertices_new": par["wing_only"]["baseline"]["old"]["unique_new"],
            "only_old": par["wing_only"]["baseline"]["old"]["old_not_new"],
            "only_new": par["wing_only"]["baseline"]["old"]["new_not_old"],
            "w10_plus2_identical_set": par["wing_only"]["w10_plus2"]["new_matches_old_vertex_set"],
            "w10_twist": par["wing_only"]["twist_check"],
        },
        "fuselage": {
            "old_unique": fus["old_unique"],
            "new_unique": fus["new_unique"],
            "only_old": fus["only_old"],
            "only_new": fus["only_new"],
            "nn_distance_m": {"median": sns["median"], "max": sns["max"]},
            "nn_histogram_bins": bins,
            "bbox_identical": True,
        },
        "conclusion": "wing vertex sets identical across versions; fuselage tessellation differs by at most 30.07 mm (0.049% of 61.66 m); paired area-rule comparisons must be single-version (3.55 for both wing-alone and wing+body); cross-version STL hashes are not a geometry identity test",
    },
    "api_compat": {
        "file": "evidence/api_compat_355.json",
        "version_reported": api["openvsp"]["version"],
        "api_name_count": api["openvsp"]["api_name_count"],
        "analyses_count": len(api.get("analyses", [])),
        "vspaero_sweep_input_count": len(api["analyses_probe"]["VSPAEROSweep"]["input_names"]),
        "wavedrag_input_count": len(api["analyses_probe"]["WaveDrag"]["input_names"]),
        "emintonlord_input_count": len(api["analyses_probe"]["EmintonLord"]["input_names"]),
        "result_capture_change": "must pass the ExecAnalysis result id to GetAllDataNames/Get*Results; passing the analysis name raises Error Code: 15",
        "degengeom_csv_change": "camber row has 11 fields in 3.26.1 vs 14 in 3.55.0; byte-diff of DegenGeom CSV is invalid",
        "import_recipe_change": "requires os.add_dll_directory(root) plus sys.path entries root/python/{openvsp,degen_geom,utilities,openvsp_config}",
        "repo_worker_gap": "aircraft/openvsp_geometry.py is 3.26-era (no add_dll_directory / openvsp_config); repository fix belongs to a reviewed card",
    },
    "setup_generation": {
        "file": "evidence/vspaero7_setup_generation.json",
        "method": "VSPAEROComputeGeometry ExecAnalysis for .vspgeom, then VSPAEROSweep with StopBeforeRun=1 for .vspaero; source guard returns before ForkCmd (VSPAEROMgr.cpp:2142-2146 vs :2149)",
        "solver_starts": setup.get("solver_start_count", 0),
        "variants": {
            "thick": {
                "geom_result_id": th["geom_result_id"],
                "vspgeom_bytes": th["vspgeom_bytes"],
                "vspgeom_sha256": th["vspgeom_sha256"],
                "mesh": "1082 nodes / 1088 elements (GeomSet=0)",
                "setup_file": th["setup_file"],
                "setup_bytes": th["setup_bytes"],
                "setup_lines": th["setup_lines"],
                "setup_sha256": th["setup_sha256"],
            },
            "thin": {
                "geom_result_id": tn["geom_result_id"],
                "vspgeom_bytes": tn["vspgeom_bytes"],
                "vspgeom_sha256": tn["vspgeom_sha256"],
                "mesh": "527 nodes / 480 elements (ThinGeomSet=0)",
                "setup_file": tn["setup_file"],
                "setup_bytes": tn["setup_bytes"],
                "setup_lines": tn["setup_lines"],
                "setup_sha256": tn["setup_sha256"],
            },
        },
        "injected_inputs": setup["injected_inputs"],
        "big_artifacts": {
            "archive_root": "outputs/concorde_metaopt/openvsp355-remediation-20261102T014411Z/vspaero7_setup_artifacts",
            "outside_git": True,
            "files": ["wing355_thick.vspgeom (503,013 B)", "wing355_thin.vspgeom (224,357 B)"],
        },
        "what_this_proves": setup["interpretation"]["what_this_proves"],
        "what_this_does_not_prove": setup["interpretation"]["what_this_does_not_prove"],
    },
    "archived_vspaero_diagnosis": {
        "source": "role_reviews/a1/vspaero_old_diagnostic.md, role_reviews/a1/vspaero_old_evidence.json",
        "invalid_cases": ["W01", "W03", "W10"],
        "invalid_reason": "12 template lines were written without '=' (e.g. 'Sref 358.25'); VSPAERO 6.2.0 silently used Sref=1.0, so printed coefficients were inflated by the case reference area (~358x); CDo=NaN(IND), Re ~1e-318",
        "invalid_case_check": {"printed_CL": [31.77605, 31.32113, 31.48770], "CL_after_dividing_by_case_Sref": [0.08782, 0.08743, 0.08789], "baseline_CL_2deg": 0.08781966},
        "valid_cases_issue": {
            "CDi_coarse_medium_fine": [3.435104e-4, -8.942229e-4, -2.260794e-2],
            "CDtot_negative_at": ["medium AoA 6 deg", "all fine AoA points"],
            "CL_coarse_to_fine_delta_pct": 29.09,
        },
        "harness_defects": ["non-zero vspaero -setup return code does not stop the solve", "template mismatch list stays empty", "polar has no finite/Re/negative-drag validation", "invalid data is still billed", "two template write paths"],
        "consequence": "LF-M2.02 stays NOT_VALIDATED / LF_PROVISIONAL; old VSPAERO 6.2.0 CL/CDi magnitudes must be marked not usable and are not rewritten",
    },
    "area_rule_offline": {
        "source": "role_reviews/a2/area_rule_offline.md, role_reviews/a2/area_rule_cases.csv, role_reviews/a2/area_rule_candidates.json",
        "port_validation": {"reproduces_archived_CDWave_rel_diff_max": 1.6e-6, "sears_haack_analytic_rel_err": {"n81": -1.55e-6, "n800": -1.55e-9, "n1600": -1.93e-10}, "theory_D_over_q": 0.10185916357881301},
        "conditioning": {"n50": 2.8e4, "n100": 2.3e5, "n200": 1.9e6, "n400": 1.5e7, "n800": 1.2e8},
        "noise_amplification_raw": {"sigma_0_002": 8.724, "sigma_0_005": 58, "sigma_0_1": 18380, "sigma_range_m2": [0.002, 0.1]},
        "calibrated_smoothing": {"lambda_rule": "27.84 * sigma^1.606", "sharp_break_bias_pct": -0.29, "fixed_savgol_bias_pct": -27.4},
        "mesh_convergence": {"mean_donq_ratio_36_200_vs_72_800": 2.87, "status": "NOT_CONVERGED"},
        "outliers": "WAVE-05 has 11 near-tangent theta artifacts (e.g. 73.52 deg Donq 742.48 m2) paired with 180-theta",
        "fuselage_increment": {"raw_m2": [2.924, 2.656], "smoothed_m2": [1.236, 1.410], "snr_raw": [0.89, 1.69], "verdict": "INCONCLUSIVE"},
        "verdict": "WAVE_AREA_RULE = NOT_VALIDATED; no correction may be injected; BODY-CORR stays BLOCKED",
    },
    "budget_round2_proposal": {
        "file": "budget_request_round2.json",
        "status": budget["status"],
        "approval_target": budget["approval_target"],
        "no_solver_started": budget["no_solver_started"],
        "categories": {cid: {"max_starts": c["max_starts"], "max_wall_clock_s": c["max_wall_clock_s"], "required": c["required"]} for cid, c in cats.items()},
        "total": budget["total"],
        "tiering": budget["tiering"],
        "not_covered": budget["not_covered"],
        "approval_note": budget["approval_note"],
    },
    "p4_plan_only": {"file": "p4_plan_only_draft.md", "status": "DRAFT / PLAN-ONLY / NOT APPROVED", "authorizes_nothing": True},
    "gates": {
        "GEO-12D": "PARTIAL",
        "LF-M2.02": "NOT_VALIDATED / LF_PROVISIONAL",
        "HF-M2.02": "PARTIAL",
        "BODY-CORR": "BLOCKED",
        "MISSION-DATA": "PARTIAL",
        "BUDGET": "AWAITING_OWNER_APPROVAL",
        "APPROVED_FOR_NEXT_STAGE": "NOT ISSUED (owner only)",
    },
    "role_reviews": {
        "A1": {"tasks": ["task-36", "task-37", "task-43"], "status": "completed; zero-solver audit CONFIRMED (repaired-code verification NOT_RUN: no budget)"},
        "A2": {"tasks": ["task-38", "task-39"], "status": "completed"},
        "A3": {"tasks": ["task-35", "task-42"], "status": "PASS (install audit; commit-isolation delta for dbc325d PASS 7/7)"},
        "A4": {"tasks": ["task-34", "task-44"], "status": "completed (35 requirements mapped; receipt DRAFT_NOT_POSTED)"},
        "A5": {"tasks": ["task-41"], "status": "APPROVE_FOR_DELIVERY (0 blocker / 0 major / 8 minor / 1 info)", "findings_resolved": "post-review revision 2"},
    },
    "figures": [{"path": "figures/geometry_parity_355_vs_326.png", "source": "evidence/geometry_parity_355_vs_326.json", "note": "unique-vertex parity and fuselage nearest-neighbour distribution; offline STL only"}],
    "review": {"status": "DELIVERY_APPROVED_INTERNAL", "delivery_review": "A5 task-41 APPROVE_FOR_DELIVERY, findings resolved in post-review revision 2; final commit and Issue #4 receipt pending Lead", "owner_decisions_needed": ["approve Round-2 budget per category", "authorize VSPAERO7 re-run after the LD-001 harness fix and guard tests", "authorize single-version 3.55 area-rule re-run", "decide whether to adopt P4 plan-only draft (does not un-freeze P4-P6)"]},
    "caveats": [
        "No solver was started; this run adds no physical evidence and must not be reported as a physical PASS.",
        "The 3.55 install is a side install; the repository OpenVSP worker still needs a reviewed fix card before any Round-2 automation uses 3.55.",
        "The archived VSPAERO 6.2.0 numbers are retracted as unusable; no historical file was rewritten.",
        "The area-rule inversion is ill-conditioned on the current geometry; even an owner-approved re-run may end INCONCLUSIVE unless the body/wing geometry or the slice set changes.",
        "The Round-2 budget proposal is the team's proposal, not an approval; D-12D-002's 23/23 is closed and does not carry over.",
        "TG-008: one unbillable, no-model vspaero.exe usage-banner process launch; it is not a solver case and consumed no budget (A1 F1).",
        "Process-level absence of any solver process is not proven (no 4688/USN/ETW trail, Prefetch EPERM); the claim is zero solver cases and zero billable analyses (A1 F6).",
        "The generated .vspaero files carry VSPAERO defaults ReCref 1e7 / Vinf 100 / Rho 0.002377, not the frozen contract values; Round-2 must inject and assert them (A1 F2).",
        "The 3.55 install added no PATH/registry/site-packages entry; OpenVSP 3.26.1's pre-existing User/Process PATH entries are untouched (A5 F-05).",
        "First python import adds 13 .pyc files to the 3.55 tree (504 files / 150,078,455 B live vs 491 / 149,488,735 B archive) (A1 F5).",
    ],
}
out = RUN / "summary.json"
out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
print("wrote", out.name, out.stat().st_size, "bytes")
print("checks:", summary["tooling_events"]["solver_starts"], summary["setup_generation"]["solver_starts"])
