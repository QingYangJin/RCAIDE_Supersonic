# RCAIDE_Supersonic · Issue #1 后续执行计划（v0.1）

- 日期：2026-10-27（Asia/Shanghai）
- 仓库：QingYangJin/RCAIDE_Supersonic（AGPL-3.0，默认分支 main）
- 依据：仓库主页 README、Issue #1《[METAOPT-00] 研究总控与第一阶段：Concorde 15维固定巡航优化、MAML-A验证及智能体交接》（open，0 comments）、本机只读环境/源码审计
- 状态：待用户确认的草案。本文件位于 git-ignored 的 outputs/plans/；确认后可移入 docs/ 并提交。本文件不是 AI 记忆日记，属 Issue 允许的“人为审核技术协议/计划文档”。

---

## 0. 阅读结论

### 0.1 仓库主页
- 定位：基于 RCAIDE-LEADS 1.5.0 的独立超声速研究/教程工作区（非上游源码镜像），AGPL v3 并保留上游署名；含 examples/、tutorials/、digital_hangar/、installation/、docs/。
- 工程事实：Windows + Python 3.11，入口 run_rcaide.cmd；不提交 envs/、outputs/ 与长时运行目录。
- 当前验收范围（README，2026-10-26）：pip check、标准大气 100 点、三个高度失速速度、VTK/GUI 主模块导入通过；明确不宣称 Mission/优化/MAML 已验收。
- 上游基线提交 5d80bd5006828c967cc8d3425e29a9b3a3385608；本地提交到 ec65e5a（并行 DE worker 隔离），工作区仅有未提交的 .gitignore 改动。

### 0.2 Issue #1（执行合同）
- 研究主题：面向超声速飞行器的多保真、少样本、元学习辅助总体设计优化；用 MAML 少步适应提高昂贵黑箱优化的评价效率。
- Phase I 冻结问题：Concorde 类固定拓扑、固定单一超声速巡航段与发动机/装载/起始质量，仅优化 15 个机翼/垂尾/机身变量，最小化该段燃油量 fuel_burn_kg = mass_start_kg − mass_end_kg；约束统一写为 g_j ≤ 0；失败（geometry_invalid/solver_failed/non_converged）必须与“已求解但违约”分开记账，禁止把失败伪装成目标值喂给神经网络。
- 阶段顺序（合同原文）：P0 只读审计 → P1 15维几何 → P2 固定巡航评价器 → P3 DOE/多保真 → P4 普通约束 BO/DE 基线 → P5 MAML-A → P6 同预算对照；Phase II–IV 暂不执行。
- 强制交付目录 research/concorde_metaopt/（CLI、configs、tasks、aircraft、evaluation、data、optimization、learning、reports、tests、optimization_runs）。
- 结果发布：每次运行落 research/concorde_metaopt/optimization_runs/<run_id>/，summary.json / evaluations.jsonl / figures 等小文件随 PR 提交；原始 SU2 网格/流场/长日志放 outputs/concorde_metaopt/<run_id>/ 并写入 data_manifest.json（路径/hash/审查结论）；禁止 AI 记忆 Markdown、token、私密绝对路径进仓库。
- 每轮回执需按 Issue §6 字段（阶段/状态/分支与 SHA/代码路径/复现命令/测试与真实 Mission 证据/DOE 与真实调用数/预算与墙钟/产物路径/CFD 原始文件位置与 SHA256/物理局限/未完成项）。

### 0.3 本机只读审计摘要（已完成部分）
- 项目环境：D:\RCAIDE\envs\RCAIDE\python.exe（Python 3.11.17）；run_rcaide.cmd 以 -E -s -B 运行并设置 MPLCONFIGDIR=outputs/matplotlib-cache。
- 关键包：RCAIDE-LEADS 1.5.0、rcaide-gui 1.2.0、maml-opt 0.1.0、rcaide-multifidelity 0.1.0（导入名 rcaide_cfd）、rcaide-cpacs 0.1.0、numpy 2.4.6、scipy 1.17.1、torch 2.8.0（CPU 版，cuda 不可用）、scikit-learn 1.9.1。
- 外部工具：SU2 v8.5.0（SU2_CFD.exe）、Gmsh 4.15.2（gmsh.exe）、OpenVSP 3.26.1 win64 Python3.9（vsp.exe + py3.9 API）。RCAIDE 3.11 环境内无 gmsh/openvsp 的 Python 绑定（导入失败）。
- 复用资产：maml-opt 完整 API（contracts/initialization/bayesian/campaign/evaluation/learning、RcaideBackend 适配器、CLI 只做审计不启动仿真）；rcaide_cfd 已验证固定几何 RCAIDE/OpenVSP/Gmsh/SU2 Euler 链路（63 tests 通过，仅直梯形翼首版、仅 Euler 无粘、仅 CL 配对）；D:\CodexMemory\RCAIDE 下有 Concorde 全机/主翼网格导出、CFD 质量审计、旧迁移与 MAML 研究日志（需重核后引用）。
- 既有 Concorde 教程：13 段任务（climb_1..5、climbing_cruise、level_cruise 60,000 ft / 4500 nmi、descent_2/3/4），起飞 185,000 kg、max_fuel 95,680 kg、design_mach 2.05；另有一套 3 变量 DE 优化教程（1225 次评价预算，历史最好可行 7800.66 kg，约 8 小时跑完 1218 次，未收敛）。
- 当前缺口：仓库无 research/ 目录；无分支/PR；Issue 0 条评论；.gitignore 改动未提交；.agents/ 下有 token 文件（已计划忽略）。

