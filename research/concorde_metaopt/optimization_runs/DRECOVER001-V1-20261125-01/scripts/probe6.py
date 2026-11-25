
import os, sys, math
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
os.chdir(REPO); sys.path.insert(0, REPO)
import numpy as np
from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.aircraft.design_space import design_space_from_config
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle, load_template_module
from RCAIDE.Library.Methods.Geometry.Planform.wing_planform import wing_planform
from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
from RCAIDE.Library.Methods.Aerodynamics.Vortex_Lattice_Method.VLM import VLM
from RCAIDE.Framework.Core import Data
from RCAIDE.Framework.Mission.Common.Results import Results
CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
data = load_config(CONFIG); data["frozen"] = False
space = design_space_from_config(data, source="probe")
full = space.expand(dict(space.baseline_dict()))
geom = build_geometry(tuple(full), tuple(full.values()))
module = load_template_module(verify_hash=False)
t, veh = build_vehicle(geom, module=module)
for w in veh.wings: wing_planform(w)
veh.reference_area=358.25; veh.reference_chord=18.489893; veh.reference_span=25.604638
a = Vortex_Lattice_Method(); a.settings.use_surrogate=False; a.vehicle=veh; a.initialize(veh)
a.settings.number_of_spanwise_vortices=20; a.settings.number_of_chordwise_vortices=10
def cond(mach, adeg):
    st = Data(); st.conditions = Results()
    c = st.conditions
    c.freestream.mach_number=np.array([[mach]]); c.freestream.velocity=np.array([[mach*295.07]])
    c.aerodynamics.angles.alpha=np.array([[math.radians(adeg)]]); c.aerodynamics.angles.beta=np.array([[0.0]])
    return st
for adeg in [0.0, 2.0, 5.18132, 8.0]:
    res = VLM(cond(2.02, adeg).conditions, a.settings, veh)
    print("alpha=%6.3f keys=%s" % (adeg, [k for k in res.keys()][:12]), flush=True)
    print("   CL shape", np.shape(res.CL), "CL", np.ravel(res.CL)[:3], "CDi", np.ravel(res.CDrag_induced)[:3], flush=True)
    break
# also dump wing info
w = veh.wings["main_wing"]
print("segments", list(w.segments.keys()), flush=True)
for k, s in w.segments.items():
    print(" seg", k, "root_chord", getattr(s,"root_chord",None), "tip_chord", getattr(s,"tip_chord",None), "twist", getattr(s,"twist",None), flush=True)
