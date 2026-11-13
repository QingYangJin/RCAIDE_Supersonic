# L-30 Lead 决策 — #11 M0 物理任务族阻断与 M0-R 重冻路径

- decision_id: L-30
- 日期: 2026-11-13（本地 CST）
- 依据: A1 task-52 a1_m0_domain_review_20261113.md/.json（PHYSICAL_TASK_FAMILY_BLOCKED）；A3 task-51 M0 DRAFT（commit 1cee3e5）；A5 G-T0-READY-02（T0_CODE_READINESS_PASS，不构成 #11 admission）；Issue #11 原文
- 范围: Issue #11 D-META-REAL-001 M0（零物理）；不授权 M1 真实采集，不启动 solver
- 结论: 当前 T0-4/A3 M0 字节 **不可冻结**，M0 = **M0_BLOCKED**；启动 **M0-R** 最小重冻；不宣布 PHYSICAL_TASK_FAMILY 最终失败，但拒绝在未接线、旧缺陷几何、L_ref 冲突、纯缩放副本上采集伪标签

## 1. 接受 A1 阻断结论

接受 A1 的 PHYSICAL_TASK_FAMILY_BLOCKED 作为当前字节的裁决，五项 BLOCKING 全部成立：

1. F-M0-01: evaluator_v12.py:718 无 task/Mach/alt/CL 入参；openvsp_model.py:343 prepare_case 无 altitude 参数，:374-377 固定 Vinf/Rho/ReCref 为 18,288m/M2.02 常数；Mach/alt/CL 只是字段，未进入求解器/约束。
2. F-M0-02: 任务族 geometry 40fdd436 是 F1_FAIL_ON_PHYSICS 旧缺陷几何（旧 483x418 链），不是 post-fix 16da482a/225,414B/546x480；必须重绑。
3. F-M0-03: L_ref 锚点冲突（A1 冻结 L_ref=W=1,333,704.4 N；T0-4 L_ref=q*358.25*CL = 0.567–2.083 W，隐含质量 77.1–283.2 t，无质量/载荷模型）。
4. F-M0-04: 18 任务中 12 个是纯高度缩放副本（固定 Vinf/Rho/ReCref 下 CDi 不变，D_i 与 L_ref 只随 q 缩放），设计排序不变。
5. F-M0-05: max_refine_sweeps 自相矛盾（frozen_geometry=0、tasks=2、alpha_refine_deg=[]）；C2 用插值后 CL 构造性满足，不构成升力验证。

同时接受 F-M0-06..14 的高/中/低发现作为 M0-R 修正清单；其中 F-M0-11（P1-05 1.8/2.02/2.2 包络依据不存在）要求 T0-4/A3 文本更正，不得再引用不存在的 A5 结论。

## 2. L_ref 裁定：方案 B（目标升力/任务质量模型），不做 A

采用 **方案 B**：把“目标升力/任务质量”声明为任务因素，并给出可核的质量模型；不采用 A（固定 L_ref=W）导致的任务退化（仅 Mach×alt，高度主要是缩放）。

- 冻结海拔: **18,288 m**（唯一已有真实执行先例的高度；15/20 km 从未真实运行，本轮不使用）。
- 任务因素: Mach × 目标 CL；每个任务预注册 CL_target ∈ {0.17, 0.19}。
- 每任务参考升力: L_ref_task = q(M, 18,288 m) × SREF_REF × CL_target。q 必须由该任务实际注入的 Vinf/Rho 复算（0.5*rho*Vinf^2，rel≤1e-12），不得任务端另算一套。
- SREF_REF 必须由 post-fix baseline 几何在运行时重算（当前 358.25000000000006 m²），SHA 绑定；不得在代码中硬编码 358.25。
- 质量模型: m_task = L_ref_task / g0（g0=9.80665）。显式声明为“任务目标巡航质量”，限定 **100–190 t**（低于 Concorde 约 185 t MTOW 的上界；所有选中任务 101.01–168.65 t）。质量仅由 L_ref 派生，不引入额外航程/载荷模型；任务不声明燃油。fuel_burn_kg=null。
- 评价仍用逐设计 Sref(x): CL_required(x)=L_ref_task/(q*Sref(x))，D_i_N=q*Sref(x)*CDi；Sref(x) 由该次构建几何重算，W01 交叉校验 rel≤1e-6。
- 若某任务 L_ref 对应质量超出 [100,190] t，或 q/Sref/SHA 校验失败，fail-closed，不得回退到 358.25。

## 3. 任务族（6 个候选，M0-R 重生成新 ID/SHA）

