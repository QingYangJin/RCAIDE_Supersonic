# S3 正式运行证据包（p4ra-s3-formal-20261109T1310Z）

本目录是 Issue #7（D-P4-003 路线 A 分阶段改进）S3 阶段的正式运行证据包：冲突族 F-QE-conflict-v1 上的约束感知初始化 / ANIL 消融对照，**全部为合成解析任务，无任何物理求解**（`physical_call_count=0`，`solver_processes_started=0`）。

- 运行对象：`run_id=p4ra-s3-formal-20261109T1310Z`，`run_mode=FORMAL`。
- 证据边界：本包只覆盖 S3 正式运行与其分析；不构成任何物理验证、不构成阶段验收、不解除 S4 前置条件。
- 权威记录：`S3_M3_AUTHORIZATION.json`（授权，sha256 `5e0d8f1d12a0fee07b9ad6c5e1ff5dce94ffaefa0ab9f70f2a0b2514dd6cde60`）、`S3_M2R_FROZEN.json`（冻结记录，sha256 `6abce6fcab7634d80ae23cff15ceb780881f25e79251187e32fd9486b59b2c77`）、`S3_M4_ANALYSIS_RECORD.json`（分析记录）。三者位于仓库外权威状态根 `<STATE_ROOT>/p4-route-a/lead/s3/`，不在本包内。

## 1. 绑定（预先注册与代码）

| 项 | 值 |
| --- | --- |
| 预注册 ID | `p4ra-s3-prereg-b31044c7614cced4` |
| 预注册摘要 digest | `b31044c7614cced440d70ccdd8d12f6ee39e349fe3edf899708c03507fbd1ce8` |
| 预注册文件 | `s3_preregistration.json`，34,308 B，sha256 `192dd36a3bc1fefcb6debf0fc2e73cea0df4d28af499691de17e9e9b0bd3d42b` |
| code_sha（运行代码） | `75f7bfce4e313f8792b6e971358d2ca315dcf08f607602640e8b3fbbd350f920` |
| analysis_code_sha（分析代码） | `45ab8962e7aa1bf471b704e0ce73ad5c3102966b92110de4dad649f86b05053a`（预注册顶层 `analysis_code_sha` 为 `null`，见 §7.7；该值记录于冻结记录） |
| analysis_plan_digest（计划 v1.3e） | `31ac71d730cfc58a1ff669488ca431dcb930cc8f6861418504e11ffc5f799c05` |
| 执行计划 | `docs/planning/p4_route_a_s3_execution_plan_20261107.md` v1.3e，110,311 B，sha256 `543aab5a0581a3b44b3f4c43bfd5fcffec17c266b7715145aa01ff9e062a4fd5` |
| 族包 | `family_package/p4ra_fqec_v1_family_package.json`，202,120 B，sha256 `70075498062e03dba7e2d258d3b4f7700f5a7b8a48ffbd37bef72f390deca23e` |
| 封存参考解 | `references_sealed/p4ra_fqec_v1_references_sealed.json`，78,955 B，sha256 `b8575a3e31ce01a62e09ddcc49735f37f8d1d1234805ac7250f2d0411a6d392c`，n=110 |
| 校准 | `calibration/family_calibration_20261109T120826Z.json`，2,283 B，sha256 `8895eb4882b2f7cae2f87565be361a0bab09458d3285ffe420a93779547cc01d`，`selected_delta1_base=0.2` |
| FD/梯度门 | `gate/fd_or_gradient_gate.json`，9,768 B，sha256 `651593e930807721ddb4a5795d5a6d7c4cee5827d38c581a9b242d417c8cb1cd` |
| W8 试点门 | `gate/w8_pilot_gate.json`，17,233 B，sha256 `f6ad0de9989045cbad783968262e7160da308e79e3362e985c33cc7600b8a4cf` |
| 模型清单（冻结） | `models/model_manifest.json`，3,223 B，sha256 `6a0a5033c577d8d199294c49f737135e652b816f5e323b23796878c686220450` |
| 哈希向量 | `hash_vectors.json`，12,472 B，sha256 `bde487fb6ed49768ca76e328a31c0efab77d2bd39d41c0ac99def4bb8e876203` |
| campaign 授权 ID | `R-S3-M3-CAMPAIGN-20261109T1310Z`（UT 2026-11-09T13:10:00+00:00，截止 2026-11-09T21:10:00Z） |

