# DRECOVER001-V1L-20261125-01 — RCAIDE 超音速 VLM (20×10) 上的 BO 优化与五臂重训

状态：**COMPLETED（本地；未 push 到远端）**
上游 Issue：[QingYangJin/RCAIDE_Supersonic#15](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/15)
证据范围：`RCAIDE_VLM_INTERNAL_ONLY`（声明型计算标签，非 VSPAERO 原始字节，非风洞，非飞行试验）
物理求解器启动：**0 次 VSPAERO**（本包全部结果来自 RCAIDE 自带超音速 VLM）

## 1. 这个包是什么

自用户 m00542 起，低保真气动评估全部切换到 **RCAIDE 自带超音速 VLM**，格架统一 **(20,10)**（20 展向 × 10 弦向涡格）。
本包是该切换之后的两条主线的完整证据：

1. **优化线（V1L-BO）**：在 12 维设计空间的 2 维活动子空间上跑 24 次 LHS + 96 次 GP-EI，共 **120 次真实 VLM 评估**，全部成功。
2. **训练线（V1L-A0）**：用 VLM 重算的 **44 条标签**（8 个任务 × 7 个设计中的 44 个 support/query 槽位）重跑五臂消融（RANDOM_INIT / POOLED_PRETRAIN_12D / COND_SUPERVISED_16D / FOMAML_12D / COND_FOMAML_16D × K=0/1/3）。

## 2. 目录

```
scripts/   v1l_bo.py         BO 主脚本（24 LHS + 96 GP-EI，seed 20261125）
           v1l_data.py       VLM 标签生成 + 数据集装配（8 任务，冻结 support/query）
           v1l_train.py      五臂训练/评估（由 a0_train.py 改写，走 vlm_labels 门禁）
           landscape.py      20×10 vs 30×15 景观/排序一致性探针
           v1l_paired_stats.py, v1l_stats2.py, make_csv.py   统计与导出
data/      v1l_labels.json          44 条 VLM 标签（40,778 B）
           v1l_bo_results.json      120 次评估全记录（含每点 CDi/CL/α/Di/wall）
           v1l_bo_evaluations.csv   同一份记录的 CSV（9,600 B，便于直接读）
           landscape_probe.json     格架对比探针原始输出
           smoke_20x10.json         切换前的冒烟验证
tables/    v1l_arm_metrics.csv / v1l_arm_summary.csv / v1l_paired_differences.csv /
           v1l_predictions.csv / v1l_training_curves.csv / v1l_rank_selection.csv /
           v1l_grid_selection.csv / v1l_cost.csv
logs/      v1l_bo.log（120 次评估逐条）, v1l_train.log（五臂训练逐轮）
receipts/  V1L_RECEIPT.md（完整回执：表格、限制、复现命令）
SHA256SUMS.txt / data_manifest.json   逐文件校验
```

配套源代码（在仓库源码树，不在本包内）：

- `research/concorde_metaopt/evaluation/rcaide_vlm_backend.py` — `SupersonicVLMBackend`，新增
- `research/concorde_metaopt/dreal001/meta/meta_dataset.py` — 新增 `source_kind="rcaide_vlm_20x10"` 与 `require_declared_computed_labels()`
- `research/concorde_metaopt/dreal001/meta/real_a0_ablation.py` — 新增 `mode="vlm_labels"` 分支

## 3. 优化结果（V1L-BO）

任务：Mach 2.02，18,288 m，L_ref = 1,333,704.4 N，q = 20,483.94 Pa，CL_target = 0.181743998494，SREF = 358.25 m²。
目标函数：Trefftz 诱导阻力系数 `CDi`（等 CL 反解 α，割线法 tol 1e-7）。**不含波阻**。
活动子空间：`sweep_1 ∈ [65.5, 68.5]`，`sweep_2 ∈ [46.5, 49.5]`；其余 10 维逐位冻结。

| 项 | sweep_1 | sweep_2 | CDi | α (°) | Di (N) |
|---|---|---|---|---|---|
| baseline | 67.0 | 48.0 | 0.007314667 | 5.528498 | 54,123.416 |
| best (d119) | 65.501955 | 48.636094 | 0.007089604 | 5.508490 | 52,458.110 |

ΔDi = **1,665.306 N（3.08%）**；120/120 status=VALID；总墙钟 78.2 s（单点 0.66–0.77 s）。

跨格架确认（等 CL 反解 α，独立重解）：

| 格架 | baseline CDi | top-5 相对改善 | best 相对改善 |
|---|---|---|---|
| 30×15 | 0.008463523 | −3.6734% … −4.7125% | −4.0776% |
| 45×25 | 0.008133283 | −4.2018% … −4.5543% | −4.2708% |

三条限制（必须与结论同时读）：

1. 最优点压在子空间**下界**（65.501955 vs 下界 65.5，差 0.002°）→ 真实最优可能在子空间外。
2. `sweep_2` 在 20×10 上**不可分辨**：全区间 CDi 变幅仅 0.281%，与 30×15 排序 Spearman = 0.3132（`sweep_1` 为 0.9945）。
3. 20×10 的绝对水平比 30×15 低 13.4%（比值 0.8659）→ 绝对数值不可跨格架比较。

## 4. 训练结果（V1L-A0）

44 条标签全部由 VLM 在 8 个任务上重算（M140/M160/M180/M200/M202/M220/M240/M260）。测试 MAE（N，n=6，K=0/1/3）：

| 臂 | K=0 | K=1 | K=3 |
|---|---|---|---|
| RANDOM_INIT | 41,690 | 15,530 | 25,936 |
| POOLED_PRETRAIN_12D | 41,669 | 13,217 | 25,269 |
| COND_SUPERVISED_16D | **8,595** | 5,363 | 6,677 |
| FOMAML_12D | 47,351 | 15,724 | 28,189 |
| COND_FOMAML_16D | 21,971 | **5,183** | **5,339** |

核心配对 COND_FOMAML − COND_SUPERVISED：K=0 **+13,375 N，CI[+1,390, +25,361]（显著更差）**；K=1 −181 CI[−6,004, +5,643]；K=3 −1,338 CI[−9,588, +6,912]；全 K 合并 +3,952 CI[−2,484, +10,389]。

结论：条件化仍是唯一稳健大效应（验证集 −88%/−95%）；FOMAML 无收益；模型相对误差 15–26% 比 BO 效应 3–4% 大一个数量级 → 用模型排序热启动缺乏可行性依据。

## 5. 复现

```bash
PY="D:/Anaconda/envs/RCAIDE/python.exe"
cd D:/RCAIDE/.worktrees/dreal005-20261124
"$PY" .real_runs/DRECOVER001-V1L-20261125-01/v1l_bo.py       # 120 次评估，约 78 s
"$PY" .real_runs/DRECOVER001-V1L-20261125-01/v1l_train.py    # 五臂训练，约 20 s
```

确定性：两个独立 backend 对同一设计给出**逐位相同**的 CDi（0.0073146665957392271）；BE 优化器为 numpy 实现，seed 固定即可复现 120 条记录。

## 6. 不能声称

- 不能用本包数值与 VSPAERO 结果并列或互相验证（目标函数定义不同：VSPAERO 的 CDi 含波阻，本包为 Trefftz，且 RCAIDE 全链路 `drag.compressible.total` 为 NaN）。
- 不能声称全局最优、不能声称收敛（20×10 格架本身在 V1 审计中判为不收敛）。
- 不能声称 `physics_validated`、不能声称 MAML 优于监督式条件化。
- 绝对 CDi/Di 只在 20×10 格架内成立，跨格架必须附格架号。
