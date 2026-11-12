# D-REAL-001 A3（r3-stats）任务回执

- 状态：**本轮交付完成（恢复重建版）**；真实求解器启动 **0** 次，physical_solver_starts=0。
- 角色：A3（路线B独立合成验证 + 真实数据统计/风险诊断）；共享任务 id=task-8。
- 分支：research/dreal001-a3-stats-routeb；worktree：D:/RCAIDE/dnext001/wt-real-a3-stats-routeb。
- 基线：683a868（docs(real-opt): 授权宽预算VSPAERO真实气动优化、科学门禁与中文结果报告计划）。
- 作者：QingYangJin。未 push（由 Lead 统一 push/merge）。
- 时间：生成于 2026-11-10 晚（CST，UTC 另注）；所有真实批次状态为 NOT_RUN。
- 恢复声明：原 worktree 与 3 个旧 commit 于 2026-11-10 晚间丢失；本回执与全部源码由重建 worktree 中**会话转录逐文件重放 + 确定性重生成**恢复。旧 commit 0782a4e2cf7c713624d7f5e506b4e5d2244e0efa、1c417dc3ba03fc6a0fe97482233bb1e91e34eb3d、de088db（短 SHA）的 git 对象已丢失，**NOT_RECOVERABLE**；以本分支新 commit 为准（见 §11）。旧证据 SHA 除非另有说明均不可复核，只作记录。

## 0. 一句话结论

纯合成门禁对路线B（学习式元采集）的判定仍为 **NOT_READY**：G0/G1/G2/G5 通过，但 **G3（learned vs EI）与 G4（训练 seed 稳健性）未通过**，learned 策略在两个主终点上均显著差于 EI。因此**不得**进入真实采集对照，也不得进入 2×2 因子实验的 learned 单元；统计工具与 A/B 2×2 预注册分析计划完成并通过 94 项 pytest，但工具与计划本身不构成任何物理证据。三层结论见 §1。

## 1. 三层结论分离（硬性）

| 结论层 | 本轮状态 | 证据/说明 | 边界 |
|---|---|---|---|
| SOLVER_LOOP_VERIFIED | **NOT_RUN** | 本线未启动 VSPAERO/SU2/任何真实 solver；physical_solver_starts=0。闭环验证由 A1 负责 | 不得把本线任何内容写成 solver 闭环已验证 |
| INTERNAL_AERO_OPTIMIZATION_GAIN | **NOT_RUN** | P2 真实 pilot 未排程、未执行；本线只有 synthetic_analogue 合成代理结果 | 合成 CDi/目标改善不得当作 VSPAERO 内部气动收益 |
| EXTERNAL_PHYSICS_SUPPORTED | **NOT_RUN** | 无独立外部物理验证（无密网格/不同尾迹/SU2/独立理论对照） | 不得宣称真实气动或整机性能收益 |
| fuel_burn_kg | **null** | 未做任何燃油/任务分析，缺独立验证前保持 null | 禁止把翼面诱导阻力改善说成真实燃油收益 |

本回执所有数字均为**软件/合成统计**证据：source_kind=synthetic_analogue，physical_solver_starts=0。

## 2. 恢复背景、方法与可复核性

### 2.1 丢失与恢复方法

1. 工作区重建后以 683a868 为基线，先 git reset --hard 683a868 + git clean -fdx 清掉不可靠底稿。
2. 解析本会话转录（session id caf225e3-50be-46cc-957f-b5510ec86fdb）的 tool/ptc-dispatch 事件，按 seq 顺序重放 write/edit（read 的完整文件结果作为 edit 的 seed），得到 32 个文件、0 skip、共 305799 bytes，逐文件字节写入 worktree。
3. 非 tools.write 生成的确定性文件用原构造器重生成：
   - 预注册 JSON：prereg.canonical_prereg_text() 重生成 4676B，文件 sha256=8b57c53e1e824642cf7f9a8244ecbe3728ed8a95f5c451faa668f03e721b9e42，**与丢失前提交中记录的 prereg_sha256 完全一致**。
   - 6 个 schema JSON：schema.write_schema_documents() 重生成（见 §4.3）。
