# P4 路线A S0 数据合同与预注册规范（中文草案）

> 状态：S0-4 / v4c 修订（v1.3），供 Lead、A1、A2、A5 审阅；**不构成新物理授权**。
> 依据：Issue #7（D-P4-003）§2 S0、§3、§4；docs/planning/p4_route_a_stage_improvement_plan_20261105.md（commit a331639e）；docs/planning/p4_route_a_s0_2_decisions_20261105.md（D-S0-2-01..07，Lead 裁定）；docs/planning/p4_route_a_s1_v4_remediation_rulings_20261105.md（R-V4-01..06，2026-11-05 Lead 裁定，sha256 f71e32a9…）；A5 S0 审阅 `<EXT>/p4-route-a/a5/S0_A5_review.md`；A5 S1 rev2 复审 `<EXT>/p4-route-a/a5/S1_code_review_rev2.md`（CHANGES_REQUESTED，2 blocker / 4 major / 6 minor，sha256 d5a0979a…）。
> 工作树：本仓库 @ c0cb2cd（v1.2 修订时点；branch research/p4-route-a-s1）。
> 作者：A4（任务 task-231）。本合同约束新版本数据与运行，**不修改任何旧冻结 run**；旧 S0-2 包只读。
> v1.2 变更：按 A5 S1 rev2（S1R2-B01/B02）与 R-V4-01..06，将确证性任务族升级为 p4ra-family-v4（family_id 仍 F-QE-feasible-v3），新增 holdout_seed=20261106 / holdout_splits 与 S0-3 冻结包规则；旧 p4ra-family-v3/S0-2 包降为只读历史复现；预注册 C5-B 结构性不可辨识规则（C5 不进 benefit/harm 与 Holm，pair-level overlap>=0.90 判 STRUCTURALLY_IDENTICAL）；新增 FC-14/FC-15。v1.1 已关闭 A5-S0-M01/M02/m01/m02/m09，预算与端点语义继续有效。

## 1. 目的与适用范围

本合同定义路线A（K-shot 元学习响应代理辅助普通约束 BO 初始设计）在 S0–S4 使用的数据、任务、预注册、预算与确定性 digest 规范，目标是：

1. 使每个正式实验在打开 meta_test 之前**可审计地冻结**；
2. 使合成任务、评估器与物理状态标签**不可混淆**（物理调用恒为 0）；
3. 使“支持样本计入预算”“任务级统计单位”“旧工件只读”成为可程序化检查的硬约束；
4. 所有检查失败一律 **fail-closed**（拒绝运行，不静默修正）。

适用对象：Issue #7 下新产生的所有任务族、preregistration、run_config、data_manifest、统计脚本与报告。旧 M2/M5/M6 与 D-12D-005 归档 run 只读，不受本合同修改。

## 2. 术语

| 术语 | 定义 |
|---|---|
| task（任务） | 一个合成解析优化问题实例：设计空间 + 目标函数 + 约束函数 + 参考解；是统计一级单位 |
| task_id | 全局唯一、稳定、可追溯的任务标识；格式与正则见 §3，新任务族不得与旧 M2/M5/M6 任务重名 |
| family_version | 任务分布版本；冻结后不得在不升版本的情况下改变生成规则 |
| split | 五值枚举：meta_train / meta_validation / meta_test / meta_test_ood / negative_control；规范见 §3.2 |
| split_digest | 覆盖全部五个 split（120 任务）的 task_id 有序列表 canonical digest；与 family v4 的 split_hash 覆盖集合一致 |
| holdout_seed | 仅用于 meta_test 20 + meta_test_ood 10 重采样的种子；v4 固定 20261106；不得用于 meta_train/meta_validation/negative_control |
| S0-3 冻结包 | v4 确证性冻结包，命名 `p4ra-s0-3-freeze-<UTC>Z`；旧 S0-2 包（p4ra-s0-2-freeze-20261105T072500Z）只读，仅历史复现/负控 |
| B | 单个 run 的**真实合成评价**总预算（函数评价次数），不含代理前向/训练/适应墙钟 |
| K | 部署时允许的已评价支持样本数；K 次评价必须计入 B |
| support | 目标任务上已由真实合成评估器评价过的 K 个设计点及其目标/约束标签；同一任务的 B 个评价中前 K 个固定为支持评价 |
| meta_test | 新任务族上独立、冻结后一次性打开的正式测试任务集；主统计分母只有其 20 个任务 |
| f* | reference_solution.best_feasible_value（数值或 null）；端点 gap_to_reference 的唯一参考值来源 |
| ENDPOINT_ROW_KEYS | 统计 CSV/图表/分析脚本共用的显式端点键登记表；只允许 §3.3 的 4 个规范 ID 及其登记附加键 |
| physical_call_count | 真实物理求解器启动次数；本轮必须恒为 0 |
| digest | canonical JSON 的 SHA-256 十六进制串 |

## 3. 任务与数据合同 schema（v1）

每个任务/样本至少包含以下字段（JSON；未知字段允许但不得覆盖已定义语义）：

