# P4 路线A S2 需求矩阵（v1.4）

- 文档性质：Issue #7 S2 的只读需求—证据—状态核对表，供 Lead/A5/A1/A6/A3 使用；不是阶段验收结论，不替代 A5 verdict，不构成 S3 授权或真实飞机/真实气动结论。
- 仓库状态：docs/reviews/p4_route_a_s2_requirement_matrix.md 已由 Lead 提交（docs-only commit d78dc97，父 12940c5）；本 v1.4 为 Lead 在 A4 v1.3 基础上更新回执发布状态，A4 原文仍为 EXT 副本。
- 位置：分支 research/p4-route-a-s2；证据包 rev3=12940c5；当前 HEAD=origin=d78dc97（docs-only 3 文件）；main=origin/main=ec65e5a9a723bc52df8075a395fcaf9e0fd0fc2b；base=1a2b242；S2 专用 worktree（路径用 <repo>/<EXT> 占位）。
- 依据：Issue #7 正文 §2 S2 与 §4；S2 执行计划 v1.5（commit 89fd8d9，39,246 B/290 行，sha256 f156b250…）为 M0R5 批准基线；v1.6（983e6b8，44,689 B/ec3c2823…）与 v1.6a（5a32665，46,118 B/2a046260…）为 A5 代码审阅整改计划版本；A5 S2-M0..M0R5、代码审阅/delta、prereg 核验、结果复核、证据包 rev3 复核；A3 rev3 隔离审计；S0-7 冻结包；S1 收尾矩阵。
- 读取时点：2026-11-07 03:30 +08（2026-11-06T19:30Z）。
- 变更：v1.4（2026-11-07T03:55+08）：Issue #7 S2 回执已由 Lead 发布（commentId 6693991661）；仓库 docs 归档 commit d78dc97（矩阵 v1.3 + A5 包 rev3 复核 + A3 rev3 报告）；S2 回执 PENDING→PUBLISHED；阶段验收仍 NOT_ISSUED、S3=NOT_APPROVED。
- 变更：v1.3（2026-11-07T03:30+08）：S2 由设计/待运行更新为「执行 + 结果复核 COMPLETED」；写入 6,000 条正式 run、A5 结果复核/证据包 rev3、A3 rev3、主/次端点 HARM 结果、9 图与七类映射；S2 阶段验收仍为 NOT_ISSUED，S3=NOT_APPROVED；仓库写入待 Lead。
- 变更：v1.2a（2026-11-06T22:15+08）：修正 R-S2-01A 引用沿革（raw 7d6f9739…；LF canonical 49ffa9c5…；A5 M0R5 文本 4b2a7901… 为审阅时旧版本）；v1.2a 的完整 S2-01..S2-12、X-01..X-11、A5 26 行 findings 历史仍保留在仓库版本与本文件 §5/§6 摘要中。
- 状态口径：COMPLETED 表示该需求已由正式 run/证据满足并经独立复核，不等于阶段验收；COMPLETED_REVIEWED 表示结果/包已复核但阶段验收未签发；FROZEN_VERIFIED 表示 prereg 已冻结并核验；PASS_WITH_WARNINGS 表示 A3 全项 PASS、warnings 为 info；NOT_ISSUED/NOT_APPROVED 表示未签发/未授权；ACTIVE_BOUNDARY 表示现行硬边界；SEPARATE_BOUNDARY 表示独立轨道。
- A4 边界：本文件只读核对与文档汇总；未改代码/计划/冻结包/旧 run；未 commit/push；未写 GitHub；physical_call_count=0；无新物理求解。

## 1. 当前状态与硬边界

