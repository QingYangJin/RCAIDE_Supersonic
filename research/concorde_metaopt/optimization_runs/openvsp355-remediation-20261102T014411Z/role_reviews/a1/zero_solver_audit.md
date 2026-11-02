# D-12D-003 Round-1「零物理求解」独立审计报告（A1）

- 审计任务：task-43 / D12D003-ZERO-SOLVER-AUDIT-A1
- 审计人：A1（a1-code-dev），只读独立审计；不共享 a3 结论
- 审计时间：2026-11-02 10:25–10:40 +08:00（= 2026-11-02T02:25–02:40Z）
- 审计对象：commit dbc325dd9d7412b48e0399061a86d61eb0de6941（D-12D-003 Round-1 证据包）
- 审计范围：run 包 D:/RCAIDE/research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/（35 文件）、evidence/tooling_events.json、summary.json、README.md、budget_request_round2.json、data_manifest.json、D:/RCAIDE/outputs/concorde_metaopt/openvsp355-remediation-20261102T014411Z/ 原始大文件、D-12D-002 预算台账、磁盘取证、安装/PATH 复核
- 硬约束遵守：未运行任何求解器（VSPAERO/SU2/WaveDrag/RCAIDE Mission/Gmsh）、未修改仓库/未写 git/未写 GitHub、未 spawn 子智能体

## 0. 结论（verdict）

| # | 待验证命题 | 本次审计结论 | 关键依据 |
|---|---|---|---|
| V1 | 是否执行过任何求解算例（solver case） | **CONFIRMED 否**（0 个） | 包内无 .polar/.history/.lod/.adb/.groups/.fem；磁盘全盘扫描自 2026-11-01 仅 2 个几何 .vspgeom；见 E3/E5 |
| V2 | 是否发生任何计费数值分析启动（numerical_analysis_start） | **CONFIRMED 否**（0 次） | data_manifest:250-251；tooling_events:9-10；budget 台账 23/23 未增；见 E2/E4/E6 |
| V3 | 是否产生任何求解产物/求解 stdout 日志 | **CONFIRMED 否** | 8 个 tooling 事件全为几何/API/setup/source 类；字符串扫描无新求解日志；见 E4/E5 |
| V4 | 是否消耗 D-12D-002 或 D-12D-003 求解预算 | **CONFIRMED 否** | D-12D-002 台账 23/23 于 2026-10-31 封账；D-12D-003 approved=0；见 E6 |
| V5 | 「零个 solver 进程启动」字面命题 | **PARTIAL —— 1 次 banner-only vspaero.exe 进程启动**（无模型/无算例/无产物/不计费） | tooling_events:157-159（TG-008 自述）；见 F1 |
| V6 | Round-2 预算是否处于未批准未执行状态 | **CONFIRMED 是**（PROPOSED_NOT_APPROVED，approved=0） | budget_request_round2.json:3/:6/:137；summary.json:290；见 E6 |
| V7 | main 分支是否未被本轮改动 | **CONFIRMED 是** | HEAD 非 main 祖先（git merge-base 退出 1）；main=origin/main=ec65e5a；见 E1 |

**总判定：D-12D-003 Round-1 的「零物理求解」声明成立（零求解算例 / 零计费数值分析 / 零求解产物 / 零预算消耗），未发现任何可反驳该声明的证据。** 唯一需要修正的是表述口径：报告中「zero solver process start」应按字面改为「零求解算例、零计费数值分析；含 1 次无模型 banner-only 版本探针进程」（F1）。该口径问题不改变 V1–V4 的任何结论，也不改变 gate 状态。

## 1. 审计方法

