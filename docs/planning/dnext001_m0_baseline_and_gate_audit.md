# D-NEXT-001 M0 审计：基线、参考量与物理门禁（只读审计，零真实求解）

- 任务：GitHub Issue #8 / D-NEXT-001，F 线（真实评价与航空约束）M0 交付
- 审计对象：
  - `research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml`（241 行，frozen: false）
  - `research/concorde_metaopt/configs/task_fixed_cruise.yaml`（43 行，mass_contract.status: frozen）
- 基线 commit：`ea8ad97833eb5ceab291faae643c141a2b219749`（= S3 封账 c7221fb + 计划文档）
- 审计性质：**只读**。本文件不运行 VSPAERO / SU2 / RCAIDE Mission / WaveDrag，不产生任何真实气动数据；
  审计中的数值全部来自仓库内既有冻结归档与源码，逐条给出路径。
- 结论先行：**12D 变量集合与固定机身可以冻结为"软件契约"；所有气动物理量、CG/静稳定、整机阻力与油耗
  一律保持 NOT_VALIDATED，不得冻结。** 本审计不宣称任何 PASS。

---

## 1. 12 维设计变量：边界、单位、目标路径

来源：`configs/design_space_12d_lifting_surfaces.yaml:28-124`（变量集合 owner 已批准 D-12D-001，2026-10-30；
边界仍为 `provisional_until_geometry_perturbation`，frozen: false）。

| ID | 变量 | 单位 | 基线 | 下界 | 上界 | scale | RCAIDE 目标路径 |
|---|---|---|---|---|---|---|---|
| W01 | wing_area | m^2 | 358.25 | 300.0 | 420.0 | 100.0 | main_wing.areas.reference |
| W02 | aspect_ratio | 无量纲 | 1.83 | 1.50 | 2.20 | 1.0 | main_wing.aspect_ratio |
| W03 | sweep_1 | deg | 67.0 | 62.0 | 72.0 | 10.0 | main_wing.segments.section_1.sweeps.quarter_chord |
| W04 | sweep_2 | deg | 48.0 | 40.0 | 56.0 | 10.0 | main_wing.segments.section_2.sweeps.quarter_chord |
| W05 | sweep_3 | deg | 71.0 | 66.0 | 76.0 | 10.0 | main_wing.segments.section_3.sweeps.quarter_chord |
| W06 | span_location_2 | 无量纲 | 0.480469 | 0.35 | 0.58 | 0.1 | main_wing.segments.section_2.percent_span_location |
| W07 | span_location_3 | 无量纲 | 0.945313 | 0.85 | 0.98 | 0.1 | main_wing.segments.section_3.percent_span_location |
| W08 | chord_ratio_2 | 无量纲 | 0.408284 | 0.30 | 0.50 | 0.1 | main_wing.segments.section_2.root_chord_percent |
| W09 | chord_ratio_3 | 无量纲 | 0.130178 | 0.08 | 0.20 | 0.1 | main_wing.segments.section_3.root_chord_percent |
| W10 | tip_twist | deg | 0.0 | -4.0 | 4.0 | 5.0 | main_wing.segments.tip.twist |
| V01 | vertical_tail_area | m^2 | 33.91 | 28.0 | 40.0 | 10.0 | vertical_stabilizer.areas.reference |
| V02 | vertical_tail_sweep_delta | deg | 0.0 | -10.0 | 10.0 | 10.0 | vertical_stabilizer.quarter_chord_sweep_delta |

固定机身（不参与优化、但**不得删除**，仍在 15 名物理设计中出现）：
F01 fuselage_length = 61.66 m；F02 fuselage_fineness = 4.30；F03 fuselage_height_width_ratio = 1.152778
（source: owner decision 2026-10-30，item 2；`design_space_12d_lifting_surfaces.yaml:126-144`）。

**关键边界判定**：
- 12 维包含 V01/V02（垂尾面积与垂尾后掠增量），**禁止为"简化"删掉 V01/V02**：它们承担航向稳定性方向的可控性，
  且历史 15D 结果不得当作 12D 证据（yaml:5-7 的显式约束）。
- 边界数值本身属 provisional：冻结前必须完成"12 变量几何效应矩阵 + 派生量对 RCAIDE 复算 + owner 批准"
  （`design_space_12d_lifting_surfaces.yaml:17-20`）。
