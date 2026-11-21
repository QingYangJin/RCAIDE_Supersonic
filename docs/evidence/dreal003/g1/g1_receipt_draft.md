# Issue #13 · G1 阶段回执

状态：G1 执行完成，**未完成 70% 有效标签率目标**，因此本回执**不签发 G2 GO**。
性质：本文件是 G1 真实计算与上传的阶段回执，不是 G2/G3 授权，不是人类签署，不改变 Issue #13 门禁。
授权：Owner m07992“继续执行，把G1阶段也完成，批准实际物理计算”；G1 合同上限 24 starts。

## 1. 结论先行

- G1 实际启动 **24** 次 VSPAERO（B01 8 + B02 16），完成 23 次，1 次启动后无结果；internal solver cases **391**；retries **0**；parallel **1**；剩余 starts **0**。
- 准入标签 **8** 条；null **16** 条（15 条审计升力容差失败 + 1 条启动无结果）；有效标签率 **8/23 = 34.78%**，低于 70% 目标。
- 8 条标签全部来自真实 VSPAERO 原始文件，原始 .vsp3/.vspgeom/.vspaero/.polar/.history/.lod/.adb、stdout/stderr/exitcode/超时标记、CSV、账本、PNG 已上传到 GitHub；本地与远端 SHA256 见第 5 节。
- G1 **不能宣称成功**：未达标签率目标，且同机、未做物理验证、未获独立人类签字。G2 需要新的 A5 预审与 Lead GO；当前 **NO_G2_GO**。

## 2. 授权、A5 与代码状态

| 项 | 值 |
|---|---|
| authorization_id | AUTH-DREAL003-G1-20261121-01 |
| batch_id | DRECOVER001-G1-20261121-01-B01 / -B02 |
| Owner 授权 | m07992（G1 实际物理） |
| G1 预审 A5 | G1_APPROVE，deepseek-flash，单发只读 dossier，非人类签字 |
| 修复批次 A5 | G1_REPAIR_APPROVE，仅放行 B02 16 starts |
| 预审 dossier SHA256 | 0ed4a2410357a34c6ff7620d42eca269034f496be1e89cc03e9f47e8b4b0fa79 |
| 修复 amendment SHA256 | 9dc47742648e04a385400c511eef0ae300616fc1e225ecb3faec8dbe78261b5f |
| code_sha（worktree HEAD） | f0e455f32b70da88f40d32f8be1fbabd649981ab |
| 分支 | research/dreal003-expanded-aero-meta-20261120 |

A5 的两次结论是只读 dossier 审查，不是人类签字；A5 的保留披露是：253 项测试/文件 SHA 部分自报、253 日志与 A1 文件 SHA 自报、全量远端复核只对特定 commit、m240-d01 内部 case 数未知、旧标签 pre-A1、同机、36 个 curated 非原件。G1 没有把 A5 当作 R1 全部代码 PASS。

## 3. G1 账本（六类口径最小集）

| 口径 | 数值 |
|---|---|
| physical_solver_starts_actual | 24 |
| physical_solver_starts_completed | 23 |
| internal_solver_cases_actual | 391 |
| retries_actual | 0 |
| parallelism | 1 |
| planned_reserved_starts | 24 |
| remaining_starts | 0 |
| admitted_labels | 8 |
| null_labels | 16 |
| valid_label_rate | 34.78%（8/23，未达 70%） |

### 3.1 分任务

| 任务 | split | Mach | starts | 完成 | 标签 | null |
|---|---|---:|---:|---:|---:|---:|
| DREAL003-G1-M160 | train | 1.6 | 6 | 6 | 0 | 6 |
| DREAL003-G1-M180 | val | 1.8 | 6 | 6 | 2 | 4 |
| DREAL003-G1-M202 | train | 2.02 | 6 | 5 | 3 | 3 |
| DREAL003-G1-M240 | test | 2.4 | 6 | 6 | 3 | 3 |

