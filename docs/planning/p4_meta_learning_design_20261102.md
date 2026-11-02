# P4-M0 12D 元学习软件设计文档（合成任务离线阶段）

| 项 | 内容 |
|---|---|
| 文档状态 | DESIGN v1.0（2026-11-02），待 A5 独立复核；本文档不含任何物理结论 |
| 任务 | task-49（P4-M0 A1：12D 元学习软件设计文档，中文） |
| 作者/角色 | A1（a1-code-dev） |
| 工作树 | D:/RCAIDE-p4-meta-learning，分支 research/p4-meta-learning，起点 bf6c052 |
| 授权层级 | P4-CODE（结构代码/单元测试/合成元训练/离线 BO-DE 对照） |
| 物理调用 | physical_call_count = 0；solver_starts = 0；未运行 Mission/VSPAERO/SU2/WaveDrag/Gmsh/DOE/BO 真值 |
| 上游依据 | docs/planning/p4_meta_learning_implementation_plan_20261102.md（正式计划）；Issue #5 / D-P4-001；Lead 决策 m00606（M2 五臂）；A2 设计 EXT/p4-meta-dev/a2/p4_offline_experiment_matrix.md + p4_schemas.json |
| 只读参考 | maml-opt 0.1.0（D:/RCAIDE/envs/RCAIDE/Lib/site-packages/maml_opt）；主库 D:/RCAIDE 未跟踪 P5 文件（仅只读参考，不移植、不复制） |

---

## 0. 范围与相对第一步草稿的变更

第一步草稿见 EXT/p4-meta-dev/a1/design_draft.md（256 行 / 18010 B，sha256 ec1e0917...）。本正式文档对其做了三处按 Lead 决策的修订：

1. **M2 主对照采用 A2 的五臂等预算矩阵**（§10），不再使用草稿 §9 的"四臂"命名（A-random / A-pretrain-zero-shot / A-pretrain-finetune / A-maml）。五臂是：OPT-BO-rand、OPT-BO-pretrain、OPT-BO-MAML、OPT-BO-MAML-init、OPT-DE。
2. **M1 的 R/P/M × K∈{0,1,5,10} 代理臂是独立诊断**（§9），不与 M2 优化表混表、不共用同一终点判定。
3. CSV 字段、任务规模、预算与容差全部对齐 A2 的 p4_offline_experiment_matrix.md / p4_schemas.json（§11），避免 A1 实现与 A2 统计两张皮。

本文档是**软件接口与实验合同**，不是物理可信性声明；任何"改进"只能表述为合成任务上的算法机制证据。

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
| W06 | span_location_2 | - | 0.35 | 0.58 | 0.480469 | 0.5672739130 |
| W07 | span_location_3 | - | 0.85 | 0.98 | 0.945313 | 0.7331769231 |
| W08 | chord_ratio_2 | - | 0.30 | 0.50 | 0.408284 | 0.54142 |
| W09 | chord_ratio_3 | - | 0.08 | 0.20 | 0.130178 | 0.41815 |
| W10 | tip_twist | deg | -4.0 | 4.0 | 0.0 | 0.5 |
| V01 | vertical_tail_area | m^2 | 28.0 | 40.0 | 33.91 | 0.4925 |
| V02 | vertical_tail_sweep_delta | deg | -10.0 | 10.0 | 0.0 | 0.5 |

注：W08/W09/V01 的归一化 baseline 由上式手算，四位小数仅作阅读参考；实现一律调用 DesignVariable.to_unit_interval()，不在文档中作为权威数值。

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
  - 无 decode/encode 便捷方法，12D 唯一路径就是 from_unit_interval → expand。
- 交叉约束（YAML cross_constraints）原样继承：C01 span_location_2 < span_location_3；C02 chord_ratio_3 < chord_ratio_2 < 1.0；其余见 YAML。违规设计不得进入训练/优化数据。
- bounds 状态如实标注：frozen: false、bounds_status: provisional_until_geometry_perturbation；不得在报告中写成已冻结。
- config_hash：对 design space YAML 规范化字节 + 变量顺序 + task config + family config 取 sha256，写入每条样本、dataset manifest 与 run_config。

### 2.4 固定几何来源（baseline_geometry，仅引用不重算）

