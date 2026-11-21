# Issue #14 P0 阶段回执（D-REAL-EXP-002，2026-11-22）

**性质声明**：本回执只覆盖 P0（代码 / 零物理 replay / 12D 审计 / A2 主终点分析器 / 协议冻结）。
**不是 P1 授权**，**不是新的物理结果**，也不改写 G1/G2 历史。P1 起仍需专门的 A5 批次方案审查 + Lead 新 GO。

## 1. 零物理事实

- `physical_solver_starts_actual = 0`，`internal_solver_cases_actual = 0`，`labels_created = 0`。
- 本轮没有启动任何 VSPAERO 进程；replay 只读取 G1 已有的 `.polar` 原始行。
- 测试解释器 `D:\Anaconda\envs\RCAIDE\python.exe`；求解器身份只登记不调用。

## 2. 已交付代码与证据

| 项目 | 结果 |
|---|---|
| A1 `AdaptiveAlphaSolver` | 注入式真实求解回调；每次 probe 计 1 internal case；割线插值夹在 bracket 内；非单调返回 `INVALID_POLAR`；预算耗尽 `BUDGET_EXHAUSTED`；插值目标不计 raw |
| A1 `polar_rows` 解析 | 按表头解析 Beta/Mach/AoA/CLtot/CDo/CDi/CDtot；无表头/无行报错；缺失行返回 `REPLAY_ROW_NOT_AVAILABLE` |
| G1 零物理 replay | 24 case：raw 命中 8、需新 alpha 行 7、无 bracket 8、缺输入 1；旧固定扫描 391 internal vs 自适应 replay 329 probes；新标签 0 |
| 12D 响应审计 | 15 个变量全部真实进入 VSPAERO 输入；56 个 response pair 的 deck SHA 均不同 |
| A2 主终点分析器 | N_first_feasible / best_feasible_Di_N(B) / anytime / hit rate / simple_regret(null) / cost_to_target；G1 复算首个可行第 10 个 design（170 internal），点级可行率 8/24=0.3333，internal 391 与 batch accounting 一致 |
| 测试 | 280 项，failures 0，errors 0，skipped 0，successful=True |

分支 `research/dreal004-alpha-adaptive-meta-sampling`，基线 `af9871c`。
代码提交 `db44071`；证据目录 `docs/evidence/dreal004/p0/`。

- `docs/evidence/dreal004/p0/p0_a5_dossier.md` sha256 `7a5a559ffd86362518c03a116c3d653025278f16faf860b7dc854a1298c7838b`
- `docs/evidence/dreal004/p0/p0_test_summary.json` sha256 `865e7e21e351a7fd5db5c01ab6f2b775214ab2f8324fd21372c12bf91b3a11e8`
- `docs/evidence/dreal004/p0/p0_test_log.txt` sha256 `7cfb970e8f2f98ce5b534c7e532af13fff0bb21ddea539b972065704619f0303`
- `docs/evidence/dreal004/p0/g1_alpha_replay.json` sha256 `342ff7a1cd389955a877d3028af91bb1c18a6aca8f3059dd0754817e3cf1df2d`
- `docs/evidence/dreal004/p0/12d_variable_response_audit.json` sha256 `c6e903199cfbb607f8b4cecd10d50942e3c2670de9ac2c4198af6615f9fb018d`
- `docs/evidence/dreal004/p0/a2_g1_baseline_endpoints.json` sha256 `c28c0dc02e1104c1f5d724a4ff0fb6cb1fc4e2ff19fdac0de7e01cdd62183f43`
- `docs/evidence/dreal004/p0/p1_p2_p3_preregistration.json` sha256 `aa01f5c0b3556f2627c43b69213da6559beedc6951828a0e25dce31af6daa645`
- `docs/evidence/dreal004/p0/p0_protocol_freeze_20261122.md` sha256 `9a96c0d8530c4fe66d7edb8bb1260889cb046cf2aca017ea4b969bfbf8a04f70`
- `docs/evidence/dreal004/p0/a5_review_p0_verdict.json` sha256 `6d406b035268db835678e0aafa74edaee8865911d24ff039abf0a4a922b08f67`
- `docs/evidence/dreal004/p0/g2_halt_reference.json` sha256 `6594bd35feee69809fa892eb2f1d41b6f5c4cb0dcb4ebbc4d6e00631d69fd106`

