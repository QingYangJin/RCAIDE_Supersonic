# DRECOVER001-G1-20261121-01 · Issue #13 G1 真实批次

本目录是 Issue #13 G1 的原始计算文件、表格、账本、审计与中文图表。所有数值来自本机真实 VSPAERO 3.55.0（omp=1）运行；没有 mock、replay 或旧数据冒充。

## 身份与授权
- run_id: DRECOVER001-G1-20261121-01
- authorization_id: AUTH-DREAL003-G1-20261121-01（Owner m07992；G1 总上限 24 starts）
- batch: B01（8 starts）+ B02（16 starts）
- A5: deepseek-flash 只读单发 dossier 审查；B01 verdict G1_APPROVE、B02 repair verdict G1_REPAIR_APPROVE；均非人类签字，不授权 G2/G3/R2。

## 结果（精确记账）
- physical_solver_starts_actual = 24（B01 8 + B02 16），达到 G1 上限，剩余 0。
- 完成求解 = 23；B02 的 `g1-m202-d05-query` 有 start 事件但无 case_result（外层编排 120 s 超时中断；计入 1 次启动，不重跑）。
- internal_solver_cases_actual = 391。
- 准入标签 = 8；null = 16；valid_label_rate = 8/23 = 34.8%，未达到 Issue #13 G1 的 70% 目标；本目录不宣称达标。
- B01：8 starts / 0 标签（8/8 CL_TARGET_OUTSIDE_POLAR，alpha 外推偏大）。
- B02：16 starts / 8 标签（M180 2、M202 3、M240 3）。

## 失败与负结果（原样保留）
- 15 个 null 为 AUDIT_FAILED：audit 要求极曲线中存在实际行满足 1e-3 升力相对容差；solver 的插值残差约 0.0015–0.0027，故不接纳。没有放宽容差，也没有把插值写成原始行标签。
- 1 个 null 为启动后无结果（m202-d05-query）。
- B01 的 8 个 null 永久保留；B02 修复 alpha 模型后仍有 8 个未过审计，说明仅修 alpha 基准不足以稳定命中 1e-3 容差。
- 旧 F1R2/F2R2 仍为 RAW_LOST/HISTORICAL_REPORT_ONLY；本批是重新生成，不是找回。

## 数据与可复核性
- `raw_cases/<case_id>/`：每个已启动 case 的 .vspgeom/.vspaero/.polar/.history/.lod/.adb/.vkey、plan/approval/task_spec/case_inputs、audit 与证书（若有）。
- `tables/`：all_evaluations.csv、admitted_labels.csv、failed_or_null.csv、attempt_ledger.csv、batch_accounting.json、B01/GO/修复 amendment/A5 引用。
- `metadata/`：task_family_split.json、geometry_freeze.json、code_sha.json。
- `audits/`：A5 verdict 与 dossier、批次日志。
- `SHA256SUMS.txt` + `data_manifest.json`：逐文件 SHA256 与字节数。
- `figures/`：中文 PNG（仅可视化，不新增物理）与 figure_data.csv。
- 同机保存；Owner 已豁免异机独立故障域备份（WAIVER-OFFMACHINE-BACKUP-20261118）。本目录不是异机备份，也不声称物理验证或泛化。

## 边界
- 不授权 G2/G3/R2；不声称 70% 标签率；不声称 MAML 性能；不把本批标签当作已认证的跨机真值。
