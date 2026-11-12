"""Frozen constants for D-REAL-001 A2 (governance v2 sec 3/12.5/12.9)."""
from __future__ import annotations

DIMENSION = 12

#: Six optimization arms (base + warm-started). B line never enters these arms.
ARM_IDS = ("BO", "DE", "PSO", "ABO", "ADE", "APSO")
BASE_ARM_OF = {"BO": "BO", "DE": "DE", "PSO": "PSO", "ABO": "BO", "ADE": "DE", "APSO": "PSO"}
ADAPTIVE_ARM_IDS = ("ABO", "ADE", "APSO")

#: backend enum shared with A1 EVALUATOR_API.v0.1 (D8).
BACKEND_REAL = "REAL_VSPAERO"
BACKEND_REPLAY = "REPLAY"
BACKEND_MOCK = "MOCK"
BACKENDS = (BACKEND_REAL, BACKEND_REPLAY, BACKEND_MOCK)

#: A1 record schema (schema_version) - do not rename.
SCHEMA_VERSION = "dreal001.aero_eval.v1"

#: A1 P2a guarded evaluate callable (EVALUATOR_API v1.1, A1 commit e0838b5).
P2A_EVALUATE_SCHEMA = "dreal001.p2a_evaluate_fn.v1"
P2A_EVALUATE_ID = "a1-p2a-evaluate-fn-v1"

#: A1 record statuses (dreal001.aero_eval.v1).
RECORD_SOLVED_VALID = "SOLVED_VALID"
RECORD_SOLVER_FAILED = "SOLVER_FAILED"
RECORD_GEOMETRY_INVALID = "GEOMETRY_INVALID"
RECORD_LIFT_MATCH_FAILED = "LIFT_MATCH_FAILED"
RECORD_NOT_RUN = "NOT_RUN"
RECORD_MOCK = "MOCK"
RECORD_STATUSES = (
    RECORD_SOLVED_VALID, RECORD_SOLVER_FAILED, RECORD_GEOMETRY_INVALID,
    RECORD_LIFT_MATCH_FAILED, RECORD_NOT_RUN, RECORD_MOCK,
)

#: Optimizer-facing normalized statuses (governance v1 sec 2 wording).
STATUS_VALID = "VALID"
STATUS_INVALID = "INVALID"
STATUS_FAIL = "FAIL"
STATUS_NOT_CONVERGED = "NOT_CONVERGED"
STATUS_NOT_RUN = "NOT_RUN"
STATUS_NO_FEASIBLE = "NO_FEASIBLE"
USABLE_STATUSES = (STATUS_VALID,)

RECORD_TO_STATUS = {
    RECORD_SOLVED_VALID: STATUS_VALID,
    RECORD_MOCK: STATUS_VALID,
    RECORD_SOLVER_FAILED: STATUS_FAIL,
    RECORD_GEOMETRY_INVALID: STATUS_INVALID,
    RECORD_LIFT_MATCH_FAILED: STATUS_NOT_CONVERGED,
    RECORD_NOT_RUN: STATUS_NOT_RUN,
}

#: Lift contract (governance v2 12.9, A1 D5): L_ref = 136000 kg * g0.
G0 = 9.80665
REFERENCE_MASS_KG = 136000.0
L_REF_N = REFERENCE_MASS_KG * G0  # 1,333,704.4 N
LIFT_TOL_REL = 1e-3
#: q at Mach 2.02 / 18288 m, from A1 EVALUATOR_API v0.1 D5 (Lead/Owner pending).
Q_PA_DEFAULT = 20483.940233430174

#: Reference frame / areas (A1 D3, governance 12.9).
REFERENCE_FRAME = "WING_AC"
XCG_M = 16.821978259514246
CREF_M = 18.489893
BREF_M = 25.604638
SREF_BASELINE_M2 = 358.25

#: Fixed alpha grids (governance v2 12.5: alpha list must be pre-registered,
#: adaptive alpha search is forbidden). Primary grid plus a pre-registered
#: refine grid; at most 1 refine launch, max 2 launches per design.
ALPHA_PRIMARY_DEG = (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)
ALPHA_REFINE_DEG = (-1.0, 1.0, 3.0, 5.0, 7.0, 9.0)
MAX_REFINE_SWEEPS = 1
MAX_LAUNCHES_PER_DESIGN = 2

#: A1 EVALUATOR_API v1.0 accounting (A1 m00946/m00973): one vspaero.exe
#: launch solves the pre-registered 7-alpha grid in one process, so one launch
#: is 1 physical_solver_starts and 7 internal_solver_cases. Alpha rows are not
#: billed separately. Per design: 1 expected launch, at most 2 (pre-registered).
INTERNAL_SOLVER_CASES_PER_START = 7
STARTS_PER_DESIGN_EXPECTED = 1
MAX_STARTS_PER_DESIGN = MAX_LAUNCHES_PER_DESIGN
#: A1 record results dict keys (dict of equal-length lists, one entry per alpha).
RESULTS_KEYS = ("alpha_deg", "cltot", "cdi", "cdo", "cdtot", "cmy")

#: Batch naming / approval (governance v2 sec 3/12.2).
PHASES = ("P0", "P1", "P2", "P3", "P4", "PERF", "ENV")
ARM_IDS_RUN = ARM_IDS + ("ENV", "REPLAY")
