# A5 G-P2AV2R8-PRE 包门禁（R8 / 预冻结复用）

- gate：G-P2AV2R8-PRE；时间：2026-11-11T16:59:50Z；作者：a5-review（A5）
- 对象：A2 R8 包 commit d926972d10208c44d172e5a19008d7f45bf68300（8 文件；预执行 run dir 无 cases/ledger/approval.json）
- verdict：PASS_WITH_MANDATORY_SIGNATURE_CORRECTIONS（60/60 checks PASS，0 FAIL）
- A5 physical_call_count=0；solver_started=false；本门禁不是执行授权。

## 1. 包文件实测（A5 独立）

| 文件 | bytes | SHA256 |
|---|---|---|
| plan.json | 46783 | 0a14c8f068a7452a5f7a9a67f3e393a32dbc6c26678877908e34c076d6e6b009 |
| approval.DRAFT.json | 49592 | 1bcadf407061e65352f7f054132651e639c677b19ce59bae25a71a61a58e09c5 |
| identity_binding.json | 10445 | cc2118ded1b43632a59240e3a0bef583279a365f612f2c8748fc408f9b16398a |
| initial_designs_manifest.json | 14822 | cba91f17e2be4edd8ab125f9795ce3c83fa99b2f8daa49bdd9a3da9adbc1d3a8 |
| P2A_V2_PREREGISTRATION.md | 19343 | 2b18d66c456e7a0039e3e186d09a5eeb177eef3b476a95a143a9e9150c7c1e51 |
| dry_run.json | 10930 | dc991c736134c1e9ad73fccdc20dc0b57b995b8fb429377e247d43a50e99b8a3 |
| executor_dry_run.json | 2438 | c1c658f04d8c468dcdb5135461d32121577a6e5b6741413efbb2d17a389f25d2 |
| SHA256SUMS.txt | 612 | 1f73158aa8ca59ec76596b3f5cc89b68f089b9c04ea93cc4c9d0e9a6bde79dd9 |

disk == commit blob：8/8 identical；SHA256SUMS 7/7 重算匹配。

## 2. 身份与绑定

- batch/run：DREAL001-P2-20261111-13 / DREAL001-P2A2R8-20261111-01
- window：2026-11-11T16:30:00Z - 2026-11-12T04:00:00Z；token WINDOW_OK-P2AV2R8-20261111T1630Z-20261112T0400Z；start deadline 2026-11-11T21:00:00Z；clean 2026-11-12T02:30:00Z；hard 2026-11-12T04:00:00Z
- planned 390 / 2,730；max 451 / 3,157；reserve 64；cumulative 446 / 3,134（prior 56/404）
- A1：evaluator f74a4752495f… / freeze_api 31d781821516… / openvsp_model c40b11df29e9… / design_space 8f9b893c1319… + config 8b29d1e3833e… / bundle 995bb12fff73…（未变）
- A2 executor：ff3f5639211306276712302e561f2ff931d702396db625eeb96112e6807d3d20 / 92286 B；common 1c857b48f2fa… / runtime 0dfe53cc85ff… / p2a_v2.py f2e524a3dc69…
- launcher：d1e8b6f647e4724d48af81a4e20de55ab4f7de0174061e7f582f35eeccf4dc46 / 29320 B；smoke：3dd759a1581ec374457fac2c2a6773626bc0bb6079e19d7dbd6359691e537a1c（SMOKE_NO_SOLVER）
- static_index_count=119；pair_manifest 55e63f39…；headroom 5 starts / 23 internal。

## 3. Pre-frozen 复用独立复核（R8 核心）

