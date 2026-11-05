# P4 路线A S0 需求矩阵（Issue #7 · S0–S4 → 交付物 / 角色 / 验收证据 / 状态）

> 文档性质：S0–S4 需求矩阵与门禁关系表，供 Lead、A5 与本机团队审阅；S0 已完成、S1 未开始；**不构成新的物理授权，不构成算法性能结论**。
> 依据：Issue #7 正文（D-P4-003，2026-11-05 读取，repo QingYangJin/RCAIDE_Supersonic）+ 中文计划 docs/planning/p4_route_a_stage_improvement_plan_20261105.md（V1.0，commit a331639e）+ docs/planning/p4_route_a_s0_2_decisions_20261105.md（D-S0-2-01..07，Lead S0-2 裁定）+ A5 S0-2 复审 <EXT>/p4-route-a/a5/S0_2_A5_review_phase2.md（sha256 ea9b2eb7…，APPROVE_FOR_S1_FORMAL，0 blocker / 0 major / 8 minor）+ A3 S0-2 隔离审计 <EXT>/EXT/p4-route-a/a3/S0_2_phase2_isolation.md（sha256 23bac611…，PASS 11/11）+ 冻结包 p4ra-s0-2-freeze-20261105T072500Z + Issue #7 回执 6653167378。
> 作者：A4（a4-issue-liaison）；任务：task-188 初版 + task-197 S0-2 状态更新 + task-212/217 最终事实；工作树：本仓库分支 research/p4-route-a-s1 @ 43fcfc8（只读核实；A4 未 commit/push）。
> 状态口径：PASS＝已有独立复核通过的验收证据；PASS_WITH_MINOR＝通过但仍有非阻断 minor 待修；PARTIAL＝部分产出或口径已冻结但实现/复审未完成；PENDING＝尚未提交可验收产物；READ_ONLY_VERIFIED＝A4 已只读核实源文件/字段存在（不代表验收通过）；BLOCKED＝受未授权/未批准预算阻断。physical_call_count=0。

## 1. 总体边界（所有需求共同前提）

- Issue #7 是本轮路线A（元学习响应代理辅助普通约束 BO 初始设计）**唯一执行授权**；只允许代码、单元/梯度公平性测试、全合成解析任务训练与正式离线对照。
- 未批准：真实飞机 BO/DE、真实航空元训练、路线B采集策略、真实 SU2/Mission/WaveDrag、新 VSPAERO 求解、RCAIDE 回退、P5/P6。
- 旧 Issue #5 / PR #6 为历史基线，不得覆盖；旧 PR #3/#6 保持 open 不合并 main。
- 物理调用硬隔离：physical_call_count=0；不得把 VSPAERO_INTERNAL_ONLY 说成真实 Mach 2.02 已验证。
- 每阶段先提交独立 A5 审查并取得 APPROVE 后才放行下一阶段；S1 实现后须取得 APPROVE_FOR_S1_RUN，再由 Lead 授权 A2 formal run；负结果如实记录，不允许把参数调到 MAML 获胜。
- 端点 ID 统一为 best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate（D-S0-2-02）；first_feasible_evaluation_index 为禁用别名。

## 2. Issue #7 S0–S4 需求矩阵

### 2.1 S0｜基线与预注册冻结（Issue #7 §2 S0）

**S0 总状态：COMPLETE（2026-11-05 阶段二闭环）**。A5 phase2 verdict=APPROVE_FOR_S1_FORMAL（0 blocker / 0 major / 8 minor；S0-2=COMPLETE；S1 formal=APPROVED）；A3 phase2 PASS 11/11；Lead 集成提交 766a59c→a79959c→43fcfc8；Issue #7 回执 6653167378。S1 实现与正式 run 尚未开始；8 个 A5-S0P2 minor 开放但不阻断 S1 formal 准备。

