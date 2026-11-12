# D-REAL-001 Lead 决策记录 L-07：终止 R 线（R6 为最终执行尝试，不启动 R7）

- 决策编号：L-07
- 决策时间（UTC）：2026-11-11T11:32:00Z
- 决策人：Lead（team lead）
- 适用批次：DREAL001-P2-20261111-11 / run DREAL001-P2A2R6-20261111-01（其后无新批次）
- 状态：FINAL（不可撤销）

## 1. 决策

终止 D-REAL-001 P2a 六臂 pilot 的 R 线执行：**R6 为最后一个执行批次，不启动 R7，不再发生任何真实 solver 调用**。R6 定性为 **main-stage S1 STOP**（非 setup 中止）；其 preflight 2/2 PASS_BYTE 事实保留；R6 永久排除出 E1–E6 端点。后续以 A5 独立审计 + A5 签署的中文最终回执收束并发布 Issue #9。

## 2. 依据

1. **签署件约束**：R6 已签 approval（SHA256 72b95e03130fbe958c52528f1b8f484eae4872140a7336709094b9108964f98f / 67,063 B）与 Lead GO（c1afbc9daf0dfc6438941c08a234c9921a8734d0041db9741b5e01ed073b17ce / 5,671 B，token LEAD_GO_P2AV2R6_EXEC_20261111T111942Z）均明文约定 R6 为最后执行尝试、无 R7、main 再失败即终止。Lead 不得事后放宽已签条件。
2. **main 阶段失败、非环境毛刺**：R6 于 11:21:26Z 启动；preflight PRE-01/PRE-02 均真实 spawn 且 polar 逐字节匹配 expected（455082e2…/0287afe0…，各 7,933 B）；main 唯一案 BO-d51866f7d3c49303-f1 start 11:21:47Z / end 11:21:48Z，status=LIFT_MATCH_FAILED、objective=null；随后 on_evaluation→ProposalEngine.observe 抛 ValueError: x12 must have exactly 12 values，executor 走 arm 异常路径停批。
3. **结构性缺陷**：崩溃根因为执行器冻结代码 7 处把返回字符串的 canonical_x12() 再传入要求 12 维序列的 design_hash()（p2a_v2_executor.py:752/773/777/780/783/793/798；runtime.py:66-68 len(x12)!=12 断言）。R1–R5 因各自更早的门禁/环境问题从未让 main 评估完成回调，缺陷从未被触发；R6 首次触发即崩溃。修复属真实代码改动，叠加 LIFT_MATCH_FAILED 科学口径未诊断，在最后窗口内追加新包/新签/新门禁链不符合自动科学门禁与“最后尝试”承诺。
4. **A5 独立意见**：A5 在 R5 setup 中止阶段已书面建议终止 R 线（选项 A）；Lead 当时为争取 main 数据否决并授权 R6（A5 异议已记录于 FAIL-05 §10 与 R6 gate/GO 披露）。R6 main 失败后，Lead 接受 A5 建议，R6 按“最后尝试失败即终止”执行。

## 3. 记账（权威口径以 A5 独立复核为准）

- 本轮真实 solver starts：3（preflight 2 + main 1）；internal solver cases：21（2×7 + 1×7）。
- R1–R4 各 2 starts/14 internal；R5 0/0；R6 前累计 47 starts / 341 internal。
- 累计（R6 后）：**50 starts / 362 internal**，caps 451/3157，未超限。
- R1–R5 全部排除出 E1–E6；R6 亦排除。E1–E6 无有效数据，P2a pilot 结论 NOT_RUN / NOT_COMPUTABLE。
- physical_validation_status = NOT_VALIDATED；fuel_burn_kg = null。
- 三层结论边界：preflight 回放链路（真实 spawn + polar 逐字节匹配）在 R3/R4/R6 多次成立；main 求解/优化循环未完成一次有效评估 → 不得整体宣称 SOLVER_LOOP_VERIFIED；INTERNAL_AERO_OPTIMIZATION_GAIN 未观测；EXTERNAL_PHYSICS_SUPPORTED 未验证。

## 4. 伴随更正

- A2 早期报告的“累计 43 starts/313 internal”为旧口径，作废；以 47/341（R6 前）与 50/362（R6 后）为准。
- A2 早期报告称崩溃 traceback 见 executor_run.log；实查该日志仅有 REFUSED_OR_ERROR 一行，无 traceback；stop_report.traceback 为 "NoneType: None"。根因结论由代码路径 + A2 零物理复现证据支持，不以该日志 traceback 为依据。该事实须在 A5 FAIL-06 中如实记录。

## 5. 证据与后续

- R6 run dir：D:\RCAIDE\dnext001\wt-real-a2-optimizers\research\concorde_metaopt\dreal001\runs\DREAL001-P2A2R6-20261111-01（8 包 + approval + 签后 dry-run + prestart + log + stop_report + solver_attempts + preflight/ + runtime/ + arms/，全部只读保留，字节不改）。
- R6 关键 SHA：approval 72b95e03/67,063 B；dry-run 5f61343f/13,668 B；stop_report e74d7e2db802b6d81446d93727c3823565544c8264bb737f0e68379285240def/765 B；executor_prestart 9ca155d234654ea1a64e146246cc6e6d6d8f01c163a6db867557daa9cdeae29f/10,284 B；executor_run.log f569ebb26879bea0294307b488be6a5546fe70bafbd790f3182ee9a14a36bfb1/1,374 B；solver_attempts.jsonl c214cfa5677274368fb2b5cba6cd19e4413432778aa618e62575b5b4e9eccb2b/2,174 B；main 案 polar 58b8438df1225b07b3ef8dc327670575d99a6866b204f2c0840de074324d489a/7,933 B。
- 本次决策后：A2 仅做 append-only 证据固化与事故说明；A5 做 FAIL-06 独立审计并交付签署的中文 Issue #9 最终回执；Lead 原文发布 Issue #9。**任何后续执行（含 R7 或修复后重跑）必须重新走完整预注册/审批/A5 门禁链，且需新的 Lead 决策，本记录不构成任何执行授权。**

## 6. 签署

- Lead：team lead
- 日期：2026-11-11（UTC 11:32Z）
- physical_call_count_at_decision：50（累计）；本决策不新增任何真实调用。
