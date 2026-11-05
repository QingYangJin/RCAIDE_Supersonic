# D-12D-006 / A1 零求解 VSPAERO 审计报告

- 任务：task-191（D12-A1：D-12D-005 Batch1 / Batch1b / Batch2 零求解 VSPAERO 审计）
- 授权：Issue #4 D-12D-006（评论 6647827491，2026-11-05）；保留 VSPAERO_INTERNAL_ONLY、LF-M2.02 = NOT_VALIDATED、BODY-CORR = BLOCKED
- 工作树：<repo-d12d006>；分支 research/d12d006-aero-improvements；HEAD aef2cb71e07aa28abfc28e34b14bf9dc1579c2e3（干净，唯一既有 untracked 为 A2 的 docs/reviews/d12d006_readonly_recompute_20261105.md，本审计未触碰）
- 被审计 run：research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z（下称 RUN）
- 审计人 / 日期：A1 / 2026-11-05
- 审计方式：只读静态解析 + 既有证据复核；零求解、零物理计算
- 证据 JSON：<EXT>/a1/d12d006_vspaero_audit_evidence.json（751556 B，sha256 9b9d1a32f1097392706d820c7876d438e22ef3bc877dfffcedea6c4684acd167）
- 审计脚本：同目录 audit_v2.py（53967 B，sha256 2eab1425d788df77b85dfcc18c31533fac9c996ea5e2503f39b09d8f62c0d6a2）
- 报告文件：docs/reviews/d12d006_vspaero_audit_20261105.md（本文件；不 commit、不 push）
- 路径占位符（入库前清洗，2026-11-05）：<repo>=RCAIDE 仓库根；<repo-d12d006>=D-12D-006 工作树根；<repo-d12d005>=D-12D-005 工作树根；<EXT>=本任务外部记忆目录（对应 d12d006）；<EXT-D12D005>=D-12D-005 外部记忆目录。仅替换主机绝对路径，数值/结论/证据哈希均未变。

## 0. 结论摘要

审计判定：**AUDIT_PASS_WITH_FINDINGS**。D-12D-005 的 14 次 A 类 VSPAERO 7.2.2 执行（Batch1 4 次 + Batch1b 2 次 + Batch2 8 次）在“输入合同 → 执行 setup → 求解器回显 → .polar/.history 原始文件 → 矩阵/报告”这条链上**可复核、可闭合**；未发现伪造、替换或未记录的求解。但本轮发现 **1 项 scope-limited blocker（CG/力矩参考点标签错误）**、**1 项 major（质量基线口径不一致）** 与 6 项 minor/info，均不改变既有 VSPAERO_INTERNAL_ONLY / NOT_VALIDATED 标签，也不支持把内部系数用于整机阻力/航程/配平验证。

1. **证据链完整性 PASS**：data_manifest 513/513 文件 raw + canonical-LF 双形态全部匹配（479 canonical、24 raw-CRLF 提交、10 二进制）；v1 manifest 40/40；external_artifacts 37 项（36 文件 + 1 目录）全部存在且 SHA 匹配。矩阵 14 行与原始 .polar 独立解析、合同 setup、执行 setup、stdout 回显逐项一致（差异 0）。
2. **合同字段 PASS**：14 案 Mach、AoA、Beta、Sref、Cref、Bref、X_cg、ReCref、Vinf、Rho、NumWakeNodes、WakeIters 在合同/执行/回显/极线 5 层一致；12D 生产合同为 Mach 2.02、AoA 2、Sref 358.25 m2、Cref 18.489893 m、Bref 25.604638 m、X_cg 16.821978259514246 m、NumWakeNodes 8、WakeIters 5。
3. **7.2.2 48 列表头解析 PASS（LD-002 影响面封闭）**：24 份生产 .polar 全部为第 3 行表头、恰 48 个 token、单数据行，主系数有限；独立解析值与矩阵 14/14 相等（容差 1e-12）。6 份旧 6.2 表头 .polar 全部位于旧 p1p3 输出目录（<repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/），不在 D-12D-005 证据内；负控制测试 4/4 被 runner 拒绝。
4. **LD-001 setup 格式影响面封闭**：全库扫描 173 份 .vspaero，163 份规范（含生产 48/48），10 份非规范中 3 份为旧 p1p3 产物、7 份为负控制；负控制均被 SetupFormatError 拒绝。D-12D-004 V1 的失败根因是模型路线错误（Uber_eCRM 全机多旋翼模型），不是 LD-001。
5. **CG/力矩参考点（CG-01，blocker，scope-limited）**：合同 X_cg = 16.821978259514246 m 精确等于机翼气动中心 wing_ac_x_m，而非全机 CG（28.287395109126685 m，差 -11.465416849612438 m）。因此 .polar 的 CMxtot/CMytot/CMztot 是绕机翼气动中心的力矩，**不能**用于配平、静稳定裕度或 CG 冻结结论；p1p3 报告 docs/reviews/p1p3_fullchain_validation_report_20261031.md:45 把该值标注为 “PROVISIONAL CG” 属标签错误。该缺陷不改变 CL/CD 的内部趋势有效性。
6. **质量基线（CG-02，major）**：p1p3 报告第 44 行使用 136000 kg，而 geometry-check 模型 research/concorde_metaopt/optimization_runs/geometry-check-p1-20261028T1835/baseline_geometry.json 的 mass_total_takeoff_kg = 184880.0、mass_operating_empty_kg = 78700.0。两套质量口径未统一，任何质量归一化的性能/燃油派生结论必须先冻结基线。
7. **薄面/网格/尾迹/对称 PASS（submitted scope）**：所有案均为薄面 VLM（vkey 全部 thick = 0、plate = 3，仅主翼组件 main_wing_C；stdout NumberOfThinSurfaces_ = 2，两片半翼面；0 Control Surfaces）；尾迹 NumWakeNodes 8 / WakeIters 5 / WakeRelax 1 / FarDist -1 与合同一致；求解器 Symmetry = 0（SYM_NONE），而标准翼几何在 OpenVSP 内以 Sym_Planar_Flag = SYM_XZ 半模镜像成全展（脚本 a0_generate_setups.py:163 与 :175 显式设 Symmetry = SYM_NONE），vspgeom 已含全展，二者自洽。
8. **W10 tip twist PASS（确实施加）**：B2-06 的 vsp3 第 1121 行 Tip Twist = 2.0，B2-03/B2-01/02/04/05/07 该行均为 0；在其余截面参数相同的条件下 B2-06 相对 B2-03 的 ΔCLtot = +1.72227634e-4（+0.2514567165%）、ΔCDi = +2.0717502e-5（+0.8629789120%）、ΔCDtot = +2.1022341e-5（+0.2166196215%）。单案单点，只能证明“已施加、方向合理”，不构成梯度或灵敏度结论。
9. **重复性与数值噪声（单对）**：B2-07 对 B2-03 重复性差 ΔCLtot = -8.3383e-8、ΔCDi = -8.87105e-7、ΔCDtot = -8.86799e-7（相对量约 1e-6）；而 batch2 报告的密度三件套变化达 +2.4372% / -2.7033%（CL），说明该 VLM 数值对自由流状态/单点条件敏感，只能在同一工况内做内部趋势比较。
10. **预算与标签未变**：A 类共 14/20 已用，剩余 6 次关闭不结转；14 次启动均有授权记录、retries = 0；run_config / summary 的 VSPAERO_INTERNAL_ONLY、LF-M2.02 = NOT_VALIDATED、BODY-CORR = BLOCKED、approved_for_next_stage = false 均保持不变。本轮审计未启动任何求解器，未新增 run 目录，未改写任何旧算例。

## 1. 审计范围、授权与零求解声明

### 1.1 范围

- 授权与边界：Issue #4 D-12D-006（评论 6647827491）；继续 VSPAERO 内部线、RCAIDE 回退暂停；保留 VSPAERO_INTERNAL_ONLY、LF-M2.02 = NOT_VALIDATED、BODY-CORR = BLOCKED；内部 CDo/CDtot 不得作为验证整机阻力/燃油目标；本轮不自动批准新数值启动。
- 被审计对象：RUN 下 run_config.json、solver_case_matrix.csv、summary.json、data_manifest.json、vspaero_diagnostics.json、evidence/{v1,v1b,batch2,a0,a0v2}/ 的原始 .vspaero/.vspgeom/.vkey/.csf/.geom_result/.polar/.history/solver_stdout.log、batch2 结果 JSON、以及 docs/reviews 下 batch1/batch2/p1p3 报告；外部执行证据 <EXT-D12D005>/ 与 <repo>/outputs/concorde_metaopt/d12d005-20261104T0430Z/raw_artifacts/。
- 不在范围：任何重新求解、任何几何/网格再生成、任何 VLM/CFD/RCAIDE Mission 调用、任何代码修改、任何 GitHub 写操作。

