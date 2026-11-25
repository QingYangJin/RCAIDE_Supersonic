# V1L 回执 —— 用 RCAIDE 超音速 VLM（20×10）重做优化与训练

运行目录：`D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/`
worktree：`D:/RCAIDE/.worktrees/dreal005-20261124`（分支 `research/dreal005-conditional-meta-real-optimization`）
时间：2026-11-25 12:06–12:20 +08
**物理求解器启动次数：0**（VSPAERO 未被调用；全部气动来自 RCAIDE 线性 VLM）

## 0. 口径声明

- 目标函数 = `CDi_trefftz`，即 VLM 给出的 Trefftz 诱导阻力系数，**不含波阻**；
- 每个设计的 α 由割线法反解到任务升力（|CL−CL_target| < 1e-7），因此比较的是"等升力下的诱导阻力"；
- 标签源类型 `rcaide_vlm_20x10`（新增声明的计算型标签，无法满足 `require_real_admission()`），
  与 VSPAERO 的 67 条 `vspaero_raw` 标签**互不混用**；
- 每行标签可由 (design, task, lattice) 逐位复算：三个随机的复算抽查全部 identical=True（`v1l_labels.json:determinism_checks`）。

## 1. 优化：BO on VLM 20×10

协议在驱动脚本 `v1l_bo.py` 的模块 docstring 中先固定，然后才执行：

| 项 | 取值 |
|---|---|
| 格架 | (20, 10) spanwise×chordwise，所有设计同一格架 |
| 搜索子空间 | sweep_1 ∈ [65.5, 68.5]，sweep_2 ∈ [46.5, 49.5]，其余 10 维冻结 |
| 预算 | 24 LHS bootstrap + 96 GP-EI = 120 次 VLM 评估 |
| 采集器 | RecoveryGaussianProcessBO（GP-EI + 核可行性权重），seed 20261125 |
| 确认规则 | top-5 在 30×15 与 45×25 重解，符号在更细格架仍保持才允许声称改进 |

基线（sweep_1 67.0, sweep_2 48.0）：CDi 0.007314667、CL 0.18174399805、α 5.528498°，Di 54,123.416 N。

**最优（20×10）**：sweep_1 = 65.501955、sweep_2 = 48.636094，CDi 0.007089604、α 5.508490°
→ Di 52,458.110 N，比基线低 **1,665.306 N（3.08%）**。

跨格架确认（同 top-5，等 CL 反解 α）：

| 候选 (sweep_1, sweep_2) | 30×15 CDi | 30×15 Δvs 基线 | 45×25 CDi | 45×25 Δvs 基线 |
|---|---|---|---|---|
| baseline (67.0, 48.0) | 0.008463523 | — | 0.008133283 | — |
| (65.501955, 48.636094) | 0.008118411 | −4.0776% | 0.007785928 | −4.2708% |
| (65.5005, 48.8553) | 0.008114589 | −4.1228% | 0.007791539 | −4.2018% |
| (65.5028, 48.9919) | 0.008145985 | −3.7518% | 0.007787822 | −4.2475% |
| (65.5029, 47.5666) | 0.008064684 | −4.7125% | 0.007762871 | −4.5543% |
| (65.5268, 48.4743) | 0.008152627 | −3.6734% | 0.007784259 | −4.2913% |

符号在 30×15 与 45×25 两个更密格架上全部保持，量级 3.7–4.7%，与 20×10 的 3.08% 同向。**改进结论成立。**

### 三条必须一起读的限制

1. **最优落在子空间下界**：sweep_1 的最优值 65.501955 距下界 65.5 只有 0.002°。也就是说在给定盒子内，
   减小 sweep_1 一直有利，尚未看到拐点。要声称"该设计的后掠角最优"必须先扩子空间并重新预注册预算。
2. **sweep_2 在 20×10 上不可分辨**：1D 探针显示 sweep_2 全区间 CDi 只变 0.281%，而 20×10 与 30×15 的
   排序 Spearman 仅 0.3132；top-5 的 sweep_2 从 47.57 散到 48.99，CDi 差别 < 0.6%——这部分是噪声。
   可信的只有 sweep_1 方向（Spearman 0.9945）。
3. **20×10 的绝对水平比 30×15 低 13.4%**（水平比 0.8659），且 A 项已证明 VLM 离散解不收敛。
   允许的表述是"在 20×10 基准下，BO 找到的构型在 20×10/30×15/45×25 三档上一致更低"，
   不是"该构型阻力为 0.00709"。

## 2. 训练：五臂消融重跑（VLM 标签）

数据：A0 的冻结任务族（8 个 canonical 任务，Mach 1.4–2.6，18,288 m，L_ref 1,333,704.4 N）与
冻结的 7 个设计、冻结的 support/query 划分；**44 条标签全部由 VLM 重算**，不沿用任何 VSPAERO 标签。

超参：每臂在验证 K=1 上从 9 点网格（inner_lr ∈ {0.005,0.01,0.05} × inner_steps ∈ {1,3,5}）选，
3 个种子平均后锁定；测试集不参与选择。选中：RANDOM_INIT 0.05/5、POOLED_12D 0.05/5、
COND_SUPERVISED_16D **0.01/1**、FOMAML_12D 0.05/5、COND_FOMAML_16D 0.05/3。

