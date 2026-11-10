# D-NEXT-001｜12维 Concorde 固定任务真实评价闭环、路线A通用热启动、路线B元采集策略及 GPU 并行开发实施计划

- 状态：**正式启动软件开发、合成离线研究与真实评价准备**；真实数值求解必须先通过独立物理门禁并取得有明确次数的预算批复。
- 日期：2026-11-10；全文中文；工程代码、数学符号及API名称可保留英文。
- 基线与新增分支：`research/p4-route-a-s3` @ `c7221fb2bdda382b6c2b520d57d20e67740028b8`；新综合规划/集成分支 `research/p5-concorde-real-metaopt-ab`。P1–P3 `research/concorde-metaopt`、M5/M6、路线A S1/S2/S3、旧 PR #3/#6 与 main 均只读保留。各子智能体需独立worktree/子分支，禁止覆盖历史run或直接合并main。
- 研究主张边界：先固定高度、Mach数、航程的 Concorde 12D 任务做真实求解器参与的工程闭环，再推进同构型不同任务的 MAML 跨任务迁移；**内部气动求解成功≠阻力/油耗物理验证成功**。路线A与B平行、结果分别归因。

## 一、现状与必须处理的负结果/阻断

1. 路线A S1：21,000组/1,920,000次合成函数评价（0物理），K-shot→BO 代码闭环及等预算实验完成；主比较 FOMAML-Kshot-BO 对普通预训练 K-shot BO **NO_SIGNIFICANT_IMPROVEMENT**，不可宣称元学习受益。
2. S2：Full MAML 多步二阶可微元梯度通过 32/32 有限差分；6,000条记录中，合成 meta_validation 的 K=5/K=10 适应后RMSE相对FOMAML分别报告约−3.394%/−1.619%相对改善率（实际更差）。保留 FOMAML 为主基线，Full MAML 为科学对照，不默认换用。
3. S3：`research/p4-route-a-s3` @ `c7221fb`；约束感知/ANIL 3,780 runs/362,880 合成评价完成，四个预注册检验全 `NULL/NO_EVIDENCE`，**S3阶段验收 NOT_ISSUED，S4 NOT_APPROVED**。存在A5未重新签发M2R run门而A7替代、A3独立仓库守护代理崩溃、`validate`模型清单路径缺陷F-01、聚合校验口径F-02、OOD正式分析未接入F-03、`wall_s=0`导致ANIL成本不可审计、NC补丁为sidecar、4/10图 NOT_RUN。新工作先归档整改与独立审计，不追认旧结果为PASS、不得无说明变更已冻结分析器。
4. VSPAERO 7.2.2 在12D主翼的内部系数可复现；D-12D-005实际14/20启动，剩余6次已`CLOSED`。外部`LF-M2.02=NOT_VALIDATED`、`BODY-CORR=BLOCKED`、`HF-M2.02=PARTIAL`；当前没有已验证的整机总阻力/燃油响应。`X_cg=16.821978259514246m`实际上是机翼气动中心，几何模型全机CG`28.287395109126685m`，相差`11.4654m`；旧固定巡航136000kg与几何总起飞质量184880kg口径未统一。未解决前不可做配平/静稳定/质量归一化油耗结论。
5. 设计空间`design_space_12d_lifting_surfaces.yaml`为W01–W10+V01–V02，固定机身F01–F03；当前变量与数值边界`frozen: false`。12D维度保持不变，仅在任务族/任务上下文、合成响应和采样方法中增量改进。巡航基准候选`M=2.02、h=18288m、R=3028020m`，136000kg是单巡航进入质量而非MTOW，须说明并冻结。
6. 先前的负责人指令“VSPAERO继续，RCAIDE气动回退暂停”**继续适用**。本新阶段明确授权路线A/B/PSO/GPU等**软件开发及合成离线验证**，并授权提出真实12D求解试验方案；**并不自动恢复旧6次或给出无限制真实气动计算预算**。旧RCAIDE B类12次仍LOCKED。

## 二、总目标与独立假设

