# [阶段验收汇报｜2026-11-13] D-FIXED-001：F0/F1/F2/T0 完成情况与 #11 衔接判定

> 本汇报按 Issue #10 正文“完整中文阶段汇报”要求提交，包含代码 SHA、测试、固定任务真实结果、数值门禁与跨任务训练就绪判定。**本汇报不是新一轮真实 solver 的授权**；#11 首批真实多任务 VSPAERO 采集与 FOMAML 训练仍须按 Issue #11 M0 另立批次、A5 独立审查、Lead 签发新 approval/GO 后启动。fuel_burn_kg=null；外部物理 NOT_VALIDATED。

## 0. 结论先行

| 工作包 | A5 独立结论 | 关键事实 |
|---|---|---|
| F0 可复现基线与备份 | **REPRO_BASELINE_PASS** | 远端分支/commit 4504bb75；182 变更文件；raw 备份 2,228 文件；五口径账本；restore/失败注入 PASS |
| F1 固定任务稳定性 | **F1_FAIL_ON_PHYSICS（旧批，已作废）→ F1R2_PASS_WITH_DISCLOSURE** | 旧批暴露 XForm 相对坐标缺陷，几何物理无效；修正冻结后 22/22 SOLVED、22 starts/154 internal |
| F2 普通优化闭环 | **F2R2_PASS_WITH_NO_GAIN_AND_MAJOR_PROTOCOL_DEVIATION_DISCLOSED** | 18 starts/126 internal；14 有效观测+2 失败；真实 ask→build→VSPAERO→升力匹配→D_i_N→tell（G1 为 PRE_COMPUTED_DETERMINISTIC_AT_FREEZE，objective 未参与生成、无自适应选择；E3 仅执行链闭环）；无优化增益证据 |
| T0 跨任务元学习代码基础 | **T0_CODE_READINESS_PASS**（G-T0-READY-02） | 可运行 TaskSpec/MetaDataset/MetaTrainer/AdaptationRunner/WarmStartSampler/生产 fail-closed 入口；51 checks 0 FAIL；ready_for_real_meta_training=false（真实适用域/admission 属 #11 M0/M1） |

**三层结论（不得合并）**：
- `SOLVER_LOOP_VERIFIED = PASS_WITH_DISCLOSURE`：固定任务真实执行链、账本、同输入 preflight 回放与失败分类可审计；仍有单 seed、单构造状态等披露。
- `INTERNAL_AERO_OPTIMIZATION_GAIN = NOT_EVALUATED_NO_EVIDENCE`：F2R2 完成闭环但**没有**超过数值不确定度的增益证据；没有 winner/排名/显著性。
- `EXTERNAL_PHYSICS_SUPPORTED = NOT_VALIDATED`：仅本地 OpenVSP/VSPAERO 受限翼面内部气动评价，不代表整机/燃油/外部物理。

**真实预算双口径（Issue #10 累计，禁止混写）**：actual **65 physical starts / 455 internal**；charged（含 F2R-01 预留失败）**70 / 490**。F1 旧批 22 starts 的几何物理无效，但其启动/账本事实保留；不得把其 CDi/D_i_N 当作真实气动证据。

## 1. F0：可复现远程基线、raw 备份与五口径账本

- 远端分支 `research/dfixed001-fixed-loop`，commit **4504bb75cc32e334cf9f906ad2dcda9a7ff9b471**（parent 683a868，tree 2806b88a…）；GitHub API 创建，本地装配 clone commit b2488eff。
- 变更 **182 文件 = 181 added + 1 modified + 0 deleted**，完整变更新字节 5,814,948B；F0_BASELINE_INDEX 185 条（5 个与 base 同字节无 diff，2 个复制后生成）。**更正历史笔误**：F0 汇总曾写“182 文件全部 added、5,772,366B”，实际为 181A+1M+0D、5,814,948B；5,772,366B 是 index 185 条总字节。
- raw 备份：仓库外 2,228 文件 / 207,718,755B；SHA256SUMS 7d55b016…/289,482B；三方（源/备份/A5 独立重算）0 mismatch；inventory digest 105f3bc9…；restore test 2,228 文件 0 mismatch（3.33s，总 5.95s）。
- 五口径账本（A2 accounting_ledger.py **2a8fd918…/35,413B**）：append-only JSONL；reservation→start→end；失败/取消计费；RECOVERED_INTERRUPTED；幂等；尾行修复；11 tests passed。R10 历史重算 91/637；历史累计 actual 153/1,083 与 charged 448/3,148 分离。
- A5 判据 A–G 全 PASS，结论 REPRO_BASELINE_PASS（commit ec62229）。披露：远端提交 unsigned、web_fetch 100KB 截断、A5 的 pytest 为 relocated 运行、五口径尚未接入所有执行器（后续 F2R 已接入）。

