# P4 路线A S3 需求矩阵（v1.3）

> **v1.4（Lead 追加说明）**：本文件正文是 A4 task-258 的 v1.3 只读核验（生成 2026-11-09T15:20:00Z），状态计数 49 PASS / 13 PARTIAL / 1 NOT_RUN / 3 DEVIATION（共 66 项）。其后事实更新如下，正文状态词未改写以免与 A4 原始记录冲突：
> - A7 M6 包级复核：首轮 `APPROVE_FOR_S3_RECEIPT`（0 blocker / 0 major / 3 minor / 1 info）；v3 元数据修复后 v3-final2 复核 **APPROVE**（257/257 断言 PASS，0 blocker / 0 major）。
> - A3 S3-M6 隔离审计：结论见提交前审计件（`<EXT>/p4-route-a/a3/`）；本文件不重复其判定。
> - 证据包已冻结为 v3-final2：77 文件 / 5,228,512 B / 脱敏 25 / CRLF 19 / 外置 7（308,962,109 B）；`README.md` 20,822 B `b141c838…`；`PACKAGE_MANIFEST.json` 48,173 B `b1f6387b…`；`SHA256SUMS.txt` 10,641 B `cd8c1892…`。
> - 人读报告：`docs/reviews/p4_route_a_s3_result_report_20261109.md`（12 节 + 附录）。
> - 结论未变：C1/C2 四个预注册检验全部 NULL、`overall_decision = NO_EVIDENCE`、`physical_call_count = 0`、S3 阶段验收 NOT_ISSUED、S4 NOT_APPROVED。
> - 本文件仍**不是** A5 审查、**不是** owner 阶段验收、**不是** GitHub 发布。

- 生成时间：2026-11-09T15:20:00Z（A4 只读核验；时区标注为 UTC）
- 任务：task-258 rev7（S3-M3 A4：需求矩阵 v1.0→本文件 v1.3）
- 基线：Issue #7 D-P4-003 + 计划 v1.3e（<plan>；110,311 B；raw LF sha256 543aab5a0581a3b44b3f4c43bfd5fcffec17c266b7715145aa01ff9e062a4fd5；2026-11-09T08:35Z）
- 正式 run：p4ra-s3-formal-20261109T1310Z；3,780 runs / 362,880 evals；physical_call_count=0；solver_processes_started=0
- 总判定：S3_RUN=EXECUTED_M3_PENDING_RECEIPT；M4=ANALYSIS_AVAILABLE_WITH_A7_BOUNDARY；A5 的 M2 放行未落盘（AUTH-02/06、GOV-01=DEVIATION）；S3 阶段验收=NOT_ISSUED；S4=NOT_APPROVED
- 性质：本矩阵为 A4 只读核验记录，不是 A5 审查、不是 owner 阶段验收、不是 GitHub 发布。A4 不写仓库、不评论/不改 Issue、不合并 PR。

## 0. 路径占位与状态图例

路径占位（本文件 0 绝对路径）：

- <EXT>：项目外记忆 EXT 根（A4 交付目录 <EXT>/p4-route-a/a4/）
- <STATE>：项目外记忆根；S3 运行/分析在 <STATE>/p4-route-a/s3_runs/ 与 <STATE>/p4-route-a/s3_analysis/
- <repo-s3>：S3 工作树；<plan>=<repo-s3>/docs/planning/p4_route_a_s3_execution_plan_20261107.md
- <s3-run>：<STATE>/p4-route-a/s3_runs/p4ra-s3-formal-20261109T1310Z
- <s3-analysis>：<STATE>/p4-route-a/s3_analysis/p4ra-s3-formal-20261109T1310Z

状态图例（仅四类）：

- **PASS**：该条要求已有可核对产物/证据，且在 A7 已声明的边界内成立；不等于 owner 阶段验收。
- **PARTIAL**：部分成立，缺口/例外写在“证据/理由”列。
- **NOT_RUN**：要求对应动作/产物未执行或未生成。
- **DEVIATION**：实际执行偏离计划字面门禁/顺序；不自动等于结果无效，但必须由负责人裁定。

## 1. 本版变更（相对 v1.2）

1. 旧状态词（APPROVED_DESIGN/IMPLEMENTED_M1/NOT_CREATED/GATE_PASSED 等）全部替换为 PASS/PARTIAL/NOT_RUN/DEVIATION；旧 66 项 ID 不变。
2. 旧“M1 代码未提交、M2–M6 未开始”已过时：M2 已冻结（378768c）、M2R 修复（987751d/691f554）、M3 正式 run 已执行、M4 分析已生成、A7 M4 已 APPROVE_FOR_S3_ANALYSIS。
3. 统计口径按计划 v1.3e 更新：C1 主族 s3-feasible-hit-2tests（m=2）、C2 次族 s3-gap-to-ref-2tests（m=2）；旧“C1–C5、每族 4 成员、96 比较行”口径作废。
4. 新增关键治理事实：A5 对 M2 的 verdict 为 CHANGES_REQUESTED 且 m3_start_allowed=false；A7 M2R 判 APPROVE_FOR_S3_RUN 后 M3 已执行；A5 对 M2R/分析补丁的最终 verdict 截至本文件生成时未落盘。故 AUTH-02、AUTH-06、GOV-01 记 DEVIATION，不能写“A5 已放行”。
5. 新增 A7 M4 的 F-01..F-08 缺陷、A5 s3_m5 的 P1/P2/P3 静态复现、A5 独立 rerun（analysis_rerun_a5，aggregate_mismatches=[]，C1/C2 决策一致）作为证据指针。
6. 明确 S1/S2 冻结件只读、physical=0、不合并 main、不新开 PR（见 AUTH-03/04、GOV-04/07、跨 Issue 表）。