- 设计空间只改变提升面，机身固定：**任何"整机阻力/油耗"结论都必须先过 BODY-CORR 门禁，否则只能表述为
  "提升面内部气动系数"**。

派生规则（`design_space_12d_lifting_surfaces.yaml:194-221`）中与参考量强相关的三条：
- projected_span = sqrt(wing_area * aspect_ratio)
- wing_root_chord = wing_area / (projected_span * K)，K = sum(0.5 * delta_s_i * (r_i + r_i+1))
- wing_wetted_area = sum(2.003 * exposed_segment_area)（t/c = 0.03）

---

## 2. Sref / Cref / Bref 参考量审计

### 2.1 归档中实际注入 VSPAERO 的参考量（唯一可查证据）

来源：`research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/summary.json:173`
（字段 `injected_inputs`，setup 文件 wing355_thin.vspaero / wing355_thick.vspaero，42 行）：

| 量 | 注入值 | 口径判定 |
|---|---|---|
| Sref | 358.25 m^2 | 等于 `main_wing.areas.reference` = `wing.exposed_area_m2`（yaml:156）；定义口径一致 |
| Cref | 18.489893 m | 等于 `main_wing.mean_aerodynamic_chord_m`（yaml:154）；定义口径一致 |
| Bref | 25.604638 m | 等于 `main_wing.projected_span_m`（yaml:150）；定义口径一致 |
| Xcg | 16.821978259514246 m | **不是全机 CG**，是机翼气动中心（详见第 3 节）；此处作为力矩参考点属错误口径 |
| Ycg / Zcg | 0 / 0 | 对称面假设；未做横向配平 |
| MachStart / MachEnd | 2.02 / 2.02 | 与冻结任务巡航 Mach 一致 |
| AlphaStart / AlphaEnd | 2.0 / 2.0 | 固定 2° 攻角，未做配平搜索 |
| Beta | 0 | 无侧滑 |
| RefFlag | 0 | 表示"由注入值给定参考量"，而不是求解器内部默认 |
| Symmetry | 0 | 未启用对称简化 |
| NCPU | 4 | 与串行/≤4 线程约束一致 |
| StopBeforeRun | 1 | 该归档只做输入准备，未真正求解（`what_this_does_not_prove` 明确无精度/收敛/尾迹证据） |

### 2.2 参考量的冻结判定

- **可冻结（定义口径，而非数值）**：
  1. Sref ≡ 主翼 reference/exposed area（当前 358.25 m^2 是 12D 基线值，随 W01/W02 变化时必须由派生规则重算）；
  2. Cref ≡ 主翼 MAC（基线 18.489893 m，随几何重算）；
  3. Bref ≡ 主翼 projected span（基线 25.604638 m，随 W01/W02 重算）；
  4. RefFlag=0 + 显式注入 + 求解后交叉核对 Sref/Cref/Bref 三项，作为**防静默默认值**的强制检查。
- **不可冻结（数值本身）**：任何把 Sref=358.25 / Cref=18.489893 / Bref=25.604638 当作常量写死到真实求解调用中的做法，
  在 12D 优化中都可能产生"系数不可比"伪改进。
- **历史教训（必须写进验收）**：同一归档 `:211` 记录 VSPAERO 6.2.0 曾因 12 行模板漏写 "=" 而**静默使用 Sref=1.0**，
  导致 CL 虚高约 358 倍、CDo=NaN。即"求解器打印出系数 ≠ 系数有物理意义"。
  Tier0 必须包含一次 Sref 注入核对（见 `dnext001_f_tier0_budget_proposal.md` 的 T0-4）。

---

## 3. CG / AC 口径审计（最容易被误用的两个数）

| 量 | 数值 | 真实含义 | 来源 |
|---|---|---|---|
| 机翼气动中心 X | 16.821978259514246 m | `wing_ac_x_m`：**机翼**气动中心，不是全机 CG | `optimization_runs/geometry-check-p1-20261028T1740/baseline_geometry.json`；`geometry-check-p1-20261028T1835/geometry_cases.jsonl` baseline 记录的 `wing_ac_x_m` |
| 全机几何 CG X | 28.287395109126685 m | `cg_x_m`：按几何模型质量分配得到的**全机 CG**（诊断值） | 同上 `baseline_geometry.json` 的 `cg_x_m` |
| 二者差值 | 11.4654 m | 若把机翼 AC 当 CG，力矩参考点前移 11.47 m | 本审计计算 |
| 尾翼 AC X | 6.405519112626756 m | `tail_ac_x_m`（几何诊断） | 同上 baseline 记录 |
| 几何静稳定裕度 | 0.13707938483236962 | `static_margin`：基于 AC 位置的**几何诊断**，不是气动导数意义下的静稳定裕度 | 同上 |

