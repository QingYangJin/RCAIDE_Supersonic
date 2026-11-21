# D-META-WARM-001｜固定Concorde任务下验证MAML热启动采样加速优势的定向实验计划（2026-11-21）

> **研究目的**：不再把“训练RMSE更低”当作元学习成功的主要证据，而是直接验证：在相同真实VSPAERO评价预算下，MAML能否为预先冻结的Concorde巡航设计任务提供更好的初始设计/种群，使优化器更早找到满足约束、诱导阻力更低的设计。实验围绕路线A（MAML优化器无关热启动采样）展开；路线B元采集策略继续独立研发，但不混入本Issue主要对照，以免无法区分“初始采样收益”和“后续采集策略收益”。

## 0. 当前证据与为什么要调整实验

- 上一轮G1：24次VSPAERO启动、23次完成、391个internal cases、8条准入标签、16条NULL；有效率按完成启动计`8/23=34.78%`，按所有启动计`8/24=33.33%`，未达到原70%目标。G1分任务：M1.60为0/6，M1.80为2/6，M2.02为3/6，M2.40为3/6；15条AUDIT_FAILED、1条NO_RESULT。详见[Issue #13 G1回执](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/13#issuecomment-7061216317)。
- 当前G1任务划分和标签量不足以训练/检验可靠的MAML：训练任务实际只有M1.60（0条）和M2.02（3条）；验证M1.80只有2条；测试M2.40只有3条。每个任务缺少足够的support/query设计，不能靠增加训练步数弥补。
- G1的15条AUDIT_FAILED并不等于VSPAERO全部不收敛：不少极曲线最接近目标升力的原始行相对误差约0.15%–0.27%，但严格要求存在`≤1e-3`的真实原始行；另有M1.60迎角中心偏差更大（约0.5°–0.6°）。因此需要区分**真实原始行命中**与**经验证的同升力插值标签**，不能静默放宽准入。
- 本轮固定任务主目标使用现有可审计的`D_i_N=q·Sref·CDi`。VSPAERO整机总阻力/机身波阻/推进/任务燃油仍未完成外部物理验证；`fuel_burn_kg=null`、`LF-M2.02=NOT_VALIDATED`、`VSPAERO_INTERNAL_ONLY`继续有效。
- 当前12维设计合同保留`W01–W10+V01–V02`、机身F01–F03固定。不得为提高结果而擅自删除垂尾变量、改变变量边界或事后缩小搜索范围。

## 1. 主要科学假设与范围

### H1｜主要假设

在相同固定Concorde目标任务、相同K-shot真实支持样本和相同VSPAERO总评价预算下，FOMAML热启动采样相较随机/Sobol/LHS和普通监督预训练热启动，能够：
- 降低达到预注册气动改善阈值所需的真实VSPAERO启动数；
- 改善前16/32/64次真实评价的best-so-far目标值或归一化regret曲线；
- 不以明显降低种群多样性/增加几何失败率为代价。

### H2｜优化器无关性假设

同一`WarmStartSampler`输出的初始点，在固定BO后端之外，接入DE/PSO时仍能改善各自相对冷启动基线的早期样本效率。若只在BO有效，则结论限定为BO初始化，不宣称optimizer-agnostic。

### 本Issue不试图证明的内容

- 不证明整机总阻力、真实燃油消耗、跨构型泛化或Mach 3迁移。
- 不把MAML的预测RMSE下降直接等同优化加速。
- 不把路线B元采集策略并入主要实验，不允许A/B同时变化后再归因于路线A。
- 不将G1的8条标签或旧R2的9条标签未经A5重新准入后直接当作正式meta_train/meta_test数据。

## 2. 有针对性的实验条件调整

### 2.1 固定目标任务T*

首轮确认性优化只针对一个固定任务，建议沿用现有Concorde巡航候选条件：
- 飞行器：Concorde，12D升力面几何；机身固定。
- Mach：2.02；高度：18,288 m。
- 任务段：固定巡航段；航程候选值3,028,020 m，只有在本轮TaskSpec确认后才冻结。
- 参考升力：沿用当前经核对的`L_ref/CL_target`；当前G1记录中的基准目标约`1,333,704.4 N`，A1必须重新核对质量/CG/载荷定义，不能把136,000 kg简单当成已签署的全任务质量。
- 优化变量：原12维`W01–W10/V01–V02`，单位和原冻结边界不变。
- 主目标：`min D_i_N(x;T*)=q(T*)·Sref(x)·CDi(x;T*,L=L_ref)`。
- 约束：几何有效、VSPAERO求解成功、工况/参考量匹配、目标升力标签通过本Issue新准入规则、`D_i_N`有限且非负。未验证的机身阻力/整机燃油不进入目标函数。

### 2.2 任务划分：固定目标 + 相关源任务，而不是随机拆行

MAML仍需要多个相关任务，但最终被优化的目标任务T*保持固定。为此，本Issue采用**固定Mach/高度/巡航定义下的载荷/目标升力任务族**作为源任务：
- 任务上下文`t=(Mach,h,q,L_target或CL_target)`；目标任务固定为T*。
- 源任务通过不同巡航载荷/目标升力要求构造，候选目标升力比`r_L=L_target/L_ref`可在`0.90–1.10`内选取；具体层级必须由A1检查极曲线共同覆盖范围和任务质量/载荷合理性后，在算法结果揭盲前冻结。
- 建议形成至少6个meta-train源任务、2个meta-validation任务，T*作为完全留出的meta-test目标任务。若A1证明可用域不支持上述范围，应缩小到**所有任务都有有效极曲线覆盖**的共同区间，并说明原因；禁止外推。
- 这只验证“同一构型、同一巡航Mach/高度/任务定义下，不同载荷需求之间的局部知识迁移”。跨Mach、跨高度和跨构型的任务迁移留给Issue #11后续阶段，不在本Issue夸大结论。
- 网络输入可以为`[x_12, task_context]`，例如12个几何变量加`r_L/CL_target`；**设计优化变量仍然是12维**，增加任务上下文不等于增加设计变量。

### 2.3 设计空间：保留12维，先用可解释的局部优化域

- 主实验保留12维变量和原始全局边界，不得永久改写原始配置。
- 为了先检验“初始采样质量”，确认性主实验使用以基准几何为中心的局部信赖域：归一化变量`u_i=(x_i-l_i)/(u_i-l_i)`，建议`|u_i-u_{0,i}|≤0.10`并裁剪到原始冻结边界；A1先做几何有效性/变量扰动预检，随后冻结该局部域。这个结论只适用于局部设计改进，不能称为全局最优。
- 全局12D边界可作为第二个鲁棒性实验，不能与局部域结果混在同一统计量中。
- 对W01–W10/V01–V02做单变量和小规模交互敏感性检查。若垂尾变量对当前`D_i_N`在求解器噪声内近似不敏感，必须如实报告并做独立消融；主合同仍保留12维，不得偷偷删除。

## 3. 关键标签问题：原始行与验证插值分开管理

**不放宽物理标准，不把插值冒充原始求解。** 新数据采用两个互斥的标签类型：

1. `RAW_ROW_MATCHED`：真实polar原始行满足`|q·Sref·CL-L_target|/L_target≤1e-3`，保留原始行号、AoA、Mach、Beta、文件SHA。
2. `INTERPOLATED_VALIDATED`：目标升力被同一Mach、同一Beta、同一几何的相邻有效polar原始行严格夹住；局部`CL(AoA)`单调、无外推、无重复AoA冲突；插值区间宽度处于经校准的范围；通过独立精细迎角求解验证。此类标签必须单独标记来源、bracket、插值方法、误差/不确定度，绝不写成原始行命中。

- W0先使用G1原始polar做**零物理离线重放**，确定每个Mach/目标CL的夹区和失败原因；不回写G1旧标签，不追认G1的15条NULL。
- W1使用代表性几何做粗扫+局部迎角细化，验证`CDi/Di_N`插值相对独立精细求解的误差。误差门限由重复性/离散误差确定，建议上限0.5%，若数值重复性要求更严则采用更严标准；门限必须在MAML/优化器对照前由A5预审并冻结。
- 若插值验证不通过，相关标签保持NULL，改用局部迎角细化获得真实原始行；禁止只为了提高有效率而更改`1e-3`或插值门限。
- 同一条polar可在不同`L_target`下导出多个派生任务标签，但这些标签高度相关：**物理solver starts按原始polar计一次，派生task-label数另列**；同一geometry/raw-polar的所有派生标签必须处于同一个train/val/test几何分组，防止跨任务泄漏。

## 4. MAML热启动采样器与公平基线

### 4.1 统一采样接口

实现/冻结优化器无关接口：
`WarmStartSampler.propose(task_context, design_space, support_evaluations, candidate_pool, n_init, seed) -> X_init`

输出至少包含：`X_init`、每个候选的预测目标/约束/不确定度、选择分数、空间多样性指标、任务/模型/数据SHA、支持集身份、采样器运行耗时。采样器不包含BO采集函数、DE变异/交叉或PSO速度更新。

### 4.2 主要对照方法

在同一冻结任务、相同支持集、同一候选池、同一初始点数、同一总真实评价预算下比较：
- Random / LHS / Sobol冷启动；
- 普通监督预训练代理热启动（与MAML同架构/参数规模）；
- FOMAML zero-shot热启动；
- FOMAML K-shot适应热启动（主比较K=3，K=1/5作为消融）；
- 可选最近任务/最近邻迁移基线，用于区分“任务相似性直接迁移”与MAML快速适应的额外价值。

MAML必须与普通预训练比较，不能只与随机初始化比较后就声称“元学习有效”。

### 4.3 采样策略与多样性

- 固定候选池由同一Sobol序列生成；建议每轮候选池4096点，代理只排序候选，不把预测值写入真实历史。
- 主实验引导比例`rho=0.5`：其余候选由不确定度/空间填充补足；`rho=0.25/0.75`作为消融。
- 用maximin距离或聚类约束避免MAML只挑一簇相近点。记录最小两两距离、覆盖半径、有效维度和种群多样性。
- K个support真实评价、MAML挑选的初始点、DE/PSO整个初始种群、后续BO/DE/PSO查询、失败和重试均计入物理评价预算。所有arm使用同一support集，支持集的共享成本单独列账，不能免费。
- DE/PSO初始个体的`fitness/pbest/gbest`必须由真实求解值初始化，不能用代理预测值冒充真实评价。

### 4.4 优化器安排

- **确认性主实验：BO固定后端**（固定GP核、约束处理、EI或UCB中的一种；在揭盲前冻结），只改变初始采样方法。
- **跨优化器次级验证：DE和PSO**，复用完全相同的MAML采样器，只更换后端适配器；分别与各自Random/Sobol基线配对。若只在BO有效，结论写为BO特定热启动，不宣称optimizer-agnostic。
- 路线B元采集策略在本Issue主实验中关闭，标准BO采集函数固定不变；路线B继续独立研发，待路线A初步通过后再做A/B二因素实验。

## 5. 主要目标与统计评价：直接衡量“少用多少次真实气动评价”

**不要只看最终优化值或预测RMSE。**

### 主要端点

- `N_tau`：从共享K-shot支持集之后开始，达到预注册气动改善阈值所需的新增真实VSPAERO启动数。
- 改善阈值`tau`：先做基准重复性试验，冻结`tau=max(1%, 2×CV_baseline)`；若该阈值超过预设物理可辨识范围，先修复评价噪声而不是改阈值迎合算法。
- 比较MAML相对**最强非元学习基线**（Random/Sobol/普通预训练中表现最好者）的中位`N_tau`和达到阈值概率。未达到阈值的运行按右删失处理，不能把它伪装成达到预算上限。
- 报告`speedup=median(N_tau_baseline)/median(N_tau_MAML)`及配对bootstrap 95%置信区间。

### 次要端点

- `best_feasible_D_i_N`在B=8/16/32/64次真实评价时的best-so-far；
- normalized simple regret / anytime曲线下面积；
- `first_feasible_eval`、每点可行率、每次运行是否至少命中一个可行设计（两种口径分开）；
- MAML候选排序Top-k质量、几何有效率、标签有效率、候选多样性；
- 代理训练/适应/推理墙钟、元训练数据采集成本、break-even目标任务数；
- BO/DE/PSO分别报告，不跨优化器混算一个平均值。

### 统计设计

- 每种方法配对随机种子；确认性阶段先做小规模pilot估计方差，再进行功效/样本量计算，原则上至少10个配对seed；如果预算/真实物理噪声不支持，报告探索性而非显著结论。
- 统计单位是独立目标任务与seed episode；同一polar派生的多个CL标签不能当作独立物理样本。
- 至少一个负控制：打乱task_context/task_id后重训或适应；若打乱任务信息后仍得到相同收益，不能归因于跨任务知识。
- 预注册任务划分、K、候选池、rho、预算、优化器设置、阈值和统计方法。揭盲后不得改变测试任务/超参以追求显著性。

## 6. 分阶段执行与建议预算（均为建议容量，不是自动一次性GO）

| 阶段 | 内容 | 建议真实solver starts |
|---|---|---:|
| W0 | 零物理代码修复、G1原始polar重放、任务/标签/采样合同冻结 | 0 |
| W1 | 固定Mach2.02代表几何的粗扫+局部迎角细化，验证原始行与插值误差 | ≤12 |
| W2 | 固定任务相关源任务数据集：12D局部Sobol/空间填充设计，建立train/val/test几何分组 | ≤64 |
| W3 | 固定目标T*上的BO确认性热启动对照（Random/Sobol、Pretrain、FOMAML-Kshot） | 首轮≤240 |
| W4 | 同一采样器接入DE/PSO的跨优化器小规模验证；效果成立后再按功效扩展 | 每个后端首轮≤72 |

- 上表是阶段容量规划，不代表Issue发布就批准全部物理计算。每批必须A5审查确切代码/任务/预算合同，Lead签新`authorization_id/batch_id/GO`；每mini-batch最多8 starts或60分钟，先同步GitHub并回读SHA再释放下一批。
- 若W1证明插值误差/极曲线覆盖不合格，停止W2；若W2数据不足，先补数据而不是直接训练。
- 若W3中MAML没有达到预注册的样本效率目标，保留NO_EVIDENCE/NEGATIVE_TRANSFER，不强制扩大DE/PSO。
- G1原24 starts已用尽，不能复活旧授权。所有新物理运行使用新run_id/batch_id，所有失败/重试均计费。

## 7. 研究结论判据

- **支持“固定任务下MAML热启动加速采样”**：在真实VSPAERO目标任务上，FOMAML-Kshot相较最强非元学习基线的`N_tau`有实际意义的降低（建议至少20%），配对置信区间支持改善，且几何/标签有效率、候选多样性不恶化。
- **支持“优化器无关”**：除BO外，至少DE或PSO也显示同方向、可复核的改善；否则只声明具体后端有效。
- **不支持/证据不足**：未达到阈值、置信区间跨零、仅RMSE改善但N_tau不改善、只在单seed/单个任务成立，均报告`NO_EVIDENCE`或`INCONCLUSIVE`。
- 即使达到上述标准，结论也只适用于固定Mach2.02、固定高度/巡航任务、12D局部设计域、VSPAERO翼面`D_i_N`目标；不能推广成整机油耗或任意超声速构型的普遍优势。

## 8. 工作分工与交付

| 角色 | 工作 |
|---|---|
| Lead | 唯一总控/Issue回执、冻结协议、每批GO、预算和集成 |
| A1 气动/几何 | Mach2.02迎角校准、raw/interpolation双标签、局部域几何有效性、物理误差 |
| A2 路线A | FOMAML热启动采样器、K-shot、候选排序、多样性、BO/DE/PSO适配 |
| A3 任务/统计 | 固定目标+源任务族、任务上下文、geometry分组防泄漏、统计功效/负控制 |
| A4 数据/GPU | 原始文件/CSV/JSON/PNG逐批上传、SHA与下载回读、训练成本/GPU性能 |
| A5 独立审查 | 对确切SHA审查标签/物理/任务split/预算/公平对照/统计；独立签PASS或CHANGES_REQUIRED |

每阶段原则上只提交一条中文合并回执，附：commit SHA、代码diff、测试结果、run_id、任务/几何SHA、真实solver starts/internal cases/失败重试、raw文件GitHub链接与SHA、admission记录、CSV/PNG、A5意见和下一阶段GO状态。

## 9. 强制GitHub实验产物

建议每个run存入`research/concorde_metaopt/optimization_runs/<run_id>/`：
- `raw_cases/<case_id>/`：真实`.vsp3/.vspgeom/.vspaero/.polar/.history/.lod/.adb`（实际生成者）、deck、stdout/stderr、失败/超时原件；
- `tables/`：`all_evaluations.csv`、`admitted_labels.csv`、`failed_or_null.csv`、`task_labels.csv`、`optimization_history.csv`、`training_history.csv`、`statistics.csv`；
- `metadata/`：`run_config.json`、`task_family_split.json`、`geometry_freeze.json`、`admission_manifest.json`、`batch_accounting.json`、`source_sha.json`、`data_manifest.json`、`SHA256SUMS.txt`、`upload_receipt.json`；
- `figures/`：中文图名/图注，包含标签产出率、迎角细化/插值误差、12D设计分布、MAML初始点空间分布、best-so-far/anytime regret、N_tau分布、BO/DE/PSO对照、训练成本与break-even；每张图附figure_data.csv和绘图脚本。
- 每≤8 starts或≤60分钟同步一次；GitHub实际payload必须可取回，不能只上传本机路径/manifest/hash指针。

## 10. 相关文献与方法边界

1. Feurer, Springenberg & Hutter (AAAI 2015), *Initializing Bayesian Hyperparameter Optimization via Meta-Learning*：从相关历史任务中选择有前景的初始配置，作为BO warm-start的早期基础。https://doi.org/10.1609/aaai.v29i1.9354
2. Hsieh et al. (NeurIPS 2021), *Reinforced Few-Shot Acquisition Function Learning for Bayesian Optimization (FSAF)*：学习的是BO序贯采集函数，不是单纯初始点；本Issue固定标准采集函数，避免与路线A混淆。https://ai.meta.com/research/publications/reinforced-few-shot-acquisition-function-learning-for-bayesian-optimization/
3. Dai et al. (UAI/PMLR 2022), *On provably robust meta-Bayesian optimization*：指出不相关源任务会产生负迁移，并研究鲁棒任务权重。https://proceedings.mlr.press/v180/dai22a.html
4. Agushaka & Ezugwu (Applied Sciences 2022), *Initialisation Approaches for Population-Based Metaheuristic Algorithms: A Comprehensive Review*：强调种群规模、初始化分布与多样性会影响DE/PSO类方法的搜索表现。https://doi.org/10.3390/app12020896
5. Maraval et al. (NeurIPS 2023), *End-to-End Meta-Bayesian Optimisation with Transformer Neural Processes*：将代理与采集策略联合元学习，并指出稀疏regret奖励会使RL元训练困难；本Issue不把路线B并入路线A确认性实验。https://proceedings.neurips.cc/paper_files/paper/2023/hash/2561721d0ca69bab22b749cfc4f48f6c-Abstract.html

**本Issue立即授权零物理软件/数据合同/离线重放/采样器开发；W1–W4真实求解按上表分阶段预注册、A5独立审查、Lead新GO。Issue发布不等于G1修复、真实训练或优化收益已经发生。**