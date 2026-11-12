# D-REAL-001 A4｜R6 任务回执（task-13：并行评价执行器 + PERF_02 并发吞吐计划）

- **分支**：`research/dreal001-a4-perf-figs`（工作树 `D:\RCAIDE\dnext001\wt-real-a4-perf-figs`）
- **基线**：`3c0bf9b`（PERF_01 归档闭环后）
- **任务**：共享任务 `task-13`（R6a 执行器 / R6b PERF_02 计划）
- **本轮真实 solver 启动数**：**0**（`physical_solver_starts=0`，`physical_call_count=0`）
- **本轮数据来源**：`MOCK`（合成，非物理）＋只读加载 A1 接口；无 VSPAERO/SU2/RCAIDE 真实调用
- **日期**：2026-11-10

---

## 0. 结论摘要

1. R6a 已交付 `dreal001/executor/`：`ParallelEvaluator` 支持每设计独立 case 目录、线程安全 append-only 台账、
   先记账后启动、超时/失败计费、6 类自动停机、checkpoint/resume、§12.11 保留策略，并有 MOCK 端到端测试。
2. MOCK 端到端证据已生成：`DREAL001-MOCK-20261110-01`（8 case，workers=3），台账 8 次启动/8 次结束全守恒，
   manifest 56 个文件逐一校验通过（`physical_solver_starts_source=ledger_zero`）；这是**合成链路验证，不是性能结论**。
3. R6b 的 `PERF_02` 计划已写好（并发 1/2/4/8，24 次 starts，max_starts=26），当前
   `input_status=PENDING_A1_P0`、`approval.status=PENDING_APPROVAL`、无 window token → **未启动、不得启动**。
4. 测试：`test_dreal001_r4 + test_dreal001_r6` 共 **108 passed**（R4 36 + R6 72；相对 R6a 新增 25 项 A5 三轮修复测试）；
   **归档复跑**（`git -c core.autocrlf=false archive` 解包）**106 passed + 1 skipped**（skip=无 `.git`），可脱离本地工作树复现。
5. 明确边界：本轮**没有任何**吞吐、加速比、worker 数结论；PERF_01 的 2130.59（case/分钟）永久禁用、未引用。
6. **R6b 零求解三件套已交付**（本轮追加）：`inputs.py`（A1 模板重算 SHA + 23 项校验 + `fill_plan`，禁止手抄）、
   `dry_run.py`（A1Adapter 零物理接口演练 10/10 通过、只读 replay P0 polar 识别 32≠7 缺陷）、
   `perf_runner.py`（approval+window 双门禁、逐档并发、资源采样、summary/metrics/manifest/自动 correction）
   ＋ `sampler.py`、`corrections.py`；24 case 的 mock 排练流程通过（`physical_solver_starts=0`）。
   真实批次仍 **NOT_RUN**，等 A1 production 模板与 Lead 签发 approval/window token。
7. **A5 对 R6a 的 7+1 项已修完**（R-A4R6-01..08；详见 §3.1）：MOCK `physical_solver_starts=0` + `synthetic_attempts` 单列；
   预检前置（失败只写 `preflight_failures.jsonl`，不记账）；缓存指纹 v2（模板/几何/求解器/输入 SHA）；
   manifest 覆盖 21 类产物 + status 真实；A1 依赖显式化（env/参数 + commit/逐文件 SHA）；attempt 级目录隔离；
   停机枚举统一；物理字段占位（P2 前补齐）。修复后零求解证据已重生成（SHA 见 §5.1）。
8. **A5 第二轮复审（F-R6B-01..06）已修完**（详见 §3.2）：REAL 批次入口必须显式 A1 plan/geometry（优先级 显式>plan>env>推断，fail-closed），
   批次 preflight 确实调用 A1 `solver_runner.preflight`；dirty A1 默认拒绝、书面例外才放行；manifest 启动计数三态（`ledger_zero`）；
   根 summary 标 `LAST_LEVEL_ONLY`；`gate_selfcheck.json` 用当前 plan 重生成；MOCK manifest 补 `synthetic_attempts`；
   另修逐档 `evaluator.prepare` 覆盖派生 `run_config` 的缺陷（现在写 `run_config_level<workers>.json`）。
9. **A5 第三轮复审（F-R6C-01/02）已修完**（详见 §3.3）：证据 EOL 归一化导致「公布 SHA ≠ git blob SHA」；
   `.gitattributes` 增嵌套 `runs/** -text`，159 件证据 `--renormalize` 使 blob 字节 = 工作树字节；
   追加 `correction_006` 披露 gallery 双口径 SHA（`999E2392…`/`86E8A076…`）；证据 SHA 统一采用 **canonical content** 口径。

---

## 1. 交付物清单

