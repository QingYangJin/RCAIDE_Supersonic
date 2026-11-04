# P4-M5 holdout 离线合成实验（P4-CODE）

## 范围（scope）

- 数据来源：SYNTHETIC_ONLY（解析任务族 F-QE-feasible-v2 + 12D 设计空间解析 evaluator）。
- 物理调用：physical_call_count=0（fail-closed：任何非 0 立即中止整次 run）。
- 未调用 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器，未访问网络。
- 只在 calibration -> freeze -> holdout 四方门禁一致后才评估 meta_test/meta_test_ood；
  meta_test 不参与任何超参/早停/任务选择。

## 配置（config）

- run_id：p4-meta-m5-formal-20261104T1018Z
- study_scale：FORMAL；conclusions_allowed：True
- 任务族：F-QE-feasible-v2（radius_base=0.75，参考解 u*=c，gap=f(u_best)-f(u*)）
- split：{'meta_test': 20, 'meta_test_ood': 10, 'meta_train': 60, 'meta_validation': 20, 'negative_control': 10}
- 预算：[64, 128]；优化 seeds：[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]；元训练 seeds：[0, 1, 2]
- 评估 split：meta_test 与 meta_test_ood（OOD 单列，不参与调参）
- workers：16；确定性重复 pass：3
- evaluator_id：synthetic__analytic__12d_lifting_surfaces__v2
- 门禁：UNLOCKED
- 冻结指纹：frozen_family=5e7a9d1f2acd32a482195d0ae6255205310d4d5cf4bb38562e05265c4c9da20b
- 预注册指纹：4f8a9a1fd05f0648646da58dc669524de81c2c11c38b81d72f28b0be42e565fe

## 结果（results）

- status：VALID
- 组数：300；runs：4800；真实（合成）评价：460800；历史行：460800
- runtime_s：8960.326668500085
- 确定性：PASS（mismatch=0）
- 可识别性：IDENTIFIABLE；clone_arms=[]
- 公平性审计：PASS

### 主终点描述统计（任务层级聚合中位数）

| split | budget | arm | best_feasible_value | gap_to_reference | first_feasible_evaluation_index | feasible_hit_rate |
| --- | --- | --- | --- | --- | --- | --- |
| meta_test | 64 | M5-BO-MAML-init | 0.385637 | 0.380871 | 37.3583 | 0.0575521 |
| meta_test | 64 | M5-BO-pretrain-init | 0.401901 | 0.357879 | 38.1167 | 0.0572917 |
| meta_test | 64 | M5-BO-random | 0.415765 | 0.341975 | 36.2778 | 0.0757812 |
| meta_test | 64 | M5-DE | 0.54976 | 0.526455 | 47.5 | 0.0164063 |
| meta_test | 128 | M5-BO-MAML-init | 0.271768 | 0.286921 | 40.9167 | 0.13099 |
| meta_test | 128 | M5-BO-pretrain-init | 0.268673 | 0.286347 | 43.9667 | 0.129557 |
| meta_test | 128 | M5-BO-random | 0.270027 | 0.270362 | 39.9 | 0.14375 |
| meta_test | 128 | M5-DE | 0.28571 | 0.327058 | 69.5 | 0.230859 |
| meta_test_ood | 64 | M5-BO-MAML-init | 0.675897 | 0.300096 | 46.1083 | 0.0046875 |
| meta_test_ood | 64 | M5-BO-pretrain-init | 0.674923 | 0.301227 | 43.1857 | 0.00442708 |
| meta_test_ood | 64 | M5-BO-random | 0.646544 | 0.302997 | 44.8889 | 0.00546875 |
| meta_test_ood | 64 | M5-DE | 0.755719 | 0.380273 | 45.75 | 0.0015625 |
| meta_test_ood | 128 | M5-BO-MAML-init | 0.576588 | 0.252263 | 72.4167 | 0.0114583 |
| meta_test_ood | 128 | M5-BO-pretrain-init | 0.579618 | 0.254163 | 72.4119 | 0.0110677 |
| meta_test_ood | 128 | M5-BO-random | 0.572469 | 0.255812 | 67.1875 | 0.0121094 |
| meta_test_ood | 128 | M5-DE | 0.465456 | 0.208299 | 85.875 | 0.0671875 |

### null 披露（不可行/失败保留 null，不写 0）

