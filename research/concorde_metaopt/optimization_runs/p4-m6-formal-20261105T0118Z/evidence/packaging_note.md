# P4-M6 正式 run 打包说明（Lead，零求解）

- run_id: p4-m6-formal-20261105T0118Z
- 打包不改变任何数值产物；仅应用 A5 task-160 指定的文档修正、嵌入 A2 图/脚本、升级 data_manifest 到 schema 2.0.0。
- 文档修正: README §5 补充 in_dist K=5 M−P 显著更差方向与 M−R 不显著（A5-M6-02）；bo_sample_efficiency 补清 M5 PENDING_M5_ACCEPTANCE（A5-M6-05）；run_config 补 determinism_reruns=3（A5-M6-04）。
- A5-M6-01（prereg stopping_rules 序列化缺陷）属冻结件，本轮不修；已在 summary/README 与 A5 findings 中披露，留待下次 freeze 周期修复序列化并加类型校验。
- A5-M6-03 属 A2 报告文字，已在报告终稿修正；A5 已按 stable_int seed 精确重放 300/300 行 CI/p/Holm。
- 图: figures/fig2_K_shot_rmse.png、fig6_ood_negative_control.png、fig7_k_sweep_delta.png（A2 300dpi 中文，sha 见 manifest）；脚本: scripts/{gen_figures_m6.py,recompute_m6.py,build_report_m6.py}。
- 报告: docs/reviews/p4_meta_m6_report_20261105.md（A2 草稿经 A5-M6-02/03/05 修正）。
- 复核: A5 task-160 APPROVE_FOR_M6_REPORTING（0/0/5 minor，verdict sha babc43356cf22059ed841c3649a4aa2b8db881799c163dd4e126f36c0806d5c8）；A3 task-161 PASS 21/21（audit sha a736a9cc4b49159bf4586c4f054a8b91ae97e58d2207bc919454abce49101f45）。
- physical_call_count = 0；本打包过程未启动任何求解器。