| 项目 | 当前事实 | 证据 | 状态 |
|---|---|---|---|
| S2 总体 | 正式 run 6,000 条已执行；A5 结果复核/证据包 rev3 已 APPROVE；A3 rev3 PASS_WITH_WARNINGS；S2 回执已发布（commentId 6693991661）；阶段验收未签发 | 本文件 §7；A5 result/package verdict；A3 rev3；Issue #7 评论 | 执行+结果复核 COMPLETED；阶段验收 NOT_ISSUED；回执 PUBLISHED |
| S2 设计门 | A5 S2-M0R5 APPROVE_FOR_S2_CODE_AMENDED（0B/0M/1 非阻断 minor），对象 89fd8d9（计划 v1.5，39,246 B/290 行、sha f156b250…）；M0R4 对 v1.4 的 CHANGES_REQUESTED 已由 v1.5 关闭 | <EXT>/p4-route-a/a5/S2_M0R5_review.md（8,178 B/sha b1465858…）；计划 v1.5 | APPROVED（历史设计门） |
| S2 代码 | commit 3d576bd（12 files，+10,828）→ 修复 983e6b8/5a32665/f4ab43f；A5 初始代码审阅 CHANGES_REQUESTED 2B/2M/5m（对象 3d576bd），delta 审阅 APPROVE_FOR_S2_FORMAL 0B/0M/3m（对象 f4ab43f；8 files +2,560/−356；1,174 tests OK/1 skipped；8 e2e OK） | <EXT>/p4-route-a/a5/S2_code_review.md；S2_delta_verdict.json（1,764 B/sha 18467e0b…）；<repo>/git log | COMPLETED |
| S2 prereg | 文件 4,916 B、raw sha fde3ef33…；prereg_id p4ra-s2-prereg-2751c162904d5a4f；prereg_digest c767f206…；code_sha 3e6ece85…；训练 bank sha 6954b053…；冻结 commit 994cda8；A5 核验 APPROVE_FOR_S2_RUN（104 checks/0 fail；8/8 负控；21 gates PASS） | <repo>/research/concorde_metaopt/evidence/s2/s2_preregistration.json；<EXT>/p4-route-a/a5/S2_prereg_verification/verdict.json（3,322 B/sha 282984a0…） | FROZEN_VERIFIED |
| S2 正式 run | run_id s2-formal-20261106T1810Z；FORMAL/COMPLETED；6,000 条=1,200 train+4,800 eval；0 FAILED；0 RESOURCE_LIMIT；0 重试；base wall 25.6769 s；wrapper 101.57 s；峰值 261.57 MB；授权 S2-FORMAL-AUTH-20261106T1805Z | <repo>/research/concorde_metaopt/evidence/s2/formal_run/（run_config/run_summary/run_records/data_manifest/fd_gate）；A2 报告 | COMPLETED |
| S2 结果 | k5 primary：median diff +0.03132444、relative −3.394%、Wilcoxon exact p=3.814697265625e-06、95%CI [0.04110944,0.05986981]、19/20 FULL 更差、SUPPORTED_HARM；k10 secondary：median diff +0.01450084、relative −1.619%、p_adj=3.814697265625e-06、CI [0.00732395,0.01170188]、20/20 更差、SUPPORTED_HARM；overall=SUPPORTED_HARM | <repo>/.../analysis/aggregate.json；s2_endpoint_tables.csv；s2_holm_family.csv；A2 报告 | COMPLETED_REVIEWED |
| S2 证据包 | rev1 27c935e→rev2 625d4b9→rev3 12940c5；38/38 payload canonical LF；36 payload 与 27c935e 全同；7 CRLF/31 LF；sanitized 5 true/33 false；A5 package rev3 APPROVE_FOR_S2_RECEIPT_PACKAGE 0B/0M/2m；A3 rev3 PASS_WITH_WARNINGS C01–C27 PASS/0 FAIL、W01–W04 info | A5 package rev3 verdict（1,456 B/sha 700b80e0…）；A3 S2_package_isolation_12940c5.md（16,471 B/sha 7df8d496…） | COMPLETED_REVIEWED |
| A3 隔离审计 | 单父链 12940c5←625d4b9←27c935e；delta 恰 3 files +272/−99；36 payload blob 与 27c935e 全同；sums 38/38 canonical LF；旧件 0 改；0 solver；全包绝对路径 0；worktree clean；主库/main/PR#3/#6 未动 | <EXT>/EXT/p4-route-a/a3/S2_package_isolation_12940c5.md；_facts 37,366 B/sha ca5bfcd5…；SHA256SUMS.txt 204 B/sha 5d593032… | PASS_WITH_WARNINGS |
| 物理调用 | physical_call_count=0；无 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag/批量 DOE；6,000 条均为合成解析评价记录 | run_config；A5 result verdict；A3 rev3 | 0（ACTIVE_BOUNDARY） |
| S1 基线 | S1_RUN=EXECUTED_AND_RESULT_REVIEWED；Issue #7 回执 commentId 6684142041；S1 签发不含 S2 授权 | Issue #7 评论；<EXT>/p4-route-a/lead/S1_RUN_RESULT_ACCEPTANCE_20261106.md | CLOSED_HISTORICAL |
| S0-7 数据基线 | SHA256SUMS sha 59aa81cd…；code_sha 7304d32e…；git_sha 004156c…；counts 60/20/20/10/10；holdout_seed 20261106；family_fingerprint a1f9462c…；split_hash cd597d01…；confirmatory_eligible=true；physical=0 | <repo>/research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z/ | FROZEN_READ_ONLY |
| 文档/证据链 | 计划 v1.5/89fd8d9（39,246 B/f156b250…）为执行基线；当前计划文件 46,118 B/2a046260…为 A5 delta 审阅对象；A5 六阶段门与结果/包复核已完成；A3 rev3 完成；A2 报告 repo-ready 31,771 B/f97b8eb5…、外部版 31,971 B/48e0a274… | 本文件 §5/§10；A5/A2/A3 文件 | COMPLETED（阶段验收除外） |
| Issue #4 | 独立 VSPAERO/气动验证轨道；S2 不调用任何气动求解器、不修改 Issue #4 六门禁；S2 的 0 物理结果不得当作 VSPAERO 验证或真实阻力证据 | Issue #4；D-12D-006；本文件 §11 | SEPARATE_BOUNDARY |
| Issue #5 / PR #6 | 历史基线；S2 不复用/不覆盖其运行与结果；不合并 main | Issue #7 §1；计划头部 | CLOSED_HISTORICAL |
| PR #3 / main | PR #3/#6 保持 open；main=origin/main=ec65e5a，未合并；S2 分支 research/p4-route-a-s2，HEAD=origin=d78dc97（证据包 rev3=12940c5）；未新开 PR | <repo>/git log；PR 元数据 | OPEN_NOT_MERGED / ACTIVE_BOUNDARY |
| S2 阶段验收 | NOT_ISSUED；A5 结果复核仅 APPROVE_FOR_S2_RECEIPT（回执级），不是阶段验收；S2 阶段验收/S3 放行由 Lead/负责人另行签发 | A5 result verdict；本文件 §9 | NOT_ISSUED |
| S3 | NOT_APPROVED；需负责人书面授权 + 新 prereg；不得以 S2 结果自动放行 | Issue #7 §2/§4；A5 result verdict 边界 | NOT_APPROVED |
| A4 输出 | 本矩阵 v1.3（EXT 替代文本；Lead 已提交 d78dc97 并更新为 v1.4）；Issue #7 S2 回执草稿→Lead 发布（commentId 6693991661）；task263 交付报告 | <EXT>/p4-route-a/a4/ | PUBLISHED_BY_LEAD（回执）；矩阵 v1.4 待 A3 docs 审计 |

