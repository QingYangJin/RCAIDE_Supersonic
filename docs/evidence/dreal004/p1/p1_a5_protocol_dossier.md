# Issue #14 P1 批次方案 A5 审查卷宗（自适应迎角，真实评估，≤12 starts）

## 0. 本卷宗的性质

- 对象：Issue #14 的 P1 小批（真实求解），Owner m10191 已批准真实评估。
- 本卷宗在 GO 之前生成：**尚未启动任何真实求解**，coarse bracket 全部来自既有 G2 stage1 原始 polar（零物理）。
- A5 需裁决：是否允许按本方案启动 ≤12 个真实 design starts。P2/P3/MAML/G2 重启/R2 均不在本授权内。
- 本卷宗不解宽任何容差，不允许把插值当原始行，不允许复用或改写 G1/G2 结果。

## 1. 批次身份与预算

- run_id: DRECOVER001-P1-20261122-02
- batch_id: DRECOVER001-P1-20261122-02-B01
- authorization_id: AUTH-DREAL004-P1-20261122-01
- 目标：DREAL004-M202，Mach 2.02，设计 d00/d01/d04/d07
- 上限：12 starts，每设计 ≤3 starts，每 start ≤3 alpha probes，内部 case ≤36，0 retry，parallel 1，单 case 600s，墙钟 3600s
- 算术核对：12 starts × 3 probes = 36 internal（<=36）；固定 49 点扫描对照：4 设计 × 49 = 196 internal
- 现有既有原始行只作为 coarse bracket 来源，不计入本轮 starts/internal

## 2. coarse bracket 来源（零物理）

| 设计 | 粗 case | 粗 polar sha256 | cl_target | bracket alpha (deg) | bracket CL | 粗步长 | 预测 alpha |
|---|---|---|---|---|---|---|---|
| d00 | g2-m202-d00-support-s1 | b1374bdf67822f8f | 0.181743917420 | [4.9600, 5.2000] | [0.174122366, 0.182386414] | 0.2400 | 5.181341 |
| d01 | g2-m202-d01-support-s1 | 21e4d8ee7cc7a88b | 0.179944472693 | [4.9600, 5.2000] | [0.174123471, 0.182387573] | 0.2400 | 5.129049 |
| d04 | g2-m202-d04-query-s1 | 852abc80194b6691 | 0.181743917420 | [4.9600, 5.2000] | [0.173786432, 0.182034554] | 0.2400 | 5.191543 |
| d07 | g2-m202-d07-query-s1 | b1374bdf67822f8f | 0.181743917420 | [4.9600, 5.2000] | [0.174122366, 0.182386414] | 0.2400 | 5.181341 |

说明：G2 stage1 的 M202 扫描步长 0.24 deg，目标 CL 落在 4.96–5.20 deg 之间；上表是把这些既有原始行做局部割线插值得到的预测中心，不是新求解结果。

## 3. 自适应算法（每设计最多 3 轮、每轮 3 个 alpha probe）

1. 用当前 bracket 做割线预测 alpha_target，取 alpha_target-Δ、alpha_target、alpha_target+Δ（Δ 依次 0.004/0.002/0.001 deg），并夹在当前原始 bracket 内；不做外推。
2. 每个 case 做 1 次真实求解（1 start，3 个 internal alpha 行）。
3. 读取新原始 polar 行；若存在某行满足 |q*Sref*CL - lift_target|/lift_target <= 1e-3，则该设计命中，转独立审计 + 准入。
4. 否则用全部已观测原始行重拟合 bracket，进入下一轮；3 轮仍未命中 -> NO_RAW_POINT（NULL_LABEL），不重跑。
5. 单调性缺失、无 bracket、求解失败按停止条件处理，不伪造行。

## 4. 准入与记账

- 只有新求解产生的原始 polar 行可准入；插值估计只用于选点，永不作为标签。
- 准入走既有独立审计脚本（复核 artifact sha256/deck 字段/polar 行/升力残差）与 RealAdmissionManifest 准入脚本，证书 scope 同前：LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED。
- 每次 start 前检查：starts<12、该设计 starts<3、internal+3<=36、墙钟+600<=3600、无 2 连败；否则不启动。
- 每个 ≤4 starts 迷你批完成后上传 GitHub 并逐文件 SHA256 回读，回读失败即停。