- **F线：固定12D真实求解工程闭环**。相同设计变量下，严格记录`design_u → OpenVSP几何 → VSPAERO原始极曲线/载荷 → 参考量/状态校验 → 真实求解器评价记录 → 优化器ask/tell`。首先证明可执行、可追溯、约束及预算正确；只有物理评价器通过相应验证才讨论燃油优化收益。
- **A线：基于MAML的优化器无关热启动采样**，只学习任务响应并生成初始设计/种群；后端BO、DE、PSO只读取相同的已评价初始点和优化器自身状态，所有采样/适应/真实评价成本计入合同。核心问句：同一采样器能否跨不同算法降低首次可行评价序号/小预算最优可行目标差距？
- **B线：学习BO迭代采集决策的元策略**（MetaBO/FSAF 类方法作为研究方向，须代码/文献/对照审阅），学习新样本的序贯`policy/acquisition`，而非重用A线初始点排序。不宣称已具备现成策略训练或已取得收益。核心问句：在固定初始点与评价预算下，学习采集策略是否比标准BO采集提高样本效率？
- **GPU线**：RTX5060 8GB、PyTorch项目环境`2.8.0+cpu`；参照先前[GPU并行任务草案](https://github.com/QingYangJin/RCAIDE_Supersonic/blob/planning/next-issue-gpu-benchmark/docs/planning/next_issue_gpu_pytorch_benchmark_DRAFT_20261106.md)独立建CUDA环境并测试训练加速，不改变旧CPU数值或S1–S3确认性结果。GPU更快不等于算法更好。
- **迁移线**：完成固定任务工程闭环后，建立同一机型的多个任务条件（Mach/高度/航程/巡航进入质量等），固定12D几何变量定义；前提是任务工况处于求解器可接受域，且有一致的任务约束与可信标签。一个固定任务不同随机seed不构成真实多任务MAML。

## 三、分阶段执行与放行门禁

### M0｜审计与冻结（必须先完成，软件工作可并行）

- A5对S3独立复核中缺失的A5 M2R签核、A3缺失审计、F-01/F-02/F-03、ANIL耗时`wall_s=0`、OOD/NC侧车、未出的图作**专项审计清单**；只在新分支修代码/重测，不修改S3历史run。新正式测试集不得依据旧公开结果调参。
- A1对12D变量边界、W01–W10/V01/V02、参考Sref、CG/AC与质量/推进/单巡航入口条件做一致性审查，分清 “136t巡航入口” 与 “184.88t几何模型总起飞质量” 并提出可签署的`TaskSpec`合同。不能默许质量一致或把机翼AC当真实CG。
- M0交付中文`baseline_and_gate_audit.md`、`fixed_concorde_task_contract_v2_DRAFT.yaml`、`software_compatibility_matrix.md`与外部资产SHA；Lead正式裁决/核对后才允许真实物理启动。当前S3的`S4=NOT_APPROVED`不因本新任务自动改变；本任务另行管理工程集成合同。

### F1｜固定任务真实评价器的软件闭环（零真实求解即可立即开发）

- 以12D `DesignSpace` 和 `task_fixed_cruise.yaml` 为候选，抽象统一 `EvaluatorProtocol.evaluate(x,task,fidelity)`、`EvaluationRecord`、`BudgetLedger`、`objective/constraints/status/provenance`，失败值`null`且正确计费。区分`GEOMETRY_INVALID`、`SOLVER_NONCONVERGED`、`PHYSICS_NOT_VALIDATED`；不虚构燃油/机身波阻。
- 路径：12D几何哈希、OpenVSP/VSPAERO thin-LF配置（版本7.2.2）、参考量/单位/气动力轴/力矩参考点、`polar`新版48列表头、尾迹/残差/重复性、`manifest/SHA`。mock/frozen archival replay 执行“设计→气动→评价→优化ask/tell”零物理闭环。
- **真实优化第一层仅为求解器在环工程诊断（ENGINEERING_SOLVER_IN_LOOP, VSPAERO_INTERNAL_ONLY）**；在独立物理校核前允许记录内部`CL/CDi`及预注册诊断性`J_diag`，但不得称为真实油耗最优，不得将`CDtot/CDo`直接认作经独立验证的整机总阻力。
- **真实启动预算**：根据用户本轮指示正式启动真实验证方向，但新Issue**不把未明确指定的次数解释为已经批准**。提请Owner在本Issue单独批复Tier0 **建议最多6次新VSPAERO真实启动**（先完成CG/质量/轴口径、A5预启动门），与Issue#4旧14/20封账独立；只有Tier0 PASS、物理校核/诊断状态允许且Owner再次批准时，才提申请不超过**12次**固定任务小规模真实优化试点。其他真实求解`VSPAERO/SU2/Mission/WaveDrag=0`默认，RCAIDE气动回退继续LOCKED。每次含超时/重试计入，串行/≤4线程/≤900s每案/独立停止，保存真实进程与输出证据。
- 整机真实油耗若依赖尚未校核的机身波阻、翼身干扰与任务求解链，`fuel_burn_kg=null`且不对“实际燃油优化”签字；若要启动真实Mission，另行解除当前禁令、完成质量/阻力合同并申请独立预算。不得将VSPAERO翼面系数等同整机油耗。
- 初始固定任务可先仅比较Random BO和DE的评价与缓存路径，再引入A热启动、B学习采集。真实物理budget在所有臂总和内核算，不能用同一历史标签跨算法免费借用而不披露。

### A1｜优化器无关 MAML 热启动实现（与F1/B1/GPU并行，纯合成）

- 新建共享`WarmStartSampler`接口：`propose(task_context,design_space,support_evaluations,candidate_pool,n_new,seed) -> ProposedDesigns`；输出`X_init∈[0,1]^(n×12)`、每点排序/预测`f/g`、置信或`uncertainty=null`、可行性估计、均匀性距离、model_sha、provenance、sample_budget。采样模块不得含BO采集函数、DE差分操作、PSO速度更新。
- 可选普通监督预训练/FOMAML K-shot/零样本代理；Full MAML仅实验基线。采用确定性候选池、预测排序（目标/约束/可行性）、空间多样性、探索保留比例`ρ∈{0,0.25,0.5,0.75}`（正式实验前在meta_val预注册）。所有支持集K次真实评价计入B，不允许代理预测替代真实标签。
- **BO适配器**：K公共观测+模型选n个新起始点，后续统一`maml_opt.ConstrainedBayesianOptimizer`；A独立于采集策略B。
- **DE适配器**：修改现有`optimization/baseline_de.py`支持外部`initial_population`，控制种群`Np≥4`、自适应/固定比例、高度集中时补充LHS、多样性阈值与差分变异退化诊断；全种群初始真实评价计入B。
- **PSO新基线**：引入独立`baseline_pso.py`，接收初始粒子位置；速度`v_i`、个人最好`pbest`与全局最好`gbest`要依次从已评价`f,g`建立，不能用代理预测直接设best。冻结边界处理、惯性/学习因子、不可行选择和随机种子、Np与总预算。
- 同一采样模型适用于三后端，先`K=0/1/3/5`、`B=16/32/64/128`逐级测试（低预算先用于判断早期增益，模型/任务事先冻结），跨后端比较用相对自身随机/LHS/Pretrain基线的配对改善，且报告热启动占总预算比例。避免因不同Np造成不公平；独立报告代理预训练/适应成本。
- 交付`warm_start/`、3个适配器与独立测试、训练曲线、首次可行评价、best-feasible/gap、群体多样性与失败率；没有改善也可科学通过。

### B1｜路线B元采集策略（与A独立开发，先合成实验）

- 首先提交中文方法对照`route_b_acquisition_design.md`：明确学`πϕ(x|D_t,task_context)` / 可学习采集评分，预训练轨迹来源/生成成本，状态(历史x/y/约束/预算剩余)、动作(候选选择)、奖励(可行改进/目标gap/评价成本)，序贯任务分布划分与训练目标；与MetaBO/FSAF等公开方法的关系需正式文献对照。
- 实装`MetaAcquisitionPolicy`与离线`trajectory_dataset/`、`policy_train/`、`policy_eval/`；仅输入已实际评价的历史记录，代理假标签不得进入history；没有足够已识别策略轨迹或可靠训练目标时先`NOT_READY`，不能借用A的打分函数改名为路线B。
- 首轮B仅基于BO后端对照标准EI/UCB/PI或既有约束BO采集（实际可用算法在设计合同确认），不得默许“MetaBO一定胜出”；等评价B、任务/训练seed/holdout、初始化数与分布必须一致。明确训练离线成本/轨迹生成真实函数调用成本单列、避免轨迹/holdout泄漏。
- **关键2×2因子消融（仅两路线都通过各自审查后开展）**：A−/B− = 随机初始化+普通采集；A+/B− = MAML热启动+普通采集；A−/B+ = 随机初始化+元采集；A+/B+ = 热启动+元采集。由相同BO后端分别估计初始化主效应、采集主效应和交互；路线A跨DE/PSO由A线独立验证，不把路线B强制扩为DE/PSO策略学习。
- 固定任务真实性验证需先准备科学可比的真实标签；同一任务单任务训练的“元策略”不能称为跨任务泛化。

### GPU-TEST｜独立并行 PyTorch RTX5060 加速（本阶段纳入正式新 Issue）

- 依据[既有GPU草案](https://github.com/QingYangJin/RCAIDE_Supersonic/blob/planning/next-issue-gpu-benchmark/docs/planning/next_issue_gpu_pytorch_benchmark_DRAFT_20261106.md)，RTX5060 8GB、9950X 16C32T、系统RAM约32GB、项目PyTorch`2.8.0+cpu`。本阶段GPU-TEST正式并行执行**独立环境与验证集性能测试**，不把GPU安装当算法收益。
- `G0`：保留`D:\RCAIDE\envs\RCAIDE\python.exe`不变，创建独立CUDA venv，核对CUDA真实forward/backward FP32/FP64，保存版本/显卡驱动/计算能力/环境SHA；若驱动或CUDA构建不兼容，记录失败、不得改原环境。
- `G1`：同任务/同种子下对比CPU-FP64、GPU-FP64、GPU-FP32的FOMAML预训练、K-shot、代理批量打分；GPU张量/参数常驻、减少`.cpu().numpy()`往返，计时前后`torch.cuda.synchronize()`，重复≥3次；记录训练及整个BO实验墙钟/显存/峰值RAM/QueryRMSE/梯度误差/数值异常，分开报告GPU训练与CPU优化器耗时。
- `G2`：仅在Full MAML二阶梯度门禁通过时做GPU二阶训练试验；不破坏`create_graph=True`的完整求导路径；Float32需要独立容差/确定性说明。
- `G3`：是否合并GPU可选后端取决于实测吞吐/精度和A5复核；不得修改冻结S1-S3样本和代码。CPU GP/BO/DE/PSO保留多进程可调并发，GPU训练最多一个主要训练进程作基准；RTX5060 FP64吞吐未证实，不虚构提升倍数。
- 交付中文GPU环境/性能报告、3路性能CSV、图及CUDA fallback策略；硬件性能测试不得动真实meta_test。

### T1｜真实同构型跨任务 MAML 迁移（F1/物理通过后提交实施预算）

- 保持完全相同12D几何变量与固定机身，定义多个`TaskSpec`（巡航Mach、高度、航程、进入质量），每个新任务必须位于求解器/推进可接受域且有同一评价/约束语义。先锁`train_tasks/validation_tasks/test_tasks`并有多个独立物理标签；至少一个从未用于训练的任务用于K-shot/BO热启动迁移验证。
- 区分“不同任务的真实物理响应”与“固定任务不同seed的优化轨迹”；前者才构成跨任务元学习的主科学对象。
- 本新Issue不默许多任务真实训练/批量求解预算；T1需提交物理计价、任务任务数和评估器适用域，Owner进一步决定。不得用旧15D几何DOE冒充12D已验证油耗训练集。

## 四、正式统计与交付合同

- 主要指标：`first_feasible_eval`、`feasible_hit_rate`（定义明确为可行评价点/B，与“至少找到一个可行解”的运行命中率分开）、`best_feasible_value`、`gap_to_reference`、早期B=8/16/32/64性能、失败/无可行`null`比例；中间`B`若与种群`Np`不符，只做已预注册合法层。
- 次要指标：预测RMSE/MAE、候选可行性分类与边界误差、初始化多样性、DE population退化、PSO粒子多样性与早熟、BO采集成本、GPU/CPU时间/显存、总成本分摊。
- 统计单位为**任务**（优化seed任务内聚合，元训练seed单列），配对估计+置信区间+多重比较校正与负控制。A与B模型训练任务、验证任务与新的盲测集隔离；一次揭盲后不得按结果反向改任务或超参。保持旧S1/S2/S3负结果不可变。
- 中文图至少：①固定12D几何/真实求解器闭环/求解失败矩阵；②VSPAERO CL/CDi与离散敏感性、物理门禁；③A在BO/DE/PSO上的早期可行与gap收敛；④初始化多样性对DE/PSO效率；⑤B的策略训练与对照序贯收敛；⑥A/B 2×2主效应与交互；⑦CUDA与CPU性能-精度折衷；⑧固定单任务到多任务任务分布/负迁移诊断。没有数据标`NOT_RUN`，不制作虚假物理图。
- 每工作包必须有`run_id/git_sha/code_sha/task_id/design_set/evaluator_id/fidelity/source_kind/physical_validation_status/solver_version/budget_B/K/initial_population_size/seed/physical_call_count`，产物`run_config.json/evaluations.jsonl/optimization_history.csv/metrics.csv/data_manifest.json/SHA256SUMS.txt/figures/*.png`；外置大文件按bytes+sha256指针列入证据清单，并说明GitHub独立复现局限。

## 五、建议子智能体组织（Lead + 5个并行代理）

| 角色 | 专属工作包 | 具体责任 |
|---|---|---|
| **Lead / 项目集成与预算控制** | 总控/M0、F0、发版 | 维护依赖/全局停止条件、全线CPU/GPU资源调度、唯一GitHub写操作、S3争议裁决请求、Owner真实求解批复、最终中文事实回执；不得将未审阅run宣称通过 |
| **A1 / 真实评价与航空约束** | F线 | 12D/OpenVSP/VSPAERO接入、CG/质量/TaskSpec/力轴合同、零求解replay/诊断目标、真实算例最小矩阵、solver调用预算与证据 |
| **A2 / 路线A采样热启动** | A线 | 优化器无关`WarmStartSampler`、BO/DE/PSO起点接口、群体多样性与K-shot计价、合成实验、起始点/算法差异与图表 |
| **A3 / 路线B元采集策略** | B线 | MetaBO/FSAF类文献与设计、轨迹构建、元采集模型、普通采集对照及2×2因子实验；不能借A采样器改名成B |
| **A4 / GPU、计算加速与数据工程** | GPU-TEST/infra | CUDA独立环境与FP64/FP32基准、训练计算核对、CPU并发profiling、工作树/分支隔离与制品manifest；配合恢复原A3仓库审计代理的独立性，但不签自己的审计结论 |
| **A5 / 独立科学与代码审查** | 审查所有线 | S3缺陷复核与审计补强、任务泄漏/全梯度/预算/物理状态审查、A/B公平性、GPU精度、单任务/迁移科学口径、分阶段PASS或CHANGES_REQUESTED；不得自审自改 |

- 现有分支/工作树较多，**A1–A4之间不共享同一可写worktree、不私自push/main合并**；Lead严格执行并发CPU资源上限和GPU/CPU隔离。A3如需担任代码开发，应由Lead+A4重新建立独立仓库隔离检查，A5对其提交独立审计，不能把过去A3崩溃问题当已解决。
- 不创建额外的代理数量作为硬前提；若工作机已有额外A6可用于中文统计/图表，但不能代替A5独立审核或A3证据守护。每个子代理统一提交`task_receipt.md`与明确SHA/测试输出，Leader汇总后GitHub更新。
- 里程碑建议：M0/F1软件零求解 + A1/B1/G0同步启动；软件试验与GPU冒烟无需等待Tier0真实预算；M0/A5通过后才可请求Tier0实际VSPAERO；F1真实求解器工程结论出炉后再考虑真实优化，A/B科学对照可先继续合成。

## 六、审批与禁止事项清单

**本Issue立即授权**：中国语言研究计划、代码、单测、CUDA独立环境、FOMAML/ANIL/Full MAML与跨BO/DE/PSO+路线B元采集**纯合成离线**实验、零求解假评价器与旧证据只读分析、真实求解器接口准备。

**本Issue不自动授权**：已封账VSPAERO6次复活；无上限真实优化；任何未获有明确次数新批复的VSPAERO/SU2/Mission/WaveDrag；RCAIDE气动回退；把`VSPAERO_INTERNAL_ONLY`系数视为真实全机油耗；未经签字的真实多任务MAML元训练；main合并/旧PR关闭。

**何时可以科学签字**：软件闭环≤ENGINEERING_PASS；未外部验证的VSPAERO`LF_NOT_VALIDATED`；真实空气动力校核通过后才有相应 LF_VALIDATED（限验证范围）；目标真实燃油优化必须同时满足可信阻力分项/机身/推力/质量/CG/任务计算/约束/独立评审。

最终交付要求：**全中文技术文档及真实/合成数据分开的图表，保留阴性结果。**
