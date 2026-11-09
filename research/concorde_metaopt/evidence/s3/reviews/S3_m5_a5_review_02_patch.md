# S3-M5 独立复核（第 2 步）：Lead 分析补丁 fail-closed 审查

- 日期：2026-11-09（UTC）
- 审查者：A5（a5-code-reviewer，独立会话）
- 审查对象：
  - Lead 补丁 launcher：<STATE_ROOT>/p4-route-a/lead/s3/run_s3_analysis_leadpatched.py，6,990 B，sha256 a3aac137f5ca9f4343288d0beb34c1a33f3b35e387e64909ad6029afb863aba4
  - 补丁审计：<STATE_ROOT>/s3_analysis/p4ra-s3-formal-20261109T1310Z.leadpatch_audit.json，6,499 B，sha256 39ea855b5679c3d805bf0c48fa331287c0f0030e4339a850c5d1f847094ec90c
  - 被补丁代码：<REPO_ROOT>/research/concorde_metaopt/meta_learning/s3_analysis.py、s3_prereg.py、s3_runner.py（worktree HEAD 691f554，clean）
- 边界：只读；未修改任何输入、未重跑正式 run、未改仓库；负控在 EXT 内用副本/内存 fixture 完成，不接触正式产物。
- 方法：静态读补丁与审计 + 独立负控 probe_patch_negative.py（14 个场景） + 将 review_01 的三缺陷映射到补丁覆盖范围。

## 0. 命名映射

review_01 的三个分析器缺陷：
- P1：endpoints 段注入 comparator/c1_tests/c2_tests，导致 analysis_plan_digest 复算不符；
- P2：run/prereg 模型聚合 sha 的 bytes/path 表示差异，导致 FORMAL 误报；
- P3：record_digest 排除字段口径不一致。

Lead 补丁本次只处理 P2 与 P3：
- 补丁第 1 点 = 模型 SHA 四向绑定（对应 review_01 P2）；
- 补丁第 2 点 = record_digest 排除字段（对应 review_01 P3）；
- 补丁没有处理 P1，也没有传 --verify-analysis-plan-digest（见第 3 节）。

## 1. 补丁第 1 点：模型 SHA 四向绑定（对应 review_01 P2）

### 1.1 实现事实

run_s3_analysis_leadpatched.py:34 保存原函数 _ORIG = sa._validate_model_sha_binding；:57-95 用 _patched 替换。_patched 对每个模型仅当 run_mode == FORMAL 时执行（:68-69），四向校验为：

1. run_config 与 prereg 的 per-model (kind, meta_seed) -> sha256 集合相等（:70-74）；
2. run_config 的聚合 sha == canonical_sha256(run 模型行)（:75-77）；
3. prereg 的聚合 sha == canonical_sha256(prereg 模型行)（:78-80）；
4. 把行规范化为 run-relative path、去掉 bytes 后重建的聚合 == run 聚合（:81-83）。

### 1.2 独立负控结果

A5 在 EXT 内复制 run_config/prereg fixture，逐项篡改后调用补丁函数，结果如下：

| 场景 | 观察 | 判定 |
|---|---|---|
| baseline（未篡改） | 通过 | PASS（预期） |
| tamper_run_per_model_sha | 抛 S3AnalysisError（RUN_BINDING_MISMATCH） | FAIL_CLOSED（正确） |
| tamper_run_aggregate | 抛 S3AnalysisError | FAIL_CLOSED（正确） |
| tamper_prereg_per_model_sha | 抛 S3AnalysisError | FAIL_CLOSED（正确） |
| tamper_prereg_aggregate | 抛 S3AnalysisError | FAIL_CLOSED（正确） |
| run_extra_field_aggregate_recomputed | 抛 S3AnalysisError | FAIL_CLOSED（正确） |
| prereg_bytes_changed_aggregate_recomputed | 通过 | 覆盖缺口（bytes 未绑定） |
| prereg_extra_field_aggregate_recomputed | 通过 | 覆盖缺口（额外字段未绑定） |
| smoke_invalid_sha | 通过（FORMAL 检查被跳过） | SMOKE 弱化，非本次 FORMAL 结果门 |

对模型 SHA 的核心篡改（per-model sha、run 聚合、prereg 聚合、run 额外字段）均 fail-closed；未发现能改变模型身份但仍通过 FORMAL 的旁路。两处 PASS 是覆盖缺口而非放行路径：
- prereg 模型行中的 bytes 字段和某些额外字段在 canonical 化时被丢弃，因此篡改它们并重算聚合仍可通过；
- 该缺口是绑定范围不完整（bytes/额外字段未绑定），不是 per-model sha 被绕过；对正式结果的可复现性影响低，但若未来把 bytes 作为模型身份的一部分，应显式绑定。
- smoke_invalid_sha PASS 说明补丁只保护 FORMAL；SMOKE 结果不应用于结果门。本次对象是 FORMAL，故不构成 blocker，但应写入补丁限制。

### 1.3 审计文件

