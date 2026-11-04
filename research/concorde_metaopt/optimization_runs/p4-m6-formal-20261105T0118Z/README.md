# P4-M6 快速适应 harness（合成任务族，SYNTHETIC_ONLY）

## 1. 范围与边界

- run_id：p4-m6-formal-20261105T0118Z；stage：P4-CODE；数据来源：SYNTHETIC_TEST。
- 三臂：M=MAML 一阶元训练，P=监督预训练后微调，R=随机初始化；同结构、同评估预算、同 support/query。
- K ∈ [0, 1, 5, 10, 20]；评估研究：同分布（meta_test）、OOD 参数外推（meta_test_ood）、新函数族 ['F-LIN', 'F-MF']；负控制单列。
- 全部标签为解析合成真值；physical_call_count=0，未调用任何真实 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器，无网络。
- 研究规模判定：study_scale=FORMAL，conclusions_allowed=True。

## 2. 配置

- 元训练 seed：[0, 1, 2]；元训练任务数：60
- support 池：128；query：64；元训练步数：200
- 微调步数：50；确定性重跑次数：3

## 3. 结果（任务层级均值，K=5，任务内标准化 RMSE）

| study | source_family | arm | K | n_tasks | mean rmse_norm | ci_low | ci_high | null_rate | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| in_dist | F-QE-feasible-v2 | M | 5 | 20 | 1.07116 | 1.04137 | 1.10309 | 0 | VALID |
| in_dist | F-QE-feasible-v2 | P | 5 | 20 | 1.05337 | 1.0263 | 1.08232 | 0 | VALID |
| in_dist | F-QE-feasible-v2 | R | 5 | 20 | 1.09217 | 1.05993 | 1.12583 | 0 | VALID |
| ood | F-QE-feasible-v2 | M | 5 | 10 | 1.07568 | 1.03406 | 1.12244 | 0 | VALID |
| ood | F-QE-feasible-v2 | P | 5 | 10 | 1.07111 | 1.02966 | 1.11744 | 0 | VALID |
| ood | F-QE-feasible-v2 | R | 5 | 10 | 1.10335 | 1.04922 | 1.16512 | 0 | VALID |
| new_family | F-LIN | M | 5 | 20 | 1.0559 | 1.02141 | 1.0925 | 0 | VALID |
| new_family | F-LIN | P | 5 | 20 | 1.05296 | 1.02077 | 1.08881 | 0 | VALID |
| new_family | F-LIN | R | 5 | 20 | 1.07829 | 1.04599 | 1.11261 | 0 | VALID |
| new_family | F-MF | M | 5 | 20 | 1.08627 | 1.053 | 1.1228 | 0 | VALID |
| new_family | F-MF | P | 5 | 20 | 1.07262 | 1.0453 | 1.10191 | 0 | VALID |
| new_family | F-MF | R | 5 | 20 | 1.09233 | 1.05217 | 1.13561 | 0 | VALID |

## 4. OOD 诊断与负控制（不构成泛化结论）

- H1–H5 诊断总体状态：CONFOUNDED（conclusion_allowed=False）
  - H1 难度混杂（OOD 是否显著更难/更易）：CONFOUND_SUSPECTED
  - H2 context 泄漏/错位：PASS
  - H3 任务生成完整性：PASS
  - H4 抽样与泄漏：PASS
  - H5 评估尺度差异：PASS
- 负控制状态：PASS
  - NC1 label-shuffle 后 MAML 优势回落：PASS
  - NC2 K=0 随机臂最差：PASS

## 5. 三层结论（严格分离）

- surrogate_error_advantage：NO_SIGNIFICANT_ADVANTAGE —— 仅说明代理快速适应误差，不外推到 BO 样本效率或 OOD 泛化
  - 方向明细：in_dist K=5 M−P median_diff=+0.01803237774931271（MAML 误差更高），p_holm=0.012662887573242188；M−R median_diff=-0.01166786654265974，p_holm=0.17685317993164062（不显著）；未发现 MAML 优势证据。
