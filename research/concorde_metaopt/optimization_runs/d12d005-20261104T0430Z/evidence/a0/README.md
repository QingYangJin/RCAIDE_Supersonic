# D-12D-005 / A0 零求解预检包（标准翼设置族 + 严格回读门禁 + V1 归档根因诊断）

- run_id：`d12d005-20261104T0430Z`
- 授权：Issue #4 评论 `6622447995`（D-12D-005，2026-11-04T04:20:18Z）
- 阶段：**A0 零求解预检**（尚未启动任何 VSPAERO 求解器；`solver_processes_started = 0`）
- 分支 / worktree：`research/d12d005-aero-fallback` @ `D:/RCAIDE-d12d005`
- 物理预算状态：A 类（VSPAERO7-thin-LF）cap 20，第一批 ≤6；**本轮使用 0/20**，`starts_used = 0`；D-12D-002/004 额度不结转
- 生成时间：2026-11-04T04:55:48Z 起；**evidence revision 5**（revision 3 回应 A5 task-103/106；revision 4 回应 A5 task-110 S3F-01 的主/派生列分离；revision 5 回应 A5 task-111 的 R4-M01/R4-M02/R4-M03 与 6 项 minor，零求解，见 §16）

## 1. 本轮目的

D-12D-004 V1 的两次 VSPAERO 启动均出现非物理系数/发散，A0 需在**不消耗任何求解预算**的前提下回答三件事：

1. V1 失败的归档根因是什么（是数值问题、还是 setup 路线问题）？
2. 用于"标准可核对翼"的几何与设置族是否就绪、能否用解析/半解析预期判定？
3. 正式启动前的严格门禁（LD-002 解析器、目录/版本/回读/薄厚/坐标/尾迹设置、StopBeforeRun 证据）是否冻结？

结论：① V1 是在 **Uber_eCRM-002 全机模型**上跑的，"标准翼"设置族从未被验证 → 必须先跑真正的矩形标准翼；② 标准翼（AR=4 矩形、平板中弧线）已建成，六案 setup 全部生成并通过 17 字段回读；③ 独立校验脚本全部检查通过（revision 5：**267 项检查、0 失败**；逐文件同时校验 raw 与 canonical-LF 两种形态）。**A0 本身不产生任何 CL/CD 数值**；本 run 目录下的 `evidence/v1/` 是此后经 Lead 书面授权的 A 批执行结果（4/6 次），与 A0 证据分属不同小节，A0 校验器只声明 A0 子树零求解。

## 2. 零求解证据

| 证据 | 内容 |
| --- | --- |
| `evidence/a0/setup_generation.json` | `status = A0_SETUP_READY_NO_SOLVER`；每案 `readback` 17 项决定性断言（Mach/AoA/ReCref/Vinf/Rho/Sref/Cref/Bref/X_cg/Y_cg/Z_cg/Symmetry/Beta/NumWakeNodes/WakeIters/WakeRelax/FarDist）；`stop_before_run_readback = 1`；`solver_processes_started = 0`；无 `.adb/.history/.polar/.lod` 产物 |
| `evidence/a0/vspaero_v1_divergence_analysis.json` | 只读解析 d12d004 归档：`.vspaero`/`.polar`/`.history`/solver log/模型源 SHA，`solver_starts = 0` |
| `evidence/a0/a0_verification.json` | 独立校验（revision 5）：267 checks 全部通过、0 failed；逐文件 raw + canonical-LF 双哈希；非测试脚本经 AST 扫描确认无进程启动路径（两个 unittest 以 child process 调 runner CLI，已在证据中标注例外）；A0 子树无本地 `.vspgeom`、无求解产物；求解产物只允许出现在 `evidence/v1/`（A 批授权执行，launch ledger 记账） |
| `evidence/a0/negative_controls/` | 6 个负控制 setup 均被严格门禁拒绝（见 §7） |

注：VSPAEROComputeGeometry / VSPAEROSweep 在 `StopBeforeRun=1` 下会打印形如 `...vspaero.exe -omp 4 <base>` 的**将执行命令**，这是 OpenVSP 的分析命令行回显，**不是进程启动**；证据是 `.adb/.history/.polar/.lod` 一个都不存在，且 StopBeforeRun 读回为 1。此点与 D-12D-004 V0/V1 的口径一致（V0 复核 APPROVE）。

## 3. V1 归档根因诊断（关键事实）

来源：`evidence/a0/vspaero_v1_divergence_analysis.json`（schema 1.0.0，`artifact_kind = D12D005_A0_V1_ARCHIVE_DIAGNOSTICS`）。

