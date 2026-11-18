# R0 来源扩展审计：batch2 之外的 raw 与 budget（离线，待独立验收）

日期：2026-11-17；分支：`recovery/drecover001-20261117`；基线：`4c51c7df34c9626999ef2e66e5a6c76a2b9c92e2`。

**结论：R0 remaining_r0_work 第①项（batch2 之外的 raw/budget 来源 provenance 分类）已在离线侧完成；未发现任何额外的、可恢复的新 raw。F1R2/F2R2 原始 raw 仍为 RAW_LOST。physical starts=0、internal cases=0。本报告不是 A5 独立审查，不改变 R0_PARTIAL_NOT_AUDITED。**

## 1. 方法与边界

- 输入：[reachable_history_audit.json](reachable_history_audit.json)（20 个远端固定 head、200 个可达提交、4,633 个对象、2,829 个唯一 blob、186,537,818 字节、2,760 条历史路径）与 [historical_asset_matrix.json](historical_asset_matrix.json)。
- 工具：[audit_provenance_extension.py](audit_provenance_extension.py)（22,450B / SHA256 `63eb6e468ce40de035b15737b5f69d63d07f0acae369c2b76b4b1e41c0e7bb6e`）。逐对象用 `git cat-file blob` 重读，并与审计记录核对 bytes 与 SHA256，全部一致才计入；未联网、未启动 OpenVSP/VSPAERO、未写回任何历史 raw。
- 自检：[verify_r0_provenance_extension.py](verify_r0_provenance_extension.py) 从存档字节重算 328 项检查（schema/零物理/逐源 blob 身份与本地字节/六分类计数/缺失 claim/交叉核对/摘要声明/外部引用），结果 `R0_PROVENANCE_EXTENSION_EVIDENCE_INTERNALLY_CONSISTENT`、0 failures，见 [r0_provenance_extension_verification.json](r0_provenance_extension_verification.json)。
- 产物：[r0_provenance_extension.json](r0_provenance_extension.json)（330,839B / SHA256 `b553857c5ce986e9fbfd7f6fa6de37d7aca42af9ade61075db6e17e87c524c37`，schema `drecover001.r0_provenance_extension.v1`）。
- 分类规则：只有本地工作树字节与历史 blob **完全一致**（或仅行尾不同且已明确披露）才升为 `RAW_PRESENT`；归一化不用于分类；历史存在而本地缺失记 `REMOTE_PRESENT`；历史声明但 200 个可达树都不存在记 `RAW_LOST`。所有“路径/SHA 匹配”仅是 provenance 身份，不构成物理适用性、完整 replay 或异机备份证明。

## 2. 覆盖与分类结果

| 类别 | 数量 | 分类结果 |
|---|---|---|
| budget/ledger 数据源 | 25 | RAW_PRESENT 3，REMOTE_PRESENT 22 |
| raw solver 输出（.polar/.history/.adb，optimization_runs 下） | 58 | REMOTE_PRESENT 58 |
| solver 日志（.log） | 62 | REMOTE_PRESENT 62 |
| 输入 deck（.vspaero/.vspgeom/.vkey/.vsp3） | 157 | REMOTE_PRESENT 157 |
| 缺失 raw 声明 | 2 | RAW_LOST 2：F1R2、F2R2（history_path_matches=[]） |

- 三个 `RAW_PRESENT` 均为本地精确字节：`docs/evidence/dreal001/figs/tables/table1_r1r10_attempt_ledger.csv`、`docs/evidence/dreal001/m0r_20261113/M0R_BUDGET_LEDGER.json`、`docs/evidence/dreal001/m0r_20261113/pre_draft/M0R_BUDGET_LEDGER_PREDRAFT.json`。三者都是**计划/记账**文件，不是新的求解器观测。
- 58 个 raw solver 输出全部只存在于历史，本地缺失；未因报告中的数值而制造新 raw。
- 20 组 bundle/results 同字节镜像；跨 case 的 SHA 碰撞 0。

## 3. 账本复算与交叉核对

