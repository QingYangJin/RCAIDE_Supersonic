# P4 路线A S1 需求矩阵（Issue #7 · S1 K-shot→BO 闭环 → 实现文件 / 测试 / 验收证据 / 状态）

> 文档性质：S1 需求到实现文件、测试与验收证据的映射表，供 Lead、A5、A6 与 A1 对齐口径。**A5 phase3 复审已给出 CHANGES_REQUESTED（2 blocker / 2 major / 6 minor）；S1 确证性 formal 未获批准。S0-3 冻结包结构/完整性 PASS，但其冻结 preregistration 缺 R-V4-08-02 要求的三个必填块，已不能满足 formal；须按 R-V4-08 生成 S0-4。A1 merge 子命令在当前工作树有未提交实现（+483 行）与 15 个未提交 merge 测试（+416 行），A6 v4c 分析整改有未提交代码（+478 行、尚无测试改动），均未提交、未被 A5 审。S1_RUN 仍为 NOT_APPROVED，21,000 formal 未运行。本文件不含新的算法结果，不构成新的物理授权或预算批准。**
> 依据：Issue #7 正文（D-P4-003，§2 S1 四条与 §3–§4 约束，2026-11-05 读取）+ docs/planning/p4_route_a_stage_improvement_plan_20261105.md（V1.0，commit a331639e）+ docs/planning/p4_route_a_s1_execution_plan_20261105.md（v1.3，R-V4-07 并行分片/merge）+ docs/planning/p4_route_a_s1_statistical_plan_20261105.md（工作树 R-V4-08-01 同步版）+ docs/planning/p4_route_a_s0_design_contract.md（工作树 v1.3）+ docs/planning/p4_route_a_s1_v4_remediation_rulings_20261105.md（R-V4-01..06）+ docs/planning/p4_route_a_s1_v4b_parallel_rulings_20261105.md（R-V4-07）+ docs/planning/p4_route_a_s1_v4c_phase3_rulings_20261106.md（R-V4-08）+ A5 phase3 复审 <EXT>/p4-route-a/a5/S1_phase3_review.md（CHANGES_REQUESTED；2 blocker / 2 major / 6 minor；sha256 a0ed7a43f9e793a81e2e6d1090393b9a7d296652784115aa007ffd59bb3e7fa7）+ S0-3 冻结包 p4ra-s0-3-freeze-20261105T155925Z + A2 readiness v4b + A2 15 分片 dry-run + A3 v4 holdout 暴露扫描定稿。
> 读取时点：2026-11-06T03:05+08；S1 工作树 HEAD=a836699ad2fd68f4e6f924d46b3f37ab7798dd95，branch research/p4-route-a-s1；工作树修改：Lead 合同/执行计划/统计计划、A4 本矩阵、A1 s1_runner.py（未提交 merge +483 行）、A1 test_s1_runner.py（未提交 merge 测试 +416 行）、A6 s1_analysis.py（未提交 v4c 代码 +478 行）；未跟踪：R-V4-07 与 R-V4-08 裁定文件；A4 未触碰代码；未读取新 meta_test/meta_test_ood 结果。
> 状态口径：IMPLEMENTED_PENDING_V4C＝实现已落盘但受 A5 phase3 blocker 约束，待 A1/A6 v4c 修复、提交与 A5 phase4；CHANGES_REQUESTED_B02＝A5 phase3 的 B02 Holm 族冲突直接适用于该项；TESTED_PENDING_V4C＝在 a836699 跑过 829 tests，但工作树新增代码/测试未进入该次运行；PARTIAL＝部分实现或验收证据不足；BLOCKED＝依赖 S0-4/A5 phase4/Lead 授权；PENDING＝尚未产生；NOT_RUN＝未执行；NOT_APPROVED＝未获书面批准；READ_ONLY_VERIFIED＝仅输入或历史事实经 A4 只读核对（不代表验收通过）；DRY_RUN_PLANNED_NOT_EXECUTED＝A2 只做计划核验、未启动 run。旧 S0-2 phase2 APPROVE 与 A5 phase3 之前的任何“可放行”表述均已收窄，不能作为 S1 formal 依据。

## 1. 当前状态与硬边界

| 检查项 | 当前事实 | 来源/证据 |
|---|---|---|
| S0-2 阶段门 | 旧 S0-2 冻结包 COMPLETE（历史）；A5 phase2 APPROVE_FOR_S1_FORMAL 只对旧静态/测试范围有效，确证性用途已被 A5 S1 rev2 M03 与 phase3 收窄；不能作为当前 S1 formal 放行依据 | A5 phase2 报告；A5 S1 rev2 M03；A5 phase3 报告 |
| S0-3 v4 冻结包 | **结构/完整性 PASS，但不能满足 formal**：p4ra-s0-3-freeze-20261105T155925Z，提交 fecd095；8 payload 两进程逐字节一致、SHA256SUMS 8/8；仅 meta_test 20 + meta_test_ood 10 重播种；与 v3 的 120 个 fingerprint 交集 0。A5 phase3 发现冻结 preregistration.json 缺 holdout_package / c5_policy / structural_identifiability 三键，holdout_splits 为数组而非 object；S0-3 降为历史只读，须由 S0-4 取代 | 冻结包；A5 phase3 B01；R-V4-08-02/-03/-05 |
| S0-4 冻结包 | **NOT_GENERATED**：尚未在最终代码 commit（含 merge）的干净 detached 树上生成；生成后 code_sha 必须等于 package_code_sha，旧 S0-3 只读且新 verifier 拒绝 formal | R-V4-08-03/-05；task-249/task-250 |
| S1 实现 | **CHANGES_REQUESTED（v4c 整改中）**：a836699 的 s1_runner.py 1,800 行、s1_analysis.py 4,640 行、s1_figures.py 632 行及两份测试为已提交基线；当前工作树另有 A1 merge +483 行、A1 merge 测试 +416 行、A6 v4c 分析代码 +478 行，均未提交；A5 phase3 在 a836699 复跑 829 tests OK(skipped=1)，但没有覆盖工作树新增代码/测试 | a836699；A5 phase3 报告；工作树 git status/diff |
| A5 phase3 复审 | **CHANGES_REQUESTED**：2 blocker（B01 prereg 三键缺失；B02 Holm 族四口径不一致）+ 2 major（M01 code_sha 漂移；M02 legacy/非确认包未拒绝）+ 6 minor；S1 确证性 formal NOT APPROVED | <EXT>/p4-route-a/a5/S1_phase3_review.md；sha256 a0ed7a43… |
| S1 正式 run | **NOT_APPROVED，未执行**；21,000 runs / 1,920,000 次合成评价仅为计划数；须 A1/A6 v4c 修复 + Lead commit C + S0-4 两进程冻结 + Lead commit D + A2 readiness v4c + A3 审 C/D + A5 phase4 final gate + A5 APPROVE_FOR_S1_RUN + Lead 书面授权 | 执行计划 v1.3；R-V4-08-06；A2 dry-run |
| holdout 污染 | **RESEEDED / 旧 S0-2 只读**：旧 S0-2 的 36 个 run_records（608 条）与 8/20 内存读取已在 v4 重播种中退役；S0-3 holdout 未打开、未产生真实评估；A3 v4 暴露扫描定稿 PASS（0 真实 meta_test/OOD 记录） | A5 S1R2-B01；S0-3；A3 v4 暴露扫描定稿 |
| K-shot 闭环 / C5-B | 代码层已改造（m5_arms 传递 support/k_shot）；C5-B pair-level 字段、schema v2、阈值 0.90 与 analysis 消费已在 7c1e2ce 落盘；但 A5 phase3 B02 指出 Holm 族定义仍有四处不一致，A6 工作树尚未提交；无正式 pair 结果，不得宣称适应增益/损害 | m5_arms.py；s1_analysis.py；A5 phase3 B02 |
| 15 分片 / merge | **A1 工作树未提交初版**：s1_runner.py +483 行、test_s1_runner.py +416 行（15 个 MergeSubcommandTests）；尚未提交、尚未被 A5 审；A2 task-246 已完成 15 分片 dry-run（21,000 并集、missing/extra/duplicate=0、physical=0，未执行），但 dry-run 基于 S0-3，S0-4 后需重跑 | R-V4-07；A1 工作树 diff；A2 S1_shards_plan.md / logs/dry_run.log |
| 物理调用 | physical_call_count=0；S1 不启动 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag；Issue #4 物理门禁不变 | Issue #7 §3；冻结包；A3 v4 扫描 |
| Issue #4 门禁（交叉引用） | GEO-12D=PARTIAL、LF-M2.02=NOT_VALIDATED、HF-M2.02=PARTIAL、BODY-CORR=BLOCKED、MISSION-DATA=PARTIAL、BUDGET=GATED；approved_for_next_stage=false；A 类 14/20 已用、剩余 6 次 CLOSED 不结转；B 类 12 次 LOCKED；C 类 0/4；Issue #4 最新评论 6652497663（Z-01 整改进展） | Issue #4 只读；A4 facts.csv（D-12D-006） |
| 旧证据与 main | 旧 M2/M5/M6 与旧 S0-2 包只读；main 不合并；PR #3/#6 保持 open 不合并 | A3 phase2；SAFE-05；GitHub 只读 |
| 发布权限 | 仅 Lead 可发布 GitHub；A4 本任务只读，未评论/改 Issue/建 Issue | Issue #7 §4；A4 角色约束 |

