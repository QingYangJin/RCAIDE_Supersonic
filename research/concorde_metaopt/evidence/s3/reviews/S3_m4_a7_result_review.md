# S3-M4 独立结果复核报告（task-268）

- 复核人：a7-code-reviewer（独立只读复核，未参与执行）
- 复核时间：2026-11-09 22:44 +08:00（UTC 14:44）
- 仓库：`<REPO_ROOT>`，HEAD `691f554012b8fe50d4aca3559cb1ccc1ba717276`，branch `research/p4-route-a-s3`
- run：`<STATE_ROOT>/s3_runs/p4ra-s3-formal-20261109T1310Z`（17 文件 / 312,310,937 B）
- 授权：`<STATE_ROOT>/p4-route-a/lead/s3/S3_M3_AUTHORIZATION.json`（4,736 B，sha256 `5e0d8f1d12a0fee07b9ad6c5e1ff5dce94ffaefa0ab9f70f2a0b2514dd6cde60`）
- 约束执行情况：0 仓库写、0 run 目录写、0 campaign 重跑、0 物理/求解器调用、0 GitHub 写。全部探针与输出写在 `EXT/p4-route-a/a7/s3_m4/`。

## 0. 结论

| 维度 | 结论 |
|---|---|
| 数据完整性 / 可用于分析 | **PASS** |
| **总 verdict** | **APPROVE_FOR_S3_ANALYSIS** |
| `validation_ok=false` 归因 | **校验器路径缺陷（假阴性），非数据缺陷** |
| 数据可用于分析 | **是** |
| blocker / major / minor / info | **0 / 3 / 2 / 3** |

**关键裁决：validation_ok=false 属校验器缺陷，数据可用于分析。**

本 verdict 的裁定范围是 **run 产物数据本身是否可信、能否作为 S3 分析输入**。它不解除工具链修复义务：F-01（validator 模型路径）、F-02（模型聚合 sha 的契约冲突）、F-03（OOD 流未接入 fig7）是 3 个 major，必须在产出最终分析结论前修复；修复不得改动 run 产物。F-05/F-06/F-08 须在分析报告中如实披露。

## 1. 复核方法

只读手段：

1. 直接读取 run 目录 17 个文件，逐文件计算 sha256、字节数、行数，与 `data_manifest.artifact_sha256`、`run_summary`、campaign 日志交叉核对。
2. 用仓库外 launcher `.../lead/s3/launch_s3_formal.py`（500 B，sha256 `9b66b007e2d8a964369c508ad8e7cc4a010ac9c7fb2eee156f79fa1ad1514fd6`）调用 `s3_runner.main(["validate", ...])` 复跑 4 种参数组合；输出写入本目录。
3. 独立复算绑定：`sp.compute_code_sha(REPO)`、prereg canonical digest、`sp.canonical_sha256(prereg["models"])`、data_manifest 的 14 个 artifact sha、6 个模型文件实际 sha/bytes。
4. 独立复算确定性：三份 det 记录流逐字节比较；按 `sp.canonical_sha256(core_list)` 重算 core sha；用 `sp.determinism_subset_run_keys(prereg["family"])` 重建 60 个 run_key 并重算 subset sha。
5. 独立重算计数：按 5 条记录流分别统计行数、唯一 `run_key` 数、budget 分布、phase/split 纯度、`evaluation_index` 连续性与 `record_digest` 自洽性。
6. 静态定位失败检查的实现：`s3_runner.validate_run_artifacts` 的 `model_manifest_models` 分支；`s3_analysis` 的 `_validate_model_sha_binding`、`build_ood_rows`、plan-digest 校验分支。

所有证据文件见 §6；关键数值见附录 A/B/C。

## 2. 逐项核验

### 2.1 预算、网格与计数 — PASS

| 段 | 实测 runs | 实测 evals | 预期（计划 §4.2 / 授权） |
|---|---:|---:|---:|
| 主统计 `run_records.jsonl` | 3,000 | 288,000 | 3,000 / 288,000 |
| 负控制 `negative_control_records.jsonl` | 300 | 28,800 | 300 / 28,800 |
| OOD `ood_records.jsonl` | 300 | 28,800 | 300 / 28,800 |
| 确定性 `determinism/r1..r3` | 180 | 17,280 | 180 / 17,280 |
| **合计** | **3,780** | **362,880** | **3,780 / 362,880** |

