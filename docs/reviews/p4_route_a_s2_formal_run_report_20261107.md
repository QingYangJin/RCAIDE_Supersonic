# S2 正式 Run 报告（P4 路线A · Full MAML vs FOMAML）

- 报告版本：rev1（2026-11-06T18:2xZ，Asia/Shanghai 2026-11-07 02:2x）
- 执行者：a2-run-opt（A2）
- 授权：S2-FORMAL-AUTH-20261106T1805Z（Lead，2026-11-06T18:05:56Z）
- run_id：s2-formal-20261106T1810Z
- run 状态：COMPLETED（run_mode=FORMAL）
- 证据范围：DEVELOPMENT_VALIDATION_ONLY（仅 meta_validation 20 任务；holdout 行 0 读取）
- 产物根：EXT/p4-route-a/a2/s2_formal/
- 路径约定（repo-ready 副本）：EXT=项目外记忆目录；source-repo=源仓库检出；worktree=本次使用的干净 worktree；其余路径为仓库相对路径；本副本不含机器绝对路径。
- 本报告所有数字均来自该根目录下产物；每项尽量给出文件与字段/行号口径。

---

## 0. 摘要

1. S2 正式 run 一次性完成：状态 COMPLETED，6000 条记录（训练 1200 + 评估 4800），0 失败记录，physical_call_count=0，无 RESOURCE_LIMIT、无重试。
2. 确定性：按 prereg 要求额外串行重跑 2 次（同一 run_id、同一 created_utc、不同 out_dir），base/r1/r2 的 run_config 字节一致（3/3 sha256=9522d467...），run_records_core_sha256 一致（3/3 c9460dae...），episode_bank/fd_gate/data_manifest 摘要一致；两次 compare 均 ok=true。
3. FD gate：32 个坐标全部 PASS（0 FAIL），最大相对误差 1.14476e-09，容差 1e-06；micro/full_size pilot 证据 PASS。
4. 分析：status=PASS，9/9 图 RENDERED，0 NOT_RUN；强推断端点仅 C1 的 k5（主）与 k10（次），唯一 Holm 族 family_size=2。
5. 主结论：总体 SUPPORTED_HARM。主终点 post_adaptation_rmse_raw_k5 上 FULL_MAML 显著劣于 FOMAML：task 配对中位差 +0.031324，相对恶化 -3.394%，Holm p=3.8147e-06，95% bootstrap CI [0.041109, 0.059870] 排除 0；次要推断端点 k10 同向 SUPPORTED_HARM（中位差 +0.014501，相对 -1.619%，CI [0.007324, 0.011702]）。该结论仅限 meta_validation 开发集，不涉及 holdout，不可外推到真实气动优化。
6. 资源：单 (arm,meta_seed) 训练墙钟最大 3.7138 s（限额 1200 s，占用 0.31%）；单 arm 峰值内存最大 261.57 MB（限额 8192 MB，占用 3.19%）；wrapper 总墙钟 101.57 s（总限额 7200 s）；run 内部 base run_wall_s=25.6769 s。
7. 披露：A5-S2PR-01（prereg 校验器未实际使用 S0-7 冻结包 physical 字段；当前事实 physical=0，非阻断）与 OBS-01（S2 holdout 口径 40 比 S0-7 的 30 更严格）均在 §11 明示。

---

## 1. 授权与绑定（逐项实测）

| 项目 | 值 | 证据 |
|---|---|---|
| 授权 ID | S2-FORMAL-AUTH-20261106T1805Z | EXT/p4-route-a/lead/S2_FORMAL_RUN_AUTHORIZATION.md |
| 签发/执行者 | Lead / a2-run-opt | 同上 |
| 源分支与提交 | research/p4-route-a-s2 @ 994cda8e0942060072d65eb50dde790c44d32194（父 f4ab43f） | 同上 |
| 执行 worktree | worktree（detached @994cda8e...），工作树 clean | git rev-parse HEAD；git status --porcelain 为空（run 前后均验证） |
| 计划 | docs/planning/p4_route_a_s2_execution_plan_20261106.md（v1.6a） | 授权文件 |
| prereg 文件 | research/concorde_metaopt/evidence/s2/s2_preregistration.json，4,916 B | 实测 sha256 fde3ef33bab53c67f5f595472a28538b13fbecbc5918903cdc6904c85ad692cd |
| prereg_id | p4ra-s2-prereg-2751c162904d5a4f | prereg 与 run_config/aggregate |
| prereg_digest | c767f2066b720a10db20779507b9a71f21a6ee90e3c752b66e4588e0e98aec83 | run_config.prereg_digest |
| analysis_plan_digest | 43ac6ce0464461e371bdc2e694be9145816ffad3855d7ba9dd307459a9ed60c4 | run_config.analysis_plan_digest |
| code_sha | 3e6ece85a78f1cbb5a8639e279e8388d790213da5358ab35464c8cb37e67a5bb | run_config.code_sha；run_summary.code_sha |
| episode bank sha256 | 6954b053fa5c005554c42bc6f60fc8b9be1d5a307ede49ce4f776d9f67c828a3（4,800 episodes） | run_config.episode_bank.sha256；run_summary.episode_bank_sha256 |
| S0-7 冻结包 | p4ra-s0-7-freeze-20261106T024200Z，SHA256SUMS sha 59aa81cdc1f1abdc66966822eb24b567904ba4c62924ab041ae09bd9badf41f2（9 行/9 文件） | run_config.frozen_package；data_manifest.frozen_package；A2 实测 SUMS 文件 sha 与行数 |
| 前置门禁 | A5 代码 delta APPROVE_FOR_S2_FORMAL（task-256 rev41）；A5 prereg 核验 APPROVE_FOR_S2_RUN（rev44，104 checks/0 fail，8/8 负控，官方 verify True）；A3 delta PASS（task-257 rev37，22/22） | EXT/p4-route-a/lead/S2_FORMAL_RUN_AUTHORIZATION.md；a5/S2_prereg_verification/S2_prereg_verification.md |
| 预算 | 1200 训练 + 4800 评估记录；2 arms；meta_seeds [0,1,2]；outer_steps 200；20 tasks × K[0,1,5,10] × draws 10 | run_config.record_counts / evaluation_grid |
| 资源上限 | 单 (arm,meta_seed) 训练 1200 s；峰值 8192 MB；总墙钟 7200 s；触限即停不重试 | run_config.resource_limits / run_summary.resource_limits |