| 字段 | 类型 | 必填 | 约束/说明 |
|---|---|---|---|
| schema_version | string | 是 | 固定 "p4ra-task-v1"；不兼容变更必须升 v2。S0-3 冻结前修订枚举不升版；若冻结前已生成任何 v1 工件则必须升 v2（当前无） |
| task_id | string | 是 | 唯一格式：`^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$`；v4 接受沿用该字面量，但必须同时携带 family_version=p4ra-family-v4；split 代码见 §3.2；与 M2/M5/M6 全部 task_id 零交集（程序断言，非空即 fail-closed） |
| family_id | string | 是 | 固定 "F-QE-feasible-v3"；与 family_version 绑定；v4 仅重采样 holdout，解析分布未变，不得称 v4 为新公式族 |
| family_version | string | 是 | 固定 "p4ra-family-v4"；family_seed=20261105；holdout_seed=20261106；冻结后不得改，禁止 v3/v4 跨版本混用 |
| holdout_seed | int | 是（仅 TE/OD） | 固定 20261106；仅 meta_test / meta_test_ood 任务携带，并用于该两类 split 的重采样；其他 split 不得用该字段改 seed |
| task_fingerprint | string(64 hex) | 是 | 任务内容 canonical digest（不含 split/seed） |
| split | enum | 是 | 五值：meta_train / meta_validation / meta_test / meta_test_ood / negative_control（§3.2）；同一 task_id 不得跨 split |
| seed | int ≥0 | 是 | 任务生成种子；不得与 split 混用 |
| design_dim | int ≥1 | 是 | 设计变量维数（合成任务自定，例如 2–8） |
| design_names | [string] | 是 | 长度 = design_dim，唯一 |
| design_bounds | [[float,float]] | 是 | 长度 = design_dim；lower<upper；单位在合成任务中为无量纲 |
| objective | object | 是 | 目标函数定义（analytic id + 参数 + 参数 digest）；不得引用 query 标签 |
| constraints | object | 是 | g_i(x)≤0 列表（analytic id + 参数 + digest）；可为空数组但需显式 |
| reference_solution | object | 是 | 参考解：best_known_design、best_feasible_value（可为 null）、source=analytic|grid、digest；用于 gap_to_reference，**不得**作为支持样本标签来源 |
| evaluator | object | 是 | 见 §3.4；真实物理调用必须为 0 |
| budget | object | 是 | 见 §4；B、K、initial_designs、split 计数必须与预注册一致 |
| provenance | object | 是 | 代码 git_sha、计划 commit、repo/branch/worktree、生成时间 UTC |
| digests | object | 是 | task_fingerprint、config_digest、data_manifest_digest、prereg_digest |

### 3.1 evaluator 子合同

| 字段 | 类型 | 约束 |
|---|---|---|
| evaluator_id | string | 稳定 ID，例如 synthetic-analytic-v1 |
| fidelity | enum | synthetic_LF / synthetic_HF / vspaero_internal_only（后者本轮不得用于 #7 训练标签） |
| source_kind | enum | analytic / synthetic_bias / archived_metadata（本轮禁止 real_solver） |
| physics_validation_status | enum | NOT_APPLICABLE（合成）/ NOT_VALIDATED / VALIDATED；合成任务只能 NOT_APPLICABLE |
| solver_version | string|null | 合成任务为 null；只读归档元数据时填归档版本 |
| config_hash | string(64 hex) | 评估器配置 digest；任一参数变化必须变化 |
| constraints_g_le_zero | bool | 是否按 g≤0 判定可行（必须为 true） |
| physical_call_count | int | 本轮必须为 0；>0 立即 fail-closed |

### 3.2 五 split 规范（关闭 A5-S0-M01；依据 D-S0-2-01）

| split | 代码 | 任务数 | 角色 | 进入主统计 | 进入 split_digest / split_hash |
|---|---|---|---|---|---|
| meta_train | TR | 60 | 元训练 | 否（只用于训练） | 是 |
| meta_validation | VA | 20 | 元验证/调参/校准 | 否 | 是 |
| meta_test | TE | 20 | 主确证盲测 | **是**（主结论唯一来源） | 是 |
| meta_test_ood | OD | 10 | 分布外诊断 | 否（单独描述层，不得并入主结论） | 是 |
| negative_control | NC | 10 | 负控/机制证伪 | 否（只用于负控结论） | 是 |

1. split_digest / split_hash 的覆盖集合 = 全部五个 split 的 task_id 有序列表（按上表顺序串联 canonical JSON 后哈希），共 120 个任务。
2. 合同 split enum 必须为上述五值；FC-06/FC-07 的跨 split 唯一/零交集检查覆盖全部 120 任务。
3. 主统计分母只有 meta_test 的 20 个任务；meta_test_ood 与 negative_control 单独成表，不得与主结论合并；任务级聚合按 §3.3 第 7 条。
4. 任务数 60/20/20/10/10 必须在 preregistration.split_counts 与冻结清单中一致；任何增减须在打开 meta_test 前完成并重签 split_digest。
5. v4 只对 meta_test（20）与 meta_test_ood（10）使用 holdout_seed=20261106 重采样；meta_train 60 / meta_validation 20 / negative_control 10 的 task_id→task_fingerprint 映射与 S0-2 逐项相同；五集合 task_id 仍两两互斥；主统计仍为 meta_test 20 任务，不做事后任务剔除。

