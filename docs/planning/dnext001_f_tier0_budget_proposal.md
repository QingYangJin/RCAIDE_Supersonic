# D-NEXT-001 F 线：Tier0 真实 VSPAERO 预算申请（只申请，不执行）

- 文档状态：**申请（PROPOSAL）**，不是批准；`approved_by: null`
- 申请日期：2026-11-10
- 申请主体：A1（真实评价与航空约束，F 线），Issue #8 / D-NEXT-001
- 依据：`docs/planning/dnext001_m0_baseline_and_gate_audit.md`；
  `research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/summary.json:173`（注入参考量）
  与 `:211`（VSPAERO 6.2.0 静默 Sref=1.0 缺陷）
- **本轮实际发生：physical_call_count = 0。** 本文件提交时没有启动任何 VSPAERO / OpenVSP / SU2 /
  RCAIDE Mission / WaveDrag；所有 F 线 run 均为 SYNTHETIC_MOCK 或 ARCHIVE_REPLAY。

> **申请 ≠ 批准。** 在 owner 以书面形式（`approved_by` + `approved_utc`）批复之前，
> 任何代码路径不得把本申请当作可执行授权；默认 `physical_budget = 0`。

---

## 1. 申请目的

在不扩大声张范围的前提下，用**最少次数**的真实 VSPAERO 启动回答四个"必须先答"的工程问题：

1. **可重复性**：同一算例连续两次启动，CL/CDi 是否在数值噪声内一致（否则后面的比较全部无意义）。
2. **网格敏感性**：网格加密一级后 CL/CDi 变化多大（判断"内部系数"是否已接近网格无关）。
3. **尾迹与迭代收敛**：VSPAERO 的尾迹/迭代是否真的收敛，残差历史是否可查。
4. **参考量与力轴诊断**：Sref/Cref/Bref 注入是否被求解器真实采用（防止 6.2.0 静默 Sref=1.0 复发），
   以及力矩参考点取机翼 AC（16.821978 m）与取全机几何 CG（28.287395 m）时 CM 的差异有多大。

**明确不申请、也不做**：整机阻力/油耗结论、配平/静稳定结论、机身干扰修正（BODY-CORR）、
高保真（HF-M2.02）结论、任何"物理 PASS"声明。

---

## 2. 前置条件（缺一不可）

1. M0 审计（`dnext001_m0_baseline_and_gate_audit.md`）已被 owner 评审。
2. 12D 基线几何与派生量已用 `design_space_12d_lifting_surfaces.yaml` 的派生规则重算，且
   Sref=358.25 m^2 / Cref=18.489893 m / Bref=25.604638 m 与注入值一致。
3. 使用 `openvsp355-remediation-20261102T014411Z` 已验证的 42 行 setup 模板（含全部 "=" 号），
   并在运行前做一次**离线**模板自检（不允许再出现 12 行漏 "="）。
4. 独立 run 目录：`research/concorde_metaopt/optimization_runs/f-tier0-<UTC>/`，
   不写、不改任何冻结产物（S1/S2/S3 run 目录、manifest、SHA 文件）。
5. 串行执行：同一时刻只允许 1 个 VSPAERO 进程；NCPU ≤ 4；单次墙钟 ≤ 900 s。
6. 预算账本 `BudgetLedger(physical_budget=6)`，每次启动前 `authorize(1)` 预授权，失败即停。

---

## 3. 计费与记账规则（强制）

| 规则 | 内容 |
|---|---|
| 计费单位 | **每次 VSPAERO 进程启动 = 1 次物理调用**，与是否收敛、是否超时无关 |
| 重试 | 最多 1 次重试，**重试单独计费**（即一次任务最多消耗 2 次额度） |
| 超时 | 单次硬超时 900 s；超时按 1 次计费并立即停机（不自动重试超时） |
| 缓存 | Tier0 不使用缓存规避计费；同一算例重复启动照样计费 |
| 串行 | 禁止并行/批处理并行；禁止多进程共享同一算例 |
| 额度 | 总启动次数 ≤ 6；不使用"弹性额度"越过 6 |
| 失败值 | 不收敛/崩溃/输出缺失时 objective 与气动系数一律记 `null`，状态 `SOLVER_NONCONVERGED` 或 `EVALUATOR_ERROR` |
| 记录 | 每次启动写 `attempts.jsonl`：attempt_id、命令、模板 SHA256、开始/结束 UTC、墙钟、退出码、是否计费、产物路径、SHA256 |
| 标注 | 所有记录 `source_kind=ENGINEERING_SOLVER_IN_LOOP`、`physical_validation_status=VSPAERO_INTERNAL_ONLY`、`physical_call_count=1` |

