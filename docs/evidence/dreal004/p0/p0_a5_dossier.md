# P0 A5 dossier - Issue #14 D-REAL-EXP-002

Independent review request. This dossier describes P0 only (code, zero-physical
replay, 12D response audit, A2 endpoint analyzer, protocol freeze). It grants no
new physics and no P1 authorisation.

## 1. Identity

- Issue: QingYangJin/RCAIDE_Supersonic#14 (D-REAL-EXP-002, 2026-11-21)
- Branch: `research/dreal004-alpha-adaptive-meta-sampling`
- Base commit: `af9871cd2b16a083c228ac2ecbced4c0344012a0` (previous stage snapshot `409f09c8`)
- Current authorization: P0 code/protocol/zero-physical only
- Physical solver starts this round: 0; internal solver cases: 0; labels created: 0
- Solver identity (for later phases, not invoked): vspaero-3.55.0-v7.2.2-omp1, omp 1, no retries

## 2. Code delivered (SHA256)

| file | sha256 |
|---|---|
| `research/concorde_metaopt/dreal001/geometry/adaptive_alpha.py` | `8442da15459aa6da9d0b717daf0a419f4478cafabc22b578c4d599441cbaf738` |
| `research/concorde_metaopt/dreal001/geometry/polar_rows.py` | `bc590fb4e3ef2881f1f03464c00364d88dad17b50e9463320b29d6aeb21beeaf` |
| `research/concorde_metaopt/dreal001/meta/endpoint_analysis.py` | `e20ad62493c912408bcdc72ff46155f072dc84908e2fa43530aa6191ad91438c` |
| `research/concorde_metaopt/tests/test_adaptive_alpha.py` | `5b63425eeeda96dcdbae7f641592373e5114f3f17905adeb8664242d69b53272` |
| `research/concorde_metaopt/tests/test_polar_rows.py` | `428e1551704c81042ca0b36dc4584d2835488c2ab3ec92459af242454d5ae3c5` |
| `research/concorde_metaopt/tests/test_endpoint_analysis.py` | `4553d5bc360cd11532a175235ada70a074f63fa863fc1979aca498312579ee96` |
| `docs/evidence/dreal004/p0/a1_replay_g1.py` | `1cafd9ab0f564bef5de2ac420075f38149684fc886bdb6c584dcfa1f542a585f` |
| `docs/evidence/dreal004/p0/a1_variable_response_audit.py` | `5a7b11b14c16d06a7654643068d3311a954397a990f461427d7effa587dfb34d` |
| `docs/evidence/dreal004/p0/a2_g1_baseline_endpoints.py` | `dfb65dce987868ded750f3766b4b07a9a638cd46cae397f03314d4d30078481c` |
| `docs/evidence/dreal004/p0/g1_alpha_replay.json` | `165a32616a57b4084b907e9f9c88d7784913664af0db49fb02c8803a11aa04b4` |
| `docs/evidence/dreal004/p0/12d_variable_response_audit.json` | `5e4aa7ceb7c76ea7480f17383bdb74ece0a140cb931130383a42a6e43092759b` |
| `docs/evidence/dreal004/p0/a2_g1_baseline_endpoints.json` | `2e73717d703bf8bc163640884c3b2063b8fc5b366c3d95af96a25bf68e675c08` |

### A1 AdaptiveAlphaSolver contract

- Injected evaluator only: no solver path is embedded; every probe increments one
  internal alpha case; the caller owns real solver starts.
- Statuses: RAW_POINT_MATCHED, INTERPOLATED_TARGET_ESTIMATE, NO_BRACKET,
  NO_CONVERGENCE, INVALID_POLAR, SOLVER_FAILED, BUDGET_EXHAUSTED.
- Refinement: secant interpolation constrained inside the bracket; no extrapolation;
  a target that only exists as an interpolated estimate is never reported as a raw hit.
- `replay_on_existing_rows` can only query existing raw polar rows; a missing row
  returns `REPLAY_ROW_NOT_AVAILABLE` instead of inventing data.
- `polar_rows.read_polar_rows` parses Beta/Mach/AoA/CLtot/CDo/CDi/CDtot by header
  lookup and rejects files with no table header or no matching rows.

## 3. Test evidence (zero physical)

- Command: python docs/evidence/dreal004/p0/run_p0_tests.py
- Modules: the 17 recovery preflight modules plus `test_adaptive_alpha`,
  `test_polar_rows`, `test_endpoint_analysis`.
- Result: 280 tests, failures 0, errors 0, skipped 0, successful=True
- Log: docs/evidence/dreal004/p0/p0_test_log.txt sha256 `dfe20629ddcf3c73df5eb4da3f0bfa9cc5661bf8bfa351d6cf8b2259096dc6f5`
- Summary: p0_test_summary.json sha256 `ae52d064f1fdf9e3b5723c7ffbc8aa83102be44d98d18618964e41ad7a2f74e8`
- The destructive run_recovery_preflight.py was intentionally not executed in this
  branch; it would rewrite recovery receipts and is unrelated to P0 code review.

## 4. G1 zero-physical replay (Issue #14 requirement)

- Source: the 24 recorded G1 case directories (raw .polar files) and their
  task_spec.json targets; no solver was started.
- Result statuses: `{"MISSING_INPUT": 1, "NO_BRACKET_ON_EXISTING_ROWS": 8, "REPLAY_RAW_HIT_ON_EXISTING_ROW": 8, "REQUIRES_NEW_ALPHA_ROWS": 7}`
- Fixed-sweep internal cases recorded in G1: 391; adaptive replay probes: 329
- physical_solver_starts_used=0, labels_created=0
- Interpretation: 8 raw hits are exactly the 8 G1 admitted labels; 7 cases already
  bracket the target on existing rows and need only new alpha rows in P1; 8 cases have
  no bracket (6 of them Mach 1.6) and need a wider alpha range or separate diagnosis.