- **F-A0-01 几何/路线错配（决定性）**：V7-00/V7-01 的模型源是 `D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero_ex/Uber_eCRM-002/uber2.vsp3`（913,497 B，sha256 `87ab38dce4f1b4e2c2ae9bab214876f3be3e1a5459ab7463cea2f6098436318d`）——官方**多旋翼全机**示例；case 内 `.vspgeom` 2,019,343 B（sha256 `091ba77f...`）。而 12D 主翼 thin `.vspgeom` 仅 224,357 B（sha256 `9fcda6d5...`）。即 V1 用 steady VLM thin 设置跑了一个需要 `DegenGeom + groups + -unsteady` 的多旋翼全机几何（官方 README 明示）。**这不只是标签写错，是 setup 路线错误。**
- **F-A0-02 V7-00 非物理（已归档）**：`CLtot = -2801.885568189672`、`CDtot = -376.365943305457`、`CDi = -367.353142529815`、`CMoy = -9.235854701727`，`LoDw = 6.220167...`；history `CLtot` 序列先爆后收（-0.0089 → -267095.9 → -7469379.9 → 12.2645 → -2801.8856），solver log 出现负缩减（`Red: -5.995... / -1.00000`）与 `Wake Iter 5/5`。**注**：归档文件里保留的是 VSPAERO 极性表最后一行的数值；这是"求解本身发散/非物理"的证据，不是我们计算的结论。
- **F-A0-03 V7-01 发散 + 超时**：history `CLtot` -0.0051 → 4.484e22 → 3.230e26，无 `.polar` 产出；solver log 末行 `Wake Iter 4/5 / GMRES Iter 328 / Red: -5.87629 / -1.00000 / Max 8.28035`，600.331 s 超时。
- **F-A0-04 设置族未验证**：V1 未做过任何"仅改一个尾迹参数"的对照；因此"该设置族在超声速是否可行"仍然是未知，不能拿 V1 结果归因于"VSPAERO 不支持超声速"。
- **推断边界**：以上只说明"V1 的两次启动不可作为任何气动结论"，**不证明** VSPAERO 7.2.2 在正确设置下也失败。A 线第一批正是为此设计。

## 4. 标准翼几何决策（为什么不用 TR1208）

官方 `Swept_Wing_API/TR1208.vsp3` 被放弃作"标准可核对基准"，理由（实测，非文档）：

| 量 | README 文档 | 实测 shipped `TR1208.vsp3` |
| --- | --- | --- |
| root chord | 21.941 in | 16.672 |
| Sref | 2024.35 in² | 1538.217 |
| MAC | 16.672 | 12.0872 |
| AR | 8.02 | 10.528 |
| 全展 | — | 127.26 in |
| 比例 | — | 0.7599（整体缩放） |

因此改用 `AddGeom('WING')` 自建**米制矩形翼**：

- 驱动组：`SetDriverGroup(wid, 1, SPAN_WSECT_DRIVER, TAPER_WSECT_DRIVER, ROOTC_WSECT_DRIVER)`
- `Sym_Planar_Flag = SYM_XZ`（半模，镜像后全展）
- `XSec_1`：`SectTess_U = 20`、`Span = 2.0`（半展）、`Taper = 1.0`、`Root_Chord = 1.0`、`Sweep = 0`、`Sweep_Location = 0.25`
- 默认 4-series 翼型：`Camber = 0`、`ThickChord = 0.10` → VLM thin 只取中弧线，等价平板
- 实测：`TotalSpan = 4`、`TotalArea = 4`、`TotalChord = 1`、`TotalAR = 4`（独立校验脚本另从 `.vsp3` XML 解析复核）

解析预期（用于 S0 判据，**不是**已验证数值）：

- Helmbold 有限展修正：`CLα = 2π·AR / (sqrt(AR² + 4) + 2) = 3.8832 /rad = 0.067773 /deg`
- `CL(α=2°) ≈ 0.135546` → 接受区间 ±20% = **[0.1084, 0.1627]**
- 椭圆诱导阻力 `CDi = CL²/(π·AR) ≈ 0.001462` → 接受区间 [0.000731, 0.002924]
- 总阻力 `CDtot` 参考区间 [0.000585, 0.004386]

## 5. 六案矩阵（A0 生成时全部 NOT_RUN；A 批已按授权执行 S0–S3，S4/S5 待重新授权）

