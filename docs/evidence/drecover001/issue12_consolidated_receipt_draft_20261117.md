# Issue #12 合并回执（草案，未发布）

> **状态：DRAFT / NOT POSTED。** 本文件是 Lead 准备的唯一中文合并回执草案，用于在取得 GitHub 连通与提交身份后一次性发布到 Issue #12。它不是已发布的回执，任何自动化流程不得把它当作业已完成或门禁已签。A5 审查已由 Owner 授权的 deepseek-flash 只读子智能体执行并记录 `CHANGES_REQUIRED`（非人类签名）；发布前仍须 Owner 接受该结果并核对本文件与证据 JSON 的一致性。

- 日期：2026-11-17（本地）；仓库：`QingYangJin/RCAIDE_Supersonic`；基线：`4c51c7df34c9626999ef2e66e5a6c76a2b9c92e2`。
- 分支 / worktree：`recovery/drecover001-20261117`（D:\RCAIDE\.worktrees\drecover001-20261117）。
- 远端 commit / ref：**无**。本机无 git author identity，且 git 无法访问 github.com（本轮复核：`schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)`；另见 connection timeout / connection reset，详见 `github_connectivity_check_20261118.md`）；未 fetch、未 push、未合并 main，未触碰 PR #3/#6。本地变更清单：[recovery_change_manifest.json](recovery_change_manifest.json)（127 文件；逐文件 SHA256/字节见清单，未提交）。
- 门禁状态：`R0_PARTIAL_NOT_AUDITED`、`R1_SOFTWARE_IN_PROGRESS_NOT_AUDITED`、`NO_PHYSICAL_GO`。A5 审查：已由 Owner 授权的 deepseek-flash 子智能体完成只读审查，verdict=`CHANGES_REQUIRED`（`a5_review_verdict.json` / `a5_review_transcript.json`）；它不是人类签名，Lead 未自签。异机备份要求已由 Owner 豁免（`WAIVER-OFFMACHINE-BACKUP-20261118`，m03569）。

## 本轮恢复内容

