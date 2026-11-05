# D-12D-006 A2 只读重算报告：Batch1 / Batch1b / Batch2（14 案）

- 任务：task-192（D12-A2 只读重算）；owner=a6-code-dev；报告版本 2026-11-05
- 生成时间（UTC）：2026-11-05T04:42:03Z
- 工作树：<repo-d12d006>，分支 research/d12d006-aero-improvements，HEAD aef2cb71e07aa28abfc28e34b14bf9dc1579c2e3
- 路径占位符：<repo>=RCAIDE 主仓库根（含 envs/RCAIDE/python.exe）；<repo-d12d006>=本工作树根；<EXT>=外部记忆根下 d12d006/a2（本报告生成环境）
- 数据来源（只读）：<repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z
- 归档清单 data_manifest.json：bytes=204529，sha256=4026f4223fe8e6737af5091e8fafec240d197e7f128a989075abe777a74ca0a1
- 硬边界：physical_call_count=0；solver_starts=0；subprocess_calls=0；solver_invoked=false；network_used=false；未 import 任何求解器/Mission/RCAIDE；未修改任何旧归档/旧报告；未 commit/push
- 标签：VSPAERO_INTERNAL_ONLY；LF-M2.02=NOT_VALIDATED；BODY-CORR=BLOCKED；CDo/CDtot 为 VSPAERO 内部量，不得当作已验证的整机阻力/燃油目标

## 1 执行摘要

- 覆盖 14/14 案：Batch1（S0–S3）、Batch1b（S4、S5）、Batch2（S6、B2-01..B2-07），独立解析 14 份冻结 polar（LF 规范 3021 B，单行 48 列）与归档 JSON 逐项比对。
- 系数比对 226 项：PASS 226，FAIL 0（容差 1e-12；Re/1e6 为 1e-9），最大绝对差 0.000e+00。
- 派生自检 148/152 项参与判定，FAIL 0；Ew=inf 的 0/0 派生伪影 11 项按 EXPLAINED 处理。
- 归档 deltas 复现 75 项：PASS 71，FAIL 0（其中非有限递增解释 4 项）。
- 数据溯源：14/14 polar 的实际字节 sha256 等于 data_manifest 的 sha256_canonical_lf，且 v1/v1b/b2 记录的 polar raw sha256 等于 manifest 的 sha256_raw（raw 3025 B CRLF → LF 3021 B）；关键 JSON 9/9 PASS。
- 理论对照：S6（AoA=1）实测 CLtot=0.037164223 落在独立确认带 [0.03,0.045] 内；S3/S4（AoA=2）落在 Ackeret 线化超声速解析带 [0.067341186, 0.079554325] 内，亦落在 Gate2 post-hoc 诊断带 [0.06,0.09] 内；12D（S5、B2-01..07）无独立解析参考，仅作有限性/量级/内部一致性核对。
- 历史 SU2（D-12D-002）本轮 status=NOT_EXECUTED（class C 未授权），只作限定背景，不构成交叉验证。
- 发现 1 项 minor 文档缺陷 DOC-A2-01（旧 S2 结论文本 CLtot 差写作 7.6e-6，实际归档系数差 9.652104e-06）；DOC-A2-02/03 为一致性确认。
- 总体判定：PASS_WITH_DOC_FINDINGS（仅数值一致性复核；不产生新物理证据，不改变旧判定与标签）。

## 2 方法与容差

1. 只读加载归档 JSON（UTF-8）与冻结 polar；polar 表头按 Beta/Mach/CLtot 定位，数据行唯一，列名直接映射。
2. 记录值侧：v1=Batch1 cases[*].coefficients（13 键）、v1b=results_summary cases[*].coefficients（15 键）、Batch2=cases[*].all_coefficients（18 键）；这些键全部是 polar 列名，逐项比对。
3. 派生自检：三项和恒等式、L/D、E（AR=Bref^2/Sref，按案取 4 或约 1.830）、LoDw、Batch1b/Batch2 的 CLwtot==CLo 与 CDwtot==CDo（归档 clamp 行为）、Ew 在 CDiw=0 时必须非有限。
4. deltas：用重算值重新计算归档中登记的 base/case/delta/rel（或 rel_pct），与归档数值逐项比对；Batch2 的 primary/derived 增量、密度三连、重复性均复现，S6/S3 跨 AoA 比例单独复算。
5. 溯源：对 14 份 polar 与 9 个关键 JSON 计算实际 sha256 与 CRLF→LF 规范 sha256，与 data_manifest 的 raw/canonical 双哈希及归档记录的 raw sha 三方交叉。

| 项目 | 容差 |
|---|---|
| 系数绝对差 | 1e-12 |
| Re/1e6 绝对差 | 1e-9 |
| 三项和恒等式 | 2e-12（12 位小数舍入） |
| L/D 恒等式 | 1e-9 |
| E 公式（AR 按案） | 1e-6（polar 单精度/舍入） |
| deltas 绝对差 | 2e-12；rel_pct 1e-9 |
| 溯源判定 | 实际 sha256 == manifest sha256_canonical_lf；记录 raw sha == manifest sha256_raw |

