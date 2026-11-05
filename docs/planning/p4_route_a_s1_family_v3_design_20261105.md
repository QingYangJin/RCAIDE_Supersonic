# P4 路线A S1：任务族 v3 设计与隔离规范（中文草案）

> 状态：草案 v2.0（2026-11-05），A1 起草并完成 S0-2 代码/冻结包落地（**均未提交，待 Lead 统一提交、A5 复核**）；**不构成新物理授权**，physical_call_count = 0。
> 依据：Issue #7（D-P4-003）§2 S0/S1；`docs/planning/p4_route_a_stage_improvement_plan_20261105.md`（a331639e）；`docs/planning/p4_route_a_s0_design_contract.md`（A4 / task-188）；`docs/planning/p4_route_a_s0_2_decisions_20261105.md`（Lead 裁定 D-S0-2-01..07）；任务 task-185（S0）、task-198（S0-2）。
> 工作树：<repo>（research/p4-route-a-improvements）@ a331639e47015f1d07796e46dbe3f71beb97048c；本文件及 S0/S0-2 代码由 Lead 统一提交，旧 run 只读。路径占位：<repo>=RCAIDE-p4-route-a 工作树根；<EXT>=外部记忆根（.../p4-route-a）。
> 硬约束：physical_call_count = 0；旧 M2/M5/M6 与 D-12D-005 冻结 run 不改写；本文件只定义 v3 新族与 S1 预算映射，不修改 BO 采集算法（路线B）。

## 1. 目的、范围与现状

### 1.1 目的

1. 在旧 M2/M5/M6 之外建立**独立版本**的合成任务族（family_version = p4ra-family-v3），使 S1 的 K-shot → 响应代理初始化 → 普通约束 BO 实验拥有新的、未被使用过的 meta_test 盲测集；
2. 明确 v3 与旧族的隔离规则（family/formula/seed/task_id 四重隔离），杜绝"拿已公开 holdout 当新盲测"的泄漏；
3. 固定 v3 的 family_fingerprint 生成方法与冻结流程，使"冻结后不可暗中改生成规则"可程序化审计；
4. 给出 S1 的 K ∈ {0,1,3,5} 支持集与 B ∈ {64,128} 预算映射（K 次计入 B、8 初始点补 8−K），并给出五臂等预算与 K=0 CLONE 的代码级断言。

### 1.2 范围

- 本文件定义：v3 参数/分布/种子、五 split 划分、隔离规则、family_fingerprint 算法、S1 预算与公平臂矩阵、验收清单。
- 本文件不定义：具体网络结构、BO 采集函数（路线B）、Full MAML 元梯度细节（S2，见计划文）、真实物理求解器接口（S4 另立 aero-api-v1）。
- 旧族与旧冻结 run 不因本文件发生任何修改。

### 1.3 已修复的 preregistration 序列化缺陷（S0 + S0-2）

旧版 `research/concorde_metaopt/meta_learning/feasible_v2.py`（HEAD a331639e）中：

- 旧 L130-133：`STOPPING_RULES = ("两阶段：……")` 缺少尾逗号，实际是**单个 str**；
- 旧 L1111：`"stopping_rules": list(stopping_rules)` 把该 str 逐字符拆成 113 个单字符数组写进 preregistration.json。

A1 修复（未提交，待 Lead 统一提交）：

- `feasible_v2.py:81/84`：新 schema `p4-m5-prereg-v2`，历史 `p4-m5-prereg-v1` 列入 `LEGACY_PREREGISTRATION_SCHEMA_VERSIONS`，旧 run 只读兼容；
- `STOPPING_RULES` 改为 tuple[str]（补尾逗号），新增 `STOPPING_RULE_MIN_LENGTH = 2`；
- `normalize_stopping_rules()`：str → 单元素 list、逐项类型/非空/strip 后长度 ≥2 校验、拒绝逐字符拆分形态；落盘前统一 `item.strip()`（A5 m07）；
- `validate_preregistration_schema()`：当前 schema 要求 stopping_rules 为非空 list[str]，历史 schema 只做版本识别；当前 schema 缺字段直接抛 `FeasibleV2Error`（A5 m06/m08）；
- 实测：M5 历史 `optimization_runs/p4-meta-m5-formal-20261104T1018Z/preregistration.json`（schema v1、stopping_rules 为 113 字符数组）经 `verify_preregistration` 仍返回 True（2026-11-05 只读复核，未改写该文件）。
- 单测：`tests/test_meta_learning_feasible_v2.py` Ran 37 tests OK（含新增 test_26f 缺 stopping_rules 负控、test_26g strip 用例）。