### 1.2 零求解声明与证据

本报告的全部数字来自**只读文件解析**。执行证据：

- 审计脚本 audit_v2.py 仅使用 Python 标准库（os/json/hashlib/csv/re/glob），不 import OpenVSP、VSPAERO、RCAIDE、SU2 或 Gmsh，不含任何进程启动调用；未调用任何求解器 API。
- 审计结束时 tasklist 查询结果：无 vspaero 进程（中文系统返回“没有运行的任务匹配指定标准”）；证据 JSON zero_solver_evidence.vspaero_running = false、no_solver_process_running = true。
- runner 非物理单测：test_vspaero7_runner_v2.py 58 tests OK、test_vspaero7_runner_v1frozen.py 22 tests OK（tempfile + fake evidence + CLI 子进程 mock，不启动求解器；日志见 <EXT>/a1/logs/）。
- git status（审计前后）：仅 A2 的既有 untracked 报告与本次新增的报告文件；无 commit、无 push、无 stash，未修改任何已有文件。
- 未新增 run 目录、未产生任何 .polar/.history/.adb/.lod 求解产物。

### 1.3 方法

- 独立解析器复写：不 import runner，独立解析 .vspaero（= 分隔符与重复/畸形行分类）、.polar（表头 token 集合与行宽、数据行）、.history（11 个关键字段与迭代行）、geom_result CSV、vkey、csf、vspgeom 头。
- 三方交叉：原始文件 ↔ solver_case_matrix.csv ↔ batch2/batch1 结果 JSON / 报告；并独立重算合同派生量（q、Re、Sref 溯源、CG 恒等式）。
- 完整性校验：按 data_manifest.json 记录的 raw（生成时主机 CRLF 原始字节）与 canonical-LF（提交 blob）两种形态逐文件重算 SHA-256；外部 raw_artifacts 逐文件重算。
- 全库回归扫描：对工作树内全部 173 份 .vspaero、81 份 .polar 做格式分类，区分“生产证据 / 旧 p1p3 证据 / 负控制”。

### 1.4 审计限制（必须随结论一起阅读）

- 本审计**不能**验证 VSPAERO 坐标轴方向与力/力矩符号的物理正确性：仓库内没有独立的坐标系/符号约定验收文件，证据只能证明各环节字段一致，不能证明轴定义正确（见 §4.6，结论 PARTIAL / NOT_ESTABLISHED）。
- 本审计**不能**替代物理验证：不重新求解、不比较风洞/CFD/实验数据，故所有系数仍为 VSPAERO_INTERNAL_ONLY、physical_validation = NOT_VALIDATED、lifting-surfaces-only（仅主翼升力面，无机身/垂尾/翼身干扰）。
- 所有单点极线（每案 1 个数据行）不构成梯度、灵敏度或可重复性统计结论；本文中“差量”只在明确注明的单对比较内成立。

## 2. 证据清单与文件完整性

### 2.1 运行元数据

- run_config.json（8268 B，sha256 b3d9522e2e0245e3a7277476972b0fe9db93b24ea902756c6de8b8962e1da095）：schema d12d005-run-config-1；runner_version d12d005-runner-5；runner_sha256 0c27d05f047d20e9bfc32b4ab27d687c261461b4feb9af5b97247089189f9377（执行时主机 CRLF 形态，见 §2.3）；vspaero.exe 7.2.2 sha256 db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad；serial_only = true、OMP 4、timeout 900 s、max_ram 16 GB；authority_comment_id 6622447995；status A_LINE_CLOSED_VSPAERO_NOT_VALIDATED。
- solver_case_matrix.csv（7138 B，sha256 e09fa6c3e225a0d2778f0e7b08eed74230e42dab27ebe8ae981124bae6f7dbd0）：14 行数据（第 2–15 行）；每行记录 event_id、batch、class、kind、Mach、AoA、Sref/Cref/Bref、NumWakeNodes/WakeIters、CLtot/CDi/CDtot、wall、returncode、outcome、stop_rule、setup_sha256、vspgeom_sha256/bytes/basename、polar/history 状态、label、physical_validation。
- summary.json（13556 B，sha256 6d1b7ebdf2c32d04e32715523ed219e161b01d14b986e9ce7533def9162f92d6）：14 次启动（batch1 4、batch1b 2、batch2 8），retries = 0；gate_status：GEO-12D PARTIAL、LF-M2.02 NOT_VALIDATED、HF-M2.02 PARTIAL、BODY-CORR BLOCKED、MISSION-DATA PARTIAL、BUDGET GATED；approved_for_next_stage = false；fallback NOT_TRIGGERED；SU2 NOT_EXECUTED LOCKED。
- data_manifest.json（204529 B，sha256 4026f4223fe8e6737af5091e8fafec240d197e7f128a989075abe777a74ca0a1）：513 个文件条目、37 个 external_artifacts；checkout_verification 明确 worktree_eol = “mixed: 186 run-dir files are CRLF in the original worktree”、committed_blob_eol = “LF for text files (.gitattributes: * text=auto eol=lf)”。

### 2.2 完整性统计（本审计独立复算）

| 清单 | 总数 | 通过 | 不匹配 | 缺失 |
| --- | --- | --- | --- | --- |
| RUN data_manifest 文件（raw + canonical） | 513 | 513 | 0 | 0 |
| evidence/v1 data_manifest 文件 | 40 | 40 | 0 | 0 |
| external_artifacts | 37 | 36（文件）+ 1（目录） | 0 | 0 |

513 个文件的形态分布：479 个 canonical-LF 匹配；24 个“提交 blob 为 CRLF 但 canonical-LF 内容匹配”（其中 24 个 solver_stdout.log 全部属于此类）；10 个二进制文件按 raw 匹配（.adb 等）。190 个文件的 raw 与 canonical 字节不同，均可用 CRLF/LF 归一化解释，无内容损坏。

### 2.3 SHA 口径（EOL 差异不是缺陷）

D-12D-005 在 Windows 主机上生成，执行时的 .vspgeom / runner / stdout 为 CRLF 原始字节；提交时按仓库 .gitattributes 归一化为 LF。因此同一文件存在两种合法 SHA：

- raw：执行时主机形态，被 run_config、solver_case_matrix、batch2_results 引用（例如 runner_sha256 0c27d05f…、std vspgeom 8363f8fb209dd312… / 284327 B、d12 vspgeom 9fcda6d5d45300fb… / 224357 B）。
- canonical-LF：提交 blob 形态，被 data_manifest.sha256_canonical_lf 记录（例如 runner 45545052106b84ec…、std vspgeom df04690f55d67b1f… / 280615 B、d12 vspgeom 00d937ac656afb79… / 221421 B）。

审计已对 513 个文件同时核验两种形态；另用 <repo>/outputs/concorde_metaopt/d12d005-20261104T0430Z/raw_artifacts/ 下的执行期原始 vspgeom 复核执行 SHA：14/14 与矩阵 vspgeom_sha256 完全一致。字节差（如 284327 − 280615）等于 CRLF 行数，不是几何/内容差异。此点单列为 minor 缺陷 D12D006-EOL-01（记录口径），不影响审计结论。

## 3. 14 案逐案证据链

### 3.1 案矩阵与合同

| 案 | batch | kind | Mach | AoA | Sref m2 | Cref m | Bref m | X_cg m | WakeNodes | WakeIters | contract sha256(16) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0_STD_M0p1_base | batch-1 | std | 0.1 | 2.0 | 4.0 | 1.0 | 4.0 | 0.25 | 8 | 5 | 45c723b6063d5675 |
| S1_STD_M0p1_wn128 | batch-1 | std | 0.1 | 2.0 | 4.0 | 1.0 | 4.0 | 0.25 | 128 | 5 | 3b3acace1d6fe5a5 |
| S2_STD_M0p1_wi0 | batch-1 | std | 0.1 | 2.0 | 4.0 | 1.0 | 4.0 | 0.25 | 8 | 0 | 668c1f4a5f543c5b |
| S3_STD_M2p02_base | batch-1 | std | 2.02 | 2.0 | 4.0 | 1.0 | 4.0 | 0.25 | 8 | 5 | da80fda85e2b4d67 |
| S4_STD_M2p02_wn128 | batch-1b | std | 2.02 | 2.0 | 4.0 | 1.0 | 4.0 | 0.25 | 128 | 5 | f2bbfa6c17ad3e79 |
| S5_D12_M2p02_base | batch-1b | d12 | 2.02 | 2.0 | 358.25 | 18.489893 | 25.604638 | 16.821978259514246 | 8 | 5 | c9cef04e6a6986fd |
| S6_STD_M2p02_aoa1 | batch-2 | std | 2.02 | 1.0 | 4.0 | 1.0 | 4.0 | 0.25 | 8 | 5 | 5a1e69bb298eae3d |
| B2-01 | batch-2 | d12 | 2.02 | 2.0 | 358.25 | 18.489893 | 25.604638 | 16.821978259514246 | 8 | 5 | c9cef04e6a6986fd |
| B2-02 | batch-2 | d12 | 2.02 | 2.0 | 358.25 | 18.489893 | 25.604638 | 16.821978259514246 | 8 | 5 | c9cef04e6a6986fd |
| B2-03 | batch-2 | d12 | 2.02 | 2.0 | 358.25 | 18.489893 | 25.604638 | 16.821978259514246 | 8 | 5 | c9cef04e6a6986fd |
| B2-04 | batch-2 | d12 | 2.02 | 2.0 | 358.25 | 18.489893 | 25.604638 | 16.821978259514246 | 8 | 5 | c9cef04e6a6986fd |
| B2-05 | batch-2 | d12 | 2.02 | 2.0 | 358.25 | 18.489893 | 25.604638 | 16.821978259514246 | 8 | 5 | c9cef04e6a6986fd |
| B2-06 | batch-2 | d12 | 2.02 | 2.0 | 358.25 | 18.489893 | 25.604638 | 16.821978259514246 | 8 | 5 | c9cef04e6a6986fd |
| B2-07 | batch-2 | d12 | 2.02 | 2.0 | 358.25 | 18.489893 | 25.604638 | 16.821978259514246 | 8 | 5 | c9cef04e6a6986fd |