### 3.3 主终点 ID 与语义登记（关闭 A5-S0-M02；依据 D-S0-2-02/04）

**规范 ID（唯一，禁止别名静默映射）**：`best_feasible_value`、`gap_to_reference`、`first_feasible_eval_index`、`feasible_hit_rate`。

- `first_feasible_evaluation_index` 为**禁用别名**；合同、统计计划、family_id=F-QE-feasible-v3 的任务元数据、prereg schema、分析代码、CSV 列名与图表键必须使用统一 ID。
- preregistration.primary_endpoints 只允许上述 4 个 ID，且不得为空。
- ENDPOINT_ROW_KEYS 必须显式登记主端点键与附加字段键，至少覆盖：4 个规范 ID、`first_feasible_in_support`、`first_feasible_after_support_index`、`feasible_hit_rate_non_support`、`n_nonnull`、`null_rate`。统计 CSV 生成器与图表脚本只允许读取登记键。
- 合成端到端测试必须断言该端点在统计 CSV 中的非空覆盖数与预期一致（参考 M5 A5-M5-01：键名不一致导致 4800/4800 全 null 的真实故障模式）。

端点语义（S0-3 沿用 S0-2 统计口径，不因 holdout 重播种改变；统计实现以 Lead 统计计划 v1.1 为准；本合同固化字段与公式）：

| 端点/字段 | 定义 |
|---|---|
| f* | reference_solution.best_feasible_value（数值或 null）；不重新评价，不使用历史 run 的物理量 |
| best_feasible_value | B 个评价中所有满足全部约束的点的最小目标值；无可行点 = null（不插补、不计 0） |
| gap_to_reference | f_best 或 f* 任一为 null → null；否则 gap = (f_best − f*) / max(|f*|, 1e-12)（有符号；优于参考为负；按原值报告，不截断） |
| first_feasible_eval_index | B 个评价按真实评价顺序的 1-based 序号（支持评价为 1..K），首次可行即记录；无可行 = null。附加 first_feasible_in_support（bool）与 first_feasible_after_support_index（序号−K；若首次可行在支持集内则为 null）。跨 K 比较必须声明 K 依赖性，不得把不同 K 的原始序号直接相减当作增益 |
| feasible_hit_rate | 可行评价数 / B（分母恒为 B）；附加 feasible_hit_rate_non_support = 非支持可行数 / (B−K)（B>K 时） |
| 显著性阈值 | 相对改进以配对基线臂中位数为分母：best 相对改进 =(median_base−median_arm)/max(|median_base|,1e-12) ≥ 1%；gap 相对改进 =(gap_base−gap_arm)/max(|gap_base|,1e-12) ≥ 1%；feasible_hit_rate 绝对差 ≥ 0.05；first_feasible 改善 = idx_base−idx_arm ≥ ceil(0.05×B)（同 K 内比较） |
| 聚合 | 单 run 端点 → (task, meta_seed) 内对 10 个 opt seed 取均值 → 对 20 个 meta_test 任务做配对检验；meta_seed 等权平均为主分析，逐 meta_seed 为敏感性报告；任务为一级统计单位 |
| null 政策 | null 不插补、不计 0；报告 n_nonnull/null_rate；主端点 null 率 >70% → 该端点 INCONCLUSIVE，不据此更换终点 |

### 3.4 标签与物理隔离

- 合成任务的标签只能由 evaluator_id 对应的解析/合成函数产生；不得把 VSPAERO 内部 CD、RCAIDE 经验油耗、SU2 结果或任何真实求解器输出作为 #7 的合成标签或“已校准真值”。
- 只读 VSPAERO 归档元数据仅可进入 S4 的接口演练，且必须携带 physics_validation_status=NOT_VALIDATED、source_kind=archived_metadata，不得进入合成 meta_test 的标签/终点。
- 任何字段名含 validated/real/fuel 的标签必须附物理证据引用；否则 fail-closed。

## 4. 预算口径（K 计入 B；五臂映射依据 D-S0-2-03）

### 4.1 计数规则

1. **B 只计真实合成评价（evaluate 调用）次数**；代理前向预测、元训练、适应、候选池排序不计入 B，但其墙钟与峰值内存必须单独记录（proxy_scoring_cost / adaptation_wall_s / train_wall_s）。
2. 每个 run 在同一任务上按固定顺序评价 B 个真实点：前 K 个必须是支持评价，**计入 B**；所有对照臂共享完全相同的 K 个支持点及标签记录（支持标签是否用于适应因臂而异，见 §4.2）。
3. BO 初始设计总数为 8：由代理/随机机制补 8−K 个新点，再执行普通 BO B−8 次评价；K=0 时 8 个初始点全部来自原初始化逻辑，须复现旧行为。
4. 支持集标签不得作为免费先验重复使用：同一设计点若已在 B 内评价，后续只能复用缓存记录，不得再计一次；缓存命中必须写入缓存账。
5. 任何随机臂/DE 臂与其他臂的**总真实评价次数必须精确相等**（B=64 或 128）；billable 不等于 B 即 fail-closed，该 run 作废。
6. physical_call_count 必须为 0 且每 run 落盘；真实求解器启动一次即为预算违规。
7. DE 臂没有 BO“8 个初始点”的名义概念：其 8−K 个新初始点同时作为初始 population 的一部分，按实际评价数计；不得因种群机制少评或多评。

