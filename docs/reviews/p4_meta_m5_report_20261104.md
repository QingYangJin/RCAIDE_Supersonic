# P4 元学习 M5 正式 run（FORMAL）中文报告：合成任务族上的等预算优化对照（rev5 定稿）

- run_id：p4-meta-m5-formal-20261104T1018Z
- 版本：rev5 final（2026-11-05T05:30:07.273565+08:00，A2 定稿）；相对 rev4（922d0a94）仅 §4.5 数据源声明一行绝对路径改为 EXT 相对路径（A5-M5A2-04，rev5 已修），数字/表格/结论不变；本 rev 仅将头注版本与批准链对齐 A5-M5PKG-02。
- A5 复核状态：task-170 判 APPROVE_FOR_M5_REPORTING（0 blocker / 0 major / 2 minor = A5-M5A2-02 与 A5-M5A2-03，均已在 rev4 关闭）；task-175 判 CHANGES_REQUESTED（唯一 minor A5-M5A2-04，rev5 修复并关闭）；task-177 判 APPROVE_FOR_M5_PACKAGING（0 blocker / 0 major / 0 minor new）。A5-M5-04 为既有 minor（OPEN_PREEXISTING_DISCLOSED，见 §7）。历史：task-153 曾对 attempt1 判 CHANGES_REQUESTED（1 blocker / 2 major / 4 minor），已由 attempt2 修正。
- 生成：A2（零求解、只读证据）；本文件为 rev5 定稿报告（final），提交目标路径 docs/reviews/p4_meta_m5_report_20261104.md
- 状态：VALID（study_scale=FORMAL, stage=holdout）；数据来源 SYNTHETIC_TEST；物理调用 physical_call_count=0
- 本报告所有数字来自该 run 的 summary.json / statistics.csv / endpoint_summary.csv / optimization_summary.csv / figure_data.json；已做一致性核对（见第 8 节），未运行任何求解器、未写仓库、未访问网络。

## 1 研究目的与范围

- 问题：在单一合成解析任务族上，等预算条件下比较 MAML 元初始化 + 贝叶斯优化（MAML-init）、预训练代理初始化 + 贝叶斯优化（pretrain-init）、随机初始化 + 贝叶斯优化（random）与等预算差分进化（DE）四种优化臂的最终可行解质量与可行命中率。
- 任务族：F-QE-feasible-v2（v2，radius_base=0.75；参考解 u*=c；gap = f(u_best) − f(u*)）。
- 评价器：synthetic__analytic__12d_lifting_surfaces__v2（合成解析 evaluator；12D 升力面设计空间；非真实物理求解器）。
- 范围声明：SYNTHETIC_ONLY。本 run 的结论仅适用于该合成任务族与解析 evaluator，不得外推到真实飞机、真实气动/燃油或任何真实求解器结果。
- 预注册：96 个预注册比较（6 组臂×参照 × 4 个主终点 × 2 split × 2 预算），统计方案见第 2 节；本报告不新增事后比较。holdout 为单轮正式评估。

## 2 设计与预注册

- 数据划分（任务数）：meta_train 60 / meta_validation 20 / meta_test 20 / meta_test_ood 10 / negative_control 10。
- holdout 计划：预算 [64, 128]，每组每预算 8 runs、15 组；共 300 组 / 4800 runs；meta_test 20 任务×10 优化种子、meta_test_ood 10 任务×10 优化种子；meta_seeds=[0, 1, 2]、optimization_seeds=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]、workers=16。
- 主终点：best_feasible_value、gap_to_reference、feasible_hit_rate、first_feasible_evaluation_index（lower_better；差值为臂 − 参照）。
- 推断：配对单位=task（任务内先跨 meta_seed、再跨优化种子聚合）；bootstrap 百分位 95% CI；Wilcoxon 符号秩；Holm 家族=每个 split×budget 下 6 组比较×4 个主终点（24 个检验）；fallback 指标不参与推断。
- 门禁：gate=UNLOCKED；冻结族 sha256=5e7a9d1f2acd32a4…；预注册 sha256=4f8a9a1fd05f0648…；校准报告 sha256=c5f8096d02abf5da…；split_hash=3c206ebbe35e848a…。
- 可识别性：IDENTIFIABLE（臂数 4、实现数 3、代码路径数 4、clone 臂 []）。

## 3 执行事实与门禁

