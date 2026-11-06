# P4 路线A S1 需求矩阵（v1.5）

> 文档性质：Issue #7 S1 的只读需求—证据—状态核对表；**不是验收结论，不是 S1_RUN 授权**。
> 当前位置：HEAD=commit H e95f9dc（父 G 48403e5，G 父 F fe8bdc9）；branch research/p4-route-a-s1；S0-6 确证冻结包已入库；A5 phase4 结论 CHANGES_REQUESTED（1 blocker/4 major/5 minor）；B01/M01 已由 G 修复；M02/M04 待 A2 v4e；M03 由本版文档关闭；A5 phase4b 尚未开始；S1_RUN=NOT_APPROVED；formal 21,000 NOT_RUN；15 分片未启动；physical=0。
> 依据：Issue #7 §2 S1/S4、§3–§4；执行计划 v1.5；数据合同 v1.4；统计计划 v1.3；R-V4-01..10；A5 phase4 报告（<EXT>/p4-route-a/a5/S1_phase4_review.md，sha256 c162cdc4…）与 findings_phase4.csv；Lead commit G 后全量测试日志 <EXT>/p4-route-a/lead/commitG_full_tests.log（8,954 B，sha256 53e3b7cd…）。
> 读取时点：2026-11-06（A4 task-224）。
> v1.5 变更：S0-6 替代 S0-4/S0-5 成为唯一确证包；commit G/H；947 tests；A5 phase4 1B/4M/5m 逐条映射；新增 §4.7；15 片窗口改为待 A2 B128 实测；S1 状态改为 COMMITTED_PENDING_A5_PHASE4B。
> 状态口径：PASS / PARTIAL / BLOCKED / NOT_RUN / IMPLEMENTED_PENDING_A5 / CLOSED_* / PENDING_*；未获 A5 verdict 的项不得写 PASS。

## 1. 当前状态与硬边界

| 项 | 状态 | 说明 |
|---|---|---|
| S0-2 冻结包 | 历史只读 | 旧 8 payload；仅历史复现/负控 |
| S0-3 冻结包 | 历史只读 | 已被 S0-4/S0-5/S0-6 取代 |
| S0-4 冻结包 | SUPERSEDED_LEGACY | commit D ae013ed；旧确证包；只读 |
| S0-5 冻结包 | SUPERSEDED_LEGACY | commit F fe8bdc9；A5 phase4 审查对象；只读 |
| S0-6 冻结包 | COMPLETE_GENERATED_AND_COMMITTED | commit G 生成、commit H 入库；9/9、determinism PASS、final_verify 15/15 |
| S1 实现 | COMMITTED_PENDING_A5_PHASE4B | commit G 修复 B01/M01；947 tests；真实 e2e/launcher 待 A5 phase4b |
| A5 phase3 | CHANGES_REQUESTED 已修复 | 2B/2M/6m；实现层由 G 关闭，待 phase4b 复核 |
| A5 phase4 | CHANGES_REQUESTED（1B/4M/5m） | B01/M01 CLOSED_IN_G；M02/M04 PENDING_A2_V4E；M03 CLOSED_BY_THIS_DOC；A5 phase4b 未开始 |
| S1 formal run（21,000） | NOT_RUN / NOT_APPROVED | 无授权；15 分片未启动 |
| 真实 holdout | 未读 | TE 20 任务只在授权后一次性打开 |
| K-shot 闭环 | IMPLEMENTED_PENDING_A5_PHASE4B | 支持集进入内循环；K 计入 B；R-V4-10-03 e2e 待 A5 复核 |
| 15 分片/merge | IMPLEMENTED_PENDING_A5_PHASE4B | merge canonical 子集口径；窗口待 A2 B128 实测 |
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

### 2.4 S0-6（当前唯一确证包）

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
| 状态 | COMPLETE_GENERATED_AND_COMMITTED；S0-5/S0-4 转历史只读 |

## 3. S1 需求（S1-01..12）