v3 从一开始按"list[str] + 双 digest"生成，不复用旧 schema 的缺陷路径。

### 1.4 与 A4 数据合同的关系

v3 任务与预注册的**字段语义、枚举、fail-closed 编号**沿用 A4 `p4_route_a_s0_design_contract.md`：

- task 级字段 schema_version = `p4ra-task-v1`；任务标识形如 `p4ra-FQE3-v3-<SPLIT>-<NNN>`（见 §2.4，已按 D-S0-2-05 定稿）；
- preregistration schema_version = `p4ra-prereg-v1`，stopping_rules 必须为非空 list[str]；
- evaluator 一律 `synthetic-analytic`，`physics_validation_status = NOT_APPLICABLE`、`physical_call_count = 0`；
- B/K/initial_designs 口径见该合同 §4 与 D-S0-2-03（K 计入 B、8 初始点、各臂评价次数精确相等）；
- split 枚举为**五个**：meta_train / meta_validation / meta_test / meta_test_ood / negative_control，split_digest/split_hash 覆盖五者全部 task_id 有序列表（D-S0-2-01）；主统计分母仅 meta_test 20（D-S0-2-01/04）；
- 主终点只允许四个规范 ID：`best_feasible_value`、`gap_to_reference`、`first_feasible_eval_index`、`feasible_hit_rate`；`first_feasible_evaluation_index` 为禁用别名（D-S0-2-02，代码级 `normalize_endpoints` 拒绝）。

本文件是 v3 在 A4 合同之上的**差异与冻结细节**，两者冲突时以更严格者为准。

## 2. v3 任务族定义

### 2.1 标识与命名空间

| 字段 | v2（旧，只读） | v3（本文件，已实施） |
|---|---|---|
| family_id | F-QE-feasible-v2 | **F-QE-feasible-v3** |
| family_version | v2 | **p4ra-family-v3**（D-S0-2-05；A5-S0P1-B01 裁定） |
| formula_version | p4-task-family-v2 | **p4-task-family-v3** |
| family_seed | 20261102 | **20261105** |
| task_id | 12 位 sha1 | **p4ra-FQE3-v3-<SPLIT>-<NNN>**（新命名空间） |
| schema_version | p4ra-task-v1 | p4ra-task-v1（字段不变，语义按 v3） |

v3 常量（已写入 `research/concorde_metaopt/meta_learning/task_family.py:99-109`，并由 `family_v3.py:93-98` 复用）：

```
V3_FAMILY_ID = "F-QE-feasible-v3"
V3_FORMULA_VERSION = "p4-task-family-v3"
V3_FAMILY_SEED = 20261105
V3_RADIUS_JITTER = 0.20
V3_RADIUS_MIN = 0.15
V3_RADIUS_MAX = 1.10
V3_FAMILY_VERSION = "p4ra-family-v3"   # D-S0-2-05；A5-S0P1-B01 裁定（原 v3 作废）
V3_RADIUS_BASE_DEFAULT = 0.32            # 设计初值；冻结使用 A2 校准值 0.64（见 R-02）
V3_TASK_ID_PREFIX = "p4ra-FQE3-v3-"
V3_OOD_RADIUS_SCALE = 0.75
V3_OOD_CONTEXT_SHIFT = 0.25
V3_CONTEXT_COUPLING_SCALE = 0.45
```

### 2.2 设计空间与解析族

- 设计空间：**12 维**，沿用 `DESIGN_NAMES / DESIGN_LOWER / DESIGN_UPPER`（与 M2/M5/M6 同维同界，保证难度可比；任何界变动必须升 family_version 并重算 fingerprint）。
- context：2 维（`context_1, context_2`），OOD 通过 context 偏移 + 半径缩放构造；v3 的 context 采样分支见 `task_family.py:192-199`，耦合尺度见 `task_family.py:201-208`。
- 解析族：沿用 F-QE 径向投影形式——参考解 `u* = c`、`f* = b_eff`、KKT 残差恒 0，可解析证书（`u*` 落在 [0,1]^12、严格 margin > 0）。v3 **只改参数分布与种子**，不改解析形式（`reference`/`truth` 复用 v2 分支，`task_family.py:726、867`），从而既能与旧族可比，又构成独立版本（旧 holdout 的变体不能当新盲测）。
- 合成约束：`synth_c01..03` 槽位，可行域按 g(x) ≤ 0 判定；负控任务从 meta_train 衍生并显式打标。

