# G-M0R-ADMISSION-01 checklist

{
  "schema": "dreal001.a5.m0r_gate_checklist.v1",
  "gate_id": "G-M0R-ADMISSION-01",
  "status": "ISSUED",
  "issued_by": "a5-review",
  "issued_at_utc": "2026-11-13T07:25:55Z",
  "target_package": {
    "commit": "63e93564a7cd2266b9f25e5234155e56460146fb",
    "dir": "D:/RCAIDE/dnext001/wt-real-a3-stats-routeb/docs/evidence/dreal001/m0r_20261113",
    "family_sha256": "98b84f5ecf6e18a7be90e21da41b243dccb664f09034366ea3b58d777f1c0311"
  },
  "checks": [
    {
      "id": "MRC-01",
      "category": "package",
      "severity": "CRITICAL",
      "requirement": "M0-R 包为全新 commit/目录，不修改旧 T0-4/A3 M0/F1/F2/R1-R10 字节；新 family_sha256 非 ada424cc、非 40fdd436。",
      "expected": "commit/SUMS；旧 SHA 仅出现在 superseded；旧树 diff=0",
      "source_requirement": "R01",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-02",
      "category": "package",
      "severity": "CRITICAL",
      "requirement": "M0-R 包内 SHA256SUMS 覆盖全部交付文件；A5 逐行复算全匹配。",
      "expected": "SUMS N/N；0 mismatch",
      "source_requirement": "R27",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-03",
      "category": "gate",
      "severity": "CRITICAL",
      "requirement": "gate 使用新 ID G-M0R-ADMISSION-01，不复用 G-T0-ADMISSION-01 commit/SHA/字节。",
      "expected": "新 gate json/md/checklist/conditions/SUMS；旧 gate 不改",
      "source_requirement": "R28",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-04",
      "category": "binding",
      "severity": "CRITICAL",
      "requirement": "gate 绑定 L-30 27f8d91、L-30-A01 30166a0、L-31 544629a、A5 requirements f8b70703…/16,397B/30 条。",
      "expected": "SHA/bytes 全匹配",
      "source_requirement": "R01/R28",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-05",
      "category": "zero_physical",
      "severity": "CRITICAL",
      "requirement": "M0-R 全程零物理：physical_call_count=0；无 run dir/ledger/token/authorization；无 solver spawn。",
      "expected": "A5 独立检查；spawn=[]；run_dir/ledger false",
      "source_requirement": "R17/R27",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-06",
      "category": "geometry",
      "severity": "CRITICAL",
      "requirement": "任务族几何重绑 post-fix 546x480：baseline vspgeom 16da482a…/225,414B；openvsp_geometry d20ee7ad；F1R2 12D audit 7a90b977。",
      "expected": "6 tasks geometry=16da；零物理复建 2/2 字节同",
      "source_requirement": "R02",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-07",
      "category": "geometry",
      "severity": "CRITICAL",
      "requirement": "40fdd436…/543x472/227,247B 不得出现在 active family；只可作 historical/superseded。",
      "expected": "active 引用 0；披露含 40fd 历史",
      "source_requirement": "R02",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-08",
      "category": "geometry",
      "severity": "HIGH",
      "requirement": "每设计记录 vspgeom SHA；baseline SHA 只作族身份；不得以单一 SHA 代表所有设计。",
      "expected": "per-design 字段；baseline 分开",
      "source_requirement": "R24",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-09",
      "category": "tasks",
      "severity": "CRITICAL",
      "requirement": "6 任务 ID/因子与 L-30-A01 完全一致；alt 全 18,288 m；无 15/20 km 副本。",
      "expected": "6/6 字段匹配；alt set={18288}",
      "source_requirement": "R06/R21",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-10",
      "category": "tasks",
      "severity": "CRITICAL",
      "requirement": "split 3 train/1 val/2 blind test；meta_test 盲、不在 M1/M2 运行、不揭盲。",
      "expected": "split 集合/计数；盲测流程",
      "source_requirement": "R06",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-11",
      "category": "tasks",
      "severity": "CRITICAL",
      "requirement": "每 task 记录 Mach/alt/CL/q/Vinf/Rho/ReCref/L_ref/mass/SREF_REF/fingerprint/geometry/evaluator/solver；ID 非旧 ada424cc。",
      "expected": "6 任务表；A5 逐字段复算",
      "source_requirement": "R21",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-12",
      "category": "atmosphere",
      "severity": "CRITICAL",
      "requirement": "q 单源 ATM-F1R2；p=7171.544888256813、T=216.65、R=287.05287、rho=0.1153178340089936、a=295.06801842964956、ReCref=89,397,005.8767656。",
      "expected": "字段/复算一致；仅一处大气模块",
      "source_requirement": "R04",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-13",
      "category": "atmosphere",
      "severity": "CRITICAL",
      "requirement": "6 任务 q 精确等于 20,483.940233430174（M2.02）/24,297.194081414087（M2.2）/16,265.063806566453（M1.8），rel≤1e-12。",
      "expected": "A5 6/6 复算；无 ISO 混用",
      "source_requirement": "R04",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-14",
      "category": "atmosphere",
      "severity": "HIGH",
      "requirement": "Vinf 6 任务精确匹配 596.0373972278921（2.02）/649.14964（2.2）/531.122433（1.8），rel≤1e-12。",
      "expected": "6/6 复算",
      "source_requirement": "R04",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-15",
      "category": "atmosphere",
      "severity": "HIGH",
      "requirement": "披露 ATM-F1R2 vs ISO-1 q rel≈1.24e-5；M2.02 与 F1R2 连续；2.2/1.8 不继承 F1R2 expected polar。",
      "expected": "prereg/task metadata 含披露",
      "source_requirement": "R25",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-16",
      "category": "lift_reference",
      "severity": "CRITICAL",
      "requirement": "L_ref=q*SREF_REF*CL_target；SREF_REF 运行时由 post-fix baseline 重算并 SHA 绑定；不得硬编码 358.25，不得 fallback。",
      "expected": "SREF 字段/SHA；grep 358.25 active=0；负例 fail-closed",
      "source_requirement": "R05",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-17",
      "category": "lift_reference",
      "severity": "CRITICAL",
      "requirement": "6 任务 L_ref/mass 精确匹配 L-30-A01：1,247,523.170066/127.211960；1,394,290.601839/142.178073；1,479,759.862543/150.893512；1,653,849.258137/168.645690；990,583.048479/101.011359；1,107,122.230653/112.895049。",
      "expected": "A5 复算 6/6 rel≤1e-12",
      "source_requirement": "R05",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-18",
      "category": "lift_reference",
      "severity": "HIGH",
      "requirement": "质量带 100–190 t；6 任务 mass 全在带内；越界 fail-closed。",
      "expected": "min/max 检查；负例",
      "source_requirement": "R05",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-19",
      "category": "lift_reference",
      "severity": "HIGH",
      "requirement": "LREF-1..8 fail-closed 检查存在且单测覆盖；不得 fallback 到旧 L_ref/旧几何/ISO。",
      "expected": "代码/负例；无 fallback",
      "source_requirement": "R26",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-20",
      "category": "executor",
      "severity": "CRITICAL",
      "requirement": "task-capable executor 逐任务注入 Mach/alt/CL/Vinf/Rho/ReCref/q；任务缺失 fail-closed。",
      "expected": "接口/单测；缺任务负例",
      "source_requirement": "R03",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-21",
      "category": "executor",
      "severity": "CRITICAL",
      "requirement": "6 个 per-task .vspaero deck；deck SHA 进包；M2.02 deck 与 F1R2 参数（Mach 2.02/Vinf/Rho/ReCref/alpha）一致。",
      "expected": "6 deck SHA；A5 读 deck 核字段",
      "source_requirement": "R03/R22",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-22",
      "category": "executor",
      "severity": "HIGH",
      "requirement": "同一设计跨 task 复用同一 vspgeom 字节（build once）；per-task 记录 vspgeom/deck/polar SHA。",
      "expected": "vspgeom equality；SHA 表",
      "source_requirement": "R22",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "同一设计 shared vspgeom 字节已记录；polar SHA 属真实执行产物，M0-R 零物理不生成，M1-A 记录。"
    },
    {
      "id": "MRC-23",
      "category": "dry_run",
      "severity": "CRITICAL",
      "requirement": "零物理 dry-run 覆盖 6 任务×3 参考设计；spawn=[]、solver_outputs=[]、physical=0、无 run dir。",
      "expected": "A5 独立 run/复核证据",
      "source_requirement": "R03/R27",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-24",
      "category": "design_space",
      "severity": "CRITICAL",
      "requirement": "设计空间同时绑 raw YAML 8b29d1e3…/10,846B 与 C01–C04 cross constraints。",
      "expected": "raw SHA；C01–C04 字段/SHA",
      "source_requirement": "R07",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-25",
      "category": "design_space",
      "severity": "CRITICAL",
      "requirement": "M1 sampler/executor 强制执行 check_cross_constraints；违反 C01–C04 负例被拒。",
      "expected": "代码/负例；canonical 不替代",
      "source_requirement": "R07",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "C01–C04 cross constraints 已写入并明确由 M1 sampler/executor 强制执行；负例测试属 M1-A 实现门，M0-R 只预注册。"
    },
    {
      "id": "MRC-26",
      "category": "alpha_lift",
      "severity": "CRITICAL",
      "requirement": "7 点 alpha 固定；max_refine_sweeps 单值（0 或明确列表）；alpha_refine 明确；无 frozen=0/tasks=2 矛盾。",
      "expected": "单值/列表；一致性检查",
      "source_requirement": "R08",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-27",
      "category": "alpha_lift",
      "severity": "CRITICAL",
      "requirement": "报告独立升力残差与插值不确定性；C2 残差不得仅由构造性插值得到。",
      "expected": "独立复算；残差/不确定性",
      "source_requirement": "R08",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "独立升力残差与插值不确定性已预注册（CTX-D/EP-02/EP-03）；M0-R 零物理不计算。"
    },
    {
      "id": "MRC-28",
      "category": "mask",
      "severity": "HIGH",
      "requirement": "12D_ALL_ACTIVE；10D_ACTIVE_PLUS_2_INACTIVE=DEFERRED_TO_M1；不得声明 V01/V02 零效应。",
      "expected": "mask 字段；corrected text",
      "source_requirement": "R09",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-29",
      "category": "effect_threshold",
      "severity": "HIGH",
      "requirement": "MIN_EFFECT_REL>0 且预注册；建议 max(2×U_within,1e-3)；不得 0.0。",
      "expected": "常量/字段/单测；A5 复核定义",
      "source_requirement": "R10",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "MIN_EFFECT_REL floor=1e-3 已预注册；实际 max(2*U_within,1e-3) 待 M1-A repeat 后冻结。"
    },
    {
      "id": "MRC-30",
      "category": "cross_task",
      "severity": "CRITICAL",
      "requirement": "M1-A CTX-A/B 预注册：4 任务×3 设计；效应量分离≥max(2U_within,1e-3)；Spearman n=3 仅描述性、无 p 值。",
      "expected": "定义/阈值；披露 n=3",
      "source_requirement": "R11",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-31",
      "category": "cross_task",
      "severity": "CRITICAL",
      "requirement": "4/4 任务可分或 PHYSICAL_TASK_FAMILY_BLOCKED；不得仅整体乘常数的表面迁移。",
      "expected": "CTX 结果/阻断流程",
      "source_requirement": "R11",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-32",
      "category": "budget",
      "severity": "CRITICAL",
      "requirement": "M1-A 15/105 caps 18/126 retry0；4 任务×3 设计+1 exact repeat+2 preflight；repeat 预注册 task/design/deck SHA。",
      "expected": "预算/算术/repeat 字段",
      "source_requirement": "R12",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "M1-A 15/105 预算与 1 exact repeat 已预注册；repeat 的 task/design/deck SHA 仍待 M1-A authorization 冻结。"
    },
    {
      "id": "MRC-33",
      "category": "budget",
      "severity": "CRITICAL",
      "requirement": "M1-B 66/462 caps 70/490 retry0；64 labels+2 preflight；仅 M1-A 通过后单独授权。",
      "expected": "预算/标签/授权边界",
      "source_requirement": "R13",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "M1-B 66/462 预算已预注册；64 labels 中 meta_val 用途须在 M1-B authorization 前显式限定为验证、不参与拟合。"
    },
    {
      "id": "MRC-34",
      "category": "budget",
      "severity": "CRITICAL",
      "requirement": "M3-A 34/238 caps 38/266 retry0；32 labels+2 preflight；M3 前不运行 meta_test。",
      "expected": "预算/揭盲流程",
      "source_requirement": "R14",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-35",
      "category": "budget",
      "severity": "CRITICAL",
      "requirement": "总 115/805 hard 126/882 labels96 preflight6 retry0；M3-B NOT_AUTHORIZED。",
      "expected": "汇总算术；M3-B 字段",
      "source_requirement": "R15",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-36",
      "category": "accounting",
      "severity": "CRITICAL",
      "requirement": "五口径账本（physical/charged/cached/design/planned）分离；charged vs actual 双报；不得混写。",
      "expected": "账本 schema/模板",
      "source_requirement": "R15/R27",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-37",
      "category": "admission",
      "severity": "CRITICAL",
      "requirement": "admission=DEFERRED_TO_M1A_WITH_PRE_REGISTERED_CHECKS；M0/M0-R 不签 admission；首条真实 M1 标签按 validity/status/identity 判定，不按目标值。",
      "expected": "字段/schema；无 PASS 声明",
      "source_requirement": "R16",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-38",
      "category": "authorization",
      "severity": "CRITICAL",
      "requirement": "M0-R 不创建 run dir/ledger/token/authorization；不复用 #9 R10 或 #10 F1R2/F2R2 approval/token。",
      "expected": "零物理检查；token/approval 搜索",
      "source_requirement": "R17",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-39",
      "category": "authorization",
      "severity": "CRITICAL",
      "requirement": "M1-A/M1-B/M3 各自新 authorization/approval/A5/Lead GO；M1-A 结果不自动授权后续。",
      "expected": "流程字段；无自动继承",
      "source_requirement": "R29",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-40",
      "category": "evidence_text",
      "severity": "HIGH",
      "requirement": "删除 “A5 P1-05 verified envelope 1.8/2.02/2.2”；P1-05 实际 1.8/2.0/2.2、18,288m、58f63bfc/199,997B、TREND_ONLY、2.02 NOT_COMPARABLE。",
      "expected": "文本/manifest；不得引用不存在结论",
      "source_requirement": "R19",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "正式 README/prereg/task specs/split/stat endpoints 无该断言；M0R_A5_REQUIREMENTS_MAP 仅在 R19 requirement 原文引用该禁句，非科学声明。"
    },
    {
      "id": "MRC-41",
      "category": "evidence_text",
      "severity": "INFO",
      "requirement": "记录 A1 F-M0-02 事实更正：40fd=543x472/227,247B；199,997B/483x418 是 P1-05 58f63bfc。",
      "expected": "披露/引用",
      "source_requirement": "R20",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-42",
      "category": "consistency",
      "severity": "CRITICAL",
      "requirement": "q/L_ref/Sref 三重一致：q 由 deck 实际注入；L_ref=q*SREF_REF*CL；Sref(x) 逐设计；D_i=q*Sref(x)*CDi。",
      "expected": "A5 独立复算 rel≤1e-12；无第二公式",
      "source_requirement": "R23",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-43",
      "category": "consistency",
      "severity": "HIGH",
      "requirement": "W01 交叉校验 rel≤1e-6；q/L_ref/Sref 无第二套硬编码。",
      "expected": "交叉检查/代码搜索",
      "source_requirement": "R23",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-44",
      "category": "fail_closed",
      "severity": "CRITICAL",
      "requirement": "任何 task/atmosphere/SREF/geometry/mass/q 校验失败必须 fail-closed；禁止回退 358.25/旧几何/ISO/旧 task/旧 token。",
      "expected": "负例测试；失败码；无 fallback",
      "source_requirement": "R26",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-45",
      "category": "validation",
      "severity": "CRITICAL",
      "requirement": "M0-R 包含 validation、zero-physical dry-run、6 deck、A5 复算、无 solver 证据；commit 不 push。",
      "expected": "validation/dry-run/证据/SUMS",
      "source_requirement": "R27",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-46",
      "category": "claims",
      "severity": "CRITICAL",
      "requirement": "不得宣称 winner/显著性/优化增益/跨族可比；fuel=null；外部物理 NOT_VALIDATED；单 seed 描述性；M3 任务级 n=2。",
      "expected": "prereg/回执措辞；无禁用词",
      "source_requirement": "R30",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-47",
      "category": "scientific",
      "severity": "HIGH",
      "requirement": "3 train/1 val/2 test 限制写入 prereg：单 val 不足稳健早停/模型选择；M2 固定 epoch 或 leave-one-train-out；不得据单 val 宣称泛化。",
      "expected": "prereg 文本",
      "source_requirement": "R30/科学限制",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "prereg 已写 3/1/2 split；单 val 不足以稳健早停/模型选择的限制须在 M1-A/M2 prereg 显式写入（本 gate 记条件）。"
    },
    {
      "id": "MRC-48",
      "category": "scientific",
      "severity": "HIGH",
      "requirement": "2 test 均 Mach 1.8：仅低马赫外推、无跨 Mach 测试；不得跨族/跨 Mach 泛化。",
      "expected": "prereg 文本",
      "source_requirement": "R30/科学限制",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-49",
      "category": "scientific",
      "severity": "HIGH",
      "requirement": "task-level 2 test tasks 只可描述性/配对区间；NO_EVIDENCE 可能；不得显著性/winner。",
      "expected": "prereg 文本",
      "source_requirement": "R30/科学限制",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-50",
      "category": "scientific",
      "severity": "HIGH",
      "requirement": "6 任务为 Mach×CL、无高度因子；质量为目标巡航质量、无燃油模型；fuel=null。",
      "expected": "prereg 文本",
      "source_requirement": "R30/科学限制",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-51",
      "category": "gate_input",
      "severity": "CRITICAL",
      "requirement": "A3 M0-R 包由 task-57 正式冻结；task-60 pre-draft 不得被当作正式包/不得冻结。",
      "expected": "commit/状态；pre-draft 标记",
      "source_requirement": "R01/R28",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-52",
      "category": "gate_input",
      "severity": "CRITICAL",
      "requirement": "A1 task-56 U1/U2 已交付且 6-task 零物理 dry-run 冻结；接口变更后 gate 作废重出。",
      "expected": "A1 commit/证据；接口 SHA",
      "source_requirement": "R02/R03/R27",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-53",
      "category": "gate_input",
      "severity": "CRITICAL",
      "requirement": "A5 requirements R01–R30 逐条映射到本 checklist/conditions；无遗漏。",
      "expected": "映射表 30/30",
      "source_requirement": "R01-R30",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-54",
      "category": "gate_input",
      "severity": "HIGH",
      "requirement": "L-31 与 requirements 引用/数字一致；有冲突即先报 Lead 修正，不带冲突签 gate。",
      "expected": "L-31 一致性记录",
      "source_requirement": "L-31",
      "status": "PASS_WITH_DISCLOSURE",
      "a5_evidence": "A5 先前 L-31 一致性核验为 CONSISTENT_NO_CONFLICT，另有 2 项非阻断 gap（L-31 JSON 未列 6 task ID、未显式 M1-A labels/SREF）；requirements md 已覆盖。"
    },
    {
      "id": "MRC-55",
      "category": "gate_input",
      "severity": "HIGH",
      "requirement": "旧 G-T0-ADMISSION-01 保持 M0_BLOCKED 历史；新 gate 不改变旧字节/结论。",
      "expected": "旧 commit 字节 diff=0",
      "source_requirement": "R28",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-56",
      "category": "process",
      "severity": "CRITICAL",
      "requirement": "A5 独立执行：不修补 M0-R 包、不改 A1/A3 字节、不启动 solver、不建 run dir/ledger；physical=0。",
      "expected": "A5 证据；spawn=[]",
      "source_requirement": "R18",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-57",
      "category": "process",
      "severity": "CRITICAL",
      "requirement": "gate 结果只可为 READY_FOR_M1A_ADMISSION 或 M0R_BLOCKED；不得写 admission signed/ready_for_real_meta_training=true。",
      "expected": "verdict/字段",
      "source_requirement": "R16/R18",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-58",
      "category": "process",
      "severity": "HIGH",
      "requirement": "M0-R gate PASS 不授权 M1；M1-A 需单独 authorization/approval/GO；不得复用旧 token。",
      "expected": "边界字段",
      "source_requirement": "R29",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-59",
      "category": "evidence",
      "severity": "HIGH",
      "requirement": "gate 产物含 checklist/conditions/gate json/md/SUMS；A5 commit；不 push；旧证据不覆盖。",
      "expected": "文件/SHA/commit",
      "source_requirement": "R18/R27",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    },
    {
      "id": "MRC-60",
      "category": "accounting",
      "severity": "HIGH",
      "requirement": "预算/账本算术独立复算：M1-A 15=12+1+2、105=7×15；M1-B 66、462=7×66；M3-A 34、238=7×34；总 115、805=7×115。",
      "expected": "A5 算术；无 19/133 混写",
      "source_requirement": "R12-R15",
      "status": "PASS",
      "a5_evidence": "A5 独立实读/复算通过；证据见 gate bindings 与 disclosures。"
    }
  ],
  "counts": {
    "total": 60,
    "pass": 51,
    "pass_with_disclosure": 9,
    "fail": 0,
    "pending": 0,
    "blocked": 0
  },
  "conditions": {
    "total": 42,
    "r_conditions": 30,
    "g_conditions": 12
  },
  "boundary": [
    "本 gate 不是 M1-A execution authorization。",
    "不签 admission；ready_for_real_meta_training=false。",
    "M1-A 需新的 authorization/approval/A5 gate/Lead GO。",
    "M0-R 零物理；未见真实 VSPAERO 标签。",
    "fuel=null；physics NOT_VALIDATED；单 seed 描述性；无 winner/显著性/跨族。"
  ]
}
