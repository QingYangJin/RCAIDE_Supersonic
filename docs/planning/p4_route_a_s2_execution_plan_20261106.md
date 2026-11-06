# P4 路线A S2 执行计划（FULL_MAML 二阶元梯度 vs FOMAML 等预算对照）

- 版本：v1.0（2026-11-06T12:05Z，Lead 起草）
- 上游：Issue #7 D-P4-003 §2 S2；S1 formal 已执行完成并发布结果回执（commentId 6684142041）；S1_RUN=EXECUTED_AND_RESULT_REVIEWED（不含 S2 授权）
- 分支/工作树：research/p4-route-a-s2 @ D:/RCAIDE-s2-dev，起点 51c570c（S1 docs v1.7）
- 硬边界：physical_call_count=0（全合成解析评价器，无 VSPAERO/SU2/RCAIDE/CFD/WaveDrag）；不合并 main；不新建 PR；仅 Lead 写 GitHub；旧 M2/M5/M6/S0-2..S0-7 只读；S2 不使用 S1 holdout（meta_test/meta_test_ood/negative_control），只用 S0-7 的 meta_train(60)/meta_validation(20)。

## 1. 目标与可证伪问题

S2 目标：在同一合成任务族、同一元训练预算（episodes/内步/外步/批量/初始化/种子）下，比较 FULL_MAML（二阶，torch.autograd.grad(create_graph=True) 贯穿内循环）与 FOMAML（一阶）的：
1. 元梯度正确性（gate）：FULL_MAML 外梯度对真实元目标 J(theta) 的中心差分平均相对误差 <=1e-6（FOMAML 门禁维持既有口径）。
2. 等预算适应质量（主问题）：meta_validation 任务在 K=5 支持样本适应后的 query RMSE，FULL_MAML 是否优于 FOMAML。
3. 次级：K in {0,1,10} 的适应质量；K=0 两算法应同构（无内循环更新 -> 元梯度相同）；训练稳定性（NaN/发散）与墙钟成本比。

预注册主终点 ID：post_adaptation_rmse_k5（越低越好）。次级：post_adaptation_rmse_k0/k1/k10、meta_gradient_fd_max_rel_error（gate，不进推断）、train_wall_seconds_ratio（描述）。结论可为 null（NO_EVIDENCE）；不得宣称真实航空收益。

## 2. 数据与 episode 合同

- 冻结包：research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z（只读；SHA256SUMS sha256 59aa81cd...f41f2；code_sha 7304d32e...201ed）。
- 任务：仅 tasks.json 中 split in {meta_train, meta_validation} 的 60+20 个任务；design_dim=12；family=F-QE-feasible-v3；解析真值 task.truth(designs)["objective"]（不做可行性过滤、不丢弃不可行点）。
- episode 构造（确定性）：对任务 t，以 sample_designs(t,128,kind,seed) 生成 support pool、sample_designs(t,64,kind,seed) 生成 query；seed=derive_seed(scope="S2", task_id, split, k, draw, meta_seed)。训练 episode：support=16 行、query=32 行固定；评估：support=K 行（K in {0,1,5,10}），query=64 行，每个 (task, meta_seed, K) 做 10 次独立 draw。
- 特征=12 维 design；目标=objective 标量；标准化仅用每任务 support 统计（均值/标准差，标准差下限 1e-8），query 用同一统计；禁止使用 query 统计。
- 数据指纹：episodes manifest 记录每 task/seed/draw 的 support/query 行 sha256；两独立进程生成逐字节一致（determinism）。

## 3. 算法合同（maml.py 扩展）