## 2. F1：固定 12D→真实几何与求解器稳定性

### 2.1 旧批 F1：物理几何缺陷（诚实作废）
- 旧 F1 签发/执行链合法（22/22 SOLVED、22/154、0 INFRA/retry），但 A1 零物理审计发现 A1 几何代码 `research/concorde_metaopt/aircraft/openvsp_geometry.py` 使用 `SetParmVal(...,"XForm")` 时未显式设置 `Abs_Or_Relitive_flag=0`，OpenVSP 3.55 默认 relative → 位置/旋转写入静默 no-op（读回 0）。
- 后果：vertical_tail 实际是“水平面”，两部件共面于原点，vspgeom 无真实垂尾；旧 F1 的 CDi/D_i_N 物理语义无效。A5 判 **F1_FAIL_ON_PHYSICS**，F2 旧几何 HALT；该批 22 starts 计入实际账，但结果不得作真实气动证据。
- A1 修复 commit 74e69df：写 location/rotation 前显式 `Abs_Or_Relitive_flag=0`+Update，写后 GetParmVal 读回，误差>1e-9 抛 RuntimeError（fail-closed）。orientation 审计 26/26 PASS：vertical_tail bbox [13.1576, 1.3165(厚度), 5.0093(展向)]，main_wing 展向 25.6046，3 次 build 全 546×480，Sref 358.25000000000006。

### 2.2 F1R-01：runner 缺陷（已冻结，不作科学结果）
- 修正几何首批 F1R-01 在 PRE-01 后崩溃（`classify_result` 返回 dict 被当字符串、`polar_path` 未填、`TypeError: unhashable type 'dict'`）；实际 1 start/7 internal，无 closeout。A5 判 **F1R_ATTEMPT1_RUNNER_DEFECT_INFRA_STOP_UPHELD__NO_SCIENTIFIC_RESULT**；run dir 36 files/2,830,261B 冻结只读，禁止复用其 polar 8f4c9f81 作 expected。

### 2.3 F1R2：修正几何下的真实稳定性批次（有效结果）
- 新身份 **DFIXED-F1R2-001 / DREAL001-F1R2-20261113-01**；approval 67a2d062、C-02 7e2c4be PASS、GO a84242a0（token 与 approval 逐字一致）、runner b5ebe48a、executor ed0f2324、SUMS 600262e4。
- 执行 2026-11-12T22:38:41Z–22:40:22Z（101s）：**22/22 SOLVED，22 starts/154 internal**，caps 28/196 未触顶，0 INFRA/0 retry/stop=null。run dir 653 文件；A1 closeout 58ffe4d（SUMS 8a25b2d9…/67,752 B；652/652 条匹配）。
- Preflight expected 由 **SELF_ESTABLISH_PREFLIGHT** 建立：P1=PRE-01 真实求解建立 polar **8f4c9f81…/7,933B**（record 33230790），P2=PRE-01_R2 同五文件字节（inputs 2fe7ac59）fresh 进程 PASS_BYTE；M0 零物理重放 0 starts。expected 仅作字节确定性基线，不作物理/增益判据。
- 关键门禁：Group A 4/4 设计 polar SHA 完全同（8f4c）；同 x12 各设计仅 **1 个构建状态**（cross-state 不适用，披露）；C1–C6 单变量响应均改变对应表面（C2 W10p tip_twist 0.013587m **低于 3σ=0.1014m 检测限**，按冻结参数认证并披露）；未受影响部件位移 0；orientation 22/22 PASS；SUMS 652/652。
- 不确定度：U_rep=0、U_wake=0（仅表示 M1 NumWakeNodes 8→16 在本配置下 polar 字节同；机制未证，不得表述为尾迹不敏感）、U_iter=U_within=**7.052110714290113e-08**、2U=1.41042e-7；U_mesh=**NOT_COMPUTABLE**（本批未做网格加密；不得沿用旧 5.84% 跨族带作 U_mesh/增益阈值）。端点 baseline：CDi 0.016905823456482387、D_i_N 124061.21453538346、α* 5.100657553215899、CL 0.18174391741992046、升力残差 0。
- A3 独立统计（commit 0e71afc）34 项守恒全 PASS；22/22 CL-α R²≥0.999748、残差 0；D_i_N 独立复算 rel 0。A5 verdict **F1R2_PASS_WITH_DISCLOSURE**（commit fd1ab768），REPEATABILITY=PASS_WITH_DISCLOSURE、GEOMETRY_SEMANTICS=PASS_WITH_DISCLOSURE（仅内部）、E1–E6=NOT_COMPUTABLE（非优化运行）。中文回执 A5-DFIXED001-F1R2-FINAL-RECEIPT-20261113（commit abcc3976）。

