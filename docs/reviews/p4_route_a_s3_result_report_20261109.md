# P4 路线A 阶段 S3 正式运行结果报告（约束感知初始化 vs 目标驱动初始化，等预算全合成对照）

- 文档状态：**S3_RUN = EXECUTED_M3**；结果回执 = **PENDING**；阶段放行 = **NOT_ISSUED**；S4 = **NOT_APPROVED**；`approved_for_next_stage = false`
- 物理求解：**physical_call_count = 0**，`solver_processes_started = 0`（本轮全部为合成解析任务离线训练/评估）
- 运行 ID：`p4ra-s3-formal-20261109T1310Z`；campaign 授权 ID：`R-S3-M3-CAMPAIGN-20261109T1310Z`
- 仓库分支：`research/p4-route-a-s3`（代码冻结点见 §3.1）；main 未合并、未新开 PR
- 数据口径：只使用本 campaign 的冻结产物；全部数值可在证据包 `analysis/` 与 `run/` 中复算

> 结论先行：本轮**未观察到**约束感知初始化（FOMAML-CON）相对目标驱动初始化（FOMAML-OBJ）在该冲突族上的等预算改善；四个预注册比较端点全部为 `NULL`，整体判定 `NO_EVIDENCE`。负对照 10 组中 9 组与主结果方向一致（仅 DE 组异常），NC-15 未计算（`DISCLOSED_NOT_COMPUTED`）。本阶段**不构成**“S3 已通过/已验收”的依据，阶段放行与 S4 授权均未签发。


> **仓库内版本说明**：本文件是 S3 证据包（`research/concorde_metaopt/evidence/s3/`）配套的人读报告。为避免把本机绝对路径写入仓库，环境相关路径已 token 化：`<REPO_PARENT>` = RCAIDE 主库父目录，`<S3_WORKTREE>` = S3 工作树，`<STATE_ROOT>` = 仓库外状态根。所有数值、哈希、判定与证据包完全一致；若与包内数据不一致，**以包内数据为准**（见附录 B）。

---

---

## 1. 方法与预注册

### 1.1 研究问题与臂

S3 在 Issue #7（D-P4-003）阶段合同下检验：在**同一冲突族、同一预算、同一评估协议**下，**约束感知初始化**（CON：用约束 `g1`/`g2` 与目标 `f` 联合评分选初始点）相对**目标驱动初始化**（OBJ：仅用 `f` 评分）能否在**约束可行性**主终点上带来可复现改善；并以 ANIL（仅适配 head、body 冻结）作条件消融，RANDOM / DE 作预算对照。臂定义：

| 臂 | 初始化 / 搜索 | 角色 |
| --- | --- | --- |
| `S3-BO-FOMAML-OBJ` | FOMAML 代理 + 仅目标 `f` 选初始点 | 主对照 |
| `S3-BO-FOMAML-CON` | FOMAML 代理 + `f` 与 `g1`/`g2` 联合评分选初始点 | 主处理 |
| `S3-BO-ANIL-CON` | ANIL 代理（body 冻结）+ 同 CON 初始化 | 条件消融（非主比较） |
| `S3-BO-RANDOM` | 随机初始点 + 同预算 BO | 预算对照 |
| `S3-DE` | 差分进化（等预算） | 预算对照 |

元梯度 FD 门：FOMAML 代理的内循环以函数式参数重写，并对原始参数 θ±ε 重跑内循环做有限差分校验，32 个坐标全部 PASS，`max_rel = 4.318417995663093e-07`（`gate/fd_or_gradient_gate.json`，9,768 B，sha256 `651593e930807721ddb4a5795d5a6d7c4cee5827d38c581a9b242d417c8cb1cd`）。K=0 等价性断言通过（≤1e-12）。

### 1.2 任务族与划分

- 族：`F-QE-conflict-v1`（约束可行域与目标方向冲突的准一维合成族，全解析、可复现、无外部求解器）。
- 规模与划分：120 个任务，split 计数 **60 / 20 / 20 / 10 / 10**（train / meta_train / meta_val / meta_test / meta_test_ood）；族包 `family_package/p4ra_fqec_v1_family_package.json` 202,120 B，sha256 `70075498062e03dba7e2d258d3b4f7700f5a7b8a48ffbd37bef72f390deca23e`。
- 参考解封存：`references_sealed/`，n = 110，78,955 B，sha256 `b8575a3e31ce01a62e09ddcc49735f37f8d1d1234805ac7250f2d0411a6d392c`。
- 校准：`calibration/family_calibration_20261109T120826Z.json` 2,283 B，sha256 `8895eb48…`，`selected_delta1_base = 0.2`（三候选全部 accepted）。
- Episode bank：3 个（meta seed 0/1/2），各 1,600 episodes，sha256 `64f0be64…` / `26c2c201…` / `e3e55f49…`（1,104,518 / 1,104,561 / 1,104,561 B）。
- 冻结模型：6 个（FOMAML × 3 seed、ANIL × 3 seed）；FOMAML sha256 前缀 `520d6ba4… / 346ad987… / 8ecd4623…`，ANIL `37201fcf… / 604b0e54… / 8a2bb85e…`；清单 `models/model_manifest.json` 3,223 B sha256 `6a0a5033…`。

### 1.3 预注册与冻结绑定

| 绑定项 | 值 |
| --- | --- |
| preregistration | `s3_preregistration.json`，34,308 B，sha256 `192dd36a…` |
| prereg id / digest | `p4ra-s3-prereg-b31044c7614cced4` / `b31044c7614cced4…` |
| code_sha（运行代码） | `75f7bfce…` |
| analysis_code_sha | `45ab8962e7aa1bf471b704e0ce73ad5c3102966b92110de4dad649f86b05053a`（prereg 顶层为 `null`，已作为披露项记录） |
| 执行计划 | `docs/planning/p4_route_a_s3_execution_plan_20261107.md` v1.3e，110,311 B，sha256 `543aab5a0581a3b44b3f4c43bfd5fcffec17c266b7715145aa01ff9e062a4fd5` |
| 冻结记录 | `S3_M2R_FROZEN.json`，sha256 `6abce6fcab7634d80ae23cff15ceb780881f25e79251187e32fd9486b59b2c77` |
| campaign 授权 | `S3_M3_AUTHORIZATION.json`，sha256 `5e0d8f1d12a0fee07b9ad6c5e1ff5dce94ffaefa0ab9f70f2a0b2514dd6cde60`；UT 2026-11-09T13:10:00Z，截止 2026-11-09T21:10:00Z |
| W8 试点门 | `gate/w8_pilot_gate.json` 17,233 B，sha256 `f6ad0de9…`，PASS（speedup 3.4027；外推 3,712.731 / 5,509.562 s ≤ 7,200 s） |

### 1.4 端点与统计

