# P4 路线A S1 执行计划与接口合同（v1.4）

> 状态：v1.4（2026-11-06）。v1.4 按 A5 phase3（S1R3-B01/B02/M01/M02）与 R-V4-08 增补 v4c：S0-4 确证包（prereg 三块、code_sha 绑定、legacy formal 拒绝）、merge 默认拒绝非确证包、A5 phase4 终审（含 merge delta）。v1.3 增补 R-V4-07 并行分片/merge 合同。
> 历史：v1.2（2026-11-05）。S0-2 包与 A5 phase2 `APPROVE_FOR_S1_FORMAL` 只对 S0-2 静态/测试范围有效；A5 S1 rev2（`S1_code_review_rev2.md`，sha256 `d5a0979a…`）判定 CHANGES_REQUESTED（2 blocker / 4 major / 6 minor），该批准在确证性用途上被收窄（S1R2-M03）。确证性 S1 formal **尚未获准**，须等待 S0-3 v4 冻结包 + c0cb2cd 之后干净树重建的正式工件 + A5 phase3 `APPROVE_FOR_S1_RUN` + Lead 书面授权。
> 约束：全合成解析任务、physical_call_count=0；不合并 main；不新开 PR；仅 Lead 写 GitHub；旧 M2/M5/M6 与旧 S0-2 包只读；readiness/诊断不得读取新 meta_test/meta_test_ood。

## 1. 目标

回答 Issue #7 D-P4-003 §3-S1 的单一主问题：在**任务级未见**的 F-QE-feasible-v3 新族 meta_test 上，把 K-shot 支持集真实评价计入预算并闭环进 BO 初始化后，FOMAML-Kshot-BO 相对 Pretrain-Kshot-BO / Random-BO / DE 是否有可复现的约束优化改进。

结论只允许三类：SUPPORTED_IMPROVEMENT / NO_SIGNIFICANT_IMPROVEMENT / INCONCLUSIVE。允许负结果。

## 2. 已冻结/待冻结输入（旧包只读；v4 以 S0-4 为准）

- **旧 S0-2 包（只读，历史复现/负控，不得用于确证 S1）**：`research/concorde_metaopt/optimization_runs/p4ra-s0-2-freeze-20261105T072500Z/`
  - 8 payload：tasks / meta_task_split / v3_isolation_report / frozen_family / preregistration / budget_fairness_report / digest_manifest / freeze_summary。
  - v3 冻结不变量（仅 legacy）：family_version=`p4ra-family-v3`；family_fingerprint=`e56e6921…`；split_hash=`cd597d01…`；prereg_digest=`6981f503…`；analysis_plan_digest=`37eee53c…`；radius_base=0.64；计数 60/20/20/10/10。
  - 旧 A5 phase2 报告与旧 A2 readiness（`BASELINE_989FC0A`）不得作为 v4 formal 就绪证据。
- **确证性 v4 输入（S0-4，待 A1 在最终代码 commit C 的干净 detached worktree 生成、Lead 提交 commit D、A5 phase4 审）**：
  - family_version=`p4ra-family-v4`；family_id=`F-QE-feasible-v3`；holdout_seed=`20261106`；五 split 计数 60/20/20/10/10；仅 meta_test 20 + meta_test_ood 10 重采样；meta_train/meta_validation/negative_control 与 S0-2 逐位相同。
  - 冻结包命名：`p4ra-s0-4-freeze-<UTC>Z`；产物、run_id、git_sha、code_sha、holdout_seed 必须写入 frozen_family/prereg/freeze_summary/digest_manifest；determinism_report 必须进 payload 链（digest_manifest/freeze_summary.artifacts/SHA256SUMS）。
  - prereg 必须含 holdout_package/c5_policy/structural_identifiability 三块（R-V4-08-02）；frozen/prereg confirmatory_eligible=true；legacy v3/S0-2/S0-3 包在 formal 路径一律 fail-closed，仅 exploratory 可显式 --allow-legacy。
  - code_sha 绑定（R-V4-08-03）：包必须在 commit C 干净 checkout 生成；analysis formal 重算当前 package_code_sha() 与包内 code_sha，不一致即 `S1_ANALYSIS_CODE_SHA_DRIFT`。
  - family_fingerprint / split_hash / prereg_digest / analysis_plan_digest 以 S0-4 `freeze_summary.json` 的实际值为准；本文件不预填、不得沿用 v3/S0-3 哈希。
  - radius_base=0.64 的校准证据在 meta_train/meta_validation 上仍有效（仅 holdout 重采样）；旧 S0-2 包不得改写。
