# D-NEXT-001 A5 独立复核审计输出（只读归档 replay）

- 审计 ID：A5-DNEXT001-VERIFY-20261110T061305Z
- 生成时间（UTC）：2026-11-10T06:13:05Z
- 复核角色：A5_INDEPENDENT_REVIEW（仅审查，不实现被审算法、不自审自改）
- S3 证据根：D:\RCAIDE-s3-dev
- 下游工作树根：D:\RCAIDE\dnext001
- 证据模式：ARCHIVE_REPLAY_READ_ONLY
- physical_call_count = 0（全部为 mock/合成/归档只读，未启动任何物理求解器）
- solver_processes_started = 0
- 总判定：NOT_RUN
- 状态计数：VALID=10，NOT_VALIDATED=0，NOT_RUN=2，FAIL=0
- 规则：不得以提交消息代替复现；未审阅的提交不签 PASS；缺失/外置证据只能 NOT_RUN。

## 检查明细

| 检查 | 名称 | 状态 | 严重度 | 说明 |
| --- | --- | --- | --- | --- |
| A5-C01 | package_integrity | VALID | blocker | 证据包可全量重算：LF-canonical 口径 77/77 全等；raw 字节 58/77 相等；CRLF 19 件与 manifest eol_summary 一致；manifest 计数 77 件/5228512 B 自洽。 |
| A5-C02 | physical_zero | VALID | blocker | 全部可见产物的 physical_call_count / solver_processes_started 均为 0。 |
| A5-C03 | F01_validator_path | VALID | major | 缺陷可静态复现：模型清单校验块未拼接 S3_EVIDENCE_ROOT_RELPATH 前缀；row.path=models/fomaml_meta_0.json 在 repo_root 下不可解析、在 evidence/s3 下可解析 => 合法 run 会得到 validation_ok=false（fail-closed 位置错误）。 |
| A5-C04 | F02_model_aggregate | VALID | major | 口径差异已定位且可归一：原始聚合 sha 两侧不同（per-kind 均 differ），但去掉 bytes 并把 path 归一为 models/<kind>_meta_<seed>.json 后，归一化聚合 sha 与 run 侧逐 kind 精确相等；6 个逐模型 sha 与磁盘模型文件 sha 全部一致 => 判定为比较器口径缺陷，非数据篡改。 |
| A5-C05 | F03_ood | VALID | major | 冻结分析器 build_ood_rows 只按 endpoints.split=='meta_test_ood' 过滤、从不读取 run 的独立 OOD 记录流，故 s3_ood_descriptives.csv 全行 NOT_RUN；侧车 ood_supplementary_descriptives.csv 有 100 行可与磁盘 28,800 条 OOD 记录对账，且 analysis_disclosures 已登记 A5-S3M5-01。结论：正式 OOD 分析 = NOT_RUN，侧车仅描述性。 |
| A5-C06 | wall_s_cost | VALID | major | ANIL 成本审计不可解释：逐点 wall_s 恒为 0.0（静态命中），s3_cost_table.csv 10 行 total_cost_median_s 全为 0，adaptation_cost_mean 恒等于预算（64/128），ANIL cost_ratio=1.0 仅反映预算比而非计算成本；ANIL_COST_EFFICIENT（cost_ratio<=0.75）判据因此不可审计 => NOT_VALIDATED。 |
| A5-C07 | NC15_keys | VALID | major | NC-15 不可计算已核实：negative_control_summary.json 缺 shuffled_con_minus_obj_feasible_hit_rate, shuffled_con_minus_obj, con_minus_obj_shuffled 三键，冻结分析器据此标 DISCLOSED 而非计算；负控 10 组 28,800 条中仅 S3-DE B64=0.448958 明显偏离（已披露，未修剪）；侧车复算为独立描述，不产生 p/CI/decision。 |
| A5-C08 | figures | VALID | minor | 10 图状态为 RENDERED 6 / NOT_RUN 4；4 张缺数据面板已逐张给出 reason；6 张 PNG 全部在位（cjk_font=Microsoft YaHei）。 |
| A5-C09 | endpoint_arithmetic | VALID | major | 独立重算 4 条检验：C1 effect=mean_difference、C2 effect=mean_difference//OBJ 臂均值/、CI 含点估计、p_holm>=p_raw、overall=NO_EVIDENCE 与逐检验决策（NULL）一致，Holm rank 连续。 |
| A5-C10 | determinism | NOT_RUN | major | 确定性口径字段齐备（排除 wall_s/peak_memory_mb/record_digest），3 次重跑 record_core_sha256=645e9f9c471269be…；但 6 个 externalized 记录流不在本机，无法按原始记录流独立重算 => 记录级确定性 NOT_RUN（仅登记声明）。 |
| A5-C11 | gate_chain | VALID | blocker | 门禁链替代已被记录为偏离：S3-GOV-01=DEVIATION，A5 M2R 无最终 verdict 落盘（reviews 下 a5_m2r verdict 0 件、a7_m2r verdict 0 件），M3 由 A7 M2R=APPROVE_FOR_S3_RUN 替代放行；A3 覆盖仅到 691f554（S3-M0-05 PARTIAL）；A5 仅有 M5 分析复核 verdict（['S3_m5_a5_verdict.json']）、A7 仅有 M4 复核 verdict（['S3_m4_a7_verdict.json']）。结论：任务合法执行，但门禁完整性 = NOT_VALIDATED，须由负责人裁定补签或记入 S4 前置。 |
| A5-C12 | downstream_products | NOT_RUN | info | A1–A4 工作树均无可审产物（无 receipt / TaskSpec 合同）；M0 门禁只能出待审条件清单，状态 NOT_RUN。 |