| 路径 | 说明 | SHA256（本回执生成时） |
|---|---|---|
| `research/concorde_metaopt/dreal001/executor/__init__.py` | 包导出 | 见 git 提交 |
| `.../executor/models.py` | ExecutorConfig / CaseSpec / CaseOutcome / RunSummary / MockConfig（含 A1 依赖/物理字段、合成计数、`allow_dirty_a1`/`a1_dependency_snapshot`） | `BE4FA9F01975F15D9236F1E4D529AB61C8F9E047D91FA114832F64BD907D6922` |
| `.../executor/ledger.py` | 线程安全 append-only 台账（物理/合成分离、preflight_failures） | `6E05D00B224095C617DD91DD84450176A5BE967ADC2F2DBF5915480192E965A2` |
| `.../executor/stops.py` | 自动停机条件（枚举与 plan 统一） | `6BA0C1B284C989A725500FB7AD85BDF4ED28AEA279584BDAFF35CD464E9E44FC` |
| `.../executor/runners.py` | MockRunner + A1Adapter（显式 A1 来源、依赖 SHA、完整 preflight、dirty 拒绝、`verify_dependency`） | `E702C1733CA9AF041C80C3A137279FFC40278E03E4E91DCB4CAE72C64793C457` |
| `.../executor/evaluator.py` | ParallelEvaluator（缓存指纹 v2/预检前置/attempt 隔离/合成计数/A1 快照与 dirty 拒绝/不覆盖派生 run_config） | `F37A74FAF4E7BE8998EA3C58E5AFA9379B0F255FFBFED747FE962A7B279B30BC` |
| `.../executor/plan.py` | PERF plan 加载与静态校验 | `3CE4152D521DF2A71B00F0437497F18A7E2390FF7C62898E3FFC74C9E5B08DD6` |
| `.../executor/demo_mock.py` | MOCK 端到端演示/证据生成 CLic | 见 git 提交 |
| `.../executor/runs/MOCK_R6A_20261110/` | MOCK 证据 run（summary/metrics/attempts/evaluations/cases/manifest/SHA256SUMS） | 目录合计 63 files / 121184 B |
| `research/concorde_metaopt/dreal001/perf/plans/PERF_02/plan.json` | R6b 申请计划（**未批准**；含 physics 占位与 internal_cases_mismatch） | `52AA89A97F302801233C8A164E7D9839FE3C6BC99DACF8B563C9741B64EDCE22`（5470 B） |
| `research/concorde_metaopt/dreal001/perf/plans/PERF_02/README.md` | 计划说明 | 见 git 提交 |
| `research/concorde_metaopt/tests/test_dreal001_r6/` | R6 测试（66 项，9 个文件 + helpers） | 见 git 提交 |
| `research/concorde_metaopt/dreal001/perf/artifacts.py` | **修改**：`build_manifest()` 启动计数三态（`not_provided`/`ledger_zero`/`ledger_nonzero`） | `54239064EC1D390E17598C372D83A8E821ED2D40B87CA6E2642042FD11B09CD3` |
| `.../executor/inputs.py` | **本轮新增**：A1 模板发现、23 项合同校验、`fill_plan` 写 READY（禁止手抄 SHA） | `CACD0E951AF3BC6FF9DC47CBDFF8F28A96E4FE2C6303A6BDCAA9830192F39F82` |
| `.../executor/dry_run.py` | A1Adapter 零物理接口演练 + 只读 replay（A1 目录可推断/显式指定） | `3BD3DF3C4DD97D69E793F0985EFBA4109C14350A763C50C3C60DDFD456E3D9CF` |
| `.../executor/sampler.py` | **本轮新增**：仅当前进程子孙的 RSS/磁盘/wall 采样 | `844F02DBD612587766131F08E551C0DFDA23C54E2B021CE822F7228E759246B9` |
| `.../executor/corrections.py` | **本轮新增**：补件脚本化（编号/index/SUMS/原字节不动） | `3350168D107014F85C2840AD0324152F3861B31590079A52E5AB0EDF2D3267CF` |
| `.../executor/perf_runner.py` | PERF 批次执行（双门禁/逐档/A1 解析 fail-closed/三态计数/summary/manifest/correction） | `2823196F0CDC3C7B103A7495B2D2E9D1BE00C56A03337598EECDD5B029560560` |
| `.../executor/runs/DRYRUN_R6A_A1_INTERFACE/` | **本轮新增**：dry-run 证据（`physical_solver_starts=0`） | 见 §5.1 |
| `.../executor/runs/MOCK_R6B_REHEARSAL/` | **本轮新增**：24 case mock 排练（合成，禁作性能） | 见 §5.1 |
| `docs/planning/dreal001_a4_r6_zero_solver_report.md` | **本轮新增**：零求解交付报告 | 见提交 |

MOCK 证据关键文件：