## 2. S2 需求矩阵（S2-01 至 S2-12）

| ID | 需求与来源 | 验收标准（可复核） | 当前状态 | 责任/证据 | A5 findings 映射 |
|---|---|---|---|---|---|
| S2-01 | 新增独立 FULL_MAML 模式，保留旧 FOMAML 路径/API/原有数字；不得以 FOMAML 冒充二阶 | maml.py 有独立 FULL_MAML 分支；旧 API/旧测试不改；旧 FOMAML 数字可复现；代码审阅确认未改旧路径 | COMPLETED | A1；计划 §4.1；3d576bd→983e6b8/5a32665/f4ab43f；A5 delta APPROVE；1,174 tests OK/1 skipped | 历史设计 findings CLOSED（v1.2a §5）；A5 delta 未列 blocker |
| S2-02 | 函数式可微内循环：create_graph=True；内循环不得用 .data/detach 切断二阶；元梯度需回到原始 θ | 单测证明二阶梯度存在且非零；旧 FOMAML 路径不受影响；代码审计无内循环断图 | COMPLETED | A1；计划 §4.1；A5 delta APPROVE；FD 32/32 PASS（max_rel 1.144759989428372e-09，阈值 1e-6） | 历史设计 findings CLOSED；执行层 FD gate PASS |
| S2-03 | 全元目标有限差分：扰动原始 θ±ε，每次完整重跑内循环；旧 FD 只查适应后参数不能代替；eps=1e-6*max(1,abs(θ))，top-32，阈值 1e-6 fail-closed；先 micro/full pilot | pilot 记录在 run_config；analytic 与 FD 相对误差 <=1e-6；micro hidden(8,8)/1 步/32 坐标与 full hidden(16,16)/2 步/8 坐标均通过；失败即停 | COMPLETED | A1；计划 §4.3；fd_gate.json 8,795 B/sha 7950bcb0…；32/32 PASS；micro max 1.278e-9/full 3.975e-10 | 历史设计 findings CLOSED；FD gate PASS |
| S2-04 | K=0 同 θ 梯度等价门禁：同 theta、inner_steps=0，FULL 与 FOMAML 梯度差 <=1e-12；仅证明梯度等价，不证明训练后模型等价 | 单测在固定 seed 下通过；报告明确 K=0 仅门禁，不作为算法等价性/效果比较；K=0/1 描述性 | COMPLETED | A1；计划 §4.2；1,174 tests OK/1 skipped；A5 delta APPROVE；K=0/1 未进入端点 | 历史设计 findings CLOSED；K0/K1 仅描述性（NC-11/null disclosure） |
| S2-05 | 等预算、两臂公平：FULL 与 FOMAML 除 first_order 外全部同配置；outer_steps200、meta_seed{0,1,2}；build+verify 双重断言 S2_ARM_CONFIG_MISMATCH | run_config 两臂配置 diff 仅 first_order；build 与 verify 均校验；C1 同任务/种子/预算/候选；不得出现克隆臂/免费先验 | COMPLETED | A1/A5；计划 §4.4；NC-05 fairness PASS（run_arms=PASS；arms_equal=True）；A5 result verdict | 历史设计 findings CLOSED；NC-05 PASS |
| S2-06 | 训练 episode bank 确定性：derive_seed 按 scope 派生；训练 support16/query32、batch 8 任务；两个进程逐字节一致；manifest sha 写入 run_config | 两次构建 bank 的 manifest 逐字节一致；评估 support K/query64、draw 0..9、K∈{0,1,5,10}；种子/顺序可复现；异常 fail-closed | COMPLETED | A1；计划 §3；run_config 3/3、run_records core 3/3 c9460dae…；data_manifest/bank/fd_gate sha 3 次一致 | 历史设计 findings CLOSED；run 层 determinism PASS |
| S2-07 | 数据边界 fail-closed：load_s2_tasks 校验 SHA256SUMS 9/9；只允许 meta_train(60)/meta_validation(20)；3 项负控；run_config 记录 holdout 身份且 holdout_rows_used=0；不使用 S1 holdout | 负控（篡改/缺失/非法 split）均失败；run_config 中 holdout 身份可核；无 S1 holdout 行；越界即停 | COMPLETED | A1/A5；计划 §2；A5 result：shasums 60/60、holdout 0、data boundary PASS；NC-02/NC-03 PASS | 历史设计 findings CLOSED；数据边界执行层 PASS |
| S2-08 | 端点与统计：唯一主终点 post_adaptation_rmse_raw_k5；次要 post_adaptation_rmse_raw_k10；唯一 Holm 族 s2-primary-secondary-2tests（family_size=2）；Wilcoxon n=20 双侧、bootstrap 10,000 seed 20261105、95%CI、Holm | 端点、族、检验、seed、CI 全部落 prereg；只对 2 个端点做 Holm；不得把 K=0/1、标准化 RMSE、MAE、资源等描述性指标升级为主结论；空/null 不插值 | COMPLETED | A2/A5；计划 §1/§6；aggregate、s2_endpoint_tables.csv、s2_holm_family.csv；2 端点决策均 HARM；null 0/240 | 历史设计 findings CLOSED；结果层 PASS |
| S2-09 | 统计决策与证据范围：C1=FULL−FOMAML（负值有益）；SUPPORTED_BENEFIT/HARM 需 p<0.05+CI 不跨 0+方向+相对 >=1%；INCONCLUSIVE 为 null>70%；其余 NO_EVIDENCE；证据范围 DEVELOPMENT_VALIDATION_ONLY；不得外推为未见任务确证性泛化 | 决策规则、效应量、null 处理、证据范围写入 prereg/报告；报告每个数字有 CSV 路径；不得称「显著提升/已证明优于 FOMAML」 | COMPLETED | A2/A5；计划 §6/§8；aggregate overall=SUPPORTED_HARM；A2 报告；证据范围 DEVELOPMENT_VALIDATION_ONLY | 历史设计 findings CLOSED；结果层 PASS |
| S2-10 | 预算/资源/失败规则：训练 1,200 行 + 评估 4,800 行 = 6,000 行；记录 peak_memory；单 (arm, meta_seed) 训练墙钟 >20 min 或峰值 >8 GB 标 RESOURCE_LIMIT 并停止整个正式 run（不重试）；总硬截止 7200 s；prereg.resource_limits 机械校验 | 预算、行数、资源阈值、停止规则写入 prereg；实际墙钟/内存有日志；任何超限标 RESOURCE_LIMIT；不得无授权续跑/重试 | COMPLETED | Lead/A2/A5；计划 §5/§7/§9；run_summary：6,000、0 FAILED、0 RESOURCE_LIMIT；max seed 3.7138 s/1200；peak 261.57 MB/8192；wrapper 101.57 s/7200 | 历史设计 findings CLOSED；执行层 PASS |
| S2-11 | prereg 合同：canonical JSON；prereg_id 排除自身与 prereg_digest；prereg_digest 仅排除自身；code_sha 按 sorted 字典序；analysis_plan_digest 四节 canonical sha；arms 公平；pilot_artifacts；frozen_package 双 family；resource_limits 固定值；占位拒绝；冻结流程 Lead→A5 核验→APPROVE_FOR_S2_RUN→Lead 授权→A2 run | 本地/独立核验脚本对 prereg 重算 digest 一致；占位/绝对路径/sha 不符负控均失败；Lead 冻结 commit 可追溯；A5 核验记录齐全 | COMPLETED | Lead/A5/A1；计划 §7；prereg 4,916 B/fde3ef33…；A5 核验 104 checks/0 fail、8/8 负控、21 gates PASS；对象 994cda8 | 历史设计 findings CLOSED；prereg 门 PASS |
| S2-12 | 代码、测试、分析、图与交付包：实现 maml.py FULL_MAML/s2_prereg.py/s2_runner.py 及测试；生成 run_config/summary/preregistration/data_manifest/CSV/figures PNG；按计划 §8.1 输出 fig1..fig9 共 9 个诊断图键，并按 §8.1.1 映射 Issue #7 §4 七类（③/④/⑦ 显式 NOT_APPLICABLE）；Issue #7 要求的元梯度误差、RMSE/MAE、训练墙钟、峰值 RAM 等可比项；feasible/首次可行/最优可行按 R-S2-02/07 标 NOT_APPLICABLE_S2_SURROGATE_SCOPE | 代码与测试通过；A5 代码审阅；正式 run 后 A5 结果复核；每图有数据源与 CSV/PNG 映射；9 键与七类映射齐全；报告用中文；不得把设计文档/占位图当结果 | COMPLETED | A1/A6/A4/A5；计划 §8.1；A5 delta/result/package；9/9 图 RENDERED；A2 报告 repo 31,771 B/f97b8eb5…；A5 result 140 checks/0 fail；A3 rev3 PASS_WITH_WARNINGS | 历史设计 findings CLOSED；A5-S2R-01 已关闭；A5-S2PKG3-01/02 非阻断 |

