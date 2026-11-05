# S1 v4d 裁定：analysis 包结构兼容修复与 S0-5 确证冻结包

- 文档状态：AUTHORITATIVE（Lead 裁定，2026-11-06）
- 适用范围：Issue #7 D-P4-003 S1 阶段；替代 R-V4-08 中与 S0-4 包编号相关的条款（其余条款继续有效）
- 依据：A2 task-254 readiness v4c 报告（S1_formal_readiness.md sha256 9bd0e2a5…）在 S0-4 包上发现 analysis 侧两个硬阻塞，A2 判 NOT_READY

## 1. 根因

A2-V4C-B01/B02（analysis 侧，非包缺陷）：`research/concorde_metaopt/meta_learning/s1_analysis.py` 的打包校验仍按旧布局写死：

- `FROZEN_REQUIRED_FILES`/`FROZEN_PAYLOAD_FILES` 只有 8/6 个载荷，digest_manifest 遇到 `determinism_report.json` 即报“未知产物”；
- schema-3 校验的顶层字段白名单不含 `confirmatory_eligible`；
- `_verify_freeze_summary_v4` 的 artifacts 集合写死为 6 个载荷，而 R-V4-08-05 要求 S0-4 及之后的包带 7 个载荷（6 + `determinism_report.json`）。

S0-4 包本身（A1 task-252）与 R-V4-08-05 一致：9 payload、digest_manifest/freeze_summary.artifacts 7 项、SHA256SUMS 9 行、`confirmatory_eligible=true`（frozen_family/preregistration/freeze_summary 三处）、orchestration 含 determinism_report_sha256/canonical_sha256/status。

## 2. 裁定 R-V4-09-01：analysis 必须同时支持两种 schema-3 包布局（fail-closed）

A6 在 `s1_analysis.py` 实现“布局判定 + 严格校验”：

- **确证布局（confirmatory）**：`freeze_summary.artifacts` 含 `determinism_report.json`（7 项），包内载荷 9 个（8 + determinism_report.json），SHA256SUMS 恰 9 条；`freeze_summary.confirmatory_eligible` 必须存在且为 true，且 frozen_family/preregistration 的 confirmatory_eligible 亦为 true；orchestration 的 determinism_report_sha256/determinism_report_canonical_sha256 必须与文件 raw/去 sha256 字段后的 canonical 重算一致，`determinism_report_status` 必须为 `PASS`。
- **legacy 布局**：无 determinism_report.json（8 载荷/6 artifacts，如 S0-3），`confirmatory_eligible` 缺失或 false；仅允许 exploratory（`--allow-legacy`），formal 必须拒绝。
- 任何“混合”/残缺布局（例如 SHA256SUMS 有 determinism 但 artifacts 没有，或反之；confirmatory_eligible 缺失但 artifacts 7 项）一律 fail-closed，禁止默认值/宽容。
- 旧布局若被 formal 调用必须抛 `S1_ANALYSIS_LEGACY_PACKAGE`；S0-4（确证布局但 code_sha 已过期）必须走既有的 `S1_ANALYSIS_CODE_SHA_DRIFT` fail-closed。
- 新增负控测试：确证布局正例；legacy 正例（exploratory 通过、formal 拒绝）；混合布局拒绝；artifacts 缺 determinism 拒绝；SHA256SUMS 缺/多一行拒绝；confirmatory_eligible 缺失/False 拒绝；determinism hash 篡改/status != PASS 拒绝。

## 3. 裁定 R-V4-09-02：由于 package_code_sha 覆盖 meta_learning/*.py，必须重新生成确证冻结包 S0-5

`family_v3.package_code_sha()` 对 `meta_learning/*.py` 全部文件取 sha；A6 修复 `s1_analysis.py` 会改变该 digest，S0-4 的 code_sha 9c2a6ade…（commit C 3c1f635）因此不再匹配最终代码。裁定：

- A6 修复 → Lead commit **E**（analysis 修复 + tests；docs 可同 commit）→ 独立全量测试通过；
- A1 在 **E 的干净 detached worktree** 生成新确证冻结包，run_id **`p4ra-s0-5-freeze-<UTC>Z`**，两独立进程 + determinism，code_sha = 该 worktree `package_code_sha()`；任务族/五 split/计数/holdout_seed 20261106/family_fingerprint a1f9462c…/split_hash cd597d01…/radius 0.64 必须与 S0-4 完全一致；prereg 的 `holdout_package.run_id/package_path` 指向 S0-5；旧 S0-4 包 SUPERSEDED_LEGACY（历史只读，不删除、不改写其提交）；
- Lead 将 S0-5 的 9 payload + README + SHA256SUMS 入库为 commit **F**；
- A2 以 E + S0-5 重跑 readiness（prepare/bench/冻结完整性/analysis smoke），A3 审计 E/F，A5 phase4 终审（覆盖 E/F/S0-5/readiness/merge delta）；A5 APPROVE_FOR_S1_RUN + Lead 书面授权后，才可启动 15 分片 21,000 runs。

## 4. R-V4-09-03：边界不变

- physical_call_count=0；不合并 main；不新开 PR；仅 Lead 写 GitHub；旧 M2/M5/M6/S0-2/S0-3/S0-4 只读。
- 正式 run 仍按 R-V4-07 的 15 分片（3 meta_seed × 5 opt_seed 对，每片 1,400，合计 21,000）与 R-V4-08 的 Holm/C5/代码绑定/legacy 拒绝条款执行。
- 文档同步：合同/执行计划/统计计划/矩阵中 S0-4 的确证包引用改为 S0-5（A4 执行，A5 复核）；R-V4-08-05 中“S0-4”字样按本裁定解释为“最终代码提交上的 S0 序列确证包（实际编号 S0-5）”。
## 5. R-V4-09-01a：布局判定口径补充（A6 实现确认）

- 布局判定以**封存证据**为准：`determinism_report.json` 必须同时出现在 SHA256SUMS、digest_manifest.artifacts、freeze_summary.artifacts 与 orchestration 的 `determinism_report_sha256`/`determinism_report_canonical_sha256`/`determinism_report_status=PASS` 中，且 `freeze_summary.confirmatory_eligible is True`，才是 confirmatory 布局；封存证据全不出现才是 legacy 布局。
- 历史 legacy 包（S0-2/S0-3）目录内遗留的未封存 `determinism_report.json` 不参与布局判定、按 legacy 忽略，并由 aggregate.freeze_echo 披露；但这不改变 formal 拒绝 legacy 包的规则。
- 任何混合证据（部分封存）一律 fail-closed；确证布局中封存 artifacts 集合必须恰为 7 项，SHA256SUMS 必须恰为 9 条（多/少均拒绝）。