| 文件 | SHA256 |
|---|---|
| `runs/MOCK_R6A_20261110/summary.json`（1180 B） | `BBE8117C0F16A9BCC0C57B62109652436E91DF2406F016A2930614222F90C750` |
| `runs/MOCK_R6A_20261110/metrics.csv`（2151 B） | `1DD77CA4B9F4BF0F59CDFFEA46DCF825999BCDEE22C6250302BD94843B7A0FB1` |
| `runs/MOCK_R6A_20261110/data_manifest.json`（12939 B） | `518802DD5F15B5BB9C70A77DF6998339C613614640D372DF176C4DC03D928285` |
| `runs/MOCK_R6A_20261110/solver_attempts.jsonl`（23606 B） | `907C93D0C1E9983A56354D3D91F64B1E6E9B8B5595CF021AA75847EAA54B91DF` |

manifest 校验（`verify_manifest`）：`ok=true, checked_files=56, missing=[], size_mismatch=[], hash_mismatch=[]`；`physical_solver_starts_source=ledger_zero`、`extra.synthetic_attempts=8`。

---

## 2. R6a 设计要点（为什么这样写）

1. **每设计独立 case 目录**：`runs/<run_id>/cases/<case_id>/`，模板 `.vspgeom/.vkey/.vspaero` 逐 case 拷贝并记录
   `source_sha256` 与拷贝后 SHA；case 之间不共享文件，避免并发写同一输入。
2. **台账唯一写者**：A1 的 `solver_runner.run_case` 会写自己的 ledger，批量并发有计数竞争；因此执行器只
   **只读调用** A1 的 `_run_process/_collect_outputs/parse_polar_file/_internal_case_info`，账本统一由
   `ExecutorLedger`（`threading.RLock`）写。每行 `solver_start` 带 `physical_solver_starts=1`，
   `solver_end` 带 `=0`，均 fsync；重复 attempt_id / 预算超限直接抛错（fail-closed）。
3. **先记账后启动**：`record_start()` 成功后才 `Popen`；失败/超时/解析失败/内部异常也都走 `record_end()`，
   计 1 次启动（治理 §12.5）。`attempt_id = <case_id>-a<seq02>`，重试递增。
4. **停机 6 类**（`stops.py`）：预算耗尽、连续失败（默认 3）、内部子案溢出/不等于 expected（7）、
   主系数 NaN/Inf、磁盘可用 <50 GiB、run 目录超 `max_disk_bytes`、墙钟超 `wall_budget_s`。
   触发后不再派发新 case，剩余标 `NOT_RUN`，原因写 `summary.stop_reasons`。
5. **resume**：只认"已有 `SOLVED` evaluation + `case_result.json` 内 output SHA/bytes 全部一致"的 case →
   `CACHED_SKIP`（不新增启动）；否则重跑。`CACHED_SKIP` 不计入本次 `valid`、不计入吞吐（没有新计算）。
6. **保留策略（§12.11）**：`retention_enabled` 时对 T1 后缀（`.adb/.lod/.groups/.quad.cases/.csf/...`）
   先写 `retention.jsonl`（path/bytes/sha256/attempt_id）再删，case_result 内标
   `archived_deleted_with_sha=true`；PERF 批次默认**不回收**。
7. **汇总口径**：`summary.physical_solver_starts` 由台账行数计算；`data_manifest.physical_solver_starts`
   由调用方传入台账计数（本轮同时修了 `perf/artifacts.build_manifest` 的硬编码 0，违反 §12.8）。
   吞吐只统计 `VALID` case；失败/超时/NOT_RUN 不进吞吐。`fuel_burn_kg=null`，`validation=INTERNAL_PERF_ONLY`。

MOCK 证据 run 数值（**只证明链路，不是性能**）：planned=8、physical_solver_starts=0、synthetic_attempts=8、
mock_solver_starts=8、valid=8、internal_solver_cases_total=56、`physical_call_count=0`、`wall_s=0.032`、
`stop_reasons=[]`。summary 内的吞吐字段是**合成 mock 数字**（无进程、无 sleep），禁止作为真实吞吐或
加速比引用（R6A 旧版 mock 吞吐数字亦永久禁用）。

---

## 3. 测试

命令（工作树根目录）：

```
& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r4 research/concorde_metaopt/tests/test_dreal001_r6 -q -p no:cacheprovider
```

结果（工作树）：**108 passed in 6.44s**（R4 36 项沿用 + R6 72 项；相对 R6a 新增 25 项 A5 三轮修复测试）。

归档复跑（A5 复核协议，必跑）：

```
git -c core.autocrlf=false archive --format=tar -o <tmp>.tar <commit>
tar -xf <tmp>.tar -C <tmp>/arc
# 在 <tmp>/arc 下：
& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r4 research/concorde_metaopt/tests/test_dreal001_r6 -q -p no:cacheprovider
```