## 3. 跨阶段与硬边界项（X-01 至 X-11）

| ID | 边界/跨阶段要求 | 当前事实 | 状态 |
|---|---|---|---|
| X-01 | S2_RUN 必须经 A5 代码审阅、Lead prereg 冻结、A5 prereg 核验、Lead 书面授权；设计批准不等于运行批准 | 代码门 f4ab43f APPROVE；prereg 994cda8 FROZEN；A5 prereg APPROVE_FOR_S2_RUN；Lead 授权 S2-FORMAL-AUTH-20261106T1805Z；run 已完成；结果复核 APPROVE_FOR_S2_RECEIPT | SATISFIED（回执级）；阶段验收 NOT_ISSUED |
| X-02 | physical_call_count=0；禁止 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag/批量 DOE；禁止以任何外部求解器替代 | 无求解器进程/调用/产物；run_config/A5/A3 均 physical=0；6,000 条为合成评价 | ACTIVE_BOUNDARY（PASS） |
| X-03 | 不合并 main；不新建 PR；PR #3/#6 保持 open；S2 在独立分支/worktree；仅 Lead 可写 GitHub | 分支 research/p4-route-a-s2；HEAD=origin=12940c5；main=ec65e5a；PR #3/#6 open；未新开 PR；A4 未写 GitHub | ACTIVE_BOUNDARY（PASS） |
| X-04 | 旧证据只读：M2/M5/M6、S0-2..S0-7、S1 运行/分析/冻结包不得改写、重分类或覆盖；旧负结果保留 | A3 rev3：36 payload 与 27c935e 全同；旧件 0 改；worktree clean；主库/main/PR#3/#6 未动 | ACTIVE_BOUNDARY（PASS） |
| X-05 | S2 仅使用 S0-7 meta_train/meta_validation；不使用 S1 holdout；结论范围 DEVELOPMENT_VALIDATION_ONLY；不得外推 confirmatory/真实飞机 | run_config holdout_rows_used=0、holdout_metrics_read=false；A5 result holdout 0；A2 报告证据范围 DEVELOPMENT_VALIDATION_ONLY | ACTIVE_BOUNDARY（PASS） |
| X-06 | A5 每阶段门：M0R5 仅批准设计/图合同；代码审阅、prereg 核验、正式 run、结果复核逐门；不得跳门或把设计批准写成已运行 | 六阶段门全部有 verdict：M0R5、code delta、prereg、result、package rev3；未跳门；阶段验收另列 | SATISFIED（执行门）；阶段验收 NOT_ISSUED |
| X-07 | 所有权：A1 代码、A6 分析/图、A4 文档矩阵/回执、A5 独立审阅、A2 授权后运行、A3 卫生/证据保护、Lead 冻结/授权/唯一 GitHub 发布 | 本矩阵由 A4 写；A4 无代码/运行/GitHub 写权；A5/A3 文件独立产出 | ACTIVE_BOUNDARY |
| X-08 | Issue #7 §4 的 feasible_hit_rate/first_feasible_eval/best_feasible_value 等约束优化指标在 S2 标量代理下不适用；必须标 NOT_APPLICABLE_S2_SURROGATE_SCOPE，不得伪装为已验证 | 计划 §8；A5 M05 ACCEPTED_SCOPE_REDUCTION；§8 七类映射 ③/④ NOT_APPLICABLE；报告已标 | SCOPE_REDUCTION（已披露） |
| X-09 | Issue #4 为独立 VSPAERO/气动验证轨道；S2 不改变 Issue #4 六门禁；S2 的 0 物理结果不得当作 VSPAERO 验证或真实阻力证据 | Issue #4 与 S2 分轨；S2 无 VSPAERO 调用；D-12D-006 另线 | SEPARATE_BOUNDARY |
| X-10 | S2 结果不得直接作为 S3 放行或阶段验收；须 A5 结果复核、A3 审计、Lead 签发；S3 另行授权 | A5 结果/包复核 APPROVE；A3 rev3 PASS_WITH_WARNINGS；S2 阶段验收 NOT_ISSUED；S3=NOT_APPROVED | ACTIVE_BOUNDARY（S3 未授权） |
| X-11 | 文档优先级：R-S2-01 只解释设计动机与边界，不再是计划覆盖层；冲突时以最新 A5 APPROVE 计划为准 | R-S2-01A raw 7d6f9739…/LF 49ffa9c5…；A5 M0R5 文本 4b2a7901…为旧版本；当前执行基线 v1.5/89fd8d9；当前计划文件 46,118 B/2a046260…为 A5 delta 对象 | RESOLVED（v1.5 + A5 delta） |

