# 任务回执：D-NEXT-001 路线B 元采集策略（a3-route-b / task-3）

- 角色：A3（路线B 元采集策略）
- 工作树：D:/RCAIDE/dnext001/wt-a3
- 分支：research/dnext001-b-meta-acquisition
- 本地 commit：f0d4cfb8af84816053cb29c5b7c6f56094d1e839（基线 ea8ad97833eb5ceab291faae643c141a2b219749）
- 提交信息：[D-NEXT-001] feat(route-b): 元采集策略合成垂直切片 + NOT_READY 负结果
- **physical_call_count = 0**（全部 run 为 synthetic_analogue；未启动 VSPAERO / SU2 / RCAIDE Mission / WaveDrag）
- 结论：**设计完成 + 原型完成 + NOT_READY**（负结果如实交付，不宣称 MetaBO 类方法胜出）
- 未推送、未合并 main、未改写任何历史/冻结产物。

---

## 1. 交付物清单（新增文件，26 个）

### 1.1 方法与文档

| 文件 | 说明 |
|---|---|
| docs/planning/dnext001_route_b_acquisition_design.md | 中文方法设计（9.5 KB）：状态/动作/奖励/RTG/任务分布/训练目标；轨迹来源与成本；实现骨架；泄漏防护；评测协议与结果；NOT_READY 7 项；MetaBO/FSAF/RGPE/PFNs4BO/离线RL/EI/UCB/PI/约束EI 文献对照；复现命令；声明 |
| docs/receipts/dnext001/a3_route_b_task_receipt.md | 本回执 |

### 1.2 原型代码 research/concorde_metaopt/route_b/

| 文件 | 说明 |
|---|---|
| __init__.py | 导出契约符号；显式声明未复用路线A WarmStartSampler/MAML 采样器 |
| contracts.py | TaskContext（拒绝 physical_call_count != 0）、EvaluatedPoint（source 必须为 evaluated，否则 ProxyLabelError）、ObservationHistory（拒绝重复设计/乱序 index）、CandidatePool（无标签）、RewardSpec（可行改进 + 评价成本 + 首次可行奖励）、rewards_to_go |
| synthetic_tasks.py | 6D 解析二次型 + 窄带可行性约束（x1 in [0.38, 0.62]、x0 + x1 <= 1.15）；确定性任务生成；train/val/test 任务 id 前缀隔离；Latin hypercube 固定初始设计（种子绑定 task_id） |
| baselines.py | 自建 numpy GP（RBF 核 + Cholesky）+ 约束 EI / UCB / PI |
| policy.py | 22 维特征构造（仅已评价历史 + 候选坐标 + 任务上下文，上下文不含 task_id/split）；MetaAcquisitionPolicy（标准化 + tanh MLP，可学习 acquisition_score）；RandomScorePolicy（负控）；select_candidate 统一入口 |
| trajectory_dataset/__init__.py | 4 种行为（EI/UCB/PI/random）离线轨迹生成（仅 train 任务）；dataset.jsonl + manifest.json（SHA256）+ episodes.json；载入校验 |
| policy_train/__init__.py | direct-method 训练：仅 train 任务，任务级 fit/early-stop 切分，numpy MLP + Adam，早停保存 best params，落盘报告 |
| policy_eval/__init__.py | 固定初始点闭环评测（仅 val/test）；7 臂；任务级均值聚合；主比较 learned 减 EI；负控自检 |
| run_smoke.py | 端到端垂直切片入口（数据 -> 训练 -> val/test 评测 -> 中文图 -> run_summary） |

### 1.3 测试

| 文件 | 说明 |
|---|---|
| research/concorde_metaopt/tests/test_route_b_contracts_policy.py | 契约/特征/策略合法性/前缀无未来信息等 |
| research/concorde_metaopt/tests/test_route_b_training_eval.py | 任务隔离、manifest 篡改、评测拒绝 train、负控与 INCONCLUSIVE |

### 1.4 run 产物（runs/dnext001_route_b/run_001/，14 文件 / 约 430 KB）

trajectory_dataset/{dataset.jsonl, episodes.json, manifest.json}、policy_train/{policy.json, train_report.json, loss_history.json}、policy_eval_val/ 与 policy_eval_test/{eval_results.json, eval_results.csv, eval_summary.json}、figures/route_b_arms_test.png（中文标题）、run_summary.json。

- dataset.jsonl SHA256 = 09624c934a1c3fd800a8eb749e2190ebdd0fedd5c2b2ed618a8a2c1702d1045f（manifest 校验通过）
- policy_sha256 = 693fa845f0a6d9947664a30c2c8ca85246b07ff696fda9014685e50855f46637
- 全流程标记 physical_call_count = 0、source_kind = synthetic_analogue