---

## 1. 总体判断与策略

Issue #1 本身已经把“做什么、交付什么、怎么验收”写得很细。真正缺的是：

1. **落地排序与门禁**：把 P0–P6 拆成可执行、可复审、可中断的小步。
2. **本机现实与合同要求的差距处置**：15 维几何驱动、Mach 2 保真度、CFD 收敛、maml-opt 复用、计算预算。
3. **GitHub 协作方式**：分支、草稿 PR、每阶段 Issue 回执。

策略：两条主线并行、先闭环后扩展。

- 主线 A（几何/评价链）：P1 15D 参数化 → P2 单巡航 Mission 评价器 → P3 DOE 与保真度。
- 主线 B（优化/学习链）：P4 普通约束 BO 基线 → P5 MAML-A → P6 同预算对照；B 依赖 A 的 evaluate()，但数学函数级测试可提前。
- 先低后高：先以 RCAIDE Mission（经验/低保真阻力）闭环，CFD 仅做小规模适用性验证；未打通 SU2→Mission 前不宣称“高保真整段燃油优化”。
- 每阶段以“代码 + 仓库内优化运行产物 + Issue 回执 + 门禁评审”收口；失败/负结果同样如实提交。

---

## 2. 现状 vs Issue 差距清单

| # | 维度 | Issue 要求 | 本机现状 | 处置阶段 |
|---|---|---|---|---|
| G-01 | 代码骨架 | 强制 research/concorde_metaopt/ 全套模块 | 尚无 research/ 目录 | P0 建骨架（先 audit 子命令，不写伪实现） |
| G-02 | 15D 几何驱动 | 驱动 OpenVSP 与 RCAIDE 真实几何 | 3.11 无 openvsp/gmsh 绑定；py3.9 OpenVSP API 可用；rcaide_cfd 原生仅接受直梯形翼 | G0 决策（见 D2）；P1 实施 |
| G-03 | 固定单巡航任务 | 冻结单一超声速巡航段及发动机/装载/起始质量 | 现有 Concorde.py 为完整 13 段任务；level_cruise 参数需抽取并验证 | P2 抽取并冻结 TaskSpec |
| G-04 | 高保真链 | SU2 Euler/RANS + 回传 RCAIDE Mission | rcaide_cfd 仅 Euler 无粘、固定几何、仅 CL；全机 Concorde Euler 曾 NOT_CONVERGED（2026-10-26 证据） | P3 小规模验证 + 明确范围声明 |
| G-05 | maml-opt 复用 | 复用真实响应网络/训练/适应/初始化器 | 安装包 API 完整；源码目录未定位；旧 13 维应用未定位 | P0 审计；P4/P5 以安装包为准并记录 hash |
| G-06 | 旧应用差异 | 核对旧 13 维/single_cruise 与新 15 维 | 仅找到 3 变量 DE 教程，未见 13 维应用 | P0 搜索并给出“可复用/不可复用”结论表 |
| G-07 | 预算与机时 | 正式 BO 100–150 真评价/场，需实测与批准 | 3 变量 DE 1218 次≈8h（10 worker、60% CPU 上限） | P2 实测单次耗时；P4 冻结预算（D3） |
| G-08 | GitHub 协作 | 分支/PR/每轮回执 | 无分支、无 PR、Issue 0 评论 | D1 批准后建分支 + 草稿 PR + 回执 |
| G-09 | 仓库卫生 | 禁止 AI 记忆 md、token、大文件 | .gitignore 改动未提交；token 文件在 .agents/ | P0 提交 .gitignore + 提交前扫描 |
| G-10 | 结果发布 | 运行产物入库、原始 CFD 在 outputs/ + manifest | 旧证据散落 D:\CodexMemory；research/ 尚未建立 | P0 起统一 run 目录 schema |

