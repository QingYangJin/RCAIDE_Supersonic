# P4 路线A S3 执行计划：约束感知初始化与低成本适应消融

- 文档路径：`docs/planning/p4_route_a_s3_execution_plan_20261107.md`
-版本：v1.3a（2026-11-07T00:45Z 执行层并行验收与预算口径重裁 R-S3-05A、R-S3-05B（书面接受保守外推 5,509.562 s）+ FORMAL 模型/FD/K 语义 R-S3-06 + R-S3-07 FORMAL train=0 与 gate/model_manifest 绑定；v1.3 对象 36e5820 被 A5 M0R3 判 CHANGES_REQUESTED；v1.2b 为 R-S3-03；v1.2 见 f81f69b，v1.0 见 7bef3cf）
-状态：M0R2 已 APPROVE_FOR_S3_CODE（对象 f81f69b）；M0R3 对 v1.3（36e5820）判 CHANGES_REQUESTED（2 blocker/4 major/2 minor/1 info：execution_report schema 三方冲突、W=8 微基准不满足 1/8±30% 验收、CPU 预算无硬上限与批准、缺 M2 W=8 必过门/线程固定/fallback、6,900 与 3,780 网格未单值化、M0R3 状态互斥）；本 v1.3a 按 R-S3-05A（并行验收改吞吐外推、sum_run_wall 硬上限 28,000 s、M2 W=8 稳态试点门、fallback、确定性 60-run 子集、单值 3,780 网格）与 R-S3-06（FORMAL 加载冻结模型不重训、FD 门每模型 32 坐标、FORMAL K=5）修订；待 A5 M0R3R 以限定 diff 批准前 M1 不得启动。
- 作者/唯一集成者：Lead（teammate 不得提交、不得写 GitHub）
- 上游合同：Issue #7（D-P4-003，body 5,150 字符）；`docs/planning/p4_route_a_stage_improvement_plan_20261105.md` 的 S3 条；S1 回执 commentId 6684142041；S2 回执 commentId 6693991661；A5 S3-M0 审阅（CHANGES_REQUESTED，S3-M0-01..16）；A5 S3-M0R 审阅（CHANGES_REQUESTED，S3-M0R-01..09，对象 dd2bab2）；A4 矩阵 v1.1（NEW-01..09）
- 基线提交：`8da84fc105755825561829d4fb371f2baea57438`（research/p4-route-a-s3 的父提交，S2 docs closeout）；v1.0 计划提交 `7bef3cf8218df2328d997dbb12e4dd626704005f`；v1.1 提交 `dd2bab2`（父 7bef3cf）；v1.2 提交 `f81f69b0cbf27a26e3e17be34844df3a1147a297`（随附 `research/concorde_metaopt/evidence/s3/hash_vectors.json`，12,472 B sha256 `bde487fb6ed49768ca76e328a31c0efab77d2bd39d41c0ac99def4bb8e876203`）；v1.2a 为文档状态勘误提交
- 工作树：`<repo-s3>`（S3 专用 worktree，绝对路径不入库），分支 `research/p4-route-a-s3`
- 证据根（仓库内）：`research/concorde_metaopt/evidence/s3/`
- 外部记忆根（不得入库）：`<EXT>/p4-route-a/`（`<EXT>` 为用户级 RCAIDE_Supersonic_agent_state 目录）

**v1.1 修订摘要（相对 v1.0）**

1. 家族构造由 12D 全维椭球改为**线性半空间 + 盒**的多面体冲突族（A5 S3-M0-01 blocker；A4 DEV-07；Lead 数值探针与 A5 建议一致）：目标无约束最优点 c 严格不可行，参考解 u_star 有闭式 KKT 证书；可行性由校准实测控制，不再依赖体积近似。
2. 校准候选、接受条件、重试规则与独立 4096 点估计写入 §2.5；默认候选 δ1 ∈ {0.20, 0.22, 0.25}，m2 ~ U(0.10, 0.15)。
3. 端点合同对齐 Issue #7 §4：新增 gap_to_reference、正式诊断端点 RMSE/MAE、best/first 的角色与配对检验（A5 S3-M0-02；A4 DEV-02/03/04）。
4. 数据边界改为 phase-scoped holdout 访问合同，消除“正式评估 split={meta_test}”与“训练 split⊆{train,val}”冲突（A5 S3-M0-03）；参考解封存件与运行期评估器分离。
5. 新增 OOD 正式运行网格与 OOD 偏移定义（A5 S3-M0-04；fig7 有数据）。
6. code_sha 固定覆盖 7 个实现文件（§6.1 逐文件枚举；含 s3_analysis.py/s3_figures.py），禁止新增 s3_arms.py；定义 analysis_plan_digest（A5 S3-M0-05；A4 DEV 允许的开放选项删除）。
7. 训练 episode bank 与 ANIL 参数分区、优化器、seed 公式、digest 全部写死（A5 S3-M0-06）。
8. 新增哈希与 canonicalization 子节，覆盖 package/task_ids/params/reference/analysis_plan/record/history/prereg 与 task_fingerprint，并给出固定测试向量；向量文件 `research/concorde_metaopt/evidence/s3/hash_vectors.json` 随计划提交（A5 S3-M0-07/15、A5-S3M0R-02）。
9. 新增 fd_or_gradient_gate 合同（目标模型、坐标、eps、tol、产物、错误码、时点、负控）（A5 S3-M0-08）。
10. 新增 fig10_vspaero_gate_status（Issue #7 图⑦），只读引用 D-12D-005，不伪造数据（A5 S3-M0-09）。
11. 固定四 BO 臂随机流与包装函数：引擎 seed 不含 arm、候选池共享、初始点 3 点唯一差异、LEGACY_BO_ARM 合同化（A5 S3-M0-10）。
12. Wilcoxon 改为 tie-aware 精确符号翻转枚举检验，零差丢弃并报告 n_zero，附敏感性分析（A5 S3-M0-11）。
13. 确定性子集与 opt_seed 降级同步、负控制网格理由、fig2 K-sweep 诊断网格、负控制置换 seed 全部写死（A5 S3-M0-12/13/14/16）。
14. 处置 A4 DEV-01..09：R-S3-01 授权链裁决、降网格 R-S3-02 书面审批、多样性进入 Wave A、Meta-SGD 显式排除、总体结论映射规则、头标措辞一致（§16）。

**v1.2 修订摘要（相对 v1.1）**

1. C1/C2 的 comparator 由 RANDOM 回归修正为 `S3-BO-FOMAML-OBJ`（与 §1.3 H0 一致；A5-S3M0R-01 blocker）；RANDOM/DE 仅描述性，禁止进入推断（§5.2、fig3/fig4）。
2. 提交 `research/concorde_metaopt/evidence/s3/hash_vectors.json`（11 个固定向量，含精确中间串与期望 sha256），并在 §6.1 逐项定义 7 文件 code_sha、analysis_code_sha、task_ids_sha256、task_fingerprint、analysis_plan_digest、package_sha256、prereg/record/episode digest 与原始字节摘要（A5-S3M0R-02/03；A4 NEW-01/07/09）。
3. R-S3-02 降网格算术更正为 3,780 runs/362,880 evals（负控/OOD 保持 300/28,800，确定性 180/17,280；A5-S3M0R-04）。
4. phase-scoped 边界改写：TRAIN/DEV 禁读 holdout truth；EVAL 允许读被测 task 的 support 标签做 K=5 适配（`support_truth_read` 记录）；query truth 仅端点计算读取；每 task 一次授权**评估 campaign**（A5-S3M0R-05）。
5. RANDOM 臂统一执行多样性规则（仅在自己的共享候选序列内取点），删除“RANDOM 豁免”（A5-S3M0R-06；A4 NEW-05）。
6. 决策枚举改为互斥穷尽判定表 + 总体唯一优先级，附 3×3 组合单测（A5-S3M0R-07；A4 NEW-06）。
7. 哈希规则中 `radius_base` 改为 `delta1_base`；BO trace 一致性合同改为引擎四元组 + 初始观测前抽样序列（A5-S3M0R-08；A4 NEW-04/NEW-08）。
8. episode 消耗披露：唯一 4,800、模型-episode 9,600（3 FOMAML + 3 ANIL 各 1,600），计入 auxiliary_compute（A5-S3M0R-09）。
9. 门禁链新增 M0R2（v1.2 限定 diff：计划 + hash_vectors.json）；新增 §18/§19 逐项处置表。

## 0. 阶段前提、授权口径与硬边界

### 0.1 阶段前提（S3 条件开启）与授权链裁决 R-S3-01

Issue #7 §2/§4 规定：S3（约束感知初始化与方法效率消融）在 S1/S2 验收后条件开启；Leader 负责 S0→S3 阶段批准与唯一 GitHub 发布；每一阶段需 A5 APPROVE 方可放行下阶段正式实验。本阶段开启依据：

| 条件 | 证据 | 状态 |
|---|---|---|
| S1 正式 run 已执行并经 A5 结果复核、A3 审计、Issue #7 回执 | commentId 6684142041 | SATISFIED |
| S2 正式 run 已执行并经 A5 结果复核与证据包复核、A3 隔离审计、Issue #7 回执 | commentId 6693991661；包 rev3 12940c5；S2_CLOSEOUT_20261107.json | SATISFIED |
| S1/S2 均 physical_call_count=0、无真实求解 | 两阶段回执与 A3 审计 | SATISFIED |
| S3 属 Issue #7 已批准范围（算法代码 + 全合成解析任务离线训练/对照） | Issue #7 当前批准段 | YES |
| S3 是否需要新的负责人预算授权 | 不需要（零真实求解；不新增 A/B/C/D 类 VSPAERO/RCAIDE/SU2 调用） | NOT_REQUIRED |
| S3 阶段批准（Leader 依据 Issue #7 §4 阶段批准职责签发） | R-S3-01（本计划 §0.1A；EXT 记录） | SATISFIED |

**§0.1A 授权链裁决 R-S3-01（回应 A4 DEV-01）**

- A4 指出：S2 closeout 记录 next.s3=NOT_APPROVED_REQUIRES_OWNER_WRITTEN_AUTHORIZATION，且 S1/S2 回执本身不构成 S3 授权，故 S3 开启前需书面处置。
- 裁决：该 closeout 字段是上一阶段结束时的保守备注，不构成对 Issue #7 的修订。Issue #7 原文明确：(a) §0「当前批准：代码、单元/梯度/公平性测试、全合成解析任务的训练和正式离线对照，physical_call_count=0 硬隔离」；(b) §2「S3｜约束感知初始化与方法效率消融（S1/S2验收后条件开启）」；(c) §4「Leader 负责S0→S3阶段批准与唯一GitHub发布」。S3 是 Issue #7 已批准的工作包，开启条件是 S1/S2 完成并经 A5 复核，而不是新的负责人预算授权；只有真实求解、真实航空优化、路线B、P5/P6 需要另行授权。
- 因此：Lead 以 Issue #7 §4 的阶段批准职责签发 S3 阶段开启（R-S3-01），并显式取代 S2 closeout 中 REQUIRES_OWNER_WRITTEN_AUTHORIZATION 对 S3 的表述；S4 仍按 Issue #7 §2 需要另立计划与授权。
- 记录：`<EXT>/p4-route-a/lead/R-S3-01_stage_authorization.md` 与 `S3_STAGE_OPENING_20261107.json`（含本裁决、Issue #7 原文引用、S1/S2 复核链、时间戳）。

### 0.2 硬边界（任一违反即 fail-closed）

1. `physical_call_count = 0`；不启动 VSPAERO/RCAIDE/SU2/WaveDrag/CFD/Mission/Gmsh 等任何真实求解器或子进程；评估器只能是本仓库内的解析合成函数。
2. 不访问网络资源做训练/评估；不下载数据；不调用外部 API。
3. 不合并 main；不新开 PR；旧 PR #3/#6 保持 open；仅 Lead 写 GitHub。
4. 旧冻结件只读：S0-2..S0-7、S1、S2、M2/M5/M6 的一切文件不得修改；S3 只新增文件。
5. 唯一写入域：`<repo-s3>` 的 S3 新增/修改文件 + 外部记忆根。不得写主库 `<repo-main>`、`<repo-s2>` 或其他 worktree。
6. 不学习 BO 采集策略、不做路线B；不实现 P5/P6；不实现真实飞机 BO/DE；不做真实航空元训练。
7. 不使用 S1/S2 任务族或任何已见任务充当 S3 盲测集；S3 的 meta_test/meta_test_ood/negative_control 必须来自全新族 F-QE-conflict-v1（formula_version=polyhedral-v1），且在任何调参/选型前未生成标签（见 §2.3）。
8. 不伪造数据：缺失即 NOT_RUN/None，不插补、不筛选有利任务。

### 0.3 门禁链（每步 A5 verdict 才放行下一步）

| 门 | 产出 | 放行条件 |
|---|---|---|
| M0 设计门 | 本计划 v1.0（7bef3cf）+ S3 阶段开启记录 | A5 实际结论：CHANGES_REQUESTED（S3-M0-01..16） |
| M0R 修订门 | v1.1 限定 diff（相对 7bef3cf，对象 dd2bab2） | A5 实际结论：CHANGES_REQUESTED（S3-M0R-01..09） |
| M0R2 复审门 | v1.2 限定 diff（相对 dd2bab2：计划 + hash_vectors.json，对象 f81f69b） | A5 实际结论：APPROVE_FOR_S3_CODE（task-256 rev63，0B/0M/3m/1obs） |
| M0R3 执行层修订门 | v1.3 限定 diff（相对 f81f69b，对象 36e5820） | A5 实际：CHANGES_REQUESTED（2B/4M/2m/1i；B01 execution_report schema 冲突、B02 W=8 验收不达标） |
| M0R3R 执行层重裁复审门 | v1.3a 限定 diff（相对 f81f69b，对象=本提交） | A5: APPROVE_FOR_S3_CODE_AMENDED（R-S3-05A + R-S3-06） |
| M1 代码/校准门 | 家族实现+校准报告+ANIL+臂+runner+prereg 生成器+测试 | A5: APPROVE_FOR_S3_FORMAL（代码审阅） |
| M2 预注册门 | 新族冻结包、prereg JSON、FD/梯度门、冻结记录 | A5: APPROVE_FOR_S3_RUN |
| M3 正式 run 授权 | Lead 书面授权（task/worktree/out_dir/预算/停止规则） | Lead 签发 |
| M4 结果门 | run 证据、A2 报告、A5 独立复核 | A5: APPROVE_FOR_S3_RECEIPT |
| M5 证据包门 | 证据包 commit + A5 packaging + A3 隔离审计 | A5: APPROVE_FOR_S3_RECEIPT_PACKAGE；A3 PASS |
| M6 发布 | Issue #7 S3 中文回执（单条） | Lead 发布；阶段验收 NOT_ISSUED |
| S4 | 仅航空数据合同（离线），需另立计划与 A5 门 | 不在本计划范围 |

## 1. 目标、可证伪问题与决策规则

