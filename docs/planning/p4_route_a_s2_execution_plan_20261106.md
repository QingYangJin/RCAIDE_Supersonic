# P4 路线A S2 执行计划（FULL_MAML 二阶元梯度 vs FOMAML 等预算对照）

- 版本：v1.2（2026-11-06T13:05Z，Lead 起草；v1.1 响应 A5 S2-M0 3B/6M/6m；v1.2 响应 A5 S2-M0R 2B/1M：B04/B03R/M07）
- 上游：Issue #7 D-P4-003 §2 S2；S1_RUN=EXECUTED_AND_RESULT_REVIEWED（commentId 6684142041，不含 S2 授权）
- 分支/工作树：research/p4-route-a-s2 @ D:/RCAIDE-s2-dev；base 1a2b242（S1 closeout docs v1.8），首个 S2 提交 b0acdf2 为本文 v1.0；v1.1 提交见 git log
- 硬边界：physical_call_count=0（全合成解析评价器，无 VSPAERO/SU2/RCAIDE/CFD/WaveDrag）；不合并 main；不新建 PR；仅 Lead 写 GitHub；旧 M2/M5/M6/S0-2..S0-7 只读；S2 不使用 S1 holdout（meta_test/meta_test_ood/negative_control）
- 证据范围：S2 仅使用 S0-7 的 meta_train(60) 训练、meta_validation(20) 评估。meta_validation 在 S1 已用于调参/校准，因此 S2 结论定位为 DEVELOPMENT_VALIDATION_ONLY（开发/验证集证据），不得表述为未见任务上的确证性泛化。
- 本版关闭的 A5 findings：M0 的 B01/B02/B03、M01-M06、m01-m06（§13）；M0R 的 B04/B03R/M07（§13、§4.4、§6、§7、§11）。

## 1. 目标与可证伪问题

S2 在同一合成任务族、同一元训练预算（episodes/内步/外步/批量/初始化/种子）下比较：
1. 元梯度正确性（gate）：FULL_MAML 外梯度对真实元目标 J(theta) 的中心差分最大相对误差满足 §4.3 门禁（fail-closed）。
2. 等预算适应质量（主问题）：meta_validation 任务在 K=5 支持样本适应后的 query 原始空间 RMSE，FULL_MAML 是否低于 FOMAML。
3. 次级/描述：K=10 推断性次要端点；K=0（无适应基线）、K=1、标准化空间 RMSE、MAE、训练稳定性、墙钟/峰值内存仅描述，不做 benefit/harm 推断。

主终点 ID：post_adaptation_rmse_raw_k5（越低越好）。
次要推断端点：post_adaptation_rmse_raw_k10。
描述性：post_adaptation_rmse_raw_k0/k1、post_adaptation_rmse_std_k5/k10、post_adaptation_mae_raw_k5、train_wall_seconds_ratio、peak_memory_mb、meta_gradient_fd_max_rel_error（gate，不进推断）。
结论可为 null（NO_EVIDENCE / INCONCLUSIVE）；不得宣称真实航空收益。

## 2. 数据边界（fail-closed 机制，关闭 M02）

- 冻结包：research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z（只读；SHA256SUMS sha256 59aa81cd...f41f2；code_sha 7304d32e...201ed；git_sha 004156c...）。
- 专用加载器 load_s2_tasks(package_dir)：先校验 SHA256SUMS 9/9，再读 tasks.json；只返回 split in {meta_train, meta_validation} 的任务；若输入任务集含任何其它 split（meta_test/meta_test_ood/negative_control）立即抛 S2_DATA_BOUNDARY_ERROR。
- 负控测试：(a) 人为把 meta_test 任务注入加载结果 -> 必须被拒绝；(b) 直接把 holdout split 传给 episode 生成 -> 必须抛错；(c) 加载器返回的 task_id 集合 sha256 必须等于预注册期望值。
- run_config 记录：allowed_splits、split_counts、meta_train_task_ids_sha256、meta_validation_task_ids_sha256、holdout_task_ids_sha256（仅用于边界断言，不参与训练/评估）、holdout_rows_used=0、holdout_metrics_read=false。
- 所有 run/eval record 必须带 task_id 与 split；评估记录 split 必须为 meta_validation；训练记录 split 必须为 meta_train；否则 fail-closed。

