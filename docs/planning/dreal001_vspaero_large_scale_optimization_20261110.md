# D-REAL-001｜Concorde 12维 VSPAERO 大规模真实求解器在环气动优化计划

**日期：**2026-11-10。**状态：**Owner 最新授权真实VSPAERO大规模优化；本文件是待工作机执行的中文任务合同，**并不是已经产生新的气动计算或优化结论**。

**关联**：[Issue #8](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/8)真实评价器/路线A/B/GPU；[Issue #4](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/4) VSPAERO物理门禁；[Issue #7](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/7)保留MAML S1/S2/S3负结果。新计算分支`research/dreal001-vspaero-optimization`从已提交集成版`research/dnext001-integration@1cfaf43143ae585a67216e09f61f35b3d7d18578`开始，所有旧run、PR #3/#6与main保持原样。

## 一、预算授权：取消低额度硬上限，改为科学门禁+批次记录

负责人新决策“放开工作机预算限制、进行较大规模的真实气动优化验证”正式生效：本轮不再受旧Tier0≤6次、固定任务试点≤12次和旧A类总20次限制。旧14/20已使用、剩余6次`CLOSED`的历史事实保留不结转；新轮次另立唯一`authorization_id/run_id`并独立记账。

**本轮本地VSPAERO真实启动总次数不再设置预先固定的上限**；允许根据实际资源、误差收敛与多种子重复试验扩大到数千/数万次真实启动。每个实际提交的有限批次必须提前列明`case_id/算法/B/seed/所需启动/超时/重试/资源/科学停机条件`，并由Lead登记、A5核对。P0/P1通过后，Lead可依据本授权自动逐批推进P2/P3，**无须每批另请Owner批准**；任何失败/越界及时暂停对应设置而非无限重跑。禁止付费云计算、未知机器资源、后台无界循环或擅自修改已冻结实验配置。RCAIDE气动回退/Mission与WaveDrag继续`LOCKED`。

## 二、物理科学边界：真求解器计算不等于真实整机燃油

VSPAERO7.2.2薄面势流在Mach2.02主翼有内部可重复的`CL/CDi`，但`LF-M2.02=NOT_VALIDATED`、机身/翼身阻力`BODY-CORR=BLOCKED`、高保真`HF=PARTIAL`。不能用内部`CDo/CDtot`直接宣称整机真实阻力、航程或油耗收益。项目需要以**三层结论**分别报告：
1. `SOLVER_LOOP_VERIFIED`：真实OpenVSP几何→VSPAERO→系数解析→统一评价→优化器ask/tell全过程实际执行、完整计费。
2. `INTERNAL_AERO_OPTIMIZATION_GAIN`：同工况、同升力的翼面模型内部诱导阻力改善，经过加密网格/尾迹和重复性复核，报告不确定性；只能作为模型内部结论。
3. `EXTERNAL_PHYSICS_SUPPORTED`：独立理论/合格CFD/公开实验在同几何、同参考量与可比物理量支持；否则`NOT_VALIDATED`。`fuel_burn_kg`在整机阻力、CG/质量、推进和Mission接口真正验证前为`null`。

## 三、设计对象、任务和主优化目标

- 维度固定12：`W01–W10,V01–V02`，机身`F01–F03`固定。原`design_space_12d_lifting_surfaces.yaml`的`frozen:false`意味着数值边界仍待冻结；工作机先提交独立`design_space_freeze.json`，核对每维范围、几何合法性、主翼扭转、垂尾实际进入求解器的情况及12维扰动效应。
- 巡航候选`Mach2.02、18288m、3028020m`；136000kg为单巡航进入质量，184880kg为另一个几何模型质量定义。`X_ref=16.821978m`是机翼AC而非全机CG(几何报告28.287395m)。未冻结质量CG前，不使用CM推导配平/静稳定，不做实际燃油结论。
- **主目标优先定义为同升力下的真实求解器翼面诱导阻力**：`min D_i(x,α)=q(M,h)×Sref(x)×CDi(x,α)`，`L=q×Sref(x)×CLtot`需匹配同一VSPAERO模型内的**基准翼面升力`L_ref`**；提前指定升力误差、网格、α范围及几何约束。α搜索引发的每一次真实VSPAERO启动都必须计入solver-start公平预算。W01更改Sref时不得只比CDi系数，必须报告N量纲力值和各设计对应的L、Sref、q。若固定α而未保持L，报告只能叫`fixed-alpha`响应优化。
- 由于旧模型主要是“12D主翼”的thin求解，V01/V02垂尾可能没有真实输出敏感性。若两个变量未影响VSPAERO实际气动量，先将其标`10D_ACTIVE_PLUS_2_INACTIVE`并据此解释结果；不得暗称所有12维均得到有效优化。补入垂尾后需重验求解器和维度。
- 没有可行解、几何无效、主系数NaN/Inf、尾迹不收敛、升力/参考状态不一致、超时，均记录为`INVALID/NO_FEASIBLE/NOT_CONVERGED`，不可用惩罚数值伪造真实目标；已知派生`Ew=Inf`只能在预先登记白名单情况下不阻断主系数验证。

## 四、阶段与放行条件（不再按低次数逐次找Owner审批）

**P0：工程冻结/零物理预检。** A1冻结TaskSpec、几何参考系、翼面/垂尾效应、VSPAERO版本/配置、升力目标；A2在mock/历史replay上验证真实计算记账、BO/DE/PSO接口/缓存、真值与代理预测隔离；A5复核。`P0_PASS`前不得打开大规模真实试验。
**P1：数值与物理合理性基础实测。** 按Issue#4现有I-01… I-06进行真实重复性、12→24→48面元密度、12D尾迹设置、α±符号、Mach 1.8/2.02/2.2与CL-α扫描，并完成12变量的单变量效应探针。先小批次、单因素；不设置“仅6次”的强制终止，但任何设置族主系数异常/数值发散/未达到预注册收敛阈值应停该族整改。P1 A5签`SOLVER_INTERNAL_PASS`后允许P2。
**P2：真实优化pilot。** 预算`B=64,128`、每臂≥3个预先固定优化seed，对普通BO、DE、PSO，以及A热启动对应的A-BO/A-DE/A-PSO进行真实solver-in-loop，同样升力/约束、同样solver调用记账。B元采集尚为`NOT_READY`，仅在代码审查/合成性能及holdout防泄漏通过后纳入。若出现明显伪改善、变量无效、频繁失败、收敛异常，先停后修；不能把pilot失效扩为数万次。
**P3：放开规模的真实正式对照。** P2科学门禁通过后自动允许`B=128,256,512`，至少5个独立优化seed，每方法同等solver预算；示意规模7方法×5 seed×(128+256+512)=31,360次真实**评价请求**（配平搜索会增加真正求解启动次数）。这是研究量级示例而非固定新上限、也非已执行数量；依据单次消耗、方差、置信区间与数值有效性调整有限批次，不按结果好坏事后调整主比较。将`B=16/32/64`早期样本效率作为补充，并报告各算法初始点、评价命中与多样性。
**P4：优胜候选复验。** 基线、各方法代表解与所有前沿最优候选重新用密网格/不同尾迹配置、重复求解，并与**同几何同Mach同参考量的独立理论或按需SU2**限定对比；压力阻力≠诱导阻力，SU2 Euler非真实整机总阻力。排名差异若小于数值误差则结论`NO_EVIDENCE/NUMERICALLY_INCONCLUSIVE`，禁止宣称获得改进。

## 五、并发与硬件防失控

- 本地9950X 16C/32T、系统内存约32GB、RTX5060 8GB；VSPAERO真实并发以1/2/4/8进程小样本实测选择有效吞吐，GPU用于经过CUDA数值审查的代理批量打分；不能擅自按32逻辑线程开32个求解器而造成内存/线程争用。
- 所有批次设定有限`max_cases`和`max_retries`及单案例超时；同配置连续两次异常即停止该假设并排查；资源温度/内存/磁盘压力超限、输入/输出hash不一致、主系数异常、求解设置变化未重冻结、精度/预算误差一律停。
- 主真实预算单位是`physical_solver_starts`（包括α搜索、超时及必要重试），同时记录`unique_design_evals`和`cached_reads`，不得给元学习臂免费真实支持标签。使用不同seed和模型时需对统计单位与重复历史评价披露；所有方法均不得使用未授权的真实Mission和虚构物理标签。
- 重新启动计算必须识别已完成case并加载原始checksum，避免系统重启导致重复算例、漏算和预算失真；不覆盖旧P1–P4资料、不合并main/PR#3/#6。

## 六、A/B路线、角色与科研结论

- 路线A：元学习仅负责优化器无关`WarmStartSampler`的采样初始种群/起点；BO/DE/PSO后续搜索与采样器分离。旧合成任务A热启动普遍负结果必须保留。若用合成训练代理迁移到真实固定Concorde，标`SYNTHETIC_TO_REAL_TRANSFER`，不能把单固定任务随机seed冒充真实多任务MAML。
- 路线B：元采集策略目前只有合成原型`NOT_READY`，不提前进入真实比较；一旦通过预先定义的策略验证与A5检查可添加普通BO和B-BO，并按2×2因子实验区分热启动主效应与学习采集主效应。**不因为宽预算就允许未通过评审的策略污染大规模真实结果**。
- Lead负责授权与有限批次调度、原始日志/总账/中文GitHub回执；A1负责几何/真实VSPAERO与数值门禁；A2负责BO/DE/PSO与A热启动公平优化；A3负责路线B和任务间统计/风险诊断；A4负责CPU/GPU吞吐、检查点、输入/输出SHA及可重绘中文图；A5负责独立P0/P1/P2/正式结果科学复核。A5可因非物理/失败停止任何正式批次；不得自审。
- 主要终点：`best_valid_Di_N`、`ΔDi_N`、`lift_residual_N`、`first_feasible_solver_start`、各B下`anytime_best_valid_Di`、`valid_solve_rate`、`solver_starts/CPU-hours`、数值收敛误差与跨seed配对CI；任务级/seed统计与多重比较预注册。结果再好也不能以翼面VSPAERO诱导阻力改善替代整机燃油收益。

## 七、必须交付的中文结果

至少有①基线/优化后12D几何图②基线与最优的实际VSPAERO CL/CDi/力值/同升力残差③各优化器真实solver次数-目标收敛曲线④独立网格/尾迹/重复性验证⑤失效与硬件吞吐⑥MAML热启动多样性/算法差异⑦物理验证门禁结论；任何未执行的图标`NOT_RUN`而不伪造。
每个真实case至少记录`run_id/task_id/design_set/x12/geometry_sha/solver_version/ref_units/grid/wake/alpha/objective/constraints/status/physical_solver_starts/git_sha/input_sha/output_sha`。规范文件`approval.json/run_config.json/solver_attempts.jsonl/evaluations.jsonl/optimization_history.csv/metrics.csv/numerical_validation.csv/summary.json/data_manifest.json/SHA256SUMS.txt/figures/*.png`，原始`.vspaero/.polar/.history/.vspgeom`另存不可变目录并提供bytes/SHA256；大文件不能推送时列外置路径且如实披露GitHub复现限制。
最终报告**必须分别给**：①软件闭环结论；②VSPAERO内部气动优化是否改善及数值不确定性；③外部物理验证是否支持；④MAML对BO/DE/PSO是否实际提高同预算样本效率。允许`NO_EVIDENCE/FAILED`，不得迎合预期。
