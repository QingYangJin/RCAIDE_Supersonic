# P4 路线A S1 v4c（phase3 整改）Lead 裁定 R-V4-08

- 日期：2026-11-06（Asia/Shanghai）
- 依据：A5 `S1_phase3_review.md`（verdict CHANGES_REQUESTED；2 blocker / 2 major / 6 minor；sha256 a0ed7a43…）；A5 S1 rev2；合同 v1.3（§7/§7.2/FC-14）；统计计划。
- 边界：仅离线合成、physical_call_count=0；不合并 main；不新开 PR；旧 S0-2/S0-3 包只读；新物理求解仍须 Issue #4 owner 书面批准。
- 本裁定取代此前与之冲突的统计族/预注册口径；R-V4-01..07 其余条款继续有效。

## R-V4-08-01 唯一 Holm 族定义（关闭 S1R3-B02）

- 族键 = `(primary_endpoint, budget_B, K)`。
- 族成员 = 该族键下全部可推断臂对比较 C1–C4（以 `s1_analysis.INFERENCE_COMPARISON_IDS` 为唯一来源，当前 4 个）。
- C5（FOMAML-KSHOT vs FOMAML-ZERO）永不进入 Holm 族，也不做 benefit/harm 推断。
- pair-level `STRUCTURALLY_IDENTICAL` 行按行排除；排除后族实际大小可 <4，必须动态记录，禁止写死 4。
- 必须同步：合同 §7.2、统计计划多重校正行、`s1_analysis.collect_hypotheses` docstring/返回字段、冻结 prereg 的 `multiple_comparison` 与 `statistics.multiplicity` 文本。
- 回归测试：构造族大小 4→3（多排 1 行或减少比较），断言 Holm p_adj 重算且与手算一致；断言 C5 永不出现在 p_adj 行。

## R-V4-08-02 prereg 三键与 holdout_splits 强校验（关闭 S1R3-B01）

冻结 prereg 必须新增/修正：

```json
"holdout_splits": {"meta_test": 20, "meta_test_ood": 10},
"holdout_package": {
  "run_id": "p4ra-s0-4-freeze-<UTC>Z",
  "family_version": "p4ra-family-v4",
  "holdout_seed": 20261106,
  "split_counts": {"meta_test": 20, "meta_test_ood": 10},
  "task_count": 30,
  "frozen_family_sha256": "<frozen_family.sha256>",
  "package_path": "research/concorde_metaopt/optimization_runs/<run_id>"
},
"c5_policy": {
  "mode": "C5_B_STRUCTURAL_IDENTIFIABILITY",
  "overlap_threshold": 0.90,
  "c5_benefit_harm_inference": false,
  "c5_in_holm": false,
  "min_estimable_tasks": 10,
  "below_min_conclusion": "NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY"
},
"structural_identifiability": {
  "pair_overlap_threshold": 0.90,
  "pair_status_above_threshold": "STRUCTURALLY_IDENTICAL",
  "pair_status_below_threshold": "IDENTIFIABLE",
  "overlap_definition": "交集行数 / 较大集合行数",
  "exclude_from_benefit_harm_inference": true,
  "exclude_from_holm": true,
  "post_hoc_task_exclusion": false,
  "report_structural_exclusion_counts": true,
  "report_c5_estimable_task_count": true
}
```

- `holdout_splits` 为 object，键/值与 `split_counts` 的 meta_test/meta_test_ood 一致，和=30=holdout_task_count。
- verifier：三键必须存在、类型正确、常量字段精确匹配；holdout_package.task_count = 两 split 计数和 = 30；holdout_package.run_id 必须等于本包 run_id 且匹配 `^p4ra-s0-[0-9]+-freeze-[0-9]{8}T[0-9]{6}Z$`；package_path 必须为仓库相对路径且不含盘符/绝对路径；frozen_family_sha256 必须等于 frozen_family.sha256。
- s1_analysis formal 模式加载 prereg 后必须校验三键（阈值、c5_in_holm=false、min_estimable_tasks=10、holdout_package.run_id 与本包目录名一致）；缺失/漂移 fail-closed。

## R-V4-08-03 冻结包与执行代码绑定（关闭 S1R3-M01）

- 新冻结包必须在最终代码 commit（含本轮全部代码修复与 merge 实现）的干净 checkout 上生成；包内 code_sha 必须等于该 commit 的 `family_v3.package_code_sha()`。
- `s1_analysis` formal 模式启动时重算当前 `package_code_sha()`，与 `freeze_summary.code_sha` / `frozen.code_sha` 比较；不一致 fail-closed（错误码 S1_ANALYSIS_CODE_SHA_DRIFT）。exploratory 模式可 `--allow-code-delta` 但必须记录 warning。
- 任何在冻结包生成后修改 `research/concorde_metaopt/meta_learning/*.py` 的提交都使该包失效，必须重新生成包；文档/测试/run 产物提交不影响。
- 重跑 determinism_report 并纳入包完整性链（见 R-V4-08-05）。

## R-V4-08-04 formal 拒绝 legacy/v3 包（关闭 S1R3-M02）

- `s1_runner` formal grid/run 与 `s1_analysis` formal 模式：若包 family_version != `p4ra-family-v4` 或 `confirmatory_eligible != true`（legacy/旧 holdout），立即 raise；不得只记录后继续。
- exploratory/read-only 复现可用 `--allow-legacy` 显式放行，但输出必须标 `confirmatory_eligible=false` 且不得进入主统计。
- 负控测试：S0-2/v3 包 + formal → 失败；v4 包 + formal → 通过。

## R-V4-08-05 新冻结包 S0-4 与完整性链（关闭 S1R3-m02/m03）

- 新包 run_id：`p4ra-s0-4-freeze-<UTC>Z`（由 A1 在干净 detached worktree 用 `make_freeze.py` 生成两独立进程）。
- 不变量：任务族/五 split 内容/计数/holdout_seed=20261106/family_fingerprint/split_hash 与 S0-3 相同；radius_base=0.64；physical=0。变化仅：prereg_digest、freeze_summary 的 run_id/git_sha/code_sha/时间戳、frozen_family.calibration.note 文案（去掉 PENDING 残留）。
- `determinism_report.json` 必须进入 `digest_manifest` 与 `freeze_summary.artifacts`（或作为第 9 个 payload 登记）；SHA256SUMS 覆盖；两进程逐字节一致。
- 旧 S0-3 包保留只读，不得改写；由于缺三键，新 verifier 会拒绝其进入 formal。

## R-V4-08-06 阶段门（v4c）

1. A1 修 family_v3（R-V4-08-02/05）+ s1_runner（R-V4-08-04）+ merge（task-245）+ 测试。
2. A6 修 s1_analysis（R-V4-08-01/03/04 + 三键消费）+ 测试。
3. Lead 提交 commit C（代码+文档+merge+rifting），并独立复跑全量测试。
4. A1 在 C 的干净 detached worktree 生成 S0-4 两进程，Lead 入库 commit D。
5. A2 readiness v4c（S0-4 包，不读真实 holdout，重建/复用正式工件，20-run bench）。
6. A3 审计 C/D；A5 phase4 final gate（覆盖 B01/B02/M01/M02 + merge delta task-247）。
7. 仅当 A5 给 `APPROVE_FOR_S1_RUN` 且 Lead 书面授权，A2 才可启动 15 片并行 21,000 formal。
