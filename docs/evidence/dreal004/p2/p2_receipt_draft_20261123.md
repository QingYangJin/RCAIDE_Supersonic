# Issue #14 P2 阶段回执草案（真实 VSPAERO 标签扩充 + 四臂 MAML 公平对照）

状态：DRAFT / NOT POSTED（由 make_p2_receipt.py 生成）；不是 P3/MAML 授权，也不构成 R1 全面 PASS。

## 一、结论摘要

- P2 补采已完成：真实 VSPAERO 启动 16 次（本批上限 16，P2 累计 16/240），完成 16，失败 0，重试 0，并行 1；内部 alpha 求解 case 48 个。
- 本批产出 16 条唯一真实准入标签，NULL 0，行级有效率 100.00%，容差 1e-3 未放宽，全部来自可远端回读的原始 .polar 行。
- 合并 R2/G1/G2 只读复用标签后，数据集为 44 行 / 44 张证书、8 个固定任务、44 条独立标签；K=5 因只有 d00–d03 四个独立 support 槽位判 NOT_ELIGIBLE（不以 query 充数）。
- 四臂对照（FOMAML / 普通联合预训练 / 任务条件预训练 / 随机初始化）在 K=1、3 与种子 7/19/43 上完成；任务条件预训练最好，FOMAML 在 K=3 明显退化（负结果原样保留）。
- 结论仅限 44 行、2 个留出任务（M240/M260）的样本范围，不宣称统计显著或跨任务泛化；P3（BO/DE 预算对照）未授权。

## 二、批次身份与授权链

- run_id：DRECOVER001-P2-20261123-01；batch_id：DRECOVER001-P2-20261123-01-B01；authorization_id：AUTH-DREAL004-P2-20261123-01
- Owner 指令：Issue #14 评论 7103901506（P2 执行指令）；P2 物理上限 240 starts，本批预注册上限 16 starts / 48 internal cases
- 预注册 SHA256：ba2eeb884bd994837181aadd115582d4d87bf51ae45927b5eb07a9984d4dc7f3
- GO 记录 SHA256：aa483aaaab508e6b42563d3605ced47fb6c71c47c540ebe09b4846c894fe6958（绑定预注册、协议卷宗、协议 A5 verdict 与全部 source_code_sha256）
- 协议 A5：P2_PROTOCOL_AND_CODE_REVIEW_PASS（deepseek-flash，2026-11-23T15:22:25Z，非人类签署，human_signature=False）
- 结果 A5：P2_RESULT_REVIEW_PASS（deepseek-flash，2026-11-23T16:38:52Z，非人类签署）

## 三、真实启动与内部成本

| 口径 | 本批 | 上限 | 说明 |
| --- | --- | --- | --- |
| physical_solver_starts_actual | 16 | 16 | 16 个设计 case，每 case 1 次真实启动 |
| physical_solver_starts_completed | 16 | 16 | 全部 SOLVED |
| internal_solver_cases_actual | 48 | 48 | 每 start 3 个局部迎角探针 |
| retries | 0 | 0 | 失败不重跑 |
| admitted_labels | 16 | — | 原始 polar 行升力相对误差 <= 1.4e-4 |
| null_labels | 0 | — | 无 NULL 标签 |

- 求解墙钟合计 29.394 s；停止条件触发：[]

## 四、数据集、切分与去重披露

- 数据集 SHA256：7558f89aa86754f511fd0d61044b49028f9a02a46c0cd1f9a615a65c1e6315f4；行 44，证书 44，excluded 20 条
- 任务族固定：train M140/M160/M200/M202；val M180/M220；test M240/M260（未因算法表现换任务）

| 任务 | split | Mach | support | query | K=3 可行 |
| --- | --- | --- | --- | --- | --- |
| P2-CANON-M140 | train | 1.4 | 3 | 1 | 是 |
| P2-CANON-M160 | train | 1.6 | 4 | 2 | 是 |
| P2-CANON-M180 | val | 1.8 | 4 | 3 | 是 |
| P2-CANON-M200 | train | 2.0 | 3 | 3 | 是 |
| P2-CANON-M202 | train | 2.02 | 4 | 3 | 是 |
| P2-CANON-M220 | val | 2.2 | 3 | 1 | 是 |
| P2-CANON-M240 | test | 2.4 | 3 | 3 | 是 |
| P2-CANON-M260 | test | 2.6 | 3 | 1 | 是 |

