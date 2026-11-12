# A5 R7 阶段 D 独立复核（零物理；R6 NaN 取证 + A2 诊断充分性 + 协议选项意见 + 门禁模板）

- review_id: `A5-P2AV2R7-STAGE-D-REVIEW-01`
- created_utc: 2026-11-11T14:02:00Z（A5 本地 21:5x +08）
- reviewer: a5-review（A5 独立复核与签署）；Lead 指令：m01715 + L-08
- physical_call_count: **0**；solver_started: **false**；未 push；未改 A1/A2/R1–R6 任何证据字节
- 本文件**不构成** R7 门禁、不构成签署建议、不构成执行授权；G-P2AV2R7-PRE 须在 A2 交付 R7 包后另行出具。

## 0. 结论摘要（verdict）

`R6_NAN_PHENOMENON_INDEPENDENTLY_CONFIRMED_ITER2_WAKE_COUPLING_DIVERGENCE_MECHANISM_NOT_PROVEN_A2_STAGE_D_GEOM_METRICS_NOT_ACCEPTED_AS_IS_OPTION_A_REJECTED_B_AND_C_CONDITIONALLY_ACCEPTABLE_B_PLUS_C_LITE_PREFERRED_WITH_CONDITIONS_GATE_TEMPLATE_PREPARED_NOT_ISSUED`

1. **R6 NaN 现象成立**：7 个 solver case 的 iteration-1 线性解全部有限（CLi=CDi=0，尾迹未耦合），iteration-2 起 40/48 token 非有限、L2/MaxRes 变为 NaN；VSPAERO 对 7/7 AoA 全部失败，polar 7 行全 NaN、valid 0 → objective=null → `LIFT_MATCH_FAILED`。同设置下 PRE-01/PRE-02（平坦网格）5 迭代收敛。A5 独立解析 R6 原始 `.history`/`.polar`/`.lod`/`.case.1.quad.1.dat` 确认。
2. **机理未证实**：A2 归因“design 15 薄面网格几何质量特异（非平面/自交/sliver）”方向合理且有部分独立佐证（z_extent 6.2e-2 vs PRE ~1e-14；两族同设计、字节可复现），但 **A2 的几何度量实现存在内部矛盾**（同一 design 的两族 `area_total` 分别为 366.963 与 336.964 m²，差 8.9%；A5 独立规范解析两族 Newell 面积**完全相等** = 369.271374 m²），因此“自交/退化驱动 NaN”尚不能作为协议决策依据。
3. **协议选项**：A（原样重跑）**拒绝**（可预测 S1 空耗 3 starts/21 internal）；B（零物理网格 QC 门）与 C（预注册 1–2 个诊断真实求解）**有条件可接受**；A2 推荐 B+C-lite 方向可用，但**前置条件**是度量实现修正并自检、零物理预检 16/17 号初始设计、阈值/诊断在 prereg 显式预注册、DE/PSO population 缺陷同批修复。
4. **门禁模板**已按 R6 schema 预建 52 条（占位），**未签发**；正式 G-P2AV2R7-PRE 待 R7 包落盘 + Lead 裁定 option 后出具。

## 1. 范围与方法

- 只读对象：R6 run dir 全证据、A2 阶段 D 交付（commit `6c098ec8`）、R4/R6 冻结几何、A1 冻结绑定字节、L-08 决策记录。
- 方法：A5 自写独立 parser（vspgeom v3；`.history`/`.polar`/`.lod`/`.case.*.dat` 原始行解析；Newell + fan 双面积口径；全量 SHA256 实算），不依赖 A2 解析代码；所有 SHA/bytes 由 A5 现场实算。
- 复核边界：A5 未运行任何求解器（physical=0），几何/求解机理结论只能基于既有字节与零物理统计；不替代 Lead 的协议决策。

## 2. 证据锚（A5 实算 SHA256 / bytes）

