# L-16 决策：接单 D-FIXED-001 / D-META-REAL-001，冻结 F0–F3 与 T0 执行顺序

- decision_id: L-16
- decision: ACCEPT_DFIXED001_AND_DMETA_REAL001_WITH_F0_FIRST_GATE_SEQUENCE
- physical_authorization: false（本决策不含任何真实 solver 调用授权）
- date_utc: 2026-11-12

## 1. 依据
- Issue #10（D-FIXED-001，2026-11-12；2026-11-13 Owner 增补）：固定任务真实气动—普通优化闭环优先，T0 跨任务元学习代码基础必须在 F0/F1/F2 并行完成，不得延期；F0+F1+F2+T0 通过并 A5 审查后，Lead 必须在 #10 发布完整中文阶段汇报。
- Issue #11（D-META-REAL-001）：CONDITIONALLY_AUTHORIZED / NOT_STARTED；#10 门禁通过后必须直接预注册并启动首个有限真实多任务训练批次，不重复询问 Owner。
- #9 R10 approval/window/GO token/剩余额度全部关闭，不得复用；R1–R10 历史不可变。

## 2. 执行顺序（硬门禁）
1) F0：远端可复核基线（新分支 research/dfixed001-fixed-loop，从远端 683a868 起）+ 证据备份 + 五口径账本与崩溃恢复测试 → A5 REPRO_BASELINE_PASS。
2) F1：同一冻结 deck 重复性 / 同 x12 跨进程重建 / 单变量扰动真实性 + 网格族根因 + CL-α 预注册 → A5 审查后仅允许小型诊断批次（需新 approval/GO）。
3) F2：一条真实普通优化器（优先 DE，备选 BO）完整 ask/tell 闭环 + 候选独立复评 → A5 REAL_SOLVER_OPTIMIZATION_LOOP_PASS。
4) T0：TaskSpec/TaskFamily、MetaDataset/任务级 split 与泄漏隔离、FOMAML MetaTrainer、K-shot AdaptationRunner、WarmStartSampler→BO 接口、单测+端到端冒烟+checkpoint/重放 → A5 READY_FOR_REAL_META_TRAINING。
5) F3：普通算法等预算基线，可增量并行，不阻断 #11。
6) #10 中文验收汇报（A5 复核）→ #11 M0 冻结任务族/有限批次 → M1 真实多任务标签采集 → M2 FOMAML 训练 → M3 新任务 K-shot 等预算对照。

## 3. 角色（复用 durable teammates，provider=课题组DS/sub2，deepseek-flash）
| 角色 | 职责 |
|---|---|
| Lead | 远端唯一写入、基线与批次冻结、approval/GO、中文汇报、#11 衔接 |
| A1 | 几何重建确定性、12D 有效维度、CL-α 升力匹配、VSPAERO 固定工况评价器、TaskSpec 物理域 |
| A2 | 真实 ask/tell（Random/Sobol/DE/BO/PSO）、统一预算、T0 训练/适应/热启动接口与单测 |
| A3 | 任务级 split/泄漏诊断、配对统计、失败分类 |
| A4 | 进程/资源保护、断点恢复与备份、checkpoint、SHA/manifest、中文图 |
| A5 | 非作者独立审查 F0–F3 与 T0，签 REPRO_BASELINE_PASS / REAL_SOLVER_OPTIMIZATION_LOOP_PASS / READY_FOR_REAL_META_TRAINING；可 STOP |

## 4. 首个有限批次状态
- F1 诊断批次、F2 工程 E2E、#11 M1 首批：均 NOT_REQUESTED / NOT_STARTED；
- 前置：F0 gate PASS + 批次预注册（case 矩阵/预算/停止条件）+ A5 预审 + 新 approval.json + Lead GO；
- 预算口径：physical_solver_starts_actual / internal_solver_cases_actual / planned_reserved / design_evaluations / cached_reads 五口径分离，旧 #9 额度不结转。

## 5. 禁止项
- 不得把 #9 R10 结果、approval、token 当作已启动依据；不得用合成/mock 替代真实标签进入训练；
- 不得在 F1/F2 门禁前启动大型真实批次；不得改 A1 冻结字节而不新版本化；
- 不得只写规划/接口就宣称 F2 或 T0 完成；结论 NOT_RUN 不得写成 PASS。