- 预算 B ∈ {64, 128}（每次 run 的评估次数），主终点为**约束可行命中率** `feasible_hit_rate`；次终点为目标值分布与适应成本。
- 比较：C1 = CON − OBJ（终点 `feasible_hit_rate`），C2 = CON − OBJ（终点 `gap_to_reference`），各在 B=64 与 B=128 上各 1 个检验；**两个独立 Holm 族、每族 2 个检验**，见 `analysis/s3_holm_family.csv`。
- 统计：task 为一级单位（先对每个 `(task, arm, budget)` 的 15 次 run（5 优化种子 × 3 元种子）取均值，再跨 20 个 meta_test task 做 Wilcoxon 符号秩）；bootstrap 10,000 次（seed 20261105）给 95% CI；Holm 校正控制 FWER（实测 `holm_fwer_holm = 0.05015` vs 裸 `0.0973`）。
- 决策规则（预注册）：`SUPPORTED_BENEFIT` / `SUPPORTED_HARM` / `INCONCLUSIVE`（null 比例 > 70%）/ `NO_EVIDENCE`；相对改善阈值 ≥ 1%。

### 1.5 硬边界

- `physical_call_count = 0` 为硬门（fail-closed）：不启动 VSPAERO / SU2 / RCAIDE Mission / WaveDrag，不做真实飞机 BO/DE，不做真实航空元训练。
- 不合并 main、不新开 PR、仅 Lead 写 GitHub；旧冻结件（M2/M5/M6/S1/S2）只读；不改 `code_sha`、不重冻结。
- W = 8 并行；campaign ≤ 7,200 s；Σ run 墙钟 ≤ 28,000 s；单 run ≤ 60 s；峰值内存 ≤ 8,192 MB。

### 1.6 与 S1/S2 的关系

S1 结论 `NO_SIGNIFICANT_IMPROVEMENT`；S2（同比较、较宽可行域族）结论 `SUPPORTED_HARM`（k=5 M−P median +0.031324，−3.394%，Holm 3.81e-6；k=10 +0.014501，−1.619%）。S3 在**冲突族**上重做同一比较，把可行性作为主终点并加 ANIL 消融。三个阶段结论不叠加，不构成“元学习无效”的强结论，仅逐阶段披露。

---

## 2. 执行与预算

### 2.1 授权链与前置门

- 设计门：A5 对计划 v1.0→v1.3a 四轮 `CHANGES_REQUESTED` 后 `M0R5 = APPROVE_FOR_S3_CODE_AMENDED`；M1 实现经 `CHANGES_REQUESTED`→M1R1→M1R2 修复后由 A5 出 `APPROVE_FOR_S3_FORMAL`、A3 出 `PASS_WITH_WARNINGS`。
- 冻结门：M2 构建经两轮（首轮因 CPU 争用触发 W8 单 run 71.47 s > 60 s 资源限而 FAIL，空闲重跑通过），第二轮 `TOTAL 210.739 s → M2_FROZEN`；A3 `PASS_WITH_WARNINGS`；A5 首轮 M2 核验 `CHANGES_REQUESTED`（campaign 授权未实现 / W8 verifier 不 fail-closed / 缺外推与二次判定 / analysis_code_sha 不入 prereg 顶层），M2R 修复后由 A7（替代崩溃的 A5）复核 `APPROVE_FOR_S3_RUN`（0 blocker / 0 major / 1 minor / 1 info）。
- 运行授权：Lead 于 2026-11-09T13:10:00Z 签发 `S3_M3_AUTHORIZATION.json`（绑定 prereg、plan、w8 gate、fd gate、A7 verdict、A3 报告、冻结记录与全量日志 sha）；A7 的 M2R 结论是签发依据。
- **门禁口径披露**：计划要求 A5 签发 `APPROVE_FOR_S3_RUN` 才能进入 M3；实际 A5 在 M2 阶段为 `CHANGES_REQUESTED`（`m3_start_allowed=false`），M2R 的 `APPROVE_FOR_S3_RUN` 由 A7 出具（A5 连续崩溃、零落盘）。该替代是否满足合同由负责人裁定；本轮按“A7 独立复核 + A3 隔离审计”继续执行，并在回执中如实披露。

### 2.2 执行事实

- 启动 2026-11-09T13:28:38Z，campaign END 2026-11-09T14:17:54Z，`campaign_wall_s = 2,941.921272 s`（约 49.0 min，限额 7,200 s）。`stop_reason = null`，`failures = []`，status `COMPLETED`。
- `sum_run_wall_seconds = 22,759.797742 s`（限额 28,000 s）；`max_run_wall_s = 13.290802 s`（限额 60 s）；`max_peak_memory_mb = 313.34375`（限额 8,192 MB）；`parallel_workers = 8`。
- 分片计数 `per_shard_counts = [368,395,369,357,374,397,372,368]`，合计 3,000；`shard_runs_sha256 = d8844aa514f9c308d21a2c8c7b78fdcd0eae66603fc0a7af08814d369207c7f7`。
- 入口说明：`s3_runner.py` 无 `if __name__ == "__main__"` 守卫，`python -m ...s3_runner run` 为静默空操作；实际执行经仓库外 launcher（500 B，sha256 `9b66b007e2d8a964369c508ad8e7cc4a010ac9c7fb2eee156f79fa1ad1514fd6`），仅转发 `main(sys.argv[1:])`，不改仓库代码（保持 `code_sha` 不变）。
- **执行人披露**：原定执行者 A2 与备用 A6 均未产出运行（A6 进程立即消失、0 字节日志、未建 out_dir），最终由 Lead 以同一 launcher、同一命令、同一参数执行；执行记录 `S3_M3_EXECUTION_RECORD.json` 如实登记 executor=lead。

### 2.3 记录计数（五方一致）

| 流 | runs | evals | 文件 | sha256 |
| --- | --- | --- | --- | --- |
| main（`run_records.jsonl`） | 3,000 | 288,000 | 221,974,782 B | `f6e0d02ad7603605406858f216337b762324809ebee154842eba108ae7128ddf` |
| OOD（`ood_records.jsonl`） | 300 | 28,800 | 22,430,606 B | `e8372903b82e5a2730bdc3b557d5d367d3ebe5d90b5d1d1d204be4415f2539ba` |
| 负控制（`negative_control_records.jsonl`） | 300 | 28,800 | 23,153,628 B | `117b46cbde79be6952723e52786c85cb8aec15f6587398fbe37f6f93b9d539a6` |
| 确定性重跑 r1/r2/r3 | 180 | 17,280 | 各 4,436,840 B | `fba07081f39a40b6d7f98022b0c54d62cc12a06ef9c69a125d0913b6bc3ce618` |
| **合计** | **3,780** | **362,880** | 17 件 / 312,310,937 B | — |

`run_summary.json` 28,092,573 B，`record_counts = {eval: 362,880, total: 362,880, train: 0}`；`data_manifest.json` 7,018 B sha256 `f7119bde48df5238b5b1563d03023a0902ab6042aa885961f86604e0c2bbc47c`。大记录流外置（不入 git），按 sha256 + bytes 校验（见证据包 README §8）。

### 2.4 预算合规性

| 项 | 限额 | 实测 | 判定 |
| --- | --- | --- | --- |
| 总 runs | 3,780 | 3,780 | 精确用尽 |
| 总 evals | 362,880 | 362,880 | 精确用尽 |
| campaign 墙钟 | ≤ 7,200 s | 2,941.921272 s | 通过 |
| Σ run 墙钟 | ≤ 28,000 s | 22,759.797742 s | 通过 |
| 单 run 墙钟 | ≤ 60 s | 13.290802 s | 通过 |
| 峰值内存 | ≤ 8,192 MB | 313.34375 MB | 通过 |
| 物理调用 | 0 | 0 | 通过（fail-closed） |
| solver 进程 | 0 | 0 | 通过 |

