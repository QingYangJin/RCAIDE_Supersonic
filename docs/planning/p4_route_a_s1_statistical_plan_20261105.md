# P4 路线A S1 统计分析计划（v1.2）

> 状态：S0-2 修订版（Lead task-186/190 集成），已按 A5 S0 审阅的 A5-S0-M02/M03/M04 与 D-S0-2-02/03/04 裁定回填；**仍待 A5 复审，不构成 S1 放行**。
> 依据：Issue #7 D-P4-003 §3 S1、docs/planning/p4_route_a_stage_improvement_plan_20261105.md、docs/planning/p4_route_a_s0_design_contract.md（v1.3）、docs/reviews/p4_route_a_s0_baseline_snapshot_20261105.md。
> 约束：physical_call_count=0；只允许全合成解析任务；不合并 main；结论允许为“无改进/INCONCLUSIVE”。

## 1. 目标与问题

S1 要回答的**单一主问题**：在任务级未见的新合成任务族上，把 K-shot 支持集真实评价计入预算并闭环进 BO 初始化后，**FOMAML-Kshot-BO 是否比预处理初始化（Pretrain-Kshot-BO）、随机初始化（Random-BO）与 DE 取得可复现的约束优化改进**？

次要问题（预注册，不得升级为主结论）：
1. K-shot 适应本身是否带来增益（FOMAML-Kshot-BO vs FOMAML-ZeroShot-BO，K>0）；
2. 增益是否随 K∈{1,3,5} 单调/稳定变化（只作描述与预注册对比，不做事后挑选）；
3. 改进是否以更多代理/适应墙钟为代价（成本端点描述）。

## 2. 任务族与数据（新 family v3）

| 项 | 规定 |
|---|---|
| family_version | 新版本（建议 p4ra-family-v3，最终以 A1 task-185 草案 + A5 审阅为准）；冻结后不升版本不得改生成规则 |
| task_id | 全新命名空间；必须与 M2/M5/M6 全部 task_id **零交集**（程序输出交集报告，非空即 fail-closed） |
| split | 五 split：meta_train 60 / meta_validation 20 / meta_test 20 / meta_test_ood 10 / negative_control 10（任务级切分，同一 task_id 不得跨 split；split_digest/split_hash 覆盖全部五个 split，见 D-S0-2-01） |
| 生成种子 | family_seed 新值，且不得与旧族 seed 序列重叠；split_digest 冻结 |
| 评估器 | 固定 evaluator_id 与解析函数；config_hash 变化视为新族，必须重新冻结 |
| 支持池 | support_pool_size=128、query_size=64（延用 M5 口径；v3 若变更须在 prereg 冻结） |
| 标签 | 只由合成 evaluator 产生；禁止真实求解器输出、禁止旧 run 内部 CD/油耗当标签/终点 |

旧 M2/M5/M6 的 meta_test 已被历史报告公开，**只能作诊断性对照，不得作为 S1 的“未见盲测”**；S1 主结论只来自新族 meta_test。

## 3. 实验设计（arms × K × B）

- 臂（5）：Random-BO、Pretrain-Kshot-BO、FOMAML-ZeroShot-BO、FOMAML-Kshot-BO、DE。
- 预算：B∈{64,128}；initial_designs=8；standard_bo_calls=B−8；K 个支持评价真实发生且计入 B；各臂每 run 的真实评价次数必须精确相等。
- K∈{0,1,3,5}；K 次支持评价来自支持池的真实评价，各臂共享同一组支持点与标签；补 8−K 个初始点后再 BO B−8 次。

**五臂预算映射（D-S0-2-03，唯一口径）**：所有臂均执行「K 支持评价 → 8−K 新初始点 → B−8 主搜索」，合计恰为 B；Random-BO/DE 不把支持标签用于适应但仍计入 K 次评价；DE 的初始 8 点即其初始 population 的一部分，B−8 为其世代评价；任何臂 billable≠B 即作废。K=0 时 FOMAML-Kshot-BO 与 FOMAML-ZeroShot-BO 同构（CLONE，排除推断）。
- **可辨识性（预注册）**：K=0 时 FOMAML-Kshot-BO 无支持标签可用，与 FOMAML-ZeroShot-BO 同构，登记为 CLONE_OF_FOMAML-ZeroShot-BO，**排除出 K=0 的推断与主统计**（仅作描述）；K>0 时 5 臂均可辨识。若 A5 代码审阅发现其他臂同构，按同一规则登记并披露。
- 网格划分（预先固定，不按结果调整）：

