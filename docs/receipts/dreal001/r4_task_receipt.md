# D-REAL-001｜A4 任务回执（r4_task_receipt）

- 角色：A4（真实 VSPAERO 并发吞吐 / checkpoint / SHA256 manifest / 中文图库）
- 共享任务：task-9
- 工作树：`D:\RCAIDE\dnext001\wt-real-a4-perf-figs`；分支：`research/dreal001-a4-perf-figs`（未 push，未合并 main）
- run_id：`PERF_20261110_A4_01`（purpose=INTERNAL_PERF_ONLY，canonical_batch_id=`DREAL001-PERF-20261110-01`）
- 窗口：`WINDOW_OK-PERF_20261110_A4_01-20261110T0825Z-0845Z`（16:25–16:45 CST）
- **真实物理求解启动数 = 2（两次 smoke 均 CRASHED，无有效 polar）。36 次并发批次 = NOT_RUN。**
- **A5 复核（m00792）= FAIL（证据完整性，不签 PASS）；Lead 裁定（m00825）= 工程失败停机记录归档，结论固定 NOT_RUN/FAIL，吞吐投影禁止引用，剩余 37 次预算不结转。** 补件见 §5.6。
- **A5 终审（m00901）仍不签 PASS**：新增 R-A4-11（fig6 内嵌禁用数字 2130.59 且标 REAL_DATA）与 R-A4-12（`fig_perf_throughput.png` 实际存在且与 fig6 同字节）；已追加 `correction_005` 撤回为 RETRACTED_BANNED_METRIC（原字节/原清单 SHA 不变），并完成代码防再犯 + 5 项新测试（全量 36 passed）。

## 1 结论
1. smoke #1 失败：case 目录缺 `<base>.vkey` → 已修（输入准备类修复，未改 plan/几何/哈希）。
2. smoke #2 失败：`Could not find global edge for trailing wake!` / `Looking for edge with nodes: 457, 458`（网格/尾迹拓扑）。按 Lead smoke #3 规则（仅输入/环境类修复）判定**不跑 #3**，本批 **FAIL 停机**，不消耗剩余 37 次预算。
3. 零求解工具链（manifest/checkpoint/并发 bench/中文图库）全部交付并通过 36 项测试。
4. 吞吐、每进程内存、失败率、推荐 worker 数 = **NOT_RUN**（无有效 solver 运行，不给出数字）。

## 2 代码与产物（本树内）

| 路径 | 说明 |
|---|---|
| `research/concorde_metaopt/dreal001/perf/artifacts.py` | bytes+SHA256、`data_manifest.json`+`SHA256SUMS.txt`、`verify_manifest`（size/hash 独立判定） |
| `.../perf/checkpoint.py` | `CaseIdentity(case_id,geometry_sha256,solver_config_sha256)`、启动记账、`should_skip`（raw bytes+sha 校验）、`build_resume_plan` |
| `.../perf/bench_vspaero.py` | approval+window token 双门禁、Popen 前写 `solver_start`、并发档 1/2/4/8、peak RSS/CPU 采样、polar 解析、metrics/summary/manifest/图；`run/dry-run/resume`。**本轮修改：`prepare_case_inputs` 增加 `.vkey` 边车复制并纳入输入清单** |
| `.../perf/figures.py` | 7 类中文图、字体自检（no_tofu）、NOT_RUN 占位 |
| `.../perf/build_figure_gallery.py` | 图库总装 + `gallery_index.json`（逐图 REAL_DATA/NOT_RUN + bytes + SHA256） |
| `.../perf/make_probe_geometry.py` | OpenVSP 3.55 API 探针几何生成（脚本化可复现） |
| `.../perf/geometry/probe_wing/*` | `.vsp/.vspgeom/.vspaero/.vkey`（GEOMETRY_SHARED_WITH_A1=NO） |
| `.../perf/plans/PERF_20261110_A4_01/` | plan.json、plan_smoke.json、approval.json（Lead 权威件，A4 未改） |
| `.../perf/runs/PERF_20261110_A4_01_smoke/` | FAIL 证据：summary.json、metrics.csv、solver_attempts.jsonl、evaluations.jsonl、data_manifest.json、SHA256SUMS.txt、cases/PERF_P1_01/{solver_stdout.txt,solver_stderr.txt,.vsp,.vspgeom,.vspaero,.vkey}、figures/ |
| `research/concorde_metaopt/tests/test_dreal001_r4/` | 36 项测试（vkey 边车 2 + 失败吞吐口径 2 + A1 vspgeom sha 1 + corrections/attempt_id 6 + 吞吐图撤回/防再犯 5） |
| `docs/planning/dreal001_a4_perf_report.md` | 中文交付/失败报告 |

