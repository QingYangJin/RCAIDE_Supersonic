# P4 路线A S1 需求矩阵（Issue #7 · S1 K-shot→BO 闭环 → 实现文件 / 测试 / 验收证据 / 状态）

> 文档性质：S1 需求到实现文件、测试与验收证据的映射表，供 Lead、A5、A6 与 A1 在 S1 实现前对齐口径；**S1 实现尚未开始、S1 formal run 尚未执行，本文件不含任何算法结果，不构成新的物理授权或预算批准**。
> 依据：Issue #7 正文（D-P4-003，§2 S1 四条与 §3–§4 约束，2026-11-05 读取）+ docs/planning/p4_route_a_stage_improvement_plan_20261105.md（V1.0，commit a331639e）+ docs/planning/p4_route_a_s1_execution_plan_20261105.md（v1.0，sha256 74ae668b18312f5a8c10fefcba2823ac254639faeab79cf05cb64ce01fbc085a）+ docs/planning/p4_route_a_s1_statistical_plan_20261105.md（v1.1，sha256 7d6ce0c24745fe56e24758d457ee5c1cc12acdb8eacc056aa5ae5538a6033ae6）+ docs/planning/p4_route_a_s0_design_contract.md（v1.1，sha256 3f622570b38a2013de1ed695457f721d8aa2584784c2a797addcedbb00ac1ebb）+ 冻结包 p4ra-s0-2-freeze-20261105T072500Z + A5 S0-2 复审 <EXT>/p4-route-a/a5/S0_2_A5_review_phase2.md（sha256 ea9b2eb708fa660fb84a913bc1b5f63624a7303337fff574ad2c4c05905068d8，APPROVE_FOR_S1_FORMAL）+ A3 S0-2 隔离审计 <EXT>/EXT/p4-route-a/a3/S0_2_phase2_isolation.md（sha256 23bac611159b76064a39789a27837e7e5c92e31a573585f2f137ef9aec92858d，PASS 11/11）+ S0 需求矩阵 v1.2。
> 读取时点：2026-11-05T16:48+08；S1 工作树 HEAD=43fcfc851525bd74935b20c85dfbea2d932e436e，branch research/p4-route-a-s1；仅 S1 执行计划未跟踪，S1 代码/测试文件均不存在。
> 状态口径：PENDING＝S1 实现、测试或证据尚未产生；NOT_RUN＝计划中的测试/运行尚未执行；BLOCKED＝依赖 A5 或 Lead 放行/授权；READ_ONLY_VERIFIED＝仅输入或历史事实经 A4 只读核对（不代表 S1 验收通过）。S1 formal=APPROVED 仅表示 S0-2 阶段门放行，不等于 S1 formal run 已获授权或已执行。

## 1. 当前状态与硬边界

| 检查项 | 当前事实 | 来源/证据 |
|---|---|---|
| S0-2 阶段门 | COMPLETE；A5 phase2 verdict=APPROVE_FOR_S1_FORMAL；0 blocker / 0 major / 8 minor；S1 formal=APPROVED（阶段放行） | A5 phase2 报告；Issue #7 回执 6653167378 |
| S1 实现 | **未开始**；s1_runner.py、s1_analysis.py、s1_figures.py、test_s1_runner.py、test_s1_analysis.py 均不存在 | A4 只读 ls/git ls-files，2026-11-05T16:48+08 |
| S1 正式 run | **未开始、未授权**；21,000 runs / 1,920,000 次合成评价仅为计划数 | S1 执行计划 v1.0；统计计划 v1.1 |
| K-shot 闭环缺口 | m5_arms.py 的 score_m5_init_designs() 无 support_features/support_targets 参数；run_m5_bo_arm() 硬编码 adaptation_k_shot=0（:623、:717）；默认 k_shot=0（:514） | 当前 HEAD 43fcfc8 只读核实 |
| 物理调用 | physical_call_count=0；S1 不启动 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag；Issue #4 物理门禁不变 | Issue #7 §3；A5 phase2 §7④ |
| 旧证据与 main | 旧 M2/M5/M6 只读；main 不合并；PR #3/#6 保持 open 不合并 | A3 phase2；SAFE-05 |
| 发布权限 | 仅 Lead 可发布 GitHub；A4 本任务只读，未评论/改 Issue/建 Issue | Issue #7 §4；A4 角色约束 |