1. git 层面独立复核 commit/parent/branch/main 祖先关系与工作树干净度。
2. 文件层面：包内 35 文件全清单；按 data_manifest 的 canonical-LF 约定独立复算 bytes+sha256。
3. 静态源码：核验 OpenVSP 3.55.0 源码中 StopBeforeRun 与 solver fork 的先后关系（EXT/src355/，由 a3 取回；A1 独立重读）。
4. 事件/预算：tooling_events、summary、budget_request_round2、D-12D-002 ledger/evaluations.jsonl 的独立重算与时间线比对。
5. 磁盘取证：对 D:/RCAIDE、外部记忆目录、Temp 做「自 2026-11-01 起新增求解产物」的时间过滤扫描；对求解器输出特征串做内容扫描。
6. 反驳性检查：主动假设「包隐瞒求解」「仓库外有求解日志」「脚本偷偷 fork solver」等并逐一检验（第 3 节）。
7. 安装/环境：archive sha256、新旧 vspaero.exe 指纹、安装目录文件计数、PATH/注册表。

## 2. 证据链

### E1 git 状态（commit 属于 Round-1 证据，未入 main）
- worktree D:/RCAIDE-verify-a3-dbc325d：HEAD=dbc325dd9d7412b48e0399061a86d61eb0de6941，parent=5dcb0bf09335fd6f73363d0280a667286d6d20f9（与 summary.json 的 git_sha_at_run_start 一致）；git status --porcelain 输出为空；git branch --show-current 为空（detached HEAD）。
- 主仓 D:/RCAIDE：branch=research/concorde-metaopt，HEAD=dbc325d；main=ec65e5a9a723bc52df8075a395fcaf9e0fd0fc2b；origin/main=ec65e5a；git merge-base --is-ancestor HEAD main 退出码 1 → HEAD 不是 main 祖先 → main 未被本轮改动（与 summary.json scope.main_branch_untouched=true 一致）。
- commit dbc325d：2026-11-02 10:21:47 +0800，36 files changed，+5744/−0；35 个 run 包文件 + docs/reviews/p1p3_d12d003_round1_remediation_report_20261102.md（110 行）；唯一二进制为 figures/geometry_parity_355_vs_326.png（95,305 B）。**提交内不含任何求解产物**。

### E2 包清单与 data_manifest 完整性
- 包内 35 文件：14 json / 5 csv / 2 .vspaero / 1 txt / 1 png / 9 md / 3 py。扩展名扫描：无 .polar、.history、.lod、.groups、.adb、.csf、.vkey、.vspgeom。
- data_manifest.json：:9 hashing_convention（sha256 over canonical LF bytes，CRLF→LF）；:10 file_count=34；:11 total_bytes=407111；:231-235 raw_artifacts（manifest/raw_artifacts_manifest.json，file_count=2，total_bytes=717903，outside_git）；:250 solver_starts=0；:251 numerical_analysis_starts=0。
- A1 独立按 CRLF→LF 复算：34/34 文件的 bytes 与 sha256 全部吻合，无一项失配。目录实有 35 文件，唯一未被 manifest 收录的是 data_manifest.json 自身（自排除约定）→ **不存在被 manifest 隐藏的求解产物文件**。

