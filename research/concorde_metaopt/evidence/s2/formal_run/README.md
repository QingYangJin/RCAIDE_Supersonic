# S2 正式运行证据包：FULL_MAML 二阶 vs FOMAML（全合成、physical=0）

本目录是 Issue #7（D-P4-003）S2 阶段**正式离线运行**的可提交证据包，由 Lead 从本机外部记忆目录的原始运行产物打包并做路径脱敏生成。包 revision 3。自 revision 2 起 manifest 采用**双哈希口径**（工作树 raw + git blob canonical LF），SHA256SUMS 采用 canonical-LF 口径（详见第 8 节）；revision 3 修正 `sanitized` 标记、补充脱敏规则与复核互链（payload 字节未变）。
所有产物为**合成解析任务离线训练/评估**，未调用任何真实气动求解器（VSPAERO/SU2/RCAIDE），未读取任何 holdout 真实飞机数据。

## 1. 来源与绑定

| 项 | 值 |
| --- | --- |
| run_id | s2-formal-20261106T1810Z |
| run_mode / status | FORMAL / COMPLETED |
| source commit | 994cda8e0942060072d65eb50dde790c44d32194（parent f4ab43f；branch research/p4-route-a-s2） |
| 冻结 prereg | `research/concorde_metaopt/evidence/s2/s2_preregistration.json`（raw 4,916 B，sha256 fde3ef33bab53c67f5f595472a28538b13fbecbc5918903cdc6904c85ad692cd） |
| prereg_id | p4ra-s2-prereg-2751c162904d5a4f |
| prereg_digest | c767f2066b720a10db20779507b9a71f21a6ee90e3c752b66e4588e0e98aec83 |
| code_sha | 3e6ece85a78f1cbb5a8639e279e8388d790213da5358ab35464c8cb37e67a5bb |
| 训练 episode bank sha256 | 6954b053fa5c005554c42bc6f60fc8b9be1d5a307ede49ce4f776d9f67c828a3（4,800 episodes） |
| 冻结 prereg created_utc | 2026-11-06T17:43:39+00:00 |

## 2. 运行事实

- 记录数：train 1,200 + eval 4,800 = 6,000；FAILED 0；无 RESOURCE_LIMIT、无重试。
- 预算：2 arms（FULL_MAML / FOMAML）× 3 meta_seeds [0,1,2] × 200 outer steps；评估 20 tasks × K∈{0,1,5,10} × 10 draws。
- 墙钟：base run run_wall_s=25.6769；含确定性重跑 r1/r2 的 wrapper 总墙钟 101.57 s；峰值内存 261.57 MB；train_wall_seconds_ratio（FULL/FOMAML）=1.4369237。
- 训练耗时（均值）：FULL_MAML 3.6831 s/seed（3.6689/3.7138/3.6666，峰值 256.72 MB）；FOMAML 2.5632 s/seed（2.5440/2.5988/2.5469，峰值 261.57 MB）。
- 确定性：run_config 3/3 同 sha；run_records_core 3/3 同 sha（c9460dae…）；compare_r1/r2 全字段 true。
- FD 门：32/32 PASS，max_relative_error=1.144759989428372e-09（阈值 1e-6），mode=full。
- 数据边界：仅 meta_train / meta_validation；holdout_rows_used=0、holdout_metrics_read=false；physical_call_count=0；evidence_scope=DEVELOPMENT_VALIDATION_ONLY。

## 3. 主结果（预注册端点，task 级配对）

overall_decision = **SUPPORTED_HARM**（在全合成开发验证范围内，FULL_MAML 二阶元学习相对 FOMAML 的适应后误差显著更大，即二阶并未带来收益）。

| 端点 post_adaptation_rmse_raw | k=5 | k=10 |
| --- | --- | --- |
| FULL_MAML − FOMAML 均值差 | +0.050741847983885126 | +0.009438519167637188 |
| 两臂中位数之差 | +0.03132444017229297 | +0.01450084111954375 |
| 相对改善（负=更差） | −3.394% | −1.619% |
| Wilcoxon exact p（Holm 校正后） | 3.814697265625e-06 | 3.8147e-06 |
| bootstrap 95% CI（n=10,000, seed=20261105） | [0.04110944269599093, 0.05986980980200832] | [0.007323951140872326, 0.011701881656536987] |
| task 级 FULL 更差计数 | 19/20 | 20/20 |

null 端点缺失：0/240。负控 13 PASS + 1 DISCLOSED。全部 9 张图（fig1..fig9）已渲染，0 NOT_RUN。

## 4. 文件清单（38 个 payload 文件）