### 2.3 参数分布（v2 → v3，已实施）

| 参数 | v2（旧） | v3（已实施） | 说明 |
|---|---|---|---|
| c | U(0.15, 0.85) | U(0.20, 0.80) | 中心点，收窄避免极端半径 |
| d | clip(c + N(0, 0.25), 0.05, 0.95) | clip(c + N(0, 0.20), 0.10, 0.90) | 偏移项降低噪声 |
| a, w | logU(0.5, 5.0) | logU(0.5, 4.0) | 曲率/权重 |
| b | U(-1, 1) | U(-0.9, 0.9) | 目标偏置 |
| radius_base | M5 冻结 0.75（v2 默认自适应） | **0.64（A2 校准，CALIBRATED）**，jitter 0.20，截断 [0.15, 1.10] | A2 2026-11-05：pooled success 16/24=0.6667，逐 seed [0.750,0.688,0.750]，Wilson95 [0.467,0.820]；设计初值 0.32 实测 success=0.0 已弃用（Lead 裁定 R-02） |
| OOD 半径缩放 | 0.70 | 0.75 | OOD 难度略高 |
| OOD context 偏移 | 0.20 | 0.25 | OOD 分布外程度 |
| context coupling | 0.50 | 0.45 | 降低耦合 |
| support/query/designs | 128 / 64 / 192 | 128 / 64 / 192 | 与 v2 同规模 |

实现位置：`task_family.py:415-428`（v3 采样分支）、`task_family.py:507-513`（v3 params 记录 family_version/formula_version/radius_base/radius_jitter/radius_bounds）、`task_family.py:373-401`（v3 fingerprint 分支）、`task_family.py:254-258`（v3 config 校验）。

注意：表中分布已落地；radius_base 已由 A2 在 meta_train/meta_validation 上校准为 0.64（见 §2.1 常量与 Lead 裁定 R-02，第二判据退化为「带内最大半径」的口径须在 prereg 明示）。**禁止**用 meta_test/OOD 的任何信息调参；一旦 family_fingerprint 冻结，任何分布/种子/半径改动必须升 family_version = v4 并重新预注册（A4 合同 FC-10）。

### 2.4 种子与 task_id 生成（D-S0-2-05 定稿）

- 任务 seed：`seed = derive_seed(family_id, split, index, attempt, config.seed)`，其中 family_id 为 `F-QE-feasible-v3`、config.seed 为 `V3_FAMILY_SEED=20261105`；派生函数与 v2 同实现，保证确定性。
- task_id：`p4ra-FQE3-v3-<SPLIT>-<NNN>`，已定稿正则 `^p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-[0-9]{3}$`（`family_v3.py:98`），split 代码固定映射：TR=meta_train、VA=meta_validation、TE=meta_test、OD=meta_test_ood、NC=negative_control；序号在 split 内从 000 递增，跨 split 全局唯一（`assign_v3_task_ids`，`family_v3.py:342`）。
- task_id 由 `family_v3.assign_v3_task_ids` 在 build 后统一重写，不依赖原 sha1 形态；同一 task 的 task_id 不随进程/时间变化。
- task_fingerprint：`sha256(canonical_json(task_definition))`，覆盖 family_id/family_version/formula_version/design_dim/params/context/constraint_slots，**不含** split/index/seed（与 A4 合同 §6.2 一致，`family_v3.py:369`）；用于跨 split 查重和内容追溯。
- 生成顺序固定：meta_train(60) → meta_validation(20) → meta_test(20) → meta_test_ood(10) → negative_control(10)，共 120 个任务；build 时断言五 split task_id 全局互异、task_fingerprint 在五 split 内不重复（`verify_split_manifest_v3`，`family_v3.py:493`）。

### 2.5 split 划分与约束（D-S0-2-01）