### 1.1 背景（为什么 S3 只能问这些问题）

- M5 发现：MAML 初始化臂的 `feasible_hit_rate` 显著低于普通 BO（配对差 −0.01526/−0.01228，Holm 显著）；其结构原因是旧 F-QE-feasible-v2/v3 的约束中心与目标中心相同，可行率问题被弱化/转移。
- S1 发现：K-shot→BO 初始化闭环在目标值主端点 NO_EVIDENCE；可行率不是 S1 主端点。
- S2 发现：FULL_MAML 相对 FOMAML SUPPORTED_HARM（k5 相对 −3.394%，19/20 任务更差），因此 S3 不默认升级二阶，适配核心保留 FOMAML，并用 ANIL 做低成本消融。

S3 的唯一干预目标是：**在目标最优点严格不可行的多面体冲突族上，检验“约束感知的初始点选择”能否提高等预算可行率，并量化其目标值代价与参考差距**。

### 1.2 可证伪问题

| 编号 | 问题 | 类型 |
|---|---|---|
| Q1（主） | 在 F-QE-conflict-v1 上，K=5 支持集 + 约束感知联合打分的 3 个新初始点，相对仅目标打分的同源初始点，能否在 B∈{64,128} 等预算下提高 `feasible_hit_rate`？ | 确证性（配对任务级检验，Holm 2 检验） |
| Q2（次） | Q1 的可行率收益是否以 `best_feasible_value`/`gap_to_reference` 变差为代价？`first_feasible_eval_index` 是否提前？ | 次级/描述性 |
| Q3 | ANIL（仅适应输出层）在可行率上是否相对 FOMAML 非劣（边际 −0.02），且适应/训练成本更低？ | 描述性/成本-性能 |
| Q4 | 新冲突族是否出现“全不可行/全可行”退化？若出现，是否按预注册规则披露 INCONCLUSIVE 而不改任务？ | 诊断门 |
| Q5（条件） | 约束归一化方式、初始点多样性配额是否进一步改善？（Wave B，仅当 Wave A 结果与 A5 同意另立实验卡时执行；注意初始点多样性已在 Wave A 以预注册规则覆盖，见 §3.2） | 探索性，不默认 |

### 1.3 假设与决策规则（预注册，M2 冻结）

- H0：在相同预算、相同支持集、相同 BO 引擎下，联合打分与目标打分的任务级平均 `feasible_hit_rate` 无差异。
- 主检验族 C1 = {`feasible_hit_rate`，B=64；`feasible_hit_rate`，B=128}，共 2 个检验，Holm 校正，双侧 tie-aware 精确符号翻转检验（§5.2），alpha=0.05；效应阈值 = 绝对 +0.02（2 个百分点）。
- 决策枚举（每个预算层分别判定；**互斥穷尽、优先级从上到下**；与 §5.2 完全一致；A5-S3M0R-07 处置）：
  1. `INCONCLUSIVE`：有效配对任务 n_eff<15，或检验不可计算；
  2. `SUPPORTED_BENEFIT`：Holm 校正后 p<0.05、效应方向为获益且 |效应| ≥ 阈值（0.02）；
  3. `SUPPORTED_HARM`：Holm p<0.05、方向为损害且 |效应| ≥ 0.02；
  4. `NEGLIGIBLE_SIGNIFICANT`：Holm p<0.05 但 |效应| < 0.02；
  5. `DIRECTION_INCONSISTENT`：p≥0.05、点估计方向为损害（差<0）且 |效应| ≥ 0.02；
  6. `NULL`：其余（p≥0.05 且非 `DIRECTION_INCONSISTENT`）。
- 总体 S3 结论映射（A5-S3M0R-07 + A4 DEV-08 处置；预注册、防选择性汇报；两层 = C1@B64 与 C1@B128 的可行命中率层）：
  1. 任一层 `INCONCLUSIVE` → 总体 `INCONCLUSIVE`；
  2. 任一层 `SUPPORTED_HARM` → 总体 `HARM`；
  3. 任一层 `DIRECTION_INCONSISTENT` → 总体 `DIRECTION_INCONSISTENT`；
  4. 两层均 `SUPPORTED_BENEFIT` → 总体 `BENEFIT`；
  5. 一层 `SUPPORTED_BENEFIT`、另一层为 `NULL`/`NEGLIGIBLE_SIGNIFICANT` → 总体 `NO_EVIDENCE`；
  6. 其余 → 总体 `NO_EVIDENCE`。
- 判定必须由固定查表函数产生（不允许自由文本结论），并附 3×3 组合单测。
- 端点空值规则：`best_feasible_value`/`gap_to_reference` 在 run 内无可行点时 = null（不插补、不以惩罚值替代）；`feasible_hit_rate` 分母固定为 B，恒有定义；null 计数必须披露。
- 禁止：事后按任务筛选、按结果调半径/权重、只报告有利预算、把 INCONCLUSIVE 写成 benefit、把 Wave B 探索性结果写成确证性结论。


## 2. 数据边界与全新冲突任务族 F-QE-conflict-v1

### 2.1 族定义（数学合同，v1.1：线性多面体冲突族；formula_version=polyhedral-v1）

v1.0 的 12D 全维椭球构造经 A5 独立探针与 Lead 数值探针证明不可满足 §2.5 的可行率接受条件（12D 全维球在 box 内可行体积远低于 2%，且 g1 与 g2 叠加更低）；A5 S3-M0-01 要求改族构造。v1.1 采用线性半空间约束（A5 建议的“线性/盒约束”），使可行域为多面体、参考解有闭式 KKT 证书、可行率可由 δ1 直接控制且可数值校准。

- 族 id `F-QE-conflict-v1`；`formula_version = polyhedral-v1`；维度 12；设计框 [0.02, 0.98]^12。
- 任务参数（由 task seed 唯一派生）：`a_i = exp(sigma_i)`，`sigma_i ~ U(-0.5, 0.5)`；`c ~ U(0.30, 0.70)^12`（目标无约束最优中心，位于 box 内）；`b1, b2` 为 12 维标准高斯归一化单位向量（`b = g/||g||_2`）；`delta1_base` 由 §2.5 校准选定（候选 {0.20, 0.22, 0.25}）；`m2 ~ U(0.10, 0.15)`。
- 目标：`f(u; c, a) = sum_i a_i (u_i - c_i)^2`；无约束最优点为 c。
- 约束 1（线性半空间，目标点严格不可行）：`g1(u) = b1 · (u - c) + delta1 <= 0`；因为 `g1(c) = delta1 > 0`，c 不可行，c 到 g1 边界的欧氏距离为 `delta1`。
- 参考解（闭式 KKT）：`S = sum_i b1_i^2 / a_i`；`lambda = delta1 / S`；`u_star = c - lambda * (b1 / a)`（逐元素）；则 `g1(u_star) = 0` 精确成立、`kkt_residual = max_i | 2 a_i (u_star_i - c_i) + 2 lambda b1_i | = 0`（解析恒等，浮点实现应 <= 1e-12）。
- 参考目标与 regret：`f_star = f(u_star) = delta1^2 / S`（因 f(c)=0 且 `u_star - c = -lambda b1/a`）；`objective_regret = f(u_star) - f(c) = delta1^2 / S > 0`；`conflict_ratio = delta1`（c 到可行边界的距离）。
- 约束 2（第二线性半空间，在参考点不活跃）：`delta2 = - b2 · (u_star - c) - m2`；`g2(u) = b2 · (u - c) + delta2 <= 0`；于是 `g2(u_star) = -m2`（精确负值，`margin_m = m2`）；`g2` 切掉可行域的一个角，使“多约束”成立且参考点仍可行。
- 真值：`truth(u) = (f(u), g1(u), g2(u))`；feasible 当且仅当 `u in [0.02,0.98]^12` 且 `g1(u) <= 0` 且 `g2(u) <= 0`（比较容差 1e-12）。
- 参考证书断言（生成期逐一 fail-closed；任一失败则该 task seed 重采样，最多 50 次，记录 retry_count）：
  1. `u_star` 严格在 box 内（0.02 < u_star_i < 0.98）；
  2. `|g1(u_star)| <= 1e-12`；
  3. `kkt_residual <= 1e-12`；
  4. `|g2(u_star) + m2| <= 1e-12`；
  5. `m2 ∈ [0.10, 0.15]`；`objective_regret > 1e-6`；
  6. `g1(c) = delta1 > 0` 且 `g2(c) = delta2`（记录其符号，不要求 >0）；
  7. 128 点 support LHS 池中至少 1 个可行点：**仅在 meta_train/meta_validation 任务上**为该条件重采样 task seed（最多 10 次，记录 support_retry_count）；meta_test/meta_test_ood 任务一律不重采（盲测完整性优先），若出现 0 可行 support 点则记录 `degenerate_support=true`，在分析中披露并做敏感性报告。候选 δ1 下该重采规则预期触发率为 0（Lead 探针 0/200）。
- 参考解字段：`reference_kind = "POLYHEDRAL_KKT_CERTIFIED"`，包含 `u_star`、`f_star`、`g1_star`、`g2_star`、`lambda`、`S`、`kkt_residual`、`margin_m`、`conflict_ratio`、`objective_regret`、`delta1`、`delta2`、`retry_count`、`support_retry_count`。
- 局限性（必须写入报告与回执）：线性约束使 g1/g2 更易被 3 输出代理学习；本族检验的是“初始点选择”而非长期学习能力，故结论只针对该族与 K-shot 设置，不外推到非线性约束或真实飞机。

### 2.2 分片、OOD/负控制、任务 id 与冻结包

| split | 任务数 | 用途 | 是否允许调参 |
|---|---|---|---|
| meta_train | 60 | FOMAML/ANIL 元训练 | 是（仅训练超参，不动族参数） |
| meta_validation | 20 | 家族校准/代码调试/SMOKE | 是（校准后冻结） |
| meta_test | 20 | 正式确证性评估（C1/C2 主端点） | 否（冻结后只读一次） |
| meta_test_ood | 10 | OOD 描述性诊断（更强冲突偏移） | 否 |
| meta_test_negative_control | 10 | 标签打乱负控制 | 否 |

- 种子：`FAMILY_SEED = 20261107`（meta_train/meta_validation/negative control）；`HOLDOUT_SEED = 20261108`（meta_test/meta_test_ood 追加进 seed 派生，参照 v3 的 RESEEDED_SPLITS 机制）；每个 task 的 seed = `int.from_bytes(sha256(f"{split}|{family_id}|{formula_version}|{index}|{split_seed}").digest()[:8], "big") % (2**31)`。
- 任务 id：`p4ra-FQEC-v1-<sha1(family_id|formula_version|canonical(params)|seed) 前 16 hex>`；`task_fingerprint = sha256(canonical JSON({family_id, formula_version, task_id, seed, params}))[:16]`（唯一算法，见 §6.1；`params={a,c,b1,b2,delta1,delta2,m2}`，不含 w/r）。
- OOD 定义（A5 S3-M0-04 处置）：OOD 任务使用同一族公式，但 `delta1_ood = delta1_base + 0.05`（冲突更强），且在 b1 上叠加确定性偏移：`b1_ood = normalize(b1 + 0.30 * e_rand)`，其中 `e_rand` 为 12 维标准高斯单位向量、seed 由 `HOLDOUT_SEED|ood-direction|index` 派生；`m2` 与 b2 采样分布不变。参考证书断言与 §2.1 相同；OOD 仍为 `reference_kind=POLYHEDRAL_KKT_CERTIFIED`；`task_context.ood_flag = 1`，且该 flag 不进入代理输入特征（§3.2）。
- 负控制定义（A5 S3-M0-16 处置）：负控制任务沿用 meta_test 前 10 个任务的几何与 design points，仅对 query 标签做置换：`shuffle_seed = int.from_bytes(sha256(f"{FAMILY_SEED}|{task_id}|label-shuffle").digest()[:8], "big") % (2**31)`；置换仅作用于 query 的 3 维标签行（f/g1/g2 同时置换，保持行内一致），support 标签不变；`reference_kind=LABEL_SHUFFLED_NO_REFERENCE`，参考类端点对这些任务为 null 并披露。
- 冻结包路径：`research/concorde_metaopt/evidence/s3/family_package/p4ra_fqec_v1_family_package.json`；包内含 `family_id`、`formula_version`、参数分布、每任务 `task_id/task_fingerprint/split/params/seed/reference_digest`、split→task_ids 映射、`family_package_sha256`（= 包文件原始字节 sha256）、生成 code_sha、生成 UTC。
- 参考解封存（A5 S3-M0-03 处置）：完整参考解（u_star/f_star/lambda 等）写入**独立封存件** `research/concorde_metaopt/evidence/s3/references_sealed/p4ra_fqec_v1_references_sealed.json`，其 `sealed_reference_sha256` 写入 prereg；runner 在正式 run 期间**不得加载封存件**，只有 analysis 在 run 完成后可加载；冻结包只含 `reference_digest`（SHA-256 前 32 hex），不含 u_star/f_star 数值。
- 冻结件 sha256 写入 prereg（`frozen_package.family_package_sha256`、`hash_vectors_sha256`、`task_ids_sha256`、`references_sealed_sha256`、`split_counts`）；正式 run 前 A5 独立核验。
- 旧族（F-QE-feasible-v2/v3）只允许作为“历史诊断对照”只读引用，不得出现在 S3 任何训练/评估/统计中。

### 2.3 数据边界、split 白名单与 phase-scoped holdout 访问合同

- split 白名单（唯一允许，写入 family package / runner / prereg / analysis 枚举）：`dev`、`meta_train`、`meta_validation`、`meta_test`、`meta_test_ood`、`meta_test_negative_control`；S3 新产物不得写入历史名 `negative_control`；读取旧件时允许把历史名只读映射为 `meta_test_negative_control` 并记录映射。
- 阶段（phase）枚举：`TRAIN`（meta_train）、`DEV`（dev/meta_validation）、`EVAL`（meta_test）、`OOD`（meta_test_ood）、`NEGATIVE_CONTROL`（meta_test_negative_control）。每条评估记录必须写 `phase`。
- phase-scoped 泄漏标志（runner 与 analysis 双重校验；替代 S2 的单一 `holdout_metrics_read=false`）：
  1. `holdout_truth_used_for_training = false`：训练/episode bank 只读 meta_train；
  2. `holdout_truth_used_for_adaptation = false`：TRAIN/DEV 阶段的适配/支持集只读 meta_train 或 meta_validation 的 support 设计；
  3. `support_truth_read`（仅 EVAL/OOD/NEGATIVE_CONTROL 阶段）：正式评估时允许读取被测 task 的 support 标签用于 K=5 适配（算法输入，不是泄漏），记录布尔值与 `support_truth_read_utc`；
  4. `holdout_truth_used_for_bo_ranking = false`：BO 候选排序只用 support 标签，不得用 query 标签或参考解；
  5. `holdout_truth_read_for_evaluation = true`：仅评估器对算法已选设计返回 query truth、且仅用于计算端点；query truth 在 run 内只允许在端点计算时读取一次，记录 `evaluation_phase_read_utc`。
