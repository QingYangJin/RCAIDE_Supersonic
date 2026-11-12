# Lead Decision L-10 — R7 S1 STOP 裁定与 R8 预冻结复用修复授权

- decision_id: L-10
- date_utc: 2026-11-11T16:05:00Z
- author: lead
- batch_context: DREAL001-P2-20261111-12 / run DREAL001-P2A2R7-20261111-01
- physical_authorization: **false** (本决策不构成任何 solver 执行授权)

## 1. 事实（R7 执行结果）

R7 于 2026-11-11T15:49:26Z 经 Lead GO 启动。preflight 2/2 PASS_BYTE（PRE-01 8bd5a6c7c8311938/543x472 objective 132401.55562456633 polar 455082e2…/7,933B；PRE-02 bc52a54ecefaac4c/483x418 objective 122973.4519637892 polar 0287afe0…/7,933B，均等于 approval 期望字节）。诊断阶段 2/2 SOLVED_VALID，但实际每案 2 starts/14 internal（预注册每案 1 start/7 internal），合计 4/28。main 首个评估 design15 d51866f7d3c49303 冻结后，A1 evaluator 在创建 case 目录前以 ERR_RUNTIME_SHA/KeyError 拒绝，A2 侧记录 status=NOT_VALIDATED、validation_error=FROZEN_BYTES_SHA_MISMATCH、main_starts=0、无 solver spawn；15:50:23Z stop_report phase=s1、arm_id=BO、message=ARM_STOPPED_STOP_NOT_VALIDATED、ledger 6 starts/6 ends 闭合。R7 实际 charged = 6 starts / 42 internal（preflight 2/14 + diag 4/28），main 0；R7 前累计 50/362 → 实际累计 56/404（caps 451/3157），R7 永久排除出 E1–E6，无 retry / 无重启。

## 2. 根因（代码路径 + 字节对照；机理陈述为观测事实）

- A1 静态 family_pair_manifest 中 design15：462x401 = 6b00d72d06ac59b210ea93c69840f1aaf0e4ac4d306113d9791faa3bf7c1c220；546x472 = be8454bfd7db4c4637e73d9637a79391e45f4cbfd66408b956ad35d51f68a689。
- R7 本次新鲜冻结 design15（runtime/family_pair_manifest.append_only.jsonl）：546x472 = 27325306c712f1bb1a709aec52e0d6d63dfe7c6a54ef407d66940120c0e9ec14（228,792B，与静态值同长不同字节）→ OpenVSP 跨进程 tessellation 非确定。
- A1 evaluator_v12.py:615 _runtime_resolve：:641 static=self._index.get(dh)；:642-649 对 f1/f2 比较 static_fam.frozen.frozen_vspgeom_sha256 与 runtime_fam.frozen.frozen_vspgeom_sha256，不等即 raise KeyError(ERR_RUNTIME_SHA)。该守卫在第一次 family 调用内执行，故被记 f1 调用，实际不一致为 f2（546x472）。A2 收到空 geometry bundle 后按 p2a_v2_runtime.py:803-818 判 FROZEN_BYTES_SHA_MISMATCH。
- initial_designs_manifest 三个设计（design15 d51866f7d3c49303、design16 eb00b7ad545243e6、design17 dc96d2438a6dddc3）的 6 个 family 预冻结 .vspgeom 路径均存在于 A1 树，且 SHA256 == manifest 值（Lead 实算：6b00d72d/be8454bf、5feb1be8/54a46567、99a52d06/7ab0b60d）。plan 语义为 initial designs 采用 PREFROZEN_ZERO_PHYSICAL_FROM_P2AFAM_MANIFEST；R7 仍走了重建路径。R6 只是碰巧重建命中静态字节。

## 3. 裁定

decision = CONTINUE_WITH_R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX（R7 关闭为 S1_STOP_FROZEN_BYTES_SHA_MISMATCH；R7 approval 不复用、不重开）。

R8 最小修复范围（A2 执行层 + 包/launcher/工具；A1 冻结字节与 plan/prereg 科学政策零改动）：