- 结果：status=VALID；runs=4800；真实（合成）评价次数=460800；history 行数=460800；holdout 组数=300；runtime_s=8960.327（holdout_wall_s=8942.368）。
- run 启动/结束 HEAD 披露（A5-M5A2-02）：run 启动时仓库 HEAD=7e94973；运行窗口内外部 M6 打包提交把 HEAD 推进到 183616c，故 run_config.json 记录的 git_sha=183616c…（-dirty）是 run 结束时 HEAD，并非 M5 启动 HEAD。A5 独立核验 m5_runner.py / m5_arms.py / baseline_arms.py 等 M5 代码与产物在 7e94973 与 183616c 下相同、git diff 7e94973..183616c 不含 M5 文件，本 run 数值与结论不受 HEAD 推进影响。
- 确定性：PASS（重跑 3 次，300 组，mismatch=0；排除列 wall_s / proxy_scoring_cost_json）；但 run 未保存原始 rerun digest/摘要（raw_digest_manifest=NOT_STORED），第三方无法独立复算该结论，仅能采信 summary 字段（A5-M5-07 披露）。
- 训练损失（A5-M5-06 修正）：MAML 代理训练损失（training_history.csv，3 元种子按迭代均值）：loss_query it0=3.334090 -> it199=1.351967；loss_support it0=3.279149 -> it199=1.312956；预训练代理终点 loss_query（每元种子 1 值）=[1.643786, 1.673174, 1.648085]。这些是 M5 实测值，不得引用旧 run（M2/M6）的 2.77199 -> 1.25405 数值（A5-M5-06）。
- 物理守卫：PASS（期望物理调用 0）；物理调用实测 0。
- 公平性门禁：PASS（4 臂 / 4800 记录 / 2400 组；去重阈值 1e-12；组键 ['task_id', 'seed', 'budget', 'meta_seed']；初始设计数 8）。
- 旧 M2 run 不可变性：PASS（before/after 各 26 文件，mismatch=0；manifest sha256=acaab106388f8342…）。
- 结论许可：conclusions_allowed=True；message：SYNTHETIC_ONLY：仅解析合成任务族 F-QE-feasible-v2 与 12D 设计空间解析 evaluator；physical_call_count=0；结论不得外推到真实飞机/真实求解器。

## 4 结果

### 4.1 描述统计（endpoint_summary.csv 中位数）

| 数据划分 | 预算 | 臂 | best_feasible_value 中位 | gap_to_reference 中位 | feasible_hit_rate 中位 | n_runs |
|---|---|---|---|---|---|---|
| meta_test | 64 | M5-BO-MAML-init | 0.3856 | 0.3809 | 0.0576 | 600 |
| meta_test | 64 | M5-BO-pretrain-init | 0.4019 | 0.3579 | 0.0573 | 600 |
| meta_test | 64 | M5-BO-random | 0.4158 | 0.3420 | 0.0758 | 200 |
| meta_test | 64 | M5-DE | 0.5498 | 0.5265 | 0.0164 | 200 |
| meta_test | 128 | M5-BO-MAML-init | 0.2718 | 0.2869 | 0.1310 | 600 |
| meta_test | 128 | M5-BO-pretrain-init | 0.2687 | 0.2863 | 0.1296 | 600 |
| meta_test | 128 | M5-BO-random | 0.2700 | 0.2704 | 0.1437 | 200 |
| meta_test | 128 | M5-DE | 0.2857 | 0.3271 | 0.2309 | 200 |
| meta_test_ood | 64 | M5-BO-MAML-init | 0.6759 | 0.3001 | 0.0047 | 300 |
| meta_test_ood | 64 | M5-BO-pretrain-init | 0.6749 | 0.3012 | 0.0044 | 300 |
| meta_test_ood | 64 | M5-BO-random | 0.6465 | 0.3030 | 0.0055 | 100 |
| meta_test_ood | 64 | M5-DE | 0.7557 | 0.3803 | 0.0016 | 100 |
| meta_test_ood | 128 | M5-BO-MAML-init | 0.5766 | 0.2523 | 0.0115 | 300 |
| meta_test_ood | 128 | M5-BO-pretrain-init | 0.5796 | 0.2542 | 0.0111 | 300 |
| meta_test_ood | 128 | M5-BO-random | 0.5725 | 0.2558 | 0.0121 | 100 |
| meta_test_ood | 128 | M5-DE | 0.4655 | 0.2083 | 0.0672 | 100 |

图3（等预算可行命中率）与图4（等预算最优可行值/gap 收敛曲线）见第 9 节图表清单；可行命中率图按 split×预算分面，x 轴第二行同时披露无可行解 runs 占比（null_run_fraction）。

### 4.2 主终点 best_feasible_value 的预注册推断（臂 − 参照；负值=更好）

**meta_test，预算 64**

