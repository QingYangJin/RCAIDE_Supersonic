# P4 路线A S2 执行计划（FULL_MAML 二阶元梯度 vs FOMAML 等预算对照）

- 版本：v1.5（2026-11-06T13:52Z，Lead 起草；v1.1 响应 A5 S2-M0 3B/6M/6m；v1.2 响应 A5 S2-M0R 2B/1M；v1.3 响应 A5 S2-M0R2 并获 APPROVE_FOR_S2_CODE（对象 969c0e7，plan sha 35c486b9…）；v1.3a 仅 2 项文档 minor；v1.4 响应 A4 C-01..C-07 并新增 §8.1 图合同；A5 M0R4 对 v1.4 判 CHANGES_REQUESTED（0B/2M/3m，F-01..F-05）；v1.5 补 Issue #7 §4 七类映射与 fig8/fig9、fig3 CI 细则、prereg resource_limits、R-S2-01A/R-S2-01 版本更正、旧 v1.2 说明 superseded 标注。A5 批准对象仍为 v1.3/969c0e7；v1.5 须经 A5 M0R5 限定 diff 复审 APPROVE_FOR_S2_CODE_AMENDED 后方可作为代码与图合同基线）
- 上游：Issue #7 D-P4-003 §2 S2；S1_RUN=EXECUTED_AND_RESULT_REVIEWED（commentId 6684142041，不含 S2 授权）
- 分支/工作树：research/p4-route-a-s2 @ D:/RCAIDE-s2-dev；base 1a2b242（S1 closeout docs v1.8），首个 S2 提交 b0acdf2 为本文 v1.0；v1.1 提交见 git log
- 硬边界：physical_call_count=0（全合成解析评价器，无 VSPAERO/SU2/RCAIDE/CFD/WaveDrag）；不合并 main；不新建 PR；仅 Lead 写 GitHub；旧 M2/M5/M6/S0-2..S0-7 只读；S2 不使用 S1 holdout（meta_test/meta_test_ood/negative_control）
- 证据范围：S2 仅使用 S0-7 的 meta_train(60) 训练、meta_validation(20) 评估。meta_validation 在 S1 已用于调参/校准，因此 S2 结论定位为 DEVELOPMENT_VALIDATION_ONLY（开发/验证集证据），不得表述为未见任务上的确证性泛化。
- 本版关闭的 A5 findings：M0 的 B01/B02/B03、M01-M06、m01-m06（§13）；M0R 的 B04/B03R/M07；M0R2 的 M01/N01/N02（§13、§4.4、§7、§12）；M0R4 的 F-01..F-05（§8.1、§7、§14/§15、EXT R-S2-01A、旧 v1.2 说明）。
- 本版处置的 A4-S2C findings：C-01 资源口径、C-02 裁定优先级、C-03 图表合同、C-04 双层 family 版本、C-05 旧说明更正、C-06 版本标注、C-07 A5 审阅对象衔接（§14）；不改变对 A5 M0R3 结论的引用。

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
- 两臂 MAMLConfig 逐字段相同（input_dim=12、output_dim=1、hidden_sizes=(16,16)、inner_lr=0.01、inner_steps=5、outer_lr=1e-3、tasks_per_batch=8、seed=42、backend=torch），仅 first_order 不同（FOMAML=True，FULL=False）。hidden=(16,16) 与既有 offline_runner/m5_arms 的 HIDDEN_SIZES 一致，降低二阶图内存；不做超参搜索。
- outer_steps=200、meta_seed in {0,1,2}、episode bank 相同；build 写入前与 verify 读入后都断言两臂 config 除 first_order 外逐字段相同（含 seed/backend/hidden_sizes），任一差异 -> fail-closed S2_ARM_CONFIG_MISMATCH；run_config 的 arms 配置再比对一次。

## 5. 训练与评估合同

