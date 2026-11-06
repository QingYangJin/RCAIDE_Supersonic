# S2 正式 run 结果独立复核（A5）

- 复核对象：run_id=`s2-formal-20261106T1810Z`
- run 根：`EXT/p4-route-a/a2/s2_formal/s2-formal-20261106T1810Z`
- 源提交：`994cda8e0942060072d65eb50dde790c44d32194`（source-repo，父 f4ab43f；执行 worktree source-repo-worktree，detached @994cda8）
- 复核日期：2026-11-07；复核人：a5-code-reviewer
- 边界：只读仓库与 run；0 solver、0 物理调用、0 仓库写、0 GitHub 写；未修改 analysis/merged/freeze。

## 0. 结论

**verdict = APPROVE_FOR_S2_RECEIPT**

- 0 blocker / 0 major / 1 minor（另有 1 项 info）。
- 独立重算与 A2 aggregate/CSV **逐项一致**；主结论 `SUPPORTED_HARM` 成立（FULL_MAML 在 meta_validation 上劣于 FOMAML），但仅限 DEVELOPMENT_VALIDATION_ONLY，不涉及 holdout，不可外推到真实气动/Concorde。
- 唯一 minor 为 A2 报告 §7.4 对 2400 条 null 的归因文字错误；不影响统计、决策、绑定或数据边界，建议回执前修正报告该行（无需重跑）。
- 5 个 fail-closed 篡改探针全部按预期拒绝（exit 2），clean control exit 0。

## 1. 绑定与完整性

| 项 | 实测 | 判定 |
|---|---|---|
| SHA256SUMS | 60 条；自身 sha256 `d7f68960a8b181f9c31f574e300a723d1031ec222dab04bb4a60bdd5559fac39`；总 8,166,179 B；逐条匹配 | PASS |
| run_config.json | 3,939 B，sha256 `9522d467f6b6fcc0bdd75694966d111f36a0ec4ae6c02eb4b98367fc5a6853e0` | PASS |
| run_summary.json | 3,908 B，sha256 `77d10cd62bc7295dc5d9d2477bed02bb9d83c627448356d421e8c657c652335e` | PASS |
| run_records.jsonl | 2,186,063 B，sha256 `32fbd2c65b6eb6e50e1bb3ca338a0b7da0a90e196242721961c73f344e0a9a25` | PASS |
| fd_gate.json | 8,795 B，sha256 `7950bcb05d322a41b0688e752b270ac47df6c97ed912b9fd83dd7023a8d5dec6` | PASS |
| data_manifest.json | 2,603 B，sha256 `8809813911478c6287dfe45727b4d7f6ac0b70e5cfc50eaa37ddbc8ef887ecef` | PASS |
| analysis/aggregate.json | 45,846 B，sha256 `16d7a4d3eca2b4e59e92d66cfbfaa3a543f4a2d0503dcd1acaf7eb7384af8463` | PASS |
| prereg raw | `research/concorde_metaopt/evidence/s2/s2_preregistration.json`，4,916 B，sha256 `fde3ef33bab53c67f5f595472a28538b13fbecbc5918903cdc6904c85ad692cd`；prereg_id `p4ra-s2-prereg-2751c162904d5a4f`；prereg_digest `c767f2066b720a10db20779507b9a71f21a6ee90e3c752b66e4588e0e98aec83`；analysis_plan_digest `43ac6ce0464461e371bdc2e694be9145816ffad3855d7ba9dd307459a9ed60c4` | PASS |
| code_sha | 三方一致 `3e6ece85a78f1cbb5a8639e279e8388d790213da5358ab35464c8cb37e67a5bb`；maml.py/s2_prereg.py/s2_runner.py canonical 顺序复算 | PASS |
| episode bank | 4,800 条，sha256 `6954b053fa5c005554c42bc6f60fc8b9be1d5a307ede49ce4f776d9f67c828a3`；run_config.episode_bank.episodes=4800 | PASS |
| 数据边界 | holdout_rows_used=0；holdout_metrics_read=false；allowed=[meta_train,meta_validation]；forbidden=[meta_test,meta_test_ood,negative_control]；aggregate.data_boundary.splits_seen=[meta_validation] | PASS |
| physical | prereg=0；run_config=0；run_summary=0；data_manifest=0；fd_gate=0 | PASS |
| 旧证据不可变 | source-repo HEAD=994cda8，git status --porcelain 空；source-repo-worktree 同 HEAD、status 空；复核 worktree primary-repo-s2-a5review2 HEAD=f4ab43f、status 空 | PASS |

## 2. 记录与覆盖（从 run_records.jsonl 直接计数）

