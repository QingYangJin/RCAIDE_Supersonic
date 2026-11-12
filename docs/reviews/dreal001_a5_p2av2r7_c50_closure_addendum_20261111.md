# A5 C50 闭合补遗 —— D-G1/G2/G3 独立验收（G-P2AV2R7-PRE）

- review_id: A5-P2AV2R7-C50；gate: G-P2AV2R7-PRE（commit 040dbd0ade0a24a124040b38dbb046da59b33ef7，json SHA256 AECA052BABE8FC7F679E4ED91BF20E080EE8FB9DE432243A6A8FC429E970FA87 / 63,739 B）
- 对象: A2 commit C **c3de1de3cc34cf5f12da372f47eabf823a1b0cdc**（parent 893cf456cc2c8daf522d3c29debc60b9a20209fa，5 files +2,102/−1,277）
- 审查者: a5-review（独立）；时间: 2026-11-11T15:34:36Z；A5 physical_call_count=0，solver_started=false
- **结论: C50 从 PASS_PENDING → PASS（closure accepted）；不重发 gate；a5_review 仍用 040dbd0ade0a24a124040b38dbb046da59b33ef7；本补遗不改变 gate 的 52 conditions，也不改变 gate 的科学结论口径。**

## 1. 结论摘要

| 项 | 结论 |
|---|---|
| D-G1 面积解析错误 | **CLOSED**：根因（仅 quad 求和）已定位并修复为全 face Newell 求和；8/8 可对照几何与 A5 独立 Newell+fan 值一致，\|Δ\| ≤ 4.4e-7 m²（判据 < 1e-6）；节点/面元数 8/8 与 A1 canonical 一致 |
| D-G2 严格 JSON | **CLOSED**：两份 JSON 严格解析通过、无 NaN/Infinity 字面量；与修正前旧 JSON 的 99（data）/20（geom）个共同叶子值逐值相同（0 变化）；非有限值→null 且原始 token 保留 |
| D-G3 定义/容差/入口/复现 | **CLOSED**：算法、容差、实现入口（`analyze()`）、复现命令、A1 canonical 交叉核对、判别力披露全部就位；明确"不作数据门"，符合 L-09 |
| C50 状态 | PASS_PENDING → **PASS**（依据 A2 commit C + 本补遗的独立验收） |

## 2. A2 commit C 字节与范围核验（A5 实算）

