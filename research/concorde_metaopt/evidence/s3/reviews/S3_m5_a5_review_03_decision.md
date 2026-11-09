# S3-M5 独立复核（第 3 步）：从 aggregate + CSV 独立复算结论

- 日期：2026-11-09（UTC）
- 审查者：A5（a5-code-reviewer）
- 对象：S3 formal run p4ra-s3-formal-20261109T1310Z 的官方 analysis 与 Lead 记录 S3_M4_ANALYSIS_RECORD.json
- 输入哈希（只读）：
  - aggregate.json：164,295 B，sha256 27bb5f17c4650dab5b20228abad1b0f82507f017d66918676b608dd15f3fca94
  - s3_per_task_endpoint_values.csv：36,153 B，sha256 7de822fe43de8f959419608a5abef08182c0b8b1a885d6a8ef11203bfea255e4
  - s3_holm_family.csv：sha256 aab407dd56388f6272a03ec8578599093ce19f347822d6f85c1c8f29b0974150
  - s3_endpoint_tables.csv：sha256 08c9d0529641461fcb21a1530a2471e462b73d24b16de58377257a6d68031eb4
  - s3_negative_controls.csv：1,612 B，sha256 07a439a653043fc54a31b1925e4df75eaed201f6b19fc34c7720ea58eacc8198
  - s3_ood_descriptives.csv：588 B，sha256 61d349e8eefefbca4a726a575a4ef3d64b993aedec6a127a5a1122a428e07eec
  - s3_cost_table.csv：984 B，sha256 3c331882dc6c6248424ed74f2fba725a1e38917557aafca1a8456e829ceff261
  - Lead 记录：16,090 B，sha256 61a9fc9f3b9bf1102e8f285914569c44a0525a4606a14237dc534e987177b6fc
- 独立复跑：A5 自己的 a5_launcher.py，显式开启 verify_analysis_plan_digest / verify_code_sha / verify_record_digests，并对 review_01 的 P1/P2/P3 做等价修复；输出 analysis_rerun_a5/，status=PASS、overall_decision=NO_EVIDENCE、c1/c2 decisions 全 NULL、record_counts eval=362,880/train=0。官方 7 个核心 CSV 与 A5 复跑逐字节相同（见 compare_vs_lead.json）；aggregate 的非易变差异仅为图状态/图数据（A5 未生成图）和 P1 注入键。

## 1. 总体判定：NO_EVIDENCE 成立

官方 aggregate.overall_decision=NO_EVIDENCE。独立核对：
- holm_rows 4 行（C1b B64、C1a B128、C2b B64、C2a B128）全部 reject=false、decision=NULL；
- inference.c1_decisions={B64:NULL,B128:NULL}、c2_decisions 同；
- 独立脚本从 s3_per_task_endpoint_values.csv 重算四个检验的 p_raw、p_holm、效应、CI、n_eff，aggregate_mismatches=[]，全部与 aggregate 精确一致（recompute_stats.json）。
- 因此，C1/C2 均未达到预注册显著性，主结论 NO_EVIDENCE 可复现。

## 2. C1 / C2 关键数值（独立重算）

| 检验 | 预算 | effect | 95% CI | p_raw | p_holm | n_eff / n | decision |
|---|---|---:|---|---:|---:|---:|---|
| C1 feasible_hit_rate | 64 | +0.009635416666666664 | [-0.0014583333333333284, 0.02151041666666666] | 0.1785125732421875 | 0.357025146484375 | 19 / 20 | NULL |
| C1 feasible_hit_rate | 128 | +0.0033593749999999978 | [-0.0033339843750000205, 0.010234374999999967] | 0.43577003479003906 | 0.43577003479003906 | 20 / 20 | NULL |
| C2 gap_to_reference | 64 | -0.011233867492171538 | [-0.014384482303944438, 0.006972196318877517] | 0.8408222198486328 | 1.0 | 20 / 20 | NULL |
| C2 gap_to_reference | 128 | +0.002654621142214754 | [-0.0017178974779196797, 0.0027917714450128917] | 0.7982521057128906 | 1.0 | 19 / 20 | NULL |

- Holm 族结构：每个 endpoint 一个族（2 个预算成员），family_size=2；C1/C2 四个检验的 p_holm 分别为 0.357025、0.435770、1.0、1.0，全部大于 0.05，reject=false。
- n_eff 最低 19（C1 B64 与 C2 B128），均 >=15；C1 B64 n_zero=1、C2 B128 n_zero=1；无 >70% null 的情况，null_disclosure 未触发 INCONCLUSIVE 条款。
- C1 B64 的效应为正但 CI 跨 0；C1 B128 效应接近 0；C2 两个预算方向不一致且 CI 跨 0。结论 NULL 与数据一致。

## 3. ANIL_INCONCLUSIVE 复核

