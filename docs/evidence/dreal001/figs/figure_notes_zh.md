# R10 六臂图/表说明（中文）— A4 本地补充证据集

> **SIX_ARM_PILOT_NOT_COMPLETED / E1–E6 NOT_COMPUTABLE — NO PERFORMANCE DATA**

- 包 ID：A4-P2AV2-R10-FINAL-20261111；生成时间（UTC）：2026-11-11T20:14:06Z
- 数据源：A3 r10_stats_20261111.{md,json,csv}（tool a3-r10-descriptive-stats-v1.0.0，生成 2026-11-11T19:30:03Z，commit 699ce2a）+ R10 run dir 受治理文件 + R1–R10 approval/stop；全部文件 SHA256/bytes 实算断言（fail-closed）
- 判定：六臂 pilot NOT_COMPLETED；E1–E6 全部 NOT_COMPUTABLE；R10 为协议 D 科学自动停，不是优化结果。

## 全局披露（12 条）

- D-01 PILOT_NOT_COMPLETED：六臂 pilot 未完成：BO COMPLETED、DE STOPPED_SCIENTIFIC_INVALID_RATIO，其余 4 臂 NOT_RUN。
- D-02 NO_PERFORMANCE_DATA：E1–E6 六臂端点全部 NOT_COMPUTABLE；本包不呈现任何性能/增益/收敛结论。
- D-03 SINGLE_SEED：仅 seed=42 单次运行，无重复、无置信区间、无显著性检验。
- D-04 NO_WINNER_RANKING：不宣布 winner/排名/显著性；不比较 BO 与 DE 的优劣。
- D-05 NO_CROSS_FAMILY_POOLING：f1/f2 为不同族标签槽位，禁止跨族合并/比较；族槽统计仅作槽位描述。
- D-06 FUEL_BURN_NULL：fuel_burn_kg=null（未测量）。
- D-07 PHYSICS_NOT_VALIDATED：EXTERNAL_PHYSICS_SUPPORTED=NOT_VALIDATED（R10 未取得外部物理验证）。
- D-08 R1_R10_EXCLUDED：R1–R10 永远排除出 E1–E6 端点；R10 为科学自动停，非优化结果。
- D-09 A5_AUDIT_AND_RECEIPT_DELIVERED：A5 R10 post-run 独立审计已签发（audit v2 commit 9ac700427ba92283894d147cc862ef7850d5dc77；md 09444da3… / 18,698 B；JSON 85/85 PASS）；签署最终回执 A5-P2A-V2-R10-FINAL-RECEIPT-20261111（commit 964a451a0b43c037e5a64f0c81a006a27eaa7058；md af33d084… / 17,238 B；json 7bfdb45f…）。本包为 A4 本地补充证据集，不并入回执、不作 Issue #9 正文图号。
- D-10 A4_ZERO_PHYSICAL：A4 physical_call_count=0；本包全程未启动任何真实 VSPAERO/solver。
- D-11 NO_ISSUE9_FIG_NUMBERS：本包不并入 A5 签署回执，不作为 Issue #9 回执正文图号。
- D-12 CHARGE_VS_ACTUAL：448/3,148 为 charged_projected（含计划预留），153/1,083 为 physical_actual；不得混同。

## 图 1 — fig1_objective_distribution_trajectory

- 文件：figures/fig1_objective_distribution_trajectory.png / .pdf
- 内容：A 面板 BO/DE 的 per-design primary 分布（strip + box，n=23/12）；B/C 面板 BO（32/32）与 DE（16/32，右删失）的 primary 散点与 best-so-far 描述性轨迹；× 标注 INVALID_NUMERICAL 槽位。
- 视觉编码：箱线为 min–max 须（whis=(0,100)），中位线黑色；BO/DE 颜色仅作组成员区分，不表示优劣；同一 y 轴便于诚实展示重叠，不构成臂间比较。
- 关键数字（描述性）：BO n=23 median=0.01622804 IQR=0.00561393；DE n=12 median=0.01532678 IQR=0.00574188；BO best=0.010006880012（design_index 4 / c50a5bc80b15ada0，描述性非 winner）；DE best=0.012894807420（design_index 2 / eb00b7ad545243e6，描述性非 winner）。
- 禁止解读：把 best-so-far 说成收敛/增益；比较 BO 与 DE 优劣；跨族合并 CDi。预算不等（32 vs 16）且单 seed。