> 结论：S1 目前只有**计划与冻结输入**，没有任何可验收的实现或结果。下文所有实现/测试/图表行均为计划映射，不得被引用为已完成证据。

## 2. S0-2 冻结输入（S1 只读基线）

| 冻结项 | 规范值 | 来源 |
|---|---|---|
| 冻结包 run_id | p4ra-s0-2-freeze-20261105T072500Z | freeze_summary.json |
| 创建时间 | 2026-11-05T07:25:00+00:00 | freeze_summary.json |
| git_sha | 766a59ce14c9edda7b9174b621eb0d6727bfe1b8 | freeze_summary.json |
| code_sha | c929609a1eb4d5c01cc4f94865ebdebb5fa7a1772fe8f4139a411cf7a8414f59（LF clean checkout） | freeze_summary.json；A5 phase2 §7⑥ |
| family_id / family_version | F-QE-feasible-v3 / p4ra-family-v3 | frozen_family.json；S0 合同 §3 |
| family_seed | 20261105 | frozen_family.json |
| family_fingerprint | e56e6921be6b94e6611a24618a6e331cd7e4417597926d089d71b00da8c1c0c3 | 冻结包；Issue #7 回执 |
| split_hash | cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae | 冻结包；Issue #7 回执 |
| prereg_digest | 6981f503…（完整值以 preregistration.json / digest_manifest.json 为准） | 冻结包；A5 phase2 |
| analysis_plan_digest | 37eee53c…（完整值以 analysis_plan/digest_manifest 为准） | 冻结包；A5 phase2 |
| radius_base / 校准状态 | 0.64 / CALIBRATED（A2 meta_train pooled 16/24=0.6667） | frozen_family.json；A2 校准；A5 phase2 |
| 五 split 与任务数 | meta_train 60 / meta_validation 20 / meta_test 20 / meta_test_ood 10 / negative_control 10；共 120 tasks | frozen_family.json；meta_task_split.json |
| 主统计范围 | 仅 meta_test 20 任务进入主统计；OOD/负控不入主分母 | S1 统计计划 §3 |
| 支持池/查询池 | support 128 / query 64（每任务） | S1 统计计划 §3 |
| 端点键 | 9 个 ENDPOINT_ROW_KEYS：best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate、first_feasible_in_support、first_feasible_after_support_index、feasible_hit_rate_non_support、n_nonnull、null_rate | family_v3.py:162；S1 执行计划 |
| 计划规模 | 21,000 runs；1,920,000 次合成评价；B∈{64,128}；K∈{0,1,3,5} | S1 统计计划 v1.1 |
| 物理调用 | 0 | Issue #7；A5 phase2 §7④ |

> 冻结包文件：README.md、SHA256SUMS.txt、budget_fairness_report.json、determinism_report.json、digest_manifest.json、freeze_summary.json、frozen_family.json、meta_task_split.json、preregistration.json、tasks.json、v3_isolation_report.json。

## 3. S1 需求矩阵（S1-01..S1-12）