- 6,000 条：train 1,200 + eval 4,800；0 FAILED；train 600/arm、eval 2,400/arm；20 个 task 全为 meta_validation；K∈{0,1,5,10}；draw=0..9。
- eval 6 个 (arm, meta_seed) 组合各 800 条；train 各 200 条；train 12 字段、eval 16 字段精确集合；网格键唯一。
- eval support_size=K（K=0/1 为 0/1），query_size=64；无重复、无 forbidden split、无 holdout 任务 ID。
- 2400 条含显式 null：全部为 eval K=0/K=1 的 `query_rmse_standardized`（按执行计划 §1 设计，K<2 标准化指标恒 null）；train 记录 1200 条缺少 `split` 键（是缺键，不是 null，也不在 eval 网格中）。
- 结论：记录完整性与数据边界通过；上述 null 不构成“记录失败”，也不进入推断端点。

## 3. 独立统计复算（不复用 A2 分析结果）

独立实现：task 级值 = 每 task 的 3 meta_seeds × 10 draws 均值；端点差 = FULL_MAML − FOMAML；Wilcoxon signed-rank exact（平均秩、精确分布、双侧、截断 1）；bootstrap 10,000 次（numpy default_rng(20261105)，percentile 2.5/97.5）；Holm 按升序 running max；相对改善 = (FOMAML_median − FULL_median)/FOMAML_median。

| 端点 | FULL mean / median | FOMAML mean / median | 中位差 | 相对改善 | Wilcoxon W / p_raw | Holm p_adj | 95% CI（均值差） | decision |
|---|---|---|---|---|---|---|---|---|
| k5（primary） | 1.0096595945946287 / 0.9541571205352783 | 0.9589177466107437 / 0.9228326803629854 | +0.03132444017229297 | −0.03394379158741091（−3.394%） | W=1（w+=209, w−=1），3.814697265625e-06 | 3.814697265625e-06 | [0.04110944269599093, 0.05986980980200832] | SUPPORTED_HARM |
| k10（secondary） | 0.9097952349242538 / 0.9102146042296693 | 0.9003567157566167 / 0.8957137631101255 | +0.01450084111954375 | −0.016189146261628796（−1.619%） | W=0（w+=210, w−=0），1.9073486328125e-06 | 3.814697265625e-06 | [0.0073239511408723255, 0.011701881656536987] | SUPPORTED_HARM |

- 与 aggregate 对比：`endpoint_diff=[]`、`inference_diff=[]`、`descriptive_diff=[]`、`pertask_csv_diff=[]`、`endpoint_csv_diff=[]`；CSV 280 行 task 级值与 aggregate 逐项一致。
- 方向稳健性：k5 20 个 task 中 19 个 FULL 更差、1 个更好；k10 20/20 FULL 更差。k5 唯一反向 task 的差值为 −0.0030238835901181815，不改变中位差/均值差方向。
- 总体：`overall.decision=SUPPORTED_HARM`，primary=k5，secondary=k10；Holm family_size=2（C1×k5/k10），family_id=`s2-primary-secondary-2tests`；无其他推断端点进入 Holm。

## 4. 报告核对

- A2 报告：`EXT/p4-route-a/a2/S2_formal_run_report.md`，31,383 B / 361 行，sha256 `20ee8874cc7831c53e96d0c27b9761d4ac2b95998f0c9f5e591c9d58f02a0cb2`；关键数字、哈希、绑定、9/9 图、FD、负控均核对一致。
- 报告 §7.2 表（:180-183）明确 CI 为“均值差”，同时列 mean 与 median；报告摘要 :20 的“中位差 + CI”需结合该表阅读，不构成统计错误。
- A5-S2PR-01：`inspect_frozen_package` 返回 physical_call_count=None（顶层无该键），实际 `orchestration.physical_call_count=0`；报告 §10.3/§11.1 已披露，非阻断。
- OBS-01：S2 holdout 口径 40（meta_test 20 + meta_test_ood 10 + negative_control 10）比 S0-7 的 30 更严格；报告 §11.2 已披露；本次 holdout 行 0。
- 绝对路径：aggregate.run_dir 为 EXT 绝对路径，aggregate.prereg.path 为 `.../s2_preregistration.json`；报告 §0/§1/§13 使用 EXT/worktree 路径。属机器本地证据，不影响数据/统计；建议回执说明或转相对路径（info）。
- 报告唯一实质问题：§7.4 :210 将 2400 条 null 归因为“训练记录无 split 字段（split=null）”，实际 2400 条是 eval K0/K1 的标准化指标 null；训练缺 split 键是 1200 条。另 §3 :88 “null 记录 0”指推理 null cells，与 :210 的原始记录 null 措辞易混。见 A5-S2R-01。

## 5. Fail-closed 篡改探针（在 EXT 副本上执行，不改原 run）