- 训练：每 meta_seed 从 init_parameters(seed=meta_seed) 出发；每步用 §3 的 bank 顺序；记录 outer_step/train_loss/grad_norm/inner_loss_first/inner_loss_last/wall_s/status/peak_memory_mb。
- 评估：20 个 meta_validation 任务 x 3 meta_seeds x K in {0,1,5,10} x 10 draws；K>=1 做 K 步内循环适应；K=0 不更新；query 上计算 RMSE/MAE（原始空间为主；标准化空间按 §3 规则或 null）。
- 输入特征：S2 元学习输入仅为 12 维设计向量，不使用 S1 的 context 特征；因此 S2 是独立算法对照，不是 S1 代理的复现/替换。
- 评估记录（每行）：run_id、arm、meta_seed、task_id、split=meta_validation、K、draw、query_rmse_raw、query_rmse_standardized、query_mae_raw、support_size、query_size、adaptation_inner_steps、wall_s、status。
- 训练记录（每行）：run_id、arm、meta_seed、outer_step、train_loss、grad_norm、inner_loss_first、inner_loss_last、wall_s、peak_memory_mb、status。
- 预期行数：训练 2 arms x 3 seeds x 200 steps = 1,200；评估 2 x 3 x 20 x 4 x 10 = 4,800；合计 6,000 行（K=0 也 10 draws）。
- 资源（C-01 统一口径）：记录每进程峰值内存（peak_memory_mb，psutil 或 resource 实测；不得写 null 冒充 0）；FULL 相对 FOMAML 的时间/内存上限：单 (arm, meta_seed) 训练墙钟 > 20 min 或峰值内存 > 8 GB -> 该 seed 记 RESOURCE_LIMIT，立即停止整个正式 run（不重试）并报告部分产物；正式 run 总硬截止仍为 2 h（§9），总超时同样停止并报部分产物。上述两规则不冲突：总截止是全局上界，单 seed 阈值是更早的分支停止条件；训练/评估代码须输出 1 outer-step 实测 timing，供运行前资源预估与报告披露。

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
- code_sha 算法（可机械复算）：文件清单按文件路径的 Python sorted() 字典序（即 maml.py、s2_prereg.py、s2_runner.py；完整相对路径 research/concorde_metaopt/meta_learning/{maml.py,s2_prereg.py,s2_runner.py}）；对每个文件写 path.encode("utf-8") + b"\n" + sha256(raw bytes).hexdigest().encode("ascii") + b"\n"，拼接后整体 sha256 = code_sha。冻结时与当前工作树逐文件比对；run 启动前再比对一次（不一致 -> 拒绝启动）。固定测试向量：tests/test_s2_prereg.py 内置 3 个内容固定的小型 fixture 文件及独立计算的期望 code_sha，断言算法实现得到同一值（不得仅用同一实现自证）。
- analysis_plan_digest = sha256(canonical JSON of object {"endpoints":<endpoints 节>,"comparison":<comparison 节>,"statistical_plan":<statistical_plan 节>,"fd_gate":<fd_gate 节>})；字段本身不在被哈希对象内，无循环；verify 复算比较。
- arms 公平性：两臂 config 除 first_order 外必须逐字段相同（含 seed、backend、hidden_sizes）；build 写入前与 verify 读入后都断言，不一致 -> S2_ARM_CONFIG_MISMATCH。
- 必填字段（v1）与示例：

    {
      "schema_version": "p4ra-s2-prereg-v1",
      "prereg_id": "p4ra-s2-prereg-0123456789abcdef",
      "created_utc": "2026-11-06T12:30:00+00:00",
      "upstream": {"issue": "#7", "decision": "D-P4-003", "stage": "S2", "s1_receipt_comment_id": 6684142041},
      "frozen_package": {"run_id": "p4ra-s0-7-freeze-20261106T024200Z", "package_path": "research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z", "sha256sums_sha256": "59aa81cdc1f1abdc66966822eb24b567904ba4c62924ab041ae09bd9badf41f2", "code_sha": "7304d32e524b0e1e28b0e83e7a2ed7822ce88fc14963ca4d769098841e6201ed", "git_sha": "004156c232f31a450f7446c3b280772de47423df", "package_family_version": "p4ra-family-v4", "task_family_version": "p4ra-family-v3"},
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
      "resource_limits": {"per_seed_train_wall_s": 1200, "peak_memory_mb": 8192, "total_wall_s": 7200},
      "failure_rules": ["nonfinite_loss_or_grad -> arm/seed FAILED, stop, no retry", "resource_limit(per_seed_train_wall_s>1200 or peak_memory_mb>8192) -> RESOURCE_LIMIT, stop entire run, no retry", "any seed failed -> arm DEGRADED and primary INCONCLUSIVE"],
      "stopping_rules": ["stop_on_nonfinite", "stop_on_data_boundary_violation", "stop_on_fd_gate_failure", "stop_on_code_sha_mismatch", "total_wall_s>7200 -> stop, report partial products"],
      "code_sha": "<computed by §7 sorted file-list algorithm over maml.py+s2_prereg.py+s2_runner.py>",
      "analysis_plan_digest": "<computed by §7 algorithm over endpoints+comparison+statistical_plan+fd_gate>",
      "physical_call_count": 0,
      "prereg_digest": "<self-excluded sha256>"
    }

