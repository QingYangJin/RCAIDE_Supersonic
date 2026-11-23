# P2 结果卷宗（Issue #14：真实 VSPAERO 标签 + 四臂 MAML 公平对照）

本卷宗用于 A5 对 P2 结果、账本与产物做独立只读复审；不是人类签署，不授权 P3，也不改变任何历史结论。

## 0. 文件身份
- p2_preregistration.json: ba2eeb884bd994837181aadd115582d4d87bf51ae45927b5eb07a9984d4dc7f3
- p2_go_record.json: aa483aaaab508e6b42563d3605ced47fb6c71c47c540ebe09b4846c894fe6958
- a5_review/verdict.json: 29bc9df40a1f3d3dde87b227b52bc9c61fa1181dbb742548e3c9a931ae2c758d
- p2_supplement_plan.json: 208edee0dbc95e27f140ca4211138ee465120b7082c0b4720d893db477179411
- p2_supplement_accounting.json: d789adc4d91a21a7b6cdb3e25e3268b70649d9b5fa0daee75c5ffe1a749aac53
- p2_dataset/p2_dataset.json: 7558f89aa86754f511fd0d61044b49028f9a02a46c0cd1f9a615a65c1e6315f4
- p2_dataset/p2_dataset_diff.json: 355efdd2aff45fd159a0bfef6e6cc1085b42a14daa8f9aa25a4c73dd18e90fde
- tables/p2_arm_metrics.csv: c720cd180823ffe10abd34a6a43fe61cb82ea02490525c74d03708ec175b2f07
- tables/p2_predictions.csv: eb77ed7a80430ce919bef9187201a4eb2758b90193fce1d3ccc6b52c88c9ca9f
- tables/p2_training_curves.csv: bccebbf8d443c7718d5e1b9515051e5077fa512faaf7a4cb2a64b94550dbc702
- training/p2_training_result.json: d76ff35b5d3c28a0b1f32c5582d194fc63a882e6bed3b51c65a9f376cf8ea4dc
- training/p2_arm_summary.json: 20f2307603ac48619ca95aa2e363e0470a55c74d7b4b9c4a293a2ce7bd8f0739
- training/p2_normalizer.json: dd054cdcb76e71350b18f090782c98b7ca931a53d542a3ee8e9036d674203e0a
- upload_receipt.json: 2ae6b94406ee43b464c112724d3beed3301fb5bdf4ed5dd02147fb85340f99b7
- remote_retrieval/p2_remote_retrieval_audit.json: 7761245f60ba0ee61c474627b8fa743acca0cccd722bce13d16da78516a1d879

## 1. 批次身份与授权链
- run_id: DRECOVER001-P2-20261123-01；batch_id: DRECOVER001-P2-20261123-01-B01；authorization_id: AUTH-DREAL004-P2-20261123-01
- Owner 指令：Issue #14 comment 7103901506（P2 执行指令）；m10841 要求执行；P2 物理上限 240 starts
- 预注册 sha256: ba2eeb884bd994837181aadd115582d4d87bf51ae45927b5eb07a9984d4dc7f3
- GO sha256: aa483aaaab508e6b42563d3605ced47fb6c71c47c540ebe09b4846c894fe6958；GO 绑定预注册、卷宗、协议 verdict 与全部 source_code_sha256
- 协议 A5 verdict: P2_PROTOCOL_AND_CODE_REVIEW_PASS（deepseek-flash，非人类签署，human_signature=False）
- 补采前数据：旧批次复用 25 条准入标签（R2/G1/G2），8 任务中 3 个任务为零标签；补采 16 starts 后 44 行/44 证书

## 2. 真实启动与内部成本（本次补采批次）
- 真实 design starts: 16 / 上限 16（P2 累计 16/240）；完成 16；失败 0；重试 0；并行 1
- 内部 alpha solver cases: 48 / 上限 48（每 start 3 个局部迎角探针）
- 准入标签 16；NULL 0；行级有效率 1.0；总求解墙钟 29.394 s；停止条件 []
- 本批次解密：16 个 case 全部 SOLVED 且原始 polar 行升力相对误差 <= 1.4e-4（容差 1e-3 未放宽）

## 3. 数据集与切分（44 行 / 44 证书）
- 任务族：train M140/M160/M200/M202；val M180/M220；test M240/M260（训练/验证/留出按 Owner 指令固定，未因算法表现换任务）
- 每任务 support/query 行：
  - P2-CANON-M140（train，Mach 1.4）：support 3 / query 1；K=3 可行=True
  - P2-CANON-M160（train，Mach 1.6）：support 4 / query 2；K=3 可行=True
  - P2-CANON-M180（val，Mach 1.8）：support 4 / query 3；K=3 可行=True
  - P2-CANON-M200（train，Mach 2.0）：support 3 / query 3；K=3 可行=True
  - P2-CANON-M202（train，Mach 2.02）：support 4 / query 3；K=3 可行=True
  - P2-CANON-M220（val，Mach 2.2）：support 3 / query 1；K=3 可行=True
  - P2-CANON-M240（test，Mach 2.4）：support 3 / query 3；K=3 可行=True
  - P2-CANON-M260（test，Mach 2.6）：support 3 / query 1；K=3 可行=True
