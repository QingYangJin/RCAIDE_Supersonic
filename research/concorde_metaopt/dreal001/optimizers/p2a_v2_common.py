"""Shared frozen constants for the P2a v2 (C+B2) package.

Everything here is a policy value, not a runtime observation.  The module is
deliberately dependency-free so the plan builder and the runtime adapters can
both import it without a cycle.
"""
from __future__ import annotations

PLAN_SCHEMA = "dreal001.p2a_v2_plan.v1"
APPROVAL_SCHEMA = "dreal001.approval.v3"
IDENTITY_SCHEMA = "dreal001.p2a_v2_identity.v1"
INITIAL_MANIFEST_SCHEMA = "dreal001.p2a_v2.initial_designs_manifest.v1"
PREFLIGHT_BUNDLE_SCHEMA = "dreal001.p2a_v2.preflight_bundle.v1"
FREEZE_API_SCHEMA = "dreal001.freeze_api.v1"
FREEZE_RECORD_SCHEMA = "dreal001.p2a_v2.freeze_record.v1"
FREEZE_API_CHAIN_SCHEMA = "dreal001.freeze_api.chain.v1"
APPEND_LOG_SCHEMA = "dreal001.p2a_v2.append_only_log.v1"
LEDGER_SCHEMA = "dreal001.p2a_v2.evaluator_event_ledger.v1"
RUNNER_VERSION = "a2-p2a-v2-runner-2026-11-11"

BATCH_ID = "DREAL001-P2-20261111-15"
RUN_ID = "DREAL001-P2A2R10-20261111-01"
STAGE = "D-NEXT-001-P2a-v2-R10"

ARMS = ("BO", "DE", "PSO", "ABO", "ADE", "APSO")
BASE_ARM_OF = {
    "BO": "BO",
    "DE": "DE",
    "PSO": "PSO",
    "ABO": "BO",
    "ADE": "DE",
    "APSO": "PSO",
}
ADAPTIVE_ARMS = ("ABO", "ADE", "APSO")
SEED = 42
DESIGN_EVALS_PER_ARM = 32
FAMILY_SLOTS = 2
FAMILY_SLOTS_LABELS = ("f1", "f2")

MAIN_PLANNED_STARTS = len(ARMS) * DESIGN_EVALS_PER_ARM * FAMILY_SLOTS  # 384
PREFLIGHT_CASES = 2
PREFLIGHT_PLANNED_STARTS = PREFLIGHT_CASES
PREFLIGHT_PLANNED_INTERNAL_CASES = PREFLIGHT_CASES * 7
PLANNED_STARTS = MAIN_PLANNED_STARTS + PREFLIGHT_PLANNED_STARTS  # 386
PLANNED_INTERNAL_CASES = PLANNED_STARTS * 7  # 2702
RESERVE_GROUPS = 32
RESERVE_STARTS = RESERVE_GROUPS * FAMILY_SLOTS  # 64
MAX_STARTS = 451
MAX_INTERNAL_CASES = 3157
MAX_REFINE_STARTS = 0
TIMEOUT_SECONDS = 60.0

# A1 FreezeAPI worst case: 20 discovery + 2 x 40 force = 100 builds/design.
# 384 main designs + 32 reserve = 416 attempted designs -> 41,600 builds is the
# hard policy bound; the approved planning cap is 8,000 and the runtime stop is
# the first of (8,000 total, 100/design, 3,600 s zero-physical wall time).
MAX_GEOMETRY_BUILDS = 8000
MAX_GEOMETRY_BUILDS_PER_DESIGN = 100
ZERO_PHYSICAL_WALL_CAP_SECONDS = 3600
DISCOVERY_TARGET_ATTEMPTS = 20
DISCOVERY_CONTINUE_ATTEMPTS = 40
FORCE_ATTEMPTS_PER_FAMILY = 40
FREEZE_API_DISCOVERY_K = 10

Q_PA = 20483.940233430174
L_REF_N = 1333704.4
LIFT_TOLERANCE_REL = 1e-3
PHYSICAL_CALL_COUNT = 0

# A1 evaluator v1.2 real-path probe evidence (A1 commit 6753eb3, zero physical).
A1_PROBE_V3_REL = "docs/receipts/dreal001/a1_task49_probe_v3_result.json"
A1_PROBE_V3_SHA256 = "9757bcf1dd573e6ae9e8686ce9862d724d1adcb2b7e1ec05175b72d6ce327a13"
A1_PROBE_V3_OVERALL = "SECURE"
A1_READINESS_STATUS = "REAL_PATH_IMPLEMENTED_PROBE_VERIFIED_PENDING_FIRST_REAL_START"

WINDOW_START_UTC = "2026-11-11T18:30:00Z"
WINDOW_END_UTC = "2026-11-12T04:00:00Z"
WINDOW_TOKEN = "WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z"