## 关键度量

### A5-C01 package_integrity（VALID）

- metrics: {"bytes_raw_total": 5228512, "crlf_declared": 19, "mismatch": 0, "mismatched": [], "missing_files": 0, "sha256_lf_match": 77, "sha256_raw_match": 58, "sums_entries": 77}
- 证据：research\concorde_metaopt\evidence\s3\SHA256SUMS.txt
- 证据：research\concorde_metaopt\evidence\s3\PACKAGE_MANIFEST.json

### A5-C02 physical_zero（VALID）

- metrics: {"absent": {}, "counters": {"figure_summary.physical_call_count": 0, "negative_control_summary.physical_call_count": 0, "package_manifest.physical_call_count": 0, "package_manifest.solver_processes_started": 0, "run_config.physical_call_count": 0}, "nonzero": {}}
- 证据：research\concorde_metaopt\evidence\s3\PACKAGE_MANIFEST.json
- 证据：research\concorde_metaopt\evidence\s3\run\run_config.json

### A5-C03 F01_validator_path（VALID）

- metrics: {"block_has_prefix": false, "prefix_constant_defined": true, "resolves_against_evidence_root": true, "resolves_against_repo_root": false, "row_path": "models/fomaml_meta_0.json"}
- 证据：research/concorde_metaopt/meta_learning/s3_runner.py:2527-2531
- 证据：research\concorde_metaopt\evidence\s3\run\model_manifest.json

### A5-C04 F02_model_aggregate（VALID）

- metrics: {"kinds": {"anil": {"aggregates_differ": true, "model_file_sha_equal": true, "normalized_equals_run": true, "per_model_sha_equal": true, "prereg_aggregate": "3dfe78a318ad1ea983b1ad573ddee3660bc2afaec1154bd1756c21d8856b5d52", "prereg_aggregate_normalized": "9b421cce88db4d27bad876a0b019d1c7b4c9e43d20acc7dde27f807e5777d8ff", "prereg_aggregate_raw": "3dfe78a318ad1ea983b1ad573ddee3660bc2afaec1154bd1756c21d8856b5d52", "run_aggregate": "9b421cce88db4d27bad876a0b019d1c7b4c9e43d20acc7dde27f807e5777d8ff"}, "fomaml": {"aggregates_differ": true, "model_file_sha_equal": true, "normalized_equals_run": true, "per_model_sha_equal": true, "prereg_aggregate": "731a699872b0e8d0d42d3833abb5705bc894b1c092fdc92fe86591f368294a8d", "prereg_aggregate_normalized": "e90a05c5234e82f0e9052c6726811264aa8043299746f3c13d30ba965a306336", "prereg_aggregate_raw": "731a699872b0e8d0d42d3833abb5705bc894b1c092fdc92fe86591f368294a8d", "run_aggregate": "e90a05c5234e82f0e9052c6726811264aa8043299746f3c13d30ba965a306336"}}, "model_file_sha_equal": true, "per_model_sha_equal": true}
- 证据：research/concorde_metaopt/meta_learning/s3_runner.py:1635-1661
- 证据：research\concorde_metaopt\evidence\s3\s3_preregistration.json
- 证据：research\concorde_metaopt\evidence\s3\run\run_config.json

### A5-C05 F03_ood（VALID）

- metrics: {"build_ood_rows_reads_run_stream": false, "descriptive_statuses": ["NOT_RUN"], "disclosure_A5_S3M5_01": true, "filters_meta_test_ood": true, "supplementary_rows": 100}
- 证据：research/concorde_metaopt/meta_learning/s3_analysis.py:4601-4606
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\analysis\s3_ood_descriptives.csv
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\analysis\ood_supplementary_descriptives.csv

### A5-C06 wall_s_cost（VALID）

- metrics: {"adaptation_equals_budget": true, "anil_cost_ratio": 1.0, "disclosure_A5_S3M5_03": true, "rows": 10, "runner_wall_s_zero_literal": true, "total_cost_zero_rows": 10}
- 证据：research/concorde_metaopt/meta_learning/s3_runner.py:1035
- 证据：research/concorde_metaopt/meta_learning/s3_analysis.py:4113-4116
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\analysis\s3_cost_table.csv

### A5-C07 NC15_keys（VALID）

- metrics: {"de_b64_rate": 0.44895833333333335, "disclosure_present": true, "missing_keys": ["shuffled_con_minus_obj_feasible_hit_rate", "shuffled_con_minus_obj", "con_minus_obj_shuffled"], "records": 28800}
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\run\negative_control_summary.json
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\analysis\s3_negative_controls.csv

