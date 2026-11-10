# A1 任务回执（F 线：真实评价与航空约束，D-NEXT-001）

- 角色：A1（真实评价与航空约束，F 线）
- 共享任务：task-1（已 claim，revision 1→2，owner=a1-aviation-f）
- 工作树：`D:\RCAIDE\dnext001\wt-a1`
- 分支：`research/dnext001-f-real-evaluator`
- 基线 commit：`ea8ad97833eb5ceab291faae643c141a2b219749`
- 本轮交付 commit：`d66053dd274c9d63474b2adad9a5d5396d7bf966`（本地提交，**未 push**）
- 回执 commit：紧随其后的第二提交（`git log -1` 可查；内容仅本文件）
- **physical_call_count = 0（本轮全部 run；未启动 VSPAERO / OpenVSP / SU2 / RCAIDE Mission / WaveDrag）**
- 状态：最小可运行垂直切片已交付；**不宣称任何物理 PASS**

---

## 1. 交付物 1：M0 基线/Gate 中文审计

`docs/planning/dnext001_m0_baseline_and_gate_audit.md`（127 行，中文）

- 12 维变量表：W01–W10 + V01–V02，逐项列边界/单位/scale/target 与 yaml 行号；固定机身 F01–F03 保留不删。
- 参考量审计：Sref=358.25 m^2、Cref=18.489893 m、Bref=25.604638 m（来源
  `optimization_runs/openvsp355-remediation-20261102T014411Z/summary.json:173`），并记录
  `:211` 的 VSPAERO 6.2.0 静默 Sref=1.0 缺陷（CL 虚高约 358 倍、CDo=NaN）——因此
  "打印系数 ≠ 物理量"，参考量注入必须核对。
- CG/AC 口径：机翼 AC `wing_ac_x_m=16.821978259514246 m` vs 全机几何 CG
  `cg_x_m=28.287395109126685 m`，差 11.4654 m；`static_margin=0.13707938483236962` 仅为几何诊断。
  **禁止把机翼 AC 当 CG**；力矩参考点未核对，力轴/符号未核对。
- 质量口径：136000 kg 是**固定巡航进入质量**（ZFW 89200 + 46800 燃油自洽），不是 MTOW；
  几何模型 MTOW=184880 kg（与 `max_takeoff_kg=185000` 差 120 kg）。禁止质量归一化互证。
- 约束：10 项 schema 顺序、`FEASIBILITY_TOLERANCE=1e-12`、`RESIDUAL_LIMIT=1e-4`、
  `MAX_ATTITUDE_DEG=12.0`；其中 6–10 项（max_throttle/cruise_range_error/mission_convergence/
  trim_attitude_limit/fuel_remaining_deficit）物理语义 **NOT_VALIDATED**。
- 可冻结 / 不可冻结 / 硬性禁止三清单；门禁表：LF-M2.02 = NOT_VALIDATED、
  BODY-CORR = BLOCKED、HF-M2.02 = PARTIAL；历史 S1/S2/S3/S4 结论按原样引用，不改写。

配套草案：`research/concorde_metaopt/configs/task_fixed_cruise_contract_v2_DRAFT.yaml`
（143 行，`contract_status: DRAFT_NOT_FROZEN`，`owner_approval_required: true`，
含 reference_quantities / moment_reference（`wing_ac_as_cg_allowed: false`）/ force_axes
（NOT_VALIDATED）/ 10 项约束 / 4 个 gate / frozen_items / not_frozen_items / prohibited /
approval_checklist）。已用仓库无依赖 loader `research/concorde_metaopt/config_io.py:28 load_config`
解析通过（design_dim=12、10 约束、wing_ac_as_cg_allowed=False）。**未宣称 PASS、未冻结。**

## 2. 交付物 2：F1 零求解评价闭环（`research/concorde_metaopt/f_line/`）

