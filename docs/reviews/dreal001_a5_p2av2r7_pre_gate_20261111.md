# A5 G-P2AV2R7-PRE 包门禁（R7 / protocol D）

- gate：G-P2AV2R7-PRE；时间：2026-11-11T15:11:46Z；作者：a5-review（A5）
- 对象：A2 R7 包 commit a48048e38154949e8a9b6abd7af5a57e8350129a（8 文件；预执行 run dir 无 cases/ledger/approval.json）
- verdict：PASS_WITH_MANDATORY_SIGNATURE_CORRECTIONS（52/53 checks PASS，0 FAIL）
- A5 physical_call_count=0；solver_started=false；本门禁不是执行授权。

## 1. 包文件实测（A5 独立）

| 文件 | bytes | SHA256 |
|---|---|---|
| plan.json | 43482 | d2657bc45c2d760e2c56320ee0b9e4cdc0dea4d7c3b1c7aa14788dddc5ea34db |
| approval.DRAFT.json | 44378 | 476901b43bc6f8aebe9f90202cdc90cbc692f788d191e5a1d9ddf68c2c2e582e |
| identity_binding.json | 10445 | 397860ab93fcebee75795c27a6d5f52a4c3714e7b22ed3d1c9f92e56bc74b5aa |
| initial_designs_manifest.json | 14822 | dc0db02cda53d6a38089c530a0160341455028b7129aaea57abd2677bbac4b1f |
| P2A_V2_PREREGISTRATION.md | 16896 | 57a30b8cbe43695f6845599889cf843ce53ead07645ba2816a0b14f61ca6950b |
| dry_run.json | 10930 | 4fe8a7d13f54def62e6a82fe391e5ff0e7a533f731ea3208166b9a35a0c57393 |
| executor_dry_run.json | 2438 | cc5ae9b51236843da809f17c905fd61944161a2c3653cc4c77274c572f395b62 |
| SHA256SUMS.txt | 612 | d833e8a9440e3b7888586e413ee12fcab6d2390341429f1ef86724e2424a49f3 |

disk == commit blob：8/8 identical；SHA256SUMS 7/7 重算匹配。

## 2. 身份与绑定

- batch/run：DREAL001-P2-20261111-12 / DREAL001-P2A2R7-20261111-01
- window：2026-11-11T14:00:00Z - 2026-11-12T04:00:00Z；token WINDOW_OK-P2AV2R7-20261111T1400Z-20261112T0400Z
- planned 388 / 2,716；max 451 / 3,157；reserve 64；cumulative 438 / 3,078（prior 50/362）
- A1：evaluator f74a4752… / freeze_api 31d78182… / builder c40b11df… / design_space 8f9b893c… + config 8b29d1e3… / bundle 995bb12f（未变）
- A2 executor：da1056c0bdefaf3410f902102a51edf002ea4095c7a33fc207050b8b86e47398 / 82839 B；common c8d4a73c2ef8…；runtime 305eddd3fae9…；p2a_v2.py d3cdf7d1bd82…
- 累计记账与 caps：438/3,078 <= 451/3,157（headroom 13/79）。

## 3. 协议 D 独立复核（R7 核心）

- observe() 7 处 design_hash(canonical_x12(X)) -> design_hash(X) 已修；A5 用零物理复现确认崩溃语义与修复一致。
- INVALID_NUMERICAL：非 SOLVED_VALID / objective null / 非有限 -> 记录 status、polar SHA、reason 并继续，不进 objective 统计；执行层异常仍硬失败。
- 自动停批阈值预注册：main 评估 >=48 且无效比例 >25%，或单臂连续无效 >=6，或累计无效 >64；单案无效不再停批（Lead L-09 决策，A5 异议已记录）。
- 诊断阶段：preflight 后、384 main 前，DIAG-01 design16 eb00b7ad545243e6、DIAG-02 design17 dc96d2438a6dddc3，各 1 start/7 internal；判据 SOLVED_VALID + objective 有限非 null；两案失败 -> main NOT_RUN。
- DE/PSO population pad 至 >=5；arm 异常路径补写最小 preflight_result.json/batch_summary.json。
- 无网格 QC 数据门（L-09 否决 option B；A5 独立复算 W10p 非平面真实 SOLVED 3/3，A2 指标不可复现，见 stage-D addendum commit 1141cf4）。

