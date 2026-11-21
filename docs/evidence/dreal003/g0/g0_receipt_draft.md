# [D-REAL-EXP-001][G0 回执] 旧 24 次真实原件全量上传、A1 per-case 修复、A5 复审 G0_APPROVE

> 性质：G0 阶段回执；不是 G1 授权，不是物理外部验收。G1 仍未预注册、未下发 GO。
> physical_solver_starts_actual_new=0；本轮只上传历史原件与修复代码。

## 0. 结论

- 旧 24 次真实 VSPAERO 的 1,345 个原始文件已全部上传到版本化目录，并生成逐文件映射与 SHA256SUMS；全新浅克隆按 commit 逐字节复核 1,345/1,345 通过。
- A1 已修复 build_evaluation 的全局 Mach/q 缺陷，改为 per-case 读取并做 q 一致性校验；253 项零物理测试全绿。
- A5 独立复审（deepseek-flash，只读，非人类签名）：verdict=G0_APPROVE；G0_CODE_PASS=PASS_WITH_DISCLOSURE；G0_REMOTE_RAW_RETRIEVAL_PASS=PASS_WITH_DISCLOSURE。
- 旧 9 条标签是 pre-A1 历史标签，未回写、未重标；A1 精确升力插值造成的 5.56e-4 偏移已披露。
- 新增真实物理 0；G1/G2/G3 均未授权。

## 1. 旧 24 次文件存活与上传

- 原始目录：D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/；1,345 个文件；209,935,206 字节。
- 24 个 case 目录全部存活；23 个完成并产出 case_result；1 个中断（m240-d01-support）无 case_result、无证书。
- 最终数据 commit：bd8fa4a1f99627e184ea09e233955fa629dae727；tree：953025e507a89c8924485b214bfdd3d46c0f2980；parent：e71e25e9045a7be98e54aed0feac86e91f9a5374。
- 上传：1,384 个文件 / 211,456,790 字节 = 1,345 原始 + 36 curated + mapping + README + SHA256SUMS。
- 证据与 A5 结论 commit：9619d342441d57c44fc116047a270aedb5abcd87。

链接（固定在 bd8fa4a）：

- 目录：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/bd8fa4a1f99627e184ea09e233955fa629dae727/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01
- SHA256SUMS：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/bd8fa4a1f99627e184ea09e233955fa629dae727/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/SHA256SUMS.txt
- 逐文件映射：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/bd8fa4a1f99627e184ea09e233955fa629dae727/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/metadata/upload_file_mapping.json
- admitted_labels.csv：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/bd8fa4a1f99627e184ea09e233955fa629dae727/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/tables/admitted_labels.csv
- all_evaluations.csv：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/bd8fa4a1f99627e184ea09e233955fa629dae727/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/tables/all_evaluations.csv
- failed_or_null.csv：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/bd8fa4a1f99627e184ea09e233955fa629dae727/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/tables/failed_or_null.csv
- G0 回读审计：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/9619d342441d57c44fc116047a270aedb5abcd87/docs/evidence/dreal003/g0/g0_full_remote_retrieval.json

计数差异说明：首次上传 commit 1f0bdd5 为 1,274 个（.gitignore 漏 58 个 *.log 与 13 个 *.build.log）；28f4c5f 补 13 个 build.log 至 1,287；e71e25e 起上传原始 root 全部文件。早期清单记 1,344 / 209,926,588，是因为 g0_survival_inventory.json 在统计后写入自身（8,618 字节），含自身为 1,345 / 209,935,206。

## 2. Mach/q 修复与全量测试

修改文件：research/concorde_metaopt/dreal001/geometry/solver_runner.py
SHA256：cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3

- 新增 _read_optional_json(path: Path) 与 _case_flow_conditions(cwd, basename, geometry_sref_m2=None)。
- 优先级：case/task_spec.json → case_inputs.json 的 sweep_input_readback.inputs_double → 全局 TASK_SPEC。
- q 与 0.5*rho*Vinf^2 相对差 > 1e-6*max(1,q) 时抛 PreflightError("case flow conditions disagree with q from case task spec")，不静默使用全局值。
- build_evaluation 改用 per-case sref/q/lift/mach/rho/vinf 计算同升力 Di_N=q*Sref*CDi。
- 真实 24 case 解析：M160 q=12851.40843975621；M180 q=16265.063806566453；M202 q=20483.940233430174；M220 q=24297.194081414087；M240 q=28915.66898945147。

测试：research/concorde_metaopt/tests/test_recovery_solver_runner.py 新增 5 项；零物理 preflight run_id=DRECOVER001-SOFTWARE-20261120T121100Z，253 tests，0 failed / 0 error / 0 skipped，physical=0。

修复效果：23 个 case 有 evaluation；6 个由 CL_TARGET_OUTSIDE_POLAR 变为 LIFT_MATCHED_BY_INTERPOLATION（m160-d00-support-r1、m160-d02-query-r1、m180-d00-support-r1、m180-d02-query-r1、m240-d00-support-r1、m240-d02-query-r1）；12 个仍 outside，保持 NULL_LABEL；其余 5 个保持原状态。新增物理 0。

