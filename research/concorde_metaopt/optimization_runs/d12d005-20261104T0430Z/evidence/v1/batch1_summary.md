# D-12D-005 A 类第一批（S0..S5）执行摘要

run_id: d12d005-20261104T0430Z
status: BATCH1_STOPPED_ABORT_FINAL_FREEZE（Lead 已批准停止并冻结）

## 结果

| 案 | 状态 | 事件 | 墙钟 s | CLtot | CDtot | 备注 |
|---|---|---|---|---|---|---|
| S0 | SOLVED_VALID | NA-D12D005-001 | 4.045 | 0.126545398398 | 0.020946562364 | 有效 |
| S1 | SOLVED_VALID | NA-D12D005-002 | 6.012 | 0.134634955743 | 0.021167612993 | 有效 |
| S2 | SOLVED_VALID | NA-D12D005-003 | 0.507 | 0.126555050502 | 0.02094685813 | 有效 |
| S3 | FAILED_INVALID_POLAR | NA-D12D005-004 | 1.008 | 0.074251031783 | 0.013789407924 | S3 触发停止规则 |
| S4 | NOT_RUN_AFTER_ABORT | - |  |  |  | 未启动 |
| S5 | NOT_RUN_AFTER_ABORT | - |  |  |  | 未启动 |

## 预算

- starts: 4/6 used；remaining 2 关闭（不重分配、不重试、不结转）；billable_events=4；retries=0；class A used total 4/20。
- S4/S5 从未启动，未计费。

## 停止规则

- 事件 NA-D12D005-004（S3_STD_M2p02_base，M2.02）返回 rc=0、history 有限，但 polar 校验 rc=2：POLAR_NONFINITE line 4 第 47 列 Ew=inf。
- 按 stop rule 1（NaN/INF/IND -> INVALID）立即停止整批；S4/S5 标 NOT_RUN_AFTER_ABORT。

## S3 列诊断（零求解）

- S3 polar 仅 1 个非有限 token：line 4, column 47/48 = Ew, inf；S0/S1/S2 各 0 个。
- 主系数全有限：CLtot=0.074251031783、CDtot=0.013789407924、CDi=0.002606540227、CMoy=0、CMytot=-0.014777040022。
- 判断 (A) 派生效率列退化伪影：CDwtot=0.011182867698（非零有限）、CLwtot=-0.000390514345（近零）、LoDw=-0.034920769492；history 5 步残差单调下降（L2 1.11 -> -2.75），CLtot/CDtot 平滑收敛。
- 但 Ew=inf 仍使 polar fail-closed，VSPAERO 7.2.2 thin 在 M2.02 判 NOT_VALIDATED；S3 的 CL/CDi 只作诊断，不得进入阻力/燃油/body correction。

## 门禁影响

- LF VSPAERO 7.2.2 thin M0.10 标准矩形翼：S0/S1/S2 有效（单因素 wake 敏感性可用）。
- LF 超声速（M2.02）：NOT_VALIDATED；12D 主翼 S5 未运行，12D 独立机翼 LF 仍无有效证据。
- 全机已验证燃油标签：false；外部 body correction 未注入（NOT_VALIDATED）。
- 与 D-12D-004 V1 对照：M2.02 为两种独立失败模式（V1 数值发散 vs 本批派生列退化）；V1 的 M0.10 异常在本批未复现。

## 记录

- 逐案结论: evidence/v1/per_case_conclusions.md / .csv
- 停止决定: evidence/v1/stop_decision.json
- 结果: evidence/v1/batch1_results.json
- 账本: evidence/v1/ledger.jsonl（4 COMPLETED + 1 AMEND）
- S3 诊断: evidence/v1/cases/S3_STD_M2p02_base/s3_column_diagnosis.json / .md / verify_polar_rerun.json
- 清单: evidence/v1/data_manifest.json