## 4. 合同一致性核对（执行层）

| 项目 | 合同要求 | 执行事实 | 状态 |
|---|---|---|---|
| 数据边界 | 仅 meta_train/meta_validation；holdout 0；S0-7 SHA256SUMS 9/9；越界 fail-closed | A5 result：shasums 60/60、records 6000/6000、holdout 0、physical 0；run_config holdout 0 | PASS_EXECUTED |
| 端点/Holm | 唯一主 k5、唯一副 k10；family_size=2；Wilcoxon n=20；bootstrap 10,000/seed 20261105；Holm | aggregate 与 s2_holm_family.csv；2 端点均 HARM；Holm p 同值 | PASS_EXECUTED |
| K0/K1 描述性 | K=0/1 不进入端点；标准化 RMSE 仅描述；null 不插值 | 2,400/4,800 eval 记录 query_rmse_standardized=null（K0/K1 各 1,200）；端点 null 0/240；不插值 | PASS_EXECUTED |
| FD gate | 32/32；max_rel <=1e-6；micro/full pilot | 32/32 PASS；max_rel 1.144759989428372e-09；micro 1.278e-9/full 3.975e-10 | PASS_EXECUTED |
| 公平性 | 两臂仅 first_order 不同；同任务/种子/预算；无克隆臂/免费先验 | NC-05 fairness PASS（run_arms=PASS；arms_equal=True）；A5 未列 blocker | PASS_EXECUTED |
| 确定性 | run_config/core 3/3 同 sha；r1/r2 compare true；bank/manifest sha 同 | run_config 3/3 9522d467…；core 3/3 c9460dae…；compare true | PASS_RUN_LEVEL |
| 确定性（分析层） | 分析器应可验证 determinism | NC-10 DISCLOSED：分析器不读 run 层 determinism 产物；run 层另证 | DISCLOSED（非失败） |
| 资源/预算 | 6,000；0 FAILED/0 重试/0 RESOURCE_LIMIT；max seed<=1200 s；peak<=8192 MB；total<=7200 s | 6,000；0/0/0；max 3.7138 s；261.57 MB；101.57 s | PASS_EXECUTED |
| prereg | canonical、digest、code_sha、bank sha、双 family、resource_limits；冻结后不改 | 4,916 B/fde3ef33…；A5 104/0；8/8 负控；21 gates；冻结 994cda8 | PASS_FROZEN_VERIFIED |
| 图/七类 | fig1..fig9 共 9 键；七类映射；③/④/⑦ NOT_APPLICABLE；每图支持 CSV | figure_status 9/9 RENDERED；n_not_run=0；七类映射见 §8 | PASS_RENDERED |
| 报告 | 中文；A5-S2R-01 补 §7.4 null 归因；所有数字可溯源 | A2 报告 repo 31,771 B/f97b8eb5…；外部 31,971 B/48e0a274…；A5-S2R-01 关闭 | PASS_WITH_MINOR_CLOSED |
| 证据包 | 38/38 payload canonical LF；36 payload 与 27c935e 同；review_chain 互链；绝对路径 0；旧件 0 改 | A5 package rev3 0B/0M/2m；A3 C01–C27 PASS/0 FAIL | PASS_WITH_NONBLOCKING_MINORS |
| 阶段验收 | 需 Lead/负责人签发；A5 结果复核不等于阶段验收 | S2 阶段验收 NOT_ISSUED；S3 NOT_APPROVED | NOT_ISSUED |

