
import xml.etree.ElementTree as ET, re, collections
IDPAT = re.compile(r'^[A-Z]{11}$')
files = {
 "O1 full baseline": r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/baseline.vsp3",
 "O1 solver baseline": r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/baseline_solver.vsp3",
 "O1 case sobol": r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/o1-d06-refine.vsp3",
 "O1 solver sobol": r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/sobol_best_solver.vsp3",
}
for name, p in files.items():
    root = ET.parse(p).getroot()
    geoms = [e for e in root.iter("Geom")]
    types = collections.Counter(g.findtext("Type") or "?" for g in geoms)
    names = [ (g.findtext("Name") or "?") + ":" + (g.findtext("Type") or "?") for g in geoms]
    print("%-20s total_elements=%5d geoms=%2d %s" % (name, sum(1 for _ in root.iter()), len(geoms), dict(types)))
    print("    ", names)
