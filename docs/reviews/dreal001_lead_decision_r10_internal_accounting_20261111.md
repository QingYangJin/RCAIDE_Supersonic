# D-REAL-001 P2a v2 — Lead Decision L-12（R9 S1 停批裁定 + R10 内部计数修复最终尝试）

decision_id: L-12
date_utc: 2026-11-11T18:05Z
decided_by: lead
physical_authorization: false（本决策本身不构成执行授权；R10 须经新预注册、A5 门禁、Lead 签署、签后 dry-run、A5 C 门禁、Lead GO 后方可启动 solver）

## 1. R9 事实（Lead 独立核验，physical=6 starts/42 internal 实际）

- R9 batch DREAL001-P2-20261111-14 / run DREAL001-P2A2R9-20261111-01，approval b502b484e50c71707e484c758b5baaf0409c423c4838094c8300c36202bdd991 / 76,257B，GO token LEAD_GO_P2AV2R9_EXEC_20261111T180109Z（GO record 62dd594253c41688a5cf7f2415c79d0a878e1fa1e6051202f6090fa65165eff3 / 9,082B）。
- 2026-11-11T18:02:19Z launcher 启动 PID 15416，GATE=PASS；prestart_prefrozen_gate PASS（ae701e00e502ce6adb9cf2b713c26a1d04c7031aceb0c8ee388ea87761b3458e / 37,476B，static_index 119，A1 runtime guard all_equal=True，triples 6）。
- preflight 2/2 PASS_BYTE：PRE-01 polar 455082e2ac8029216a811c89aaa20b34fd9d73faa319eed23da5348e3de4bc87；PRE-02 0287afe0d7e5a91bc286c0b6cbd1ca5623d8aafe65110862fe263925129dd33f；preflight_result cf25c1305a5c71881d385aea0cd58a14264a5506b52adcefbb682ea5d75a8302 / 5,771B，overall=PREFLIGHT_PASS_BYTE。
- 诊断阶段 4 starts：DIAG-01 design16 eb00b7ad545243e6 SOLVED_VALID objective=0.01289480742004768；DIAG-02 design17 dc96d2438a6dddc3 SOLVED_VALID objective=0.021752395563484656；两者 passed=true（科学判据通过）。
- 18:02:45Z 执行器在诊断记账边界 fail-closed：batch_summary status=STOP_DIAGNOSTICS_ACCOUNTING_INCONSISTENT；stop_report 19f7a502a0c4f67d84600ee9c6cad7a7aca2c0b097103ac2c9db6c5433b68dfe / 830B，message="diagnostic phase DIAGNOSTICS_ACCOUNTING_INCONSISTENT: starts=4 internal=0 planned=4/28"；main NOT_RUN（0/384）；physical 6 starts，ledger 6 start/6 end，pending 0，无 retry、无 NaN/Inf 停批、无 timeout、无窗口违规。
- 缺陷性质：执行层记账/报告缺陷（internal_solver_cases 未接通），非数值/几何/求解失败；preflight 与诊断的科学层结果均为通过。A1 评估记录不携带 internal 计数（A1 ledger 只审 physical start/end），R9 按 A5/Lead 要求删除“默认 7”兜底后，preflight/诊断/main 路径的 internal 全部记录为 0。
- 实际消耗核算（caps 口径）：R9 = 6 starts / 42 internal（preflight 2×7 + 诊断 4×7；记录值 0 为报告缺陷，按物理求解 case 计 42）。R9 前累计 56 starts/404 internal；R9 后累计 **62 starts / 446 internal**（caps 451/3157，余 389/2711）。R9 永久排除出 E1–E6，证据按字节只读保留。

## 2. R9 定性

R9 判为 **S1 STAGE STOP — DIAGNOSTICS ACCOUNTING INCONSISTENT**（main NOT_RUN）。R9 不计入端点，不产生任何优化增益或物理结论；R9 的 preflight PASS_BYTE 与诊断 2/2 SOLVED_VALID 作为真实求解循环与 main-chain 数值可行性的证据保留（排除端点）。R9 approval 关闭，不复用；R9 失败不归因于 A1/A1 字节/plan 科学政策。

## 3. R10 立项（最后一次执行尝试，无 R11）

决定：**CONTINUE_WITH_R10_INTERNAL_ACCOUNTING_FIX**。理由：
1) R9 停因是单一、可定位、可审计的执行层记账缺陷；数值链路本身已在本轮真实跑通（preflight PASS_BYTE + 诊断 2/2 SOLVED_VALID，objective 有限且与 R7 同案逐位一致）。
2) caps 仍允许一次**最小**批次：R10 planned 386 starts / 2702 internal（2 preflight + 384 main，不再重跑诊断）→ 累计 448 starts / 3148 internal，仍 ≤ 451/3157（余 3 starts / 9 internal）。任何 retry 或额外诊断 start 都不允许（会越 caps）。
3) R9 诊断（design16/17 两族 SOLVED_VALID）已满足 protocol D 的“main-chain 数值可行性”前置目的；R10 不重跑诊断，R9 诊断证据仅作可行性记录、排除端点，须在 R10 预注册与回执中披露。
4) 窗口充足（硬停 2026-11-12T04:00:00Z），A2 修复 + A5 门禁 + 签署 + dry-run + 执行 + 审计可在窗口内完成。
5) 风险：main 路径仍可能暴露新的执行层缺陷（R1–R9 模式）。Lead 承担该风险；R10 若 main 再失败或记账再不一致，立即终止 R 线出事故回执（无 R11）。A5 的独立意见与异议须逐字记录。

