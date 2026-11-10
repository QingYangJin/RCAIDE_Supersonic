# 任务回执：A5 独立复核（task-5 / D-NEXT-001）

- 角色：A5（独立科学/代码审查；未实现、未修改被审算法；未写 A1–A4 工作树）
- 工作树：D:\RCAIDE\dnext001\wt-a5
- 分支：research/dnext001-a5-review
- 本轮主提交：fd29903 [D-NEXT-001] review(A5): S3 defect audit + M0 pending checklist + A/B/GPU replay protocol + read-only audit script/tests
- 基线：ea8ad97833eb5ceab291faae643c141a2b219749（= S3 封账 c7221fb + 计划文档）
- 共享任务：task-5（已 claim，完成后置 completed）
- physical_call_count = 0；solver_processes_started = 0；全部为 mock/合成/归档只读 replay

## 1. 交付物清单

| 文件 | 说明 |
| --- | --- |
| docs/reviews/dnext001_a5_s3_defect_audit_20261110.md | S3 缺陷专项审计清单（F-01/F-02/F-03、wall_s=0、NC-15/侧车、4/10 图 NOT_RUN、A5 M2R 被 A7 替代、A3 崩溃/隔离缺口 + 追加发现 F-04/record_digest/时间戳/launcher/记录级确定性），每条含证据路径+commit、复现方法、严重度、整改门槛 G1–G8、fail-closed 判据 |
| docs/reviews/dnext001_a5_m0_gate_review_20261110.md | M0 门禁与物理口径独立评审：A1 CG/质量/TaskSpec 合同最低条件 C-M0-01…10、PASS/CHANGES_REQUESTED/FAIL 判据、预启动检查 P0–P7；因 A1 产物不存在，当前状态 NOT_RUN（待审条件清单 v1） |
| docs/reviews/dnext001_a5_ab_gpu_replay_protocol_20261110.md | A/B/GPU 独立复核协议：独立重放定义、种子校验、公平性 F-1…F-9、FP32 容差表、二阶梯度门禁、后端≠方法边界、复核 receipt 字段；当前 NOT_RUN（产物不存在） |
| docs/reviews/dnext001_a5_sample_audit_output_20261110.json | 示例审计输出（机器可读，12 项检查：VALID 10 / NOT_RUN 2 / FAIL 0，overall=NOT_RUN） |
| docs/reviews/dnext001_a5_sample_audit_output_20261110.md | 示例审计输出的中文可读版（含每条检查的度量与证据路径） |
| research/concorde_metaopt/reviews/a5_audit/a5_audit.py | 只读复核脚本（纯 stdlib：hashlib/json/csv/argparse；检查 A5-C01…C12；不写被审树；退出码 0/2/3） |
| research/concorde_metaopt/reviews/a5_audit/test_a5_audit.py | 脚本单测 11 项（合成证据包构造、篡改检测、CRLF 口径、图状态、缺失证据不升级 PASS 等） |

## 2. 实际运行的测试命令与结果

1) 单测：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/reviews/a5_audit -q
   结果：11 passed in 0.20s

2) 审计脚本实跑（对 S3 归档只读）：
   & D:\RCAIDE\envs\RCAIDE\python.exe research\concorde_metaopt\reviews\a5_audit\a5_audit.py --s3-root D:\RCAIDE-s3-dev --dnext-root D:\RCAIDE\dnext001 --out docs\reviews\dnext001_a5_sample_audit_output_20261110.json --md docs\reviews\dnext001_a5_sample_audit_output_20261110.md
   结果：overall=NOT_RUN；counts = VALID 10 / NOT_VALIDATED 0 / NOT_RUN 2 / FAIL 0

