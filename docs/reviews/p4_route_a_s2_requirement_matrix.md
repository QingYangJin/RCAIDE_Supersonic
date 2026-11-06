# P4 路线A S2 需求矩阵（v1.2a）

- 文档性质：Issue #7 S2 的只读需求—证据—状态核对表，供 Lead/A5/A1/A6 使用；不是阶段验收结论，不替代 A5 verdict，不构成 S2_RUN 授权。
- 位置：分支 research/p4-route-a-s2；HEAD=origin=89fd8d9；base=1a2b242；S2 专用 worktree（本文路径均为仓库相对路径或 <EXT> 占位）。
- 依据：Issue #7 正文 §2 S2、§4 通用要求；S2 执行计划 v1.5（commit 89fd8d9，39,246 B / 290 行，sha256 f156b250…）；A5 S2-M0/M0R/M0R2/M0R3/M0R4/M0R5，M0R5 为 APPROVE_FOR_S2_CODE_AMENDED（0B/0M/1 非阻断 minor，对象 89fd8d9）；M0R4 历史结论 CHANGES_REQUESTED（对象 0c85aee）；R-S2-01 与 R-S2-01A；S0-7 冻结包；S1 收尾矩阵。
- 读取时点：2026-11-06 22:08 +08（2026-11-06T14:08Z）；A1/A6 未提交/未跟踪文件按 22:07Z git status 观测，本矩阵不把未提交代码写成已实现或已审阅。
- 变更：v1.2a（2026-11-06T22:15+08）：仅修正 R-S2-01A 引用沿革——最新 raw sha256 7d6f9739f0e62e96981e40156f3abf430daea2fcdc9bda1d2c0813eae104b9c5（LF canonical 49ffa9c5…）；A5 M0R5 文本引用的 4b2a7901… 为其审阅时旧版本，已由 M0R5 通过后 Lead 追加的 M0R5 APPROVE 记录取代；其余内容不变。
- 变更：v1.2（2026-11-06T22:08+08）：计划引用升级 v1.5/89fd8d9；A5 状态改为 M0R5 APPROVE_FOR_S2_CODE_AMENDED（M0R4 CHANGES_REQUESTED 为历史）；C-01..C-07 保持 CLOSED，补 A5-M0R4-F-01..F-05 闭合证据；图合同 7 键→9 键并补 Issue #7 §4 七类映射；保留 v1.1 历史。
- 状态口径：APPROVED_DESIGN 仅表示 A5 已批准设计（当前基线为 v1.5/89fd8d9，M0R5 APPROVE_FOR_S2_CODE_AMENDED；v1.3/969c0e7 为历史批准对象；v1.4/0c85aee 为 M0R4 CHANGES_REQUESTED），不等于实现、运行或 S2_RUN 授权；CLOSED 表示文档/合同层已由计划 v1.5 处置，最终以 A5 M0R5 结论为准；NOT_RUN/NOT_CREATED 表示无产物；ACTIVE_BOUNDARY 表示现行边界。
- A4 边界：本文只读核对；未改代码/计划/冻结包；未 commit/push；未写 GitHub；physical_call_count=0；无新物理求解。

## 1. 当前状态与硬边界

| 项目 | 当前事实 | 证据 | 状态 |
|---|---|---|---|
| S2 设计门 | A5 S2-M0R5 给出 APPROVE_FOR_S2_CODE_AMENDED（0B/0M/1 非阻断 minor），对象 89fd8d9（计划 v1.5，39,246 B / 290 行、sha f156b250…）；v1.5 为代码与图合同基线；M0R4 对 v1.4/0c85aee 的 CHANGES_REQUESTED（F-01..F-05）已由 v1.5 关闭；A5 代码审阅尚未开始 | <EXT>/p4-route-a/a5/S2_M0R5_review.md（8,178 B、sha b1465858…）；计划 v1.5；git log | APPROVED_FOR_S2_CODE_AMENDED（v1.5/89fd8d9）；CODE_REVIEW_NOT_STARTED |
| S2 代码 | 截至 22:07Z，A1/A6 已在共享 worktree 写入未提交/未跟踪文件：maml.py 未提交修改（39,759 B）、s2_runner.py（5,968 B）、s2_prereg.py（33,715 B）、s2_analysis.py（180,624 B）、s2_figures.py（19,821 B）、evidence/；tests/test_maml_full.py（12,777 B）、tests/test_s2_analysis.py 未跟踪；tests/test_s2_runner.py、tests/test_s2_prereg.py 尚未出现；未提交、未审阅、未运行 | git status/文件快照（22:07Z）；上述文件 | IN_PROGRESS（A1/A6，未提交未审阅） |
| S2 prereg | 尚未创建 prereg 文件；无冻结记录；S2_RUN 未授权；计划 v1.5 §7 要求 frozen_package 双 family、resource_limits={per_seed_train_wall_s:1200, peak_memory_mb:8192, total_wall_s:7200}，verify 机械校验 | 计划 §7 L124-126、L136；仓库内无 s2_preregistration.json | NOT_CREATED |
| S2 正式 run | 未执行；无 run 目录、无 6,000 行训练/评估产物；无 A5 结果复核 | 计划 §5、§9、§11；无正式 run 产物 | NOT_RUN；S2_RUN=NOT_APPROVED |
| 物理调用 | physical_call_count=0；本轮/本阶段无 VSPAERO、SU2、RCAIDE Mission、CFD、WaveDrag、批量 DOE | 计划头部硬边界；S0-7 freeze_summary physical_call_count=0；A4 核对无新求解 | 0（ACTIVE_BOUNDARY） |
| S1 基线 | S1_RUN=EXECUTED_AND_RESULT_REVIEWED；Issue #7 回执 commentId 6684142041；S1 签发不含 S2 授权 | Issue #7 评论；<EXT>/p4-route-a/lead/S1_RUN_RESULT_ACCEPTANCE_20261106.md；S1 收尾矩阵 v1.8 | CLOSED_HISTORICAL |
| S0-7 数据基线 | 冻结包 SHA256SUMS sha 59aa81cd…；code_sha 7304d32e…；git_sha 004156c…；counts 60/20/20/10/10；holdout_seed 20261106；family_fingerprint a1f9462c…；split_hash cd597d01…；confirmatory_eligible=true；physical=0 | research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z/（SHA256SUMS.txt、freeze_summary.json） | FROZEN_READ_ONLY |
| 文档/证据链 | 计划 v1.5 已提交 89fd8d9（sha f156b250…）；A5 M0R5 已 APPROVE_FOR_S2_CODE_AMENDED（0B/0M/1 minor：S0-7 单 family/fig9 仅族内分布/A6 图注注明）；R-S2-01A 最新 raw 7d6f9739…/LF 49ffa9c5…（A5 M0R5 文本 4b2a7901… 为审阅时旧版本），R-S2-01 已更新；C-01..C-07 与 F-01..F-05 均在计划层关闭 | 计划 v1.5；A5 M0R5；§6 | CURRENT_APPROVED_AMENDED（M0R5） |
| Issue #4 | 独立 VSPAERO/气动验证轨道；S2 不调用任何气动求解器，也不修改 Issue #4 门禁；Issue #4 状态不由本矩阵验收 | Issue #4 URL；计划头部硬边界 | SEPARATE_BOUNDARY |
| Issue #5 / PR #6 | 历史基线；S2 不复用/不覆盖其运行与结果；不合并 main | Issue #7 §1；计划头部 | CLOSED_HISTORICAL |
| A4 输出 | 本文 v1.2a（未提交）；EXT 回执草稿（按 v1.5/M0R5 事实更新，DRAFT_NOT_PUBLISHED）、刷新报告 task224_s2_refresh_v12a.md | docs/reviews/p4_route_a_s2_requirement_matrix.md；<EXT>/p4-route-a/a4/ | IN_PROGRESS |

