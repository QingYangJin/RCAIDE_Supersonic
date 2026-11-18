# Issue #12 合并回执（草案，未发布）

> **状态：DRAFT / NOT POSTED。** 本文件是 Lead 准备的唯一中文合并回执草案，用于在 Owner 接受 A5 结论后一次性发布到 Issue #12（GitHub 推送已可通过 API 完成，但本文件尚未发布）。它不是已发布的回执，任何自动化流程不得把它当作业已完成或门禁已签。A5 审查已由 Owner 授权的 deepseek-flash 只读子智能体执行并记录 `CHANGES_REQUIRED`（非人类签名）；发布前仍须 Owner 接受该结果并核对本文件与证据 JSON 的一致性。

- 日期：2026-11-18（Issue #12 修订后）；仓库：`QingYangJin/RCAIDE_Supersonic`；新基线：`01c9274801474c113a2c488e375d451bcd0297c3`。
- 分支 / worktree：`recovery/drecover001-20261117`（D:\RCAIDE\.worktrees\drecover001-20261117）。
- 远端 commit / ref：`recovery/drecover001-20261117` @ `f367b8e4230902cd72f88a093411f635f4563f19`（tree `529d016da29862988e6e5f010e018a0fa8654829`，parent `01c9274`，36 文件 / 4,234,995 字节；经 GitHub Data API 推送，并用本地临时 index `git write-tree` 得到相同 tree、抽查 blob 逐字节一致；main 未动，未触碰 PR #3/#6）。此前快照 `01c9274`（tree `8b2be0a4…`）是同一恢复分支的上一版。本地 worktree HEAD 仍为 `01c9274` 且带有与远端快照内容相同的未提交改动；CLI git 传输仍无凭据（`SEC_E_NO_CREDENTIALS`），推送经 API。变更清单：[recovery_change_manifest.json](recovery_change_manifest.json)（30 文件；逐文件 SHA256/字节见清单）。
- 门禁状态：`RECOVERY_READINESS_GATES_CLOSED_EXPECTED`（9 gates = 7 CLOSED + 1 CLEAN + 1 WAIVED，blockers=9，`CLOSED` 不等于 PASS）、`NO_PHYSICAL_GO`。A5 审查：Owner 授权的 deepseek-flash 只读子智能体对上一快照给出 verdict=`CHANGES_REQUIRED`（`a5_review_verdict.json` / `a5_review_transcript.json`），两项 major 已修复；新快照 `f367b8e4` 尚未复审。它不是人类签名，Lead 未自签。异机备份要求已由 Owner 豁免（`WAIVER-OFFMACHINE-BACKUP-20261118`，m03569）。

## 本轮恢复内容

