# P4 路线A S1 执行计划（v1.7）

> 状态：v1.7（2026-11-06，A4 task-224 同步 L、A2 readiness v4f、A3 v4f 与 A5 phase4c）；供 Lead、A1、A2、A3、A5 审阅。本计划**不构成物理授权**，也不构成 S1 formal 放行；21,000 次 formal 只有在 A5 final re-verdict 给出 APPROVE_FOR_S1_RUN 且 Lead 书面授权（显式绑定 S0-7 路径、SHA256SUMS、run_id、15 分片过滤、3.5h 硬上限、失败停跑）后才可启动。
> 依据：Issue #7 §2 S1/S4、§3–§4；docs/planning/p4_route_a_stage_improvement_plan_20261105.md（commit a331639e）；合同 v1.6；统计计划 v1.5；R-V4-01..06（v4 修订）、R-V4-07（v4b 并行）、R-V4-08（v4c phase3）、R-V4-09（v4d S0-5）、R-V4-10（v4e S0-6）、R-V4-11（v4f，37 行，随 commit J 入库）；A5 phase4b 终审（CHANGES_REQUESTED，1B/0M/4m，报告 sha256 def5c059…，findings sha256 ffb5dcf0…）；A5 phase4c 终审（CHANGES_REQUESTED，0B/1M/2m，仅治理/文档项，报告 sha256 db8e3106…，findings sha256 f66e2b9a…，verdict sha256 5fe0afc5…）；A2 readiness v4f（COMPLETE，md 11,863 B，sha256 77db3e24…）；A3 v4f 审计（PASS 40/40，sha256 ef694d55…；L addendum sha d1c597a9…；m04 addendum sha ae5cf638…）；Lead commit J 后全量测试日志 `<EXT>/p4-route-a/lead/commitJ_full_tests.log`（8,956 B，sha256 6f584635…；Ran 949 tests in 442.006s / OK (skipped=1)）。
> 工作树：v1.7 修订于本仓库 @ 8f34e91（commit L，父 K；branch research/p4-route-a-s1；worktree clean）。
> v1.6 变更（历史记录，已被 v1.7 取代）：S0-6→S0-7 确证包（J 生成、K 入库；9/9、determinism PASS、final_verify 15/15）、R-V4-11 确证包 code_sha 绝对 fail-closed（FC-20）与 phase4b 1B/0M/4m 关闭、949 tests 基线、A2 readiness v4f 未定稿/A3/A5 phase4c 未开始、15 片窗口按 A2 v4e B128 实测改为 2.58–3.01h（首片核对）。
> v1.7 变更：A2 readiness v4f COMPLETE（7/7 gate，READY_PENDING_LEAD_AUTHORIZATION，runs_executed=0）；A3 v4f PASS（40/40）+ L addendum + m04 登记 addendum（TE-000/001 受控读取披露）；A5 phase4c CHANGES_REQUESTED（0B/1M/2m，仅治理项），m04 经 A3 登记后由 A4 标 CLOSED，待 A5 final re-verdict；15 片窗口按 A2 v4f 实测改为 2.55–2.97h；final_verify 15/15 声明为包外证据（不补写冻结包）。
> 约束：0 物理；不启动求解器；不读真实 holdout；不修改旧冻结 run；不合并 main；仅 Lead 写 GitHub；A4 本轮不 commit/push。

## 1. 目标与范围

S1 检验：把目标任务上已评价的 K 个支持样本（特征+目标/约束标签）接入适应内循环，再用适应后代理为正式约束 BO 选初始点，能否在相同 B 下改善主终点。三阶段结论：

1. K-shot 闭环是否按预期实现且公平（K 次支持评价计入 B，五臂预算一致，无 query 标签泄漏）；
2. 是否在预注册主终点上相对普通 BO/Pretrain/零样本 FOMAML/DE 有一致收益（或如实报告无收益）；
3. 是否值得进入 S2 完整二阶 MAML（不看单点最优，按统计门禁与成本判断）。

