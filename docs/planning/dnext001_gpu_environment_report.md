# D-NEXT-001｜G0 独立 CUDA 环境建设报告（RTX 5060 / torch 2.8.0+cu128）

- 角色：A4（GPU、计算加速与数据/仓库隔离）
- 分支：`research/dnext001-gpu-benchmark`；工作树 `D:\RCAIDE\dnext001\wt-a4`
- 基线 commit：`ea8ad97833eb5ceab291faae643c141a2b219749`（S3 封账 c7221fb + 官方计划文档）
- 生成时间：2026-11-10（Asia/Shanghai）
- `physical_call_count = 0`：本报告所有测量均为合成张量 / 合成任务族，未启动 VSPAERO、SU2、RCAIDE Mission、WaveDrag 等任何真实物理求解器。

## 0. 结论摘要

1. **CUDA 可用**：在**独立 venv**（`D:\RCAIDE\dnext001\gpu-env`，工作树之外、同盘工作区）中成功安装 `torch 2.8.0+cu128`，`torch.cuda.is_available()=True`，识别设备 `NVIDIA GeForce RTX 5060`，计算能力 **(12, 0) = sm_120**，可用显存 8150.6 MB。
2. **原环境零改动**：`D:\RCAIDE\envs\RCAIDE` 仍为 `torch 2.8.0+cpu`（`torch.cuda.is_available()=False`），torch 文件 SHA256 与安装前一致，pip freeze 内容前后**逐行无差异**（详见 §5）。
3. **FP64 在 GPU 上真实执行且数值正确**：FP64 前向/反向与 CPU float64 参考**逐元素完全一致（最大绝对误差 0.0）**；FP32 相对误差 ~3.1e-7，量级符合 float32 舍入。三种配置重复 3 次**逐位相同**（确定性 OK）。
4. **重要负结果（必须如实写入后续报告）**：RTX 5060 是消费级 Blackwell，**FP64 吞吐被人为压低**。实测方阵 GEMM（2048³）：CUDA-FP64 **270 GFLOPS**、CUDA-FP32 **11 799 GFLOPS**（FP64:FP32 ≈ **1:44**）；而本机 CPU-FP64 为 **553 GFLOPS**。即 **GPU-FP64 比 CPU-FP64 还慢约 2 倍（0.49×）**。因此 **G1 中任何 "GPU 加速" 只能来自 FP32，不能来自 FP64；不得宣称 FP64 加速**。
5. **CUDA 路径可用**，故 G1 三路对比（CPU-FP64 / GPU-FP64 / GPU-FP32）按计划完整执行，无 NOT_RUN 降级。

## 1. 硬件与驱动事实（nvidia-smi / WMI 实测）

| 项目 | 实测值 | 来源 |
| --- | --- | --- |
| GPU | NVIDIA GeForce RTX 5060 | `nvidia-smi --query-gpu=name` |
| 显存 | 8151 MiB（torch 报 8150.6 MB） | nvidia-smi / `torch.cuda.get_device_properties(0).total_memory` |
| 驱动版本 | 610.88 | nvidia-smi |
| CUDA UMD（驱动侧） | 13.3 | nvidia-smi |
| 计算能力 | **12.0（sm_120，Blackwell）** | nvidia-smi / torch capability |
| SM 数量 | 30 | torch device properties |
| PCIe 链路 | Gen5 ×8（`pcie.link.gen.max=5`、`pcie.link.width.max=8`） | nvidia-smi |
| CPU | AMD Ryzen 9 9950X，16C/32T，MaxClockSpeed 4300 MHz | Win32_Processor |
| 内存 | 31.1 GB（32 GB 机器） | Win32_ComputerSystem |
| D: 盘可用 | 356 720 590 848 bytes（≈332 GB） | Get-PSDrive |
| 操作系统 | Windows 10.0.26200（`Windows-10-10.0.26200-SP0`） | platform.platform() |

## 2. CUDA 构建版本选择依据

