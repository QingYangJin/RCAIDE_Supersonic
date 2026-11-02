# Task-26 独立复核：p1p3-fullchain 交付证据（EXECUTED_NO_GATE_APPROVED）

- 任务：FULLCHAIN-A5-INDEPENDENT-RECALC-d80b4c4（team task-26）
- 被审对象：`D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z/`、`docs/reviews/p1p3_fullchain_validation_report_20261031.md`、raw artifacts `D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/`
- 被审 commit / worktree：HEAD `d80b4c4`（干净 detached worktree `D:/RCAIDE-verify-fullchain-a5`，porcelain 0）
- 日期：2026-10-31；复核人：A5（独立会话）；本轮 0 solver 调用（D-12D-002 预算 23/23 已耗尽）

## 1. 独立复算：SU2 尾窗积分（PASS）

从 `hf_raw/HFS-02|HFS-03/history.csv` 尾窗 200 iteration 重算，并从 `surface_flow.csv`（wall triangles）按 `p=(gamma-1)(E-0.5*mom^2/rho)`、`Cp=(p-p_inf)/q_inf`、`p_inf=7171.544888256813`、`q_inf=20483.94023343017`、`Sref=358.25`、AoA=2.8398297488947493 deg、风轴 `D=Fx cos a+Fz sin a`、`L=-Fx sin a+Fz cos a` 重新积分，与 `hf_su2_results.json` 对比（mean 与 peak-to-peak 共 6 个分量）：

| case | 量 | A1 JSON mean | A5 重算 mean | abs_diff | A1 rel p2p |
| --- | --- | --- | --- | --- | --- |
| HFS-02 | CD | 0.006819724039999985 | 0.006819724039999985 | 0.0 | 3.2259369709177243e-09 |
| HFS-02 | CL | 0.09277659982000022 | 0.09277659982000022 | 0.0 | 4.742575277643825e-09 |
| HFS-02 | CMy | -0.038076134449999854 | -0.038076134449999854 | 0.0 | 6.303161007456263e-09 |
| HFS-02 | CMx/CMz/CEff p2p | — | — | 0.0 | 4.63e-07 / 4.09e-08 / 1.47e-09 |
| HFS-03 | CD/CL/CMy/CMx/CMz/CEff | — | — | 0.0 | 4.50e-06 / 2.74e-06 / 5.05e-06 / 3.58e-03 / 1.86e-04 / 1.76e-06 |

HFS-02 壁面压力积分：25700 wall triangles、12852 surface 行、PointID 0-based（0-based mismatch 0；1-based mismatch 12852）、duplicate 0、missing Cp 0；`fx=16253.149728260441`、`fz=682472.5289181785`、`wall_area=722.5664575910514`、`CD_int=0.006819724029441855`、`CL_int=0.09277659959739352`，与 JSON 差 ≤1.4e-17；`CD_int`/`CL_int` 对尾窗均值差 1.06e-11 / 2.23e-10（闭包成立）；法向取反符号自洽。结论：SU2 归档数字可逐位复现。

## 2. 独立复算：WaveDrag / Eminton-Lord（PASS）

port `scripts/area_rule_recompute.py`（仅解析 raw slice TXT，未调用 OpenVSP）：`WAVE-00R` 81 点，`emlord_port=0.10185900595764863`，theory rel error `-1.5474421627514013e-06`，与 A1 的 `python_port` 差 0；`WAVE-01` / `WAVE-02` 的 `donq_avg=12.578880434576416` / `15.502478232190041` 与 A1 完全一致，`implied Sref=99.99984445838996` / `99.99985958516395`（约 100 m²，证实脚本以 100 m² 为基准），`cd_on_Sref` 与 A1 一致。结论：area-rule 数字可复现；implied Sref=100 m² 成立。

## 3. 预算审计（PASS，1 处证据链弱点）

`evaluations.jsonl` 23 行全部 `billable=true`；ledger 23 个 numerical_analysis_events（VSPAERO 6、WAVE 7、RCAIDE 4、SU2 6），caps/used 全满、totals 23/23、remaining 0。失败/作废尝试均计费：`NA-018` config-parse 中止（0 iter）、`NA-019` 100 iter 无效解（CL/CD=0，NOT evidence）、`NA-021` rc1 mesh-format 失败。未发现任何未计数的 solver 启动；`mesh_generation_events` 11 个 `billable=false`。弱点：`NA-018` 的 `files=[]`，无归档 raw 日志，ledger note 自认 Post-hoc recorded（预算正确，证据链弱）。

## 4. 夸大/诚实性扫描（1 处 MAJOR 事实错误）

报告/README/summary 对 gate 的表述诚实：`EXECUTED_NO_GATE_APPROVED`、无 `APPROVED_FOR_NEXT_STAGE`、P4–P6 frozen、PR #3 open；LF VSPAERO `NOT VALIDATED`、area-rule real-geometry `NOT_VALIDATED` 且 `BODY-CORR BLOCKED`、HF `PARTIAL`（wedge 超出 1 deg 预算、机翼仅二级网格、inviscid wing-only）、GEO-12D `PARTIAL`、MISSION-DATA `PARTIAL`；无 validated fuel-burn label 或 full-aircraft high fidelity 宣称。

