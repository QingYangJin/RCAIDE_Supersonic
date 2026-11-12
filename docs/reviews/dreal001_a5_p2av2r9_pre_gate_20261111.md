# G-P2AV2R9-PRE — A5 独立包门禁（R9，最后尝试）

- gate_id: **G-P2AV2R9-PRE**
- created_utc: `2026-11-11T17:52:57Z`
- reviewer: A5 (a5-review, branch `research/dreal001-a5-review`)
- run: `DREAL001-P2A2R9-20261111-01` / batch `DREAL001-P2-20261111-14`
- window: `2026-11-11T17:30:00Z` – `2026-11-12T04:00:00Z`，token `WINDOW_OK-P2AV2R9-20261111T1730Z-20261112T0400Z`
- verdict: **PASS_WITH_MANDATORY_SIGNATURE_CORRECTIONS**（52/52 checks PASS，0 FAIL）；本门禁**不是**执行授权
- physical_call_count: **0**；solver_started=false

## 1. 结论

A5 独立复核 R9 包（package commit `a4e9ded2f358035eff2dd55965b4408cb89dc96a`、tools commit `0603597c0a87f6ded231ae4ee1781bb9dea5f1b6`、launcher-gate 证据 commit `851b1a647e5bc7b80d5461bc271c8d472b9f8107`）后判定：**包可签署**，但签署必须整体执行 M1–M6 更正（14 键 refs、52 条 conditions、状态/授权/window/b2、amendment_log 绑定、a5_review 替换为本门禁 commit）。R8 attempt-1 为零物理 SETUP_STOP（charged 0/0），A5 FAIL-08 已独立确认根因与 R9 修复方向；R9 是 Lead 裁定的**最后尝试**（无 R10）。

## 2. R8 SETUP_STOP → R9 决策链

R8（approval `fa0d94a2...`/75,166 B）于 17:14:09Z 启动：launcher 侧 prefrozen gate PASS（79 checks、static_index_count=119、a1_runtime_guard all_equal、6 triples、physical 0），prestart 证据落盘后，**executor 自身** `_prefrozen_reuse_gate` → `FrozenPairService.get_or_freeze` 抛 `FreezeRecordError: PREFROZEN_GEOM_MISSING d51866f7d3c49303/462x401`。根因：`initial_designs_manifest.json` 的 family 行把 frozen 字段**平铺**（FLAT），而执行字节 `p2a_v2_runtime.py:574` 与 `p2a_v2_executor.py:1131` 只读嵌套 `"frozen"`。R8 无 cases/ledger/solver_attempts/preflight/batch/evaluations，physical 0/0，永久排除。R9 修复为执行层两处 reader 兼容 flat/nested（`family_frozen_payload`），A1 字节与 plan 科学政策不变。

## 3. R9 包文件（磁盘字节 = commit 字节，8/8）

| 文件 | SHA256 | bytes |
|---|---|---|
| `plan.json` | `3450034d54960dcb2c06c61d84f87c9b67604a369d63264603d7d0907c8b84c4` | 48619 |
| `approval.DRAFT.json` | `b57f9f6c551159e0cb1be490bc46e441f69e0005b9de448693c2516314ce0517` | 52781 |
| `identity_binding.json` | `f2ae7ced21229e616eb2d572c1c823060ab0448e530e50d1adc42a30a9d9893b` | 10445 |
| `initial_designs_manifest.json` | `93a078e3dcae1b7bf04e3f39a02632d87ef9fbcd26368dda4236ba8f517efe47` | 14822 |
| `P2A_V2_PREREGISTRATION.md` | `887f9880e6b9f53a5b99e2cddf9825b2a77fed2adc79dfd626a19e3a7e1be89b` | 17578 |
| `dry_run.json` | `ff54772e5e7d940408b457bfb4e856edb962d9cbb3c11e1312fa21d19f28573e` | 10930 |
| `executor_dry_run.json` | `d8e92cd9e93dd9f29662154d068d316d681657e7a5e846c4bab66670030043b3` | 2438 |
| `SHA256SUMS.txt` | `2f5d3c6c890b209a0b1d1ce7d970b3a5e5ddfe21b037c0c550cd2ea36d55fbe4` | 612 |