| 需求ID | 原文位置 | 要求（摘要） | 交付物/证据 | 角色 | 验收证据 | 状态 |
|---|---|---|---|---|---|---|
| S0-01 | §2 S0 | 只读验证旧 M2/M5/M6 的 run_id、git_sha、config_hash、manifest 不可变性与负结果完整性；不得重跑覆盖 | 基线不可变性核对表 + 各 run 的 SHA256/字段清单 | Lead（主）；A2 独立复核；A3 保护；A5 复核 | docs/reviews/p4_route_a_s0_baseline_snapshot_20261105.md/.csv；A5 独立复核 92/92 manifest、4/4 external、3/3 git_sha 祖先、3/3 M5 逻辑 digest、physical=0；m04 快照时间口径已在 md:15 注 541/546/579，m05 CSV 第 2 行 notes 已同步 | PASS（A5 phase2 未再列为 finding；m04/m05 关闭） |
| S0-02 | §2 S0 | 旧 M5/M6 holdout 已公开，不得作为改进版未见盲测集；新方法必须使用独立任务族/独立 task_id | 隔离规则 + 旧/新 task_id 清单 + split 摘要 | A1+A4 | D-S0-2-01/05；docs/planning/p4_route_a_s1_family_v3_design_20261105.md；冻结包 p4ra-s0-2-freeze-20261105T072500Z（frozen_family.json、v3_isolation_report.json） | PASS（五 split 60/20/20/10/10、120 tasks、task_id 正则与 legacy 280 task_id 零交集；A5 phase2 复核） |
| S0-03 | §2 S0 | 冻结新 family_version 与 preregistration，只用 meta_train/meta_validation 调参，正式 meta_test 锁定统计方案后一次性打开 | preregistration 草案 + family_version 冻结记录 | A2+A1（Lead 签发） | D-S0-2-05/06；冻结包 frozen_family.json、preregistration.json；family_version p4ra-family-v3；prereg_digest 6981f503…；legacy v1 只读 | PASS（family/family_version/seed 20261105 冻结；A5 phase2 复核） |
| S0-04 | §2 S0 | 主终点与统计方案在打开新 meta_test 前冻结；禁止事后依据效果改任务/终点/剔除 | 预注册主终点、次终点、多重校正、失败规则 | Lead+A2+A5 | D-S0-2-02/04；docs/planning/p4_route_a_s1_statistical_plan_20261105.md v1.1；analysis_plan_digest 37eee53c… | PASS（四规范端点/9 个 ENDPOINT_ROW_KEYS/阈值/null 规则冻结；A5 phase2 复核） |
| S0-05 | §2 S0、§1 缺口 | 修复新版本 preregistration.stopping_rules 错误序列化并增加 schema 类型校验；旧冻结 run 不修改 | 新版 schema + 类型校验单测 + 修正记录 | A1（A5 复核） | 766a59c 代码提交（feasible_v2.py 与 test_meta_learning_feasible_v2.py）；604 tests OK(skipped=1) 37.687s；A5 phase2 §3 | PASS（stopping_rules 序列化/类型校验已修，旧冻结 run 未改） |
| S0-06 | §2 S0 | 新版本保存确定性重跑 digest 与运行日志；旧冻结工件保持不变 | 确定性 digest 规范 + 复算脚本 + 日志 | A1+A3 | 合同 §6 canonical JSON/七个 digest/复算；冻结包 8/8 payload 逐字节一致；determinism 29/29、rerun=2 | PASS（A5 phase2 独立复跑复核） |
| S0-07 | §2 S0 | 提交中文设计合同（task_id/family_version/split/seed/prereg 字段/确定性 digest/预算口径） | docs/planning/p4_route_a_s0_design_contract.md | A4（A5 复审） | 本合同 v1.1（25,880 B，sha256 3f622570…）；五 split、端点 ID/ENDPOINT_ROW_KEYS、stopping_rules len≥2、行号修正、task_id 正则、五臂预算映射 | PASS（A5 phase2 合同侧通过；A5-S0-M01/M02/m01/m02/m09 关闭） |
| S0-08 | §2 S0 | 提交中文风险清单（query 泄漏、支持样本免费先验、克隆臂、旧工件改写、物理调用、过拟合 meta_test 等） | docs/reviews/p4_route_a_s0_risk_register.md | A4 | 风险清单 R-01..R-20（9,723 B，sha 294432ff…） | PASS（A5 S0 审阅 §2 判 PASS） |
| S0-09 | §2 S0 | 提交基线统计快照（M2/M5/M6 现有数字与负结果，不重跑） | 基线统计快照（数字+来源文件+字段） | Lead+A2 | docs/reviews/p4_route_a_s0_baseline_snapshot_20261105.md/.csv；A5 判 PASS 附 m04/m05 minor；快照 md:15 与 CSV 第 2 行已同步 | PASS（A5 phase2 未再列 finding） |
| S0-10 | §2 S0 | 各角色审查记录齐全，A5 审核并确认新任务冻结边界后才可开始 S1 | A5 S0 审查记录（PASS/CHANGES_REQUESTED） | A5+Lead | A5 phase2 APPROVE_FOR_S1_FORMAL（报告 sha256 ea9b2eb7…）；A3 phase2 PASS 11/11（报告 sha256 23bac611…） | PASS（S0-2=COMPLETE；S1 formal=APPROVED） |

#### 2.1.1 S0-2 关闭对照表（A5-S0-M01..M04 / m01..m10，14 条）

