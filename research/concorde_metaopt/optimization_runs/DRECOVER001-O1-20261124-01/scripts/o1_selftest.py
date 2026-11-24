"""Zero-physical self-test for the O1 arm machinery.

Nothing here starts VSPAERO. It checks the pure-python/ numpy pieces that would be
expensive to discover are broken *after* paying for real solver starts:

  * the three shared support designs (baseline first, all inside the frozen subspace)
  * the 256-candidate common pool (coordinates only, no objective)
  * both frozen A0 checkpoints load and forward as 16 -> 32 -> 32 -> 1
  * K-shot ranking over the pool runs and returns a full permutation
  * the per-arm ledger refuses to exceed the affordable design count
  * the cost model adds up to the preregistered numbers

Run: python scripts/o1_selftest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
sys.path.insert(0, str(RUN / "scripts"))

import o1_arms as arms  # noqa: E402
import o1_eval as ev  # noqa: E402
from research.concorde_metaopt.dreal001.meta.meta_dataset import Observation  # noqa: E402
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

FAILURES = []


def check(name, condition, detail=""):
    ok = bool(condition)
    status = "PASS" if ok else "FAIL"
    if not ok:
        FAILURES.append("%s: %s" % (name, detail))
    suffix = "" if ok else ("  -- " + str(detail))
    print("[%s] %s%s" % (status, name, suffix))


def main():
    support = arms.support_designs()
    check("three shared support designs", len(support) == 3, len(support))
    check("first support design is the baseline",
          o0.design_identity(list(support[0]))["is_baseline"])
    baseline = np.array(o0.BASELINE_X12)
    for index, design in enumerate(support):
        delta = np.abs(np.array(design) - baseline)
        moved = np.nonzero(delta > 1e-12)[0]
        check("support[%d] only moves sweep_1/sweep_2" % (index,),
              set(int(i) for i in moved) <= {2, 3}, moved)
        point = o0.design_to_subspace(list(design))
        inside = all(lo - 1e-12 <= v <= hi + 1e-12
                     for v, lo, hi in zip(point, arms.SUBSPACE_LOWER, arms.SUBSPACE_UPPER))
        check("support[%d] inside the frozen subspace" % (index,), inside, point)

    pool = arms.candidate_pool()
    check("candidate pool size", len(pool) == arms.CANDIDATE_POOL_COUNT, len(pool))
    identities = {o0.design_identity(list(d))["design_id"] for d in pool}
    check("candidate pool has no duplicate coordinates",
          len(identities) == len(pool), len(identities))
    check("candidate pool is coordinates only", isinstance(pool[0][0], float))
    for design in pool:
        point = o0.design_to_subspace(list(design))
        if not all(lo - 1e-12 <= v <= hi + 1e-12
                   for v, lo, hi in zip(point, arms.SUBSPACE_LOWER, arms.SUBSPACE_UPPER)):
            check("pool inside subspace", False, point)
            break
    else:
        check("pool inside subspace", True)

    warm = arms.sobol_warm_start()
    check("sobol warm start size", len(warm) == arms.WARM_START_COUNT, len(warm))

    normalizer = arms.load_a0_normalizer()
    check("A0 normalizer x_mean is 12D", normalizer.x_mean.shape == (12,))
    check("A0 normalizer y_scale positive", normalizer.y_scale > 0)

    for arm in ("COND_SUPERVISED_KSHOT_BO", "COND_FOMAML_KSHOT_BO"):
        params, meta = arms.load_checkpoint(arms.CHECKPOINT_ARM[arm])
        shapes = [tuple(t.shape) for t in params.tensors]
        expected = [(16, 32), (32,), (32, 32), (32,), (32, 1), (1,)]
        check("%s checkpoint shapes 16->32->32->1" % (arm,), shapes == expected, shapes)
        check("%s checkpoint input_dim 16" % (arm,), meta["input_dim"] == 16)
        check("%s checkpoint sha256 recorded" % (arm,), len(meta["checkpoint_sha256"]) == 64)

    # Synthetic support rows (values invented) only to exercise the inference path.
    task = ev.task_spec("O1-M190")
    synthetic = []
    for index in range(arms.K_SUPPORT):
        design = support[index]
        synthetic.append(Observation(
            observation_id="SELFTEST-%02d" % (index,), task_id=task.task_id,
            design=tuple(float(v) for v in design), partition="support",
            source_kind="vspaero_raw", status="ok", di_n=121000.0 + index * 100.0,
            q_pa=task.dynamic_pressure_pa, sref_m2=358.25, cdi=0.0330, cl=0.18,
            raw_sha256="0" * 64,
        ))
    for arm in ("COND_SUPERVISED_KSHOT_BO", "COND_FOMAML_KSHOT_BO"):
        ranking = arms.kshot_ranked_candidates(arms.CHECKPOINT_ARM[arm], "O1-M190",
                                               synthetic, pool)
        check("%s ranks the whole pool" % (arm,),
              len(ranking["order"]) == len(pool) and len(set(ranking["order"])) == len(pool))
        check("%s predicted values finite" % (arm,),
              np.all(np.isfinite(ranking["predicted"])))
        steps = arms.load_checkpoint(arms.CHECKPOINT_ARM[arm])[1]["maml_config"]["inner_steps"]
        check("%s inner adaptation ran %d steps" % (arm, steps),
              len(ranking["inner_losses"]) == steps,
              "%d vs %d" % (len(ranking["inner_losses"]), steps))
        check("%s context vector is 4D" % (arm,), len(ranking["context_vector"]) == 4)

    ledger = arms.ArmLedger("SELFTEST")
    for index in range(arms.CAPS["affordable_designs_per_arm"]):
        ledger.add(arms.DesignRecord(arm="SELFTEST", role="warm_start",
                                     design_index=index, tag="d%02d" % index,
                                     x12=support[index % 3]))
    check("ledger holds the affordable design count",
          len(ledger.records) == arms.CAPS["affordable_designs_per_arm"])
    try:
        ledger.add(arms.DesignRecord(arm="SELFTEST", role="adaptive",
                                     design_index=99, tag="d99", x12=support[0]))
    except RuntimeError as error:
        check("ledger refuses to exceed the affordable design count",
              "affordable design count" in str(error), str(error))
    else:
        check("ledger refuses to exceed the affordable design count", False, "no error")

    per_arm_internal = arms.CAPS["affordable_designs_per_arm"] * arms.INTERNAL_PER_DESIGN
    check("eight designs cost exactly 160 internal",
          per_arm_internal == arms.CAPS["max_internal_per_arm"], per_arm_internal)
    per_arm_starts = arms.CAPS["affordable_designs_per_arm"] * arms.STARTS_PER_DESIGN
    check("eight designs cost 16 starts, inside the 24 start cap",
          per_arm_starts == 16 and per_arm_starts <= arms.CAPS["max_starts_per_arm"],
          per_arm_starts)
    check("three arms are 480 equivalent internal",
          3 * per_arm_internal == arms.CAPS["max_internal_all_arms"])
    shared = arms.SHARED_SUPPORT_COUNT * arms.STARTS_PER_DESIGN
    check("physical starts = 48 equivalent - 3 shared support x 2",
          3 * per_arm_starts - 2 * shared == 36, 3 * per_arm_starts - 2 * shared)

    payload = {"schema": "dreal005.o1_selftest.v1", "checks": 0, "failures": FAILURES,
               "zero_physical": True, "caps": arms.CAPS,
               "target_improvement_fraction": arms.TARGET_IMPROVEMENT_FRACTION}
    out = RUN / "audits" / "o1_selftest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n%d failure(s)" % (len(FAILURES),))
    if FAILURES:
        for failure in FAILURES:
            print(" -", failure)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