## 3. A5 独立审查结论

- reviewer：`deepseek-flash`，单发只读、无工具；**非人类签署**，不替代 Owner 签字。
- verdict：**`P0_CODE_AND_PROTOCOL_PASS`**（reviewed 2026-11-21T19:24:11Z）。
- gates：`P0_CODE_PASS`=PASS；`P0_ZERO_PHYSICAL_REPLAY_PASS`=PASS；`P0_12D_RESPONSE_AUDIT_PASS`=PASS_WITH_DISCLOSURE；`P0_A2_ENDPOINT_ANALYZER_PASS`=PASS；`P0_PROTOCOL_FREEZE_PASS`=PASS；`P0_ZERO_PHYSICAL`=PASS
- findings：[info] Dossier grants no new physics and explicitly withholds P1 authorisation; P1 requires separate batch-plan A5 review and fresh Lead GO.；[info] Interpolated estimates are not counted as raw hits; replay returns REPLAY_ROW_NOT_AVAILABLE for missing rows.；[info] tol_CL=1e-3 is unchanged and prior G1/G2 results are not re-graded.；[minor] V01/V02 are passive at beta=0 and correctly excluded from active 12D response claims; V02 response remains unmeasured.；[minor] Dossier does not state its own SHA256, so dossier_sha256 could not be verified from provided content.；[minor] Mach 1.6 has zero G1 labels and 6 no-bracket cases; P2 inclusion is conditional on new admitted labels.；[info] Zero-physical claim is supported by 0 solver starts, 0 labels, and 0 internal solver cases this round.
- 非阻断披露：V01/V02 在 β=0 任务族中为 passive 维度，不声称其 12D 响应；Mach 1.6 零 G1 标签、6 个无 bracket；无独立 Di_N 参考，`simple_regret` 保持 null。

## 4. 冻结协议（P1–P3 预注册）

- 任务 split 冻结：train M140/M160/M200/M202，val M180/M220，test M240/M260；support `d00–d03`、query `d04–d07`。
- P1（**未授权**）：Mach 2.02，设计 `d00/d01/d04/d07`，≤12 design starts、≤3 starts/design、≤36 internal cases，`tol_CL=1e-3` 不放宽；需 A5 批次方案审查 + Lead 新 GO。
- P2（未授权）：≤240 新 starts；每 train 任务 ≥4 条真实准入标签；FOMAML/普通预训练/16D 上下文预训练/随机初始化；负迁移照实报告。
- P3（未授权）：≤384 新 starts；等预算配对比较 Random/LHS/Sobol/预训练/FOMAML；输出 B=4/8/16/32/64/128 anytime 曲线。
- 主终点、公平性、统计、禁止项见 `p1_p2_p3_preregistration.json` 和中文 `p0_protocol_freeze_20261122.md`。

## 5. 上一阶段（G2）中止真相（不改写、不签发 G2 回执）

- B01：24 starts，23 completed，731 internal，4 标签，20 null。
- B02：78 starts，78 completed，2886 internal，26 标签，52 null，有效率 33.3%，B02 上限 112，剩 34 未用。
- 累计 **102/240** starts；G2 MAML 未运行，G2 回执未签发。G1 24 starts / 8 labels / 34.78% 永久保留。

## 6. 门禁与下一步

- P0：A5 `P0_CODE_AND_PROTOCOL_PASS` 已取得（非人类）；**P0 已完成**。
- P1：未授权。拟定 `AUTH-DREAL004-P1-20261122-01` / `DRECOVER001-P1-20261122-01`（Mach 2.02，4 designs，≤12 starts，每 ≤8 starts 上传+远端回读，连续 2 次 solver 失败或墙钟 3600s 停止）。
- P2/P3：未授权，须 P1 验收后另行 A5 + Lead 分批 GO。

## 7. GitHub 复核入口

- 分支：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/research/dreal004-alpha-adaptive-meta-sampling
- P0 证据目录：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/research/dreal004-alpha-adaptive-meta-sampling/docs/evidence/dreal004/p0
- G2 中止说明：Issue #13 评论 https://github.com/QingYangJin/RCAIDE_Supersonic/issues/13#issuecomment-7063823679