- sm_120（Blackwell）**不在 cu126 及更早构建的编译目标列表内**，PyTorch 2.8 官方 wheel 矩阵中支持 sm_120 的最低常用 CUDA 构建是 **cu128**。
- 驱动 610.88 的 CUDA UMD 为 13.3，对 cu128 运行时向后兼容，无需降级驱动。
- 因此选定 `torch==2.8.0` 的 **cu128** wheel：
  `torch-2.8.0+cu128-cp311-cp311-win_amd64.whl`（3 461 420 395 bytes = 3.22 GiB）。
- 该 wheel 的安装哈希（来自 `pip freeze`）：
  `sha256=34c55443aafd31046a7963b63d30bc3b628ee4a704f826796c865fdfd05bb596`。

## 3. 独立环境构建（不改 RCAIDE 原环境）

### 3.1 路径与解释器

| 项目 | 值 |
| --- | --- |
| venv 路径 | `D:\RCAIDE\dnext001\gpu-env`（**不在任何 git 工作树内**，不污染仓库） |
| venv Python | 3.11.17（cp311，与 RCAIDE 原环境同为 3.11.17） |
| `pyvenv.cfg` | `home = D:\RCAIDE\envs\RCAIDE`；`include-system-site-packages = false`；创建命令 `D:\RCAIDE\envs\RCAIDE\python.exe -m venv D:\RCAIDE\dnext001\gpu-env` |
| 隔离验证 | `env_check` 记录 `executable = D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe`、`torch 2.8.0+cu128`；RCAIDE 解释器仍为 `2.8.0+cpu`（§5） |
| 环境指纹 | `pip freeze` → `D:\RCAIDE\dnext001\gpu-env-logs\gpu_env_pip_freeze.txt`，**SHA256 = CC9B1BD0019E8C9B1B174CD9AB9320E56C6B5FF0C8F51272855B4C6CE91B720F** |

依赖清单（freeze 全文）：torch 2.8.0+cu128（file URL 安装）、numpy 2.4.6、matplotlib 3.11.2（含 contourpy/cycler/fonttools/kiwisolver/pillow/pyparsing/python-dateutil/tzdata）、filelock 4.2.10、fsspec 2026.9.0、Jinja2 3.1.6、MarkupSafe 3.0.4、mpmath 1.3.0、networkx 3.6.1、packaging 26.3、sympy 1.14.0、typing_extensions 4.16.0。

注意：本 venv **没有** pytest，也没有 pandas/scipy；A4 的测试仍用 RCAIDE 解释器（pytest 9.2.0）执行，GPU 脚本用 venv 解释器执行，两者职责分离，互不污染。

### 3.2 最终可用的安装路径（三次失败后确定）

```powershell
# 1) 纯 Python 依赖走清华镜像（PyPI 直连在本机可用但 pip 解析会出现“CPU 空转”，见 §4）
& D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m pip install --no-cache-dir ^
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple ^
    filelock typing-extensions sympy networkx jinja2 fsspec setuptools numpy matplotlib

# 2) 用 curl 直接下载 cu128 wheel（23.65 MB/s，2 分 22 秒）
curl.exe -L --retry 5 -C - -o torch-2.8.0+cu128-cp311-cp311-win_amd64.whl ^
    https://download-r2.pytorch.org/whl/cu128/torch-2.8.0%2Bcu128-cp311-cp311-win_amd64.whl

# 3) 本地 wheel 安装（--no-deps：依赖已单独装好；文件名必须是合法的 wheel 文件名）
& D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m pip install --no-deps ^
    D:\RCAIDE\dnext001\gpu-env-logs\torch-2.8.0+cu128-cp311-cp311-win_amd64.whl
```

自检输出（真实终端回显）：
```
torch 2.8.0+cu128
cuda_available True
device NVIDIA GeForce RTX 5060
capability (12, 0)
torch_cuda 12.8
total_mem_mb 8150.6
```

## 4. 失败证据与教训（保留负结果，便于他人复现时避开）