| ledger | 行结构 | 完成 starts | retries | billable | 备注 |
|---|---|---|---|---|---|
| d12d004 `evidence/v1/ledger/solver_ledger.jsonl` | 4 行 alternate schema（无 record_type） | 4 | 2 | 4 | returncodes {1:1, None:2, 0:1}；outcomes FAILED / ABORTED_WRAPPER_DEADLINE / TIMEOUT / VERIFY_FAILED |
| d12d005 `evidence/v1/ledger.jsonl` | 9 行 = 4 PENDING + 4 COMPLETED + 1 AMEND | 4 | 0 | 4 | pair_issues=[] |
| d12d005 `evidence/v1b/ledger.jsonl` | 4 行 = 2 PENDING + 2 COMPLETED | 2 | 0 | 2 | labels VSPAERO_INTERNAL_ONLY；2 个 legacy Infinity token 原样保留 |
| d12d005 `evidence/batch2/ledger.jsonl` | 16 行 = 8 PENDING + 8 COMPLETED | 8 | 0 | 8 | 与既有 reconciliation 一致 |

交叉核对 4 对：batch2 与同目录 budget 8/8 一致、v1b 与同目录 budget 2/2 一致、v1 与其 config approval 账本 4/4 一致（后两对为启发式配对，均无 flag）。authoritative flag=0。

唯一的启发式分歧（只标记、不裁决）：d12d004 的 `config/actual_solver_budget.json` 计数器声称 `starts_used=0 / retries_used=0 / billable_events=0`（status=UNUSED_AT_ZERO_STARTS、no_solver_started=true），而同一 run 的 `solver_ledger.jsonl` 记录 4 attempts / 4 starts / 2 retries / 4 billable。flag 为 COUNTERS_CLAIM_ZERO_STARTS_BUT_LEDGER_HAS_ATTEMPTS、RETRY_COUNT_DISAGREES_WITH_LEDGER、BILLABLE_COUNT_DISAGREES_WITH_LEDGER。该分歧不改变历史成本叙述，也不产生任何可复用科学标签。

## 4. 摘要声明与外部引用

- claim_groups 共 89 条：阶段索引 17 条（8 找到字节身份 / 8 不可达 / 1 短摘要不构成身份）；额外必需摘要 6 条全部不可达；5 条关键路径（production、task_spec、meta_dataset、geometry freeze、replay manifest）在 200 个可达树中全部缺失；U1 依赖 6 条（2 找到 / 4 缺失）；图表 source 55 条（13 找到 / 42 缺失）。
- 外部引用 4 条，3 条摘要不在可达 Git 历史中，均指向仓库外的 agent state 目录（`C:\Users\pc\AppData\Local\RCAIDE_Supersonic_agent_state`）：`a5/a0_rev3_review/verdict.txt`（78e9933b…）、`a3/a0_rev3_isolation_980fffb.md`（bcee12cc…）、batch2 authorization（fd02dd89…）。第 4 条 v1b parent `approval_and_budget_ledger.json`（65f22fa0…）的摘要存在于可达历史。**这 3 条外部摘要无法在本仓库内复核，不能当作已恢复签署。**
- 绝对路径引用 121 条（OTHER 88 / AGENT_STATE_DIR 32 / OPENVSP_EXECUTABLE_PATH 1，后者为 `D:\OpenVSP-3.55.0\...`），印证历史运行依赖机器本地绝对路径，属于 R1 A4 路径可重绑定要解决的同一类问题。
- v1b 账本含 10 个 legacy `Infinity` token，保持字节原样，不转写成标签、不重写历史文件。

## 5. 对 R0/R1 状态的含义

- R0 `remaining_r0_work` 第①项在离线侧完成，但**清单仍不能签 RECOVERY_INVENTORY_PASS**：独立 6-terra A5 审查未开始，且本报告本身不是独立签署。
- F1R2/F2R2 原始 raw 确认丢失；R2 不得用旧报告数值补入观测，也不得把重生成文件冒充旧 raw。
- 历史账本只作为 provenance 记录保留；它们不是新进程启动见证，不授予缓存准入（cache admission=NONE），不改变 `admitted_scientific_labels=0`。

## 6. 边界声明

`physical_solver_starts_actual=0`、`internal_solver_cases_actual=0`、`physics_validated=false`、`cache_admission=NONE`、`admitted_scientific_labels=0`、`independent_review=NOT_STARTED`。本报告与 JSON 均未启动任何求解器，也未进行 git commit/push。
