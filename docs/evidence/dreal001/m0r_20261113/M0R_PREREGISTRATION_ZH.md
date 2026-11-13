# D-REAL-001 M0-R 物理任务族冻结包（中文预注册）

- 包 ID：DREAL001-M0R-20261113-01
- 状态：M0R_PACKAGE_FROZEN_PENDING_A5_GATE
- 新 family SHA256：98b84f5ecf6e18a7be90e21da41b243dccb664f09034366ea3b58d777f1c0311
- A1 code commit：0c514151d989de716dbb855973b900a34615b5aa
- A1 freeze commit：c5698a218fad974e8e96b604573c5cc79b3abb32
- A5 gate：G-M0R-ADMISSION-01（PENDING；A3 不签 gate、不宣布 admission）
- 零物理：physical_call_count=0，solver_started=false，run_dir/ledger/token/authorization 均未创建。

## 1. 范围与边界

M0-R 是零物理的物理任务族重冻包。它只定义 6 个任务、3/1/2 split、预算模板、CTX-A..F
预注册、泄漏审计、统计端点与 A5 证据映射；不是 run，不是结果，不是验收通过，不是 M1
授权。fuel_burn_kg=null；外部物理 NOT_VALIDATED；单 seed=42 仅描述性；无 winner / 排名 /
显著性 / p 值 / 置信区间 / 跨族或跨 Mach 平均 / 优化增益声明。

## 2. 六个任务（L-30-A01，ATM-F1R2，固定 18,288 m）

| A3 task_id | A1 temp id | Mach | CL | split | q (Pa) | Vinf (m/s) | L_ref (N) | mass (t) |
|---|---|---|---|---|---|---|---|---|
| M0R-M202-CL017 | T18K_M202_CL017 | 2.02 | 0.17 | meta_train | 20483.9402334302 | 596.0373972279 | 1247523.170066 | 127.211960 |
| M0R-M202-CL019 | T18K_M202_CL019 | 2.02 | 0.19 | meta_train | 20483.9402334302 | 596.0373972279 | 1394290.601839 | 142.178073 |
| M0R-M220-CL017 | T18K_M220_CL017 | 2.20 | 0.17 | meta_train | 24297.1940814141 | 649.1496405452 | 1479759.862543 | 150.893512 |
| M0R-M220-CL019 | T18K_M220_CL019 | 2.20 | 0.19 | meta_val | 24297.1940814141 | 649.1496405452 | 1653849.258137 | 168.645690 |
| M0R-M180-CL017 | T18K_M180_CL017 | 1.80 | 0.17 | meta_test_blind | 16265.0638065665 | 531.1224331734 | 990583.048479 | 101.011359 |
| M0R-M180-CL019 | T18K_M180_CL019 | 1.80 | 0.19 | meta_test_blind | 16265.0638065665 | 531.1224331734 | 1107122.230653 | 112.895049 |

全部任务：12D_ALL_ACTIVE；alpha 7 点 (-2,0,2,4,6,8,10)；max_refine_sweeps=0；
V01/V02 不声称零效应，10D 掩码 DEFERRED 到 M1。

## 3. 几何与设计空间

- post-fix baseline vspgeom SHA256 16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84，
  225,414 B，546x480；openvsp_geometry d20ee7adc38286c7da3ef3ea5aa5be8204596d491d6601b9a635b0ae5213dc56。
- 旧 40fdd436 / 543x472 与旧 family ada424cc 已 retired，不在 active family。
- raw 12D design-space YAML 8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e，
  10,846 B；C01-C04 交叉约束必须由 M1 sampler/executor 在 build 前强制。A1 interface 不代替
  cross-constraint 强制（A1 已书面明确）。
- SREF 唯一来源是 runtime post-fix baseline 重算；358.25000000000006 仅是 anchor 校验常量，
  不得直接当作 SREF_REF 输入，也不得硬编码。运行时需记录重算值、vspgeom 16da482a 与绑定
  SHA。预注册容差 1e-9，实测 Newell 重算 358.2500000223502 vs anchor 358.25000000000006，
  rel=6.2387e-11。A1 的实现中存在该 anchor 常量（task_evaluator.py:56）与 :300-303 校验；
  :1169 仍从 post-fix baseline build 取 runtime sref，M0-R 以 runtime 值为唯一 SREF 来源。
- deck determinism：solver_input_sha256 含 path-dependent .vkey（绝对路径+随机 component
  object-ID），不是跨进程 expected；确定性绑定用 deck_sha256 + vspgeom_sha256。vkey 按 run
  记录并可披露非确定性；A2 runner 不得以 solver_input_sha256 做 gate。
