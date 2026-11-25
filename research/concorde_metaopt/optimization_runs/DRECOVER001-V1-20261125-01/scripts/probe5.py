
import os, sys, math
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
os.chdir(REPO); sys.path.insert(0, REPO)
import RCAIDE
from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.aircraft.design_space import design_space_from_config
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle, load_template_module
CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
data = load_config(CONFIG); data["frozen"] = False
space = design_space_from_config(data, source="probe")
full = space.expand(dict(space.baseline_dict()))
geom = build_geometry(tuple(full), tuple(full.values()))
module = load_template_module(verify_hash=False)
t, vehicle = build_vehicle(geom, module=module)
w = vehicle.wings["main_wing"]
print("before: Sref", vehicle.reference_area, "cref", vehicle.reference_chord, "bref", vehicle.reference_span, flush=True)
print("wing chords: root", w.chords.root, "tip", w.chords.tip, "mean_aero", getattr(w.chords, "mean_aerodynamic", None), "mean_geo", getattr(w.chords,"mean_geometric",None), flush=True)
g = RCAIDE.Framework.Analyses.Geometry.Geometry()
g.vehicle = vehicle
try:
    out = g.evaluate()
    print("geometry evaluate ok", type(out), flush=True)
except Exception as e:
    print("geometry evaluate failed:", type(e).__name__, e, flush=True)
print("after: Sref", vehicle.reference_area, "cref", vehicle.reference_chord, "bref", vehicle.reference_span, flush=True)
