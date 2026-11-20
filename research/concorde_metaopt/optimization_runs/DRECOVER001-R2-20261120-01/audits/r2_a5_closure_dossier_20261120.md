# R2 A5 closure review dossier (2026-11-20)

Reviewer role: A5 independent read-only reviewer. No tools. This dossier is the only input. Do not treat any local audit as human authentication. Return only the requested JSON verdict.

## 1. Identity, authorization and boundary

- Owner authorization: message ref `m05968`; authorization `AUTH-DRECOVER001-R2-20261120-01`; run `DRECOVER001-R2-20261120-01`; batch `DRECOVER001-R2-20261120-01-B01`.
- Budget: 24 physical solver starts, 128 internal cases per start, timeout 1200 s, retries 0, parallel 1, MAML training runs max 8. Charged before this review: **3 starts / 23 internal cases / 0 retries; 21 starts remain**. No solver start has occurred since the A5 verdict below.
- Physical scope: real VSPAERO 3.55 / VSPAERO v.7.2.2 at fixed altitude 18,288 m, fixed geometry contract `5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15`, fixed lift target 1,333,704.4 N. Labels remain `LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`; local audit is a separate script, not human or A5.
- Same-machine backup is the only backup; Owner waiver `WAIVER-OFFMACHINE-BACKUP-20261118` waives the off-machine failure domain. It is not an independent backup.

## 2. Original A5 verdict and conditions

- Verdict `CHANGES_REQUIRED`; pilot disposition `RATIFIED_WITH_CONDITIONS`; reviewed `2026-11-20T06:50:06Z`; model `deepseek-flash`; human signature false.
- Original findings: pilot before A5; uncommitted code / no full preflight; Ew=inf scope; flow_conditions default equivalence; NOT_AUTHENTICATED labels / same-machine backup; limited MAML power.

## 3. Condition closure evidence

- **C1_PILOT_EXCEPTION — CLOSED**. 3 pilot starts charged; A5 verdict CHANGES_REQUIRED with pilot RATIFIED_WITH_CONDITIONS recorded; no further starts until closure review.
- **C2_CODE_FREEZE_AND_FULL_PREFLIGHT — CLOSED**. freeze_id R2FREEZE-6bdfe74e7f41b664 binds 19 files; pushed remote commit 2273024eeb5eae634b11fcebcee16376c82e409e (parent 0effd7628774c8ee61468627c7af446b21591705); full preflight DRECOVER001-SOFTWARE-20261120T065735Z ran 248 tests, 0 failures/errors/skipped, PASS. Targeted pytest PermissionError was a sandbox temp ACL issue; preflight unittest path passed; --basetemp workaround documented.
- **C3_EW_INF_SCOPE — CLOSED**. Only Ew with math.isinf is removed from nonfinite; Ew NaN and every other nonfinite payload still raise ContractError. Regression test test_infinite_ew_diagnostic_tolerated_but_nan_or_core_inf_fatal; 18 admission tests passed.
- **C4_FLOW_CONDITIONS — CLOSED**. Default vs explicit baseline flow: same vspgeom SHA and same deck Sref/Mach/AoA/ReCref/Vinf/Rho; verdict DEFAULT_PATH_EQUIVALENT. 14 matrix decks, 168 checks, 0 failures; q/CL recomputed from deck Rho/Vinf.
- **C5_PILOT_ADMISSIONS — CLOSED**. 2/2 successful pilot cases have admission certificates; baseline-coarse remains NULL_LABEL (POLAR_HAS_INVALID_ROWS). All certificates are LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED.
- **C6_MAML_AFTER_ADMISSIONS — PENDING**. MAML has not started. Matrix labels must be admitted case-by-case; failed cases stay null; results labeled exploratory with no generalization claim; same-machine backup limitation disclosed.

## 4. Code freeze and full preflight