范围外：真实飞机 BO/DE、真实航空元训练、路线B采集策略、真实 SU2/Mission/WaveDrag、新 VSPAERO 求解、RCAIDE 回退、P5/P6；旧 A 类剩余 6 次 CLOSED 不结转。

## 2. 输入与前置

### 2.1 历史只读

S0-2 包（8 payload）仅历史复现；S0-3、S0-4、S0-5、S0-6 包均转历史只读，其中 S0-6/S0-5/S0-4 在 freeze_summary/README 标 SUPERSEDED_LEGACY。旧 M2/M5/M6 结果与旧任务族不得当新盲测，不得改标、不得改写旧工件。

### 2.2 S0-7 确证冻结包（唯一有效）

| 项 | 值 |
|---|---|
| run_id | p4ra-s0-7-freeze-20261106T024200Z |
| 生成/入库 | commit J 004156c 干净 detached worktree 生成；commit K 8118234 入库 |
| 目录 | research/concorde_metaopt/optimization_runs/p4ra-s0-7-freeze-20261106T024200Z/ |
| 文件 | 9 payload + README.md + SHA256SUMS.txt；SHA256SUMS.txt sha256=59aa81cd…；sha256sum 9/9 |
| git_sha / code_sha | 004156c232f31a450f7446c3b280772de47423df / 7304d32e524b0e1e28b0e83e7a2ed7822ce88fc14963ca4d769098841e6201ed |
| 不变量 | family_version p4ra-family-v4；family_id F-QE-feasible-v3；family_fingerprint a1f9462c…；split_hash cd597d01…；五 split 60/20/20/10/10（120 任务）；holdout_seed 20261106；radius_base 0.64；prereg_digest 3155de15…；analysis_plan_digest 5222af0d…；confirmatory_eligible=true（三处）；physical_call_count=0 |
| 确定性 | 两独立进程 6 个内容载荷逐字节一致；determinism_report schema p4ra-s0-7-determinism-report-1、status=PASS、rerun_count=2、independent_processes=true；final_verify sha256 ecee6971… 15/15 PASS；README sha256 936f94ac… |
| 与 S0-6 差异 | 仅 run_id/git_sha/code_sha/时间戳/frozen+prereg 字节/determinism 证据；tasks.json/meta_task_split.json 逐字节相同；S0-6 标 SUPERSEDED_LEGACY 只读 |

### 2.3 配套文档

- 数据合同 v1.6（本版同步 S0-7/J/K/L、R-V4-11、A5 phase4b/phase4c 关闭映射与 FC-20、A2/A3 v4f）；
- 统计计划 v1.5（pair 标签字典序规范化、确证包禁止 delta，Holm 族定义不变；A2 v4f 实测窗口）；
- 需求矩阵 v1.7；
- R-V4-01..06 文件、R-V4-07、R-V4-08、R-V4-09、R-V4-10、R-V4-11 裁定文件。

### 2.4 当前实现事实

- s1_runner.py/s1_analysis.py 已在 commit G 修复 pair 标签与 code_sha 门禁；commit J 进一步修复 A5 phase4b S1R4b-B01（确证包 code_sha 漂移禁止 `--allow-code-delta` 逃生，s1_runner.py:281-307；测试 +2 至 93 模块 tests）；
- K-shot 闭环（m5_arms.py 支持集传入）已实现并测试；S1-07 状态以矩阵 v1.7 为准；
- 949 tests OK(skipped=1)，442.006s（Lead commit J 后全量日志 8,956 B，sha256 6f584635…；A1 自测 442.712s，sha256 261da8ce…）；这不是 A5 phase4b/phase4c verdict；
- A2 readiness v4f 已 COMPLETE（READY_PENDING_LEAD_AUTHORIZATION；md 11,863 B，sha256 77db3e24…；json 45,235 B，sha256 b883e691…；七项 gate 全 PASS；runs_executed=0；formal 未启动；physical=0）；A3 审计 J/K/S0-7 已 PASS（sha256 ef694d55…，40/40），L addendum（sha256 d1c597a9…）与 m04 登记 addendum（sha256 ae5cf638…，8/8 PASS（H01–H08））已交付；A5 phase4c 已给 CHANGES_REQUESTED（0B/1M/2m，仅治理/文档项），待 final re-verdict；
- S1_RUN=NOT_APPROVED；formal 21,000 NOT_RUN；15 分片未启动。

