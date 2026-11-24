"""O0-FINAL: independent re-verification of the baseline and the best feasible design.

The optimizer batch and this verification are two separate budgets. The optimizer spends its
own ledger (which B02 exhausted); this file spends a separately itemized verification ledger
that is fixed in the pre-registration under o0_final.separate_budget and is never folded into
the optimizer caps.

Hard gates before the first start, because "the dossier did not mention this budget" is
exactly how unauthorized physical work happens:
  * o0_final_go_record.json must exist and be issued;
  * its A5 verdict must be the expected PASS and must bind to the current dossier bytes;
  * its byte verifier round must read the current dossier bytes;
  * its pre-registration hash must equal the current pre-registration;
  * the designs it authorizes must be the designs this run picks, by design id;
  * the ledger caps must equal the caps in the pre-registration, not a number typed here.

Each re-run uses a fresh case id in its own batch directory and re-derives everything from the
frozen geometry, so nothing is copied from the optimization batch except the design vector and
the recorded fixed-lift alpha (used only as the refinement centre).

The ledger persists after every charge and is read back on start-up: a crashed verification
must not restart with a clean bill. A label already in the ledger may never be charged twice.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(RUN / "scripts"))

import o0_eval as ev  # noqa: E402
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

PRE = RUN / "o0_preregistration.json"
DOSSIER = RUN / "o0_a5_dossier.md"
VERDICT = RUN / "a5_review/verdict.json"
RECEIPT = RUN / "o0_dossier_receipt.json"
GO = RUN / "o0_go_record.json"
FINAL_GO = RUN / "o0_final_go_record.json"
BEYOND = RUN / "o0_binding_verification.json"
OUT = RUN / "o0_final"
LEDGER = OUT / "verification_ledger.json"
ROUNDS = OUT / "o0_final_rounds.json"
PLAN = OUT / "o0_final_plan.json"
RESULT_VERDICT = OUT / "o0_final_verdict.json"

CAPS = {"max_verification_starts": 8, "max_verification_internal_cases": 104,
        "max_repeat_runs_per_design": 2, "max_wake_probe_starts": 2, "max_void_rows": 2,
        "n_wake_nodes_reference": 8, "n_wake_nodes_probe": 16,
        "refinement_points": 13}
EXPECTED_VERDICT = "H0_A0_O0_REVIEW_PASS"


def sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


class Ledger:
    """Verification-only counter. It reads its own history and refuses to write past its caps.

    The caps come from the pre-registration, so this object cannot authorize a budget the A5
    review never saw. Rows are persisted after every charge: a run that dies after three starts
    restarts owing three starts, not zero.
    """

    def __init__(self, path: Path, caps: Dict[str, Any]):
        self.path = path
        self.caps = dict(caps)
        self.rows: List[Dict[str, Any]] = []
        self.prior_sha256 = None
        if path.is_file():
            self.prior_sha256 = sha_file(path)
            state = json.loads(path.read_text(encoding="utf-8"))
            self.rows = [row for row in (state.get("rows") or [])]

    def totals(self) -> Dict[str, int]:
        return {
            "starts": sum(int(r["starts"]) for r in self.rows),
            "internal": sum(int(r["internal"]) for r in self.rows),
            "wake_rows": len([r for r in self.rows if r["kind"] == "wake"]),
            "repeat_rows": len([r for r in self.rows if r["kind"] == "repeat"]),
            "void_rows": len([r for r in self.rows if r["kind"] == "void"]),
            "admissible_rows": len([r for r in self.rows if r.get("admissible_as_evidence")]),
        }

    def charged(self, label: str) -> bool:
        return any(r["label"] == label for r in self.rows)

    def charge(self, label: str, starts: int, internal: int, kind: str,
               note: str = "", admissible_as_evidence: bool = True) -> None:
        """Charge one attempted start, before the solver runs.

        The kinds are set by the plan entry, never inferred from a number:
          * "repeat"  - a reference-mesh repeat of one of the two designs; may be admitted;
          * "wake"    - a 16-wake-node probe; never admitted (the admission mesh is fixed at 8);
          * "void"    - a start that was already spent on a mis-configured case (wake count below
                        the admission mesh), recorded here so the bill matches the disk instead of
                        being dropped. A void row cannot be admitted and cannot be re-run: it is
                        the honest cost of a bug, not a spare attempt.
        "No room for this start" is a reason not to start it, which is why this is checked here
        and called before the solver is spawned.
        """
        if self.charged(label):
            raise RuntimeError("label %r is already in the verification ledger; a re-run of the "
                               "same case is a second start and needs its own label" % label)
        if kind not in ("repeat", "wake", "void"):
            raise RuntimeError("unknown verification row kind %r; the kind is set by the plan, "
                               "never inferred from a number" % kind)
        total = self.totals()
        starts_after = total["starts"] + int(starts)
        internal_after = total["internal"] + int(internal)
        if kind == "repeat" and total["repeat_rows"] >= (
                2 * int(self.caps["max_repeat_runs_per_design"])):
            raise RuntimeError("repeat cap reached: %d repeat rows already charged"
                               % total["repeat_rows"])
        if kind == "wake" and total["wake_rows"] >= int(self.caps["max_wake_probe_starts"]):
            raise RuntimeError("wake probe cap exceeded: %d rows" % total["wake_rows"])
        if kind == "void" and total["void_rows"] >= int(self.caps["max_void_rows"]):
            raise RuntimeError("void row cap exceeded: %d rows" % total["void_rows"])
        if starts_after > int(self.caps["max_verification_starts"]):
            raise RuntimeError("verification start cap exceeded: %d > %d"
                               % (starts_after, self.caps["max_verification_starts"]))
        if internal_after > int(self.caps["max_verification_internal_cases"]):
            raise RuntimeError("verification internal cap exceeded: %d > %d"
                               % (internal_after, self.caps["max_verification_internal_cases"]))
        # Only a reference-mesh repeat can ever be evidence. A probe is measured on a mesh the
        # admission rule does not accept, and a void row was spent on a mis-made case, so neither
        # may be counted as a measurement however the caller sets the flag.
        self.rows.append({"label": label, "kind": kind, "starts": int(starts),
                          "internal": int(internal), "utc": now(), "note": note,
                          "admissible_as_evidence": bool(admissible_as_evidence)
                          and kind == "repeat"})
        self.persist()

    def persist(self) -> None:
        total = self.totals()
        write_json(self.path, {
            "schema": "dreal005.o0_final_verification_ledger.v1",
            "created_utc": now(),
            "caps": self.caps,
            "rows": self.rows,
            "verification_starts_actual": total["starts"],
            "verification_internal_cases_actual": total["internal"],
            "wake_probe_starts_actual": total["wake_rows"],
            "repeat_runs_actual": total["repeat_rows"],
            "void_rows_actual": total["void_rows"],
            "admissible_rows_actual": total["admissible_rows"],
            "prior_ledger_sha256": self.prior_sha256,
            "note": ("separately itemized verification budget; never folded into the O0 "
                     "optimizer caps, and the wake probe cases are never admitted because the "
                     "admitted wake count is fixed at 8. A void row is a start that was already "
                     "spent on a mis-configured case: it is charged so the bill matches the disk, "
                     "it is never admitted, and it is never re-run."),
        })

    def summary(self) -> Dict[str, Any]:
        total = self.totals()
        return {"caps": self.caps, "rows": self.rows,
                "verification_starts_actual": total["starts"],
                "verification_internal_cases_actual": total["internal"],
                "wake_probe_starts_actual": total["wake_rows"],
                "repeat_runs_actual": total["repeat_rows"],
                "void_rows_actual": total["void_rows"],
                "admissible_rows_actual": total["admissible_rows"],
                "prior_ledger_sha256": self.prior_sha256}


def check_final_go(picks: Dict[str, Any]) -> Dict[str, Any]:
    """Refuse to spend a verification start unless a GO for exactly these bytes exists."""
    problems: List[str] = []
    state: Dict[str, Any] = {}
    dossier_sha = sha_file(DOSSIER)
    pre_sha = sha_file(PRE)
    if not FINAL_GO.is_file():
        raise SystemExit("NO_FINAL_GO: %s does not exist; the O0-FINAL verification budget has "
                         "never been reviewed and authorized" % FINAL_GO)
    go = json.loads(FINAL_GO.read_text(encoding="utf-8"))
    state = {"path": str(FINAL_GO), "sha256": sha_file(FINAL_GO),
             "go_issued": go.get("go_issued"), "kind": go.get("authorization_kind"),
             "a5_verdict": go.get("a5_verdict"),
             "a5_dossier_sha256": go.get("a5_dossier_sha256"),
             "authorized_designs": go.get("authorized_designs"),
             "budget": go.get("verification_budget")}
    if not go.get("go_issued"):
        problems.append("the O0-FINAL GO record is not marked go_issued")
    if go.get("authorization_kind") != "O0_FINAL_VERIFICATION":
        problems.append("the GO record authorizes %r, not O0_FINAL_VERIFICATION"
                        % (go.get("authorization_kind"),))
    if go.get("a5_verdict") != EXPECTED_VERDICT:
        problems.append("the GO carries A5 verdict %r, expected %r"
                        % (go.get("a5_verdict"), EXPECTED_VERDICT))
    if go.get("a5_dossier_sha256") != dossier_sha:
        problems.append("the GO binds dossier %r but disk has %s"
                        % (go.get("a5_dossier_sha256"), dossier_sha))
    if go.get("preregistration_sha256") != pre_sha:
        problems.append("the GO binds pre-registration %r but disk has %s"
                        % (go.get("preregistration_sha256"), pre_sha))
    if not VERDICT.is_file():
        problems.append("no A5 verdict file exists")
    elif go.get("a5_verdict_sha256") != sha_file(VERDICT):
        problems.append("the A5 verdict file changed after the GO")
    if not RECEIPT.is_file():
        problems.append("no dossier receipt exists")
    elif (json.loads(RECEIPT.read_text(encoding="utf-8")).get("dossier") or {}).get(
            "sha256") != dossier_sha:
        problems.append("the dossier receipt binds different dossier bytes")
    ver_path = RUN / "o0_binding_verification.json"
    if not ver_path.is_file():
        problems.append("no byte verifier round exists")
    else:
        ver = json.loads(ver_path.read_text(encoding="utf-8"))
        if ver.get("status") != "O0_BYTES_BOUND_MECHANICALLY" or int(
                ver.get("failure_count") or 0) != 0:
            problems.append("the byte verifier round is %r with %r failures"
                            % (ver.get("status"), ver.get("failure_count")))
        if (ver.get("dossier") or {}).get("sha256") != dossier_sha:
            problems.append("the byte verifier round read an earlier dossier")
        if str(ver.get("created_utc") or "") < datetime.fromtimestamp(
                DOSSIER.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"):
            problems.append("the byte verifier round predates the dossier bytes")
    budget = go.get("verification_budget") or {}
    for key, value in CAPS.items():
        if int(budget.get(key, -1)) != int(value):
            problems.append("GO verification budget %s is %r but this run would spend %r"
                            % (key, budget.get(key), value))
    authorized = go.get("authorized_designs") or {}
    for name in ("baseline", "best"):
        picked = (picks.get(name) or {}).get("design_id")
        # The GO binds the whole design record, not a bare hash, so the comparator reads the
        # design_id out of the record rather than trusting the GO to store only a string.
        entry = authorized.get(name)
        authorized_id = entry if isinstance(entry, str) else (entry or {}).get("design_id")
        if picked and authorized_id != picked:
            problems.append("GO authorizes %s design %r but this run would verify %r"
                            % (name, authorized_id, picked))
    if problems:
        raise SystemExit("FINAL_GO_INVALID: " + "; ".join(problems))
    state["problems"] = []
    return state


def pick_designs(result: Dict[str, Any]) -> Dict[str, Any]:
    """The baseline and the best admitted non-baseline design, taken from the batch records."""
    attempts = result.get("attempts") or []
    baseline = None
    best = None
    for row in attempts:
        if row.get("status") != "FEASIBLE_ADMITTED":
            continue
        if row.get("is_baseline"):
            baseline = row
        elif best is None or float(row["di_n"]) < float(best["di_n"]):
            best = row
    if not baseline:
        raise SystemExit("NO_BASELINE: the batch has no admitted baseline row to verify")
    if not best:
        raise SystemExit("NO_FEASIBLE_NONBASELINE: the batch has no admitted non-baseline row; "
                         "the pre-registered verdict for that case is NO_FEASIBLE_NONBASELINE "
                         "and no verification start may be spent")
    return {"baseline": baseline, "best": best}


def refine_only(x12: List[float], center: float, label: str,
                n_wake_nodes: int = 8) -> Dict[str, Any]:
    alphas = o0.refine_alphas(float(center))
    cl_target = ev.cl_target_for(x12)
    return ev.make_case(x12, label, "final", alphas, cl_target, float(center),
                        n_wake_nodes=n_wake_nodes)


def planned_internal_for(case: Dict[str, Any]) -> int:
    """How many internal cases one start of this case costs, as planned before the run.

    o0_eval.make_case() returns "alpha_points" as the COUNT of alpha points, not the list, while
    an earlier draft of this file read it as if it were the list. That mismatch threw a TypeError
    after the first attempt spent its start and before it charged it, so the run died with a bill
    on the disk and nothing in the ledger - the exact failure the pre-charge was added to prevent.
    A charge made before the run is only a guarantee if computing the charge cannot throw, so the
    cost is computed here, from either shape, and tested in o0_final_selftest.py without a solver.
    """
    points = case["alpha_points"]
    if isinstance(points, int):
        return points
    return len(list(points))


def attempt_refine(x12: List[float], center: float, label: str, *,
                   admit: bool, n_wake_nodes: int = 8,
                   ledger: Ledger = None, kind: str = "repeat",
                   note: str = "", case: Dict[str, Any] = None) -> Dict[str, Any]:
    """Charge the start, then spend it.

    The charge happens before the solver is spawned, using the planned cost (one start, one
    internal case per planned alpha point). A start that is charged and then dies still owes its
    bill, which is the point: the previous version charged after the run, so a crash on the third
    case left a real, paid solver run out of the ledger entirely and the bill on the disk and the
    bill in the ledger disagreed by exactly the amount nobody wants to discover later. After the
    run the reported cost must equal the charged cost; if it does not, the row is already paid and
    the mismatch is raised rather than papered over.
    """
    if case is None:
        case = refine_only(x12, center, label, n_wake_nodes=n_wake_nodes)
    planned_starts = 1
    planned_internal = planned_internal_for(case)
    if ledger is not None:
        ledger.charge(label, planned_starts, planned_internal, kind, note=note,
                      admissible_as_evidence=(kind == "repeat"))
    try:
        result = ev.run(case, label)
    except BaseException as exc:
        # The start was charged before it was spent, so the bill already survives this crash.
        # The record is written out here as well, because the exception unwinds past the caller.
        write_json(OUT / ("o0_final_crash_%s.json" % label), {
            "label": label, "kind": kind, "case_id": case.get("case_id"),
            "case_dir": case.get("case_dir"), "error": repr(exc),
            "charged_starts": planned_starts, "charged_internal": planned_internal,
            "charged_before_the_run": True, "utc": now(),
            "note": ("the solver start is already in the verification ledger; this record exists "
                     "so that a crash cannot look like a start that was never spent"),
        })
        raise
    record: Dict[str, Any] = {
        "label": label, "kind": kind, "case_id": case["case_id"],
        "case_dir": case["case_dir"],
        "design_id": case.get("design_id") or o0.design_identity(x12)["design_id"],
        "x12": list(x12), "alpha_center_deg": float(center),
        "alpha_grid_deg": o0.refine_alphas(float(center)),
        "n_wake_nodes": int(n_wake_nodes),
        "task_physics_sha256": case.get("task_physics_sha256"),
        "plan_sha256": case.get("plan_sha256"),
        "vspgeom_sha256": case.get("vspgeom_sha256"),
        "status": result.get("status"),
        "exit_code": result.get("exit_code"),
        "wall_s": result.get("wall_s"),
        "polar_rows": result.get("polar_rows"),
        "physical_solver_starts": int(result.get("physical_solver_starts") or 0),
        "internal_solver_cases": int(result.get("internal_solver_cases") or 0),
        "sref_m2": case["sref_m2"], "q_pa": case["q_pa"],
        "admitted": False, "di_n": None, "cl": None, "cdi": None, "alpha_deg": None,
        "lift_rel_error": None, "admission_status": None, "evidence_scope": None,
        "raw_sha256": None,
    }
    record["charged_starts"] = planned_starts if ledger is not None else 0
    record["charged_internal"] = planned_internal if ledger is not None else 0
    reported = (record["physical_solver_starts"], record["internal_solver_cases"])
    if ledger is not None and reported[1] > planned_internal:
        write_json(OUT / ("o0_final_cost_underreported_%s.json" % label), record)
        raise RuntimeError(
            "the solver reported %d internal cases but only %d were charged for %r; the ledger "
            "under-bills this label, so it must be topped up rather than left short"
            % (reported[1], planned_internal, label))
    if result.get("status") == "SOLVED":
        record["rows"] = ev.bracket_rows(result)
        if admit:
            audit_id = "O0F-AUDIT-%s" % case["case_id"]
            audit = ev.audit_case(case["case_id"], audit_id)
            record["audit_id"] = audit_id
            record["audit_returncode"] = audit.get("returncode")
            record["audit_sha256"] = audit.get("audit_sha256")
            if audit.get("returncode") == 0:
                admission_id = "O0F-ADM-%s" % case["case_id"]
                admission = ev.admit_case(case["case_id"], admission_id, audit_id,
                                          "final-" + label)
                record["admission_id"] = admission_id
                record["admission_returncode"] = admission.get("returncode")
                record["admission_sha256"] = admission.get("certificate_sha256")
                if admission.get("returncode") == 0:
                    cert = admission["certificate"]
                    record.update({
                        "admitted": True, "di_n": float(cert["di_n"]),
                        "cl": float(cert["cl"]), "cdi": float(cert["cdi"]),
                        "alpha_deg": float(cert["alpha_deg"]),
                        "sref_m2": float(cert["sref_m2"]),
                        "q_pa": float(cert["q_pa"]),
                        "raw_sha256": cert.get("raw_sha256"),
                        "admission_status": cert.get("status"),
                        "evidence_scope": cert.get("evidence_scope"),
                        "lift_rel_error": abs(float(cert["q_pa"]) * float(cert["sref_m2"])
                                              * float(cert["cl"]) - ev.LIFT) / ev.LIFT,
                    })
    return record


def decide(rounds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply the pre-registered verdict rule to the measured repeats."""
    verdicts = ["VERIFIED_IMPROVEMENT", "FEASIBLE_NO_VERIFIED_IMPROVEMENT",
                "PROVISIONAL_CANDIDATE", "NO_FEASIBLE_NONBASELINE"]
    by_design: Dict[str, List[Dict[str, Any]]] = {"baseline": [], "best": []}
    for row in rounds:
        by_design[row["design"]].append(row)
    admitted = {k: [r for r in v if r.get("admitted")] for k, v in by_design.items()}
    detail: Dict[str, Any] = {
        "rule": ("both repeats of both designs must be admitted; the mean improvement must be "
                 "positive and larger than three times the largest within-design repeat spread"),
        "counts": {k: {"runs": len(v), "admitted": len(admitted[k])}
                   for k, v in by_design.items()},
        "allowed_verdicts": verdicts,
    }
    if len(admitted["baseline"]) == 0 or len(admitted["best"]) == 0:
        detail.update({"verdict": "PROVISIONAL_CANDIDATE",
                       "why": "at least one design produced no admitted raw row in any repeat"})
        return detail
    base = [float(r["di_n"]) for r in admitted["baseline"]]
    cand = [float(r["di_n"]) for r in admitted["best"]]
    base_spread = max(base) - min(base) if len(base) > 1 else 0.0
    cand_spread = max(cand) - min(cand) if len(cand) > 1 else 0.0
    spread = max(base_spread, cand_spread)
    mean_base = statistics.fmean(base)
    mean_cand = statistics.fmean(cand)
    improvement = mean_base - mean_cand
    worst_pair = min(b - c for b in base for c in cand)
    complete = (len(admitted["baseline"]) == len(by_design["baseline"])
                and len(admitted["best"]) == len(by_design["best"]))
    detail.update({
        "baseline_di_n": base, "best_di_n": cand,
        "baseline_mean_di_n": mean_base, "best_mean_di_n": mean_cand,
        "improvement_n": improvement,
        "improvement_fraction_of_baseline": improvement / mean_base if mean_base else None,
        "repeat_spread_n": spread, "baseline_spread_n": base_spread,
        "best_spread_n": cand_spread,
        "worst_paired_improvement_n": worst_pair,
        "three_times_spread_n": 3.0 * spread,
        "all_repeats_admitted": complete,
    })
    if not complete:
        detail.update({"verdict": "PROVISIONAL_CANDIDATE",
                       "why": "a repeat failed admission, so the design cannot be claimed "
                              "reproducible"})
    elif improvement > 0 and worst_pair > 0 and improvement > 3.0 * spread:
        detail.update({"verdict": "VERIFIED_IMPROVEMENT",
                       "why": "every repeat admitted, every pairing favours the candidate, and "
                              "the mean improvement exceeds three times the repeat spread"})
    else:
        detail.update({"verdict": "FEASIBLE_NO_VERIFIED_IMPROVEMENT",
                       "why": "the candidate re-ran feasibly but the improvement is not larger "
                              "than the measured repeat scatter"})
    return detail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True,
                        help="the optimizer batch result JSON, e.g. o0_result_B02.json")
    parser.add_argument("--label", default="O0F",
                        help="batch label for the verification case directories")
    parser.add_argument("--only", default="all", choices=["all", "baseline", "best"],
                        help="run one design's repeats and wake probe instead of both")
    parser.add_argument("--preflight-only", action="store_true",
                        help="check every gate and build the cases, but spend no start")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ev.set_label(args.label)
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    budget = dict(pre.get("o0_final", {}).get("separate_budget") or {})
    # Every cap comes from the pre-registration. A number typed in this file would be a budget
    # the A5 review never saw, so any key this file holds must also exist there and match it.
    rename = {"verification_starts_max": "max_verification_starts",
              "verification_internal_cases_max": "max_verification_internal_cases",
              "wake_probe_starts_max": "max_wake_probe_starts",
              "void_rows_max": "max_void_rows"}
    caps = dict(CAPS)
    missing = []
    for key in CAPS:
        source = key
        for pre_key, here in rename.items():
            if here == key:
                source = pre_key
        if source in budget:
            caps[key] = int(budget[source])
        else:
            missing.append(source)
    if missing:
        raise SystemExit("BUDGET_NOT_PRE_REGISTERED: the pre-registration's "
                         "o0_final.separate_budget does not state %r, so this run would spend a "
                         "budget that was never reviewed" % (missing,))
    if caps != CAPS:
        raise SystemExit("BUDGET_MISMATCH: the pre-registration says %r but this file would "
                         "spend %r; a verification budget typed here rather than read there is "
                         "not pre-registered" % (caps, CAPS))
    picks = pick_designs(result)
    go_state = check_final_go(picks)
    closed = sorted(RUN.glob("o0_batch_close_*.json"))
    if not closed:
        raise SystemExit("OPTIMIZER_BATCH_NOT_CLOSED: the pre-registration says a verification "
                         "start may only be spent after the optimizer batch is closed by a batch "
                         "record, and no o0_batch_close_*.json exists")
    ledger = Ledger(LEDGER, CAPS)
    names = ["baseline", "best"] if args.only == "all" else [args.only]
    cases = []

    def free_label(base: str) -> str:
        """The first label of this shape that the ledger has not already charged.

        A label that is already in the ledger is a start that was already paid for, so reusing it
        would either refuse to run (the ledger refuses a second charge for one label) or, worse,
        look like a re-run of a case that was never actually measured. The first repeat of the
        baseline in the repaired batch therefore lands on final-baseline-r1b, because
        final-baseline-r1 is the label of a start that was spent on the wrong wake count.
        """
        if not ledger.charged(base):
            return base
        for suffix in "bcdefgh":
            candidate = base + suffix
            if not ledger.charged(candidate):
                return candidate
        raise SystemExit("NO_FREE_LABEL: every suffix of %r is already charged" % base)

    probes_already_spent = []
    for name in names:
        row = picks[name]
        for repeat in (1, 2):
            cases.append((name, row, free_label("final-%s-r%d" % (name, repeat)), repeat,
                          CAPS["n_wake_nodes_reference"], "repeat"))
        probe_base = "final-%s-wake%d" % (name, CAPS["n_wake_nodes_probe"])
        spent_probes = [r for r in ledger.rows
                        if r.get("kind") == "wake" and str(r.get("label", "")).startswith(probe_base)]
        if spent_probes:
            # The probe is a pre-registered item that has already been spent and completed. Its
            # output is on the disk and charged in the ledger, so spending a second start to
            # reproduce it would be paying twice for the same item, not measuring anything new.
            probes_already_spent.append({"design": name, "label": spent_probes[0]["label"],
                                         "ledger_row": spent_probes[0].get("note")})
            continue
        cases.append((name, row, free_label(probe_base), None,
                      CAPS["n_wake_nodes_probe"], "wake"))
    plan = {
        "schema": "dreal005.o0_final_plan.v1",
        "created_utc": now(),
        "run_id": pre.get("run_id"),
        "authorization_kind": "O0_FINAL_VERIFICATION",
        "batch_label": args.label,
        "case_root": str(ev.case_root()),
        "result_source": str(Path(args.result)),
        "result_sha256": sha_file(Path(args.result)),
        "final_go": go_state,
        "preregistration_sha256": sha_file(PRE),
        "dossier_sha256": sha_file(DOSSIER),
        "budget": CAPS,
        "designs": {name: {"design_id": picks[name].get("design_id"),
                           "design_index": picks[name].get("design_index"),
                           "is_baseline": bool(picks[name].get("is_baseline")),
                           "x12": picks[name].get("x12"),
                           "alpha_center_deg": picks[name].get("alpha_deg"),
                           "batch_di_n": picks[name].get("di_n")}
                    for name in names},
        "planned_cases": [{"design": name, "label": label, "repeat": repeat,
                           "n_wake_nodes": wake, "kind": kind,
                           "admit": kind == "repeat",
                           "planned_starts": 1, "planned_internal": CAPS["refinement_points"]}
                          for (name, _row, label, repeat, wake, kind) in cases],
        "already_charged_labels": [r["label"] for r in ledger.rows],
        "void_rows_precharged": [r for r in ledger.rows if r.get("kind") == "void"],
        "probes_already_spent_not_re_run": probes_already_spent,
        "prior_verification_ledger": ledger.summary(),
        "physical_solver_starts_actual": ledger.totals()["starts"],
        "internal_solver_cases_actual": ledger.totals()["internal"],
        "note": ("this plan is written before the first start so the intended spend is on "
                 "record even if the run dies"),
    }
    write_json(PLAN, plan)
    print(json.dumps({"planned_cases": len(cases), "already_charged": len(ledger.rows),
                      "go": go_state.get("kind"), "case_root": plan["case_root"]},
                     ensure_ascii=False, indent=2))
    if args.preflight_only:
        for (name, row, label, repeat, wake, kind) in cases:
            if ledger.charged(label):
                print("  %s already charged, skipping case construction" % label)
                continue
            case = refine_only(list(row["x12"]), float(row["alpha_deg"]), label,
                               n_wake_nodes=wake)
            print("  built %s -> %s (kind %s, wake %d, %d alpha points)"
                  % (label, case["case_id"], kind, wake, case["alpha_points"]))
        print("PREFLIGHT_ONLY: gates passed and cases built; zero solver starts spent")
        return 0
    rounds: List[Dict[str, Any]] = []
    wake_rows: List[Dict[str, Any]] = [
        {"label": item["label"], "design": item["design"], "kind": "wake",
         "carried_forward_from_the_ledger": True,
         "why_not_run_again": ("this probe is a pre-registered item that has already been spent "
                               "and completed; its paid output is on the disk and the ledger "
                               "charges it, so a second start would re-buy the same measurement"),
         "note": item["ledger_row"]}
        for item in probes_already_spent]

    def flush() -> None:
        write_json(ROUNDS, {"schema": "dreal005.o0_final_rounds.v1", "created_utc": now(),
                            "plan_sha256": sha_file(PLAN),
                            "rounds": rounds, "wake_probe": wake_rows,
                            "ledger": ledger.summary(),
                            "decision": decide(rounds) if rounds else None})

    for (name, row, label, repeat, wake, kind) in cases:
        if ledger.charged(label):
            print("  %s already charged; not spending a second start for the same label" % label)
            continue
        record = attempt_refine(list(row["x12"]), float(row["alpha_deg"]), label,
                                admit=(kind == "repeat"),
                                n_wake_nodes=wake, ledger=ledger, kind=kind)
        record["design"] = name
        if kind == "repeat":
            rounds.append(record)
        else:
            wake_rows.append(record)
        flush()
        print("  %s %s di_n %s admitted %s starts %d internal %d"
              % (label, record["status"], record["di_n"], record["admitted"],
                 record["physical_solver_starts"], record["internal_solver_cases"]))
    decision = decide(rounds)
    flush()
    write_json(RESULT_VERDICT, {
        "schema": "dreal005.o0_final_verdict.v1", "created_utc": now(),
        "decision": decision, "ledger": ledger.summary(),
        "plan_sha256": sha_file(PLAN), "rounds_sha256": sha_file(ROUNDS),
        "physics_validated": False,
        "physical_interpretation": ("lifting-surface VSPAERO internal only; forced-lift induced "
                                    "drag at fixed Mach and altitude"),
    })
    print(json.dumps({"decision": decision, "ledger": ledger.summary()},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())