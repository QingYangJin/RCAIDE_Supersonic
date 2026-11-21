# G2 B02 修订案（A5 独立审查用 dossier）

- 阶段：Issue #13 / G2（真实 VSPAERO 标签 + 后续 MAML）
- run_id：`DRECOVER001-G2-20261121-01`
- authorization_id：`AUTH-DREAL003-G2-20261121-01`（Owner m08739「批准」；G2 上限 240 starts）
- 本 dossier 只申请 **B02 修订与放行**，不申请 G3/R2 物理，不改变 G2 的 240 starts 总上限。
- 生成时间：2026-11-22T00:45:00Z；本修订本身 physical_solver_starts_actual = 0。
- 字节绑定：本文件正文之后有 `<!-- SELF_HASH -->` 标记；`dossier_payload_sha256` = 该标记之前全部字节的 SHA256，写在标记之后。文件无法包含自身完整 SHA256，这是可验证的替代绑定。

## 0. 结论摘要（供 A5 判定）

B01 已用 24/24 starts，23 completed，4 条准入标签，标签率 4/23 = **17.4%**，远低于 G2 预注册的 70%。根因不是求解器或准入规则，而是 **stage2 窗口中心由 stage1 全范围 OLS 估计**，在 M140 高迎角处中心偏低最多 0.11°，导致 ±0.006° 窗口整体错过目标升力；B01 的 11 个 stage2 中 7 个 M140 全部 `CL_TARGET_OUTSIDE_POLAR`，4 个 M160 因 OLS 恰好接近而准入。

本修订把 stage2 中心改为 **stage1 原始极曲线相邻两行的局部线性 bracket 插值**（不引入新物理、不改变冻结的 g2_build.py、不改变准入规则），已用 B01 的 12 个 stage1 原始 polar 做零物理验证：12/12 目标均被 bracket，最坏保守相邻网格相对升力误差 1.2966e-4，为 1e-3 容差的 13.0%，物理 starts = 0。

B02 申请范围：**最多 112 starts**（stage1 52 + stage2 最多 60），占 G2 剩余额度 216 的 51.9%；若全部执行则累计 136/240。分 15 个 ≤8 starts 的子批，每子批上传并远端回读 SHA256 后才放行下一子批；0 retry、parallel 1、单 case 600s、批次 wall stop 3300s。**112 是上限，不是承诺**；bracket 失败、超时、wall stop 都会减少实际 starts，按 null/未启动如实披露。

## 1. B01 最终账本（已发生，不可改写）

证据文件（本地绝对路径，SHA256）：
- `D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/batch_accounting.json`：`1fa46038c1e0ad288e8db7045da69449a14cb2c5b451b6b5ce3fc193cfa063fc`
- `D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/admitted_labels.csv`：`6b7051692823785df5a9f4e41522cc9957ca4eed11fb2f5d5aa62313ca3a45c6`
- `D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/g2_go_record_b01.json`：`4849d7534fe2639e2e12219a7f5f645963f047be07136734327525ba75164873`
- `D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/g2_preregistration.json`：`d4aa6c235367a3093933dacb2039ceab8baa9c392fe6c61aeb00dd4e4fce83f9`

账本数字：

| 口径 | 数值 |
|---|---|
| physical_solver_starts_actual / logged | 24 / 24（每个都有 solver_attempts.jsonl start 事件） |
| completed | 23（stage1 12 + stage2 11） |
| interrupted（有 start、无 end、无 .polar/case_result） | 1：`g2-m140-d03-support-s1`，外层 120s 超时，`NULL_SOLVER_NO_RESULT_INTERRUPTED`，不重跑 |
| internal_solver_cases_actual_logged | 731（中断 case 内部数 UNKNOWN，不计入） |
| retries / parallelism | 0 / 1 |
| charged starts / remaining | 24 / 0（B01 的 GO 为 24） |
| cumulative against G2 cap | 24 / 240 |
| admitted labels / null | 4 / 20 |
| valid rate over completed / charged | 17.39% / 16.67% |