## 3. 实现模块与所有权

### 3.1 运行与运行器（A1）

`research/concorde_metaopt/meta_learning/s1_runner.py`、`m5_arms.py`：五个 arm（Random-BO、Pretrain-Kshot-BO、FOMAML-ZeroShot-BO、FOMAML-Kshot-BO、DE），B∈{64,128}，K∈{0,1,3,5}。正式网格 15 分片×1,400 run = 21,000 run（9,000/6,000/6,000）。分片窗口按 A2 readiness v4f B128×K=3 实测（5 runs/1 任务/K=3，measured/predicted=0.8226，20% 内）为每片 2.1216h、窗口 2.55–2.97h、峰值 311.492 MB/进程（15 进程约 4.56 GiB）（A2 readiness v4f 披露）；首片启动前以实测复核，3.5h 为硬上限，不得把窗口写成未经实测的确定值。merge 子命令按 canonical 子集校验（serial/merged 仅 cost.total_wall_s 与 record_digest 可不同）。

### 3.2 分析与图（A1/A2）

`s1_analysis.py`、`s1_figures.py`：九个端点、C1–C5、Wilcoxon/bootstrap/Holm、七图、pair 级可辨识性；pair 标签按 R-V4-10-01 归一。

### 3.3 文档与回执（A4）

合同、执行计划、统计计划、需求矩阵、Issue #7 回执草稿；只读事实，0 物理，不发布。

### 3.4 审计与独立复审（A3/A5）

A3 保护分支/worktree/旧证据并审计 commit H；A5 phase4b 复核 B01/M01 修复、M02/M03/M04 与 merge delta，独立跑测试并给 verdict；每阶段 A5 APPROVE 才放行下一阶段。

## 4. run_records.jsonl 字段

`run_id`、`run_group_id`、family 五字段（family_version/family_id/family_fingerprint/split_hash/holdout_seed）、`split`、`grid_stratum`、`task_id`、`arm`、`budget_B`、`K`、`initial_designs`、`bo_calls`、`meta_seed`、`opt_seed`、`identifiability`、`billable_evals`、`endpoint_values`、`fallback_values`、`cost`、`physics`、`status`、`failure_reason`、`history_digest`、`record_digest`。字段缺失/空值/fail-closed 规则同合同 §6。

## 5. 端点与聚合

九个端点：best_feasible_value、gap_to_reference、first_feasible_eval_index、feasible_hit_rate、final_best_objective、constraint_violation_min、bo_initial_best、bo_initial_feasible、n_feasible。聚合按任务（任务为一级统计单位，不把随机种子当任务）；无可行解写 null，不插值、不补零；端点表含定义、方向、分母与缺失原因。

## 6. 统计合同