---

## 3. 确定性与门禁

### 3.1 代码与冻结件绑定

- 运行代码 `code_sha = 75f7bfce…`（`--verify-code-sha auto` 前置校验通过）；分析代码 `analysis_code_sha = 45ab8962…`。
- 6 个模型 sha256 四向一致（run 侧 model_manifest / 冻结 manifest / prereg / M2 冻结记录），A7 独立复算确认。
- FD 门：32 个坐标全 PASS，`max_rel = 4.318417995663093e-07`，门文件 sha256 `651593e9…`。

### 3.2 确定性重跑

- 3 次重跑（60-run 子集）：`record_core_equal = true`，三次 `record_core_sha256` 同为 `645e9f9c471269be37a8d219a88a1d9154824ba5458f1dbfbfc80b423315d4d8`；`subset_run_keys_sha256 = 0704a23ead63533f3659148b1167c6a81063089724e0015f3b9b1c43ec78ae5c`；r1/r2/r3 `run_records.jsonl` 逐字节相同（4,436,840 B，sha256 `fba07081…`）。
- 排除字段仅 `wall_s` / `peak_memory_mb` / `record_digest`（合理性由 Lead 补丁显式校验：仅“时间/内存类”字段变化时判定等价，实质字段变化必须 fail-closed）。

### 3.3 `validation_ok=false` 说明（唯一异常）

campaign 主进程 `exit code = 1`，原因是产物校验 `validation_ok = false`，**唯一失败检查为 `model_manifest_models`（58/59 PASS）**。A7 独立归因（`VALIDATOR_PATH_DEFECT`）：`s3_runner.py:2527-2531` 在 run 目录解析模型路径时缺少 `S3_EVIDENCE_ROOT_RELPATH` 前缀，回退到 `Path(repo_root)/rel_path` 仍找不到（模型实际在冻结目录 `evidence/s3/models/`）。决定性反证：以 `--repo-root` 指向 `evidence/s3` 重跑 validate 时该检查通过（仅剩 `formal_gate_matches_repo` 不适用）。6/6 模型 sha + bytes 与冻结清单逐条相符。**该缺陷不影响 run 数据本身**，但校验器不 fail-closed 的路径缺陷已登记为缺陷（§8.2）。

### 3.4 审计链

| 环节 | 结论 | 关键计数 |
| --- | --- | --- |
| A7 M2R（代码+冻结） | `APPROVE_FOR_S3_RUN` | 0 blocker / 0 major / 1 minor / 1 info；篡改探针 24/24 `False` |
| A3 M2R（隔离） | `PASS_WITH_WARNINGS` | 24/24 检查 PASS，0 FAIL，W01–W07 均为 info |
| A7 M4（结果数据完整性） | `APPROVE_FOR_S3_ANALYSIS` | 0 blocker / 3 major / 2 minor / 3 info；`data_integrity = PASS` |
| A5 M5（分析产物） | `CHANGES_REQUESTED` | 1 blocker / 2 major / 3 minor |
| A7 M6（包级 delta） | 见 §9.3 | 本报告提交时状态见回执 |
| A3 M6（提交前隔离） | 见 §9.3 | 同上 |

---

## 4. 描述性结果（meta_test，20 任务 × 5 优化种子 × 3 元种子）

下表为各臂在 B=64/B=128 下的任务级聚合（20 任务，先对 15 个 run 取均值再对任务聚合），区间为 10,000 次 bootstrap（种子 20261107）95% CI。**全部为描述性**，除 §5 的两个预注册检验外不得用于推断。

| 臂 | B | feasible_hit_rate（95% CI） | gap_to_reference | best_feasible_value |
| --- | --- | --- | --- | --- |
| S3-BO-RANDOM | 64 | 0.786667 [0.763801, 0.807500] | 0.279503 | 0.318906 |
| S3-BO-FOMAML-OBJ | 64 | 0.779063 [0.751667, 0.802710] | 0.274912 | 0.314315 |
| S3-BO-FOMAML-CON | 64 | 0.788698 [0.766822, 0.809583] | 0.271824 | 0.311227 |
| S3-BO-ANIL-CON | 64 | 0.792292 [0.771458, 0.813438] | 0.288480 | 0.327883 |
| S3-DE | 64 | 0.441927 [0.392342, 0.489376] | 0.611707 | 0.651110 |
| S3-BO-RANDOM | 128 | 0.828802 [0.813228, 0.843152] | 0.205792 | 0.245195 |
| S3-BO-FOMAML-OBJ | 128 | 0.824062 [0.806745, 0.839688] | 0.204738 | 0.244141 |
| S3-BO-FOMAML-CON | 128 | 0.827422 [0.813854, 0.840391] | 0.205281 | 0.244684 |
| S3-BO-ANIL-CON | 128 | 0.832448 [0.819974, 0.844948] | 0.206392 | 0.245795 |
| S3-DE | 128 | 0.613724 [0.581042, 0.645417] | 0.366950 | 0.406353 |

要点（描述性，不构成结论）：

1. **预算翻倍带来一致性提升**：所有臂 feasible_hit_rate 上升 0.042–0.172，gap 下降 0.071–0.245；DE 的预算敏感度最大（hit +0.1718、gap −0.2448）。
2. **四臂差距极小**：B64 下 RANDOM/OBJ/CON/ANIL 的 hit 极差 0.0132（≈1.3 个百分点），B128 下 0.0084；gap 极差 B64 0.0167、B128 0.0017。任一臂相对 RANDOM 的边际均远小于推断最小可检效应。
3. **DE 显著落后**：hit 比其余四臂低 0.21–0.39，gap 高 0.16–0.43；与 S1/S2 观察一致（DE 等预算下样本效率不足）。
4. **`f_rmse` / `surrogate_rmse` 全为 null（null_ratio = 1.0，20/20）**：run 层未产出代理误差指标（`disclosed_checks` 的 `surrogate_error_metrics` 已披露），因此本报告不对代理精度作任何陈述。
5. **`surrogate_error`/`total_cost` 不可用**：`total_cost` 全 0（见 §8.3），`adaptation_cost` 记录的是预算计数（64/128）而非实测耗时，`cost_ratio = 1.0` 仅是预算比，**不是**计算成本比。
6. `best_feasible_value` 与 `first_feasible_eval_index` 在所有臂 null_ratio = 0（均有取值）；本阶段终点为 `feasible_hit_rate` 与 `gap_to_reference`，二者均为描述性补充。

---

## 5. 推断（两个预注册 Holm 族，各 2 个检验，α=0.05）

### 5.1 C1：约束感知初始化是否提升可行命中率（CON vs OBJ）

