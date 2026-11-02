# FULLCHAIN-A4-ACCEPTANCE-MATRIX — D-12D-002 P1–P3 全链路验收对照矩阵

> 生成者：A4（a4-issue-liaison，只读角色）｜生成时间：2026-10-31（Asia/Shanghai）｜任务：task-29 FULLCHAIN-A4-ACCEPTANCE-MATRIX
> 本文件是事实对照矩阵，不是验收签字；A4 未运行任何求解器、未写 GitHub、未写仓库、未 spawn 子智能体。

## 0. 数据源、快照与读取边界

| 来源 | 路径/标识 | 快照时间 | 说明 |
|---|---|---|---|
| Issue #4 | GitHub API 只读快照 pre0/issue4.json（32,159 B） | 2026-10-31T03:35:23Z（updated_at） | state=open；comments=7；author=QingYangJin |
| Issue #4 评论 | pre0/comments.json（60,758 B，7 条） | 同上 | D-12D-002：id=6538481816、created_at 2026-10-31T03:35:23Z、正文 6,401 字符（pre0/d12d002_body.txt） |
| PR #3 | pre0/pr3.json（22,469 B） | head=048ef2e55f389b0ae52e8872131dcfcf0c91a1eb；updated_at 2026-10-30T11:28:23Z | state=open、merged=false、draft=false、commits=34、changed_files=258；policy=保持 Open 不合并 main |
| 被审 run 目录 | research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z/ | 2026-10-31T04:07:14Z→09:44:53Z | summary.status=EXECUTED_NO_GATE_APPROVED；base_commit=048ef2e5…；无 gate 通过 |
| 验证报告 | docs/reviews/p1p3_fullchain_validation_report_20261031.md | 存在，13,650 B | A4 仅登记存在性与大小；逐段复核属 A5/A2 |
| 原始产物 | outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/ | 存在 | 195 files / 108,824,422 B；仓库外；raw_artifacts_manifest.json 以 sha256 索引 |
| 本地 Git（只读实测） | D:/RCAIDE | 2026-10-31T10:06:51.358Z | HEAD=d80b4c485d689082cd117f09ec6445a181dd458c；branch=research/concorde-metaopt；porcelain 变更条目=22；HEAD 提交主题=P1-P3: execute D-12D-002 capped full-chain validation (23/23 starts, no gate approved) |

读取边界与限制：

- A4 未从原始求解器日志独立重算数值（A2 职责），未独立复跑测试/算法（A5 职责）；本矩阵依据 run 目录结构化证据、账本、manifest 与报告存在性。
- run 的 summary.json 明示 review.a1..a5 = PENDING（独立角色审阅待完成）；A4 本矩阵不能替代独立审阅。
- run.base_commit=048ef2e5… 与 pre0 快照的 PR #3 head 相同；本地 HEAD=d80b4c485d689082cd117f09ec6445a181dd458c（run 提交/证据目录的推送与 PR 更新仅由 L 执行）。
- GitHub 写操作 0；仓库写操作 0；求解器进程启动 0；本文件位于项目外记忆目录。

## 1. 一次性授权与预算核对（D-12D-002 §1）

