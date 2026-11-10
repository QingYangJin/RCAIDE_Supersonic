# D-NEXT-001 路线A（优化器无关热启动）任务 receipt

- 角色：A2（路线A 优化器无关热启动）
- 工作树：`D:\RCAIDE\dnext001\wt-a2`
- 分支：`research/dnext001-a-warmstart`
- 基线 commit：`ea8ad97833eb5ceab291faae643c141a2b219749`（S3 封账 c7221fb + 计划文档）
- 本地交付 commit：见本分支 HEAD（本 receipt 随交付提交；提交消息以 `[D-NEXT-001]` 开头，未推送）
- 阶段验收状态：**NOT_ISSUED**（本 receipt 仅交付路线A合成垂直切片，不做真实物理验证，不构成阶段验收）
- 真实物理求解调用数：**physical_call_count = 0**（未启动 VSPAERO / SU2 / RCAIDE Mission / WaveDrag；全部为合成解析真值）
- 数据来源：`SYNTHETIC_ANALOGUE`（受控 12D 合成任务族），非物理标签

## 1. 交付物

### 1.1 新增代码
| 路径 | 内容 |
| --- | --- |
| `research/concorde_metaopt/warm_start/__init__.py` | 包边界与来源常量导出；声明采样模块不含后端算法、physical_call_count=0 |
| `research/concorde_metaopt/warm_start/synthetic.py` | 受控 12D 合成任务族 S-QC / S-RB、14 维特征（12 设计 + 2 任务上下文）、约束与参考解（SLSQP 多起点，确定性 seed） |
| `research/concorde_metaopt/warm_start/surrogate.py` | 代理快照：zero-shot / 监督预训练 / FOMAML K-shot（复用 meta_learning/maml.py 的 MAMLConfig/TaskEpisode/inner_adapt/meta_train），model_sha 冻结 |
| `research/concorde_metaopt/warm_start/sampler.py` | 共享采样接口 `WarmStartSampler.propose(...) -> ProposedDesigns`，4 来源，LHS 候选池、去重、贪心多样性选择、代理排序/可行性预测、sample_budget/provenance/model_sha |
| `research/concorde_metaopt/warm_start/bo_adapter.py` | BO 适配：先 tell K 个共享观测，再用采样器选 `n_init` 起点真实评价，之后完全走既有 `ConstrainedBayesianOptimizer` 路径（不重写采集函数） |
| `research/concorde_metaopt/warm_start/experiment.py` | 合成矩阵运行器：26 cells × 2 任务 × 3 后端 = 156 runs；产物 run_config/evaluations/metrics/runs.jsonl/paired_comparisons/cell_summary/manifest/SHA256SUMS/README |
| `research/concorde_metaopt/warm_start/figures.py` | 中文 matplotlib 图（fig1 矩阵总览、fig2 anytime、fig3 可行性校准负结果图） |
| `research/concorde_metaopt/optimization/baseline_pso.py` | 新约束 PSO 基线：速度/pbest/gbest 只用真实评价初始化与更新；冻结惯性和学习因子、边界、种子接口；群体多样性诊断 |
| `research/concorde_metaopt/tests/test_warm_start.py` | 21 个契约/预算/防泄漏测试 |

### 1.2 修改代码
| 路径 | 改动 |
| --- | --- |
| `research/concorde_metaopt/optimization/baseline_de.py` | `DifferentialEvolutionBaseline` 新增 `initial_population`、`concentration_threshold=0.10`；外部种群校验（Np≥4、维度、[0,1]）；高度集中时保留前半段并用 LHS 补齐（`lhs_supplement_count`）；返回/记录 `initial_population_source/diversity/concentrated/lhs_supplement_count/final_population_diversity`；预算计数修正（`_budget_left` 以实际评价数为准） |

### 1.3 正式 run 产物
`research/concorde_metaopt/optimization_runs/dnext001-a-warmstart-20261110T1452Z/`
- `run_config.json` / `evaluations.jsonl` / `metrics.json`（每 run 一个目录，共 156 个）
- `metrics.csv`、`paired_comparisons.csv`、`cell_summary.csv`、`runs.jsonl`
- `experiment_config.json`（baseline_commit、git_head_at_run、code_sha256、references、matrix、snapshots model_sha、limits）
- `data_manifest.json`、`SHA256SUMS.txt`
- `figures/fig1_matrix_overview.png`、`figures/fig2_anytime.png`、`figures/fig3_feasibility_calibration.png`
- `README.md`（中文说明与限制）

说明：首次后台任务曾在 75/156 处 exit 1 且 stderr 丢失；单独复现 B=128/K=0 的 BO run 均成功，改用文件重定向重跑后完整完成（156/156，exit 0），故判断为运行环境管道问题而非代码缺陷。早期两版 run（1425Z 被杀、1430Z 半成品）以及 trace 统计口径修正前的 1440Z 已删除，仅保留 1452Z 为正式 run。

