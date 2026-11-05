# P4 路线A S0-2 接口与语义冻结裁定（D-S0-2）

> 状态：Lead 裁定（S0-2 输入）；依据 Issue #7 D-P4-003、A5 S0 审阅（APPROVE_FOR_S1_PREP，0 blocker / 4 major / 10 minor，`<EXT>/p4-route-a/a5/S0_A5_review.md`）。
> 目的：在写生成器/冻结包之前，一次关闭 A5-S0-M01..M04 与 m01/m09 的口径冲突；本文件是合同、统计计划、family v3、prereg schema 的四方可引用唯一裁定。
> 约束：physical_call_count=0；不打开 meta_test/OOD/负控正式 holdout；不启动任何求解器/真实优化；不合并 main。

## D-S0-2-01 五 split 规范（关闭 A5-S0-M01）

| split | 角色 | 进入主统计 | 进入 split_digest/split_hash | 任务数 |
|---|---|---|---|---|
| meta_train | 元训练 | 否（只用于训练） | 是 | 60 |
| meta_validation | 元验证/调参/校准 | 否 | 是 | 20 |
| meta_test | 主确证盲测 | **是**（主结论唯一来源） | 是 | 20 |
| meta_test_ood | 分布外诊断 | 否（单独描述层，不得并入主结论） | 是 | 10 |
| negative_control | 负控/机制证伪 | 否（只用于负控结论） | 是 | 10 |

- split_digest / split_hash 覆盖集合 = 全部五个 split 的 task_id 有序列表（按上表顺序串联 canonical JSON 后哈希）。
- 合同 schema 的 split enum 必须为上述五值；FC-06/FC-07 的跨 split 唯一/零交集检查覆盖全部 120 任务。
- 主统计分母只有 meta_test 的 20 任务；OOD/负控结果单独成表，不得与主结论合并。

## D-S0-2-02 端点 ID 统一（关闭 A5-S0-M02）

- 规范 ID（唯一，禁止别名静默映射）：`best_feasible_value`、`gap_to_reference`、`first_feasible_eval_index`、`feasible_hit_rate`。
- `first_feasible_evaluation_index` 为**禁用别名**；合同/统计计划/family v3/prereg schema/分析代码/图表键必须使用统一 ID。
- preregistration.primary_endpoints 只允许上述 4 个 ID；ENDPOINT_ROW_KEYS 显式登记；合成端到端测试须断言该列非空覆盖数符合预期（参考 M5 A5-M5-01 前例）。

## D-S0-2-03 五臂预算映射（关闭 A5-S0-M03）

统一规则（对所有臂、所有 K、所有 B 成立）：每 run 在**同一任务**上按固定顺序评价 B 个真实点，评价历史与标签全臂共享支持集；**K 个支持评价计入 B**。

| 阶段 | 评价点数 | 说明 |
|---|---|---|
| 1. 支持评价 | K | 从支持池选 K 个设计，真实评价；标签对 Pretrain/FOMAML 臂可用，Random/DE 不用于适应（但仍计费，保证公平） |
| 2. 初始设计 | 8−K | 新评价的随机/代理初始点；第 1 阶段已覆盖 K 个，故只需补 8−K |
| 3. 主搜索 | B−8 | BO 臂：B−8 次 BO 迭代；DE 臂：B−8 次 DE 世代评价（其 population 由前 8 个点初始化） |
| 合计 | B | 任何臂 billable 必须精确等于 B，否则该 run 作废 |

- K=0：阶段 1 为 0，阶段 2 为 8；FOMAML-Kshot-BO 与 FOMAML-ZeroShot-BO 同构，登记 CLONE 并排除推断。
- DE 的 8−K 初始点同时作为其初始 population 的一部分；DE 不得因种群机制少评或多评（以实际评价数计）。
- 单测断言：5 臂 × K∈{0,1,3,5} × B∈{64,128}，billable=B；K 未计入或各臂不相等 → fail-closed。

## D-S0-2-04 端点语义（关闭 A5-S0-M04）

