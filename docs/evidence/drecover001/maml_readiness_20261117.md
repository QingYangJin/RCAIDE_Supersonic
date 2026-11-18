# MAML 训练就绪度（软件侧）：已完成、门禁与阻断项

日期：2026-11-17；分支：`recovery/drecover001-20261117`；基线：`4c51c7df34c9626999ef2e66e5a6c76a2b9c92e2`。
本文件回答一个问题：**现在能不能开始 MAML 训练？** 答案是分层的：

- **离线 rehearsal（零物理、合成标签）**：已就绪，可重复运行并产出可核验回执；
- **真实任务 MAML 训练（R2 / #11 M1–M2）**：**不可开始**。R0/R1 仍未获人类 A5 签署（仅有一个 deepseek-flash 子智能体 verdict=`CHANGES_REQUIRED`）；异机备份按 Owner m03569 豁免，同机恢复有显式标签；真实准入与新的 R2 门禁均未建立。
- **物理求解器启动次数：0**（本轮新增 0，累计本轮恢复 0）。

## 1. 已完成（软件侧，可复跑）

| 项 | 内容 | 证据 |
|---|---|---|
| R1 合同模块 | `TaskSpec` / `MetaDataset` / `MetaTrainer` / `AdaptationRunner` / `WarmStartSampler` / `ValidationSelector`，全部 fail-closed；真实准入协议已实现（manifest + 逐文件 SHA + 同升力 `D_i_N` + 证书 issuer），无真实 raw 时仍抛 `REAL_ADMISSION_NOT_IMPLEMENTED` | `research/concorde_metaopt/dreal001/meta/{task_spec,meta_dataset,production,validation_training,real_admission}.py` |
| 条件特征生产入口（软件） | `ConditionalPretrainer.fit` / `ConditionalAdaptationRunner.predict`：16D = 12D 归一化设计 + 4D 任务上下文；真实模式先过 fail-closed 门禁；仅 fixture 执行，`SOFTWARE_FIXTURE_CONDITIONAL_ONLY` | `production.py`、`test_recovery_meta_contracts.py` |
| 离线 MAML rehearsal | 6 个真实任务物理身份（T18K 系列，Mach 1.80–2.20 / CL 0.17–0.19，split=meta_train/val/test）+ 合成标签；FOMAML、池化预训练、16D 条件特征预训练、random-init、K=0/4/10 评估、验证早停、checkpoint | [m2_offline_rehearsal_receipt.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/m2_offline_rehearsal_receipt.json>)、[m2_offline_rehearsal_checkpoint.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/m2_offline_rehearsal_checkpoint.json>) |
| M1 批次控制路径 | `BatchAuthorization`/`WorkItem`/`BatchPlan`/`run_batch`：`physical_go=False`、A5/Lead 占位符、复用旧 #9/#10 门禁均被拒；六口径分账；预算/墙钟/重试/缓存停止条件；`evidence_grade=SOFTWARE_CONTROL_PATH_ONLY` | [m1_batch_software_rehearsal_receipt.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/m1_batch_software_rehearsal_receipt.json>)、[m1_batch_software_verification.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/m1_batch_software_verification.json>) |
| A4 可注入根目录 | `RCAIDE_A1_ROOT` / `RCAIDE_S3_ROOT` / `RCAIDE_DNEXT_ROOT` / `RCAIDE_DNEXT_PARENT`；缺注入即失败，不再静默指向本机路径 | [a4_path_injection_20261117.md](<.worktrees/drecover001-20261117/docs/evidence/drecover001/a4_path_injection_20261117.md>) |
| A1 几何/参考冻结 v2 | `geometry_freeze_v2.json`：Sref 358.25 m²、Cref 18.489893、Bref 25.604638、CL_target 0.18174391742；模型边界 24/24 + 真实 OpenVSP 边界 24/24，VSP3/STL/STEP 导出逐 SHA/位置校验；`GEOMETRY_FREEZE_V2_VERIFIED`、101 检查 0 失败。质量/CG/AC 仍 provisional，`XCG_M` 是主翼局部 AC，力轴须 R2 读回 | [geometry_freeze_v2.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/geometry_freeze_v2.json>)、[verification](<.worktrees/drecover001-20261117/docs/evidence/drecover001/geometry_freeze_v2_verification.json>) |
| A2 可执行反馈（软件） | 真实 `ArmHarness`/GP-BO 路径 6 次 MOCK 评价；交换前两次反馈会改变第 3 个 proposal；失败设计 objective=null；physical=0，`scope=SOFTWARE_FEEDBACK_REHEARSAL_ONLY_NOT_PHYSICAL_EVIDENCE` | [a2_feedback_rehearsal.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/a2_feedback_rehearsal.json>) |
| 软件回归 | 247 项 pytest 全绿（0 failed / 0 error / 0 skipped），含 M1 批次控制、M2、路径注入、恢复合同、审计工具等 | [recovery_preflight_receipt.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/recovery_preflight_receipt.json>) |
| 恢复门禁就绪聚合 | 9 个 gate（R0/A1 几何冻结/R1/M1/M2/备份/A5/真实准入/变更清单）自动核对；结果 `RECOVERY_READINESS_GATES_CLOSED_EXPECTED`、`violations=0`、`blockers=9`，`CLOSED` 不等于 PASS | [recovery_readiness.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/recovery_readiness.json>)、[recovery_readiness.md](<.worktrees/drecover001-20261117/docs/evidence/drecover001/recovery_readiness.md>) |
| A5 审查包 | 只读聚合 39 项证据的 SHA256、9 门禁状态、外部待签项与检查清单；deepseek-flash 子智能体已执行两次审查（01c9274 只读工具、c0723397 单发 dossier），两次 verdict 均 `CHANGES_REQUIRED`，逐项处置见 `a5_finding_disposition_20261118.md`；非人类签名、不授予 GO | [a5_review_packet.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/a5_review_packet.json>)、[a5_review_packet.md](<.worktrees/drecover001-20261117/docs/evidence/drecover001/a5_review_packet.md>) |
| 本地恢复演练 | 2,241 文件 + 54 overlay 逐 SHA 核对、247 测试通过、重训 checkpoint/holdout 精确一致；bundle 内嵌 manifest 2,241 项逐 SHA/字节复验通过（`bundle_manifest_verified=true`）；恢复后 98 个证据文件还原为 bundle 原字节，两轮 R0/M1 verifier、readiness 与 A5 packet 校验均通过（`evidence_chain_verified=true`）；bundle SHA256 `3088b3166ba4009f92d453785be3e117a7b4015dfdf40457aea1d0b5565b181e` / 58,419,708B；receipt `off_machine_backup=false` / `backup_label=SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP` | [local_restore_receipt.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/local_restore_receipt.json>)（同机，**不构成独立故障域，Owner 已豁免**） |

