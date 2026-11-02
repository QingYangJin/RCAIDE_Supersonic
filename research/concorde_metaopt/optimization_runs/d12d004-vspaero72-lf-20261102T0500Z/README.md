# d12d004-vspaero72-lf-20261102T0500Z — D-12D-004 A 类 LF VSPAERO 7.2.2 薄翼验证 run

- 状态：V1_STOPPED_ABORT_FINAL（V1 轮已按批准的停止规则提前终止；starts 4/10，剩余 6 次已关闭，不结转、不重分配）
- 授权：Issue #4 评论 6569140757（2026-11-02，D-12D-004），仅批准 A 类 A-VSPAERO7-thin-LF 最多 10 次启动；V1 轮起点 2026-11-02T05:55:00Z，截止 2026-11-02T11:55:00Z（以 Lead 勘误为准）。
- 被拒绝类别（额度恒为 0，禁止借用/转换）：B VSPAERO Thick=0、C OpenVSP WaveDrag=0、D SU2 Euler=0、E RCAIDE Mission=0、P4 真实 BO/MAML=0。
- 分支/worktree：research/d12d004-vspaero7 @ D:/RCAIDE-d12d004；base SHA e5140fc64d348f2d9dcf52962f1dcfc425099341；runner 代码提交 f8506c9ae13d6c6f472a461bf80d26dba6cadbd0；V1 首次启动时实际 HEAD=f8506c9（记录见 evidence/v1/run_start.json）。不合并 main。
- 报告语言：简体中文；图表中文。
- 本 run 只计算 lifting surfaces only（仅薄翼面，无机身、无垂尾），不得据此宣称全机阻力、航程或燃油标签。

## 1. 硬约束（来自授权评论）

1. 串行执行，单并发；CPU ≤4 核；RAM ≤8 GB；无付费云。
2. 单次启动墙钟 ≤600 s；整轮（准备+运行）≤6 h。
3. 每一次 vspaero.exe 进程启动都计费：失败、超时、被中止、setup 失败后仍启动均计 1 次；每案最多 1 次重试且占用同一 cap。
4. starts_used >= 10 立即强制停止；剩余案例保持未运行状态。本轮由批准的停止规则提前终止（见第 5 节）。
5. 门禁 A1/A5/A3/A2 在首次启动前已全部置 true 并留证（见 config/actual_solver_budget.json 的 preflight_gates 与 evidence/v1/run_start.json）。
6. 新版 .vspaero 必须逐字段写入并回读断言（13 条，见 config/run_config.json），禁止默认值 Vinf=100 / Rho=0.002377 / ReCref=1e7 进入真实求解。
7. 进程退出码 0 不等于物理通过；零升力 CDi 约等于 0 不算失败，但升力非零时负总阻力为严重警报。
8. 与 P4 仅通过 evaluator_id / fidelity / physics_validation_status 数据合同交接；物理验证不通过不阻塞 P4。

## 2. 目录与文件（最终状态）

| 路径 | 用途 | 最终状态 |
|---|---|---|
| README.md | 本说明 | 已更新为 V1 final state（task-66 记账修复） |
| config/run_config.json | 运行配置：授权、合同工况、参考量、13 条回读断言、账本与输出 | status=V1_STOPPED_ABORT_FINAL；budget.used_starts=4/10；git_sha 已从 run_start 记录解析 |
| config/actual_solver_budget.json | D-12D-004 独立预算账本 | V1_STOPPED_ABORT_FINAL_FREEZE：4/10、剩余 6 次 closed |
| config/solver_case_matrix.csv | 10 案矩阵（S2 -> M3 -> P3 -> D2） | 终态已写入每案 status 列 |
| evidence/v1/ | V1 证据：run_start、solver_ledger.jsonl（4 事件）、stop_decision、case_results、setup_gen（9 个 setup 目录）等 | 已冻结 |
| lf_vspaero_results.json / summary.json | V1 结果与摘要 | 已生成，状态枚举统一 |
| data_manifest.json | 交付清单 | 由 Lead 在本次记账修复后重生成（A2 不修改 manifest） |

raw 产物（gitignored）位于 D:/RCAIDE/outputs/concorde_metaopt/d12d004-vspaero72-lf-20261102T0500Z/。

## 3. 合同工况（冻结，来自 configs/task_fixed_cruise.yaml 与 12D 约定）

Mach 2.02；高度 18288 m（T=216.65 K, p=7171.544888256813 Pa, rho=0.1153178340089936 kg/m3, a=295.0680184 m/s）；Vinf=596.0373972278921 m/s；ReCref=89397005.8767656；Sref=358.25 m2；Cref=18.489893 m；Bref=25.604638 m；AoA=2 度；CG x=16.821978259514246（PROVISIONAL_NOT_FROZEN）；Symmetry=NO；WakeNodes=8、WakeIters=5。

