# D-12D-003 Round-1 A4 需求矩阵（intake）

- 生成：A4 / a4-issue-liaison，2026-11-02T10:26+08:00；任务 task-34 / D12D003-INTAKE-MATRIX
- 方式：只读 EXT 快照 + 只读本地 git/文件系统；零求解器、零 GitHub 写、零仓库写
- 交付：本文件、requirements.csv（35 条）、round_plan.md

## 0. 读取边界与实时状态

| 项 | 实测 | 来源 |
|---|---|---|
| Issue #4 | open；updated_at 2026-11-02T01:37:00Z；comments=9；最新为 D-12D-003（id 6566994749，created 2026-11-02T01:36:18Z） | issue4.json / comments4.json |
| #4 正文 | 顶部已加 D-12D-003 提示块（优先升级、最多两轮、P4-PLAN-ONLY 有限覆盖、新求解须另批预算） | issue4_body_now.md（14,677 B） |
| Issue #1 | open；updated_at 2026-11-02T01:36:57Z；comments=6（未逐段复核正文变更） | issue1.json |
| PR #3 | open、merged=false、draft=false；head=5dcb0bf09335fd6f73363d0280a667286d6d20f9；base=main；commits=55；changed_files=363；updated 2026-11-01T03:42:06Z；标题已改为 [P1-P3][12D] 几何—Mission—DOE 集成代码修复与超声速气动待验收 | pr3.json |
| 本地 git | D:/RCAIDE HEAD=5dcb0bf…（与 PR head 同）；分支 research/concorde-metaopt；porcelain 23 行历史未提交（A4 未触碰） | git rev-parse/log/status |
| 预算 | D-12D-002 的 23/23 已耗尽（VSPAERO 6/6、RCAIDE LF 4/4、SU2 6/6、Wave 7/7）；D-12D-003 不自动追加，当前无新物理预算获批 | comment_08 / comment_07 |

时序事实：D-12D-003 发布于 2026-11-02T01:36:18Z，晚于 PR head（2026-11-01）。因此 PR head 不含 D-12D-003 Round-1 代码/证据；Round-1 证据目前只应存在于 EXT（仓库外）。

## 1. 权威层级与旧指令状态

- 生效：Issue #4 正文 + 评论 D-12D-003（comment 6566994749，2026-11-02）+ Issue #1 治理/路线。
- D-12D-003 的「有限覆盖」只放宽 P4-PLAN-ONLY（阶段计划、离线 BO/DE 玩具测试、接口与数据合同）；对真实 Concorde 优化、物理 DOE/CFD、MAML/MetaBO 训练、把临时 LF 结果当真实性能的禁令仍然有效。
- D-12D-002 的 23 次授权与 #4 正文 approved_budget=0 均为历史；不得据此启动任何新求解。AWAITING_RUN_BUDGET 为无预算时的唯一合法状态，禁止写成「已测试仍失败」。
- P4-PLAN-ONLY 不等于 APPROVED_FOR_NEXT_STAGE；P1-P3 是否最终验收只由负责人决定，升级本身不得宣布 PASS。

## 2. 两轮结构与停止条件（详见 round_plan.md）

- Round-1（零求解）：OpenVSP 3.55.0 侧装与隔离（A3）、Python3.11 API 兼容与几何同源对照（A1）、旧 .vspaero/.history/.polar 与 DegenGeom 诊断（A1/A2）、WAVE-01..05 原始切片离线复算与病态诊断（A2）、A5 独立复核、L 版本化 run_id 归档。
- Round-2（预算门控）：仅在 A2 提交逐项预算（最大调用数、重试、墙钟、CPU、RAM、失败停止条件）且负责人明确批复后执行；否则保持 AWAITING_RUN_BUDGET。
- 最多两轮；两轮后仍未通过即停止循环（禁止无限重试/盲目加密）。
- 通过分支：A5 独立复核 → 逐项汇总 LF/面积律/SU2/Mission Gate → 负责人裁决 P1-P3。
- 失败分支：保留双版本与全部历史，标 LF_PROVISIONAL / BODY-CORR_NOT_VALIDATED，允许 P4-PLAN-ONLY；仍不得合并 main、不得关闭未通过 Gate。
- 停止/中止条件：破面/负体积；参考量不一致；Mach 错误；反复不收敛；力/阻力/波阻非物理；资源超限；预算耗尽；证据无法落盘；需改冻结合同（任一即 BLOCKED/FAILED 并上报 L）。

