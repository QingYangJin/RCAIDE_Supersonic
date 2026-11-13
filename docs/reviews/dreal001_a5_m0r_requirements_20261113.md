# A5 M0-R 要求清单 — Issue #11 M0-R（非授权）

- requirement_id: **A5-M0R-REQ-20261113**
- 签发: a5-review，2026-11-13T06:12:00Z
- current_gate: G-T0-ADMISSION-01 = M0_BLOCKED
- planned_next_gate: **G-M0R-ADMISSION-01**
- 性质: M0-R 最小重冻要求；不是 authorization/approval/GO；不签 admission；零物理。

## 1. 依据

- Issue #11 D-META-REAL-001；L-30（commit 27f8d91，md f54156c7…/11,483B，json 62991bcc…/4,431B）；L-30-A01（commit 30166a0，md 177dc4be…/3,689B，json 62616a8d…/2,460B）。
- A1 M0 复核（commit b4e4140；md 9a591772…/32,267B；json 643e3baa…/35,680B）；A3 M0 DRAFT（commit 1cee3e5；freeze 359f9f92…/69,346B）；A3 D3 blocked disclosure（commit 5bbca70；crosswalk a8044a2f…/19,867B）。
- L-30 第 3 节旧 q/L_ref 表作废，以 L-30-A01 为准。

## 2. 六个任务（ATM-F1R2，18,288 m，SREF_REF=358.25000000000006）

| 任务 | Mach | CL | q Pa | Vinf m/s | L_ref N | 质量 t | split |
|---|---:|---:|---:|---:|---:|---:|---|
| T18K_M202_CL017 | 2.02 | 0.17 | 20483.940233430174 | 596.0373972278921 | 1247523.170066 | 127.21196 | meta_train |
| T18K_M202_CL019 | 2.02 | 0.19 | 20483.940233430174 | 596.0373972278921 | 1394290.601839 | 142.178073 | meta_train |
| T18K_M220_CL017 | 2.2 | 0.17 | 24297.194081414087 | 649.14964 | 1479759.862543 | 150.893512 | meta_train |
| T18K_M220_CL019 | 2.2 | 0.19 | 24297.194081414087 | 649.14964 | 1653849.258137 | 168.64569 | meta_val |
| T18K_M180_CL017 | 1.8 | 0.17 | 16265.063806566453 | 531.122433 | 990583.048479 | 101.011359 | meta_test_blind |
| T18K_M180_CL019 | 1.8 | 0.19 | 16265.063806566453 | 531.122433 | 1107122.230653 | 112.895049 | meta_test_blind |

- q 单源 ATM-F1R2；与 ISO 差 1.24e-5 已披露；M2.02 与 F1R2 连续；2.2/1.8 不继承 expected polar；不得混用 ISO。
- 质量 101.011359–168.645690 t，均在 100–190 t；任何 q/SREF 变化必须重算并 fail-closed。

## 3. 30 条 M0-R 条件