# R1/R2/R3 history: each aborted arm charged two real preflight starts / 14
# internal cases while the main batch stayed NOT_RUN.  All three are excluded
# from E1-E6 endpoints but all count toward the cumulative caps.
R1_CHARGED_STARTS = 2
R1_CHARGED_INTERNAL_CASES = 14
R1_MAIN_STARTS = 0
R2_CHARGED_STARTS = 2
R2_CHARGED_INTERNAL_CASES = 14
R2_MAIN_STARTS = 0
PRIOR_CHARGED_STARTS = 39
PRIOR_CHARGED_INTERNAL_CASES = 285
R3_CHARGED_STARTS = 2
R3_CHARGED_INTERNAL_CASES = 14
R3_MAIN_STARTS = 0
R4_CHARGED_STARTS = 2
R4_CHARGED_INTERNAL_CASES = 14
R4_MAIN_STARTS = 0
R5_CUMULATIVE_STARTS = (
    PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS + R2_CHARGED_STARTS
    + R3_CHARGED_STARTS + R4_CHARGED_STARTS + PLANNED_STARTS
)  # 433
R5_CUMULATIVE_INTERNAL_CASES = (
    PRIOR_CHARGED_INTERNAL_CASES + R1_CHARGED_INTERNAL_CASES
    + R2_CHARGED_INTERNAL_CASES + R3_CHARGED_INTERNAL_CASES
    + R4_CHARGED_INTERNAL_CASES + PLANNED_INTERNAL_CASES
)  # 3043
R5_EXCLUDES_R1_R2_R3_R4_FROM_ENDPOINTS = True

# R5: closed as SETUP_STOP_DESIGN_SPACE_IMPORT before any solver start -> 0 charged.
R5_CHARGED_STARTS = 0
R5_CHARGED_INTERNAL_CASES = 0
R5_MAIN_STARTS = 0
R6_CUMULATIVE_STARTS = (
    PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS + R2_CHARGED_STARTS
    + R3_CHARGED_STARTS + R4_CHARGED_STARTS + R5_CHARGED_STARTS + PLANNED_STARTS
)  # 433
R6_CUMULATIVE_INTERNAL_CASES = (
    PRIOR_CHARGED_INTERNAL_CASES + R1_CHARGED_INTERNAL_CASES
    + R2_CHARGED_INTERNAL_CASES + R3_CHARGED_INTERNAL_CASES
    + R4_CHARGED_INTERNAL_CASES + R5_CHARGED_INTERNAL_CASES + PLANNED_INTERNAL_CASES
)  # 3043
R6_EXCLUDES_R1_R2_R3_R4_R5_FROM_ENDPOINTS = True

# ---- R7 protocol-D identity and accounting (Lead L-09; zero physical before GO) ----
# R6 execution (S1 STOP main-stage) charged two PASS_BYTE replay preflight starts
# (14 internal cases) plus one main-pool evaluation start (7 internal cases) whose
# polar was produced but whose on_evaluation callback raised ValueError from the
# frozen executor's design_hash(canonical_x12(...)) string misuse.  R6 is excluded
# from E1-E6 endpoints but counts toward the cumulative caps.
R6_CHARGED_STARTS = 3
R6_CHARGED_INTERNAL_CASES = 21
R6_MAIN_STARTS = 1
R6_RUN_ID = "DREAL001-P2A2R6-20261111-01"
R6_APPROVAL_SHA256 = "72b95e03130fbe958c52528f1b8f484eae4872140a7336709094b9108964f98f"
R6_APPROVAL_BYTES = 67063
R6_AMENDMENT_AT_UTC = "2026-11-11T10:50:50Z"

R7_MAIN_PLANNED_STARTS = MAIN_PLANNED_STARTS
DIAGNOSTIC_CASES = (
    ("DIAG-01", "eb00b7ad545243e6", 16),
    ("DIAG-02", "dc96d2438a6dddc3", 17),
)
DIAGNOSTIC_PLANNED_STARTS = 2
DIAGNOSTIC_PLANNED_INTERNAL_CASES = 14
R7_PLANNED_STARTS = PREFLIGHT_PLANNED_STARTS + DIAGNOSTIC_PLANNED_STARTS + R7_MAIN_PLANNED_STARTS  # 388
# PLANNED_INTERNAL_CASES already includes the two preflight internal cases (384*7 + 14 = 2,702);
# R7 adds two diagnostic starts x 7 internal cases, so 2,702 + 14 = 2,716.
R7_PLANNED_INTERNAL_CASES = (
    PLANNED_INTERNAL_CASES + DIAGNOSTIC_PLANNED_INTERNAL_CASES
)  # 2,716
R7_CUMULATIVE_STARTS = (
    PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS + R2_CHARGED_STARTS + R3_CHARGED_STARTS
    + R4_CHARGED_STARTS + R5_CHARGED_STARTS + R6_CHARGED_STARTS + R7_PLANNED_STARTS
)  # 438
R7_CUMULATIVE_INTERNAL_CASES = (
    PRIOR_CHARGED_INTERNAL_CASES + R1_CHARGED_INTERNAL_CASES + R2_CHARGED_INTERNAL_CASES
    + R3_CHARGED_INTERNAL_CASES + R4_CHARGED_INTERNAL_CASES + R5_CHARGED_INTERNAL_CASES
    + R6_CHARGED_INTERNAL_CASES + R7_PLANNED_INTERNAL_CASES
)  # 3078
R7_EXCLUDES_R1_R2_R3_R4_R5_R6_FROM_ENDPOINTS = True

# R7 invalid-numerical tolerance (protocol D) and pre-registered scientific auto-stop rules.
INVALID_EVALUATION_STATUS = "INVALID_NUMERICAL"
INVALID_RATIO_MIN_EVALS = 48
INVALID_RATIO_MAX = 0.25
INVALID_CONSECUTIVE_MAX = 6
INVALID_TOTAL_MAX = 64

