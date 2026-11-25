
# -*- coding: utf-8 -*-
"""Probe: can RCAIDE's VLM be driven directly at M=2.02 for the 12D design?"""
import os, sys, json, math, time
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
os.chdir(REPO); sys.path.insert(0, REPO)
import numpy as np
import RCAIDE
print("RCAIDE", getattr(RCAIDE, "__version__", "?"), flush=True)
from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
from RCAIDE.Library.Methods.Aerodynamics.Vortex_Lattice_Method.VLM import VLM
from RCAIDE.Framework.Core import Data
from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle

CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
space = load_design_space(CONFIG)
names = tuple(space.names)
base = dict(space.baseline_dict())
print("names", names, flush=True)
expanded = space.expand(base)
geom = build_geometry(tuple(expanded), tuple(expanded.values()))
t0 = time.time()
template, vehicle = build_vehicle(geom)
print("vehicle built in %.1fs" % (time.time()-t0), flush=True)
print("Sref", vehicle.reference_area, "cref", vehicle.reference_chord, "bref", vehicle.reference_span, flush=True)
for w in vehicle.wings:
    print("wing", w.tag, "span", w.spans.projected, "area", w.areas.reference, "AR", w.aspect_ratio, "sweep_le_qc", w.sweeps.quarter_chord, flush=True)

aer = Vortex_Lattice_Method()
aer.settings.use_surrogate = False
aer.vehicle = vehicle
aer.initialize(vehicle)
print("lattice", aer.settings.number_of_spanwise_vortices, aer.settings.number_of_chordwise_vortices, flush=True)

def make_conditions(mach, alpha_rad, velocity=600.0, n=1):
    c = Data()
    c.freestream.mach_number = np.array([[mach]]*n)
    c.freestream.velocity = np.array([[velocity]]*n)
    c.aerodynamics.angles.alpha = np.array([[alpha_rad]]*n)
    c.aerodynamics.angles.beta = np.array([[0.0]]*n)
    c.static_stability.pitch_rate = np.array([[0.0]]*n)
    c.static_stability.roll_rate = np.array([[0.0]]*n)
    c.static_stability.yaw_rate = np.array([[0.0]]*n)
    return c

for (nsw, ncw) in [(8,4),(15,8),(30,15)]:
    aer.settings.number_of_spanwise_vortices = nsw
    aer.settings.number_of_chordwise_vortices = ncw
    t0 = time.time()
    cond = make_conditions(2.02, math.radians(5.18132))
    res = VLM(cond, aer.settings, vehicle)
    print("lattice %dx%d  CL=%.6f  CDi=%.6f  n_cpts=%s  %.1fs" % (
        nsw, ncw, float(res.CL[0][0]), float(res.CDrag_induced[0][0]), np.shape(res.CL), time.time()-t0), flush=True)