## 5. 交付物

- raw_cases（每个 case 的全部原始文件）、tables/alpha_refinement_history.csv、all_evaluations.csv、admitted_labels.csv、failed_or_null.csv、actual_solver_ledger.csv
- metadata（prereg/go/code_sha/data_manifest）、figures（中文 PNG + figure_data.csv）、SHA256SUMS.txt、upload_receipt.json
- P1 结论：hit rate、每设计 internal 数、与固定 49 点扫描的 internal 对比、A5 P1 关闭审查

## 6. 披露（不隐藏）

- d00/d01 在 G1 已有同几何、同 Mach 的已准入标签；P1 对这两个设计是重确认 + 自适应效率测量，不是新几何发现。d04/d07 在 G1/G2 尚无准入标签。
- 已发现的重复：d07 的 G2 stage1 coarse polar 与 d00 字节完全相同（同 sha256 b1374bdf…），两设计仅 fuselage_length 不同。这说明该变量在当前薄面 VSPAERO 模型下对本极曲线无影响；d07 因此只作该变量的重复性/无效性对照，即使命中也不视为独立几何发现。
- 所有准入证书为同机、非物理验证、非人类签名；A5 为 deepseek-flash 单发只读评审，不是人类签署。
- 本批次不训练 MAML、不产生跨任务泛化结论；P2/P3 仍需另行 A5 + Lead GO。
- 墙钟按各次 run_case 的 wall_s 之和计算（含求解进程时间，不含上传等待），与 G2 口径一致。

## 7. A5 检查点

- P1_CAPS: 12 starts total, 3 per design, 3 alpha probes per start, 36 internal max, 0 retry, parallel 1, 600s per case, wall 3600s, 2 consecutive failure stop.
- P1_COARSE_BRACKET_PROVENANCE: all coarse brackets come from existing G2 stage1 M202 raw polar files whose sha256 are listed per design; no new solver call before GO.
- P1_ALPHA_ALGORITHM: secant prediction inside the observed raw bracket, half widths 0.004/0.002/0.001 deg, no extrapolation, non-monotone or missing bracket stops the design.
- P1_ADMISSION_TOLERANCE: tol_CL=1e-3 unchanged; only raw polar rows from new solver runs may be admitted; interpolated targets are never labels.
- P1_ACCOUNTING_CONTROLS: per-start ledger rows (case, round, status, wall, internal, exit code, matched row), cumulative caps enforced before each start, accounting report at the end.
- P1_ZERO_PHYSICAL_UNTIL_GO: dossier creation and A5 review are zero physical; the batch starts only after an A5 PASS and a separate Lead GO record binding this prereg sha256.

## 8. 待绑定哈希

- 本 preregistration sha256: dfbde72fe6e6e2064dc61b2d9efabcc792adb4414576d6c03bc907817744d477
- 代码/脚本 sha256:
  - research/concorde_metaopt/dreal001/geometry/adaptive_alpha.py: 8442da15459aa6da9d0b717daf0a419f4478cafabc22b578c4d599441cbaf738
  - research/concorde_metaopt/dreal001/geometry/polar_rows.py: bc590fb4e3ef2881f1f03464c00364d88dad17b50e9463320b29d6aeb21beeaf
  - research/concorde_metaopt/dreal001/geometry/solver_runner.py: cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3
  - research/concorde_metaopt/dreal001/meta/real_admission.py: 4322554ea488dd583a9c06fc8bb611e0584360573287673fe46bbbcc605ee3fc
  - scripts/p1_run.py: 628e4bf15dd565b488eda69fb38513cf318df4869f13b8832cd5e94cdfb8dc27
  - scripts/audit_real_case.py: 5c07a4865f37d434961f99b9862fea7ea1e8b4a238db8b1cd79aba4c339a842c
  - scripts/admit_g1_case.py: b2b70846b1fe17b3335b4e8c46be3afd40188459c302ce59b0ecfeef20d8cddf