**错误来源已定位**：`docs/reviews/p1p3_fullchain_validation_report_20261031.md:45` 把 16.821978 写成
"PROVISIONAL CG"；而 VSPAERO 注入（summary.json:173）沿用了该值作为 Xcg。**这是口径错误，不是数值误差。**

**审计判定**：
- 16.821978 只能用于：机翼内部气动系数（CL/CDi 等）的力矩参考点声明，并且必须显式标注 "moment reference = wing AC"。
- 16.821978 **不得用于**：全机配平、静稳定裕度、尾翼配平能力、质量 CG 归一化、油耗/航程结论。
- 28.287395 是几何模型诊断 CG（`mass_and_cg: PROVISIONAL_NOT_FROZEN`，yaml:219-221），**同样不可冻结**：
  它没有经过气动配平校验，也不是称重结果。
- 静稳定裕度 0.137 只能表述为"几何 AC 间距比"，不得表述为"静稳定"。

---

## 4. 力轴与力矩参考点

- 现有归档只覆盖**输入准备**（StopBeforeRun=1），因此严格地说：**力轴定义尚未经过真实求解核对**。
- 当前唯一可声明的口径：VSPAERO 自由来流沿 +X（Mach 2.02），AlphaStart=2.0°、Beta=0，
  力矩参考点由注入的 Xcg/Ycg/Zcg 给定；力轴与体轴/风轴的符号约定**待 Tier0 T0-5 核对**。
- 禁止表述："VSPAERO 的 CL/CDi 就是整机升阻特性"、"CL/CDi 可直接换算整机油耗"。
  允许表述（且必须带限定）："VSPAERO 内部气动系数，参考量 Sref/Cref/Bref，力矩参考点 Xcg=机翼 AC，
  物理验证状态 VSPAERO_INTERNAL_ONLY / NOT_VALIDATED"。
- 真实整机阻力必须先过 BODY-CORR（机身阻力/干扰修正），当前状态 **BLOCKED**。

---

## 5. 质量口径审计：136000 kg 单巡航进入质量 vs 184880 kg 几何 MTOW

来源：`configs/task_fixed_cruise.yaml`（task_id: concorde-fixed-cruise-p2-v1, version p2-2026-10-29b）
与 `geometry-check-p1-20261028T1835/baseline_geometry.json`。

| 量 | 数值 | 含义 | 可否冻结 |
|---|---|---|---|
| start_mass_kg | 136000 | **单巡航段进入质量**（不是 MTOW） | 可冻结（任务合同，见下） |
| fuel_loaded_kg | 46800 | 该巡航段携带燃油 | 可冻结 |
| operating_empty_kg | 78700 | OEW（上游声明值，几何模型未称重） | 仅任务合同层，非物理验证 |
| payload_kg / cargo_kg | 9500 / 1000 | 商载 / 货载 | 任务合同层 |
| zero_fuel_mass（计算） | 89200 = 78700+9500+1000 | 零燃油质量 | 与 start_mass 自洽：136000-89200=46800 ✓ |
| max_takeoff_kg | 185000 | 任务合同起飞上限 | 任务合同层 |
| max_zero_fuel_kg | 92000 | 任务合同零燃油上限（余量 2800 kg） | 任务合同层 |
| max_fuel_kg | 95680 | 任务合同最大载油 | 任务合同层 |
| mass_total_takeoff_kg（几何） | 184880 | 几何模型按部件质量分配得到的 MTOW | **不可冻结/不可混用** |

**关键判定**：
1. 136000 kg 是"固定巡航进入状态"，yaml 注释与冻结证据（2026-10-29 节流阀扫描：
   185000→1.2708、155000→1.0374、150000→1.0008、145000→1.0163（P1 几何不可行）、136000→0.9455）都指向这一点；
   该质量合同 status=frozen 指的是**任务描述冻结**，**不是**"油耗已物理验证"。