说明：batch1 的 4 案（S0–S3）与 S6 为标准可核对矩形翼（AR = 4、Sref = 4、Cref = 1、Bref = 4、X_cg = 0.25 作为力矩参考点），用于验证设置族与解析器；S5 与 B2-01…B2-07 为 12D 主翼（Sref 358.25/Cref 18.489893/Bref 25.604638/X_cg 16.821978259514246）。S1/S4 的 NumWakeNodes = 128、S2 的 WakeIters = 0、S6 的 AoA = 1 是**协议内单因素敏感性/验证案**，不违反 12D 生产合同；12D 生产合同（S5/B2）均为 NumWakeNodes 8、WakeIters 5、AoA 2。S3 的矩阵 outcome 为 FAILED_INVALID_POLAR（运行时旧解析器把派生列 Ew = inf 当非有限值而停批），但其主系数有限，rev5 allowlist 重读为 PASS_WITH_WARNINGS（§6.3）；该差异在矩阵中保留原运行值时点状态，不构成数据矛盾。

### 3.2 原始 .polar/.history 与实际系数

| 案 | polar sha256(16) | history sha256(16) | CLtot | CDi | CDtot | CMytot | matrix outcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S0_STD_M0p1_base | 920ae8c9e341373e | 9a9422b5dccf2add | 0.126545398398 | 0.001314258293 | 0.020946562364 | 0.005134520432 | SOLVED_VALID |
| S1_STD_M0p1_wn128 | f54d81d2ec3792bd | c06a3f25d3741a1f | 0.134634955743 | 0.001522504678 | 0.021167612993 | 0.003123686783 | SOLVED_VALID |
| S2_STD_M0p1_wi0 | 65087b8cff3d0297 | eadea4af1d67b873 | 0.126555050502 | 0.001314544617 | 0.020946858130 | 0.005138311266 | SOLVED_VALID |
| S3_STD_M2p02_base | 61e49c249d611cce | e8ed6e8b5369c6f2 | 0.074251031783 | 0.002606540227 | 0.013789407924 | -0.014777040022 | FAILED_INVALID_POLAR |
| S4_STD_M2p02_wn128 | a78a33ee500cc9f8 | 48f2692c359a02d6 | 0.074250958215 | 0.002606535876 | 0.013789403504 | -0.014776993867 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| S5_D12_M2p02_base | 5842830cf4faa097 | e149acdfeee75d9c | 0.070832611794 | 0.002488240979 | 0.009796560997 | -0.019446218970 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| S6_STD_M2p02_aoa1 | 7d384e69941c9ec9 | aa17e4d6e696fd9c | 0.037164223289 | 0.000652721593 | 0.011813972653 | -0.007348237833 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| B2-01 | 4aeb47fc84e72f17 | 7ef752fcca22efa7 | 0.068720123506 | 0.002408676841 | 0.009720832617 | -0.018418348760 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| B2-02 | e080fd65b11cfdca | 1aa22130db379ad7 | 0.070394960019 | 0.002467158219 | 0.009775137856 | -0.019363091256 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| B2-03 | 3fa9af027ae4bc47 | 306049f597d583a9 | 0.068491960121 | 0.002400696206 | 0.009704726125 | -0.018563127748 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| B2-04 | 39d213c9aaa40d31 | 5496b75cfc7fdfd6 | 0.071941629767 | 0.002521957494 | 0.010164783208 | -0.021611409887 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| B2-05 | 1b86475b0fbfdbec | db74715ddc4790cc | 0.067018850290 | 0.002349255361 | 0.009652284430 | -0.022290135972 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| B2-06 | 9bd645e3d3bee3b9 | fed094042061ef6a | 0.068664187755 | 0.002421413708 | 0.009725748466 | -0.018671664135 | SOLVED_VALID_WITH_DERIVED_WARNINGS |
| B2-07 | 99702bbfaf2eed0b | 46b7ef3d5cbbf83b | 0.068491876738 | 0.002399809101 | 0.009703839326 | -0.018562783568 | SOLVED_VALID_WITH_DERIVED_WARNINGS |

- 14 案独立解析的 CLtot/CDi/CDtot 与 solver_case_matrix.csv 对应列完全一致（最大绝对差 < 1e-12，数值按 12 位小数打印）。
- 每案 .polar 均为 1 个数据行（单点极线），无缺行、无坏行；主系数（CLo/CLi/CLtot/CDo/CDi/CDtot/CMxtot/CMytot/CMztot）全部有限。
- Ew = inf 出现在 6 个 12D 案（S5、B2-01…07）以及 S3/S4：由 CDiw = 0 导致除零，属派生列；runner rev4 起 allowlist 仅允许派生列 Ew 非有限（POLAR_DERIVED_NONFINITE_COLUMNS），主系数非有限仍会 fail-closed。
- .history 每案含 11 个关键字段（Sref_/Cref_/Bref_/Xcg_/Ycg_/Zcg_/Mach_/AoA_/Beta_/Rho_/Vinf_）与 5 行迭代（S2 因 WakeIters = 0 只有 1 行），末行 CLtot 与 .polar 数据行一致。
- batch2 案同时存在 bundle 与 results 两份 .polar/.history，内容 SHA 相同（互为副本）；batch1b 同理。因此 24 份生产 .polar 即 12 个不同求解结果 × 2 份存储副本。

### 3.3 矩阵 ↔ 合同 ↔ 执行 setup ↔ 回显 一致性

- setup_sha256：14/14 与合同 setup 文件 SHA 相等，且 batch1 案与 evidence/a0/setup_gen/<case>/<case>_contract.vspaero 的 SHA 相等；12D 案（S5/B2）合同 SHA 均为 c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64，S6 为 5a1e69bb298eae3d…。
- 12D 案的执行 setup（外部 bundle 内 wing355_baseline.vspaero）与仓库内合同逐字段相等（41 行规范 “ = ” 格式，legacy = 0、malformed = 0），且 SHA 与合同相同；batch1 的执行 setup 位于 <EXT-D12D005>/a2/bundles/<case>/，SHA 与合同相同。
- 求解器 stdout 回显与合同一致：Sref/Cref/Bref/X_cg/Mach/AoA/Beta/Vinf/Rho/ReCref/Symmetry/FarDist/NumWakeNodes/WakeIters 全部在 1e-6 相对/绝对误差内（历史与极线的 Re/Mach 更严）。
- 注意：evidence/a0/setup_gen/ 下的 <case>_model.vspaero 对 std 案保留 VSPAERO 默认 Vinf = 100 / Rho = 0.002377 / ReCref = 1e7，这是 A0 生成模板（runner DEFAULT_LEAK_FIELDS 监控对象），**不是**执行 setup；执行 setup 已由 inject_contract_fields 注入合同值（外部 bundle 实测正确）。审计据此判定不存在“默认值泄漏进入执行”。

## 4. 合同字段逐项核验（Mach / AoA / CG / Sref）

### 4.1 Mach、AoA、Beta、Re、Vinf、Rho

