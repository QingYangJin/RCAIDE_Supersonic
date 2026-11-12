# [接单回执 issue_brief｜2026-11-13] D-FIXED-001：实际实例、真实基线、F0–F3/T0 任务卡与首个有限批次审批状态

> 本回执为 #10 要求的**接单首回执**（先于任何新的真实启动）：确认已接单，报告实际工作机/代理状态、远端/本地真实基线、旧 R10 结果可获取性、F0–F3 任务卡、T0 代码负责人与交付、当前阻断、首个有限批次审批状态，以及 #11 首批真实训练计划与当前门禁。**本轮零 solver 调用（physical_solver_starts_actual=0）**。

## 0. 结论先行
- 接单状态：**ACCEPTED / F0_IN_PROGRESS**；F1/F2/F3/T0 **NOT_STARTED**；首个有限真实批次 **NOT_REQUESTED**（前置 F0 gate 与 F1 预注册）。
- 远端可核对基线：默认分支 main @ `ec65e5a`；远端仅有 `research/dreal001-vspaero-optimization` @ `683a868`（#9 计划提交）。**#9 R1–R10 的代码/证据分支（A1/A2/A3/A4/A5）均未推送，远端不可取回（LOCAL_ONLY）**。
- 旧 R10 结果：**本地完整可读、远端不可读**。R10 run dir 2,228 文件 / 198.1 MB（含全部原始 .vspgeom/.polar/.history/ledger），SHA256SUMS 索引 64bc7886…/289,537 B；A5 签署回执已作为 Issue #9 评论 6805989352 发布（文本级可读），但**原始数据文件不在 GitHub**。
- 实际实例：Lead=本会话（工作目录 `D:\RCAIDE`）；5 个 durable teammates 已存在（a1-geometry / a2-optimizers / a3-stats / a4-perf-figs / a5-review），provider=**课题组DS(sub2)**、model=deepseek-flash；按阶段唤醒、最多 2 个并发。**角色=实际可唤醒会话，不是纸面分配**。
- 首个有限批次：**NOT_REQUESTED**。在 F0 `REPRO_BASELINE_PASS`、F1 诊断批次预注册（case 矩阵/预算/停止条件）与 A5 预审完成前，不生成 approval.json、不签发 GO、不启动真实求解。**#9 R10 approval/window/GO token/剩余额度一律不复用**。

## 1. 真实基线：远端 vs 本地（F0 起点）

| ref | 远端 | 本地 HEAD | 状态 |
|---|---|---|---|
| main | `ec65e5a` | — | 基线，不覆盖 |
| research/dreal001-vspaero-optimization | `683a868` | `ebc0baa`（Lead worktree，clean） | REMOTE_BASE + LOCAL_AHEAD（R1–R10 决策/签署/回执未推） |
| research/dreal001-a1-geometry-solver | absent | `2a57632` | LOCAL_ONLY（1,617 dirty：含 runs/原始证据与临时） |
| research/dreal001-a2-optimizers | absent | `f639087` | LOCAL_ONLY（3 dirty） |
| research/dreal001-a3-stats-routeb | absent | `699ce2a` | LOCAL_ONLY（7 dirty） |
| research/dreal001-a4-perf-figs | absent | `88ad510` | LOCAL_ONLY（clean） |
| research/dreal001-a5-review | absent | `964a451` | LOCAL_ONLY（3 dirty） |

- R10 原始结果与 R1–R9 证据均在本地 run dirs：R1 0.6MB/27、R2 4.1MB/60、R3 4.1MB/58、R4 4.8MB/69、R5 0.2MB/14、R6 6.6MB/90、R7 14.1MB/175、R8 0.3MB/16、R9 14.1MB/166、**R10 198.1MB/2,228**；均已 append-only commit 于各自本地分支（A2 `f299ce22` 等）。
- 结论：**远端可复核代码基线 = `683a868`；R10 之后的执行代码/证据 = LOCAL_ONLY，需 F0 推送与备份后 A5 才能从独立位置复核。**