## 2. AUTH（7）

| ID | 需求（原文语义） | 依据 | 计划位置 | 状态 | 证据/理由 | 风险/待办 |
|---|---|---|---|---|---|---|
| S3-AUTH-01 | S3 授权来自 Issue #7 D-P4-003 负责人书面授权；不覆盖 S1/S2 历史结论 | Issue #7 D-P4-003；计划 §0/§0.2 | §0 L42–89 | PASS | Issue #7 正文授权“算法代码+全合成解析任务训练与正式离线对照，physical_call_count=0 硬隔离”；S1/S2 回执评论未被本 run 改写 | 仅授权 S3 离线实验，不含真实航空/新物理 |
| S3-AUTH-02 | S3 必须逐阶段过 A5 门；M0 未过不得进 M1，M1 未过不得进 M2 | 计划 §0.3/§16 | §0.3 L75–89；§16 L546–568；L680 | **DEVIATION** | 计划 L680：M3 仅在 A5 签发 APPROVE_FOR_S3_RUN 后由 Lead 授权。实际：A5 S3_M2_verdict.json（对象 378768c）=CHANGES_REQUESTED、m3_start_allowed=false；A7 M2R verdict=APPROVE_FOR_S3_RUN；M3 授权 R-S3-M3-CAMPAIGN-20261109T1310Z 已签发并执行；A5 对 M2R 的复核 verdict 未落盘 | 需负责人裁定 A7 是否可替代 A5 的 M2/M3 放行；不得写“A5 已放行” |
| S3-AUTH-03 | S3 范围仅合成任务/离线算法验证；真实飞机、真实气动、SU2/Mission/VSPAERO 均 0 | Issue #7 §0/§2；计划 §0.2 | §0.2 L64–74 | PASS | run_config/run_summary：physical_call_count=0、solver_processes_started=0；family package physical_call_count=0；无 solver 日志 | 若发现真实调用即 fail-closed |
| S3-AUTH-04 | 不启动 S4、真实 Mission、SU2/VSPAERO、路线B 采集策略；不新增物理预算 | Issue #7 §0/§3；计划 §0.2 | §0.2 L64–74 | PASS | S4 无计划/无任务卡；本轮无新增物理预算；run 仍为 S3 | S4 需另立计划与 owner 书面授权 |
| S3-AUTH-05 | S3 计划版本/提交/哈希冻结；v1.3e 为当前基线 | Issue #7 §0；计划 §14/§17 | §14 L514–523；§17 L569–576 | PASS | <plan> 110,311 B sha 543aab5a…；版本 v1.3e（2026-11-09T08:35Z）；A5 M0R3R3 对象 cf18770 | v1.3e 为 M2R 修复依据；不得把 v1.3e 文本修补当 A5 结果 |
| S3-AUTH-06 | M3 Lead 阶段门未过不得正式 run；M1/M2/M3 不得跳步 | 计划 §0.3 | §0.3 L75–89；L680 | **DEVIATION** | A5 M2 verdict=CHANGES_REQUESTED/m3_start_allowed=false；A7 M2R 判 APPROVE_FOR_S3_RUN；Lead 签发 M3 授权；M3 已执行并完成 3,780 runs | 需补 A5 对 M2R 的书面复核或 owner 豁免；否则门禁链不完整 |
| S3-AUTH-07 | S3_RUN/prereg/physical 状态必须如实，不得用 S1/S2 回执替代 | Issue #7 §4；计划 §0.3 | §0.3 L75–89 | PASS | 当前 S3_RUN=EXECUTED_M3_PENDING_RECEIPT；prereg=EXISTS 34,308 B sha 192dd36a…；physical=0；未用 S1/S2 回执冒充 S3 | 回执必须保留 A5 门缺口，不得写“已验收” |

## 3. M0 门禁（6）

| ID | 需求（原文语义） | 依据 | 计划位置 | 状态 | 证据/理由 | 风险/待办 |
|---|---|---|---|---|---|---|
| S3-M0-01 | M0 举证：计划文件/版本/哈希/门禁历史/不可变基线完整 | 计划 §0.2/§0.3/§14 | §0.2 L64–74；§0.3 L75–89；§14 L514–523 | PASS | 计划 v1.3e 110,311 B sha 543aab5a…；A5 M0R3R3 2026-11-07T02:32Z 对象 cf18770，0B/0M/2m | A4 未重算 S2 官方全部 1,174 资产 |
| S3-M0-02 | M0R3R3 通过后才能进 M1 | 计划 §16/§20 | §16 L546–568；§20 L604–613 | PASS | A5 M0R3R3 verdict=APPROVE_FOR_S3_CODE_AMENDED，m1_start_allowed=true | 2 minor 仍需在后续代码审查中跟踪 |
| S3-M0-03 | 历史 M0/M0R findings 全部处置并由 A5 确认 | 计划 §18 | §18 L577–590 | PASS | A5 M0R2 dispositions M0R-01..09 CLOSED；M0R3R3 0B/0M/2m | 历史 JSON 未逐条重开，属基线 |
| S3-M0-04 | S2 已封存资产/文档/哈希不得被 S3 改写 | 计划 §0.2/§10 | §0.2 L64–74；§10 L452–467 | PARTIAL | A3 S3_M2R_isolation_691f554.md（13,761 B sha 128464b7…）称 13 个 evidence 文件零改动、24/24 PASS；但 A4 未重算 S2 官方 1,174 资产 | 若 M5 打包涉及 S2 资产需 A3 再审计 |
| S3-M0-05 | A3 对 S3 暂存/未提交内容的隔离审计通过 | 计划 §0.3/§10；GOV-01 | §0.3 L75–89；§10 L452–467 | PARTIAL | A3 M2R 审计 PASS_WITH_WARNINGS（0 FAIL、7 info），覆盖 378768c→987751d→691f554；M3/M4 的 <s3-run>/<s3-analysis> 未跟踪目录未审计 | A3 M5 阶段须覆盖 run/analysis 与最终包 |
| S3-M0-06 | M1–M6 在 M0 后按序启动，不得并行跳步 | 计划 §0.3 | §0.3 L75–89 | PASS | 实际顺序 M1→M2→M2R→M3→M4；M5/M6 未启动；无并行跳步证据 | A5 M2 门口径问题另见 AUTH-02，不重复计入本行 |

