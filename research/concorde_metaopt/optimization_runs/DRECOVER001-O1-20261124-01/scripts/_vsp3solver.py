
import hashlib, re, json
import xml.etree.ElementTree as ET

IDPAT = re.compile(r"^[A-Z]{8,12}$")   # OpenVSP element ids are 9, 10 or 11 uppercase chars

PAIRS = [
 ("O1","baseline", r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/baseline_solver.vsp3",
   r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/SUPPORT/o1-s00-refine/o1-s00-refine.vsp3"),
 ("O1","sobol_best", r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/sobol_best_solver.vsp3",
   r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/o1-d06-refine.vsp3"),
 ("O1","supervised_best", r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/supervised_best_solver.vsp3",
   r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_COND_SUPERVISED_KSHOT_BO/o1-d07-refine/o1-d07-refine.vsp3"),
 ("O0","baseline", r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/geometry/baseline_solver.vsp3",
   r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/B02/o0-d00-refine/o0-d00-refine.vsp3"),
 ("O0","optimized", r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/geometry/optimized_solver.vsp3",
   r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/B02/o0-d10-refine/o0-d10-refine.vsp3"),
]

def canon(path):
    root = ET.parse(path).getroot()
    out = []
    for el in root.iter():
        attrs = tuple(sorted((k, "<ID>" if IDPAT.match(v) else v) for k, v in el.attrib.items()))
        text = (el.text or "").strip()
        out.append((el.tag, attrs, "<ID>" if IDPAT.match(text) else text))
    return out

rows = []
for run, label, delivered, case in PAIRS:
    a, b = canon(delivered), canon(case)
    diffs = []
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            diffs.append({"index": i, "delivered": [a[i][0], list(a[i][1]), a[i][2]],
                          "case": [b[i][0], list(b[i][1]), b[i][2]]})
    same = a == b
    rows.append({"run": run, "role": label, "delivered": delivered, "case": case,
                 "elements_delivered": len(a), "elements_case": len(b),
                 "identical_modulo_element_ids": same, "difference_count": len(diffs),
                 "differences": diffs[:10],
                 "raw_sha256_delivered": hashlib.sha256(open(delivered,"rb").read()).hexdigest(),
                 "raw_sha256_case": hashlib.sha256(open(case,"rb").read()).hexdigest()})
    print("%-2s %-16s elements=%d/%d identical=%s diffs=%d" % (run, label, len(a), len(b), same, len(diffs)), flush=True)
    for d in diffs[:3]:
        print("    ", json.dumps(d)[:300])

print("mismatches", sum(1 for r in rows if not r["identical_modulo_element_ids"]))
json.dump(rows, open(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/_geom_probe.json","w",encoding="utf-8"), indent=1)