4. 合成门禁全流程重跑（纯 CPU、零物理），并逐产物与丢失前记录的 SHA256 对比（§2.2）。

### 2.2 旧证据 SHA 对照（关键产物）

| 产物（相对 artifacts/dreal001/r3_route_b_gate/） | 丢失前 SHA256 | 重建后 SHA256 | 判定 |
|---|---|---|---|
| dataset/dataset.jsonl | 5abd898d014ae053a737a648f9ecf1ddba6c76263136ffa2212023106abae271 | 同左 | **MATCH** |
| results/eval_results.csv | b8207655ce590ab4389c5727aadf08368fc30896c783a3dd0d9ef77e93e55a9d | 同左 | **MATCH** |
| results/analysis.json | 0f0024da2b191f077337c403c05caee86c478f11030e8fbabe850a51af466836 | 同左 | **MATCH** |
| arm_summary.csv | fe11094a55a576c8cf0ed5221650ca810ca5a1e24f98d0c384491d0131113a6f | 同左 | **MATCH** |
| figures/anytime_best_feasible_synthetic.png | fdd7969bed98221cff142c74a5ec3feed9089ccb789d66150905326245ffae7e | 同左 | **MATCH**（163581B） |
| figures/forest_best_feasible_value.png | c03e303f3ccb6ac9e74a25a841e9d0667c1a0ee5ae355e34d3259c334ae4fe2b | 同左 | **MATCH**（43604B） |
| figures/forest_feasible_hit_rate.png | 5a87f22c58ed6112ae3ee5a609e8b0c295a474b4350b8f66ab3979e154d82fed | 同左 | **MATCH**（45862B） |
| results/traces.jsonl.gz | c53ea8eb4e7df104e793a742636598d7450750ffd0fc32a61005a21d316ad25d | 1cea562b150a7e24887c23736007063e84e3ecd53be8a3db999d0cfeff2ac19a | **MISMATCH（已解释）** |

traces.jsonl.gz 说明：该文件是 gzip 容器，头部含写入时刻 MTIME（本次读得 MTIME=2026-11-10T13:48:10Z），故每次重跑文件 SHA 不同；解压后 payload 为 2394029B、sha256=8818cf9b2dfd78dcf8c5c76b08b4028ce120992ff4e47b84b783edf1af61a410，首行结构见 §3.2。由于 analysis.json（由 trace 统计派生）与 eval_results.csv 均与丢失前**字节一致**，可判定 trace 统计内容一致；旧 gzip 文件本身不可字节级恢复。

其他产物：run_manifest.json 含 generated_utc 时间戳（本次 2026-11-10T13:48:24Z），每次重跑字节不同，属预期；其余确定性产物见 §8。

## 3. 路线B 合成门禁（预注册先于结果）

### 3.1 预注册与设计

- 预注册：research/concorde_metaopt/route_b/gate/prereg/dreal001_route_b_gate_v1.json，sha256=8b57c53e1e824642cf7f9a8244ecbe3728ed8a95f5c451faa668f03e721b9e42，prereg_version=route-b-gate-prereg-v1；分析实现见 research/concorde_metaopt/route_b/gate/（prereg/analysis/pipeline/extended_tasks/report/run_gate）。判据 G0–G5 在跑结果前冻结，结果后未修改；任何结果后修改判据/终点/剔除规则均视为门禁无效。
- 合成任务族：dim=6，budget=12，n_init=4，候选池 256，fit_task_count=22，早停仅用 train 内部 2 个任务；train/val/test 按 task_id 前缀绝对隔离（synth-{split}-{index:02d}），测试任务不参与训练、早停、调参或特征统计。
- 划分：train 24 / val 8 / test 36；决策记录 2304（=24 任务 × 4 behaviors × 8 步 ≈ 768 条实际形态，见 dataset.jsonl）；训练 240 epochs、lr=0.02、behaviors=ei/ucb/pi/random、training_seeds=0,1,2；best_val_loss 分别为 0.1726131643088488 / 0.5077237155406393 / 0.9300749168553281（seed0/1/2，仅 sanity，不参与判定）。
- 评测：9 臂（learned_s0/1/2、ei、ucb、pi、random、random_score、untrained）× 36 test 任务 × 6 eval seed = **1944 cells**；同任务同 eval seed 下所有臂共享同一固定初始设计，评测只读 test 划分；anytime 网格 [4,6,8,10,12]。
- 泄漏防护：数据契约拒绝 proxy/fake 标签记录；策略特征显式排除 task_id 与 split；候选池坐标可见但池标签不可见；G0 完整性检查要求 1944 cells 无缺失无重复、全部 split=test、prereg SHA 一致；G1 负控（untrained）要求不得显著优于 random 且 mean 差 <=0.05；random_score 与 random 同分布自检通过。

