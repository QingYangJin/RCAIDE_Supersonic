# A4 任务回执（D-NEXT-001｜GPU、计算加速与数据/仓库隔离）

* 角色：A4（GPU 性能 / CPU 并发 / 仓库隔离），teammate `a4-gpu-perf`
* 共享任务：`task-4`（已 claim，revision 1 → in_progress）
* 工作树：`D:\RCAIDE\dnext001\wt-a4`
* 分支：`research/dnext001-gpu-benchmark`
* 基线 commit：`ea8ad97833eb5ceab291faae643c141a2b219749`
* 生成时间：2026-11-10（Asia/Shanghai）
* **physical_call_count = 0**：本轮未启动 VSPAERO / SU2 / RCAIDE Mission / WaveDrag，全部为**合成任务（synthetic）**与**结构性 git 只读检查**；未读取或改写任何真实物理求解产物。

---

## 1. 本轮交付物（对照 m00001）

| 编号 | 要求 | 状态 | 证据 |
| --- | --- | --- | --- |
| G0 | 独立 CUDA 环境，不改 `D:\RCAIDE\envs\RCAIDE` | **DONE** | `D:\RCAIDE\dnext001\gpu-env`（venv）+ `docs/planning/dnext001_gpu_environment_report.md` + `research/concorde_metaopt/gpu/reports/g0_env_check.json` |
| G0 | 真实 forward/backward FP32/FP64、确定性、峰值显存 | **DONE** | `env_check.py` 自检结果写入 g0_env_check.json（FP64 与 CPU 参考逐元素一致；FP32 rel≈3e-7；4 配置×3 重复 bitwise 一致） |
| G1 | 同任务同种子 CPU-FP64 / GPU-FP64 / GPU-FP32 三路基准 | **DONE** | `research/concorde_metaopt/gpu/runs/g1_20261110/`（metrics.csv / summary.json / 图 3 张 / 梯度 npy / SHA256SUMS） |
| G1 | synchronize、重复≥3、墙钟/显存/RAM/RMSE/梯度误差/数值异常 | **DONE** | `bench_gpu.py` 的 Stopwatch（前后 `torch.cuda.synchronize()`）+ `reset_peak_memory_stats`；每配置 1 预热 + 3 重复 |
| G2 | Full MAML 二阶 GPU 门禁 | **NOT_RUN**（按计划门禁，未获授权） | 本回执第 5 节风险说明 |
| G3 | 合并 GPU 后端 | **NOT_APPROVED** | 需 A5 复核 + Lead 决策 |
| CPU 并发 | 1/2/4…进程实测 + BO/DE/PSO 并发上限与隔离建议 | **DONE** | `runs/cpu_concurrency_rep3/`（另 rep1/rep2 历史数据）；报告第 5 节 |
| 隔离 | 仓库隔离可复跑检查脚本 + 说明 | **DONE** | `repo_isolation_check.py` + `reports/repo_isolation_check.json/.md`（all_passed=true，exit 0） |
| 降级 | CUDA 不可用时 NOT_RUN + 降级计划 | 不适用（CUDA AVAILABLE，未降级） | g0_env_check.json：`cuda_available=true` |

---

## 2. 新增/修改文件清单