参考量合同：std 翼 `Sref=4 / Cref=1 / Bref=4 / X_cg=0.25 / AoA=2 / Beta=0 / Rho=0.1153178340089936 / FarDist=-1 / WakeRelax=1`；M0.1 `Vinf=29.506801840000005 / ReCref=239352.08001331755`；M2.02 `Vinf=596.0373971680001 / ReCref=4834912.016269014`。

| 案号 | 几何 | Mach | 尾迹 | 合同 setup | 用途 |
| --- | --- | --- | --- | --- | --- |
| S0_STD_M0p1_base | std 矩形翼 | 0.1 | NumWakeNodes=8, WakeIters=5 | 814 B / `45c723b6...` | 第 1 关基线（亚声速标准翼） |
| S1_STD_M0p1_wn128 | std | 0.1 | **仅** NumWakeNodes=128 | 816 B / `3b3acace...` | 单因素尾迹对照 A |
| S2_STD_M0p1_wi0 | std | 0.1 | **仅** WakeIters=0 | 814 B / `668c1f4a...` | 单因素尾迹对照 B |
| S3_STD_M2p02_base | std | 2.02 | 8/5 | 813 B / `da80fda8...` | 第 2 关超声速标准薄翼 |
| S4_STD_M2p02_wn128 | std | 2.02 | **仅** NumWakeNodes=128 | 815 B / `f2bbfa6c...` | 超声速单因素尾迹对照 |
| S5_D12_M2p02_base | 12D 主翼 thin | 2.02 | 8/5 | 847 B / `c9cef04e...` | 第 3 关前哨（与 D-12D-004 V0 完全同字节） |

- 12D 案参考量：`Sref=358.25 / Cref=18.489893 / Bref=25.604638 / X_cg=16.821978259514246 / ReCref=89397005.8767656 / Vinf=596.0373972278921`；合同 setup 847 B / `c9cef04e...` 与 D-12D-004 V0 的 contract setup **逐字节一致**（V0 已由 A5 复核 APPROVE）。
- 单因素 diff 由 `scripts/a0_verify_cases.py` 断言：S0→S1 仅 `NumWakeNodes` 8→128；S0→S2 仅 `WakeIters` 5→0；S3→S4 仅 `NumWakeNodes` 8→128。
- **A 批执行现状（2026-11-04，详见 `evidence/v1/`）**：S0/S1/S2 = `SOLVED_VALID`；S3 = 主系数有限但与理论区间一致（CLtot=0.074251），因派生列 `Ew=inf` 被 v2 旧版判 `POLAR_NONFINITE`，A2 按 stop_rule_1 保守停批，S4/S5 = `NOT_RUN_AFTER_ABORT`；A5 task-110 判定 `Ew` 为除零伪影（`STOP_CONFIRMED=false`），v2 rev4 已分离主/派生列，且公共 API 层禁止 allowlist 掩盖主系数（本 revision 5），S4/S5 需 Lead 重新书面授权（`evidence/lead/batch1b_reauthorization.md`）。
- 每案目录 7 个文件：`<case>_model.vsp3`、`<case>_model.vspaero`（**raw**，仍含 VSPAERO 三个默认值 ReCref=1e7 / Vinf=100 / Rho=0.002377）、`<case>_contract.vspaero`（17 断言 PASS）、`<case>_model.vkey`、`<case>_model.csf`、`geom_result_thin.csv`、`expected.json`。薄 `.vspgeom` 已外置：
  - std：284,327 B / sha256 `8363f8fb209d...`（5 个 std 案同几何同哈希）
  - 12D：224,357 B / sha256 `9fcda6d5...`（与 D-12D-004 V0 一致）
  - 外部根：`D:/RCAIDE/outputs/concorde_metaopt/d12d005-20261104T0430Z/raw_artifacts/a0_setup/`（`outside_git = true`）

## 6. A2 执行 bundle（门禁通过后照此启动，禁止自行改参数）

