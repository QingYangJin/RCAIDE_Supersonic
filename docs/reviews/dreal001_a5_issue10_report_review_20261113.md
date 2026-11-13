# Issue #10 阶段汇报 A5 独立复核与签署

- review_id: A5-ISSUE10-STAGE-REPORT-REVIEW-20261113
- 复核对象: D:/RCAIDE/dnext001/wt-real-lead/docs/receipts/dreal001/issue10_stage_report_20261113.md
- report SHA256: ff43d5a979ba237a1a18116250060684d65a7af5e3e90bf402eb5de182cbd6a8
- report bytes: 19,200 B（UTF-8，109 行）
- reviewer: a5-review（独立复核与签署负责人）
- issued_at_utc: 2026-11-13T04:50:05Z
- verdict: **ISSUE10_STAGE_REPORT_REVIEW_PASS_WITH_MINOR_CORRECTIONS_REQUIRED**
- signature_status: **A5_SIGNED_SUBJECT_TO_LISTED_CORRECTIONS**
- publication: **PUBLISH_AFTER_APPLYING_C-01..C-07**
- A5 physical_call_count: **0**

## 1. 结论

A5 已对报告的事实基础、关键数字、commit/SHA、预算双口径、三层结论与授权边界逐项独立核对。**核心结论正确，未发现执行、训练、物理或 #11 的越权授权，也未发现会改变阶段结论的重大事实错误。**

报告发布前须落实下列 7 项修正/补披露（C-01..C-07）：

1. L41 F1R2 SUMS 的字节数与条目数单位写错；
2. L64 T0-2 的 22 tests 已过时（当前合同测试文件 31 passed）；
3. L74 F1 重复性容差把“且/更差 FAIL”写成了“或”；
4. L75 F2 科学停阈值边界写成“=25%”，实际是“>25% 或 numerator>=5”；
5. L44 U_wake=0 缺“本配置无可测效应、机制未证、不得称尾迹不敏感”的限定；
6. L11/L57 F2R2 的 E3 未披露 G1 预计算/objective 未用于生成/E3 仅执行链闭环，易被读成自适应优化；
7. L59 把 RA-01..06 都写成未来运行前置，实际仅 RA-01、RA-03 为 blocking_future=true。

上述修正均属表述精度/披露完整性，**不改变报告的三层结论**：SOLVER_LOOP_VERIFIED=PASS_WITH_DISCLOSURE；INTERNAL_AERO_OPTIMIZATION_GAIN=NOT_EVALUATED_NO_EVIDENCE；EXTERNAL_PHYSICS_SUPPORTED=NOT_VALIDATED。

## 2. 核验结果