实测 **106 passed + 1 skipped**；解包目录内 7 件公布证据 SHA 全部逐字节复现（bad=0）。默认 `core.autocrlf` 的 `git archive` 同样 106+1。

R6 测试覆盖：

| 文件 | 覆盖 |
|---|---|
| `test_plan.py`（9） | PERF_02 计划合法/未批准/矩阵 24 且每档可跑满/-fs 拒绝/expected_internal 拒绝/停机条件缺失/预算不足 |
| `test_mock_executor.py`（10） | 端到端产物与台账守恒、失败/超时计费、resume 不新增启动、预算/连续失败/内部溢出/NaN 停机、T1 保留先记 SHA 后删、8 线程并发台账守恒、REAL 无 approval 拒绝 |
| `test_ledger_stops.py`（5） | attempt 序号递增、重复 attempt 拒绝、预算 fail-closed、24 线程并发写、StopGuard 内部子案判定 |
| `test_adapter.py`（3，A1 包存在时运行） | 只读加载 A1（api 三个入口可用、SHA 64 hex）、目录缺失不可用、未批准 preflight 拒绝、argv 组装 |
| `test_inputs_dryrun.py`（6） | A1 模板 23 项全过；篡改 vkey SHA/alpha/`solver_started` 失败；`fill_plan` 写 READY 且 plan SHA 变；dry-run `physical_solver_starts=0`、拒绝未批准、StopGuard 拦截 32≠7 |
| `test_corrections.py`（4） | 编号 001→002、target bytes+SHA、原 `.jsonl` 字节不变、index/SUMS 覆盖、篡改检测 |
| `test_sampler.py`（3） | 子进程 descendants、RSS>0、采样快照、只审计 vspaero 子孙 |
| `test_perf_runner.py`（9） | 无 approval/input_status 未 READY/未批准/plan SHA 不符/token 缺失或不符/窗口过期 均拒绝；全就绪通过；mock 放行；分组 4/4/8/8；推荐 worker |
| `test_r6b_fixes.py`（6，新增；含 mock 汇总 level_synthetic_attempts 回归） | 预检失败不记账（physical=0、无 solver_start、case_result=NOT_RUN）；指纹变化不跳过 + `superseded/` 归档；manifest 覆盖 21 类产物 + status；verify 检出 extra；停机枚举一致 |
| `test_adapter.py`（重写） | A1 路径 env/参数显式、无硬编码默认、fail-closed；未批准拒绝；argv 无扫描旗标 |
| `test_mock_executor.py`（更新） | MOCK physical=0 / synthetic=N / mock_solver_starts=N；台账守恒按合成计数 |
| `test_r6c_eol_canonicalization.py`（5，第三轮新增） | `.gitattributes` 覆盖嵌套 `runs/**`；索引 blob = 工作树字节（无 `.git` 则 skip）；`correction_006` 重发 SHA 与盘上一致；corrections 索引路径 `corrections/<file>`；gallery 双口径 SHA 均披露 |
| `test_r6b_a1_dependency.py`（9，第二轮新增） | REAL 必填显式 A1 plan；geometry 目录优先级 fail-closed；批次 preflight 确实调用 A1 `solver_runner.preflight`（假模块、零进程）；dirty 拒绝/书面例外；manifest 三态；根 summary `LAST_LEVEL_ONLY`；逐档 prepare 不覆盖派生 run_config |

---

### 3.1 A5 对 R6a 的 7+1 项修复（本轮）

| ID | 修复 | 验证 |
|---|---|---|
| R-A4R6-01 | MOCK：`physical_solver_starts=0` + `synthetic_attempts`/`mock_solver_starts` 单列；台账按 `physical` 标志与 `source_kind` 分离；manifest 取台账物理计数 | 测试断言 physical=0；mock 证据 physical=0 / synthetic=8、24 |
| R-A4R6-02 | 缓存指纹 v2：模板逐文件 SHA/bytes、geometry/solver_config/solver_exe SHA、basename、expected_internal、x12、design_hash；digest 与结果不一致即不跳过 | 改 x12 重跑不跳过；旧目录归档 |
| R-A4R6-03 | 预检前置：归档→复制输入→完整预检→通过才 `record_start`；REAL 调 A1 `solver_runner.preflight`；失败写 `preflight_failures.jsonl` + NOT_RUN 结果，不记账 | 预检失败 0 启动、0 evaluation |
| R-A4R6-04 | 产物覆盖 21 类后缀（含 `.adb/.adb.cases/.lod/.groups/.quad.cases/.csf/.vkey`）；status 自动读 case_result；verify 增 unexpected 期望集检查 | manifest 168 文件全 VALID；extra 文件触发 ok=false |
| R-A4R6-05 | A1 依赖显式：`a1_geometry_dir`/env，无硬编码；记录 A1 commit/dirty + 逐文件 SHA；缺失 fail-closed | 无配置测试报错含环境变量名 |
| R-A4R6-06 | attempt 级隔离：旧 case 目录移入 `superseded/<case>-aNN/` + `superseded_index.json`（逐文件 SHA） | 重试/续跑不混用旧产物 |
| R-A4R6-07 | 停机枚举统一 `max_disk_exceeded`；plan 增 `internal_cases_mismatch`；`preflight_failed` 纳入停机原因 | plan/代码枚举一致测试 |
| R-A4R6-08 | evaluation/case_result 增 `physics` 与 `accounting` 字段；PERF 阶段 null，P2 前由 A1 production 输入补齐 | 字段落盘，null 不伪造 |