| 端点 | n_runs | n_null | null_rate |
| --- | --- | --- | --- |
| best_feasible_value | 4800 | 1252 | 0.2608333333333333 |
| gap_to_reference | 4800 | 1252 | 0.2608333333333333 |
| first_feasible_evaluation_index | 4800 | 1252 | 0.2608333333333333 |
| feasible_hit_rate | 4800 | 0 | 0.0 |
| best_objective_raw | 4800 | 0 | 0.0 |
| min_constraint_violation_sum | 4800 | 0 | 0.0 |
| true_evals_used | 4800 | 0 | 0.0 |
| cache_hits | 4800 | 0 | 0.0 |
| wall_s | 4800 | 0 | 0.0 |
| n_failed_evals | 4800 | 0 | 0.0 |

### fallback 指标口径

- best_objective_raw / min_constraint_violation_sum / feasible_hit_rate 仅是 fallback 描述量：无可行解时主终点保留 null 并披露比例，禁止以非可行 raw objective 宣称约束优化更优。

## 非声明（non-claims）

- SYNTHETIC_ONLY：合成解析任务，不代表真实飞机/CFD 性能；physical_call_count=0；旧 F-QE 压力测试结果单独成表，不与 v2 混算绝对目标。

## 产物

- old_m2_run_immutability.json
- run_config.json
- environment.json
- tasks.json
- reference_solutions.json
- meta_task_split.json
- frozen_family.json
- preregistration.json
- solver_validation.csv
- metrics/training_history.csv
- metrics/optimization_history.csv（打包时外置到仓库外输出目录，仓库内不含该文件；raw sha256/bytes 见 data_manifest.json external_artifacts）
- metrics/optimization_summary.csv
- metrics/metrics.csv
- metrics/statistics.csv
- metrics/endpoint_summary.csv
- metrics/arm_audit.csv
- metrics/clone_audit.csv
- metrics/adaptation_results.csv
- figures/figure_data.json
- figures/figure_status.json
- README.md
- summary.json
- data_manifest.json

### 打包新增（Lead，非 solver 产物）

- figures/fig1_meta_training_loss.png（A2 生成，300 dpi 中文）
- figures/fig3_feasible_rate.png（A2 生成，300 dpi 中文）
- figures/fig4_equal_budget_gap.png（A2 生成，300 dpi 中文）
- figures/fig5_fairness_audit.png（A2 生成，300 dpi 中文）
- scripts/gen_figures_m5.py（图生成脚本，A2）
- scripts/build_report_m5.py（报告生成脚本，A2）
- evidence/packaging_note.md（打包说明与披露）
- evidence/a5_m5_results_review.json（A5 结果复核证据）
- evidence/a3_m5_run_audit.json（A3 run 审计证据）
- evidence/a2_status_final.json（A2 定稿状态）
- SHA256SUMS.txt（canonical-LF / raw 口径校验和；data_manifest.json 与 SHA256SUMS.txt 不在 manifest 的 35 条内）

- 图状态：{'fig1_meta_training_loss': 'DATA_READY', 'fig2_k_shot_adaptation': 'NOT_APPLICABLE_THIS_STAGE', 'fig3_feasible_rate': 'DATA_READY', 'fig4_equal_budget_gap': 'DATA_READY', 'fig5_fairness_audit': 'DATA_READY', 'fig6_airframe_gate_progress': 'NOT_RUN'}
- 本阶段只落盘图数据（figure_data.json）与状态（figure_status.json）；PNG 由 A2/M5 报告阶段从 CSV 生成。fig2 归 M6；fig6 归 Issue #4 D-12D-004，缺失图一律记 NOT_RUN/NOT_APPLICABLE，禁止假图。

## 复现命令

- D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m research.concorde_metaopt.meta_learning.m5_runner --stage calibration --run-id p4-meta-m5-formal-20261104T1018Z --output-root research/concorde_metaopt/optimization_runs
- D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m research.concorde_metaopt.meta_learning.m5_runner --stage freeze --run-id p4-meta-m5-formal-20261104T1018Z --output-root research/concorde_metaopt/optimization_runs
- D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m research.concorde_metaopt.meta_learning.m5_runner --stage holdout --run-id p4-meta-m5-formal-20261104T1018Z --output-root research/concorde_metaopt/optimization_runs