执行前 preflight 实测 PASS（EXIT=0，约 6 s），输出 episode_bank_sha256=6954b053...，与 prereg 一致。

---

## 2. 执行路径与时间线（实测）

执行路径：Windows 计划任务 RCAIDE_S2_FORMAL_A2 → wrapper EXT/p4-route-a/a2/s2_formal/s2_formal_launcher.cmd（sha256 dd33468baa881aa5a073ad757c6c8c877d379e00be7db9483e37503d7a981d05，2,678 B，ASCII/CRLF）→ envs/RCAIDE/python.exe（cwd=worktree；PYTHONIOENCODING=utf-8、PYTHONHASHSEED=0、PYTHONDONTWRITEBYTECODE=1）。

wrapper 顺序（每步独立进程、独立日志）：
1) base run → OUT=s2_formal/s2-formal-20261106T1810Z
2) 确定性重跑 r1 → s2_formal/determinism/r1（同 run_id、同 created_utc）
3) 确定性重跑 r2 → s2_formal/determinism/r2（同 run_id、同 created_utc）
4) validate base run
5) compare base-vs-r1
6) compare base-vs-r2
7) analyze_s2_run（输出 OUT/analysis）
8) 结束标记

timeline.txt（s2_formal/logs/timeline.txt）实测：

| 时间点（本地 +08:00） | 事件/退出码 | 对应 UTC 约值 |
|---|---|---|
| 2026-11-07 02:10:35.70 | START（created_utc=2026-11-06T18:10:34Z） | 18:10:35.70Z |
| 02:11:07 前后 | BASE_EXIT=0（base 产物 mtime 18:11:07Z） | 18:11:07Z |
| 02:11:38 前后 | R1_EXIT=0（r1 产物 mtime 18:11:38Z） | 18:11:38Z |
| 02:12:10 前后 | R2_EXIT=0；VALIDATE_EXIT=0（18:12:12Z） | 18:12:10Z |
| 02:12:13/14 | COMPARE_R1_EXIT=0；COMPARE_R2_EXIT=0 | 18:12:13/14Z |
| 02:12:17 | ANALYSIS_EXIT=0；ALL_DONE 02:12:17.27 | 18:12:17Z |

- wrapper 总墙钟：101.57 s（02:10:35.70 → 02:12:17.27）；run 内部 run_wall_s 分别为 base 25.6769 s、r1 25.6815 s、r2 25.7853 s。
- 所有 8 个退出码均为 0；base/r1/r2/validate/analysis 的 stderr 日志均为 0 B；task 结束后状态 Ready。
- 计划任务自 2026-11-06T18:10:34Z 启动（授权 issued 18:05:56Z），未等待人工确认，符合授权。

---

## 3. 记录计数与完整性

| 类别 | 期望 | 实际 | 状态 | 证据 |
|---|---|---|---|---|
| 训练记录 | 1200（2 arms × 3 meta_seeds × 200 outer steps） | 1200 | OK 1200 / FAILED 0 | run_summary.record_counts.train；run_summary.status_counts.train；run_records 6000 行扫描 |
| 评估记录 | 4800（2 arms × 3 meta_seeds × 20 tasks × K[0,1,5,10] × 10 draws） | 4800 | OK 4800 / FAILED 0 | run_summary.record_counts.eval；run_summary.status_counts.eval |
| 合计 | 6000 | 6000 | COMPLETED | run_summary.status；validate stdout |
| null 记录 | 0 | 0 | PASS | aggregate.null_disclosure（max_null_rate=0.0，0/240 cells） |