## 4. DATA 数据合同（12）

| ID | 需求（原文语义） | 依据 | 计划位置 | 状态 | 证据/理由 | 风险/待办 |
|---|---|---|---|---|---|---|
| S3-DATA-01 | 任务族 ID/公式版本/12D bounds/参数种子固定：F-QE-conflict-v1、polyhedral-v1、[0.02,0.98]^12 | 计划 §2.1/§2.2 | §2.1 L135–157；§2.2 L158–176 | PASS | family_package 202,120 B sha 70075498…：family_id=F-QE-conflict-v1、formula_version=polyhedral-v1、design_dim=12、delta1_base=0.2、physical_call_count=0 | 无 |
| S3-DATA-02 | 任务函数 f/g1/g2/解析参考解/regret 与证书实现 | 计划 §2.1 | §2.1 L135–157 | PASS | family_package tasks=120；references_sealed 110 refs；model_manifest 6 models；M2 build errors=[]；A7 M2R code_verdict=PASS | 代码正确性由 A5/A7 复核，A4 不重跑 |
| S3-DATA-03 | 证书 7 条残差均 ≤1e-12 才可入族；失败即停 | 计划 §2.1/§2.5 | §2.1 L135–157；§2.5 L199–209 | PARTIAL | 族包/校准存在；A4 可读 references_sealed 110 条 KKT 残差 max=1.942890293094024e-16；但未找到逐任务“7 条残差”证书 JSON，无法逐项复算 7/7 | 要求 A5 在 M5 复核中给出 7 条残差逐项证据；不得写“7/7 已由 A4 验证” |
| S3-DATA-04 | split 计数 60/20/20/10/10；family seed 20261107，holdout seed 20261108 | 计划 §2.2 | §2.2 L158–176 | PASS | family_package split_counts 60/20/20/10/10；family_seed=20261107、holdout_seed=20261108；120 unique tasks；A7 M4 data_integrity=PASS | 无 |
| S3-DATA-05 | task_fingerprint=sha256(canonical {family_id,formula_version,task_id,seed,params})[:16]，params 七键 | 计划 §2.2 | §2.2 L158–176 | PARTIAL | family_package tasks=120，task_id 长度 29 且前缀 p4ra-FQEC-v1-；lead_s3_family_check.json 的 task_id_len_ok=false 为字段异常；aggregate family_task_fingerprints 显示 20/expected_tasks 120 仍 PASS | 需澄清指纹清单 20 vs 120 的汇总口径；不得把 20 当全量 |
| S3-DATA-06 | 校准仅 meta_validation；4096 网格 + 6 条接受条件；不通过不得进 M2 | 计划 §2.5 | §2.5 L199–209 | PASS | calibration 2,283 B sha 8895eb…：selected_delta1_base=0.2，候选 0.2/0.22/0.25 均 accepted；M2 build errors=[] | A4 未独立重算 4096 网格全部点 |
| S3-DATA-07 | 12 分支强 schema/缺失/null 规定；禁止缺字段/静默默认 | 计划 §2.1/§2.5 | §2.1 L135–157；§2.5 L199–209 | PASS | family_package 120 tasks 的 params 含 a/b1/b2/c/delta1/delta2/m2 等键；M2 build errors=[]；A7 M2R 456 tests OK | 无 |
| S3-DATA-08 | 7/7 参考证书在 1e-12 内；证书 JSON 可重算 | 计划 §2.1/§2.5 | §2.1 L135–157；§2.5 L199–209 | PASS | references_sealed 110 refs，A4 只读复算 kkt_residual max=1.942890293094024e-16、min=5.551115123125783e-17、>1e-12 的条数 0 | 110 refs ≠ 7/7 证书项；7 条口径见 DATA-03 的 PARTIAL |
| S3-DATA-09 | 五 split 生成器 + 统一白名单；dev 仅为开发白名单 | 计划 §2.2/§2.3 | §2.2 L158–176；§2.3 L177–191 | PASS | family_package splits 五键；120 tasks；split 计数 60/20/20/10/10；run_config.data_boundary.allowed_splits 含 dev/meta_train/meta_validation/meta_test/meta_test_ood/meta_test_negative_control | dev 无记录；不得把 dev 当有效结果 |
| S3-DATA-10 | 族包 + prereg + data_manifest 落盘（不可变、哈希可复算） | 计划 §2.1/§6.1 | §2.1 L135–157；§6.1 L385–397 | PASS | family_package 202,120 B sha 70075498…；prereg 34,308 B sha 192dd36a…；data_manifest 7,018 B sha f7119bde…；14/14 artifact_sha256 匹配 | 无 |
| S3-DATA-11 | phase-scoped 读取标志：TRAIN 只读 support；EVAL 允许 support 标签；holdout truth 仅分析层 | 计划 §2.3 | §2.3 L177–191 | PASS | run_config/records 含 source/split 字段；data_boundary.training_splits=[]、holdout_splits=[]；A7 M4 data_integrity=PASS | A5 泄漏审查未出最终 verdict（见 ARM-07） |
| S3-DATA-12 | 负控任务由源任务置换生成；仅改变无关量，不改变 f/g 结构 | 计划 §2.5/§3.2 | §2.5 L199–209；§3.2 L233–246 | PARTIAL | negative_control 300 runs/28,800 evals 已执行；F-08：9/10 组 feasible_rate>0.50 被 runner 标 suspicious；仅 S3-DE B64=0.448958，其余 0.609896–0.851302 | 需 A5 判定负控是否有效；不得把 suspicious 当通过 |

