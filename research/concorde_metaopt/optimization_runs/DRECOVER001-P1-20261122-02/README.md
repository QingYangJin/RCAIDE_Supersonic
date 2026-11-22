# DRECOVER001-P1-20261122-02 — Issue #14 P1 自适应迎角真实评估批次

- 关联 Issue: https://github.com/QingYangJin/RCAIDE_Supersonic/issues/14
- 分支: research/dreal004-alpha-adaptive-meta-sampling
- run_id: DRECOVER001-P1-20261122-02
- batch_id: DRECOVER001-P1-20261122-02-B01
- authorization_id: AUTH-DREAL004-P1-20261122-01（Owner m10191 “批准真实评估”）
- 上限: 12 次真实 starts；每设计 ≤3；每 start ≤3 个 alpha probe；内部 case ≤36；0 retry；parallel 1；单 case 600s；墙钟 3600s
- 容差: |q*Sref*CL - lift_target|/lift_target <= 1e-3，不放宽；只有新求解的原始 polar 行可准入

## 做什么

目标任务 DREAL004-M202（Mach 2.02，alt 18288 m，q≈20483.94 Pa，Sref 358.25 m²）。对 d00/d01/d04/d07 四个设计，用 G2 stage1 既有原始 polar 行做 coarse bracket（零物理），据此割线预测 alpha_target，每轮在预测点 ±0.004/0.002/0.001° 内取 3 个 alpha probe，跑 1 次真实 VSPAERO；若新原始行命中升力容差则独立审计+准入，否则重拟合 bracket 再试，最多 3 轮；未命中即 NULL_LABEL，不重跑。

## 目录

- raw_cases/<case_id>/：原始 .vspgeom/.vspaero/.polar/.history/.lod/.adb/.vkey、plan/approval/task_spec/case_inputs/case_result/audit/admission manifest/certificate、logs
- tables/：p1_attempt_ledger.csv、p1_alpha_refinement_history.csv、p1_admitted_labels.csv、p1_failed_or_null.csv、actual_solver_ledger.csv、all_evaluations.json
- p1_accounting.json：六类计数（starts/内部 case/retry/parallel/准入/NULL）、固定 49 点扫描对照 196 internal、停止原因
- p1_preregistration.json、p1_a5_dossier.md、p1_go_record.json、a5_review/：预注册、A5 卷宗与独立评审结论、Lead GO 记录
- scripts/：p1_prereg.py、p1_run.py、p1_upload.py、p1_a5_review.py、p1_make_go.py
- figures/：中文图 PNG + figure_data.csv（批次结束后生成）
- SHA256SUMS.txt / data_manifest.json / upload_receipt.json：字节与远端回读凭据

## 披露

- 本批次只做自适应迎角效率与可复现性评估，不训练 MAML，不产生跨任务泛化结论；P2/P3 未授权。
- 准入证书 scope 为 LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED：同机、非物理验证、非人类签署。
- A5 为 deepseek-flash 单发只读评审，不是人类签署；A5 结论与 Lead GO 是两件事。
- 每个 ≤4 starts 迷你批上传并逐文件回读，回读失败即停。
- 若某设计 3 轮后仍无原始行命中 1e-3，记为 NULL_LABEL/NO_RAW_POINT，按负结果如实报告，不重跑、不放宽容差。
