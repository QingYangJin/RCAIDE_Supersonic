# D-NEXT-001 路线B：元采集策略（Meta-Acquisition）方法设计与首轮原型报告

- 状态：**设计完成，原型完成，结论 NOT_READY（不具备宣称"元采集优于标准约束 BO"的训练条件）**
- 分支：research/dnext001-b-meta-acquisition；工作树：D:/RCAIDE/dnext001/wt-a3
- 基线：ea8ad97833eb5ceab291faae643c141a2b219749（S3 封账 + 官方实施计划）
- **physical_call_count = 0**：本报告涉及的全部实验均为纯合成任务（source_kind = synthetic_analogue），未启动 VSPAERO / SU2 / RCAIDE Mission / WaveDrag，未读取任何冻结 run 目录。
- 本路线**未复用**路线A 的 WarmStartSampler 或 MAML 采样器（详见 §4.3），也不宣称 MetaBO 类方法一定胜出。

---

## 1. 问题定位与边界

Concorde 12 维真实评价闭环尚未接通（VSPAERO LF-M2.02 = NOT_VALIDATED、BODY-CORR = BLOCKED；X_cg = 16.821978 m 实为机翼 AC、几何全机 CG = 28.287395 m；136000 kg 是单巡航进入质量而几何 MTOW = 184880 kg）。因此路线B**不在真实物理后端上训练或评测**，而是：

1. 把"序贯约束 BO 的候选选择"形式化为一个元学习问题；
2. 用合成类比任务族提供可复现、零物理调用的离线轨迹；
3. 交付可运行的最小垂直切片与**诚实的负结果**，为将来接通真实评价后是否值得继续投入提供判据。

路线B 学的是 **序贯候选选择策略 πφ(x | D_t, task_context)**，不是初始点排序；与路线A（跨 BO/DE/PSO 热启动）在接口上正交，本轮不扩展 DE/PSO 策略学习，也不做 2×2 因子消融（须两条路线各自审查通过后另行立项）。

---

## 2. 形式化定义

### 2.1 状态（state）

第 t 步状态 s_t 由四部分组成，全部为闭环中**当时可见**的信息：

| 分量 | 内容 | 说明 |
|---|---|---|
| 历史 D_t | 已**实际评价**的 (x_i, y_i, g_i, status_i) | 只含 source="evaluated" 记录；代理/假标签在数据契约层直接拒绝 |
| 候选池 X_t | 固定 256 个候选的**坐标** | 池中不含任何标签，策略与特征函数从不读取池标签 |
| 预算 | 已评价数 n、剩余预算 (B−n)/B、可行点数 | 由历史派生 |
| 任务上下文 c | (dim/12, budget/64, synthetic_flag) | **显式排除 task_id 与 split**，避免任务身份泄漏 |

### 2.2 动作（action）

a_t ∈ { i : x_i ∈ X_t 且 x_i 未被评价 }，即从候选池选择一个尚未评价的设计。策略输出为候选评分向量 score_φ(s_t) ∈ R^{|X_t|}，动作为可用候选上的 argmax（已评价候选被屏蔽）。

### 2.3 奖励（reward）

单步奖励同时计"可行改进"和"评价成本"（RewardSpec：cost_weight = 0.05、first_feasible_bonus = 0.05）：

    r_t = − cost_weight / B
          + first_feasible_bonus · 1[首次得到可行点]
          + max(0, best_before − best_after) / improvement_scale

不可行或失败评价同样消耗一步预算并按上式扣成本——这正是把"评价成本"纳入奖励的目的。回合目标为 reward-to-go：G_t = Σ_{k≥t} γ^{k−t} r_k（本轮 γ = 1）。

### 2.4 序贯任务分布与划分

- 合成任务族：6 维解析二次型目标 + 3 条约束（x1 必须落在窄带 [0.38, 0.62]，且 x0 + x1 ≤ 1.15），最优点被限制在可行域内，故 f* = 0 可达、gap 可精确计算；x_last > 0.995 时伪造失败评价以检验 null 计账。
- 任务按 **task_id 前缀绝对隔离**：synth-train-00..05（6）、synth-val-00..02（3）、synth-test-00..03（4），构造时即校验互不重叠（重叠抛 LeakageError）。
- 训练阶段再**只在 train 任务内部**按任务 id 切分 fit/early-stop 验证集（本轮 fit = train-00/01/04/05，val = train-02/03）；val/test 划分任务从不参与训练或早停。