- bo_sample_efficiency：NOT_EVALUATED_IN_M6 —— M5 holdout 已执行（p4-meta-m5-formal-20261104T1018Z），但其成果仍在修复/复核（PENDING_M5_ACCEPTANCE）；不得由 M6 K-shot 代理误差推断 BO 样本效率。
- ood_generalization：OOD_NO_SIGNIFICANT_ADVANTAGE —— 即使 OOD 不退化也不能宣布泛化成功；只有 H1-H5 通过且优势显著才可条件性表述
- 三层结论各自独立报告；禁止由 L1 推断 L2/L3，禁止把 K=5 RMSE 较低自动宣布 BO 更优

## 6. non-claims

- 真实跨任务元训练与真实低/高保真标签（需 P4-REAL-LF / P4-MULTIFIDELITY-REAL 授权）
- MAML 参数级等价性声明（backend=torch 自写一阶实现，equivalence_claimed=false）
- 由 M6 代理误差直接推断 BO 样本效率（必须引用 M5 的 holdout 统计）
- 不宣称真实飞机油耗/Mach 2.02 物理改进/真实 P4 优化；VSPAERO 结果为 NOT_RUN（归 Issue #4 D-12D-004）。

## 7. 产物与复现

- 产物文件（run 目录共 33 个 = data_manifest 31 条 + data_manifest.json + SHA256SUMS.txt；A5-M6PKG-05）：
  - 配置/记录（11）：run_config.json、environment.json、tasks.json、reference_solutions.json、meta_task_split.json、solver_validation.csv、determinism_check.json、old_m2_run_immutability.json、preflight/formal_scale_preflight.json、summary.json、README.md
  - 指标（5）：metrics/training_history.csv、metrics/adaptation_results.csv、metrics/adaptation_summary.csv、metrics/statistics.csv、metrics/metrics.csv
  - 图（5）：figures/fig2_K_shot_rmse.png、figures/fig6_ood_negative_control.png、figures/fig7_k_sweep_delta.png、figures/figure_data.json、figures/figure_status.json
  - 脚本（3）：scripts/gen_figures_m6.py、scripts/recompute_m6.py、scripts/build_report_m6.py
  - 证据（3）：evidence/a3_m6_run_audit.json、evidence/a5_m6_results_review.json、evidence/packaging_note.md
  - 门禁（4）：gate/frozen_family.json、gate/preregistration.json、gate/meta_task_split.json、gate/frozen_gate.json
  - 清单：data_manifest.json（schema 2.0.0，31 条；excluded = data_manifest.json、SHA256SUMS.txt）、SHA256SUMS.txt（31 条 raw sha256）
  - 未随包的 A2 外部产物：figures_manifest.json、recompute.json、recompute.md、probe*.py（属 A2 交付目录，不纳入本 run 包；A5-M6PKG-02）
- 确定性：determinism_reruns=3，比较时排除列：wall_s
- 正式复现命令（A5M6R-02：--frozen-run-dir 为必填，缺省会 fail-closed）：
  cd <repo> && D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m research.concorde_metaopt.meta_learning.m6_study
  --run-id p4-m6-formal-20261105T0118Z --output-root <OUT> --frozen-run-dir research\concorde_metaopt\optimization_runs\p4-meta-m5-formal-20261104T1018Z --old-run-output-root research\concorde_metaopt\optimization_runs --ks 0,1,5,10,20 --meta-seeds 0,1,2 --determinism-reruns 3
- 正式规模 dry-run（零真值评价、不写 run 产物，只写 preflight/formal_scale_preflight.json）：
  ... 同上命令行追加 --preflight-only

## 8. 状态

- summary.status = VALID；physical_call_count = 0
- 状态口径（A5-M6PKG-04）：summary.json 为 run 生成时的不可变快照，其 m5_reference.status 保留历史值 PENDING_M5_HOLDOUT；machine-readable 现行状态以 run_config.json 与本 README §5 的 PENDING_M5_ACCEPTANCE 为准。