- 冻结/核验流程：Lead 写 prereg -> A1 生成 s2_prereg.py 的 build/verify 实现 -> Lead 冻结并提交 -> A5 独立核验（digest、字段、S0-7 身份、端点、Holm 单族、预算、FD gate 路径/sha、arms 公平性、code_sha/analysis_plan_digest 复算）-> A5 verdict APPROVE_FOR_S2_RUN -> Lead 书面授权 -> A2 正式 run。
- 占位拒绝（fail-closed）：verify 遇到任何字符串匹配 ^<.*>$ 或等于 TBD/TODO/PENDING/PLACEHOLDER/REPLACE_ME 立即抛 S2_PREREG_PLACEHOLDER_REJECTED；pilot_artifacts 每项必须为 {path, sha256}，path 相对仓库根目录解析（resolve 后必须位于仓库根内），文件存在且 sha256(raw bytes) 匹配；错误路径/错误 sha/绝对路径三类负控测试。必填字段缺失/空串同样拒绝。
- 正式 run 启动前 fail-closed 校验：prereg digest 自洽；S0-7 SHA256SUMS 9/9；code_sha 与当前代码一致；FD gate PASS 且 sha 匹配；episode bank manifest sha 匹配；否则拒绝启动。
- resource_limits 固定值核验（A5-M0R4-F-03）：verify 必须要求 resource_limits 恰为 {per_seed_train_wall_s: 1200, peak_memory_mb: 8192, total_wall_s: 7200}（键集合与数值均一致），否则报 S2_PREREG_RESOURCE_LIMITS_INVALID；该字段纳入 prereg_digest。

## 8. 指标范围说明（关闭 M05 的 scope 部分）

- 本阶段 S2 的代理模型只预测标量目标，不预测约束；S1 的可行率/首次可行/最优可行指标属于“约束优化器证据”，在 S2 中不适用。
- Lead 书面缩小 scope：S2 以 RMSE/MAE（适应质量）、FD 正确性、稳定性/资源为证据；feasible_hit_rate/first_feasible_eval/best_feasible_value 在 summary 记 NOT_APPLICABLE_S2_SURROGATE_SCOPE，并附理由。
- peak_memory_mb 与训练墙钟必须实测并记录（不得伪造）；HVP/微型网络/K>1 数值稳定性测试纳入验收（§4.3）。

## 8.1 S2 图表合同（关闭 C-03 / A5-M0R4-F-01；含 Issue #7 §4 七类映射）

Issue #7 §4 要求 7 类中文图。S2 的研究对象是代理模型适应误差，不是约束优化或真实气动，因此本节先定义 S2 诊断图键（9 个规范键），再给出与 Issue 七类的逐类映射；不适用于 S2 的类别必须显式标注 NOT_APPLICABLE 及理由，不得用伪造数据补图。所有图必须由正式 run 产物生成，不得手工填数、不得平滑/插值伪造，也不得用分析代码内置常量冒充数据。

