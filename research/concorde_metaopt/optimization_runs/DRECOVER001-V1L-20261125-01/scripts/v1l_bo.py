# -*- coding: utf-8 -*-
"""V1L optimization: GP-EI BO on the RCAIDE supersonic VLM objective at 20x10.

Pre-registered protocol (written before the run, see V1L_PREREGISTRATION.md):
  objective  = CDi_trefftz at CL_target, alpha solved per design
  lattice    = (20, 10) spanwise x chordwise, identical for every design
  subspace   = sweep_1 in [65.5, 68.5], sweep_2 in [46.5, 49.5]; the other 10 dims frozen
  budget     = 24 LHS bootstrap + 96 BO acquisitions = 120 VLM evaluations
  confirmation = top-5 designs re-evaluated at 30x15 and 45x25; an improvement is
                 only claimed if the sign survives both finer lattices
"""
import os, sys, json, time
import numpy as np
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
OUT  = r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01"
sys.path.insert(0, REPO); os.chdir(REPO)
from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend
from research.concorde_metaopt.dreal001.optimizers.recovery_bo import (
    RecoveryGaussianProcessBO, generate_initial_designs)

CFG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
SEED = 20261125
BOOT = 24
TOTAL = 120
LOWER = np.array([65.5, 46.5])
UPPER = np.array([68.5, 49.5])
BASE = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]

be = SupersonicVLMBackend(REPO, CFG, lattice=(20, 10))
NAMES = be.design_names
Q, S = be._atmo["dynamic_pressure_Pa"], 358.25

def design(s1, s2):
    d = dict(zip(NAMES, BASE)); d["sweep_1"] = float(s1); d["sweep_2"] = float(s2); return d

def run(point, purpose):
    rec = be.evaluate(design(point[0], point[1]), purpose=purpose)
    return rec

# baseline reference (the frozen 12D baseline design)
t0 = time.time()
base_rec = run([67.0, 48.0], "baseline")
print("baseline CDi=%.9f alpha=%.5f wall=%.2fs" % (base_rec["objective"], base_rec["alpha_deg"], base_rec["wall_seconds"]), flush=True)

bo = RecoveryGaussianProcessBO(LOWER, UPPER, seed=SEED)
rows = []
seen = set()
key = lambda p: (round(float(p[0]), 9), round(float(p[1]), 9))

boot = generate_initial_designs(LOWER, UPPER, count=BOOT, seed=SEED)
for i, point in enumerate(boot):
    point = np.asarray(point, dtype=float)
    if key(point) in seen:
        continue
    rec = run(point, "bootstrap")
    ok = rec["status"] == "VALID"
    bo.tell(point, {"valid": ok, "feasible": ok, "objective": rec["objective"] if ok else None})
    seen.add(key(point))
    rows.append({"index": len(rows), "phase": "bootstrap", "sweep_1": float(point[0]), "sweep_2": float(point[1]),
                 "cdi": rec["objective"], "alpha_deg": rec["alpha_deg"], "status": rec["status"],
                 "di_N": rec.get("cdi_times_q_sref_N"), "wall_s": rec["wall_seconds"]})
    if (i+1) % 8 == 0:
        print("bootstrap %d/%d" % (i+1, BOOT), flush=True)

stall = 0
while len(rows) < TOTAL:
    point = np.asarray(bo.ask()["design_vector"], dtype=float)
    if key(point) in seen:
        stall += 1
        if stall > 40:
            print("no fresh acquisition after 40 asks; stopping at %d evals" % len(rows), flush=True)
            break
        continue
    stall = 0
    rec = run(point, "bo")
    ok = rec["status"] == "VALID"
    bo.tell(point, {"valid": ok, "feasible": ok, "objective": rec["objective"] if ok else None})
    seen.add(key(point))
    rows.append({"index": len(rows), "phase": "bo", "sweep_1": float(point[0]), "sweep_2": float(point[1]),
                 "cdi": rec["objective"], "alpha_deg": rec["alpha_deg"], "status": rec["status"],
                 "di_N": rec.get("cdi_times_q_sref_N"), "wall_s": rec["wall_seconds"]})
    if len(rows) % 12 == 0:
        json.dump({"partial": rows}, open(os.path.join(OUT, "v1l_bo_partial.json"), "w"), indent=1)
        best = min((r for r in rows if r["cdi"]), key=lambda r: r["cdi"])
        print("bo %3d evals | best CDi=%.9f at (%.4f, %.4f) | %.0fs" % (
            len(rows), best["cdi"], best["sweep_1"], best["sweep_2"], time.time()-t0), flush=True)

