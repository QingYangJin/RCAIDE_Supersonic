"""D-REAL-001 A2 optimizers: lift-matched induced-drag evaluation + six arms.

Public API
----------
Records / task / design helpers:
    build_task, DRealTaskSpec, canonical_x12, design_hash

Accounting (governance v2 sec 5/6/7):
    SolverStartLedger, SolverBudgetExceeded, AccountingViolation

Evaluators (one interface, three backends):
    MockLiftMatchEvaluator      backend=MOCK        physical_solver_starts=0
    ReplayEvaluator             backend=REPLAY      historical record replay
    RealVspaeroAdapter          backend=REAL_VSPAERO guarded (approval + A1 fn)

Six arms:
    run_arm(ArmSpec(...), task, design_space, evaluator) -> ArmResult

Pilot pre-registration:
    PreregistrationConfig, write_preregistration, run_pilot
"""

from .constants import (
    ARM_IDS,
    ADAPTIVE_ARM_IDS,
    BACKEND_MOCK,
    BACKEND_REAL,
    BACKEND_REPLAY,
    DIMENSION,
    INTERNAL_SOLVER_CASES_PER_START,
    LIFT_TOL_REL,
    L_REF_N,
    MAX_STARTS_PER_DESIGN,
    P2A_EVALUATE_ID,
    P2A_EVALUATE_SCHEMA,
    Q_PA_DEFAULT,
    RESULTS_KEYS,
    SCHEMA_VERSION,
    STARTS_PER_DESIGN_EXPECTED,
    STATUS_FAIL,
    STATUS_INVALID,
    STATUS_NOT_CONVERGED,
    STATUS_NOT_RUN,
    STATUS_VALID,
)
from .task import DRealTaskSpec, build_task, isa_atmosphere, isa_q_pa
from .records import (
    AeroEvaluation,
    AlphaSample,
    LiftMatchResult,
    SolverAttempt,
    canonical_json,
    canonical_x12,
    design_hash,
    sha256_bytes,
    sha256_file,
    solver_config_hash,
)
from .design import (
    clip_x12,
    geometric_constraint_g,
    sref_from_physical,
    sref_from_x12,
    validate_x12,
)
from .ledger import AccountingViolation, SolverBudgetExceeded, SolverStartLedger
from .cache import CrossRunCacheReuse, EvaluationCache, VisibleLabelStore
from .lift_match import interpolate_lift_match
from .evaluators import (
    BaseLiftMatchEvaluator,
    EvaluationRecorder,
    MockLiftMatchEvaluator,
    RealSolverNotAuthorized,
    RealVspaeroAdapter,
    ReplayEvaluator,
)
from .real_backend import (
    A1_EVALUATOR_CLASS,
    A1_EVALUATOR_MODULE,
    A1_P2A_FACTORY,
    A1_P2A_MODULE,
    P2A_CACHE_ENABLED,
    P2A_MAX_MESH_ATTEMPTS,
    P2A_TARGET_MESH_FAMILY,
    RealBackendUnavailable,
    build_p2a_adapter,
    build_real_adapter,
    load_a1_evaluator_class,
    load_a1_p2a_factory,
    p2a_adapter_factory,
    pilot_real_adapter_factory,
)
from .arms import ArmResult, ArmSpec, WarmStartSpec, run_arm
from .pilot import (
    PreregistrationConfig,
    build_preregistration,
    run_pilot,
    write_preregistration,
)

__all__ = [
    "ARM_IDS", "ADAPTIVE_ARM_IDS", "BACKEND_MOCK", "BACKEND_REAL", "BACKEND_REPLAY",
    "DIMENSION", "LIFT_TOL_REL", "L_REF_N", "Q_PA_DEFAULT", "SCHEMA_VERSION",
    "INTERNAL_SOLVER_CASES_PER_START", "MAX_STARTS_PER_DESIGN",
    "P2A_EVALUATE_ID", "P2A_EVALUATE_SCHEMA",
    "STARTS_PER_DESIGN_EXPECTED", "RESULTS_KEYS",
    "STATUS_FAIL", "STATUS_INVALID", "STATUS_NOT_CONVERGED", "STATUS_NOT_RUN", "STATUS_VALID",
    "DRealTaskSpec", "build_task", "isa_atmosphere", "isa_q_pa",
    "AeroEvaluation", "AlphaSample", "LiftMatchResult", "SolverAttempt",
    "canonical_json", "canonical_x12", "design_hash", "sha256_bytes", "sha256_file",
    "solver_config_hash",
    "clip_x12", "geometric_constraint_g", "sref_from_physical", "sref_from_x12", "validate_x12",
    "AccountingViolation", "SolverBudgetExceeded", "SolverStartLedger",
    "EvaluationCache", "CrossRunCacheReuse", "VisibleLabelStore", "interpolate_lift_match",
    "BaseLiftMatchEvaluator", "EvaluationRecorder", "MockLiftMatchEvaluator",
    "RealSolverNotAuthorized", "RealVspaeroAdapter", "ReplayEvaluator",
    "A1_EVALUATOR_CLASS", "A1_EVALUATOR_MODULE", "RealBackendUnavailable",
    "build_real_adapter", "load_a1_evaluator_class", "pilot_real_adapter_factory",
    "A1_P2A_MODULE", "A1_P2A_FACTORY", "P2A_TARGET_MESH_FAMILY", "P2A_MAX_MESH_ATTEMPTS",
    "P2A_CACHE_ENABLED", "build_p2a_adapter", "load_a1_p2a_factory", "p2a_adapter_factory",
    "ArmResult", "ArmSpec", "WarmStartSpec", "run_arm",
    "PreregistrationConfig", "build_preregistration", "run_pilot", "write_preregistration",
]