族：F-QE-conflict-v1，120 任务，split 计数 60/20/20/10/10（meta_train/meta_validation/meta_test/meta_test_ood/meta_test_negative_control）。3 个 episode bank（`models/episode_bank_meta_{0,1,2}.jsonl`，1,104,518 / 1,104,561 / 1,104,561 B，各 1,600 episodes）。6 个模型（FOMAML ×3 seeds、ANIL ×3 seeds）。

## 2. 授权与预算对照（实际 vs 上限）

| 项 | 授权上限 | 实际 | 结论 |
| --- | --- | --- | --- |
| 总 runs | 3,780 | 3,780 | 精确用尽 |
| 总 evals | 362,880 | 362,880 | 精确用尽 |
| workers | 8 | 8 | 一致 |
| campaign 墙钟 | ≤ 7,200 s | 2,941.921272 s | 通过 |
| Σ run 墙钟 | ≤ 28,000 s | 22,759.797742 s | 通过 |
| 单 run 墙钟 | ≤ 60 s | 13.290802 s（最大） | 通过 |
| 峰值内存 | < 8,192 MB | 313.34375 MB（最大） | 通过 |
| 物理调用 | 0 | 0 | 通过 |
| 求解器启动 | 0 | 0 | 通过 |

run 组成（与授权逐项一致）：主 campaign 3,000 runs / 288,000 evals；OOD 300 runs / 28,800 evals；负控 300 runs / 28,800 evals；确定性 180 runs / 17,280 evals。

## 3. 执行事实

- 启动 2026-11-09T13:28:38Z，campaign END 2026-11-09T14:17:54Z，墙钟 2,941.921272 s（约 49.0 min）。`stop_reason=null`，`failures=[]`，状态 `COMPLETED`。
- 分片计数 `per_shard_counts=[368,395,369,357,374,397,372,368]`，合计 3,000；`shard_runs_sha256=d8844aa514f9c308d21a2c8c7b78fdcd0eae66603fc0a7af08814d369207c7f7`。
- 记录流：`main` 3,000 runs / 288,000 条；`ood` 300 / 28,800；`nc` 300 / 28,800；`det` 180 / 17,280。全部 `status_counts.OK`，无 FAILED。
- 确定性：3 次重跑 60-run 子集，`record_core_equal=true`，三次 `record_core_sha256` 同为 `645e9f9c471269be37a8d219a88a1d9154824ba5458f1dbfbfc80b423315d4d8`；`subset_run_keys_sha256=0704a23ead63533f3659148b1167c6a81063089724e0015f3b9b1c43ec78ae5c`；r1/r2/r3 `run_records.jsonl` 逐字节相同（4,436,840 B，sha256 `fba07081f39a40b6d7f98022b0c54d62cc12a06ef9c69a125d0913b6bc3ce618`）。
- FD/梯度门：32 坐标 × 2 臂全部 PASS，`max_rel=4.318417995663093e-07`（阈值 1e-6），产物 sha256 与 `gate/fd_or_gradient_gate.json` 一致（`651593e9…`）。
- **`validation_ok=false` → 进程 exit code = 1**：59 项校验中 58 项 PASS，唯一失败为 `model_manifest_models`。根因是校验器路径回退缺陷（`meta_learning/s3_runner.py:2527-2531` 未拼 `S3_EVIDENCE_ROOT_RELPATH` 前缀）；把 `--repo-root` 指向本目录时该检查通过。6/6 模型 sha256 与 bytes 在 run manifest、M2 冻结清单、预注册三处一致。详见 §7.1。
- 执行人替换：原定执行人 A2/A6 连续失败且未启动任何 run，最终由 Lead 执行；因 `s3_runner.py` 缺 `if __name__ == "__main__"` 守卫，入口改用仓库外 launcher（500 B，sha256 `9b66b007e2d8a964369c508ad8e7cc4a010ac9c7fb2eee156f79fa1ad1514fd6`，内容为 `sys.path.insert` + `from ...s3_runner import main`），**未修改仓库代码**（否则 code_sha 变化需重新冻结）。详见 §7.2。

## 4. 分析产物