## 3 数据与状态总表（14 案）

| case | batch | 几何 | AoA | Mach | Re/1e6 | 归档状态 | CLtot | CDi | CDtot | E |
|---|---|---|---|---|---|---|---|---|---|---|
| S0_STD_M0p1_base | Batch1 | std | 2° | 0.100 | 0.239352 | SOLVED_VALID | 0.126545398 | 0.001314258 | 0.020946562 | 0.969621 |
| S1_STD_M0p1_wn128 | Batch1 | std | 2° | 0.100 | 0.239352 | SOLVED_VALID | 0.134634956 | 0.001522505 | 0.021167613 | 0.947430 |
| S2_STD_M0p1_wi0 | Batch1 | std | 2° | 0.100 | 0.239352 | SOLVED_VALID | 0.126555051 | 0.001314545 | 0.020946858 | 0.969558 |
| S3_STD_M2p02_base | Batch1 | std | 2° | 2.020 | 4.834912 | FAILED_INVALID_POLAR | 0.074251032 | 0.002606540 | 0.013789408 | 0.168318 |
| S4_STD_M2p02_wn128 | Batch1b | std | 2° | 2.020 | 4.834912 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.074250958 | 0.002606536 | 0.013789404 | 0.168318 |
| S5_D12_M2p02_base | Batch1b | d12 | 2° | 2.020 | 89.397006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.070832612 | 0.002488241 | 0.009796561 | 0.350730 |
| S6_STD_M2p02_aoa1 | Batch2 | std | 1° | 2.020 | 4.834912 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.037164223 | 0.000652722 | 0.011813973 | 0.168388 |
| B2-01 | Batch2 | d12 | 2° | 2.020 | 89.397006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.068720124 | 0.002408677 | 0.009720833 | 0.341027 |
| B2-02 | Batch2 | d12 | 2° | 2.020 | 89.397006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.070394960 | 0.002467158 | 0.009775138 | 0.349370 |
| B2-03 | Batch2 | d12 | 2° | 2.020 | 89.397006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.068491960 | 0.002400696 | 0.009704726 | 0.339892 |
| B2-04 | Batch2 | d12 | 2° | 2.020 | 89.397006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.071941630 | 0.002521957 | 0.010164783 | 0.356962 |
| B2-05 | Batch2 | d12 | 2° | 2.020 | 89.397006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.067018850 | 0.002349255 | 0.009652284 | 0.332555 |
| B2-06 | Batch2 | d12 | 2° | 2.020 | 89.397006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.068664188 | 0.002421414 | 0.009725748 | 0.338681 |
| B2-07 | Batch2 | d12 | 2° | 2.020 | 89.397006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.068491877 | 0.002399809 | 0.009703839 | 0.340017 |

注：Batch1 的 S0–S2 为 Mach 0.10 标准矩形翼；S3/S4/S6 为 Mach 2.02 标准矩形翼（AR=4）；S5 与 B2-01..07 为 12D 主翼（Bref=25.604638 m、Sref=358.25 m²、AR≈1.830、Re≈8.94e7）。S3 的归档状态为 FAILED_INVALID_POLAR（Ew=inf 触发 fail-closed），S4/S5/S6/B2 为 SOLVED_VALID_WITH_DERIVED_WARNINGS。

## 4 Batch1（S0–S3）：主系数、尾迹/迭代 delta、S3 派生伪影

| case | CLo | CLi | CLtot | CDo | CDi | CDtot | E | LoDw | Ew |
|---|---|---|---|---|---|---|---|---|---|
| S0_STD_M0p1_base | -0.000685575 | 0.127230974 | 0.126545398 | 0.019632304 | 0.001314258 | 0.020946562 | 0.969621 | 6.057520 | 1.009909991712 |
| S1_STD_M0p1_wn128 | -0.000686022 | 0.135320978 | 0.134634956 | 0.019645108 | 0.001522505 | 0.021167613 | 0.947430 | 6.581949 | 1.769927638406 |
| S2_STD_M0p1_wi0 | -0.000685575 | 0.127240626 | 0.126555051 | 0.019632314 | 0.001314545 | 0.020946858 | 0.969558 | 6.057892 | 1.009778243121 |
| S3_STD_M2p02_base | -0.000390514 | 0.074641546 | 0.074251032 | 0.011182868 | 0.002606540 | 0.013789408 | 0.168318 | -0.034921 | inf |

尾迹/迭代设置的描述性 delta（相对 S0；仅归档系数重算，非新实验）：

