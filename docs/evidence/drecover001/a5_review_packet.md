# A5 独立审查包（只读聚合）

- 生成时间（UTC）：2026-11-18T06:37:42Z
- 范围：READ_ONLY_EVIDENCE_AGGREGATION_FOR_INDEPENDENT_A5_REVIEW
- 软件 run_id：DRECOVER001-SOFTWARE-20261118T062546Z
- 离线测试：230 项，失败 0，错误 0，跳过 0
- 物理求解器启动：0；内部求解案例：0；真实元训练：false；真实标签：0
- 异机备份：Owner 已豁免（m03569），只做同机恢复；同机恢复标注为非异机备份，backup_restore_pass 仍为 false。
- 本包记录一次 A5 审查：deepseek-flash，verdict=CHANGES_REQUIRED，非人类签名，不授予物理 GO。

## 门禁状态

- R0_INVENTORY: CLOSED
- R1_SOFTWARE: CLOSED
- M1_BATCH_CONTROL_PATH: CLOSED
- M2_OFFLINE_REHEARSAL: CLOSED
- BACKUP_INDEPENDENT_FAILURE_DOMAIN: WAIVED
- A5_INDEPENDENT_REVIEW: CLOSED
- REAL_ADMISSION: CLOSED
- EVIDENCE_MANIFEST: CLEAN

## 可复核证据（逐文件 SHA256）

- docs/evidence/drecover001/recovery_inventory.json（18205 字节）：65df586e7067f20767ff6419d6d00bb2a769df780ad1b2c41be92ac409aa4a43 — R0 loss ledger and provenance inventory
- docs/evidence/drecover001/recovery_inventory.md（20930 字节）：43dc411bb4d303bc7db478883c851045504809ee8a6f084f38111b2dc9bc8bae — R0 human-readable inventory
- docs/evidence/drecover001/all_ref_blob_audit.json（6308435 字节）：ad8222e8965c5a5fa3834f29b4309ff7cea71d71729100f245d29984e10a1613 — R0 remote-ref byte/blob audit
- docs/evidence/drecover001/reachable_history_audit.json（1309494 字节）：ba8f65fd5f1bc4f6eebe980dad3992b853360acf9b01ebf508c79d49f001d6dc — R0 reachable-history audit
- docs/evidence/drecover001/r0_provenance_extension.json（330839 字节）：b553857c5ce986e9fbfd7f6fa6de37d7aca42af9ade61075db6e17e87c524c37 — R0 provenance extension records
- docs/evidence/drecover001/r0_provenance_extension_20261117.md（6794 字节）：bdf7380e4d0c9368b3128d51b52de652ea21bf06a7d2d107edc674914d54327f — R0 provenance extension summary
- docs/evidence/drecover001/r0_provenance_extension_verification.json（81117 字节）：73b99833c7f86c5ef317dc21ca83a3ae0537170384309c6d1dbf07af7dbcb3b5 — R0 archived-byte self-verification
- docs/evidence/drecover001/needed_for_next_run.json（19663 字节）：edceccd8d1be1e54fa064f0c747fd3fb7d18220018172d2f071107dc8395c0f6 — R0/R1/R2 handoff requirements
- docs/evidence/drecover001/recovery_preflight_receipt.json（7358 字节）：cff5cc1f4d3ed81e1f9164a0b877c2bf441d0f27f11f86eccf497c5e793b1e39 — R1 software preflight receipt
- docs/evidence/drecover001/synthetic_software_training_trace.json（6327 字节）：290dccc5bc06cd80b445d2bb8c2a36460a1c944eb2a5cf632680f1ffa74fbd65 — R1 fixture training trace
- docs/evidence/drecover001/synthetic_software_checkpoint.json（9081 字节）：0211bc97e73418722d60e45c3eb2dd812686cc17cc412f99168b227f0dc7b155 — R1 fixture checkpoint roundtrip artifact
- docs/evidence/drecover001/m1_batch_software_rehearsal_receipt.json（3468 字节）：526d337ae54fb6849fc6822f032560b3c9a3a21ba39395a5c18594f1479ab7f5 — M1 control-path rehearsal receipt
- docs/evidence/drecover001/m1_batch_software_result.json（12411 字节）：63ee7a6a868f5f1b9abda6a55480e1e72068a6ec4ee9f7fdc075a3e4df96fac8 — M1 control-path result
- docs/evidence/drecover001/m1_batch_software_verification.json（1785 字节）：e0e678b2c24ded6056e1dc63ec02858d215b4c31ba251f8424584c3dcf657d15 — M1 artifact verification
- docs/evidence/drecover001/m2_offline_rehearsal_receipt.json（33973 字节）：232551c3a7eb996d7b9edf0fe156d2e3fd6e23d1db574c6e7e4a0cd46dadc0bc — M2 offline rehearsal receipt
- docs/evidence/drecover001/m2_rehearsal_repeat_check.json（1862 字节）：8f6ad3e69462f1b3c16970f7cd9194de50b17352e3d540ef251e1c50e9c64c10 — M2 repeatability check
- docs/evidence/drecover001/local_restore_receipt.json（2099 字节）：6f82dd68db850b693d3ab6e59d5bf251736046f4b8bd2b34d813c247bd223cde — same-host restore test explicitly labelled not an off-machine backup
- docs/evidence/drecover001/owner_waiver_offmachine_backup_20261118.json（839 字节）：b9edcaae932060bc684972427d34b6f3247e1dc6cade83a599e7d25c8ac0bb68 — Owner waiver of the off-machine failure-domain backup
- docs/evidence/drecover001/a5_review_verdict.json（3551 字节）：e6cfc666c0491b281e0a3c7c621b6de7529d41470ea8f257420d19e5fe9af7df — A5 verdict from the authorized deepseek-flash subagent (not a human signature)
- docs/evidence/drecover001/a5_review_transcript.json（155516 字节）：71e08f219ae7c3759f1a20714ccd037138897afed99ecfd5904986c10d943deb — Read-only A5 inspection transcript (16 tool steps before HTTP 524)
- docs/evidence/drecover001/issue12_consolidated_receipt_draft_20261117.md（10259 字节）：5c98d20cfbb4d1f6b92c695ad7702aa0db4614fa5c7a0c8f814eb07a8521f3b6 — Issue #12 receipt draft (not posted)
- docs/evidence/drecover001/maml_readiness_20261117.md（10287 字节）：69bfbdfbfb55fc70cc45fac514fa51509cf74ee751a075cf6352bc5919831e56 — MAML offline readiness summary