- 主网格 3,000 = 20 task × 5 臂 × 2 budget × 3 meta_seed × 5 opt_seed；evals 96,000（B=64）+ 192,000（B=128）。
- 确定性每轮 5,760 evals（1,920 B64 + 3,840 B128），3 轮 17,280；det 三文件各 5,760 行、各 60 个唯一 run_key。
- 逐流 phase/split 纯：主 `meta_test/EVAL`、OOD `meta_test_ood/OOD`、负控 `meta_test_negative_control/NEGATIVE_CONTROL`；`evaluation_index` 连续，`record_digest` 逐条重算全部自洽，`bad_records_per_run=0`。
- `run_summary.per_run` 3,000 条，`sum(n_records)=288,000`，全部 `OK`；`status_counts={eval:{OK:362880,FAILED:0},train:{OK:0,FAILED:0}}`，`failures=[]`。
- `data_manifest.split_task_ids`：meta_train 60 / meta_validation 20 / meta_test 20 / meta_test_ood 10 / meta_test_negative_control 10 / dev 0，120 个 task 全局无重复、无交集；`synthetic_call_count=362,880`。
- `execution_report`：`run_count_requested=run_count_completed=3000`（仅主 campaign），`per_shard_counts=[368,395,369,357,374,397,372,368]` 和 = 3,000，`shard_runs_sha256=d8844aa514f9c308d21a2c8c7b78fdcd0eae66603fc0a7af08814d369207c7f7`；`stop_reason=null`。
- 说明：`run_count_requested/completed=3000` 与总 runs 3,780 不矛盾——前者只记主 campaign，OOD/NC/det 在 `budgets` 与 `record_counts` 中另记，且与 3,780 求和一致。

### 2.2 资源限额与停止规则 — PASS

| 指标 | 实测 | 上限 | 结论 |
|---|---:|---:|---|
| campaign_wall_s | 2,941.921272 | 7,200 | PASS（余量 59.1%） |
| sum_run_wall_seconds | 22,759.797742 | 28,000 | PASS（余量 18.7%） |
| max_run_wall_s | 13.290802 | 60 | PASS |
| max_peak_memory_mb | 313.34375 | 8,192 | PASS |
| physical_call_count | 0 | 0 | PASS |
| solver_processes_started | 0 | 0 | PASS |
| stop_reason | null | — | PASS |

`run_summary.resources.resource_limits={peak_memory_mb:8192, per_run_wall_s:60, total_wall_s:7200, sum_run_wall_limit_s:28000}`，与 M3 授权 `budgets` 一致；`parallel_workers=8`。campaign 未被资源限制中止，`status=COMPLETED`；进程退出码 1 仅由 `validation_ok=false` 引起（见 2.4），不是 RESOURCE_LIMIT。

### 2.3 确定性 — PASS

- 三份 det 记录流 `determinism/r1|r2|r3/run_records.jsonl` 各 4,436,840 B、各 5,760 行，**逐字节完全相同**，sha256 均为 `fba07081f39a40b6d7f98022b0c54d62cc12a06ef9c69a125d0913b6bc3ce618`。
- 去掉机器相关字段（`wall_s`、`peak_memory_mb`、`record_digest`）后逐 run canonical 数组重算 core sha，三份均为 `645e9f9c471269be37a8d219a88a1d9154824ba5458f1dbfbfc80b423315d4d8`，与 `determinism_check.record_core_sha256` 的三值一致。
- 由 `sp.determinism_subset_run_keys(prereg["family"])` 重建 60 个 run_key：与 det r1 提取集合完全相等（only_sel=0 / only_det=0）；按 prereg 顺序重排后 `sp.determinism_run_keys_sha256` = `0704a23ead63533f3659148b1167c6a81063089724e0015f3b9b1c43ec78ae5c`，与 `determinism_check.subset_run_keys_sha256`、`prereg.determinism.subset_run_keys_sha256` 三方一致。
- 方法说明：该 sha 对**有序** run_key 列表计算；按字典序重排会得到 `5d3cbc94…`，属排序口径差异，不是数据不一致。`record_digest` 自校验在三份文件中全部通过。

### 2.4 `validation_ok=false` 归因 — 校验器路径缺陷（数据 PASS）

复跑 4 种参数组合（均 exit 1；stdout 见 `validate_rerun.log` 与 `validate_*.out.json`）：