| 项 | 报告主张/数字 | A5 独立核验 | 结果 |
|---|---|---|---|
| 报告身份 | SHA ff43d5a9…/19,200 B | 独立 Get-FileHash 与 bytes 全等；109 行 | PASS |
| F0 远端基线 | 4504bb75；182=181A+1M+0D；5,814,948 B；index 185/5,772,366 B | 远端 commit/tree 与 A5 F0 审计一致；5,772,366−20,291+62,873=5,814,948 算术成立 | PASS |
| F0 raw/restore | 2,228 files/207,718,755 B；SUMS 7d55b016/289,482；restore 0 mismatch | 与 A5 F0 审计及 restore 记录一致；3.33s/总 5.95s | PASS |
| F1 旧批 | 22/22 SOLVED、22 starts/154 internal；F1_FAIL_ON_PHYSICS | 与 F1 旧批执行和 A5 F1 审计一致；旧批 22 starts 计入实际账 | PASS |
| F1R-01 | 1 start/7 internal；run dir 36 files/2,830,261 B | 与 A5 F1R-01 失败审计一致；该批仅失败证据 | PASS |
| F1R2 门禁/执行 | approval 67a2d062、C-02 7e2c4be、GO a84242a0；22/154；caps 28/196 | 与 A5 F1R2 审计/回执一致；22/22 SOLVED、0 INFRA/0 retry、stop=null | PASS |
| F1R2 expected/重复性 | 8f4c9f81…/7,933 B；Group A 4/4；单构建状态披露 | 与 F1R2 run 证据一致；P1/P2/M0 字节链完整；单状态披露准确 | PASS |
| F1R2 不确定度 | U_iter 7.052110714290113e-08；2U 1.41042e-7；U_mesh NOT_COMPUTABLE | 数值与 A5 F1R2 审计一致；但 U_wake=0 缺机制限定，见 C-05 | PASS_WITH_CORRECTION |
| F2R-01 | 2/14 actual、7/49 charged；main solver 0；INFRA_ZERO_PHYSICAL_MAIN | 与 F2R-01 事故审计一致；5 例 ORIENTATION_INVALID 中止，main 未求解 | PASS |
| F2R2 门禁/执行 | 18/126；18/18/18；14 valid；16 SOLVED_VALID+2 SOLVER_FAILED；0 INFRA/retry | 与 F2R2 run_result/ledger/attempts 及 A5 审计一致；执行 75.528s | PASS |
| F2R2 失败/预注册 | DE-G1-02、RE-06-G1 SOLVER_NONCONVERGED；2/16=12.5% 未触发科学停 | 与 solver_attempts/polar 证据一致；失败计费、目标 null | PASS |
| P-01 协议偏差 | 实际 18/126 vs counterfactual 17/119；无新增有效观测；禁止 19/133 | 与 A5 F2R2 审计、A2 skip_logic 增补一致；但 RA 范围表述过宽，见 C-07 | PASS_WITH_CORRECTION |
| T0-1 | task_spec d7267738/81,219；T0-1 合同 fb85c9cd/167,540；family ada424cc；split 11/4/3 | 与 A3 task-48 交付及 A5 独立读一致；18/18 applicability=DEFERRED | PASS |
| T0-2 | meta_dataset da385389；泄漏 7/7 PASS；sealed fixture 32；22 tests | 文件/合同/隔离事实正确；但当前合同测试为 31 passed，22 已过时，见 C-02 | PASS_WITH_CORRECTION |
| T0-3 | A2 660071da；29 passed；smoke 18/18；K=0/1/3/5；BO evals 8；physical 0 | 与 A2 T0-3 证据及 A5 独立 pytest 一致 | PASS |
| T0-4 | A3 5832017；18 任务；admission PENDING_M0_BY_DESIGN；M1/M3/full pilot 预算 | 与 T0-4 六文件及 A5 独立读一致；DRAFT_PENDING_M0_GO、not_authorization | PASS |
| C32 | 9a9e294；production.py 21d3e807/27,663；20 tests/21 scenarios/16 REFUSED | 与 A5 独立 pytest（20 passed）及直接缺 provider probe 一致；入口 fail-closed | PASS |
| G-T0-READY-02 | commit 318c5ac；51 checks；112 tests；ready_for_real_meta_training=false | 与 A5 gate JSON/checklist 一致；51=42+8+1+0+0，C32 PASS/C36 N/A/C51 PASS | PASS |
| 累计预算 | actual 65/455；charged 70/490 | 22+22+1+2+18=65 starts；154+154+7+14+126=455 internal；charged 70/490 均复算成立 | PASS |
| 三层结论/物理边界 | 三层分离；fuel null；物理 NOT_VALIDATED；无 winner/显著性 | 与 A5 已签 F1/F1R2/F2R2/T0 审计口径一致；无跨族 pooled/无增益宣称 | PASS |
| 授权边界 | 不启动 #11、不授权 F2R3、不授权真实训练/物理 | 报告 L69/L88 等明确 ready_for_real_meta_training=false；未发现越权 | PASS |

**核验汇总：核心事实 21 项已核，0 项 FAIL；需按 §3 落实 7 项修正/补披露（C-01..C-07）。** 其中 C-05/C-06/C-07 是披露/范围精确化，不是核心数字错误；C-01..C-04 是单位、测试数或阈值表述错误。

## 3. 必须修正/补披露（逐条）

### C-01 L41：SUMS 单位错误（MINOR_FACTUAL_UNIT）

- 原文：A1 closeout 58ffe4d（SUMS 8a25b2d9/67,752 条 652/652 匹配）。
- 改为：A1 closeout 58ffe4d（SUMS 8a25b2d9…/67,752 B；652/652 条匹配）。
- 理由：67,752 是 SHA256SUMS 文件字节数，652 是条目数；原文把字节写成“条”，与 L68/其他 SUMS 写法不一致。

### C-02 L64：T0-2 测试数过时（STALE_TEST_COUNT）

- 原文：…；REAL_TRAINING_INGEST 默认 fail-closed；22 tests）。
- 改为：…；REAL_TRAINING_INGEST 默认 fail-closed；T0-1/T0-2 合同测试当前 31 passed（task-48 前 22；新增 9 项；A5 独立复跑））。
- 理由：当前 research/concorde_metaopt/tests/test_dreal001_t0_contracts.py 为 31 passed（A5 独立复跑）；L68 的 112=29+20+31+32 也使用 31。原 22 是 task-48 前数字，不能继续挂在 T0-2 单项后。