另新增 .gitattributes（runs/** 与 route_b 代码 -text），保证证据文件字节不被 EOL 归一化、SHA256 可复算。

---

## 2. 实际运行的测试命令与结果

    cd D:/RCAIDE/dnext001/wt-a3
    & D:/RCAIDE/envs/RCAIDE/python.exe -m pytest research/concorde_metaopt/tests/test_route_b_contracts_policy.py research/concorde_metaopt/tests/test_route_b_training_eval.py -q
    # => 14 passed in 0.74s

    & D:/RCAIDE/envs/RCAIDE/python.exe -m research.concorde_metaopt.route_b.run_smoke --out runs/dnext001_route_b/run_001
    # => 数据集 48 episodes/384 记录；训练 best_epoch=8 best_val_loss=0.6491；7 臂 x val(3)/test(4) 评测完成

覆盖的 14 项断言（对应交付要求"单元与负控测试"）：

1. 代理假标签构造即抛 ProxyLabelError（history 不含假标签）
2. history 拒绝重复设计；拒绝 eval_index 乱序
3. TaskContext 拒绝 physical_call_count != 0
4. context_features 不含 task_id / split
5. 非 train 任务进入离线数据集抛 LeakageError
6. train/val/test 任务划分重叠抛 LeakageError
7. 特征维度 22 == feature_names 长度；评分有限；select 返回合法未评价候选
8. 决策记录可按 history 前缀精确重算（无未来信息泄漏）
9. manifest SHA256 篡改可检测
10. 训练/验证任务不重叠（fit 与 early-stop 任务 id 集合不相交）
11. 策略 to_params/from_params 往返一致
12. 评测拒绝 train 任务
13. 负控：未训练策略不优于随机；随机评分与随机同分布；主比较无法判定时 verdict = INCONCLUSIVE
14. run_summary/评测产物的 physical_call_count = 0

---

## 3. 评测结果（合成类比任务，统计单位 = 任务）

TEST（4 个 synth-test 任务，同一固定初始点、B = 12）：

| 臂 | first_feasible_eval | feasible_hit_rate | best_feasible_value | null_fraction | total_reward |
|---|---|---|---|---|---|
| learned | 2.00 | 0.104 | 0.440 | 0.896 | 0.179 ± 0.309 |
| EI（标准约束 BO） | 2.00 | 0.375 | 0.144 | 0.625 | 0.416 ± 0.426 |
| PI | 3.25 | 0.354 | 0.191 | 0.646 | 0.369 ± 0.352 |
| UCB | 3.50 | 0.208 | 0.299 | 0.792 | 0.266 ± 0.404 |
| random | 1.00 | 0.104 | 0.431 | 0.896 | 0.166 ± 0.317 |
| random_score（负控） | 1.00 | 0.104 | 0.431 | 0.896 | 0.166 ± 0.317 |
| untrained（负控） | 1.00 | 0.083 | 0.431 | 0.917 | 0.166 ± 0.317 |

主比较 learned 减 EI：total_reward -0.237、feasible_hit_rate -0.271、best_feasible_value +0.296（劣）、first_feasible_eval 0.000 -> verdict **INCONCLUSIVE**（test 任务仅 4 个，功效不足），描述性方向一致为"不如 EI/PI"。负控 **PASS**。

---

## 4. 未完成项与风险（NOT_READY 判定依据）

1. Concorde 12D 真实评价闭环未接通（VSPAERO LF-M2.02 = NOT_VALIDATED、BODY-CORR = BLOCKED）→ 本路线仅 6D 合成二次型，任务族过窄；
2. 离线轨迹仅 48 episodes / 384 条决策记录（6 个合成任务 x 4 行为 x 2 seed），不足以学习可泛化策略；
3. direct method 未做 IPS/反事实校正 → 训练目标有偏，learned 评分不保证最优；
4. test 任务仅 4 个 → 主比较只能 INCONCLUSIVE，不能宣称任何方向性统计结论；
5. 单一合成任务族，结论不可外推到真实气动任务；
6. 超参（hidden/lr/top_k/特征集）未系统搜索，比较不完全公平；
7. 未与路线A 做 2x2 因子消融（按计划须两路线各自审查通过后立项）。

风险：learned 在合成任务上"接近随机"的负结果若被误读为"路线B 无价值"，需注意其约束是数据与任务族规模，而非方法本身已被证伪。

---

## 5. 显式声明

- **physical_call_count = 0**：本轮未调用任何 VSPAERO / SU2 / RCAIDE Mission / WaveDrag 求解，未读取冻结 run 目录；只做 mock/合成/归档 replay 只读意义上的离线实验。
- **未复用路线A 采样器**：无 WarmStartSampler/MAML 采样器改名包装；仅共享仓库级工具（canonical_json、SHA256 约定、pytest 布局）。
- **不宣称 MetaBO 一定胜出**；NOT_READY 与 INCONCLUSIVE 为如实判定。
- 仅围绕 BO 后端，未扩展 DE/PSO 策略学习。
- 未 push、未合并 main、未改写历史或冻结产物；本回执与代码仅存在于本地分支 research/dnext001-b-meta-acquisition。

---

## 6. 复现

    cd D:/RCAIDE/dnext001/wt-a3
    & D:/RCAIDE/envs/RCAIDE/python.exe -m research.concorde_metaopt.route_b.run_smoke --out runs/dnext001_route_b/run_001
    & D:/RCAIDE/envs/RCAIDE/python.exe -m pytest research/concorde_metaopt/tests/test_route_b_contracts_policy.py research/concorde_metaopt/tests/test_route_b_training_eval.py -q
