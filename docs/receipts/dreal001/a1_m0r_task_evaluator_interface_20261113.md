# D-FIXED-001 M0-R：task-capable evaluator 接口合同（A1 → A2）

- 文档 ID：A1-M0R-TASK-EVALUATOR-INTERFACE-20261113
- 代码：research/concorde_metaopt/dreal001/m1/task_evaluator.py
- 依据：Lead L-30（含 ATM-F1R2 裁定 m03137）、A3 D3 crosswalk（A3 commit 5bbca702…）
- 状态：零物理 DRAFT；未启动 solver、未创建真实 run dir、physical_call_count = 0
- 适用范围：A2 的 M1 runner 调用 A1 task-capable evaluator；F1R2/F2R2 冻结字节不改

## 1. 范围与不变量

A1 交付的是“任务感知的评价器接口”，不是新的物理批次。它把 L-30 的 6 个任务因子
（Mach × CL_target，海拔固定 18,288 m）映射为：

1. 一个 TaskSpec：q / Vinf / rho / ReCref / L_ref / mass / task_fingerprint；
2. 每个（设计，任务）一个派生 .vspaero deck，只改写 Mach / Vinf / Rho / ReCref；
3. 每个（设计，任务）一次求解后的 EvaluationRecord：raw polar SHA、exit code、
   stdout/stderr、alpha*、升力匹配 CDi、D_i_N、失败分类与五口径记账字段。

不变量：

- 同一设计的 vspgeom/vkey 字节在 6 个任务间复用；任务只改变 .vspaero deck。
- Sref(x) 永远由该设计的主翼外露平面面积重算；SREF_REF 只用于 L_ref 目标。
- 主目标 D_i_N = q(M,18288) * Sref(x) * CDi(x, alpha*(x))。
- alpha* 是内层升力匹配变量，不是第 13 个设计变量。
- 失败目标的 objective_Di_N / alpha* / CDi 必须是 null，不得填惩罚值。
- fuel_burn_kg = null；物理状态 NOT_VALIDATED。
- 12D_ALL_ACTIVE 是本轮 mask；10D 为 DEFERRED，不得把 10D 结果冒充 12D。

## 2. 冻结几何与冻结链（U1）

- openvsp_geometry.py：d20ee7adc38286c7da3ef3ea5aa5be8204596d491d6601b9a635b0ae5213dc56，
  13,654 B（XForm Abs_Or_Relitive_flag=0 修复）
- baseline vspgeom：16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84，
  225,414 B（post-fix，family 546x480）
- bundle manifest：1b16f5725cf178361f47539db5d727f9687b079e9c8534cc67c153c3d3f8bbe2，6,083 B
- F1R2 12D 零物理审计：7a90b977fd7ba1778ee44c722a837898b62c9f9d201e4cbd22ca2b7b3afdeea5，74,850 B
- design space YAML：8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e，10,846 B
- design_space_freeze.json：fe7e48eba6a70eb76b0b139b1004f775830da68bd5d003604d686e59656e8373，41,775 B

旧 F1 的 40fdd4364e01c7fe11ca2ea4530d39c371ae693a434f39e44986f7512d6446f4
（543x472）不得再作为 task family geometry。dry-run 的 U1 检查已显式断言
U1-OLD-GEOMETRY-NOT-USED = true。

## 3. 大气与任务模型（ATM-F1R2）

单一来源：AtmosphereModel.atmosphere_id = ATM-F1R2。

- altitude = 18,288 m
- p = 7,171.544888256813 Pa
- T = 216.65 K
- R = 287.05287 J/(kg K)
- rho = 0.1153178340089936 kg/m3
- a = 295.06801842964956 m/s
- anchor Mach = 2.02
- anchor Vinf = 596.0373972278921 m/s
- anchor q = 20,483.940233430174 Pa
- anchor ReCref = 89,397,005.8767656

规则：

- Vinf(M) = M * a
- q(M) = q_anchor * (M / 2.02)^2
- q_recomputed(M) = 0.5 * rho * Vinf(M)^2
- ReCref(M) = ReCref_anchor * (M / 2.02)
- 每个任务必须验证 q 与 q_recomputed 的相对误差 <= 1e-12；否则 fail-closed。
- 2.02 任务与已执行 F1R2 完全连续；2.2/1.8 是新条件，不继承 F1R2 expected polar。
- ATM-F1R2 与 ISO 标准 ISA 的 q 相对差约 1.24e-5；本轮不使用 ISO，不得混用。