## 3. episode 与确定性合同（关闭 B01 的 episode 部分、M04）

- 设计采样：task_family.sample_designs(task, count, kind, seed)（只读既有 API；count<=128/64；kind in {support, query}）。
- seed 派生：derive_seed(*parts)（既有实现无 scope 关键字；把 scope 作为第一个字符串参数）。
- 训练 episode bank（两臂共享、与 meta_seed 绑定、与 arm 无关）：
  - 对每个 meta_seed m、meta_train 任务 t、outer_step s in 0..199：
    support = sample_designs(t, 16, "support", derive_seed("S2-train-support", t.task_id, str(m), str(s)))
    query   = sample_designs(t, 32, "query",   derive_seed("S2-train-query",   t.task_id, str(m), str(s)))
  - 第 s 步 batch 任务选择：把 60 个 meta_train 任务按 derive_seed("S2-train-order", str(m), str(s)) 洗牌，取前 8 个；两臂使用同一顺序。
  - bank manifest：逐 episode 记录 task_id/split/outer_step/support_rows_sha256/query_rows_sha256；manifest canonical JSON 的 sha256 写入 run_config；两独立进程生成必须逐字节一致。
- 评估 episode（每 task/meta_seed/K/draw 独立）：
  - support = sample_designs(t, K, "support", derive_seed("S2-eval-support", t.task_id, str(m), str(K), str(draw)))（K=0 时 support 为空数组，不调用 sample_designs）；
  - query = sample_designs(t, 64, "query", derive_seed("S2-eval-query", t.task_id, str(m), str(K), str(draw)))；
  - K in {0,1,5,10}，draw in 0..9（K=0 也做 10 draws，保证行数一致；support 为空。若空 support 无法进 TaskEpisode，则 K=0 直接以最终参数在 query 上评估，不走适配 API）。
- 标准化：原始空间指标为推断依据；标准化空间仅描述：对 K>=2 用该次 support 的均值/标准差（ddof=1，std 下限 1e-8）；std<1e-8 时标准化指标记 null（不 fail 启动）；K=0/1 标准化指标恒 null。

## 4. 算法合同（maml.py 扩展）

