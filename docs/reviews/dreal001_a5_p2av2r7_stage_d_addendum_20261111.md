# A5 R7 阶段 D 补充审计：L-09 协议 D 独立复核与校准复算

- 审计 ID：A5-P2AV2R7-STAGE-D-ADDENDUM-01
- 时间：2026-11-11T14:28:58Z（UTC）
- 作者：a5-review（A5 独立复核与签署负责人）
- 工作树：D:\RCAIDE\dnext001\wt-real-a5-review（branch research/dreal001-a5-review）
- physical_call_count = 0；solver_started = false；未 push；未改 A1 / A2 / R1–R6 任何字节。
- 本文件不构成任何执行授权。

## 1. 范围与输入

- Lead L-09 决策 md：D:\RCAIDE\dnext001\wt-real-lead\docs\reviews\dreal001_lead_decision_r7_protocol_d_20261111.md，SHA256 f44641ce908d23835c28af59acce9c6a74c4dc13358de47f941fa9834bfed606（json ad5bbcc99d4203a8a94806f6aad610e2dcc03cb41026de2a9c106b52d6ab597a）。
- A5 阶段 D 主审：commit b448c3e（docs/reviews/dreal001_a5_p2av2r7_stage_d_review_20261111.md/.json，SHA256 0f731c1c…/afdda218…）。
- A2 阶段 D 交付：commit 6c098ec825d9b69b23ffc3b668c2de65281ccc3a（observe 7 处修复、R6 NaN 零物理诊断、协议 memo B+C）。
- A5 独立校准复算对象（全部只读，A5 自写 parser 与 tri-tri 实现，未调用 A2 代码）：
  - CAL-W10p-f483x418-r1/r2/r3：D:\RCAIDE\dnext001\wt-real-a1-geometry-solver\research\concorde_metaopt\dreal001\geometry\runs\DREAL001-P2CAL-20261111-02\cases\CAL-W10p-f483x418-r{1,2,3}\concorde_baseline.vspgeom（199,997 B，SHA256 8b45d104eebbb1c46e8b3c0d5f8eae217540deb407fcfffe33d1915c3cf17932）
  - design 15 冻结两族：D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\runs\DREAL001-P2A2R6-20261111-01\runtime\designs\d51866f7d3c49303\freeze\462x401\model.vspgeom（191,129 B，6b00d72d…）与 freeze\546x472\model.vspgeom（228,792 B，be8454bf…）
  - PRE-01（543x472，227,247 B，40fdd436…）/ PRE-02（483x418，199,997 B，192036cf…）

## 2. 结论摘要（verdict）

`R7_PROTOCOL_D_ACCEPTABLE_WITH_MANDATORY_DG_CLOSURE_AND_STRICTER_DISCLOSURE_B_GATE_REJECTION_INDEPENDENTLY_SUPPORTED_W10P_NONPLANAR_REAL_SUCCESS_CONFIRMED_A2_ABSOLUTE_GEOM_METRICS_NOT_REPRODUCIBLE_A5_DISSENT_RECORDED_NO_AUTHORIZATION`

1. **B（网格 QC 数据门）否决方向成立**：A5 独立复算确认 CAL-W10p-f483x418 真实 VSPAERO 求解 3/3 SOLVED（每案 physical_solver_starts=1、objective=125224.6310990786），但该几何本身非平面（z_extent=1.3587e-2 m、|z|>1e-4 节点 116/483）——已知可解案例即落在非平面侧；且 A2 的 self-int/nonplan_max 绝对数在 A5 独立严格定义下不可复现（见 §4/§5），任何 QC 阈值门都会先拒绝已知可解几何，构成未经证实的几何筛选。
2. **协议 D 可接受，但为有条件下可接受**：INVALID_NUMERICAL 容错 + 预注册诊断 + DE/PSO 修复 + 异常路径落盘 + 自动停批阈值的组合，在 A5 看来是目前证据下风险最小的可执行方案；前提是 D-G1/G2/G3 证据修正闭环、prereg §19/plan.r7_addendum 逐字固定无效判据/诊断通过判据/停批阈值、每案 invalid 审计字段与诊断-main 分离报告、异常路径最小 preflight_result/batch_summary 落盘。
3. **A5 异议如实记录**：A5 仍认为（i）B+C-lite 的零物理 QC 预检（先验证 initial 设计集是否有可解样本）有价值，Lead 不采用；（ii）R6 GO 的“单案 NaN 即硬停”被协议 D 替换，A5 曾建议保留更严硬停，Lead 决策由 Lead 承担。A5 要求以更严披露与既有硬停（执行层异常/ledger 不一致/窗口/caps/preflight 非 PASS_BYTE）补偿。
4. 本 addendum 不改变协议 D 的科学结论口径（三层结论分离、无 winner/显著性、跨族不可比、fuel=null、physical NOT_VALIDATED）；亦不构成执行授权。

## 3. W10p 真实成功核验（A5 独立）