## 4. 六个任务（冻结数值）

| task_id | Mach | CL_target | q_pa | L_ref_n | mass_t | split |
|---|---|---|---|---|---|---|
| T18K_M202_CL017 | 2.02 | 0.17 | 20483.940233430174 | 1247523.1700664815 | 127.21196025824125 | meta_train |
| T18K_M202_CL019 | 2.02 | 0.19 | 20483.940233430174 | 1394290.6018390087 | 142.17807322979905 | meta_train |
| T18K_M220_CL017 | 2.2 | 0.17 | 24297.194081414087 | 1479759.862543322 | 150.89351231494157 | meta_train |
| T18K_M220_CL019 | 2.2 | 0.19 | 24297.194081414087 | 1653849.2581366538 | 168.6456902343465 | meta_val |
| T18K_M180_CL017 | 1.8 | 0.17 | 16265.063806566455 | 990583.0484794137 | 101.01135948355594 | meta_test |
| T18K_M180_CL019 | 1.8 | 0.19 | 16265.063806566455 | 1107122.2306534622 | 112.89504883456249 | meta_test |

- L_ref = q(M,18288) * SREF_REF * CL_target；SREF_REF = post-fix baseline 几何重算值
  358.25000000000006 m2。
- m_task = L_ref / 9.80665；质量必须落在 [100, 190] t，否则 TaskSpecInvalid。
- CL_required(x) = L_ref / (q * Sref(x))；C5（W01p，Sref 370.25）必须用逐设计 Sref
  重算，禁止硬编码 358.25。
- task_fingerprint = canonical_digest(schema, task_id, altitude, Mach, CL_target,
  atmosphere_id, active_mask, split, l_ref_rule)。

## 5. A1 对外函数（A2 直接 import）

模块：research.concorde_metaopt.dreal001.m1.task_evaluator（Python 3.11）。

- build_task_spec(task: TaskDefinition, sref_ref: float, atmosphere=ATM_F1R2) -> dict
  - 校验 SREF_REF、q 重算、正性、质量边界；失败抛 TaskSpecInvalid。
- build_reference_design(design: ReferenceDesign, work_dir, atmosphere=ATM_F1R2) -> dict
  - 零物理构建一次几何（OpenVSP build + VSPAEROComputeGeometry，StopBeforeRun=1）；
  - 断言 design_hash 与 REFERENCE_DESIGNS 冻结值一致、family=546x480、Sref 重算；
  - 返回 vspgeom/vkey/vspaero_base/csf/vsp3 的 path/bytes/sha256 与 record。
- derive_task_deck(build: dict, task_spec: dict, out_dir) -> dict
  - 复制共享几何；只改写 Mach/Vinf/Rho/ReCref；写 task_deck.json；
  - 返回 schema dreal001.m1_task_deck.v1，含 solver_inputs、deck SHA、checks。
- validate_task_deck(deck_path, task_spec, sref_m2) -> dict
  - 校验 Sref/Mach/AoA/ReCref/Vinf/Rho/Cref/Bref/X_cg/Beta 与 q 重算；
  - q 必须由 deck 实际写入的 Vinf/Rho 重算 0.5*Rho*Vinf^2 并与 task q 比对 rel<=1e-12；
  - alpha 网格必须恰为 (-2,0,2,4,6,8,10)，MAX_ALPHA_REFINE=0；失败抛 DeckContractError。
- solver_input_sha256(case_dir, basename=concorde_baseline) -> dict
  - 四文件 vspgeom/vkey/vspaero/csf；缺一即抛 DeckContractError。
- analyze_polar(polar_path, task_spec, sref_m2) -> dict
  - 7 行唯一有效、全有限、Mach 匹配；线性插值 alpha*；独立计算
    cdi_lift_matched、lift_residual_n/rel、d_i_n、cl_alpha OLS（n>=5, R2>=0.99）；
  - 状态：OK / NO_POLAR / PARSE_ERROR / INCOMPLETE / NONFINITE /
    ALPHA_GRID_MISMATCH / MACH_MISMATCH / NO_BRACKET。