## 3. F2：真实普通优化器闭环（DE）

### 3.1 F2R-01：零物理主试验停批（INFRA）
- rev5 approval 66728640、C-03 dc855bf PASS、GO cbb5b55d；2026-11-13T00:38:32Z 启动，preflight 2/2 PASS_LIVE_PREFLIGHT 后 main 前 5 例全部 `ModuleNotFoundError: research.concorde_metaopt.dreal001.geometry`（A2 进程先导入 regular package，A1 runner 的 `sys.path.insert` 对已导入父包无效）；主试验 solver 0。A5 判 **INFRA_ZERO_PHYSICAL_MAIN**；actual 2/14、charged 7/49；approval/GO/C-03/dry-run 消耗不复用。

### 3.2 F2R2：修正 import-root + 校准 orientation gate 后真实执行
- 第二层缺陷：旧 orientation gate `G-ORI-05: tail_bbox[2]>=4.9` 按 baseline 尾面积/展长校准，F2R 16 个 main 槽位中 **6/16（37.5%）** 合法低尾面积设计会被拒；A5 裁定 **GATE_CALIBRATION_DEFECT_CORRECTION**（非移动门柱）。A1 新冻结 **f1r2g_runner.py 4e595661…/110,025B**：判据改为 `tail_bbox[2]>=1.0 且 tail_bbox[2]>=3.0*tail_bbox[1]`；18-case 零物理真实 build：旧 12 PASS/6 FAIL → 新 18/18 PASS，3 个负例（共面/零厚度/厚 Y）仍 FAIL；A5 定向重冻结审计 f282898 PASS。
- rev6/rev6b：rev6 因 identity/plan 的 A1 audit 引用路径与短 SHA 错误被 rev6b 取代（L-26；rev6 标 SUPERSEDED 非 VOID）；rev6b 包 commit 0ab25d3，approval DRAFT e50bb309（revision 7、immutable 37b3d2a1）、identity 2f3e4277、plan af2e1069、SUMS 921da83f；A5 PRE-03 6750e8c/8808c7ed（77 conditions、89 checks 0 FAIL）；Lead 签 approval **13515f5d…/26,877B**、安装 SUMS b505c2ee、窗口内 post-approval dry-run **41d33522…/11,734B**（GREEN、physical 0）、A5 C-P2AV2F2R-04 4579cd4/760797ae PASS、Lead GO **1c07bdfc…/4,680B**（issued 2026-11-13T02:14:21Z）。
- 执行 2026-11-13T02:16:33.916956Z–02:17:49.445186Z（75.528s），status=COMPLETED、stop=null、ledger_consistent=true；**18 starts/126 internal**（actual=charged，caps 24/168，reservations/starts/ends=18/18/18，abandoned/open=0）；design_evaluations=14、cached_reads=0；**16 SOLVED_VALID + 2 SOLVER_FAILED**；0 INFRA、0 retry。
- preflight 2/2 PRE-01/PRE-01_R2 = SOLVED_VALID + PASS_LIVE_PREFLIGHT，polar 8f4c9f81…/7,933、CDi 0.016905823456482387、α* 5.100657553215899、D_i_N 124061.21453538346、mismatches=[]。
- main 16：14 有效；DE-G1-02 与 RE-06-G1（同设计 2b7e08bacfd3c25e）SOLVER_NONCONVERGED（exit 0、未超时、objective=null；polar 58b8438d…），失败率 12.5%<25% 且<5 → 未触发科学停；失败计费、无 retry；E2 为 7/7 PASS + 1 NOT_COMPUTABLE（RE-06-G1）；7 对有效重复 CDi 相对差 0、polar SHA 相同。描述性最小 D_i_N=105466.23760960519（DE-G0-02，CDi 0.012273199825898704，α* 4.360086975080307）。**不得表述为优化增益**（单 seed、U_mesh unavailable、无 2U 增益规则）。
- A5 正式审计 **7ed9c9e4**（79 checks=67 PASS+10 PWD+2 NOT_COMPUTABLE、0 FAIL）；中文回执 **64549a46**。verdict **F2R2_PASS_WITH_NO_GAIN_AND_MAJOR_PROTOCOL_DEVIATION_DISCLOSED**；科学结果 PASS_WITH_NO_GAIN、执行完整性 PASS_WITH_DISCLOSURE、预注册合规 PASS_WITH_MAJOR_PROTOCOL_DEVIATION_DISCLOSED。三层：SOLVER_LOOP_VERIFIED=PASS_WITH_DISCLOSURE；INTERNAL_AERO_OPTIMIZATION_GAIN=NOT_EVALUATED_NO_EVIDENCE；EXTERNAL_PHYSICS_SUPPORTED=NOT_VALIDATED。
- **P-01 重大协议偏差（必须披露）**：F2R_PLAN.json:376 预注册了 `skip_logic`（源 primary 失败则 RE 复评标记 NOT_RUN_PRIMARY_FAILED、0 start），但 executor/runner 未实现该分支，导致 RE-06-G1 在 DE-G1-02 SOLVER_FAILED 后仍执行 1 start/7 internal。实际 18/126；counterfactual 17/119；无新增有效观测、未超 caps、无 retry、无科学停；不属 INFRA/治理/窗口违规。A2 增补 eb4f6b8（F2R2_SKIP_LOGIC_AUDIT 96c811cc、verify 25/25）；A5 要求 RA-01、RA-03 为未来 F2-like 运行前置；RA-02/04/05/06 为携带整改/记录项（skip 语义+fail-closed 合同+回归测试+dry-run 策略模拟+closeout 对账+门禁 condition）。禁止把本批写成“17/119”或“19/133”。