### 4.1 FULL_MAML
- _inner_adapt_full_torch(tensors, support_x, support_y, config)：函数式内循环，不原地改 .data；每步 loss=MSE(forward(tensors), y)；grads=torch.autograd.grad(loss, tensors, create_graph=True)；tensors=[t - inner_lr*g for t,g in zip(tensors, grads)]。
- _full_maml_outer_gradient(parameters, episodes, config)：batch 内每任务从同一 theta 做完整内循环，J(theta)=mean_t L_query(theta_t'(theta))；torch.autograd.grad(J, base_tensors, create_graph=False) 返回二阶元梯度；返回 (J, grads)。
- meta_train_step(..., second_order: bool=False)：second_order=True 或 config.first_order=False 时走 FULL_MAML；否则维持 FOMAML。
- 既有 FOMAML 实现与 API 不变（回归测试全绿）。

### 4.2 K=0 等价性（仅梯度门禁，关闭 B01 语义混用）
- 在同一 theta、inner_steps=0 条件下，FULL 与 FOMAML 元梯度逐元素差 <=1e-12（测试断言）。
- 该等价性只用于元梯度门禁；训练后 K=0 评估是两个不同最终参数的“无适应基线”，不构成等价性对照，不参与 benefit/harm 推断。

### 4.3 FD 门禁（关闭 M01）
- mode="full"：解析梯度由 _full_maml_outer_gradient 计算；数值差分在原始 theta 上做：对坐标 j，eps_j = 1e-6 * max(1.0, |theta_j|)，theta±eps_j e_j 后重跑完整内循环并计算 J(theta±eps_j e_j)，numeric=(J_plus-J_minus)/(2*eps_j)。
- 坐标选择：按 |analytic| 从大到小选 32 个坐标（跨全部张量），不采用均匀抽样；若可抽查坐标少于 32 个则 fail-closed。
- 相对误差：|numeric-analytic| / max(|numeric|, |analytic|, 1e-12)；阈值 max_rel_error<=1e-6，否则 S2_META_GRAD_FD_FAIL。
- mode="fomaml" 维持既有口径（epsilon=1e-5、tolerance=1e-4、top-5 |grad|）；两种 mode 认证不同对象（适配点参数化 vs 真实元目标），须在报告披露。
- 零物理试点（正式 run 前，A1 执行）：(i) 微型网络 hidden=(8,8)、inner_steps=1、batch=1、32 坐标；(ii) 全尺寸 hidden=(16,16)、inner_steps=2、batch=2、8 坐标；报告误差分布/耗时/内存；试点产物 sha256 写入 run_config。
- 测试补充：多步内循环（inner_steps>=2）FD；小网络 HVP/解析对照测试（autograd 二阶梯度 vs 有限差分，容差 1e-6）；微型网络 K>1 数值稳定性。

### 4.4 等预算与公平性
- 两臂 MAMLConfig 逐字段相同（input_dim=12、output_dim=1、hidden_sizes=(16,16)、inner_lr=0.01、inner_steps=5、outer_lr=1e-3、tasks_per_batch=8），仅 first_order 不同（FOMAML=True，FULL=False）。hidden=(16,16) 与既有 offline_runner/m5_arms 的 HIDDEN_SIZES 一致，降低二阶图内存；不做超参搜索。
- outer_steps=200、meta_seed in {0,1,2}、episode bank 相同；自动比对 run_config 的 arms 配置，除 first_order 外任一差异 -> fail-closed。

## 5. 训练与评估合同

- 训练：每 meta_seed 从 init_parameters(seed=meta_seed) 出发；每步用 §3 的 bank 顺序；记录 outer_step/train_loss/grad_norm/inner_loss_first/inner_loss_last/wall_s/status/peak_memory_mb。
- 评估：20 个 meta_validation 任务 x 3 meta_seeds x K in {0,1,5,10} x 10 draws；K>=1 做 K 步内循环适应；K=0 不更新；query 上计算 RMSE/MAE（原始空间为主；标准化空间按 §3 规则或 null）。
- 输入特征：S2 元学习输入仅为 12 维设计向量，不使用 S1 的 context 特征；因此 S2 是独立算法对照，不是 S1 代理的复现/替换。
- 评估记录（每行）：run_id、arm、meta_seed、task_id、split=meta_validation、K、draw、query_rmse_raw、query_rmse_standardized、query_mae_raw、support_size、query_size、adaptation_inner_steps、wall_s、status。
- 训练记录（每行）：run_id、arm、meta_seed、outer_step、train_loss、grad_norm、inner_loss_first、inner_loss_last、wall_s、peak_memory_mb、status。
- 预期行数：训练 2 arms x 3 seeds x 200 steps = 1,200；评估 2 x 3 x 20 x 4 x 10 = 4,800；合计 6,000 行（K=0 也 10 draws）。
- 资源：记录每进程峰值内存（peak_memory_mb，psutil 或 resource 实测；不得写 null 冒充 0）；FULL 相对 FOMAML 的时间/内存硬上限：若 FULL 单 seed 训练墙钟 > 2 h 或峰值内存 > 8 GB，该 run 标记 RESOURCE_LIMIT，不重试，报告披露。

## 6. 端点、统计与决策（关闭 B02、M03）

- 单位：task（20 个 meta_validation 任务）。每 task/arm 聚合值 = 该 task 的 3 meta_seeds x 10 draws 共 30 个值的均值（先 draw 后 seed 聚合；不得跨任务混合）。
- 主比较 C1=FULL_MAML - FOMAML（负值=有益）。
- 主终点：post_adaptation_rmse_raw_k5（唯一主终点）。
- 次要推断端点：post_adaptation_rmse_raw_k10。
- 多重校正：唯一 Holm 族 family_id=s2-primary-secondary-2tests、family_key=s2_primary_secondary、family_size=2，成员=[{comparison:C1,endpoint:post_adaptation_rmse_raw_k5},{comparison:C1,endpoint:post_adaptation_rmse_raw_k10}]；禁止按 endpoint 拆成两个单成员族。K=0/K=1 及标准化空间/MAE/资源指标均不进入 Holm，不做 benefit/harm 推断。
- 检验：配对 Wilcoxon 符号秩（n=20，双侧）；bootstrap 10,000 次（seed 20261105）95% CI（配对差）；Holm 调整后 p。
- 决策：
  - SUPPORTED_BENEFIT：Holm p<0.05 且 95% CI 不跨 0 且方向 FULL<FOMAML 且相对改善 >=1%（相对 FOMAML 该端点的中位数）。
  - SUPPORTED_HARM：对称（FULL>FOMAML 且相对恶化 >=1%）。
  - INCONCLUSIVE：null 比例 >70%。
  - 其余：NO_EVIDENCE。
- 证据范围标注：所有 aggregate/summary/图/报告必须带 evidence_scope="DEVELOPMENT_VALIDATION_ONLY" 与 development_set="meta_validation"；结论措辞限于“在 meta_validation 上观察到/未观察到差异”，禁止“确证性泛化/真实任务/未见任务”类表述。
- 允许 null；不得宣称 S2“成功”；不得外推真实航空收益。

## 7. Prereg schema（关闭 B03）

- 文件：s2_preregistration.json（正式 run 前由 Lead 冻结，之后不得修改）。
- canonical JSON：json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False) + 末尾换行。
- prereg_id（去循环）：base = canonical JSON of prereg with BOTH prereg_id and prereg_digest omitted；prereg_id = "p4ra-s2-prereg-" + sha256(base)[:16]；随后写入 prereg_id。
- prereg_digest = sha256(canonical JSON of prereg with ONLY prereg_digest omitted，此时 prereg_id 已固定)；再写回 prereg_digest。verify 必须从文件独立复算两者并与字段逐字节比较（不相等 -> S2_PREREG_DIGEST_MISMATCH）。
- code_sha 算法（可机械复算）：文件清单按字典序 ["research/concorde_metaopt/meta_learning/maml.py","research/concorde_metaopt/meta_learning/s2_runner.py","research/concorde_metaopt/meta_learning/s2_prereg.py"]；对每个文件写 path.encode("utf-8") + b"\n" + sha256(raw bytes).hexdigest().encode("ascii") + b"\n"，拼接后整体 sha256 = code_sha。冻结时与当前工作树逐文件比对；run 启动前再比对一次（不一致 -> 拒绝启动）。
- analysis_plan_digest = sha256(canonical JSON of object {"endpoints":<endpoints 节>,"comparison":<comparison 节>,"statistical_plan":<statistical_plan 节>,"fd_gate":<fd_gate 节>})；字段本身不在被哈希对象内，无循环；verify 复算比较。
- arms 公平性：两臂 config 除 first_order 外必须逐字段相同（含 seed、backend、hidden_sizes）；build 写入前与 verify 读入后都断言，不一致 -> S2_ARM_CONFIG_MISMATCH。
- 必填字段（v1）与示例：

    {
      "schema_version": "p4ra-s2-prereg-v1",
      "prereg_id": "p4ra-s2-prereg-0123456789abcdef",
      "created_utc": "2026-11-06T12:30:00+00:00",
      "upstream": {"issue": "#7", "decision": "D-P4-003", "stage": "S2", "s1_receipt_comment_id": 6684142041},
      "frozen_package": {"run_id": "p4ra-s0-7-freeze-20261106T024200Z", "package_path": "research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z", "sha256sums_sha256": "59aa81cdc1f1abdc66966822eb24b567904ba4c62924ab041ae09bd9badf41f2", "code_sha": "7304d32e524b0e1e28b0e83e7a2ed7822ce88fc14963ca4d769098841e6201ed", "git_sha": "004156c232f31a450f7446c3b280772de47423df", "family_version": "p4ra-family-v4"},
      "data_boundary": {"allowed_splits": ["meta_train","meta_validation"], "forbidden_splits": ["meta_test","meta_test_ood","negative_control"], "split_counts": {"meta_train": 60, "meta_validation": 20, "meta_test": 20, "meta_test_ood": 10, "negative_control": 10}, "meta_train_task_ids_sha256": "<required>", "meta_validation_task_ids_sha256": "<required>", "holdout_task_ids_sha256": "<required>", "holdout_rows_used": 0},
      "episode_contract": {"train_support": 16, "train_query": 32, "eval_K": [0,1,5,10], "eval_draws": 10, "eval_query": 64, "seed_scopes": ["S2-train-support","S2-train-query","S2-train-order","S2-eval-support","S2-eval-query"], "standardization": "raw_primary; standardized descriptive for K>=2 with support std>=1e-8 else null", "train_episode_bank_sha256": "<required>"},
      "arms": [{"id": "FULL_MAML", "first_order": false, "config": {"input_dim": 12, "output_dim": 1, "hidden_sizes": [16,16], "inner_lr": 0.01, "inner_steps": 5, "outer_lr": 0.001, "tasks_per_batch": 8, "seed": 42, "backend": "torch"}}, {"id": "FOMAML", "first_order": true, "config": {"input_dim": 12, "output_dim": 1, "hidden_sizes": [16,16], "inner_lr": 0.01, "inner_steps": 5, "outer_lr": 0.001, "tasks_per_batch": 8, "seed": 42, "backend": "torch"}}],
      "training_budget": {"outer_steps": 200, "meta_seeds": [0,1,2], "train_records_expected": 1200},
      "evaluation_grid": {"meta_validation_tasks": 20, "K": [0,1,5,10], "draws": 10, "eval_records_expected": 4800},
      "endpoints": {"primary": {"id": "post_adaptation_rmse_raw_k5", "direction": "lower_is_better", "K": 5, "space": "raw"}, "secondary_inferential": [{"id": "post_adaptation_rmse_raw_k10", "direction": "lower_is_better", "K": 10, "space": "raw"}], "descriptive": ["post_adaptation_rmse_raw_k0","post_adaptation_rmse_raw_k1","post_adaptation_rmse_std_k5","post_adaptation_rmse_std_k10","post_adaptation_mae_raw_k5","train_wall_seconds_ratio","peak_memory_mb"]},
      "comparison": {"id": "C1", "arms": ["FULL_MAML","FOMAML"], "difference": "FULL_MAML - FOMAML", "unit": "task", "aggregation": "mean over 3 meta_seeds x 10 draws per task"},
      "statistical_plan": {"test": "wilcoxon_signed_rank_two_sided", "n_tasks": 20, "bootstrap": {"n_resamples": 10000, "seed": 20261105, "ci": 0.95}, "multiple_comparison": {"family_id": "s2-primary-secondary-2tests", "family_key": "s2_primary_secondary", "method": "holm", "family_size": 2, "members": [{"comparison": "C1", "endpoint": "post_adaptation_rmse_raw_k5"}, {"comparison": "C1", "endpoint": "post_adaptation_rmse_raw_k10"}]}, "decision_rules": {"benefit": "holm_p<0.05 and ci_excludes_zero and full<fomaml and relative_improvement>=0.01", "harm": "symmetric", "inconclusive": "null_rate>0.70", "else": "NO_EVIDENCE"}, "evidence_scope": "DEVELOPMENT_VALIDATION_ONLY"},
      "fd_gate": {"mode": "full", "max_relative_error": 1e-6, "coordinates": 32, "epsilon": "1e-6 * max(1, |theta_j|)", "denominator": "max(|numeric|, |analytic|, 1e-12)", "fail_closed": true, "pilot_artifacts": {"micro": {"path": "evidence/s2_fd_pilot_micro.json", "sha256": "<64hex computed at build>"}, "full_size": {"path": "evidence/s2_fd_pilot_full.json", "sha256": "<64hex computed at build>"}}},
      "determinism": {"reruns": 2, "requires_byte_identical": ["train_episode_bank_manifest","run_config","run_records_core"], "fail_closed": true},
      "failure_rules": ["nonfinite_loss_or_grad -> arm/seed FAILED, stop, no retry", "resource_limit -> RESOURCE_LIMIT, no retry", "any seed failed -> arm DEGRADED and primary INCONCLUSIVE"],
      "stopping_rules": ["stop_on_nonfinite", "stop_on_data_boundary_violation", "stop_on_fd_gate_failure", "stop_on_code_sha_mismatch", "hard_deadline_2h"],
      "code_sha": "<computed by §7 file-list algorithm over maml.py+s2_runner.py+s2_prereg.py>",
      "analysis_plan_digest": "<computed by §7 algorithm over endpoints+comparison+statistical_plan+fd_gate>",
      "physical_call_count": 0,
      "prereg_digest": "<self-excluded sha256>"
    }