### 测试集平均 MAE（N；n = 6 = 2 任务 × 3 种子）

| 臂 | K=0 | K=1 | K=3 | 相对误差 K=0/1/3 |
|---|---|---|---|---|
| RANDOM_INIT | 41,690 | 15,530 | 25,936 | 124.2% / 44.2% / 77.3% |
| POOLED_PRETRAIN_12D | 41,669 | 13,217 | 25,269 | 123.9% / 37.0% / 75.4% |
| COND_SUPERVISED_16D | **8,595** | 5,363 | 6,677 | 26.1% / 16.2% / 20.3% |
| FOMAML_12D | 47,351 | 15,724 | 28,189 | 140.6% / 44.5% / 84.2% |
| COND_FOMAML_16D | 21,971 | **5,183** | **5,339** | 64.4% / 14.8% / 15.7% |

验证集平均 MAE：COND_SUPERVISED 991 / 719 / 865；COND_FOMAML 13,003 / 1,880 / 7,447。

### 核心配对（COND_FOMAML_16D − COND_SUPERVISED_16D，配对 n=6）

| 划分 | K | Δ MAE (N) | 95% CI | 方向票数 |
|---|---|---|---|---|
| test | 0 | +13,375 | [+1,390, +25,361] | 5 差 / 1 好 |
| test | 1 | −181 | [−6,004, +5,643] | 4 好 / 2 差 |
| test | 3 | −1,338 | [−9,588, +6,912] | 3 / 3 |
| test | 全部 K 合并 | +3,952 | [−2,484, +10,389] | — |

### 结论（与 VSPAERO 线一致的部分，与不一致的部分）

- **条件化仍是唯一稳健的大效应**：16D 条件监督相对 12D 池化预训练，验证集 −88%/−95%、测试集 −80%/−95%。
  与 VSPAERO 标签的结论相同，且更强。
- **元学习目标仍未通过**：COND_FOMAML 在 K=0 显著更差（CI 不含 0），K=1/K=3 与条件监督不可区分。
  FOMAML_12D 相对 POOLED_12D 也没有稳定增益（测试 K=1 15,724 vs 13,217、K=3 28,189 vs 25,269 更差）。
- **与 VSPAERO 线的一处方向差异**：VSPAERO 标签下 COND_FOMAML 在 K=1/K=3 略好；
  VLM 标签下这个优势缩到 −181 / −1,338 N 且不显著。**样本量下这是噪声级别的差别，不能反过来当正结果。**
- **新出现、且更重要的一条**：VLM 标签的跨任务量级差 4 倍（M140 123,191 N → M260 31,514 N），
  而最好的条件模型相对误差仍有 15–26%。BO 找到的改进是 3–4%，比模型误差小一个数量级以上。
  → 用这套模型做候选排序热启动（O1 那类协议）在 20×10 VLM 口径下没有可行性依据。

## 3. 代码改动（本次落地，均有明确 fail-closed 语义）

1. `research/concorde_metaopt/evaluation/rcaide_vlm_backend.py`（新增）——VLM 评估器，确定性、0.66–0.77 s/设计。
2. `research/concorde_metaopt/dreal001/meta/meta_dataset.py`——`source_kind` 增列 `rcaide_vlm_20x10`；
   新增 `require_declared_computed_labels()`（只接受单一计算型来源、有限正标签，且拒绝携带
   admission 证书；它**不会**让数据集通过 `require_real_admission()`）。
3. `research/concorde_metaopt/dreal001/meta/real_a0_ablation.py`——`run_arm`/`run_arm_for_arm`
   增加 `mode="vlm_labels"` 分支，走上述门禁，不放松 `mode="real"` 的原始字节要求。

## 4. 不能声称

- 不能声称 VLM 结果物理有效、收敛或与 VSPAERO 一致（A 项 FAIL，D 项只能作对照）；
- 不能声称改进是"真实气动改进"：口径只是 Trefftz 诱导阻力（无波阻、无粘性、无配平）；
- 不能声称全局最优、后掠角最优（最优在盒子边界）、或 sweep_2 被优化过；
- 不能声称元学习（FOMAML）有收益；也不能声称条件监督需要元学习才能得到；
- 不能声称 3–4% 的 CDi 改进等价于同等任务性能改进（未跑 mission/fuel）。

## 5. 复现

```bash
cd D:/RCAIDE/.worktrees/dreal005-20261124
D:/Anaconda/envs/RCAIDE/python.exe -B -u D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/v1l_bo.py
D:/Anaconda/envs/RCAIDE/python.exe -B -u D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/v1l_data.py
D:/Anaconda/envs/RCAIDE/python.exe -B -u D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/v1l_train.py
```

## 6. 未完成

- O1 式三臂热启动（Sobol+BO / 条件监督 K-shot 排序 / COND_FOMAML K-shot 排序）尚未在 VLM 后端重跑。
  按第 2 节最后一条，重跑前应先决定"模型误差 15–26% vs 目标效应 3–4%"这一量级不匹配怎么处理，
  否则协议注定复现"模型排序不如 Sobol"。
- v1l_bo_results.json 里 top-5 确认表与 20×10 的 120 条评估记录齐全，但尚未生成图（收敛曲线、跨格架对比）。