- 12D 生产合同（run_config.json frozen_contract）：Mach 2.02、AoA 2.0、Beta 0、alt 18288 m、q 20483.94 Pa、T 216.65 K、p 7171.544888 Pa、rho 0.1153178340089936 kg/m3、V 596.0373972278921 m/s、ReCref 89397005.8767656、Sref 358.25、Cref 18.489893、Bref 25.604638。
- 每一份 12D 执行 setup 的 Mach/AoA/Beta/ReCref/Vinf/Rho 与合同一致（逐文件核对 41 行 setup）；.polar 数据行与 .history 的 Mach/AoA/Beta/Re 与合同一致（Re/1e6 = 89.397005876766）；stdout 回显一致（S5 bundle solver_stdout.log:60-61 等）。
- 标准翼案（S0–S4、S6）合同为 M0.1 或 M2.02、Sref 4/Cref 1/Bref 4/Xcg 0.25，各自执行 setup 与回显一致。
- 判定：PASS（合同 → 执行 → 求解器 → 原始文件 5 层一致；runner 另有 17 字段 readback 断言与 DEFAULT_LEAK_FIELDS 检查，见 vspaero7_runner_v2.py:426-511、:535-565）。

### 4.2 Sref、Cref、Bref 溯源

- Sref = 358.25 m2：design_space_12d_lifting_surfaces.yaml:156 的 main_wing.exposed_area_m2 = 358.250000；同时 W01 的 baseline = 358.25、target = main_wing.areas.reference（yaml:29-33）。**358.25 是参考/暴露面积，不是浸润面积**；浸润面积在 yaml:155 为 717.574750，且 yaml:204-205 的派生规则为 sum(2.003 × exposed_segment_area)（厚度比 0.03 < 0.05），所以两者不可混用。
- Cref = 18.489893 m = 机翼平均气动弦长（yaml:154 mean_aerodynamic_chord_m = 18.489893；baseline_geometry.json wing_mac_m = 18.489892944055953）。
- Bref = 25.604638 m = 投影半展 × 2（yaml:150 projected_span_m = 25.604638；baseline_geometry.json wing_span_m = 25.604638251691824）。
- 上游声明差异（yaml:181-193 upstream_declared）：root_chord_m 33.8、wetted_area_m2 601.0、exposed_area_m2 326.5、vertical_stabilizer.projected_span_m 6.0、fuselage.wetted_area_m2 442.0、front_projected_area_m2 11.9，与本模型（root 29.901819、wetted 717.574750、exposed 358.25、vertical span 5.009331、fuselage wetted 488.922167、front 7.509665）不一致；owner 2026-10-30 决策采用模型计算值（yaml:127-146 F01–F03 的 source 字段），上游值仅留作追溯。
- 判定：PARTIAL。Sref/Cref/Bref 与 12D 模型、合同、VSPAERO 回显自洽；但 upstream_declared 与模型值差异（尤其 exposed 326.5 vs 358.25，翼身遮挡未建模）未在气动上解释，属已知风险而非本轮可解决项（不得据此声称整机阻力已验证）。

### 4.3 CG 与力矩参考点（CG-01，blocker，scope-limited）

证据链：

- 合同与执行：run_config.json frozen_contract.x_cg_m = 16.821978259514246；所有 12D 案 setup X_cg = 16.821978259514246、Y_cg = Z_cg = 0；stdout 回显 X_cg = 16.821978；history Xcg_ = 16.8219783（S5、B2-01…07）；std 案为 0.25。
- 几何模型：research/concorde_metaopt/optimization_runs/geometry-check-p1-20261028T1835/baseline_geometry.json 中 cg_x_m = 28.287395109126685、wing_ac_x_m = 16.821978259514246、static_margin = 0.13707938483236962；代码 research/concorde_metaopt/aircraft/geometry_model.py:681 wing_ac_x = WING_ORIGIN_X_M + wing.aerodynamic_center_x_m、:680 cg_x = sum(masses * positions) / total_mass、:645 wing_cg = WING_ORIGIN_X_M + 0.45 * root_chord、:378 mass, cg_x, static_margin = _provisional_mass_and_cg(...)。
- 精确性：合同 X_cg 与 wing_ac_x_m 的差为 0（float 级相等），与 cg_x_m 的差为 -11.465416849612438 m。
- 旁证：p1p3 脚本 research/concorde_metaopt/scripts/make_hfs_cfg.py:18 XAC = 16.821978259514246、:31 REF_ORIGIN_MOMENT_X= {xac}；make_drag_component_ledger.py:83 moment_reference_x_m = 16.821978259514246。即 p1p3 全链路的“力矩参考点”统一取机翼气动中心，这是**参考点**语义，而不是 CG。
- 报告标签错误：docs/reviews/p1p3_fullchain_validation_report_20261031.md:45 写 “moment reference x = 16.821978259514246 m (PROVISIONAL CG, y = z = 0)”，把参考点标为 CG，属错误标签。

影响与判定：

- .polar 的 CMxtot/CMytot/CMztot 是绕 X_cg 的力矩；由于 X_cg 实际为机翼气动中心，这些力矩**不能**用于配平/静稳定/全机 CG 相关结论，也不能与全机 CG 28.287395 直接组合。
- 该缺陷限定于“参考点/标签/派生用途”，不影响 CLtot/CDi/CDtot 本身及同工况内部趋势比较；不改变 VSPAERO_INTERNAL_ONLY / NOT_VALIDATED 标签。
- 判定：BLOCKER（scope-limited）——任何配平/静稳定/质量-重心耦合任务在修复前不得使用该力矩系数；建议新增独立任务卡：明确“力矩参考点 = 机翼 AC”为工程约定，或用真实 CG 重新生成合同（需 owner 授权，且会消耗新求解预算，本轮不做）。

### 4.4 质量基线（CG-02，major）

- p1p3 报告 docs/reviews/p1p3_fullchain_validation_report_20261031.md:44 使用 136000 kg。
- geometry-check 模型 baseline_geometry.json：mass_total_takeoff_kg = 184880.0、mass_operating_empty_kg = 78700.0。
- 影响：以 136000 kg 推导的推重比、燃油、航程类结论与 184880 kg 口径不可混用；D-12D-005 的气动系数不含质量，本身不受影响，但任何质量归一化/任务派生比较必须先把质量基线冻结到 TaskSpec。
- 判定：MAJOR（口径风险，非求解错误）；建议随 CG-01 同一任务卡解决。

### 4.5 自由流热力学一致性（ATMOS-01，minor）

- 内部自洽：用合同 rho = 0.1153178340089936、V = 596.0373972278921 复算 q = 0.5·rho·V²，与合同 q = 20483.94 的相对差 1.140e-8；Re = rho·V·Cref/μ（μ = 1.42161308e-05）与合同 ReCref = 89397005.8767656 的相对差 2.523e-10。PASS。
- 独立推导：用理想气体 R = 287.05287、T = 216.65、p = 7171.544888 反算 rho = 0.11531668103891886（相对差 9.998e-6）、V = 596.0403768883244（4.999e-6）、a = 295.0694935090715（合同 295.0680184）、Re 相对差 4.999e-6。属合同常数来源/大气模型未在仓库内独立溯源的 minor 项，不影响一致性判定。
- 判定：PASS（内部自洽）+ MINOR（外部溯源）。

### 4.6 坐标系与力/力矩符号（NOT_ESTABLISHED）

- 仓库内未找到独立的“VSPAERO 坐标系/力符号”验收文件；本轮只能确认：.vspaero 中 X_cg/Y_cg/Z_cg、Sref/Cref/Bref 与回显/极线/历史一致，且 std 案 X_cg = 0.25、12D 案 X_cg = 16.821978 的语义已由 §4.3 澄清。
- 无法从证据判断 X 轴指向（机头/机尾）、升力/阻力正方向、CM 正负号是否与项目约定一致；这需要外部文档或独立验证（例如与已知符号的解析算例对照），**本轮不做**。
- 判定：PARTIAL / NOT_ESTABLISHED。本报告所有 CL/CD/CM 结论均不依赖符号方向的物理解释，只依赖“同一求解器、同一设置下的内部趋势”；任何符号相关的物理结论必须等符号约定冻结后再下。

## 5. 薄面模型、几何、网格、尾迹与对称

### 5.1 薄面（thin surface）设置

