# P4 路线A S1 需求矩阵（Issue #7 · S1 K-shot→BO 闭环 → 实现文件 / 测试 / 验收证据 / 状态）

> 文档性质：S1 需求到实现文件、测试与验收证据的映射表，供 Lead、A5、A6 与 A1 对齐口径；**S1 代码已部分实现、A5 rev2 判 CHANGES_REQUESTED、S1 formal run 尚未获准且未执行；本文件不含新的算法结果，不构成新的物理授权或预算批准**。
> 依据：Issue #7 正文（D-P4-003，§2 S1 四条与 §3–§4 约束，2026-11-05 读取）+ docs/planning/p4_route_a_stage_improvement_plan_20261105.md（V1.0，commit a331639e）+ docs/planning/p4_route_a_s1_execution_plan_20261105.md（v1.2）+ docs/planning/p4_route_a_s1_statistical_plan_20261105.md（v1.1，sha256 7d6ce0c24745fe56e24758d457ee5c1cc12acdb8eacc056aa5ae5538a6033ae6）+ docs/planning/p4_route_a_s0_design_contract.md（v1.2）+ docs/planning/p4_route_a_s1_v4_remediation_rulings_20261105.md（R-V4-01..06，sha256 f71e32a9…）+ A5 S1 rev2 复审 <EXT>/p4-route-a/a5/S1_code_review_rev2.md（CHANGES_REQUESTED；2 blocker / 4 major / 6 minor；sha256 d5a0979ac83009e4217bf9848fc3c9cdca7216c3a87f899ed143195678a5f795）+ 旧 S0-2 包（只读历史）+ A3 S0-2 隔离审计。
> 读取时点：2026-11-05T22:00+08；S1 工作树 HEAD=c0cb2cd8f74b2eaeb346806c059f28f603ca30fb，branch research/p4-route-a-s1；S1 代码/测试已存在；仅 v4 裁定文件未跟踪；未读取新 meta_test/meta_test_ood 结果。
> 状态口径：IN_PROGRESS＝实现已落盘且现有测试通过，但 A5 rev2/v4 整改未关闭；PARTIAL＝部分实现或验收证据不足；BLOCKED＝依赖 S0-3 冻结包、正式工件、A5 phase3 或 Lead 授权；PENDING＝尚未产生；READ_ONLY_VERIFIED＝仅输入或历史事实经 A4 只读核对（不代表验收通过）。S0-2 phase2 APPROVE_FOR_S1_FORMAL 只对旧静态/测试范围有效，已不能作为当前 holdout 的确证性 formal 放行依据。

## 1. 当前状态与硬边界

| 检查项 | 当前事实 | 来源/证据 |
|---|---|---|
| S0-2 阶段门 | 旧 S0-2 冻结包 COMPLETE（历史）；A5 phase2「APPROVE_FOR_S1_FORMAL」只对旧静态/测试范围有效，确证性用途已被 A5 S1 rev2 M03 收窄；**不能作为当前 S1 formal 放行依据** | A5 phase2 报告；A5 S1 rev2 S1R2-M03 |
| S0-3 v4 remediation | **IN_PROGRESS**：R-V4-01 选 H1，只重播种 meta_test 20 + meta_test_ood 10，holdout_seed=20261106、family_version=p4ra-family-v4；S0-3 包待 A1 干净 detached worktree 生成并由 Lead 提交，尚未冻结 | v4 裁定 R-V4-01/R-V4-05 |
| S1 实现 | **PARTIAL**：c0cb2cd 已落盘 s1_runner.py 1,733 行、s1_analysis.py 2,849 行、s1_figures.py 632 行及两份测试（1,145/1,748 行）；A5 rev2 复跑 768 tests OK(skipped=1)，但判 **CHANGES_REQUESTED（2 blocker / 4 major / 6 minor）** | c0cb2cd；A5 S1 rev2 |
| S1 正式 run | **未批准、未执行**；21,000 runs / 1,920,000 次合成评价仅为计划数；须 S0-3 + 正式工件 + A5 phase3「APPROVE_FOR_S1_RUN」+ Lead 书面授权 | S1 执行计划 v1.2 §10 |
| holdout 污染 | **BLOCKED**：EXT 下 36 个 run_records.jsonl 共 608 条 split=meta_test，涉 TE-000/001/003（3/20）；TE-000..007（8/20）曾被内存读取；旧 S0-2 meta_test 已不满足一次性盲测 | A5 S1 rev2 S1R2-B01 |
| K-shot 闭环 | 代码层已改造（m5_arms 传递 support/k_shot，旧 B03 closed）；但正式 200/50 工件下 K=5 ZERO==KSHOT 初始设计 22/24（K=3 22/24、K=1 20/24），需 pair-level 报告与 C5-B 处置，不得直接宣称适应增益/损害 | A5 S1 rev2 S1R2-B02；R-V4-02 |
| 物理调用 | physical_call_count=0；S1 不启动 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag；Issue #4 物理门禁不变 | Issue #7 §3；A5 phase2 §7④ |
| 旧证据与 main | 旧 M2/M5/M6 与旧 S0-2 包只读；main 不合并；PR #3/#6 保持 open 不合并 | A3 phase2；SAFE-05 |
| 发布权限 | 仅 Lead 可发布 GitHub；A4 本任务只读，未评论/改 Issue/建 Issue | Issue #7 §4；A4 角色约束 |

> 结论：S1 不再处于“未开始”，但当前实现**不可验收**：holdout 污染使旧 S0-2 不能用于确证，C5 结构克隆使 FOMAML-KSHOT 的适应增益不可辨识；须完成 v4/S0-3、正式工件重建、pair-level/C5-B 分析与 A5 phase3 后才可能放行 formal。下文状态为当前映射，不得引用为已通过证据。