R7_AMENDMENT_SEQ = 7
R7_AMENDMENT_ACTION = "R7_OBSERVE_AND_INVALID_TOLERANCE_FIX"
R7_AMENDMENT_REASON = (
    "R6 is preserved read-only and excluded from endpoints. It charged 3 starts / 21 "
    "internal cases: two PASS_BYTE replay preflight starts plus one main-pool evaluation "
    "start whose polar was produced but whose on_evaluation callback raised ValueError from "
    "the frozen executor's design_hash(canonical_x12(...)) string misuse. R7 is a minimal "
    "A2 execution-layer and reporting fix only: (a) observe() design_hash argument misuse "
    "corrected; (b) per-evaluation invalid-numerical tolerance with pre-registered "
    "scientific auto-stop rules, so an individual invalid evaluation no longer aborts the "
    "batch; (c) DE/PSO population padding to remove the latent proposal crash; (d) "
    "arm-failure evidence now persists a minimal preflight_result.json and "
    "batch_summary.json. R7 also inserts a pre-registered two-case diagnostic phase "
    "(designs 16 and 17, 1 start / 7 internal cases each) before the 384-start main "
    "batch. No A1 frozen bytes, no executor scientific policy and no plan scientific "
    "fields are changed. Cumulative accounting after R7 is 438 starts / 3,078 internal "
    "cases against caps 451 / 3,157, and R1-R6 are excluded from E1-E6 endpoints. The R6 "
    "NaN mechanism is not proven; candidate mechanisms remain H1 face/cut topology "
    "singularity, H2 frozen geometry plus numerics incompatibility, H3 family/wake "
    "initialisation."
)

# Signed approvals that the R3 approval must explicitly supersede (bytes are read-only history).
R1_RUN_ID = "DREAL001-P2A2R-20261111-01"
R1_APPROVAL_SHA256 = "9e5c29b0ac482f36dc0d9bbe694a94afb7a3cf4a8557b549919dbe180cfe9b9b"
R1_APPROVAL_BYTES = 38476
R2_RUN_ID = "DREAL001-P2A2R2-20261111-01"
R2_APPROVAL_SHA256 = "eee7868a4ea3892a5df1a8d51595e1b8dee78c34996d5fd9ccf2293363e2808f"
R2_APPROVAL_BYTES = 47081
R2_DRY_RUN_FILENAME = "post_approval_dry_run.R2_20261111T073426Z.json"
R2_DRY_RUN_SHA256 = "0f619fb79bcfd43eb01016dd2b6343dd1f1e5c3fe435f2b434a62f0dd693c983"
R2_DRY_RUN_BYTES = 13014
R2_AMENDMENT_SEQ = 2
R2_AMENDMENT_ACTION = "R2_MINIMAL_EXEC_FIX"
R2_AMENDMENT_AT_UTC = "2026-11-11T07:05:56Z"
R2_AMENDMENT_REASON = (
    "R1 preflight 2/2 SOLVER_FAILED because A2 spawned basename concorde_baseline "
    "without concorde_baseline.vspgeom/.vkey (A1 materialises model.*); main batch "
    "NOT_RUN. R2 is limited to three execution-layer fixes; R1 charged 2 starts/14 "
    "internal cases count toward cumulative caps but R1 is excluded from E1-E6 endpoints."
)
R3_AMENDMENT_SEQ = 3
R3_AMENDMENT_ACTION = "R3_SOLVED_STATUS_FIX"
R3_AMENDMENT_AT_UTC = "2026-11-11T08:28:49Z"
R3_AMENDMENT_REASON = (
    "R2 preflight reached PASS_BYTE cartesian polars for both cases (2 starts/14 "
    "internal, main batch NOT_RUN) but the A2 preflight verifier required the literal "
    "status 'SOLVED_VALID' while the A2 real spawn returned 'SOLVED'; R3 is limited to "
    "that status-vocabulary fix in the A2 execution layer plus package identity/budget "
    "reseating. R1 and R2 are both excluded from E1-E6 endpoints; their charged counts "
    "(2+2 starts, 14+14 internal) count toward the cumulative caps (429 starts / 3,015 "
    "internal cases for R3, caps 451/3,157)."
)

# R3 signed approval: R4 must explicitly supersede it (bytes are read-only history).
R3_RUN_ID = "DREAL001-P2A2R3-20261111-01"
R3_APPROVAL_SHA256 = "18865f8f4e8206135f1673e5f8706bd201465bc617473c604b262ba440dd7f60"
R3_APPROVAL_BYTES = 52695
R4_AMENDMENT_AT_UTC = "2026-11-11T09:16:49Z"
R4_AMENDMENT_SEQ = 4
R4_AMENDMENT_ACTION = "R4_TEMP_ROOT_ISOLATION_FIX"
R4_AMENDMENT_REASON = (
    "R3 arm aborted before its main batch (charged 2 preflight starts / 14 internal "
    "cases, main batch NOT_RUN) because the frozen A1 FreshProcessBuilder hit a "
    "PermissionError writing task.json under a tempfile.mkdtemp 0o700 root created in "
    "this DSH session, and its child geometry worker also lacked the A1 repo root on "
    "PYTHONPATH and the openvsp_root task key. R4 is limited to a launcher-level "
    "env/compat shim (TMP/TEMP isolation + ACL-safe mkdtemp using default os.mkdir mode "
    "+ PYTHONPATH + openvsp_root) applied in the launcher process and injected into the "
    "A1 geometry worker via sitecustomize; no A1, executor or plan bytes change. "
    "R1/R2/R3 are all excluded from E1-E6 endpoints; their charged counts (2+2+2 "
    "starts, 14+14+14 internal) count toward cumulative caps (431 starts / 3,029 "
    "internal cases for R4, caps 451/3,157)."
)

