# P4 路线A S3 执行计划：约束感知初始化与低成本适应消融

- 文档路径：`docs/planning/p4_route_a_s3_execution_plan_20261107.md`
- 版本：v1.0（2026-11-07T04:35:00Z 草稿）
- 状态：DRAFT_FOR_A5_M0_REVIEW（未经 A5 APPROVE 前不构成执行合同）
- 作者/唯一集成者：Lead（teammate 不得提交、不得写 GitHub）
- 上游合同：Issue #7（https://github.com/QingYangJin/RCAIDE_Supersonic/issues/7，D-P4-003，body 5,150 字符）；`docs/planning/p4_route_a_stage_improvement_plan_20261105.md` 的 S3 条；S1 正式回执 commentId 6684142041；S2 正式回执 commentId 6693991661
- 基线提交：`8da84fc105755825561829d4fb371f2baea57438`（research/p4-route-a-s3 的父提交，S2 docs closeout）
- 工作树：`D:/RCAIDE-s3-dev`，分支 `research/p4-route-a-s3`（本计划为 S3 首个提交）
- 证据根（仓库内）：`research/concorde_metaopt/evidence/s3/`
- 外部记忆根（不得入库）：`C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/p4-route-a/`

## 0. 阶段前提、授权口径与硬边界

### 0.1 阶段前提（S3 条件开启）

Issue #7 §2/§4 规定：S3（约束感知初始化与方法效率消融）在 S1/S2 验收后条件开启；Leader 负责 S0→S3 阶段批准与唯一 GitHub 发布；每一阶段需 A5 APPROVE 方可放行下阶段正式实验。本阶段开启依据：

| 条件 | 证据 | 状态 |
|---|---|---|
| S1 正式 run 已执行并经 A5 结果复核、A3 审计、Issue #7 回执 | commentId 6684142041 | SATISFIED |
| S2 正式 run 已执行并经 A5 结果复核与证据包复核、A3 隔离审计、Issue #7 回执 | commentId 6693991661；包 rev3 12940c5；closeout（S2_CLOSEOUT_20261107.json） | SATISFIED |
| S1/S2 均 physical_call_count=0、无真实求解 | 两阶段回执与 A3 审计 | SATISFIED |
| S3 属 Issue #7 已批准范围（算法代码 + 全合成解析任务离线训练/对照） | Issue #7 当前批准段 | YES |
| S3 是否需要新的负责人预算授权 | 不需要（零真实求解；不新增 A/B/C/D 类 VSPAERO/RCAIDE/SU2 调用） | NOT_REQUIRED |

Leader 阶段开启记录：`<EXT>/p4-route-a/lead/S3_STAGE_OPENING_20261107.json`（记录开启时 UTC、依据提交、A5/A3 回执、门禁链；本计划 commit 后另存引用）。

### 0.2 硬边界（任一违反即 fail-closed）

1. `physical_call_count = 0`；不启动 VSPAERO/RCAIDE/SU2/WaveDrag/CFD/Mission/Gmsh 等任何真实求解器或子进程；评估器只能是本仓库内的解析合成函数。
2. 不访问网络资源做训练/评估；不下载数据；不调用外部 API。
3. 不合并 main；不新开 PR；旧 PR #3/#6 保持 open；仅 Lead 写 GitHub。
4. 旧冻结件只读：S0-2..S0-7、S1（s1-formal-*）、S2（p4ra-s2-prereg-*、s2-formal-*）、M2/M5/M6 的一切文件不得修改；S3 只新增文件。
5. 唯一写入域：`D:/RCAIDE-s3-dev` 的 S3 新增/修改文件 + 外部记忆根。不得写 `D:/RCAIDE` 主库、`D:/RCAIDE-s2-dev`、其他 worktree。
6. 不学习 BO 采集策略、不做路线B；不实现 P5/P6；不实现真实飞机 BO/DE；不做真实航空元训练。
7. 不使用 S1/S2 任务族或任何已见任务充当 S3 盲测集；S3 的 meta_test/meta_test_ood 必须来自全新族 F-QE-conflict-v1，且在任何调参/选型前未生成标签（见 §2.3）。
8. 不伪造数据：缺失即 NOT_RUN/None，不插补、不筛选有利任务。

### 0.3 门禁链（每步 A5 verdict 才放行下一步）

| 门 | 产出 | 放行条件 |
|---|---|---|
| M0 设计门 | 本计划 v1.x + S3 阶段开启记录 | A5: APPROVE_FOR_S3_CODE |
| M1 代码/校准门 | 家族实现+校准报告+ANIL+臂+runner+prereg 生成器+测试 | A5: APPROVE_FOR_S3_CODE（代码审阅） |
| M2 预注册门 | 新族冻结包、prereg JSON、FD/梯度门、冻结记录 | A5: APPROVE_FOR_S3_RUN |
| M3 正式 run 授权 | Lead 书面授权（task/worktree/out_dir/预算/停止规则） | Lead 签发 |
| M4 结果门 | run 证据、A2 报告、A5 独立复核 | A5: APPROVE_FOR_S3_RECEIPT |
| M5 证据包门 | 证据包 commit + A5 packaging + A3 隔离审计 | A5: APPROVE_FOR_S3_RECEIPT_PACKAGE；A3 PASS |
| M6 发布 | Issue #7 S3 中文回执（单条） | Lead 发布；阶段验收 NOT_ISSUED |
| S4 | 仅航空数据合同（离线），需另立计划与 A5 门 | 不在本计划范围 |

## 1. 目标、可证伪问题与决策规则

### 1.1 背景（为什么 S3 只能问这些问题）

- M5 发现：MAML 初始化臂的 `feasible_hit_rate` 显著低于普通 BO（配对差 −0.01526/−0.01228，Holm 显著）；其结构原因是旧 F-QE-feasible-v2/v3 的约束中心与目标中心相同（`g = sum w(u-c)^2 - r^2`），目标最优与可行中心重合，可行率问题被弱化/转移。
- S1 发现：K-shot→BO 初始化闭环在目标值主端点 NO_EVIDENCE（四主端点），可行率不是 S1 主端点。
- S2 发现：FULL_MAML 相对 FOMAML SUPPORTED_HARM（k5 相对 −3.394%，19/20 任务更差），因此 S3 不默认升级二阶，适配核心保留 FOMAML，并用 ANIL 做低成本消融。

