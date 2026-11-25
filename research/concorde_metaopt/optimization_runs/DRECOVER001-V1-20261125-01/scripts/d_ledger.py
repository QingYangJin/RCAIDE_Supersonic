# -*- coding: utf-8 -*-
"""V1-D2: dump the full drag ledger tree from RCAIDE evaluate() to locate the NaN."""
import os, sys, json, math
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
OUT  = r"D:/RCAIDE/.real_runs/DRECOVER001-V1-20261125-01"
os.chdir(REPO); sys.path.insert(0, REPO)
import numpy as np
from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.aircraft.design_space import design_space_from_config
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle, load_template_module
from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
from RCAIDE.Framework.Mission.Common.Results import Results
from RCAIDE.Framework.Core import Data
from RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976 import US_Standard_1976
from RCAIDE.Library.Methods.Geometry.Planform.wing_planform import wing_planform

SREF, CREF, BREF = 358.25, 18.489893, 25.604638
ALT, M_O0, ALPHA0 = 18288.0, 2.02, 5.18132
atm = US_Standard_1976().compute_values(ALT)
f = lambda x: float(np.ravel(np.asarray(x, dtype=float))[0])
T, P, RHO, ASND = f(atm.temperature), f(atm.pressure), f(atm.density), f(atm.speed_of_sound)
MU, NU = f(atm.dynamic_viscosity), f(atm.kinematic_viscosity)
CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
data = load_config(CONFIG); data["frozen"] = False
space = design_space_from_config(data, source="V1-side-study")
module = load_template_module(verify_hash=False)
BASE_X = dict(zip(space.names, [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]))
fx = space.expand(dict(BASE_X))
geom = build_geometry(tuple(fx), tuple(fx.values()))
_, veh = build_vehicle(geom, module=module)
for w in veh.wings: wing_planform(w)
veh.reference_area, veh.reference_chord, veh.reference_span = SREF, CREF, BREF

a = Vortex_Lattice_Method(); a.settings.use_surrogate=False; a.vehicle=veh; a.initialize(veh)
a.settings.number_of_spanwise_vortices=30; a.settings.number_of_chordwise_vortices=15

st = Data(); st.conditions = Results(); st.analyses = Data(); st.analyses.aerodynamics = a
c = st.conditions; V = M_O0*ASND
for k,v in (("altitude",ALT),("mach_number",M_O0),("velocity",V),("temperature",T),("pressure",P),
            ("density",RHO),("speed_of_sound",ASND),("dynamic_pressure",0.5*RHO*V*V),
            ("gravity",9.81),("kinematic_viscosity",NU),("dynamic_viscosity",MU),
            ("reynolds_number",RHO*V*CREF/MU)):
    setattr(c.freestream, k, np.array([[v]]))
c.aerodynamics.angles.alpha=np.array([[math.radians(ALPHA0)]])
c.aerodynamics.angles.beta=np.array([[0.0]]); c.aerodynamics.angles.bank=np.array([[0.0]])
a.evaluate(st, veh)

def walk(obj, prefix, depth=0):
    rows=[]
    if depth>3: return rows
    keys = list(obj.keys()) if isinstance(obj, dict) else [k for k in dir(obj) if not k.startswith("_")]
    for k in keys:
        try: v = obj[k] if isinstance(obj, dict) else getattr(obj, k)
        except Exception: continue
        if isinstance(v, dict):
            rows += walk(v, prefix+"."+k, depth+1)
        elif isinstance(v, np.ndarray) and v.size:
            try: rows.append((prefix+"."+k, float(np.ravel(v)[0])))
            except Exception: pass
        elif isinstance(v, (int,float)):
            rows.append((prefix+"."+k, float(v)))
    return rows

rows = walk(c.aerodynamics, "aero", 0)
d = {k:v for k,v in rows if "drag" in k or "lift" in k}
print(json.dumps(d, indent=1), flush=True)
with open(os.path.join(OUT,"v1_d_ledger.json"),"w") as fh: json.dump(d, fh, indent=2)
print("airfoils main_wing:", [af.tag for af in getattr(veh.wings["main_wing"],"airfoils",[])], flush=True)
print("segments/cs:", len(getattr(veh.wings["main_wing"],"segments",[])), flush=True)
