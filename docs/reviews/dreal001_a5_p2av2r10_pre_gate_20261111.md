# G-P2AV2R10-PRE - A5 package gate

- gate_id: G-P2AV2R10-PRE
- created_utc: 2026-11-11T18:47:58Z
- reviewer: A5 (physical_call_count=0)
- batch/run: DREAL001-P2-20261111-15 / DREAL001-P2A2R10-20261111-01
- window: {"start_utc":"2026-11-11T18:30:00Z","end_utc":"2026-11-12T04:00:00Z","token":"WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z","status":"REQUESTED_NOT_SIGNED"}
- verdict: **PASS_WITH_MANDATORY_SIGNATURE_CORRECTIONS**
- checks: 57 total / 53 PASS / 4 PASS_WITH_DISCLOSURE / 0 FAIL
- package commit: 79e8f6a8133422c3865d99a841f8b68e8cc039d6
- tools commit: 5f1f74e681f029a97212f4ed1a50293263bcdcc; dry-tool fix commit: 0782b29618bbe83241cc631f188edbf7880f6b71
- A5 independent executor-gate replay: docs/reviews/dreal001_a5_p2av2r10_exec_gate_replay_20261111.json b6c14f09d5f54597ba7304445a4996c4b564013028f951db9a337da541f949de/14255 B (PASS)
- conditions: 57 (docs/reviews/dreal001_a5_p2av2r10_signature_conditions_20261111.json)

## Anchors

- package_commit: "79e8f6a8133422c3865d99a841f8b68e8cc039d6"
- tools_commit: "5f1f74ee681f029a97212f4ed1a50293263bcdcc"
- dry_tool_fix_commit: {"resolved":"0782b29618bbe83241cc631f188edbf7880f6b71","files":["docs/evidence/dreal001/post_approval_dry_run_r10.py","docs/evidence/dreal001/r10_post_approval_dry_run_selftest_20261111T184054Z.json"],"disk_equal":true,"note":"verified A5: git diff --quiet exit 0 for both files"}
- launcher: SHA256 476481e65674d30450b03eb85f7fc44bca06323213161d53ddc652c218690bc8 / 29361 B (docs/evidence/dreal001/p2av2r10_launch.py)
- launcher_gate: SHA256 0a293dc5d34931145029fac4c4f8660192137e7c705547ffead2aad2d4dfc68c / 19669 B (docs/evidence/dreal001/p2av2r10_prefrozen_gate.py)
- executor: SHA256 ed0f2324f91ffc649e9b8d997051d515ff7e248f027c46ba1c9125e2f575704c / 99591 B (D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\optimizers\p2a_v2_executor.py)
- runtime: SHA256 fdb22a4b64a8ab7daf0e22a1902d9f17caaf60d977dfab4dc3d20569801d9c6d / 58386 B (D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\optimizers\p2a_v2_runtime.py)
- common: SHA256 44d984acb0f8afe8c6b7dfdf933c4d78567ab2f0bef39c0d996f7f0227559624 / 30690 B (D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\optimizers\p2a_v2_common.py)
- p2a_v2: SHA256 6ac8ab3e8e36951f7fc72ee42a171c8efef466ce7d4d38e81798053ca4cfc1ed / 150869 B (D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\optimizers\p2a_v2.py)
- launcher_smoke: SHA256 82df939bd1d68d191aff59151c4c1122b5b547f1885269fdffcf77b044f5c64d / 24734 B (docs/evidence/dreal001/r10_launcher_smoke_20261111T1909Z.json)
- mainpath_smoke: SHA256 fa163ecefd33dac1a53c00c192b0c8bd8c8af6393a35f4b609a418c67f680ea5 / 9431 B (docs/evidence/dreal001/r10_accounting_smoke_20261111T1859Z.json)
- dry_run_tool: SHA256 bf283ec0295634059a7f6a14f5070196cfc97fed7bddffca0ad02d19b272cc08 / 22795 B (docs/evidence/dreal001/post_approval_dry_run_r10.py)
- dry_run_selftest: SHA256 2cb377b13fb0decff037868fcaa4ba0966f0488a414408564ec6cb59caec6b12 / 1649 B (docs/evidence/dreal001/r10_post_approval_dry_run_selftest_20261111T184054Z.json)
- a5_executor_gate_replay: SHA256 b6c14f09d5f54597ba7304445a4996c4b564013028f951db9a337da541f949de / 14255 B (docs/reviews/dreal001_a5_p2av2r10_exec_gate_replay_20261111.json)
- pytest_log: SHA256 4e2d171e6a60009352cbb4d175800e2d8a09550bfae9f8bbc4f6ddf545a56a56 / 234 B (docs/evidence/dreal001/r10_pytest_20261111.txt)
- pair_manifest: SHA256 55e63f392e2821fff02e6f849a3090b9f9c7263be0b9f6c8debbcea599ab1892 / 294786 B

## Checks