2. 184880 kg 是几何模型推算的 MTOW（= OEW 78700 + 其余质量分配），与任务上限 185000 kg 相差 120 kg；
   两者都不是称重结果，**不得把 136000 与 184880 相互归一化**，也不得写成"136000 是 MTOW 的 73.6%"这类隐含归一化结论。
3. 单巡航段燃烧量 34109.5 kg（46800 - 剩余）只作为合成/归档链路的量级锚点，**不是**物理验证过的油耗。
4. 质量归一化油耗（kg/kg 或 kg/(kg·km)）在 CG 与 BODY-CORR 未解决前**禁止使用**。

---

## 6. 约束定义审计（10 项，冻结 schema）

来源：`research/concorde_metaopt/evaluation/contract.py`，顺序即契约顺序（F 线 `ordered_constraints` 复用同一顺序）：

| # | 约束名 | 表达式（g ≤ 0 可行） | 单位 | 现状 |
|---|---|---|---|---|
| 1 | geometry_invalid | 1 - 合法标志（越界/C01/C02/C03/C04 违反时为 1） | 1 | 软件层已实现 |
| 2 | task_mass_balance | (start_mass - (zero_fuel_mass + fuel_loaded)) / start_mass | 1 | 任务合同自洽（=0） |
| 3 | fuel_capacity_excess | (fuel_loaded - max_fuel_kg) / max_fuel_kg | 1 | 任务合同层 |
| 4 | zero_fuel_excess | (zero_fuel_mass - max_zero_fuel_kg) / max_zero_fuel_kg | 1 | 任务合同层 |
| 5 | takeoff_excess | (start_mass - max_takeoff_kg) / max_takeoff_kg | 1 | 任务合同层 |
| 6 | fuel_remaining_deficit | (reserve_kg - (fuel_loaded - fuel_burn_kg)) / fuel_loaded | 1 | 依赖真实油耗 → NOT_VALIDATED |
| 7 | max_throttle | 实际推力/可用推力 - 1 | 1 | 依赖真实推进模型 → NOT_VALIDATED |
| 8 | cruise_range_error | 1 - 实际航程/任务航程 | 1 | 依赖真实 L/D → NOT_VALIDATED |
| 9 | mission_convergence | 求解收敛标志（不收敛为 1） | 1 | 依赖真实任务求解 → NOT_VALIDATED |
| 10 | trim_attitude_limit | |alpha_end| / 12.0 - 1（MAX_ATTITUDE_DEG=12.0） | 1 | VSPAERO 固定 AlphaStart=2.0，尚不支持真实配平 |

- 可行性容差 `FEASIBILITY_TOLERANCE = 1e-12`，残差上限 `RESIDUAL_LIMIT = 1e-4`，姿态上限 `MAX_ATTITUDE_DEG = 12.0`。
- **约束 6–10 目前只有"接口定义"是可冻结的；其数值语义在物理门禁未过前一律 NOT_VALIDATED。**
- 冻结判定：约束**名称、顺序、单位、g≤0 方向**可冻结；约束 6–10 的**阈值与判定能力**不可冻结，
  必须保持 NOT_VALIDATED，直到 Tier0 及以上真实求解给出可复现证据。

---

## 7. 可冻结 / 不可冻结清单

### 7.1 可以冻结（软件契约层，冻结的是"定义"而不是"物理结论"）

1. 12D 变量集合 = W01–W10 + V01–V02，共 12 维，含 V01/V02。
2. 固定机身 F01–F03 的基线数值与"固定但不删除"的地位。
3. 任务巡航定义：Mach 2.02 / 18288 m / 3028020 m；objective = fuel_burn_kg（kg）。
4. 质量合同：start_mass 136000 kg、fuel_loaded 46800 kg、OEW 78700 kg、payload 9500 kg、cargo 1000 kg、
   max_takeoff 185000 kg、max_fuel 95680 kg、max_zero_fuel 92000 kg（**仅作为任务描述**）。
5. 参考量口径：Sref ≡ 主翼 reference area；Cref ≡ 主翼 MAC；Bref ≡ 主翼 projected span；RefFlag=0 显式注入。
6. 10 项约束的名称、顺序、单位与 g≤0 方向。
7. EvaluatorProtocol / EvaluationRecord / BudgetLedger 的记录字段与"失败值 null"规则（见 F 线代码）。

### 7.2 不可冻结（保持 NOT_VALIDATED / NOT_RUN）