## 2. 冻结输入（旧 S0-2 只读 + v4/S0-3 待冻结）

### 2.1 旧 S0-2（历史复现/负控，只读，不得用于确证 S1 formal）

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
| 支持池/查询池 | support 128 / query 64（每任务） | S1 统计计划 §3 |
| 计划规模 | 21,000 runs；1,920,000 次合成评价；B∈{64,128}；K∈{0,1,3,5} | S1 统计计划 v1.1 |

> 旧包只读：不得改写、不得把其 meta_test 重新当作未读盲测；其 meta_test 已被 36 个 run_records（608 条记录）与 8/20 任务的内存读取消耗（A5 S1R2-B01）。旧包仅用于历史复现、负控与格式对照。

### 2.2 v4/S0-3 目标输入（尚未冻结，待 A1 生成 + Lead 提交）

| 冻结项 | 目标值/规则 | 来源 |
|---|---|---|
| family_id / family_version | F-QE-feasible-v3 / p4ra-family-v4 | R-V4-01 |
| holdout_seed | 20261106 | R-V4-01 |
| 任务 ID 字面量 | 仍为 p4ra-FQE3-v3-（TR/VA/TE/OD/NC）-NNN；run record/run_config/frozen_family/prereg 必须携带 family_version | R-V4-01 |
| 五 split 计数 | meta_train 60 / meta_validation 20 / meta_test 20 / meta_test_ood 10 / negative_control 10 | R-V4-01 |
| 重播种范围 | **仅** meta_test 20 + meta_test_ood 10；meta_train 60 / meta_validation 20 / negative_control 10 逐位不变 | R-V4-01 |
| 隔离硬条件 | v4 holdout task_fingerprint 与 v3 官方包 120 个 fingerprint 零交集（legacy 280 task_id 仅 task_id 零交集）；五集合互斥 | R-V4-01/R-V4-05 |
| 新冻结包名 | p4ra-s0-3-freeze-（UTC）Z | R-V4-01 |
| 必填元数据 | run_id、git_sha、code_sha、holdout_seed、两进程逐字节一致证明，写入 frozen_family/prereg/freeze_summary/digest_manifest | R-V4-01/R-V4-05 |
| 冻结验收 | meta_test/ood fingerprint 全变、其余三 split 映射逐项相同、计数不变；A5 phase3 复核通过后才可用于确证 formal | R-V4-05 |
| 物理调用 | 0 | Issue #7；R-V4-05 |

> v4 冻结包尚未生成，family_fingerprint/split_hash/prereg_digest/analysis_plan_digest 的 v4 值不得预填或猜测；本矩阵不引用任何新 meta_test 结果。

## 3. S1 需求矩阵（S1-01..S1-12）