| split | 任务数 | 用途 | 约束 |
|---|---|---|---|
| meta_train | 60 | 元训练/代理训练 | 可用其支持集标签；不得触碰 test/ood |
| meta_validation | 20 | 调参/早停/校准旁证 | 与 train 不共享 task_id；不得用于 meta_test 选型 |
| meta_test | 20 | 正式盲测（一次性解封） | **主统计唯一来源**；解封后不得增删/改终点/按结果剔除 |
| meta_test_ood | 10 | 分布外泛化（只报告） | 单独描述层；不参与调参；与 test 不同 task |
| negative_control | 10 | 泄漏/证书负控 | 从 meta_train 派生并打标；只进入负控结论，不计入主终点 |

硬约束：任务级切分（同一 task_id 只能属于一个 split）；meta_test = 20 且为主统计分母；负控不得进入正式统计分母；所有 split 的 task_id 清单按上表顺序写入 split_manifest 并计算 split_hash（`build_split_manifest_v3`，`family_v3.py:451`）；split_digest/split_hash 覆盖五 split 全部 task_id 有序列表。

## 3. 与旧任务族隔离规则（硬约束）

### 3.1 命名空间隔离

1. family_id / family_version / formula_version 三者必须同时变化（v3），不得在 v2 上改参数后沿用旧版本号；
2. task_id 使用全新前缀 `p4ra-FQE3-v3-`，与旧 M2/M5/M6 的 12 位 sha1 task_id 天然不同命名空间；
3. 新族的 frozen manifest 必须显式记录旧族 fingerprint 列表与旧清单文件 sha256，供审计比对（`v3_isolation_report.json` 的 `legacy_sources`）。

### 3.2 种子隔离

1. family_seed 取新值 20261105，不得复用 M2 seed = 42、M5/M6 family seed = 20261102；
2. task seed 的派生输入包含新 family_id，即使整数相同也因输入串不同而不重叠；build 时导出全部 task seed 并断言互异；
3. 实验级 seeds（meta seeds 0,1,2；optimization seeds 0..9）是**协议参数**，允许跨族复用（配对比较需要），但必须记录在 preregistration 中，且不得与任务生成种子混用；
4. 禁止复用 M5/M6 已公开的 meta_test/meta_test_ood 任务作为 v3 的训练/验证/测试任务，也禁止把旧 test 任务改 index 后冒充新任务。

### 3.3 task_id/task_fingerprint 零交集断言（已实施）

`family_v3.py` 在 build 时执行（fail-closed）：

1. `collect_legacy_task_ids(paths)`（`family_v3.py:552`）递归解析旧 run JSON，收集所有 `task_id` / `task_fingerprint` / `task_ids` 列表，记录每个来源的路径、字节数与 raw sha256（`legacy_sources`）；
2. `assert_zero_intersection`（`family_v3.py:588`）断言 `set(v3_ids) ∩ legacy_ids == ∅` 且 `set(v3_fps) ∩ legacy_fps == ∅`，否则抛 `FamilyV3Error`（A4 合同 FC-06）；
3. `build_isolation_report`（`family_v3.py:602`）输出 `p4ra-v3-isolation-1` 报告：v3 120 个 id/fp、旧清单计数、交集（空）、断言状态 `ZERO_INTERSECTION`、`physical_call_count=0`、报告 sha256；`verify_isolation_report` 复核。
4. 实测（2026-11-05，零求解）：旧清单 5 个文件（M2 `tasks.json`、M5 `tasks.json`+`meta_task_split.json`、M6 `tasks.json`+`meta_task_split.json`）共 280 个 legacy task_id、0 个 legacy task_fingerprint；v3 120 个 task_id，交集 = 0；报告 sha256 = `3350316359256c767cd14ef0e04a6e1a3b553520bdaf8d949582b2238bc394e7`（见 §4.4 与 EXT 证据）。

### 3.4 旧 holdout 使用限制

1. M2/M5/M6 的 meta_test 已公开：只能用于**诊断性复现/历史对照**，不得作为新方法"未见盲测"；
2. v3 meta_test 只在 frozen_family + split_manifest + preregistration 三方 sha256/fingerprint 校验通过后**一次性**构造并评估一次（A4 合同 FC-07/FC-10）；
3. 旧 run 的 run_config/summary/SHA256SUMS 不改写；新版本只新增文件与新的 digest 记录（A3 留档）。