### 代码（全部新增）
| 文件 | 大小 | 作用 |
| --- | --- | --- |
| `research/concorde_metaopt/gpu/__init__.py` | 小 | 包标记 |
| `research/concorde_metaopt/gpu/torch_fomaml.py` | ≈9.5 KB | 设备常驻 FOMAML（张量常驻、无每步 numpy 往返）；`forward/mse/inner_adapt/fomaml_step/adapt_and_score/batch_score/init_parameters` |
| `research/concorde_metaopt/gpu/bench_gpu.py` | ≈26 KB | G1 基准 CLI：W0 GEMM 探针 / W1 FOMAML 预训练 / W2 K-shot 适应 / W3 代理批量打分；CSV+JSON+梯度+图 |
| `research/concorde_metaopt/gpu/make_figures.py` | ≈5.8 KB | 中文科研图（墙钟、加速比、精度），Agg 后端 |
| `research/concorde_metaopt/gpu/env_check.py` | 新增 | G0 自检 CLI：设备报告、FP32/FP64 前向反向对照、确定性、GEMM 吞吐与峰值显存 |
| `research/concorde_metaopt/gpu/cpu_concurrency.py` | 新增 | CPU 并发基准：spawn + Barrier 同时起跑、每进程单线程、聚合吞吐/并行效率/RSS |
| `research/concorde_metaopt/gpu/repo_isolation_check.py` | 新增 | 只读仓库隔离检查（15 项），输出 JSON + 中文 Markdown |
| `research/concorde_metaopt/tests/test_gpu_benchmark.py` | 新增 | 8 个测试：与项目 `maml.meta_train_step` 的一阶梯度等价性、确定性、FP32 偏差、batch_score 形状等 |
| `research/concorde_metaopt/tests/test_repo_isolation_check.py` | 新增 | 6 个测试：worktree 解析、冻结前缀、渲染、真实树 evaluate 结构 |

### 文档与回执
* `docs/planning/dnext001_gpu_environment_report.md`（中文，G0 环境报告）
* `docs/planning/dnext001_gpu_benchmark_report.md`（中文，G1 性能 + CPU 并发 + 隔离检查报告）
* `docs/receipts/dnext001/a4_task_receipt.md`（本文件）

### 证据产物（提交入库）
* `research/concorde_metaopt/gpu/reports/g0_env_check.json`
* `research/concorde_metaopt/gpu/reports/repo_isolation_check.json` + `.md`
* `research/concorde_metaopt/gpu/runs/g1_20261110/`：`metrics.csv`、`summary.json`、`run_config.json`、`data_manifest.json`、`SHA256SUMS.txt`、`gradients/*.npy`（18 个）+ `gradient_index.json`、`figures/fig1_walltime.png`、`fig2_speedup.png`、`fig3_precision.png`、`figure_index.json`
* `research/concorde_metaopt/gpu/runs/cpu_concurrency_rep3/`（`cpu_concurrency.csv`、`summary.json`、`fig_cpu_concurrency.png`）；rep1/rep2 目录保留为历史重复（其时 RSS 字段采集 bug 未修，仅吞吐可用）

### 冻结产物
S1/S2/S3 的 run 目录、manifest、SHA 文件 **零改动**（隔离检查 `frozen_artifacts_untouched` PASS）。本轮未 stage 任何冻结路径。

---

## 3. 实际运行的命令与结果

### 3.1 单元测试（通过的判据）
```powershell
cd D:\RCAIDE\dnext001\wt-a4
& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest `
    research/concorde_metaopt/tests/test_gpu_benchmark.py `
    research/concorde_metaopt/tests/test_repo_isolation_check.py -q
```
结果：**14 passed in 7.81s**（test_gpu_benchmark 8 个 + test_repo_isolation_check 6 个）。

关键测试 `test_fomaml_step_matches_project_maml`：用同一随机种子与同一 support/query 数据，比较本模块一次 FOMAML 外更新后的参数与项目 `research/concorde_metaopt/meta_learning/maml.py:meta_train_step` 的结果，逐元素相对误差阈值 1e-9，**实测通过** → 证明加速实现与项目一阶梯度定义一致，不是另一套算法。

### 3.2 G0 环境自检（CUDA venv）
```powershell
& D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m research.concorde_metaopt.gpu.env_check `
    --out research/concorde_metaopt/gpu/reports/g0_env_check.json
```
结果：torch 2.8.0+cu128，CUDA available，RTX 5060（sm_120, 8150.6 MB, 30 SM），驱动 610.88。
* FP64：CUDA 与 CPU 参考**逐元素完全一致**（max abs err 0.0）。
* FP32：前向 rel≈3.1e-7，权重梯度 rel≈3.2e-7；仍属正常数值误差。
* 确定性：4 配置 × 3 次重复，参数/梯度 bitwise 一致，max_grad_delta=0.0。
* GEMM 2048³×10：CPU-FP64 553.0 GFLOPS；**CUDA-FP64 269.9 GFLOPS（0.49× CPU）**；CUDA-FP32 11799.2 GFLOPS。
* 峰值显存：gemm 已分配 144.2 MB(fp64)/80.2 MB(fp32)，保留 174.0 MB。

### 3.3 G1 三路基准
```powershell
& D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m research.concorde_metaopt.gpu.bench_gpu `
    --out research/concorde_metaopt/gpu/runs/g1_20261110 `
    --configs cpu-fp64,cuda-fp64,cuda-fp32 --repeat 3