| ID | 要求 | 实现/证据 | 状态 | 责任 |
|---|---|---|---|---|
| S1-01 | K-shot 支持集进入适应内循环并用适应后代理评分 | m5_arms.py 支持集参数与调用链；K∈{0,1,3,5}；K=0 兼容 | IMPLEMENTED_PENDING_A5_PHASE4B | A1 |
| S1-02 | 五臂（Random/Pretrain/FOMAML-Zero/FOMAML-Kshot/DE）与预算公平 | 40 组预算单测；billable=B；K 计入 B | TESTED_PENDING_A5_PHASE4B | A1/A2 |
| S1-03 | run_records.jsonl 字段/确定性/record_digest | 合同 §4；200×3 确定性测试；947 tests 基线 | TESTED_PENDING_A5_PHASE4B | A1 |
| S1-04 | 九端点、null 规则、聚合口径 | s1_analysis.py/s1_figures.py；端点表；null 不插值 | IMPLEMENTED_PENDING_A5_PHASE4B | A1 |
| S1-05 | C1–C4/C5-B、Wilcoxon/bootstrap/Holm 唯一族 | 统计计划 v1.3；Holm 族键 (endpoint,B,K)；C5 排除 | IMPLEMENTED_PENDING_A5_PHASE4B | A1/A2 |
| S1-06 | 七类中文图 | s1_figures.py；图题图注中文；数据来源标注 | IMPLEMENTED_PENDING_A5_PHASE4B | A1/A2 |
| S1-07 | 15 分片×1,400、merge、S1_RUN 门禁 | G 修复后 merge canonical 子集；窗口待 A2 B128 实测 | TESTED_947_PENDING_A5_PHASE4B | A1 |
| S1-08 | launcher 预检（S0-6 路径/SHA256SUMS/code_sha/HEAD/artifacts/TOP run_id/15 片/21,000） | commit G 实现；--dry-run；预检失败 exit≠0 | IMPLEMENTED_PENDING_A5_PHASE4B | A1 |
| S1-09 | code_sha fail-closed 与 --allow-code-delta 仅 exploratory | commit G 实现；三类负控；confirmatory 无逃生 | IMPLEMENTED_PENDING_A5_PHASE4B | A1 |
| S1-10 | 真实 runner→analysis e2e（串行与 merge） | R-V4-10-03；B64/K∈{0,3}/2 任务/2 臂/0 物理；G 修复 B01 | IMPLEMENTED_PENDING_A5_PHASE4B | A1/A5 |
| S1-11 | 预注册/S0-6 冻结包与不变量 | S0-6；9/9；determinism PASS；final_verify 15/15 | COMPLETE_PENDING_A5_PHASE4B | A1/A2 |
| S1-12 | 中文回执/交付包 | A4 回执草稿 v4（未发布）；文档同步 | IN_PROGRESS | A4 |

## 4. 历史 finding 与裁定

### 4.1 A5PRE-01..06（预注册审查项）

split 计数与 digest、task_id 正则、stopping_rules 长度/类型、canonical digest、端点键唯一、预算公平。A5 phase4 后均转为 CLOSED_PENDING_PHASE4B（实现/文档已修，最终关闭权归 phase4b）。

### 4.2 V4-01..06（v4 修订项）

V4-01 S0-4/S0-5/S0-6 冻结包与不变量（CLOSED_IN_H）；V4-02 code_sha 绑定（CLOSED_IN_G）；V4-03 pair 标签统一（CLOSED_IN_G）；V4-04 真实 e2e（CLOSED_IN_G_PENDING_PHASE4B）；V4-05 B128 实测（PENDING_A2_V4E）；V4-06 文档同步（CLOSED_BY_THIS_DOC）。

### 4.3 S1R2 findings（A5 S1 rev2：2B/4M/6m）

S1R2-B01/B02、M01..M04、m01..m06：实现层已由 phase3 修复，A5 phase4 确认 B01/B02/M01/M02 实现层 CLOSED；其余文档/口径项由本版同步。统一状态 CLOSED_PENDING_PHASE4B。

### 4.4 R-V4-07：15 分片与 merge

- 15 分片×1,400 run=21,000（9,000/6,000/6,000）；分片窗口待 A2 v4e B128 实测后确定（建议 3.5–4.5h，不得先写成确定值）。
- merge 子命令：serial/merged 仅 cost.total_wall_s 与 record_digest 可不同；去掉这两项的 canonical 子集必须逐字节一致；analysis 用 canonical 子集校验。
- merge 测试：A1 已实现；A5 merge delta 未开始。
- 资源：A2 v4d 外推理论 2.4601h、推荐 2.95–3.44h、15 进程 4.4583 GiB；B128 实测未完成。
- S1_RUN 门禁顺序：修复→G→S0-6→H→A2 readiness v4e→A4 文档→A3 审计→A5 phase4b→APPROVE+Lead 授权→15 片+merge→A5/A3→回执。