| 比较（臂 − 参照） | mean diff | 95% CI | Wilcoxon p | Holm p | 判定 |
|---|---|---|---|---|---|
| MAML-init vs pretrain-init | 0.00679 | [-0.0079, 0.0124] | 0.4980 | 1.0000 | 不显著 |
| MAML-init vs random | 0.02390 | [-0.0099, 0.0416] | 0.1893 | 1.0000 | 不显著 |
| pretrain-init vs random | 0.01712 | [-0.0051, 0.0293] | 0.2024 | 1.0000 | 不显著 |
| DE vs MAML-init | 0.14574 | [0.0395, 0.2506] | 0.0020 | 0.0323 | 显著·更差 |
| DE vs random | 0.16263 | [0.0618, 0.2670] | 0.0010 | 0.0174 | 显著·更差 |

**meta_test，预算 128**

| 比较（臂 − 参照） | mean diff | 95% CI | Wilcoxon p | Holm p | 判定 |
|---|---|---|---|---|---|
| MAML-init vs pretrain-init | -0.00079 | [-0.0022, 0.0020] | 0.8721 | 1.0000 | 不显著 |
| MAML-init vs random | 0.00704 | [-0.0009, 0.0065] | 0.2024 | 1.0000 | 不显著 |
| pretrain-init vs random | 0.00783 | [-0.0016, 0.0051] | 0.3488 | 1.0000 | 不显著 |
| DE vs MAML-init | 0.05892 | [0.0190, 0.0595] | 0.0001 | 0.0024 | 显著·更差 |
| DE vs random | 0.06596 | [0.0270, 0.0735] | 1.91e-05 | 0.0004 | 显著·更差 |

**meta_test_ood，预算 64**

| 比较（臂 − 参照） | mean diff | 95% CI | Wilcoxon p | Holm p | 判定 |
|---|---|---|---|---|---|
| MAML-init vs pretrain-init | -0.00683 | [-0.0290, 0.0084] | 1.0000 | 1.0000 | 不显著 |
| MAML-init vs random | 0.02259 | [0.0000, 0.0585] | 0.1094 | 1.0000 | 不显著 |
| pretrain-init vs random | 0.02942 | [-0.0032, 0.0785] | 0.1562 | 1.0000 | 不显著 |
| DE vs MAML-init | 0.05267 | [-0.1197, 0.1801] | 0.4688 | 1.0000 | 不显著 |
| DE vs random | 0.08131 | [-0.0647, 0.2120] | 0.3750 | 1.0000 | 不显著 |

**meta_test_ood，预算 128**

| 比较（臂 − 参照） | mean diff | 95% CI | Wilcoxon p | Holm p | 判定 |
|---|---|---|---|---|---|
| MAML-init vs pretrain-init | 0.00113 | [-0.0021, 0.0045] | 0.5781 | 1.0000 | 不显著 |
| MAML-init vs random | 0.00936 | [-0.0002, 0.0217] | 0.1953 | 1.0000 | 不显著 |
| pretrain-init vs random | 0.00823 | [-0.0020, 0.0182] | 0.2500 | 1.0000 | 不显著 |
| DE vs MAML-init | -0.04157 | [-0.0780, -0.0111] | 0.0645 | 1.0000 | 不显著 |
| DE vs random | -0.03221 | [-0.0783, 0.0046] | 0.1602 | 1.0000 | 不显著 |

关键读数：
- meta_test 预算 64：MAML-init vs random 平均差 0.02390（95% CI [-0.0099, 0.0416]，Holm p=1.0000，不显著）；MAML-init vs pretrain-init 平均差 0.00679（CI [-0.0079, 0.0124]，Holm p=1.0000，不显著）。
- meta_test 预算 128：MAML-init vs random 平均差 0.00704（CI [-0.0009, 0.0065]，Holm p=1.0000，不显著）；MAML-init vs pretrain-init 平均差 -0.00079（CI [-0.0022, 0.0020]，Holm p=1.0000，不显著）。
- meta_test_ood 预算 64/128：MAML-init vs random 平均差 0.02259 / 0.00936（Holm p=1.0000 / 1.0000，不显著 / 不显著）。
- DE 显著更差：meta_test 预算 64 DE vs random 平均差 0.16263（CI [0.0618, 0.2670]，Holm p=0.0174，显著·更差）；DE vs MAML-init 0.14574（CI [0.0395, 0.2506]，Holm p=0.0323，显著·更差）。meta_test 预算 128：DE vs random 0.06596（Holm p=0.0004，显著·更差）；DE vs MAML-init 0.05892（Holm p=0.0024，显著·更差）。

### 4.3 可行命中率 feasible_hit_rate 的显著结果（Holm p<0.05）