## 5. EVAL 评估器合同（7）

| ID | 需求（原文语义） | 依据 | 计划位置 | 状态 | 证据/理由 | 风险/待办 |
|---|---|---|---|---|---|---|
| S3-EVAL-01 | 评估器接口只暴露 10 个语义字段；真实标签不越界到适应层 | 计划 §2.4 | §2.4 L192–198 | PASS | 288,000 main eval records；record schema 校验；A7 M4 data_integrity=PASS | 字段越界由 A5 泄漏审查最终判定 |
| S3-EVAL-02 | 记录 schema 唯一采用 §4.3 + s3_prereg 的 19 字段；billable 由记录数=B 与 source 分布断言 | 计划 §2.4/§4.3；R-S3-03 | §2.4 L192–198；§4.3 L294–304；§17 L569–576 | PASS | 362,880 eval records 全 OK/0 FAILED；data_manifest 14/14；run_config 24 字段/prereg 19 字段 | F-04/F-05 为分析/记录元数据缺陷，另列 |
| S3-EVAL-03 | evidence_scope 固定 SYNTHETIC_OFFLINE/ANALYSIS_ONLY；禁止写成真实飞机/真实气动 | 计划 §2.4/§5.1 | §2.4 L192–198；§5.1 L323–333 | PASS | aggregate.evidence_scope=DEVELOPMENT_VALIDATION_ONLY；physical=0；无真实气动 | 不得写“真实 Mach 2.02 已验证” |
| S3-EVAL-04 | 校准报告只基于 meta_validation；6 条接受条件全部满足才允许 M2 | 计划 §2.5 | §2.5 L199–209 | PASS | calibration 2,283 B sha 8895eb…；selected_delta1_base=0.2；M2 build 无 errors | A4 未逐条重算 6 条件 |
| S3-EVAL-05 | 10 个图键 fig1..fig10 的生成与状态记录 | 计划 §5.3 | §5.3 L347–364 | PARTIAL | figure_status.json：6 RENDERED（fig3/4/5/6/8/9）、4 NOT_RUN（fig1/2/7/10）；理由见图状态 | fig1 无训练记录；fig2 无 K-sweep；fig7 OOD 未接入；fig10 无 VSPAERO 门档案 |
| S3-EVAL-06 | 预算闭合：主 6,000/576,000 + 负控 300/28,800 + OOD 300/28,800 + 确定性 300/28,800 = 6,900/662,400 | 计划 §4.2/§13 | §4.2 L274–293；§13 L498–513 | PASS | 实际按 R-S3-02 降网格执行 3,780/362,880；未超过 6,900/662,400 计划上限；6,900 仅计划未耗 | 不得把 6,900/662,400 写成已执行 |
| S3-EVAL-07 | R-S3-02 降网格版 3,780/362,880；K-sweep 240/15,360 仅 M1 开发，不计正式预算 | 计划 §4.2/§13/§17 | §4.2 L274–293；§13 L498–513；§17 L569–576 | PASS | 3,000+300+300+180=3,780；288,000+28,800+28,800+17,280=362,880；K-sweep 240/15,360 NOT_RUN（fig2） | K-sweep 未执行，不得画 fig2 |

## 6. ARM 方法臂（9）

| ID | 需求（原文语义） | 依据 | 计划位置 | 状态 | 证据/理由 | 风险/待办 |
|---|---|---|---|---|---|---|
| S3-ARM-01 | 五臂固定：S3-BO-RANDOM/S3-BO-FOMAML-OBJ/S3-BO-FOMAML-CON/S3-BO-ANIL-CON/S3-DE | 计划 §3/§4.1 | §3 L210–232；§4.1 L257–273 | PASS | main 3,000 runs = 5 臂 × 5 opt_seed × 2 B × 60 tasks；run_records 含五臂 | 无 |
| S3-ARM-02 | FOMAML-OBJ 与 RANDOM 同任务/种子/候选池/预算，公平比较 | 计划 §3.1/§4.5 | §3.1 L212–232；§4.5 L315–320 | PASS | run grid 同 task/seed/B；A7 M2R code review PASS；A7 M4 data_integrity PASS | A5 公平性审查未出最终 verdict |
| S3-ARM-03 | FOMAML-CON 使用 f 与 g≤0 联合代理打分；约束尺度/可行性排序固定 | 计划 §3.2 | §3.2 L233–246 | PASS | 五臂含 FOMAML-CON；A7 M2R code review PASS；run 记录含约束可行标记 | 不得把 g 当软惩罚不报可行性 |
| S3-ARM-04 | ANIL-CON 为低成本消融；Meta-SGD 不在本阶段 | 计划 §3.3/§9 | §3.3 L247–254；§9 L444–451 | PASS | model_manifest 6 models（FOMAML/ANIL 各 3 seed）；ANIL 臂已运行；无 Meta-SGD | ANIL 决策为 INCONCLUSIVE，不是“成本有效” |
| S3-ARM-05 | DE 作为非元学习基线，同预算/同评价器 | 计划 §3.1/§4.1 | §3.1 L212–232；§4.1 L257–273 | PASS | S3-DE 已运行（B64/B128）；negative control 中 S3-DE B64=0.448958 | 不得用旧 S2 DE 结果代替 |
| S3-ARM-06 | K=5 支持集适应：只用 support 标签；不得读 query 标签 | 计划 §3/§5.4 | §3 L210–232；§5.4 L365–379 | PASS | K=5 固定；episode banks 3×1,600；A7 M2R 456 tests OK；A7 M4 data_integrity PASS | A5 最终泄漏 verdict 未落盘 |
| S3-ARM-07 | 适应流程严禁读取 query 真值或解析最优点；仅 A5 审查可验证 | 计划 §3/§5.4 | §3 L210–232；§5.4 L365–379 | PARTIAL | A7 M2R code review PASS、A7 M4 data_integrity PASS；A5 s3_m5 仅有 review_01_defects.md（P1/P2/P3）与独立 rerun，无最终 leak verdict | 不得把 A7 审计当 A5 独立放行 |
| S3-ARM-08 | 训练 episode 支持样本数与部署 K 匹配（5/10 或混合）；不得只用 128 内循环 | 计划 §4.1/§18 | §4.1 L257–273；§18 L577–590 | PASS | episode banks 3×1,600（sha 64f0be64…/26c2c201…/e3e55f49…）；K=5 部署；M2 build | 旧 128 内循环为消融基线，不用于正式 |
| S3-ARM-09 | 克隆/重复臂识别：同初始化/同候选池/同预测须可检测并披露 | 计划 §4.5/§5.2 | §4.5 L315–320；§5.2 L334–346 | NOT_RUN | aggregate 未含 clone_rate/重复臂检测结论；A5 s3_m5 未出最终 verdict | 不得声称臂独立；需分析器或 A5 补检测 |