S3 的唯一干预目标是：**在目标最优点位于可行域外的冲突族上，检验“约束感知的初始点选择”能否提高等预算可行率，并量化其目标值代价**。

### 1.2 可证伪问题

| 编号 | 问题 | 类型 |
|---|---|---|
| Q1（主） | 在 F-QE-conflict-v1 上，K=5 支持集 + 约束感知联合打分的 3 个新初始点，相对仅目标打分的同源初始点，能否在 B∈{64,128} 等预算下提高 `feasible_hit_rate`？ | 确证性（配对任务级检验，Holm 2 检验） |
| Q2（次） | Q1 的可行率收益是否以 `best_feasible_value` 变差为代价？`first_feasible_eval_index` 是否提前？ | 次级/描述性 |
| Q3 | ANIL（仅适应输出层）在可行率上是否相对 FOMAML 非劣（边际 −0.02），且适应/训练成本更低？ | 描述性/成本-性能 |
| Q4 | 新冲突族是否出现“全不可行/全可行”退化？若出现，是否按预注册规则披露 INCONCLUSIVE 而不改任务？ | 诊断门 |
| Q5（条件） | 约束归一化方式、初始点多样性配额是否进一步改善？（Wave B，仅当 Wave A 结果与 A5 同意另立实验卡时执行） | 探索性，不默认 |

### 1.3 假设与决策规则（预注册，M2 冻结）

- H0：在相同预算、相同支持集、相同 BO 引擎下，联合打分与目标打分的任务级平均 `feasible_hit_rate` 无差异。
- 主检验族 C1 = {`feasible_hit_rate`，B=64；`feasible_hit_rate`，B=128}，共 2 个检验，Holm 校正，双侧 Wilcoxon signed-rank（exact），alpha=0.05；效应阈值 = 绝对 +0.02（2 个百分点）。
- 决策枚举（对每个预算分别判定后再给总体结论）：
  - `SUPPORTED_BENEFIT`：Holm p<0.05 且平均配对差 ≥ +0.02；
  - `SUPPORTED_HARM`：Holm p<0.05 且平均配对差 ≤ −0.02；
  - `INCONCLUSIVE`：p<0.05 但效应绝对值 <0.02，或有效配对任务 <15；
  - `NO_EVIDENCE`：p≥0.05。
- 总体 S3 结论：仅当 B=64 与 B=128 均 SUPPORTED_BENEFIT 才可写“约束感知初始化改善可行率”；任一预算 HARM 则如实标注方向不一致；其余为 NO_EVIDENCE/INCONCLUSIVE，并披露目标值代价（Q2）。
- 端点空值规则：`best_feasible_value` 在 run 内无可行点时 = null（不插补、不以惩罚值替代）；`feasible_hit_rate` 分母固定为 B，恒有定义；null 计数必须披露。
- 禁止：事后按任务筛选、按结果调半径/权重、只报告有利预算、把 INCONCLUSIVE 写成 benefit。

## 2. 数据边界与全新冲突任务族 F-QE-conflict-v1

### 2.1 族定义（数学合同）

新增族（在 `task_family.py` 中实现；旧族代码路径不改）：

- `FAMILY_ID = "F-QE-conflict-v1"`；`FAMILY_VERSION = "p4ra-family-conflict-v1"`；`FORMULA_VERSION = "p4ra-formula-conflict-v1"`；`TASK_ID_PREFIX = "p4ra-FQEC-v1-"`。
- 设计变量：u ∈ [0,1]^12（DESIGN_DIM=12，单位盒；复用 `DESIGN_LOWER/DESIGN_UPPER`）。
- 目标：`f(u) = b_eff + sum_i a_i (u_i - c_i)^2`，`b_eff = b + CONTEXT_COUPLING_SCALE*(context_1 + context_2 - 2.0)`（复用现有 context 采样与耦合，不引入新维度）。
- 约束 1（活动/冲突约束）：`g1(u) = sum_i w_i (u_i - d_i)^2 - r^2 <= 0`。
- 约束 2（多约束代理，参考解处不活跃）：`g2(u) = sum_i w2_i (u_i - e_i)^2 - r2^2 <= 0`。
- 冲突构造：目标中心 c 位于 g1 可行域外，且分离度可控：
  - c ~ U(0.20, 0.80)^12；
  - a_i ~ exp(U(log 0.5, log 4.0))；w_i ~ exp(U(log 0.5, log 4.0))；
  - r = clip(radius_base * (1 + 0.20*z), 0.10, 0.30)，z~N(0,1)；radius_base 由 §2.5 校准后冻结（默认候选 0.20）；
  - m ~ U(0.25, 0.75)（分离裕度）；
  - v ~ N(0,I_12)，v = v/||v||；scale = r*(1+m)/||sqrt(w) ⊙ v||；d = c - scale*v；
  - 若 d ∉ [0.10,0.90]^12 或 `||sqrt(w) ⊙ (c-d)|| < r*(1+0.24)`，拒绝并重采样（固定 rng 顺序，最多 50 次，超限则任务失败不静默降级）。
- 参考解（解析 KKT）：`u* = argmin f(u) s.t. g1<=0` 由既有 `_trust_region_diag(c, a, d, w, r)` 精确求解（一维 λ 单调求根，400 次二分，`_LAMBDA_TOL`）；返回 `lambda>=0`、`kkt_residual`。因 c 不可行（g1(c)>0），λ>0、g1(u*)=0。该 u* 对双约束问题仍是全局最优，当且仅当 `g2(u*) < 0`（见下）。
- 约束 2 构造：w2_i ~ exp(U(log 0.5, log 4.0))；e = clip(u* + N(0, 0.01^2), 0.02, 0.98)；`r2 = sqrt(sum_i w2_i (u*_i - e_i)^2 + 0.30)`，从而 `g2(u*) = -0.30` 精确成立，参考解处 g2 严格不活跃。
- 参考解断言（任何一条失败则拒绝该任务并重采样）：
  1. `g1(u*) <= 1e-9`；`g2(u*) <= -0.20`；
  2. `g1(c) > 0`（冲突成立），且报告 `conflict_ratio = ||sqrt(w)⊙(c-d)|| / r = 1+m`；
  3. `lambda >= 0`，`kkt_residual <= 1e-6`；
  4. u* ∈ [0.02,0.98]^12；`REFERENCE_ABS_TOL = 1e-10` 的参考目标复算一致；
  5. `objective_regret = f(c) - f(u*) = sum_i a_i (u*_i - c_i)^2 > 0`（目标最优点不可行造成的代价）。