- 参考解使用边界：runner 不得读取 `references_sealed`；analysis 在 run 完成后读取并计算 `gap_to_reference`；任何 runner 进程读取封存件即 fail-closed（`S3_LEAKAGE_SEALED_REFERENCE_READ`）。
- 盲测：meta_test/meta_test_ood/negative control 在 prereg 冻结（M2）前不生成任何评估记录；冻结后只允许 A2 在 Lead 授权下执行一次正式评估 campaign（定义见下一条）；A5 可在复核时读取 run 产物但不得改动。
- 其他硬检查：support 与 query 设计不得相交（1e-12 不相交保证）；support 与初始点不得重叠；代理训练/适配只使用 support 标签。
- 授权 campaign（A5-S3M0R-05 处置）：每个 meta_test/meta_test_ood/negative control task 只允许一次**授权评估 campaign**；campaign 覆盖该 task 在预注册网格内的全部 runs（5 臂 × 2 预算 × opt_seed × meta_seed）与确定性重跑，`campaign_authorization_id`/`campaign_authorization_utc` 写入 run_config 与 data_manifest；campaign 内每个 run 仍独立记账与校验。

### 2.4 评估器与计费口径（S3 是合成评估，不是物理评估）

- 评估器：`make_synthetic_task_evaluator(task)`（S3 自实现，纯解析；不调用 RCAIDE/求解器），返回 objective/constraints/feasibility/valid；每次调用记账为 `synthetic_evaluation`。
- 计数合同：每 run 的 `billable_evals = B` 必须精确成立（support K 次 + 新初始 8−K 次 + 主搜索 B−8 次）；support 评价在每 run 开头真实调用评估器：首次访问记 `cache_hit=false` 并计入 synthetic_call_count；同一 run 内重复访问同一 support 设计记 `cache_hit=true` 且不重复计费；cache 不得跨 run 复用。DE 臂同样恰好 B 次。
- `physical_call_count = 0` 字段必须存在且为 0；同时记录 `synthetic_call_count = B` 与 `solver_processes_started = 0`；任何真实子进程/网络调用即 fail-closed。
- 评估记录字段以 §4.3 为唯一 schema（`evaluation_index/design/f/g1/g2/feasible/source/phase/holdout_truth_read/wall_s/record_digest`，共 19 字段）；§2.4 原列名为语义清单，映射为：`eval_index→evaluation_index`、`design_u→design`、`objective→f`、`constraints→(g1,g2)`、`valid` 由 box 与数值有限性派生、`synthetic` 由 evidence_scope 与物理计数承担、`cache_hit/billable` 由记录数=B 与 `source` 分布断言承担（R-S3-03）。预算超限或记录数不符立即终止该 run 并标 FAILED_BUDGET_MISMATCH。

### 2.5 家族校准协议（M1 阶段，仅 meta_validation，不碰 meta_test）

校准目标：冲突族既可解、又不过难/过易，确保 `feasible_hit_rate` 有区分度。步骤：
1. 生成候选 `delta1_base ∈ {0.20, 0.22, 0.25}`（优先序）的 meta_validation 20 任务（m2 ~ U(0.10,0.15)，其余参数同 §2.1）；每任务按 §2.1 重试规则生成，重试次数记入报告。
2. 对每个 delta1_base 计算：参考证书通过率、每任务 support 池（128 点）可行比例的中位数/最小/最大、128 池可行点数最小值、4096 个独立 LHS 点的可行比例（独立估计，不用 support 池）、`objective_regret` 分布、`margin` 分布、`conflict_ratio` 分布。
3. 接受条件（全部满足）：(a) 参考证书 20/20 通过；(b) 每任务 support 池 128 点至少 1 个可行点；(c) support 池可行比例中位数 ∈ [0.02, 0.50]，且 4096 点独立估计中位数 ∈ [0.02, 0.50]；(d) 无任何任务在 4096 点估计中全不可行；(e) `margin_m` 均值 ∈ [0.10, 0.15]；(f) 参考目标 regret 中位数 > 1e-6。
4. 若三个候选均不满足，允许在 meta_validation 上把候选扩展为 `{0.18, 0.28, 0.30}` 或微调 c 的采样区间 [0.30,0.70]→[0.25,0.75]（每次尝试记录尝试编号/参数/统计），但不得使用 meta_test；仍不满足则如实报告并请 A5 M1 复审是否调整族构造（走计划 v1.x 修订），不得强行冻结。
5. 校准报告：`research/concorde_metaopt/evidence/s3/calibration/family_calibration_<UTC>.json`（含每候选统计、接受/拒绝理由、最终选择、尝试清单、sha256）；A5 M1/M2 可复核；校准实现必须复用 §2.1 同一采样/参考解代码路径（不得另写几何）。
6. 预期量级（Lead 独立探针，<EXT>/p4-route-a/lead/s3/probe2/s3_linear_probe3.py，200 任务/候选，非验收证据）：delta1=0.20,m2=0.10 时 support 128 点可行比例中位 0.1484、4096 独立点中位 0.1544、无全不可行任务；delta1=0.25 时 0.1172/0.1191、最少 support 可行点 1；delta1=0.30 时 0.0938/0.0918 且 3/200 任务出现 support 0 可行点，故默认候选止于 0.25。校准必须以实际族代码复算，探针数字不作为冻结值。


## 3. 干预、臂、公平合同

### 3.1 五臂（Wave A 必须全部执行）

| 臂 id | 实现（m5_arms.py 内） | K=5 支持评价 | 8−K 新初始点来源 | 主搜索 | 备注 |
|---|---|---|---|---|---|
| S3-BO-RANDOM | `run_s3_bo_random` | 计入 B | `shared_initial_designs(task_id, opt_seed, 8)` 中按索引顺序取满足多样性规则的 3 点 | `maml_opt` BO，B−8 | 无代理 |
| S3-BO-FOMAML-OBJ | `run_s3_bo_fomaml_obj` | 计入 B | FOMAML 适配后按 `S_obj` 打分选 3 点 | 同上 | 只改初始点打分 |
| S3-BO-FOMAML-CON | `run_s3_bo_fomaml_con` | 计入 B | FOMAML 适配后按 `S_joint` 打分选 3 点 | 同上 | 主干预 |
| S3-BO-ANIL-CON | `run_s3_bo_anil_con` | 计入 B | ANIL 头-only 适配后按 `S_joint` 打分选 3 点 | 同上 | 低成本消融 |
| S3-DE | `run_s3_de` | 计入 B | support(5) + shared(3) | `maml_opt` DE/rand/1/bin，B−8 | 等预算基线 |

- 实现归属（A5 S3-M0-05/10 处置）：五臂全部作为 `research/concorde_metaopt/meta_learning/m5_arms.py` 的新增段（文件末尾 S3 段），**禁止新增 s3_arms.py**；每臂包一层 `run_s3_bo_arm(...)`，内部调用 `baseline_arms.run_bo_arm` 的 LEGACY_BO_ARM 合同路径；包装函数签名、返回结构与 S1/M5 审计过的 BO 路径逐字段兼容。
- 随机流合同（A5 S3-M0-10 处置）：
  1. BO 引擎 seed = `int.from_bytes(sha256(f"{task_id}|{opt_seed}|{meta_seed}|s3-bo-engine").digest()[:8], "big") % (2**31)`；**不含 arm 名、不含 budget**，故四个 BO 臂与两个预算共享同一引擎随机流；
  2. 候选池由 `shared_candidate_pool(task_id)` 生成（task 的 128 点 support LHS 去掉 5 个 support 点，共 123 点；sha256 写入 run 记录），四臂与两预算共用；
  3. 初始 3 点由各臂的确定性规则产生（打分/随机基线），不消耗 BO 引擎 RNG；BO 主搜索从固定初始点出发、以引擎 seed 驱动，四臂共享同一 `(engine_seed, candidate_pool_sha256, candidate_count=512, bo_config_sha256)` 四元组，单测断言四元组相等、`bo_engine_draws_sha256`（引擎在首个观测前的候选抽样序列）逐位相等；**不要求**初始 3 点之后的完整 trace 逐位一致（BO 后验依赖各臂初始观测，必然分叉；A4 NEW-04），改记 `bo_trace_first_divergence_index` 供审计；
  4. DE seed = `int.from_bytes(sha256(f"{task_id}|{opt_seed}|{meta_seed}|s3-de").digest()[:8], "big") % (2**31)`；DE 与 BO 不共享流；
  5. `shared_initial_designs(task_id, opt_seed, 8)` 由 `(task_id, opt_seed, "shared-init")` 派生，五臂共享；RANDOM 臂按索引顺序取满足多样性规则的前 3 点，其余臂的 support 5 点来自同一支持集，两集合不相交由构造保证。
- 所有 BO 臂共享同一 `maml_opt.bayesian.ConstrainedBayesianOptimizer/run_search` 引擎（不修改、不调参），候选数 512；唯一干预差异 = 8−K=3 个新初始点的选择（及 FOMAML/ANIL 适配方法）。
- 所有臂共享同一支持集：`select_support_designs(task, k_shot=5, meta_seed)`（同一 task/meta_seed 下逐位相同）；支持集评价在每 run 开始缓存，臂间不可共享缓存（run 为独立单位）。
- 全部臂必须写 `initial_designs_sha256`、`initial_design_row_digests`、`initial_diversity_min/max`、`bo_trace_sha256`（BO/DE 主搜索轨迹摘要），供公平性审计与克隆检测。

### 3.2 代理、联合评分与初始点多样性（精确公式，冻结）

- 代理网络：`MAMLConfig(input_dim=12, output_dim=3, hidden_sizes=(64,64), inner_lr=0.01, inner_steps=5, outer_lr=1e-3, tasks_per_batch=8, first_order=True, seed=meta_seed, backend="torch")`；输出 3 维 = [f, g1, g2]；输入仅 12 维设计向量（不含 task_id/context/truth/ood_flag 特征）。
- 训练 episode 合同（A5 S3-M0-06 处置；详见 §4.1）：每 meta_seed 一个模型；200 outer steps × 8 tasks = 1,600 episodes/模型；3 个 meta_seed 共 4,800 **唯一** episodes；模型-episode 消耗 = 9,600（3 FOMAML 模型 + 3 ANIL 模型各 1,600，A5-S3M0R-09），计入 `resources.auxiliary_compute` 披露；episode bank 先构建后训练，sha256 写入 prereg 与 run_config。
- 每任务标签归一化（仅用 support 标签，K=5）：`f_scale = max(std(f_support), 1e-6)`；`g_scale_k = max(sqrt(mean(g_k_support^2)), 1e-6)`，k∈{1,2}；标准化 `f_tilde = (f - mean(f_support))/f_scale`，`g_tilde_k = g_k / g_scale_k`。该归一化在训练 episode、适配、打分中一致使用；最优/最差 run 的归一化参数必须记录。
- 联合评分（CON/ANIL 臂）：候选 x 的 `S_joint(x) = f_tilde_hat(x) + 10.0 * (max(0, g1_tilde_hat(x)) + max(0, g2_tilde_hat(x)))^2`；按 `(S_joint 升序, 候选索引升序)` 取满足多样性规则的 3 个互异设计。
- 目标评分（OBJ 臂）：`S_obj(x) = f_tilde_hat(x)`；按 `(S_obj 升序, 候选索引升序)` 取满足多样性规则的 3 个。
- 初始点多样性规则（A4 DEV-07 处置；Wave A 预注册，不推迟）：三个新初始点与 5 个 support 点、以及彼此之间，在归一化 box 距离 `d_norm(x,y) = ||x-y||_2 / sqrt(12)` 下必须 >= `0.10`；若无法满足 3 点，则按已选点最小距离降序补足，`diversity_relaxed=true` 写入记录；每 run 记录 `initial_diversity_min/max`。该规则**统一适用于五臂（含 RANDOM）**，各臂只在自己的确定性候选序列内按索引顺序挑选，不改变各臂随机流来源。
- 随机臂：从 `shared_initial_designs(task_id, opt_seed, count=8)` 中按索引顺序取满足同一 `d_norm>=0.10` 规则的 3 个；必须与 support 集无重复（重叠即 FAILED_LEAKAGE）。
- 候选池（打分用）：`shared_candidate_pool(task_id)` = `task.support_designs()` 的 128 个固定 LHS 点去掉 support 的 5 个点，共 123 个；候选池 sha256 写入 run 记录；三臂（OBJ/CON/ANIL）使用同一候选池。
- Meta-SGD 排除（A4 DEV-06 处置）：S3 不实现、不训练、不评估 Meta-SGD；若 Wave A 结果与 A5 认为必须，只能按 Issue #7 §2 另立计划与审批，本计划与 prereg 不得包含 Meta-SGD 臂。
- 不确定性：S3 不标定不确定度，所有产物 `uncertainty = null`、`calibration = "NOT_PERFORMED"`；禁止伪概率、禁止把代理输出当置信度。
- 适配成本：FOMAML/ANIL 的适配 wall_s、前向预测次数、候选打分次数、峰值内存写入 run 记录；用于 Q3 成本-性能比较。

### 3.3 预算、K 与公平性约束

- `B ∈ {64, 128}`；K=5（固定）；初始点 8 = 5 support + 3 new；主搜索 B−8；DE 相同总预算；所有臂每 run 恰好 B 次评估。
- 任务、opt_seed、meta_seed 为三层重复；同一 (task, budget, arm) 的 opt_seed 均值在统计前先聚合；meta_seed 是模型训练复制，FOMAML/ANIL 用 3 个模型，RANDOM/DE 的 meta_seed 只作为重复标签（不训练模型，但每 meta_seed 都执行，以保持网格平衡）。
- 公平性断言（fail-closed）：同 (task, budget, opt_seed, meta_seed) 下五臂的 B、K、初始点总数、support 设计集合、BO 引擎配置、候选数、候选池 sha 完全一致；仅 3 个新初始点与适配方法可不同。
- 克隆检测：若某两臂逐 run `initial_designs_sha256` 完全相同且方法声明不同 → 标 CLONE，排除推断并在报告披露；任一预算层克隆率 > 20% → 该层标 IDENTIFIABILITY_LIMITED（A4/A5 一致要求）。
- 预算记账：run 记录 `billable_evals == B`、`support_evals == 5`、`initial_evals == 3`、`bo_or_de_evals == B-8`；任何不等即该 run FAILED_BUDGET_MISMATCH，且不进入统计（失败 run 数必须披露）。

## 4. 训练、正式 run 与运行合同

### 4.1 训练与 episode bank 合同（M1/M2，不接触 holdout）