- 数据来源：R2/G1/G2 旧案例只读复用 + P2 补采 16 个案例；历史 task_id 通过显式别名表映射到 8 个 canonical 任务，历史证书/原始文件未被改写
- 去重与冲突：excluded=20 条（同设计重复、低优先级冲突被高优先级批次取代、同优先级 support/query 冲突整条丢弃）
- 关键披露（post-GO 数据构建器修复）：首次重建时 2 条 R2 低优先级 query 记录与 P2 补采 support 记录在“同设计不同分区”分支被误判为不可解冲突并同时剔除，导致 M180/M202 各少 1 条 support（39 行、K=3 不可行）；修复为“低优先级冲突只剔除低优先级记录”后重建为 44 行，M180/M202 恢复 3+ support。该修复只影响样本分配，不改变已发生的 16 次物理启动与 16 条标签；修复前后数据集 SHA 与行数差异见下。
- 修复前后逐项差异（p2_dataset/p2_dataset_diff.json，sha256 355efdd2aff45fd159a0bfef6e6cc1085b42a14daa8f9aa25a4c73dd18e90fde）：
  - pre_fix: git b402db4:research/concorde_metaopt/optimization_runs/DRECOVER001-P2-20261123-01/p2_dataset/p2_dataset.json，sha256 848652cf08c715416bad4f378d8f05b4ef51ce711848ffdfcca2de1e7509b5fe，rows 25，certificates 25，excluded 23
  - post_fix: sha256 7558f89aa86754f511fd0d61044b49028f9a02a46c0cd1f9a615a65c1e6315f4，rows 44，certificates 44，excluded 20
  - 新增准入记录 19 条：g2-adm-g2-m160-d02-support-s2, g2b02-adm-g2-m180-d03-support-s2, g2b02-adm-g2-m202-d03-support-s2, p2-adm-p2-m140-d00, p2-adm-p2-m140-d01, p2-adm-p2-m140-d02, p2-adm-p2-m140-d03, p2-adm-p2-m180-d02, p2-adm-p2-m202-d02, p2-adm-p2-m220-d00, p2-adm-p2-m220-d01, p2-adm-p2-m220-d02, p2-adm-p2-m220-d03, p2-adm-p2-m240-d01, p2-adm-p2-m240-d03, p2-adm-p2-m260-d00, p2-adm-p2-m260-d01, p2-adm-p2-m260-d02, p2-adm-p2-m260-d03
  - 移除准入记录 0 条
  - P2-CANON-M140（train）：support None -> 3；query None -> 1
  - P2-CANON-M160（train）：support 3 -> 4；query 2 -> 2
  - P2-CANON-M180（val）：support 2 -> 4；query 3 -> 3
  - P2-CANON-M202（train）：support 2 -> 4；query 3 -> 3
  - P2-CANON-M220（val）：support None -> 3；query None -> 1
  - P2-CANON-M240（test）：support 1 -> 3；query 3 -> 3
  - P2-CANON-M260（test）：support None -> 3；query None -> 1
- 修复原因：R2 low-priority query records for M180 d02 / M202 d02 conflicted with P2 supplement support records on the same design; the old dedupe branch dropped both sides, the fix drops only the lower-priority record；物理影响：none: the 16 real starts and 16 admitted labels were already produced before this dataset-builder fix
- 数据集合规：K=5 为 NOT_ELIGIBLE（冻结协议仅 d00–d03 四个独立 support 槽位；禁止 query 充数或重复采样）

## 4. 四臂训练协议
- 臂：RANDOM_INIT, POOLED_PRETRAIN, TASK_COND_PRETRAIN, FOMAML；K 值 [1, 3]；种子 [7, 19, 43]；CPU float64
- 网络容量：隐藏层 [32, 32]（条件模型输入 16D 条件特征，其余 12D 设计向量）；最大 60 步；inner_lr 0.05、inner_steps 5、outer_lr 0.01、tasks_per_batch 2
- 归一化：x/y 统计只用 train split 行（fit_observation_ids 共 23 条，全部为 train 任务）；val 只用于早停/选择；test 只评一次
- checkpoint：24 个 npz（每臂 × K × 种子），归一化参数 sha256 dd054cdcb76e71350b18f090782c98b7ca931a53d542a3ee8e9036d674203e0a
- 训练脚本不启动任何物理求解器（physical_solver_starts=0）