| ID | 来源 | 要求与验收条件 | 实现文件（计划） | 测试/验收证据（计划） | 状态 | 责任/依赖 |
|---|---|---|---|---|---|---|
| S1-01 | Issue #7 §2 S1-1；执行计划 §2、§3.2；合同 §4.2 | K 次目标任务支持样本的特征与目标/约束标签进入内循环，用适应后代理评分；query 标签、解析最优点不可见；代理预测不得写入 BO 真实 observations；K=0 退化为旧行为 | s1_runner.py（新增）；m5_arms.py 的 score_m5_init_designs()/run_m5_bo_arm()（必须改）；adaptation.py/baseline_arms.py 作为只读复用 | test_s1_runner.py：support_features_enter_inner_loop、no_query_leakage、no_proxy_in_observations、K=0 regression；A5 代码审查 | PENDING（实现未开始） | A1；A5 审阅 |
| S1-02 | Issue #7 §2 S1-2；合同 §4.2；统计计划 §3 | B∈{64,128}、K∈{0,1,3,5}；五臂共享同一 K 次目标任务评价，K 次必须计入 B；每 run 满足 K+(8−K)+(B−8)=B；计划 21,000 runs / 1,920,000 评价；非物理代理时间单列 | s1_runner.py 网格构建与预算账；m5_arms.py 预算字段；run_records.jsonl | test_s1_runner.py：equal_budget_40_combinations、billable_equals_B、total_run_and_eval_counts；冻结包 budget_fairness_report.json 复用 | PENDING（实现未开始） | A1+A2；A5 复核 |
| S1-03 | Issue #7 §2 S1-2；合同 §4.2；A5 phase2 §7③ | 8 个初始点=K 个支持点+8−K 个新点；之后普通 BO B−8 次；DE 的 8−K 新点并入 population；K=0 复现旧初始化行为 | s1_runner.py 初始化路径；m5_arms.py 初始化记录；run_records.initial_designs | test_s1_runner.py：initial_designs_count_8、design_source_labels、K0_initialization_regression；run_records 可追溯 sha256 | PENDING（实现未开始） | A1；A2 复核 |
| S1-04 | Issue #7 §2 S1-3；A5 phase2 §7③ | 五臂 RAND-BO / PRETRAIN-KSHOT-BO / FOMAML-ZERO-BO / FOMAML-KSHOT-BO / DE；同任务、同种子、同候选池、同约束；仅初始化路径不同 | s1_runner.py arm registry；m5_arms.py 旧臂复用 | test_s1_runner.py：five_arms_configured、fairness_audit_same_task_seed_pool_constraints；公平性审计表 | PENDING（实现未开始） | A1+A2；A5 复核 |
| S1-05 | Issue #7 §2 S1-3；S1 执行计划 §3 | 克隆识别、缓存与 null 规则一致；K=0 的 FOMAML-KSHOT-BO 登记 CLONE_OF_FOMAML-ZERO-BO，排除因果推断；代理评分墙钟/缓存账单列 | s1_runner.py clone/cache 判定；run_records.identifiability/cost | test_s1_runner.py：clone_identification、K0_clone_excluded、cache_and_walltime_accounting、null_not_imputed | PENDING（实现未开始） | A1+A2；A5 复核 |
| S1-06 | Issue #7 §2 S1-3；执行计划 §3 | 训练 episode 支持样本数与部署 K 匹配（5/10 或混合 K）；旧 128 样本内循环仅作消融基线，不得冒充新 K-shot 闭环 | 训练/episode 采样路径；s1_runner.py 配置；adaptation.py 复用 | test_s1_runner.py：episode_support_count_matches_deploy_K、legacy_128_ablation_label；配置对照表 | PENDING（实现未开始） | A1+A2；A5 复核 |
| S1-07 | Issue #7 §2 S1-4；A5 phase2 §7①②④ | 先做零物理单测：query/任务泄漏负控、真实合成评价预算精确一致、K>0 确实改变模型参数与初始选点、失败路径 fail-closed；physical_call_count=0 | test_s1_runner.py；s1_runner.py 前置断言；s1_analysis.py 前置断言 | 全部单测通过日志；失败用例必须抛错/停止；physical guard 测试 | PENDING（实现未开始） | A1+A6；A5 审阅 |
| S1-08 | Issue #7 §2 S1-4；执行计划 §6；A5 phase2 §7② | 验证集小样本 pilot 通过后，A5 书面 APPROVE_FOR_S1_RUN 且 Lead 授权，才执行新独立 holdout；正式 meta_test 一次性打开，之后禁止调参/选臂/选终点；允许无改进 | s1_runner.py pilot/holdout 模式；s1_analysis.py 一次性评估入口 | A5 approval 记录；pilot 报告；holdout run_config；未获授权不得启动 | BLOCKED（待实现与 A5/Lead 放行） | A1+A6；A5+Lead |
| S1-09 | Issue #7 §2 S1-4、§4；统计计划 §3–§5 | 按 B=64/128 分层报告主终点；9 个 ENDPOINT_ROW_KEYS 精确列键，禁用别名 first_feasible_evaluation_index；不可行保留 null；单 run 对 10 opt seed 均值→meta seed 等权→任务为一级统计单位；OOD/负控不入主统计；7 类中文图 | s1_analysis.py（新增）；s1_figures.py（新增）；statistics.csv；aggregate.json | test_s1_analysis.py：endpoint_keys_exact、alias_rejected、null_policy、task_level_aggregation、figure_keys；7 PNG + figure_status | PENDING（实现未开始） | A6；A2 复核；A5 审阅 |
| S1-10 | Issue #7 §2 S1、§4；A5 phase2 §7②⑤ | 不得为让 MAML 获胜调参；负结果如实记录；正式 meta_test 打开后不得按效果改任务/终点/剔除；旧 M2/M5/M6 只读，main 不合并，PR #3/#6 不合并 | s1_analysis.py 预注册校验；文档/报告口径；A3 只读审计 | prereg_digest/analysis_plan_digest 校验；A5 审查无事后调参；A3 旧工件 tree_agg 未变 | PENDING（实现未开始） | A1+A2+A5；A3 |
| S1-11 | Issue #7 §1 缺口（m5_arms.py）；执行计划 §3.1 | 修复 score_m5_init_designs() 无 support_features/support_targets 参数、run_m5_bo_arm() 不传 k_shot/support 导致默认 k_shot=0 的闭环缺口；K=0 与旧行为逐位一致 | m5_arms.py；s1_runner.py 调用层；test_s1_runner.py | test_s1_runner.py：K_gt_0_changes_adaptation、K0_bitwise_regression；旧 m5_arms 测试回归 | READ_ONLY_VERIFIED（缺口已核实，修复未做） | A1；A5 审阅 |
| S1-12 | Issue #7 §2 S1、§4；执行计划 §5；A5 phase2 §7①⑥ | 产物齐全：preregistration.json、run_config.json、train_val_test_split.json、data_manifest.json、SHA256SUMS.txt、run_records.jsonl、statistics.csv、图数据/PNG、中文报告；code_sha 以 LF clean checkout 为准；缺数据标 NOT_RUN | s1_runner.py 输出目录；s1_analysis.py；s1_figures.py；中文报告 | 文件清单 + SHA 校验；figures/figure_status；报告逐条引用 JSON 路径与字段 | PENDING（实现未开始） | A1+A2+A6+A4；Lead 发布 |