### 3.2 门禁结果（run_manifest generated_utc=2026-11-10T13:48:24Z，git_head=683a868，physical_solver_starts=0）

| 判据 | 状态 | 关键证据 |
|---|---|---|
| G0_completeness | **PASS** | observed_rows=1944，expected_cells=1944，n_missing_cells=0，n_duplicate_cells=0，prereg_sha 匹配，physical_solver_starts_sum=0 |
| G1_negative_control | **PASS** | untrained−random mean delta=−0.06917678506570368（不为正），significant_better=false；Wilcoxon p=1.4683758142142379e-8 方向为 untrained 更差 |
| G2_learned_beats_random | **PASS** | feasible_hit_rate 平均改善 +0.06365740740740741，CI [0.04886509773662551, 0.07883230452674897]，Holm p=7.766075764216863e-13；best_feasible_value 平均改善 +0.07663948098794915（lower 方向），CI [0.02838129702772479, 0.12507937388357054]，Holm p=0.010325065953609675 |
| G3_learned_vs_ei | **FAIL** | 两个主终点均显著劣于 EI：hit_rate 改善 −0.05748456790123457，CI [−0.07497749485596708, −0.040509259259259266]，Holm p=8.256062464897347e-10；best_feasible_value 改善 −0.16792976468001264，CI [−0.20508543733185236, −0.13188585258386387]，Holm p=2.3378537350304656e-18 |
| G4_training_seed_robustness | **FAIL** | n_robust_seeds=0（要求 3 个训练 seed 中至少 2 个在两个主终点上均不显著劣于 EI） |
| G5_power | **PASS** | n_test_tasks=36>=32，n_eval_seeds=6>=5，n_train_tasks=24>=24，n_decision_records=2304>=2000，cells_complete=true |

判定：**verdict=NOT_READY**；verdict_reason=「未通过预注册判据: G3_learned_vs_ei, G4_training_seed_robustness。合成任务上证据不足以支持进入真实采集对照。」（与 Issue#8 首轮 NOT_READY 结论一致；历史结论未改写。）

### 3.3 主/次终点描述统计（pooled learned = 3 个训练 seed 的单元内均值；单位 task_id × eval_seed，n=216 配对）

| 指标（方向） | learned pooled | EI | PI | UCB | random |
|---|---|---|---|---|---|
| feasible_hit_rate（higher） | 0.22569444444444445 | 0.28317901234567905 | 0.3036265432098766 | 0.18672839506172842 | 0.16203703703703703 |
| best_feasible_value（lower） | 0.4494559914514245 | 0.2815262267714119 | 0.28244703108690655 | 0.48499314418563866 | 0.5260954724393737 |
| total_reward（higher，次终点） | 0.23831282745495808 | 0.2677143451854062 | 0.26354441037862353 | 0.14070281473360044 | 0.11203382519473783 |
| null_fraction（lower，次终点） | 0.7743055555555556 | 0.716820987654321 | 0.6963734567901234 | 0.8132716049382717 | 0.8379629629629629 |
| anytime_best_feasible_auc（lower，次终点，归一化） | 0.5978073106475181 | 0.49769202451318856 | 0.49704565831848346 | 0.6148476763912745 | 0.6472800453944026 |