- 核心表（与冻结分析器逐字节一致）：`analysis/s3_endpoint_tables.csv`（15,384 B）、`s3_holm_family.csv`（544 B）、`s3_negative_controls.csv`（1,612 B）、`s3_null_disclosure.csv`（12,179 B）、`s3_cost_table.csv`（984 B）、`s3_ood_descriptives.csv`（588 B）、`s3_per_task_endpoint_values.csv`（36,153 B）。
- 聚合：`analysis/aggregate.json`。
- 图：6 张已渲染（fig3 可行命中率 / fig4 best&first feasible / fig5 成本 / fig6 族诊断 / fig8 负控 / fig9 确定性与预算），各带 `*_data.csv`；4 张 `NOT_RUN`（fig1 训练损失与全元梯度、fig2 K-shot 曲线、fig7 OOD 诊断、fig10 VSPAERO 门禁），理由见 `analysis/figure_status.json`，未伪造数据。
- 披露侧车：`analysis/analysis_disclosures.json`（Lead 撰写，5,390 B）。**不修改任何冻结产物字节**，逐项更正/披露 A5 复核提出的 blocker 与 major（§6.2）。
- OOD 补充描述性件（非冻结分析器产出）：`analysis/ood_supplementary_descriptives.csv`（100 行 = 10 task × 2 budget × 5 arm）、`analysis/ood_supplementary_summary.json`（label=`LEAD_AUXILIARY_NOT_FROM_FROZEN_ANALYZER`，`inference=NONE_DESCRIPTIVE_ONLY`）、复算脚本 `analysis/repro/ood_supplementary.py`。
- 复现材料：`analysis/repro/run_s3_analysis_leadpatched.py`、`analysis/repro/leadpatch_audit.json`、`analysis/repro/analysis_source_run.log`、`analysis/repro/leadpatched.log`。

## 5. 统计结论（与冻结分析器一致，独立复算复核）

- 总判定：`overall_decision = NO_EVIDENCE`。
- C1（约束感知初始化 vs 目标导向初始化，端点 `feasible_hit_rate`，family `s3-feasible-hit-2tests`，Holm 族大小 2）：
  - B64 / C1b：效应 `0.009635416666666664`，95% CI `[-0.0014583333333333284, 0.02151041666666666]`，`n_eff=19`（20 task 中 1 个零差），Wilcoxon `p_raw=0.1785125732421875`，Holm `p_holm=0.357025146484375`，置换 p `0.17798220177982202`，Pratt p `0.192474365234375` → `NULL`。
  - B128 / C1a：效应 `0.0033593749999999978`，95% CI `[-0.0033339843750000205, 0.010234374999999967]`，`n_eff=20`，`p_raw=p_holm=0.43577003479003906`，置换 p `0.43625637436256376` → `NULL`。
- C2（相对封存参考解的 gap，端点 `gap_to_reference`，family `s3-gap-to-ref-2tests`）：
  - B64 / C2b：效应 `-0.011233867`，CI `[-0.0143845, +0.0069722]`，`n_eff=20`，`p_raw=0.84082221984863281`，`p_holm=1.0` → `NULL`。
  - B128 / C2a：效应 `+0.002654621`，CI `[-0.0017179, +0.0027918]`，`n_eff=19`，`p_raw=0.79825210571289062`，`p_holm=1.0` → `NULL`。
- ANIL 消融：`ANIL_INCONCLUSIVE`（命中率未显示优势，且成本比不可用，见 §6.2 与 §7.4）。
- 负控：NC-01…NC-13 为 PASS；**NC-14 与 NC-15 为 `DISCLOSED` 而非 PASS**（冻结分析器未计算，见 §6.2 A5-S3M5-02）。
- 成本端点：**`NOT_AVAILABLE`**（逐 run 墙钟未计时，见 §6.2 A5-S3M5-03）。
- 描述性（非推断）：OOD 10 task 的 `feasible_hit_rate_mean`，B64：RANDOM 0.7869791666666667、FOMAML-OBJ 0.79375、FOMAML-CON 0.7848958333333333、ANIL 0.7828125、DE 0.4213541666666667；B128：RANDOM 0.8229166666666666、OBJ 0.8268229166666667、CON 0.8151041666666666、ANIL 0.8221354166666667、DE 0.6052083333333333。

## 6. 复核链

### 6.1 A7 独立结果复核（run 数据完整性）

- 结论：`APPROVE_FOR_S3_ANALYSIS`，`data_integrity=PASS`，`validation_ok_false_attribution=VALIDATOR_PATH_DEFECT`；0 blocker / 3 major / 2 minor / 3 info。附件：`reviews/S3_m4_a7_result_review.md`、`S3_m4_a7_findings.json`、`S3_m4_a7_verdict.json`、`S3_m4_a7_model_sha_table.md`。
- A7 只裁定 run 数据可信，不解除任何修复义务、不修改 run、不重跑 campaign。
- major：F-01（模型清单校验缺 evidence-root 前缀 → `validation_ok=false` 假阴性）、F-02（run_config 与 prereg 的 model sha 聚合规范化口径不同，去掉 bytes 并归一化路径后精确相等）、F-03（OOD 28,800 条记录未接入 fig7）。minor/info：F-04 plan-digest 复算过严、F-05 `created_utc` 陈旧、F-06 campaign 日志 UTF-16LE、F-07 无 `__main__`、F-08 负控 9/10 被 runner 标 suspicious。