---

## 3. 阶段计划

### P0 · 只读审计与骨架（0.5–1 天）
目标：证明“工具链与源码可复用性”，建立最小可运行骨架，产出第一轮回执素材；不做仿真、不写物理 PASS。

步骤：
1. 分支：git switch -c research/concorde-metaopt；提交 .gitignore（/.agents/ 等）；确认 research/ 不被忽略。
2. 建 research/concorde_metaopt/ 骨架与 cli.py audit 子命令（只读）。
3. audit 证据清单：
   - git HEAD/status/branch、Python 版本、pip check、关键包版本与 direct_url/hash；
   - rcaide_cfd doctor 输出、gmsh/SU2/OpenVSP（py3.9 导入）版本；
   - maml_opt API 表（模块/类/函数签名）+ 包内测试（163 passed）与 rcaide_cfd 测试（63 passed）实跑记录；
   - Concorde.py 结构表：主翼 4 段、垂尾 3 段、机身 10 段、segment_6 是否重复、折点/弦长/扭转、面积/质量/参考量派生链、level_cruise 参数；
   - 旧 13 维/single_cruise 应用搜索结论（D:\CodexMemory\MAML元学习、D:\MAML-Opt、migration-20261023）。
4. 产出 research/concorde_metaopt/optimization_runs/<audit_run_id>/{environment.json,summary.json,evidence/} 与人类可读审计表 README.md。
5. 阻断清单分级：立即阻断 / 阶段阻断 / 风险。
门禁 G0：审计可重跑、字段齐全、结论分“已验证/未验证”，并确定 D2 路线。

### P1 · 15 维参数化与真实几何（2–3 天）
- 交付：configs/design_space_15d.yaml（顺序/单位/基准/实测收缩边界）、configs/task_fixed_cruise.yaml（占位）、aircraft/geometry_builder.py、geometry_checks.py、concorde_adapter.py、tests/test_geometry_15d.py、CLI geometry-check --all-variables。
- 要点：主从关系更新翼展/弦长/湿面积/机身截面容积/部件布置；派生量单一来源；Concorde 无水平尾翼，不凑维数；usable_volume>=required_volume 作为约束。
- 验收：15/15 变量均有可测几何/派生量响应（effect matrix + CSV/JSON + PNG）；每变量 ±扰动；折点有序、弦长正、闭合、截面唯一、无干涉、垂尾连接。
门禁 G1：不存在“只改字段、网格没变”的变量；否则列 blocked 并请求决策。

### P2 · 固定单巡航评价器（2–3 天）
- 交付：tasks/task_spec.py、evaluation/contract.py、evaluation/mission.py、ledger.py、CLI smoke/doe 骨架、tests/test_task_and_evaluation.py。
- 要点：从 Concorde.py 抽取 level_cruise 单段并冻结 Mach/高度/距离/载荷/起始质量/推进；每次评价独立创建 Aircraft/Mission；fuel_burn=mass_start−mass_end；约束全部 g_j≤0；失败与违约分离；缓存/预算硬停止。
- 验收：基准 Mission ≥3 次重复（记录实测差异，若确定性则要求逐位一致）；单变量扰动真评价；玩具后端测试缓存/预算/失败处理/序列化；实测单次评价墙钟 → 预算表。
门禁 G2：评价器可重复、任务闭合、summary/evaluations 与原始评价一致。

### P3 · DOE 与保真度（3–4 天，CFD 风险最高）
- 交付：data/generate_doe.py、schema.py、validate_dataset.py、evaluation/low_fidelity.py、high_fidelity.py、data_manifest.json、pytest 与适用性报告。
- 要点：LHS/Sobol 32 → 128（先几何合法性，再按批准预算真实评价）；VLM/VSPAERO 在 Mach 2 实测适用域，超域只做声明域内筛选；SU2 用已有 Concorde 网格做 1–3 工况 + 3 档网格趋势，核对 CL/CD/Cm、参考量、收敛；失败单独记账；模型不可信时停止扩充。
- 验收：dataset_manifest 含来源/版本/真实调用数/失败数/适用性结论；不宣称高保真整段油耗。
门禁 G3。

