# D-RECOVER-001 R2 真实标签与 K=1 FOMAML 实验（2026-11-20）

状态：**探索性真实训练已执行，未宣称泛化**。本文件不授予新预算，也不替代 A5 审查。

## 1. 真实数据

- run_id：\`DRECOVER001-R2-20261120-01\`
- batch：\`DRECOVER001-R2-20261120-01-B01\`（17 starts）+ \`...-B01R\`（7 starts）
- 真实求解器启动：**24 / 24**（含 1 次被外层超时中断的 \`m240-d01-support\`，计费但不重跑）
- 完成：23；内部求解 case：645；retries：0；并行：1
- 准入证书：**10**；可组成无重复 design 的数据集：**9 行**
  - 10 张证书中 \`baseline-refine-01\` 与 \`baseline-admit-01\` 同为 M202 d00，重复 design 被 \`MetaDataset\` 排除。
- 4 个任务：M160 train（Mach 1.6，q 12851.408）、M202 train（Mach 2.02，q 20483.940）、M180 val（Mach 1.8，q 16265.064）、M240 test（Mach 2.4，q 28915.669）。
- 证据级别：\`LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED\`；审计是本地独立复算脚本，不是人类或 A5 签名。
- 数据集 SHA256：\`c63ccb0a7becd3dd7f558b9de7c61efa280c75bc1d385ea96492d631fccbab8b\`。

## 2. 模型与训练

- 入口：\`research/concorde_metaopt/dreal001/meta/real_training.py\`
  - \`RealFOMALMTrainer.fit(dataset, config=..., max_steps=20, support_per_task=1)\`
  - \`RealAdaptationRunner.predict(...)\`
- 配置：12D→32→32→1，first-order FOMAML，inner_lr 0.05，inner_steps 5，outer_lr 0.01，tasks_per_batch 2，K=1，seed 7，20 outer steps。
- 训练任务：M160、M202（各 1 support，1 query）。val M180、test M240 各 1 support、1 query。
- 状态：\`REAL_META_TRAINING_EXECUTED\`；\`real_meta_training_executed=true\`；\`physical_solver_starts_actual=0\`。
- 最终参数 SHA256：\`a75073640aefb5bd9fc6b8fce11fdcd7fea5efff45bd7fe34f140602f9001abb\`。

## 3. 结果（单次探索，n=1 query/task）

| 任务 | 划分 | adapted Di_N | 真值 Di_N | 绝对误差 | 相对误差 | MSE |
|---|---|---|---:|---:|---:|---:|
| M180 | val | 159,539.48 | 145,594.17 | 13,945.31 | 9.58% | 1.945e8 |
| M240 | test（仅一次） | 153,611.29 | 103,658.99 | 49,952.30 | 48.19% | 2.495e9 |

零适应（inner_steps=0，同样 support）对照：

| 任务 | 划分 | zero-shot Di_N | 真值 Di_N | 绝对误差 | 相对误差 | MSE |
|---|---|---|---:|---:|---:|---:|
| M180 | val | 158,709.21 | 145,594.17 | 13,115.04 | 9.01% | 1.720e8 |
| M240 | test（仅一次） | 158,709.21 | 103,658.99 | 55,050.22 | 53.11% | 3.031e9 |

训练任务 query（adapted）：

| 任务 | 预测 | 真值 | 相对误差 |
|---|---:|---:|---:|
| M202 | 155,941.99 | 125,276.45 | 24.48% |
| M160 | 165,289.58 | 177,703.76 | 6.99% |

## 4. 解读（如实）

- **验证集上 K=1 adaptation 比 zero-shot 更差**（MSE 1.945e8 vs 1.720e8；MRE 9.58% vs 9.01%）。因此本实验**不支持**“MAML 已带来收益”的结论。
- 测试集上 adapted 误差小于 zero-shot，但只有 1 个 query、2 个训练任务，且 test 只评估一次；不能据此宣称泛化或稳定性。
- 训练任务 M202 的 query 误差仍很大；M160 较好。数据量极小，结论只能是“真实链路可执行”，不是模型有效性的证据。

## 5. 必须披露的限制与已知缺陷

1. 新真实训练入口是在 A5 repair 冻结之后新增的，**未经过 A5 审查**；本实验不能称为 A5 已批准的真实 MAML。
2. 标签为本地字节校验 + 审计绑定，但 **NOT_AUTHENTICATED**；同机备份，异机故障域由 Owner 豁免。
3. \`solver_runner.build_evaluation\` 仍用 baseline \`TASK_SPEC.q_pa\` 计算 CL_target；非 M2.02 case 的 \`case_result.lift_match\` 会报 \`CL_TARGET_OUTSIDE_POLAR\`。本次准入使用 \`audit_real_case.py\` 从 deck 复算 q，未受影响；该缺陷应修复后再引用 case_result 的 objective。
4. 未跑真实反馈驱动 BO（预算 24/24 已用尽）；只有固定 design 的 support/query。
5. 未做多 seed、多 query、更多训练任务；K=1、2 train tasks、n=1 query 的统计功效极低。

## 6. 产物

- \`D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/real_maml_result.json\`（SHA256 \`8a3d9987...\`）
- 本目录 \`real_maml_result_20261120.json\`（同一内容）
- \`D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/batch_accounting.json\`（24 starts、10 certs、9 usable；SHA256 \`5e2a44c1...\`）
- \`D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/real_dataset_manifest.json\`

## 7. 下一步（需新的授权/门禁）

1. 修复 \`build_evaluation\` 的 per-case q/Mach，补测试并重跑 preflight。
2. 对真实训练入口做独立 A5 复审；当前只能称 exploratory。
3. 若继续科学问题：增加训练任务与 support/query 设计，先做普通预训练/零适应基线，再做 K=1/2/5；所有新 solver starts 需新 authorization_id 与预算。
4. 真实反馈驱动 BO 需要新批次；当前批次已封顶。