- 主翼：投影半展 25.604638 m；根弦 29.901819 m；尖弦 0.973136 m；taper 0.032544；MAC 18.489893 m；暴露面积 358.25 m²；段展向分数 [0.0, 0.480469, 0.945313, 1.0]。
- 垂尾：投影半展 5.009331 m；根弦 13.157616 m；MAC 8.124385 m；段展向分数 [0.0, 0.4, 1.0]。
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
| evaluator_id | str | 如 p4_synthetic_analytic_12d_v1；物理为 rcaide_single_cruise |
| design_set | str | 12d_lifting_surfaces |
| design | float[12] | 物理值，顺序冻结 W01..V02 |
| design_normalized | float[12] | u∈[0,1]，与 design 一一对应 |
| config_hash | str | sha256(space+task+family config) |
| objective | float 或 null | 失败/无效必须 null，不得填 0 或惩罚值 |
| constraints | {str: float} | 10 项几何/任务 g<=0 语义；合成任务按 §4 启用子集，其余为 null 并显式标记 |
| status | str | VALID / INFEASIBLE / INVALID / GEOMETRY_INVALID / MISSION_FAILED / NONFINITE ...（复用 maml-opt LABEL_STATUSES 语义） |
| source_kind | enum | synthetic / archived_real_lf / validated_real_lf / validated_real_hf |
| physics_validation_status | enum | NOT_APPLICABLE / NOT_VALIDATED / PARTIAL / VALIDATED |
| git_sha | str | 记录产生时 commit；未知写 UNKNOWN 并标 warning |
| seed | int | 生成/评估种子 |
| physical_call_count | int | 离线必须 0 |
| split | enum | train / validation / test（按 task_id 划分） |
| task_context | {str: float} | 合成 2 维上下文；物理可为空 |
| created_utc | str | ISO-8601 UTC |

联合校验：source_kind=synthetic ⇒ physics_validation_status=NOT_APPLICABLE；validated_real_hf ⇒ VALIDATED；objective 非 null 时必须有有限数值且 status 属 VALID/FEASIBLE；约束必须全为有限 float 或 null。data_contract.validate_sample() 返回错误列表，写入 archive 前任何错误即整体失败，不做自动修复。

### 3.3 归档映射（复用 maml-opt schema-2，不造第二套格式）

- 使用 maml_opt.data.archive.write_archive(...) 生成 observations.jsonl + manifest.json（schema_version=2、state=FROZEN/UNFROZEN、records_sha256）。
- manifest 必填：dataset_id、task_split_id、task_splits（train/validation/test 任务 id 列表）、design_feature_names（12）、task_context_names、target_names、target_map（objective→{source:"objective"}，约束→{source:"constraints_g_le_zero", key}）、feature_units/target_units、records_file、records_sha256。
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
| negative-control | 10 | label-shuffle 的 meta-train 子集 |

- 每任务：query 64 点（独立 LHS seed）；support 候选池 128 点（另一 LHS seed）；K=0/1/5/10 取池按 seed 置换后的前 K 点。
- 泄漏断言：task_id 跨 split 交集为空；support∩query=∅；adaptation 路径不得读 query 标签；归一化用任务参数而非测试集统计。

---

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

    def run_offline_study(config: OfflineRunnerConfig) -> dict[str, Any]
    def main(argv: Sequence[str] | None = None) -> int

