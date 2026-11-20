# D-REAL-EXP-001｜扩大 Concorde 真实气动数据与元学习优化验证——全量原始结果同步 GitHub（2026-11-20）

**任务状态：负责人已明确授权启动新阶段，按分批科学门禁执行。** 当前仅提交计划与代码开发要求；新物理 solver 启动必须遵守独立预注册/有限单批GO，不复用24/24已经耗尽的旧`AUTH-DRECOVER001-R2-20261120-01`。

本计划为[新执行Issue](https://github.com/QingYangJin/RCAIDE_Supersonic/issues)的详细合同；上游[Issue #12](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/12)是恢复与历史回执，[Issue #11](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/11)是跨任务MAML科学技术合同；本计划专门管理**扩容、新数据、真实反馈优化、与GitHub原始文件上传**。在两个旧Issue上只添加一次链接，不重复刷回执。新集成分支`research/dreal003-expanded-aero-meta-20261120`从恢复分支`5e85c74587bde97a1b3f7fb2e1ade24b8dafee22`创建；子智能体各自独立worktree；不动`main`/PR#3/PR#6/历史实验。

## 1. 必须记住的真实前情

- 2026-11-20 R2真实VSPAERO：`24/24 physical_solver_starts_actual`、`645 internal_solver_cases_actual`、`23完成/1超时`、`0 retries`、`parallel=1`；包含先前3次pilot及后续matrix/repair，11月20日旧授权已用尽。
- 生成10张本地字节核查证书，去重后**9条`LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`标签**；4个物理任务：Mach1.6(train,2)，Mach2.02(train,3)，Mach1.8(val,2)，Mach2.4(test,2)。
- K=1 FOMAML已真实执行1次，`12D→32→32→1`、20 outer steps、2 train任务、val/test各一query；验证集相对误差9.58%（零适应9.01%，更差），测试集48.19%（零适应53.11%，仍很大），**不能宣称泛化、优化优势或物理验证完成**。
- `solver_runner.build_evaluation`仍使用基准`TASK_SPEC.q_pa`和`TASK_SPEC.mach`，非2.02工况下case_result会错报`CL_TARGET_OUTSIDE_POLAR`。本次9条证书从deck真实`Rho/Vinf`重新计算q，现存结果可以作探索报告，但原缺陷必须先修复。
- 新增`meta/real_training.py`在旧A5 repair冻结后加入，未经A5对**新入口**审查；旧A5为deepseek-flash单发只读dossier，仅对指定旧矩阵/修复范围有`PASS`，不表示全R1代码/新M2完整验收。
- **严重交付缺口**：当前GitHub仅有`docs/evidence/drecover001/real_maml_result_20261120.json`和报告/审查记录，**没有完整24次原始求解文件、全部batch账本和checkpoint的远端可取回副本**。旧工作机本地位置`D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/`；不能让这个单点再次发生不可追溯损失。
- 物理边界：`VSPAERO_INTERNAL_ONLY`、`LF-M2.02=NOT_VALIDATED`、`fuel_burn_kg=null`；只能解释同升力翼面诱导阻力`Di_N=q*Sref*CDi`的受限优化，不能宣传整机真实油耗最优或高保真CFD已验收。

## 2. 阶段 G0｜先解决缺陷并把已做的24次结果上传GitHub（不新增物理）

**这项是新真实计算的第一道硬门禁，优先于一切扩容。**

1. A1修复`solver_runner.build_evaluation`的`Mach/q`取值：来自当前`case`与冻结deck中的`Rho、Vinf、Mach、Sref、L_ref/CL_target`，禁止静默回退到基准`TASK_SPEC`；对Mach1.6/1.8/2.02/2.4设计非baseline单测，核实`CL_TARGET_OUTSIDE_POLAR`及真实`Di_N`结果、单位、失效/空值语义，保持已有9证书不被隐式改写。
2. A3对`real_training.py`、`RealAdmissionManifest`、模型训练/适应、任务级split无泄漏、真值证书状态作独立回归；补`K=0/1`与缺失/伪证书fail-closed，训练权重/标准化统计**只在meta_train任务拟合**。既有20步真实K1结果保留为`EXPLORATORY`，不偷偷改成正式M2。
3. A4立即检索工作机现存`D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/`，确认**不是找回旧F1R2/F2R2**。将本次仍存在的24次实际原始文件、case输入、`.vspgeom/.vspaero/.polar/.history`、日志、网格/尾迹文件、`batch_accounting.json`、证书和admission、所有失败/超时日志、`real_dataset_manifest.json`、模型checkpoint/训练曲线（若有）逐项建清单，**实际上传到GitHub可取回的研究分支/版本化实验目录**。不可只上传文件名、hash或本地绝对路径。
4. 用户要求完整真实输出：建议将每个`run_id`存储于`research/concorde_metaopt/optimization_runs/<new_or_existing_run_id>/`，下分`raw_cases/<case_id>/`、`inputs/`、`tables/`、`figures/`、`training/`、`audits/`；为旧24次保留其原`run_id`，仅新加远端同步manifest/commit，不改写原记录。文本`.polar/.history`、deck、JSON/CSV、可视化PNG可直接Git提交；二进制/超大原始文件需采用**Git LFS或可公开验证的GitHub Release资产**并在同一仓库保存**实际下载URL+字节数+SHA256+关联run_id/case_id**。禁止仅在`D:`盘存档或GitHub只提交LFS pointer而无实际LFS对象；不得上传令牌/隐私/机器凭证。所有可视化图须来源于真实 CSV/原始结果，不能制作占位图冒充结论。
5. 远端核验：Lead/A5使用**全新目录、从 GitHub 下载**该批次至少1个完整成功case及1个失败case的原始文件和账本；逐文件校SHA、重算`Di_N`、核对9条有效标签、14条NULL、24次starts/645 internal和费用总账；所有完整24次文件的远端可取回/缺失比例出`remote_raw_upload_audit.json`。若某些文件已确实不存在，标`CURRENT_RUN_RAW_LOST`，不得虚构，阻断其科学准入（不是要求找回历史F1R2）。
6. A5对修复后的**确切新SHA**重新审查：`G0_CODE_PASS`、`G0_REMOTE_RAW_RETRIEVAL_PASS`（可分开）；若不通过先修复再加物理。Lead不得用之前指定范围的`PASS`直接授权新代码。

**完成证据**：`github_upload_manifest.json`（原始SHA与remote URI）、`batch_accounting.json`、`admission_manifest.json`、`real_dataset_manifest.json`、`cases.csv`、`failed_cases.csv`、`figures/*.png`、中文`g0_audit.md`、A5复核，真实starts增加0。**已有24次新数据优先保全**。

## 3. 阶段 G1｜提升真实物理标签有效率与数值可信度（初步提议≤24次新物理starts）

**不可直接复制旧24批次参数**：上次24次仅9条有效，存在12次升力匹配未命中1e-3和基线无效/超时，先提高有效标签率。

- 预注册Mach、CL_target、q、参考面积、迎角搜索区间、迎角布点/局部细化、`NumWakeNodes/WakeIters`、网格族与重复性检查；以**真实求解结果原始行**为准，不能通过编造行、强行把未达到升力约束点插值成已匹配标签而提高比例。
- 对同一设计在不同进程重复、稀密网格、尾迹、参考量/坐标/CG做低成本辨识；记录`mesh_family`且处理历史不确定性；如发现同一输入重复几何网格翻转，停止扩大正式优化。
- 建议**首个G1有限新批次至多24次 solver starts**，由A5逐条预审、Lead使用**新的**`authorization_id/batch_id`签GO；不复用旧24/24 GO；GPU/CPU总核数、每case 120s（如不足经预审调整）、重试最多1/案、建议求解并发先1并验证后≤2；无前置复现不要盲目增加至16路。
- **扩容放行门**：按设计类型/任务分别报告有效/无效率和重复离散误差。建议稳定可用标签率≥70%（相对于旧9/24≈37.5%目标性提升，不是气动物理通过证明）；若达不到，报告具体根因并调整新试验合同，不能直接奔向数百solver。
- 输出真实polar曲线/同升力插值/网格与尾迹敏感性/失败矩阵、raw SHA/账本/中文图表。新原始数据需随每个mini-batch推远端并确认。

## 4. 阶段 G2｜扩大真实 Concorde 多任务数据集（建议≤240次新solver starts；门禁后放行）

- 保持12维几何的W01–W10/V01–V02定义及固定机身；从Mach、高度、CL_target等能**实际进入VSPAERO求解输入和约束**的条件构建新`TaskFamily`。不将同一工况不同seed/仅任务标签变化视为新的物理任务；Mach2.4等超出当前适用域必须先校核。
- 初步目标**至少8个物理可区分任务**：建议≥4 train、≥2 validation、≥2 heldout test。每个任务争取≥8–10个有效独立设计，其中至少K=5 support + ≥3 query；**数量是科研目标而不是已取得的样本事实**。据G1实测有效率决定每任务真实starts预算，先meta_train、再meta_val，**测试任务只按冻结计划采集，不能用于调参**。
- 独立可行设计DoE与边界探索：Sobol/LHS＋低覆盖区域补采样，明示设计x的几何真实性、任务条件与标签，不只围绕既有2个训练设计重复评价；避免高维12D任务用1个support过度拟合。
- 建议按≤16–32 starts/mini-batch，**G2计划上限240新的solver starts**，每子批A5/Lead门禁（不必每批要求Owner重申研究方向）；这不是全项目总上限，需额外预算时提供新统计功效和物理能力理由，经新预注册后再追加。任何材料缺失、远端上传未完成或物理求解异常立即暂停下一批。
- A2/A3在真实标签数量满足基本分割后实际训练**FOMAML、普通预训练、条件上下文预训练（16D）、随机/常数**。报告K=0/1/3/5适应曲线、MAE/RMSE/任务级差异、预测校准、训练墙钟、元训练/训练任务数、GPU/CPU精度成本。真实训练前请A5审核训练入口及每个标签真实SHA；真实标签不足时仅报告不足、不造假。

## 5. 阶段 G3｜真实反馈优化与路线A/B对照（建议≤384次新solver starts；门禁后启动）

1. **先完成至少一条**真正的BO或DE`ask → actual VSPAERO → tell`轨迹，反事实更改反馈应能让后续搜索点改变；旧固定设计批次不能冒充优化。
2. 后续对照：在同一个冻结工况和评价预算下对比至少Random/Sobol初始化BO、Pretrain-Kshot-BO、FOMAML-Kshot-BO；路线A若软件/样本及A5门禁通过，可并行比较DE和PSO随机/MAML热启动，但重点先回答**MAML是否真正减少物理评价次数**，不是同时堆叠所有算法。
3. 对真实优化的初始`K`个support、全部初始化种群、失败重试/修复、后续真正评价统一计费；模型预测不能冒充真值。B=32/64/128候选预算由实际吞吐和G1物理门禁决定，**不得把多个算法的共用真实数据算免费先验**；真实每个arm 1–3 seed的实际规模由预注册功效/成本方案锁定。初步G3规划≤384新starts仅用于逐批有限GO的计划容量，**不是立即无条件允许一次性384次启动**。
4. 路线B“元BO采集策略”仍独立于路线A初始选点：须先在真正未见的任务上用普通采集对照证明轨迹数据和策略无泄漏，再在资源允许时进行A×B二因素实验；不能因B模块未就绪长期阻断真实FOMAML路线。
5. 主要端点：`best_feasible_Di_N`，`first_feasible_eval`，`feasible_hit_rate`（分清每点可行率/每次运行是否找到可行解），`gap/reference`（基准若可信），anytime曲线、设计差异、真实solver starts总成本与运行时间；失败/不收敛`null`，不通过物理门禁则不报“优化赢家”。
6. M3正式迁移采用≥2个未见任务并先冻结split；以任务为一级统计单位，配对比较并报告置信区间/负迁移。不可对test任务重复调超参至好看。仅1个test query不能证明泛化。

## 6. 每次真实分析和试验结果的**强制 GitHub 同步合同**

> **Owner明确要求：本次起任何可称为“完成”的真实气动计算和优化实验都必须有可从GitHub取回的原始文件及再绘图数据。文件不上远端=不可远端验收，不得以本机绝对路径/仅Issue文字/仅manifest替代。**

每一`run_id/batch_id`保存：
- `raw_cases/<case_id>/`：实际OpenVSP模型`.vsp3/.vspgeom`、`.vspaero`输入、`.polar`、`.history`、`.lod/.adb/.adb.cases`（若分析需要/实际生成）及求解stdout/stderr、exitcode、网格/尾迹配置、工况deck、超时/失败原件；不能只保存“成功”的案例。大文件可按`raw_bundle.tar.gz/zip`上传Git LFS或GitHub Release，并以manifest逐case寻址；任何压缩包必须可远端真实下载且可逐SHA复核。
- `tables/`：`all_evaluations.csv`、`actual_solver_ledger.csv`、`admitted_labels.csv`、`failed_or_null.csv`、`optimization_history.csv`、`training_history.csv`、`statistics.csv`，包含x12、工况、单位、算法、seed、K/B、约束和真实/拟合来源。
- `figures/`：中文标题/图注的`CL-α`、`CDi-α`、同升力`Di_N`、mesh/wake、失败占比、设计变量分布、优化anytime曲线、K-shot误差/训练损失、算法对照及GPU成本/精度；每图附`figure_data.csv`与生成脚本，**无真实数据的不画占位图**。
- `metadata/`：`run_config.json`、`task_family_split.json`、`geometry_freeze.json`、`admission_manifest.json`、`batch_accounting.json`、`source_sha/code_sha/environment.json`、`data_manifest.json`、`SHA256SUMS.txt`、`upload_receipt.json`、A5 verdict；标注`VSPAERO_INTERNAL_ONLY`及未验证全机油耗的科学口径。
- **上传频率**：建议每次完成≤8个solver starts或每≤60分钟作为最大片段，较早者到达即上传并检查；**mini-batch远端上传并经hash/readback确认后，才能释放下一批次GO**。未联网时保留原件、暂停下一批，不能待全部几百次算完后才统一上传。
- **可恢复性**：由A4实际创建新的空目录，仅通过GitHub链接/clone+LFS pull或Release URL取回至少一成功、一失败case以及任意一训练checkpoint，逐SHA核对并用解析器重算气动力/指标，保存`remote_download_recheck.json`。如果LFS quota/Release下载或仓库大文件限制阻断，立即停止新大批并给出可执行方案；用户可通过GitHub读到结果，不是只看本地证据索引。
- 不保留云服务token、访问密钥、个人路径的敏感内容在Git；历史失败结果和负性能如实保留；无异机备份的过去豁免并非禁止GitHub上传，**本次GitHub同步是强制交付要求**。

## 7. 组织责任与最终交付

| 角色 | 当期任务 |
|---|---|
| Lead | 本Issue唯一主进度与阶段批准，逐批`approval/GO`、业务资源、commit/分支审核，确保旧24批次已上传再启动新批；每阶段**一条**中文可审计回执 |
| A1（气动/几何） | per-case Mach/q修复、VSPAERO参数/网格/尾迹/同升力物理核查、新多任务真实计算和raw产物 |
| A2（优化器/算法A） | BO/DE真实反馈、预算和缓存、MAML优化器无关热启动、多算法随机/预训练/MAML公平实验 |
| A3（真实元学习/路线B） | admission与真实TaskSpec/split、新真实FOMAML和条件预训练/Kshot、B元采集策略独立验证 |
| A4（数据工程/GPU） | GitHub真实原始结果推送、LFS/Release或小文件策略、manifest与远端新目录恢复、CSV/PNG可重绘、CPU/GPU计时 |
| A5（独立审查） | 对确定源码SHA审计q/Mach、真实准入、物理条件、计费/数据泄漏、原始上传读回和统计；签`CHANGES_REQUIRED/PASS_WITH_DISCLOSURE`，不能替代为“代码测试通过” |

**分阶段交付门禁**：G0新代码+旧24次可远端复核；G1真实标签产出率/物理设置可靠；G2跨任务真实标签数量、train/val/test与真实训练；G3真反馈优化、多算法和M3统计。任何负收益均可结题为`NO_EVIDENCE/NEGATIVE_TRANSFER`而不强求模型获胜。

当前本计划仅为下发执行合同，**尚未代表新阶段求解已运行、数据已上传或计算结果已通过**。接到Issue的工作机应提交第一次“接单+修复+旧24次数据上传能力”回执，明确新G1的冻结批次数与预计物理适用性。