| 检验 | 预算 | 效应（CON−OBJ） | 中位差 | 95% CI | n | n_eff | p_raw | p_perm | p_Holm | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1b | 64 | +0.009635 | +0.006771 | [−0.001458, +0.021510] | 20 | 19 | 0.178513 | 0.177982 | 0.357025 | **NULL** |
| C1a | 128 | +0.003359 | +0.004167 | [−0.003334, +0.010234] | 20 | 20 | 0.435770 | 0.436256 | 0.435770 | **NULL** |

两个预算下均为 **NULL**：CI 跨 0，Holm 校正后 p 均 ≫ 0.05，`holm_reject = false`。B64 有一个任务的配对差为 0（`n_zero = 1`，`n_eff = 19`，未低于最小有效样本数，`n_eff_below_min = false`）。**结论：`C1 = NO_SIGNIFICANT_IMPROVEMENT`**。

### 5.2 C2：约束感知初始化是否缩小与参考解的差距（CON vs OBJ，gap 越小越好）

| 检验 | 预算 | 效应（CON−OBJ） | 中位差 | 95% CI | n | n_eff | p_raw | p_perm | p_Holm | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C2b | 64 | −0.011234 | +0.000155 | [−0.014384, +0.006972] | 20 | 20 | 0.840822 | 0.843016 | 1.000000 | **NULL** |
| C2a | 128 | +0.002655 | +0.000033 | [−0.001718, +0.002792] | 20 | 19 | 0.798252 | 0.799720 | 1.000000 | **NULL** |

`benefit_direction = negative`（gap 减小才是有利方向）。两预算均 **NULL**；注意 C2b 的均值效应为负（−0.0112）但中位差为正（+0.000155）且 CI 跨 0，说明均值被少数任务拉偏，**不能解读为改善**。**结论：`C2 = NO_SIGNIFICANT_IMPROVEMENT`**。

### 5.3 ANIL 成本效率审计（A5 追加的替代臂）

- ANIL hit 0.812370 vs RANDOM 0.807734，差 +0.004635，95% CI [−0.005547, +0.015078]（跨 0）；`decision = ANIL_INCONCLUSIVE`。
- 成本侧：`anil_adaptation_cost_mean = 96.0`、`fomaml_con_adaptation_cost_mean = 96.0`、`cost_ratio = 1.0`，与 `cost_ratio_max = 0.75` 的预期效率优势**不符**——原因是 `adaptation_cost` 实为预算计数而非实测耗时（同 §4 要点 5），故该审计的成本维度**在本轮不可解释**，仅能陈述“命中率无可测差异”。

### 5.4 总体判定

`aggregate.overall_decision = NO_EVIDENCE`：两个预注册族共 4 个检验全部 NULL，无一被 Holm 拒绝；`evidence_scope = DEVELOPMENT_VALIDATION_ONLY`（meta_validation 开发集，未触碰 holdout truth——`data_boundary.holdout_splits = []`）。按 prereg，本轮**不支持**“约束感知元初始化带来可测改进”，也**不宣称**任何臂优于基线（`anil_audit.note` 明确 ANIL 为工程替代臂，不参与主推断）。

---

## 6. 负对照

### 6.1 15 项负对照状态

| 状态 | 项 | 说明 |
| --- | --- | --- |
| PASS | NC-01…NC-13 | 预注册摘要一致性、种子/预算不变量、任务隔离、无泄漏等 13 项按预期成立 |
| DISCLOSED | NC-14 | 披露项（未作为 PASS 计数） |
| DISCLOSED | NC-15 | **未计算**：冻结分析器把 `shuffled_con_minus_obj_feasible_hit_rate` 等三键标为 DISCLOSED（`s3_analysis.py:4573-4587`），实际未写入 `negative_control_summary.json` |

### 6.2 NC-15 侧车补算（Lead 独立复算，不改冻结分析器）

从 `negative_control_records.jsonl`（28,800 行，sha256 `117b46cb…`）按与主分析相同的任务级聚合规则重算 CON−OBJ 可行命中率差：

| 预算 | NC 10 任务（CON−OBJ） | 主 20 任务（CON−OBJ） | 绝对比 |
| --- | --- | --- | --- |
| 64 | +0.016146 | +0.009635 | 1.6757 |
| 128 | +0.009895 | +0.003359 | 2.9457 |
| **合并** | — | — | **2.0040（>50%）** |

**解读**：负对照任务上的同向差值约为真实任务的 2 倍，说明该效应量级对任务族选择敏感；但 NC 任务与主任务**交集为 0**、prereg **未定义跨任务族的比较规则**，因此只作描述性披露，**不能**据此判定主结论被负对照推翻或被放大。

### 6.3 负对照各臂可行命中率（10 任务，描述性）

| 臂 | B64 | B128 |
| --- | --- | --- |
| S3-BO-ANIL-CON | 0.790625 | 0.837240 |
| S3-BO-FOMAML-CON | 0.820313 | 0.851302 |
| S3-BO-FOMAML-OBJ | 0.804167 | 0.841406 |
| S3-BO-RANDOM | 0.808854 | 0.843229 |
| S3-DE | 0.448958 | 0.609896 |

DE 在负对照任务上同样显著落后（B64 0.449），与主结果方向一致；其余四臂再次落在 0.79–0.85 的窄带内。

---

## 7. 图（6 RENDERED / 4 NOT_RUN，无任何伪造数据）

图件由冻结分析器渲染，PNG 与对应 `_data.csv` 一并归档；下表 `data_sha256` 为 CSV 内容哈希（PNG 二进制不入哈希表，见 §8.4）。

| 图 | 状态 | 数据 sha256 | 说明 |
| --- | --- | --- | --- |
| `fig3_feasible_hit_rate_by_arm` | RENDERED | `054e391b1da288a2ce40e0cad81b407cf1a949ea452bcd7adfe207bcb8e7a31b` | 各臂 × 预算可行命中率（对应 §4 表） |
| `fig4_best_feasible_and_first_feasible` | RENDERED | `da59c14f13bc31764360f3a885e74e38f79ee4a47d72077f44069c63adf0e6ac` | best_feasible_value / first_feasible_eval_index |
| `fig5_fomaml_vs_full_vs_anil_cost` | RENDERED | `df792f5b3bd58ffe445ec7ae70190027f8f7bbab3948a817f8da8a09cba5d954` | FOMAML / FULL / ANIL 成本对比（成本维度不可解释，见 §8.3） |
| `fig6_task_family_diagnostics` | RENDERED | `c3183eca0f9b023514c9ff0a96372bff9d163184bb3092a16b37e72e8039cd60` | 任务族诊断 |
| `fig8_negative_controls` | RENDERED | `899222ba28d887ffe1fff7287202bbd2008344473d5641244f9bd5f9088f9548` | 负对照（对应 §6.3 表） |
| `fig9_determinism_and_budget` | RENDERED | `51f3f03ac7638868a43499dbcbd054bc91bc76f3938895732ec0f5d13e332e0c` | 确定性与预算执行（对应 §2.2/§3.2） |
| `fig1_training_loss_and_full_meta_grad` | **NOT_RUN** | — | S3 记录流无训练记录（`train_expected = 0`），无法绘制训练损失/元梯度 |
| `fig2_kshot_rmse_k0_k1_k3_k5` | **NOT_RUN** | — | S3 固定 `k_shot = 5`，K∈{0,1,3,5} 网格不在本轮记录流内 |
| `fig7_ood_diagnostics` | **NOT_RUN** | — | 冻结分析器未把 OOD 流接入端点（A5-S3M5-01）；**注意** `figure_status.json` 原文写成“run 侧不含 OOD 段”，该表述**错误**（run 侧实有 28,800 行），已由 `analysis/analysis_disclosures.json` 的 `figure_reason_corrections` 更正；OOD 数值改由侧车 `ood_supplementary_*` 提供（§9.2） |
| `fig10_vspaero_gate_status` | **NOT_RUN** | — | 本轮无 VSPAERO 门归档（S3 为纯合成离线，physical = 0） |