- 生成脚本 research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/a0_generate_setups.py 在 VSPAEROComputeGeometry / VSPAEROSweep 上设 GeomSet = SET_NONE、ThinGeomSet = SET_ALL、Symmetry = SYM_NONE、RefFlag = MANUAL_REF、MACFlag = 0，并按合同注入 Sref/cref/bref/Mach/AoA/Beta/Xcg/Ycg/Zcg/NumWakeNodes/WakeNumIter/WakeRelax/FarDist；StopBeforeRun = 1 仅生成 setup。
- 证据 1（CSV 枚举）：bundle/geom_result_thin.csv 记录 GeometrySet = -1、ThinGeometrySet = 0；对照 OpenVSP API，SET_NONE = -1、SET_ALL = 0，与脚本设置一致。
- 证据 2（vkey）：bundle/<name>.vkey 第 1 行为 “# VSPGEOM v3 Tag Key File”，第 2 行为生成机绝对路径；组件表 2 个面元行 gname = main_wing_C、thick = 0、plate = 3（薄面），无其他组件。
- 证据 3（solver stdout）：S5 bundle solver_stdout.log:133/139 “Surface: 1 is thin”“Surface: 2 is thin”、:145 NumberOfThinSurfaces_: 2、:200 NumberOfWakeTrailingNodes_: 8；每案均有等价记录。
- 证据 4（csf）：bundle/<name>.csf 精确内容为 “0 Control Surfaces”。
- 证据 5（vspgeom 头）：bundle/<name>.vspgeom 第 1–3 行 “# vspgeom v3”、组件数 1、节点/面计数（S5 为 527 480 1）；仅主翼组件，**无机身、无垂尾、无翼身干扰** → 与 lifting-surfaces-only 声明一致。
- 判定：PASS（薄面模型、无控制面、仅主翼升力面）。

### 5.2 vspgeom 与执行 SHA

- 每案执行期 vspgeom（外部 raw_artifacts）与矩阵 vspgeom_sha256/vspgeom_bytes 完全一致；提交到仓库 bundle 的 vspgeom 为 canonical-LF 形态，字节数与 SHA 不同（CRLF/LF 差异），但 data_manifest 同时记录 raw 与 canonical，且审计对 513 文件双形态校验全部通过（§2.3）。
- batch1 案（S0–S3）的 bundle 内没有提交 vspgeom（执行用外部 raw），审计以矩阵记录 + 外部 raw_artifacts 复核；batch1b/batch2 案有提交 canonical vspgeom。
- 注：solver_case_matrix.csv 的 vspgeom_basename 列对 S0–S5 记录的是 “vspaero.exe -omp 4 <name>.vspgeom”（把 OpenVSP 命令行回显当文件名），S6/B2 记录正确文件名；这是元数据缺陷 D12D006-MATRIX-01（minor），不影响 SHA/bytes 列。

### 5.3 网格

- 标准翼（S0–S4、S6）：A0 用 AddGeom('WING') 自建米制矩形翼，SectTess_U = 20（a0 README §4；驱动组 SPAN_WSECT_DRIVER/TAPER_WSECT_DRIVER/ROOTC_WSECT_DRIVER），Sym_Planar_Flag = SYM_XZ（半模镜像后全展），NACA 4-series 厚度 0.10（VLM 只取中弧线，等价平板）。
- 12D 主翼（S5/B2）：由 a0v2 生成/复制 wing355_baseline 几何，各案 SectTess_U 与截面参数按设计变量生成；不同案 vspgeom 尺寸不同（B2-01 raw 89427 B、B2-02/S5 raw 224357 B、B2-03…B2-07 raw 495690 B），审计只核验“执行文件 SHA = 矩阵记录”，不重新生成几何。
- 判定：PASS（就“同一份被 SHA 锁定的几何”而言）；几何本身是否物理正确（翼型、扭转、表面质量）不在本轮范围。

### 5.4 尾迹

- 合同：NumWakeNodes = 8、WakeIters = 5、WakeRelax = 1.0、FarDist = -1.0；stdout 回显 :27 “Setting NumWakeNodes to: 8”、:28 “Setting WakeIters to: 5”、:60-61 回显 8/5；FarDist = -1 由求解器自动换算，S5 日志记录 “Wake FarFieldDist_ set to: 31.495344”。
- 敏感性案：S1（M0.1）与 S4（M2.02）NumWakeNodes = 128；S2（M0.1）WakeIters = 0（history 仅 1 行迭代）。三者均为协议内单因素对照，用于 std 翼的设置族行为判断；12D 生产案不使用这些偏离值。
- 判定：PASS（合同值与回显一致，偏离均有记录）。

### 5.5 对称性

- 求解器 Symmetry = 0（SYM_NONE）：a0_generate_setups.py:163 对 VSPAEROComputeGeometry、:175 对 VSPAEROSweep 显式设 vsp.SYM_NONE；全部 setup/回显一致为 0。
- 几何侧：标准翼用 Sym_Planar_Flag = SYM_XZ 半模建模，镜像后全展（a0 README §4 实测 TotalSpan = 4、TotalArea = 4）；vkey 有 2 个面元行（两片半翼），stdout “NumberOfThinSurfaces_: 2”，说明求解器看到的是全展几何。两者自洽（几何已镜像全展，因此求解器无需对称假设）。
- 判定：PASS（内部自洽）。是否应改用 solver 对称减半以节省算力属优化建议，不在本轮范围。

## 6. 7.2.2 48 列表头与解析器（LD-002）

### 6.1 表头结构

D-12D-005 生产 .polar（24 份）全部为 VSPAERO 7.2.2 输出形态：

- 第 1 行为分组标签（Surface Integration Forces and Moments --> 等）；
- 第 2 行为超长 Surf-Surf 标签；
- 第 3 行为 48 列 token：Beta Mach AoA Re/1e6 CLo CLi CLtot CDo CDi CDtot CSo CSi CStot L/D E CMox CMoy CMoz CMix CMiy CMiz CMxtot CMytot CMztot CFox CFoy CFoz CFix CFiy CFiz CFxtot CFytot CFztot CLwtot CDwtot CSwtot CLiw CDiw CSiw CFwxtot CFwytot CFwztot CFiwx CFiwy CFiwz LoDw Ew StallFactor；
- 第 4 行为单数据行（每案单点）。
- runner 硬编码 POLAR_722_COLUMNS（vspaero7_runner_v2.py:115-124）与 POLAR_DERIVED_NONFINITE_COLUMNS = ("Ew",)（:131），并要求表头恰为第 3 行、token 集合与顺序完全一致，否则 fail-closed（:601-668、:685-780）。

### 6.2 全库扫描与影响面

- 工作树内 81 份 .polar：75 份为 7.2.2 48 列第 3 行表头；6 份为旧 6.2 表头，全部位于旧 p1p3 输出 <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/（baseline、sens_coarse、sens_fine、w01_plus1pct、w03_plus1deg、w10_plus2）。生产 .polar 24/24 合规，production_bad = []。
- 6 份旧 6.2 极线（表头列为 Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E，20 列）被 runner 识别为 POLAR_LEGACY_62_HEADER_REJECTED 并拒绝；负控制测试 4/4 通过（含旧 setup 与旧 polar 两类）。
- 影响面结论：LD-002 缺陷只影响历史 p1p3 输出与负控制样本，**未污染 D-12D-005 生产证据**；旧 p1p3 的 6 份极线结论不得与 D-12D-005 混用。

| 文件 | 表头形态 |
| --- | --- |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/baseline/main_wing_baseline_DegenGeom.polar | 旧 6.2 表头 20 列（Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E） |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/sens_coarse/main_wing_sens_coarse_DegenGeom.polar | 旧 6.2 表头 20 列（Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E） |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/sens_fine/main_wing_sens_fine_DegenGeom.polar | 旧 6.2 表头 20 列（Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E） |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/w01_plus1pct/main_wing_w01_plus1pct_DegenGeom.polar | 旧 6.2 表头 20 列（Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E） |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/w03_plus1deg/main_wing_w03_plus1deg_DegenGeom.polar | 旧 6.2 表头 20 列（Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E） |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/w10_plus2/main_wing_w10_plus2_DegenGeom.polar | 旧 6.2 表头 20 列（Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E） |

### 6.3 S3 的状态沿革（D12D006-S3-01，minor）

- 运行时（batch1）解析器尚未 allowlist 派生列，S3 的 Ew = inf 触发 POLAR_NONFINITE → 停批，矩阵记 outcome = FAILED_INVALID_POLAR、verify_polar_status = FAIL_NONFINITE_DERIVED_COLUMN、stop_rule_hit = stop_rule_1_nonfinite_IND_INF。
- rev4/rev5 将主系数与派生列分离，仅允许 Ew 非有限（allowlist），重读 S3 为 PASS_WITH_WARNINGS；batch1b 的 S4 与 S3 对比即基于此修复。
- 现状：矩阵保留运行时值、报告记录修复后重读值，两者并存但有明确沿革说明；建议后续在矩阵中增加 “re-read status” 列（minor 改进，不阻塞）。

## 7. LD-001 setup 格式缺陷影响面