> 结论：A5 phase3 已实际否决当前 S1 确证性放行（CHANGES_REQUESTED）。当前不是“等一个 verdict”，而是“B01/B02/M01/M02 四项必须修复并重新冻结 S0-4，A1 merge 与 A6 分析改动必须提交并经 A5 phase4 复审”。S1 当前不可验收、不可启动 formal；下文状态为当前映射，不得引用为已通过证据。

## 2. 冻结输入（旧 S0-2 只读 + S0-3 历史包 + S0-4 待生成）

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
| 计划规模 | 21,000 runs；1,920,000 次合成评价；B∈{64,128}；K∈{0,1,3,5} | S1 统计计划工作树版 |

> 旧包只读：不得改写、不得把其 meta_test 重新当作未读盲测；其 meta_test 已被 36 个 run_records（608 条记录）与 8/20 任务的内存读取消耗（A5 S1R2-B01）。旧包仅用于历史复现、负控与格式对照。

### 2.2 S0-3 v4 冻结包（结构 PASS；formal 不合格，历史只读）

| 冻结项 | 实际值 | 来源 |
|---|---|---|
| 冻结包 run_id | p4ra-s0-3-freeze-20261105T155925Z | freeze_summary.json |
| 包内容/校验 | 11 文件/556K；8 个 payload + SHA256SUMS + README；sha256sum -c 8/8 OK | 冻结包；A3 v4 扫描 |
| git_sha | 7c1e2ce9eb4aac1725003537fdbaf4a3425be5cb | freeze_summary.json |
| code_sha | c926653d83a57164b8b3079ea7cf2f8ae944dd92f7a971041d5b87208f67bf9e | freeze_summary.json；A5 phase3 M01 |
| family_id / family_version | F-QE-feasible-v3 / p4ra-family-v4 | frozen_family.json；R-V4-01 |
| holdout_seed | 20261106 | frozen_family.json；R-V4-01 |
| family_fingerprint | a1f9462c35ea641d0559485354c63b47eec2e6fb4696e86f94efa1f3d19daf2e | freeze_summary.json |
| split_hash | cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae | freeze_summary.json |
| prereg_digest | aa806767445421335874322321145af4b5ed5bc52826dc732a05c0f8f3feb948 | freeze_summary.json |
| analysis_plan_digest | 37eee53c9018fce34e414fa553ad3986a2d1be87d10409bc28e4f697b63588df | freeze_summary.json |
| radius_base / 校准状态 | 0.64 / CALIBRATED | frozen_family.json |
| 五 split 与任务数 | meta_train 60 / meta_validation 20 / meta_test 20 / meta_test_ood 10 / negative_control 10；共 120 tasks | frozen_family.json；meta_task_split.json |
| 重播种范围 | 仅 meta_test 20 + meta_test_ood 10；其余三 split 逐位不变 | v3_comparison；A3 v4 扫描 |
| 确定性 | 两进程 8 payload 逐字节一致；determinism_report status PASS、failed_checks=[] | determinism_report.json |
| v4 vs v3 隔离 | 90 个非 holdout fingerprint 相同、30 个 holdout 全变、与 v3 120 fp 交集 0；task_id 集合与 split_hash 相同；family_fingerprint e56e6921…→a1f9462c…；legacy 280 task_id 仅 task_id 零交集（fingerprint 缺失，TASK_FINGERPRINT_INTERSECTION_UNDETERMINABLE） | v3_comparison；v3_isolation_report |
| 物理调用 | 0 | 冻结包；A3 v4 扫描 |
| formal 合规 | **不合格**：冻结 preregistration.json 278 行/50 键，缺 holdout_package / c5_policy / structural_identifiability；holdout_splits 在 :142-145 为数组而非 object；冻结包无 confirmatory_eligible=true；A5 探针 verify_preregistration_v3 返回 True 且 missing_contract_fields 三键；s1_runner.py 旧入口 :179 会接受 | A5 phase3 B01/M01/M02；R-V4-08-02/-03/-04 |

> S0-3 包已提交且结构/完整性 PASS，但**已不能满足确证性 formal**；本矩阵不引用任何新 meta_test 结果，且不得将 A3 的暴露扫描 PASS 当作 A5 验收结论。S0-3 之后仅作历史只读/格式对照；新包 S0-4 必须按 R-V4-08-02/-03/-05 生成。

## 3. S1 需求矩阵（S1-01..S1-12）

| ID | 来源 | 要求与验收条件 | 实现文件（a836699 基线 + 当前工作树） | 测试/验收证据（当前） | 状态（v4c 口径） | 责任/依赖 |
|---|---|---|---|---|---|---|
| S1-01 | Issue #7 §2 S1-1；执行计划 §2、§3.2；合同 §4.2 | K 次目标任务支持样本的特征与目标/约束标签进入内循环，用适应后代理评分；query 标签、解析最优点不可见；代理预测不得写入 BO 真实 observations；K=0 退化为旧行为 | s1_runner.py 内循环；m5_arms.py 已传 support_features/support_targets 与 k_shot；adaptation.py 复用 | a836699 的 829 tests；A5 phase3 未对 S1-01 本身提出独立 blocker，但整体 CHANGES_REQUESTED；无正式结果 | IMPLEMENTED_PENDING_V4C | A1；A5 phase4 |
| S1-02 | Issue #7 §2 S1-2；合同 §4.2；统计计划 §3 | B∈{64,128}、K∈{0,1,3,5}；五臂共享同一 K 次目标任务评价，K 次必须计入 B；每 run 满足 K+(8−K)+(B−8)=B；计划 21,000 runs / 1,920,000 评价；非物理代理时间单列 | s1_runner.py 网格与预算账；run_records.jsonl；A1 工作树 merge +483 行 | A2 20-run bench billable=1280/true=1250；A2 15 分片 dry-run 21,000 并集、0 missing/extra/duplicate；merge 测试 15 个未提交、未跑；A1 v4c 未开始 | IMPLEMENTED_PENDING_V4C | A1+A2；A5 phase4 |
| S1-03 | Issue #7 §2 S1-2；合同 §4.2；A5 phase2 §7③ | 8 个初始点=K 个支持点+8−K 个新点；之后普通 BO B−8 次；DE 的 8−K 新点并入 population；K=0 复现旧初始化行为 | s1_runner.py 初始化路径；run_records.initial_designs | a836699 的 829 tests 含初始化/来源标签用例；A2 CLONE 2 对、K=0 复现待正式复验 | IMPLEMENTED_PENDING_V4C | A1；A2 复核 |
| S1-04 | Issue #7 §2 S1-3；A5 phase2 §7③ | 五臂 RAND-BO / PRETRAIN-KSHOT-BO / FOMAML-ZERO-BO / FOMAML-KSHOT-BO / DE；同任务、同种子、同候选池、同约束；仅初始化路径不同 | s1_runner.py arm registry；m5_arms.py 旧臂复用 | A2 readiness v4b 20-run bench 2×20 PASS；正式 40 组合未运行 | IMPLEMENTED_PENDING_V4C | A1+A2；A5 phase4 |
| S1-05 | Issue #7 §2 S1-3；执行计划 §3；R-V4-02 | 克隆识别、缓存与 null 规则一致；K=0 的 FOMAML-KSHOT-BO 登记 CLONE_OF_FOMAML-ZERO-BO；K>0 每个（task,B,K,meta_seed）组按初始设计行 digest overlap_rate≥0.90 判 STRUCTURALLY_IDENTICAL；C5 不做 benefit/harm、不进 Holm | s1_runner.py clone/cache；s1_analysis.py pair-level（schema p4ra-s1-identifiability-2；三对 REQUIRED_PAIRS；阈值 0.90；pair_status_counts；C5_ESTIMABLE_MIN_TASKS=10） | 7c1e2ce 已落盘 pair 字段/schema/消费与测试；A5 phase3 B02 指出 Holm 族定义仍需唯一化；A6 工作树改动未提交、无新增测试；无正式 pair 结果 | CHANGES_REQUESTED_B02 | A1+A6；A5 phase4 |
| S1-06 | Issue #7 §2 S1-3；执行计划 §3 | 训练 episode 支持样本数与部署 K 匹配（5/10 或混合 K）；旧 128 样本内循环仅作消融基线，不得冒充新 K-shot 闭环 | 训练/episode 采样路径；s1_runner.py 配置；adaptation.py 复用 | a836699 的 829 tests 含 episode 支持数用例；A5 phase3 未对 S1-06 本身提出独立 blocker | IMPLEMENTED_PENDING_V4C | A1+A2；A5 phase4 |
| S1-07 | Issue #7 §2 S1-4；A5 phase2 §7①②④；执行计划 §9 | 先做零物理单测：query/任务泄漏负控、真实合成评价预算精确一致、K>0 确实改变模型参数与初始选点、失败路径 fail-closed；physical_call_count=0 | test_s1_runner.py；s1_runner.py/s1_analysis.py 前置断言 | A5 phase3 在 a836699 复跑 829 tests OK(skipped=1)/161.811s；A1 工作树新增 15 个 merge tests 未进入该次运行；A6 改动无测试；A5 verdict=CHANGES_REQUESTED | TESTED_PENDING_V4C | A1+A6；A5 phase4 |
| S1-08 | Issue #7 §2 S1-4；执行计划 §6、§10；A5 phase2 §7② | 验证集小样本 pilot 通过后，A5 phase4 书面 APPROVE_FOR_S1_RUN 且 Lead 授权，才执行新独立 holdout；正式 meta_test 一次性打开，之后禁止调参/选臂/选终点；允许无改进 | s1_runner.py pilot/holdout 模式；s1_analysis.py 一次性评估入口 | S0-3 结构 PASS 但 formal 不合格；S0-4 未生成；A5 phase3 CHANGES_REQUESTED；A5 phase4 未开始；Lead 未授权；无 pilot/formal 记录 | BLOCKED（等待 v4c 修复+S0-4+A5 phase4+Lead 授权） | A1+A6；A5+Lead |
| S1-09 | Issue #7 §2 S1-4、§4；统计计划 §3–§5；R-V4-04；R-V4-08-01 | 按 B=64/128 分层报告主终点；9 个 ENDPOINT_ROW_KEYS 精确列键，禁用别名；不可行保留 null；任务为一级统计单位；OOD/负控不入主统计；7 类规范图（图面英文，避免中文字体缺失）；Holm 族唯一化 | s1_analysis.py；s1_figures.py；statistics.csv；aggregate.json；A6 工作树新增 formal/exploratory 校验与动态 Holm 族信息 | a836699 的 829 tests 含端点/聚合/图键用例；A6 工作树新增代码无测试；B02 要求族键=(primary_endpoint,budget_B,K)、C1–C4、C5 永不进族、动态族大小；A5 phase3 未通过 | CHANGES_REQUESTED_B02 | A6；A2 复核；A5 phase4 |
| S1-10 | Issue #7 §2 S1、§4；A5 phase2 §7②⑤；R-V4-06 | 不得为让 MAML 获胜调参；负结果如实记录；正式 meta_test 打开后不得按效果改任务/终点/剔除；旧 M2/M5/M6 只读，main 不合并，PR #3/#6 不合并 | s1_analysis.py 预注册校验；文档/报告口径；A3 只读审计 | S0-3 已冻结；A3 v4 暴露扫描 PASS；Issue #7 尚无 S1 phase3 回执（最新仍是 S0-2 完成回执 6653167378）；统计计划工作树已按 R-V4-08-01 改 :100 | PARTIAL（约束/证据已就位；回执未发布；合同元数据 lag） | A1+A2+A5+A4；A3 |
| S1-11 | Issue #7 §1 缺口（m5_arms.py）；执行计划 §3.1；A5 rev2 B03 | 修复 score_m5_init_designs() 无 support 参数、run_m5_bo_arm() 不传 k_shot/support 的闭环缺口；K=0 与旧行为逐位一致 | m5_arms.py；s1_runner.py 调用层；test_s1_runner.py | a836699 已含修复；829 tests 通过；A5 phase3 未对 S1-11 本身提出独立 blocker，但整体 CHANGES_REQUESTED | IMPLEMENTED_PENDING_V4C | A1；A5 phase4 |
| S1-12 | Issue #7 §2 S1、§4；执行计划 §5、§9；A5 phase2 §7①⑥ | 产物齐全：preregistration.json、run_config.json、train_val_test_split.json、data_manifest.json、SHA256SUMS.txt、run_records.jsonl、statistics.csv、identifiability_report.json、图数据/PNG、中文报告；code_sha 以 LF clean checkout 为准；缺数据标 NOT_RUN | s1_runner.py 输出目录；s1_analysis.py；s1_figures.py；中文报告 | S0-3 冻结包、A2 readiness v4b 已备；formal run 未执行，无正式产物；S0-4 未生成 | PARTIAL（输入/readiness 已备；formal 产物 NOT_RUN） | A1+A2+A6+A4；Lead 发布 |