4 条准入标签（全部 M160 support stage2；证书 q_pa=12851.40843975621、sref=358.25000000000006、evidence_scope=`LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`）：

| case_id | di_n | cl | cdi | alpha_deg |
|---|---|---|---|---|
| g2-m160-d00-support-s2 | 175741.51787085226 | 0.289770270714 | 0.038171343647 | 7.4745148219 |
| g2-m160-d01-support-s2 | 174033.2901422012 | 0.287004214635 | 0.037426053272 | 7.4001425458 |
| g2-m160-d02-support-s2 | 177763.73005993845 | 0.289687458338 | 0.038610571425 | 7.5612945065 |
| g2-m160-d03-support-s2 | 177530.4075414802 | 0.292627944682 | 0.038949387267 | 7.5513903279 |

准入恒等式 `di_n = q_pa * sref_m2 * cdi` 逐张证书复核，4/4 相对误差 0.0；B01 已上传并完成全量远端逐字节回读（见第 7 节）。

20 个 null 的分类：
- 12 个 stage1：`SCREENING_ONLY_NOT_ADMITTED`（stage1 是 49 点粗扫，仅用于 bracket/中心，按预注册不产生标签）。
- 7 个 stage2 M140：`CL_TARGET_OUTSIDE_POLAR`，全部为 v1 OLS 中心偏差所致。
- 1 个 stage1 中断：`NULL_SOLVER_NO_RESULT_INTERRUPTED`。

## 2. B01 根因（v1 stage2 方法）

预注册 v1（`g2_build.py`，SHA256 `3de1c261abc1a38f5f12c4d2d4c3c83bccefd75300d5b4f3df65fc0bbedf18b8`）stage2 中心 = 对 stage1 全部 49 个同 Mach 点做 CL(alpha) 全范围 OLS，再在 CL_target 处反解 alpha。stage2 网格 13 点、步长 0.001°、半宽 0.006°。

B01 实测：
- M140：v1 OLS 中心 9.3386–9.5638°，局部原始行 bracket 插值中心 9.4351–9.6783°，偏移最大 **0.11°**；0.006° 半宽无法覆盖，7/7 stage2 全部 `CL_TARGET_OUTSIDE_POLAR`。
- M160：OLS 中心恰好接近目标，4/4 support stage2 准入；d04-query 的 stage1 完成但 stage2 未启动（B01 的 11 个 stage2 = M140 7 + M160 4）。
- 斜率：B01 v1 全范围 OLS 低估高迎角局部斜率；B02 v2 局部斜率 M140 0.03645–0.03752 /deg、M160 0.03677–0.03719 /deg。
- 结论：这是 **窗口中心估计方法** 问题，不是 VSPAERO、不是准入审计、不是 lift 容差；不通过放宽容差或插值准入解决。

## 3. v2 方法（B02 唯一变更）

新 stage2 builder：`D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/scripts/g2_stage2_build_v2.py`，SHA256 `9435d7a79867981523954ee7102bc5a760f567e33c5e883867b44aa39be2b06f`。

算法（只读 stage1 原始 `.polar`，零物理）：
1. 解析 `.polar` 中 `Beta Mach AoA Re/1e6` 表头的行；只保留 `|Mach - case_mach| < 1e-12` 的行，按 AoA 排序。
2. 在相邻两行 `(a0,c0),(a1,c1)` 中寻找严格 bracket：`min(c0,c1) <= cl_target <= max(c0,c1)` 且 `c1 != c0`。
3. 线性插值得到 `alpha_center = a0 + (cl_target-c0)/(c1-c0)*(a1-a0)`，并记录局部斜率 `(c1-c0)/(a1-a0)` 与 bracket 两行原始值。
4. stage2 网格 = `alpha_center + 0.001*(i-6)`，i=0..12（13 点，半宽 0.006°），与 B01 网格完全相同。
5. 若目标不在 stage1 同 Mach CL 范围内，输出 `SKIP_TARGET_OUTSIDE_STAGE1_RANGE`，该 case 为 null，不扩窗、不重跑、不插值准入。
6. 其他一切不变：`g2_build.make_case` 的几何、flow、TaskSpec、plan/approval、budget 字段不变；准入仍是 `RealAdmissionManifest` + 独立 `audit_real_case.py`，只接受 stage2 原始 polar 行且 `|L-L_target| <= 1e-3*L_target`，插值不入账。

