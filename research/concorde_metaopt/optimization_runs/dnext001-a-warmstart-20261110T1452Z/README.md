# D-NEXT-001 路线A：优化器无关热启动合成实验

- 阶段：D-NEXT-001-A（route A）
- 实验 ID：dnext001-a-warmstart-20261110T1452Z
- 基线 commit：ea8ad97833eb5ceab291faae643c141a2b219749；运行 HEAD：ea8ad97833eb5ceab291faae643c141a2b219749（dirty=True）
- **physical_call_count = 0**：全部真值来自合成解析函数，未启动 VSPAERO / SU2 / RCAIDE Mission / WaveDrag。
- evaluator：synthetic_analytic_truth；来源：SYNTHETIC_ANALOGUE
- runs：156；配对比较：54 行；代码 SHA 见 experiment_config.json。

## 矩阵
- smoke：B=[16, 32, 64, 128]，K=[0, 5]，rho=[0.0]，来源=['random', 'fomaml_kshot']
- extension：B=[64]，K=[1, 3]，rho=[0.0, 0.25, 0.5, 0.75]，来源=['fomaml_kshot']
- source_compare：B=[64]，K=[3]，rho=[0.0]，来源=['zero_shot_surrogate', 'pretrain_supervised']

## 参考解（scipy SLSQP 多起点，合成问题）
- 67137470f0c3：status=VALID，objective*=-0.2144
- 80c23acd1d01：status=VALID，objective*=-0.2204

## 关键负结果与风险（如实报告）
- 代理模型预测的可行性概率明显高于真实可行率：FOMAML/pretrain 提议点的真实可行数常为 0-1/8，而预测可行概率均值约 0.55-0.67。
- 单 seed、最小矩阵；first_feasible_eval 的下限受 K（支撑观测）与初始种群规模限制。
- 合成任务可行域阈值经调参（S-QC 可行率约 0.38，S-RB 约 0.15），调参过程记录在 receipt。

## 文件
- metrics.csv：每个 run 的主指标与早期 anytime 指标。
- paired_comparisons.csv：同任务、同预算、同 seed 的配对比较（treatment vs control）。
- cell_summary.csv：按矩阵 cell 聚合的均值。
- runs.jsonl：每个 run 的配置+指标（不含逐点 trace）。
- runs/<run_id>/evaluations.jsonl：逐次真实评价 trace。
- figures/*.png：中文图（matplotlib）。
- data_manifest.json / SHA256SUMS.txt：完整性校验。

## 度量口径
- first_feasible_eval：第几个真实评价首次得到可行解（1 起，含 K 个支撑观测与初始种群评价）。
- feasible_hit_rate：可行评价数 / 总预算 B。
- gap_to_reference：(best_feasible - objective*) / max(|objective*|, 1e-9)。
- anytime_best_feasible_*：预算截断到 8/16/32/64 时的最优可行目标值。
