# A1 M0-R Interface Freeze (zero physics)

- freeze_id: A1-M0R-INTERFACE-FREEZE-20261113
- source_commit: 0c514151d989de716dbb855973b900a34615b5aa (branch research/dreal001-a1-geometry-solver, not pushed)
- authorization: DFIXED-F1R2-001; Lead L-30 / L-30-A01 / L-31
- A5 gate: G-T0-ADMISSION-01 M0_BLOCKED / PHYSICAL_TASK_FAMILY_BLOCKED (commit 24ccdb5)

## Frozen files (SHA256 / bytes)

- task_evaluator.py: e88c21775d753c555b1ba8d5076c45d5c3fc956be8c2daf8eb194e73ec777261 / 63459 B
- tests/test_task_evaluator.py: 290485ce262cccec8792e26f67ff9c92c6dc3688ac18c9f308d58cb91c1ffb1c / 32417 B
- tests/conftest.py: 53a678b494f6802a267e987645103364abd8969ed76db711f1ead605c3464b39 / 1024 B
- interface.md: 6ef6b16e181f404ee6219db27a9125769b78d5368de653ec791c2aa21a4e790b / 16925 B
- dry_run.json: 8688d25770911af7fadd42587f66a4914091c829fd8cdc89c1f349a53731b4c6 / 43587 B
- u1_geometry_rebind.json: d90f2ed5ca3031be6500e4b7a4167253f4aa03828438af1e137b703164ab0e8e / 33508 B
- pytest.log: 3c8f15fadd1ec0cbbc9dd80f85e2aa7ab21b5435ab7e40aa4e2ebaf593862712 / 104 B
- SHA256SUMS: 3ca22ec983f4c7f60360075564cf93d255fbcce2156181f0cdbdff07d4f5d302 / 948 B

## A2 call entry

- module: research.concorde_metaopt.dreal001.m1.task_evaluator (Python 3.11)
- build_task_spec -> derive_task_deck -> validate_task_deck -> analyze_polar -> classify_failure -> build_evaluation_record
- A2 supplies the A2 accounting_ledger object; A1 only wraps it with A2LedgerHooks. A1 does not import/rewrite A2 bytes.
- EvaluationRecord schema: dreal001.m1_evaluation_record.v1

## Six task specs (ATM-F1R2, 18,288 m)

- T18K_M202_CL017: Mach 2.02, CL_target 0.170, q=20483.9402334302 Pa, L_ref=1247523.17006648 N, mass=127.211960258 t, split=meta_train
- T18K_M202_CL019: Mach 2.02, CL_target 0.190, q=20483.9402334302 Pa, L_ref=1394290.60183901 N, mass=142.17807323 t, split=meta_train
- T18K_M220_CL017: Mach 2.20, CL_target 0.170, q=24297.1940814141 Pa, L_ref=1479759.86254332 N, mass=150.893512315 t, split=meta_train
- T18K_M220_CL019: Mach 2.20, CL_target 0.190, q=24297.1940814141 Pa, L_ref=1653849.25813665 N, mass=168.645690234 t, split=meta_val
- T18K_M180_CL017: Mach 1.80, CL_target 0.170, q=16265.0638065665 Pa, L_ref=990583.048479414 N, mass=101.011359484 t, split=meta_test
- T18K_M180_CL019: Mach 1.80, CL_target 0.190, q=16265.0638065665 Pa, L_ref=1107122.23065346 N, mass=112.895048835 t, split=meta_test

## 18 deck table (design x task)