- 冻结/核验流程：Lead 写 prereg -> A1 生成 s2_prereg.py 的 build/verify 实现 -> Lead 冻结并提交 -> A5 独立核验（digest、字段、S0-7 身份、端点、Holm 单族、预算、FD gate 路径/sha、arms 公平性、code_sha/analysis_plan_digest 复算）-> A5 verdict APPROVE_FOR_S2_RUN -> Lead 书面授权 -> A2 正式 run。
- 占位拒绝（fail-closed）：verify 遇到任何字符串匹配 ^<.*>$ 或等于 TBD/TODO/PENDING/PLACEHOLDER/REPLACE_ME 立即抛 S2_PREREG_PLACEHOLDER_REJECTED；pilot_artifacts 每项必须为 {path, sha256} 且文件存在、sha256 匹配；必填字段缺失/空串同样拒绝。
- 正式 run 启动前 fail-closed 校验：prereg digest 自洽；S0-7 SHA256SUMS 9/9；code_sha 与当前代码一致；FD gate PASS 且 sha 匹配；episode bank manifest sha 匹配；否则拒绝启动。

## 8. 指标范围说明（关闭 M05 的 scope 部分）

- 本阶段 S2 的代理模型只预测标量目标，不预测约束；S1 的可行率/首次可行/最优可行指标属于“约束优化器证据”，在 S2 中不适用。
- Lead 书面缩小 scope：S2 以 RMSE/MAE（适应质量）、FD 正确性、稳定性/资源为证据；feasible_hit_rate/first_feasible_eval/best_feasible_value 在 summary 记 NOT_APPLICABLE_S2_SURROGATE_SCOPE，并附理由。
- peak_memory_mb 与训练墙钟必须实测并记录（不得伪造）；HVP/微型网络/K>1 数值稳定性测试纳入验收（§4.3）。