p4ra-s3-formal-20261109T1310Z.leadpatch_audit.json 的 lead_patch_audit.patched=true、per_model_equal=true，记录 fomaml/anil 的 run aggregate、prereg aggregate、normalized rebuild：
- fomaml run_aggregate=e90a05c5234e82f0e9052c6726811264aa8043299746f3c13d30ba965a306336；prereg_aggregate=731a699872b0e8d0d42d3833abb5705bc894b1c092fdc92fe86591f368294a8d；normalized=e90a05…；
- anil run_aggregate=9b421cce88db4d27bad876a0b019d1c7b4c9e43d20acc7dde27f807e5777d8ff；prereg_aggregate=3dfe78a318ad1ea983b1ad573ddee3660bc2afaec1154bd1756c21d8856b5d52；normalized=9b421c…。

审计文件只记录模型绑定检查，没有记录 verify_code_sha / verify_record_digests / 是否开启 --verify-analysis-plan-digest；因此补丁审计本身不能证明所有校验开关的取值，需用 launcher 与日志补证。

## 2. 补丁第 2 点：record_digest 排除字段（对应 review_01 P3）

### 2.1 实现事实

Lead 补丁 :98-106 对 sp.record_digest 做 monkey-patch，排除字段为 (wall_s, peak_memory_mb, record_digest)。这与 runner 写 digest 时的常量一致：s3_runner.py:119-120 的 S3_TRAIN_RECORD_EXCLUDED_FIELDS / S3_EVAL_RECORD_EXCLUDED_FIELDS 也是这三个字段。补丁作用域是 launcher 进程；不修改仓库文件。

### 2.2 独立负控结果

| 场景 | 观察 | 判定 |
|---|---|---|
| record_baseline | 通过 | PASS（预期） |
| record_wall_changed | 通过 | PASS（预期：wall_s 被排除） |
| record_peak_changed | 通过 | PASS（预期：peak_memory_mb 被排除） |
| record_substantive_changed | 抛 S3AnalysisError | FAIL_CLOSED（正确） |
| record_digest_missing | 抛 S3AnalysisError | FAIL_CLOSED（正确） |

没有发现通过修改 wall/peak 之外字段绕过 digest 校验的路径；实质性字段变更 fail-closed。由于 monkey-patch 是全局的，若 launcher 内其他代码误用 sp.record_digest，会统一采用 runner 口径；这与正式记录口径一致，但在补丁审计中未声明，属于可维护性风险，不是本次结果的阻断项。

## 3. 补丁未覆盖 P1（analysis_plan_digest）

- Lead launcher :109-130 的 CLI 没有 --verify-analysis-plan-digest 参数，main 只传 verify_code_sha 和 verify_record_digests；
- 官方 aggregate 的 checks 只有 analysis_plan_digest_format PASS: 格式校验通过（未复算），没有 digest 复算；
- 官方 S3_M4_ANALYSIS_RECORD.json 的 prereg.endpoints 仍含 comparator / c1_tests / c2_tests 三个注入键，正是 review_01 P1 的现场证据；
- A5 自己的 launcher 显式开启 verify_analysis_plan_digest=True，独立复跑通过；A5 静态实算原始三段 sections 的 digest 为 31ac71d730cfc58a1ff669488ca431dcb930cc8f6861418504e11ffc5f799c05，与 prereg 声明一致；注入后为 d5b2ac24f8f614f2b641466b3d7f92e77f23d3e9090996f7f29cc08a0ad04ec1，不相等。

结论：P1 的真实 digest 是正确的，但官方分析没有复算、补丁也没有修；这意味着官方产物的计划绑定只停留在格式校验，属于 provenance 缺口。对 C1/C2 的统计结论没有数值影响（A5 独立复跑已用原始 prereg 重算），但不能说官方补丁已经关闭 review_01 的三项缺陷。

## 4. 结论与定级

- 补丁第 1 点：核心模型 SHA 篡改 fail-closed，四向校验有效；无 blocker 级旁路。遗留 bytes/额外字段未绑定、仅 FORMAL 生效、审计未记录校验开关，属 minor。
- 补丁第 2 点：record_digest 与 runner 口径一致；wall/peak 容忍、实质字段 fail-closed，符合预期；无 blocker 级旁路。
- 补丁第 3 点（P1）：未覆盖；官方未复算 plan digest，A5 独立复跑可证原始 digest 正确。列为 minor（provenance），不是本次结果阻断项。
- 因此，补丁本身不构成拒绝结果的 blocking 理由；本任务最终 CHANGES_REQUESTED 的 blocker 来自 review_03 的 OOD 伪 NOT_RUN（A5-S3M5-01），不是补丁。

## 5. 建议（若需要重新发布分析）

1. 把模型行 bytes 与未知额外字段纳入 canonical 绑定，或在 prereg 中声明这些字段不参与身份；
2. 把 --verify-analysis-plan-digest 设为 FORMAL 默认开启，并在 aggregate 记录真实复算结果，而不只是格式校验；
3. 在补丁审计中记录 verify_code_sha / verify_record_digests / plan digest 三个开关及取值；
4. SMOKE 路径至少执行同一绑定函数（可对缺失 fixture 显式豁免），避免 FORMAL/SMOKE 校验分叉；
5. 修复 OOD 消费与 NC-15 计算（见 review_03），而不是仅修补丁。