## 7. RUN 运行/冻结（7）

| ID | 需求（原文语义） | 依据 | 计划位置 | 状态 | 证据/理由 | 风险/待办 |
|---|---|---|---|---|---|---|
| S3-RUN-01 | 训练仅 meta_train 60 task×3 meta_seed×200 outer；batch 8；K_train 5/10 50/50 | 计划 §4.1 | §4.1 L257–273 | PASS | model_manifest 6 models；M2 training 1,200 records（2 模型×3 seed×200 step）；FORMAL run train=0 | M2 训练证据在 M2 包，不在 formal run |
| S3-RUN-02 | M1 校准 4,096 网格并落 calibration_report；失败即停 | 计划 §2.5/§0.3 | §2.5 L199–209；§0.3 L75–89 | PASS | calibration 2,283 B sha 8895eb…；selected_delta1_base=0.2；M2 build errors=[] | A4 未重算 4096 全网格 |
| S3-RUN-03 | M2 prereg 冻结：19 字段 schema、code_sha、split、预算、分析计划 digest | 计划 §6.1/§6.2 | §6.1 L385–397；§6.2 L398–406 | PASS | prereg 34,308 B sha 192dd36a…；prereg_id p4ra-s3-prereg-b31044c7614cced4；digest b31044c7…；analysis_plan_digest 31ac71d7…；verified=true | 无 |
| S3-RUN-04 | M3 code_sha 覆盖 7 文件；改动后重算并 A5 复核 | 计划 §6.1 | §6.1 L385–397 | PASS | code_sha 75f7bfce…；analysis_code_sha 45ab8962…；A7 M2R code_verdict=PASS；M3 授权绑定同值 | A5 对 M2R 的复核未落盘（AUTH-02） |
| S3-RUN-05 | run_config 24 必填字段、run_summary 18 必填字段；缺一即 fail-closed | 计划 §4.4/§6.1 | §4.4 L305–314；§6.1 L385–397 | PARTIAL | run_config 24 字段/prereg 19 字段存在；但 validation_ok=false（F-01 validator evidence-root 路径缺陷）；6/6 模型 sha 与冻结一致，A7 归因 VALIDATOR_PATH_DEFECT | 修 F-01 后只读重跑 validate 得 ok=true，不得改 run |
| S3-RUN-06 | M5 分析/图：10 图 + endpoint/negative/structural CSV；图状态记录 | 计划 §5.3/§6.1 | §5.3 L347–364；§6.1 L385–397 | PARTIAL | 6/10 图 RENDERED；CSV：s3_endpoint_tables 15,384 B sha 08c9d052…、s3_cost_table 984 B sha 3c331882…、s3_negative_controls 1,612 B sha 07a439a6…；fig7 OOD NOT_RUN | F-03 未关闭；fig1/2/10 也 NOT_RUN |
| S3-RUN-07 | M6 fail-closed：预算/泄漏/旧件改写/未过门即停；停止条件预注册 | 计划 §7/§8 | §7 L407–424；§8 L425–443 | PARTIAL | 预算未超（campaign 2,941.921272s<7,200；sum 22,759.797742s<28,000）；physical=0；stop_reason=null；旧 run 未改写；但 validation_ok=false 未在运行中止，F-02/F-03 未关闭 | A5/A7 已定边界；修复与补丁复核完成前不得称“全部 fail-closed 通过” |

## 8. STAT 统计与图（11）