## 9. 失败/停止规则（关闭 m04）

- 任一训练步出现非有限 loss/grad：该 (arm, meta_seed) 记 FAILED，停止该 seed；不重试；其余 seed 继续；若某 arm 任一 seed FAILED，该 arm 记 DEGRADED，主终点 INCONCLUSIVE。
- 数据边界违反、FD gate FAIL、code_sha 不匹配、prereg 校验失败：立即停止，不产生正式结果。
- 硬时限：正式 run 2 h；超时停止并报告部分产物状态（不伪造完整）。
- 评估记录 status in {OK, FAILED}；FAILED 原因写入 run_summary。

## 10. 文件与产物所有权（关闭 M06）

- A1：maml.py（FULL_MAML/FD）、s2_runner.py（新建）、s2_prereg.py（新建）、tests/test_maml_full.py、tests/test_s2_runner.py、训练/评估代码。
- A6：s2_analysis.py、s2_figures.py、tests/test_s2_analysis.py。
- A4：docs/reviews/p4_route_a_s2_requirement_matrix.md、Issue #7 S2 回执草稿（EXT）。
- A5：M0 设计审阅、代码审阅、prereg 冻结核验、结果复核（四次独立 verdict）。
- A2：正式 run 执行与产物（run_records.jsonl、run_config.json、run_summary.json、data_manifest.json、CSV、figures PNG、S2_formal_run_report.md，均在 EXT/p4-route-a/a2/s2_formal/）。
- A3：只读审计（提交隔离、旧件不变、证据哈希链、边界）；报告 EXT/p4-route-a/a3/S2_isolation.md。
- Lead：计划、prereg 冻结、commit、书面授权、Issue 回执、阶段裁定。

