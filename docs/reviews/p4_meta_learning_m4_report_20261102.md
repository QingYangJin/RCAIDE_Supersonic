# P4-CODE M4 报告：M1 元学习与 M2 等预算优化（合成离线，物理调用 0）

> 状态：FINAL（A2 起草、Lead 定稿；已提交入库并通过 M3 独立终审 APPROVE_FOR_ISSUE_RECEIPT_AND_PR，0 blocker/0 major/4 minor，处置见 §11）。本 run 为 SYNTHETIC_ONLY：全部评估由合成解析评估器产生，physical_call_count=0，不含任何真实物理结论。
> run_id：p4-meta-m2-offline-20261102T092828Z；stage=P4-CODE；git_sha=36d58918fc5f1002a599c45661e3cd389ce96c19；data_origin=SYNTHETIC_TEST；生成时间（UTC）：2026-11-02T11:21:56Z（最终 figure_status；初版 11:03:35Z）/ 本稿由脚本生成。
> 全部引用数字均可追溯到 run 目录 summary.json、run_config.json、environment.json、data_manifest.json、tasks.json、metrics/*.csv、figures/*；逐项审计见本 run 目录 m4_report_numbers.csv（随包提交）。

## 1. 执行摘要

- 运行状态：status=VALID，failure 计数 n_failed_evaluations=0、n_nonfinite_m1=0；git 工作区 worktree_dirty=false，config_hash=0d393de6ae1d56b3c62308d977678581025f63ec74ce92c6c43201436c902f8b。
- 规模：M1 元训练 2000 步（外层损失 2.771985041028135 → 1.2540536115550236）；自适应评估 480 行（R/P/M × K=0/1/5/10 × 3 split）；M2 750 次 run、每次恰好 64 次真实（合成）评估，合计 48000 次评估；优化种子 [0, 1, 2, 3, 4]。
- 门禁：determinism=PASS（3 次重跑）、finite_difference=PASS（最大相对误差 2.052996661561224e-11，容差 0.0001）、reference_solutions=PASS（110 个任务，max_residual=0.0）、physics_guard=PASS（expected=0）、physical_call_count=0。

三条结论（口径严格）：

1. M1 预注册主终点（meta_test、K=5、query RMSE）：M 相对 P 的配对均值差为 -0.013730479463645154（95% bootstrap CI [-0.01808574719479586, -0.0036721320542072444]，Wilcoxon p=0.005580902099609375），相对 R 为 -0.050614345553870066（CI [-0.08374463321767278, -0.03865358684311426]，p=0.0019855499267578125）；20 个配对 task，n=20。
2. M2 主终点（best_feasible_value）稀疏且不可比：meta_test 仅 OPT-BO-rand 有 2/100 个有限值（1.3184193592143387 ～ 1.4658106408684481），OPT-BO-MAML-init 与 OPT-DE 均为 0/100；meta_test_ood 三臂均 0/50。因此 arm 间优劣不得使用主终点，只能用预先声明的 A7 fallback 指标，且仍不宣称优于基线。
3. A7 fallback 三臂比较：meta_test 中 MAML-init 相对 rand 的 best_objective_raw 均值差 0.027096717088332944（CI [-0.07424225759273084, 0.06674580761003293]）、min_constraint_violation_sum 均值差 -0.038206900142249284（CI [-0.10339492770448677, 0.10108321753660071]），均跨 0；DE 的约束违反和均值差 0.4186941189582042（CI [0.14958818011667696, 0.5575462622685858]，p=1.3584976082693048e-06）。

## 2. 方法与数据合同

- 任务族/设计空间：family_id=F-QE，design_set=12d_lifting_surfaces，evaluator_id=synthetic__analytic__12d_lifting_surfaces__v1；家族指纹 family_fingerprint=f4afd17512558277fd898e2b2b5c19f00d15b9b0e8618126ce3876b2c3b7c4e2；support_pool_size=128、query_size=64、designs_per_task=192；上下文维度 2（context_1/context_2），设计维度 12，参考容差 1e-10。
- 数据来源：data_origin=SYNTHETIC_TEST，archive.dataset_id=p4-meta-m2-offline-20261102T092828Z-m1，n_samples=21120（synthetic，schema_version=2）；任务拆分 meta_train=60、meta_validation=20、meta_test=20、meta_test_ood=10、negative_control=10。
- M1 预注册主终点：meta_test K=5 query RMSE (MAML vs P, MAML vs R)；统计口径：paired unit=per (task, seed)，test=wilcoxon_signed_rank（n>=5 且非全零时计算），bootstrap_samples=10000，confidence=0.95，effect_size=paired_cohen_d，seed=42。
- 负控制协议：负控制任务为 label-shuffle 伪任务（单列、不进入主终点）；预期 MAML 相对预训练优势回落至接近 0，K=0 随机初始化臂应最差，OOD RMSE 预期上升（见 m1/negative_control_checks 的 interpretation 字段）。
- M2 五臂：可识别臂 ['OPT-BO-rand', 'OPT-BO-MAML-init', 'OPT-DE']；克隆臂 ['OPT-BO-pretrain', 'OPT-BO-MAML']（标识 CLONE_OF_OPT-BO-rand，仅描述性、不用于推断）。每臂每 run 真实评估预算 64，优化种子 [0, 1, 2, 3, 4]。
- M2 主终点/回退终点：primary_metrics=['best_feasible_value', 'gap_to_reference', 'first_feasible_eval_index']；fallback_metrics=['best_objective_raw', 'min_constraint_violation_sum', 'feasible_hit_rate']；可行域说明：true（可行域体积 ~1e-6，B=64 预期 0 可行，结论表需披露）。
- 可复现与确定性：determinism compared_files=['metrics/metrics.csv', 'metrics/optimization_summary.csv']，reruns=3，mismatched_files=[]，排除列=['wall_s', 'proxy_scoring_cost_json']；finite_difference epsilon=1e-05，n_checked=5。
- 环境：python 3.11.17，numpy 2.4.6，scipy 1.17.1，matplotlib 3.11.2，torch 2.8.0，platform Windows-10-10.0.26200-SP0，cpu_count 32，device=cpu。

## 3. M1 结果

### 3.1 训练曲线（training_history.csv）

| 臂 | 行数 | iteration 范围 | 首个 loss_query | 末个 loss_query |
| --- | ---: | --- | ---: | ---: |
| M（MAML） | 2000 | 0→1999 | 2.771985041028135 | 1.2540536115550236 |
| P（预训练） | 50 | 0→49 | 8.324461073516257 | 1.9443600498105809 |

M 的外层（query）损失自 2.771985041028135 降至 1.2540536115550236（2000 步）；P 的预训练损失自 8.324461073516257 降至 1.9443600498105809（50 步、11520 行）。说明：training_history.csv 未记录验证损失（NOT_AVAILABLE），图 1 已按此加注。

### 3.2 K-shot 自适应（meta_test，每格 n=20 task×seed 行）

| 臂 | K=0 RMSE | K=1 RMSE | K=5 RMSE | K=10 RMSE |
| --- | ---: | ---: | ---: | ---: |
| R（随机初始化基线） | 2.1197442749159547 | 1.4549018090612789 | 1.1616797323999541 | 1.0316007430457637 |
| P（监督预训练基线） | 1.4272160593355654 | 1.40504407858714 | 1.1247958663097293 | 1.0357548173942683 |
| M（MAML 元学习） | 1.4183756507878262 | 1.4054756861601827 | 1.111065386846084 | 1.0110682598510805 |

OOD（meta_test_ood）K=5 RMSE 均值：R=1.0128182020665357，P=1.0330937934173205，M=1.023160461535162。

### 3.3 预注册主终点与次要终点（配对差，M−P / M−R）

| 终点 | 对比 | n | 均值差 | 中位差 | 95% CI | Wilcoxon p | 判读 |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| K=5（主终点） | M−P | 20 | -0.013730479463645154 | -0.011314151283426388 | [-0.01808574719479586, -0.0036721320542072444] | 0.005580902099609375 | CI 不含 0 且 p<0.05 |
| K=5（主终点） | M−R | 20 | -0.050614345553870066 | -0.051697121292827386 | [-0.08374463321767278, -0.03865358684311426] | 0.0019855499267578125 | CI 不含 0 且 p<0.05 |
| K=0（次要） | M−P | 20 | -0.008840408547739247 | -0.00937397703348819 | [-0.016851395935849722, -0.0029893594901730935] | 0.0758514404296875 | CI 不含 0 但 p≥0.05 |
| K=0（次要） | M−R | 20 | -0.7013686241281287 | -1.2267265324665946 | [-1.505044958833152, -0.2605971734620949] | 0.013616561889648438 | CI 不含 0 且 p<0.05 |
| K=1（次要） | M−P | 20 | 0.00043160757304274713 | 0.0004569838235692347 | [-0.02321399263756352, 0.003014369670105599] | 0.9854354858398438 | CI 含 0 |
| K=1（次要） | M−R | 20 | -0.04942612290109612 | -0.03264347068048834 | [-0.12222255619084477, 0.05107506614865648] | 0.2305126190185547 | CI 含 0 |
| K=10（次要） | M−P | 20 | -0.024686557543187944 | -0.021232999057475055 | [-0.033238991179254385, -0.007880540585217366] | 0.0003948211669921875 | CI 不含 0 且 p<0.05 |
| K=10（次要） | M−R | 20 | -0.020532483194683197 | -0.021587525182617417 | [-0.05036347307241179, -0.003436520208131788] | 0.04405403137207031 | CI 不含 0 且 p<0.05 |

### 3.4 负控制（m1.negative_control_checks）

- K=0 组 RMSE：R=2.1197442749159547、P=1.4272160593355656、M=1.4183756507878262；K=0 随机初始化臂最差=true（最差臂 R）。
- label-shuffle 负控制上 MAML 相对预训练优势=-0.001791347919281705（meta_test 上为 0.013730479463645695），优势回落=true。
- OOD K=5 M RMSE=1.023160461535162；ood_degraded_vs_meta_test=false（预期 OOD 上升，实测未上升，列为待查限制，不作为正面结论）。

## 4. M2 结果

### 4.1 主终点可用性（best_feasible_value）

| split | 臂 | n_total | n_finite | n_null | min | mean | max |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| meta_test | OPT-BO-rand | 100 | 2 | 98 | 1.3184193592143387 | 1.3921150000413935 | 1.4658106408684481 |
| meta_test | OPT-BO-MAML-init | 100 | 0 | 100 | null | null | null |
| meta_test | OPT-DE | 100 | 0 | 100 | null | null | null |
| meta_test_ood | OPT-BO-rand | 50 | 0 | 50 | null | null | null |
| meta_test_ood | OPT-BO-MAML-init | 50 | 0 | 50 | null | null | null |
| meta_test_ood | OPT-DE | 50 | 0 | 50 | null | null | null |

OPT-BO-rand 的 gap_to_reference（n_finite=2）均值=0.6974555844120012；first_feasible_eval_index（n_finite=2）均值=50.5。主终点因 n_finite 在臂间失衡而不可比，以下仅报告预先声明的 A7 fallback 指标。

### 4.2 A7 fallback 描述统计

| split | 臂 | best_objective_raw 均值 | 中位 | 约束违反和均值 | 中位 | feasible_hit_rate 均值 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| meta_test | OPT-BO-rand | 0.808731606195756 | 0.9804166742344513 | 0.9631083640547611 | 0.7155377161388597 | 0.0003125 |
| meta_test | OPT-BO-MAML-init | 0.835828323284089 | 1.0404854433002844 | 0.924901463912512 | 0.7951025119445383 | 0.0 |
| meta_test | OPT-DE | 0.8501261145880554 | 1.1266250975090921 | 1.3818024830129656 | 1.163300346509415 | 0.0 |
| meta_test_ood | OPT-BO-rand | 1.18696641110554 | 1.2502599766414475 | 1.245365143554399 | 1.0858301534276316 | 0.0 |
| meta_test_ood | OPT-BO-MAML-init | 1.2732174962816691 | 1.4044063917012033 | 1.1772170480886337 | 0.8679161198649318 | 0.0 |
| meta_test_ood | OPT-DE | 1.183293079257971 | 1.3658370817030447 | 1.846640730893884 | 1.4950012184627965 | 0.0 |

### 4.3 与参考臂 OPT-BO-rand 的配对比较（预先声明 fallback）

| split | 指标 | 对比臂 | n | 均值差 | 中位差 | 95% CI | Wilcoxon p |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| meta_test | best_objective_raw | OPT-BO-MAML-init − rand | 100 | 0.027096717088332944 | -0.012437043068222187 | [-0.07424225759273084, 0.06674580761003293] | 0.8689128190274791 |
| meta_test | best_objective_raw | OPT-DE − rand | 100 | 0.0413945083922995 | 0.043122220084671786 | [-0.03688282341270904, 0.1316838633845258] | 0.32201859899733143 |
| meta_test | min_constraint_violation_sum | OPT-BO-MAML-init − rand | 100 | -0.038206900142249284 | -0.007882719346085143 | [-0.10339492770448677, 0.10108321753660071] | 0.9670887024899815 |
| meta_test | min_constraint_violation_sum | OPT-DE − rand | 100 | 0.4186941189582042 | 0.34687010382691297 | [0.14958818011667696, 0.5575462622685858] | 1.3584976082693048e-06 |
| meta_test_ood | best_objective_raw | OPT-BO-MAML-init − rand | 50 | 0.08625108517612905 | 0.11684484705195242 | [-0.0144320989743294, 0.16396755981486105] | 0.031261656763490464 |
| meta_test_ood | best_objective_raw | OPT-DE − rand | 50 | -0.0036733318475688304 | 0.0 | [-0.09097188139104073, 0.06813497287340453] | 0.9954969422956927 |
| meta_test_ood | min_constraint_violation_sum | OPT-BO-MAML-init − rand | 50 | -0.06814809546576539 | -0.26315222361977086 | [-0.40847615388739766, 0.05593542677797397] | 0.4042577575813002 |
| meta_test_ood | min_constraint_violation_sum | OPT-DE − rand | 50 | 0.6012755873394848 | 0.29255736347205424 | [0.0, 0.6874203879875715] | 0.0015446673518809207 |

判读（严格）：meta_test 上 MAML-init 的两项 fallback 差 CI 均跨 0，无法与 rand 区分；DE 的约束违反和显著更差（CI 全正）。meta_test_ood 上 MAML-init 的 best_objective_raw 均值差 CI [-0.0144320989743294, 0.16396755981486105] 跨 0，但 Wilcoxon p=0.031261656763490464，二者口径不一致，按保守原则不宣称显著。

### 4.4 可行性、失败与预算执行

- feasible_hit_rate：meta_test 仅 OPT-BO-rand mean=0.0003125、max=0.015625，其余臂为 0；与 F-QE 可行域体积约 1e-6、B=64 预期 0 可行一致。
- n_runs=750、n_evaluations=48000（750×64）；failures n_failed_evaluations=0。
- 负控制任务在 M2 中按协议单列：negative_control_in_m2=false，evaluated_splits=['meta_test', 'meta_test_ood']；仅用于 M1 label-shuffle 诊断，不进入 M2 主矩阵。

## 5. 与基线/预期的对照

### 5.1 克隆臂（仅描述性，不用于推断或结论）

| split | 臂 | best_feasible_value n_finite/n_null | best_objective_raw 均值 | 约束违反和均值 | feasible_hit_rate 均值 |
| --- | --- | --- | ---: | ---: | ---: |
| meta_test | OPT-BO-pretrain | 0/100 | 0.8185187599190629 | 1.0276588559122086 | 0.0 |
| meta_test | OPT-BO-MAML | 2/98 | 0.8042217549373349 | 0.9906410898004744 | 0.0003125 |
| meta_test_ood | OPT-BO-pretrain | 0/50 | 1.2192004208909568 | 1.2998680929375963 | 0.0 |
| meta_test_ood | OPT-BO-MAML | 0/50 | 1.2609828871086268 | 1.25113224869581 | 0.0 |

警告：OPT-BO-pretrain / OPT-BO-MAML 在 P4-CODE 与 OPT-BO-rand 同机制同初始点，标 CLONE_OF_OPT-BO-rand；预注册终点统计、图、回执与结论只引用可识别臂（M0 v1.4 §10.1）。 本报告任何主终点/fallback 结论均未使用克隆臂。

### 5.2 与预注册预期的对照

- M1：K=5 主终点 M 优于 P、R（95% CI 不含 0）；K=0 时 M 与 P 差异 CI [-0.016851395935849722, -0.0029893594901730935] 不含 0，但 Wilcoxon p=0.0758514404296875≥0.05（bootstrap 与 Wilcoxon 口径不一致，保守视为不显著），符合无自适应步时无优势的预期；K=1 混合；K=10 仍有利于 M。
- M2：主终点按预注册的 null_reporting_rule 如实报告 null 计数；预期可行命中极稀疏，实测 meta_test rand 2/100 命中、其余为 0，与该预期方向一致，但样本量不足以支持臂间比较。
- M2 OOD：三臂主终点全 null；fallback 仅作描述，OOD 结果不支持泛化性优越结论。

## 6. 局限与不声明事项

- 合成性（SYNTHETIC_ONLY）：评估器为解析合成族，不对应任何真实飞机/物理求解；不能外推到真实气动、真实 12D 设计或真实燃油标签。
- 未批准事项（summary.not_approved）：P4-REAL-LF；P4-MULTIFIDELITY-REAL；REAL-CROSS-TASK-META-TRAINING —— 本报告不做对应声明。
- M2 主终点不可比：n_finite 失衡（rand 2/100，其余 0），不得声称任一臂优于基线，也不得声称等价。
- fallback 结论的边界：MAML-init 与 rand 在 meta_test 两项 fallback 上不可区分；DE 仅显示约束违反和更差；OOD 上 bootstrap CI 与 Wilcoxon p 存在口径不一致（见 4.3），保守不宣称显著。
- 克隆臂（OPT-BO-pretrain/OPT-BO-MAML）与 OPT-BO-rand 同机制，仅描述性；其有限 best_feasible_value 数值不得用于归因。
- 负控制中 OOD 未如预期退化（ood_degraded_vs_meta_test=false），属待查异常，不构成泛化性正面证据。
- M1 统计为单一 seed=42 的 20 个配对 task；M2 为 5 个优化种子；统计功效有限。
- 图 4（VSPAERO 版本面板/密度敏感性）状态为 NOT_RUN，原因见第 8 节；本报告未提供任何 VSPAERO 数据。
- physical_call_count=0 仅由 physics_guard 断言保证；本报告不验证真实求解器，也不构成对 D-12D-004 的结论。

## 7. 复现方法

- 代码版本：git_sha=36d58918fc5f1002a599c45661e3cd389ce96c19（git_sha_label 与 git_sha 相同）；worktree_dirty=false；config_hash=0d393de6ae1d56b3c62308d977678581025f63ec74ce92c6c43201436c902f8b；git 仓库 <REPO_ROOT>（P4 worktree，机器相关；本文以占位符代替本机绝对路径）。
- 运行入口：使用已提交的 research/concorde_metaopt/meta_learning/offline_runner（run_offline_study / OfflineRunnerConfig），由 EXT 包装脚本 <EXT_ROOT>/p4-meta-dev/a6/run_p4_m2.py 调用；等价 CLI：

    python -m research.concorde_metaopt.meta_learning.offline_runner --run-id <RUN_ID> --output-root research/concorde_metaopt/optimization_runs --seed 42 --max-meta-steps 2000 --budget 64 --ks 0 1 5 10 --optimization-seeds 0 1 2 3 4 --determinism-reruns 3

- 环境：python 3.11.17，matplotlib 3.11.2，numpy 2.4.6，scipy 1.17.1，torch 2.8.0，platform Windows-10-10.0.26200-SP0，cpu_count 32，device=cpu。
- 数据清单：data_manifest.json file_count=26，total_bytes=3276410（文本 canonical-LF、PNG raw、外置工件 raw），binary_file_count=5，external_artifacts=3 个（root=<EXTERNAL_ROOT>/concorde_metaopt/p4-meta-m2-offline-20261102T092828Z/raw_artifacts，external_total_bytes=82990422，不计入 file_count/total_bytes，逐文件 raw sha256 记录于 external_artifacts 段）；manifest 自身 canonical sha256=eada0111df6569f86d9cb4084093e395e63459c6ac12d61c5c6d8ab516a55918；本报告生成时脚本核对了清单计数（file_count 与 files 长度一致）。
- 出图命令（已执行，生成第 8 节 5 张 PNG 与本报告数字审计 CSV）：

    MPLCONFIGDIR=<cache> python <EXT_ROOT>/p4-meta-dev/a2/scripts/make_p4_m4_figures.py --run-dir <RUN_DIR> --out-dir <RUN_DIR>/figures --dpi 150

- 出图脚本 sha256=cee891c01df64e9ad0523fe6e0af5d80a1205fca4af71fbf0f00e5ab40fbd9c3（与 manifest 记录一致：true）；图 manifest=figures/make_p4_m4_figures.manifest.json（checks.all_checks_pass=true）；figure_status=figures/figure_status.json（status=GENERATED）。
- 校验：summary.m2 aggregate 与 metrics/optimization_summary.csv 逐值复算，mismatch=0（数值比较 76 项，max_abs_diff=2.220446049250313e-16）；CSV 行数 adaptation_results=480、optimization_summary=750、training_history=4050；PNG 磁盘 sha256 与 figure_status 全部一致，fig3 序列仅含可识别臂，fig4 状态 NOT_RUN。
- 首次尝试（不属于本 run，仅存于 EXT 日志）：run_id p4-meta-m2-offline-20261102T071103Z 在 build_m2 阶段因等预算断言失败（OPT-DE true_evals_used=24 != budget=64）终止；修复后本 run（092828Z）完成。来源：EXT/p4-meta-dev/a6/run_p4_m2_progress_failed_first.log 与 run_p4_m2_summary_failed_first.json，不进入 data_manifest。

## 8. 图表清单

| 键 | 文件 | 状态 | 字节 | sha256（前 16） | 说明 |
| --- | --- | --- | ---: | --- | --- |
| fig1_meta_training_loss | fig1_meta_training_loss.png | GENERATED | 130569 | 10dfde94315744af | 中文版元训练损失曲线（training_history.csv，2000 步；验证损失 NOT_AVAILABLE） |
| fig2_k_shot_adaptation | fig2_k_shot_adaptation.png | GENERATED | 132333 | 098e1015ced303c7 | K-shot 自适应 MAE/RMSE（meta_test；R/P/M，K=0/1/5/10；误差条 ±std） |
| fig3_equal_budget_convergence | fig3_equal_budget_convergence.png | GENERATED | 99114 | 124a7c58d05c2fdb | 等预算收敛（仅 3 个可识别臂，min-max 带宽；克隆臂排除） |
| fig4_vspaero_version_panel_density | fig4_vspaero_version_panel_density.png | NOT_RUN | 85245 | f3cb9c1840e1736e | NOT_RUN：VSPAERO 版本面板/密度敏感性无合法数据，归 Issue #4 D-12D-004（V1 4/10 starts 冻结），不画假数据；占位排版已做 bbox 无重叠自检 |
| fig5_budget_gate_progress | fig5_budget_gate_progress.png | GENERATED | 154355 | 054b50f33c69c633 | 预算与门禁进度（5 臂计划/实际 64、物理调用 0、门禁表 PASS、not_approved 红字） |

- metrics_summary.csv：6283 行，13 列（figure,panel,series,x,y_mean,y_std,y_min,y_max,n,unit,status,source,note）；每张图的数据点均已记录，可离线复核。
- 图 manifest 检查项：{'all_five_png_written': True, 'every_png_gt_20kb': True, 'min_png_bytes': 85245, 'png_signature_and_dimensions_ok': True, 'metrics_summary_written': True, 'fig4_not_run_no_fake_data': True, 'fig4_placeholder_no_text_overlap': True, 'fig3_excludes_clone_arms': True, 'font_cjk_coverage': True, 'all_checks_pass': True}。
- 图4 占位排版于 task-88 修订：原因段按语义拆为三行、去除文字背景点状 hatch，并用 matplotlib 渲染 bbox 自检（pairwise_overlaps=0、outside_inner_box=0、min_body_vertical_gap=26.51px）；其余四图与 task-87 交付逐字节一致（fig1 130569、fig2 132333、fig3 99114、fig5 154355 B）。
- 字体：Microsoft YaHei（C:/Windows/Fonts/msyh.ttc，CJK=true，missing_characters=[]，characters_checked=209）；5 图均经人工目检无豆腐块。

## 9. 下一步

- M3（独立评审）：审阅本稿、m4_report_numbers.csv 与 5 图；重点核验 M2 主终点 n_finite 计数、A7 fallback 的 CI/p 口径、克隆臂排除、图 3 是否仅 3 臂、图 4 是否 NOT_RUN；评审通过前本稿不得外发。
- 评审后由 Lead 决定是否提交 run 目录 figures/ 与报告到仓库分支；提交前需更新 data_manifest 并重算 sha256。
- 待查项：(a) 负控制 OOD 未退化（ood_degraded_vs_meta_test=false）；(b) OOD best_objective_raw 的 bootstrap CI 与 Wilcoxon p 不一致口径的说明；(c) M2 主终点功效不足，若需臂间结论须在获批后提高预算或调整任务族（不得默认启动）。
- 图 4 保持 NOT_RUN，待 D-12D-004 合法数据（当前 V1 已停止冻结、starts 4/10、剩余 6 关闭不结转）。
- 本稿不含任何新 run、不含任何真实物理调用；后续动作均需 owner/Lead 书面批准。


## 10. 打包与提交说明（Lead）

- 大文件外置：evaluations.jsonl（41,969,526 B）、archive/.../observations.jsonl（20,555,285 B）、metrics/optimization_history.csv（20,467,611 B）共 82990422 B 已移至仓库外 <EXTERNAL_ROOT>/concorde_metaopt/p4-meta-m2-offline-20261102T092828Z/raw_artifacts/（outside_git=true）；run 目录内保留 summary/metrics/CSV 派生文件；external_artifacts 段记录每个外置文件的 raw sha256，manifest 的 file_count/total_bytes 只统计仓库内文件。
- data_manifest：file_count=26、total_bytes=3276410、external_file_count=3、external_total_bytes=82990422、schema_version=2.0.0；manifest 自身 canonical sha256=eada0111df6569f86d9cb4084093e395e63459c6ac12d61c5c6d8ab516a55918；可从干净 checkout 复现文本文件的 canonical-LF sha256。post-M3 修正（§11）已把 m4_report_numbers.csv 纳入包内并更新本清单。
- 提交范围：run 目录（26 个包内文件 + data_manifest.json 自身；含 5 张图、figures 元数据与 m4_report_numbers.csv）+ 本报告 + docs/planning/p4_meta_learning_design_20261102.md（v1.4a）；未含 P5 未跟踪文件、未改基线代码、未合并 main。post-M3 修正在父提交 f92a7f2 之上追加 follow-up 提交（仅 run 目录产物与本报告）。
- 门禁：determinism=PASS、finite_difference=PASS、reference_solutions=PASS、physics_guard=PASS（expected=0）、physical_call_count=0；M2 主终点因 n_finite 失衡不可比，仅报告 A7 fallback 且不宣称优于基线。
- 复核状态：A5 已签发 M1 rev5 APPROVE_TO_START_M2、A3 rev5 隔离 PASS 17/17；M3 独立终审（A5，f92a7f2）APPROVE_FOR_ISSUE_RECEIPT_AND_PR（0 blocker/0 major/4 minor，见 §11）；A3 对 f92a7f2 的隔离复核 PASS 25/25；post-M3 修正的 delta 复核结论以独立复核为准。run 实际执行于父提交 36d5891，f92a7f2 及 follow-up 仅为打包提交。

## 11. post-M3 修正记录（M3-F01..M3-F04）

- 触发：A5 M3 独立终审（task-89，target f92a7f2）verdict=APPROVE_FOR_ISSUE_RECEIPT_AND_PR，0 blocker / 0 major / 4 minor。
- M3-F01（m4_report_numbers.csv 未随包）：已复制到 run 根目录 m4_report_numbers.csv（404 行，sha256 774c20203088dc6da6c4c2bc08143b9966057be2e838808a64d63bd27efd486a，与 EXT 源文件逐字节一致），并纳入 data_manifest.json。
- M3-F02（run README 产物/图表述不一致）：README 产物段已改为"5 张图已生成：fig1/2/3/5 GENERATED、fig4 NOT_RUN 归 Issue #4 D-12D-004"；evaluations.jsonl 与 metrics/optimization_history.csv 移入 external_artifacts 说明。
- M3-F03（报告图时间戳旧）：生成时间改为 2026-11-02T11:21:56Z（最终 figure_status），保留初版 11:03:35Z 供追溯。
- M3-F04（本机绝对路径）：报告与 figures/make_p4_m4_figures.manifest.json 中的本机绝对路径替换为 <REPO_ROOT> / <EXT_ROOT> / <EXTERNAL_ROOT> 占位符；PNG 哈希与 manifest 校验项未变。
- 包内影响：新增 m4_report_numbers.csv → data_manifest file_count 25→26、total_bytes 3,217,559→3,276,410 B、manifest 自身 canonical sha256=eada0111df6569f86d9cb4084093e395e63459c6ac12d61c5c6d8ab516a55918。
- 未变项：5 张 PNG 与 figure_status 哈希、metrics/*.csv、run 在父提交 36d5891 执行的事实、M3 已核验的统计数值与 n_finite 计数。
- delta 复核：follow-up 提交的 A5/A3 复核结论以独立复核记录为准；本稿不代签。
- 不声明：本修正不改变任何结论、门禁状态或物理调用计数（physical_call_count=0）。