| ID | 来源 | 要求与验收条件 | 实现文件（c0cb2cd 实况） | 测试/验收证据（当前） | 状态（v4 口径） | 责任/依赖 |
|---|---|---|---|---|---|---|
| S1-01 | Issue #7 §2 S1-1；执行计划 §2、§3.2；合同 §4.2 | K 次目标任务支持样本的特征与目标/约束标签进入内循环，用适应后代理评分；query 标签、解析最优点不可见；代理预测不得写入 BO 真实 observations；K=0 退化为旧行为 | s1_runner.py 内循环；m5_arms.py 已传 support_features/support_targets 与 k_shot；adaptation.py 复用 | A5 rev2 复跑 768 tests OK(skipped=1)；但 C5 结构克隆未处置，pair-level 证据缺失 | IN_PROGRESS（代码已落盘；A5-B03 代码层 closed；B02/C5-B 待整改） | A1；A5 phase3 |
| S1-02 | Issue #7 §2 S1-2；合同 §4.2；统计计划 §3 | B∈{64,128}、K∈{0,1,3,5}；五臂共享同一 K 次目标任务评价，K 次必须计入 B；每 run 满足 K+(8−K)+(B−8)=B；计划 21,000 runs / 1,920,000 评价；非物理代理时间单列 | s1_runner.py 网格与预算账；run_records.jsonl | 768 tests 中含预算/网格用例；正式 21,000 网格未运行 | IN_PROGRESS（单测层通过；正式网格未执行） | A1+A2；A5 phase3 |
| S1-03 | Issue #7 §2 S1-2；合同 §4.2；A5 phase2 §7③ | 8 个初始点=K 个支持点+8−K 个新点；之后普通 BO B−8 次；DE 的 8−K 新点并入 population；K=0 复现旧初始化行为 | s1_runner.py 初始化路径；run_records.initial_designs | 768 tests 含初始化/来源标签用例；A5 rev2 未否定预算与计数逻辑 | IN_PROGRESS（实现存在；待 v4 重跑复验） | A1；A2 复核 |
| S1-04 | Issue #7 §2 S1-3；A5 phase2 §7③ | 五臂 RAND-BO / PRETRAIN-KSHOT-BO / FOMAML-ZERO-BO / FOMAML-KSHOT-BO / DE；同任务、同种子、同候选池、同约束；仅初始化路径不同 | s1_runner.py arm registry；m5_arms.py 旧臂复用 | 768 tests 含五臂配置/公平审计用例；正式工件待重建 | IN_PROGRESS（实现存在；正式工件 M01 未关闭） | A1+A2；A5 phase3 |
| S1-05 | Issue #7 §2 S1-3；执行计划 §3；R-V4-02 | 克隆识别、缓存与 null 规则一致；K=0 的 FOMAML-KSHOT-BO 登记 CLONE_OF_FOMAML-ZERO-BO；K>0 每个（task,B,K,meta_seed）组按初始设计行 digest overlap_rate≥0.90 判 STRUCTURALLY_IDENTICAL；C5 不做 benefit/harm、不进 Holm | s1_runner.py clone/cache；identifiability_report.json（pair-level） | A5-M02：旧报告仅组级 max/mean，analysis 未消费；pair-level 字段/schema 缺失 | PARTIAL（组级克隆已识别；pair-level/C5-B 未实现） | A1+A6；A5 phase3 |
| S1-06 | Issue #7 §2 S1-3；执行计划 §3 | 训练 episode 支持样本数与部署 K 匹配（5/10 或混合 K）；旧 128 样本内循环仅作消融基线，不得冒充新 K-shot 闭环 | 训练/episode 采样路径；s1_runner.py 配置；adaptation.py 复用 | 768 tests 含 episode 支持数用例；A5 rev2 未单列此项缺陷 | IN_PROGRESS（实现存在；v4 复验后确认） | A1+A2；A5 phase3 |
| S1-07 | Issue #7 §2 S1-4；A5 phase2 §7①②④；执行计划 §9 | 先做零物理单测：query/任务泄漏负控、真实合成评价预算精确一致、K>0 确实改变模型参数与初始选点、失败路径 fail-closed；physical_call_count=0 | test_s1_runner.py；s1_runner.py/s1_analysis.py 前置断言 | A5 rev2 复跑 768 tests OK(skipped=1)；v4 修复后须重跑，不得引用旧数字 | PARTIAL（当前测试通过；v4 变更后需重跑） | A1+A6；A5 phase3 |
| S1-08 | Issue #7 §2 S1-4；执行计划 §6、§10；A5 phase2 §7② | 验证集小样本 pilot 通过后，A5 phase3 书面 APPROVE_FOR_S1_RUN 且 Lead 授权，才执行新独立 holdout；正式 meta_test 一次性打开，之后禁止调参/选臂/选终点；允许无改进 | s1_runner.py pilot/holdout 模式；s1_analysis.py 一次性评估入口 | 旧 S0-2 holdout 已被污染（B01），不能用于确证；S0-3 尚未冻结；无 pilot/formal 记录 | BLOCKED（等待 S0-3 + 正式工件 + A5 phase3 + Lead 授权） | A1+A6；A5+Lead |
| S1-09 | Issue #7 §2 S1-4、§4；统计计划 §3–§5；R-V4-04 | 按 B=64/128 分层报告主终点；9 个 ENDPOINT_ROW_KEYS 精确列键，禁用别名；不可行保留 null；任务为一级统计单位；OOD/负控不入主统计；7 类规范图（图面英文，避免中文字体缺失） | s1_analysis.py；s1_figures.py；statistics.csv；aggregate.json | 768 tests 含端点/聚合/图键用例；A5-M02 指 analysis 未消费 pair 报告；A5-m05 指图面英文 | PARTIAL（分析已实现；pair 消费/C5-B/图面口径待整改） | A6；A2 复核；A5 phase3 |
| S1-10 | Issue #7 §2 S1、§4；A5 phase2 §7②⑤；R-V4-06 | 不得为让 MAML 获胜调参；负结果如实记录；正式 meta_test 打开后不得按效果改任务/终点/剔除；旧 M2/M5/M6 只读，main 不合并，PR #3/#6 不合并 | s1_analysis.py 预注册校验；文档/报告口径；A3 只读审计 | 旧 phase2 APPROVE 已被 M03 收窄；v4 prereg 未冻结；无事后调参证据 | PARTIAL（约束已写入；v4 冻结/回执披露未完成） | A1+A2+A5+A4；A3 |
| S1-11 | Issue #7 §1 缺口（m5_arms.py）；执行计划 §3.1；A5 rev2 B03 | 修复 score_m5_init_designs() 无 support 参数、run_m5_bo_arm() 不传 k_shot/support 的闭环缺口；K=0 与旧行为逐位一致 | m5_arms.py；s1_runner.py 调用层；test_s1_runner.py | c0cb2cd 已改；A5 rev2 判 B03 代码层 CLOSED；v4 需回归重验 | IN_PROGRESS（代码已修；待 v4 回归确认） | A1；A5 phase3 |
| S1-12 | Issue #7 §2 S1、§4；执行计划 §5、§9；A5 phase2 §7①⑥ | 产物齐全：preregistration.json、run_config.json、train_val_test_split.json、data_manifest.json、SHA256SUMS.txt、run_records.jsonl、statistics.csv、identifiability_report.json、图数据/PNG、中文报告；code_sha 以 LF clean checkout 为准；缺数据标 NOT_RUN | s1_runner.py 输出目录；s1_analysis.py；s1_figures.py；中文报告 | 正式工件未从 c0cb2cd 干净树重建（M01）；无 formal run 产物 | BLOCKED（正式工件/formal 未产生） | A1+A2+A6+A4；Lead 发布 |

> 说明：状态为 **当前实现映射**，不是验收通过。S1-01/S1-11 的代码修改已在 c0cb2cd 落盘且旧 A5 代码层 finding 关闭，但 v4 变更后须重跑测试；S1-05/S1-09 的 pair-level/C5-B 是 A5-M02 与 R-V4-02 的新增整改项；S1-08/S1-12 在 S0-3 与 A5 phase3 前保持 BLOCKED。

## 4. A5 phase2 §7 前置映射（A5PRE-01..06）与 v4/A5 rev2 整改项

### 4.1 A5 phase2 前置（旧阶段门，保留追溯）

