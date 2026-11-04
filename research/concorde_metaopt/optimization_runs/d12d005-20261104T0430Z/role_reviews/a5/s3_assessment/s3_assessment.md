# D-12D-005 A 批 S3（Ew=inf）独立评估

- 任务：task-110，A5 独立只读复核；对象为 D-12D-005 A 批 S3_STD_M2p02_base。
- 运行：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/
- 目标 HEAD：980fffb15431a4a5499f86f5a8f40c2b3e00f111；A 批授权 6 starts，实际 4 starts（S0/S1/S2/S3），S4/S5 未启动。
- 结论：VERDICT=CONTINUE_S4_S5（有条件）。Ew=inf 是派生列 CDiw=0 的除零伪影，不是求解发散信号；A2 的停止是 fail-closed 规则的保守正确执行，但继续 S4/S5 在技术上可行，前提是 Lead 重新书面授权 2 starts，并先修正/书面豁免 v2 runner 对派生列的致命判定。
- 约束：本轮零物理/零 solver；只读证据、JSON/CSV/日志解析、线化理论算术；未改仓库、未写 GitHub、未启动 vspaero.exe；A5 自写探针 s3_probe.py 仅读文件。

## 1. 独立验证的动作与结果

1. 读取 S3 polar、history、solver_stdout、case_summary、s3_column_diagnosis，以及 S0/S1/S2 对照和 batch_state/run_start；文件 SHA256 记录见 commands.log。
2. 用 v2 runner 的纯静态 CLI 复现门禁（不启动 solver）：
   - verify-polar S3 → exit 2，DataQualityError：POLAR_NONFINITE: [{'line': 4, 'column': 'Ew', 'token': 'inf'}]；与 case_summary.json:11-12、225-228 一致。
   - polar-structure S3 → exit 0，PASS_STRUCTURE_ONLY，48 列/1 行，nonfinite_tokens=1；说明结构解析正常。
   - verify-history S3 + A2 S3 expected.json → exit 0，PASS；history 结构、Sref/Cref/Bref/Re 回读正常。
3. 自写独立探针 s3_probe.py（不 import A1/v2 的解析器）读取四个 case：22 项检查，0 failed；其中 12 项公式/分母检查、10 项物理一致性检查。输出在 EXT/s3_assessment/s3_probe.json、s3_probe.stdout.log。
4. 未启动任何 solver；未做 RANS/风洞/CFD；未修改 A0/A2 证据，未 git add/commit/push。

## 2. Ew=inf 的独立判定：派生列除零伪影

### 2.1 数值事实

- S3 polar 第 3 行是 48 列表头，第 4 行是唯一数据行；第 47 列 Ew 为 inf。同一行 CLo=-0.000390514345、CLi=0.074641546128、CLtot=0.074251031783、CDo=0.011182867698、CDi=0.002606540227、CDtot=0.013789407924、CLwtot=-0.000390514345、CDwtot=0.011182867698、CDiw=0、E=0.168318084604。
  证据：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/S3_STD_M2p02_base_model.polar:4
- S3 history 5 次迭代，CLtot 从 -0.000389270298 → 0.073663981306 → 0.074121045070 → 0.074269385763 → 0.074251031783；CDtot 从 0.011147242841 → 0.013775768372 → 0.013780702003 → 0.013790118249 → 0.013789407924；Ew 在 history 中全为 0.000000000000。
  证据：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/S3_STD_M2p02_base_model.history:26-31（迭代表头与第 1-5 行）。
- S3 case_summary：returncode=0、wall_seconds=1.008、outcome_class=FAILED_INVALID_POLAR；verify_polar.message 精确指出 line 4 / column Ew / token inf；verify_history 通过。
  证据：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/case_summary.json:7-12,225-228。

### 2.2 公式核对

用 s3_probe.py 对四个 case 的 polar 行复算：