1. VSPAERO 超声速升阻精度与收敛性（LF-M2.02 = **NOT_VALIDATED**）。
2. 机身阻力与干扰修正（BODY-CORR = **BLOCKED**）。
3. 高保真全机阻力（HF-M2.02 = **PARTIAL**，不等于可用）。
4. CG 与静稳定：16.821978 是机翼 AC、28.287395 是几何诊断 CG，均不可作冻结约束。
5. 整机阻力/油耗/航程/配平结论。
6. 12D 变量边界数值（provisional，需几何效应矩阵与 RCAIDE 复算后才能申请冻结）。
7. 垂尾几何偏差（派生 tail span 5.009331 m vs 上游声明 6.0 m）未解决前，垂尾相关结论不可冻结。
8. 质量归一化油耗。

### 7.3 硬性禁止

- 禁止把 16.821978259514246 m 当作全机 CG 或配平参考点。
- 禁止删除 V01/V02 或把固定机身从合同里"简化掉"。
- 禁止把 VSPAERO 内部 CL/CDi 当作真实整机油耗/阻力。
- 禁止把 136000 kg 当作 MTOW，或与 184880 kg 做归一化互证。
- 禁止在没有新证据的情况下把任何门禁从 NOT_VALIDATED 改成 PASS。

---

## 8. 门禁与历史事实（不得改写）

| 门禁/阶段 | 状态 | 证据 |
|---|---|---|
| VSPAERO 低速/超声速 LF-M2.02 | NOT_VALIDATED | `docs/reviews/p1p3_fullchain_validation_report_20261031.md`；`docs/reviews/p4_route_a_s3_requirement_matrix.md` |
| BODY-CORR（机身阻力/干扰） | BLOCKED | 同上 |
| HF-M2.02 高保真 | PARTIAL | 同上 |
| S1 21000 runs 主端点 | NO_SIGNIFICANT_IMPROVEMENT | S1 冻结证据 `research/concorde_metaopt/evidence/` |
| S2 Full MAML vs FOMAML | Full MAML 更差 | S2 冻结证据 |
| S3 四检验 | NULL / NO_EVIDENCE；阶段验收 NOT_ISSUED；S4 NOT_APPROVED | S3 冻结证据 + `docs/reviews/p4_route_a_s3_requirement_matrix.md` |

---

## 9. 审计结论

1. 12D 提升面集合（含 V01/V02）与固定机身 F01–F03 在**软件契约**层面是自洽且可冻结的；边界数值不是。
2. 参考量口径（Sref/Cref/Bref）与几何派生量一致，但**必须随设计变量重算并显式注入**，否则系数不可比；
   历史上已出现过 Sref 静默变成 1.0 的严重缺陷，必须用 Tier0 核对。
3. CG/AC 口径是当前最大误用风险：16.821978 m 是机翼 AC，不是全机 CG；全机几何 CG 为 28.287395 m。
   二者不可互换，任何配平/静稳定结论在气动验证前都不成立。
4. 质量口径：136000 kg 是巡航进入质量，184880 kg 是几何 MTOW 推算值，二者不可混用或归一化。
5. 约束 1–5 是任务合同自洽性检查；约束 6–10 的物理语义仍 NOT_VALIDATED。
6. 因此 F 线本轮只交付**零真实求解**的软件闭环与申请文档；物理门禁维持原状，等待 owner 对 Tier0 的单独批复。

## 10. 证据来源清单

- `research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml`（全文，含 :5-7、:17-20、:28-124、:126-144、:146-192、:194-221、:223-241）
- `research/concorde_metaopt/configs/task_fixed_cruise.yaml`（全文 43 行）
- `research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/summary.json:173`（injected_inputs）、`:211`（Sref=1.0 缺陷）
- `research/concorde_metaopt/optimization_runs/geometry-check-p1-20261028T1740/baseline_geometry.json`（cg_x_m、wing_ac_x_m、tail_ac_x_m、static_margin、mass_*）
- `research/concorde_metaopt/optimization_runs/geometry-check-p1-20261028T1835/geometry_cases.jsonl`（31 条，baseline 记录）
- `research/concorde_metaopt/evaluation/contract.py`（10 项约束定义与容差）
- `docs/reviews/p1p3_fullchain_validation_report_20261031.md:43-45`（D-12D-002 来流条件；16.821978 被误写为 PROVISIONAL CG）
- `docs/reviews/p4_route_a_s3_requirement_matrix.md`（S3/S4 与门禁状态）
