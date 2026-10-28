# RCAIDE_Supersonic · 项目智能体团队计划（v1.0，已获批）

- 日期：2026-10-27（Asia/Shanghai）
- 依据：GitHub Issue #1《[METAOPT-00] 研究总控与第一阶段：Concorde 15维固定巡航优化、MAML-A验证及智能体交接》、仓库主页、阶段计划 phase1_followup_plan_2026-10-27.md
- 批准状态：2026-10-27 用户审阅通过（T1–T6，见 §14）。执行范围：完成 Issue #1 Phase I 全部工作（P0–P6，T5）。
- 目标：Lead + 5 个成员（新增 A5 独立代码审查），完成 Phase I 的 Concorde 15 维固定巡航优化与 MAML-A 的代码、实验、结果报告和 Issue 回执；GitHub 发布逐次经用户批准，预算按 T6 分阶段审批。

---

## 0. 范围与前提

1. 工作对象是 Issue #1 的 Phase I：P0 只读审计 → P1 15 维几何 → P2 固定单巡航评价器 → P3 DOE/多保真 → P4 普通约束 BO/DE 基线 → P5 MAML-A → P6 同预算对照。Phase II–IV 明确不做。
2. MAML 工作严格限定为“路线 A”：学习快速适应响应预测器，只用少量真实探测预测候选目标/约束，选择更有价值的初始设计；之后由同一普通约束 BO 继续。不做路线 B、不做跨物理任务迁移、不把预测标签当真实评价。
3. 子智能体只在收到 Lead 签发的任务卡（含任务 ID、写作用域、交付物、验收标准）后行动；A1 首个 P0 任务即开始写审计 CLI，其余成员首批任务以只读/最小骨架为主。
4. 用户已于 2026-10-27 批准（T1–T6）；本文件转为执行手册：随后真实 spawn、建任务板、建分支、写代码。

---

## 1. 团队拓扑

| 代号 | 成员名 | 角色 | 一句话职责 |
|---|---|---|---|
| L | lead | 项目经理 / 集成者 / 最终审核 | 拆解 Issue、发任务卡、守门禁、唯一 git 写权限、向用户汇报 |
| A1 | code-dev | 代码编写与审阅 | 按 Issue 实现 research/concorde_metaopt 代码与测试，自审并保证可运行 |
| A2 | run-opt | 优化执行与结果审阅 | 代码门禁通过后执行 DOE/BO/DE/MAML 运行，监控、审计结果、产出报告 |
| A3 | repo-guard | 项目环境完整性监控 | 仓库卫生、文档污染、大文件/凭证、产物 schema；AI 记忆文件放仓库外 |
| A4 | issue-liaison | GitHub Issue 审阅与报告 | 读 Issue→结构化 brief→任务分发建议；阶段完成报告/优化结果报告草稿（发布由 Lead 执行） |
| A5 | code-reviewer | 独立代码审查 | 非作者视角独立复审 A1 代码/测试，重跑验收，出具签署或缺陷清单 |

Lead 与 5 个成员共享同一工作目录 D:\RCAIDE 与文件系统；所有写入必须落在各自写作用域（§5.3）。

### 1.1 Lead 职责

- 项目层：把 Issue 要求映射成阶段任务卡；维护任务板与依赖；控制次序与并发；决定阶段是否进入下一门禁。
- 质量层：独立复核 A1 的代码 diff 与测试结果；复核 A2 的 run 目录、summary/evaluations/figures 一致性与结论；复核 A3 的 hygiene 报告；复核 A4 的 Issue 回执是否与证据一致。
- 协作层：唯一执行 git commit/branch/merge/push 的成员；GitHub 写操作（PR、Issue 评论）由 Lead 在用户明确批准后执行（T2，不授权 A4 执行）。
- 汇报层：每个门禁向用户交付阶段性报告与需决策项；本轮先交付本文档。

### 1.2 A1 code-dev（代码编写与审阅）

- 实现：research/concorde_metaopt 下的 configs、tasks、aircraft、evaluation、data、optimization、learning、reports、tests 与 cli.py；P4 基线 BO/DE；P5 MAML-A 训练/适应/初始化器代码。
- 自审：每个任务完成前跑 pytest、CLI smoke、静态检查、逐文件 diff 自审；维护每个模块的“接口-单位-失败模式”说明。
- 交叉配合：接收 A2 的 bug 复现与 A3 的卫生问题；修复后重新过 Code Gate；不直接把“临时绕过”写进代码。
- 禁止：改优化运行结果、伪造数据、写 AI 记忆/日记到仓库、git 写操作、GitHub 写操作、安装新依赖（先申请）、修改上游 RCAIDE/maml-opt/rcaide_cfd 源码、越界写 A2/A3 目录。

### 1.3 A2 run-opt（优化执行与结果审阅）

- 运行：代码门禁通过后，按 Lead 批准的预算执行 P2 重复性/扰动、P3 DOE 与保真度验证、P4 BO/DE 小预算闭环、P5 MAML 训练/适应评估、P6 同预算对照。
- 监控：统一用 run_id、run_config.json、environment.json；运行中周期性检查 evaluations.jsonl 尾部、失败/非法计数、吞吐、内存/磁盘；异常即停。
- 结果审阅：从 evaluations.jsonl 重算 summary.json；校验 schema；复算可行率；从 JSON/CSV 重画 figures 并比对；抽样重跑复现；确认无 inf/失败伪装目标、无泄漏；产出结果报告。
- 禁止：修改代码（发现问题提交 bug 复现给 A1）；伪造/补齐缺失数据；未经批准扩大预算或并行度；把临时脚本写进仓库（草稿放仓库外）。

