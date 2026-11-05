# D-12D-006 A5：最小 VSPAERO 验证矩阵与可信度审查

- 任务：task-193（D12-A5 独立审查 + 最小 VSPAERO 验证矩阵，零求解）
- 工作树：<repo-d12d006> @ aef2cb71e07aa28abfc28e34b14bf9dc1579c2e3（分支 research/d12d006-aero-improvements；只读）
- 审查对象：D-12D-005 归档 run d12d005-20261104T0430Z 的 14 次 A 类 VSPAERO 7.2.2 执行、A1 零求解审计、A2 全量 14/14 只读重算、D-12D-006 授权与 A4 门禁矩阵
- 审查方式：只读静态审查 + 既有证据解析；physical_call_count = 0；solver_starts = 0；未改仓库、未 commit/push、未做 GitHub 写操作
- 日期：2026-11-05；审阅人：A5（a5-code-reviewer）
- 路径占位：<repo>=RCAIDE 主仓库根；<repo-d12d006>=D-12D-006 工作树根；<EXT>=外部记忆根（.../d12d006）。本入库副本仅将机器绝对路径替换为占位，数值/结论/哈希未改；外部原件 sha256 a0684638… 保留于 EXT。

## 0. 结论摘要

**verdict = MATRIX_READY_FOR_OWNER_BUDGET_REVIEW；本文件不构成任何求解授权。**

1. **solver_internal_valid = CONDITIONAL_PASS（有限范围）**：14 次 A 类执行的“合同 → 执行 setup → 求解器回显 → .polar/.history → 矩阵/报告”链路可复核；A1 审计 513/513 文件双形态 SHA、40/40 v1 manifest、37 项 external 全部匹配；A2 对全部 14 案 226/226 项系数逐位一致（最大绝对差 0 ≤1e-12）、148/152 派生自检无 FAIL、75 项归档 deltas 71 PASS+4 非有限解释；14/14 polar 与 9/9 关键 JSON 双哈希链匹配；A5 既有探针亦对 14 案 polar/矩阵/结果 JSON 做过 0 差复核。该通过只证明“同一求解器、同一设置、同一归档内的内部一致”，不证明物理正确。
2. **external_physics_validated = NOT_VALIDATED / 当前 A 类不可达**：现有证据没有风洞、飞行试验、独立 CFD 或带黏性/激波/机身的参考解；VSPAERO 为 thin-LF VLM，CDo 是内部寄生项而非真实阻力，CDtot 不得当作整机阻力/燃油目标；LF-M2.02 维持 **NOT_VALIDATED**，BODY-CORR 维持 **BLOCKED**。
3. **A 类预算现状**：已用 14/20，剩余 6 次 **CLOSED / NOT_AUTHORIZED / 不结转**；B 类 RCAIDE LF 0/12、C 类 SU2 0/4 **LOCKED**。本矩阵提出的 10 次 A 类新启动上限（Tier 0 六次 + Tier 1 四次）属于**新封顶预算建议**，必须 owner 书面批准后才可启动；批准前一次也不得运行。
4. **最小矩阵的核心判断**：现有内部证据足以支持“CL/CDi 同工况趋势可比较”，但不足以支持“物理阻力/燃油/配平/静稳定/CG 结论”；需要先做 6 次 Tier 0（重复性、密度收敛、12D 尾迹、符号）关闭内部数值缺口，再决定是否批准 4 次 Tier 1（12D 迎角/马赫趋势）。外部物理验证另需 C 类 4 次，当前 NOT_AUTHORIZED，且即使执行也不能单独把 CDtot 变成真实阻力。

## 1. 既有证据基线与可信度判定

### 1.1 14 次执行的内部一致性（已复核）