| 尝试 | 命令要点 | 结果 | 证据文件 |
| --- | --- | --- | --- |
| A | `pip install torch==2.8.0+cu128 --index-url .../cu128 --extra-index-url https://pypi.org/simple` | 约 8 分钟无下载进展；pip cache `http-v2` 停在 1099 MB 不增长，pip 进程 CPU 累计 210 s+，site-packages 为空 → 判为解析器在 PyPI 巨型索引上回溯，人工 kill | `D:\RCAIDE\dnext001\gpu-env-logs\pip-torch-cu128.log` |
| B | 仅单一 cu128 索引 `pip install torch==2.8.0` | 解析阶段正常输出 metadata 后**停滞**：`pip2.log` 最后一行停在 14:12:19；进程 CPU 446 s、cache 1230 MB 30 s 零增长 → kill | `pip2.log`、`pip2.status` |
| C | (inline) `pip install` 一组小依赖（pypi.org） | 6 分钟仍无任何包落地，但同期 `curl https://pypi.org/simple/numpy/` 2.03 s / 200 OK、1.15 MB/s → 网络本身正常，问题在 pip 的解析/重试路径 → kill | `g0.status` |
| D | **改用 curl 直下 wheel + `pip install --no-deps` + 依赖走清华镜像** | ✅ 全部成功（三步合计 < 6 分钟，其中下载 2:22、23.65 MB/s） | `curl_download.log`、`torch_install2.log` |

教训（对后续同类环境建设有效）：

1. **不要**给 pytorch 专用索引再叠加 `--extra-index-url https://pypi.org/simple`，解析器会在 PyPI 巨型索引上回溯到长时间无进展。
2. 本机 pip 存在“打印了 Successfully installed 但进程仍在空转（CPU 持续累积）”的现象，安装脚本必须自带超时 / 进程检查；本次最终安装后手动 `Stop-Process` 了残余 pip 进程（torch 已完整安装，import 自检通过）。
3. 大 wheel（3.2 GiB）优先用 `curl -C -` 断点续传，**下载与依赖安装解耦**，避免 pip 把两者耦合在一个不可观测的长事务里。
4. `curl -o` 时**必须保留完整 wheel 文件名**（含 `cp311-cp311-win_amd64`）；本次一度把文件截断命名为 `torch-2.8.0+cu128-cp311.whl`，导致 `pip install <文件名>` 报 `ERROR: ... is not a valid wheel filename`。
5. 本机 PowerShell 5.1 **禁止执行 .ps1 脚本**（ExecutionPolicy），后台任务需把脚本内容内联为 `pwsh -Command`。
6. conda base 上创建的 venv，其 `Scripts\python.exe` 会再拉起一个 `D:\RCAIDE\envs\RCAIDE\python.exe -m pip ...` 子进程执行实际工作（`sys.prefix` 仍为 venv，site-packages 隔离有效）——用 `Get-CimInstance Win32_Process` 排查时不要误判为“写到了原环境”。

## 5. RCAIDE 原环境完整性证据（未改动）

| 检查项 | 安装前 | 安装后 | 结论 |
| --- | --- | --- | --- |
| `torch.__version__` | 2.8.0+cpu | 2.8.0+cpu | 未变 |
| `torch.cuda.is_available()` | False | False | 未变 |
| `site-packages/torch/__init__.py` SHA256 | `6d6c92d0b1091fc8f437cfe8228e9c9ad088dc0faf8446b1df8738f61c0834f2` | 同左 | 未变 |
| `site-packages/torch/version.py` SHA256 | `6dbefff887dc70206b024758537044eb02242892e1ed1d839dd6e4bd884a44c1` | 同左 | 未变 |
| `pip freeze` 文本 | `rcAIDE_pip_freeze_before_gpu_install.txt` | `rcAIDE_pip_freeze_after_gpu_install.txt` | **逐行 diff 为空**（PowerShell `Compare-Object` 无输出）；两文件字节级 SHA256 不同仅因写文件时的编码差异（`*>` 原生重定向 vs `Out-File -Encoding utf8`），内容一致 |