## 4. family_fingerprint 生成与冻结

### 4.1 payload 组成（canonical）

v3 fingerprint payload（`task_family.py:373-401`）包含：

```
{
  "formula_version": "p4-task-family-v3",
  "config": { family_id, design_dim, context_names, seed, train_tasks,
              validation_tasks, test_tasks, ood_tasks, negative_control_tasks,
              designs_per_task, support_pool_size, query_size,
              reference_tolerance, family_version, radius_base },
  "design_names": [...12],
  "design_bounds": [[lo,hi], ...12],
  "param_distributions": { c, d, a, w, b, radius_mapping, ... },
  "context_coupling": { "scale": 0.45 },
  "ood_protocol": { "context_shift": 0.25, "radius_scale": 0.75 },
  "negative_control_protocol": {...},
  "constraint_slots": ["synth_c01", ...],
  "task_id_namespace": "p4ra-FQE3-v3-"
}
```

禁止进入 payload 的内容：时间戳、主机名/路径、Python/torch 版本、运行随机态、旧 run 的 mtime。生成规则冻结后，这些运行时信息只写入 run_config，不进入 family_fingerprint。

### 4.2 算法

`family_fingerprint = sha256(canonical_json(payload).encode("utf-8")).hexdigest()`，其中 canonical_json 规则：对象键按 Unicode 码点升序、数组保持顺序、无多余空白、UTF-8、禁止 NaN/Infinity、浮点用 Python repr 最短往返表示。输出 64 位小写十六进制。实现见 `task_family.family_fingerprint` 与 `family_v3.digest`（`family_v3.py:223`）。

### 4.3 双 digest 与确定性重跑（已实施）

为修复"只有 canonical digest、缺原始字节 digest"问题，v3 冻结产物同时记录：

| digest | 覆盖内容 | 生成时机 |
|---|---|---|
| family_fingerprint | 上述 canonical payload | family 冻结时 |
| family_manifest_canonical_sha256 | family_manifest 的 canonical JSON | 写盘前 |
| family_manifest_raw_sha256 | 实际写入磁盘的 UTF-8 字节（含格式化空白） | 写盘后 |
| split_hash | 五 split 的 task_id 有序列表 | split 冻结时 |
| prereg_digest | preregistration.json canonical digest | 预注册冻结时 |
| prereg_raw_sha256 | preregistration.json 磁盘字节 | 写盘后 |

实现：`family_v3.write_json_artifact`（`family_v3.py:250`）对每个产物返回 `path/bytes/canonical_sha256/raw_sha256/stored_sha256`；`build_digest_manifest`（`family_v3.py:1074`）聚合 6 个 payload 文件的逻辑名 + 双 digest。确定性重跑要求：同输入在干净进程重跑 ≥2 次，canonical 与 raw digest 逐位一致；记录 `determinism_reruns = {rerun_count, identical: true, canonical_sha256, raw_sha256}`。若只有 canonical digest 而无法重算 raw digest，标 `PARTIAL`，不得声称冻结完成。

### 4.4 冻结与验证流程（已实施）

