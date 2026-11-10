# D-NEXT-001 A5 独立复核协议：路线 A / B / GPU（独立重放、公平性、精度、边界）

- 出具人：A5（独立复核；不实现 WarmStartSampler / 元采集策略 / 评价器，不改 A1–A4 工作树）
- 适用对象：A1 真实评价器闭环、A2 路线 A 跨 BO/DE/PSO 热启动、A3 路线 B 元采集、A4 GPU 并行基准
- 当前状态：四线产物均未产生（各工作树 HEAD=ea8ad97，无 receipt），故本协议为"前置复核协议 v1"，待产物交付后按 §6 执行并出具名结论
- physical_call_count=0；本协议所有重放均为 mock / 合成 / 归档 replay 只读

## 1. 独立重放的最小定义

A5 的"独立重放"必须同时满足：
1. 不同 worktree：A5 在 D:\RCAIDE\dnext001\wt-a5 内运行自己的只读脚本；被审代码以只读方式引用（git -C <被审树> show <sha>:<path> 或只读拷贝到临时目录），不得写被审树。
2. 不同进程：每次重放用全新进程；不得复用被审执行人的常驻进程、缓存、临时产物。
3. 不共享可变状态：清空/隔离 PYTHONPYCACHEPREFIX、TMP、torch cache；重放前后对比被审树 git status 与冻结目录 sha。
4. 输入固定：design_space / task 集 / 评价器 mock 的 sha 必须固定并在 receipt 中列出；输入发生变化即视为不同实验，不得与旧结果比较。
5. 结论只认"命令 + 输出 + 输入 sha"，不认提交消息、截图、执行人自述。

## 2. 随机种子与确定性校验

- 种子登记：每个 run 必须记录 seed、numpy/torch 全局种子、以及是否使用 SHA-256 派生种子（derived seed = sha256(base_seed, task_id, arm) 之类），派生规则须入仓。
- 同种子可复现：同一 seed 在两个全新进程各跑一次，比较排除计时字段后的 core sha（口径参考 S3: wall_s / peak_memory_mb / record_digest 三字段排除）；不一致 => FAIL。
- 不同种子必须不同：换 seed 后结果必须变化（若逐位相同，说明种子未生效或代码忽略 seed）=> FAIL。
- 无隐式随机：静态扫描 random./np.random./torch.rand 无 seed 参数、未传 generator 的调用；存在且未在 run_config 声明 => CHANGES_REQUESTED。
- 竞态与并行：GPU/多进程并行下必须固定线程数与算法（见 §4），否则同种子不可复现 => FAIL。
- 允许的排除字段仅限计时与资源统计（wall_s、peak_memory_mb、record_digest）；把结果相关字段加入排除集 => FAIL。

## 3. 公平性检查项（A/B 方法比较）

| 编号 | 检查 | 判据 |
| --- | --- | --- |
| F-1 同预算 | 每个 arm 的 B 相同；DE 的初始 Np 真实评价必须计入 B；BO 的初始点评价计入 B；不得用"额外免费评价" | B 不等或初始评价不计入 => FAIL |
| F-2 同初始化 | 初始设计集必须逐元素相同（同 sha），或按预注册规则显式不同并登记 | 未登记差异 => FAIL |
| F-3 同评价器 | evaluator_id、fidelity、solver_version、physical_validation_status 必须一致；mock 必须同版本 | 不一致 => FAIL |
| F-4 同 K / 同内循环 | 元学习 K-shot、inner_steps、inner_lr 必须一致或按预注册网格 | 未预注册的自由调参 => FAIL |
| F-5 同停止条件 | 预算停止或墙钟停止二选一且全 arm 一致；不得对有利 arm 放宽 | 停止条件不同 => FAIL |
| F-6 代理标签不泄漏 | 训练特征/目标不得含 arm_id、method one-hot、未来信息；用"标签置换检验"：打乱 arm 标签后性能不应系统性保持 => 若明显保持则泄漏 |
| F-7 训练/测试任务隔离 | meta-train / meta-val / meta-test 任务 id 无交集；test 任务不得参与任何选择、early stop 或超参调整 | 交集非空 => FAIL |
| F-8 并列与错位 | 同分处理规则预注册且全 arm 相同；随机 tie-break 用登记种子 | 未预注册 => CHANGES_REQUESTED |
| F-9 成本口径 | 预算成本与计算成本分开记录（见 S3 的 G4 教训）；效率结论必须用计算成本而非预算比 | 用 budget 冒充 wall time => FAIL |