> 说明：状态为当前实现映射，不是验收通过。829 tests 是 A5 phase3 在 a836699 的复跑结果；当前工作树的 A1 merge 代码/15 个 merge tests 与 A6 v4c 代码都不在该次运行中。A5 phase3 已给出 CHANGES_REQUESTED，S1-08/S1-12 在 v4c 修复、S0-4、A5 phase4 与 Lead 授权前不得放行 formal。

## 4. A5 phase2 §7 前置映射（A5PRE-01..06）与 v4/A5 rev2/phase3 整改项

### 4.1 A5 phase2 前置（旧阶段门，保留追溯）

| ID | A5 §7 前置（摘要） | 落地实现/检查 | 验收证据（当前） | 关联 S1 | 状态 |
|---|---|---|---|---|---|
| A5PRE-01 | ① S1 分析/汇总强制校验 ENDPOINT_ROW_KEYS 9 键与 analysis_plan_digest，补 null/键名不一致负控 | s1_analysis.py 启动校验；test_s1_analysis.py | a836699 的 829 tests 含端点/负控用例；A6 工作树新增三键/formal 校验但无测试；A5 phase3 CHANGES_REQUESTED | S1-09/S1-12 | PARTIAL_PENDING_V4C |
| A5PRE-02 | ② 三方 sha256/fingerprint/split_hash 校验后一次性构造并评估 meta_test/meta_test_ood；之后禁止调参/选臂/选终点 | s1_runner.py 预检；s1_analysis.py 预检；A5 审查记录 | S0-3 结构 PASS 但 prereg 缺三键、A5 phase3 判定 formal 不合格；S0-4 未生成；holdout 未打开；A3 v4 扫描 PASS | S1-02/S1-08/S1-10 | PARTIAL_PENDING_S0_4 |
| A5PRE-03 | ③ 五臂×K{0,1,3,5}×B{64,128} 逐 run 断言 billable=B；K=0 FOMAML-KSHOT-BO 登记 CLONE 排除因果推断 | s1_runner.py 预算断言；run_records.identifiability | 829 tests 含预算/CLONE 用例；A2 20-run bench billable=1280/true=1250；A2 15 分片 dry-run 21,000、b128_k0=0；正式 40 组合未运行 | S1-02/S1-03/S1-04/S1-05 | PARTIAL_PENDING_A2_RERUN |
| A5PRE-04 | ④ physical_call_count=0；不得启动 VSPAERO/SU2/RCAIDE Mission/CFD；#4 门禁不变 | s1_runner.py guard；报告口径；A3 审计 | 冻结包/A2/A3 均记 physical=0、0 solver；A2 dry-run physical_call_count=0；无 formal 运行证据 | S1-07/S1-12 | READ_ONLY_VERIFIED（当前事实） |
| A5PRE-05 | ⑤ 旧 M2/M5/M6 只读；main 不合并；PR #3/#6 不合并 | A3 只读审计；A4 矩阵记录；无代码改动 | 旧 run tree_agg 未变；PR merged=false；main/旧分支 SHA 未动 | S1-10/S1-12 | READ_ONLY_VERIFIED（当前事实） |
| A5PRE-06 | ⑥ code_sha 以 LF clean checkout 为准 | run_config.json；data_manifest.json；报告 | A2 在 a836699 detached 干净树重建 200/50 工件并通过 readiness v4b；但 A5 phase3 M01 发现冻结 S0-3 code_sha 与 a836699 当前 package_code_sha 漂移；formal run_config 尚未生成 | S1-02/S1-12 | CHANGES_REQUESTED_M01 |

### 4.2 R-V4 裁定整改项（V4-01..V4-06）

| ID | 裁定/要求（摘要） | 落地文档/代码 | 验收证据 | 关联 S1 | 状态 |
|---|---|---|---|---|---|
| V4-01 | 选 H1：只重播种 meta_test 20 + meta_test_ood 10；holdout_seed=20261106；family_version=p4ra-family-v4；S0-3 新包替代 S0-2；旧包只读 | 合同 §3/§5/§6.2/§7；执行计划 §2；本矩阵 §2.2 | S0-3 包两进程一致、fingerprint 零交集、三 split 逐位相同；但 A5 phase3 判定其 prereg 缺三键、formal 不合格 | S1-02/S1-08/S1-10 | SUPERSEDED_BY_R_V4_08_02（S0-4 取代） |
| V4-02 | C5-B：pair 级 overlap_rate≥0.90 判 STRUCTURALLY_IDENTICAL；C5 不做 benefit/harm、不进 Holm；可估计任务<10 → NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY | 合同 §7.2；执行计划 §6 第 10 条；s1_analysis.py；本矩阵 S1-05/S1-09 | pair-level 报告 + analysis 消费 + aggregate 排除计数已落盘；829 tests；但 A5 phase3 B02 发现 Holm 族四口径不一致 | S1-05/S1-09/S1-10 | CHANGES_REQUESTED_B02 |
| V4-03 | 正式工件从 v4 代码干净树重建（默认 200/50）；artifact sha 写 readiness/run_config；旧 readiness 标 BASELINE_989FC0A 不可复用 | 执行计划 §7；合同 §9；A2 readiness v4b | A2 独立 detached worktree @ a836699 detached clean；200/50 工件、artifact sha、20-run bench、合成烟测均完成；readiness=READY_PENDING_LEAD_AUTHORIZATION；但 S0-4 需重新生成 | S1-02/S1-12 | PARTIAL_PENDING_S0_4 |
| V4-04 | identifiability_report.json 增 pair 级字段与 pair_status_counts；analysis 必须加载校验；formal 缺失 fail-closed；aggregate/CSV 输出排除计数 | 执行计划 §6 第 11 条、§9；合同 §7；s1_analysis.py | schema p4ra-s1-identifiability-2、三对 REQUIRED_PAIRS、pair_status_counts、C5_ESTIMABLE_MIN_TASKS=10；829 tests；A6 工作树新增消费代码未提交/无新测试 | S1-05/S1-09/S1-12 | IMPLEMENTED_PENDING_V4C |
| V4-05 | 阶段门：A1/A6 修复→Lead commit V4→S0-3 生成/提交→A2 工件/readiness→A5 phase3→A3 隔离→A5 APPROVE_FOR_S1_RUN + Lead 授权→formal | 执行计划 §10；本矩阵 §7；R-V4-08-06 | 已走到 A5 phase3，verdict=CHANGES_REQUESTED；S0-4 未生成；merge 未提交/未审；phase4 未开始 | S1-08/S1-12 | BLOCKED_AT_A5_PHASE3 |
| V4-06 | 文档统一 v4/holdout/C5-B/pair/旧 S0-2 只读；Issue #7 回执须披露污染/H1/C5/旧 APPROVE 收窄/0 物理/未合并 main | 合同/执行计划/本矩阵/S0 矩阵；Lead 回执 | 本矩阵升 v1.3；回执草稿由 A4 起草；Issue #7 最新评论仍是 S0-2 完成回执 6653167378，无 S1 回执 | S1-10 | PARTIAL（文档已同步；回执未发布） |

