# Role reviews archived for D-12D-003 Round-1

This directory mirrors the read-only deliverables that the independent roles produced during Round-1 (zero solver starts). Each subdirectory is the verbatim copy of the role's file from the external agent-state directory, with hashes recorded in `../data_manifest.json` (regenerated after the final revision).

## a1-code-dev (task-36 NEW-API-COMPAT, task-37 VSPAERO-OLD-DIAG)

- `api_compat_matrix.md` / `api_compat_checks.csv` - 29-item compatibility matrix between OpenVSP 3.26.1 (Python 3.9) and 3.55.0 (Python 3.11); includes the changed result-capture path (ExecAnalysis id -> result APIs) and the DegenGeom CSV camber-row field count change 11 -> 14.
- `vspaero_old_diagnostic.md` / `vspaero_old_evidence.json` - static diagnosis of the archived VSPAERO 6.2.0 run: three cases (W01/W03/W10) had 12 template lines without `=`, so VSPAERO silently used Sref=1.0 and printed coefficients inflated by about 358x (those cases are INVALID); the correctly-formatted cases show Trefftz CDi sign flips with mesh density and CL is not mesh-converged (coarse -> fine +29.09%). Harness guard defects (setup rc=1 not stopping the solve, no polar sanity checks) are documented as blocker-level process issues.
- `geometry_diff.json` - STL geometry diff for the baseline and W10+2deg wing between the two OpenVSP versions.

A1's own status: task-36 completed, task-37 completed; repaired-code verification NOT_RUN (no budget).

## a2-run-opt (task-38 AREA-RULE-OFFLINE; task-39 budget proposal)

- `area_rule_offline.md` / `area_rule_cases.csv` - independent Eminton-Lord port reproduces the archived OpenVSP CDWave to about 1e-6 and the Sears-Haack analytic value to 1e-9 at n=800; however the raw inversion is ill-conditioned (matrix condition number 1.9e6 at n=200, 1.2e8 at n=800), white-noise calibration amplifies slice noise by 58x-18380x, and the paired wing-alone vs wing+body fuselage increment has SNR below 2 and no mesh convergence. Verdict: WAVE area rule stays NOT_VALIDATED; no correction may be injected.
- Round-2 budget request: see `../budget_request_round2.json` (proposal only, AWAITING_OWNER_APPROVAL; no solver was started).

## a3-repo-guard (task-35 INSTALL-AUDIT)

- `install_audit.md` / `facts.json` - official-source check (HTTP 200, remote archive length matches the local 49,664,844 B, Last-Modified 2026-10-12 04:47:13 GMT), expansion 491/491 files / 149,488,735 B, API version OpenVSP 3.55.0, vspaero banner v7.2.2, old 3.26.1 install and SUAVE 3.9 worker untouched, no PATH/registry/site-packages changes, rollback plan static-only (execution NOT_RUN), repository clean of install artifacts.

## a4-issue-liaison (task-34 INTAKE-MATRIX)

- `requirements_matrix.md` / `requirements.csv` / `round_plan.md` - 35 unique requirements from D-12D-003 (14 Round-1 zero-solver, 9 Round-2 budget-gated, 12 standing governance), each with source, owner, needed evidence, status and gate. Confirms PR #3 head 5dcb0bf (D-12D-003 is later and not yet in the PR), 23/23 old budget exhausted, no new physical budget approved.

## Cross-role conclusion carried into the run summary

- The archive diagnosis and the offline area-rule recomputation are both **negative/partial results**: VSPAERO 6.2.0 thin-surface results are not usable at Mach 2.02, and the OpenVSP area-rule numbers are not a validated correction. No gate state changes in Round-1.
- The new toolchain (OpenVSP 3.55.0 / VSPAERO 7.2.2) is installed, isolated, and able to produce the exact solver inputs for a future owner-approved Round-2 without starting a solver. That is a capability result, not a physical result.