| 证据 | 内容 | A5 判定 |
|---|---|---|
| A1 零求解审计 | 14 案合同/执行/回显/极线 5 层一致；513/513 文件 raw+canonical、40/40 v1 manifest、37 项 external 全匹配；14/14 矩阵与原始 polar 一致 | PASS（证据链）；CG-01/CG-02/sign 另列 |
| A2 全量重算 | 14/14 案 226/226 系数 PASS（Batch1 52、Batch1b 30、Batch2 144；最大绝对差 0）；148/152 派生自检无 FAIL；75 项 deltas 71 PASS+4 非有限解释；polar 14/14、关键 JSON 9/9 双哈希；physical 0 | PASS_WITH_DOC_FINDINGS（14/14；Z-01 关闭；DOC-A2-01 minor） |
| A5 既有探针 | 14 案 polar vs evaluations、矩阵 vs 结果 JSON 均 0 差；预算 14/20、retries 0 | PASS（抽查口径） |
| 既有资源 | 14 starts；总 wall 50.246 s；单次最大 28.314 s；最大 RSS 3.493 GB；batch2 8 次总 9.846 s、单次最大 1.762 s、RSS 0.294 GB | 有界，可作新预算资源基线 |

### 1.2 现有内部数值缺口

| 缺口 | 现有证据 | 为什么是缺口 |
|---|---|---|
| 重复性 | 只有 B2-07 对 B2-03 一对重复：ΔCLtot = -8.3383e-8、ΔCDi = -8.87105e-7、ΔCDtot = -8.86799e-7 | 单对不足以估计噪声分布/离群；不能支撑“重复性已验证”的统计表述 |
| 密度收敛 | B2-01/02/03 为 SectTess_U 3/6/12：3→6 CL +2.4372%、CDi +2.4279%；6→12 CL -2.7033%、CDi -2.6939% | 12→更细网格仍可能变化；无 24/48，不能判“网格收敛”，只能判“同网格内部趋势” |
| 尾迹 | 标准翼 S3 vs S4（NumWakeNodes 8→128）ΔCL -7.3568e-8；12D 生产案只用 8 | 12D 几何未做尾迹敏感性；不能把标准翼结论直接外推到 12D |
| 迎角 | 标准翼 S0/S3/S6 为 2°/2°/1°；12D S5/B2 均 2°（单点） | 无同几何多点，不能检验 CL-α 线性/斜率，也不能识别“单点巧合” |
| 马赫 | 标准翼 M0.1 与 M2.02；12D 只 M2.02 | 无同几何马赫扫描；不能判跨马赫趋势是否合理 |
| 符号/坐标轴 | A1 §4.6 判 PARTIAL / NOT_ESTABLISHED；无独立符号约定文件 | 只能证明字段一致，不能证明 X 轴/升力/阻力/CM 正方向符合项目约定 |
| CG/质量 | CG-01：X_cg=16.821978259514246 为机翼 AC，不是全机 CG 28.287395109126685；CG-02：136000 kg vs 184880 kg/OEW 78700 kg | CM 不能用于配平/静稳定/CG；质量归一化/燃油/航程不可混用 |
| 外部物理 | SU2 0/4 LOCKED；无风洞/飞行数据；无机身/垂尾 | thin VLM 不含厚度、黏性、激波、边界层、翼身干扰；CDo/CDtot 非真实阻力 |

### 1.3 内部有效 vs 外部有效（定义）

- **solver_internal_valid**：同一求解器/版本/设置/几何/合同下，输入输出可追溯、可解析、可复现，主系数满足代数恒等式，且对数值设置（网格/尾迹/重复）有界。它回答“算得稳不稳、能不能在同一工况内比较”，不回答“算得对不对”。
- **external_physics_validated**：与独立物理参考（风洞/飞行试验/经验证的 CFD）在声明的不确定度内一致，并覆盖真实几何/黏性/压缩性/机身干扰。它回答“能不能用于真实阻力、燃油、配平、静稳定或适航级结论”。
- 本矩阵的 Tier 0/Tier 1 全部只服务 **solver_internal_valid**；只有 E-01 服务 **external_physics_validated**，且 E-01 当前不批准。

## 2. 物理假设与适用边界（矩阵的前置条件）