## 2. S2 需求矩阵（S2-01 至 S2-12）

| ID | 需求与来源 | 验收标准（可复核） | 当前状态 | 责任/证据 | A5 findings 映射 |
|---|---|---|---|---|---|
| S2-01 | 新增独立 FULL_MAML 模式，保留旧 FOMAML 路径/API/原有数字；不得以 FOMAML 冒充二阶 | maml.py 有独立 FULL_MAML 分支；旧 API/旧测试不改；旧 FOMAML 数字可复现；代码审阅确认未改旧路径 | APPROVED_DESIGN / IN_PROGRESS_CODE | A1；计划 §4.1 L49-51；Issue #7 §2 S2 第 1 条；21:23Z maml.py 未提交 +269/−6、test_maml_full.py 未跟踪；A5 代码审阅未开始 | A5-S2M0R3：0B/0M；设计层已闭合，代码实现中，未审阅 |
| S2-02 | 函数式可微内循环：create_graph=True；内循环不得用 .data/detach 切断二阶；元梯度需回到原始 θ | 单测证明二阶梯度存在且非零；旧 FOMAML 路径不受影响；代码审计无内循环断图 | APPROVED_DESIGN / IN_PROGRESS_CODE | A1；计划 §4.1 L49-51；Issue #7 §2 S2 第 2 条；21:23Z A1 已改 maml.py（未提交），测试未运行 | A5-S2M0-M01（FD/二阶口径，设计闭合）；M0R3 无新增 |
| S2-03 | 全元目标有限差分：扰动原始 θ±ε，每次完整重跑内循环；旧 FD 只查适应后参数不能代替；eps=1e-6*max(1,|θ|)，top-32，阈值 1e-6 fail-closed；先 micro/full pilot | pilot 记录在 run_config；analytic 与 FD 相对误差 <=1e-6；micro hidden(8,8)/1 步/32 坐标与 full hidden(16,16)/2 步/8 坐标均通过；失败即停 | APPROVED_DESIGN / IN_PROGRESS_CODE / PILOT_NOT_RUN | A1 实现，A5 复核；计划 §4.3 L59-64；R-S2-04；21:23Z 编码中，pilot 未运行 | A5-S2M0-M01 CLOSED（设计）；M0R2-M01/M0R3-N01 为文档顺序，不改变 FD 合同 |
| S2-04 | K=0 同 θ 梯度等价门禁：同 theta、inner_steps=0，FULL 与 FOMAML 梯度差 <=1e-12；仅证明梯度等价，不证明训练后模型等价 | 单测在固定 seed 下通过；报告明确 K=0 仅门禁，不作为算法等价性/效果比较；K=0/1 描述性 | APPROVED_DESIGN / IN_PROGRESS_TESTS | A1；计划 §4.2 L54-56；R-S2-03；Issue #7 §2 S2；21:23Z test_maml_full.py 已新增 12,777 B 未跟踪，未运行 | A5-S2M0-B01 CLOSED（M0R 确认语义拆分）；M0R3 无新增 |
| S2-05 | 等预算、两臂公平：FULL 与 FOMAML 除 first_order 外全部同配置（input12/output1/hidden(16,16)/inner_lr0.01/inner_steps5/outer_lr1e-3/tasks8/seed42/backend torch）；outer_steps200、meta_seed{0,1,2}；build+verify 双重断言 S2_ARM_CONFIG_MISMATCH | run_config 两臂配置 diff 仅 first_order；build 与 verify 均校验；C1=FULL−FOMAML 同任务/种子/候选/预算；两臂共享同一任务/support/query/评估预算；不得出现克隆臂/免费先验 | APPROVED_DESIGN / PENDING_CODE | A1；计划 §4.4 L67-68、§7；Issue #7 §2 S2 第 4 条；R-S2-02 | A5-S2M0R-B04 CLOSED（M0R2 功能 PASS）；M0R2-N01 CLOSED（M0R3） |
| S2-06 | 训练 episode bank 确定性：derive_seed 按 scope 派生；训练 support16/query32、batch 8 任务；两个进程逐字节一致；manifest sha 写入 run_config | 两次构建 bank 的 manifest 逐字节一致；评估 support K/query64、draw 0..9、K∈{0,1,5,10}；种子/顺序可复现；异常 fail-closed | APPROVED_DESIGN / PENDING_CODE | A1；计划 §3 L33-44；R-S2-06 | A5-S2M0-M04 CLOSED（M0R）；代码未实现 |
| S2-07 | 数据边界 fail-closed：load_s2_tasks 校验 SHA256SUMS 9/9；只允许 meta_train(60)/meta_validation(20)；3 项负控；run_config 记录 holdout 身份且 holdout_rows_used=0；不使用 S1 holdout | 负控（篡改/缺失/非法 split）均失败；run_config 中 holdout 身份可核；无 S1 holdout 行；越界即停 | APPROVED_DESIGN / PENDING_CODE | A1；计划 §2 L22-28；R-S2-05；S0-7 | A5-S2M0-M02 CLOSED（M0R） |
| S2-08 | 端点与统计：唯一主终点 post_adaptation_rmse_raw_k5；次要 post_adaptation_rmse_raw_k10；唯一 Holm 族 family_id=s2-primary-secondary-2tests、family_key=s2_primary_secondary、family_size=2；Wilcoxon n=20 双侧、bootstrap 10,000 seed 20261105、95%CI、Holm | 端点、族、检验、seed、CI 全部落 prereg；只对 2 个端点做 Holm；不得把 K=0/1、标准化 RMSE、MAE、资源等描述性指标升级为主结论；空/null 不插值 | APPROVED_DESIGN / PENDING_ANALYSIS | A2 分析，A5 复核；计划 §1 L13-19、§6 L84-93；R-S2-02 | A5-S2M0-B01/B02 CLOSED；M0R-M07 CLOSED（M0R2 PASS） |
| S2-09 | 统计决策与证据范围：C1=FULL−FOMAML（负值有益）；SUPPORTED_BENEFIT/HARM 需 p<0.05+CI 不跨 0+方向+相对 >=1%；INCONCLUSIVE 为 null>70%；其余 NO_EVIDENCE；证据范围 DEVELOPMENT_VALIDATION_ONLY；不得外推为未见任务确证性泛化 | 决策规则、效应量、null 处理、证据范围写入 prereg/报告；报告每个数字有 CSV 路径；不得称“显著提升/已证明优于 FOMAML” | APPROVED_DESIGN / PENDING_ANALYSIS | A2/A5；计划 §6、§8；R-S2-01、R-S2-02、R-S2-07；Issue #7 §4 | A5-S2M0-M03 CLOSED；M05 ACCEPTED_SCOPE_REDUCTION |
| S2-10 | 预算/资源/失败规则：训练 1,200 行 + 评估 4,800 行 = 6,000 行；记录 peak_memory；单 (arm, meta_seed) 训练墙钟 >20 min 或峰值 >8 GB 标 RESOURCE_LIMIT 并停止整个正式 run（不重试）；正式 run 总硬截止 2 h；prereg.resource_limits={per_seed_train_wall_s:1200,peak_memory_mb:8192,total_wall_s:7200} 且 verify 机械校验；非有限/失败即停并报告部分产物 | 预算、行数、资源阈值、resource_limits、停止规则写入 prereg；实际墙钟/内存有日志；任何超限标 RESOURCE_LIMIT；不得无授权续跑/重试 | APPROVED_DESIGN（C-01/F-03 CLOSED） | Lead/A2/A5；计划 §5 L190、§7 L124-126/L136、§9、§12 L227 | A4-S2C-01 CLOSED（v1.5 §5/§7/§9/§12）；A5-M0R4-F-03 CLOSED（M0R5） |
| S2-11 | prereg 合同：canonical JSON（sort_keys/separators/ensure_ascii=False/allow_nan=False+换行）；prereg_id 排除自身与 prereg_digest；prereg_digest 仅排除自身；code_sha 按 Python sorted 字典序（maml.py、s2_prereg.py、s2_runner.py）拼接 sha256；analysis_plan_digest 对 endpoints/comparison/statistical_plan/fd_gate 四节 canonical sha256；arms 公平；pilot_artifacts 相对仓库根且 sha 匹配；frozen_package 同时写 package_family_version=p4ra-family-v4 与 task_family_version=p4ra-family-v3；resource_limits={per_seed_train_wall_s:1200,peak_memory_mb:8192,total_wall_s:7200} 且 verify 固定值校验；占位拒绝；冻结流程 Lead→A5 核验→APPROVE_FOR_S2_RUN→Lead 授权→A2 run | 本地/独立核验脚本对 prereg 重算 digest 一致；占位/绝对路径/sha 不符负控均失败；Lead 冻结 commit 可追溯；A5 核验记录齐全 | APPROVED_SCHEMA / PREREG_NOT_CREATED | Lead 冻结，A5 核验，A1 提供 code_sha 输入；计划 §7 L99-137；R-S2-09 | A5-S2M0-B03 CLOSED；B03R CLOSED（M0R2 部分→M0R3）；M0R2-M01/N02 CLOSED；M0R3-N01 CLOSED（v1.4）；C-04 CLOSED；F-03 CLOSED（v1.5 §7/§12） |
| S2-12 | 代码、测试、分析、图与交付包：实现 maml.py FULL_MAML/s2_prereg.py/s2_runner.py 及测试；生成 run_config/summary/preregistration/data_manifest/CSV/figures PNG；按计划 §8.1 输出 fig1..fig9 共 9 个诊断图键，并按 §8.1.1 映射 Issue #7 §4 七类（③/④/⑦ 显式 NOT_APPLICABLE）；Issue #7 §2 要求的元梯度误差、RMSE/MAE、训练墙钟、峰值 RAM 等可比项；feasible/首次可行/最优可行按 R-S2-02/07 标 NOT_APPLICABLE_S2_SURROGATE_SCOPE | A1/A6 代码与测试通过；A5 代码审阅；正式 run 后 A5 结果复核；每图有数据源与 CSV/PNG 映射；9 键与七类映射齐全；报告用中文；不得把设计文档/占位图当结果 | IN_PROGRESS_CODE / IN_PROGRESS_ANALYSIS / FIGURES_NOT_RUN | A1/A6/A4/A5；计划 §8.1 L144-184、§8.1.1 L160-172、§8.1.2 L174-184、§12 L225；22:07Z A1/A6 已写未提交/未跟踪 s2_runner.py、s2_prereg.py、s2_analysis.py、s2_figures.py、evidence/；测试未运行 | A5-S2M0-M05 ACCEPTED_SCOPE_REDUCTION、M06 CLOSED；A4-S2C-03 CLOSED（v1.5 §8.1）；A5-M0R4-F-01/F-05 CLOSED（M0R5） |