- classify_failure(geometry_ok, deck_ok, attempt, polar_analysis) -> str
  - 五类：GEOMETRY_INVALID / LIFT_TARGET_UNREACHABLE / SOLVER_NONCONVERGED /
    SOLVER_FAILED / INFRA_ERROR；SOLVED。顺序 fail-closed。
- evaluation_key(task_spec, design_hash, deck_sha256, geometry_sha256, solver_sha256) -> str
- build_evaluation_record(task_spec, deck_record, attempt, polar_analysis, status) -> dict
- write_evaluation_record(out_dir, record) -> dict
  - 路径 evaluations/<evaluation_key>.json；O_EXCL；同字节重写返回 reused=true；
    同 key 不同字节抛 TaskEvaluatorError（不覆盖）。
- write_attempt_summary(run_dir, summary) -> dict
  - attempts/<attempt_id>/attempt.json；O_EXCL；重复 attempt_id 抛 FileExistsError。
- SpawnGuard()：零物理守卫；拦截 subprocess.Popen/run/call/check_* 与
  os.system/popen/spawn*；记录 attempts 并抛 TaskEvaluatorError；uninstall 恢复。
- A2LedgerHooks(ledger, phase=main, arm_id=M1_TASK)：A2 accounting_ledger 的薄适配器；
  不导入/不改 A2 字节；charged 与 actual 分列。
- verify_u1_reference_files() -> list：U1 六文件 + design hash + 旧几何断言。
- _component_orientation_checks(build) -> dict：结构式 orientation gate；
  垂尾 z >= max(1.0, 3*y)，wing y 展向 >20 且 z < 0.5*y；共面缺陷必须失败。

## 5b. L-31 R-门自检映射（A1 交付边界）

本接口只负责 task-capable evaluator 与几何/大气/deck 契约；不替代 M0-R 包或
M1 sampler/executor 的 cross-constraint 检查。逐项对应：

| R 门 | A1 实现/证据 | 状态 |
|---|---|---|
| R02 post-fix 几何 | U1_REFERENCE_FILES 绑定 openvsp_geometry d20ee7ad/13,654B、bundle manifest 1b16f572、baseline vspgeom 16da482a/225,414B/546x480；40fdd436 仅作 retired 常量，dry-run 检查 U1-OLD-GEOMETRY-NOT-USED | PASS（零物理） |
| R03 task-capable executor | build_task_spec/build_reference_design/derive_task_deck/validate_task_deck；缺 task 字段或 deck 字段抛 TaskSpecInvalid/DeckContractError；18 per-task deck | PASS（零物理） |
| R05/R23 L_ref/SREF_REF/q | SREF_REF 由 post-fix baseline geometry.wing.area_m2 运行时重算并绑 vspgeom SHA，禁止 358.25 字面量；L_ref=q*SREF_REF*CL_target；q 由 deck 实际注入的 Vinf/Rho 重算 0.5*Rho*Vinf^2，逐 deck rel<=1e-12；Sref(x) 逐设计；D_i_N=q*Sref(x)*CDi | PASS（dry-run DECK-Q-ALL） |
| R08 alpha/残差 | ALPHA_GRID 固定 7 点；MAX_ALPHA_REFINE=0、ALPHA_REFINE_MODE=FIXED_7_POINT_NO_REFINE；独立升力残差由 polar 插值后重算，构造残差不作为证据 | PASS |
| R22/R24 每 task deck/几何复用 | 每 task 独立 case dir 与 task_deck.json；同设计跨 task 复制同一 vspgeom/vkey 字节（CROSS-TASK-GEOMETRY-IDENTITY）；per-task 记录 vspgeom/polar/deck SHA；baseline SREF_REF 与 per-design Sref(x) 分开 | PASS |
| R25 F1R2 连续性 | M2.02 任务 q 与 F1R2 anchor q=20483.940233430174 逐位连续；M2.2/M1.8 为新区间，不继承 F1R2 expected polar；M1-A 重建 admission baseline | PASS（披露） |
| R07 C01–C04 cross constraints | 不在 A1 本接口职责内；由 A3 M0-R 包 + A2 M1 sampler/executor 强制；A1 只提供 design_hash/x12/Sref/active_mask 输入 | NOT_A1_SCOPE |

## 6. TaskSpec 字段（A2 消费）