统计协议：Wilcoxon signed-rank 双侧；Holm step-down（每个终点族内 learned vs ei/ucb/pi/random 共 4 个比较）；bootstrap 10,000 次、seed=20261110、百分位 95% CI；统计单元 = task（task_id × eval_seed），跨 seed 配对；learned 主分析先对 3 个训练 seed 取算术平均，不按测试集表现挑 seed。anytime 次终点只报告、不参与 READY/NOT_READY（预注册排除项）。

### 3.4 判定解读与科学意义

1. learned 相对 random/untrained 显著更好（G2 PASS）说明训练管线有信号、负控自检通过；但 learned 明显输给标准约束 BO 的 EI/PI，且 3 个训练 seed 中 0 个稳健不劣于 EI（G4=0），说明当前 direct-method 离线训练/样本量 2304、单一 6D 合成任务族条件下，**没有证据支持 learned 采集可进入真实对照**。
2. 该负结果本身即交付物（沿用 dnext001_route_b_acquisition_design.md §1/§6.4 的诚实结论）：避免在真实评价接通前过度投入；也避免把不合格策略带进大规模真实 VSPAERO 批次。
3. 本门禁为 synthetic_analogue，physical_solver_starts=0；无论 verdict 如何，都不构成气动/物理证据。

## 4. 统计与诊断工具模块（research/concorde_metaopt/dreal001/stats/）

### 4.1 模块与公开 API

- schema.py：SchemaError、validate_against_json_schema、build/load/write_schema_documents、classify_source_kind、validate_evaluation_record、validate_optimization_history_row、detect_metrics_schema、validate_metrics_row、validate_run_record。
- records.py：is_missing、parse_metric_value、RunRecord、normalize_run_record、load_run_table_csv、load_metrics_csv、EvaluationStep、load_evaluations_jsonl、RunArtifacts、load_run_directory、mean_by_unit、physical_start_summary、write_run_table_csv。
- paired.py：bootstrap_ci_mean、wilcoxon_signed_rank、cohens_dz、holm_correction、paired_units、PairedComparison、compare_paired、compare_paired_across_seeds。
- anytime.py：best_so_far、anytime_curve_from_steps、aggregate_curves、area_under_curve、cap_missing、cumulative_solver_starts、anytime_curve_at_points、anytime_curve_from_solver_starts、anytime_solver_start_area。
- isolation.py：EvidenceIsolationError、evidence_mix、assert_comparison_isolated、assert_no_physical_claims、summarize_evidence。
- family.py：compare_to_references（族比较，Holm 家族）；plots.py：configure_chinese_font、figure_sha256、plot_anytime_curves、plot_paired_forest；real_data.py：RealDataStatusError、validate_real_data_status、load_real_data_status、is_real_data_available。

### 4.2 统计口径（与预注册一致）

- 统计单元 = (task_id, eval_seed)；跨 seed 先单元内聚合再配对；compare_paired 输出单元级配对差、bootstrap CI、Wilcoxon p、Cohen dz、Holm 校正。
- 缺失数据：NOT_RUN 明确标记，不补 0；truncate/worst-case cap 按预注册规则并计数；全缺失 task 剔除并列出 task_id。
- anytime：x 轴 = 累计 physical_solver_starts（每次真实启动 +1），不按墙钟/评价次数；AUC 归一化可复算。
- 证据隔离：source_kind 分类（真实求解 vs synthetic_analogue/replay 等）；混入合成记录被 isolation 断言拒绝；report 层禁止物理收益声明。

### 4.3 输入 schema 与契约