| 数据划分 | 预算 | 比较 | mean diff（正=更好） | 95% CI | Holm p | 判定 |
|---|---|---|---|---|---|---|
| meta_test | 64 | M5-BO-MAML-init vs M5-BO-random | -0.01526 | [-0.0167, -0.0057] | 0.0056 | 显著·更差 |
| meta_test | 64 | M5-BO-pretrain-init vs M5-BO-random | -0.01596 | [-0.0172, -0.0049] | 8.39e-05 | 显著·更差 |
| meta_test | 64 | M5-DE vs M5-BO-random | -0.08039 | [-0.0891, -0.0250] | 4.58e-05 | 显著·更差 |
| meta_test | 64 | M5-DE vs M5-BO-MAML-init | -0.06513 | [-0.0799, -0.0115] | 4.58e-05 | 显著·更差 |
| meta_test | 128 | M5-BO-MAML-init vs M5-BO-random | -0.01228 | [-0.0161, -0.0061] | 9.16e-05 | 显著·更差 |
| meta_test | 128 | M5-BO-pretrain-init vs M5-BO-random | -0.01232 | [-0.0142, -0.0064] | 0.0020 | 显著·更差 |
| meta_test_ood | 128 | M5-DE vs M5-BO-random | 0.04586 | [0.0172, 0.0742] | 0.0469 | 显著·更好 |
| meta_test_ood | 128 | M5-DE vs M5-BO-MAML-init | 0.04721 | [0.0172, 0.0767] | 0.0469 | 显著·更好 |

- 需要如实披露：MAML-init 在 meta_test 两个预算下的可行命中率均显著低于 random 基线（预算 64 平均差 -0.01526，Holm p=0.0056；预算 128 平均差 -0.01228，Holm p=9.16e-05），即在本合成族的可行率维度上 MAML 初始化不仅没有优势，反而更差。
- meta_test_ood 预算 128：DE 的可行命中率显著高于 MAML-init（平均差 0.04721，Holm p=0.0469），说明 DE 在该 OOD 预算下更常找到可行点；但其最优可行值仍显著更差（见 4.2），两者不矛盾。

### 4.4 first_feasible_evaluation_index

- 数据覆盖（attempt2 修正）：optimization_summary.csv 中非空 first_feasible_evaluation_index = 3548 / 4800（73.92%），空值 1252 / 4800（26.08%）。未找到可行解的 run 该终点恒为 null（本 run best_feasible_value 为空的 run 数 = 1252），本报告不把 null 当作 0、不插值。
- 缺陷与修复（A5-M5-01，blocker）：attempt1 中该列全为 null（4800/4800），根因是 baseline_arms.py 输出的键 first_feasible_eval_index 与 m5_runner.py 期望列名 first_feasible_evaluation_index 不一致，且 ENDPOINT_ROW_KEYS 无别名映射；attempt2 runner 增加别名映射并重跑 holdout，覆盖率由 0 提升至上述值。该修复只补全记录列，不改变各优化臂的评价序列与终点值。（对应 A5-M5-01 blocker；A5-M5-05 指出 attempt1 把该终点写成“未记录”，本版改为按 CSV 实测覆盖率披露。）

statistics.csv 中该终点的预注册比较（仅对有可行解的 run 做 task 聚合；first_feasible 越低越好，差值为臂 − 参照）：

