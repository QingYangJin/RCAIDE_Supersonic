# A5 T0 Gate — G-T0-READY-02（T0_CODE_READINESS）

- gate_id: **G-T0-READY-02**
- 签发: a5-review（独立非作者复核），2026-11-13T04:35:00Z
- verdict: **T0_CODE_READINESS_PASS**
- ready_for_real_meta_training: **false**
- 范围: 仅 Issue #10 T0 阶段的代码/合同/单测/冒烟/重放/隔离/可复算证据；**不判** #11 REAL_META_TRAINING_ADMISSION，不授权训练/物理/执行/发布。

## 1. 结论

T0_CODE_READINESS 范围内 C01–C50 已按 L-28 口径重核并新增 C51（T0-1/T0-4 同源）。A2 C32 生产入口 fail-closed 已实现并由 A5 独立复跑（20 passed；直接 probe 拒绝且不建 run dir）；A3 task-48 已将 T0-1 从 8 个亚声速占位重建为 T0-4 的 18 任务族，applicability 全量 DEFERRED_TO_M1_REAL_COLLECTION，T0-4 admission 全量 PENDING_M0_BY_DESIGN；A5 独立 pytest 合计 **112 passed / 0 failed**；T0-1/T0-4 的 family、18 task fingerprint/id、split 11/4/3 逐元素同源。

因此本 gate 只给出 **T0_CODE_READINESS_PASS**。它不是 READY_FOR_REAL_META_TRAINING，不得引用为真实任务族、真实标签、真实训练或物理可用性证据。

## 2. 计数

| total | PASS | PASS_WITH_DISCLOSURE | BLOCKED | NOT_APPLICABLE_BY_DESIGN | FAIL |
|---:|---:|---:|---:|---:|---:|
| 51 | 42 | 8 | 0 | 1 | 0 |

## 3. 关键检查

- **C01 T0-1 TaskSpec/TaskFamily 合同与非法输入** — PASS_WITH_DISCLOSURE
  - 证据: task_spec.py d7267738/81,219; T0-1 contract fb85c9cd/167,540; 18 tasks; readiness T0_1_CONTRACT_READY_APPLICABILITY_DEFERRED_TO_M1; contract_ready=true; real_training_ready=false
  - 说明: 合同/非法输入均有测试；status 是 CONTRACT_READY，不是 READY_FOR_REAL_META_TRAINING；applicability 全 DEFERRED，不得记 PASS
- **C07 split 按 task 身份且互斥** — PASS
  - 证据: T0-1 split 11/4/3 seed42; T0-4 split 11/4/3 seed42; task_split_manifest c516e177/14,939; tests
  - 说明: 按 task 身份切分且集合互斥；T0-1/合同 split 与 T0-4 manifest 逐元素相等
- **C08 T0-1/T0-4 合同与配置单测** — PASS
  - 证据: A5 独立 pytest: A3 tests_contracts 31 + tests_configs 32 = 63 passed; A2 T0-3 29 + C32 20 = 49 passed; 合计 112 passed/0 failed
  - 说明: 覆盖非法/缺字段/漂移/DEFERRED 不可声明 PASS/生产入口拒绝
- **C17 meta_dataset 单测** — PASS
  - 证据: A2 T0-3 29 passed; A3 合同/配置 63 passed
  - 说明: A5 独立 pytest 合计 112 passed
- **C26 固定 seed 重放字节一致** — PASS
  - 证据: A2 replay_a/b core 4763a339/9ab5362d; A4 compare 12/12 PASS; A5 independent core 9ab5362d
  - 说明: A5 独立重跑 core_sha 与证据逐字节同
- **C29 端到端 smoke 18/18** — PASS
  - 证据: A2 smoke cc3527c9/130,897; A5 independent smoke 9da222f2/130,699; 18/18 checks
  - 说明: A5 独立重跑，18/18 true，physical=0
- **C31 无生产 mock 入口** — PASS
  - 证据: A2 boundary_scan 14 files forbidden_total=0 PASS; production.py 仅 imports stdlib/meta; C32 21 scenarios
  - 说明: 未发现生产 mock 入口；生产入口无 fixture fallback
- **C32 生产训练入口 fail-closed** — PASS
  - 证据: production.py 21d3e807/27,663; production/__init__ 2a642b42/3,236; test 8fe82de7/15,654; 20 passed; C32 evidence dc08949b/86,641（21 scenarios, failed=0, 16 REFUSED）; A5 独立 probe: refused=true, missing_roles=[evaluator,solver,ledger], run_dir_created=false
  - 说明: 生产入口要求显式真实 provider/ledger/authorization/train_config；缺任一即 ProductionEntryRefused 且不建 run dir/不写 ledger/不启 solver；C32 已修
- **C36 internal=7×starts 策略** — NOT_APPLICABLE_BY_DESIGN
  - 证据: T0-3 零物理: starts=0 -> internal=0; 7× 策略未被非零 starts 触发
  - 说明: T0 阶段无物理 starts；该策略应在 #11 真实 M0/M1 实验中验证，不能用 T0 合成 smoke 冒充