## 3 测试

```powershell
& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r4 -q -p no:cacheprovider
# 36 passed in 2.24s（vkey 边车 2 + 失败吞吐口径 2 + A1 vspgeom sha 1 + corrections/attempt_id 6 + 吞吐图撤回/防再犯 5）
```

覆盖：manifest 往返 + `verify_manifest` 的 missing/size/hash 分类；checkpoint 仅在 raw sha 一致时跳过；启动计数先记后跑、失败也计；坏行容忍；resume plan 分类；approval/window 门禁（无 token 退出码 2、未批准 SystemExit）；polar 正常解析与解析失败不伪造；吞吐按 level_wall 口径；RunContext 使用 approval.max_starts；图库无 run 全 NOT_RUN、伪造 run 出 REAL_DATA；字体 no_tofu；**`.vkey` 边车复制进 case 并与 sha256 入清单**。

## 4 关键 SHA256

| 对象 | SHA256 |
|---|---|
| approval.json（3227 B） | `11713385FEC54F19EBE30CC2A1B511AAD8536C25867A3822C29241D1194D024C` |
| plan.json（2222 B） | `F6E64F9029D115A049BE21FC23FCBA913546B2C21FD36ED47DA7228CEC51CD23` |
| plan_smoke.json（2337 B） | `66BBCB42E2238BF3A2BC64897DCEF6146EE449FB3EB9349F0CF36EF915226068` |
| probe_wing.vsp（87721 B） | `706E212CEB1C9B47CBB5E93E540F89346C8E8AC1CFD4560AAFB508748A77DC64` |
| probe_wing.vspgeom（251021 B） | `306AB82BB239848C6F6F340FF35737F7541F60408F36B8431811B2D3484DC7D4` |
| probe_wing.vspaero（853 B） | `F51ED59FDDA7E429D9C78583DCADF8CF1773678A51DBB07C4CFA2F3179DBFE43` |
| probe_wing.vkey（322 B） | `768357352D7F8CA815F6B7779918C81E4917C65A6EC8BA19B620088E35C644B1` |
| run summary.json（1222 B） | `1BBB2B9737228C11D34CED20623D01FCD3C6458940139BDC1A68BCD3BD9ADBB5` |
| run data_manifest.json（1568 B） | `7C18597440A694A95A99822DCF0562297539A764A184B8AE327DDCBF88A3BF66`（verify ok=true, checked_files=5） |
| run SHA256SUMS.txt（474 B） | `457009879798BDDC5EA7664435829EBD51DA61E50AF92492589F5A0C35EC5AD9` |
| run solver_attempts.jsonl（2376 B） | `D51041E418A787A0359A7354C47C5A25B2AF2F0BAAB1EBB6ADF79B0C1A37AB37` |
| run evaluations.jsonl（4432 B） | `8D92D121BE92A5500A7887FC93E686CBA78C34E8994B2E605C039A8EB5630DFB` |
| gallery_index.json（2960 B） | `999E239203F1BDEF5B277E7FBC4B47F1059D80A96E40C6923168057DF6E67BD1` |
| corrections/correction_001.json（2543 B） | `B3BCC5B606271599E4BD44BFAD9DE36C21487AC21158DBFB8307B434144B4528` |
| corrections/correction_002.json（3478 B） | `E7AF69D7557E6379BD066FAE11EB7133A7C0CF27990DF665711901DBD1BE92BE` |
| corrections/correction_003.json（2001 B） | `AB67BAB4677A384DF0260377C9088C6D5A0D4F741AEF3C4DD2A52FDA034337E5` |
| corrections/correction_004.json（1257 B） | `6CE00B9034B1195E2A37FBF3062F684423536B29ADF11668BBE55B7088B180E8` |
| corrections/correction_005.json（5635 B，撤回 fig6/fig_perf_throughput） | `2EFD1CAB7F85F98B162FE660B35A5F057B276A62E7F99AF3741AF6DF269998FE` |
| corrections/correction_index.json（2101 B，5 件） | `1E373C168DE1DF74141F709D6B17EDF049A6F44FBBA6842D198F8252EE808CE3` |
| corrections/SHA256SUMS_corrections.txt（490 B，5 行） | `B3BD8C66D3FB8B6CB1C7477A4351AE9A7C3F732C2363D793201A65669476E90B` |
| figures/fig_perf_throughput.png（73141 B，与 fig6 **同字节**，已撤回） | `1B60689466E8A3992D343D8AB7760F020385A8E4B8E05CBB3E9E0CD4FECB2257` |
| fig6_resources_and_failures.png（73141 B） | `1B60689466E8A3992D343D8AB7760F020385A8E4B8E05CBB3E9E0CD4FECB2257` |
| fig7_evidence_isolation.png（64783 B） | `FD76626E8183804AA8F111F54FC4ED01557DE8A5BD4AB6CFA9D5663A64967D6C` |

