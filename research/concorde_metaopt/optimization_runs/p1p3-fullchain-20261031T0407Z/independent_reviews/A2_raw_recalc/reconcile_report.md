# A2 原始产物重算对账报告 — p1p3-fullchain-20261031T0407Z

- 任务：task-27 / FULLCHAIN-A2-RAW-RECALC-d80b4c4（A2 = a2-run-opt）
- 日期：2026-10-31（Asia/Shanghai）｜模式：只读静态重算｜求解器启动：0 次｜仓库写/GitHub 写：0 次
- 验证基准：worktree `D:/RCAIDE-verify-fullchain-a2`（HEAD `d80b4c485d689082cd117f09ec6445a181dd458c`，git status 干净，分支 research/concorde-metaopt）
- 原始产物：`D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z`（196 文件 / 108,875,262 B）
- 环境：Python 3.11.17、numpy 2.4.6；独立解析脚本 `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a2/scripts/verify_phase5.py`（45 项检查：42 PASS、3 FAIL，3 个 FAIL 全部映射到下述 discrepancy）
- 交付：本文件 + `.../fullchain/a2/reconcile.json`（结构化，含 45 项检查/全部中间表）+ `.../a2/scripts/check_results.json` + `.../a2/verify_phase5.log`

## 结论

**归档/记录的核心数值证据全部可由原始产物独立重算复现**：fuel 4/4 与 lf_mission、mission_e2e、归档 evaluations.jsonl 精确一致；LF 有效 polar 重解析 0 差异；HF 网格体积/面积与 mesh JSON/preflight/CSV 一致（<1e-6）；raw manifest 155+39 个文件逐字节哈希一致；预算 23/23 事件完全一致。
**同时发现 3 项记账/版本类不一致**（X2 中、X4 中、X3 低），均不改变已记录数值，但影响证据版本的可复现性/冻结性。
**物理门禁状态不变**：LF VSPAERO 阻力 NOT_VALIDATED、HF SU2 Euler PARTIAL、面积律波阻 NOT_VALIDATED、机身修正未注入、预算 23/23 用尽、无门禁批准。

## 1. Fuel 复现（4/4 PASS）

| case | lf_mission.objective = mission_e2e.fuel_burn_kg | 对照 |
|---|---|---|
| E2E-00 | 34109.48257123768 | == 归档 smoke-p2-20261029T1612/evaluations.jsonl 第 1 行 objective（literal；archive 差 0.0，match=true） |
| E2E-01 | 34117.55529648991 | == 归档第 5 行 objective（W10 tip_twist +2deg 复现） |
| LFV-04 | 34117.751745703776 | delta=+8.269174466098775 == mission_e2e.tail_sensitivity V01_plus_1pct |
| LFV-05 | 34109.70744320392 | delta=+0.2248719662457006 == V02_plus_2deg |

补充核验：四 case range_span_m=3028019.999999994（== 冻结 3028020.0）；E2E-00→E2E-01 design 仅 tip_twist 0→2.0；归档 best feasible 34035.332605355274 仅作 archive 记录、未被重算、无新 fuel label。**fuel 无 discrepancy。**

## 2. LF VSPAERO 极曲线重解析（记录复现 PASS；物理 NOT_VALIDATED 不变）

- 重解析 3 个有效 `.polar`（LFV-00 baseline/medium；SENS-A=coarse，Tess_U/W 8/17；SENS-B=fine）：5 行 × CL/CDo/CDi/CDtot/CMy 与 `lf_vspaero_results.json` 全部差 0.0；polar sha256 逐一等于 JSON 记录（LFV-00 = f03511d5ee374860cad635195569322746bafed00c167547fa1e109ea6821691）。
- density spread 复现：alpha=2° 时 CL=[0.08387934, 0.08781966, 0.1082826]、CDi=[+3.435104e-4, −8.942229e-4, −2.260794e-2]（变号，magnitude ~65×）、CDtot=[0.005420316, 0.004188608, −0.01743937]（fine 为负）。
- 口径更正：任务卡写 “SENS-A/B/C medium”，实际只有 SENS-A(coarse)/SENS-B(fine)，无 SENS-C；medium = LFV-00 baseline。
- quarantine LFV-01/02/03 原始 polar：5/5 行 NaN、Re/1e6≈4e-319~5e-318、alpha=2 CL≈31.3~31.8 → 确证非证据；JSON 标 MISSING/polar_sha256=null 正确（坏 namelist 缺陷 LD-001 已记录）。
- 结论沿用：`lf_vspaero_results.assessment.verdict = NOT_VALIDATED`（CDi 随 panel 加密变号、CDtot 变负）。本轮只证明“记录值=原始文件值”，不构成物理验收。