## 已记录的 A5 审查

- [major] None × None：Same-host restore receipt lacks the owner-required 'not-an-off-machine-backup' label.
- [major] None × None：Packet reports BACKUP_INDEPENDENT_FAILURE_DOMAIN CLOSED, conflicting with owner waiver; should be WAIVED_BY_OWNER.
- [minor] None × None：R0 inventory is R0_PARTIAL_NOT_AUDITED, so R0 should pass only with disclosure.
- [info] None × None：REAL_ADMISSION remains fail-closed; no R2 preregistration or Lead batch GO is shown, so physics is not authorized.

## 待外部签署的门禁

- A5_INDEPENDENT_REVIEW（CLOSED）：A deepseek-flash subagent performed a read-only review and recorded a verdict (not a human signature). Owner acceptance of that verdict is still external; the Lead must not upgrade it to a human sign-off.
- BACKUP_INDEPENDENT_FAILURE_DOMAIN（WAIVED）：WAIVED by Owner (m03569): only a same-host restore is required. The same-host restore is still not an off-machine backup; backup_restore_pass stays false and the receipt must keep the explicit label.
- REAL_ADMISSION（CLOSED）：Implement and independently audit raw parsing, signed manifests, task-deck binding and gate checks; this is intentionally blocked now.
- R2_BATCH_GO（NOT_ISSUED）：After the above, A5 and Lead must pre-register a new batch with new ids, budget, stop conditions and approval; no physical run is authorized by this packet.

## 已知限制

- A CLOSED gate is expected and is not a PASS.
- The off-machine failure-domain backup is WAIVED by the Owner (m03569); the same-host restore receipt is explicitly labelled SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP and backup_restore_pass remains false. WAIVED is not a PASS.
- The A5 review was performed by a deepseek-flash subagent with read-only tools; it is not a human signature and does not by itself authorize physical runs. It returned CHANGES_REQUIRED, and the Lead must close or disclose each finding.
- Two files named real_openvsp_geometry_probe.json exist: docs/evidence/drecover001/real_openvsp_geometry_probe.json is the pre-repair SURFACE_DIAGNOSTIC_FAIL snapshot; the authoritative post-repair record is docs/evidence/drecover001/a1_thickness_repair/real_openvsp_geometry_probe.json (SURFACE_DIAGNOSTIC_PASS_NOT_FREEZE). Neither is a solver freeze or physics validation.
- research/concorde_metaopt/dreal001/meta/m2_rehearsal.py hardcodes three native_probe_status PASS strings into its geometry contract; the rehearsal therefore asserts, rather than reads, those probe statuses.
- needed_for_next_run.json had a truncated R1 requirement tail; it is valid JSON now but the lost tail is marked UNKNOWN and is not evidence.
- The evidence tree is uncommitted: no git author identity is configured and github.com is unreachable from this host.
- Some R0 report claims are REPORT_PRESENT only; raw identity is not established for all historical numbers.
- The M1 run uses a structural placeholder authorization and simulated starts.
- The readiness matrix is regenerated evidence; this packet quotes its status but intentionally does not embed its file hash.
- run_recovery_preflight.py is deliberately excluded from the non-destructive reproduction list: it assigns a new run_id and overwrites the preflight receipt, trace and checkpoint hashed here. Rerun the suite only inside a restored copy of the bundle, never in this frozen evidence tree.

## 复核步骤（非破坏性）

    D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/assess_recovery_readiness.py
    D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/verify_r0_provenance_extension.py
    D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/verify_m1_batch_evidence.py
    D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/build_a5_review_packet.py --check

## A5 检查清单

- [ ] Confirm every evidence_index hash against the bytes on disk.
- [ ] Confirm physical/internal counters are 0 and no admitted real labels exist.
- [ ] Confirm the R0 inventory still says R0_PARTIAL_NOT_AUDITED and keeps RAW_LOST items raw-lost.
- [ ] Confirm R1 changes do not overwrite historical raw data or S1/S2/S3 negative results.
- [ ] Confirm REAL_ADMISSION remains fail-closed and no placeholder is presented as a real GO.
- [ ] Confirm the destructive preflight was NOT run in this tree and every evidence_index hash still matches on disk.
- [ ] Record an explicit verdict: APPROVE_FOR_R2, REJECT, or CHANGES_REQUIRED, with scope and date.

## 请求的 A5 结论

APPROVE_FOR_R2、REJECT 或 CHANGES_REQUIRED，并写明范围与日期。Lead 不自签。