- run_records.jsonl（base）：2,186,063 B，6000 行，sha256 32fbd2c65b6eb6e50e1bb3ca338a0b7da0a90e196242721961c73f344e0a9a25。
- 训练记录：按 arm 各 600；字段 12 个（arm/grad_norm/inner_loss_first/inner_loss_last/meta_seed/outer_step/peak_memory_mb/record_type/run_id/status/train_loss/wall_s）。
- 评估记录：K=0/1/5/10 各 1200；draw∈0..9；6 个 (arm,meta_seed) 组各 800；字段 16 个；split 全部为 meta_validation。
- 训练记录没有 split 字段（run 层数据边界由 run_config.run_mode 与 data_boundary 表征），评估记录 split 均为 meta_validation；无任何 meta_test/meta_test_ood/negative_control 行。
- validate 输出：{"ok": true, "run_status": "COMPLETED"}（EXIT=0）。
- 文件哈希一致性：run_summary.run_config_sha256=9522d467... 与 run_config.json 实测一致；run_summary.run_records_sha256=32fbd2c6... 与 run_records.jsonl 实测一致；run_summary.data_manifest_sha256=88098139... 与 data_manifest.json 实测一致；run_summary.fd_gate_sha256=7950bcb0... 为 fd_gate.json 原始文件 sha。
- analysis 对 run 产物的独立检查：aggregate.checks 共 19 项，18 PASS + 1 DISCLOSED（run_records_core_sha256 的“核心记录摘要口径”未在接口文档定义，分析层不伪造复核 PASS）；无 FAIL。

---

## 4. determinism：2 次重跑证据（run 层实测）

prereg 合同：reruns=2；requires_byte_identical=[train_episode_bank_manifest, run_config, run_records_core]；fail_closed=true（run_config.determinism；run_summary.determinism 同）。

执行方式：base 之外再串行运行 2 次完整 run（同 run_id、同 created_utc、同 prereg/code/worktree，仅 out_dir 不同），然后用 s2_runner compare 比较。两次比较输出（logs/compare_r1.json、logs/compare_r2.json，各 214 B）逐字段均为 true：

| 比较项 | base vs r1 | base vs r2 |
|---|---|---|
| ok | true | true |
| run_config_byte_identical | true | true |
| run_records_core_equal | true | true |
| run_records_core_sha256_equal | true | true |
| episode_bank_sha256_equal | true | true |
| fd_gate_sha256_equal | true | true |
| record_counts_equal | true | true |

A2 独立复算的关键哈希（三条 run 目录逐一计算）：

| 文件/摘要 | base | r1 | r2 | 结论 |
|---|---|---|---|---|
| run_config.json 字节/sha256 | 3,939 B / 9522d467f6b6fcc0bdd75694966d111f36a0ec4ae6c02eb4b98367fc5a6853e0 | 3,939 B / 同左 | 3,939 B / 同左 | 字节完全一致（3/3） |
| run_records_core_sha256（run_summary 字段） | c9460daedbf1868b44e7f2cb5456d6d95da2cbeb64cd692f94e1a5050dafb08f | 同左 | 同左 | 核心记录摘要一致（3/3） |
| episode_bank_sha256 | 6954b053... | 同左 | 同左 | 一致 |
| fd_gate.json 原始 sha256 | 7950bcb05d322a41b0688e752b270ac47df6c97ed912b9fd83dd7023a8d5dec6（8,795 B） | 同左 | 同左 | 一致 |
| data_manifest.json 原始 sha256 | 8809813911478c6287dfe45727b4d7f6ac0b70e5cfc50eaa37ddbc8ef887ecef（2,603 B） | 同左 | 同左 | 一致 |
| run_records.jsonl 全文件 sha256 | 32fbd2c6...（2,186,063 B） | fefa6c07...（2,186,357 B） | 5ca9dab4...（2,186,421 B） | 允许不同：差异仅为逐记录 wall_s 等计时元数据，核心记录摘要相同 |
| run_summary.json sha256 | 77d10cd6...（3,908 B） | 88be3322...（3,922 B） | 931d5576...（3,911 B） | 允许不同：仅计时/耗时字段不同 |
| validate base run | {"ok": true, "run_status": "COMPLETED"} | — | — | run 产物 schema/覆盖/边界/physical 检查 PASS |

结论：run 层 determinism 满足 prereg 合同（run_config 字节一致、run_records_core 一致、bank manifest 一致，fail-closed 未被触发）。analysis 层 NC-10 按设计标 DISCLOSED / NOT_VERIFIABLE_IN_ANALYSIS（分析输入不含逐字段确定性证据），本节的 run 层证据为其补充，不把 DISCLOSED 伪造成 PASS。

---

## 5. FD gate（有限差分梯度正确性门）