| 对比 | 系数 | 绝对差 | 相对差 |
|---|---|---|---|
| S1_STD_M0p1_wn128 vs S0_STD_M0p1_base | CLtot | 8.090e-03 | +6.3926% |
| S1_STD_M0p1_wn128 vs S0_STD_M0p1_base | CDi | 2.082e-04 | +15.8452% |
| S1_STD_M0p1_wn128 vs S0_STD_M0p1_base | CDtot | 2.211e-04 | +1.0553% |
| S2_STD_M0p1_wi0 vs S0_STD_M0p1_base | CLtot | 9.652e-06 | +0.0076% |
| S2_STD_M0p1_wi0 vs S0_STD_M0p1_base | CDi | 2.863e-07 | +0.0218% |
| S2_STD_M0p1_wi0 vs S0_STD_M0p1_base | CDtot | 2.958e-07 | +0.0014% |
| S3_STD_M2p02_base vs S0_STD_M0p1_base | CLtot | -5.229e-02 | -41.3246% |
| S3_STD_M2p02_base vs S0_STD_M0p1_base | CDi | 1.292e-03 | +98.3279% |
| S3_STD_M2p02_base vs S0_STD_M0p1_base | CDtot | -7.157e-03 | -34.1686% |

- S1（NumWakeNodes 8→128）使 CLtot 增加约 6.4%、CDi 增加约 15.8%，与旧结论文本一致（DOC-A2-02）。
- S2（WakeIters 5→0，冻结初始尾迹）相对 S0 的 CLtot 差为 9.652e-06、CDi 差为 2.863e-07；旧结论文本所称 7.6e-6 与归档系数差 9.652104e-06 不符（DOC-A2-01）。
- S3 的 Ew=inf 由 CDiw=0 的 0/0 派生比导致（CLiw=0、CDiw=0），归档 polar 因而被判 FAILED_INVALID_POLAR；其主系数均有限，但按原流程不得作为阻力/燃油对比的物理证据。

## 5 Batch1b（S4、S5）：15 项系数、单因子与跨几何 delta

| case | CLo | CLi | CLtot | CDo | CDi | CDtot | E | L/D | LoDw | Ew | CMytot |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S4_STD_M2p02_wn128 | -0.000390514 | 0.074641473 | 0.074250958 | 0.011182868 | 0.002606536 | 0.013789404 | 0.168318 | 5.384639 | -0.034921 | inf | -0.014776994 |
| S5_D12_M2p02_base | -0.000255212 | 0.071087824 | 0.070832612 | 0.007308320 | 0.002488241 | 0.009796561 | 0.350730 | 7.230355 | -0.034921 | inf | -0.019446219 |

S4 vs S3（仅 NumWakeNodes 8→128 的单因子变化，归档 deltas 复现）：

| 系数 | 归档绝对差 | 重算绝对差 | 归档相对差 | 重算相对差 | 状态 |
|---|---|---|---|---|---|
| CLo | 2.000e-12 | 2.000e-12 | 5.121e-09 | 5.121e-09 | PASS |
| CLi | -7.357e-08 | -7.357e-08 | -9.856e-07 | -9.856e-07 | PASS |
| CLtot | -7.357e-08 | -7.357e-08 | -9.908e-07 | -9.908e-07 | PASS |
| CDo | -7.000e-11 | -7.000e-11 | -6.260e-09 | -6.260e-09 | PASS |
| CDi | -4.351e-09 | -4.351e-09 | -1.669e-06 | -1.669e-06 | PASS |
| CDtot | -4.420e-09 | -4.420e-09 | -3.205e-07 | -3.205e-07 | PASS |
| CMytot | 4.615e-08 | 4.616e-08 | 3.123e-06 | 3.123e-06 | PASS |
| E | -5.260e-08 | -5.260e-08 | -3.125e-07 | -3.125e-07 | PASS |

S5 vs S4（跨几何 + 跨 Re，非单因子，归档相对差复现）：

| 系数 | 归档相对差 | 重算相对差 | 状态 |
|---|---|---|---|
| CLtot | -4.604e-02 | -4.604e-02 | PASS |
| CDi | -4.538e-02 | -4.538e-02 | PASS |
| CDtot | -2.896e-01 | -2.896e-01 | PASS |
| CDo | -3.465e-01 | -3.465e-01 | PASS |
| E | 1.084e+00 | 1.084e+00 | PASS |

- S4 与 S3 的差异在 1e-6 相对量级，说明仅改尾迹节点数对主系数影响极小；S5 相对 S4 的 CLtot/CDtot/CDo 明显下降（约 -4.6%/-29.0%/-34.6%），E 上升约 +108%，但跨几何比较不能归因于单一因子。
- S4/S5 的 Ew=inf 属允许的派生警告（derived_column_diagnosis.classification=DERIVED_RATIO_NONFINITE_ALLOWED）。

## 6 Batch2（S6、B2-01..B2-07）：8 案与门禁