| 图键 | 内容 | 数据源 | 中文标题/轴 | 缺失处置 |
|---|---|---|---|---|
| fig1_training_loss_curves | 两臂 train_loss 随 outer_step 的 3 seed 曲线（均值+范围） | run_records 训练行 | 训练损失曲线 / outer step, train loss | 无训练行 -> NOT_RUN |
| fig2_post_adaptation_rmse_k5_k10 | task 级配对 raw RMSE，K=5（主）与 K=10（次要） | s2_per_task_aggregates.csv（endpoint=post_adaptation_rmse_raw_k5 / _k10） | 适应后 RMSE（K=5/10）/ arm, RMSE | 缺端点 -> NOT_RUN |
| fig3_rmse_vs_K | K in {0,1,5,10} 的 task 级 raw RMSE 均值±95% CI | s2_per_task_aggregates.csv + 本节 8.1.2 的 bootstrap | RMSE 随 K 变化 / K, RMSE | 缺 K 网格 -> 对应点 NOT_RUN |
| fig4_meta_gradient_fd | 两臂 FD max relative error 与 1e-6 阈值线 | FD pilot JSON + run_config | 元梯度有限差分校验 / 坐标, 相对误差 | pilot 缺失/fail -> NOT_RUN 并写明 S2_META_GRAD_FD_FAIL |
| fig5_effect_size_ci | C1=FULL-FOMAML 的 task 级均值与 bootstrap 95% CI（K=5 主、K=10 次要），含 0 线 | aggregate 的 C1 per-task 差值 + §6 bootstrap | 效应量及 95% CI / 端点, 差值 | 缺 bootstrap 结果 -> NOT_RUN |
| fig6_descriptive_k0_k1_standardized | K=0/K=1 描述性 raw RMSE、标准化空间 K=5 RMSE、raw MAE K=5 | s2_per_task_aggregates.csv（descriptive endpoints，见 8.1.2） | 描述性指标 / 指标, 值 | 缺标准化条件 -> 对应子图 NOT_RUN |
| fig7_determinism_and_negative_controls | 确定性重跑逐字节一致性与 3 项数据边界负控状态 | run_config / analysis summary | 确定性与负控 / 项目, 通过状态 | 缺重跑或负控记录 -> NOT_RUN |
| fig8_performance_cost | 两臂逐 meta_seed 训练墙钟、FULL/FOMAML 训练墙钟比、两臂峰值内存 | aggregate.json 的 resources.per_arm（train_wall_seconds_per_meta_seed / train_wall_seconds_mean / peak_memory_mb_max）与 resources.train_wall_seconds_ratio | 性能-成本（FULL_MAML vs FOMAML）/ meta seed、训练墙钟 s；arm、峰值内存 MB | 缺资源记录 -> NOT_RUN（不得用估计值代替） |
| fig9_task_family_diagnostics | K=5 的 task 级 raw RMSE（两臂排序）与按冻结包 family 分组均值/范围 | s2_per_task_aggregates.csv（endpoint=post_adaptation_rmse_raw_k5, arm, K=5）+ prereg.frozen_package.package_path/tasks.json 的 task_id->family | 任务族诊断（K=5）/ task（family）、RMSE | 缺 task 行 -> NOT_RUN；family 合并不可能 -> 仅 panel a，panel b 标 NOT_RUN 并写原因 |

### 8.1.1 Issue #7 §4 七类 -> S2 输出映射（A5-M0R4-F-01）

| Issue #7 §4 类别 | S2 输出 | 判定/理由 |
|---|---|---|
| ① 训练与全元目标 FD | fig1、fig4 | APPLICABLE：训练损失曲线与 FD max relative error |
| ② K-shot 误差 | fig2、fig3、fig6 | APPLICABLE：K=5/10 主次端点、RMSE vs K、K=0/1 描述性 |
| ③ Kshot/ZeroShot/Pretrain/Random 可行率 | NOT_APPLICABLE_S2_SURROGATE_SCOPE | S2 代理仅拟合标量目标，无约束函数/可行域定义；可行率不得伪造 |
| ④ 同预算最优/首次可行 | NOT_APPLICABLE_S2_NO_OPTIMIZATION_ARM | S2 无 BO/DE 优化臂与预算分配，只有等预算训练+后适应误差 |
| ⑤ FOMAML/FullMAML 性能-成本 | fig8_performance_cost | APPLICABLE：实测训练墙钟、墙钟比、峰值内存（仅描述，不参与判定） |
| ⑥ 任务族/约束/OOD 诊断 | fig9_task_family_diagnostics（任务族）+ NOT_APPLICABLE 说明 | 任务族可出图；约束诊断 NOT_APPLICABLE_S2_SURROGATE_SCOPE；OOD NOT_APPLICABLE_S2_NO_OOD_SPLIT（S2 仅 meta_validation，且为 DEVELOPMENT_VALIDATION_ONLY） |
| ⑦ 只读 VSPAERO 门禁 | NOT_APPLICABLE_S2_ZERO_PHYSICS_NO_VSPAERO | S2 physical_call_count=0，不调用 VSPAERO；Issue #4 D-12D-006 门禁属另一合同 |

