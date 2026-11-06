# P4 路线A S1 需求矩阵（v1.8）

> 文档性质：Issue #7 S1 的只读需求—证据—状态核对表；**不是验收结论，不是 S1_RUN 授权**。
> 当前位置：HEAD=commit M 51c570c（父 L 8f34e91；J 004156c/K 8118234/I 36619cf）；branch research/p4-route-a-s1；S0-7 确证冻结包（J 生成、K 入库）用于正式 run；S1 formal 21,000 已执行完成（run_id p4ra-s1-formal-20261106T0250Z；15 分片 + merge PASS；analysis 最终版 + v5b 确定性 PASS）；A5 终审 APPROVE_FOR_S1_RUN、A5 结果复核 APPROVE_FOR_S1_RESULT_RECEIPT；A3 终稿审计 PASS；A4 回执已由 Lead 发布（Issue #7 commentId 6684142041）；S1_RUN=EXECUTED_AND_RESULT_REVIEWED（Lead 签发，不含 S2 授权/阶段验收放行）；physical=0。
> 依据：Issue #7 §2 S1/S4、§3–§4；执行计划 v1.7；数据合同 v1.6；统计计划 v1.5；R-V4-01..11；A5 phase4b 报告（<EXT>/p4-route-a/a5/S1_phase4b_review.md，sha256 def5c059…）与 findings_phase4b.csv（sha256 ffb5dcf0…）；A5 phase4c 报告（<EXT>/p4-route-a/a5/S1_phase4c_review.md，sha256 db8e3106…）、findings_phase4c.csv（sha256 f66e2b9a…）、verdict_phase4c.txt（sha256 5fe0afc5…）；A2 readiness v4f（<EXT>/p4-route-a/a2/s1_prep_v4f/S1_formal_readiness.md，sha256 77db3e24…）；A3 v4f 审计（<EXT>/p4-route-a/a3/S1_v4f_isolation.md，sha256 ef694d55…）与 addenda（d1c597a9…、ae5cf638…）；Lead commit J 后全量测试日志 <EXT>/p4-route-a/lead/commitJ_full_tests.log（8,956 B，sha256 6f584635…；Ran 949 tests in 442.006s / OK (skipped=1)）。
> 读取时点：2026-11-06 20:05+08（Lead 同步 v1.8；正式 run 报告/最终 analysis/A5 final/A3 终稿/回执发布均已读取）。
> v1.6 变更：S0-7 替代 S0-6 成为唯一确证包；commit J/K；949 tests；A5 phase4b 1B/0M/4m 逐条映射；新增 §4.8/§4.9；phase4 M01/M02/M04 状态按 phase4b 实际更新；15 片窗口改为 A2 v4e B128 实测 2.58–3.01h（首片核对）；S1 状态改为 COMMITTED_PENDING_A5_PHASE4C；明确确证包 code_sha 绝对 fail-closed（FC-20）。
> v1.7 变更：同步 L、A2 readiness v4f（COMPLETE，7/7 gate）、A3 v4f（PASS 40/40 + addenda）、A5 phase4c（CHANGES_REQUESTED 0B/1M/2m，仅治理/文档项；待 final re-verdict）；m04 经 A3 addendum 登记后 CLOSED，m01 由文档同步关闭、m02 声明 final_verify 15/15 为包外证据（sha256 ecee6971…，不补写冻结包）；窗口按 A2 v4f 实测改为 2.55–2.97h；S1_RUN 仍 NOT_APPROVED。
> v1.8 变更：S1 formal 已执行（p4ra-s1-formal-20261106T0250Z，15×1,400=21,000；attempt1/2 外部终止 0 records 已归档披露，attempt3 成功）+ merge PASS + analysis 最终版 + v5b 确定性 PASS；A5 final re-verdict APPROVE_FOR_S1_RUN、A5 结果复核 APPROVE_FOR_S1_RESULT_RECEIPT、A3 终稿审计 PASS；Issue #7 S1 结果回执已发布（commentId 6684142041，正文 sha256 6985e3d2…）；S1_RUN=EXECUTED_AND_RESULT_REVIEWED；S1-07/S1-11/S1-12 → COMPLETE。
> 状态口径：PASS / PARTIAL / BLOCKED / NOT_RUN / IMPLEMENTED_PENDING_A5 / CLOSED_* / PENDING_*；未获 A5 final re-verdict 的项不得写 PASS；A4 文档对 m04 的 CLOSED 属文档映射，最终关闭权归 A5 final re-verdict。

## 1. 当前状态与硬边界