| 对象 | 绝对路径 | bytes | SHA256 |
|---|---|---:|---|
| R6 approval（只读） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/approval.json` | 67063 | `72b95e03130fbe958c52528f1b8f484eae4872140a7336709094b9108964f98f` |
| R6 main .history（唯一 main 案） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/arms/BO/BO-d51866f7d3c49303-f1/concorde_baseline.history` | 34615 | `a5f47b63afd82960c2a32474469a947f081d90ce6f9a5228c694e2642da52495` |
| R6 main .polar（7 行全 NaN） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/arms/BO/BO-d51866f7d3c49303-f1/concorde_baseline.polar` | 7933 | `58b8438df1225b07b3ef8dc327670575d99a6866b204f2c0840de074324d489a` |
| R6 main .lod（441 行/224 行含 nan） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/arms/BO/BO-d51866f7d3c49303-f1/concorde_baseline.lod` | 173005 | `3b137fec4625d6b2281f3605df99c2affa9fcedaee7eeb6b3fcdec227c772eb3` |
| R6 main .vspaero（957 B） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/arms/BO/BO-d51866f7d3c49303-f1/concorde_baseline.vspaero` | 957 | `cad6e016e6a8fd1023ad1f397b8e63e6bd99410c948ba6aec302ad2840b6e3f0` |
| R6 main .vspgeom（=462x401 冻结族） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/arms/BO/BO-d51866f7d3c49303-f1/concorde_baseline.vspgeom` | 191129 | `6b00d72d06ac59b210ea93c69840f1aaf0e4ac4d306113d9791faa3bf7c1c220` |
| R6 main .case.1.quad.1.dat（25 节点/16 单元） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/arms/BO/BO-d51866f7d3c49303-f1/concorde_baseline.case.1.quad.1.dat` | 2002 | `26d9af33f269bba6c51184c57d85589b68e3549abddfebb98e25696bd394e3e0` |
| PRE-01 .history（对照，5 迭代收敛） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/preflight/PRE-01/PRE-01/concorde_baseline.history` | 49388 | `d65b02fb0609802dec5a2a199d63770a1718bedd99cb4da5090c94c3f6704eed` |
| PRE-01 .polar（=期望 455082e2） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/preflight/PRE-01/PRE-01/concorde_baseline.polar` | 7933 | `455082e2ac8029216a811c89aaa20b34fd9d73faa319eed23da5348e3de4bc87` |
| PRE-01 .vspaero（对照设置） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/preflight/PRE-01/PRE-01/concorde_baseline.vspaero` | 985 | `3c70d11ae6af74e6fd1cf9b787c71571768bc398a07b1343df9a1340cf93b837` |
| f1 冻结 462x401 model.vspgeom | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/runtime/designs/d51866f7d3c49303/freeze/462x401/model.vspgeom` | 191129 | `6b00d72d06ac59b210ea93c69840f1aaf0e4ac4d306113d9791faa3bf7c1c220` |
| f2 冻结 546x472 model.vspgeom | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/runtime/designs/d51866f7d3c49303/freeze/546x472/model.vspgeom` | 228792 | `be8454bfd7db4c4637e73d9637a79391e45f4cbfd66408b956ad35d51f68a689` |
| R6 freeze_record（PAIR_READY） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R6-20261111-01/runtime/designs/d51866f7d3c49303/freeze_record.json` | 8772 | `61cb3fc20d1db793424dcf84ef3c781d66cf2439d7b07b19fbcf9b072844f9fe` |
| A2 诊断 md | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/docs/evidence/dreal001/r7_r6_nan_zero_physical_diagnosis_20261111.md` | 10077 | `86fdbe6de96ac0bfbff39acc890b5356be5a4f3b071bd38fc2d609bc11a041e8` |
| A2 诊断 data JSON（**含 NaN 字面量**） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/docs/evidence/dreal001/r7_nan_diagnosis_data_20261111T2142Z.json` | 35775 | `cc168063b8b1a65cffa12010bace5dd158a96c2ff4e6049682ad6cb23ac60dca` |
| A2 诊断 geom JSON | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/docs/evidence/dreal001/r7_nan_diagnosis_geom_20261111T2148Z.json` | 16446 | `44f2d1fba443791e67fe690910a597bf21e6bbce6081ad0afeebc553f24feb4f` |
| A2 选项 memo | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/docs/evidence/dreal001/r7_protocol_options_memo_20261111.md` | 12731 | `62d24bd1e00c3fc37fcb70db7e7607cd9333cfea13616ad5437ef0d098f0a819` |
| A2 observe 修复证据 md | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/docs/evidence/dreal001/r7_observe_fix_and_tests_20261111.md` | 5580 | `fa9f1e4a52fd11a687adb50960ce91cafd9a5adbb1e3d7f39d15a76f99ca2faf` |
| A2 pytest 原始输出 | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/docs/evidence/dreal001/r7_pytest_20261111.txt` | 781 | `95129ba303691cd76d998a9b02a5f5e557f193dc1c318671b382dbb412f73680` |
| A2 诊断 parser 脚本 | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/docs/evidence/dreal001/r7_nan_diag_parse.py` | 13807 | `2651bd9e5fa29810b379bfd6fca41b1e06d41d4f0c4cf9b05688a86d1090d924` |
| A2 诊断 geom 脚本 | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/docs/evidence/dreal001/r7_nan_diag_geom.py` | 9619 | `b0061c1583169c97cc825e6562506946297d00da5d937b69ff7ac76940941a9d` |
| A2 修复后 executor（workspace） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/dreal001/optimizers/p2a_v2_executor.py` | 70709 | `ac79d4fa6b0b08f00d1f57976669cca274307414ecf59cdf12142e7926274b4f` |
| A2 tests（workspace） | `D:/RCAIDE/dnext001/wt-real-a2-optimizers/research/concorde_metaopt/tests/test_dreal001_p2a_v2.py` | 50366 | `3153675e7be80637017bdcb466a5a6b8b6d7f14d2338522c23f15ec6c93f7876` |
| L-08 Lead 决策记录 | `D:/RCAIDE/dnext001/wt-real-lead/docs/reviews/dreal001_lead_decision_r7_continue_20261111.md` | 6231 | `27898d2e281efb6a38b59c1e9e9e37e1ba872b6dee2b18241d9dad44641b8ddf` |
| A1 evaluator_v12.py（冻结） | `D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/dreal001/geometry/evaluator_v12.py` | 58291 | `f74a4752495fd6c5330edcaf7edb4bcbe93f99c2a76bac06b5670d1f765ae20d` |
| A1 freeze_api.py（冻结） | `D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/dreal001/geometry/freeze_api.py` | 27288 | `31d781821516bb80fc158238e4ef485c361afea674ca3b962efbb89d5a737173` |
| A1 openvsp_model.py（冻结） | `D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/dreal001/geometry/openvsp_model.py` | 36902 | `c40b11df29e9a41889b81f5c608c9a12cd921cf62d01c5318a6ab8eb91f859f6` |
| A1 aircraft/design_space.py（冻结） | `D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/aircraft/design_space.py` | 33660 | `8f9b893c13195c80ff1ee88598134e3f44fef0495452249780d114c9e0593b89` |
| A1 design_space 配置（冻结） | `D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml` | 10846 | `8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e` |
| A1 R1 replay bundle manifest（995bb12f） | `D:/RCAIDE/dnext001/wt-real-a1-geometry-solver/research/concorde_metaopt/dreal001/geometry/replay_bundles/P2A_V2_PREFLIGHT_20261111_R1/bundle_manifest.json` | 3262 | `995bb12fff738d3ebb0bde08c0d5c5bfeb9532aebe536847ef307a2332013aa5` |

