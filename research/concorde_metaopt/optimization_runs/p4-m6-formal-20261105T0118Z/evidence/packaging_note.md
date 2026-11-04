# P4-M6 正式 run 打包说明（Lead，零求解）

- run_id: p4-m6-formal-20261105T0118Z
- 打包不改变任何数值产物；仅应用 A5 task-160 指定的文档修正、嵌入 A2 图/脚本、升级 data_manifest 到 schema 2.0.0。
- 文档修正: README §5 补充 in_dist K=5 M−P 显著更差方向与 M−R 不显著（A5-M6-02）；bo_sample_efficiency 补清 M5 PENDING_M5_ACCEPTANCE（A5-M6-05）；run_config 补 determinism_reruns=3（A5-M6-04）。
- 2026-11-05 rev2（A5 task-166 的 A5-M6PKG-01..05 文档修订，doc-only）：更新本说明/README/报告文字与 data_manifest 的 excluded 字段；不重跑、不改任何数值 payload、不启动求解器。
- A5-M6-01（prereg stopping_rules 被序列化为单字符数组，malformed，pre-existing）属冻结件既有开放项，本轮不修。**summary.json 与 README.md 全文均未披露该字段**；仅在报告 §6 第 7 条（docs/reviews/p4_meta_m6_report_20261105.md）与 A5 open_findings（evidence/a5_m6_results_review.json 的 open_findings = ["A5-M6-01"]）中记录。该字段未被 M6 任何数值计算使用，不影响本 run 数值；留待下次 freeze 周期修复并加类型校验（A5-M6PKG-03）。
- A5-M6-03 属 A2 报告文字，已在报告终稿修正；A5 已按 stable_int seed 精确重放 300/300 行 CI/p/Holm。
- A5-M6PKG-04：summary.json 为 run 生成时的不可变快照，其 m5_reference.status 保留历史值 PENDING_M5_HOLDOUT；machine-readable 现行状态以 run_config.json 与 README §5 的 PENDING_M5_ACCEPTANCE 为准（不改写 summary 原始 payload）。
- 清单口径（A5-M6PKG-05）：data_manifest.json 31 条（3 张 PNG 按 raw、文本按 canonical-LF；excluded = data_manifest.json、SHA256SUMS.txt，故 run 目录共 33 文件）；SHA256SUMS.txt 为 31 条 raw sha256（LF checkout 下文本 raw == canonical-LF）。
- SHA256SUMS 口径修订说明：旧版 SHA256SUMS.txt 由 CRLF 工作树生成，其中 README.md、run_config.json、evidence/a3_m6_run_audit.json、evidence/a5_m6_results_review.json、evidence/packaging_note.md 五行为 CRLF raw 哈希；rev2 统一重建为 canonical-LF 口径（内容未改的 run_config.json、a3、a5 三行哈希因此与旧版不同，但与其 data_manifest 条目一致）。
- 图: figures/fig2_K_shot_rmse.png、fig6_ood_negative_control.png、fig7_k_sweep_delta.png（A2 300dpi 中文，sha 见 manifest）；脚本: scripts/{gen_figures_m6.py,recompute_m6.py,build_report_m6.py}。
- 报告: docs/reviews/p4_meta_m6_report_20261105.md（A2 草稿经 A5-M6-02/03/05 修正）。
- 复核: A5 task-160 APPROVE_FOR_M6_REPORTING（0/0/5 minor，verdict sha babc43356cf22059ed841c3649a4aa2b8db881799c163dd4e126f36c0806d5c8）；A3 task-161 PASS 21/21（audit sha a736a9cc4b49159bf4586c4f054a8b91ae97e58d2207bc919454abce49101f45）。
- physical_call_count = 0；本打包过程未启动任何求解器。
