
# -*- coding: utf-8 -*-
"""V1: RCAIDE supersonic VLM on the 12D model — tests A (lattice convergence), B (Mach sweep),
C (O0 improvement robustness), D (cross-check against VSPAERO). No physical solver starts."""
import os, sys, json, math, time, hashlib, traceback
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
OUT = r"D:/RCAIDE/.real_runs/DRECOVER001-V1-20261125-01"
os.chdir(REPO); sys.path.insert(0, REPO)
import numpy as np
from research.concorde_metaopt.config_io import load_config
from research.concorde_metaopt.aircraft.design_space import design_space_from_config
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle, load_template_module, resolve_tutorial_path
from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
from RCAIDE.Library.Methods.Aerodynamics.Vortex_Lattice_Method.VLM import VLM
from RCAIDE.Framework.Mission.Common.Results import Results
from RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976 import US_Standard_1976
from RCAIDE.Library.Methods.Geometry.Planform.wing_planform import wing_planform
import RCAIDE

SREF, CREF, BREF = 358.25, 18.489893, 25.604638
ALT = 18288.0
Q_O0 = 20483.94          # task q at M=2.02, 18.288 km
CL_TARGET = 0.181743998494
ALPHA0 = 5.18132
VSP_CDI = 0.016548
VSP_CL = 0.18174
M_O0 = 2.02

res = {"schema": "dreal005.v1_rcaide_vlm.v1",
       "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
       "purpose": "RCAIDE native supersonic VLM (use_surrogate=False) on the frozen 12D model: A lattice convergence, B Mach sweep, C O0 improvement robustness, D cross-check vs VSPAERO",
       "physics_scope": "VLM_INVISCID_LINEAR_THEORY_ONLY",
       "physical_solver_starts": 0,
       "reference": {"SREF_m2": SREF, "CREF_m": CREF, "BREF_m": BREF, "altitude_m": ALT, "q_Pa": Q_O0,
                     "CL_target": CL_TARGET, "alpha0_deg": ALPHA0, "mach": M_O0},
       "vspaero_reference": {"CL": VSP_CL, "CDi": VSP_CDI, "Di_N": 121437.61102443402,
                             "Di_optimized_N": 121146.85696341874, "delta_Di_N": 290.754},
       "tests": {}}

ATM = US_Standard_1976()
at = ATM.compute_values(ALT)
def f(x):
    a = np.ravel(np.asarray(x, dtype=float)); return float(a[0])
T, P, RHO, A_SND = f(at.temperature), f(at.pressure), f(at.density), f(at.speed_of_sound)
print("atmo alt=%.0f T=%.2f P=%.2f rho=%.5f a=%.2f" % (ALT, T, P, RHO, A_SND), flush=True)

CONFIG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
data = load_config(CONFIG); data["frozen"] = False
space = design_space_from_config(data, source="V1-side-study")
module = load_template_module(verify_hash=False)

def build(x12):
    full = space.expand(dict(x12))
    geom = build_geometry(tuple(full), tuple(full.values()))
    t, veh = build_vehicle(geom, module=module)
    for w in veh.wings:
        try: wing_planform(w)
        except Exception as e: print("wing_planform failed on", w.tag, type(e).__name__, e, flush=True)
    veh.reference_area = SREF; veh.reference_chord = CREF; veh.reference_span = BREF
    return veh

BASE_X = dict(zip(space.names, [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]))
OPT_X  = dict(BASE_X); OPT_X["sweep_1"] = 66.92203997956408; OPT_X["sweep_2"] = 48.00055732910467

veh_b = build(BASE_X); veh_o = build(OPT_X)
for tag, v in (("baseline", veh_b), ("optimized", veh_o)):
    w = v.wings["main_wing"]
    print("%s Sref=%.4f bref=%.4f cref=%.4f span=%.4f sweep_qc=%.4f" % (
        tag, v.reference_area, v.reference_span, v.reference_chord, w.spans.projected, math.degrees(w.sweeps.quarter_chord)), flush=True)

