# A5 M0-R Gate Conditions — G-M0R-ADMISSION-01（DRAFT，未签发）

- status: **DRAFT_NOT_ISSUED**；不是 gate/admission/authorization/approval/GO。
- conditions: 42 = A5 R01–R30（30）+ G01–G12（12）。

| ID | 类别 | 严重度 | 条件 | 验收 | 来源 |
|---|---|---|---|---|---|
| R01 | package | CRITICAL | M0-R 必须是全新包、新 family SHA、新 task ID；不得复用 ada424cc/40fdd436/旧 18-task 字节；旧 T0-4/A3 M0 字节不改，只作历史。 | 新包 commit/SUMS；family_sha256 非 ada424cc；旧 SHA 只出现在 superseded 披露 | A5_M0R_REQUIREMENTS_20261113 |
| R02 | geometry | CRITICAL | 任务族几何必须重绑 post-fix 546x480 链：openvsp_geometry d20ee7ad；baseline vspgeom 16da482a/225,414B/546x480；F1R2 12D audit 7a90b977；40fdd436 不得出现在 active family。 | 6 tasks geometry_sha256=16da482a…；零物理复建 2/2 字节一致；无 40fd active 引用 | A5_M0R_REQUIREMENTS_20261113 |
| R03 | executor | CRITICAL | task-capable executor：逐任务注入 Mach/alt/CL/Vinf/Rho/ReCref/q；6 个 per-task .vspaero deck；任务缺失 fail-closed；零物理 dry-run。 | executor 接口/单测；6 deck SHA；M2.02 deck 与 F1R2 同参数（Vinf/Rho/ReCref/Mach/alpha）；spawn=[]；physical=0 | A5_M0R_REQUIREMENTS_20261113 |
| R04 | q_source | CRITICAL | q 单源 ATM-F1R2；q 由实际注入 Vinf/Rho 复算 rel≤1e-12；6 任务 q 精确等于 20483.940233430174/24297.194081414087/16265.063806566453；禁止 ISO 混用。 | A5 独立复算 6/6 rel≤1e-12；代码仅一处大气模块；无第二套 q/L_ref | A5_M0R_REQUIREMENTS_20261113 |
| R05 | lift_reference | CRITICAL | L_ref=q*SREF_REF*CL_target；SREF_REF 运行时由 post-fix baseline 几何重算并 SHA 绑定，不得硬编码 358.25；m_task=L_ref/g0；质量带 100–190 t；LREF-1..8 fail-closed。 | 6 任务 L_ref/mass 精确匹配 L-30-A01；SREF_REF 运行时字段/SHA；越界或 fallback 即 fail-closed | A5_M0R_REQUIREMENTS_20261113 |
| R06 | tasks | CRITICAL | 只保留 L-30-A01 的 6 任务；固定 18,288 m；3 train/1 val/2 test；meta_test 盲；删除全部高度缩放副本。 | 6 tasks 因子/ID/split 全匹配；无 15/20 km task；meta_test 在 M1/M2 不运行、不揭盲 | A5_M0R_REQUIREMENTS_20261113 |
| R07 | design_space | CRITICAL | 设计空间同时绑 raw YAML 8b29d1e3…/10,846B 与 C01–C04 cross constraints；M1 sampler/executor 强制执行 check_cross_constraints。 | raw SHA + C01–C04 字段/SHA；负例测试拒绝违反 C01–C04；canonical hash 不能替代 cross constraints | A5_M0R_REQUIREMENTS_20261113 |
| R08 | alpha_lift | CRITICAL | 7 点 alpha 固定；max_refine_sweeps 统一（0 或明确 refine 列表）；不得 frozen=0/tasks=2 矛盾；报告独立升力残差与插值不确定性。 | 单值 max_refine；alpha_refine 明确；C2 残差独立复算；低 CL 插值不确定性>1e-3 时预注册加密或 A5 预签放宽 | A5_M0R_REQUIREMENTS_20261113 |
| R09 | mask | HIGH | 12D_ALL_ACTIVE；10D_ACTIVE_PLUS_2_INACTIVE=DEFERRED_TO_M1；更正 “no zero-effect evidence” 文本。 | mask 字段/文本；F1R2 C3/C4 证据引用；不得声明 V01/V02 无效 | A5_M0R_REQUIREMENTS_20261113 |
| R10 | effect_threshold | HIGH | MIN_EFFECT_REL>0 并预注册；建议 max(2×U_within,1e-3)；不得用 0.0。 | 常量/字段>0；单测；A5 复核阈值定义 | A5_M0R_REQUIREMENTS_20261113 |
| R11 | cross_task | CRITICAL | M1-A CTX-A/B 预注册：4 任务×3 设计；效应量分离 ≥max(2U_within,1e-3)；3 设计下 Spearman 仅描述性，不得做 p 值/显著性；TOO_SIMILAR 规则保留。 | CTX-A/B 定义/阈值；4/4 任务可分或 PHYSICAL_TASK_FAMILY_BLOCKED；披露 n=3 限制 | A5_M0R_REQUIREMENTS_20261113 |
| R12 | budget | CRITICAL | M1-A 15 starts/105 internal，caps 18/126，retry 0；4 任务×3 设计+1 exact repeat+2 preflight；repeat 必须预注册 task/design/deck SHA。 | 预算表/算术；repeat 预注册；无额外设计/任务；五口径 | A5_M0R_REQUIREMENTS_20261113 |
| R13 | budget | CRITICAL | M1-B 66/462 caps 70/490；4 任务×16 designs=64 labels+2 preflight；retry 0。 | 仅 M1-A 通过后单独授权；预算/标签表 | A5_M0R_REQUIREMENTS_20261113 |
| R14 | budget | CRITICAL | M3-A 34/238 caps 38/266；2 test 任务×16=32 labels+2 preflight；retry 0；M3 前不得运行 meta_test。 | 单独授权；揭盲流程；任务级 n=2 描述性 | A5_M0R_REQUIREMENTS_20261113 |
| R15 | budget | CRITICAL | 总预算 planned 115/805，hard 126/882，labels 96，preflight 6，retry 0；M3-B 不授权。 | 汇总算术；M3-B NOT_AUTHORIZED；charged/actual 分离 | A5_M0R_REQUIREMENTS_20261113 |
| R16 | admission | CRITICAL | admission=DEFERRED_TO_M1A_WITH_PRE_REGISTERED_CHECKS；M0/M0-R 不签 admission；首条真实 M1 标签按 validity/status/identity 判定，不按目标值。 | admission 字段；schema；M0-R 无 PASS 声明；M1-A 后才可申请 | A5_M0R_REQUIREMENTS_20261113 |
| R17 | authorization | CRITICAL | M0-R 零物理；不创建 run dir/ledger/token/authorization；不复用 #9 R10 或 #10 F1R2/F2R2 approval/token。 | physical=0；run_dir/ledger false；not_authorization=true；新 D-META-M1A-001 等仅在未来单独签 | A5_M0R_REQUIREMENTS_20261113 |
| R18 | a5 | CRITICAL | A5 独立复核/门禁 G-M0R-ADMISSION-01；M0-R 包到后先 gate，不得先签 admission；A5 physical=0。 | A5 checklist/gate/SUMS；commit；不 push | A5_M0R_REQUIREMENTS_20261113 |
| R19 | evidence_text | HIGH | T0-4/M0-R 必须删除 “A5 P1-05 verified envelope 1.8/2.02/2.2”；P1-05 实际 1.8/2.0/2.2、18,288m、旧 58f63/199,997B、TREND_ONLY、2.02 NOT_COMPARABLE。 | 新文本/manifest；不得引用不存在的 A5 结论；如保留 1.6/2.4 排除，需新工程理由或校准 | A5_M0R_REQUIREMENTS_20261113 |
| R20 | review_correction | INFO | A5 记录 A1 F-M0-02 事实更正：40fdd436=543x472/227,247B；199,997B/483x418 是 P1-05 58f63bfc；阻断结论不变。 | gate 披露；A1 复核可引用更正 | A5_M0R_REQUIREMENTS_20261113 |
| R21 | task_metadata | CRITICAL | 每 task 记录 Mach/alt/CL/q/Vinf/Rho/ReCref/L_ref/mass/SREF_REF/task fingerprint/geometry SHA/evaluator/solver；任务 ID 不得复用旧 ada424cc 任务 ID。 | 6 任务表；A5 逐字段复算 | A5_M0R_REQUIREMENTS_20261113 |
| R22 | deck | CRITICAL | 每 task 独立 .vspaero deck；同一设计跨 task 复用同一 vspgeom 字节（build once）；per-task 记录 vspgeom/polar/deck SHA。 | 6 deck；vspgeom 字节 equality；SHA 表；零物理 dry-run | A5_M0R_REQUIREMENTS_20261113 |
| R23 | consistency | CRITICAL | q/L_ref/Sref 三重一致：q 由 deck 实际注入；L_ref=q*SREF_REF*CL；Sref(x) 逐设计；D_i=q*Sref(x)*CDi；A5 独立复算。 | rel≤1e-12；W01 交叉 rel≤1e-6；无第二套公式 | A5_M0R_REQUIREMENTS_20261113 |
| R24 | geometry_identity | HIGH | baseline SHA 与 per-design SHA 分开；M1 每设计记录 vspgeom SHA；不得用一个 40fd/16da 代表所有设计。 | per-design vspgeom SHA 字段；baseline 只作族身份 | A5_M0R_REQUIREMENTS_20261113 |
| R25 | expected_polar | HIGH | M2.02 可作 F1R2 连续性锚点；2.2/1.8 不继承 F1R2 expected polar；M1-A 重建 admission baseline。 | expected/polar 字段；披露；不得用 F1R2 8f4c 作 2.2/1.8 expected | A5_M0R_REQUIREMENTS_20261113 |
| R26 | fail_closed | CRITICAL | 任何 task/atmosphere/SREF/geometry/mass/q 校验失败必须 fail-closed；禁止回退到 358.25、旧几何、ISO、旧 task 或旧 token。 | 负例测试；失败码；无 fallback | A5_M0R_REQUIREMENTS_20261113 |
| R27 | evidence | CRITICAL | M0-R 包/证据必须含 SUMS、validation、zero-physical dry-run、6 deck、A5 复算、无 solver 证据；commit 不 push。 | SUMS 全匹配；A5 独立 pytest/dry-run；spawn=[]；physical=0 | A5_M0R_REQUIREMENTS_20261113 |
| R28 | gate_process | CRITICAL | M0-R gate 新 ID G-M0R-ADMISSION-01；旧 G-T0-ADMISSION-01 保持 M0_BLOCKED 历史；不得复用旧 gate commit/SHA。 | 新 gate json/md/checklist/SUMS；旧字节不改 | A5_M0R_REQUIREMENTS_20261113 |
| R29 | m1_process | CRITICAL | M1-A 通过 A5 后单独 authorization/approval/GO；M1-A 结果只给 admission verdict，不自动授权 M1-B/M3。 | M1-A 新 gate；M1-A PASS/FAIL；不自动后续 | A5_M0R_REQUIREMENTS_20261113 |
| R30 | claims | CRITICAL | 不得宣称 winner/显著性/优化增益/跨族可比；fuel_burn_kg=null；外部物理 NOT_VALIDATED；单 seed 描述性；M3 任务级 n=2。 | prereg/回执措辞；无禁用词；披露 | A5_M0R_REQUIREMENTS_20261113 |
| G01 | gate | CRITICAL | M0-R 包必须由 A3 task-57 正式冻结并 commit；task-60 pre-draft 不得作为正式包。 | package commit/status；pre-draft 标记 | R01/R28 |
| G02 | gate | CRITICAL | G-M0R-ADMISSION-01 为新 gate ID；不得复用 G-T0-ADMISSION-01 commit/SHA/字节。 | 新 gate 产物；旧 gate diff=0 | R28 |
| G03 | binding | CRITICAL | gate 绑定 L-30 27f8d91、L-30-A01 30166a0、L-31 544629a、A5 requirements f8b70703/16,397/30 条。 | SHA/bytes 全匹配 | R01 |
| G04 | package | CRITICAL | M0-R 包含新 family SHA、6 TaskSpec、6 deck、raw YAML+C01–C04、validation、zero-physical dry-run、SUMS；A5 逐行复算。 | 包内文件/SUMS N/N | R01/R27 |
| G05 | zero_physical | CRITICAL | A5 gate 全程 physical=0；不启 solver、不建 run dir/ledger/token；spawn=[]。 | 独立证据 | R17/R18 |
| G06 | gate_result | CRITICAL | verdict 只可 READY_FOR_M1A_ADMISSION 或 M0R_BLOCKED；不得签 admission、不得 ready_for_real_meta_training=true。 | verdict 字段 | R16/R18 |
| G07 | m1_authorization | CRITICAL | gate PASS 不授权 M1；M1-A 需新 authorization/approval/A5/Lead GO；不复用 #9/#10 token。 | 后续流程 | R29 |
| G08 | budget | CRITICAL | M1-A 15/105 caps18/126 retry0；repeat 预注册 exact task/design/deck SHA；spare 3/21 不得额外用。 | 预算/repeat 字段 | R12 |
| G09 | budget | CRITICAL | M1-B 66/462 caps70/490 labels64；M3-A 34/238 caps38/266 labels32；总 115/805 hard126/882 labels96 preflight6 retry0；M3-B 不授权。 | 预算/算术 | R13-R15 |
| G10 | ctX | CRITICAL | CTX-A/B 4 任务×3 设计；效应量≥max(2U_within,1e-3)；Spearman n=3 只描述性、无 p 值；4/4 可分或 PHYSICAL_TASK_FAMILY_BLOCKED。 | CTX 定义/结果 | R11 |
| G11 | claims | CRITICAL | 不得 winner/显著性/优化增益/跨族；fuel=null；外部物理 NOT_VALIDATED；单 seed 描述性；M3 任务级 n=2。 | prereg/回执措辞 | R30 |
| G12 | change_control | CRITICAL | gate 后任何包字节/接口/预算/任务/几何变化必须新 revision + 重出 gate；不得口头/单方面修改。 | 变更记录；新 gate | R28 |

## 关键边界

- M0-R 零物理；不创建 run dir/ledger/token/authorization；M0-R 通过前不得启动 solver。
- G-M0R-ADMISSION-01 只给 READY_FOR_M1A_ADMISSION / M0R_BLOCKED，不签 admission、不 ready_for_real_meta_training=true。
- M1-A/M1-B/M3 各自新 authorization/approval/A5/Lead GO；不复用 #9 R10、#10 F1R2/F2R2 token。
- fuel_burn_kg=null；外部物理 NOT_VALIDATED；不得 winner/显著性/优化增益/跨族。