- 运行时生成 6 个 JSON Schema 到 research/concorde_metaopt/dreal001/stats/schemas/（SCHEMA_VERSION=dreal001-stats-schema-v1）：
  - evaluations_a1.schema.json 2758B sha256=0e6e247c40e3878d5d50f3be9f8aba7ccc815f265b0345930f7d2f32c421a3ec
  - evaluations_a2.schema.json 1076B sha256=df2b403033e6bd3c9de3b127f8b5d4313ffd44a7a145d656cbee4bf392b8076a
  - metrics_a1.schema.json 1460B sha256=6ca88d401f403792ef83c2b31308a9eee0a55406bb3ca09f6ebb7ada4be41248
  - metrics_a2.schema.json 3195B sha256=e43c6ba43740270f6ff80bf969602e35f0ac6f4a8313932d25c29de47b26561d
  - optimization_history.schema.json 1345B sha256=a5840a83da3a58ea7097362d255b8c82204bce5dd8d004872bfdce1d1bdc92e9
  - run_record.schema.json 1161B sha256=030b7441ba9d1195e31865395d5220f216be4a24334171b2620cad9eef72004e
- 轨迹/表格 schema 对齐 A2 的 evaluations.jsonl / optimization_history.csv / metrics.csv；先定义 schema 并写契约测试，随后可适配 A2 实际产出。环境无 jsonschema 包且禁止 pip install，故自研最小 schema 校验器（validate_against_json_schema）。
- 已知兼容修复（相对早期版本）：records.load_run_table_csv 的 run_config 合并映射补充 run_id/task_id，使 A1 metrics.csv 缺 task_id 时仍可读；契约测试同时锁定中文错误消息与字段路径。

## 5. A/B 2×2 因子实验预注册分析计划（不执行真实批次）

- 文档：docs/planning/dreal001_r3_ab_2x2_prereg_20261110.md（PRE-REGISTERED PLAN 草案 v0.1，physical_solver_starts=0）。
- 因子：F1 热启动（cold=预注册 Sobol 初始设计 n0=8；warm=同 task 的 P2 预注册 incumbent 设计纳入初始集）；F2 学习采集（standard=EI；learned=路线B gate READY 后冻结的学习采集策略）。四单元 cold_ei / warm_ei / cold_learned / warm_learned，除因子外 solver 版本、网格/wake、alpha 搜索、初始点数、预算、seed 分配必须一致。
- 假设：H1（F1 主效应：warm 的 best_valid_Di_N 更低）、H2（F2 主效应：learned 低于 EI）；H3 交互仅探索性，不进入确证家族。
- 主终点（确证，Holm 家族 size=2）：best_valid_Di_N、anytime_best_valid_Di_auc（按累计 physical_solver_starts 归一化，越低越好）。次终点仅描述性（first_feasible_solver_start、valid_solve_rate、delta_Di_N、reaches_threshold_starts、lift_residual_N、null_rate、失败/重试计数）。
- 统计：统计单元=task（task 内先对 5 个优化 seed 取均值，避免伪重复），跨 task 配对；≥36 tasks；确证预算 B=256 次物理评价请求/run，B=128/512 为 anytime/敏感性层；配对 bootstrap 10,000、seed=20261110、Holm；MDE 近似 2.8·SD/sqrt(36)=0.47·SD，CI 宽于预注册 MDE 时写 INCONCLUSIVE（不得写“无效应”）。
- 负控：A/A（cold_ei vs cold_ei' 仅 seed 不同）、标签置换安慰剂（预注册置换 seed）、sham warm（随机合法设计替代 incumbent）、合成冒烟（physical=0 仅验证代码路径）、审计（solver 版本/输入输出 SHA/物理计数与 data_manifest 对齐）。
- 停止/披露：不因期中优效停止；intention-to-analyze，禁止按结果剔除；偏离写入 deviations.log 并报 Lead；解盲后不改分析代码。
- 前置条件（全部满足才允许 Lead 立项冻结 v1.0 预注册 SHA）：路线 A/B 独立审查通过；A5 签 SOLVER_INTERNAL_PASS 且 tol_lift 冻结；P2 真实 pilot 门禁通过；**路线B 合成门禁 READY**。当前 Route B = NOT_READY，因此 **F2=learned 单元现在不得进入本实验**，本计划仅为纸面草案。
- 解释边界：主终点改善只能表述为同一 VSPAERO 模型内翼面诱导阻力优化收益（INTERNAL_AERO_OPTIMIZATION_GAIN 候选证据）；不得表述为真实燃油收益/整机性能/外部物理验证；fuel_burn_kg 保持 null；S1/S2/S3 负结果事实保留、不改写历史结论（§8）。