## 11. 阶段门与放行链（更新，含 prereg 核验门）

1. A5 M0/M0R 限定 diff 复审（本计划 v1.2 + prereg schema）-> APPROVE_FOR_S2_CODE。
2. A1 实现+测试；A6 分析+图；A4 文档（可并行，均以 M0 通过为前置）。
3. A5 代码审阅 -> APPROVE_FOR_S2_FORMAL。
4. Lead 按 §7 算法生成/冻结 S2 prereg（build 计算 prereg_id/code_sha/analysis_plan_digest/prereg_digest；verify 独立复算并拒绝占位）并提交 -> A5 独立核验冻结 prereg -> APPROVE_FOR_S2_RUN。
5. Lead 书面授权（绑定 commit/prereg digest/S0-7/数据边界/时限）-> A2 正式 run（零物理）。
6. A5 结果复核 -> A3 审计 -> Issue #7 S2 回执 -> S3。

## 12. 验收清单

- [ ] FD gate PASS（mode=full，32 坐标，max_rel_error<=1e-6，fail-closed）
- [ ] K=0 元梯度等价性 <=1e-12；既有 FOMAML 测试全绿；全量测试 >= 949 + 新增
- [ ] 两臂配置除 first_order 外逐字段相同（自动比对）
- [ ] 训练 episode bank 两独立进程逐字节一致；manifest sha 写入 run_config
- [ ] 数据边界负控 3 项通过；holdout_rows_used=0
- [ ] prereg_id/prereg_digest 去循环可复算；code_sha 文件清单算法可机械复算；analysis_plan_digest 由四节复算；占位拒绝负控通过
- [ ] 两臂 config 含 seed=42/backend=torch 且除 first_order 外逐字段相同（build 与 verify 双重断言）
- [ ] Holm 唯一族 family_size=2，分析脚本按 family 对象执行、不按 endpoint 拆分；2 检验 Holm 单测
- [ ] 正式 run 记录完整：训练 1,200 行 + 评估 4,800 行；physical_call_count=0
- [ ] 分析脚本强制 prereg digest/端点 ID/证据范围标签；统计规则与 §6 一致
- [ ] 报告事实/推断/局限分节；结论允许 null；不使用确证性泛化措辞
- [ ] A5 四次 verdict + A3 审计 + Issue #7 回执