- Outputs: g1_alpha_replay.json sha256 `165a32616a57b4084b907e9f9c88d7784913664af0db49fb02c8803a11aa04b4`, .csv sha256 `66e80dfaf7ab45229e32f97d3de1ed92659dc33eb9fba963696cb76ed248010a`

## 5. 12D variable response audit

- Static wiring: True of 15 named variables change the VSPAERO model inputs.
- Dynamic: 56 response pairs measured on existing G2 stage1 raw cases; every pair has
  a different deck SHA256 (see the JSON evidence).
- V01 (vertical_tail_area +2%): all 8 tasks show delta CDi = 0.0 exactly; mean delta
  CDo = +1.4274743502551002e-05; mean |delta CLtot| = 9.98187295918259e-07. Cause: beta=0 means the
  vertical tail is unloaded, so it only adds parasite drag; the primary endpoint
  Di_N=q*Sref*CDi does not move. V01/V02 therefore remain in the geometry contract but
  are passive dimensions for this task family; P2/P3 must not claim their 12D response.
- V02 (vertical_tail_sweep_delta): no existing perturbed raw case; status
  RESPONSE_PENDING_P1_PROBE - no inference was made.
- Outputs: 12d_variable_response_audit.json sha256 `5e4aa7ceb7c76ea7480f17383bdb74ece0a140cb931130383a42a6e43092759b`, .csv sha256 `014cf6b48d8741667413983d9d0e60c3f711368d6699a3d87e0b7525e8cc97c7`

## 6. A2 endpoint analyzer and G1 baseline

- endpoint_analysis.py implements N_first_feasible, best_feasible_Di_N(B), anytime
  curve, point/run feasible hit rate, simple_regret (null without an independent
  reference), cost_to_target; records are validated as real and feed no synthetic
  values; infeasible records may not carry di_n.
- G1 baseline replay (descriptive, not a new sampler run): first feasible at design
  evaluation 10 / 170 internal cases; point feasible hit rate 8/24=0.3333;
  3.0 design starts and 48.875 internal cases per admitted label.
- Consistency: replayed internal cases 391 vs G1 batch accounting 391 (matches=True).
- Output: a2_g1_baseline_endpoints.json sha256 `2e73717d703bf8bc163640884c3b2063b8fc5b366c3d95af96a25bf68e675c08`

## 7. Frozen protocol

- Task split frozen: train M140/M160/M200/M202, val M180/M220, test M240/M260;
  support d00-d03, query d04-d07, 8 unique designs per task.
- P1 (NOT authorised): Mach 2.02, designs d00/d01/d04/d07, <=12 design starts,
  <=3 starts per design, <=36 internal alpha cases, tol_CL=1e-3 unchanged.
- P2 (NOT authorised): <=240 new starts, >=4 real admitted labels per train task,
  FOMAML/pretrain/context-pretrain/random arms, negative transfer reported.
- P3 (NOT authorised): <=384 new starts, paired sampler comparison at equal cost,
  B=4/8/16/32/64/128 anytime curves.
- Primary endpoints, fairness, statistics and forbidden practices are frozen in
  p1_p2_p3_preregistration.json sha256 `21d36ce1a58d64f08aefc958926b997ef28baa20d6972789a2710108584af1dd`
- Chinese protocol summary: p0_protocol_freeze_20261122.md sha256 `9a96c0d8530c4fe66d7edb8bb1260889cb046cf2aca017ea4b969bfbf8a04f70`

## 8. Prior-state truth (not re-graded)

- G1 is unchanged: 24 starts, 8 admitted labels, 34.78% valid rate; no label is
  rewritten and tol_CL is not relaxed.
- G2 was halted under Issue #14: B01 24 starts / 4 labels, B02 78 starts / 26 labels,
  total 102/240 charged starts, 30 labels, no G2 receipt issued.
- No real MAML training was run for G2 and none is authorised here.

## 9. Disclosures / limitations

- A5 reviews in this project are deepseek-flash single-shot read-only; this is not a
  human signature and does not replace Owner sign-off.
- P0 evidence is same-host; the off-machine backup requirement is waived by Owner
  (m03569) and this dossier does not claim an independent failure domain.
- P0 does not admit any new real raw data; RealAdmissionManifest fail-closed behaviour
  is unchanged (REAL_ADMISSION_NOT_IMPLEMENTED without certificates).
- Mach 1.6 has zero G1 labels and 6 no-bracket replay cases; its inclusion in P2
  training is conditional on new admitted labels.
- No independent Di_N reference exists yet, so simple_regret stays null.

## 10. Requested gate verdicts

- P0_CODE_PASS - code files above, 280 tests green.
- P0_ZERO_PHYSICAL_REPLAY_PASS - G1 replay with 0 solver starts, 0 labels.
- P0_12D_RESPONSE_AUDIT_PASS - 15 wired, V01 zero-CDi mechanism explained,
  V02 left explicitly pending.
- P0_A2_ENDPOINT_ANALYZER_PASS - endpoints implemented and consistent with G1 ledger.
- P0_PROTOCOL_FREEZE_PASS - split/endpoints/fairness/statistics frozen.
- P0_ZERO_PHYSICAL - no solver process was started in this round.

This dossier does not authorise P1. If the verdict is P0_CODE_AND_PROTOCOL_PASS,
the Lead must still issue a separate P1 GO after a dedicated P1 batch-plan review.