---

### 3.2 A5 第二轮复审（F-R6B-01..06）修复

| ID | 修复 | 验证 |
|---|---|---|
| F-R6B-02（blocker） | `perf_runner.resolve_a1_dependency()`：REAL 必须显式 A1 plan（CLI > plan.a1.plan_path > plan.a1_plan_path），geometry 目录 CLI > plan.a1.geometry_dir > env `DREAL001_A1_GEOMETRY_DIR` > 模板推断，缺失/非目录/缺模块 fail-closed；`A1Adapter.preflight` 缺 plan 即 `BackendNotReady`；批次 `preflight_attempt` 调 A1 `solver_runner.preflight` 并附 `verify_dependency` | 8+1 项测试（含假 A1 四模块实调 preflight、CALLS==1、无 solver 进程） |
| F-R6B-03（major） | A1 `dirty` 默认拒绝；`allow_dirty_a1` 为唯一书面例外，写入 `run_config.a1_dependency_exception` 且 digest 入缓存指纹 | dirty 拒绝 / 例外放行测试 |
| F-R6B-01（残留） | manifest 启动计数三态 `not_provided`/`ledger_zero`/`ledger_nonzero` | 三态断言；MOCK manifest 实测 `ledger_zero` |
| F-R6B-04 | 根 summary `root_summary_scope=LAST_LEVEL_ONLY` + note；派生 run_config 增 `executor_level_configs` | mock 实测 4 档清单 |
| F-R6B-05 | `gate_selfcheck.json` 用当前 plan `52AA89A9…CE22` 重生成（`4D7AE0B7…E1F`） | 证据 SHA 见 §5.1 |
| F-R6B-06 | MOCK manifest 补 `extra.synthetic_attempts`/`physical_call_count`/`mock_rehearsal` | mock 实测 `synthetic_attempts=24` |
| 额外（本轮发现） | 逐档 `evaluator.prepare` 不再覆盖派生 `run_config.json`，改写 `run_config_level<workers>.json`；循环结束补写派生件 | 测试 + mock 实测（派生件 + 4 档文件） |

> 全量测试 **102 passed**；零求解证据已重生成；`physical_solver_starts=0`。A1 production 模板未发布 → `inputs --write` **NOT_RUN**，`PERF_02` 保持 `PENDING`。

---

### 3.3 A5 第三轮复审（F-R6C-01/02）修复：证据 EOL 规范化

背景：A5 审 `5f8e6e8` 发现 `.gitattributes` 未覆盖嵌套 `runs/**`，含 CRLF 的 JSON 证据入库被归一化为 LF，
公布 SHA（工作树字节）在任何 `git archive` 复跑中不可复现（A5 实测 `archive 5f8e6e8` = 99 passed/3 failed）。

| ID | 修复 | 验证 |
|---|---|---|
| F-R6C-01（major） | 根 `.gitattributes` 增 `research/concorde_metaopt/dreal001/**/runs/** -text` 与 `research/concorde_metaopt/gpu/runs/** -text`；`git add --renormalize` **159 件**证据使 index/blob 字节 = 工作树字节；**不改写任何证据字节** | `git check-attr text` = unset；159/159 件 `git rev-parse :path` == `git hash-object path`；`git -c core.autocrlf=false archive` 解包后 5 件受影响 SHA + `correction_006` 全部复现（bad=0） |
| F-R6C-02（major） | 追加 `correction_006.json`（6068 B，`59C84C6F…E218`，type `EVIDENCE_SHA_CANONICALIZATION`）：披露 `999E2392…67BD1` = 工作树 2960 B 口径、`86E8A076…9CF0` = 旧 blob 2901 B 规范内容口径，旧 gallery blob 未改；重发 5 件证据新口径 SHA；索引/SUMS 保守重建（6 件：`2996CA4B…5E20` / `41EBC9A1…00D0`） | 索引/SUMS 覆盖 6 件且保留既有元数据；测试改为规范化口径断言 |
| 测试口径 | 新增 `test_r6c_eol_canonicalization.py`（5 项）；`test_corrections.py` 断言改 `corrections/<file>` 相对路径 | 工作树 107 passed；归档复跑 106 passed + 1 skipped |

