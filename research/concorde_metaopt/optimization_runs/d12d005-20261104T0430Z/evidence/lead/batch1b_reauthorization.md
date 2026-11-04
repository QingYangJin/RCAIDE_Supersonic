# D-12D-005 A 批第一批剩余 2 次启动的重新授权（Lead 书面授权，条件生效）

- 授权编号：D-12D-005-BATCH1B
- 授权人：Lead（本文件即书面授权；后续 Issue 回执引用本文件路径与 sha256）
- 授权时间：2026-11-04T16:00+08:00 左右（Asia/Shanghai；精确值见文件 mtime）
- 依据：Issue #4 评论 6622447995（A 类 VSPAERO7-thin-LF，cap 20，本批 2 次、A 类累计至多 6）；A5 task-110 verdict CONTINUE_S4_S5（0 blocker / 2 major / 3 minor，STOP_CONFIRMED=false）
- 生效条件（**已满足并生效**）：Lead 书面授权 task-124（2026-11-04T10:16:19Z，Issue #4 评论 6622447995）、A5 task-120 对 target 0e62db3 判 APPROVE_FOR_BATCH1B（blocker 0 / major 0 / minor 3）、A3 task-121 PASS。旧文引用的 task-111/task-116 为过期文本，按 B1B-m04 更正；A5 task-125 对执行后 BATCH1B 的 CHANGES_REQUESTED 属 post-hoc 复核，处置见 evidence/v1b/corrections/batch1b_corrections.json。

## 1. 授权范围（严格）

1. 仅允许 **2 次**真实 VSPAERO 7.2.2 thin-LF 启动：先 `S4_STD_M2p02_wn128`，后 `S5_D12_M2p02_base`；不得增补、不得换案、不得重试。
2. 不得使用 B 类（RCAIDE 低保真 12 次）、C 类（SU2 Euler 4 次）、D/E 类或 P4 真实计算额度；B/C 维持 LOCKED。
3. 本批冻结的剩余 2 次现重新释放为 S4/S5 专用；失败/超时/重启/补跑**均计费**，用满即关闭，不结转、不重分配。
4. A 类总 cap 20 不变：当前已用 4，本次最多至 6；剩余 14 须按 Issue #4 规则（先开第一批、A5 审阅定位证据后释放）另行批准。

## 2. 硬限制

- 串行；≤4 核；≤16 GB RAM；单次启动 ≤900 s；轮次墙钟 ≤24 h（自授权生效起算）；仅本机；无付费云。
- 每案启动前必须用 v2 rev5 runner（`d12d005-runner-5`）`check-case-dir`（含 7 文件 bundle、vkey 绝对路径、17 字段回读、StopBeforeRun=1）得 `status=PASS`。
- 每案启动后必须用 v2 rev5 `verify-polar`（`--expect <case>/expected.json --allow-nonfinite-derived`）与 `verify-history` 复核；任何主系数非有限/发散/负阻力按停止规则处理。
- 每案须由 A2 逐案记账（19 字段、append-only），并记录实际命令、SHA、wall time、RSS/CPU 观测。

## 3. 停止规则（按 A5 条件 ④ 修订）

1. **主系数**（`CLo/CLi/CLtot/CDo/CDi/CDtot/CMox..CMztot`）出现非有限、数量级发散（|CLtot|>10 或 |CDtot|>10）或负阻力 → 立即停批，后续案 `NOT_RUN_AFTER_ABORT`。
2. **派生列**（`Ew`、`LoDw` 等）非有限 → 记 WARNING，不触发停批（需在案结果中显式标注）。
3. 单案墙钟 >900 s 或 >600 s 仍未收敛（S4/S5 任一）→ 停止该案并停批；不得自行重试。
4. 求解器进程残留、RSS >16 GB、CPU >4 核 → 立即停止整批。
5. 用满 2 次 → 本批关闭。

## 4. 证据与标注要求

- S4/S5 证据目录不得改动 A2 已冻结的 `evidence/v1/`（batch1 的 4 案与 manifest 保持不变），应写入新目录（建议 `evidence/v1b/`）并在 `summary` 中汇总本批 6 案（4+2）状态。
- S4/S5 一律标注 `VSPAERO_INTERNAL_ONLY`、`physical_validation = NOT_VALIDATED`；`CDo/CDtot` 不得作为真实阻力或优化目标，不得据此宣称 LF-M2.02 通过。
- S3 的 `Ew=inf` 修复记录与 allowlist 复算输出（`evidence/lead/s3_verify_polar_allowlisted.json`）必须随包。
- 结果须交给 A5 独立复核（新任务）后再进入 Issue #4 回执；Lead 是唯一 GitHub 发布者。

## 5. 与 P4 线的接口

- 本批任何数值均**不得**作为 P4/Issue #5 的训练标签或真实航空真值；P4 仍物理 0。
- 与 #4/#5 的交接字段：`task_id/design_set/evaluator_id/fidelity/source_kind/physics_validation_status/solver_version/mission_fingerprint/constraints_g_le_zero/physical_call_count`。