## 3. 跨阶段与硬边界项（X-01 至 X-11）

| ID | 边界/跨阶段要求 | 当前事实 | 状态 |
|---|---|---|---|
| X-01 | S2_RUN 必须经 A5 代码审阅、Lead prereg 冻结、A5 prereg 核验、Lead 书面授权；设计批准不等于运行批准 | 当前 A5 M0R5 APPROVE_FOR_S2_CODE_AMENDED（对象 89fd8d9）+ 代码审阅未开始；S2_RUN=NOT_APPROVED；无 prereg、无正式 run | ACTIVE_BOUNDARY |
| X-02 | physical_call_count=0；禁止 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag/批量 DOE；禁止以任何外部求解器替代 | 无求解器进程/调用/产物；S0-7 physical=0；A4 本轮 0 物理 | ACTIVE_BOUNDARY |
| X-03 | 不合并 main；不新建 PR；PR #3/#6 保持 open；S2 在独立分支/worktree；仅 Lead 可写 GitHub | 分支 research/p4-route-a-s2；HEAD=origin=89fd8d9；A4 未写 GitHub；PR #3/#6 按历史状态保持 open（本轮 S2 不涉及合并） | ACTIVE_BOUNDARY |
| X-04 | 旧证据只读：M2/M5/M6、S0-2..S0-7、S1 运行/分析/冻结包不得改写、重分类或覆盖；旧负结果保留 | 无旧 run 修改；S0-7 只读核对；A4 未触碰旧产物 | ACTIVE_BOUNDARY |
| X-05 | S2 仅使用 S0-7 meta_train/meta_validation；不使用 S1 holdout；结论范围 DEVELOPMENT_VALIDATION_ONLY；不得外推 confirmatory/真实飞机 | 计划 §2/头部；S0-7 counts 60/20/20/10/10；无 S1 holdout 使用 | ACTIVE_BOUNDARY |
| X-06 | A5 每阶段门：M0R5 仅批准设计/图合同；代码审阅、prereg 核验、正式 run、结果复核逐门；不得跳门或把设计批准写成已运行 | M0R5 APPROVE_FOR_S2_CODE_AMENDED（对象 89fd8d9）；M0R4 CHANGES_REQUESTED 为历史；代码/prereg/run/结果门未发生 | ACTIVE_BOUNDARY |
| X-07 | 所有权：A1 代码、A6 分析/图、A4 文档矩阵/回执、A5 独立审阅、A2 授权后运行、A3 卫生/证据保护、Lead 冻结/授权/唯一 GitHub 发布 | 本矩阵由 A4 写；A4 无代码/运行/GitHub 写权 | ACTIVE_BOUNDARY |
| X-08 | Issue #7 §4 的 feasible_hit_rate/first_feasible_eval/best_feasible_value 等约束优化指标在 S2 标量代理下不适用；必须标 NOT_APPLICABLE_S2_SURROGATE_SCOPE，不得伪装为已验证 | 计划 §8 L137-139；R-S2-02/07；A5 M05 ACCEPTED_SCOPE_REDUCTION | SCOPE_REDUCTION（需在报告显式标注） |
| X-09 | Issue #4 为独立 VSPAERO/气动验证轨道；S2 不改变 Issue #4 六门禁；S2 的 0 物理结果不得当作 VSPAERO 验证或真实阻力证据 | Issue #4 与 S2 分轨；S2 无 VSPAERO 调用 | SEPARATE_BOUNDARY |
| X-10 | S2 结果不得直接作为 S3 放行或阶段验收；须 A5 结果复核、A3 审计、Lead 签发；S3 另行授权 | 当前无 S2 结果；S2_RUN 未批准 | ACTIVE_BOUNDARY |
| X-11 | 文档优先级：R-S2-01 只解释设计动机与边界，不再是计划覆盖层；冲突时以最新 A5 APPROVE 计划为准 | R-S2-01A 已更新（raw sha 7d6f9739…；LF canonical 49ffa9c5…；A5 M0R5 文本 4b2a7901… 为审阅时旧版本）；R-S2-01 文末已加版本优先；当前权威为 v1.5/89fd8d9（M0R5 APPROVE_FOR_S2_CODE_AMENDED） | RESOLVED_BY_RS201A（v1.5 §14/C-02） |