| 数据划分 | 预算 | 比较（臂 − 参照） | mean diff | 95% CI | Wilcoxon p | Holm p | 判定 |
|---|---|---|---|---|---|---|---|
| meta_test | 64 | M5-BO-MAML-init vs M5-BO-random | 0.66703 | [-0.9667, 3.2167] | 0.3300 | 1.0000 | 不显著 |
| meta_test | 64 | M5-BO-MAML-init vs M5-BO-pretrain-init | -1.00334 | [-2.6333, -0.2685] | 0.0362 | 0.5073 | 不显著 |
| meta_test | 64 | M5-BO-pretrain-init vs M5-BO-random | 1.67038 | [-0.8500, 4.6611] | 0.2162 | 1.0000 | 不显著 |
| meta_test | 64 | M5-DE vs M5-BO-random | 13.95934 | [11.2222, 16.4921] | 1.91e-05 | 0.0004 | 显著·更差 |
| meta_test | 64 | M5-BO-pretrain-init vs M5-BO-MAML-init | 1.00334 | [0.2685, 2.6333] | 0.0362 | 0.5073 | 不显著 |
| meta_test | 64 | M5-DE vs M5-BO-MAML-init | 12.65193 | [6.9375, 16.7524] | 3.81e-06 | 8.39e-05 | 显著·更差 |
| meta_test | 128 | M5-BO-MAML-init vs M5-BO-random | 3.72155 | [0.5833, 4.7667] | 0.0042 | 0.0675 | 不显著 |
| meta_test | 128 | M5-BO-MAML-init vs M5-BO-pretrain-init | -0.50815 | [-1.4083, 0.7833] | 0.3488 | 1.0000 | 不显著 |
| meta_test | 128 | M5-BO-pretrain-init vs M5-BO-random | 4.22970 | [0.6053, 5.6250] | 0.0094 | 0.1321 | 不显著 |
| meta_test | 128 | M5-DE vs M5-BO-random | 26.92877 | [22.9000, 33.1500] | 3.81e-06 | 9.16e-05 | 显著·更差 |
| meta_test | 128 | M5-BO-pretrain-init vs M5-BO-MAML-init | 0.50815 | [-0.7833, 1.4083] | 0.3488 | 1.0000 | 不显著 |
| meta_test | 128 | M5-DE vs M5-BO-MAML-init | 23.20722 | [19.4667, 28.9778] | 5.72e-06 | 0.0001 | 显著·更差 |
| meta_test_ood | 64 | M5-BO-MAML-init vs M5-BO-random | 1.37622 | [-2.0611, 7.0000] | 0.6562 | 1.0000 | 不显著 |
| meta_test_ood | 64 | M5-BO-MAML-init vs M5-BO-pretrain-init | 4.27134 | [0.0000, 4.8463] | 0.0625 | 1.0000 | 不显著 |
| meta_test_ood | 64 | M5-BO-pretrain-init vs M5-BO-random | -2.89512 | [-6.9074, 6.8631] | 0.8125 | 1.0000 | 不显著 |
| meta_test_ood | 64 | M5-DE vs M5-BO-random | -3.52183 | [-10.2500, 0.0000] | 0.3125 | 1.0000 | 不显著 |
| meta_test_ood | 64 | M5-BO-pretrain-init vs M5-BO-MAML-init | -4.27134 | [-4.8463, 0.0000] | 0.0625 | 1.0000 | 不显著 |
| meta_test_ood | 64 | M5-DE vs M5-BO-MAML-init | -4.09464 | [-9.2500, 2.0208] | 0.1094 | 1.0000 | 不显著 |
| meta_test_ood | 128 | M5-BO-MAML-init vs M5-BO-random | 2.45988 | [-2.2750, 6.3000] | 0.4609 | 1.0000 | 不显著 |
| meta_test_ood | 128 | M5-BO-MAML-init vs M5-BO-pretrain-init | 0.01127 | [-2.1905, 1.8000] | 1.0000 | 1.0000 | 不显著 |
| meta_test_ood | 128 | M5-BO-pretrain-init vs M5-BO-random | 2.44861 | [-3.0333, 7.1639] | 0.4609 | 1.0000 | 不显著 |
| meta_test_ood | 128 | M5-DE vs M5-BO-random | 18.60060 | [-1.3333, 37.1750] | 0.0273 | 0.6016 | 不显著 |
| meta_test_ood | 128 | M5-BO-pretrain-init vs M5-BO-MAML-init | -0.01127 | [-1.8000, 2.1905] | 1.0000 | 1.0000 | 不显著 |
| meta_test_ood | 128 | M5-DE vs M5-BO-MAML-init | 16.14071 | [2.7857, 38.4833] | 0.0371 | 0.7793 | 不显著 |

- 显著比较数（Holm p<0.05）：4 / 24。
- meta_test / 预算 64：M5-DE vs M5-BO-random，mean diff=13.95934，Holm p=0.0004，显著·更差。
- meta_test / 预算 64：M5-DE vs M5-BO-MAML-init，mean diff=12.65193，Holm p=8.39e-05，显著·更差。
- meta_test / 预算 128：M5-DE vs M5-BO-random，mean diff=26.92877，Holm p=9.16e-05，显著·更差。
- meta_test / 预算 128：M5-DE vs M5-BO-MAML-init，mean diff=23.20722，Holm p=0.0001，显著·更差。
### 4.5 attempt1 vs attempt2 差异披露（A5-M5-01 修复的统计口径影响）