## 6. 真实数据诊断占位（NOT_RUN）

- docs/receipts/dreal001/r3_real_data_manifest.json（schema dreal001-real-data-manifest-v1）：status=NOT_RUN，authorization_id=NOT_ISSUED，physical_solver_starts=0，artifact_root=artifacts/dreal001/real/p2_pilot/run_000。仅声明 P2 真实产物的期望格式（evaluations.jsonl、optimization_history.csv、metrics.csv、run_config.json、summary.json、solver_attempts.jsonl、approval.json、numerical_validation.csv、data_manifest.json、SHA256SUMS.txt）与统计适配契约；P2 未执行，故**真实数据诊断全部 NOT_RUN**，禁止用合成/回放数据冒充。
- 适配契约要点：真实产物必须 source_kind=real_solver 且经 isolation 断言（混入合成记录拒绝）；anytime x 轴按 cumulative physical_solver_starts（缺字段报错，不补 0）；单元=(task_id, seed) 配对；主终点 best_valid_Di_N/lift_residual_N/delta_Di_N/first_feasible_solver_start/valid_solve_rate/anytime_best_valid_Di_auc。

## 7. 测试与验证记录（零物理）

- 命令（worktree 根）：
    D:/RCAIDE/envs/RCAIDE/python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r3_stats_schema.py research/concorde_metaopt/tests/test_dreal001_r3_stats_records.py research/concorde_metaopt/tests/test_dreal001_r3_stats_paired.py research/concorde_metaopt/tests/test_dreal001_r3_stats_anytime.py research/concorde_metaopt/tests/test_dreal001_r3_stats_isolation.py research/concorde_metaopt/tests/test_dreal001_r3_stats_p2_ready.py research/concorde_metaopt/tests/test_dreal001_r3_route_b_prereg.py research/concorde_metaopt/tests/test_dreal001_r3_route_b_gate.py research/concorde_metaopt/tests/test_dreal001_r3_route_b_report.py -q -p no:cacheprovider
- 结果：**94 passed in 3.86s**（exit=0；与丢失前“A3 pytest 94 通过”一致）。
- 门禁重跑命令与结果：
    D:/RCAIDE/envs/RCAIDE/python.exe -m research.concorde_metaopt.route_b.gate.run_gate --stage all
  返回 stages split/dataset/train/evaluate/analyze 全部 done，verdict=NOT_READY，generated_utc=2026-11-10T13:48:24Z，git_head=683a868ed5a7014adbe0ca6dce704f9c947872eb，physical_solver_starts=0。
- 报告生成命令与结果：
    D:/RCAIDE/envs/RCAIDE/python.exe -c "import sys; sys.path.insert(0,'research'); from concorde_metaopt.route_b.gate.report import build_gate_report; print(build_gate_report('artifacts/dreal001/r3_route_b_gate'))"
  返回 report_version=route-b-gate-report-v1、source_kind=synthetic_analogue、verdict=NOT_READY、physical_solver_starts=0、n_rows=1944，中文图字体 Microsoft YaHei 可用（C:/Windows/Fonts/msyh.ttc），生成 3 张图（anytime 1 张、forest 2 张）。
- schema 生成：schema.write_schema_documents() 返回 6 键，见 §4.3；SCHEMA_VERSION=dreal001-stats-schema-v1。
- 代码改动（相对 683a868）：唯一修改既有文件 research/concorde_metaopt/route_b/policy_eval/__init__.py（+STATUS_VALID 导入；run_closed_loop 增加 trace: bool=False；trace=True 时逐次评价追加 {eval_index, valid, feasible, objective, status} 并在结果中返回 trace；默认关闭保持既有产物字节稳定）；其余均为新增文件（gate/、dreal001/stats/、tests、planning/receipts 文档）。

