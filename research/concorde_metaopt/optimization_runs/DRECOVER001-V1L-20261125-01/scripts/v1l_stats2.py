import csv, json, statistics as st
base = r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/training/tables/"
m = list(csv.DictReader(open(base+"v1l_arm_metrics.csv")))
lab = json.load(open(r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/v1l_labels.json"))["labels"]
scale = {}
for k,v in lab.items(): scale.setdefault(k.split("|")[0], []).append(v["di_n"])
mean_lab = {t: st.mean(v) for t,v in scale.items()}
rel, sp = {}, {}
for r in m:
    if r["split"] != "test": continue
    rel.setdefault((r["arm"], r["k"]), []).append(float(r["mae_n"])/mean_lab[r["task_id"]])
    if r["spearman"] not in ("", None):
        sp.setdefault((r["arm"], r["k"]), []).append(float(r["spearman"]))
print("arm                    K=0 rel  K=1 rel  K=3 rel  | K=0 rho  K=1 rho  K=3 rho")
for arm in ("RANDOM_INIT","POOLED_PRETRAIN_12D","COND_SUPERVISED_16D","FOMAML_12D","COND_FOMAML_16D"):
    rh = ["%+.3f" % st.mean(sp[(arm,k)]) if sp.get((arm,k)) else "  n/a" for k in ("0","1","3")]
    print("  %-20s" % arm, "  ".join("%6.1f%%" % (100*st.mean(rel[(arm,k)])) for k in ("0","1","3")), " | ", "  ".join(rh))
print("\ntest label magnitude (VLM N):", {t: round(mean_lab[t],1) for t in mean_lab})