# R4 signed approval: R5 must explicitly supersede it (bytes are read-only history).
R4_RUN_ID = "DREAL001-P2A2R4-20261111-01"
R4_APPROVAL_SHA256 = "6e2aebcf7b5cbced471d0dfc6d7200d761e990660ac6f384517940600a2063ab"
R4_APPROVAL_BYTES = 59125
R4_DRY_RUN_FILENAME = "post_approval_dry_run.R4_20261111T094853Z.json"
R4_DRY_RUN_SHA256 = "02b6023908a98dddeafc7299a2060e3f4a7cc1b25e0f40c1d9ed14a78c896429"
R4_DRY_RUN_BYTES = 13529

R5_AMENDMENT_SEQ = 5

# R5 signed approval: R6 must explicitly supersede it (bytes are read-only history).
R5_RUN_ID = "DREAL001-P2A2R5-20261111-01"
R5_APPROVAL_SHA256 = "ca0bdc7b34bc29dc0a9e8a2157da28069be5279ca4a59d3ad5194e9646b528bf"
R5_APPROVAL_BYTES = 63264
R5_AMENDMENT_AT_UTC = "2026-11-11T10:16:35Z"
R6_AMENDMENT_SEQ = 6
R6_AMENDMENT_ACTION = "R6_DESIGN_SPACE_BINDING_FIX"
R6_AMENDMENT_REASON = (
    "R5 was closed as SETUP_STOP_DESIGN_SPACE_IMPORT before any solver start (0 "
    "physical starts / 0 internal cases, main batch NOT_RUN): the A2 executor imported "
    "design_space through the already-bound A2 research package, so the A2 copy "
    "shadowed the A1 frozen module (8f9b893c.../33660B) and its P1 frozen-guard rejected "
    "the A1 frozen config before x12 conversion or any solver start. R6 is limited to a "
    "launcher-level importlib preload that binds the A1 frozen design_space.py and config "
    "bytes before the executor import (sys.modules registration + parent package "
    "setattr), with the absolute path and both SHAs recomputed before registration; no "
    "A1 bytes, no executor bytes and no plan science fields change. R1/R2/R3/R4 remain "
    "excluded from E1-E6 endpoints with charged 2+2+2+2 starts / 14+14+14+14 internal "
    "cases; their charged counts plus R5's 0 count toward the cumulative caps (433 "
    "starts / 3,043 internal cases for R6, caps 451/3,157)."
)
R5_AMENDMENT_ACTION = "R5_X12_DOMAIN_FIX"
R5_AMENDMENT_REASON = (
    "R4 preflight reached PASS_BYTE polar bytes for both cases (2 starts/14 internal, "
    "main batch NOT_RUN) but the first BO arm evaluation aborted with the A1 "
    "V12ConfigurationError UNIT_BOX_VECTOR_NOT_ACCEPTED: the A2 executor seeded the "
    "proposal engine by np.clip()ing physical x12 and returned ProposalEngine unit "
    "vectors as physical x12, so the A1 unit-box guard rejected the design before any "
    "main solver start. R5 is limited to the A2 execution-layer x12 unit<->physical "
    "boundary fix using the A1 frozen design space (config 8b29d1e3... / design_space.py "
    "8f9b893c...), with fail-closed bounds checks; no A1 bytes, no executor solver policy "
    "and no plan science fields change. R1/R2/R3/R4 are all excluded from E1-E6 "
    "endpoints; their charged counts (2+2+2+2 starts, 14+14+14+14 internal) count toward "
    "cumulative caps (433 starts / 3,043 internal cases for R5, caps 451/3,157)."
)

# R5: A1 frozen 12D design space used only for unit<->physical conversion at the
# A2 execution boundary (A1 bytes unchanged; these SHAs are pinned in plan/identity).
A1_DESIGN_SPACE_CONFIG_REL = "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
A1_DESIGN_SPACE_CONFIG_SHA256 = "8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e"
A1_DESIGN_SPACE_CONFIG_BYTES = 10846
A1_DESIGN_SPACE_PY_REL = "research/concorde_metaopt/aircraft/design_space.py"
A1_DESIGN_SPACE_PY_SHA256 = "8f9b893c13195c80ff1ee88598134e3f44fef0495452249780d114c9e0593b89"
A1_DESIGN_SPACE_PY_BYTES = 33660
DESIGN_SPACE_VARIABLE_IDS = (
    "wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3",
    "span_location_2", "span_location_3", "chord_ratio_2", "chord_ratio_3",
    "tip_twist", "vertical_tail_area", "vertical_tail_sweep_delta",
)