> 受影响 5 件证据的旧 LF blob SHA（`DA64102B…`/`0A4C8700…`/`E3C83012…`/`9390B8F3…`/`3BC8AC92…`）
> 仅作缺陷证据记录，不再用于引用；本回执 §5.1 与报告 §4.3 全部为 canonical content 口径。
> `PERF_02` 仍 `PENDING_APPROVAL`/`PENDING_A1_P0`，本轮 `physical_solver_starts=0`。

**封存 PERF_01 run 的 verify 差异（主动披露）**：当前更严格的 `summarize_manifest_verify()` 对
`runs/PERF_20261110_A4_01_smoke` 返回 `ok=false`，但 `missing/size_mismatch/hash_mismatch` **三列表为空**（登记 5 件全部 hash-match），
仅 `unexpected_files=["PERF_P1_01/probe_wing.vkey"]` 与 `status_unknown=["PERF_P1_01"]`——
该 manifest 由 smoke #1 失败修复前的生成器写出（`RAW_SUFFIXES` 未含 `.vkey`、case 无 status）。**不重写封存证据**，
生成器已修；同 run `verify_corrections()` = `ok=true, count=6`（修复大写 SHA 比较误报，新增回归测试）。

---

## 4. PERF_02 计划（R6b，**未批准、未启动**）

- batch_id / run_id：`DREAL001-PERF-20261110-02`
- 用途：`INTERNAL_PERF_ONLY`（只测并发吞吐/内存/失败率；不作气动/优化结论）
- 矩阵：并发档 1/2/4/8，case 数 4/4/8/8 → **24 次** physical starts；`max_starts=26`（+2 smoke 预留，不结转）
- 配置：`vspaero.exe -omp 1 <basename>`，固定 7 个 alpha（-2/0/2/4/6/8/10）写入 `.vspaero`，**不带 `-fs`**；
  `expected_internal_cases = max_internal_cases = 7`
- 资源：`timeout_s=300`、`expected_disk_bytes=262144000`、`max_disk_bytes=1073741824`、
  `disk_free_min_gb=50`、`max_threads_total=8`（9950X 16C/32T，留余量）
- 停机：预算/连续失败 3/内部子案溢出/NaN/磁盘<50GB/超配额/墙钟 3600s
- 缺口：`input_status=PENDING_A1_P0` —— 等 A1 发布 production 模板 `.vspaero`（固定 7α、无 -fs）与
  `.vspgeom/.vkey` SHA；SHAs 当前为 `null` 占位
- 授权：`approval.status=PENDING_APPROVAL`、`approved_by=null`、`window_token=null` → **不得启动**

---

## 5.1 R6b 零求解证据（本轮追加）

| 文件 | bytes | SHA256 |
|---|---|---|
| `runs/DRYRUN_R6A_A1_INTERFACE/interface_dryrun.json` | 7646 | `2EFA0DBA1E41D1A83DE3B99AE577A6B0ACDA4AFA8623845FC3DE5CEB42794161` |
| `runs/DRYRUN_R6A_A1_INTERFACE/input_validation.json` | 8833 | `C6250AA2CDBBD491C0049E19FDF4A2260129B7C0A5109A11FF8A7EA42CF30A5C` |
| `runs/DRYRUN_R6A_A1_INTERFACE/input_validation_probe.json` | 8833 | `C6250AA2CDBBD491C0049E19FDF4A2260129B7C0A5109A11FF8A7EA42CF30A5C` |
| `runs/DRYRUN_R6A_A1_INTERFACE/gate_selfcheck.json` | 2220 | `4D7AE0B74A5110B0A0DF77A6B2878656E7A7E2BCBE91D3D59D83F85A32424E1F` |
| `runs/MOCK_R6B_REHEARSAL/perf_summary.json` | 9928 | `0F916590D889B13CAAC1AD144B251059EE432CFD3035F1B0CD400DDBEA2ADA99` |
| `runs/MOCK_R6B_REHEARSAL/perf_metrics.csv` | 3547 | `61A3DB651CDA5E4235E1672EF434A89D57050E39D7F24DA9156458DF74763EEE` |
| `runs/MOCK_R6B_REHEARSAL/data_manifest.json` | 38172 | `7060B5667E8C778CEE5C3A7B340EE0927F37C77F3ACD6E85E7E32269B866CEF8` |
| `runs/MOCK_R6B_REHEARSAL/solver_attempts.jsonl` | 78384 | `EB3F3990857F4D665D88D1CD79717D5E0BE8A3D3A73AA4A21AFB97FB0B655954` |
| `runs/MOCK_R6B_REHEARSAL/run_config.json`（派生权威件） | 1366 | `9547295A9649793318E522F9434E56983FF4CAA7B944307442211132808256E0` |
| `runs/MOCK_R6B_REHEARSAL/run_config_level{1,2,4,8}.json` | 1410×4 | `F199D043…57AD7` / `CB3F1827…5D98` / `3AB74471…EAF3` / `3B20CEC2…8C63` |
| `runs/MOCK_R6B_REHEARSAL/README.md` | 见盘 | 合成边界 + run_config 双件说明（重写） |
| `runs/MOCK_R6A_20261110/summary.json` | 1180 | `BBE8117C0F16A9BCC0C57B62109652436E91DF2406F016A2930614222F90C750` |
| `runs/MOCK_R6A_20261110/data_manifest.json` | 12939 | `518802DD5F15B5BB9C70A77DF6998339C613614640D372DF176C4DC03D928285` |
| `runs/MOCK_R6A_20261110/solver_attempts.jsonl` | 23606 | `907C93D0C1E9983A56354D3D91F64B1E6E9B8B5595CF021AA75847EAA54B91DF` |
| `perf/runs/PERF_20261110_A4_01_smoke/corrections/correction_006.json` | 6068 | `59C84C6F39E7ADCBEC4A5B9A7291AEEF314E4CDF15413C15B6DC534DC6E9E218` |
| `.../corrections/correction_index.json` | 2725 | `2996CA4BDC5023685ABB2F648CF3E079286F297EC5D3DA496537F978F5DB5E20` |
| `.../corrections/SHA256SUMS_corrections.txt` | — | `41EBC9A1373239AD07CED6505D1A1DF0F86A04B2D21069901C502A46484400D0` |