### 4.5 A5 phase3 findings（S1R3-B01/B02/M01/M02/m01..m06）

phase3 结论 CHANGES_REQUESTED（2B/2M/6m）；commit G 修复 B01/M01 等；A5 phase4 确认 B01/B02/M01/M02 实现层 CLOSED；minor 由文档/代码同步。状态 CLOSED_PENDING_PHASE4B。

### 4.6 v1.5 同步证据

1. S0-6 入库（commit H）与 9/9 校验；
2. commit G 修复 pair 标签/code_sha/launcher + 947 tests；
3. 合同 v1.4、执行计划 v1.5、统计计划 v1.3 同步；
4. A2 v4e 进行中（真实 G05、B128 实测未完成）；
5. A5 phase4b 未开始，S1_RUN 未批准。

### 4.7 A5 phase4 findings 逐条映射（1B/4M/5m）

| ID | 等级 | 事实（摘要） | 落点/证据 | 状态 |
|---|---|---|---|---|
| S1R4-B01 | blocker | runner required-order pair 标签与 analysis 字典序不一致；真实 16-run serial/merged analysis 均 EXIT=2（S1_ANALYSIS_FAILED … FOMAML-ZERO-BO|PRETRAIN-KSHOT-BO） | commit G 48403e5 统一 pair 标签函数；analysis 归一/计数严格相等；R-V4-10-01/-03；真实 e2e 测试 | CLOSED_IN_G_PENDING_A5_PHASE4B |
| S1R4-M01 | major | S0-4 仍被 runner grid 接受（run_count=21000）；launcher 未绑定 S0-5/S0-6 | commit G code_sha fail-closed + --allow-code-delta 限制；launcher 六项预检；R-V4-10-02/-04 | CLOSED_IN_G_PENDING_A5_PHASE4B |
| S1R4-M02 | major | A2 G05 用合成 report，未覆盖真实 runner→analysis | A2 readiness v4e 改用真实 runner 小样本并断言 analysis 重算一致；R-V4-10-03 | PENDING_A2_V4E |
| S1R4-M03 | major | 合同/执行计划/矩阵仍以 S0-4/v1.4/867 tests 为基线 | 合同 v1.4、执行计划 v1.5、统计计划 v1.3、矩阵 v1.5；947 tests | CLOSED_BY_THIS_DOC |
| S1R4-M04 | major | B128 资源未实测；15 片窗口为外推 | A2 readiness v4e 实测 B128×K=3；R-V4-10-05 | PENDING_A2_V4E |
| S1R4-m01 | minor | A3 报告引用旧 sha；最终版 13,550 B / sha f7f467dc… | 文档引用最终版；A3 保持最终版 | CLOSED_BY_A3_FINAL_PENDING_A5_PHASE4B |
| S1R4-m02 | minor | merge serial 61,740 B vs merged 61,741 B，仅 cost.total_wall_s 差异；口径未写明 | R-V4-10-07 canonical 子集；§4.4 | CLOSED_BY_R_V4_10_07_PENDING_A5_PHASE4B |
| S1R4-m03 | minor | analysis 自动发现 report 可能重复加载 | R-V4-10-01/-03 e2e；CLI 文档 | CLOSED_BY_R_V4_10_01_PENDING_A5_PHASE4B |
| S1R4-m04 | minor | A2 synthetic aggregate 中文 mojibake | A2 统一 UTF-8 输出/显式 encoding；v4e 复核 | PENDING_A2_V4E |
| S1R4-m05 | minor | A6 legacy 诊断文案（LEGACY_PACKAGE vs CODE_SHA_DRIFT） | analysis 文档补区分 | PENDING_A5_PHASE4B |

## 5. 统计计划映射