### 4.2 五臂 × K 预算映射（所有 B∈{64,128}）

| 臂 | 阶段 1：支持评价 | 阶段 2：初始设计 | 阶段 3：主搜索 | 合计 | 支持标签使用 |
|---|---|---|---|---|---|
| Random-BO | K（计费） | 8−K 个随机新点 | B−8 次普通 BO | B | 不用于适应（仍计费） |
| Pretrain-Kshot-BO | K（计费） | 8−K 个代理/随机新点 | B−8 次 BO | B | 用于适应 |
| FOMAML-ZeroShot-BO | K（计费） | 8−K 个代理/随机新点 | B−8 次 BO | B | 不用于适应（仍计费） |
| FOMAML-Kshot-BO | K（计费） | 8−K 个代理/随机新点 | B−8 次 BO | B | 用于适应 |
| DE | K（计费） | 8−K 个随机/代理新点（并入初始 population） | B−8 次 DE 世代评价 | B | 不用于适应（仍计费） |

- K=0：阶段 1 为 0，阶段 2 为 8；FOMAML-Kshot-BO 与 FOMAML-ZeroShot-BO 同构，必须登记 CLONE 并排除因果推断。
- 单测断言：5 臂 × K∈{0,1,3,5} × B∈{64,128}（共 40 组）billable 精确等于 B；K 未计入或各臂不相等 → fail-closed。
- 阶段顺序固定为“支持评价 → 初始设计 → 主搜索”；不得把支持评价挪到初始化之后以规避计费。

### 4.3 预算账字段

run_config 与 summary 至少包含：budget.arm_id、budget.B_total、budget.K_support、budget.initial_designs=8、budget.standard_bo_calls=B−8、budget.support_evaluations_counted=true、budget.billable_must_equal_B=true、evaluations.billable（必须 = B）、evaluations.non_billable、proxy_scoring_cost.wall_s、adaptation_wall_s、physical_call_count、physical_call_sources=[]。

## 5. 任务族隔离、v4 holdout 与旧包只读规则

1. **新任务族**使用 family_version=p4ra-family-v4（family_id 仍 F-QE-feasible-v3）；仅重采样 holdout 两类集合（meta_test 20 + meta_test_ood 10），meta_train 60 / meta_validation 20 / negative_control 10 的 task_id→task_fingerprint 逐位不变。v4 的 holdout task_fingerprint 必须与 v3 官方包 120 个 task_fingerprint 零交集（程序断言，非空即 fail-closed）；对旧 M2/M5/M6 的 280 个 legacy task_id 只做 task_id 零交集（旧清单无 task_fingerprint 字段）。
2. 旧 M2/M5/M6 的 meta_test 已公开，只能用于**诊断性复现/历史对照**；旧 p4ra-family-v3 / p4ra-s0-2-freeze-20261105T072500Z 包保持只读可验证，仅用于历史复现/负控，**不得用于 S1 确证性 formal**，也不得作为“新未见盲测”。
3. 确证性 S1 只接受新的 S0-3 冻结包 `p4ra-s0-3-freeze-<UTC>Z`；pack 内 frozen_family/prereg/freeze_summary/digest_manifest 必须写入 family_version=p4ra-family-v4、holdout_seed=20261106、run_id、git_sha、code_sha，并禁止 v3/v4 跨版本混用。
4. split 必须是任务级切分：同一 task_id 不能同时出现在五个 split 任一之中；split_digest 覆盖全部五个 split 的 120 个任务并由程序计算、复核；五集合 task_id 两两互斥。
5. 任务数（60/20/20/10/10）、B、seed 数量必须在 preregistration 中冻结；打开 meta_test 后不得增删任务或改终点；OOD/负控结果不得并入主结论；不做事后任务剔除。
6. 旧冻结 run 的 run_config.json/summary.json/data_manifest.json 与产物文件不得修改；新版本只新增文件与新的 digest 记录。旧 S0-2 白名单只允许 legacy 只读复现，不得被改写或重签。

## 6. 确定性 digest 规范

### 6.1 canonical JSON

1. 对象键按 Unicode 码点升序排序；数组保持原顺序；无多余空白（separators=(',',':')）；UTF-8 编码；NaN/Infinity 禁止出现。
2. 浮点数使用 Python repr 的最短往返表示；禁止字符串化后再比较；布尔与 null 使用 JSON 原生字面量。
3. digest = SHA-256(规范字节串) 的 64 位小写十六进制；文件级 digest 用原始字节（不解析）。

### 6.2 必须记录的 digest