1. 预注册/冻结校验先于任何比较；统计计划 digest 与 analysis_plan_digest 一致。
2. C1–C4：K-shot 闭环 arm 对普通 BO、Pretrain、零样本 FOMAML、DE。
3. C5-B：结构不可辨识时只做结构性诊断，不做 benefit/harm/Holm 推断。
4. Wilcoxon 符号秩（配对）+ bootstrap CI（10,000 次，固定 seed）；多重比较用 Holm，唯一族键 `(primary_endpoint, budget_B, K)`；族内比较由 4 降为 3 时 p_adj 重算。
5. pair 标签字典序规范化（R-V4-10-01）：两臂名排序后单竖线连接；analysis 对键 split/sort 归一，非法格式 fail-closed，归一后计数须与实际 pairwise 严格相等。
6. 主终点 = best_feasible_value；显著性阈值、效应量方向、最小可检出效应按统计计划 v1.3。
7. 判定规则：只有预注册主终点+预算+族内校正后显著才可写“改善”；否则写“未观察到显著改善”或“不确定”。
8. 输出 summary.json/CSV/七图 PNG/中文报告；每个数字可追溯到 run_records 或端点表。
9. C5-B 与 pair-level 结论必须与 identifiability_report 一致。
10. 失败/缺失/部分运行必须如实统计，不得只报成功子集。
11. 任何发现泄漏/预算漏计/旧工件改写即停跑并 fail-closed。

## 7. 确定性、负控与泄漏

- 确定性：200 runs×3 固定种子；K=0 复现旧行为；历史记录不可改。
- 负控：pair 标签非法/顺序不一致→fail-closed；确证包 code_sha 漂移绝对 fail-closed（真实 S0-5/S0-6 对 load/grid/run/merge + `--allow-code-delta` 均 DRIFT 且无产物；legacy S0-2 正控放行并记录 frozen/current 双 sha、`evaluation_mode=exploratory`）；merge canonical 子集比较；标签打乱负控。
- 泄漏：不得读 query 标签、解析最优点、把代理预测写入真实 observations；支持样本特征+目标/约束标签可入内循环，且 K 次必须计入 B。
- 物理隔离：所有 evaluator 为合成/离线；physical_call_count=0 断言；不得启动 RCAIDE Mission/SU2/VSPAERO。
- readiness 隔离（R-V4-05）与正式工件重建（R-V4-03）继续有效。

## 8. 七类中文图

1) 五臂主终点分布（含 null）；2) gap_to_reference；3) first_feasible_eval_index；4) feasible_hit_rate；5) K-shot 成本/收益；6) 配对差与 CI；7) 可辨识性/结构性诊断。图题图注中文，数据来源与过滤规则写图注。

## 9. 验收

1. 949 tests OK(skipped=1)（Lead commit J 后全量 442.006s，A1 自测 442.712s；本计划不把它当 A5 phase4b/phase4c verdict）。
2. 40 组预算公平单测：五臂 billable=B，K 计入 B，K=0 复现旧行为。
3. 九端点键完整、null 规则正确。
4. 统计计划可执行：C1–C4、C5-B、Holm 族大小、bootstrap 固定 seed。
5. 冻结包=S0-7（p4ra-s0-7-freeze-20261106T024200Z），SHA256SUMS.txt sha256=59aa81cd…、9/9、determinism PASS、final_verify 15/15；S0-6 标 SUPERSEDED_LEGACY 只读。
6. 确定性 200×3 与负控通过。
7. physical_call_count=0，无 solver 启动。
8. 文档 0 绝对路径、中文、无 AI 记忆污染。
9. formal 21,000 网格=9,000/6,000/6,000，15 分片×1,400；窗口 2.55–2.97h（A2 v4f readiness 实测：每片 2.1216h，峰值 311.492 MB/进程、15 进程约 4.56 GiB；首片核对，3.5h 硬上限）。
10. v4 holdout 隔离：S0-6 五 split，确证用 TE 20 任务；旧 S0-4/S0-5 不进入 formal。
11. pair 标签/计数严格一致；C5-B 不进 Holm。
12. 正式工件/readiness 可重建且与冻结包身份一致。
13. R-V4-10-03 真实 runner→analysis e2e：串行与 merge 两条链路 exit 0 且 structural 计数一致。
14. 确证包 code_sha 绝对 fail-closed 负控通过（S0-5/S0-6 四命令 DRIFT 且无产物；legacy 正控放行记录双 sha）；launcher 六项预检通过（含 --dry-run 报告），且绑定 S0-7。
15. merge canonical 子集逐字节一致（仅 cost.total_wall_s 与 record_digest 可不同）。