- E = CLtot²/(π·AR·CDi)：S0/S1/S2/S3 的复算值与报告值最大绝对差 2.02e-7；S3 为 0.16831804957668986 vs 报告 0.168318084604。
- Ew = CLtot²/(π·AR·CDiw)：S0/S1/S2 复算最大绝对差 3.68e-7，均匹配；S3 的 CDiw=0.0，CLtot=0.074251031783，分母为零，Ew 在数值上只能是 inf。
- LoDw = CLwtot/CDwtot：S0/S1/S2/S3 均匹配；S3 的 CDwtot=0.011182867698 有限非零，LoDw=-0.034920769492。
  证据：EXT/s3_assessment/s3_probe.json:s3_logic、:checks；s3_probe.stdout.log 的 checks_failed 为空。

因此 Ew 是 VSPAERO 输出层的派生效率列，不是主求解量；S3 的 CDiw=0 是“wake 诱导阻力为零”的退化，不是主系数发散。
### 2.3 主系数有限且解稳定

- 主系数 27 列全部有限；唯一非有限 token 是 Ew（派生列）。S3 主系数 CLtot=0.074251、CDi=0.002607、CDtot=0.013789 均有限且为正；没有 NaN/INF/IND 扩散到主系数。
- history 第 4→5 步 ΔCLtot=-1.84e-5（相对 2.47e-4），ΔCDtot=-7.1e-7；5 次迭代 CLtot 保持在 0.0742 附近，没有增长/振荡。作为对照，S0 的末步相对变化 1.08e-4、S1 为 1.47e-6；S3 的 2.47e-4 属同一收敛量级，未达到 1e-6 plateau，但不是发散。
  证据：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/S3_STD_M2p02_base_model.history:30-31；EXT/s3_assessment/s3_probe.json:cases.S3_STD_M2p02_base.history_series（last_rel_step_CLtot=0.00024718821488771056）。
- solver_stdout：VSPAERO v7.2.2，5 个 wake iter，最后 GMRES 残差 Red=-14.53548、Max=-17.19114（相对限 -1.0/1.77527）；Total setup and solve time 0.516 s；stdout 无 nan/inf/IND token。
  证据：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/solver_stdout.log:70,345-349,361；s3_probe.json:s3_stdout。

### 2.4 与线化超声速理论和 V1 发散的对照

- 线化理论：M=2.02，β=sqrt(M²-1)=1.7551068343551055；2D CLα=4/β=2.2790635428582076 /rad；α=2°=0.03490658503988659 rad；CL_2D=0.07955432537008524。一阶有限展长估计 CLα_3D=CLα/(1+CLα/(πAR))=1.9291828605300199 /rad，CL_3D=0.0673411855785828（AR=4）。
  S3 的 CLtot=0.074251 落在 0.06734–0.07955 之间：相对 2D 低 6.67%，相对一阶有限展长估计高 10.26%。这是合理量级，不是异常放大。
  证据：EXT/s3_assessment/s3_probe.json:linear_theory；本机算术，无 solver。
- S3 的 CDi=0.002606540227；CL·tan(2°)=0.002592；比值 1.005259（差 0.5%），符合超声速无前缘吸力时的升致阻力 CL·tanα。S0/S1/S2 的 CDi 与 CL²/(πAR) 的比值分别为 1.031/1.055/1.031，符合亚声速诱导阻力。两者说明 S3 的 CDi 物理上合理。
  证据：EXT/s3_assessment/s3_probe.json:cd_o_analysis.physical_checks；s3_probe.json:checks。
- V1 归档对照的 V7-00/V7-01 是 Uber_eCRM-002 全机（uber2.vsp3，913,497 B），不是标准翼；V7-00 CLtot 从 -0.0089 到 -267,095.9 再到 -7,469,379.9；V7-01 为 -0.0051 → 4.484e22 → 3.230e26，且无 polar；两者均 diverged=true。S3 的标准翼 5 行稳定在 0.0742，与 V1 发散模式不同。
  证据：evidence/a0/vspaero_v1_divergence_analysis.json 的 cases.V7-00/cases.V7-01；EXT/s3_assessment/s3_probe.json:v7_comparison。