| 项 | 状态 | 说明 |
|---|---|---|
| S0-2 冻结包 | 历史只读 | 旧 8 payload；仅历史复现/负控 |
| S0-3 冻结包 | 历史只读 | 已被 S0-4/S0-5/S0-6 取代 |
| S0-4 冻结包 | SUPERSEDED_LEGACY | commit D ae013ed；旧确证包；只读 |
| S0-5 冻结包 | SUPERSEDED_LEGACY | commit F fe8bdc9；A5 phase4 审查对象；code_sha=25f726f8… 已漂移；只读 |
| S0-6 冻结包 | SUPERSEDED_LEGACY | commit H e95f9dc 入库；code_sha 1f244984…；被 S0-7 取代；只读 |
| S0-7 冻结包 | COMPLETE_GENERATED_AND_COMMITTED | commit J 生成、K 入库；9/9、determinism PASS；final_verify 15/15 为包外证据（sha256 ecee6971…，A5 phase4c m02）；唯一确证包 |
| A2 readiness v4f | COMPLETE | 7/7 gate；md 11,863 B sha256 77db3e24…；正式 21,000 已授权并执行完成（A2 正式报告 rev2 sha256 b26f1648…；attempt1/2 外部终止 0 records 已归档，attempt3 21,000 成功） |
| A3 v4f 审计 | PASS | S1_v4f_isolation.md sha256 ef694d55…（40/40）；addendum L sha d1c597a9…；m04 登记 addendum sha ae5cf638…（8/8 PASS）；S1 终稿证据审计（LEAD-ADHOC-ATT3-AUDIT-FINAL）PASS，S1_att3_evidence_audit_final.md sha256 175b2fc7…（W01–W11 仅披露/口径） |
| S1 实现 | COMPLETE | commit J 修复 S1R4b-B01；949 tests；A5 phase4c/final 复审通过（APPROVE_FOR_S1_RUN，0B/0M/3m）；S1 结果复核 APPROVE_FOR_S1_RESULT_RECEIPT（0B/0M/0m 新增） |
| A5 phase3 | CHANGES_REQUESTED 已修复 | 2B/2M/6m；实现层由 G 关闭，phase4/4b 复核 |
| A5 phase4 | CHANGES_REQUESTED（1B/4M/5m） | B01/M01 CLOSED_IN_J_PENDING_PHASE4C；M02 CLOSED；M03 CLOSED_IN_DOCS；M04 CLOSED_WITH_RESIDUAL |
| A5 phase4b | CHANGES_REQUESTED（1B/0M/4m）已关闭 | B01 CLOSED_IN_J_PENDING_PHASE4C；m01 CLOSED_BY_THIS_DOC；m02 CLOSED_BY_A1；m03 CLOSED_WITH_RESIDUAL；m04 CLOSED（A3 m04 登记 addendum sha ae5cf638…；A5 final 确认） |
| A5 phase4c | CLOSED（APPROVE_FOR_S1_RUN） | final re-verdict：0B/0M/3m（H05 文件清单漏列、授权指针旧 review、矩阵 m04 状态待 A4；均为披露/文档项）；J/K/S0-7 未变（SUMS 59aa81cd…、code_sha 7304d32e…）；949 tests 复用通过 |
| S1 formal run（21,000） | EXECUTED / MERGE PASS / RESULT REVIEWED | run_id p4ra-s1-formal-20261106T0250Z；15×1,400=21,000、billable 1,920,000、physical=0；attempt1/2 外部终止 0 records（已归档）；merge 21,000/21,000、missing/extra/dup=0；analysis aggregate sha256 02b24c44…、determinism PASS（41623140…）；不含阶段验收放行 |
| 真实 holdout | 未读指标 | TE 20 任务只在授权后一次性打开；A2 G05/A5 phase4b/phase4c e2e 对 TE-000/001 任务定义的受控读取已由 A3 m04 addendum 登记（各 8 records、0 物理、未读指标），正式分析须披露 |
| K-shot 闭环 | IMPLEMENTED_PENDING_A5_FINAL | 支持集进入内循环；K 计入 B；R-V4-10-03 e2e 待 phase4c 复核 |
| 15 分片/merge | COMPLETE | 15 片各 1,400，union 21,000 unique；merge PASS（problem_count=0、code_sha_match=true、evaluation_mode=confirmatory）；records 65,648,720 B sha d994d3c7…；actual 墙钟约 3.22 h/片（15 进程争用，Lead v5a 时限修订披露） |
| 物理调用 | 0 | 无 solver；无 RCAIDE Mission；无 VSPAERO |
| Issue #4 门禁 | GEO-12D=PARTIAL / LF-M2.02=NOT_VALIDATED / HF-M2.02=PARTIAL / BODY-CORR=BLOCKED / MISSION-DATA=PARTIAL / BUDGET=GATED | approved_for_next_stage=false |
| 旧证据/PR | 只读/open | PR #3/#6 保持 open，不合并 main；PR #7 未创建 |
| GitHub 写权限 | 仅 Lead | A4 不评论/不改 Issue/不发布 |

## 2. 冻结包演进

### 2.1 S0-2（历史只读）

旧 v3 包（p4ra-s0-2-freeze-20261105T072500Z）；8 payload；五 split 与 family v3；已被后续包取代，仅历史复现与负控。不得用于 S1 确证。

### 2.2 S0-3（历史只读）

v4 首版确证包（p4ra-s0-3-freeze-20261105T155925Z）；15 文件；8 payload 两进程一致；已被 S0-4/S0-5/S0-6 取代。

### 2.3 S0-4 / S0-5（SUPERSEDED_LEGACY）

- S0-4：p4ra-s0-4-freeze-<UTC>Z；commit D ae013ed；旧确证包；被 A5 phase4 发现 runner 仍接受 S0-4、code_sha 未绑定等问题。
- S0-5：p4ra-s0-5-freeze-20261105T215000Z；commit F fe8bdc9；9 payload；schema p4ra-freeze-summary-3；A5 phase4 审查对象；自身完整性 PASS（9/9、digest 7/7、identity 5/5、code_sha=25f726f8…），但因 B01/M01 未修复不能用于 S1。
- 两者在 freeze_summary/README 标 SUPERSEDED_LEGACY，只读。

### 2.4 S0-6（SUPERSEDED_LEGACY）