## 4. 10 次启动的执行排序与含义

1. S 组（2 次）：V7-00 标准薄翼亚音速（运行器自洽）、V7-01 标准薄翼 Mach2.02（适用性探针）。V7-01 若负阻力/NaN/超时则停止大翼链。
2. M 组（3 次）：12D 仅主翼粗 8/17 -> 中 16/33（主判据）-> 细 32/65（收敛判据，中到细相对差 <15%）。
3. P 组（3 次）：W01 +1%（361.8325）、W03 +1 度（68.0）、W10 +2 度（2.0），仅中网格，几何断言 + 趋势自洽。
4. D 组（2 次）：V7-08 攻角 0/2/4 机理诊断；V7-09 唯一重试/尾迹敏感性余量（启动前必须写明假设与准则，否则保持未触发）。

## 5. 当前事实（V1 最终，4 次启动，均有账本）

- 账本与计数：cap=10、starts_used=4、starts_remaining=6、retries_used=2、billable_events=4；starts_used+starts_remaining=10 且 billable_events=starts_used（均在 evidence/v1/run_start.json 断言）。
- 4 个计费事件（evidence/v1/ledger/solver_ledger.jsonl）：
  1. NA-D12D004-001 V7-00 attempt 1，FAILED，0.024 s（.vkey/.csf 缺失，LD-001）。
  2. NA-D12D004-002 V7-01 attempt 1，ABORTED_WRAPPER_DEADLINE，120.0 s（外层 120 s 工具期限，LD-003）。
  3. NA-D12D004-003 V7-01 attempt 2，TIMEOUT，600.331 s（Mach 2.02 thin 数值发散、无 polar），触发批准停止规则。
  4. NA-D12D004-004 V7-00 attempt 2，VERIFY_FAILED，76.891 s（Lead 在停止冻结后单独授权的唯一一次重试；Mach 0.10 返回非物理系数；校验器另报 LD-002 表头不兼容）。
- 停止与重试时间线：A2 于 2026-11-02T06:25:27Z 按停止规则冻结链路（计数 3/7/1）；Lead 随后以消息 m01190/m01194 作出决定 (a)：仅追加一次 V7-00 重试、不重分配剩余额度、不重试 V7-01；该重试 06:26:57Z 启动、06:28:14Z 结束（事件 004）；最终计数 4/6/2，剩余 6 次 CLOSED_NOT_CARRIED_OVER_NOT_REALLOCATED。
- 案件终态（config/solver_case_matrix.csv）：V7-00 FAILED_NONPHYSICAL_VALUE；V7-01 TIMEOUT_DIVERGED；V7-02..V7-08 NOT_RUN_AFTER_ABORT；V7-09 NOT_RUN_CONDITION_NOT_TRIGGERED。
- 状态枚举选择：canonical token 统一为 FAILED_NONPHYSICAL_VALUE（矩阵、本 README、summary.json、lf_vspaero_results.json、case_results.json 一致）；旧别名 FAIL_HYGIENE_NONPHYSICAL 已废弃。理由：该 token 表达求解完成但系数非物理的最终判定，FAIL_HYGIENE 只是其中一个检查项的名称，不能作为 case 终态。
- 门禁不变：LF-M2.02 VSPAERO drag=NOT_VALIDATED；VSPAERO 7.2.2 thin 超声速=NOT_A_VALID_PHYSICAL_METHOD；V7-00 亚音速 hygiene=FAIL；validated aircraft fuel label=false；external body correction 未注入（body_correction_gate=BLOCKED）。
- 零求解器静态根因核对：VSPGEOM 是官方 thin 路径（SET_NONE=-1 / SET_ALL=0；官方 test_vsp_api.py:1450-1463、1524-1536），不是输入模式错误；本轮共 9 个 setup 目录，其中 8 个含 geom_result_thin.csv（V7-03 该文件缺失；V7-09 条件案未生成 setup 目录），8 个记录均为 GeometrySet=-1 / ThinGeometrySet=0；诊断性 DegenGeom 启动按 Lead 规则 4 跳过，starts 保持 4/10。
- 无求解器进程在运行；未修改源码/测试；本轮未 commit/push（run 目录文本由 Lead 统一提交）。

## 6. 后续（本轮未授权、未执行）

1. VSPAERO 7.2.2 设置敏感性研究（NumWakeNodes/WakeIters/WakeRelax 等）属新的授权轮，本轮无额度、不得启动。
2. 不得据本 run 推断全机阻力/航程/燃油；仅 lifting surfaces only 的失败/未验证证据。
3. data_manifest.json 需在本次记账文本修复后由 Lead 重新生成并提交；A2 不修改该文件。
