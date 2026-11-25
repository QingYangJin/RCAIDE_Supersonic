import csv, statistics as st, math
p = r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/training/tables/v1l_paired_differences.csv"
rows = list(csv.DictReader(open(p)))
def ci(vals, t=2.571):  # 5 df
    m = st.mean(vals); s = st.stdev(vals) if len(vals)>1 else 0.0
    h = t*s/math.sqrt(len(vals))
    return m, m-h, m+h, s
for split in ("val","test"):
    for k in ("0","1","3"):
        d = [float(r["delta_mae_n"]) for r in rows if r["split"]==split and r["k"]==k]
        m,lo,hi,s = ci(d)
        left = [float(r["mae_n_cond_supervised"]) for r in rows if r["split"]==split and r["k"]==k]
        right = [float(r["mae_n_cond_fomaml"]) for r in rows if r["split"]==split and r["k"]==k]
        print("%-4s K=%s n=%d  sup=%.0f fomaml=%.0f  delta=%+.0f CI95[%+.0f,%+.0f] sd=%.0f  p_sign=%d/%d" % (
            split,k,len(d),st.mean(left),st.mean(right),m,lo,hi,s,
            sum(1 for v in d if v>0), sum(1 for v in d if v<0)))
# all K pooled
allv = [float(r["delta_mae_n"]) for r in rows if r["split"]=="test"]
m,lo,hi,s = ci(allv); print("test pooled all K: delta=%+.1f CI[%+.1f,%+.1f] sd=%.1f n=%d" % (m,lo,hi,s,len(allv)))
print("--- label scale per test task ---")
import json
lab = json.load(open(r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/v1l_labels.json"))["labels"]
for k,v in lab.items():
    if "M240" in k or "M260" in k: print(k.split("|")[0], round(v["di_n"],1))