| digest 名称 | 覆盖内容 | 生成时机 |
|---|---|---|
| task_fingerprint | 任务定义（不含 split/seed） | 任务生成时 |
| family_digest | 整个 family 生成配置（含 family_version、family_seed、holdout_seed、生成规则与 evaluator 配置） | family 冻结时 |
| split_digest | 全部五个 split（120 任务）的 task_id 有序列表，按 §3.2 表顺序串联 canonical JSON 后哈希 | 冻结时 |
| prereg_digest | preregistration.json canonical digest | 冻结时 |
| run_config_digest | run_config.json canonical digest | run 启动前 |
| data_manifest_digest | data_manifest.json（文件路径+sha256） | run 结束后 |
| result_digest | 评价记录/最终统计（不含时间戳） | run 结束后 |

### 6.3 复算与不可变性

- 每个 run 必须支持“同输入 → 同 digest”复算；复算脚本只读，不得覆盖原 run。
- 旧 run 的 SHA256SUMS 与 manifest 由 A3 留档；任何 SHA 变化视为旧工件改写并 fail-closed。
- 环境（git_sha、Python/torch 版本、CPU 线程数）写入 run_config；环境差异不得被悄悄忽略。

## 7. preregistration schema（新版本）

必填字段与类型校验：

| 字段 | 类型 | 必填 | 校验 |
|---|---|---|---|
| schema_version | string | 是 | 固定 p4ra-prereg-v1（本阶段冻结名）；若复用 A1 已实现的 p4-m5-prereg-v2 校验路径，须在报告中显式声明并保持 stopping_rules 规则一致（D-S0-2-06） |
| prereg_id | string | 是 | 唯一；与 family_version 关联 |
| family_version | string | 是 | 固定 p4ra-family-v4；与任务文件一致；禁止 v3/v4 跨版本混用 |
| family_id | string | 是 | 固定 F-QE-feasible-v3；解析分布未变，仅 holdout 重采样 |
| holdout_seed | int | 是 | 固定 20261106；仅用于 meta_test 20 + meta_test_ood 10 的重采样 |
| holdout_splits | object | 是 | 必须精确为 {"meta_test":20,"meta_test_ood":10}；其余 split 计数不变，且与 split_counts 一致 |
| holdout_package | object | 是 | 固定 object：run_id（格式 `p4ra-s0-4-freeze-<UTC>Z`）、family_version="p4ra-family-v4"、holdout_seed=20261106、split_counts={"meta_test":20,"meta_test_ood":10}、task_count=30（=holdout_task_count=计数和）、frozen_family_sha256（64 hex）、package_path="research/concorde_metaopt/optimization_runs/<run_id>"；verifier 强校验 run_id 正则、package_path 为仓库相对路径且无盘符/`..`、frozen_family_sha256 与冻结件一致、task_count=计数和；旧 p4ra-s0-2/s0-3 冻结包仅 legacy 只读，不得作为 S1 确证输入 |
| split_counts | object | 是 | 必须精确为 {meta_train:60, meta_validation:20, meta_test:20, meta_test_ood:10, negative_control:10}，合计 120 |
| split_digest | string(64 hex) | 是 | 覆盖全部五个 split 的 120 个 task_id（§3.2 顺序）；与 family v4 split_hash 一致 |
| task_id_regex | string | 是 | 固定 `^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$`；附“与 M2/M5/M6 零交集”程序断言 |
| frozen_at_utc | string | 是 | ISO-8601；冻结后不得改 |
| primary_endpoints | [enum] | 是 | 只允许 best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate；禁止别名 first_feasible_evaluation_index；不得为空 |
| secondary_metrics | [string] | 是 | RMSE、MAE、可行率、代理时间、峰值内存等 |
| budget_plan | object | 是 | B∈{64,128}、K∈{0,1,3,5}、initial_designs=8、support_counted=true、五臂 billable=B、K=0 的 FOMAML-Kshot/ZeroShot 登记 CLONE |
| task_counts | object | 是 | 五 split 计数与 split_counts 一致；meta_test 精确 20（或负责人书面批准的扩大依据） |
| seeds | object | 是 | meta_train_seeds≥3、optimization_seeds≥10 |
| stopping_rules | [string] | 是 | **必须是非空 list[str]，每项 strip 后长度≥2**；禁止 str 被序列化成单字符数组；新 run 标 v1 一律 fail-closed |
| failure_rules | [string] | 是 | 明确失败/停止/不作结论的条件 |
| c5_policy | object | 是 | 固定 {mode:"C5_B_STRUCTURAL_IDENTIFIABILITY", overlap_threshold:0.90, c5_benefit_harm_inference:false, c5_in_holm:false, min_estimable_tasks:10, below_min_conclusion:"NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY"}；规则见 §7.2 |
| structural_identifiability | object | 是 | pair-level 预注册：每个 (task,B,K,meta_seed) 的每个臂对计算初始设计行 digest 的 overlap_rate；>=0.90 判该臂对在该组 STRUCTURALLY_IDENTICAL；排除出 benefit/harm 推断；报告 structural_exclusion_counts 与 C5 可估计任务数；不做事后任务剔除 |
| multiple_comparison | object | 是 | 方法与家族；预注册；**唯一 Holm 族定义**=(primary_endpoint, budget_B, K)：族内为该组全部可推断臂对比较（C1–C4，C5 排除；pair-level STRUCTURALLY_IDENTICAL 行级排除），族大小≤4；禁止"同 K 内 32 检验"或"每端点 5 检验"等其它口径；C5 不进入任何 benefit/harm 推断与 Holm 族（C5-B） |
| analysis_plan_digest | string(64 hex) | 是 | 分析脚本 canonical digest；脚本必须使用 ENDPOINT_ROW_KEYS 同一组 ID；必须加载并消费每个 source run 的 identifiability_report.json，缺失即 fail-closed |
| prereg_digest | string(64 hex) | 是 | 自身 canonical digest（计算时置空该字段） |