- 统计计划：`docs/planning/p4_route_a_s1_statistical_plan_20261105.md`（v1.2；C5-B/pair-level 补丁以 R-V4-02/R-V4-04 为准；Holm 唯一口径见 R-V4-08-01）。
- 设计合同：`docs/planning/p4_route_a_s0_design_contract.md`（v1.3，五 split / 预算映射 / 端点 ID / task_id 格式 / prereg 三块 / C5-B / FC-01..15）。
- v4 整改裁定：`docs/planning/p4_route_a_s1_v4_remediation_rulings_20261105.md`（R-V4-01..06，sha256 `f71e32a9…`）、`p4_route_a_s1_v4b_parallel_rulings_20261105.md`（R-V4-07）、`p4_route_a_s1_v4c_phase3_rulings_20261106.md`（R-V4-08）。

## 3. 实现模块与文件所有权（互不重叠）

### 3.1 S1 runner / 臂闭环（A1）

- 已存在（c0cb2cd）：`research/concorde_metaopt/meta_learning/s1_runner.py`
- 修改：`research/concorde_metaopt/meta_learning/m5_arms.py`（K-shot 闭环、预算记账、五臂）
- 已存在测试：`research/concorde_metaopt/tests/test_s1_runner.py`
- 责任：按 S0-4 冻结包生成 **21,000 run 分层正式网格**；每个 run 执行「K 支持评价 → 8−K 新初始点 → B−8 主搜索」；逐 run 断言 billable=B；输出 `run_records.jsonl` 与 run 级 `identifiability_report.json`（pair-level 字段）；确定性重跑子集；标签打乱负控；raw_digest_manifest；不做统计推断。
- **并行执行合同（R-V4-07，v4b）**：正式 21,000 分 15 片（3 meta_seed × 5 opt_seed 对，每片 1,400 runs，同一顶层 run_id）并行执行；新增 `s1_runner merge` 子命令按完整 formal plan 校验分片并集恰好=21,000、无 missing/extra/duplicate、按 plan 顺序合并并重算 identifiability report。详见 `docs/planning/p4_route_a_s1_v4b_parallel_rulings_20261105.md`。
- 正式网格（`s1_runner.py --grid formal`，必须 fail-closed 校验）：

| 层 `grid_stratum` | B | K | 组合数 |
|---|---|---|---|
| main | 64 | 0,3,5 | 5 臂×3K×20 任务×10 opt×3 meta = 9,000 |
| secondary | 128 | 3,5 | 5×2×20×10×3 = 6,000 |
| exploratory | 64,128 | 1 | 5×2×1×20×10×3 = 6,000 |

合计 21,000；`(B=128,K=0)` 组合必须为 0。默认 cartesian 网格 24,000 仅供测试兼容，不得用于 formal run。

### 3.2 S1 统计 / 图表 / 校验（A6）

- 已存在（c0cb2cd）：`research/concorde_metaopt/meta_learning/s1_analysis.py`
- 已存在（c0cb2cd）：`research/concorde_metaopt/meta_learning/s1_figures.py`
- 已存在测试：`research/concorde_metaopt/tests/test_s1_analysis.py`
- 责任：读取 `run_records.jsonl` 与每个 source run 的 `identifiability_report.json`，先做冻结/端点/预算/CLONE/pair 覆盖强校验，再按统计计划输出 `aggregate.json`（含 `structural_exclusion_counts`、C5 可估计任务数）、主表 CSV、7 类规范图（图面英文；图注/结论中文）与 `figure_status.json`、结论层；C5-B 下 C5 不做 benefit/harm 与 Holm；不做 runner 执行。

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
| run_group_id | str | 本次 S1 run 的顶层 run_id（并行分片共享同一顶层 id，merge 后仍一致） |
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
8. 输出：`aggregate.json`、`s1_endpoint_tables.csv`、`s1_identifiability_table.csv`、`s1_budget_audit.csv`、`s1_negative_controls.csv`、`figure_status.json`、7 张 PNG；run 级 `identifiability_report.json` 列入分析合同产物，analysis 必须加载并消费。
9. **Pair-level 结构性规则（R-V4-02/R-V4-04）**：每个 `(task,B,K,meta_seed)` 组，对每个臂对计算初始设计行 digest 的 `overlap_rate`（交集行数/较大集合行数）；`>=0.90` 判该臂对在该组 `STRUCTURALLY_IDENTICAL`，不进入 benefit/harm 推断，只作描述；不做事后任务剔除；每个比较的排除率必须披露。
10. **C5-B**：C5（FOMAML-KSHOT-BO vs FOMAML-ZERO-BO，K>0）不进入任何 benefit/harm 推断与 Holm 族，只报告结构克隆率/描述性数值；若可推断组覆盖任务数 <10，总固定结论 `NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY`，不得声称适应增益/损害；总体结论仍只依赖 C1。C5 不进入 Holm 并不意味着其他比较可以跳过校正。
11. **Identifiability report 消费**：`identifiability_report.json` 逐 pair 输出 `pair_identifiable`、`structural_status`、`threshold`；顶层 `pair_status_counts`；analysis 校验 schema/组覆盖/与 run_records 的 `(task,B,K,meta_seed,arm)` 一致，缺失即 fail-closed；`aggregate.json`/CSV 输出 `structural_exclusion_counts` 与 C5 可估计任务数。