1. 生成 v3 任务 → 计算 task_fingerprint → 生成五 split manifest（split_hash）：`build_v3_family_config`（`family_v3.py:266`）→ `assign_v3_task_ids` → `task_fingerprint` → `build_split_manifest_v3`；
2. 冻结 family_manifest（family_fingerprint + 双 digest）：`build_frozen_family_v3`（`family_v3.py:767`）→ frozen_family.json（schema `p4ra-frozen-v3-1`，含 split{manifest_sha256, split_hash, counts, split_order, task_ids}、arms/budgets/k_values/initial_designs=8/support_policy、calibration{status, selected_radius_base, radius_base_source}、evaluator=`synthetic-analytic`、physics_validation_status=`NOT_APPLICABLE`、meta_test_tuning_policy）；`verify_frozen_family_v3`（`family_v3.py:879`）复核；
3. 冻结 preregistration（族绑定 + B/K/arms/seeds/终点）：`build_preregistration_v3`（`family_v3.py:950`，schema `p4ra-prereg-v1`，primary_endpoints 只允许四规范 ID，stopping_rules 非空 list[str]）→ `verify_preregistration_v3`（`family_v3.py:1028`，含 frozen 绑定校验）；
4. `build_freeze_bundle`（`family_v3.py:1096`）一次构造 tasks/task_records/split_manifest/isolation_report/frozen_family/preregistration，并对每个产物执行 verify；任一步失败 fail-closed，不得用默认值静默填充；
5. 实测冻结包（2026-11-05，零求解，见 EXT 证据目录）：
   - INT/EXT 证据：`<EXT>/a1/s0_2_freeze/`（make_freeze.py、compare_runs.py、run1/、run2/、determinism_report.json）；
   - run_id=`p4ra-s0-2-freeze-20261105T000000Z`、created_utc=`2026-11-05T00:00:00+00:00`、git_sha=`a331639e47015f1d07796e46dbe3f71beb97048c`、physical_call_count=0；
   - family_fingerprint = `848be432b61cf1be34312995d1d274ad8ea9d03e15100a7d2a5f6d0a6c4c4642`；
   - split_hash = `cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae`；counts 60/20/20/10/10；
   - frozen_family.sha256 = `8b99b5b86965fce143843b3d12bb026251f64aabfde2bc75bf29c72776000858`；
   - preregistration.sha256 = `30dc99578777d715f423b41c335f1f3670b14de8ae7356262045d11ecd8952ad`；
   - 独立进程 run1/run2 的 7 个 payload+digest 文件（tasks.json、meta_task_split.json、v3_isolation_report.json、frozen_family.json、preregistration.json、budget_fairness_report.json、digest_manifest.json）**逐字节一致**，status=PASS，16 项结构校验全部 true（见 determinism_report.json，schema `p4ra-determinism-report-1`）；
   - freeze_summary.json 因 run 目录绝对路径不同而不参与逐位比对（已在报告中说明）。

## 5. S1：K-shot 支持集与预算映射

### 5.1 定义（D-S0-2-03）

- K：部署时允许的已评价支持样本数；K 个支持点来自目标任务 support pool 的固定前 K 个（固定 seed/顺序），标签由真实合成评估器给出；
- **K 次评价计入 B**；所有对照臂共享完全相同的 K 个支持点、标签与顺序（RAND/DE 不使用标签，但同样评价并计费）；
- 同任务固定顺序评价 B 个真实点：阶段1 支持 K → 阶段2 初始设计 8−K → 阶段3 主搜索 B−8（BO 臂为 B−8 次 BO 迭代；DE 臂为 B−8 次 DE 世代评价，population 由前 8 点初始化；8−K 初始点同时作为初始 population 的一部分，不得多评/少评）；
- 合计精确 B，否则 run 作废；K=0 时阶段1=0、阶段2=8，FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 同构 → 登记 CLONE 并排除推断（不得当作两个独立证据）；
- 同一设计点若已在 B 内评价，后续只能复用缓存记录，不得重复计费。

### 5.2 预算映射表（已代码化）

| K | 支持评价（计入 B） | 初始补点 | 主搜索评价（B−8） | B=64 总评价 | B=128 总评价 |
|---|---|---|---|---|---|
| 0 | 0 | 8 | B−8 | 64 | 128 |
| 1 | 1 | 7 | B−8 | 64 | 128 |
| 3 | 3 | 5 | B−8 | 64 | 128 |
| 5 | 5 | 3 | B−8 | 64 | 128 |

所有臂的 `billable evaluations` 必须精确等于 B（fail-closed，A4 合同 FC-02/FC-03 与 §4.1）。预算账字段：`budget.B_total, budget.K_support, budget.initial_designs=8, budget.standard_bo_calls=B-8, budget.support_evaluations_counted=true, evaluations.billable, evaluations.non_billable, physical_call_count=0, physical_call_sources=[]`。

实现：`budget_fairness.build_budget_plan`（`budget_fairness.py:76`）生成单计划（阶段 support/initial/main 均 `counted_in_billable=true`，`billable=B`、`non_billable=0`、`physical=0`）；`build_all_budget_plans`（`budget_fairness.py:151`）生成 5 臂 × 4 K × 2 B = 40 个计划；`assert_budget_fairness`（`budget_fairness.py:177`）逐计划重算并校验每 (K,B) 五臂 billable 相等且等于 B、K 未计入或各臂不等 → 抛 `BudgetFairnessError`；实测 40 计划全部通过。