| case | AoA | CLtot | CDi | CDtot | CDo | E | Ew |
|---|---|---|---|---|---|---|---|
| S6_STD_M2p02_aoa1 | 1.0 | 0.037164223 | 0.000652722 | 0.011813973 | 0.011161251 | 0.168388 | inf |
| B2-01 | 2.0 | 0.068720124 | 0.002408677 | 0.009720833 | 0.007312156 | 0.341027 | inf |
| B2-02 | 2.0 | 0.070394960 | 0.002467158 | 0.009775138 | 0.007307980 | 0.349370 | inf |
| B2-03 | 2.0 | 0.068491960 | 0.002400696 | 0.009704726 | 0.007304030 | 0.339892 | inf |
| B2-04 | 2.0 | 0.071941630 | 0.002521957 | 0.010164783 | 0.007642826 | 0.356962 | inf |
| B2-05 | 2.0 | 0.067018850 | 0.002349255 | 0.009652284 | 0.007303029 | 0.332555 | inf |
| B2-06 | 2.0 | 0.068664188 | 0.002421414 | 0.009725748 | 0.007304335 | 0.338681 | inf |
| B2-07 | 2.0 | 0.068491877 | 0.002399809 | 0.009703839 | 0.007304030 | 0.340017 | inf |

- 8/8 案 outcome_class=SOLVED_VALID_WITH_DERIVED_WARNINGS，verify_polar_status=PASS_WITH_WARNINGS，各案 gate_result 全 true（派生自检中逐案断言）。
- S6 为 AoA=1 的独立超声速确认 case；B2-01..07 均为 12D 几何。B2 预算：class A cap=20，本批 8 次、累计 14 次、剩余 6 次（legacy.remaining_6=CLOSED，不结转）。
- 标签：VSPAERO_INTERNAL_ONLY / NOT_VALIDATED / validated_fuel_label=false；CDo/CDtot 不得外推为整机阻力。

## 7 归档 deltas 复现