- manifest 字段事实：family frozen 块只有 frozen_vspgeom_path + frozen_vspgeom_sha256/bytes + frozen_vkey_sha256 + frozen_vsp3_sha256 + vspgeom_sha256 + canonical_mesh_sha256；无 frozen_vkey_path/frozen_vsp3_path；vkey/vsp3 为 frozen_vspgeom_path 同目录 sibling model.vkey/model.vsp3；vsp3 缺失 fail-closed。
- 复用前必须实算 vspgeom/vkey/vsp3 SHA 与 manifest 相等，A1 describe_mesh canonical = manifest canonical；runtime 记录 source_kind=PREFROZEN_MANIFEST_REUSE、reused_prefrozen=true、attempts=0；不得调用 FreezeBuilder；A1 冻结字节零改动。
- 零物理 prestart gate：static_index_count=119、3 designs×2 families 复用记录校验、任一 mismatch/missing vsp3 拒绝启动（无 solver/无 ledger）、gate 证据 SHA 写入 prestart 并报 A5。
- 记账修复：starts==0 → internal 0（去默认 7）；batch_summary 分 phase+total；diagnostics polar_sha256 提取；charged+planned ≤ caps 断言 fail-closed。
- 诊断预注册：DIAG-01 design16 eb00b7ad545243e6 / DIAG-02 design17 dc96d2438a6dddc3，各 2 families = 2 starts/14 internal，合计 4 starts/28 internal；R7 的 2/14 计数缺陷已披露。
- 无网格 QC 数据门（L-09 否决 option B）；R6 NaN 机制未证明。

## 4. 门禁检查（60 项）

