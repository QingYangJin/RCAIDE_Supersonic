# P1–P3 physical-call accounting rectification

Status: REVIEWED_ON_ACCC734; THIS DOCS-ONLY REVISION CORRECTS THE RECORD REFERENCES AND ADDS THE ROLE-REVIEW RESULTS
Date: 2026-10-30 (Asia/Shanghai)
Parent commit: 38f5119e33196498b5fbb422b58cbc54fc1722f0
Physical calls introduced by this patch: 0 (no RCAIDE Mission, VSPAERO, SU2, DOE evaluation, BO/DE or MAML run)

This patch answers the management review on Issue #4
(comment 6519643090, 2026-10-30T09:37:55Z, CHANGES_REQUESTED): the software
delivery may be accepted conditionally, but it must not be presented as a
physical gate pass, and the physical-call ledger must distinguish a request
from a billed solver attempt.

## Defect

Before this patch:

- `evaluation/low_fidelity.py` initialised `record["physical_call_count"] = 1`
  before the design was even expanded, so parameter errors, out-of-bounds
  requests, geometry rejections, adapter failures and Mission build failures all
  looked like one physical call.
- `evaluation/ledger.py` treated a non-cached request that reported 0 calls as
  an accounting error, so a correct "zero solver attempts" record could not be
  written.
- Cache hits, rejected requests and failed solver attempts were not separately
  traceable in `evaluations.jsonl` or in the run summary.

## Accounting contract

`evaluation/contract.py` (schema `CALL_ACCOUNTING_SCHEMA_VERSION = 1`):

- outcome flags: `request_rejected`, `geometry_rejected`,
  `mission_build_failed`, `mission_solve_attempted`;
- accounting flags: `request`, `cache_hit`, the four outcomes,
  `mission_solve_completed`, `billable_physical_calls`;
- `new_call_accounting()` returns a fresh block: one request, zero outcomes,
  zero billable calls, `failure_stage = None`;
- `validate_call_accounting()` is fail-closed: every flag must be int 0/1,
  exactly one outcome must be set, `billable_physical_calls` must equal
  `mission_solve_attempted`, `mission_solve_completed` cannot exceed attempts,
  and backend rows cannot claim a cache hit (the ledger owns cache marking).

Billing rule: only a Mission solver attempt is billable. A request rejected
before the solver, a geometry rejection and a Mission build failure cost 0 but
remain recorded with their failure stage. Backends that raise without exposing
an accounting block keep the historical fallback and are billed one attempt
(an exception after entering a backend cannot be proven unsolved); the
low-fidelity backend always exposes its per-request block, and the fail-closed
high-fidelity stub is unused by P2.

## Code changes

- `evaluation/contract.py:194-271`: contract constants, `new_call_accounting`,
  `validate_call_accounting`.
- `evaluation/low_fidelity.py`: every record starts with
  `physical_call_count = 0` and a fresh accounting block; `evaluate()` marks
  `design_vector` / `design_space` (request rejected), `geometry_model`
  (geometry rejected), `analysis_build` / `mission_build` (build failed, 0
  billed), and bills exactly one attempt immediately before
  `mission.evaluate()`; later failures keep the attempt billed and set
  `observation`, `geometry_cross_check`, `geometry_mismatch` or
  `mission_not_converged`. A task-fingerprint mismatch is a request rejection
  with stage `task_mismatch`. `last_physical_call_count` /
  `last_call_accounting` expose the outcome even when the backend raises.
- `evaluation/ledger.py`: explicit accounting rows are validated and billed by
  `billable_physical_calls`, with a cross-check against the raw
  `physical_call_count`; cache hits carry `request_count = 1` and
  `cache_hit = 1`; backend exceptions carry the backend's last accounting block;
  legacy backends without the block keep the historical rule (a non-cached zero
  call is an accounting error). Summary adds `accounting_errors`,
  `request_rejected_requests`, `geometry_rejected_requests`,
  `mission_build_failed_requests`, `mission_solve_attempts`,
  `mission_solve_successes` and `call_accounting_consistent`.
- `evaluation/smoke.py`: run summary gains a `call_accounting` block; smoke
  baseline rows carry `request_count` and `call_accounting`.
- `tests/test_physical_call_accounting.py` (new, 17 tests).

## Management five scenarios

| # | Scenario | Code path | Billed | Test |
|---|----------|-----------|--------|------|
| 1 | invalid geometry / out of bounds / parameter error | request rejected / geometry rejected before the solver | 0 | `test_parameter_error_is_not_billed`, `test_out_of_bounds_request_is_not_billed`, `test_geometry_rejection_is_not_billed` |
| 2 | Mission build failure | `analysis_build` / `mission_build` | 0 | `test_analysis_build_failure_is_not_billed`, `test_mission_build_failure_is_not_billed` |
| 3 | solver entered and failed | attempt billed once | 1 | `test_failed_solver_attempt_is_billed_once`, `test_post_solve_failure_still_bills_the_attempt` |
| 4 | cache hit | ledger cache row | 0 new | `test_cache_hit_accounting_and_jsonl_summary_consistency` |
| 5 | budget limit / exception / JSONL-summary consistency | budget stop + exception row | 0 or 1 as described | `test_budget_exhaustion_writes_no_extra_row`, `test_exception_after_billing_is_recorded_and_consistent`, `test_rejected_requests_are_zero_billed_and_traceable` |