> 说明：S1-11 是既有缺陷修复，不是新算法结果；其 READ_ONLY_VERIFIED 仅表示 A4 已核实缺口存在，不代表修复完成。其余 S1 行均为 PENDING。

## 4. A5 phase2 §7 前置映射（A5PRE-01..06）

| ID | A5 §7 前置（摘要） | 落地实现/检查 | 验收证据（计划） | 关联 S1 | 状态 |
|---|---|---|---|---|---|
| A5PRE-01 | ① S1 分析/汇总强制校验 ENDPOINT_ROW_KEYS 9 键与 analysis_plan_digest，补 null/键名不一致负控 | s1_analysis.py 启动校验；test_s1_analysis.py | 键名/别名/null/摘要不一致负控全部拒绝；合法输入通过 | S1-09/S1-12 | PENDING |
| A5PRE-02 | ② 三方 sha256/fingerprint/split_hash 校验后一次性构造并评估 meta_test/meta_test_ood；之后禁止调参/选臂/选终点 | s1_runner.py 预检；s1_analysis.py 预检；A5 审查记录 | 冻结输入逐字节校验；holdout 一次性评估日志；无事后修改 | S1-02/S1-08/S1-10 | PENDING |
| A5PRE-03 | ③ 五臂×K{0,1,3,5}×B{64,128} 逐 run 断言 billable=B；K=0 FOMAML-KSHOT-BO 登记 CLONE 排除因果推断 | s1_runner.py 预算断言；run_records.identifiability | 40 组预算测试；每 run billable_evals=B；CLONE 标记可查 | S1-02/S1-03/S1-04/S1-05 | PENDING |
| A5PRE-04 | ④ physical_call_count=0；不得启动 VSPAERO/SU2/RCAIDE Mission/CFD；#4 门禁不变 | s1_runner.py guard；报告口径；A3 审计 | 每 run physics.guard=PASS、physical_call_count=0；无求解器进程/产物 | S1-07/S1-12 | PENDING |
| A5PRE-05 | ⑤ 旧 M2/M5/M6 只读；main 不合并；PR #3/#6 不合并 | A3 只读审计；A4 矩阵记录；无代码改动 | 旧 run tree_agg 未变；PR merged=false；main/旧分支 SHA 未动 | S1-10/S1-12 | READ_ONLY_VERIFIED（当前事实） |
| A5PRE-06 | ⑥ code_sha 以 LF clean checkout 为准 | run_config.json；data_manifest.json；报告 | code_sha 记录与复算一致；非 clean checkout 拒绝 | S1-02/S1-12 | PENDING |