## 8. 交付清单与关键 SHA256（恢复后生成）

- 门禁证据根：artifacts/dreal001/r3_route_b_gate/（本次重跑；下文 SHA 为重建后值）
  - dataset/dataset.jsonl 1442051B sha256=5abd898d014ae053a737a648f9ecf1ddba6c76263136ffa2212023106abae271
  - dataset/episodes.json 93270B sha256=18ad398a299218b55a252c7e7ff491b1fc62a4ed4c6193f089b59c5faf46bb09
  - dataset/manifest.json 734B sha256=277216534a308ccb5f0120e7b87d05e4b56d7115ff49e12ca7e151324e5477ee
  - split_manifest.json 1366B sha256=63648659c1f9292efac7880a362a3ff77133ec0ddf8cb0165eded1a9b4647c53
  - train_summary.json 59159B sha256=38547d642612f6599780426618a821b470171cd53d4764acf1fc818ca623cfab
  - results/eval_protocol.json 486B sha256=6d39d192b5ab87d6db98a4c459873b8ccfa50c5de9e9276896b9f12672a4c03a
  - results/eval_results.csv 655496B sha256=b8207655ce590ab4389c5727aadf08368fc30896c783a3dd0d9ef77e93e55a9d
  - results/traces.jsonl.gz 257059B sha256=1cea562b150a7e24887c23736007063e84e3ecd53be8a3db999d0cfeff2ac19a（gzip 头含 MTIME，见 §2.2）
  - results/analysis.json 48546B sha256=0f0024da2b191f077337c403c05caee86c478f11030e8fbabe850a51af466836
  - results/analysis_summary.json 560B sha256=f6e927d7bee2bdccacca66cd7e6475fcab0f99922405cc04c3cc3c76b337f408
  - arm_summary.csv 1626B sha256=fe11094a55a576c8cf0ed5221650ca810ca5a1e24f98d0c384491d0131113a6f
  - figures/anytime_best_feasible_synthetic.png 163581B sha256=fdd7969bed98221cff142c74a5ec3feed9089ccb789d66150905326245ffae7e
  - figures/forest_best_feasible_value.png 43604B sha256=c03e303f3ccb6ac9e74a25a841e9d0667c1a0ee5ae355e34d3259c334ae4fe2b
  - figures/forest_feasible_hit_rate.png 45862B sha256=5a87f22c58ed6112ae3ee5a609e8b0c295a474b4350b8f66ab3979e154d82fed
  - figures/report_index.json 5458B sha256=52d76e7f496f1d1cf1eb0fa5326265238ba2cefcec502c9abb83baa5a5b96fb3
  - run_manifest.json 2115B sha256=03ceb6dadda24be57ad72bde8152463391bf7e00d10fd0bd45a78646360900d9（含 generated_utc）
- 预注册：research/concorde_metaopt/route_b/gate/prereg/dreal001_route_b_gate_v1.json 4676B sha256=8b57c53e1e824642cf7f9a8244ecbe3728ed8a95f5c451faa668f03e721b9e42
- schema（6 个）：见 §4.3。
- 文档：docs/planning/dreal001_r3_route_b_gate_prereg_20261110.md（9593B）、docs/planning/dreal001_r3_ab_2x2_prereg_20261110.md（9579B）、docs/receipts/dreal001/r3_real_data_manifest.json（5175B）、本回执、docs/receipts/dreal001/r3_gate_artifact_sha256.txt（§8 证据清单的机器可读版）。
- 测试：research/concorde_metaopt/tests/test_dreal001_r3_stats_*.py（6 个文件）+ test_dreal001_r3_route_b_{prereg,gate,report}.py（3 个文件），共 94 tests。
- 恢复清单：D:/RCAIDE/_recovery/r3-stats/recovered_manifest.json（逐文件 bytes+sha256、来源事件、旧 SHA 不可恢复清单）。

## 9. 未完成项与风险（诚实清单）

