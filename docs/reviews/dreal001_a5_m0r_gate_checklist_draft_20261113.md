# A5 M0-R Gate Checklist — G-M0R-ADMISSION-01（DRAFT，未签发）

- gate_id: **G-M0R-ADMISSION-01**
- status: **DRAFT_NOT_ISSUED_AWAITING_M0R_PACKAGE**
- 性质: 预置草稿；不是 gate、不是 admission、不是 authorization/approval/GO，不授权 M1，不启动 solver。
- 目标: Issue #11 M0-R；A3 task-57 正式包（task-60 pre-draft 不算）。
- 依据: L-30 27f8d91 / L-30-A01 30166a0 / L-31 544629a / A5 requirements f8b70703…/16,397B/30 条。
- 旧 gate: G-T0-ADMISSION-01 commit 24ccdb5、json 422df1b5…、verdict M0_BLOCKED / PHYSICAL_TASK_FAMILY_BLOCKED，保持历史不改。

## 1. 计数与覆盖

- checks: 60（全部 PENDING_M0R_PACKAGE，包到后逐项判 PASS/PWD/FAIL/BLOCKED）。
- conditions: 42 = A5 R01–R30（30）+ 新增 G01–G12（12）。
- 预算: M1-A 15/105 caps 18/126；M1-B 66/462 caps 70/490；M3-A 34/238 caps 38/266；总 115/805 hard 126/882；labels 96；preflight 6；retry 0；M3-B 不授权。
- 科学限制: 6 任务 3 train/1 val/2 blind test；ATM-F1R2 单源；SREF_REF 运行时重算；12D active/10D deferred；MIN_EFFECT>0；CTX n=3 只描述性。

## 2. Checklist（60 项）