| 任务（临时 ID） | Mach | 高度 m | CL_target | q Pa | L_ref N | 目标质量 t | split |
|---|---:|---:|---:|---:|---:|---:|---|
| T18K_M202_CL017 | 2.02 | 18,288 | 0.17 | 20,483.940233 | 1,247,538.668 | 127.21 | meta_train |
| T18K_M202_CL019 | 2.02 | 18,288 | 0.19 | 20,483.940233 | 1,394,307.924 | 142.18 | meta_train |
| T18K_M220_CL017 | 2.2 | 18,288 | 0.17 | 24,297.496 | 1,479,778.246 | 150.90 | meta_train |
| T18K_M220_CL019 | 2.2 | 18,288 | 0.19 | 24,297.496 | 1,653,869.804 | 168.65 | meta_val |
| T18K_M180_CL017 | 1.8 | 18,288 | 0.17 | 16,265.266 | 990,595.355 | 101.01 | meta_test（盲） |
| T18K_M180_CL019 | 1.8 | 18,288 | 0.19 | 16,265.266 | 1,107,135.985 | 112.90 | meta_test（盲） |

- 切分 **3 train / 1 val / 2 test**，按 task_id 身份隔离；M1 只用 4 个 train+val 任务采集标签；M3 只用 2 个 meta_test 任务，且 meta_test 在 M1/M2 期间不得运行 solver、不得揭盲。
- 选择理由: 只保留唯一已验证高度 18,288 m；Mach 2.02 已有 F1R2/F2R2 真实执行先例，Mach 2.2/1.8 为目标域扩展；质量 101–169 t 均在合理巡航质量带；测试集留出整个 Mach 1.8（低马赫外推），训练含 2.02/2.2，避免“同 Mach/CL 仅换高度”的纯缩放副本。
- 同一设计跨任务必须复用同一 vspgeom 字节（build once，per-task 只生成 .vspaero deck）；每任务记录 vspgeom/polar SHA。
- 12D_ALL_ACTIVE 保持；10D_ACTIVE_PLUS_2_INACTIVE = DEFERRED_TO_M1；不得在 M0 声明 V01/V02 无效。

## 4. M0-R 最小修复（零物理，必须全做完才可重签 gate）

1. U1 几何重绑: post-fix openvsp_geometry d20ee7ad、baseline vspgeom 16da482a/225,414B、546x480、F1R2 12D audit 7a90b977；删除 40fdd436 作为 task family geometry；零物理复建 2/2 字节一致。
2. U2 task-capable executor: 逐任务注入 Vinf/Rho/ReCref/q（由 Mach+18,288m ISA 计算，q 与 .vspaero deck 一致）、per-task .vspaero、CL_required=L_ref/(q*Sref(x))、7 点 alpha 求根/线性插值、升力残差与插值不确定性分别记录；记录 attempt/exit/stdout/stderr/polar SHA；零物理 dry-run 生成 6 个 task deck，不启 solver。
3. U3 L_ref/质量模型: 按本决策 B；LREF-1..8 fail-closed；任务端不得构造第二套 q/L_ref。
4. U4 去冗余: 只保留本决策 6 任务；删除 12 个高度缩放副本；新 family SHA，不沿用 ada424cc。
5. U5 设计空间: 同时绑 raw YAML 8B29D1E3 与 C01–C04 交叉约束；M1 sampler/executor 强制 check_cross_constraints。
6. U6 q/L_ref/面积一致性: 统一 q 源为 solver 实际注入；Sref(x) 逐设计；A5 独立复算 rel≤1e-12。
7. U7 alpha/升力: 冻结 7 点 alpha、max_refine=0 或明确 refine 列表；C2 必须报告真实插值不确定性，不得只报构造残差 0；低 CL 若插值估计 >1e-3，必须预注册加密或 A5 预签放宽。
8. U8 mask: 12D_ALL_ACTIVE + 10D DEFERRED；更正 A3 “no zero-effect evidence” 文本。
9. U9 MIN_EFFECT_REL: 预注册 >0 阈值（建议 max(2×U_within,1e-3)）；不得用 0.0。
10. U10 重冻结: 新 M0 合同/prereg/split/预算/统计端点/A5 review items；admission=DEFERRED_TO_M1A_WITH_PRE_REGISTERED_CHECKS；任何真实 M1 仍需新 authorization/approval/A5 gate/Lead GO，禁止复用 R10/F1R2 token。

## 5. M1 分期与预算（每期独立 authorization/approval/GO）

### M1-A 任务族准入 pilot（物理，必须执行）

- 授权: 新 **D-META-M1A-001**，run **DREAL001-M1A-20261113-01**，新 window/token（待 M0-R 通过后由 Lead 另立）；不复用 #9/#10 token。
- 设计: 只对 4 个 M1 任务（3 train+1 val）各跑 **3 个冻结参考设计**（B0-01 + 2 个 12D 扰动设计，具体由 A1 冻结；同一设计跨任务复用 vspgeom 字节）；meta_test 任务不运行。
- 规模: 4×3=12 starts；加 1 个重复条件=1 start；加 2 个 preflight=2 starts；合计 **15 starts/105 internal**；caps **18/126**；retry 0；solver 90 s/start、case 180 s、wall 1800 s；串行、ncpu1/omp1。
- 准入门槛（必须全部满足）:
  - 每任务每设计 7 行 polar 全有限且 SOLVED；|L-L_ref|/L_ref≤1e-4；alpha* 在 7 点网格内；记录插值不确定性。
  - 跨任务可分性: 用 3 个设计的主指标 D_i 计算 CTX-A/B；至少 **4/4 任务** 两两归一化响应差 ≥max(2×U_within,1e-3) 或 Spearman<0.99；CTX-C 可行域/alpha* 差异须披露。
  - CTX-A 纯缩放: 若 max(r)/min(r)≤1+1e-3 且 Spearman=1 → TOO_SIMILAR，该任务对不得作为独立任务。
  - 任一任务不满足 solver/升力/可分性 → **PHYSICAL_TASK_FAMILY_BLOCKED**，停止，不进入 M1-B；不后验替换任务。