| ID | 需求（原文语义） | 依据 | 计划位置 | 状态 | 证据/理由 | 风险/待办 |
|---|---|---|---|---|---|---|
| S3-STAT-01 | 主端点：best_feasible_value、gap_to_reference、首次可行、可行率；null 不插值 | 计划 §5.1 | §5.1 L323–333 | PASS | s3_endpoint_tables.csv 15,384 B sha 08c9d052…；C1/C2 表；best_feasible/first_feasible 描述性 | 端点数值不得外推真实飞机 |
| S3-STAT-02 | 配对 bootstrap + Wilcoxon + Holm；族/比较行预注册，禁事后改口径 | 计划 §5.2 | §5.2 L334–346 | PASS | C1/C2 各 family_size=2；exact tie-aware Wilcoxon；Holm；A5 recompute_stats.json 复算 p_perm/p_pratt 与主值一致 | 旧 v1.2 的 96 行口径作废 |
| S3-STAT-03 | 无可行解记 null，不补零、不删除任务；分母固定 | 计划 §5.1/§5.2 | §5.1 L323–333；§5.2 L334–346 | PASS | null_disclosure：C1/C2 n_cells=20、n_null=0；C1 B64 n_zero=1；无补零 | surrogate_rmse n_null=20/20，属描述性不可用 |
| S3-STAT-04 | 任务为一级统计单位，不把种子当任务；paired 以同任务配对 | 计划 §5.2 | §5.2 L334–346 | PASS | n_tasks=20；C1 B64/B128 n_eff=19/20；C2 B64/B128 n_eff=20/19；A5 recompute n=20 | 无 |
| S3-STAT-05 | 结论仅限本合成族/开发验证范围；禁止“普遍优于/二阶普遍有害”外推 | 计划 §5.1/§9 | §5.1 L323–333；§9 L444–451 | PASS | overall_decision=NO_EVIDENCE；evidence_scope=DEVELOPMENT_VALIDATION_ONLY；无效果宣称 | 回执只写“开发验证、无证据” |
| S3-STAT-06 | 多重比较族固定为 C1/C2 各 m=2；报告 4 个正式比较行 | 计划 §5.2/§18 | §5.2 L334–346；§18 L577–590 | PASS | C1 family s3-feasible-hit-2tests（C1a B128/C1b B64）；C2 family s3-gap-to-ref-2tests（C2a B128/C2b B64）；均 decision=NULL | 旧 C1–C5、每族 4 成员、96 行已废；不得混用 |
| S3-STAT-07 | 10 图键 fig1..fig10 与图注/坐标/单位/中文标题合同 | 计划 §5.3 | §5.3 L347–364 | PARTIAL | 6/10 RENDERED；fig1/2/7/10 NOT_RUN；fig7 理由“分析器未读 OOD”，不是无 OOD 数据 | A5 未逐图复核中文标题/图注 |
| S3-STAT-08 | 每端点/臂/预算 CSV 表可重绘；不得只给 PNG | 计划 §5.3/§6.1 | §5.3 L347–364；§6.1 L385–397 | PASS | 4 个 CSV + 6 个图数据 CSV；A5 比对 7 个 CSV 与 Lead sha 全等（compare_vs_lead.json） | 无 |
| S3-STAT-09 | 负结果保留；禁止按效果调参/删任务/改 seed；预注册后一次性 holdout | 计划 §5.2/§8 | §5.2 L334–346；§8 L425–443 | PASS | 负结果 C1/C2 NULL 原样保留；无删任务；确定性 3 次逐字节同；无根据效果改参证据 | holdout 已按 prereg 打开；不得二次调参 |
| S3-STAT-10 | 无校准不确定性不得输出伪置信概率；只报排序/可行性判断 | 计划 §5.1/§5.4 | §5.1 L323–333；§5.4 L365–379 | PASS | ANIL_INCONCLUSIVE；无“概率置信”字段；仅报 feasible_hit_rate/CI/决策 | ANIL 不得写成“成本有效” |
| S3-STAT-11 | 图表必须可重绘、中文标题/图注、标明合成/0 物理 | 计划 §5.3/§9 | §5.3 L347–364；§9 L444–451 | PARTIAL | 6 图可重绘（PNG+data CSV）；4 图 NOT_RUN；A5 未逐图确认中文标题/“合成/0 物理”标注 | 回执不得贴未复核图注 |

## 9. GOV 治理（7）

| ID | 需求（原文语义） | 依据 | 计划位置 | 状态 | 证据/理由 | 风险/待办 |
|---|---|---|---|---|---|---|
| S3-GOV-01 | A5 分阶段门（M0/M0R/M0R2/M1/M2/M3/M4/M5/M6）与 A3 每阶段隔离审计 | 计划 §0.3/§10 | §0.3 L75–89；§10 L452–467 | **DEVIATION** | A5 M2=CHANGES_REQUESTED/m3_start_allowed=false；A7 M2R=APPROVE_FOR_S3_RUN 后 M3 执行；A5 M2R 复核与 A5 结果复核（s3_m5）均未落盘最终 verdict；A3 仅 M2R 审计（691f554），未覆盖 M3/M4 | 需 owner 裁定门禁链；A5 M5/M6 未开始 |
| S3-GOV-02 | A4 只读：不写仓库、不 commit/push、不 GitHub 写；交付只落 EXT | Issue #7 §4；团队协议 | §0.3 门禁责任段 | PASS | 本任务 A4 未写 <repo-s3>；未 commit/push；未评论/改 Issue；矩阵/回执/报告仅 <EXT>/p4-route-a/a4/ | 无 |
| S3-GOV-03 | 阶段验收与 S4 解锁只能由负责人书面签发；不得自动继续 | Issue #7 §0/§4；计划 §0.3 | §0.3 L75–89 | PASS | 未发现 S3 阶段验收文件；S4=NOT_APPROVED；M5/M6 未启动 | M6 后仍需 owner 决定 |
| S3-GOV-04 | PR#3/#6 保持 open、不合并 main；main 不因 S3 移动 | Issue #7 §3；团队协议 | §0.3 门禁责任段 | PASS | 2026-11-09 只读 API：PR#3 open/merged=false/head e5140fc/base main ec65e5a；PR#6 open/merged=false/head ff6280f/base research/concorde-metaopt e5140fc；PR#7=404 | 本轮未新开 PR；S3 分支不合并 main |
| S3-GOV-05 | S3 期间禁止真实飞机 BO/DE、MAML 真实训练、真实航空元训练 | Issue #7 §0 | §0.2 L64–74 | PASS | 0 solver/0 Mission/0 真实飞机；family package physical_call_count=0；run 为合成任务 | 发现即 BLOCKED |
| S3-GOV-06 | 交付包：矩阵 v1.3、回执骨架、报告、SHA256SUMS；0 绝对路径、可追溯 | 任务卡；Issue #7 §4 | §5.3 交付段 | PARTIAL | 本矩阵与回执骨架已落盘；task_report.md 与 SHA256SUMS 同批生成；最终包仍需 Lead 核定 | SUMS 生成后闭合；本文件不自我认证 |
| S3-GOV-07 | S1/S2 历史证据、回执、closeout 不可改写；S3 不覆盖 | Issue #7 §0；团队协议 | §0.2 L64–74 | PASS | Issue #7 S1 评论 6684142041（2026-11-06T11:50:15Z）、S2 评论 6693991661（2026-11-06T19:49:49Z）仍在；S3 只新增文件；A3 M2R 称 13 evidence 文件零改动 | 不得把 S1/S2 结论并入 S3 验收 |