| Finding | 严重度 | A5 关闭条件（摘要） | 本版落点 | 剩余依赖 | 状态 |
|---|---|---|---|---|---|
| A5-S0-M01 合同三 split vs 五 split | major | 合同明确五 split enum/角色/是否进主统计/split_digest 覆盖；与 family v3 一致；schema 校验与单测 | 合同 v1.1 §3.2、§5、§6.2、§7；本矩阵 S0-02/S0-03；冻结包 split_counts/split_digest | A1 生成器与 v3 文档 rev2 已随 766a59c 提交；A5 phase2 复核通过 | CLOSED（A5 phase2 0 major） |
| A5-S0-M02 主终点 ID 两种写法 | major | 统一规范 ID、禁别名、ENDPOINT_ROW_KEYS 登记、合成端到端非空覆盖断言 | 合同 v1.1 §3.3、§7、§8 FC-11；本矩阵 §1；统计计划 v1.1；family_v3.py ENDPOINT_ROW_KEYS | S1 分析脚本强制 9 键与 analysis_plan_digest（S1-09/S1-17） | CLOSED（合同/计划侧）；S1 实现待验 |
| A5-S0-M03 K 支持评价/8 初始点/RAND 与 DE 预算映射 | major | 五臂×K 预算表；支持标签用途；DE population 映射；billable=B 单测与 K 未计入 fail-closed | 合同 v1.1 §4.1、§4.2、§4.3、§8 FC-02；本矩阵 S1-02/S1-03；冻结包预算公平性测试 | A1 40 组预算公平单测随 766a59c 提交；A5 phase2 复核 | CLOSED（A5 phase2 0 major） |
| A5-S0-M04 first_feasible/gap/1% 阈值语义 | major | u*/gap 公式与归一化、first_feasible 是否含 K、feasible_hit 分母、阈值公式与分母、null 处理；prereg 固化、分析脚本同 ID、合成小手算核对 | 合同 v1.1 §3.3（D-S0-2-04 全文）、§7；本矩阵 S0-04；统计计划 v1.1；preregistration.json | A2/A5 合成小手算核对；S1 分析脚本实现 | CLOSED（合同/计划侧）；S1 实现待验 |
| A5-S0-m01 stopping_rules 只写“非空” | minor | 合同统一为每项 strip 后长度≥2（与代码/统计计划一致） | 合同 v1.1 §7、§7.1 | A5 phase2 复核 | CLOSED |
| A5-S0-m02 feasible_v2 行号引用不准 | minor | 改为准确行号或函数名（HEAD a331639 + 修复后） | 合同 v1.1 §7.1、§9；本矩阵 S0-05 | A5 phase2 复核；固定 commit 后行号以 766a59c 为准 | CLOSED |
| A5-S0-m03 本矩阵状态/责任人 stale | minor | 按实际产出更新 S0-01..S0-10 状态/责任人/证据 | 本矩阵 §2.1（v1.2 更新） | A5 phase2 复核 | CLOSED |
| A5-S0-m04 快照时间口径 | minor | 区分 A1 修复前 541 / A1 后 546 / S0-2 604 tests 的时间与 SHA | docs/reviews/p4_route_a_s0_baseline_snapshot_20261105.md:15；本矩阵 S0-01 | A4 只读核对 | CLOSED（A5 phase2 未再列） |
| A5-S0-m05 CSV figure_status/notes 滞后 | minor | CSV 与 md 同步；无数据图标 NOT_RUN 但 figure_status 记录 4 GENERATED | docs/reviews/p4_route_a_s0_baseline_snapshot_20261105.csv:2；本矩阵 S0-09 | A4 只读核对 | CLOSED（A5 phase2 未再列） |
| A5-S0-m06 legacy 路径 fail-closed | minor | 旧 legacy 路径只读、不可写；新族不覆盖旧族 | 766a59c（family_v3.py 与测试）；冻结包 | A5 phase2 复核 | CLOSED |
| A5-S0-m07 normalize 契约 | minor | normalize 行为与合同/端点语义一致并有单测 | 766a59c（feasible_v2.py 与测试） | A5 phase2 复核 | CLOSED |
| A5-S0-m08 test_26f 覆盖 | minor | 补齐 26f 相关断言，纳入 604 tests | 766a59c（test_meta_learning_feasible_v2.py） | A5 phase2 复核 | CLOSED |
| A5-S0-m09 task_id 格式未定稿 | minor | 定稿正则并写入合同；生成器/隔离报告/合同一致，正则单测 | 合同 v1.1 §3、§7；D-S0-2-05；冻结包 task_id_regex；本矩阵 S0-02 | A5 phase2 复核 | CLOSED |
| A5-S0-m10 固定 commit 未记录 | minor | Lead 记录集成提交 SHA 并据此重跑测试 | 766a59c→a79959c→43fcfc8；Issue #7 回执 6653167378 | A5 phase2 复跑 604 tests | CLOSED |

> 说明：D-S0-2 实际文件为 D-S0-2-01..07（无 08/09）；本矩阵此前写 01..09 已按实际更正。上表 14 条为 A5 S0 审阅的全部 finding；A5 phase2 未新增 blocker/major。

#### 2.1.2 A5 phase2 开放 minor（8 条，非阻断）

| ID | 范围 | 关闭条件（摘要） | 对本轮影响 | 状态 |
|---|---|---|---|---|
| A5-S0P2-m01 | 冻结包 README | stored_sha256 措辞区分 raw CRLF 与入库 LF 口径 | 文档口径，不影响 S1 算法 | OPEN（A1/Lead） |
| A5-S0P2-m02 | 冻结包 README | make_freeze 复现路径写清固定 commit 与命令 | 复现性，不影响已冻结文件 | OPEN（A1/Lead） |
| A5-S0P2-m03 | v3_isolation_report | 旧 M6 目录标签补 meta- 前缀 | 可读性，不影响零交集结论 | OPEN（A1） |
| A5-S0P2-m04 | frozen_family calibration.note | 移除残留 PENDING 标记 | 口径一致性，不影响 radius=0.64 | OPEN（A1） |
| A5-S0P2-m05 | A2 校准证据 | 族版本标签滞后，采样参数未变，0.64 仍有效 | 证据标注，不影响校准值 | OPEN（A2/Lead） |
| A5-S0P2-m06 | calibration 绑定 | 绑定 A2 校准证据文件 sha256 | 可追溯性，不影响 S1 预算 | OPEN（A2/A5） |
| A5-S0P2-m07 | code_sha 口径 | 以 LF clean checkout 计算 code_sha | 复现性，不影响冻结输入 | OPEN（A3/Lead） |
| A5-S0P2-m08 | S1 分析脚本 | 强制 ENDPOINT_ROW_KEYS 9 键与 analysis_plan_digest，补 null/键名不一致负控 | S1 实现必须落实，已映射 S1-09/S1-17 | OPEN（A6/A5） |

