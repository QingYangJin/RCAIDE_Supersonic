# [R2/M2 阶段状态｜2026-11-20] 真实 VSPAERO 24/24、9 条准入标签、K=1 FOMAML 探索性结果

> **性质**：阶段进度与状态通报，**不是**新的 GO、**不是** R1/R2 验收 PASS、**不是**人类签署。本轮 R2 授权预算已用完（24/24 starts）；继续真实求解必须新建 authorization_id/batch_id、重新 A5 预审并由 Lead 发新 GO。所有标签仍为 `LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`，同机保存，不冒充异机备份。

## 1. 远端位置

- 分支：`recovery/drecover001-20261117`
- commit：`5e85c74587bde97a1b3f7fb2e1ade24b8dafee22`
- tree：`fb6403c671780ebb6e97c11c6a780b6dcb4f2523`
- parent：`2273024eeb5eae634b11fcebcee16376c82e409e`
- 本次推送 9 个文件：A5 closure/repair dossier 与 verdict、follow-up code freeze、真实 MAML 结果 JSON/Markdown、`real_training.py` 及其守卫测试。

本轮是依据 #12 修订**重新生成真实数据**，不是找回 F1R2/F2R2；旧数据仍固定为 `RAW_LOST / HISTORICAL_REPORT_ONLY`，没有混入新标签。

## 2. 真实批次与记账

授权：`AUTH-DRECOVER001-R2-20261120-01`，含 B01（14 次 matrix starts）与 B01R（7 次修复 starts）。

| 项目 | 结果 |
|---|---|
| 真实 starts | **24 / 24**，`remaining=0` |
| 完成 / 中断 | 23 完成；`m240-d01-support` 因外层 120s 超时中断，已计费并保持 `NULL_LABEL`，未重跑 |
| internal cases | 645 |
| retries / parallel | 0 / 1 |
| 准入证书 | 10 张；去重后 **9 条可用真实标签** |
| 失败/空标签 | 14 条（含 baseline-coarse 的 invalid row、12 条未命中 1e-3 升力行、1 条中断） |

9 条标签覆盖 4 个任务：

| 任务 | split | Mach | q (Pa) | 标签数 |
|---|---|---:|---:|---:|
| M160 | train | 1.6 | 12,851.4 | 2（d00 support / d02 query） |
| M202 | train | 2.02 | 20,483.9 | 3（d00、d01 support / d02 query） |
| M180 | val | 1.8 | 16,265.1 | 2（d00 support / d02 query） |
| M240 | test | 2.4 | 28,915.7 | 2（d00 support / d02 query；d01 中断为 null） |

批次记账、证书与 null 标签可核对：`D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/batch_accounting.json`（SHA256 `5e2a44c15fbed7cd9da2541deceb82ee82fbf924f6511e762b4c24eeac17cc48`）。

## 3. A5 与门禁

- 3 个 pilot starts 早于 A5，这是治理顺序缺陷，已在 dossier 中披露；A5 以 `RATIFIED_WITH_CONDITIONS` 追认。
- A5 closure review 返回 **PASS**，仅覆盖 24 starts 的矩阵计划、既有冻结代码与 pilot 处置；6 项条件 C1–C6 已在 `r2_gate_record.json` 闭合，`maml_started=true`。
- A5 repair amendment 返回 **PASS**，只授权 7 个 B01R case、无 retry，并在标签不足 2 train + 1 val + 1 test 时停止 MAML；本轮满足 4 任务后按 K=1 执行。
- A5 身份是 deepseek-flash 单发只读子智能体，`tool_access=NONE_SINGLE_SHOT_DOSSIER_STREAM`，**不是人类签署，也不等于 A5 对全部 R1 代码的最终 PASS**。
- 新增 `real_training.py` 在 A5 repair 冻结之后加入，**未经 A5 审查**；`r2_followup_code_freeze_20261120.json` 已明确声明。

## 4. K=1 FOMAML 探索结果