---

## 4. 六次启动矩阵（申请上限 6）

统一条件：Mach 2.02、Alpha 2.0°、Beta 0、18288 m 来流（Vinf=596.0373972278921 m/s、
Rho=0.1153178340089936 kg/m^3、ReCref=89397005.8767656、q=20483.94023343017 Pa，
来源 `docs/reviews/p1p3_fullchain_validation_report_20261031.md:43`）；
NCPU=4；串行；单次超时 900 s；无重试（除非该行"重试"列写明）。

| ID | 目的 | 算例/网格 | 预期产物 | 成功判据（仅内部一致性，不是物理 PASS） | 重试 |
|---|---|---|---|---|---|
| T0-1a | 可重复性 第 1 次 | wing355_thin（基线网格） | lod/polar、残差日志 | 正常退出、有收敛文件、CL/CDi 有限 | 0 |
| T0-1b | 可重复性 第 2 次（同 T0-1a） | wing355_thin（同输入） | 同上 | 两次 CL 相对差 < 1e-3、CDi 相对差 < 1e-3 | 0 |
| T0-2 | 网格加密敏感性 | wing355_thick（refinement +1） | lod/polar、残差日志 | 正常退出；记录 ΔCL、ΔCDi；不宣称网格无关 | 0 |
| T0-3 | 尾迹/迭代收敛诊断 | wing355_thin（提高迭代上限） | 残差历史、wake 文件 | 残差单调下降并 ≤ 1e-4（否则记 NONCONVERGED） | 0 |
| T0-4 | Sref/Cref/Bref 注入核对 | wing355_thin，RefFlag=0，显式注入 | 打印系数 + 反推的 Sref/Cref/Bref | 反推 Sref 与 358.25 的相对误差 < 1e-6；Cref/Bref 同理 | 0 |
| T0-5 | 力轴/力矩参考点诊断 | wing355_thin，Xcg=16.821978 m 与 Xcg=28.287395 m 两工况（**共 2 次启动**） | 两工况 CL/CDi/CM、力轴符号表 | 两者 CM 差异被量化并记录；不宣称配平/静稳定 | 0 |
| T0-6 | 弹性重试位（保留） | 仅当 T0-1..T0-5 出现**可重试**失败时使用；否则不执行 | 同失败项 | 同失败项判据 | 计入 1 次 |

> 注：T0-5 需要 2 次启动，因此矩阵实际占满 6 次额度（T0-1a、T0-1b、T0-2、T0-3、T0-4、T0-5×2 = 7 次）
> —— **这正是本申请要 owner 明确取舍的地方**。建议二选一：
> - 方案 A（默认申请）：T0-1a、T0-1b、T0-2、T0-3、T0-4 = 5 次，T0-5 降级为"仅 Xcg=28.287395 单工况"= 1 次，合计 **6 次**，不做 Xcg 对比；
> - 方案 B：保留 Xcg 对比，则删去 T0-2（网格加密）或 T0-3（尾迹收敛）之一，合计仍 6 次。
>
> 本申请默认按**方案 A** 执行；若 owner 选择方案 B 需在批复中写明删除项。T0-6 不占额外额度，
> 只在出现可重试失败时替代被跳过项，且总额度仍 ≤ 6。

---

## 5. 停机条件（任一触发即停止，剩余额度不自动使用）