| design | task | deck SHA256 | bytes | vspgeom SHA256 | Sref m2 | q Pa |
|---|---|---|---|---|---|---|
| B0-01 | T18K_M202_CL017 | 1614a964fc729d42 | 943 | 16da482a1f8e59f6 | 358.25 | 20483.9402334302 |
| B0-01 | T18K_M202_CL019 | 1614a964fc729d42 | 943 | 16da482a1f8e59f6 | 358.25 | 20483.9402334302 |
| B0-01 | T18K_M220_CL017 | 6a022882fa5b9e4c | 957 | 16da482a1f8e59f6 | 358.25 | 24297.1940814141 |
| B0-01 | T18K_M220_CL019 | 6a022882fa5b9e4c | 957 | 16da482a1f8e59f6 | 358.25 | 24297.1940814141 |
| B0-01 | T18K_M180_CL017 | 9e755cddfb730d4c | 942 | 16da482a1f8e59f6 | 358.25 | 16265.0638065665 |
| B0-01 | T18K_M180_CL019 | 9e755cddfb730d4c | 942 | 16da482a1f8e59f6 | 358.25 | 16265.0638065665 |
| B1-01 | T18K_M202_CL017 | 1614a964fc729d42 | 943 | 6a296aee6e6f6b50 | 358.25 | 20483.9402334302 |
| B1-01 | T18K_M202_CL019 | 1614a964fc729d42 | 943 | 6a296aee6e6f6b50 | 358.25 | 20483.9402334302 |
| B1-01 | T18K_M220_CL017 | 6a022882fa5b9e4c | 957 | 6a296aee6e6f6b50 | 358.25 | 24297.1940814141 |
| B1-01 | T18K_M220_CL019 | 6a022882fa5b9e4c | 957 | 6a296aee6e6f6b50 | 358.25 | 24297.1940814141 |
| B1-01 | T18K_M180_CL017 | 9e755cddfb730d4c | 942 | 6a296aee6e6f6b50 | 358.25 | 16265.0638065665 |
| B1-01 | T18K_M180_CL019 | 9e755cddfb730d4c | 942 | 6a296aee6e6f6b50 | 358.25 | 16265.0638065665 |
| C5 | T18K_M202_CL017 | 1253fa5f2c0f8be4 | 931 | e1ad74cc3820553e | 370.25 | 20483.9402334302 |
| C5 | T18K_M202_CL019 | 1253fa5f2c0f8be4 | 931 | e1ad74cc3820553e | 370.25 | 20483.9402334302 |
| C5 | T18K_M220_CL017 | d5d9104e19304a20 | 945 | e1ad74cc3820553e | 370.25 | 24297.1940814141 |
| C5 | T18K_M220_CL019 | d5d9104e19304a20 | 945 | e1ad74cc3820553e | 370.25 | 24297.1940814141 |
| C5 | T18K_M180_CL017 | a1619d691a148252 | 930 | e1ad74cc3820553e | 370.25 | 16265.0638065665 |
| C5 | T18K_M180_CL019 | a1619d691a148252 | 930 | e1ad74cc3820553e | 370.25 | 16265.0638065665 |

## Build / solver accounting

- 4 real OpenVSP in-process builds (B0-01 twice for 2/2 byte identity, B1-01, C5); OpenVSPComputeGeometry only, StopBeforeRun=1.
- VSPAERO solver starts = 0; spawn_events = []; solver_started = false; physical_call_count = 0; no run dir created.
- SHA 16da482a baseline vspgeom / 225,414 B / 546x480; 40fdd436 retired (227,247 B / 543x472); 58f63bfc is P1-05 (199,997 B / 483x418), not 40fdd436.

## R-gate self-check

- R02_post_fix_geometry: PASS
- R03_task_capable_executor: PASS
- R05_R23_lref_sref_q: PASS
- R07_C01_C04_cross_constraints: NOT_A1_SCOPE (M1 sampler/executor enforces)
- R08_alpha_and_independent_residual: PASS
- R22_R24_per_task_deck_and_shared_geometry: PASS
- R25_f1r2_continuity: PASS_WITH_DISCLOSURE

## A3/A5 statements

- U2 dry-run builds are real OpenVSP in-process builds (OpenVSPComputeGeometry), not VSPAERO solver starts; solver_started=false, spawn_events=[], physical_call_count=0.
- R07 C01-C04 cross constraints are enforced by the M1 sampler/executor (A3 M0-R package + A2 runner), not by the A1 interface.

## Open items

- task_id values are A1 temporary IDs; A3 must preserve task_fingerprint numeric inputs if renaming and record the mapping in the M1 package.
- M1-A admission baseline case matrix is not fixed here; Lead/A5 pre-review determines it.
- Real M1 execution requires A5 pre-review and Lead written GO; this freeze is zero physics.
- F1R2/F2R2 frozen packages and run directories were not modified.

## Verification

- pytest: 27 passed, 0 failed (log SHA 3c8f15fadd1ec0cbbc9dd80f85e2aa7ab21b5435ab7e40aa4e2ebaf593862712 / 104 B).
- dry-run: PASS checks=50 failed=0 decks=18 physical=0 spawn=[].
