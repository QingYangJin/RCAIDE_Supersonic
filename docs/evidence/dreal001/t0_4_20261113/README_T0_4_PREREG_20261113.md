# A3 T0-4 真实任务族 / 首批训练批次预注册（DRAFT）

- 生成：2026-11-13（CST），A3 / a3-stats
- 状态：**DRAFT_PENDING_M0_GO**，not_authorization=true，**physical_call_count = 0**
- 对应：Issue #10 T0-4；上游 Issue #11 M0（M0_NOT_STARTED / GATE_WAITING_ON_#10）
- 本文件不是执行许可，不构成 READY_FOR_REAL_META_TRAINING，不宣布任何 winner/显著性/跨族比较。

## 0. 结论先行

本预注册给出 18 个候选真实任务的族、按任务身份的 11/4/3 split、FOMAML/K-shot 配置、首批 6 任务 96 条真实标签的 DRAFT 预算，以及 3 个 heldout 任务的 M3 预留。所有任务的 solver_domain / lift_target_reachable / cross_task_response 均为 NOT_CHECKED，状态 EXPLICITLY DEFERRED_TO_M1_REAL_COLLECTION，admitted=false；必须由 M0/M1 逐任务真实采集补全后 M0 才能冻结。T0-4 本身零物理、零真实标签。F1R2/F2R2 仅证明固定任务域（M2.02/h18.288km 等）的求解链，不是 18 个候选任务的 admission 证据。

## 1. 任务族与物理可用域

### 1.1 候选网格

- Mach：1.8 / 2.02 / 2.2
- 高度：15,000 / 18,288 / 20,000 m
- CL_target：0.17 / 0.19
- L_ref = q(M,h) × Sref × CL_target，Sref=358.25 m²；不是把 358.25 当升力，也不是整体乘常数。q 由 A3 isa_q_pa 与 A1 固定任务值一致。
- 18 个任务，family_sha256 = ada424cce029201aa612cdc3a660e0e4c6edf211034510b3f6d20e98f6ae4e62。

排除项（显式披露，不静默）：

| 候选 | 排除原因 |
|---|---|
| Mach 1.6 / 2.4 | 超出 A5 P1-05 已验证的 1.8/2.02/2.2 求解包络，无物理域证据 |
| 高度 21.0 km | 超出 T0-1 ISA 合同 0-20 km；需要新的大气/求解域合同 |

### 1.2 固定几何/求解器绑定

- evaluator_id = dreal001.evaluator.v12.fixed_cruise，代码 SHA256 = f74a4752495fd6c5330edcaf7edb4bcbe93f99c2a76bac06b5670d1f765ae20d
- geometry_id = CFG-01-thin-12x25-production-baseline，几何 SHA256 = 40fdd4364e01c7fe11ca2ea4530d39c371ae693a434f39e44986f7512d6446f4
- VSPAERO 7.2.2 / OpenVSP 3.55.0；WING_AC；x_ref=16.821978259514246 m；Sref=358.25 m²
- alpha 主网格 [-2,0,2,4,6,8,10]，lift_tol_rel=1e-3，单 start 60 s，NCPU=1，serial
- A1 源配置：D:\RCAIDE\dnext001\wt-real-a1-geometry-solver\configs\dreal001_task_fixed_cruise_REAL.json，SHA256 0aa64eb25d9fd2ed939f7c9f2bdfa9df4b32ee19cbfd9310fbaae56d4976cf27
- 元学习目标：0.5*CDi(f1)+0.5*CDi(f2)（无量纲，与 R10/#9 E1 口径一致）；物理阻力 D_i_N=q*Sref(x)*CDi 只作报告，不混写。

### 1.3 物理域门槛（逐任务，未通过前不得采集）

每个任务必须同时满足：

1. solver_domain：VSPAERO 7.2.2 在 (M,h) 收敛，alpha in [-2,10] 无 LIMIT/UNCONVERGED；
2. lift_target_reachable：存在 alpha in [-2,10] 使 |L-L_ref|/L_ref <= 1e-3；
3. cross_task_response：目标对 (M,h,CL) 的响应超过 MIN_EFFECT_REL，且不是全局缩放/仅改字段。

三项均须为 PASS 且附 REAL_VSPAERO 原始证据（raw_sha/geometry_sha/solver_version/physical_solver_starts_actual/internal_solver_cases_actual，physics_validation_status=NOT_VALIDATED）；否则该任务从族中移除并重新预注册。18 个候选任务当前 applicability status = DEFERRED_TO_M1_REAL_COLLECTION、三项均 NOT_CHECKED、admitted=false，证据 schema 见 `TaskApplicability.REQUIRED_APPLICABILITY_EVIDENCE_SCHEMA`。F1R2（A5 `fd1ab768`）/F2R2（A5 `7ed9c9e`）只证明固定任务域求解链，不是候选任务 admission 证据。

