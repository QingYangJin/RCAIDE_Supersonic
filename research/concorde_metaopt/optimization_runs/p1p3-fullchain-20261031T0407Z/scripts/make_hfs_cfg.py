"""Write SU2 Euler configs for the isolated-wing HF cases HFS-01/02/03."""
import json
from pathlib import Path

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
WING = EXT / "hf" / "wing"
CASES = {
    "HFS-01": "wing_coarse",
    "HFS-02": "wing_medium",
    "HFS-03": "wing_fine",
}
MACH = 2.02
AOA = 2.8398297488947493
P_INF = 7171.544888256813
T_INF = 216.65
SREF = 358.25
CREF = 18.489893
XAC = 16.821978259514246

TEMPLATE = """SOLVER= EULER
MATH_PROBLEM= DIRECT
RESTART_SOL= NO
MACH_NUMBER= {mach}
AOA= {aoa}
SIDESLIP_ANGLE= 0.0
FREESTREAM_PRESSURE= {p_inf}
FREESTREAM_TEMPERATURE= {t_inf}
REF_DIMENSIONALIZATION= DIMENSIONAL
REF_AREA= {sref}
REF_LENGTH= {cref}
REF_ORIGIN_MOMENT_X= {xac}
REF_ORIGIN_MOMENT_Y= 0.0
REF_ORIGIN_MOMENT_Z= 0.0
FLUID_MODEL= STANDARD_AIR
GAMMA_VALUE= 1.4
GAS_CONSTANT= 287.058
MESH_FILENAME= {mesh}.su2
MESH_FORMAT= SU2
CONV_FILENAME= history_{case}
RESTART_FILENAME= restart_{case}
VOLUME_FILENAME= flow_{case}
SURFACE_FILENAME= surface_flow_{case}
OUTPUT_WRT_FREQ= 500
OUTPUT_FILES= (RESTART, CSV, SURFACE_CSV)
SCREEN_OUTPUT= (INNER_ITER, WALL_TIME, RMS_DENSITY, RMS_ENERGY, CL, CD, CMz)
HISTORY_OUTPUT= (ITER, RMS_RES, AERO_COEFF)
MARKER_EULER= ( wall )
MARKER_FAR= ( farfield )
MARKER_PLOTTING= ( wall )
MARKER_MONITORING= ( wall )
NUM_METHOD_GRAD= WEIGHTED_LEAST_SQUARES
CONV_NUM_METHOD_FLOW= ROE
MUSCL_FLOW= YES
SLOPE_LIMITER_FLOW= VENKATAKRISHNAN
CFL_NUMBER= 10.0
CFL_ADAPT= NO
ITER= 5000
CONV_FIELD= RMS_DENSITY
CONV_RESIDUAL_MINVAL= -8
CONV_STARTITER= 10
CONV_CAUCHY_ELEMS= 100
CONV_CAUCHY_EPS= 1E-10
MGLEVEL= 0
LINEAR_SOLVER= FGMRES
LINEAR_SOLVER_PREC= ILU
LINEAR_SOLVER_ERROR= 1E-8
LINEAR_SOLVER_ITER= 20
"""

index = {}
for case, mesh in CASES.items():
    path = WING / (case.lower().replace("-", "") + ".cfg")
    path.write_text(TEMPLATE.format(mach=MACH, aoa=AOA, p_inf=P_INF, t_inf=T_INF,
                                    sref=SREF, cref=CREF, xac=XAC, mesh=mesh, case=case))
    index[case] = {"cfg": str(path), "mesh": str(WING / (mesh + ".su2"))}
print(json.dumps(index, indent=2))
