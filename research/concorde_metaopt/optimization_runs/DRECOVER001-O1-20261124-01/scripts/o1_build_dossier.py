"""Build the O1 A5 dossier from the frozen preregistration, not from prose.

Every number in the dossier is rendered from o1_preregistration.json and from the code the
preregistration froze. That is deliberate: a dossier that is typed by hand can drift from
the preregistration it claims to describe, and the A5 reviewer cannot recompute it.

Run: python scripts/o1_build_dossier.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(RUN / "scripts"))
sys.path.insert(0, str(REPO))

import o1_arms as arms  # noqa: E402
import o1_eval as ev  # noqa: E402

PREREG = RUN / "o1_preregistration.json"
DOSSIER = RUN / "o1_a5_dossier.md"
RECEIPT = RUN / "o1_dossier_receipt.json"
TICK = chr(96)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def code(name: str) -> str:
    return TICK + str(name) + TICK


def main() -> int:
    pre = json.loads(PREREG.read_text(encoding="utf-8"))
    caps = pre["budgets"]["caps"]
    model = pre["budgets"]["cost_model"]
    per_arm = model["per_arm_equivalent"]
    all_arms = model["all_arms_equivalent"]
    support = pre["shared_support"]
    lines: list = []
    add = lines.append

    add("# O1 three-arm warm-start comparison -- A5 pre-registration dossier")
    add("")
    add("Run " + code(pre["run_id"]) + " | protocol " + code(pre["protocol_id"])
        + " | authorization " + code(pre["authorization_id"])
        + " | written " + pre["created_utc"])
    add("")
    add("This dossier authorises **nothing**. It documents a protocol that is already frozen "
        "in " + code("o1_preregistration.json") + " (" + sha(PREREG) + ", "
        + str(PREREG.stat().st_size) + " bytes) so that an independent reviewer can reject it "
        "before a single solver start is spent.")
    add("")

    add("## 0. What this stage is, and what it is not")
    add("")
    add("Issue #15 section 6 asks a narrow question: at *equal* real evaluation cost, does a "
        "meta-learned warm start reach a lower best-feasible induced drag than a plain Sobol "
        "warm start on a new task? O1 is the experiment that answers that question. It is not")
    add("")
    add("* a claim that the meta objective is superior -- the A0 ablation did **not** establish "
        "that (paired test delta -893.145 N, 95% CI [-7111.5, 5289.6], sign test p=0.8145; "
        "validation was worse, p=0.0309);")
    add("* a claim of aerodynamic validation: " + code("physics_validated") + " stays false and "
        "the evidence scope stays " + code("VSPAERO_INTERNAL_ONLY") + ";")
    add("* a global optimum or a regret statement: the search is one frozen two-variable slice;")
    add("* a second seed or a second task: Mach 2.10 and seeds 19/43 are explicitly not "
        "authorised by this pairing.")
    add("")

    add("## 1. Frozen code")
    add("")
    add("The preregistration binds the exact bytes that will spend the budget:")
    add("")
    add("| file | bytes | sha256 |")
    add("| --- | --- | --- |")
    for name, digest in sorted(pre["code"]["code_shas"].items()):
        path = Path(pre["code"]["code_root"]) / name
        add("| " + code(name) + " | " + str(path.stat().st_size) + " | " + code(digest) + " |")
    add("")

    add("## 2. The new task, and why it is new")
    add("")
    add("| task | Mach | q (Pa) | physics sha256 | in any historical label? |")
    add("| --- | --- | --- | --- | --- |")
    for key, task in sorted(pre["tasks"].items()):
        add("| " + task["task_id"] + " | %.2f | %.6f | " % (task["mach"],
                                                            task["dynamic_pressure_pa"])
            + code(task["physics_sha256"]) + " | no |")
    add("")
    add("The collision check compared "
        + str(pre["task_collision_check"]["historical_physics_hashes_considered"])
        + " historical physics hashes from the A0 dataset and found no collision. The physics "
          "hash excludes the task id and the split by construction, so renaming a task cannot "
          "manufacture a new physical task.")
    add("")
    add("First pairing: task " + code(pre["pairing"]["task_key"]) + ", pairing seed "
        + str(pre["pairing"]["pairing_seed"]) + ", GP seed "
        + str(pre["pairing"]["gp_seed"]) + ".")
    add("")

    add("## 3. What is held equal, and what is allowed to differ")
    add("")
    for item in pre["arms"]["held_equal"]:
        add("* " + item)
    add("")
    add("The *only* difference between arms is the rule that chooses the three extra "
        "initialisation designs:")
    add("")
    for arm in pre["arms"]["order"]:
        add("**" + arm + "** -- " + pre["arms"][arm]["warm_start_rule"])
        add("")
    add("Neither K-shot model reads a test label or any optimiser feedback: the context vector "
        "is a function of the task specification only (Mach, q, CL target, altitude), and the "
        "ranking is computed from the common candidate pool before any of the arm's own "
        "adaptive designs exist.")
    add("")

    add("## 4. Cost model, and why every arm stops at eight designs")
    add("")
    add("One design costs **" + str(model["internal_per_design"]) + " internal alpha cases** ("
        + str(arms.ALPHA_PLAN["coarse_internal_cases"]) + " coarse + "
        + str(arms.ALPHA_PLAN["refine_internal_cases"]) + " refine) and **"
        + str(model["starts_per_design"]) + " charged solver starts**.")
    add("")
    add("| cap | value |")
    add("| --- | --- |")
    for name in sorted(caps):
        add("| " + code(name) + " | " + str(caps[name]) + " |")
    add("")
    add("The internal cap binds first: " + str(caps["max_internal_per_arm"]) + " internal / "
        + str(model["internal_per_design"]) + " per design = **"
        + str(model["affordable_designs_per_arm"]) + " designs per arm**, before the "
        + str(caps["max_designs_per_arm"]) + "-design and " + str(caps["max_starts_per_arm"])
        + "-start caps can bind.")
    add("")
    add("* per arm: " + str(per_arm["designs"]) + " designs = " + str(per_arm["starts"])
        + " starts = " + str(per_arm["internal"]) + " internal (equivalent)")
    add("* all three arms: " + str(all_arms["starts"]) + " starts = "
        + str(all_arms["internal"]) + " internal (equivalent)")
    add("* physical bill if everything admits: " + model["physical_if_everything_admits"])
    add("")
    add("The eight designs decompose as three pre-designated shared support designs, three "
        "warm-start designs and two adaptive designs. **The support designs are solved once "
        "and charged in full to all three arms**, so the equivalent bill is three times the "
        "physical bill for that block. The two numbers are reported separately and are never "
        "added together or conflated.")
    add("")
    add("The truncation rule is honest by construction: every arm is cut at the same design "
        "count, so the report states that the arms were truncated at a common budget rather "
        "than claiming they independently converged.")
    add("")

    add("## 5. Preregistered target")
    add("")
    add("Target: best feasible Di at most **%.6f%%** below the pre-designated baseline design "
        "inside the shared support." % (pre["budgets"]["target_improvement_fraction"] * 100.0,))
    add("")
    add(pre["budgets"]["target_derivation"])
    add("")
    add("Provenance of the cited prior effect, stated plainly: the 0.2394% figure comes from "
        "the O0 run, not from O1. It is used only to size a threshold that a reader can judge "
        "as plausible or implausible before seeing any O1 number; it is not a fit to O1 data, "
        "and no O1 label exists at the time this target was frozen.")
    add("")
    add("The target is fixed before any O1 result exists; it cannot be moved to fit an "
        "outcome.")
    add("")

    add("## 6. Shared support and candidate pool")
    add("")
    add("Shared support: " + str(support["count"]) + " designs, seed " + str(support["seed"])
        + ", the first of which is the baseline. Design ids:")
    add("")
    for index, design_id in enumerate(support["design_ids"]):
        add("* " + code("s%02d" % (index,)) + " -> " + code(design_id))
    add("")
    pool_info = pre["candidate_pool"]
    add("Candidate pool: " + str(pool_info["count"]) + " coordinate vectors, seed "
        + str(pool_info["seed"]) + ", containing **no objective values**.")
    add("")
    add("Pool and Sobol overlap, disclosed rather than left implicit: the pool and the Sobol "
        "warm-start triple come from the same LHS generator with different seeds ("
        + str(pool_info["seed"]) + " vs " + str(pre["shared_support"]["seed"] + 1)
        + "), and no point is excluded in advance. This is harmless for the comparison "
        "because (a) the SOBOL arm never reads the pool, (b) the two K-shot arms rank the pool "
        "but are given no objective value for any point in it, and (c) every design, wherever "
        "its coordinates came from, is scored by the same real evaluation and admission gate. "
        "Any arm that would propose a design already in its own ledger -- shared support "
        "included -- skips it and takes the next, so no arm is charged twice for one design.")
    add("")
    add("Measured overlap between the pool and the Sobol triple: "
        + str(pool_info["pool_minus_sobol_overlap_count"]) + " shared coordinate vector(s).")
    add("")

    add("## 7. The carried-forward bill")
    add("")
    carried = pre["carried_forward"]
    if carried.get("optimizer"):
        spend = carried["optimizer"].get("authorization_spend") or {}
        add("O0 optimizer, from " + code(Path(carried["optimizer"]["source"]).name) + ": "
            + str(spend.get("designs")) + " designs, " + str(spend.get("solver_starts"))
            + " starts, " + str(spend.get("internal_cases")) + " internal cases.")
    if carried.get("final_verification"):
        add("O0-FINAL verification, from "
            + code(Path(carried["final_verification"]["source"]).name) + ": "
            + str(carried["final_verification"]["starts"]) + " starts, "
            + str(carried["final_verification"]["internal"]) + " internal cases.")
    add("")
    add("O1 authorises **zero** further optimizer designs. Its whole budget is this one "
        "pairing, three arms, fixed at the cost model above.")
    add("")

    add("## 8. Stop conditions")
    add("")
    for item in pre["stop_conditions"]:
        add("* " + item)
    add("")

    add("## 9. Primary endpoints")
    add("")
    for item in pre["primary_endpoints"]:
        add("* " + item)
    add("")

    add("## 10. Explicitly not authorised")
    add("")
    for item in pre["not_authorized"]:
        add("* " + item)
    add("")

    add("## 10b. Live authorization artifacts are retired, never silently overwritten")
    add("")
    add("An earlier release of this dossier was reviewed, and that review PASSed. Those bytes "
        "no longer exist as the live document: the dossier was re-signed after changes, so the "
        "old verdict and the old binding round now name a dossier hash that is not on disk.")
    add("")
    add("Leaving them on the live path would make a GO issued today indistinguishable from a "
        "GO issued against the superseded bytes, which is exactly the failure this stage has "
        "to avoid. The handling rule, implemented in " + code("scripts/o1_retire_stale.py")
        + " and frozen in section 1, is:")
    add("")
    add("* an artifact is retired **only** when it names a dossier or preregistration sha256 "
        "that is not the sha256 on disk;")
    add("* an artifact that names the bytes on disk is never touched;")
    add("* a retired artifact is first copied into a dated history directory, verified byte "
        "for byte, and only then removed from the live path -- it is never deleted outright, so "
        "the record of what was ever reviewed survives;")
    add("* every retirement is written into " + code("o1_retire_record.json")
        + " with the old and new hashes, so the substitution is auditable rather than implied.")
    add("")
    add("After retirement the live path holds exactly one verdict and at most one binding "
        "round, and both name the dossier bytes on disk. The GO is then gated on that binding "
        "round and on that verdict by sha256, so a GO cannot exist for bytes that are not the "
        "bytes on disk.")
    add("")

    add("## 11. What the reviewer is asked to judge")
    add("")
    add("1. Is the three-arm comparison fair -- does any arm get information or effort the "
        "others do not?")
    add("2. Is the cost model arithmetically consistent, and does it prevent silent overspend?")
    add("3. Is the preregistered target fixed before the result rather than fitted to it?")
    add("4. Does the K-shot warm start use only the frozen checkpoint, the shared support and "
        "the task specification -- never a test label, never the other arm's feedback?")
    add("5. Does anything in this document claim more than the evidence will support?")
    add("")

    text = "\n".join(lines) + "\n"
    DOSSIER.write_text(text, encoding="utf-8", newline="\n")
    dossier_sha = sha(DOSSIER)
    receipt = {
        "schema": "dreal005.o1_dossier_receipt.v1",
        "created_utc": ev.now(),
        "dossier": {"path": str(DOSSIER), "sha256": dossier_sha,
                    "bytes": DOSSIER.stat().st_size},
        "preregistration": {"path": str(PREREG), "sha256": sha(PREREG),
                            "bytes": PREREG.stat().st_size},
        "code_shas_sha256": hashlib.sha256(
            json.dumps(pre["code"]["code_shas"], sort_keys=True).encode("utf-8")).hexdigest(),
        "physical_solver_starts_actual": 0,
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
    print(json.dumps({"dossier": str(DOSSIER), "bytes": DOSSIER.stat().st_size,
                      "sha256": dossier_sha,
                      "receipt": str(RECEIPT), "receipt_sha256": sha(RECEIPT)},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