- 参考解返回（参考解可审计）：`reference_kind = "KKT_CERTIFIED_CONFLICT"`；字段含 `u_star`、`f_star`、`g1_star`、`g2_star`、`lambda`、`kkt_residual`、`margin_m`、`conflict_ratio`、`objective_regret`。
- 真值函数：`truth(designs)` 返回 `objective`、`synth_c01`（g1）、`synth_c02`（g2，正式启用槽）、`feasibility = (g1<=0 and g2<=0)`。约束槽名使用 `SYNTHETIC_CONSTRAINT_SLOTS` 前两个（synth_c01/synth_c02），不新增槽位。
- 负控制：沿用 v3 的 label-shuffle 机制（`split=meta_test_negative_control`，10 个任务），但源任务必须来自新族 meta_train，禁止用 S1/S2 任务。

### 2.2 分片、任务 id 与冻结包

| split | 任务数 | 用途 | 是否允许调参 |
|---|---|---|---|
| meta_train | 60 | FOMAML/ANIL 元训练 | 是（仅训练超参，不动族参数） |
| meta_validation | 20 | 家族校准/代码调试/SMOKE | 是（校准后冻结） |
| meta_test | 20 | 正式确证性评估（主端点） | 否（冻结后只读一次） |
| meta_test_ood | 10 | OOD 描述性诊断（context/半径偏移） | 否 |
| meta_test_negative_control | 10 | 标签打乱负控制 | 否 |

- `FAMILY_SEED = 20261107`；`HOLDOUT_SEED = 20261108`（仅对 meta_test/meta_test_ood 追加进 seed 派生，参照 v3 的 RESEEDED_SPLITS 机制；meta_train/meta_validation/negative_control 不走 holdout 追加）。
- 冻结包路径：`research/concorde_metaopt/evidence/s3/family_package/p4ra_fqec_v1_family_package.json`；包内：`family_id/version/formula_version`、参数分布、参考解证书、每任务 `task_id/task_fingerprint/split/params/seed/reference_kind/reference_kkt_residual`、split→task_ids 映射、包 `package_sha256`、生成代码 code_sha、生成 UTC。
- 任务 id：`p4ra-FQEC-v1-<sha1(family|canonical(params)|seed) 前 16 hex>`；不同 split 的 id 天然不重叠。
- 冻结件 sha256 写入 prereg（`frozen_package.package_sha256`、`task_ids_sha256`、`split_counts`）；正式 run 前 A5 独立核验。
- 旧族（F-QE-feasible-v2/v3）只允许作为“历史诊断对照”只读引用，不得出现在 S3 任何训练/评估/统计中。

### 2.3 数据边界与盲测规则

- 允许训练/调试的数据：meta_train（元训练）、meta_validation（家族校准、SMOKE、代码调试）。meta_validation 结果只能用于族参数校准与代码修复，不得用于报告主端点。
- 盲测：meta_test/meta_test_ood 在 prereg 冻结（M2）前不生成任何评估记录；冻结后只允许 A2 在 Lead 授权下执行一次正式 run；A5 可在复核时读取 run 产物但不得改动。
- 负控制：10 个 label-shuffle 任务只用于诊断，不进入主/次端点统计；必须报告置换 seed。
- 泄漏硬检查（fail-closed，写入 runner 与 analysis）：
  1. 正式 run 的 split 集合必须 ⊆ {meta_train, meta_validation}（训练/候选选型仅用 meta_validation）；正式评估阶段的 split 必须 = {meta_test}（负控制单独段）；
  2. 任何 run 不得读取 holdout 的 query/truth 标签；评估器须记录每次评估的 task_id/split/phase，analysis 复核 holdout_metrics_read=false；
  3. support 与 query 设计不得相交（复用 `query_designs` 的 1e-12 不相交保证）；support 与初始点不得重叠；
  4. 代理训练/适配只使用 support 标签；query 标签不得进入适配、评分、BO 候选排序。

### 2.4 评估器与计费口径（S3 是合成评估，不是物理评估）

- 评估器：`make_synthetic_task_evaluator(task, design_space)`（复用 S1/M5 已审计实现），返回 objective/constraints/feasibility/valid；每次调用记账为 `synthetic_evaluation`。
- 计数合同：每 run 的 `billable_evals = B` 必须精确成立（support K 次 + 新初始 8−K 次 + 主搜索 B−8 次）；support 评价在同一 run 内是缓存命中（cache_hit=true），但仍在 B 内并计入评估记录；DE 臂同样恰好 B 次。
- `physical_call_count = 0` 字段必须存在且为 0；同时记录 `synthetic_call_count = B` 与 `solver_processes_started = 0`；任何真实子进程/网络调用即 fail-closed。
- 评估记录逐条包含：`eval_index/design_u/objective/constraints/feasible/valid/cache_hit/billable/phase/synthetic`；预算超限或记录数不符立即终止该 run 并标 FAILED_BUDGET_MISMATCH。

### 2.5 家族校准协议（M1 阶段，仅 meta_validation，不碰 meta_test）

校准目标：冲突族既可解、又不过难/过易，确保 `feasible_hit_rate` 有区分度。步骤：
1. 生成候选 radius_base ∈ {0.15, 0.20, 0.25} 的 meta_validation 20 任务（其余参数同 §2.1）。
2. 对每个 radius_base 计算：参考证书通过率、每任务 support 池（128 点）可行比例的中位数、最小/最大值、`objective_regret` 分布、`margin` 分布。
3. 接受条件（全部满足）：(a) 参考证书 20/20 通过；(b) support 池可行比例中位数 ∈ [0.02, 0.50]；(c) 没有任何任务的 support 池 128 点全不可行；(d) margin 均值 ∈ [0.30, 0.70]；(e) 参考目标 regret 中位数 > 1e-6。
4. 若三个候选均不满足，允许在 meta_validation 上调整 r 的上下界/采样区间（记录每次尝试），但不得使用 meta_test；最终配置写入校准报告并冻结。
5. 校准报告：`research/concorde_metaopt/evidence/s3/calibration/family_calibration_<UTC>.json`（含每候选统计、接受/拒绝理由、最终选择、sha256）；A5 M1/M2 可复核。

