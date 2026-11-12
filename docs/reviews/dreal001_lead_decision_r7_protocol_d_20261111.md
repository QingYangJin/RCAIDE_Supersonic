# L-09 Lead 决策：R7 以“无效评估容错”协议继续（否决网格 QC 数据门）

- 决策 ID：L-09
- 时间：2026-11-11T13:58Z（Asia/Shanghai 21:58）
- 决策人：Lead（Team Lead）
- 依据：用户 m01474“为什么Issue#9发布的任务没有完成？继续执行任务”；L-08（`D:\RCAIDE\dnext001\wt-real-lead\docs\reviews\dreal001_lead_decision_r7_continue_20261111.md`，SHA256 27898d2e281efb6a38b59c1e9e9e37e1ba872b6dee2b18241d9dad44641b8ddf）；A2 R7 阶段 D 交付 commit 6c098ec825d9b69b23ffc3b668c2de65281ccc3a；A2 memo `docs/evidence/dreal001/r7_protocol_options_memo_20261111.md`（SHA256 62d24bd1…d098f0a819）
- 本决策 physical_authorization=false：不授权任何求解器启动；只有 R7 approval 签署 + 签后 dry-run + A5 C 门禁 + Lead GO 之后才可执行。

## 1. R6 残余事实

- R6（batch 11 / run DREAL001-P2A2R6-20261111-01）于 2026-11-11T11:21:26Z 真实执行：preflight 2/2 PASS_BYTE（PRE-01 455082e2…/PRE-02 0287afe0…，各 7,933B）；main 唯一案 BO-d51866f7d3c49303-f1（design 15）polar 7 行全 NaN（polar SHA 58b8438df1225b07b3ef8dc327670575d99a6866b204f2c0840de074324d489a/7,933B）→ LIFT_MATCH_FAILED、objective null；随后 on_evaluation→observe 抛 ValueError: x12 must have exactly 12 values（executor 7 处 design_hash(canonical_x12(X)) 误用，canonical_x12 返回 str）→ S1 STOP。R6 charged 3 starts/21 internal；累计 50/362（caps 451/3157）；R1–R6 全部永久排除出 E1–E6；无 R7 的旧决议 L-07 已被用户 m01474 的新指令取代，L-08 开启新 R7 循环。
- A2 阶段 D 已完成（zero-physical，commit 6c098ec）：
  - observe 修复：7 处 design_hash(canonical_x12(X)) → design_hash(X)（executor 3,707B→70,709B，SHA256 ac79d4fa6b0b08f00d1f57976669cca274307414ecf59cdf12142e7926274b4f）；pytest -k r7_ 4 passed，相关回归 14 passed。
  - R6 NaN 零物理诊断结论：NaN 为 design 15 薄面网格几何质量特异（两冻结族指标相同：z_extent 0.06195、120 非平面面元、75 三角形自交、28 sliver；PRE-01/PRE-02 完全平坦且 0 自交），.vspaero 设置与 PRE-01 逐键相同（仅 Sref 362.268 vs 358.25），两族几何等价 → 原样重跑必然再 NaN。A1 冻结层只做 mesh identity（PAIR_READY），无网格 QC。
  - 协议选项 memo A/B/C；A2 推荐 B（零物理网格 QC 门）+ C-lite（1 个诊断 start）。

## 2. Lead 对选项 B（网格 QC 数据门）的独立校准结论：否决

Lead 用 A2 同一套 QC 解析器（`r7_nan_diag_geom.py` 的 analyze()）对 3 个初始设计 6 套冻结网格 + 2 个 P2CAL 真实成功求解案例 + 2 个 preflight 网格复算，结果：

| geometry | z_extent | nodes\|z\|>1e-4 | nonplanar faces | nonplan_max | self_int_pairs | slivers |
|---|---|---|---|---|---|---|
| d15 462x401（R6 NaN） | 0.0620 | 120 | 120 | 0.00990 | 75 | 28 |
| d15 546x472 | 0.0620 | 120 | 120 | 0.00990 | 75 | 28 |
| d16 456x395 | 0.0711 | 120 | 120 | 0.01152 | 69 | 16 |
| d16 548x474 | 0.0711 | 120 | 120 | 0.01152 | 69 | 16 |
| d17 481x416 | 0.0528 | 120 | 120 | 0.00837 | 80 | 15 |
| d17 539x468 | 0.0528 | 120 | 120 | 0.00837 | 80 | 14 |
| CAL-W05p-f483x418（真实 SOLVED） | 0.0000 | 0 | 0 | 0.00000 | 0 | 11 |
| CAL-W10p-f483x418（真实 SOLVED，P2CAL 12/12 成功之一） | 0.0136 | 116 | 120 | 0.00158 | 101 | 7 |
| PRE-01（真实 PASS_BYTE） | 0.0000 | 0 | 0 | 0.00000 | 0 | 6 |
| PRE-02（真实 PASS_BYTE） | 0.0000 | 0 | 0 | 0.00000 | 0 | 7 |