## 2. 任务卡 F0–F3 与 T0（owner / 交付 / 门禁 / 状态）

| 卡 | owner（实际会话） | 关键交付 | 门禁 | 当前状态 |
|---|---|---|---|---|
| F0 | Lead（本会话）+ A2/A4 支持 | 新分支 `research/dfixed001-fixed-loop`（从 `683a868`）推送代码/配置/测试/决策/回执/证据索引；R10 raw 仓库外不可变备份+SHA 索引；五口径账本（actual starts/internal、planned_reserved、design_evals、cached_reads）与断电/取消恢复测试 | A5 `REPRO_BASELINE_PASS` | **IN_PROGRESS**（远端/本地基线核查完成；推送与备份待执行） |
| F1 | A1（a1-geometry） | (a) 同一冻结 .vspgeom/.vspaero 重复求解；(b) 同一物理 x12 跨进程重建；(c) 单变量扰动真实性（几何/网格/Sref）；483x418 vs 543x472 族翻转根因；CL-α 预注册、失败分类（GEOMETRY_INVALID/LIFT_TARGET_UNREACHABLE/SOLVER_NONCONVERGED/INFRA_ERROR） | A5 审查诊断预注册；仅允许小型真实诊断批次（需新 approval/GO） | NOT_STARTED |
| F2 | A2（a2-optimizers） | 优先 DE（备选 BO）真实 ask→x12→OpenVSP→VSPAERO→升力匹配→D_i_N→tell 完整闭环；B_design=8/16 smoke；失败注入与崩溃恢复；候选独立复评 | A5 `REAL_SOLVER_OPTIMIZATION_LOOP_PASS` | NOT_STARTED |
| F3 | A2/A3 | Random/Sobol + BO/DE/PSO 等预算基线，真实启动成本为主横轴；不阻断 #11 | A5 审查；可增量 | NOT_STARTED（非阻塞） |
| T0 | **A2（a2-optimizers）** | T0-1 TaskSpec/TaskFamily/TaskContextEncoder；T0-2 MetaDataset/EvaluationRecord 合同 + 任务级 train/val/heldout split + support/query 零泄漏；T0-3 FOMAML MetaTrainer + K-shot AdaptationRunner + WarmStartSampler→BO；T0-4 配置/预注册/测试 | A5 `READY_FOR_REAL_META_TRAINING` | **NOT_STARTED**（本轮仅接单，未开始编码） |

### T0 负责人/会话与交付文件（逐项确认）
- 负责人：**A2（实际会话 a2-optimizers）**；协作：A3（任务级 split/泄漏审查）、A4（checkpoint/恢复/备份）、A5（非作者独立审查）。计划分支：`research/dfixed001-t0-meta`（待 F0 后创建，不覆盖 #9 历史）。
- 交付文件（计划路径，全部在新增分支）：
  - `research/concorde_metaopt/dreal001/meta/task_spec.py`、`task_family.py`（TaskSpec/TaskFamily/active_mask/fingerprint）
  - `research/concorde_metaopt/dreal001/meta/meta_dataset.py`（EvaluationRecord/MetaDataset/任务级 split/泄漏 fail-closed）
  - `research/concorde_metaopt/dreal001/meta/trainer.py`（FOMAML MetaTrainer、普通预训练对照、checkpoint/重放）
  - `research/concorde_metaopt/dreal001/meta/adaptation.py`（AdaptationRunner K=0/1/3/5）
  - `research/concorde_metaopt/dreal001/meta/warm_start.py`（WarmStartSampler→BO/DE 接口）
  - `configs/meta/real_task_family_candidate.yaml`、`meta_data_contract.json`、`meta_train_config.yaml`、`task_split_manifest.json`、`first_real_training_batch_DRAFT.json`
  - `tests/test_dreal001_meta_*.py`（单测 + 合成/回放 fixture 端到端冒烟 + 固定 seed 重放 + checkpoint SHA）
