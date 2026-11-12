# D-REAL-001 A1 任务回执（task-14 接管；原 r1-geometry 产物）

## 0. 身份与范围

- 角色：a1-aviation-f（F 线，同时接管原 A1/r1-geometry 的 D-REAL-001 P0 收尾）
- 任务：共享任务 task-14（task-6 已 reassign）
- 工作树：D:\RCAIDE\dnext001\wt-real-a1-geometry-solver
- 分支：research/dreal001-a1-geometry-solver（基线 683a868，接管时 HEAD 37235fd）
- 未 push、未合并 main、未改 A4/A5 树、未启动真实 solver
- physical_call_count（本轮新增物理求解启动）= 0

## 1. 本地提交

- 264d768 — P0 F-ENV-02/03：evaluations 行级重构、run_closeout.py、evidence_manifest.read_retention、13 个测试
- 2505108 — 证据重生成：evaluations/summary/manifest/SHA + run_config + batch_summary + correction_001 + 两个 .log 入库
- a3a5770 — P1 预注册 v1.1（24x49、23 starts/175 internal）+ P0 闭合说明
- 本次回执提交 — 本文件

接管前已有的四批提交：3b00272（真求解接口）、afcc8ff（P0 冻结件）、b5dcbbc（ENV_SMOKE 证据）、37235fd（P1 v1）。

## 2. 新增/修改文件

代码（research/concorde_metaopt/dreal001/geometry/）：

- evaluation_reserialize.py：重写为"一唯一流动条件一行"（治理 §6 schema），补齐 record_id / batch_id / cache_key / alpha 标量 / source_kind / labels / 约束 / 证据分层；旧聚合记录移入 evaluation_summary.json。
- run_closeout.py（新增）：run_config.json（F-ENV-03）、batch_summary.json（批次收口 + 实际/批准预算对照 + F-ENV-01/05/06 披露）、corrections/correction_001.json（§12.7 只披露旧 SHA，不覆盖）。
- evidence_manifest.py：新增 read_retention()（append-only 全量读取），CLI 用全量 retention 生成 manifest。
- p0_finalize.py：流水线改为 reference declaration → reserialize → retention（记录后删大件）→ read_retention → write_closeout → write_manifest。

测试（research/concorde_metaopt/tests/test_dreal001_r1/）：

- test_dreal001_r1_reserialize.py：重写为 7 个用例（临时目录副本，不触碰冻结证据）。
- test_dreal001_r1_closeout.py（新增）：6 个用例（run_config / batch_summary / correction / retention / manifest 覆盖）。

证据与文档：

- P0 run 目录重生成：evaluations.jsonl（5 行，d1307abd…）、evaluation_summary.json（ee64455d…）、run_config.json（afb9a971…）、batch_summary.json（0322d634…）、corrections/correction_001.json、data_manifest.json（30 文件 / 1,436,141 B）、SHA256SUMS.txt（30 行）、reference_injection_declaration.json；两个 .log 用 git add -f 入库。
- P1_PREREGISTRATION_v1.md 升到 v1.1（P1-02c 24x49；expected 23 starts / 175 internal；max 26/196；P1-06 覆盖说明；§11 变更记录）。
- docs/planning/dreal001_p0_closure_20261110.md（新增）：五条签署条件逐项对照、F-ENV-01/05/06 披露、复现命令。

## 3. 实际运行的测试与结果

    Set-Location D:\RCAIDE\dnext001\wt-real-a1-geometry-solver
    & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests -q -k "dreal001 or geometry" -p no:cacheprovider

结果：89 passed（6.5–6.7 s，1 个既有 xlim 警告）。接管时为 76 passed → 新增 13 个用例全绿（reserialize 7 + closeout 6）。没有真实求解调用。

## 4. F-ENV 闭合情况

- F-ENV-01：披露（不修复）。pre-v3 的 -fs 列表致 1 启动 = 32 内部子案；写入 run_config.legacy_cli_list、batch_summary.disclosures、evaluation_summary.accounting；P1 起禁用。
- F-ENV-02：已修复。5 行 × 标量 alpha，字段齐全；行级 starts=0 + attempt 级=1，防求和放大 5 倍。
- F-ENV-03：已修复。manifest/SHA 覆盖 30 个跟踪产物；新增 run_config/batch_summary；.log 入库。
- F-ENV-04：已实现待复核。TaskSpec RefFlag=0 / Sref 重算 / W01 敏感性契约；需 A5 独立勾选。
- F-ENV-05：披露。case_result.json 36 个 Infinity 不改写；下游 null + allow_nan=False。
- F-ENV-06：披露。plan.status 陈旧字段不改写（保 plan_sha256 57a14fdc… 不漂移）。
- F-ENV-07：已修复。P1 v1.1 补 24x49、internal 双上限 175/196、P1-06 覆盖说明。

## 5. 未完成项与风险

1. P0_PASS 未签：已向 A5 提交申请；A5 需复核 F-ENV-04 与 F-ENV-02 新格式（新 evaluations SHA 已变，审计基线仍是旧 201d3ce0…，已在 correction_001 中说明）。
2. P1 plan.json / approval.json 未创建：按治理 §4 由 Lead 在批窗口时生成，必须原样写 23/26 starts 与 175/196 internal；本回执不提前落盘以免造成"已批准"误读。
3. P1 真实启动数为 0：本轮无任何真实 VSPAERO 启动；P1 执行仍阻塞于 P0_PASS + Lead 窗口 token。
4. 残余风险：ENV_SMOKE internal 计数来自 <base>.adb.cases（pre-v3 台账无该字段），属派生值；P1 起必须由 ledger end 行给出。测试对 run 目录使用临时副本，但重跑 p0_finalize / reserialize_run 会重写派生件（幂等但产生新 SHA），审计应在提交后冻结 SHA。

## 6. 声明

- 本轮 physical_call_count = 0：未启动 VSPAERO / OpenVSP 求解器，未写 A4/A5 树，未 push。
- 三层结论：本轮仅支撑 SOLVER_LOOP_VERIFIED（工具链与台账可审计），INTERNAL_AERO_OPTIMIZATION_GAIN = NOT_CLAIMED、EXTERNAL_PHYSICS_SUPPORTED = NOT_CLAIMED、fuel_burn_kg = null。
- 门禁：LF-M2.02 = NOT_VALIDATED、BODY-CORR = BLOCKED、HF-M2.02 = PARTIAL，均未变化。