| ID | A5 §7 前置（摘要） | 落地实现/检查 | 验收证据（当前） | 关联 S1 | 状态 |
|---|---|---|---|---|---|
| A5PRE-01 | ① S1 分析/汇总强制校验 ENDPOINT_ROW_KEYS 9 键与 analysis_plan_digest，补 null/键名不一致负控 | s1_analysis.py 启动校验；test_s1_analysis.py | 768 tests 含端点/负控用例；pair 报告消费仍缺（A5-M02） | S1-09/S1-12 | PARTIAL |
| A5PRE-02 | ② 三方 sha256/fingerprint/split_hash 校验后一次性构造并评估 meta_test/meta_test_ood；之后禁止调参/选臂/选终点 | s1_runner.py 预检；s1_analysis.py 预检；A5 审查记录 | 旧 S0-2 holdout 已被污染（B01），不能用于确证；v4 holdout 未冻结 | S1-02/S1-08/S1-10 | BLOCKED（须 S0-3） |
| A5PRE-03 | ③ 五臂×K{0,1,3,5}×B{64,128} 逐 run 断言 billable=B；K=0 FOMAML-KSHOT-BO 登记 CLONE 排除因果推断 | s1_runner.py 预算断言；run_records.identifiability | 768 tests 含预算/CLONE 用例；正式 40 组合未运行 | S1-02/S1-03/S1-04/S1-05 | IN_PROGRESS |
| A5PRE-04 | ④ physical_call_count=0；不得启动 VSPAERO/SU2/RCAIDE Mission/CFD；#4 门禁不变 | s1_runner.py guard；报告口径；A3 审计 | 代码层 guard 存在；无 formal run 运行证据 | S1-07/S1-12 | PARTIAL |
| A5PRE-05 | ⑤ 旧 M2/M5/M6 只读；main 不合并；PR #3/#6 不合并 | A3 只读审计；A4 矩阵记录；无代码改动 | 旧 run tree_agg 未变；PR merged=false；main/旧分支 SHA 未动 | S1-10/S1-12 | READ_ONLY_VERIFIED（当前事实） |
| A5PRE-06 | ⑥ code_sha 以 LF clean checkout 为准 | run_config.json；data_manifest.json；报告 | 正式工件未从 c0cb2cd 干净树重建（M01） | S1-02/S1-12 | BLOCKED（须正式工件） |

### 4.2 R-V4 裁定整改项（V4-01..V4-06）

| ID | 裁定/要求（摘要） | 落地文档/代码 | 验收证据 | 关联 S1 | 状态 |
|---|---|---|---|---|---|
| V4-01 | 选 H1：只重播种 meta_test 20 + meta_test_ood 10；holdout_seed=20261106；family_version=p4ra-family-v4；S0-3 新包替代 S0-2；旧包只读 | 合同 §3/§5/§6.2/§7；执行计划 §2；本矩阵 §2.2 | S0-3 包两进程一致、fingerprint 零交集、三 split 逐位相同；A5 phase3 | S1-02/S1-08/S1-10 | IN_PROGRESS（裁定已冻结，包未生成） |
| V4-02 | C5-B：pair 级 overlap_rate≥0.90 判 STRUCTURALLY_IDENTICAL；C5 不做 benefit/harm、不进 Holm；可估计任务<10 → NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY | 合同 §7.2；执行计划 §6 第 10 条；本矩阵 S1-05/S1-09 | pair-level 报告 + analysis 消费 + aggregate 排除计数；A5 phase3 | S1-05/S1-09/S1-10 | PARTIAL（文档规则已写；组级报告已有，pair-level 未实现） |
| V4-03 | 正式工件从 v4 代码干净树重建（默认 200/50）；artifact sha 写 readiness/run_config；旧 readiness 标 BASELINE_989FC0A 不可复用 | 执行计划 §7；合同 §9 | 干净树重建记录、artifact sha、A2 readiness PASS | S1-02/S1-12 | BLOCKED（须 v4 提交后） |
| V4-04 | identifiability_report.json 增 pair 级字段与 pair_status_counts；analysis 必须加载校验；formal 缺失 fail-closed；aggregate/CSV 输出排除计数 | 执行计划 §6 第 11 条、§9；合同 §7 | schema/覆盖校验负控；aggregate/CSV 字段 | S1-05/S1-09/S1-12 | PARTIAL（组级报告已存在；pair 级字段/消费待实现） |
| V4-05 | 阶段门：A1/A6 修复→Lead commit V4→S0-3 生成/提交→A2 工件/readiness→A5 phase3→A3 隔离→A5 APPROVE_FOR_S1_RUN + Lead 授权→formal | 执行计划 §10；本矩阵 §7 | 每阶段证据齐全；缺一不得启动 formal；readiness 不读 test/OOD | S1-08/S1-12 | IN_PROGRESS（文档已写，流程未走） |
| V4-06 | 文档统一 v4/holdout/C5-B/pair/旧 S0-2 只读；Issue #7 回执须披露污染/H1/C5/旧 APPROVE 收窄/0 物理/未合并 main | 合同/执行计划/本矩阵/S0 矩阵；Lead 回执 | 四文档一致；回执字段齐全；A4 只读核验 | S1-10 | PARTIAL（四文档已统一；Issue #7 回执待 Lead） |

### 4.3 A5 S1 rev2 findings 映射（B01/B02/M01..M04 + minor）