1. **P1/P2/P3 真实批次：NOT_RUN**。P2 pilot 未排程、P1 数值物理验收未签、无任何真实 VSPAERO 数据；真实数据诊断与真实统计对照全部 NOT_RUN。
2. **路线B：NOT_READY**。G3/G4 未过；learned 不得进入真实采集对照或 2×2 的 F2 单元。要翻案必须先补强训练（更多轨迹/任务族）、消除 direct-method 偏差（IPS/双重稳健/在线 RL）或引入更强基线（RGPE/PFNs4BO 等），并**预先**重写预注册后再跑；本轮判据不得事后修改。
3. **旧 commit 对象与旧证据 SHA 不可复核**：0782a4e/1c417dc/de088db 的 git 对象已丢失，旧 SHA 仅为记录，NOT_RECOVERABLE；traces.jsonl.gz 旧文件因 gzip 头时间戳无法字节级重建（统计内容一致性由 analysis.json/eval_results.csv 字节一致佐证）。
4. **合成任务族窄**：6D 二次型 + 窄带约束、2304 决策、3 个训练 seed；结论不可外推到 12D 真实气动任务；G2“优于 random”只说明管线有信号，不说明优于 EI/PI。
5. **统计工具尚未在真实 A2 数据上运行**：schema/约定测试通过，但 P2 数据到位后需按 r3_real_data_manifest.json 契约做一次真实数据适配复核（source_kind=real_solver、solver-starts 轴、lift 残差）。
6. **时间戳类产物**（run_manifest.json、figures/report_index.json 等）每次重跑字节不同，比较时必须用确定性产物；gzip 容器同理。
7. 本回执所有内容均未 push；如与 Lead 总账/其他线回执冲突，以 Lead 统一记录为准。

## 10. 复现命令（从 worktree 根，零物理）

    D:/RCAIDE/envs/RCAIDE/python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r3_stats_schema.py research/concorde_metaopt/tests/test_dreal001_r3_stats_records.py research/concorde_metaopt/tests/test_dreal001_r3_stats_paired.py research/concorde_metaopt/tests/test_dreal001_r3_stats_anytime.py research/concorde_metaopt/tests/test_dreal001_r3_stats_isolation.py research/concorde_metaopt/tests/test_dreal001_r3_stats_p2_ready.py research/concorde_metaopt/tests/test_dreal001_r3_route_b_prereg.py research/concorde_metaopt/tests/test_dreal001_r3_route_b_gate.py research/concorde_metaopt/tests/test_dreal001_r3_route_b_report.py -q -p no:cacheprovider

    D:/RCAIDE/envs/RCAIDE/python.exe -m research.concorde_metaopt.route_b.gate.run_gate --stage all

    D:/RCAIDE/envs/RCAIDE/python.exe -c "import sys; sys.path.insert(0,'research'); from concorde_metaopt.route_b.gate.report import build_gate_report; print(build_gate_report('artifacts/dreal001/r3_route_b_gate'))"

    D:/RCAIDE/envs/RCAIDE/python.exe -c "import sys; sys.path.insert(0,'research'); from concorde_metaopt.dreal001.stats import schema; print(sorted(schema.write_schema_documents()))"

## 11. 提交与恢复记账

- 旧分支 commit（丢失，NOT_RECOVERABLE）：0782a4e2cf7c713624d7f5e506b4e5d2244e0efa（stats 模块+55 tests）；1c417dc3ba03fc6a0fe97482233bb1e91e34eb3d（gate prereg v1 + 划分/管线/分析 + trace/契约测试 19 passed）；de088db（stats P2-ready + route B 报告模块；A3 94 passed）。
- 新 commit：本分支恢复后提交（recover(a3-stats): ... + 本回执/证据），SHA 以 git log 与给 Lead 的汇报消息为准。
- 恢复清单：D:/RCAIDE/_recovery/r3-stats/recovered_manifest.json。
- 声明：本回执未伪造任何数字；NOT_RUN 一律写 NOT_RUN；合成结果未标成真实求解；physical_solver_starts 触发数=0。