- `run_config.json` / `run_summary.json` / `run_records.jsonl` / `fd_gate.json` / `data_manifest.json`：运行合同与原始记录（原始字节未脱敏；已实测不含任何本机绝对路径；run_records.jsonl 为 2,186,063 B）。
- `analysis/`：aggregate.json（脱敏）、s2_prereg_echo.json（脱敏）、6 个统计 CSV、figure_status.json、fig1..fig9 PNG 与对应 support CSV。
- `determinism/compare_r1.json`、`compare_r2.json`：确定性重跑对比。
- `reviews/`：A5 结果复核（md + verdict JSON，脱敏）、A3 隔离审计报告（脱敏）。
- `PACKAGE_MANIFEST.json`：逐文件 `bytes_raw`/`sha256_raw`（工作树原始字节）与 `bytes_lf`/`sha256_lf`（git blob canonical LF），含来源与脱敏标记；`SHA256SUMS.txt`：38 条 payload 校验和（canonical-LF 口径，不含 manifest 与自身）。
- 仓库内同时提交 `docs/reviews/p4_route_a_s2_formal_run_report_20261107.md`（A2 正式报告 repo-ready 副本，31,771 B，sha256 f97b8eb5edf273145a497305a64e2edaa4f52dbcd79b5d699ac7c190617d3372）。

## 5. 复核链

- A5 结果复核：APPROVE_FOR_S2_RECEIPT，0 blocker / 0 major / 1 minor（A5-S2R-01）；关闭依据为 A2 修正版正式报告（sha 48e0a274…，其中 §7.4 null 口径说明）；A5 review 正文见 `reviews/S2_result_review_a5.md`。A5 独立复算 140 checks PASS/0 FAIL。
- A3 隔离审计：PASS_WITH_WARNINGS，20/20 PASS、0 FAIL；SHA256SUMS 60/60 独立重算一致；0 solver / 0 仓库写 / 0 GitHub 写；6 条仅披露类告警。
- A3 证据包 delta 审计（27c935e）：PASS_WITH_WARNINGS，C01–C19 全 PASS、0 FAIL；W01–W06 均 info。
- Lead 独立核验：重算 k5/k10 均值差与 aggregate 一致；40 余项探针与篡改负控全部 fail-closed。

## 6. 复现

```
# 1) 检出冻结代码（仅 meta_learning/tests/prereg，不含本证据包）
git checkout 994cda8e0942060072d65eb50dde790c44d32194
# 2) 正式 run（FORMAL，1200+4800 记录，约 26 s；零物理）
#    python -m research/concorde_metaopt/... 见计划 §5 与 s2_runner.run_experiment
# 3) 分析（读 run 目录，写 aggregate+CSV+9 图）
```

本环境 python：RCAIDE 环境 python 3.11.17 + torch 2.8.0+cpu；命令细节见仓库 `docs/planning/p4_route_a_s2_execution_plan_20261106.md` v1.6+ 与 A2 报告。

## 7. 边界与披露

- 本证据包**不**构成真实飞机/真实气动验证；仅合成解析任务开发验证。
- 不合并 main；不改动 M2/M5/M6/S0-2..S0-7/S1 的既有冻结证据；physical_call_count=0。
- 脱敏披露：manifest 对 5 个文件记录 `sanitized=true`（`analysis/aggregate.json`、`analysis/s2_prereg_echo.json`、`reviews/S2_result_review_a5.md`、`reviews/S2_result_review_a5_verdict.json`、`reviews/S2_isolation_audit_a3.md`），其余 33 条为 `sanitized=false`；替换规则见顶层 `sanitization` 块。上述文件中的本机绝对路径已替换为 `EXT/…`、`source-repo`、`source-repo-worktree`、`primary-repo`、`USERPROFILE` 等相对标记；JSON 数值/结构逐项保持不变（见 PACKAGE_MANIFEST 的 sanitized 字段）。`run_config.json`/`run_summary.json`/`fd_gate.json`/`data_manifest.json`/`run_records.jsonl` 保持原始字节（实测无本机绝对路径）。
- EOL 披露：7 个 payload 文件在 Windows 工作树为 CRLF，而 git blob 为 canonical LF（Δ313 B）；其余为 LF。manifest 双哈希并存，SHA256SUMS 用 canonical LF。
- A3 告警 W03：3 个辅助脚本在 EXT 原始树中含本机路径，不在本包内。

## 8. 哈希口径与校验

- `PACKAGE_MANIFEST.json` 每文件两套：`sha256_raw`/`bytes_raw` 按工作树原始字节；`sha256_lf`/`bytes_lf` 按 git blob（canonical LF）。`eol` 字段标注 `LF` 或 `CRLF`。
- `SHA256SUMS.txt` 全部使用 `sha256_lf`（canonical LF），因此任何平台 clone 后可用下述命令逐条校验：

```
# canonical LF 校验（推荐，跨平台可复现）
git cat-file blob HEAD:research/concorde_metaopt/evidence/s2/formal_run/run_config.json | sha256sum
# 工作树 raw 校验（Windows autocrlf 下 7 个 CRLF 文件会与 raw 值一致）
sha256sum research/concorde_metaopt/evidence/s2/formal_run/run_config.json
```

`SHA256SUMS.txt` 自身与 `PACKAGE_MANIFEST.json` 不在 sums 覆盖范围；manifest 记录 sums 的 sha256 与条数，A3/A5 可交叉核验。

`PACKAGE_MANIFEST.json` 的 `sanitized` 标记：5 个脱敏文件为 `true`，其余 33 条为 `false`；顶层 `sanitization` 块记录替换规则、token 列表、脱敏文件清单与 `numeric_structure_identical=true`（JSON 数值/结构逐项不变）。