## 4. 合同一致性核对（计划 v1.5 × R-S2-01/R-S2-01A × 统计口径）

| 核对项 | 计划 v1.5 依据 | R-S2-01/R-S2-01A/合同/统计口径 | 结论 | 关联 finding |
|---|---|---|---|---|
| 证据范围/数据身份 | §2、头部；S0-7 60/20/20/10/10 | R-S2-01 证据范围 DEV_VALIDATION_ONLY；R-S2-05 数据边界 | PASS | 无 |
| 主/次要端点 | §1 L17-18：K5 主、K10 次；K0/K1/标准化/MAE 描述性 | R-S2-02：K5/K10+Holm2；A5 B01/B02 | PASS | 无 |
| 多重校正 | §6：唯一族 family_size=2 | R-S2-02；A5 M07；A5 M0R2 确认 | PASS | 无 |
| K=0/K=1 | §1、§3、§4.2：K=0/1 描述性；K=0 仅同 theta 梯度等价 | R-S2-03 完全一致 | PASS | 无 |
| FD 口径 | §4.3：full、eps=1e-6*max(1,|θ|)、top-32、阈值 1e-6、pilot micro/full | R-S2-04 完全一致；A5 M01 已闭合设计 | PASS_DESIGN / PILOT_NOT_RUN | 无 |
| 数据边界 | §2：SHA256SUMS 9/9、只 meta_train/validation、3 负控、holdout_rows_used=0 | R-S2-05 一致；A5 M02 已闭合 | PASS_DESIGN | 无 |
| 训练确定性 | §3：derive_seed/scope、两进程逐字节一致、manifest sha 入 run_config | R-S2-06 一致；A5 M04 已闭合 | PASS_DESIGN | 无 |
| 两臂公平/等预算 | §4.4、§7：除 first_order 外同配置；build+verify 断言 | A5 B04/M0R2；Issue #7 §2 同网络/任务/K-shot/seed/预算 | PASS_DESIGN | 无 |
| 指标 scope | §8：S2 标量代理不适用 feasible/首次可行/最优可行 | R-S2-07；A5 M05 ACCEPTED_SCOPE_REDUCTION | PASS_WITH_SCOPE_REDUCTION | 报告须标 NOT_APPLICABLE |
| 所有权 | §10：A1/A6/A4/A5/A2/A3/Lead | R-S2-08 一致 | PASS | 无 |
| 放行链 | §11 L203-210：M0/M0R/M0R2/M0R3→M0R4→M0R5→A1/A6/A4→A5 code→Lead prereg freeze+commit→A5 prereg verify→Lead 授权→A2 run→A5 result→A3→回执→S3 | R-S2-09 一致；v1.5 补 M0R3/M0R4/M0R5；A5 对象 89fd8d9，M0R5 APPROVE_FOR_S2_CODE_AMENDED；v1.3/969c0e7 为历史批准对象 | PASS_M0R5_APPROVED | A4-S2C-02、A4-S2C-06、A4-S2C-07（均 CLOSED） |
| 失败/停止规则 | §5、§7 L124-126/L136、§9 L188-191、§12 L226-227：单 seed >20 min 或 >8GB 记 RESOURCE_LIMIT 并停止整个正式 run；总硬截止 2h；prereg.resource_limits 1200/8192/7200 机械校验 | R-S2-10 一致；F-03 已写入 | PASS_C01_F03_CLOSED | A4-S2C-01 CLOSED；A5-M0R4-F-03 CLOSED（M0R5） |
| prereg 合同 | §7 L99-137：canonical、id/digest 解耦、code_sha 字典序、analysis_plan_digest、占位拒绝、pilot path、双 family、resource_limits；L136 固定值校验 | A5 B03/B03R 已闭合；F-03 已闭合；R-S2-09 引核验门 | PASS_SCHEMA / NOT_CREATED | A4-S2C-04 CLOSED；A5-M0R4-F-03 CLOSED（M0R5） |
| Issue #7 §4 图表/交付包 | §8.1 L144-184 定义 9 个 S2 诊断图键（fig1..fig9）、数据源、中文标题/轴、缺失 NOT_RUN、evidence_scope 与 CSV 支撑；§8.1.1 L160-172 逐类映射 Issue 七类；§12 L225 纳入验收 | Issue #7 §4 要求 7 类中文图、CSV/figures/run_config；9 键 ≠ 七类 | PASS_CONTRACT / FIGURES_NOT_RUN | A4-S2C-03 CLOSED；A5-M0R4-F-01/F-05 CLOSED（M0R5） |
| Issue #7 §4 七类映射（A5-M0R4-F-01） | §8.1.1 L160-172：①→fig1/fig4；②→fig2/fig3/fig6；③ NOT_APPLICABLE_S2_SURROGATE_SCOPE（代理仅拟合标量目标，无约束函数/可行域）；④ NOT_APPLICABLE_S2_NO_OPTIMIZATION_ARM（无 BO/DE 优化臂与预算分配）；⑤→fig8；⑥→fig9（任务族；约束诊断 NOT_APPLICABLE_S2_SURROGATE_SCOPE；OOD NOT_APPLICABLE_S2_NO_OOD_SPLIT）；⑦ NOT_APPLICABLE_S2_ZERO_PHYSICS_NO_VSPAERO（physical=0，不调用 VSPAERO） | Issue #7 §4；计划 §8.1.1 L166-172 | PASS_CONTRACT / FIGURES_NOT_RUN；9 图键不等于 Issue 七类 | A5-M0R4-F-01 CLOSED（M0R5 确认）；A4-S2C-03 CLOSED |
| Issue #7 §4 通用 feasible 端点 | §8 已 scope-reduce | R-S2-02/07；A5 M05 | PASS_BY_RULING（须显式标注） | 无（但报告不得省略说明） |
| A5 批准对象/HEAD | A5 M0R5 对象 89fd8d9（v1.5）；当前 HEAD=89fd8d9；M0R3 对象 969c0e7（v1.3）为历史 | 计划 §7/§11；A5 M0R5 已批准 v1.5 为代码与图合同基线；代码审阅未开始 | PASS_M0R5_APPROVED / CODE_REVIEW_NOT_STARTED | A4-S2C-07 CLOSED（v1.5 §11 第 3 步） |
| R-S2-01 版本优先级 | 当前权威 v1.5/89fd8d9（M0R5 approved）；历史批准基线 v1.3/969c0e7；v1.4/0c85aee 为 M0R4 CHANGES_REQUESTED | R-S2-01A：最新 A5 APPROVE 计划 > 旧计划 > R-S2-01；R-S2-01 仅为设计理由 | PASS_C02_CLOSED | A4-S2C-02 CLOSED（v1.5 §14/R-S2-01A） |