| ID | 等级 | 事实（摘要） | 本矩阵处置 | 状态 |
|---|---|---|---|---|
| S1R2-B01 | blocker | 36 个 run_records 共 608 条 split=meta_test；TE-000/001/003 被读；TE-000..007 共 8/20 入内存；旧 S0-2 holdout 不满足一次性盲测 | §2.1 标旧包只读；S1-08/S1-10 改 BLOCKED；V4-01 重播种 | OPEN（须 S0-3） |
| S1R2-B02 | blocker | 正式 200/50 工件 K=5 ZERO==KSHOT 初始设计 22/24（K=3 22/24、K=1 20/24）；meta0 K5 B64 8/8 历史逐字节相同 | S1-01/S1-05/S1-09 增 C5-B/pair 规则；不宣称适应增益 | OPEN（代码/报告待改） |
| S1R2-M01 | major | 正式工件未从 c0cb2cd 干净树重建 | S1-12/A5PRE-06/V4-03 标 BLOCKED；执行计划 §7 | OPEN |
| S1R2-M02 | major | identifiability_report 只有组级 max/mean；analysis 未消费 | S1-05/S1-09/§4.2 V4-04 | OPEN |
| S1R2-M03 | major | phase2 APPROVE 对确证用途被 supersede | 本矩阵 header/§1 明确收窄；S1-10 | MITIGATED_BY_DOC（待 A5 phase3 确认） |
| S1R2-M04 | major | A1 的 10/24 来自 2/3-step 诊断工件，正式 200/50 为 22/24 | 本矩阵统一采用正式工件 22/24；不再引用 10/24 | CLOSED_BY_FACT（本矩阵口径） |
| S1R2-m01 | minor | S1 矩阵 stale | 本次 v1.1 重写 | CLOSED_BY_DOC（v1.1） |
| S1R2-m02 | minor | 执行计划输出清单缺 identifiability_report | 执行计划 v1.2 §6/§9 已补 | CLOSED_BY_DOC |
| S1R2-m03 | minor | overlap 分母口径未定 | 合同 §7.2 已写 pair 组与臂对；代码待实现 | PENDING |
| S1R2-m04 | minor | 合同 4 项歧义 | 合同 v1.2 §3/§5/§7 已补；待 A5 复核 | PARTIAL |
| S1R2-m05 | minor | 图面英文 | S1-09 已改为“7 类规范图（图面英文）”；执行计划 v1.2 §3.2 同步为“7 类规范图（图面英文；图注/结论中文）” | CLOSED_BY_DOC（图面由 A6 实现） |
| S1R2-m06 | minor | 旧 readiness 不可用 | V4-03/执行计划 §7 标 BASELINE_989FC0A 不可复用 | CLOSED_BY_DOC（须 A2 重跑） |


## 5. 统计计划 v1.1 验收映射

| 统计要素 | 规范值/规则（v4） | 落点 | 关联 S1 | 状态 |
|---|---|---|---|---|
| 总 run 网格 | 21,000 runs | s1_runner.py；run_config.json | S1-02 | BLOCKED（formal 未授权） |
| 主确认网格 | B=64、K∈{0,3,5}、20 meta_test 任务、10 opt seed×3 meta seed=9,000 runs；v4 重播种后 meta_test 任务换新 | s1_runner.py；统计计划 §3 | S1-02/S1-08 | BLOCKED |
| 次级网格 | B=128、K∈{3,5}=6,000 runs | s1_runner.py；统计计划 §3 | S1-02 | BLOCKED |
| 探索网格 | B=64/128、K=1=6,000 runs；不进主结论 | s1_runner.py；统计计划 §3 | S1-02/S1-10 | BLOCKED |
| 合成评价总量 | 1,920,000 次 | run_config/summary；A2 复核 | S1-02/S1-12 | BLOCKED |
| 五 split | 60/20/20/10/10，共 120 tasks；主统计仅 meta_test 20；v4 仅 TE/OD 重播种，其余三 split 逐位不变 | frozen_family.json；s1_runner.py split 过滤 | S1-02/S1-09 | PARTIAL（v4 包未冻结） |
| 支持/查询池 | support 128 / query 64 | s1_runner.py 任务构造；run_records | S1-01/S1-02 | IN_PROGRESS |
| 主端点 | best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate | s1_analysis.py；statistics.csv | S1-09 | IN_PROGRESS |
| 诊断端点 | first_feasible_in_support、first_feasible_after_support_index、feasible_hit_rate_non_support、n_nonnull、null_rate | s1_analysis.py；aggregate.json | S1-09 | IN_PROGRESS |
| gap 公式 | gap=(f_best−f*)/max(|f*|,1e-12) | s1_analysis.py；合同 §3.3 | S1-09 | IN_PROGRESS |
| first/hit 分母 | first 为 1-based 真实评价顺序；feasible_hit_rate 分母恒 B | s1_analysis.py；合同 §3.3 | S1-09 | IN_PROGRESS |
| null 政策 | 不插补、不转 0；null 率>70% 该端点 INCONCLUSIVE；不换终点 | s1_analysis.py；报告 | S1-09/S1-10 | IN_PROGRESS |
| 主比较 C1–C5 | C1 FOMAML-Kshot vs Pretrain-Kshot；C2 vs Random；C3 vs DE；C4 Pretrain-Kshot vs Random；**C5 按 C5-B 只描述结构克隆率，不做 benefit/harm、不进 Holm** | s1_analysis.py；统计计划 §5；合同 §7.2 | S1-09 | PARTIAL（C5-B 待实现） |
| 显著性 | Wilcoxon 双侧 n=20；全零或 n<10 INCONCLUSIVE；bootstrap 10,000 seed=20261105；每端点内 Holm alpha=0.05；C5 不进入 Holm 族 | s1_analysis.py；统计计划 §5 | S1-09 | IN_PROGRESS |
| 实际阈值 | best/gap 相对 ≥1%；hit 绝对差 ≥0.05；first 改善 ≥ceil(0.05B)；同 K 内比较 | s1_analysis.py；统计计划 §5 | S1-09 | IN_PROGRESS |
| 结论规则 | 单比较 SUPPORTED_BENEFIT/SUPPORTED_HARM/NO_EVIDENCE/INCONCLUSIVE；总体 SUPPORTED_IMPROVEMENT 要求 C1 四主端点至少 2 BENEFIT 且 0 HARM；C5 不可估计时总结论固定 NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY | s1_analysis.py；中文报告 | S1-09/S1-10 | PARTIAL |
| pair-level/C5-B | 每个 (task,B,K,meta_seed) 组每臂对算初始设计行 digest overlap_rate；≥0.90 判 STRUCTURALLY_IDENTICAL；输出 pair_identifiable/structural_status/threshold 与 pair_status_counts；formal 缺报告 fail-closed | identifiability_report.json；s1_analysis.py；aggregate/CSV | S1-05/S1-09 | PENDING |
| 7 类规范图 | fig1_meta_training_loss、fig2_k_shot_adaptation、fig3_feasible_rate、fig4_equal_budget_gap、fig5_fairness_audit、fig6_k_sweep_delta、fig7_negative_control_and_determinism；图面英文，图注/结论中文 | s1_figures.py；figures/ | S1-09/S1-12 | PARTIAL（A5-m05） |
| 确定性 | 200 runs（5 臂×K{0,3}×B64×20 任务×seed0）重跑 3 次一致；K=0 逐字节等价 | s1_runner.py；raw_digest_manifest；determinism 报告 | S1-07/S1-10 | PARTIAL（代码层；v4 重跑待做） |
| 负控 | 标签打乱负控；任务泄漏负控；预算/摘要不一致 fail-closed | s1_runner.py；test_s1_runner.py | S1-07 | PARTIAL |
| 物理 | physical_call_count=0；不启动任何求解器 | physics guard；报告；A3 审计 | S1-07/S1-12 | PARTIAL（无 formal 运行证据） |