| id | status | check |
|---|---|---|
| C01 | PASS | package commit resolves and the 8-file package is in the commit |
| C02 | PASS | 8/8 package files on disk are byte-identical to the package commit |
| C03 | PASS | plan.json SHA256/bytes |
| C04 | PASS | approval.DRAFT.json SHA256/bytes |
| C05 | PASS | identity_binding.json file SHA and canonical identity SHA |
| C06 | PASS | initial_designs_manifest cffec652/14,822 B with 3 designs 15/16/17 and FLAT family rows |
| C07 | PASS | P2A_V2_PREREGISTRATION.md R10 addendum, run/window/386-2702, diagnostics not rerun, no stale R9 addendum |
| C08 | PASS | dry_run.json + executor_dry_run.json package previews with R10 constants |
| C09 | PASS | SHA256SUMS.txt 7/7 entries recomputed |
| C10 | PASS_WITH_DISCLOSURE | package dry_run C10_executor_sha defined false-negative and C16/C19 NV triaged (non-blocking) |
| C11 | PASS | executor dry-run blocked pre-approval: 386 planned/0 emitted/2702 internal/diagnostics 0-0/0 physical |
| C12 | PASS | pre-execution run dir contains exactly the 8 package files (no cases/ledger/approval/batch/stop; R9/R8 dirs clean) |
| C13 | PASS | DRAFT identity: batch 15/run R10/window/token/planned 386-2702/caps 451-3157/diagnostics 0-0 not in matrix |
| C14 | PASS | supersedes R9 signed approval b502b484/76,257 B/physical 62/run R9 |
| C15 | PASS | amendment_log seq1-9 byte-identical to R9 signed history; seq10=R10_INTERNAL_ACCOUNTING_FIX physical 62 |
| C16 | PASS | R9 stage stop independently disclosed: charged 6/42, main NOT_RUN, evidence SHAs |
| C17 | PASS | flat/nested fix is execution-layer only: runtime family_frozen_payload helper + executor flat-row fallback; A1 bytes and plan scientific policy unchanged |
| C18 | PASS_WITH_DISCLOSURE | executor-OWN _prefrozen_reuse_gate executed zero-physically on the real R10 manifest by A5 independent replay |
| C19 | PASS | launcher --smoke zero-physical gate PASS 79 checks/static 119/A1 guard all_equal/6 triples |
| C20 | PASS | launcher-side gate module 0a293dc5/19,669 B present with static 119, role map, vkey/vsp3, canonical, A1 guard |
| C21 | PASS | launcher and executor prefrozen gates are equivalent on the same R10 manifest (119 static/3 designs/PASS) |
| C22 | PASS | P3 zero-physical main-path accounting smoke: real PreflightVerifier+P2AV2Runner+Batch.run_arm (6 arms), 2/14 + 0/0 + 384/2688 = 386/2702 = 7x386 |
| C23 | PASS_WITH_DISCLOSURE | R9 flat/nested + fail-closed unit tests retained in test_dreal001_p2a_v2.py; pytest green |
| C24 | PASS | A1 frozen bytes unchanged (evaluator/freeze_api/openvsp_model/mesh_identity/design_space/config/bundle/exe) |
| C25 | PASS | A2 R10 execution code SHAs: executor ed0f2324/99,591; runtime fdb22a4b; common 44d984ac; p2a_v2 6ac8ab3e |
| C26 | PASS | plan diff vs R9 (482 leaf paths) is fully whitelisted identity/accounting/diagnostics-derivation; scientific policy byte-equal |
| C27 | PASS | cumulative accounting 62/446 + 386/2702 = 448/3148 <= caps 451/3157 (headroom 3/9) |
| C28 | PASS | R10 window 18:30Z-11-12T04:00Z, token, start 21:00Z/clean 02:30Z/hard 04:00Z |
| C29 | PASS | preflight remains PASS_BYTE-only replay PRE-01/PRE-02 with expected polar SHAs |
| C30 | PASS | R1-R8 signed approvals byte-unchanged (8/8) |
| C31 | PASS | R1-R9 historical exclusion and charged baseline 62/446 (R9 6/42) recorded |
| C32 | PASS | L-12 decision trail + A5 independent position/dissent recorded in gate |
| C33 | PASS | launcher binding/safety: pins executor-plan-identity, R10 env, gate before prestart/spawn, refuses on gate FAIL |
| C34 | PASS | launcher smoke is SMOKE_NO_SOLVER with zero physical/solver, no cases/ledger |
| C35 | PASS_WITH_DISCLOSURE | dry-run tool bf283ec0/22,795 B (D01-D46) and fake-signed selftest 2cb377b1 46/46; old 1c6199bf superseded |
| C36 | PASS | r10_addendum = R10_INTERNAL_ACCOUNTING_FIX; DRAFT bindings self-consistent |
| C37 | PASS | conditions set = 57 items (39 R3-BASE retained + 3 R1 history + R10-specific) |
| C38 | PASS | refs_final 14 keys with a5_review gate-commit placeholder; a2_package_commit=79e8f6a; a2_execution_code=ed0f2324 |
| C39 | PASS | DRAFT->signed allowed deltas are exactly the 9 documented top-level fields |
| C40 | PASS | executor fail-closed tamper/mismatch guards present (flat/nested, sibling, static-hit, x12) |
| C41 | PASS | pytest green: 16 passed, 31 deselected, zero physical |
| C42 | PASS | no stale R8/R9 identity text in R10 package (no stale addendum, batch 15/run R10, prereg updated) |
| C43 | PASS | design-space binding and static-hit fail-closed guard retained |
| C44 | PASS | GO/gate prefixes present in launcher (G-P2AV2R10-PRE:PASS / C-P2AV2R10-02:PASS:) |
| C45 | PASS | static index 119 and pair manifest 55e63f39 match in launcher and executor gates |
| C46 | PASS | 3 designs x 2 families = 6 A1 runtime guard triples equal; replay designs all ok |
| C47 | PASS | R7 H1 evidence retained (prefrozen reuse rationale) |
| C48 | PASS | no mesh-QC data gate added; R10 fixes remain execution/reporting layer |
| C49 | PASS | no winner/significance/cross-family comparison/fuel; physical NOT_VALIDATED, fuel_burn_kg null |
| C50 | PASS | R10 is the final attempt: no R11 default; failure -> stop receipt, R1-R10 excluded |
| C51 | PASS | A5 physical_call_count=0 throughout this gate (independent replay used in-memory store, no solver) |
| C52 | PASS | pre-execution run dir exactly 8 files; R9 dir clean vs d1cc798; R8 dir clean vs 62a6231 |
| C53 | PASS | A5 blocker on old package 5632c2d (diagnostics unconditional + R8 dry-run constants) is closed in v2 package |
| C54 | PASS | executor diagnostics declaration fail-closed (missing/mismatch guards) and skip writes DIAGNOSTICS_NOT_IN_MATRIX |
| C55 | PASS | executor dry-run uses R10 constants (386/2702, no R8 stale constants, empty diagnostic cases) |
| C56 | PASS | refs_final 14 keys and conditions 57 are internally consistent with the template; M1-M6 declared |
| C57 | PASS | A5 gate is not an execution authorization; GO remains Lead-only after signature + real dry-run + C gate |

## Accounting