schema、task_id、task_fingerprint、task_definition（schema/task_id/mach/cl_target/
altitude_m/atmosphere_id/active_mask/split/rationale）、atmosphere（id/altitude/
p/T/R/rho/a/basis）、q_pa、q_recomputed_pa、q_recompute_rel_error、vinf_m_s、
rho_kg_m3、recref、sref_ref_m2、l_ref_n、mass_t、mass_bounds_t、
cl_required_baseline、active_mask。

## 7. EvaluationRecord 字段（A2 消费）

schema、evaluation_key、task_id、task_fingerprint、design_id、design_hash、x12、
active_mask、source_kind、objective_Di_N、alpha_star_deg、sref_m2、sref_policy、
l_ref_n、q_pa、cl_required、raw_sha、polar_bytes、geometry_sha、deck_sha、
solver_version、solver_sha256、starts、internal、physical_solver_starts、status、
failure_class、classification_detail、cdi_lift_matched、cl_at_alpha_star、
lift_residual_n、lift_residual_rel、interpolation、cl_alpha、polar_rows_total、
polar_rows_valid、attempt（attempt_id/exit_code/timed_out/started_utc/ended_utc/
stdout_path/stderr_path/stdout_sha256/stderr_sha256/polar_path/argv/cwd）、created_utc。

约束：

- starts/internal 只在真实启动时分别为 1/7；未启动为 0/0；
  physical_solver_starts 与 starts 同口径，绝不虚报。
- SOLVED 时 objective_Di_N 非空；任何失败类必须 objective_Di_N = null，
  failure_class = 失败类。
- geometry_sha = vspgeom SHA；deck_sha = 该任务派生 .vspaero SHA；raw_sha = polar SHA。

## 8. 失败分类（fail-closed 顺序）

1. 几何/几何门失败 -> GEOMETRY_INVALID（不 spawn solver）
2. deck 契约失败 -> GEOMETRY_INVALID（不 spawn）
3. timeout / 无 exit_code / exit=0 但无 polar / polar 解析错误 -> INFRA_ERROR
4. exit != 0 且有 polar -> SOLVER_FAILED
5. NaN/Inf、行数不完整、alpha 网格或 Mach 不匹配 -> SOLVER_NONCONVERGED
6. CL_target 在极曲线范围外 -> LIFT_TARGET_UNREACHABLE（必须有有效求解证据）
7. 全部通过 -> SOLVED

任何 INFRA_ERROR 必须硬停批次、不重试（L-30/D6 口径）；失败目标保持 null。

## 9. 幂等 / 恢复 / 不覆盖语义

- evaluation_key 是幂等键：task_id、task_fingerprint、design_hash、deck_sha、
  geometry_sha、solver_sha、internal_cases_per_start。
- 同一 key 的 EvaluationRecord：不存在则 O_EXCL 写；存在且字节完全相同则
  reused=true；存在但字节不同则拒绝，不覆盖证据。
- attempt 目录按 attempt_id 独占创建；重复 attempt_id 拒绝。
- 一个设计跨 6 个任务复用同一 vspgeom/vkey；不得因任务不同重建几何
  （除非显式做几何重复性实验并记录）。
- 中断恢复由 A2 ledger.recover() 负责；A1 evaluator 不做自动重试，
  max_retries = 0，partial accounting 必须落盘。
- 本接口不创建真实 run dir；真实 M1 批次由 A2 runner 在 Lead/A5 授权后创建。

## 10. A2 accounting 接线（五口径）

A2 runner 负责按 approval 绑定的路径/SHA 加载 A2 accounting_ledger.py
（SHA 2a8fd91841bc69062ba62c25a52ce9f3311d4b2a68ce39dbda5470673ab1c8bc，
35,413 B），并把 ledger 对象传给 A2LedgerHooks：

- reserve(phase, arm_id, design_index, design_hash, planned_starts=1,
  planned_internal_cases=7, meta)：charged 基数；
- start(tx_id, case_id)：actual starts +1；
- end(tx_id, status, internal_solver_cases=7)：actual internal +7；
- fail_before_start(tx_id, reason)：reservation 未转 start 时计 charged/abandoned；
- record_evaluation / record_cached_read：评估/缓存读计数。

charged（reserve）与 actual（start/end）必须分列，不得混写。A1 不修改 ledger 字节；
A2 若调整字段，只做 adapter，不改 F1R2/F2R2 run dir。

## 11. 与 M0/M1 的集成顺序

