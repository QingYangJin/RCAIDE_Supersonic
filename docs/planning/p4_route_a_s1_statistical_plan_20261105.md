# P4 路线A S1 统计计划（v1.4）

> 状态：v1.4（2026-11-06，A4 task-224）；依据数据合同 v1.5、R-V4-11 与 A5 phase4b 结论。**本计划不构成 S1_RUN 放行**；S1_RUN=NOT_APPROVED，formal 21,000 NOT_RUN，待 A5 phase4c 与 Lead 书面授权（S0-7）。
> 范围：S1（K-shot→BO 初始化闭环）的预注册、端点、比较、判定与报告；S2/S3 不在本计划。
> 0 物理；不读真实 holdout；不修改旧 run；不 commit/push。

## 1. 目标与三个问题

1. K-shot 适应是否按合同进入正式 BO 初始化，且五臂预算公平、无泄漏；
2. 相对普通 BO/Pretrain-Kshot-BO/FOMAML-ZeroShot-BO/DE，主终点是否有预注册可检验的改善；
3. 结果是否支持进入 S2（完整二阶 MAML），或应保留 FOMAML、停止扩展。

结论口径只有三类：“改善”“未观察到显著改善”“不确定/不可判定”；不得按事后挑选的终点写获胜。

## 2. 任务族与冻结

- family_version=p4ra-family-v4；family_id=F-QE-feasible-v3；family_fingerprint=a1f9462c…；split_hash=cd597d01…；holdout_seed=20261106；radius_base=0.64。
- 五 split：TR 60 / VA 20 / TE 20 / OD 10 / NC 10，共 120 任务；仅 TE（20 任务）进入主统计；VA 用于调参/资格；OD/NC 用于分布外与负控。
- 每任务 support 128 / query 64（旧 v2 的 128 内循环仅作消融基线）；目标/约束标签按合同 §3。
- 冻结包 S0-7：run_id=p4ra-s0-7-freeze-20261106T024200Z；commit K 8118234 入库；git_sha=J 004156c；code_sha=7304d32e…；9 payload+README+SHA256SUMS（sha256 59aa81cd…）、9/9、determinism PASS、final_verify 15/15；S0-6 标 SUPERSEDED_LEGACY 只读。
- 确证包 code_sha 绝对 fail-closed（R-V4-11/FC-20）：包内 code_sha≠当前 package_code_sha() 时，即使 `--allow-code-delta` 也拒绝 grid/run/merge；该 flag 仅 legacy/exploratory 包可用并记录双 sha/evaluation_mode=exploratory。
- 预注册一旦冻结，不得按结果调阈值/换终点/换任务；旧 M5/M6 任务已公开，不得当新盲测。

## 3. 设计、臂与预算

| 臂 | 说明 | 预算 |
|---|---|---|
| Random-BO | 随机初始化 + 普通 BO | B |
| Pretrain-Kshot-BO | 预训练代理 + K-shot 适应 + BO | B |
| FOMAML-ZeroShot-BO | 旧 FOMAML 零样本初始化 + BO | B |
| FOMAML-Kshot-BO | FOMAML + K-shot 适应 + BO | B |
| DE | 差分进化基线（population 计预算） | B |

B∈{64,128}；K∈{0,1,3,5}。五臂共享同一 K 次目标任务评价，且这 K 次必须计入 B；初始化 8 个点中不足 8−K 的由普通策略补足；主搜索 B−8；billable_evals=B（K=0 时 CLONE 规则）。正式网格 21,000 run：9,000/6,000/6,000（对应配置以矩阵 v1.6 与预注册为准）；15 分片×1,400；1,920,000 次合成评价；A2 v4e B128 实测窗口 2.58–3.01h、峰值 4.5743 GiB（A2-V4E-B03，5 runs/1 任务/K=3，measured/predicted=0.8333983992）；首片核对，3.5h 硬上限。

## 4. 预注册（p4ra-prereg-v1）