- post-GO 数据构建器修复（已披露）：pre_fix 25 行 / excluded 23（sha256 848652cf08c715416bad4f378d8f05b4ef51ce711848ffdfcca2de1e7509b5fe）→ post_fix 44 行 / excluded 20（sha256 7558f89aa86754f511fd0d61044b49028f9a02a46c0cd1f9a615a65c1e6315f4）。
- 新增准入记录 19 条，移除 0 条；逐任务变化见 p2_dataset_diff.json。
- 修复原因（中文）：R2 的低优先级 query 记录与 P2 补采 support 记录落在同一设计上，旧分支把双方同时剔除；修复后只剔除低优先级记录、保留高优先级记录。物理影响：不改变已发生的 16 次真实启动与 16 条标签，只影响样本分配。
- 原始字段：R2 low-priority query records for M180 d02 / M202 d02 conflicted with P2 supplement support records on the same design; the old dedupe branch dropped both sides, the fix drops only the lower-priority record；none: the 16 real starts and 16 admitted labels were already produced before this dataset-builder fix
- K=5：NOT_ELIGIBLE（冻结协议仅 d00–d03 四个独立 support 槽位；禁止 query 充数或重复采样）。

## 五、四臂协议与结果

- 臂：RANDOM_INIT, POOLED_PRETRAIN, TASK_COND_PRETRAIN, FOMAML；K=[1, 3]；种子 [7, 19, 43]；CPU float64
- 容量与预算：隐藏层 [32,32]，最大 60 步，inner_lr 0.05、inner_steps 5、outer_lr 0.01、tasks_per_batch 2；四臂共享同一标签、同一归一化（仅 train 行 23 条拟合）、同一种子与预算
- 归一化参数 SHA256：dd054cdcb76e71350b18f090782c98b7ca931a53d542a3ee8e9036d674203e0a；checkpoint 共 24 个 npz（每臂 × K × 种子），逐文件 SHA 见 p2_training_result.json
- val 只用于选参与早停，test 只评一次；训练过程物理启动 0 次

| 方案 | val MAE (N) | val RMSE (N) | test MAE (N) | test RMSE (N) |
| --- | --- | --- | --- | --- |
| RANDOM_INIT | 21089.0 | 23187.3 | 28509.2 | 30234.8 |
| POOLED_PRETRAIN | 15015.9 | 16197.6 | 25192.8 | 26190.5 |
| TASK_COND_PRETRAIN | 10693.0 | 11786.0 | 8528.9 | 9730.0 |
| FOMAML | 25350.2 | 26713.2 | 40053.8 | 40498.0 |

- 每格为 12 个任务×K×种子组合的平均；逐任务逐种子明细见 p2_arm_metrics.csv，逐 query 预测见 p2_predictions.csv，训练曲线见 p2_training_curves.csv 与 figures/p2_training_curves.png
- 离线候选排序诊断（非在线优化）：按预测最小 Di_N 选设计相对真实最优的遗憾，M180 约 0.67k/0.33k/0/1.8k N，M240 约 1.86k/1.86k/0.87k/1.86k N；M220/M260 各只有 1 个 query，遗憾恒为 0，不可用于比较

## 六、负结果与诊断（不隐藏）

- FOMAML 在 K=3 明显退化：部分种子的外循环损失后段从约 0.22 升到 0.43，K=3 留出 MAE 反而高于随机初始化；本轮 FOMAML 超参数未调（未用 test/val 反调），负结果原样保留。
- 任务条件预训练在所有 split 上最好；普通联合预训练次之；随机初始化居中偏弱。
- 未把 P1 的 196 对 18 内部工况差异记作 MAML 收益；本批未做该比较。
- 不因训练器允许两任务就宣称验收：所有结论限制在 44 行标签、8 任务、2 个留出任务的范围内。

## 七、产物上传与远端独立复核（A4）

- 上传 commit：8833e943e46eea22547942224022753bd85c8838（分支 research/dreal004-alpha-adaptive-meta-sampling，目录 research/concorde_metaopt/optimization_runs/DRECOVER001-P2-20261123-01）
- 文件 380 个，共 18986410 字节；回读 checked=380，missing=[]，bad=[]
- data_manifest SHA256：8f0d1f4b8a1689718ad4b23ce86fc4be6d9d16cda698fd7b8e3e436c09f2073e；SHA256SUMS SHA256：94b4691a8b8f7d400bd09f13de4b4e562e9f84ce801baa241a1820fbbe832fa8
- 说明：A4 独立复核针对数据提交 e4bbfb707307f1e895df0b7e1e135e469245320d；最终提交 8833e943e46eea22547942224022753bd85c8838 只追加 A5 审查产物与数据集 diff，已复核的 raw 字节未改变，最终包回读 380/380 通过。
- 远端独立复核（GitHub blob API 原始字节）：remote head e4bbfb707307f1e895df0b7e1e135e469245320d，复核 case 16 个，通过 16 个，bad=0，A4 判据成立=True
- 复核方法：GitHub blob API raw bytes for remote certificates and polar files; recompute CL/CDi from the raw row at the certified alpha and Di_N = q*Sref*CDi; no local raw file is read
- 每个 case 均校验证书 raw_sha256 等于远端 polar 字节 SHA256，并按证书 alpha 从远端原始行重算 CL/CDi 与 Di_N=q·Sref·CDi 恒等式。

## 八、A5 独立审查范围与边界