### 6.2 A5 独立结果复核（分析产物 + 补丁正当性 + 结论复现）

- 结论：`CHANGES_REQUESTED`（1 blocker / 2 major / 3 minor），`artifact_receipt_allowed=false`；同时确认 `confirmatory_result_reproduced=true`：主结论 NO_EVIDENCE 与 C1/C2 的 p 值/效应/CI/n_eff 独立重算完全一致，7 个核心 CSV 逐字节相同，22 项产物 bytes/sha256 22/22 一致。附件：`reviews/S3_m5_a5_*.md|json|csv`。
- **A5-S3M5-01（blocker，OOD 伪 NOT_RUN）**：run 侧 `ood_records.jsonl` 存在（22,430,606 B，sha256 `e8372903b82e5a2730bdc3b557d5d367d3ebe5d90b5d1d1d204be4415f2539ba`，28,800 行 / 300 runs / 10 tasks），而 fig7 与 `s3_ood_descriptives.csv` 的理由写“run 产物不含 OOD 段”。根因 `meta_learning/s3_analysis.py:4601-4606` 只从主 `run_records` 端点找 OOD，从不读独立 OOD 记录流。**处置**：不修改冻结产物；在 `analysis_disclosures.json` 中更正理由（正确理由为“冻结分析器未接入独立 OOD 记录流”），并交付 §4 的 OOD 补充描述性件。
- **A5-S3M5-02（major，NC-15 未计算）**：`negative_control_summary.json` 缺预注册要求字段，`s3_analysis.py:4573-4587` 直接标 `DISCLOSED`。**处置**：侧车标 `DISCLOSED_NOT_COMPUTED`，并给出独立描述性结果：NC 10 task 的 CON−OBJ 为 B64 `+0.016145833333333325`、B128 `+0.009895833333333316`；主 20 task 真实值 `+0.009635416666666664` / `+0.0033593749999999978`；绝对比 1.6757 / 2.9457，合并 2.0040。但 NC task 与主 task 交集为 0、预注册未定义跨 task 集比较规则，故**该比值仅为描述性，不构成预注册判定**；不得把 NC-15 报告为通过。
- **A5-S3M5-03（major，成本表全 0）**：`s3_runner.py:1035` 每条记录 `wall_s=0.0`（未逐点计时已在该文件与 `run_config.scope_notes` 披露），`s3_analysis.py:4115-4116` 据此定义 `total_cost` → 恒 0，ANIL `cost_ratio=1.0` 实为预算比而非运行成本比。**处置**：侧车标 `NOT_AVAILABLE_LABELLED`，附可用 run 级墙钟；`s3_cost_table.csv` 与 fig5 不得用于成本效率论证。
- minors：A5-S3M5-04（官方只对 `analysis_plan_digest` 做格式校验、未复算）、A5-S3M5-05（Lead 补丁仅 FORMAL 生效、模型 bytes/额外字段未绑定、补丁审计未记录校验开关）、A5-S3M5-06（`aggregate.prereg.endpoints` 含注入键 `comparator/c1_tests/c2_tests`）。
- Lead 两处分析侧补丁（在仓库外 launcher 内实现，**未改冻结代码**）已由 A5 反向验证：模型 sha 四向校验 14 个篡改场景全部 fail-closed（`tamper_run_per_model_sha`/`tamper_run_aggregate`/`tamper_prereg_per_model_sha`/`tamper_prereg_aggregate`/`run_extra_field_aggregate_recomputed` 等）；`record_digest` 排除字段篡改亦 fail-closed。补丁审计见 `analysis/repro/leadpatch_audit.json`。

### 6.3 后续复核（第二轮提交）

处置后的 delta 复核（A7）与发布前隔离审计（A3）结论与报告随后续提交加入 `reviews/`，并在 `PACKAGE_MANIFEST.json` 重新登记。

## 7. 已知缺陷与限制（逐项披露，不隐瞒）