3) 关键独立重算结果（脚本输出）：
   - C01 证据包：SHA256SUMS 77 行，LF-canonical 口径 77/77 全等；raw 58/77；CRLF 19 件与 PACKAGE_MANIFEST.eol_summary 一致；manifest 77 件 / 5,228,512 B 自洽。
   - C02 physical=0：PACKAGE_MANIFEST、run_config、figure_summary、negative_control_summary 全部 0。
   - C03 F-01：校验块无 S3_EVIDENCE_ROOT_RELPATH 前缀；models/fomaml_meta_0.json 仅在 evidence/s3 下可解析 => 合法 run 得 validation_ok=false（缺陷确认）。
   - C04 F-02：去 bytes + 路径归一后聚合 sha 与 run 侧逐 kind 相等；6/6 逐模型 sha 与磁盘一致 => 口径缺陷，非篡改。
   - C05 F-03：build_ood_rows 不读 run.record_streams.ood；正式 OOD 全 NOT_RUN；侧车 100 行仅描述。
   - C06 成本：cost_table 10 行 total 全 0、adaptation=budget；ANIL cost_ratio=1.0 vs max 0.75 => 不可审计。
   - C07 NC-15：缺三键，DISCLOSED 而非计算；S3-DE B64=0.448958 异常已披露。
   - C08 图：6 RENDERED / 4 NOT_RUN，6 张 PNG 在位，cjk_font=Microsoft YaHei。
   - C09 端点：C1 effect=mean_difference、C2 effect=mean_difference/|OBJ 臂均值|、CI 含点估计、p_holm>=p_raw、overall=NO_EVIDENCE 与 4 检验 NULL 一致、Holm rank 按族连续。
   - C10 确定性：3 次重跑 record_core 均为 645e9f9c…；但 6 个外置记录流不在本机 => 记录级 NOT_RUN。
   - C11 门禁链：S3-GOV-01=DEVIATION 已记录；reviews 下 a5_m2r / a7_m2r verdict 均 0 件；仅有 a5 M5、a7 M4 verdict => 门禁完整性 NOT_VALIDATED。
   - C12 下游产物：wt-a1…wt-a4 均无可审 receipt/TaskSpec => NOT_RUN。

## 3. 未完成项与风险

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 原始记录流级重算 | NOT_RUN | 8 件外置记录流（合计 312,310,937 B）不在本机，只登记声明；确定性/端点数值只能从归档聚合重算 |
| A1 M0 合同实审 | NOT_RUN | A1 产物不存在，仅出待审条件清单；需 A1 交付后再签字 |
| A2/A3/A4 复核 | NOT_RUN | 三条线尚无产物，协议已就绪 |
| A3 进程级隔离结论 | NOT_RUN | A3 崩溃，本机无法重放；仅以计划文档 + 需求矩阵 L63/L64 为证据 |
| A5 M2R 补签 | 待负责人裁定 | 缺陷已登记为 S3-GOV-01 DEVIATION；A5 不自行补签历史门 |
| 侧车与正式产物边界 | 已披露 | 侧车 label=LEAD_AUXILIARY_NOT_FROM_FROZEN_ANALYZER，不得升级为 p/CI/decision |

风险：
- F-01/F-02 若不在 S4 前修复，任何"validate 通过"表述都不可采信；建议作为零物理前置 G1/G2。
- 若 S4 计划把 A7 M2R 当作 A5 M2R 引用，将构成门禁虚假陈述（G7 fail-closed）。
- 本机缺失外置记录流，若需记录级复核必须先把归档搬到可复核位置。

## 4. 结论标注汇总

- S3 缺陷清单：F-01/F-02/F-03/成本/NC-15/图/门禁替代/A3 缺口 = VALID（缺陷已复现）；记录级确定性 = NOT_RUN；A1–A4 复核 = NOT_RUN。
- M0：NOT_RUN（待审条件清单 v1，未签 PASS）。
- A/B/GPU 协议：就绪，执行状态 NOT_RUN。
- 未替任何未审阅提交签 PASS；未用提交消息代替复现。

## 5. 声明

- physical_call_count = 0；未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag；未修改 S1/S2/S3 冻结产物与其它工作树；未 push、未合并 main。
- receipt 路径：docs/receipts/dnext001/a5-review_task_receipt.md