- episode bank 构建（A5 S3-M0-06 处置；deterministic，纯 CPU）：对每个 `meta_seed ∈ {0,1,2}`，for `step ∈ [0,199]`，for `slot ∈ [0,7]`：
  1. 任务：`task_index = int.from_bytes(sha256(f"{FAMILY_SEED}|{meta_seed}|task|{step}|{slot}").digest()[:8], "big") % 60`；若与同 step 已选任务重复，则按 `slot+1` 重试直到 8 个互异任务（最多 100 次，失败即构建错误）；
  2. `K_train = 5 if ((step*8+slot) % 2 == 0) else 10`（固定 50/50 交错）；
  3. support 设计索引：以 `(meta_seed, step, slot, "support")` 的 sha256 为随机源，对 128 个 support_designs 做 Fisher-Yates 取前 K_train；query 设计索引：以 `(meta_seed, step, slot, "query")` 为随机源，从 64 个 query_designs 取全部 64；
  4. 断言 support 集合与 query 集合无重叠（1e-12）；
  5. episode 记录：`meta_seed, step, slot, task_id, K_train, support_indices, query_indices, support_designs_sha256, query_designs_sha256, episode_digest`；
  6. `episode_digest = sha256(canonical JSON(episode 记录去掉 episode_digest))`。
- bank 文件：`research/concorde_metaopt/evidence/s3/models/episode_bank_meta_<seed>.jsonl`（每行 canonical JSON，LF）；`episode_bank_sha256 = sha256(整个文件字节)`；三个 bank 的 sha 与条目数（1,600 each）写入 prereg 与 run_config。
- 训练（FOMAML）：`meta_train` 60 任务；每 outer step 取 8 个 episode；support K_train、query 64；内循环 SGD lr=0.01、5 步、loss=MSE(3 输出等权)；外循环 Adam lr=1e-3；outer_steps=200；first_order=True；每 meta_seed 一个模型。
- 训练（ANIL 参数分区，A5 S3-M0-06 处置）：模型参数分 body（除末层外全部）与 head（输出层 weight 3×64 + bias 3）；内循环只更新 head（body 逐位不变，单测断言）；外循环更新**全部参数**：head 走适配后 query loss 的梯度，body 走 query loss 对冻结特征的梯度（即 ANIL 的外循环更新 body，但不通过内循环二阶路径）；优化器/学习率/预算/episode 序列与 FOMAML 逐位相同。
- 模型产物：`evidence/s3/models/fomaml_meta_<seed>.json`、`anil_meta_<seed>.json`（确定性 JSON：参数按名字升序、float 用最短 round-trip repr、LF、无时间戳）+ `model_manifest.json`（每模型 sha256、config、训练统计、episode_bank_sha256）；M2 冻结。
- M2 冻结后正式 run **只加载、不重训**（R-S3-06）：runner 从 prereg.models 的仓库相对路径加载 fomaml/anil 各 3 个冻结模型并校验 sha256；冻结 model_manifest.json 原样复制到 run 目录并追加 verification 块（loaded_from_prereg=true、prereg_models_sha256、verified_utc）；SMOKE 允许 run 内重训微型模型并 DISCLOSED。
- **FORMAL 记录语义（R-S3-07）**：正式 run `record_counts.train=0`、`status_counts.train={OK:0,FAILED:0}`、`run_records` 不含 train 行；M2 训练（2 模型 × 3 meta_seed × 200 step = 1,200 训练记录）属 M2 证据，存于 evidence/s3/models/ 与 episode banks，不进正式 run；SMOKE 仍原地训练 2×len(meta_seeds)×outer_steps 并 DISCLOSED models_retrained_in_run。
- 训练统计：loss 曲线（每 10 step）、wall_s、峰值内存、episode digest 抽样；`train_wall_s` 与 `peak_memory_mb` 写入 run_summary 与模型 manifest。
- SMOKE 训练：`outer_steps=2`、`meta_seeds=(0,)`、episode bank 16 条、训练/评估预算按 SMOKE 覆盖；用于 e2e 与梯度门，不进入正式统计；SMOKE 语义见 §4.5。
- 训练不得使用 meta_validation/meta_test/negative control；校准（§2.5）只使用 meta_validation 的几何统计，不训练模型。

### 4.2 正式 run 网格、OOD/负控制/确定性子集与预算记账

| 段 | 网格 | run 数 | 合成评估数 | 用途 |
|---|---|---|---|---|
| 主统计（R-S3-02 后正式段） | 20 task × 5 臂 × 2 预算 × 5 opt_seed × 3 meta_seed | 3,000 | 288,000 | C1/C2 主/次推断 |
| 负控制 | 10 task × 5 臂 × 2 预算 × 3 opt_seed × 1 meta_seed | 300 | 28,800 | 标签打乱诊断，不进推断 |
| OOD | 10 task × 5 臂 × 2 预算 × 3 opt_seed × 1 meta_seed | 300 | 28,800 | 描述性 OOD 诊断（fig7） |
| 确定性 | R-S3-05A 预注册规则：每 (arm,shard) 1 run（40）+ 每臂补 2 run（20）= 60/次 × 3 次 | 180 | 17,280 | 确定性子集，不进推断 |
| 合计（正式段唯一网格） | — | 3,780 | 362,880 | campaign 墙钟 ≤ 7,200 s；sum_run_wall ≤ 28,000 s |
| K-sweep 诊断（M1，预 run） | 4 task × 5 臂 × B=64 × 3 opt_seed × 1 meta_seed × K∈{0,1,3,5} | 240 | 15,360 | fig2 数据，DEVELOPMENT_VALIDATION_ONLY，不进正式段 |

- **名义上限网格 vs 正式唯一网格（A5-S3M0R3-05 处置）**：opt_seed=10 的 6,000/576,000（加负控/OOD/确定性后 6,900/662,400）仅为名义上限，任何情况下不得执行；R-S3-02 触发后正式段唯一合法网格 = 3,780 runs/362,880 evals，prereg 冻结该单值并由 build/verify 断言。
- 主统计 5 opt_seed 由 R-S3-02 降网格生效（M2 计时试点串行外推 ≈23,400 s > 5,400 s，必触发）；负控/OOD 不随 opt_seed 降级。

- 负控制只用一个 meta_seed（A5 S3-M0-13 处置）：标签置换破坏 support→query 关系，模型间差异不是该诊断的目标；固定 meta_seed=0 以控制成本，并在 prereg/报告披露“负控制不用于跨模型比较”。
- OOD 描述性（A5 S3-M0-04 处置）：OOD 段只作描述（fig7、描述统计），不进入 C1/C2；OOD 任务定义见 §2.2。
- 计时试点与 R-S3-02（A5-S3M0R-04/-05、R-S3-05A）：M2 在 meta_validation 上跑 1 task × 5 臂 × B=128 × 1 opt × 1 meta = 5 runs 记录墙钟与峰值，并执行 §4.2.1 的 W=8 稳态试点门；按实测外推正式段（3,780 runs）> 5,400 s（串行实测 ≈23,400 s）→ **R-S3-02 必触发**，Lead 在 prereg 冻结前书面签发 R-S3-02（opt_seed 10→5）；正式段唯一网格 3,780/362,880，R-S3-02 写入 prereg 与 §17 处置表，A5 M2 核验，冻结后不得再降级。
- 正式 run 必须使用 clean worktree；run 目录：`<EXT>/p4-route-a/a2/s3_formal/s3-formal-<UTC>/`；不得写仓库；跑完由 Lead 做哈希核验与打包。
- 运行停止规则：单 run 墙钟 > 60 s 或峰值 > 8,192 MB → 立即停止整个 run，报 RESOURCE_LIMIT，不重试；总墙钟 > 7,200 s → 停止并交部分产物；任何物理/网络调用 → fail-closed；任何预算不符 → 该 run FAILED（不重试），失败率 > 1% 时停止并报 A5。
- 确定性（A5 S3-M0-12/-07 处置 + R-S3-05A §6）：正式 run 之后执行 3 次确定性重跑，每次 60 runs（3 次共 180 runs/17,280 evals）：(a) 对 5 臂 × 8 shard 每个组合，在 meta_test 网格中按 canonical run_key sha256 升序取第一个匹配 run（40）；(b) 每臂再取 2 个未选 run，优先不同 budget/task/opt_seed（20）；(c) 子集按 canonical run_key 排序，determinism.subset_rule 与 subset_run_keys_sha256 写入 prereg（M2 冻结），M2 断言子集覆盖 5 臂 × 8 shard 全组合，缺组合 fail-closed。要求 run_records 逐记录 core digest 一致（core 排除 wall_s/peak_memory_mb/时间戳）、3 次 run_config 网格字段一致、analysis 对同一产物字节级一致 aggregate（排除 generated_utc）；披露确定性仅覆盖该预注册子集，不是全网格。
- 运行产物：run_config.json、run_summary.json、run_records.jsonl、model_manifest.json、data_manifest.json、fd_or_gradient_gate.json、execution_report.json（schema v2）、negative_control_{records.jsonl,summary.json}、determinism/{r1,r2,r3}/、analysis/（见 §5）、logs/。
- **执行层并行合同（v1.3 R-S3-05；v1.3a 按 R-S3-05A 修订）**：方法合同（臂/评分/BO 配置/candidate_count=512/candidate_pool=123/初始 3 点/support 5 缓存/预算 B/K/端点/统计/schema）全部不变；唯一变化是 campaign 层以 W=8 并行执行独立 run。分片规则 shard = int(sha256(canonical_json(run_key))[:8], 16) % W，run_key={arm_id,task_id,budget,opt_seed,meta_seed}；合并按该 5 元组规范排序；worker 编号不得进入 RNG/记录/digest。W=1 为默认路径，必须与串行逐位等价。线程固定：OMP/MKL/OPENBLAS/NUMEXPR/VECLIB=1，worker 与主进程 torch.set_num_threads(1)。
- 确定性扩展：单测固定向量断言 W∈{1,2,3,8} 下同一 run_key 集合的 record_digest 序列与 aggregate 完全一致；正式 run 的确定性子集（本节上文）同样在 W=8 下执行 3 次；`compare_deterministic_runs` 语义不变。
- 计时口径与硬上限（A5-S3M0R3-03 处置）：每个 run 在子进程内测 wall_s/peak_memory_mb；父进程记录 campaign 并行墙钟 campaign_wall_s、**sum_run_wall_seconds = Σ 单 run wall_s（不是 process CPU 时间）**、max_run_wall_s、max_peak_memory_mb。resource_limits.total_wall_s=7,200 解释为 campaign 并行墙钟；**resource_limits.sum_run_wall_limit_s=28,000**（= 实测 23,400 s 的 1.20×）为 Σ 单 run wall 硬上限；任一超限 → RESOURCE_LIMIT 停止整个 run、不重试、交部分产物并披露（stop_reason=S3_SUM_RUN_WALL_LIMIT 或 S3_CAMPAIGN_WALL_LIMIT）。产物 execution_report.json 唯一 schema p4ra-s3-execution-report-v2（18 字段：schema_version、campaign_id、run_mode、created_utc、parallel_workers、execution_rule、shard_runs_sha256、per_shard_counts、run_count_requested、run_count_completed、campaign_wall_s、sum_run_wall_seconds、max_run_wall_s、max_peak_memory_mb、sum_run_wall_limit_s、stop_reason、physical_call_count、parallel_note），由 s3_runner 写入、validate_run_artifacts 精确键集校验 + 负控，并纳入 data_manifest.artifact_sha256；W 规则写入 campaign.rules 与 scope_notes 确定性文本。
- 实测依据（R-S3-05A 吞吐外推验收，bench_v13a）：research/concorde_metaopt/evidence/s3/bench/bench_v13a.json（run1）与 bench_v13a_run2.json（run2），26,825 / 26,821 B（仓库 canonical LF 字节），sha256 16fbb1f5…（run1）/ 004bbe64…（run2）；EXT 原始 CRLF 字节为 27,816 / 27,812 B，sha256 60e22cc9…c06c（run1）/ 5e9f2655…8651（run2），两者差异仅 EOL；W=1 wall 177.817 / 176.431 s、W=8 wall 42.267 / 43.727 s（5 臂 × 3 meta_validation task × B∈{64,128}，30 runs，同一 run_key 集合）；W=8 稳态吞吐 0.7098 / 0.6861 runs/s → 3,780 runs 外推 3,518.653–3,712.731 s（吞吐）/ 5,325.653–5,509.562 s（保守；run2 保守值落入 (5,400,7,200] 区间，由 R-S3-05B 书面接受，硬顶 7,200 s 不变）；record_digest 逐位一致 true（30/30，两轮均 first_divergence_index=null）；8 worker 峰值和 2,448.78 / 2,449.03 MB < 8,192 MB；连续两次 wall 差异 0.779%（W1）/ 3.453%（W8） <20%。旧 8-run bench（6,274 B sha 0260237f…）仅历史证据，不再作为判据。

### 4.2.1 W=8 稳态试点门与 fallback（M2 必过，不可跳过；A5-S3M0R3-02/-04 处置）

- 时点与规模：模型训练 + 校准 + FD 门完成后、prereg 冻结前，在 meta_validation 上跑 3 task × 5 臂 × B=128 × 1 opt_seed × 1 meta_seed = 15 runs，W=1 与 W=8 各一次（同一 run_key 集合）。
- 判据（全 PASS 才可冻结 prereg）：(i) record_digest 序列逐位一致、status/record_counts 全等、合并顺序一致；(ii) 按 W=8 稳态吞吐（排除一次性池启动）外推 3,780 runs ≤ 5,400 s（(5,400, 7,200] 需 Lead 书面接受；>7,200 不得启用 W=8）；(iii) 8 worker 峰值之和 < 8,192 MB、单 run 峰值 < 8,192 MB；(iv) 连续 2 次同集合 campaign wall 差异 < 20%；(v) 线程环境固定 OMP/MKL/OPENBLAS/NUMEXPR/VECLIB=1 与 torch.set_num_threads(1)。
- 产物：evidence/s3/gate/w8_pilot_gate.json（schema p4ra-s3-w8-pilot-gate-v1：w1_wall_s、w8_wall_s、runs_per_second、projected_3780_wall_s、record_digest_equal、peak_memory_mb、threads_env、verdict），纳入 M2 证据与 A5 M2 核验。
- Fallback（45 min 内不达标，Lead 书面重裁，只能执行一次）：(a) W=4：campaign 墙钟 7,200 s、sum_run_wall 28,000 s 不变；或 (b) 串行 W=1：resource_limits.total_wall_s 改 25,200 s 并重新授权（3,780 runs ≈23,400 s，留 7.7% 余量），prereg 冻结前写入并由 A5 核验；正式 run 中不得切换并行度。

### 4.3 run 产物 schema（v1，单源定义）