## 图 2 — fig2_validity_and_invalid_reasons

- 文件：figures/fig2_validity_and_invalid_reasons.png / .pdf
- 内容：A 有效（SOLVED_VALID）/无效（LIFT_MATCH_FAILED、SOLVER_FAILED）堆叠计数；B 无效评估的 starts 分布（starts=1 fail-fast vs starts=2）。
- 关键数字：BO 32 evals / 23 valid / 9 invalid（LIFT 4 + SOLVER 5）；DE 16 / 12 / 4（LIFT 2 + SOLVER 2）；13 invalid 合计；7 行 fail-fast（starts=1）→ main starts 89 = 2×48 − 7，internal 623 = 7×89。
- 禁止解读：有效率高不等于优化性能好；PSO/ABO/ADE/APSO 为 NOT_RUN，不能据此排序。

## 图 3 — fig3_endpoint_availability_e1_e6

- 文件：figures/fig3_endpoint_availability_e1_e6.png / .pdf
- 内容：E1–E6 × 六臂 + 六臂 overall 的端点状态矩阵（D=描述性可算、D*=部分/右删失、D@B=at-budget 描述性、NC=NOT_COMPUTABLE、N/R=NOT_RUN、NC-6ARM=六臂端点不可计算）。
- 判定：六臂 E1–E6 全局 NOT_COMPUTABLE；BO E1/E2/E4 为描述性可算（单 seed、预算/删失限制），DE E1 为部分描述性、E2/E4 受右删失限制；E3/E5/E6 全不可计算。
- 禁止解读：任何 D/D*/D@B 都不是可发表端点结论，不得用于 winner/显著性/跨族比较。

## 图 4 — fig4_accounting_two_bases

- 文件：figures/fig4_accounting_two_bases.png / .pdf
- 内容：A starts、B internal cases 的 charged_projected 448/3,148（含 R10 计划预留）vs physical_actual 153/1,083（真实消耗），caps 451/3,157；C 累计分解（前序 62/446 + R10 计划 386/2,702 或实际 91/637）。
- 关键数字：charged 余量 3/9；physical 余量 298/2,074；R10 实际 91/637 = preflight 2/14 + diagnostics 0/0 + main 89/623。
- 禁止解读：448/3,148 不是实际消耗（L-15）；不得把计划预留计入物理预算陈述。

## 图 5 — fig5_preflight_byte_identity

- 文件：figures/fig5_preflight_byte_identity.png / .pdf
- 内容：R1–R10 × PRE-01/PRE-02 的 preflight 字节证据矩阵：MATCH/PASS_BYTE、MATCH/NO_JSON、MATCH/VERDICT_FAIL、NO_OUTPUT/FAIL、N/R（未达 preflight）。
- 关键数字：期望 polar SHA 455082e2…（PRE-01）/ 0287afe0…（PRE-02），各 7,933 B；R2 字节 MATCH 但判定词 FAIL（状态词缺陷）；R3/R4/R6 字节 MATCH 但未落 preflight_result.json；R5/R8 setup 即停、未达 preflight。
- 判定：R7/R9/R10 三案 preflight PASS_BYTE（方法层回放链路验证），但 main 求解循环未验证；不得据此宣称物理验证。

## 图 6 — fig6_r1r10_timeline

- 文件：figures/fig6_r1r10_timeline.png / .pdf
- 内容：R1–R10 每轮 approval（▲）→ 首次 solver attempt（●）→ 停止（■，按阶段着色）时间线（UTC）；治理事件 L-07/L-08/L-14/L-15 虚线；R1–R6 组 11/77、R7–R10 组 103/721。
- 关键数字：R1 preflight 06:08:32Z；R2 07:44:48Z；R3 08:53:55Z；R4 09:55:20Z；R5 10:38:28Z；R6 11:21:48Z；R7 15:50:23Z；R8 17:14:11Z；R9 18:02:45Z；R10 19:13:55Z。
- 判定：R1–R10 全部事故/非结果，永久排除出 E1–E6；R10 科学自动停后无 R11（L-14）。