### E3 solver 输入生成证据（GENERATED_NOT_SOLVED）
- evidence/vspaero7_setup_generation.json：status="GENERATED_NOT_SOLVED"；:6 solver_start_count=0；:7 generated_utc=2026-11-02T02:20:00Z（与文件 mtime 存在漂移，见 F3）。
- thick 变体：geom_result_id=LBMHAKQ，sweep_result_id=""（sweep_result_id_empty=true）；wing355_thick.vspgeom 503,013 B sha256 494feef5bb8b070dc77892dd7e2838f4946bcd856c2448a99c1a56d2884fb718，mesh 1082 nodes/1088 elements（GeomSet=0）。thin 变体：geom_result_id=SPUSFGT，sweep_result_id=""；wing355_thin.vspgeom 224,357 B sha256 9fcda6d5d45300fbb0e20257c9ddc80540b44f5064a9566089d7ef85f9018d8e，mesh 527 nodes/480 elements（ThinGeometrySet=0）。
- geom_result CSV 仅含 Results_Timestamp=1793585030（=2026-11-02 10:03:50 +0800）、Analysis_Duration_Sec=0.035（thick）/0.02（thin）、GeometrySet/ThinGeometrySet/Mesh_GeomID/VSPGeomFileName——**无 Cl/Cd/L/D 等任何气动系数**。
- 两变体 setup 文件均 930 B / 42 行，sha256 同为 c862aa220bc6f3a9d057b2fbe99c4ed340591a14ad88f455d3d1b0ddbe7c1804（设置相同；A1 独立重算一致）。setup 内容为纯输入参数（Sref=358.25，Cref=18.489893，Bref=25.604638，X_cg=16.821978259514246，Mach=2.02，AoA=2，Beta=0，ReCref=10000000，Vinf=100，Rho=0.002377，…；见第 4 节 F2），**不含任何求解输出**。
- 原始大产物归档 D:/RCAIDE/outputs/concorde_metaopt/openvsp355-remediation-20261102T014411Z/vspaero7_setup_artifacts/：仅 wing355_thick.vspgeom + wing355_thin.vspgeom + raw_artifacts_manifest.json（710 B）；两 vspgeom 的 bytes/sha256 与证据记录一致（A1 独立复算）。
- 源码级证明（EXT/src355/VSPAEROMgr.cpp，6740 行，sha256 9e39c3b746e2516a3a1b37f11c7d8a19d31839630642a70f4dcfbea0abfbc1a2）：StopBeforeRun 仅在 :371/:446/:2142/:2144 出现；:2129 组装 cmdStr，:2142-2146 `if ( m_StopBeforeRun ) { m_StopBeforeRun = false; return string(); }` 在 :2149 `m_SolverProcess.ForkCmd( veh->GetVSPAEROPath(), veh->GetVSPAEROCmd(), args );` 之前返回 → setup 生成路径不会 fork 求解器；:2152 的 MonitorProcess 不可达。AnalysisMgr.cpp（111,483 B，sha256 869248c9050493836c7b099de826ac401a7b72c151f52ca8a1656ac757e0643e）：ExecAnalysis :163；StopBeforeRun 注册 :2255（"Flag to stop after writing files, but before running VSPAERO."）、读取 :2875-2878；VSPAEROComputeGeometry 入口 :2044-2156；VSPAEROSweep Execute :2356；未发现第二条 solver fork 路径。

### E4 tooling_events 与证据文件校验
- evidence/tooling_events.json（8,122 B）：:8-10 policy 明确 "no VSPAERO / WaveDrag / SU2 / RCAIDE solver process may be started in Round-1; geometry export, API reflection, setup-file generation and source retrieval are tooling events ... not billable numerical analysis starts"；:9 solver_processes_started_total=0；:10 numerical_analysis_starts_total=0。
- 8 个事件 TG-001…TG-008 全部 solver_starts=0：TG-001 几何导出（3.55 STL baseline sha 019c6112…、w10 sha 4f08a88e…）；TG-002 几何导出（wingbody_old326 worker_result sha 77763998…、new355 sha b803fc30…）；TG-003 API 探针（api_355_probe.json 17,427 B sha 9cbc5080…）；TG-004/005/006 setup 生成三份报告（1,883 B/1,862 B/6,357 B）+ 两 vspgeom；TG-007 源码取回（AnalysisMgr/VSPAEROMgr/tree.json 3,278,759 B sha 490b6e52…）；TG-008 二进制版本探针（usage.txt 1,546 B sha 3bc9b1d1…）。
- A1 对全部 15 个 evidence 路径逐一独立校验 exists+bytes+sha256，均吻合。

