# D-NEXT-001 Lead 启动与依赖计划（阶段回执 #1 依据）

- 日期：2026-11-10（Asia/Shanghai）
- 基线 commit：`ea8ad97833eb5ceab291faae643c141a2b219749`（父 `c7221fb` S3 封账 + 本计划文档单 commit）
- 依据：GitHub Issue #8「[D-NEXT-001][12D] 启动Concorde固定任务真实求解闭环＋路线A跨BO/DE/PSO热启动＋路线B元采集＋RTX5060 GPU并行」及 Owner 评论（五条子分支基线）
- 官方计划：`docs/planning/dnext001_real_concorde_route_a_b_gpu_plan_20261110.md`
- 本文件：Lead（唯一 GitHub 写入、集成与预算控制）的阶段启动计划与依赖/门禁约定。

## 1. 授权边界（本轮）

| 事项 | 状态 |
|---|---|
| 中文计划/代码/单测 | 已授权（本轮执行） |
| 独立 CUDA venv + 合成基准 | 已授权（本轮执行，不改原 `D:\RCAIDE\envs\RCAIDE` 的 torch 2.8.0+cpu） |
| 纯合成离线训练、公平实验、mock/replay 评价闭环 | 已授权（本轮执行） |
| S3 缺陷整改（新分支、新测试） | 已授权（本轮执行，不改 S3 历史 run/manifest/SHA） |
| 真实 VSPAERO Tier0 启动（建议 ≤6 次） | **未授权，待 Owner 单独批复**；本轮仅提交预算矩阵申请文档 |
| 固定任务真实小规模优化试点（建议 ≤12 次，Tier0 PASS 后） | **未授权**；本轮不申请执行，仅列入后续提案 |
| SU2 / RCAIDE Mission / WaveDrag / 整机油耗 / 气动 B 类回退 | **LOCKED** |
| 真实多任务 MAML 元训练、T1、main 合并、旧 PR 关闭 | **未授权** |

本轮全线 `physical_call_count = 0`；未获批复前任何真实求解器进程一律不得启动。

## 2. 不可改写的阶段事实

- S1：21,000 runs / 1,920,000 合成评价，主端点 `NO_SIGNIFICANT_IMPROVEMENT`。
- S2：6,000 条 Full MAML 相较 FOMAML K5/K10，适应后 RMSE 更差（约 −3.394% / −1.619% 相对改善，实为更差）。
- S3：3,780 runs / 362,880 合成评价；C1/C2 四检验 NULL / NO_EVIDENCE；阶段验收 `NOT_ISSUED`；S4 `NOT_APPROVED`；缺 A5 M2R 二次签核与独立 A3 结论。
- A5 已发现：F-01 模型清单路径缺陷、F-02 聚合校验口径、F-03 OOD 未接入正式分析、ANIL `wall_s=0` 不可审计、NC 仅 sidecar、4/10 图 NOT_RUN。
- VSPAERO 7.2.2：LF-M2.02 = `NOT_VALIDATED`、BODY-CORR = `BLOCKED`、HF-M2.02 = `PARTIAL`；`X_cg=16.821978259514246 m` 实为机翼 AC，几何全机 CG = `28.287395109126685 m`；136,000 kg 为单巡航进入质量，几何 MTOW = 184,880 kg。
- 代码已提交 ≠ 算法训练运行 ≠ 真实 VSPAERO 求解 ≠ 真实燃油优化有效。`fuel_burn_kg=null` 直到独立物理校核。

## 3. 角色、工作树与分支

| 角色 | 工作树 | 专题分支 | 任务卡 | 本轮工作包 |
|---|---|---|---|---|
| Lead | `D:\RCAIDE\dnext001\wt-lead` | `research/dnext001-integration` | — | 集成、依赖/预算、唯一 GitHub 写入、阶段回执 |
| A1 真实评价与航空约束 | `wt-a1` | `research/dnext001-f-real-evaluator` | task-1 | M0 审计 + TaskSpec 合同草案 + EvaluatorProtocol/记录/账本/mock/replay + 零求解 E2E + Tier0 预算矩阵申请 |
| A2 路线A热启动 | `wt-a2` | `research/dnext001-a-warmstart` | task-2 | WarmStartSampler + BO/DE/PSO 适配 + K×B×ρ 合成实验与中文图 |
| A3 路线B元采集 | `wt-a3` | `research/dnext001-b-meta-acquisition` | task-3 | 方法设计/文献对照 + MetaAcquisitionPolicy 原型 + 泄漏防护负控 |
| A4 GPU/性能/隔离 | `wt-a4` | `research/dnext001-gpu-benchmark` | task-4 | 独立 CUDA venv + FP32/FP64 基准 + CPU 并发 + 仓库隔离复核 |
| A5 独立审查 | `wt-a5` | `research/dnext001-a5-review` | task-5 | S3 缺陷专项审计清单 + M0 门禁评审表 + A/B/GPU 复核协议 |

规则：每线只写自己工作树；不 push、不合 main、不改写 S1/S2/S3 冻结产物；本地提交消息前缀 `[D-NEXT-001]`；统一 receipt：`docs/receipts/dnext001/<role>_task_receipt.md`（含 diff、独立测试输出、CSV/JSON/PNG、原始 SHA、`physical_call_count=0` 声明）。Lead 统一审查、集成、推送与发回执。

## 4. 依赖与门禁

```
M0（A1 合同草案 + A5 审计/门禁清单）─┐
F1 软件闭环（A1，零求解）────────────┼─→ Lead M0/F1 集成复核 ─→ 提交 Tier0 预算申请
A1 采样器（A2，纯合成）──────────────┤                        （≤6 次，未批不执行）
B1 原型（A3，纯合成，可 NOT_READY）──┤
G0/G1 GPU（A4，独立环境）────────────┘
A5 每阶段 PASS / CHANGES_REQUESTED 为合并必要条件（不得自审）
```

- M0 未通过：不得申请/执行真实 VSPAERO；不得宣称 `PHYSICS_VALIDATED`。
- A/B 2×2 因子消融：仅在 A、B 两条线各自审查通过后开展（本轮不做）。
- 统计以任务为单位；Wilcoxon / 配对 bootstrap / Holm；无数据标 `NOT_RUN`；中文图。

## 5. 证据与产物规范（每 run 必备）

`run_id / git_sha / code_sha / task_id / design_set / evaluator_id / fidelity / source_kind / physical_validation_status / solver_version / budget_B / K / initial_population_size / seed / physical_call_count`；
产物：`run_config.json / evaluations.jsonl / optimization_history.csv / metrics.csv / data_manifest.json / SHA256SUMS.txt / figures/*.png`。大文件按 bytes+sha256 指针列入清单。

## 6. 本轮（Wave-1）验收与停止条件

1. 五线各产出可复跑垂直切片 + 单测通过 + 中文 receipt；负结果/NOT_READY 同样算交付。
2. Lead 完成集成复核：独立重跑各线 pytest、核对 `physical_call_count=0`、核对无跨树写入与无 main 合并。
3. 产出阶段回执（中文）至 Issue #8：事实、文件、SHA、测试命令与结果、未完成项、预算申请状态。
4. 停止条件：真实求解未经批准被调用；冻结产物被改写；跨工作树写入；测试无法复现；任一门禁 fail-closed —— 立即停止该线并上报 Owner。