| # | 参数 | failed_checks | 说明 |
|---|---|---|---|
| a | `--repo-root <REPO_ROOT>` | `model_manifest_models` | 唯一失败检查 |
| b | 不带 `--repo-root` | `model_manifest_models` | 与 a 相同 |
| c | 不带 `--prereg` | `formal_gate_prereg_binding`, `model_manifest_models` | 少输入导致的预期附加失败 |
| d | `--repo-root .../evidence/s3`（基址探针） | `formal_gate_matches_repo` | **`model_manifest_models` 通过**；剩余失败是错置 repo root 的预期副作用 |

- run 目录 `models/` 只有 3 个 episode bank（`episode_bank_meta_0/1/2.jsonl`），**没有 6 个权重 json**。这是设计：计划 §4.3 line 327 规定模型 manifest 固定于 `evidence/s3/models/`，FORMAL run 只复制 manifest + verification，不复制权重。
- 6 个模型的实际文件位于 `<REPO_ROOT>/research/concorde_metaopt/evidence/s3/models/`；6/6 实际 sha256 == run `model_manifest` == M2 冻结 manifest == prereg，字节数也 6/6 等于 prereg 冻结值（见附录 A）。
- 失败点定位：`s3_runner.py:2527-2531` 只尝试 `root/rel_path`（run 目录）与 `Path(repo_root)/rel_path`，**缺少 `sp.S3_EVIDENCE_ROOT_RELPATH` 前缀**（`s3_prereg.py:641` = `research/concorde_metaopt/evidence/s3`）；两处都不存在时 `_raw_sha` 返回 None，与 manifest sha 比较必失败。
- 探针 (d) 是决定性反证：把解析基址换成 evidence root 后，唯一模型检查通过，只剩一个因“把 evidence/s3 当 repo root”而必然失败的 `formal_gate_matches_repo`。
- 结论：`validation_ok=false` **不是 run 数据错误**，而是 validator 对模型文件基址的解析缺陷（假阴性）。修复 F-01 后重跑 `validate`（只读，不触碰 run 目录）即可得到 `ok=true`，无需重跑 campaign。

### 2.5 哈希绑定与产物完整性 — PASS

| 绑定 | 实算/比对结果 | 结论 |
|---|---|---|
| `code_sha` | `75f7bfce4e313f8792b6e971358d2ca315dcf08f607602640e8b3fbbd350f920` = run_config = prereg = `sp.compute_code_sha(REPO)` | PASS |
| `prereg_digest` | `b31044c7614cced440d70ccdd8d12f6ee39e349fe3edf899708c03507fbd1ce8` = prereg 文件 raw sha | PASS |
| `prereg_id` | `p4ra-s3-prereg-b31044c7614cced4`（id 由 digest 派生） | PASS |
| `analysis_plan_digest` | `31ac71d730cfc58a1ff669488ca431dcb930cc8f6861418504e11ffc5f799c05` = run_config = prereg | PASS |
| family package | `70075498…` / 202,120 B = run_config = prereg | PASS |
| `task_ids_sha256` | `6695346afba7fac008b562d4112db8a0421b4c14cf5a3e9b2f9875dc418c886f` = run_config = prereg | PASS |
| `references_sealed_sha256` | `b8575a3e31ce01a62e09ddcc49735f37f8d1d1234805ac7250f2d0411a6d392c` = run_config = run data_manifest = prereg | PASS |
| FD gate | `651593e930807721ddb4a5795d5a6d7c4cee5827d38c581a9b242d417c8cb1cd` / 9,768 B，run_config = prereg = run_summary；status PASS，max_rel fomaml 4.318417995663093e-07、anil 2.5145570109047648e-08，negative_control PASS | PASS |
| run model_manifest | `f91e6109b02a7a9f24a859826aeb2b8a961ea30de35264bfe5261321a5f651d6` / 3,478 B；`verification.loaded_from_prereg=true`，`prereg_models_sha256=c128f987…` = `sp.canonical_sha256(prereg["models"])` | PASS |
| episode banks | 3 × 1,600 行，sha `64f0be64…` / `26c2c201…` / `e3e55f49…`，均 = run_config = run_summary = prereg | PASS |
| data_manifest.artifact_sha256 | 覆盖 14 个文件，14/14 实际 sha 一致，mismatch=0；未覆盖仅 data_manifest.json / run_config.json / run_summary.json（自指或自产） | PASS |
| run_summary.data_manifest_sha256 | `f7119bde…` = data_manifest.json raw sha | PASS |
| campaign 授权 | `campaign_authorization_id=R-S3-M3-CAMPAIGN-20261109T1310Z`、`utc=2026-11-09T13:10:00+00:00`，run_config 与 data_manifest 同值 | PASS |