## 5. A5 findings 映射与处置

- 证据文件均位于 `<EXT>/p4-route-a/a5/`；报告完整哈希见 §8。A5 当前状态：M0R5 APPROVE_FOR_S2_CODE_AMENDED（0B/0M/1 非阻断 minor，对象 89fd8d9）；M0R4 对 v1.4/0c85aee 判 CHANGES_REQUESTED（0B/2M/3m，F-01..F-05）为历史，v1.5 已逐项关闭。

| A5 ID | 轮次/对象 | 摘要 | 当前处置 | 证据 |
|---|---|---|---|---|
| S2M0-B01 | M0 / b0acdf2 v1.0 | K=0/1 评估合同不可执行；等价性语义混用 | CLOSED（M0R 确认拆分；R-S2-03） | S2_M0_design_review.md；S2_M0R_review.md |
| S2M0-B02 | M0 / v1.0 | 主终点/Holm 矛盾 | CLOSED（M0R；M07 最终闭合） | S2_M0_design_review.md；S2_M0R2_review.md |
| S2M0-B03 | M0 / v1.0 | 缺 prereg schema | CLOSED（v1.1 补 schema；B03R 继续细化） | S2_M0R_review.md；S2_M0R3_review.md |
| S2M0R-B04 | M0R / e584568 v1.1 | prereg arms hidden_sizes 不一致（FOMAML 64×64） | CLOSED（v1.2 两臂 hidden(16,16)+断言；M0R2 功能 PASS） | S2_M0R_review.md；S2_M0R2_review.md |
| S2M0R-B03R | M0R / v1.1 | prereg_id/digest 循环、code_sha/analysis_plan_digest 不可机械核验 | CLOSED（v1.2 解耦+算法；M0R2 部分→M0R3 全闭） | S2_M0R2_review.md；S2_M0R3_review.md |
| S2M0-M01 | M0 / v1.0 | FD 口径不清 | CLOSED（设计；pilot 待执行） | S2_M0R_review.md；计划 §4.3 |
| S2M0-M02 | M0 / v1.0 | 数据边界无 fail-closed | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-M03 | M0 / v1.0 | 无独立测试集/validation-only | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-M04 | M0 / v1.0 | episode 确定性 | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-M05 | M0 / v1.0 | 指标 scope | ACCEPTED_SCOPE_REDUCTION（feasible 不适用 S2，标 NOT_APPLICABLE） | S2_M0R_review.md；计划 §8 |
| S2M0-M06 | M0 / v1.0 | 所有权 | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-M07 | M0R / v1.1 | family_key=endpoint 与 2 检验 Holm 矛盾 | CLOSED（v1.2 唯一 2-test 族；M0R2 PASS） | S2_M0R2_review.md |
| S2M0-N01 | M0 / v1.0 | 行数 4,800 vs 3,720 | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-N02 | M0 / v1.0 | API 字面量 | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-N03 | M0 / v1.0 | base 1a2b242 | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-N04 | M0 / v1.0 | 失败规则 | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-N05 | M0 / v1.0 | FD 进 run_config | CLOSED（M0R） | S2_M0R_review.md |
| S2M0-N06 | M0 / v1.0 | prereg 核验门 | CLOSED（M0R） | S2_M0R_review.md |
| S2M0R2-M01 | M0R2 / eac34dd v1.2 | code_sha 清单与字典序矛盾（s2_runner.py 在 s2_prereg.py 前） | CLOSED（v1.3 修正；M0R3 确认） | S2_M0R2_review.md；S2_M0R3_review.md |
| S2M0R2-N01 | M0R2 / v1.2 | §4.4 未同步 seed/backend/build-verify | CLOSED（v1.3；M0R3） | S2_M0R2_review.md；S2_M0R3_review.md |
| S2M0R2-N02 | M0R2 / v1.2 | pilot_artifacts.path 根目录未定义 | CLOSED（v1.3；M0R3） | S2_M0R2_review.md；S2_M0R3_review.md |
| S2M0R3-N01 | M0R3 / 969c0e7 v1.3 | §7:125 code_sha 示例顺序仍旧 | CLOSED（v1.3a 修正；v1.4 §13 记录；M0R4 复审） | S2_M0R3_review.md；计划 §7/§13 |
| S2M0R3-N02 | M0R3 / 969c0e7 v1.3 | §11:160/§13:184 版本标签旧；§13 无 M0R3 行 | CLOSED（v1.4 §11/§13 更新；M0R4 复审） | S2_M0R3_review.md；计划 §11/§13；A4-S2C-06 |
| S2M0R3 结论 | M0R3 / 969c0e7 | A5 设计批准（历史对象） | APPROVE_FOR_S2_CODE（0B/0M/2m）；v1.4 经 M0R4 CHANGES_REQUESTED；v1.5 经 M0R5 APPROVE_FOR_S2_CODE_AMENDED | S2_M0R3_review.md；计划 §11 |
| S2M0R4 | M0R4 / 0c85aee v1.4 | C-01..C-07 限定 diff 复审 | CHANGES_REQUESTED（0B/2M/3m；F-01..F-05）；v1.5 已逐项关闭，M0R5 APPROVE | S2_M0R4_review.md（12,610 B、sha 57ae3556…）；计划 §13/§15 |
| S2M0R5 | M0R5 / 89fd8d9 v1.5 | v1.4→v1.5 限定 diff 复审（仅计划文件 +67/−22） | APPROVE_FOR_S2_CODE_AMENDED（0B/0M/1 非阻断 minor A5-S2M0R5-01：S0-7 全 120 task 单 family、fig9 panel b 仅族内分布、A6 图注须注明不声称族间差异） | S2_M0R5_review.md（8,178 B、sha b1465858…）；计划 §11 |