1. **模型**：VSPAERO 7.2.2 thin-surface VLM；主翼薄面（vkey thick=0、plate=3），仅 main_wing_C，两片半翼、无控制面；solver Symmetry=0，几何已全展；无机身、垂尾、翼身干扰 → lifting-surfaces-only。
2. **压缩性**：M2.02 为超声速线性薄翼近似；参考量可用 Ackeret/线化理论做量级检查，但真实 Concorde 双三角/OGV 的激波、黏性、厚度、配平阻力不在模型内。
3. **阻力**：CDo 是 VSPAERO 内部寄生项，不是 skin-friction；CDtot 不是真实整机阻力；Ew=inf 是 CDiw=0 的 0/0 派生伪影，不是发散。
4. **参考量**：12D 合同 Sref=358.25 m²（暴露面积，不是浸润面积 717.57475）、Cref=18.489893 m（MAC）、Bref=25.604638 m、X_cg=16.821978259514246 m（机翼 AC）、ReCref=89.3970058767656e6、V=596.0373972278921 m/s、rho=0.1153178340089936 kg/m³、q=20483.94 Pa。
5. **质量**：136000 kg（p1p3）与 184880 kg（geometry-check）/OEW 78700 kg 两套口径未统一；本矩阵不做质量归一化、燃油、航程、推重比结论。
6. **设置**：尾迹 NumWakeNodes=8、WakeIters=5、WakeRelax=1、FarDist=-1；任何单因素变更必须记录为不同状态，不得与基线混算。

## 3. 最小验证矩阵

> 启动上限是“最多允许次数”，不是承诺执行次数。每案单次失败不得自动重试；所有重跑都计入上限。资源为计划上限，依据既有 28.314 s / 3.493 GB 峰值留余量；实际以 runner 硬超时为准。

### 3.1 零求解前置（0 次启动）

| ID | 验证问题 | 交付/判据 | 预期判断 | 启动上限 | 资源 | 停止条件 | 类别 | 状态 |
|---|---|---|---|---|---|---|---|---|
| Z-00 | CG-01/CG-02/符号/合同是否先冻结？ | 书面冻结“X_cg=机翼 AC 为工程约定”或“用全机 CG 重建合同”；质量基线二选一并写入 TaskSpec；坐标轴/力/CM 符号约定独立文件 | 未冻结前，CM/质量/配平结论一律禁止；矩阵 Tier 1 不得解释 CM | 0 | 0 | 未冻结 → 不启动任何新求解 | not_applicable | 待 owner/A1/A4 |
| Z-01 | Batch2 八案是否独立重算？ | A2 扩展：B2-01..07 六项主系数 + 恒等式，容差 1e-12；0 物理 | 14/14 与归档一致才可进入 Tier 0 | 0 | 0 | 任一不一致 → 先查归档，不启动 | solver_internal_valid（零求解） | A2 已完成全量 14/14（226/226 系数、14/14 polar、9/9 JSON；0 物理）；PASS_WITH_DOC_FINDINGS，Z-01 关闭 |

### 3.2 Tier 0：内部数值闭合（6 次启动，必须先全部通过）