- fd_gate.json（8,795 B，raw sha256 7950bcb0...）：mode=full，outer_step=0，meta_seed=0，batch_size=8，query_size=32，physical_call_count=0。
- 检查结果：n_checked=32，PASS=32，FAIL=0；容差 tolerance=1e-06；最大相对误差 1.144759989428372e-09，最大绝对误差 1.79754267026766e-10。
- 坐标可用 497，请求 32；覆盖参数层 layer_0/1/2 的 weight 与 bias；无 override。
- run_config.fd_gate.status=PASS、fd_gate_sha256=4fc75e6909a13f1a2162c59cadf33581357d9ffadb5dbb80a030ef53171c3e8a（内嵌记录摘要）；run_summary.fd_gate_sha256=7950bcb0... 为 fd_gate.json 原始文件 sha；aggregate 检查 fd_gate_artifact 复核两者一致，PASS。
- pilot 证据：micro（s2_fd_pilot_micro.json，sha 1db9d7d65122fd6a56a8e02ad83766f9645641fe636fde8c8bef2752bcfc8e21，n=32，max_rel=1.2780446719818776e-09）PASS；full_size（s2_fd_pilot_full.json，sha e8f425ad9297dd954aca4af79413b2e2e9c18df7e0d20e074fc53aabaf4d0b59，n=8，max_rel=3.975211759696654e-10）PASS。负控 NC-09 PASS。

---

## 6. 负控与完整性检查

分析层负控 14 项（analysis/s2_negative_controls.csv，3,217 B）：13 项 PASS，1 项 DISCLOSED；无 FAIL、无 SKIPPED 伪 PASS。

| check_id | category | status |
|---|---|---|
| NC-01 | physical_isolation | PASS |
| NC-02 | data_boundary | PASS |
| NC-03 | prereg_contract | PASS |
| NC-04 | frozen_package | PASS |
| NC-05 | fairness | PASS |
| NC-06 | multiple_comparison | PASS |
| NC-07 | run_schema | PASS |
| NC-08 | coverage | PASS |
| NC-09 | fd_gate | PASS |
| NC-10 | determinism | DISCLOSED（NOT_VERIFIABLE_IN_ANALYSIS；run 层证据见 §4） |
| NC-11 | null_disclosure | PASS |
| NC-12 | decision_rules | PASS（overall=SUPPORTED_HARM，决策重放一致） |
| NC-13 | endpoint_scope | PASS（推断端点仅 k5/k10） |
| NC-14 | aggregation_unit | PASS（20 tasks，40 pairs） |

另：aggregate.checks 19 项 = 18 PASS + 1 DISCLOSED（run_records_core_sha256 口径未定义）；integrity.degraded_arms=[]、failed_train_records=0、failed_eval_records=0、run_status=COMPLETED。

---

## 7. 端点统计（推断 + 描述，含 null 披露）

### 7.1 统计设置

- 唯一 Holm 族 family_id=s2-primary-secondary-2tests，family_size=2（C1×k5、C1×k10）；alpha=0.05；相对改善阈值 1%。
- 分析单位为 task（同一 task_id 配对 FULL_MAML vs FOMAML，difference=FULL-FOMAML）；每个 (arm,meta_seed,task,K) 先对 10 draws 取均值、再对 3 meta_seeds 取均值。
- 推断端点仅 2 个：post_adaptation_rmse_raw_k5（primary）、post_adaptation_rmse_raw_k10（secondary_inferential）；其余指标一律描述性。
- 检验：Wilcoxon signed-rank two-sided exact；bootstrap 为 task 均值百分位 bootstrap（10,000 resamples，seed 20261105，95%）。
- null 政策：任一 draw 缺失/FAILED/null → 该 (arm,meta_seed,task,K) 记 null；任一 meta_seed 单元 null → 该 task 端点记 null；不插补、不丢弃任务。

### 7.2 推断端点结果（C1）

| 端点 | 角色 | FULL_MAML mean / median | FOMAML mean / median | task 中位差（FULL−FOM） | 相对改善 | Wilcoxon exact p_raw | Holm p_adj | 95% CI（均值差） | 决策 |
|---|---|---|---|---|---|---|---|---|---|
| post_adaptation_rmse_raw_k5 | primary | 1.0096595945946287 / 0.9541571205352783 | 0.9589177466107437 / 0.9228326803629854 | +0.03132444017229297 | -0.03394379158741091（-3.394%） | 3.814697265625e-06（W=1） | 3.814697265625e-06 | [0.04110944269599093, 0.05986980980200832]，mean_diff=0.050741847983885126 | SUPPORTED_HARM（HOLM_SIGNIFICANT_CI_EXCLUDES_ZERO_RELATIVE_DEGRADATION） |
| post_adaptation_rmse_raw_k10 | secondary_inferential | 0.9097952349242538 / 0.9102146042296693 | 0.9003567157566167 / 0.8957137631101255 | +0.01450084111954375 | -0.016189146261628796（-1.619%） | 1.9073486328125e-06（W=0） | 3.814697265625e-06（Holm rank 1） | [0.007323951140872326, 0.011701881656536987]，mean_diff=0.009438519167637188 | SUPPORTED_HARM |