### 1.4 A3 repo-guard（项目环境完整性监控）

- 基线：登记跟踪文件清单、.gitignore 规则、允许的仓库文档白名单、运行产物 schema、工作区目录职责。
- 周期审计：每个提交/PR 前检查 git status、跟踪文件、大小、敏感信息、AI 记忆/日记文件、临时脚本、缓存、产物 schema、data_manifest、绝对路径泄露。
- 文档污染控制：仓库内只允许 README、docs/ 下人工审核文档、research 包内必要说明；AI 记忆、工作日志、草稿、聊天摘要一律放 outputs/agent-worklog/（gitignored）下（沙箱限制，见 §8.2）。
- 只读为主：仅可修改 .gitignore 与经 Lead 批准的 docs/ 文档；不删除用户文件，发现异常报告 Lead。

### 1.5 A4 issue-liaison（GitHub Issue 审阅与报告）

- 读取：仅在用户/Lead 要求时读取 Issue（gh_issue get/comments），核对标题、正文、更新时间与评论；输出结构化 issue_brief（需求条目、验收证据映射、歧义、任务拆分建议、§6 回执字段映射）。
- 分发建议：把 brief 交 Lead；Lead 确认后由 A4 按任务卡向 A1/A2/A3 发送任务包（含任务 ID、范围、输入、验收、回执字段），并跟踪回执。
- 报告：每个阶段门禁后收集证据，按 Issue §6 模板起草回执；A4 起草→Lead 审阅→用户批准后由 Lead 发布到 Issue（T2/T4）；A4 记录评论 URL 与追踪矩阵。
- 禁止：未经批准发评论/改 Issue/关 Issue；把 Issue 草稿写进仓库；代替 Lead 决定任务优先级；编造证据。

### 1.6 A5 code-reviewer（独立代码审查，T1 新增）

- 独立审查：不参与实现，对 A1 每个交付做独立复审——重跑 pytest/CLI、读关键路径、检查真实 API 调用、单位/参考量、失败分类、预算/缓存、无伪造/占位/泄漏、测试是否覆盖验收点；产出 [REVIEW] 报告（findings 分级 blocking/major/minor，含复现命令与证据路径）。
- 签署：blocking 清零后才允许进入 Code Gate；对 Issue 中“物理适用性/不宣称”类红线单独核查。
- 不写仓库：审查报告与证据记录放 outputs/agent-worklog/reviews/（gitignored）；修复需求回交 Lead→A1，不自行改代码。
- 禁止：git 写、GitHub 写、改他人作用域、以“通过”代替证据、替 A1 设计实现。

---

## 2. RACI（R=负责执行，A=最终担责，C=被咨询，I=被知会）

| 活动 | L | A1 | A2 | A3 | A4 | A5 |
|---|---|---|---|---|---|---|
| Issue 解读与任务拆分 | A | C | C | C | R | C |
| 阶段任务卡与依赖维护 | A/R | I | I | I | C | C |
| 设计空间/配置冻结 | A | R | C | C | I | C |
| 代码实现与单元测试 | A | R | I | I | I | C |
| 代码独立审查 | A | C | I | I | I | R |
| Code Gate（可运行门禁） | A/R | C | C | I | I | C |
| 优化运行与监控 | A | C | R | I | I | I |
| 结果一致性与可复现审计 | A | C | R | C | I | C |
| 环境/卫生审计 | A | C | I | R | I | I |
| 任务完成报告/Issue 回执 | A | C | C | C | R | I |
| GitHub 发布/PR | A/R | I | I | I | C | I |
| 用户沟通与预算申请 | A/R | I | I | I | I | I |

---

## 3. 工作流（每一阶段循环）

### 3.1 状态机

S0 Intake（A4 读 Issue → brief） → S1 Task Dispatch（L 建卡/派发） → S2 Code（A1） → S2R Independent Review（A5） → S3 Code Gate（L+A2 预检） → S4 Run（A2） → S5 Result Review（A2+A3+L） → S6 Report（A4 起草 §6 回执） → S7 Hygiene Release（A3 终检） → S8 Human Review（用户批准） → 下一阶段。

### 3.2 状态输入/输出/责任人

| 状态 | 进入条件 | 责任人 | 输出 | 退出条件 |
|---|---|---|---|---|
| S0 Intake | 用户要求读 Issue | A4 | issue_brief（仓库外） | Lead 确认覆盖 Issue 全部要求 |
| S1 Dispatch | brief 已确认 | L | 任务卡（任务板） | 依赖与写作用域明确 |
| S2 Code | 任务被领取 | A1 | 代码+测试+命令 | 自审通过 |
| S2R Independent Review | A1 自审通过 | A5 | [REVIEW] 报告 | blocking 清零 |
| S3 Code Gate | 代码完成 | L（A2 参与预检） | 门禁记录 | pytest/CLI/审查全过 |
| S4 Run | 代码冻结（git sha 记录） | A2 | run 目录+ledger+日志 | 预算内正常结束或触发停止规则 |
| S5 Review | run 完成 | A2+A3+L | 结果审计报告 | 数据一致、可复现、无泄漏 |
| S6 Report | 证据齐 | A4 | §6 回执草稿 | 用户批准 |
| S7 Release | 回执批准 | A3 | hygiene 报告 | 零问题 |
| S8 Human | 全部证据齐 | L | 阶段汇报 | 用户同意进入下一阶段 |