Contract-invariant tests: `test_valid_block_is_normalized`,
`test_zero_outcomes_are_rejected`, `test_two_outcomes_are_rejected`,
`test_billable_call_without_attempt_is_rejected`,
`test_backend_cache_hit_is_rejected`, `test_foreign_task_request_is_not_billed`.

## Verification (local, this machine)

- new tests: `Ran 17 tests ... OK`, 2.783 s, exit 0;
- existing ledger/evaluation suites: `Ran 69 tests ... OK`, 7.562 s;
- main checkout full suite (includes the uncommitted P5 tests): `Ran 373
  tests ... OK (skipped=1)`, 29.557 s, exit 0; the single skip is the real
  OpenVSP worker test that needs `CONCORDE_OPENVSP_PYTHON` /
  `CONCORDE_OPENVSP_ROOT`;
- main-checkout log:
  `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/verification-accounting/main_full_suite.log`;
- committed suite after this patch = 277 + 17 = 294 tests (1 skipped).

These are software tests with fake backends or mocked geometry/Mission builders.
No simulation, CFD or OpenVSP geometry export was run for this rectification.

## Historical records

The ten archived RCAIDE Mission evaluations in
`optimization_runs/smoke-p2-20261029T1520` and
`optimization_runs/smoke-p2-20261029T1612` (5 rows each,
`physical_call_count = 1` per row) are not rewritten, recomputed or re-billed by
this patch; the ledger only changes how new records are written. All ten rows
are `VALID`, but feasibility is 5/10: the 145 t diagnostic run
`smoke-p2-20261029T1520` is infeasible on `max_throttle` (largest excess about
`+0.01675`), while the 136 t acceptance run `smoke-p2-20261029T1612` is 5/5
feasible. The five additional Mission calls (four mass-contract calibration
missions plus the 136 t diagnostic probe) are recorded only in
`research/concorde_metaopt/README.md:481-487`, not in either run README, and
remain unarchived documentation rather than billable archived rows. The DOE
160 candidates remain geometry-only with 0 physical calls and 0 fuel-burn
labels.

## Gate status (unchanged, still not physically validated)

| Gate | Status |
|------|--------|
| GEO-12D | PARTIAL (software verified, physical evidence missing) |
| LF-M2.02 | LF_PROVISIONAL |
| HF-M2.02 | BLOCKED |
| BODY-CORR | BLOCKED |
| MISSION-DATA | PARTIAL |
| BUDGET | BLOCKED (no per-item written owner budget) |

P4–P6 remain frozen; PR #3 remains open and is not merged into `main`; no
APPROVED_FOR_NEXT_STAGE is requested or implied by this patch.

## Independent role reviews on accc734

- A1 (own clean worktree, detached): 17/17 new tests OK, exit 0; committed
  suite `Ran 294 tests ... OK (skipped=1)`, 25.550 s, exit 0; the only skip is
  the real OpenVSP worker test that needs the external Python 3.9 install.
- A5 (own clean worktree, detached): verdict `APPROVE_WITH_FINDINGS`,
  0 blocker / 0 major / 4 minor; independent 17-test rerun OK and 294-test
  rerun OK (skipped=1), exit 0; all five management scenarios map to real code
  paths and tests; commit scope has no `optimization_runs/` file and the
  archived 5+5 rows are untouched.
- A3: `PASS`, 7/7 checks; the commit is one single-parent change of exactly
  7 files (2 added, 5 modified), no P5/tutorials/`optimization_runs/` paths,
  no staged leftovers, `main` still at ec65e5a, no reset/force.
- A2: `COMPLETED_WITH_PREMISE_CORRECTIONS`; 10 archived rows unchanged (2 x 5,
  feasible only 5/10 as noted above), the 5 unarchived calls live only in
  `research/concorde_metaopt/README.md:481-487`, DOE 160 candidates are
  geometry-only, and of the new summary fields only `mission_solve_attempts`
  (=10) is derivable from the old archives; the other five are
  `NOT_DERIVABLE` and are not back-filled with invented values.

The A5 minors are accepted as non-blocking follow-ups: (F-01) a valid
accounting block that disagrees with the raw count is flagged but billed 0,
(F-02) backend-exception fallback default (now documented above), (F-03) the
cache-hit-while-exhausted boundary has no dedicated test, and (F-04)
`budget_overruns` also counts accounting errors. None of them changes the five
management scenarios or the archived record interpretation.

## Revision note

This revision is docs-only relative to accc734: it corrects the unarchived-call
reference location (A2 finding D2), records the valid 10 / feasible 5 split
(A2 finding D1), adds the backend-exception default disclosure (A5 F-02), and
replaces the pending-review list with the completed role results. No code or
test changed, and the 294-test suite is unaffected.

The Lead will post one consolidated evidence receipt on Issue #4 after the
docs-only revision, without claiming any gate pass and without requesting a new
physics budget.