补充：`run_config` 27 个必需字段齐全（计划 §4.3 line 317），`record_counts={train:0,eval:362880,total:362880}`；`data_manifest` 13 字段齐全，`data_boundary` 明确 holdout 只读标志与 phase 策略，`physical_call_count=0`。

### 2.6 异常披露 — PASS（不影响数据有效性，但须在分析报告披露）

1. **`execution_report.created_utc` 陈旧**：值为 `2026-11-09T14:07:08+00:00`（主 campaign 完成时刻），而 campaign 日志 `END_UTC=2026-11-09T14:17:54Z`、`run_summary.created_utc=14:17:46Z`。`s3_runner.py:3085-3115` 的 `build_final_execution_report` 用 `dict(main_report)` 只覆盖 wall/peak/stop 等指标，未更新 `created_utc`；属账目时间戳，非数据缺陷（F-05）。
2. **campaign 日志混合编码**：`.../p4ra-s3-formal-20261109T1310Z.log` 3,536 B，sha256 `d4cb89f8151d513b9ff42b93425779ffb588e19145e6f8fd2099efd75e08b6df`；首字节 `FF FE`（UTF-16LE BOM）后为 UTF-16LE JSON 主体，尾部 `EXIT=1`、`END_UTC=...` 为 ASCII 追加。内容完整可恢复，但普通 UTF-8 解析器会误读（F-06）。
3. **入口无 `if __name__ == "__main__"`**：`s3_runner.py` 中 0 命中；`python -m research.concorde_metaopt.meta_learning.s3_runner` 会静默 no-op。本次执行使用外部 launcher（500 B，sha `9b66b007…`），已在 `S3_M3_EXECUTION_RECORD.json`（sha `67cd2c4f…`）披露；对 run 产物无影响（F-07）。
4. **负控 9/10 组被 runner 自身标记 suspicious**：`_negative_control_summary`（`s3_runner.py:3572`）以 `feasible_rate > 0.50` 为启发式；除 `S3-DE B64`（0.448958）外，其余 9 组均 >0.50（最高 `S3-BO-FOMAML-CON B128` 0.851302）。这是诊断性披露，不是数据完整性失败；但分析报告必须呈现该阈值、9/10 的分布及“负控未显示预期可行率塌缩”的解释，不得隐藏（F-08）。

## 3. Findings

### F-01 · major · validator · 模型文件解析缺 evidence-root 前缀，造成 `validation_ok=false` 假阴性

- 位置：`<REPO_ROOT>/research/concorde_metaopt/meta_learning/s3_runner.py:2527-2531`（`validate_run_artifacts` 的 `model_manifest_models` 分支）。
- 证据：
  - run `models/` 仅 3 个 episode bank，无 6 个权重 json；权重按计划 §4.3 line 327 固定于 `evidence/s3/models/`，run 只复制 manifest。
  - 4 种 validate 组合均失败于 `model_manifest_models`；当 `--repo-root` 指向 evidence root 时该检查通过（只剩错置 root 导致的 `formal_gate_matches_repo`）。
  - 6/6 模型实际 sha256/bytes 与 run manifest、M2 冻结 manifest、prereg 完全一致（附录 A）。
  - 失败代码：`rel_path=str(row.get("path")); path=root/rel_path; if not path.is_file() and repo_root is not None: path=Path(repo_root)/rel_path`——未尝试 `repo_root / sp.S3_EVIDENCE_ROOT_RELPATH / rel_path`。
- 影响：`validate` 返回 `ok=false`、进程 exit 1；但不影响数据内容。任何下游若把 `validation_ok` 当作数据门槛会误判。
- 建议：在 fallback 中加入 evidence-root 解析（优先 run 目录，其次 evidence root，最后才裸 repo root），并新增“run 目录只有 bank、权重在 evidence root”的回归测试；修复后只读重跑 `validate` 记录 `ok=true`，不要改 run 目录。

### F-02 · major · analysis 契约 · `run_config.models.<arm>.sha256` 与 `prereg.models.<arm>.sha256` 比较不同规范化对象，FORMAL 分析被 fail-closed

