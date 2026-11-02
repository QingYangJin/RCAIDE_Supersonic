# P4-M0 12D 元学习软件设计文档（合成任务离线阶段）

| 项 | 内容 |
|---|---|
| 文档状态 | DESIGN v1.4（2026-11-02 修订 4）：v1.3 已按 A5 M1 代码复核（1 blocker/5 major/4 minor）修订并新增 §10.1 P4-CODE 可识别臂裁决（M1-F05）；v1.4 按 A5 M1 rev3 复核（0 blocker / 3 open major / 3 minor 新增）把 §0/§10/§11 与 §10.1 对齐（预注册推断仅用三可识别臂；pretrain/MAML 标 CLONE_OF_OPT-BO-rand 且仅作描述性记录），并补 M1-F10 映射与代码 rev4 落点；本文档不含任何物理结论 |
| 任务 | task-49（P4-M0 A1：12D 元学习软件设计文档，中文） |
| 作者/角色 | A1（a1-code-dev）初稿；Lead 修订 1（2026-11-02，A5 独立复核后） |
| 工作树 | D:/RCAIDE-p4-meta-learning，分支 research/p4-meta-learning，起点 bf6c052 |
| 授权层级 | P4-CODE（结构代码/单元测试/合成元训练/离线 BO-DE 对照） |
| 物理调用 | physical_call_count = 0；solver_starts = 0；未运行 Mission/VSPAERO/SU2/WaveDrag/Gmsh/DOE/BO 真值 |
| 上游依据 | docs/planning/p4_meta_learning_implementation_plan_20261102.md（正式计划）；Issue #5 / D-P4-001；A2 设计 EXT/p4-meta-dev/a2/p4_offline_experiment_matrix.md + p4_schemas.json；M2 五臂以 A2 §5 与 Issue #5 为准（原 Lead 消息 m00606 引用撤回，不可独立复核，见修订 1 m-01） |
| 只读参考 | maml-opt 0.1.0（D:/RCAIDE/envs/RCAIDE/Lib/site-packages/maml_opt）；主库 D:/RCAIDE 未跟踪 P5 文件（仅只读参考，不移植、不复制） |

---

## 0. 范围与相对第一步草稿的变更

第一步草稿见 EXT/p4-meta-dev/a1/design_draft.md（256 行 / 18010 B，sha256 ec1e0917...）。本正式文档对其做了三处按 Lead 决策的修订：

1. **M2 执行 A2 的五臂等预算矩阵**（§10），不再使用草稿 §9 的"四臂"命名（A-random / A-pretrain-zero-shot / A-pretrain-finetune / A-maml）。五臂是：OPT-BO-rand、OPT-BO-pretrain、OPT-BO-MAML、OPT-BO-MAML-init、OPT-DE。**推断限制**：按 §10.1 可识别臂裁决，预注册终点统计/图/回执/结论只引用可识别臂 {OPT-BO-rand、OPT-BO-MAML-init、OPT-DE}；OPT-BO-pretrain/OPT-BO-MAML 标 CLONE_OF_OPT-BO-rand，仅作描述性记录。
2. **M1 的 R/P/M × K∈{0,1,5,10} 代理臂是独立诊断**（§9），不与 M2 优化表混表、不共用同一终点判定。
3. CSV 字段、任务规模、预算与容差全部对齐 A2 的 p4_offline_experiment_matrix.md / p4_schemas.json（§11），避免 A1 实现与 A2 统计两张皮。

本文档是**软件接口与实验合同**，不是物理可信性声明；任何"改进"只能表述为合成任务上的算法机制证据。

### 0.1 修订 1（v1.1，2026-11-02）——回应 A5 M0 审阅

A5 M0 审阅结论为 CHANGES_REQUESTED（0 blocker / 8 major / 10 minor，依据 EXT/p4-meta-dev/a5/m0_design_review.md 与 findings.csv）。本修订逐项处理：
- M-01 需求映射与交付清单缺失 → §11.1（需求→章节/产物映射）、§11.2（统一运行目录清单，含 solver_validation.csv 与图4/图5 归口）；
- M-02 baseline_bo/de 复用与依赖分析 → §8.1（复用表、预算语义、12D 适配、依赖版本表）；
- M-03 split 枚举缺 OOD/负控制 → §3.2 与 §5.2 枚举扩展、§4.3 五集合定义；
- M-04 负控制定义与互斥冲突 → §4.3 负控制伪任务生成/打乱/登记协议（伪任务 ID 独立、不参与训练）；
- M-05 MAML-init 参数未冻结 → §8.2（candidate_count=64、initial_design_count=8、diversity_candidate_count=64、seed 冻结）；
- M-06 确定性缺整 run 重跑 → §12 测试 15（seed 0 整 run ×3，metrics 逐位一致）；
- M-07 evaluator physical>0 注入负控制 → §12 测试 14（注入 physical_call_count=1 必须中止）；
- M-08 15D 无参默认回归 → §2.3（无参默认 15D，12D 仅显式路径）与 §12 测试 16。
minor m-01..m-10 的处置见 §16 修订记录表。

---

## 1. 授权边界与不可越界清单

### 1.1 当前获批（P4-CODE）

- 算法结构代码、类型/接口、单元测试与契约测试；
- 合成任务族的生成、元训练、快速适应、离线 BO/DE 对照；
- 对外部记忆与 run 目录写 JSON/CSV/PNG（物理调用为 0）；
- 读取 maml-opt 0.1.0 公开 API 与 P4 分支既有只读源码。

### 1.2 明确未获批（一律写 NOT_APPROVED，不得以代码默认值悄悄越过）

| 项 | 状态 | 约束 |
|---|---|---|
| P4-REAL-LF（真实 RCAIDE 单巡航调用） | NOT_APPROVED | 需单独批准预算与 fidelity 合同 |
| P4-MULTIFIDELITY-REAL（真实 HF+LF） | NOT_APPROVED | 需保真度配对与气动口径相容证明 |
| 真实跨任务元训练 | NOT_APPROVED | 现有 10 条归档 Mission 仅 5 feasible，不足 |
| VSPAERO 7.2.2 修复与重跑 | 归 Issue #4 / D-12D-004 | 不计入 P4 代码任务，P4 不消费未验证气动标签 |
| 把合成结论升级为 Mach 2.02 真实收益 | 禁止 | 报告须标 SYNTHETIC_ONLY |

### 1.3 硬隔离（实现层门禁）