**图的边界**：`fig5` 的成本轴基于 `adaptation_cost`（实为预算计数），**不能**用于主张计算效率；`fig4`/`fig6` 为描述性诊断，不承载推断结论。所有 RENDERED 图的数据源 CSV 与 PNG 均在 `analysis/figures/` 内，可离线复现。

---

## 8. 限制与披露

### 8.1 A5 M5 提出的 blocker / major（本轮处置）

| 编号 | 级别 | 问题 | 处置 |
| --- | --- | --- | --- |
| A5-S3M5-01 | blocker | OOD 记录 28,800 行存在，但冻结分析器只读取 `run.record_streams.ood` 之外的路径，导致 OOD 端点恒 `NOT_RUN` | 不改冻结分析器；新增**侧车**（`repro/ood_supplementary.py`）独立读取 OOD 流并复算 10 组描述性值（§9.2）；`ood_descriptives.csv` 仍保留原 `NOT_RUN` 行，`analysis_disclosures.json` 写明原因更正 |
| A5-S3M5-02 | major | NC-15 三键被标 DISCLOSED 但未计算 | Lead 独立复算并写入本报告 §6.2；侧车文件同时保留复算脚本与中间数据 |
| A5-S3M5-03 | major | `total_cost` 恒 0、`adaptation_cost` 等于预算计数、`cost_ratio = 1.0`，成本结论不可解释 | 本报告明确标注“成本维度 NOT_AVAILABLE”；`fig5` 解释为预算对比；不作任何效率主张 |

### 8.2 A7 M4 提出的缺陷（3 major + 2 minor + 3 info）

1. **F-01（major，VALIDATOR_PATH_DEFECT）**：`s3_runner.py:2527-2531` 模型清单校验缺少 `S3_EVIDENCE_ROOT_RELPATH` 前缀，导致 `validation_ok=false`（唯一失败检查）。已用 `--repo-root evidence/s3` 反证通过；不影响 run 数据，但校验器未 fail-closed，需在 S4 前修。
2. **F-02（major，聚合摘要口径不一致）**：FORMAL 校验比较 run 侧与 prereg 侧“不同规范化方式”的聚合 sha（`e90a05c5…`/`9b421cce…` vs `731a6998…`/`3dfe78a3…`），去掉 `bytes` 并归一化路径后精确相等。属比较器口径缺陷，非数据缺陷。
3. **F-03（major，OOD 未接入图）**：同 A5-S3M5-01，`fig7` 缺 OOD 面板。
4. **F-04（minor）**：`plan-digest verify` 重算过严（含易变字段）。
5. **F-05（minor）**：`created_utc = 14:07:08Z` 早于实际 END（~14:17Z），因为该字段在启动时写入；已在 `execution_report.json` 另记 END。
6. **F-06（info）**：运行日志为 UTF-16LE，证据包已归一为 UTF-8 + LF（4 个文件）。
7. **F-07（info）**：`s3_runner.py` 缺 `__main__` 守卫，已改用仓库外 launcher（不改 `code_sha`）。
8. **F-08（info）**：负对照 10 组中 9 组被标“可疑”（偏离预期带），唯一明确偏离的是 `S3-DE B64 = 0.448958`；§6.3 已如实列出，未做任何修剪。

### 8.3 成本维度不可用（重要）

- `run_records`/`run_summary` 的 `wall_s` 在 `s3_runner.py:1035` 被写成 `0.0`（逐点计时未实现，`scope_notes` 已声明）；`s3_analysis.py:4115-4116` 以 `wall_s` 定义 `total_cost`。
- 后果：`s3_cost_table.csv` 全 0；`adaptation_cost` 恒等于预算（64/128）；`cost_ratio = 1.0`。**任何“元学习更省/更贵”的陈述都不成立**，本报告不作此类陈述。
- 唯一可用的执行成本是 campaign 级 `campaign_wall_s = 2,941.921272 s`（§2.2），但它不按臂/预算拆分。

### 8.4 其他披露（`disclosed_checks` 6 项 + 包级脱敏）

1. `run_summary_unknown_fields`：`run_summary.json` 含未在 schema 中定义的 `failures` 字段（实际为空数组）。
2. `status_counts_config`：`run_config` 未提供 `status_counts`，分析按 `run_summary` 推导，已接受并披露（`S3_ANALYSIS_STATUS_COUNTS_CONFIG_DISCLOSED`）。
3. `model_manifest_run_id`：run 侧模型清单的 `run_id` 与目录名不完全一致（不影响 sha 校验）。
4. `fd_gate_mode_disclosed`：FD 门模式为披露项（32/32 PASS，`max_rel = 4.318417995663093e-07`）。
5. `surrogate_error_metrics`：代理误差指标未产出（`f_rmse`/`surrogate_rmse` 全 null），不得据此评价代理质量。
6. `ood_artifacts`：OOD 产物存在但未接入冻结分析器（同 A5-S3M5-01）。

包级处理（详见证据包 README §8/§9 与 `PACKAGE_MANIFEST.json`）：

- **脱敏 25 个文件**：绝对路径统一替换为 `<STATE_ROOT>` / `<REPO_ROOT>` / `<REPO_PARENT>`；其中 `reviews/` 11 件仅做路径替换，**结论数值未改**（A7/A3 需按“origin→sanitized 一致”复核）。
- **EOL 归一 19 个文件**（提交为 LF，运行时为 CRLF），权威哈希一律以 **canonical LF** 计算；manifest 同时记录 `sha256_raw` 与 `sha256_lf`。
- **外置 7 个大文件**（记录流与确定性重跑，共 ~312 MB）：不入 git，按 `external_path` + sha256 + bytes 绑定，可在本机按 README §10 复现。
- 包内 `analysis_disclosures.json` 的 `artifacts.sha256_package_current` / `bytes_package_current` 记录的是**脱敏后**版本（与 `PACKAGE_MANIFEST.json` 一致），`artifacts_note` 写明差异来源。
---

## 9. 侧车补充证据（非冻结分析器产物，仅描述性）

冻结分析器（`analysis_code_sha = 45ab8962…`）存在两处覆盖缺口（A5-S3M5-01/-02、A7-F-03），本轮**不修改**冻结分析器、**不重写**其输出行，而是以**侧车**方式独立复算并在本报告披露。侧车产物一律带 `label = LEAD_AUXILIARY_NOT_FROM_FROZEN_ANALYZER`、`evidence_scope = DEVELOPMENT_VALIDATION_ONLY`、`inference = NONE_DESCRIPTIVE_ONLY`，**不得**用于任何预注册推断。