- 既有 FOMAML 实现与 API 不变（回归测试必须全绿）。
- 新增 FULL_MAML：
  - _inner_adapt_full_torch(tensors, support_x, support_y, config)：函数式内循环（不原地改 .data）；每步 loss=MSE(forward(tensors),y)；grads=torch.autograd.grad(loss,tensors,create_graph=True)；tensors=[t-inner_lr*g for t,g in zip(tensors,grads)]。
  - _full_maml_outer_gradient(parameters, episodes, config)：对 batch 内每个任务从同一 theta 做完整内循环，计算 query loss，J(theta)=mean_t L_query(theta_t'(theta))；torch.autograd.grad(J, base_tensors) 返回二阶元梯度；返回 (J, grads)。
  - meta_train_step(..., second_order=False)：second_order=True 或 config.first_order=False 时走 FULL_MAML；否则维持 FOMAML。
  - finite_difference_gradient_check(..., mode="fomaml"|"full")：mode="full" 时数值差分在原始 theta 上加/减 eps（eps=1e-6 相对），每次都重跑完整内循环后计算 J(theta±eps)，中心差分与解析二阶元梯度比较（max_rel_error/mean_rel_error/per-tensor）；mode="fomaml" 维持现状。
  - FD gate 细则：抽样坐标数=32（跨张量均匀抽样，seed=20261106）；相对误差分母 max(|analytic|,|numeric|,1e-8)；阈值 max_rel_error <=1e-6，否则 fail-closed（S2_META_GRAD_FD_FAIL）。
- K=0 等价性：inner_steps=0 时 FULL 与 FOMAML 元梯度逐元素差 <=1e-12（测试断言）。
- 预算相等：两臂相同 MAMLConfig（input_dim=12, output_dim=1, hidden_sizes=(64,64), inner_lr=0.01, inner_steps=5, outer_lr=1e-3, tasks_per_batch=8, seed=meta_seed），相同 episodes、相同 outer_steps；除 first_order 外无差异。

## 4. 训练与评估合同

- 训练：outer_steps=200；每步 batch=8 个 meta_train 任务（轮转采样，seed 固定）；FULL 与 FOMAML 各 3 个 meta_seed {0,1,2}；每臂每 seed 保存最终参数（canonical JSON）与训练 loss 曲线。
- 评估：meta_validation 20 任务 x K in {0,1,5,10} x 10 draws；从最终参数出发做 K 步内循环适应（K=0 不更新），query 上计算 RMSE（标准化空间与原始空间都记录；主终点用标准化空间，std<1e-8 fail-closed）。
- run_records.jsonl（每行一个 arm/meta_seed/task/K/draw）：run_id、arm、meta_seed、task_id、split=meta_validation、K、draw、query_rmse_standardized、query_rmse_raw、support_size、query_size、adaptation_inner_steps、wall_s、status；训练记录（arm, meta_seed, outer_step, train_loss, grad_norm, wall_s, status）。
- 顶层 run_config：冻结包身份 5 键 + S2 prereg_digest + 代码 sha + grid 描述 + physical_call_count=0。

## 5. 统计与决策

- 单位：task（20 个 meta_validation 任务）；每 task 观测=3 meta_seeds x 10 draws 的均值（先 seed 后 draw 聚合；不得跨任务混合）。
- 主比较：C1=FULL_MAML vs FOMAML at K=5；配对 Wilcoxon 符号秩（n=20，双侧），bootstrap 10,000（seed 20261105）95% CI（配对差 FULL-FOMAML，越低越好：负=benefit）。
- 多重校正：Holm 族=(endpoint,K)，成员仅 C1；K in {0,1,5,10} 共 4 族（K=0 为等价性对照）。
- 决策：SUPPORTED_BENEFIT 需 Holm p<0.05、95% CI 不跨 0、方向为 FULL<FOMAML、且相对改善 >=1%（相对 FOMAML 均值）；SUPPORTED_HARM 对称；null 率 >70% -> INCONCLUSIVE；其余 NO_EVIDENCE。
- 预注册规则在正式 run 前冻结为 s2_preregistration.json（stopping_rules list[str]、endpoints、comparison、statistical plan digest、预算与确定性计划）；正式 run 后不得改。
- 结论层：L1 元梯度正确性（gate PASS/FAIL）、L2 等预算适应质量（primary 四端点判定）、L3 披露（成本、稳定性、局限）；允许 null，禁止「S2 成功」类措辞。

## 6. 文件所有权

- A1：maml.py（+FULL_MAML）、s2_runner.py（新建）、s2_prereg.py（新建）、tests/test_maml_full.py、tests/test_s2_runner.py。
- A6：s2_analysis.py、s2_figures.py、tests/test_s2_analysis.py（均新建）。
- A4：docs/reviews/p4_route_a_s2_requirement_matrix.md、回执草稿（EXT）。
- A5：S2 M0 设计审阅、代码审阅、结果复核（三次独立 verdict）。
- Lead：本计划、prereg 冻结与 commit、run 授权、Issue 回执、A3 审计派发。

## 7. 阶段门与放行链

1. A5 M0 设计审阅（本计划+数据/episode/prereg schema）-> APPROVE_FOR_S2_CODE。
2. A1 实现+测试（全量既有测试不得回归；新增 FD gate/等价性/预算/确定性测试）。
3. A5 代码审阅 -> APPROVE_FOR_S2_FORMAL。
4. Lead 生成并冻结 S2 prereg（prereg_digest）-> 书面授权 A2 正式 run（零物理、硬时限 2 h）。
5. 正式 run（两臂 x 3 seeds）-> 分析+图（>=5 张中文图）-> A5 结果复核 -> Issue #7 回执 -> S3。
6. 中途失败不重试、不伪造数据；任何越界（读 holdout、启 solver、改冻结包）立即停并报告。

## 8. 验收清单

- [ ] FULL_MAML FD 门禁 PASS（max_rel_error <=1e-6，抽样 32 坐标，mode=full）
- [ ] K=0 等价性 <=1e-12；FOMAML 既有测试全绿；全量测试 >= 现有基线（949+新增）
- [ ] 两臂配置除 first_order 外逐字段相同（自动比对 run_config）
- [ ] episodes determinism：两独立进程 manifest 逐字节一致
- [ ] 正式 run 记录完整：2 臂 x 3 seeds x 20 任务 x (1+10+10+10) 评估行 + 训练曲线
- [ ] physical_call_count=0；未读 meta_test/OOD/NC；未启 solver；未改冻结包
- [ ] 分析脚本强制 prereg digest/端点 ID/units；统计规则与 §5 一致
- [ ] 报告分列事实/推断/局限；结论允许 null
- [ ] A5 三次 verdict + A3 审计 + Issue #7 回执