# R1: the real solver executable is bound by plan/approval solver_contract,
# never discovered by OPENVSP_ROOT scanning.
VSPAERO_EXE_PATH = r"D:\OpenVSP-3.55.0\OpenVSP-3.55.0-win64\vspaero.exe"
VSPAERO_EXE_SHA256 = "db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad"
VSPAERO_EXE_BYTES = 811520


PREFLIGHT_ACCEPT_NUMERIC_RTOL = 1e-9
PREFLIGHT_CASES_DEFAULT = (
    {
        "case_id": "PRE-01",
        "design_index": 0,
        "design_hash": "8bd5a6c7c8311938",
        "family_label": "543x472",
        "mesh_family": (543, 472),
        "expected_polar_sha256": "455082e2ac8029216a811c89aaa20b34fd9d73faa319eed23da5348e3de4bc87",
        "expected_vspgeom_sha256": "40fdd4364e01c7fe11ca2ea4530d39c371ae693a434f39e44986f7512d6446f4",
        "expected_vkey_sha256": "768e470e3d7a4a24a4af7814d658f58a2b9cdc77f38101a7493678f3a4f1cbf0",
        "expected_vspaero_sha256": "3c70d11ae6af74e6fd1cf9b787c71571768bc398a07b1343df9a1340cf93b837",
        "expected_csf_sha256": "bb29bf526f4379308ca9c271a8df90c39f4df4235f81f63e370f25e714bb797c",
        "source_note": "P1R P1-00a historical solver inputs + frozen family_pair 543x472",
    },
    {
        "case_id": "PRE-02",
        "design_index": 5,
        "design_hash": "bc52a54ecefaac4c",
        "family_label": "483x418",
        "mesh_family": (483, 418),
        "expected_polar_sha256": "0287afe0d7e5a91bc286c0b6cbd1ca5623d8aafe65110862fe263925129dd33f",
        "expected_vspgeom_sha256": "192036cffb9941a64561953f5d5a6e6ee1af5ff8e385ef077b0c30374e7b3cae",
        "expected_vkey_sha256": "887dfa1f2f63dbc1978f397ed78c0f6feab5c5fb0eb84f245d6d498833e6f6c3",
        "expected_vspaero_sha256": "39bce6c03514e3ba7083e472a91000ee7ec318c7b2a47410a23cdc95ff348780",
        "expected_csf_sha256": "bb29bf526f4379308ca9c271a8df90c39f4df4235f81f63e370f25e714bb797c",
        "source_note": "P1C W01-plus historical solver inputs + frozen family_pair 483x418",
    },
)

INITIAL_DESIGN_INDICES = (15, 16, 17)
INITIAL_DESIGN_HASHES = (
    "d51866f7d3c49303",
    "eb00b7ad545243e6",
    "dc96d2438a6dddc3",
)
INITIAL_DESIGNS_NOTE = (
    "manifest group=LHS, design_index ascending 15/16/17; x12 copied from the "
    "manifest record bytes; not in the 15 P1C/P1R A-arm historical labels"
)

FROZEN_VSPGEOM = ".vspgeom"
FROZEN_VKEY = ".vkey"
FROZEN_PAIR_MANIFEST_SHA256 = (
    "55e63f392e2821fff02e6f849a3090b9f9c7263be0b9f6c8debbcea599ab1892"
)
A1_PAIR_MANIFEST_PATH = (
    "D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/"
    "dreal001/geometry/runs/P2A_FAM_FEASIBILITY_20261111/family_pair_manifest.json"
)
A1_PREFLIGHT_BUNDLE_PATH = (
    "D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/"
    "dreal001/geometry/replay_bundles/P2A_V2_PREFLIGHT_20261111_R1/bundle_manifest.json"
)
APPEND_ONLY_LOG_PATH = "runtime/family_pair_manifest.append_only.jsonl"
A1_PREFLIGHT_BUNDLE_SHA256 = (
    "995bb12fff738d3ebb0bde08c0d5c5bfeb9532aeb536847ef307a2332013aa5"
)
DRY_RUN_FILENAME = "dry_run.json"

DISCLOSURE_FAMILY_PAIRS = (
    "A1 P2AFAM manifest: 119 designs; 104 distinct per-design family pairs; "
    "the (483x418)+(543x472) pair appears on design_index [0,2,5,8,9,11,13,14] only; "
    "W01-plus (design_index 5, design_hash bc52a54ecefaac4c) is 483x418+543x472; "
    "a fixed global pair is forbidden."
)


# ---- R8 prefrozen-reuse identity and accounting (Lead L-10; zero physical before GO) ----
# R7 execution (S1 STOP main-stage) charged two PASS_BYTE replay preflight starts
# (14 internal cases) plus the two-case diagnostic phase that actually evaluated both
# families per design: 4 starts / 28 internal cases (the R7 prereg had written 2/14;
# that implementation/preregistration deviation is disclosed in the R8 package).
# R7 is excluded from E1-E6 endpoints but counts toward the cumulative caps.
R7_CHARGED_STARTS = 6
R7_CHARGED_INTERNAL_CASES = 42
R7_MAIN_STARTS = 0
R7_RUN_ID = "DREAL001-P2A2R7-20261111-01"
R7_APPROVAL_SHA256 = "1a552267ab0070ee4f690815ed1de1db6d5976c1ada8356421f017bb84d72e37"
R7_APPROVAL_BYTES = 69405
R7_AMENDMENT_AT_UTC = "2026-11-11T15:17:45Z"
# R7 cumulative recorded by the signed R7 package: prior 50/362 + 388/2716 = 438/3078.
R7_CUMULATIVE_STARTS_RECORDED = 438
R7_CUMULATIVE_INTERNAL_CASES_RECORDED = 3078