### E5 磁盘取证（无新增求解产物）
- 对 D:/RCAIDE 扫描自 2026-11-01 00:00 起新增的 .polar/.history/.lod/.adb/.groups/.fem/.vspgeom/.csf/.vkey：**仅 2 个命中**，均为输出目录 D:/RCAIDE/outputs/concorde_metaopt/openvsp355-remediation-20261102T014411Z/vspaero7_setup_artifacts/ 下的 wing355_thick.vspgeom（503,013 B）与 wing355_thin.vspgeom（224,357 B）（mtime 2026-11-02 10:08）——即 E3 的几何输入，不存在任何 .polar/.history/.lod/.adb/.groups/.fem。
- 外部记忆目录 C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state 同过滤自 2026-11-01 → 0 命中。Temp（depth≤2，283 文件）→ 0 命中。
- 求解输出特征串扫描（"Total surface area"、"Number Of Trailing Vortices"、"VSPAERO v.7.2.2"、"Agglomerating Grid0"、"Found a TE node"、"Solver Case:"、"Total NumberOfNodes"）：只命中说明/证据文档（generation JSON、usage.txt、install_provenance.json、role_reviews、summary.json）与旧 p1p3 台账；**没有任何新的 vspaero 求解 stdout/日志**。

### E6 预算未执行
- D-12D-002 台账 D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z/approval_and_budget_ledger.json（42,454 B）：:14 counting_contract；:75-77 totals {cap:23, used:23, remaining:0}；:1018 updated_utc=2026-10-31T10:10:27.416720Z；:1019 revision_note（仅 backfill 11 个非计费 mesh_generation_events，billable 仍 23/23）。文件 mtime 为 2026-10-31，早于 Round-1。
- 同目录 evaluations.jsonl（11,295 B、23 行）末条为 HFS-03（SU2_HF，billable，status SOLVED，finished_utc 2026-10-31T09:33:22Z）→ 23 行全部为 2026-10-31 及以前，Round-1 期间无新增。
- optimization_runs 下除 openvsp355-remediation-20261102T014411Z（mtime 2026-11-02 10:20）外无新 run 目录；也未见任何 D-12D-003 计费事件或审批记录。
- Round-2 提案：budget_request_round2.json（4,429 B）:3 status="PROPOSED_NOT_APPROVED"；:6 no_solver_started=true；:100 recommended_cap=23；:109 tier1_cap=22；:114 tier2_cap=4；:137 approval_note="AWAITING_OWNER_APPROVAL: no solver may start until the owner approves each category in writing on Issue #4."；全文无 approved 记录。summary.json:290 同状态；:22 d12d003 approved=0。→ **PROPOSED_NOT_APPROVED 且未执行 CONFIRMED**。

### E7 自述一致性
- summary.json（14,562 B/417 行）：:12 new_physical_solver_starts=0；:13 numerical_analysis_starts=0；:29 gate_approved=false；:79 tooling solver_starts=0；:138 setup_generation solver_starts=0；:358 APPROVED_FOR_NEXT_STAGE="NOT ISSUED (owner only)"；:411 caveat "No solver was started; this run adds no physical evidence and must not be reported as a physical PASS."；status=ROUND1_EVIDENCE_COMPLETE_NO_GATE_APPROVED；6 个 gate 均未通过（GEO-12D PARTIAL、LF NOT_VALIDATED/LF_PROVISIONAL、HF PARTIAL、BODY-CORR BLOCKED、MISSION-DATA PARTIAL、BUDGET AWAITING_OWNER_APPROVAL）。
- docs/reviews/p1p3_d12d003_round1_remediation_report_20261102.md:6 "zero solver starts, zero numerical-analysis starts"；:19-20 "No solver was started, so no gate can move on physical grounds."

### E8 生成脚本无求解能力（静态）
- make_round1_summary.py（215 行）、make_round1_manifest.py（97 行）、make_round1_figures.py（68 行）的 import 仅 json/os/time/pathlib/hashlib/matplotlib，全文无 subprocess/Popen/os.system，也无 vspaero/SU2 调用字符串；figures 脚本注释 "No solver is started"。
- 注意：summary 的 solver_starts 由 make_round1_summary.py:21 `sum(int(e.get("solver_starts",0)) for e in ev)` 对 tooling_events 自报字段求和得到 → 属**自报口径**而非进程级计量（见 F6）。