字段：schema_version、run_id、git_sha、code_sha、family_version/family_id/family_fingerprint、split_hash、split_counts、split_digest、holdout_seed、radius_base、arms、budgets_B、K_values、task_id_regex、primary_endpoint、secondary_endpoints、comparisons、holm_family_key、alpha、bootstrap、stopping_rules、analysis_plan_digest、digest。

强校验：五 split 计数和=120；split_digest 覆盖 120 task_id；task_id 正则 ^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$；holdout_package 为 object 且字段完整；stopping_rules 每项 strip 后 len≥2；canonical JSON 排序/无浮点歧义；冻结后 digest 不匹配即 fail-closed。**确证包（confirmatory_eligible=true）在 code_sha≠当前 package_code_sha() 时必须失败，`--allow-code-delta` 不适用**（R-V4-11-01/FC-20）。

## 5. 端点定义

| 端点 | 定义 | 方向 | 缺失 |
|---|---|---|---|
| best_feasible_value | 预算内可行解的最优目标值 | 越小越好 | 无可行解 null |
| gap_to_reference | (best_feasible−reference)/reference 尺度 | 越小越好 | 无可行解/无参考 null |
| first_feasible_eval_index | 首次可行评价序号（1-based） | 越小越好 | 无可行解 null |
| feasible_hit_rate | 可行评价数/计费评价数 | 越大越好 | 分母 0 null |
| final_best_objective | 最终代理预测最优目标 | 越小越好（仅诊断） | 缺失 null |
| constraint_violation_min | 最小约束违反 | 越小越好（仅诊断） | 缺失 null |
| bo_initial_best | BO 初始化阶段最优目标 | 越小越好（仅诊断） | 缺失 null |
| bo_initial_feasible | BO 初始化阶段是否已有可行解 | 布尔 | 缺失 null |
| n_feasible | 可行评价计数 | 越大越好 | 0 保留 |

聚合：任务为一级统计单位；每任务每臂一个值；随机种子只在任务内平均，不把种子当任务。null 不插值、不补零；报告 null 比例与原因。端点表、CSV、图注使用同一 ID，禁用别名。

## 6. 比较与检验

- C1：FOMAML-Kshot-BO vs Random-BO（主闭环是否有效）。
- C2：FOMAML-Kshot-BO vs Pretrain-Kshot-BO（元学习初始化是否优于普通预训练）。
- C3：FOMAML-Kshot-BO vs FOMAML-ZeroShot-BO（K-shot 适应增量）。
- C4：FOMAML-Kshot-BO vs DE（对强基线）。
- C5-B：结构不可辨识诊断；C5 不出现在任何 benefit/harm 与 Holm 行；仅当可估计任务数≥10 且 pair-level overlap<0.90 时才可解释，否则写 STRUCTURALLY_IDENTICAL/不可判定。

检验：对配对任务差做 Wilcoxon 符号秩（双侧，alpha=0.05）；效应量用配对差中位数/均值与相对变化；bootstrap 10,000 次固定 seed 给 95% CI；多重比较用 Holm，族键唯一 `(primary_endpoint, budget_B, K)`，族内比较由 4 降为 3 时 p_adj 重算。**pair 标签规范化（R-V4-10-01，v1.3 新增）**：两臂名按字典序排序后用单竖线连接 `<lex_smaller>|<lex_larger>`；runner 只用同一函数生成；analysis 加载 identifiability_report 时对每个 pair 键 split("|") 排序归一，非法（非 2 段/空段/未知 arm/重复 arm）fail-closed；归一后与实际 pairwise 计数严格相等，否则 fail-closed。**Holm 族定义不变**：仍按 (primary_endpoint,budget_B,K)，不因 pair 标签顺序变化增删族成员。

主终点=best_feasible_value；其余为预注册次要/诊断端点。禁止按结果更换主终点、用未校正的多个端点挑显著、或把不可辨识的 C5 当结论。

## 7. 判定规则