# R8 diagnostic phase retains full pair evaluation semantics (2 families per design),
# so each of the two pre-registered diagnostic designs costs 2 starts / 14 internal cases.
DIAGNOSTIC_STARTS_PER_CASE = 2
DIAGNOSTIC_INTERNAL_CASES_PER_CASE = 14
DIAGNOSTIC_PLANNED_STARTS = len(DIAGNOSTIC_CASES) * DIAGNOSTIC_STARTS_PER_CASE  # 4
DIAGNOSTIC_PLANNED_INTERNAL_CASES = len(DIAGNOSTIC_CASES) * DIAGNOSTIC_INTERNAL_CASES_PER_CASE  # 28
R8_MAIN_PLANNED_STARTS = MAIN_PLANNED_STARTS
R8_PLANNED_STARTS = PREFLIGHT_PLANNED_STARTS + DIAGNOSTIC_PLANNED_STARTS + R8_MAIN_PLANNED_STARTS  # 390
R8_PLANNED_INTERNAL_CASES = (
    PREFLIGHT_PLANNED_INTERNAL_CASES + DIAGNOSTIC_PLANNED_INTERNAL_CASES
    + R8_MAIN_PLANNED_STARTS * 7
)  # 2730
R8_CUMULATIVE_STARTS = (
    PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS + R2_CHARGED_STARTS + R3_CHARGED_STARTS
    + R4_CHARGED_STARTS + R5_CHARGED_STARTS + R6_CHARGED_STARTS + R7_CHARGED_STARTS
    + R8_PLANNED_STARTS
)  # 446
R8_CUMULATIVE_INTERNAL_CASES = (
    PRIOR_CHARGED_INTERNAL_CASES + R1_CHARGED_INTERNAL_CASES + R2_CHARGED_INTERNAL_CASES
    + R3_CHARGED_INTERNAL_CASES + R4_CHARGED_INTERNAL_CASES + R5_CHARGED_INTERNAL_CASES
    + R6_CHARGED_INTERNAL_CASES + R7_CHARGED_INTERNAL_CASES + R8_PLANNED_INTERNAL_CASES
)  # 3134
R8_EXCLUDES_R1_R2_R3_R4_R5_R6_R7_FROM_ENDPOINTS = True
STATIC_INDEX_COUNT_EXPECTED = 119
PREFROZEN_SOURCE_KIND = "PREFROZEN_MANIFEST_REUSE"
ACCOUNTING_INCONSISTENT = "ACCOUNTING_INCONSISTENT"

R8_AMENDMENT_SEQ = 8
R8_AMENDMENT_ACTION = "R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX"
R8_AMENDMENT_REASON = (
    "R7 is preserved read-only and excluded from endpoints. It charged 6 starts / 42 internal "
    "cases: two PASS_BYTE replay preflight starts plus two diagnostic designs evaluated over "
    "their full family pair (4 starts / 28 internal; the R7 prereg said 2/14 and that deviation "
    "is disclosed). The R7 main batch stopped after one design at FROZEN_BYTES_SHA_MISMATCH before "
    "any solver spawn: the executor rebuilt design15 f2 as 27325306... while the A1 static index and "
    "the initial manifest hold the pre-frozen be8454bf..., so the A1 evaluator static-vs-runtime guard "
    "refused the design. R8 is a minimal A2 execution/reporting fix: (a) initial designs 15/16/17 reuse "
    "the pre-frozen manifest family bytes (frozen_vspgeom_path plus sibling model.vkey/model.vsp3), "
    "verify SHA/canonical fail-closed and append a PREFROZEN_MANIFEST_REUSE record instead of calling "
    "FreezeBuilder; (b) non-initial designs keep the FreezeBuilder path and a static-index hit without "
    "prefrozen reuse is recorded unusable (fail-closed, no silent rebuild); (c) internal-case accounting "
    "no longer defaults to 7 when starts==0, batch_summary splits preflight/diagnostic/main internal "
    "cases, and charged+planned above caps is ACCOUNTING_INCONSISTENT; (d) the diagnostic phase is "
    "pre-registered as 4 starts / 28 internal with polar SHA extraction. No A1 bytes, no plan scientific "
    "policy and no scientific endpoint changes."
)