- 规范格式：VSPAERO setup 每行 “key = value”。runner 的 parse_setup_text（vspaero7_runner_v2.py:233-279）区分 equals/legacy/malformed/vector/duplicate，assert_canonical（:293-310）对 legacy 行（无 “ = ”）抛 SetupFormatError；normalize_legacy_text 仅供显式迁移（:313-347）。
- 生产证据：48 份 D-12D-005 相关 .vspaero 全部规范（legacy = 0、malformed = 0），包括 14 案合同、执行 setup、a0/a0v2 setup_gen 与负控制之外的模板；production bad = []。
- 全库扫描：173 份 .vspaero 中 163 份规范、10 份非规范：3 份旧 p1p3 产物（p1p3-fullchain-20261031T0407Z/lf_raw/ 下的 w01_plus1pct/w03_plus1deg/w10_plus2 等 legacy 文件）+ 7 份负控制 neg_legacy.vspaero（a0 S0/S3、a0v2 B2-03、d12d004 v0/setup_gen、外部 lead relocate_test 与 a2 prestart_verification 副本）。全部非规范文件均被 runner 拒绝（SetupFormatError: LD-001 legacy lines without '='），负控制 4/4 通过。

| 文件 | legacy 行（无 '='） | 归类 |
| --- | --- | --- |
| <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d004-vspaero72-lf-20261102T0500Z/evidence/v0/setup_gen/neg_legacy.vspaero | L1: Mach 2.02; L2: Sref 358.25 | 负控制（应拒绝，已拒绝） |
| <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/a0/negative_controls/S0_STD_M0p1_base/neg_legacy.vspaero | L1: Sref 4.0; L2: Mach 0.1 | 负控制（应拒绝，已拒绝） |
| <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/a0/negative_controls/S3_STD_M2p02_base/neg_legacy.vspaero | L1: Sref 4.0; L2: Mach 0.1 | 负控制（应拒绝，已拒绝） |
| <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/a0v2/negative_controls/B2-03/neg_legacy.vspaero | L1: Sref 4.0; L2: Mach 0.1 | 负控制（应拒绝，已拒绝） |
| EXT/d12d005/a2/prestart_verification/work/regenerated_a0v2/negative_controls/B2-03/neg_legacy.vspaero | L1: Sref 4.0; L2: Mach 0.1 | 负控制（应拒绝，已拒绝） |
| EXT/d12d005/lead/relocate_test/run/evidence/a0/negative_controls/S0_STD_M0p1_base/neg_legacy.vspaero | L1: Sref 4.0; L2: Mach 0.1 | 负控制（应拒绝，已拒绝） |
| EXT/d12d005/lead/relocate_test/run/evidence/a0/negative_controls/S3_STD_M2p02_base/neg_legacy.vspaero | L1: Sref 4.0; L2: Mach 0.1 | 负控制（应拒绝，已拒绝） |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/w01_plus1pct/main_wing_w01_plus1pct_DegenGeom.vspaero | L1: Sref 358.25; L2: Cref 18.489893; L3: Bref 25.604638 | 旧 p1p3 产物（不可引用） |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/w03_plus1deg/main_wing_w03_plus1deg_DegenGeom.vspaero | L1: Sref 358.25; L2: Cref 18.489893; L3: Bref 25.604638 | 旧 p1p3 产物（不可引用） |
| <repo>/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/w10_plus2/main_wing_w10_plus2_DegenGeom.vspaero | L1: Sref 358.25; L2: Cref 18.489893; L3: Bref 25.604638 | 旧 p1p3 产物（不可引用） |

- 影响面结论：LD-001 缺陷仅影响历史 p1p3 与负控制，D-12D-005 生产 setup 全部规范；inject_contract_fields（:535-565）先 normalize 再写入并回读（read_setup_file require_canonical = true），require_setup_success（:568-586）保证非 0 返回码/空 setup 直接失败。D-12D-004 V1 的失败根因是模型路线错误（Uber_eCRM 全机多旋翼模型，uber2.vsp3 sha256 87ab38dce4f1b4e2c2ae9bab214876f3be3e1a5459ab7463cea2f6098436318d、vspgeom 2019343 B），不是 LD-001（见 evidence/a0/vspaero_v1_divergence_analysis.json 的 F-A0-01…F-A0-04）。

## 8. 矩阵、报告与原始文件的交叉核对

- 14 案矩阵列 Mach/AoA/Sref/Cref/Bref/NumWakeNodes/WakeIters 与合同 setup 逐字段相等；CLtot/CDi/CDtot 与独立解析的 .polar 数据行相等（< 1e-12）；setup_sha256 与合同 SHA 相等；vspgeom_sha256/bytes 与执行 raw 相等。
- batch2 的 results/coefficients.json primary_values 与 .polar 数据行一致（例：B2-06 CLtot 0.068664187755、CDi 0.002421413708、CDtot 0.009725748466、CMytot -0.018671664135）；prestart_gate.json 15 项 checks 全 true（auth/exe/HEAD/无其他 vspaero 进程/stop_before_run = 1/evidence_zero_solver_started/pc09/contract/csf/setup_sha/vkey_local/check_case_dir/readback_17/all_pass）。
- batch2 final_checks.json：36/36 checks all_pass = true；预算分类 A 类 14/20、剩余 6（关闭不结转）、batch2 本轮 8 次、retries = 0；summary 与 matrix、ledger 一致。
- batch1/batch2 报告引用值与原始文件一致：S3 的 Ew = inf 与主系数有限（batch1 报告 :14/:30）；S4–S3 差 CLtot -7.3568e-08 / CDi -4.351e-09（:146）；batch2 密度三件套 ΔCL +2.4372%（3/3→6/6）与 -2.7033%（6/6→12/12）（batch2 报告 :66-69）；W10 单因素 +0.2515%（:79）；重复性（:89）。
- 结论：无“报告数字无原始依据”的项；矩阵/报告/JSON/原始文件四方闭合。

## 9. W10 tip twist 核查

- 定义：configs/design_space_12d_lifting_surfaces.yaml:101-108 定义 W10 tip_twist，baseline 0.0，范围 [-4, 4]，目标 main_wing.segments.tip.twist；aircraft/geometry_model.py:350 将 tip_twist 写入第 4 个截面的 twist_deg = (0.0, 0.0, 0.0, values["tip_twist"])。
- 施加证据：scripts/a0_generate_setups_v2.py:105-106 中 B2-06 的设计为 {"tip_twist": 2.0}；B2-06 的 bundle/wing355_baseline.vsp3:1121 为 Twist Value = 2.000000000000000000e+00，而 B2-03 同路径 :1121 为 0（其余 3 个 Twist 行 605/777/949 均 0）；B2-01/02/04/05/07 全 0。审计独立解析 14 份 vsp3，仅 B2-06 有非零 twist。
- 量化（B2-06 相对 B2-03，其余截面参数相同的单因素对照）：ΔCLtot = +1.72227634e-4（+0.2514567165%）、ΔCDi = +2.0717502e-5（+0.8629789120%）、ΔCDtot = +2.1022341e-5（+0.2166196215%）。
- 解读与限制：W10 确实被施加，且方向/量级与 tip 扭转增加局部有效迎角一致；但只有 1 个 +2° 单点、单次运行，不能据此给出导数/梯度/灵敏度区间，也不能外推到 -4°/0°/+4°。建议后续（新预算、单独授权）用 3–5 个 twist 点重复扫描，并报告重复性。
- 判定：PASS（施加性核查通过）；灵敏度结论 NOT_AVAILABLE。

## 10. 重复性与数值噪声

- 同几何重复性（唯一一对）：B2-07 对 B2-03（同 12D 合同、同 AoA、同几何）ΔCLtot = -8.3383e-8、ΔCDi = -8.87105e-7、ΔCDtot = -8.86799e-7；CL 相对量约 1.2e-6。说明同工况单次求解的数值噪声远小于物理量级。
- 设置扰动：S4（NumWakeNodes 128）对 S3（NumWakeNodes 8）ΔCLtot = -7.3568e-8（相对 -9.908e-7）等（batch1 报告 :146），说明该设置族对尾迹节点数不敏感（单对）。
- 自由流状态：batch2 密度三件套 3/3→6/6 的 ΔCL +2.4372%（相对 CDi +2.4279%、CDtot +0.5586%），6/6→12/12 的 ΔCL -2.7033%（CDi -2.6939%、CDtot -0.7203%）；同一密度重复 12/12→12/12 的差为 0 量级。说明该 VLM 的 CL/CDi 对密度（Re 标定）有约 2.7% 量级的状态敏感性。
- 结论：只能做“同一合同状态、同一几何”的内部趋势比较；跨状态（密度/Re/马赫）比较必须重新给定合同并标注为不同状态，不能把 2.7% 量级的状态变化当成设计灵敏度。

## 11. 缺陷与风险清单