结论：Issue 七类均被覆盖（4 类有图或 OOD 说明，3 类显式 NOT_APPLICABLE）；S2 另有 fig5（效应量 CI）与 fig7（确定性与负控）为自有诊断图，不替代七类映射，也不得声称“7 类图=7 张图”。

### 8.1.2 可验收细节（关闭 A5-M0R4-F-05）

- fig3：重采样单元 = task（20 个 meta_validation task）；每个 arm/K 先用该 task 的 meta_seed×draw 聚合值作为 task 级值，再对 20 个 task 级值做 percentile bootstrap，10,000 次重采样，seed=20261105，取 2.5/97.5 分位；不得跨 task 平滑；n<20 时图注披露实际 n。
- fig2：数据取 s2_per_task_aggregates.csv 的 endpoint=post_adaptation_rmse_raw_k5（主）与 post_adaptation_rmse_raw_k10（次），按 task 配对画两臂分布/配对点；不得用全局均值替代 task 级值。
- fig6：数据取 s2_per_task_aggregates.csv 的 post_adaptation_rmse_raw_k0、post_adaptation_rmse_raw_k1、post_adaptation_rmse_std_k5（标准化 K>=2 的代表）、post_adaptation_mae_raw_k5；按 arm 分组，仅描述。
- fig5：沿用 §6 的 task 级配对差 bootstrap（10,000 次，seed=20261105），不得另换 CI 方法。
- fig8：仅用 aggregate.json resources 实测字段；无记录 -> NOT_RUN，不得用训练日志估算替代。
- fig9：panel a 按 task 级 K=5 RMSE 排序（两臂同序）；panel b 用 frozen package tasks.json 的 family 分组，family 成员 <2 时该族仅画点并注明；OOD/约束在图注标注 NOT_APPLICABLE 及理由。
- 公共规则：每图必须标注 evidence_scope=DEVELOPMENT_VALIDATION_ONLY 与数据来源文件；中文标题、轴标签、图例、注释；输出 PNG（>=150 dpi）与支撑 CSV；图中不得出现未由数据计算的数值；任何 NOT_RUN 必须在图注和分析报告中写明原因，不得静默省略。
- 图键为唯一规范键：A6 的 s2_figures.py 必须输出 fig1..fig9 共 9 个键；额外图必须标注 diagnostic_ 前缀且不得替代规范键。
- A4 矩阵与 A6 实现均以本节为图合同；若 Issue #7 要求与本合同冲突，以 Issue 原文为准并由 Lead 更新本节。

## 9. 失败/停止规则（关闭 m04）

- 任一训练步出现非有限 loss/grad：该 (arm, meta_seed) 记 FAILED，停止该 seed；不重试；其余 seed 继续；若某 arm 任一 seed FAILED，该 arm 记 DEGRADED，主终点 INCONCLUSIVE。
- 数据边界违反、FD gate FAIL、code_sha 不匹配、prereg 校验失败：立即停止，不产生正式结果。
- 硬时限：正式 run 总硬截止 2 h（自 run 启动起算）；单 (arm, meta_seed) 训练 > 20 min 或峰值内存 > 8 GB 立即停止并记 RESOURCE_LIMIT；两类停止均报告部分产物状态（不伪造完整、不重试）。
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