1. **R0 清单（未签）**：20 个远端固定 head、0 tags、200 个可达提交、4,633 对象、2,829 唯一 blob、186,537,818 字节、2,760 条历史路径逐字节审计；基线 2,109 文件 / 164,917,591 字节与 Git blob 一致；docs checksum 162 MATCH / 2 MISSING / 0 MISMATCH。
2. **R0 来源扩展（本轮新增，离线）**：batch2 之外的 25 个 budget/ledger 源、58 个 raw solver 输出、62 个 solver 日志、157 个输入 deck 完成 provenance 分类；未发现额外可恢复 raw；F1R2/F2R2 原始 raw 确认 `RAW_LOST`；历史账本仅作 provenance 记录（d12d004 4/2/4、v1 4/0/4、v1b 2/0/2、batch2 8/0/8；authoritative flag=0，唯一启发式分歧已披露）。证据：[r0_provenance_extension.json](r0_provenance_extension.json)（330,839B / `b553857c…`）、[r0_provenance_extension_20261117.md](r0_provenance_extension_20261117.md)。
3. **R1 软件侧（未签）**：新 TaskSpec/MetaDataset/MetaTrainer/AdaptationRunner/WarmStartSampler/ValidationSelector 合同；绝对 XForm 写读回、12D 掩码、Sref/升力 Di_N、账本所有权与不可变预留、BO/DE/PSO 反馈接线等修复；真实准入保持 fail-closed（`REAL_ADMISSION_NOT_IMPLEMENTED`）。本轮另修复 M1 批次结算异常的 fail-closed 路径：`settle`/`register_evaluation` 抛错时强制停止未结算预留、行状态覆盖为 `failed`/`objective=null`/`failure_kind=ACCOUNTING_VIOLATION`，并新增 1 项回归（M1 套件 20 项），使 `summary.accounting_resolved=false` 且未结算预留进入 unresolved，不再可能误报对账完成。另修复账本 `accounting_resolved` 的 open-reservation fail-open：未结算预留（`starts_reserved>0`）不再被视为已对账，`assert_conserved` 明确拒绝并新增 1 项账本回归（套件 229 项）。另修复 `TaskSpec` 数值表示 fail-open：`mach=1` 与 `1.0`、`altitude=0.0` 与 `-0.0` 曾产生不同 `physics_sha256`，同一物理条件可被当成新任务；现统一转 float、拒绝非有限值并把 signed zero 规范为 `0.0`，新增 2 项回归（同物理条件唯一身份、数值 clone 必须拒绝）。本轮另修复 evaluator 异常分支的 stop fail-open：`_stop_reservation` 若在 quarantine 阶段抛错，旧实现会直接抛出、没有结构化结果；现捕获并转 `STOPPED_ACCOUNTING_VIOLATION` + `failure_kind=ACCOUNTING_VIOLATION`，保留 open reservation（新增 1 项回归）。MetaDataset 同时要求 failed observation 的 `cl`/`cdi` 也为空（新增 1 项回归）。
4. **M0/MAML 就绪（离线）**：M2 rehearsal `run_id=DRECOVER001-M2-REHEARSAL-20261117T160233Z`，16D 条件特征、K=0/4/10、验证早停均跑通，`SOFTWARE_FIXTURE_TRAINING_ONLY`；`production.py` 已补 `ConditionalPretrainer`/`ConditionalAdaptationRunner` fixture-only 生产入口，真实准入门仍 fail-closed；M1 批次控制路径 `run_id=DRECOVER001-M1-SOFTWARE-20261118T000000Z`，18 fixture（6 任务身份 × 3 设计）physical=0 / simulated=18 / internal=126 / charged=18，回执标记 `STRUCTURAL_SOFTWARE_FIXTURE_NOT_A_REAL_GO`。
5. **软件回归**：`run_id=DRECOVER001-SOFTWARE-20261118T102149Z`，247 tests / 0 failed / 0 error / 0 skipped；preflight 自身记录的 `a5_independent_review=NOT_PERFORMED`（该字段由 preflight 运行前固定，不代表 A5 未执行）、`physical_go=NOT_ISSUED`、`backup_restore=NOT_ESTABLISHED`。
6. **恢复门禁就绪矩阵（本轮新增，离线只读）**：聚合器 [assess_recovery_readiness.py](assess_recovery_readiness.py) 输出 [recovery_readiness.json](recovery_readiness.json) / [recovery_readiness.md](recovery_readiness.md)，`status=RECOVERY_READINESS_GATES_CLOSED_EXPECTED`、9 gate（7 `CLOSED` + 1 `CLEAN` + 1 `WAIVED`）、`violations=0`、`blockers=9`；只证明证据一致、门禁仍按预期关闭，不是 A5 签署。
7. **数据完整性修复**：`needed_for_next_run.json` 的 R1 `required` 文本曾被历史编辑截断为非法 JSON；已恢复合法 JSON，丢失尾部在 `integrity_note` 标为 UNKNOWN，并新增聚合器 JSON 解析校验与 1 项回归测试。
8. **A5 审查包**：已生成只读 `a5_review_packet.json` / `.md`（36 项证据逐 SHA、门禁状态与检查清单），并由 Owner 授权的 deepseek-flash 子智能体实际执行只读审查（16 步工具调用，HTTP 524 中断后用自身 transcript 的 compact digest 出结论）；verdict=`CHANGES_REQUIRED`，两项 major（同机恢复缺少显式标签、packet 备份门禁状态与豁免冲突）已在本轮修复。Lead 未自签、未授予 GO。复核步骤已限定为非破坏性命令并排除会改写 run_id 的 preflight；实际按序执行后全部证据 SHA256 不变，R0 自检脚本重复运行也字节一致。
9. **2026-11-18 修订后的 R0 新基线**：停止旧历史数据搜寻并归档 `RAW_LOST`；[new_baseline_manifest.json](new_baseline_manifest.json) 固定 `base_commit=01c9274801474c113a2c488e375d451bcd0297c3`（tree `8b2be0a4…`）、16 个关键源码 SHA256、新 run/batch/geometry/task_family 身份策略与 `REGENERATED_FROM_SPEC`/`NEW_PHYSICAL_RUN` 允许来源；旧几何 `d20ee7ad…`、旧 checkpoint 与旧报告明确不可复用。
10. **R1 A1 几何/参考合同冻结 v2**：[geometry_freeze_v2.json](geometry_freeze_v2.json) 与验证器 [verify_geometry_freeze_v2.py](verify_geometry_freeze_v2.py)，`status=GEOMETRY_FREEZE_V2_VERIFIED`、101 项检查 0 失败、模型边界 24/24 + 真实 OpenVSP 边界 24/24；`freeze_id=GBFREEZE2-5f2bb12fe8b1dc68`、`geometry_contract_sha256=5f2bb12f…`；Sref 358.25 m²、Cref 18.489893 m、Bref 25.604638 m、q 20483.940233 Pa、CL_target 0.18174391742；真实 VSP3/STL/STEP 导出及逐件 STL 位置校验通过。开放项：质量/CG/AC 仍 `PROVISIONAL_NOT_FROZEN`，`XCG_M=16.821978259514246` 是主翼局部 AC 而非全局 30.821978259514246，力轴符号须 R2 VSPAERO 读回验证。
11. **R1 A3 真实准入协议**：新增 [real_admission.py](../../../research/concorde_metaopt/dreal001/meta/real_admission.py) 与 17 项 fixture 测试；`RealAdmissionManifest` 逐文件校验 mesh/deck/polar/history 的路径、字节与 SHA256，绑定 task/design/geometry/evaluator/audit，成功路径必须从原始 polar 同升力行取得 `D_i_N=q·Sref·CDi`，失败求解只给 `objective=null`；`AdmissionCertificate` 只能由模块私有 issuer 签发并复核 D_i_N 恒等式；`MetaDataset.require_real_admission()` 只在每行都有匹配证书时放行，否则仍抛 `REAL_ADMISSION_NOT_IMPLEMENTED`（未删除 guard）。尚无真实 raw 准入，测试全部是 synthetic bytes。
12. **R1 A2 可执行反馈闭环（软件 rehearsal）**：[a2_feedback_rehearsal.json](a2_feedback_rehearsal.json) 走真实 `ArmHarness`/GP-BO 路径（`MockLiftMatchEvaluator` + ledger + cache + label store），6 次评价、physical 0；交换前两次反馈会使第 3 个 proposal 改变，失败设计 objective 为 null；仅软件反馈证据，不是物理闭环。

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