1. 新建 case 执行目录（不要直接改写 A0 证据目录）。
2. 复制：`<case>_model.vsp3`、`<case>_model.vkey`、`<case>_model.csf`、`<case>_contract.vspaero`（**用 contract 版，不要用 raw 版**）、`geom_result_thin.csv`、`expected.json`（**必须随包**：v2 的 check-case-dir 在缺 expected.json 时回退 12D 合同，std 案会以 Sref 4.0 vs 358.25 报 SETUP_READBACK_FAIL）。
3. 把外置 thin `.vspgeom` 复制到执行目录，命名 `<base>.vspgeom`（base 与 contract 文件名主干一致）。
4. 改写 `.vkey` 第 2 行为该 `.vspgeom` 的**绝对路径**（D-12D-004 V1 两次失败的直接根因之一：缺 vkey/csf + vkey 内路径不对）。
5. 运行：`D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe -omp 4 <base>`，cwd = 执行目录；串行，≤4 核，≤16 GB，单次 ≤900 s。
6. 启动前门禁（v2 已就绪，A0-aero ab29a0c）：`D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/vspaero7_runner_v2.py check-case-dir --dir <case_dir> --evidence evidence/a0/setup_generation.json --case-id <case_id>`，必须 `status=PASS`（Lead 已用 S0/S5 bundle 端到端验证：contract 17 断言、vspgeom sha、vkey/csf、StopBeforeRun=1、无 solver 产物全过）。注意 CLI 退出码在管道里可能显示 0，须以 JSON status 判定。
7. 启动后：用 v1frozen/v2 的 `validate_polar_file` / `validate_history_file` 复核；v1frozen 的 polar 校验是 **6.2 旧表头**，在 v2（LD-002）就绪前**不得**用它判定 7.2.2 结果有效。

判定（第 1 关 S0，先看符号/量纲/残差/尾迹有界，再看是否落入解析区间）：

- CL 符号为正、量级 O(0.1)，落 [0.1084, 0.1627]；
- CDi/CDtot 为正、量级 O(1e-3)，CDi 落 [0.000731, 0.002924]；
- history 无 NaN/Inf、系数序列单调收敛、末段残差有界（不出现负缩减 / O(1e2) 以上跳变）；
- 以上通过 → 第 1 关 PASS，可进 S1/S2 单因素对照；任一不满足 → 按 A1 路线"两独立核查仍发散则停该设置族"，出根因并转 B 线 fallback，**不必耗尽 A 额度**。

## 7. LD-002 解析器修复要求（A1 task-95）

VSPAERO 7.2.2 真实 polar 表头（A0 从归档 V7-00 `.polar` 实测确证，48 列；**表头前有两行分组标签**）：

```
Beta Mach AoA Re/1e6 CLo CLi CLtot CDo CDi CDtot CSo CSi CStot L/D E
CMox CMoy CMoz CMix CMiy CMiz CMxtot CMytot CMztot CFox ... CLwtot CDwtot CSwtot
CLiw CDiw CSiw CFwxtot ... LoDw Ew StallFactor
```

- 必须定位"同时含 CLtot、CDtot、Mach"的真实表头行；严格 token 匹配，禁止把旧 `CL` 当 `CLtot`、禁止读取不存在列；
- 缺列 / NaN / IND / INF / 非物理 → `INVALID`（不伪造通过）；
- 旧 6.2 表头（无 `CLo/CLi`）明确拒绝并给错误码；
- 回归测试覆盖：LD-001 模板缺 `=`、缺 `.vkey/.csf`、外层 120 s 包装器误杀、默认值泄漏（1e7/100/0.002377）、错误 Sref、旧表头。测试不得启动真实求解器。

当前状态：v2 解析器已交付并完成 rev2 加固、rev3 主/派生列分离与 rev4 公共 API 收紧（`scripts/vspaero7_runner_v2.py` 1,371 行 / 55,689 B canonical / sha256 `45545052106b...`，SCHEMA_VERSION `d12d005-runner-5`；`scripts/test_vspaero7_runner_v2.py` 637 行 / 28,823 B / `f6cffa0e41ed...`；**58 tests OK**，日志 `evidence/a0/v2rev4_test_run.log`；`--allow-nonfinite-derived` 只放行派生列 `Ew`，公共 API 对任何非派生白名单列抛 `POLAR_ALLOWLIST_NOT_DERIVED`）。本包的 `scripts/vspaero7_runner_v1frozen.py` 仍是 D-12D-004 V1 的冻结基线（`start_solver()` 恒 raise `SolverStartRefused`），只作 setup 注入/回读/负控制用途；polar 校验必须用 v2（7.2.2 48 列），v1frozen 的 polar 校验器对 7.2.2 **不可用**。

## 8. 门禁状态（本阶段）