## 5 记账核对（A5 可复核）
- `solver_attempts.jsonl` 共 4 行：start(08:22:59.795, starts=1)、end(08:22:59.811, exit=1, wall 0.012671)、start(08:24:25.002, starts=1)、end(…, exit=1, wall 0.012671→#2 0.018473)。**start 行数 = 2 = summary.physical_solver_starts = 与真实 Popen 次数一致**。
- `evaluations.jsonl` 2 行，status=CRASHED，cl/cdi=null，`polar_ok=false`，未伪造数值。
- 每次启动均带 geometry_sha256=`c07403131b0c039e5613572b58335aa95bc92b9be398bfb5ddd59fb5d2bdba98`、solver_config_sha256=`58ac4df85bc009f087c7fcdeef37f969fab9b273bea3cdb0451999177f685378`。

## 5.5 与 A1 口径对齐（本轮新增）
- A1 canonical 启动：`cwd=<case_dir>` + `vspaero.exe -omp <N> <basename>`，α/Mach 扫描写在 `.vspaero`；A4 本批使用自拟 `-fs` 模板，**未对齐**，下一轮改用 A1 口径。
- hash 定义：A1 `geometry_sha256 = sha256(.vspgeom raw bytes)`；A4 `geometry_hash` 是多文件 canonical digest。已在 `summary.json` 并列输出 `geometry_vspgeom_sha256`（A1 定义）与 `geometry_sha256_definition`，双方可互验；solver_config 与 case_sha 的对齐项见报告 §5.3。
- A1 计划 16:45–17:15 在 `research/concorde_metaopt/dreal001/geometry/artifacts/` 产出共享轻量几何 + setup + SHA，下一轮优先采用以消除 GEOMETRY_SHARED_WITH_A1=NO。

## 5.6 A5 FAIL / Lead 裁定与补件（2026-11-10 16:30–16:32 CST）

- A5（m00792，对 HEAD=6b4c149 只读）：**VERDICT=FAIL（证据完整性）**，维持两项 FAIL：①`data_manifest.json.physical_solver_starts=0` 与台账 2 条 solver_start、summary=2 矛盾；②`solver_attempts.jsonl` 无 `attempt_id`。另有 4 项 CHANGES_REQUESTED（派生 approval 字段、2130.59 吞吐投影禁引用、plan 残留 45、case_matrix_digest digest_scope）。
- Lead（m00825）裁定：允许 **corrections 追加文件** 方式补齐，**不得重生成/覆盖既有证据**；本批归档为「工程失败停机记录」，结论固定 **NOT_RUN/FAIL**，不签 PASS，不引用任何吞吐/内存/worker 数字；剩余 37 次不结转。
- 补件（`runs/PERF_20261110_A4_01_smoke/corrections/`，原证据字节与 SHA 一律不变）：
  - `correction_001.json`（FAIL-1）：原 `data_manifest.json` SHA `7C185974…BF66` 保持不变；`physical_solver_starts=0` 解释为旧生成器固定值（语义=成功完成启动数，本批 2 次均 CRASHED）；权威计数 2（= solver_start 行数 = summary），并给出后续批次修复与强校验计划。
  - `correction_002.json`（FAIL-2）：4 行 → `PERF_P1_01-a01`/`a01`/`a02`/`a02` 映射；工具已改：`checkpoint.record_solver_start` 派生 `attempt_seq/attempt_id`，`record_solver_end` 与 `record_evaluation` 使用同一 `attempt_id`（evaluation 缺省时由账本派生并标 `attempt_id_derived=true`）。
  - `correction_003.json`（CR）：派生 `approval.json` 缺失的 canonical_batch_id / batch_id_naming_exception / case_matrix_digest(+digest_scope) / parallelism / limits / timeouts 已由 `run_batch` 在**后续批次**写入；既有派生文件不改写。
  - `correction_004.json`（CR）：plan.json “批准 45 次”= 申请值，实际批准 **39**（37→39）；不改写 plan（SHA 保留），报告与回执已披露。
  - `correction_005.json`（A5 终审 R-A4-11/R-A4-12）：撤回 `figures/figures/fig6_resources_and_failures.png`（73141 B，`1B606894…B2257`）与**同字节**的 `figures/fig_perf_throughput.png`，状态 `RETRACTED_BANNED_METRIC`、`citation_allowed=false`；永久禁用 2130.591 case/分钟（替代证据：本批吞吐=NOT_RUN）；更正 `correction_004` 中“fig_perf_throughput 未生成”的不准确表述（实际存在、未登记 gallery、已一并撤回）；原图字节与旧 `gallery_index.json` SHA `999E2392…67BD1` 不变。
  - 索引 `correction_index.json` + `SHA256SUMS_corrections.txt`（**5** 个 correction 的 SHA256 见 §4）；旧 `SHA256SUMS.txt` 未覆盖。
- 复核方式：`test_corrections_and_attempt_id.py` 断言 correction_001 的原 SHA 与盘上一致、correction_002 覆盖全部 4 行且 start/end 同号、索引 SHA 与文件一致（索引与 SUMS 行数=盘上 correction 文件数）、Ledger 新写入 attempt_id 配对且不改变启动计数、correction_005 撤回两图同 SHA 且禁止引用。
- 代码防再犯（A5 R-A4-11）：`figures.throughput_is_valid`（None/0/NaN/inf 无效）、`fig_resources_and_failures` 只画有效行否则 NOT_RUN、`bench_vspaero.write_figures` 无有效吞吐不生成图且遇撤回声明不生成、`build_figure_gallery` 读 `corrections/*.json` 撤回声明并把归档 run 的 fig6 标 `RETRACTED_BANNED_METRIC`（不重绘被禁内容）。

## 6 未完成项与风险
| 项 | 状态 | 说明 |
|---|---|---|
| 36 次并发吞吐批次 | NOT_RUN | smoke 未过，按批准条件停机 |
| 1/2/4/8 吞吐/内存/失败率/推荐 worker | NOT_RUN | 不给出数字 |
| 尾迹拓扑根因 | 未验证 | H1（探针翼网格过粗，251 KB vspgeom vs A1 历史成功 2 MB）最可能 |
| `summarize` 失败 case 吞吐投影 | 已修（后续提交，25 tests） | 原实现把失败 case 退出耗时当求解耗时（2130.591 case/min）；现仅统计 VALID/CACHED_SKIP，整档无有效 case 给 null(NOT_RUN)，原值移入 raw_throughput_cases_per_min；历史 summary.json 保留为缺陷证据 |
| fig1–fig5 | NOT_RUN 占位 | 无有效数据不画假图 |
| 12 维几何对照 | NOT_RUN | 依赖 A1 canonical 几何 |
| A5 复核 | **FAIL（证据完整性，不签 PASS）** | 首轮 FAIL-1/FAIL-2 + 4 项 CR 已用 correction_001–004 补齐；终审新增 R-A4-11/R-A4-12 已用 correction_005 撤回补齐；A5 重跑 `dreal_audit.py` 后关闭（预期 FAIL_STOPPED_ARCHIVED_NOT_RUN） |
| 吞吐投影 2130.591 case/min | **永久禁用** | 失败 case 的无意义投影；summary 保留为缺陷证据。fig6（`figures/figures/fig6_resources_and_failures.png`）内嵌该数字，已由 correction_005 撤回为 RETRACTED_BANNED_METRIC；`figures/fig_perf_throughput.png` 与 fig6 同字节，一并撤回（原字节不变） |

下一轮前置条件：几何/网格细化 + 四件套输入（.vsp/.vspgeom/.vspaero/.vkey）内置 + 独立 smoke 通过 + Lead 重新批准 window token 与预算（本轮剩余 37 次不结转）。

## 6.1 后续提交
- 6b4c149：吞吐汇总排除失败 case（整档无有效 case 给 null/NOT_RUN）+ 文档同步。
- 第三个（2112f8e）：summary 新增 `geometry_vspgeom_sha256`（A1 定义）与 `geometry_sha256_definition`；报告/回执新增 §5.3 A1 口径对照；测试 26 passed。
- 第四个（58b811d）：corrections/correction_001–004 + correction_index + SHA256SUMS_corrections；`checkpoint.py`/`bench_vspaero.py` 强制写 attempt_id（start/end/evaluation 同号）；派生 approval 记录补齐治理字段；报告 §7.1 与回执 §5.6；新增 5 项测试（共 31 passed）。
- 第五个（本提交）：correction_005（fig6/fig_perf_throughput 撤回为 RETRACTED_BANNED_METRIC，原字节/清单不变）+ 索引与 SUMS 更新（5 件）；`figures.throughput_is_valid`、`fig_resources_and_failures` 只画有效吞吐、`write_figures` 不生成被禁/无效吞吐图、gallery 读撤回声明强制 RETRACTED；报告 §0/§7.1/§7.2 与回执 §3–§7 同步；新增 5 项测试（共 36 passed）。

## 7 合规声明
- 只写本工作树；未写 `D:\RCAIDE`（仅 pip 临时目录为系统副作用，非本次）、`D:\RCAIDE\dnext001\repo`、其它 `wt-*`。
- 未 push、未合并 main、未改写历史或冻结产物（S1/S2/S3 run/manifest/SHA 未触碰）。
- 未修改 `approval.json` 的批准语义（Lead 修订 max_starts=39 与 amendment_log，A4 仅读取并记录 SHA）。
- 未改动 RCAIDE 原环境；本阶段未涉及 CUDA 训练。
- 本回执不含气动/优化收益结论；`fuel_burn_kg=null`；物理求解启动数=2，全部真实、全部记账。
- A5 结论为 FAIL（证据完整性），本回执与报告均不以 PASS 表述；本批归档结论为 **NOT_RUN/FAIL**（工程失败停机记录）。
- plan.json 中“批准 45 次”为旧申请值，实际批准 39（37→39 修订）；plan 未改写属**披露项**（correction_004）。
- corrections 为追加文件，未改动 `data_manifest.json`/`summary.json`/`solver_attempts.jsonl`/`evaluations.jsonl`/`metrics.csv`/`SHA256SUMS.txt`/`approval.json`/`gallery_index.json`/fig6/fig_perf_throughput 的任何字节；correction_005 为**追加撤回声明**，不重绘、不重写被撤图。
- 本批结论固定 **NOT_RUN/FAIL**（工程失败停机记录）；禁止引用 2130.59/2130.591 及任何吞吐、内存、worker 数字；真实求解启动数=2，全部记账。
- task-9 以「工具链交付完成 + 真实吞吐批次 FAIL/NOT_RUN（physical_solver_starts=2，预算不结转）」关闭；下一轮需 Lead 新 window token + 新预算 + A1 canonical 几何。