- 共享 schema 版本常量由 `s3_prereg.py` 单源定义，`s3_runner.py`/`s3_analysis.py` 必须 import 不得复制：`S3_RUN_CONFIG_SCHEMA_VERSION="p4ra-s3-run-config-v1"`、`S3_RUN_SUMMARY_SCHEMA_VERSION="p4ra-s3-run-summary-v1"`、`S3_RECORD_SCHEMA_VERSION="p4ra-s3-record-v1"`、`S3_AGGREGATE_SCHEMA_VERSION="p4ra-s3-aggregate-v1"`。
- `run_config.json` 必需字段：schema_version, run_id, run_mode, prereg_id, prereg_digest, analysis_plan_digest, code_sha, family_package, task_ids_sha256, references_sealed_sha256, data_boundary, models, arms, budgets, seeds, episode_bank, evaluation_grid, fd_or_gradient_gate, record_counts, record_schemas, resource_limits, physical_call_count, evidence_scope, scope_notes（可选 smoke_overrides）。
- `run_records.jsonl` 每行（评估层）：schema_version, run_id, task_id, split, arm_id, budget, opt_seed, meta_seed, evaluation_index, design, f, g1, g2, feasible, source（support/initial/bo/de）, phase, holdout_truth_read, wall_s, record_digest；训练层：schema_version, run_id, meta_seed, outer_step, loss, wall_s, train_episode_digest, record_digest；训练记录字段集按 §4.1（不含 task_id/split，边界由 episode bank 承载）。
- `run_summary.json` 必需字段：schema_version, run_id, run_mode, created_utc, status, record_counts, status_counts, per_run, models, resources, determinism, fd_or_gradient_gate_sha256, data_manifest_sha256, negative_controls, physical_call_count, evidence_scope, environment, scope_notes。
- v1.3a 语义：FORMAL 的 run_summary.models 为 prereg 冻结条目（loaded=true，含 sha256/path），resources.auxiliary_compute 披露 models_source=PREREG_FROZEN、model_training_episodes=9,600、fd_gate_episode_reruns=128（均属 M2，不计本次 run）。
- v1.3a（R-S3-07）：FORMAL `record_counts={train:0,eval:362,880,total:362,880}`、`status_counts.train={OK:0,FAILED:0}`；若出现 train 记录则 analysis fail-closed；SMOKE 按实际训练记录计。
- 资源字段：`per_run`（arm_id, task_id, budget, opt_seed, meta_seed, status, wall_s, peak_memory_mb）、`resources`（total_wall_s, max_wall_s, max_peak_memory_mb, auxiliary_compute, resource_limits）。
- `data_manifest.json`：data_boundary（phase 标志）、meta_train/meta_validation/meta_test/negative_control/ood 的 task_id 列表与 sha、references_sealed_sha256、holdout_truth_read_phase（仅 EVAL）、physical_call_count、产物 sha 列表。
- v1.3a：data_manifest.artifact_sha256 必须包含 execution_report.json 的 sha256，否则产物不完整。
- `model_manifest.json`：每模型 arm_type（fomaml/anil）、meta_seed、config、path、sha256、train_wall_s、peak_memory_mb、episode_bank_sha256、final_train_loss。
- v1.3a（R-S3-06）：FORMAL 时 model_manifest 另含 verification 块（loaded_from_prereg、prereg_models_sha256、verified_utc）；train_wall_s/peak_memory_mb/final_train_loss 为 M2 实测值。
- v1.3a（R-S3-07）：model_manifest 固定于 evidence/s3/models/model_manifest.json；FORMAL run 复制 + verification{loaded_from_prereg,prereg_models_sha256,verified_utc}，每模型 sha256 必须等于 `prereg.models` 对应项；不新增 prereg 字段。
- 版本/字段不符即 fail-closed（错误码 `S3_ANALYSIS_RUN_SCHEMA_INVALID`），不得静默降级；未知额外字段记 DISCLOSED。

### 4.4 梯度/FD 门契约（A5 S3-M0-08 处置）

- 目标：对 FOMAML 与 ANIL 各一个 meta_seed=0 的冻结模型（M2 产物；SMOKE 可用 SMOKE 训练产物），验证元梯度实现；**每模型 32 坐标、2 个模型、合计 64 坐标条目**（32 坐标 × 2 方向 × 2 模型 = 128 次 episode 重跑，§13）。
- 参数：epsilon = 1e-6 * max(1.0, |θ_i|)（逐坐标相对尺度）；tolerance = 1e-6（最大相对误差）；坐标数 32（**每模型**从全参数中按 sha256(s3-gate|param|index) 排序取前 32，固定）；中心差分 (L(θ+ε)-L(θ-ε))/(2ε)。
- 损失：SMOKE 训练同一 episode（`meta_seed=0, step=0, slot=0..3` 共 4 episode 均值，batch=4），内循环 5 步、inner_lr=0.01，与训练路径逐位相同；`K=0` 时不调用内循环（单测断言 `inner_steps=0` 分支等价于直接用初始参数评估）。
- 计算：解析梯度由 `meta_train_step(second_order=False)` 的 FOMAML 路径（与训练同实现）给出；数值梯度对原始 θ 逐坐标 ±ε 重跑完整 episode 内循环后取 query loss；比较 `|num-ana| / max(|num|,|ana|,1e-12)`，任一坐标超 tol 即 `S3_GATE_FD_FAIL`。
- 时点：M2 冻结模型前；产物 evidence/s3/gate/fd_or_gradient_gate.json（schema p4ra-s3-fd-gate-v1：created_utc、tolerance=1e-6、epsilon_rule、models={fomaml_meta_0:{arm_type,meta_seed,n_checked=32,status,max_relative_error,coordinates[{index,param,analytic,numeric,relative_error} × 32]}, anil_meta_0:{同上}}、negatives={tamper,anil_body_frozen,k0_equivalence}、status、max_relative_error）；sha256 写入 prereg 与 run_config；SMOKE fd_coordinates=N 对每个模型生效。
- **R-S3-07 路径与绑定**：gate 固定于 evidence/s3/gate/fd_or_gradient_gate.json；M2 `build_preregistration` 必须断言该文件存在且其原始字节 sha256 进入 `prereg.package_sha256` 的 evidence/s3 清单（缺失 → fail-closed，不新增 prereg 字段）；FORMAL runner 读该文件并把 raw sha256 写入 `run_config.fd_or_gradient_gate={sha256, coordinates_per_model:32, coordinates_total:64, mode:"FORMAL", models:{fomaml_meta_0/anil_meta_0 各 path/sha256/n_checked/status/max_relative_error}}`；SMOKE N=fd_coordinates、models 恰两键。
- 不占用正式 run 预算：这是代码正确性检查，不计入 B、不写入 run_records；但必须在 run_summary.resources.auxiliary_compute 披露计算量与墙钟（`fd_gate` 计算次数）。
- 负控：篡改坐标数值 1 个 → 门必须 FAIL（`S3_GATE_TAMPER_DETECTED`）；ANIL 的 body 参数在适配前后必须逐位相同（`S3_GATE_ANIL_BODY_FROZEN`）；K=0 等价性（`S3_GATE_K0_EQUIVALENCE`）。

### 4.5 SMOKE 语义（开发自检，不进入正式统计）

- `run_mode ∈ {FORMAL, SMOKE}`；SMOKE 必须提供 `smoke_overrides`，键集：`outer_steps, meta_seeds, budgets, opt_seeds, eval_tasks, k_sweep, fd_coordinates`；允许与 prereg 不同并记 DISCLOSED（`code=S3_ANALYSIS_SMOKE_BUDGET_DISCLOSED`）。
- v1.3a：SMOKE 的 fd_coordinates=N 对**每个模型**生效（n_checked=N，允许 1-2 个模型）；FORMAL fd gate 恒为 2 模型 × 每模型 32 坐标，见 §4.4。
- SMOKE 的 episode bank 使用 `outer_steps=2`、`meta_seeds=(0,)`、16 episodes；评估用 4 task（meta_validation 前 4）×5 臂×2 预算×1 opt×1 meta = 40 runs；仅用于 e2e/图数据形状/门测试。
- FORMAL 必须与 prereg 严格一致（包 sha、task ids sha、episode bank sha、网格、预算、seeds、阈值）；不一致 fail-closed。

## 5. 端点、统计与图

### 5.1 端点定义（A5 S3-M0-02 + A4 DEV-02/-03/-04 处置）

逐 run 计算（评估顺序 = support 5 → initial 3 → 主搜索 B−8，共 B 个索引，1-based）：
- `feasible_hit_rate` = 满足 g1<=0 且 g2<=0 的评估点数 / B（∈[0,1]）。
- `best_feasible_value` = 可行点中 f 的最小值；无可行点 = null。
- `gap_to_reference` = `best_feasible_value − f_ref`（f_ref 来自封存参考解，>=0 数值上允许 -1e-9 容差）；无可行点 = null；run 阶段不读参考解。
- `first_feasible_eval_index` = 第一个可行评估点的 1-based 索引（1..B）；无可行点 = null。
- `surrogate_rmse` / `surrogate_mae` = 该 run 中被评估设计上的 [f,g1,g2] 三输出预测与真值的均方根/绝对误差（在 task 标准化尺度上，用 run 内 support 的归一化参数）；另给 f-only 的 `f_rmse`/`f_mae`。
- `adaptation_cost` = 适配 wall_s（FOMAML/ANIL 实际测量）、前向打分次数；`total_cost` = run wall_s。
- Issue #7 §4 端点映射（A4 DEV-04 处置）：四个 Issue 端点中 `feasible_hit_rate` 与 `gap_to_reference` 进入正式推断（C1/C2），`best_feasible_value` 对应 `gap_to_reference` 的原始量并同表报告，`first_feasible_eval_index` 为描述性端点（不参与 Holm 推断，单独报告 CI）；`RMSE/MAE` 按 Issue 要求作为描述性指标报告。降级理由：Issue 未规定目标优化端点的主次，本计划按“可行性冲突”问题优先选可行命中率；`best_feasible_value` 在可行率极低时大量 null（M5 前车之鉴），作主终点会导致不可比，故作次要。该映射写入 prereg 与回执。

### 5.2 聚合与推断

- 一级统计单位 = task（n=20，meta_test）。对每个 (task, budget, arm)：先对 opt_seed（10 或 R-S3-02 后的 5）与 meta_seed（3）取均值 → 得到该 task 的端点值；null 端点（无可行点）按缺失处理并在 null_disclosure 报告数量，不插值。
- 主族 C1（Holm family size=2，family_id=`s3-feasible-hit-2tests`；comparator 固定 = `S3-BO-FOMAML-OBJ`，A5-S3M0R-01）：C1a = `feasible_hit_rate` FOMAML-CON − FOMAML-OBJ @ B=128；C1b = 同上 @ B=64；预期方向 = FOMAML-CON 更高；检验为双侧 exact；获益阈值 +0.02，损害阈值 −0.02。RANDOM/DE 仅描述性报告，不进入 C1。
- 次族 C2（Holm size=2，family_id=`s3-gap-to-ref-2tests`；comparator 固定 = `S3-BO-FOMAML-OBJ`）：C2a = `gap_to_reference` FOMAML-CON − FOMAML-OBJ @ B=128；C2b = @ B=64；预期方向 = FOMAML-CON 更低（gap 更小）；检验为双侧 exact；获益阈值 = 相对 −1%，损害阈值 = 相对 +1%（相对 FOMAML-OBJ 均值，分母 max(|mean_OBJ|,1e-06)，null 按缺失处理）。
- comparator 断言（单测）：C1/C2 的 (arm_a, arm_b) 必须等于 (`S3-BO-FOMAML-CON`, `S3-BO-FOMAML-OBJ`)；RANDOM/DE 出现在推断表即 `FAILED_COMPARATOR_MISMATCH`。
- 检验：task 级配对差做 Wilcoxon signed-rank 精确检验（tie-aware 精确符号翻转枚举，2^n 全枚举，n<=20 可行）；零差处理（A5 S3-M0-11 处置）：主分析丢弃零差并报告 `n_zero`、`n_eff`，`n_eff<15` → INCONCLUSIVE；敏感性分析 (a) Pratt 含零差秩、(b) 10,000 次符号置换（seed=20261107）报告 p 值一致性；ties 用精确符号翻转分布（不依赖正态近似）。
- 多重比较：C1、C2 各自独立 Holm（m=2）；ANIL、DE、first_feasible、RMSE/MAE、OOD、负控制全部为描述性，不做推断，报告点估计 + 任务级 bootstrap 95% CI（10,000 次，重采样 task，seed=20261107）。
- 决策（每个端点层；互斥穷尽、优先级从上到下；与 §1.3 完全一致）：(1) `INCONCLUSIVE` = n_eff<15 或不可计算；(2) `SUPPORTED_BENEFIT` = p<0.05 且效应 ≥ 阈值；(3) `SUPPORTED_HARM` = p<0.05 且效应 ≤ −阈值；(4) `NEGLIGIBLE_SIGNIFICANT` = p<0.05 且 |效应| < 阈值；(5) `DIRECTION_INCONSISTENT` = p≥0.05 且效应 ≤ −阈值；(6) `NULL` = 其余（p≥0.05 且非 DIRECTION_INCONSISTENT）。总体 S3 决策（唯一优先级；A4 DEV-08/A5-S3M0R-07）：(1) 任一层 INCONCLUSIVE → `INCONCLUSIVE`；(2) 任一层 SUPPORTED_HARM → `HARM`；(3) 任一层 DIRECTION_INCONSISTENT → `DIRECTION_INCONSISTENT`；(4) 两层 SUPPORTED_BENEFIT → `BENEFIT`；(5) 一层 SUPPORTED_BENEFIT 另一层 NULL/NEGLIGIBLE_SIGNIFICANT → `NO_EVIDENCE`；(6) 其余 → `NO_EVIDENCE`。判定必须由固定查表函数产生并附 3×3 组合单测。
- ANIL 消融决策：若 ANIL 的 feasible_hit_rate 不低于 RANDOM 均值 − 0.02 且 ANIL 适配+训练成本 <= FOMAML-CON 的 75% → `ANIL_COST_EFFICIENT`；若 ANIL 显著低于 RANDOM（描述性 CI 上界 < −0.02）→ `ANIL_INFERIOR`；否则 `ANIL_INCONCLUSIVE`。DE 作为等预算基线：报告与 RANDOM 的配对差（描述性），不参与 C1/C2。
- 负控制分析：比较真实标签与打乱标签的 `feasible_hit_rate`/gap 差异；若打乱后 CON−OBJ 差异仍 >= 真实 CON−OBJ 差异的 50%，RANDOM/DE 仅描述，标 `NEGATIVE_CONTROL_SUSPICIOUS`。
- 全部汇总写 `s3_endpoint_tables.csv`、`s3_per_task_endpoint_values.csv`、`s3_holm_family.csv`、`s3_null_disclosure.csv`、`s3_negative_controls.csv`、`s3_ood_descriptives.csv`、`s3_cost_table.csv`、`aggregate.json`。

### 5.3 图（10 个键；Issue #7 §4 七类映射见 §5.4）

