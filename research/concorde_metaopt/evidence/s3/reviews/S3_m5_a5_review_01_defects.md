# S3-M5 步骤 1：三个分析器缺陷的独立静态复现

对象：run `p4ra-s3-formal-20261109T1310Z`；prereg `<REPO_ROOT>/research/concorde_metaopt/evidence/s3/s3_preregistration.json`（raw 34,308 B，sha256 `192dd36a3bc1fefcb6debf0fc2e73cea0df4d28af499691de17e9e9b0bd3d42b`，declared digest `b31044c7614cced440d70ccdd8d12f6ee39e349fe3edf899708c03507fbd1ce8`，declared analysis_plan_digest `31ac71d730cfc58a1ff669488ca431dcb930cc8f6861418504e11ffc5f799c05`）。以下均由 A5 只读脚本 `probe_p1p2p3.py` / `probe_p2p3.py` 实算，未改仓库、未跑物理。

## 缺陷 P1：endpoints 段校验器向被校验对象注入派生键，导致 analysis_plan_digest 复算必然不符

- 代码事实：`s3_analysis.py:1309` `_validate_endpoints_section()` 先取原始 C1/C2，随后在 `:1344` 返回 **新对象**：
  ```python
  return {"C1": c1, "C2": c2, "comparator": ..., "c1_tests": c1_tests, "c2_tests": c2_tests}
  ```
  即返回值比 prereg 原始 endpoints 段多出 `comparator`、`c1_tests`、`c2_tests` 三个顶层键。
- `s3_analysis.py:1696` 将该返回值赋给 `endpoints`，`:1740-1745` 用这个被注入的对象调用 `sp.analysis_plan_digest(endpoints=..., statistics=..., figures=..., analysis_code_sha=...)`；而 `s3_prereg.py:372-385` 对该 payload 做 canonical sha256。
- A5 实算（analysis_code_sha=`45ab8962e7aa1bf471b704e0ce73ad5c3102966b92110de4dad649f86b05053a`）：
  - 原始三段 sections 直接复算：`31ac71d730cfc58a1ff669488ca431dcb930cc8f6861418504e11ffc5f799c05`，与声明的 `31ac71d7…` **相等**。
  - 经 `_validate_endpoints_section()` 后的三段复算：`d5b2ac24f8f614f2b641466b3d7f92e77f23d3e9090996f7f29cc08a0ad04ec1`，与声明值 **不等**。
- 结论：`--verify-analysis-plan-digest` 在原始代码上必然失败，原因不是 prereg 内容错，而是校验器自身污染了被哈希对象。该缺陷可静态复现，证据见 `probe_p1p2p3.py` 输出。

## 缺陷 P2：模型聚合 sha 的 run/prereg 表示不同（bytes/path），原校验把“聚合不等”误判为“模型不等”

- 代码事实：`s3_runner.py:1635-1661` `_model_block_summary()` 为每个 kind 构造 rows 时只保留 `meta_seed/path/sha256/config/episode_bank_sha256/final_train_loss`（`:1640-1648`），**丢弃 `bytes`**，且 path 是 run 相对路径；随后 `:1654` 用 `sp.canonical_sha256(rows)` 生成 run_config.models.<kind>.sha256。
- prereg 的 `models.<kind>.models[]` 行还含 `bytes`（A5 实测 pre_row_keys 有 `bytes`，run_row_keys 无），因此两边聚合 sha 必然不同：fomaml run `e90a05c5234e82f0e9052c6726811264aa8043299746f3c13d30ba965a306336` vs prereg `731a699872b0e8d0d42d3833abb5705bc894b1c092fdc92fe86591f368294a8d`；anil run `9b421cce88db4d27bad876a0b019d1c7b4c9e43d20acc7dde27f807e5777d8ff` vs prereg `3dfe78a318ad1ea983b1ad573ddee3660bc2afaec1154bd1756c21d8856b5d52`。
- 但 A5 逐模型核对：fomaml 三 seed 的 sha 与 prereg 全等（seed0 `520d6ba4…`、seed1 `346ad987…`、seed2 `8ecd4623…`），anil 三 seed 全等（seed0 `37201fcf…`、seed1 `604b0e54…`、seed2 `8a2bb85e…`）；run 聚合等于 canonical(run rows)（两者均 true），prereg 聚合等于 canonical(prereg rows)（均 true）；把 prereg 行去掉 `bytes`、path 改为 `models/<kind>_meta_<seed>.json` 后重建的聚合分别等于 run 聚合（fomaml `e90a05c5…`、anil `9b421cce…`，均 true）。
- 代码事实：`s3_analysis.py:2221-2249` `_validate_model_sha_binding()` 在 FORMAL 下直接把 run_config 的**聚合** sha 与 prereg 的**聚合** sha 比较（`:2243`），不展开逐模型行，因此即使 6 个模型完全一致也会 fail-closed 误报。A5 实算 run 与 prereg 聚合均不等（两个 kind 的 legacy_equal=false）。

## 缺陷 P3：record_digest 排除字段口径不一致（分析器多纳入 wall_s/peak_memory_mb）

- 代码事实：runner 的 digest 口径在 `s3_runner.py:119-120`：
  `S3_TRAIN_RECORD_EXCLUDED_FIELDS = ("wall_s", "peak_memory_mb", "record_digest")`；
  `S3_EVAL_RECORD_EXCLUDED_FIELDS = ("wall_s", "peak_memory_mb", "record_digest")`；
  `s3_runner.py:428-437` `_record_core()/eval_record_digest()/train_record_digest()` 按此排除；写入处在 `:879`/`:1037`。
- 分析器 `s3_analysis.py:3608` 却调用 `sp.record_digest(dict(record))`；`s3_prereg.py:388-390` 的 `record_digest()` **只排除 `record_digest` 自身**，不排除 `wall_s`/`peak_memory_mb`。同文件 `:3536-3538` 的 `_record_core_digest()` 又正确排除了三字段，说明同一分析器内部存在两套口径。
- A5 实测首条 eval record（`run_records.jsonl` 第 1 行，task/arm 等字段齐全，`wall_s=0.0`、`peak_memory_mb=None`）：
  - 冻结 `record_digest`：`9fd5b7bf5e56fad05c36dea5f7904a8d9c59ae86e5a566c50aae1ccf4c7c0971`；
  - `sp.record_digest(record)`：`35edae4a2a80077403e1205bad9eca59fe36e4c7abe1810512b976b33ac914a1`，**不匹配**；
  - runner 口径（排除 wall_s/peak_memory_mb/record_digest）：`9fd5b7bf…`，**匹配**。
- 结论：`--verify-record-digests` 在原始代码上对合法记录必然失败；不是 run 被篡改，而是分析器用了错误排除集。

## 小结

三项均为可静态复现的 **分析器缺陷**，且均发生在“读入后校验/聚合”层，不涉及 runner 产物数值本身。P1 直接使 `--verify-analysis-plan-digest` 不可用；P2 使 FORMAL 模型绑定在逐模型完全一致时仍硬失败；P3 使 `--verify-record-digests` 对合法记录硬失败。三者共同解释了为何 Lead 需要旁路 launcher 才能完成正式 run 的分析。
