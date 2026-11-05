# P4 路线A S1 执行计划与接口合同（v1.0）

> 状态：S0-2 已由 A5 判定 COMPLETE / APPROVE_FOR_S1_FORMAL（`S0_2_A5_review_phase2.md`，sha256 `ea9b2eb7…`），本文件是 S1 formal 的实现合同。
> 约束：全合成解析任务、physical_call_count=0；不合并 main；不新开 PR；仅 Lead 写 GitHub；旧 M2/M5/M6 只读。

## 1. 目标

回答 Issue #7 D-P4-003 §3-S1 的单一主问题：在**任务级未见**的 F-QE-feasible-v3 新族 meta_test 上，把 K-shot 支持集真实评价计入预算并闭环进 BO 初始化后，FOMAML-Kshot-BO 相对 Pretrain-Kshot-BO / Random-BO / DE 是否有可复现的约束优化改进。

结论只允许三类：SUPPORTED_IMPROVEMENT / NO_SIGNIFICANT_IMPROVEMENT / INCONCLUSIVE。允许负结果。

## 2. 已冻结输入（不得修改）

- 冻结包：`research/concorde_metaopt/optimization_runs/p4ra-s0-2-freeze-20261105T072500Z/`
  - 8 payload：tasks / meta_task_split / v3_isolation_report / frozen_family / preregistration / budget_fairness_report / digest_manifest / freeze_summary。
  - 冻结不变量：family_version=`p4ra-family-v3`；family_fingerprint=`e56e6921…`；split_hash=`cd597d01…`；prereg_digest=`6981f503…`；analysis_plan_digest=`37eee53c…`；radius_base=0.64；计数 60/20/20/10/10。
- 统计计划：`docs/planning/p4_route_a_s1_statistical_plan_20261105.md`（v1.1）。
- S0-2 设计合同：`docs/planning/p4_route_a_s0_design_contract.md`（v1.1，五 split / 预算映射 / 端点 ID / task_id 格式 / FC-01..13）。

## 3. 实现模块与文件所有权（互不重叠）

### 3.1 S1 runner / 臂闭环（A1）

- 新增：`research/concorde_metaopt/meta_learning/s1_runner.py`
- 修改：`research/concorde_metaopt/meta_learning/m5_arms.py`（K-shot 闭环、预算记账、五臂）
- 新增测试：`research/concorde_metaopt/tests/test_s1_runner.py`
- 责任：按冻结包生成 **21,000 run 分层正式网格**；每个 run 执行「K 支持评价 → 8−K 新初始点 → B−8 主搜索」；逐 run 断言 billable=B；输出 `run_records.jsonl`；确定性重跑子集；标签打乱负控；raw_digest_manifest；不做统计推断。
- 正式网格（`s1_runner.py --grid formal`，必须 fail-closed 校验）：

| 层 `grid_stratum` | B | K | 组合数 |
|---|---|---|---|
| main | 64 | 0,3,5 | 5 臂×3K×20 任务×10 opt×3 meta = 9,000 |
| secondary | 128 | 3,5 | 5×2×20×10×3 = 6,000 |
| exploratory | 64,128 | 1 | 5×2×1×20×10×3 = 6,000 |

合计 21,000；`(B=128,K=0)` 组合必须为 0。默认 cartesian 网格 24,000 仅供测试兼容，不得用于 formal run。

### 3.2 S1 统计 / 图表 / 校验（A6）

- 新增：`research/concorde_metaopt/meta_learning/s1_analysis.py`
- 新增：`research/concorde_metaopt/meta_learning/s1_figures.py`
- 新增测试：`research/concorde_metaopt/tests/test_s1_analysis.py`
- 责任：读取 `run_records.jsonl`，先做冻结/端点/预算/CLONE 强校验，再按统计计划输出 `aggregate.json`、主表 CSV、7 张图与 `figure_status.json`、结论层；不做 runner 执行。

### 3.3 文档 / 需求矩阵（A4）

- `docs/reviews/p4_route_a_s1_requirement_matrix.md`（新增）
- `docs/planning/p4_route_a_s1_execution_plan_20261105.md`（本文件；A4 可补充验收映射）
- 不修改冻结包与旧 run。

### 3.4 复核（A5 / A3）

- A5：代码审阅 + 独立复跑 + 负控 + 统计口径审阅，输出 `APPROVE_FOR_S1_RUN` 或 `CHANGES_REQUESTED`。
- A3：run 前后隔离审计（旧冻结件、main、P5、其他 worktree、0 solver）。