MAJOR-1（事实性夸大）：`docs/reviews/p1p3_fullchain_validation_report_20261031.md:132-133` 与 run `README.md:162-163` 称 Both completed runs ... stationary ... relative peak-to-peak <= 6.3e-9；但 `hf_su2_results.json.force_stability_last_200` 自身数据为：HFS-02 CD/CL/CMy ≤6.30e-9，但 CMz 4.09e-08、CMx 4.63e-07；HFS-03 CD 4.50e-06、CL 2.74e-06、CMy 5.05e-06、CMz 1.86e-04、CMx 3.58e-03。6.3e-9 只是 HFS-02 三个力的最大值，不是 both completed runs 的全部分量；且同 JSON 的 HFS-02/HFS-03 `residual.note` 写 stationary to 1e-9 relative 亦不实（HFS-03 尤甚）。不影响 gate 状态（HF 仍 PARTIAL），但必须改文字。

## 5. Findings

| id | severity | finding | 证据 |
| --- | --- | --- | --- |
| F-01 | MAJOR | stationarity <=6.3e-9 both runs 不实；力矩分量与 HFS-03 超出 3 个数量级 | report:132-133；README:162-163；hf_su2_results.json force_stability_last_200 + residual.note |
| F-02 | MAJOR | `data_manifest.json` 的 sha256 由 CRLF 工作树生成；干净 LF checkout（HEAD d80b4c4）59 文件中 14 个哈希不匹配（全部仅行尾差异，无内容差）→ all committed files 不可跨 checkout 复现；且主 checkout 的 ledger 有未提交 backfill（+253 行，sha 由 32677B/d064d93f… 变 43240B/b491fcf1…），manifest 已失效 | README:242；worktree 校验 45/59；D:/RCAIDE porcelain M .../approval_and_budget_ledger.json |
| F-03 | minor | 1082 wing vertices 实为 unique 顶点数（STL 记录 6480），committed `geometry_validation.json` 只记 6480/2388/1056，未记 1082（A5 从 STL 独立复算=1082，max |dz|=0.033961960305，声明本身为真） | README:73；geometry_validation.json |
| F-04 | minor | vertical tail and fuselage STL byte-identical 无归档证据（run dir 仅 wing-only STL；仓库仅 PRE-0 F/V case） | README:74；git grep |
| F-05 | minor | `summary.json` 的 `wall_clock_limit_hours=null`、`wall_clock=null`，与 ledger 30 h 上限不一致 | summary.json；ledger.wall_clock |
| F-06 | minor | condition number grows like n^3.1，实测 50→800 约 n^3.0 | wave_drag_area_rule.json 与报告 |
| F-07 | minor | `NA-018` 无归档 raw 日志，仅 post-hoc 补记 | ledger numerical_analysis_events NA-018 |
| F-08 | minor | ledger `categories.case_ids` 为计划名，与 events 实际 case_id 不一致，需人工映射表 | ledger；README:53-57；report:52-56 |

## 6. Verdict

**CHANGES_REQUESTED**（文档/证据修复，不需要新物理、不改变任何物理 gate）。

必须修复（交付前）：
1. 修正 F-01 三处文字（report、README、hf_su2_results.json notes），按分量如实报告：可写 HFS-02 CD/CL/CMy rel p2p ≤6.3e-9，但 CMx 4.6e-7；HFS-03 CD/CL/CMy ≤5.1e-6、CMx 3.6e-3，并明确这与 HF PARTIAL 结论一致。
2. 处理 F-02：将 data_manifest 的哈希改为对 commit 内容（LF 归一化）计算并重新生成；或明确记录行尾策略使干净 checkout 可复算；同时把主 checkout 未提交的 ledger mesh-events backfill 提交（并重生成 manifest）或从该交付明确剔除并标注 A4 GAP-08 未关闭。

建议修复（非阻塞）：F-03 在 geometry_validation.json 增 `unique_vertex_count=1082`；F-04 引用 PRE-0 证据或删除该句；F-05 对齐 wall_clock；F-06 措辞改 n^3；F-07 补 NA-018 日志或调低该行证据等级；F-08 在 ledger 增计划名与实际名映射。

## 7. 限制

- 本轮 0 次 solvers（禁物理）；SU2/WAVE 结论均来自既有 raw 文件独立重算。
- 主 checkout `D:/RCAIDE` 有历史未提交改动（23 项，含 run dir ledger backfill）；本复核以干净 worktree HEAD `d80b4c4` + raw artifacts 为准。
- 未复核 195 个 raw 文件的全部内容，仅核 manifest/哈希链与关键 spot 文件（history/surface/medium mesh/log）。
- 未评估物理正确性（SU2 单楔/二级网格无法证明网格收敛；wing-only inviscid 不能证明整机阻力），与报告自身 caveat 一致。

复核人：A5（a5-code-reviewer）；输出目录：`C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a5/`