## 5. 统计计划 v1.1 验收映射

| 统计要素 | 规范值/规则 | 落点 | 关联 S1 | 状态 |
|---|---|---|---|---|
| 总 run 网格 | 21,000 runs | s1_runner.py；run_config.json | S1-02 | PENDING |
| 主确认网格 | B=64、K∈{0,3,5}、20 meta_test 任务、10 opt seed×3 meta seed=9,000 runs | s1_runner.py；统计计划 §3 | S1-02/S1-08 | PENDING |
| 次级网格 | B=128、K∈{3,5}=6,000 runs | s1_runner.py；统计计划 §3 | S1-02 | PENDING |
| 探索网格 | B=64/128、K=1=6,000 runs；不进主结论 | s1_runner.py；统计计划 §3 | S1-02/S1-10 | PENDING |
| 合成评价总量 | 1,920,000 次 | run_config/summary；A2 复核 | S1-02/S1-12 | PENDING |
| 五 split | 60/20/20/10/10，共 120 tasks；主统计仅 meta_test 20 | frozen_family.json；s1_runner.py split 过滤 | S1-02/S1-09 | PENDING |
| 支持/查询池 | support 128 / query 64 | s1_runner.py 任务构造；run_records | S1-01/S1-02 | PENDING |
| 主端点 | best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate | s1_analysis.py；statistics.csv | S1-09 | PENDING |
| 诊断端点 | first_feasible_in_support、first_feasible_after_support_index、feasible_hit_rate_non_support、n_nonnull、null_rate | s1_analysis.py；aggregate.json | S1-09 | PENDING |
| gap 公式 | gap=(f_best−f*)/max(|f*|,1e-12) | s1_analysis.py；合同 §3.3 | S1-09 | PENDING |
| first/hit 分母 | first 为 1-based 真实评价顺序；feasible_hit_rate 分母恒 B | s1_analysis.py；合同 §3.3 | S1-09 | PENDING |
| null 政策 | 不插补、不转 0；null 率>70% 该端点 INCONCLUSIVE；不换终点 | s1_analysis.py；报告 | S1-09/S1-10 | PENDING |
| 主比较 C1–C5 | C1 FOMAML-Kshot vs Pretrain-Kshot；C2 vs Random；C3 vs DE；C4 Pretrain-Kshot vs Random；C5 FOMAML-Kshot vs FOMAML-Zero（K>0） | s1_analysis.py；统计计划 §5 | S1-09 | PENDING |
| 显著性 | Wilcoxon 双侧 n=20；全零或 n<10 INCONCLUSIVE；bootstrap 10,000 seed=20261105；每端点内 Holm alpha=0.05 | s1_analysis.py；统计计划 §5 | S1-09 | PENDING |
| 实际阈值 | best/gap 相对 ≥1%；hit 绝对差 ≥0.05；first 改善 ≥ceil(0.05B)；同 K 内比较 | s1_analysis.py；统计计划 §5 | S1-09 | PENDING |
| 结论规则 | 单比较 SUPPORTED_BENEFIT/SUPPORTED_HARM/NO_EVIDENCE/INCONCLUSIVE；总体 SUPPORTED_IMPROVEMENT 要求 C1 四主端点至少 2 BENEFIT 且 0 HARM | s1_analysis.py；中文报告 | S1-09/S1-10 | PENDING |
| 7 类中文图 | fig1_meta_training_loss、fig2_k_shot_adaptation、fig3_feasible_rate、fig4_equal_budget_gap、fig5_fairness_audit、fig6_k_sweep_delta、fig7_negative_control_and_determinism | s1_figures.py；figures/ | S1-09/S1-12 | PENDING |
| 确定性 | 200 runs（5 臂×K{0,3}×B64×20 任务×seed0）重跑 3 次一致；K=0 逐字节等价 | s1_runner.py；raw_digest_manifest；determinism 报告 | S1-07/S1-10 | PENDING |
| 负控 | 标签打乱负控；任务泄漏负控；预算/摘要不一致 fail-closed | s1_runner.py；test_s1_runner.py | S1-07 | PENDING |
| 物理 | physical_call_count=0；不启动任何求解器 | physics guard；报告；A3 审计 | S1-07/S1-12 | PENDING |

