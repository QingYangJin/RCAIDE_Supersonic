
# -*- coding: utf-8 -*-
"""Probe 4: full RCAIDE aero pipeline (VLM + parasite + induced + compressibility) at M=2.02."""
import os, sys, math, time
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
os.chdir(REPO); sys.path.insert(0, REPO)
import numpy as np
from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.aircraft.design_space import design_space_from_config
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle, load_template_module
from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
from RCAIDE.Framework.Mission.Common.Results import Results

CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
data = load_config(CONFIG); data["frozen"] = False
space = design_space_from_config(data, source="probe")
full = space.expand(dict(space.baseline_dict()))
geom = build_geometry(tuple(full), tuple(full.values()))
module = load_template_module(verify_hash=False)
template, vehicle = build_vehicle(geom, module=module)

aer = Vortex_Lattice_Method(); aer.settings.use_surrogate = False; aer.vehicle = vehicle
aer.initialize(vehicle)

ATMO = template.base_analysis  # not used
def atmosphere(alt):
    from RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976 import US_Standard_1976
    a = US_Standard_1976(); r = a.compute_values(alt)
    return r

def make_state(mach, adeg, alt=18288.0):
    st = Results()
    at = atmosphere(alt)
    T = float(at.temperature); P = float(at.pressure); rho = float(at.density); a_snd = float(at.speed_of_sound)
    V = mach * a_snd
    st.conditions.freestream.altitude = np.array([[alt]])
    st.conditions.freestream.mach_number = np.array([[mach]])
    st.conditions.freestream.velocity = np.array([[V]])
    st.conditions.freestream.temperature = np.array([[T]])
    st.conditions.freestream.pressure = np.array([[P]])
    st.conditions.freestream.density = np.array([[rho]])
    st.conditions.freestream.speed_of_sound = np.array([[a_snd]])
    st.conditions.freestream.gravity = np.array([[9.81]])
    st.conditions.freestream.dynamic_pressure = np.array([[0.5*rho*V*V]])
    st.conditions.freestream.kinematic_viscosity = np.array([[float(at.kinematic_viscosity)]])
    st.conditions.freestream.dynamic_viscosity = np.array([[float(at.dynamic_viscosity)]])
    st.conditions.freestream.reynolds_number = np.array([[rho*V*vehicle.reference_chord/float(at.dynamic_viscosity)]])
    st.conditions.aerodynamics.angles.alpha = np.array([[math.radians(adeg)]])
    st.conditions.aerodynamics.angles.beta = np.array([[0.0]])
    st.conditions.aerodynamics.angles.bank = np.array([[0.0]])
    return st

def run(nsw, ncw, mach=2.02, adeg=5.18132):
    aer.settings.number_of_spanwise_vortices = nsw
    aer.settings.number_of_chordwise_vortices = ncw
    st = make_state(mach, adeg)
    t0 = time.time()
    out = aer.evaluate(st, vehicle)
    c = st.conditions
    d = {}
    d["CL"] = float(c.aerodynamics.coefficients.lift.inviscid.total[0][0])
    for k in ("inviscid","viscous","total","wings"):
        try: d["CDi_"+k] = float(c.aerodynamics.coefficients.drag.induced[k][0][0])
        except Exception as e: d["CDi_"+k] = "ERR:"+type(e).__name__
    for k in ("compressibility","parasite","total"):
        try: d["CD_"+"compress" if k=="compressibility" else "CD_"+k] = float(getattr(c.aerodynamics.coefficients.drag,k)[0][0]) if k!="total" else float(c.aerodynamics.coefficients.drag.total[0][0])
        except Exception as e: d["CD_"+k] = "ERR:"+type(e).__name__
    d["secs"] = round(time.time()-t0,2)
    return d

print("bref", vehicle.reference_span, "cref", vehicle.reference_chord, flush=True)
for (nsw,ncw) in [(8,4),(15,8),(30,15)]:
    print("lattice %2dx%-2d" % (nsw,ncw), run(nsw,ncw), flush=True)