## 5. A5 门禁与 findings 摘要

- S2 设计层 M0..M0R5 共 26 行 findings 的完整映射见 v1.2a §5（本文件不重复）；本表只列最终门与执行/结果层，避免把历史设计 findings 与执行层混写。
- 历史设计层最终对象：v1.5/89fd8d9，A5 M0R5 APPROVE_FOR_S2_CODE_AMENDED（0B/0M/1 非阻断 minor：fig9 仅族内分布，A6 图注已注明）；M0R4 的 0B/2M/3m 已由 v1.5 关闭。

| 门/复核 | 对象 | 结论 | 关键证据 |
|---|---|---|---|
| S2 设计 M0R5 | v1.5/89fd8d9 | APPROVE_FOR_S2_CODE_AMENDED 0B/0M/1m | <EXT>/p4-route-a/a5/S2_M0R5_review.md 8,178 B/b1465858… |
| 代码审阅（初始） | 3d576bd | CHANGES_REQUESTED 2B/2M/5m | 1,135 tests OK/462.195 s；A5 S2_code_review.md |
| 代码 delta | f4ab43f | APPROVE_FOR_S2_FORMAL 0B/0M/3m | 1,174 tests OK/1 skipped；8 e2e OK；8 files +2,560/−356；1,764 B/18467e0b… |
| prereg 核验 | 994cda8 | APPROVE_FOR_S2_RUN 0B/0M/1m/3obs | 104 checks/0 fail；8/8 负控；21 gates PASS；3,322 B/282984a0… |
| 结果复核 | raw run root | APPROVE_FOR_S2_RECEIPT 0B/0M/1m/1info | 140 checks/0 fail；shasums 60/60；records 6000/6000；tamper 6/6；FD 32/32；figures 9/9；1,979 B/b1236dd5… |
| 结果复核报告 | — | 1 minor A5-S2R-01 已关闭 | S2_result_review.md 11,555 B/3a8c4bc1… |
| 证据包 rev1 | 27c935e | 历史包 | 36 payload；A3 曾审计 |
| 证据包 rev2 | 625d4b9 | 历史包 | 36 payload；A3 曾审计 |
| 证据包 rev3 | 12940c5 | APPROVE_FOR_S2_RECEIPT_PACKAGE 0B/0M/2m | 38/38 canonical LF；36 payload 同 27c935e；1,456 B/700b80e0… |
| A3 rev3 | 12940c5 | PASS_WITH_WARNINGS；C01–C27 PASS/0 FAIL；W01–W04 info | 16,471 B/7df8d496…；facts 37,366 B/ca5bfcd5…；sums 204 B/5d593032… |

## 6. A4 合同一致性 findings 与处置（S2 设计层）

| ID | 级别 | 处置 | 证据 | 状态 |
|---|---|---|---|---|
| A4-S2C-01 | major | CLOSED：单 (arm, meta_seed) >20 min 或峰值 >8 GB 记 RESOURCE_LIMIT 并停止整个 run；总硬截止 7200 s；prereg 增 resource_limits 并机械校验 | 计划 §5/§7/§9；v1.2a §6 | CLOSED |
| A4-S2C-02 | major | CLOSED：R-S2-01A 版本优先规则（最新 A5 APPROVE 计划 > 旧计划 > R-S2-01）；R-S2-01 文末优先级已更新 | <EXT>/p4-route-a/lead/R-S2-01A_version_precedence.md；A5 M0R5 | CLOSED |
| A4-S2C-03 | gap | CLOSED：§8.1 定义 fig1..fig9 共 9 个诊断图键，§8.1.1 增七类映射；③/④/⑦ 显式 NOT_APPLICABLE | 计划 §8.1；A5 M0R5 | CLOSED |
| A4-S2C-04 | minor | CLOSED：frozen_package 拆 package_family_version=p4ra-family-v4 与 task_family_version=p4ra-family-v3 | 计划 §7；A5 M0R5 | CLOSED |
| A4-S2C-05 | minor | CLOSED：EXT 旧 v1.2 变更说明顶部标 SUPERSEDED；code_sha 顺序以计划 §7 sorted() 为准 | <EXT>/p4-route-a/lead/S2_plan_v1_2_change_note.md；A5 M0R5 | CLOSED |
| A4-S2C-06 | minor | CLOSED：§11 增 M0R3/M0R4/M0R5，§13 增 M0R3/M0R4 行并更新版本标注 | 计划 §11/§13；A5 M0R5 | CLOSED |
| A4-S2C-07 | minor | CLOSED：A5 代码审阅首步确认 969c0e7..v1.5 仅计划文件 diff 且 v1.4/v1.5 未回退修复 | 计划 §11；M0R5 实测 diff 仅 1 文件 | CLOSED |

## 7. 结果摘要（S2 正式 run）

### 7.1 运行事实

| 项 | 值 |
|---|---|
| run_id | s2-formal-20261106T1810Z |
| 模式/状态 | FORMAL / COMPLETED |
| 记录 | 6,000 = 1,200 train + 4,800 eval；0 FAILED；0 RESOURCE_LIMIT；0 重试 |
| 设计 | 2 arms × 3 meta_seeds × 200 outer steps；20 tasks × K{0,1,5,10} × 10 draws |
| 物理 | 0（无 VSPAERO/SU2/Mission/CFD/WaveDrag/DOE） |
| holdout | 0 行；holdout_metrics_read=false |
| 墙钟 | base 25.6769 s；wrapper 101.57 s；总上限 7,200 s |
| 内存 | peak 261.57 MB；上限 8,192 MB |
| 训练墙钟 | FULL 3.6831412338651717 s/seed；FOMAML 2.5632127992964038 s/seed；ratio 1.4369237056229534 |
| 确定性 | run_config 3/3、core 3/3（c9460dae…）、compare r1/r2 true |
| FD | 32/32 PASS；max_rel 1.144759989428372e-09；阈值 1e-6 |