### 4.3 A5 S1 rev2 findings 映射（B01/B02/M01..M04 + minor；含 phase3 重开状态）

| ID | 等级 | 事实（摘要） | 本矩阵处置 | 状态 |
|---|---|---|---|---|
| S1R2-B01 | blocker | 36 个 run_records 共 608 条 split=meta_test；TE-000/001/003 被读；TE-000..007 共 8/20 入内存；旧 S0-2 holdout 不满足一次性盲测 | S0-3 已重播种（仅 TE/OD）；旧包 §2.1 标只读；A3 v4 暴露扫描 PASS；但 A5 phase3 B01 发现 S0-3 prereg 缺三键，旧结论被重开 | REOPENED_BY_S1R3_B01 |
| S1R2-B02 | blocker | 正式 200/50 工件 K=5 ZERO==KSHOT 初始设计 22/24（K=3 22/24、K=1 20/24）；meta0 K5 B64 8/8 历史逐字节相同 | 7c1e2ce 落盘 pair-level/C5-B 与 analysis 消费；A5 phase3 复核 CHANGES_REQUESTED；不宣称适应增益 | PARTIALLY_CLOSED_REOPENED_BY_S1R3_B02 |
| S1R2-M01 | major | 正式工件未从 c0cb2cd 干净树重建 | A2 在 a836699 detached 干净树重建 200/50；readiness v4b READY；但 A5 phase3 M01 发现 S0-3 冻结 code_sha 与 a836699 当前 package_code_sha 漂移 | REOPENED_BY_S1R3_M01 |
| S1R2-M02 | major | identifiability_report 只有组级 max/mean；analysis 未消费 | 7c1e2ce pair-level 字段/schema/消费；829 tests；但 A5 phase3 M02 发现 formal 未拒绝 legacy/非确认包 | REOPENED_BY_S1R3_M02 |
| S1R2-M03 | major | phase2 APPROVE 对确证用途被 supersede | 本矩阵 header/§1 明确收窄；S1-10 | CLOSED_BY_DOC（phase3 再次确认收窄） |
| S1R2-M04 | major | A1 的 10/24 来自 2/3-step 诊断工件，正式 200/50 为 22/24 | 本矩阵统一采用正式工件 22/24；不再引用 10/24 | CLOSED_LABELED |
| S1R2-m01 | minor | S1 矩阵 stale | 本次 v1.3 重写（仍待 Lead commit） | CLOSED_BY_DOC_V1_3 |
| S1R2-m02 | minor | 执行计划输出清单缺 identifiability_report | 执行计划 v1.2/v1.3 §6/§9 已补 | CLOSED_BY_DOC |
| S1R2-m03 | minor | overlap 分母口径未定 | 合同 §7.2 已写 pair 组与臂对；7c1e2ce 代码实现 | CLOSED_BY_IMPL_PENDING_A5 |
| S1R2-m04 | minor | 合同 4 项歧义 | 合同 v1.3 §3/§5/§7 已补；待 A5 phase4 | PARTIAL |
| S1R2-m05 | minor | 图面英文 | S1-09 已改为“7 类规范图（图面英文）”；执行计划同步；A6 实现 | CLOSED_BY_DOC |
| S1R2-m06 | minor | 旧 readiness 不可用 | V4-03 标 BASELINE_989FC0A 不可复用；A2 已重建 v4b readiness | CLOSED_BY_READINESS_PENDING_A5 |

### 4.4 R-V4-07 并行分片/merge 与 S1_RUN 门禁（v4c）

| 要求 | 规范值/规则 | 当前证据 | 状态 |
|---|---|---|---|
| 15 分片 | 21,000 = 15 片（3 meta_seed × 5 opt_seed 对），每片 1,400 = main 600 + secondary 400 + exploratory 400；同一顶层 run_id，run_group_id 相同 | A2 task-246 已完成 dry-run：15×1,400=21,000；并集 21,000、missing/extra/duplicate=0；集合 sha256 237f2b7e9a81f9365ffeab21d7344ec07ec4d757b94d0e161fe7ccc2ecfe1f74；runs_executed=0、physical=0；该 dry-run 基于 S0-3，S0-4 后需重跑 | DRY_RUN_PLANNED_NOT_EXECUTED |
| merge 子命令 | s1_runner merge：完整 plan 重建、期望集合=分片并集（21,000，missing/extra/duplicate=0）、分层 9,000/6,000/6,000、B128×K0=0、identity/billable/physics=0 校验、按 plan 顺序排序、重算 identifiability、合并 5 产物、merge_manifest、两跑逐字节一致/缩小网格与串行一致 | A1 工作树有未提交 merge 实现：s1_runner.py +483 行；MERGE_MANIFEST_SCHEMA_VERSION='p4ra-s1-merge-manifest-1'（:68）、_merge_key(:1474)、_merge_expected_run_id(:1486)、shard_definitions(:1508)、_merge_record_problems(:1534)、merge_plan_from_args(:1618)、merge_run_shards(:1659)；未提交、未 A5 审 | IN_PROGRESS_UNCOMMITTED |
| merge 测试 | 新增 merge fail-closed/顺序/并集/确定性测试；测试总数不得低于 829 | test_s1_runner.py +416 行、15 个 MergeSubcommandTests（default_merge_plan=21000、15 shards、两 shard 对 serial、执行 shard core 对 serial、missing/extra/duplicate fail-closed、idempotent 等）；未提交、未进入 829 tests 运行 | ADDED_UNCOMMITTED_NOT_RUN |
| A5 merge delta | A5 对 merge 代码/测试/合并产物做独立 delta 复审，合格后方可进入 S1_RUN 授权 | task-247 pending（blocked_by task-245；task-245 已 completed，故当前为 ready、未开始） | PENDING |
| 资源 | 15 进程约 4.6GB；预计 2–3h；A2 串行估算 36.9949h / 8-worker 5.555h；每片预计墙钟约 2.466h | A2 S1_shards_plan.md；R-V4-07 | PLANNED（未实测） |
| S1_RUN 门禁顺序 | A1/A6 v4c 修复→Lead commit C→S0-4 两进程冻结→Lead commit D→A2 readiness v4c→A3 审 C/D→A5 phase4（B01/B02/M01/M02 + merge delta）→A5 APPROVE_FOR_S1_RUN + Lead 书面授权→A2 15 分片 + merge→A5/A3 post-run→Lead Issue #7 回执 | 当前：A5 phase3 CHANGES_REQUESTED；A1 task-249 in_progress；A6 task-250 in_progress；merge 代码/测试未提交未审；S0-4 未生成；A5 phase4 未开始；授权 NOT_APPROVED | BLOCKED |

> 关键边界：A5 phase3 不是“未出结论”，而是 **CHANGES_REQUESTED**；不能把 phase3 当作 phase4 放行。A5 merge delta 与 S0-4 是 R-V4-07/R-V4-08 新增的独立门禁，缺一不得启动 21,000 formal。

### 4.5 A5 phase3 findings 与 R-V4-08 整改映射（S1R3-B01/B02/M01/M02 + m01..m06）

