# D-12D-005 BATCH1B 证据目录（S4 → S5）

status: **BATCH1B_COMPLETED**（2026-11-04，2/2 starts，0 retries，未触发停止规则；结果见 §7）  
run_id: d12d005-20261104T0430Z  
创建时间 (UTC): 2026-11-04T09:03:25Z  
求解器: VSPAERO 7.2.2 thin（`-omp 4`），exe sha256 `db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad`；仅升力面，机身不在求解域。
runner: 上级 scripts/vspaero7_runner_v2.py，版本 `d12d005-runner-5`，sha256 `0c27d05f047d20e9bfc32b4ab27d687c261461b4feb9af5b97247089189f9377`；准备时 HEAD `69e2e03`，执行时 HEAD `0e62db35b4722154e1bbe8706d222cae230e1d33`。

## 1. 范围

- 本批（BATCH1B）**仅 S4 → S5 两案**，串行执行：
  - S4_STD_M2p02_wn128：标准矩形翼，Mach 2.02，仅 NumWakeNodes=128（与 S3 单因素对照）。
  - S5_D12_M2p02_base：12D 主翼（wing-only），Mach 2.02 基线。
- 不重跑 S0/S1/S2/S3；不新增其他 case；每题最多 1 次启动，**无重试**（除非 Lead 届时另行书面批准并明确计费）。
- 预算：A 类总 cap 20；A 批已用 4（v1 中 remaining 2 已关闭、不结转）；BATCH1B 拟用 2 次，剩余 16。失败/超时/中止均计 1 次。

## 2. 授权生效条件

本目录在收到 Lead **书面授权消息** 前不得启动任何求解器。BATCH1B 的实际生效授权（全部满足后才执行）：

1. Lead 书面授权 task-124（2026-11-04T10:16:19Z，Issue #4 评论 6622447995），明确 S4→S5 案序、预算（本批 2 次、A 类累计至多 6）与停止规则。
2. A5 task-120 对 target 0e62db3 判 APPROVE_FOR_BATCH1B（blocker 0 / major 0 / minor 3）。
3. A3 task-121 隔离复核 PASS。

说明（B1B-m04 更正）：旧文引用的 A5 task-116/task-117 为过期文本；A5 task-125 对执行后的 BATCH1B 判 CHANGES_REQUESTED，属 post-hoc 复核，处置见 corrections/batch1b_corrections.json。

## 3. 停止规则（修订版）

**仅在以下情况停止整批**：

- 主系数（CLo/CLi/CLtot/CDo/CDi/CDtot/CMxtot/CMytot/CMztot/CLwtot/CDwtot 等）出现 NaN/INF/IND；
- history 迭代出现 NaN/INF/IND（数值发散）；
- 回读/校验失败、默认值泄漏、单次 >900s、RSS >16GB、核数 >4、A 类 starts 达到 20。

**派生列（Ew，以及同类派生效率/比值列）非有限值仅记 WARNING，不停止、不计为失败**，但必须在 case_summary 与逐案结论中显式标注，不得把含 WARNING 的 polar 当作已物理验证证据。

## 4. 证据标签与门禁

- 本批所有输出的标签固定为 **VSPAERO_INTERNAL_ONLY**；`physical_validation` = **NOT_VALIDATED**。
- 不得用于：全机阻力/燃油结论、body correction、validated fuel label、升力波阻/诱导阻力双计判定。
- 与 D-12D-004 V1 的关系：V1 在 M2.02 数值发散（600s 超时）；A 批 S3 在 M2.02 出现派生列 Ew=inf 但主系数有限。BATCH1B 的 S4/S5 用于区分「数值不稳定」与「纯派生列退化」，仍属内部诊断。

## 5. 记账要求