- 因此：Ew=inf 不是发散信号；S3 不是 V7 类发散；A2 诊断的结论“派生列退化伪影”方向正确，但其 s3_column_diagnosis.md:44 把原因写成“CDwtot 非零/CLwtot 近零导致 Ew 溢出”，并不精确：实际公式分母是 CDiw=0（CDwtot 只是同一 wake 组的有限量）。这是 A2 文档的因果表述问题，不改变“伪影”结论。

## 3. CDo 语义（回答 Lead 的 4 个问题）

### 3.1 CDo 是什么

CDo 是 VSPAERO 内部的寄生/摩擦型阻力项，不是升致项。证据：

- 迭代 1 时 S0 的 CLi=0、CDi=0，但 CDo 已经等于 0.019525802111；S3 迭代 1 的 CLi=0、CDi=0，CDo=0.011147242841。升致项为零时 CDo 仍存在，说明它不是诱导阻力。
- CDo 随 Re 增大而下降：S0/S1/S2 在 Re/1e6=0.239352 时 CDo≈0.01963–0.01965；S3 在 Re/1e6=4.834912 时 CDo=0.011182867698；旧 6.2 数据在 Re/1e6=89.39701 时 CDo≈0.00503–0.00508。S3/S0=0.569616，Re^-0.2 的粗略期望比为 0.548188；量级与平板摩擦阻力的 Re 趋势一致。
- 旧 6.2 polar 在 AoA=-2/0/+2° 的 CDo 为 0.005083525/0.005028233/0.005082831，核心 AoA 范围相对散布 1.0996%，基本不随 AoA 变；高 AoA 到 6° 时散布 9.59%，但仍远小于升致项的变化。
  证据：S3 history:27；S0 history:27；旧 6.2 polar（D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/baseline/main_wing_baseline_DegenGeom.polar）；EXT/s3_assessment/s3_probe.json:cd_o_analysis.physical_checks。

结论：CDo 行为上像内部的寄生/摩擦阻力估算，量级在 0.005–0.020；但本机没有用 RANS、风洞或制造商数据标定它，且 VSPAERO 7.2.2 thin 在 M2.02 仍 NOT_VALIDATED。因此 CDo 不能当作真实 CD0，CDtot 不能当作真实整机阻力，L/D=5.38 不能当作真实巡航效率。
### 3.2 SOLVED_VALID 是否只能限定 CL/CLi/CDi

是，而且应进一步限定为“内部量”。当前 S0/S1/S2 在 batch_state.json:10-63 标为 SOLVED_VALID，S3 标 FAILED_INVALID_POLAR；但 SOLVED_VALID 只说明 VSPAERO 内部求解器返回 0、polar 结构可解析、主系数有限；它没有、也不能说明物理真实性。建议：

- CL/CLi/CDi：可作为 VSPAERO 内部诊断/趋势量，但仍是 VLM 无黏量，不能替代 RANS/风洞。
- CDo/CDtot：内部寄生/摩擦项与内部总阻力，不得与真实阻力直接对照，不得作为优化目标/燃油换算依据。
- L/D、E、Ew、LoDw：均为派生量；E 使用亚声速诱导阻力公式，在 M2.02 不适用；S3 的 CDi/(CL²/πAR)=5.941，说明 E=0.168 只是在用错误的亚声速公式，不能作效率。Ew 在分母 CDiw=0 时无定义。
  证据：EXT/s3_assessment/s3_probe.json:cd_o_analysis.physical_checks.S3_CDi_over_CL2_piAR=5.941133482207892，:checks；S3 polar:4。

### 3.3 是否影响 S4/S5