- 数据源声明：attempt2 = 本 run（metrics/statistics.csv、endpoint_summary.csv、optimization_summary.csv、clone_audit.csv 均为 attempt2 版本）；attempt1 = 缺陷归档 EXT/p4-m5m6/lead/m5_formal_attempt1_defective/run_dir_snapshot。本节只解释修复造成的记录/统计口径变化，不把 attempt1 数值当作结果引用。
- 数值 payload（按 budget/meta_seed/arm/task_id/split/seed 对齐 4800/4800 行）：仅 wall_s（4800 行，非确定性耗时）、proxy_scoring_cost_json（内嵌 wall_s，3599 行）与 first_feasible_evaluation_index（3548 行）不同；其余列 0 行差异。first_feasible 空值从 4800/4800 降至 1252/4800（非空 3548 行）。
- statistics.csv：96 行；status=REPORTED 行 72→96（first_feasible 24 行由 NO_DATA→REPORTED）。Holm 家族（split×budget 共 4 族）每族检验数 18→24（每族 4 端点×6 比较；attempt1 中 first_feasible 的 6 个 p 缺失被跳过）。
- 44/96 行 Holm p 发生变化（系统性变大，因族内检验数 18→24）；30/96 行 Wilcoxon p 出现末位变化（并行完成顺序导致的浮点求和/零值处理差异）。

| 预算 | 数据划分 | 终点 | 比较（臂 − 参照） | Holm p（attempt1） | Holm p（attempt2） | Wilcoxon p（attempt1） | Wilcoxon p（attempt2） |
|---|---|---|---|---|---|---|---|
| 64 | meta_test | best_feasible_value | M5-DE vs M5-BO-random | 0.0135 | 0.0174 | 0.0010 | 0.0010 |
| 128 | meta_test | best_feasible_value | M5-DE vs M5-BO-random | 0.0003 | 0.0004 | 1.91e-05 | 1.91e-05 |
| 64 | meta_test | feasible_hit_rate | M5-BO-MAML-init vs M5-BO-random | 0.0060 | 0.0056 | 0.0004 | 0.0003 |
| 128 | meta_test | feasible_hit_rate | M5-BO-MAML-init vs M5-BO-random | 6.87e-05 | 9.16e-05 | 3.81e-06 | 3.81e-06 |

- 结论影响：无方向改变。本报告第 4、5 节全部使用 attempt2 statistics.csv 数值：DE 在 best_feasible_value 上显著更差、MAML-init 的 feasible_hit_rate 在 meta_test 显著更低等结论均保持不变；MAML 仍无可检测优势。

## 5 结论

1. **无可检测的 MAML 优势**：在全部预注册比较中，没有任何“MAML 臂相对参照臂更好且 Holm 校正后显著”的结果（0 项）。meta_test 与 meta_test_ood、预算 64 与 128 下的 best_feasible_value / gap_to_reference 差异均不显著；因此**不得宣称 MAML 优越，也不得宣称其更优或等价**——只能说本 run 未检测到优势。
2. **DE 显著更差**：等预算 DE 在 meta_test 两个预算下的 best_feasible_value 均显著差于 random 与 MAML-init（见 4.2，Holm p 分别为 0.0174 / 0.0323 / 0.0004 / 0.0024），即 DE 显著更差。
3. MAML 初始化的可行命中率在 meta_test 显著低于随机初始化（4.3），说明“元学习初始化更好”的直觉在本合成族上不仅未获支持，可行率维度反而是负向证据。
4. 本 run 是 SYNTHETIC_ONLY 的离线合成实验（physical_call_count=0），以上结论不外推到真实物理、真实飞机或真实求解器；不得用于签核任何 LF/HF 气动门禁。

## 6 公平性与可识别性

- 公平性门禁 PASS：4 臂 / 4800 记录 / 2400 组；去重阈值 1e-12；组键 = (task_id, seed, budget, meta_seed)；初始设计数 8。该门禁保证各臂在同一任务×种子×预算单元内比较，且重复记录被识别。
- 可识别性：IDENTIFIABLE；实现数 3、代码路径数 4、clone 臂 []。clone_audit.csv（MAML-init vs pretrain-init）：mean_initial_overlap=0.7186111111111111、max_initial_overlap=1.0、high-overlap fraction=0.5744444444444444、label=IDENTIFIABLE、clone=false；mean 与 fraction 均未达 clone 判据（mean >= 0.9 且 fraction >= 0.9），故 status=IDENTIFIABLE，但两臂初始设计重叠显著非零，不得表述为「初始设计重叠为 0」（A5-M5-02/03 修正）。
- A5-M5-03 披露（独立成条）：MAML-init 与 pretrain-init 初始设计平均重叠 0.7186（max 1.0、high-overlap fraction 0.5744）显著非零，本报告不以「重叠为 0」表述；因未达 clone 判据（mean 与 fraction 均 >= 0.9）故 label=IDENTIFIABLE、clone=false。
- DE 与 random 臂共享相同初始设计（mean/max overlap=1.0，clone_audit 标签 SAME_INIT_DIFFERENT_ENGINE），但引擎不同（DE/rand/1/bin vs 贝叶斯优化），因此不是克隆、也不是同一实现；这使 DE 与 BO 的差异可归因于搜索引擎而非起点。
- 代理评分成本：MAML-init 与 pretrain-init 各 1800 次代理评分（中位耗时 5.89 / 6.03 ms，取自 figures/figure_data.json 的 proxy_scoring_wall_s_median），random 与 DE 为 0 次；即 MAML 臂额外付出初始化评分成本，但其终点收益未达显著。
- 图5 给出上述公平性/可识别性证据的可视化。