| ID | 物理假设/验证问题 | 构型/单因素（相对基线） | 参考量与判据（PASS/FAIL） | 预期判断 | 启动上限 | 资源上限/次 | 停止条件 | 类别 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| I-01 | 同一 12D 基线在相同合同下是否数值可重复？ | B2-03 基线（SectTess_U=12、M2.02、AoA=2°），再加 2 次同配置 | 3 次两两比较：max abs(ΔCLtot) ≤ 1e-5、max abs(ΔCDi) ≤ 1e-5、max abs(ΔCDtot) ≤ 1e-4；代数恒等式仍成立 | 预期 PASS（现有单对 ~1e-7/1e-6，约为阈值的 1/10） | 2 | 4 threads；≤900 s；≤4 GB；≤20 MB | 超阈值或非有限 → REPEATABILITY_FAIL，停 Tier 0，不补跑 | solver_internal_valid | 现有 1 对，不足 |
| I-02 | 12D 主翼网格 12→24→48 是否收敛？ | B2-03 基线，SectTess_U 24、48 各 1 次（现有 3/6/12） | 12→24 与 24→48：abs(ΔCL)/CL ≤ 0.5%、abs(ΔCDi)/CDi ≤ 1%；且后一步相对变化 ≤ 前一步的 0.75（单调收敛） | 预期 PARTIAL/PASS；若 24→48 仍 >0.5%/1% 则判 NOT_CONVERGED | 2 | 4 threads；≤900 s；≤4 GB；≤20 MB | 48 仍不收敛 → 停，不再加网格；不得把 12 结果称“网格收敛” | solver_internal_valid | 现有 3/6/12，未收敛 |
| I-03 | 12D 几何对尾迹节点数是否敏感？ | B2-03 基线，NumWakeNodes 8→128，其余不变 | abs(ΔCLtot) ≤ 1e-4、abs(ΔCDi) ≤ 1e-5；history 迭代有限、无 parser 失败 | 预期 PASS（标准翼 S3/S4 差 7.36e-8，但 12D 未验证） | 1 | 4 threads；≤900 s；≤4 GB；≤20 MB | 超阈值 → WAKE_SENSITIVE，停；不得用 8 节点结果做跨案比较 | solver_internal_valid | 12D 未做，标准翼已有 |
| I-04 | 对称标准翼的升力/阻力/力矩符号是否随迎角反号？ | 标准翼 S0 构型（M0.1、Sref4/Cref1/Bref4），AoA=-2° 1 次；现有 +2° | CL(-2) ≈ -CL(+2) 相对差 ≤2%；CDi(-2) 与 CDi(+2) 相对差 ≤5%；CMoy 反号；主系数有限 | 预期 PASS（几何对称）；只验证符号一致性，不验证轴方向 | 1 | 4 threads；≤300 s；≤1 GB；≤10 MB | 不反号/不对称 >5% → SIGN_CONVENTION_FAIL，停并升级 Z-00 | solver_internal_valid（仅符号） | 现有仅 +2° |

**Tier 0 通过判据**：6 次全部 PASS 或仅 I-02 判 PARTIAL 但 24→48 变化 ≤0.5%/1%；否则停，不得进入 Tier 1。

### 3.3 Tier 1：物理合理性检查（4 次启动，需 Tier 0 通过 + owner 书面扩额）

| ID | 物理假设/验证问题 | 构型/单因素（相对基线） | 参考量与判据（PASS/FAIL） | 预期判断 | 启动上限 | 资源上限/次 | 停止条件 | 类别 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| I-05 | 12D 主翼 CL-α 在 M2.02 是否呈线性、斜率是否落在薄翼理论量级？ | B2-03 基线，AoA=0°、4° 各 1 次；现有 2° | 0–2–4° 线性拟合 R²≥0.99；斜率 ∈ [0.03, 0.045] CL/deg（Ackeret 2D 0.039777、有限翼 3D 一阶 0.033671；现有 S6 1° 为 0.037164）；CL 单调 | 预期 PASS；若斜率越界，判 SOLVER_ANOMALY，不判“物理无效” | 2 | 4 threads；≤900 s；≤4 GB；≤20 MB | 非有限/非单调/R²<0.99/斜率越界 → 停，报告为内部异常，不得外推 | solver_internal_valid + physics plausibility | 12D 仅 2° 单点 |
| I-06 | 12D 主翼在 M1.8/2.2 的 CL/CDi 是否连续、量级合理？ | B2-03 基线，Mach 1.8、2.2 各 1 次；现有 2.02 | 主系数有限；CL 相对 2.02 变化 ≤20%；CDi 随 Mach 变化方向与线化理论一致且在 2 倍因子内；无 parser/收敛失败 | 预期 PARTIAL：可能有限但只能作趋势；不得称跨马赫验证 | 2 | 4 threads；≤900 s；≤4 GB；≤20 MB | 非有限/CL 变化 >20%/CDi 反向且超 2 倍 → 停；不得用 2.02 单点代表全马赫 | solver_internal_valid + physics plausibility | 无同几何马赫扫描 |