# ---- R9 prefrozen flat-row identity and accounting (Lead R9 ruling; zero physical before GO) ----
R8_CHARGED_STARTS = 0
R8_CHARGED_INTERNAL_CASES = 0
R8_MAIN_STARTS = 0
R8_RUN_ID = "DREAL001-P2A2R8-20261111-01"
R8_APPROVAL_SHA256 = "fa0d94a2be7ea2dcb6828b85b0cc032885829a9c8fe904e993bb40535c981f46"
R8_APPROVAL_BYTES = 75166
R8_AMENDMENT_AT_UTC = "2026-11-11T17:05:16Z"
R8_STOP_REPORT_SHA256 = "729eae0f339558881139cf593bfc998f9498a5fb5a4c63139ccb5a5edc07cb6b"
R8_STOP_REPORT_BYTES = 2303
R8_PRESTART_SHA256 = "72a51f0c9121af10d20cd6cd1e617fa36dbb85e11e92dab7dd37d15f83bdc160"
R8_PRESTART_BYTES = 12545
R8_LAUNCHER_GATE_SHA256 = "533263b7ce6982cf79e6ed20345c68dd4f90a4e4ad945633c5fd44ff68e8321b"
R8_LAUNCHER_GATE_BYTES = 37476
R8_CUMULATIVE_STARTS_RECORDED = 446
R8_CUMULATIVE_INTERNAL_CASES_RECORDED = 3134

R9_MAIN_PLANNED_STARTS = MAIN_PLANNED_STARTS
R9_PLANNED_STARTS = R8_PLANNED_STARTS
R9_PLANNED_INTERNAL_CASES = R8_PLANNED_INTERNAL_CASES
R9_CUMULATIVE_STARTS = R8_CUMULATIVE_STARTS
R9_CUMULATIVE_INTERNAL_CASES = R8_CUMULATIVE_INTERNAL_CASES
R9_EXCLUDES_R1_R2_R3_R4_R5_R6_R7_R8_FROM_ENDPOINTS = True

R9_AMENDMENT_SEQ = 9
R9_AMENDMENT_ACTION = "R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX"
R9_AMENDMENT_REASON = (
    "R8 is preserved read-only and excluded from endpoints. Its only attempt stopped in the setup "
    "phase with zero physical calls: the executor-side prefrozen reuse gate raised FreezeRecordError "
    "PREFROZEN_GEOM_MISSING d51866f7d3c49303/462x401 because the initial manifest stores family rows "
    "FLAT while p2a_v2_runtime._reuse_prefrozen and the executor gate expected a nested frozen dict; "
    "no preflight, diagnostic or main case ran and no ledger/cases existed, so R8 charged 0 starts / "
    "0 internal cases. R9 is a minimal A2 execution-layer fix: (a) both readers accept nested or flat "
    "family rows (nested preferred, flat fallback to the row itself) with the same three-file "
    "SHA/vkey/vsp3/canonical fail-closed checks; (b) the executor imports the utc_now helper its gate "
    "needs (latent NameError surfaced by the zero-physical executor gate probe); (c) a new zero-physical "
    "smoke exercises the executor prefrozen gate end-to-end on the real R9 initial manifest before GO. "
    "No A1 bytes, no executor science policy, no plan scientific policy and no endpoint changes. "
    "Protocol D is unchanged."
)

# ---- R10 internal-accounting identity (Lead L-12; zero physical before GO) ----
# R9 is preserved read-only and excluded from endpoints.  Its only attempt stopped in
# the pre-registered diagnostic phase with 6 real starts / 42 real internal cases (the
# batch_summary recorded 0 internal because the A1 evaluator records do not carry an
# internal_solver_cases field), and the main batch stayed NOT_RUN.
R9_CHARGED_STARTS = 6
R9_CHARGED_INTERNAL_CASES = 42
R9_MAIN_STARTS = 0
R9_RUN_ID = "DREAL001-P2A2R9-20261111-01"
R9_APPROVAL_SHA256 = "b502b484e50c71707e484c758b5baaf0409c423c4838094c8300c36202bdd991"
R9_APPROVAL_BYTES = 76257
R9_AMENDMENT_AT_UTC = "2026-11-11T17:56:00Z"
R9_STOP_REPORT_SHA256 = "19f7a502a0c4f67d84600ee9c6cad7a7aca2c0b097103ac2c9db6c5433b68dfe"
R9_STOP_REPORT_BYTES = 830
R9_PREFLIGHT_RESULT_SHA256 = "cf25c1305a5c71881d385aea0cd58a14264a5506b52adcefbb682ea5d75a8302"
R9_PREFLIGHT_RESULT_BYTES = 5771
R9_SOLVER_ATTEMPTS_SHA256 = "c0669bb32d9796884847f1030a987ed941351dd396fecd47b272e42a851dd447"
R9_SOLVER_ATTEMPTS_BYTES = 4477
R9_PRESTART_SHA256 = "c5df82ad869d65cd873a54491824903fa2dca15640b976149dcefeb7e82dc9ed"
R9_PRESTART_BYTES = 12552
R9_LAUNCHER_GATE_SHA256 = "ae701e00e502ce6adb9cf2b713c26a1d04c7031aceb0c8ee388ea87761b3458e"
R9_LAUNCHER_GATE_BYTES = 37476
R9_CUMULATIVE_STARTS_RECORDED = 448
R9_CUMULATIVE_INTERNAL_CASES_RECORDED = 3148
R9_DIAGNOSTICS_IN_MATRIX = False