决策规则：Holm p<0.05 且 CI 不跨 0 且相对改善≥1% 为 BENEFIT；对称方向为 HARM。两个端点均满足“显著 + CI 排除 0 + FULL 不比 FOMAML 好”，判 HARM。
总体：primary_decision=SUPPORTED_HARM，secondary k10=SUPPORTED_HARM；aggregate.overall.decision=SUPPORTED_HARM（主终点映射总体结论，次要端点并列披露、不改变主结论）。
说明：本 run 中 FULL_MAML 在样本外适配后 RMSE 反而高于 FOMAML（约 3.4%/1.6% 更差），未复现“Full MAML 优于一阶近似”的预期；方向与 S1 的 NO_SIGNIFICANT_IMPROVEMENT 不矛盾（S1 是不同终点/任务族，不可直接合并）。

### 7.3 描述性指标（不做 benefit/harm 推断）

以下为 20 个 meta_validation task 的 arm 均值（描述性；aggregate.descriptive.metrics；逐 task 值见 s2_per_task_aggregates.csv，25,757 B）：

| 指标 | FULL_MAML 均值 | FOMAML 均值 | 差值（FULL−FOM） |
|---|---|---|---|
| post_adaptation_rmse_raw_k0 | 1.975885 | 1.312567 | +0.663318 |
| post_adaptation_rmse_raw_k1 | 1.538408 | 1.159999 | +0.378409 |
| post_adaptation_rmse_raw_k5（=推断端点） | 1.009660 | 0.958918 | +0.050742（均值差；中位差 +0.031324） |
| post_adaptation_rmse_raw_k10（=推断端点） | 0.909795 | 0.900357 | +0.009439（均值差；中位差 +0.014501） |
| post_adaptation_mae_raw_k5 | 0.795976 | 0.762975 | +0.033001 |
| post_adaptation_rmse_std_k5 | 1.566413 | 1.480299 | +0.086114 |
| post_adaptation_rmse_std_k10 | 1.231942 | 1.216283 | +0.015659 |

描述性观察（不作推断）：K=0/1 时 FULL_MAML 明显更差；随 K 增大差距缩小，但 k5/k10 仍同向为 FULL 更差；标准化 RMSE 也同向。资源描述：训练墙钟比 FULL/FOMAML=1.4369237056229534；峰值内存 FULL 256.72 MB vs FOMAML 261.57 MB。

### 7.4 null 披露（逐层）

- task_arm_values：k5 与 k10 各 expected 40，observed_nonnull 40，observed_null 0，null_rate 0.0。
- meta_seed_cells：FULL_MAML/FOMAML 各 expected 60，observed_null 0，null_rate 0.0。
- 资源指标：train_wall_seconds_ratio / peak_memory_mb 各 expected 1，observed_nonnull 1，null 0。
- 逐记录扫描补充（A5-S2R-01 修正）：4800 条评估记录中恰有 2400 条 query_rmse_standardized=null（K=0 与 K=1 各 1200 条），属评估记录字段级 null，不进入端点统计；全部评估记录 split=meta_validation。1200 条训练记录无 split 键（训练记录按计划 §5 为 12 字段，本就不含 split；数据边界由 episode bank manifest 与 run_config.data_boundary 承载）。分析层端点 null 仍为 0/240（max_null_rate=0.0），与字段级 null 口径不同；未插补、未把 null 写 0，不影响统计、决策、绑定与 0 物理结论。

---

## 8. 图清单与 NOT_RUN

analysis/figure_status.json（1,482 B）：n_figures=9，n_rendered=9，n_not_run=0，n_not_applicable=0；generated_utc 2026-11-06T18:12:17+00:00。

| 图 | 状态 | PNG 字节 |
|---|---|---|
| fig1_training_loss_curves.png | RENDERED | 356,777 |
| fig2_post_adaptation_rmse_k5_k10.png | RENDERED | 126,176 |
| fig3_rmse_vs_K.png | RENDERED | 127,104 |
| fig4_meta_gradient_fd.png | RENDERED | 61,492 |
| fig5_effect_size_ci.png | RENDERED | 77,583 |
| fig6_descriptive_k0_k1_standardized.png | RENDERED | 65,133 |
| fig7_determinism_and_negative_controls.png | RENDERED | 132,155 |
| fig8_performance_cost.png | RENDERED | 129,245 |
| fig9_task_family_diagnostics.png | RENDERED | 155,922 |

- NOT_RUN 图：0。每张图均带 *_support.csv（数据支撑），全部列入 SHA256SUMS。
- fig7 说明：图已渲染，但其 determinism 面板按 analysis 层口径显示 NOT_VERIFIABLE_IN_ANALYSIS（NC-10）；真正的字节一致性证据是 §4 的 run 层两次 compare 与哈希对照，不以图替代。
- 图无缺数据、无 N/A；不存在“缺数据 NOT_RUN”项。

---

## 9. 资源实测与预算

