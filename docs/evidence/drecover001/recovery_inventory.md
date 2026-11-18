# D-RECOVER-001 R0 资产、损失与最小恢复矩阵（待独立验收）

日期：2026-11-17；基线：`4c51c7df34c9626999ef2e66e5a6c76a2b9c92e2`；分支：`recovery/drecover001-20261117`。

## 结论与门禁

**R0_PARTIAL_NOT_AUDITED / R1_SOFTWARE_IN_PROGRESS_NOT_AUDITED / NO_PHYSICAL_GO。新增 physical starts=0、internal cases=0。**

本报告是 Issue #12 要求的工程资产核对，不是 AI 记忆文件，也不是 A5 独立签署。R0 remaining_r0_work 第①项（batch2 之外的 raw/budget 来源分类）已在离线侧补做，见第 7 节；未发现额外可恢复 raw，F1R2/F2R2 仍为 RAW_LOST。A1–A4 要求实际 GPT-6-luna；A5 已由 Owner 授权 Lead 创建的 deepseek-flash 只读子智能体执行（m03569），verdict=`CHANGES_REQUIRED`，不是人类签名，Lead 未自签。异机备份要求已由 Owner 豁免（`WAIVER-OFFMACHINE-BACKUP-20261118`）。R1 软件侧已实施并复跑（230 项测试通过，见第 6 节），但 R1 门禁 RESTORED_CODE_BASELINE_PASS 未由 A5 签发；异机备份/恢复未验收，R2 与 #11 真实训练未启动。

## 1. 审计范围与字节结论