### 7.2 端点

| 端点 | FULL mean | FOMAML mean | FULL median | FOMAML median | median diff | relative | p（Holm） | 95% CI | 方向 | 决策 |
|---|---|---|---|---|---|---|---|---|---|---|
| k5 primary | 1.0096595945946287 | 0.9589177466107437 | 0.9541571205352783 | 0.9228326803629854 | +0.03132444017229297 | −3.394% | 3.814697265625e-06 | [0.04110944269599093,0.05986980980200832] | 19/20 FULL 更差 | SUPPORTED_HARM |
| k10 secondary | 0.9097952349242538 | 0.9003567157566167 | 0.9102146042296693 | 0.8957137631101255 | +0.01450084111954375 | −1.619% | 3.814697265625e-06（raw 1.9073486328125e-06） | [0.007323951140872326,0.011701881656536987] | 20/20 FULL 更差 | SUPPORTED_HARM |

- overall_decision=SUPPORTED_HARM；主、次端点方向一致；Holm family_id=s2-primary-secondary-2tests，family_size=2。
- 结论仅适用合成开发集/当前任务族/当前预算；不得外推为真实飞机、真实气动或普遍结论。

### 7.3 null、负控与图

- 端点 null：0/40 task-arm 单元/端点；每臂 meta_seed 单元 0/60；null 率 0/240。
- 字段 null：4,800 eval 记录中 2,400 条 query_rmse_standardized=null（K0/K1 各 1,200），仅描述性披露，不插值、不进端点。
- 负控：14 项 = 13 PASS + 1 DISCLOSED（NC-10 determinism NOT_VERIFIABLE_IN_ANALYSIS；run 层另证 PASS）。
- 图：9/9 RENDERED；n_not_run=0；fig1..fig9 均有数据源/支持 CSV；fig7 determinism 面板分析层不可验证、run 层另证。

### 7.4 结论与限制

- 事实：6,000 条记录完整；0 失败；0 重试；0 资源超限；physical=0；确定性 3/3；FD 32/32；主/次端点 HARM；A5 结果/包复核 APPROVE；A3 rev3 PASS_WITH_WARNINGS。
- 推断：在本合成开发集、本预算、本任务族下，FULL_MAML 未带来优于 FOMAML 的适应后 RMSE，点估计更差；不得写成「FULL_MAML 普遍有害」或「S2 未通过」。
- 限制：20 meta_validation 任务、3 seeds、2 端点；单任务族/单网络/单超参；无 holdout 确证；无真实气动；6,000 是合成评价记录，不是物理调用。

## 8. Issue #7 §4 七类图映射

| 七类 | 要求 | S2 图/状态 | 说明 |
|---|---|---|---|
| ① | 训练/适应曲线与误差 | fig1_training_loss_curves、fig4_meta_gradient_fd | 训练损失与 FD 诊断；不替代端点统计 |
| ② | 主/次端点与 K 扫描 | fig2_post_adaptation_rmse_k5_k10、fig3_rmse_vs_K、fig6_descriptive_k0_k1_standardized | 端点/方向/K 扫描；K0/K1 仅描述性 |
| ③ | 约束诊断/可行域 | NOT_APPLICABLE_S2_SURROGATE_SCOPE | S2 为标量代理，无约束函数/可行域；不得伪造 |
| ④ | 约束优化臂 | NOT_APPLICABLE_S2_NO_OPTIMIZATION_ARM | S2 无 BO/约束优化臂；BO 属 S1/S3 议题 |
| ⑤ | 成本/效率 | fig8_performance_cost | 墙钟/内存/训练成本比值 |
| ⑥ | 任务族/统计诊断 | fig9_task_family_diagnostics | 任务族分布；约束诊断/OOD 不适用（无 OOD split） |
| ⑦ | 物理/气动验证 | NOT_APPLICABLE_S2_ZERO_PHYSICS_NO_VSPAERO | S2 physical=0；不得把 9 图当真实气动证据 |

## 9. 门禁状态与下一步

| 项目 | 状态 | 说明 |
|---|---|---|
| S2 设计/代码/prereg | APPROVED/FROZEN_VERIFIED | 历史门禁；对象 v1.5/89fd8d9、f4ab43f、994cda8 |
| S2 正式 run | COMPLETED | 6,000 条；0 失败；physical=0；确定性/FD PASS |
| S2 结果复核 | APPROVE_FOR_S2_RECEIPT | 回执级，不是阶段验收 |
| S2 证据包 | APPROVE_FOR_S2_RECEIPT_PACKAGE | 2 个非阻断 minor 已披露 |
| A3 rev3 | PASS_WITH_WARNINGS | 27 项 PASS/0 FAIL；W01–W04 info |
| S2 阶段验收 | NOT_ISSUED | Lead/负责人另行签发 |
| S2 回执 | PUBLISHED（commentId 6693991661） | 由 Lead 发布；GitHub 写入仅 Lead |
| S3 | NOT_APPROVED | 需负责人书面授权 + 新 prereg；不得自动放行 |
| Issue #4 | 独立轨道 | 六门禁不变；D-12D-006 另线等待新预算 |
| main/PR#3/#6 | 未合并/open | PR #3/#6 保持 open；未新开 PR |