- 官方 anil_audit.decision=ANIL_INCONCLUSIVE；
- ANIL hit rate mean 0.8123697916666666，RANDOM 0.8077343750000001，差值 +0.00463541666666665；
- CI [-0.00554687499999999, 0.015078124999999998] 跨 0；非劣边界 margin=0.02；cost_ratio=1.0，cost_ratio_max=0.75；
- 独立重算的分预算均值：ANIL B64 0.7922916666666666、RANDOM B64 0.7866666666666666；ANIL B128 0.8324479166666666、RANDOM B128 0.8288020833333333；与官方均值一致（recompute_stats.json）；
- 因此 ANIL 既不显著优于 RANDOM，也不满足成本比上限，ANIL_INCONCLUSIVE 成立。需要注意：cost_ratio=1.0 是 adaptation_cost 的预算比，不是真实运行成本比（见第 5 节），但这不改变 ANIL 未显示优势的结论。

## 4. 图状态与理由核对

官方 figure_status.json（3,700 B，sha256 868f93d242c56f8f9a10a9e934d90162ada02e961367ef50241e4147e2c52da7）summary：6 RENDERED、4 NOT_RUN。
- fig1 NOT_RUN：reason train record 缺失，无法绘制训练损失；record_counts.train=0，与产物一致，理由成立。
- fig2 NOT_RUN：reason S3 记录不含 K-shot 适配曲线（K 属于 {0,1,3,5}）；主记录无该曲线，理由成立。
- fig10 NOT_RUN：reason 未找到只读 VSPAERO 门禁归档；S3 run 目录无该归档，理由可接受（不涉及 S3 合成实验结论）。
- fig7 NOT_RUN：reason run 产物不含 OOD 段（OOD 分析 NOT_RUN）；该理由为假，见第 6 节。s3_ood_descriptives.csv 的全部 10 行也使用该理由并给 NOT_RUN，属于错误披露。

## 5. 成本表与 ANIL cost_ratio 的解读缺陷

- s3_cost_table.csv 10 行全部 total_cost_mean_s=0、total_cost_median_s=0、adaptation_cost_mean 等于 64 或 128；
- 原因：s3_runner.py:1035 每条记录 wall_s=0.0；s3_runner.py:2065 与 run_config.scope_notes 明确 per-record wall_s 未逐点计时（统一 0.0）；run 级墙钟与峰值见 execution_report.json 与 run_summary.per_run；
- s3_analysis.py:4115-4116 的 endpoint 定义 total_cost=wall_s、adaptation_cost=wall_s+打分次数，所以 total_cost 恒 0、adaptation_cost 恒等于 budget；
- s3_analysis.py:4432-4447 直接汇总这些零值；s3_analysis.py:4473-4474 的 ANIL cost 使用 adaptation_cost，:4492 得 cost_ratio=1.0（B64/B128 相同），实际是预算比而非运行成本比；
- execution_report 显示 campaign_wall_s=2941.921272、max_run_wall_s=13.290802、sum_run_wall_seconds=22759.797742，说明运行墙钟存在，但没有进入成本表；分析器应把该成本标为 NOT_AVAILABLE 或改用 run 级墙钟，而不是输出 0 并继续算 ratio。
- 该缺陷不改变 C1/C2/ANIL 的推断结论，但使 fig5 与成本表不可用于解释成本效率；Lead 记录未对此给出 NOT_AVAILABLE 标注，属分析产物缺陷。

## 6. OOD：官方 NOT_RUN 与 raw 记录直接矛盾（blocker）

### 6.1 事实

- run 目录存在 ood_records.jsonl：22,430,606 B，sha256 e8372903b82e5a2730bdc3b557d5d367d3ebe5d90b5d1d1d204be4415f2539ba；28,800 行、300 runs、10 tasks，split=meta_test_ood、phase=OOD、source=support；
- aggregate.checks 同时有：
  - record_stream_ood PASS: OOD 记录流: 300 runs/28800 records；
  - ood_artifacts DISCLOSED: run 产物不含 OOD 段，OOD 描述性对比记 NOT_RUN；
- 官方 S3_M4_ANALYSIS_RECORD.json 也记录 record_counts_by_stream.ood={runs:300,records:28800,status_counts:{OK:28800,FAILED:0}}，同时 figure_reasons.fig7 写 run 产物不含 OOD 段；
- 因此，官方对 OOD 的不存在/未运行陈述与自身 checks、record_counts、raw 文件三者矛盾。

### 6.2 代码根因

- s3_analysis.py:4038 的 per_run=tuple(eval_records) 中 eval_records 只来自主 run_records.jsonl；
- s3_analysis.py:4069 的 compute_run_endpoints 只遍历 run.per_run；
- s3_analysis.py:4601-4606 的 build_ood_rows 只从传入的 endpoints 里找 split==meta_test_ood；找不到就写 ood_artifacts DISCLOSED 并返回 10 行 NOT_RUN；它从不读取 run.record_streams.ood 或 ood_records.jsonl；
- 结果：OOD 文件虽然被加载并通过 checks，但永远不会进入 OOD 端点/描述性表。Lead 记录的 OOD 分析 NOT_RUN 是分析器 bug 的产物，不是真实数据缺失。

