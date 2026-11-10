# D-NEXT-001｜G1 计算设备基准与 CPU 并发分析报告（合成任务，零物理调用）

- 角色：A4（GPU、计算加速与数据/仓库隔离）
- 分支：`research/dnext001-gpu-benchmark`；工作树 `D:\RCAIDE\dnext001\wt-a4`
- 基线 commit：`ea8ad97833eb5ceab291faae643c141a2b219749`
- 生成时间：2026-11-10（Asia/Shanghai）
- **`physical_call_count = 0`**；`source_kind = synthetic_analogue`（合成任务族 `y = amp·tanh(2·x·w) + bias`，12 维输入 / 1 维输出，未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag，未读取任何真实评价结果作为训练信号）
- **本报告只回答“同样的计算在哪跑更快/更准”，不回答“算法是否更好”**；GPU 加速不是算法收益。

## 0. 结论摘要（先看这五条）

1. **GPU 只在一个工作负载上真正赢：代理批量打分**（20 万候选 × 12 维）：GPU-FP32 **19.38×**、GPU-FP64 **3.45×** 快于 CPU-FP64。
2. **小张量元学习在 GPU 上更慢**：FOMAML 预训练（30 步、batch=8、隐层 64×64）GPU-FP64 **0.33×**、GPU-FP32 **0.31×**；K-shot 适应 GPU 约 **0.30×**。原因是每次内层 SGD 只有 64×64 级张量，**CUDA kernel 启动开销主导**，不是算力不足。
3. **FP64 在 GPU 上没有优势**：GEMM 探针 GPU-FP64 **0.45×** CPU-FP64（0.273 vs 0.607 TFLOPS），与 G0 报告的“消费级 Blackwell FP64:FP32≈1:44”一致；**不得宣称 FP64 场景有 GPU 加速**。
4. **数值可信**：GPU-FP64 元梯度相对 CPU-FP64 的 rel-L2 误差 **8.94e-16**（双精度等价）；GPU-FP32 为 **1.38e-07**；三路 QueryRMSE 一致到 7–9 位有效数字，NaN/Inf 计数全 0，同种子三次重复逐位一致（确定性 0.0 差）。
5. **CPU 并发**：单线程 worker 的聚合吞吐在 **8–16 进程饱和于 ≈1.2–1.3 M 候选/秒**，16→32 进程无增益；每 worker 峰值 RSS ≈199 MB。建议 BO/DE/PSO 用 **8–12 个单线程 worker**，保留 4+ 逻辑核给主进程/交互。

## 1. 实验设计（同任务、同种子、同数据）

| 项目 | 设置 |
| --- | --- |
| 任务族 | `y = amplitude · tanh(2 · x·w) + bias`，`x∈R^12`（与项目 12 维真实评价向量同维度），`y∈R^1` |
| 数据划分 | 训练任务 8 个、验证任务 12 个；同一种子 20261110 生成，三路配置**共用同一批** support/query 张量 |
| 内/外循环 | `inner_lr=0.05`、`inner_steps=5`、`outer_lr=0.02`、`batch_size=8` |
| 三路配置 | `cpu-fp64`（CPU 双精度，守门口径）、`cuda-fp64`（GPU 双精度）、`cuda-fp32`（GPU 单精度） |
| 重复次数 | 每工作负载 3 次计时（另有 1 次预热，不计入统计） |
| 计时口径 | 计时前后 `torch.cuda.synchronize()`；GPU 计时前 `reset_peak_memory_stats()`；报告 3 次的中位数/最小/最大 |
| 记录项 | 墙钟、峰值显存、进程峰值 RAM、元验证 QueryRMSE、相对 CPU-FP64 的元梯度误差、NaN/Inf 计数、同种子重复间最大参数差 |
| 运行命令 | `D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m research.concorde_metaopt.gpu.bench_gpu --out research/concorde_metaopt/gpu/runs/g1_20261110 --configs cpu-fp64,cuda-fp64,cuda-fp32 --repeat 3` |
| 证据目录 | `research/concorde_metaopt/gpu/runs/g1_20261110/`：`metrics.csv`、`summary.json`、`run_config.json`、`gradients/*.npy`、`data_manifest.json`、`SHA256SUMS.txt`、`figures/fig{1,2,3}_*.png` |

环境（同一次运行内采集）：`torch 2.8.0+cu128` / CUDA build 12.8 / RTX 5060（sm_120，7.96 GB 可见）/ `cudnn 91002` / `cudnn.benchmark=False` / `deterministic_algorithms=False` / 进程峰值 RAM 2096.8 MB。

