# S3-M5 A5 独立结果复核（汇总）

- 任务：task-264（rev6），S3-M5 独立结果复核；对象 run p4ra-s3-formal-20261109T1310Z；只读，0 仓库写、0 GitHub 写、0 物理求解、未重跑正式 run。
- 审查者：A5（a5-code-reviewer，独立会话）。
- 日期：2026-11-09（UTC）。
- 结论：verdict = CHANGES_REQUESTED；1 blocker / 2 major / 3 minor。
- 统计主结论：NO_EVIDENCE 可复现；C1/C2 全部 NULL；ANIL_INCONCLUSIVE 成立。问题不在确认性统计数值，而在分析产物的完整性/披露：OOD 被错误标 NOT_RUN、NC-15 未计算、成本表不可用。

## 1. 交付与对象

交付目录：<STATE_ROOT>/EXT/p4-route-a/a5/s3_m5/

- review_01_defects.md（已存在，5,623 B）：静态复现 3 个分析器缺陷；
- review_02_patch.md：Lead 补丁 fail-closed 审查；
- review_03_decision.md：aggregate + CSV 独立复算与结论核对；
- review.md（本文件）、verdict.json、findings_s3_m5.csv、commands.log、SHA256SUMS.txt。

只读输入：
- 官方 analysis：<STATE_ROOT>/s3_analysis/p4ra-s3-formal-20261109T1310Z/（aggregate.json 164,295 B sha 27bb5f17…、7 CSV、figure_status.json、6 PNG+6 data CSV）；
- Lead 记录：<STATE_ROOT>/p4-route-a/lead/s3/S3_M4_ANALYSIS_RECORD.json（16,090 B sha 61a9fc9f…）；
- Lead 补丁：.../lead/s3/run_s3_analysis_leadpatched.py（6,990 B sha a3aac137…）与 .../s3_analysis/p4ra-s3-formal-20261109T1310Z.leadpatch_audit.json（6,499 B sha 39ea855b…）；
- 正式 run：.../s3_runs/p4ra-s3-formal-20261109T1310Z/（run_config 11,273 B sha 0a4ec865…、execution_report 1,142 B sha e70a5a5a…、ood_records 22,430,606 B sha e8372903…、negative_control_records 23,153,628 B sha 117b46cb…）；
- prereg：<REPO_ROOT>/research/concorde_metaopt/evidence/s3/s3_preregistration.json（34,308 B sha 192dd36a…）；
- 代码：<REPO_ROOT>/research/concorde_metaopt/meta_learning/{s3_analysis.py,s3_prereg.py,s3_runner.py}（HEAD 691f554 clean）。

## 2. 独立验证摘要

1. 自己的 launcher：a5_launcher.py 显式开启 verify_analysis_plan_digest、verify_code_sha、verify_record_digests，并对 review_01 的 P1/P2/P3 做等价修复；EXIT=0，status=PASS，overall_decision=NO_EVIDENCE，c1/c2 全 NULL，record_counts eval=362,880/train=0。
2. 7 个核心 CSV 与官方逐字节相同（cost/endpoint/holm/negative_controls/null_disclosure/ood_descriptives/per_task）；aggregate 的非易变差异仅为图状态/图数据（A5 未生成图）和 P1 注入键。
3. 从 s3_per_task_endpoint_values.csv 独立重算四个检验：p_raw/p_holm/effect/CI/n_eff 全部与 aggregate 精确一致，aggregate_mismatches=[]。
4. 22 项官方 outputs 的 bytes/sha256 与磁盘全部一致（verify_outputs.py：22/22）。
5. 独立读取 OOD 与负控 raw 记录，得到下述 findings。
6. 补丁负控 14 个场景：核心模型 SHA 篡改与 record_digest 实质字段篡改均 fail-closed；bytes/额外字段、SMOKE、P1 未覆盖。

## 3. Findings

### Blocker

