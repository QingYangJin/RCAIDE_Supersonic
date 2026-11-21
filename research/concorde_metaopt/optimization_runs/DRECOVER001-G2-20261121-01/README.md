# DREAL003 G2 B01 中间批次记录（DRECOVER001-G2-20261121-01）

本目录是 Issue #13 G2 阶段 **B01 试跑批次** 的原始计算文件与整理结果。它不是 G2 完成回执，也不是 G3/R2 的授权。

## 授权与身份

- authorization_id: `AUTH-DREAL003-G2-20261121-01`
- batch_id: `B01`
- GO 记录: `tables/g2_go_record_b01.json`（授权本批 24 starts）
- A5 预审: `audits/a5_g2_review_verdict.json`（deepseek-flash 单发只读；**非人类签署**）
- 预注册: `tables/g2_preregistration.json`

## 实际执行事实（以本目录账本为准）

- physical_solver_starts_actual = **24**（24/24 授权，剩余 0；G2 累计 24/240）
- completed = 23（stage1 12 个 + stage2 11 个）
- interrupted = 1（`g2-m140-d03-support-s1`：启动事件存在，但被外层 120 s 超时杀掉，无 .polar / case_result；按中断计费为 NULL，不重跑）
- internal_solver_cases_actual = 731（记录值；中断 case 的内部数未知，未计入）
- retries = 0，parallelism = 1
- 准入标签 = **4**（全部为 M160 support 设计 d00–d03 的 stage2 原始 polar 行）
- null = 20（stage1 筛选 12 + stage2 审计失败 7 + 中断 1）
- 有效标签率 = 4/23 = **17.4%**，远低于 Issue #13 G1/G2 的 70% 目标；本批**不宣称达标**。

## 方法与本批暴露的缺陷

B01 采用“stage1 全窗口 alpha 粗扫（49 点）→ 全范围 OLS 拟合 CL(alpha) → stage2 在预测 alpha 附近 13 点细化”。M140 的大部分 case 失败原因不是容差，而是**全范围 OLS 在非线性高 alpha 段低估局部斜率**，把 stage2 中心放低了约 0.1°，13 点窗口（±0.006°）完全落在目标之外。M160 的 4 个 support 设计因曲率较小而成功命中。

因此 B01 是**方法诊断批次**，不能作为“G2 已达到标签率”的证据。下一批（B02）开始前必须提交方法修订：stage2 中心改用 stage1 原始 polar 行的局部线性插值（bracket 两行），并用同一批数据验证中心误差；该修订需 A5 amendment 与新 GO。

## 数据与审计链

- 每个 case 目录包含 `plan.json`、`approval.json`、`task_spec.json`、`case_inputs.json`、`solver_attempts.jsonl`、VSPAERO 原始 `.vsp3/.vspgeom/.vspaero/.history/.polar/.lod/.adb`、stdout/stderr 日志；完成的 case 另有 `audit.json`、`admission_manifest.json`、`admission_certificate.json`。
- 准入规则：只接受 stage2 的**实际 polar 行**满足升力相对容差 1e-3；stage1 仅筛选，不产生标签。
- 证据范围：`LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`；同机保存；Owner 已豁免异机故障域备份（`WAIVER-OFFMACHINE-BACKUP-20261118`）。
- 未做物理验证（无风洞/CFD 交叉验证）；VSPAERO 内部求解器，LF-M2.02 未验证。

## 目录

- `raw_cases/`：24 个实际启动 case 的原始文件
- `tables/`：`all_evaluations.csv`、`admitted_labels.csv`、`failed_or_null.csv`、`attempt_ledger.csv`、`batch_accounting.json`、预注册/GO/授权
- `figures/`：中文标注 PNG + `figure_data.csv`（只画有标签的点）
- `audits/`：A5 verdict、控制台日志
- `metadata/`：任务族/split、代码 SHA、几何冻结
- `scripts/`：本批构建/运行/后处理脚本
- `data_manifest.json` / `SHA256SUMS.txt`：完整性与逐文件哈希

## 下一门禁

G2 尚未完成：8 个任务中只有 M160 有标签，B02 需方法修订 + A5 amendment + 新 GO；G3/R2 仍未授权。