run dir 执行前恰 **8 文件**（无 cases/ledger/approval.json/preflight/batch/stop）；executor dry-run status `DRY_RUN_BLOCKED_NOT_APPROVED`：planned 390 / emitted 0 / internal 2,730 / physical 0。package `dry_run.json` 22 checks 仅 `C10_executor_sha` FAIL（文件字节 SHA 与聚合 SHA 比较的定义性假阴性，非阻断），`C16_window_requested`/`C19_a1_runtime_constructor` NV（签名前不可执行），已在 C10 记录 triage。

## 4. flat/nested 修复（执行层，零物理）

- runtime:199 `def family_frozen_payload(row)`，:470/:582 使用；executor:1132 `mf = family_frozen_payload(fam_row)`；两 reader 均兼容 flat 与 nested，缺字段 fail-closed。
- A1 `_runtime_resolve` 等价检查保持（static vs runtime frozen_vspgeom_sha256；evaluator_v12.py:641-649 口径），未 spawn evaluator/solver。
- C17 证实修复仅执行层：plan 科学政策 34 字段逐字节相等、A1 全部冻结字节不变、caps/planned/seed/端点/停规则不变。

## 5. 零物理 gate 证据与等价性

| 证据 | SHA256 | 结果 |
|---|---|---|
| launcher 侧 gate | `31c6a3ac...`/19,666 | 79 checks PASS，static 119，guard all_equal，physical 0 |
| gate 原始报告 | `7d7d63a9...`/37,494 | 3 designs × 2 families，triples 6 |
| launcher gate selftest | `97ecd67f...`/4,611 | PASS |
| executor-own gate smoke | `e15776f1...`/13,041 | PREFROZEN_REUSE_GATE_PASS，static 119，freeze_builder_invocations=0，service_builds=0，physical 0，solver false，ledger false，copied_files 18 |
| executor gate 原始报告 | `ae098245...`/10,073 | 3 designs PAIR_READY/PREFROZEN_MANIFEST_REUSE/attempts 0 |
| A5 独立 replay（最终 executor 字节 c2bdfb68） | `1e759466...`/14,252 | PASS，static 119，designs 3，checks_all_true，run_dir unchanged，physical 0 |
| launcher smoke | `25649de1...`/13,019 | SMOKE_NO_SOLVER，gate PASS，physical 0 |

launcher/executor 两侧 gate 使用同一 R9 initial manifest（93a078e3）与同一 119 static index，role_map/fail-closed 行为等价；live 顺序为 `verify_execution_gate` → executor prestart gate 落盘 → `run_batch_executable`，gate FAIL 在 spawn 前抛 `PREFROZEN_REUSE_GATE_FAILED`。

## 6. 单测与失败关闭矩阵

- tests `106f90f5...`/55,397 B，含 `test_r9_family_frozen_payload_flat_and_nested`、`test_r9_prefrozen_gate_flat_nested_and_fail_closed_matrix`；pytest `9191b6f2...`/234 B：`-k "r2_ or r3_ or r5_ or r7_ or r9_"` → **16 passed / 31 deselected**，exit 0，零物理。
- 失败关闭覆盖：flat PASS、nested PASS、缺 frozen 字段 FAIL、SHA 篡改 FAIL、vkey/vsp3 sibling 缺失 FAIL、执行器 mf/rf 混合形状 PASS。

## 7. 身份不变量与历史排除

- A1：evaluator `f74a4752...`/58,291、freeze_api `31d78182...`/27,288、openvsp_model `c40b11df...`/36,902、design_space `8f9b893c...`/33,660、config `8b29d1e3...`/10,846、bundle `995bb12f...`/3,262——全部未变。
- R1–R7 已签 approvals 7/7 字节未变（r1 9e5c29b0、r2 eee7868a、r3 18865f8f、r4 6e2aebcf、r5 ca0bdc7b、r6 72b95e03、r7 1a552267）；R8 approval `fa0d94a2...`/75,166 B 未动，R8 run dir 15 文件只读（相对 62a6231 clean）。
- R1–R8 全部排除：charged 17 starts/119 internal（R1–R4 各 2/14、R5 0/0、R6 3/21、R7 6/42、R8 0/0），baseline 56/404；R9 计划 390/2,730，预计累计 446/3,134 ≤ caps 451/3,157（余量仅 5 starts/23 internal）。