1. A2 先验 U1：verify_u1_reference_files() 全 true；引用 post-fix 几何链。
2. 每个 12D 设计 build 一次几何（A1 提供 build_reference_design 或 A2 自己的
   post-fix builder），记录 vspgeom/vkey/Sref/component_metrics/orientation。
3. 对 6 个任务分别 derive_task_deck；同一设计复用几何字节；记录 deck SHA。
4. 真实求解前：校验 deck、q、Sref、orientation、caps、window、approval/GO；
   任一失败 -> 不 spawn，失败目标 null。
5. 真实求解：reserve -> start -> spawn -> 收 polar/exit/stdout/stderr ->
   analyze_polar/classify_failure -> end -> EvaluationRecord -> 五口径 partial accounting。
6. 组首观测 polar SHA 作为该组 expected；同组重复只做 PASS_BYTE，不做数值重判。

## 12. 零物理证据（本次交付）

- dry-run：TASK-EVALUATOR-DRYRUN PASS checks=50 failed=0 decks=18 physical=0；
  spawn_events=[]；solver_started=false；run_dir_created=false。
- build_count=4 次真实 OpenVSP in-process build（B0-01 两次用于 2/2 字节复现，
  B1-01/C5 各一次），仅 OpenVSP build + VSPAEROComputeGeometry（StopBeforeRun=1）；
  VSPAERO solver start=0，不 spawn 任何子进程。
- 18 个 deck：3 个参考设计（B0-01/B1-01/C5）× 6 任务；每任务独立 case dir 与
  task_deck.json。同一 Mach 的两个 CL 任务 deck 字节相同，因为 CL_target 是
  后处理升力匹配目标、不是 solver 输入；这是预注册语义，不是复用其他 task 的 deck。
- B0-01 六个任务 deck SHA：
  - M202_CL017 / M202_CL019：1614a964fc729d42bfa764025a2aa1d3915be8f20dbc6480b72862c15e0c59dc
  - M220_CL017 / M220_CL019：6a022882fa5b9e4cd9c0800fd428f6b5a8465de0e272be1c2db9b5499d55620e
  - M180_CL017 / M180_CL019：9e755cddfb730d4cc71adaf66de4d4a90acbd025bed74c65d198cdbbc097bb80
- 单测：research/concorde_metaopt/dreal001/m1/tests（pytest，27 passed，0 failed）。
- dry-run 报告：docs/receipts/dreal001/a1_m0r_task_executor_dry_run_20261113.json；
  U1 证据：docs/receipts/dreal001/a1_m0r_u1_geometry_rebind_20261113.json；
  SHA256SUMS 见 docs/receipts/dreal001/a1_m0r_SHA256SUMS_20261113.txt。

## 13. 披露与未决

- 本接口尚未被任何真实 M1 批次使用；physical_call_count=0，solver 未启动。
- F1R2/F2R2 冻结包/run dir 字节未改；F1R2 旧 expected polar 仅作历史证据，
  不作为新任务 expected。
- ATM-F1R2 与 ISO q 差约 1.24e-5；Lead 已裁定采用 ATM-F1R2。
- task_id 是 A1 临时 ID；A3 可在不改变数值契约的前提下重命名，映射需写入 M1 包。
- 10D mask 为 DEFERRED；12D 结果不得表述为 10D。
- 无 winner、无显著性、无跨族平均；family 差异只能作协变量报告。
- 真实 M1 执行仍需 A5 预审 + Lead 书面 GO；A1 不在本接口内启动 solver。
- 明确给 A3/A5：U2 dry-run 的 3 个参考设计是真实 OpenVSP in-process build
  （OpenVSPComputeGeometry），不是 VSPAERO solver start；solver_started=false、
  spawn=[]、physical_call_count=0。
- 明确给 A3/A5：R07 的 C01–C04 cross constraints 由 M1 sampler/executor 强制
  （A3 M0-R 包 + A2 runner）；A1 interface 只提供设计/几何/task 契约，不代替该检查。
- 未决：task_id 为 A1 临时 ID；A3 重命名时须保持 task_fingerprint 输入数值不变并写映射。
- 未决：M1-A admission baseline 的具体 case 矩阵由 Lead/A5 预审后确定；本接口只保证
  同设计跨 task 复用 vspgeom 字节与 per-task deck 生成。