| 分组 | 系数 | 归档 delta | 重算 delta | 状态 |
|---|---|---|---|---|
| v1b.S4_vs_S3（NumWakeNodes 8->128，单因子） | CLo | 2.000e-12 | 2.000e-12 | PASS |
| v1b.S4_vs_S3（NumWakeNodes 8->128，单因子） | CLi | -7.357e-08 | -7.357e-08 | PASS |
| v1b.S4_vs_S3（NumWakeNodes 8->128，单因子） | CLtot | -7.357e-08 | -7.357e-08 | PASS |
| v1b.S4_vs_S3（NumWakeNodes 8->128，单因子） | CDo | -7.000e-11 | -7.000e-11 | PASS |
| v1b.S4_vs_S3（NumWakeNodes 8->128，单因子） | CDi | -4.351e-09 | -4.351e-09 | PASS |
| v1b.S4_vs_S3（NumWakeNodes 8->128，单因子） | CDtot | -4.420e-09 | -4.420e-09 | PASS |
| v1b.S4_vs_S3（NumWakeNodes 8->128，单因子） | CMytot | 4.615e-08 | 4.616e-08 | PASS |
| v1b.S4_vs_S3（NumWakeNodes 8->128，单因子） | E | -5.260e-08 | -5.260e-08 | PASS |
| v1b.S5_vs_S4（跨几何/跨 Re，非单因子） | CLtot |  | -3.418e-03 | PASS |
| v1b.S5_vs_S4（跨几何/跨 Re，非单因子） | CDi |  | -1.183e-04 | PASS |
| v1b.S5_vs_S4（跨几何/跨 Re，非单因子） | CDtot |  | -3.993e-03 | PASS |
| v1b.S5_vs_S4（跨几何/跨 Re，非单因子） | CDo |  | -3.875e-03 | PASS |
| v1b.S5_vs_S4（跨几何/跨 Re，非单因子） | E |  | 1.824e-01 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | CLtot | 3.450e-03 | 3.450e-03 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | CDi | 1.213e-04 | 1.213e-04 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | CDtot | 4.601e-04 | 4.601e-04 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | CLo | -1.183e-05 | -1.183e-05 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | CDo | 3.388e-04 | 3.388e-04 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | CMytot | -3.048e-03 | -3.048e-03 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | E | 1.707e-02 | 1.707e-02 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | L/D | 1.995e-02 | 1.995e-02 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | LoDw | 0.000e+00 | 0.000e+00 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | Re/1e6 | 0.000e+00 | 0.000e+00 | PASS |
| Batch2.perturbation.B2-04_vs_B2-03 | Ew | nan | nan | PASS_NONFINITE_EXPLAINED |
| Batch2.perturbation.B2-05_vs_B2-03 | CLtot | -1.473e-03 | -1.473e-03 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | CDi | -5.144e-05 | -5.144e-05 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | CDtot | -5.244e-05 | -5.244e-05 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | CLo | 3.495e-08 | 3.495e-08 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | CDo | -1.001e-06 | -1.001e-06 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | CMytot | -3.727e-03 | -3.727e-03 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | E | -7.338e-03 | -7.338e-03 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | L/D | -1.143e-01 | -1.143e-01 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | LoDw | 0.000e+00 | 0.000e+00 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | Re/1e6 | 0.000e+00 | 0.000e+00 | PASS |
| Batch2.perturbation.B2-05_vs_B2-03 | Ew | nan | nan | PASS_NONFINITE_EXPLAINED |
| Batch2.perturbation.B2-06_vs_B2-03 | CLtot | 1.722e-04 | 1.722e-04 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | CDi | 2.072e-05 | 2.072e-05 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | CDtot | 2.102e-05 | 2.102e-05 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | CLo | -6.988e-07 | -6.988e-07 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | CDo | 3.048e-07 | 3.048e-07 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | CMytot | -1.085e-04 | -1.085e-04 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | E | -1.211e-03 | -1.211e-03 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | L/D | 2.453e-03 | 2.453e-03 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | LoDw | -9.421e-05 | -9.421e-05 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | Re/1e6 | 0.000e+00 | 0.000e+00 | PASS |
| Batch2.perturbation.B2-06_vs_B2-03 | Ew | nan | nan | PASS_NONFINITE_EXPLAINED |
| Batch2.repeatability.B2-07_vs_B2-03 | CLtot | -8.338e-08 | -8.338e-08 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | CDi | -8.871e-07 | -8.871e-07 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | CDtot | -8.868e-07 | -8.868e-07 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | CLo | -1.100e-11 | -1.100e-11 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | CDo | 3.060e-10 | 3.060e-10 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | CMytot | 3.442e-07 | 3.442e-07 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | E | 1.248e-04 | 1.248e-04 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | L/D | 6.364e-04 | 6.364e-04 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | LoDw | 0.000e+00 | 0.000e+00 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | Re/1e6 | 0.000e+00 | 0.000e+00 | PASS |
| Batch2.repeatability.B2-07_vs_B2-03 | Ew | nan | nan | PASS_NONFINITE_EXPLAINED |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-02_Tess_6_6 | CLtot | 1.675e-03 | 1.675e-03 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-02_Tess_6_6 | CDi | 5.848e-05 | 5.848e-05 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-02_Tess_6_6 | CDtot | 5.431e-05 | 5.431e-05 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-02_Tess_6_6 | CLo | 1.458e-07 | 1.458e-07 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-02_Tess_6_6 | CDo | -4.176e-06 | -4.176e-06 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-02_Tess_6_6 | CMytot | -9.447e-04 | -9.447e-04 | PASS |
| Batch2.density_trio.B2-02_Tess_6_6_vs_B2-03_Tess_12_12 | CLtot | -1.903e-03 | -1.903e-03 | PASS |
| Batch2.density_trio.B2-02_Tess_6_6_vs_B2-03_Tess_12_12 | CDi | -6.646e-05 | -6.646e-05 | PASS |
| Batch2.density_trio.B2-02_Tess_6_6_vs_B2-03_Tess_12_12 | CDtot | -7.041e-05 | -7.041e-05 | PASS |
| Batch2.density_trio.B2-02_Tess_6_6_vs_B2-03_Tess_12_12 | CLo | 1.379e-07 | 1.379e-07 | PASS |
| Batch2.density_trio.B2-02_Tess_6_6_vs_B2-03_Tess_12_12 | CDo | -3.950e-06 | -3.950e-06 | PASS |
| Batch2.density_trio.B2-02_Tess_6_6_vs_B2-03_Tess_12_12 | CMytot | 8.000e-04 | 8.000e-04 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-03_Tess_12_12 | CLtot | -2.282e-04 | -2.282e-04 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-03_Tess_12_12 | CDi | -7.981e-06 | -7.981e-06 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-03_Tess_12_12 | CDtot | -1.611e-05 | -1.611e-05 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-03_Tess_12_12 | CLo | 2.838e-07 | 2.838e-07 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-03_Tess_12_12 | CDo | -8.126e-06 | -8.126e-06 | PASS |
| Batch2.density_trio.B2-01_Tess_3_3_vs_B2-03_Tess_12_12 | CMytot | -1.448e-04 | -1.448e-04 | PASS |

Batch2 bits（重算值）：

- 密度三连：B2-01(Tess 3) → B2-02(Tess 6) 的 CLtot rel=2.437e-02；B2-02 → B2-03(Tess 12) 的 CLtot rel=-2.703e-02。
- 扰动（vs B2-03）：B2-04 的 CLtot rel=5.037e-02；B2-05 的 CLtot rel=-2.151e-02；B2-06 的 CLtot rel=2.515e-03。
- 重复性（B2-07 vs B2-03）：ΔCLtot=-8.338e-08，ΔCDi=-8.871e-07，属数值噪声量级。
- S6/S3 跨 AoA：CLtot 比例=0.500521305（归档 0.500521305），相对线性 0.5 期望=1.001042609（归档 1.001042609），即 S6 与 S3 近似线性缩放；状态 PASS。

## 8 理论对照（解析式，仅量级参照）