- Freeze `R2FREEZE-6bdfe74e7f41b664` binds 19 files (source, scripts, authorization, pilot and A5 evidence).
- Remote commit `2273024eeb5eae634b11fcebcee16376c82e409e`, tree `cdcaa9663e87678b6db308cfe7333a09ef9f811e`, parent `0effd7628774c8ee61468627c7af446b21591705`, branch `recovery/drecover001-20261117`; worktree clean at that commit. The three changed source files and the first A5 dossier are in that commit.
- Full zero-physical preflight `DRECOVER001-SOFTWARE-20261120T065735Z`: **248 tests, 0 failures, 0 errors, 0 skipped, status PASS**; physical_solver_starts_actual=0, real_meta_training_executed=false, admitted_scientific_labels=0. Checkpoint `0211bc97e73418722d60e45c3eb2dd812686cc17cc412f99168b227f0dc7b155`.
- Targeted pytest earlier hit `PermissionError: [WinError 5]` in the sandbox temp directory, not assertion failures. The full preflight uses the project unittest path and passed; `--basetemp` is the documented workaround.

## 5. Pilot starts and admission status

- 3 charged starts: `baseline-coarse` (7 alpha, exit 0, `POLAR_HAS_INVALID_ROWS` because alpha=0 has E=-nan(ind)/Ew=-nan(ind)); `baseline-refine-01` (13 alpha, SOLVED); `baseline-admit-01` (3 alpha, SOLVED).
- Admitted certificates: baseline-admit-01 `di_n=121434.35218570218`, alpha 5.18125; baseline-refine-01 `di_n=121492.55215765651`, alpha 5.1825, lift relative error 0.00022375442687054152. baseline-coarse is **NULL_LABEL**, not admitted.
- All certificates are `LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`; the audit role is `SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5`.

## 6. Ew=inf scope proof

`research/concorde_metaopt/dreal001/meta/raw_verification.py:144-160` removes a nonfinite value only when `key == "Ew" and math.isinf(value)`. `Ew` is a diagnostic drag column; it is not used in `D_i_N=q*Sref*CDi`. `Ew=NaN` is not removed, and every other nonfinite column (including CLtot/CDtot/CDi) still raises `ContractError("nonfinite polar row")`. Regression test `test_infinite_ew_diagnostic_tolerated_but_nan_or_core_inf_fatal` is at `research/concorde_metaopt/tests/test_recovery_real_admission.py:214`; the admission test file reports 18 passed. The pilot certificates were produced from rows whose CL/CDi are finite.

## 7. flow_conditions default equivalence and per-case q/CL

- Default vs explicit baseline flow: same `.vspgeom` SHA `f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34`; deck Sref/Mach/AoA/ReCref/Vinf/Rho rows identical; q=20483.940233430174; CL=0.18174391741992046; verdict `DEFAULT_PATH_EQUIVALENT`.
- 14 matrix input decks were verified independently: **168 checks, 0 failures**, including Sref/Mach/Vinf/Rho/ReCref/q/CL/plan SHA/alpha count.
- Below, q and CL are recomputed as `q=0.5*rho*Vinf^2` and `CL=L_ref/(q*Sref)` from each task_spec. Maximum relative q deviation from the stored dynamic pressure: 1.776e-16; maximum relative CL deviation from stored cl_target: 1.542e-16. Every case has 15 alpha points.
| case | task | split/part | Mach | Vinf m/s | q Pa | CL target | alpha c | plan sha (12) |
|---|---|---|---|---|---|---|---|---|
| m160-d00-support | concorde-real-M160 | train/support | 1.60 | 472.108829 | 12851.408440 | 0.289682765875 | 8.319597608 | 34aa215e8461 |
| m160-d01-support | concorde-real-M160 | train/support | 1.60 | 472.108829 | 12851.408440 | 0.286814619678 | 8.236207375 | be0c3136958c |
| m160-d02-query | concorde-real-M160 | train/query | 1.60 | 472.108829 | 12851.408440 | 0.289682765875 | 8.319597608 | 3b2fe2883174 |
| m180-d00-support | concorde-real-M180 | train/support | 1.80 | 531.122433 | 16265.063807 | 0.228885148346 | 6.551930565 | ba80125be4e1 |
| m180-d01-support | concorde-real-M180 | train/support | 1.80 | 531.122433 | 16265.063807 | 0.226618958758 | 6.486041986 | bf26e261a5f2 |
| m180-d02-query | concorde-real-M180 | train/query | 1.80 | 531.122433 | 16265.063807 | 0.228885148346 | 6.551930565 | b68b7da3e82e |
| m202-d01-support | concorde-fixed-cruise-dreal001-real-v1 | train/support | 2.02 | 596.037397 | 20483.940233 | 0.179944472693 | 5.128999488 | ae012f43da4a |
| m202-d02-query | concorde-fixed-cruise-dreal001-real-v1 | train/query | 2.02 | 596.037397 | 20483.940233 | 0.181743917420 | 5.181317643 | 9a29e828bd9e |
| m220-d00-support | concorde-real-M220 | val/support | 2.20 | 649.149641 | 24297.194081 | 0.153220636496 | 4.352014363 | 54c13e631042 |
| m220-d01-support | concorde-real-M220 | val/support | 2.20 | 649.149641 | 24297.194081 | 0.151703600491 | 4.307907132 | d5f52b9cae33 |
| m220-d02-query | concorde-real-M220 | val/query | 2.20 | 649.149641 | 24297.194081 | 0.153220636496 | 4.352014363 | 51fbd54622ae |
| m240-d00-support | concorde-real-M240 | test/support | 2.40 | 708.163244 | 28915.668989 | 0.128747895944 | 3.640478966 | b7834f39a3e7 |
| m240-d01-support | concorde-real-M240 | test/support | 2.40 | 708.163244 | 28915.668989 | 0.127473164301 | 3.603416640 | da939584586f |
| m240-d02-query | concorde-real-M240 | test/query | 2.40 | 708.163244 | 28915.668989 | 0.128747895944 | 3.640478966 | f598d71c00b5 |