## 3. HF SU2 网格重算（记录复现 PASS；物理 PARTIAL 不变）

- 关键实现事实：raw `.su2` 为 **0-based 节点索引**（存在引用节点 0 的单元；1-based 解析得 volume 45,335,811.4 m³ 明显错误）；按 0-based 解析后复现 total_tet_volume=2,015,871.1723349323 等记录值。
- coarse/medium/fine：npoin=14079/28323/56623，nelem=61436/125876/256455，wall triangles=12896/25700/49520；机身散度定理体积=128.48334750167413/128.82766506802807/129.01360420185486 m³，壁面面积=722.2754060160041/722.5664575914074/722.7633839169255 m²。
- 与 `mesh_convergence.csv`/mesh JSON/preflight 差 <1e-6（csv 体积差 1.6e-10/7.6e-11；面积差 2.7e-10/3.6e-10）；vs analytic 129.4516 m³ / 717.57475 m²：体积误差 −0.748%/−0.482%/−0.338%、面积误差 +0.655%/+0.696%/+0.723%（faceting bias，已记录）；0 个负体积四面体；coarse 行 CL/CD/CMy 为空（HFS-01 失败，符合预期）。
- HF verdict 沿用：`HF_M2_02 = PARTIAL`（两级网格、残差平台 rms[Rho]~1e-1、Euler 无黏、仅机翼、楔形激波角超 1° 容差 1.6–2.1°、无 CL 匹配对比；Euler CL 0.0928 vs mission CL 0.1334）。

## 4. Manifest / 归档完整性（PASS，1 项 X4、1 项 X3）

- `data_manifest.json`：59 文件、59/59 resolve；**58 个**逐字节 sha256+size 匹配 D:/RCAIDE 运行目录；仅 `approval_and_budget_ledger.json` 不匹配（→ X4）。
- `raw_manifest.json`：**155/155** 归档副本 sha256+size 匹配，group counts 与 `raw_artifacts_manifest.json` 声明逐组一致；`wave_raw_manifest.json`：**39/39** 匹配；两个 manifest 自身 sha256 与声明一致（b6b959ba1c7cc12d61f355ca248b3f140c01c1c4bbde5e2cdeb9116c613e2d11；06c3c9dffe08679a40076d3f51234da720076232452d538d1325b2b1304d5b2a）。
- 计数/字节：155 文件/100,875,290 B + 40 文件/7,949,132 B（=39 个 case 文件 7,936,388 B + wave manifest 自身 12,744 B）= **195 文件/108,824,422 B**；磁盘 195/108,824,422 + `raw_manifest.json` 50,840 B = 196/108,875,262 B（与 lead 提供的 find 计数一致）。
- 口径澄清（E10）：`wave_raw_manifest.json` 自身无 file_count 字段、不列自己；`raw_artifacts_manifest.json` 的 wave file_count=40/total_bytes=7,949,132 为“含 manifest 自身”口径，两者自洽。
- EXT live source 冻结性：155 个 source_abs 中 154 个仍与归档 manifest 一致，1 个漂移（→ X3）。

## 5. 预算 / q / frozen 一致性（PASS）

