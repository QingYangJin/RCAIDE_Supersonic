# R2 A5 repair-batch amendment dossier (2026-11-20)

Status: DRAFT_FOR_A5_REVIEW / NOT_APPROVED / NO_NEW_STARTS_YET

## 1. Why this dossier exists

The R2 closure review (verdict PASS, 2026-11-20T07:07:37Z) authorized at most 14 matrix solver starts. All 14 were consumed. 13 completed; 1 (`m240-d01-support`) was killed by the outer tool timeout after its start event and remains a counted null-label start. Only one new matrix label is admissible: `m202-d01-support`, relative lift error 3.38e-6. The remaining 12 completed matrix cases do not contain any polar row inside the 1e-3 relative lift tolerance, so they cannot be admitted and currently carry no label.

Root cause is a calibration error in the matrix input builder, not a solver failure. `scripts/build_task_case.py` used a refinement grid (15 alphas, step 0.0025 deg, total span 0.035 deg) centered with the M2.02 baseline lift slope 0.03439427 per deg. At Mach 1.6/1.8/2.2/2.4 the supersonic lift slope differs; the target lift row is outside the 0.035-deg window. The completed raw polars themselves show the required alpha shifts (all from actual rows, not interpolation):

| case | sampled alpha (deg) | actual CL | target CL | local slope /deg | linear estimate | quadratic estimate |
|---|---:|---:|---:|---:|---:|---:|
| m160-d00-support | 8.3371 | 0.321612 | 0.289683 | 0.036623 | 7.4653 | 7.5207 |
| m160-d02-query | 8.3371 | 0.317979 | 0.289683 | 0.036210 | 7.5556 | 7.5632 |
| m180-d00-support | 6.5694 | 0.242662 | 0.228885 | 0.035781 | 6.1844 | 6.1951 |
| m180-d02-query | 6.5694 | 0.241919 | 0.228885 | 0.035671 | 6.2040 | 6.2062 |
| m202-d02-query | 5.1988 | 0.176822 | 0.181744 | 0.033346 | 5.3464 | 5.3448 |
| m240-d00-support | 3.6580 | 0.106365 | 0.128748 | 0.028797 | 4.4352 | 4.4377 |
| m240-d02-query | 3.6580 | 0.106626 | 0.128748 | 0.028867 | 4.4243 | 4.4339 |

The fix is to use a wider, still exact-row grid: 61 alphas at 0.005 deg spacing (span 0.30 deg) centered on the quadratic/linear estimate. At the observed slopes the half-spacing is at most 9.2e-5 CL (m160), below the 0.1% relative tolerance for every task (m240 half-spacing 7.2e-5 CL against 1.29e-4 tolerance). No interpolation or post-hoc lift target is used: admission still requires an actual polar row meeting `|q*Sref*CL - L_ref|/L_ref <= 1e-3`.

## 2. Budget state before the requested repair

- Authorization: `AUTH-DRECOVER001-R2-20261120-01`, owner message `m05968`, window end `2026-11-20T18:44:39Z`.
- Physical starts used: 17 / 24 (pilot 3 + matrix 14). Remaining: 7.
- Matrix starts used: 14 / 14 in the closure condition.
- Retries: 0. Parallelism: 1. All starts used `vspaero-3.55.0-v7.2.2-omp1`.
- Admitted new matrix label: `m202-d01-support`, admission `ADM-R2-MATRIX-M202-D01-SUPPORT`, di_n 120203.9250481344, alpha 5.1289994884, cl 0.179945080054, cdi 0.016218010459.
- Existing admitted pilot labels: baseline d00 support (two raw runs, same design; only one usable dataset row) and baseline d01 support.

## 3. Requested repair sub-batch B01R (7 starts, exactly the remaining budget)

One start per case, 61 alphas, step 0.005 deg, max_starts=1, retries=0, parallel=1, timeout 1200 s, same solver and authorization window. New case ids; old null cases are not overwritten. These seven starts are a named amendment to the 14-matrix-start condition; if PASS, the verdict authorizes only these seven cases and no other starts. MAML training runs are CPU software runs, not VSPAERO starts, and do not consume the 24-start physical budget.

| new case | task_id | split | partition | design | alpha center (deg) | alphas |
|---|---|---|---|---:|---:|---:|
| m160-d00-support-r1 | concorde-real-M160 | train | support | d00 | 7.49 | 61 |
| m160-d02-query-r1 | concorde-real-M160 | train | query | d02 | 7.56 | 61 |
| m180-d00-support-r1 | concorde-real-M180 | val | support | d00 | 6.20 | 61 |
| m180-d02-query-r1 | concorde-real-M180 | val | query | d02 | 6.20 | 61 |
| m202-d02-query-r1 | concorde-fixed-cruise-dreal001-real-v1 | train | query | d02 | 5.345 | 61 |
| m240-d00-support-r1 | concorde-real-M240 | test | support | d00 | 4.44 | 61 |
| m240-d02-query-r1 | concorde-real-M240 | test | query | d02 | 4.43 | 61 |

Why this set: it completes two train tasks (M2.02, M1.6), one val task (M1.8), one test task (M2.4), each with at least one support and one query design. M2.02 already has d00/d01 admitted support and needs only d02 query; M1.6, M1.8, M2.4 need d00 support + d02 query. Total physical starts after repair = 24 / 24. No new design or task is invented.

Protocol deviation disclosed: the earlier plan said K=2; the remaining budget supports K=1 for M1.6/M1.8/M2.4 (M2.02 keeps two support designs). We request approval for K=1 exploratory MAML, or explicit rejection. We will not run MAML if fewer than two train tasks and one val/test task are admitted.

## 4. Gate conditions requested

1. Only the seven case ids above may start; any further start is prohibited.
2. Any repair case without an actual row inside 1e-3 is recorded NULL_LABEL and is not rerun.
3. If fewer than two train tasks plus one val and one test task are admitted, stop before MAML and report the null labels.
4. All admitted labels keep `LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`; audit is a separate local script, not a human and not A5.
5. Same-host backup is disclosed; off-machine backup remains waived by `WAIVER-OFFMACHINE-BACKUP-20261118`.
6. MAML is exploratory, max 8 training runs, no generalization claim; it starts only after all admissions above.

## 5. Decision requested

Return PASS only if the seven repair starts and the K=1 deviation are admissible under the original 24-start budget. Otherwise return REJECT or CHANGES_REQUIRED with the specific condition. No start will occur before this review is recorded.