def analysis(vehicle):
    a = Vortex_Lattice_Method(); a.settings.use_surrogate = False; a.vehicle = vehicle; a.initialize(vehicle)
    return a

def cond(a, mach, adeg, v):
    from RCAIDE.Framework.Core import Data
    st = Data(); st.conditions = Results(); st.analyses = Data()
    c = st.conditions
    V = mach * A_SND
    c.freestream.altitude = np.array([[ALT]])
    c.freestream.mach_number = np.array([[mach]])
    c.freestream.velocity = np.array([[V]])
    c.freestream.temperature = np.array([[T]])
    c.freestream.pressure = np.array([[P]])
    c.freestream.density = np.array([[RHO]])
    c.freestream.speed_of_sound = np.array([[A_SND]])
    c.freestream.dynamic_pressure = np.array([[0.5*RHO*V*V]])
    c.freestream.gravity = np.array([[9.81]])
    c.aerodynamics.angles.alpha = np.array([[math.radians(adeg)]])
    c.aerodynamics.angles.beta = np.array([[0.0]])
    c.aerodynamics.angles.bank = np.array([[0.0]])
    return st

def vlm(vehicle, a, mach, adeg):
    out = VLM(cond(a, mach, adeg, vehicle).conditions, a.settings, vehicle)
    return float(out.CLift[0][0]), float(out.CDrag_induced[0][0])

def full(vehicle, a, mach, adeg):
    st = cond(a, mach, adeg, vehicle); c = st.conditions
    V = mach * A_SND
    c.freestream.kinematic_viscosity = np.array([[f(at.kinematic_viscosity)]])
    c.freestream.dynamic_viscosity = np.array([[f(at.dynamic_viscosity)]])
    c.freestream.reynolds_number = np.array([[RHO*V*CREF/f(at.dynamic_viscosity)]])
    a.evaluate(st, vehicle)
    out = {}
    for key, path in (("CL","aerodynamics.coefficients.lift.inviscid.total"),
                      ("CDi_trefftz","aerodynamics.coefficients.drag.induced.inviscid"),
                      ("CDi_total","aerodynamics.coefficients.drag.induced.total"),
                      ("CD_compress","aerodynamics.coefficients.drag.compressibility"),
                      ("CD_parasite","aerodynamics.coefficients.drag.parasite"),
                      ("CD_total","aerodynamics.coefficients.drag.total")):
        try:
            obj = c
            for p in path.split("."): obj = getattr(obj, p)
            out[key] = float(np.ravel(obj)[0])
        except Exception as e:
            out[key] = "ERR:%s:%s" % (type(e).__name__, e)
    return out

def lattice(vehicle, nsw, ncw):
    a = analysis(vehicle); a.settings.number_of_spanwise_vortices = nsw; a.settings.number_of_chordwise_vortices = ncw
    return a

# ---------------- A: lattice convergence (baseline, M=2.02, alpha0)
A = []
for (nsw, ncw) in [(6,3),(8,4),(12,6),(15,8),(20,10),(30,15),(45,25)]:
    a = lattice(veh_b, nsw, ncw)
    t0 = time.time(); CL, CDi = vlm(veh_b, a, M_O0, ALPHA0)
    A.append({"n_span": nsw, "n_chord": ncw, "n_panels": nsw*ncw, "CL": CL, "CDi": CDi, "L_over_D": CL/CDi, "secs": round(time.time()-t0,2)})
    print("A %2dx%-2d CL=%.6f CDi=%.6f L/D=%.2f" % (nsw, ncw, CL, CDi, CL/CDi), flush=True)
res["tests"]["A_lattice"] = A

