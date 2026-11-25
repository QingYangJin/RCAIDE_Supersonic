import json, csv, os
run = r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01"
d = json.load(open(run + "/v1l_bo_results.json"))
ev = d["evaluations"]
print("evals", len(ev), "keys", list(ev[0].keys()))
out = run + "/tables"
os.makedirs(out, exist_ok=True)
with open(out + "/v1l_bo_evaluations.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["index","phase","sweep_1","sweep_2","cdi","alpha_deg","di_N","status","wall_s"])
    for r in ev:
        w.writerow([r["index"], r["phase"], "%.9f" % r["sweep_1"], "%.9f" % r["sweep_2"],
                    "%.12f" % r["cdi"], "%.6f" % r["alpha_deg"],
                    "%.3f" % (r["cdi"]*20483.94*358.25), r["status"], "%.2f" % r["wall_s"]])
print("csv bytes", os.path.getsize(out + "/v1l_bo_evaluations.csv"))
best = sorted([r for r in ev if r["cdi"]], key=lambda r: r["cdi"])[:3]
print("top3", [(round(r["sweep_1"],4), round(r["sweep_2"],4), "%.9f" % r["cdi"], r["phase"]) for r in best])
print("phases", {p: sum(1 for r in ev if r["phase"]==p) for p in ("bootstrap","bo")})
print("status", {s: sum(1 for r in ev if r["status"]==s) for s in {r["status"] for r in ev}})
print("wall_total", round(sum(r["wall_s"] for r in ev),1))