**Tier 1 通过判据**：只把 12D M2.02 的 CL/CDi 内部趋势从“单点”提升为“有迎角/马赫邻域支撑”；**不改变 LF-M2.02=NOT_VALIDATED**。

### 3.4 外部物理验证（单独 C 类预算，当前 NOT_AUTHORIZED）

| ID | 物理假设/验证问题 | 参考 | 判据 | 预期判断 | 启动上限 | 资源 | 停止条件 | 类别 | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| E-01 | thin-LF VLM 的 CL/CDi 是否与独立物理参考一致？ | 同 12D 主翼的 SU2 RANS（C 类）或公开风洞/飞行数据；必须含机身/黏性/激波，否则只能比 CL | CL 相对差 ≤10%；CD（若参考含黏性/激波）相对差 ≤20% 或 ≤20 counts；压力分布趋势一致；需独立不确定度 | 预期 **FAIL/PARTIAL**：无黏 thin VLM 无法验证 CDtot；CL 可能部分通过 | 4（C 类；当前 0/4 LOCKED） | 4 threads（按 SU2 配置）；≤4 GB；≤3600 s/次 | 无参考、参考几何不一致、或 CD 差 >20% → 不得标 external_physics_validated；停 | external_physics_validated | NOT_AUTHORIZED |

> E-01 不是本矩阵 10 次 A 类预算的一部分。即使 E-01 全部通过，也只能在“同几何、同状态、含机身/黏性”的限定下声明外部验证；CDo/CDtot 仍不得直接当整机阻力目标。

## 4. 预算、分阶段与停止规则

### 4.1 建议的新封顶预算

| 阶段 | 内容 | A 类启动上限 | 前置条件 | 失败处理 |
|---|---|---|---|---|
| Stage 0 | Z-00 零求解冻结（Z-01 已 PASS） | 0 | owner/A1/A4 完成 Z-00；A5 复核 Z-00 | 未完成 → 不启动；Z-01 不再阻塞 |
| Stage 1 | I-01..I-04 | 6 | Stage 0 全 PASS；owner 书面批准 6 次新预算 | 任一 FAIL 即停；不自动补跑 |
| Stage 2 | I-05..I-06 | 4 | Stage 1 全 PASS；owner 书面扩额到 10 次 | 任一 FAIL 即停；不自动补跑 |
| E | E-01 外部参考 | 4（C 类） | 单独 C 类授权；不占用 A 类 | 当前 LOCKED |
| 合计 | A 类新启动 | **10（6+4，分阶段释放）** | 每次启动前记录授权号/合同/digest | — |

**与既有预算的关系**：A 类 14/20 已用，剩 6 次已 CLOSED/NOT_AUTHORIZED，**不结转**；本表 10 次是新封顶预算建议，不是对剩余 6 次的重新解释。若 owner 只批准 6 次，则只执行 Stage 1，Tier 1 不启动；不得用“剩余 6 次”名义绕过新授权。

### 4.2 全局停止条件（任一触发即停）

1. 无 owner 书面批准、无授权号、无冻结合同/digest → 不启动。
2. 合同/几何/SHA 与基线不一致，或 setup 回显与合同不一致 → 不启动。
3. 主系数非有限（Ew 除外）、48 列表头/解析失败、history 非有限 → 停当前阶段。
4. 单次超过 900 s 或 4 GB RSS → kill，标 INCONCLUSIVE，不自动重试。
5. Stage 1 任一 FAIL → 不进入 Stage 2；Stage 2 任一 FAIL → 停，不追加预算。
6. 任何测试试图解释 CM/配平/静稳定/CG、质量归一化燃油/航程、或把 CDo/CDtot 当真实阻力 → 立即停并判越界。
7. 同一条件重跑超过 1 次（基础设施失败除外）→ 超出最小矩阵，需重新审批。