## 7. 确定性 / 负控 / 泄漏

- 确定性重跑子集：5 臂 × K∈{0,3} × B=64 × 20 任务 × opt_seed=0 × meta_seed=0 = 200 runs，重跑 3 次；任一 mismatch → fail-closed；全量重跑可选。
- K=0 回归：FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 必须逐字节等价（history_digest 相同）；否则 CLONE 声明无效并 abort。
- 标签打乱负控：在同一支持集上打乱标签重跑诊断性子集；MAML 优势应消失/缩小，否则结论降级并披露。
- 泄漏检查：支持/query 索引不得重叠；reference_solution 不得进入支持标签。
- 物理隔离：逐 run `physical_call_count=0`、`physical_call_sources=[]`、`physics_guard=PASS`。
- **readiness/诊断隔离（R-V4-05）**：A1/A2/A6/A5 的 readiness、label-shuffle、克隆率与诊断只能读 meta_train/meta_validation 或合成 pilot 任务；**不得读取新 meta_test/meta_test_ood**；A5 phase3 前对新 holdout 做暴露扫描（EXT/run_records 中不得出现 v4 meta_test 任务）。
- **正式工件重建（R-V4-03）**：在 commit C/S0-4 包生成后的干净 worktree，用 `s1_runner prepare-artifacts --frozen <S0-4 package> --meta-seeds 0,1,2` 默认参数（maml 200 steps / pretrain 50 steps）重建；artifact sha256 写入 A2 readiness 与 run_config；旧 A2 readiness（BASELINE_989FC0A）不得作为 v4 formal 就绪证据；A2 在 v4 提交后重跑 readiness。

## 8. 图（规范键名，A6 实现；A5 核对键-文件一一对应）

1. `fig1_meta_training_loss`
2. `fig2_k_shot_adaptation`
3. `fig3_feasible_rate`
4. `fig4_equal_budget_gap`
5. `fig5_fairness_audit`
6. `fig6_k_sweep_delta`
7. `fig7_negative_control_and_determinism`

`figure_status.json` 必须把每个键映射到文件名或 `NOT_APPLICABLE`/`NOT_RUN`，禁止旧键名/文件名漂移。

## 9. 验收（A5 phase4 放行 S1 run 的条件）