- 协议 A5（GO 前）：P2_PROTOCOL_AND_CODE_REVIEW_PASS，审查预注册、补采矩阵、bracket 来源、预算与停止条件；不是人类签署。
- 结果 A5（上传回读后）：P2_RESULT_REVIEW_PASS，gate：{"P2_ACCOUNTING": "PASS", "P2_DATASET_SPLIT": "PASS_WITH_DISCLOSURE", "P2_ARM_FAIRNESS": "PASS", "P2_REMOTE_RETRIEVAL": "PASS", "P2_STATISTICAL_CLAIMS": "PASS", "P2_BOUNDARIES": "PASS"}
- A5 为 deepseek-flash 单发只读审查，非人类签署；不构成 R1 全面 PASS，也不授权 P3/MAML。
- 唯一 minor：post-GO 去重修复已披露并已补逐项 diff；A5 复审 PASS。

## 九、边界与披露

- 标签同机保存（Owner 已豁免异机独立故障域备份）；未做风洞/物理验证；physics_validated=false；fuel_burn_kg=null。
- 目标为同升力（容差 1e-3）下翼面诱导阻力 Di_N=q·Sref·CDi；不含整机阻力/油耗；LF-M2.02 未验证。
- 样本量小（44 行、2 个留出任务）；不宣称统计显著或普遍泛化；不把种子当独立任务。
- P1 仅为单任务 pilot，其 6 次启动未作为 P2 训练样本。
- M140 迎角接近 G2 stage-1 极曲线上界（9.52–9.76°），补采探针已夹紧在 bracket 内；本批 1.0 标签率不构成对其他 Mach 的保证。
- post-GO 代码变更：p2_data.py 去重优先级修复、p2_upload.py 远端校验改为逐层 tree 下钻（规避 recursive tree 截断）、新增 p2_train/p2_figures/p2_metadata/verify_p2_remote 脚本；这些变更不新增物理、不改变已发生的 16 次启动。

## 十、下一门禁与未授权范围

- P2 物理已用 16/240；后续批次需新的预注册 amendment、A5 审查与新 GO，不得沿用本批 GO。
- P3（BO/DE 预算对照、在线优化）未预注册、未审查、未授权；MAML 的 claim 需要更多任务与独立 support/query 才能检验。
- R1 全面 PASS、R2/#11 门禁状态不因本回执改变。

## 附：证据文件 SHA256

- p2_preregistration.json：ba2eeb884bd994837181aadd115582d4d87bf51ae45927b5eb07a9984d4dc7f3
- p2_go_record.json：aa483aaaab508e6b42563d3605ced47fb6c71c47c540ebe09b4846c894fe6958
- p2_supplement_plan.json：208edee0dbc95e27f140ca4211138ee465120b7082c0b4720d893db477179411
- p2_supplement_accounting.json：d789adc4d91a21a7b6cdb3e25e3268b70649d9b5fa0daee75c5ffe1a749aac53
- p2_dataset.json：7558f89aa86754f511fd0d61044b49028f9a02a46c0cd1f9a615a65c1e6315f4
- p2_dataset_diff.json：355efdd2aff45fd159a0bfef6e6cc1085b42a14daa8f9aa25a4c73dd18e90fde
- p2_training_result.json：d76ff35b5d3c28a0b1f32c5582d194fc63a882e6bed3b51c65a9f376cf8ea4dc
- p2_arm_summary.json：20f2307603ac48619ca95aa2e363e0470a55c74d7b4b9c4a293a2ce7bd8f0739
- p2_normalizer.json：dd054cdcb76e71350b18f090782c98b7ca931a53d542a3ee8e9036d674203e0a
- p2_arm_metrics.csv：c720cd180823ffe10abd34a6a43fe61cb82ea02490525c74d03708ec175b2f07
- p2_predictions.csv：eb77ed7a80430ce919bef9187201a4eb2758b90193fce1d3ccc6b52c88c9ca9f
- p2_training_curves.csv：bccebbf8d443c7718d5e1b9515051e5077fa512faaf7a4cb2a64b94550dbc702
- p2_inventory.json：c423f79dc9d9388db3ee42b9758957d80c408029888d60957e332afd015992a2
- a5_protocol_verdict.json：29bc9df40a1f3d3dde87b227b52bc9c61fa1181dbb742548e3c9a931ae2c758d
- a5_result_verdict.json：aa3873ab6e9686aafc36950c4891641de6d20fc1c86c467c98e3b3564bffeeb1
- p2_a5_protocol_dossier.md：6b26bb180b55515fe887e04a30e5136d94f37ff658539e19449fc4bf09f1ca59
- p2_a5_result_dossier.md：7aa878ffe123158798a3c2bf96ea9d90abd2e6dbcf9c63cf0dded1294069a245
- p2_remote_retrieval_audit.json：7761245f60ba0ee61c474627b8fa743acca0cccd722bce13d16da78516a1d879
- p2_upload_receipt.json：1779f94c123b22c4a0904575ed059aff83479884964db2d0ece3529ffb5a9a6f