- 数据集：9 条真实标签，4 任务；数据集 SHA256 `c63ccb0a7becd3dd7f558b9de7c61efa280c75bc1d385ea96492d631fccbab8b`。
- 配置：12D→32→32→1，first-order FOMAML，`inner_lr=0.05`、`inner_steps=5`、`outer_lr=0.01`、20 outer steps、`tasks_per_batch=2`、K=1、seed 7；每任务 1 support / 1 query。
- 运行：`DRECOVER001-MAML-20261120T074500Z`，状态 `REAL_META_TRAINING_EXECUTED`，训练期间 physical starts=0。

| 评估 | adapted Di_N | 真值 | 相对误差 | MSE |
|---|---:|---:|---:|---:|
| val M180 | 159,539.48 | 145,594.17 | 9.58% | **1.945e8** |
| val zero-shot | 158,709.21 | 145,594.17 | 9.01% | **1.720e8** |
| test M240 | 153,611.29 | 103,658.99 | 48.19% | **2.495e9** |
| test zero-shot | 158,709.21 | 103,658.99 | 53.11% | **3.031e9** |

解释：val 上 adaptation **更差**（MSE 增加约 13.1%）；test 上 adaptation 略好（MSE 降低约 17.7%），但只有 1 个 query、1 次运行，**不能宣称泛化或 K-shot 有效性**。train query 误差为 M202 24.48%、M160 6.99%，也未达到可用水平。

结果与摘要：
- `docs/evidence/drecover001/real_maml_result_20261120.json`（SHA256 `8a3d998747a5f91abcec6388cdec0f1074516bfadc159b15b3cfabb7602621b7`）
- `docs/evidence/drecover001/real_maml_experiment_20261120.md`

## 5. 本轮没有关闭什么

- **R2 未完全闭合**：Issue #12 要求至少一条真实反馈驱动的 BO/DE 轨迹；本轮 24/24 starts 全部用于基准、升力匹配和修复批次，**没有做 ask→实际评价→tell 的 BO/DE**，也没有多 seed / 多 query。
- **M2 只是探索性 K=1**，不是统计意义上的真实 FOMAML 对照；M3 未见任务 K-shot 等预算对照尚未开始。
- 已知代码缺陷未修：`research/concorde_metaopt/dreal001/geometry/solver_runner.py` 的 `build_evaluation` 仍用 `TASK_SPEC.q_pa` 与 `TASK_SPEC.mach`，非 M2.02 case 的 `case_result.lift_match` 会误报 `CL_TARGET_OUTSIDE_POLAR`。本次准入用 `audit_real_case.py` 从 deck 的 `Rho/Vinf` 复算 q，**9 条证书不受影响**；但下一批前必须修复并重跑全量 preflight。
- 原始 `.vspgeom/.polar/.history` 与证书仍在工作机 `.real_runs`，仅同机保存；异机备份按 Owner 豁免未做，**不是** `BACKUP_RESTORE_PASS`。
- `fuel_burn_kg=null`、`VSPAERO_INTERNAL_ONLY`、`LF-M2.02=NOT_VALIDATED` 边界不变。

## 6. 建议的下一步（需新的有限授权）

1. 修复 `build_evaluation` 的 q/Mach 来源，补非 M2.02 回归测试，重跑全量零物理 preflight。
2. 把 `real_training.py` 与真实 MAML 证据送 A5 独立复审；未复审前不把它称为 A5 已审入口。
3. 新建 authorization_id / batch_id，A5 预审后由 Lead 发新 GO：先做至少一条真实反馈 BO/DE 轨迹，再做多 seed / 多 query 的 K-shot 与 M3 等预算对照。
4. 新批次继续逐次记账、原始文件 SHA、失败 null、同机备份披露；不复活 #9/#10 旧 GO，不覆盖历史负结果。

**当前结论**：真实 VSPAERO 数据链、真实准入和真实 FOMAML 执行链已经打通并产出可审计结果；但 R2 仍缺真反馈优化轨迹，M2 仍是 K=1 探索，M3 未开始，A5 对 R1 全部代码的最终 PASS 也未形成。