1. initial designs（15/16/17）在 main 与诊断阶段**复用** initial_designs_manifest 登记的 A1 P2AFAM 预冻结 family 字节：逐文件校验 SHA256 与 manifest 一致后 copy 到 runtime freeze 目录，append 合法 runtime pair 记录（status PAIR_READY、arm_blind=true、roles/x12/families 与 manifest 一致），标记 reused_prefrozen=true、source_kind=PREFROZEN_MANIFEST_REUSE、builder 重建次数 0、physical_call_count 0；禁止对这些设计调用 OpenVSP 重建。篡改字节必须 fail-closed。
2. 诊断阶段保留 P2A 完整 pair 评估语义（每诊断 design 2 starts/14 internal，共 4 starts/28 internal），但 R8 预注册必须**明确写 4/28**（替换 R7 的 2/14 旧写法），并在 prereg/plan 中披露 R7 实现与旧预注册不符（4/28 vs 2/14），R8 按实际实现语义前置登记 4/28。DIAG-01 design16 eb00b7ad545243e6、DIAG-02 design17 dc96d2438a6dddc3；判据 SOLVED_VALID 且 objective 有限非 null；两者都失败 → main NOT_RUN 干净停止；≥1 通过 → main 384。
3. 修正 batch_summary 的 internal_solver_cases 伪计数：physical_solver_starts==0 时 internal 必须=0（移除 p2a_v2_executor.py:534 的默认 7 兜底，即 int(solver.get("internal_solver_cases", 7) or 7)），并按 phase 分列 preflight/diagnostic/main internal + total，新增 fail-closed 记账断言（starts==0 且 internal>0 → ACCOUNTING_INCONSISTENT）。
4. 修正 diagnostics[].polar_sha256 汇总字段（从实际 polar 文件实算）。
5. 新增 zero-physical preflight gate：solver 启动前校验 3 个 initial design 的复用 record 与 manifest 字节/canonical 完全一致，任一不一致 REFUSED；prestart 记录该检查。
6. R8 预注册必须逐字登记 2+4+384=390 starts / 2730 internal。

## 4. R8 身份（预注册常量）

- batch_id: DREAL001-P2-20261111-13
- run_id: DREAL001-P2A2R8-20261111-01
- run_dir: D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\runs\DREAL001-P2A2R8-20261111-01（全新空）
- window: 2026-11-11T16:30:00Z – 2026-11-12T04:00:00Z；token WINDOW_OK-P2AV2R8-20261111T1630Z-20261112T0400Z
- start deadline 2026-11-11T21:00:00Z；clean stop 2026-11-12T02:30:00Z；hard stop 2026-11-12T04:00:00Z
- planned: 390 starts / 2730 internal（preflight 2 + diag 4 + main 384）
- caps: 451 / 3157；reserve 64；cumulative: 446 / 3134（prior 56/404 + R8 390/2730；headroom 5 starts / 23 internal）
- supersedes: R7 approval sha256 1a552267ab0070ee4f690815ed1de1db6d5976c1ada8356421f017bb84d72e37 / 69,405 B / physical_call_count_at_supersede 56 / run DREAL001-P2A2R7-20261111-01
- amendment_log seq8: action=R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX, physical=56（seq1–seq7 必须与 R7 已签 approval 逐字段一致）
- r8_addendum.status=R8_PREFROZEN_REUSE_AND_DIAG_PAIR_PREREG_FIX；r1–r7_reference 全部 excluded_from_endpoints=true、artifacts_preserved=true；r7_reference 记 charged 6/42、status S1_STOP_FROZEN_BYTES_SHA_MISMATCH、superseded_approval_sha256=1a552267…
- A1 绑定不变：a1_head 2a57632b3f7d5d567556d9774913ec40a5d72272 / evaluator f74a4752… / freeze_api 31d78182… / openvsp_model c40b11df… / design_space 8f9b893c… / config 8b29d1e3…/10,846 B / bundle manifest 995bb12f…

## 5. 授权与边界

- 本决策仅授权 A2 构建 R8 零物理包（8 文件）+ 新 launcher（p2av2r8_launch.py，env 前缀 DREAL001_R8_*，沿用 R6/R7 design_space preload + R4 env shim）+ 新 post-approval dry-run 工具 + 零物理 smoke（含复用 record vs manifest 字节/canonical 校验、A1 _runtime_resolve 守卫的零物理验证）+ 单测；physical_call_count 必须保持 0，禁止启动任何 solver、禁止重跑 R7、禁止改 A1 / R1–R7 证据字节、不 push。
- R8 必须经 A5 G-P2AV2R8-PRE 门禁、Lead 签署 approval.json、签后真实 dry-run、A5 C-P2AV2R8-02、Lead GO 六步后才可真实执行。
- 累计预算 446/3134 距 caps 仅余 5 starts/23 internal；R8 不允许任何 retry 或计划外求解。自动停批与硬停规则沿用协议 D（L-09）。
- R8 之后是否继续由 Lead 在 A5 审计后另行决策；本决策不预授权 R9。

## 6. 风险与披露

- Lead 承担 R8 授权风险；A2 推荐的预冻结复用方案与 Lead 独立代码复核一致。诊断 4/28 口径为 Lead 采纳 A2 推荐 (a)，并更正 A2 累计算术（A2 报 440/3092 误用 pre-R7 的 50/362；正确 446/3134）。
- A5 的独立意见（含是否建议终止、是否接受预冻结复用作为零物理修复、是否接受 4/28 重登记）必须原样记录进 R8 gate 与本轮最终回执。
- 三层结论口径不变：main 未完成有效评估前，INTERNAL_AERO_OPTIMIZATION_GAIN=NOT_COMPUTABLE；EXTERNAL_PHYSICS_SUPPORTED=NOT_VALIDATED；fuel_burn_kg=null。

## 7. 不构成执行授权

本文件为治理决策记录，非 approval 签署件；任何 solver 启动必须另经 R8 approval + GO。