## 4. GPU 精度与二阶梯度门禁（A4）

### 4.1 环境固定
- 关闭 TF32：torch.backends.cuda.matmul.allow_tf32=False、torch.backends.cudnn.allow_tf32=False。
- 确定性：torch.use_deterministic_algorithms(True)、cudnn.benchmark=False、cudnn.deterministic=True。
- 线程：OMP_NUM_THREADS=1、PYTHONHASHSEED=0、CUBLAS_WORKSPACE_CONFIG=:4096:8。
- 记录 GPU 型号、驱动、torch/CUDA 版本；RTX 5060 8GB 下 batch 必须使显存峰值 < 7 GB 并记录。

### 4.2 数值容差（FP32 vs float64 CPU 参考）
| 量 | 容差 | 失败处理 |
| --- | --- | --- |
| 前向 loss | rtol 1e-5，atol 1e-6 | 超差 => NOT_VALIDATED，查 TF32/归约顺序 |
| 一阶梯度 | rtol 1e-3，atol 1e-6 | 超差 => FAIL（实现/归约错误） |
| 二阶量（HVP / meta-gradient 中的二阶项） | GPU FP32 对 CPU float64 参考 rtol 1e-2（首轮筛查）、1e-3（最终签署） | 超差 => CHANGES_REQUESTED/FAIL |
| 同后端重复性 | core sha 逐位一致（排除计时） | 不一致 => FAIL |

### 4.3 二阶梯度门禁（Full MAML 与 FOMAML 必须可区分）
- 必须证明二阶项真实存在：Full MAML 的 meta-gradient 与 FOMAML 在数值上不同（差值相对量 > 1e-6），且 Full MAML 方向可由 HVP 有限差分独立验证（eps 取 1e-3 与 5e-4 两次，收敛阶检查）。
- 若 Full MAML 与 FOMAML 输出逐位相同、或二阶项恒为 0 => 判 FAIL（说明二阶图被 detach/未建图）。
- 梯度门禁不通过时，允许报告"梯度数值未验证"，但不得给出"Full MAML 优于 FOMAML"类结论。
- 本轮 GPU-TEST 的 G2（Full MAML 二阶门禁）必须由 A5 独立复核后才能进入 G3 合并；A5 未复核 => G3 NOT_ISSUED。

## 5. 后端 ≠ 方法（边界检查）

- 后端（CPU/GPU、torch/numpy）与训练方法（FOMAML/ANIL/MAML、BO/DE/PSO）是两个正交维度；报告中不得出现"GPU MAML 是新的训练方法"这类表述。
- 任何"后端带来提升"的结论必须排除算法差异：同算法、同种子、同预算下 CPU vs GPU 的差异只能归因于数值精度/归约顺序，且必须落在 §4.2 容差内。
- 方法标签只能来自算法实现；后端、设备、并行度写入 backend 字段。
- 跨后端比较必须给出 parity 测试（相同输入、CPU vs GPU 前向/一阶梯度在 §4.2 容差内）；parity 不通过则禁止做性能对比结论。

## 6. 复核执行步骤（产物交付后）

1. 读取被审 receipt 与 run_config，核对 git_sha/code_sha 与工作树 HEAD 一致。
2. 用 A5 只读脚本做产物存在性、physical_call_count、字段完整性检查（脚本 A5-C12；后续扩展为 A5-C13…）。
3. 独立重放：按 §2 同种子双进程；按 §3 逐项公平性断言；按 §4 精度门禁；按 §5 边界检查。
4. 输出 verdict：VALID（复现通过）/ NOT_VALIDATED（证据不足或超差未定位）/ NOT_RUN（未执行）/ FAIL（断言被证伪）。
5. verdict 必须落到 docs/reviews/ 下具名文件，含命令、输入 sha、输出摘要、physical_call_count。

## 7. 复核 receipt 最小字段

run_id, reviewer, audited_commit, audited_files[path+sha256], replay_commands[], inputs[path+sha256], seeds[], budget_B, K, evaluator_id, physical_call_count=0, tolerance_results{}, fairness_checks{}, backend_fields{}, verdict, limitations[].

## 8. 当前结论与限制

- A1–A4 产物均不存在 => 本协议各条状态 NOT_RUN；不构成对任何实现的 PASS。
- 本协议不改变 S3 结论（NO_EVIDENCE / NOT_ISSUED / S4 NOT_APPROVED）。
- physical_call_count=0；未启动任何物理求解器。
