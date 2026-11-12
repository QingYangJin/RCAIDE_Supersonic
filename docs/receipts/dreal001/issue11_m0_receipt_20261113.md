# [M0 接单回执｜2026-11-13] D-META-REAL-001：M0_NOT_STARTED / GATE_WAITING_ON_#10

- **状态**：`M0_NOT_STARTED / GATE_WAITING_ON_#10`；CONDITIONALLY_AUTHORIZED 未触发，**未启动任何真实多任务求解或训练**。
- **批次**：尚未分配；authorization_id / approval.json / GO：未生成；**#9 R10 approval/window/token/额度不复用**。
- **分支/head**：本 Issue 尚无执行分支；Lead 工作树 `research/dreal001-vspaero-optimization` @ `ebc0baa`（本地，未推）；远端基线 `683a868`。计划分支 `research/dfixed001-meta-real`（F0 后创建）。
- **执行人**：Lead（本会话）+ A1/A2/A3/A4/A5（durable teammates，provider=课题组DS/sub2，deepseek-flash）；当前均未进入 #11 实跑，按 #10 门禁激活。

## 依赖检查表（全部未满足 → 阻塞）
| 依赖 | 状态 |
|---|---|
| #10 F0 可复现远端基线 + REPRO_BASELINE_PASS | IN_PROGRESS / 未签 |
| #10 F1 几何–求解器稳定性诊断 | NOT_STARTED |
| #10 F2 真实普通优化闭环 | NOT_STARTED |
| #10 T0 READY_FOR_REAL_META_TRAINING | NOT_STARTED |
| #10 中文验收汇报（Lead） | NOT_SUBMITTED |
| A5 独立预审（任务族/预算/泄漏/梯度接口） | 未开始 |
| 新有限批次 approval/GO | 未生成 |

## 通过后的首个动作（不重复询问 Owner 是否做真实训练）
1. M0：冻结固定任务（Mach=2.02、h=18,288m、F01–F03、W01–W10/V01–V02 活动掩码）、TaskFamily/任务分布/train-val-test 任务级切分、evaluator_id/source_kind、模型与训练成本、K-shot/种子/统计端点。
2. A5 审核任务族与目标一致性、支持/查询样本零泄漏、可执行梯度与 K-shot 接口、基线公平性。
3. Lead 预注册有限首批（任务数/每任务设计数/预算/失败上限/停止条件/窗口）并签发 approval/GO。
4. M1 真实多任务 VSPAERO 标签采集 → M2 FOMAML 训练 → M3 heldout K-shot 等预算对照；允许 NO_EVIDENCE / NEGATIVE_TRANSFER。

本回执不构成执行授权；A5 独立签署与 #10 门禁完成前不启动真实求解。