- [远端头清单](<.worktrees/drecover001-20261117/docs/evidence/drecover001/remote_refs.json>)来自 [GitHub heads API](https://api.github.com/repos/QingYangJin/RCAIDE_Supersonic/git/matching-refs/heads/)：20 heads、0 tags。git fetch 失败的原始错误为 `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)`；只读 API 回退已验证 heads 身份。
- [全部可达历史对象审计](<.worktrees/drecover001-20261117/docs/evidence/drecover001/reachable_history_audit.json>)覆盖这 20 个固定 SHA 的 **200 个可达提交、4,633 个对象、2,829 个唯一 blob、186,537,818 字节、2,760 条历史文件路径**。逐 blob 验 Git object identity、大小与 SHA256，非 shallow；不包含隐藏 refs、服务器不可达对象或从未推送的提交，不能宣称这些也不存在。
- [冻结清单核对](<.worktrees/drecover001-20261117/docs/evidence/drecover001/canonical_blob_audit.json>)：基线 2,109 文件 / 164,917,591 字节与原始 Git blob 一致；docs checksum 162 MATCH、2 MISSING、0 HASH_MISMATCH；M1A 12 slots 的 60/60 payload 大小和 SHA 一致。
- 导出必须关闭 core.autocrlf 转换；先前默认 archive 的 54 个 checksum 与 24 个 payload 差异全部是 CRLF，不是远端损坏。历史中文阶段报告原始 20,227B / SHA256 4a8200df7ab052252286084897e3aae8dc25a9a17372f0247e10b707f07d373f 完整保留。
- [历史资产矩阵](<.worktrees/drecover001-20261117/docs/evidence/drecover001/historical_asset_matrix.json>)含每条路径的全部 blob 版本。阶段索引 17 个摘要声明：8 找到身份、8 未找到、1 是短摘要不能证明身份；此为声明数，不是文件数。图表 source 55 个摘要声明中 13 找到、42 未找到。历史 verified=true/PASS 仅是历史叙述，不是当前验收。

## 2. 最小恢复集合与严重度

| 严重度 / 角色 | 当前材料 | 必须恢复的最小能力；验证前不得放行 |
|---|---|---|
| P0 / A1 | 旧几何源码在；指定修正版 13,654B / d20ee7adc38286c7da3ef3ea5aa5be8204596d491d6601b9a635b0ae5213dc56 不在可达 blob 中 | 绝对 XForm 模式写入+回读 fail-closed、垂尾非共面、12D active mask、固定机身、Sref、同升力 Di_N=qSrefCDi、CG/质量合同；新 freeze/replay 身份 |
| P0 / A2 | 普通 BO/DE/PSO 与旧执行器代码候选在，不代表 VSPAERO 适配正确；旧精确 runner 摘要未找到 | returned-feedback ask→evaluate→tell、null 失败、skip 语义、缓存去重、actual/charged/reserved/eval/cache 分账；反事实反馈分叉测试证明下一候选非预生成 |
| P0 / A3 | 历史 S1/S2/S3/meta_learning 与 tasks 源码保留；生产 T0 的六个指定完整摘要未找到 | TaskSpec/MetaDataset/MetaTrainer/AdaptationRunner/WarmStartSampler/production、真实标签 fail-closed、任务改变 deck/约束、固定任务 split 与 support/query 隔离；不能用旧 readiness 代替真实训练 |
| P0 / A4 | 历史绝对路径与备份报告在，当前异机原件没有证明 | 注入根目录/fresh-clone 软件回归、固定 exe SHA、CPU 双精度、可选 GPU；批准独立故障域存储并实际下载恢复 SHA/size，不能把 D: 另目录当异机 |
| P0 / A5 | 旧审查报告部分在、部分原始签署未找到；新审查未开始 | 独立实际 6-terra 签 RECOVERY_INVENTORY_PASS；R1 后再签 RESTORED_CODE_BASELINE_PASS + BACKUP_RESTORE_PASS |
| P1 / Lead | 报告、账本名文件与数字在；缺 F1R2/F2R2 原始运行目录 | 保留历史实际成本，不重建旧 raw 或旧 approval；后续只预注册必要新诊断，不自动全重跑 |

五条关键路径在所有 200 个可达树均不存在：production、task_spec、meta_dataset、geometry freeze、replay manifest。前六个相关 U1 文件中仅 **2 个精确字节身份保留**（设计空间 YAML 与 baseline 网格）；修正几何、bundle manifest、zero-physics audit、freeze 均未找到。

特别保留：baseline 网格 **225,414B / 16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84** 在 M1A 冻结路径存在，虽然旧 replay 路径不在。它是可复用的网格字节，不是完整 replay bundle、真实标签或新的物理验证。

## 3. source / report / raw / replayable / physics 分层

- SOURCE_CODE_PRESENT：矩阵列出 272 条研究 Python 源码路径；R1 软件回归已实施（见第 6 节），但 `RESTORED_CODE_BASELINE_PASS` 未签，仍不承诺真实 VSPAERO 可执行。实现复用 S1/S2/S3，不从零重写。
- REPORT_PRESENT：阶段报告、23 条历史图表路径、32 条 M0R 合同类路径；M0R/PENDING_REAL_LABELS 不是真实观测，图表中 NOT_COMPUTABLE 不改写成数值。
- RAW candidates：68 条 solver-output 扩展名路径全部属于更早的 d12d005-20261104T0430Z；其 [远端旧批报告](https://github.com/QingYangJin/RCAIDE_Supersonic/blob/aef2cb71e07aa28abfc28e34b14bf9dc1579c2e3/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/batch2/batch2_report.md) 明示主翼/矩形翼、单 AoA、VSPAERO_INTERNAL_ONLY、physical_validation=NOT_VALIDATED，不能替代修正 Concorde 垂尾/升力匹配 F1R2/F2R2。
- [旧 batch2 raw/账本逐项核对](<.worktrees/drecover001-20261117/docs/evidence/drecover001/historical_raw_reconciliation.json>)：16 行 PENDING/COMPLETED 对应 8 个唯一已完成事件，非 16 次启动；与旧账本 8 starts、0 retries、8 billable 一致。80 条输入/输出摘要声明中，8 条二进制 adb 的路径/大小/SHA 完全匹配、16 条 setup/vkey 的路径/SHA 匹配但原声明没有大小，56 条文本输出/网格原字节不匹配且均可由换行转换解释。**不做身份升级、不写回重建旧 raw**；旧 JSONL 的 8 个 Infinity token 单独披露，严格 JSON 输出未偷偷补标签。仍不证明完整 replay、物理适用性或异机备份。
- batch2 之外的 raw/budget 来源扩展审计（第 7 节）：25 个 budget/ledger 源、58 个 raw solver 输出、62 个 solver 日志、157 个输入 deck 全部完成 provenance 分类；无额外可恢复 raw。
- F1R2/F2R2 原始 raw solver 输出：**RAW_LOST**（损失账本显式条目）。未找到相关 run 命名路径；扩展 provenance 审查的 absent_raw_claims 明确列出 F1R2/F2R2；Owner 已确认无本地备份。原始文件完整身份与来源未恢复，不用于缓存，不以报告数值免费补入观测；更早 d12d005 的留存输出不能替代。
- 历史真实训练 checkpoint：**UNKNOWN**。唯一扩展名候选是无关教程 pickle，不是 MAML checkpoint；没有真实训练 checkpoint 的已验证恢复证明。当前 fixture checkpoint 仅为 SOFTWARE_FIXTURE_TRAINING_ONLY，不是历史真实 checkpoint。
- REPLAYABLE：NOT_ESTABLISHED；PHYSICS_VALIDATED：无新认定；cache admission：NONE；可免重跑的真实科学标签：**本轮认定 0 条**。这不否认旧运行曾发生。

## 4. 新诊断清单（仅草案，不授权）

R1 两门通过后，由 A5/Lead 为新 batch 冻结最小矩阵：绝对坐标/垂尾与 Sref 审计、升力 bracket 与 Di_N 独立复算、重复性、有限密度/尾迹/迎角与必要单变量响应，然后至少一条真正反馈驱动普通 BO 或 DE 轨迹。不要自动重跑所有旧批，不复用旧 token/窗口，不恢复旧 6/12 总上限；每批仍须有限 starts/时间/重试/并发/硬件/科学停止条件，备份或物理异常即停。

历史 Issue #10 actual=65/455、charged=70/490 保持原样，仅 REPORT_PRESENT，非当前 raw 复验。fuel_burn_kg=null；EXTERNAL_PHYSICS_SUPPORTED=NOT_VALIDATED。

## 5. 验证与交接

[审计工具测试](<.worktrees/drecover001-20261117/docs/evidence/drecover001/test_recovery_audit.py>)共 23 项通过，为纯内存离线 fixture：检查 SHA256 大小写等价、相对路径、换行不混充身份、大小/完整摘要、嵌套来源、历史覆盖计数与不自动接纳物理标签。不是 R1 pytest、不是训练、不是独立 A5。

后续入口：[恢复清单](<.worktrees/drecover001-20261117/docs/evidence/drecover001/recovery_inventory.json>)、[下一轮必要条件](<.worktrees/drecover001-20261117/docs/evidence/drecover001/needed_for_next_run.json>)。仍需实际指定模型子智能体、独立 A5 与批准外部存储；本地资产尚未提交/推送，不能把本报告称远端可恢复交付。

## 6. R1 软件侧进展与 MAML 就绪度（2026-11-17 续）

- R1 合同与训练管线：TaskSpec/MetaDataset/MetaTrainer/AdaptationRunner/WarmStartSampler/ValidationSelector 已实现并 fail-closed；离线 M2 rehearsal 用 6 个真实任务物理身份 + 合成标签跑通 FOMAML、池化预训练、16D 条件特征预训练、K=0/4/10 评估与验证早停；回执 `run_id=DRECOVER001-M2-REHEARSAL-20261117T160233Z`，`scope=OFFLINE_REHEARSAL_ONLY`，physical=0。重复运行校验（repeat `run_id=DRECOVER001-M2-REHEARSAL-20261117T160500Z`）：code/参数 SHA/evaluation/training/task identity/labels/dataset/config 全等，checkpoint payload 除内嵌 run_id 外完全相同。详见 [m2_offline_rehearsal_receipt.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/m2_offline_rehearsal_receipt.json>)、[m2_rehearsal_repeat_check.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/m2_rehearsal_repeat_check.json>)、[maml_readiness_20261117.md](<.worktrees/drecover001-20261117/docs/evidence/drecover001/maml_readiness_20261117.md>)。
- A4 可注入根目录：`RCAIDE_A1_ROOT` / `RCAIDE_S3_ROOT` / `RCAIDE_DNEXT_ROOT` / `RCAIDE_DNEXT_PARENT`，缺失即失败；详见 [a4_path_injection_20261117.md](<.worktrees/drecover001-20261117/docs/evidence/drecover001/a4_path_injection_20261117.md>)。
- M1 批次控制路径（仅离线软件结构验证）：`m1_batch.py` 实现批次授权/计划/执行/分账/停止，拒绝无 `physical_go`、A5/Lead 占位符及复用旧门禁；18 项 fixture（6 个真实任务身份 × 3 设计）physical=0、simulated=18、internal=126、charged=18；回执标记 `STRUCTURAL_SOFTWARE_FIXTURE_NOT_A_REAL_GO`，不是 solver 证据。本轮修复结算异常 fail-closed：`settle`/`register_evaluation` 抛错时停止未结算预留并把行标为 `failed`/`ACCOUNTING_VIOLATION`，`summary.accounting_resolved=false`、未结算预留进入 unresolved；M1 套件 20 项（含 2 项新增回归）。账本 `accounting_resolved` 同时收紧为要求 `starts_reserved==0`：open reservation 不再被误报为已对账，`assert_conserved` 拒绝签通过；新增账本回归 1 项。另修复 `TaskSpec` 数值表示 fail-open：`mach=1` 与 `1.0`、`altitude=0.0` 与 `-0.0` 曾产生不同 `physics_sha256`，现统一转 float、拒绝非有限值、signed zero 规范为 `0.0`，新增 2 项回归（同物理条件唯一身份、数值 clone 拒绝重复物理），套件 229 项。本轮另修复 evaluator 异常时 `_stop_reservation` 自身抛错的 fail-open：原实现会直接抛出、不留结构化批次结果；现捕获 stop 失败，状态改为 `STOPPED_ACCOUNTING_VIOLATION`，行 `failure_kind=ACCOUNTING_VIOLATION`，`starts_reserved` 保持未结清；并新增 1 项回归。MetaDataset 同时收紧 failed observation：`di_n` 之外 `cl`/`cdi` 也必须为空，新增 1 项回归。详见 [m1_batch_software_rehearsal_receipt.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/m1_batch_software_rehearsal_receipt.json>)。
- 软件 preflight：`run_id=DRECOVER001-SOFTWARE-20261118T102149Z`，247 tests / 0 failed / 0 error / 0 skipped；preflight 自身记录 `a5_independent_review=NOT_PERFORMED`（运行前固定字段）、`physical_go=NOT_ISSUED`、`backup_restore=NOT_ESTABLISHED`。
- A5 审查（本轮实际执行）：deepseek-flash 只读子智能体，verdict=`CHANGES_REQUIRED`；major 两项（同机恢复缺显式标签、packet 备份门禁状态与 Owner 豁免冲突）已修复；verdict 与 16 步 transcript 见 `a5_review_verdict.json` / `a5_review_transcript.json`。不是人类签署，不授权物理。详见 [recovery_preflight_receipt.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/recovery_preflight_receipt.json>)。
- 可移植本机恢复包：`run_local_restore.py` 现在把 `git status` 中全部变更/未跟踪文件叠加到 baseline archive，重建 bundle `80cd0697fdd29a72328820e4044222e785346cbd43f7367d12495f127273c716`（58,418,755B）；在同机新目录恢复 2,241 文件（79 overlay）并通过 247 项测试，重训 checkpoint 与 holdout 精确一致；bundle 内嵌 manifest 的 2,241 项路径/SHA256/字节逐项复验通过（manifest SHA `380f66f493b9b393fa67090db63e9b4c64ee87687edef9f440c72baa554a30ec`）；恢复后先把被 preflight 覆盖的 98 个证据文件恢复为 bundle 原字节，再连续两轮运行 R0 provenance/M1 batch verifier、readiness 与 A5 packet 校验（`evidence_verifiers` 两项均 ok），均 `bundle_manifest_verified=true`、`evidence_chain_verified=true`、`readiness=RECOVERY_READINESS_GATES_CLOSED_EXPECTED`（7 CLOSED+1 CLEAN+1 WAIVED）、`packet_check_problems=[]`。仍为 `PASS_NOT_REMOTE_BACKUP`、`off_machine_backup=false`、`backup_label=SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP`、`owner_waiver=WAIVER-OFFMACHINE-BACKUP-20261118`，Owner 已豁免异机故障域但同机恢复不构成备份。bundle 内嵌文档快照早于最终 SHA 更新，权威 SHA 以本文件与外部 receipt 为准。另外修正 `git archive` 在 `core.autocrlf=true` 下把 LF blob 改写为 CRLF 的可移植性 bug（曾使 r0_provenance_extension.json 330,839B/b553857c 变为 339,808B/49211a4a，证据链校验失败）；现以 `git -c core.autocrlf=false archive` 构建 baseline。
- U1 参考绑定缺口：8项检查6项失败（4个期望冻结工件在所有本地树均不存在：`bundle_manifest.json` 1b16f572…、`PRE-01R/geometry.vspgeom` 16da482a…、`zero_physics_audit_12d.json` 7a90b977…、`design_space_freeze.json` fe7e48eb…；另有2项SHA因R1修复变化：`aircraft/openvsp_geometry.py`实际4f64d4c0…(16,299B)≠期望d20ee7ad…(13,654B)，`design_space_12d_lifting_surfaces.yaml`实际ebca2b7b…(11,099B)≠期望8b29d1e3…(10,846B)）。U1-DESIGN-HASHES与U1-OLD-GEOMETRY-NOT-USED通过；旧冻结ID已作废，不得静默重冻，须在新R2门禁下以新ID重发。完整 checks 见 [a1_u1_reference_gap.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/a1_u1_reference_gap.json>)。
- 仍未实现/未验收：真实 raw 准入（协议已实现但零真实样本）、task→geometry/mesh 完整绑定、A5 对新 commit 复审、正式条件特征预训练接真实标签、验证早停接真实路径、真实反馈 BO 生产入口、质量/CG/AC 与力轴 VSPAERO 读回、异机（独立故障域）备份恢复、Git 可复核 commit。

## 7. R0 来源扩展审计（batch2 之外的 raw/budget，2026-11-17 续，离线）

- 产物：[r0_provenance_extension.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/r0_provenance_extension.json>)（330,839B / SHA256 `b553857c5ce986e9fbfd7f6fa6de37d7aca42af9ade61075db6e17e87c524c37`），脚本 [audit_provenance_extension.py](<.worktrees/drecover001-20261117/docs/evidence/drecover001/audit_provenance_extension.py>)（22,450B / `63eb6e46…`），摘要 [r0_provenance_extension_20261117.md](<.worktrees/drecover001-20261117/docs/evidence/drecover001/r0_provenance_extension_20261117.md>)。
- 分类：budget/ledger 25（RAW_PRESENT 3 均为计划/记账文件，REMOTE_PRESENT 22）；raw solver 输出 58 全 REMOTE_PRESENT；solver 日志 62 全 REMOTE_PRESENT；输入 deck 157 全 REMOTE_PRESENT；缺失 raw 声明 2（F1R2/F2R2）为 RAW_LOST。**没有发现额外可恢复的新 raw。**
- 账本复算：d12d004 4 行 4 starts/2 retries/4 billable；d12d005 v1 4 starts/0 retries/4 billable；v1b 2/0/2；batch2 8/0/8（与既有 reconciliation 一致）。四对交叉核对 authoritative flag=0；唯一启发式分歧是 d12d004 的 budget 计数器声称 0 starts 而同 run ledger 记 4 starts/2 retries/4 billable，已标记未裁决。
- 摘要声明：89 条 claim；关键路径 5 条在 200 个可达树中全缺失；图表 source 55 条仅 13 找到；另有 3 条外部摘要（agent state 目录内 A5 签署/隔离/authorization）不在可达 Git 历史，不能当作已恢复签署。
- 自检：`verify_r0_provenance_extension.py` 重算 328 项检查全部通过（`R0_PROVENANCE_EXTENSION_EVIDENCE_INTERNALLY_CONSISTENT`，0 failures），只从存档字节与历史 blob 复核，不启动求解器；输出不含时间戳，重复运行字节一致（SHA256 `73b99833c7f86c5ef317dc21ca83a3ae0537170384309c6d1dbf07af7dbcb3b5`），A5 复核重跑不会改变证据身份。
- 本地对象库检查：`git fsck --full --unreachable --no-reflogs` 返回 0 个 unreachable 对象（24 refs、0 tags、4,633 in-pack、0 loose）；仅 `git count-objects -v` 提示 `garbage: 1`，对应空目录 `D:/RCAIDE/.git/worktrees/drecover001-20261117/refs`，不是 dangling 对象。因此 5 条缺失关键路径不能从本地 dangling Git 对象恢复；本检查只覆盖本地对象库，不等于远端复核。证据 [r0_local_object_store_audit.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/r0_local_object_store_audit.json>)（SHA256 `adf23138966cb959c941771b3122abbd6972f897afdb04d211bd3b5e0ec1f603`）。
- 边界：physical=0、internal=0、physics_validated=false、cache admission=NONE、admitted_scientific_labels=0；本项完成不改变 R0_PARTIAL_NOT_AUDITED，也未替代独立 A5 审查。

## 8. 恢复门禁就绪矩阵（聚合器，离线，不构成 A5 签署）

- 聚合器 [assess_recovery_readiness.py](<.worktrees/drecover001-20261117/docs/evidence/drecover001/assess_recovery_readiness.py>) 只读汇总 R0/R1/M1/M2/备份/A5/真实准入/变更清单证据，产物 [recovery_readiness.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/recovery_readiness.json>) 与 [recovery_readiness.md](<.worktrees/drecover001-20261117/docs/evidence/drecover001/recovery_readiness.md>)。
- 当前结果：`status=RECOVERY_READINESS_GATES_CLOSED_EXPECTED`；9 个 gate 中 7 个 `CLOSED`（预期外部签批缺失）、1 个 `CLEAN`（变更清单）、1 个 `WAIVED`（Owner 豁免异机备份）；`violations=0`、`missing_evidence=0`、`blockers=9`。
- 矩阵明确：`physical_solver_starts_actual=0`、`internal_solver_cases_actual=0`、`real_meta_training_executed=false`、`admitted_real_labels=0`；`CLOSED` 是“预期未签”而非 PASS，不能替代 A5 的 `RECOVERY_INVENTORY_PASS` / `RESTORED_CODE_BASELINE_PASS` / `BACKUP_RESTORE_PASS`。
- 变更清单由 [build_change_manifest.py](<.worktrees/drecover001-20261117/docs/evidence/drecover001/build_change_manifest.py>) 从实际工作树重建；清单自身排除 `__pycache__`、`.pyc` 与聚合器输出。
- A5 审查包：`build_a5_review_packet.py` 从现有回执聚合 36 项证据（逐文件 SHA256，含 Owner 豁免与 A5 verdict/transcript），生成 `a5_review_packet.json` / `.md`；只读、无人类签名、不授予物理 GO。A5 结论记录为 deepseek-flash 子智能体的 `CHANGES_REQUIRED`，两项 major 已修复。
- A5 复核步骤只列非破坏性命令，不要求重跑 preflight；完整 pytest 只能在恢复副本里重跑，以免新 run_id 覆盖 packet 记录的 receipt/trace/checkpoint。按 packet 顺序实际执行一遍后，全部 evidence 的 SHA256 不变（changed=0）。
- 数据完整性：聚合器对 `needed_for_next_run.json` / `recovery_inventory.json` 做 JSON 解析校验。本轮发现 `needed_for_next_run.json` 中 R1 的 `required` 文本曾被一次历史编辑截断成非法 JSON（尾部丢失），已恢复为合法 JSON，并在该文件 `integrity_note` 中把丢失尾部标为 UNKNOWN、不得当作证据；新增 1 项回归测试防止再次发生。

## 9. 2026-11-18 修订后的 R0 新基线、A1 几何冻结、A2 反馈与 A3 真实准入（零物理）

- **R0 新基线**：[new_baseline_manifest.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/new_baseline_manifest.json>)（schema `drecover001.new_baseline_manifest.v1`）固定 `base_commit=01c9274801474c113a2c488e375d451bcd0297c3`、`base_tree=8b2be0a4b122dc1ef2ec9a5b4d01cf113f216861`、16 个关键源码 SHA256；历史数据策略 `RAW_LOST_ARCHIVED`（停止继续搜寻 F1R2/F2R2/旧 200 提交/旧几何字节），旧几何 `d20ee7ad…` 与旧 checkpoint 明确 `NOT_REUSABLE`；新实验必须使用新 run_id/batch_id/geometry_sha/task_family_sha/RealAdmissionManifest，来源仅允许 `REGENERATED_FROM_SPEC` 或 `NEW_PHYSICAL_RUN`。
- **A1 几何冻结 v2**：[geometry_freeze_v2.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/geometry_freeze_v2.json>)（354,374B / SHA256 `401bc6b6c605eafe416bd4b0e925d106b93673b2e4d2c21f1d21e688d7e62bf1`）与 [geometry_freeze_v2_verification.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/geometry_freeze_v2_verification.json>)（SHA256 `ca1c052b0d3093223706676bcb70cd81bc9627f94ecd3d3c3fbb13e3df763aa4`，101 项检查 / 0 失败、两次运行字节一致）；`status=GEOMETRY_FREEZE_V2_ISSUED_ZERO_PHYSICAL`、`freeze_id=GBFREEZE2-5f2bb12fe8b1dc68`、`geometry_contract_sha256=5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15`；合同值 Sref 358.25 m²、Cref 18.489893 m、Bref 25.604638 m、q 20483.940233430174 Pa、L_ref 1,333,704.4 N、CL_target 0.18174391742、`lift_tolerance_rel=1e-3`；模型边界 24/24、真实 OpenVSP 边界 24/24；导出 [vsp3](<.worktrees/drecover001-20261117/docs/evidence/drecover001/geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.vsp3>) 301,252B / `e471be01…`、[stl](<.worktrees/drecover001-20261117/docs/evidence/drecover001/geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.stl>) 1,245,302B / `bae4e17c…`、[step](<.worktrees/drecover001-20261117/docs/evidence/drecover001/geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.step>) 630,057B / `3b0d9636…`；VSP3 回读三部件面积/位置/机身长度通过。开放项：质量/CG/AC 为 `PROVISIONAL_NOT_FROZEN`（总重 184,880 kg、OEW 78,700 kg、cg_x 28.287395、全局翼 AC 30.821978、静稳定裕度 0.137079），`XCG_M=16.821978259514246` 是主翼局部 AC，不可与全局值混用；力轴符号须 R2 VSPAERO 读回验证。
- **A2 反馈闭环（软件）**：[a2_feedback_rehearsal.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/a2_feedback_rehearsal.json>)（SHA256 `b8f5c6950d99be20c982bead819a552046b501746abbbd25ecc02df926f83436`）由 [run_a2_feedback_rehearsal.py](<.worktrees/drecover001-20261117/docs/evidence/drecover001/run_a2_feedback_rehearsal.py>) 生成，走真实 `ArmHarness`/GP-BO 路径；6 次评价、physical=0、simulated=6，best_valid_D_i_N 51494.25737678772；交换前两次 D_i_N 后前两个 proposal 相同、第三个不同（因果反馈）；失败设计行 objective 为 null。`scope=SOFTWARE_FEEDBACK_REHEARSAL_ONLY_NOT_PHYSICAL_EVIDENCE`，不是物理闭环。
- **A3 真实准入协议**：[real_admission.py](<.worktrees/drecover001-20261117/research/concorde_metaopt/dreal001/meta/real_admission.py>) 实现 `RealAdmissionManifest`、`AdmissionCertificate`、`admit_real_manifest`；逐文件校验 mesh/deck/polar/history 路径、字节和 SHA256，拒绝绝对路径/`..`/symlink 越界，绑定 task/design/geometry/evaluator/独立 audit；成功路径调用 `verify_artifact_bundle` 并从原始 polar 同升力行取 `D_i_N=q·Sref·CDi`，失败路径签发 status=failed 且无 label；证书只能由模块私有 `_ISSUER` 签发并复核 D_i_N 恒等式；`MetaDataset.require_real_admission()` 只在每行都有匹配证书时放行，无证书仍抛原 `REAL_ADMISSION_NOT_IMPLEMENTED`。17 项 fixture 测试覆盖成功/缺失/篡改/路径穿越/失败求解/合成数据拒绝等；当前 `admitted_scientific_labels=0`，测试字节均为 synthetic，不构成真实准入。
- 边界：`physical_solver_starts_actual=0`、`internal_solver_cases_actual=0`、`physics_validated=false`、`cache_admission=NONE`、`admitted_scientific_labels=0`；A1 只是几何/参考合同，A2 只是软件反馈，A3 只是协议与 fixtures，均不授权 R2 物理批次。