## 3. 干预、臂、公平合同

### 3.1 五臂（Wave A 必须全部执行）

| 臂 id | 类型 | K=5 支持评价 | 8−K 新初始点来源 | 主搜索 | 备注 |
|---|---|---|---|---|---|
| S3-BO-RANDOM | 基线 | 计入 B | shared_initial_designs 前 3 点（随机） | maml_opt BO，B−8 | 无代理 |
| S3-BO-FOMAML-OBJ | 对照 | 计入 B | FOMAML 适配后按预测目标打分选 3 点 | maml_opt BO，B−8 | 只改初始点打分 |
| S3-BO-FOMAML-CON | 主干预 | 计入 B | FOMAML 适配后按联合评分选 3 点 | maml_opt BO，B−8 | 约束感知 |
| S3-BO-ANIL-CON | 消融 | 计入 B | ANIL 头-only 适配后按联合评分选 3 点 | maml_opt BO，B−8 | 低成本 |
| S3-DE | 基线 | 计入 B | support(5)+shared(3) | DE/rand/1/bin，B−8 | 等预算 |

- 所有 BO 臂共享同一 `maml_opt.bayesian.ConstrainedBayesianOptimizer/run_search` 引擎（不修改、不调参），候选数 512；BO 引擎随机种子只由 `(task_id, opt_seed, "s3-bo")` 派生，**不含 arm 名**，保证四个 BO 臂除初始点外随机流一致。DE 种子由 `(task_id, opt_seed, "s3-de")` 派生。
- 所有臂共享同一支持集：`select_support_designs(task, k_shot=5, meta_seed)`（同一 task/meta_seed 下逐位相同）；支持集评价在每 run 开始缓存，臂间不可共享缓存（run 是独立单位）。
- 唯一干预差异：8−K=3 个新初始点的选择（以及 FOMAML/ANIL 的适配方法）。BO 主搜索逻辑、候选池、预算、评估顺序规则完全相同。

### 3.2 代理与联合评分（精确公式，冻结）

- 代理网络：`MAMLConfig(input_dim=12, output_dim=3, hidden_sizes=(64,64), inner_lr=0.01, inner_steps=5, outer_lr=1e-3, tasks_per_batch=8, first_order=True, seed=meta_seed, backend="torch")`；输出 3 维 = [f, g1, g2]；输入仅 12 维设计向量（不含 task_id/context/truth 特征）。
- 训练：FOMAML 在 meta_train 60 任务上训练；ANIL 同配置、仅内循环更新输出层权重/偏置（body 冻结于元学习参数）。训练 episode：每 outer step 采样 8 任务；每任务 support K_train ∈ {5,10}（按元种子与 episode 索引确定，固定 50/50 混合）、query 64 点；loss = query MSE（三输出等权）；outer_steps=200；每 meta_seed 一个模型；训练仅用 meta_train。模型产物（state_dict + config + episode digests + sha256）在 M2 冻结，写入 prereg。
- 每任务标签归一化（仅用 support 标签，K=5）：`f_scale = max(std(f_support), 1e-6)`；`g_scale_k = max(sqrt(mean(g_k_support^2)), 1e-6)`，k∈{1,2}；标准化 `f_tilde = (f - mean(f_support))/f_scale`，`g_tilde_k = g_k / g_scale_k`。该归一化在训练 episode、适配、打分中一致使用；最优/最差 run 的归一化参数必须记录。
- 联合评分（CON 臂）：候选 x 的 `S(x) = f_tilde_hat(x) + 10.0 * (max(0, g1_tilde_hat(x)) + max(0, g2_tilde_hat(x)))^2`；按 S 升序、候选索引升序取前 3 个互异设计。
- 目标评分（OBJ 臂）：`S(x) = f_tilde_hat(x)`；同样取前 3。
- 随机臂：`shared_initial_designs(task_id, opt_seed, count=8)` 的前 3 个（与 S1 相同共享初始点构造）；必须与 support 集无重复（重叠即 FAILED_LEAKAGE）。
- 候选池（打分用）：`task.support_designs()`（128 个固定 LHS 点）去掉 support 的 5 个点，共 123 个候选；候选池 sha256 写入 run 记录；三臂（OBJ/CON/ANIL）使用同一候选池。
- 不确定性：S3 不标定不确定度，所有产物 `uncertainty = null`、`calibration = "NOT_PERFORMED"`；禁止伪概率、禁止把代理输出当置信度。
- 适配成本：FOMAML/ANIL 的适配 wall_s、前向预测次数、候选打分次数、峰值内存写入 run 记录；用于 Q3 成本-性能比较。

### 3.3 预算、K 与公平性约束

- `B ∈ {64, 128}`；K=5（固定）；初始点 8 = 5 support + 3 new；主搜索 B−8；DE 相同总预算；所有臂每 run 恰好 B 次评估。
- 任务、opt_seed、meta_seed 为三层重复；同一 (task, budget, arm) 的 opt_seed 均值在统计前先聚合；meta_seed 是模型训练复制，FOMAML/ANIL 用 3 个模型，RANDOM/DE 的 meta_seed 只作为重复标签（不训练模型，但每 meta_seed 都执行，以保持网格平衡）。
- 公平性断言（fail-closed）：同 (task, budget, opt_seed, meta_seed) 下五臂的 B、K、初始点总数、support 设计集合、BO 引擎配置、候选数完全一致；仅 3 个新初始点与适配方法可不同；克隆检测：若某两臂逐 run 初始点 sha256 完全相同且方法声明不同 → 标 CLONE，排除推断并在报告披露。
- 预算记账：run 记录 `billable_evals == B`、`support_evals == 5`、`initial_evals == 3`、`bo_or_de_evals == B-8`；任何不等即该 run FAILED_BUDGET_MISMATCH，且不进入统计（失败 run 数必须披露）。