```
（seed=20261110，合成任务族 `y = amp·tanh(2·x·w) + bias`，12 维输入；8 训练 / 12 验证任务；inner_lr=0.05、inner_steps=5、outer_lr=0.02、batch=8；每配置 1 预热 + 3 重复，计时窗口前后均 `torch.cuda.synchronize()`。）

墙钟中位数与精度见 `docs/planning/dnext001_gpu_benchmark_report.md` 第 2–3 节；要点：
* 小批量元学习（W1/W2）：GPU 比 CPU 慢约 3×（kernel 启动开销主导，张量仅 8×12）。
* 代理批量打分（W3，20 万×12）：GPU-FP32 **19.38×**、GPU-FP64 **3.45×**（相对 CPU-FP64）。
* 元梯度与 CPU-FP64 相比：cuda-fp64 rel_l2 8.94e-16；cuda-fp32 rel_l2 1.38e-7。
* NaN/Inf 计数 0；确定性重复 max_param_delta 全 0。

### 3.4 CPU 并发基准
```powershell
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.gpu.cpu_concurrency `
    --procs 1 2 4 8 16 32 --tag rep3
```
聚合吞吐（候选/秒）：1→279262；2→489325；4→801989；8→1.19M；16→1.28M；32→1.26M（并行效率 32 进程仅 14%）。
每 worker 峰值 RSS ≈199 MB（20 万候选批量打分负载）。

### 3.5 仓库隔离检查
```powershell
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.gpu.repo_isolation_check `
    --cwd D:\RCAIDE\dnext001\wt-a4 `
    --out-json research/concorde_metaopt/gpu/reports/repo_isolation_check.json `
    --out-md   research/concorde_metaopt/gpu/reports/repo_isolation_check.md