- **C42 T0-4 18 candidate family** — PASS
  - 证据: T0-4 YAML de1732a5/139,212; Mach{1.8,2.02,2.2}×h{15000,18288,20000}×CL{0.17,0.19}; 18 tasks
  - 说明: 18 candidate tasks；admission 全部 PENDING_M0_BY_DESIGN，不再是 PENDING_F1_F2
- **C46 T0-4 first batch DRAFT** — PASS
  - 证据: T0-4 first_real_training_batch 2942e5db/9,625; status DRAFT_PENDING_M0_GO; token/approval null; gates 4 条; no F1/F2
  - 说明: M1 planned 98/686 hard 102/714；非授权；M1 只选 6 tasks（train 4 + val 2，无 test）
- **C48 仓库状态与冻结字节** — PASS
  - 证据: A2 HEAD 9a9e294; A3 HEAD 5832017; A4 HEAD 1c29d0a; T0 路径 disk==HEAD/git diff exit 0; A3 仅无关 stats/p2a_v2.py modified（D-T0-04）
  - 说明: T0 交付字节冻结；旧 T0-1/T0-4 备份在 t0_revision_history_20261113_r1，旧 SUMS 10/10 OK
- **C49 A5 独立复跑** — PASS
  - 证据: A5 pytest 112 passed（A2 49 + A3 63）; A5 independent C32 refusal probe; A5 independent smoke 18/18 core 9ab5362d; A4 verifier 24/24; self-test 12/12; compare 12/12
  - 说明: A5 未启动 solver；仅合成 fixture；physical_call_count=0
- **C51 T0-1 与 T0-4 同源一致** — PASS
  - 证据: T0-1 contract fb85c9cd vs T0-4 YAML de1732a5: family ada424cc 逐字节重算一致; 18 task fingerprints/ids 全等; split 11/4/3 数组全等; readiness {DEFERRED:18}; admission 18/18 PENDING_M0_BY_DESIGN; old 8-task 合同 ec0a73e3 仅在历史目录
  - 说明: T0-1 已由 T0-4 生成器重建，亚声速 8-task 占位不再在权威族；DEFERRED 不得声明 PASS；admission 留给 #11 M0

## 4. C32 生产入口 fail-closed（硬门禁）

A2 production.py（21d3e807/27,663）提供唯一生产入口；open_production_training_entry 要求显式真实 evaluator/solver/ledger/authorization/train_config，缺任一即 ProductionEntryRefused，且不创建 run dir、不写 checkpoint/ledger、不启动 solver。C32 证据 21 scenarios：16 REFUSED、1 ACCEPTED_TEST_ONLY、1 BLOCKED_TEST_ONLY_TRAIN，failed=0；A5 独立 pytest 20 passed。A5 直接 probe（全参数缺失）得到 refused=true、TRAIN_CONFIG_REQUIRED、missing_roles=[evaluator,solver,ledger]、run_dir_created=false。

这证明**代码级** fail-closed；不证明真实生产组件已具备、也不证明真实训练可启动。

## 5. T0-1 / T0-4 同源（C51）

- T0-1 合同 fb85c9cd/167,540：18 tasks，family_sha256=ada424cc，split 11/4/3 seed42，readiness=T0_1_CONTRACT_READY_APPLICABILITY_DEFERRED_TO_M1，contract_ready=true，real_training_ready=false。
- T0-4 YAML de1732a5/139,212：18 tasks，family_sha256=ada424cc，split_preview 11/4/3 seed42，18/18 admission_status=PENDING_M0_BY_DESIGN，每任务 applicability DEFERRED、三项 NOT_CHECKED。
- A5 独立 import 断言：from_t0_4_candidate_yaml 与 t0_4_candidate_family 均重算 ada424cc；18 task fingerprints/ids 全等；build_split 与 T0-4 split manifest 逐元素相等（11/4/3、互斥、fingerprint 全等）；YAML split map 与 manifest 全等。
- 旧 8-task 亚声速 T0-1 合同 ec0a73e3/66,349 已移出权威族，保留在 t0_revision_history_20261113_r1（旧 SUMS 10/10 OK）。
- **DEFERRED 不得声明 PASS**：本案 applicability 全部是 DEFERRED_TO_M1_REAL_COLLECTION；任何把 T0_1_CONTRACT_READY 写成 real training ready 的表述都属越界。

## 6. 披露（摘要）