关键反证：**CAL-W10p-f483x418 的真实 VSPAERO 求解成功（P2CAL W10 标定 3/3 正常收敛），但其 self_int_pairs=101 > d15 的 75、nonplanar faces=120 与 d15 相同，且 W10p 的 nonplan_max=0.00158 也在 A2 建议阈值 nonplanarity_max>1e-3 的拒绝侧**。若按 A2 建议阈值（self_intersections>0 或 nonplanarity_max>1e-3 或 slivers>20），W10p 这类已知可解几何会被拒绝；同时 d16/d17 的 nonplan_max（0.01152/0.00837）也全部被拒 → 3 个初始设计全 QC_FAIL，R7 无法开 main。这说明该 QC 指标**未被证明与 VSPAERO 求解成败相关**，不能作为进入/排除评估的数据门（否则构成未经证实的几何筛选/数据选择偏差）。Lead 因此否决选项 B。

## 3. L-09 决策：R7 采用“无效评估容错 + 预注册诊断”协议（选项 D）

### 3.1 协议 D 内容（R7 预注册）

1. **代码修复（A2 executor/optimizer 层，不改 A1 冻结字节、不改 plan 科学政策）**：
   - observe 修复（已完成，commit 6c098ec）：7 处 design_hash(canonical_x12(X)) → design_hash(X)。
   - **无效数值评估容错**：对每个 main 评估，若 A1 evaluator 返回状态非 SOLVED_VALID、或 objective 为 null/非有限（NaN/Inf polar、LIFT_MATCH_FAILED、非收敛等），该评估记录为 `INVALID_NUMERICAL`（含原始状态、polar SHA、原因），**不进入 objective 统计**；arm 记录失败评估并继续后续提案；不得因单个无效评估中断批次（删除 R6 那样的硬 S1 崩溃路径，但保留真正执行层错误为硬失败）。
   - **优化器容错**：BO 模型更新跳过无效观测；DE/PSO 对无效评估按预注册规则处理（不得崩溃）；修复 DE/PSO population 初始化潜伏缺陷（R6 只跑 BO 未触发：ProposalEngine.observe 只建 3 seeds，DE.propose 需要 population≥4，可能 ValueError）并补零物理单测。
   - **异常路径证据**：executor 在 arm 异常停止路径必须落盘最小 preflight_result.json / batch_summary.json（R6 未落盘，属报告缺陷），不改变科学判定。
2. **诊断阶段（预注册、排除端点）**：2 个 replay preflight 之后、384 main 之前，插入 2 个诊断真实求解（各 1 start/7 internal，串行 OMP1 timeout 60 no-retry）：
   - DIAG-01：初始 design 16（design_hash eb00b7ad545243e6）走完整 main 链路（freeze→evaluate→lift match→observe 修复版）；
   - DIAG-02：初始 design 17（design_hash dc96d2438a6dddc3）同样链路；
   - 通过判据：status=SOLVED_VALID 且 objective 有限非 null；若两者都失败 → main NOT_RUN，R7 以诊断证据干净停止并出回执；若 ≥1 通过 → 继续 384 main。
   - 诊断结果不计入 E1–E6 端点；诊断真实求解计入预算与 caps；诊断发现的 invalid 也记录。
   - 说明：design 15（d51866f7d3c49303）的 NaN 已被 R6 证明可复现，R7 main 中其首个 BO 种子评估将按无效评估记录（允许成本 1 start/7 internal，不再浪费 batch）。
3. **预算与身份（R7）**：
   - batch_id `DREAL001-P2-20261111-12`；run_id `DREAL001-P2A2R7-20261111-01`；全新空 run dir `D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\runs\DREAL001-P2A2R7-20261111-01`。
   - window 2026-11-11T14:00:00Z–2026-11-12T04:00:00Z；token `WINDOW_OK-P2AV2R7-20261111T1400Z-20261112T0400Z`；执行启动死线 2026-11-11T19:00:00Z；02:30Z clean stop；04:00Z 硬停。
   - planned：2 preflight + 2 diagnostic + 384 main = **388 starts / 2716 internal**；caps 451/3157；累计 = 50/362 + 388/2716 = **438/3078**（余量 13 starts/79 internal）。
   - supersedes R6 approval `72b95e03130fbe958c52528f1b8f484eae4872140a7336709094b9108964f98f` / 67,063B / physical_call_count_at_supersede=50 / run DREAL001-P2A2R6-20261111-01；amendment_log seq1–seq6 与 R6 已签 approval 逐字段一致，新增 seq7 action=`R7_OBSERVE_AND_INVALID_TOLERANCE_FIX`、physical_call_count_at_amendment=50。
   - r7_addendum：status=R7_OBSERVE_AND_INVALID_TOLERANCE_FIX；r1–r6_reference（各 charged、excluded_from_endpoints=true、artifacts_preserved=true）；r6_reference 含 R6 单案 NaN 事实与 polar SHA、observe 缺陷、R6 approval sha；r7_change 列明 observe 修复、无效评估容错、DE/PSO 修复、诊断阶段、异常路径证据补齐、launcher preload/env shim 沿用；mesh QC 数据门**未采用**（附 Lead 校准证据）；A1 绑定不变（a1_head 2a57632b3f7d5d567556d9774913ec40a5d72272、evaluator f74a4752…、freeze_api 31d78182…、openvsp_model c40b11df…、design_space 8f9b893c…、config 8b29d1e3…/10,846B、bundle manifest 995bb12f…）；plan/prereg 科学政策字段（六臂、B=64、seed42、no-retry、timeout 60、serial 1/OMP1、fuel null、NOT_VALIDATED）不变。