## 4. 数据合同：run_records.jsonl

每行一个 run（UTF-8 canonical JSON，字段顺序按字典序、separators=(',',':')、ensure_ascii=False）：

| 字段 | 类型 | 说明 |
|---|---|---|
| run_id | str | `<run_id>--<arm>--B<B>--K<K>--T<task>--MS<meta_seed>--OS<opt_seed>`，全局唯一 |
| run_group_id | str | 本次 S1 run 的顶层 run_id |
| family_version / family_fingerprint / split_hash / prereg_digest / analysis_plan_digest | str | 来自冻结包，逐 run 回显 |
| split | str | 必须 `meta_test`（主统计）或 `meta_test_ood`/`negative_control`（单独层，不入主统计分母） |
| grid_stratum | str | main / secondary / exploratory（formal 网格必填；cartesian 为 null） |
| task_id | str | 必须匹配 `^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$` |
| arm | str | RAND-BO / PRETRAIN-KSHOT-BO / FOMAML-ZERO-BO / FOMAML-KSHOT-BO / DE |
| budget_B / K / initial_designs / bo_calls | int | 必须满足 K + (8−K) + (B−8) = B，initial_designs=8，bo_calls=B−8 |
| meta_seed / opt_seed | int | meta_seed∈{0,1,2}；opt_seed∈0..9 |
| identifiability | str | IDENTIFIABLE / CLONE_OF_FOMAML-ZERO-BO（仅 K=0 FOMAML-KSHOT-BO） |
| billable_evals / support_evals / initial_evals / bo_evals | int | support_evals=K，initial_evals=8−K，bo_evals=B−8，billable_evals=B。K 次支持评价在实际执行中只调用评估器一次（之后为缓存命中）；arm 内 true_evals_used=B−K，加上支持集 K 次实际评价后总真实（合成）评价恰为 B |
| endpoint_values | object | 见 §5，9 个 ENDPOINT_ROW_KEYS |
| fallback_values | object | best_objective_raw / min_constraint_violation_sum |
| cost | object | adaptation_wall_s / proxy_scoring_cost / peak_memory_mb / total_wall_s |
| physics | object | physical_call_count=0、physical_call_sources=[]、physics_guard=PASS |
| status | str | OK / FAILED_BUDGET_MISMATCH / FAILED_LEAKAGE / FAILED_NONFINITE / FAILED_OTHER |
| failure_reason | str|null | status≠OK 时必填 |
| history_digest | str | 该 run 评价历史 CSV 的 canonical sha256（不强制存全历史） |
| record_digest | str | 本行除 record_digest 外字段的 canonical sha256 |

## 5. 端点（规范 ID，禁止别名）

`best_feasible_value`、`gap_to_reference`、`first_feasible_eval_index`、`feasible_hit_rate`、`first_feasible_in_support`、`first_feasible_after_support_index`、`feasible_hit_rate_non_support`、`n_nonnull`、`null_rate`。

- null 不插补、不转 0；无可行点 → 主端点 null。
- gap_to_reference：f* 来自 prereg reference_solution；任一 null → null；`gap=(f_best−f*)/max(|f*|,1e-12)`。
- first_feasible_eval_index：B 个评价按真实顺序 1-based；支持评价占 1..K；无可行 null。
- feasible_hit_rate = 可行数 / B（分母恒 B）。
- 聚合：单 run → (task, meta_seed) 内对 10 个 opt seed 取均值（null 不参与，但保留 null_rate）；meta_seed 等权 → 任务为一级统计单位；OOD/负控不入主统计分母。

## 6. 统计合同（A6 实现）