### 2.2 S1｜K-shot→目标代理适应→BO 初始选点闭环（Issue #7 §2 S1，最高优先级）

> 详细实现文件/测试/验收证据映射见 docs/reviews/p4_route_a_s1_requirement_matrix.md（v1.0，task-217）；本表保留 12 条跨阶段需求视图，两表 ID 一致。

| 需求ID | 原文位置 | 要求（摘要） | 交付物/证据 | 角色 | 验收证据 | 状态 |
|---|---|---|---|---|---|---|
| S1-01 | §2 S1-1 | 扩展 adaptation.py / baseline_arms.py / m5_arms.py / m5_runner.py：K 次目标任务已评价样本的特征与目标/约束标签进入内循环，用适应后代理评分；不得读 query 标签、不得解析最优点、不得把代理预测写入 BO 真实 observations | 新接口 + 单测（支持样本进入/query 不可见/observations 只含真实评价） | A1 | 单测与代码审查；泄漏负控通过 | PENDING |
| S1-02 | §2 S1-2 | B∈{64,128}、K∈{0,1,3,5}；各臂共享同一 K 次目标任务评价，K 次必须计入 B；非物理代理时间单列 | run_config/budget ledger 字段 + 一致性断言 | A1+A2 | 每臂真实合成评价次数精确等于 B；支持评价已计费；五臂×K×B 预算表见合同 §4.2 | PENDING |
| S1-03 | §2 S1-2 | 8 个 BO 初始点由 K 个支持点+代理/随机补 8−K 个新点，再普通 BO B−8 次；K=0 复现旧初始化行为 | 初始化记录（designs sha256、来源标签）+ K=0 回归对照 | A1 | 初始点来源可区分、总数=8、K=0 与旧代码结果一致；DE 的 8−K 新点并入 population | PENDING |
| S1-04 | §2 S1-3 | 公平臂至少 Random-BO、Pretrain-Kshot-BO、FOMAML-ZeroShot-BO、FOMAML-Kshot-BO、DE；同任务/种子/候选池/约束 | arm 配置矩阵 + 公平性审计表 | A1+A2 | 各臂仅初始化路径不同；其余条件逐项一致 | PENDING |
| S1-05 | §2 S1-3 | 克隆识别、缓存与 null 规则一致；代理评分墙钟/缓存账单独记录 | 克隆判定报告 + 缓存/时间账 | A2+A5 | 机制相同标 clone 并排除因果推断；K=0 的 FOMAML-Kshot/ZeroShot 登记 CLONE；null 不补值 | PENDING |
| S1-06 | §2 S1-3 | 训练 episode 支持样本数与部署 K 匹配（5/10 或混合 K）；旧 128 样本内循环为消融基线 | episode 采样实现 + K_train∈{5,10,混合} 对比计划 | A1+A2 | K_train 与部署 K 对齐；旧 128 仅作消融 | PENDING |
| S1-07 | §2 S1-4 | 先做零物理单测：任务泄漏负控、真实合成评价预算精确一致、K>0 确实改变模型参数与初始选点 | 单测清单与日志 | A1 | 全部单测通过且失败会 fail-closed | PENDING |
| S1-08 | §2 S1-4 | 验证集小样本 pilot 通过后，A5 APPROVE_FOR_S1_FORMAL 才执行新独立 holdout；允许无改进 | pilot 报告 + A5 放行记录 | A1+A5 | A5 书面 APPROVE 后才有正式 holdout 运行 | PENDING |
| S1-09 | §2 S1-4、§4 | 按 B=64/128 分层报告主终点：best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate | statistics.csv + 图 + 中文报告 | A2 | 终点定义与预注册一致；不可行保留 null；列键按 ENDPOINT_ROW_KEYS | PENDING |
| S1-10 | §0、§2 S1 | 不得为让 MAML 获胜调参；负结果如实记录；正式 meta_test 一次性打开 | 分析与结论审查记录 | A1+A2+A5 | A5 核查无 meta_test 后调参、无有利任务筛选 | PENDING |
| S1-11 | §1 缺口（m5_arms.py） | 修复 score_m5_init_designs() 无 support_features/support_targets 参数、run_m5_bo_arm() 不传 k_shot/support 导致默认 k_shot=0 的闭环缺口 | 接口变更 + 兼容性单测 + K=0 回归 | A1 | K>0 支持样本真实进入适应；K=0 与旧行为逐位一致 | READ_ONLY_VERIFIED（缺口已核实，修复未做） |
| S1-12 | §2 S1、§4 | 产物齐全：preregistration.json、run_config.json、train_val_test_split.json、data_manifest.json、SHA256SUMS、CSV、图数据/PNG、中文报告 | 交付目录 + 清单 | A1+A2+A4 | 文件存在、SHA 可校验、缺数据标 NOT_RUN | PENDING |

### 2.3 S2｜完整二阶 MAML（Issue #7 §2 S2，S1 审查通过后）