## 2. 任务级 split 与泄漏控制

- 单位：TASK_IDENTITY；seed=42；ratios=0.6/0.2/0.2；holdout_provenance=NEVER_EVALUATED_PRIOR_RUN
- 结果：**11 meta_train / 4 meta_val / 3 meta_test**；require_unseen_holdout=true，三组 task_id 与 fingerprint 均不相交。
- 任务身份由物理上下文哈希决定，不含 task_id/source_kind/clock；同一物理任务不能跨 split。
- meta_test 的 3 个任务从未参与训练、调参、early stopping、特征/标签统计；M0 前不会读取其标签。
- TaskContextEncoder、FeatureStats、LabelTransform 只在 meta_train 上 fit；support/query 为任务内互斥记录；query 标签对 adaptation 不可见。
- 预注册 preflight 行不进入 dataset/统计。
- 允许 NO_EVIDENCE / NEGATIVE_TRANSFER；不允许把合成/mock/历史回放混入 REAL_TRAINING_INGEST（T0-2 fail-closed）。

## 3. 首批 DRAFT（M1）：6 任务 × 16 设计 = 96 条真实标签

### 3.1 任务选择

- meta_train 4 个：2066f5620f26（1.8/15k/0.17）、576f7bfdbdcc（2.02/18.288k/0.17）、9f30c337b993（2.2/15k/0.19）、106e141f5f37（2.02/20k/0.19）
- meta_val 2 个：a820ff5f11e4（1.8/18.288k/0.17）、d0bbe623c78e（2.2/20k/0.19）
- **不含任何 meta_test 任务**；选择规则是按因子覆盖预注册，不看结果，不按性能挑选。

### 3.2 设计采集

- 每任务 16 个设计：确定性 12D Halton（基 2,3,5,7,11,13,17,19,23,29,31,37），归一化映射到冻结上下界；inactive 维固定 baseline。
- seed 仅取 task_fingerprint 前缀做 digit scramble；同一任务永远得到同一 16 点。
- support=8 / query=8；**M1 不用 BO 选点**，避免采集偏差；不做结果依赖筛选。

### 3.3 预算（DRAFT，未授权）

| 阶段 | starts | internal cases |
|---|---:|---:|
| preflight 2 例 | 2 | 14 |
| main 96 设计 | 96 | 672 |
| **planned** | **98** | **686** |
| hard max（infra reserve 4） | 102 | 714 |

- 单 start 60 s、serial、NCPU=1、OMP=1；M1 wall cap 3 h。
- solver 失败不重试；reserve 只用于基础设施失败。preflight 任一 FAIL → 整批 ABORT。
- 失败上限：单任务 invalid >25%（>=8 次后）停该任务；全批 invalid >20%（>=24 次后）停批；连续 2 次 INFRA 停；磁盘 <20 GB 停。
- charged（预算预留）与 actual（ledger 实际）分列，不混写；当前 physical_call_count=0。

## 4. M3 heldout 预留（不授权）

- 3 个 meta_test 任务，每任务 16 设计（support 8 + query 8），K=0/1/3/5 离线 query 评分；M3-A 不使用 BO，避免自适应选点偏差。
- preflight 2 + main 48 = **50 starts / 350 internal**；hard max 52/364；wall cap 1.5 h。
- M3-B 的 BO warm-start 需要 M0 后另立预算，不在本 DRAFT。
- 全 pilot 合计 planned **148 starts / 1,036 internal**；hard max 154/1,078；4.5 h wall cap。

## 5. 训练配置（A2 T0-3 接口）

- 默认 **FOMAML**，first-order；Full MAML disabled（二阶/显存门禁未过）；普通监督预训练 + 同 K-shot inner-loop 作为对照。
- K=0/1/3/5；support=8/query=8；inner_lr=0.01、inner_steps=5、outer_lr=1e-3；meta_steps=20、batch=4 tasks；seed=42；CPU、threads=1、deterministic。
- 模型：design_dim=12、context_dim=20（12 mask bits + 8 numeric）、input=32、output=2、hidden=[64,64]。
- A2 绑定（仅接口核对，不改 A2 代码）：make_model kwargs、TrainConfig、MetaTrainer.train、AdaptationRunner.adapt、WarmStartSampler.propose 与 T0-3 当前签名对齐；A2 不 import A3 树，只依赖 duck-typed 协议。
- 成本：TRAIN/ADAPT/INFERENCE 的 physical starts 均为 0，分别记账；M1/M3 的采集成本单列。

## 6. 统计端点与解释边界