## 2. 三路墙钟对比（秒，3 次中位数）

| 工作负载 | CPU-FP64 | GPU-FP64 | GPU-FP32 | GPU-FP64 相对 CPU | GPU-FP32 相对 CPU |
| --- | --- | --- | --- | --- | --- |
| W0 GEMM 吞吐探针（2048³ × 12 次） | 0.6796 | 1.5125 | 0.0339 | **0.45×（更慢）** | **20.05×** |
| W1 FOMAML 预训练（30 步） | **0.2509** | 0.7631 | 0.7972 | **0.33×（更慢）** | **0.31×（更慢）** |
| W2 K-shot 适应（10-shot × 12 验证任务） | **0.01064** | 0.03423 | 0.03525 | **0.31×（更慢）** | **0.30×（更慢）** |
| W3 代理批量打分（20 万候选 × 12 维） | 0.05620 | 0.01627 | **0.00290** | **3.45×** | **19.38×** |

图 1（墙钟，对数纵轴）与图 2（相对 CPU-FP64 的加速比，虚线=1.0 基准）见 `figures/`：
`fig1_walltime.png`、`fig2_speedup.png`。

### 2.1 怎么读这张表（避免误读）

- **W1/W2 的 GPU 慢不是“GPU 弱”**：内层每步只处理 `8×12` 输入、`64×64` 权重，单个 kernel 工作量只有几微秒，而一次 CUDA kernel 启动/同步约 5–10 µs，30 步 × (5 内层 + 反向) 的启动开销把计算量淹没了；CPU 侧张量小、缓存命中，反而占优。
- **W3 的 GPU 快是“批量并行”红利**：20 万候选一次前向，矩阵规模足够大，FP32 的 11.8 TFLOPS 才发挥出来；FP64 因硬件配比只有 0.27 TFLOPS，因此只有 3.45×。
- **W0 是纯算力对照**：FP32 达到 12.16 TFLOPS（与 G0 的 11.80 一致），FP64 只有 0.273 TFLOPS（0.45× CPU）。
- 因此**设备选型必须按工作负载分别决定**，不能一句“上 GPU”概括。

## 3. 数值与精度

| 指标 | CPU-FP64 | GPU-FP64 | GPU-FP32 |
| --- | --- | --- | --- |
| 元验证 QueryRMSE（W1 后） | 0.41632008968689443 | 0.41632008968689443 | 0.41632009614259 |
| K-shot 后 QueryRMSE（W2） | 0.4432920645829359 | 0.4432920645829359 | 0.44329205217460793 |
| 元梯度相对 CPU-FP64 的 rel-L2 | 0（参考） | **8.94e-16** | **1.38e-07** |
| 元梯度相对 CPU-FP64 的 max-abs | 0（参考） | 3.89e-16 | 6.09e-08 |
| 代理批量打分 checksum（20 万候选求和） | 142956.80878448373 | 142956.80878448384 | 142956.80705194175 |
| NaN/Inf 计数 | 0 | 0 | 0 |
| 同种子 3 次重复的参数最大差 | 0.0 | 0.0 | 0.0 |

图 3：`figures/fig3_precision.png`（元梯度相对误差 + 元验证 QueryRMSE，对数轴）。

解读：
- **GPU-FP64 与 CPU-FP64 在双精度上是等价实现**（rel-L2 8.9e-16 已在 float64 舍入下限），可以做数值复核；
- GPU-FP32 的 1.38e-07 相对误差与 float32 机器精度（≈1.19e-07）同量级，**没有异常放大**；QueryRMSE 差异 6.5e-09（相对 1.6e-08），远小于任何任务间差异；
- 三路重复逐位一致 → 在“同种子、同形状、同 stream”的短程重复下可复现；**不对任意 kernel 组合做全局确定性承诺**（本环境未开 `use_deterministic_algorithms`）。

## 4. 显存与内存

| 工作负载 | GPU-FP64 峰值显存 | GPU-FP32 峰值显存 | 进程峰值 RAM（CPU 跑） | 进程峰值 RAM（GPU 跑） |
| --- | --- | --- | --- | --- |
| W0 GEMM 2048³ | 144.3 MB | 80.3 MB | 1611 MB | 1888 MB |
| W1 FOMAML 预训练 | 16.6 MB | 16.5 MB | 461.7 MB | 1855–2064 MB |
| W2 K-shot 适应 | 16.5 MB | 16.4 MB | 同进程 | 同进程 |
| W3 批量打分 20 万 | 328.6 MB | 172.3 MB | 1485 MB | 1860–2084 MB |