1. 校验：冻结包三方 sha256/fingerprint/split_hash/prereg_digest/analysis_plan_digest 必须与 run_records 回显一致；ENDPOINT_ROW_KEYS 恰为 9 个规范键且禁用别名；task_id 正则；billable=B；K=0 CLONE 排除；任一失败 → fail-closed（不产结论）。三方冻结校验通过后 meta_test/meta_test_ood 只允许一次性打开，禁止多次 peek 后改分析计划。
2. 比较（预注册）：C1 FOMAML-Kshot vs Pretrain-Kshot；C2 vs Random-BO；C3 vs DE；C4 Pretrain-Kshot vs Random-BO；C5 FOMAML-Kshot vs FOMAML-Zero（K>0）。
3. 检验：双侧 Wilcoxon signed-rank（配对任务差，n=20）；全零或 n<10 → INCONCLUSIVE；效应量 paired Cohen's d + rank-biserial；bootstrap 10,000 次（seed=20261105，百分位法）。
4. 多重校正：每个端点内对该端点可用比较做 Holm-Bonferroni，alpha=0.05；family 定义写入 aggregate.json。
5. 实际显著性阈值：best/gap 相对改进 ≥1%；feasible_hit_rate 绝对差 ≥0.05；first_feasible 改善 ≥ceil(0.05×B)（同 K 内）。
6. 判定：SUPPORTED_BENEFIT / SUPPORTED_HARM / NO_EVIDENCE / INCONCLUSIVE；总体结论需 C1 在 4 主端点至少 2 个 SUPPORTED_BENEFIT 且 0 个 SUPPORTED_HARM，否则 NO_SIGNIFICANT_IMPROVEMENT 或 INCONCLUSIVE。
7. null 率 >70% → 该端点 INCONCLUSIVE，不换终点。
8. 输出：`aggregate.json`、`s1_endpoint_tables.csv`、`s1_identifiability_table.csv`、`s1_budget_audit.csv`、`s1_negative_controls.csv`、`figure_status.json`、7 张 PNG。

## 7. 确定性 / 负控 / 泄漏

- 确定性重跑子集：5 臂 × K∈{0,3} × B=64 × 20 任务 × opt_seed=0 × meta_seed=0 = 200 runs，重跑 3 次；任一 mismatch → fail-closed；全量重跑可选。
- K=0 回归：FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 必须逐字节等价（history_digest 相同）；否则 CLONE 声明无效并 abort。
- 标签打乱负控：在同一支持集上打乱标签重跑诊断性子集；MAML 优势应消失/缩小，否则结论降级并披露。
- 泄漏检查：支持/query 索引不得重叠；reference_solution 不得进入支持标签。
- 物理隔离：逐 run `physical_call_count=0`、`physical_call_sources=[]`、`physics_guard=PASS`。

## 8. 图（规范键名，A6 实现；A5 核对键-文件一一对应）

1. `fig1_meta_training_loss`
2. `fig2_k_shot_adaptation`
3. `fig3_feasible_rate`
4. `fig4_equal_budget_gap`
5. `fig5_fairness_audit`
6. `fig6_k_sweep_delta`
7. `fig7_negative_control_and_determinism`

`figure_status.json` 必须把每个键映射到文件名或 `NOT_APPLICABLE`/`NOT_RUN`，禁止旧键名/文件名漂移。

## 9. 验收（A5 放行 S1 run 的条件）

1. 604 基线测试 + 新增 S1 测试全绿（skipped 只允许 RealOpenVSPIntegrationTests 等既有 skip）。
2. 预算公平：5 臂 × K{0,1,3,5} × B{64,128} 共 40 组合，每组合断言 billable=B；K=0 CLONE 排除；负控测试。
3. 端点：9 键齐全、null 语义、alias 拒绝、负控测试。
4. 统计：Wilcoxon/bootstrap/Holm/阈值/决策规则的单测（含全零、n<10、null>70%、全 null、方向相反等边界）。
5. 冻结校验：篡改 family_fingerprint/split_hash/prereg_digest/analysis_plan_digest/endpoint keys 任一 → fail-closed。
6. 确定性：bundle 两次独立运行逐字节一致；200 runs × 3 mismatch=0；K=0 逐字节等价。
7. 0 物理：全代码路径 physical_call_count=0，无 solver import/启动。
8. 0 绝对路径、无凭据；旧 run/main/P5 未变。
9. 正式网格：`grid --grid formal` 输出 run_count=21,000 且分 9,000/6,000/6,000，`(B=128,K=0)` 为 0；run_config 记录 grid_mode=formal 与 grid_strata 明细；两独立进程输出逐字节一致。

## 10. 阶段门

- 实现完成 → A5 审阅（task 见板）→ 若 APPROVE_FOR_S1_RUN → Lead 书面授权 A2 启动 formal run（21,000 runs，预计 ~12 h，零物理）→ run 完成后 A5 统计/证据复核 + A3 隔离审计 → Lead 发布 Issue #7 S1 回执。
- S1 formal 网格与 run_id 在启动前由 Lead 写入 run_config（grid_mode=formal、grid_strata、run_count=21,000）并冻结；启动后不得改终点/比较集/任务/网格分层。