### 3.3 强制规则

1. 代码冻结：A2 启动运行前记录 HEAD sha 与 run_config；运行期间 A1 不得改动被运行代码；必须修复时由 Lead 暂停运行、记录中断、修复后重过 Code Gate、以新 run_id 重跑。
2. Bug 回路：A2/A3 发现缺陷 → 提交最小复现与证据给 Lead → Lead 派 bug 任务给 A1 → 修复+回归测试 → Code Gate → 继续。
3. 不伪造：缺失/失败/不收敛一律 null 或失败状态；禁止把 inf、失败、缓存命中伪装成真评价；禁止用预测值代替真实评价。
4. 一阶段一回执：每阶段结束必须产出 Issue §6 格式回执草稿；无证据不得写“通过”。
5. 不越界：任何写入前确认路径在写作用域内；共享工作区先读后写；发现他人改动先报告 Lead。

---

## 4. 角色提示词（spawn 时由 Lead 填入）

### 4.0 所有角色共用的纪律（写进每个 prompt）

- 工作目录 D:\RCAIDE；项目解释器 envs/RCAIDE/python.exe；统一入口 run_rcaide.cmd；Python 3.11；Windows。
- 以 GitHub Issue #1 为唯一需求来源；以 phase1_followup_plan_2026-10-27.md 与本文档为执行约束；以 Lead 任务卡为行动边界。
- 首轮 onboarding：读 Issue #1、计划文档、仓库结构、相关源码；A1 首个 P0 任务即写审计 CLI，其余成员首批任务以只读/最小骨架为主，均须先 claim 任务。
- 不写 AI 记忆/日记/草稿到仓库；工作笔记放 outputs/agent-worklog/<成员名>/（gitignored；当前沙箱禁止写 D:\CodexMemory，若用户授予 danger-full-access 再外移）。
- 不执行 git 写命令（branch/commit/push/merge）；不执行 GitHub 写操作；不安装/升级依赖；不改上游包。
- 不伪造数据与结论；不宣称未验证的物理结果；结论必须带证据路径。
- 汇报格式：[STATUS] 任务ID / 进展 / 证据路径 / 阻塞；[BLOCKER] 现象/复现/需要谁做什么；[DONE] 交付物/验收对照/下一步建议。
- 发现跨角色问题（代码 bug、卫生、报告）先报 Lead，不自行修改他人作用域。

### 4.1 A1 code-dev 提示词要点

你是 RCAIDE_Supersonic 的代码编写与审阅智能体。仓库是 RCAIDE-LEADS 1.5.0 的独立超声速研究区，Issue #1 是 Phase I 执行合同（Concorde 15 维固定巡航油耗优化 + MAML-A）。你的任务：严格按 Issue 的强制目录与验收标准，实现 research/concorde_metaopt 的代码、配置、CLI、测试；代码要能真实运行、可复现、无伪造。先读 Issue、计划、现有 RCAIDE 与 maml-opt 源码，再实现；每个模块交付 pytest 证据、运行命令、已知限制。遇到 Issue 要求但外部能力不足（如 OpenVSP/Mach 2 适用性/CFD 收敛），不做假实现，改为明确的 blocked 设计与证据报告。自审清单：导入与 API 真实存在、单位与参考量写明、失败分类、预算硬停止、缓存键完整、JSON 可序列化、路径跨平台、异常信息可诊断、无硬编码私密路径、无网络、无临时调试代码。完成前把 diff 与测试结果发给 Lead 复核。

### 4.2 A2 run-opt 提示词要点

你是优化执行与结果审阅智能体。你只在 Lead 通知“Code Gate 通过”后开始运行。你的职责：按批准的预算与配置执行 P2–P6 的真实运行，监控健康度，保证过程与产物可审计，并独立复核结果是否与结论一致。启动前：核对代码 HEAD sha、run_config、environment、dry-run、预算、磁盘；运行中：记录 evaluations.jsonl，定期检查失败/非法/吞吐/耗时，触发停止规则立即停并报告；结束后：从原始记录重算 summary、校验 schema、重画 figures 并比对、抽样复现、检查无 inf/失败伪装、检查泄漏、写 run 报告与 Issue 回执所需证据。禁止：修改代码、伪造补数据、擅自扩大预算/并行度、把临时脚本提交仓库。发现问题给 Lead 报 [BLOCKER]，附最小复现。

### 4.3 A3 repo-guard 提示词要点

你是项目环境完整性监控智能体。你守护仓库整洁与合规：确保仓库只包含 Issue 允许的代码、配置、测试、人工审核文档与轻量运行结果；AI 记忆/日记/草稿/聊天摘要不得进入仓库，统一放 outputs/agent-worklog/（gitignored）；envs/、outputs/、原始 CFD、大文件不得被跟踪；不得提交 token/密钥/私密绝对路径；不得用 *.md 通配屏蔽正常文档。每个提交/PR 前执行检查：git status 与跟踪清单、文件大小、敏感信息扫描、文档白名单、临时脚本/缓存、运行产物 schema、data_manifest、绝对路径、忽略规则有效性。输出 hygiene 报告与零问题签署；发现问题报告 Lead，不擅自删除用户文件，只可修改 .gitignore 与经批准的 docs/。

### 4.4 A4 issue-liaison 提示词要点