### 7.1 旧缺陷修正（只作用于新版本）

- stopping_rules 序列化/类型校验缺陷的准确定位（HEAD a331639e）：STOPPING_RULES 定义在 research/concorde_metaopt/meta_learning/feasible_v2.py:130-136；:1077 是调用参数默认值（不是定义）；旧序列化缺陷点在 :1111。A1 修复后（A5 审阅时点）：normalize_stopping_rules 位于 :151-197，build_preregistration 落盘前 normalize 在 :1144-1197（落盘点 :1190），schema 校验在 :200-219。A1 文件当前未提交，冻结前以 Lead 固定 commit 后重新记录的 SHA 与行号为准。
- 新版本必须按上表做类型校验：stopping_rules 为 list[str] 且每项 strip 后 len≥2；反序列化后再次校验。旧冻结 run 的 preregistration.json 保持原样，不修补、不重写；修正只在新 schema 与新增校验中体现。
- legacy 路径（D-S0-2-06）：legacy v1 仅用于只读验证历史 M5；新 run 目录/新 prereg 标 v1 → fail-closed；校验结果记录 legacy_warning 供 A5/Lead 确认。
- 校验失败抛 DataContractError/FeasibleV2Error 类异常并 fail-closed，不得用默认值静默填充。

### 7.2 C5-B 结构性不可辨识预注册规则（R-V4-02 / R-V4-04）

1. 对每个 `(task, budget_B, K, meta_seed)` 组，对每个臂对计算初始设计行 digest 的 `overlap_rate`（定义：交集行数 / 较大集合行数；实现须与 A5 S1R2-m03 口径一致）；`overlap_rate >= 0.90` 判该臂对在该组 `STRUCTURALLY_IDENTICAL`。
2. 结构性相同臂对不进入 benefit/harm 推断，只作描述性记录；不做事后任务剔除；每个比较的排除率必须在 aggregate/CSV 中披露。
3. C5（FOMAML-KSHOT-BO vs FOMAML-ZERO-BO，K>0）**不进入任何 benefit/harm 推断与 Holm 族**，只报告结构克隆率/描述性数值；若可推断组覆盖任务数 < 10，总结论固定为 `NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY`，不得声称适应增益或损害。
4. `identifiability_report.json` 必须逐 pair 输出 `pair_identifiable`、`structural_status`（IDENTIFIABLE / STRUCTURALLY_IDENTICAL）、`threshold`；顶层输出 `pair_status_counts`；组级 `ranking_status` 仅作描述、不作推断依据。分析脚本必须加载每个 source run 的该报告，校验 schema、组覆盖与 `(task,B,K,meta_seed,arm)` 一致；formal 缺失即 fail-closed；aggregate/CSV 输出 `structural_exclusion_counts` 与 C5 可估计任务数。
5. C5-B 不改变总体结论仍只依赖 C1 的预注册规则；C5-B 的负结果/不可估计本身不得被写成“MAML 无效”或“MAML 有效”。
6. **Holm 族唯一定义（R-V4-08-01）**：族键 = `(primary_endpoint, budget_B, K)`；每族包含该族键下全部可推断臂对比较（C1–C4），C5 永不进族；pair-level STRUCTURALLY_IDENTICAL 行按行排除后，族实际大小可 <4，预注册/代码/统计计划必须使用同一动态族大小口径；任何其它口径（如同 K 内 32 检验、每端点 5 检验）一律作废。
7. prereg 必须落盘 `holdout_package`（object，见 §7 表）、`c5_policy`（object，固定字段 mode/overlap_threshold/c5_benefit_harm_inference/c5_in_holm/min_estimable_tasks/below_min_conclusion）、`structural_identifiability`（object，pair_overlap_threshold=0.90、pair_status_above_threshold="STRUCTURALLY_IDENTICAL"、pair_status_below_threshold="IDENTIFIABLE"、overlap_definition="intersection_size/max(set_size)"、exclude_from_benefit_harm_inference=true、exclude_from_holm=true、post_hoc_task_exclusion=false、report_structural_exclusion_counts=true、report_c5_estimable_task_count=true）；verifier 对三键做类型/取值/交叉一致性强校验；analysis formal 模式必须加载并校验三键；Holm 族按 §7.2 第 6 条唯一口径动态计算。