1. **`validation_ok=false` / exit code 1**：唯一失败检查 `model_manifest_models` 为校验器路径缺陷，非数据问题（A7 F-01 已用 `--repo-root` 指向本目录复验通过）。本包不以“validation 已通过”表述。
2. **代码入口缺陷**：`meta_learning/s3_runner.py` 缺 `if __name__ == "__main__"`，`python -m ... run` 为静默空操作；本次用仓库外 launcher（sha256 `9b66b007…`）执行，未改仓库代码。
3. **三处冻结分析器缺陷**（A5 复核确认，均以侧车披露、未改代码）：OOD 记录流未接入（§6.2-01）、NC-15 未计算（-02）、逐 run 成本未计时（-03）。
4. **成本端点不可用**：见 -03；ANIL 的成本效率结论不成立。
5. **图 6/10**：fig1/fig2 因记录流不含训练损失与 K-shot 曲线而 NOT_RUN；fig7 因分析器未接入 OOD 流而 NOT_RUN（数据存在）；fig10 因无只读 VSPAERO 门禁归档而 NOT_RUN。
6. **代理误差与真实泛化未测**：S3 全部为合成解析任务，未涉及真实飞机/真实航空元训练/真实求解器（Issue #7 明确禁止）。
7. **预注册顶层 `analysis_code_sha=null`**（A3 W01）；分析代码 sha 记录于冻结记录。
8. **`execution_report.created_utc=14:07:08Z` 早于 campaign END 14:17:54Z**（A7 F-05）：以 campaign END / `run_summary.created_utc` 为准。
9. **A7-F-08**：负控 10 组中 9 组被 runner 标 `suspicious`（唯一例外 S3-DE B64 = 0.448958），已在 A7 报告中披露，不解释为通过。
10. **`aggregate.prereg.endpoints` 注入键**（A5-S3M5-06）污染 provenance 但未改变已复算的 C1/C2 数值。
11. **本包不是阶段验收**：`APPROVED_FOR_NEXT_STAGE` / S3 阶段放行均未签发；S4 仍为 `NOT_APPROVED`。

## 8. 外部化大产物（不入 git，按 sha256 + bytes 校验）

以下 7 个文件位于仓库外权威目录 `<STATE_ROOT>/p4-route-a/s3_runs/p4ra-s3-formal-20261109T1310Z/`，本包只记录摘要（等同 `run/data_manifest.json` 与 `run/run_artifacts_manifest.json`）：

| 路径 | bytes | sha256 |
| --- | --- | --- |
| `run_records.jsonl` | 221,974,782 | `f6e0d02ad7603605406858f216337b762324809ebee154842eba108ae7128ddf` |
| `run_summary.json` | 28,092,573 | `f5225e1e61d7c5944336b521b0f10d950b969669de808aef924b8953a0b876d2` |
| `negative_control_records.jsonl` | 23,153,628 | `117b46cbde79be6952723e52786c85cb8aec15f6587398fbe37f6f93b9d539a6` |
| `ood_records.jsonl` | 22,430,606 | `e8372903b82e5a2730bdc3b557d5d367d3ebe5d90b5d1d1d204be4415f2539ba` |
| `determinism/r1/run_records.jsonl` | 4,436,840 | `fba07081f39a40b6d7f98022b0c54d62cc12a06ef9c69a125d0913b6bc3ce618` |
| `determinism/r2/run_records.jsonl` | 4,436,840 | 同 r1（逐字节相同） |
| `determinism/r3/run_records.jsonl` | 4,436,840 | 同 r1（逐字节相同） |

run 产物合计 17 件 / 312,310,937 B；存储分层 committed 7（35,188 B，见 `run/`）、dedup_committed 3（episode bank，与 `models/` 下 3 个文件逐字节相同，不重复提交）、externalized 7（上表）。`data_manifest.json`（7,018 B）的 `artifact_sha256` 记录 14 条（含 3 个 episode bank 条目，不含 run_summary），其自哈希 `f7119bde48df5238b5b1563d03023a0902ab6042aa885961f86604e0c2bbc47c`。

## 9. 脱敏、编码归一与换行符