| 层级 | B | K | 任务 | opt seeds | meta seeds | run 数 |
|---|---|---|---|---|---|---|
| 主确认性 | 64 | 0,3,5 | 20 meta_test | 0..9 | 0,1,2 | 5×3×20×10×3 = 9,000 |
| 次级复现 | 128 | 3,5 | 20 meta_test | 0..9 | 0,1,2 | 6,000 |
| 探索性（不进主结论） | 64/128 | 1 | 20 meta_test | 0..9 | 0,1,2 | 6,000 |
| 合计 | | | | | | 21,000 runs |

- 评价次数：9,000×64 + 6,000×128 + 3,000×64 + 3,000×128 = **1,920,000 次**（另加确定性重跑，见 §8）。
- 墙钟估计：以 M5 实测速率（460,800 次评价 / 8,960 s ≈ 51.4 次/s，16 workers）线性外推约 **10.4 h**；加确定性重跑与打包约 12 h。实际 worker 数、墙钟、峰值内存必须写入 run_config；不设“静默截断”，中断须支持从检查点续跑并保持 digest 一致。

## 4. 冻结与预注册（p4ra-prereg-v1）

1. 先在**未打开 meta_test** 的情况下生成并冻结：family v3 定义、split、preregistration.json、分析脚本（analysis_plan_digest）。
2. preregistration 必填（对齐 A4 设计合同 §7，本计划只补充统计字段）：
   - 基础：schema_version=p4ra-prereg-v1、prereg_id、family_version、frozen_at_utc、seeds、task_counts；
   - 设计：arms、budgets（B 与 K 集合）、identifiability_map、comparison_registry；
   - 端点：primary_endpoints、secondary_metrics、fallback_endpoints；
   - 统计：aggregation_rule、statistical_tests、multiple_comparison、decision_rules、null_policy、practical_significance；
   - 运行：stopping_rules（**非空 list[str]**，禁止再出现单字符串被 list() 拆成单字符）、failure_rules；
   - digest：analysis_plan_digest、prereg_digest（自身 canonical JSON digest，计算时置空该字段）、old_task_id_disjointness_digest。
3. **强校验**（fail-closed，A1 task-185 实现 + 负控测试）：
   - 类型：所有数组字段必须为 list 且元素类型正确；stopping_rules/failure_rules 每项为非空 str（len≥2）、列表非空；
   - 一致性：B/K/arms/task_counts/seeds 与 run_config 完全一致；
   - 不可变性：冻结后任何字段变化 → 拒绝运行并作废；
   - 旧件：M2/M5/M6 的 preregistration/summary/manifest 只读，不修补。
4. 冻结顺序：family 生成 → split/family digest → prereg build → validate → 冻结宣告（A5 APPROVE_FOR_S1_FORMAL）→ 创建 run 目录 → 打开 meta_test **一次**。
5. 打开 meta_test 后禁止：调参、改终点、按结果剔除任务、改比较集；违反即结果作废（合同 FC-07/FC-10）。

## 5. 端点定义（规范 ID，D-S0-2-02/04）

> 唯一规范 ID 为 `best_feasible_value`、`gap_to_reference`、`first_feasible_eval_index`、`feasible_hit_rate`；`first_feasible_evaluation_index` 为禁用别名。

| 类型 | 端点 | 方向 | 定义 |
|---|---|---|---|
| 主 | best_feasible_value | lower | B 个评价中所有满足全部约束点的最小目标值；无可行点=null（不插补、不计 0） |
| 主 | gap_to_reference | lower | f* = reference_solution.best_feasible_value（数值或 null）；f_best 或 f* 任一 null → null；否则 `gap=(f_best−f*)/max(|f*|,1e-12)`（有符号，不截断） |
| 主 | first_feasible_eval_index | lower | B 个评价按真实评价顺序的 1-based 序号（支持评价占 1..K），首次可行即记录；无可行=null；附加 `first_feasible_in_support`（bool）与 `first_feasible_after_support_index`（序号−K，支持集内则 null）；跨 K 比较须声明 K 依赖性 |
| 主 | feasible_hit_rate | higher | 可行评价数 / B（分母恒为 B）；附加 `feasible_hit_rate_non_support` = 非支持可行数/(B−K)，B>K 时 |
| 次 | best_objective_raw | lower | 不剔除不可行的最优原始目标（fallback） |
| 次 | min_constraint_violation_sum | lower | 最小约束违反和（fallback） |
| 次 | rmse_norm | lower | 代理/适应后预测的归一化 RMSE（机制诊断，不作 BO 主结论） |
| 成本 | adaptation_wall_s / proxy_scoring_cost / peak_memory | 描述 | 与公平性审计一起报告 |

