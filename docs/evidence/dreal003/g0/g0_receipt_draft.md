# [D-REAL-EXP-001][G0 回执] 旧 24 次真实原件已上传、A1 per-case 修复完成、远端回读通过

> 性质：G0 阶段回执；不是 G1 授权，不是物理外部验收。G1 仍未预注册、未下发 GO。
> physical_solver_starts_actual_new=0。

## 0. 结论

- 旧 24 次真实 VSPAERO 原件已实际上传到版本化目录，可从 GitHub 按 commit 下载；不是 LFS 指针、不是本地路径、不是只有哈希。
- A1 已修复 build_evaluation 的全局 Mach/q 缺陷，改为 per-case 读取并做 q 一致性校验；253 项零物理测试全绿。
- A3 内审通过；A5 独立审查结论见第 4 节。G0 门禁结论以 A5 为准。
- 旧 9 条标签是 pre-A1 历史标签，未回写、未重标；A1 精确升力插值造成的 5.56e-4 偏移已披露。

## 1. 旧 24 次文件是否存活、何时上传

- 工作机原始目录：D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/，1,345 个文件，209,926,588 字节。
- 24 个 case 目录全部存活；23 个完成并产出 case_result，1 个中断（m240-d01-support）无 case_result、无证书。
- 上传目录：research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/
- 最终 commit：28f4c5f15cd3eb99dda0fc52f0497019f632959e；tree：041025ebf24e783005f2f4c44b49328368cb5549；parent：1f0bdd53af38e58f5e16394fc7e1c4cc2ee866f7。
- 上传文件：1,287 个（含 README.md、SHA256SUMS.txt），209,789,363 字节。
- 覆盖：24 个 case 的 .vsp3/.vspgeom/.vspaero/.polar/.history/.lod/.adb/.csf/.dat、stdout/stderr、case_result、证书、审计、plan、evaluations；另含 13 个 *.build.log、batch_accounting、real_dataset_manifest、null_labels、r2_gate_record、A5 旧结论、训练结果与图表。
- 首次提交 1f0bdd5 漏了 13 个顶层 *.build.log；最终提交 28f4c5f 已补齐，并在 upload_receipt.json 记录该历史。

可打开链接：

- 目录：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/28f4c5f15cd3eb99dda0fc52f0497019f632959e/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01
- SHA256SUMS：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/28f4c5f15cd3eb99dda0fc52f0497019f632959e/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/SHA256SUMS.txt
- data_manifest：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/28f4c5f15cd3eb99dda0fc52f0497019f632959e/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/metadata/data_manifest.json
- admitted_labels.csv：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/28f4c5f15cd3eb99dda0fc52f0497019f632959e/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/tables/admitted_labels.csv
- all_evaluations.csv：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/28f4c5f15cd3eb99dda0fc52f0497019f632959e/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/tables/all_evaluations.csv
- failed_or_null.csv：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/28f4c5f15cd3eb99dda0fc52f0497019f632959e/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/tables/failed_or_null.csv

## 2. Mach/q 修复与全量测试

修改文件：research/concorde_metaopt/dreal001/geometry/solver_runner.py
SHA256：cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3

- 新增 _read_optional_json(path: Path) 与 _case_flow_conditions(cwd, basename, geometry_sref_m2=None)。
- 优先级：case/task_spec.json → case_inputs.json 的 sweep_input_readback.inputs_double → 全局 TASK_SPEC。
- q 与 0.5*rho*Vinf^2 相对差 > 1e-6*max(1,q) 时抛 PreflightError("case flow conditions disagree with q from case task spec")，不静默使用全局值。
- build_evaluation 改用 per-case sref/q/lift/mach/rho/vinf 计算同升力 Di_N=q*Sref*CDi。

真实 24 case 解析结果：M160 q=12851.40843975621；M180 q=16265.063806566453；M202 q=20483.940233430174；M220 q=24297.194081414087；M240 q=28915.66898945147。

测试：research/concorde_metaopt/tests/test_recovery_solver_runner.py 新增 5 项；G0 分支零物理 preflight run_id=DRECOVER001-SOFTWARE-20261120T121100Z，253 tests，0 failed / 0 error / 0 skipped，physical_solver_starts_actual=0。