### 3.2 8 条准入标签（真实 VSPAERO，D_i_N = q·Sref·CDi）

| case | task | split | design | Mach | alpha_deg | D_i_N (N) |
|---|---|---|---|---:|---:|---:|
| g1-m180-d03-query | M180 | val | d03（面积-1%） | 1.8 | 6.2491982452 | 146625.66015490517 |
| g1-m180-d05-query | M180 | val | d05（垂尾+2%） | 1.8 | 6.1846 | 145090.24050579005 |
| g1-m202-d00-support | M202 | train | d00 基准 | 2.02 | 5.1813176428 | 121437.50128642528 |
| g1-m202-d01-support | M202 | train | d01（面积+1%） | 2.02 | 5.1289994884 | 120203.9250481344 |
| g1-m202-d03-query | M202 | train | d03（面积-1%） | 2.02 | 5.2346927295 | 122695.47957091438 |
| g1-m240-d00-support | M240 | test | d00 基准 | 2.4 | 4.4381854595 | 104021.09903911852 |
| g1-m240-d04-query | M240 | test | d04（后掠-0.5°） | 2.4 | 4.4981854595 | 105515.00008485503 |
| g1-m240-d05-query | M240 | test | d05（垂尾+2%） | 2.4 | 4.4381854595 | 104021.09903911852 |

### 3.3 16 条 null 的原因（没有放宽、没有伪造）

- **15 条 AUDIT_FAILED**：准入审计要求极曲线中存在一条真实求解行满足升力相对容差 1e-3。VSPAERO 的 alpha 扫描中，最接近目标升力的原始行相对误差约 0.0015–0.0027，solver_runner 用插值得到 cl，但审计拒绝“插值而非原始行”。没有放宽 1e-3，也没有把插值写成原始行。
- **1 条 NO_RESULT**：g1-m202-d05-query 的启动事件已记录、已计费，但外层运行包装器在 120 s 边界中断，未产生 case_result.json/polar；**不重跑**，永久记为 NO_RESULT。
- 失败/空值全部保留在 tables/failed_or_null.csv 与 tables/null_labels.json，未删除、未改写成成功。

### 3.4 已披露的执行瑕疵

- B01 的 8 个 case 在 A5 修复前执行，0 标签全部保留；B02 只重建未启动的 16 个 case，B01 原始文件不覆盖、不重跑。16/24=66.7% 的上限在任何情况下都低于 70%，因此 G1 从一开始就不能宣称标签率达标。
- B02 首次 --limit 16 被外层 120 s 超时中断，完成 10 个；随后 --limit 6 补齐 M240 6 个。总 starts 仍为 24，没有超过授权。
- 1 个 m202-d05 启动计费但无结果；账本按 24 starts 计，未用“完成数”冒充“启动数”。

## 4. 产物与 GitHub 路径

- 原始/整理数据：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/f0e455f32b70da88f40d32f8be1fbabd649981ab/research/concorde_metaopt/optimization_runs/DRECOVER001-G1-20261121-01
- B02 修复与 A5 文档：同目录 audits/
- 图表目录：同目录 figures/
  - admitted_di_n_by_mach_design.png（只画 8 个有标签点，明确不画 16 个无标签点）
  - batch_outcome_overview.png（24 启动 / 23 完成 / 8 标签 / 15 审计失败 / 1 无结果）
  - figure_data.csv
- 本回执与执行结果：docs/evidence/dreal003/g1/（本文件、g1_execution_result.json、A5 dossier 与 verdict）

## 5. 完整性、SHA256 与远端回读