## 4. 训练、正式 run 与运行合同

### 4.1 训练（M1/M2，不接触 holdout）

- FOMAML：meta_train 60 任务 × meta_seeds (0,1,2)，outer_steps=200，tasks_per_batch=8，query=64；每 meta_seed 一个模型。
- ANIL：同数据/同 episode 序列/同优化器/同预算，唯一差异是内循环只更新输出层；meta_seed 对应 FOMAML 的同一序列，保证可比。
- 训练产物：`evidence/s3/models/fomaml_meta_<seed>.pt`、`anil_meta_<seed>.pt` + 训练日志/摘要（loss 曲线、wall_s、峰值内存、episode digests、模型 sha256）；模型文件可放仓库（torch state_dict 小，<1MB）或外部并在 manifest 记录 sha；M2 冻结。
- 训练不得使用 meta_validation/meta_test/negative_control；SMOKE 训练可在 meta_train 小子集上跑通。

### 4.2 正式 run 网格

| 维度 | 取值 | 说明 |
|---|---|---|
| meta_test 任务 | 20 | 冻结包 meta_test，主端点 |
| 臂 | 5 | §3.1 |
| 预算 B | 64, 128 | 每 run 精确 B 次 |
| opt_seed | 0..9（10 个） | 初始点/BO/DE 随机流 |
| meta_seed | 0,1,2（3 个） | FOMAML/ANIL 模型复制；RANDOM/DE 重复标签 |
| run 数 | 20×5×2×10×3 = 6,000 | 评估次数 = 5×20×10×3×(64+128) = 576,000（含 support） |
| 负控制 | 10 任务 × 2 预算 × 5 臂 × 10 opt × 1 meta = 1,000 runs | 单独段，不进主统计 |

- 若 M2 计时试点（1 任务 × 5 臂 × B=128 × 1 opt × 1 meta = 5 runs）外推的正式 run 总墙钟 > 90 min，则在 prereg 冻结前把 opt_seed 从 10 降为 5（网格 3,000 runs；在计划 v1.x 修订与 prereg 中记录，不使用 holdout 调整），否则保持 10。
- 正式 run 必须使用 clean worktree；run 目录：`<EXT>/p4-route-a/a2/s3_formal/s3-formal-<UTC>/`；不得写仓库；跑完由 Lead 做哈希核验与打包。
- 运行停止规则：单 run 墙钟 > 60 s 或峰值 > 8,192 MB → 立即停止整个 run，报 RESOURCE_LIMIT，不重试；总墙钟 > 7,200 s → 停止并交部分产物；任何物理/网络调用 → fail-closed；任何预算不符 → 该 run FAILED（不重试），失败率 > 1% 时停止并报 A5。
- 确定性：正式 run 之后执行 3 次确定性重跑，范围 = meta_test 前 2 个 task（按 task_id 排序）× 5 臂 × 2 预算 × 10 opt_seed × 3 meta_seed = 600 runs/次；要求 run_records 逐字节一致（排除 wall_s/时间戳字段，按记录 core digest 比较）；披露“确定性仅覆盖 600-run 分层子集，不是全网格”。
- 运行产物：run_config.json、run_summary.json、run_records.jsonl、model_manifest.json、data_manifest.json、determinism/{r1,r2,r3}/、analysis/（见 §5）、logs/。

### 4.3 run_config / run_summary / record schema（S3 自有，不复用 S2 版本号）

- schema_version：`p4ra-s3-run-config-v1`、`p4ra-s3-run-summary-v1`、`p4ra-s3-record-v1`；字段清单在 `s3_prereg.py` 单源定义，runner 与 analysis 必须导入，不得复制版本常量。
- run_config 必需字段（≥20）：schema_version/run_id/run_mode/stage/prereg_id/prereg_digest/analysis_plan_digest/code_sha/frozen_package/data_boundary/arms/training_budget/evaluation_grid/episode_bank/fd_or_gradient_gate/determinism/record_counts/record_schemas/resource_limits/physical_call_count/synthetic_call_count/evidence_scope/development_set/scope_notes/model_artifacts。
- run_summary 必需字段：run_mode/created_utc/run_status/per_arm_seed/run_counts/resources/environment/model_artifacts_verified/negative_controls/scope_notes/checks。
- record 必需字段：run_id/task_id/split/arm/budget_B/K/meta_seed/opt_seed/initial_designs_sha256/initial_design_row_digests/billable_evals/support_evals/initial_evals/bo_or_de_evals/endpoint_values/fallback_values/cost/physics/synthetic/status/failure_reason/history_digest/record_digest。
- SMOKE 模式：允许小子集（outer_steps/任务数/opt_seed 缩减），必须写 `smoke_overrides` 并在 analysis 记 DISCLOSED；FORMAL 模式严格相等校验。

## 5. 分析、端点与统计合同

### 5.1 端点

| 端点 | 定义 | 用途 |
|---|---|---|
| feasible_hit_rate | 每 run 中 feasible 评估数 / B（B=64/128） | 主（C1） |
| best_feasible_value | 每 run 可行记录的最小 objective；无可行 = null | 次（C2，代价） |
| first_feasible_eval_index | 首次 feasible 的 eval_index（1-based）；无可行 = null | 描述性 |
| initial_feasible_rate | 8 个初始点中 feasible 比例 | 机制诊断 |
| adaptation_wall_s / train_wall_s | 适配/训练墙钟 | Q3 成本 |
| peak_memory_mb | 进程峰值 | 资源 |

### 5.2 聚合与检验