1. **R0 清单（未签）**：20 个远端固定 head、0 tags、200 个可达提交、4,633 对象、2,829 唯一 blob、186,537,818 字节、2,760 条历史路径逐字节审计；基线 2,109 文件 / 164,917,591 字节与 Git blob 一致；docs checksum 162 MATCH / 2 MISSING / 0 MISMATCH。
2. **R0 来源扩展（本轮新增，离线）**：batch2 之外的 25 个 budget/ledger 源、58 个 raw solver 输出、62 个 solver 日志、157 个输入 deck 完成 provenance 分类；未发现额外可恢复 raw；F1R2/F2R2 原始 raw 确认 `RAW_LOST`；历史账本仅作 provenance 记录（d12d004 4/2/4、v1 4/0/4、v1b 2/0/2、batch2 8/0/8；authoritative flag=0，唯一启发式分歧已披露）。证据：[r0_provenance_extension.json](r0_provenance_extension.json)（330,839B / `b553857c…`）、[r0_provenance_extension_20261117.md](r0_provenance_extension_20261117.md)。
3. **R1 软件侧（未签）**：新 TaskSpec/MetaDataset/MetaTrainer/AdaptationRunner/WarmStartSampler/ValidationSelector 合同；绝对 XForm 写读回、12D 掩码、Sref/升力 Di_N、账本所有权与不可变预留、BO/DE/PSO 反馈接线等修复；真实准入保持 fail-closed（`REAL_ADMISSION_NOT_IMPLEMENTED`）。本轮另修复 M1 批次结算异常的 fail-closed 路径：`settle`/`register_evaluation` 抛错时强制停止未结算预留、行状态覆盖为 `failed`/`objective=null`/`failure_kind=ACCOUNTING_VIOLATION`，并新增 1 项回归（M1 套件 20 项），使 `summary.accounting_resolved=false` 且未结算预留进入 unresolved，不再可能误报对账完成。另修复账本 `accounting_resolved` 的 open-reservation fail-open：未结算预留（`starts_reserved>0`）不再被视为已对账，`assert_conserved` 明确拒绝并新增 1 项账本回归（套件 229 项）。另修复 `TaskSpec` 数值表示 fail-open：`mach=1` 与 `1.0`、`altitude=0.0` 与 `-0.0` 曾产生不同 `physics_sha256`，同一物理条件可被当成新任务；现统一转 float、拒绝非有限值并把 signed zero 规范为 `0.0`，新增 2 项回归（同物理条件唯一身份、数值 clone 必须拒绝）。本轮另修复 evaluator 异常分支的 stop fail-open：`_stop_reservation` 若在 quarantine 阶段抛错，旧实现会直接抛出、没有结构化结果；现捕获并转 `STOPPED_ACCOUNTING_VIOLATION` + `failure_kind=ACCOUNTING_VIOLATION`，保留 open reservation（新增 1 项回归）。MetaDataset 同时要求 failed observation 的 `cl`/`cdi` 也为空（新增 1 项回归）。
4. **M0/MAML 就绪（离线）**：M2 rehearsal `run_id=DRECOVER001-M2-REHEARSAL-20261117T160233Z`，16D 条件特征、K=0/4/10、验证早停均跑通，`SOFTWARE_FIXTURE_TRAINING_ONLY`；`production.py` 已补 `ConditionalPretrainer`/`ConditionalAdaptationRunner` fixture-only 生产入口，真实准入门仍 fail-closed；M1 批次控制路径 `run_id=DRECOVER001-M1-SOFTWARE-20261118T000000Z`，18 fixture（6 任务身份 × 3 设计）physical=0 / simulated=18 / internal=126 / charged=18，回执标记 `STRUCTURAL_SOFTWARE_FIXTURE_NOT_A_REAL_GO`。
5. **软件回归**：`run_id=DRECOVER001-SOFTWARE-20261118T062546Z`，230 tests / 0 failed / 0 error / 0 skipped；preflight 自身记录的 `a5_independent_review=NOT_PERFORMED`（该字段由 preflight 运行前固定，不代表 A5 未执行）、`physical_go=NOT_ISSUED`、`backup_restore=NOT_ESTABLISHED`。
6. **恢复门禁就绪矩阵（本轮新增，离线只读）**：聚合器 [assess_recovery_readiness.py](assess_recovery_readiness.py) 输出 [recovery_readiness.json](recovery_readiness.json) / [recovery_readiness.md](recovery_readiness.md)，`status=RECOVERY_READINESS_GATES_CLOSED_EXPECTED`、8 gate（6 `CLOSED` + 1 `CLEAN` + 1 `WAIVED`）、`violations=0`、`blockers=8`；只证明证据一致、门禁仍按预期关闭，不是 A5 签署。
7. **数据完整性修复**：`needed_for_next_run.json` 的 R1 `required` 文本曾被历史编辑截断为非法 JSON；已恢复合法 JSON，丢失尾部在 `integrity_note` 标为 UNKNOWN，并新增聚合器 JSON 解析校验与 1 项回归测试。
8. **A5 审查包**：已生成只读 `a5_review_packet.json` / `.md`（22 项证据逐 SHA、门禁状态与检查清单），并由 Owner 授权的 deepseek-flash 子智能体实际执行只读审查（16 步工具调用，HTTP 524 中断后用自身 transcript 的 compact digest 出结论）；verdict=`CHANGES_REQUIRED`，两项 major（同机恢复缺少显式标签、packet 备份门禁状态与豁免冲突）已在本轮修复。Lead 未自签、未授予 GO。复核步骤已限定为非破坏性命令并排除会改写 run_id 的 preflight；实际按序执行后 19 项证据 SHA256 全部不变，R0 自检脚本重复运行也字节一致。

## 六口径记账（本轮，真实物理 0）

| 口径 | 数值 |
|---|---|
| physical_solver_starts_actual | 0 |
| internal_solver_cases_actual | 0 |
| simulated_solver_starts_actual（fixture，不计物理） | 18 |
| simulated internal cases（fixture） | 126 |
| charged_planned_reserved | 0 |
| design_evaluations | 0（真实）；fixture 18 |
| cached_reads | 0 |
| admitted_scientific_labels | 0 |