| ID | 等级 | A5 phase3 事实与定位 | R-V4-08 条款/整改落点 | 状态 |
|---|---|---|---|---|
| S1R3-B01 | blocker | 冻结 preregistration.json 278 行/50 键，缺 holdout_package / c5_policy / structural_identifiability；holdout_splits :142-145 为数组；family_v3.py:1595-1645 构建 payload 未含三键、:1542 docstring 称 17 字段全落盘、verifier family_v3.py:1652-1824 不校验三键（:1808-1816 只等值比较 holdout）；s1_runner.py:179 会接受缺字段 prereg；探针 verify_preregistration_v3 返回 True 且 missing_contract_fields 三键 | R-V4-08-02：三键固定 schema + verifier 强校验；R-V4-08-03/-05：S0-4 在最终代码 commit 生成；A1 task-249 + A6 task-250 + Lead commit C/D | OPEN（A1/A6 v4c 与 S0-4 未完成） |
| S1R3-B02 | blocker | Holm 族定义四处不一致：冻结 prereg:160-164/:247 为“同 K 内臂对×预算×4 主端点”=32 检验/K、共 96；s1_analysis.py 按 (endpoint,budget_B,K) 每族 4 比较、24 族×4=96（A5 时点 :2695/:2719-2743）；统计计划 :100 旧写“每端点内 5 个比较”；合同 §7.2 只写 C5 排除 | R-V4-08-01：唯一族键=(primary_endpoint,budget_B,K)、成员 C1–C4、C5 永不进族、STRUCTURALLY_IDENTICAL 行级排除后族大小可<4且动态记录；同步合同/统计计划/collect_hypotheses docstring/冻结 prereg；回归 4→3 与 C5 不进 p_adj | OPEN（A6 工作树已有动态族信息、未提交/无测试；冻结 prereg 需 S0-4） |
| S1R3-M01 | major | 冻结 code_sha=c926653d 由 7c1e2ce 生成；A5 在 a836699 重算 package_code_sha=fb0119c669bc62d6285a0a721ad4684e814d7cc4ce7e5fff803f39f008971ec7；s1_analysis.py:771-775（A5 时点）只校验 freeze_summary 与 frozen 相等，不与当前代码比较；analysis formal 未失败 | R-V4-08-03：S0-4 code_sha==package_code_sha；analysis formal 重算当前 package_code_sha 与 frozen 比较 fail-closed；exploratory 可 --allow-code-delta 但 warning；A6 工作树已新增 S1_ANALYSIS_CODE_SHA_DRIFT（:78）、_current_analysis_code_sha(:133)、校验块(:322-399)，未提交/无测试 | OPEN（A6 未提交/无测试；S0-4 未生成） |
| S1R3-M02 | major | s1_runner.py:154-162（A5 时点）allowed_family_versions=(FAMILY_VERSION,*LEGACY)；:193/:231-234/:264-265 只记录 legacy_frozen_package/confirmatory_eligible 无 raise；formal plan :1282-1321 不检查；合同 FC-14 要求拒绝 | R-V4-08-04：formal 对 family_version!=p4ra-family-v4 或 confirmatory_eligible!=true raise；exploratory 可 --allow-legacy 但标 false 且不入主统计；负控测试；A1 task-249 尚未落盘 | OPEN（A1 task-249 未落盘；当前 s1_runner.py 仍 :185/:193/:231-232/:264-265 记录不拒绝） |
| S1R3-m01 | minor | 矩阵 stale（A5 phase3 时点 v1.2） | 本矩阵 v1.3 重写；待 Lead commit C | CLOSED_BY_DOC_V1_3（待提交） |
| S1R3-m02 | minor | frozen_family.json:14-18 calibration.note 仍写 PENDING | S0-4 生成时改为 CALIBRATED 并写 A2 证据 sha256 | OPEN（S0-4） |
| S1R3-m03 | minor | determinism_report 未入 digest_manifest / freeze_summary.artifacts / SHA256SUMS | R-V4-08-05：determinism_report 进 digest_manifest/freeze_summary.artifacts 或第 9 payload、SHA256SUMS；S0-4 | OPEN（S0-4） |
| S1R3-m04 | minor | A5 phase3 时 A3 task-244 仍 in_progress；事实 JSON 64,816 B sha e5f7af1d… | A3 已定稿：报告 23,801 B sha d2fc198e…，facts JSON 64,816 B sha e5f7af1d…；A5 phase4 复核 | CLOSED_BY_A3_FINAL（待 phase4 确认） |
| S1R3-m05 | minor | A5 phase3 时 merge +479 行未提交/无测试 | 当前工作树 merge +483 行、tests +416/15 个 MergeSubcommandTests，仍未提交、未 A5 审；A1 task-249 未处理 merge 提交 | OPEN（A1 task-249 + A5 merge delta） |
| S1R3-m06 | minor | 统计计划 :100 旧口径未同步 | Lead 已把 :100 改为 R-V4-08-01 唯一口径；代码/prereg 同步仍待 B02 修复 | PARTIAL（文档已改；代码/prereg 待 S0-4） |

## 5. 统计计划 v1.1 / v4b / R-V4-08-01 验收映射

| 统计要素 | 规范值/规则（v4c） | 落点 | 关联 S1 | 状态 |
|---|---|---|---|---|
| 总 run 网格 | 21,000 runs = 15 分片×1,400 | s1_runner.py；run_config.json；merge_manifest | S1-02 | DRY_RUN_PLANNED_NOT_EXECUTED（A2 已核计划，未运行） |
| 主确认网格 | B=64、K∈{0,3,5}、20 meta_test 任务、10 opt seed×3 meta seed=9,000 runs；v4 重播种后 meta_test 任务换新 | s1_runner.py；统计计划 §3 | S1-02/S1-08 | PLANNED / BLOCKED |
| 次级网格 | B=128、K∈{3,5}=6,000 runs | s1_runner.py；统计计划 §3 | S1-02 | PLANNED / BLOCKED |
| 探索网格 | B=64/128、K=1=6,000 runs；不进主结论 | s1_runner.py；统计计划 §3 | S1-02/S1-10 | PLANNED / BLOCKED |
| 合成评价总量 | 1,920,000 次 | run_config/summary；A2 复核 | S1-02/S1-12 | PLANNED / NOT_RUN |
| 五 split | 60/20/20/10/10，共 120 tasks；主统计仅 meta_test 20；v4 仅 TE/OD 重播种，其余三 split 逐位不变 | S0-3 frozen_family.json；s1_runner.py split 过滤；S0-4 保持同族/同 split/同 seed | S1-02/S1-09 | S0-3 结构 PASS；S0-4 未生成 |
| 支持/查询池 | support 128 / query 64 | s1_runner.py 任务构造；run_records | S1-01/S1-02 | IMPLEMENTED_PENDING_V4C |
| 主端点 | best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate | s1_analysis.py；statistics.csv | S1-09 | IMPLEMENTED_PENDING_V4C |
| 诊断端点 | first_feasible_in_support、first_feasible_after_support_index、feasible_hit_rate_non_support、n_nonnull、null_rate | s1_analysis.py；aggregate.json | S1-09 | IMPLEMENTED_PENDING_V4C |
| gap 公式 | gap=(f_best−f*)/max(|f*|,1e-12) | s1_analysis.py；合同 §3.3 | S1-09 | IMPLEMENTED_PENDING_V4C |
| first/hit 分母 | first 为 1-based 真实评价顺序；feasible_hit_rate 分母恒 B | s1_analysis.py；合同 §3.3 | S1-09 | IMPLEMENTED_PENDING_V4C |
| null 政策 | 不插补、不转 0；null 率>70% 该端点 INCONCLUSIVE；不换终点 | s1_analysis.py；报告 | S1-09/S1-10 | IMPLEMENTED_PENDING_V4C |
| 主比较 C1–C5 | C1 FOMAML-Kshot vs Pretrain-Kshot；C2 vs Random；C3 vs DE；C4 Pretrain-Kshot vs Random；C5 按 C5-B 只描述结构克隆率，不做 benefit/harm、不进 Holm | s1_analysis.py；统计计划 §5；合同 §7.2 | S1-09 | CHANGES_REQUESTED_B02 |
| Holm 族（R-V4-08-01） | 唯一族键=(primary_endpoint,budget_B,K)；成员=C1–C4；C5 永不进族；STRUCTURALLY_IDENTICAL 行级排除后族大小可<4且必须动态记录；禁止旧“每端点 5 个比较”/“32 检验每 K”口径 | s1_analysis.py collect_hypotheses/Holm 聚合；统计计划 :100；合同 §7.2 | S1-09 | CHANGES_REQUESTED_B02（A6 工作树部分实现、未提交/无测试） |
| 显著性 | Wilcoxon 双侧 n=20；全零或 n<10 INCONCLUSIVE；bootstrap 10,000 seed=20261105；Holm alpha=0.05；C5 不进入 Holm 族 | s1_analysis.py；统计计划 §5 | S1-09 | CHANGES_REQUESTED_B02 |
| 实际阈值 | best/gap 相对 ≥1%；hit 绝对差 ≥0.05；first 改善 ≥ceil(0.05B)；同 K 内比较 | s1_analysis.py；统计计划 §5 | S1-09 | IMPLEMENTED_PENDING_V4C |
| 结论规则 | 单比较 SUPPORTED_BENEFIT/SUPPORTED_HARM/NO_EVIDENCE/INCONCLUSIVE；总体 SUPPORTED_IMPROVEMENT 要求 C1 四主端点至少 2 BENEFIT 且 0 HARM；C5 不可估计时总结论固定 NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY | s1_analysis.py；中文报告 | S1-09/S1-10 | IMPLEMENTED_PENDING_V4C |
| pair-level/C5-B | 每个 (task,B,K,meta_seed) 组每臂对算初始设计行 digest overlap_rate；≥0.90 判 STRUCTURALLY_IDENTICAL；输出 pair_identifiable/structural_status/threshold 与 pair_status_counts；formal 缺报告 fail-closed | identifiability_report.json；s1_analysis.py；aggregate/CSV | S1-05/S1-09 | CHANGES_REQUESTED_B02 |
| 15 分片/merge | 15 片同一顶层 run_id；merge 精确重建 21,000、分层/identity/physics/确定性校验；两跑逐字节一致 | s1_runner.py merge；merge_manifest；R-V4-07 | S1-02/S1-12 | PARTIAL（A1 工作树 +483/+416，未提交未审） |
| 7 类规范图 | fig1_meta_training_loss、fig2_k_shot_adaptation、fig3_feasible_rate、fig4_equal_budget_gap、fig5_fairness_audit、fig6_k_sweep_delta、fig7_negative_control_and_determinism；图面英文，图注/结论中文 | s1_figures.py；figures/ | S1-09/S1-12 | IMPLEMENTED_PENDING_V4C（无 formal 数据） |
| 确定性 | 200 runs（5 臂×K{0,3}×B64×20 任务×seed0）重跑 3 次一致；K=0 逐字节等价 | s1_runner.py；raw_digest_manifest；determinism 报告 | S1-07/S1-10 | PARTIAL（freeze 确定性 PASS；formal 未跑） |
| 负控 | 标签打乱负控；任务泄漏负控；预算/摘要不一致 fail-closed | s1_runner.py；test_s1_runner.py | S1-07 | IMPLEMENTED_PENDING_V4C |
| 物理 | physical_call_count=0；不启动任何求解器 | physics guard；报告；A3 审计 | S1-07/S1-12 | READ_ONLY_VERIFIED（当前事实） |

