# P4 路线 A 分阶段针对性改进实施计划（D-P4-003）

- 版本：V1.0（2026-11-05）；语言：中文。
- 性质：**正式启动的算法代码与合成任务离线改进计划**，非真实航空优化授权。
- 执行入口：新建 D-P4-003 Issue；历史 [Issue #5](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/5) 和 [PR #6](https://github.com/QingYangJin/RCAIDE_Supersonic/pull/6) 只读作为算法基线。
- 新开发分支：`research/p4-route-a-improvements`，从 `research/p4-meta-learning` @ `ff6280f7b1c0cb98ebcc31478ffd14858481b711` 分出，以独立干净工作树开发；不得向 main 直接合并。
- 并行气动：只继续 OpenVSP 3.55.0 / VSPAERO 7.2.2 的既有验证方法，原 [Issue #4](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/4) 归口；**暂停 RCAIDE 回退/真实 Mission 评价及其B类预算启用**。

## 0. 事实基线：严格区分已经完成与尚未证明

1. M5 run `p4-meta-m5-formal-20261104T1018Z`：合成解析任务 `F-QE-feasible-v2`，4,800 runs、460,800次合成评价、`physical_call_count=0`。MAML 零样本初始化相对于随机 BO 的 `best_feasible_value` 无显著优势；在 meta_test B=64/128 的 `feasible_hit_rate` 配对差约 −0.01526/−0.01228，Holm 校正显著，方向更差。
2. M6 run `p4-m6-formal-20261105T0118Z`：3,600条适应结果、10,800次适应流程执行（含三次确定性复跑，并非互异物理样本）。同分布 K=5 标准化 query RMSE：MAML≈1.07116、普通预训练≈1.05337、随机≈1.09217；MAML 较普通预训练显著更差；OOD 因难度不匹配 `CONFOUNDED`。
3. 当前 `meta_learning/m5_arms.py`：`run_m5_bo_arm()` 调用 `score_m5_init_designs()` 不提供目标任务支持集，默认 `k_shot=0`；M1/M6 的 K-shot 适应虽然已实现，**未闭合进入正式 BO 初始化**。M5 代理采用统一常规 BO 后端，仅改变初始设计。
4. M5/M6 的外部评审 `APPROVE_FOR_ISSUE5_RECEIPT` 是软件/证据交付批准，不是物理验证、优化正向结论或二阶算法批准。归档实验不可改写/补跑覆盖。
5. VSPAERO D-12D-005 A类已经14/20启动，A线关闭剩余6次且不结转；数值内部一致，`LF-M2.02=NOT_VALIDATED`；`CDtot/CDo`仍非独立验证的真实整机阻力；B/RCAIDE 0/12 未启动，本计划明确不启用。

## 1. 总体目标与研究问题

路线 A 只改变**元学习响应代理初始化/目标任务适应/普通约束BO初始选点**，不修改常规 BO 采集策略，也不开展路线 B 的 MetaBO/FSAF 策略学习。检验三个递进问题：

- Q1：当目标任务只有 K 个已评价样本时，MAML 是否比普通预训练/随机模型更准确地拟合目标和约束？
- Q2：将适应后的代理用于初始选点，能否在**相同合成函数评价总预算**下改善首次可行、可行命中和最优可行值？
- Q3：完整二阶 MAML 是否相较 FOMAML 产生可重复的性能/成本优势？如不能，应保留 FOMAML 并如实报告。

“二阶”提高的是所定义元目标的梯度忠实度，不保证响应预测更好，也不修复气动物理精度。

## 2. 阶段执行次序与硬门禁

### S0｜冻结基线、审查口径（先于所有算法变更）

- 固定代码来源 `ff6280f` 和 M2/M5/M6 三次历史运行的 `run_id/git_sha/config_hash/manifest`，提供只读不可变性校验；基线统计与负结果不得通过重跑覆盖。
- 检查旧 `preregistration.json` 的 `stopping_rules` 序列化为单字符数组等遗留缺陷：只在**新版本数据合同**修正并增加 schema 类型校验，旧冻结工件不修改；保存新的确定性重跑 digest/日志。
- 旧 M5/M6 holdout 已在报告中公开，**不能再把同一批任务当作改进版未见过的盲测集**。新方法通过新的任务分布版本/独立任务ID和预先冻结的独立 `meta_test` 做主结论；旧数据仅作诊断性复现与历史对照。
- 提交中文设计合同、风险清单、基线统计快照、各角色审查记录，确认新任务冻结边界后开始 S1。

### S1｜K-shot 到 BO 初始化闭环（最优先的核心改进）

1. 在现有 `adaptation.py` / `baseline_arms.predict_proxy_targets()` 上扩展受控入口。为 `m5_arms.score_m5_init_designs()` 增加 `support_features/support_targets/k_shot`（默认兼容旧 K=0），由 `m5_runner` 显式传入适应所需的**目标任务真实合成评价样本**，且不读取 query 标签、不能用冻结参考最优点替代真实支持观测。
2. **预算守恒**：对每组 B=64/128，先公共评价 K 个支持设计点（推荐 K∈{0,1,3,5}），所有臂共享相同的 `K` 观测；若规定BO总初始点为8个，则只由各代理或随机机制补充 `8-K` 个新点，BO余下 B−8 次评价。支持集标签必须计入评价预算，不可作为免费先验；`K=0`须与旧零样本代码一致。
3. **公平对照**：至少 Random-BO、Pretrain-Kshot-BO、FOMAML-ZeroShot-BO、FOMAML-Kshot-BO、DE；四个初始化路径必须可识别，固定任务/种子/候选池/评价预算，报告初始化重叠、额外代理训练/适应墙钟和缓存账。若某臂机制相同则标 clone 并排除因果推断。
4. **元训练适配样本匹配**：当前内循环常用完整128样本 support 池；新增与部署K一致的任务episode采样，比较 `K_train∈{5,10,混合K}`（K=0只作零样本消融），不在最终测试上选超参；独立记录梯度与收敛。
5. 通过独立代码审阅、泄漏负控、真实合成评价次数精确一致、`K=0`回归与 K>0 适应确实改变模型参数/初始选点的证明后，才执行新的预注册多种子合成任务正式实验。性能无提升也允许完成科学验收。

### S2｜完整二阶 MAML（Full MAML）与一阶公平对照

- 在 `maml.py` 另设 `algorithm=FOMAML|FULL_MAML`，保持旧 FOMAML 的 API/训练与产物不变。
- Full MAML 内循环采用可微分的函数式参数更新，`torch.autograd.grad(create_graph=True)`，不得对需要回传二阶链的参数使用 `tensor.data` 或等价断图写法；明确多步内循环图和随机种子。
- **梯度门禁**：区别于当前只在适应后参数处做中心差分，新的全元目标差分必须针对原始 `θ±ε` **重新完整运行内循环**，与 Full MAML 自动微分元梯度比较；增加K>1、网络微型规模、数值稳定性与二阶 Hessian-vector 基准。
- 同构同数据、相同训练任务查询、优化器和更新步数，对比 FOMAML 与 Full MAML 的少样本 query RMSE/MAE、最优可行值、可行率、首次可行、训练墙钟和峰值RAM；区别离线训练成本和在线函数评价成本。
- **S2 仅在 S1 验证和 A5 审查通过后开放**；Full MAML 不显著改善时保留低成本 FOMAML 作为主路线，不做“高阶必优”的性能宣传。

### S3｜定向消融：约束感知初始化与低成本适应（有条件）

- 在 S1/S2 之后审查 `g≤0` 的多约束代理、标签尺度和可行率劣势。先对比纯目标排序、目标+约束评分、任务内约束归一化、预留随机/多样性比例（候选池/代理误差预算可审计）；任何不确定度接口未标定则输出 `uncertainty=null`，不得以伪概率冒充可靠可行性。
- 用 `ANIL`（只适应输出层）作为低计算成本消融；若出现少步适应不足，再评估 Meta-SGD，**不默认叠加多个新算法**。
- 旧 `F-QE-feasible-v2` 将可行域中心与目标最优点一致，可能不代表目标与约束竞争：另建**解析参考解可审计、目标与约束冲突**的独立合成族；先开发校准/冻结方案，再给新盲测集作预注册推断，禁止事后筛选有利任务。
- S3 算法设计属于路线 A 的消融，禁止学习 BO 采集策略（路线 B 待另行授权）。

### S4｜航空数据接入（本Issue只做合同，不做真实优化）

- 只设计/测试版本化 `task_id/design_set/evaluator_id/fidelity/source_kind/physics_validation_status/solver_version/config_hash/constraints_g_le_zero/physical_call_count` 接口；`VSPAERO_INTERNAL_ONLY` 结果不能当已验证真值。
- 可使用合成 LF/HF 偏差函数演练数据流；不得调用 RCAIDE Mission、SU2、新 VSPAERO 真实算例或把其结果混进合成 `meta_test`。真实12D航空任务 BO/DE/MAML训练仍需另行批准物理预算及适用域。

## 3. 科学对照、统计与图表

- 每个阶段先使用 meta_train/meta_val 调参与代码门禁，冻结新 `family_version/task_fingerprint/pre-registration` 再打开独立 `meta_test`；同任务≥20（如研究目标需要增大），至少3个独立元训练seed和10个优化seed作为建议目标；以任务为一级配对/重抽样单位，避免把seed当独立任务放大显著性。
- 函数评价预算分层 B=64/128；主终点：`best_feasible_value/gap_to_reference/first_feasible_eval_index/feasible_hit_rate`，不可行结果保留null、同时绘制无可行run比例；补充 RMSE/MAE、代理评分时间、峰值内存、全部训练成本与可重复性。事先约定多重比较校正和失败规则。
- 必须至少生成中文图：（1）元训练/元验证损失与梯度校验；（2）K-shot 预测误差与适应步数；（3）ZeroShot/KShot/Pretrain/Random的可行率；（4）等预算最优可行值/首个可行点；（5）FOMAML vs Full MAML 预测/优化/时间/Pareto对照；（6）任务分布/约束与OOD匹配诊断；（7）VSPAERO（#4，仅已获真实证据）CL/CDi-网格密度、残差及门禁与预算。
- 提交 `summary.json`、`run_config.json`、`train_val_test_split.json`、`preregistration.json`、`training_history.csv`、`adaptation_results.csv`、`optimization_history.csv`、`statistics.csv`、`data_manifest.json`、`SHA256SUMS`、图数据与 PNG、中文 `docs/reviews` 科研报告；缺数据标 `NOT_RUN/NOT_VALIDATED`，不绘制虚构曲线。

## 4. 并行气动方向——VSPAERO 继续、RCAIDE 暂停

- 由 **Issue #4** 继续管理 VSPAERO 7.2.2：已证实标准翼与12D主翼当前求解器链路有有限/稳定、内部可重复结果，**只意味着 VSPAERO_INTERNAL_ONLY**；仍缺独立压力/升致阻力、尾迹与参考模型的物理有效性验证。特别是 `CDo/CDtot` 不得直接当真实阻力或燃油目标。
- 下一步先使用**零新增求解器**的历史数据审计：参考面积/气动力轴、主翼/垂尾/机身覆盖范围、尾迹节点与网格敏感性、升力/升致阻力口径、与已有 SU2 可比量分离；提出能提高物理可信性的最小新算例矩阵和明确停止条件。**现有A类14/20后剩余6已CLOSED，不能自动复活；新增 VSPAERO 实际求解要另列明确次数并获得负责人书面批准**。
- **暂停 RCAIDE 气动回退与 Mission 计算**：B类12次保持 LOCKED / NOT_TRIGGERED / NOT_EXECUTED；不得开发或启动 RCAIDE fallback evaluator、不得为不可信 VSPAERO 输出自动切换 RCAIDE、不得把旧RCAIDE经验油耗当新的validated标签。若将来重新考虑RCAIDE，须负责人新指令。
- 不扩大 SU2 或 WaveDrag 实际调用；机身/翼身修正 `BODY-CORR=BLOCKED`，物理验收未通过。

## 5. 工作机团队、审批与停机条件

| 角色 | 责任 |
|---|---|
| Leader | 按S0→S1→S2→S3与A5审查分段启动；协调 #4 的 VSPAERO 零求解整改；统一GitHub回执，控制无新物理预算 |
| A1 | K-shot→BO新接口、episode训练、二阶可微路径及单测；保留旧API |
| A2 | 预注册、同预算实验、多seed统计、图表脚本与数值重算，区分任务级统计和合成真值评价 |
| A3 | 独立干净worktree、Git SHA/manifest与历史运行原样保留；与主库未跟踪P5资料隔离 |
| A4 | 新Issue与#4/#5/#6之间的需求/门禁矩阵、中文计划与图表回执 |
| A5 | 独立检查泄漏、支持样本计费、二阶梯度真实性、克隆臂、统计公平性、非物理标签隔离，按阶段签PASS/CHANGES_REQUESTED |

- **本计划批准的是本机 CPU 上的代码编写、单元测试和合成解析任务离线实验**。每一阶段如需显著扩大训练资源、开启真实求解或改变旧版冻结工件，先提交新预算/变更申请，禁止自动扩大；没有结果时保持 IN_PROGRESS，不得假称完成。
- 任何阶段泄漏、梯度不一致、预算不一致、元测试后调参、主数据破坏、真实物理调用非零，应立即停止对应 run 并将原因写入 JSON/中文报告。
- 不合并 main，不删除/覆盖历史PR #3/#6；本 Issue 的成果单独PR审阅，以 `research/p4-meta-learning` 为基线，最终合并策略由负责人再确认。

## 6. 研究论文可用证据的三层结论

1. **机制**：比较“零样本预训练→K-shot可适应→BO初始化”的因果消融，解释为何此前M5可行率更差。
2. **梯度与成本**：FOMAML vs Full MAML vs（有条件）ANIL，报告精度/训练成本权衡；Full MAML 的更准确元梯度不意味着一定更好。
3. **应用边界**：合成任务上优化收益/失败、OOD任务转移范围、VSPAERO内部数值结果与物理门禁分离；不宣称已验证真实Concorde油耗或跨飞行任务迁移。

**最终目标不是让某算法必然胜出，而是得到独立可重复、便于论文撰写的正负对照结论。**