- 位置：`<REPO_ROOT>/research/concorde_metaopt/meta_learning/s3_analysis.py:2240-2248`（`_validate_model_sha_binding`）；生成侧 `s3_runner.py:1654`（`_model_block_summary` 的 `sp.canonical_sha256(rows)`）与 `s3_prereg.py:2282`（`normalize_models` 的 `canonical_sha256(entries)`）。
- 证据：
  - fomaml：run 聚合 `e90a05c5234e82f0e9052c6726811264aa8043299746f3c13d30ba965a306336`，prereg 聚合 `731a699872b0e8d0d42d3833abb5705bc894b1c092fdc92fe86591f368294a8d`；anil：`9b421cce…` vs `3dfe78a3…`。
  - 差异纯属规范化：run 行无 `bytes`、路径为 `models/<kind>_meta_<seed>.json`、无 `kind`/`config_note`；prereg 行含 `bytes`、仓库相对路径。把 prereg 行去掉 `bytes`、路径归一化后，两臂聚合 sha 分别精确等于 `e90a05c5…`/`9b421cce…`；6 个逐模型 sha 全部相同。
  - 实际分析日志 `.../s3_analysis/p4ra-s3-formal-20261109T1310Z.log`（4,220 B，sha `23acc630219e4b8146b7dd847a60de26ae375a22ca843beeb779d8713b831c2a`，UTF-16LE，mtime 14:30:28Z）记录 `S3_ANALYSIS_RUN_BINDING_MISMATCH`：`FORMAL run_config.models.fomaml.sha256 必须等于预注册模型 sha`。
  - 计划 §4.3 line 317 只列 `models` 字段，未定义该聚合 sha 语义；line 320 又称 `run_summary.models` 为 prereg 冻结条目；分析侧按“等于 prereg 聚合 sha”解释——三处措辞未单源化，属契约歧义/实现过严，不是数据损坏。
- 影响：官方分析器在 FORMAL 下拒绝该 run；数据本身完好（6/6 逐模型一致）。修复前无法用原始分析器产出最终结果。
- 建议（二选一，优先前者，均不需重跑 campaign）：
  1. 分析器改为**逐模型**比对（6 个 sha 集合相等）或比对 `model_manifest.verification.prereg_models_sha256`；同时在计划/schema 明确 `run_config.models.<arm>.sha256` 是“本 run 归一化清单摘要”，不是 prereg 聚合。
  2. 若契约确实要求携带 prereg 聚合，则 runner 改为写入 prereg 聚合 sha（需重跑才能更新 run 产物——代价高，且不解决语义混淆）。
- 修复或采用经审计的等价归一化补丁后，必须重跑分析；不得修改 run 产物。

### F-03 · major · analysis · OOD 记录流未被分析器消费，fig7 被判 NOT_RUN

- 位置：`s3_analysis.py:3961-3968`/`4038`（`per_run` 只来自主 `run_records.jsonl`）、`4065-4123`（`compute_run_endpoints` 只遍历 `run.per_run`）、`4933-4934`/`4956`（`aux_endpoints` 由主端点按 split 过滤）、`4601-4606`（`build_ood_rows` 无 OOD 端点即 NOT_RUN）。
- 证据：run 目录 `ood_records.jsonl` 22,430,606 B、28,800 行、300 run、sha `e8372903…` 真实存在；`_scan_aux_streams` 已校验其 split/phase/count/sha（`record_streams PASS: NC=28800 OOD=28800 DET=17280`），但只用于计数与来源记录，未解析成端点；Lead 侧补丁日志的 `figure_status` 显示 `fig7_ood_diagnostics=NOT_RUN`，原因“run 产物不含 OOD 段”。
- 影响：计划 §5.3 line 384 要求的 OOD 描述性对比（fig7）缺失；不影响 C1/C2 主推断（计划 line 295 明确 OOD 不进推断），但属计划内分析交付缺口。
- 建议：从 `ood_records.jsonl` 构建 OOD 端点（复用 `_aggregate_eval_records`/端点聚合但独立流），接入 `build_ood_rows`；新增单测：存在 OOD 流时 fig7 必须 RENDERED，且 OOD 行数 = arms×budgets。

### F-04 · minor · analysis · `--verify-analysis-plan-digest` 用被增补的 sections 重算 digest，必然不等