A2 阶段 D commit：`6c098ec825d9b69b23ffc3b668c2de65281ccc3a`（A2 分支，未 push；executor 修复后 70,709 B / `ac79d4fa6b0b08f00d1f57976669cca274307414ecf59cdf12142e7926274b4f`；tests 50,366 B / `3153675e7be80637017bdcb466a5a6b8b6d7f14d2338522c23f15ec6c93f7876`）。A5 复核两文件字节与 A2 报告一致。

A1 冻结绑定字节全部未变：evaluator `f74a4752…`、freeze_api `31d78182…`、openvsp_model `c40b11df…`、design_space.py `8f9b893c…`、config `8b29d1e3…`、bundle `995bb12f…`。

## 3. R6 NaN 独立复核（结论：现象成立、机理未证）

### 3.1 `.history` 逐迭代（A5 独立解析）

- main（design 15，462x401）：7 个 case（AoA -2,0,2,4,6,8,10；Mach 2.02）**每个恰 2 个迭代**。iteration-1：CLo ∈ [-0.001267, 0.000258]，CDo ∈ [0.0072, 0.0073]，L2 ∈ [1.0357, 1.7582]，MaxRes ∈ [1.318, 2.015]，**全部有限**；iteration-2：40/48 token 非有限（CLo/CDi/CLtot 全 NaN、L2=NaN、MaxRes ∈ [-14.57, -15.05]）→ 求解器对 7/7 AoA 终止。
- PRE-01（对照，543x472 平坦网格）：7 个 case 全有限，6 个 case 各 5 迭代（L2：1.0948→0.5134→-0.4221→-1.8543→-2.4858），1 个 case 1 迭代（L2=-11.976）；polar 首行 CLtot=-0.066551349073。
- 现象语义：**只在首个 wake-coupled 迭代**（iteration-2）出现全体 NaN，而非逐步发散；这与“尾迹/矩阵组装在该几何上产生非有限项”一致，但不能单凭输出判定根因。

