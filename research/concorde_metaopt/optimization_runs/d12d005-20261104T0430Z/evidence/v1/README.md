# D-12D-005 A 类第一批（S0..S5）证据目录

status: **BATCH1_STOPPED_ABORT_FINAL_FREEZE**  
run_id: d12d005-20261104T0430Z  
冻结时间 (UTC): 2026-11-04T07:27:14Z  
求解器: VSPAERO 7.2.2 thin (`-omp 4`)，exe sha256 `db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad`；仅升力面（无机身），plain VLM 气动回退。

## 结果（4/6 starts）

| 案 | 状态 | 墙钟 s | CLtot | CDtot |
|---|---|---|---|---|
| S0 | SOLVED_VALID | 4.045 | 0.126545398398 | 0.020946562364 |
| S1 | SOLVED_VALID | 6.012 | 0.134634955743 | 0.021167612993 |
| S2 | SOLVED_VALID | 0.507 | 0.126555050502 | 0.02094685813 |
| S3 | FAILED_INVALID_POLAR | 1.008 | 0.074251031783 | 0.013789407924 |
| S4 | NOT_RUN_AFTER_ABORT |  |  |  |
| S5 | NOT_RUN_AFTER_ABORT |  |  |  |

## 停止

- `NA-D12D005-004`（S3, M2.02）rc=0，但 polar 校验 rc=2：`POLAR_NONFINITE: line 4, column Ew, token='inf' in S3_STD_M2p02_base_model.polar`。
- 命中停止规则 1（非有限值 → INVALID）→ 批次停止；S4/S5 NOT_RUN_AFTER_ABORT；remaining 2 关闭（不重分配、不重试、不结转）；billable 4、retries 0。
- S3 列诊断（零求解）：判定为派生效率列退化（`CDiw=0` 使 `Ew = CLtot²/(π·AR·CDiw)` 除零为 inf；`CLwtot≈0` 不是原因），主系数与 history 均有限且收敛；但 fail-closed 仍拒收，VSPAERO 7.2.2 thin M2.02 判 NOT_VALIDATED。revision 5 的 `case_summary_reconciliation.json` 用 v2 解析器（allowlist `Ew`）重读四案 polar：S0/S1/S2 = `PASS`、S3 = `PASS_WITH_WARNINGS`，主系数与 `batch1_results.json` 一致。

## 文件

- `evidence/v1/ledger.jsonl` — append-only 账本：4 COMPLETED + 1 AMEND（事件 004 精确原因）
- `evidence/v1/stop_decision.json` — 停止决定、精确失败文本、Lead 批准、受影响门禁
- `evidence/v1/per_case_conclusions.md/.csv/.json` — 逐案结论
- `evidence/v1/batch1_results.json` — 机器可读结果汇总
- `evidence/v1/batch1_summary.md` — 一页中文摘要
- `evidence/v1/batch_state.json` — 批次状态（含 S3 系数与 S4/S5 NOT_RUN 条目）
- `evidence/v1/run_start.json` — 授权与运行开始记录（AUTHORIZED → RUN_STOPPED_FINAL_FREEZE）
- `evidence/v1/cases/<case>/` — polar/history/stdout/stderr/case_summary（S3 另含 s3_column_diagnosis.json/.md 与 verify_polar_rerun.json/.log）
- `evidence/v1/summary.json` — 冻结摘要（机器可读）
- `evidence/v1/final_checks.json` — 最终断言校验结果
- `evidence/v1/data_manifest.json` — 本清单（**revision 6**，schema 2，40 条 = `evidence/v1/` 37 文件 + `config/` 3 文件；逐文件 `bytes_raw`/`sha256_raw` 与 `bytes_canonical_lf`/`sha256_canonical_lf` 双形态，`total_canonical=290,912 B`、`total_raw=292,514 B`；revision 6 在最终 README/run_start 文本修订后重跑，40 条逐条与提交 blob 一致）
- `evidence/v1/case_summary_reconciliation.json` — 四案 polar 主系数对账（v2 解析器 allowlist `Ew`；A2 原始 `case_summary.json` 不改写）
- `config/run_config.json` — 本批运行配置（最终冻结态）
- `config/approval_and_budget_ledger.json` — 授权/预算账本（最终冻结态）
- `config/solver_case_matrix.csv` — S0..S5 矩阵（状态列已更新）

## 门禁

- LF VSPAERO 7.2.2 thin **M0.10 标准矩形翼**：S0/S1/S2 有效（单因素 wake 敏感性可用）。
- LF 超声速 **M2.02**：NOT_VALIDATED；12D 主翼（S5）未运行，12D 独立机翼 LF 仍无有效证据。
- validated_aircraft_fuel_label = false；外部 body correction 未注入（NOT_VALIDATED）；本批不产生全机阻力/燃油结论。
- 与 D-12D-004 V1 的关系：M2.02 为两种独立失败模式（V1 数值发散 vs 本批派生列退化）；V1 的 M0.10 异常在本批未复现。

## 复现

- 每案 bundle（模型/合约/vspgeom/expected.json）在仓库外：`C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/a2/bundles/<case>/`。
- 求解命令（cwd = 该案 bundle）：`vspaero.exe -omp 4 <base>`，其中 <case>_contract.vspaero 复制为 <base>.vspaero。
- 校验：`python -B research/concorde_metaopt/scripts/vspaero7_runner_v2.py verify-polar --polar <polar> --expect <bundle>/expected.json`（以及 verify-history）。
- 本冻结过程零求解：仅重跑 above verify-polar 一次用于取回精确错误文本（rc=2，无 solver 启动）。