## 6. 实现文件、测试与当前存在性

| 文件 | 角色 | 当前存在性（HEAD c0cb2cd + 工作树） | 备注 |
|---|---|---|---|
| docs/planning/p4_route_a_s1_execution_plan_20261105.md | S1 执行计划 v1.2 | 已跟踪；本次修改未提交 | 168 行；A4 按 task-231 修订，未 commit/push |
| docs/planning/p4_route_a_s1_statistical_plan_20261105.md | S1 统计计划 v1.1 | 已跟踪 | sha256 7d6ce0c2…；仍写旧“待 A5 复审”，属文档 minor；本任务未改 |
| docs/planning/p4_route_a_s0_design_contract.md | S0 设计合同 v1.2 | 已跟踪；本次修改未提交 | 292 行；S1 数据合同基线 |
| docs/planning/p4_route_a_s1_v4_remediation_rulings_20261105.md | v4 裁定 R-V4-01..06 | 未跟踪（Lead 提供） | 5,715 B/84 行；A4 只读依据 |
| research/concorde_metaopt/meta_learning/s1_runner.py | A1：网格、K-shot 闭环、预算断言、run_records | 已存在（1,733 行/74,304 B）；工作树有 A1 未提交改动 | A4 未触碰；本次仅只读 |
| research/concorde_metaopt/meta_learning/m5_arms.py | A1：接入支持样本与 k_shot | 已存在；c0cb2cd 已修 | 旧缺口 :504/:514/:585/:623/:717；A5-B03 代码层 closed |
| research/concorde_metaopt/tests/test_s1_runner.py | A1：泄漏/预算/初始化/K=0/负控/确定性单测 | 已存在（1,145 行/46,565 B）；工作树有 A1 未提交改动 | 768 tests 集合的一部分 |
| research/concorde_metaopt/meta_learning/s1_analysis.py | A6：预检、聚合、C1–C5、null 政策、结论层 | 已存在（2,849 行/128,095 B）；工作树有 A1/A6 未提交改动 | A4 未触碰 |
| research/concorde_metaopt/meta_learning/s1_figures.py | A6：7 类图与 figure_status | 已存在（632 行/27,990 B） | 图面英文（A5-m05） |
| research/concorde_metaopt/tests/test_s1_analysis.py | A6：9 键/别名/null/摘要/负控单测 | 已存在（1,748 行/76,444 B） | 768 tests 集合的一部分 |
| research/concorde_metaopt/meta_learning/family_v3.py | 既有冻结族/9 端点键/CSV 校验 | 已存在；工作树有未提交改动 | :162 ENDPOINT_ROW_KEYS；:836-872 校验；A4 只读 |
| research/concorde_metaopt/meta_learning/baseline_arms.py | 既有配对统计复用 | 已存在 | paired_statistics :1220-1244（bootstrap/Wilcoxon） |
| research/concorde_metaopt/meta_learning/m5_runner.py | 既有统计/端点映射复用 | 已存在 | :95 ENDPOINT_ROW_KEYS 映射；:2125-2160 统计入口 |

> 当前 HEAD c0cb2cd 没有 S1 formal 运行目录、run_records.jsonl 或 run 结果图；工作树中 family_v3.py、s1_analysis.py、s1_runner.py、task_family.py、test_meta_learning_family_v3.py 的未提交改动由 A1/A6 并发产生，**不是 A4 修改**。本表“存在”仅指源码/计划文件，不代表 S1 验收通过。

## 7. 阶段门与交付证据包

阶段门（v4，严格顺序）：

    A1/A6 修复 → Lead commit V4
      → A1 干净 detached worktree 生成 S0-3（两进程逐字节一致）
        → Lead 将 S0-3 冻结包写入仓库并提交
          → A2 重建正式工件 + readiness + K=5 克隆率复核
            → A5 phase3 审阅（v4 包 + 工件 + pair/C5-B + M01/M02/M04）
              → A3 隔离审计
                → A5 APPROVE_FOR_S1_RUN + Lead 书面授权
                  → A2 执行 21,000 formal run
                    → A5/A3 复核 → Lead 发布 Issue #7 中文回执