| 文件 | 行数 | 内容 |
|---|---|---|
| `f_line/records.py` | 209 | `EvaluationRecord`（frozen dataclass）：run_id/task_id/design/design_sha256/evaluator_id/fidelity/source_kind/physical_validation_status/solver_version/objective/constraints/status/provenance/physical_call_count/wall_seconds/feasible/diagnostics；`__post_init__` 强制：VALID 必须有有限 objective、非 VALID 必须 objective=None、非求解类 source_kind 必须 physical_call_count=0；`canonical_design_sha256`、`ordered_constraints`（严格 10 项）、`is_feasible`；状态词表 VALID/GEOMETRY_INVALID/SOLVER_NONCONVERGED/PHYSICS_NOT_VALIDATED/EVALUATOR_ERROR |
| `f_line/protocol.py` | 25 | `@runtime_checkable EvaluatorProtocol`：`evaluate(design, task=None, fidelity=None) -> EvaluationRecord` + evaluator_id/fidelity/source_kind/solver_version/physical_validation_status/estimated_physical_cost |
| `f_line/budget.py` | 247 | `BudgetLedger`：`authorize()` 求解前预授权（超预算抛 `BudgetExceeded`）、按请求/记录上限、缓存命中 0 费、`evaluate_with_retry`（每次尝试独立计费）、`status_counts`/`summary`/`evaluations_jsonl`/`write_summary_json`；只缓存 VALID 记录（失败缓存会让重试永远拿不到真实第二次） |
| `f_line/mock_evaluator.py` | 265 | `MockEvaluator`（source=SYNTHETIC_MOCK、fidelity=synthetic、0 费）：基线 `34109.482571 kg` + 归一化线性占位响应；越界/C01/C02 违反 → GEOMETRY_INVALID + objective=None；可注入 `failure_hook`（SOLVER_NONCONVERGED/EVALUATOR_ERROR）与 `raise_hook` |
| `f_line/replay_evaluator.py` | 204 | `ArchiveReplayEvaluator`（source=ARCHIVE_REPLAY、0 费）：只读 `optimization_runs/geometry-check-p1-20261028T1835/geometry_cases.jsonl`（31 条、sha256 前缀 `5850a57c`），按 15 名设计精确匹配；命中 → status=PHYSICS_NOT_VALIDATED、objective=None、provenance 附归档指标；未命中 → EVALUATOR_ERROR |
| `f_line/search.py` | 542 | `run_bo_search`（maml_opt ConstrainedBayesianOptimizer + run_search，LHS 初始设计，首点强制基线）、`MiniDE` ask/tell + `run_de_search`（自写 DE/rand/1/bin，避免 `baseline_de.py` 的 4× 请求放大）、`write_run_artifacts`（run_config.json/evaluations.jsonl/optimization_history.csv/metrics.csv/data_manifest.json/SHA256SUMS.txt/figures/README.md） |
| `f_line/__init__.py` | 92 | 公共导出与中文边界声明 |

复用既有接口：`aircraft/design_space.py:327 load_design_space`（12D yaml）、
`tasks/task_spec.py load_task_spec`、`evaluation/contract.py` 的 10 项约束与容差常量。

**零求解 E2E 冒烟 run**：`research/concorde_metaopt/optimization_runs/f1-zero-physics-smoke-20261110T061634Z/`

- `bo/`：requests=10、initial_designs=5、seed=42 → physical_call_count=0，best=33371.037 kg
  （`run_config.json`：budget_B=0、K=10、source_kind=SYNTHETIC_MOCK、zero_physical_run=true）
- `de/`：requests=12、population_size=6、seed=42 → physical_call_count=0，best=33722.357 kg，generations=1
- `replay/`：归档 replay + BO(requests=6, initial=3) → physical_call_count=0，best_feasible=None
  （全部 objective=None、source_kind=ARCHIVE_REPLAY、physical_validation_status=NOT_VALIDATED）
- 每个子目录 7 类产物齐全；`metrics.csv` 中 `drag_polar`/`trim_curve`/`fuel_burn_physical` 均为 `NOT_RUN`；
  `figures/` 只有中文说明（NOT_RUN，未造假图）。
- 未触碰 `optimization_runs/index.json` 或任何 S1/S2/S3 冻结产物。

## 3. 交付物 3：Tier0 预算申请（只申请，不执行）

`docs/planning/dnext001_f_tier0_budget_proposal.md`（89 行，中文）

- 申请 ≤6 次真实 VSPAERO 启动；**申请 ≠ 批准**（`approved_by: null`、`max_launches: 0`）。
- 计费：每次进程启动=1、重试单独计费且最多 1 次、超时（900 s）照计费且不自动重试、无缓存规避、总额度 ≤6。
- 串行、单进程、NCPU ≤4、独立 run 目录、`BudgetLedger(physical_budget=6)` 预授权。
- 矩阵：T0-1a/T0-1b 重复性、T0-2 加密网格、T0-3 尾迹/残差收敛、T0-4 Sref/Cref/Bref 注入反推（误差 <1e-6）、
  T0-5 Xcg 16.821978 vs 28.287395 两工况、T0-6 弹性重试位；方案 A（默认 5 项 + T0-5 单工况 = 6 次）。