## 6. 实现文件、测试与当前存在性

| 文件 | 角色 | 当前存在性（HEAD a836699 + 工作树） | 备注 |
|---|---|---|---|
| docs/planning/p4_route_a_s1_execution_plan_20261105.md | S1 执行计划 v1.3 | 已跟踪；Lead 未提交修改 | 171 行/17,823 B/sha256 c803510d…；含 R-V4-07 15 分片/merge |
| docs/planning/p4_route_a_s1_statistical_plan_20261105.md | S1 统计计划 v1.1 | 已跟踪；Lead 未提交修改 | 161 行/14,375 B/sha256 beee0c3c…；:100 已按 R-V4-08-01 同步；其余 v1.1 内容未大改 |
| docs/planning/p4_route_a_s0_design_contract.md | S0 设计合同 v1.3 | 已跟踪；Lead 未提交修改 | 294 行/34,233 B/sha256 0bdde7b3…；§10/§11/§12 元数据仍引用 v1.2/S0-3（文档 lag） |
| docs/planning/p4_route_a_s1_v4_remediation_rulings_20261105.md | v4 裁定 R-V4-01..06 | 已跟踪 | 84 行/5,715 B |
| docs/planning/p4_route_a_s1_v4b_parallel_rulings_20261105.md | R-V4-07 并行/merge 裁定 | 未跟踪（Lead 提供） | 47 行/4,477 B/sha256 09049dc8… |
| docs/planning/p4_route_a_s1_v4c_phase3_rulings_20261106.md | R-V4-08 phase3 整改裁定 | 未跟踪（Lead 提供） | 85 行/6,055 B/sha256 cb55543e… |
| research/concorde_metaopt/meta_learning/s1_runner.py | A1：网格、K-shot 闭环、预算断言、run_records、merge | a836699 为 1,800 行；工作树 2,283 行/99,252 B/sha256 c35938e… | +483 行 merge 未提交；无 v4c B01/M02 修复（A1 task-249 未落盘）；非 A4 改动 |
| research/concorde_metaopt/tests/test_s1_runner.py | A1：泄漏/预算/初始化/K=0/负控/确定性/merge 单测 | a836699 为 1,293 行；工作树 1,709 行/70,459 B/sha256 5a132086… | +416 行、15 个 MergeSubcommandTests 未提交；未进入 829 tests 运行 |
| research/concorde_metaopt/meta_learning/s1_analysis.py | A6：预检、聚合、C1–C5、null 政策、结论层、pair 消费、v4c formal/exploratory 校验 | a836699 为 4,640 行；工作树 5,098 行/236,522 B/sha256 73c9e719… | +478 行 A6 v4c 代码未提交；已含 S1_ANALYSIS_CODE_SHA_DRIFT(:78)、三键强校验(:322-399)、动态 Holm 族信息(:3047+)、formal/exploratory 入口(:4687+)；无测试改动 |
| research/concorde_metaopt/tests/test_s1_analysis.py | A6：9 键/别名/null/摘要/pair/负控单测 | 2,840 行/127,203 B/sha256 0689f3e5… | A6 未改测试（git status 无该文件）；新校验/动态族尚无测试 |
| research/concorde_metaopt/meta_learning/s1_figures.py | A6：7 类图与 figure_status | 632 行 | 图面英文（A5-m05） |
| research/concorde_metaopt/meta_learning/family_v3.py | 既有冻结族/9 端点键/CSV 校验 | 1,955 行 | :162 ENDPOINT_ROW_KEYS；:836-872 校验；A5 phase3 B01 指向 :1595-1645/:1542/:1652-1824；A1 task-249 待修；A4 只读 |
| research/concorde_metaopt/meta_learning/m5_arms.py | 既有接入支持样本与 k_shot | 1,716 行 | 旧缺口 :504/:514/:585/:623/:717；A5-B03 代码层 closed |
| research/concorde_metaopt/meta_learning/baseline_arms.py | 既有配对统计复用 | 已存在 | paired_statistics :1220-1244（bootstrap/Wilcoxon） |
| research/concorde_metaopt/meta_learning/m5_runner.py | 既有统计/端点映射复用 | 已存在 | :95 ENDPOINT_ROW_KEYS 映射；:2125-2160 统计入口 |
| docs/reviews/p4_route_a_s1_requirement_matrix.md | 本矩阵 v1.3 | 工作树修改（A4） | 本文件；未 commit/push |

> 当前 HEAD a836699 没有 S1 formal 运行目录、run_records.jsonl 或正式结果图；工作树有 7 个修改文件（Lead 3 文档 + A4 本矩阵 + A1 2 代码/测试 + A6 1 代码）和 2 个未跟踪裁定文件。A1/A6 改动均未提交、未被 A5 审；**不是 A4 修改**。本表“存在”仅指源码/计划文件，不代表 S1 验收通过。

## 7. 阶段门与交付证据包

阶段门（R-V4-08-06，严格顺序）：

    A1 v4c 修复（family_v3 + s1_runner + merge + tests，task-249）
      + A6 v4c 修复（s1_analysis，task-250）
        → Lead commit C
          → A1 在 C 干净 detached worktree 生成 S0-4（两进程逐字节一致）
            → Lead 将 S0-4 冻结包写入仓库并提交 commit D
              → A2 readiness v4c
                → A3 审 commit C/D 隔离
                  → A5 phase4 final gate（B01/B02/M01/M02 + merge delta task-247）
                    → A5 APPROVE_FOR_S1_RUN + Lead 书面授权
                      → A2 执行 15 分片 + merge（21,000 formal run）
                        → A5/A3 复核 → Lead 发布 Issue #7 中文回执

当前位置：**A5 phase3 CHANGES_REQUESTED；A1 task-249 in_progress；A6 task-250 in_progress；merge 代码/测试未提交、未 A5 审；A5 merge delta task-247 pending（ready 未开始）；S0-4 NOT_GENERATED；A2 readiness v4b 仅对 S0-3 有效，S0-4 后需重跑；A5 phase4 未开始；S1_RUN NOT_APPROVED、formal 21,000 NOT_RUN。** 旧 phase2 APPROVE 已收窄；A5 phase3 必须修复后才能进入 phase4。readiness/诊断不得读取新 meta_test/meta_test_ood。

交付证据包（计划路径；当前均未产生）：