输出（与 A2 对齐）：run_config.json、environment.json、summary.json、data_manifest.json、tasks.json、reference_solutions.json、metrics/{training_history,adaptation_results,metrics,optimization_history,optimization_summary}.csv、evaluations.jsonl、figures/*.png、README.md。启动/结束均断言 physical_call_count=0。

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
                               candidate_count: int = 512,
                               shortlist_count: int = 5,
                               adaptation_method: str = "maml",
                               seed: int = 42) -> InitialDesignProposal
    def compare_initializers(design_space, artifact, tasks, methods, budget, seed) -> dict[str, Any]

- 复用 maml_opt.initialization.prepare_model_scored_initial_designs / select_model_scored_initial_designs 的公开签名；传入 LoadedModelArtifact，features 顺序必须 = design_feature_names + task_context_names。
- 单位门禁：合成设计空间 units 全 "1"；物理 SI 设计空间不得误入该路径（测试覆盖）。
- 关键隔离：预测标签只能用于"先评估哪些点"的排序，绝不写入 BO observations；观测只能来自真实（合成）评估结果。测试断言 observations 长度只随真实评估增长。
- 与既有基线共用同一真值评估预算与可行性判据；不修改 optimization/baseline_bo.py / baseline_de.py。
- 返回的 designs 必须在界内、去重，并记录候选池 digest 与 artifact sha256，保证可追溯。

---

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

## 10. M2 等预算五臂优化矩阵（Lead 决策 m00606，替换草稿四臂）

统一设定：同一合成任务集（meta-test 20 + OOD 10 单列）、seeds={0,1,2,3,4}、true_evaluation_budget=64、同一可行性判据（g<=0，容差 1e-12）、同一缓存规则（缓存命中不计 true 预算，但记 requested/billable 双计数）。每 run 恰好消耗 64 次真实（合成）评价。

| 臂（精确命名） | 初始 8 点来源 | 代理来源 | 作用 |
|---|---|---|---|
| OPT-BO-rand | 共享 LHS 8 点 | 每任务从头 GP（普通约束 BO） | 基线 |
| OPT-BO-pretrain | 同一 8 点 | 条件预训练代理（零样本或 support 微调，按 M1 选定） | 隔离"代理先验"效应 |
| OPT-BO-MAML | 同一 8 点 | MAML 适应后代理 | 主对照 |
| OPT-BO-MAML-init | MAML 代理从 64 候选池排序出的 8 点 | MAML 适应后代理 | 隔离"初始化选择"效应；初始点不同但数量相同 |
| OPT-DE | 同一 8 点（=种群 8） | 无 | DE/rand/1/bin 语义，8 代×8 个体=64 |

- BO 执行：8 初始 + 56 次采集；DE 执行 8×8=64；两者预算严格相等。
- 共享初始点由同一 (task, seed) 的 LHS seed 生成并在臂间复用；记录 initial_feasible_count；MAML-init 例外但同样 8 点、同任务同 seed 可复现。
- 约束与失败：g>0 即不可行；失败/非有限目标为 null，不得用大惩罚值伪造；失败评价计入预算并记 status。
- 每 run 指标：best_feasible_value（无可行 null）、gap_to_reference = best − f*、first_feasible_eval_index（1-based，无则 null）、feasible_count、violation_rate、true_evals_used、cache_hits、wall_s、n_failed_evals。
- 预注册终点：优化侧 first_feasible_eval_index 与 best_feasible_value（B=64）；统计任务×seed 配对（20×5=100 对）报告配对中位差 + bootstrap 95% CI（10,000 次）与 Wilcoxon 参考；不显著即如实报"无改进"。
- 负控制：label-shuffle、K=0、OOD、参考解断言。若 MAML 无改进，禁止改基线/指标/阈值。

---

## 11. 产物、CSV schema 与运行目录（对齐 A2）

运行目录：research/concorde_metaopt/optimization_runs/p4-synthetic-<UTC>Z/（P4 分支）。每次 run 含：

- run_config.json：run_id、git_sha、seed、family/split id、seeds、预算（64/8/8×8/50）、ks、tolerance、物理调用声明；
- environment.json：python、numpy/scipy/scikit-learn/torch 版本（torch 可缺）、平台、CPU 核数；
- summary.json：status、arms、终点统计、失败数、physical_call_count、NOT_APPROVED 列表；
- data_manifest.json：每文件 sha256+bytes、hash_mode（如 CRLF→LF 规范化）、file_count、total_bytes，排除自身；
- CSV（列名与 A2 完全一致）：
  - training_history.csv：run_id, arm, split(meta_train|meta_val), task_id, family, iteration, epoch, loss_support, loss_query, grad_norm, lr, seed, wall_s, status(VALID|NONFINITE)
  - adaptation_results.csv：run_id, task_id, split(meta_test|meta_test_ood|negative_control), family, arm(R|P|M), K, seed, n_support, n_query, adapt_steps, mae_raw, rmse_raw, mae_norm, rmse_norm, r2, max_abs_err, wall_s, status
  - metrics.csv：experiment_id, phase(adaptation|optimization), split, family, arm, K, task_id, seed, metric, value, unit, aggregation(per_task|group_mean|group_std|ci95_low|ci95_high), n, status
  - optimization_history.csv：run_id, task_id, split, family, arm, seed, eval_index, design_u_0..design_u_11, objective, feasible, constraints_json, cache_hit, billable, status, wall_s, best_feasible_so_far, best_value_so_far
  - optimization_summary.csv：run_id, task_id, split, family, arm, seed, budget, true_evals_used, cache_hits, failed_evals, best_feasible_value, gap_to_reference, first_feasible_eval_index, feasible_count, violation_rate, wall_s, status
- figures/*.png 为 A2 消费 CSV 后生成；A1 不预生成伪图。缺失数据显示 NOT_RUN，禁止画假数据。

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

---

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
| Lead 五臂决策 | Team 消息 m00606（2026-11-02） |
| P5 只读参考（不复制） | 主库 D:/RCAIDE：configs/meta_tasks.yaml、data/meta_tasks.py、learning/{adapter,train_baselines,train_maml_a}.py、optimization/{initializer,maml_a_bo}.py |

## 15. 附录 B：状态枚举与术语

- run status：DESIGN_ONLY / NOT_RUN / RUNNING / COMPLETED / FAILED / FINITE_DIFFERENCE_FAILED / SYNTHETIC_TEST_ONLY；
- sample status：VALID / FEASIBLE / INFEASIBLE / INVALID / GEOMETRY_INVALID / NONFINITE / MISSION_FAILED / MISSION_NOT_CONVERGED / PARTIAL_RESULT（与 maml-opt LABEL_STATUSES/EXCLUDED_STATUSES 语义对齐）；
- source_kind：synthetic、archived_real_lf、validated_real_lf、validated_real_hf；
- 术语：12D=W01–W10+V01–V02；F01–F03 固定机身；S_adapt=50 适应步；B=64 真实（合成）评价预算；M1=代理诊断，M2=等预算优化对照；NOT_APPROVED=未获 owners 书面批准。