M2 rehearsal 回执关键身份：`run_id=DRECOVER001-M2-REHEARSAL-20261117T160233Z`；`scope=OFFLINE_REHEARSAL_ONLY`；`real_meta_training_executed=false`；`admitted_real_labels=0`；`physical_solver_starts_actual=0`；checkpoint SHA256=`1616dc5d7441caf7ab0214aeb753aa9cb3be51fec12c7b7a8c3e4739ea326e49`；code SHA256=`5d642680af3dab9b8f3238c5febe95b7ce37544bf6b7231b2b12b0420d904bfb`。
重复运行校验（同代码同 seed 同 policy 重跑，repeat `run_id=DRECOVER001-M2-REHEARSAL-20261117T160500Z`）：`code_sha256`、`checkpoint_parameters_sha256`、evaluation、training、task identity、labels、dataset、geometry contract、config 全等；checkpoint payload 除嵌入 `run_id` 外完全相同，文件 SHA 因此不同（见 [m2_rehearsal_repeat_check.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/m2_rehearsal_repeat_check.json>)）。

## 2. Rehearsal 数值（mse_normalized，meta_test 两任务宏平均；30 步验证早停）

| 模型 | K=0 | K=4 | K=10 |
|---|---|---|---|
| FOMAML | 9.0966 | 7.6897 | 6.3880 |
| 池化预训练 | 8.6736 | 7.2816 | 6.0882 |
| 条件特征预训练（16D） | 10.5396 | 3.6982 | 2.8603 |
| random-init | 10.5875 | 11.3894 | 7.9008 |
| constant_train_mean | 9.6823 | 9.6823 | 9.6823 |

诚实结论：**`meta_learning_gain_claim = NO_META_LEARNING_GAIN_CLAIM`**。test 任务 Mach 1.80 位于 train（Mach 2.02–2.20）分布之外，K=0 的误差是刻意的分布移动（query 均值相对 train 均值偏移 −3.43σ / −2.76σ）；FOMAML 在 K=4/K=10 仍略差于池化预训练（7.69 vs 7.28；6.39 vs 6.09）。没有通过调参去制造"MAML 更优"的结论；合成标签上的任何收益都没有物理含义。