### E9 二进制与环境
- 新 vspaero.exe 811,520 B sha256 db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad，banner "VSPAERO v.7.2.2 --- Compiled on: Oct 12 2026 at 04:08:14 PST"；旧 3.26.1 vspaero.exe 561,664 B sha256 e1affca023f9d63d9b0b5f343c3ea5afd5a8dbcfe420952e557718dd15f90eb8，banner "VSPAERO v.6.2.0 --- Compiled on: Jan  6 2022"；新版 python 侧安装目录内副本与 install root 副本 hash 相同（A1 独立复算）。
- usage.txt 为 vspaero 7.2.2 usage（含 -geom/-omp/-fs/-restart 等，**无 -setup 选项**）→ setup 文件只能由 OpenVSP API 生成，不能由 vspaero.exe 生成，与 E3 一致。
- archive D:/OpenVSP-download/OpenVSP-3.55.0-win64-Python3.11.zip 49,664,844 B sha256=f1fde65f9d48ae482dcad2c0b7711b81a22810871a5bebc236c4618c0131ebb9（A1 独立复算，与 install_provenance 一致）。

### E10 几何类 ExecAnalysis ≠ 求解
- Round-1 的 VSPAEROComputeGeometry / DegenGeom / sweep 结果 id 均为空或仅产生 .csf（20 B）、.vkey（350–356 B）、.vspgeom（几何网格），无 .polar/.history 等求解输出；sweep_result_id 为空且 geom 仅 0.02–0.035 s（E3）。
- 佐证（A1 前置 task-36 探针，同版本 3.55.0）：在 EXT/fullchain/d12d003/a1/ 下用 OpenVSP Python API 构建几何并执行 VSPAEROComputeGeometry/DegenGeom ExecAnalysis，产物同为分析目录内的 .csf/.vkey/.vspgeom 与 DegenGeom CSV，从未产生求解产物，也从未 fork vspaero.exe。两条独立路径结论一致。

## 3. 反驳性检查（主动寻找反证，全部为负结果）

| # | 反驳假设 | 检验方法 | 结果 |
|---|---|---|---|
| R1 | 包内隐藏求解产物 | 全目录扩展名枚举 + 内容特征串扫描 | 未发现（E2/E5） |
| R2 | 仓库外（outputs/EXT/Temp）有求解日志 | 时间过滤全盘扫描 + 特征串扫描 | 未发现（E5） |
| R3 | data_manifest 隐瞒文件 | 34 vs 35 文件差异逐项归因 | 仅 manifest 自排除（E2） |
| R4 | 求解器进程执行痕迹 | Prefetch 扫描 → "EPERM: operation not permitted, scandir 'C:\Windows\Prefetch'"；两 vspaero.exe atime 均 2026-11-02T02:08:06Z（=生成报告读取哈希时刻，晚于 setup355c 的 02:03:50Z），无法据此判定执行；无 4688/USN/ETW 采集 | **无法独立证明"零进程启动"**；仅能依据 TG-008 自述与产物/计费为空（F6） |
| R5 | Round-1 期间新预算事件/审批 | ledger 更新时刻、evaluations.jsonl、run 目录 mtime、budget_request_round2 状态 | 无新增（E6） |
| R6 | setup 文件被误当求解结果 | 42 行内容逐行检查 + geom_result CSV 字段检查 | 均无气动输出（E3） |
| R7 | 生成脚本偷偷 fork | 静态 import/字符串全文扫描 | 无 subprocess/os.system（E8） |
| R8 | 3.55 安装被混入求解 | 安装目录无求解产物；无 3.55 PATH；无注册表键 | 未发现（E9/F4） |

结论：**没有任何一条反驳假设被证据支持**；同时 R4 表明「零进程」只能有条件地断言（见 F1/F6）。

## 4. 发现清单