## 6. 实现文件、测试与当前存在性

| 文件 | 角色 | 当前存在性 | 备注 |
|---|---|---|---|
| docs/planning/p4_route_a_s1_execution_plan_20261105.md | S1 执行计划 v1.0 | 未跟踪（untracked） | Lead 正式 run 前须固定 commit；A4 只读，不代提交 |
| docs/planning/p4_route_a_s1_statistical_plan_20261105.md | S1 统计计划 v1.1 | 已跟踪（HEAD 43fcfc8） | sha256 7d6ce0c2…；第 3 行仍有“待 A5 复审”旧措辞，属文档 minor，非本任务写范围 |
| docs/planning/p4_route_a_s0_design_contract.md | S0 设计合同 v1.1 | 已跟踪 | sha256 3f622570…；S1 数据合同基线 |
| research/concorde_metaopt/meta_learning/s1_runner.py | A1 新增：21,000 run 网格、K-shot 闭环、预算断言、run_records | **不存在** | 计划文件；当前无可执行实现 |
| research/concorde_metaopt/meta_learning/m5_arms.py | A1 修改：score_m5_init_designs()/run_m5_bo_arm() 接入支持样本与 k_shot | 已存在，缺口未修 | :504/:514/:540/:557/:566/:585/:623/:717 |
| research/concorde_metaopt/tests/test_s1_runner.py | A1 新增：泄漏/预算/初始化/K=0/负控/确定性单测 | **不存在** | 计划测试文件 |
| research/concorde_metaopt/meta_learning/s1_analysis.py | A6 新增：预检、聚合、C1–C5、null 政策、结论层 | **不存在** | 计划文件；不得由 A1 代写 |
| research/concorde_metaopt/meta_learning/s1_figures.py | A6 新增：7 类中文图与 figure_status | **不存在** | 计划文件 |
| research/concorde_metaopt/tests/test_s1_analysis.py | A6 新增：9 键/别名/null/摘要/负控单测 | **不存在** | 计划测试文件 |
| research/concorde_metaopt/meta_learning/family_v3.py | 既有冻结族/9 端点键/CSV 校验 | 已存在 | :162 ENDPOINT_ROW_KEYS；:836-872 校验；:194/:210/:218/:221 analysis_plan |
| research/concorde_metaopt/meta_learning/baseline_arms.py | 既有配对统计复用 | 已存在 | paired_statistics :1220-1244（bootstrap/Wilcoxon） |
| research/concorde_metaopt/meta_learning/m5_runner.py | 既有统计/端点映射复用 | 已存在 | :95 ENDPOINT_ROW_KEYS 映射；:2125-2160 统计入口 |

> 当前 HEAD 43fcfc8 没有任何 S1 运行目录、run_records.jsonl 或 S1 图表；本表“存在”仅指源码/计划文件，不代表 S1 验收通过。

## 7. 阶段门与交付证据包

阶段门（严格顺序）：

    S1 实现（A1/A6，零物理单测）
      → A5 代码与证据审阅
        → A5 签发 APPROVE_FOR_S1_RUN
          → Lead 授权 A2 执行 formal run（21,000 runs）
            → A5/A3 复核（统计、公平性、物理 0、旧证据隔离）
              → Lead 发布中文回执