| 门禁 | 状态 | 说明 |
| --- | --- | --- |
| GEO-12D | PARTIAL | 12D 主翼几何沿用 D-12D-004 已验证的 `wing355_baseline.vsp3`（111,816 B / `9a788b467095...`）+ thin vspgeom（224,357 B / `9fcda6d5...`），未新增几何结论 |
| LF-M2.02 | **NOT_VALIDATED** | 本轮零求解，未改变 |
| HF-M2.02 | PARTIAL | 未动（SU2 需 owner 另行授权 C 类预算） |
| BODY-CORR | BLOCKED | 未动（面积律仍 NOT_VALIDATED，禁止注入 Mission） |
| MISSION-DATA | PARTIAL | 未动 |
| BUDGET | 门控中 | A 类 cap 20、本批 ≤6、已用 0；B/C 类 0 |
| APPROVED_FOR_NEXT_STAGE | **未签发** | 仅负责人可签发 |

## 9. 文件与哈希

- 生成/校验脚本（9 条，逐文件双形态哈希见 `setup_generation.json` 的 `scripts` 数组）：`scripts/a0_analyze_v1_divergence.py`、`scripts/a0_generate_setups.py`、`scripts/a0_finalize_evidence_v2.py`、`scripts/a0_verify_cases.py`（支持 `--no-write` 只读复核）、`scripts/make_v1_evidence_reconciliation.py`（V1/A 批证据双形态对账）、`scripts/vspaero7_runner_v1frozen.py`、`scripts/test_vspaero7_runner_v1frozen.py`、`scripts/vspaero7_runner_v2.py`、`scripts/test_vspaero7_runner_v2.py`
- 冻结基线：`scripts/vspaero7_runner_v1frozen.py`（30,373 B / sha256 `b77b56526acab6ac03ee07838d06970f2bd98d298aae597997bf393474128a36`）、`scripts/test_vspaero7_runner_v1frozen.py`（8,217 B；import 已修，22 tests OK）；LD-002 v2 解析器：`scripts/vspaero7_runner_v2.py`（55,689 B canonical / `45545052106b...`，rev4 / `d12d005-runner-5`）、`scripts/test_vspaero7_runner_v2.py`（28,823 B canonical / `f6cffa0e41ed...`，rev4）；测试日志 `evidence/a0/v1frozen_test_run.log`（22 tests）、`evidence/a0/v2rev2_test_run.log`（46 tests）、`evidence/a0/v2rev3_test_run.log`（51 tests）与 `evidence/a0/v2rev4_test_run.log`（58 tests）
- 关键哈希：OpenVSP 3.55.0 / `vspaero.exe` sha256 `db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad`；12D 模型 sha256 `9a788b467095...`（完整值见 `setup_generation.json`）
- 完整 `data_manifest.json` 在本阶段**未生成**；A0 阶段的逐文件哈希在 `evidence/a0/setup_generation.json` 与 `evidence/a0/a0_verification.json` 内，采用 raw + canonical-LF 双形态记录（见 §13）。整包 manifest 将在 A 线执行包冻结时统一生成（与 D-12D-004 V1 相同的 canonical-LF 约定）。

## 10. 明确不声明（non-claims）

- 本阶段**没有**启动任何 VSPAERO 求解器、没有消耗任何求解预算（A 0/20）。
- 本阶段**没有**产生任何 CL/CD/CDi/CM 数值结论；§4 的解析区间只是待验证的判据。
- 本阶段**没有**证明 VSPAERO 7.2.2 在超声速下不可用，也**没有**证明它可以；V1 的非物理只是"在错误的几何/设置路线上"的结果。
- 本阶段**没有**改变六门禁状态，**没有**签发 APPROVED_FOR_NEXT_STAGE，**没有**触碰 main / PR #3 / PR #6 / 旧 P5 文件。
- 面积律（Jones 型 Mach 切面）仍为 NOT_VALIDATED，不得注入 Mission 或用于 P4 训练标签。

## 11. 复现

```bat
cd D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/a0_verify_cases.py --run-dir .
# 只读复核（不重写 tracked a0_verification.json）：追加 --no-write
```

- setup 生成（会调用 OpenVSP 3.55 API，但 StopBeforeRun=1，不启动求解器）：
  `D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/a0_generate_setups.py`
- 归档诊断（纯只读解析）：`D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/a0_analyze_v1_divergence.py`


- 也可从任意位置的完整 checkout 副本复核（run 内路径全部相对化）：
  D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B <root>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/a0_verify_cases.py --run-dir <root>/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z

## 13. 复核整改（evidence revision 2，A5 task-97）

A5 首轮复核 verdict CHANGES_REQUESTED（0 blocker / 1 major / 4 minor），本 revision 2 逐项处置：