### 5.3 公平臂矩阵（S1）

| 臂 id | 含义 | 初始化 | 是否用支持集标签 |
|---|---|---|---|
| RAND-BO | 随机/旧初始化 + 普通 BO | 随机 8 点（K 点支持仍评价并计入 B） | 否 |
| PRETRAIN-KSHOT-BO | 预训练代理 + K-shot 适应 + BO | 代理补 8−K | 是（`SUPPORT_ADAPTATION_ARMS`） |
| FOMAML-ZERO-BO | FOMAML 代理零样本初始化 + BO | 代理 8 点 | 否（K=0 语义） |
| FOMAML-KSHOT-BO | FOMAML 代理 + K-shot 适应 + BO | 代理补 8−K | 是（`SUPPORT_ADAPTATION_ARMS`） |
| DE | 差分进化同预算对照 | 8−K 初始点兼作初始 population | 否（但同 B、同支持点计费） |

同一 (task, seed, B, K) 下五臂使用相同目标/约束/支持点；DE 的真实评价次数必须精确等于 B；K=0 时 FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 同构，由 `clone_map(0)`（`budget_fairness.py:61`）登记 CLONE，`inference_eligible_arms`（`budget_fairness.py:70`）排除重复推断；K>0 不得误标 CLONE。公平性报告 `build_fairness_report`（`budget_fairness.py:279`）输出 `p4ra-budget-fairness-1`，含 40 计划、CLONE 对、推断可用臂、status=PASS、sha256=4026fefa0ff007b65692cc61806b5331a704434b69f592e68d2e86a904731620。

### 5.4 统计与解封门禁（D-S0-2-04）

- 主终点只允许四个规范 ID：`best_feasible_value`、`gap_to_reference`、`first_feasible_eval_index`、`feasible_hit_rate`；`first_feasible_evaluation_index` 为禁用别名，代码级拒绝（`family_v3.normalize_endpoints`，`family_v3.py:669`）；
- 端点语义：`f* = reference_solution.best_feasible_value`（数值或 null）；`best_feasible_value` = B 个评价中满足全部约束的最小目标值，无可行 = null（不插补、不计 0）；`gap_to_reference = (f_best − f*)/max(|f*|,1e-12)` 有符号、任一 null → null；`first_feasible_eval_index` 为 B 个评价按真实顺序 1-based（支持评价为 1..K），无可行 null，附加 `first_feasible_in_support`(bool) 与 `first_feasible_after_support_index`（序号−K，支持集内为 null），跨 K 比较须声明 K 依赖性；`feasible_hit_rate = 可行数/B`（分母恒 B），附加 `feasible_hit_rate_non_support` = 非支持可行数/(B−K)；
- 显著性阈值：best 相对改进 = (median_base−median_arm)/max(|median_base|,1e-12) ≥ 1%；gap 相对改进 ≥ 1%；feasible_hit_rate 绝对差 ≥ 0.05；first_feasible 改善 = idx_base−idx_arm ≥ ceil(0.05×B)（同 K 内）；
- 聚合：单 run → (task, meta_seed) 内对 10 个 opt seed 均值 → 20 个 meta_test 任务配对检验；meta_seed 等权为主分析，任务为一级统计单位；null 不插补/不计 0，报告 n_nonnull/null_rate；主端点 null 率 >70% → INCONCLUSIVE；
- 统计一级单位 = task；meta seeds ≥ 3、optimization seeds ≥ 10；配对差按 (task, opt seed, B, K)；Wilcoxon + Holm-Bonferroni 校正；
- 先 meta_train/validation 校准与 pilot，冻结 preregistration 后才允许一次性解封 meta_test；解封后不得调参/改终点/按结果剔除任务；
- 泄漏负控：注入"用 query 标签做支持标签""参考最优点当支持标签"必须被抓（FC-01）；K 未计入 B 必须 fail（FC-02）。

## 6. 验收清单（S0/S0-2/S1 可检查项）