- deck 冻结边界：full family deck 空间 = 3 个设计（B0-01/B1-01/C5）×6 个任务 = 18 个条目；
  其中 6 个 B0-01 baseline deck 已在本包冻结，12 个 B1-01/C5 reference 条目未冻结。M1-A 需要
  12 个 deck 槽位（4 个 M1 任务 ×3 个设计）：4 个 B0-01 槽位已冻结，8 个 B1-01/C5 槽位必须在
  M1-A 授权前冻结或确定性重生成；剩余 4 个 B1-01/C5 meta_test 槽位必须在 M3-A 前冻结。
  M0R_DECK_FREEZE.json 的 m1a_required_deck_set 逐条列出 12 个槽位的 task_id、design_id、
  deck_sha256、vspgeom_sha256 与 frozen_status。未冻结的 reference deck 不得直接用于物理执行。

## 3.1 A1/A5 三项权威口径（原文，必须照录）

- CL-1-SREF：SREF_REF 以 post-fix baseline 几何运行时重算值为唯一来源（本次 358.25000000000006），冻结常量仅作 1e-12 校验锚；不得把 358.25 作为计算输入硬编码。
- CL-2-SOLVER-INPUT-SHA：solver_input_sha256 含 path-dependent/random 的 .vkey，跨进程不可复现；确定性绑定只用 deck_sha256 + vspgeom_sha256（加 solver_sha256/task_fingerprint），vkey 与 input_sha 按 run 记录，不作跨进程 expected。
- CL-3-F1R2-CONTINUITY：M2.02 仅物理条件与 F1R2 逐位连续（q=20483.940233430174，Mach/Vinf/Rho/ReCref/alpha 网格相同），deck 字节不相等（A1 943B/LF vs F1R2 985B/CRLF，43 行规范化后相同）；不继承 F1R2 expected polar，M1-A 重建 admission baseline。

## 4. Split 与泄漏

3 meta_train（M2.02 CL0.17 / M2.02 CL0.19 / M2.2 CL0.17）、1 meta_val（M2.2 CL0.19）、
2 meta_test_blind（M1.8 CL0.17 / M1.8 CL0.19）。按 task identity 切分，不按样本；meta_test
在 M1/M2 期间不读标签、不参与归一化/标签变换/early stopping；无高度副本；同设计跨 task
复用同一 vspgeom 字节属于有意迁移，不是 task-identity 泄漏。M2.02 与 F1R2 的连续性只是
q/物理条件逐位连续，不是 deck 字节连续，也不继承 F1R2 expected polar；M1-A 会重建 admission
 baseline。

## 5. 预算（未来授权模板，不是已计费）

- M1-A：15 starts / 105 internal，caps 18/126，retry 0；4 任务 x 3 设计=12 + 1 exact repeat + 2 preflight。
- M1-B：66/462，caps 70/490；4x16=64 labels + 2 preflight。
- M3-A：34/238，caps 38/266；2x16=32 labels + 2 preflight。
- 总：115/805，hard 126/882，labels 96，preflight 6，retry 0；M3-B NOT_AUTHORIZED。
- 五口径：M0-R 全零；M1 起 charged 与 actual 分列，禁止混写。

## 6. CTX 预注册（不测值）

CTX-A 纯缩放（TOO_SIMILAR）；CTX-B 归一化响应差（效应量 >= max(2*U_within,1e-3) 或
Spearman<0.99）；CTX-C 可行域；CTX-D 升力匹配/插值；CTX-E 每任务真实物理证据（DEFERRED
到 M1-A）；CTX-F 同几何字节。M1-A 只有 3 个参考设计，Spearman 仅描述性，无 p 值。

## 7. 统计端点

主指标 D_i_N=q*Sref(x)*CDi(lift_matched)，按 task/design 分报；禁止 0.5*(f1+f2)、硬编码
Sref、跨 family 平均。EP-01..EP-06 见 M0R_STAT_ENDPOINTS.json。M0-R 零物理，E1-E6
不计算、不继承 R10，不构成绩效结论。

## 8. A5 证据

本包映射 A5 R01-R30、gate draft 60 checks、42 conditions（R01-R30 + G01-G12）。A5 独立
复算并签 G-M0R-ADMISSION-01；A3 不声称 PASS、READY_FOR_M1A_ADMISSION 或 admission。
A1 interface 冻结绑定：code 0c51415、freeze c5698a2、7 文件 SUMS 3ca22ec9。

## 9. 未授权事项

不创建 run dir / ledger / token / authorization；不启动 VSPAERO；不复用旧 #9/#10
authorization；M1-A 通过后仍需 A5 预审 + Lead 单独 authorization/GO。