## 表 1–6

- tables/table1_r1r10_attempt_ledger.csv：R1–R10 尝试台账（approval/stop SHA+bytes、窗口、停止 phase/时间、starts/internal、原因、preflight 类别、排除说明）；含 PRE_R1、R1_R10_SUBTOTAL、双口径累计行。
- tables/table2_six_arm_status.csv：六臂状态（BO COMPLETED / DE STOPPED / 其余 NOT_RUN）、有效/无效、starts/internal、invalid 原因、note。
- tables/table3_objective_descriptive_stats.csv：overall 与 f1/f2 槽位的描述统计（n/min/Q1/median/Q3/max/IQR/mean/sd）；槽位统计禁跨族比较。
- tables/table4_endpoint_availability_e1_e6.csv：E1–E6 × 六臂 + overall 原始状态与 reason。
- tables/table5_accounting_two_bases.csv：prior/planned/actual/charged/physical/caps/headroom 双口径记账与语义。
- tables/table6_preflight_byte_evidence.csv：逐轮逐案 expected/actual polar SHA+bytes、byte_match、preflight_result SHA/overall/case_status、证据类别。

## 来源文件清单（SHA256 / bytes 已实算校验）

- r10_stats_20261111.md：0728ccae856d913cfc2ff6984e2e32d05cfd2413345693eab0a983ffeec526eb（17707 B）
- r10_stats_20261111.json：5705269ba2bb7015f703fb2c9bb24da2f300bda0e7c2d83848a369e8d562daf9（72881 B）
- r10_stats_20261111.csv：007e1a9b22fa1f16223bb5fc257990ac0c742830344b504c1beccca791b1c3df（95286 B）
- dreal001_lead_decision_r10_scientific_stop_20261111.md：e13435d3f16eb5ac0d33c19681f99dcf595e56a4ab521382fdfd8e2e350ea395（4966 B）
- dreal001_lead_decision_r10_scientific_stop_20261111.json：3391996b4406ace288f5ac344263fa86e48e75059d659d10f41d9428826ba1c9（2886 B）
- dreal001_lead_decision_r10_accounting_two_bases_20261111.md：1c76a34d95db8c29e92e53bcde6d023181f42b4b9a0010434be06fa83e3f7976（2819 B）
- dreal001_lead_decision_r10_accounting_two_bases_20261111.json：fcd950ed326bf47f0e1bf3b9ef33263503d6bd1f1fcae6ddb50b92a70e200c8c（1974 B）
- a2_r10_scientific_auto_stop_20261111T1913Z.md：fc0e81ef273b4c272359ba72002ff229199002b649a139c9b8fd6321a15f671f（12243 B）
- r10_arm_invalid_decomposition_20261111T1913Z.json：080c12904e4ad43476d22ce8bedf046d098c6f10de3a48e37c097a240a597f52（6500 B）
- R10 run dir：DREAL001-P2A2R10-20261111-01（9 个受治理文件：evaluations.jsonl / batch_summary.json / final_run_manifest.json / solver_attempts.jsonl / preflight_result.json / diagnostics.json / stop_report.json / plan.json / approval.json；SHA 见 data_sources.json）
- R1–R10 approval.json / stop_report.json / solver_attempts.jsonl：SHA/bytes 见 data_sources.json 与 table1。

## A4 自检与边界

- A4 physical_call_count=0；全程未启动真实 VSPAERO/solver，未改 A2/A3/A5 工作树，未 push。
- 本包为 A4 本地补充证据集，不并入 A5 签署回执、不作为 Issue #9 回执正文图号；A5 R10 审计+回执已签发（AUDIT_AND_RECEIPT_DELIVERED）：audit v2 commit 9ac7004（md 09444da3… / 18,698 B，JSON 85/85 PASS）、回执 A5-P2A-V2-R10-FINAL-RECEIPT-20261111 commit 964a451（md af33d084… / 17,238 B）。
- 所有图/表仅描述 A3 统计与 run dir 证据状态；fuel_burn_kg=null；EXTERNAL_PHYSICS_SUPPORTED=NOT_VALIDATED。