## 8. Fail-closed 条件（必须实现为程序化断言）

| 代码 | 条件 | 处理 |
|---|---|---|
| FC-01 | 读取 query/未授权标签，或把参考最优点当支持标签 | 停止 run，写 JSON 事件+中文报告 |
| FC-02 | 支持样本 K 次评价未计入 B，或五臂 billable 不等于 B，或各臂评价次数不等 | 停止并作废该 run |
| FC-03 | B/K/initial_designs/split_counts 与 prereg 不一致 | 拒绝启动 |
| FC-04 | 旧冻结 run 文件 SHA 变化或 manifest 不一致 | 停止，通知 A3/A5 |
| FC-05 | physical_call_count>0 或出现真实求解器启动记录 | 立即停止，上报 Lead |
| FC-06 | task_id 跨 split 重复，或新旧任务族 task_id 冲突，或五 split 未覆盖全部 120 任务 | 拒绝生成/启动 |
| FC-07 | 缺少 prereg、prereg 打开 meta_test 后变更、digest 不匹配 | 拒绝运行/作废结果 |
| FC-08 | evaluator 字段缺失/枚举非法（如 real_solver、VALIDATED 无证据） | 拒绝运行 |
| FC-09 | 任务数/seed 数低于冻结计划 | 不进入正式分析，只作 pilot |
| FC-10 | meta_test 打开后调参、改终点、按效果剔除任务 | 结果作废并记录事件 |
| FC-11 | 端点 ID 不在 ENDPOINT_ROW_KEYS、prereg 使用禁用别名 first_feasible_evaluation_index，或统计列键未登记 | 拒绝运行/作废统计 |
| FC-12 | 新 run 使用 legacy prereg schema v1 | 拒绝启动 |
| FC-13 | task_id 不匹配 §3 正则，或 family_id/family_version 与冻结值不一致 | 拒绝生成/启动 |
| FC-14 | 使用旧 p4ra-family-v3/S0-2 包做 S1 确证、holdout_seed/holdout_splits 缺失或与 20261106 不一致、或把 v3/v4 任务/工件跨版本混用 | 拒绝启动；旧包只允许历史复现/负控 |
| FC-15 | 在 C5-B 下仍对 C5 做 benefit/harm/Holm 推断，或 C5 可估计任务数<10 仍给 C5 结论 | 拒绝/作废 C5 推断，只保留结构性诊断 |

事件 JSON 至少含：event_code、run_id、task_id、detected_at_utc、evidence_path、action_taken、notified_to=[Lead,A5]。

## 9. 与现有代码的映射（只读引用；修改由 Lead 派修复卡）

| 文件:行 | 现状 | 本合同要求 |
|---|---|---|
| research/concorde_metaopt/meta_learning/data_contract.py:110 DataContractError、:132 validate_split、:169 MetaSample、:229 validate_sample | 已有基础字段校验与 split 校验 | 扩展五值 split、task_id 正则/family_id、split_digest、prereg/digest 字段与 §8 断言 |
| adaptation.py:243-248 adapt_and_predict、:293/:302 k_shot==0 分支、:328 inner_steps=max(1,...) if k_shot>0 | 已支持 k_shot 适应 | S1 复用它并确保支持标签来自真实评价且计入 B |
| baseline_arms.py:944-946 predict_proxy_targets(support_features,support_targets,k_shot)、:962-965 强制 supports、:1016-1018 score_maml_init_designs | 已有支持集入口 | 作为 S1 的受控接口；端点输出键按 §3.3 登记 |
| m5_arms.py:504-514 score_m5_init_designs 签名无 support_features/support_targets；:585 run_m5_bo_arm；:636-644 调用未传 k_shot/support；:623 默认 adaptation_k_shot=0 | K-shot 未闭环进正式 BO 初始化 | S1-11 修复：加参数、显式传支持集、K=0 兼容旧行为；五臂 billable=B 断言 |
| maml.py:292/:317/:361 create_graph=False；无 FULL_MAML | 仅 FOMAML | S2 新增 FULL_MAML 可微内循环与元梯度门禁 |
| feasible_v2.py:130-136 STOPPING_RULES 定义；:1077 参数默认值；:1111 旧序列化；修复后 normalize :151-197、build 落盘 normalize :1144-1197（落盘点 :1190）（HEAD a331639e + A5 审阅时点） | 旧版序列化缺陷；A1 已修复未提交 | 新版本按 §7.1 修复并测试；旧 run 不改；Lead 固定 commit 后复核哈希 |
| baseline_arms.py 端点输出键与 m5_runner.py 读取列名（M5 A5-M5-01 前例，见 docs/reviews/p4_meta_m5_report_20261104.md:130） | 曾因输出键/列名不一致导致端点列全 null | 新版本统一 §3.3 规范 ID，ENDPOINT_ROW_KEYS 显式登记，禁止别名与静默映射 |

## 10. 验收标准（S0 可检查项）