## 8. 预算与记账

seq9 = `R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX`，physical_call_count_at_amendment=56；seq1–seq8 与 R8 已签逐字节相同。计划：preflight 2 + diagnostics 4 + main 384 = 390 starts，2,730 internal；reserve 64。任何超出已批准数字的物理消耗需新的 Lead 书面批准（不重试、不静默改预算）。

## 9. G-P2AV2R9-PRE 检查表（52/52 PASS）

| # | check | 结论 | 期望/实际（截断） |
|---|---|---|---|
| C01 | A2 R9 package commit resolves and contains the 8 package files | PASS | `resolved a4e9ded; 8 files in commit` / `a4e9ded2f358035eff2dd55965b4408cb89dc96a resolved; run_dir_entries=8; ` |
| C02 | disk bytes == commit blobs for all 8 package files | PASS | `8/8 identical (git diff --exit-code)` / `identical` |
| C03 | plan.json bytes/SHA | PASS | `3450034d/48,619` / `3450034d54960dcb2c06c61d84f87c9b67604a369d63264603d7d0907c8b84c4 / 486` |
| C04 | approval.DRAFT.json bytes/SHA | PASS | `b57f9f6c/52,781` / `b57f9f6c551159e0cb1be490bc46e441f69e0005b9de448693c2516314ce0517 / 527` |
| C05 | identity_binding.json file SHA and canonical identity_sha256 | PASS | `f2ae7ced/10,445 + canonical present` / `f2ae7ced21229e616eb2d572c1c823060ab0448e530e50d1adc42a30a9d9893b / 104` |
| C06 | initial_designs_manifest.json SHA/bytes and 3 initial designs | PASS | `93a078e3/14,822; 3 designs` / `93a078e3dcae1b7bf04e3f39a02632d87ef9fbcd26368dda4236ba8f517efe47 / 148` |
| C07 | prereg SHA + R9 addendum + no stale R8 addendum + R9 window/run text | PASS | `887f9880/17,578; R9 section` / `887f9880e6b9f53a5b99e2cddf9825b2a77fed2adc79dfd626a19e3a7e1be89b / 175` |
| C08 | dry_run.json and executor_dry_run.json SHAs/bytes | PASS | `ff54772e/10,930 ; d8e92cd9/2,438` / `ff54772e5e7d940408b457bfb4e856edb962d9cbb3c11e1312fa21d19f28573e / 109` |
| C09 | SHA256SUMS.txt self-consistency | PASS | `7/7 recomputed match` / `7/7 PASS; sums sha 2f5d3c6c890b209a0b1d1ce7d970b3a5e5ddfe21b037c0c550c` |
| C10 | package dry_run non-PASS checks triage | PASS | `C10 definitional FAIL only; C16/C19 NV; C23/C32 PASS` / `["C10_executor_sha"] / NV ["C16_window_requested","C19_a1_runtime_cons` |
| C11 | executor dry-run | PASS | `390 planned / 0 emitted / 2,730 internal / physical 0` / `{"status":"DRY_RUN_BLOCKED_NOT_APPROVED","planned":390,"emitted":0,"in` |
| C12 | R9 pre-execution run dir has no execution artifacts | PASS | `8 package files only; no cases/ledger/evaluations/approval.json/batch_` / `8 files; extra=[]` |
| C13 | DRAFT identity | PASS | `batch 14 / run R9 / window 17:30Z-11-12T04:00Z / token / planned 390-2` / `{"batch":"DREAL001-P2-20261111-14","run":"DREAL001-P2A2R9-20261111-01"` |
| C14 | DRAFT supersedes R8 signed approval | PASS | `fa0d94a2.../75,166 B / physical 56 / seq9` / `{"approval_path":"D:\\RCAIDE\\dnext001\\wt-real-a2-optimizers\\researc` |
| C15 | amendment_log seq1-seq8 == R8 signed history seq9 R9 fix at physical 56 | PASS | `{"draft_n":9,"equal_first_n":8,"seq9":{"seq":9,"action":"R9_PREFROZEN_` / `true` |
| C16 | R8 setup-stop facts disclosed | PASS | `SETUP_STOP_PREFROZEN_GEOM_MISSING; charged 0/0; launcher gate PASS` / `{"batch_id":"DREAL001-P2-20261111-13","run_id":"DREAL001-P2A2R8-202611` |
| C17 | flat/nested read fix is execution-layer only | PASS | `runtime family_frozen_payload; executor mf=family_frozen_payload(fam_r` / `{"executor_mf_flat":true,"runtime_helper":true,"static_guard":true}` |
| C18 | executor OWN prefrozen gate zero-physical smoke | PASS | `e15776f190a4721e75ae704ce05c009b331004fb172827c3dbf2622d1ec3bca9` / `{"status":"PREFROZEN_REUSE_GATE_PASS","static":119,"designs_ok":{"15":` |
| C19 | executor gate reuse evidence for 3 designs x 2 families | PASS | `PAIR_READY / PREFROZEN_MANIFEST_REUSE / attempts 0` / `{"status":"PREFROZEN_REUSE_GATE_PASS","static":119,"designs":[[15,"PAI` |
| C20 | launcher-side prefrozen gate + selftest PASS | PASS | `31c6a3ac70cd89eed6735736a1b5bff2a46b7030444552398cf9bf60dd2e3e54 / 7d7` / `{"status":"PASS","checks":79,"static":119,"physical":0}` |
| C21 | launcher-side and executor-side gates equivalent | PASS | `same static_index 119, same 3 designs, same manifest, guard all_equal` / `{"tool_static":119,"launcher_static":119,"launcher_guard":true,"triple` |
| C22 | flat/nested fail-closed unit test matrix + pytest green | PASS | `test_r9_family_frozen_payload_flat_and_nested, test_r9_prefrozen_gate_` / `{"n":45,"r9":["test_r9_family_frozen_payload_flat_and_nested","test_r9` |
| C23 | accounting: planned 390/2,730; cumulative 446/3,134 <= 451/3,157; headroom 5/23 | PASS | `{"planned_starts":390,"planned_internal":2730,"caps_starts":451,"caps_` / `{"planned_starts":390,"planned_internal":2730,"caps_starts":451,"caps_` |
| C24 | A1 frozen bytes unchanged | PASS | `evaluator f74a4752/58,291; freeze 31d78182/27,288; openvsp_model c40b1` / `{"evaluator":{"bytes":58291,"sha256":"f74a4752495fd6c5330edcaf7edb4bcb` |
| C25 | A2 R9 execution bytes | PASS | `{"executor":"c2bdfb6825d156b71713ad57b9c982ebc06ec5a08bbfadf4324839ce8` / `{"executor":"c2bdfb6825d156b71713ad57b9c982ebc06ec5a08bbfadf4324839ce8` |
| C26 | plan deep diff vs R8 limited to identity/history/derived whitelist; scientific policy equal | PASS | `369 leaf paths; outside=[]; policy_equal=true` / `{"stage":1,"batch_id":1,"canonical_batch_id":1,"run_id":1,"run_dir":1,` |
| C27 | cumulative budget | PASS | `prior 56/404 + R9 390/2,730 = 446/3,134 <= 451/3,157` / `{"planned_starts":390,"planned_internal":2730,"caps_starts":451,"caps_` |
| C28 | window / token / deadlines | PASS | `17:30Z-11-12T04:00Z / token / start 21:00Z / clean 02:30Z / hard 04:00` / `{"start_utc":"2026-11-11T17:30:00Z","end_utc":"2026-11-12T04:00:00Z","` |
| C29 | preflight authorization limited to PASS_BYTE | PASS | `PASS_NUMERIC not pre-authorized` / `{}` |
| C30 | R1-R7 signed approvals unchanged | PASS | `9ea/eee/188/6e2/ca0/72b/1a5` / `{"R1":{"bytes":38476,"sha256":"9e5c29b0ac482f36dc0d9bbe694a94afb7a3cf4` |
| C31 | R1-R8 excluded and charged counts disclosed | PASS | `R1-R4 2/14 each; R5 0/0; R6 3/21; R7 6/42; R8 0/0; total 17/119 prior ` / `{"keys":["r1","r2","r3","r4","r5","r6","r7","cumulative_charged","r8"]` |
| C32 | L-10 decision, Lead m02945 and A5 dissent recorded | PASS | `present in gate/conditions` / `{"lead_decision":"Lead m02945 (2026-11-11T17:19Z): R8 attempt-1 closed` |
| C33 | launcher bindings, safety pins, live gate order | PASS | `{"len":29320,"pins":{"executor":true,"plan":true,"identity":true},"pre` / `{"pins":{"executor":true,"plan":true,"identity":true},"prefixes":{"pre` |
| C34 | zero-physical launcher smoke | PASS | `25649de1df1f92296460f0b462c42c864c41abeba5907c94c52485b5992cf7ae` / `{"mode":"SMOKE_NO_SOLVER","gate":"PASS","checks":79,"static":119,"phys` |
| C35 | post-approval dry-run tool registered and physically inert | PASS | `3ae662660cabb93c6a0b01239395f47bb04e1d393447de6416741f5568d6a790` / `{"len":22322,"codes":45,"d43":true,"d44":true,"d45":true,"selftest":"P` |
| C36 | r9_addendum status / R8 reference / retained fixes | PASS | `{"status":"R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX","r8ref":{"batch_id":"DR` / `{"status":"R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX","r1_reference":{"batch_` |
| C37 | A5 signature conditions prepared | PASS | `52 items` / `52` |
| C38 | approval_refs_final 14 keys prepared | PASS | `14 keys; only a5_review/a2 anchors substituted at signature` / `["a1_bundle_commit","a1_bundle_commit_full","a1_bundle_manifest_sha256` |
| C39 | draft-to-signed delta whitelist | PASS | `9 top-level paths` / `["approved","approved_at_utc","approved_by","approval_refs","authoriza` |
| C40 | fail-closed unit tests for missing/tampered prefrozen bytes | PASS | `missing + tamper cases present` / `{"flat_nested":true,"fail_closed":true,"missing":true,"tamper":true,"s` |
| C41 | pytest R9 suite green | PASS | `16 passed / 31 deselected` / `"................                                                     ` |
| C42 | no stale R7/R8 identity text | PASS | `R9 addendum present; no R8 current run claim` / `{"r9add":true,"staleR8":false,"r8runCurrent":false}` |
| C43 | design-space binding retained | PASS | `A1 design_space 8f9b893c + config 8b29d1e3` / `{"ds":"8f9b893c13195c80ff1ee88598134e3f44fef0495452249780d114c9e0593b8` |
| C44 | GO / gate prefix bindings | PASS | `G-P2AV2R9-PRE:PASS / C-P2AV2R9-02:PASS:` / `{"pre":true,"c":true}` |
| C45 | static_index_count=119 | PASS | `119` / `{"tool":119,"launcher":119,"replay":119}` |
| C46 | 3 designs x 2 families prefrozen triples equal | PASS | `12/12 families` / `{"triples":6,"guard":true,"replay_designs":3,"replay_detail":3}` |
| C47 | R7 H1 evidence retained | PASS | `r7_verify_prefrozen json+py present` / `{"json":true,"py":true}` |
| C48 | no mesh QC data gate | PASS | `L-09 option B rejected` / `{"mesh_qc_gate":false}` |
| C49 | no winner/significance/cross-family; fuel null; physical NOT_VALIDATED | PASS | `not claimed` / `{"policy_equal":true,"endpoint":["E1","E2","E3","E4","E5","E6"],"stati` |
| C50 | no R10 default; R9 = last attempt | PASS | `no_r10_by_default true` / `{"noR10":true,"noR9":false}` |
| C51 | A5 physical_call_count=0 / solver_started=false | PASS | `0 / false` / `{"replay_physical":0,"replay_solver":false,"exec_smoke_physical":0}` |
| C52 | R9 pre-exec run dir exactly 8 files; R8 dir untouched | PASS | `8 files; R8 clean vs 62a6231` / `{"run":8,"extra":0,"r8_diff_exit":0,"r8_files":14}` |