方法标识写入 `g2_stage2_manifest_v2.json`：`method = LOCAL_LINEAR_BRACKET_INTERPOLATION_OF_STAGE1_RAW_POLAR_ROWS`，schema `dreal003.g2_stage2_manifest.v2`，并记录 `builder_sha256` 与 `g2_build_sha256`。

## 4. v2 零物理验证（B01 的 12 个 stage1 原始 polar）

验证脚本：`D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/scripts/validate_g2_stage2_v2.py`，SHA256 `0952db186844c458376da76c637d0a3571e8dc4d72d4e11a944c7d29f7c8ce42`。
输出：`D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/g2_stage2_v2_validation.json`，SHA256 `5a3526639a0fe779f4de6d5a46ee7a710806f8d6479588f654ac594d917dfbb6`；副本 `docs/evidence/dreal003/g2/g2_stage2_v2_validation.json`（同字节）。

结果：
- 检查 12 个有 stage1 结果的 case（M140 7 + M160 5），**12/12 全部 bracket 成功**。
- `all_proxy_within_tolerance = true`。
- 最坏保守相邻网格相对升力误差 `worst_conservative_adjacent_rel_error = 0.0001296611813962056`，为 1e-3 容差的 **13.0%**（7.7 倍余量）。
- M140 中心范围 v1 9.3386–9.5638° → v2 9.4351–9.6783°。
- `physical_solver_starts_used = 0`。
- 验证方式：用同一 bracket 线性式在中心与中心 ±0.001° 处求代理 CL，取相邻两点最坏相对误差作为保守上界；不把代理值当作准入标签。

## 5. B02 申请范围（精确到 case）

总计划 **最多 112 starts**；若全部执行，累计 136/240，剩余 104。B02 自身不超 112。

### 5.1 stage1（计划最多 52 starts）

分项（互不重复）：
- **51 个从未发过 start 的设计**：M160 d05,d06,d07（3）+ M180/M200/M202/M220/M240/M260 各 8 个（48）。
- **1 个 repair**：`g2-m140-d03-support-s1`（B01 已计费中断，B02 用新 start 重跑，不掩盖 B01 的 1 次中断）。
- 合计 51 + 1 = 52。M140 的 d03 只出现在 repair，不再重复计入“未启动”项。
- stage1 alpha 网格仍为 49 点全窗口。

### 5.2 stage2（计划最多 60 starts，依赖 stage1 成功）

- **52 个**：B02 stage1 完成后，对其 52 个成功 case 用 v2 bracket 建 stage2；失败/目标不在范围内则 null，不启动。
- **1 个 backfill**：`g2-m160-d04-query-s1` 的 stage1 已完成、B01 未建 stage2，用 v2 补建 1 个 stage2。
- **7 个 repair**：B01 v1 的 7 个 M140 stage2（d00,d01,d02,d04,d05,d06,d07）全部 `CL_TARGET_OUTSIDE_POLAR`，用同一批 stage1 原始 polar 以 v2 重建并重跑；这是新 GO 下的新 start，**不是同一 batch 内的 retry**。
- 合计 52+1+7 = 60。其中 d03 的 stage2 依赖 5.1 的 repair 成功；若失败则少 1，按 null 披露。
- **60 是上限，不是承诺**：任何 bracket/target 失败、超时、wall stop 都会减少实际 stage2 starts。

### 5.3 任务/标签目标

8 个任务 × 8 设计 = 64 个设计；B01 已有 4 个 M160 准入标签。B02 完成后最多再产生 60 条标签，G2 最多 64 条（每设计 1 条，support 4 / query 4 per task），满足后续 MAML 的 K-shot 结构。**不承诺 60/60 全部成功**；失败/超时按 null 计，不重跑。

