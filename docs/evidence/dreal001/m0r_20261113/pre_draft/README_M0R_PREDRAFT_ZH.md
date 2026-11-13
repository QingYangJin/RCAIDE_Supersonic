# M0-R Pre-Draft (A3 task-60, zero physical, not frozen)

状态：**PRE_DRAFT_NOT_FROZEN / NOT_A_GATE / NOT_A_RUN / NOT_AN_ADMISSION**。

本目录是 A3 依据 L-30 / L-30-A01、A5 M0-R requirements 与 gate draft、A1 U1/U2
零物理接口 dry-run、A1 raw 12D design-space YAML 与 post-fix baseline vspgeom
生成的 M0-R 预草案。它**不是**正式 M0-R 包，**不是**冻结，**不是** A5 gate，
**不是** M1 授权，**不是**任何物理结论。

## 1. 边界

- 零物理：physical_call_count=0，physical_solver_starts=0，solver_started=false，spawn_events=[]。
- 不创建 run dir / accounting ledger / token / authorization。
- 不生成最终 family SHA；所有 task fingerprint 字段为 null 或明确标为 A1 dry-run draft。
- 不改 T0-4、A1、旧 M0、F1/F2/R1-R10 的字节；旧 SHA 只作 superseded 披露。
- 无 winner、无显著性、无优化增益、无跨族/跨 Mach 比较；fuel_burn_kg=null；外部物理 NOT_VALIDATED。
- 单 seed、任务级 n=2 仅描述性。

## 2. 六个任务（L-30-A01 ATM-F1R2）

| task_id | Mach | CL | split | q (Pa) | Vinf (m/s) | L_ref (N) | mass (t) |
|---|---|---|---|---|---|---|---|
| T18K_M202_CL017 | 2.02 | 0.17 | meta_train | 20483.940233430174 | 596.0373972278921 | 1247523.170066 | 127.211960 |
| T18K_M202_CL019 | 2.02 | 0.19 | meta_train | 20483.940233430174 | 596.0373972278921 | 1394290.601839 | 142.178073 |
| T18K_M220_CL017 | 2.2 | 0.17 | meta_train | 24297.194081414087 | 649.1496405452291 | 1479759.862543 | 150.893512 |
| T18K_M220_CL019 | 2.2 | 0.19 | meta_val | 24297.194081414087 | 649.1496405452291 | 1653849.258137 | 168.645690 |
| T18K_M180_CL017 | 1.8 | 0.17 | meta_test_blind | 16265.063806566453 | 531.1224331733692 | 990583.048479 | 101.011359 |
| T18K_M180_CL019 | 1.8 | 0.19 | meta_test_blind | 16265.063806566453 | 531.1224331733692 | 1107122.230653 | 112.895049 |

全部 18,288 m；12D_ALL_ACTIVE；7 点 alpha；max_refine_sweeps=0；无高度副本。

## 3. SREF_REF 与 L_ref

SREF_REF 必须由 post-fix baseline vspgeom 在运行时独立重算并 SHA 绑定，不得写死数值。
本预草案从 A1 baseline vspgeom（SHA 16da482a…，225,414 B，546x480）用正确 token-stream
Newell 解析重算主翼面积，与 A1 运行时 anchor 的相对差在 1e-9 预注册容差内（约 6.2e-11）。
A1 task_evaluator 目前仍带 frozen SREF_REF 常量并以 1e-12 校验，这是 A1 接口偏差，
已在本包与报 Lead/A5 中披露；task-57 冻结前需 A1 修正或 A5 书面接受。

L_ref = q(M,18288) * SREF_REF * CL_target；mass = L_ref/g0，6 个任务均在 100-190 t。
q 由 deck 实际注入的 Vinf/Rho 复算，rel<=1e-12；q 单源 ATM-F1R2，禁止 ISO 混用。

## 4. Deck 与几何

- 6 个 per-task baseline deck（B0-01）与 3 个参考设计（B0-01/B1-01/C5）共 18 个
  A1 dry-run deck 引用；deck SHA 已登记，但状态为 **A1_DRY_RUN_DECK_NOT_FROZEN**。
- 同一设计跨 task 复用同一 vspgeom 字节；baseline 与 per-design SHA 分开记录。
- 旧 40fdd436/543x472 链不得出现在 active family；只作历史/superseded。

## 5. Split 与泄漏

3 train / 1 val / 2 blind test（按 task identity，不按样本）。meta_test 盲、不参与
M1/M2、不读标签；归一化/标签变换只在 meta_train 拟合；无 query 标签/heldout 最优/未来评价
泄漏；无高度副本。

## 6. 预算（未来授权模板，不是已计费）

- M1-A：15 starts / 105 internal，caps 18/126，retry 0；4 任务×3 设计=12 + 1 repeat + 2 preflight。
- M1-B：66/462，caps 70/490；4×16=64 labels + 2 preflight。
- M3-A：34/238，caps 38/266；2×16=32 labels + 2 preflight。
- 总：115/805，hard 126/882，labels 96，preflight 6，retry 0；M3-B NOT_AUTHORIZED。
- 五口径模板：physical=0、charged=0、actual=0、design_evaluations=0、cached_reads=0；
  charged 与 actual 分列，不混写。

## 7. CTX 预注册

CTX-A 纯缩放（TOO_SIMILAR）；CTX-B 归一化响应差（效应量 >= max(2*U_within,1e-3) 或
Spearman<0.99）；CTX-C 可行域；CTX-D 升力匹配/插值；CTX-E 每任务真实物理证据（DEFERRED
到 M1-A）；CTX-F 同几何字节。U_within/U_rep 等 M0-R 未测量，不得复用旧 F1 数值；
3 设计 Spearman 只作描述性、无 p 值/显著性。

## 8. A5 映射

M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json 覆盖 A5 R01-R30、gate draft 60 项检查与 42 条
conditions（R01-R30 + G01-G12）。状态分为 EVIDENCED_IN_PREDRAFT、PRE_REGISTERED_*、
PENDING_A1_INTERFACE_FREEZE、PENDING_FINAL_PACKAGE_OR_A5_GATE。A5 gate 仍由 A5 独立签发；
本包不声称 PASS / READY_FOR_M1A_ADMISSION / admission。

## 9. 进入 task-57 前必须补齐

1. A1 U1/U2 task-capable executor commit + SHA256SUMS 冻结。
2. A1 6 任务零物理 dry-run 冻结（deck SHA、spawn=[]、physical=0）。
3. Lead 释放 task-57，并确认预算/任务/几何/接口不再变。
4. A3 生成新 family SHA（非 ada424cc/40fdd436），冻结 6 TaskSpec 与 6 baseline deck。
5. A3 重跑 fail-closed validation，写正式 SHA256SUMS。
6. A5 独立复算并签 G-M0R-ADMISSION-01；之后才谈 M1-A 授权。

## 10. 文件

- M0R_PREDRAFT_MANIFEST.json
- M0R_TASK_SPECS_PREDRAFT.json
- M0R_SREF_PROVENANCE_PREDRAFT.json
- M0R_DECK_SPECS_PREDRAFT.json
- M0R_SPLIT_LEAKAGE_AUDIT_PREDRAFT.json
- M0R_BUDGET_LEDGER_PREDRAFT.json
- M0R_CTX_PLAN_PREDRAFT.json
- M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json
- M0R_ZERO_PHYSICAL_EVIDENCE_PREDRAFT.json
- M0R_VALIDATION_PREDRAFT.json
- SHA256SUMS.txt