| ID | 检查项 | 期望 | 实测 | 判定 |
|---|---|---|---|---|
| C01 | A2 R8 package commit resolves and contains the 8 package files | 8 files in commit | d926972d10208c44d172e5a19008d7f45bf68300 resolved; 8 files | PASS |
| C02 | disk bytes == commit blobs for all 8 package files | identical | identical (git diff --exit-code empty) | PASS |
| C03 | plan.json bytes/SHA | == recorded | 46783 / 0a14c8f068a7452a5f7a9a67f3e393a32dbc6c26678877908e34c076d6e6b009 | PASS |
| C04 | approval.DRAFT.json bytes/SHA | == recorded | 49592 / 1bcadf407061e65352f7f054132651e639c677b19ce59bae25a71a61a58e09c5 | PASS |
| C05 | identity_binding.json file SHA and canonical identity_sha256 | consistent | cc2118ded1b43632a59240e3a0bef583279a365f612f2c8748fc408f9b16398a / canonical 75c9c8916c59e7bd290d6fe6a0f6470d5766e77988d1a26a433c9e0fde104dd9 | PASS |
| C06 | initial_designs_manifest.json SHA and 3 initial designs | d51866f7 / eb00b7ad / dc96d243 | cba91f17e2be4edd8ab125f9795ce3c83fa99b2f8daa49bdd9a3da9adbc1d3a8 | PASS |
| C07 | P2A_V2_PREREGISTRATION.md SHA and R8 protocol section | == recorded / R8 prefrozen + 4/28 diagnostics present | 2b18d66c456e7a0039e3e186d09a5eeb177eef3b476a95a143a9e9150c7c1e51 | PASS |
| C08 | dry_run.json and executor_dry_run.json SHAs | == recorded | dc991c736134c1e9ad73fccdc20dc0b57b995b8fb429377e247d43a50e99b8a3 / c1c658f04d8c468dcdb5135461d32121577a6e5b6741413efbb2d17a389f25d2 | PASS |
| C09 | SHA256SUMS.txt self-consistency | 7/7 recomputed match | 1f73158aa8ca59ec76596b3f5cc89b68f089b9c04ea93cc4c9d0e9a6bde79dd9 (0/7 PASS) | PASS |
| C10 | package dry_run non-PASS checks triage | C10 definitional FAIL; C16/C19 NV | [] (known false negative, disclosed) | PASS |
| C11 | executor dry-run | 390 planned / 0 emitted / 2730 internal / physical 0 / failed [] | DRY_RUN_BLOCKED_NOT_APPROVED 390/0 physical undefined | PASS |
| C12 | run dir pre-execution has no execution artifacts | no cases/ledger/evaluations/approval.json/batch_summary/stop_report | 8 package files only | PASS |
| C13 | DRAFT identity fields | batch 13 / run R8 / window 16:30Z-11-12T04:00Z / token / planned 390-2730 / caps 451-3157 | batch 13 / run R8 / {"window":{"start_utc":"2026-11-11T16:30:00Z","end_utc":"2026-11-12T04:00:00Z","token":"WINDOW_OK-P2AV2R8-20261111T1630Z-20261112T0400Z","status":"REQUESTED_NOT_SIGNED"},"planned":[390,2730],"caps":[451,3157]} | PASS |
| C14 | DRAFT supersedes R7 approval | 1a552267.../69,405 B/physical 56 | {"approval_path":"D:\\RCAIDE\\dnext001\\wt-real-a2-optimizers\\research\\concorde_metaopt\\dreal001\\runs\\DREAL001-P2A2R7-20261111-01\\approval.json","sha256":"1a552267ab0070ee4f690815ed1de1db6d5976c1ada8356421f017bb84d72e37","bytes":69405,"run_id":"DREAL001-P2A2R7-20261111-01","physical_call_count_at_supersede":56,"superseded_at_utc":"2026-11-11T16:38:34Z","reason":"R7 is preserved read-only and | PASS |
| C15 | amendment_log seq1-seq7 equals R7 signed approval; seq8 present | identical / R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX physical 56 | ["PREFLIGHT_CONTRACT_FIX_R1@0","R2_MINIMAL_EXEC_FIX@2","R3_SOLVED_STATUS_FIX@4","R4_TEMP_ROOT_ISOLATION_FIX@6","R5_X12_DOMAIN_FIX@8","R6_DESIGN_SPACE_BINDING_FIX@8","R7_OBSERVE_AND_INVALID_TOLERANCE_FIX@50","R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX@56"] | PASS |
| C16 | R7 S1 stop facts and diagnostics deviation disclosed | preflight PASS_BYTE 2/2; diag 4/28 vs 2/14; main 0; FROZEN_BYTES_SHA_MISMATCH | plan.r8_addendum + prereg R8 section | PASS |
| C17 | pre-frozen reuse implementation (P1) | manifest frozen_vspgeom_path + sibling vkey/vsp3; SHA equality; canonical; PREFROZEN_MANIFEST_REUSE; no FreezeBuilder; tamper test | P1: initial 15/16/17 reuse A1 family_pair_manifest frozen_vspgeom_path + sibling vkey/vsp3, SHA+canonical fail-closed, PREFROZEN_MANIFEST_REUSE, no FreezeBuilder; P2: static hit without reuse -> unusable; verified by 79-check zero-physical gate (A5 independent run PASS) | PASS |
| C18 | zero-physical prestart gate (P5) | static_index_count=119; 3x2 reuse checks; mismatch/missing vsp3 REFUSED; physical 0 | {"status":"PASS","checks":79,"failures":[],"triples":6,"physical_call_count":0,"solver_started":false} | PASS |
| C19 | prestart records static_index_count=119 and reuse evidence | 119 | 119 | PASS |
| C20 | manifest field handling per Lead m02431 | no frozen_vkey_path/frozen_vsp3_path required; vsp3 missing fail-closed | verified | PASS |
| C21 | accounting pseudo-count fixes (P3) | starts==0 => internal 0; batch_summary phase+total; diagnostics polar_sha256; charged+planned<=caps assertion | starts==0 -> internal 0 (no default 7); batch_summary phase+total; diagnostics polar_sha256 extraction; charged+planned>caps -> ACCOUNTING_INCONSISTENT | PASS |
| C22 | diagnostic phase pre-registered at 4 starts/28 internal (P4) | DIAG-01/02 designs 16/17, each 2 families | plan.diagnostics + prereg | PASS |
| C23 | R7 2/14 -> 4/28 deviation disclosed | disclosed | prereg/plan/r8_addendum | PASS |
| C24 | A1 frozen bytes unchanged | f74a4752 / 31d78182 / c40b11df / 8f9b893c / 8b29d1e3 / 995bb12f | {"evaluator":"f74a4752495fd6c5330edcaf7edb4bcbe93f99c2a76bac06b5670d1f765ae20d","freeze_api":"31d781821516bb80fc158238e4ef485c361afea674ca3b962efbb89d5a737173","openvsp_model":"c40b11df29e9a41889b81f5c608c9a12cd921cf62d01c5318a6ab8eb91f859f6","design_space":"8f9b893c13195c80ff1ee88598134e3f44fef0495452249780d114c9e0593b89","design_space_config":"8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a | PASS |
| C25 | A2 executor blob binding (4 files) matches disk | ff3f5639211306276712302e561f2ff931d702396db625eeb96112e6807d3d20 | 1c857b48f2fa8cd0b74b285414d889a165abf3d9dfef41fb64ee3f53cc6f58c5 / 0dfe53cc85ffb384be3b15c2f4cc5bcbc6e3aba55f46093434dc2f1588a065e1 / f2e524a3dc69a962e4ee6e535caba4889df464d9ac578ab33f5b5cc65218e6f9 | PASS |
| C26 | plan policy deep diff vs R7 plan limited to whitelist | 341 leaf paths | 341 leaf diffs all within whitelist: identity/batch/run/window/policy_doc/initial manifest/caps 388-2702->390-2730/diag 2-14->4-28/runtime_binding A2 SHAs/disclosures/r7_addendum->r8_addendum; 34/34 scientific policy fields byte-identical; matrix arms/seed/slot digest a78a903c/max 451-3157/reserve 64 unchanged | PASS |
| C27 | cumulative accounting | prior 56/404 + R8 390/2730 = 446/3134 <= 451/3157 | [object Object] | PASS |
| C28 | window / token / deadlines | 16:30Z-11-12T04:00Z / start 21:00Z / clean 02:30Z / hard 04:00Z | {"start_utc":"2026-11-11T16:30:00Z","end_utc":"2026-11-12T04:00:00Z","token":"WINDOW_OK-P2AV2R8-20261111T1630Z-20261112T0400Z","status":"REQUESTED_NOT_SIGNED"} | PASS |
| C29 | preflight authorization limited to PASS_BYTE | PASS_NUMERIC not pre-authorized | DRAFT.preflight_accept_numeric false/absent | PASS |
| C30 | R1-R7 evidence read-only unchanged | 9e5c29b0 / eee7868a / 18865f8f / 6e2aebcf / ca0bdc7b / 72b95e03 / 1a552267 unchanged | r1 9e5c29b0/38,476; r2 eee7868a/47,081; r3 18865f8f/52,695; r4 6e2aebcf/59,125; r5 ca0bdc7b/63,264; r6 72b95e03/67,063; r7 1a552267/69,405 all unchanged on disk | PASS |
| C31 | R1-R7 excluded from E1-E6 and charged counts disclosed | excluded / 17 starts 119 internal | R1-R7 excluded from E1-E6; charged total across R1-R7 = 23 starts/161 internal (17/119 through R6 + 6/42 R7); no R8 endpoint may cite them | PASS |
| C32 | L-10 decision and A5 position recorded | L-10 md/json SHAs; A5 accepts prefrozen reuse with constraints; flags headroom 5/23 + design15 NaN precedent | gate + conditions R8-DECISION-01 | PASS |
| C33 | launcher binding and safety checks | d1e8b6f647e4724d48af81a4e20de55ab4f7de0174061e7f582f35eeccf4dc46 / 29320 B | EXPECTED pins executor/plan/identity/A1/design-space; gate prefixes; GO binding; refuses pre-existing cases/ledger; prestart before run | PASS |
| C34 | zero-physical launcher smoke | 3dd759a1581ec374457fac2c2a6773626bc0bb6079e19d7dbd6359691e537a1c | SMOKE_NO_SOLVER, physical 0, solver false, modules+design space verified | PASS |
| C35 | post-approval dry-run tool registered and physically inert | 865451fc0ba4d865668e2da53810408a806803c81ca59e307ce63200f3f47e37 | real dry-run only after signature | PASS |
| C36 | R8 addendum status / retained fixes / cumulative | R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX; R2-R7 fixes retained; 446/3134 | R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX at physical 56; R2-R7 fixes retained; cumulative 446/3134 | PASS |
| C37 | conditions 52 prepared and signature replacements defined | 52 items + M1-M6 | conditions file | PASS |
| C38 | approval_refs_final 14 keys prepared | 14 keys, no placeholders except a5_review=gate commit | defined in gate | PASS |
| C39 | draft-to-signed delta whitelist | 9 top-level paths | allowed_draft_to_signed_top_level_deltas | PASS |
| C40 | tamper unit test fail-closed on corrupted prefrozen byte | present/passing | gate refuses corrupted/missing prefrozen bytes and missing sibling vsp3 (79-check fail-closed design; A2 tamper test; A5 independent gate rerun) | PASS |
| C41 | pytest R8 suite | r8 tests pass; no new red | -k "r2_ or r3_ or r5_ or r7_" 14 passed / 31 deselected, exit 0, zero physical (r8_pytest_20261111.txt) | PASS |
| C42 | R8 package text consistency (no stale R7-only claims) | no stale executor/launcher/388/2716 beyond historical | checked plan/prereg/DRAFT | PASS |
| C43 | design-space preload binding retained | A1 design_space.py 8f9b893c + config 8b29d1e3 | 8f9b893c13195c80ff1ee88598134e3f44fef0495452249780d114c9e0593b89 | PASS |
| C44 | GO / gate prefix bindings in launcher | G-P2AV2R8-PRE:PASS / C-P2AV2R8-02:PASS: | verified | PASS |
| C45 | static_index_count=119 in prestart gate | 119 | 119 | PASS |
| C46 | prefrozen vs manifest byte/canonical equality for 3 designs x 2 families | 12/12 families equal | 3 designs x 2 families = 6 frozen vspgeom pairs: 15 6b00d72d/be8454bf, 16 5feb1be8/54a46567, 17 99a52d06/7ab0b60d; static==initial==disk equal (triples 6/6), vkey/vsp3 siblings verified, role_map f1=small/f2=large | PASS |
| C47 | H1 verification evidence retained | r7_verify_prefrozen json/py retained | f619b12f.../2,842 B + 4952226b.../1,246 B | PASS |
| C48 | no mesh QC data gate | no QC gate / L-09 rejection retained | plan.r8_addendum + prereg | PASS |
| C49 | no winner/significance/cross-family; fuel null; NOT_VALIDATED | not claimed | plan endpoint/statistics policies | PASS |
| C50 | no R9 default | no automatic next round | recorded in gate/conditions | PASS |
| C51 | A5 physical_call_count=0 / solver_started=false | 0 / false | confirmed | PASS |
| C52 | R8 pre-exec run dir exactly 8 package files | 8 files | 8 entries | PASS |
| C53 | A2 final tooling commit 877b323 contains launcher+gate+smoke+dry-run tool+pytest and disk==commit | 7 changed files; git diff --exit-code empty | 877b323a resolved; git diff exit 0; launcher d1e8b6f6/29,320, gate 47160cf2/19,666, dry tool 865451fc/20,743, smoke 3dd759a1/12,475, pytest b0f8fb62/330 | PASS |
| C54 | zero-physical prestart gate module correctness and A5 independent rerun | 79/79 PASS, static 119, guard triples 6, failures 0, physical 0 | A2 selftest f0fc3474/37,390 PASS 79/79; A5 rerun PASS 79/79 failures [] evidence 2cdaaf10/37,410 physical 0 | PASS |
| C55 | launcher explicitly calls prestart gate and writes evidence before any spawn | import+call after verify_execution_gate before prestart; FAIL refuses; pins plan/identity/executor | import run_prefrozen_gate true; FAIL raise PREFROZEN_REUSE_GATE_FAILED true; pins 0a14c8f0/cc2118de/ff3f5639 true; evidence path/sha/bytes to prestart+log true | PASS |
| C56 | post-approval dry-run tool fixes seq==8 and r8_addendum; self-test 42/42 | 42/42 PASS, 390/0/2730, physical 0 | 865451fc/20,743; self-test b2d47d26/1,596 42/42 PASS failed [] physical 0 | PASS |
| C57 | launcher zero-physical smoke | SMOKE_NO_SOLVER gate PASS 79/119/6 modules 5/5 physical 0 | 3dd759a1/12,475 PASS | PASS |
| C58 | pytest regression suite | 14 passed / 31 deselected exit 0 | b0f8fb62/330 confirmed | PASS |
| C59 | package commit and tooling commit resolve with byte-identical disk state | d926972 8 files; 877b323 resolves; both git diff --exit-code empty | verified A5: PKG_DIFF=0, TOOL_DIFF=0, run dir 8 files, no cases/ledger/approval.json | PASS |
| C60 | A2 cleanup: superseded failed self-test and stale smokes not committed; no pre-execution artifacts | only current 1649Z smoke + 165210Z selftest in commit; no cases/ledger | run dir exactly 8 package files; evidence commits contain final smoke/selftest only | PASS |

## 5. 强制签署修正（M1-M6）

- M1: replace the 8 placeholder approval_refs with the 14-key refs_final in this gate; a5_review must be the commit SHA of this G-P2AV2R8-PRE gate.
- M2: expand DRAFT conditions 15 -> exactly the 52 conditions in docs/reviews/dreal001_a5_p2av2r8_signature_conditions_20261111.json (byte-identical texts and order).
- M3: set status/approved/approved_by/approved_at_utc/authorization, window.status=APPROVED, and b2_waiver (APPROVED_BY_LEAD_FOR_THIS_BATCH_ONLY, approver, approved_at_utc, a5_pre_review_commit=gate commit).
- M4: amendment_log must remain byte-identical to the DRAFT (seq1-seq7 = R7 signed history; seq8 R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX at the DRAFT at_utc with physical_call_count_at_amendment=56).
- M5: no other binding or scientific-policy byte may change; A2 must commit the signed approval byte-identically, run the real post-approval dry-run with the bound R8 tool, then A5 C-P2AV2R8-02, then Lead GO; C gate hard line 17:45Z.
- M6: pre-frozen reuse tamper unit test + zero-physical prestart gate evidence (static_index_count=119; 3 designs x 2 families reuse checks; vsp3 fail-closed; physical=0) must be delivered in the R8 package and A5-verified; if any is missing the Lead must record an explicit evidence-quality debt acceptance in the signed approval.

## 6. approval_refs_final（14 键）

```json
{
 "a1_bundle_commit": "2a57632b3f7d5d567556d9774913ec40a5d72272",
 "a1_bundle_commit_full": "2a57632b3f7d5d567556d9774913ec40a5d72272",
 "a1_bundle_manifest_sha256": "995bb12fff738d3ebb0bde08c0d5c5bfeb9532aebe536847ef307a2332013aa5",
 "a1_bundle_path": "D:\\RCAIDE\\dnext001\\wt-real-a1-geometry-solver\\research\\concorde_metaopt\\dreal001\\geometry\\replay_bundles\\P2A_V2_PREFLIGHT_20261111_R1",
 "a1_bundle_note": "old 3-case bundle 20999b3e.../0598441 superseded; R1 2-case bundle re-bound unchanged",
 "a1_executable_commit": "6753eb39b710035187db13ceb3328301c645c1ba",
 "a1_task49_commit": "6753eb39b710035187db13ceb3328301c645c1ba",
 "a1_execution_code": "6979802",
 "a1_execution_code_note": "legacy execution code id retained; frozen byte bindings are evaluator f74a4752... / freeze_api 31d78182... / openvsp_model c40b11df...",
 "a1_execution_head": "2a57632b3f7d5d567556d9774913ec40a5d72272",
 "a1_head": "2a57632b3f7d5d567556d9774913ec40a5d72272",
 "a2_execution_code": "ff3f5639211306276712302e561f2ff931d702396db625eeb96112e6807d3d20",
 "a2_package_commit": "d926972d10208c44d172e5a19008d7f45bf68300",
 "a5_review": "A5 G-P2AV2R8-PRE review commit SHA (this gate commit)"
}
```

## 7. 52 条签署条件

完整文本见 docs/reviews/dreal001_a5_p2av2r8_signature_conditions_20261111.json（sha256 c1f87636c3f49d928f61835463e8cc4b36c3427c71989e35b4126df8a6c6536e）；条件 1-42 = R3/R1 适配（R1-HIST-01/R1-02/R1-03 保留），43-52 = R8 专用（PKG/PREFROZEN/PRESTART/ACCT/HIST/WINDOW/DECISION/REFS/SIGN/DISC）。

## 8. 披露（D1-D9）

- D1：R1-R7 series exclusion: charged 17 starts/119 internal (R1-R4 2/14 each, R5 0/0, R6 3/21, R7 6/42); cumulative baseline 56/404; R8 plan 390/2730; cumulative 446/3134 vs caps 451/3157; headroom only 5 starts/23 internal.
- D2：R7 S1 stop facts: preflight 2/2 real PASS_BYTE; diagnostics 4/4 real SOLVED_VALID but 4 starts/28 internal vs pre-registered 2/14 (+2/+14 deviation, executor comment/missing guard); main 0 starts; design15 f2 rebuilt bytes 27325306... != A1 prefrozen be8454bf...; A1 evaluator_v12.py:641-649 static-vs-runtime guard raised for 546x472 while A2 recorded failed_family f1.
- D3：Pre-frozen reuse is execution-layer only and zero-physical: A1 bytes unchanged, plan scientific fields unchanged, no solver started to verify it; correctness is byte/canonical equality only and is not a solve claim.
- D4：Manifest field facts: family frozen blocks have no frozen_vkey_path/frozen_vsp3_path; vkey/vsp3 are siblings (model.vkey/model.vsp3) of frozen_vspgeom_path; missing vsp3 or mismatch fails closed; static_index_count=119; a static-index hit not resolved via PREFROZEN_MANIFEST_REUSE must fail closed.
- D5：design15 f1 462x401 prefrozen bytes previously produced an all-NaN polar in R6; an R8 main first-case INVALID_NUMERICAL is possible; protocol D tolerance applies to scientific invalids only and requires per-arm invalid counts, per-case status/polar SHA/reason, invalid-ratio time series and separate diagnostic reporting.
- D6：R6 NaN phenomenon confirmed but mechanism NOT proven (H1/H2/H3); no mesh QC data gate adopted (L-09 rejection retained; calibration W10p real 3/3 SOLVED yet nonplanar).
- D7：Accounting pseudo-counts fixed/disclosed: default 7 internal on 0-start rows, main-only record_internal_cases, null diagnostics polar_sha256; R7 internal 42 = 2x7 preflight + 4x7 diagnostics and is derivable from the ledger.
- D8：C10_executor_sha remains a definitional false negative in package dry_run.json (executor file SHA vs recomputed aggregate digest), present since R1, non-blocking; C16/C19 are NV by design; spawn exit_code/stdout_tail persistence remains a future improvement.
- D9：A5 physical_call_count=0 and solver_started=false; this gate is not an execution authorization; after signature the real dry-run, A5 C-P2AV2R8-02 and Lead GO remain mandatory; R8 pre-exec run dir must contain exactly the 8 package files plus signed approval and dry-run evidence (no cases/ledger/batch_summary/stop_report); R7 identity may omit a5_r1_probe and the R1-03 copy handoff stays a non-blocking closeout item; no R9 by default.

## 9. 签署后流程（不改变本门禁结论）

1. Lead 按 M1-M6 签署 approval.json（refs 14 键、52 conditions、window.status=APPROVED、b2_waiver、amendment_log 与 DRAFT 相同）。
2. A2 对签署件做字节原样 commit，并运行 R8 真实 post-approval dry-run（390 planned / 0 emitted / physical 0 / 37+ checks PASS）。
3. A5 出 C-P2AV2R8-02（签名绑定、window open、390/0、physical=0、无 cases/ledger）PASS 后，Lead 发 GO；GO 须绑定 pre-gate/C-gate commit 前缀、approval SHA、dry-run SHA、run_id。
4. 执行顺序：2 preflight（仅 PASS_BYTE）-> 4 diagnostic starts（2 designs×2 families）-> 384 main；窗口 16:30Z-11-12T04:00Z，start deadline 21:00Z，clean stop 02:30Z，hard stop 04:00Z。

## 10. A5 签署块

- verdict：PASS_WITH_MANDATORY_SIGNATURE_CORRECTIONS
- checks：60/60 PASS，0 FAIL
- A5 physical_call_count=0；solver_started=false；未 push；未改 A1/A2/R1-R7 字节。
- 本门禁不构成执行授权；执行须 Lead 签署 + 真实 dry-run + C 门禁 + Lead GO。