## 2. 接口契约与边界

### 2.1 共享采样接口
```python
WarmStartSampler(WarmStartConfig(source, support_size, diversity_weight, feasibility_weight, candidate_pool_size, seed), snapshot=None)
.propose(task_context, design_space, observed_support=None, candidate_pool=None, n_new=None, seed=None) -> ProposedDesigns
```
- `ProposedDesigns.X_init`：`[0,1]^(n×12)`，去重且确定性（同 seed 同输出）；
- `rank_score / predicted_objective / predicted_constraint_margin / predicted_feasibility / uncertainty(可 null) / uniformity_distance / min_support_distance / model_sha / provenance / sample_budget`；
- 四来源：`random`、`zero_shot_surrogate`、`pretrain_supervised`（普通监督，非元学习）、`fomaml_kshot`（K∈{0,1,3,5}，`maml.inner_adapt` 适配）。**Full MAML 未使用**（计划要求只作对照，本切片未跑）；
- 边界：采样模块内无 BO 采集函数、无 DE 差分/选择算子、无 PSO 速度更新（单测用 AST 扫描模块名/导入断言）；代理预测只用于排序，**不写回真实观测**，也不参与 pbest/gbest 判定；
- `sample_budget.planned_true_evaluations = support_size + n_new`（热启动阶段真值评价预算，不含优化器内部预算）。

### 2.2 三个后端预算口径（总预算 B 含 K 个共享观测）
- BO：K 个共享观测 → 采样器 `n_init=max(1,min(4,B-K))` 个起点 → 剩余预算走 `ConstrainedBayesianOptimizer.ask/tell`；trace 含 support+initial+bo；
- DE：`remaining=B-K`，`Np=max(4,min(8,remaining))`，外部 `initial_population`，全种群初始真实评价计入预算，trace 以 support 记录开头；
- PSO：`swarm=max(4,min(8,B-K))`，外部 `initial_positions`，初始 pbest/gbest 全部来自真实评价，trace 以 support 记录开头；冻结参数：inertia=0.7298、c1=c2=1.49618、v_max=0.2×(ub-lb)。

## 3. 实验设计

- 合成任务族（12D，纯解析真值）：
  - S-QC：耦合二次目标 + 两个错位球约束（目标偏移/上下文偏移），约束相互竞争，任务上下文 (0.55,-0.65)；实测随机点可行率约 38%；
  - S-RB：Rosenbrock 带 + 均值上下界 + 二阶矩约束，任务上下文 (-0.70,0.45)；随机点可行率约 15%；
  - 参考解：`scipy.optimize.minimize(SLSQP)` 32 起点、4000 点预筛、确定性 seed；S-QC objective*=-0.214362，S-RB objective*=-0.220417；reference 记录于 experiment_config.json。
- 矩阵（26 cells，2 任务 × 3 后端 = 156 runs，seed=0）：
  - smoke：B∈{16,32,64,128} × K∈{0,5} × ρ=0 × {random, fomaml_kshot}；
  - extension：B=64 × K∈{1,3} × ρ∈{0,0.25,0.5,0.75} × fomaml_kshot；
  - source_compare：B=64 × K=3 × ρ=0 × {zero_shot_surrogate, pretrain_supervised}。
- 指标：first_feasible_eval、feasible_hit_rate（可行评价数/B）、best_feasible_value、gap_to_reference、anytime best feasible @B=8/16/32/64、DE/PSO 最终多样性、配对比较（同任务/同后端/同 B/K/ρ/seed）。
- 复跑命令（工作树根目录）：
  ```powershell
  & D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.warm_start.experiment --stamp <UTC时间戳>
  & D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.warm_start.figures
  ```

## 4. 结果摘要（156 runs，全部 status=completed）

- 预算：BO 52/52 精确用满；PSO 52/52 精确用满；DE 45/52 用满，7 次因既有 `no_accepted_trial_in_generation` 停滞规则提前终止（48/32/37/57 次评价，均未超预算）。该 7 次是 DE 既有终止语义，非预算越界；在配对比较中按统一 B 作为分母，属对 DE 偏保守/偏严格的口径。
- 可行性：156 runs 的 `first_feasible_eval` 与 `best_feasible_value` 均非空，说明合成族存在可学习可行域；所有 run 的 physical_call_count=0。
- 来源总均值（全部 cells）：
  - BO：random ≈ first 6.75 / hit 0.410 / best 0.380；fomaml ≈ 6.78 / 0.527 / 0.318；pretrain ≈ 5.00 / 0.727 / 0.112；zero-shot ≈ 5.00 / 0.445 / 0.286；
  - DE：random ≈ 4.50 / 0.357 / 0.268；fomaml ≈ 12.06 / 0.200 / 0.467；
  - PSO：random ≈ 4.50 / 0.690 / 0.068；fomaml ≈ 7.78 / 0.683 / 0.080；pretrain ≈ 15.0 / 0.578 / 0.253。