| 证据 | 内容 | 关联 S1 | 当前状态 |
|---|---|---|---|
| run_config.json | 网格、B/K、五臂、seeds、S0-4 冻结输入摘要、code_sha | S1-02/S1-12 | BLOCKED（formal 未授权） |
| run_records.jsonl | 每 run 字段、budget 账、endpoint_values、physics、digest | S1-01..S1-12 | BLOCKED |
| identifiability_report.json | pair 级 structural_status/threshold、pair_status_counts | S1-05/S1-09 | IMPLEMENTED_PENDING_V4C（正式报告未生成） |
| 15 分片目录/merge_manifest | 15×1,400 分片产物、并集/顺序/分层/确定性校验 | S1-02/S1-12 | BLOCKED（A1 初版未提交/未 A5 审） |
| summary.json / aggregate.json | 聚合、C1–C5、C5 结构排除计数、null 率、结论层 | S1-09 | BLOCKED |
| statistics.csv / s1_identifiability_table.csv | 9 端点主表与 pair 表 | S1-09 | BLOCKED |
| train_val_test_split.json | 120 tasks 五 split 引用 S0-4 冻结包 | S1-02/S1-12 | BLOCKED |
| data_manifest.json / raw_digest_manifest.json | 文件 SHA256、code_sha、复算记录 | S1-12 | BLOCKED |
| figures/*.png + figure_data/*.csv | 7 类规范图与图数据；无数据标 NOT_RUN | S1-09/S1-12 | BLOCKED |
| SHA256SUMS.txt | 交付目录校验清单 | S1-12 | BLOCKED |
| 中文报告 | 结果/负结果、统计、限制、无物理声明 | S1-12 | BLOCKED |
| A5/A3 审查记录 | A5 rev2 CHANGES_REQUESTED；phase3 CHANGES_REQUESTED；merge delta PENDING；A3 v4 暴露扫描定稿 PASS | S1-08/S1-10 | A5 rev2 DONE；phase3 CHANGES_REQUESTED；merge delta PENDING；A3 exposure PASS |

验收 13 条（执行计划 §9 + R-V4-07 + R-V4-08，当前均未按 v4c 执行）：

1. 829 tests 全绿；A5 phase3 已在 a836699 复跑 OK(skipped=1)/161.811s，但 A1 merge +483/+416 与 A6 +478 未进入该次运行；**不得引用为 S1_RUN 证据**。
2. 40 组五臂×K×B 预算测试 billable=B；当前仅代码/单测/20-run bench 层，未跑正式 40 组合；A2 dry-run 只核 plan。
3. 9 端点键/禁用别名/null/摘要不一致负控；代码层存在，A6 工作树新校验无测试，A5 phase3 未通过。
4. 统计检验/pair/C5-B 单测；代码层存在；B02 要求 Holm 族唯一化并补 4→3/C5 排除回归测试，A6 工作树未提交/无测试。
5. 冻结输入篡改、预算不一致、K=0 clone 误入主分析 fail-closed；S0-3 formal 不合格，S0-4 生成后重验。
6. 确定性 bundle 两跑一致、200 runs×3、K=0 逐字节等价；freeze 确定性 PASS，formal 未跑 NOT_RUN。
7. physical_call_count=0；冻结包/A2/A3 均记 0 solver，A2 dry-run physical=0；无 formal 运行证据。
8. 0 主机绝对路径、旧 M2/M5/M6 工件不变、PR 边界不变；A4 文档为相对路径，旧工件未触碰。
9. v4 holdout 隔离：S0-3 两进程一致、三 split 逐位相同、TE/OD fingerprint 与 v3 官方包 120 个零交集（legacy 280 task_id 仅 task_id 零交集）；A3 v4 暴露扫描 PASS；但 S0-3 prereg 缺三键，formal 拒绝，需 S0-4。
10. pair-level/C5-B：identifiability_report 字段/pair_status_counts、analysis 消费、C5 不进 Holm、可估计任务<10 固定结论；B02 未关闭前不得标记通过。
11. 正式工件与 readiness：a836699 干净树重建 200/50、artifact sha 绑定、A2 readiness v4b READY_PENDING_LEAD_AUTHORIZATION；S0-4 后需重跑 readiness v4c。
12. 回执披露：污染/H1/C5/旧 APPROVE 收窄/0 物理/未合并 main；A4 草稿需刷新，Issue #7 当前仅 2 条评论（最新仍是 S0-2 完成回执），不得假装已发布 S1 回执。
13. merge/15 分片：A1 工作树 merge +483、tests +416/15 tests，未提交、未 A5 审；A2 dry-run 计划 PASS 但未执行；**S1_RUN 门禁未满足**。

## 8. 风险、缺口与待决策

| ID | 风险/缺口 | 影响 | 缓解/下一步 | 状态 |
|---|---|---|---|---|
| R-01 | A5 phase3 verdict=CHANGES_REQUESTED（2B/2M/6m），B01/B02/M01/M02 未关闭 | 当前实现不可验收，S1 formal 被阻断 | A1 task-249 + A6 task-250 修复；Lead commit C；S0-4；A5 phase4 | OPEN |
| R-02 | C5-B pair-level 已实现，但 B02 Holm 族定义冲突（32 检验/K vs 每族 4 比较 vs 每端点 5 比较） | 统计结论可能被错误多重校正 | R-V4-08-01 唯一族定义；同步合同/统计计划/代码/冻结 prereg；回归 4→3 与 C5 排除 | OPEN（B02） |
| R-03 | A6 工作树新增 formal/exploratory 校验、code_sha 漂移、三键强校验，但无测试文件改动 | 新 fail-closed 逻辑未被独立验证 | A6 补 test_s1_analysis.py；A5 phase4 审负控 | OPEN |
| R-04 | 合同 v1.3 与 R-V4-08 存在元数据 lag：§10 仍写 v1.2、§11 仍写生成 S0-3、§12 无 v1.3 行；未写 run_id 正则/verifier 交叉校验细节、漏 pair_status_below_threshold 与 overlap_definition 两键、未写 4→3/C5 回归 | 文档口径与实现可能漂移 | Lead 在 commit C 前修订；A5 phase4 对照 R-V4-08-02 | OPEN（A4 仅记录，不改合同） |
| R-05 | 工作树 7 个修改/2 个未跟踪文件未提交 | 冻结/审查对象可能不是最终 commit | Lead commit C/D 固定 SHA；A4 以工作树事实记录并注明未提交 | OPEN |
| R-06 | 统计计划 :100 已同步 R-V4-08-01，但代码/prereg 尚未最终统一 | B02 可能以文档已改为由提前关闭 | code + S0-4 prereg 同步后再关闭 B02 | PARTIAL |
| R-07 | 21,000 runs 资源/时间未实测；串行估算 36.9949h，8-worker 5.555h，15 进程约 4.6GB/2–3h | 预算/资源风险 | A2 dry-run 已核计划；正式前 Lead 确认预算与停止条件 | OPEN |
| R-08 | 7 类图与 figure_status 尚无 formal 数据 | 无数据不得绘虚构曲线 | A6 仅用真实 formal 数据；无数据标 NOT_RUN；A5 审图 | OPEN |
| R-09 | 旧 S0-2 holdout 已被读取（B01：608 条/3 任务；8/20 入内存） | 旧包不能用于确证 S1 | S0-3 已重播种；A3 v4 扫描 PASS；S0-4 继续隔离 | ADDRESSED_PENDING_S0_4 |
| R-10 | 旧 M2/M5/M6 与 PR #3/#6 边界；merge 产物尚未产生 | 误合并/误改会破坏历史证据 | A3 审计；main 不合并；旧 run 只读；仅 Lead 发布 | OPEN（A3 持续） |
| R-11 | 物理调用与 Issue #4 门禁 | S1 合成结果可能被误标为真实气动证据 | 报告强制 synthetic/lifting 标注；physical=0；#4 门禁不变 | OPEN（持续） |
| R-12 | S0-3 结构 PASS 但 formal 不合格 | 若直接引用可能越过阶段门 | 本矩阵标历史只读；S0-4 生成前不得 formal | OPEN（B01/M01） |
| R-13 | 正式工件已重建，但 formal run_config/产物未生成 | 旧 readiness 不能作为 S0-4 formal 依据 | A2 readiness v4c 在 S0-4 后重跑 | OPEN |
| R-14 | **merge 未提交/未审**：A1 工作树 s1_runner.py +483 行、test_s1_runner.py +416 行（15 tests），未提交、未 A5 审 | S1_RUN 无法启动 | A1 task-249 一并提交；A2 重跑 dry-run；A5 merge delta task-247 | OPEN（S1_RUN blocker） |
| R-15 | A5 phase3 与 phase4 分两段审；phase3 已 CHANGES_REQUESTED | 阶段门误判/跳过修复 | 矩阵/回执明确 phase3≠phase4；Lead 只在 phase4 APPROVE 后授权 | OPEN（口径风险） |
| R-16 | 829 tests 不含工作树 merge/A6 新增代码；A6 无测试改动 | 缺陷可能带入 formal | A1/A6 补测试并复跑全量；A5 phase4 审 | OPEN |
| R-17 | 15 进程/4.6GB/2–3h 资源为估算，未实测；并行写同一 run_id 的隔离未验证 | 运行失败/产物污染 | A2 dry-run 先小网格；A3 审计；失败即停 | OPEN |
| R-18 | S0-4 尚未生成；生成必须基于含 merge 的最终代码 commit C，且 code_sha==package_code_sha | 若基于脏树/旧 commit 生成，formal 仍会被拒 | A1/A6→Lead commit C→A1 干净 detached 生成→Lead commit D；A5 phase4 复核 | OPEN |
| R-19 | S0-3 冻结 code_sha c926653d 与 a836699 当前 package_code_sha fb0119c6 漂移（M01） | 旧包不能 formal；分析可能误用旧包 | R-V4-08-03；A6 已加 S1_ANALYSIS_CODE_SHA_DRIFT 未提交/无测试；S0-4 重新登记 | OPEN（M01） |
| R-20 | S1_runner 仍允许 legacy family_version 且不拒绝 confirmatory_eligible=false（M02） | legacy 包可能进入 formal | A1 task-249 加 raise；exploratory 仅 --allow-legacy；负控测试 | OPEN（M02） |
| R-21 | A6 v4c 代码 +478 行未提交、无测试；A1 v4c 尚未落盘 | Lead commit C 无法按 R-V4-08-06 推进 | A1/A6 完成并自测；A5 phase4 审 | OPEN |

待决策：

1. A5 phase4 的最终 verdict 时点，以及 B01/B02/M01/M02 与 6 minor 的关闭标准（A5 职责，A4 不代判）。
2. A1 task-249 与 A6 task-250 的修复范围/完成时点；Lead commit C 的时点与提交内容（含 merge + A6 + tests）。
3. S0-4 生成时点、两进程确定性复跑与 Lead commit D 的安排。
4. S1_RUN 的 Lead 书面授权时点与 15 分片资源/停止条件确认。
5. 合同 v1.3 元数据 lag（§10/§11/§12）与 R-V4-08-02 细节是否在 commit C 前补齐（A4 写范围外，需 Lead 决定）。
6. Issue #7 S1 实现回执的发布时间：应在 A5 phase4 + S0-4 后由 Lead 发布；A4 仅提供草稿；当前 Issue #7 最新评论仍是 S0-2 完成回执，不得伪装已发布。

## 9. 读取记录

- Issue #7：GitHub 只读；最近读取 2026-11-06T02:30+08；state=open；comments=2；updated_at=2026-11-05T08:17:17Z；最新评论 6653167378（2026-11-05T08:17:17Z，S0-2 完成回执）；无 S1 phase3 新回执；raw 落盘 <EXT>/p4-route-a/a4/raw/issue7_latest_comment_v4c.md 等；本任务未发布/未写 GitHub。
- Issue #4：state=open，comments=17，updated_at=2026-11-05T07:38:19Z；最新 3 条 6647827491（D-12D-006）、6651680755（Round-1 事实回执）、6652497663（Z-01 整改进展）；门禁 GEO-12D=PARTIAL、LF-M2.02=NOT_VALIDATED、HF-M2.02=PARTIAL、BODY-CORR=BLOCKED、MISSION-DATA=PARTIAL、BUDGET=GATED、approved_for_next_stage=false；A 类 14/20、剩余 6 CLOSED 不结转、B 类 12 次 LOCKED、C 类 0/4；physical=0；raw 落盘 <EXT>/p4-route-a/a4/raw/issue4_v4c.json 等。
- Issue #5：state=open，comments=3；最新终态回执 6643119583（2026-11-04T21:55:56Z）。
- PR #3：open、merged=false、head=e5140fc、base=main ec65e5a；PR #6：open、merged=false、head=ff6280f；PR #7 不存在（404）；main 未合并。
- 旧 S0-2 冻结包：research/concorde_metaopt/optimization_runs/p4ra-s0-2-freeze-20261105T072500Z（11 文件；SHA256SUMS.txt 8 个 payload 校验；freeze_summary.json git_sha=766a59c、code_sha=c929609a…、radius_base=0.64、CALIBRATED）；只读，不得用于确证。
- S0-3 冻结包：research/concorde_metaopt/optimization_runs/p4ra-s0-3-freeze-20261105T155925Z（11 文件/556K；8 payload+SHA256SUMS+README；sha256sum -c 8/8 OK；两进程 8 payload 逐字节一致；family_version=p4ra-family-v4、holdout_seed=20261106、family_fingerprint=a1f9462c…、split_hash=cd597d01…、prereg_digest=aa806767…、analysis_plan_digest=37eee53c…、radius_base=0.64/CALIBRATED、physical=0）；**A5 phase3 判定 formal 不合格，历史只读**。
- A5 phase3：<EXT>/p4-route-a/a5/S1_phase3_review.md（17,927 B/162 行/sha256 a0ed7a43f9e793a81e2e6d1090393b9a7d296652784115aa007ffd59bb3e7fa7；CHANGES_REQUESTED；2B/2M/6m；审阅 a836699）；<EXT>/p4-route-a/a5/s1_phase3_829tests.log（8,843 B/sha256 950790c4…；末行 Ran 829 tests in 161.811s / OK (skipped=1) / EXIT=0）。
- A5 S1 rev2：<EXT>/p4-route-a/a5/S1_code_review_rev2.md（sha256 d5a0979a…；269 行；CHANGES_REQUESTED；2B/4M/6m；审阅 c0cb2cd；768 tests OK(skipped=1)）。
- A2 readiness v4b：<EXT>/p4-route-a/a2/s1_prep_v4b/S1_formal_readiness.md（sha256 3bf9f2ea…）/json（sha256 41ccbaa8…）；worktree A2 独立 detached worktree @ a836699 detached clean；总体 READY_PENDING_LEAD_AUTHORIZATION；20-run bench 2×20 PASS、billable=1280/true=1250、physical=0、CLONE 2 对；合成 meta_test 8 产物 PASS（非真实）；formal 21,000 NOT_RUN；A2-V4-B01 已由 a836699 修复。
- A2 15 分片 dry-run：<EXT>/p4-route-a/a2/s1_formal_plan/S1_shards_plan.md（112 行；DRY_RUN_PLANNED_NOT_EXECUTED；15 分片×1,400=21,000；run_count=21000、union=21000、missing/extra/duplicate=0；physical_call_count=0；runs_executed=0）；<EXT>/p4-route-a/a2/s1_formal_plan/logs/dry_run.log（status=DRY_RUN_NOT_EXECUTED）；<EXT>/p4-route-a/a2/s1_formal_plan/logs/run_shards_dryrun.log（15 shards planned、no process started）。
- A3 v4 holdout 暴露扫描定稿：<EXT>/p4-route-a/a3/S1_v4_holdout_exposure.md（23,801 B/sha256 d2fc198e…；PASS）；facts JSON 64,816 B/sha256 e5f7af1d…；40 run_records/683 条：legacy v3 608 条、v4 bench 40 条、合成 meta_test 35 条、OOD 0；30 个 holdout fingerprint 仅命中 8 个冻结/验证包文件；0 solver；formal 未启动。
- v4 裁定：docs/planning/p4_route_a_s1_v4_remediation_rulings_20261105.md（sha256 f71e32a9…；84 行；R-V4-01..06）。
- v4b 并行裁定：docs/planning/p4_route_a_s1_v4b_parallel_rulings_20261105.md（47 行/4,477 B/sha256 09049dc8…；R-V4-07 15 分片+merge）。
- v4c phase3 裁定：docs/planning/p4_route_a_s1_v4c_phase3_rulings_20261106.md（85 行/6,055 B/sha256 cb55543e…；R-V4-08-01..06）。
- 本地 S1 工作树：HEAD=a836699ad2fd68f4e6f924d46b3f37ab7798dd95，branch research/p4-route-a-s1；git status：7 个修改（Lead 合同/执行计划/统计计划、A4 本矩阵、A1 s1_runner.py、A1 test_s1_runner.py、A6 s1_analysis.py）+ 2 个未跟踪（R-V4-07、R-V4-08 裁定）；A1/A6 改动未提交、未 A5 审；A4 未 commit/push，未改代码或冻结包。
- A1 工作树 merge 初版实况（A4 只读 grep/wc，2026-11-06T03:05+08）：s1_runner.py 2,283 行/99,252 B/sha256 c35938e…；MERGE_MANIFEST_SCHEMA_VERSION='p4ra-s1-merge-manifest-1'（:68）、_merge_key(:1474)、_merge_expected_run_id(:1486)、shard_definitions(:1508)、_merge_record_problems(:1534)、merge_plan_from_args(:1618)、merge_run_shards(:1659)；test_s1_runner.py 1,709 行/70,459 B/sha256 5a132086…、15 个 MergeSubcommandTests；未提交、未 A5 审。
- A6 工作树 v4c 代码实况（A4 只读 grep/wc，2026-11-06T03:05+08）：s1_analysis.py 5,098 行/236,522 B/sha256 73c9e719…；新增 S1_ANALYSIS_CODE_SHA_DRIFT(:78)、V4C_HOLDOUT_SPLIT_COUNTS(:81)、_freeze_bundle_confirmatory_eligible(:115)、_current_analysis_code_sha(:133)、三键强校验(:322-399)、动态 Holm 族信息(:3047+)、formal/exploratory 入口(:4687+)；test_s1_analysis.py 未改（2,840 行/127,203 B/sha256 0689f3e5…）；未提交、未 A5 审。
- A4 本任务仅改本矩阵并刷新 Issue #7 回执草稿/简报；未执行物理计算、未启动求解器、未做 GitHub 写操作、未读取新 meta_test/meta_test_ood 结果。

## 10. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4（task-217） | 首次生成 S1-01..S1-12 需求→实现文件/测试/验收证据矩阵；映射 S0-2 冻结输入、A5 phase2 §7 六前置、统计计划 v1.1 与阶段门；明确 S1 未实现、所有运行/图表 NOT_RUN，无算法结果、无物理调用 |
| v1.1 | 2026-11-05 | A4（task-231） | 按 A5 S1 rev2 与 R-V4-01..06：S1 状态改为 IN_PROGRESS/PARTIAL/BLOCKED；新增 §2.2 v4/S0-3 输入、§4.2 V4-01..06、§4.3 B01/B02/M01..M04 与 minor 映射；C5-B/pair-level、readiness 不读 test/OOD、正式工件重建、A5 phase3 门；旧 S0-2 标只读且不得用于确证；未 commit/push、未执行物理计算、未读取新 holdout 结果 |
| v1.2 | 2026-11-06 | A4（task-248） | 基线更新到 a836699 + 执行计划 v1.3 + R-V4-07：S0-3 冻结包 COMPLETE（实际哈希/两进程确定性/零 fingerprint 交集）；S1 实现 IMPLEMENTED_PENDING_A5、829 tests；新增 §4.4 15 分片/merge/S1_RUN 门禁；V4/S1R2 状态改为代码/工件层关闭待 A5；A2 readiness v4b READY_PENDING_LEAD_AUTHORIZATION；A3 v4 暴露扫描 PASS；新增 R-14..R-17；明确 merge 初版未提交/无测试、formal 21,000 NOT_RUN、S1_RUN 未授权；未 commit/push、未发布 GitHub、未执行物理计算、未读取新 holdout 结果 |
| v1.3 | 2026-11-06 | A4（task-251） | 按 A5 phase3（CHANGES_REQUESTED；2B/2M/6m）与 R-V4-08：新增 §1 A5 phase3/S0-4 行与结论；S0-3 改标“结构 PASS、formal 不合格、历史只读”；新增 §4.5 S1R3-B01/B02/M01/M02 与 m01..m06 关闭映射；S1-05/S1-09 标 CHANGES_REQUESTED_B02；S1-08 标 BLOCKED；A5PRE/V4/S1R2 状态改为 phase3 重开/收窄；§4.4 更新 A2 dry-run PASS、A1 merge +483/+416/15 tests 未提交未审、task-247 ready 未开始；§5 Holm 族改为 R-V4-08-01 唯一口径；§6 更新工作树 A1/A6 文件/行数/哈希与 A6 无测试；§7 阶段门改为 R-V4-08-06 七步；验收 13 条/风险 R-01..R-21/读取记录全部更新；明确 Issue #7 当前仅 2 条评论、最新仍是 S0-2 完成回执、S1 回执未发布；未 commit/push、未发布 GitHub、未执行物理计算、未读取新 holdout 结果 |