### 3.2 polar / lod / `.case.1.quad.1.dat`

- main polar 7,933 B / `58b8438df1225b07b3ef8dc327670575d99a6866b204f2c0840de074324d489a`：7 行，CLtot/CDi/CDtot 均为 `nan`/`-nan(ind)`，有效点 0。
- main `.lod` 173,005 B，441 行中 224 行含 `nan`；PRE-01 `.lod` 173,005 B（对照无 NaN 失败）。
- main `.case.1.quad.1.dat` 2,002 B：头 `2 0.000000 596.037397 891.599260` / `25 16`；25 个节点全 y=0，x∈[-175.300001, 210.360001]，z∈[-175.300001, 175.361956]；节点 1/4 速度有限 `(595.674307, 0, -20.801405)`，节点 2/3/5/7/… 速度为 `nan`/`-nan(ind)`。PRE-01 对应文件 268 节点/208 单元、全有限 → 失败已发生在**求解器内部速度/影响系数数组**，不是后处理阶段。

### 3.3 `.vspaero` 设置 diff（main vs PRE-01）

- 逐行 diff 仅 7 行数值格式化差异：Sref 362.267959370711 vs 358.25000000000006（差 1.1%）、Cref 18.489893 vs 18.489892999999999、Bref 25.604638 vs 25.604638000000001、X_cg 16.8219782595142 vs …246、ReCref 89397005.8767656 vs …594、Vinf 596.037397227892 vs …214、Rho 0.115317834008994 vs …361。
- 其余设置逐行相同：Mach 2.02、AoA -2..10、Beta 0、StallModel 0、Symmetry 0、**ImplicitWake 0**、ImplicitWakeStartIteration 0、**WakeRelax 1**、**NumWakeNodes 8**、**WakeIters 5**、FarDist -1、Freeze* 10000、GMRES 因子 1 等；`.adb.cases`（1,673 B）/`.quad.cases`（18 B）/`.csf`（20 B）两案逐字节相同。
- 结论：**可排除“VSPAERO 数值设置不同/Sref 诱因”**（Sref 差 1.1% 不足以解释全体 NaN）；换设置参数不是可辩护的默认修正。

### 3.4 冻结几何（A5 独立规范解析 vspgeom v3）

| 几何 | nodes×faces | 非 quad 面 | Newell 面积 | fan 面积 | min fan tri |
|---|---:|---:|---:|---:|---:|
| f1 462x401（main spawn） | 462×401 | 11 | 369.271374 | 369.272949 | 1.343e-6 |
| f2 546x472（另一冻结族） | 546×472 | 32 | 369.271374 | 369.272949 | 4.616e-16 |
| PRE-01 543x472 | 543×472 | 25 | 367.082666 | 367.082666 | 8.758e-16 |
| PRE-02 483x418 | 483×418 | 16 | 379.082666 | 379.082666 | 8.325e-4 |

- f1/f2 同一 bbox（x 0–35.0600002、y ±11.77935411、z -2.89e-15–0.06195494822）、无零长度边/重复节点/NaN 文本、**Newell 与 fan 面积逐位相同** → 两族是同一 design15 几何的粗/细 tessellation，无 family 级几何差异。
- 最小 fan 三角面积在 PRE 中同样出现 ~1e-16（n-gon 共线节点 fan 三角化伪影），**不能**用 fan 最小面积区分网格质量（A5 早前内部“f1 sliver 显著”判断已自我纠正，不采用）。
- z_extent：main 两族 0.06195494822 vs PRE ~9.3e-15 / 9.5e-15；max nonplanarity：0.00989572 vs ~2e-16/1.6e-16（与 A2 指标方向一致，A5 可采信该量级）。