## 7 限制与不得外推

- best_feasible_value 与 gap_to_reference 的空值率均为 26.08%（1252/4800）；first_feasible_evaluation_index 空值 1252/4800（26.08%）、覆盖率 73.92%（3548/4800）。未找到可行解的 run 该终点恒为 null，本报告已如实披露，未把 null 当作 0 或插值。
- A5-M5-04（minor）披露：preregistration.json 中 stopping_rules 被序列化为约 100 个单字符数组（feasible_v2.py 序列化缺陷），属冻结件记录缺陷；按 A5 要求不改冻结 run，不影响预注册比较集合与统计，仅在此披露。
- A5-M5-07（minor）披露：确定性仅由 summary.json 字段证明（3 次重跑 / 300 组 / 0 mismatch），raw_digest_manifest=NOT_STORED，run 目录未保存原始重跑摘要，第三方无法独立复算。
- 单一合成任务族（F-QE-feasible-v2）与单一解析 evaluator；无真实物理/气动/燃油数据，不能外推到真实飞机或真实求解器。
- 图2（K-shot 适应曲线）本阶段 NOT_APPLICABLE_THIS_STAGE（归 M6）；图6（气动门禁进度）NOT_RUN（归 Issue #4 D-12D-004）。本报告不生成假图。
- 元训练损失曲线只有 MAML 代理与预训练代理终点；validation_loss=NOT_AVAILABLE（M5 未记录，按合同不得补造）。预训练代理仅有终点值，无迭代曲线，因此不能据此判断其训练动态。
- 统计：Holm 家族为每个 split×budget 下 24 个检验；配对单位为 task 聚合值；结论不涉及未预注册的事后比较。
- run_config 记录 git_sha_label=183616c7d69d277d16fca2f4b21839062cdbbab0-dirty、worktree_dirty=True：本 run 在 dirty worktree 上执行，代码可追溯性以 run_config 与 environment.json 记录为准；复现时需核对该状态。
- 本报告不宣称 MAML 与 BO 等价，也不宣称 DE 在任何意义上优于/劣于其他方法之外的结论；只报告本 run 的统计结果。

## 8 溯源与复现

- run_id：p4-meta-m5-formal-20261104T1018Z；status=VALID；study_scale=FORMAL；stage=holdout；evaluator_id=synthetic__analytic__12d_lifting_surfaces__v2。
- run HEAD 时序（A5-M5A2-02）：启动 HEAD=7e94973，结束记录 HEAD=183616c…（run_config.git_sha 在 run 结束时写入；-dirty 说明见 §3 与 §7）；M5 产物 blob 在两端一致，数值不受影响。
- 代码/环境：git_sha=183616c7d69d277d16fca2f4b21839062cdbbab0（label=183616c7d69d277d16fca2f4b21839062cdbbab0-dirty，dirty=True）；python=3.11.17；matplotlib=3.11.2；numpy=2.4.6；torch=2.8.0；平台=Windows-10-10.0.26200-SP0；workers=16。
- 门禁哈希：frozen_family=5e7a9d1f2acd32a482195d0ae6255205310d4d5cf4bb38562e05265c4c9da20b；preregistration=4f8a9a1fd05f0648646da58dc669524de81c2c11c38b81d72f28b0be42e565fe；calibration_report=c5f8096d02abf5da4bfd9a5b234bdcedd8a7ffbb98ce7b413eb48e42c116286b；split_hash=3c206ebbe35e848a5137b433d7bc9ca022eb28b4b310ab3ccb9d89c989f33f8a；family_fingerprint=2b78ec7b533fa346f0629d34ed9e3bf525a2ff6295260f21a490452cc1778a42。
- 输入文件 sha256（本报告生成时现算）：summary.json=86e6afe15ba6f539eea2a410a123c366b5660a80374fd13bfc07f6edf49e8746；run_config.json=a55aa75d494e02d8ac1c987de82a1a8de8bc28e167b07a93074eaf505050e5f0；metrics/statistics.csv=65d24923097a63c4de8604ff7968cc5140a30cdd14d2a83f05d8def526e06239；metrics/endpoint_summary.csv=7d20d1aa12078517a873f3dfc61d6895159813d142d14ccbd586d5c8b855b151；metrics/training_history.csv=0bea742c37788c438f4c5b5e7ae2b476e16efeaf0c5ce1c6ed9069a13f4d4ae7；figures/figure_data.json=e405cad190e38c7da4c9cfea86b61e88e440f77d2cfdc8cdb2114364b5507512；README.md=d3cb70155e522165b9b45948713053f8dc7dcc324bc653dea955d4462c086c9c。
- 一致性核对：summary vs optimization_summary.csv 的 runs/评价次数/null 计数/物理调用全部一致（见 8.1）；statistics.csv 与 endpoint_summary.csv 为同一 run 产物。
- 复现命令（run 目录，未在本任务执行）：m6/m5 runner --stage calibration / freeze / holdout 三阶段，--run-id p4-meta-m5-formal-20261104T1018Z --output-root research/concorde_metaopt/optimization_runs；本报告只读 CSV/JSON 重算，未启动任何求解器。
- 图由 EXT 下 scripts/gen_figures_m5.py 从 metrics/training_history.csv、figures/figure_data.json、metrics/clone_audit.csv 生成（300 dpi，Microsoft YaHei，布局自检 0 重叠）；报告由 scripts/build_report_m5.py 生成。