| ID | 类别 | 严重度 | 要求 |
|---|---|---|---|
| R01 | package | CRITICAL | M0-R 必须是全新包、新 family SHA、新 task ID；不得复用 ada424cc/40fdd436/旧 18-task 字节；旧 T0-4/A3 M0 字节不改，只作历史。 |
| R02 | geometry | CRITICAL | 任务族几何必须重绑 post-fix 546x480 链：openvsp_geometry d20ee7ad；baseline vspgeom 16da482a/225,414B/546x480；F1R2 12D audit 7a90b977；40fdd436 不得出现在 active family。 |
| R03 | executor | CRITICAL | task-capable executor：逐任务注入 Mach/alt/CL/Vinf/Rho/ReCref/q；6 个 per-task .vspaero deck；任务缺失 fail-closed；零物理 dry-run。 |
| R04 | q_source | CRITICAL | q 单源 ATM-F1R2；q 由实际注入 Vinf/Rho 复算 rel≤1e-12；6 任务 q 精确等于 20483.940233430174/24297.194081414087/16265.063806566453；禁止 ISO 混用。 |
| R05 | lift_reference | CRITICAL | L_ref=q*SREF_REF*CL_target；SREF_REF 运行时由 post-fix baseline 几何重算并 SHA 绑定，不得硬编码 358.25；m_task=L_ref/g0；质量带 100–190 t；LREF-1..8 fail-closed。 |
| R06 | tasks | CRITICAL | 只保留 L-30-A01 的 6 任务；固定 18,288 m；3 train/1 val/2 test；meta_test 盲；删除全部高度缩放副本。 |
| R07 | design_space | CRITICAL | 设计空间同时绑 raw YAML 8b29d1e3…/10,846B 与 C01–C04 cross constraints；M1 sampler/executor 强制执行 check_cross_constraints。 |
| R08 | alpha_lift | CRITICAL | 7 点 alpha 固定；max_refine_sweeps 统一（0 或明确 refine 列表）；不得 frozen=0/tasks=2 矛盾；报告独立升力残差与插值不确定性。 |
| R09 | mask | HIGH | 12D_ALL_ACTIVE；10D_ACTIVE_PLUS_2_INACTIVE=DEFERRED_TO_M1；更正 “no zero-effect evidence” 文本。 |
| R10 | effect_threshold | HIGH | MIN_EFFECT_REL>0 并预注册；建议 max(2×U_within,1e-3)；不得用 0.0。 |
| R11 | cross_task | CRITICAL | M1-A CTX-A/B 预注册：4 任务×3 设计；效应量分离 ≥max(2U_within,1e-3)；3 设计下 Spearman 仅描述性，不得做 p 值/显著性；TOO_SIMILAR 规则保留。 |
| R12 | budget | CRITICAL | M1-A 15 starts/105 internal，caps 18/126，retry 0；4 任务×3 设计+1 exact repeat+2 preflight；repeat 必须预注册 task/design/deck SHA。 |
| R13 | budget | CRITICAL | M1-B 66/462 caps 70/490；4 任务×16 designs=64 labels+2 preflight；retry 0。 |
| R14 | budget | CRITICAL | M3-A 34/238 caps 38/266；2 test 任务×16=32 labels+2 preflight；retry 0；M3 前不得运行 meta_test。 |
| R15 | budget | CRITICAL | 总预算 planned 115/805，hard 126/882，labels 96，preflight 6，retry 0；M3-B 不授权。 |
| R16 | admission | CRITICAL | admission=DEFERRED_TO_M1A_WITH_PRE_REGISTERED_CHECKS；M0/M0-R 不签 admission；首条真实 M1 标签按 validity/status/identity 判定，不按目标值。 |
| R17 | authorization | CRITICAL | M0-R 零物理；不创建 run dir/ledger/token/authorization；不复用 #9 R10 或 #10 F1R2/F2R2 approval/token。 |
| R18 | a5 | CRITICAL | A5 独立复核/门禁 G-M0R-ADMISSION-01；M0-R 包到后先 gate，不得先签 admission；A5 physical=0。 |
| R19 | evidence_text | HIGH | T0-4/M0-R 必须删除 “A5 P1-05 verified envelope 1.8/2.02/2.2”；P1-05 实际 1.8/2.0/2.2、18,288m、旧 58f63/199,997B、TREND_ONLY、2.02 NOT_COMPARABLE。 |
| R20 | review_correction | INFO | A5 记录 A1 F-M0-02 事实更正：40fdd436=543x472/227,247B；199,997B/483x418 是 P1-05 58f63bfc；阻断结论不变。 |
| R21 | task_metadata | CRITICAL | 每 task 记录 Mach/alt/CL/q/Vinf/Rho/ReCref/L_ref/mass/SREF_REF/task fingerprint/geometry SHA/evaluator/solver；任务 ID 不得复用旧 ada424cc 任务 ID。 |
| R22 | deck | CRITICAL | 每 task 独立 .vspaero deck；同一设计跨 task 复用同一 vspgeom 字节（build once）；per-task 记录 vspgeom/polar/deck SHA。 |
| R23 | consistency | CRITICAL | q/L_ref/Sref 三重一致：q 由 deck 实际注入；L_ref=q*SREF_REF*CL；Sref(x) 逐设计；D_i=q*Sref(x)*CDi；A5 独立复算。 |
| R24 | geometry_identity | HIGH | baseline SHA 与 per-design SHA 分开；M1 每设计记录 vspgeom SHA；不得用一个 40fd/16da 代表所有设计。 |
| R25 | expected_polar | HIGH | M2.02 可作 F1R2 连续性锚点；2.2/1.8 不继承 F1R2 expected polar；M1-A 重建 admission baseline。 |
| R26 | fail_closed | CRITICAL | 任何 task/atmosphere/SREF/geometry/mass/q 校验失败必须 fail-closed；禁止回退到 358.25、旧几何、ISO、旧 task 或旧 token。 |
| R27 | evidence | CRITICAL | M0-R 包/证据必须含 SUMS、validation、zero-physical dry-run、6 deck、A5 复算、无 solver 证据；commit 不 push。 |
| R28 | gate_process | CRITICAL | M0-R gate 新 ID G-M0R-ADMISSION-01；旧 G-T0-ADMISSION-01 保持 M0_BLOCKED 历史；不得复用旧 gate commit/SHA。 |
| R29 | m1_process | CRITICAL | M1-A 通过 A5 后单独 authorization/approval/GO；M1-A 结果只给 admission verdict，不自动授权 M1-B/M3。 |
| R30 | claims | CRITICAL | 不得宣称 winner/显著性/优化增益/跨族可比；fuel_burn_kg=null；外部物理 NOT_VALIDATED；单 seed 描述性；M3 任务级 n=2。 |