- AR=4 标准翼：Bref=4、Sref=4，AR=Bref²/Sref=4。
- 亚声速 Helmbold（仅用于 S0–S2 的描述性参照，Mach 0.10）：CLα=2πAR/(√(AR²+4)+2)=3.883222077 /rad，AoA=2° 时 CL=0.135550022。
- 超声速 Ackeret 线化 + 一阶有限展长：β=√(M²−1)=1.755106834；CLα,2D=4/β=2.279063543 /rad；CLα,3D=CLα,2D/(1+CLα,2D/(πAR))=1.929182861 /rad。
- 由此：AoA=2° 时 CL_2D=0.079554325、CL_3D=0.067341186；AoA=1° 时 CL_2D=0.039777163、CL_3D=0.033670593。
- 对 Gate2 repair 注册的 derivation 互校（1e-12）：全部一致。

| case | 参考 | 下限 | 上限 | 实测 CLtot | 相对带中点 | 判定 |
|---|---|---|---|---|---|---|
| S3_STD_M2p02_base | Ackeret 线化超声速 + 一阶有限展长（解析式，AoA=2） | 0.067341 | 0.079554 | 0.074251032 | +1.094% | IN_BAND |
| S3_STD_M2p02_base | Gate2 repair 诊断带（post-hoc，[0.06,0.09]） | 0.060000 | 0.090000 | 0.074251032 | — | IN_BAND |
| S4_STD_M2p02_wn128 | Ackeret 线化超声速 + 一阶有限展长（解析式，AoA=2） | 0.067341 | 0.079554 | 0.074250958 | +1.094% | IN_BAND |
| S4_STD_M2p02_wn128 | Gate2 repair 诊断带（post-hoc，[0.06,0.09]） | 0.060000 | 0.090000 | 0.074250958 | — | IN_BAND |
| S6_STD_M2p02_aoa1 | S6 独立超声速确认带（expected_v2，AoA=1） | 0.030000 | 0.045000 | 0.037164223 | -0.895% | IN_BAND |
| S6_STD_M2p02_aoa1 | Ackeret 线化超声速 + 一阶有限展长（解析式，AoA=1） | 0.033671 | 0.039777 | 0.037164223 | +1.199% | IN_BAND |
| S0_STD_M0p1_base | 亚声速 Helmbold 有限翼展（AR=4，AoA=2；M0.1 描述性） | 0.135550 | 0.135550 | 0.126545398 | -6.643% | DESCRIPTIVE_ONLY |
| S1_STD_M0p1_wn128 | 亚声速 Helmbold 有限翼展（AR=4，AoA=2；M0.1 描述性） | 0.135550 | 0.135550 | 0.134634956 | -0.675% | DESCRIPTIVE_ONLY |
| S2_STD_M0p1_wi0 | 亚声速 Helmbold 有限翼展（AR=4，AoA=2；M0.1 描述性） | 0.135550 | 0.135550 | 0.126555051 | -6.636% | DESCRIPTIVE_ONLY |
| S5_D12_M2p02_base | 12D 主翼：无独立解析参考（expected_v2 cl_expected_range=null） | — | — | 0.070832612 | — | NO_ANALYTIC_REFERENCE |
| B2-01 | 12D 主翼：无独立解析参考（expected_v2 cl_expected_range=null） | — | — | 0.068720124 | — | NO_ANALYTIC_REFERENCE |
| B2-02 | 12D 主翼：无独立解析参考（expected_v2 cl_expected_range=null） | — | — | 0.070394960 | — | NO_ANALYTIC_REFERENCE |
| B2-03 | 12D 主翼：无独立解析参考（expected_v2 cl_expected_range=null） | — | — | 0.068491960 | — | NO_ANALYTIC_REFERENCE |
| B2-04 | 12D 主翼：无独立解析参考（expected_v2 cl_expected_range=null） | — | — | 0.071941630 | — | NO_ANALYTIC_REFERENCE |
| B2-05 | 12D 主翼：无独立解析参考（expected_v2 cl_expected_range=null） | — | — | 0.067018850 | — | NO_ANALYTIC_REFERENCE |
| B2-06 | 12D 主翼：无独立解析参考（expected_v2 cl_expected_range=null） | — | — | 0.068664188 | — | NO_ANALYTIC_REFERENCE |
| B2-07 | 12D 主翼：无独立解析参考（expected_v2 cl_expected_range=null） | — | — | 0.068491877 | — | NO_ANALYTIC_REFERENCE |

- S6 实测 CLtot=0.037164223，位于独立确认带 [0.03,0.045] 内；也落在 AoA=1 的 Ackeret 带内。
- S3/S4 实测分别 0.074251032 / 0.074250958，落在 AoA=2 的 Ackeret 带 [0.067341186, 0.079554325] 内；Gate2 post-hoc 诊断带 [0.06,0.09] 亦覆盖。
- 旧 a0 预注册的亚声速 Helmbold 带 [0.10844,0.16266] 状态已为 VOID_FOR_SUPERSONIC_CASES（理由：Helmbold 亚声速公式在 Mach 2.02 不适用；S3/S4 观测 CLtot 低于该带下界）；本次不追溯改标签，仅引用其作废状态。
- S5 与 B2-01..07 的 expected_v2 明确 cl_expected_range=null、independent_confirmation=false：12D 无独立解析参考，只能做有限性、符号/量级、与 baseline/密度/扰动的一致性核对。

