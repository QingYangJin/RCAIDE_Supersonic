# 恢复门禁就绪矩阵（离线聚合）

- status: RECOVERY_READINESS_GATES_CLOSED_EXPECTED
- generated_utc: 2026-11-18T06:37:42Z
- HEAD: 4c51c7df34c9626999ef2e66e5a6c76a2b9c92e2 (recovery/drecover001-20261117)
- software_run_id: DRECOVER001-SOFTWARE-20261118T062546Z
- physical_solver_starts_actual: 0 / internal_solver_cases_actual: 0
- real_meta_training_executed: false / admitted_real_labels: 0

| gate | state | blockers | violations |
| --- | --- | --- | --- |
| R0_INVENTORY | CLOSED | 1 | 0 |
| R1_SOFTWARE | CLOSED | 2 | 0 |
| M1_BATCH_CONTROL_PATH | CLOSED | 1 | 0 |
| M2_OFFLINE_REHEARSAL | CLOSED | 1 | 0 |
| BACKUP_INDEPENDENT_FAILURE_DOMAIN | WAIVED | 1 | 0 |
| A5_INDEPENDENT_REVIEW | CLOSED | 1 | 0 |
| REAL_ADMISSION | CLOSED | 1 | 0 |
| EVIDENCE_MANIFEST | CLEAN | 0 | 0 |

## 阻断项
- A5 review performed by deepseek-flash subagent (not a human signature): verdict='CHANGES_REQUIRED'; R2/M1 physics is not authorized by this review
- Independent A5 review is a recorded deepseek-flash subagent verdict (not a human signature); no human/Owner sign-off exists
- Independent actual 6-terra inventory review is NOT_STARTED; gate remains unsigned
- Independent failure-domain backup is waived by the Owner (m03569); the same-host restore is not an off-machine backup
- Owner waived the off-machine failure-domain backup (WAIVER-OFFMACHINE-BACKUP-20261118); same-host restore is still not an off-machine backup and backup_restore_pass remains false
- R0 independent audit, R1 audit, independent backup, and A5 admission signature are all absent
- Real M1 label batch requires a new A5 gate and a Lead batch GO; none issued
- Rehearsal is offline-only; M2 real training awaits real admitted labels

## 说明
Offline evidence aggregation only. No solver start, no network, no new physical evidence, no A5 signature. A CLOSED gate is expected and is not a PASS.