| 项目 | 实测 | 限额 | 占用 |
|---|---|---|---|
| 单 (arm,meta_seed) 训练墙钟最大值 | 3.713840300333686 s（FULL_MAML, meta_seed=1） | 1,200 s | 0.309% |
| 单 arm 训练墙钟均值 | FULL_MAML 3.6831412338651717 s；FOMAML 2.5632127992964038 s | — | — |
| 单 arm 峰值内存最大值 | FULL_MAML 256.72265625 MB；FOMAML 261.57421875 MB | 8,192 MB | 3.19% |
| run 内部墙钟（base） | 25.67694490007125 s | 7,200 s（总） | 0.357% |
| wrapper 总墙钟（3 runs+validate+2 compare+analysis） | 101.57 s | 7,200 s | 1.41% |
| 训练/评估记录 | 1200 / 4800 | 1200 / 4800 | 100% |

- 逐 seed 训练墙钟/内存：FULL_MAML seeds [0,1,2] = 3.668945/3.713840/3.666638 s，内存 251.789/254.5/256.723 MB；FOMAML seeds [0,1,2] = 2.544015/2.598773/2.546851 s，内存 257.551/259.688/261.574 MB。
- 评估墙钟均值：FULL_MAML 1.1228846330195665 s，FOMAML 1.1256700332354133 s（描述性）。
- resource_stop=null；failures=[]；无 RESOURCE_LIMIT、无 DEADLINE_EXCEEDED、无重试。
- 辅助计算：每 arm 训练前 1 次 outer-step 计时（FULL_MAML 0.012521700002253056 s；FOMAML 0.006766199949197471 s），仅用于资源预估，不计入训练预算，physical_call_count=0（run_summary.auxiliary_compute）。
- 平台：Windows-10-10.0.26200-SP0；Python 3.11.17；torch 2.8.0+cpu；numpy 2.4.6；torch_threads=1（CPU）。墙钟为平台相关值。

---

## 10. 0 物理与数据边界证据

### 10.1 physical_call_count=0

- prereg 顶层 physical_call_count=0；run_config.physical_call_count=0；run_summary.physical_call_count=0；data_manifest.physical_call_count=0。
- fd_gate.json physical_call_count=0；aggregate 负控 NC-01 PASS（prereg=0; run_config=0）。
- 执行命令仅 8 条 python -m 调用（s2_runner run/validate/compare ×2；s2_analysis ×1），无任何求解器命令行；无 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag/Gmsh 调用或 import。
- run 结束后进程扫描：无 python/pythonw、无求解器进程；wrapper 的 8 个退出码均 0、所有 stderr 0 B。
- 目标函数来源：SyntheticTask.truth(designs)["objective"]（解析合成评价器，零物理）；run_summary.scope_notes.objective_source 明示。
- 任务领域：S2 是 12 维合成元学习任务，不做气动求解；scope_notes.lifting_surfaces_only=NOT_APPLICABLE（S2 无 VLM/CFD 气动求解），本 run 不涉及机身/机翼求解域。

### 10.2 数据边界（holdout=0）

- run_config.data_boundary：allowed_splits=[meta_train, meta_validation]；forbidden_splits=[meta_test, meta_test_ood, negative_control]；holdout_metrics_read=false；holdout_rows_used=0；holdout_task_ids_sha256=cdc8ea1a5a4afbe4f016846ed320ecdddd2c9533a7a659df6997cb7f29ae5337。
- 记录级实测：6000 行中评估记录 4800 行 split 全部为 meta_validation；训练记录无 split 字段；无任何 forbidden split 行。
- 分析层：aggregate.data_boundary.splits_seen=[meta_validation]；NC-02 PASS；完整负控重放通过。
- 冻结包 echo：S0-7 run_id=p4ra-s0-7-freeze-20261106T024200Z，code_sha=7304d32e524b0e1e28b0e83e7a2ed7822ce88fc14963ca4d769098841e6201ed，git_sha=004156c232f31a450f7446c3b280772de47423df，SHA256SUMS sha 59aa81cd...（9 行）；未修改冻结包（只读使用）。

### 10.3 S0-7 冻结包 physical 字段独立核验（对应 A5-S2PR-01）

- S0-7 的 freeze_summary.json 顶层无 physical_call_count 字段；实际位置为 orchestration.physical_call_count，实测值为 0（A2 已直接读取该文件确认）。
- 因此“0 物理”证据不依赖 S2 校验器的返回值，而来自 prereg 顶层 0 + S0-7 orchestration 嵌套 0 + 本次 run 产物三处 0。

---

## 11. 披露：A5-S2PR-01、OBS-01（及 OBS-02）

### 11.1 A5-S2PR-01（minor，非阻断，A5 已核验）

- 内容：S2 prereg 校验器未实际校验 S0-7 冻结包的 physical_call_count。inspect_frozen_package() 在 research/concorde_metaopt/meta_learning/s2_prereg.py:487 返回 summary.get("physical_call_count")，但 S0-7 的 freeze_summary.json 顶层无该字段（实际字段为 orchestration.physical_call_count=0），返回 None；verify_preregistration() 在 s2_prereg.py:828-843 比较了 sha256sums/code_sha/git_sha/版本/run_id，但未使用 actual["physical_call_count"]。
- 本次独立嵌套读取确认实际值为 0，因此当前事实 PASS，不阻断正式 run。影响：若未来旧包出现 physical>0 而顶层仍无字段，官方校验器不会发现。因 frozen code_sha 不得改动，本轮不改代码；本报告披露该独立核验。
- 与本次 run 的关系：本 run 的 0 物理证据见 §10.1（不依赖该校验器返回值）。