## 4. T0：跨任务元学习代码基础（A5：T0_CODE_READINESS_PASS）

- **T0-1**：`meta/task_spec.py` v1.1.0 **d7267738…/81,219B**（TaskSpec/TaskFamily/TaskContextEncoder/任务指纹/active mask；`from_t0_4_candidate_yaml`；18 个任务与 T0-4 同源；18/18 applicability=DEFERRED_TO_M1_REAL_COLLECTION，real_training_ready=false；T0-1 合同 fb85c9cd…/167,540，family ada424cc…，split 11/4/3 seed42）。
- **T0-2**：`meta/meta_dataset.py` **da385389…**（EvaluationRecord/MetaDataset；support/query 任务内切分、meta_train/val/test 任务身份切分；泄漏 7/7 审计 PASS；sealed fixture 32；REAL_TRAINING_INGEST 默认 fail-closed；T0-1/T0-2 合同测试当前 31 passed（task-48 前 22；新增 9 项；A5 独立复跑））。
- **T0-3**：A2 commit 660071da（11 模块；interfaces **b5d3086c**、trainer **5ddd1a68**、warm_start **2bdc1f2a**、a3_adapter **1bb048be**；29 passed；封存 fixture 端到端冒烟 18/18；K=0/1/3/5；BO evals 8；resume 一致；模型权重/checkpoint SHA 可重放；core_sha 9ab5362d；physical 0）。
- **T0-4**：A3 commit 5832017（18 候选任务族 Mach{1.8,2.02,2.2}×h{15000,18288,20000}×CL{0.17,0.19}，family ada424cc…；split 11/4/3 seed42；18/18 admission=PENDING_M0_BY_DESIGN；status DRAFT_PENDING_M0_GO；M1 DRAFT 96 labels planned 98/686 hard 102/714；M3 planned 50/350 hard 52/364；全 pilot planned 148/1,036 hard 154/1,078；FOMAML K=[0,1,3,5]；budget/token null、not_authorization）。
- **C32 生产 fail-closed 入口**：A2 commit 9a9e294；`meta/production.py` **21d3e807…/27,663B**；强制显式 evaluator/solver/ledger+Lead authorization+TrainConfig；缺失/mock/synthetic/fixture/replay/TEST_ONLY/未 ready/SHA 不符/ledger run mismatch 全拒绝；检查通过前不建 run dir、不写 checkpoint/ledger、不启 solver；20 tests，21 scenarios 16 REFUSED；A5 直接 probe 缺 provider → refused、missing_roles=[evaluator,solver,ledger]、run_dir_created=false。
- **A5 G-T0-READY-02**（commit **318c5ac**）：gate **8f0743dd…/25,469**、MD 4650f240…/11,442、checklist cd308ca5…/15,163；51 checks=42 PASS+8 PASS_WITH_DISCLOSURE+1 NOT_APPLICABLE_BY_DESIGN+0 BLOCKED+0 FAIL；C32=PASS、C36=NOT_APPLICABLE_BY_DESIGN、C51=PASS；A5 独立 pytest 112 passed（A2 T0-3 29+C32 20+A3 合同 31+配置 32）；T0-4 SUMS 6/6。
- **就绪判定的准确含义**：`ready_for_real_meta_training=false`。本 gate 认证的是“**代码基础可运行、可重放、任务级无泄漏、生产入口 fail-closed**”；真实任务适用域（每任务 REAL_VSPAERO 证据）、真实多任务标签、真实训练与 K-shot 对照属 Issue #11 M0/M1，须在 #11 另签 G-T0-ADMISSION-01 与真实批次 approval/GO。**DEFERRED 不得写成 PASS；不得把本 gate 当作 #11 执行授权。**
- 审计历史（公开）：首版 G-T0-READY 曾判 T0_BLOCKED_WITH_PARTIAL_CREDIT；Lead L-28 依 Issue 原文把“T0 代码就绪”与“真实训练 admission”拆开，A5 范围更正 addendum 7703bce 接受；修复 C32 与 T0-1/T0-4 同源后重发。旧 gate 字节未改。