> **SHA 口径**：本表全部为 canonical content（`git -c core.autocrlf=false archive` 解包字节 = 工作树字节）。
> 不得以混合 EOL 的本地工作树原始字节作独立复核；历史提交内 LF blob 值见 §3.3。

- A1 候选模板 `PREFLIGHT_FIXED_NPTS_20261110T0907Z`：`geometry_sha256=40fdd436…6f4`、
  `solver_config_sha256=3c70d11a…b837`、23/23 校验通过、`internal expected=7`、`alpha=-2..10`。
- dry-run：10/10 通过，只读 replay P0 polar（32 行有效，CL=0.066551、CDi=0.0023325），
  内部子案实测 32 ≠ 7 → StopGuard `internal_cases_overflow`；输出目录无 `*.polar`/`*.adb.cases`。
- mock 排练：24 start/24 end/24 evaluation 守恒、`physical_solver_starts=0`、`synthetic_attempts=24`、
  `mock_solver_starts=24`、`level_synthetic_attempts=[4,4,8,8]`；`recommended_workers=8` **无意义**
  （仅证明字段/流程存在，禁止引用）。
- 修复后已重生成两处 mock 证据（R6A 8 case / R6B 24 case），`physical_solver_starts=0`；
  旧 SHA（283CE061…/DABA643B…/288CDBC6…/3A658955…/58A81E8D…/B41B1C47…/6121D2AC…/97EB774B…/193D597F…/655E039E…/12C2C55E…/28763DA6…/A424F817…/5F6F2044…）作废，以本表为准。

---

## 5. physical_solver_starts 与科学边界

- 本轮 `physical_solver_starts = 0`：无 VSPAERO/SU2/RCAIDE Mission/WaveDrag 进程；
  MOCK run（R6A 8 条 + R6B 24 条）`solver_attempts` 行全部 `source_kind=MOCK`、`synthetic_attempts=1`、
  `physical_solver_starts=0`、`physical_call_count=0`。
- 三层结论：`SOLVER_LOOP_VERIFIED = MOCK_ONLY`、`INTERNAL_AERO_OPTIMIZATION_GAIN = NOT_RUN`、
  `EXTERNAL_PHYSICS_SUPPORTED = NOT_RUN`。
- 未引用、未复制 PERF_01 的 2130.59（case/分钟）或任何失败 case 投影；PERF_02 计划本身 `physical_call_count=0`。
- `fuel_burn_kg = null`；不得由 CDi 变化外推燃油收益。

---

## 6. 未完成项与风险