- 位置：`s3_analysis.py:1738-1752`（`load_s3_prereg` 的 verify 分支）与 `s3_analysis.py:1343-1344`（`_validate_endpoints_section` 返回值增补 `c1_tests/c2_tests/comparator`）。
- 证据：用校验后的 sections 重算得 `d5b2ac24f8f614f2b641466b3d7f92e77f23d3e9090996f7f29cc08a0ad04ec1` ≠ 声明值 `31ac71d7…`；改用 prereg 原始 `endpoints/statistics/figures` + `compute_analysis_code_sha(REPO)=45ab8962…` 重算精确等于声明值。
- 影响：仅显式开关 `--verify-analysis-plan-digest` 时失败；默认 CLI 路径不带该开关（`s3_analysis.py:5119`），不影响常规分析，但会误导审计者。
- 建议：verify 重算使用 prereg 原始 sections，或让 `_validate_endpoints_section` 不改写输入；补单测覆盖“验证通过且 digest 相等”。

### F-05 · minor · 记账 · 最终 `execution_report.created_utc` 未更新

- 位置：`s3_runner.py:3085-3115`。
- 证据：`execution_report.created_utc=2026-11-09T14:07:08+00:00`，campaign `END_UTC=2026-11-09T14:17:54Z`，`run_summary.created_utc=14:17:46Z`。
- 影响：最终报告时间早于实际完成约 10m46s，属账目陈旧；不影响记录/计数/哈希。
- 建议：`build_final_execution_report` 显式写当前 UTC，或重命名该字段为 `main_campaign_completed_utc` 并附带 `finalized_utc`。

### F-06 · info · 产物编码 · campaign 日志混合 UTF-16LE/ASCII

- 位置：`.../s3_runs/p4ra-s3-formal-20261109T1310Z.log`。
- 证据：3,536 B，sha `d4cb89f8…`；`FF FE` + UTF-16LE JSON 主体 + ASCII 尾部 `EXIT=1`/`END_UTC`；内容可完整恢复。analysis 日志同样为 UTF-16LE。
- 影响：机器解析需容忍两种编码；不影响证据内容。
- 建议：日志统一 UTF-8（无 BOM），或在 harness 记录中声明编码。

### F-07 · info · 打包 · `s3_runner.py` 无 `__main__` 入口

- 位置：`<REPO_ROOT>/research/concorde_metaopt/meta_learning/s3_runner.py`（全文无 `if __name__ == "__main__"`）。
- 证据：直接 `python -m ...s3_runner` 会静默 no-op；本次用外部 launcher（500 B `9b66b007…`），执行记录已披露。
- 影响：可重复性依赖外部文件；对既有 run 产物无影响。
- 建议：加入标准入口或把 launcher 纳入仓库并加 smoke test。

### F-08 · info · 负控诊断 · 9/10 组被自身启发式标记 suspicious

- 位置：`s3_runner.py:3558-3580`，尤其 `:3572` 的 `feasible_rate > 0.50`。
- 证据：`negative_control_summary.json`（1,680 B，sha `1a17774d…`）10 组中 9 组 >0.50（0.609896–0.851302）；唯一非 suspicious 为 `S3-DE B64=0.448958`。
- 影响：属负控诊断信号（标签置换后可行率未如预期塌缩），不是数据完整性失败；但必须在分析报告中披露并解释，不能用它反向推断主结果。
- 建议：分析报告列出阈值、9/10 分布及解释；若计划对负控有更强判据，需在后续版本单源定义。

## 4. Verdict

```
verdict                 = APPROVE_FOR_S3_ANALYSIS
data_integrity          = PASS
validation_ok_false     = VALIDATOR_PATH_DEFECT (F-01), NOT a data defect
statement               = validation_ok=false 属校验器缺陷，数据可用于分析
blocker / major / minor / info = 0 / 3 / 2 / 3
```

支持 APPROVE 的核心证据：