### 11.2 OBS-01（holdout 口径，info，不计入 findings）

- S0-7 freeze_summary 的 holdout_task_count=30、holdout_splits=[meta_test, meta_test_ood]；S2 prereg 的 holdout_task_ids_sha256 覆盖三个 forbidden split 共 40（含 negative_control 10），且 s2_analysis.py:1050 也按 40 校验。
- 结论：S2 口径更严格，不是不一致；本次 run 实际 holdout_rows_used=0、holdout_metrics_read=false，评估记录 split 仅 meta_validation。本报告按 A5 建议注明该口径。

### 11.3 OBS-02（physical 字段位置，info）

- S0-7 把 physical 放在 orchestration，不在顶层；本报告“0 物理”证据同时来自 prereg 顶层 physical_call_count=0 与 S0-7 嵌套值 0，不依赖校验器返回值。OBS-03（origin reflog 无法形式化证明从未 force-push）属 A5 报告层观察，与本次 run 无关，不在此展开。

---

## 12. 偏差、限制与不确定性

1) 时间偏差：计划 v1.6a 总硬上限 2 h，实际 wrapper 总墙钟 101.57 s（约 1.7 min），远低于上限；无资源触限、无重试、无人工干预。该偏差是“比计划快”，不构成对预算的超出。
2) 确定性重跑属于 prereg 强制协议（reruns=2），不是额外统计预算；分析只使用 base run，r1/r2 仅用于字节一致性证据，不参与端点统计。
3) 证据范围限制：结论为 DEVELOPMENT_VALIDATION_ONLY（20 个 meta_validation 任务）；未读取 meta_test/meta_test_ood/negative_control；不能当作 holdout 泛化证据，也不能外推到真实 Concorde/气动优化。
4) 合成目标限制：objective 来自 SyntheticTask.truth 解析评价器（12 维合成任务），非 VSPAERO/SU2/RCAIDE Mission 物理结果；本 run 对真实气动性能无任何声明。
5) 统计不确定性：仅 20 个配对 task；Wilcoxon exact 最小双边 p=1.907e-06，Holm 调整后 3.8147e-06；样本小、任务族单一，效应量（约 1.6%–3.4% 相对恶化）的普适性有限；未做 equivalence/non-inferiority 检验；描述性指标不参与推断。
6) 分析层 determinism 无法自验（NC-10 DISCLOSED / NOT_VERIFIABLE_IN_ANALYSIS）：由 run 层证据（§4 + SHA256SUMS + logs）承载，不伪造 PASS。
7) run_records_core_sha256 口径未在接口文档定义（aggregate DISCLOSED）：A2 通过 runner compare 与三条 run_summary 字段复核一致，未把它当作独立定义已核验。
8) 平台相关：CPU（torch 2.8.0+cpu，torch_threads=1）；墙钟/内存为 Windows 本机实测，不同机器会变化。
9) 未修改仓库、未 commit/push、未做 GitHub 写操作；worktree run 前后 git status 为空（tracked/untracked 均无），所有产物写 EXT。无 solver 启动、无网络求解。
10) 冻结件：prereg 与 S0-7 冻结包仅只读使用；未修改 s2_prereg.py/s2_runner.py/s2_analysis.py 等计划代码旧件。

---

## 13. 复现命令

以下为本次实际执行口径（worktree 只读使用；输出只写 EXT）：

    git -C source-repo rev-parse HEAD
    git worktree add --detach worktree 994cda8e0942060072d65eb50dde790c44d32194
    set PYTHONIOENCODING=utf-8
    set PYTHONHASHSEED=0
    set PYTHONDONTWRITEBYTECODE=1
    cd /d worktree
    envs/RCAIDE/python.exe -m research.concorde_metaopt.meta_learning.s2_runner preflight --repo-root worktree --prereg worktree/research/concorde_metaopt/evidence/s2/s2_preregistration.json --run-mode FORMAL
    envs/RCAIDE/python.exe -m research.concorde_metaopt.meta_learning.s2_runner run --repo-root worktree --prereg worktree/research/concorde_metaopt/evidence/s2/s2_preregistration.json --out EXT/p4-route-a/a2/s2_formal/s2-formal-20261106T1810Z --run-id s2-formal-20261106T1810Z --run-mode FORMAL --created-utc 2026-11-06T18:10:34Z
    （r1/r2 同命令，仅 --out 改为 EXT/.../s2_formal/determinism/r1 与 r2；run_id/created-utc 不变）
    envs/RCAIDE/python.exe -m research.concorde_metaopt.meta_learning.s2_runner validate --run-dir EXT/p4-route-a/a2/s2_formal/s2-formal-20261106T1810Z
    envs/RCAIDE/python.exe -m research.concorde_metaopt.meta_learning.s2_runner compare --dir-a EXT/p4-route-a/a2/s2_formal/s2-formal-20261106T1810Z --dir-b EXT/p4-route-a/a2/s2_formal/determinism/r1
    envs/RCAIDE/python.exe -m research.concorde_metaopt.meta_learning.s2_runner compare --dir-a EXT/p4-route-a/a2/s2_formal/s2-formal-20261106T1810Z --dir-b EXT/p4-route-a/a2/s2_formal/determinism/r2
    envs/RCAIDE/python.exe -m research.concorde_metaopt.meta_learning.s2_analysis --prereg worktree/research/concorde_metaopt/evidence/s2/s2_preregistration.json --run-dir EXT/p4-route-a/a2/s2_formal/s2-formal-20261106T1810Z --output-dir EXT/p4-route-a/a2/s2_formal/s2-formal-20261106T1810Z/analysis --repo-root worktree