### 5.4 预算与控制

| 项 | 值 |
|---|---|
| B02 starts 上限 | 112（stage1 52 + stage2 60） |
| G2 累计（若全部执行） | 136 / 240（B01 24 + B02 112） |
| 子批 | 每个 ≤8 starts；stage1 7 个子批（8×6+4），stage2 8 个子批（8×7+4） |
| 子批间动作 | 打包本子批新增 raw + logs + 账本 → push 到 `research/dreal003-expanded-aero-meta-20261120` → 从远端回读 SHA256SUMS/data_manifest 并核对，全部匹配才发下一子批 |
| retries | 0（失败/超时即 null） |
| parallelism | 1 |
| 单 case timeout | 600s |
| 批次 wall stop | 3300s；每次 start 前检查 elapsed，若 elapsed≥3300s 或 elapsed+600s>3300s 则不再发 start；预留 300s 上传/回读。**若 wall stop 触发，B02 提前收口，未启动设计不再补，按未启动/null 披露** |
| 停止条件 | 任何 REFUSED；连续 2 个非 SOLVED；任何 timeout/无结果；子批账本不守恒；任何 raw/上传回读 hash 不匹配；同一子批内 >20% completed stage1 无法建 stage2 |
| 标签验收 | 以 completed stage2 为分母，目标 ≥70%；若 B02 结束仍 <70%，如实披露、不宣称达标，并把是否继续 MAML 提交 Owner/A5 决定 |

B01 实测单 start 墙钟：stage1 约 22s/start，stage2 约 7s/start；若 B02 全部 112 starts 按此均值约 1,600s，加上 15 次上传/回读，预计仍在 3300s 内。但**这是实测均值，不是保证**；长尾 case 会触发 wall stop 或 600s timeout。

## 6. 代码与证据身份

| 文件 | SHA256 |
|---|---|
| `scripts/g2_stage2_build_v2.py` | `9435d7a79867981523954ee7102bc5a760f567e33c5e883867b44aa39be2b06f` |
| `scripts/validate_g2_stage2_v2.py` | `0952db186844c458376da76c637d0a3571e8dc4d72d4e11a944c7d29f7c8ce42` |
| `scripts/g2_build.py`（冻结，未改） | `3de1c261abc1a38f5f12c4d2d4c3c83bccefd75300d5b4f3df65fc0bbedf18b8` |
| `scripts/run_g2_batch.py`（冻结，未改） | `45bfe3beadabb3dfaa2ae30379d03ef4ab61446e2bdc195a59ece657694650be` |
| `scripts/postprocess_g2.py`（冻结，未改） | `3c0d967439fbe57d101aaa14335d688231a23694f784a42cbb73402c8f1dfb38` |
| `scripts/package_g2_b01.py` | `bcab99d38cc9ca2c0c01f40fce6f6156f50b44edcf08991bfae3d5d2a191f38c` |
| `g2_stage2_v2_validation.json` | `5a3526639a0fe779f4de6d5a46ee7a710806f8d6479588f654ac594d917dfbb6` |
| B01 `batch_accounting.json` | `1fa46038c1e0ad288e8db7045da69449a14cb2c5b451b6b5ce3fc193cfa063fc` |
| B01 `admitted_labels.csv` | `6b7051692823785df5a9f4e41522cc9957ca4eed11fb2f5d5aa62313ca3a45c6` |
| B01 全量远端回读审计 | `6c64af194575787692867f2165247aca5803f1f8d8cb34d2f88e7ac00dd080bd` |

B02 的 runner 将复用冻结的 `run_g2_batch.py` 的逐 case plan/approval/budget 与 solver 调用路径；子批编排/上传回读封装如新增，会单独列 SHA，不修改上述冻结文件的语义。

## 7. B01 远端状态（已上传并完成全量回读）

