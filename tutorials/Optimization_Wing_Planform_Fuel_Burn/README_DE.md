# 差分进化优化教程（本地修订，2026-10-26）

入口为 `D:\RCAIDE\tutorials\Optimization_Wing_Planform_Fuel_Burn\Optimize.py`。
优化器采用本目录 `Differential_Evolution.py`，不调用安装包中存在约束回调问题的 DE 分支。

## 在 VS Code 中运行

选择解释器 `D:\RCAIDE\envs\RCAIDE\python.exe`，打开 `Optimize.py` 后使用“在终端中运行 Python 文件”。也可在 PowerShell 中执行：

```powershell
Set-Location -LiteralPath 'D:\RCAIDE\tutorials\Optimization_Wing_Planform_Fuel_Burn'
& 'D:\RCAIDE\envs\RCAIDE\python.exe' -B -E -s '.\Optimize.py'
```

每次启动会打印独立输出目录 `runs\DE_日期_时间\`，其中保存配置、评价历史和最终结果，不覆盖教程根目录的旧 SLSQP 结果。默认关闭设计空间扫描和前置图窗。

## 调整算法

在 `Optimize.py` 的 `DE_OPTIONS` 中修改：

```python
DE_OPTIONS = dict(
    max_generations=50,       # 最大进化代数，不是 Mission 评价次数
    population_multiplier=8,# 3 个自由变量对应 24 个个体
    tolerance=0.001,         # 种群目标值离散程度的停止容差
    seed=42,                # 随机数种子
    display=True,           # 每次评价及每代打印进度
    parallel_workers=24,    # 并行进程上限，实际数量按内存自动缩减
    blas_threads=2,         # 每个进程的 BLAS 数值计算线程上限
    cpu_limit_percent=60,   # 整个优化进程组的 CPU 上限，百分比
)
```

仍直接运行 `Optimize.py`；并行实现已合入原来的 `Differential_Evolution.py`，无需独立的 Parallel 入口。采用 `best1bin`、拉丁超立方初始化，并将名义初值放入种群。关闭额外的局部精修 `polish`。当前预算最多约 `(50+1)×24+1=1225` 次性能评价（含初始种群及最多一次最终状态同步），缓存可减少重复评价。增加 `parallel_workers` 不增加种群或评价预算。

### CPU 与内存控制

- `cpu_limit_percent=60` 在 Windows 下通过 Job Object 将主进程及其后代进程的合计 CPU 用量限制在系统总处理能力的约 60% 上限。它不是每个子进程各占 60%；其他应用的 CPU 用量不属于此限制。实际占用会随任务阶段、内存和并行余量低于该上限，不能保证始终维持 60%。设为 `None` 可取消此 CPU 上限。
- `parallel_workers=24` 是最大候选并行数，不是必定启动 24 个进程。首先在一个工作进程评价名义初值；该点随后由缓存复用，不额外增加一个任务。根据实测工作进程峰值内存、系统可用物理内存及提交额度，预留 2 GiB 和 25% 峰值余量后确定并行数。若运行中可用内存/提交额度不足 1 GiB，会减少新任务的并发提交，不会终止正在计算的任务。这是基于已观测峰值的预防措施，不能保证所有未来候选的峰值完全相同。
- `blas_threads=2` 防止每个工作进程又开启大量 OpenBLAS 线程；每个进程单独持有 Nexus、飞机及 Mission，避免共享可变任务状态。
- 初始一个候选评价期间 CPU 较低属于预热阶段。随后终端打印 `parallel workers=实际数/上限` 和 `CPU cap=60.0%`，再进入批量计算。
- 若内存允许的进程数量不足，CPU 可能达不到 60%。此时应以运行目录的 `parallel_runtime.json` 中的实际进程数和内存计划为准，不建议只为提高 CPU 占用盲目增加进程。

并行时通过 SciPy 的 `vectorized=True` 批量接口将完整的目标/约束计算分派到进程池；SciPy 的 `workers=1` 是内部映射器设置，不代表教程只用一个进程。单改 SciPy 的 `workers=-1` 无法并行本教程最耗时的非线性约束评价。

并行采用 `updating='deferred'`，整代计算完成后更新种群；原串行版采用 `immediate`。同样种子下，串行与并行轨迹可能不同。设 `parallel_workers=1` 可使用原串行更新路径，仍应用 BLAS 线程与 CPU 上限。

每个工作进程在本次运行目录 `workers\worker_PID` 保存独立日志、历史及资源配置，主进程单独写统一历史，避免同时覆盖结果文件。`parallel_runtime.json` 记录实际并行数、CPU 上限、内存计划及已观测的子进程资源用量。完成后主进程同步求解器返回设计并比较主进程/工作进程指标；不一致会明确报错，不能宣称数值验证成功。

终端会打印每代 `generation`、候选评价数 `candidates`、缩放目标 `best` 和缩放约束违反量 `maxcv`。没有可行个体时 `best` 可显示为 `inf`。最终结果必须结合 `solver.success`、`solver.message` 和 `constraint_feasible` 判断；达到代数上限也会保存返回候选点，不能自动称为最优解。

## 任务修正

- `range_residual = 目标航程 - 实际航程` 改为 `<= 0`，要求至少达到 1500 nmi。残差单位为米，以 1500 nmi 作数值缩放。
- 巡航高度同时绑定爬升第三段终点、巡航高度和下降第一段起点。
- 巡航高度下限由 6 km 收紧为 **8.1 km**，避免第三爬升段从 8 km 向下爬升或出现零时长。
- 下降第二段修正速度字段为 `air_speed_end=170 m/s`，并采用 **6→5 km**、220→170 m/s 的减速下降；下一段继续 **5→4 km**。这是本地任务剖面的明确修订，不是上游原始定义。

结果中分别保存声明单位和 SI 单位的返回设计、求解状态、实际代数、Mission 评价数及逐代进展。历史每条评价包含设计输入，便于追溯。返回设计会在保存前重新同步到 Nexus；求解器返回点与最后评价点不再混淆。

接口修复及并行修改用真实 SciPy、真实 Nexus 的解析任务和任务构造检查验证；Windows 的子进程 CPU 限制继承也已检查。并行修改后没有启动新的飞机 Mission，真实加速比及工程可行性仍需后续实际运行验证。`Run_Optimize_Quick.py` 是旧的独立 SLSQP 入口；运行差分进化请使用 `Optimize.py`。