（EXT=EXT。wrapper 完全按上述顺序执行；schtasks 任务 RCAIDE_S2_FORMAL_A2；完整命令文本见 s2_formal_launcher.cmd，sha dd33468b...。）

---

## 14. 证据位置与哈希

根目录（EXT）：EXT/p4-route-a/a2/s2_formal/

| 证据 | 位置 | 关键哈希/说明 |
|---|---|---|
| 正式 run | s2-formal-20261106T1810Z/ | run_config.json 3,939 B sha 9522d467...；run_records.jsonl 2,186,063 B sha 32fbd2c6...；run_summary.json 3,908 B sha 77d10cd6...；fd_gate.json 8,795 B sha 7950bcb0...；data_manifest.json 2,603 B sha 88098139... |
| 确定性重跑 | determinism/r1、determinism/r2 | 各 5 文件；run_config 与 base 字节同 sha 9522d467...；core sha c9460dae...；完整文件哈希见 SHA256SUMS.txt |
| 分析产物 | s2-formal-20261106T1810Z/analysis/ | aggregate.json 45,846 B sha 16d7a4d3eca2b4e59e92d66cfbfaa3a543f4a2d0503dcd1acaf7eb7384af8463；s2_endpoint_tables.csv 1,077 B sha 5a3dc849...；s2_holm_family.csv 388 B sha 76ab520e...；s2_negative_controls.csv 3,217 B sha e7cd9d85...；s2_null_disclosure.csv 1,188 B sha 0e57d31e...；s2_per_task_aggregates.csv 25,757 B sha d8058d6d...；s2_prereg_echo.json 10,661 B sha f3611748...；figure_status.json 1,482 B sha 7c216ba3...；fig1..fig9 均 RENDERED |
| 日志 | logs/ | timeline.txt 210 B sha 4096c97c...；base/r1/r2 stdout 各 100 B sha da88a99c...；analysis_stdout 900 B sha 6f34075d...；compare_r1/r2 各 214 B sha 7378b818...；validate_stdout 41 B sha 767c92c5...；全部 stderr 0 B（空文件 sha e3b0c442...） |
| launcher | s2_formal_launcher.cmd | 2,678 B sha256 dd33468baa881aa5a073ad757c6c8c877d379e00be7db9483e37503d7a981d05 |
| 运行事实抽取 | s2_formal_facts.json | 48,584 B（A2 只读抽取，供本报告引用） |
| 校验和清单 | SHA256SUMS.txt | 60 个 run 树文件 + 本报告（修正后）共 61 条；清单自身 bytes/sha256 见 repo_ready_manifest.json 与 A2 回执 |
| 本报告 | EXT/p4-route-a/a2/S2_formal_run_report.md | 修正后 bytes/sha256 见 repo_ready_manifest.json 与 A2 回执（避免自引用哈希循环） |
| repo-ready 副本 | EXT/p4-route-a/a2/S2_formal_run_report_repo.md | UTF-8+LF；绝对路径已替换为 EXT/仓库相对表述；bytes/sha256 见 repo_ready_manifest.json |

---

## 15. 声明

- A2 严格按 S2-FORMAL-AUTH-20261106T1805Z 执行：FORMAL 模式、干净 worktree @994cda8、预算与记录数达标、0 物理、无 solver、无重试、无追加预算。
- 未修改仓库文件、未 commit/push、未写 GitHub、未修改冻结 prereg/旧件；所有产物写 EXT。
- 报告中的确定性 PASS 证据来自 run 层两次 compare 与三份 run 产物的独立哈希复算；analysis 层 NC-10 仍按设计 DISCLOSED，不伪造 PASS。
- 无 NOT_RUN 图、无缺数据；DISCLOSED 项为 NC-10（determinism 分析层不可见）与 aggregate.checks 的 run_records_core_sha256 口径，均已在 §4/§6/§12 明示。
- 本报告结论仅适用于本次 S2 FORMAL run 的 meta_validation 开发集，不代表 holdout、真实气动或 Concorde 优化结论。

（报告结束）
