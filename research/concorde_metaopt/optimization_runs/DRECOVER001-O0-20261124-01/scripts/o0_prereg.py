"""Pre-register the D-REAL-EXP-003 O0 real-BO protocol (zero physical).

Everything in this file is decided before a single solver start: the frozen task,
the 2D local subspace, the alpha search, the caps, the evaluation recipe, the
admission rule and the stop conditions. The A5 reviewer signs off on this exact
text plus the exact code SHAs, and only then can the Lead issue a GO record.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(RUN / "scripts"))

from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

import o0_eval as E  # noqa: E402
import o0_spend  # noqa: E402  (single authority on how spent budget is counted)

SCHEMA = "dreal005.o0_preregistration.v1"
PRE = RUN / "o0_preregistration.json"
DOSSIER = RUN / "o0_a5_dossier.md"

CODE_FILES = (
    "research/concorde_metaopt/dreal001/geometry/h0_contract.py",
    "research/concorde_metaopt/dreal001/ops/o0_short_bo.py",
    "research/concorde_metaopt/dreal001/ops/resource_monitor.py",
    "research/concorde_metaopt/dreal001/optimizers/recovery_bo.py",
    "research/concorde_metaopt/dreal001/geometry/solver_runner.py",
    "research/concorde_metaopt/dreal001/geometry/openvsp_model.py",
    "research/concorde_metaopt/dreal001/geometry/design_identity.py",
    "research/concorde_metaopt/dreal001/geometry/task_spec.py",
    "research/concorde_metaopt/dreal001/meta/real_admission.py",
    "research/concorde_metaopt/dreal001/meta/raw_verification.py",
    "research/concorde_metaopt/dreal001/meta/task_spec.py",
    "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
)
RUN_FILES = (
    "scripts/o0_eval.py",
    "scripts/o0_admit_case.py",
    "scripts/o0_prereg.py",
    "scripts/o0_run.py",
    "scripts/o0_final.py",
    "scripts/o0_fix_evidence.py",
    # The guards are frozen too. A GO, a verifier round and a review harness that could be
    # edited after the dossier was reviewed would make every gate above cosmetic.
    "scripts/o0_make_go.py",
    "scripts/o0_verify_binding.py",
    "scripts/o0_build_dossier.py",
    "scripts/o0_a5_review_tools.py",
    "scripts/o0_probe_production_loader.py",
    # Same reason for the O0-FINAL guard: the final GO is a second authorization and its
    # issuer has to be frozen before the review that blesses it.
    "scripts/o0_make_final_go.py",
    # The spend rule is frozen too: it is the single place that decides whether a record's
    # counters are batch-local or authorization-cumulative, and a rule that could be edited
    # after the review would let the carry-forward be recomputed into whatever is convenient.
    "scripts/o0_spend.py",
    "scripts/o0_retire_stale_go.py",
    # The final GO is retired by its own script: it binds a dossier byte-for-byte, so when the
    # dossier changes the old record must move to go_history/ rather than sit at the working path
    # looking like live authority. That script can therefore retire an authorization, and it is
    # frozen with the rest.
    "scripts/o0_retire_stale_final_go.py",
    # The repair of the crashed first verification attempt is part of the evidence, not a
    # housekeeping script: it decides which paid starts are void, and it can therefore change the
    # bill. It is frozen here so that the repair a reviewer reads is the repair that ran.
    "scripts/o0_repair_ledger.py",
    # The ledger's own tests are frozen for the same reason: a claim that the ledger cannot lose a
    # paid start is a claim about code, and the code that checks it must not move afterwards.
    "scripts/o0_final_selftest.py",
)
AUDIT_SCRIPT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def carried_forward() -> dict:
    """What earlier batches under this authorization already spent, counted once.

    The caps bind the authorization id, not one process, so the pre-registration must state
    the spent amount instead of printing zero. It must not re-derive that amount here: an
    abort record is batch-local while a crash record is authorization-cumulative, and summing
    both would bill 24 starts for the 23 that were actually spent. scripts/o0_spend.py owns
    that rule and this function only reports what it says.
    """
    spend = o0_spend.authorization_spend(RUN)
    return {"design_attempts": spend["design_attempts"],
            "solver_starts": spend["solver_starts"],
            "internal_solver_cases": spend["internal_solver_cases"],
            "records": [{"record": r["name"], "sha256": r["sha256"], "basis": r["basis"],
                         "designs": r["designs"], "starts": r["starts"],
                         "internal": r["internal"]} for r in spend["records"]],
            "counting_rule": spend["rule"], "basis_record": spend["basis_record"]}


def code_shas() -> dict:
    rows = {}
    for rel in CODE_FILES:
        path = REPO / rel
        rows[rel] = {"sha256": sha_file(path), "bytes": path.stat().st_size}
    for rel in RUN_FILES:
        path = RUN / rel
        if not path.is_file():
            rows[rel] = {"sha256": None, "bytes": None,
                         "status": "PENDING_AT_PREREG"}
            continue
        rows[rel] = {"sha256": sha_file(path), "bytes": path.stat().st_size}
    rows["D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py"] = {
        "sha256": sha_file(AUDIT_SCRIPT), "bytes": AUDIT_SCRIPT.stat().st_size}
    return rows


def main() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    h0 = json.loads((REPO / "docs/evidence/dreal005/h0/h0_gate.json").read_text(encoding="utf-8"))
    contract = json.loads((REPO / "docs/evidence/dreal005/h0/geometry_contract.json")
                          .read_text(encoding="utf-8"))
    design_ids = {d["design_id"]: d["x12"] for d in [o0.design_identity(x) for x in
                                                    (o0.BASELINE_X12,)]}
    prior = carried_forward()
    # The design cap binds before the stored ceilings do: 12 designs x 2 starts = 24 < 36 and
    # 12 designs x 20 internal = 240 = 240. Spendable budget is therefore the design-derived
    # number, and the stored solver-start ceiling is inert arithmetic.
    spendable_starts = min(int(o0.CAPS["max_solver_starts"]),
                           int(o0.CAPS["max_design_attempts"]) * int(o0.CAPS["max_starts_per_design"]))
    spendable_internal = min(int(o0.CAPS["max_internal_cases"]),
                             int(o0.CAPS["max_design_attempts"])
                             * int(o0.CAPS["max_internal_per_design"]))
    bootstrap = [{"design_id": o0.design_identity(x)["design_id"],
                  "sweep_1": x[2], "sweep_2": x[3],
                  "is_baseline": o0.design_identity(x)["is_baseline"]}
                 for x in o0.bootstrap_designs(4)]
    payload = {
        "schema": SCHEMA,
        "issue": 15,
        "stage": "O0",
        "run_id": E.RUN_ID,
        "batch_id": E.batch_id(),
        "authorization_id": E.AUTH_ID,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol_id": o0.PROTOCOL_ID,
        "owner_authorization_ref": E.OWNER_REF,
        "nature": ("pre-registration only; it authorizes nothing by itself. A separate "
                   "A5 verdict on this exact dossier and a Lead GO record with matching "
                   "SHAs are required before any solver start."),
        "h0": {
            "gate_file": "docs/evidence/dreal005/h0/h0_gate.json",
            "h0_gate_sha256": h0["h0_gate_sha256"],
            "geometry_contract_sha256": h0["geometry_contract_sha256"],
            "code_bundle_sha256": h0["code_bundle_sha256"],
            "physical_solver_starts_actual": h0["physical_solver_starts_actual"],
            "gates_pending_a5": [k for k, v in h0["gates"].items() if v == "PENDING_A5_REVIEW"],
        },
        "task": dict(o0.TASK),
        "task_physics_sha256": E.task_spec().physics_sha256,
        "geometry": {
            "contract_sha256": h0["geometry_contract_sha256"],
            "design_id_rule": "sha256 of the frozen 12D vector (design_identity.design_hash)",
            "baseline_x12": list(o0.BASELINE_X12),
            "baseline_design_id": o0.design_identity(o0.BASELINE_X12)["design_id"],
            "variable_order": list(o0.VARIABLE_ORDER),
            "physical_15_names": list(o0.PHYSICAL_15_NAMES),
            "fixed_15": dict(o0.FIXED_15),
            "frozen_non_active_variables": [n for n in o0.VARIABLE_ORDER
                                            if n not in o0.SUBSPACE_INDEX],
        },
        "search_space": {
            "subspace": ["sweep_1", "sweep_2"],
            "bounds": {k: list(v) for k, v in o0.SUBSPACE_BOUNDS.items()},
            "selection_rule": ("chosen from the measured 12D CDi response audit "
                               "(sweep_1 max|dCDi| 1.707e-3, sweep_2 6.977e-4, wing_area "
                               "1.45e-10); NOT chosen from any meta-learning result"),
            "bootstrap": {"method": "LHS on the frozen box, baseline forced first",
                          "count": o0.CAPS["bootstrap_attempts"],
                          "seed": 20261124, "designs": bootstrap},
            "adaptive": {"backend": "RECOVERY_NUMPY_RBF_GP_EI_V1",
                         "acquisition": "GP EI on feasibility-weighted observations",
                         "max_adaptive_attempts": o0.CAPS["max_adaptive_attempts"]},
        },
        "alpha_search": o0.alpha_plan(),
        "evaluation_recipe": {
            "starts_per_design": 2,
            "start_1": "7-point coarse bracket around 5.18 deg (spans 2.1 deg)",
            "start_2": ("13-point refinement centred on the coarse quadratic CL(alpha) "
                        "root, +/-0.024 deg at 0.004 deg resolution"),
            "internal_cases_per_design": 20,
            "charge_policy": ("both starts and all internal alpha cases are charged even "
                              "when the design ends infeasible; retries are never allowed"),
            "solver": {"path": str(E.EXE), "sha256": sha_file(E.EXE),
                       "version_banner": "VSPAERO v.7.2.2", "omp_threads": 1,
                       "timeout_s": o0.CAPS["solver_timeout_s"]},
        },
        "admission_rule": {
            "tolerance_rel": 1e-3,
            "tolerance_relaxed": False,
            "authority": ("admit_real_manifest re-reads the raw bytes and requires an "
                          "ACTUAL polar row satisfying |q*Sref*CL - L_ref|/L_ref <= 1e-3; "
                          "interpolated rows are never promoted"),
            "objective": "Di_N = q * Sref * CDi of that admitted raw row",
            "sref": "per-design, recomputed from the actual geometry",
        },
        "caps": dict(o0.CAPS),
        "stop_conditions": [
            "the baseline design (bootstrap design 0) fails: the batch aborts at once and "
            "the remaining budget is not spent, because a baseline failure means the "
            "protocol rather than the aerodynamics is broken",
            "any spendable cap reached (12 designs, or the 24 starts and 240 internal cases "
            "that the design cap implies; the stored 36-start ceiling is unreachable)",
            "two consecutive designs with no solver result at all",
            "three consecutive designs with no admitted raw row: the loop stops with budget "
            "deliberately unspent (at most 6 charged starts) instead of grinding out 12 misses",
            "wall clock 3300 s",
            "any accounting inconsistency (ledger charge rejected)",
            "upload + remote readback after every 8 starts or 60 minutes, before continuing",
        ],
        "deliverables": [
            "raw_cases/ with every case's .vsp3/.vspgeom/.vspaero/.polar/.history/.adb, decks, "
            "mesh/wake, stdout/stderr, exit code and timeout flag",
            "tables/all_evaluations.csv, admitted_labels.csv, failed_or_null.csv, "
            "optimization_history.csv, acquisition_trace.csv, actual_solver_ledger.csv",
            "tables/resource_usage.csv + figures with CPU and memory during the optimization",
            "final_aircraft/ with baseline.vsp3, optimized.vsp3, design_before_after.csv, "
            "optimized_design.json, performance_before_after.csv, constraint_report.json, "
            "verification_receipt.json, figures/ and the independent O0-FINAL re-run",
            "SHA256SUMS.txt, data_manifest.json and a GitHub readback audit",
        ],
        "o0_final": {
            "rule": ("the final candidate must be an admitted, non-baseline design; it is "
                     "re-run with a fresh case_id and an empty directory, and the baseline "
                     "is re-run the same way"),
            "repeatability": "same frozen configuration, two independent re-runs",
            "design_selection": {
                "baseline": "the admitted row flagged is_baseline (bootstrap design 0)",
                "best": ("the admitted non-baseline row with the lowest Di_N of the optimizer "
                         "batch, which is the objective being maximised downward"),
                "when_identities_are_fixed": ("the selection rule is fixed here, before any "
                                              "batch runs; the two design identities and the "
                                              "batch result SHA256 are bound by the separate "
                                              "O0-FINAL GO record, because a design id cannot "
                                              "be written into a pre-registration that precedes "
                                              "the batch that produced it"),
            },
            "separate_budget": {
                "verification_starts_max": 8,
                "verification_internal_cases_max": 104,
                "wake_probe_starts_max": 2,
                "void_rows_max": 2,
                "note": ("this is a separately itemized verification ledger; it is never "
                         "folded into the O0 optimizer caps, and the wake probe cases are "
                         "never admitted because the admitted wake count is fixed at 8. The "
                         "budget covers the whole of the verification step, including the "
                         "three starts the crashed first attempt already spent, because a "
                         "replacement batch that ignored them would need nine starts and "
                         "would misreport what the verification actually cost."),
                "itemization": [
                    "2 void rows: the baseline repeats the crashed first attempt spent at 2 "
                    "wake nodes, below the admission mesh of 8; already paid for, never "
                    "admissible, never re-run, 13 alpha cases each = 26 internal cases",
                    "1 wake-probe start already spent: the baseline solved at 16 wake nodes, "
                    "which completed before the crash and whose paid output is on the disk; "
                    "never admitted, not re-run, 13 alpha cases = 13 internal cases",
                    "4 repeat starts still to spend: baseline and best at the reference mesh, "
                    "two independent re-runs each, 13 refinement alpha cases per start = 52 "
                    "internal cases",
                    "1 wake-probe start still to spend: the best design at 16 wake nodes, "
                    "never admitted, 13 alpha cases = 13 internal cases",
                    "26 + 13 + 52 + 13 = 104 internal cases, and 2 + 1 + 4 + 1 = 8 starts in "
                    "total, of which 3 starts are already spent",
                ],
                "max_repeat_runs_per_design": 2,
                "n_wake_nodes_reference": 8,
                "n_wake_nodes_probe": 16,
                "refinement_points": 13,
                "why_it_is_not_extra_optimizer_budget": ("the optimizer cap is a search "
                                                         "budget; these repeats cannot propose "
                                                         "or admit a new design, they can only "
                                                         "measure two already-selected ones "
                                                         "again"),
            },
            "authorization": {
                "requires_its_own_a5_review": True,
                "requires_its_own_go": True,
                "go_file": "o0_final_go_record.json",
                "authorization_kind": "O0_FINAL_VERIFICATION",
                "may_start_only_after": ("the optimizer batch is closed by a batch record; a "
                                         "verification start spent while the optimizer is still "
                                         "running would be unauditable"),
                "ledger_file": "o0_final/verification_ledger.json",
                "ledger_must_survive_a_crash": ("the ledger is written after every charge and "
                                                "read back on start-up, so a run that dies "
                                                "after three starts restarts owing three"),
                "no_repeat_of_a_charged_label": ("one label is one case; spending a second "
                                                 "start for a label already in the ledger is "
                                                 "refused rather than silently double-charged"),
            },
            "row_kinds": {
                "repeat": ("a reference-mesh repeat of one of the two designs; it may be "
                            "admitted"),
                "wake": ("a 16-wake-node probe; it can never be admitted, because the admission "
                          "mesh is fixed at 8 wake nodes"),
                "void": ("a start already spent on a mis-configured case; it is charged so the "
                          "bill matches the disk, it is never admitted, and it is never re-run. "
                          "The kind is set by the plan entry and is never inferred from a wake "
                          "count, which is exactly how the first attempt mislabelled two "
                          "repeats as probes"),
            },
            "repair_of_the_first_verification_attempt": {
                "what_happened": ("the first attempt at section 4b died on its third start with "
                                   "'wake probe cap exceeded: 2 rows'. The two rows that had been "
                                   "charged were the baseline repeats, and they had been charged "
                                   "as kind=wake because the runner derived the kind from the "
                                   "wake count and gave every repeat 2 wake nodes instead of the "
                                   "admission mesh of 8"),
                "what_was_already_spent": ("3 real solver starts and 39 internal alpha cases: "
                                            "final-baseline-r1 and final-baseline-r2 at 2 wake "
                                            "nodes, and final-baseline-wake16 at 16 wake nodes, "
                                            "which completed with its polar and case_result.json "
                                            "still on the disk"),
                "what_was_wrong_with_the_ledger": ("it recorded 2 starts and 26 internal cases, "
                                                    "both mislabelled kind=wake, and it was "
                                                    "missing the third start entirely, because "
                                                    "the charge happened after the run instead "
                                                    "of before it"),
                "what_the_repair_changes": [
                    "the kind is now a plan field, never derived from a number",
                    "the charge happens before the solver is spawned, so a crash cannot lose a "
                    "paid start, and a crash after a charge writes a record next to it",
                    "the two mislabelled repeats are re-charged as void rows with the sha256 of "
                    "the polar and case_result.json that back them",
                    "the completed 16-wake-node probe is charged as a wake row, not re-run",
                    "the budget becomes 8 starts and 104 internal cases, of which 3 starts and "
                    "39 internal cases are already spent",
                ],
                "what_the_repair_does_not_do": [
                    "it does not re-classify a paid start as unspent",
                    "it does not re-run any case that already produced paid output",
                    "it does not spend a solver start",
                    "it does not widen any optimizer cap",
                ],
                "spent_before_this_pre_registration": 3,
                "internal_before_this_pre_registration": 39,
                "remaining_to_spend": 5,
                "remaining_internal": 65,
                "attempts_that_spent_nothing": [
                    {
                        "what_happened": ("after the ledger repair and a fresh A5 PASS, the "
                                          "repaired run died on its first planned case with "
                                          "'TypeError: object of type int has no len()' inside "
                                          "attempt_refine, before the charge and before the "
                                          "solver was spawned"),
                        "root_cause": ("o0_eval.make_case() returns alpha_points as the count of "
                                       "alpha points, and the new pre-charge code read it as the "
                                       "list; the charge therefore threw while computing its own "
                                       "amount, which is the one way a pre-charge can still lose "
                                       "a start"),
                        "what_it_cost": ("nothing: the failure happened before the charge was "
                                         "written and before any VSPAERO process was spawned. "
                                         "The ledger still reads 3 starts / 39 internal cases and "
                                         "every new case directory holds preparation files only, "
                                         "with no polar and no case_result.json"),
                        "how_it_is_closed": ("the planned cost is now computed by "
                                             "planned_internal_for(), which accepts either the "
                                             "count or the list and is tested without a solver; "
                                             "two further tests pin the wiring: the kind comes from "
                                             "the plan and never from a wake count, and repeat "
                                             "cases are planned at the reference wake mesh of 8"),
                        "how_it_is_prevented_from_recurring": ("o0_final_selftest.py covers the "
                                                               "cost helper, the explicit kind "
                                                               "wiring and the non-admissibility "
                                                               "of wake rows; it runs 12 checks "
                                                               "with zero solver starts"),
                    },
                ],
            },
            "verdicts": ["VERIFIED_IMPROVEMENT", "FEASIBLE_NO_VERIFIED_IMPROVEMENT",
                         "PROVISIONAL_CANDIDATE", "NO_FEASIBLE_NONBASELINE"],
            "extra_budget": ("no extra optimizer starts are spent beyond the O0 search cap; the "
                             "8 verification starts above are a separate itemized ledger that "
                             "cannot propose or admit a new design, and anything beyond them must "
                             "be requested as another limited batch"),
        },
        "code_shas": code_shas(),
        "not_authorized": [
            "any VSPAERO start before the A5 verdict and the Lead GO record",
            "O1 warm-start arms",
            "any change to the lift tolerance, target lift or reference quantities",
            "re-use of an old GO or an old authorization id",
        ],
        "carried_forward": prior,
        "batch_budget_statement": (
            "the caps below bind the authorization id, not one process. What the authorization "
            "can actually spend is min(stored cap, design cap x per-design cost) = %d starts and "
            "%d internal cases, because the design cap binds first. %d solver start(s) and %d "
            "internal alpha case(s) are already spent under this authorization, so a GO can "
            "authorize at most %d further starts, %d further internal cases and %d further "
            "design attempts"
            % (spendable_starts, spendable_internal, prior["solver_starts"],
               prior["internal_solver_cases"],
               spendable_starts - prior["solver_starts"],
               spendable_internal - prior["internal_solver_cases"],
               int(o0.CAPS["max_design_attempts"]) - prior["design_attempts"])
            + ("" if int(o0.CAPS["max_design_attempts"]) - prior["design_attempts"] > 0 else
               ". No further optimizer design may be proposed: the design cap is spent, so the "
               "residue of %d start(s) and %d internal case(s) is stranded rather than "
               "available. The only physics this pre-registration leaves for authorisation is "
               "the separate O0-FINAL verification budget recorded under o0_final."
               % (spendable_starts - prior["solver_starts"],
                  spendable_internal - prior["internal_solver_cases"]))),
        "physical_solver_starts_actual": prior["solver_starts"],
        "internal_solver_cases_actual": prior["internal_solver_cases"],
        "physics_validated": False,
    }
    PRE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pre_sha = sha_file(PRE)
    print(json.dumps({"preregistration": str(PRE), "sha256": pre_sha,
                      "code_files": len(payload["code_shas"]),
                      "pending": [k for k, v in payload["code_shas"].items()
                                  if v.get("status")]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())