## 9 历史 SU2 对照（限定背景，非交叉验证）

- 本轮 su2_crosscheck.json：status=NOT_EXECUTED；class C 预算 cap=4、已用 0、剩余 4、LOCKED_NOT_AUTHORIZED；无 Lead 授权、A 线已关闭，故本轮未执行 SU2。

| case | mesh | CL | CD | CMy | 迭代 | 力收敛 | 末200步 CMy rel p2p | verdict |
|---|---|---|---|---|---|---|---|---|
| HFS-02 | medium | 9.278e-02 | 6.820e-03 | -3.808e-02 | 4999 | True | 6.303e-09 | FORCE_CONVERGED_2_LEVEL_ONLY |
| HFS-03 | fine | 9.548e-02 | 7.117e-03 | -3.941e-02 | 4999 | True | 5.050e-06 | FORCE_CONVERGED_2_LEVEL_ONLY |

- 历史数据属 D-12D-002（run p1p3-fullchain-20261031T0407Z）：isolated 12D main wing (span 25.604638 m, Sref 358.25 m2, NACA65-203 sections)；冻结条件 Mach 2.02、高度 18288 m、AoA=2.8398297488947493°、ReCref=89397005.8767656。
- 历史 run 的孤立 12D 主翼 Euler 结果，属 D-12D-002，非本轮（D-12D-006）新执行
- HFS-02/03 的 AoA=2.8398297488947493°，与本轮 LF 合同的 AoA=2° 不一致，不能直接 CL 对比
- 没有 CL 匹配对照；历史 note 明确 Euler CL=0.0928 与 mission CL=0.1334 不匹配
- su2_crosscheck.json 本轮 status=NOT_EXECUTED，class C 未授权；不得宣称 SU2 交叉验证结果

## 10 数据溯源

| case | 实际字节 | CRLF 数 | 实际 sha256（前16） | == manifest canonical LF | 记录 raw sha == manifest raw | 状态 |
|---|---|---|---|---|---|---|
| S0_STD_M0p1_base | 3021 | 0 | 920ae8c9e341373e… | True | True | PASS |
| S1_STD_M0p1_wn128 | 3021 | 0 | f54d81d2ec3792bd… | True | True | PASS |
| S2_STD_M0p1_wi0 | 3021 | 0 | 65087b8cff3d0297… | True | True | PASS |
| S3_STD_M2p02_base | 3021 | 0 | 61e49c249d611cce… | True | True | PASS |
| S4_STD_M2p02_wn128 | 3021 | 0 | a78a33ee500cc9f8… | True | True | PASS |
| S5_D12_M2p02_base | 3021 | 0 | 5842830cf4faa097… | True | True | PASS |
| S6_STD_M2p02_aoa1 | 3021 | 0 | 7d384e69941c9ec9… | True | True | PASS |
| B2-01 | 3021 | 0 | 4aeb47fc84e72f17… | True | True | PASS |
| B2-02 | 3021 | 0 | e080fd65b11cfdca… | True | True | PASS |
| B2-03 | 3021 | 0 | 3fa9af027ae4bc47… | True | True | PASS |
| B2-04 | 3021 | 0 | 39d213c9aaa40d31… | True | True | PASS |
| B2-05 | 3021 | 0 | 1b86475b0fbfdbec… | True | True | PASS |
| B2-06 | 3021 | 0 | 9bd645e3d3bee3b9… | True | True | PASS |
| B2-07 | 3021 | 0 | 99702bbfaf2eed0b… | True | True | PASS |

关键归档 JSON：

| 路径 | 字节 | 实际 sha256（前16） | == canonical LF | == raw | 状态 |
|---|---|---|---|---|---|
| evidence/v1/batch1_results.json | 17608 | 5833d60342d316f7… | True | True | PASS |
| evidence/v1/per_case_conclusions.json | 7531 | 9a0dccbb4091c326… | True | True | PASS |
| evidence/v1/case_summary_reconciliation.json | 7364 | 5bb8ca0429f3ce8b… | True | True | PASS |
| evidence/v1b/results_summary.json | 15180 | 91d83c626960d77b… | True | True | PASS |
| evidence/v1b/per_case_conclusions.json | 6944 | d59d83eeb1364dfa… | True | True | PASS |
| evidence/batch2/batch2_results.json | 47367 | 0ffb4906d65ee6d5… | True | True | PASS |
| evidence/batch2/batch2_report.md | 9810 | 76ac086ce68dce24… | True | True | PASS |
| su2_crosscheck.json | 806 | 5c6dbe68f2ebf4ce… | True | True | PASS |
| approval_and_budget_ledger.json | 3583 | a58c9454263a8f32… | True | True | PASS |

- 结论：14/14 polar 与 9/9 关键 JSON 的字节级哈希与 data_manifest 双哈希链一致；归档只读，未做任何 LF 规范化写回。

## 11 文档缺陷与一致性核对