1. A5 M0/M0R/M0R2/M0R3 限定 diff 复审（计划 v1.3 + prereg schema）-> APPROVE_FOR_S2_CODE（已于 969c0e7 取得）；v1.4 的 C-01..C-07 修订经 A5 M0R4 限定 diff 复审判 CHANGES_REQUESTED（0B/2M/3m，F-01..F-05，对象 0c85aee）；v1.5 修复后须经 A5 M0R5 限定 diff 复审（20 min 内）-> APPROVE_FOR_S2_CODE_AMENDED，方作为代码与图合同基线。M0R5 通过前，代码与图合同基线仍为 v1.3/969c0e7。
2. A1 实现+测试；A6 分析+图；A4 文档（可并行，均以 M0R3 通过为前置；A6 图代码以 §8.1 为合同）。
3. A5 代码审阅 -> APPROVE_FOR_S2_FORMAL；首步须确认 969c0e7..v1.5 的计划文件 diff 不含代码改动（C-07），并核对 v1.4/v1.5 未回退 v1.2/v1.3 修复；v1.5 仅改计划文件与 EXT 裁定/说明文件。
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
- [ ] code_sha 文件清单为 sorted() 字典序（maml.py/s2_prereg.py/s2_runner.py），固定测试向量通过
- [ ] pilot_artifacts.path 相对仓库根解析，错误路径/sha/绝对路径负控通过
- [ ] 正式 run 记录完整：训练 1,200 行 + 评估 4,800 行；physical_call_count=0
- [ ] §8.1 图合同 fig1..fig9 共 9 键全部产出或按原因标 NOT_RUN；Issue #7 §4 七类映射齐全（③/④/⑦ 显式 NOT_APPLICABLE）；每图有 CSV 支撑且标注 DEVELOPMENT_VALIDATION_ONLY
- [ ] 资源口径一致：单 seed >20 min 或 >8 GB 记 RESOURCE_LIMIT 即停；总硬截止 2 h；1 outer-step timing 已记录
- [ ] prereg.resource_limits 恰为 1200/8192/7200 且 verify 机械校验；fig8/fig9 数据源字段存在（resources.per_arm / s2_per_task_aggregates.csv + tasks.json family）
- [ ] 分析脚本强制 prereg digest/端点 ID/证据范围标签；统计规则与 §6 一致
- [ ] 报告事实/推断/局限分节；结论允许 null；不使用确证性泛化措辞
- [ ] A5 四次 verdict + A3 审计 + Issue #7 回执

## 13. A5 M0/M0R/M0R2/M0R3/M0R4 findings 处置（v1.5）

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
| A5-S2M0R2-M01 | 关闭：code_sha 文件清单改为 sorted() 字典序（maml.py/s2_prereg.py/s2_runner.py）；增固定测试向量要求 | §7/§12 |
| A5-S2M0R2-N01 | 关闭：§4.4 补 seed=42/backend=torch 与 build/verify 双重断言、S2_ARM_CONFIG_MISMATCH、run_config 三重复核 | §4.4 |
| A5-S2M0R2-N02 | 关闭：pilot_artifacts.path 明确相对仓库根解析并须位于仓库根内；增错误路径/错误 sha/绝对路径三类负控 | §7/§12 |
| A5-S2M0R3-M01 | 关闭（v1.3a）：§7 code_sha 示例顺序改为 sorted() 字典序并加固定测试向量要求 | §7/§12 |
| A5-S2M0R3-N01 | 关闭（v1.3a）：§11/§13 版本标注更新 | §11/§13 |
| A5-M0R4-F-01 | 关闭（v1.5）：§8.1 增 Issue #7 §4 七类映射表；新增 fig8_performance_cost、fig9_task_family_diagnostics；③/④/⑦ 显式 NOT_APPLICABLE 及理由 | §8.1/§12 |
| A5-M0R4-F-02 | 关闭（v1.5）：R-S2-01A 与 R-S2-01 更正为“v1.3a 未单独获批；M0R4 前批准对象为 v1.3/969c0e7；v1.5 经 M0R5 通过后才成基线” | EXT R-S2-01A/R-S2-01、头部/§11 |
| A5-M0R4-F-03 | 关闭（v1.5）：§7 prereg 增 resource_limits（1200/8192/7200）与对应 failure/stopping rule、verify 固定值校验 | §7/§12 |
| A5-M0R4-F-04 | 关闭（v1.5）：旧 v1.2 变更说明顶部标注 SUPERSEDED 并以计划 §7 sorted() 顺序为准 | EXT 说明 |
| A5-M0R4-F-05 | 关闭（v1.5）：§8.1 明确 fig3 的 task 级 bootstrap 单元/10,000 次/seed=20261105，fig2/fig3/fig6 的 aggregate 字段 | §8.1.2 |
| A5-M0R4 结论 | CHANGES_REQUESTED（0B/2M/3m；对象 0c85aee）；v1.5 修复后由 M0R5 限定 diff 复审 | 头部/§11 |
| A5-S2M0R3 结论 | APPROVE_FOR_S2_CODE（0B/0M/2m；对象 969c0e7）。v1.4 由 M0R4 复审判 CHANGES_REQUESTED（0B/2M/3m）；v1.5 由 M0R5 复审 | 头部/§11 |

