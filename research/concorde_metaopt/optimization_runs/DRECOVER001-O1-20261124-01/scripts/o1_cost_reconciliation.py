"""Reconcile the O1 cost line against the per-arm charges.

o1_result.json reports cost.equivalent_solver_starts as three times the WHOLE physical bill
(3 x 36 = 108). The preregistered cost model only charges the three shared support designs three
times, once per arm, because those three designs are solved once and consumed by all three arms;
each arm's own designs are charged once. The preregistered bill is therefore
  equivalent = 3 x support_starts + sum(arm own starts) = 3 x 6 + 30 = 48
and the physical bill is 36, which is exactly what the preregistration predicted
("48 equivalent minus 2 x 6 shared support starts = 36", i.e. the support block is paid three
times in the equivalent bill and once in the physical bill).

o1_result.json is already bound by o1_batch_close.json (result_sha256) and by the A4 audit and
the upload receipt, so it is NOT rewritten here. The correction is recorded in this file, which
names the sha256 of every source it read.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
ARMS = ["SOBOL_BO", "COND_SUPERVISED_KSHOT_BO", "COND_FOMAML_KSHOT_BO"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


res = json.loads((RUN / "o1_result.json").read_text(encoding="utf-8"))
sup = json.loads((RUN / "o1_shared_support.json").read_text(encoding="utf-8"))
close = json.loads((RUN / "o1_batch_close.json").read_text(encoding="utf-8"))
pre = json.loads((RUN / "o1_preregistration.json").read_text(encoding="utf-8"))
caps = pre["budgets"]["caps"]
model = pre["budgets"]["cost_model"]

support_starts = int(sup["starts"])
support_internal = int(sup["internal"])
arm_phys = {a: int(res["arms"][a]["physical_solver_starts_actual"]) for a in ARMS}
arm_equiv = {a: int(res["arms"][a]["equivalent_starts_actual"]) for a in ARMS}
arm_internal = {a: int(res["arms"][a]["internal_solver_cases_actual"]) for a in ARMS}
arm_designs = {a: int(res["arms"][a]["designs"]) for a in ARMS}

physical = support_starts + sum(arm_phys.values())
equivalent_contract = len(ARMS) * support_starts + sum(arm_phys.values())
equivalent_reported = int(res["cost"]["equivalent_solver_starts"])
internal_charged = sum(arm_internal.values())
internal_physical = support_internal + sum(arm_internal[a] - support_internal for a in ARMS)

checks = [
    {"check": "per-arm equivalent starts within cap", "value": arm_equiv,
     "cap": caps["max_starts_per_arm"],
     "pass": all(v <= caps["max_starts_per_arm"] for v in arm_equiv.values())},
    {"check": "per-arm internal cases within cap", "value": arm_internal,
     "cap": caps["max_internal_per_arm"],
     "pass": all(v <= caps["max_internal_per_arm"] for v in arm_internal.values())},
    {"check": "per-arm designs within cap", "value": arm_designs,
     "cap": caps["max_designs_per_arm"],
     "pass": all(v <= caps["max_designs_per_arm"] for v in arm_designs.values())},
    {"check": "three-arm charged equivalent starts within cap",
     "value": sum(arm_equiv.values()), "cap": caps["max_starts_all_arms"],
     "pass": sum(arm_equiv.values()) <= caps["max_starts_all_arms"]},
    {"check": "three-arm charged internal cases within cap",
     "value": internal_charged, "cap": caps["max_internal_all_arms"],
     "pass": internal_charged <= caps["max_internal_all_arms"]},
    {"check": "three-arm designs within cap", "value": sum(arm_designs.values()),
     "cap": caps["max_designs_all_arms"],
     "pass": sum(arm_designs.values()) <= caps["max_designs_all_arms"]},
    {"check": "physical bill equals the preregistered prediction",
     "value": physical, "cap": 36, "pass": physical == 36},
    {"check": "contract-reading equivalent bill equals the preregistered model",
     "value": equivalent_contract, "cap": model["all_arms_equivalent"]["starts"],
     "pass": equivalent_contract == model["all_arms_equivalent"]["starts"]},
    {"check": "charged internal equals the preregistered model",
     "value": internal_charged, "cap": model["all_arms_equivalent"]["internal"],
     "pass": internal_charged == model["all_arms_equivalent"]["internal"]},
]

payload = {
    "schema": "dreal005.o1_cost_reconciliation.v1",
    "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "run_id": pre["run_id"], "batch_id": pre["batch_id"],
    "batch_close_outcome": close.get("outcome"),
    "why_this_file_exists": (
        "the cost block of o1_result.json triples the whole physical bill, which charges each "
        "arm's own designs three times; the preregistered model triples only the shared support "
        "block. o1_result.json is bound by the batch record and the upload receipt, so it is left "
        "byte-identical and the recomputation is recorded here."),
    "reported_numbers": {
        "physical_solver_starts_actual": physical,
        "equivalent_solver_starts_in_o1_result_cost_block": equivalent_reported,
        "per_arm_equivalent_starts": arm_equiv,
        "per_arm_internal_cases": arm_internal,
        "per_arm_designs": arm_designs,
    },
    "recomputed_numbers": {
        "support_starts": support_starts, "support_internal": support_internal,
        "arm_own_physical_starts": arm_phys,
        "physical_total": physical,
        "equivalent_total_contract_reading": equivalent_contract,
        "equivalent_total_reported_reading": equivalent_reported,
        "difference": equivalent_reported - equivalent_contract,
        "direction_of_the_difference": (
            "the reported figure is larger, i.e. it overstates cost; it never flatters an arm"),
        "internal_physical_total": internal_physical,
        "internal_equivalent_total_charged_to_the_three_arms": internal_charged,
    },
    "cap_checks": checks,
    "all_cap_checks_pass": all(c["pass"] for c in checks),
    "which_numbers_the_caps_are_judged_against": (
        "the per-arm charged figures (16 equivalent starts, 160 internal cases, 8 designs) and "
        "their three-arm sums (48 / 480 / 24), because those are the quantities the cap keys "
        "name; on the contract reading the bill matches the preregistration exactly"),
    "disclosure": (
        "the discrepancy is disclosed, not repaired in place: the batch is closed and uploaded, "
        "and rewriting o1_result.json would change a hash that o1_batch_close.json, the A4 "
        "recompute and the upload receipt already cite"),
    "does_the_discrepancy_flatter_any_arm": "no; it inflates the total, and every per-arm number "
                                            "used for the comparison is unaffected",
    "primary_endpoint_unaffected": True,
    "source_sha256": {name: sha(RUN / name) for name in
                      ("o1_result.json", "o1_shared_support.json", "o1_batch_close.json",
                       "o1_preregistration.json")},
}
out = RUN / "o1_cost_reconciliation.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
               encoding="utf-8", newline="\n")
print(json.dumps({"written": str(out), "bytes": out.stat().st_size, "sha256": sha(out),
                  "physical": physical, "equivalent_contract": equivalent_contract,
                  "equivalent_reported": equivalent_reported,
                  "all_cap_checks_pass": payload["all_cap_checks_pass"]},
                 ensure_ascii=False, indent=2))