| ID | 类别 | 严重度 | 检查项 | 期望 | 来源 |
|---|---|---|---|---|---|
| MRC-01 | package | CRITICAL | M0-R 包为全新 commit/目录，不修改旧 T0-4/A3 M0/F1/F2/R1-R10 字节；新 family_sha256 非 ada424cc、非 40fdd436。 | commit/SUMS；旧 SHA 仅出现在 superseded；旧树 diff=0 | R01 |
| MRC-02 | package | CRITICAL | M0-R 包内 SHA256SUMS 覆盖全部交付文件；A5 逐行复算全匹配。 | SUMS N/N；0 mismatch | R27 |
| MRC-03 | gate | CRITICAL | gate 使用新 ID G-M0R-ADMISSION-01，不复用 G-T0-ADMISSION-01 commit/SHA/字节。 | 新 gate json/md/checklist/conditions/SUMS；旧 gate 不改 | R28 |
| MRC-04 | binding | CRITICAL | gate 绑定 L-30 27f8d91、L-30-A01 30166a0、L-31 544629a、A5 requirements f8b70703…/16,397B/30 条。 | SHA/bytes 全匹配 | R01/R28 |
| MRC-05 | zero_physical | CRITICAL | M0-R 全程零物理：physical_call_count=0；无 run dir/ledger/token/authorization；无 solver spawn。 | A5 独立检查；spawn=[]；run_dir/ledger false | R17/R27 |
| MRC-06 | geometry | CRITICAL | 任务族几何重绑 post-fix 546x480：baseline vspgeom 16da482a…/225,414B；openvsp_geometry d20ee7ad；F1R2 12D audit 7a90b977。 | 6 tasks geometry=16da；零物理复建 2/2 字节同 | R02 |
| MRC-07 | geometry | CRITICAL | 40fdd436…/543x472/227,247B 不得出现在 active family；只可作 historical/superseded。 | active 引用 0；披露含 40fd 历史 | R02 |
| MRC-08 | geometry | HIGH | 每设计记录 vspgeom SHA；baseline SHA 只作族身份；不得以单一 SHA 代表所有设计。 | per-design 字段；baseline 分开 | R24 |
| MRC-09 | tasks | CRITICAL | 6 任务 ID/因子与 L-30-A01 完全一致；alt 全 18,288 m；无 15/20 km 副本。 | 6/6 字段匹配；alt set={18288} | R06/R21 |
| MRC-10 | tasks | CRITICAL | split 3 train/1 val/2 blind test；meta_test 盲、不在 M1/M2 运行、不揭盲。 | split 集合/计数；盲测流程 | R06 |
| MRC-11 | tasks | CRITICAL | 每 task 记录 Mach/alt/CL/q/Vinf/Rho/ReCref/L_ref/mass/SREF_REF/fingerprint/geometry/evaluator/solver；ID 非旧 ada424cc。 | 6 任务表；A5 逐字段复算 | R21 |
| MRC-12 | atmosphere | CRITICAL | q 单源 ATM-F1R2；p=7171.544888256813、T=216.65、R=287.05287、rho=0.1153178340089936、a=295.06801842964956、ReCref=89,397,005.8767656。 | 字段/复算一致；仅一处大气模块 | R04 |
| MRC-13 | atmosphere | CRITICAL | 6 任务 q 精确等于 20,483.940233430174（M2.02）/24,297.194081414087（M2.2）/16,265.063806566453（M1.8），rel≤1e-12。 | A5 6/6 复算；无 ISO 混用 | R04 |
| MRC-14 | atmosphere | HIGH | Vinf 6 任务精确匹配 596.0373972278921（2.02）/649.14964（2.2）/531.122433（1.8），rel≤1e-12。 | 6/6 复算 | R04 |
| MRC-15 | atmosphere | HIGH | 披露 ATM-F1R2 vs ISO-1 q rel≈1.24e-5；M2.02 与 F1R2 连续；2.2/1.8 不继承 F1R2 expected polar。 | prereg/task metadata 含披露 | R25 |
| MRC-16 | lift_reference | CRITICAL | L_ref=q*SREF_REF*CL_target；SREF_REF 运行时由 post-fix baseline 重算并 SHA 绑定；不得硬编码 358.25，不得 fallback。 | SREF 字段/SHA；grep 358.25 active=0；负例 fail-closed | R05 |
| MRC-17 | lift_reference | CRITICAL | 6 任务 L_ref/mass 精确匹配 L-30-A01：1,247,523.170066/127.211960；1,394,290.601839/142.178073；1,479,759.862543/150.893512；1,653,849.258137/168.645690；990,583.048479/101.011359；1,107,122.230653/112.895049。 | A5 复算 6/6 rel≤1e-12 | R05 |
| MRC-18 | lift_reference | HIGH | 质量带 100–190 t；6 任务 mass 全在带内；越界 fail-closed。 | min/max 检查；负例 | R05 |
| MRC-19 | lift_reference | HIGH | LREF-1..8 fail-closed 检查存在且单测覆盖；不得 fallback 到旧 L_ref/旧几何/ISO。 | 代码/负例；无 fallback | R26 |
| MRC-20 | executor | CRITICAL | task-capable executor 逐任务注入 Mach/alt/CL/Vinf/Rho/ReCref/q；任务缺失 fail-closed。 | 接口/单测；缺任务负例 | R03 |
| MRC-21 | executor | CRITICAL | 6 个 per-task .vspaero deck；deck SHA 进包；M2.02 deck 与 F1R2 参数（Mach 2.02/Vinf/Rho/ReCref/alpha）一致。 | 6 deck SHA；A5 读 deck 核字段 | R03/R22 |
| MRC-22 | executor | HIGH | 同一设计跨 task 复用同一 vspgeom 字节（build once）；per-task 记录 vspgeom/deck/polar SHA。 | vspgeom equality；SHA 表 | R22 |
| MRC-23 | dry_run | CRITICAL | 零物理 dry-run 覆盖 6 任务×3 参考设计；spawn=[]、solver_outputs=[]、physical=0、无 run dir。 | A5 独立 run/复核证据 | R03/R27 |
| MRC-24 | design_space | CRITICAL | 设计空间同时绑 raw YAML 8b29d1e3…/10,846B 与 C01–C04 cross constraints。 | raw SHA；C01–C04 字段/SHA | R07 |
| MRC-25 | design_space | CRITICAL | M1 sampler/executor 强制执行 check_cross_constraints；违反 C01–C04 负例被拒。 | 代码/负例；canonical 不替代 | R07 |
| MRC-26 | alpha_lift | CRITICAL | 7 点 alpha 固定；max_refine_sweeps 单值（0 或明确列表）；alpha_refine 明确；无 frozen=0/tasks=2 矛盾。 | 单值/列表；一致性检查 | R08 |
| MRC-27 | alpha_lift | CRITICAL | 报告独立升力残差与插值不确定性；C2 残差不得仅由构造性插值得到。 | 独立复算；残差/不确定性 | R08 |
| MRC-28 | mask | HIGH | 12D_ALL_ACTIVE；10D_ACTIVE_PLUS_2_INACTIVE=DEFERRED_TO_M1；不得声明 V01/V02 零效应。 | mask 字段；corrected text | R09 |
| MRC-29 | effect_threshold | HIGH | MIN_EFFECT_REL>0 且预注册；建议 max(2×U_within,1e-3)；不得 0.0。 | 常量/字段/单测；A5 复核定义 | R10 |
| MRC-30 | cross_task | CRITICAL | M1-A CTX-A/B 预注册：4 任务×3 设计；效应量分离≥max(2U_within,1e-3)；Spearman n=3 仅描述性、无 p 值。 | 定义/阈值；披露 n=3 | R11 |
| MRC-31 | cross_task | CRITICAL | 4/4 任务可分或 PHYSICAL_TASK_FAMILY_BLOCKED；不得仅整体乘常数的表面迁移。 | CTX 结果/阻断流程 | R11 |
| MRC-32 | budget | CRITICAL | M1-A 15/105 caps 18/126 retry0；4 任务×3 设计+1 exact repeat+2 preflight；repeat 预注册 task/design/deck SHA。 | 预算/算术/repeat 字段 | R12 |
| MRC-33 | budget | CRITICAL | M1-B 66/462 caps 70/490 retry0；64 labels+2 preflight；仅 M1-A 通过后单独授权。 | 预算/标签/授权边界 | R13 |
| MRC-34 | budget | CRITICAL | M3-A 34/238 caps 38/266 retry0；32 labels+2 preflight；M3 前不运行 meta_test。 | 预算/揭盲流程 | R14 |
| MRC-35 | budget | CRITICAL | 总 115/805 hard 126/882 labels96 preflight6 retry0；M3-B NOT_AUTHORIZED。 | 汇总算术；M3-B 字段 | R15 |
| MRC-36 | accounting | CRITICAL | 五口径账本（physical/charged/cached/design/planned）分离；charged vs actual 双报；不得混写。 | 账本 schema/模板 | R15/R27 |
| MRC-37 | admission | CRITICAL | admission=DEFERRED_TO_M1A_WITH_PRE_REGISTERED_CHECKS；M0/M0-R 不签 admission；首条真实 M1 标签按 validity/status/identity 判定，不按目标值。 | 字段/schema；无 PASS 声明 | R16 |
| MRC-38 | authorization | CRITICAL | M0-R 不创建 run dir/ledger/token/authorization；不复用 #9 R10 或 #10 F1R2/F2R2 approval/token。 | 零物理检查；token/approval 搜索 | R17 |
| MRC-39 | authorization | CRITICAL | M1-A/M1-B/M3 各自新 authorization/approval/A5/Lead GO；M1-A 结果不自动授权后续。 | 流程字段；无自动继承 | R29 |
| MRC-40 | evidence_text | HIGH | 删除 “A5 P1-05 verified envelope 1.8/2.02/2.2”；P1-05 实际 1.8/2.0/2.2、18,288m、58f63bfc/199,997B、TREND_ONLY、2.02 NOT_COMPARABLE。 | 文本/manifest；不得引用不存在结论 | R19 |
| MRC-41 | evidence_text | INFO | 记录 A1 F-M0-02 事实更正：40fd=543x472/227,247B；199,997B/483x418 是 P1-05 58f63bfc。 | 披露/引用 | R20 |
| MRC-42 | consistency | CRITICAL | q/L_ref/Sref 三重一致：q 由 deck 实际注入；L_ref=q*SREF_REF*CL；Sref(x) 逐设计；D_i=q*Sref(x)*CDi。 | A5 独立复算 rel≤1e-12；无第二公式 | R23 |
| MRC-43 | consistency | HIGH | W01 交叉校验 rel≤1e-6；q/L_ref/Sref 无第二套硬编码。 | 交叉检查/代码搜索 | R23 |
| MRC-44 | fail_closed | CRITICAL | 任何 task/atmosphere/SREF/geometry/mass/q 校验失败必须 fail-closed；禁止回退 358.25/旧几何/ISO/旧 task/旧 token。 | 负例测试；失败码；无 fallback | R26 |
| MRC-45 | validation | CRITICAL | M0-R 包含 validation、zero-physical dry-run、6 deck、A5 复算、无 solver 证据；commit 不 push。 | validation/dry-run/证据/SUMS | R27 |
| MRC-46 | claims | CRITICAL | 不得宣称 winner/显著性/优化增益/跨族可比；fuel=null；外部物理 NOT_VALIDATED；单 seed 描述性；M3 任务级 n=2。 | prereg/回执措辞；无禁用词 | R30 |
| MRC-47 | scientific | HIGH | 3 train/1 val/2 test 限制写入 prereg：单 val 不足稳健早停/模型选择；M2 固定 epoch 或 leave-one-train-out；不得据单 val 宣称泛化。 | prereg 文本 | R30/科学限制 |
| MRC-48 | scientific | HIGH | 2 test 均 Mach 1.8：仅低马赫外推、无跨 Mach 测试；不得跨族/跨 Mach 泛化。 | prereg 文本 | R30/科学限制 |
| MRC-49 | scientific | HIGH | task-level 2 test tasks 只可描述性/配对区间；NO_EVIDENCE 可能；不得显著性/winner。 | prereg 文本 | R30/科学限制 |
| MRC-50 | scientific | HIGH | 6 任务为 Mach×CL、无高度因子；质量为目标巡航质量、无燃油模型；fuel=null。 | prereg 文本 | R30/科学限制 |
| MRC-51 | gate_input | CRITICAL | A3 M0-R 包由 task-57 正式冻结；task-60 pre-draft 不得被当作正式包/不得冻结。 | commit/状态；pre-draft 标记 | R01/R28 |
| MRC-52 | gate_input | CRITICAL | A1 task-56 U1/U2 已交付且 6-task 零物理 dry-run 冻结；接口变更后 gate 作废重出。 | A1 commit/证据；接口 SHA | R02/R03/R27 |
| MRC-53 | gate_input | CRITICAL | A5 requirements R01–R30 逐条映射到本 checklist/conditions；无遗漏。 | 映射表 30/30 | R01-R30 |
| MRC-54 | gate_input | HIGH | L-31 与 requirements 引用/数字一致；有冲突即先报 Lead 修正，不带冲突签 gate。 | L-31 一致性记录 | L-31 |
| MRC-55 | gate_input | HIGH | 旧 G-T0-ADMISSION-01 保持 M0_BLOCKED 历史；新 gate 不改变旧字节/结论。 | 旧 commit 字节 diff=0 | R28 |
| MRC-56 | process | CRITICAL | A5 独立执行：不修补 M0-R 包、不改 A1/A3 字节、不启动 solver、不建 run dir/ledger；physical=0。 | A5 证据；spawn=[] | R18 |
| MRC-57 | process | CRITICAL | gate 结果只可为 READY_FOR_M1A_ADMISSION 或 M0R_BLOCKED；不得写 admission signed/ready_for_real_meta_training=true。 | verdict/字段 | R16/R18 |
| MRC-58 | process | HIGH | M0-R gate PASS 不授权 M1；M1-A 需单独 authorization/approval/GO；不得复用旧 token。 | 边界字段 | R29 |
| MRC-59 | evidence | HIGH | gate 产物含 checklist/conditions/gate json/md/SUMS；A5 commit；不 push；旧证据不覆盖。 | 文件/SHA/commit | R18/R27 |
| MRC-60 | accounting | HIGH | 预算/账本算术独立复算：M1-A 15=12+1+2、105=7×15；M1-B 66、462=7×66；M3-A 34、238=7×34；总 115、805=7×115。 | A5 算术；无 19/133 混写 | R12-R15 |

## 3. 判定规则

- 任一 CRITICAL FAIL/BLOCKED → **M0R_BLOCKED**；不得 M0_PASS。
- 全部 PASS，或仅非关键 PWD/INFO 且经 A5 书面接受 → 才可 **READY_FOR_M1A_ADMISSION**。
- READY_FOR_M1A_ADMISSION 不等于 admission、不等于 M1 授权；M1-A 必须新 authorization/approval/A5/Lead GO。
- 包字节/接口/预算/任务/几何任何变化 → 新 revision + 重出 gate，不得口头修改。

## 4. 产物与状态

- 本文件及同名 JSON 为 DRAFT；A3 task-57 包到后 25 分钟内转正式 gate（新 commit/SHA），旧 draft 保留历史但不作 gate。
- A5 physical_call_count=0；未启 solver；未建 run dir/ledger/token；未改 A1/A3/旧证据。