## 6. A4 合同一致性 findings 与处置（计划 v1.5）

计划 v1.5（commit 89fd8d9，sha f156b250…）已逐项响应并关闭 A4-S2C-01..07 与 A5-M0R4-F-01..F-05；A5 M0R5 已 APPROVE_FOR_S2_CODE_AMENDED（0B/0M/1 非阻断 minor）。CLOSED 指文档/合同层已处置，不等于 S2 代码已审阅、prereg 已冻结或 S2_RUN 已放行。

| ID | 级别 | 处置 | 计划位置/证据 | 状态 |
|---|---|---|---|---|
| A4-S2C-01 | major | CLOSED：单 (arm, meta_seed) >20 min 或峰值 >8 GB 记 RESOURCE_LIMIT 并停止整个正式 run；总硬截止 2 h；prereg 增 resource_limits={1200,8192,7200} 并机械校验 | §5、§7 L124-126/L136、§9 L188-191、§12 L226-227 | CLOSED（M0R5 确认） |
| A4-S2C-02 | major | CLOSED：R-S2-01A 版本优先规则（最新 A5 APPROVE 计划 > 旧计划 > R-S2-01）；R-S2-01 文末优先级已更新 | <EXT>/p4-route-a/lead/R-S2-01A_version_precedence.md（1,879 B、raw sha 7d6f9739…；A5 M0R5 文本 4b2a7901… 为审阅时旧版本）；R-S2-01（3,792 B、raw sha 32cd75f4…）；§14 | CLOSED（M0R5 确认） |
| A4-S2C-03 | gap | CLOSED：§8.1 定义 fig1..fig9 共 9 个诊断图键，§8.1.1 增 Issue #7 §4 七类逐类映射；③/④/⑦ 显式 NOT_APPLICABLE | §8.1 L144-184、§8.1.1 L160-172、§12 L225 | CLOSED（F-01） |
| A4-S2C-04 | minor | CLOSED：frozen_package 拆 package_family_version=p4ra-family-v4 与 task_family_version=p4ra-family-v3 | §7 L113-114 | CLOSED（M0R5 确认） |
| A4-S2C-05 | minor | CLOSED：EXT 旧 v1.2 变更说明顶部标 SUPERSEDED；code_sha 顺序以计划 §7 sorted() 为准 | <EXT>/p4-route-a/lead/S2_plan_v1_2_change_note.md；§13 L262 | CLOSED（F-04） |
| A4-S2C-06 | minor | CLOSED：§11 增 M0R3/M0R4/M0R5，§13 增 M0R3/M0R4 行并更新版本标注 | §11 L203-210、§13 L232-265 | CLOSED（M0R5 确认） |
| A4-S2C-07 | minor | CLOSED：A5 代码审阅首步确认 969c0e7..v1.5 仅计划文件 diff 且 v1.4/v1.5 未回退修复 | §11 L207；M0R5 实测 diff 仅 1 文件 | CLOSED（M0R5 确认） |