- 分支：`research/dreal003-expanded-aero-meta-20261120`
- commit：`28d2d95d0df83d7179ee1353b2e11f378743bbbd`（parent `409f09c8b31ce653873727217273805a16d5b422`）
- 包目录：`research/concorde_metaopt/optimization_runs/DRECOVER001-G2-20261121-01`
- 文件：1,366 / 243,812,834 B；`data_manifest.json` SHA `371d7e968c3c3bed8c184289a24feb6333e6afacadc41d20f45882441d525008`；`SHA256SUMS.txt` SHA `f6866a1b275187dd82a002ad7d9a3c07005cc83c1036a2e6f048438f09f12795`
- **全量回读方法**：`git fetch --depth=1` 精确 commit（verify_g2_b01_remote_git.py），checkout 后逐文件 SHA256 对照 data_manifest；结果 `all_ok=true`、1,366/1,366 通过、`bad_sha256=[]`、`missing=[]`、SHA256SUMS 集合一致、4 张证书恒等式全通过；审计文件 `D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/remote_g2_b01_retrieval/g2_b01_remote_retrieval_audit.json`，SHA256 `6c64af194575787692867f2165247aca5803f1f8d8cb34d2f88e7ac00dd080bd`。

## 8. 披露与不声称

1. 本文的 12/12 bracket 验证是 **B01 已有 stage1 原始 polar 的离线重分析**，不是新物理；对新任务（M180 等）的 bracket 只有在 B02 stage1 完成后才能确认，可能出现 null。
2. B01 的 24 个 start 与 4 条标签已计费、不撤销、不重标；B02 的 7 个 M140 stage2 与 1 个 M140 d03 stage1 是 repair start，B01 已计费，两者都进入累计账本；B01 的 7 个 null 保持 null，不被覆盖。
3. B01 的 17.4% 标签率不满足 G2 的 70% 目标；B02 不保证达标，若仍不达标将如实报告并停在此处。
4. B01 的 4 条 M160 标签仍是同机、`LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`、非人类独立认证、未做物理验证；B02 不改变该证据等级。
5. 本 dossier 不授权 G3、不授权 R2、不授权任何 MAML 训练物理；MAML 只在 G2 标签完成后另行预注册。
6. 本 dossier 不替代 A5 对 R1 全部代码的最终 PASS；A5 仍是 deepseek-flash 独立只读、非人类签字。
7. B02 若触发任何停止条件，立即停止并保留全部 raw/账本，不重跑、不覆盖。
8. B02 的 112 starts 是上限；B01 实测墙钟均值只是估算，长尾 case、上传回读耗时与 wall stop 都可能减少实际 starts。

## 9. 请 A5 判定的 gate

- `G2_B01_ACCOUNTING`：24/24/23/1/731/4/20/17.4% 是否与证据一致、是否如实披露。
- `G2_STAGE2_METHOD_V2`：局部 bracket 插值是否是可接受的 stage2 中心方法、是否不改变准入（原始行 + 1e-3 容差）、零物理验证是否充分。
- `G2_B02_SCOPE`：最多 112 starts、52+60 上限分解、累计最多 136/240、7 个 M140 repair + 1 个 M160 backfill + 52 个新 stage2 是否在 G2 授权范围内。
- `G2_REPAIR_START`：B01 已计费的 M140 stage2 以新 GO 重跑是否合规、是否与"不重跑"冲突（本修订明确：新的 start，不是 retry；B01 的 7 个 null 保持 null）。
- `G2_BATCH_CONTROLS`：≤8 starts/子批、上传回读后再放行、0 retry、600s、wall 3300s、停止条件、账本守恒是否足够。
- `G2_ZERO_PHYSICAL`：本修订与验证是否 0 次求解器启动。

期望 verdict：`G2_AMENDMENT_APPROVE` | `G2_AMENDMENT_CHANGES_REQUIRED` | `G2_AMENDMENT_REJECT`。

<!-- SELF_HASH -->
dossier_payload_sha256 = 1a092153c52aee8ba7be57727a726af3cc5a632c18d50415afd11c0fff974a1b