当前位置：**“S1 实现”之前**；APPROVE_FOR_S1_RUN 与 Lead 正式 run 授权均未取得。

交付证据包（计划路径；全部 NOT_RUN/PENDING）：

| 证据 | 内容 | 关联 S1 | 当前状态 |
|---|---|---|---|
| run_config.json | 网格、B/K、五臂、seeds、冻结输入摘要、code_sha | S1-02/S1-12 | PENDING |
| run_records.jsonl | 每 run 字段、budget 账、endpoint_values、physics、digest | S1-01..S1-12 | PENDING |
| summary.json / aggregate.json | 聚合结果、C1–C5、null 率、结论层 | S1-09 | PENDING |
| statistics.csv | 9 个 ENDPOINT_ROW_KEYS 主表 | S1-09 | PENDING |
| train_val_test_split.json | 120 tasks 五 split 引用冻结包 | S1-02/S1-12 | PENDING |
| data_manifest.json / raw_digest_manifest.json | 文件 SHA256、code_sha、复算记录 | S1-12 | PENDING |
| figures/*.png + figure_data/*.csv | 7 类中文图与图数据；无数据标 NOT_RUN | S1-09/S1-12 | PENDING |
| SHA256SUMS.txt | 交付目录校验清单 | S1-12 | PENDING |
| 中文报告 | 结果/负结果、统计、限制、无物理声明 | S1-12 | PENDING |
| A5/A3 审查记录 | S1 代码审阅与隔离审计 | S1-08/S1-10 | BLOCKED（待实现） |

验收 8 条（执行计划 §6，全部尚未执行）：

1. 既有 604 tests 与 S1 新增测试全绿；当前 NOT_RUN。
2. 40 组五臂×K×B 预算测试全部 billable=B；当前 NOT_RUN。
3. 9 端点键/禁用别名/null/摘要不一致负控通过；当前 NOT_RUN。
4. 统计检验（Wilcoxon/bootstrap/Holm/阈值/结论规则）单测通过；当前 NOT_RUN。
5. 冻结输入篡改、预算不一致、K=0 clone 误入主分析等 fail-closed；当前 NOT_RUN。
6. 确定性 bundle 两跑一致；200 runs×3 与 K=0 逐字节等价；当前 NOT_RUN。
7. physical_call_count=0；当前只有计划 guard，无运行证据。
8. 0 主机绝对路径、旧 M2/M5/M6 工件不变、PR 边界不变；当前 A4 文档为相对路径，旧工件未触碰。

## 8. 风险、缺口与待决策

| ID | 风险/缺口 | 影响 | 缓解/下一步 | 状态 |
|---|---|---|---|---|
| R-01 | S1 代码/测试/运行全部未开始 | 无任何 S1 结果可评审 | A1/A6 按本矩阵实现；A5 先审代码 | OPEN |
| R-02 | m5_arms.py K-shot 闭环缺口（:504/:514/:585/:623/:717） | K>0 支持样本不会进入适应，S1 会重演 M5 缺口 | S1-11 必改；K=0 逐位回归；A5 复核 | OPEN（缺口已核实） |
| R-03 | A5 phase2 m08 要求分析脚本强制 9 键与摘要负控 | 若不实现，S1 分析可能接受错误 CSV/端点 | s1_analysis.py 启动即校验；负控纳入 test_s1_analysis.py | OPEN |
| R-04 | S1 执行计划 untracked，未固定 commit | 实现/验收口径可能漂移 | Lead 在 formal run 前提交固定 commit 并记录 SHA | OPEN |
| R-05 | Issue #7 要求扩展 adaptation.py/baseline_arms.py/m5_arms.py/m5_runner.py，执行计划 §3.1 仅列 s1_runner.py+m5_arms.py | 文件所有权/改动范围可能不一致 | Lead/A5 在实现前确认；超出执行计划 §3.1 的改动先更新计划并复审 | OPEN（需确认） |
| R-06 | 统计计划 v1.1 第 3 行仍写“待 A5 复审” | 文档口径滞后，易被误读为未冻结 | 由 Lead/A2 在正式 run 前修文档；不在 task-217 写范围 | OPEN（文档 minor） |
| R-07 | 21,000 runs 约 12h、1,920,000 次合成评价 | 资源/时间估计未实测；可能影响阶段排期 | 先 pilot 实测吞吐；正式 run 前 Lead 确认预算与停止条件 | OPEN |
| R-08 | 7 类中文图与 figure_status 尚无数据 | 无数据不得绘虚构曲线；可能被误当已完成 | A6 仅用真实 run 数据；无数据标 NOT_RUN；A5 审图 | OPEN |
| R-09 | 旧 M2/M5/M6 与 PR #3/#6 边界 | 误合并/误改会破坏历史证据 | A3 审计；main 不合并；旧 run 只读；仅 Lead 发布 | OPEN（A3 持续） |
| R-10 | 物理调用与 Issue #4 门禁 | S1 合成结果可能被误标为真实气动证据 | 报告强制 lifting/synthetic 标注；physical=0；#4 门禁不变 | OPEN（持续） |

待决策：
1. 执行计划 §3.1 与 Issue #7 的文件所有权差异（R-05）由 Lead/A5 确认，确认前 A1 不应改 adaptation/baseline_arms/m5_runner。
2. S1 执行计划 untracked，需 Lead 在实现/formal run 前固定 commit（R-04）。
3. S1 pilot 的样本规模、通过条件与 APPROVE_FOR_S1_RUN 的具体判据需 A5 在执行计划中冻结。
4. 统计计划 v1.1 第 3 行旧措辞与 A5 phase2 8 minor 的关闭时点（不阻断 S1 formal 准备）。

## 9. 读取记录

- Issue #7：GitHub 只读；读取时间 2026-11-05T11:49+08；state=open；正文落盘 <EXT>/d12d006/a4/raw/issue7_body.txt；读取时 comments=0，其后 Lead 发布 S0-2 回执 6653167378（现 1 条评论）。
- Issue #4：state=open，comments=15；最新评论 6647827491（D-12D-006）；S1 不改变 #4 物理门禁。
- Issue #5：state=open，comments=3；最新终态回执 6643119583（2026-11-04T21:55:56Z）。
- PR #3：open、merged=false、head=e5140fc；PR #6：open、merged=false、head=ff6280f；PR #7 不存在（404）；main=ec65e5a 未合并。
- 冻结包：research/concorde_metaopt/optimization_runs/p4ra-s0-2-freeze-20261105T072500Z（11 文件；SHA256SUMS.txt 8 个 payload 校验；freeze_summary.json git_sha=766a59c、code_sha=c929609a…、radius_base=0.64、CALIBRATED）。
- A5 phase2：<EXT>/p4-route-a/a5/S0_2_A5_review_phase2.md（sha256 ea9b2eb7…；0 blocker/0 major/8 minor；604 tests OK(skipped=1)/37.687s；determinism 29/29；physical=0）。
- A3 phase2：<EXT>/EXT/p4-route-a/a3/S0_2_phase2_isolation.md（sha256 23bac611…；PASS 11/11；三提交单父非 merge；旧 M2/M5/M6 tree_agg 未变；0 solver）。
- 本地 S1 工作树：HEAD=43fcfc851525bd74935b20c85dfbea2d932e436e，branch research/p4-route-a-s1；porcelain 仅 docs/planning/p4_route_a_s1_execution_plan_20261105.md 未跟踪；S1 代码/测试/运行目录均不存在；A4 未 commit/push，未改代码或冻结包。
- A4 本任务仅新增本文件并更新 S0 需求矩阵；未执行物理计算、未启动求解器、未做 GitHub 写操作。

## 10. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4（task-217） | 首次生成 S1-01..S1-12 需求→实现文件/测试/验收证据矩阵；映射 S0-2 冻结输入、A5 phase2 §7 六前置、统计计划 v1.1 与阶段门；明确 S1 未实现、所有运行/图表 NOT_RUN，无算法结果、无物理调用 |