A5-S3M5-01：OOD 被错误标为 NOT_RUN/数据不存在。
- 事实：ood_records.jsonl 存在且为 22,430,606 B、sha e8372903…、28,800 行/300 runs/10 tasks；aggregate 自身 record_stream_ood PASS 300/28800，record_counts_by_stream.ood OK=28800；但 ood_artifacts 与 fig7/ood_descriptives 的理由写“run 产物不含 OOD 段”。
- 根因：s3_analysis.py:4038/4069 只消费主 run 的 per_run；:4601-4606 的 build_ood_rows 只从 endpoints 找 OOD，从不读 ood_records.jsonl。
- 影响：Lead 记录与 fig7 的事实陈述错误，预注册的 OOD 描述性分析未交付；不改变 C1/C2 的 NO_EVIDENCE，但使产物不能按现状作为 S3 结果回执。

### Major

A5-S3M5-02：NC-15 未计算，DISCLOSED 不是 PASS。
- negative_control_summary.json 缺 prereg 要求的 shuffled_con_minus_obj 等字段；s3_analysis.py:4573-4587 找不到就标 DISCLOSED。
- A5 从 raw NC 记录算 CON-OBJ：B64 +0.0161458333、B128 +0.0098958333；主 real：+0.0096354167、+0.0033593750；绝对值比 1.6757/2.9457（合并 2.0040）。但 NC task 与主 20 task 无交集，不能把该比值当作 prereg 的正式判定；可确定的是负控没有被正式计算，summary/记录未如实说“未计算”。

A5-S3M5-03：成本表全 0，ANIL cost_ratio 不是运行成本比。
- s3_runner.py:1035 记录 wall_s=0.0；s3_runner.py:2065 与 run_config.scope_notes 已披露 per-record wall 未计时；execution_report 有 campaign_wall_s 2941.921272、max_run_wall_s 13.290802、sum_run_wall_seconds 22759.797742。
- s3_analysis.py:4115-4116/4432-4447/4473-4492 直接汇总零值并把 adaptation_cost（=budget）当成本，得 total_cost=0、cost_ratio=1.0；fig5/成本表无法解释成本效率。应标 NOT_AVAILABLE 或改用 run 级墙钟。

### Minor

A5-S3M5-04：官方未复算 analysis_plan_digest（只做格式校验），Lead 补丁也未加 --verify-analysis-plan-digest；A5 独立显式复跑通过，原始 digest 31ac71d7… 正确，注入后 d5b2ac24… 不等。
A5-S3M5-05：Lead 补丁仅 FORMAL 生效；prereg 模型 bytes/额外字段未绑定；补丁审计未记录 verify_code_sha/verify_record_digests/plan digest 开关。
A5-S3M5-06：官方 aggregate 与 S3_M4_ANALYSIS_RECORD 的 prereg.endpoints 仍含注入的 comparator/c1_tests/c2_tests 三键（P1 现场证据）；不影响已复算的 C1/C2 数值，但污染 provenance。

## 4. 结论与建议

- 统计层面：NO_EVIDENCE 成立，C1/C2 全 NULL、ANIL_INCONCLUSIVE，A5 独立复跑与官方 7 CSV 逐字节一致；没有发现确认性数值被篡改。
- 产物层面：不能按现状签发 S3 结果回执。最低修复要求：
  1) 修复 build_ood_rows/compute_run_endpoints，让 OOD 记录真正进入描述性分析，或明确声明 OOD 分析未实现并撤回“数据不存在”的理由；
  2) 实现 NC-15 正式计算（或明确 NOT_COMPUTED 并在记录/报告中披露），不能用 DISCLOSED 冒充通过；
  3) 成本表改为 run 级墙钟或 NOT_AVAILABLE，ANIL cost_ratio 不得用预算比冒充运行成本比；
  4) 修复 P1 的 endpoints 注入，FORMAL 默认复算 plan digest，并补齐补丁审计的校验开关；
  5) 重新生成 aggregate/CSV/图并重新提交独立复核。
- 未做：未改仓库、未重跑正式 run、未做物理求解、未做 GitHub 写操作；未复跑 180s W8 pilot（本任务对象是 S3 formal 分析，非 M2 冻结门）。