### 8.1 数字一致性核对（summary vs 原始 CSV）

| 检查项 | 结果 | 说明 |
|---|---|---|
| summary_counts_runs | PASS | summary=4800 csv=4800 |
| summary_counts_true_evals | PASS | summary=460800 csv=460800 |
| null_best_feasible | PASS | csv=1252 summary=1252 |
| null_rate_consistency | PASS | 0.2608333333333333 |
| first_feasible_null_matches_summary | PASS | csv=1252 summary=1252 |
| first_feasible_coverage_positive | PASS | coverage=3548/4800 (73.92%) |
| physical_calls_zero | PASS | 0 |
| status_valid | PASS | VALID |
| figures_status | PASS | {"fig1_meta_training_loss": "DATA_READY", "fig2_k_shot_adaptation": "NOT_APPLICABLE_THIS_STAGE", "fig3_feasible_rate": "DATA_READY", "fig4_equal_budget_gap": "DATA_READY", "fig5_fairness_audit": "DATA_READY", "fig6_airframe_gate_progress": "NOT_RUN"} |
| four_figures_generated | PASS | 4 |
| layout_all_pass | PASS |  |
| first_feasible_endpoint_rows | PASS | rows=24 reported=24 |
| first_feasible_stats_present | PASS | reported=24 |
| no_significant_maml_advantage | PASS | [] |
| no_significant_maml_bfv_advantage | PASS | 0 |
| maml_fhr_not_significantly_worse_than_pretrain | PASS |  |
| de_significantly_worse_bfv_present | PASS | 2 |
| attempt1_attempt2_payload_identical_except_expected | PASS | [] |
| attempt1_attempt2_holm_family_18_to_24 | PASS | ({('meta_test', '64'): 18, ('meta_test', '128'): 18, ('meta_test_ood', '64'): 18, ('meta_test_ood', '128'): 18}, {('meta_test', '64'): 24, ('meta_test', '128'): 24, ('meta_test_ood', '64'): 24, ('meta_test_ood', '128'): 24}) |

## 9 图表清单

| figure key | 文件 | 字节 | sha256（前缀） | 布局自检 |
|---|---|---|---|---|
| fig1_meta_training_loss | fig1_meta_training_loss.png | 518092 | 3bc798bd63ddcc23… | PASS |
| fig3_feasible_rate | fig3_feasible_rate.png | 392371 | 3fe31a11006dccf8… | PASS |
| fig4_equal_budget_gap | fig4_equal_budget_gap.png | 742299 | 3ef23de1f40257e9… | PASS |
| fig5_fairness_audit | fig5_fairness_audit.png | 470224 | 24bc0754084a9c10… | PASS |

- 图1：元训练损失（MAML 代理 3 元种子均值±min–max、loss_support 虚线；预训练代理 3 个终点；validation_loss NOT_AVAILABLE）。
- 图3：等预算可行命中率中位数（4 个分面 = split×预算；x 轴第二行披露无可行解 runs 占比）。
- 图4：等预算最优可行值 / gap_to_reference 收敛曲线（4 个分面 = 预算×端点；无可行解点留空，不插值）。
- 图5：公平性审计（代理评分运行次数与中位耗时；初始设计重叠度与 IDENTIFIABLE / SAME_INIT_DIFFERENT_ENGINE 标签；公平性事实文本）。
- fig2（K-shot 适应）NOT_APPLICABLE_THIS_STAGE（M6）；fig6（气动门禁）NOT_RUN（Issue #4 D-12D-004）；均未画假图。