{
 "baseline": {
  "prior_39_285": true,
  "r1": {
   "starts": 2,
   "internal": 14
  },
  "r2": {
   "starts": 2,
   "internal": 14
  },
  "r3": {
   "starts": 2,
   "internal": 14
  },
  "r4": {
   "starts": 2,
   "internal": 14
  },
  "r5": {
   "starts": 0,
   "internal": 0
  },
  "r6": {
   "starts": 3,
   "internal": 21
  },
  "r7": {
   "starts": 6,
   "internal": 42
  },
  "r8": {
   "starts": 0,
   "internal": 0
  },
  "r9": {
   "starts": 6,
   "internal": 42
  },
  "total_starts": 62,
  "total_internal": 446
 },
 "rule": "any physical count beyond the approved figures requires a new written Lead approval; no retry, no silent budget change",
 "r10": {
  "planned_starts": 386,
  "planned_internal": 2702,
  "preflight_starts": 2,
  "diagnostic_starts": 0,
  "diagnostic_designs": 0,
  "main_starts": 384,
  "reserve": 64,
  "cumulative_starts": 448,
  "cumulative_internal": 3148,
  "max_starts": 451,
  "max_internal_cases": 3157,
  "headroom_starts": 3,
  "headroom_internal": 9,
  "check": true
 }
}

## Protocol D (R10)

{
 "lead_decision": "L-12 (Lead): R9 S1 STOP accepted and permanently excluded; R10 authorized as the FINAL attempt (no R11 by default). R10 fixes: P1 internal=7xstarts from preregistered policy with fail-closed conservation; P2 polar_sha256 recorded when available else null; P3 zero-physical main-path accounting smoke; P4 diagnostics not re-run (R10 matrix has 0 diagnostics, reference R9 evidence SHA); P5 R9 fixes retained.",
 "internal_accounting": "internal_solver_cases = 7 x physical_solver_starts, source INTERNAL_PER_START_POLICY, tolerance 0, phase+total conservation, ACCOUNTING_INCONSISTENT fail-closed stop; no ledger inference and no silent default.",
 "diagnostics_not_rerun": "R10 matrix diagnostic_starts=0 / diagnostic_internal_cases=0; executor skips the diagnostics phase with DIAGNOSTICS_NOT_IN_MATRIX (0/0, no solver spawn) after dual-source plan/approval declaration check; R9 diagnostic evidence is referenced by SHA.",
 "prefrozen_flat_fix": "R9 flat/nested read fix retained unchanged in R10 as execution-layer code: runtime family_frozen_payload helper + executor family row fallback; A1 bytes unchanged.",
 "stop_rules": "preflight non-PASS_BYTE -> stop; ledger/window/hardware/single-case execution-layer exception -> stop; single-case INVALID_NUMERICAL tolerated; auto-stop >25% invalid after >=48 main starts, >=6 consecutive invalid in one arm, or >64 cumulative invalid; accounting inconsistency -> stop; no retry."
}

## Exclusions

{
 "r1": "Permanent.",
 "r2": "Permanent.",
 "r3": "Permanent.",
 "r4": "Permanent.",
 "r5": "Permanent.",
 "r6": "Permanent.",
 "r7": "Permanent.",
 "r8": "Permanent.",
 "r9": "Permanent (stage stop, charged 6/42; A5 FAIL-09 upheld).",
 "rule": "R1-R9 are excluded from E1-E6 and from any optimizer/physics result; their run dirs, signed approvals, evidence and SHA256SUMS remain READ-ONLY and byte-unchanged (R9 dir clean vs commit d1cc798; R8 dir clean vs commit 62a6231)."
}

## Lead decision and A5 position

{
 "lead_decision": "Lead L-12 + m02945/m03593: R9 closed as S1 STOP with charged 6 starts/42 internal; R10 = batch DREAL001-P2-20261111-15 / run DREAL001-P2A2R10-20261111-01 / window 2026-11-11T18:30:00Z-2026-11-12T04:00:00Z / token WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z / planned 386-2702 / caps 451-3157 / cumulative 448/3148 (prior 62/446) / supersedes R9 approval b502b484/76,257 B/physical 62 / seq10=R10_INTERNAL_ACCOUNTING_FIX physical 62 / final attempt, no R11.",
 "a5_position": "A5 independently upheld the R9 stop and root cause (FAIL-09; including the version-attribution correction: default 7->0 removal and the diagnostics conservation check were introduced in R8 P3, not R9) and records: this is the 10th execution attempt in the series and the 4th consecutive round whose stop was an execution/accounting-layer defect rather than a numerical/geometry result. A5 accepts R10 only as the FINAL attempt under all 57 conditions and the P1/P3/P4 evidence, and states in advance that a further setup/main failure with no receipt-grade numerical result closes P2a as NOT_RUN/NOT_COMPUTABLE.",
 "no_r9_by_default": false,
 "no_r10_by_default": false,
 "no_r11_default": true
}

## Disclosures