## 14. A4-S2C findings 处置（v1.4，v1.5 保持关闭）

| ID | 级别 | 处置 | 位置 |
|---|---|---|---|
| A4-S2C-01 | major | 关闭（v1.5 补字段）：单 seed 资源阈值 20 min/8 GB；总截止 2 h 为全局上界；prereg 增 resource_limits 固定字段供机器核验 | §5/§7/§9/§12 |
| A4-S2C-02 | major | 关闭：发布 R-S2-01A 版本优先规则（最新 A5 APPROVE 计划优先，R-S2-01 仅为设计理由），并更新 R-S2-01 文末优先级 | §14/EXT R-S2-01A |
| A4-S2C-03 | gap | 关闭（v1.5 对齐）：§8.1 定义 9 个 S2 诊断图键并给出 Issue #7 §4 七类逐类映射（fig8/fig9 补⑤⑥；③/④/⑦ NOT_APPLICABLE 及理由） | §8.1/§12 |
| A4-S2C-04 | minor | 关闭：prereg frozen_package 拆 package_family_version=p4ra-family-v4 与 task_family_version=p4ra-family-v3 | §7 |
| A4-S2C-05 | minor | 关闭（v1.5 实际标注）：EXT 旧 v1.2 变更说明顶部已加 SUPERSEDED，code_sha 顺序以计划 §7 sorted() 为准（不改历史正文） | EXT 说明/本表 |
| A4-S2C-06 | minor | 关闭（v1.5 再更新）：§11 增 M0R3/M0R4/M0R5，§13 增 M0R3/M0R4 行，版本标注更新到 v1.5 | §11/§13 |
| A4-S2C-07 | minor | 关闭（v1.5 改口径）：A5 代码审阅首步确认 969c0e7..v1.5 仅计划文件 diff 且 v1.4/v1.5 未回退修复 | §11 第 3 步 |

## 15. A5 M0R4 findings 处置（v1.5）

| ID | 级别 | 处置 | 位置 |
|---|---|---|---|
| A5-M0R4-F-01 | major | 关闭：§8.1 增 Issue #7 §4 七类图逐类映射；新增 fig8_performance_cost（⑤）与 fig9_task_family_diagnostics（⑥）；③/④/⑦ 标 NOT_APPLICABLE 并给理由；明确 9 个 S2 诊断键不等于 Issue 七类 | §8.1/§8.1.1/§8.1.2 |
| A5-M0R4-F-02 | major | 关闭：R-S2-01A 第 2 条与 R-S2-01 文末更正为“v1.3a 未单独获批；M0R4 前批准对象为 v1.3/969c0e7；v1.5 经 M0R5 通过后才为基线” | EXT R-S2-01A/R-S2-01 |
| A5-M0R4-F-03 | minor | 关闭：prereg 增 resource_limits 固定字段及 failure/stopping rule；verify 机械校验，失败码 S2_PREREG_RESOURCE_LIMITS_INVALID | §7/§12 |
| A5-M0R4-F-04 | minor | 关闭：EXT/S2_plan_v1_2_change_note.md 顶部加 SUPERSEDED 标注 | EXT 说明 |
| A5-M0R4-F-05 | minor | 关闭：fig3 的 CI 方法/重采样单元/seed 与 fig2/fig3/fig6 的 aggregate 字段写入 §8.1.2 | §8.1.2 |

本版仅修改计划文件与 EXT 裁定/说明文件，不改代码、不生成 prereg、不启动 run、physical_call_count=0。