- meta_learning/* 与 optimization/meta_bo_initialization.py 禁止 import：evaluation.low_fidelity、RCAIDE Mission 入口、任何 OpenVSP/VSPAERO/SU2/Gmsh 调用面。
- 所有离线产物必须显式写 physical_call_count: 0；offline_runner 启动时断言，结束时回读断言。
- 失败/异常一律如实落盘（status、错误类型、traceback 摘要），不得伪造目标值、不得以惩罚常数冒充失败代价。
- 合成标签 data_origin=SYNTHETIC_TEST，物理标签 SIMULATION；两者不得混入同一训练集，除非显式 source 隔离并单独报告。

---

## 2. 12D 设计空间、归一化与解码链

### 2.1 声明变量（顺序冻结，来自 configs/design_space_12d_lifting_surfaces.yaml）

| ID | name | 单位 | 下界 | 上界 | baseline | 归一化 baseline |
|---|---|---|---|---|---|---|
| W01 | wing_area | m^2 | 300.0 | 420.0 | 358.25 | 0.4854166667 |
| W02 | aspect_ratio | - | 1.50 | 2.20 | 1.83 | 0.4714285714 |
| W03 | sweep_1 | deg | 62.0 | 72.0 | 67.0 | 0.5 |
| W04 | sweep_2 | deg | 40.0 | 56.0 | 48.0 | 0.5 |
| W05 | sweep_3 | deg | 66.0 | 76.0 | 71.0 | 0.5 |
| W06 | span_location_2 | - | 0.35 | 0.58 | 0.480469 | 0.5672565217 |
| W07 | span_location_3 | - | 0.85 | 0.98 | 0.945313 | 0.7331769231 |
| W08 | chord_ratio_2 | - | 0.30 | 0.50 | 0.408284 | 0.54142 |
| W09 | chord_ratio_3 | - | 0.08 | 0.20 | 0.130178 | 0.41815 |
| W10 | tip_twist | deg | -4.0 | 4.0 | 0.0 | 0.5 |
| V01 | vertical_tail_area | m^2 | 28.0 | 40.0 | 33.91 | 0.4925 |
| V02 | vertical_tail_sweep_delta | deg | -10.0 | 10.0 | 0.0 | 0.5 |

注：W06/W08/W09/V01 的归一化 baseline 由 u=(v-lower)/(upper-lower) 手算，四位小数仅作阅读参考（W06 按 yaml 0.480469 计算为 0.5672565217，旧稿误写 0.5672739130）；实现一律调用 DesignVariable.to_unit_interval()，不在文档中作为权威数值。

### 2.2 固定机身（F01–F03，owner 决策 2026-10-30）

| ID | name | 值 | 来源 |
|---|---|---|---|
| F01 | fuselage_length | 61.66 m | 模型计算值（非上游声明） |
| F02 | fuselage_fineness | 4.30 | 模型计算值 |
| F03 | fuselage_height_width_ratio | 1.152778 | 模型计算值 |

固定机身**不删除、不优化、不作为网络输入维**；保留在 fixed_variables 与 baseline_geometry 中供几何重建与可追溯性。上游声明值（如机身湿面积 442.0 m²、机翼根弦 33.8 m）保留在 upstream_declared，仅作交叉核对。

### 2.3 归一化与解码（唯一允许路径）

- 归一化：u_i = (v_i - lower_i) / (upper_i - lower_i)，u ∈ [0,1]^12。不做按任务的数据统计重标定（避免任务泄漏）。
- 反归一化与解码：

  1. u ∈ [0,1]^12
  2. DesignSpace.from_unit_interval(u) → 物理 12 名 dict（只含声明变量）
  3. DesignSpace.expand(physical) → 完整 15 名物理向量（F01–F03 自动取 fixed_variables.baseline）
  4. DesignSpace.check_bounds(physical) / check_cross_constraints(physical) → 违规即 INVALID
  5. 解码后的 15 名向量才可交给几何模型/评估器

- 契约事实（已只读核对 research/concorde_metaopt/aircraft/design_space.py）：
  - expand() 拒绝未声明变量（如直接传 15 名向量会抛 DesignSpaceError）；固定值绝不来自调用方；
  - 12D 加载校验：load_design_space() 要求 12d_lifting_surfaces 恰有 3 个固定变量，且 id/name 顺序等于 FIXED_FUSELAGE_IDS / FIXED_FUSELAGE_NAMES；15d 配置不得声明 fixed；
- DesignSpace 已有 from_unit_interval()/to_unit_interval()（research/concorde_metaopt/aircraft/design_space.py:279-285 附近）；缺的是 12→15 合并解码入口，因此 12D 唯一路径仍是 from_unit_interval → expand。
- 交叉约束（YAML cross_constraints）原样继承：C01 span_location_2 < span_location_3；C02 chord_ratio_3 < chord_ratio_2 < 1.0；其余见 YAML。违规设计不得进入训练/优化数据。
- bounds 状态如实标注：frozen: false、bounds_status: provisional_until_geometry_perturbation；不得在报告中写成已冻结。
- 旧 15D 默认行为（M-08）：load_design_space() 无参调用必须仍然加载 configs/design_space_15d.yaml（15 变量、无 fixed、design_set="15d"），既有 P1-P3/历史脚本行为不变；12D 仅在显式传入 design_space_12d_lifting_surfaces.yaml 路径时生效。新增回归测试 §12 T-16，禁止把 12D 设为无参默认。
- config_hash：对 design space YAML 规范化字节 + 变量顺序 + task config + family config 取 sha256，写入每条样本、dataset manifest 与 run_config。

### 2.4 固定几何来源（baseline_geometry，仅引用不重算）

- 主翼：投影展长 25.604638 m（全展，与 yaml projected_span_m 语义一致，不得当半展用）；根弦 29.901819 m；尖弦 0.973136 m；taper 0.032544；MAC 18.489893 m；暴露面积 358.25 m²；段展向分数 [0.0, 0.480469, 0.945313, 1.0]。
- 垂尾：投影展长 5.009331 m（全展，同上不得当半展）；根弦 13.157616 m；MAC 8.124385 m；段展向分数 [0.0, 0.4, 1.0]。
- 机身：长 61.66 m、宽 2.88 m、高 3.32 m、湿面积 488.922167 m²。
- 来源字段 status: p1_geometry_model_derived；这些数值是几何模型计算值，不是本轮重算结果（本轮 physical_call_count=0）。

---

## 3. TaskSpec 与元学习数据合同

### 3.1 物理任务合同（只读复用，不在 P4 改写）

复用 research/concorde_metaopt/tasks/task_spec.py:FixedCruiseTask 与 configs/task_fixed_cruise.yaml：

- task_id = concorde-fixed-cruise-p2-v1；version = p2-2026-10-29b；
- 巡航：Mach 2.02、高度 18288.0 m、距离 3028020.0 m；
- 质量：OEW 78700 kg、payload 9500 kg、cargo 1000 kg、fuel_loaded 46800 kg、start 136000 kg、max_fuel 95680 kg、max_zero_fuel 92000 kg、max_takeoff 185000 kg；
- 目标：fuel_burn_kg（kg）；约束 10 项 g<=0，顺序冻结：geometry_invalid、task_mass_balance、fuel_capacity_excess、zero_fuel_excess、takeoff_excess、fuel_remaining_deficit、max_throttle、cruise_range_error、mission_convergence、trim_attitude_limit；可行性容差 1e-12。
- FixedCruiseTask.fingerprint() = sha256(compact sorted JSON(to_dict()))；run_record() 追加 task_fingerprint 与 task_spec_version；maml_context() 提供 11 个数值上下文键；to_maml_task_spec() 返回 maml_opt TaskSpec(task_id, context, model_config)，其中 model_config 含 aircraft=Concorde、mission_contract=single-fixed-cruise-p2-v1、objective、objective_unit、propulsor_tags、cruise_config_tag、task_spec_version、task_fingerprint。
- P4 合成阶段**不调用**该物理任务，只复用其指纹/上下文/约束顺序，保证未来 P4-REAL-LF 数据合同同构。

### 3.2 元学习样本合同（P4 定义，每条样本全字段）

| 字段 | 类型 | 约束 |
|---|---|---|
| task_id | str | 任务唯一身份；split 只按它划分 |
| fidelity | str | synthetic / single_cruise / ...（取真实保真度标识） |
| evaluator_id | str | 命名规则 source_kind__fidelity__design_set__version，如 synthetic__analytic__12d_lifting_surfaces__v1、validated_real_lf__rcaide_single_cruise__12d_lifting_surfaces__p2v1；真实 evaluator 在 P4-CODE 默认不可达（构造即抛 NotImplementedError） |
| design_set | str | 12d_lifting_surfaces |
| design | float[12] | 物理值，顺序冻结 W01..V02 |
| design_normalized | float[12] | u∈[0,1]，与 design 一一对应 |
| config_hash | str | sha256(space+task+family config) |
| objective | float 或 null | 失败/无效必须 null，不得填 0 或惩罚值 |
| constraints | {str: float 或 null} | 10 项几何/任务 g<=0 语义；合成任务启用的槽位按 §4.4 命名规则，未启用槽位为 null（语义=未启用，不是满足/不满足） |
| status | str | VALID / FEASIBLE / INFEASIBLE 属 maml-opt LABEL_STATUSES；INVALID / GEOMETRY_INVALID / MISSION_FAILED / MISSION_NOT_CONVERGED / NONFINITE / PARTIAL_RESULT 属 EXCLUDED_STATUSES（maml_opt/data/dataset.py:14/:17）；P4 合成只用 VALID/INFEASIBLE/INVALID/NONFINITE，禁止自造第三套枚举 |
| source_kind | enum | synthetic / archived_real_lf / validated_real_lf / validated_real_hf |
| physics_validation_status | enum | NOT_APPLICABLE / NOT_VALIDATED / PARTIAL / VALIDATED |
| git_sha | str | 记录产生时 commit；未知写 UNKNOWN 并标 warning；工作树 dirty 时写 <sha>-dirty，且该样本不得进入结论表/正文，仅作调试（m-10） |
| seed | int | 生成/评估种子 |
| physical_call_count | int | 离线必须 0 |
| split | enum | meta_train / meta_validation / meta_test / meta_test_ood / negative_control（内部数据合同五值，按 task_id 划分，五集合互斥见 §4.3；写入 schema-2 archive 时必须经 §3.3 映射为三值，不得直接写五值） |
| task_context | {str: float} | 合成 2 维上下文（数值）；物理可为空；OOD 标记用数值键 ood_flag=1.0，不得写 bool/字符串 |
| created_utc | str | ISO-8601 UTC |

联合校验：source_kind=synthetic ⇒ physics_validation_status=NOT_APPLICABLE；validated_real_hf ⇒ VALIDATED；objective 非 null 时必须有有限数值且 status 属 VALID/FEASIBLE/INFEASIBLE（INFEASIBLE 仍保留 objective，不得置 null；objective=null 仅限 EXCLUDED_STATUSES 中的失败/无效状态）；约束必须全为有限 float 或 null。data_contract.validate_sample() 返回错误列表，写入 archive 前任何错误即整体失败，不做自动修复。

### 3.3 归档映射（复用 maml-opt schema-2，不造第二套格式）

- 使用 maml_opt.data.archive.write_archive(...) 生成 observations.jsonl + manifest.json（schema_version=2、state=FROZEN/UNFROZEN、records_sha256）。
- manifest 必填：dataset_id、task_split_id、task_splits（train/validation/test 任务 id 列表）、design_feature_names（12）、task_context_names、target_names、target_map（objective→{source:"objective"}，约束→{source:"constraints_g_le_zero", key}）、feature_units/target_units、records_file、records_sha256。
- 五值内部 split → schema-2 三值 archive 映射（M-03）：meta_train→train；meta_validation→validation；meta_test→test；meta_test_ood→test 且样本 task_context.ood_flag=1.0；negative_control 不写入三值 archive（仅记录在 tasks.json 与 tasks/negative_control_manifest.json，绝不进入训练或主终点统计）。archive 的 task_splits 恰为 train/validation/test 三键；内部五值互斥由 data_contract.assert_task_disjoint 保证，映射由 to_archive_splits() 单向完成并加断言测试。ood_flag 仅作 OOD 元数据，不进入 task_context_names 或 14 维特征（特征仍为 §3.1 的 2 维 context_1/context_2）。
- TaskDataset.load() 会校验 feature_names=design+context、target_map 键集合=target_names、任务 split 归属；P4 数据合同测试必须覆盖这些失败分支。
- build_dataset_archive(history_root, run_ids, ...) 仅用于未来真实 run（从 EvaluationManager 的 run_manifest/evaluation_log 构建）；P4 合成阶段用 write_archive 直接写 records，并用 audit_archive() 复核 labeled_records/task_counts/data_origins。
- data_origin 取值：合成 SYNTHETIC_TEST；禁止把 P5 的 15D RFF 数据集直接当 12D 数据（维度/身份都不匹配）。

---

## 4. 合成任务族设计

### 4.1 总体

- 输入 u ∈ [0,1]^12；每任务 2 维上下文 context_1/context_2 ∈ [0.6,1.4]（固定 seed 采样）。
- task_id = sha1(family_id | params_json | seed)[:12]；参数一经采样即写入 tasks.json，不得事后按测试集调整。
- 每族输出：目标 f(u) 与 1–3 个 g(u)<=0 约束；参考最优 (u*, f*) 由解析式或 KKT 枚举给出，并按 |f(u*)-f*| ≤ 1e-10·max(1,|f*|) 断言；任一任务断言失败即整族标记 FAILED，不进入矩阵。
- 所有族确定性：同 seed 同参数逐位可复现；记录拒绝采样次数（参考点越界、约束不可行等）。

### 4.2 四族

| 族 | 目标 | 约束 | 参考最优 | 用途 |
|---|---|---|---|---|
| F-QE | f=b+Σa_i(u_i-c_i)^2 | 椭球 Σw_i(u_i-d_i)^2 ≤ r^2 | 解析投影：若 √W(c-d) 范数≤r 则 u*=c，否则 u*=d+W^{-1/2}·r·ŷ | 核心家族，K-shot 主判据 |
| F-LIN | 同 F-QE | 2 个线性约束 p·u≤q、s·u≤t | 活动集枚举 {1}/{2}/{1,2} 解等式 QP，取可行最小；断言 KKT 残差<1e-9 | 约束处理诊断 |
| F-NC | Rastrigin f=120+Σ[(u_i-c_i)^2-10cos(2π(u_i-c_i))] | 球 ‖u-c‖^2≤r^2，r<0.5 | 解析全局最优 f*=0,u*=c | BO 全局性/局部极小 |
| F-MF | f_L 二次；f_H=f_L+γ·v·(u-c)+δ | 同 F-QE | LF 解析；HF 用 KKT_CERTIFIED_NUMERIC（残差<1e-9） | 仅多保真消融，不进主矩阵 |

族参数分布（固定入库）：c_i~U(0.15,0.85)、a_i~LogU(0.5,5)、r~U(0.15,0.45)、w_i~LogU(0.5,5)、b~U(-1,1)；F-MF 的 γ、v、δ 分布由 task_family.py 固定并写入 family_fingerprint。

### 4.3 规模、划分与负控制（与 A2 对齐）

| 集合 | 任务数 | 用途 |
|---|---|---|
| meta-train | 60 | 外循环/预训练/长度尺度标定 |
| meta-val | 20 | 仅超参与早停选择 |
| meta-test | 20 | 最终结论唯一来源 |
| meta-test-OOD | 10 | 上下文中心整体平移 +0.2、r 缩小 30%；单列报告 |
| negative-control | 10 | 由 10 个不同 meta-train 任务派生的伪任务（label-shuffle，见 §4.3 协议）；仅评估诊断，不进训练、不进主终点 |

- 每任务：query 64 点（独立 LHS seed）；support 候选池 128 点（另一 LHS seed）；K=0/1/5/10 取池按 seed 置换后的前 K 点。
- 任务身份互斥（M-03/M-04）：meta_train/meta_validation/meta_test/meta_test_ood/negative_control 五集合的 task_id 两两交集为空；OOD 与负控制都使用新 task_id（不得复用原任务 id 作为 split 标签）。
- 负控制协议（M-04）：对第 i 个来源任务，pseudo_task_id = "NC-" + sha1("negative_control|" + source_task_id + "|" + shuffle_seed)[:10]；打乱种子 shuffle_seed = 20261102 + i，仅打乱该伪任务内部的 objective/constraints 与 design 的配对（同一 seed 逐位可复现），不改 context/params；伪任务与原任务、与训练集合均互斥；split manifest 记录 source_task_id 映射；负控制结果单列，禁止进入主终点或用于调参。
- OOD 协议：meta-test-OOD 用新 task_id（context 中心整体 +0.2、r 缩小 30%），单列报告，不参与超参选择。
- 泄漏断言：support∩query=∅（design 精确比较，容差 1e-12）；K 增大只能从 128 点池取更多点，不得取到 query；adaptation 路径不得读 query 标签；归一化用任务参数而非测试集统计。

---

### 4.4 合成约束命名槽位与状态映射（m-05/m-07）

- 约束键名与槽位映射（m-05）：constraints 字典键集合恒等于 10 项物理约束名且顺序固定 = [geometry_invalid, task_mass_balance, fuel_capacity_excess, zero_fuel_excess, takeoff_excess, fuel_remaining_deficit, max_throttle, cruise_range_error, mission_convergence, trim_attitude_limit]；前 3 个键承载合成约束槽位 synth_c01/synth_c02/synth_c03（synth_c01→geometry_invalid、synth_c02→task_mass_balance、synth_c03→fuel_capacity_excess），其余 7 个键显式写 null；每任务启用 1-3 个槽位，未启用槽位在 constraints 中写 null 并记录在 task.params.enabled_slots。
- objective/status 映射：有可行且有限的参考评价 → status=VALID、objective=有限值；解析上不可行（g>0 无可行域） → INFEASIBLE、objective=null；设计越界/交叉约束违规 → INVALID 或 GEOMETRY_INVALID、objective=null；数值非有限 → NONFINITE、objective=null。禁止用 0 或大惩罚值代替 null。
- CSV 统计时 null 约束按未启用剔除（denominator 只算启用槽位），并在 metrics.csv 的 n 字段记录启用的约束数。

## 5. meta_learning/ 六模块接口与签名

通用约定：类型标注仅供契约；运行环境必须 CPU≤4 核、确定性 seed；仅复用 maml-opt 0.1.0 公开 API（contracts/evaluation/initialization/bayesian/learning/data），不复制 P5 仓库代码。torch 缺失时相关测试标 NOT_RUN（不得假装通过）。

### 5.1 meta_learning/task_family.py

    @dataclass(frozen=True)
    class TaskFamilyConfig:
        family_id: str
        design_dim: int
        context_names: tuple[str, ...]
        seed: int
        train_tasks: int
        validation_tasks: int
        test_tasks: int
        ood_tasks: int
        negative_control_tasks: int
        designs_per_task: int
        support_pool_size: int
        query_size: int
        reference_tolerance: float = 1e-10

    @dataclass(frozen=True)
    class SyntheticTask:
        task_id: str
        split: str
        family: str
        context: Mapping[str, float]
        params: Mapping[str, Any]
        seed: int
        def truth(self, designs: np.ndarray) -> dict[str, np.ndarray]  # objective + constraints + feasibility
        def reference(self) -> dict[str, Any]                          # u*, f*, reference_kind, assertion_residual

    def load_task_family_config(path: Path | None = None) -> TaskFamilyConfig
    def build_task_family(config: TaskFamilyConfig) -> list[SyntheticTask]
    def sample_designs(task: SyntheticTask, count: int, kind: str, seed: int) -> np.ndarray
    def family_fingerprint(config: TaskFamilyConfig) -> str
    def assert_reference_solutions(tasks: Sequence[SyntheticTask]) -> dict[str, float]

### 5.2 meta_learning/data_contract.py

    SOURCE_KINDS = ("synthetic", "archived_real_lf", "validated_real_lf", "validated_real_hf")
    PHYSICS_STATUSES = ("NOT_APPLICABLE", "NOT_VALIDATED", "PARTIAL", "VALIDATED")
    SPLITS = ("meta_train", "meta_validation", "meta_test", "meta_test_ood", "negative_control")
    LABEL_STATUSES = ("VALID", "FEASIBLE", "INFEASIBLE")            # 与 maml_opt 一致
    EXCLUDED_STATUSES = ("INVALID", "GEOMETRY_INVALID", "MISSION_FAILED", "MISSION_NOT_CONVERGED", "NONFINITE", "PARTIAL_RESULT")
    EVALUATOR_ID_PATTERN = "<source_kind>__<fidelity>__<design_set>__<version>"
    def validate_split(split: str) -> None   # 非 SPLITS 一律 DataContractError

    @dataclass(frozen=True)
    class MetaSample:  # §3.2 全字段
        ...

    def validate_sample(sample: MetaSample) -> list[str]
    def require_valid(sample: MetaSample) -> None                      # 抛 DataContractError
    def split_by_task(samples, fractions, seed) -> dict[str, list[MetaSample]]
    def assert_task_disjoint(*splits) -> None
    def support_query_split(samples, task_id, k_shot, query_size, seed) -> tuple[list, list]
    def from_ledger_row(row, *, task_id, config_hash, git_sha, source_kind, physics_validation_status) -> MetaSample
    def to_archive_records(samples) -> list[dict[str, Any]]
    ARCHIVE_SPLIT_MAP = {"meta_train": "train", "meta_validation": "validation", "meta_test": "test", "meta_test_ood": "test"}  # negative_control 不入三值 archive
    def to_archive_splits(samples) -> dict[str, list[str]]      # 仅 train/validation/test 三键，M-03 映射

### 5.3 meta_learning/surrogate.py

    @dataclass(frozen=True)
    class SurrogatePrediction:
        mean: np.ndarray
        uncertainty: np.ndarray | None = None   # 未标定必须 None，不得冒充

    class ResponseSurrogate(Protocol):
        input_dim: int
        def fit(self, features: np.ndarray, targets: np.ndarray) -> "ResponseSurrogate"
        def predict(self, features: np.ndarray) -> SurrogatePrediction

    def encode_features(designs, task_context, context_names) -> np.ndarray
    def regression_metrics(prediction, target) -> dict[str, float]   # rmse/mae/r2/max_abs_err/rank corr/top-k overlap
    def select_objective_and_constraint_targets(target_names) -> tuple[int, tuple[int, ...]]

### 5.4 meta_learning/maml.py

    @dataclass(frozen=True)
    class MAMLConfig:
        input_dim: int
        output_dim: int
        hidden_sizes: tuple[int, ...] = (64, 64)
        inner_lr: float = 0.01
        inner_steps: int = 5
        outer_lr: float = 1e-3
        tasks_per_batch: int = 8
        first_order: bool = True
        seed: int = 42
        backend: str = "torch"  # torch | numpy；numpy 仅降级路径

    @dataclass
    class ParameterSet:
        tensors: list[np.ndarray]

    def init_parameters(config: MAMLConfig, seed: int) -> ParameterSet
    def inner_adapt(params, support, config) -> tuple[ParameterSet, list[float]]
    def meta_train_step(params, batch, config) -> tuple[ParameterSet, dict[str, float]]
    def meta_train(tasks, config, max_steps: int) -> dict[str, Any]
    def finite_difference_gradient_check(model, batch, epsilon: float = 1e-5, tolerance: float = 1e-4) -> dict[str, Any]

- 一阶（first_order=True）为 M2 必要路径；二阶仅在资源批准且数值检查通过后另立任务。
- 每步记录 seed、step、loss_support、loss_query、grad_norm、lr、wall_s；非有限 loss 立即终止并 mark NONFINITE。

### 5.5 meta_learning/adaptation.py

    @dataclass(frozen=True)
    class AdaptationResult:
        method: str          # none | fine_tuning | maml | from_scratch
        k_shot: int
        inner_steps: int
        predictions: np.ndarray
        targets: np.ndarray
        losses: tuple[float, ...]
        metrics: Mapping[str, float]
        physical_call_count: int   # 恒 0

    def adapt_and_predict(artifact, support, query, method, k_shot, config) -> AdaptationResult
    def run_k_shot_study(artifact, tasks, ks, seed) -> list[AdaptationResult]

### 5.6 meta_learning/offline_runner.py

    @dataclass(frozen=True)
    class OfflineRunnerConfig:
        run_id: str
        output_root: Path
        family_config_path: Path | None
        ks: tuple[int, ...] = (0, 1, 5, 10)
        seed: int = 42
        max_meta_steps: int = 2000
        budget_true_evaluations: int = 64
        bo_initial_designs: int = 8
        de_population: int = 8
        de_generations: int = 8
        # 修订 1 冻结字段（M-05/M-06/M-07）
        maml_init_candidate_count: int = 64
        maml_init_initial_designs: int = 8
        maml_init_diversity_candidate_count: int = 64
        determinism_reruns: int = 3
        physical_guard_expected: int = 0
        optimization_seeds: tuple[int, ...] = (0, 1, 2, 3, 4)  # A8：正式 run 必须 5 seeds；单测可小集合

    def run_offline_study(config: OfflineRunnerConfig) -> dict[str, Any]
    def main(argv: Sequence[str] | None = None) -> int

输出（与 A2 对齐；修订 1 统一清单，M-01/m-06）：

- run_config.json（字段见 §11）、environment.json、summary.json、data_manifest.json；
- tasks.json、reference_solutions.json、README.md；
- metrics/training_history.csv、metrics/adaptation_results.csv、metrics/metrics.csv、metrics/optimization_history.csv、metrics/optimization_summary.csv；
- solver_validation.csv（Issue #5 §4 要求；P4-CODE 阶段所有行 status=NOT_RUN 或 NOT_APPLICABLE_THIS_STAGE，note 写明 VSPAERO 验证归口 Issue #4 D-12D-004，本阶段不画图4）；
- evaluations.jsonl、figures/fig1..fig5（中文标题，缺失显示 NOT_RUN，禁止假图）；
- 启动/结束均断言 physical_call_count=0；任何 evaluator 报告 physical_call_count>0 立即中止并写 status=PHYSICS_GUARD_VIOLATION（不得照常写 0）。

---

## 6. support/query 不重叠与按任务身份 split（合同级）

1. 任务 split 以 task_id 为键，meta-train/val/test/OOD/negative-control 五者任务身份互斥；任何样本不得跨 split。
2. 同任务内 support 与 query 设计集合按 design 精确比较（容差 1e-12）必须不相交；K 增大只能从 128 点池取更多点，不得取到 query 点。
3. 适应阶段（inner loop / fine-tune）只允许接触 support；query 标签只在评估函数内部一次性使用。
4. 超参、早停、meta 长度尺度只允许用 meta-train（标定）与 meta-val（选择）；meta-test 只评估一次。
5. 任何上述检查失败 → 对应测试 FAIL，禁止降级为 warning；offline_runner 直接中止并写失败 summary。

---

## 7. MAML 一阶实现与有限差分梯度检查

### 7.1 实现路径

- 首选：复用 maml_opt.learning.training.train_maml(dataset, config, output_root, run_id, allow_synthetic_for_tests=True)；config 键：episode.support_design_count/query_design_count、response_model.hidden_sizes、meta_training.{meta_batch_size,steps_per_epoch,outer_epochs,inner_learning_rate,inner_steps,second_order,gradient_clip,device,seed}、early_stopping.{patience,min_delta}。
- 数据输入必须是 TaskDataset（schema-2 archive），且 labeled_tasks 满足 train≥2、validation≥1、test≥1；输出 summary status 在合成数据下为 SYNTHETIC_TEST_ONLY。
- 预训练对照用 train_conditional_pretraining(dataset, config, output_root, run_id, ...)；配置块为 episode + training。
- 若实现自写核心（numpy 降级），必须与 maml_opt 产物字段兼容，并在 summary 标 backend: numpy、equivalence_claimed: false。

### 7.2 有限差分检查（强制门禁）

- 模型：input_dim=12、output_dim=2（目标+1 个合成约束）、hidden=(8,8)、1 步内循环、双精度。
- 方法：对 3–5 个参数分量做中心差分 (L(θ+ε)-L(θ-ε))/(2ε)，ε=1e-5；与解析/自动微分梯度比较相对误差；阈值 tolerance=1e-4。
- 结果落盘 finite_difference_check.json：参数名、解析值、数值值、绝对/相对误差、epsilon、tolerance、PASS/FAIL。
- FAIL 时 M2 不得启动（summary.status=FINITE_DIFFERENCE_FAILED），并保留原始数组供复核。

---

## 8. BO 初始化接口 meta_bo_initialization

    @dataclass(frozen=True)
    class InitialDesignProposal:
        designs: tuple[tuple[float, ...], ...]   # 物理 12 维，固定顺序
        scores: tuple[float, ...]
        metadata: Mapping[str, Any]               # artifact sha256、adaptation_method、pool digest、seed

    def meta_bo_initialization(design_space, artifact, task_context,
                               candidate_count: int = 64,        # 修订 1 冻结（M-05）
                               initial_design_count: int = 8,    # 修订 1 冻结（M-05）；适配层映射到上游 shortlist
                               adaptation_method: str = "maml",
                               seed: int = 42) -> InitialDesignProposal
    def compare_initializers(design_space, artifact, tasks, methods, budget, seed) -> dict[str, Any]

- 复用 maml_opt.initialization.prepare_model_scored_initial_designs / select_model_scored_initial_designs 的公开签名；传入 LoadedModelArtifact，features 顺序必须 = design_feature_names + task_context_names。
- 单位门禁：合成设计空间 units 全 "1"；物理 SI 设计空间不得误入该路径（测试覆盖）。
- 关键隔离：预测标签只能用于"先评估哪些点"的排序，绝不写入 BO observations；观测只能来自真实（合成）评估结果。测试断言 observations 长度只随真实评估增长。
- 与既有基线共用同一真值评估预算与可行性判据；不修改 optimization/baseline_bo.py / baseline_de.py。
- 返回的 designs 必须在界内、去重，并记录候选池 digest 与 artifact sha256，保证可追溯。
- MAML-init 冻结（M-05，§8.2）：candidate_count=64、initial_design_count=8、diversity_candidate_count=64、seed 显式传入；代理打分只用于排序，不得进入 BO observations。

---

### 8.1 与既有基线复用分析（M-02）

| 复用对象 | 位置 | 复用内容 | M2 对应臂 | 适配/差异 |
|---|---|---|---|---|
| baseline_bo.py | research/concorde_metaopt/optimization/baseline_bo.py | run_baseline_bo()（默认 budget=30、initial_design_count=5、strategy=bayesian）、maml_opt.bayesian 的 ConstrainedBayesianOptimizer/run_search/generate_initial_designs、EvaluationLedger(cache_enabled=True)、_DuplicateTolerantOptimizer | OPT-BO-rand（基线语义） | P4 合成臂不 import 物理 SingleCruiseBackend；预算改 B=64、初始 8 点；复用搜索机制与缓存双计数语义，不改 baseline_bo.py 本体 |
| baseline_de.py | research/concorde_metaopt/optimization/baseline_de.py | run_baseline_de()（默认 budget=30、population/mutation/crossover 默认）、DifferentialEvolutionBaseline（8 代×8 个体） | OPT-DE | 以合成 evaluator 替换物理 backend；budget=64、population=8、generations=8；不改 baseline_de.py 本体 |
| 10 项约束顺序/容差 | research/concorde_metaopt/evaluation/contract.py | CONSTRAINT_NAMES、FEASIBILITY_TOLERANCE=1e-12 | 全臂 | 原样复用，禁止重排 |
| 评估缓存语义 | maml_opt EvaluationLedger | 缓存命中不计 billable、但记 requested/billable 双计数 | 全臂 | 原样复用并落 optimization_history.csv 的 cache_hit/billable |
| 设计空间 | research/concorde_metaopt/aircraft/design_space.py | from_unit_interval/expand/check_bounds/check_cross_constraints | 全臂 | 12D 显式路径，经 expand 得 15D 再进评估器 |

实现方式：新增 meta_learning/baseline_arms.py，仅组合上述公开函数/类；不得复制 P5 代码、不得修改 baseline_bo.py/baseline_de.py；每个臂在 run_config.json 记录 implementation=reuse:<module>:<function>。

依赖版本表（environment.json 必填，本次实测）：Python 3.11.17；numpy 2.4.6；torch 2.8.0+cpu；scipy 1.17.1；scikit-learn 1.9.1；matplotlib 3.11.2；maml_opt 0.1.0；Windows CPU（无 GPU）。

### 8.2 MAML-init 参数冻结（M-05）

- candidate_count=64（模型打分候选池）、initial_design_count=8（最终交给 BO 的初始点）、diversity_candidate_count=64、seed 显式（由任务 seed 派生，禁止默认 42 静默）。
- 与 maml_opt.initialization.prepare_model_scored_initial_designs / select_model_scored_initial_designs 的参数名对齐（initial_design_count、diversity_candidate_count）；若上游签名不同，以适配层显式映射并在 run_config 记录 upstream_signature。
- 记录 proxy_scoring_cost（候选数、预测次数、wall_s）；该成本不计入 true_evaluation_budget=64，但必须在报告中单列。
- 候选去重容差 1e-12；不足 8 个唯一候选时整臂 FAIL（不得静默放宽阈值）。

## 9. M1 代理诊断矩阵（独立，不与 M2 混表）

| 臂 | 定义 | 说明 |
|---|---|---|
| R | 随机初始化 MLP，同预算训练 | 基线 |
| P | meta-train 普通监督预训练 + support 微调相同步数 | 隔离先验 |
| M | MAML-A 一阶快速适应 | 主诊断 |

- K ∈ {0,1,5,10}；K=0 为零样本（不更新参数），三臂都报告。
- 适应预算 S_adapt=50 步（meta-val 选一次，全臂共享）；预训练/外循环预算各自记录总步数与墙钟。
- 每任务指标：RMSE、MAE（原始与按 support 目标尺度归一化两套）、R²、max_abs_err；非有限状态记 NONFINITE 且计入分母。
- 终点：meta-test 上 K=5 的 query RMSE（MAML vs P、MAML vs R）为预注册主终点；K=0/1/10 为次终点。OOD 单列。
- 本矩阵只回答"代理是否快速适应"，不回答"优化是否更好"；结论不得外推到 M2 或真实物理。

---

## 10. M2 等预算五臂优化矩阵（A2 §5 矩阵；Lead 2026-11-02 确认，替换草稿四臂；推断仅限 §10.1 可识别臂）

统一设定：同一合成任务集（meta-test 20 + OOD 10 单列）、seeds={0,1,2,3,4}、true_evaluation_budget=64、同一可行性判据（g<=0，容差 1e-12）、同一缓存规则（缓存命中不计 true 预算，但记 requested/billable 双计数）。每 run 恰好消耗 64 次真实（合成）评价。

| 臂（精确命名） | 初始 8 点来源 | 代理来源 | 作用 |
|---|---|---|---|
| OPT-BO-rand | 共享 LHS 8 点 | 每任务从头 GP（普通约束 BO） | 基线 |
| OPT-BO-pretrain | 同一 8 点 | 条件预训练代理（零样本或 support 微调，按 M1 选定） | 描述性：P4-CODE 与 rand 同机制（CLONE_OF_OPT-BO-rand），禁用于代理先验归因；真隔离须 P4-REAL-LF 或新授权 |
| OPT-BO-MAML | 同一 8 点 | MAML 适应后代理 | 描述性：P4-CODE 与 rand 同机制（CLONE_OF_OPT-BO-rand），禁用于代理先验归因 |
| OPT-BO-MAML-init | MAML 代理从 64 候选池排序出的 8 点 | MAML 适应后代理 | 隔离"初始化选择"效应；初始点不同但数量相同 |
| OPT-DE | 同一 8 点（=种群 8） | 无 | DE/rand/1/bin 语义，8 代×8 个体=64 |

- **推断限制（§10.1 优先）**：预注册终点统计、图、回执与结论只引用可识别臂 {OPT-BO-rand、OPT-BO-MAML-init、OPT-DE}；OPT-BO-pretrain/OPT-BO-MAML 只作描述性记录（CLONE_OF_OPT-BO-rand），不得据此声称代理先验效应；若克隆臂与 rand 数值逐位相同，属预期（不可识别性的实证）。

- BO 执行：8 初始 + 56 次采集；DE 执行 8×8=64；两者预算严格相等。
- 共享初始点由同一 (task, seed) 的 LHS seed 生成并在臂间复用；记录 initial_feasible_count；MAML-init 例外但同样 8 点、同任务同 seed 可复现，参数冻结见 §8.2（candidate_count=64、diversity_candidate_count=64）。
- 约束与失败：g>0 即不可行；失败/非有限目标为 null，不得用大惩罚值伪造；失败评价计入预算并记 status。
- 每 run 指标：best_feasible_value（无可行 null）、gap_to_reference = best − f*、first_feasible_eval_index（1-based，无则 null）、feasible_count、violation_rate、true_evals_used、cache_hits、wall_s、n_failed_evals。
- F-QE 可行域极小的披露与 fallback（A7，2026-11-02 Lead 裁决）：F-QE 的可行域为 12 维加权球 r∈[0.15,0.45]，体积占比约 1e-6，B=64 下可识别三臂很可能全部 0 可行。此时主终点如实为 null（禁止写成 0/大惩罚），并同时报告三项 fallback 指标用于同等比较：best_objective_raw（该臂全部评价中的最小原始目标）、min_constraint_violation_sum（对应最好目标设计的 sum(max(0,g))）、feasible_hit_rate=feasible_count/true_evals_used；optimization_summary.csv 需含 feasibility_expected_zero 注记与 n_feasible；结论表须披露“主终点不可比、仅 fallback 可比”，不得据 fallback 宣称优于基线。
- 正式 M2 run 的 run_config 必须写 actual_seeds（=optimization_seeds 实际值，5 个），单测可减少但不得替代正式 run。
- 预注册终点：优化侧 first_feasible_eval_index 与 best_feasible_value（B=64）；统计任务×seed 配对（20×5=100 对）报告配对中位差 + bootstrap 95% CI（10,000 次）与 Wilcoxon 参考；不显著即如实报"无改进"。
- 负控制：label-shuffle、K=0、OOD、参考解断言。若 MAML 无改进，禁止改基线/指标/阈值。

---

### 10.1 P4-CODE 可识别臂裁决（Lead 2026-11-02；回应 A5 M1-F05）

**事实**：maml-opt 0.1.0 的公开 API 只在“初始点选择”处接受模型先验（`select_model_scored_initial_designs`）；BO 采集阶段没有公开的代理注入入口。按 §1.3 硬隔离，不调用私有 API、不修改 `baseline_bo.py`、不伪造先验。

**裁决**：
1. P4-CODE 阶段的**可识别臂集合**（primary/secondary 对比唯一允许使用的臂）= {OPT-BO-rand, OPT-BO-MAML-init, OPT-DE}。三者机制不同：从头 GP + 共享 LHS 8 点 / MAML 代理从 64 候选池排序出的 8 点 / 无代理 DE 8×8。
2. OPT-BO-pretrain 与 OPT-BO-MAML 在 P4-CODE 与 OPT-BO-rand **机制相同**（同 BO 实现、同 8 初始点、同 GP、同预算），只是元数据标签不同；二者**不得**用于任何“代理先验效应”归因，M2 产物与报告中必须标 `identifiability=CLONE_OF_OPT-BO-rand`，并披露“若与 rand 数值逐位相同，属预期（不可识别性的实证）”。
3. 预注册终点（§10）的统计、图、回执与结论只允许引用可识别臂；禁止声称“预训练代理/MAML 代理在 BO 中带来改进”。若要真正隔离代理先验，须在 P4-REAL-LF 或新授权下用公开 API 可支持的采集注入重新设计并重新预注册。

**能力边界**：本裁决不降低 M2 预算/统计要求（B=64、5 seeds、配对 bootstrap/Wilcoxon 不变），只是把不可识别臂排除出归因结论。**本裁决优先于 §10 表格中任何“主对照/隔离效应”措辞；如两者冲突，以本节为准。**

## 11. 产物、CSV schema 与运行目录（对齐 A2）

运行目录：research/concorde_metaopt/optimization_runs/p4-synthetic-<UTC>Z/（P4 分支）。每次 run 含：

- run_config.json：run_id、git_sha、worktree_dirty、seed、family/split id、seeds、actual_seeds、预算（true_evaluation_budget=64、bo_initial=8、de=8×8、S_adapt=50）、ks、tolerance、物理调用声明、primary_endpoint（预注册）、secondary_endpoints、negative_control_protocol、statistics（配对中位差、bootstrap 95% CI 10,000 次、Wilcoxon 参考）、determinism_reruns=3、maml_init 冻结参数、evaluator_id、identifiable_arms、clone_arms、arm_identifiability（§10.1 可识别臂标签）、implementation 标签；
- environment.json：python、numpy/scipy/scikit-learn/torch/matplotlib 版本（torch 可缺）、maml_opt 版本、平台、CPU 核数；
- summary.json：status、arms（全五臂描述性结果）、identifiable_arms/clone_arms/arm_identifiability、终点统计（仅可识别三臂，另附 all_arms_descriptive 描述性块）、失败数、physical_call_count、PHYSICS_GUARD 结果、NOT_APPROVED 列表；
- data_manifest.json：每文件 sha256+bytes、hash_mode（CRLF→LF 规范化）、file_count、total_bytes，排除自身；
- CSV 同 A2 列名：training_history.csv、adaptation_results.csv、metrics.csv、optimization_history.csv、optimization_summary.csv；
- solver_validation.csv：列 run_id, case_id, evaluator_id, solver_family, status, note；P4-CODE 阶段每行 status=NOT_RUN 或 NOT_APPLICABLE_THIS_STAGE；
- figures/fig1..fig5 由 A2 消费 CSV 生成（中文标题；fig3 仅可识别三臂 OPT-BO-rand/OPT-BO-MAML-init/OPT-DE）；P4-CODE 阶段 fig1/fig2/fig3/fig5 在数据产生后生成，fig4（VSPAERO 新旧对比）归口 Issue #4 D-12D-004，本阶段 NOT_RUN；缺失一律显示 NOT_RUN，禁止画假数据。

### 11.1 需求映射（M-01）

| 需求来源 | 需求 | 本设计章节/产物 | P4-CODE 状态 |
|---|---|---|---|
| Issue #5 §2 M0 | 设计复用分析、12D 解码、TaskSpec、模块接口、split | §2、§3、§5、§6 | 本文档 |
| Issue #5 §2 M1 | 元学习模块 + 测试 | §5、§7、§12 | 待实现（M1） |
| Issue #5 §2 M2 | 等预算优化对照 | §8、§10 | 待实现（M2） |
| Issue #5 §4 图1 | MAML 训练损失 | figures/fig1_meta_training_loss.png | 数据后生成 |
| Issue #5 §4 图2 | K-shot 适应精度 | figures/fig2_k_shot_adaptation.png | 数据后生成 |
| Issue #5 §4 图3 | 等预算优化收敛 | figures/fig3_equal_budget_convergence.png | 数据后生成 |
| Issue #5 §4 图4 | VSPAERO 新旧版本 | figures/fig4_vspaero_version_panel_density.png | NOT_RUN（归口 Issue #4） |
| Issue #5 §4 图5 | 预算/门禁进度 | figures/fig5_budget_gate_progress.png | 数据后生成 |
| Issue #5 §4 | solver_validation.csv | §11 solver_validation.csv | NOT_RUN 占位（归口 Issue #4） |
| A4 F-01..F-05 | 五张中文图 | 图1-图5 | 同图1-图5 |
| A4 T-01 | P4 交付物清单 | §11 统一清单 | M4 生成 |
| A4 T-04 / V-06 | VSPAERO 线证据 | 不在 P4 run；见 Issue #4 D-12D-004 run 目录 | 归口 Issue #4 |
| A4 V-01..V-12 | VSPAERO 验证需求全集 | 仅 V-06 在本轮 §11 solver_validation.csv 留占位；V-01..V-05、V-07..V-12 标 NOT_APPLICABLE_THIS_STAGE | 归口 Issue #4，P4-CODE 不消费 |
| A4 BW-04 | 文档/图表中文 | 全文 | 本文档中文 |
| D-12D-004 | VSPAERO 修复/验证 | 不进入 P4-CODE；物理标签不消费 | 不在本阶段授权 |

### 11.2 统一运行目录清单（m-06）

每 run 目录固定文件集（manifest 必须全覆盖，缺项按 NOT_RUN 记录）：run_config.json、environment.json、summary.json、data_manifest.json、tasks.json、tasks/negative_control_manifest.json、reference_solutions.json、evaluations.jsonl、README.md、solver_validation.csv、metrics/{training_history,adaptation_results,metrics,optimization_history,optimization_summary}.csv、figures/fig1..fig5（缺失显示 NOT_RUN）。

---

## 12. 测试清单（全部非物理）

1. 12D 解码：from_unit_interval→expand 得到 15 名；传 15 名向量必须抛 DesignSpaceError；固定值不可覆盖；越界报 INVALID。
2. 交叉约束：span_location_2≥span_location_3 或 chord_ratio_2≤chord_ratio_3 等违规必须被拒。
3. 数据合同：缺字段、非法 source_kind/physics_validation_status 组合、objective 非空但 status 无效 → 拒收。
4. split：train/val/test 任务互斥；support/query 不相交；构造泄漏用例必须 FAIL。
5. 合成族：同 seed 逐位复现；参考解断言 PASS；label 确定性；拒绝采样数记录。
6. MAML：有限差分 PASS；一阶训练 loss 有限；seed 复现初始化；FAIL 时 summary 状态正确。
7. adaptation：K=0/1/5/10 各跑通；losses 长度=inner_steps；physical_call_count=0。
8. initializer：预测标签不进入 observations；候选在界内且去重；单位门禁拦截 SI 设计空间。
9. offline_runner：产品 JSON 可解析；manifest sha256/bytes 一致；无 RCAIDE/VSPAERO/SU2 import；physical_call_count=0。
10. 回归：python -m unittest discover -s research/concorde_metaopt/tests -t . 仍通过（P4 分支，不改 P1–P3 文件）。
11. 负控制：label-shuffle 后 MAML 优势应回落；K=0 随机臂最差；OOD 性能下降；异常则查泄漏后重跑。

---

T-12 split 枚举（M-03）：SPLITS 五值在内部数据合同可写入；非法 split 抛 DataContractError；写入 schema-2 archive 时必须按 §3.3 映射只出现 train/validation/test 三键（OOD→test 且 task_context.ood_flag=1.0；negative_control 不进三值 archive，单独清单 negative_control_manifest.json），映射函数有断言测试。
T-13 负控制协议（M-04）：伪任务 ID 与来源任务不同；同一 (source_task_id, shuffle_seed) 打乱逐位复现；五集合 task_id 两两交集为空；负控制样本不得进入训练或主终点统计。
T-14 evaluator 物理守卫（M-07）：注入返回 physical_call_count=1 的 evaluator → offline_runner 立即中止，summary.status=PHYSICS_GUARD_VIOLATION，且不得写出正常 0 计数 summary。
T-15 确定性（M-06）：seed=0 整 run 独立重跑 3 次，metrics.csv 与 optimization_summary.csv 逐位一致（float 精确比较；若框架非确定，记录并降级该臂结论，不得静默通过）。
T-16 旧 15D 回归（M-08）：load_design_space() 无参 → 15 变量、无 fixed、design_set="15d"；传 12D 路径 → 12 变量 + 3 fixed；构造参数不得改变无参默认。
T-17 MAML-init 冻结（M-05）：候选池=64、初始点=8、去重容差 1e-12；不足 8 唯一候选时该臂 FAIL。
T-18 solver_validation.csv（M-01）：P4-CODE run 必含该文件，所有行 status 属 {NOT_RUN, NOT_APPLICABLE_THIS_STAGE}，不得出现伪造数值；图4 不在 P4-CODE 生成。

## 13. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 合成→真实过度声明 | 高 | 分层标注 SYNTHETIC_ONLY；报告模板强制物理调用=0；A5 复核 |
| 15D/12D 混淆或泄漏 | 中 | expand 契约 + 维度/身份测试；不消费 P5 15D 数据 |
| 预测标签进入 BO observations | 中 | 接口隔离 + 断言测试 |
| MAML 不稳定/二阶昂贵 | 中 | 一阶优先；有限差分门禁；失败如实落盘 |
| torch 缺失/版本漂移 | 中 | numpy 降级路径并标 backend，不声称等价 |
| support/query 泄漏 | 高影响 | 任务级 split + 设计不相交断言 + A5 复核 |
| P5 只读参考被误当可复制 | 治理 | 文档/代码注释注明只读参考；只用 maml-opt 公开 API |
| 预算/终点事后调整 | 治理 | 预注册终点写入 run_config；改写即记录偏离 |
| evaluator 误报/漏报物理调用 | 高 | §12 T-14 注入 physical>0 负控制；offline_runner 中止写 PHYSICS_GUARD_VIOLATION |
| 负控制身份泄漏/伪任务混入训练 | 高 | 伪任务独立 task_id + split manifest 登记 + 五集合互斥断言 |
| 合成实验不可复现（非确定框架） | 中 | seed0 整 run ×3 逐位检查；不通过即降级该臂结论 |
| 12D 改造回归 15D 默认 | 中 | §2.3 无参默认声明 + §12 T-16 回归测试 |

## 14. 附录 A：只读盘点证据（文件/符号）

| 事实 | 证据位置 |
|---|---|
| 12D 变量与 bounds、固定机身、派生规则 | research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml（variables/fixed_variables/derived_rules/baseline_geometry） |
| DesignSpace API 与 12D 加载校验 | research/concorde_metaopt/aircraft/design_space.py（from_unit_interval/expand/load_design_space/config_summary） |
| 固定巡航任务合同 | research/concorde_metaopt/tasks/task_spec.py（FixedCruiseTask/fingerprint/maml_context/to_maml_task_spec）；configs/task_fixed_cruise.yaml |
| 10 项约束顺序与容差 | research/concorde_metaopt/evaluation/contract.py（CONSTRAINT_NAMES/FEASIBILITY_TOLERANCE） |
| maml-opt 训练与归档签名 | D:/RCAIDE/envs/RCAIDE/Lib/site-packages/maml_opt/{learning/training.py,data/archive.py,data/dataset.py,initialization.py,contracts.py} |
| P4 正式计划与三层门禁 | docs/planning/p4_meta_learning_implementation_plan_20261102.md |
| A2 实验矩阵与 schema | EXT/p4-meta-dev/a2/p4_offline_experiment_matrix.md、p4_schemas.json |
| 基线复用对象与默认预算 | research/concorde_metaopt/optimization/baseline_bo.py:59-61,403-423（DEFAULT_BUDGET=30、DEFAULT_INITIAL_DESIGN_COUNT=5）；research/concorde_metaopt/optimization/baseline_de.py:66,566-590（DEFAULT_BUDGET=30、DifferentialEvolutionBaseline） |
| 依赖版本（实测） | Python 3.11.17、numpy 2.4.6、torch 2.8.0+cpu、scipy 1.17.1、scikit-learn 1.9.1、matplotlib 3.11.2、maml_opt 0.1.0 |
| M2 五臂矩阵 | A2 实验矩阵 §5 + Issue #5；原 Lead 消息 m00606 引用已撤回（不可独立复核，见 §16 m-01） |
| P5 只读参考（不复制） | 主库 D:/RCAIDE：configs/meta_tasks.yaml、data/meta_tasks.py、learning/{adapter,train_baselines,train_maml_a}.py、optimization/{initializer,maml_a_bo}.py |

## 15. 附录 B：状态枚举与术语

- run status：DESIGN_ONLY / NOT_RUN / RUNNING / COMPLETED / FAILED / FINITE_DIFFERENCE_FAILED / SYNTHETIC_TEST_ONLY；
- sample status：VALID / FEASIBLE / INFEASIBLE（LABEL_STATUSES）与 INVALID / GEOMETRY_INVALID / MISSION_FAILED / MISSION_NOT_CONVERGED / NONFINITE / PARTIAL_RESULT（EXCLUDED_STATUSES），与 maml_opt/data/dataset.py:14/:17 对齐；
- source_kind：synthetic、archived_real_lf、validated_real_lf、validated_real_hf；
- 术语：12D=W01–W10+V01–V02；F01–F03 固定机身；S_adapt=50 适应步；B=64 真实（合成）评价预算；M1=代理诊断，M2=等预算优化对照；NOT_APPROVED=未获 owners 书面批准。


## 16. 修订记录

| 修订 | 日期 | 触发 | 内容 |
|---|---|---|---|
| v1.0 | 2026-11-02 | A1 初稿 | 设计文档初稿 |
| v1.1 | 2026-11-02 | A5 M0 审阅 CHANGES_REQUESTED（0 blocker / 8 major / 10 minor） | 见 §0.1 与本表 |
| v1.2 | 2026-11-02 | A5 M0 v1.1 delta 复审 CHANGES_REQUESTED（1 open major M-03 + M-08 值错误） | §3.3/§5.2/§12 T-12 五值→三值 archive 映射；§2.3/§12 T-16 design_set=15d；§4.4 槽位映射；§13 单表；§12 T-12..T-18 编号；§11.1 A4 V-01..V-12 |
| v1.2a | 2026-11-02 | A5 M0 v1.2 delta 复审 CHANGES_REQUESTED（M-03 部分闭合：§3.2 合同冲突） | §3.2 split/task_context 措辞；§3.3/T-12 ood_flag=1.0；§11.2 negative_control_manifest.json；本表 v1.2 行 |
| v1.2b | 2026-11-02 | A5 v1.2a 终核 APPROVE_FOR_M1（1 non-blocking minor） | §3.3 补 ood_flag 不入特征/特征仍为 2 维 context_1/context_2 |
| v1.2c | 2026-11-02 | M1 实现期 Lead 裁决 A7/A8/A9（a6 提出） | §3.2 联合校验允许 INFEASIBLE+objective；§5.6 加 optimization_seeds；§10 加 F-QE fallback 指标与披露；§11 run_config 加 actual_seeds |
| v1.3 | 2026-11-02 | A5 M1 代码复核 CHANGES_REQUESTED（1 blocker/5 major/4 minor） | 新增 §10.1 可识别臂裁决（M1-F05）；M1-F01..F09 由 M1 rev3 代码/测试修复（F01=0f2cf43 等预算；F02 静态扫描；F03 objective=None 反向校验；F04 negative_control_manifest；F06 ood_flag；F07 FD 下界；F08 figure 键名；F09 失败路径） |
| v1.4 | 2026-11-02 | A5 M1 rev3 复核 CHANGES_REQUESTED（0 blocker / 3 open major / 3 minor 新增；F02 CLOSED_WITH_GAP） | §0/§10/§11 对齐 §10.1（预注册推断仅三可识别臂；pretrain/MAML 标 CLONE_OF_OPT-BO-rand 且仅描述性）；§11 run_config/summary/fig3 加可识别性标签；§16 补 M1-F10 映射；代码同步 rev4（offline_runner 打标 + 统计/图过滤，测试补 test_02 断言） |

| 审阅项 | 严重度 | 处置位置 |
|---|---|---|
| M-01 需求映射/交付清单缺 | major | §11.1、§11.2、§12 T-18 |
| M-02 baseline 复用/依赖分析缺失 | major | §8.1 |
| M-03 split 枚举缺 OOD/负控制 | major | §3.2、§4.3、§5.2 |
| M-04 负控制定义与互斥冲突 | major | §4.3 |
| M-05 MAML-init 参数未冻结 | major | §8.2、§5.6、§12 T-17 |
| M-06 缺 seed0 整 run 重跑 | major | §5.6、§12 T-15 |
| M-07 缺 evaluator physical>0 负控制 | major | §5.6、§12 T-14、§13 |
| M-08 缺 15D 默认回归 | major | §2.3、§12 T-16 |
| m-01 m00606 不可复核 | minor | 头部上游依据、§10、§14、§16 |
| M-03 未闭合（v1.2） | major | §3.3 五值→三值 archive 映射 + §5.2 ARCHIVE_SPLIT_MAP/to_archive_splits + §12 T-12 |
| M-03 残留合同冲突（v1.2a） | major | §3.2:161 改内部五值/archive 三值措辞；§3.2:162 task_context 数值合同加 ood_flag=1.0；§3.3/T-12 同步 |
| negative_control_manifest 未入文件集（v1.2a） | minor | §11.2 文件集补齐 |
| §16 缺 v1.2 修订行（v1.2a） | minor | §16 修订表补 v1.2/v1.2a 两行 |
| M-08 值错误（v1.2） | major | §2.3 与 §12 T-16 改为 design_set="15d"（aircraft/design_space.py:197/359） |
| m-05 槽位映射 | minor | §4.4 显式槽位↔物理键名映射 |
| §13 表格断裂 | minor | 风险表合并为单表 |
| m-02 W06 归一化数值 | minor | §2.1 注 |
| m-03 投影半展语义 | minor | §2.4 |
| m-04 decode/encode 表述 | minor | §2.3 |
| m-05 合成约束槽位 | minor | §3.2、§4.4 |
| m-06 输出清单不一致 | minor | §5.6、§11.1/§11.2 |
| m-07 status 语义引用 | minor | §3.2、§4.4、§5.2、§15 |
| m-08 run_config 缺终点/负控制/统计 | minor | §11 |
| m-09 evaluator_id 命名规则 | minor | §3.2 |
| m-10 dirty 工作树规则 | minor | §3.2 |
| M1-F05 三 BO 臂同机制（A5 M1 审阅） | major | §10.1（可识别臂裁决） |
| M1-F01 DE 提前终止（A5 M1 审阅） | blocker | M1 rev2 0f2cf43（已修）+ M1 rev3 回归测试 |
| M1-F02/F03/F04/F06（A5 M1 审阅） | major | M1 rev3 代码/测试（静态扫描/反向校验/负控制清单/OOD flag） |
| M1-F07/F08/F09（A5 M1 审阅） | minor | M1 rev3 代码/测试（FD 下界/figure 键名/失败路径） |
| M1-F10 正式 run actual_seeds（A5 M1 rev3 审阅） | minor | 正式 M2 run 的 run_config.actual_seeds（由 M2 执行落盘验证，不属代码改动） |
| M1R3-M01 v1.3 §0/§10 与 §10.1 矛盾 | major | 本版 §0、§10 对齐 §10.1 可识别臂裁决 |
| M1R3-M02 M2 orchestration 未落可识别臂标签/过滤 | major | M1 rev4 offline_runner（ARM_IDENTIFIABILITY、identifiable_arms、统计/图过滤） |
| M1R3-M03 静态扫描 test_02 空断言 | minor | tests/test_meta_learning_offline_runner.py test_02 补断言 |
| M1R3-M04 §16 缺 M1-F10 映射 | minor | 本表 M1-F10 行 |
| M1R3-M05 A2 p4_schemas.json 旧 figure 键 | minor | A2 同步（外部 schema 文件，另行交付） |