| 需求ID | 原文位置 | 要求（摘要） | 交付物/证据 | 角色 | 验收证据 | 状态 |
|---|---|---|---|---|---|---|
| S2-01 | §2 S2 | maml.py 新增独立 algorithm=FULL_MAML 模式，保留旧 FOMAML 路径/API/已发布数字不变 | FULL_MAML 实现 + 旧结果回归对照 | A1 | 旧 FOMAML 结果逐位不变（或给允许误差=0 的说明） | PENDING |
| S2-02 | §2 S2 | 内循环函数式可微：torch.autograd.grad(..., create_graph=True)；不得对二阶链参数用 .data/detach 断图 | 实现 + 静态检查/单测 | A1 | 代码审查确认无断图；二阶链可回传 | PENDING |
| S2-03 | §2 S2 | 明确多步内循环计算图与随机种子控制 | 设计说明 + 单测 | A1 | 同种子两次运行结果一致 | PENDING |
| S2-04 | §2 S2 | 元梯度门禁：对原始 θ±ε 每次完整重跑内循环的全元目标有限差分，与 Full MAML 自动微分元梯度比较；旧 FD 只查适应后参数不能代替 | 梯度校验报告（误差表） | A1+A5 | FD 与自动微分元梯度一致度达到预注册阈值 | PENDING |
| S2-05 | §2 S2 | 增加 K>1、微型网络、数值稳定性与二阶 Hessian-vector 基准 | 基准脚本 + 结果 | A1 | 基准覆盖并记录数值稳定性 | PENDING |
| S2-06 | §2 S2 | FOMAML vs Full MAML 同构同数据同任务查询同优化器步数比较：query RMSE/MAE、最优可行值、可行率、首次可行、训练墙钟、峰值 RAM | 对照实验结果表 + 图 | A2 | 成对比较、置信区间、多重校正齐全 | PENDING |
| S2-07 | §2 S2 | 区分离线训练成本与在线函数评价成本 | 成本分项表 | A2 | 两类成本不混算 | PENDING |
| S2-08 | §0、§2 | S2 仅在 S1 验证与 A5 审查通过后开放 | 放行记录 | A5+Lead | A5 APPROVE + Lead 批准 | PENDING |
| S2-09 | §2 S2 | 若无统计收益或成本过高则保留低成本 FOMAML；不得宣传高阶必优 | 结论与决策记录 | A1+A5 | 结论有统计依据；失败即记录 | PENDING |

### 2.4 S3｜约束感知初始化与方法效率消融（Issue #7 §2 S3，S1/S2 验收后条件开启）

| 需求ID | 原文位置 | 要求（摘要） | 交付物/证据 | 角色 | 验收证据 | 状态 |
|---|---|---|---|---|---|---|
| S3-01 | §2 S3 | 针对 M5 可行率显著下降：比较纯目标排序、目标+约束评分、任务内约束归一化、预留随机/多样性比例 | 消融方案 + 结果表 | A1+A2 | 各方案同预算同任务；差异可归因 | PENDING |
| S3-02 | §2 S3 | 候选池规模与代理误差预算可审计 | 候选池/误差预算记录 | A2 | 与预注册一致、可复算 | PENDING |
| S3-03 | §2 S3 | 不确定度接口未标定时 uncertainty=null，不得输出伪置信概率 | 接口约束 + 单测 | A1 | 未标定即 null，无伪概率字段 | PENDING |
| S3-04 | §2 S3 | ANIL 仅适应输出层作低成本消融；Meta-SGD 需先证明少步适应不足并另行审批 | 消融计划/审批记录 | A1+A5 | 无审批不启动 Meta-SGD | PENDING |
| S3-05 | §2 S3 | 另建“目标最优与约束可行域中心不重合、解析参考解可验证”的新任务族；旧 F-QE-feasible-v2 保留 | 新任务族定义 + 解析参考解 | A1+A2 | 解析参考解独立可复算 | PENDING |
| S3-06 | §2 S3 | 先开发校准/冻结方案，再给新盲测集预注册推断；禁止事后筛选有利任务 | 校准/冻结方案 + 预注册 | A2+A5 | A5 核对无事后筛选 | PENDING |
| S3-07 | §2 S3 | S3 属路线A消融，禁止学习 BO 采集策略（路线B） | 边界声明 + 代码审查 | A1+A5 | 无采集策略学习代码 | PENDING |

### 2.5 S4｜航空接口合同（Issue #7 §2 S4，本轮只离线）

| 需求ID | 原文位置 | 要求（摘要） | 交付物/证据 | 角色 | 验收证据 | 状态 |
|---|---|---|---|---|---|---|
| S4-01 | §2 S4 | 版本化数据合同字段：task_id、design_set、evaluator_id、fidelity、source_kind、physics_validation_status、solver_version、config_hash、constraints_g_le_zero、physical_call_count | 合同 schema + 校验实现 | A1+A4 | 字段齐全、类型/枚举校验 | PENDING |
| S4-02 | §2 S4 | 本轮只离线：允许合成 LF/HF 偏差函数与只读 VSPAERO 归档元数据演练数据流 | 演练脚本 + 只读证明 | A1+A2 | 无真实求解器启动记录 | PENDING |
| S4-03 | §2 S4、§3 | VSPAERO_INTERNAL_ONLY 不得当作已验证 HF 或真实燃油标签；真实物理状态只能来自负责人批准的证据 | 标签校验 + 负控测试 | A1+A5 | 伪造/误标标签被拒绝 | PENDING |
| S4-04 | §2 S4 | 不得调用 RCAIDE Mission、SU2、新 VSPAERO 真实算例；合成 meta_test 不得混入真实算法结果 | 隔离测试 | A1 | 物理调用计数=0；合成/真实数据流分离 | PENDING |
| S4-05 | §2 S4 | 真实 12D 航空 BO/DE/MAML 需另行批准物理预算与适用域，S4 不自动开启 | 待批准清单 | Lead | 负责人书面新预算 | PENDING |
| S4-06 | §2 S4 | 合同测试失败即 fail-closed（未授权 fidelity/标签污染/缺少 provenance 一律拒绝） | 失败路径单测 | A1 | 负向用例全部拒绝 | PENDING |

