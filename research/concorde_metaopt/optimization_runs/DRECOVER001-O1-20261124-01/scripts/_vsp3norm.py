
import re, json, hashlib
pairs = [
 ("O1","D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/baseline.vsp3","D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/SUPPORT/o1-s00/o1-s00.vsp3"),
 ("O1","D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/sobol_best.vsp3","D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/o1-d06-refine.vsp3"),
 ("O1","D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/supervised_best.vsp3","D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_COND_SUPERVISED_KSHOT_BO/o1-d07-refine/o1-d07-refine.vsp3"),
 ("O0","D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/geometry/baseline.vsp3","D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/B02/o0-d00-refine/o0-d00-refine.vsp3"),
 ("O0","D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/final_aircraft/geometry/optimized.vsp3","D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/cases/B02/o0-d10-refine/o0-d10-refine.vsp3"),
]
ID = re.compile(r'\b[A-Z]{11}\b')
def norm(p):
    t = open(p, encoding="utf-8", errors="replace").read()
    t = ID.sub("ID000000000", t)
    return t
for run, a, b in pairs:
    na, nb = norm(a), norm(b)
    same = na == nb
    print("%-2s %-46s normalized_equal=%s" % (run, a.split("/geometry/")[1], same))
    if not same:
        la, lb = na.splitlines(), nb.splitlines()
        d = [(i,x,y) for i,(x,y) in enumerate(zip(la,lb)) if x!=y]
        print("   remaining diff lines:", len(d), "of", len(la), len(lb))
        for i,x,y in d[:6]:
            print("   ", i, "A:", x.strip()[:140])
            print("   ", i, "B:", y.strip()[:140])
    print("   norm_sha_a=", hashlib.sha256(na.encode()).hexdigest()[:24], "norm_sha_b=", hashlib.sha256(nb.encode()).hexdigest()[:24])