你是 GitHub Issue 审阅与报告智能体。你只在用户/Lead 要求时读取 Issue #1（gh_issue，只读），核对正文/评论/更新时间，输出结构化 brief：逐条需求、验收证据映射、歧义与风险、任务拆分建议、§6 回执字段映射。brief 交 Lead 确认后，向 A1/A2/A3/A5 分发任务包并跟踪。每阶段门禁后，按 Issue §6 字段收集证据起草回执；A4 起草→Lead 审阅→用户明确批准→由 Lead 发布评论（T2/T4），A4 不直接发布；记录评论 URL，更新追踪矩阵。不得修改 Issue 正文、不得未经批准关闭 Issue、不得把草稿或 AI 记忆写入仓库、不得编造证据、不得越过 Lead 决定优先级。

### 4.5 A5 code-reviewer 提示词要点

你是独立代码审查智能体（T1 新增）。你不参与实现，只对 A1 的交付做非作者视角的独立复核：重跑 pytest 与 CLI 验收命令；阅读关键实现路径，核对 RCAIDE-LEADS/maml-opt/rcaide_cfd 真实 API、单位/参考量、失败分类、约束符号、预算/缓存/停止条件、确定性；检查伪造/占位/掩盖 skip、数据泄漏、预测值冒充真值、把物理未验证写成 PASS；核对测试是否覆盖 Issue 验收点。输出 [REVIEW] 报告（blocking/major/minor，含复现命令与证据路径），blocking 清零并明确签署后才允许 Code Gate。审查报告放 outputs/agent-worklog/reviews/，不写仓库、不改代码（修复回交 Lead→A1）、不做 git/GitHub 写操作。

### 4.6 spawn 参数（已获批）

| 成员 | name | context | description |
|---|---|---|---|
| A1 | code-dev | fresh | RCAIDE_Supersonic 代码编写、测试与自审 |
| A2 | run-opt | fresh | 优化运行、监控与结果审阅 |
| A3 | repo-guard | fresh | 仓库/环境完整性审计 |
| A4 | issue-liaison | fresh | GitHub Issue 审阅、任务分发与报告 |
| A5 | code-reviewer | fresh | 独立代码审查、验收点与红线复核 |

Lead 在 spawn prompt 中附：Issue #1 摘要、本文档路径、当前阶段任务卡、写作用域、首批任务与回报要求；A5 另附审查清单与当前待审对象。

---

## 5. 任务板与任务卡规划

### 5.1 任务卡模板

- ID / 标题 / 对应 Issue 阶段（P0–P6）
- Owner / 协助 / 依赖（blocked_by）
- 写作用域（advisory 路径前缀）
- 输入（文档、源码、上一阶段产物）
- 交付物（精确路径）
- 验收标准（可执行命令 + 证据文件 + 判定）
- 预算/时限 / 状态（draft/ready/claimed/in_progress/code_gate/run/blocked/review/done）
- 证据（命令输出路径、commit sha、run_id）

### 5.2 阶段任务清单（批准后建板）

| ID | 阶段 | 任务 | Owner | 依赖 | 主要交付/验收 |
|---|---|---|---|---|---|
| M-00 | 启动 | 5 成员 onboarding 与角色确认 | A1–A5 | — | onboarding 状态消息 |
| M-01 | P0 | Issue 结构化 brief 与需求矩阵 | A4 | M-00 | issue_brief（仓库外），Lead 确认 |
| M-02 | P0 | P0 审计：环境/工具链/API/Concorde 源码表/阻断清单 | A1 | M-01 | audit CLI、environment.json、审计表、run 目录 |
| M-02R | P0 | P0 审计代码/证据独立审查 | A5 | M-02 | [REVIEW] 报告、签署 |
| M-03 | P0 | 审计核验与仓库基线登记 | A3 | M-02 | hygiene/基线报告 |
| M-04 | P0 | 第一轮回执草稿与发布审批 | A4 | M-02,M-03 | §6 回执草稿 |
| M-05 | P1 | 15D design_space/task 配置与几何生成/检查代码 | A1 | M-02 | configs、geometry 模块、31+ 测试 |
| M-05R | P1 | P1 几何代码独立审查 | A5 | M-05 | [REVIEW] 报告、签署 |
| M-06 | P1 | 几何 effect matrix 独立验收运行 | A2 | M-05 | geometry-check 全变量输出、CSV/JSON/PNG、审计 |
| M-07 | P2 | TaskSpec、evaluate 契约、Mission 评价器、ledger | A1 | M-05 | 代码+测试+smoke |
| M-07R | P2 | P2 评价器代码独立审查 | A5 | M-07 | [REVIEW] 报告、签署 |
| M-08 | P2 | 重复性/扰动/玩具替身验收运行与单次成本测量 | A2 | M-07 | run 目录、summary/evaluations、成本表 |
| M-09 | P3 | DOE 生成、数据集校验、低保真/高保真接口 | A1 | M-07 | 代码+测试+manifest schema |
| M-09R | P3 | P3 DOE/保真度代码独立审查 | A5 | M-09 | [REVIEW] 报告、签署 |
| M-10 | P3 | LHS 32/128、低保真适用性、SU2 小规模验证 | A2 | M-09 | dataset_manifest、适用性报告 |
| M-11 | P4 | 普通约束 BO/DE 代码与数学函数测试 | A1 | M-07 | 代码+测试+toy 证据 |
| M-11R | P4 | P4 BO/DE 代码独立审查 | A5 | M-11 | [REVIEW] 报告、签署 |
| M-12 | P4 | Concorde BO/DE 小预算闭环 | A2 | M-11 | smoke/BO/DE run、convergence/feasibility 图 |
| M-13 | P5 | MAML-A：元任务、模型/训练/适应、初始化器、泄漏测试 | A1 | M-11 | 代码+测试+训练证据 |
| M-13R | P5 | MAML-A 代码/泄漏独立审查 | A5 | M-13 | [REVIEW] 报告、签署 |
| M-14 | P5 | MAML 训练/适应/消融与 A 初始化运行 | A2 | M-13 | 训练日志、RMSE/排序诊断、初始化对比 |
| M-15 | P6 | 同预算对照矩阵运行（含强基线） | A2 | M-14 | 多 seed run 目录、汇总 JSON/PNG |
| M-16 | P6 | 阶段/最终技术报告与 Issue 回执 | A4 | M-15 | §6 回执、报告、PR 描述 |
| M-17 | 每阶段 | hygiene 审计（常设） | A3 | 各阶段 | 零问题签署 |
| M-18 | 每阶段 | 代码审查与 Code Gate（常设） | L | A1 完成 | 门禁记录 |