| 编号 | 级别 | 问题 | 处置 |
| --- | --- | --- | --- |
| F-A0-01 | MAJOR | 逐文件哈希按提交前 CRLF 记录；clean checkout 是 canonical LF（.gitattributes 为 text=auto/eol=lf），复跑 24/163 失败 | 所有文本文件记录改为 raw + canonical-LF 双形态（bytes_raw/sha256_raw/bytes_canonical_lf/sha256_canonical_lf/hash_mode/eol），case 路径改为 run 目录相对路径；README 的 163/0 表述改为引用 a0_verification.json 的 checks_total |
| F-A0-02 | minor | test_vspaero7_runner_v1frozen.py import 旧模块名，A0 包内死测试 | 改为 import vspaero7_runner_v1frozen 与 HERE/模块名；实跑 22 tests OK，日志 evidence/a0/v1frozen_test_run.log |
| F-A0-03 | minor | §5 写每案 6 文件但列了 7 个 | 改为 7 文件 |
| F-A0-04 | minor | 脚本无进程启动的扫描只覆盖 2 个脚本 | 扫描扩展到 setup_generation.json 的 scripts 全部 9 个记录，改为 AST 导入/调用扫描；两个 unittest 的 child-process CLI 作为例外显式记录（process_spawn_scan.documented_exception） |
| F-A0-05 | minor | S5 的 Vinf 直接继承 V0 冻结值，未注明与公式推导差 6.0e-8 m/s | S5 增加 reference_velocity 块：来源、公式值 596.0373971680001、差值 5.99e-8 m/s（相对 1.0e-10）、保留冻结值的理由（与已复核 V0 逐字节一致） |

**哈希约定**：文本文件按 canonical LF 计哈希（等于提交后的 git blob 内容）；外部 thin .vspgeom（outside_git = true）按 raw 字节计哈希。raw 形态只在生成机存在（Windows CRLF）：在干净 checkout 中文本文件只有 canonical-LF 形态，校验器对 raw_hash 判为 checkout_normalised（raw 仅作生成机证据，不作为 clean checkout 判据）。复跑方式见 §11（--run-dir 支持任意 checkout 根）。

**干净 checkout 复跑**：`evidence/a0/a0_verification_checkout.log`（720 B；raw 与 canonical-LF 同形，sha256 `5233490259f1672ef49ac07dc5d5483a750d77bcd5f575847256ce2008ffe68a`，因纯 LF 生成；raw = canonical），在 detached worktree @ `2378345`（revision 2 checkpoint）、`git status` 全干净的条件下重跑 verifier，结果 **260 checks PASS / 0 failed**（日志显式记录 `checks_failed: 0`、`solver_processes_started: 0`、命令与 commit）。

## 14. 复核整改（evidence revision 3，A5 task-103 / task-106）

A5 对 v2 解析器 delta 给 CHANGES_REQUESTED（0/3/5：V2-M01/M02/M03），对 A0 revision 2 给 APPROVE_FOR_A_BATCH1（0/0/5：A0R2-01..05）。revision 3 处置：

| 编号 | 级别 | 问题 | 处置 |
| --- | --- | --- | --- |
| V2-M01 | MAJOR | check-case-dir 只比较 vkey 的 basename，不验证存在/同一文件 | vkey 目标解析为绝对路径并 `resolve(strict=True)`，与解析出的 vspgeom 全路径相等才算 PASS（`CASE_VKEY_GEOM_MISMATCH`） |
| V2-M02 | MAJOR | 本地 `*.vspgeom` 分支直接返回，不核对证据记录 | 本地 vspgeom 必须与记录 sha256/bytes 一致（`CASE_VSPGEOM_SHA_MISMATCH`/`CASE_VSPGEOM_BYTES_MISMATCH`），并返回 `evidence_record_verified` |
| V2-M03 | MAJOR | 缺 `solver_processes_started` 时放行 | 改为 fail-closed：缺失即 `CASE_SOLVER_PROCESS_EVIDENCE_MISSING` |
| V2-minor | minor | csf 仅 startswith；表头行号未强制；无 structure-only；说明文件数值旧；未 commit 表述 | csf 精确等于 `0 control surfaces`；强制表头为第 3 行（`POLAR_HEADER_ROW_UNEXPECTED`）；新增 `polar-structure`（`PASS_STRUCTURE_ONLY`）；本文件与 §1 表更新；说明改为已提交 |
| A0R2-01 | minor | README 只写 checkout log 的 raw 哈希 | 本节与 §13 同时写 raw 与 canonical-LF 两种形态 |
| A0R2-02 | minor | checkout log 写 `failed=None` | 新 log 显式写 `checks_failed: 0`，并记录 commit/命令 |
| A0R2-03 | minor | verifier 只重放 S0 的 3/6 负控制 | 遍历 negative_controls 下所有分组（S0 与 S3），6/6 全部重放 |
| A0R2-04 | minor | `model_is_12d_wing` 恒真 | 改为按案检查期望模型名（S5 为 `wing355_baseline.vsp3`，其余为 `<case>_model.vsp3`） |
| A0R2-05 | minor | 绝对 provenance 字段 + verifier 写回弄脏 tracked JSON | `--no-write` 只读复核；绝对路径字段标注为 informational |