修复效果（只读重算，不改历史 raw）：24 个 case 中 23 个有 evaluation；6 个由 CL_TARGET_OUTSIDE_POLAR 变为 LIFT_MATCHED_BY_INTERPOLATION（m160-d00-support-r1、m160-d02-query-r1、m180-d00-support-r1、m180-d02-query-r1、m240-d00-support-r1、m240-d02-query-r1）；12 个仍 outside，保持 NULL_LABEL；新增物理 0。

## 3. 远端空目录下载与账本核对

- 从空目录 D:/RCAIDE/.recovery-local-restore/g0_download/ 按精确 commit 回读 7 个文件：成功 case m160-d00-support-r1 的 task_spec、case_inputs、case_result、admission_certificate、polar；失败 case m240-d01-support 的 task_spec、vspaero。
- 7/7 与工作树逐字节 SHA256 相同，mismatch=[]。
- 失败 case 的 case_result.json 与 admission_certificate.json 远端均 404，与其“中断、无标签”一致；本地目录仍有 31 个原始文件。
- 账本：24 starts、645 internal、0 retries；23 完成、1 超时；10 张证书；去重后 9 条可用标签；14 条 null/failed。
- 重复证书身份：同一 task concorde-fixed-cruise-dreal001-real-v1、同一 design 937aa7c9… 出现两次（ADM-R2-B01-BASELINE-ADMIT-01 与 ADM-R2-B01-BASELINE-REFINE-01）；去重后 9 条标签，不隐藏。
- 远端文件数 1,287、总字节 209,789,363；本地 tree 与远端 tree 一致（041025eb…）。

## 4. A5 结论

[A5_VERDICT_PLACEHOLDER]

## 5. Di_N 重算与旧标签偏移

m160-d00-support-r1 证书记录：di_n=175533.59122875682；q=12851.40843975621；Sref=358.25；CDi=0.038126181642；CL=0.289604495511；alpha=7.47。

- 在 alpha=7.47 重算：di=175533.59122875682，与证书逐位一致。
- A1 精确升力插值到 lift_target=1,333,704.4 N：alpha=7.472104416484619，CDi=0.038147364348580154，di=175631.11677151572，相对差 5.56e-4。
- 结论：证书自身恒等式成立；旧标签是 pre-A1 历史标签，不静默替换、不重标；A1 结果只用于后续批次。

## 6. G1 第一批预注册草案（未授权）

- 新 authorization_id：AUTH-DREAL003-G1-20261121-01（草案，尚未签发）。
- 新 batch_id：DRECOVER001-G1-20261121-01（草案）。
- 上限：24 真实 starts；每 mini-batch ≤8 starts 或 ≤60 分钟；parallel=1；单 case 超时 600s；0 重试；每 mini-batch 上传并回读后才放行下一批。
- 目标：有效标签率 ≥70%；不足则停止扩容、报告根因。阈值只是改善目标，不是物理外部验收。
- 布点：围绕 M160/M180/M202/M220/M240 的迎角 bracket，先做 1 个成功/失败各 1 的 pilot，再放量；异常/未匹配升力保持 NULL_LABEL。
- 前置条件：A5 对 G1 合同与确切代码 SHA 复审通过；Lead 另发 GO。当前 NO_PHYSICAL_GO。

## 7. G2 split 冻结草案（未冻结、未授权）

- 目标 ≥8 个物理不同任务：≥4 train、≥2 val、≥2 heldout test；每任务 8–10 个去重真实设计；K=1/3/5，多 query。
- 草案槽位：M160@CL017、M180@CL017、M202@CL017、M220@CL017（train）；M240@CL017、M202@CL019（val）；M160@CL019、M240@CL019（test）。
- 以上是槽位草案，不是已存在任务；必须先验证求解器适用域、生成合法 deck、冻结 task_id/geometry_sha256 后才算 split。G2 容量 ≤240 starts，按 G1 有效率调整。

## 8. 声明

- 本轮新增真实物理 0；上传的是历史原件，不是新计算。
- 旧标签为 LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED，同机保存；异机备份由 Owner 豁免。
- 无 G1/G2/G3 授权；不声称泛化、不声称物理验证、不声称整机燃油优化。
- A5 是 deepseek-flash 独立单发只读审查，不是人类签名。