- D1 R1-R9 exclusion: charged 23 starts/161 internal (R1-R4 2/14 each, R5 0/0, R6 3/21, R7 6/42, R8 0/0 setup stop, R9 6/42 stage stop); cumulative baseline 62/446; R10 plan 386/2702; projected cumulative 448/3148 vs caps 451/3157 (headroom only 3 starts/9 internal).
- D2 R9 stage stop (independently upheld by A5 FAIL-09): preflight PASS_BYTE 2 starts/14 internal; diagnostics DIAG-01 design16 eb00b7ad545243e6 and DIAG-02 design17 dc96d2438a6dddc3 both SOLVED_VALID (primary 0.01289480742004768 / 0.021752395563484656) but internal recorded 0 vs preregistered 28 -> DIAGNOSTICS_ACCOUNTING_INCONSISTENT; main NOT_RUN; charged 6 starts/42 internal; evidence preflight cf25c130/5,771, batch 038feee3/19,285, stop 19f7a502/830, solver_attempts c0669bb3. R9 permanently excluded.
- D3 R10 P1 internal accounting is derived ONLY from the preregistered policy 7 x starts (INTERNAL_PER_START_POLICY); the legacy silent default 7 and ledger-derived inference are removed; conservation tolerance 0; fail-closed ACCOUNTING_INCONSISTENT on mismatch; P2 polar_sha256 recorded when available else null/disclosed.
- D4 R10 P3 zero-physical accounting smoke (docs/evidence/dreal001/r10_accounting_smoke_20261111T1859Z.json fa163ece/9,431 B, 24/24 checks, failed []) drives the real executor main path (PreflightVerifier + P2AV2Runner + P2AV2Batch.run_arm over 6 arms): preflight 2/14, diagnostics 0/0 not in matrix (no spawn), main 384/2688, total 386/2702 = 7x386, cumulative 448/3148, physical 0, solver false, no ledger/cases, freeze builder not called.
- D5 A2 did not produce a separate R10 executor-own _prefrozen_reuse_gate smoke JSON (R9-style). A5 compensates with an independent zero-physical replay of the executor OWN gate code path on the final R10 executor bytes ed0f2324 and the real R10 initial manifest: docs/reviews/dreal001_a5_p2av2r10_exec_gate_replay_20261111.json (PASS, PREFROZEN_REUSE_GATE_PASS, static 119, 3 designs, 0 FreezeBuilder, physical 0, solver false, run dir unchanged). Recorded as an evidence-quality debt acceptable for signing; not a solve claim.
- D6 dry-run tool supersession: post_approval_dry_run_r10.py 1c6199bf/22,795 B (tools commit 5f1f74e) had a stale R9 package anchor (R10_PACKAGE_COMMIT=a4e9ded2) that would FAIL D27 against the real signed approval_refs.a2_package_commit=79e8f6a; A2 fixed exactly that 1 line in commit 0782b296 -> new tool bf283ec0/22,795 B, fake-signed selftest r10_post_approval_dry_run_selftest_20261111T184054Z.json 2cb377b1/1,649 B (46/46 PASS, failed []). All gate/launcher/dry-run anchors use the NEW tool SHA; the old SHA is superseded and must not be used.
- D7 launcher smoke filename tag r10_launcher_smoke_20261111T1909Z.json but internal utc field 2026-11-11T18:37:57Z; discrepancy is a local-time filename tag only, content governs; the file is committed in tools commit 5f1f74e and its bytes/SHA are bound.
- D8 definitional dry-run anomalies: package dry_run C10_executor_sha FAIL (Executor file-byte SHA vs JSON aggregate SHA comparison in p2a_v2.py, pre-existing R1-R9) and C16_window_requested / C19_a1_runtime_constructor NV (no pre-approval window request; A1 runtime constructor not importable in that harness). Non-blocking and unchanged in kind from every prior round.
- D9 R10 first main design15 f1 produced an all-NaN polar in R7 (7 rows NaN, LIFT_MATCH_FAILED); the R6 NaN mechanism remains unproven (H1/H2/H3). Under L-12 a single-case INVALID_NUMERICAL/void is tolerated and excluded from endpoints; automatic stop rules still apply (>25% invalid after >=48 main starts, >=6 consecutive invalid in one arm, or >64 cumulative invalid).
- D10 A5 physical_call_count=0 in this gate (independent replay used an in-memory FreezeRecordStore; no solver/OpenVSP/evaluator spawn). This G-P2AV2R10-PRE is NOT an execution authorization; Lead signature, real post-approval dry-run and A5 C-P2AV2R10-02 remain required before any GO.

## Mandatory signature corrections (M1-M6)

- M1: replace the 8 placeholder approval_refs with the 14-key refs_final in this gate; a5_review must be the commit SHA of this G-P2AV2R10-PRE gate; a2_package_commit=79e8f6a8133422c3865d99a841f8b68e8cc039d6; a2_execution_code=ed0f2324f91ffc649e9b8d997051d515ff7e248f027c46ba1c9125e2f575704c (99,591 B).
- M2: expand DRAFT conditions 15 -> exactly the 57 conditions in docs/reviews/dreal001_a5_p2av2r10_signature_conditions_20261111.json (byte-identical texts and order).
- M3: set status/approved/approved_by/approved_at_utc/authorization, window.status=APPROVED, and b2_waiver (APPROVED_BY_LEAD_FOR_THIS_BATCH_ONLY, approver, approved_at_utc, a5_pre_review_commit=gate commit).
- M4: amendment_log must remain byte-identical to the DRAFT (seq1-seq9 = R9 signed history; seq10 R10_INTERNAL_ACCOUNTING_FIX at the DRAFT at_utc 2026-11-11T18:32:44Z with physical_call_count_at_amendment=62).
- M5: no other binding or scientific-policy byte may change; A2 must commit the signed approval byte-identically (single-file byte commit), run the REAL post-approval dry-run with the bound NEW tool bf283ec0/22,795 B in this run dir, then A5 C-P2AV2R10-02, then Lead GO; C gate hard line 19:50Z.
- M6: R10 evidence debt accepted for signing: (i) P3 accounting smoke fa163ece (24/24, real main path, 6 arms, preflight 2/14 + diagnostics 0/0 + main 384/2688 = 386/2702 = 7x386, physical 0); (ii) launcher-side gate smoke 82df939b (79 checks, static 119, A1 guard all_equal, 6 triples, physical 0); (iii) no separate R10 executor-own gate smoke -> A5 independent zero-physical replay b6c14f09 covers the executor OWN _prefrozen_reuse_gate on final bytes ed0f2324 (PASS, 119, 3 designs, 0 builder); (iv) dry tool supersession 1c6199bf->bf283ec0 documented (D6); Lead must record this evidence-quality debt acceptance in the signed approval.

## Conditions (57)