| 项 | 值 |
|---|---|
| run_id | p4ra-s0-6-freeze-20261106T003500Z |
| created | 2026-11-06T00:35:00Z |
| 生成 / 入库 | commit G 48403e5 干净 detached worktree；commit H e95f9dc 入库 |
| git_sha / code_sha | 48403e5d7a72a5c077e8f0c6c072c94628087fc3 / 1f244984ad0bddb09a820076a87caa5df2ca63fcd85f9f149aea3defc12fbd6d |
| 文件 | 9 payload + README.md（4,972 B）+ SHA256SUMS.txt（784 B）；sha256sum 9/9 |
| 不变量 | family_version p4ra-family-v4；family_id F-QE-feasible-v3；family_fingerprint a1f9462c…；split_hash cd597d01…；counts 60/20/20/10/10；holdout_seed 20261106；radius_base 0.64；prereg_digest 44d6ff80…；analysis_plan_digest 5222af0d…；confirmatory_eligible=true |
| 确定性 | 两独立进程 run1/run2；6 个内容载荷逐字节一致；determinism_report status=PASS、rerun_count=2、6/6 identical；final_verify sha e42df338… 15/15 PASS |
| 与 S0-5 关系 | 仅 run_id/git_sha/code_sha/时间戳/prereg holdout_package 元数据/calibration 文案可不同；tasks/split 逐字节相同 |
| 状态 | SUPERSEDED_LEGACY；因 commit J 改变 meta_learning/*.py 导致 code_sha 漂移，由 S0-7 取代；只读，不得用于确证 formal，也不得 --allow-code-delta 进入确证路径 |

### 2.5 S0-7（当前唯一确证包）

| 项 | 值 |
|---|---|
| run_id | p4ra-s0-7-freeze-20261106T024200Z |
| created | 2026-11-06T02:42:00Z |
| 生成 / 入库 | commit J 004156c 干净 detached worktree；commit K 8118234 入库 |
| git_sha / code_sha | 004156c232f31a450f7446c3b280772de47423df / 7304d32e524b0e1e28b0e83e7a2ed7822ce88fc14963ca4d769098841e6201ed |
| 文件 | 9 payload + README.md（sha256 936f94ac…）+ SHA256SUMS.txt（sha256 59aa81cd…）；sha256sum 9/9 |
| 不变量 | family_version p4ra-family-v4；family_id F-QE-feasible-v3；family_fingerprint a1f9462c…；split_hash cd597d01…；counts 60/20/20/10/10；holdout_seed 20261106；radius_base 0.64；prereg_digest 3155de15…；analysis_plan_digest 5222af0d…；confirmatory_eligible=true（三处）；physical_call_count=0 |
| 确定性 | 两独立进程 6 个内容载荷逐字节一致；determinism_report schema p4ra-s0-7-determinism-report-1、status=PASS、rerun_count=2、independent_processes=true；final_verify sha ecee6971… 15/15 PASS |
| 与 S0-6 关系 | 仅 run_id/git_sha/code_sha/时间戳/frozen+prereg 字节/determinism 证据不同；tasks.json（59f66a41…）与 meta_task_split.json（589f77e5…）逐字节相同；S0-6 标 SUPERSEDED_LEGACY |
| 状态 | COMPLETE_GENERATED_AND_COMMITTED；待 A2 readiness v4f/A3 审计/A5 phase4c/Lead 授权 |

## 3. S1 需求（S1-01..12）

| ID | 要求 | 实现/证据 | 状态 | 责任 |
|---|---|---|---|---|
| S1-01 | K-shot 支持集进入适应内循环并用适应后代理评分 | m5_arms.py 支持集参数与调用链；K∈{0,1,3,5}；K=0 兼容 | IMPLEMENTED_PENDING_A5_FINAL | A1 |
| S1-02 | 五臂（Random/Pretrain/FOMAML-Zero/FOMAML-Kshot/DE）与预算公平 | 40 组预算单测；billable=B；K 计入 B | TESTED_PENDING_A5_FINAL | A1/A2 |
| S1-03 | run_records.jsonl 字段/确定性/record_digest | 合同 §4；200×3 确定性测试；949 tests 基线 | TESTED_PENDING_A5_FINAL | A1 |
| S1-04 | 九端点、null 规则、聚合口径 | s1_analysis.py/s1_figures.py；端点表；null 不插值 | IMPLEMENTED_PENDING_A5_FINAL | A1 |
| S1-05 | C1–C4/C5-B、Wilcoxon/bootstrap/Holm 唯一族 | 统计计划 v1.5；Holm 族键 (endpoint,B,K)；C5 排除 | IMPLEMENTED_PENDING_A5_FINAL | A1/A2 |
| S1-06 | 七类中文图 | s1_figures.py；图题图注中文；数据来源标注 | IMPLEMENTED_PENDING_A5_FINAL | A1/A2 |
| S1-07 | 15 分片×1,400、merge、S1_RUN 门禁 | 正式执行 15×1,400=21,000；merge PASS（0 problems、union 21,000）；attempt1/2 外部终止 0 records 已归档披露；A5 phase4c/final 已复核 | COMPLETE | A1/A2/A5 |
| S1-08 | launcher 预检（S0-7 路径/SHA256SUMS/code_sha/HEAD/artifacts/TOP run_id/15 片/21,000） | commit G 实现；--dry-run；预检失败 exit≠0；须绑定 S0-7/K | IMPLEMENTED_PENDING_A5_FINAL | A1 |
| S1-09 | code_sha fail-closed 与 --allow-code-delta 仅 exploratory | commit J：确证包绝对 fail-closed（S1_FROZEN_CODE_SHA_DRIFT）；负控 S0-5/S0-6 四命令 DRIFT 无产物；正控 S0-2 双 sha | CLOSED_IN_J_PENDING_PHASE4C | A1 |
| S1-10 | 真实 runner→analysis e2e（串行与 merge） | R-V4-10-03；B64/K∈{0,3}/2 任务/2 臂/0 物理；G 修复 B01；phase4c e2e 8 records/merge PASS/analysis exit 0/C5 NOT_ESTIMABLE | PASSED_PHASE4C_PENDING_A5_FINAL | A1/A5 |
| S1-11 | 预注册/S0-7 冻结包与不变量 | S0-7；9/9；determinism PASS；final_verify 15/15（包外证据）；SHA256SUMS 59aa81cd…；A5 final 复核未变 | COMPLETE | A1/A2/A5 |
| S1-12 | 中文回执/交付包 | Issue #7 S1 结果回执已发布（commentId 6684142041，正文 9,599 字符 sha256 6985e3d2…）；Lead 签发 S1_RUN=EXECUTED_AND_RESULT_REVIEWED（S1_RUN_RESULT_ACCEPTANCE_20261106.md sha256 3d003464…）；A2 报告 rev2 sha256 b26f1648… | COMPLETE | A4/Lead |

## 4. 历史 finding 与裁定

### 4.1 A5PRE-01..06（预注册审查项）

split 计数与 digest、task_id 正则、stopping_rules 长度/类型、canonical digest、端点键唯一、预算公平。A5 phase4/4b 后均转为 CLOSED_PENDING_PHASE4C（实现/文档已修，最终关闭权归 phase4c）。

### 4.2 V4-01..06（v4 修订项）

V4-01 S0-7 冻结包与不变量（CLOSED_IN_K）；V4-02 code_sha 绑定（CLOSED_IN_J）；V4-03 pair 标签统一（CLOSED_IN_G）；V4-04 真实 e2e（CLOSED_IN_G_PENDING_PHASE4C）；V4-05 B128 实测（CLOSED_WITH_RESIDUAL：A2 G06 首测 5 runs/1 任务/K=3，measured/predicted=0.8333983992、2.58–3.01h；A2 readiness v4f 复测 0.8226、2.55–2.97h、311.492 MB/进程）；V4-06 文档同步（CLOSED_BY_THIS_DOC）。

### 4.3 S1R2 findings（A5 S1 rev2：2B/4M/6m）

S1R2-B01/B02、M01..M04、m01..m06：实现层已由 phase3 修复，A5 phase4 确认 B01/B02/M01/M02 实现层 CLOSED；其余文档/口径项由本版同步。统一状态 CLOSED_PENDING_PHASE4C。

### 4.4 R-V4-07：15 分片与 merge

- 15 分片×1,400 run=21,000（9,000/6,000/6,000）；分片窗口按 A2 readiness v4f 实测每片 2.1216h、窗口 2.55–2.97h、峰值 311.492 MB/进程（15 进程约 4.56 GiB）（5 runs/1 任务/K=3，measured/predicted=0.8226，20% 内）；首片核对，3.5h 硬上限。
- merge 子命令：serial/merged 仅 cost.total_wall_s 与 record_digest 可不同；去掉这两项的 canonical 子集必须逐字节一致；analysis 用 canonical 子集校验。
- merge 测试：A1 已实现；A5 merge delta 未开始。
- 资源：A2 v4d 外推理论 2.4601h、推荐 2.95–3.44h、15 进程 4.4583 GiB；A2 v4e 首测 2.58–3.01h；A2 readiness v4f 复测 2.55–2.97h、峰值 311.492 MB/进程；首片核对。
- S1_RUN 门禁顺序：J→K→A2 readiness v4f→A3 审计 J/K/S0-7/readiness→A5 phase4c→APPROVE+Lead 授权→15 片+merge→A5/A3→回执。

### 4.5 A5 phase3 findings（S1R3-B01/B02/M01/M02/m01..m06）

phase3 结论 CHANGES_REQUESTED（2B/2M/6m）；commit G 修复 B01/M01 等；A5 phase4 确认 B01/B02/M01/M02 实现层 CLOSED；minor 由文档/代码同步。状态 CLOSED_PENDING_PHASE4C。

### 4.6 v1.7 同步证据

1. S0-7 入库（commit K）与 9/9、determinism PASS；final_verify 15/15 为包外证据（sha256 ecee6971…，A5 phase4c m02）；
2. commit J 修复确证包 delta 逃生（s1_runner.py:281-307；测试 :2035/:2088/:2101/:2154/:2209/:2272/:2326）与 949 tests；
3. 合同 v1.6、执行计划 v1.7、统计计划 v1.5 同步；
4. A2 readiness v4f COMPLETE（7/7 gate，sha 77db3e24…，runs_executed=0）；
5. A3 v4f 审计 PASS（40/40，sha ef694d55…）+ L addendum（d1c597a9…）+ m04 addendum（ae5cf638…）；
6. A5 phase4c CHANGES_REQUESTED（0B/1M/2m，治理/文档项），待 final re-verdict；m04 已由 A4 标 CLOSED；
7. （v1.7 时点）S1_RUN 未批准、21,000 NOT_RUN；v1.8 已更新为已执行/已复核（见 §1 与 §7.2）。

### 4.7 A5 phase4 findings 逐条映射（1B/4M/5m）

| ID | 等级 | 事实（摘要） | 落点/证据 | 状态 |
|---|---|---|---|---|
| S1R4-B01 | blocker | runner required-order pair 标签与 analysis 字典序不一致；真实 16-run serial/merged analysis 均 EXIT=2（S1_ANALYSIS_FAILED … FOMAML-ZERO-BO|PRETRAIN-KSHOT-BO） | commit G 48403e5 统一 pair 标签函数；analysis 归一/计数严格相等；R-V4-10-01/-03；真实 e2e 测试 | CLOSED_IN_G_PENDING_PHASE4C |
| S1R4-M01 | major | S0-4 仍被 runner grid 接受（run_count=21000）；launcher 未绑定 S0-5/S0-6 | commit G code_sha fail-closed + --allow-code-delta 限制；phase4b 判 PARTIAL_BLOCKER；J 确证包绝对 fail-closed + S0-7 重生成；R-V4-11 | CLOSED_IN_J_PENDING_PHASE4C |
| S1R4-M02 | major | A2 G05 用合成 report，未覆盖真实 runner→analysis | A2 readiness v4e 改用真实 runner 小样本并断言 analysis 重算一致；R-V4-10-03；phase4b 确认 | CLOSED |
| S1R4-M03 | major | 合同/执行计划/矩阵仍以 S0-4/v1.4/867 tests 为基线 | 合同 v1.5、执行计划 v1.7、统计计划 v1.5、矩阵 v1.6；949 tests（现行为合同 v1.6、统计计划 v1.5、矩阵 v1.7） | CLOSED_IN_DOCS |
| S1R4-M04 | major | B128 资源未实测；15 片窗口为外推 | A2 readiness v4e G06 首测（5 runs/1 任务/K=3）；A2 readiness v4f 复测 0.8226、窗口 2.55–2.97h、311.492 MB/进程；首片核对 | CLOSED_WITH_RESIDUAL |
| S1R4-m01 | minor | A3 报告引用旧 sha；最终版 13,550 B / sha f7f467dc… | 文档引用最终版；A3 保持最终版 | CLOSED_BY_A3_FINAL_PENDING_PHASE4C |
| S1R4-m02 | minor | merge serial 61,740 B vs merged 61,741 B，仅 cost.total_wall_s 差异；口径未写明 | R-V4-10-07 canonical 子集；§4.4 | CLOSED_BY_R_V4_10_07_PENDING_PHASE4C |
| S1R4-m03 | minor | analysis 自动发现 report 可能重复加载 | R-V4-10-01/-03 e2e；CLI 文档 | CLOSED_BY_R_V4_10_01_PENDING_PHASE4C |
| S1R4-m04 | minor | A2 synthetic aggregate 中文 mojibake | A2 统一 UTF-8 输出/显式 encoding；v4e 复核 | CLOSED_WITH_RESIDUAL_PENDING_PHASE4C |
| S1R4-m05 | minor | A6 legacy 诊断文案（LEGACY_PACKAGE vs CODE_SHA_DRIFT） | analysis 文档补区分 | PENDING_A5_FINAL |

### 4.8 A5 phase4b findings 逐条映射（1B/0M/4m）

| ID | 等级 | 事实（摘要） | 落点/证据 | 状态 |
|---|---|---|---|---|
| S1R4b-B01 | blocker | commit G 的 code_sha 门禁只判 require_code_sha_match+allow_code_delta，未判 exploratory/confirmatory；A5 复现 grid --frozen S0-5 --grid formal --allow-code-delta EXIT=0、evaluation_mode=confirmatory、run_count=21000；run --frozen S0-5 ... EXIT=0 且 confirmatory_eligible=true；测试 :2070/:2122 反向固化 | commit J：s1_runner.py:281-307 先判 confirmatory 直接抛 S1_FROZEN_CODE_SHA_DRIFT；flag 仅非确证包生效；测试 :2035/:2088/:2101/:2154/:2209/:2272/:2326；负控 S0-5/S0-6 四命令 DRIFT 无产物；正控 S0-2 双 sha/evaluation_mode=exploratory；证据 sha 541b7ac6…（7/7） | CLOSED_IN_J_PENDING_PHASE4C |
| S1R4b-m01 | minor | 矩阵/文档状态 stale（仍写 M01 CLOSED_IN_G、M02/M04 PENDING_A2_V4E） | 合同 v1.6、执行计划 v1.7、统计计划 v1.5、矩阵 v1.7 更新；§4.7 状态按 phase4b 实际；phase4c S1R4c-m01 一并关闭 | CLOSED_BY_THIS_DOC |
| S1R4b-m02 | minor | A1 v4e 修复报告 :14/:56/:66 漏写「仅非确证包可 --allow-code-delta」 | A1 已就地修正 S1_v4e_b01_fix_report.md（13,862 B，sha256 c385887f…，追加 §7） | CLOSED_BY_A1 |
| S1R4b-m03 | minor | B128 资源仅 5 runs/1 任务/K=3，未覆盖完整矩阵 | A2-V4E-B03 披露：measured/predicted=0.8333983992（20% 内），窗口 2.58–3.01h、峰值 4.5743 GiB；首片核对 | CLOSED_WITH_RESIDUAL |
| S1R4b-m04 | minor | A2 G05 与 A5 e2e 读取 meta_test TE-000/001 任务定义（各 8 records，合成解析，0 物理，未看指标） | A3 m04 登记 addendum（`<EXT>/p4-route-a/a3/S1_v4f_holdout_registration_addendum.md`，sha256 ae5cf638…）登记 A2 G05、A5 phase4b e2e、A5 phase4c e2e；正式分析披露 TE-000/001 仅用于链路验证、不据此调参、不作科学结论 | CLOSED（A3 登记完成；A5 final re-verdict 确认） |

### 4.9 R-V4-11：S0-7 与 phase4c 门禁

1. R-V4-11-01 确证包 code_sha 绝对 fail-closed（FC-20）：confirmatory_eligible=true 的包，grid/run/merge 在 code_sha≠当前 package_code_sha() 时必须抛 S1_FROZEN_CODE_SHA_DRIFT，即使 --allow-code-delta 也不放行；flag 仅 legacy/exploratory 包，放行时记录 frozen/current 双 sha、code_sha_match=false、code_sha_delta_allowed=true、evaluation_mode=exploratory；禁止「确证包+delta+confirmatory」组合。
2. R-V4-11-02 测试：更新旧 :2070/:2122；负控 S0-5/S0-6 四命令非 0 退出且错误码含 DRIFT、无产物；正控 S0-2/S0-3 legacy 可 delta；全量 ≥948 OK(skipped=1)。
3. R-V4-11-03 文档：A1 修报告、A4 更新矩阵（phase4 M01=OPEN_UNTIL_S0-7→CLOSED_AFTER_PHASE4C、M02/M04=CLOSED、B01 映射 R-V4-11）、合同/执行计划同步确证包禁止 delta；不得称 S1 已放行。
4. R-V4-11-04 S0-7 重生成：见 §2.5；S0-6 标 SUPERSEDED_LEGACY；A2/A3/A5 绑定同一 S0-7。
5. R-V4-11-05 放行链：A1 修→Lead J→A1 S0-7→Lead K→A2 readiness v4f→A3 审计 J/K/S0-7/readiness→A5 phase4c（含 B01 负控复现、947+ tests、真实 e2e）→APPROVE_FOR_S1_RUN→Lead 书面授权（S0-7 路径/SHA256SUMS/run_id/15 片/3.5h 上限）→A2 启动 15 片 21,000。
6. R-V4-11-06 边界：physical=0；RCAIDE/SU2/VSPAERO/WaveDrag LOCKED；不合 main；不新开 PR；仅 Lead 写 GitHub；旧冻结件只读；A5 不得以书面 deviation 替代修复。

### 4.10 A5 phase4c findings 逐条映射（0B/1M/2m；2026-11-06）

| ID | 等级 | 事实（摘要） | 落点/证据 | 状态 |
|---|---|---|---|---|
| S1R4c-M01 | major | A3 未登记 A5 对 meta_test TE-000/001 的受控 e2e 读取（程序性/治理，无代码/包缺陷） | A3 m04 登记 addendum（sha256 ae5cf638…）登记 A2 G05、A5 phase4b e2e（run_records sha 00cf0692…）、A5 phase4c e2e（run_records sha 26b50ae9…）；A4 合同 §10.1/矩阵 §4.8 同步标 CLOSED | CLOSED_BY_A3_REGISTRATION_PENDING_A5_FINAL |
| S1R4c-m01 | minor | L 时点文档仍写 A2 readiness v4f 未定稿、A3 未开始、A5 phase4c 未开始 | 合同 v1.6、执行计划 v1.7、统计计划 v1.5、矩阵 v1.7 状态同步；A2 md sha 77db3e24…、A3 md sha ef694d55… | CLOSED_BY_THIS_DOC |
| S1R4c-m02 | minor | S0-7 11 文件包不含 final_verify_report.json；README/文档引用 15/15 但未声明外部路径 | 合同 §10 第 13 项与矩阵 §6 声明：A1 外部 `<EXT>/p4-route-a/a1/s0_7_freeze_official/final_verify_report.json`（5,110 B，sha256 ecee6971…，15/15 PASS）；冻结包不可变、不补写 | CLOSED_BY_THIS_DOC |

A5 phase4c 独立事实：worktree detached L、clean；独立 949 tests（Ran 949 tests in 448.714s / OK (skipped=1)，log sha 8ba8dcca…）；B01 12/12 DRIFT 负控 + S0-2 正控 exploratory；S0-7 两进程 grid 逐字节一致 21,000；e2e 8 records/merge PASS/analysis exit 0/C5 NOT_ESTIMABLE；physical=0；verdict=S1_RUN NOT_APPROVED。

## 5. 统计计划映射

| 统计项 | 合同/计划 | 矩阵状态 |
|---|---|---|
| 主终点 best_feasible_value | 统计计划 v1.5 §5–§7 | IMPLEMENTED_PENDING_A5_FINAL |
| C1–C4 四比较 | 统计计划 v1.5 §6 | IMPLEMENTED_PENDING_A5_FINAL |
| C5-B 结构性不可辨识 | 合同 §7.2 / 统计计划 v1.5 §6 | IMPLEMENTED_PENDING_A5_FINAL |
| Holm 唯一族 (endpoint,B,K) | 合同 §7.2 / 统计计划 v1.5 §6 | IMPLEMENTED_PENDING_A5_FINAL |
| pair 标签字典序规范化 | R-V4-10-01 / 统计计划 v1.5 §6 | CLOSED_IN_G_PENDING_A5_FINAL |
| null/缺失处理 | 统计计划 v1.5 §5 | IMPLEMENTED_PENDING_A5_FINAL |
| 七类图 | 执行计划 v1.7 §8 | IMPLEMENTED_PENDING_A5_FINAL |
| 确定性/负控/泄漏 | 执行计划 v1.7 §7 | TESTED_PENDING_A5_FINAL |

## 6. 文件与测试存在性

| 文件/对象 | 证据 | 状态 |
|---|---|---|
| research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z/ | 11 文件；SHA256SUMS.txt sha256 59aa81cd…；9/9；determinism PASS；final_verify 15/15 为包外证据（见下行） | COMMITTED（K） |
| s0-7 tasks.json | 340,443 B；sha256 59f66a41… | VERIFIED |
| s0-7 meta_task_split.json | 79,128 B；sha256 589f77e5… | VERIFIED |
| s0-7 frozen_family.json | 10,259 B；sha256 246729d4… | VERIFIED |
| s0-7 preregistration.json | 12,368 B；sha256 ffd33764… | VERIFIED |
| s0-7 budget_fairness_report.json | 64,723 B；sha256 f2033257… | VERIFIED |
| s0-7 determinism_report.json | 3,297 B；sha256 dafba4f5… | VERIFIED |
| s0-7 digest_manifest.json / freeze_summary.json | 2,332 B / 7,217 B；sha 6cd0aa4c… / ea1d7931… | VERIFIED |
| s0-7 v3_isolation_report.json | 4,170 B；sha256 fe80047d… | VERIFIED |
| final_verify_report.json（包外） | <EXT>/p4-route-a/a1/s0_7_freeze_official/final_verify_report.json；5,110 B；sha256 ecee6971…；15/15 PASS | VERIFIED_EXTERNAL |
| s1_runner.py / test_s1_runner.py | commit J 修复；2,463 行/110,377 B（sha 11ca2452…）、2,425 行/101,294 B（sha 41bbf924…）；模块 93 tests OK | TESTED |
| 949 tests 全量 | Lead commitJ_full_tests.log（8,956 B，sha 6f584635…；442.006s）；A1 full_suite_v4f.log（sha 261da8ce…；442.712s）；A5 phase4c 独立 s1_phase4c_949tests.log（448.714s，sha 8ba8dcca…） | TESTED（非 A5 verdict） |
| R-V4-11 裁定文件 | docs/planning/p4_route_a_s1_v4f_rulings_20261106.md（37 行，随 J 入库） | READ |
| A5 phase4b 报告/findings/verdict | <EXT>/p4-route-a/a5/S1_phase4b_review.md（sha def5c059…）；findings_phase4b.csv（sha ffb5dcf0…）；verdict_phase4b.txt（sha ef35bb36…） | READ |
| A1 v4f 修复报告/证据 | S1_v4f_b01_fix_report.md；v4f_b01_escape_evidence.json（9,971 B，sha 541b7ac6…，7/7） | READ |
| A2 readiness v4f | <EXT>/p4-route-a/a2/s1_prep_v4f/S1_formal_readiness.md（11,863 B，sha256 77db3e24…）、.json（45,235 B，sha b883e691…）、SUMS（sha e8f9a874…）；7/7 gate | PASS_READY_PENDING_LEAD_AUTHORIZATION |
| A3 v4f 审计 | S1_v4f_isolation.md（sha ef694d55…，40/40）；addendum L（sha d1c597a9…）；m04 addendum（sha ae5cf638…） | PASS（8/8 PASS） |
| A5 phase4c | S1_phase4c_review.md（sha db8e3106…）、findings（sha f66e2b9a…）、verdict（sha 5fe0afc5…）；独立 949 tests 448.714s | CHANGES_REQUESTED（0B/1M/2m） |

## 7. 阶段门、当前位置与验收

### 7.1 阶段门

修复→Lead 全量测试→commit J→A1 干净 detached worktree 生成 S0-7→Lead 入库 commit K→A2 readiness v4f（已完成）→A4 文档 v1.7（L 之后单独文档提交）→A3 v4f 审计（PASS + addenda）→A5 phase4c（CHANGES_REQUESTED 0B/1M/2m）→A3 m04 登记 + A4 m04 CLOSED→A5 final re-verdict（APPROVE_FOR_S1_RUN）+ Lead 书面授权→15 分片+merge（21,000 PASS）→analysis 最终版+v5b 确定性 PASS→A5 结果复核（APPROVE_FOR_S1_RESULT_RECEIPT）→A4 中文回执经 Lead 发布（Issue #7 commentId 6684142041）。

### 7.2 当前位置

- 已完成：J、K、L、M、S0-7、949 tests、A4 文档同步 v1.6/v1.7/v1.5/v1.7、A2 readiness v4f（7/7 gate）、A3 v4f（PASS 40/40 + addenda）、A5 phase4c final（APPROVE_FOR_S1_RUN）、Lead 授权 v3/v5/v5a/v5b、S1 formal 21,000（15 分片+merge PASS）、analysis 最终版、v5b 确定性 PASS、A5 结果复核（APPROVE_FOR_S1_RESULT_RECEIPT）、A3 终稿证据审计 PASS、Issue #7 回执发布、Lead S1_RUN 验收签发；
- 未完成（S1 范围内）：无；S2 尚未启动；
- 未批准/未变更：阶段验收放行、S2 授权、真实 holdout 指标、新物理；S1_RUN 状态=EXECUTED_AND_RESULT_REVIEWED。

### 7.3 交付证据包（12 项）

run_config、summary.json、preregistration、data_manifest、run_records.jsonl、端点 CSV、配对 CSV、预算 CSV、可辨识性 CSV、七图 PNG、中文报告、SHA256 清单。

### 7.4 验收（16 条）

1. 949 tests OK(skipped=1)（Lead J 日志；非 A5 verdict）。
2. 40 组预算公平单测，五臂 billable=B，K 计入 B。
3. 九端点键完整、null 规则正确。
4. 统计计划 C1–C4/C5-B/Holm 可执行。
5. 冻结包 S0-7，SHA256SUMS.txt sha256 59aa81cd…、9/9、determinism PASS；final_verify 15/15 为包外证据（5,110 B，sha ecee6971…，不补写冻结包）。
6. 确定性 200×3 与负控通过。
7. physical_call_count=0。
8. 文档 0 绝对路径、中文、无 AI 记忆。
9. 21,000 网格=9,000/6,000/6,000，15×1,400；窗口 2.55–2.97h（A2 v4f 实测，首片核对，3.5h 硬上限）。
10. v4 holdout 隔离，TE 20 任务；旧包不进 formal。
11. pair 标签/计数严格一致；C5-B 不进 Holm。
12. 正式工件/readiness 可重建。
13. R-V4-10-03 真实 e2e：串行与 merge 两条链路 exit 0 且 structural 计数一致。
14. 确证包 code_sha 绝对 fail-closed 负控（S0-5/S0-6 四命令 DRIFT 无产物；S0-2 正控双 sha）。
15. launcher 六项预检（含 --dry-run）并绑定 S0-7/K。
16. merge canonical 子集逐字节一致。
17. A3 m04 登记 addendum 已登记 A2 G05/A5 phase4b/phase4c 对 TE-000/001 的受控读取（各 8 records、0 物理、未读指标），正式报告须披露。
18. A2 readiness v4f 7/7 gate、A3 v4f 40/40 PASS 与 m04 登记均在 A5 final re-verdict 前完成；S1_RUN 未批准前不得启动 21,000；v1.8 时点前置已满足（A5 final APPROVE + Lead 授权），21,000 已执行并完成结果复核/回执。

## 8. 风险与待决策

| ID | 风险 | 缓解 |
|---|---|---|
| R-01 | K-shot 未真正闭环或泄漏 query 标签 | S1-01 测试；R-V4-10-03 e2e；A5 审 |
| R-02 | 预算不公平（K 未计入 B/臂间不等） | 40 组单测；billable=B 断言 |
| R-03 | pair 标签再次不一致 | 唯一函数 + analysis 归一 + 计数严格相等 |
| R-04 | code_sha 漂移导致旧包混入 | fail-closed + --allow-code-delta 仅 exploratory |
| R-05 | launcher 未绑定 S0-7 | 六项预检；失败不启动 |
| R-06 | B128 资源超预期 | A2 readiness v4f 复测比值 0.8226；窗口 2.55–2.97h；3.5h 硬上限 |
| R-07 | merge 口径不一致 | canonical 子集逐字节比较 |
| R-08 | 旧工件被改写 | 只读；A3 审计；fail-closed |
| R-09 | 旧任务当新盲测 | 新任务族/seed；冻结预注册 |
| R-10 | holdout 污染 | TE 一次性打开；隔离审计 |
| R-11 | 物理调用漏计 | physical_call_count=0 断言；无 solver 路径 |
| R-12 | 不可辨识 C5 被当结论 | C5-B 排除；结构性诊断 |
| R-13 | 过拟合 meta_test | 预注册主终点；Holm；bootstrap；A5 审 |
| R-14 | 文档与代码不一致 | 本版同步；A5 phase4b 复核 |
| R-15 | A2 G05 仍用合成数据 | M02 PENDING_A2_V4E；真实 runner 产物 |
| R-16 | 资源/墙钟外推失真 | M04；B128 实测后定窗口 |
| R-17 | 中文乱码/mojibake | UTF-8 显式 encoding；A2 统一输出（v4f 交付）；A5 复核 |
| R-18 | 自动发现 report 重复加载 | 显式 report 路径；分析测试 |
| R-19 | legacy 诊断混淆 | 文档区分 LEGACY_PACKAGE/CODE_SHA_DRIFT |
| R-20 | A5 未出 verdict 即启动 | S1_RUN 门禁；Lead 书面授权 |
| R-21 | 分片失败未停 | stopping_rules；3.5h 上限 |
| R-22 | 旧 A 类剩余 6 次被误用 | 封账 CLOSED 不结转 |
| R-23 | B 类 12 次/RCAIDE 被误启动 | LOCKED/NOT_TRIGGERED；无自动回退 |
| R-24 | GitHub 越权发布 | 仅 Lead 写；A4 只读 |
| R-25 | S0-6 与 S0-5 不变量漂移 | 逐字节 tasks/split 对比；9/9 |
| R-26 | A2 v4e/B128 未完成即授权 | 阶段门；M04 未关闭不放行 |
| R-27 | 回执提前宣称放行 | 回执写 NOT_APPROVED/待 phase4b |
| R-28 | 确证包 delta 逃生再次出现 | J 修复 + FC-20 + 负控；A5 phase4c 复现 |
| R-29 | S0-7 未绑定 readiness/审计 | A2/A3/A5 全部绑定同一 S0-7；门禁 |
| R-30 | A3 m04 addendum 读取中间版本时曾见 H05 FAIL 与总结 FAIL 0 不一致；最终版为 8/8 PASS（H01–H08，fails=[]） | 已按最终版 sha256 ae5cf638…（82 行/7,569 B）修正文档引用；不构成开放风险 |
| R-31 | final_verify 15/15 为包外证据，离线复现易漏 | 合同 §10 第 13 项/矩阵 §6 声明外部路径与 sha256；冻结包不可变、不补写 |

待决策：1) 首片窗口 2.55–2.97h 的复核（A2 v4f 实测）；2) A5 final re-verdict（B01 负控、949 tests、真实 e2e、merge delta 已通过，m04 登记已闭环）；3) Lead 授权范围（S0-7 路径/SHA256SUMS/run_id/15 片/3.5h/停跑）；4) 是否在 S1 后进入 S2（按统计门禁与成本，不在本轮）。

## 9. 读取记录

- 2026-11-06（v1.6）：读取 commit K（8118234）、J（004156c）、I（36619cf）、S0-7 包全部 11 文件、SHA256SUMS 9/9、determinism_report、A1 v4f 修复报告与证据 JSON、A5 phase4b 报告/findings/verdict、Lead 949 tests 日志、R-V4-11 裁定、合同 v1.4→v1.5、执行计划 v1.5→v1.6、统计计划 v1.3→v1.4、矩阵 v1.5→v1.6。
- 2026-11-06（v1.7）：读取 commit L（8f34e91）、A2 readiness v4f（md/json/SUMS）、A3 S1_v4f_isolation.md + addendum L + m04 登记 addendum、A5 phase4c 报告/findings/verdict/949 日志、A1 final_verify_report.json（5,110 B，sha ecee6971…）；按 A3 addendum 最终版（sha256 ae5cf638…，82 行/7,569 B，8/8 PASS）校正文档引用。
- 未读取真实 holdout 指标；未启动 solver；未写 GitHub。

## 10. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4 | 初版 S1 矩阵（S1-01..12、A5PRE、阶段门） |
| v1.1 | 2026-11-05 | A4 | 按 R-V4-04/-05 补 merge/readiness 隔离 |
| v1.2 | 2026-11-05 | A4 | 按 task-248 同步 S0-3、A2 v4b、A3 v4b、15 分片/merge |
| v1.3 | 2026-11-06 | A4 | 按 R-V4-08/A5 phase3 同步 v4c、S0-4、867 tests |
| v1.4 | 2026-11-06 | A4 | 按 A5 phase3/S0-4 同步 390 行；A5 phase4 PENDING |
| v1.5 | 2026-11-06 | A4（task-224） | 同步 S0-6/G/H/947 tests；A5 phase4 1B/4M/5m 逐条映射；新增 §4.7；15 片窗口待 B128；S1_RUN=NOT_APPROVED；未 commit/push，0 物理 |
| v1.6 | 2026-11-06 | A4（task-224） | 按 R-V4-11 与 A5 phase4b（1B/0M/4m）：S0-7（J 生成/K 入库）、commit J code_sha 绝对 fail-closed、949 tests、§4.8/§4.9、phase4 M01/M02/M04 状态更新、15 片窗口 2.58–3.01h、S1_RUN=NOT_APPROVED；未 commit/push，0 物理 |
| v1.7 | 2026-11-06 | A4（task-224） | 按 L/A2 readiness v4f/A3 v4f/A5 phase4c：A2 COMPLETE（77db3e24…）、A3 PASS（ef694d55…）+ addenda（d1c597a9…/ae5cf638…）、A5 phase4c 0B/1M/2m 逐条（§4.10）、m04 CLOSED、m02 final_verify 包外声明、窗口 2.55–2.97h、S1_RUN=NOT_APPROVED；未 commit/push，0 物理 |
| v1.8 | 2026-11-06 | Lead（同步 A4 task-263 事实） | S1 formal 21,000 执行完成（p4ra-s1-formal-20261106T0250Z；attempt1/2 外部终止 0 records 已归档；attempt3 成功）+ merge PASS + analysis 最终版（aggregate 02b24c44…）+ v5b 确定性 PASS（41623140…）；A5 final APPROVE_FOR_S1_RUN、A5 结果复核 APPROVE_FOR_S1_RESULT_RECEIPT、A3 终稿 PASS（175b2fc7…）；Issue #7 回执 commentId 6684142041（正文 sha 6985e3d2…）；S1_RUN=EXECUTED_AND_RESULT_REVIEWED；S1-07/S1-11/S1-12 COMPLETE；0 物理 |