（任务板已获批准：P0/P1 首批卡由 Lead 建板，后续阶段随门禁滚动建卡；A5 审查卡先于对应 Code Gate。）

### 5.3 写作用域（建议）

| 成员 | 写作用域 | 说明 |
|---|---|---|
| Lead | 全仓库最终集成、git 写、任务板、经用户批准的 GitHub 写 | 唯一 commit/merge/push 权限 |
| A1 | research/concorde_metaopt/（除 optimization_runs/ 与 reports/ 生成物） | 代码、configs、tasks、tests、CLI |
| A2 | research/concorde_metaopt/optimization_runs/、outputs/concorde_metaopt/ | 只写运行产物，不改代码 |
| A3 | .gitignore、docs/（仅经批准文档） | 卫生与文档，不删用户文件 |
| A4 | outputs/agent-worklog/issue/ 与 GitHub 草稿 | 不写仓库文件；发布由 Lead 执行 |
| A5 | outputs/agent-worklog/reviews/（不写仓库） | 独立审查报告与证据 |

### 5.4 依赖图

M-00 → M-01 → M-02 → M-02R → M-03/M-04；M-02 → M-05 → M-05R → M-06；M-05 → M-07 → M-07R → M-08；M-07 → M-09 → M-09R → M-10；M-07 → M-11 → M-11R → M-12；M-11 → M-13 → M-13R → M-14 → M-15 → M-16。M-17/M-18 在每个阶段完成前必过。

---

## 6. 代码编写与审查制度

### 6.1 编码规则

- Python 3.11；优先复用 RCAIDE-LEADS 1.5.0、maml-opt 0.1.0、rcaide_cfd 0.1.0 的真实 API；调用前先读安装包源码/签名，不凭记忆写接口。
- 配置与任务参数全部显式落在 YAML/JSON（design_space_15d、task_fixed_cruise、experiment_phase1）；代码不硬编码数值与路径。
- 公共函数带类型提示、单位、失败模式；所有约束统一 g_j ≤ 0；失败分类与物理违约分开。
- 路径基于仓库根相对解析；跨平台路径用 pathlib；文件写入 UTF-8；JSON 可序列化；无网络调用；默认确定性种子。
- 预算、缓存、去重、停止条件必须实现为可测试逻辑；缓存键覆盖几何/任务/保真度/代码版本/参考量。
- 禁止伪实现：外部能力不足时返回明确 blocked 状态与证据，不返回假数据。

### 6.2 测试策略

- 单元：几何派生量、折点/弦长顺序、约束符号、油耗计算、ledger 行 schema、缓存键、预算异常。
- 玩具：数学函数（Branin/Ackley + 约束）验证 BO/初始化/可行性选点；替身后端验证缓存/预算/失败序列化。
- 集成：P1 15 维 effect matrix（每变量 ±扰动 ≥31 例）；P2 基准重复性与单变量扰动；P3 dataset 校验；P5 泄漏测试与适应权重变化测试。
- 真实：仅在小预算、明确批准下运行；真实结果单独记账，不与玩具结果混表。
- 统一命令：run_rcaide.cmd -m pytest research/concorde_metaopt/tests -q（数值阈值以实测为准）。

### 6.3 四级审查（T1 新增 A5）

1. A1 自审：跑全部测试 + CLI smoke；逐文件 diff 自审（接口、单位、异常、硬编码、临时调试）。
2. A5 独立审查：非作者复核，重跑测试/CLI、读关键实现、核查真实 API/单位/失败分类/伪造占位/泄漏与测试覆盖；blocking 清零并出具签署。
3. Lead 独立审查：读 diff、重跑测试、抽查 JSON/CSV/PNG 一致性、检查验收对照。
4. A2 验收运行：全新 run 目录复跑关键命令，确认可复现；发现 bug 回退到 §3.3 的 bug 回路。

### 6.4 Code Gate 清单（G-code）

- pytest 全绿（含新增测试），无 skip 掩盖关键路径；
- CLI 目标命令可在干净 run 目录执行，--dry-run/--budget 生效；
- 无 NotImplementedError/占位返回冒充完成；blocked 项有证据与说明；
- 输入输出 schema 与 Issue 对齐（summary/evaluations/run_config/environment/index）；
- 失败/非法/不收敛路径有测试；无 inf/NaN 泄漏；
- 无硬编码私密路径/token；无网络；无未批准依赖；
- git status 干净（仅本任务预期文件），A3 通过卫生预检。

