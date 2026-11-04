# D-12D-005 A 批执行后的单点修复记录（Lead, 零求解）

- 生成时间：2026-11-04T15:5x+08:00（Asia/Shanghai；精确值见文件 mtime）
- 授权依据：Issue #4 评论 6622447995（A 类 VSPAERO7-thin-LF cap 20、本批 ≤6）
- 本批实际执行：4/6 次（NA-D12D005-001..004，全部计费；retries=0）
- 本次修复的求解器启动：**0**；A 批启动计数保持 4/6
- 相关复核：A5 task-110（S3 证据快速评估）verdict = `CONTINUE_S4_S5`（0 blocker / 2 major / 3 minor）

## 1. A 批 4 次启动的实际结果

| 事件 | 案号 | 结果 | CLtot | CDi | CDtot | 关键证据 |
| --- | --- | --- | --- | --- | --- | --- |
| NA-D12D005-001 | S0_STD_M0p1_base | SOLVED_VALID | 0.126545 | 0.001314 | 0.020947 | Re=239352.080013 匹配；verify-polar/verify-history rc=0 |
| NA-D12D005-002 | S1_STD_M0p1_wn128 | SOLVED_VALID | 0.134635 | 0.001523 | 0.021168 | 仅 NumWakeNodes=128；CL 更接近 Helmbold 0.1355 |
| NA-D12D005-003 | S2_STD_M0p1_wi0 | SOLVED_VALID | 0.126555 | 0.001315 | 0.020947 | 仅 WakeIters=0；相对 S0 ΔCLtot=+7.6e-06（几乎冻结） |
| NA-D12D005-004 | S3_STD_M2p02_base | 停止触发（主系数有限，派生列非有限） | 0.074251 | 0.002607 | 0.013789 | polar 第 4 行 Ew=inf；history 5 步稳定；S4/S5 NOT_RUN_AFTER_ABORT |

A2 按 run_start 的 `stop_rule_1`（任何非有限 token）立即停批，属**保守正确**；A5 复核 `STOP_CONFIRMED=false`，即这不是已确认的物理发散。

## 2. 两个独立事实（不得混淆）

**事实 1（数值/工具层）：`Ew=inf` 是派生列除零伪影。**
S3 的 `CDiw=0`，而 `Ew = CLtot^2 / (π·AR·CDiw)` 为派生比；同一 polar 行的主系数 `CLtot=0.074251`、`CDi=0.002607`、`CDtot=0.013789` 全部有限，history 5 次迭代平滑收敛（末步相对变化 2.47e-4），CL 与线化超声速理论区间 0.0673–0.0796 一致。v2 旧版把派生列判为致命 `POLAR_NONFINITE`，导致 S3 被标 `FAILED_INVALID_POLAR`。

**事实 2（语义层）：`CDo/CDtot` 是 VSPAERO 内部寄生估算，不是真实阻力。**
同一 48 列 polar 中 `CDo` 与几何/Re 相关、在零升力时仍非零：D-12D-004 归档 6.2 polar 在 AoA=0、CL≈0 时 CDo=5.028233e-03、AoA=2° 时 5.082831e-03；量级随 Re 单调（12D 翼 Re≈8.94e7 → 0.0050；标准翼 S3 Re≈4.83e6 → 0.01118；S0 Re≈2.39e5 → 0.01963）。因此 `CDtot` 不能当作真实阻力或优化目标，只能做模型内相对比较；主判据用 CL（线化理论）、CDi（`CL²/(πAR)` 量级）、符号/量纲/收敛/尾迹有界。

## 3. 本次零求解修复（v2 runner rev3 + evidence revision 4）

| 项 | 内容 |
| --- | --- |
| 授权/依据 | A5 task-110 条件 ②「v2 分离主/派生列或书面豁免 Ew，并重跑 S3 verify-polar」 |
| 代码 | `scripts/vspaero7_runner_v2.py` rev3（SCHEMA `d12d005-runner-4`）：新增 `POLAR_DERIVED_NONFINITE_COLUMNS=("Ew",)`、`validate_polar_file(..., allow_nonfinite_columns=...)`、CLI `--allow-nonfinite-derived`；白名单列非有限 → `PASS_WITH_WARNINGS` + `derived_column_warnings`；非白名单/主系数非有限 → 仍 `POLAR_NONFINITE`；未知白名单列 → `POLAR_ALLOWLIST_UNKNOWN_COLUMNS` |
| 测试 | `scripts/test_vspaero7_runner_v2.py` rev3：**51 tests OK**（新增 5 项），日志 `evidence/a0/v2rev3_test_run.log` |
| S3 复算 | `scripts/vspaero7_runner_v2.py verify-polar --allow-nonfinite-derived` → `PASS_WITH_WARNINGS`（唯一非有限 token：第 4 行 Ew=inf），输出 `evidence/lead/s3_verify_polar_allowlisted.json` |
| verifier | `scripts/a0_verify_cases.py` revision 4：**264 checks PASS / 0 failed**；求解产物检查改为「A0 子树零求解 + 求解产物只允许在 evidence/v1」 |
| 文档 | `evidence/a0/ld002_parser_fix.md` §1/§3.1/§4/§5/§6/§8/§10 与 `evidence/a0/README.md` §5/§7/§9/§12/§15 同步 |
| 求解计数 | 0（未启动 vspaero/SU2/Mission；未改写 A2 冻结的 `evidence/v1/*`） |

## 4. 对 S4/S5 的约束（A5 条件 ③/④）

- S4/S5 结果只作 `VSPAERO_INTERNAL_ONLY`，`physical_validation = NOT_VALIDATED`；不得据此宣布 LF-M2.02 通过，也不得把 `CDtot` 当真实阻力或优化目标。
- 停止规则修订：只有**主系数**（`CLo/CLi/CLtot/CDo/CDi/CDtot/CM*`）非有限、发散或出现负阻力时才停；派生列非有限降级为 WARNING，不触发停批。
- 剩余 2 次启动须 Lead 重新书面授权（`evidence/lead/batch1b_reauthorization.md`），且该授权在 A5 delta 复核通过后方可生效。

## 5. 预算与账本状态（截至本次修复）

| 项 | 值 |
| --- | --- |
| A 类总 cap | 20 |
| 本批（batch 1）cap | 6 |
| 已用 | 4（NA-001..004 全部 billable；retries=0） |
| 本批剩余 | 2（S4/S5；A2 已按 stop 冻结为 NOT_REALLOCATED，本修复不改冻结状态） |
| A 类总剩余 | 16（4/20 已用） |
| B/C 线 | 0/12、0/4（LOCKED） |
| 求解器进程 | 0（本次修复期间） |