- 停机条件 6 条（NaN/超时/连续 2 次失败/Sref 反推失败/模板 SHA 不符/无法解释现象）→
  `fail_stop.json` + `stage_status=STOPPED_FAIL_CLOSED`；成功最多把内部系数置信度提到 PARTIAL，
  LF-M2.02/BODY-CORR/HF-M2.02 门禁状态不变。

## 4. 测试

命令 1（F 线新增）：

```powershell
Set-Location 'D:\RCAIDE\dnext001\wt-a1'
& 'D:\RCAIDE\envs\RCAIDE\python.exe' -m pytest research/concorde_metaopt/tests/test_f_line_records.py research/concorde_metaopt/tests/test_f_line_budget.py research/concorde_metaopt/tests/test_f_line_mock.py research/concorde_metaopt/tests/test_f_line_replay.py research/concorde_metaopt/tests/test_f_line_e2e.py -q
```

结果：**32 passed in 1.59 s**（要求 ≥8，实际 32）。覆盖：记录合法性/失败值 null 规则/约束顺序、
预算预授权与超发、0 费运行、缓存命中 0 费、重试逐次计费、Mock 几何非法与注入失败、
归档 replay 31 条索引与基线命中（objective=None）、未命中 EVALUATOR_ERROR、BO/DE E2E 全零物理调用、
7 类产物与 SHA256SUMS 校验、metrics 的 NOT_RUN 列。

命令 2（既有回归，确认 conftest 改动无破坏）：

```powershell
& 'D:\RCAIDE\envs\RCAIDE\python.exe' -m pytest research/concorde_metaopt/tests/test_budget_and_cache.py research/concorde_metaopt/tests/test_design_space_12d.py research/concorde_metaopt/tests/test_12d_pipeline.py -q
```

结果：**59 passed in 8.12 s**。

## 5. 未完成项与风险

未完成（本轮明确不做）：
1. 任何真实 VSPAERO/SU2/RCAIDE Mission 调用（Tier0 仅申请，未获 owner 批复）。
2. 12D 边界冻结：`design_space_12d_lifting_surfaces.yaml` 仍 `frozen: false` /
   `bounds_status: provisional_until_geometry_perturbation`，需几何效应矩阵与 owner 批准。
3. 力轴/力矩参考点的真值核对、BODY-CORR、HF-M2.02 均未触达。
4. 未做真实目标函数的 BO/DE 对比（合成目标无物理含义，不能作为算法结论）。

风险：
1. **合成目标不可外推**：线性占位响应只验证软件闭环，best 值（33371 / 33722 kg）无物理意义，
   不得写入任何性能结论或图。
2. **机翼 AC 被误当 CG 的文献级错误仍存在于旧报告**
   （`docs/reviews/p1p3_fullchain_validation_report_20261031.md:45` 写作 "PROVISIONAL CG"）；
   本轮审计已纠正并写入 `wing_ac_as_cg_allowed: false`，但旧文档未改（只读保留）。
3. **力矩参考点与力轴符号尚未核对**：即使未来 VSPAERO 正常返回 CL/CDi，CM 与配平结论仍不可用。
4. **run_config.json 记录了绝对路径**（`design_space_config: D:\RCAIDE\...`），跨机复现需重生成；
   属记录性瑕疵，不影响判定。
5. **maml_opt 0.1.0 的 ask 返回 dict 而非向量**、`tell` 对重复设计抛 ValueError，已在
   `search.py` 内适配；若升级 maml_opt 需重跑 E2E 测试。
6. `evaluation/ledger.py` 的旧账本把"非缓存评价零物理调用"判为 accounting_error，
   因此 F 线自建 `f_line/budget.py`；两套账本并存，后续需明确迁移口径。

## 6. 声明

- 本轮 **physical_call_count = 0**（全部 run：BO 10 次请求、DE 12 次请求、replay 6 次请求，物理求解 0 次）。
- 未启动 OpenVSP/VSPAERO/SU2/RCAIDE Mission/WaveDrag；未把 VSPAERO 内部 CL/CDi 当作整机油耗；
  未宣称任何物理 PASS；未改写任何 S1/S2/S3 冻结产物；未 push、未合并 main。
- 本回执路径：`docs/receipts/dnext001/a1-aviation-f_task_receipt.md`。