| 项 | 状态 | 说明 |
|---|---|---|
| R6b 真实吞吐批次 | **NOT_RUN / 未批准** | 需 Lead 书面 approval（approved_by、max_starts=26、window token/时段）+ A1 production 输入就绪；窗口顺延至 19:10–19:40 |
| A5 修复复审（第二轮） | **CLOSED（六项）** | F-R6B-01..06 经 A5 m02072 确认全部 CLOSED |
| A5 修复复审（第三轮） | **WAITING** | F-R6C-01/02 已修完并提交；A5 按 `git -c core.autocrlf=false archive` 协议复审 `PASS` 前 REAL 不得启动 |
| `input_status` 自动填充 | **READY 能力就绪，未写** | `inputs.py` 对候选模板 23/23 通过；A1 正式发布后执行 `--write` 并回报 Lead |
| A1 接口 dry-run | **完成**（10/10） | 证明 A1Adapter/argv/POLAR 解析/内部子案计数/StopGuard 均可用，零物理 |
| PERF 执行脚本 | **完成**（mock 排练通过） | 双门禁 + 逐档并发 + 采样 + summary/manifest/自动 correction |
| 证据 EOL/复现性 | **FIXED** | 159 件 renormalize；归档复跑 106 passed + 1 skipped；复核必须用 archive 口径 |
| A1Adapter 真机执行路径 | 未实测真实启动 | 本轮只测只读加载/未批准拒绝；首个真实启动需 smoke + window token，属 R6b |
| A1 production `.vspaero`/.vspgeom/.vkey SHA | 待 A1 | 当前 plan 为 placeholder，`input_status=PENDING_A1_P0` |
| 并发吞吐/worker 建议 | NOT_RUN | 无真实数据；不得用 MOCK 数字或 CPU 并发（Issue#8 G1）替代 VSPAERO 结论 |
| 停机条件真实触发演练 | MOCK 已测 | 磁盘、墙钟、内部子案在 mock 层验证；真机需 R6b 窗口内观察 |
| 与 proposal `case_id` 序号 | 按治理 §3 | `<run_id>-c<index4>-<design_hash8>`，design 为 PERF 占位 12 维 |

---

## 7. 复现命令

```
# 测试
& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r6 -q -p no:cacheprovider

# MOCK 端到端证据（physical_solver_starts=0）
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.dreal001.executor.demo_mock --cases 8 --workers 3

# manifest 校验
& D:\RCAIDE\envs\RCAIDE\python.exe -c "from pathlib import Path; from research.concorde_metaopt.dreal001.executor import summarize_manifest_verify; print(summarize_manifest_verify(Path('research/concorde_metaopt/dreal001/executor/runs/MOCK_R6A_20261110')))"

# R6b 零求解：A1 模板校验（不写 plan）
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.dreal001.executor.inputs --plan research/concorde_metaopt/dreal001/perf/plans/PERF_02/plan.json --template-dir <A1目录> --report-out research/concorde_metaopt/dreal001/executor/runs/DRYRUN_R6A_A1_INTERFACE/input_validation_probe.json

# R6b 零求解：A1Adapter dry-run（不启动 solver）
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.dreal001.executor.dry_run --plan research/concorde_metaopt/dreal001/perf/plans/PERF_02/plan.json --template-dir <A1目录> --out research/concorde_metaopt/dreal001/executor/runs/DRYRUN_R6A_A1_INTERFACE

# R6b 零求解：门禁自检（无 approval/token 必拒绝）+ mock 排练
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.dreal001.executor.perf_runner gate --plan research/concorde_metaopt/dreal001/perf/plans/PERF_02/plan.json
& D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.dreal001.executor.perf_runner run --plan research/concorde_metaopt/dreal001/perf/plans/PERF_02/plan.json --out research/concorde_metaopt/dreal001/executor/runs/MOCK_R6B_REHEARSAL --mock

# 证据归档复跑（A5 协议；不信任本地工作树 EOL）
git -c core.autocrlf=false archive --format=tar -o tests/_tmp/tree.tar HEAD
tar -xf tests/_tmp/tree.tar -C tests/_tmp/arc
cd tests/_tmp/arc ; & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r4 research/concorde_metaopt/tests/test_dreal001_r6 -q -p no:cacheprovider

# PERF_02 plan 静态校验（不启动）
& D:\RCAIDE\envs\RCAIDE\python.exe -c "from research.concorde_metaopt.dreal001.executor import load_plan, validate_plan; p=load_plan('research/concorde_metaopt/dreal001/perf/plans/PERF_02/plan.json'); print(validate_plan(p))"
```

## 8. 合规声明

- 只写本工作树 `wt-real-a4-perf-figs`；未写 repo 主树/A1 树/其它 wt-*；A1 目录只读 import。
- 未改 approval.json、未 push、未合并 main、未改写冻结产物（PERF_01 证据只读）。
- 禁止项遵守：未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag；未引用禁用数字；未把 MOCK/GPU 装机当算法收益。
- 证据 SHA 口径统一为 canonical content（git blob = 工作树字节，F-R6C 修复后成立）；旧 LF blob 值仅作缺陷披露。
- 未改写任何历史证据字节；`correction_006` 为纯追加，旧 `gallery_index.json` / `data_manifest.json` / `SHA256SUMS.txt` 字节未动。