- case_result.json（r1/r2/r3）：status=SOLVED，physical_solver_starts=1，actual_family=483x418=target_family，objective.value=125224.6310990786，created_utc 2026-11-10T21:06:55 / 21:06:59 / 21:07:03Z。
- 三份 polar 均 7,933 B、7 个 AoA（-2,0,2,4,6,8,10）/Mach 2.02 数据行，CLo/CLi/CLtot/CDo/CDi/CDtot 全部有限（E 列 inf 为已知显示项）；polar SHA256 随运行不同但数值收敛（objective 三案逐位相同）。
- 结论：W10p 是“真实求解成功且几何非平面”的标定反例，可作为 Lead §2 校准结论的独立佐证。

## 4. A5 独立几何指标复算（自写 vspgeom v3 解析 + Newell 面积 + 平面偏差非平面度）

口径说明：nonplanar_faces = 面内节点到该面 Newell 平面最大距离 > 1e-3 m 的面数；nonplanarity_max = 上述最大距离（m）；area_total = Newell 面积和；min_fan_tri_area = fan 三角化最小面积。

| geometry | nodes | faces | z_extent (m) | nodes abs(z)>1e-4 | area_total | min face area | nonplanar faces (>1e-3 m) | max plane dev (m) |
|---|---|---|---|---|---|---|---|---|
| W10p f483x418（真实 SOLVED 3/3） | 483 | 418 | 1.3587e-2 | 116 | 367.082863 | 8.325e-4 | 0 | 6.0734e-4 |
| W10p f543x472（同几何另一 tessellation） | 543 | 472 | 1.3587e-2 | 116 | 367.082863 | 3.199e-3 | 0 | 6.0734e-4 |
| design15 f1 462x401（R6 NaN） | 462 | 401 | 6.1955e-2 | 120 | 369.271374 | 1.343e-6 | 50 | 3.4213e-3 |
| design15 f2 546x472（R6 NaN） | 546 | 472 | 6.1955e-2 | 120 | 369.271374 | 8.511e-4 | 50 | 3.4213e-3 |
| PRE-01（真实 PASS_BYTE） | 543 | 472 | 9.284e-15 | 0 | 367.082666 | 3.196e-3 | 0 | 2.45e-15 |
| PRE-02（真实 PASS_BYTE） | 483 | 418 | 9.548e-15 | 0 | 379.082666 | 8.325e-4 | 0 | 9.10e-16 |

- 关键事实：**W10p 真实求解成功但 z_extent 1.36e-2 m、116 个节点离面 >1e-4 m**；design15 更差（z_extent 6.20e-2、max 平面偏差 3.42e-3）但两者同属“非平面薄面网格”，不存在 A2 暗示的“QC-clean 才可解、非平面必失败”二分。PRE-01/02 是真正平坦的 replay 几何。
- A5 面积独立值与 A2 矛盾：同一 design15 两族均为 369.271374（Newell）；W10p f483/f543 均为 367.082863。A2 geom JSON 给 462x401=366.9630105291308、546x472=336.9641621779387（差 8.9%/30 m²）、PRE-01=337.2238、PRE-02=375.5917——A2 面积/遍历实现确有缺陷（D-G1 成立）。
- A2 的 nonplanar_faces=120 与“|z|>1e-4 面数”定义吻合（d15、W10p 同为 120），其 nonplan_max=0.00990/0.00158 与 A5 平面偏差 3.42e-3/6.07e-4 不同源于定义（A2 似取最大节点 z 偏移/首三节点平面），进一步说明该指标未经校准，不能作为门。

## 5. 自交指标不可复现（D-G3 的独立证据）

A5 用严格三角形-三角形相交检测（Möller 线段-三角形穿越；仅统计不共享节点的三角对，fan 三角化）对同样几何复算：

| geometry | tris | self-intersecting tri pairs (A5) | A2 reported |
|---|---|---|---|
| W10p f483x418 | 859 | 0 | 101（Lead 表） |
| W10p f543x472 | 979 | 1 | — |
| design15 f1 462x401 | 820 | 0 | 75 |
| design15 f2 546x472 | 988 | 0 | 75 |
| PRE-01 | 979 | 1 | 0 |
| PRE-02 | 859 | 0 | 0 |

- A2 的 75/101 与严格几何检测 0/0–1 相差两个数量级，且 PRE-01（真实字节 PASS）也出现 1 对 → 该计数高度依赖容差/定义（可能计入近邻、节点落面、sliver 邻接等），不具备判别力与可复现性；不能作为 QC 门或“网格缺陷驱动 NaN”的定量依据（A5 阶段 D 主审 D-G3 判断维持）。

## 6. 对 Lead §2 校准结论的评估