- run → (task, budget, arm)：opt_seed × meta_seed 的可行率均值（10×3=30 个 run 的均值）作为该任务值；best_feasible_value 只对非 null run 取均值，并报告 null 计数；若某任务全部 null，则该任务该端点 null。
- 主比较：CON（S3-BO-FOMAML-CON）− OBJ（S3-BO-FOMAML-OBJ），20 个 meta_test 任务逐任务配对；Wilcoxon signed-rank（exact，双侧）；Holm 校正 2 个检验（B=64/128）；bootstrap 10,000 次（seed=20261107）任务级均值差的 95% CI（percentile）。
- 次级 C2：best_feasible_value（B=128，CON−OBJ；负值表示 CON 更优）的配对差均值/中位数、Wilcoxon、CI；同时报告 CON 在可行率提升时目标值变差的幅度（权衡曲线）。
- ANIL（Q3）：ANIL−CON 的 feasible_hit_rate 配对差、均值、CI、成本比（train/adapt wall、峰值内存）；预设非劣边际 −0.02；只作描述性结论，不做“ANIL 更优”的显著性宣称。
- RANDOM/DE：描述性表格（可行率、best value、首次可行）；不做主推断。
- 负控制：10 个 label-shuffle 任务上报告 feasible_hit_rate/best value，确认不优于随机臂；不进入主/次检验。
- 效应阈值与决策见 §1.3；所有 p 值、CI、效应量、null 计数、有效任务数写入 aggregate。

### 5.3 图表合同（9 个键；映射 Issue #7 §4 七类图）

| 图键 | 内容 | Issue #7 七类映射 | 数据源 |
|---|---|---|---|
| fig1_training_loss_curves | FOMAML/ANIL 元训练与 query loss 曲线 | ①训练诊断 | model_manifest + train logs |
| fig2_adaptation_rmse_vs_k | 适应后代理 RMSE vs K-shot（K=0,1,3,5 描述性；主网格 K=5） | ②K-shot 误差 | SMOKE/附加诊断段（不得用 holdout 调参） |
| fig3_feasible_hit_rate_by_arm | 五臂 × B={64,128} 可行率（任务级均值 ± bootstrap CI） | ③可行率对比 | run_records |
| fig4_best_feasible_and_first_feasible | 同预算 best_feasible_value 与 first_feasible_eval_index | ④同预算最优/首次可行 | run_records |
| fig5_performance_cost_fomaml_vs_anil | FOMAML vs ANIL：可行率 vs 训练/适配成本、峰值内存 | ⑤性能-成本 | run_summary |
| fig6_conflict_diagnostics | conflict_ratio/margin/objective_regret 分布与任务级可行率关系 | ⑥任务族/约束诊断 | frozen package + run_records |
| fig7_ood_diagnostics | meta_test vs meta_test_ood 可行率/最优值对比 | ⑥OOD 诊断 | run_records（OOD 段） |
| fig8_determinism_and_negative_controls | 600-run 确定性重跑一致性 + label-shuffle 负控制 | ⑥诊断/负控制 | determinism + negative_controls |
| fig9_tradeoff_curve | 可行率提升 vs best value 变差（CON−OBJ 任务散点） | ⑥诊断 | run_records |

- ⑦只读 VSPAERO 门禁：`NOT_APPLICABLE_S3_ZERO_PHYSICS`（S3 无任何真实求解；不得伪画）；③/④ 若某臂全 null 则图注 NOT_RUN/部分缺失，禁止伪造数据点。
- 所有图：中文标题/轴标签、`evidence_scope`（meta_test=CONFIRMATORY_SYNTHETIC；meta_validation=DEVELOPMENT_VALIDATION_ONLY）、数据源与 sha 脚注、CSV 数据支持；`figures_status.json` 记录每图 RENDERED/NOT_RUN 及原因。

### 5.4 分析器硬校验（fail-closed）

- 逐文件 sha（run_config/run_summary/run_records/model_manifest/data_manifest）与 summary 声明一致；记录数、FAILED 数、预算等式、physical=0、solver_processes_started=0。
- prereg 绑定：prereg_id/digest、code_sha、frozen_package.package_sha256/task_ids_sha256、models sha 全部一致；否则 S3_ANALYSIS_PREREG_MISMATCH。
- 数据边界：holdout 使用阶段与 split 白名单；negative_controls 独立；OOD 只作描述；任何越界 → fail-closed。
- 统计：端点定义、Holm 族、bootstrap seed/次数、Wilcoxon exact 与 prereg 完全一致；null 处理规则一致；若 analysis 与 prereg 不一致 → fail-closed。
- 输出：aggregate.json + s3_endpoint_tables.csv + s3_per_task_aggregates.csv + s3_holm_family.csv + s3_null_disclosure.csv + s3_negative_controls.csv + figures_status.json + 9 PNG + 9 support CSV。

## 6. 预注册（prereg）合同

- 生成器：`s3_prereg.py`；schema `p4ra-s3-prereg-v1`；prereg_id 前缀 `p4ra-s3-prereg-`。
- 冻结件路径：`research/concorde_metaopt/evidence/s3/preregistration/s3_preregistration.json`（canonical JSON + LF；raw sha256 写入 closeout/回执）。
- 必需段：schema_version/prereg_id/prereg_digest/created_utc/stage/family_contract（family_id/version/formula_version/package_sha256/task_ids_sha256/split_counts/params_digest/reference_cert_digests）/frozen_package（package_path/package_sha256/task_ids_sha256/family_package_version）/data_boundary/arms（五臂精确配置）/training（模型 sha、outer_steps、episode bank sha）/evaluation_grid（tasks/budgets/opt_seeds/meta_seeds/K/run_count）/endpoints（主/次/描述性定义）/statistical_plan（Wilcoxon exact/Holm 2/bootstrap 10000 seed 20261107/效应阈值 +0.02/决策枚举）/negative_controls/determinism（600-run 子集，3 次）/resource_limits（per_run_wall_s=60、peak_memory_mb=8192、total_wall_s=7200）/stopping_rules/code_sha/figures/scope_notes/analysis_plan_digest。
- verify（fail-closed）：占位字符串/空段拒绝；prereg_digest 复算；code_sha 算法固定（见下）；family package sha/task ids sha/split counts；arms 精确配置与 run_config 一致；模型 sha；统计参数固定值；资源限制固定值；负控制 10 任务；SMOKE/FORMAL 模式语义；任何不符 → S3_PREREG_* 错误码，拒绝写/读。
- code_sha：对 5 个文件按字典序哈希（`m5_arms.py`, `maml.py`, `s3_prereg.py`, `s3_runner.py`, `task_family.py`）——排序后的相对路径 + 文件字节 sha256，join 后整体 sha256；算法与 S2 的“排序路径+sha”约定一致；旧 S2 code_sha 算法不受影响。
- prereg 必须在正式 run 前由 Lead 生成并提交，A5 独立核验（不依赖 Lead 脚本）；冻结后任何代码改动都需要新 prereg 版本 + A5 复核，不得在旧 prereg 下跑。

