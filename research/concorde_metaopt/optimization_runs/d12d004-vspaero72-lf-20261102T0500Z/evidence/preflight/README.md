# evidence/preflight — 启动前三门禁证据占位（D-12D-004）

状态：**EMPTY_PLACEHOLDER / 门禁未通过 / 0 启动**。

本目录用于存放 A2 之外的三个门禁证据，A1 完成后再允许第一次 `vspaero.exe` 启动：

1. **A1 — runner 修复与本地测试**
   - 文件建议：`A1_runner_fix_log.md`、`A1_test.log`、`A1_harness_sha.txt`（含 runner 40 位 commit SHA）
   - 必须证明：LD-001 修复（`.vspaero` 每字段 `key = value`）、setup 返回码检查、polar NaN 检测、Sref/Re 注入与回读断言全部覆盖，且中→细网格判据逻辑有单元测试。
2. **A5 — 独立复核**
   - 文件建议：`A5_review.md`、`A5_verdict.txt`
   - 必须给出：批准/拒绝、批准的具体 runner SHA、复核人（独立 agent）与时间；只有批准 SHA 可被 `run_config.json` 引用。
3. **A3 — 二进制与 worktree 隔离**
   - 文件建议：`A3_isolation_report.md`
   - 必须证明：仅使用 `D:/OpenVSP-3.55.0` 下 vspaero 7.2.2（sha256 `db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad`），旧 3.26.1 vspaero 6.2.0 只读未被调用/覆盖；worktree `D:/RCAIDE-d12d004` 与主库 `D:/RCAIDE` 隔离；raw 输出只写 gitignored 的 outputs 路径。

## 规则

- 门禁全部通过前，**任何求解器启动都是违规**；不产生计费事件，也不产生证据。
- 门禁通过后，把 `config/actual_solver_budget.json` 的 `preflight_gates.*` 更新为 true（`gates_passed=true`），并把对应证据文件路径记入该 JSON 的 `preflight_evidence` 字段（由 runner 追加）。
- 本占位文件本身不构成门禁通过证据。