## 5. A1 CG-01 / CG-02 对本矩阵的输入影响

### 5.1 CG-01（blocker，scope-limited）

- 合同 X_cg = 16.821978259514246 m 精确等于机翼气动中心 wing_ac_x_m；全机 CG = 28.287395109126685 m，差 -11.465416849612438 m。
- 因此 .polar 的 CMxtot/CMytot/CMztot 是绕**机翼 AC**的力矩，不是绕全机 CG；**禁止**用于配平、静稳定裕度、CG 冻结或质量-重心耦合结论。
- p1p3 报告 docs/reviews/p1p3_fullchain_validation_report_20261031.md:45 把该值标为“PROVISIONAL CG”属标签错误；本矩阵不接受该标签。
- 本矩阵仅 I-04 检查“符号是否随迎角反号”，不检查 CM 的物理配平含义；Z-00 必须先冻结参考点语义。
- 若改用真实 CG 重建合同，属于新合同 + 新求解预算，需 owner 单独授权；本轮不做。

### 5.2 CG-02（major）

- p1p3 报告 :44 使用 136000 kg；geometry-check baseline_geometry.json 的 mass_total_takeoff_kg = 184880.0、mass_operating_empty_kg = 78700.0。
- 两套质量口径不可混用；本矩阵不产生任何质量归一化、燃油、航程、推重比结论；Z-00 要求把质量基线写入 TaskSpec 后才可谈质量相关派生。
- D-12D-005 的气动系数本身不含质量，故 CG-02 不否定 CL/CDi 的内部趋势，但否定“用这些系数直接算燃油/航程”的做法。

### 5.3 符号/坐标轴（A1 §4.6，NOT_ESTABLISHED）

- 仓库无独立坐标系/力符号验收文件；A1 只能判 PARTIAL。I-04 只验证对称翼在 ±AoA 下的符号一致性，不能证明 X 轴指向、升力/阻力正方向或 CM 正负号符合项目约定。
- 在 Z-00 的符号约定冻结前，任何“升力为正/阻力为正/抬头为正”的物理解释都只能标 ASSUMED，不能写进验收结论。

## 6. 矩阵通过后能说什么、不能说什么

| 结果 | 可以说 | 不能说 |
|---|---|---|
| Stage 0 + Tier 0 全 PASS | 14 案证据链内部可复核；12D 基线重复性/密度/尾迹/符号在声明阈值内；solver_internal_valid=CONDITIONAL_PASS | 物理阻力已验证；CDtot 是真实阻力；CM 可用于配平 |
| Tier 1 全 PASS | 12D M2.02 的 CL/CDi 在 AoA 0–4°/Mach 1.8–2.2 邻域内呈合理线性/连续趋势 | LF-M2.02=VALIDATED；跨马赫/全包线已验证；可用于整机优化目标 |
| E-01 全 PASS（未来） | 在给定参考、几何、状态和不确定度下，CL/CDi 与独立参考一致（限定声明） | CDtot/整机阻力自动有效；机身/垂尾/配平已验证；无需 BODY-CORR |
| 任一 FAIL | 记录失败模式、停止阶段、已消耗启动；不得用剩余预算“刷到通过” | 把失败归因于物理而不排查数值/合同/设置；或把 PASS 子集当整体通过 |

**标签维持**：VSPAERO_INTERNAL_ONLY；LF-M2.02 = NOT_VALIDATED；BODY-CORR = BLOCKED；HF-M2.02 = PARTIAL（如 A4 门禁矩阵）；physical_validation = NOT_VALIDATED；approved_for_next_stage = false；lifting-surfaces-only。任何新结果不得覆盖这些标签，直到 E-01 + 机身修正 + owner 验收。

## 7. 与 A4 门禁矩阵、A1/A2 证据的对应

