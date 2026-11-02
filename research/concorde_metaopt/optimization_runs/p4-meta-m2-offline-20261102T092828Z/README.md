# P4 元学习离线实验 run：p4-meta-m2-offline-20261102T092828Z

> 阶段：P4-CODE（SYNTHETIC_ONLY）。本 run 只使用解析合成任务族与合成评估器，
> 未调用任何真实 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器，physical_call_count=0。
> 本 run 的任何数值都不得外推为真实飞机性能结论。

- status: VALID
- family: F-QE；config_hash: 0d393de6ae1d56b3c62308d977678581025f63ec74ce92c6c43201436c902f8b
- git_sha: 36d58918fc5f1002a599c45661e3cd389ce96c19；worktree_dirty=False
- seed: 42；M2 seeds: [0, 1, 2, 3, 4]
- 主终点（预注册）：meta_test K=5 query RMSE (MAML vs P, MAML vs R)
- 确定性重跑：3 次，状态 PASS

## 可行域稀疏与 null 规则（A7）

F-QE 的可行域是 12 维加权球（r~U(0.15,0.45)），体积约 1e-6；
在 64 次真实（合成）评估预算下可识别三臂预期均无可行解（克隆臂仅描述性，不参与比较）。此时
best_feasible_value / gap_to_reference / first_feasible_eval_index 如实写 null，
严禁写成 0。可识别三臂比较使用 fallback 指标：best_objective_raw（最小原始目标）、
min_constraint_violation_sum（最好目标设计的约束正违反之和）、
feasible_hit_rate（feasible_count/evaluations）。

## 可识别臂（M0 v1.4 §10.1）

P4-CODE 可识别臂集合 = {OPT-BO-rand, OPT-BO-MAML-init, OPT-DE}；预注册终点统计、图、回执与结论只引用这三臂。
OPT-BO-pretrain 与 OPT-BO-MAML 标 CLONE_OF_OPT-BO-rand（与 rand 同机制、同 8 初始点，仅元数据标签不同），只作描述性记录，禁用于代理先验归因。

## 产物文件

run_config.json / environment.json / summary.json / data_manifest.json / tasks.json /
tasks/negative_control_manifest.json / reference_solutions.json / evaluations.jsonl / solver_validation.csv /
finite_difference_check.json / README.md；
metrics/{training_history,adaptation_results,metrics,optimization_history,optimization_summary}.csv；
figures/figure_status.json（本阶段不生成图；fig1/fig2/fig3/fig5 由 A2 从 CSV 生成，fig4 归 Issue #4 D-12D-004）。

## 隔离与边界

- 物理调用守卫：启动断言 sys.modules 无真实求解器模块；评估器每次调用检查
  physical_call_count，非零立即中止并写 status=PHYSICS_GUARD_VIOLATION。
- FD 梯度门禁（§7.2）：M2 启动前在适配后参数点做中心差分检查，非 PASS 时
  整 run 中止并写 status=FINITE_DIFFERENCE_FAILED（保留 FD 原始数组）。
- 数据合同：所有样本 data_origin=SYNTHETIC_TEST、physics_validation_status=NOT_APPLICABLE。
- 负控制（label-shuffle）只用于 M1 诊断，单列、不进主终点/调参。
- archive：{'dataset_id': 'p4-meta-m2-offline-20261102T092828Z-m1', 'manifest_path': 'archive/p4-meta-m2-offline-20261102T092828Z-m1/manifest.json', 'n_samples': 21120, 'target_names': ['objective', 'geometry_invalid'], 'task_splits': {'train': 60, 'validation': 20, 'test': 30}, 'data_origin': 'SYNTHETIC_TEST', 'schema_version': 2}

评估器：synthetic__analytic__12d_lifting_surfaces__v1；实现标签：maml_opt 公开 API 复用 + 合成任务族解析真值。
