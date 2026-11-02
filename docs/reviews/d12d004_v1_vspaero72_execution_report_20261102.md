# D-12D-004 · V1 轮（VSPAERO 7.2.2 thin-LF）执行报告

- 日期：2026-11-02
- 授权：Issue #4 评论 6569140757（D-12D-004），仅 A 类 A-VSPAERO7-thin-LF，≤10 次真实启动；B/C/D/E/P4 真实计算全部 0；D-12D-002 的 23/23 已封账不结转。
- 分支 / worktree：research/d12d004-vspaero7 @ D:/RCAIDE-d12d004（基线 f8506c9 = V0 门禁提交）
- run 目录：research/concorde_metaopt/optimization_runs/d12d004-vspaero72-lf-20261102T0500Z/
- 执行者：A2（run-opt）；授权与停止裁决：Lead。

## 1. 执行摘要

- V1 轮共消耗 **4 次真实启动（4/10）**：NA-D12D004-001 = V7-00 attempt1（打包缺陷，0.024 s 失败）、NA-D12D004-002/003 = V7-01 两次（120.0 s 中止、600.331 s 超时发散）、NA-D12D004-004 = V7-00 attempt2（76.891 s，非物理）；**剩余 6 次 CLOSED，不结转、不重分配**。
- V7-00（标准薄翼 Mach 0.10 卫生检查）：solver rc=0、76.891 s，但系数非物理——**CLtot = −2801.885568189672、CDtot = −376.365943305457（负阻力）、CDi = −367.353142529815**；`.history` 在 wake 迭代 2–3 即发散，polar 不可用。
- V7-01（标准薄翼 Mach 2.02 适用性探针）：第一次尝试被外层 120 s 工具期限中止（运行器缺陷，已修并记录），第二次 600.331 s 超时；`.history` 达到 O(1e18)–O(1e24)，无 `.polar`。**触发 D-12D-004 停止规则**。
- 停止规则由 NA-D12D004-003 触发：`evidence/v1/stop_decision.json` 在 **06:25:27Z 冻结**（计数 3/10、remaining 7、retries 1、V7-02…V7-09 全部未执行）；随后 Lead 裁决 (a)（消息 m01190/m01194，见该文件 `lead_decision`）**追加授权并仅追加授权 1 次 V7-00 必要重试**，A2 于 **06:26:57Z 启动 NA-D12D004-004**、06:28:14Z 结束（76.891 s，rc=0 但非物理），最终计数 **4/10、remaining 6、retries 2**；此后**未再启动任何求解器**，无 vspaero.exe 残留进程。冻结快照 3/7/1（`counters_after_stop`）与终态 4/6/2（`counters_after_retry` / `budget_final`）同时保留在该 JSON 中。
- 结论：**LF-M2.02 阻力维持 NOT_VALIDATED**；VSPAERO 7.2.2 thin 在 Mach 2.02 不是可用的物理方法；本轮不产生任何可用于上游优化/元学习的真实标签。

## 2. 每个算例的结论

| # | case | 组 | Mach | 状态 | 关键结果 |
|---|---|---|---|---|---|
| 1 | V7-00 | S | 0.10 | FAILED_NONPHYSICAL_VALUE | rc=0，76.891 s；CLtot −2801.89 / CDtot −376.37 / CDi −367.35；history 发散；LD-002 校验器表头不兼容（独立缺陷） |
| 2 | V7-01 | S | 2.02 | TIMEOUT_DIVERGED | 120.0 s 中止 + 600.331 s 超时；history O(1e18)–O(1e24)；无 polar |
| 3 | V7-02 | M | 2.02 | NOT_RUN_AFTER_ABORT | 12D 基线 tess 8/17 setup 已零求解生成，未执行 |
| 4 | V7-03 | M | 2.02 | NOT_RUN_AFTER_ABORT | 12D 基线 tess 16/33（V0 资产），未执行 |
| 5 | V7-04 | M | 2.02 | NOT_RUN_AFTER_ABORT | 12D 基线 tess 32/65，未执行 |
| 6 | V7-05 | P | 2.02 | NOT_RUN_AFTER_ABORT | W01 面积 +1%，未执行 |
| 7 | V7-06 | P | 2.02 | NOT_RUN_AFTER_ABORT | W03 后掠 +1°，未执行 |
| 8 | V7-07 | P | 2.02 | NOT_RUN_AFTER_ABORT | W10 翼尖扭转 +2°，未执行 |
| 9 | V7-08 | D | 2.02 | NOT_RUN_AFTER_ABORT | AoA 0/2/4 setup 已生成，未执行 |
| 10 | V7-09 | D | 2.02 | NOT_RUN_CONDITION_NOT_TRIGGERED | 条件唤醒敏感性，前置条件未满足 |

## 3. 两个独立事实（不得混为一谈）