### 2.5 训练目标

离线数据中未被选中候选的真实标签不可观测，因此本轮采用**有偏 direct method**：最小化决策时刻的已实现回报回归误差

    L(φ) = E_{(s_t, G_t) ~ D_offline} [ ( score_φ(s_t)[a_t] − (G_t − target_mean) / target_std )² ]

不做事后反事实加权 / IPS（该已知偏差在报告与 NOT_READY 结论中显式标注）。策略结构为标准化特征 → 2 层 tanh MLP（hidden = 32）→ 标量评分，numpy 手写反向传播 + Adam，按验证任务 loss 早停（本轮 best_epoch = 8，best_val_loss = 0.6491）。

---

## 3. 轨迹来源与生成成本

| 项目 | 取值 |
|---|---|
| 行为策略 | 约束 EI、约束 UCB、约束 PI、均匀随机（4 种） |
| 任务 | 6 个 train 合成任务 |
| 种子 | 0, 1（每个 (任务, 行为, 种子) 一条轨迹） |
| 预算 | B = 12，固定初始点 n_init = 4（同任务+同种子下各臂共享） |
| 轨迹数 | 6 × 4 × 2 = 48 episodes |
| 决策记录数 | 384 条（每条 = 特征快照 + reward-to-go） |
| 生成成本 | CPU-only、无模型训练依赖；单次全流程（数据 + 训练 + 7 臂 × 7 任务评测）约数十秒 |
| 物理调用 | **0** |
| 数据 SHA256 | 09624c934a1c3fd800a8eb749e2190ebdd0fedd5c2b2ed618a8a2c1702d1045f（dataset.jsonl，manifest 校验） |

轨迹为**归档 replay 式**离线数据：生成后即冻结为 jsonl + manifest，训练与评测只读；manifest 记录 SHA256，读入时校验，篡改即抛错。

---

## 4. 实现骨架

### 4.1 代码结构（research/concorde_metaopt/route_b/）

| 模块 | 职责 |
|---|---|
| contracts.py | 数据契约与不变量：TaskContext / EvaluatedPoint / ObservationHistory / CandidatePool / RewardSpec；ProxyLabelError、LeakageError |
| synthetic_tasks.py | 合成类比任务族、确定性任务生成、任务划分、固定初始设计 |
| baselines.py | 自建 numpy GP 与标准约束采集 EI/UCB/PI（未复用路线A 采样器） |
| policy.py | 特征构造、MetaAcquisitionPolicy（可学习 acquisition_score）、RandomScorePolicy（负控）、select_candidate 统一入口 |
| trajectory_dataset/ | 离线轨迹生成、manifest/SHA256、按任务切分 |
| policy_train/ | direct-method 训练、任务级早停切分、报告 |
| policy_eval/ | 固定初始点闭环评测、任务级聚合、主比较与负控自检 |
| run_smoke.py | 端到端垂直切片入口 |

### 4.2 数据契约层的关键不变量

1. EvaluatedPoint.source 只允许 "evaluated"；任何代理/假标签构造即抛 ProxyLabelError。
2. ObservationHistory.append 拒绝非 EvaluatedPoint、拒绝重复设计、要求 eval_index == len(history)。
3. CandidatePool 校验坐标 ∈ [0, 1]，**不携带标签字段**。
4. TaskContext 拒绝 physical_call_count != 0。
5. context_features() 只返回 (dim/12, budget/64, synthetic_flag)，不含 task_id / split。

### 4.3 与路线A 的关系（显式声明）

本包**没有**复用路线A 的 WarmStartSampler / MAML 采样器，也没有把任何 A 线采样器改名包装；全部 GP、采集函数、特征与 MLP 均为路线B 自建。两路线共享的仅有仓库级工具（canonical_json、SHA256 约定、pytest 布局）。路线B 只围绕 BO 后端，不涉及 DE/PSO 策略学习。

---

## 5. 泄漏防护清单

| 风险 | 防护 | 对应测试 |
|---|---|---|
| 代理假标签进入 history | source 白名单，构造即抛错 | test_proxy_label_rejected |
| 策略看到未来评价 / 未选候选标签 | 特征只由前缀历史 + 候选坐标计算；决策记录可按前缀精确重算 | test_prefix_features_contain_no_future_labels |
| train/val/test 任务混用 | 任务 id 前缀隔离 + 构造期校验 + 训练期任务级切分 | test_training_task_isolation_and_policy_roundtrip、test_dataset_rejects_non_train_tasks |
| 数据集被悄然改写 | manifest SHA256 校验 | test_manifest_detects_tampering |
| 评测任务参与训练 | evaluate_arms / run_closed_loop 只接受 val/test | test_eval_rejects_train_tasks |
| 评测实现"作弊" | 未训练网络 / 随机评分负控 | test_negative_controls_and_inconclusive_verdict |

