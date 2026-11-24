"""Freeze the O1 preregistration before a single solver start is spent.

This records: the new task and its physics hash, the frozen geometry contract, the shared
search subspace and alpha recipe inherited from O0, the three arms, the shared support and
candidate pool seeds, the cost model and caps, the preregistered target, the exact sha256 of
every code file that will spend the budget, and the carried-forward O0 bill.

Run: python scripts/o1_prereg.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
O0_RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
sys.path.insert(0, str(RUN / "scripts"))
sys.path.insert(0, str(REPO))

import o1_arms as arms  # noqa: E402
import o1_eval as ev  # noqa: E402

CODE_ROOT = RUN / "scripts"
# Every file that can spend, gate or sign the O1 budget is frozen here. The two authorisation
# files are included on purpose: they decide whether a start happens at all, so a GO that froze
# only the solver-facing code would leave the gates editable.
CODE_FILES = ("o1_eval.py", "o1_arms.py", "o1_run.py", "o1_admit_case.py",
              "o1_prereg.py", "o1_selftest.py", "o1_verify_binding.py", "o1_make_go.py",
              "o1_build_dossier.py", "o1_retire_stale.py")

PREREG = RUN / "o1_preregistration.json"


def sha(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def o0_carried_forward() -> dict:
    """The O0 bill, read from the records O0 itself wrote (never re-derived by hand)."""
    spend = {"optimizer": None, "final_verification": None}
    for path in sorted(O0_RUN.glob("o0_batch_crash_*.json")) + sorted(
            O0_RUN.glob("o0_batch_close_*.json")):
        pass
    close = O0_RUN / "o0_batch_close_B02.json"
    if close.exists():
        payload = json.loads(close.read_text(encoding="utf-8"))
        spend["optimizer"] = {
            "source": str(close), "source_sha256": sha(close),
            "authorization_spend": payload.get("authorization_spend"),
            "batch_spend": payload.get("batch_spend"),
        }
    ledger = O0_RUN / "o0_final" / "verification_ledger.json"
    if ledger.exists():
        payload = json.loads(ledger.read_text(encoding="utf-8"))
        rows = payload.get("rows") or []
        spend["final_verification"] = {
            "source": str(ledger), "source_sha256": sha(ledger),
            "starts": sum(int(row.get("starts", 0)) for row in rows),
            "internal": sum(int(row.get("internal", 0)) for row in rows),
        }
    return spend


def main() -> int:
    tasks = {}
    for key in sorted(ev.TASK_REGISTRY):
        spec = ev.task_spec(key)
        flow = ev.flow_for(float(ev.TASK_REGISTRY[key]["mach"]))
        tasks[key] = {
            "task_id": spec.task_id, "mach": spec.mach, "altitude_m": spec.altitude_m,
            "dynamic_pressure_pa": spec.dynamic_pressure_pa,
            "lift_target_n": spec.lift_target_n,
            "physics_sha256": spec.physics_sha256,
            "flow": flow, "split": ev.TASK_REGISTRY[key]["split"],
        }
    history_physics = set()
    a0_dataset = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01/dataset/a0_dataset.json")
    if a0_dataset.exists():
        payload = json.loads(a0_dataset.read_text(encoding="utf-8"))
        for task in payload.get("tasks") or []:
            if task.get("physics_sha256"):
                history_physics.add(task["physics_sha256"])
    collision = {key: value["physics_sha256"] for key, value in tasks.items()
                 if value["physics_sha256"] in history_physics}
    if collision:
        raise SystemExit("a new O1 task collides with a historical physics hash: %r" % (collision,))

    payload = {
        "schema": "dreal005.o1_preregistration.v1",
        "issue": "Issue #15 D-REAL-EXP-003 section 6 (O1 three-arm warm start)",
        "stage": "O1",
        "run_id": ev.RUN_ID,
        "batch_id": "%s-PAIRING-01" % (ev.RUN_ID,),
        "authorization_id": ev.AUTH_ID,
        "created_utc": ev.now(),
        "protocol_id": arms.PROTOCOL_ID,
        "owner_authorization_ref": ev.OWNER_REF,
        "nature": {
            "physical_solver_starts_spent_by_this_preregistration": 0,
            "this_is": ("a zero-physical registration of the O1 three-arm comparison; it "
                        "authorises nothing on its own"),
            "requires_a_separate_a5_review": True,
            "requires_a_separate_go_record": True,
            "go_file": "o1_go_record.json",
        },
        "why_three_arms": (
            "Issue #15 section 6 asks whether a meta-learned warm start beats a plain Sobol "
            "warm start at equal real evaluation cost. The comparison is therefore three arms "
            "that differ ONLY in how the three extra initialisation designs are chosen."),
        "arms": {
            "order": list(arms.ARMS),
            "SOBOL_BO": {
                "warm_start_rule": "three LHS designs from seeds %d, shared by every Sobol arm "
                                   "and independent of any model" % (arms.WARM_START_SEED,),
                "model": None,
            },
            "COND_SUPERVISED_KSHOT_BO": {
                "warm_start_rule": ("rank the common candidate pool with the frozen A0 "
                                    "COND_SUPERVISED_16D checkpoint after K=3 support "
                                    "adaptation, then take the top three"),
                "model": {"checkpoint_arm": "COND_SUPERVISED_16D",
                          "checkpoint": "A0 training/checkpoints/COND_SUPERVISED_16D_k3_seed7.npz",
                          "k_support": arms.K_SUPPORT,
                          "uses_test_labels": False,
                          "uses_optimizer_feedback": False},
            },
            "COND_FOMAML_KSHOT_BO": {
                "warm_start_rule": ("rank the common candidate pool with the frozen A0 "
                                    "COND_FOMAML_16D checkpoint after K=3 support adaptation, "
                                    "then take the top three"),
                "model": {"checkpoint_arm": "COND_FOMAML_16D",
                          "checkpoint": "A0 training/checkpoints/COND_FOMAML_16D_k3_seed7.npz",
                          "k_support": arms.K_SUPPORT,
                          "uses_test_labels": False,
                          "uses_optimizer_feedback": False},
            },
            "held_equal": [
                "the same three real shared support designs",
                "the same 256-design candidate pool of coordinates (no truth pre-computed)",
                "the same GP backend RECOVERY_NUMPY_RBF_GP_EI_V1 with the same seed and "
                "hyperparameters (candidate_count 256, length_scale 0.35, noise 1e-6)",
                "the same coarse/refine alpha recipe, lift tolerance, audit and admission gate",
                "the same geometry contract and the same frozen two-dimensional subspace",
                "each arm's adaptive proposals use only that arm's own real feedback",
            ],
            "cost_modelling": ("the three shared support designs are solved once but charged in "
                               "full to all three arms; the physical and equivalent bills are "
                               "reported separately and never conflated"),
        },
        "pairing": {
            "task_key": "O1-M190",
            "pairing_seed": arms.PAIRING_SEED,
            "gp_seed": arms.GP_SEED,
            "n_tasks_executed_in_this_pairing": 1,
            "why_this_task": ("Mach 1.90 is named in Issue #15 section 6 as the first-pairing "
                              "candidate; its physics hash does not appear in any historical "
                              "A0 label, so it is a genuinely new task"),
            "future_pairings_not_authorised_here": ["O1-M210 at seed 19 and seed 43"],
        },
        "tasks": tasks,
        "task_collision_check": {
            "historical_physics_hashes_considered": len(history_physics),
            "collisions": collision,
            "source": str(a0_dataset),
        },
        "geometry": {
            "contract_sha256": ev.GEOM,
            "sref_note": ("Sref is the design's own wing area as reported by the geometry "
                          "model; it is not pinned to 358.25 for non-baseline designs"),
            "subspace": {
                "index": dict(arms.o0.SUBSPACE_INDEX) if hasattr(arms.o0, "SUBSPACE_INDEX") else {},
                "lower": list(arms.SUBSPACE_LOWER), "upper": list(arms.SUBSPACE_UPPER),
                "frozen_from": "O0-SHORT-BO-20261124",
                "not_claimed": "a full 12-variable optimisation",
            },
        },
        "alpha_search": {"plan": arms.ALPHA_PLAN,
                         "lift_tolerance_rel": 1e-3,
                         "tolerance_is_not_relaxed": True},
        "admission_rule": {
            "gate": "audit_real_case.py then o1_admit_case.py",
            "requires": ("an actual raw polar row within 1e-3 relative lift error, an "
                         "independent recomputation of the deck/polar and a bound "
                         "artifact manifest"),
            "interpolated_rows_never_admitted": True,
        },
        "shared_support": {
            "count": arms.SHARED_SUPPORT_COUNT, "seed": arms.SHARED_SUPPORT_SEED,
            "first_design_is_baseline": True,
            "design_ids": [arms.o0.design_identity(list(d))["design_id"]
                           for d in arms.support_designs()],
            "must_all_be_admitted": True,
        },
        "candidate_pool": {
            "count": arms.CANDIDATE_POOL_COUNT,
            "seed": arms.CANDIDATE_POOL_SEED,
            "contains_objectives": False,
            "overlap_rule": (
                "the pool and the Sobol warm-start triple are drawn from the same LHS "
                "generator with different seeds (20261126 vs 20261125). No coordinate is "
                "excluded in advance, because a pool point can only help an arm by being "
                "ranked or proposed, and every design is scored by the same real evaluation "
                "regardless of where its coordinates came from. Any arm that would propose a "
                "design already present in its own ledger (shared support included) skips it "
                "and takes the next one, so no arm can be charged twice for one design. The "
                "SOBOL arm never reads the pool; the two K-shot arms rank the pool but receive "
                "no objective value for any point in it."),
            "pool_sha256": arms.canon([list(d) for d in arms.candidate_pool()]),
            "sobol_warm_start_sha256": arms.canon([list(d) for d in arms.sobol_warm_start()]),
            "pool_minus_sobol_overlap_count": len(
                {arms.o0.design_identity(list(d))["design_id"] for d in arms.candidate_pool()}
                & {arms.o0.design_identity(list(d))["design_id"]
                   for d in arms.sobol_warm_start()}),
        },
        "budgets": {
            "target_improvement_fraction": arms.TARGET_IMPROVEMENT_FRACTION,
            "target_derivation": (
                "fixed before any O1 result exists; a 0.1% Di reduction is an order of "
                "magnitude above the 1e-3 relative lift tolerance that bounds the reported "
                "drag, and O0 already demonstrated a reachable 0.2394% effect"),
            "reference_point": "the pre-designated baseline design inside the shared support",
            "caps": dict(arms.CAPS),
            "cost_model": {"internal_per_design": arms.INTERNAL_PER_DESIGN,
                           "starts_per_design": arms.STARTS_PER_DESIGN,
                           "affordable_designs_per_arm": arms.CAPS["affordable_designs_per_arm"],
                           "per_arm_equivalent": {
                               "designs": arms.CAPS["affordable_designs_per_arm"],
                               "starts": arms.CAPS["affordable_designs_per_arm"] * arms.STARTS_PER_DESIGN,
                               "internal": arms.CAPS["affordable_designs_per_arm"] * arms.INTERNAL_PER_DESIGN},
                           "all_arms_equivalent": {
                               "starts": (3 * arms.CAPS["affordable_designs_per_arm"]
                                          * arms.STARTS_PER_DESIGN),
                               "internal": (3 * arms.CAPS["affordable_designs_per_arm"]
                                            * arms.INTERNAL_PER_DESIGN)},
                           "physical_if_everything_admits": (
                               "48 equivalent minus 2 x 3 shared support starts = 36"),
                           "why_160_binds": ("the internal cap binds before the 12-design and "
                                             "24-start caps, so eight designs per arm is the "
                                             "honest affordable number, and every arm is "
                                             "truncated at the same place"),
                       },
            "truncation_rule": ("all three arms are truncated at the same design count; the "
                                "report must say so instead of pretending the arms spent "
                                "identical effort by accident"),
        },
        "stop_conditions": [
            "any shared support design fails to admit a raw row -> abort before any arm starts",
            "an arm reaches eight designs -> stop that arm",
            "a solver start returns a non-SOLVED status -> record it as a paid failure, keep "
            "charging, do not retry (retries are zero)",
            "a wall-clock or internal cap would be exceeded -> abort rather than overspend",
        ],
        "primary_endpoints": [
            "best_feasible_Di_N at equal equivalent starts/internal",
            "equivalent starts needed to reach the preregistered target Di",
            "the anytime curve (best feasible Di against cumulative equivalent starts)",
            "point-level and run-level feasible rate",
        ],
        "not_claimed": ["global optimum", "regret", "aerodynamic validation",
                        "that the meta objective is superior (A0 did not establish it)",
                        "that a seed is an independent task"],
        "deliverables": [
            "o1_result.json with the primary endpoints and both cost ledgers",
            "o1_shared_support.json, one file per arm, o1_attempts.jsonl",
            "every raw solver artifact under cases/ uploaded and read back from GitHub",
            "the best geometry for each arm exported as vsp3/stl/step",
            "figures and tables, including an anytime comparison across the three arms",
        ],
        "code": {
            "code_root": str(CODE_ROOT),
            "code_files": list(CODE_FILES),
            "code_shas": {name: sha(CODE_ROOT / name) for name in CODE_FILES},
            "repo": str(REPO),
            "repo_head": json.loads((REPO / ".git" / "HEAD").read_text(encoding="utf-8")) if False else None,
        },
        "carried_forward": o0_carried_forward(),
        "not_authorized": [
            "Mach 2.10 or any second pairing task",
            "a second seed for the same task",
            "more than eight designs per arm in this pairing",
            "any change to the GP, the alpha recipe, the geometry contract or the tolerance",
            "reusing an old GO",
            "touching main or merging any pull request",
        ],
        "authorization_artifacts": {
            "why_this_is_preregistered": (
                "a GO is only meaningful if it binds the bytes that are on disk now; if a "
                "verdict or a binding round for superseded bytes stays on the live path, a GO "
                "issued today cannot be told apart from a GO issued against the old bytes"),
            "retirement_rule": (
                "an artifact is retired only when it names a dossier or preregistration sha256 "
                "that is not on disk; it is copied into dated history, verified byte for byte, "
                "and only then removed from the live path; nothing is deleted outright"),
            "retired_never_overwritten": True,
            "retire_record": "o1_retire_record.json",
            "retire_script": "scripts/o1_retire_stale.py",
            "live_path_after_retirement": (
                "exactly one verdict and at most one binding round, both naming the dossier "
                "bytes on disk"),
            "go_gate": (
                "o1_make_go.py refuses unless the binding round and the verdict both bind the "
                "dossier sha256 on disk, so a GO for other bytes cannot be issued"),
        },
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
        "physics_validated": False,
    }
    PREREG.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("preregistration written: %s (%d B)" % (PREREG, PREREG.stat().st_size))
    print("sha256: %s" % (sha(PREREG),))
    print("code shas: %s" % (json.dumps(payload["code"]["code_shas"], indent=2),))
    return 0


if __name__ == "__main__":
    sys.exit(main())