| 编号 | 级别 | 位置 | 判定 |
|---|---|---|---|
| DOC-A2-01 | minor | evidence/v1/per_case_conclusions.json -> cases[S2_STD_M0p1_wi0].conclusion | MISMATCH |
| DOC-A2-02 | info | evidence/v1/per_case_conclusions.json -> cases[S1_STD_M0p1_wn128].conclusion | CONSISTENT |
| DOC-A2-03 | info | evidence/v1/per_case_conclusions.json -> cases[S3_STD_M2p02_base].conclusion | CONSISTENT |

### DOC-A2-01（minor，MISMATCH）

- 旧文本要点：7.6e-6/2.9e-7
- 重算：DeltaCLtot=9.652104e-06, DeltaCDi=2.863240e-07
- 评估：S2 结论文本称 CLtot/CDi 与 S0 相差 7.6e-6/2.9e-7，但归档系数重算为 9.652104e-06/2.863240e-07：CDi 的 2.9e-7 四舍五入一致，CLtot 数值不符（约 27%）。polar 与 batch1_results 数据本身一致，属旧结论文本的数值笔误。
- 建议：后续修订旧结论文本时更正为 9.65e-06（或同时给出 CLi 差）；本次不修改旧归档。

### DOC-A2-02（info，CONSISTENT）

- 旧文本要点：CLtot +6.4%、CDi +15.8%
- 重算：CLtot +6.392613%, CDi +15.845164% vs S0
- 评估：四舍五入到 1 位小数后与文本一致（6.4%/15.8%），无缺陷。
- 建议：无。

### DOC-A2-03（info，CONSISTENT）

- 旧文本要点：Ew=inf / CDwtot 非零 / CLwtot 近零
- 重算：CLwtot=-0.000390514345, CDwtot=0.011182867698, Ew=inf
- 评估：与归档 polar/报告一致：Ew=inf 是 CDiw=0 的派生比退化，主系数有限。
- 建议：无。

- 与旧 Batch2 报告「60/60 项一致」的声明核对：本次独立重算覆盖 Batch2 全部 144 项系数（8 案 × 18 键），全部 PASS，与 60/60 声明不矛盾（统计口径不同）；未发现新的 Batch2 数值不一致。

## 12 结论与限制

1. 14/14 案的归档主系数与独立解析冻结 polar 逐位一致（最大绝对差 0.000e+00），归档 deltas 与跨案比例全部复现。
2. 派生列行为可解释：Ew=inf 仅出现在 CDiw=0 的 0/0 派生比；S3 因此按旧流程判 FAILED_INVALID_POLAR，S4/S5/S6/B2 则记为允许的派生警告。
3. 理论量级一致性：S6 在独立确认带内、S3/S4 在 Ackeret 带与 post-hoc 诊断带内；12D 无解析参考，不声称物理验证。
4. 本轮为只读重算，physical_call_count=0；不改变任何旧判定、标签与结论；CDo/CDtot 仍不得当作真实阻力/燃油目标；LF-M2.02 仍为 NOT_VALIDATED；BODY-CORR 仍为 BLOCKED。
5. 限制：无新求解器数据、无网格/物理收敛再评估；历史 SU2 仅作限定背景；文档缺陷只记录不修改旧归档。

## 附录 A 输出文件与 SHA256

| 文件 | 字节 | sha256 |
|---|---|---|
| out/full_recompute.json | 207475 | 15d678da0a0e6729e52a418957a643c23597034123a76baff4251a13c0a29924 |
| out/full_cases_summary.csv | 3446 | ee043cf1f7fcaea41a3cc313d700b85cb13d091c90ddcefe8c13d5f0190b81ed |
| out/full_coefficient_comparison.csv | 19267 | cb16c01ceb3fda1a7e4e82d6b8e27da3344545d3d33a95828b332c8d300d2368 |
| out/full_derived_checks.csv | 12928 | d2d4d635e7c5bc21753f74b062bacdc3e2b078d28ca42618e7e2d2caa08a1894 |
| out/full_provenance.csv | 7368 | 8927779e25dbab821fb188513b7b183ca4169657958e3668eb5a05255928cf3f |
| out/full_deltas.csv | 18660 | d96d65c434bab0119155a6e425aa22b2483787a0f27b7500474a7e1a9afee529 |
| out/full_theory.csv | 3932 | 9e578058ff2b7c700cd6a9491b73591f4c7cd3d95e20b408bf881860668bf72b |
| scripts/recompute_all.py | 67059 | 03ed2e15d566a623bd62f2f59669f682b7b7b6e0e696b5c89b00d5132e15e101 |

## 附录 B 复现命令（只读；不启动任何求解器）

    cd <repo-d12d006>
    set PYTHONIOENCODING=utf-8
    <repo>/envs/RCAIDE/python.exe <EXT>/scripts/recompute_all.py

脚本仅用 Python 标准库读取归档与 polar，输出到 EXT 的 out/ 与 docs/reviews/ 新报告；不 import 求解器、不启动子进程、无网络。