## 3. 远端全量回读与账本核对

- 方法：全新浅克隆远端分支 research/dreal003-expanded-aero-meta-20261120，固定 commit bd8fa4a；逐文件读取 blob 与 upload_file_mapping.json 比较字节数和 SHA256。
- 结果：1,345/1,345 通过，bad=0；上传树 1,384 文件；mapping SHA256 fd93d194a2104b45f057dc249a8531774bf039e3b550d817dba9defa6e68f707。
- 失败 case m240-d01-support 的 case_result 与 admission_certificate 在远端 404，与其无标签一致；本地目录仍有 31 个原始文件。
- 账本：24 starts、645 internal、0 retries；23 完成、1 超时；10 张证书；去重后 9 条标签；14 条 null/failed。
- 645 分解：pilot 23 + 13 个完成 matrix case ×15 + 7 个 B01R repair case ×61 = 645；中断 case 内部数未知，不计入 645。
- 14 条 null/failed 只统计 23 个完成 case 中的 14 个；中断 m240-d01 不在 14 内，单独为第 15 个非标签 start。
- 重复证书：同一 task/design 出现两次（ADM-R2-B01-BASELINE-ADMIT-01 与 ADM-R2-B01-BASELINE-REFINE-01）；CSV 按唯一 (task_id,design_sha256) 去重保留 admit，refine 不重复计数。

## 4. A5 结论

- reviewer：deepseek-flash；review_type：independent_subagent_single_shot_read_only_dossier_reexamination；human_signature=false。
- reviewed_utc：2026-11-20T13:39:22Z。
- verdict：G0_APPROVE。
- G0_CODE_PASS：PASS_WITH_DISCLOSURE。
- G0_REMOTE_RAW_RETRIEVAL_PASS：PASS_WITH_DISCLOSURE。
- A5 判据：A1 有完整 diff 与 253 测试原始日志；1,345 原件全量克隆复核通过；645 已对账；7 文件与全量回读均给出 URL/SHA；A3 自审不作为独立证据；重复证书已解释；每 case Sref/lift 已列表。
- A5 保留披露：253 测试与文件 SHA 是自报；全量复核只对 bd8fa4a 成立；m240-d01 内部 case 数未知；旧标签 pre-A1；同机存储；36 个 curated 副本不是原件。A5 复审结论文件在 docs/evidence/dreal003/g0/a5_g0_review_verdict.json。

## 5. Di_N 重算与旧标签偏移

m160-d00-support-r1 证书：di_n=175533.59122875682；q=12851.40843975621；Sref=358.25；CDi=0.038126181642；CL=0.289604495511；alpha=7.47。

- 在 alpha=7.47 重算 di=175533.59122875682，与证书逐位一致。
- A1 精确升力插值到 lift_target=1,333,704.4 N：alpha=7.472104416484619，CDi=0.038147364348580154，di=175631.11677151572，相对差 5.56e-4。
- 结论：证书恒等式成立；旧标签是 pre-A1 历史标签，不静默替换、不重标；A1 结果只用于后续批次。

## 6. G1 第一批预注册草案（未授权）

- 新 authorization_id：AUTH-DREAL003-G1-20261121-01（草案）。
- 新 batch_id：DRECOVER001-G1-20261121-01（草案）。
- 上限：24 真实 starts；每 mini-batch ≤8 starts 或 ≤60 分钟；parallel=1；单 case 超时 600s；0 重试；每 mini-batch 上传并回读后才放行下一批。
- 目标：有效标签率 ≥70%；不足则停止扩容并报告根因。
- 布点：围绕 M160/M180/M202/M220/M240 的迎角 bracket；先 pilot 成功/失败各 1，再放量；异常/未匹配升力保持 NULL_LABEL。
- 前置条件：A5 对 G1 合同与确切代码 SHA 复审；Lead 另发 GO。当前 NO_PHYSICAL_GO。

## 7. G2 split 冻结草案（未冻结、未授权）

- 目标 ≥8 个物理不同任务：≥4 train、≥2 val、≥2 heldout test；每任务 8–10 个去重真实设计；K=1/3/5，多 query。
- 草案槽位：M160@CL017、M180@CL017、M202@CL017、M220@CL017（train）；M240@CL017、M202@CL019（val）；M160@CL019、M240@CL019（test）。
- 以上是槽位草案；必须先验证求解器适用域、生成合法 deck、冻结 task_id/geometry_sha256 后才算 split。G2 容量 ≤240 starts。

## 8. 声明

- 本轮新增真实物理 0；上传的是历史原件，不是新计算。
- 旧标签为 LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED，同机保存；异机备份由 Owner 豁免。
- 无 G1/G2/G3 授权；不声称泛化、不声称物理验证、不声称整机燃油优化。
- A5 是 deepseek-flash 独立单发只读审查，不是人类签名。