- 本机 bundle SHA256：`80cd0697fdd29a72328820e4044222e785346cbd43f7367d12495f127273c716`，58,418,755 字节；同机新目录恢复 2,241 文件（79 overlay）、247 项测试通过，重训 checkpoint 与 holdout 精确一致；bundle 内嵌 manifest 的 2,241 项路径/SHA256/字节逐项复验通过（manifest SHA `380f66f493b9b393fa67090db63e9b4c64ee87687edef9f440c72baa554a30ec`）；恢复后证据链（98 个证据文件）经两轮 R0 provenance + M1 batch verifier、readiness 与 A5 packet 校验（`evidence_verifiers` 两项 status 均 ok），`bundle_manifest_verified=true`、`evidence_chain_verified=true`、`readiness_status=RECOVERY_READINESS_GATES_CLOSED_EXPECTED`（7 CLOSED+1 CLEAN+1 WAIVED）、`packet_check_problems=[]`；receipt `off_machine_backup=false`、`backup_label=SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP`、`owner_waiver=WAIVER-OFFMACHINE-BACKUP-20261118`。注：bundle 内嵌文档快照记录的是构建前的上一版 SHA/run_id，内嵌 readiness/packet 也是构建前快照；恢复后 `run_local_restore.py` 会按 bundle 字节重算 readiness 与 A5 packet 并记录到外部 receipt，权威身份以本回执与外部 receipt 为准。
- `off_machine_backup=false`、`backup_label=SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP`、`independent_failure_domain=false`、`backup_restore_pass=false`：**没有异机备份，没有实际异机恢复证明**；Owner 已豁免异机故障域要求（m03569），但同机恢复仍不等同于备份，BACKUP_RESTORE_PASS 未签。

## 源码差异摘要

- 新增：`dreal001/meta/{task_spec,meta_dataset,m1_batch,real_admission,...}.py`、对应 tests（247 项套件）、新基线/几何冻结/A2/A3 证据与审计脚本；本轮远端快照共 36 个路径（19 个已跟踪文件修改 + 17 个新增）。
- 未删除历史 Issue、未覆盖旧跑数、未把重生成文件冒充旧 raw（重生成件标 `REGENERATED_FROM_SPEC`，新身份）。

## 负结果（原样保留）

旧 S1/S2/S3 与 M0R 的负结果、`NOT_COMPUTABLE`、`PHYSICS_VALIDATED=NOT_VALIDATED` 均保留，不追认为正结果；历史 `verified=true` 仅是历史叙述。

## 下一门禁

1. Owner 接受 A5 子智能体 verdict（当前 `CHANGES_REQUIRED`，两项 major 已修复）后，R0 收口仍不能自签 `RECOVERY_INVENTORY_PASS`；如需要人类签署，须由 Owner 或授权审阅者给出。
2. A5/授权审阅者对远端快照 `f367b8e4…` 复审（当前 verdict 针对上一快照 `01c9274`）；是否把本回执发布到 Issue #12 由 Owner 决定并接受 A5 结论。
3. ~~批准独立故障域存储并签 BACKUP_RESTORE_PASS~~：Owner 已豁免异机备份（m03569）；保留同机 bundle/恢复证据与显式标签，不再要求异机签名。
4. 上述通过后由 A5/Lead 记录 `RESTORED_CODE_BASELINE_PASS`（A5 结果须标为 deepseek-flash 子智能体 verdict、非人类签名）；再由 A5/Lead 预注册 R2 最小矩阵，Lead 逐批 `GO`。
5. 真实准入（REAL_ADMISSION）在 R2 首个真实 batch 前实现并验证；在此之前 physical 保持 0。

**本草案不授予任何预算、不构成 A5 签署、不替代 Issue 回执。**