4. **停止规则（R7，预注册）**：
   - 硬停：preflight 非 PASS_BYTE；ledger/记账不一致；窗口违规；硬件异常；非单案执行层异常（executor 崩溃、写盘失败等）；任何未预注册的协议偏离。
   - 科学自动停：main 评估 ≥48 个后，无效比例 >25%，或单臂连续无效 ≥6，或累计无效 >64 → 停止 main，按预注册记录并出回执；其余情况按计划跑完 384 main。
   - 单案无效不是停止条件（与 R6 GO 的“NaN 即停”不同，该条已在 R7 预注册中显式替换并说明理由）。
5. **端点与结论边界**：E1–E6 只用 R7 main 的有效评估（六臂各自轨迹），R1–R6 与诊断不进入；不宣布 winner/显著性，不做跨族/跨批比较；fuel_burn_kg=null；physical NOT_VALIDATED；三层结论继续分开（SOLVER_LOOP_VERIFIED / INTERNAL_AERO_OPTIMIZATION_GAIN / EXTERNAL_PHYSICS_SUPPORTED）。
6. **A5 独立复核**：A5 必须在 G-P2AV2R7-PRE 中逐项审查协议 D（observe 修复、无效评估语义、诊断设计、停止规则、预算/身份/supersedes/amendment、A1 字节未变、R1–R6 证据未改、R6 approval 不复用），并在 gate/最终回执中记录：A2 推荐 B+C、Lead 否决 B 的校准证据、Lead 决策与责任、A5 的独立意见及其边界；A5 有权在 condition 中追加更严格的披露/停止要求（不得改变协议 D 的科学结论口径）。

### 3.2 Lead 责任与风险

- Lead 承担：R7 是用户 m01474 明确要求继续后的新一轮尝试；协议 D 的科学风险（无效评估比例可能高、E1–E6 样本可能稀疏）由 Lead 承担，A5 独立审计与回执如实记录。
- 预算风险有界：R7 实际计划 388 starts ≤ caps 451（余 13），internal 2716 ≤ 3157（余 79）；若 R7 因无效比例自动停，累计消耗仍受控，R7 永久排除、出事故回执。
- 严禁：绕过 A5 门禁、签署前启动求解器、复用 R6 approval、修改 A1 冻结字节、修改 R1–R6 证据字节、push。

## 4. 立即执行顺序

1. A2：按 §3.1 构建 R7 8 文件包（含新 executor SHA/新 launcher p2av2r7_launch.py/新 dry-run 工具/verify_package/pytest/smoke），立即开工；阶段 D 的 observe 修复 commit 6c098ec 作为代码基线；包完成后报 Lead+a5（目标 2026-11-11T14:45Z 前，硬线 15:00Z）。
2. A5：独立复核 A2 阶段 D 诊断与 Lead §2 校准结论；准备 G-P2AV2R7-PRE 模板（R6 schema：conditions 52 条形态、approval_refs_final 14 键、signature_requirements）；A2 包到后 20 分钟内给 verdict（硬线 15:20Z），并如实记录分歧。
3. Lead：A5 gate PASS 后签署 R7 approval（新 sign_approval_r7.py）→ A2 单文件字节 commit + 真实 post-approval dry-run → A5 C-P2AV2R7-02（硬线 15:50Z）→ Lead GO（sign_go_r7.py）→ 执行。
4. 执行完成后 A5 post-run 审计 + A3 E1–E6 + A4 图/表 → Issue #9 新中文回执（A5 签署）。

## 5. 合规声明

- 本决策不启动任何求解器、不消耗 physical（physical_call_count 保持 0/solver_started=false）。
- 未改 A1 冻结代码字节；未改 R1–R6 run dir/approval 字节；未 push。