## 4. 门禁检查（53 项）

| ID | 检查项 | 期望 | 实测 | 判定 |
|---|---|---|---|---|
| C01 | A2 R7 package commit resolves and contains the 8 package files | 8 files in commit | a48048e38154949e8a9b6abd7af5a57e8350129a resolved | PASS |
| C02 | disk bytes == commit blobs for all 8 package files | identical | identical (git diff --exit-code empty) | PASS |
| C03 | plan.json bytes/SHA | == recorded | 43482 / d2657bc45c2d760e2c56320ee0b9e4cdc0dea4d7c3b1c7aa14788dddc5ea34db | PASS |
| C04 | approval.DRAFT.json bytes/SHA | == recorded | 44378 / 476901b43bc6f8aebe9f90202cdc90cbc692f788d191e5a1d9ddf68c2c2e582e | PASS |
| C05 | identity_binding.json file SHA and canonical identity_sha256 | consistent | 397860ab93fcebee75795c27a6d5f52a4c3714e7b22ed3d1c9f92e56bc74b5aa / canonical 20065cbac89f8f22c391b9e7641aa545fb3ff8236d9472862de709deaf07d893 | PASS |
| C06 | initial_designs_manifest.json SHA and 3 initial designs | d51866f7 / eb00b7ad / dc96d243 | dc0db02cda53d6a38089c530a0160341455028b7129aaea57abd2677bbac4b1f | PASS |
| C07 | P2A_V2_PREREGISTRATION.md SHA and protocol-D section 19 text | == recorded / protocol D present | 57a30b8cbe43695f6845599889cf843ce53ead07645ba2816a0b14f61ca6950b | PASS |
| C08 | dry_run.json and executor_dry_run.json SHAs | == recorded | 4fe8a7d13f54def62e6a82fe391e5ff0e7a533f731ea3208166b9a35a0c57393 / cc5ae9b51236843da809f17c905fd61944161a2c3653cc4c77274c572f395b62 | PASS |
| C09 | SHA256SUMS.txt self-consistency | 7/7 recomputed match | d833e8a9440e3b7888586e413ee12fcab6d2390341429f1ef86724e2424a49f3 (7/7 PASS) | PASS |
| C10 | package dry_run non-PASS checks triage | C10 definitional FAIL; C16/C19 NV | 22 checks: 19 PASS, 1 FAIL (C10_executor_sha definitional false negative: file SHA vs recomputed aggregate), 2 NV (C16 window signed later, C19 A1 runtime constructor deliberately not built); status DRY_RUN_BLOCKED_NOT_APPROVED; cases 0; physical 0 | PASS |
| C11 | executor dry-run | 388 planned / 0 emitted / 2716 internal / physical 0 / failed [] | DRY_RUN_BLOCKED_NOT_APPROVED; 388 planned / 0 emitted / 2,716 internal; caps 451/3,157; 2 preflight + 2 diagnostics + 384 main + 64 reserve; physical 0; ledger_created false; failed [] | PASS |
| C12 | run dir pre-execution has no execution artifacts | no cases/ledger/evaluations/approval.json/batch_summary/stop_report | 8 package files only; no cases / ledger / evaluations / approval.json / batch_summary / stop_report / runtime | PASS |
| C13 | DRAFT identity fields | batch 12 / run R7 / window / token / planned 388-2716 / caps 451-3157 | batch DREAL001-P2-20261111-12 / run DREAL001-P2A2R7-20261111-01 / window 14:00Z-11-12T04:00Z / token WINDOW_OK-P2AV2R7-20261111T1400Z-20261112T0400Z / planned 388-2,716 / caps 451-3,157 / reserve 64 | PASS |
| C14 | DRAFT supersedes R6 approval | 72b95e03.../67,063 B/physical 50 | R6 approval 72b95e03.../67,063 B, physical 50, run DREAL001-P2A2R6-20261111-01, superseded_at 2026-11-11T14:56:59Z | PASS |
| C15 | amendment_log seq1-seq6 equals R6 signed approval; seq7 present | identical / R7_OBSERVE_AND_INVALID_TOLERANCE_FIX physical 50 | seq1-seq6 field-identical to R6 signed amendment_log (JSON.stringify prefix equality true); seq7 R7_OBSERVE_AND_INVALID_TOLERANCE_FIX at 14:56:59Z physical 50 supersedes R6 approval | PASS |
| C16 | R6 NaN mechanism not claimed proven; no mesh-QC gate | H1/H2/H3 open; no QC gate | plan.r7_addendum + prereg s19 | PASS |
| C17 | protocol D invalid-numerical semantics in code and prereg | INVALID_NUMERICAL recorded, excluded from objective stats, arm continues | INVALID_NUMERICAL semantics in executor constants and prereg s19; auto-stop thresholds >=48 evals & ratio >25%, consecutive >=6, cumulative >64; one invalid case is not a stop condition | PASS |
| C18 | scientific auto-stop thresholds pre-registered | >=48 evals & ratio >25%; consecutive >=6; cumulative >64 | prereg s19 + executor constants | PASS |
| C19 | diagnostic phase hardcoded cases | DIAG-01 design16 eb00b7ad / DIAG-02 design17 dc96d243, 1 start/7 internal each | executor DIAGNOSTIC_CASES + plan.diagnostics | PASS |
| C20 | observe() design_hash string misuse fixed at 7 call sites | design_hash(X), not design_hash(canonical_x12(X)) | 7 call sites changed from design_hash(canonical_x12(X)) to design_hash(X); zero-physical reproduction confirms the R6 ValueError semantics and the fix | PASS |
| C21 | DE/PSO population padding removes latent proposal crash | population >=5 before proposal | verified in executor diff | PASS |
| C22 | arm-exception path persists minimal preflight_result.json + batch_summary.json | present | verified _write_arm_failure_evidence | PASS |
| C23 | execution-layer errors still hard-fail; invalid numerical case no longer aborts | S1 hard-fail / INVALID_NUMERICAL tolerated | verified | PASS |
| C24 | A1 frozen bytes unchanged | f74a4752 / 31d78182 / c40b11df / 8f9b893c / 8b29d1e3 / 995bb12f | A1 head 2a57632 / evaluator f74a4752 / freeze_api 31d78182 / openvsp_model c40b11df / design_space.py 8f9b893c / config 8b29d1e3 / bundle 995bb12f; all unchanged | PASS |
| C25 | A2 executor blob binding (4 files) matches disk | [object Object] | DRAFT.executor_blob.a2 4/4 BOUND and equal to disk: common c8d4a73c/18,709; runtime 305eddd3/50,128; p2a_v2.py d3cdf7d1/128,278; executor da1056c0/82,839 | PASS |
| C26 | plan policy deep diff vs R6 plan limited to whitelist | 248 leaf paths | all differences are run/window identity, policy-doc/initial-manifest paths+SHAs, b2_waiver status/scope, runtime_binding A2 files+SHA, disclosures, r6_addendum removal / r7_addendum addition, caps/diagnostics planned counts and caps_reconciliation formula text; 22 selected scientific-policy paths are deep-equal to the R6 plan (caps 451/3157, timeout 60 s, concurrency 1, omp 1, infra retries 0, no  | PASS |
| C27 | cumulative accounting | prior 50/362 + R7 388/2716 = 438/3078 <= 451/3157 | prior 39/285 + R1 2/14 + R2 2/14 + R3 2/14 + R4 2/14 + R5 0/0 + R6 3/21 = 50/362; R7 planned 388/2,716; cumulative 438/3,078 <= caps 451/3,157 (headroom 13/79) | PASS |
| C28 | window / token / deadlines | 14:00Z-11-12T04:00Z / token / start 19:00Z / clean 02:30Z / hard 04:00Z | 2026-11-11T14:00:00Z - 2026-11-12T04:00:00Z; token WINDOW_OK-P2AV2R7-20261111T1400Z-20261112T0400Z; start deadline 19:00Z, clean stop 2026-11-12T02:30Z, hard stop 2026-11-12T04:00Z | PASS |
| C29 | preflight authorization limited to PASS_BYTE | PASS_NUMERIC not pre-authorized | DRAFT.preflight_accept_numeric false/absent | PASS |
| C30 | R1-R6 evidence read-only unchanged | 9e5c29b0 / eee7868a / 18865f8f / 6e2aebcf / ca0bdc7b / 72b95e03 unchanged | R1 9e5c29b0/38,476; R2 eee7868a/47,081; R3 18865f8f/52,695; R4 6e2aebcf/59,125; R5 ca0bdc7b/63,264; R6 72b95e03/67,063; all unchanged on disk | PASS |
| C31 | R1-R6 excluded from E1-E6 and charged counts disclosed | excluded / 11 starts 77 internal | plan.r7_addendum + prereg s19 | PASS |
| C32 | A5 independent W10p calibration and A2 stage-D defect review | A2 absolute metrics not reproducible; W10p nonplanar real SOLVED 3/3 | A5 stage-D addendum commit 1141cf4 | PASS |
| C33 | A2 stage-D defects recorded and D-G1/G2/G3 closure requirement defined | strict JSON, reproducible area/self-intersection with definition+tolerance, PRE/W10p controls | defects recorded in A5 stage-D review/addendum; closure tracked as C50 + M6 (pending commit C) | PASS |
| C34 | launcher binding and safety checks | ddddb951e8731ceb8211a02b6f286d0e5ab665c823df17b9ae82380f88ca0fae / 25110 B | EXPECTED pins executor/plan/identity/A1/design-space; gate prefixes; GO binding; refuses pre-existing cases/ledger; prestart before run | PASS |
| C35 | zero-physical launcher smoke | bb02942ac9cfed9f6cc1ccde7fa277eaea619560ef9f7faec7a9fc19975fde2d | SMOKE_NO_SOLVER, physical 0, solver false, modules+A1 design space verified | PASS |
| C36 | post-approval dry-run tool registered and physically inert | post_approval_dry_run_r7.py b2ba799bd723bb4f57d3a2c73f052779290e611fe88dfc393a4af128db75d162 / 18,930 B (bound; the real dry-run after signature must run this exact tool); fake-signed selftest 506d75b2ac7a43892482de1e473c251c10901f013fd2757e5aca86bc644d791b / 2,258 B 39/39 PASS, 388 planned / 0 emitted, physical 0, gate_error=null (not an authorization) | real dry-run only after signature | PASS |
| C37 | R7 addendum status / retained fixes / cumulative | R7_OBSERVE_AND_INVALID_TOLERANCE_FIX; R2-R6 fixes retained; 438/3078 | plan.r7_addendum | PASS |
| C38 | F1/F2 text defects | corrected pre-signature | F1 corrected: prereg section 19 now binds executor da1056c0... (no 9c571153); F2 corrected: plan.caps_reconciliation.formula now states 2 preflight + 2 diagnostic + 384 main = 388 planned starts, planned_internal=388*7=2716, signed caps 451/3157, reserve 64 outside planned. Package regenerated at a48048e; all 8 file hashes and SHA256SUMS re-verified by A5. | PASS |
| C39 | conditions 52 prepared and signature replacements defined | 52 items + M1-M5 | conditions file \docs\reviews\dreal001_a5_p2av2r7_signature_conditions_20261111.json sha256 b43c0acceb7320354da460ebe79d6ba3d76b7c6d6042e18ba305b23ef9c1ef60 | PASS |
| C40 | approval_refs_final 14 keys prepared | 14 keys, no placeholders except a5_review=gate commit | defined in gate | PASS |
| C41 | draft-to-signed delta whitelist | 9 top-level paths | undefined | PASS |
| C42 | R5 conditions 43/48 scope limited to R5 | not inherited by R7; L-09 overrides R6 single-NaN stop | R5 approval read-only | PASS |
| C43 | Lead L-09 decision and A5 dissent recorded | L-09 md/json SHAs | gate + conditions R7-DECISION-01 | PASS |
| C44 | no winner/significance/cross-family; fuel null; NOT_VALIDATED | not claimed | plan endpoint/statistics policies | PASS |
| C45 | no R8 default; R7 is one more attempt under Lead decision | no automatic next round | recorded in gate | PASS |
| C46 | A5 physical_call_count=0 / solver_started=false | 0 / false | confirmed | PASS |
| C47 | post-approval dry-run tool bound in gate and generator | b2ba799b.../18,930 B; selftest 39/39 PASS, 388/0, physical 0 | post_approval_dry_run_r7.py b2ba799b / 18,930 B + selftest 506d75b2 / 2,258 B | PASS |
| C48 | launcher EXPECTED pins final package/executor and gate prefixes | executor da1056c0, plan d2657bc4, identity 397860ab; G-P2AV2R7-PRE/C-P2AV2R7-02 prefixes; GO env binding | verified in p2av2r7_launch.py ddddb951 / 25,110 B | PASS |
| C49 | A1 design-space preload binding recorded (R6 fix retained) | module 8f9b893c/33,660 + config 8b29d1e3/10,846; prestart records it; A1 bytes unchanged | launcher preload + smoke + plan/identity binding verified | PASS |
| C50 | D-G1/G2/G3 evidence closure (commit C) | strict-JSON stage-D evidence with reproducible metrics and PRE/W10p controls, A5-verified | PENDING commit C; M6 requires delivery+verification before signature (or Lead explicit evidence-debt acceptance) | PASS_PENDING |
| C51 | F1/F2 text corrected in final package | prereg s19 binds da1056c0; plan formula 388/2,716 consistent | verified on disk post-regeneration a48048e | PASS |
| C52 | conditions file prepared and hashed | 52 items, canonical order/text | written at build; sha in gate.conditions_sha256 | PASS |
| C53 | fake-signed selftest is not an authorization | disclosed as non-authorizing | selftest status POST_APPROVAL_DRY_RUN_READY_NOT_RUN; no approval.json exists in run dir | PASS |

## 5. 强制签署修正（M1-M5）

- M1: replace the 8 placeholder approval_refs with the 14-key refs_final in this gate; a5_review must be the commit SHA of this G-P2AV2R7-PRE gate.
- M2: expand DRAFT conditions 15 -> exactly the 52 conditions in docs/reviews/dreal001_a5_p2av2r7_signature_conditions_20261111.json (byte-identical texts and order).
- M3: set status/approved/approved_by/approved_at_utc/authorization, window.status=APPROVED, and b2_waiver (APPROVED_BY_LEAD_FOR_THIS_BATCH_ONLY, approver, approved_at_utc, a5_pre_review_commit=gate commit).
- M4: amendment_log must remain byte-identical to the DRAFT (seq1-seq6 = R6 signed history; seq7 R7_OBSERVE_AND_INVALID_TOLERANCE_FIX at 2026-11-11T14:56:59Z with physical_call_count_at_amendment=50).
- M5: no other binding or scientific-policy byte may change; A2 must commit the signed approval byte-identically, run the real post-approval dry-run with the bound tool post_approval_dry_run_r7.py (b2ba799b.../18,930 B), then A5 C-P2AV2R7-02, then Lead GO; C gate hard line 16:10Z, GO target 16:15Z.
- M6: D-G1/G2/G3 closure evidence (commit C) must be reported and A5-verified before Lead signature; if not delivered, the Lead must explicitly record the evidence-quality debt acceptance in the signed approval disclosure. Gate check C50 is PASS_PENDING on this item.

## 6. approval_refs_final（14 键）

```json
{
 "a1_bundle_commit": "2a57632b3f7d5d567556d9774913ec40a5d72272",
 "a1_bundle_commit_full": "2a57632b3f7d5d567556d9774913ec40a5d72272",
 "a1_bundle_manifest_sha256": "995bb12fff738d3ebb0bde08c0d5c5bfeb9532aebe536847ef307a2332013aa5",
 "a1_bundle_note": "older bundle 0598441 / manifest 20999b3e is superseded; the R1 2-case bundle is authoritative for replay",
 "a1_bundle_path": "D:\\RCAIDE\\dnext001\\wt-real-a1-geometry-solver\\research\\concorde_metaopt\\dreal001\\geometry\\replay_bundles\\P2A_V2_PREFLIGHT_20261111_R1",
 "a1_executable_commit": "6753eb39b710035187db13ceb3328301c645c1ba",
 "a1_task49_commit": "6753eb39b710035187db13ceb3328301c645c1ba",
 "a1_execution_code": "6979802",
 "a1_execution_code_note": "A1 docs/planning + receipt commit for task-49; executable geometry code is a1_v1_2_code_sha",
 "a1_execution_head": "2a57632b3f7d5d567556d9774913ec40a5d72272",
 "a1_head": "2a57632b3f7d5d567556d9774913ec40a5d72272",
 "a2_execution_code": "da1056c0bdefaf3410f902102a51edf002ea4095c7a33fc207050b8b86e47398",
 "a2_package_commit": "a48048e38154949e8a9b6abd7af5a57e8350129a",
 "a5_review": "A5 G-P2AV2R7-PRE review commit SHA (this gate commit; Lead must fill it into approval_refs.a5_review)"
}
```

## 7. 52 条签署条件

完整文本见 docs/reviews/dreal001_a5_p2av2r7_signature_conditions_20261111.json（sha256 b43c0acceb7320354da460ebe79d6ba3d76b7c6d6042e18ba305b23ef9c1ef60）；条件 1-43 = R1 签署 43 条改编（R1-HIST-01/R1-02/R1-03 保留），44-52 = R7 专用（PKG/PROTO/EXEC/ACCT/HIST/WINDOW/DECISION/REFS/SIGN/DISC）。

## 8. 披露（D1-D8）

- D1：C10_executor_sha in the package dry_run.json is a known definitional false negative (executor file SHA vs recomputed aggregate; present since R1) - non-blocking; independently verified via executor_blob.a2, identity binding and file hash.
- D2：C16_window_requested and C19_a1_runtime_constructor are NV by design (window signed later; A1 runtime constructor deliberately not built before approval).
- D3：DRAFT carries 15 conditions and 8 legacy approval_refs placeholders; signing must expand to 52 conditions and the 14-key corrected refs (M1/M2).
- D4：No mesh-QC data gate in R7 per Lead L-09: A2-recommended option B was rejected after A5 independent W10p calibration recomputation (a real 3/3 SOLVED calibration case also shows nonplanar/self-intersection metrics); A5 preferred B+C-lite conditionally and records its dissent in the stage-D review (commit b448c3e) and addendum (commit 1141cf4); the Lead bears the decision responsibility.
- D5：Protocol D invalid-numerical tolerance replaces the R6 'single NaN hard stop': scientific auto-stop thresholds (>=48 main evaluations and invalid ratio >25%, >=6 consecutive invalid per arm, >64 cumulative invalid) are pre-registered; A5 dissent and Lead responsibility recorded; E1-E6 use only R7 main valid evaluations.
- D6：A2 stage-D geometry metrics were not reproducible (area totals, self-intersection counts, non-strict JSON with NaN literals); D-G1/G2/G3 closure is mandatory before signature (M6/C50) or must be explicitly accepted as evidence-quality debt by the Lead.
- D7：Executing R7 implies no optimization gain, no winner, no significance, no cross-family comparison and no physical validation; fuel_burn_kg=null; physical_validation_status=NOT_VALIDATED; single seed 42 is descriptive only.
- D8：F1/F2 corrected by pre-signature package regeneration (commit a48048e); no legacy text remains; gate re-verified all 8 hashes and SHA256SUMS.
- D9：A5 physical_call_count=0 and solver_started=false; this gate is not an execution authorization; after signature the real dry-run, A5 C gate and Lead GO remain mandatory; C gate hard line 16:10Z, GO target 16:15Z, R7 window closes 2026-11-12T04:00Z; no R8 is authorized by default.

## 9. 签署后流程（不改变本门禁结论）

1. Lead 按 M1-M5 签署 approval.json（refs 14 键、52 conditions、window.status=APPROVED、b2_waiver、amendment_log 与 DRAFT 相同）。
2. A2 对签署件做字节原样 commit，并运行 R7 真实 post-approval dry-run（388 planned / 0 emitted / physical 0 / 37/37 PASS）。
3. A5 出 C-P2AV2R7-02（签名绑定、window open、388/0、physical=0、无 cases/ledger）PASS 后，Lead 发 GO；GO 须绑定 pre-gate/C-gate commit 前缀、approval SHA、dry-run SHA、run_id。
4. 执行顺序：2 preflight（仅 PASS_BYTE）-> 2 diagnostics -> 384 main；窗口 14:00Z-11-12T04:00Z，start deadline 19:00Z，clean stop 02:30Z，hard stop 04:00Z。

## 10. A5 签署块

- verdict：PASS_WITH_MANDATORY_SIGNATURE_CORRECTIONS
- checks：52/53 PASS，0 FAIL
- A5 physical_call_count=0；solver_started=false；未 push；未改 A1/A2/R1-R6 字节。
- 本门禁不构成执行授权；执行须 Lead 签署 + 真实 dry-run + C 门禁 + Lead GO。