### 6.1 A5-M0R4-F-01..F-05 闭合证据（v1.5，M0R5 确认）

| ID | 级别 | v1.5 处置 | 证据位置 | 状态 |
|---|---|---|---|---|
| A5-M0R4-F-01 | major | CLOSED：§8.1 增 Issue #7 §4 七类映射表；新增 fig8_performance_cost（⑤）与 fig9_task_family_diagnostics（⑥）；③/④/⑦ 显式 NOT_APPLICABLE 及理由；明确 9 个 S2 诊断键不等于 Issue 七类 | 计划 §8.1 L144-184、§8.1.1 L160-172、§12 L225；A5 M0R5 §2 | CLOSED |
| A5-M0R4-F-02 | major | CLOSED：R-S2-01A 与 R-S2-01 更正为“v1.3a 未单独获批；M0R4 前批准对象为 v1.3/969c0e7；v1.5 经 M0R5 通过后才成基线” | 计划头部 L3、§11 L205、§13 L260；EXT R-S2-01A/R-S2-01；A5 M0R5 §2 | CLOSED |
| A5-M0R4-F-03 | minor | CLOSED：§7 prereg 增 resource_limits（per_seed_train_wall_s=1200、peak_memory_mb=8192、total_wall_s=7200）及 failure/stopping rule；verify 固定值校验，失败码 S2_PREREG_RESOURCE_LIMITS_INVALID | 计划 §7 L124-126/L136、§12 L227；A5 M0R5 §2 | CLOSED |
| A5-M0R4-F-04 | minor | CLOSED：EXT 旧 v1.2 变更说明顶部加 SUPERSEDED 标注；code_sha 顺序以计划 §7 sorted() 为准 | <EXT>/p4-route-a/lead/S2_plan_v1_2_change_note.md；A5 M0R5 §2 | CLOSED |
| A5-M0R4-F-05 | minor | CLOSED：§8.1.2 明确 fig3 task 级 bootstrap（20 task、10,000 次、seed=20261105、2.5/97.5 分位）与 fig2/fig3/fig6 的 aggregate 字段 | 计划 §8.1.2 L174-181、§12 L225；A5 M0R5 §2 | CLOSED |