## 4. M1-A 预算评估

- **接受 Lead 15/105 caps 18/126**；A1 草案 12/84 caps 16/112 不足以算 cross-design CTX。
- 15 = 4 任务×3 设计（12）+1 exact repeat+2 preflight；internal=105；caps 18/126 余 3/21；retry 0；spare 不得用于额外设计/任务。
- repeat 必须预注册 exact task/design/deck SHA；否则不是 repeat。
- CTX-A/B：4 任务×3 设计；以效应量为主；n=3 的 Spearman 仅描述性，不做 p 值/显著性；4/4 任务可分或 PHYSICAL_TASK_FAMILY_BLOCKED。

## 5. 科学限制（必须写入 prereg）

- 3 train/1 val/2 test：单 val 任务不足以稳健早停/模型选择；M2 应固定 epoch 或 leave-one-train-out，不得据单 val 任务宣称泛化。
- 2 test 任务均为 Mach 1.8：仅低马赫外推；无跨 Mach 测试；不得跨族/跨 Mach 泛化。
- task-level n=2：只可描述性/配对区间，NO_EVIDENCE 可能；不得显著性/winner。
- 6 任务为 Mach×CL，无高度因子；质量为目标巡航质量，无燃油模型，fuel=null。

## 6. 预算总表

| 批次 | starts | internal | caps | labels | retry |
|---|---:|---:|---:|---:|---:|
| M1-A | 15 | 105 | 18/126 | — | 0 |
| M1-B | 66 | 462 | 70/490 | 64 | 0 |
| M3-A | 34 | 238 | 38/266 | 32 | 0 |
| 合计 | 115 | 805 | hard 126/882 | 96 | 0 |

- preflight 6；M3-B 不授权；每批独立 authorization/approval/A5/Lead GO；不复用 #9 R10 或 #10 F1R2/F2R2 token。

## 7. 边界

不是 authorization/approval/GO；M0-R 零物理；不签 admission；M1-A 之前不启动 solver；fuel=null；外部物理 NOT_VALIDATED；不得 winner/显著性/跨族。