| ID | 级别 | 标题 | 影响 | 建议 |
| --- | --- | --- | --- | --- |
| D12D006-CG-01 | blocker（scope-limited） | 合同 X_cg = 16.821978259514246 实为机翼气动中心，非全机 CG（28.287395109126685） | CMxtot/CMytot/CMztot 不能用于配平/静稳定/CG 冻结；p1p3 报告 :45 标签错误 | 新增“力矩参考点/质量基线”任务卡，冻结参考点语义；修复前禁止相关派生结论 |
| D12D006-CG-02 | major | p1p3 报告 136000 kg 与 geometry-check 模型 184880 kg（OEW 78700 kg）质量口径不一致 | 质量归一化/燃油/航程派生结论不可混用 | 与 CG-01 同卡冻结质量基线 |
| D12D006-MATRIX-01 | minor | solver_case_matrix.csv 的 vspgeom_basename 对 S0–S5 记录命令行回显 | 元数据可读性/自动处理风险 | 下次生成矩阵时取真实文件名；或增加独立 basename 校验 |
| D12D006-EOL-01 | minor | raw(CRLF) 与 committed-LF 双形态，矩阵/SHA 记录口径混用 | 人工核对易误判为 SHA 不匹配 | 报告与矩阵注明 raw/canonical 口径；data_manifest 已给出双哈希 |
| D12D006-PATH-01 | minor | vkey 第 2 行与 geom_result_thin.csv 的 VSPGeomFileName 保留生成机绝对路径 <repo-d12d005>\… | 可移植性/复现路径依赖 | 归档时保留并注明，或提供相对路径清单 |
| D12D006-S3-01 | minor | S3 矩阵记为 FAIL_NONFINITE_DERIVED_COLUMN，rev5 重读为 PASS_WITH_WARNINGS | 状态歧义 | 矩阵增加 re-read status 列，注明修复时点 |
| D12D006-ATMOS-01 | minor | rho/V/a/Re 无仓库内独立推导；理想气体复算差 ~1e-5 | 自由流常数来源不可独立追溯 | 记录大气模型来源；在合同文件中固化推导 |
| D12D006-SOLVER-STD-01 | info | 本轮零求解；仅 mock 单测 58 + 22 通过 | 无 | 保持；下轮求解仍需新授权 |

## 12. 结论与放行建议

1. **证据链与合同一致性**：PASS。D-12D-005 的 14 次 A 类执行在“合同 → 执行 setup → 求解器回显 → .polar/.history → 矩阵/报告”上完整闭合；513 + 40 文件双形态 SHA 全匹配；14/14 案矩阵与原始极线一致。
2. **解析器（LD-001/LD-002）**：PASS（影响面封闭）。生产证据全部规范/48 列合规；6 份旧 6.2 极线与 10 份非规范 setup 全部位于旧 p1p3 或负控制；负控制 4/4 拒绝。
3. **薄面/尾迹/对称/lifting-surfaces-only**：PASS（内部自洽）。仅主翼薄面、无控制面、无机身/垂尾/翼身干扰；12D 生产合同尾迹 8/5/1/-1；solver Symmetry = 0 与几何全展自洽。
4. **CG/力矩参考点与质量基线**：存在 scope-limited blocker + major（CG-01/CG-02）。这不改变气动系数本身的内部趋势有效性，但**禁止**将 CM 系数用于配平/静稳定，也禁止混用两套质量口径。
5. **W10**：确实施加（PASS），但只有单点，不得给出灵敏度。
6. **标签与放行**：维持 VSPAERO_INTERNAL_ONLY、LF-M2.02 = NOT_VALIDATED、BODY-CORR = BLOCKED、physical_validation = NOT_VALIDATED、lifting-surfaces-only；approved_for_next_stage 维持 false；A 类剩余 6 次不结转、不自动使用。
7. **后续建议（均需新授权，本轮不执行）**：① 力矩参考点/质量基线冻结任务卡（CG-01/CG-02）；② 坐标系与力/力矩符号独立验证；③ 同几何多点重复性（≥3 对）与 W10 扫描（3–5 点）；④ VSPAERO 版本升级时先跑 48 列表头/薄面回归；⑤ 修正矩阵 vspgeom_basename 与 S3 re-read 状态（小修，不消耗求解预算）。

## 13. 复现方法与命令

本报告与证据 JSON 可由以下命令复现（全部零求解；python = <repo>/envs/RCAIDE/python.exe，仅标准库）：

    1) 生成审计证据 JSON（约 751 KB）
    cd <EXT>/a1
    <repo>/envs/RCAIDE/python.exe -E -s -B audit_v2.py

    2) runner 非物理单测（mock，不启动求解器）
    cd <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z
    <repo>/envs/RCAIDE/python.exe -E -s -B -m unittest scripts.test_vspaero7_runner_v2 -v
    <repo>/envs/RCAIDE/python.exe -E -s -B -m unittest scripts.test_vspaero7_runner_v1frozen -v

    3) 零求解自查
    tasklist | findstr /i vspaero

审计要点文件（附录 A/B 给出 SHA）：run_config.json、solver_case_matrix.csv、summary.json、data_manifest.json、evidence/v1/data_manifest.json、evidence/batch2/{batch2_results.json,final_checks.json,budget_ledger.json,ledger.jsonl}、scripts/vspaero7_runner_v2.py、scripts/test_vspaero7_runner_v2.py、docs/reviews/d12d005_batch1_report_20261104.md、docs/reviews/d12d005_batch2_report_20261104.md。

## 附录 A 关键文件 SHA

| 类别 | 文件 | 字节 | sha256 |
| --- | --- | --- | --- |
| runner/run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/vspaero7_runner_v2.py | 55689 | 45545052106b84ec7aee990878cadae398b05701d651cd140c23eb67daa7c776 |
| runner/run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/vspaero7_runner_v1frozen.py | 30373 | b77b56526acab6ac03ee07838d06970f2bd98d298aae597997bf393474128a36 |
| runner/run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/test_vspaero7_runner_v2.py | 28823 | f6cffa0e41ed8833eeba192f4cc4c5351ea12ee1552b2e68bec6fd449b98e9dd |
| runner/run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/test_vspaero7_runner_v1frozen.py | 8217 | 51946c9c67dffe5e0e3db017043053f1329c384f418d66b7e707ea8275267192 |
| runner/run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/run_config.json | 8268 | b3d9522e2e0245e3a7277476972b0fe9db93b24ea902756c6de8b8962e1da095 |
| runner/run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/solver_case_matrix.csv | 7138 | e09fa6c3e225a0d2778f0e7b08eed74230e42dab27ebe8ae981124bae6f7dbd0 |
| runner/run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/summary.json | 13556 | 6d1b7ebdf2c32d04e32715523ed219e161b01d14b986e9ce7533def9162f92d6 |
| runner/run | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/data_manifest.json | 204529 | 4026f4223fe8e6737af5091e8fafec240d197e7f128a989075abe777a74ca0a1 |
| 报告 | <repo-d12d006>/docs/reviews/d12d005_batch1_report_20261104.md | 20977 | 819eec707b162b99532a6be4f552d6f424c9a57dac0d89bbb7c95b500ad78b63 |
| 报告 | <repo-d12d006>/docs/reviews/d12d005_batch2_report_20261104.md | 18721 | c5a13fc7a1d5efff83cb3a05513450e130b30b5b6e97ffe8b0ff3cabf04ebc79 |
| 报告 | <repo-d12d006>/docs/reviews/p1p3_fullchain_validation_report_20261031.md | 13788 | adcf253aca1fb2ae093802c20e879190c05695ca2b520c654cb45d2b02c31ad3 |
| 日志 | EXT/d12d006/a1/logs/runner_v2_tests.log | — | — |
| 日志 | EXT/d12d006/a1/logs/runner_v1frozen_tests.log | — | — |
| 批2 结果 | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/batch2/batch2_results.json | 47367 | 0ffb4906d65ee6d52f047b39add3d94ccf2d3c187a84382d47a6f7927e3c9a06 |
| 批2 结果 | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/batch2/final_checks.json | 6285 | c9657c8276c76093179bda612e4f40f5976873b569905578a00facc3303ce35c |
| 批2 结果 | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/batch2/budget_ledger.json | 928 | e138b1215e994f18c2453de85a99355ffcdada7a8441ce94574e39fca3f4b09f |
| 批2 结果 | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/batch2/ledger.jsonl | 54057 | a895c4f65df5aef0f5f47dabc9a05506ceed477bf5ffe80a0d47f4bf56376897 |
| 批2 结果 | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/batch2/run_start.json | 12607 | 26d06acf8b741a74fb27e805c0c2fc9c75d0d2190336f89dd92dc1be4f37455b |
| 清单 | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1/data_manifest.json | 20781 | 9fd98ddee746b92e9c5127cca60e09054ade1ff2f616ba8a87851fe8a0d496aa |
| 清单 | <repo-d12d006>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/v1b/data_manifest.json | 40182 | 3daac237276669da7e5ff0a999df438530f8ff4fefc43e6eb19703deae4560b8 |

## 附录 B 14 案完整 SHA