- 配对比较（54 对，treatment=fomaml_kshot）：
  - vs random（48 对）：BO win 6 / loss 8 / tie 2；DE win 0 / loss 16；PSO win 2 / loss 14；
  - vs pretrain（6 对，B=64/K=3/ρ=0）：BO loss 1 / tie 1；DE win 1 / loss 1；PSO win 1 / loss 1。
  - **结论（负结果）：在本合成族、单 seed、同预算配对下，FOMAML K-shot 热启动总体不优于随机采样；仅 BO 在部分 cell（如 B=64/K=5、S-QC）best value 更好，但不足以翻转总体配对结果。**
- 可行性校准（负结果）：代理预测可行概率明显高估真实可行率（fig3）：zero-shot 预测≈0.54 vs 真实≈0.12；pretrain 预测≈0.38 vs 真实≈0.25；FOMAML 预测≈0.53 vs 真实≈0.065。说明当前代理排序信号主要来自目标值而非可行性判别。
- 多样性：DE 最终多样性随 ρ 增大（≈0.220→0.305）但 hit rate 未同步提升；PSO 多样性≈0.11–0.12 且随 ρ 变化小；ρ 增大使部分 DE 组合更易停滞。
- 图：`figures/fig1_matrix_overview.png`（首次可行/预算、gap vs K、四来源对比、多样性 vs ρ）、`figures/fig2_anytime.png`（三后端 anytime）、`figures/fig3_feasibility_calibration.png`（校准负结果）。

## 5. 测试

| 命令 | 结果 |
| --- | --- |
| `& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_warm_start.py -q` | **21 passed**（sampler 接口契约、X_init 形状/边界/唯一性、support 数不匹配、无快照校验、采样模块无后端内部实现、采样期不读真值/不写回共享观测、三后端预算守恒 B=16/K=2、DE 外部种群与集中度/LHS 补充、DE 非法种群拒绝、PSO 真值 pbest/gbest、PSO 冻结接口、合成标签来源标注） |
| `& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_de_toy.py research/concorde_metaopt/tests/test_bo_toy.py research/concorde_metaopt/tests/test_physical_call_accounting.py research/concorde_metaopt/tests/test_budget_and_cache.py -q` | **81 passed**（修改 baseline_de.py 后的回归；含物理调用计费） |

## 6. 未完成项与风险

1. **单 seed**：仅 seed=0，无重复种子/置信区间，配对结果只能作方向性证据（计划允许先最小 smoke 后扩展，但本轮未扩展多 seed）。
2. **纯合成**：S-QC/S-RB 是 `SYNTHETIC_ANALOGUE`，参考解来自合成真值上的 SLSQP，不可当作真实物理结论；真实物理调用=0，未验证 Concorde 12 维真实评价。
3. **负结果为主**：FOMAML 热启动不优于随机、可行性预测高估；后续若进入真实闭环需先修正可行性判别与校准，不能直接沿用本次排序。
4. **Full MAML 对照未跑**：本轮只实现 FOMAML（计划默认），Full MAML 仅保留接口一致性（同一 maml.py 配置可切换 first_order=False），未进入矩阵。
5. **DE 提前停止 7/52**：由既有 `no_accepted_trial_in_generation` 规则触发，导致该 7 个 run 未用满预算；已在 metrics 中如实记录 `budget_conserved=false` 与 `evaluations`，未做任何补点/伪造。
6. **配对覆盖不完整**：zero-shot/pretrain 只有 B=64/K=3/ρ=0 的 cell，缺少同预算随机对照，因此仅与 FOMAML 配对（6 对），不能单独下“优于随机”的结论。
7. **BO 代理路径**：BO 适配复用既有约束 BO，采集函数与模型未改动；其 epsilon/候选数参数固定，未做敏感性分析。
8. 首次后台 job 异常退出（75/156）原因未定位到代码层（重跑 156/156 成功），保留为环境风险记录。

## 7. 合规声明

- 只写本工作树 `D:\RCAIDE\dnext001\wt-a2`；未写 `D:\RCAIDE`、`D:\RCAIDE\dnext001\repo` 或其它 `wt-*`；未 `git push`、未合并 main、未改写历史。
- 未触碰 S1/S2/S3 冻结 run 目录、manifest、SHA 文件；本 receipt 与新增 run 目录均为本轮新产物。
- 真实物理求解调用数 = 0；未启动 VSPAERO / SU2 / RCAIDE Mission / WaveDrag；所有 run 均标注 `physical_call_count=0`、`source_kind=SYNTHETIC_ANALOGUE`、`physical_validation_status=NOT_APPLICABLE_SYNTHETIC`。
- 未把代理预测写入真实观测；未用预测值初始化/更新 PSO 的 pbest/gbest；未把不同后端包装成不同训练方法。