- M1-A 通过后由 A5 签 M1-A verdict；不自动授权 M1-B。

### M1-B 真实标签采集（物理，单独授权 D-META-M1B-001）

- 4 个 M1 任务 ×16 designs（8 support + 8 query，DETERMINISTIC_HALTON_12D，seed=task_fingerprint[:8]，outcome_dependent_selection=false）=64 labels；+2 preflight=**66 starts/462 internal**；caps **70/490**；retry 0。
- 每设计记录 EvaluationRecord: task_id/x12/active_mask/source_kind/objective_Di_N/alpha*/Sref(x)/L_ref/q/raw_sha/geometry_sha/solver_version/starts/internal=7×starts/status；失败 objective=null；真实/合成隔离。
- 五口径账本 charged/actual 分列；A5 签 REAL_MULTITASK_DATA_PASS。

### M3-A 严格留出（物理，单独授权 D-META-M3-001）

- 2 个 meta_test 任务 ×16 designs=32 labels；+2 preflight=**34 starts/238 internal**；caps **38/266**；retry 0。
- meta_test 任务在 M1/M2 期间不得运行 solver；M3 开始才揭盲；不用于任务选择/调参。
- 比较 Random/Sobol-BO、Pretrain-Kshot-BO、FOMAML-Kshot-BO，等 starts 预算；任务级 n=2，只做描述性/配对区间，明确 NO_EVIDENCE 可能；不得宣称显著性/winner/跨族平均。
- 允许 SUPPORTED_GAIN / NO_EVIDENCE / NEGATIVE_TRANSFER。

### 总预算（三批合计）

- planned **115 starts/805 internal**（15/105 + 66/462 + 34/238）；hard **126 starts/882 internal**（18/126 + 70/490 + 38/266）；labels 96；preflight 6；retry 0；M3-B（BO 扩展）不授权。
- 所有批次 solver 60–90 s/start、case ≤180 s、wall ≤1800 s、串行；超时/失败按失败分类记账，不 retry；INFRA 硬停。

## 6. 角色与顺序

- A1: U1/U2 实现与零物理 dry-run；提供 task-capable executor 冻结 SHA；负责几何/升力/跨任务标签一致性。
- A3: M0-R 合同包（新 family/split/预算/CTX/泄漏审计/A5 items/prereg），不得复用旧 18 任务字节。
- A2: M1-A/M1-B runner 与真实标签采集包（在 A1/A3 接口冻结后）；五口径账本；失败分类；不自行放宽阈值。
- A4: M2/M3 证据基础设施、checkpoint/replay、中文图；M1 数据后填数。
- A5: 先独立裁决 A1 阻断与 L-30；M0-R gate（G-T0-ADMISSION-01 或新 ID）；M1-A/M1-B/M2/M3 各自 gate；不得把 T0_CODE_READINESS 当 #11 授权。
- Lead: 唯一签署/GO/发布；M0-R 通过后先发 M1-A 有限 pilot，不直接进大采集。

## 7. 边界

- 本决策不构成 authorization/approval/GO；M0-R 零物理；M1-A 之前不得启动任何 solver。
- 不继承 #9 R10 token/approval；不继承 #10 F1R2/F2R2 approval；每批新 authorization_id/run_id/approval.json/case matrix/caps/超时/资源阈值/A5 预审/Lead GO。
- fuel_burn_kg=null；外部物理 NOT_VALIDATED；不得宣称优化增益/winner/显著性/跨族可比。
- 本决策不改变 #10 已发布报告与 R1–R10/F1/F1R2/F2R2 历史字节。

## 8. 立即动作

1. A5 独立复核 A1 阻断与本 L-30，给出 M0_BLOCKED/M0-R 要求；在 M0-R 前不签 admission。
2. A1 完成 review commit/SHA，提交 U1/U2 接口与零物理 dry-run 证据。
3. A3 在 A1 U1/U2 接口冻结后重做 M0-R 包；新 family SHA、新 split、新预算。
4. A2 在 M0-R 包冻结后出 M1-A pilot 包；A5 预审；Lead 签 M1-A authorization/approval/GO。
5. 以上全部完成前，M1/M2/M3 不启动，不发布 #11 结论。
