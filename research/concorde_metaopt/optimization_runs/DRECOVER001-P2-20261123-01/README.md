# DRECOVER001-P2-20261123-01（Issue #14 P2：真实 VSPAERO 标签 + MAML 四臂公平对照）

本目录是 Issue #14「P2 执行指令」的运行产物，不是 P3，也不构成任何新的物理授权。

## 1. 物理开销（真实 VSPAERO）
- 补采 16 次真实 solver 启动，16/16 完成，0 失败、0 重试，并行 1，墙钟 29.394 s。
- 内部迎角工况 48 个（每 start 3 个局部 alpha 探针），上限 48。
- 16 条准入标签（valid label rate 1.0），0 个 NULL。
- 原始 deck/polar/history/日志、准入证书、账本、上传回执全部在本仓库，可从 GitHub 实际回读。

## 2. 数据切分
- train：M140、M160、M200、M202；val：M180、M220；test：M240、M260。
- 可用独立 support/query 行见 task_family_split.json 与 p2_dataset/p2_dataset.json（44 行、44 张证书）。
- 仅训练集行用于归一化；验证集只用于早停/选择；留出测试集只评一次。
- K=1 与 K=3 实际运行；K=5 为 NOT_ELIGIBLE（冻结协议只有 d00-d03 四个独立 support 槽位，禁止用 query 充数）。

## 3. 四臂与结果（CPU float64，种子 7/19/43）
- 随机初始化、普通联合预训练、任务条件预训练、FOMAML；逐任务逐种子指标见 tables/p2_arm_metrics.csv、tables/p2_predictions.csv、tables/p2_training_curves.csv。
- 每个模型 checkpoint（npz）与归一化参数在 training/checkpoints/、training/p2_normalizer.json，SHA256 见 training/p2_training_result.json。
- 结论以实测为准，包含负结果：本轮任务条件预训练最好，FOMAML 在 K=3 明显退化（外循环损失在部分种子后期上升），未按测试集调参。
- 离线候选排序诊断见 training/p2_offline_selection.json（不是在线优化，也不是 P3 的 BO/DE 对比）。

## 4. 边界与披露
- A5 审查为 deepseek-flash 只读上下文，非人类签名；审查范围仅为协议、代码与产物，不等同 R1 全部代码 PASS。
- 标签同机保存（Owner 已豁免异机独立故障域备份要求）；无风洞/物理验证，physics_validated=false。
- 目标定义：同升力（相对容差 1e-3）下的翼面诱导阻力 Di_N = q * Sref * CDi；不含整机阻力或油耗，fuel_burn_kg=null。
- P1 的 196 对 18 内部工况差异不得记作 MAML 收益。
- P3 需另行预注册、A5 审查与新的 Lead GO。