不构成“停止物理实验”的理由；但影响证据解释：

- CDo 语义是系统性的模型定义问题，不是 S3 的新发散；S4/S5 仍可用来回答两个问题：S4（NumWakeNodes=128）相对 S3 的 wake 敏感性；S5（D12 主翼标准 12D 几何）相对 S3 的几何/版本敏感性。
- S4/S5 的 CDtot 同样不能当真实阻力；其“SOLVED_VALID”也只能是内部有效。S4/S5 不能“修复”CDo 语义；不应把 S4/S5 的 CDtot 作为最终目标。
- 若 S4/S5 出现主系数非有限、CL 发散、CDi<0/CDtot<0 等，仍按原 stop_rules 停止；若只是 Ew/派生列退化，则按第 3.4 节的派生白名单处理，不应再次误停。

### 3.4 v2 runner 最小修改建议（不改仓库，本轮只给建议）

当前 v2 runner 把任何非有限 token 都当致命错误：vspaero7_runner_v2.py:632（_parse_polar_rows 收集 nonfinite）、:680-687（validate_polar_file 一进来就 raise POLAR_NONFINITE）、:751（parse_polar_structure 已存在结构-only 路径）。建议最小改动：

1. 明确 PRIMARY_COLUMNS 与 DERIVED_COLUMNS：主列至少包含 CLtot/CDi/CDtot/CDo/CLo/CLi；派生列包含 E、Ew、LoDw。validate_polar_file 只对主列 nonfinite 抛错；派生列 nonfinite 记录为 derived_degenerate，不抛致命错。
2. 对 Ew 增加语义判断：若 CDiw==0 且 CLtot 有限非零且 CDwtot 有限，则把 Ew 归一化为 null，返回 status=PASS 并附 derived_degenerate=[{line,column,token}]、primary_columns_finite=true；其它派生列/其它原因的非有限仍 fail-closed。
3. 保留现有 parse_polar_structure（结构-only）用于归档非物理文件；不要用它替代主列验证。不要放宽 CLtot/CDtot 的 10.0 非物理阈值。
4. 在结果/证据中增加字段：primary_nonfinite、derived_degenerate、primary_columns_finite、physical_validation="NOT_VALIDATED"、validation_scope="VSPAERO_INTERNAL_ONLY"、cdtot_components={CDo,CDi}、cdtot_real_drag_comparable=false、cdtot_use_for_objective=false、efficiency_columns_derived=true。
5. 在 case_summary/batch_state 中增加 stop_rule_1_primary_triggered=false 与 derived_degenerate_columns=["Ew"]，避免把派生列伪影计入 stop_rule_1；若 Lead 要求“任何 INF 一律停”，则保留严格规则但必须由 Lead 书面豁免 S3/S4/S5 的派生列。
6. 命名：SOLVED_VALID 改为 SOLVED_VALID_VSPAERO_INTERNAL，或保留 SOLVED_VALID 但强制同时写 validation_scope/physical_validation；仅改标签不够，证据 JSON 必须有字段。

## 4. 停止/继续的治理判断

- A2 的停止在字面规则上成立：run_start.json:37-42 的 stop_rule_1 写“任一启动出现 NaN/INF/IND 或非物理……”，batch_state.json:4-8,97-117 记录 stops 4/6、stopped=true、stop_rule_1_nonfinite_IND_INF、remaining_disposition=CLOSED_NOT_CARRIED_OVER_NOT_REALLOCATED。A5 不认为 A2 违规；这是 fail-closed 的保守正确执行。
- 但物理判断上，Ew=inf 是派生列除零，不是主系数发散；S3 主系数有限、history 稳定、CL 与线化理论合理、CDi 与 CLtanα 一致，故不是“STOP_CONFIRMED”的物理证据。
- 因此建议 CONTINUE_S4_S5，但必须满足以下条件，缺一不可：
  1. Lead 以新书面授权重开剩余 2 starts（原 batch 的 remaining_disposition 已关闭，不得由 A5 自行继续）。
  2. v2 runner 按第 3.4 节修复，或 Lead 对 S3/S4/S5 的 Ew 派生列给出书面白名单/豁免；S4/S5 运行前用 S3 复跑 verify-polar 验证不再误停。
  3. S4/S5 报告/证据显式写 VSPAERO_INTERNAL_ONLY / physical_validation=NOT_VALIDATED；CDtot 不作真实阻力或优化目标；项目报告遵守既有 lifting-surfaces-only 边界（本批为标准翼，不涉及机身）。
  4. 若 S4/S5 出现主列非有限、CL 发散或负阻力，停止，不再继续。
