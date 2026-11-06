# 待纳入下一个 GitHub Issue 的并行任务草案：路线 A 的 PyTorch/CUDA GPU 加速可行性验证

> **状态：DRAFT / PENDING_NEXT_ISSUE；尚未发布新 Issue、尚未向工作机授权执行，也不代表已完成任何 GPU 训练。**  
> 创建日期：2026-11-06。  
> 用途：待负责人下一次明确要求发布新任务 Issue 时，将本草案完整整理为该 Issue 中的**并行工作包（GPU-TEST）**，与主线算法开发/数值验证分别记账、分别审查。发布前须核对当时 GitHub HEAD、S1 运行状态与新的实验冻结门禁。
>
> **当前有效工作线**：[路线 A Issue #7](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/7)；[S1 开发分支](https://github.com/QingYangJin/RCAIDE_Supersonic/tree/research/p4-route-a-s1)。本草案只保存在独立**规划分支**，不进入 S1 工作分支，不触动已冻结的正式 holdout、代码哈希、旧 M2/M5/M6 结果或正在审阅的 S1。
>
> **未来 Issue 可直接复制的工作包标识**：§GPU-TEST-01｜RTX 5060 上路线 A 元学习 PyTorch CUDA 加速与 CPU/GPU 对照§。

## 一、提出背景（已核实的工作机事实）

- 工作机 CPU：AMD Ryzen 9 9950X，16个物理核心、32个逻辑处理器；内存约32GB。任务管理器显示有约15个 Python CPU 工作进程，单个持续占总CPU约3.1%，总CPU约51%–54%。不能据此断言每个进程都在神经网络元训练，须用PID/命令行及运行日志确认。
- GPU：NVIDIA GeForce RTX 5060，显存8151MiB（约8GB）；§nvidia-smi§：驱动610.88、驱动可支持 CUDA 13.3（**不代表 PyTorch CUDA 运行时已安装**），取样时 GPU-Util 4%、占显存约1232MiB，主要为桌面/应用程序。系统为 Windows WDDM。
- 项目 Python：§D:\RCAIDE\envs\RCAIDE\python.exe§；已实际执行检测：§torch.__version__ = 2.8.0+cpu§、§torch.version.cuda = None§、§torch.cuda.is_available() = False§。直接在 PowerShell 运行§python§还曾报 §ModuleNotFoundError: No module named 'torch'§，表明 Python 环境不同，不能据此评价项目环境。
- 截至起草时，§research/concorde_metaopt/meta_learning/maml.py§ 主实现使用 §torch.float64§、CPU Tensor、NumPy/torch参数往返、§create_graph=False§的一阶MAML；修改为 CUDA 需要显式设备策略、减少传输及一致性校验，**仅安装 CUDA 版PyTorch不会自动使旧代码跑到GPU**。
- 现有 S1 计划为21,000组约1,920,000次**合成**函数评价、15分片并行，工作机近期证据为§S1_RUN=NOT_APPROVED§（新 Issue 发布时应重新查核）。大规模 S1 BO/GP 搜索主要为 CPU 型负载；神经网络在 GPU 上加速不保证使全流程等比例加速。
- §float64§元梯度与有限差分正确性基线必须保留。GeForce RTX 5060 的 FP64 吞吐可能有限，不能预设 GPU FP64 比 Ryzen9950X CPU 快；§float32§性能可能更好，但精度差异必须单独审查。

## 二、未来并行任务的目标与明确边界

目标：**用实际可复核的工作机测量**，判断路线 A 的 FOMAML（以及在 S2 已开发后可选的 Full MAML）哪些环节适合 GPU，是否存在端到端速度收益，并确保训练、代理预测和科学结论可靠。

- 任务形态：并行**软件/环境/性能验证**，不是新算法获胜实验，不以GPU占用率为目标函数。
- **禁止**：修改/卸载当前项目§RCAIDE§ CPU PyTorch 环境；替换已归档M2/M5/M6或已冻结S1计算的设备/精度；未获授权提前读取S1确认性 holdout；改变正式实验中的真实合成函数评价预算B=64/128、任务划分或主终点；在此任务里启动任何 VSPAERO/SU2/RCAIDE Mission/WaveDrag/真实航空优化。
- 未来执行时使用**独立虚拟环境+独立 worktree/branch+独立 run_id**；§physical_call_count=0§、§data_origin=SYNTHETIC_TEST§，只使用合成训练/验证任务进行调试与基准。
- 不允许以“换浮点精度/GPU硬件”带来的结果变化称为算法精度或优化性能提升。若最终优化任务验证需要GPU与CPU方法学对照，必须在新预注册下另外设计，不能回写旧run。

## 三、GPU-TEST 分阶段实施

### G0｜设备及环境核对（零代码与算法变更）

1. 核对§nvidia-smi§完整设备型号、驱动、空闲显存、Windows WDDM；执行 §D:\RCAIDE\envs\RCAIDE\python.exe§ 的版本探测并保存原CPU环境 §pip freeze§/解释器路径/CPU数值基线 SHA。
2. 创建**全新** GPU 测试环境（建议§D:\RCAIDE\envs\RCAIDE_GPU_TEST§，若已存在则不得覆盖）；仅从官方 PyTorch 安装源选择**明确支持 RTX5060/Blackwell 的 CUDA 构建**并核对 Python 3.11/Windows 兼容性。不可依据§nvidia-smi CUDA Version§推断必须安装同版本运行时；不在该草案阶段预设固定wheel一定可用。
3. 最低冒烟：§torch.cuda.is_available()§、设备名称和compute capability、CUDA Float32与Float64矩阵计算的**实际前向/反向传播**、§torch.cuda.synchronize()§、异常/非有限检查。识别显存不足、§no kernel image§及驱动兼容问题；失败时只生成诊断并保持CPU基线。
4. 产物：中文§gpu_environment_report.md§、§environment_cpu.json§、§environment_gpu.json§、§cuda_smoke_results.json§、§pip_freeze_*.txt§。不得安装软件到正式CPU项目环境。

### G1｜现有 FOMAML 计算路径与训练成本剖析

1. 对已有 §maml.py / adaptation.py / m5_arms.py / s1_runner.py§ 记录内循环、外循环、支持集编码、候选打分、CPU GP/BO、数据输出的计时，测出**训练阶段与整体优化阶段占比**。
2. 在独立GPU测试分支新增可选设备后端，至少支持 §device=cpu|cuda§，禁止修改既有CPU默认数值输出；PyTorch模型参数及支持/查询张量放在同一设备，训练期间尽量不做逐task §.cpu().numpy()§传输，最终仅在明确边界转回CPU存档。控制GPU工作进程数，避免15个S1 CPU分片各自创建GPU上下文。
3. 进行 CPU-FP64（参考）/GPU-FP64（同精度实现核对）/GPU-FP32（探索性加速）的三路基准。相同网络、优化更新数、训练/验证task、seed与K，分别记录CUDA warm-up、训练净时间、端到端时间、峰值RAM/显存、梯度范数、支持/查询RMSE、NaN/Inf与数据传输成本。GPU计时前后强制同步；报告重复运行分布而非仅单次最快值。
4. 先比较单模型/单进程与合理的episode batch，不把大量小task随意拆成多GPU进程；CPU BO并行数不因GPU试验而私自改变正式S1调度。
5. 若GPU-FP64性能不佳，保留负结果；若GPU-FP32较快，需对损失、元梯度及预测指标进行预先规定的容差审查，**不宣称与FP64逐bit一致**。

### G2｜Full MAML 后续可选GPU基准（须等S2源码和独立审查通过）

- 在完整二阶MAML已实现并由A5验证**原始θ扰动、每次重新执行内循环**的有限差分元梯度后，才可将其CPU/GPU实现纳入正式性能基准。
- 不允许为了GPU迁移而用§.data§、§detach§断开二阶计算图；记录较长内循环的显存峰值、显存不足与速度。
- 不保证Float32二阶梯度能通过Float64的有限差分误差阈值，阈值应在meta_validation上独立校准并报告精度权衡。

### G3｜确定是否合入后续算法代码（需要A5通过）

- 输出工作机实测的**训练吞吐提升倍数、整体任务耗时降低比例、GPU显存/RAM成本和误差影响**。区分“GPU训练快”与“21,000次CPU BO总流程快”；如果训练只占小比例，需用端到端Amdahl上界解释效果。
- 当新GPU后端稳定、性能证据充分且A5核对通过，提交独立PR供负责人决策；否则保留CPU默认实现及负结论。**不自动改写S1确认性实验配置，也不自动改变B或K、任务数或seed。**

## 四、建议测试矩阵与验收条件

| 分组 | 设备/精度 | 测试对象 | 科学口径 |
|---|---|---|---|
| CPU 基线 | CPU / float64 | 现有FOMAML训练、K-shot、候选评分 | 冻结参考，不修改 |
| GPU 同精度 | RTX5060 / float64 | 同架构、同数据、同seed | 检查数值一致性和真实性能 |
| GPU 探索精度 | RTX5060 / float32 | 同架构、同数据、同seed | 需声明精度变化，单列性能与误差 |
| 可选后续 | RTX5060 / float32/64 | 已通过S2审查的Full MAML | 仅在二阶正确性证明后执行 |

通过门禁：

- G0：独立环境CUDA真实forward/backward完成或给出可复核的不支持原因；旧CPU环境哈希/依赖未变。
- G1：设备调度可切换；CPU旧路径回归PASS；目标任务/支持query隔离PASS；FP64 CPU/GPU在经过独立规定的浮点容差内核对；性能指标覆盖训练、适应与全流程，不得只汇报GPU-Util。
- G2（条件）：二阶原始参数元梯度有限差分与A5独立审查PASS；真实显存与时间记录。
- G3：A3检查分支和旧run不变性，A5检查梯度正确性、数值精度、无物理调用、性能测量公平性；Lead只在审查通过后形成下一步代码并入建议。

实验可使用**例如3次以上独立重复**与warm-up，并保存原始CSV、每个benchmark的§run_id/seed/git_sha/torch_cuda/driver/device/dtype§；最终报告中文，至少形成“CPU vs GPU训练时间”“FP32/FP64误差/梯度差异”“峰值RAM与VRAM”“训练与BO时间组成/端到端收益”4类可重绘图表。若结果为GPU更慢或数值不符合容差，也必须报告。

## 五、工作机团队分工建议（待下次 Issue 发布时真正下发）

- **Lead**：选择测试环境与并行调度窗口；落实“只并行基准，不改正式S1”；负责唯一GitHub回执和预算。
- **A1**：独立可选CUDA训练后端、CPU兼容性、张量设备/数据传输改造。
- **A2**：可重复三路性能基准、耗时拆分、吞吐和显存记录、中文图表。
- **A3**：GPU测试环境与现有CPU环境/冻结run/PR隔离；提交SHA和环境清单。
- **A4**：与下次新Issue主线任务并行的依赖、验收、科学口径矩阵；中文文档。
- **A5**：独立验证GPU计算、精度/梯度一致性、预算隔离和不夸大性能结论。

## 六、下一次 Issue 发布时的操作约定

1. 当负责人明确要求**创建下一次新Issue**时，从本文件抽取 §GPU-TEST-01§ 作为一项**并行工作包**，与该Issue主线算法改进任务独立里程碑、独立状态/回执；附上此文件永久URL或将内容复制到正文。
2. 在正式发布前重新查询当时GitHub分支、已完成的S1/S2、CUDA环境和工作机资源，若S1已有正式实验则不能变更历史；更新时间、依赖和环境版本再下发。
3. 该任务只授权未来的**离线环境/性能测试**；真实气动与其他物理求解的预算仍由Issue #4单独审批。RCAIDE气动回退继续暂停，VSPAERO整改并行不受本GPU测试影响。
4. **现在不是新Issue、也不是立即执行命令**：此草案仅保存待下一次负责人指令；当前所有已经冻结的科学运行、GitHub Issue #7 和 PR#6的既有审批状态不变。

**拟发布时的简明任务句**：并行开展RTX5060上的PyTorch CUDA可用性、FOMAML训练与K-shot适应的CPU/GPU Float64/Float32对照（Full MAML待S2审查后选做）；不得修改当前CPU环境及已冻结的S1实验；以真实耗时、显存、梯度和RMSE数据决定是否有加速价值。