## 10. 签署必须执行的更正（M1–M6）

- M1: replace the 8 placeholder approval_refs with the 14-key refs_final in this gate; a5_review must be the commit SHA of this G-P2AV2R9-PRE gate.
- M2: expand DRAFT conditions 15 -> exactly the 52 conditions in docs/reviews/dreal001_a5_p2av2r9_signature_conditions_20261111.json (byte-identical texts and order).
- M3: set status/approved/approved_by/approved_at_utc/authorization, window.status=APPROVED, and b2_waiver (APPROVED_BY_LEAD_FOR_THIS_BATCH_ONLY, approver, approved_at_utc, a5_pre_review_commit=gate commit).
- M4: amendment_log must remain byte-identical to the DRAFT (seq1-seq8 = R8 signed history; seq9 R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX at the DRAFT at_utc with physical_call_count_at_amendment=56).
- M5: no other binding or scientific-policy byte may change; A2 must commit the signed approval byte-identically, run the real post-approval dry-run with the bound R9 tool, then A5 C-P2AV2R9-02, then Lead GO; C gate hard line 18:45Z.
- M6: the R9 package must deliver (i) the two-line flat/nested read fix diff with unit tests (flat PASS/nested PASS/missing FAIL/tampered SHA FAIL/missing vkey-vsp3 sibling FAIL/executor mf-rf mixed-shape PASS), (ii) zero-physical evidence from the executor OWN _prefrozen_reuse_gate code path on the real R9 initial manifest (PASS, static 119, no FreezeBuilder, physical 0, no cases/ledger), and (iii) launcher-side gate equivalence report; A5 independently replays the executor gate with physical=0 before signing; if any item is missing the Lead must record an explicit evidence-quality debt acceptance in the signed approval.

