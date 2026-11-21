# D-REAL-EXP-002 P0 协议冻结与代码/零物理证据（Issue #14）

生成时间：2026-11-22。分支 `research/dreal004-alpha-adaptive-meta-sampling`，基线 `af9871cd2b16a083c228ac2ecbced4c0344012a0`（上一阶段快照 `409f09c8`）。
本文件是 **P0 交付物**：代码/协议审查材料。**不授权任何新物理**；P1 起必须 A5 审查 + Lead 新 GO。
本轮 `physical_solver_starts_actual = 0`、`internal_solver_cases_actual = 0`、`labels_created = 0`。

## 1. P0 结论摘要

| 项目 | 结果 |
|---|---|
| A1 自适应迎角 `AdaptiveAlphaSolver` | 已实现，13 项单测通过；只接受注入式真实求解回调，每次 probe 计 1 个 internal case；割线插值夹在 bracket 内；非单调返回 `INVALID_POLAR`；预算耗尽返回 `BUDGET_EXHAUSTED` |
| G1 24 case 零物理 replay | 8 个 `REPLAY_RAW_HIT_ON_EXISTING_ROW`、7 个 `REQUIRES_NEW_ALPHA_ROWS`、8 个 `NO_BRACKET_ON_EXISTING_ROWS`、1 个 `MISSING_INPUT`；原固定扫描 391 internal cases vs 自适应 replay 329 probes；新标签 0 |
| 12D 变量响应审计 | 15 个变量全部真实进入 VSPAERO 输入；56 个 G2 stage1 response pair 全部 deck SHA 不同 |
| A2 主终点分析器 | 已实现，10 项单测通过；G1 历史序列复算：首个可行第 10 个 design（170 internal cases）、点级可行率 8/24=0.333、391 internal 与 batch accounting 一致 |
| split/协议预注册 | `p1_p2_p3_preregistration.json`：8 任务 4/2/2 冻结；P1 ≤12 starts、P2 ≤240、P3 ≤384；主终点/公平性/统计/禁止项明确 |
| A5 | 待做：`P0_CODE_AND_PROTOCOL_PASS` 或 `CHANGES_REQUIRED` |

### 1.1 重要机制发现（V01/V02）

- V01 垂尾面积 +2%（G2 d05）在 8 个任务上 **ΔCDi = 0.0（精确为 0）**，ΔCDo ≈ +1.445e-5，ΔCLtot ≈ -1.0e-6（最大绝对 2.46e-6）。
- 机制：本轮任务 β=0，垂尾不产生升力/诱导阻力，只增加寄生阻力；主终点 `Di_N = q·Sref·CDi` 完全不动。
- 处理：V01/V02 保留在几何合同，但**不作为 P2/P3 活跃优化维度**；若未来增加 β≠0 任务族，再重新审查。V02 无既有扰动 raw，状态 `RESPONSE_PENDING_P1_PROBE`，不做推断。

### 1.2 G2 中止账本（不是 G2 回执，永久保留）

Issue #13 评论 `7063823679` 发布 #14 后立即停止 G2 后续子批：

| 批次 | charged starts | completed | internal cases | admitted | null | 有效率 |
|---|---|---|---|---|---|---|
| B01 | 24 | 23 | 731 | 4 | 20 | 17.4% |
| B02 | 78 | 78 | 2886 | 26 | 52 | 33.3% |
| 合计 | 102/240 | 101 | 3617 | 30 | 72 | — |

- B02 GO 上限 112，实际 78，剩余 34 未用；stage2 60 个中 26 已跑、34 未启动。
- 未运行 G2 MAML（遵守 #14“不得先训练正式跨任务 MAML”）；未签发 G2 回执。
- G1 的 24 starts / 8 labels / 34.78% 永久保留，不重标、不放宽 1e-3。

## 2. 冻结的任务 split（P1–P3 不再改）

| 任务 | Mach | split |
|---|---|---|
| DREAL004-M140 | 1.4 | train（G1 零标签，诊断任务） |
| DREAL004-M160 | 1.6 | train（G1 零标签、6 个无 bracket；标签不足时可暂不纳入训练，但不得改到 val/test） |
| DREAL004-M200 | 2.0 | train |
| DREAL004-M202 | 2.02 | train（参考 Mach） |
| DREAL004-M180 | 1.8 | val |
| DREAL004-M220 | 2.2 | val |
| DREAL004-M240 | 2.4 | test（held out，不得调参） |
| DREAL004-M260 | 2.6 | test（held out，不得调参） |

- 每任务 support `d00–d03`、query `d04–d07`，共 8 个去重设计；support/query 不重叠。
- 测试任务身份在任何超参数选择前冻结；P1 pilot 只用 M202，且**不是训练批**。

