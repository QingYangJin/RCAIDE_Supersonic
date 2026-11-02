# D-12D-004 V1 (VSPAERO 7.2.2 thin-LF) - per-case conclusions

- run_id: d12d004-vspaero72-lf-20261102T0500Z
- round: V1, authorised 2026-11-02T05:55:00Z, deadline 2026-11-02T11:55:00Z (closed early by stop rule)
- budget: 4/10 starts used, 2 retries, remaining 6 CLOSED / NOT carried over / NOT reallocated
- solver: D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe (VSPAERO 7.2.2, sha256 db71c441...fddad), invoked directly with '-omp 4', serial

| # | case | group | Mach | status | evidence / reason | usable as physical evidence |
|---|------|-------|------|--------|-------------------|------------------------------|
| 1 | V7-00 | S | 0.10 | FAILED_NONPHYSICAL_VALUE | solver rc=0, wall 76.891 s; CLtot=-2801.89, CDtot=-376.37 (negative drag), history diverged; LD-002 verifier header incompat | failed; not usable |
| 2 | V7-01 | S | 2.02 | TIMEOUT_DIVERGED | attempt1 got 120 s outer-deadline abort; attempt2 hit 600.331 s timeout; history O(1e18)-O(1e24); no polar | failed; LF-M2.02 thin NOT_VALIDATED |
| 3 | V7-02 | M | 2.02 | NOT_RUN_AFTER_ABORT | Tess 8/17 12D baseline setup generated (zero solver), not executed | not executed |
| 4 | V7-03 | M | 2.02 | NOT_RUN_AFTER_ABORT | Tess 16/33 12D baseline setup (V0 asset), not executed | not executed |
| 5 | V7-04 | M | 2.02 | NOT_RUN_AFTER_ABORT | Tess 32/65 12D baseline setup, not executed | not executed |
| 6 | V7-05 | P | 2.02 | NOT_RUN_AFTER_ABORT | W01 area +1% setup generated, not executed | not executed |
| 7 | V7-06 | P | 2.02 | NOT_RUN_AFTER_ABORT | W03 sweep1 +1 deg setup generated, not executed | not executed |
| 8 | V7-07 | P | 2.02 | NOT_RUN_AFTER_ABORT | W10 tip twist +2 deg setup generated, not executed | not executed |
| 9 | V7-08 | D | 2.02 | NOT_RUN_AFTER_ABORT | alpha sweep 0/2/4 setup generated, not executed | not executed |
| 10 | V7-09 | D | 2.02 | NOT_RUN_CONDITION_NOT_TRIGGERED | conditional wake sensitivity; prerequisite never satisfied | not executed |

## Global conclusions

1. VSPAERO 7.2.2 thin diverges at Mach 2.02 on the standard wing (V7-01): 600 s timeout, .history reaches O(1e18)-O(1e24) by wake iteration 2-3, no .polar. It is not a valid physical method for the supersonic LF point.
2. Even the Mach 0.10 standard-wing sanity case (V7-00) returned nonphysical coefficients (CLtot=-2801.89, CDtot=-376.37); the wake/GMRES iteration diverged and the written polar is unusable.
3. The V7-00 verifier failure POLAR_HEADER_MISSING (LD-002) is a runner defect: VSPAERO 7 writes CLo/CLi/CLtot, while the V0 validator expects the 6.2 column names. It is recorded separately from the nonphysical values.
4. Therefore LF-M2.02 drag remains NOT_VALIDATED; no external body correction may be injected; V7-02..V7-09 were not executed after the approved stop rule triggered.
5. 0 fabricated numbers; every value above traces to evidence/v1/ledger/solver_ledger.jsonl, evidence/v1/case_results.json, the archived .polar/.history files, or evidence/v1/v7_01_divergence.json.