- G1 包目录：**1023 文件 / 134,572,519 字节**；其中 data_manifest.json 统计 1021 个 payload 文件 / 134,243,569 字节（不含 data_manifest.json 与 SHA256SUMS.txt 两个索引自身）。
- data_manifest.json SHA256：98fe6ab7f6fe302de348204c0e5ffde4342d7e278b35d31c68cbfe673a1c68e5
- SHA256SUMS.txt SHA256：b34213ad65477e9121e89513b987dee5421de459052fa24c5dbd1371738a4100
- 远端回读审计：GitHub recursive tree 对全部 **1023** 个远端 blob 与本地逐字节 Git blob SHA-1 + size 比对，0 mismatch；另从 GitHub 下载 3 个原始文件（admitted_labels.csv、一个 .polar、一张 PNG）重算 SHA256，全部一致；`admitted_identity_bad=[]`；`all_ok=true`。审计 JSON：`docs/evidence/dreal003/g1/remote_g1_retrieval_audit.json`，SHA256 `704e30b7a0990fd1102e6a44f974fada8dffdd40e6513fbc1a06a98655348263`。**未做完整 134MB 重下载**：codeload/zipball 在当前网络下不稳定，因此以远端 Git 对象身份比对 + 3 个原始文件 SHA256 抽查替代，这是本回执的披露限制。
- 数据提交：f0e455f32b70da88f40d32f8be1fbabd649981ab（tree 8734ad57579db1fe981675c43e9f6834fec74396），父提交 9c12e62eda55b3ce22af8310e106e2fe673227d3。
- 上传方式：Git（非 LFS pointer）；原始二进制实际 payload 在仓库中；回读从 GitHub zipball 独立下载并逐文件重算 SHA256，详见审计 JSON。

## 6. 负结果与科学边界

- M160 6 个 case 全部 0 标签：B01 的单一全局 alpha 模型把 M160 目标 alpha 估高约 0.52–0.62°，极曲线最接近点仍超出 1e-3 容差。B02 没有重跑 M160，因为其 8 starts 已消耗；这是预算事实，不是“修好了”。
- 即使 B02 16 个全部成功，累计也只有 16/24=66.7% < 70%；G1 的标签率目标没有达到，不能把 8 条标签当作 G1 成功。
- 同机、无独立存储故障域（Owner 已豁免异机备份，但同机恢复不是备份）；证据范围 LOCAL_RAW_BYTES_VERIFIED_NOT_AUTHENTICATED；physics_validated=false。
- 本阶段没有 MAML 训练、没有 FOMAML/K-shot、没有 BO/DE；这些属于 G2/G3。

## 7. 下一门禁（不是本回执的授权）

G1 → G2 之前必须：
1. 修复 alpha/升力匹配策略，使原始极曲线行能在 1e-3 内命中，或由 A5 预审后明确改变审计策略（不得静默放宽）。
2. 新 G2 authorization_id / batch_id / GO，A5 对 G2 计划与冻结代码预审；G2 上限 240 starts、≥8 任务、每任务 8–10 个去重设计、K=1/3/5。
3. 重新做冻结几何/任务合同与远端回读；不得复用 G1 的 null 为成功，不得覆盖 G1 原始文件。
4. 本回执只报告 G1 事实；**NO_G2_GO**，G3、R2 亦未授权。

## 8. 需要 Owner/上游确认

- 是否接受“G1 标签率 34.78%、未达 70%，因此 G2 暂不放行”，还是先批准一次小规模 alpha/审计策略修复（仅代码与零物理重放，不新增 starts）？
- 修复策略二选一：A）保持 1e-3 并改进 alpha 搜索/扫描密度，使真实行命中；B）由 A5 预审后修改审计定义（例如允许插值但标注插值来源）。我建议 A，B 会改变标签定义，必须单独审查。

文档提交：55284cfc3bafe6bc97e591e8cb04896eab6faffc（tree c2cfd4125bd0d2fc0a645bd9789e34e6694d08a7，父 f0e455f32b70da88f40d32f8be1fbabd649981ab）。G1 数据提交 f0e455f；本回执所在提交只增加 docs/evidence/dreal003/g1/ 三份文档，不改变原始数据。