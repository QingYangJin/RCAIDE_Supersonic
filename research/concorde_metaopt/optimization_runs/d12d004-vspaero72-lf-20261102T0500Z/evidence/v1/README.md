# D-12D-004 V1 evidence - VSPAERO 7.2.2 thin-LF

status: **V1_STOPPED_ABORT_FINAL** (closed 2026-11-02T06:34Z, before the 11:55Z deadline, by the approved stop rule; root-cause static check added afterwards, no extra solver start, starts stay 4/10)

## What was authorised

- Lead authorisation 2026-11-02T05:55:00Z (Issue #4 / comment 6569140757), category A (VSPAERO 7.2.2 thin-LF only).
- Hard limits: <=10 solver starts, serial, <=4 cores, <=8 GB RAM, <=600 s per start, round <=6 h.
- Categories B/C/D/E/P4 = 0 starts; D-12D-002 23/23 starts do **not** carry over.

## What happened

| event | case | attempt | outcome | wall | note |
|-------|------|---------|---------|------|------|
| NA-D12D004-001 | V7-00 | 1 | FAILED | 0.024 s | .vkey/.csf missing beside .vspgeom (packaging defect LD-001) |
| NA-D12D004-002 | V7-01 | 1 | ABORTED_WRAPPER_DEADLINE | 120.0 s | outer 120 s tool deadline killed wrapper+solver (LD-003) |
| NA-D12D004-003 | V7-01 | 2 | TIMEOUT | 600.331 s | Mach 2.02 thin solution diverged, no .polar |
| NA-D12D004-004 | V7-00 | 2 | VERIFY_FAILED | 76.891 s | Mach 0.10 ran; nonphysical values; header incompat LD-002 |

A2 stopped the chain after event 003 under the approved stop rules at 2026-11-02T06:25:27Z (freeze-instant counters 3 used / 7 remaining / 1 retry). The Lead then authorised exactly one V7-00 retry (messages m01190/m01194, decision (a)): that retry ran as event 004 (started 06:26:57Z, finished 06:28:14Z, VERIFY_FAILED) and the round was terminated with final counters 4 used / 6 remaining / 2 retries (billable_events=4). The remaining 6 starts are CLOSED_NOT_CARRIED_OVER_NOT_REALLOCATED.

## Final state

- budget: starts_used=4, starts_remaining=6, retries_used=2, billable_events=4; remaining 6 **CLOSED_NOT_CARRIED_OVER_NOT_REALLOCATED**.
- case matrix: V7-00 FAILED_NONPHYSICAL_VALUE, V7-01 TIMEOUT_DIVERGED, V7-02..V7-08 NOT_RUN_AFTER_ABORT, V7-09 NOT_RUN_CONDITION_NOT_TRIGGERED.
- gates: LF-M2.02 drag NOT_VALIDATED; VSPAERO 7.2.2 thin supersonic NOT_A_VALID_PHYSICAL_METHOD; V7-00 subsonic hygiene FAIL; validated aircraft fuel label false.
- no solver is running; no source or test file was modified; nothing was committed or pushed.

## Status tokens (canonical)

- V7-00 final status is FAILED_NONPHYSICAL_VALUE in the case matrix, summary.json, lf_vspaero_results.json and evidence/v1/case_results.json. The alias FAIL_HYGIENE_NONPHYSICAL is deprecated and no longer used.
- V7-01 = TIMEOUT_DIVERGED; V7-02..V7-08 = NOT_RUN_AFTER_ABORT; V7-09 = NOT_RUN_CONDITION_NOT_TRIGGERED always.
- Reason for choosing FAILED_NONPHYSICAL_VALUE: it states the final case verdict (solver completed, coefficients nonphysical); FAIL_HYGIENE is only one of the internal checks and is kept as hygiene_check.verdict=FAIL in case_results.json.

## Defects found (recorded, not fixed in this round)

- LD-001: .vkey/.csf are required beside .vspgeom/.vspaero with the same base name; setup packaging missed them.
- LD-002: the V0 runner polar validator expects VSPAERO 6.2 column names (CL, CDi, CDtot); VSPAERO 7.2.2 writes CLo/CLi/CLtot, CDo/CDi/CDtot -> POLAR_HEADER_MISSING. The V7 polar itself is structurally readable.
- LD-003: the wrapper must run without an outer 120 s tool deadline; it now runs as a background job with an internal 600 s solver timeout and streams stdout/stderr.

## Evidence index

- evidence/v1/ledger/solver_ledger.jsonl - 4 billable events (19 fields each).
- evidence/v1/run_start.json - authorised round record and actual first start time.
- evidence/v1/stop_decision.json - stop rule, Lead decision, retry record, final counters.
- evidence/v1/case_results.json - per-case harness result, polar/history sha256, final classification.
- evidence/v1/per_case_conclusions.md / .csv - 10-case table.
- evidence/v1/v7_01_divergence.json - V7-01 divergent history extract.
- evidence/v1/vkey_fix.json, wrapper_deadline_fix.json, case_prep.json - pre-flight and defect records.
- evidence/v1/setup_gen/ - zero-solver OpenVSP 3.55 setup generation for V7-00/01/02/03/04/05/06/07/08 (9 setup dirs, readback 17/17); geom_result_thin.csv exists for 8 of them (not V7-03).
- Archival raw products: D:/RCAIDE/outputs/concorde_metaopt/d12d004-vspaero72-lf-20261102T0500Z/raw_artifacts/ (gitignored): cases/V7-00/ (polar, history, lod, adb, logs), cases/V7-01/ (history, logs, no polar), failed_runs/V7-00_attempt1/, failed_runs/V7-01_attempt1/.

## Root-cause static check (zero solver, Lead diagnosis request)

After the Lead asked whether DegenGeom is the only correct thin input mode, a static check was done; no solver was started:

- Official enum: SET_NONE = -1, SET_ALL = 0 (Python API facade.py plus compiled _vsp).
- Official VSPAERO API test (test_vsp_api.py lines 1450-1463 and 1524-1536) configures VSPAEROComputeGeometry with GeomSet=SET_NONE and ThinGeomSet=SET_ALL, i.e. the .vspgeom thin path used by our generator is the official path.
- Our generated geom_result_thin.csv records GeometrySet = -1 (= SET_NONE, no thick set) and ThinGeometrySet = 0 (= SET_ALL, all thin geoms) for 8 of the 9 generated setup directories (V7-00, V7-01, V7-02, V7-04, V7-05, V7-06, V7-07, V7-08; V7-03 has no geom_result_thin.csv and V7-09 has no setup directory): thin geometry was applied, the inputs were not swapped.
- The bundled Uber_eCRM-002 example uses DegenGeom + .groups + -unsteady (multirotor TimeStep case), a different input mode, and is not a steady thin benchmark.
- Conclusion: the official thin path is VSPGEOM, so this was not an input-mode error; the DIAGNOSTIC_DEGENGEOMMODE start was skipped per the Lead decision rule 4. Remaining differences from the official example are solver settings (NumWakeNodes=8 / WakeIters=5 versus 128 / 0), recorded as an unproven likely contributing factor.

## Non-carryover statement

The 6 unused starts are not transferred to any later round, category, or run; the V1 round is closed.

## Bookkeeping revision (task-66, text only)

- 2026-11-02T07:03:10Z (UTC): A5 CHANGES_REQUESTED run-dir items were fixed without any solver start: run_start lists all 4 starts, the stop -> authorisation -> retry ordering is explicit, V7-00 status is unified, V7-09 is split out as NOT_RUN_CONDITION_NOT_TRIGGERED, and the geom CSV count is 8 of 9 setup dirs.
- data_manifest.json is regenerated by the Lead after these text edits; A2 does not modify it.