- 若上述条件不满足，A 批保持冻结；这是治理性停止，不等于“物理发散已确认”。verdict 文件同时写明这一点。

## 5. Findings（详见 findings.csv）

计数：0 blocker / 2 major / 3 minor。

- S3F-01 major：v2 verify-polar 把派生列 Ew=inf 当致命 POLAR_NONFINITE，导致 S3 被标 FAILED_INVALID_POLAR、批次停止；主系数全部有限。证据：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/vspaero7_runner_v2.py:632,680-687；D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/S3_STD_M2p02_base_model.polar:4；C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/a5/s3_assessment/s3_probe.json:s3_logic。建议按 3.4 节分离主/派生列。
- S3F-02 major：SOLVED_VALID 未限定物理范围；CDo 是内部寄生/摩擦项，CDtot 不能当真实阻力，E/Ew/L-D 不能当效率；证据：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/batch_state.json:10-63；C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/a5/s3_assessment/s3_probe.json:cd_o_analysis.physical_checks。建议加 validation_scope/physical_validation/cdtot_real_drag_comparable 字段。
- S3F-03 minor：A2 诊断 D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/s3_column_diagnosis.md:44 把 Ew 溢出归因于 CDwtot 非零/CLwtot 近零，实际分母是 CDiw=0；结论正确、因果表述需改。
- S3F-04 minor：D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/case_summary.json:11-12 的 outcome_class_reason 为 “v2 polar verification failed: unknown”，而 :225-228 有精确 message；应写入精确原因，便于审计。
- S3F-05 minor：同一 Ew 列 D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/S3_STD_M2p02_base_model.history 输出 0、D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/cases/S3_STD_M2p02_base/S3_STD_M2p02_base_model.polar 输出 inf；派生列在 history 与 polar 之间不一致，runner 应归一化为 null 并记录 derived_degenerate。

## 6. 限制

- 本轮未启动 VSPAERO/solver，未做 RANS/CFD/风洞；CDo 语义来自本机数值行为与跨版本/跨 Re 对照，不是 VSPAERO 源码或官方文档的正式定义；因此 CDo 的“寄生/摩擦项”判断应视为高置信度的工作解释，不能升级为物理验证。
- 未验证 S4/S5（未运行）；未验证 VSPAERO 7.2.2 在 M2.02 的真实性；未做网格/时间步/收敛参数敏感性。
- 未改仓库、未写 GitHub；s3_probe 是独立解析器，不复用 A1/v2 的 polar parser。A5 自写探针 22 checks/0 failed 是内部一致性检查，不是求解器验证。

## 7. 交付与复现

- EXT/s3_assessment/s3_assessment.md（本文件）
- EXT/s3_assessment/findings.csv
- EXT/s3_assessment/verdict.txt
- EXT/s3_assessment/commands.log
- EXT/s3_assessment/s3_probe.py、s3_probe.json、s3_probe.stdout.log
- 关键证据（只读）：S3 polar/history/case_summary/diagnosis；S0/S1/S2 对照；batch_state/run_start；V1 divergence analysis。
- 复现命令与退出码见 commands.log；所有数字均给文件路径+行号或 JSON 字段。