- commit c3de1de3cc34cf5f12da372f47eabf823a1b0cdc，parent 893cf456cc2c8daf522d3c29debc60b9a20209fa；`diff-tree` 显示恰好 5 个文件（下表）。每个文件 `git diff --exit-code <commit> -- <file>` = 0，且 `rev-parse <commit>:<file>` == `hash-object -- <file>`（disk 字节 == commit blob），5/5 一致。
- 范围核验：commit C **只改 docs/evidence/dreal001/**，不触及 8 包、launcher、executor/common/runtime/p2a_v2、A1 冻结树、plan/prereg/identity/approval.DRAFT —— 即 gate 的全部绑定字节未变，故 addendum 无需重发 gate。

| 文件 | bytes | SHA256 | 状态 |
|---|---|---|---|
| r7_dg_correction_20261111.md | 9,358 | bbdc46a43968bcc8c637bde88a697a3ce31a9f8c1d21c4536a692ecf11ef8ee1 | A (new) |
| r7_r6_nan_zero_physical_diagnosis_20261111.md | 16,547 | 8677cedcd1ba9ae5430e7fd41bd86f15ca4412a1a6466067d5101418aa135af3 | M |
| r7_nan_diagnosis_data_20261111T2142Z.json | 31,097 | 9a98f6feff227665b969eea9858259140f6d964be0a332ed3cd0cc82501a2ceb | M |
| r7_nan_diagnosis_geom_20261111T2148Z.json | 34,631 | 18f1f3446266a48abe9567967144efc6183b3422411a76b4a37e01f00672da77 | M |
| r7_nan_diag_fix_20261111.py | 19,917 | 253dc5a2d1a8fd04e3bf0ea206500a3afcba569153b0146cf5e3d7731af50d24 | A (new) |

- 被取代的旧版本（仍可从 git 历史取得，未重写历史）：旧 cc168063b8b1a65cffa12010bace5dd158a96c2ff4e6049682ad6cb23ac60dca / 35,775 → 新 9a98f6fe... / 31,097；旧 44f2d1fba443791e67fe690910a597bf21e6bbce6081ad0afeebc553f24feb4f / 16,446 → 新 18f1f344... / 34,631；旧 86fdbe6de96ac0bfbff39acc890b5356be5a4f3b071bd38fc2d609bc11a041e8 / 10,077 → 新 8677cedc... / 16,547。

## 3. D-G1 独立验收（严格 Newell + fan 双口径）

- 根因确认：旧 `r7_nan_diag_geom.py:face_data()` 先过滤 `quads=[f for f in faces if len(f)==4]`，仅对 quad 累计 Newell 面积；每个网格有 11–32 个非 quad 面元被整体漏掉，两族 non-quad 集合不同 → 同一 underlying 几何 f1/f2 面积差 8.9%（366.963 vs 336.964），A5 阶段 D 已指出该自相矛盾。
- 修复路径（已读源码确认，非仅信报告）：`r7_nan_diag_fix_20261111.py:271` `area_newell = sum(newell_area([nodes[i] for i in f]) for f in faces)` —— 对**所有** face 求和；`area_fan` 对**所有** face fan 三角化求和作交叉核对；quad-only 口径仅保留给 nonplanarity/sliver/self-intersection 等与 A5 阶段 D 对齐的缺陷指标。
- A5 独立对照（A5 阶段 D 自算值，commit b448c3e/1141cf4）：8/8 一致，\|Δ\| ≤ 4.4e-7 m²：d15 f1/f2 369.27137399178747 / 369.2713739917873；d16 f1/f2 411.12965729155036 / 411.1296572915505；d17 f1/f2 329.862062566815 / 329.8620625668152；PRE-01 367.08266642706883；PRE-02 379.08266641555787。d15/d16 两族完全相同、d17 差 5e-13（浮点级）。
- 节点/面元数：d15 462x401 / 546x472、d16 456x395 / 548x474、d17 481x416 / 539x468、PRE-01 543x472、PRE-02 483x418，**8/8 与 A1 canonical 一致**（含 `a1_canonical_cross_check.nodes_match/elements_match=true`）。
- 旧面积数字现状：不再作为任何活跃指标出现；仅保留在 geom JSON 顶层 `supersedes.D_G1` 的说明文字中（作为"已撤回错误值"的历史记录）——这是恰当做法，A2 §1 "旧 JSON 中全部错误面积数字已从发布文件中删除" 的措辞略宽（见 D-add-2），不影响 D-G1 闭合。

## 4. D-G2 独立验收（严格 JSON）

- 两份 JSON 均由 `strict_json()` 生成（`json.dumps(..., allow_nan=False)` + `sanitize()` 把非有限 float 转 null）：A5 用 Node `JSON.parse` 严格解析 **通过**，全文无 `NaN`/`Infinity` 字面量。
- 有限数值未改变：A5 导出 commit C 的父版本旧 JSON（容忍 NaN 字面量做等值清洗后解析），与新版逐叶子比较——data 99 个共同叶子、geom 20 个共同叶子，**0 个数值/结构变化**；仅新增 `supersedes`/`raw_nonfinite_tokens`/`metric_definitions` 等修正元数据。
- 原始 token 保留：`history.<case>.iterations[*].raw_nonfinite_tokens` 等字段保留 `"nan"`/`"-nan(ind)"` 原始字符串（A5 抽查 main 462x401 的 7 case 全命中）。

## 5. D-G3 独立验收（定义/容差/入口/复现/判别力）

- `geom.metric_definitions` 与修正记录 §3 均给出：area_total_m2（全 face Newell 求和，与 A5 canonical 判据 < 1e-6 m²）、area_fan_triangulation_m2（交叉核对，与 Newell 差 < 2e-3 m²）、nonplanarity（quad 面元、阈 1e-6 m）、self_intersection（全 face fan 三角化、跨面三角形对、SAT + segment/triangle、参数容差 1e-9）、sliver（fan 三角最小内角 < 1.0°，数值容差 1e-12）、z_extent；实现入口 `r7_nan_diag_fix_20261111.py:analyze()`；复现命令 `D:\RCAIDE\envs\RCAIDE\python.exe docs/evidence/dreal001/r7_nan_diag_fix_20261111.py`（cwd=A2 worktree，只读输入、零物理）。
- A5 复核：源码 `python compile()` 通过（Python 3.11.17，不落盘）；`tri_tri_intersect`/SAT 实现、`strict_json`、`main()` CLI 均已读码确认。A5 **未执行**该脚本（它会覆盖 A2 的两份证据文件，A5 不写 A2 树；见 D-add-3），改用独立解析器 + 旧/新 JSON 逐值对照 + 读码。
- 判别力披露符合 L-09：CAL-W10p-f483x418（真实 VSPAERO 3/3 成功）仍有 120 个非平面 quad（nonplanarity_max=0.0015789697 m）、101 个自交三角形对（> d15 的 75）；CAL-W05p 全 0；PRE 平坦网格 sliver 6/7 非零 → 指标与求解成败关系未被证明，**只作观察/披露，不设网格 QC 数据门**；表述保持"NaN 现象成立、设置差异可排除、候选机理 H1/H2/H3、机制未证明"。

## 6. seq7 文字不一致披露（D-add-1）

- gate.signature_requirements.seq7_semantics 写 "seq7 ... at 2026-11-11T14:35:00Z"，而 DRAFT/signed approval 的 amendment_log[6].at_utc 实值为 **2026-11-11T14:56:59Z**（action=R7_OBSERVE_AND_INVALID_TOLERANCE_FIX、physical_call_count_at_amendment=50，两者一致）。
- 口径：以 **DRAFT/签署件字节**为准；签署件 amendment_log 必须与 DRAFT 字节同一（M4 不变）；gate 中 14:35:00Z 为 gate 文本笔误，不参与任何绑定/校验，无实际影响；已在 C-P2AV2R7-02 与最终回执中继续记录。

## 7. C50 状态转换与签署口径

- gate 签发时（commit 040dbd0ade0a24a124040b38dbb046da59b33ef7）checks_summary = 52 PASS + 1 PASS_PENDING（C50）。签发时 A2 commit C 尚未提交，PASS_PENDING 是如实状态。
- 本补遗（独立 commit）以 A2 commit C 的字节 + A5 独立验收为准，将 C50 置为 **PASS**；C50 的闭合证据 = A2 commit C + 本补遗 commit。
- **不重发 gate**：commit C 未改任何 gate 绑定字节（见 §2）；重发只会改变 a5_review/gate commit 并制造链上歧义，对绑定与科学结论零收益（R6 先例 rev2 亦"记录不重签"）。
- 签署口径：Lead 按 M1 以 **a5_review=040dbd0ade0a24a124040b38dbb046da59b33ef7** 签署 approval.json；本补遗 commit 作为独立证据在 Lead 签署证据、C-P2AV2R7-02、最终 Issue #9 回执中引用。签署后 A2 单文件字节原样 commit → 用 `post_approval_dry_run_r7.py`（b2ba799b…/18,930 B）跑真实 dry-run → A5 C 门禁（硬线 16:10Z）→ Lead GO。

## 8. 残余与披露

- D-add-1：seq7 文字时间不一致（见 §6），以 DRAFT/签署件为准。
- D-add-2：A2 修正记录 "旧 JSON 中全部错误面积数字已从发布文件中删除" 措辞略宽——旧值仍以 `supersedes.D_G1` 说明文字保留（作为撤回记录），不是活跃指标；非阻断，建议后续证据文档表述精确化。
- D-add-3：A5 未执行 A2 复现脚本（会覆盖 A2 证据文件）；A5 以独立解析器 + 旧/新 JSON 逐值对照 + 读码 + compile 复核替代，结论等价。
- D-add-4：D-G 指标为观察/披露性质，不构成数据门，不改变 L-09 协议 D，也不影响 E1–E6 端点口径。
- D-add-5：A5 physical_call_count=0、solver_started=false；本补遗不构成任何执行授权。

## 9. A5 签署块

- verdict: **A5-P2AV2R7-C50-CLOSURE-DG1-DG2-DG3-PASS-NO-GATE-REISSUE-SEQ7-TEXT-DISCLOSED**
- 日期：2026-11-11T15:34:36Z；签署者：a5-review（独立复核）；physical_call_count=0；solver_started=false。
- 本补遗仅闭合 C50，不改变 gate 的 52 conditions、不改变 gate 科学结论、不构成执行授权。
