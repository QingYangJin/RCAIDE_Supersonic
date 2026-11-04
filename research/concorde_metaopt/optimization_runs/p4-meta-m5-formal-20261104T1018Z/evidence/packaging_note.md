# M5 正式 run（attempt2）打包说明（Lead，零求解）

- run_id: p4-meta-m5-formal-20261104T1018Z
- 本说明记录提交前打包步骤，不改变任何 run 数值产物；data_manifest.json 升级为 schema 2.0.0（text canonical-LF、PNG raw、excluded 字段）。
- attempt 历史: attempt1 因 A5-M5-01（first_feasible 端点列名/映射缺陷）、A5-M5-02（clone_audit reference/budget 空）、A5-M5-07（determinism 无逐 pass digest）判定缺陷，已归档至 EXT/.../m5_formal_attempt1_defective/（27 文件/243,445,932 B）；修复提交 7e94973（A5 task-158 APPROVE_FOR_HOLDOUT_RERUN、A3 task-159 PASS）后以同一 run_id 干净重跑 attempt2。
- 外部化: metrics/optimization_history.csv 移至 D:/RCAIDE/outputs/concorde_metaopt/p4-meta-m5-formal-20261104T1018Z/raw_artifacts（gitignored、仓库外）；raw sha256/bytes 记录在 data_manifest.json external_artifacts。
- 打包新增（均非 solver 产物）: figures/fig1,fig3,fig4,fig5 PNG（A2 生成、300 dpi 中文、scripts/gen_figures_m5.py）；scripts/gen_figures_m5.py 与 scripts/build_report_m5.py；evidence/packaging_note.md、evidence/a5_m5_results_review.json、evidence/a3_m5_run_audit.json、evidence/a2_status_final.json；SHA256SUMS.txt。
- 报告: docs/reviews/p4_meta_m5_report_20261104.md（rev5 定稿；A5 task-175 曾判 CHANGES_REQUESTED（1 minor A5-M5A2-04），rev5 修复后 A5 task-177 判 APPROVE_FOR_M5_PACKAGING（0/0/0）；报告 sha256 见 evidence/a2_status_final.json；注意 data_manifest.json 仅覆盖本 run 目录 35 个文件，不含 docs 报告与 4 张图）。
- 本说明对应打包修订 rev2（A5 task-179 findings A5-M5PKG-01/02/03）：仅改文档/证据文本，run 数值产物与统计结果不变。
- determinism: status PASS（3 pass / 300 组 / mismatch 0），但 raw_digest_manifest=NOT_STORED（逐 pass 原始 digest 未随包保存，不可独立复算；summary/README 如实披露）。
- 已知冻结件缺陷: preregistration.json 的 stopping_rules 因 feasible_v2.STOPPING_RULES 为多行字符串、list() 序列化为单字符数组（A5-M5-04）；不影响端点/预算/种子/统计，留待下次 freeze 修复，本次如实披露。
- README.md: 产物清单在打包时由 Lead 补充（新增 PNG/scripts/evidence/SHA256SUMS 与外置文件标记），仅文档文本，数值内容未改。
- 已知残留: summary.json 为 run 生成时不可变快照；A5-M5-04 等披露以本说明与报告为准。
- 物理调用: 0；本打包过程未启动任何求解器；未联网。