| 键 | 内容 | 数据源 | 备注 |
|---|---|---|---|
| fig1_training_loss_and_full_meta_grad | 训练 loss 曲线（FOMAML/ANIL）+ FD 门 num vs ana 散点（①） | model_manifest、fd_or_gradient_gate.json | 必须真实数据 |
| fig2_kshot_rmse_k0_k1_k3_k5 | K-shot 后 query RMSE f/g1/g2（②） | K-sweep 诊断（M1，DEV_VALIDATION_ONLY） | 未执行则 NOT_RUN |
| fig3_feasible_hit_rate_by_arm | 五臂 feasible_hit_rate 分布（③）；主对比 CON−OBJ，RANDOM/DE 仅描述 | aggregate/per-task CSV | 主图 |
| fig4_best_feasible_and_first_feasible | best_feasible_value / gap / first_feasible 分布（④）；主对比 CON−OBJ | per-task CSV | 主图 |
| fig5_fomaml_vs_full_vs_anil_cost | S2 FULL/FOMAML 成本-性能（只读）+ S3 ANIL 成本（⑤） | S2 归档 aggregate + S3 cost CSV | 说明跨阶段口径 |
| fig6_task_family_diagnostics | 族内几何诊断（δ1、m2、f_ref、可行比例）⑥ | family package 只读字段 + calibration | 不声称族间差异 |
| fig7_ood_diagnostics | OOD 段与 ID 段的描述性对比（⑥） | OOD records | 描述性 |
| fig8_negative_controls | 负控制置换前后对比（⑥） | negative_control summary | — |
| fig9_determinism_and_budget | 确定性子集一致性 + 预算记账（⑥） | determinism + run_summary | — |
| fig10_vspaero_gate_status | 只读 VSPAERO 门禁状态（⑦） | S2/D-12D 归档门禁 JSON（只读） | 不启动求解器、无新物理 |

- 每图必须：中文标题/轴标签/图例、`evidence_scope=DEVELOPMENT_VALIDATION_ONLY` 水印或脚注、数据源文件与 sha 脚注、对应支持 CSV（`figN_*_data.csv`）。
- 缺数据 → `NOT_RUN` 并在 figure_status.json 记原因，禁止伪造/插值/占位数据。

### 5.4 七类映射与 fail-closed 分析校验（A4 DEV + A5 S3-M0 处置）

| Issue #7 §4 图类 | 键 |
|---|---|
| ① 训练与全元目标 FD | fig1 |
| ② K-shot 误差 | fig2（K-sweep 诊断） |
| ③ Kshot/ZeroShot/Pretrain/Random 可行率 | fig3 |
| ④ 同预算最优/首次可行 | fig4 |
| ⑤ FOMAML/FullMAML 性能-成本 | fig5 |
| ⑥ 任务族/约束/OOD 诊断 | fig6/fig7/fig8/fig9 |
| ⑦ 只读 VSPAERO 门禁 | fig10 |

- 分析器 fail-closed 校验（任一失败即 `S3_ANALYSIS_*` 错误）：schema 版本与字段集；run_config 与 prereg 绑定（prereg_id/digest/code_sha/family/task_ids/episode_bank/models 网格严格相等，SMOKE 例外按 §4.5）；记录计数与预算公式；逐 run 预算记账；data_boundary phase 标志（训练/适配/BO 排序阶段不得读 holdout truth，EVAL 阶段恰好一次）；物理调用 = 0；负控 sha 与 seed；参考解封禁（run 阶段 references_sealed 不可读，analysis 才读）；确定性产物；图状态。
- 负控探针（fail-closed 测试，脚本随代码提交）：篡改 run_records 数值、删字段、改 fd gate status、改 data_manifest holdout 标志、改 prereg code_sha、改 episode bank sha，每类必须被拒绝（`S3_ANALYSIS_*`，exit code 2）。

## 6. 预注册（prereg）与冻结

- 文件：`research/concorde_metaopt/evidence/s3/s3_preregistration.json`（canonical JSON + LF），冻结提交后只读。
- 必需字段：schema_version、created_utc、family（family_id=F-QE-conflict-v1、formula_version=polyhedral-v1、FAMILY_SEED=20261107、HOLDOUT_SEED=20261108、package_version、family_package_sha256、task_ids_sha256、hash_vectors_sha256、task_fingerprint 算法与 20 个值、splits 计数 60/20/20/10/10）、references_sealed（每 task 的 f_ref/u* 证书 digest）、calibration（候选表、选中 delta1_base、中位可行比例、任务构造统计）、episode_bank（三 bank sha、条数 1,600×3、唯一 4,800、模型-episode 9,600）、models（fomaml/anil 的 config、episode_bank_sha、模型产物 sha —— 模型在 M2 训练后、prereg 冻结前生成，冻结时写真实 sha）、arms（五臂 + 方法声明 + RNG 合同）、budgets（B 集合、K、seeds、网格与 run 数）、endpoints（C1/C2 定义、comparator=S3-BO-FOMAML-OBJ、阈值、方向）、statistics（Wilcoxon 精确 tie-aware、零差处理、bootstrap 10k seed、Holm 2×2、决策映射）、figures（10 键）、negative_controls（10 任务、seed 公式、reference_kind）、campaign（授权 campaign 规则；v1.3 增补并行执行规则字符串：W=8、shard 规则、合并顺序、worker 编号不进 RNG/记录/digest）、ood（10 任务、偏移公式、seed）、determinism（子集与规则）、resource_limits（per_run 60s、peak 8192MB、total 7200s）、analysis_plan_digest、code_sha（7 文件）、physical_call_count=0、data_boundary、R-S3-01/R-S3-02 引用。
- 冻结流程（M2）：Lead 在 clean worktree 用 build→verify 两遍（写前/读后）生成 prereg；写入仓库并提交（单独 commit）；A5 独立核验（M2 gate）；核验通过后 Lead 签发正式 run 授权（M3），A2 执行。
### 6.1 哈希与摘要定义（A5 S3-M0-07、A5-S3M0R-02/03；唯一权威文本；固定向量见 §6.2）