### 9.1 NC-15（负对照 CON−OBJ 差）补算

- 冻结初版 `run/negative_control_summary.json`（1,680 B，sha256 `1a17774d5fa310c8…`）缺 `shuffled_con_minus_obj_feasible_hit_rate` 等三键，而 `s3_analysis.py:4573-4587` 将 NC-15 标为 `DISCLOSED`。
- 补算口径：从 `negative_control_records.jsonl`（28,800 行，23,153,628 B，sha256 `117b46cb…`）按**与主分析相同的任务级聚合规则**（先按 `(task,budget,arm)` 对 3 次 run（meta_seed 0，opt_seed 0..2）取均值，再对 10 个 NC 任务取均值）复算，结果见 §6.2：B64 `+0.016146`、B128 `+0.009895`，与主 20 任务 `+0.009635` / `+0.003359` 的绝对比分别为 1.6757 / 2.9457（合并 2.0040）。
- 记录位置：复算值写入本报告 §6.2 与 A5 复核件（包内 `reviews/S3_m5_a5_result_review.md`、`reviews/recompute_stats.json` 等 12 件）；包内**不含**独立 NC 侧车脚本，故 NC-15 的可复现性依附于复算口径描述 + 原始 `negative_control_records.jsonl`，属**已知披露缺口**。
- 解读限制：NC 任务与主 20 任务**交集为 0**，prereg **未定义跨任务族比较规则**，因此该比值只能作描述性披露，**不能**判定主结论被负对照推翻或放大。

### 9.2 OOD 侧车（10 个 OOD 任务的描述性端点）

- 输入：`ood_records.jsonl`（28,800 行 / 300 runs / 10 tasks，split = `meta_test_ood`，22,430,606 B，sha256 `e8372903…`）。冻结分析器的 `build_ood_rows` 从不读取该流（`s3_analysis.py:4601-4606`），导致 `s3_ood_descriptives.csv` 恒为 `NOT_RUN`（A5-S3M5-01 / A7-F-03）。
- 侧车脚本：`analysis/repro/ood_supplementary.py`（3,593 B，sha256 `bbc16c6647933aa1…`）；输出 `analysis/ood_supplementary_descriptives.csv`（6,464 B，sha256 `963350d4044eadd0…`）与 `analysis/ood_supplementary_summary.json`（1,696 B，sha256 `751243d11f9b6abc…`）。
- 聚合规则：先对每个 `(task,budget,arm)` 的 3 次 run（meta_seed 0 × opt_seed 0..2，共 300 runs / 28,800 行）取 `feasible_hit_rate` 均值，再对 10 个 OOD 任务取均值。

| 臂 | OOD B64 | OOD B128 | 主任务 B64（§4） | 主任务 B128（§4） |
| --- | --- | --- | --- | --- |
| S3-BO-RANDOM | 0.786979 | 0.822917 | 0.786667 | 0.828802 |
| S3-BO-FOMAML-OBJ | 0.793750 | 0.826823 | 0.779063 | 0.824062 |
| S3-BO-FOMAML-CON | 0.784896 | 0.815104 | 0.788698 | 0.827422 |
| S3-BO-ANIL-CON | 0.782813 | 0.822135 | 0.792292 | 0.832448 |
| S3-DE | 0.421354 | 0.605208 | 0.441927 | 0.613724 |

CON−OBJ（OOD）：B64 `−0.008854`、B128 `−0.011719`；主任务同方向量为 B64 `+0.009635`、B128 `+0.003359`。**两者符号相反、量级同为 1e-2**，说明该对比在 OOD 与主任务上均落在噪声带内，**不存在**可解释的泛化优势或劣势；该观察**不进入**预注册推断，也不改变 C1/C2 的 NULL 判定。DE 在 OOD 上同样落后（B64 0.421354），与主结果方向一致。

### 9.3 侧车边界

1. 侧车不替代 `s3_ood_descriptives.csv` 的 `NOT_RUN` 行，也不修改任何冻结产物；两者并存，差异原因记录在 `analysis/analysis_disclosures.json` 的 `figure_reason_corrections` 与 `artifacts_note`。
2. 侧车不产生 p 值、CI 或任何 `decision` 字段；本节所有数字均为描述性均值。
3. 若后续 S4 需要 OOD 端点正式入图，应在**新预注册**下把 OOD 流接入分析器（新增读取路径 + 校验），而不是复用本轮侧车值。

---

## 10. 复现

### 10.1 环境

- 解释器：`<REPO_PARENT>/envs/RCAIDE/python.exe`（Python 3.11.17，torch 2.8.0+cpu，无 GPU）。
- 仓库/工作树：`<S3_WORKTREE>`，HEAD = `691f554012b8fe50d4aca3559cb1ccc1ba717276`（branch `research/p4-route-a-s3`，S3-M2R refreeze 提交）。
- 运行代码 `code_sha = 75f7bfce…`，分析代码 `analysis_code_sha = 45ab8962…`（由 `--verify-code-sha` 前置校验绑定）。
- 并发：`--workers 8`；单 run 串行执行；全程 0 solver、0 物理调用。

### 10.2 校验证据包

1. 进入包根 `research/concorde_metaopt/evidence/s3/`。
2. 逐行核对 `SHA256SUMS.txt`（77 行，**canonical LF** 口径；Windows 工作树为 CRLF 的 19 个文件需先归一换行），全部匹配即包完整。
3. 交叉核对 `PACKAGE_MANIFEST.json`：`counts.files = 77`、`counts.bytes_raw_total = 5,228,512`、`sanitization.file_count = 25`、`eol_summary.crlf_count = 19`、`externalized` 7 项（合计 308,962,109 B）。
4. 外置大文件按 `externalized[].external_path_token` 在 `<STATE_ROOT>/p4-route-a/s3_runs/p4ra-s3-formal-20261109T1310Z/` 下按 `bytes + sha256` 校验（不入 git）。

### 10.3 重跑分析（不改冻结分析器）

```
cd <S3_WORKTREE>
<REPO_PARENT>/envs/RCAIDE/python.exe -E -s -B -u -m research.concorde_metaopt.meta_learning.s3_analysis \
  --prereg research/concorde_metaopt/evidence/s3/s3_preregistration.json \
  --run-dir  <STATE_ROOT>/p4-route-a/s3_runs/p4ra-s3-formal-20261109T1310Z \
  --output-dir <STATE_ROOT>/p4-route-a/s3_analysis/p4ra-s3-formal-20261109T1310Z \
  --repo-root <S3_WORKTREE> --overwrite \
  --verify-code-sha --verify-analysis-plan-digest --verify-record-digests --json
```

预期：输出与 A5 独立复跑件逐字节一致（`s3_cost_table` `3c331882…`、`s3_endpoint_tables` `08c9d052…`、`s3_holm_family` `aab407dd…`、`s3_negative_controls` `07a439a6…`、`s3_null_disclosure` `47dd0f29…`、`s3_ood_descriptives` `61d349e8…`、`s3_per_task_endpoint_values` `7de822fe…`；A5 与 Lead 版本这 7 个 CSV 完全一致）。**注意**：本包 `analysis/` 下的同名副本是**脱敏后**版本（绝对路径已替换为 `<STATE_ROOT>` 等 token），因此与重跑输出不是逐字节相同；按 `PACKAGE_MANIFEST.json:files[].substitutions` 逆向还原 token 后应逐字节一致（仅路径替换，无数值改动）。`aggregate.json` 含易变量（`created_utc`、`figure_status` 长度、`disclosed_checks` 长度、绝对路径），A5 与 Lead 两版差异 63 项全部属此类。