valid = [r for r in rows if r["cdi"]]
valid.sort(key=lambda r: r["cdi"])
best = valid[0]
improvement_pct = 100.0 * (base_rec["objective"] - best["cdi"]) / base_rec["objective"]
print("\nBEST 20x10: (%.6f, %.6f) CDi=%.9f  alpha=%.5f  vs baseline %.2f%% lower" % (
    best["sweep_1"], best["sweep_2"], best["cdi"], best["alpha_deg"], improvement_pct), flush=True)
print("Di base=%.3f N best=%.3f N dDi=%.3f N" % (
    base_rec["objective"]*Q*S, best["cdi"]*Q*S, (base_rec["objective"]-best["cdi"])*Q*S), flush=True)

# ---- cross-lattice confirmation of the top-5 (and the baseline) ----
top = valid[:5]
conf = {"baseline": {}, "candidates": []}
for lat in ((30, 15), (45, 25)):
    be2 = SupersonicVLMBackend(REPO, CFG, lattice=lat)
    rb = be2.evaluate(design(67.0, 48.0), purpose="confirm-baseline")
    tag = "%dx%d" % lat
    conf["baseline"][tag] = {"cdi": rb["objective"], "alpha_deg": rb["alpha_deg"], "status": rb["status"]}
    print("confirm baseline %s CDi=%.9f" % (tag, rb["objective"]), flush=True)
    for r in top:
        rc = be2.evaluate(design(r["sweep_1"], r["sweep_2"]), purpose="confirm")
        conf["candidates"].append({"sweep_1": r["sweep_1"], "sweep_2": r["sweep_2"], "lattice": tag,
                                   "cdi": rc["objective"], "alpha_deg": rc["alpha_deg"], "status": rc["status"],
                                   "dcdi_pct_vs_baseline": 100.0*(conf["baseline"][tag]["cdi"]-rc["objective"])/conf["baseline"][tag]["cdi"]})
        print("  cand (%.4f,%.4f) %s CDi=%.9f d=%.4f%%" % (r["sweep_1"], r["sweep_2"], tag, rc["objective"],
              conf["candidates"][-1]["dcdi_pct_vs_baseline"]), flush=True)

out = {"schema": "dreal005.v1l_bo.v1", "seed": SEED, "lattice": [20, 10], "budget": TOTAL,
       "bootstrap": BOOT, "objective_name": "CDi_trefftz", "cl_target": be.cl_target,
       "subspace": {"sweep_1": [65.5, 68.5], "sweep_2": [46.5, 49.5]},
       "baseline": {"sweep_1": 67.0, "sweep_2": 48.0, "cdi": base_rec["objective"],
                    "alpha_deg": base_rec["alpha_deg"], "di_N": base_rec["objective"]*Q*S},
       "best": {"sweep_1": best["sweep_1"], "sweep_2": best["sweep_2"], "cdi": best["cdi"],
                "alpha_deg": best["alpha_deg"], "di_N": best["cdi"]*Q*S, "improvement_pct": improvement_pct},
       "confirmation": conf, "evaluations": rows, "provenance": be.provenance(),
       "wall_seconds": round(time.time()-t0, 1)}
json.dump(out, open(os.path.join(OUT, "v1l_bo_results.json"), "w"), indent=2)
print("\nWROTE v1l_bo_results.json  (%.1fs total)" % (time.time()-t0), flush=True)