## 3. P1 预注册（未授权，等 A5 + 新 GO）

- 建议 `AUTH-DREAL004-P1-20261122-01` / `DRECOVER001-P1-20261122-01`；目标 Mach 2.02。
- 设计：`d00` 基准、`d01` 面积 +1%、`d04` 后掠 -0.5°、`d07` 机身长度 +1%；**≤12 design starts**（每设计 ≤3 starts），每 start ≤3 alpha probes，≤36 internal cases。
- 粗 bracket 来自既有 G2 stage1 M202 raw（零物理）；细化用 bracket 内割线，不外推；`tol_CL=1e-3` **不得放宽**；插值目标永不记为 raw。
- 成功标准：4 个设计中 ≥70% 命中真实 raw 行（同一行相对升力误差 ≤1e-3）；否则记 `UNDERPOWERED`/`CHANGES_REQUIRED`，不强行放行。
- 停止规则：每设计 3 starts 用尽、总 12 starts、连续 2 次 solver 失败、墙钟 3600s、账本不守恒（`STOP_ACCOUNTING_VIOLATION`）、每 ≤8 starts 上传+远端回读未通过即停。
- 输出必须含 `tables/alpha_refinement_history.csv`、`actual_solver_ledger.csv`、原始 `.polar/.history/.vspaero`、中文 PNG + `figure_data.csv`、`SHA256SUMS.txt`、`upload_receipt.json`、A5 verdict。

## 4. P2 / P3 规划（未授权）

- **P2** ≤240 新 starts：至少 4 train / 2 val / 2 test 物理有效任务；每 train 任务 ≥4 条真实准入标签；训练 FOMAML K=1/3/5、普通池化预训练、16D 上下文预训练（与 12D 设计变量分开）、随机初始化；测试只用 support 适应，query 不得反向更新；报告摊销前/后成本；负迁移照实报告。
- **P3** ≤384 新 starts：固定 M202 Concorde 任务、统一 BO 后端与等总预算，比较 Random/LHS/Sobol/普通预训练/FOMAML K-shot/zero-shot；后续接 DE/PSO 验证优化器无关性；输出 B=4/8/16/32/64/128 anytime 曲线、首个可行成本、best-feasible Di_N、cost-to-target、任务级配对统计。
- 每批 ≤16–32 starts（P3）或更短时限，上传回读通过后才放行下一批；A5 逐批审查，Lead 逐批 GO。

## 5. 主终点与公平性（A2）

- 主终点：`N_first_feasible`（design evaluations / design starts / internal alpha cases）、`best_feasible_Di_N(B)` 与 anytime 曲线、`simple_regret(B)`（无独立参考时保持 null）、点级/运行级 `feasible_hit_rate`、`cost_to_target`。
- 成本键：`design_starts`、`internal_solver_cases`、墙钟。
- 公平性：按 (task, seed, budget) 配对；support 点、初始样本、alpha cases、失败/重试全部计费；MAML 训练成本摊销前后都报告。
- 统计：task 为一级单位；配对差 + bootstrap/Wilcoxon + 多重比较校正；样本不足标 `UNDERPOWERED`，不宣称 win。
- 参考解：目前不存在独立充分搜索的 `D_reference`，因此 `simple_regret` 保持 null，只用 best-so-far。

## 6. 代码与证据 SHA（A5 审查对象）

见 `p1_p2_p3_preregistration.json` 的 `code_shas`：`adaptive_alpha.py`、`polar_rows.py`、`endpoint_analysis.py`、三个测试文件、三个 P0 脚本，以及 `g1_alpha_replay.json`、`12d_variable_response_audit.json`、`a2_g1_baseline_endpoints.json`。

## 7. 明确禁止

- 放宽 `tol_CL=1e-3`，或把 `INTERPOLATED_TARGET_ESTIMATE` 混入 raw-point 主结果；
- 用 G1 null 点冒充成功、删失败、改历史标签；
- 把 internal alpha cases 藏在 design-start 成本后；
- 单任务换 seed 冒充跨任务 MAML；
- 未过 A5 + 新 Lead GO 就启动 P1/P2/P3；
- β=0 时宣称 V01/V02 的 12D 响应；
- 把 VSPAERO 翼面诱导阻力当整机阻力/燃油（`fuel_burn_kg=null`、`LF-M2.02=NOT_VALIDATED` 保持）。

## 8. 当前门禁

- P0：代码/协议已就绪，**A5 审查未完成** → 无 `P0_CODE_AND_PROTOCOL_PASS`。
- P1：未授权；需 A5 + Lead 新 GO。
- P2/P3：未授权。
- 旧 G2：已中止（102/240），未签发回执，不上调为 PASS。