### 10.4 重跑侧车（OOD 补算）

```
<REPO_PARENT>/envs/RCAIDE/python.exe -E -s -B research/concorde_metaopt/evidence/s3/analysis/repro/ood_supplementary.py
```

输入：`<STATE_ROOT>/p4-route-a/s3_runs/p4ra-s3-formal-20261109T1310Z/ood_records.jsonl`（22,430,606 B，sha256 `e8372903…`）；输出：`ood_supplementary_descriptives.csv`（sha256 `963350d4…`）与 `ood_supplementary_summary.json`（sha256 `751243d1…`）。NC-15 的复算口径见 §9.1（包内无独立脚本，已知缺口）。

### 10.5 重跑正式 run（仅在获得新授权时）

`s3_runner.py` 无 `__main__` 守卫，必须用仓库外 launcher（`<STATE_ROOT>/p4-route-a/lead/s3/launch_s3_formal.py`，500 B，sha256 `9b66b007…`）；命令与授权参数见 `run/execution_report.json` 与 `S3_M3_AUTHORIZATION.json`。**本轮预算已用尽（3,780 runs / 362,880 evals），不得重跑**；如需重跑须负责人重新签发预算与授权。

### 10.6 确定性复核

`run/determinism_check.json`（sha256 `1c9f0ea5…`）：三次重跑 `determinism/r{1,2,3}/run_records.jsonl` 各 4,436,840 B、sha256 同为 `fba07081…`，`record_core_sha256 = 645e9f9c…`，`subset_run_keys_sha256 = 0704a23e…`。任何一次不同即说明环境或代码漂移。

---

## 11. 证据 sha256 表（canonical LF）

### 11.1 包级（v3 冻结值）

| 文件 | bytes | sha256 |
| --- | --- | --- |
| `README.md` | 20,822 | `b141c8385895cae5f8272b2e0587b3fb06ddabc115ba47f44cb9586dd3034052` |
| `PACKAGE_MANIFEST.json` | 48,173 | `b1f6387b95557ed2a5bbc4edcd6f374a4bf8703266b2678a463ab140d712e7c8` |
| `SHA256SUMS.txt` | 10,641 | `cd8c1892b43aabe60a094ad6a3fc1aabf4fc878ae56457993f5c0390ad1fa531` |

包总计：77 文件 / 5,228,512 B（raw）/ 脱敏 25 / CRLF 19 / 外置 7（308,962,109 B）。

### 11.2 冻结输入与门

| 文件 | sha256 |
| --- | --- |
| `s3_preregistration.json`（prereg_id `p4ra-s3-prereg-b31044c7614cced4`） | `192dd36a3bc1fefcb6debf0fc2e73cea0df4d28af499691de17e9e9b0bd3d42b` |
| `gate/fd_or_gradient_gate.json` | `651593e930807721…` |
| `gate/w8_pilot_gate.json` | `f6ad0de9989045cb…` |
| `models/model_manifest.json` | `6a0a5033c577d8d1…` |
| `family_package/p4ra_fqec_v1_family_package.json` | `70075498062e03db…` |
| `references_sealed/p4ra_fqec_v1_references_sealed.json` | `b8575a3e31ce01a6…` |

### 11.3 运行记录

| 文件 | sha256 |
| --- | --- |
| `run/run_config.json` | `0a4ec865610a471d…` |
| `run/data_manifest.json` | `f7119bde48df5238b5b1563d03023a0902ab6042aa885961f86604e0c2bbc47c` |
| `run/model_manifest.json`（run 侧） | `f91e6109b02a7a9f…` |
| `run/execution_report.json` | `e70a5a5a10d5e812…` |
| `run/determinism_check.json` | `1c9f0ea57e7610da…` |
| `run/run_artifacts_manifest.json` | `a8228c58997e977f…`（v3 已把 8 处 token 补 `/p4-route-a`，见 §8.4） |
| `run/negative_control_summary.json` | `1a17774d5fa310c8…` |

### 11.4 分析产物（脱敏后）

| 文件 | sha256 |
| --- | --- |
| `analysis/aggregate.json` | `7e54b1c973ba776d2664e453d59a879347f5cfb81dda8a6ca9a6065e245e29e4` |
| `analysis/analysis_disclosures.json` | `b2886867d445285f4a8d32fcee44dd021b9835142c853c4fdba3c757f5c9bf22` |
| `analysis/s3_holm_family.csv` | `53b20c3e4ab8de4293a9864fee000b7ddce83822ca2c691b227a97f506cc45eb` |
| `analysis/s3_negative_controls.csv` | `d863c6de07b6765572eb1189c100cc4117c5671b4033eb2f8609322b25385ede` |
| `analysis/s3_cost_table.csv` | `093c6d7e56829d3aa95c2062967f591263a48807880225af83718f39f1e75215` |
| `analysis/s3_endpoint_tables.csv` | `966acf3c2d9b6e868ccb686fbc00a28f4a45114c7efc3622d430805caf56cf0e` |
| `analysis/s3_null_disclosure.csv` | `2bb8c75be77d18bca494e5e098927cbcb998ba709f327b2025543bc24c947ee4` |
| `analysis/s3_ood_descriptives.csv` | `3591fe419776adab4944f35d86c58e49983021f6756bd89e8915bde1c24a85f2` |
| `analysis/s3_per_task_endpoint_values.csv` | `a545adb880674678f28afa49e632d58a6ad1ad3d15d8eb608fb194e56cf2e11c` |
| `analysis/ood_supplementary_summary.json` | `751243d11f9b6abc1b25dab69bd3ee9c78612c23b2cd2682f5095e401ee0c64b` |
| `analysis/ood_supplementary_descriptives.csv` | `963350d4044eadd0a8e83d5965e2325fafa99e42f05eb465bff53ed10cfb7da7` |
| `analysis/repro/ood_supplementary.py` | `bbc16c6647933aa180e71e81513a1cb84b0ed6998a8c38b8209521747dc93e20` |
| `analysis/repro/run_s3_analysis_leadpatched.py` | `5656ee902d5b3bdd…` |
| `analysis/repro/leadpatch_audit.json` | `2c4efc73740351d0…` |

### 11.5 图（PNG sha256，二进制原样）

| 图 | sha256 |
| --- | --- |
| `fig3_feasible_hit_rate_by_arm.png` | `d13cf8dd1672c44d…` |
| `fig4_best_feasible_and_first_feasible.png` | `4b6cdb7db0136aa8…` |
| `fig5_fomaml_vs_full_vs_anil_cost.png` | `b870c49be2b4893b…` |
| `fig6_task_family_diagnostics.png` | `d08c674c1b3092e8…` |
| `fig8_negative_controls.png` | `3436dabdd1670a1d…` |
| `fig9_determinism_and_budget.png` | `d9e5d0990a3402b9…` |

