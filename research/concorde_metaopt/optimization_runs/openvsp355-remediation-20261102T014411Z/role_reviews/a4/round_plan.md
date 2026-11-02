# D-12D-003 两轮执行与停止条件计划（A4 intake 版）

- 生成：A4 / a4-issue-liaison，2026-11-02T10:26+08:00；依据 Issue #4 评论 D-12D-003（6566994749）；只读，零求解
- 定位：本文件是计划对照表，不是 L 的派工卡；任务卡与预算由 L/负责人签发

## 1. 阶段结构

| 阶段 | 性质 | 允许动作 | 交付（证据） | 责任 |
|---|---|---|---|---|
| PRE-R1 | 零求解预检 | 读 Issue/PR/历史证据；清点旧版本、旧账本 | 需求矩阵、基线清单 | A4/A3 |
| R1-A 安装与隔离 | 零求解 | 官方 3.55.0 zip 校验、便携侧装、旧版保留 | 来源/hash/路径/回滚步骤（回滚执行=NOT_RUN） | A3 |
| R1-B API 兼容 | 非物理 | import/版本/Twist/导出/薄面与新 VSPAERO 输入/WaveDrag 结果 API；新旧几何同源对照 | API 兼容矩阵 JSON/CSV、几何差异 | A1 |
| R1-C 旧数据诊断 | 零求解 | 解析旧 .vspaero/.history/.polar/DegenGeom/尾迹/面元；WAVE-01..05 切片复算、条件数/离群/体积守恒 | 诊断 JSON/MD（文件+行号）、复算 CSV | A1/A2 |
| R1-D 独立复核 | 非物理 | 干净 worktree 复核 API/口径/诊断/账本；不得与 A1 编码重叠 | A5 独立复核记录（PASS/CHANGES_REQUESTED） | A5 |
| R1-E 归档 | 零求解 | 版本化 run_id：安装版本/hash、API 矩阵、源码/测试、诊断、Gate 状态、P4-PLAN 建议 | 仓库外草稿→L 决定入仓；正式报告 docs/reviews | L |
| R2（条件） | 预算门控 | 仅负责人批复后：最小分阶段 VSPAERO 测试；成对 wing-alone vs wing+body 面积律；可选 SU2 共同量对照 | 预算账本、结果 JSON/CSV、不确定度 | A2（A1 修代码） |
| 裁决 | 研究门 | A5 复核→L 汇总→负责人决定 P1-P3 / APPROVED_FOR_NEXT_STAGE | 单条 Issue 事实回执 | L/A4 |

## 2. 两轮上限与停止条件

- R1 与 R2 各最多一轮；合计两轮。不得以反复加密/重试替代假设检验。
- R1 内若无任何零求解证据可修复（如旧文件缺失/不可解析），直接记录 NOT_VALIDATED 缺口并进入 R2 预算申请或失败分支，不空转。
- R2 未获预算批复：状态 AWAITING_RUN_BUDGET；禁止写「已测试仍失败」或启动任何求解器自检。
- 即时停止（BLOCKED/FAILED，上报 L）：破面/负体积；参考量（Mach 2.02 / 18288 m / 3028020 m / 136000 kg / Sref 358.25 / cref 18.489893 / bref 25.604638）不一致；Mach 错误；反复不收敛；力/波阻非物理（如负总阻）；资源超限；预算耗尽；证据无法落盘；需改冻结合同。
- 每次真实进程启动（含失败/重试）必须计入 evaluations.jsonl/预算账本；缓存不得冒充新求解。

## 3. AWAITING_RUN_BUDGET 规则

1. 适用：需要 VSPAERO/WaveDrag/SU2/RCAIDE 任何真实求解，而负责人尚未批复该轮预算。
2. 申请内容（A2→L→负责人）：逐项最大调用数（按类型分列）、重试策略与是否计费、墙钟、CPU 核数/单机、RAM、失败停止条件、预期证据文件、成本上限。
3. 未批复：相关条目保持 AWAITING_RUN_BUDGET，不得降级为「NOT_RUN=已测试」或默认失败；不得以软件启动/API 自检替代物理验证。
4. 批复后：L 冻结 run_config、代码 SHA、环境与账本；A2 串行执行，超限即停并报告。
5. 旧预算边界：D-12D-002 的 23/23 已耗尽，不结转、不复用、不默认续批。

## 4. 通过/失败分支

- 通过（R1 或 R2 后）：A5 独立复跑/复核 → 逐项给出 LF/面积律/SU2/Mission 的 Gate 状态与不确定度 → L 汇总事实回执 → 负责人裁决 P1-P3 与是否 APPROVED_FOR_NEXT_STAGE。升级或单元测试通过不得单独宣布 PASS。
- 仍不通过：保留 3.26.1 + 3.55.0 双版本、D-12D-002 全部 23 次历史、SU2 部分有效结果与可复现 RCAIDE 单巡航；统一挂 LF_PROVISIONAL / BODY-CORR_NOT_VALIDATED 标签；允许启动 P4-PLAN-ONLY。
- P4-PLAN-ONLY 边界：固定 12D 任务与约束；15D 历史数据库隔离；fidelity 身份与未验证标志；BO/DE 既有代码离线玩具测试；预算/缓存/异常处理；未来 LF/HF 替代方案；物理误差/不确定度与正式优化前置条件。禁止新开 P5 MAML、正式 Concorde BO/DE、增列真实油耗标签；不等于 APPROVED_FOR_NEXT_STAGE。
- 无论结果：历史 P1-P3 科学结论与当前 Gate 原样保留；不得反向关闭未通过 Gate、不得合并 main。

## 5. 禁止清单（本轮 A4 摘要）

- 禁止未批复的 VSPAERO/WaveDrag/SU2/RCAIDE 求解（含伪装自检）。
- 禁止新开 Issue、评论他处、合并 main；PR #3 保持 open。
- 禁止 P4-P6 真实优化/训练（P4-PLAN-ONLY 除外）。
- 禁止把异常 LF/面积律结果作为优化真值或注入 Mission/目标（修正项未验证时为 null）。
- 禁止伪造数据/燃油标签/「已测试」结论；失败与 NOT_RUN 必须如实保留。
- 禁止 AI 记忆、聊天摘要、草稿进仓库；禁止未经 L 的仓库写与 git 写。