1. 本合同（v1.3）被 Lead/A5 审阅，字段与 Issue #7 §2 S0、R-V4-01..06、R-V4-08 逐条对应；A5-S0-M01/M02/m01/m02/m09 与本版 §7.2/FC-14/FC-15 可逐条核对（§3.2、§3.3、§5、§7、§7.1、§7.2）。
2. 新版本 schema 具备 §7 类型校验与 §8 至少 FC-01/02/03/05/06/07/11/12/13/14/15 的程序化断言；五 split enum、120 任务计数、family_version=p4ra-family-v4、holdout_seed=20261106、holdout_splits 有 schema 校验。
3. 端点 ID 统一为 4 个规范 ID，ENDPOINT_ROW_KEYS 已登记，存在“禁用别名/未登记键 → fail-closed”的负控测试，并有合成端到端非空覆盖断言；C5-B 下 C5 不进入 benefit/harm 与 Holm。
4. 五臂 × K∈{0,1,3,5} × B∈{64,128} 共 40 组预算公平性单测通过（billable=B），K 未计入即 fail-closed；K=0 的 FOMAML-Kshot/ZeroShot CLONE 识别测试通过。
5. 旧 M2/M5/M6、D-12D-005 与旧 p4ra-s0-2-freeze-20261105T072500Z 的 SHA256 前后一致（A3 出具只读证明）；旧包不得改写、不得用于 S1 确证。
6. v4 新任务族与旧 task_id 零交集（程序输出 split/family 清单），task_id 正则单测通过；v4 的 meta_test/meta_test_ood task_fingerprint 与 v3 官方包 120 个 fingerprint 零交集（legacy 280 个 task_id 仅做 task_id 零交集），meta_train/meta_validation/negative_control 映射与 S0-2 逐项相同。
7. 所有物理调用计数为 0，且 run_config 留痕。
8. 任一 fail-closed 条件均能产生事件 JSON 与中文报告。
9. Holm 族动态大小回归（R-V4-08-01）：族内比较由 4 降为 3（行级排除）时 p_adj 必须重算且 C5 不出现在任何 p_adj 行；prereg/统计计划/代码 docstring 使用同一族键 $(primary_endpoint, budget_B, K)$。

## 11. 待决策项

1. A1 在最终代码 commit C 的干净 detached worktree 生成 S0-4 冻结包（run_id p4ra-s0-4-freeze-<UTC>Z；两独立进程 run1/run2 逐字节一致；prereg 含三键；determinism_report 进 payload 链）；Lead 将其写入仓库并提交 commit D；A2 重建正式工件/readiness（v4c）；A3 审计 C/D；A5 phase4 终审（v4c 修复 + merge delta + phase3 findings 关闭）通过后才可申请 APPROVE_FOR_S1_RUN。旧 S0-3 包转历史只读、不得用于 S1 确证。
2. C5-B 的 prereg 文本、identifiability_report.json schema 与 analysis 消费实现由 A1/A6 落地；A5 在 phase3 核对；C5 不进入 benefit/harm/Holm。
3. Full MAML 元梯度一致性阈值与统计判定规则（S2 前冻结）。
4. 是否允许 S1 pilot 后按计划扩大合成训练（仍需 physical_call_count=0）。
5. 数据合同是否在 S4 复用同一 schema_version，或另立 p4ra-aero-api-v1。
6. 旧 S0-2 包/旧 A5 批准范围收窄的 Issue #7 回执披露时点（A5-S1R2-M03）。

## 12. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4 | 首次生成 S0 数据合同与预注册规范草案 |
| v1.1 | 2026-11-05 | A4（task-197） | 按 D-S0-2-01..09 与 A5 S0 审阅：五 split（§3.2/§5/§6.2/§7）、端点 ID 与语义（§3.3/§7/§8 FC-11）、stopping_rules len≥2（§7/§7.1）、行号引用修正（§7.1/§9）、task_id 正则（§3/§7）、五臂预算映射（§4.2）；关闭 A5-S0-M01/M02/m01/m02/m09 合同侧口径；未修改旧 run，未执行任何物理计算 |
| v1.2 | 2026-11-05 | A4（task-231） | 按 A5 S1 rev2（S1R2-B01/B02）与 R-V4-01..06：family_version p4ra-family-v4、holdout_seed=20261106、S0-3 冻结包替代 S0-2 确证用途、旧 S0-2 包只读、prereg 新增 holdout_seed/holdout_splits/holdout_package/c5_policy/structural_identifiability、§7.2 C5-B 规则、FC-14/FC-15、v4 验收项；未修改旧 run，未执行物理计算，未 commit/push |
| v1.3 | 2026-11-06 | Lead（R-V4-08） | 按 A5 phase3（S1R3-B01/B02/M01/M02/m01-m03）：holdout_splits 改 object、holdout_package 改 object 并补 verifier 级校验、prereg 三键 schema 精确化、Holm 族唯一口径 (endpoint,budget,K) 动态族大小、C5 排除、S0-4 冻结包替代 S0-3 确证用途、determinism_report 进 payload 链、analysis code_sha/legacy fail-closed；§10 增 4→3 p_adj 回归；§11 S0-4 阶段门；未修改旧 run，0 物理，未 commit/push |