聚合规则（预注册）：单 run 端点 → (task, meta_seed) 内对 10 个 opt seeds 取均值 → 对 20 个 meta_test 任务做配对统计；meta_seed 等权平均为主分析（同时报告逐 meta_seed 敏感性）。**任务是一级统计单位**，禁止以 run/评价为单位夸大样本量。

null 政策：null 不插补、不计 0；报告 n_nonnull/null_rate；主端点 null 率 >70% → 该端点 INCONCLUSIVE，不据此更换终点（D-S0-2-04.8）。

## 6. 预注册比较、检验与多重校正

| ID | 比较 | 适用条件 |
|---|---|---|
| C1 | FOMAML-Kshot-BO vs Pretrain-Kshot-BO | 主假设（K>0） |
| C2 | FOMAML-Kshot-BO vs Random-BO | K>0 |
| C3 | FOMAML-Kshot-BO vs DE | K>0 |
| C4 | Pretrain-Kshot-BO vs Random-BO | K>0 |
| C5 | FOMAML-Kshot-BO vs FOMAML-ZeroShot-BO | K>0（验证适应增益） |

- 检验：双侧 Wilcoxon signed-rank（配对任务差）；n_tasks=20；全零或 n<10 → INCONCLUSIVE。
- 效应量：配对差中位数（端点单位）、rank-biserial correlation、Cohen's d（报告但不用作判据）。
- 置信区间：task 级配对差 bootstrap 10,000 次（百分位法，固定 seed=20261105）。
- 多重校正（R-V4-08-01 唯一口径）：Holm-Bonferroni 族键 = `(primary_endpoint, budget_B, K)`；族内为 C1–C4 全部可推断臂对比较（C5 永不进族；pair-level STRUCTURALLY_IDENTICAL 行级排除后族大小可 <4）；alpha=0.05 双侧。禁止“同 K 内 32 检验”“每个端点内 5 个比较”等其它口径。
- 实际显著性阈值（预注册，D-S0-2-04.6）：best 相对改进 =(median_base−median_arm)/max(|median_base|,1e-12) ≥1%；gap 相对改进 =(gap_base−gap_arm)/max(|gap_base|,1e-12) ≥1%；feasible_hit_rate 绝对差 ≥0.05；first_feasible 改善 = idx_base−idx_arm ≥ ceil(0.05×B)（同 K 内比较）。

## 7. 判定与结论规则

每个（端点×比较）给出：SUPPORTED_BENEFIT / SUPPORTED_HARM / NO_EVIDENCE / INCONCLUSIVE。

- SUPPORTED_BENEFIT：Holm p<0.05 且 bootstrap CI 不跨 0 且效应方向有利且达到实际显著性阈值；
- SUPPORTED_HARM：对称定义；
- INCONCLUSIVE：null 率 >70%、n<10、全零差、或与冻结计划不一致。

S1 总体结论“改进得到支持”需**同时**满足：
1. C1 在 4 个主端点中至少 2 个 SUPPORTED_BENEFIT；
2. C1 在 4 个主端点中 0 个 SUPPORTED_HARM；
否则输出 “NO_SIGNIFICANT_IMPROVEMENT” 或 “INCONCLUSIVE” 并给出具体原因（允许负结果）。

null 政策：主端点 null（无可行）不计 0、不插补；报告 n_nonnull/null_rate；若多数为 null，按预注册 fallback 端点做描述性报告并明确“不可与非约束目标直接比较”，禁止事后换终点造结论。

## 8. 确定性、负控与泄漏检查