---

## 6. 评测协议与首轮结果

### 6.1 协议

同一任务上所有臂：**同一固定初始点**（种子绑定 task_id + eval seed，各臂共享）、同一候选池、同一预算 B = 12。统计单位 = 任务。指标：first_feasible_eval、feasible_hit_rate、best_feasible_value、gap_to_reference（相对 f* = 0）、null_fraction、total_reward。臂：learned / EI / UCB / PI / random / random_score / untrained。

### 6.2 测试任务结果（4 个 synth-test 任务，均值）

| 臂 | first_feasible_eval | feasible_hit_rate | best_feasible_value | gap_to_reference | null_fraction | total_reward |
|---|---|---|---|---|---|---|
| **learned** | 2.00 | 0.104 | 0.440 | 0.440 | 0.896 | 0.179 ± 0.309 |
| EI | 2.00 | 0.375 | 0.144 | 0.144 | 0.625 | 0.416 ± 0.426 |
| PI | 3.25 | 0.354 | 0.191 | 0.191 | 0.646 | 0.369 ± 0.352 |
| UCB | 3.50 | 0.208 | 0.299 | 0.299 | 0.792 | 0.266 ± 0.404 |
| random | 1.00 | 0.104 | 0.431 | 0.431 | 0.896 | 0.166 ± 0.317 |
| random_score（负控） | 1.00 | 0.104 | 0.431 | 0.431 | 0.896 | 0.166 ± 0.317 |
| untrained（负控） | 1.00 | 0.083 | 0.431 | 0.431 | 0.917 | 0.166 ± 0.317 |

验证任务（3 个 synth-val）趋势相同：learned 的 feasible_hit_rate = 0.111、total_reward = 0.357，均低于 EI / PI（0.417 / 0.504）。

### 6.3 主比较（learned − EI，test）

- total_reward：−0.237；feasible_hit_rate：−0.271；best_feasible_value：+0.296（越小越好，即劣于 EI）；first_feasible_eval：0.000。
- 判定：**INCONCLUSIVE**（4 个测试任务远不足以支撑统计结论），但描述性证据一致指向 learned **不如**标准约束 BO。
- 负控：random_score 与 random 同分布（差 0.0，符合预期）；untrained 不优于 random（差 0.0）→ 负控自检 PASS，未发现泄漏/作弊迹象。

### 6.4 诚实结论

1. 垂直切片可运行、可复现、零物理调用，负控通过；
2. 首轮 learned 策略在合成任务族上**没有**优于 EI / PI，甚至接近随机——这与 direct-method 的已知偏差、384 条轨迹的小样本、单一任务族都一致；
3. 因此本轮**不具备**宣称"路线B 元采集优于标准 BO"的训练条件，正式判定 **NOT_READY**；该负结果本身即为交付物，用于避免在真实评价接通前过度投入。

---

## 7. NOT_READY 判定与阻塞清单

| # | 阻塞原因 | 影响 | 解除条件 |
|---|---|---|---|
| 1 | Concorde 12D 真实评价闭环未接通（VSPAERO LF-M2.02 NOT_VALIDATED、BODY-CORR BLOCKED） | 只有 6D 合成二次型，任务族过窄 | 真实/归档 replay 评价可用 |
| 2 | 离线轨迹仅 384 条、来自 6 个合成任务 | 策略容量与泛化无法检验 | 真实任务轨迹 ≥ 数百 episodes 或大规模合成族 |
| 3 | direct method 未做反事实 / IPS 校正 | 回归目标有偏，学到的评分不保证最优 | 引入 IPS / 双重稳健或在线 RL 数据 |
| 4 | 测试任务仅 4 个 | 统计功效不足，主比较只能 INCONCLUSIVE | 每划分 ≥ 30 任务 |
| 5 | 单一合成任务族（二次型 + 窄带约束） | 结论无法外推到真实气动任务 | 多族任务或真实任务 |
| 6 | 超参未系统搜索（hidden、lr、top_k、特征集） | learned 未调优，比较不完全公平 | 固定调参预算下的任务级 CV |
| 7 | 未与路线A 联合做 2×2 消融 | 无法评估 A/B 互补性 | 两路线各自审查通过后立项 |