## 10. 跨 Issue/PR 只读快照（2026-11-09）

| 对象 | 状态 | 证据/说明 |
|---|---|---|
| Issue #7 | OPEN；4 条评论 | S1 回执 6684142041（2026-11-06T11:50:15Z）、S2 回执 6693991661（2026-11-06T19:49:49Z）；无 S3 回执；S3 阶段验收未签发 |
| Issue #7 S1 | EXECUTED_AND_RESULT_REVIEWED（历史） | S1 回执已发布；S1 冻结件只读；不覆盖 S3 |
| Issue #7 S2 | EXECUTED_AND_RESULT_REVIEWED / CLOSEOUT（历史） | S2 回执已发布；closeout 历史；不覆盖 S3 |
| Issue #7 S3 | RUN_EXECUTED / RECEIPT_NOT_PUBLISHED | p4ra-s3-formal-20261109T1310Z；A5 M2 门缺口与 A5 结果复核未落盘；不得写“S3 已验收” |
| Issue #4 | OPEN；17 条评论；六门禁未验收 | 最新评论 6652497663（2026-11-05T07:38:19Z）：D-12D-006 零新增求解；GEO-12D/LF-M2.02/HF-M2.02/BODY-CORR/MISSION-DATA/BUDGET 不变；A 类 14/20 剩余 6 CLOSED 不结转；B 类 12 LOCKED；C 类 0/4 |
| Issue #5 | OPEN；3 条评论；历史闭环 | S1 终态回执 6643119583（2026-11-04T21:55:56Z）；不覆盖 S3 |
| PR #3 | OPEN / 未合并 | 只读 API：head e5140fc、base main ec65e5a、commits 57、files 410、+71,671；merged=false |
| PR #6 | OPEN / 未合并 | 只读 API：head ff6280f、base research/concorde-metaopt e5140fc、commits 29、files 135、+188,582；merged=false |
| PR #7 | 不存在 | 只读 API 404；S3 分支未新开 PR |

## 11. A7 M4 缺陷与 A5 在研复现（证据指针）

| ID | 严重度 | 事实 | 对矩阵的影响 | 处置要求 |
|---|---|---|---|---|
| F-01 | major | s3_runner.py:2527-2531 模型路径缺 evidence-root 前缀，validation_ok=false 假阴性；6/6 模型 sha 与冻结一致 | RUN-05 PARTIAL | 修 F-01 后只读重跑 validate 得 ok=true，不得改 run |
| F-02 | major | s3_analysis.py:2240-2248 与 s3_runner.py:1654、s3_prereg.py:2282 模型聚合 sha 契约冲突；逐模型 6/6 一致但聚合不等 | RUN-05/STAT 边界 | 修 F-02 或经独立审计等价补丁后再产最终分析 |
| F-03 | major | OOD 流未接入 analysis/fig7；<s3-run>/ood_records.jsonl 22,430,606 B/28,800 行真实存在；build_ood_rows 恒 NOT_RUN | EVAL-05/RUN-06/STAT-07 PARTIAL | 修 F-03 或审计补丁；fig7 仍 NOT_RUN |
| F-04 | minor | s3_analysis.py:1738-1752,1343-1344 用被增补 sections 重算 analysis_plan_digest 必不等 | STAT 口径披露 | A5 s3_m5 P1 已静态复现；Lead 补丁 D1 处理 |
| F-05 | minor | execution_report.created_utc=14:07:08Z 陈旧（campaign END 14:17:54Z、run_summary 14:17:46Z） | RUN-07 披露 | 回执必须披露 |
| F-06 | info | campaign 日志 3,536 B sha d4cb89f8… 混 UTF-16LE/ASCII | RUN-07 披露 | 回执必须披露 |
| F-07 | info | s3_runner.py 无 __main__，python -m 静默 no-op | 执行方式披露 | 回执必须披露 lead 用仓库外 launcher 500 B sha 9b66b007… |
| F-08 | info | 负控 9/10 suspicious（S3-DE B64=0.448958；其余 0.609896–0.851302，阈值 >0.50） | DATA-12 PARTIAL | 需 A5 判定负控有效性 |
| P1/P2/P3 | A5 在研 | A5 s3_m5/review_01_defects.md 5,623 B：P1 endpoints 注入键；P2 模型聚合 bytes/path 差异；P3 record_digest 排除集不一致；均静态复现、不涉及 runner 数值 | 支持 A7 F-01/F-02/F-04 归因 | A5 独立 rerun status=PASS、aggregate_mismatches=[]、C1/C2 决策一致；尚无 final verdict |