## 3. 阻断真实 MAML 的门禁（全部未通过）

1. **R0 A5 独立审查**：已由 Owner 授权的 deepseek-flash 子智能体执行两次，两次 verdict 均 `CHANGES_REQUIRED`（01c9274 的旧两项 major 已修复；c0723397 的 7 major + 3 minor 已逐项处置，见 `a5_review_verdict_c0723397.json` 与 `a5_finding_disposition_20261118.md`）；这不是人类签署，R0 清单状态仍为 `R0_PARTIAL_NOT_AUDITED`。
2. **RESTORED_CODE_BASELINE_PASS**：未签发（需 A5）。
3. **BACKUP_RESTORE_PASS（独立故障域）**：Owner 已豁免异机要求（`WAIVER-OFFMACHINE-BACKUP-20261118`，m03569）；同机恢复带 `SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP` 标签，`backup_restore_pass=false`，不得写成 PASS。
4. **真实准入 + raw 验证**：`dreal001/meta/meta_dataset.py` 的 `require_real_admission()` 仍直接抛 `REAL_ADMISSION_NOT_IMPLEMENTED`；F1R2/F2R2 原始运行目录未恢复，可免重跑的标签认定 0 条。
5. **A1 冻结身份重发**：U1参考绑定8项检查6项失败（4个期望冻结工件在所有本地树均不存在：`bundle_manifest.json` 1b16f572…、`PRE-01R/geometry.vspgeom` 16da482a…、`zero_physics_audit_12d.json` 7a90b977…、`design_space_freeze.json` fe7e48eb…；另有2项SHA因R1修复变化：`aircraft/openvsp_geometry.py`实际4f64d4c0…(16,299B)≠期望d20ee7ad…(13,654B)，`design_space_12d_lifting_surfaces.yaml`实际ebca2b7b…(11,099B)≠期望8b29d1e3…(10,846B)）。U1-DESIGN-HASHES与U1-OLD-GEOMETRY-NOT-USED通过；旧冻结ID已作废，不得静默重冻，须在新R2门禁下以新ID重发。完整 checks 见 [a1_u1_reference_gap.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/a1_u1_reference_gap.json>)。
6. **新的 R2 门禁 + Lead 逐批 GO**：未预注册、未签发。 软件侧 `m1_batch.py` 已实现并测试（18 项 fixture，physical=0），但无 A5 审查、无真实 `authorization_id`/GO，真实批次仍不可执行。
7. **Git 可复核性**：无 author identity、无法连 github.com；所有改动只在工作树，远端无法复核。
8. **其他未闭环**：任务→几何/mesh 完整重建绑定未在真实路径验证；条件特征生产入口（已实现，但只在 fixture 路径验证，真实路径未验证）；验证早停未接真实训练路径；真实反馈 BO 生产入口未接；完整几何语义/12D 掩码未恢复；旧 pytest 账本/缓存 4 项因沙箱临时目录 ACL（`mkdtemp` 0o700，`PermissionError WinError 5`）未跑绿，属环境问题、非本轮逻辑回归。

## 4. 建议的下一步顺序

1. Owner 接受/必要时人类签署 A5 审查结果（当前 deepseek-flash verdict=`CHANGES_REQUIRED`，major 已修复）；Lead 不能自签 `RECOVERY_INVENTORY_PASS`。
2. ~~建立独立故障域备份~~：Owner 已豁免（m03569）；只保留本机可移植 bundle 与同机恢复证据，标签必须显式为非异机备份。
3. 解析 git author identity + 凭据，把本轮恢复分支推送远端，形成可复核 commit。
4. A1 冻结 ID 重发（新 ID，不覆盖旧跑数），补齐 U1 缺失工件或明确宣告丢失并重生成（标注 `REGENERATED_FROM_SPEC`）。
5. A5/Lead 预注册 R2 最小可识别矩阵与每批上限（≤24 starts、600s 超时、1 次重试、并行 1），签发新 `authorization_id`/GO 后才启动第一批真实 VSPAERO。
6. 真实标签通过 `require_real_admission` 后，才把 M2 rehearsal 切换为真实 M1/M2 训练；在此之前任何"MAML 已训练"的说法都不成立。

## 5. 口径声明

- 本轮 `physical_solver_starts_actual=0`、`internal_solver_cases_actual=0`；无任何真实 VSPAERO 标签。
- M2 回执中所有标签来自 `synthetic_fixture`，仅用于验证训练/适配/评估管线可执行，不可作为科学结论。
- 本文件不替代 Issue 回执，不勾选任何 R2/#11 验收项。