### 6.3 独立复算（仅描述性，不做推断）

A5 直接读取 ood_records.jsonl，按 (task,budget,arm) 平均 seed 后，10 个 OOD task 的 feasible_hit_rate_mean：
- B64：RANDOM 0.7869791666666667、FOMAML-OBJ 0.79375、FOMAML-CON 0.7848958333333333、ANIL 0.7828125、DE 0.4213541666666667；
- B128：RANDOM 0.8229166666666666、FOMAML-OBJ 0.8268229166666667、FOMAML-CON 0.8151041666666666、ANIL 0.8221354166666667、DE 0.6052083333333333；
- CON-OBJ：B64 -0.008854166666666673、B128 -0.011718749999999967。
OOD 是预注册的描述性分析，不是确认性检验；但数据不存在的陈述是错误的，且 fig7/描述性表因此缺失。该缺陷不改变 C1/C2 主结论，却直接违反 Lead 记录与 fig7 理由，属于必须修正的 blocker。

## 7. 负控 NC-15：未计算，不是 PASS（major）

- prereg negative_controls 的 suspicious_rule：打乱后 CON-OBJ 差异 >= 真实差异的 50% 判 NEGATIVE_CONTROL_SUSPICIOUS；
- negative_control_summary.json（1,680 B，sha256 1a17774d5fa310c86f909b0063aaa8a1e58d3cb9ec37cf581ed9952e96d7d038）只有 executed/groups/records/physical_call_count/schema_version/suspicious_groups，没有 shuffled_con_minus_obj_feasible_hit_rate 等比较字段；
- s3_analysis.py:4573-4587 的 NC-15 从 summary 找 3 个键，找不到就把 NC-15 标 DISCLOSED；negative_controls.csv 的 NC-15 行 status=DISCLOSED，不是 PASS；
- A5 从 negative_control_records.jsonl（23,153,628 B，sha256 117b46cbde79be6952723e52786c85cb8aec15f6587398fbe37f6f93b9d539a6）独立算 10 个 NC task 的 CON-OBJ：B64 +0.016145833333333325、B128 +0.009895833333333316；主 20 task 的真实值 B64 +0.009635416666666664、B128 +0.0033593749999999978；绝对值比为 1.6757 / 2.9457，合并为 2.0040（> 50%）。但 NC task 与主 20 task 交集为 0，且 prereg 未定义跨 task 集的正式比较规则，因此不能直接把该比值当作 prereg 判定；可以确定的是：NC-15 没有被正式计算，summary 缺字段，DISCLOSED 不应被报告为负控通过。
- 对主结论的影响：负控未通过/未计算会削弱无假阳性的保证；但 C1/C2 本身就是 NULL，结论保守，故定为 major 而非 blocker（OOD 的错误事实陈述才是 blocker）。

## 8. 与 Lead 记录的一致性

- 一致项：overall NO_EVIDENCE；C1/C2 全 NULL；四个 p 值/CI/effect/n_eff；ANIL_INCONCLUSIVE；record_counts eval=362,880/train=0；figure_status 6/4；S3_M4_ANALYSIS_RECORD 的 outputs 22 项 bytes/sha 全部与磁盘一致；7 个核心 CSV 与 A5 独立复跑逐字节相同。
- 不一致项（均为本 review 的 finding）：
  1) OOD：Lead 记录 fig7/ood_descriptives 称 run 产物不含 OOD 段，实际有 28,800 条 OOD 记录（A5-S3M5-01，blocker）；
  2) NC-15：官方标 DISCLOSED，但 Lead 记录的整体 status=PASS 只表示分析器运行成功，不能替代 NC-15 的通过/未通过结论；记录与报告均未披露“NC-15 未计算”（A5-S3M5-02，major）；
  3) 成本表：官方给出全 0 成本并计算 cost_ratio，Lead 记录未标 NOT_AVAILABLE（A5-S3M5-03，major）。
- 因此：统计结论本身可复现，但分析产物不能按现状作为 S3 结果回执；verdict=CHANGES_REQUESTED。

## 9. 复跑命令与证据

- <PYTHON_EXE> a5_launcher.py（workdir EXT/p4-route-a/a5/s3_m5），EXIT=0，输出 analysis_rerun_a5/，a5_run_summary.json 844 B；
- <PYTHON_EXE> recompute_stats.py，EXIT=0，输出 recompute_stats.json（aggregate_mismatches=[]）；
- <PYTHON_EXE> nc15_final.py，EXIT=0，输出 nc15_final.json；
- <PYTHON_EXE> verify_outputs.py，EXIT=0，22/22 项 bytes/sha 一致；
- <PYTHON_EXE> probe_patch_negative.py，14 个场景，结果见 review_02；
- 官方 7 CSV 与 A5 产物对比见 analysis_rerun_a5/compare_vs_lead.json（7/7 equal）。