| 检查 | 规定 |
|---|---|
| raw digest | 每 run 落盘 raw_digest_manifest：产品文件 canonical sha256 + 评价历史 CSV digest（修正 M5 的 NOT_STORED 缺陷） |
| 确定性重跑 | 固定子集：5 臂 × K{0,3} × B=64 × 20 任务 × opt seed 0 × meta seed 0 = 200 runs，重跑 3 次；mismatch>0 → fail-closed；全量重跑视为可选加固 |
| K=0 回归/CLONE | FOMAML-Kshot-BO 与 FOMAML-ZeroShot-BO 在 K=0 必须逐字节等价（历史 CSV digest 相同）；否则 CLONE 声明无效并 abort |
| 泄漏负控 | 支持/query 污染检测（FC-01）；标签打乱负控：MAML 优势应消失/缩小，若仍显著 → 机制解释失败，结论降级 |
| 旧件隔离 | A3 在 run 前后校验 M2/M5/M6 与 D-12D-005 归档 SHA；任何变化 → fail-closed |
| 物理隔离 | physical_call_count=0、physical_call_sources=[]、physics_guard=PASS，每 run 落盘 |

## 9. 停止规则（stopping_rules，新 schema 必须为非空 list[str]）

1. “physical_call_count 大于 0 或出现任何真实求解器启动记录时立即停止并上报负责人。”
2. “任一臂每 run 真实评价次数不等于 B，或支持评价未计入 B 时，作废该 run 并停止。”
3. “B、K、arms、task_counts、seeds 与冻结 preregistration 不一致时拒绝启动。”
4. “旧 M2/M5/M6 或 D-12D-005 冻结工件 SHA 发生变化时立即停止并通知 A3/A5。”
5. “确定性重跑 mismatch 大于 0 时立即停止，相关结果作废。”
6. “检测到支持集/query 标签泄漏或参考最优点被当作支持标签时立即停止并记录事件。”
7. “meta_test 打开后出现调参、改终点、按效果剔除任务时结果作废并停止。”
8. “task_id 跨 split 重复或与旧任务族交集非空时拒绝生成/启动。”
9. “主端点 null 率超过 70% 时该端点判 INCONCLUSIVE，不据此选择替代终点。”
10. “任一臂实现被审阅判定与其他臂同构（CLONE）时，将其排除出推断并在报告中披露。”

## 10. 交付物（S1 阶段）

- 7 张中文图（规范键名 + 文件名 + figure_status.json，键与文件一一对应；修正 M6 历史漂移）：
  fig1_meta_training_loss、fig2_k_shot_adaptation、fig3_feasible_rate、fig4_equal_budget_gap、fig5_fairness_audit、fig6_k_sweep_delta、fig7_negative_control_and_determinism。
- 主表：每端点每比较的 n_tasks、null_rate、median diff、bootstrap CI、Holm p、effect size、verdict；可辨识性映射表；预算/支持评价审计表；负控与确定性表。
- 中文报告 docs/reviews/p4_route_a_s1_formal_report_<run_id>.md；run 目录含 run_config/summary/data_manifest/SHA256SUMS/raw_digest_manifest。
- 结论层：只允许“支持改进 / 无显著改进 / INCONCLUSIVE”三类，附限定条件；不写物理/真实飞机外推。

## 11. 待审阅/待裁决项

1. 已由 D-S0-2 关闭：五 split（D-01）、端点 ID 与语义（D-02/04）、预算映射（D-03）、task_id 格式（D-05）、legacy v1 路径（D-06）。
2. 仍待 A5/负责人确认：确定性重跑子集（200 runs×3）是否足够；S1 计算资源与墙钟上限（当前估计 ~12 h，无物理调用）；v3 冻结包生成后是否按 APPROVE_FOR_S1_FORMAL 一次打开 meta_test。
3. 本计划中 meta_test 任务数 20 与 family v3 一致；OOD/负控不进入主统计分母。

## 12. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | Lead（task-186） | 首次生成 S1 统计分析与预注册计划草案 |
| v1.1 | 2026-11-05 | Lead（task-190/S0-2） | 按 A5-S0-M02/M03/M04 与 D-S0-2-02/03/04 关闭端点 ID、预算映射、端点语义；五 split 与 split_digest 覆盖明确 |
| v1.2 | 2026-11-06 | Lead（R-V4-08） | Holm 唯一族键 (primary_endpoint,budget_B,K)、成员 C1–C4、C5 排除、动态族大小；与合同 v1.3/prereg 冻结口径一致 |