```
结果：**all_passed=true，exit code 0**。检查 7 个 worktree 路径唯一、分支互不相同、gitdir 接线正确、无跨树链接（junction/symlink）、当前分支无 merge、未把 main 合入、无 upstream、写作用域仅在允许前缀、冻结产物零改动。

---

## 4. 证据指纹（SHA256）

| 文件 | SHA256 |
| --- | --- |
| `research/concorde_metaopt/gpu/reports/g0_env_check.json` | `6F9BE6F56E1424904C0A001931AAA9BAF926D1807FA03F626CACE7AD0728911A` |
| `research/concorde_metaopt/gpu/reports/repo_isolation_check.json` | `85C38F710CAC11F34BE813ABCE9213C837C06AEE5A88E99384DCEFC968952303` |
| `runs/g1_20261110/summary.json` | `1B48180201263A325A00E79DBBDE7F064F3AF52769215FAF48E5C7071DFEB3A1` |
| `runs/g1_20261110/metrics.csv` | `E39B9D872E2795F812544E1EE2F4A1FA83E6A529B169A600BD29E2B956E7110B` |
| `runs/cpu_concurrency_rep3/summary.json` | `2B369D392A064B04E5471340939CB891FCF2C5D8A4AF6F2C8C5086A79A0FB925` |
| `runs/cpu_concurrency_rep3/cpu_concurrency.csv` | `4B7945028B3B6FE9B30AC35273E2049ED2B951480642740FCB14A725E25CF3CC` |
| CUDA venv `gpu_env_pip_freeze.txt` | `CC9B1BD0019E8C9B1B174CD9AB9320E56C6B5FF0C8F51272855B4C6CE91B720F` |
| torch wheel（cu128） | `34c55443aafd31046a7963b63d30bc3b628ee4a704f826796c865fdfd05bb596` |

环境报告与基准报告内亦引用了原环境未改动证据（RCAIDE `torch/__init__.py` 与 `version.py` 的 SHA256、pip freeze before/after 内容 diff 为空）。

---

## 5. 未完成项、限制与风险（如实声明）

| 项 | 状态 | 说明 |
| --- | --- | --- |
| G2 Full MAML 二阶 GPU 实现 | **NOT_RUN** | 计划规定“仅当 Full MAML 二阶门禁通过才做 GPU 二阶”。上一阶段事实为 S2 Full MAML 比 FOMAML 更差，门禁未通过，故本轮不做二阶，不得据此宣称任何算法收益。 |
| G3 合并 GPU 后端 | **NOT_APPROVED** | 需 A5 独立复核 + Lead 决策；本轮不碰正式训练入口，不改 S1–S3 冻结产物。 |
| 长训练 / 全量实验 | **NOT_RUN** | 时间盒限制；仅 30 步预训练、12 验证任务、3 次重复。结论只适用于该规模。 |
| 真实 Concorde/物理数据上的 GPU 收益 | **NOT_RUN** | 全部合成任务；真实数据 NOT_RUN，不作外推。 |
| 多卡 / 多 GPU 并发 | **NOT_RUN** | 单卡 RTX 5060；且硬约束禁止超过单主训练进程的 GPU 并发。 |
| RTX 5060 FP64 吞吐 | **未证实（且实测劣于 CPU-FP64）** | 实测 GEMM 2048³ CUDA-FP64 = 269.9 GFLOPS，仅 CPU-FP64（553.0）的 0.49×。**不得宣称 FP64 加速**。 |
| 全局确定性 | **未承诺** | 只证明同配置同进程内重复 bitwise 一致；未设 `cudnn.deterministic=True`，未做跨进程/跨驱动位级复现承诺。 |
| 测量噪声 | 存在 | 机器同时有其他 agent 计算，CPU 并发吞吐在 8–16 进程区间波动（rep1/rep2/rep3 三次数值差异见报告）；报告只给区间与结论方向，不宣称精确倍数。 |
| 隔离检查判定口径修正 | 已修 | 首次 post-commit 复跑时 `frozen_artifacts_untouched` 误报（把本轮**新增**的 `docs/receipts/dnext001/a4_task_receipt.md` 当作“改动冻结产物”）。已将冻结判定拆为两类：`research/concorde_metaopt/{optimization_runs,evidence,reports}/` 严格禁止任何改动；`docs/receipts/` 允许新增回执，仅 `--diff-filter=MDR`（改写/删除既有回执）判 FAIL。修正后 14 tests 通过、检查 all_passed=true、exit 0。 |
| A3/A5 复核 | **未完成（非本角色职责）** | 本隔离检查只证明结构性 + 可观测事实，**不能证明其他 agent 未在其自身工作树写入，也无法离线验证是否 push 过远端**，因此**不替代 A5 独立复核**，更不能宣称 A3 复核已完成。 |
| 原环境使用 | 未改动 | RCAIDE 环境仍为 `torch 2.8.0+cpu`；CUDA 依赖全部装在独立 venv `D:\RCAIDE\dnext001\gpu-env`。 |
| 工作树外残留 | 已知 | `D:\RCAIDE` 根下仍有安装期间 pip 生成的临时目录（`pip-unpack-*` 等）。**未删除**：当时无法确认其他 agent 是否正在使用同类临时目录，避免误删他人正在进行的 pip 进程产物；这些目录不在任何 git 工作树内，不影响仓库状态。 |

---

## 6. 结论一句话

在 **不触碰原环境、不调用任何真实物理求解（physical_call_count=0）** 的前提下，独立 CUDA 环境（torch 2.8.0+cu128）建成并完成三路数值/性能基准：**GPU-FP64 在本卡上不具加速价值（GEMM 0.45–0.49× CPU-FP64），GPU-FP32 仅在批量打分/大 GEMM 有实质收益（19–20×），小批量元学习循环 GPU 反而慢约 3×**；CPU 并发建议 8–12 个单线程 worker；仓库隔离检查可独立复跑且全部通过。以上均为工程性能事实，不构成任何算法收益或科学结论。