- C-01..C-07、F-01..F-05 均不再作为开放 blocker；v1.5/89fd8d9 已于 M0R5 获 APPROVE_FOR_S2_CODE_AMENDED，但代码审阅、prereg 冻结/核验、S2_RUN 授权均未发生。

## 7. 交付与下一步

- 本矩阵 v1.2a 为 A4 对 S2 设计阶段（计划 v1.5/89fd8d9、A5 M0R5 批准后）的需求—证据快照；不提交、不推送，待 Lead 决定是否纳入正式交付。保留 v1.1 历史：v1.1 曾按 v1.4/0c85aee + M0R4 PENDING 记录，已被本版取代。
- 当前基线为 v1.5/89fd8d9（M0R5 APPROVE_FOR_S2_CODE_AMENDED）；历史批准对象 v1.3/969c0e7；v1.4/0c85aee 为 M0R4 CHANGES_REQUESTED。设计/图合同已批准不等于 S2 代码已审阅、prereg 已冻结或 S2_RUN 已授权。
- 仍不可放行 S2_RUN、不可启动正式 run、不可把 S2 写成已完成；A1/A6 未提交/未跟踪代码与测试未审阅、未运行。
- 后续门禁：A1/A6 实现与测试→A5 代码审阅（APPROVE_FOR_S2_FORMAL）→Lead prereg 冻结+commit→A5 prereg 核验→Lead 书面授权→A2 正式 run（6,000 行、physical=0）→A5 结果复核→A3 审计→Lead 发布 Issue #7 S2 回执→S3 另行授权。A4 不代写 A5/A1/A6 状态。

## 8. 证据清单（哈希）

| 证据 | 路径 | 大小/行数 | sha256 |
|---|---|---|---|
| S2 计划 v1.5 | docs/planning/p4_route_a_s2_execution_plan_20261106.md | 39,246 B / 290 行 | f156b250df40395dc3a3bce5957a1ebe3156025d68f4e798d31ea04be6aded6f |
| A5 S2-M0 | <EXT>/p4-route-a/a5/S2_M0_design_review.md | 26,629 B | f372fb5eb02b2d44fdd84592c1c776dbcf240ac03dd67da255eaf6c164e09d5b |
| A5 S2-M0R | <EXT>/p4-route-a/a5/S2_M0R_review.md | 15,934 B | fa8b7f95c064730a0063416e3176406fe8c5547685823bc9fcc9305a06d90278 |
| A5 S2-M0R2 | <EXT>/p4-route-a/a5/S2_M0R2_review.md | 9,893 B | d65be96eb037ab0865614580db9d19ee114d95b8ab86eec9b0033a69e89a155e |
| A5 S2-M0R3 | <EXT>/p4-route-a/a5/S2_M0R3_review.md | 5,620 B | df997633810f43eca5181f2db6b8554a50cde17a9f015d05143b8e21a6541a9e |
| A5 S2-M0R4 | <EXT>/p4-route-a/a5/S2_M0R4_review.md | 12,610 B / 83 行 | 57ae355614845ad31eb4f797e347ff7af287ede5dc3c048efa7a6810c599ff40 |
| A5 S2-M0R5 | <EXT>/p4-route-a/a5/S2_M0R5_review.md | 8,178 B / 64 行 | b14658587c2e95fff91882b6db6161fe05264d631f8913643ae57a2b33384522 |
| R-S2-01 | <EXT>/p4-route-a/lead/R-S2-01_design_rulings.md | 3,792 B / 24 行 | raw 32cd75f48b8805c5fa2888d56be91a7927b080015b9c619a60b66e222b10dd03（LF canonical c1098c4e…） |
| R-S2-01A | <EXT>/p4-route-a/lead/R-S2-01A_version_precedence.md | 1,879 B / 19 行 | raw 7d6f9739f0e62e96981e40156f3abf430daea2fcdc9bda1d2c0813eae104b9c5（LF canonical 49ffa9c5…；A5 M0R5 文本引用其审阅时旧版本 4b2a7901…，已由 M0R5 后 Lead 追加记录取代） |
| v1.2 变更说明 | <EXT>/p4-route-a/lead/S2_plan_v1_2_change_note.md | 2,506 B / 20 行 | raw bc05174802a165b3eaa45dbdb1aa82bf0862e53304ff7ff2eda243ffe7357d01（顶部 SUPERSEDED） |
| S0-7 SHA256SUMS | research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z/SHA256SUMS.txt | 784 B | 59aa81cdc1f1abdc66966822eb24b567904ba4c62924ab041ae09bd9badf41f2 |
| S0-7 freeze_summary | 同目录 freeze_summary.json | 7,217 B | ea1d7931dfd7b172486a19f148dc1a4fa82e6640f00dca1c026cc64e8be98086 |

## 9. 边界声明

- 本文只读核对，不修改仓库代码/计划/冻结包/旧 run；A4 未 commit、未 push、未写 GitHub。
- physical_call_count=0；无 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag/DOE 调用。
- 本文是正式可审阅文档，不含会话记忆、草稿口吻或机器绝对路径；不替代 A5 verdict、不替代 Lead 签发。
- 所有状态以 2026-11-06T14:08Z 读取时点为准；A1/A6 在 22:07Z 前写入的未提交/未跟踪代码与证据已并入 S2-01/02/03/04/12 与 §1 代码行；后续变更须由 Lead/A5/A1 更新，A4 不代写代码状态。