## 13. A5 M0/M0R findings 处置（v1.2）

| ID | 处置 | 位置 |
|---|---|---|
| A5-S2M0-B01 | 关闭：K=0/K=1 改为描述性；主终点改用原始空间 RMSE；标准化仅 K>=2 描述；K=0 等价性仅梯度单测 | §1/§3/§4.2 |
| A5-S2M0-B02 | 关闭：唯一主终点 K=5；K=10 次要推断；Holm 族=2（K=5/K=10）；K=0/1 不推断 | §6 |
| A5-S2M0-B03 | 关闭：新增完整 prereg schema 与示例、canonical digest 规则、冻结/核验门 | §7、§11 |
| A5-S2M0-M01 | 关闭：eps 按参数尺度、top-32 |g| 坐标、分母 max(|num|,|ana|,1e-12)、试点 + 多步/HVP 测试 | §4.3 |
| A5-S2M0-M02 | 关闭：加载器 allowlist + 3 项负控 + run_config holdout 身份 | §2 |
| A5-S2M0-M03 | 关闭：显式 DEVELOPMENT_VALIDATION_ONLY 与措辞限制 | 头部/§6 |
| A5-S2M0-M04 | 关闭：seed 公式/固定 bank/batch 顺序/两臂共享/determinism | §3/§4.4 |
| A5-S2M0-M05 | 部分书面缩小 scope：feasible 指标 NOT_APPLICABLE 并记录 peak_memory/HVP/稳定性 | §8 |
| A5-S2M0-M06 | 关闭：新增 A2/A3 owner 与产物映射 | §10 |
| A5-S2M0-N01 | 关闭：统一评估行数 4,800（K=0 也 10 draws）、训练 1,200 | §5 |
| A5-S2M0-N02 | 关闭：seed/sample API 字面量改为可执行形式（derive_seed 首参 scope；kind 明确） | §3 |
| A5-S2M0-N03 | 关闭：base 更正为 1a2b242 | 头部 |
| A5-S2M0-N04 | 关闭：非有限/资源/失败规则 | §9 |
| A5-S2M0-N05 | 关闭：FD gate 结果 path/sha 写入 run_config 并在 run 前校验 | §4.3/§7 |
| A5-S2M0-N06 | 关闭：新增 A5 prereg 冻结核验门（第 4 步） | §11 |
| A5-S2M0R-B04 | 关闭：arms 两臂 hidden_sizes 统一 [16,16]（删除 FOMAML [64,64]）；增 seed=42/backend=torch；build/verify 断言除 first_order 外逐字段相同 | §4.4/§7/§12 |
| A5-S2M0R-B03R | 关闭：prereg_id 去循环（同时排除 prereg_id+prereg_digest）；code_sha 文件清单算法、analysis_plan_digest 四节算法写入 §7；arms 增 seed/backend；占位拒绝规则 | §7/§11/§12 |
| A5-S2M0R-M07 | 关闭：唯一 Holm 族 family_id/family_key/family_size/members 明确，禁止按 endpoint 拆分；分析脚本与 2 检验 Holm 单测 | §6/§7/§12 |