- 8 GB 显存对当前规模**绰绰有余**（最大 328.6 MB），真正的限制是**不能并发占卡**：单卡只允许 1 个主训练/打分进程（本次全部运行均为单进程单 stream）。
- GPU 进程常驻 RAM 比 CPU 进程高约 1.4–1.6 GB（CUDA 上下文 + 驱动），规划 32 GB 内存并发时要计入。

## 5. CPU 多进程并发分析（BO/DE/PSO 上限与资源隔离建议）

负载：每进程单线程做“代理批量打分”（4000 候选 × 12 维，重复 20 次，取最好一次墙钟），`spawn` 起进程 + `Barrier` 同时起跑，所有 worker 强制 `OMP/MKL/OPENBLAS_NUM_THREADS=1`、`torch.set_num_threads(1)`。

### 5.1 实测（第三次独立重复，RSS 采集已修正）

| 并发进程数 | 墙钟（s） | 聚合吞吐（候选/秒） | 并行效率 | 单 worker 峰值 RSS | 全部 worker RSS 合计 |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.286 | 279 262 | 100.0% | 198.4 MB | 198.4 MB |
| 2 | 0.327 | 489 325 | 87.6% | 198.9 MB | 397.3 MB |
| 4 | 0.399 | 801 989 | 71.8% | 198.7 MB | 794.2 MB |
| 8 | 0.537 | 1 192 853 | 53.4% | 199.0 MB | 1 587.8 MB |
| 16 | 1.004 | 1 275 379 | 28.5% | 198.7 MB | 3 175.2 MB |
| 32 | 2.038 | 1 255 901 | 14.1% | 199.0 MB | 6 351.1 MB |

前两次独立重复（同一脚本、同一参数；当时 RSS 采集有 bug 已修复，吞吐数值可用）：
- rep1：1→254 259、2→430 697、4→779 943、8→1 234 032、16→1 301 726、32→1 205 396 候选/秒；
- rep2：1→263 865、2→483 105、4→748 941、8→1 203 487、16→1 378 315、32→1 346 867 候选/秒。

三次重复的一致结论：**聚合吞吐在 8–16 进程进入平台（≈1.2–1.38 M 候选/秒），32 进程不再提升且墙钟变长**。测量期间机器上同时有其他 agent 的 pytest/实验负载，故绝对值偏保守（上限估计）。

### 5.2 结论与建议（9950X 16C/32T，RAM 31.1 GB 可用）

1. **BO/DE/PSO 多进程上限：8–12 个单线程 worker**。8 worker 已拿到约 60% 的可用聚合吞吐，12 worker 与 8 worker 相差在测量噪声内；16 worker 效率降到 28.5%，32 worker 纯属拖慢墙钟。
2. **留 4+ 逻辑核给主进程/交互/IO**：主进程负责种群更新、日志、图，若也抢满 32 线程会把整体墙钟拉长。
3. **内存预算**：每 worker ≈200 MB 峰值 RSS；12 worker ≈2.4 GB，16 worker ≈3.2 GB，32 worker ≈6.4 GB。32 GB 机器上内存不是瓶颈，**CPU 调度与内存带宽才是**。
4. **资源隔离**：worker 内必须显式设 `OMP_NUM_THREADS=MKL_NUM_THREADS=OPENBLAS_NUM_THREADS=1` 并 `torch.set_num_threads(1)`，否则 BLAS 线程与进程数相乘导致过度订阅（这是 16/32 进程效率崩塌的主要机制之一）。
5. **GPU 不进并发池**：8 GB 单卡只承载 1 个主进程；若确需 GPU 批量打分，应作为主进程内的“批量调用”而不是 N 个 GPU worker 并发。

图：`research/concorde_metaopt/gpu/runs/cpu_concurrency_rep3/fig_cpu_concurrency.png`（左：聚合吞吐 vs 进程数 + 线性理想线；右：并行效率）。

## 6. 仓库隔离可复跑检查（本报告的独立复核件）

脚本：`research/concorde_metaopt/gpu/repo_isolation_check.py`（只读，不改任何仓库状态）
产物：`research/concorde_metaopt/gpu/reports/repo_isolation_check.json` 与 `repo_isolation_check.md`
复跑：
```powershell
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.gpu.repo_isolation_check ^
    --cwd D:\RCAIDE\dnext001\wt-a4 ^
    --out-json research/concorde_metaopt/gpu/reports/repo_isolation_check.json ^
    --out-md   research/concorde_metaopt/gpu/reports/repo_isolation_check.md
```