## 4. R10 身份与边界

- batch_id: DREAL001-P2-20261111-15
- run_id: DREAL001-P2A2R10-20261111-01
- run dir: D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\runs\DREAL001-P2A2R10-20261111-01（全新空）
- window: 2026-11-11T18:30:00Z – 2026-11-12T04:00:00Z；token WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z；启动死线 21:00Z；clean stop 02:30Z；硬停 04:00Z。
- planned: 386 starts / 2702 internal（2 preflight + 384 main）；caps 451/3157；reserve 64；cumulative 448/3148。
- supersedes: R9 approval b502b484.../76,257B，physical_call_count_at_supersede=62，run DREAL001-P2A2R9-20261111-01。
- amendment_log: seq1–seq9 与 R9 已签 approval 逐字段一致；seq10 action=R10_INTERNAL_ACCOUNTING_FIX，physical=62。
- A1 冻结字节不变（evaluator f74a4752、freeze_api 31d78182、openvsp_model c40b11df、design_space 8f9b893c、config 8b29d1e3/10,846B、bundle 995bb12f）；plan 科学政策不变（仅 r10 addendum/身份/计数文本）。
- R1–R9 证据只读；R9 run dir 不得改动/删除/移动；R9 approval 不复用。

### R10 修复（仅执行/报告层，A1 字节零改动）
P1 internal 计数：按预注册政策常量 internal_solver_cases_per_start=7（fixed alpha rows）由 physical starts 推导 internal，来源标注 INTERNAL_PER_START_POLICY；preflight/诊断/main 所有 evaluation/record 行统一；不得以 A1 ledger 推断；在阶段边界与最终 summary 做守恒校验 sum(internal)=7×starts，不符 fail-closed（但不得再误停，除非真不一致）。
P2 polar 证据：evaluation/诊断行记录 polar_sha256（可得时；不可得则 null 并披露），用于审计对照。
P3 零物理 smoke：必须用假 solver/录制结果走完整 main-path evaluation 记账链路（含 preflight + main 评估），证明 internal=7×starts 且 phase 边界守恒；physical=0。
P4 诊断不再重跑；R9 诊断证据引用 SHA；R10 预注册明确“diagnostics not in R10 matrix”。
P5 其他 R9 已保留修复（prefrozen reuse flat rows、observe、x12 域、invalid tolerance、launcher preload/env shim、异常路径落盘）不变。

### 停止规则（R10）
- preflight 非 PASS_BYTE 立即停；ledger 不一致/窗口违规/硬件异常/非单案执行层异常立即停；
- main 无效容错：单案 INVALID_NUMERICAL 不中断（含 design15 首种子 NaN）；自动停：>=48 main 评估后无效比例>25%，或单臂连续无效>=6，或累计无效>64；
- 记账不一致（P1 守恒失败）→ 立即停并报；
- 启动死线 21:00Z、clean 02:30Z、硬停 04:00Z；
- 无 retry；serial 1；OMP 1；timeout 60s。

## 5. 后续链路（必须全部完成）

A2 修复+打 R10 包/工具/零物理 smoke（包硬线 18:40Z、工具 18:50Z）→ A5 FAIL-09（R9 独立复核）+ G-P2AV2R10-PRE（含 R10 修复逐行审计、零物理 smoke 复核；硬线 19:10Z/19:20Z）→ Lead 签署 approval（≤19:25Z）→ A2 单文件字节 commit + 真实 post-approval dry-run（≤19:35Z）→ A5 C-P2AV2R10-02（≤19:50Z）→ Lead GO（≤19:55Z）→ A2 执行（2 preflight + 384 main，约 40–50 min）→ A5 post-run 独立审计 + A3 E1–E6 + A4 证据 → A5 签署中文最终回执 → Lead 发布 Issue #9。
- R10 若 main 成功：E1–E6 端点只用 R10 main 有效评估；诊断/预检/R1–R10 其它轮排除；不宣布 winner/显著性/跨族比较；fuel null、NOT_VALIDATED；三层结论分开。
- R10 若失败：立即终止 R 线，A5 出 FAIL-10 + 事故回执，Issue #9 发布（无 R11）。

## 6. 责任与披露

- Lead 对继续 R10 的决定负责；L-12 记录 A5 既有异议（R5 阶段建议终止、R7/R8/R9 阶段多次提示风险）并再次要求 A5 在 gate/回执逐字记录其独立意见与 dissent。
- R9 的 internal=0 记录缺陷、诊断 4/28 与预注册一致、preflight/诊断排除端点、R10 不重跑诊断、累计 448/3148、余量 3/9 等必须在 R10 预注册、A5 gate、最终回执披露。
- 所有分支未 push；R1–R9 证据字节未改。