### 6.5 Bug 处理

A2/A3 报告 → Lead 建 bug 任务 → A1 最小复现 + 修复 + 回归测试 → Code Gate → A2 重跑相关小节 → 记录在 run 报告“已修复问题”节。禁止 A2 直接改代码或手工修补数据。

---

## 7. 优化执行与结果审查制度

### 7.1 运行前

- 核对：代码 HEAD sha、run_config.json、environment.json、预算上限、磁盘/CPU/内存、无并发冲突运行。
- dry-run 与小样本 smoke（如 ≤5 次真实评价）先通过，再放大。
- 运行目录固定：research/concorde_metaopt/optimization_runs/<run_id>/；原始 CFD/大日志：outputs/concorde_metaopt/<run_id>/；run_id 格式 <stage>_<method>_<YYYYMMDD-HHMMSS>_s<seed>。

### 7.2 运行中监控

- 每检查点看：evaluations.jsonl 尾部、真实调用数、失败/非法数、平均耗时、累计墙钟、磁盘。
- 监控脚本不得提交仓库；用 CLI 自带状态或仓库外脚本。
- 长运行后台任务化，保留可恢复 ledger；每 30–60 分钟记录一次状态摘要。

### 7.3 停止规则（任一触发即停并报 Lead）

连续失败/异常；出现非有限值或明显违反物理一致性的输出；预算/时间超限；内存/磁盘异常；代码/配置被改动；同配置结果不一致无法解释。

### 7.4 结果审计清单

- summary.json 由 evaluations.jsonl 重算一致；字段齐全（缺失 null）；
- 每行 evaluations 字段完整；cumulative_calls/physical_call_count/cache_hit 自洽；
- 可行率、首次可行、最优可行油耗与原始行一致；无可行点时不伪造目标；
- figures 由 JSON/CSV 重画可复现（轴名/单位/图例/图注）；
- 抽样 2–3 个设计以同配置重跑，结果在声明容差内；
- P5/P6 泄漏检查：S/Q 按任务身份不重叠，预测标签未进入 BO；
- data_manifest 覆盖 P3/P6 原始文件与 hash；远程不可复核项注明；
- 失败/重试单独成表，不计入成功次数。

### 7.5 报告格式（每 run）

run 报告（仓库外或按 Issue 允许的 docs/ 提交，经 Lead 定）：run_id/方法/预算/种子/commit/环境；总调用与真实调用；失败分类；最优可行设计与油耗；收敛/可行率图；异常与修复；结论边界（软件验收/物理验收/统计结论分开）；下一步。

### 7.6 MAML 特定要求（P5/P6）

- 复用 maml-opt 真实 ResponseModel/conditional_pretraining_step/evaluate_adaptation/meta_train_step 与 train_maml；不虚构 API；缺能力写适配层并说明。
- 首版元任务用“仅训练数据拟合的 GP”合成有标注任务；S/Q 按完整任务身份划分；明确这是算法级验证，不是物理迁移。
- 必须有支持集少步梯度更新代码与测试；记录适应前后预测变化、候选排序变化、选点变化。
- 对照臂：普通 GP、普通 MLP、预训练+微调、MAML、历史最佳复用、Sobol/LHS 初始；同任务/同预算/同候选池。
- 路线 A 只改初始设计：共同探测 → 任务内适应 → 候选池预测/约束排序/多样性 → 额外初始设计真实评价 → 同一普通约束 BO 继续；预测值不得写回标签。
- 主指标：真实评价成本—最佳可行油耗、首次可行成本、可行率、失败重试、在线/离线累计成本；RMSE/排序仅辅助。

---

## 8. 环境完整性制度

### 8.1 仓库允许与禁止

允许：README、docs/ 人工审核技术文档、research/concorde_metaopt 代码/配置/测试、优化运行小结果（summary/run_config/environment/evaluations/best_design/figures/小 CSV/index.json）、必要小日志。
禁止：AI 记忆/日记/草稿/思考记录/上下文摘要（MEMORY.md、memory*.md、.agent_memory/、.aider/ 等）、token/密钥、私密绝对路径、envs/outputs 跟踪、原始网格/流场/大日志、重复/临时脚本、缓存文件。

### 8.2 记忆与工作文档位置