| 项目 | 授权上限 | 实际（账本/评估记录） | 判定 |
|---|---|---|---|
| 数值分析启动总数 | 23 | 23（used=23, remaining=0） | PASS（用尽，符合停止原则） |
| VSPAERO Thin/LF | 6 | 6（NA-001..006） | PASS |
| RCAIDE 单巡航/LF | 4 | 4（NA-014..017） | PASS |
| SU2 Euler/HF | 6 | 6（NA-018..023，含 2 次配置尝试与 1 次失败） | PASS（计数合规） |
| OpenVSP WaveDrag/面积律 | 7 | 7（NA-007..013，含 1 次结果丢失重跑） | PASS |
| 墙钟 ≤30 h | 30 h | 04:07:14Z→09:44:53Z = 5 h 37 min 39 s（ledger deadline 2026-11-01T10:07:14Z） | PASS |
| 串行、单机、≤4 CPU 核 | 串行 | 账本 serial；VSPAERO -omp 4；SU2 mpiexec -n 4；未并行 | PASS |
| 内存 ≤可用物理 RAM 约 70% | 31.05 GB×70%≈21.8 GB | 主机 RAM 31.05 GB、free 16.41 GB、run 预算目标 14 GB | PASS |
| 网格生成与导出另记 CPU/内存/磁盘/时长/网格数 | 必须另记 | ledger.mesh_generation_events=[]（0 条），而 HF 网格确已生成（coarse/medium/fine） | GAP（见 GAP-08） |
| 审批来源注记 | run_config/账本注 Issue #4 / D-12D-002 | run_config.approval.source=Issue #4 / D-12D-002 (comment 6538481816)；ledger.approval_source 同 | PASS |
| 失败/重试计数、禁用缓存冒充求解 | 必须 | evaluations.jsonl 23 行全部 billable=true；HFS-SETUP-01/02、HFS-01、WAVE-00（LD-002）均计入；cache_hit=0 | PASS |

结论：预算与计数合同执行合规；唯一账本缺口是网格生成事件未记录（物理求解计数完整）。23/23 用尽后任何新求解均需 owner 新预算。

## 2. 23 次实际启动 → case → 证据 → 可用性