- R3-BASE-01: A5 Q2=A sequential runtime freeze; approval binds policy+code+initial seeds only, not future designs.
- R3-BASE-02: Before any solver start for a design: A1 FreezeAPI arm-blind K=10 discovery + <=40 builds per target family -> two families frozen -> PRE SHA -> append-only record -> then start.
- R3-BASE-03: A1 evaluator MODE_RUNTIME must verify the design record exists and both family SHAs match; otherwise 0 start.
- R3-BASE-04: One freeze per design shared by all six arms; no recompute, no family picking, no overwrite.
- R3-BASE-05: Any unreachable family -> entire design VOID for every arm; no single-arm discard and no single-family primary.
- R3-BASE-06: End of run: final pair manifest + complete append-only log for A5 review.
- R3-BASE-07: Initial three LHS designs are zero-physical pre-frozen and exactly listed in the initial manifest.
- R3-BASE-08: If A1 cannot satisfy the runtime checks, fall back to B (split windows); A2 must not re-implement freeze.
- R3-BASE-09: The single canonical solver_attempts.jsonl writer is the A1 TwoFamilyEvaluator (event=start/end rows); A1 solver_ledger.SolverLedger is not invoked; A2 only reads/pairs by case_id and never writes a second schema.
- R3-BASE-10: No retry: any non-SOLVED result -> S2 stop; timeout is a charged start, no retry.
- R3-BASE-11: Single seed=42 descriptive only; no winner; no optimizer PASS; cross-family numeric comparison forbidden.
- R3-BASE-12: R3-BASE-12: A1 evaluator v1.2 real path is implemented and verified by the A1 probe v3 (10/10 SECURE, physical=0); no main-batch evaluation has completed a valid SOLVED_VALID family pair yet (R1-R9 preflights/setups/arm stops and the R6 main first-case ValueError; R7/R9 main design15 freeze stop).
- R3-BASE-13: Physical validation remains NOT_VALIDATED; fuel_burn_kg is null.
- R3-BASE-14: R3-BASE-14: This approval governs only batch_id DREAL001-P2-20261111-15 / run_id DREAL001-P2A2R10-20261111-01; the approved plan bytes and all bound identities must not change after signature; any byte change voids this approval (Lead-signed approval SHA binds plan/identity/executor).
- R3-BASE-15: R3-BASE-15: After signature A2 must run the post-approval dry-run in this run dir and report POST_APPROVAL_DRY_RUN_READY_NOT_RUN with approval_sha256/plan_sha256, 386 planned starts / 2702 planned internal / 451 max starts / 3157 max internal, diagnostics 0/0, and 0 physical call.
- R3-BASE-16: R3-BASE-16: Window: no solver start before 2026-11-11T18:30:00Z or after 2026-11-12T04:00:00Z; token WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z must be present both at approval top level and in approval.window.token.
- R3-BASE-17: R3-BASE-17: Physical starts are capped at 451 (386 planned: 2 B2 preflight + 384 main arm slots; 64 reserve; diagnostics are NOT in the R10 matrix and consume 0 starts) and internal solver cases at 3157 (2702 planned = 386 x 7; reserve internal exists outside planned); any count beyond requires new written Lead approval.
- R3-BASE-18: R3-BASE-18: Preflight runs first: only PRE-01 and PRE-02 replay cases are authorized; each bills exactly 1 start / 7 internal; any non-PASS_BYTE outcome stops the batch with 0 main starts. After preflight PASS the diagnostic phase is skipped per R10 matrix declaration (0/0, no solver spawn); the R9 diagnostics evidence is referenced, not re-run.
- R3-BASE-19: Per-design runtime freeze must precede any solver start for that design: A1 FreezeAPI K=10 arm-blind discovery, exactly two families, <=40 forced builds per family, PRE SHA verification, append-only hash-chained record; any failure voids the design for all six arms (0 start) and no single-family fallback is allowed.
- R3-BASE-20: B2 frozen-geometry waiver is approved only for this batch/run: frozen .vspgeom/.vkey bytes are batch-scoped, must be generated by the bound A1 builder/FreezeAPI, must never be reused from P1/P1C/P1R runs or across runs, and every start must re-verify the frozen SHA before spawn.
- R3-BASE-21: A5 must complete the post-execution independent audit of the ledger/batch summary/manifest before any result is reported as an optimizer outcome; A5 signs continuation/result only within its stated scope.
- R3-BASE-22: No optimizer ranking, no statistical significance claim, no winner, no fuel burn, no aerodynamic PASS, no 12D_ACTIVE validation, and no physical validation may be claimed from this single-seed descriptive batch; fuel_burn_kg remains null and physical_validation_status remains NOT_VALIDATED.
- R3-BASE-23: Preflight evaluator isolation: PRE-01 (design 8bd5a6c7c8311938, 543x472) and PRE-02 (design bc52a54ecefaac4c, 483x418) are distinct cells; each preflight case must use a fresh A1 TwoFamilyEvaluator instance with independent _seen_cells. PRE-03 is retired and must not run. Reusing one instance (DUPLICATE_DESIGN_FAMILY_CELL) or asking A1 to waive dedupe is not authorized.
- R3-BASE-24: Executor blob freeze: approval.a2_executor_sha256 must equal the SHA256 of p2a_v2_executor.py ({{A2_EXECUTOR_SHA256}}); executor_blob.a2 must list p2a_v2_common.py, p2a_v2_runtime.py, p2a_v2.py and p2a_v2_executor.py with the SHAs recorded at signature. Any A2 code change after signature voids this approval. The run command is: python -m research.concorde_metaopt.dreal001.optimizers.p2a_v2 run --out <run dir> --a1-root <A1 root>.
- R3-BASE-25: A1 code binding: evaluator_v12.py f74a4752495fd6c5330edcaf7edb4bcbe93f99c2a76bac06b5670d1f765ae20d, freeze_api.py 31d781821516bb80fc158238e4ef485c361afea674ca3b962efbb89d5a737173, a1_v1_2_code_sha 2a57632b3f7d5d567556d9774913ec40a5d72272, executable geometry commit 6753eb39b710035187db13ceb3328301c645c1ba (freeze path). The R1 2-case replay bundle (re-bound unchanged for R9) commit 2a57632b3f7d5d567556d9774913ec40a5d72272 with bundle_manifest 995bb12fff738d3ebb0bde08c0d5c5bfeb9532aebe536847ef307a2332013aa5 (2 cases PRE-01/02; PRE-03 retired) is immutable and must be SHA-verified before preflight.
- R3-BASE-26: Preflight PASS requires the actual polar SHA to equal approval.replay_bundles.cases polar SHA (PASS_BYTE). PASS_NUMERIC (7 rows max rel <= 1e-9, same mesh) is accepted only with prior written Lead and A5 acceptance; otherwise S1 stops the batch and the main matrix is NOT_RUN. A2 alone may not accept numeric equivalence.
- R3-BASE-27: Per-row backend must be explicit and non-inheritable: main-batch rows REAL_VSPAERO; preflight rows REPLAY_B2 with preflight=true. A3/A5 audit row-level backend evidence; run-level inheritance is not allowed.
- R3-BASE-28: This approval binds policy, code and initial seeds, not future designs. Every runtime design must be arm-blind frozen and appended to the hash-chained append-only log before any solver start for that design; final_run_manifest_required=true and the final manifest must be complete. A design may not be frozen or replaced after its first solver start.
- R3-BASE-29: A2 executes; A1 is read-only witness. Only the Lead may authorize continuation or results release; A5's result signature scope is limited to its stated audit scope.
- R3-BASE-30: Any deviation (protocol, retry, accounting mismatch, preflight failure, ledger gap, or design re-freeze) must stop the batch and be disclosed as an incident; no result may be reported as an optimizer outcome before A5's independent post-execution audit.
- R3-BASE-31: Execution protocol for the A1 single-writer ledger: exactly one canonical run_dir/solver_attempts.jsonl; exactly one evaluator instance alive at a time (each preflight case, then each main arm, constructed in scope and closed in finally; six evaluators must not be pre-constructed). The ledger must never be deleted, truncated or recreated; a stale lock is a fail-closed incident and must never be silently removed.
- R3-BASE-32: Per-arm evaluator max_starts is the arm budget (or the global remainder), never 451; A2 independently tracks global starts from the canonical ledger and stops at 451.
- R3-BASE-33: Case identity: every start/end pair is keyed by case_id, which must be non-empty and globally unique; start/end pairing and start counts are audited by case_id with event=start. attempt_id is informational only and may repeat across arms; A3/A5 must key on case_id.
- R3-BASE-34: Sref(x) must be resolved and validated (zero-physical, from x12) and written into the case record before evaluator.evaluate is called; an unresolved Sref means 0 starts and a fail-closed ExecutorRefused.
- R3-BASE-35: After an evaluator close and only with no live ledger writer, an orphan start may be repaired by appending an EXECUTOR_EXCEPTION end row (no refund); no end row may be fabricated without a recorded start; the normal path must never have A2 write the ledger directly.
- R3-BASE-36: Run end must call A1 build_final_run_manifest(..., allow_invalid=false); an invalid or refused final manifest is a failed batch with stop_report, never COMPLETED; batch_summary must record the final manifest SHA.
- R3-BASE-37: Before the first start, A2 must verify the initial_designs_manifest file SHA and its approval binding, and recompute design_hash from x12 for initial designs 15/16/17; any mismatch is fail-closed with zero starts.
- R3-BASE-38: R3-BASE-38: Internal solver cases must be derived per the PREREGISTERED policy constant 7 x physical solver starts actually performed (INTERNAL_PER_START_POLICY; not from the evaluator event ledger, no silent default); batch_summary must report phase starts/internal and fail closed as ACCOUNTING_INCONSISTENT on any sum(internal) != 7 x starts at a phase boundary or in the final summary.
- R3-BASE-39: If preflight fails, A2 must close the evaluator, repair orphan starts only after the writer is closed, recompute physical starts from the canonical ledger, write stop_report, and only then write batch_summary; no summary may report 0 physical while the ledger has unpaired starts.
- R1-HIST-01: R1-HIST-01: plan.json and P2A_V2_PREREGISTRATION.md may carry the task49 probe 9757bcf1.../status BOUND as HISTORICAL_TASK49_SNAPSHOT; it is not an active binding and must never be cited as A1 evaluator v1.2 evidence or in any post-run audit. The active A1 evidence remains the R1 signed approval-bound identity.a5_r1_probe_* (SHA 1264e9c0..., evaluator f74a4752..., overall SECURE, physical=0); the R10 identity need not restate a5_r1_probe_* and no R10 launch decision may depend on it; the R1-03 copy handoff carries forward (see R1-03). R1-R9 (R1 batch DREAL001-P2-20261111-06 / run DREAL001-P2A2R-20261111-01, plus R2-R9) are historical, read-only and excluded from E1-E6; their charged counts (R1-R4 2/14 each, R5 0/0, R6 3/21, R7 6/42, R8 0/0, R9 6/42 = 23 starts / 161 internal) remain included in the cumulative totals (prior 39/285 + 23/161 = pre-R10 actual 62 starts / 446 internal); R10 is planned at 386 starts / 2702 internal cases, so the cumulative becomes 448/3148 against caps 451/3157; R10 must not cite the task49 probe as active evidence. R1/R2/R3/R4/R5/R6/R7/R8/R9 runs are excluded from E1-E6; their preflight/diagnostic/main starts are counted in the cumulative caps.
- R1-02: R1-02: the p2a_v2_executor.py:6-7 docstring text "three REPLAY_B2 preflight cases" / "PRE-01 and PRE-03" is a stale comment; the actual preflight is exactly PRE-01/PRE-02 (p2a_v2_common.py:88-115) with no PRE-03. The comment does not change the execution contract; A2 patches it after this batch; the executor bytes must not be changed before signature except the approved execution-layer fixes: R3 status-literal fix (SOLVED_VALID), R5 x12 unit<->physical boundary fix, R7 observe design_hash fix + invalid-numerical tolerance + arm-exception persistence + DE/PSO population fix, R9 prefrozen flat-row read fix + diagnostic pair pre-registration + accounting pseudo-count fixes, R10 internal-accounting policy-constant derivation fix (all retained or added as declared in the R10 package and executed bytes {{A2_EXECUTOR_SHA256}}), and their unit tests. The launcher compatibility shim (R4 env shim/sitecustomize retained byte-identical, plus design-space preload) is a separate bound artifact and must be byte-frozen with the package; changes to it after signature void this approval.
- R1-03: R1-03: the R1 identity.a5_r1_probe_path points to the A5 worktree absolute path; its SHA256 1264e9c0... was verified at R1 signature. R10 identity may not carry this field, but A2 must still save a byte-identical copy of the A5 R1 probe in the R10 run dir or A2 docs/evidence before batch closeout and disclose it in the report; the A5 path remains provenance. This is not a launch blocker. The R10 launcher shim copy of the A5 R1 probe handoff remains required at batch closeout.
- R10-PKG-01: R10-PKG-01: The A5 G-P2AV2R10-PRE audit object is the A2 R10 package commit {{PKG_COMMIT}} (recorded by Lead as approval_refs.a2_package_commit) with the 8-file package (plan.json, approval.DRAFT.json, identity_binding.json, initial_designs_manifest.json, P2A_V2_PREREGISTRATION.md with R10 addendum, dry_run.json, executor_dry_run.json, SHA256SUMS.txt), the new executor/runtime/common/p2a_v2 bytes (executor {{A2_EXECUTOR_SHA256}}; runtime {{A2_RUNTIME_SHA256}}), and the R10 launcher/gate/smoke/dry-run tool set pinned to those bytes. The package must not contain R9 approval bytes, R9 plan SHA, or stale R9 window/token/run-id text as current identity; pre-execution run dir must contain exactly the 8 package files (no cases/ledger/approval.json/batch_summary/stop_report).
- R10-PREFROZEN-FLAT-01: R10-PREFROZEN-FLAT-01: The R9 prefrozen flat/nested read fix must be retained unchanged in R10 and must remain execution-layer only, with A1 bytes unchanged: (i) p2a_v2_runtime.py _reuse_prefrozen family frozen descriptor resolution accepts the initial_designs_manifest FLAT family row as well as the A1 family_pair_manifest nested "frozen" form, with explicit precedence and no silent fallback to a rebuild; (ii) p2a_v2_executor.py _prefrozen_reuse_gate mf resolution accepts the same FLAT row while the record side rf stays nested under record.families[label].frozen; any field missing, path absent, vkey/vsp3 sibling missing, or SHA mismatch must fail closed with zero starts; FreezeBuilder must never be invoked for the R10 initial designs, and a static-index hit not resolved via PREFROZEN_MANIFEST_REUSE must remain fail-closed (no rebuild).
- R10-INTERNAL-01: R10-INTERNAL-01: R10 internal_solver_cases must be derived from the PREREGISTERED policy constant 7 (fixed alpha rows) multiplied by the physical solver starts actually performed for that evaluation, with provenance tagged INTERNAL_PER_START_POLICY; the derivation must be uniform across preflight, main, evaluation rows, batch_summary phase counters and the final summary; it must not be inferred from the A1 ledger (which only audits physical starts/ends) and must not be silently defaulted (no hidden 7, no hidden 0). Preflight 2 starts -> 14 internal; main 384 starts -> 2688 internal; total 386 starts -> 2702 internal.
- R10-INTERNAL-02: R10-INTERNAL-02: R10 must fail closed with ACCOUNTING_INCONSISTENT (stop before the next phase; no retry) whenever sum(internal) != 7 x starts at a phase boundary or in the final summary, whenever charged+planned exceeds caps 451/3157, or whenever internal records disagree with the phase accounting; the failure must be reported with the concrete numbers, and no silent correction/backfill is permitted. A1 ledger consistency (starts/ends) remains separately checked.
- R10-INTERNAL-03: R10-INTERNAL-03: R10 P2: polar_sha256 must be recorded on each evaluation/attempt row when the polar file is available; where genuinely unavailable it must be null with an explicit disclosure. It may not be fabricated or inferred from other runs.
- R10-EXECGATE-01: R10-EXECGATE-01: Before any solver start, the executor OWN code path (p2a_v2_executor.py _prefrozen_reuse_gate, not only the launcher-side gate module) must be executed zero-physically on the REAL R10 initial_designs_manifest (3 designs x 2 families) and must PASS with static_index_count=119, no FreezeBuilder invocation, physical_call_count=0, solver_started=false, and no cases/ledger written; the evidence JSON (path/SHA256/bytes) must be in the R10 package and A5 must independently replay the same code path with physical=0 before signing G-P2AV2R10-PRE. The launcher-side prefrozen gate and the executor-side gate must be shown equivalent on the same manifest.
- R10-EXECGATE-02: R10-EXECGATE-02: R10 P3 zero-physical smoke must exercise the REAL executor main-path accounting chain (not a helper unit test): a fake/recorded solver drives at least one preflight evaluation and at least one main evaluation through the same code path used in the live run, proving internal=7 x starts on every evaluation/record row, phase-boundary conservation, final summary conservation, physical_call_count=0, solver_started=false, and no cases/ledger written. The smoke evidence (path/SHA256/bytes) must be in the R10 package and independently re-checked by A5.
- R10-ACCT-01: R10-ACCT-01: Accounting baseline is 62 starts / 446 internal (prior 39/285 + R1 2/14 + R2 2/14 + R3 2/14 + R4 2/14 + R5 0/0 + R6 3/21 + R7 6/42 + R8 0/0 setup stop + R9 6/42 stage stop), and the R9 stage stop is charged 6 starts / 42 internal and permanently excluded. R10 planned is 386 starts / 2702 internal (2 preflight + 384 main arm slots; diagnostics NOT re-run; 64 reserve), so the projected cumulative is 448 starts / 3148 internal against caps 451 / 3157 (headroom 3 starts / 9 internal). Any R10 charge beyond the approved figures requires a new written Lead approval; charged+planned>caps must fail closed (ACCOUNTING_INCONSISTENT). No retry and no extra diagnostic start are permitted.
- R10-DIAG-01: R10-DIAG-01: R10 does not re-run diagnostics (plan matrix diagnostic_starts=0, diagnostic designs=0). The R9 diagnostics DIAG-01 design16 eb00b7ad545243e6 (SOLVED_VALID, primary 0.01289480742004768) and DIAG-02 design17 dc96d2438a6dddc3 (SOLVED_VALID, primary 0.021752395563484656) are referenced only as prior feasibility evidence with their evidence SHAs (preflight_result cf25c130/5,771; batch_summary 038feee3/19,285; stop_report 19f7a502/830) and are excluded from R10 endpoints.
- R10-HIST-01: R10-HIST-01: R1, R2, R3, R4, R5, R6, R7, R8 and R9 are historical and permanently excluded from E1-E6 and from any optimizer/physics result; their run dirs, signed approvals, evidence files and SHA256SUMS are READ-ONLY and must not be modified, re-signed, re-used as approval basis, or relabelled as gate PASS. R9 (batch DREAL001-P2-20261111-14 / run DREAL001-P2A2R9-20261111-01) is an S1 stage stop (status STOP_DIAGNOSTICS_ACCOUNTING_INCONSISTENT, main NOT_RUN, 6 starts/42 internal physical, internal records 0 due to report-layer defect) and is excluded in full; its 165-file run dir is read-only and its evidence is append-only. R1-R9 charged counts remain in the cumulative caps: R1-R4 2/14 each, R5 0/0, R6 3/21, R7 6/42, R8 0/0, R9 6/42; total 62 starts/446 internal. R8 approval fa0d94a2.../75,166 B and R9 approval b502b484.../76,257 B are superseded and non-reusable.
- R10-WINDOW-01: R10-WINDOW-01: The valid R10 execution window is 2026-11-11T18:30:00Z to 2026-11-12T04:00:00Z with token WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z present both at approval top level and in approval.window.token; no solver start outside the window; the launcher and executor window gate must fail closed on a missing/late/expired token; no window extension may be granted by anyone other than the Lead in writing and re-signed.
- R10-DECISION-01: R10-DECISION-01: Lead decision trail: L-10 authorized R8; R8 attempt-1 stopped in setup with 0 physical; A5 FAIL-08 upheld; Lead m02945 authorized R9 as last attempt (seq9, no R10 by default); R9 stopped at the diagnostics accounting boundary 18:02:45Z (starts=4 internal=0 planned=4/28) with main NOT_RUN, charged 6/42; A5 FAIL-09 (commit 859008d) independently upheld the stop and corrected the attribution (default-7 removal and conservation check entered in R8 P3, not R9); Lead L-12 (docs/reviews/dreal001_lead_decision_r10_internal_accounting_20261111.md, commit 1b5728a) accepts the R9 stop, excludes R9, and authorizes R10 as the LAST execution attempt (no R11; main failure or accounting inconsistency ends the series with an incident receipt). Protocol D remains in force (invalid-numerical tolerance, no mesh QC data gate); no winner/significance/cross-family comparison; fuel_burn_kg null; physical NOT_VALIDATED. A5 position: conditionally accepts R10 as the final attempt under R10 conditions, records that this is the 9th consecutive execution-layer defect with headroom only 3/9, and states that a further R10 execution-layer failure ends the series NOT_RUN/NOT_COMPUTABLE without R11.
- R10-REFS-01: R10-REFS-01: The Lead-signed approval must carry the corrected 14-key approval_refs (no DRAFT placeholders): a1_bundle_commit = a1_bundle_commit_full = 2a57632b3f7d5d567556d9774913ec40a5d72272, a1_bundle_manifest_sha256 = 995bb12fff738d3ebb0bde08c0d5c5bfeb9532aebe536847ef307a2332013aa5, a1_bundle_path = D:\RCAIDE\dnext001\wt-real-a1-geometry-solver\research\concorde_metaopt\dreal001\geometry\replay_bundles\P2A_V2_PREFLIGHT_20261111_R1, a1_bundle_note, a1_executable_commit = a1_task49_commit = 6753eb39b710035187db13ceb3328301c645c1ba, a1_execution_code = 6979802, a1_execution_code_note, a1_execution_head = a1_head = 2a57632b3f7d5d567556d9774913ec40a5d72272, a2_execution_code = {{A2_EXECUTOR_SHA256}}, a2_package_commit = {{PKG_COMMIT}}, a5_review = A5 G-P2AV2R10-PRE review commit SHA (this gate commit). Any placeholder or R9 approval SHA in these keys voids the signature.
- R10-SIGN-01: R10-SIGN-01: The signature must expand approval.conditions from the DRAFT to this 57-item R10 set (39 R3-BASE items retained; R1-HIST-01/R1-02/R1-03 adapted; R10-PKG-01/PREFROZEN-FLAT-01/INTERNAL-01/INTERNAL-02/INTERNAL-03/EXECGATE-01/EXECGATE-02/ACCT-01/DIAG-01/HIST-01/WINDOW-01/DECISION-01/REFS-01/SIGN-01/DISC-01), and must apply M1-M6: 14-key refs, 57 conditions byte-identical to docs/reviews/dreal001_a5_p2av2r10_signature_conditions_20261111.json, status/approved/approved_by/approved_at_utc/authorization + window.status=APPROVED + b2_waiver, amendment_log byte-identical to DRAFT (seq1-9 = R9 signed history; seq10 = R10_INTERNAL_ACCOUNTING_FIX at DRAFT at_utc with physical_call_count_at_amendment=62), no other binding/scientific-policy byte change; A2 commits the signed approval byte-identically and runs the real R10 post-approval dry-run with the bound R10 tool (386 planned/0 emitted/2702 internal/physical 0), then A5 C-P2AV2R10-02, then Lead GO; C gate hard line 2026-11-11T19:50:00Z.
- R10-DISC-01: R10-DISC-01 (non-blocking disclosures that must appear in the A5 gate and final receipt): (a) R1-R9 series exclusion: charged 23 starts/161 internal (R1-R4 2/14 each, R5 0/0, R6 3/21, R7 6/42, R8 0/0, R9 6/42), cumulative baseline 62/446; R10 plan 386/2702, projected cumulative 448/3148 vs caps 451/3157, headroom only 3 starts/9 internal; (b) R9 stage stop: preflight 2/2 PASS_BYTE, diagnostics 4 starts/28 planned both SOLVED_VALID, then DIAGNOSTICS_ACCOUNTING_INCONSISTENT (starts=4 internal=0 planned=4/28) with main NOT_RUN, 6 starts/42 internal physical, no retry/timeout/NaN stop; (c) the internal-accounting defect is a report-layer field-mapping defect (A1 RUNTIME record has no internal_solver_cases; executor read 0; conservation check then failed) first introduced in R8 P3 and first triggered in R9; (d) R10 fixes it by deriving internal from the preregistered policy constant with fail-closed conservation and by a zero-physical main-path accounting smoke; (e) design15 f1 prefrozen bytes produced an all-NaN polar in R6 so an R10 main INVALID_NUMERICAL remains possible under protocol D; R6 NaN mechanism NOT proven and no mesh QC data gate adopted (L-09 rejection retained); (f) C10_executor_sha remains a definitional false negative in package dry_run.json (executor file SHA vs aggregate digest), non-blocking; (g) A5 physical_call_count=0 and solver_started=false; this gate is not an execution authorization and no R11 exists by default.

## A5 statement

A5 independent review: package 79e8f6a, tools 5f1f74e, dry-tool fix 0782b296, launcher 476481e6/29,361 B, executor ed0f2324/99,591 B. 53 PASS + 4 PASS_WITH_DISCLOSURE of 57 checks; 0 FAIL. R10 P1 accounting policy verified in code and by the real-main-path zero-physical smoke (386/2702=7x386, cumulative 448/3148). R10 P4 diagnostics not-in-matrix dual-source gate verified (0/0, no spawn); R9 diagnostics referenced only. The executor OWN prefrozen reuse gate was replayed zero-physically by A5 on the final executor bytes (b6c14f09, PASS). R9 stage stop independently upheld (FAIL-09). This gate is NOT an execution authorization. A5 physical_call_count=0.
