# -*- coding: utf-8 -*-
import os, sys, json, math, warnings, traceback
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
os.chdir(REPO); sys.path.insert(0, REPO)
import numpy as np
warnings.simplefilter("error")   # turn numpy RuntimeWarnings into exceptions to locate the NaN
from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.aircraft.design_space import design_space_from_config
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle, load_template_module
from RCAIDE.Framework.Mission.Common.Results import Results
from RCAIDE.Framework.Core import Data
from RCAIDE.Library.Methods.Geometry.Planform.wing_planform import wing_planform
from RCAIDE.Library.Methods.Aerodynamics.Common.Drag.compressibility_drag import compressibility_drag
from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
from RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976 import US_Standard_1976

SREF, CREF, BREF = 358.25, 18.489893, 25.604638
atm = US_Standard_1976().compute_values(18288.0)
f = lambda x: float(np.ravel(np.asarray(x, dtype=float))[0])
CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
data = load_config(CONFIG); data["frozen"]=False
space = design_space_from_config(data, source="V1-side-study")
module = load_template_module(verify_hash=False)
BASE_X = dict(zip(space.names, [358.25,1.83,67.0,48.0,71.0,0.480469,0.945313,0.408284,0.130178,0.0,33.91,0.0]))
fx = space.expand(dict(BASE_X)); geom = build_geometry(tuple(fx), tuple(fx.values()))
_, veh = build_vehicle(geom, module=module)
for w in veh.wings: wing_planform(w)
veh.reference_area, veh.reference_chord, veh.reference_span = SREF, CREF, BREF
for w in veh.wings:
    print(w.tag, "tc=", w.thickness_to_chord, "sweep_le_deg=", round(math.degrees(w.sweeps.leading_edge),3) if w.sweeps.leading_edge==w.sweeps.leading_edge else w.sweeps.leading_edge,
          "span=", w.spans.projected, "mac=", w.chords.mean_aerodynamic, "area=", w.areas.reference, flush=True)

a = Vortex_Lattice_Method(); a.settings.use_surrogate=False; a.vehicle=veh; a.initialize(veh)
st = Data(); st.conditions = Results(); st.analyses=Data(); st.analyses.aerodynamics=a
c = st.conditions; V=2.02*f(atm.speed_of_sound)
for k,v in (("altitude",18288.0),("mach_number",2.02),("velocity",V),("temperature",f(atm.temperature)),
            ("pressure",f(atm.pressure)),("density",f(atm.density)),("speed_of_sound",f(atm.speed_of_sound)),
            ("dynamic_pressure",0.5*f(atm.density)*V*V),("gravity",9.81)):
    setattr(c.freestream,k,np.array([[v]]))
c.aerodynamics.angles.alpha=np.array([[math.radians(5.18132)]])
c.aerodynamics.angles.beta=np.array([[0.0]]); c.aerodynamics.angles.bank=np.array([[0.0]])
c.aerodynamics.coefficients.lift.total = np.array([[0.19040900982746334]])
try:
    compressibility_drag(st, a.settings, veh)
    print("compressible.total =", float(np.ravel(c.aerodynamics.coefficients.drag.compressible.total)[0]), flush=True)
except Exception:
    print("RAISED:\n", traceback.format_exc()[-1200:], flush=True)
