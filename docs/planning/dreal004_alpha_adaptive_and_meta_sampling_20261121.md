# D-REAL-EXP-002｜自适应迎角求解与元学习加速采样专项实验计划（2026-11-21）

## 0. 负责人决策与本阶段目标

本阶段不是简单扩大solver数量，而是针对G1的明确失败机制，重新设计实验条件与评价目标，回答核心科研问题：

> **在相同真实VSPAERO调用预算下，基于跨任务MAML的候选设计采样，能否比Random/LHS/Sobol/普通预训练代理更快找到满足升力约束、且同升力诱导阻力更低的设计？**

保持Concorde机翼+垂尾12D设计变量W01–W10/V01–V02，机身固定；固定任务基准Mach 2.02、高度18,288m和已冻结的质量/参考量/CL目标合同。后续任务迁移仍使用相同12D定义，改变真实进入VSPAERO deck的任务条件。**本阶段优先路线A（优化器无关MAML热启动采样）；路线B独立继续，不与路线A混为一个算法或归因。**

本计划从远端分支`research/dreal003-expanded-aero-meta-20261120@409f09c8b31ce653873727217273805a16d5b422`建立。历史G1结果保留，不能重标或覆盖。

## 一、G1的诊断结论与不可更改事实

- G1授权24次VSPAERO启动，实际24 starts、23 completed、1 NO_RESULT、391 internal cases、8 admitted labels、16 null；标签率8/23=34.78%（按全部starts为8/24=33.33%），未达到70%目标，**G2 NO_GO**。
- 15个AUDIT_FAILED主要因为原始极曲线没有一行满足严格升力相对误差`1e-3`；最接近原始行约0.0015–0.0027。评价器插值出的目标升力结果不能伪装成原始求解行。1个M202 case在120秒边界无case_result，永久记NO_RESULT。
- M160 6个case全0标签；G1回执指出原单一全局alpha模型对M160目标迎角高估约0.52–0.62°。M180、M202、M240各有部分标签。
- B01在A5修复前执行，0标签；B02修复后16个starts，即使16个全成功，累计最大标签率也只有16/24=66.7%，所以G1目标70%从设计上已不可能达成。这个协议设计错误应记录为实验设计教训，不归咎于物理模型。
- G1已有数据、原始文件、失败案例、账本、图、SHA上传在[数据目录](https://github.com/QingYangJin/RCAIDE_Supersonic/tree/f0e455f32b70da88f40d32f8be1fbabd649981ab/research/concorde_metaopt/optimization_runs/DRECOVER001-G1-20261121-01)。历史数据保持不变。
- 现有8条真实标签主要来自Mach1.8/2.02/2.4，Mach1.6无有效标签；不能把当前8条直接当作足够的MAML训练集。G1没有真实BO/DE反馈优化，也没有新的MAML训练。
- 当前物理边界仍为VSPAERO内部翼面系数/诱导阻力，LF-M2.02未获外部物理验证，fuel_burn_kg=null。不能宣称整机油耗改善。

## 二、核心调整：将“每个设计一次固定alpha sweep”改为“目标升力驱动的自适应迎角求解”

### A1｜自适应alpha搜索器

实现独立模块`AdaptiveAlphaSolver`，每个`(design_x, task)`求目标升力，而非用一个全局固定迎角表。

1. **输入合同**：12D几何设计、真实task deck（Mach/rho/Vinf/q/Sref/CL_target/alpha范围）、求解器版本/网格/尾迹配置、升力容差`tol_CL=1e-3`。所有状态从当前case deck读取，禁止TASK_SPEC全局值覆盖实际工况。
2. **阶段a：粗扫描**：用经过物理合同许可的迎角区间执行低密度alpha扫描，保留全部真实求解原始点，检查CL(alpha)单调性、有效极曲线、分离/失效、是否存在包围CL_target的区间。
3. **阶段b：区间定位**：若目标被相邻有效alpha点包围，使用bracketing（如二分/割线）产生下一真实alpha求解点；若CL(alpha)局部非单调，分段识别所有有效区间，不跨越无效段插值。
4. **阶段c：停止**：只有**真实求解点**满足相对CL误差≤1e-3才输出`RAW_POINT_MATCHED`标签。若达到每设计最大alpha求解次数、alpha边界仍未包围目标、极曲线不单调或求解器失败，输出明确的`NO_BRACKET/NO_CONVERGENCE/INVALID_POLAR`，不得强行外推。
5. **插值分开记账**：允许生成`INTERPOLATED_TARGET_ESTIMATE`用于诊断/代理候选排序，但它不属于真实raw标签；不得与真实行混合训练。若未来考虑把插值标签用于模型训练，需另立数据来源类型、误差校准和A5批准，不能静默改变本阶段严格准入定义。
6. **预算效率**：每个alpha case都计入internal_solver_cases与wall time；一次设计级真实solver start与其内部alpha cases分开记账。记录达到目标升力所需的alpha case数，与旧固定sweep的平均case数比较。不得仅以design start次数宣称成本下降而隐藏内部计算量。
7. **安全与物理检查**：固定VSPAERO版本、网格/尾迹/收敛阈值；记录CL、CDi、alpha、q、Sref、Di_N=q*Sref*CDi、solver状态、原始文件SHA。无可靠极曲线/不在适用域时拒绝准入。

### A2｜G1.1 alpha算法离线/小批验证

- 先用G1现有24个case原始文件做零物理replay，比较旧固定扫描与新自适应算法的目标迎角预测、可否形成有效bracket、所需alpha case数；**replay不计新物理标签**。
- 使用合成CL(alpha)曲线、非单调/多根/无包围/求解失败模拟测试停止条件；但合成测试不得作为物理验证。
- 之后提出新批次，先以固定Mach2.02基准+若干设计扰动做小规模真实试验，再逐步覆盖Mach1.8/2.02/2.4；Mach1.6单独作为故障诊断工况，不得因其零标签而强行塞进训练集。
- 保持`tol_CL=1e-3`。本阶段目标是改善真实求解的标签产出和总内部求解成本，不通过放宽阈值制造标签率提升。
- G1.1建议首个pilot最多12个新design starts，每个设计最多预注册alpha求解case数；pilot达到目标或出现失败模式后暂停，由A5/Lead复核再申请扩容。预算口径分别列design starts、internal solver cases、重试/失败/缓存。

## 三、路线A研究调整：从预测RMSE转向“固定真实评价预算下的加速采样”

### A线研究假设

H1：在相关航空任务族中，MAML代理利用历史任务的真实响应结构，能在新任务少量support数据下，将更多高价值候选排到初始采样前列。

H2：在相同总真实评价预算下，MAML热启动较Random/LHS/Sobol及普通预训练，能更早找到可行设计或更快降低最优可行同升力`Di_N`。

H3：如果同一采样器分别接入BO与DE/PSO仍能带来收益，则说明学到的是优化器无关设计先验；若只对BO有效，需如实限定结论。

### 任务和数据设计

- 固定12D变量语义与边界，冻结变量尺度、有效mask、几何有效性约束；不能在不同任务间改变变量含义。
- 任务上下文至少包含真实Mach、目标CL/升力、q、Sref及其他经验证会改变真实deck的任务条件；不要把仅改变task_id或seed算作新任务。
- **先构建同一任务内的设计响应数据，再建立任务级迁移**。MAML的task应是一组不同设计x在一个固定真实工况下的函数评价数据，而不是一个样本/一个seed。
- 当前8条真实标签不足以训练有说服力的MAML。G1.1先提高有效标签产出；G2建议目标≥8个物理可区分任务（至少4 train、2 val、2 heldout test），每个任务目标8–10个去重有效设计，其中至少K support与多个query；具体数由实际标签率/solver成本决定，不得为了凑8任务纳入不适用Mach。
- 测试任务身份在任何超参数选择前冻结；训练/验证/测试严格按task_id隔离。对每个test task使用同一support真实观测，所有方法获得相同K与相同评价成本。
- 训练对照：FOMAML、普通pooling pretrain、task-conditioned pretrain（若条件输入使用16维，需与12D设计变量清晰分开）、random initialization；Full MAML作为可选消融，不预设其更优。
- 在固定单任务阶段先验证算法闭环，不把单任务不同随机种子称为跨任务MAML。

### 优化目标与主终点调整

**不再把全设计空间RMSE作为唯一或主要成功指标。** RMSE/MAE仍为代理诊断指标；主要终点应直接反映有限真实评价预算的采样价值：

1. `N_first_feasible`：从开始到首个满足全部已批准约束的真实设计所需design evaluations与internal solver cases。
2. `best_feasible_Di_N(B)`：预算B结束时最优真实可行同升力翼面诱导阻力。
3. `simple_regret(B)=best_observed_feasible_Di_N(B)-D_reference`：参考解必须由独立充分搜索/可信边界建立；否则只报告best-so-far，不造reference。
4. `feasible_hit_rate`：分开定义“点级可行比例”和“运行级至少找到一个可行点的比例”。
5. `cost_to_target`：达到预注册Di_N改善阈值所需的实际VSPAERO design starts、internal alpha solver cases、墙钟/失败成本；阈值应在验证任务确定后冻结。
6. `anytime_curve`：B=4/8/16/32/64/128下最优可行Di_N、可行性、累计真实调用；低预算段是本研究重点。
7. 代理RMSE、排序相关、可行分类、校准、OOD误差作为次要机制指标，不用它们替代优化收益。

### 严格公平对照

- 采样器对照：Random、LHS、Sobol、普通预训练代理、FOMAML K-shot、FOMAML zero-shot（若适用）。
- 后端：首轮固定BO（统一同一个GP与采集策略）；随后同一采样器接DE/PSO作跨优化器扩展。**路线B元采集策略不纳入本次路线A因果主对照**，以免混淆热启动效应；路线B继续独立软件/合成研究。
- 对每个任务、seed、预算B使用配对设计；所有support点、初始样本、alpha solver cases、失败/重试都计入成本。不得将MAML训练历史任务成本隐藏；报告“摊销前/摊销后”两种工程成本。
- 至少多个独立test tasks与多个优化随机种子；以task为一级统计单位，配对差、置信区间、bootstrap/Wilcoxon及多重比较校正；若样本太少，标`UNDERPOWERED`。
- 采样器必须保留探索比例和空间多样性，避免候选聚集导致DE/PSO退化；预测值不能冒充真实标签。

## 四、分阶段新实验授权/门禁

### P0｜代码/分析重设计（立即，0新物理）

- 修复AdaptiveAlphaSolver；完成G1原始24 case零物理replay、合成曲线单元测试、Mach/q/Sref/CL目标一致性检查。
- 修复12D每个变量的几何/气动扰动审计，重点核查V01/V02是否真实改变VSPAERO输入和输出；无响应时查明是变量未连接、模型对称/变量范围过小还是气动效应真实很小。
- 新建A线实验分析器，计算主终点/anytime/cost-to-target与公平预算；冻结新的任务split和实验预注册。
- A5审查确切code SHA和实验协议，交付`P0_CODE_AND_PROTOCOL_PASS`或CHANGES_REQUIRED。旧G1结果不改写。

### P1｜自适应迎角小批物理试验（建议≤12个新design starts）

- Owner此前已批准宽总预算、每批有限GO；本阶段由A1提出实际alpha cases预算上限、预计耗时、stop rules，A5逐项预审、Lead新GO后才启动。
- 先固定Mach2.02基准和少量12D扰动，pilot验证目标CL的真实行命中率、每design内部求解alpha cases数、重复性、失败率；通过后再申请扩展Mach1.8/2.4。Mach1.6继续单独诊断。
- 每≤8 design starts或≤60分钟（先到为准）上传完整原始VSPAERO数据、所有失败case、deck、ledger、SHA、CSV/PNG；GitHub远端回读通过后才放行下一mini-batch。
- 验收建议：目标升力真实raw-point命中率显著优于G1的8/23，并达到预注册目标（初始建议≥70%）；若样本数太小导致区间宽，标UNDERPOWERED，不强行放行。
- 本批不是MAML训练批，不宣称优化收益。

### P2｜扩充真实任务族与训练数据（规划容量≤240新design starts，逐批GO）

- 仅在P1通过后；至少8个物理有效任务、≥4 train/≥2 val/≥2 heldout test，任务适用域经审查；每个任务至少多个独立designs和query，不能只有一个query。
- 按有效率和内部alpha成本动态规划每任务starts，不能先假定240次一定够；每批≤16–32starts（或更短时限）上传/回读后继续。
- 新数据通过RealAdmissionManifest、原始SHA、deck/geometry/task身份与A5准入后才进入MetaDataset。训练/验证/测试任务级隔离冻结。
- 在真实标签满足最小量后实际训练FOMAML/Pretrain/Context-pretrain，记录checkpoint、训练曲线、适应前后误差和运行成本。若任务数/标签量不足，先扩大有效数据，不以合成训练代替。

### P3｜真实优化器加速采样主实验（规划容量≤384新design starts，逐批GO）

- 首先在固定Mach2.02 Concorde任务，使用相同真实support、统一BO后端、同一总design starts+internal solver cases成本，比较Random/LHS/Sobol/Pretrain/FOMAML热启动。
- 真实MAML必须从多个真实训练任务学习初始化；对未见任务仅使用K-shot support适应；不能用测试query反向更新/调参。
- 后续将同一WarmStartSampler接DE/PSO，验证优化器无关性；按各后端自己的随机基线比较相对收益，不能跨算法直接拿不同目标值/不同种群大小宣称赢家。
- 输出B=4/8/16/32/64/128 anytime曲线、首个可行成本、best-feasible Di_N、成本到目标、任务级配对统计、种群多样性、训练摊销成本。负结果照常报告。
- P3容量≤384仅为首轮计划容量，按批A5审查、Lead GO；后续追加需要说明功效/数据有效率/资源依据。

## 五、原始结果上传合同（强制）

所有新物理mini-batch在每≤8 design starts或≤60分钟上传GitHub远端：
- `optimization_runs/<run_id>/raw_cases/<case_id>/`：真实几何、求解deck、polar/history、stdout/stderr、mesh/wake、超时/失败记录；
- `tables/`：`all_evaluations.csv`、`admitted_labels.csv`、`failed_or_null.csv`、`alpha_refinement_history.csv`、`actual_solver_ledger.csv`、`optimization_history.csv`；
- `metadata/`：`run_config.json`、`task_family_split.json`、`geometry_freeze.json`、`admission_manifest.json`、`data_manifest.json`、`SHA256SUMS.txt`、`upload_receipt.json`；
- `figures/`：中文迎角细化前后CL-alpha、目标CL命中、Di_N对照、每design内部求解成本、G1/G1.1有效率、BO anytime、MAML K-shot误差/收益、figure_data.csv和绘图脚本；
- 大文件使用Git可取回payload/Git LFS/Release实际资产，提供永久URL、字节数、SHA；只提交LFS pointer/本地路径/文件hash不算完成。
- A4在新空目录从GitHub下载抽查至少1个成功+1个失败case，逐SHA核验并重算Di_N；每批远端核验PASS后才能放下一批GO。

## 六、子智能体分工

- **Lead**：唯一新Issue总控/批次GO/计算资源调度/远端上传门禁与中文回执；保持路线B独立，不把它混入路线A主对照。
- **A1 气动**：AdaptiveAlphaSolver、Mach/CL/q/Sref、迎角细化、几何变量响应、VSPAERO真实求解及原始文件。
- **A2 算法**：MAML optimizer-agnostic sampler、BO主对照、DE/PSO适配和多样性，真实等预算加速采样统计。
- **A3 元学习**：真实任务族与任务级split、FOMAML/普通预训练/上下文预训练、K-shot及测试隔离；路线B独立。
- **A4 数据/GPU**：GitHub原始文件同步、CSV/PNG可重绘、远端下载验证、CPU/GPU训练性能；不能将GPU速度称为MAML收益。
- **A5 独立审查**：代码SHA、迎角求解物理合同、标签准入、预算、真实/合成隔离、统计功效和GitHub回读；明确PASS_WITH_DISCLOSURE/CHANGES_REQUIRED，不代替Owner签署。

## 七、明确禁止与成功标准

- 不放宽`tol_CL=1e-3`以人为提高标签率；若想使用插值标签，另列`INTERPOLATED_ESTIMATE`并单独校准/审查，不能混入raw-point主结果。
- 不用G1 null点冒充成功，不删除失败、不重写历史；不把internal solver cases隐藏在design start成本后。
- 不以全局RMSE下降替代真实优化加速；不能只挑最优seed/任务。
- 不把VSPAERO翼面诱导阻力当整机阻力/燃油；`fuel_burn_kg=null`及LF-M2.02=NOT_VALIDATED保持。
- 不启动240/384全量大批，先完成P0、P1并逐批上传；RCAIDE回退继续暂停。
- **成功不要求MAML必须胜出**：若FOMAML未优于普通预训练或Sobol，应如实结论“在当前任务分布/预算下未显示采样优势”，并分析适用边界。

**本计划当前立即授权P0代码/协议/零物理replay。P1真实小批需A5审查、Lead新GO；P2/P3需前阶段验收和新的分批GO。**