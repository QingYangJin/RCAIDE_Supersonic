# L-14 Lead decision — R10 pre-registered scientific auto-stop accepted; R-line execution closed

- decision_id: L-14
- decision: ACCEPT_R10_SCIENTIFIC_AUTO_STOP_AND_CLOSE_R_EXECUTION
- physical_authorization: false
- batch_id: DREAL001-P2-20261111-15
- run_id: DREAL001-P2A2R10-20261111-01
- date_utc: 2026-11-11
- related: L-09 (protocol D), L-10 (prefrozen reuse), L-12 (R10 internal accounting), L-13 (launcher precheck fix)

## Facts (Lead independently read from the run dir)
1. R10 execution started 2026-11-11T18:58:01Z (PID 27588, GATE=PASS, prefrozen gate PASS, 119 static index, A1 runtime guard all_equal=true).
2. Preflight: PRE-01 18:58:04Z-18:58:08Z and PRE-02 18:58:08Z-18:58:12Z both SOLVED_VALID; polar SHA256 455082e2ac8029216a811c89aaa20b34fd9d73faa319eed23da5348e3de4bc87 and 0287afe0d7e5a91bc286c0b6cbd1ca5623d8aafe65110862fe263925129dd33f (7,933 B each) equal the approval expected values -> PREFLIGHT_PASS_BYTE.
3. Diagnostics: diagnostics.json 4976fda2d9ea3b903ac7353802f2492400dd92aead2f829aeff1f69315341613 status DIAGNOSTICS_NOT_IN_MATRIX, starts=0, internal=0, skipped=true; no diagnostic spawn, no diagnostic ledger row (as preregistered under L-12).
4. Main: 48 evaluations recorded (BO 32: 23 valid / 9 invalid; DE 16: 12 valid / 4 invalid), 13 invalid = 27.08% > 25% after main_evaluations >= 48 -> the pre-registered protocol-D automatic scientific stop fired at 2026-11-11T19:13:55Z, phase=scientific_auto_stop, arm_id=DE, message ARM_STOPPED_STOPPED_SCIENTIFIC_INVALID_RATIO. Ledger 91 starts/91 ends, pending 0, no retry, single writer PID 27588, no window violation, no hardware anomaly.
5. Accounting: R10 charged 91 physical starts / 637 internal cases (7 per start: preflight 2/14 + diagnostics 0/0 + main 89/623). Cumulative 448 starts / 3,148 internal against signed caps 451 / 3,157 -> headroom 3 starts / 9 internal. All phases fail-closed conservation checks passed. physical_validation_status=NOT_VALIDATED; fuel_burn_kg=null.
6. Arm statuses: BO COMPLETED (best_primary 0.010006880012223485); DE STOPPED_SCIENTIFIC_INVALID_RATIO (best_primary 0.01289480742004768); PSO, A-BO, A-DE, A-PSO never started. Main was stopped by the signed scientific rule, not by an execution-layer fault.

## Decision
- Accept the stop as valid and pre-registered. It is NOT an execution failure, NOT a solver failure, and NOT a reason to retry. Under the signed protocol D, invalid evaluations are recorded and the arm/batch stops only on the pre-registered scientific thresholds; those thresholds fired exactly as written.
- Close the R-line execution. No R11 and no further real solver calls are authorized: the caps have 3 starts / 9 internal cases of headroom, which cannot support any meaningful new batch, and the signed R10 approval is the final attempt (L-12, no R11).
- Do not reopen, re-sign or reuse the R10 approval for any additional execution. R1-R10 evidence stays read-only.
- The P2a v2 six-arm pilot is therefore NOT COMPLETED: only BO and part of DE ran, and the batch was stopped by the pre-registered invalid-ratio rule. This is the honest end state of the execution line; it must be reported exactly that way.

## Required deliverables (no physical execution)
1. A2: byte-identical append-only commit of the R10 run dir evidence plus the R10 stop report, preserving the merged executor_run.log (REFUSED line at 18:56:53Z plus restarted run), the original launcher bytes from commit 5f1f74e, the one-line 52->57 diff, and the full SHA list. No further byte changes to package/approval/executor/A1.
2. A5: independent post-run audit of the R10 stop and the whole R1-R10 line, then a Chinese final receipt for Issue #9 signed by A5, covering: preflight PASS_BYTE; scientific auto-stop facts and rule; E1-E6 availability (BO completed 32 evaluations, DE partial 16, PSO/A-BO/A-DE/A-PSO NOT_RUN -> full-pilot endpoints NOT_COMPUTABLE); three-layer conclusions kept separate (SOLVER_LOOP_VERIFIED = partial; INTERNAL_AERO_OPTIMIZATION_GAIN = NOT_COMPUTABLE as a six-arm pilot, only descriptive BO/DE observations; EXTERNAL_PHYSICS_SUPPORTED = NOT_VALIDATED); fuel_burn_kg=null; R1-R10 exclusions; cumulative 448/3,148 vs caps 451/3,157; disclosure D-11 (launcher 52->57 pre-start check fix, L-13); no winner, no significance, no cross-family pooling, single seed.
3. A3: descriptive statistics only on the R10 evaluations that exist (BO 32 evaluations / 23 valid; DE 16 / 12 valid), with invalid accounting; no winner/significance claims.
4. A4: final figure/table package for the actual R10 end state (BO completed, DE partial, other arms not run; stop reason; accounting vs caps; preflight byte evidence; R-line timeline), with the descriptive-only corner label.

## Constraints carried forward
- A1 frozen bytes unchanged; plan scientific policy unchanged; no retry; serial 1/OMP 1/timeout 60; no push; physical=0 for all non-execution work; Issue #9 receipt must state this decision and the A5 independent position.