`pip freeze` 文件：`D:\RCAIDE\dnext001\gpu-env-logs\rcAIDE_pip_freeze_before_gpu_install.txt`（SHA256 `BC5AD5D59F1F31FDF88C6A0273316544A73E8CD060DBB5B4A16E7F352AE08A4C`）与安装后同名文件；**内容 diff 为空**。

## 6. FP32 / FP64 前向与反向核对（真实 GPU 执行）

方法（`research/concorde_metaopt/gpu/env_check.py`）：固定种子 20261110，随机 `x(512×256)`、`w(256×256)`，计算 `loss = sum((x@w)²)` 并反传；同一数据在 CPU float64 上做参考，比较最大绝对/相对误差，并检查梯度是否有限且非零。FP32 的 GPU 结果**仍然是 GPU 上执行**（`executed_on_device = cuda:0`），其误差是相对 float64 参考而言的舍入误差，不是 CPU 回退。

| 设备/精度 | 前向最大绝对误差 | 前向相对误差 | grad_w 最大绝对误差 | grad_w 相对误差 | grad_x 相对误差 | 梯度有限/非零 | 实际执行设备 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CPU / float64 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 是 / 是 | cpu |
| CPU / float32 | 1.35e-06 | 3.81e-07 | 8.59e-05 | 3.02e-07 | 2.70e-07 | 是 / 是 | cpu |
| **CUDA / float64** | **0.0** | **0.0** | **0.0** | **0.0** | **0.0** | 是 / 是 | **cuda:0** |
| **CUDA / float32** | **1.11e-06** | **3.14e-07** | **8.95e-05** | **3.15e-07** | **2.35e-07** | 是 / 是 | **cuda:0** |

结论：
- **FP64 路径在 GPU 上真实可用**（不是 fallback 到 CPU）：与 CPU float64 逐元素完全一致，说明这一路是真正的双精度执行；
- FP32 的误差量级（≈3e-7 相对）与 float32 机器精度一致，且梯度非零、无 NaN/Inf；
- 因此 G1 中的 GPU-FP32 与 GPU-FP64 都是有效的数值路径，两者之间的差异只应解释为**精度 vs 吞吐**的取舍。

## 7. 确定性与数值异常

| 设备/精度 | 重复次数 | 梯度重复间最大差 | 是否逐位相同 | cudnn.benchmark / deterministic |
| --- | --- | --- | --- | --- |
| CPU / float64 | 3 | 0.0 | 是 | False / False |
| CPU / float32 | 3 | 0.0 | 是 | False / False |
| CUDA / float64 | 3 | 0.0 | 是 | False / False |
| CUDA / float32 | 3 | 0.0 | 是 | False / False |

- 本环境**未开启** `cudnn.benchmark`，也未设 `deterministic=True`；在“同种子、同形状、同 stream”的短程重复下已逐位一致。**注意**：这不等于对任意 kernel 组合的全局确定性承诺——若后续把 GPU 后端口径化，建议显式设 `torch.use_deterministic_algorithms(True)` 并单独复测。
- 全程 NaN/Inf 计数为 0。

## 8. 峰值显存与吞吐探针

2048×2048 方阵 GEMM，每配置预热 2 次 + 计时 10 次（CUDA 计时前后 `torch.cuda.synchronize()`）：

| 设备/精度 | 墙钟 | 实测吞吐 | 峰值已分配显存 | 峰值保留显存 |
| --- | --- | --- | --- | --- |
| CPU / float64 | 0.311 s | **553.0 GFLOPS** | — | — |
| CPU / float32 | 0.140 s | **1225.6 GFLOPS** | — | — |
| CUDA / float64 | 0.636 s | **269.9 GFLOPS** | 144.2 MB | 174.0 MB |
| CUDA / float32 | 0.0146 s | **11 799.2 GFLOPS（≈11.8 TFLOPS）** | 80.2 MB | 174.0 MB |

**如实结论**：