- `canonical_json(obj)` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`；所有 `*_sha256` 均为小写 hex。
- `code_sha`：7 个文件（相对仓库根，按路径字典序）：`research/concorde_metaopt/meta_learning/m5_arms.py`、`research/concorde_metaopt/meta_learning/maml.py`、`research/concorde_metaopt/meta_learning/s3_analysis.py`、`research/concorde_metaopt/meta_learning/s3_figures.py`、`research/concorde_metaopt/meta_learning/s3_prereg.py`、`research/concorde_metaopt/meta_learning/s3_runner.py`、`research/concorde_metaopt/meta_learning/task_family.py`；对每个文件取 sha256(原始字节)，构造行 `f"{path}\t{hex}"`，按 path 排序，`"\n".join(lines)`（末尾无换行），再取 sha256。
- `analysis_code_sha`：`s3_analysis.py`、`s3_figures.py` 两文件（仓库相对路径按字典序），行算法与 `code_sha` 相同。
- `task_ids_sha256`：`sorted(task_ids)` 以 `"\n"` join（末尾无换行）后取 sha256。
- `task_fingerprint`：`sha256(canonical_json({family_id, formula_version, task_id, seed, params}))[:16]`；`params={a,c,b1,b2,delta1,delta2,m2}`。
- `analysis_plan_digest`：`sha256(canonical_json({endpoints, statistics, figures, analysis_code_sha}))`；inputs 见 §5.1/§5.2/§5.3。
- `record_digest`：记录去掉 `record_digest` 键后 canonical_json 的 sha256；`episode_digest` 同理；`history_digest` = 按记录顺序 join 各 `record_digest` 的 `"\n"` 后 sha256。
- `prereg_digest`：prereg 去掉 `prereg_id`/`prereg_digest` 后 canonical_json 的 sha256。
- `family_package_sha256` / `references_sealed_sha256` / `episode_bank_sha256` / `model_sha256` / `fd_gate_sha256` / `hash_vectors_sha256`：对应文件原始字节的 sha256（不重编码）。
- `package_sha256`（M5 打包用，不写入 prereg）：`research/concorde_metaopt/evidence/s3/` 下全部文件（排除 `PACKAGE_MANIFEST.json` 与 `SHA256SUMS.txt`，relpath 相对该目录），行 `f"{relpath}\t{sha256(原始字节)}"` 按 relpath 排序后 `"\n".join` 再 sha256；包内含 `hash_vectors.json` 本身。

### 6.2 哈希固定向量（随计划提交）

- 文件：`research/concorde_metaopt/evidence/s3/hash_vectors.json`；当前提交版本 12,472 B、raw sha256 `bde487fb6ed49768ca76e328a31c0efab77d2bd39d41c0ac99def4bb8e876203`。
- A5-S3M0R2-01 处置（v1.2a）：V11（`family_package_sha256`）的输入是族包文件的原始字节，无法在 JSON 内无损内嵌，故该向量不含 `canonical_payload`；其 `input` 记录被测快照标识，校验方式为对所指原始字节取 sha256。
- A5-S3M0R2-02 处置（v1.2a）：V02/V03 的 `files` 映射是为验证行算法而构造的固定输入（不代表仓库当前真实代码）；M1 测试必须分开两类断言：(i) 用向量内 `files` 复算 `canonical_payload`/`expected_sha256` 验证算法；(ii) 用仓库真实 7 个代码文件重算 `code_sha`/`analysis_code_sha` 并断言与 prereg 记录一致。
- 顶层：`schema_version=p4ra-s3-hash-vectors-1`、`generated_utc`、`algorithms`（§6.1 规则的结构化副本）、`vectors`（V01..V11，每项含 input、精确中间串 `canonical_payload`、`expected_sha256`）、`self_check`（all_ok）。
- 覆盖：canonical_json、code_sha（7 文件合成）、analysis_code_sha、task_fingerprint、task_ids_sha256、analysis_plan_digest、package_sha256、prereg_digest、record_digest、episode_digest、family_package_sha256。
- 该文件 sha256 写入 prereg 的 `frozen_package.hash_vectors_sha256`；若其字节变化而代码未变，prereg 冻结前必须重新签发向量文件并记录原因。

## 7. 写域、只读边界与角色

| 路径 | 写者 | 说明 |
|---|---|---|
| `research/concorde_metaopt/meta_learning/task_family.py` | A1 | 追加 F-QE-conflict-v1（M0R 后） |
| `research/concorde_metaopt/meta_learning/maml.py` | A1 | ANIL head_only + FD 门 |
| `research/concorde_metaopt/meta_learning/m5_arms.py` | A1 | S3 五臂 + 联合评分 + RNG 合同 |
| `research/concorde_metaopt/meta_learning/s3_runner.py`、`s3_prereg.py` | A1 | 新建 |
| `research/concorde_metaopt/meta_learning/s3_analysis.py`、`s3_figures.py` | A6 | 新建 |
| `research/concorde_metaopt/tests/test_s3_*.py`、`test_maml_anil.py` | A1/A6 | 新建 |
| `research/concorde_metaopt/evidence/s3/**` | Lead（冻结/打包） | 模型、prereg、gate、正式 run 证据 |
| `docs/planning/p4_route_a_s3_execution_plan_*.md`、`docs/reviews/**` | Lead | 本计划与审阅归档 |

- 只读：旧 M2/M5/M6、S0-2..S0-7、S1、S2 全部证据与 prereg；`optimization_runs/**` 历史；`main` 分支；PR #3/#6。
- 禁止：任何 VSPAERO/SU2/RCAIDE/OpenVSP 求解器启动；RCAIDE fallback/Mission；网络下载；写 GitHub（除 Lead 回执）；合并 main；新开 PR。
- 角色：A1 实现 runner/arm/family/maml；A6 analytics/figures；A2 正式 run 执行；A3 隔离/哈希/只读审计；A5 设计/代码/prereg/结果/打包复核；A4 需求矩阵与回执草稿；Lead 计划、裁决、prereg 冻结、授权、唯一 GitHub 发布者。


## 8. 测试与验收（M1 前必须全部通过）

- 单元测试（新增，目标 >= 55 tests）：
  1. 族几何：构造断言（box、g1(c)=δ1、g2(u*)=−m2、KKT<=1e-6、u* 在 box 内、regret>0）、参考证书可复算、task_fingerprint 固定向量、OOD 偏移公式与 ood_flag、负控制置换确定性与 seed 公式。
  2. 校准：候选表 {0.20,0.22,0.25} 在 meta_validation 上重算可复现、选中规则（中位可行比例 ∈[0.02,0.50] 且 minpts>=1 且 20 任务全构造成功）判定函数。
  3. 随机流：shared_candidate_pool/shared_initial_designs/BO seed/DE seed 公式固定向量；四臂在相同 task/seed 下 `(engine_seed,candidate_pool_sha256,candidate_count,bo_config_sha256)` 四元组相等、`bo_engine_draws_sha256` 逐位相等、`bo_trace_first_divergence_index` 已记录；初始点不消耗引擎 RNG；不要求完整 trace 逐位一致。
  4. 臂与预算：五臂 B 记账、support 共享、克隆检测、diversity 规则（含 relaxed 分支）、五臂（含 RANDOM）统一执行 `d_norm>=0.10` 过滤，RANDOM 只在自己的共享候选序列内按索引取点；RANDOM 多样性单测。
  5. ANIL：head_only 与 first_order=False 互斥 fail-closed；body 内循环逐位冻结；外循环更新全部参数；与 FOMAML episode 逐位一致；K=0 不调内循环；9 条专项测试。
  6. FD 门：解析 vs 数值在容差内、篡改坐标 FAIL、ANIL body 冻结、K=0 等价、gate JSON schema 与 sha 稳定性。
  7. episode bank：3 bank 条数 1,600、sha 稳定、support/query 不重叠、K_train 50/50 交错、digest 固定向量。
  8. 哈希：canonical JSON、code_sha、task_fingerprint、record_digest、analysis_plan_digest、package_sha256、prereg_digest 的固定向量（与仓库内 `research/concorde_metaopt/evidence/s3/hash_vectors.json` 逐项一致）。
  9. 统计：Wilcoxon tie-aware 精确（含 ties/zeros/全零/n_eff<15 分支）、bootstrap CI 固定 seed、Holm 校正、决策映射（含 DIRECTION_INCONSISTENT/INCONCLUSIVE/NEGLIGIBLE_SIGNIFICANT）、固定测试向量。
  10. runner/analysis e2e（SMOKE）：run_experiment(SMOKE) → load → analyze 成功，产出 aggregate + CSV；负控 6 类篡改 fail-closed；schema 单源断言。
  11. 图：10 键齐全；缺数据 → NOT_RUN；中文标签/evidence_scope/数据源脚注存在；CSV 与 PNG 对应。
- 12. 并行执行与执行层（v1.3/v1.3a）：W∈{1,2,3,8} 固定向量（同一 run_key 集合 record_digest 序列一致）、shard 映射固定向量、worker 编号不进 RNG/记录/digest、execution_report v2 18 字段精确键集 + 负控（删/改名/多字段 fail-closed）、W=1 与串行逐位等价；**W=8 稳态试点门必须在 M2 执行且不可默认跳过**（§4.2.1，产物 w8_pilot_gate.json）；FORMAL 模型加载 + sha 篡改 fail-closed；FD 门按模型 32 坐标校验（FORMAL）/N 覆盖（SMOKE）。
- 回归：全量测试必须保持 `1174 + 新增` 全绿（skipped=1 仅 RealOpenVSPIntegrationTests），A1/A5 独立复跑一致；不得修改既有测试断言（除 A5 批准的 schema v2 适配）。
- 静态检查：禁止在 s3 代码/测试中出现求解器调用（vspaero/SU2/RCAIDE/OpenVSP）、网络、绝对路径、`random` 无 seed、`time.time()` 进入统计、`eval/exec`；`grep` 扫描 + 单测断言（A5 复核）。
- 公平性验收：同一 (task,budget,opt_seed,meta_seed) 下五臂 B/K/support/candidate pool/BO 配置一致；预算记账逐 run 校验；克隆检测可用；多样性指标记录。
- 分析器验收：对正式 run 产物重算端点与 aggregate 一致（容差 1e-12）；篡改探针全 fail-closed；决策映射固定向量；确定性重跑 aggregate byte-identical（排除 generated_utc）。

## 9. 交付物（全部中文，除代码/JSON 键名）

- 代码：§7 所列 7 个实现文件 + 测试文件；提交入 `research/p4-route-a-s3` 分支，不合并 main。
- 证据包：`research/concorde_metaopt/evidence/s3/`（family package、references_sealed、episode bank、模型、prereg、gate、正式 run、analysis、determinism、负控、OOD、审阅归档、README、PACKAGE_MANIFEST、SHA256SUMS）。
- 报告：`docs/reviews/p4_route_a_s3_formal_run_report_20261108.md`（中文，含方法、结果、10 图、门禁、边界、复现命令、哈希口径）。
- 审阅：A5 设计/代码/prereg/结果/打包复核、A3 隔离审计、A4 需求矩阵与回执草稿。
- GitHub：Issue #7 单条 S3 事实回执（仅 Lead）；不新开 Issue/PR；不合并 main。

## 10. 时间与资源计划（估算，非承诺）

| 阶段 | 内容 | 估算 |
|---|---|---|
| M0R | A5 v1.1 复审（限定 diff） | 0.5–1 h |
| M0R2 | A5 v1.2 复审（限定 diff：计划 + hash_vectors.json） | 0.5–1 h |
| M1 | A1/A6 实现 + 单测（并行）+ Lead 集成（2026-11-07T05:49Z 起） | 4–6 h |
| M2 | 模型训练（3×FOMAML + 3×ANIL，SMOKE 规模守护）+ 校准 + FD 门 + prereg 冻结 + A5 核验 | 1–2 h |
| M3 | Lead 授权 + A2 正式 run（<=2 h 硬截止）+ 确定性重跑 | 2–3 h |
| M4 | A5 结果复核 | 1–2 h |
| M5 | 证据包 + A3 审计 + A5 打包复核 | 1–2 h |
| M6 | A4 回执 + Lead 发布 + closeout | 0.5–1 h |

- 计算资源：仅 CPU；峰值内存 <= 8 GB；正式 run 总墙钟硬截止 7,200 s（campaign 并行墙钟）；训练（6 模型 × 200 step × 8 tasks × 64 query）预计 <= 30 min，M2 实测后写入资源账本。
- 并行执行实测与 W=8 稳态试点门（v1.3a）：bench_v13a 覆盖 5 臂 × 3 task × B∈{64,128}、共 30 runs，W=1 wall 177.817 / 176.431 s、W=8 wall 42.267 / 43.727 s，稳态吞吐 0.7098 / 0.6861 runs/s → 3,780 runs 外推 3,518.653–3,712.731 s（吞吐）/ 5,325.653–5,509.562 s（保守；run2 保守值落入 (5,400,7,200] 区间，由 R-S3-05B 书面接受，硬顶 7,200 s 不变）；R-S3-05B 判定与预算接受见 §4.2.1；M2 必须通过 §4.2.1 试点门（产物 w8_pilot_gate.json）后才可冻结 prereg。
- 物理资源：0；不启动任何求解器；不访问网络。

## 11. 门禁（Gates，逐门书面结论）

| 门 | 内容 | 通过条件 | 执行者 |
|---|---|---|---|
| M0 | 设计审阅 | 实际：CHANGES_REQUESTED（S3-M0-01..16），由 M0R 修订门接续 | A5 |
| M0R | v1.1 修订复审 | 实际：CHANGES_REQUESTED（S3-M0R-01..09），由 M0R2 复审门接续 | A5 |
| M0R2 | v1.2 修订复审 | 实际：APPROVE_FOR_S3_CODE（f81f69b，限定 diff：计划 + hash_vectors.json）；v1.2a 文档勘误随 M1 审阅确认 | A5 |
| M0R3 | v1.3 执行层修订复审 | 实际：CHANGES_REQUESTED（2B/4M/2m/1i，对象 36e5820） | A5 |
| M0R3R | v1.3a 执行层重裁复审 | 待 A5（对象=本提交，限定 diff） | A5 |
| M1 | 实现 + 单测 + 集成 | A5 `APPROVE_FOR_S3_FORMAL`；全量测试绿；公平性/预算/哈希/e2e 测试齐备 | A5 |
| M2 | 校准 + 模型 + FD 门 + prereg 冻结 | 校准报告满足 §2.5 接受条件；FD 门 PASS；prereg build/verify 两遍；A5 `APPROVE_FOR_S3_RUN` | A5 |
| M2 附加门（v1.3a） | W=8 稳态试点门（§4.2.1） | w8_pilot_gate.json 全 PASS（外推 3,780 runs ≤5,400 s）；否则走 fallback 重裁 | A1/Lead |
| M3 | 正式 run 授权与执行 | Lead 书面授权（含 owner 指令复核）+ A2 执行（<=2 h、physical=0、无重试） | Lead/A2 |
| M4 | 结果复核 | A5 `APPROVE_FOR_S3_RECEIPT`；端点重算一致；负控/确定性/图合格 | A5 |
| M5 | 隔离与打包 | A3 `PASS*`；A5 `APPROVE_FOR_S3_RECEIPT_PACKAGE`；双哈希可复现 | A3/A5 |
| M6 | 回执与收尾 | Lead 发布 Issue #7 回执；A4 矩阵 v-final；closeout 记录 | Lead/A4 |

- 任何门未通过不得进入下一门；stage acceptance（阶段验收）由负责人另行签发，本计划不声称已获得。
- fail-closed：真实求解器调用、物理调用 >0、预算漏计、holdout truth 泄漏、旧件改写、全元目标 FD 失败、产物哈希不可复现 → 立即停止并报 A5/负责人。

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 选定 δ1 下可行率仍低（~2–10%），多数 run 无可行点 | 主端点 null 多、C2 失效 | 校准选择中位>=2%；null 披露；C1 为主；C2 仅在有可行点时推断；预注册允许 INCONCLUSIVE |
| 与 M5 类似，MAML 初始化可能损害可行率 | 结论为 HARM | 允许负结果；如实报告；不事后调参 |
| 代理 3 输出训练不稳定 | 端点噪声大 | FD 门、训练曲线、任务级聚类、3 模型重复、固定种子 |
| ANIL 实现错误（body 泄漏更新） | 消融无效 | body 冻结单测 + FD 门 + 逐位断言 |
| 离散可行率 ties/zeros 多 | 检验无效 | tie-aware 精确检验、敏感性分析、n_eff<15 → INCONCLUSIVE |
| 单核串行超时（实测 3,780 runs 串行 ≈23,400 s，> 7,200 s 硬顶） | 网格不完整 | R-S3-05A：W=8 campaign 并行（方法合同不变）+ M2 W=8 稳态试点门（外推 3,780 runs ≤5,400 s）+ R-S3-02 单值网格 + campaign 墙钟 7,200 s 与 sum_run_wall 28,000 s 双硬截止；fallback W=4/串行 25,200 s 需 Lead 书面重裁 |
| 运行超时 | 网格不完整 | 计时试点 + R-S3-02 降网格（预注册条件）+ 硬截止部分产物披露 |
| 旧件/主库被误改 | 违反边界 | 只读断言、A3 审计、独立 worktree、0 写仓库 run 目录（EXT） |
| 图/报告数字与 aggregate 不一致 | 回执失真 | 分析器自动生成表/图；A5 逐数核对；报告引用 aggregate sha |

## 13. 预算记账（合成评估层，非物理）

| 项 | 正式段 runs | 评估数 | 备注 |
|---|---|---|---|
| 主统计（R-S3-02 后） | 3,000 | 288,000 | B∈{64,128}，5 opt_seed |
| 负控制 | 300 | 28,800 | 1 meta_seed |
| OOD | 300 | 28,800 | 描述性 |
| 确定性 | 180 | 17,280 | 3 次 × 60 runs（每次 5,760） |
| 合计（正式段唯一网格） | 3,780 | 362,880 | campaign 墙钟 7,200 s；sum_run_wall 28,000 s |
| K-sweep 诊断 | 240 | 15,360 | M1，DEV_VALIDATION_ONLY，不进正式段 |
| 训练 | — | 4,800 唯一 episodes / 9,600 模型-episode（每模型 1,600） | 6 模型（3 FOMAML + 3 ANIL），计入 auxiliary_compute |
| FD 门 | — | 32 坐标 × 2 方向 × 2 模型 = 128 次 episode 重跑 | auxiliary_compute 披露 |

- R-S3-02 降网格（v1.3a 单值化）：正式段唯一合法网格 = 主 3,000/288,000、负控 300/28,800、OOD 300/28,800、确定性 180/17,280（3×60 runs，每次 5,760），合计 3,780/362,880；名义上限 6,900/662,400 不得执行；负控/OOD 不随 opt_seed 降级。
- 执行层并行（v1.3a）不改变 runs/eval 预算，只改变墙钟口径与并行验收：campaign 墙钟硬截止 7,200 s、sum_run_wall_seconds 硬上限 28,000 s（= 实测 23,400 s 的 1.20×）；M2 必须通过 §4.2.1 W=8 稳态试点门（w8_pilot_gate.json）；报告/回执必须同时披露 campaign 墙钟、sum_run_wall、单核等效 CPU 秒、M2 训练与 FD 门 auxiliary_compute（9,600 模型-episode + 128 次 episode 重跑，均属 M2）。
- 物理调用 = 0（fail-closed，prereg/run_summary 双处断言）；任何 >0 即整体作废。

## 14. 版本记录

| 版本 | 日期（UTC） | 对象 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-07 | commit 7bef3cf | 初版设计（12D 椭球族、9 图、Holm 2、6,000 runs） |
| v1.1 | 2026-11-07 | 本文件 | 处置 A5 S3-M0（1 blocker + 10 major + 5 minor）与 A4 DEV-01..09：线性多面体族、phase-scoped 数据边界、gap_to_reference/MAE、OOD 网格、7 文件 code_sha/analysis_plan_digest、episode/ANIL 合同、哈希 canonical 与固定向量、FD 门合同、fig10 图⑦、BO 随机流合同、Wilcoxon ties/zeros、R-S3-01 授权链、R-S3-02 降网格审批、10 图映射、预算记账 6,900 runs |
| v1.2 | 2026-11-07 | 本文件 + `research/concorde_metaopt/evidence/s3/hash_vectors.json` | 处置 A5 S3-M0R-01..09 与 A4 NEW-01..09：C1/C2 comparator 改 CON−OBJ、提交哈希固定向量与完整算法（7 文件 code_sha/analysis_code_sha/task_ids_sha256/package_sha256）、R-S3-02 算术更正 3,780/362,880、phase-scoped 与 campaign 语义、RANDOM 多样性统一、决策枚举互斥穷尽、radius_base→delta1_base、episode 消耗披露 |
| v1.2a | 2026-11-07 | 本文件 | 文档状态勘误（A5 S3-M0R2-01..04）：版本/状态/基线提交、§0.3/§10/§11 补 M0R2 门与实际结论、§6.2 注 V11 原始字节语义与 V02/V03 合成输入、§16 注 params_digest 旧承诺处置、§20 处置表；不改变执行合同 |
| v1.2b | 2026-11-07 | 本文件 | R-S3-03 评估记录 schema 冲突裁定：§2.4 语义清单映射到 §4.3 的 19 字段 schema；billable/cache_hit 由记录数与 source 分布断言；不新增字段、不改 A5 M0R2 已批准合同 |
| v1.3 | 2026-11-07 | 本文件 | R-S3-05 执行层并行合同：campaign 层 W=8 分片并行、W=1 与串行逐位等价、确定性扩展到 W∈{1,2,3,8}、计时与 execution_report 口径、prereg 不新增字段；附微基准与 R-S3-02 触发实证；A5 M0R3 判 CHANGES_REQUESTED（2B/4M/2m/1i） |
| v1.3a | 2026-11-07 | 本文件 | R-S3-05A + R-S3-06：执行层并行验收改吞吐外推 + M2 W=8 稳态试点门 + fallback + 线程固定；execution_report 唯一 schema v2 18 字段；sum_run_wall_seconds 与 28,000 s 硬上限；确定性 60-run 预注册子集；正式段单值 3,780/362,880；FORMAL 加载冻结模型不重训、FD 门每模型 32 坐标、FORMAL K=5；不改变方法合同/端点/统计 |

## 15. Issue #7 对齐表

| Issue #7 要求 | 本计划位置 |
|---|---|
| §1 S1/S2 验收后条件开启 S3 | R-S3-01（§0.1、§17） |
| §2 联合约束感知初始化（f 与 g<=0 联合打分、约束尺度/可行性排序） | §3.1/§3.2（S_joint、g_scale 归一化、OBJ vs CON 臂） |
| §2 ANIL 低价消融 | §3.1/§4.1（ANIL 臂 + head-only 适配 + 成本比较） |
| §2 Meta-SGD 仅报告证明必要时另审批 | §3.2（显式排除） |
| §2 新族（目标最优与可行域中心不重合、解析参考解可验证） | §2.1/§2.2（F-QE-conflict-v1、KKT 证书、conflict_ratio） |
| §2 初始点多样性 | §3.2（d_norm>=0.10，Wave A） |
| §2 旧 F-QE-feasible-v2 保留只读 | §7（只读边界） |
| §2 预注册盲测不可事后调整 | §6（冻结流程、R-S3-02 预授权条件） |
| §4 主端点四量 + RMSE/MAE | §5.1/§5.2（映射与降级理由） |
| §4 任务为一级统计单位 | §5.2 |
| §4 多重比较校正 / paired CI | §5.2（Holm 2×2、bootstrap 10k） |
| §4 中文图七类 | §5.3/§5.4（10 键映射） |
| §4 Leader 负责 S0→S3 阶段批准 | §7/§11（门禁与授权链） |
| §4 每阶段 A5 APPROVE 才放行 | §11 |
| §4 fail-closed 条件 | §11/§12 |
| §4 旧 PR#3/#6 不合并 main | §7（禁止） |
| §4 阶段验收非本 Issue 授权 | §0.1/§11（NOT_ISSUED） |

## 16. A5 S3-M0 findings 处置（v1.1）

| id | 严重度 | 处置 |
|---|---|---|
| S3-M0-01 | blocker | §2.1 改为线性多面体族（12 维设计、2 个线性约束，解析 u*/f_ref，冲突比 δ1），12D 椭球弃用；§2.5 候选 {0.20,0.22,0.25}（探针：median 0.0938–0.1484，minpts>=1，20 任务构造成功 100%） |
| S3-M0-02 | major | §5.1 定义 gap_to_reference/RMSE/MAE/first_feasible；四端点映射与降级理由写入 prereg 与回执 |
| S3-M0-03 | major | §2.3/§4.3 采用 phase-scoped 标志：训练/适配/BO 排序 holdout_truth_read=false；EVAL 阶段恰好一次 read_for_evaluation=true；不照搬 S2 holdout_metrics_read=false；负控/OOD/DET 段同规则 |
| S3-M0-04 | major | §2.2 OOD 定义（δ1+0.05、b1 扰动 0.30、seed 公式、ood_flag 不进特征、参考证书）；§4.2 OOD 300 runs/28,800；fig7 |
| S3-M0-05 | major | §6 code_sha 7 文件（含 s3_analysis/s3_figures）；明确禁止 s3_arms.py；analysis_plan_digest 定义 |
| S3-M0-06 | major | §4.1 episode seed/索引/50-50/digest/bank sha；ANIL 参数分区、body 冻结内循环、外循环更新全部参数、与 FOMAML 同 episode、SMOKE 与单测 |
| S3-M0-07 | major | §6 哈希 canonical 与 8 个摘要定义 + 固定测试向量（EXT hash_vectors.json，单测匹配） |
| S3-M0-08 | major | §4.4 FD 门完整合同（模型、32 坐标、eps/tol、中心差分、episode、产物、错误码、时点、auxiliary_compute、负控） |
| S3-M0-09 | major | §5.3 新增 fig10_vspaero_gate_status（只读归档门禁状态，不启求解器） |
| S3-M0-10 | major | §3.1 随机流合同（BO seed 不含 arm/budget、候选池共享、初始 3 点不耗 RNG、轨迹逐位一致单测、LEGACY_BO_ARM） |
| S3-M0-11 | major | §5.2 tie-aware 精确符号翻转、零差丢弃并报 n_zero、Pratt 与置换敏感性、n_eff<15→INCONCLUSIVE、固定向量 |
| S3-M0-12 | minor | §4.2 确定性 300 runs/3 次（100/次）与 R-S3-02 联动（60/次、180 总）|
| S3-M0-13 | minor | §4.2 负控制 1 meta_seed 理由 + 披露不用于跨模型比较 |
| S3-M0-14 | minor | §4.2 K-sweep 240 runs/15,360 evals（4 task×5 臂×B=64×3 opt×1 meta×4 K），DEV_VALIDATION_ONLY，fig2 数据源；未执行则图 NOT_RUN |
| S3-M0-15 | minor | §6 task_fingerprint 算法与固定向量 |
| S3-M0-16 | minor | §2.2 负控制 seed 派生公式（sha256）与固定向量 |