- A4 交付：矩阵 v1.3（EXT 替代文本，Lead 已提交 d78dc97）、<EXT>/p4-route-a/a4/issue7_s2_result_receipt_draft.md（DRAFT_FOR_LEAD_REVIEW，Lead 审核并发布 commentId 6693991661）、<EXT>/p4-route-a/a4/task263_delivery_report.md（交付报告）。
- 仓库写入：docs/reviews/p4_route_a_s2_requirement_matrix.md 由 Lead 提交（d78dc97 为矩阵 v1.3；v1.4 为发布状态更新）；A4 不写仓库。
- 下一步：S2 回执已发布；S2 阶段验收与 S3 授权分开处理；S3/S4/Issue #4 均需另行授权，不得由本矩阵自动放行。
- 发布记录：Issue #7 commentId 6693991661（2026-11-06T19:49:49Z）；GitHub 正文 15,564 字符/sha256 3b473e7b…；本地发布快照 22,542 B/sha256 b795b468…；S2_RUN=EXECUTED_AND_RESULT_REVIEWED、阶段验收=NOT_ISSUED、S3=NOT_APPROVED。

## 10. 证据清单（哈希）

| 证据 | 路径 | 大小/行数 | sha256 |
|---|---|---|---|
| S2 计划 v1.5 | <repo>/docs/planning/p4_route_a_s2_execution_plan_20261106.md（历史对象 89fd8d9） | 39,246 B/290 行 | f156b250df40395dc3a3bce5957a1ebe3156025d68f4e798d31ea04be6aded6f |
| S2 计划当前文件 | 同路径（v1.6a，A5 代码审阅整改计划版本） | 46,118 B | 2a046260dc0bcb05d0bafdd4c0c3143400b170edc015661263e72b00a85b4774 |
| S2 prereg | <repo>/research/concorde_metaopt/evidence/s2/s2_preregistration.json | 4,916 B | fde3ef33bab53c67f5f595472a28538b13fbecbc5918903cdc6904c85ad692cd |
| run_config | <repo>/.../evidence/s2/formal_run/run_config.json | 3,939 B | 9522d467… |
| run_summary | 同目录 run_summary.json | 3,908 B | 77d10cd6… |
| run_records | 同目录 run_records.jsonl | 2,186,063 B | 32fbd2c6… |
| fd_gate | 同目录 fd_gate.json | 8,795 B | 7950bcb0… |
| data_manifest | 同目录 data_manifest.json | 2,603 B | 88098139… |
| package aggregate | 同目录 analysis/aggregate.json | 40,581 B | cf0daed6…（脱敏副本；raw 45,846 B/16d7a4d3…；numeric_structure_identical） |
| figure_status | 同目录 analysis/figure_status.json | — | 9/9 RENDERED；n_not_run=0 |
| PACKAGE_MANIFEST | 同目录 PACKAGE_MANIFEST.json | 25,960 B | 907f2c5a… |
| README | 同目录 README.md | 8,070 B | 35d28b78… |
| SHA256SUMS | 同目录 SHA256SUMS.txt | 5,665 B | 63c661cb… |
| A2 报告（repo） | <repo>/docs/reviews/p4_route_a_s2_formal_run_report_20261107.md | 31,771 B | f97b8eb5… |
| A2 报告（外部） | <EXT>/p4-route-a/a2/S2_formal_run_report.md | 31,971 B | 48e0a274… |
| A5 结果复核 | <EXT>/p4-route-a/a5/S2_result_review/S2_result_review.md | 11,555 B | 3a8c4bc1… |
| A5 结果 verdict | 同目录 verdict.json | 1,979 B | b1236dd5… |
| A5 prereg verdict | <EXT>/p4-route-a/a5/S2_prereg_verification/verdict.json | 3,322 B | 282984a0… |
| A5 delta verdict | <EXT>/p4-route-a/a5/S2_delta_verdict.json | 1,764 B | 18467e0b… |
| A5 包 rev3 verdict | <EXT>/p4-route-a/a5/S2_package_review_rev3/verdict.json | 1,456 B | 700b80e0… |
| A3 隔离审计 | <EXT>/p4-route-a/a3/S2_package_isolation_12940c5.md | 16,471 B | 7df8d496… |
| A3 facts | 同目录 S2_package_isolation_12940c5_facts.json | 37,366 B | ca5bfcd5… |
| A3 SHA256SUMS | 同目录 SHA256SUMS.txt | 204 B | 5d593032… |
| 仓库文档归档 | <repo>/docs/reviews/（矩阵 v1.3、A5 包 rev3 复核、A3 rev3 报告） | 3 files +514/−152 | commit d78dc97；父 12940c5 |
| Issue #7 回执 | Issue #7 评论（本矩阵对应回执） | 15,564 字符（GitHub） | commentId 6693991661；sha256 3b473e7b… |
| S0-7 SHA256SUMS | <repo>/research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z/SHA256SUMS.txt | 784 B | 59aa81cd… |

## 11. 边界声明

- 本文件只读核对，不修改仓库代码/计划/冻结包/旧 run；A4 未 commit、未 push、未写 GitHub；Lead 已提交矩阵 v1.3/d78dc97 并发布 Issue #7 回执（commentId 6693991661）。
- physical_call_count=0；无 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag/DOE 调用；6,000 条为合成解析评价记录，不是物理调用。
- 本文件不替代 A5 verdict、不替代 Lead 签发；S2 阶段验收/S3 授权/PR 合并/Issue #4 门禁变更均不在本文件授权范围内。
- 所有状态以 2026-11-07T03:55+08 为准（A4 读取时点 03:30+08；回执发布 03:49+08）；A5/A3 文件后续变更由各自 owner 更新，A4 不代写。