verifier revision 3 结果：**263 checks PASS / 0 failed**（`a0_verification.json`，schema `d12d005-a0-verification-2`）。`setup_generation.json` revision 3 同步记录 8 个脚本的双形态哈希。

**干净 checkout 复跑（revision 3）**：`evidence/a0/a0_verification_checkout_rev3.log`（896 B；纯 LF 生成，raw = canonical-LF，sha256 `d498c2ecc00fe483d0a144ea2d2f2fc16104b6a58acd38173e115c48744d65bd`），在 detached worktree @ `0790f17`（revision 3 checkpoint，v2 rev2 + evidence rev3）、`git status` 全干净的条件下以 `--no-write` 重跑 verifier，结果 **263 checks PASS / 0 failed**；日志显式记录 `checks_failed: 0`、`solver_processes_started: 0`、命令与 commit，且 `--no-write` 不重写 tracked 的 `a0_verification.json`。

## 15. 复核整改（evidence revision 4，A5 task-110 S3F-01）

A 批 4/6 次启动后 S3 因派生列 `Ew=inf` 触发 `POLAR_NONFINITE` 停批；A5 判定为除零伪影（主系数 `CLtot=0.074251 / CDi=0.002607 / CDtot=0.013789` 均有限且 CL 落在线化理论 0.0673–0.0796 内，`STOP_CONFIRMED=false`）。revision 4 处置：

| 编号 | 处置 |
| --- | --- |
| S3F-01 | v2 rev3 新增 `POLAR_DERIVED_NONFINITE_COLUMNS=("Ew",)` 与 CLI `--allow-nonfinite-derived`：仅白名单派生列可非有限，报告降级为 `PASS_WITH_WARNINGS` 并记录 `derived_column_warnings`；主系数任何非有限仍 `POLAR_NONFINITE`；未知白名单列 `POLAR_ALLOWLIST_UNKNOWN_COLUMNS` |
| S3F-02 | 文档限定：`CDo/CDtot` 为 VSPAERO 内部寄生估算，不能当作真实阻力/优化目标；S4/S5 证据须标 `VSPAERO_INTERNAL_ONLY` / `physical_validation=NOT_VALIDATED` |
| S3F-03/04/05 | A2 停批判定为保守正确（不追责）；S3 以 allowlist 重跑 `verify-polar` 得 `PASS_WITH_WARNINGS`（`evidence/lead/s3_verify_polar_allowlisted.json`）；history `Ew=0` 与 polar `Ew=inf` 的差异记入诊断说明 |

verifier revision 4 结果：**264 checks PASS / 0 failed**（`a0_verification.json`，schema `d12d005-a0-verification-2`）；`setup_generation.json` revision 4 同步记录 8 个脚本的双形态哈希。本次修订**零求解**，A 批启动计数保持 4/6。

**干净 checkout 复跑（revision 4）**：`evidence/a0/a0_verification_checkout_rev4.log`（1,011 B；纯 LF 生成，raw = canonical-LF，sha256 `a0151e9fa7a80c63c38e42640ef31d4074b470a51d116d95fe06acae6862c37b`），在 detached worktree @ `f5827ba`（batch1 证据提交）、`git status` 全干净的条件下以 `--no-write` 重跑 verifier，结果 **264 checks PASS / 0 failed**；日志显式记录 `checks_failed: 0`、`solver_processes_started: 0`、命令与 commit。

## 16. 复核整改（evidence revision 5，A5 task-111 R4-M01/M02/M03）

A5 对 revision 4 判 `CHANGES_REQUESTED`（0 blocker / 3 major / 6 minor）。revision 5 逐项处置（**零求解**）：

