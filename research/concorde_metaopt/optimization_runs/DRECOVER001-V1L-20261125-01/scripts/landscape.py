# -*- coding: utf-8 -*-
"""Landscape smoothness + lattice rank-stability of the RCAIDE VLM objective."""
import os, sys, json, time
import numpy as np
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
OUT = r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01"
sys.path.insert(0, REPO); os.chdir(REPO)
from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend
CFG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")

BASE = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]
def vec(s1, s2, names):
    d = dict(zip(names, BASE)); d["sweep_1"] = s1; d["sweep_2"] = s2; return d

grid1 = [65.5 + 0.25*i for i in range(13)]   # 65.5 .. 68.5
grid2 = [46.5 + 0.25*i for i in range(13)]   # 46.5 .. 49.5

out = {}
for lat in ((20, 10), (30, 15)):
    be = SupersonicVLMBackend(REPO, CFG, lattice=lat)
    names = be.design_names
    t0 = time.time()
    s1 = [be.evaluate(vec(x, 48.0, names))["objective"] for x in grid1]
    s2 = [be.evaluate(vec(67.0, x, names))["objective"] for x in grid2]
    out["%dx%d" % lat] = {"sweep1_x": grid1, "sweep1_cdi": s1, "sweep2_x": grid2, "sweep2_cdi": s2,
                          "wall_s": round(time.time()-t0, 1), "evals": be.solve_count}
    print(lat, "done in %.1fs" % (time.time()-t0), flush=True)

def diffs(v):
    v = np.asarray(v); return np.diff(v)
rep = {}
for lat, d in out.items():
    c1, c2 = np.asarray(d["sweep1_cdi"]), np.asarray(d["sweep2_cdi"])
    rep[lat] = {
        "sweep1_monotone_decreasing": bool(np.all(np.diff(c1) < 0)),
        "sweep1_sign_changes": int(np.sum(np.diff(np.sign(np.diff(c1))) != 0)),
        "sweep1_range_pct": float(100*(c1.max()-c1.min())/c1.mean()),
        "sweep2_monotone_increasing": bool(np.all(np.diff(c2) > 0)),
        "sweep2_sign_changes": int(np.sum(np.diff(np.sign(np.diff(c2))) != 0)),
        "sweep2_range_pct": float(100*(c2.max()-c2.min())/c2.mean()),
        "sweep1_min_at": float(d["sweep1_x"][int(np.argmin(c1))]),
        "sweep2_min_at": float(d["sweep2_x"][int(np.argmin(c2))]),
    }
# rank agreement between lattices
from scipy.stats import spearmanr
a, b = out["20x10"], out["30x15"]
rep["rank"] = {
    "sweep1_spearman": float(spearmanr(a["sweep1_cdi"], b["sweep1_cdi"]).statistic),
    "sweep2_spearman": float(spearmanr(a["sweep2_cdi"], b["sweep2_cdi"]).statistic),
    "sweep1_pearson": float(np.corrcoef(a["sweep1_cdi"], b["sweep1_cdi"])[0,1]),
    "sweep2_pearson": float(np.corrcoef(a["sweep2_cdi"], b["sweep2_cdi"])[0,1]),
    "level_ratio_20_over_30": float(np.mean(a["sweep1_cdi"])/np.mean(b["sweep1_cdi"])),
}
print(json.dumps(rep, indent=1), flush=True)
json.dump({"raw": out, "summary": rep}, open(os.path.join(OUT, "landscape_probe.json"), "w"), indent=2)
print("WROTE landscape_probe.json", flush=True)