- `evaluations.jsonl` 23 行：VSPAERO_LF=6、WAVE_AREA_RULE=7、RCAIDE_LF=4、SU2_HF=6（合计 23）；status：SOLVED 20、SOLVED_VOID_CONVERGENCE 1、FAILED 1、FAILED_CONFIG_PARSE 1；`summary.json` budget cap/used/remaining = 23/23/0；`mission_e2e.budget_accounting` 一致；3 个非 SOLVED 的 SU2 事件（HFS-01、HFS-SETUP-01、HFS-SETUP-02）均 billable，解释了 HFS-00R/HFS-04 未跑。
- q：`hf_su2_results.frozen_conditions.dynamic_pressure_pa = 20483.94023343017 Pa`，等于 0.5·ρ·V²（ρ=0.1153178340089936，V=596.0373972278921），也等于由 HFS-02 力积分反推的 q（CD_N_on_Sref=50045.669056686085 N / (CD=0.006819724029 × Sref=358.25 m²) = 20483.94023343017，CL 反推同值）；`mission_e2e.observed_mission_dynamic_pressure_pa=20654.013924958777`（+0.83% vs 批准 ISA q）是该文件已记录的任务观测差异，不属于记账错误（X1 已澄清，非 discrepancy）。
- LF/HF frozen 公共字段完全一致：mach 2.02、altitude_m 18288.0、density 0.1153178340089936 kg/m³、velocity 596.0373972278921 m/s、speed_of_sound 295.0680184 m/s。

## 6. Discrepancies（3 项）

**X2 [MEDIUM] 主 checkout 的 approval_and_budget_ledger.json 与 HEAD 不一致。** D:/RCAIDE 工作区该文件 43,240 B、sha b491fcf1…，git diff HEAD 显示 +253 行未提交（HEAD d80b4c4 blob 为 31,911 B/LF；31,911→32,677 B 的 766 B 差即 766 行 CRLF artifact）。运行目录 60 文件集合两边一致（60=60，无新增/缺失）；15 个 sha 差异中 14 个纯 CRLF/LF 行尾差异（规范化后完全一致），唯一真实内容差异就是该 ledger。本报告一律以 worktree HEAD 版本为准。
**X4 [MEDIUM] data_manifest 的 ledger 行无法复验（run-time 版本未归档）。** manifest 记录 sha256 d064d93fd14b865f…/32,677 B（run 时 CRLF 工作副本），该版本不存在于 main checkout（43,240 B）也不存在于 d80b4c4 blob（31,911 B）→ run-time 账本版本未随 run 归档保存；其余 58/59 行可字节级复验。建议后续 run 归档时把 run 目录 JSON 一并按字节归档（或改用 LF 规范化哈希+规范化校验口径）。
**X3 [LOW] 1/155 EXT live source 归档后被编辑。** `EXT/fullchain/hf/wedge/hfs00_analysis.json` 现 1,913 B/sha 084adf09…，manifest 记录 1,915 B/sha 01a61f47…；但归档副本 `RAW/hf_raw/wedge/hfs00_analysis.json` 仍 1,915 B/01a61f47…，与 manifest 完全一致 → 归档证据完好，仅 EXT 工作副本发生归档后编辑。

## 7. 限制与边界

- 只做静态复算，不重跑任何 solver；LF/HF 的物理适用性与门禁结论沿用 run 内记录（LF NOT_VALIDATED、HF PARTIAL、wave NOT_VALIDATED、机身修正未注入 `injected=false`），不构成任何物理验收或新的 fuel/drag 标签。
- 未验证 VSPAERO/SU2 二进制行为、也未做外部数量级对比；只验证“记录数值 ↔ 原始文件”的对应关系。
- data_manifest 为 CRLF 字节级哈希（run 时工作副本），committed LF 化后不能逐字节匹配属于预期现象；E1/E5 已把该行尾因素与真实内容差异区分开。
- 本轮未写仓库、未改 Issue/PR、未 commit/push。

## 8. 产物清单

- `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a2/reconcile_report.md`（本文件）
- `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a2/reconcile.json`（45 项检查 + 全部中间表 + discrepancies）
- `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a2/scripts/verify_phase5.py`、`check_results.json`、`verify_phase5.log`
- `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a2/verify_phase5.log`（副本）
