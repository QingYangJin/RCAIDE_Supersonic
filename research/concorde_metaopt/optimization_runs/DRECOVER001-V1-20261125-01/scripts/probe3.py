
# -*- coding: utf-8 -*-
"""Probe 3: build vehicle with verify_hash=False and run VLM at M=2.02."""
import os, sys, json, math, time, hashlib
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
os.chdir(REPO); sys.path.insert(0, REPO)
import numpy as np
from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.aircraft.design_space import design_space_from_config
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle, load_template_module, resolve_tutorial_path
from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
from RCAIDE.Library.Methods.Aerodynamics.Vortex_Lattice_Method.VLM import VLM
from RCAIDE.Framework.Core import Data

CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
data = load_config(CONFIG); data["frozen"] = False
space = design_space_from_config(data, source="probe")
full = space.expand(dict(space.baseline_dict()))
geom = build_geometry(tuple(full), tuple(full.values()))
tut = resolve_tutorial_path()
print("tutorial", tut, "sha", hashlib.sha256(tut.read_bytes()).hexdigest(), flush=True)
module = load_template_module(verify_hash=False)
t0 = time.time(); template, vehicle = build_vehicle(geom, module=module); print("vehicle %.1fs" % (time.time()-t0), flush=True)
print("Sref %.4f cref %.4f bref %.4f" % (vehicle.reference_area, vehicle.reference_chord, vehicle.reference_span), flush=True)
for w in vehicle.wings:
    print("wing %-20s span %.3f area %.3f AR %.4f sweep_qc %.4f vert %s" % (
        w.tag, w.spans.projected, w.areas.reference, w.aspect_ratio, math.degrees(w.sweeps.quarter_chord), w.vertical), flush=True)

aer = Vortex_Lattice_Method(); aer.settings.use_surrogate = False; aer.vehicle = vehicle; aer.initialize(vehicle)
def cond(mach, adeg, v=600.0):
    c = Data()
    c.freestream.mach_number = np.array([[mach]]); c.freestream.velocity = np.array([[v]])
    c.aerodynamics.angles.alpha = np.array([[math.radians(adeg)]]); c.aerodynamics.angles.beta = np.array([[0.0]])
    c.static_stability.pitch_rate = np.array([[0.0]]); c.static_stability.roll_rate = np.array([[0.0]]); c.static_stability.yaw_rate = np.array([[0.0]])
    return c
for (nsw, ncw) in [(8,4),(15,8),(30,15),(45,25)]:
    aer.settings.number_of_spanwise_vortices = nsw; aer.settings.number_of_chordwise_vortices = ncw
    t0 = time.time(); res = VLM(cond(2.02, 5.18132), aer.settings, vehicle)
    CL = float(res.CL[0][0]); CDi = float(res.CDrag_induced[0][0])
    print("lattice %2dx%-2d CL=%.6f CDi=%.6f CL/CDi=%.2f %.1fs" % (nsw, ncw, CL, CDi, CL/CDi, time.time()-t0), flush=True)