### P4 · 普通约束 BO/DE 基线（2 天）
- 交付：optimization/baseline_bo.py、baseline_de.py、initializer.py、evaluation/contract.py 适配、tests/test_bo_toy.py、convergence.png/feasibility_rate.png。
- 要点：先 Branin/Ackley+约束数学测试，再接 Concorde；复用 maml_opt.bayesian/campaign 的约束 GP/预算接口，不足则写适配层并说明；smoke ≤5、BO ≤30；DE 复用现有 3 变量代码改同一 15 维 evaluate 接口。
- 验收：真实闭环、预算硬停止、JSON 与 PNG 一致。
门禁 G4；据此冻结正式 BO 预算（D3）。

### P5 · MAML-A 实验链（3 天）
- 交付：learning/*、data/meta_tasks.py、optimization/maml_a_bo.py、tests/test_no_data_leakage.py、tests/test_bo_toy.py 扩展。
- 要点：审计并复用真实 maml_opt 学习 API；首版用“仅训练数据拟合的 GP”合成有标注元任务（只证明少样本算法效果，不冒充物理迁移）；S/Q 按完整任务身份划分；对照 GP/MLP/预训练+微调；支持集少步梯度更新必须有实际代码与证据；A 只影响初始设计，预测标签不得进入 BO。
- 验收：适应前后预测/选点确有变化；与普通微调差异可解释；无数据泄漏。
门禁 G5。

### P6 · 同预算对照与报告（3–5 天 + 机时）
- 交付：P6 运行目录、汇总表与 PNG、技术报告（软件验收/物理验收/统计结论分开）、PR 与回执。
- 要点：对照 Sobol/LHS 初始、历史检索/历史 GP、预训练+微调、MAML-A，另加历史最佳直接复用；后续 BO/预算/权限一致；先 2 种子调试，正式预算按 G2 实测与 D3 批准；主指标为真实评价成本—最佳可行油耗、首次可行成本、可行率、失败重试与累计成本；代表设计按对称规则 SU2 复核（若链路可用）；即使 MAML 无收益也完整提交。
门禁 G6（关闭条件）。

---

## 4. 协作、提交与发布规范

- 分支：research/concorde-metaopt（长期集成分支）→ 草稿 PR 到 main；每阶段小步 commit。
- 提交前检查：无 envs/、outputs/、token、AI 记忆 md、大文件；research 测试通过；git diff --check。
- Issue 回执：严格按正文 §6 字段，每阶段一条；P0 完成先发“启动回执”（需 D1 批准后再发）。
- 结果 schema：summary.json / evaluations.jsonl / index.json / figures 严格按 Issue 要求；无可行点时写 null，不伪装数值。
- 原始 CFD：outputs/concorde_metaopt/<run_id>/，data_manifest.json 记录相对路径/hash/审查结论/访问方式，注明远程不可复核。
- 复用证据：D:\CodexMemory\RCAIDE\migration-20261023、multifidelity、concorde-mesh-export-20261026、cfd-quality-audit-20261026 与 outputs/project-analysis/ 的旧审计，引用前必须重核并标注日期/版本。

---

## 5. 预算草案（分阶段批准，先测量后冻结）

| 阶段 | 真实 Mission 次数 | SU2 次数 | 墙钟估算 | 说明 |
|---|---|---|---|---|
| P0 | 0 | 0 | 0.5–1 天 | 纯审计 |
| P1 | 0 | 0 | 2–3 天 | 几何测试不跑 Mission |
| P2 | 8–12 | 0 | 2–3 天 | 重复性 + 扰动 |
| P3 | 32–128（建议先 64） | 4–8 | 3–4 天 | DOE 候选先合法性过滤 |
| P4 | 35–50 | 0 | 2 天 | smoke 5 + BO 30 + DE 小预算 |
| P5 | 10–20（集成） | 0 | 3 天 | 合成元任务为主 |
| P6 | 480–1200 | 2–4 | 3–5 天 + 20–40h 机时 | 5 组 × 2–3 种子 × 60–100 次 |
| 合计 | ≈565–1410 | 6–12 | 约 3–4 周 | 正式 P6 前先用 2 种子 60 次试跑 |

建议：P6 先用 3 组（Sobol 初始、预训练+微调、MAML-A）× 2 种子 × 60 次 = 360 次；有信号再扩到全对照。所有正式大规模运行前单独申请批准。

---

## 6. 风险登记册

| # | 风险 | 证据/触发 | 缓解 |
|---|---|---|---|
| R1 | 15 维几何“假参数化” | 字段变、几何/派生量不变 | P1 effect matrix 强制验证；不通过即 blocked |
| R2 | OpenVSP/Gmsh 无 3.11 绑定 | 导入失败；rcaide_cfd 走 py3.9 worker | G0 选路线：RCAIDE 原生主路径 + py3.9 OpenVSP 导出/复核 |
| R3 | rcaide_cfd 不支持 Concorde 全机 | 首版仅直梯形翼、仅 CL | 不假装打通；VSP3/已有 SU2 网格 + 范围声明；必要时缩到主翼单点验证 |
| R4 | Mach 2 下 VLM/VSPAERO 不适用 | 适用性实测未做 | 仅在声明域内做低保真筛选；结论写入报告 |
| R5 | 全机 Euler 不收敛 | 2026-10-26 诊断流 NOT_CONVERGED | P3 预留调参时间；失败不留假标签；必要时降级到主翼/2D 截面 |
| R6 | 计算预算超支 | 3 变量 DE 已 8h/1218 次 | 分阶段预算、硬停止、先测单次成本再冻结 |
| R7 | maml-opt 源码缺失/漂移 | 仅 site-packages；hash 可核 | 以安装包为权威并记录 wheel hash；不修改第三方包 |
| R8 | 元任务外部效度不足 | 首版只能合成 GP 任务 | 报告明确“算法级验证，非物理迁移”；Phase II 再做真实任务族 |
| R9 | 数据泄漏 | 同任务跨 split、预测标签入 BO | 按完整任务身份划分 + 自动测试 |
| R10 | 长跑中断 | 8h 级 DE 曾中断/未落盘 | 原子写、ledger、缓存、小步运行 |
| R11 | 仓库卫生/凭证 | token 文件、AI 记忆 md | 提交前扫描；.gitignore 先行 |
| R12 | GitHub 写操作未授权 | 无分支/PR，token 在本地 | 先获 D1 批准；issue_comment 走审批 |

---

## 7. 时间表（相对工作日，含人工门禁）

| 里程碑 | 阶段 | 产出 | 估算 | 门禁 |
|---|---|---|---|---|
| M0 | P0 | 审计 run 目录 + 审计表 + 回执草案 | D0–D1 | G0 + D1/D2 确认 |
| M1 | P1 | 15D YAML + 几何生成/检查 + 31 测试 + effect matrix | D2–D4 | G1 |
| M2 | P2 | TaskSpec + evaluate() + 重复性 + 单次耗时 | D5–D7 | G2 + D3 预算决策 |
| M3 | P3 | DOE + 低/高保真小规模验证 + data_manifest | D8–D11 | G3 |
| M4 | P4 | 数学测试 + Concorde BO/DE 小预算闭环 | D12–D13 | G4 |
| M5 | P5 | 合成元任务 + MAML 训练/适应 + A 初始化 | D14–D16 | G5 |
| M6 | P6 | 同预算对照 + 报告 + PR/回执 | D17–D21+ | G6 |

（CFD 调试与正式 P6 机时可能拉长 3–5 天；每阶段结束请求用户审核后进入下一阶段。）

---

## 8. 需要用户现在确认的决策

- D1 GitHub 授权：是否允许创建 research/concorde-metaopt 分支、提交代码、开草稿 PR，并在 Issue #1 发布 P0 启动/完成回执（需要 token 权限与审批）。
- D2 几何路线：A) RCAIDE 原生 15D 构造 + py3.9 OpenVSP 作为导出/复核（推荐，先闭环）；B) 完全走 OpenVSP VSP3 参数化（更贴合同原文，工具链风险大）；C) 先只做 RCAIDE 原生，OpenVSP 延后。
- D3 计算预算：P3 真实 Mission 上限（建议先 64）、P4/P6 每场预算（建议 smoke 30 → 正式 60–100 × 2 种子）、是否接受约 20–40h 机时；正式运行前再单独确认。
- D4 元任务：首版仅合成 GP 元任务是否满足第一阶段验收（Issue 已允许，但需明确写入回执），还是要求同时构造 Mach/高度/载荷不同的物理任务变体（注意 Issue §7 将真实跨任务迁移列为 Phase II）。
- D5 计划文档：确认后是否把本文件移入 docs/ 并在 PR 中提交（vs 仅保留本地 outputs/）。

---

## 9. 立即可执行的下一步（收到确认后）

1. D1/D2 确认 → 建分支、提交 .gitignore、创建 research/concorde_metaopt/ 骨架与 audit CLI。
2. 执行 P0 只读审计（0.5–1 天），产出 environment.json/summary.json/审计表与阻断清单。
3. 起草 Issue #1 第一轮回执（P0 启动/完成），经用户批准后发布；同时开草稿 PR。
4. 依据 G0 结论进入 P1。