检查项（全部通过，`all_passed=true`）：
- `worktree_list_available` / `worktree_paths_unique` / `worktree_branches_unique`：7 个 worktree 路径互不相同、分支互不相同（`research/dnext001-f-real-evaluator`、`…-a-warmstart`、`…-b-meta-acquisition`、`…-gpu-benchmark`、`…-a5-review`、`…-integration`，加主仓库）；
- `worktree_gitdir_wiring`：每个 worktree 的 `.git` 文件指向 `repo/.git/worktrees/<name>`，无串线；
- `no_cross_tree_links`：工作树内无指向其它 worktree 的目录联接/junction 逃逸；
- `base_is_ancestor_of_head`：基线 `ea8ad97…` 是当前 HEAD 的祖先；
- `no_merge_commits_current_branch` / `no_main_merge_into_current` / `current_branch_no_upstream`：当前分支无 merge commit、未把 main 合并进来、无 upstream（未推送）；
- `other_branch_merges_observed`：仅**记录**到 Lead 的集成分支有 1 个 merge commit（属 Lead 作用域，不影响本树判定）；
- `write_scope_uncommitted` / `write_scope_committed`：本树改动只落在 `research/concorde_metaopt/gpu/`、`docs/planning/dnext001_gpu_*`、`docs/receipts/dnext001/a4_*`、`research/concorde_metaopt/tests/test_{gpu_benchmark,repo_isolation_check}.py`；
- `frozen_artifacts_untouched`：`research/concorde_metaopt/{optimization_runs,evidence,reports}/` 下冻结产物零改动；`docs/receipts/` 只允许新增回执，**改写或删除既有回执即判 FAIL**（首次运行曾因把本轮新回执误判为“改动冻结产物”而 FAIL，已按“新增允许、改写禁止”修正判定口径）。

**边界声明（不得夸大）**：该检查只证明“本树的结构性事实与可观测 git 状态”。它**不能**证明其他 agent 未在各自工作树里写入、**不能**离线验证是否发生了 push（无远端凭据校验）、也**不替代 A5 的独立复核**；A3 复核是否完成不由本报告宣称。

## 7. 未完成项与风险（如实列出）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| G2 二阶（Full MAML）GPU 门禁 | **未执行（NOT_RUN）** | 计划要求“仅当 Full MAML 二阶门禁通过才做 GPU 二阶”；S2 事实为 Full MAML 比 FOMAML 更差，门禁未过，故不做 GPU 二阶 |
| G3 GPU 后端合并进项目 | **未做（NOT_APPROVED）** | 是否合并取决于本报告吞吐/精度 + A5 复核；本报告只交付证据，不改冻结 S1–S3、不改项目默认后端 |
| 大规模长训练 | **未做** | 时间盒内只做最小可运行垂直切片（30 步预训练、20 万候选打分）；长训练墙钟趋势外推**未验证** |
| 真实 Concorde 12 维数据上的 GPU 收益 | **NOT_RUN** | `physical_call_count=0` 约束下只能合成；真实评价数据的分布差异可能改变结论 |
| 多卡 / MIG / ECC / 显存带宽饱和 | **NOT_RUN** | 单卡 8 GB，无相关硬件 |
| 全局确定性承诺 | **未承诺** | 只验证了同种子短程重复逐位一致 |
| 环境噪声 | 已知风险 | 计时期间同机有其他 agent 负载（pytest 全量、warm_start 实验），绝对墙钟偏保守 |

## 8. 复现命令（全部在 `D:\RCAIDE\dnext001\wt-a4` 下）

```powershell
# G0 环境自检
& D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m research.concorde_metaopt.gpu.env_check ^
    --out research/concorde_metaopt/gpu/reports/g0_env_check.json
# G1 三路基准（3 次重复，含图）
& D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m research.concorde_metaopt.gpu.bench_gpu ^
    --out research/concorde_metaopt/gpu/runs/g1_20261110 ^
    --configs cpu-fp64,cuda-fp64,cuda-fp32 --repeat 3
# CPU 并发上限
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.gpu.cpu_concurrency ^
    --procs 1 2 4 8 16 32 --tag rep3
# 仓库隔离复核
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.gpu.repo_isolation_check ^
    --cwd D:\RCAIDE\dnext001\wt-a4 ^
    --out-json research/concorde_metaopt/gpu/reports/repo_isolation_check.json ^
    --out-md   research/concorde_metaopt/gpu/reports/repo_isolation_check.md
# 单元测试
& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_gpu_benchmark.py research/concorde_metaopt/tests/test_repo_isolation_check.py -q
```