1. **数值非物理**：V7-00/V7-01 的极性/历史显示求解发散或严重违反正阻力/正升力卫生判据；这是求解结果层的事实。
2. **校验器缺陷 LD-002**：VSPAERO 7.2.2 的 polar 表头是 CLo/CLi/CLtot、CDo/CDi/CDtot，而 V0 版运行器按 6.2 的 CL/CDi/CDtot 解析，导致 V7-00 报 POLAR_HEADER_MISSING；这是工具缺陷，已记录并需在后续轮次修复解析器。二者独立：即使修复解析器，V7-00 的数值仍然非物理。

## 4. 根因静态核对（零求解）

- 复核 OpenVSP 3.55 官方 API 与示例：`SET_NONE=-1`、`SET_ALL=0`；官方 `test_vsp_api.py:1450-1463`、`1524-1536` 使用 `GeomSet=SET_NONE` + `ThinGeomSet=SET_ALL`；已生成 `geom_result_thin.csv` 的 **8 个** V7 case（V7-03 无该文件、V7-09 目录不存在）均为 `GeometrySet=-1`/`ThinGeometrySet=0`。
- 结论：**VSPGEOM 就是官方 thin 路径**，本轮非物理不是『误用了厚网格』；官方 `Uber_eCRM-002` 示例是 DegenGeom + `.groups` + `-unsteady` 多旋翼非定常案例，不能反证 VSPGEOM 路径错误。
- 因此未执行额外的 DegenGeom 诊断启动；剩余预算仍为 6 次（CLOSED）。发散根因未定：`NumWakeNodes=8`/`WakeIters=5`（对方官方示例为 128/0）只是未经证明的疑点，需新的设置研究授权。

## 5. 预算与合规

- starts_used = 4 / cap 10（其中 1 次为 stop 冻结后由 Lead 裁定 (a) 追加授权的 V7-00 重试 NA-D004）；remaining = 6（CLOSED_NOT_CARRIED_OVER_NOT_REALLOCATED）；retries_used = 2；billable_events = 4；serial、≤4 核、≤8 GB、单次 ≤600 s、本轮总墙钟约 22 分钟（远低于 6 h）。
- 未启动 B（thick）、C（WaveDrag/面积律）、D（SU2）、E（RCAIDE Mission）任何一次；P4 真实计算 0。
- 未改动源码/测试文件（仅 run 目录内的 config/evidence/matrix 记录文件）；未伪造数据；所有数字可回溯到 solver_ledger.jsonl / case_results.json / .polar / .history。

## 6. 门禁影响

| 门禁 | 状态 | 说明 |
|---|---|---|
| GEO-12D | PARTIAL | 文档化已缓解，校准继承未闭合 |
| LF-M2.02 | **NOT_VALIDATED** | V1 未产生任何物理可信结果；VSPAERO 7.2.2 thin 在 Mach 2.02 判为不可用物理方法 |
| HF-M2.02 | PARTIAL | 维持 Round-1（SU2 只算机翼） |
| BODY-CORR | BLOCKED | 无可信面积律/机身修正；严禁注入 |
| MISSION-DATA | PARTIAL | 无新真实标签 |
| BUDGET | CLOSED_FOR_V1 | V1 4/10 用尽本轮，剩 6 次不结转 |
| APPROVED_FOR_NEXT_STAGE | NOT ISSUED | 仅负责人可签发 |

## 7. 证据与文件

- run 目录：`research/concorde_metaopt/optimization_runs/d12d004-vspaero72-lf-20261102T0500Z/`（config/run_config.json、actual_solver_budget.json、solver_case_matrix.csv；evidence/v1/{README.md, case_prep.json, case_results.json, per_case_conclusions.md/.csv, run_start.json, stop_decision.json, root_cause_static_check.json, v7_01_divergence.json, vkey_fix.json, wrapper_deadline_fix.json, tooling_events.json, ledger/solver_ledger.jsonl, setup_gen/}；summary.json；lf_vspaero_results.json；data_manifest.json 122 文件 3,154,507 B）。
- 原始求解产物（polar/history/adb/lod、.vspgeom 等）归档于 `D:/RCAIDE/outputs/concorde_metaopt/d12d004-vspaero72-lf-20261102T0500Z/raw_artifacts/`（outside_git，manifest 引用）。

## 8. 不声明事项（explicit non-claims）

- 不声明 LF-M2.02 阻力已获得可信数值；不声明任何 12D 敏感性结论；不声明 VSPAERO 7.2.2 完全不可用（只声明 thin 在 Mach 2.02 不可用物理方法、且本轮 Mach 0.10 卫生检查也未通过）。
- 不声明 D-12D-004 预算已用满；不声明剩余 6 次可结转；不声明 V1 可作为 P4 真实标签。

## 9. 需负责人决策

1. 是否另行授权一次 VSPAERO 7.2.2 设置研究（NumWakeNodes/WakeIters/收敛参数/网格尺度，建议 ≤2 次启动、单独立账，不与本轮混算）。
2. 若不授权，LF-M2.02 是否按 NOT_VALIDATED 关闭并改走备用低保真方法（例如基于理论的阻力工程估算），该决定影响 P4 真实标签与本项目后续门禁。
3. 是否批准修复 LD-002 解析器缺陷（零求解，属工具修复，不影响预算）。
