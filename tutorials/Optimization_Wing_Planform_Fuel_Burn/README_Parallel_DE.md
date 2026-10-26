> 2026-10-26 当前入口说明：以下保留早期并行方案的历史记录。当前工作区没有 `Optimize_Parallel.py`，请运行 `Optimize.py`；它通过 `Differential_Evolution.py` 使用当前并行实现。以脚本中的 `DE_OPTIONS` 和根 README 为准。

# 并行差分进化入口

在 VS Code 打开同目录的 `Optimize_Parallel.py`，使用
`D:\RCAIDE\envs\RCAIDE\python.exe` 运行。它会启动一次全新的优化。
已有的 `Optimize.py` 运行无法原地切换；本次准备工作没有停止或重启它。

默认在 `Optimize_Parallel.py` 顶部设置：

```python
PARALLEL_OPTIONS = dict(parallel_workers=4, blas_threads=2)
```

- `parallel_workers`：同时计算候选设计的独立进程数，初次使用建议 4。
- `blas_threads`：每个进程的 BLAS 数值计算线程上限，默认 2。
- 代数、种群乘数、容差、种子仍读取 `Optimize.py` 的 `DE_OPTIONS`。
  当前配置为 50 代、乘数 8，三个变量对应 24 个个体。
  增大种群乘数会增加计算量，不会增加并行进程数。

也可以在 PowerShell 指定进程数：

```powershell
& 'D:\RCAIDE\envs\RCAIDE\python.exe' -E -s 'D:\RCAIDE\tutorials\Optimization_Wing_Planform_Fuel_Burn\Optimize_Parallel.py' --workers 4 --blas-threads 2
```

每个进程构造自己的 Nexus、飞机与 Mission；完整的目标/约束评价在进程内执行。
SciPy 的 `workers` 只分派目标函数，当前教程最耗时的任务也发生在非线性约束
计算中，因此仅改 `workers=-1` 不能解决这个瓶颈。新适配器通过批量约束接口
分派完整评价，SciPy 自身仍为 `workers=1`，由独立进程池负责并行。

并行采用 `updating='deferred'`：整代评价完成后再更新最优个体。
当前串行版为 `immediate`；因此即使种子相同，两者的搜索轨迹也可能不同。
不能把一次运行的结果差异完全归因于并行提速。

每次运行在 `runs\DE_parallel_时间戳` 保存配置、统一评价历史和最终结果。
`workers\worker_PID` 下各自保存任务历史与 `console.log`。
统一历史的 `iteration` 是完成的性能评价序号，不是 DE 代数；结束前还会在
主进程同步求解器返回设计，以输出完整航段结果，并比较主进程与工作进程指标。
进程报错或最终指标不一致会明确抛错，不宣称优化成功。

已验证 Windows spawn、真实 SciPy DE、真实 Nexus 的解析测试任务：6 项通过；
覆盖约束方向及单位、两个工作进程实际参与、缓存、空种群、评价计数、最终状态、
保存结果、跨进程错误传播及随机种子复现。未执行新的飞机 Mission。
真实飞机并行运行的数值一致性与实际加速比需在下一次启动后观察。
不能保证四进程恰好获得四倍速度，也无需以 CPU 达到 100% 为目标。

验证材料：`D:\CodexMemory\RCAIDE\parallel-de-20261026`。