| 门禁/证据 | 当前状态 | 本矩阵关系 |
|---|---|---|
| GEO-12D | PARTIAL | Sref/Cref/Bref 与模型自洽；上游声明差异（exposed 326.5 vs 358.25 等）未解释；不因本矩阵变 PASS |
| LF-M2.02 | NOT_VALIDATED | 本矩阵只做内部/合理性，不改变；E-01 才可能触碰外部验证 |
| HF-M2.02 | PARTIAL | 与本矩阵无关；HF 仍需独立验证 |
| BODY-CORR | BLOCKED | 本矩阵不含机身/垂尾；Z-00/E-01 也不自动解锁 |
| MISSION-DATA | PARTIAL | 质量/任务口径未统一（CG-02）；本矩阵不产出任务数据 |
| BUDGET | GATED | A 14/20；剩 6 CLOSED；本矩阵 10 次为新建议，待 owner 书面批准 |

## 8. 限制与未执行声明

- 本文件只做只读审查与矩阵设计；**未启动任何 VSPAERO/SU2/RCAIDE Mission/Gmsh/DOE/BO/DE/MAML 求解或训练**；physical_call_count = 0；solver_starts = 0。
- 未修改 <repo-d12d006> 任何文件；未 commit/push/checkout/stash；未做 GitHub 写操作；未新增 run 目录。
- 既有 14 案的所有数字来自归档文件；A1/A2 的独立复核数字来自其报告/JSON；A5 另以独立解析脚本对 A2 的 226 系数、14 polar、9 关键 JSON 做交叉核对（0 差），未重跑 A2 生成脚本。
- 资源上限是计划值，不是实测承诺；实际执行必须由 runner 硬超时/内存限制和授权账本约束。
- 本矩阵不构成对 VSPAERO 物理有效性的认可，也不构成对 owner 预算的替代批准；启动前必须由 owner 书面批准新封顶预算，并由 Lead/A1 落授权文件。

## 9. 证据路径与哈希（只读）

| 证据 | 路径 | 说明/哈希 |
|---|---|---|
| A1 审计报告 | <repo-d12d006>/docs/reviews/d12d006_vspaero_audit_20261105.md | 57,377 B；sha256 da8fdc15…（路径清洗后入库版；清洗前原件 57,447 B / 50fc0630…） |
| A1 审计证据 JSON | <EXT>/a1/d12d006_vspaero_audit_evidence.json | 751,556 B；sha256 9b9d1a32f1097392706d820c7876d438e22ef3bc877dfffcedea6c4684acd167 |
| A2 全量重算 | <repo-d12d006>/docs/reviews/d12d006_readonly_recompute_20261105.md | 30,254 B；sha256 086297ecc0c2700591f081f0e9f587067ed2b9fbea47af51aa8c5d2f765906d5（入库版；EXT 原件 30,150 B / 7b587bd5d1c30cb37e9149edd3f172acd3c3377955ce9e1502e8353b509e6629） |
| A2 全量重算 JSON | <EXT>/a2/out/full_recompute.json | 207,475 B；sha256 15d678da0a0e6729e52a418957a643c23597034123a76baff4251a13c0a29924 |
| A4 门禁矩阵 | <EXT>/a4/issue4_7_gate_matrix.md | 9,858 B；sha256 36789457ee87bf0d430bc663f018e46e9ad862f678437ae57d9689f99f1c6d07 |
| D-12D-006 原文 | <EXT>/a4/raw/d12d006_body.txt | 授权边界/分工/中文要求 |
| 归档 run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/ | 14 案原始 polar/history/矩阵/汇总 |

**最终判定**：现有 14 案可判 **solver_internal_valid = CONDITIONAL_PASS（仅内部趋势）**；**external_physics_validated = NOT_VALIDATED**；维持 **LF-M2.02 = NOT_VALIDATED、CDo/CDtot 非真实阻力、lifting-surfaces-only**。Z-01 已 PASS；建议 owner 先审 Z-00 与 Tier 0 六次新预算；未书面批准前不启动任何求解。