### 3.5 结论

- **现象描述成立**：surface-only 一阶解正常 → 首个 wake-coupled 迭代全 NaN → 7/7 AoA 失败 → polar 全 NaN → `LIFT_MATCH_FAILED`。
- **机理三种候选未区分**：H1 网格面元/切割拓扑奇异（TE 带薄面/自交）；H2 该几何与冻结 VSPAERO numerics 不相容（同设置不等于对任意几何稳定）；H3 冻结 family 选择/尾迹初始化问题。R6 产物不足以排除 H2，A2 诊断亦未提供判别性实验。
- 因此 R7 不得以“根因已确认”为前提写协议；只能以“风险已识别 + 门控/诊断控制”为前提。

## 4. A2 阶段 D 诊断充分性评估

### 4.1 可采信部分

| 项 | A2 报告 | A5 独立复核 | 判定 |
|---|---|---|---|
| settings diff | 仅 Sref 等 7 行数值差 | 与 A5 逐行 diff 一致 | 采信 |
| history/polar 解析 | 7 case iter1 有限/iter2 全 nan | 与 A5 独立解析一致 | 采信 |
| z_extent/非平面量级 | 0.06195 / 0.00990 | A5 独立解析一致 | 采信（量级） |
| 两族缺陷指标相同 | 120/120/75/28 两族相同 | 两族确为同一几何、面积相等；具体计数待规范实现复算 | 方向采信 |
| spawn 几何可复现 | 462x401 SHA 6b00d72d 跨运行 3/3 | R4 smoke 与 R6 spawn 一致（A5 实算 6b00d72d） | 采信 |
| observe 修复 | 7 处 canonical_x12 误用已改 + 4 测试 | 文件 SHA 与 A2 报告一致；A5 未重跑 pytest（只读） | 采信（代码事实） |

### 4.2 不能采信/必须修正（阻断级，用于协议决策前）

- **D-G1 几何面积度量内部矛盾**：A2 geom JSON 报 `main_462x401.area_total=366.9630105291308`、`main_546x472.area_total=336.9641621779387`（同一 design15 几何的两种 tessellation），差 30.0 m²（8.9%）；`pre01_543x472=337.2238`、`pre02_483x418=375.5917`。A5 独立规范解析：f1=f2=**369.271374**、PRE-01=367.082666、PRE-02=379.082666。即 A2 面积指标对**同一几何的两族**给出 9% 差异，说明其面元遍历/方向/三角形化实现有误（或对 11/32 个 n-gon 面处理不一致）。**A2 “两族缺陷指标完全相同”的结论因此与自己的面积数据自相矛盾**，须修正后重出。
- **D-G2 数据文件非严格 JSON**：`r7_nan_diagnosis_data_20261111T2142Z.json` 含 Python `NaN` 字面量，`JSON.parse` 失败（A5 实测 `Unexpected token 'N'`）。门禁/统计脚本无法稳定解析，且 NaN 语义不明；须改为 `null` + `raw` 双字段或 `allow_nan=False` 规范化。
- **D-G3 自交/sliver 统计未自检**：A2 报 main 两族 `self_int_pairs=75`、`self_int_faces=82`、`slivers=28`，但未给出与 A1 `mesh_identity.parse_vspgeom`/`canonical_mesh_sha256` 的交叉核对、未报告算法/容差、未在同一实现下复算 PRE（A2 报 PRE sliver=6/7，说明 sliver 指标在“正常”网格上也非零，判别阈值需说明）。在 D-G1 未修正前，这些计数只能作“风险提示”，不能作门控阈值依据。
- **D-G4 结论强度与证据不匹配**：A2 诊断 md 结论 1 称“NaN 是设计 15 的薄面网格几何质量问题特异，不是 VSPAERO 数值设置”，前半句方向有支持，后半句可排除设置差异但不能排除 H2（几何-numerics 不相容）；诊断未提供判别性实验，故不得写成“根因已确认”。

### 4.3 协议决策前必须补齐（零物理）