注（v1.2a，A5-S3M0R2-04）：S3-M0-07 行所述 `params_digest`/`reference_cert_digests` 为 v1.0 旧承诺，未在 §6.1 单列，现不新增；params 由 `task_fingerprint` 覆盖，参考证书完整性由 `references_sealed_sha256`（原始字节）承担。

## 17. Lead 裁决与 A4 DEV 处置

- **R-S3-01（S3 授权链）**：Issue #7 正文授权路线 A“算法代码 + 全合成解析任务的训练与正式离线对照（physical_call_count=0 硬隔离）”，§2 将 S3 列为“S1/S2 验收后条件开启”，§4 明确“Leader 负责 S0→S3 阶段批准”。S1、S2 均已完成并经 A5 APPROVE 与回执发布，Issue #7 无相反指令。据此裁决：(a) S3 的 M0–M2（设计、代码、单测、校准、prereg 冻结）在 Issue #7 授权范围内推进，不需要新的负责人预算；(b) M3 正式 run 前 Lead 必须再次复核 Issue #7/#4 是否有相反指令，确认后签发书面授权，并在授权中写明依据；(c) S3 阶段验收仍由负责人签发，本计划与回执不得声称已获阶段验收；(d) 若负责人发布任何相反指令，S3 立即停止；(e) S2 closeout 中“S3 需负责人书面授权”的保守表述以本裁决为准并记录于回执。
- **R-S3-02（降网格审批）**：若 M2 计时试点外推正式段 > 5,400 s，Lead 在 prereg 冻结前书面签发 R-S3-02，按 §4.2 降 opt_seed 10→5；该条件在 v1.1 中预先写明，A5 M2 核验，冻结后不得再降级；若不触发则必须保持 10 opt_seed。
- A4 DEV-01 → R-S3-01；(DEV-02/03/04) → §5.1；(DEV-05) → R-S3-02 与 §4.2；(DEV-06) → §3.2 排除；(DEV-07) → §3.2 Wave A 多样性；(DEV-08) → §5.2 决策映射；(DEV-09) → 头部状态与 §0.1 一致（v1.1 为设计修订、代码未开始、A5 M0R 待审；v1.2 处置见 §18/§19）。
- **R-S3-03（评估记录 schema 冲突裁定，v1.2b）**：A4/Lead 核查发现 §2.4 的逐条字段列表（eval_index/design_u/objective/constraints/valid/cache_hit/billable/phase/synthetic）与 §4.3 及 s3_prereg.py 的 19 字段 schema 命名不一致。裁定：**§4.3 + s3_prereg.py 为唯一权威 schema**；§2.4 列表为语义清单（映射见修订后的 §2.4 条目），不新增字段；`billable` 由记录数=B 与 `source` 分布（support 5 / initial 3 / search B-8）断言；`cache_hit` 仅在 run 内部处理，若发生重复访问须在 `scope_notes` 披露；本裁定不改变 A5 M0R2 已批准的 19 字段合同，A5 在 M1 代码审阅时确认。
- 旧件只读、0 物理、不合并 main、仅 Lead 写 GitHub 的边界贯穿全阶段；违反即 fail-closed。

## 18. A5 S3-M0R findings 处置（v1.2）

| id | 严重度 | 处置 |
|---|---|---|
| S3-M0R-01 | blocker | §5.2 C1/C2 comparator 改为 FOMAML-CON − FOMAML-OBJ（与 §1.3 H0 一致）；RANDOM/DE 仅描述；新增 comparator 单测与 `FAILED_COMPARATOR_MISMATCH`；§1.3/§5.2/fig3/fig4/prereg 同步 |
| S3-M0R-02 | major | 提交 `research/concorde_metaopt/evidence/s3/hash_vectors.json`（12,472 B，sha bde487fb…）；§6.1 固定算法；fingerprint 统一定义；`analysis_code_sha`/`task_ids_sha256` 已定义；删除 §6.2 旧引用 |
| S3-M0R-03 | major | §6.1 枚举 7 文件 code_sha、analysis_code_sha（2 文件）、package_sha256 的精确包含清单与排除项 |
| S3-M0R-04 | major | §4.2/§13 R-S3-02 改为 3,780 runs/362,880 evals；负控/OOD 保持 300/28,800；旧 R-S3-02 算术行已删除（A5-S3M0R-04） |
| S3-M0R-05 | major | §2.3 重写 phase-scoped 标志（`support_truth_read`）；query truth 仅端点读取一次；每 task 一次授权评估 campaign（campaign_authorization_id/utc） |
| S3-M0R-06 | major | §3.2/§8 五臂统一 `d_norm>=0.10`；RANDOM 仅在自己的候选序列内取点，不再豁免；RANDOM 多样性单测 |
| S3-M0R-07 | major | §1.3/§5.2 改为互斥穷尽判定表 + 总体唯一优先级 + 固定查表函数 + 3×3 组合单测 |
| S3-M0R-08 | minor | §6.1 `radius_base` → `delta1_base`；`w/r` 残留清除 |
| S3-M0R-09 | minor | §3.2/§13 披露唯一 4,800 episodes 与 9,600 模型-episode，计入 auxiliary_compute |

## 19. A4 矩阵 v1.1 NEW findings 处置（v1.2）

| id | 严重度 | 处置 |
|---|---|---|
| NEW-01 / NEW-09 | major | `task_fingerprint` 统一为 §2.2/§6.1 单一定义（params={a,c,b1,b2,delta1,delta2,m2}），删除不存在的 §6.2 引用 |
| NEW-02 | major | §2.1 regret 更正为 `f(u_star) - f(c) = delta1^2 / S > 0` |
| NEW-03 | major | 见 S3-M0R-05：phase-scoped + campaign 语义重写 |
| NEW-04 | major | §3.1/§8 BO 一致性改为 `(engine_seed,candidate_pool_sha256,candidate_count,bo_config_sha256)` 四元组 + `bo_engine_draws_sha256` + `bo_trace_first_divergence_index`；不要求完整 trace 逐位一致 |
| NEW-05 | major | 见 S3-M0R-06：RANDOM 统一多样性规则 |
| NEW-06 | major | 见 S3-M0R-07：决策枚举互斥穷尽 |
| NEW-07 | major | 见 S3-M0R-02/03：`analysis_code_sha` 已定义 |
| NEW-08 | major | 见 S3-M0R-08：radius_base 与 w/r 清除 |

## 20. A5 S3-M0R2 findings 处置（v1.2a）

| id | 严重度 | 处置 |
|---|---|---|
| A5-S3M0R2-01 | minor | §6.2 增注 V11（family_package_sha256）原始字节语义：不含 canonical_payload 为设计选择，校验方式为对所指原始字节取 sha256；不改 hash_vectors.json（避免字节变化导致 prereg 冻结前重新签发） |
| A5-S3M0R2-02 | minor | §6.2 增注 V02/V03 的 files 为合成固定输入；M1 测试分两类：(i) 向量算法自检；(ii) 用仓库真实 7 个代码文件重算 code_sha/analysis_code_sha 并与 prereg 记录一致（A5 明确要求） |
| A5-S3M0R2-03 | minor | 本文件 L4/L5/L8 状态更新；§0.3/§10/§11 补 M0R2 门与实际结论；§14 增 v1.2a 行 |
| A5-S3M0R2-04 | observation | §16 注：params_digest/reference_cert_digests 为旧承诺，以 §6.1 实际枚举为准，不新增摘要 |
| R-S3-03 | major（Lead 发现，v1.2b） | §2.4 逐条字段列表与 §4.3/s3_prereg.py 19 字段 schema 命名冲突 → 裁定 §4.3/s3_prereg 为唯一 schema；§2.4 改为语义映射；billable 校验记录数=B 与 source 分布；cache_hit 仅内部处理并在 scope_notes 披露；A5 M1 代码审阅确认 |

## 21. Lead 裁决 R-S3-05 处置（v1.3）

| id | 严重度 | 处置 |
|---|---|---|
| R-S3-05 | major（进度/预算，Lead 发现） | 串行实测 6,900 runs ≈42,700 s，超 7,200 s 硬顶 6.3×；裁决执行层并行：campaign 层 W=8、shard 规则固定、worker 编号不进 RNG/记录/digest、W=1 与串行逐位等价、确定性扩展到 W∈{1,2,3,8}；方法合同（臂/评分/BO/candidate/pool/初始点/support/预算/K/端点/统计/schema）不变 |
| R-S3-05-R1 | — | 计时口径：单 run 子进程内 wall/peak；父进程 campaign 墙钟、total_cpu_seconds、max_run_wall、max_peak；7,200 s 解释为 campaign 并行墙钟；per_run 60 s/8,192 MB 不变 |
| R-S3-05-R2 | — | 产物：新增 execution_report.json（schema p4ra-s3-execution-report-v1，13 字段）并纳入 data_manifest.artifact_sha256；prereg 不新增字段，规则写入 campaign.rules 与 scope_notes（确定性文本） |
| R-S3-05-R3 | — | 披露：报告/回执/README 必须写「W=8 并行、方法合同不变、campaign 墙钟≈2,940 s、单核等效 CPU 秒≈23,400 s、确定性子集已验证」；不得把并行墙钟当单核计算量 |
| R-S3-05-R4 | — | 触发证据：8-run 微基准（W=1 49.542 s vs W=8 cold 27.968 s，compute-only 13.28 s）、record_digest 逐位一致、8 worker 峰值上界 2,289.8 MB；保留 A1 的 bench/parallel_microbench.json 作为 M2/回执附件引用 |
| R-S3-05-R5 | — | 门禁：本 v1.3 计划须经 A5 M0R3 限定 diff 批准（APPROVE_FOR_S3_CODE_AMENDED）后方可作为 M1 基线；M1 代码审阅必须核对 W 等价测试与 execution_report schema |
| R-S3-05A | major（A5 M0R3 B02/M03-M06/-m07/-m08 处置） | 并行验收改吞吐外推（3,780 runs 外推 ≤5,400 s）、M2 W=8 稳态试点门、fallback、线程固定、确定性 60-run 预注册子集、sum_run_wall_limit_s=28,000、正式段单值 3,780；文件 <EXT>/p4-route-a/lead/s3/R-S3-05A_parallel_acceptance_ruling.md（8,346 B sha 8e2eb26e…） |
| R-S3-05A-B01 | blocker（A5 M0R3） | execution_report 唯一 schema v2、18 字段（§4.2），写入/校验/负控/data_manifest 绑定；旧 v1 10/13/16 字段口径全部作废 |
| R-S3-05A-B02 | blocker（A5 M0R3） | W=8 验收改为吞吐外推 + M2 必过门（§4.2.1），不再要求墙钟 1/8±30% |
| R-S3-06 | — | FORMAL 加载冻结模型不重训（§4.1）；FD 门每模型 32 坐标、2 模型（§4.4）；FORMAL k_sweep=[5]（§3.3），[0,1,3,5] 属 M1 K-sweep 诊断（fig2 数据源）；文件 <EXT>/p4-route-a/lead/s3/R-S3-06_formal_model_gate_semantics.md（5,318 B sha fb86fb11…） |
| R-S3-05B | — | R-S3-05A 判据替换后 W=8 验收通过：30/30 record_digest 一致、峰值 2,449 MB、两次 wall 差 <20%；3,780 runs 吞吐外推 3,518.653–3,712.731 s，保守外推 5,325.653–5,509.562 s（run2 保守值落入 (5,400,7,200]，由 R-S3-05B 书面接受）；6,900 名义网格不可执行（保守 10,057 s > 7,200 s），3,780/362,880 为唯一正式网格；证据 evidence/s3/bench/bench_v13a.json 与 bench_v13a_run2.json；文件 <EXT>/p4-route-a/lead/s3/R-S3-05B_parallel_acceptance_decision.md |
| R-S3-07 | — | FORMAL 不训练模型：run record_counts.train=0、无 train 行；M2 训练 1,200 条属 M2 证据；FD 门固定路径并纳入 package_sha256、run_config 写 sha256/coordinates_per_model=32/coordinates_total=64；model_manifest 复制+verification，不新增 prereg 字段；文件 <EXT>/p4-route-a/lead/s3/R-S3-07_formal_train_gate_binding.md（4,495 B sha 73171f7d…） |