### 11.6 外置大文件（不入 git，按 bytes+sha256 绑定）

| 产物 | bytes | sha256 |
| --- | --- | --- |
| `run_records.jsonl`（288,000 行） | 221,974,782 | `f6e0d02ad7603605406858f216337b762324809ebee154842eba108ae7128ddf` |
| `run_summary.json` | 28,092,573 | `f5225e1e61d7c5944336b521b0f10d950b969669de808aef924b8953a0b876d2` |
| `ood_records.jsonl`（28,800 行） | 22,430,606 | `e8372903b82e5a2730bdc3b557d5d367d3ebe5d90b5d1d1d204be4415f2539ba` |
| `negative_control_records.jsonl`（28,800 行） | 23,153,628 | `117b46cbde79be6952723e52786c85cb8aec15f6587398fbe37f6f93b9d539a6` |
| `determinism/r1/run_records.jsonl` | 4,436,840 | `fba07081f39a40b6d7f98022b0c54d62cc12a06ef9c69a125d0913b6bc3ce618` |
| `determinism/r2/run_records.jsonl` | 4,436,840 | 同上 |
| `determinism/r3/run_records.jsonl` | 4,436,840 | 同上 |

---

## 12. 结论边界与 S4 建议

### 12.1 结论边界（可直接引用）

1. 本轮 S3 是**纯合成离线**开发集验证：3,780 runs / 362,880 次评估，`physical_call_count = 0`、`solver_processes_started = 0`，全部数值来自解析任务族，与 Concorde/CFD/VSPAERO 无关。
2. 两个预注册族（C1 可行命中率、C2 与参考解差距）共 4 个检验**全部 NULL**，Holm 校正后无任何拒绝；`overall_decision = NO_EVIDENCE`，`evidence_scope = DEVELOPMENT_VALIDATION_ONLY`（未触碰 holdout truth）。
3. 描述性上四臂差距在 1.3 个百分点以内（B64 hit 极差 0.0132 / B128 0.0084），远小于本轮可检效应；DE 在等预算下系统性落后 0.21–0.39，与前两阶段一致。
4. 成本维度**不可用**（`wall_s` 全 0、`adaptation_cost` 为预算计数、`cost_ratio = 1.0` 是预算比），任何“更省/更贵”的表述均不成立。
5. OOD 与 NC-15 均为**侧车描述性**数字，不进入推断；OOD 上 CON−OBJ 符号与主任务相反，量级同处 1e-2 噪声带。
6. 不得由本轮结果推断 S4 任何机制（ANIL/Meta-SGD/全二阶）的有效性；本轮也未评估 FULL_MAML（S2 已单独评估并同样 NO_EVIDENCE / SUPPORTED_HARM 边界见 S2 回执）。

### 12.2 交付前必须完成的门（本报告不构成验收）

| 门 | 状态 | 说明 |
| --- | --- | --- |
| A7 M6 包级复核 | v2 APPROVE_FOR_S3_RECEIPT；v3 delta 待回 | 3 minor 已在 v3 关闭（F-04/F-06/F-07），F-05 以披露处理 |
| A3 M6 隔离审计 | 进行中 | 提交前确认仅证据包 + docs、主库 main 未动、无 P5/P6 改动 |
| Lead 报告定稿 | 本文件 | 需在 A7 v3 delta 与 A3 审计后冻结 |
| Issue #7 S3 回执 | 未发布 | 仅 Lead 发布；不得写 APPROVED_FOR_NEXT_STAGE |
| S4 启动 | **NOT_APPROVED** | 仅数据合同阶段；需负责人书面批准 |

### 12.3 S4 建议（供负责人决策，不构成授权）

1. **先修三门禁缺陷再谈机制**：F-01 校验器缺少 `S3_EVIDENCE_ROOT_RELPATH` 前缀（fail-closed 失效）、F-02 聚合 sha 口径不一致、F-03 OOD 未接入图；三者均为**工程可修**问题，建议作为 S4 前置提交（纯离线、零物理）。
2. **S4 若继续，应先扩端点而非换算法**：本轮四臂 1.3pp 的差距落在噪声带，说明在当前任务族/预算下端点分辨率不足；建议 S4 预注册时明确最小可检效应（MDE）与所需任务数，否则重复“全 NULL”。
3. **成本维度必须先实现逐点计时**（`wall_s`），否则任何效率类假设无法检验；这也是 ANIL 审计（`cost_ratio_max = 0.75`）失败的直接原因。
4. **NC-15/OOD 需正式接入**：侧车可验证方向，但不能替代预注册端点；S4 应把 OOD 读取路径与 NC-15 计算写入分析器并有负控。
5. **不建议**在 S4 引入真实飞机/CFD 环节：本轮 `physical = 0` 是硬边界，且 S1–S3 三代均未出现超越 RANDOM 的可测优势，此时扩大物理规模无证据支撑。

---

## 附录 A：术语与判定口径

| 术语 | 定义 |
| --- | --- |
| `feasible_hit_rate` | 20 个任务上“在预算内找到至少一个可行解的比例”，任务级聚合 |
| `gap_to_reference` | 与冻结参考解的归一化差距，越小越好；`benefit_direction = negative` |
| C1 | 预注册对比 `S3-BO-FOMAML-CON` vs `S3-BO-FOMAML-OBJ`，终点 `feasible_hit_rate`，B64/B128 两个检验 |
| C2 | 同两臂，终点 `gap_to_reference`，B64/B128 两个检验 |
| NULL | CI 跨 0 且 Holm 校正后 p ≥ 0.05，判定无可测差异 |
| `n_eff` | 配对差非零的任务数；`n_zero` 为配对差恰为 0 的任务数 |
| `ANIL_INCONCLUSIVE` | ANIL 替代臂审计结论：命中率无可测差异（CI 跨 0） |
| `NO_EVIDENCE` | 聚合总判定：两个预注册族 4 个检验全部 NULL |
| `DEVELOPMENT_VALIDATION_ONLY` | 证据范围：meta_validation 开发集，未读 holdout truth |
| 侧车（sidecar） | 不改冻结分析器、独立复算的补充产物，仅描述性，不参与推断 |

## 附录 B：本报告与证据包的关系

- 本报告是**人读摘要**；事实与数值的权威来源是证据包（`PACKAGE_MANIFEST.json` 绑定的 77 个文件 + 7 个外置大文件）。
- 报告中的每个数值都能在包内定位：§4 → `analysis/s3_endpoint_tables.csv` + `analysis/aggregate.json:endpoint_rows`；§5 → `analysis/s3_holm_family.csv` + `aggregate.json:inference`；§6 → `analysis/s3_negative_controls.csv`；§9.2 → `analysis/ood_supplementary_*`；§2/§3 → `run/execution_report.json` + `run/determinism_check.json`。
- 报告由 Lead 撰写（A6 撰文任务因连续崩溃未产出，task-270 移交 Lead）；所有数值均由 Lead 从冻结产物直接读取，未做手工改写。
- 若报告与包内数据不一致，**以包内数据为准**，并按 §8 的披露流程记录差异。