### F1（major，治理/口径）字面「0 solver 进程」与 TG-008 自述冲突
- 证据：evidence/tooling_events.json:157 TG-008 description 明写 "vspaero.exe invoked with no arguments only to print the usage banner, capturing v7.2.2; no model, no case, no solver start"；:158 solver_starts=0；:159 actual_solver_processes=0。而 README.md:21 写 "not performed here: any solver process start"，:9（tooling_events）写 solver_processes_started_total=0。
- 判定：按 policy 文本「no ... solver process may be started」，这是一次**实际的 vspaero.exe 进程启动**（banner-only：无模型、无算例、无产物、不计费），属口径/分类偏差而非求解开始。
- 影响：不影响 V1–V4 结论，不影响 gate 与预算；但对外验证（A4/owner 回执）若被逐字审核，会与「zero solver process start」字面矛盾，削弱证据包严谨性。
- 建议（由 L 决定是否执行写入）：Round-1 包与回执表述改为「零求解算例、零计费数值分析；含 1 次无模型 banner-only 版本探针进程（不计费）」；tooling_events 可加字段注明 actual_solver_processes=1、分类为 version-probe、不计费。

### F2（major，影响 Round-2 有效性）README 把 VSPAERO 默认值误标为冻结合同值
- 证据：README.md:94-96 "Injected reference values (matching the frozen conditions): ... ReCref = 1e7, Vinf = 100, Rho = 0.002377"；而 evidence/vspaero7_setup_generation.json:64 与 :103 的 setup_content 中确为 ReCref = 10000000 / Vinf = 100 / Rho = 0.0023770000000000002（VSPAERO 默认值）；D-12D-002 冻结合同值见 p1p3 run_lf_case.py:21 `"Vinf": 596.0373972278921, "Rho": 0.1153178340089936, "ReCref": 89397005.8767656`（同文件 :35-36、:52 写入 setup），docs/reviews/p1p3_fullchain_validation_report_20261031.md:43 "V 596.037397 m/s, q 20483.94023343017 Pa, Re 8.9397e7"；generation JSON:152 的 what_this_proves 只声明 Sref/cref/bref/CG/Mach/AoA 冻结，未含 Re/Vinf/Rho。
- 影响：现模板是「solver 输入生成样例」，本身不是求解结果，不反驳零求解；但若 Round-2 直接复用该 setup 模板而不注入合同来流参数，将以 Re=1e7、Vinf=100 m/s、Rho=0.002377 求解 → 与 D-12D-002 冻结条件不一致，Round-2 结果无效。
- 建议（L/owner）：修正 README:94-96 表述；Round-2 生成器强制注入 Vinf/Rho/ReCref 合同值并加断言（ReCref 必须 = 89397005.8767656 ± 1）。

### F3（minor，记录准确性）generated_utc 与文件 mtime 漂移
- 证据：evidence/vspaero7_setup_generation.json:7 generated_utc=2026-11-02T02:20:00Z，而文件 mtime 为 2026-11-02 10:08 +0800（=02:08Z）；tooling_events.json 的 generated_utc 同为 02:20:00Z，文件 mtime 10:10 +0800（=02:10Z）。生成时刻应为 02:08–02:10Z 附近。
- 影响：不影响零求解判定；影响时间线可审计性。建议改记实际写入时刻。

### F4（minor，措辞）README:39 PATH 表述不精确
- 证据：A1 独立复核：User PATH 中存在**旧** 3.26.1 条目 D:\Program Files\OpenVSP\OpenVSP-3.26.1-win64-Python3.9\OpenVSP-3.26.1-win64（预存，非本轮新增）；Machine PATH 无；进程 PATH 因继承而为 true；HKCU/HKLM SOFTWARE 无 OpenVSP 注册键；install_provenance.json isolation_checks.path_env_has_openvsp=true。**新 3.55 安装路径确未加入任何 PATH**。
- 影响：不推翻隔离结论（3.55 未污染环境）。建议表述为「未为 3.55 新增 PATH 条目；预存 3.26.1 User PATH 条目保持不变；无 OpenVSP 注册表键」。