## 7. 代码改动范围与写域

| 文件 | 改动 | 负责人 |
|---|---|---|
| `research/concorde_metaopt/meta_learning/task_family.py` | 新增 F-QE-conflict-v1 族：常量/配置校验/采样/参考解/真值/包生成；旧族路径不改 | A1 |
| `research/concorde_metaopt/meta_learning/maml.py` | 新增 ANIL 适配模式：`adaptation_mode="anil"` 或 `MAMLConfig.head_only=True`；保持 first_order/full 旧路径逐位不变；ANIL 梯度测试 | A1 |
| `research/concorde_metaopt/meta_learning/m5_arms.py`（或新增 `s3_arms.py`，以 A5 意见为准） | S3 五臂、联合评分函数、预算/公平断言、克隆检测 | A1 |
| `research/concorde_metaopt/meta_learning/s3_runner.py`（新） | SMOKE/FORMAL run、训练模型加载、run_config/summary/record、确定性、计时/资源 | A1 |
| `research/concorde_metaopt/meta_learning/s3_prereg.py`（新） | prereg build/verify、schema 单源、code_sha、family/model 绑定 | A1 |
| `research/concorde_metaopt/meta_learning/s3_analysis.py`（新） | 严格校验、端点/统计/aggregate/CSV、负控制、null 披露；可复用 s1_analysis 的 wilcoxon_signed_rank/bootstrap_mean_ci/holm_adjust 纯函数 | A6 |
| `research/concorde_metaopt/meta_learning/s3_figures.py`（新） | 9 图 + support CSV + figures_status | A6 |
| `research/concorde_metaopt/tests/test_s3_*.py` | 单元/负控/公平/端到端测试 | A1+A6 |
| `docs/planning/p4_route_a_s3_execution_plan_20261107.md` | 本计划 | Lead |
| `docs/reviews/p4_route_a_s3_requirement_matrix.md` | A4 需求矩阵 | A4 |
| `docs/reviews/p4_route_a_s3_formal_run_report_20261107.md` | 正式 run 中文报告（repo-ready） | A2/Lead |
| `research/concorde_metaopt/evidence/s3/...` | 校准包/模型/prereg/正式 run 证据包/复核归档 | Lead 打包 |

写域边界：A1 只写 task_family.py + maml.py + m5_arms.py（或 s3_arms.py）+ s3_runner.py + s3_prereg.py + 对应测试；A6 只写 s3_analysis.py + s3_figures.py + 对应测试；Lead 只写计划/文档/证据包/集成提交；A2 只在授权 out_dir 写 run 产物与报告草稿；A3/A4/A5 只写外部记忆根，不改仓库。任何 teammate 不得执行改变工作树的 git 命令（checkout/reset/stash/clean/commit），只读 git status/log 允许；Lead 是唯一提交者。

## 8. 测试与质量门（M1/M2 必须全绿）

1. 基线：`D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m unittest discover -s research/concorde_metaopt/tests -t .` 在 clean worktree 上 ≥1,174 tests OK(skipped=1)，0 fail。
2. 新族测试（≥12）：参考解证书 20/20 抽样通过；冲突断言（c 不可行、u* 可行、g2 不活跃、margin）；确定性（同 seed 同包/同 task_id）；非法参数拒绝；旧族逐位回归（旧 v2/v3 任务 id/params/fingerprint 不变）。
3. ANIL 测试（≥6）：head-only 内循环只更新输出层；body 参数在适配后不变；ANIL 对 FOMAML 的等价性极限（head_only 且 body=0 层时）；有限差分梯度（小网络，FD eps 相对 1e-6，阈值 1e-6）；旧 FULL_MAML/FOMAML 测试全绿；确定性。
4. 臂/预算测试（≥12）：`billable_evals==B`；support=5/initial=3/BO=B−8；联合评分公式数值测试；预测可行优先/惩罚单调性；候选池排除 support；OBJ/CON 同候选池；克隆检测；BO 引擎种子不含 arm；RANDOM/DE 复用共享初始点。
5. runner 测试（≥10）：SMOKE 端到端；记录字段/计数；预算不符 fail-closed；物理调用守卫（0）；holdout 读取守卫；确定性 core digest；资源限制触发；模型 sha 校验。
6. prereg 测试（≥8）：build/verify 往返；占位拒绝；code_sha 算法固定向量；family/model 绑定篡改拒绝；统计参数篡改拒绝；SMOKE/FORMAL 语义。
7. analysis/figures 测试（≥12）：端点独立重算；Wilcoxon/Holm/bootstrap 金标；null 处理；负控制分离；OOD 描述性；9 图键/中文标签/evidence_scope/NOT_RUN；e2e（SMOKE run → analysis → aggregate/CSV）。
8. A5 独立复跑与代码审阅；A3 隔离审计；A4 矩阵。

## 9. 交付物清单

1. 计划 v1.x（本文件）；S3 阶段开启记录（EXT）。
2. 代码：task_family.py（新族）、maml.py（ANIL）、m5_arms.py/s3_arms.py（五臂/评分）、s3_runner.py、s3_prereg.py、s3_analysis.py、s3_figures.py + 测试。
3. 校准报告 + 家族冻结包 + 模型产物 + prereg JSON + 冻结记录。
4. 正式 run 证据包（run_config/summary/records/model_manifest/data_manifest/determinism/analysis/9 图/9 support CSV/负控制）+ 中文报告 + A2 运行报告。
5. A5 复核（代码、prereg、结果、packaging）、A3 隔离审计（代码、run、证据包）、A4 需求矩阵与回执草稿。
6. Issue #7 S3 中文回执（单条，仅 Lead 发布）；closeout 记录（EXT）。
7. 不合并 main、不新开 PR；阶段验收 NOT_ISSUED（仅负责人可签发）。