| 编号 | 处置 |
| --- | --- |
| R4-M01（major） | `validate_polar_file` 的 `allow_nonfinite_columns` 现在只允许派生列：`not_derived = [n for n in allowed if n not in POLAR_DERIVED_NONFINITE_COLUMNS]`，非派生列一律抛 `DataQualityError("POLAR_ALLOWLIST_NOT_DERIVED: ...")`，因此公共 API 不可能再用 allowlist 掩盖 CDi/CLo/CDo/CLi 等主系数；新增 `AllowlistScopeTests` 7 个测试（CDi/CLo/CDtot 单列拒绝、Ew+CDi 混合拒绝、主系数 NaN + allowlist 仍拒、`POLAR_DERIVED_NONFINITE_COLUMNS == ("Ew",)`、Ew 仍 `PASS_WITH_WARNINGS`）；SCHEMA_VERSION 升 `d12d005-runner-5`，**58 tests OK**（`evidence/a0/v2rev4_test_run.log`） |
| R4-M02（major） | 新增 `scripts/make_v1_evidence_reconciliation.py` 重生成 `evidence/v1/data_manifest.json`（schema 2 / revision 6，**40 条** = `evidence/v1/` 37 文件 + `config/` 3 文件；逐文件 `bytes_raw` / `sha256_raw` + `bytes_canonical_lf` / `sha256_canonical_lf` / `hash_mode` / `eol`；`total_canonical = 290,912 B`、`total_raw = 292,514 B`；revision 6 在最终 README/run_start 文本修订后重跑，40/40 与提交 blob 一致；`total_bytes_note` 记明 A5 核对中 283,485 B 为 10 条 CRLF 差值的估算）。A2 首版 manifest（39 条 / sha `a0b100ec…`）被本 revision 取代，可在 `f5827ba` 取回 |
| R4-M03（major） | 新增 `evidence/v1/case_summary_reconciliation.json`：四案 polar 用 v2 解析器（allowlist `Ew`）重读，S0/S1/S2 = `PASS`，S3 = `PASS_WITH_WARNINGS`，主系数与 `batch1_results.json` 一致；A2 原始 `case_summary.json` 不改写，缺口由对账文件补足 |
| R4-minor | 报告补 S4/S5 的 `VSPAERO_INTERNAL_ONLY` / `physical_validation=NOT_VALIDATED` 标签；`evidence/v1/run_start.json` 增加 `batch1b_stop_rule_amendment`；报告复现命令补齐 `_model.polar` 文件名；`evidence/v1/README.md` 把 Ew 溢出归因改为 `CDiw=0`（除零）；“只改 run+docs” 改为准确提交范围；日志分类改为“求解器产物日志 9 个 + 校验器日志” |

verifier revision 5 结果：**267 checks PASS / 0 failed**（`evidence/a0/a0_verification.json`）；`evidence/a0/setup_generation.json` revision 5 同步记录 9 个脚本的双形态哈希。本次修订**零求解**，A 批启动计数保持 4/6。

**干净 checkout 复跑（revision 5）**：`evidence/a0/a0_verification_checkout_rev5.log`，在 detached worktree `D:/RCAIDE-verify-d12d005-c891a0c`（HEAD `c891a0c`，`git status` 全干净）中以 `--no-write` 重跑 verifier，结果 **267 checks PASS / 0 failed**；日志显式记录 `checks_failed: 0`、`solver_processes_started: 0`、命令与 commit，且 `--no-write` 不重写 tracked 的 `a0_verification.json`（复跑后 worktree 仍为空 status）。

## 17. 下一步（等待门禁）

1. ~~A1 交付 v2 解析器（LD-002）+ 回归测试 → A5 复核。~~ 已完成（`ab29a0c` 首版 + rev2 加固 + rev3 主/派生列分离 + rev4 allowlist 范围限制；58 tests OK）。
2. ~~A5 复核本 A0 包（setup/回读/负控制/零求解）。~~ A0 revision 2 = `APPROVE_FOR_A_BATCH1`（task-106）；v2 delta CHANGES_REQUESTED（task-103）→ revision 3 处置后 A5 复核 APPROVE（task-108，980fffb）。
3. ~~Lead 授权 A 类第一批 ≤6（S0–S5）~~ 已授权并执行 4/6（S0/S1/S2 = SOLVED_VALID；S3 触发 stop_rule_1，S4/S5 NOT_RUN；见 `evidence/v1/`）。
4. ~~A5 复核 revision 4~~ → A5 task-111 判 `CHANGES_REQUESTED`（0 blocker / 3 major / 6 minor）→ revision 5 处置（本 §16）→ A5 delta 复核 + A3 delta → Lead 重新书面授权剩余 2 次（S4/S5）后由 A2 串行执行。