## 5. 结果（MAE/RMSE，N；逐任务逐种子平均）
- RANDOM_INIT / val：MAE 21089.0 N，RMSE 23187.3 N（n=12 任务×K×种子）
- RANDOM_INIT / test：MAE 28509.2 N，RMSE 30234.8 N（n=12 任务×K×种子）
- POOLED_PRETRAIN / val：MAE 15015.9 N，RMSE 16197.6 N（n=12 任务×K×种子）
- POOLED_PRETRAIN / test：MAE 25192.8 N，RMSE 26190.5 N（n=12 任务×K×种子）
- TASK_COND_PRETRAIN / val：MAE 10693.0 N，RMSE 11786.0 N（n=12 任务×K×种子）
- TASK_COND_PRETRAIN / test：MAE 8528.9 N，RMSE 9730.0 N（n=12 任务×K×种子）
- FOMAML / val：MAE 25350.2 N，RMSE 26713.2 N（n=12 任务×K×种子）
- FOMAML / test：MAE 40053.8 N，RMSE 40498.0 N（n=12 任务×K×种子）
- 逐任务逐种子明细见 tables/p2_arm_metrics.csv；逐 query 预测见 tables/p2_predictions.csv；训练曲线见 tables/p2_training_curves.csv 与 figures/p2_training_curves.png

## 6. 负结果与诊断（不隐藏）
- FOMAML 在 K=3 明显退化：外循环损失在部分种子的后段从约 0.22 升到 0.43，K=3 的留出 MAE 反而高于随机初始化；本轮 FOMAML 超参数未调（未用 test/val 反调），该负结果按原样保留
- 任务条件预训练在所有 split 上最好；普通联合预训练次之；随机初始化居中偏弱
- 离线候选排序诊断（training/p2_offline_selection.json）：按预测最小 Di_N 选设计的遗憾在 M180/M240 可计算，M220/M260 只有 1 个 query，遗憾恒为 0；该诊断不是在线优化，也不是 P3 的 BO/DE 对比
- 不得把 P1 的 196 对 18 内部工况差异记作 MAML 收益；本卷宗未做该比较

## 7. 产物上传与远端回读（A4）
- 上传 commit: e4bbfb707307f1e895df0b7e1e135e469245320d；文件 373，字节 18912176；readback checked=373，missing=[]，bad=[]
- 远端独立复核（GitHub blob API 原始字节）：remote head e4bbfb707307f1e895df0b7e1e135e469245320d，case 目录 16，逐 case 通过 16，bad=0，A4 判据=True
- 复核方法：GitHub blob API raw bytes for remote certificates and polar files; recompute CL/CDi from the raw row at the certified alpha and Di_N = q*Sref*CDi; no local raw file is read
- 每条标签均从远端 .polar 原始行按证书 alpha 重算 CL/CDi 并验证 Di_N = q·Sref·CDi 恒等式；同时验证证书 raw_sha256 等于远端 polar 字节 SHA256

## 8. 已披露偏差与限制
- A5 为 deepseek-flash 单发只读审查，非人类签署；本卷宗不请求也不构成 P3/MAML 授权
- 标签同机保存（Owner 已豁免异机独立故障域备份）；未做风洞/物理验证；physics_validated=false；fuel_burn_kg=null
- 目标为同升力（tol 1e-3）下翼面诱导阻力 Di_N=q·Sref·CDi；不含整机阻力/油耗；LF-M2.02 未验证
- 样本量小（44 行、2 个留出任务）；不宣称统计显著或普遍泛化；不把种子当独立任务
- post-GO 代码变更已披露：p2_data.py 去重优先级修复、p2_upload.py 远端校验改为逐层 tree 下钻（修复 recursive tree 截断）、新增 p2_train/p2_figures/p2_metadata/verify_p2_remote 脚本；这些变更不新增物理、不改变已发生的 16 次启动
- M140 迎角接近 G2 stage-1 极曲线上界（9.52–9.76°），补采探针已夹紧在 bracket 内；该批次 1.0 标签率不构成对其它 Mach 的保证
- P1 仅为单任务 pilot，不作为正式训练批；P2 未使用 P1 的 6 次启动作为训练样本

## 9. 请 A5 判断的关键点
1. 账本是否自洽：16 starts / 16 completed / 48 internal / 16 标签 / 0 NULL / 0 retry
2. 数据切分与去重是否可接受：44 行、8 任务、support/query 无泄漏、K=5 NOT_ELIGIBLE、post-GO 去重修复是否披露充分
3. 四臂对照是否公平：同一标签、同一归一化（仅 train 拟合）、同一容量/预算/种子、未用 test 调参
4. 远端回读与独立复算是否支撑 A4
5. 结果与负结果（FOMAML 退化）是否被如实报告，统计主张是否被限制在样本范围内
6. 是否放行 P2 结果（本卷宗不请求 P3 GO；P3 需另行预注册与新的 GO）