1. 用**同一规范解析器**重算 design 15 两族 + PRE-01/02 的全部几何度量并自检：两族 `area_total`/`Sref` 必须一致（A5 实测 369.271374/362.267959=1.0193 两族相同）；与 A1 mesh_identity 的 canonical 解析交叉核对（A1 字节只读）。
2. 输出严格 JSON（无 NaN/Infinity 字面量），每个度量含 value/unit/method/tolerance 与样本清单。
3. 明确自交/sliver 算法定义与容差，报告 PRE 对照值，并给出“是否可区分 clean/dirty”的对照说明（阈值在 prereg 写死前必须有对照数据）。
4. 对 16/17 号初始设计做**零物理**构建+冻结+同度量 QC（不比 15 贵），在打包前回答“初始设计集是否有可用样本”；若 16/17 QC-clean 则直接支撑 C2 诊断与 B 门；若全废则不应打包 main 计划。
5. 复核 observe 修复语义：7 处 `design_hash(canonical_x12(X))`→`design_hash(X)` 只去掉字符串误用；确认 `canonical_x12` 其余用途未被误删，并给出零物理哈希重放证据。

## 5. R7 协议选项评估（A5 独立意见）

| 选项 | 内容 | A5 判定 | 理由 |
|---|---|---|---|
| A | 原样重跑（仅带 observe 修复） | **拒绝** | spawn 几何字节可复现（6b00d72d），design 15 必再 NaN → 白耗 3/21 并再次触发 S1；无信息量 |
| B | 零物理网格 QC 门（QC_FAIL 跳过 evaluate、不写 ledger start） | **有条件可接受** | 记账精确（A1 唯一 ledger 写入者）；但须先修 D-G1/G3、阈值 prereg 写死、非随机缺失披露、QC 不得成为“挑数据”的可调门 |
| C | 预注册 1–2 个诊断真实求解（C1 复现 NaN、C2 QC-clean 设计走完整链路） | **有条件可接受** | 预算内（+2/14 → 累计 438/3078 ≤451/3157）；C2 能验证 observe 修复后链路可产出目标值，价值高；C1 信息量低但可留受控复现证据；须 prereg 声明诊断不计入 E1–E6 |
| B+C-lite | QC 门 + 1 个诊断 start（A2 推荐） | **方向可接受，附条件** | 见 §5.1；前置 = 度量修正 + 零物理预检 16/17 + prereg 显式 + DE/PSO 修复 |
| D（不可接受） | 自适应选族/逐案跳过失败族、删 design 15、改 A1 字节、复用 R6 approval、放宽 NaN 判定、提高 caps、无预注册试探求解、以 preflight 代替 main 验证 | **禁止** | 破坏预注册与可比性 |

### 5.1 A2 “B+C-lite” 的 A5 附加条件（缺一不可）

1. **顺序**：先零物理 QC 预检 3 个初始设计（15/16/17）→ 有 QC-clean 样本才打包 → 否则只做 preflight 后干净停止（不申请 R8）。
2. **度量修正**：D-G1/G2/G3 全部闭环（同一解析器、严格 JSON、PRE 对照、A1 canonical 交叉核对）后，QC 阈值才允许进入 prereg。
3. **阈值预注册**：QC 指标/阈值/判定/跳过计数/披露方式写入 prereg §19 与 plan `r7_addendum.mesh_qc_gate`，批准后不得改；A5 门禁核对字节一致。
4. **诊断预注册**：C2 固定为“对 prereg 指明的 QC-clean 初始设计，走完整 freeze→evaluate→observe 链路，1 start/7 internal”；C1 仅在 Lead 书面同意时作为第 2 诊断；诊断不计入 384 main、不进入 E1–E6、不改变 caps。
5. **停止规则不放宽**：main 内任何 NaN/Inf/non-finite 或 non-SOLVED_VALID 仍 S1 停批；QC skip 不是“求解失败”而是“预注册的几何不合格”，两者在 batch_summary/回执中分开计数。
6. **DE/PSO population 缺陷**同批修复 + 零物理单测（R6 潜伏，R7 会运行 DE/PSO）。
7. **披露**：R7 数据存在几何质量门控导致的非随机缺失；QC 是 A2 执行层风险缓解，不是 A1 根治；R1–R6 排除、fuel=null、NOT_VALIDATED、无 winner/显著性、跨族不可 pool 不变。

## 6. G-P2AV2R7-PRE 固定项（模板，不签发）