1. 任一系数为 NaN/Inf，或日志出现数值发散。
2. 进程超时 > 900 s，或退出码非 0 且无法归因。
3. 启动失败连续 2 次（含重试）。
4. T0-4 反推 Sref 相对误差 > 1e-6（说明注入未生效，后续所有系数不可比）。
5. 磁盘写入失败、许可/环境错误、或发现 setup 模板 SHA256 与归档不一致。
6. 出现"系数看起来合理但无法解释"的情况：停机并写 receipt，不调参重跑。

停机后必须：写 `fail_stop.json`（触发条件、已完成启动数、已计费数、产物 SHA256），
并在 stage receipt 中明确 `stage_status = STOPPED_FAIL_CLOSED`。

---

## 6. 成功也不等于物理 PASS

即使 6 次全部正常完成，最多只能得到：

- "VSPAERO 在本算例上可重复、可收敛、参考量注入正确、力轴符号一致"——**内部一致性证据**；
- `physical_validation_status` 最多从 `NOT_VALIDATED` 提升到 `PARTIAL`（需 owner 评审）；
- **LF-M2.02 仍为 NOT_VALIDATED，BODY-CORR 仍为 BLOCKED，HF-M2.02 仍为 PARTIAL**；
- 仍不得产出整机阻力/油耗/配平/静稳定结论；仍不得把 CL/CDi 当作整机油耗。

---

## 7. 申请与批复

- 本文件 = 申请。**未获批复前，F 线所有 run 的 `physical_call_count` 恒为 0。**
- 需要的批复字段（写入本文件或独立批复记录）：

```yaml
tier0_budget:
  requested_launches: 6
  plan: A            # A = 默认（5 项 + T0-5 单工况）；B = 保留 Xcg 对比、删 T0-2 或 T0-3
  approved_by: null  # owner 签字
  approved_utc: null
  max_launches: 0    # 未批准前必须为 0
  serial_only: true
  timeout_seconds: 900
  ncpu: 4
  retry_max: 1        # 仅对可重试失败，且计入总额度
  stop_on_first_hard_failure: true
```

- 批复后，执行方必须在 run_config.json 中写入 `budget_requested: 6`、`budget_approved: <max_launches>`、
  `approval_ref: <批复记录路径>`，并按第 3 节逐次记账。
- 若实际启动次数低于批复额度，剩余额度作废，不顺延。

---

## 8. 交付物（获批并执行后）

1. `research/concorde_metaopt/optimization_runs/f-tier0-<UTC>/`：
   `run_config.json`、`attempts.jsonl`、`evaluations.jsonl`、`SHA256SUMS.txt`、`figures/`（有数据才画图）。
2. VSPAERO 原始产物（lod/polar/wake/残差日志）及 SHA256。
3. 中文 `tier0_report.md`：逐项回答第 1 节四问，明确写出"能证明什么/不能证明什么"。
4. 失败则：`fail_stop.json` + 中文说明，负结果同样算交付。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| VSPAERO 6.2.0/7.2.2 静默使用默认 Sref=1.0 | T0-4 反推 Sref；模板 SHA256 校验；setup 全行含 "=" 自检 |
| 单次求解结果被误当整机性能 | 记录强制 `VSPAERO_INTERNAL_ONLY` + `physical_validation_status`；文档与图标题写明参考量与力矩参考点 |
| 机翼 AC 被当作全机 CG | 记录中同时写 `wing_ac_x_m` 与 `cg_x_m`；CM 结论必须声明 moment reference |
| 超时/失败被"重跑到收敛"掩盖 | 重试单独计费且计入总额度；超时不自动重试 |
| 额度被并行消耗 | 串行 + 单进程锁文件 + Ledger 预授权 |
| 冻结产物被改写 | 独立 run 目录；提交前 `git status` 检查；禁止 touch S1/S2/S3 |

---

## 10. 结论

申请 6 次（方案 A）真实 VSPAERO 启动，用于可重复性、网格敏感性、尾迹收敛、参考量注入与
力轴/力矩参考点五项内部诊断；**申请 ≠ 批准**，批准前 physical_call_count 保持 0，
批准后也必须串行、≤900 s、失败即停，且**不得**据此宣称任何物理 PASS。