- 方向性成立：W10p 真实成功且非平面 → 以非平面/自交筛数据会误伤已知可解几何；B 被否决不依赖 A2 缺陷数字。
- A2 绝对数不可采信：D-G1 面积、D-G3 自交均在 A5 独立复算下不可复现；Lead 若在后续文档引用这些绝对值，应标注来源为 A2 未修正实现或改用 A5 复算值。
- design16/17 指标不可独立验证：A5 未找到 d16/d17 的冻结/持久化 vspgeom 产物（R6 未冻结 16/17；A2 geom JSON 的 d16/d17 行无对应可复算文件），故 A2/Lead 表中 d16/d17 nonplan_max 0.01152/0.00837 仅作 A2 自报，A5 不背书；这也加强了“不能用无法复算的指标设门”的结论。
- 无判别实验：迄今没有“按预设阈值分组的几何 → 求解成功率”预注册对照，B 门缺乏因果/预测效度证据，否决正确。

## 7. 对协议 D 的独立意见与签署前提

可接受项：①INVALID_NUMERICAL 只记录不统计、不中断 arm/批次，同时保留执行层错误硬失败；②预注册诊断 DIAG-01/02（各 1 start/7 internal，走完整 main 链路，判据 SOLVED_VALID+有限 objective，双失败 main NOT_RUN）；③DE/PSO population 缺陷修复+单测；④arm 异常路径落盘最小 preflight_result/batch_summary；⑤自动停批阈值（main≥48 后 invalid>25%、单臂连续 invalid≥6、累计 invalid>64）与既有硬停。

签署前提（A5 将在正式 G-P2AV2R7-PRE 作为 mandatory corrections / 前置条件验收）：
1. D-G1/G2/G3 闭环：A2 用规范解析重算面积（两族相等、与 A5 一致 369.271374/367.082863 量级）、JSON 严格（NaN→null+raw/allow_nan=False）、自交/sliver 给定义+容差+PRE/W10p 对照；A5 在 gate 中独立复核后才 PASS。
2. prereg §19 与 plan.r7_addendum 逐字写入 INVALID_NUMERICAL 判据、诊断通过判据、自动停批阈值、诊断-main 分离报告字段（每案 status/polar SHA/reason/arm 计数/无效比例时序）。
3. 每案 invalid 审计字段与异常路径最小产物必须在包内绑定（executor/launcher SHA），签后不可改。
4. A1 冻结字节（f74a4752 / 31d78182 / c40b11df / 8f9b893c / 8b29d1e3 / 995bb12f）与 plan 科学字段不变；R1–R6 证据只读未改。
5. 无 R8 默认；诊断不计入 E1–E6；三层结论口径不变；fuel=null、physical NOT_VALIDATED。

## 8. A5 独立意见边界与异议（记录）

- A5 独立意见：协议 D 在“不可用几何 QC 门、又要避免单案无效即停”的约束下是合理折中；但 INVALID_NUMERICAL 容错会引入非随机缺失，若 invalid 比例偏高，E1–E6 的有效样本可能稀疏，最终只能给描述性结论（这本来也是单 seed 的边界）。
- 异议 1：B+C-lite 的零物理 QC 预检（先构建/冻结 design 15/16/17 并逐案验证是否有可解样本）A5 仍认为能降低“包签后全废”风险，Lead 不采用；A5 尊重决策并记录。
- 异议 2：R6 GO 的“单案 NaN 即硬停”被协议 D 替换为预注册 invalid 记录+自动停批；A5 曾建议保留更严硬停，Lead 承担该决策责任；A5 已在条件中要求更严披露与既有硬停不变。
- 责任边界：协议 D 的科学风险由 Lead 决策承担；A5 只对独立审计、门禁事实与披露完整性负责；A5 不因记录异议而改变协议 D 的科学结论口径。

## 9. 交付状态

- 本 addendum：docs/reviews/dreal001_a5_p2av2r7_stage_d_addendum_20261111.md + .json。
- 协议 D 版 gate 模板 v2：docs/reviews/dreal001_a5_p2av2r7_gate_template_protocol_d_20261111.json（52 conditions、refs_final 14 键、signature_requirements、plan deep-diff 白名单待包到填实；status TEMPLATE_NOT_ISSUED，未签发）。
- 正式 G-P2AV2R7-PRE 待 A2 R7 包 commit 报到后 20 分钟内出具（目标 15:05Z、硬线 15:20Z）。

## 10. A5 签署块

- 审计人：a5-review（A5）
- verdict：R7_PROTOCOL_D_ACCEPTABLE_WITH_MANDATORY_DG_CLOSURE_AND_STRICTER_DISCLOSURE_B_GATE_REJECTION_INDEPENDENTLY_SUPPORTED_W10P_NONPLANAR_REAL_SUCCESS_CONFIRMED_A2_ABSOLUTE_GEOM_METRICS_NOT_REPRODUCIBLE_A5_DISSENT_RECORDED_NO_AUTHORIZATION
- physical_call_count = 0；solver_started = false；未 push；未改 A1/A2/R1–R6 字节。
- 本文件不构成任何新执行授权；R7 执行仍须 A2 包 → A5 G-P2AV2R7-PRE PASS → Lead 签署 → 签后 dry-run → A5 C-P2AV2R7-02 PASS → Lead GO。