### C-03 L74：F1 重复性容差连接词/失败条件错误（TOLERANCE_LOGIC）

- 原文：否则 |ΔCDi|/|ΔCL|≤1e-9 或 rel+abs≤1e-3 仅披露。
- 改为：否则 |ΔCDi|≤1e-9 且 |ΔCL|≤1e-9 = PASS_WITH_DISCLOSURE；相对/绝对均≤1e-3 = PASS_WITH_DISCLOSURE；更差 FAIL。
- 理由：F1R2 预注册要求“且”而非“或”，且写明了更差 FAIL；原文的“rel+abs”也未明确两者均需满足，容易被误读为任一满足即可。

### C-04 L75：F2 科学停阈值边界错误（STOP_THRESHOLD）

- 原文：F2：预注册 invalid+failed/16=25%（≥5）自动停。
- 改为：F2：预注册 invalid+failed/16 >25% 或 numerator≥5 自动停；本批 2/16=12.5% 且 numerator=2<5，未触发。
- 理由：F2R_PLAN 的实际规则是 >25% 或 numerator>=5；若恰好 25% 不会触发。报告后文虽写“2/16=12.5% 未触发”，但规则句本身仍错误。

### C-05 L44：U_wake=0 缺机制限定（DISCLOSURE）

- 在 L44 的 U_rep/U_wake/U_iter 句后补：U_wake=0 仅表示 M1 NumWakeNodes 8→16 在本配置下 polar 字节同；机制未证，不得表述为尾迹不敏感。
- 理由：A5 F1R2 审计明确要求该限定；U_wake=0 是测量值，不是“尾迹不敏感”的证据。

### C-06 L11/L57：E3 闭环口径需补 G1 预计算披露（SCOPE_CLARITY）

- L11 的 F2 表项改为：…；真实 ask→build→VSPAERO→升力匹配→D_i_N→tell（G1 为 PRE_COMPUTED_DETERMINISTIC_AT_FREEZE，objective 未参与生成、无自适应选择；E3 仅执行链闭环）；无优化增益证据。
- L57 补一句：E2 为 7/7 PASS + 1 NOT_COMPUTABLE（RE-06-G1）。
- 理由：F2R2 的 G1 预计算、objective 未用于生成、reeval 不入 DE；若不披露，读者可能把“真实 ask→…→tell”误读为自适应优化闭环。

### C-07 L59：RA 范围过宽（OVERSTATEMENT）

- 原文：A5 要求后续同类运行前完成 RA-01..06。
- 改为：A5 要求 RA-01、RA-03 为未来 F2-like 运行前置；RA-02/04/05/06 为携带整改/记录项。
- 理由：A5 审计中仅 RA-01、RA-03 的 blocking_future=true；RA-02/04/05/06 为 false。原文把所有 RA 都写成未来运行前置，扩大了要求范围。

## 4. 可选精确化（不阻断发布）

- L53：6/16（37.5%）可写为“3 个设计×primary/reeval = 6/16 槽位（37.5%）”，避免被读成 16 个独立设计。
- L33：“两部件共面于原点”可改为“两部件 z≈0 共面”，更符合审计记录（不是精确原点）。
- L41：可在 run dir 653 文件后补 60,041,950 B，便于与 SUMS/字节口径对齐。

## 5. §8 建议写入文本（供 Lead 发布）

§8 A5 独立复核：A5 已对报告 SHA ff43d5a9…/19,200 B 逐项核对。核心数字、commit/SHA、预算双口径（actual 65/455、charged 70/490）、三层结论、fuel null 与物理 NOT_VALIDATED 边界均与 A5 已签审计/回执一致；未发现越权授权。发布前须按 A5 review C-01..C-07 修正 L41 单位、L64 测试数、L74 容差、L75 科学停边界，并补 U_wake 机制、E3 G1 预计算、RA 范围披露；修正不改变结论。A5 physical_call_count=0。

## 6. 签署与边界

- A5 签署范围：报告事实基础、关键数字/commit/SHA、预算双口径、三层结论与授权边界；**以 C-01..C-07 的修正/补披露为发布条件**。
- 本复核不是执行、训练、物理、Issue #11、G-T0-ADMISSION-01 或任何真实批次的授权；不启动 solver、不建 run dir、不写 ledger。
- 未修改 Lead 报告字节；报告字节以 ff43d5a9…/19,200 B 为准。
- A5 physical_call_count=0；本复核仅新增 docs/reviews 两文件。

**A5 结论：PASS_WITH_MINOR_CORRECTIONS_REQUIRED；修正后建议发布。**