- 主端点（描述性）：query MAE / RMSE（每 method×K×task）；K-shot gain = 1 - MAE(K)/MAE(K=0)；negative transfer 标记（>5% 变差）。
- 次端点：query 目标 Spearman 相关、invalid/可行计数、每任务 physical starts/internal cases。
- 单 seed、3 个 heldout 任务：**不做 p 值/CI/显著性/winner**；不做跨族绝对比较；不允许用 test 任务调参。
- 物理分层：SOLVER_LOOP_VERIFIED 需 F1/M1 独立证据；INTERNAL_AERO_OPTIMIZATION_GAIN 由 M3 判定；EXTERNAL_PHYSICS_SUPPORTED=NOT_VALIDATED；fuel_burn_kg=null。

## 7. 与 #11 M0/M1 接口

M0 需冻结：任务族与 family_sha、18→9 任务的 admission 结果、split manifest、evaluator/geometry SHA、设计采集策略、K-shot、seeds、统计端点、预算与停止规则，并在 M0/M1 阶段完成逐任务真实 applicability 证据（F1R2/F2R2 只作固定任务域先例）。M0_PASS 后由 Lead 另签 M1 的 window/token/approval；**不复用 #9 R10 的 token/审批/额度**。M1 只做真实标签采集；M2 做 FOMAML；M3 做 heldout K-shot。A5 对 M0 与 T0 Gate 做非作者独立复核。T0-1 代码合同的 readiness 为 `T0_1_CONTRACT_READY_APPLICABILITY_DEFERRED_TO_M1`，任何真实训练入口经 `TaskFamily.require_real_training_ready()` fail-closed 拒绝。

## 8. 与 A1/A2 接口核对结论

- A1：evaluator_v12 代码 SHA、CFG-01 几何 SHA、VSPAERO/OpenVSP 版本、alpha 网格、lift_tol_rel、WING_AC 全部写入配置；D_i_N 与元学习目标分离。F1R2 真实 run 22/22 SOLVED（A5 `fd1ab768`）与 F2R2 18 starts（A5 `7ed9c9e`）只作固定任务域证据，不构成 18 个候选任务的 applicability/admission 结论。
- A2：TrainConfig(method, max_steps, batch_size, seed, checkpoint_every, allow_second_order, ...)、MAMLConfig/make_model、AdaptationRunner.adapt、WarmStartSampler.propose 字段和调用顺序已逐项对照；context_names 与 A3 CONTEXT_FEATURE_NAMES 完全一致（20 维）。A2 的 SEALED_SYNTHETIC_FIXTURE 仅 CODE_TEST 可用，本 DRAFT 的真实采集全部 REAL_VSPAERO。
- 未解决项：A2 的 EvaluationRecord 仍缺 alpha/Sref/L_ref/raw_sha（其已声明真实记录由 A3 合同提供）；本 DRAFT 要求真实 VALID 行必须带这些字段。T0-1 生成器已改为与 T0-4 同源（`t0_4_candidate_family()`），18 tasks / family_sha `ada424cc` / split 11/4/3 必须逐项一致；真实训练入口 fail-closed。

## 9. 交付文件 SHA256（本报告生成时）

| 文件 | SHA256 |
|---|---|
| real_task_family_candidate.yaml | de1732a5627776b201e7e86ae9c8a31e9fb49c13507d33d6cf8800876226c756 |
| meta_data_contract.json | b0be72e09be0e8930520bf2bf064d01418b9a098784c27d0756f4eaaf0f4ef62 |
| meta_train_config.yaml | 2c9736f32abfecc4cd770eeada12a59de277db2deb96f0116d2a04ef72103018 |
| task_split_manifest.json | c516e1772f8302b7ac187b810f1ef21546e1d10e6b5cd305b490a57dfa71518d |
| first_real_training_batch_DRAFT.json | 2942e5db7366e93e6266626f3580c5f8eddadf577b4f69574c5b1053783ff1bb |

## 10. Non-result boundary

- physical_call_count = 0；未启动 VSPAERO，未采集任何真实标签，未运行训练/推理。
- readiness = false；不是 READY_FOR_REAL_META_TRAINING，不是 M0_PASS。
- physics_validation_status = NOT_VALIDATED；fuel_burn_kg = null；EXTERNAL_PHYSICS_SUPPORTED = NOT_VALIDATED。
- 不宣布 winner、排名、显著性、p 值、CI；不做跨族 CDi/D_i 绝对比较。
- 所有候选任务 applicability status = DEFERRED_TO_M1_REAL_COLLECTION、admission_status = PENDING_M0_BY_DESIGN；逐任务真实 applicability 证据与 M0 冻结前，任何真实执行均被禁止。