| 统计项 | 合同/计划 | 矩阵状态 |
|---|---|---|
| 主终点 best_feasible_value | 统计计划 §5–§7 | IMPLEMENTED_PENDING_A5_PHASE4B |
| C1–C4 四比较 | 统计计划 §6 | IMPLEMENTED_PENDING_A5_PHASE4B |
| C5-B 结构性不可辨识 | 合同 §6.3 / 统计计划 §6 | IMPLEMENTED_PENDING_A5_PHASE4B |
| Holm 唯一族 (endpoint,B,K) | 合同 §6.3 / 统计计划 §6 | IMPLEMENTED_PENDING_A5_PHASE4B |
| pair 标签字典序规范化 | R-V4-10-01 / 统计计划 §6 | CLOSED_IN_G_PENDING_A5_PHASE4B |
| null/缺失处理 | 统计计划 §5 | IMPLEMENTED_PENDING_A5_PHASE4B |
| 七类图 | 执行计划 §8 | IMPLEMENTED_PENDING_A5_PHASE4B |
| 确定性/负控/泄漏 | 执行计划 §7 | TESTED_PENDING_A5_PHASE4B |

## 6. 文件与测试存在性

| 文件/对象 | 证据 | 状态 |
|---|---|---|
| research/concorde_metaopt/optimization_runs/p4ra-s0-6-freeze-20261106T003500Z/ | 10 文件；SHA256SUMS.txt 9/9；determinism PASS；final_verify 15/15 | COMMITTED（H） |
| s0-6 tasks.json | 340,443 B；sha256 59f66a41… | VERIFIED |
| s0-6 meta_task_split.json | 79,128 B；sha256 589f77e5… | VERIFIED |
| s0-6 frozen_family.json | 10,259 B；sha256 28ac2fb1… | VERIFIED |
| s0-6 preregistration.json | 12,368 B；sha256 6c6db6f7… | VERIFIED |
| s0-6 budget_fairness_report.json | 64,723 B；sha256 8d6e3544… | VERIFIED |
| s0-6 determinism_report.json | 3,297 B；sha256 d9b5dea0… | VERIFIED |
| s0-6 digest_manifest.json / freeze_summary.json | 2,332 B / 7,217 B；sha 011a03a5… / a786d1eb… | VERIFIED |
| s0-6 v3_isolation_report.json | 4,170 B；sha256 ee10aba9… | VERIFIED |
| s1_runner.py / s1_analysis.py / tests | commit G 修复；947 tests OK(skipped=1)、444.869s | TESTED |
| R-V4-10 裁定文件 | docs/planning/p4_route_a_s1_v4e_rulings_20261106.md（5,071 B） | READ |
| A5 phase4 报告/findings | <EXT>/p4-route-a/a5/S1_phase4_review.md（sha c162cdc4…）；findings_phase4.csv | READ |
| Lead commit G 全量测试日志 | <EXT>/p4-route-a/lead/commitG_full_tests.log；8,954 B；sha 53e3b7cd… | VERIFIED |

## 7. 阶段门、当前位置与验收

### 7.1 阶段门

修复→Lead 全量测试→commit G→A1 干净 detached worktree 生成 S0-6→Lead 入库 commit H→A2 readiness v4e→A4 文档→A3 审计→A5 phase4b→A5 APPROVE_FOR_S1_RUN + Lead 书面授权→15 分片+merge→A5/A3 复核→A4 中文回执（经 Lead 发布）。

### 7.2 当前位置

- 已完成：G、H、S0-6、947 tests、A4 文档同步；
- 进行中：A2 readiness v4e（真实 G05、B128 实测）；
- 待做：A3 审计 H；A5 phase4b；Lead 授权；
- 未批准：S1_RUN、21,000、真实 holdout、新物理。

### 7.3 交付证据包（12 项）

run_config、summary.json、preregistration、data_manifest、run_records.jsonl、端点 CSV、配对 CSV、预算 CSV、可辨识性 CSV、七图 PNG、中文报告、SHA256 清单。

### 7.4 验收（15 条）