| 事件 | 实际 case | 类别 | 状态 | wall (s) | 主要证据文件 | 证据可用性/结论 |
|---|---|---|---|---|---|---|
| NA-001 | LFV-00 baseline | VSPAERO_LF | SOLVED | 5.0 | lf_vspaero_results.json cases.LFV-00 + polar | 已解析；但物理结论 NOT_VALIDATED（CDi 符号翻转） |
| NA-002 | w01_plus1pct（LFV-01） | VSPAERO_LF | SOLVED | 4.577 | 输出隔离 EXT/lead/failed_runs，不入证据 | 作废：LD-001 模板缺陷，3 次启动已计数 |
| NA-003 | w03_plus1deg（LFV-02） | VSPAERO_LF | SOLVED | 4.595 | 同上 | 作废（LD-001） |
| NA-004 | w10_plus2（LFV-03） | VSPAERO_LF | SOLVED | 4.213 | 同上 | 作废（LD-001） |
| NA-005 | SENS-A 8×17 面元 | VSPAERO_LF | SOLVED | 2.535 | lf_vspaero_results.json cases.SENS-A | 有效（密度敏感性） |
| NA-006 | SENS-B 32×65 面元 | VSPAERO_LF | SOLVED | 12.359 | cases.SENS-B | 有效（密度敏感性；与 NA-005/LFV-00 对比 65× 非收敛） |
| NA-007 | WAVE-00 基准（Eminton-Lord） | WAVE_AREA_RULE | SOLVED | 0.166 | 结果丢失（LD-002），仅计数 | 非证据（已计数） |
| NA-008 | WAVE-00R 基准重跑 | WAVE_AREA_RULE | SOLVED | 0.168 | wave_drag_area_rule.json analytic_benchmark | 有效：Sears-Haack 误差 -1.55e-6（port）/-1.61e-6（OpenVSP），PASS |
| NA-009 | WAVE-01 基准主翼单独 | WAVE_AREA_RULE | SOLVED | 4.27 | cases.WAVE-01 | 有效但离散未收敛（36×200） |
| NA-010 | WAVE-02 基准主翼+固定机身 | WAVE_AREA_RULE | SOLVED | 6.721 | cases.WAVE-02 | 有效但离散未收敛 |
| NA-011 | WAVE-03 W03+1° 主翼单独 | WAVE_AREA_RULE | SOLVED | 4.187 | cases.WAVE-03 | 有效（扰动对） |
| NA-012 | WAVE-04 W03+1° 主翼+机身 | WAVE_AREA_RULE | SOLVED | 6.748 | cases.WAVE-04 | 有效（扰动对） |
| NA-013 | WAVE-05 基准翼身 72×800 加密 | WAVE_AREA_RULE | SOLVED | 259.072 | cases.WAVE-05 | 有效但 NOT_CONVERGED（fine/coarse=2.8666） |
| NA-014 | LFV-04 V01+1% | RCAIDE_LF | SOLVED | 79.485 | mission_e2e.json cases.LFV-04 | 有效：fuel 34117.7517 kg，Δ +8.2692 kg (+0.02424%) |
| NA-015 | LFV-05 V02+2° | RCAIDE_LF | SOLVED | 79.455 | cases.LFV-05 | 有效：fuel 34109.7074 kg，Δ +0.2249 kg (+0.00066%) |
| NA-016 | E2E-00 基准整链 | RCAIDE_LF | SOLVED | 80.232 | cases.E2E-00 + archive_reproduction_check | 有效：34109.4826 kg，与归档 smoke-1612 完全一致（diff 0.0） |
| NA-017 | E2E-01 W10+2° 整链 | RCAIDE_LF | SOLVED | 79.771 | cases.E2E-01 | 有效：34117.5553 kg，Δ +8.0727 kg（与归档一致） |
| NA-018 | HFS-SETUP-01 配置尝试 | SU2_HF | FAILED_CONFIG_PARSE | — | evaluations.jsonl（post-hoc） | 非证据；CONV_CRITERIA 对 SU2 8.5.0 非法，0 迭代；已计数 |
| NA-019 | HFS-SETUP-02 配置尝试 | SU2_HF | SOLVED_VOID_CONVERGENCE | — | evaluations.jsonl（post-hoc） | 非证据；MARKER_MONITORING 缺失致 CL/CD=0，residual 仅 -1.53；已计数 |
| NA-020 | HFS-00 楔形基准 | SU2_HF | SOLVED | 116.0 | hf_su2_results.json wedge_benchmark | PARTIAL：壁压比误差 -0.419%，激波角差 1.59–2.05° > 1° 容差 |
| NA-021 | HFS-01 粗网格 | SU2_HF | FAILED | 1.0 | hf_su2_results.json wing_cases.HFS-01 | 失败：ASCII 网格边界 VTK type 3(line) 而非 5(triangle)，转换器缺陷；已计数 |
| NA-022 | HFS-02 中网格 | SU2_HF | SOLVED | 394.0 | wing_cases.HFS-02 | 有效：CL 0.0927766、CD 0.006819724、CMy -0.0380761；力稳定 |
| NA-023 | HFS-03 细网格 | SU2_HF | SOLVED | 871.0 | wing_cases.HFS-03 | 有效：CL 0.0954768、CD 0.007117048、CMy -0.0394070；力稳定 |

计划内未执行/被替换的 case：

| 计划 case | 计划内容 | 实际状态 | 原因 |
|---|---|---|---|
| HFS-00R | 楔形网格复核 | NOT_RUN | SU2 类别 6/6 用尽（含 2 次配置尝试、1 次 HFS-01 失败）；D-12D-002 禁止提高分类上限 |
| HFS-04 | W10 tip_twist +2° Euler 复算 | NOT_RUN | 同上 |
| WAVE-06 | 基准成对加密第 2 次（planned） | 未执行 | 同类别额度被 WAVE-00R 基准重跑占用（D-12D-002 允许同类别一次必要重试） |
| LFV-01/02/03 | W01/W03/W10 扰动 VSPAERO | 已启动但证据作废 | LD-001 模板缺陷（键值未写 '='）；输出隔离、未作证据；3 次启动已计数 |
| LFV-SENS-A/B | 涡格/面元密度敏感性 | 已执行 | SENS-A 8×17、SENS-B 32×65；用于收敛性判断 |

## 3. 必备交付物核对（D-12D-002 §4）