- 工作根（默认）：outputs/agent-worklog/（gitignored，属仓库工作区但不入库；当前沙箱禁止写 D:\CodexMemory）。子目录：issue/、code-dev/、run-opt/、repo-guard/、issue-liaison/、reviewer/、scratch/、logs/、reviews/。
- 备选（若用户授予 danger-full-access）：D:\CodexMemory\RCAIDE\metaopt-worklog\，结构相同。
- 仓库内只保留 Issue 允许的 README.md 与 docs/*.md（人工审核后）；本计划已获批准，将移入 docs/planning/ 随 P0 提交。

### 8.3 检查清单（每提交/PR）

git status 与跟踪文件清单；文件大小与数量异常；敏感信息扫描（token/key/password/私密路径）；AI 文档特征扫描；文档白名单；临时脚本与缓存；运行产物 schema 与命名；data_manifest 完整性；.gitignore 生效性（research/、optimization_runs 不被误忽略；outputs/envs 被忽略）；绝对路径/用户名泄露。

### 8.4 敏感信息与凭证

.agents/ 下 token 文件不得读取/复制/提交；任何提交前扫描命中即停并报 Lead；如需 GitHub 操作，由 Lead 使用工具审批流程，不直接读 token 文件。

### 8.5 清理与保留

输出目录与中间文件按 run 保留到阶段报告完成；可清理的仅限可重建缓存；删除任何文件前 Lead 批准；原始 CFD 保留并在 manifest 标注，不入 git。

### 8.6 报告格式

[HYGIENE] 范围/命令/发现数/明细/修复建议/签署（零问题才允许提交或 PR）。

---

## 9. GitHub Issue 工作流

### 9.1 读取与 brief

A4 在用户/Lead 要求时：gh_issue get #1 + comments（当前 0 条）；核对更新时间与正文变化；输出 issue_brief：元数据、逐条需求（引用原文）、验收证据映射（P0–P6）、强制目录与 schema、回执字段、已知歧义/风险、任务拆分建议。若 Issue 更新，重读并出变更单。

### 9.2 任务分发

brief → Lead 确认 → Lead 建任务卡 → A4 按任务卡向 A1/A2/A3 发送任务包（任务 ID、范围、输入、验收、回执字段）；A4 维护需求→任务→证据追踪矩阵。

### 9.3 报告发布

- 每阶段门禁后，A4 收集 Lead/A1/A2/A3/A5 证据，按 Issue §6 字段起草回执；A4 起草→Lead 审阅→等待用户明确批准→由 Lead 发布到 Issue #1（T2/T4）；记录 URL。
- 最终报告另写：软件验收/物理验收/统计结论分开；配套 PR 与运行目录链接；即使 MAML 无收益也如实报告。
- 发布前核对：所有数字可追溯到 run 目录；无夸大/未验证物理结论；大文件位置与 hash 已注；未完成项已列。

### 9.4 审批与安全

- 任何 GitHub 写操作（issue_comment、PR create/update、issue close）必须用户明确批准；由 Lead 执行（T2），A4 只负责起草。
- 不修改 Issue 正文；不关闭 Issue 除非用户批准并确认 §8 关闭条件。
- 频率控制：按阶段批量发布，避免刷评论；发布失败记录错误并恢复。

### 9.5 PR 协作

Lead 在 P0 完成后建分支 research/concorde-metaopt 与草稿 PR；A4 起草 PR 描述（对应 Issue 阶段、变更、证据、复现命令）；每阶段更新 PR 说明并回执；合并策略由用户决定。

### 9.6 回执模板（§6 字段映射）

阶段/完成状态（done/blocked/partial）；分支/HEAD SHA/PR；新增修改代码路径与功能；复现命令/版本；单元集成测试与真实 Mission 验收（通过/失败/未运行+证据）；固定 TaskSpec/15 维版本；DOE 候选/几何合法/真实 Mission/VLM/SU2/失败重试数；预算与 CPU/墙钟；仓库内 optimization_runs 路径；大型 CFD 原始文件位置与 SHA256；已知物理局限/模型风险/数据泄漏风险；未完成项与是否请求进入下一阶段。

---

## 10. 沟通协议

### 10.1 消息模板

- [CLAIM] 任务ID / 预计完成 / 写作用域确认
- [STATUS] 任务ID / 进展 / 证据路径 / 下一步
- [BLOCKER] 任务ID / 现象 / 复现 / 影响 / 需要谁做什么
- [CODE-GATE] 任务ID / 测试命令与结果 / diff 范围 / 已知风险
- [RUN-SUMMARY] run_id / 预算使用 / 最佳值 / 失败数 / 产物路径
- [HYGIENE] 范围 / 发现 / 修复建议 / 签署
- [ISSUE-DRAFT] 阶段 / 回执文件路径 / 待批准项
- [REVIEW-REQUEST] 对象 / 需要审的 diff 或产物 / 截止

### 10.2 状态节奏

claim 后立即回执；长任务（>1h）每 30–60 分钟或每检查点报一次；完成/阻塞立即报 Lead；不静默长跑。

### 10.3 升级路径

需求歧义/外部能力不足/预算风险/卫生违规/需要 GitHub 批准 → 立即 Lead；Lead 决定是否上报用户。

### 10.4 共享工作区规则

同一工作目录、同一文件系统；写入前确认路径属于自己作用域；他人文件只读；发现他人改动或冲突先报告 Lead；Lead 负责最终 diff 与测试回归。所有 git 写操作仅 Lead 执行；任务板用 claim（含 revision）更新，完成即 complete。

---

## 11. 阶段计划、门禁与人工审核点

| 阶段 | Issue 要求 | 主要产出（责任） | 门禁 | 人工审核 | 估算 |
|---|---|---|---|---|---|
| P0 | 只读审计、可复用性、阻断清单、回执 | 审计 CLI/证据（A1）；基线/卫生（A3）；brief（A4） | G0 工具链/API 结论 + D2 几何路线 | R1 | 0.5–1 天 |
| P1 | 15D 参数化真实几何+31 测试 | configs/geometry（A1）；effect matrix 验收（A2）；卫生（A3） | G1 15/15 变量生效 | R2 | 2–3 天 |
| P2 | 固定单巡航评价器+重复性 | TaskSpec/evaluate/ledger（A1）；重复性与成本（A2） | G2 可重复+单次耗时 | R3（含 D3 预算） | 2–3 天 |
| P3 | DOE 32→128、保真度适用性 | DOE/接口（A1）；LHS/SU2 验证（A2）；manifest | G3 数据可追溯/适用性结论 | R4 | 3–4 天 |
| P4 | 普通约束 BO/DE 基线闭环 | BO/DE 代码（A1）；smoke/BO/DE 运行（A2） | G4 真实闭环+预算实测 | R5 | 2 天 |
| P5 | MAML-A 同权限实验链 | 学习/初始化代码（A1）；训练/适应/对照（A2） | G5 适应有效+无泄漏 | R6 | 3 天 |
| P6 | 同预算对照+报告+回执 | 对照运行（A2）；报告（A4）；卫生（A3） | G6 关闭条件 | R7 最终 | 3–5 天 + 机时 |

---

## 12. 风险登记（团队运行层）

| 风险 | 触发/证据 | 缓解 | 责任 |
|---|---|---|---|
| 角色写作用域重叠 | 同一文件被两人改 | 作用域表+任务卡+Lead 复核 diff | L |
| A1 成为瓶颈 | 运行等待代码 | A2 先用玩具/数学任务；P4 与 P5 代码并行；bug 快修 | L |
| A2 长跑中断/超时 | 8h 级运行曾中断 | 小预算分阶段、ledger 恢复、后台任务、检查点 | A2 |
| 结果不可复现 | 同配置不同结果 | env/config/sha 冻结；抽样重跑；差异记录 | A2 |
| 伪参数化 | 字段变几何不变 | effect matrix 强制；gate 拦截 | A1/A2 |
| Mach 2 保真度不适用 | VLM/CFD 限制 | 声明域+只做筛选；不宣称高保真 | A2/A1 |
| CFD 不收敛 | 2026-10-26 诊断流 NOT_CONVERGED | 预留调参；失败单独记账；降级预案 | A2 |
| 数据泄漏 | split 同任务/预测入 BO | 任务身份划分+自动测试+审计 | A1/A2 |
| 预算超支 | 并行/规模失控 | 预算硬停止+用户批准+分阶段 | L/A2 |
| 文档污染 | AI 草稿进仓库 | A3 白名单+提交前扫描 | A3 |
| 敏感信息泄露 | token/路径 | 扫描+忽略规则+不读 token | A3 |
| GitHub 操作风险 | 未批准发布/误改 Issue | 审批门+草稿先行+只 comment | A4/L |
| 上下文遗忘 | 长任务/多轮 | 任务卡+磁盘证据+worklog；不依赖记忆 | 全员 |

---

## 13. 启动清单（已批准，执行中）

1. Lead 在任务板创建 P0/P1 首批任务卡（含依赖与写作用域），后续阶段随门禁滚动建卡。
2. Lead 按 §4.6 spawn 5 个成员（fresh）；成员 claim 首个任务并回报（A1/A2/A3/A4 执行各自 P0 首任务，A5 建立审查基线）。
3. A4 先产出 issue_brief（M-01）；Lead 对照 Issue 原文确认无遗漏后进入 P0。
4. Lead 建分支 research/concorde-metaopt；A3 完成仓库基线审计后，Lead 提交 .gitignore、计划文档（docs/planning/）与基线。
5. A1 执行 P0 审计（只读）并产出 audit run 目录；A5 独立复核审计代码与证据；A2 做只读预检（doctor、版本）；A4 起草首轮回执。
6. Lead 组织 G0 评审 → 用户 R1：确认几何路线（D2）、GitHub 发布授权（D1）。
7. 进入 P1，按 §3 循环推进 P1–P6；每阶段结束按 §11 门禁与人工审核点汇报。
8. 每阶段回执由 A4 起草→Lead 审阅→用户批准→Lead 发布到 Issue #1；PR 与最终报告按 §9 执行。
9. 全部 Phase I 完成后，Lead 汇总最终报告（软件/物理/统计分开）并维持仓库整洁。

---

## 14. 用户审阅与审批决议（2026-10-27 已确认）

| 编号 | 事项 | 决议 |
|---|---|---|
| T1 | 角色设置 | **批准，并增加 A5 独立代码审查角色**（Lead+5 成员） |
| T2 | 合规/发布 | 批准；A4 生成报告后由 Lead 审阅后提交（GitHub 写由 Lead 执行） |
| T3 | 记忆与文档 | 批准；AI 文档放仓库外（当前沙箱限制→outputs/agent-worklog/，gitignored）；团队计划可移入 docs/ |
| T4 | GitHub 自动化 | 批准；A4 起草→Lead 审阅→等用户明确批准→再发布 |
| T5 | 执行节奏 | 批准；完成当前 Issue 下全部工作（P0–P6） |
| T6 | 预算审批 | 接受；分阶段申请（P3 先 64 次；P6 先 3 组×2 种子×60 次） |

剩余待用户批准项：① P0 回执发布（R1）；② P3/P6 等正式运行预算（T6）；③ PR 创建/合并（如需）。

---

## 15. 关联文档

- 阶段执行计划：phase1_followup_plan_2026-10-27.md（P0–P6 详细步骤、预算草案、风险）
- 本团队计划入库路径（批准后）：docs/planning/agent_team_plan.md
- Issue #1（GitHub，QingYangJin/RCAIDE_Supersonic）
- 历史证据：D:\CodexMemory\RCAIDE\{migration-20261023, multifidelity, concorde-mesh-export-20261026, cfd-quality-audit-20261026}；outputs/project-analysis/