历史 Issue #10 的 actual=65/455、charged=70/490 保持原样，仅 `REPORT_PRESENT`，未重新验证，不得当作本轮成本。

## raw 备份与恢复

- 本机 bundle SHA256：`aad87db09a166105535016e38411842f20b424d82d7b62de83208cdb0cd9e9f4`，58,105,510 字节；同机新目录恢复 2,222 文件（136 overlay）、230 项测试通过，重训 checkpoint 与 holdout 精确一致；bundle 内嵌 manifest 的 2,222 项路径/SHA256/字节逐项复验通过（manifest SHA `a93143cb040f118e486a1931d3bb1f8d4bf22147e19f70148e3de39960ffcb78`）；恢复后证据链（83 个证据文件）经两轮 R0 provenance + M1 batch verifier、readiness 与 A5 packet 校验（`evidence_verifiers` 两项 status 均 ok），`bundle_manifest_verified=true`、`evidence_chain_verified=true`、`readiness_status=RECOVERY_READINESS_GATES_CLOSED_EXPECTED`（6 CLOSED+1 CLEAN+1 WAIVED）、`packet_check_problems=[]`；receipt `off_machine_backup=false`、`backup_label=SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP`、`owner_waiver=WAIVER-OFFMACHINE-BACKUP-20261118`。注：bundle 内嵌文档快照记录的是构建前的上一版 SHA/run_id，内嵌 readiness/packet 也是构建前快照；恢复后 `run_local_restore.py` 会按 bundle 字节重算 readiness 与 A5 packet 并记录到外部 receipt，权威身份以本回执与外部 receipt 为准。
- `off_machine_backup=false`、`backup_label=SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP`、`independent_failure_domain=false`、`backup_restore_pass=false`：**没有异机备份，没有实际异机恢复证明**；Owner 已豁免异机故障域要求（m03569），但同机恢复仍不等同于备份，BACKUP_RESTORE_PASS 未签。

## 源码差异摘要

- 新增：`dreal001/meta/{task_spec,meta_dataset,m1_batch,...}.py`、对应 tests（230 项套件）、证据与审计脚本；修改 18 个 tracked 源码文件（几何校验、12D 配置、evaluator、优化器 arms/evaluators/ledger/p2a*、GPU 探测、M5/M6、A5 审计、几何测试）。
- 未删除历史 Issue、未覆盖旧跑数、未把重生成文件冒充旧 raw（重生成件标 `REGENERATED_FROM_SPEC`，新身份）。

## 负结果（原样保留）

旧 S1/S2/S3 与 M0R 的负结果、`NOT_COMPUTABLE`、`PHYSICS_VALIDATED=NOT_VALIDATED` 均保留，不追认为正结果；历史 `verified=true` 仅是历史叙述。

## 下一门禁

1. Owner 接受 A5 子智能体 verdict（当前 `CHANGES_REQUIRED`，两项 major 已修复）后，R0 收口仍不能自签 `RECOVERY_INVENTORY_PASS`；如需要人类签署，须由 Owner 或授权审阅者给出。
2. 管理员提供 git 提交身份与 GitHub 连通后，推送分支并发布本回执；远端复核 SHA。
3. ~~批准独立故障域存储并签 BACKUP_RESTORE_PASS~~：Owner 已豁免异机备份（m03569）；保留同机 bundle/恢复证据与显式标签，不再要求异机签名。
4. 上述通过后由 A5/Lead 记录 `RESTORED_CODE_BASELINE_PASS`（A5 结果须标为 deepseek-flash 子智能体 verdict、非人类签名）；再由 A5/Lead 预注册 R2 最小矩阵，Lead 逐批 `GO`。
5. 真实准入（REAL_ADMISSION）在 R2 首个真实 batch 前实现并验证；在此之前 physical 保持 0。

**本草案不授予任何预算、不构成 A5 签署、不替代 Issue 回执。**