| 必备文件 | 状态 | 大小/内容 | 判定 |
|---|---|---|---|
| run_config.json | 存在 | 17,235 B；approval/case_plan/gates/冻结条件齐全 | PASS |
| environment.json | 存在 | 4,069 B；Python/RCAIDE 1.5.0/OpenVSP 3.26.1/VSPAERO 6.2.0/SU2 8.5.0/Gmsh 4.15.2、OS/资源 | PASS |
| approval_and_budget_ledger.json | 存在 | 32,677 B；23 events + policy_events；totals 23/23 | PASS（网格事件缺，见 GAP-08） |
| geometry_validation.json | 存在 | 3,438 B；W10 twist 检查、状态 GEOMETRY_VALIDATED_WITH_WARNINGS | PASS（PARTIAL 结论见 §5） |
| lf_vspaero_results.json | 存在 | 23,692 B；LFV-00..03+SENS-A/B、comparison、assessment、harness_defect | PASS（物理结论 NOT_VALIDATED） |
| hf_su2_results.json | 存在 | 15,650 B；wedge、HFS-02/03、mesh_convergence、not_run、verdict | PASS（HF PARTIAL） |
| mesh_convergence.csv | 存在 | 562 B | PASS（仅 2 档，无第三档） |
| wave_drag_area_rule.json | 存在 | 32,406 B；analytic_benchmark、WAVE-01..05、resolution_sensitivity、increment、verdict | PASS（NOT_VALIDATED） |
| drag_component_ledger.json | 存在 | 8,868 B；N/CD、参考量、去重规则、缺项、verdict | PASS（PARTIAL_DATA_NOT_VALIDATED） |
| mission_e2e.json | 存在 | 26,573 B；E2E-00/01、LFV-04/05、归档复现、q 注记、budget_accounting | PASS（MISSION-DATA PARTIAL） |
| evaluations.jsonl | 存在 | 11,295 B，23 行，全部 billable=true | PASS |
| summary.json | 存在 | 7,285 B；budget/gates/results/not_approved | PASS |
| blocker_register_current.json | 存在 | 4,636 B；9 条 blocker（B-LF-VSPAERO-MACH2、B-LF-RCAIDE-EMPIRICAL、B-HF-WEDGE-PARTIAL、B-HF-GRID-2LEVEL、B-HF-INVISCID-WING-ONLY、D-BODY-4-BODY-CORR-MISSING、B-BUDGET-EXHAUSTED、B-MISSION-Q-MISMATCH、B-GEO-BOUNDS-PROVISIONAL） | PASS |
| data_manifest.json | 存在 | 11,770 B；59 files/1,181,000 B + input_source_files 6 + raw 195/108,824,422 B | PASS |
| figures/*.png | 存在 | 7 张：drag_component_bookkeeping、lf_vspaero_density_sensitivity、mission_e2e_fuel_deltas、su2_wing_force_convergence、su2_wing_mesh_sensitivity、wave_area_rule_results、wave_area_rule_validation | PASS |
| 可复现命令/环境 | 存在 | scripts/ 35 个文件 + README.md 16,432 B + toolchain_capability_probe.json | PASS |
| 报告 docs/reviews/p1p3_fullchain_validation_report_20261031.md | 存在 | 13,650 B | PASS（A5/A2 独立复核待） |
| 大网格/场数据 outputs/ + hash 索引 | 存在 | raw_artifacts_manifest.json：195 files / 108,824,422 B / archive_root 仓库外 | PASS |
| AI 记忆/私有日志在仓库外 | 本矩阵位于项目外记忆目录；run 目录未见 AI 记忆 | 抽样核对 | PASS（仓库卫生终审属 A3） |

## 4. 预先声明验收标准覆盖（D-12D-002 §3）

| 验收标准 | 具体要求 | 证据 | 判定 | 缺口/说明 |
|---|---|---|---|---|
| 几何 | 12D→完整几何一致；W10 扭转传到 VLM/OpenVSP/HF 翼面；V01/V02 真实灵敏度或明示无作用；标注遮挡/湿面积残差 | geometry_validation.json：W10 +2° 最大 dz=0.03396196 m（与模型期望差 <1e-6）、dy=0、2388 顶点移动、DegenGeom 1056 点 dz 一致；LFV-04 +8.2692 kg、LFV-05 +0.2249 kg（非零可复现）；OpenVSP 导出此前 62 PASS/1 SKIP 背景 | PARTIAL | HF 侧 W10（HFS-04）NOT_RUN，未证明传到 HF 翼面；warnings：LF 仅主翼、无机身/垂尾、CG provisional；遮挡/湿面积残差未量化 |
| LF | 至少基准+代表扰动均有收敛可复核 CL/CDi/Cm；报告与 RCAIDE 差值/趋势/涡格敏感性；明确共同物理量 | lf_vspaero_results.json：alpha=2° 时 CDi 随加密 +3.44e-4→-8.94e-4→-2.26e-2（符号翻转、约 65×），CDtot 细网格 -1.74e-2 负阻力；LFV-01/02/03 证据作废；SENS-A/B 仅能证明非收敛 | NOT_VALIDATED | 无有效代表扰动 LF 证据；VSPAERO 6.2.0 在 Mach 2.02 不产生物理可接受阻力极曲线；RCAIDE LF 可复现但为经验 build-up+插值（LF_PROVISIONAL） |
| HF | 楔形激波角对理论（建议绝对差 ≤1°）；主翼三档网格 CL/CDpressure 相对变化与误差；失败保留 | hf_su2_results.json：楔形壁压比误差 -0.419% 但激波角差 1.59–2.05°（>1°），涡格 PARTIAL；HFS-02/03 CL 0.09278/0.09548、CD 0.006820/0.007117，medium→fine 相对 ΔCD 4.36%、ΔCL 2.91%、ΔCMy -3.50%；HFS-01 失败、HFS-00R/04 NOT_RUN | PARTIAL | 仅 2 档网格（无第三档/阶数估计）；residual plateau ~1e-1 未达请求收敛；Euler 无黏、仅独立主翼 → 不得称整机高保真 |
| 面积律 | 理论基准；切片/绕轴收敛；基准与代表扰动修正量可复核；说明无法描述的干扰项与重复项；禁止称完整翼身干扰校准 | wave_drag_area_rule.json：Sears-Haack 基准 PASS（相对误差 1.6e-6）；WAVE-01/02/03/04 有效但 36×200；WAVE-05 72×800 后 D/q 变化 2.8666×；paired 增量 ΔCD_on_Sref 0.0081608（基准）/0.0074147（W03+1°），但仅粗离散、无 fine 配对；绝对量 CD 0.0433(coarse)/0.1240(fine) 是归档 RCAIDE 总阻力 CD 0.016844 的 2.57–7.36 倍 | NOT_VALIDATED | 增量只能作候选警告，不得入账；未注入 mission（injected=false，避免伪造）；BODY-CORR BLOCKED；未校准翼身干扰 |
| 目标/预算 | 残差/单位/Sref/坐标系/体风轴/重复不清楚 → NOT_VALIDATED；每次进程入账；缓存不算新求解；失败不写虚假最优 | evaluations.jsonl 23 行 billable；账本与 summary 一致；钱学森账本 q 冻结值 20,483.94 Pa 与 mission 20,654.01 Pa 差异 +0.83% 明示；pile 无虚假最优 | PASS（记录层面） | mission q 差异使 LF/HF 与 E2E 量纲化存在 0.83% 口径差，见 GAP-05 |
| 物理边界声明 | 不得把主翼 SU2 Euler 称整机高保真；Euler 无摩擦；P4–P6 冻结 | summary.not_approved 列 APPROVED_FOR_NEXT_STAGE/P4/P5/P6/merge；hf verdict 明示 inviscid wing-only；blocker B-HF-INVISCID-WING-ONLY | PASS（声明层面） | 后续报告/回执须继续强制 lifting-surfaces-only 口径 |

## 5. 六门禁状态（source: summary.json gates + blocker_register_current.json）

| 门禁 | 状态 | 判定依据 | 主要证据 |
|---|---|---|---|
| GEO-12D | PARTIAL | 12D 设计集/固定机身展开/DOE 接线/W10 OpenVSP 扭转修复已验证；无已验证几何气动力证据 | geometry_validation.json、run_config.design_contract、blocker B-GEO-BOUNDS-PROVISIONAL |
| LF-M2.02 | NOT_VALIDATED / LF_PROVISIONAL | VSPAERO 6.2.0 薄面在 Mach 2.02 非收敛且非物理（CDi 符号翻转、负 CDtot、密度敏感性 65×）；RCAIDE 单巡链可复现但为经验阻力 build-up | lf_vspaero_results.json、blocker B-LF-VSPAERO-MACH2 / B-LF-RCAIDE-EMPIRICAL |
| HF-M2.02 | PARTIAL | 楔形 PARTIAL（激波角差 1.59–2.05° >1°）；主翼仅 2 档网格、无阶数估计、残差未达阈值、无黏仅独立主翼；HFS-00R/04 NOT_RUN | hf_su2_results.json、mesh_convergence.csv、blocker B-HF-* |
| BODY-CORR | BLOCKED | 面积律解析基准 PASS，但真实几何 Mach 切面层不收敛（2.87×）且绝对量悖离独立 RCAIDE 水平 2.6–7.4×；无校准干扰模型 | wave_drag_area_rule.json、drag_component_ledger.json、blocker D-BODY-4 |
| MISSION-DATA | PARTIAL | 12D E2E 仪器链与物理调用计数可复现（与归档完全一致），但无已验证整机油耗标签；mission q 比冻结值高 0.83% | mission_e2e.json、evaluations.jsonl、blocker B-MISSION-Q-MISMATCH |
| BUDGET | EXHAUSTED | 23/23 全部用尽（6/4/6/7）；HFS-00R、HFS-04 NOT_RUN；任何新物理需 owner 新批准 | approval_and_budget_ledger.json、summary.budget、blocker B-BUDGET-EXHAUSTED |

**没有任何门禁为 PASS**；本 run 未签发 APPROVED_FOR_NEXT_STAGE，且 summary.not_approved 明确列 P4 BO/DE、P5 MAML、P6、merge main 均不可启动。

## 6. 缺口与风险清单

| 编号 | 缺口/风险 | 级别 | 证据/说明 | 影响 |
|---|---|---|---|---|
| GAP-01 | LF 代表扰动（LFV-01/02/03）证据因 LD-001 模板缺陷作废 | blocking-for-LF | lf_vspaero_results.json harness_defect；3 次启动已计数 | 无法满足『基准+代表扰动均有可复核 CL/CDi/Cm』 |
| GAP-02 | HFS-00R、HFS-04 NOT_RUN；主翼仅 2 档网格 | major-for-HF | hf_su2_results.not_run；SU2 cap 6/6 | 无三档收敛、无 W10 HF 验证 |
| GAP-03 | 楔形激波角差 1.59–2.05° 超 1° 容差 | major-for-HF | hf wedge_benchmark.verdict=PARTIAL | HF 基准只能 PARTIAL；HFS-00R 加密未做 |
| GAP-04 | 面积律真实几何切片不收敛、绝对量悖离 RCAIDE 2.57–7.36× | blocking-for-BODY-CORR | wave resolution_sensitivity / absolute_magnitude_cross_check | 修正不可入账；BODY-CORR BLOCKED |
| GAP-05 | mission q=20,654.014 Pa vs 冻结 20,483.940 Pa（+0.83%） | minor | mission_e2e.dynamic_pressure_note | LF/HF 与 E2E 量纲化口径差；不得静默换算 |
| GAP-06 | RCAIDE 阻力账本缺 additive increment 项，闭合不可证 | major-for-MISSION-DATA | drag_component_ledger.rcAide_lf_component_ledger.closure | PARTIAL_DATA_NOT_VALIDATED；去重规则仅提案 |
| GAP-07 | 12D 数值边界 provisional；质量/CG/SM PROVISIONAL_NOT_FROZEN | major-for-acceptance | run_config.frozen_conditions.mass_model_status；blocker B-GEO-BOUNDS-PROVISIONAL | 验收基准非最终冻结状态 |
| GAP-08 | ledger.mesh_generation_events=0，未按合同记录网格生成 CPU/内存/磁盘/时长/网格数 | minor（账本完整性） | approval_and_budget_ledger.json | 网格成本不可审计；不影响 23 次求解计数 |
| GAP-09 | A1–A5 独立审阅在 summary 中均 PENDING | major-for-acceptance | summary.review | L 最终回执前必须补齐；A4 矩阵不替代独立复审 |
| GAP-10 | PR #3 远端快照 head=048ef2e5，本地 HEAD=d80b4c485d689082cd117f09ec6445a181dd458c（run 提交未在 pre0 快照远端） | governance | pre0/pr3.json vs 本地 git rev-parse | L 须推送/更新 PR 后再发 Issue #4 最终回执；A4 不执行 GitHub 写 |

## 7. 待负责人决策（由矩阵转交）

- D-A：是否接受 LF-M2.02 = NOT_VALIDATED / LF_PROVISIONAL，即 VSPAERO 6.2.0 在 Mach 2.02 不作为 LF 验收工具；若接受，指定 LF 替补路线（RCAIDE 经验 build-up 仅可作 LF_PROVISIONAL，或另批新工具/预算）。
- D-B：是否批准新预算完成 HFS-00R（楔形加密）+ HFS-04（W10 HF）+ 第三档网格 + 面积律 paired fine 加密；本轮 23/23 已用尽，D-12D-002 禁止自行扩大。
- D-C：面积律绝对量悖离 RCAIDE 2.57–7.36×，是否改走『文献/CFD 校准的机身-翼身干扰』路线，而非继续 OpenVSP Eminton-Lord 修正。
- D-D：12D 数值边界与质量/CG/SM 是否按 owner 既有决定冻结（当前 frozen=false、PROVISIONAL_NOT_FROZEN），以便下一轮验收有稳定基准。
- D-E：APPROVED_FOR_NEXT_STAGE 当前明确不签发；P4–P6 继续冻结。

## 8. A4 结论

1. 执行合规性：23/23 授权启动全部入账（含失败与重试），墙钟 5.6 h ≤30 h、串行、≤4 核、内存预算内；交付物 15 类齐全，原始产物 195 文件/108.8 MB 以 hash 索引在仓库外；报告存在。
2. 结果：链路『执行成功、物理未验收』。几何 PARTIAL、LF NOT_VALIDATED、HF PARTIAL、BODY-CORR BLOCKED、MISSION-DATA PARTIAL、BUDGET EXHAUSTED；无任何 gate PASS。
3. 关键数值：E2E-00 34109.4826 kg（与归档一致，diff 0.0）、E2E-01 +8.0727 kg；V01+1% +8.2692 kg、V02+2° +0.2249 kg；SU2 主翼 CL 0.0928/0.0955、CD 0.00682/0.00712；面积律增量候选 ΔCD 0.0081608（未验证，未注入）。
4. 禁止项：不得称 12D 整机高保真/可信整机油耗已验证；不得把主翼 SU2 Euler 称整机；面积律不得称完整翼身干扰校准；P4–P6 不得启动。
5. 下一步：L 汇总 A1/A2/A3/A5 真实交付与独立审阅 → 推送 run 提交/更新 PR #3 → 在 Issue #4 发一条完整最终验收回执；任何新物理启动需 owner 新预算。

---

附：本矩阵为 A4 只读整理，全部数字来自上述 run 目录文件与 GitHub 只读快照；未执行任何数值求解。GitHub 写 0 次，仓库写 0 次。