## 5. 数值门禁与预算治理（摘要）

- F1：Group A 同输入 3/3（F1R2 4/4）polar SHA 相同=PASS，否则 |ΔCDi|≤1e-9 且 |ΔCL|≤1e-9 = PASS_WITH_DISCLOSURE；相对/绝对均≤1e-3 = PASS_WITH_DISCLOSURE；更差 FAIL；同 x12 构建状态 >2 或 E3 则 FAIL（F1R2 单状态，披露）；同升力残差≤1e-4、D_i_N 独立复算≤1e-12；CL-α 预注册 alpha [-2,0,2,4,6,8,10]、线性插值、无 bracket=LIFT_TARGET_UNREACHABLE、NaN=SOLVER_NONCONVERGED、R²≥0.99。
- F2：预注册 invalid+failed/16 >25% 或 numerator≥5 自动停；INFRA_ERROR 硬停不重试，max_retries=0；失败目标 null；全部启动计费；候选独立复评一致性 |ΔCDi|/CDi≤1e-3；U_mesh unavailable、无 2U 增益规则，允许 PASS_WITH_NO_GAIN。
- T0：真实/合成 fail-closed 隔离；meta split 按任务身份；support/query 任务内；训练成本与标签成本分离；checkpoint/seed/SHA 可重放；真实训练启动前必须过生产入口与 lead authorization。
- 账本：五口径分离（physical_solver_starts_actual / internal_solver_cases_actual / planned_reserved / design_evaluations / cached_reads）；internal=7×starts 守恒；actual 与 charged 分列；失败计费、禁止 retry 掩盖。

## 6. 代码 SHA、提交与证据位置（本地工作树，未 push 的以 commit SHA 为准）

- F0 远端基线：**4504bb75cc32e334cf9f906ad2dcda9a7ff9b471**（分支 research/dfixed001-fixed-loop，GitHub 可读）。
- F1R2：A1 closeout **58ffe4d**；runner **b5ebe48a…/108,912B**；executor **ed0f2324…/92,286B**；approval **67a2d062**；GO **a84242a0**；run dir D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/dreal001/f1r2/runs/DREAL001-F1R2-20261113-01（653 文件，冻结）。
- F2R2：rev6b 包 **0ab25d3**；approval **13515f5d…/26,877B**；GO **1c07bdfc…/4,680B**；run dir D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/f2r/runs/DREAL001-F2R2-20261113-01（436 文件/45,005,145B，冻结）；ledger **7a342ef3…/24,904B**；run_result **0089f444…/364,756B**。
- T0：A2 **9a9e294**（production.py 21d3e807、trainer 5ddd1a68、warm_start 2bdc1f2a、interfaces b5d3086c）；A3 **5832017**（task_spec d7267738、meta_dataset da385389、T0-4 六文件 SUMS 121ec4d4）；A5 gate **318c5ac**（8f0743dd/4650f240/cd308ca5）。
- 阶段报告全文（本评论同文）与索引：Lead 工作树 docs/receipts/dreal001/；本报告 SHA256 将在发布后以评论勘误/索引补充。A5 独立复核记录见 §8。