# R10 re-runs neither the diagnostic phase nor any R9 work other than preflight + main.
R10_DIAGNOSTICS_IN_MATRIX = False
R10_MAIN_PLANNED_STARTS = MAIN_PLANNED_STARTS
R10_PLANNED_STARTS = PREFLIGHT_PLANNED_STARTS + R10_MAIN_PLANNED_STARTS  # 386
R10_PLANNED_INTERNAL_CASES = (
    PREFLIGHT_PLANNED_INTERNAL_CASES + R10_MAIN_PLANNED_STARTS * 7
)  # 2702
R10_CUMULATIVE_STARTS = (
    PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS + R2_CHARGED_STARTS + R3_CHARGED_STARTS
    + R4_CHARGED_STARTS + R5_CHARGED_STARTS + R6_CHARGED_STARTS + R7_CHARGED_STARTS
    + R8_CHARGED_STARTS + R9_CHARGED_STARTS + R10_PLANNED_STARTS
)  # 448
R10_CUMULATIVE_INTERNAL_CASES = (
    PRIOR_CHARGED_INTERNAL_CASES + R1_CHARGED_INTERNAL_CASES + R2_CHARGED_INTERNAL_CASES
    + R3_CHARGED_INTERNAL_CASES + R4_CHARGED_INTERNAL_CASES + R5_CHARGED_INTERNAL_CASES
    + R6_CHARGED_INTERNAL_CASES + R7_CHARGED_INTERNAL_CASES + R8_CHARGED_INTERNAL_CASES
    + R9_CHARGED_INTERNAL_CASES + R10_PLANNED_INTERNAL_CASES
)  # 3148
R10_EXCLUDES_R1_R2_R3_R4_R5_R6_R7_R8_R9_FROM_ENDPOINTS = True

# P1: internal cases are derived from the pre-registered policy constant, never from
# solver records and never from a silent default.  sum(internal) == 7 * starts always.
INTERNAL_CASES_PER_START = 7
INTERNAL_CASES_PER_START_SOURCE = "INTERNAL_PER_START_POLICY"
ACCOUNTING_CONSERVATION_TOLERANCE = 0
LEGACY_INTERNAL_DEFAULT_REMOVED = True
R10_AMENDMENT_SEQ = 10
R10_AMENDMENT_ACTION = "R10_INTERNAL_ACCOUNTING_FIX"
R10_AMENDMENT_REASON = (
    "R9 is preserved read-only and excluded from endpoints. Its only attempt ran the two "
    "PASS_BYTE replay preflight cases and the two pre-registered diagnostic designs (4 starts "
    "over the full family pair) and then stopped in the diagnostic phase with "
    "DIAGNOSTICS_ACCOUNTING_INCONSISTENT: after the R9 fix removed the silent internal=7 "
    "default, the batch_summary recorded 0 internal cases for 6 real starts because the A1 "
    "evaluator records do not expose an internal_solver_cases field, so the phase boundary "
    "check 4 starts / 28 internal failed closed. R10 is a minimal A2 execution/reporting fix: "
    "(a) every evaluation/record row derives internal_solver_cases = 7 * physical_solver_starts "
    "from the pre-registered INTERNAL_PER_START_POLICY constant (never from the A1 ledger, "
    "never a silent default), with per-phase and final conservation checks "
    "sum(internal) == 7 * starts that fail closed as ACCOUNTING_INCONSISTENT; (b) evaluation "
    "rows and the diagnostic/runtime records carry the polar SHA256 when available and null "
    "plus a disclosure otherwise; (c) the internal-accounting semantics are proven by a "
    "zero-physical smoke of the executor main-path evaluation accounting chain (fake solver / "
    "recorded results) with physical=0 and solver_started=false; (d) R10 does not re-run the "
    "diagnostic phase: diagnostics are not in the R10 matrix and the R9 diagnostic evidence is "
    "referenced by SHA; (e) all R9 fixes are retained (prefrozen flat/nested reuse, observe "
    "design_hash fix, x12 domain boundary, invalid numerical tolerance, launcher design_space "
    "preload and env shim, arm-failure evidence). R10 runs 2 preflight + 384 main = 386 planned "
    "starts / 2,702 planned internal cases; cumulative accounting is 62 + 386 = 448 starts and "
    "446 + 2,702 = 3,148 internal cases against caps 451 / 3,157 (headroom 3 starts / 9 internal "
    "cases). No A1 bytes, no plan scientific policy and no endpoint changes. R10 is the final "
    "attempt; there is no R11."
)

R10_DIAGNOSTIC_EVIDENCE_R9 = {
    "source_run_id": R9_RUN_ID,
    "source_preflight_result_sha256": R9_PREFLIGHT_RESULT_SHA256,
    "source_solver_attempts_sha256": R9_SOLVER_ATTEMPTS_SHA256,
    "cases": (
        {"case_id": "DIAG-01", "design_index": 16, "design_hash": "eb00b7ad545243e6",
         "status": "SOLVED_VALID", "objective": 0.01289480742004768,
         "family_polars": (
             "11ff632bb870a6c8f24454edc3251da5d9e2868646d122be561b8cc964ae9c89",
             "aac6e2174c934401f76ccef5c34d2e1f20e77637aaddb14c6061a4f8682ea52b")},
        {"case_id": "DIAG-02", "design_index": 17, "design_hash": "dc96d2438a6dddc3",
         "status": "SOLVED_VALID", "objective": 0.021752395563484656,
         "family_polars": (
             "0540341a1064bfb739efdd8b4a52e226d788efc835a483fda748d84100b848dd",
             "483479ad9c2f1783331b775fdd88a32da786f25311daeadb25224b2fe3fd95fe")},
    ),
    "in_r10_matrix": False,
    "excluded_from_endpoints": True,
}