| 案 | contract .vspaero sha256 | polar sha256（首份副本） | history sha256（首份副本） |
| --- | --- | --- | --- |
| S0_STD_M0p1_base | 45c723b6063d56752ba153e3d6fd70f3c95d99ddb59ad2ebd92b56abf30f8912 | 920ae8c9e341373ebb5bd28d85cccf6113c82b98352c924a76a7c831b95a41f4 | 9a9422b5dccf2add043bdaa787f1ea2c53425eddc7a709d84a767569131ae902 |
| S1_STD_M0p1_wn128 | 3b3acace1d6fe5a51c355e1633c4118817a9f8854456c1495767e4eca8606e40 | f54d81d2ec3792bd306aa591239a54f31a9bb4751fb8d7576256da356a956908 | c06a3f25d3741a1f380793b7a01cf442273b8d87324b3a49e87d47d5f5e0de3c |
| S2_STD_M0p1_wi0 | 668c1f4a5f543c5b7219b53d794fccfb88a80c0322085e5ebdf83ad35db39cbe | 65087b8cff3d02973497f6bf3c2e01d22cdccfc0e8f84d67af1f55aeedb15d27 | eadea4af1d67b873ca57163111021404109507f0c4771c651333deac9a7ec897 |
| S3_STD_M2p02_base | da80fda85e2b4d67ebd293f7f5041fd1909290c0cb670268dfc6ea3fdbfa8246 | 61e49c249d611ccecf20673be7bcbd043074a88c7f85ff814edce7a16125c75b | e8ed6e8b5369c6f295dd9db0a92532f098e25aa08ac65a6ce3e4a7c08870f74b |
| S4_STD_M2p02_wn128 | f2bbfa6c17ad3e79f8c0576fbe2340f5ad52884415ada30040df3895f5761c76 | a78a33ee500cc9f858c63415f5243376c000cd52682e30f6820cc4816ae06f23 | 48f2692c359a02d608074ad27dec053d8a0fff57e68d6cf85eec3c3383382824 |
| S5_D12_M2p02_base | c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64 | 5842830cf4faa0978225998f87829e5457f3ef727f66dec350849e73181078cc | e149acdfeee75d9c76dbe1e2b6e57ff492f8811008ee5c00de9bdd6b7e6345c5 |
| S6_STD_M2p02_aoa1 | 5a1e69bb298eae3d4e6c27f5b648750cb28eebb7b6f1581656dfd72b1727f463 | 7d384e69941c9ec9aeae2f74aec17fafaa101b99dbdfdc72c85a49035150b5c8 | aa17e4d6e696fd9cc8bd0a98947f9ade5b4639bbde7251b1086eed2c77c02acb |
| B2-01 | c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64 | 4aeb47fc84e72f1706b91149ac086346fd13d4d44dafe35009a618af1d0846ec | 7ef752fcca22efa79f8601fd8cadb11c2cc6816aff9c87517987f5bb34e9ec7a |
| B2-02 | c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64 | e080fd65b11cfdca1246841391e9884f2a9d2456a7bcbbbf7583dbc29f35486e | 1aa22130db379ad72bdfc40d535a183740cb11d879c019006603031fc05a3689 |
| B2-03 | c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64 | 3fa9af027ae4bc47bde5bd9784d799cdbb09d1b8bde429d9746c7a0c456fa421 | 306049f597d583a9b574f0ab17506692f1dc5119b765cddd5418ad55aeddbc22 |
| B2-04 | c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64 | 39d213c9aaa40d31bf850d888b3bdd5df44bfe974e011d49261cb1d2b0ef31d9 | 5496b75cfc7fdfd6c8d2fc43ed6505202c902a8ec30f23254e64befd949fe7de |
| B2-05 | c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64 | 1b86475b0fbfdbec659c8aba1ddab1be6f0c5e691a93c9d4bd7a3d89352cde19 | db74715ddc4790ccab69f8fe2df5a541ba33430f94bcc72207d136037cef1e95 |
| B2-06 | c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64 | 9bd645e3d3bee3b9653f9c1b4b3f60eae582447155e6c133350901ead7ebda97 | fed094042061ef6a2d7447c3f9aa8630b065b0726faf9989417cb6239cd10224 |
| B2-07 | c9cef04e6a6986fdc87f07338e168dbf2ee17bdab3f5836b417ba6e6036ccb64 | 99702bbfaf2eed0b083d4e418a60689012a6b7cceea86e192d2fcdc2243d9de2 | 46b7ef3d5cbbf83b15fa5d95a63669152cbd2fef9dccf67666df72cbd750cd62 |

| 案 | committed LF bytes | committed LF sha256 | 执行 raw bytes | 执行 raw sha256 |
| --- | --- | --- | --- | --- |
| S0_STD_M0p1_base | — | —（batch1 未提交 bundle vspgeom） | 284327 | 8363f8fb209dd3120bbdf2e3766605b9405b97de0c7561b0be08c91c4cb8ebad |
| S1_STD_M0p1_wn128 | — | —（batch1 未提交 bundle vspgeom） | 284327 | 8363f8fb209dd3120bbdf2e3766605b9405b97de0c7561b0be08c91c4cb8ebad |
| S2_STD_M0p1_wi0 | — | —（batch1 未提交 bundle vspgeom） | 284327 | 8363f8fb209dd3120bbdf2e3766605b9405b97de0c7561b0be08c91c4cb8ebad |
| S3_STD_M2p02_base | — | —（batch1 未提交 bundle vspgeom） | 284327 | 8363f8fb209dd3120bbdf2e3766605b9405b97de0c7561b0be08c91c4cb8ebad |
| S4_STD_M2p02_wn128 | 280615 | df04690f55d67b1f7740a9e101d4b36ab0fb6f0f2899525092abf9777720e50b | 284327 | 8363f8fb209dd3120bbdf2e3766605b9405b97de0c7561b0be08c91c4cb8ebad |
| S5_D12_M2p02_base | 221421 | 00d937ac656afb794725d4551381d2af8e87571279cf7c679cf57534ba86ee09 | 224357 | 9fcda6d5d45300fbb0e20257c9ddc80540b44f5064a9566089d7ef85f9018d8e |
| S6_STD_M2p02_aoa1 | 280615 | df04690f55d67b1f7740a9e101d4b36ab0fb6f0f2899525092abf9777720e50b | 284327 | 8363f8fb209dd3120bbdf2e3766605b9405b97de0c7561b0be08c91c4cb8ebad |
| B2-01 | 88239 | e9d8a83010597ec6a67d8fe4f583562bd92bcf77440169adac6dec3cbb770afc | 89427 | 0db18500be51340aa200cd33c2a11dc8e8a09423fcf8349f34ab0ab84008dbed |
| B2-02 | 221421 | 00d937ac656afb794725d4551381d2af8e87571279cf7c679cf57534ba86ee09 | 224357 | 9fcda6d5d45300fbb0e20257c9ddc80540b44f5064a9566089d7ef85f9018d8e |
| B2-03 | 489259 | 598f31cd18f34805560984e47d205fd340ca8b0e999a5570e87be586601ed76e | 495690 | d071b05feb499931ec2022b19787047adb34dcc27693466c57b4baf777c981d3 |
| B2-04 | 489259 | 41cb728dd279534ce388ab82e74250a9d29eb78b55003f8e6614eb3e5d084b56 | 495690 | d3f0035c12441da05f54928e3461051870fb90ed16b98837683663931af3de81 |
| B2-05 | 489259 | eccb2a8b5f481d11d144dcbdcd44826023c405f2d30002da7afb0a1f718d4a42 | 495690 | ef56573de1a526a66a8caeb072a83c8495f98d31e24b2706ba4c15100f4533e7 |
| B2-06 | 489259 | 6ed1f12542ab2c4a4a9290584b3c58419c06b261e54bf2c8145dd64a43662656 | 495690 | 3466cec97955742e9d13f7d39e214aa5cdc682c1313d4c43c7fb7d62e19e3d53 |
| B2-07 | 489259 | 598f31cd18f34805560984e47d205fd340ca8b0e999a5570e87be586601ed76e | 495690 | d071b05feb499931ec2022b19787047adb34dcc27693466c57b4baf777c981d3 |

## 附录 C 术语与标签

- VSPAERO_INTERNAL_ONLY：VSPAERO 结果只作内部趋势参考，不作物理验证。
- LF-M2.02 = NOT_VALIDATED：M2.02 低速/薄面 VLM 支线未通过物理验证。
- BODY-CORR = BLOCKED：翼身干扰/机身修正阻塞，未注入。
- lifting-surfaces-only：仅主翼升力面，不含机身、垂尾与翼身干扰。
- physical_validation = NOT_VALIDATED：所有系数均未与风洞/CFD/实验验证。
- AUDIT_PASS_WITH_FINDINGS：证据链通过，但存在需后续任务卡解决的发现。