1. R7 = 全新 batch/run/预注册/签署/GO；不复用 R6 approval（`72b95e03130fbe958c52528f1b8f484eae4872140a7336709094b9108964f98f` / 67,063 B，physical_at_supersede=**50**）；R1–R6 永久排除 E1–E6。
2. 记账：基线 50 starts/362 internal；R7 planned 386/2702；预注册诊断 ≤2 starts/14 internal；累计上限 451/3157（基线 436/3064，含诊断 438/3078）；超出需 Lead 书面再批。
3. A1 冻结字节不变（f74a4752/31d78182/c40b11df/8f9b893c/8b29d1e3/995bb12f）；preflight 期望 polar 455082e2…/0287afe0… 不变。
4. window/token/start deadline/clean stop/hard stop 按 L-08 或 Lead 最新书面记录；token 同时出现在 approval 顶层与 `approval.window.token`。
5. plan 科学字段相对 R6 的每一项变更必须出现在预注册白名单中（QC 门、诊断阶段、executor 修复、stop 规则）；A5 门禁做 plan deep-diff 白名单核对，白名单外任何科学字段变化 → FAIL。
6. executor 新 SHA + launcher/shim SHA + observe 修复 +（若批准）QC 门/DE-PSO 修复均绑定并披露；launcher 不得绕过 prestart/GO/gate 绑定。
7. 零物理证据：launcher smoke（SMOKE_NO_SOLVER）+ QC 单测（R6 真实冻结几何：design15 判 REJECTED、PRE-01/02 判 PASS）+ observe 重放证据；physical=0。
8. 签后真实 dry-run → A5 C-P2AV2R7-02（PASS 才允许 GO；硬线以 Lead 记录为准）；C 门禁后仍有 Lead 书面 GO 才可 physical。
9. 回执/审计继续三层分离（SOLVER_LOOP_VERIFIED / INTERNAL_AERO_OPTIMIZATION_GAIN / EXTERNAL_PHYSICS_SUPPORTED），fuel_burn_kg=null、physical NOT_VALIDATED、单 seed 描述性、无 winner/显著性、跨族不可 pool、R1–R6 排除披露。

## 7. 对三层结论与 E1–E6 的影响

- `SOLVER_LOOP_VERIFIED`：R6 只证明“真实 spawn + preflight 回放 byte-match + main 首个真实评估走通到求解器返回”，**main 求解循环未完成一次有效评估** → 仍 **NOT VERIFIED**（R7 目标是首次完整 main 评估与 386-start 矩阵）。
- `INTERNAL_AERO_OPTIMIZATION_GAIN`：当前 **NOT_COMPUTABLE**（无 main 端点数据）；R7 即使成功也只提供单 seed 描述性结果，不得称 winner/显著性。
- `EXTERNAL_PHYSICS_SUPPORTED`：**NOT_VALIDATED**（无外部风洞/飞行数据）；fuel_burn_kg=null 不变。
- E1–E6：R1–R6 全排除；R7 若执行，仅 R7 数据可进入 E1–E6，且 QC skip/诊断排除并在回执披露。

## 8. 披露（本复核自身边界）

- P-01：A5 未启动任何求解器（physical=0），对 NaN 机理的判断基于既有字节与零物理统计，不能替代受控真实验证。
- P-02：A5 指出 A2 面积度量矛盾，但 A5 自己的 parser 亦为独立实现；最终一致口径应由 A2 用**同一规范实现**重算并把对照表纳入 R7 包，A5 在门禁时复核。
- P-03：A2 数据 JSON 的 NaN 字面量属打包/解析质量问题，不涉及 A1/A2 代码冻结字节；但门禁脚本必须能严格解析。
- P-04：L-08 决策记录 A5 实算 6,231 B / `27898d2e…`；早前记录的 3,956 B 为不同对象，以实算为准。
- P-05：本文件不构成 R7 授权；G-P2AV2R7-PRE 模板 52 条为占位，最终文本以 R7 包与 A5 正式 gate 为准。

## 9. 签署块

| 项 | 值 |
|---|---|
| reviewer | a5-review（A5） |
| review_id | A5-P2AV2R7-STAGE-D-REVIEW-01 |
| verdict | 见 §0 |
| physical_call_count | 0 |
| solver_started | false |
| date_utc | 2026-11-11T14:02:00Z |
| 授权声明 | 本复核不构成 R7 执行授权、不构成门禁 PASS、不替代 Lead 决策 |