| # | 项 | 验收证据 | 状态 |
|---|---|---|---|
| 1 | 旧 prereg stopping_rules 缺陷修复 + schema 校验 | `feasible_v2.py` 的 STOPPING_RULES/normalize/validate；单测 test_26a-26g；feasible_v2 模块 37 tests OK | 已完成（未提交） |
| 2 | 旧 run 只读兼容 | M5 历史 prereg（113 字符数组）verify_preregistration=True | 已完成（2026-11-05 只读复核） |
| 3 | v3 常量/生成器/五 split | `task_family.py:99-109, 192-208, 254-258, 373-401, 415-428, 507-513`；`family_v3.py`（schema/生成/校验/fingerprint/split manifest） | 已完成（未提交） |
| 4 | task_id/seed/fingerprint 与旧族零交集 | `v3_isolation_report.json`（v3 120 vs legacy 280，交集=0；旧清单 sha256）；隔离单测 | 已完成，报告 sha256=3350316359256c767cd14ef0e04a6e1a3b553520bdaf8d949582b2238bc394e7 |
| 5 | family_fingerprint + 双 digest 确定性重跑 | determinism_reruns.identical=true；7 文件 canonical/raw sha256 逐位一致；freeze_summary 仅绝对路径不同 | 已完成（run1/run2 独立进程，status=PASS） |
| 6 | S1 K 计入 B、各臂等预算、K=0 回归 | `budget_fairness` 40 计划、`assert_budget_fairness`、K=0 CLONE 测试 | 已完成（单测通过；BO/DE 真实运行属 S1，未运行） |
| 7 | physical_call_count=0 | 冻结包与公平性报告静态断言；单测覆盖 | 已完成（静态断言）；每 run 仍需检查 |
| 8 | 旧 M2/M5/M6 与 D-12D-005 工件不改写 | A3 SHA256SUMS 前后一致证明 | 由 A3 出具（本文件不改写任何旧工件） |

代码级回归证据：`tests/test_meta_learning_family_v3.py` Ran 31 tests OK；`tests/test_meta_learning_feasible_v2.py` Ran 37 tests OK；全量 `python -E -s -B -m unittest discover -s research/concorde_metaopt/tests -t .` → **Ran 579 tests in 36.217s，OK (skipped=1)，exit 0**（日志：`<EXT>/a1/logs/full_suite_s0_2.log`，sha256=6d81114ac5fd7d8ef41612ef67bc862ba2f09615db28d54e13eec4159ac8d083）。

## 7. 待决策项与剩余风险

1. **radius_base 校准未完成**：默认 0.32 为 S0-2 落地值，frozen_family.calibration.status = PENDING_A2_CALIBRATION，selected_radius_base 记录为默认来源；A2 只能用 meta_train/meta_validation 校准，冻结后任何改动须升 v4 并重新预注册。
2. 任务规模 120（meta_test=20）是否足够：S1 pilot 若显示方差过大，只能在冻结前扩大并把依据/预算写入 prereg；解封后不得追加。
3. task_id 格式已按 D-S0-2-05 定稿（`p4ra-FQE3-v3-(TR|VA|TE|OD|NC)-NNN`），与 A4 合同模板的关系为"本文件更具体、A4 合同为字段语义基线"；若 A4 合同需逐字对齐，由 Lead/A4 在冻结前确认，改动须重算 family_fingerprint。
4. A5 复核：S0 审阅 4 major/10 minor 中 M01-M04、m06-m10 已由 S0-2 代码/测试/本文件关闭，仍待 A5 复核确认；Lead 统一提交前不得声称已冻结。
5. 本文件为设计文档，不替代 preregistration；正式实验以冻结后的 frozen_family.json / preregistration.json 为准；S1 真实 BO/DE 运行仍受 Issue #7 门禁与 A5 APPROVE 约束。
6. EXT 冻结包使用固定 run_id/created_utc 作为确定性证据；正式冻结 run 的 run_id/created_utc/git_sha 由 Lead 在提交后指定并重跑 `make_freeze.py`（同逻辑，换 run 元数据）。

## 8. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A1（task-185） | 首次起草：v3 参数/隔离/split/fingerprint/S1 预算映射 |
| v2.0 | 2026-11-05 | A1（task-198） | S0-2 落地后修订：task_id 正则/五 split 合同/split_hash 覆盖/端点规范 ID 与禁用别名/RAND-DE 支持集计费/K=0 CLONE/40 预算计划/冻结包与确定性证据/A5 M01-M04 与 m06-m10 关闭映射/剩余风险 |