## 7. 明确不宣称的内容

- 不宣称 12 维全部有效（V01/V02 等按实际证据/掩码处理；F1R2 为 12D_ACTIVE 登记但单变量响应证据有限）。
- 不宣称优化增益、winner、排名、p 值/CI/显著性、跨族平均；F2R2 是 **NO_GAIN**。
- 不宣称外部物理/整机阻力/燃油/配平/稳定性 PASS；fuel_burn_kg=null、外部物理 NOT_VALIDATED。
- 不把 F1 旧批、F1R-01、F2R-01 的失败当作科学结论；它们只作 INFRA/物理缺陷记录，均已冻结、不可复用。
- 不把 T0_CODE_READINESS_PASS 当作 #11 真实训练授权；#11 首批仍须 M0 冻结+A5 admission+新 approval/GO。
- 不复用 #9 R10 的 approval/window/token/额度；R1–R10 历史不可变。

## 8. A5 独立复核与本汇报签署

- A5 已签署 F0（ec62229）、F1（4a2c079）、F1R2（fd1ab768 + abcc3976）、F2R2（7ed9c9e4 + 64549a46）、T0（318c5ac）。
- **A5 独立复核（已签署）**：复核对象为本报告修正前版本 SHA256 ff43d5a9…/19,200B；A5 commit **896ab6e**（docs/reviews/dreal001_a5_issue10_report_review_20261113.json 67F9F6A9…/13,556B、.md 95C07DAF…/10,537B）；verdict **ISSUE10_STAGE_REPORT_REVIEW_PASS_WITH_MINOR_CORRECTIONS_REQUIRED**，signature_status **A5_SIGNED_SUBJECT_TO_LISTED_CORRECTIONS**。核心数字/commit/SHA/预算双口径（actual 65/455、charged 70/490）/三层结论/fuel null/物理 NOT_VALIDATED 均核验一致，未发现越权授权；C-01..C-07 已逐条落实（单位、测试数、容差、停批阈值、U_wake 限定、E3 G1 预计算、RA 范围），修正不改变结论。A5 physical_call_count=0。

## 9. 下一步：#11 D-META-REAL-001（已具备启动条件）

1. **M0 冻结**：真实任务族（18 候选→首批 6 任务 4train/2val/0test？以 A5 M0 审查为准）、每任务预算、split、统计端点、K=[0,1,3,5]、FOMAML 配置、失败/停机阈值；A5 出 **G-T0-ADMISSION-01**（真实适用域、标签采集、预算/泄漏/梯度接口）。
2. **M1 真实多任务标签采集**：按 M0 批准的小批（DRAFT planned 98/686、hard 102/714；实际首批以 M0 冻结为准）执行 VSPAERO，A5 判 REAL_MULTITASK_DATA_PASS；真实标签不得用合成/mock/replay 替代。
3. **M2 真实 FOMAML 训练**：production entry 强制真实 evaluator/solver/ledger；checkpoint/seed/SHA 可重放；A5 判 REAL_META_TRAINING_EXECUTED。
4. **M3 严格留出 K-shot 对照**：Random/Sobol-BO、Pretrain-Kshot-BO 等预算对照，允许 NO_EVIDENCE/NEGATIVE_TRANSFER。
5. 所有批次另立 authorization_id/run_id/approval.json/GO，A5 预审+Lead GO；不复用 #9 R10 或 F1/F2 已消耗 approval。

> 结论：Issue #10 的 F0/F1/F2/T0 工作包均已达到可审计的工程闭环/代码就绪状态；F2 无增益证据（合法），T0 为 CODE_READINESS_PASS（真实训练 admission 属 #11）。下一步按 #11 启动真实多任务标签采集与 FOMAML 训练。