### 2.6 跨阶段：统计门禁、角色分工与安全边界（Issue #7 §3–§4）

| 需求ID | 原文位置 | 要求（摘要） | 交付物/证据 | 角色 | 验收证据 | 状态 |
|---|---|---|---|---|---|---|
| STAT-01 | §4 | 每阶段先用 meta_train/meta_validation 调参与代码门禁；冻结 family_version/task_fingerprint/prereg 后打开独立 meta_test | 阶段冻结记录 | A2+A5 | 打开前冻结、打开后不改 | PENDING |
| STAT-02 | §4 | 主终点：best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate | 终点定义与统计代码 | A2 | 与预注册一致；禁用别名 first_feasible_evaluation_index | PENDING |
| STAT-03 | §4 | 不可行保留 null，不插值不补零；绘制无可行 run 比例 | 统计输出与图 | A2 | null 原样保留；null 率>70% 标 INCONCLUSIVE | PENDING |
| STAT-04 | §4 | 任务为一级配对/重抽样单位，不把种子当独立任务放大显著性 | 统计方案 | A2+A5 | 配对/聚类层级正确 | PENDING |
| STAT-05 | §4 | 同任务≥20（研究需要可增大）、≥3 独立元训练 seed、10 优化 seed | 实验设计 | A2 | 预注册数量与实际一致；meta_test 固定 20 任务 | PENDING |
| STAT-06 | §4 | 附 RMSE/MAE、代理时间、峰值内存、全部训练成本与可重复性；事先约定多重比较校正与失败规则 | 统计表 + 成本表 | A2 | 成本与校正前置于分析 | PENDING |
| STAT-07 | §4 | 至少 7 类中文图：损失/梯度、K-shot 误差与步数、可行率、等预算最优/首个可行、FOMAML vs Full MAML、任务/OOD 诊断、VSPAERO 已获证据图 | 图数据+PNG | A2+A4 | 图标题/图注/结论中文；无数据标 NOT_RUN 不绘虚构曲线 | PENDING |
| ROL-01 | §4 | Leader 批准 S0→S3 阶段启动并唯一负责 GitHub 发布 | 放行与发布记录 | Lead | 每阶段有批准记录 | PENDING |
| ROL-02 | §4 | A1 负责 K-shot-BO 新接口与二阶核心代码、单测、保留旧 API | 代码提交（经 Lead） | A1 | 代码审查与单测 | PENDING |
| ROL-03 | §4 | A2 负责预注册、同预算实验、多 seed 统计、图表脚本与数值重算 | 统计/图表交付 | A2 | 可复算 | PENDING |
| ROL-04 | §4 | A3 负责干净 worktree、Git SHA、manifest 与历史运行原样保留、与主库 P5 资料隔离 | 隔离记录 | A3 | 旧 run SHA 不变、worktree 干净 | PENDING |
| ROL-05 | §4 | A4 负责 Issue #4/#5/#7 需求/门禁矩阵、中文计划与中文回执（只读 GitHub） | 本矩阵及回执草稿 | A4 | 矩阵逐条可追溯 | READ_ONLY_VERIFIED（本文件） |
| ROL-06 | §4 | A5 独立检查泄漏/支持样本计费/二阶梯度真实性/克隆臂/统计公平性/非物理标签隔离；每阶段 APPROVE 放行 | A5 审查记录 | A5 | 每阶段签 PASS/CHANGES_REQUESTED | PENDING |
| SAFE-01 | §0、§3 | physical_call_count=0 硬隔离；不得启动真实飞机 BO/DE、真实航空元训练、新 VSPAERO、SU2/Mission/WaveDrag/RCAIDE 回退 | 运行前后计数核对 | A1+A3+A5 | 每次运行 physical_call_count 字段=0 | PENDING |
| SAFE-02 | §3 | RCAIDE B 类 12 次保持 LOCKED/NOT_TRIGGERED/NOT_EXECUTED；不得实现/启动 fallback evaluator/Mission/自动回退 | 只读核查 | A3+A5 | 无新 RCAIDE 运行/代码 | PENDING |
| SAFE-03 | §3 | VSPAERO 改进只在 Issue #4 实施；本 Issue 不新增 VSPAERO 求解 | 边界声明 | A4 | 交叉检查 | READ_ONLY_VERIFIED（D-12D-006 已声明） |
| SAFE-04 | §4 | FAIL-CLOSED：泄漏/梯度不一致/预算不一致/元测试后调参/主数据破坏/真实物理调用非零 → 停止对应 run，写 JSON+中文报告 | 失败处理流程 | A1+A5+Lead | 事件均落盘并上报 | PENDING |
| SAFE-05 | §3、§4 | 旧 PR #3/#6 保持 open 不合并 main；成果单独 PR 以 research/p4-meta-learning 为基线，最终合并策略由负责人确认 | 分支/PR 状态记录 | A3+Lead | PR #3/#6 merged=false；无 main 合并 | READ_ONLY_VERIFIED（2026-11-05 11:49 实测） |
| SAFE-06 | §3 | 不删除/覆盖历史运行与历史 PR；旧冻结工件只读 | 只读保护记录 | A3 | SHA 对比无变化 | PENDING |

