# -*- coding: utf-8 -*-
"""V1-D: RCAIDE full aero pipeline (drag ledger) at M=2.02 + comparison to VSPAERO."""
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
ALT, M_O0, ALPHA0, Q_O0 = 18288.0, 2.02, 5.18132, 20483.94
atm = US_Standard_1976().compute_values(ALT)
f = lambda x: float(np.ravel(np.asarray(x, dtype=float))[0])
T, P, RHO, ASND = f(atm.temperature), f(atm.pressure), f(atm.density), f(atm.speed_of_sound)
MU, NU = f(atm.dynamic_viscosity), f(atm.kinematic_viscosity)

CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
data = load_config(CONFIG); data["frozen"] = False
space = design_space_from_config(data, source="V1-side-study")
module = load_template_module(verify_hash=False)
BASE_X = dict(zip(space.names, [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]))
full_x = space.expand(dict(BASE_X))
geom = build_geometry(tuple(full_x), tuple(full_x.values()))
_, veh = build_vehicle(geom, module=module)
for w in veh.wings:
    wing_planform(w)
veh.reference_area, veh.reference_chord, veh.reference_span = SREF, CREF, BREF
print("vehicle built; wings:", [w.tag for w in veh.wings], flush=True)

def make_state(a, mach, adeg):
    st = Data(); st.conditions = Results(); st.analyses = Data()
    st.analyses.aerodynamics = a
    c = st.conditions
    V = mach * ASND
    c.freestream.altitude = np.array([[ALT]])
    c.freestream.mach_number = np.array([[mach]])
    c.freestream.velocity = np.array([[V]])
    c.freestream.temperature = np.array([[T]])
    c.freestream.pressure = np.array([[P]])
    c.freestream.density = np.array([[RHO]])
    c.freestream.speed_of_sound = np.array([[ASND]])
    c.freestream.dynamic_pressure = np.array([[0.5*RHO*V*V]])
    c.freestream.gravity = np.array([[9.81]])
    c.freestream.kinematic_viscosity = np.array([[NU]])
    c.freestream.dynamic_viscosity = np.array([[MU]])
    c.freestream.reynolds_number = np.array([[RHO*V*CREF/MU]])
    c.aerodynamics.angles.alpha = np.array([[math.radians(adeg)]])
    c.aerodynamics.angles.beta = np.array([[0.0]])
    c.aerodynamics.angles.bank = np.array([[0.0]])
    return st

a = Vortex_Lattice_Method(); a.settings.use_surrogate = False; a.vehicle = veh; a.initialize(veh)
a.settings.number_of_spanwise_vortices = 30; a.settings.number_of_chordwise_vortices = 15

out = {"note": "full RCAIDE aerodynamics pipeline (VLM + parasite + induced + compressibility)"}
try:
    st = make_state(a, M_O0, ALPHA0)
    a.evaluate(st, veh)
    c = st.conditions
    def get(path):
        try:
            o = c
            for p in path.split("."): o = getattr(o, p)
            return float(np.ravel(o)[0])
        except Exception as e:
            return "ERR:%s:%s" % (type(e).__name__, str(e)[:80])
    paths = {
        "CL_inviscid_total": "aerodynamics.coefficients.lift.inviscid.total",
        "CL_total": "aerodynamics.coefficients.lift.total",
        "CD_drag_total": "aerodynamics.coefficients.drag.total",
        "CD_drag_parasite_total": "aerodynamics.coefficients.drag.parasite.total",
        "CD_drag_induced_inviscid": "aerodynamics.coefficients.drag.induced.inviscid",
        "CD_drag_induced_total": "aerodynamics.coefficients.drag.induced.total",
        "CD_drag_compressibility": "aerodynamics.coefficients.drag.compressibility",
        "CD_drag_misc": "aerodynamics.coefficients.drag.misc",
    }
    for k, p in paths.items():
        out[k] = get(p)
    print(json.dumps(out, indent=1), flush=True)
except Exception:
    import traceback
    out["error"] = traceback.format_exc()[-1500:]
    print("FULL FAILED\n", out["error"], flush=True)

with open(os.path.join(OUT, "v1_d_full_pipeline.json"), "w") as fh:
    json.dump(out, fh, indent=2)
print("WROTE v1_d_full_pipeline.json", flush=True)