1. 3,780 runs / 362,880 evals 与授权、计划、data_manifest、5 条记录流**五方一致**；主网格 3,000/288,000 的 budget 分布、phase/split、index、digest 全部自洽。
2. 全部资源限额 PASS，`physical_call_count=0`、solver=0、无 RESOURCE_LIMIT、无 FAILED 记录。
3. 确定性三份记录流字节级相同，core sha 与 subset sha 独立复算一致。
4. 哈希绑定（code/prereg/plan/family/task_ids/references/FD gate/model manifest/banks/data_manifest）全部独立复算 PASS。
5. `validation_ok=false` 被 4 组 validate 复跑与 evidence-root 反证定位为 `s3_runner.py:2527-2531` 的基址缺陷；6/6 模型实际文件与 manifest/prereg 完全一致。
6. 异常项（时间戳、编码、入口、负控）均已披露且不影响数据内容。

Approval 的边界条件（不满足则不得发布最终分析结论）：

- **必须**先修复 F-01 并只读重跑 `validate` 得到 `ok=true`（不改 run 目录）；把新的 validate 输出归档。
- **必须**先修复 F-02、F-03（或使用经独立审计的等价补丁）；分析输出必须覆盖 OOD/fig7，且模型绑定以逐模型 sha 为准。
- **必须**在分析报告中披露 F-05 时间戳、F-06 编码、F-08 负控 9/10 suspicious。
- **禁止**以“validation 已通过”表述当前 run；应写“validation 因 validator 基址缺陷报 false，已独立复算 6/6 模型一致，修复后重验”。
- 本复核**不**授权修改 run 产物或重跑 campaign；若需重跑，另立任务。

## 5. 复现命令

```powershell
# 1) validate 复跑（4 组；只读，输出到 EXT；PowerShell 重定向会产生 UTF-16LE）
& <PYTHON_EXE> -E -s -B "<STATE_ROOT>/p4-route-a/lead/s3/launch_s3_formal.py" validate `
  --run-dir "<STATE_ROOT>/s3_runs/p4ra-s3-formal-20261109T1310Z" `
  --prereg "<REPO_ROOT>/research/concorde_metaopt/evidence/s3/s3_preregistration.json" `
  --repo-root "<REPO_ROOT>"