Task family: M1.60 `concorde-real-M160` train; M1.80 `concorde-real-M180` train; M2.02 `concorde-fixed-cruise-dreal001-real-v1` train (d00 already admitted in pilot; matrix adds d01/d02); M2.20 `concorde-real-M220` val; M2.40 `concorde-real-M240` test. d00/d01 are support, d02 is query. Designs: d00 baseline X12; d01 W01=361.8325; d02 sweep_1=67.5.

## 8. MAML plan and limitations

- MAML starts only after every successful matrix case has an admission certificate; failed cases stay null labels. No label will be synthesized or interpolated.
- Design: 3 train tasks, K=2 support designs per task, 1 query design, FOMAML and pooled-pretrain comparison; exploratory only, no generalization claim. Same-machine backup limitation is recorded. A5 is not a human signature.

## 9. Requested decision

Decide whether conditions C1–C5 are satisfied and whether it is admissible to (a) run the 14 matrix cases (14 more starts, total 17/24; 15 internal cases each) and (b) run the exploratory real-label FOMAML/K-shot experiment after case-by-case admission. Return `PASS` only if both are admissible under the stated limits; otherwise `CHANGES_REQUIRED` with exact remaining actions.

## 10. Integrity anchors

- `r2_code_freeze.json`: 5186 bytes, sha256 `dcfd8f430407014d1caafe2f0fffe02bb6ab515ce62d2db7208ce861133e2b22`
- `r2_gate_record.json`: 5217 bytes, sha256 `e1f300bb24bb2d4e7ea58f61767aac2cbf69879c4abc8d3e301ee15b58b1fb86`
- `pilot_ledger.json`: 3155 bytes, sha256 `af77faac03df79a04797d494a24af1e3cde8365c2d9c82d7c7844538642118ff`
- `pilot_label_status.json`: 2055 bytes, sha256 `f4ac668b1360c2ccb4916f1b00a06d093d341baa26059c8503e19a082a7b8691`
- `matrix_input_verification.json`: 9204 bytes, sha256 `6551dce4ad2055d7fb40db52d9a25813dadb8ef21534becfcfb387754d37d9cb`
- `flow verification.json`: 3479 bytes, sha256 `a2570bcf5b9fb70661ecd55da9e0da403d5ed7432e7d8faa5d0ab50dc94de155`
- `preflight receipt`: 7639 bytes, sha256 `33fe78aa8728ac2114b0813e47e761b4144772fb462e4e2eb0e3be1ff566dd65`
- `original A5 verdict`: 3537 bytes, sha256 `c47ee91fd9c63d335941d0d5cca22c197c0072a5772926fce54e64179678c1b4`