# ---------------- B: Mach sweep (baseline, lattice 20x10, alpha0 +-1 deg for slope)
B = []
a = lattice(veh_b, 20, 10)
for M in [1.6, 1.8, 2.0, 2.2, 2.4]:
    CL, CDi = vlm(veh_b, a, M, ALPHA0)
    CLp, _ = vlm(veh_b, a, M, ALPHA0+1.0)
    CLm, _ = vlm(veh_b, a, M, ALPHA0-1.0)
    slope = (CLp-CLm)/math.radians(2.0)
    beta = math.sqrt(M*M-1.0) if M > 1 else float("nan")
    B.append({"mach": M, "CL": CL, "CDi": CDi, "CL_alpha_per_rad": slope, "theory_4_over_beta": 4.0/beta,
              "ratio": slope/(4.0/beta), "CDi_over_CL2": CDi/(CL*CL)})
    print("B M=%.2f CL=%.6f CDi=%.6f CLalpha=%.4f 4/beta=%.4f ratio=%.4f" % (M, CL, CDi, slope, 4.0/beta, slope/(4.0/beta)), flush=True)
res["tests"]["B_mach"] = B

# ---------------- C: matched-CL Di for baseline vs optimized at two lattices
def solve_alpha(vehicle, a, mach, cl_target, a0=ALPHA0):
    x0, x1 = a0, a0 + 1.0
    f0 = vlm(vehicle, a, mach, x0)[0] - cl_target
    f1 = vlm(vehicle, a, mach, x1)[0] - cl_target
    for _ in range(8):
        if abs(f1) < 1e-7: break
        x2 = x1 - f1*(x1-x0)/(f1-f0); x0, f0, x1 = x1, f1, x2
        f1 = vlm(vehicle, a, mach, x1)[0] - cl_target
    CL, CDi = vlm(vehicle, a, mach, x1)
    return x1, CL, CDi
C = []
for (nsw, ncw) in [(15,8),(30,15),(45,25)]:
    ab, ao = lattice(veh_b, nsw, ncw), lattice(veh_o, nsw, ncw)
    ab_same, CL_b, CDi_b = solve_alpha(veh_b, ab, M_O0, CL_TARGET)
    ao_same, CL_o, CDi_o = solve_alpha(veh_o, ao, M_O0, CL_TARGET)
    Di_b, Di_o = CDi_b*Q_O0*SREF, CDi_o*Q_O0*SREF
    C.append({"n_span": nsw, "n_chord": ncw, "alpha_baseline_deg": ab_same, "alpha_optimized_deg": ao_same,
              "CL_baseline": CL_b, "CL_optimized": CL_o, "CDi_baseline": CDi_b, "CDi_optimized": CDi_o,
              "Di_baseline_N": Di_b, "Di_optimized_N": Di_o, "delta_Di_N": Di_b-Di_o,
              "delta_Di_pct": 100.0*(Di_b-Di_o)/Di_b})
    print("C %2dx%-2d dDi=%.3f N (%.3f%%) alphaB=%.4f alphaO=%.4f" % (nsw, ncw, Di_b-Di_o, 100*(Di_b-Di_o)/Di_b, ab_same, ao_same), flush=True)
res["tests"]["C_robustness"] = C

# ---------------- D: cross-check with VSPAERO + full drag ledger
D = {"vspero": {"CL": VSP_CL, "CDi": VSP_CDI, "alpha_deg": ALPHA0}}
a = lattice(veh_b, 30, 15)
CL, CDi = vlm(veh_b, a, M_O0, ALPHA0)
D["vlm_direct"] = {"CL": CL, "CDi_trefftz": CDi, "CL_over_CDi": CL/CDi,
                   "CDi_ratio_vlm_over_vspaero": CDi/VSP_CDI,
                   "CL_ratio_vlm_over_vspaero": CL/VSP_CL}
print("D vlm CL=%.6f CDi=%.6f ratio_CDi=%.3f" % (CL, CDi, CDi/VSP_CDI), flush=True)
try:
    fullres = full(veh_b, a, M_O0, ALPHA0)
    D["full_pipeline"] = fullres
    print("D full", fullres, flush=True)
except Exception:
    D["full_pipeline"] = {"error": traceback.format_exc()[-800:]}
    print("D full FAILED", flush=True)
res["tests"]["D_crosscheck"] = D

with open(os.path.join(OUT, "v1_rcaide_vlm_results.json"), "w") as fh:
    json.dump(res, fh, indent=2)
print("WROTE", os.path.join(OUT, "v1_rcaide_vlm_results.json"), flush=True)