1. **参考值**：`f*` = reference_solution.best_feasible_value（数值或 null）；不使用重新评价，不使用历史 run 的物理量。
2. **best_feasible_value** = B 个评价中所有满足全部约束的点的最小目标值；无可行点 = null（不插补、不计 0）。
3. **gap_to_reference**：f_best 或 f* 任一为 null → null；否则 `gap = (f_best − f*) / max(|f*|, 1e-12)`（有符号；优于参考时为负，按原值报告，不截断）。
4. **first_feasible_eval_index**：B 个评价按真实评价顺序的 1-based 序号（支持评价为 1..K），首次可行即记录；无可行 = null。附加字段：`first_feasible_in_support`（bool）与 `first_feasible_after_support_index`（序号−K，若首次可行在支持集内则为 null）。**跨 K 比较时必须声明该 K 依赖性**，不把不同 K 的原始序号直接相减当作增益。
5. **feasible_hit_rate** = 可行评价数 / B（分母恒为 B）；附加 `feasible_hit_rate_non_support` = 非支持可行数 / (B−K)（B>K 时）。
6. **实际显著性阈值**：相对改进以配对基线臂中位数为分母——best 相对改进 = (median_base − median_arm)/max(|median_base|,1e-12) ≥ 1%；gap 相对改进 = (gap_base − gap_arm)/max(|gap_base|,1e-12) ≥ 1%；feasible_hit_rate 绝对差 ≥ 0.05；first_feasible 改善 = idx_base − idx_arm ≥ ceil(0.05×B)（同 K 内比较）。
7. **聚合**：单 run 端点 → (task, meta_seed) 内对 10 个 opt seed 取均值 → 对 20 个 meta_test 任务做配对检验；meta_seed 等权平均为主分析，逐 meta_seed 结果作敏感性报告；任务为一级统计单位。
8. **null 政策**：null 不插补、不计 0；报告 n_nonnull/null_rate；主端点 null 率 >70% → 该端点 INCONCLUSIVE，不据此更换终点。

## D-S0-2-05 task_id 与 family_version（关闭 A5-S0-m09）

- family_version = `p4ra-family-v3`；family_id = `F-QE-feasible-v3`；family_seed = 20261105。
- task_id 正则（唯一）：`^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$`，split 代码 TR=meta_train、VA=meta_validation、TE=meta_test、OD=meta_test_ood、NC=negative_control，序号 000..NNN 在 split 内递增。
- 生成器/隔离报告/合同示例/正则单测必须一致；与 M2/M5/M6 全部 task_id 零交集（程序断言，非空即 fail-closed）。

## D-S0-2-06 legacy prereg 路径（关闭 A5-S0-m06）

- 新 run 只允许 `p4-m5-prereg-v2`（或本阶段冻结的 p4ra-prereg-v1 schema，其 stopping_rules 必须为非空 list[str]、每项 strip 后 len≥2）。
- legacy v1 仅用于**只读验证**历史 M5 run；build_preregistration 恒生成 v2；新增断言：新 run 目录/新 prereg 若标 v1 → fail-closed。校验结果须记录 legacy_warning 供 A5/Lead 确认。

## D-S0-2-07 代码 minor 关闭（A5-S0-m07/m08/m10）

- normalize_stopping_rules：删除未使用导入与不可达分支；落盘统一 `item.strip()`；补前后空格用例。
- 新增 test：v2 缺 stopping_rules 字段 → verify_preregistration 抛 FeasibleV2Error。
- A1 diff 与 S0-2 文档由 Lead 在冻结前提交为固定 commit；A5 对提交后 546 tests 与哈希复核。

## 分工与验收（S0-2）

| 任务 | 负责人 | 交付 |
|---|---|---|
| stat plan v1.1（M02/M03/M04 落为本文件口径） | Lead | docs/planning/p4_route_a_s1_statistical_plan_20261105.md |
| 设计合同 v1.1 + 需求矩阵状态更新 | A4 | docs/planning/p4_route_a_s0_design_contract.md、docs/reviews/p4_route_a_s0_requirement_matrix.md |
| family v3 生成器 + v3 文档 rev2 + 代码 minor + 单测 | A1 | 新模块 + frozen_family/prereg/isolation/determinism/预算公平测试（零求解） |
| S0-2 复审 | A5 | APPROVE_FOR_S1_FORMAL 或 CHANGES_REQUESTED |
| S0-2 集成提交 | Lead | 固定 commit + 546 tests + 哈希记录 |