- **D-T0-12**: 旧 G-T0-READY（commit 3b8abc6；json 792dfcad/28,840；md 925bd10b/12,409；checklist 2f656f1e/16,495）保留为历史记录，不被本 gate 改写；本 gate 依据 L-28 与 G-T0-READY-ADD-01 重新按 T0_CODE_READINESS 判。
- **D-T0-13**: 本 gate 只判 T0_CODE_READINESS，不判 REAL_META_TRAINING_ADMISSION；T0-1 18/18 applicability 仍 DEFERRED_TO_M1_REAL_COLLECTION，T0-4 18/18 admission 仍 PENDING_M0_BY_DESIGN。
- **D-T0-14**: C32 为生产入口代码级 fail-closed 证据：21 scenarios 中 16 REFUSED、1 ACCEPTED_TEST_ONLY、1 BLOCKED_TEST_ONLY_TRAIN；没有任何真实生产 provider 被接受，也没有执行训练。
- **D-T0-15**: A5 独立 C32 probe 以 evaluator/solver/ledger/authorization/train_config 全缺调用生产入口，得到 refused=true、TRAIN_CONFIG_REQUIRED、missing_roles=[evaluator,solver,ledger]、run_dir_created=false；这不等于真实生产组件已具备。
- **D-T0-16**: A4 T0 evidence status_snapshot 是 2026-11-12T18:57:00Z 旧快照（gate.current_status=NOT_READY、code_artifacts_present=0/4、a5_review=PENDING）；A4 为 support-only，A5 已独立复核其 SUMS/verifier/replay，但未把旧快照当作本 gate 的当前状态。
- **D-T0-17**: 旧 T0-1 8-task 亚声速占位合同 ec0a73e3/66,349 已移出权威族，保留在 t0_revision_history_20261113_r1（旧 SUMS 10/10 OK）；权威 T0-1 为 18-task T0-4 同源族。
- **D-T0-18**: T0-4 first_real_training_batch_DRAFT 的 M1 只选 6 tasks（meta_train 4 + meta_val 2），test_tasks_in_M1=0；18 task family 的 meta_test 3 tasks 在 M1 不被训练使用。这是 #11 输入约束，不是本 gate 的训练结果。
- **D-T0-19**: A3 工作树仍有与 T0 无关的 research/concorde_metaopt/dreal001/stats/p2a_v2.py modified 和未跟踪 probes；T0 路径 disk==HEAD，未改 T0 字节（沿用 D-T0-04）。
- **D-T0-20**: A4 HEAD=1c29d0a；A4 T0 evidence commit=05743958；其 snapshot 未更新至 A2 C32/A3 task-48 之后，建议刷新但不阻断。
- **D-T0-21**: 本 gate 证据读取时点 2026-11-13T04:35Z；A2 HEAD=9a9e294、A3 HEAD=5832017、A4 HEAD=1c29d0a、Lead L-28 HEAD=de727ff；若交付分支在签发后移动，需以本 gate 绑定字节为准。
- **D-T0-22**: T0-1/T0-4 采用单 seed（42）与固定 split；本 gate 不提供性能、增益、winner 或显著性证据；T0 不执行真实训练。
- **D-T0-23**: fuel_burn_kg=null；EXTERNAL_PHYSICS=NOT_VALIDATED；跨族 pooling 禁止；本 gate 不授权 #10 完整汇报发布或 #11 启动。

## 7. #11 前置动作（不是本 gate 的阻断项）

- **RA-11-01**: #11 启动前必须另立 G-T0-ADMISSION-01，核验 18 个任务的真实 applicability（solver domain/lift target reachable/cross-task response）及 required evidence schema，全部不能是 DEFERRED/NOT_CHECKED。
- **RA-11-02**: #11 M0 必须冻结任务族/有限首批预算/标签生成协议，并由 Lead 另签 authorization+window token；不得复用本 gate 或 R10 token。
- **RA-11-03**: M1 真实采集/训练前必须 preflight 2/2 与 per-task real applicability 全部通过；失败 ABORT 无 retry。
- **RA-11-04**: T0-4 admission 当前全为 PENDING_M0_BY_DESIGN，不得在 #11 前被引用为 admitted；T0-1 applicability 当前全 DEFERRED，不得在 #10 汇报中记 PASS。
- **RA-11-05**: A4 T0 evidence status snapshot 仍为 2026-11-12T18:57:00Z / NOT_READY（stale）；建议 A4 在 #10 汇报前刷新，但不构成本 gate 的 T0_CODE_READINESS 阻断。

## 8. 权威依据与边界

- L-28: de727ff27254eb4e719c377c1c9b81152d77083c（md 02585f62/5,695；json 244270ab/2,244）
- G-T0-READY-ADD-01: 7703bce7ce8794bfc21cb10bf2b957b121c55a78（md 791ffd5a/8,778；json d2ecb16a/19,868）
- 旧 G-T0-READY: commit 3b8abc6，json 792dfcad/28,840，md 925bd10b/12,409，保留不改
- A2 HEAD 9a9e294；A3 HEAD 5832017；A4 HEAD 1c29d0a；A5 physical_call_count=0，未启动 solver，未建 run dir/ledger，未 push。
- fuel_burn_kg=null；EXTERNAL_PHYSICS=NOT_VALIDATED；禁止跨族 pooling；不宣布 winner/显著性/增益。

**签署**: a5-review，2026-11-13T04:35:00Z，A5_T0_CODE_READINESS_SIGNED。本 gate 不是执行、训练、物理或发布授权。