### F5（info）安装目录文件计数因 .pyc 变化，不影响原始声明
- 证据：README/docs 声明 491 文件 / 149,488,735 B；A1 现测 504 文件 / 150,078,455 B，差值恰为 13 个 .pyc（4 个 __pycache__ 目录，mtime 2026-11-02 09:43，合计 589,720 B；491+13=504、149,488,735+589,720=150,078,455）→ API import 副作用。old 3.26.1 240 文件与声明一致。archive sha256 与 provenance 一致。
- 影响：无功能影响；若需目录清洁，仅由 L 执行删除（A1 不执行删除）。

### F6（limitation，取证缺口）无进程级独立计量
- 证据：Prefetch 读取 EPERM；exe atime 被后续读取污染（02:08:06Z）；无 4688/Sysmon/USN/ETW 采集权限；summary 的 solver_starts 来自 tooling_events 自报字段求和（make_round1_summary.py:21）。
- 影响：本次审计可确证「零求解算例/零计费分析/零求解产物」，但「零任意 solver 二进制进程」只能依赖 TG-008 自述 + 产物/计费为空来间接支持。建议后续轮次增加命令级审计（进程启动日志或包装器），本轮不作为缺陷计。

## 5. NOT_RUN / 受限项

- NOT_RUN：任何求解器执行（VSPAERO/SU2/WaveDrag/RCAIDE Mission/Gmsh）、任何几何/网格重建、任何数值分析。
- NOT_RUN（取证能力）：C:/Windows/Prefetch 内容读取（EPERM）、进程审计日志采集（4688/USN/ETW 未启用/无权限）、旧 3.26.1 安装除 vspaero.exe 外的全量文件 hash 复核。
- NOT_RUN（范围外）：GitHub PR #3 当前 head/状态（属 A4/L 职责）；role_reviews 内 a2/a3/a5 全部文档的逐行内容复核（仅交叉引用）；setup 中 Symmetry=0 与 p1p3 旧模板 Symmetry=NO 的数值语义等价性（需运行求解器验证，本轮禁止）。
- 未修改仓库任何文件；未写 git；未写 GitHub；未 spawn 子智能体。

## 6. 复核命令（可直接重放）

    git -C D:/RCAIDE-verify-a3-dbc325d rev-parse HEAD HEAD^
    git -C D:/RCAIDE-verify-a3-dbc325d status --porcelain
    git -C D:/RCAIDE rev-parse main origin/main
    git -C D:/RCAIDE merge-base --is-ancestor dbc325dd9d7412b48e0399061a86d61eb0de6941 main; echo exit=$?
    find D:/RCAIDE -type f -newermt "2026-11-01 00:00" \( -name "*.polar" -o -name "*.history" -o -name "*.lod" -o -name "*.adb" -o -name "*.groups" -o -name "*.fem" -o -name "*.vspgeom" -o -name "*.csf" -o -name "*.vkey" \)
    sha256sum "D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe" "D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64/vspaero.exe"
    grep -n "solver_processes_started_total\|numerical_analysis_starts_total" evidence/tooling_events.json
    grep -n "cap\|used\|remaining" ".../p1p3-fullchain-20261031T0407Z/approval_and_budget_ledger.json"

canonical-LF 复算：对 data_manifest.json:filename 列表逐项读取 bytes，CRLF→LF 归一后取 sha256 与 bytes 长度，与 manifest 记录比对（A1 实现为一次性只读脚本，未落盘到仓库）。

## 7. 对 gate/预算的影响

- 本审计**不改变任何 gate**：Round-1 六个 gate 仍全部未通过（E7），APPROVED_FOR_NEXT_STAGE 仍为 NOT ISSUED。
- 「零求解」不构成物理证据：任何 gate 的推进都必须等待 owner 批准 Round-2 预算后的真实求解（F2 修正后）。
- Round-2 前建议处理顺序：F2（生成器注入合同值）→ F1（回执/包口径修正）→ F3/F4（记录措辞）→ F6（增加命令级审计，可选）。

—— A1（a1-code-dev），2026-11-02 10:40 +08:00