1. 仅当主终点在 Holm 校正后显著、方向与预注册一致、bootstrap CI 支持、且无泄漏/预算违规，写“改善”。
2. 主终点不显著但次要端点一致改善，只写“未观察到主终点显著改善；次要端点提示…（探索性）”，不得写成获胜。
3. 主终点显著但方向相反或 CI 跨 0，写“无改善/不确定”。
4. 无可行解比例过高导致主终点不可估计，写“不可判定”，报告 null 比例与原因。
5. 任何臂预算不等、K 未计入 B、query 泄漏、旧工件改写、物理调用>0，整批作废并 fail-closed。
6. 总体结论按预注册主终点写；不得用“MAML 更优”之类未经验证的总结替代统计结果。

## 8. 确定性、负控与泄漏

| 项 | 要求 |
|---|---|
| 确定性 | 200 runs×3 固定种子，record_digest 一致；K=0 复现旧行为 |
| 负控 | pair 标签非法/顺序不一致 fail-closed；确证包 code_sha 漂移绝对 fail-closed（S0-5/S0-6 四命令 DRIFT 且无产物）；legacy/exploratory + `--allow-code-delta` 正控放行并记录 frozen/current 双 sha、`evaluation_mode=exploratory`；merge canonical 子集 |
| 泄漏 | 不读 query 标签、不解析最优点、不把代理预测写入真实 observations；支持集标签可入内循环但计入 B |
| 物理 | physical_call_count=0；不启动 solver；不读真实 holdout |
| 旧工件 | 不改写；旧 S0-3/S0-4/S0-5 只读，S0-5/S0-4 标 SUPERSEDED_LEGACY |
| 报告 | 每数字可追溯 run_records/端点表；失败与缺失如实统计 |

## 9. stopping_rules（预注册）

1. 同一分片连续 3 次非确定性失败→停该分片并报告。
2. 预算/计费不一致或 billable≠B→停跑。
3. 检测到 query 标签读取/泄漏→停跑。
4. physical_call_count>0→停跑。
5. 确证包 code_sha 与当前 package_code_sha() 不一致→停跑（无 escape）；仅 legacy/exploratory 显式 `--allow-code-delta` 可继续且必须记录双 sha 与 evaluation_mode=exploratory。
6. holdout 污染（TE 任务出现在训练/调参）→停跑。
7. 资源超 3.5h 硬上限或内存超披露上限→停跑并保留现场。
8. 分片 merge 冲突/canonical 子集不一致→停跑。
9. 旧工件被改写→停跑。
10. A5/A3 要求停止的其他 fail-closed 条件→停跑。

## 10. 交付物

run_config、summary.json、preregistration、data_manifest、run_records.jsonl、CSV（端点/配对/预算/可辨识性）、figures PNG（七类中文图）、中文报告；所有交付物带 SHA256 与来源说明；不得只交成功子集。

## 11. 待审阅

- 合同 v1.5 与统计计划 v1.4 的一致性；
- C1–C4 族键、alpha、bootstrap seed、最小可检出效应；
- C5-B 的“不可判定”措辞；
- 15 片窗口 2.58–3.01h 在首片启动前的复核；
- A5 phase4c verdict 与 Lead 授权范围（S0-7/SHA256SUMS/run_id/15 片/3.5h）。

## 12. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4 | 初稿：任务族、五臂、端点、C1–C5、判定、stopping |
| v1.1 | 2026-11-05 | A4 | 按 R-V4-02/-03 补预注册校验、null 规则、readiness 隔离 |
| v1.2 | 2026-11-06 | A4 | 按 R-V4-08 补 Holm 唯一族键、C5 排除、动态族大小；867 tests 基线 |
| v1.3 | 2026-11-06 | A4（task-224） | 同步合同 v1.4/S0-6/R-V4-10/947 tests；§6 新增 pair 标签字典序规范化（Holm 族定义不变）；未 commit/push，0 物理 |
| v1.4 | 2026-11-06 | A4（task-224） | 按 R-V4-11 与 A5 phase4b：S0-7（J 生成/K 入库）、确证包 code_sha 绝对 fail-closed（FC-20）、949 tests、15 片窗口 2.58–3.01h、phase4c 待审；未 commit/push，0 物理 |