## 12. 不可用/不可宣称声明

1. 6/10 图 RENDERED、4 图 NOT_RUN；不得写“10 图齐全”。
2. OOD 300/28,800 已执行但分析器未消费；不得写“OOD 已验证/已推断”。
3. validation_ok=false 属 F-01 校验器缺陷；不得写“validation 已通过”，应写“validation 因 validator 基址缺陷报 false，6/6 模型已独立复算一致，修复后重验”。
4. A5 M2 放行未落盘；不得写“A5 已放行 S3”“S3 已验收”“S3 已批准”。
5. 负控 9/10 suspicious；不得写“负控全部通过”。
6. 旧 C1–C5/每族 4 成员/96 比较行口径已作废；不得混用。
7. physical=0 是执行记录，不是“无风险/已验证”。
8. 未合并 main、未新开 PR；PR#3/#6 保持 open。
9. 本矩阵不是 owner 签发、不是 A5 审查、不是阶段验收。
10. 不得称“真实 Mach 2.02 已验证”或“真实飞机/真实气动已验证”。
11. 不得把 6,900/662,400 计划预算写成已耗预算；实际为 3,780/362,880。
12. 不得把 A7 的 APPROVE_FOR_S3_ANALYSIS 写成 A5 的 APPROVE_FOR_S3_RECEIPT。

## 13. A4 只读核验记录

| 项 | 结果 | 证据 |
|---|---|---|
| 读取时间 | 2026-11-09T15:00–15:20Z | 本文件生成时间 |
| 仓库/分支 | <repo-s3>；branch research/p4-route-a-s3；HEAD 691f554012b8fe50d4aca3559cb1ccc1ba717276 | git rev-parse/status 只读 |
| 工作树 | 非 clean：?? research/concorde_metaopt/evidence/s3/analysis/、?? research/concorde_metaopt/evidence/s3/run/；其余 clean；A4 未触碰 | git status --short |
| 计划 v1.3e | 110,311 B；raw LF sha256 543aab5a… | <plan> |
| M3 授权 | 4,736 B sha 5e0d8f1d…；run_id p4ra-s3-formal-20261109T1310Z；code_sha 75f7bfce…；deadline 21:10Z | <STATE>/p4-route-a/lead/s3/S3_M3_AUTHORIZATION.json |
| M3 执行记录 | 1,891 B sha 67cd2c4f…；started 13:28:38Z；created 13:29Z；executor=lead（a2 崩溃 0 产物；a6 wrapper 退出） | S3_M3_EXECUTION_RECORD.json |
| M4 分析记录 | 16,090 B sha 61a9fc9f…；status=PASS；overall NO_EVIDENCE；analysis_id s3-analysis-p4ra-s3-formal-20261109T1310Z-p4ra-s3-prereg-b31044c7614cced4 | S3_M4_ANALYSIS_RECORD.json |
| A7 M2R | verdict APPROVE_FOR_S3_RUN；0B/0M/1m/1i；456 tests OK；对象 987751d/691f554 | <EXT>/p4-route-a/a7/verdict.json |
| A7 M4 | verdict APPROVE_FOR_S3_ANALYSIS；data_integrity=PASS；0B/3M/2m/3i；sha 49bddbd4… | <EXT>/p4-route-a/a7/s3_m4/verdict.json |
| A5 M2 | CHANGES_REQUESTED；1B/2M/2m；m3_start_allowed=false；对象 378768c | <EXT>/p4-route-a/a5/S3_M2_review/S3_M2_verdict.json |
| A5 s3_m5 | 在研：review_01_defects.md、probe_*、analysis_rerun_a5；无 final verdict；a5_run_summary status=PASS，aggregate_mismatches=[] | <EXT>/p4-route-a/a5/s3_m5/ |
| GitHub 只读 | Issue #4/#5/#7 与 PR#3/#6 只读 API；PR#7=404；无写操作 | 2026-11-09 读取 |
| 物理调用 | 0 | run_summary/run_config；无 solver 日志 |

## 14. 状态计数与结论

| 状态 | 数量 |
|---|---|
| PASS | 49 |
| PARTIAL | 13 |
| NOT_RUN | 1 |
| DEVIATION | 3 |
| 合计 | 66 |

**总判定**：S3_RUN=EXECUTED_M3_PENDING_RECEIPT；M2=BUILT_BUT_A5_VERDICT_CHANGES_REQUESTED；M2R=A7_APPROVE_FOR_S3_RUN；M3=EXECUTED；M4=ANALYSIS_AVAILABLE_WITH_A7_BOUNDARY；M5=NOT_STARTED；M6=NOT_PUBLISHED；A5_RESULT_REVIEW=IN_PROGRESS；A5_M2R_REVIEW=NOT_RECORDED；S3_STAGE_ACCEPTANCE=NOT_ISSUED；S4=NOT_APPROVED；PHYSICAL_CALL_COUNT=0。

**结论边界**：在 A7 已声明“数据完整性 PASS、validation_ok=false 归因校验器路径缺陷”的边界内，本 run 的 C1/C2 统计结果为 NULL、overall=NO_EVIDENCE；A5 独立 rerun（analysis_rerun_a5）在修补 P1/P2/P3 后得到相同 C1/C2 决策与零 aggregate mismatch，但 A5 最终 verdict 未落盘。因此本矩阵只支持“开发验证结果可用、无可宣称改进”，不支持阶段验收或 S4 解锁。

**最小下一步**：Lead 交 A5 完成 M2R/结果复核；修 F-01 后只读重跑 validate；处置 F-02/F-03 或审计等价补丁；披露 F-05/F-06/F-08；由 owner 裁定 A5/A7 门禁口径后再发布 S3 回执。