---

## 8. 公开方法正式对照（文献均经 arXiv 页面核实，未编造）

| 方法 / 文献 | 核心思想 | 与本文关系 |
|---|---|---|
| MetaBO — Volpp, Fröhlich, Fischer, Doerr, Falkner, Hutter, Daniel, "Meta-Learning Acquisition Functions for Transfer Learning in Bayesian Optimization", arXiv:1904.02642（ICLR 2020） | 用元学习直接学"采集函数"这一映射，跨任务迁移 | 本文 score_φ 的形式化与"学采集函数而非学代理"的定位与其同源；本轮未复现其回归/策略梯度训练细节 |
| FSAF — Wistuba, Grabocka, "Few-Shot Bayesian Optimization with Deep Kernel Surrogates", arXiv:2101.07667（ICLR 2021） | 少样本下用深度核替代 GP 核，任务级元学习 | 作为"任务分布 + 少样本迁移"参照；本文保留 GP 代理，仅把选择策略参数化 |
| RGPE — Feurer, Letham, Hutter, Bakshy, "Practical Transfer Learning for Bayesian Optimization", arXiv:1802.02219（2018） | 多任务代理的加权组合迁移 | 迁移代理参照；本文未实现 RGPE（后续基线建议） |
| PFNs4BO — Müller, Feurer, Hollmann, Hutter, "PFNs4BO: In-Context Learning for Bayesian Optimization", arXiv:2305.17535（ICML 2023, PMLR 202:25444–25470） | 用 PFN 在上下文中做 BO，无需逐任务拟合 | 现有最强 in-context 基线之一；本文未复现，仅作为未来对照 |
| 离线 RL 综述 — Levine, Kumar, Tucker, Fu, "Offline Reinforcement Learning: Tutorial, Review, and Perspectives on Open Problems", arXiv:2005.01643 | 离线数据的分布偏移与反事实评估 | 本文 direct-method 偏差与不宣称胜出的依据 |
| EI — Jones, Schonlau, Welch, J. Global Optim. 1998 | 期望改进 | 标准 BO 基线 |
| GP-UCB — Srinivas, Krause, Kakade, Seeger, ICML 2010 | 置信上界 | 标准 BO 基线（最小化取 −μ + βσ） |
| PI — Kushner, J. Basic Eng. 1964 | 改进概率 | 标准 BO 基线 |
| 约束 EI — Gardner 等, ICML 2014 | 可行概率加权的 EI | 本文约束 BO 基线的加权方式 |
| BO 教程 — Brochu, Cora, de Freitas, arXiv:1012.2599 | 综述 | 术语与协议参照 |

**不宣称**：MetaBO / FSAF 类方法在 Concorde 任务上一定胜出；本轮亦未复现上述方法的完整训练流程。

---

## 9. 与 2×2 因子消融、后续路线的关系

- 2×2 因子消融（A−/B−、A+/B−、A−/B+、A+/B+）须在两条路线**各自审查通过**后开展，本轮不启动；
- 路线B 下一轮的前置条件：真实/归档 replay 评价接通（解除 §7-1/2），并补齐 RGPE、PFNs4BO 等强基线；
- 若真实数据接通后 learned 仍不优于 EI/PI，则应在 B 线上记录负结论并转投 A 线热启动与 GPU 并行。

---

## 10. 复现命令

    cd D:/RCAIDE/dnext001/wt-a3
    & D:/RCAIDE/envs/RCAIDE/python.exe -m research.concorde_metaopt.route_b.run_smoke --out runs/dnext001_route_b/run_001
    & D:/RCAIDE/envs/RCAIDE/python.exe -m pytest research/concorde_metaopt/tests/test_route_b_contracts_policy.py research/concorde_metaopt/tests/test_route_b_training_eval.py -q

产物：runs/dnext001_route_b/run_001/（trajectory_dataset/、policy_train/、policy_eval_val/、policy_eval_test/、figures/route_b_arms_test.png、run_summary.json）。

---

## 11. 声明

- 本轮所有 run 均标注 source_kind = "synthetic_analogue"、physical_call_count = 0；
- 未读取/改写 S1/S2/S3 冻结产物、manifest、SHA 文件；未与旧 main/PR#3/#6/Issue#7/M2/M5/M6 结果混用；
- 不宣称 MetaBO 类方法一定胜出；NOT_READY 为如实判定。