- RTX 5060 的 **FP32 吞吐约 11.8 TFLOPS**（本机 CPU-FP32 1.23 TFLOPS 的 9.6 倍）；
- RTX 5060 的 **FP64 吞吐约 0.27 TFLOPS**，仅为自身 FP32 的 **1/44**，且**低于**本机 9950X 的 CPU-FP64（0.55 TFLOPS，即 GPU-FP64 = 0.49× CPU-FP64）；
- 这与消费级 Blackwell 的 FP64:FP32 硬件配比一致，**属于预期行为，不是配置错误**；
- **不得**把“装了 CUDA”当成算法收益，也**不得**宣称 FP64 场景存在 GPU 加速。G1 的预期假设据此修正为：GPU 只在 FP32 路线上可能有训练/批量打分收益，FP64 路线 GPU 更慢属于**正常负结果**。

## 9. CUDA 可用性结论与回退策略

- **结论：CUDA 可用（AVAILABLE），G1 三路对比已按计划执行，不需要 NOT_RUN 降级。**
- 回退策略（若未来驱动/显卡变化导致 CUDA 不可用）：
  1. 只用 CPU-FP64 跑 G1（默认守门口径），CUDA-FP64 / CUDA-FP32 行标记 `NOT_RUN`，**不得**用 CPU 结果顶替 GPU 行；
  2. 不改 `D:\RCAIDE\envs\RCAIDE`，不重装/降级任何已有包；
  3. GPU 后端仅作为**可选加速器**：主训练进程最多 1 个（单卡 8 GB，禁并发占卡），不参与任何结论性统计检验；
  4. 合并与否由 G2/G3 的实测吞吐 + 精度门禁 + A5 复核决定，不由本报告决定。

## 10. 限制与“未证实”声明（必须随引用一起传播）

1. **RTX 5060 FP64 吞吐属本机单次探针结果（2048³ GEMM×10 次），不是厂商规格**；未做 cuBLAS 版本差异、不同矩阵形状、多 stream 的交叉验证。
2. 本机驱动 610.88 + CUDA UMD 13.3 属较新组合，与官方 CUDA 12.8 toolkit 的兼容性只经上述 import/计算实测，未做完整 suite 验证。
3. 单卡 8 GB、PCIe Gen5 ×8；**未测**多卡、MIG、ECC、显存带宽饱和工况。
4. 所有计时均受同机其它 agent 并发负载影响（同一时段存在 pytest 全量测试、warm_start 实验进程），故为**上限估计**；GPU 占用率不是科研指标，本报告不使用。
5. 本报告**不**声称任何算法收益；GPU 安装与 FOMAML 算法效果无关。

## 11. 复现命令

```powershell
# 环境自检（生成 JSON 证据）
& D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m research.concorde_metaopt.gpu.env_check ^
    --out research/concorde_metaopt/gpu/reports/g0_env_check.json
# 单元测试（用 RCAIDE 解释器的 pytest，不依赖 venv）
& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_gpu_benchmark.py -q
```

## 附录：证据文件

| 文件 | 内容 |
| --- | --- |
| `research/concorde_metaopt/gpu/reports/g0_env_check.json` | 本报告 §1/§6/§7/§8 全部原始数值（设备信息、前向/反向误差、确定性、GEMM 探针、峰值显存） |
| `D:\RCAIDE\dnext001\gpu-env-logs\gpu_env_pip_freeze.txt` | venv 环境指纹（SHA256 `CC9B1BD0…B720F`） |
| `D:\RCAIDE\dnext001\gpu-env-logs\rcAIDE_pip_freeze_{before,after}_gpu_install.txt` | 原环境安装前后 freeze 快照（内容零差异） |
| `D:\RCAIDE\dnext001\gpu-env-logs\pip-torch-cu128.log`、`pip2.log`、`pip2.status`、`g0.status` | 失败尝试 A/B/C 的原始日志 |
| `D:\RCAIDE\dnext001\gpu-env-logs\curl_download.log`、`torch_install2.log` | 成功路径 D 的下载与安装日志 |