## 11. 签署绑定 refs_final（14 键）

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
  "a2_execution_code": "c2bdfb6825d156b71713ad57b9c982ebc06ec5a08bbfadf4324839ce8625af54",
  "a2_package_commit": "a4e9ded2f358035eff2dd55965b4408cb89dc96a",
  "a5_review": "A5 G-P2AV2R9-PRE gate commit (placeholder; Lead substitutes the committed gate SHA at signature)"
}
```

## 12. 签署条件（52 条）

签署时 approval.conditions 必须与 `docs/reviews/dreal001_a5_p2av2r9_signature_conditions_20261111.json` 的 52 条**逐字节相同且同序**；DRAFT 的 15 条与占位 refs 必须整体替换。条件覆盖：R3-BASE-01..39（协议 D/冻结/预检/端点/停规则/记账/身份）、R1-HIST-01、R1-02、R1-03、R9-PKG-01、R9-PREFROZEN-FLAT-01、R9-EXECGATE-01、R9-ACCT-01、R9-HIST-01、R9-WINDOW-01、R9-DECISION-01、R9-REFS-01、R9-SIGN-01、R9-DISC-01。

## 13. 披露（D1–D10）

- D1: R1-R8 series exclusion: charged 17 starts/119 internal (R1-R4 2/14 each, R5 0/0, R6 3/21, R7 6/42, R8 0/0 setup stop); cumulative baseline 56/404; R9 plan 390/2730; projected cumulative 446/3134 vs caps 451/3157; headroom only 5 starts/23 internal.
- D2: R8 attempt-1 setup stop facts: launcher-side prefrozen gate PASS (79 checks, static_index_count=119, a1_runtime_guard all_equal, 6 triples), prestart evidence written, then executor own _prefrozen_reuse_gate raised FreezeRecordError PREFROZEN_GEOM_MISSING for d51866f7d3c49303/462x401 because the initial_designs_manifest family rows store frozen fields FLAT while runtime:574 and executor:1131 read nested "frozen"; 0 physical, no cases/ledger/solver_attempts/preflight/batch/evaluations; run dir 15 files, read-only; R8 charged 0/0 and excluded in full.
- D3: R9 flat/nested fix is execution-layer only and zero-physical: A1 bytes unchanged, plan scientific fields unchanged, no solver started to verify it; correctness is byte/canonical equality only and is not a solve claim.
- D4: Manifest field facts: initial_designs_manifest family rows are FLAT (frozen_vspgeom_path/sha256/bytes, frozen_vkey_sha256, frozen_vsp3_sha256, canonical_mesh_sha256); A1 family_pair_manifest records are NESTED under families[label].frozen; no frozen_vkey_path/frozen_vsp3_path fields exist; vkey/vsp3 are siblings model.vkey/model.vsp3 of frozen_vspgeom_path; static_index_count=119; a static-index hit not resolved via PREFROZEN_MANIFEST_REUSE must fail closed.
- D5: design15 f1 462x401 prefrozen bytes previously produced an all-NaN polar in R6; an R9 main first-case INVALID_NUMERICAL is possible; protocol D tolerance applies to scientific invalids only and requires per-arm invalid counts, per-case status/polar SHA/reason, invalid-ratio time series and separate diagnostic reporting; mechanism NOT proven and no mesh QC data gate adopted.
- D6: Accounting pseudo-count fixes retained: no default 7 internal on 0-start rows; batch_summary per-phase and total; diagnostics polar_sha256 extracted; charged+planned<=caps assertion fail-closed. R8 charged 0/0 keeps cumulative at 56/404.
- D7: C10_executor_sha remains a definitional false negative in package dry_run.json (executor file SHA vs recomputed aggregate digest), present since R1, non-blocking; C16/C19 are NV by design; spawn exit_code/stdout_tail persistence remains a future improvement.
- D8: R9 is the last execution attempt under the caps: no R10 by default; a further setup or main failure ends the series with an A5-signed receipt stating P2a pilot NOT_RUN / NOT_COMPUTABLE, R1-R8+R9 exclusion, fuel_burn_kg=null, physical NOT_VALIDATED.
- D9: A5 physical_call_count=0 and solver_started=false; this gate is not an execution authorization; after signature the real dry-run, A5 C-P2AV2R9-02 and Lead GO remain mandatory; R9 pre-exec run dir must contain exactly the 8 package files plus signed approval and dry-run evidence (no cases/ledger/batch_summary/stop_report); no R9 execution may start after the approved window.
- D10: R9 supersedes R8 approval fa0d94a2.../75,166 B; R7 approval 1a552267.../69,405 B and all R1-R6 approvals remain read-only historical bytes; no approval is reusable across batches.

## 14. 签署后流程与时间硬线

1. Lead 按 M1–M6 签署 approval（signed 字节与 DRAFT 仅 9 个允许顶层字段不同）；
2. A2 将 signed approval 单文件字节 commit，并用绑定的 R9 dry-run 工具 `3ae66266...`/22,322 B（D01–D45，含 D43 run-dir-preexec-clean、D44 setup-path-zero-physical、D45 addendum-bound-to-R8）跑**真实** post-approval dry-run（期望 45/45、390 planned/0 emitted/2,730 internal、physical 0、无 cases/ledger）；
3. A5 出 C-P2AV2R9-02（硬线 18:45Z），PASS 仅表示可 GO，不代表执行授权；
4. Lead 发 GO token 后 launcher 才可在 window 内启动；任何窗口外/未绑定 token 的启动由 launcher 拒绝。

## 15. A5 签署声明

A5 以独立复核身份声明：本门禁基于磁盘/commit 字节实测（非转述），52/52 checks PASS；R8 零物理 SETUP_STOP 根因成立且 R8 全量排除；flat/nested 修复仅为执行层、A1 与科学政策字节不变、且由 executor 自身代码路径在真实 R9 manifest 上零物理验证（A5 另行独立 replay 通过）；累计预算 446/3,134 在 caps 451/3,157 内（余量 5/23）。本门禁不构成本轮真实 VSPAERO 授权，亦不宣布任何 winner/显著性/跨族比较；A5 physical_call_count=0。

---

A5 生成文件：本 md、同目录 JSON、`dreal001_a5_p2av2r9_signature_conditions_20261111.json`。签署时 a5_review 必须替换为本 gate 的 commit SHA。