1. 947 tests OK(skipped=1)（Lead 日志；非 A5 verdict）。
2. 40 组预算公平单测，五臂 billable=B，K 计入 B。
3. 九端点键完整、null 规则正确。
4. 统计计划 C1–C4/C5-B/Holm 可执行。
5. 冻结包 S0-6，9/9、determinism PASS、final_verify 15/15。
6. 确定性 200×3 与负控通过。
7. physical_call_count=0。
8. 文档 0 绝对路径、中文、无 AI 记忆。
9. 21,000 网格=9,000/6,000/6,000，15×1,400；窗口待 B128 实测。
10. v4 holdout 隔离，TE 20 任务；旧包不进 formal。
11. pair 标签/计数严格一致；C5-B 不进 Holm。
12. 正式工件/readiness 可重建。
13. R-V4-10-03 真实 e2e：串行与 merge 两条链路 exit 0 且 structural 计数一致。
14. code_sha 三类负控 + launcher 六项预检（含 --dry-run）。
15. merge canonical 子集逐字节一致。

## 8. 风险与待决策

| ID | 风险 | 缓解 |
|---|---|---|
| R-01 | K-shot 未真正闭环或泄漏 query 标签 | S1-01 测试；R-V4-10-03 e2e；A5 审 |
| R-02 | 预算不公平（K 未计入 B/臂间不等） | 40 组单测；billable=B 断言 |
| R-03 | pair 标签再次不一致 | 唯一函数 + analysis 归一 + 计数严格相等 |
| R-04 | code_sha 漂移导致旧包混入 | fail-closed + --allow-code-delta 仅 exploratory |
| R-05 | launcher 未绑定 S0-6 | 六项预检；失败不启动 |
| R-06 | B128 资源超预期 | A2 v4e 实测；4.5h 硬上限；窗口调整 |
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
| R-17 | 中文乱码/mojibake | UTF-8 显式 encoding；v4e 复核 |
| R-18 | 自动发现 report 重复加载 | 显式 report 路径；分析测试 |
| R-19 | legacy 诊断混淆 | 文档区分 LEGACY_PACKAGE/CODE_SHA_DRIFT |
| R-20 | A5 未出 verdict 即启动 | S1_RUN 门禁；Lead 书面授权 |
| R-21 | 分片失败未停 | stopping_rules；4.5h 上限 |
| R-22 | 旧 A 类剩余 6 次被误用 | 封账 CLOSED 不结转 |
| R-23 | B 类 12 次/RCAIDE 被误启动 | LOCKED/NOT_TRIGGERED；无自动回退 |
| R-24 | GitHub 越权发布 | 仅 Lead 写；A4 只读 |
| R-25 | S0-6 与 S0-5 不变量漂移 | 逐字节 tasks/split 对比；9/9 |
| R-26 | A2 v4e/B128 未完成即授权 | 阶段门；M04 未关闭不放行 |
| R-27 | 回执提前宣称放行 | 回执写 NOT_APPROVED/待 phase4b |

待决策：1) A2 B128 实测后的分片窗口与内存上限；2) A5 phase4b 对 M02/M03/M04 的最终关闭；3) Lead 授权范围（S0-6 路径/SHA256SUMS/run_id/15 片/4.5h/停跑）；4) 是否在 S1 后进入 S2（按统计门禁与成本，不在本轮）。

## 9. 读取记录

- 2026-11-06：读取 commit H（e95f9dc）、G（48403e5）、S0-6 包全部 10 文件、A5 phase4 报告与 findings CSV、Lead 947 tests 日志、R-V4-10 裁定、合同 v1.4、执行计划 v1.4、统计计划 v1.2、矩阵 v1.4。
- 未读取真实 holdout 内容；未启动 solver；未写 GitHub。

## 10. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4 | 初版 S1 矩阵（S1-01..12、A5PRE、阶段门） |
| v1.1 | 2026-11-05 | A4 | 按 R-V4-04/-05 补 merge/readiness 隔离 |
| v1.2 | 2026-11-05 | A4 | 按 task-248 同步 S0-3、A2 v4b、A3 v4b、15 分片/merge |
| v1.3 | 2026-11-06 | A4 | 按 R-V4-08/A5 phase3 同步 v4c、S0-4、867 tests |
| v1.4 | 2026-11-06 | A4 | 按 A5 phase3/S0-4 同步 390 行；A5 phase4 PENDING |
| v1.5 | 2026-11-06 | A4（task-224） | 同步 S0-6/G/H/947 tests；A5 phase4 1B/4M/5m 逐条映射；新增 §4.7；15 片窗口待 B128；S1_RUN=NOT_APPROVED；未 commit/push，0 物理 |