> 统计：本矩阵共 10（S0）+12（S1）+9（S2）+7（S3）+6（S4）+19（跨阶段）= 63 条唯一需求ID。每条均可回查到 Issue #7 §2 对应小节或 §3/§4 段落。S0-2 关闭对照表另列 14 条 A5 finding（M01..M04/m01..m10），不计入 63 条需求；A5 phase2 另有 8 个开放 minor（A5-S0P2-m01..m08），非阻断、单列。

## 3. Issue #4 / #5 / #7 门禁关系表

| 门禁/关系项 | Issue #4（物理气动验收） | Issue #5（历史算法基线） | Issue #7（本轮路线A） | 关系与约束 | 责任 |
|---|---|---|---|---|---|
| GEO-12D | PARTIAL：几何/参考量/薄面就绪，未签发 | 历史 M5/M6 为合成任务，不涉及物理几何 | 不涉及；S0 只读校验 M2/M5/M6 manifest | #7 不改变 #4 几何门禁状态 | A2/A5 |
| LF-M2.02 | NOT_VALIDATED：A 线在 14/20 关闭，仅内部可重复 | 无 LF 物理结论 | 并行气动归 #4；本 Issue 不启动 VSPAERO 求解 | VSPAERO_INTERNAL_ONLY 不得作为 #7 的已校准 LF 真值 | A1/A5 |
| HF-M2.02 | PARTIAL：仅既往 SU2 能力；C 类 0/4 锁定 | 无 HF 物理结论 | 未批准 SU2 新调用 | #7 合成实验不得引用未验证 HF 标签 | A5 |
| BODY-CORR | BLOCKED：面积律 NOT_VALIDATED，未注入机身修正 | 合成任务无机身修正 | 不涉及 | #7 不得用 #4 内部 CDtot 拟合“机身修正” | A2/A5 |
| MISSION-DATA | PARTIAL：任务数据合同未变，无新 Mission 运行 | 历史合成数据合同可参考 | #7 只用合成解析任务；S4 只设计接口 | RCAIDE Mission 保持暂停 | A3 |
| BUDGET | GATED：A 14/20，剩余 6 关闭不结转；B 0/12、C 0/4 锁定；D/E/P4 0 | 历史 run 不新增预算 | physical_call_count=0；任何新物理预算需负责人书面批准 | #7 不得自动复活 #4 剩余 6 次或 B/C 类 | Lead |
| 算法阶段门禁 | 不开放 P4/P5/P6；#4 不启动 BO/DE/MAML | M2/M5/M6 为历史算法证据（负结果保留） | S0 COMPLETE；S1 实现未开始；S1→S2→S3→S4 每阶段 A5 放行 | #4 的“不启动 P4”与 #7 的“路线A算法开发”互不替代：后者仅合成离线 | A5/Lead |
| APPROVED_FOR_NEXT_STAGE | false（D-12D-005 结论） | A5 APPROVE_FOR_ISSUE5_RECEIPT 仅为软件/证据交付批准 | 阶段放行为 A5 APPROVE，不等于物理验证或最终发布 | 任何阶段批准不得被解读为物理门禁通过 | Lead |
| 证据冻结 | d12d005-20261104T0430Z 只读 | M2/M5/M6 归档只读 | S0 只读校验，不可重跑覆盖 | 三处一致：旧工件不可改写 | A3+A5 |
| 分支/PR 边界 | PR #3 open（head e5140fc，未合并） | PR #6 open（head ff6280f，未合并） | research/p4-route-a-s1 @ 43fcfc8，尚无 PR | 旧 PR 不合并 main；成果单独 PR，合并由负责人确认 | A3+Lead |

**门禁关系结论（关键 5 条）：**

1. Issue #7 的 S0–S4 是**合成离线算法研究**，不能改变 Issue #4 的任何物理门禁状态；任何“通过”仅表示算法/证据门禁通过。
2. Issue #4 的 VSPAERO 内部 CD 值（VSPAERO_INTERNAL_ONLY）不得作为 #7 的已校准 LF/HF 标签或真实燃油目标；#7 的合成 LF/HF 只能来自解析偏差函数。
3. Issue #4 剩余 A 类 6 次已 CLOSED 不结转，B 类 12 次、C 类 4 次保持 LOCKED；#7 不得自动触发或复活任何物理预算。
4. 旧 Issue #5（M2/M5/M6）只作为历史基线/负结果对照，旧 holdout 不得当新盲测；#7 新结论必须来自独立新任务族。
5. APPROVED_FOR_NEXT_STAGE 只能由负责人签发；#4 当前为 false，#7 的阶段 A5 APPROVE 不等价于该签发，也不等价于合并 main。

## 4. 阶段依赖与放行顺序

