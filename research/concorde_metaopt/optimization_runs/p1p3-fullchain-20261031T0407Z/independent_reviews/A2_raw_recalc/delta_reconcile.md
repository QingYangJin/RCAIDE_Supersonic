# A2 差异闭环复核 — 529d9b7（X2/X3/X4）

- 任务：task-31 / FULLCHAIN-DELTA-A2-529d9b7（A2 = a2-run-opt）
- 模式：只读静态复核；**0 次求解器启动、0 次仓库写、0 次 GitHub 写**
- 基准 worktree：`D:/RCAIDE-verify-a2-final`，HEAD `529d9b7cab6509b276533aa29a361e32a22122cf`，`git status --porcelain` 为空（0 改动）
- 前置提交：d80b4c4（执行 23/23）→ 58933bb（归档独立评审+修复）→ 529d9b7（canonical LF 清单）
- 脚本：`EXT/fullchain/a2/scripts/delta_check_31.py`；结构化结果：`EXT/fullchain/a2/delta_reconcile.json`
- 结果：**9/9 检查 PASS；X2/X3/X4 全部关闭；d80b4c4→529d9b7 无数值变化；预算 23/23 不变。**

## 结论

| 项 | 状态 | 关键证据 |
|---|---|---|
| X4（manifest CRLF 哈希不可复验） | **CLOSED** | 529d9b7 的 data_manifest 改为 canonical LF 哈希；在干净 LF checkout 上重算 **67/67 文件 0 mismatch**（合计 1,290,937 B == manifest total_bytes）；run-time CRLF ledger 32,677 B / sha256 `d064d93f…` **精确等于** d80b4c4 已提交 LF ledger（31,911 B，766 个 LF）做 LF→CRLF 转换的结果，机制写入 `line_ending_note` |
| X2（主 checkout ledger 未提交） | **CLOSED** | 含 **11 个 mesh_generation_events（MG-001…MG-011）** 的 ledger（42,222 B canonical LF，sha256 `0b9acc2e…`）已在 58933bb 提交、529d9b7 为同一 blob；D:/RCAIDE 工作副本 43,240 B（CRLF）LF 规范化后与提交版 **逐字节一致**，git status 该路径干净 → 无遗留未提交内容，仅行尾差异 |
| X3（EXT 源文件归档后被编辑） | **CLOSED（归档完好）** | raw 归档 `outputs/.../hf_raw/wedge/hfs00_analysis.json` = 1,915 B / sha256 `01a61f47…`，与 raw_manifest 条目完全一致；EXT 工作副本 1,913 B / `084adf09…` 是归档后编辑，属工作副本、非证据 → 证据完整性不受影响 |

## 逐项检查（9 项）

1. **D0 PASS** — worktree 在 529d9b7、porcelain 空、58933bb 为其祖先。
2. **D1 PASS（X4）** — data_manifest `file_count=67`、`files` 67 条，干净 LF checkout 逐文件 sha256+size 全部匹配：**67 matched / 0 mismatch / 0 missing**，磁盘字节和 1,290,937 == `total_bytes`。manifest 声明 `hashing_convention = sha256 over committed worktree bytes (git canonical LF line endings)`，`revision = post-review revision (independent reviews archived, stationarity wording corrected, mesh events backfilled, manifest canonicalized)`。
3. **D2 PASS（X4 机制）** — 取 d80b4c4 提交中的 ledger blob（LF，31,911 B，766 个 LF）→ LF→CRLF 转换 = **32,677 B**，sha256 = **d064d93fd14b865fd90d823cd0538f4d81d5facc115b89680ec9e2687f697454**，与 manifest `line_ending_note` 中的 run-time CRLF 值完全一致。
4. **D3 PASS（X2/X4）** — 58933bb 的 ledger blob sha256 `0b9acc2e13f053ee70e94471a9b00c2ef9bdad65c5e358a41a6b456a6161fd8a`（42,222 B LF）== 529d9b7 同 blob；`mesh_generation_events` 列表 **11 条**（MG-001…MG-011，含 wing coarse/medium/fine 与机身/远端网格）；data_manifest 顶层 `mesh_generation_events=11`；ledger `totals={cap:23, used:23, remaining:0}`。
5. **D4 PASS（X3）** — 见上表；raw_manifest 155 文件口径不变。
6. **D5 PASS（无数值变化）** — d80b4c4→529d9b7 仅改动 14 个路径，全部为预期台账/文档：README.md、approval_and_budget_ledger.json、data_manifest.json、hf_su2_results.json、raw_artifacts_manifest.json、summary.json + `independent_reviews/`（8 文件）。**mission_e2e.json、lf_vspaero_results.json、wave_drag_area_rule.json 及 evaluations.jsonl、mesh_convergence.csv、density/wave CSV、drag_component_ledger、geometry_validation、toolchain、run_config、blocker_register、figures/ 全部逐字节不变**（无 unexpected 改动）。hf_su2_results.json 仅新增 4 个说明字段（`revision_note`、`wing_stationarity_note`、HFS-02/HFS-03 `force_stationarity_note`），**0 个数值差异**；summary.json/raw_artifacts_manifest.json 的递归数值 diff 也均为空。
7. **D6 PASS（预算）** — evaluations.jsonl 仍 23 行（VSPAERO_LF 6 / WAVE_AREA_RULE 7 / RCAIDE_LF 4 / SU2_HF 6）；mission_e2e.budget_accounting：cap_total=23、events_recorded=23、remaining=0。
8. **D7 PASS（X2）** — main checkout ledger 43,240 B（CRLF）LF 规范化后 42,222 B / sha256 `0b9acc2e…` 等于 529d9b7 提交 blob；`git status --porcelain <path>` 无输出。
9. **D8 PASS** — data_manifest `independent_reviews` 记录 roles=[A1..A5]，干净 checkout 上 8 个评审文件全部存在（README + A1 报告、A2 reconcile.json/md、A3 报告、A4 矩阵、A5 recalc/verdict）。

## 边界与限制

- 本轮只验证台账/版本闭环与“评审修订无数值变化”，**未重跑任何物理求解器**，不构成新的物理验收；LF_M2_02=NOT_VALIDATED、HF_M2_02=PARTIAL、WAVE_AREA_RULE=NOT_VALIDATED、mission_data_gate=PARTIAL、validated_aircraft_fuel_label=false 均不变。
- “clean LF checkout 重哈希”针对 529d9b7 提交内容；该提交之后若再有工作区编辑需重新生成清单（manifest 已写明 regenerate 规则）。
- X3 的 EXT 工作副本仍与归档不同，若未来把 EXT 路径当证据来源需重新同步；归档（outputs/…/raw）才是证据。

## 交付

- `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a2/delta_reconcile.md`（本文件）
- `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a2/delta_reconcile.json`（结构化：9 检查 + closure X2/X3/X4 + stationarity + 评审归档）
- `.../a2/scripts/delta_check_31.py`、`delta_check_31.json`（原始检查输出）
