# Lead 决策 L-08：按用户指令继续 D-REAL-001 P2a v2 任务，开启 R7 新循环（诊断+修复后重预注册）

- 决策时间（UTC）：2026-11-11T13:05:00Z（北京时间 2026-11-11T21:05+08:00）
- 决策人：Lead
- 用户指令：m01474「为什么Issue#9发布的任务没有完成？继续执行任务」（2026-11-11T13:03Z）
- 前置状态：R1–R6 全部终止，A5 已签发 R1–R6 最终回执（`A5-P2A-V2-R6-FINAL-RECEIPT-20261111`，commit `3801eff`），并已在 Issue #9 发布（comment 6795075732）。L-07 曾裁定 R 线终止、无 R7；该裁定基于"R6 为最终签署尝试"的治理约束。
- 本决策：**接受用户新的明确指令，开启 R7 新循环**。R7 是**全新批次、全新预注册、全新代理/门禁/签署/GO 链**，不复用 R6 签署件；R6 证据保持只读不改；R7 仍受 451 starts / 3157 internal 累计 caps 约束。

## 1. 任务为何未完成（事实）

R1–R6 六轮真实执行全部在 main 批产生任何有效目标函数评估之前停止：
- R1 preflight SOLVER_FAILED（basename/alias 缺 `concorde_baseline.vspgeom/.vkey`）；
- R2 preflight 假 FAIL（`SOLVED` vs `SOLVED_VALID` 词表）；
- R3 arm setup PermissionError（DSH 沙箱 0o700 mkdtemp + worker 缺 PYTHONPATH/openvsp_root）；
- R4 arm BO `UNIT_BOX_VECTOR_NOT_ACCEPTED`（物理 x12 被 clip 成 unit）；
- R5 setup DesignSpaceError（A2 树 design_space 遮蔽 A1 冻结模块）；
- R6 preflight 2/2 真实 PASS_BYTE，但 main 唯一案 polar 全 NaN（LIFT_MATCH_FAILED）且 `observe` 把 canonical 字符串传给 design_hash → ValueError。R6 为签署件规定的最后尝试，故 L-07 终止、无 R7。

因此 Issue #9 的 P2a pilot 目标（六臂真实数据 + E1–E6）未达成；A5 回执如实记录 NOT_RUN / NOT_COMPUTABLE。

## 2. R7 目标与阶段

1. **阶段 D（零物理诊断，不启 vspaero）**：利用 R6 保留的完整求解产物定位 NaN 机制，并制定最小协议修正；同时修复 observe 7 处字符串误用。
2. **阶段 P（预注册与打包）**：R7 新 batch/run、新 plan/prereg/identity/DRAFT，明确诊断结论、修复内容、协议修正与预算；A5 G-P2AV2R7-PRE 门禁。
3. **阶段 S（签署）**：Lead 签署 approval.json（batch 12 / run R7 / 新 window）。
4. **阶段 D2（签后 dry-run）** + A5 C-P2AV2R7-02。
5. **阶段 G（GO）**：Lead 签发 GO。
6. **阶段 X（执行）**：2 replay preflight + 预注册诊断步 + 384 main（六臂 BO/DE/PSO/A-BO/A-DE/A-PSO）。
7. **阶段 R（复核与回执）**：A5 post-run 独立审计 + A3 统计（E1–E6）+ A4 图/表 + Issue #9 新回执。

## 3. R6 NaN 首轮零物理证据（Lead 直读，2026-11-11T13:0xZ）

- R6 main 唯一案产物完整保留：`...\runs\DREAL001-P2A2R6-20261111-01\arms\BO\BO-d51866f7d3c49303-f1\`（concorde_baseline.vspaero/.vspgeom/.vkey/.polar/.history/.adb/.lod/case dat）。
- main vspgeom 191,129 B SHA256 `6b00d72d06ac59b2…`，网格头 `462 401 2`；preflight PRE-01 vspgeom 227,247 B SHA256 `40fdd436…`，网格头 `543 472 2`。
- main `concorde_baseline.history` 196 行：7 个 solver case（AoA -2..10）**每个 case 第 1 次迭代有限（CLo≈±0.0003、CDo≈0.0073、CLi=0），第 2 次迭代全部变 nan/-nan(ind)**；preflight 同结构在第 2 次迭代起正常收敛（AoA=10 时 CLi=0.3209…）。
- main polar 7 行全 NaN；Sref=362.267959370711（设计 15 物理 Sref，符合预期）；preflight Sref=358.25。
- 初步推断（待 A2/A5 独立确认）：**不是格式/解析问题，而是该设计 15 的 462x401 冻结网格上的 VSPAERO 线性/尾迹求解在迭代 2 发散**；候选机制 H1 网格质量（退化/自交面元、法向）、H2 该网格与 VSPAERO 数值设置的相容性、H3 冻结流程对 family 的选择。需零物理网格体检 + 必要时预注册 1–2 个 main-path 诊断真实求解（计入预算、排除端点）。

## 4. 预算与窗口

- 累计 caps：451 starts / 3157 internal；已用 50 / 362；headroom 401 / 2795。
- R7 计划基线：2 preflight + 384 main = 386 starts / 2702 internal（累计 436 / 3064 ≤ caps，余量 15 / 93）。
- 允许额外预注册诊断：最多 2 starts / 14 internal（累计 438 / 3078），超出需 Lead 书面再批。
- 拟 R7 窗口：2026-11-11T14:00:00Z – 2026-11-12T04:00:00Z；token 形如 `WINDOW_OK-P2AV2R7-20261111T1400Z-20261112T0400Z`。执行启动死线 2026-11-11T19:00:00Z，clean stop 2026-11-12T02:30:00Z，硬停 2026-11-12T04:00:00Z。最终以 R7 approval 为准。

## 5. R7 硬约束

- 不得改动 A1 冻结字节（evaluator f74a4752 / freeze_api 31d78182 / openvsp_model c40b11df / design_space 8f9b893c / config 8b29d1e3 / bundle 995bb12f）与 plan 科学字段（除非在 R7 预注册中显式记录并由 A5 门禁、Lead 签署）。
- 不得改动 R1–R6 证据字节；R6 已签 approval 不复用；R7 全新 run dir。
- 所有 physical 调用必须发生在 R7 approval 签署 + 签后 dry-run + A5 C 门禁 + Lead GO 之后；阶段 D 严格 zero-physical。
- 全程 serial 1 / OMP 1、timeout 60、no retry（除预注册明确允许的单次 family fallback 诊断外）、fuel_burn_kg=null、物理 NOT_VALIDATED。
- 所有分支仅本地 commit、未 push；除非用户另行授权。
- R7 不是自动无限循环：若 R7 main 再次失败，Lead 将结合 A5 意见与预算余量决定是否再修一次；不得默认为 R8。

## 6. 角色分工（即时）

- **A2**：阶段 D — 修复 observe 7 处 + 单测；零物理分析 R6 产物（history/mesh/geometry 统计），确认 NaN 机制；给出 R7 协议修正选项 memo（≤45 min）。Lead 批准后再打 R7 包。
- **A5**：独立只读复核 R6 NaN 证据与 A2 诊断，评估协议修正的科学可接受性，准备 R7 gate 模板；physical=0。
- **A3/A4**：待 R7 执行完成后再启动（统计与图表）。
- **A1**：冻结字节不动；如诊断指向冻结/网格问题，A1 只做只读分析，不改字节。

## 7. 本决策不构成任何 physical 执行授权

阶段 D 允许零物理诊断与代码修复（不启动 vspaero.exe）；真实执行必须等 R7 新 approval + dry-run + C gate + GO。