## 10. 角色与任务板

| 角色 | 职责 | 写域 |
|---|---|---|
| Lead | 计划/集成/唯一提交与 GitHub 发布/prereg 冻结与授权/最终裁定 | docs/evidence/集成提交/EXT |
| A1 code-dev | 新族+ANIL+臂+runner+prereg+测试 | 代码文件（§7） |
| A6 code-dev | analysis/figures/测试 | s3_analysis.py/s3_figures.py/测试 |
| A2 run-opt | 正式 run 执行（仅授权后）+运行报告 | 授权 out_dir + EXT |
| A3 repo-guard | 隔离/旧件/哈希/边界审计 | EXT |
| A4 issue-liaison | 需求矩阵/回执草稿/事实核对 | EXT |
| A5 code-reviewer | M0/代码/prereg/结果/packaging 独立复核 | EXT |

任务板：S3 卡片在 M0 后创建（A5 M0、A1 代码、A6 分析、A4 矩阵、A3 基线审计；后续 A5 代码/结果、A2 run、A3 run 审计、A4 回执）。卡描述含对象 commit/写域/交付路径/verdict 枚举；Lead 维护 blocked_by 链。

## 11. 阶段门验收清单

- M0：A5 对本计划 APPROVE_FOR_S3_CODE（0 blocker；所有 major 处置或明确不阻塞）；阶段开启记录存在。
- M1：代码/测试/校准报告全绿；A5 代码审阅 APPROVE；A3 提交隔离与旧件审计 PASS。
- M2：新族冻结包 + 模型 + prereg 提交；A5 独立核验 APPROVE_FOR_S3_RUN；FD/梯度门 PASS（ANIL 梯度、确定性）；SMOKE e2e PASS。
- M3：Lead 授权文件（task/worktree/out_dir/预算/停止规则）签发；A2 在 clean worktree 执行。
- M4：6,000 runs（或 3,000，若 §4.2 降级）完成；预算/物理/数据边界/确定性核验；A5 独立重算端点与统计，APPROVE_FOR_S3_RECEIPT。
- M5：证据包 commit + A5 packaging APPROVE_FOR_S3_RECEIPT_PACKAGE + A3 证据包 PASS。
- M6：Issue #7 S3 回执发布（15 项必含：一句话结论、授权链、prereg、预算/physical、运行事实/确定性、主次端点、负控/图、复核链、边界、门禁、证据清单、null/INCONCLUSIVE 披露、旧件未动、main 未动、下一步建议）。
- 任何门禁失败 → 停止、修复、重审；不得跳门。

## 12. 风险清单与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 冲突族过难（随机可行率≈0）→ 五臂全 0 可行，端点无区分 | Q1 无信息 | M1 校准（meta_validation）强制接受条件；过难则调 r 分布；仍不行则如实披露并 INCONCLUSIVE |
| 冲突族过易（大量可行）→ 约束感知无差异 | Q1 无信息 | 同上；记录 support 池可行比例 |
| 3 个初始点对 B 总预算影响小 → 效应被稀释 | 功效低 | 预注册效应阈值 +0.02；同时报告 initial_feasible_rate 作为机制端点；允许 NO_EVIDENCE |
| ANIL 实现错误（body 被更新） | Q3 无效 | 参数不变断言 + FD 梯度测试；A5 代码审阅 |
| 联合评分利用 g2 噪声 | 结果不稳 | 只用 support 标签归一化；惩罚权重固定；报告 g_scale；负控 |
| 运行时间超预算 | 无法完成 6,000 runs | M2 计时试点；>90 min 时预注册前降 opt_seed 至 5；总硬截止 7,200 s |
| 确定性重跑成本 | 时间 | 只做 600-run 分层子集并明确披露 |
| 旧件被误改/提交范围越界 | 治理失败 | A3 审计；只新增文件；Lead 复核 git diff |
| teammate 崩溃/产出不完整 | 进度 | Lead 接管最小实现并保留角色披露；任务卡可重派 |

## 13. 时间与里程碑（目标，不构成承诺）

| 里程碑 | 目标 | 产出 |
|---|---|---|
| M0 | 计划提交后 1 轮 A5 复审 | M0 verdict |
| M1 | 2-3 个工作日 | 代码+校准+测试 |
| M2 | M1 后 1 天 | 冻结包+prereg+A5 核验 |
| M3/M4 | M2 后 1 天 | 授权+正式 run |
| M5/M6 | run 后 1-2 天 | 证据包+回执 |

## 14. 变更控制与版本记录

- 本计划任何修改都必须 commit + push 并重新经 A5 限定 diff 复审（M0R 系列）；已批准版本优先于早期版本与 Lead 设计裁定记录。
- 正式 run 后不得修改 prereg、模型、统计计划；修正只能以“分析勘误 + 新分析版本”披露，不得覆盖原始产物。
- 本文件 v1.0 为初始候选；A5 M0 意见逐条处置后升 v1.x。

## 15. 附：与上游合同的对齐表

| Issue #7 要求 | 本计划落点 |
|---|---|
| S3 条件开启（S1/S2 验收后） | §0.1（回执 6684142041/6693991661） |
| 约束感知初始化（g≤0 多约束代理、标签尺度、可行率劣势） | §3.2 联合评分、§2.1 冲突族、§1.2 Q1 |
| 对比纯目标排序/目标+约束评分 | S3-BO-FOMAML-OBJ vs S3-BO-FOMAML-CON |
| 任务内约束归一化、预留随机/多样性比例（Wave B） | §1.2 Q5 条件实验（不默认） |
| ANIL 低成本消融 | S3-BO-ANIL-CON + Q3 |
| 不标定不确定度则 uncertainty=null | §3.2 |
| 新独立冲突族+解析参考解可审计 | §2.1/§2.4 |
| 先校准冻结、再新盲测集预注册推断 | §2.3/§2.5/§6 |
| 禁止学习 BO 采集策略/路线B | §0.2 |
| physical=0 硬隔离 | §0.2/§2.4/§5.4 |
| 旧 PR 不合并 main、仅 Lead 发布 | §0.2/§9 |
| 中文交付与图 | §5.3/§9 |
| 结论允许无改进 | §1.3/§12 |