```
S0（基线冻结/预注册/设计合同/风险清单/基线快照）
  └─ A5 S0 审阅 APPROVE_FOR_S1_PREP（条件式）
       └─ S0-2（五 split/端点/预算/代码 minor 关闭 + frozen_family/prereg/isolation/determinism/预算公平测试）
            └─ A5 S0-2 复审 APPROVE_FOR_S1_FORMAL（ea9b2eb7…）+ A3 PASS 11/11（23bac611…）+ Lead 集成提交 766a59c/a79959c/43fcfc8 + Issue #7 回执 6653167378
                 └─ S1（K-shot→BO 闭环；实现未开始；先单测→pilot→A5 APPROVE_FOR_S1_RUN→Lead 授权 A2 formal run）
                      └─ S2（FULL_MAML；元梯度门禁 + A5 审查）
                           └─ S3（约束感知初始化/ANIL 消融；条件开启）
                                └─ S4（航空接口合同，只离线）
任何阶段出现泄漏/预算不一致/真实物理调用非零/旧工件改写 → 停止该 run 并上报。
```

## 5. 待 Lead/负责人决策项

1. 已关闭：S0-2 经 A5 phase2 判 APPROVE_FOR_S1_FORMAL（0 blocker/0 major/8 minor），Issue #7 回执 6653167378 已由 Lead 发布。
2. S1 实现→A5 审阅 APPROVE_FOR_S1_RUN→Lead 授权 A2 formal run；当前 S1 未开始，正式 holdout 未打开。
3. Full MAML 的梯度一致性阈值与“无收益则保留 FOMAML”的判定规则需在 S2 前冻结。
4. A5 phase2 8 个 minor 的关闭责任：A1/Lead（m01..m04）、A2/Lead（m05/m06）、A3/Lead（m07）、A6/A5（m08）；不阻断 S1 formal，但 m08 必须在 S1 分析脚本实现。
5. 任何新增物理预算仍须负责人书面批准；#4 的 A 类剩余 6 次 CLOSED 不结转、B/C 类 LOCKED 不变。

## 6. 证据与读取记录

- Issue #7：GitHub 只读，读取时间 2026-11-05T11:49 (UTC+8)；state=open；正文全文落盘 <EXT>/d12d006/a4/raw/issue7_body.txt；读取时 comments=0，其后 Lead 发布回执 6653167378（现 1 条评论）。
- Issue #4：state=open，comments=15；最新评论 6647827491（D-12D-006）。
- Issue #5：state=open，comments=3；最新终态回执 6643119583（2026-11-04T21:55:56Z）。
- PR #3/#6：open、merged=false、mergeable clean；PR #7 不存在（404）。
- S0-2 裁定：docs/planning/p4_route_a_s0_2_decisions_20261105.md（Lead，D-S0-2-01..07）；冻结包 p4ra-s0-2-freeze-20261105T072500Z。
- A5 phase2：<EXT>/p4-route-a/a5/S0_2_A5_review_phase2.md（sha256 ea9b2eb708fa660fb84a913bc1b5f63624a7303337fff574ad2c4c05905068d8；0 blocker/0 major/8 minor；独立复跑 604 tests OK(skipped=1)/37.687s；8 payload 逐字节一致；determinism 29/29；physical=0）。
- A3 phase2：<EXT>/EXT/p4-route-a/a3/S0_2_phase2_isolation.md（sha256 23bac611159b76064a39789a27837e7e5c92e31a573585f2f137ef9aec92858d；PASS 11/11；三提交单父非 merge；旧 M2/M5/M6 tree_agg 未变；0 solver）。
- 本地 HEAD（读取时点）：S1 工作树 = 43fcfc851525bd74935b20c85dfbea2d932e436e，branch research/p4-route-a-s1；porcelain 仅 1 个未跟踪 S1 执行计划（A4 未 commit、未改代码/冻结包）。D12 工作树 = aef2cb7；主库 = e5140fc（research/concorde-metaopt，含历史未提交改动，未触碰）。
- 本文件与设计合同/风险清单为 A4 文档交付；未执行任何物理计算、GitHub 写操作、git commit/push。S1 详细映射见 docs/reviews/p4_route_a_s1_requirement_matrix.md。

## 7. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4 | 首次生成 63 条需求矩阵与 #4/#5/#7 门禁关系表（S0 预注册草案） |
| v1.1 | 2026-11-05 | A4（task-197） | 按 D-S0-2 与 A5 S0 审阅更新 S0-01..S0-10 状态/责任人/证据；新增 §2.1.1 S0-2 关闭对照表（A5-S0-M01..M04/m01/m02/m03/m09）；S0 总状态标 NOT_COMPLETE；阶段依赖加入 S0-2 复审；未执行物理计算与 GitHub 写操作 |
| v1.2 | 2026-11-05 | A4（task-212/217） | S0 总状态 COMPLETE；S0-01..10 全 PASS；关闭对照表扩至 14 条 A5 finding 并新增 A5 phase2 8 minor 单列；引用 A5 phase2 ea9b2eb7…/A3 23bac611…/冻结包/604 tests/Issue #7 回执 6653167378；更正 D-S0-2 为 01..07；阶段依赖、决策项、证据与版本更新；新增 S1 详细矩阵指针；未执行物理计算与 GitHub 写操作 |