### A5-C08 figures（VALID）

- metrics: {"cjk_font": "Microsoft YaHei", "not_run": ["fig10_vspaero_gate_status", "fig1_training_loss_and_full_meta_grad", "fig2_kshot_rmse_k0_k1_k3_k5", "fig7_ood_diagnostics"], "png_missing": [], "rendered": ["fig3_feasible_hit_rate_by_arm", "fig4_best_feasible_and_first_feasible", "fig5_fomaml_vs_full_vs_anil_cost", "fig6_task_family_diagnostics", "fig8_negative_controls", "fig9_determinism_and_budget"], "total": 10}
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\analysis\figure_status.json
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\analysis\figure_generation_summary.json

### A5-C09 endpoint_arithmetic（VALID）

- metrics: {"alpha": 0.05, "decisions": ["NULL"], "n_tests": 4, "overall_decision": "NO_EVIDENCE", "problems": [], "tests": [{"budget": 64, "ci": [-0.0014583333333333284, 0.02151041666666666], "decision": "NULL", "effect": 0.009635416666666664, "family": "s3-feasible-hit-2tests", "n_eff": 19, "n_paired": 20, "p_holm": 0.357025146484375, "p_raw": 0.1785125732421875, "test_id": "C1b"}, {"budget": 128, "ci": [-0.0033339843750000205, 0.010234374999999967], "decision": "NULL", "effect": 0.0033593749999999978, "family": "s3-feasible-hit-2tests", "n_eff": 20, "n_paired": 20, "p_holm": 0.43577003479003906, "p_raw": 0.43577003479003906, "test_id": "C1a"}, {"budget": 64, "ci": [-0.014384482303944438, 0.006972196318877517], "decision": "NULL", "effect": -0.011233867492171538, "family": "s3-gap-to-ref-2tests", "n_eff": 20, "n_paired": 20, "p_holm": 1.0, "p_raw": 0.8408222198486328, "test_id": "C2b"}, {"budget": 128, "ci": [-0.0017178974779196797, 0.0027917714450128917], "decision": "NULL", "effect": 0.002654621142214754, "family": "s3-gap-to-ref-2tests", "n_eff": 19, "n_paired": 20, "p_holm": 1.0, "p_raw": 0.7982521057128906, "test_id": "C2a"}]}
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\analysis\aggregate.json
- 证据：research\concorde_metaopt\evidence\s3\s3_preregistration.json

### A5-C10 determinism（NOT_RUN）

- metrics: {"core_equal_across_reruns": true, "excluded_fields": ["peak_memory_mb", "record_digest", "wall_s"], "external_streams_local": 0, "external_streams_missing": 6, "record_core_sha256": ["645e9f9c471269be37a8d219a88a1d9154824ba5458f1dbfbfc80b423315d4d8", "645e9f9c471269be37a8d219a88a1d9154824ba5458f1dbfbfc80b423315d4d8", "645e9f9c471269be37a8d219a88a1d9154824ba5458f1dbfbfc80b423315d4d8"], "reruns": 3, "subset_run_keys_sha256": "0704a23ead63533f3659148b1167c6a81063089724e0015f3b9b1c43ec78ae5c"}
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\run\determinism_check.json
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\run\data_manifest.json

### A5-C11 gate_chain（VALID）

- metrics: {"a3_coverage_partial": true, "a5_m2r_not_recorded": true, "a5_m2r_verdict_files": [], "a5_m5_verdict_files": ["S3_m5_a5_verdict.json"], "a7_m2r_verdict_files": [], "a7_m4_verdict_files": ["S3_m4_a7_verdict.json"], "deviation_recorded": true}
- 证据：docs\reviews\p4_route_a_s3_requirement_matrix.md
- 证据：D:\RCAIDE-s3-dev\research\concorde_metaopt\evidence\s3\reviews

### A5-C12 downstream_products（NOT_RUN）

- metrics: {"roles": {"a1": {"candidate_docs": [], "exists": true, "worktree": "D:\\RCAIDE\\dnext001\\wt-a1"}, "a2": {"candidate_docs": [], "exists": true, "worktree": "D:\\RCAIDE\\dnext001\\wt-a2"}, "a3": {"candidate_docs": [], "exists": true, "worktree": "D:\\RCAIDE\\dnext001\\wt-a3"}, "a4": {"candidate_docs": [], "exists": true, "worktree": "D:\\RCAIDE\\dnext001\\wt-a4"}}}
- 证据：D:\RCAIDE\dnext001

## 结论边界

- 本输出只覆盖归档证据的只读复核；原始记录流外置（run_records.jsonl 等不在本机）时，记录级重算标 NOT_RUN。
- 侧车/描述性产物不得升级为 p 值、CI 或阶段放行结论。
- 任何 PASS 结论必须由本脚本断言可复现或由具名复核人另附独立 verdict；提交消息、执行人自述均不构成 PASS 依据。