| 探针 | 篡改 | 结果 |
|---|---|---|
| control_clean | 无 | exit 0，clean 校验通过 |
| tamper_run_records | 改一条 eval 的 query_rmse_raw | exit 2，`S2_ANALYSIS_RUN_CONFIG`：run_summary 声明的 run_records sha 不符 |
| tamper_fd_gate | 改 fd_gate.result.checks[0].relative_error | exit 2，`S2_ANALYSIS_FD_GATE_NOT_PASSED`：payload 自排除 sha 不符 |
| tamper_data_manifest | holdout_rows_used=1 | exit 2，`S2_ANALYSIS_DATA_BOUNDARY`：raw sha 不符 |
| tamper_run_config | prereg_digest 改为全 0 | exit 2，`S2_ANALYSIS_RUN_CONFIG`：prereg_digest 不符 |
| tamper_run_summary_physical | physical_call_count=1 | exit 2，`S2_ANALYSIS_PREREG_PHYSICAL_COUNT_NONZERO` |

结论：分析层对记录/配置/FD/边界/physical 篡改均 fail-closed；不是“只写报告不校验”。

## 6. 发现（findings）

### A5-S2R-01（minor）报告 §7.4 对 2400 条 null 的归因文字错误

- 位置：`S2_formal_run_report.md:210`（另参见 `:88`）。
- 原文：“run_records 扫描中‘2400 条含 null’仅指训练记录无 split 字段（split=null），不是指标 null。”
- 实测（run_records.jsonl 全量扫描）：2400 条含 null 记录 = 1200 条 eval K=0 + 1200 条 eval K=1 的 `query_rmse_standardized: null`；train 记录 1200 条是缺少 `split` 键（不是 null）。`s2_formal_facts.json` 的 `records_with_null=2400` 与 `splits.null=1200` 也证明该区别。
- 影响：不影响统计、决策、绑定、数据边界和 0 物理结论；属于报告披露准确性 minor。
- 建议：回执前把 :210 改为“2400 条 eval K0/K1 标准化指标按设计为 null；训练记录 1200 条缺 split 键”；:88 的“null 记录 0”改为“推断端点 null cells 0/240”以避免歧义。无需重跑。

### A5-S2R-02（info）机器本地绝对路径

- aggregate.run_dir / aggregate.prereg.path 与报告 §0/§1/§13 含 Windows 绝对路径；不改变证据内容，但在不同机器复现时需先映射 EXT 与 worktree。建议回执注明“路径为生成机证据路径”，或提供相对路径重定位说明。

## 7. 资源与物理

- wrapper 总墙钟 101.57 s；base/r1/r2 run_wall_s=25.67694490007125/25.681539100012742/25.78525980003178 s。
- 每 arm：FULL_MAML train mean 3.6831412338651717 s、峰值 256.72265625 MB；FOMAML train mean 2.5632127992964038 s、峰值 261.57421875 MB；ratio 1.4369237056229534；资源上限 1200 s/8,192 MB/7,200 s。
- FD gate：32/32 PASS，max_rel=1.144759989428372e-09，容差 1e-6；pilot micro n=32 max_rel=1.2780446719818776e-09；pilot full_size n=8 max_rel=3.975211759696654e-10。
- 0 physical：无 VSPAERO/SU2/Gmsh/RCAIDE Mission/DOE/BO/DE/MAML 训练等新物理调用；仅合成 12D 任务的目标函数评估（run_records 为 B 类合成评价，physical=0）。
- 9/9 图 RENDERED；负面控制 13 PASS + 1 DISCLOSED（NC-10 determinism 由 run 层证据承载）；analysis checks 18 PASS + 1 DISCLOSED。

## 8. 复现命令与证据

```text
primary-repo/envs/RCAIDE/python.exe EXT/p4-route-a/a5/S2_result_review/recompute.py
# -> {"checks_pass": 140, "checks_fail": 0}
primary-repo/envs/RCAIDE/python.exe EXT/p4-route-a/a5/S2_result_review/tamper_probes.py
# -> control exit 0；5 个 tamper exit 2；all_ok true
```

- recompute.py：从 run_records 独立重算全部统计/CSV/报告/图/物理静态检查。
- recompute_results.json：140 checks，0 fail。
- tamper_probes.py / tamper_probes/tamper_results.json：6 个探针结果。
- 本复核未写仓库；所有临时副本在 EXT/p4-route-a/a5/S2_result_review/tamper_probes/ 下。

## 9. 限制

- 仅 meta_validation 20 任务、DEVELOPMENT_VALIDATION_ONLY；不涉及 holdout，不声称 S2 泛化成功。
- 合成任务目标，非真实气动；本结论不能外推到 Concorde 或真实巡航优化。
- 复核是静态/产物层复算，不重新训练；determinism 的 run 层证据来自 A1 的 base/r1/r2 与 compare，不由分析层自证。