当前位置：**S0-3 尚未冻结、A5 phase3 未开始**；旧 phase2 APPROVE 已收窄，APPROVE_FOR_S1_RUN 与 Lead formal 授权均未取得。readiness/诊断不得读取新 meta_test/meta_test_ood。

交付证据包（计划路径；当前均未产生）：

| 证据 | 内容 | 关联 S1 | 当前状态 |
|---|---|---|---|
| run_config.json | 网格、B/K、五臂、seeds、v4 冻结输入摘要、code_sha | S1-02/S1-12 | BLOCKED（formal 未授权） |
| run_records.jsonl | 每 run 字段、budget 账、endpoint_values、physics、digest | S1-01..S1-12 | BLOCKED |
| identifiability_report.json | pair 级 structural_status/threshold、pair_status_counts | S1-05/S1-09 | PARTIAL（组级报告已存在；pair 级待实现） |
| summary.json / aggregate.json | 聚合、C1–C5、C5 结构排除计数、null 率、结论层 | S1-09 | BLOCKED |
| statistics.csv / s1_identifiability_table.csv | 9 端点主表与 pair 表 | S1-09 | BLOCKED |
| train_val_test_split.json | 120 tasks 五 split 引用 S0-3 冻结包 | S1-02/S1-12 | BLOCKED |
| data_manifest.json / raw_digest_manifest.json | 文件 SHA256、code_sha、复算记录 | S1-12 | BLOCKED |
| figures/*.png + figure_data/*.csv | 7 类规范图与图数据；无数据标 NOT_RUN | S1-09/S1-12 | BLOCKED |
| SHA256SUMS.txt | 交付目录校验清单 | S1-12 | BLOCKED |
| 中文报告 | 结果/负结果、统计、限制、无物理声明 | S1-12 | BLOCKED |
| A5/A3 审查记录 | S1 rev2 已出 CHANGES_REQUESTED；phase3 与隔离审计待做 | S1-08/S1-10 | A5 rev2 DONE（CHANGES_REQUESTED）；phase3 BLOCKED |

验收 12 条（执行计划 §9，当前均未按 v4 执行）：

1. 768 tests 全绿；A5 rev2 已在 c0cb2cd 复跑 OK(skipped=1)，但 v4 修复后必须重跑，**不得引用旧数字作为 v4 证据**。
2. 40 组五臂×K×B 预算测试 billable=B；当前仅代码/单测层，未跑正式 40 组合。
3. 9 端点键/禁用别名/null/摘要不一致负控；代码层存在，v4 待重验。
4. 统计检验单测；代码层存在，pair/C5-B 待补。
5. 冻结输入篡改、预算不一致、K=0 clone 误入主分析 fail-closed；v4 包未到，NOT_RUN。
6. 确定性 bundle 两跑一致、200 runs×3、K=0 逐字节等价；formal 未跑，NOT_RUN。
7. physical_call_count=0；代码层 guard，无 formal 运行证据。
8. 0 主机绝对路径、旧 M2/M5/M6 工件不变、PR 边界不变；A4 文档为相对路径，旧工件未触碰。
9. v4 holdout 隔离：S0-3 两进程一致、三 split 逐位相同、TE/OD fingerprint 与 v3 官方包 120 个零交集（legacy 280 task_id 仅 task_id 零交集）；NOT_RUN。
10. pair-level/C5-B：identifiability_report 字段/pair_status_counts、analysis 消费、C5 不进 Holm、可估计任务<10 固定结论；PENDING。
11. 正式工件与 readiness：v4 提交后干净树重建、artifact sha 绑定、A2 readiness PASS；BLOCKED。
12. 回执披露：污染/H1/C5/旧 APPROVE 收窄/0 物理/未合并 main；待 Lead 发布。

## 8. 风险、缺口与待决策

| ID | 风险/缺口 | 影响 | 缓解/下一步 | 状态 |
|---|---|---|---|---|
| R-01 | S1 代码已落盘但 A5 rev2 判 CHANGES_REQUESTED（2 blocker/4 major/6 minor） | 当前实现不可验收 | A1/A6 按 A5 rev2 与 v4 裁定修复；A5 phase3 复审 | OPEN |
| R-02 | m5_arms K-shot 闭环缺口已代码修复（B03 closed），但 C5 结构克隆（B02）使适应增益不可辨识 | 不能宣称 FOMAML-KSHOT 优于 ZERO | S1-05/S1-09 实现 pair-level/C5-B；不把 C5 当 benefit/harm | OPEN（B02） |
| R-03 | A5-M02：identifiability_report 仅组级，analysis 未消费 | C5 结论可能被误报 | 按 V4-04 增 pair 字段与消费校验，formal 缺失 fail-closed | OPEN |
| R-04 | v4 文档（合同/计划/矩阵/S0 矩阵）尚未 commit/push | 实现/验收口径可能漂移 | Lead 在阶段 1 提交固定 SHA；A4 只写不提交 | OPEN |
| R-05 | 工作树存在 A1/A6 并发未提交改动（family_v3.py、s1_runner.py、s1_analysis.py、task_family.py、测试） | A4 文档可能引用到未固定状态 | A4 只读并以 c0cb2cd 为基线；Lead 在阶段 1 收口并固定 SHA | OPEN（并发） |
| R-06 | 统计计划 v1.1 仍写“待 A5 复审”，未同步 C5-B/图面英文 | 文档口径滞后 | 由 Lead/A2 在 formal 前修订；本任务未改 | OPEN（文档 minor） |
| R-07 | 21,000 runs 约 12h、1,920,000 次合成评价 | 资源/时间未实测 | 先 pilot；正式 run 前 Lead 确认预算与停止条件 | OPEN |
| R-08 | 7 类图与 figure_status 尚无数据 | 无数据不得绘虚构曲线 | A6 仅用真实 formal 数据；无数据标 NOT_RUN；A5 审图 | OPEN |
| R-09 | 旧 S0-2 holdout 已被读取（B01：608 条/3 任务；8/20 入内存） | 旧包不能用于确证 S1 | 旧包只读/负控；S0-3 重播种；A5 phase3 暴露扫描 | OPEN（须 S0-3） |
| R-10 | 旧 M2/M5/M6 与 PR #3/#6 边界 | 误合并/误改会破坏历史证据 | A3 审计；main 不合并；旧 run 只读；仅 Lead 发布 | OPEN（A3 持续） |
| R-11 | 物理调用与 Issue #4 门禁 | S1 合成结果可能被误标为真实气动证据 | 报告强制 synthetic/lifting 标注；physical=0；#4 门禁不变 | OPEN（持续） |
| R-12 | S0-3 包尚未生成，v4 冻结值不可预填 | 早期文档若预填哈希将与实际不符 | 本矩阵不预填 v4 哈希；待 A1 生成后由 Lead 提交 | OPEN |
| R-13 | 正式工件未从 c0cb2cd 干净树重建（M01） | 旧 readiness 不能作为 v4 formal 依据 | V4-03：v4 提交后干净树重建；旧 readiness 标 BASELINE_989FC0A | OPEN |

待决策：
1. A1/A6 修复与 Lead commit V4 的时点、责任人（R-V4-05 阶段 1）；A4 不改代码。
2. S0-3 冻结包生成（A1 干净 detached worktree、两进程逐字节一致）与 Lead 提交时点（R-V4-01/R-V4-05）。
3. A5 phase3 对 M03/M04 与 8 个旧 minor 的最终关闭口径；phase2 APPROVE 仅历史记录。
4. 统计计划 v1.1 是否同步 C5-B/图面英文/readiness 口径（本任务写范围外，需 Lead 决定）。
5. 旧 S0-2 包与旧 readiness 的归档标识（BASELINE_989FC0A）及是否保留历史对照说明。
6. Issue #7 回执必须披露 B01/B02/旧 APPROVE 收窄/0 物理/未合并 main（R-V4-06），由 Lead 发布。

## 9. 读取记录

- Issue #7：GitHub 只读；读取时间 2026-11-05T11:49+08；state=open；正文落盘 <EXT>/d12d006/a4/raw/issue7_body.txt；读取时 comments=0，其后 Lead 发布 S0-2 回执 6653167378（现 1 条评论）。
- Issue #4：state=open，comments=15；最新评论 6647827491（D-12D-006）；S1 不改变 #4 物理门禁。
- Issue #5：state=open，comments=3；最新终态回执 6643119583（2026-11-04T21:55:56Z）。
- PR #3：open、merged=false、head=e5140fc；PR #6：open、merged=false、head=ff6280f；PR #7 不存在（404）；main=ec65e5a 未合并。
- 旧 S0-2 冻结包：research/concorde_metaopt/optimization_runs/p4ra-s0-2-freeze-20261105T072500Z（11 文件；SHA256SUMS.txt 8 个 payload 校验；freeze_summary.json git_sha=766a59c、code_sha=c929609a…、radius_base=0.64、CALIBRATED）；**只读，不得用于确证**。
- A5 phase2：<EXT>/p4-route-a/a5/S0_2_A5_review_phase2.md（sha256 ea9b2eb7…；0 blocker/0 major/8 minor；604 tests OK(skipped=1)/37.687s；determinism 29/29；physical=0）。
- A5 S1 rev2：<EXT>/p4-route-a/a5/S1_code_review_rev2.md（sha256 d5a0979a…；269 行；CHANGES_REQUESTED；2B/4M/6m；审阅 c0cb2cd；768 tests OK(skipped=1)）。
- v4 裁定：docs/planning/p4_route_a_s1_v4_remediation_rulings_20261105.md（sha256 f71e32a9…；84 行；R-V4-01..06）。
- A3 phase2：<EXT>/p4-route-a/a3/S0_2_phase2_isolation.md（sha256 23bac611…；PASS 11/11；三提交单父非 merge；旧 M2/M5/M6 tree_agg 未变；0 solver）。
- 本地 S1 工作树：HEAD=c0cb2cd8f74b2eaeb346806c059f28f603ca30fb，branch research/p4-route-a-s1；S1 代码/测试已存在；工作树有 A1/A6 并发未提交改动（非 A4）；v4 裁定文件未跟踪；A4 未 commit/push，未改代码或冻结包。
- A4 本任务仅改四份文档并新增简报；未执行物理计算、未启动求解器、未做 GitHub 写操作、未读取新 meta_test/meta_test_ood 结果。

## 10. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4（task-217） | 首次生成 S1-01..S1-12 需求→实现文件/测试/验收证据矩阵；映射 S0-2 冻结输入、A5 phase2 §7 六前置、统计计划 v1.1 与阶段门；明确 S1 未实现、所有运行/图表 NOT_RUN，无算法结果、无物理调用 |
| v1.1 | 2026-11-05 | A4（task-231） | 按 A5 S1 rev2 与 R-V4-01..06：S1 状态改为 IN_PROGRESS/PARTIAL/BLOCKED；新增 §2.2 v4/S0-3 输入、§4.2 V4-01..06、§4.3 B01/B02/M01..M04 与 minor 映射；C5-B/pair-level、readiness 不读 test/OOD、正式工件重建、A5 phase3 门；旧 S0-2 标只读且不得用于确证；未 commit/push、未执行物理计算、未读取新 holdout 结果 |