- 每次启动前写 pending 事件到本目录 ledger.jsonl（append-only，19 字段），启动后立即补 COMPLETED；失败/超时同样写 COMPLETED 并计费。
- 每案证据写入 evidence/v1b/cases/<case>/：case 根下 polar、history、solver_stdout.log、solver_stderr.log；bundle/ 下模型文件（.vspaero/.vspgeom/.vkey/.vsp3/.csf/.adb/.lod/.group.* 等）、geom_result_thin.csv、expected.json 与求解器日志。
- 启动前必须通过 vspaero7_runner_v2.py check-case-dir（本批 S4/S5 已 PASS，见 EXT d12d005/a2/v1b_prep/bundle_check/）。
- 实际冻结布局（冻结已完成，不再有“冻结后写”步骤）：顶层 case_summary.json、final_checks.json、per_case_conclusions.json、data_manifest.json、corrections/batch1b_corrections.json、README.md（本文件），以及 cases/ 原始证据树；raw 证据字节不改。

## 6. 边界

- 本目录创建为零求解准备：0 次求解器启动、0 次 commit/push、0 次 GitHub 写。
- 本目录不修改 evidence/v1/ 下任何冻结文件。
- 未获授权前不得移除本目录的 PREP_READY 状态、不得写 solver 证据。

## 7. 执行结果（BATCH1B_COMPLETED，2026-11-04）

- 授权：Issue #4 评论 6622447995；Lead task-124（S4->S5 仅 2 次、无重试）；A5 task-120 APPROVE_FOR_BATCH1B（target 0e62db3，blocker 0 / major 0 / minor 3）；A3 task-121 PASS。
- 实际启动：2/2（S4 NA-D12D005B-001、S5 NA-D12D005B-002），串行、rc=0、wall 28.314 s / 0.514 s、峰值 RSS 3.493 / 0.075 GB，均未超时；0 重试；未触发停止规则。
- 主系数（全有限）：S4 CLtot=0.074250958215、CDi=0.002606535876、CDtot=0.013789403504；S5 CLtot=0.070832611794、CDi=0.002488240979、CDtot=0.009796560997。
- Ew=inf（两案）：CLiw=CDiw=0 导致派生比值 0/0，判 DERIVED_RATIO_NONFINITE_ALLOWED；verify-polar 均 PASS_WITH_WARNINGS，verify-history 均 PASS，history 各 5 次迭代。
- S4 vs S3（仅 NumWakeNodes 8->128；单次运行各一、不声称可重复）：CLtot 绝对差 -7.3568e-08（相对 -9.908e-07）、CLi -7.357e-08、CDi -4.351e-09、CDtot -4.42e-09、CDo -7e-11，均为 1e-8 量级（CDo 为 1e-11）；描述性差异显示该工况下尾迹节点数 8->128 对主系数无实质影响；与亚声速 S1（+6.4% CLtot）形成对照。S5 与 S4 为跨几何/跨 Re 对比，不作因果归因。
- 预算：A 类 4/20 -> 6/20（本批 2/2，retries 0，billable 2）；剩余 14 未授权、不结转、不重分配。
- 标签：VSPAERO_INTERNAL_ONLY；physical_validation=NOT_VALIDATED；不改变 LF-M2.02=NOT_VALIDATED，不签发 fuel label，不注入 body correction。
- 证据：本目录（ledger.jsonl 4 行、run_start.json、batch_state.json、budget_ledger.json、cases/）；外部 C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/batch1b/（analysis/results_summary/report/commands.log/solver_output）。
- 本目录自此不再需要授权；任何后续启动必须另行书面批准并计入 A 类剩余 14 次。

## 8. 修订历史与冻结（A1 task-129，2026-11-04，零求解）

- **v1b-1（执行时）**：本 README 记录 BATCH1B 执行结果（2/2 启动、0 重试）。
- **v1b-2（A5 task-125 复核后）**：按 A5 的 B1B-m01..m06 零求解修订：§2 授权生效条件改为真实授权（Lead task-124、A5 task-120、A3 task-121；旧 task-116/task-117 为过期文本）；§5 改为实际冻结布局；§7 的 S4 vs S3 差值改为精确绝对/相对值并明确单次运行、不构成可重复性结论。
- **冻结包**：data_manifest.json（schema d12d005-v1b-manifest-1，raw + canonical-LF 双形态 sha256/bytes）由 scripts/freeze_v1b_evidence.py 生成，--verify --source git --rev HEAD 可从 committed blob 100% 复现；另有 case_summary.json、final_checks.json、per_case_conclusions.json、corrections/batch1b_corrections.json。
- 本次修订零求解、未改动任何原始求解器证据字节。