## 10. 阶段门（v4f）

1. A5 phase4b（B01 确证包 delta 逃生）→ A1 修复 → Lead 全量测试 → commit J（已完成；949 tests）。
2. A1 在 J 干净 detached worktree 两独立进程生成 S0-7（已完成）。
3. Lead 入库 commit K（已完成；SHA256SUMS 9/9、determinism PASS、final_verify 15/15）。
4. A2 readiness v4f：真实 runner + B128 资源复核，绑定 S0-7（已完成；7/7 gate，READY_PENDING_LEAD_AUTHORIZATION，runs_executed=0）。
5. A4 文档 v1.6/v1.7/v1.5（本轮；合同 v1.6/执行计划 v1.7/统计计划 v1.5/矩阵 v1.7）。
6. A3 审计 commit J/K、S0-7 与工作树隔离（已完成；40/40 PASS，addendum L 与 m04 登记 addendum 已交付）。
7. A5 phase4c：B01 负控复现（S0-5/S0-6 四命令 DRIFT 且无产物、S0-2 正控双 sha）、949 tests、真实 runner→analysis e2e/merge delta；已给 CHANGES_REQUESTED（0B/1M/2m，仅治理/文档项）。
7b. A3 m04 登记 addendum + A4 m04 CLOSED → A5 final re-verdict（不改代码/包；本版 A4 已标 CLOSED，尚待 A5 确认）。
8. 仅当 A5 `APPROVE_FOR_S1_RUN` + Lead 书面授权（S0-7 路径、SHA256SUMS 59aa81cd…、run_id、15 片过滤、3.5h 硬上限、失败停跑）→ 启动 21,000 formal。
9. 15 分片+merge 完成 → A5/A3 复核 → A4 中文回执（经 Lead 发布）。

S1 formal 冻结且 physical=0；任何真实求解需另批预算；RCAIDE/SU2/VSPAERO/WaveDrag LOCKED。

## 11. 版本记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-11-05 | A4 | 初稿：S1 目标、模块、run_records、端点、统计、验收、阶段门 |
| v1.1 | 2026-11-05 | A4 | 按 R-V4-02/-03 补 S0-2 输入、readiness 隔离、正式工件重建 |
| v1.2 | 2026-11-05 | A4 | 按 D-S0-2 与 A5 S0 意见补预算公平、端点语义、10 任务族 |
| v1.3 | 2026-11-06 | A4 | 按 R-V4-07 补 15 分片/merge 合同与 S1_RUN 门禁 |
| v1.4 | 2026-11-06 | A4 | 按 R-V4-08/A5 phase3 同步 S0-4、code_sha、867 tests |
| v1.5 | 2026-11-06 | A4（task-224） | 同步 S0-6/G/H、R-V4-10、947 tests、A2 v4e 进行中、A5 phase4b 未开始；15 片窗口待 B128 实测；验收增真实 e2e/launcher/canonical merge；未 commit/push，0 物理 |
| v1.6 | 2026-11-06 | A4（task-224） | 按 R-V4-11 与 A5 phase4b（1B/0M/4m）：S0-7（J 生成、K 入库）、确证包 code_sha 绝对 fail-closed（FC-20）、949 tests、phase4c 放行链、15 片窗口 2.58–3.01h（首片核对）、A2 readiness v4f/A3/A5 phase4c 状态；未 commit/push，0 物理 |
| v1.7 | 2026-11-06 | A4（task-224） | 按 L/A2 readiness v4f/A3 v4f/A5 phase4c：A2 COMPLETE（77db3e24…）、A3 PASS（ef694d55…）+ addenda（d1c597a9…/ae5cf638…）、A5 CHANGES_REQUESTED（0B/1M/2m，治理项）、m04 CLOSED 待 A5 确认、窗口 2.55–2.97h、final_verify 包外声明；未 commit/push，0 物理 |