# 2) 独立复算探针（均在 OUT 下，只读 run/repo）
<PYTHON_EXE> -E -s -B <OUT>/probe2_artifacts.py   # 17 文件 sha/行数、data_manifest 比对
<PYTHON_EXE> -E -s -B <OUT>/probe3_verify.py      # 计数/确定性/绑定/模型基址
<PYTHON_EXE> -E -s -B <OUT>/probe9_model_summary_semantics.py
<PYTHON_EXE> -E -s -B <OUT>/probe10_summary_binding.py
<PYTHON_EXE> -E -s -B <OUT>/probe11_run_config_fields.py
<PYTHON_EXE> -E -s -B <OUT>/probe12_model_aggregate_and_summary.py
```

`<OUT>` = `<STATE_ROOT>/EXT/p4-route-a/a7/s3_m4`。

## 6. 证据文件清单（本目录）

- `review.md` — 本报告
- `findings.json` — 机器可读 findings（F-01..F-08）
- `verdict.json` — 机器可读 verdict 与边界条件
- `validate_rerun.log` — 4 组 validate 结果 + 解释
- `validate_with_repo_root.out.json`、`validate_no_repo_root.out.json`、`validate_no_prereg.out.json`、`validate_repo_root_evidence.out.json`
- `independent_recompute.log` — 计数/绑定/确定性复算记录
- `model_sha_table.md` / `model_sha_table.json` — 6 模型 sha/bytes 四方对照
- `bindings.json` — 关键哈希绑定表
- `probe1_meta.py` … `probe12_model_aggregate_and_summary.py` + 结果 JSON
- `commands.log` — 执行命令
- `SHA256SUMS.txt` — 上述产物校验和

## 附录 A · 6 模型 sha256/bytes 四方对照

| model (manifest path) | bytes | actual = run manifest = M2 frozen = prereg sha256 |
|---|---:|---|
| `models/fomaml_meta_0.json` | 107,426 | `520d6ba465f80c910df6add0707a600b8e948cc2c01b9bd58a994b2a3945c6c6` |
| `models/fomaml_meta_1.json` | 107,429 | `346ad98742e9a9eab06b9f999a93612055317f471cd8c562dd4cb0f190722478` |
| `models/fomaml_meta_2.json` | 107,363 | `8ecd4623043dd20dc15ae7ecc1510157cbfbbfde777a1c70c33d68fd1a7da183` |
| `models/anil_meta_0.json` | 107,370 | `37201fcf2462d317906721f2716a741ada3a19e1e79f9991bf1ef309031eba29` |
| `models/anil_meta_1.json` | 107,387 | `604b0e54b00805819805306e79dce24b20806ec0a6843af371e30f59c773aae1` |
| `models/anil_meta_2.json` | 107,378 | `8a2bb85e92ff2b1eea66331cebe17a2140e8db418e32f66eb6cba2ac0c278055` |

解析基址：`run_dir/<path>` 与 `repo_root/<path>` 均不存在；仅 `repo_root/research/concorde_metaopt/evidence/s3/<path>` 命中（`S3_MODEL_ENTRY_FIELDS` 无 bytes，bytes 取 prereg 冻结值并实测一致）。

## 附录 B · run 目录 17 文件 sha256/字节/行数

| 文件 | bytes | sha256 | 行数 |
|---|---:|---|---:|
| data_manifest.json | 7,018 | `f7119bde48df5238b5b1563d03023a0902ab6042aa885961f86604e0c2bbc47c` | — |
| determinism/r1/run_records.jsonl | 4,436,840 | `fba07081f39a40b6d7f98022b0c54d62cc12a06ef9c69a125d0913b6bc3ce618` | 5,760 |
| determinism/r2/run_records.jsonl | 4,436,840 | 同上 | 5,760 |
| determinism/r3/run_records.jsonl | 4,436,840 | 同上 | 5,760 |
| determinism_check.json | 829 | `1c9f0ea57e7610daf3293d0ba71469f6a8de20e8ac08a1332774855039c2f539` | — |
| execution_report.json | 1,142 | `e70a5a5a10d5e8127d92f6a7519e9c5cb37fce5d510d04e6a08b0589306bfb91` | — |
| fd_or_gradient_gate.json | 9,768 | `651593e930807721ddb4a5795d5a6d7c4cee5827d38c581a9b242d417c8cb1cd` | — |
| model_manifest.json | 3,478 | `f91e6109b02a7a9f24a859826aeb2b8a961ea30de35264bfe5261321a5f651d6` | — |
| models/episode_bank_meta_0.jsonl | 1,104,518 | `64f0be6432007c1fc317f1b52263aa81e6c2f387ae78d73b9c608c47d44cf3f5` | 1,600 |
| models/episode_bank_meta_1.jsonl | 1,104,561 | `26c2c2013aa1e39f286dda943f53d82f7ce6eee27cbed44d89088fb2bba589b1` | 1,600 |
| models/episode_bank_meta_2.jsonl | 1,104,561 | `e3e55f491f6ecc93d52aa7e062f8088bb724aec93b49dfdae6c3f477f1260629` | 1,600 |
| negative_control_records.jsonl | 23,153,628 | `117b46cbde79be6952723e52786c85cb8aec15f6587398fbe37f6f93b9d539a6` | 28,800 |
| negative_control_summary.json | 1,680 | `1a17774d5fa310c86f909b0063aaa8a1e58d3cb9ec37cf581ed9952e96d7d038` | — |
| ood_records.jsonl | 22,430,606 | `e8372903b82e5a2730bdc3b557d5d367d3ebe5d90b5d1d1d204be4415f2539ba` | 28,800 |
| run_config.json | 11,273 | `0a4ec865610a471de0b90001a3f8b37e8e560700b96734f1f670100c24134a0c` | — |
| run_records.jsonl | 221,974,782 | `f6e0d02ad7603605406858f216337b762324809ebee154842eba108ae7128ddf` | 288,000 |
| run_summary.json | 28,092,573 | `f5225e1e61d7c5944336b521b0f10d950b969669de808aef924b8953a0b876d2` | — |

## 附录 C · 关键记账值

- campaign_wall_s = 2,941.921272；sum_run_wall_seconds = 22,759.797742；max_run_wall_s = 13.290802；max_peak_memory_mb = 313.34375。
- determinism: 3 × 4,436,840 B，sha `fba07081…`，core `645e9f9c…`，subset `0704a23e…`。
- FD gate max_rel：fomaml 4.318417995663093e-07，anil 2.5145570109047648e-08；negative_control PASS。
- run_summary：status COMPLETED，run_mode FORMAL，evidence_scope DEVELOPMENT_VALIDATION_ONLY，failures []，physical_call_count 0。
- data_manifest：synthetic_call_count 362,880；split_task_ids 120 个唯一 task（60/20/20/10/10/0）；artifact_sha256 覆盖 14/14。