- **脱敏**：本包内 25 个文本文件把绝对主机路径替换为占位符 `<STATE_ROOT>` / `<STATE_ROOT>/s3_runs/` / `<STATE_ROOT>/s3_analysis/` / `<STATE_ROOT>/p4-route-a/` / `<REPO_ROOT>` / `<REPO_PARENT>` / `<PYTHON_EXE>`（同时处理 Unix `/`、Windows 反斜杠与 JSON 转义双反斜杠三种形式；逐文件原 sha256 / 新 sha256 / 替换次数见 `PACKAGE_MANIFEST.json` 的 `sanitization` 段）。构成：(a) 8 个分析/清单文件：`analysis/aggregate.json`、`analysis/figure_generation_summary.json`、`analysis/figure_status.json`、`analysis/ood_supplementary_summary.json`、`analysis/repro/leadpatch_audit.json`、`analysis/repro/ood_supplementary.py`、`analysis/repro/run_s3_analysis_leadpatched.py`、`run/run_artifacts_manifest.json`；(b) 12 个复核文件 `reviews/S3_m4_a7_*`、`reviews/S3_m5_a5_*`（A7/A5 原报告中的 run/analysis/EXT 目录绝对路径同样替换为占位符，结论与数值未改）；(c) 4 个控制台日志 `analysis/repro/analysis_source_run.log`、`analysis/repro/leadpatched.log`、`bench/bench_v13a_console_run2.log`、`bench/bench_v13a_console_v2.log`（同时做编码归一）；(d) 本 `README.md`（Python 解释器路径；其登记 origin 为占位符替换前版本 19,063 B / sha256 `03f62b2938d5778531b1a13bccc9f0ad582857683c6662c09171cf9d013897ca`，此后 §9 又按包组装需要扩写，故 sanitized 值以当前文件为准）。脱敏不改变任何数值、哈希或统计结论。
- **溯源深度披露**：25 个脱敏文件中 21 个可定位到未脱敏 origin 并逐字节等价（A7 复核）；其余 4 个（`README.md`、`reviews/S3_m5_a5_result_review.md`、`reviews/S3_m5_a5_verdict.json`、`run/run_artifacts_manifest.json`）的 origin 已在原位被脱敏或经扩写，只能依据 `PACKAGE_MANIFEST.json` 的 `sanitization` 段与结论数值不变来核对，属审计深度限制而非缺陷。
- 脱敏来源记录 `sanitization_record.json`（逐文件 original/sanitized sha256、bytes、替换次数、编码备注）位于仓库外权威状态根 `<STATE_ROOT>/p4-route-a/lead/s3/`，不在本包内；重放时以 `PACKAGE_MANIFEST.json` 的 `sanitization` 段为准。
- **编码与换行符**：4 个原 UTF-16LE（含 BOM、CRLF）控制台日志已归一为 UTF-8（无 BOM）+ LF，并在 `sanitization` 段登记 `encoding_note` 与原 sha256/bytes。Windows `core.autocrlf` 下工作树为 CRLF、提交 blob 为 canonical LF；包内当前 CRLF 待提交文本文件 19 个（`PACKAGE_MANIFEST.json` 的 `eol_summary` 逐条列出）。`SHA256SUMS.txt` 一律采用 canonical-LF 哈希；`PACKAGE_MANIFEST.json` 同时登记 raw 与 LF 两种哈希。

## 10. 复现方法

```
# 1) 校验 run 数据（把 repo-root 指向本目录可避开已知校验器路径缺陷）
<PYTHON_EXE> <launcher.py> validate --prereg <evidence>/s3_preregistration.json \
  --run-dir <STATE_ROOT>/p4-route-a/s3_runs/p4ra-s3-formal-20261109T1310Z --repo-root <evidence>
# 2) 复跑确认性统计（不重新生成图）
<PYTHON_EXE> <repo>/research/concorde_metaopt/meta_learning/s3_analysis.py \
  --prereg <evidence>/s3_preregistration.json --run-dir <...> --out <out_dir> --no-generate-figures
```

`<launcher.py>` 为仓库外 500 B 入口（sha256 `9b66b007e2d8a964369c508ad8e7cc4a010ac9c7fb2eee156f79fa1ad1514fd6`）；分析复跑需显式开启 `--verify-code-sha` / `--verify-record-digests` / `--verify-analysis-plan-digest`（官方默认只对 plan digest 做格式校验）。

## 11. 文件分类

- 预注册/哈希向量：`s3_preregistration.json`、`hash_vectors.json`
- 冻结输入：`family_package/`、`references_sealed/`、`calibration/`、`models/`（6 模型 + 3 banks + 清单）、`gate/`
- run 摘要：`run/`（8 个小文件；大记录流外置）
- 分析：`analysis/`（7 核心 CSV、aggregate、6 PNG + 6 data CSV、figure_status、披露侧车、OOD 补充件、repro/）
- 复核：`reviews/`（A7 s3_m4 六件、A5 s3_m5 十一件）
- 包元数据：`PACKAGE_MANIFEST.json`、`SHA256SUMS.txt`、本 `README.md`