- 验收触发：#10 F0/F1/F2 PASS + T0 A5 `READY_FOR_REAL_META_TRAINING` → Lead 在 #10 发布完整中文阶段汇报 → #11 M0 启动。**当前 T0 代码 STATUS=NOT_STARTED，不由本回执宣称已就绪。**

## 3. 当前阻断（可验证）
1. 远端不存在 R10 之后的代码/证据分支 → A5 无法从 GitHub 独立复核；需 F0 推送。
2. R10 raw（198MB）尚无仓库外不可变备份 → F0 备份 + SHA 索引。
3. 五口径账本尚未实现（#9 仅 charged vs actual 两口径）→ F0 实现并做断电/取消恢复测试。
4. F1 的网格族根因、同 x12 跨进程重建稳定性、有效维度证据尚未完成。
5. 无新 approval.json / GO；#9 授权不得复用。

## 4. 下一步（Lead 已启动/将启动，零物理）
- F0-0（完成）：远端分支/本地 worktree/证据 inventory 核查（见上表）。
- F0-1（进行中）：从 `683a868` 建 `research/dfixed001-fixed-loop`，推送代码/配置/测试/决策 L-09–L-16/回执/证据 SHA 索引（不推 198MB raw，raw 走备份+索引）。
- F0-2：A4 执行 R10 raw 仓库外备份（`D:\RCAIDE\_evidence_backup_r10`）+ SHA256 索引 + 与本地 run dir 逐字节抽样核对。
- F0-3：A2 实现五口径账本 + 崩溃/取消恢复测试（零 solver）；A5 预审。
- F0 gate 通过后进入 F1 诊断预注册；F2 与 T0 按并行槽位推进。

## 5. 首个有限批次的明确审批状态
- 批次编号：**未分配（NOT_REQUESTED）**；authorization_id/approval.json/GO：**均未生成**。
- 待冻结项：任务（固定 Mach=2.02、h=18,288m、固定 F01–F03；W01–W10/V01–V02）、D_i_N 目标与 L_ref、CL-α 协议、每案超时/重试、max_solver_starts/max_internal_cases/max_design_evals、停止阈值、窗口与硬件保护。
- 首个拟启动批次：F1 小型诊断（仅重复性/重建/单变量扰动，不做优化扩量）；其规模与 evidence 矩阵在 F0 PASS 后由 A5 预审、Lead 预注册并签发新 GO。

## 6. #11 首批真实训练计划与当前门禁（M0_NOT_STARTED）
- 当前状态：**M0_NOT_STARTED / GATE_WAITING_ON_#10**；无 TaskSpec 冻结、无真实多任务标签、无训练、无 checkpoint。
- 依赖检查表：#10 F0=IN_PROGRESS、F1=NOT_STARTED、F2=NOT_STARTED、T0=NOT_STARTED、A5 审查=未开始 → 全部未通过，故 #11 不启动真实求解。
- 计划（通过后，另立有限批次+新 approval/GO，不复用 #9）：M0 冻结 TaskFamily/任务分布/留出分割/source_kind/evaluator_id/统计端点 → M1 小批次多任务真实 VSPAERO 标签采集（每任务设计数/预算预注册）→ M2 FOMAML 真实训练（普通预训练+K-shot 对照）→ M3 heldout 任务 K-shot 与 Random/Sobol-BO、Pretrain-Kshot-BO 等预算对照；允许 NO_EVIDENCE/NEGATIVE_TRANSFER 结论。

## 7. 本回执性质
- 本回执**不构成任何执行授权**、不触发真实求解、不改变 #9 历史字节；A5 physical_call_count=0。
- 后续回执将分别报告 `code-ready` / `physical-data-started` / `real-meta-training-executed`，不混写为 PASS。