1. 768 基线测试 + 新增 S1 测试全绿（A5 rev2 独立复跑 768 tests / OK(skipped=1)；v4 修复后必须重跑，不得引用旧 604/768 数字作为 v4 证据）。
2. 预算公平：5 臂 × K{0,1,3,5} × B{64,128} 共 40 组合，每组合断言 billable=B；K=0 CLONE 排除；负控测试。
3. 端点：9 键齐全、null 语义、alias 拒绝、负控测试。
4. 统计：Wilcoxon/bootstrap/Holm/阈值/决策规则的单测（含全零、n<10、null>70%、全 null、方向相反等边界）。
5. 冻结校验：篡改 family_version/holdout_seed/family_fingerprint/split_hash/prereg_digest/analysis_plan_digest/endpoint keys 任一 → fail-closed。
6. 确定性：bundle 两次独立运行逐字节一致；200 runs × 3 mismatch=0；K=0 逐字节等价。
7. 0 物理：全代码路径 physical_call_count=0，无 solver import/启动。
8. 0 绝对路径、无凭据；旧 run/main/P5 未变。
9. 正式网格：`grid --grid formal` 输出 run_count=21,000 且分 9,000/6,000/6,000，`(B=128,K=0)` 为 0；run_config 记录 grid_mode=formal 与 grid_strata 明细；两独立进程输出逐字节一致。
10. **v4 holdout 隔离**：S0-4 包由 commit C 干净 detached worktree 两独立进程逐字节一致；meta_train/meta_validation/negative_control 映射与 S0-2 相同；meta_test/meta_test_ood fingerprint 全部变化且与 v3 官方包 120 个 fingerprint 零交集（legacy 280 个 task_id 仅 task_id 零交集）；A5 phase3 暴露扫描=0。
11. **pair-level/C5-B**：identifiability_report.json 含 pair 级字段与 pair_status_counts；analysis 消费并输出 structural_exclusion_counts/C5 可估计任务数；C5 不进 Holm；可估计任务数<10 → `NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY`；不做事后任务剔除。
12. **正式工件与 readiness**：v4 代码提交后干净树 prepare-artifacts 默认 200/50 重建，artifact sha 冻结并绑定 run_config/prereg；A2 readiness 在 v4 提交后 PASS；旧 readiness 不得复用。

## 10. 阶段门（v4c）

1. A1/A6/A4 按 R-V4-08 修复 → Lead 提交 commit C 并 push（不合并 main）。
2. A1 在 commit C 的干净 detached worktree 生成 S0-4 v4c 冻结包（两独立进程 run1/run2 逐字节一致）→ Lead 将冻结包写入仓库并提交 commit D。
3. A2 用 commit C 干净树重建正式工件（默认 200/50，绑定 S0-4）+ readiness v4c + K=5 正式工件克隆率复核（只读 meta_train/meta_validation）。
4. A3 隔离审计 commit C/D（旧 S0-2/S0-3/M2/M5/M6、main、P5、0 solver）。
5. A5 phase4 终审：v4c 修复（B01/B02/M01/M02）+ S0-4 包 + 正式工件 + 分析层三块消费/Holm 动态族 + merge delta；readiness/诊断不得读取新 meta_test/meta_test_ood。
6. 只有 A5 给出 `APPROVE_FOR_S1_RUN`（含 merge delta 复审）且 Lead 书面授权后，A2 才可启动 21,000 formal run：15 分片并行（R-V4-07，15×1,400），每片串行、约 2–3 h 墙钟，随后 `merge` 校验 PASS；零物理。
7. run 完成后 A5 统计/证据复核 + A3 隔离审计 → Lead 发布 Issue #7 S1 回执；回执须披露 holdout 污染事实、H1、C5 结构不可辨识、旧 APPROVE 范围收窄、0 物理、未合并 main。
- S1 formal 网格与 run_id 在启动前由 Lead 写入 run_config（grid_mode=formal、grid_strata、run_count=21,000）并冻结；启动后不得改终点/比较集/任务/网格分层。
- physical_call_count 全程 0；RCAIDE/SU2/WaveDrag LOCKED；旧 PR #3/#6 保持 open 不合并 main。

## 11. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4/Lead | 首次生成 S1 执行计划与接口合同 |
| v1.1 | 2026-11-05 | Lead | 集成 S1 实现/统计口径与 A5 前置映射 |
| v1.2 | 2026-11-05 | A4（task-231） | 按 A5 S1 rev2 与 R-V4-01..06：S0-3/v4 输入、旧 S0-2 只读、identifiability_report 产物、pair-level/C5-B 规则、readiness 不读 test/OOD、正式工件重建、A5 phase3 门；未 commit/push、未执行物理计算 |
| v1.3 | 2026-11-05 | Lead | R-V4-07 并行分片/merge 合同（15 片 × 1,400，同一顶层 run_id，merge fail-closed 覆盖校验）；A5 需含 merge delta |
| v1.4 | 2026-11-06 | Lead | 按 A5 phase3 与 R-V4-08：S0-4 确证包（prereg 三块、determinism 进 payload 链、code_sha 绑定）、legacy formal 拒绝、merge 默认拒绝非确证包、A5 phase4 终审 |