## 3. 禁止事项（A4 理解并用于矩阵校验）

1. 未被批复不得启动 VSPAERO/WaveDrag/SU2/RCAIDE 进程（含把自检伪装成免预算求解）。
2. 不新开 Issue；PR #3 保持 open、不合并 main；P4-P6 的真实优化/训练继续冻结（仅 P4-PLAN-ONLY 例外）。
3. 不把异常/未验证 LF 结果当优化真值；ΔD/CD 修正项未验证时保持 null，不得注入 Mission/目标。
4. 不把 15D/旧 23 次结果或 D-12D-002 证据冒充 D-12D-003 新证据；不伪造燃油标签。
5. AI 记忆/草稿/中间记录在仓库外；正式报告放 docs/reviews 或 docs/planning，原始数据放 ignored outputs。
6. 不得以「进入 P4 计划」反向关闭未通过 Gate 或宣称 P1-P3 通过。

## 4. 矩阵统计与当前进展

- 共 35 条（D3-01..D3-35）：Round-1 14 条、Round-2 门控 9 条、持续治理/P4/交付 12 条。
- 状态分布：RECORDED_IN_ISSUE 10、IN_PROGRESS（含 EXT）6、PARTIAL（EXT/既有证据）5、NOT_STARTED 8、AWAITING_RUN_BUDGET 3、AWAITING_A2_REQUEST 1、PENDING_OUTCOME 1、VERIFIED_READONLY 1。
- EXT 中观察到的 Round-1 进展（未经 A5/L 验收，不作为本矩阵证据）：
  - A3：facts.json + install_audit.md，OpenVSP 3.55.0 官方 zip（sha256 f1fde65f…，49,664,844 B，491 文件解压完整），Python API 报 3.55.0、VSPAERO 7.2.2；旧 3.26.1 与 SUAVE py3.9 worker 未动；回滚执行 NOT_RUN。
  - A1：48 个 API 兼容/几何对照产物（api_compat_matrix.md、api_compat_checks.csv、geometry_diff.json 等）。
  - A2：area_rule_cases.csv + run.log，36θ×200 复算（S-H 相对误差约 1e-6）与 72×800 条件数放大（1.895e6→1.227e8、D/q 44.4387 不收敛）复核正在进行。

## 5. 未决项（交 L/负责人）

1. Round-2 预算申请尚未提交（A2 未给出逐项调用/成本/停止条件）→ BUDGET 保持 AWAITING_RUN_BUDGET。
2. 旧 VSPAERO 零求解诊断（D3-12）尚无 EXT 证据 → NOT_STARTED，Round-1 关键缺口。
3. OpenVSP 3.55.0 回滚步骤仅静态评估，执行 NOT_RUN；A5 独立复核目录为空（D3-10 NOT_STARTED）。
4. L 尚未建立 D-12D-003 的版本化 run_id 与 canonical 归档（D3-29 NOT_STARTED），EXT 进展需 L 确认后转为正式证据。
5. P4-PLAN-ONLY 提纲可并行准备（D3-25），但启动范围需 L 明确；不得据此声称 P1-P3 通过。
6. PR #3 head 5dcb0bf 早于 D-12D-003；Round-1 增量如何推送/存档与单条回执时机由 L 决定。
7. 负责人需明确：AWAITING_RUN_BUDGET 是否作为当前正式 Gate 状态记录（不得默认 PASS/FAIL）。

## 6. 文件

- C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/d12d003/a4/requirements_matrix.md
- C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/d12d003/a4/requirements.csv
- C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/d12d003/a4/round_plan.md
