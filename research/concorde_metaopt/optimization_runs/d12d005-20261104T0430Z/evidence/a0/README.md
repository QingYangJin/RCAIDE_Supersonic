# D-12D-005 / A0 零求解预检包（标准翼设置族 + 严格回读门禁 + V1 归档根因诊断）

- run_id：`d12d005-20261104T0430Z`
- 授权：Issue #4 评论 `6622447995`（D-12D-005，2026-11-04T04:20:18Z）
- 阶段：**A0 零求解预检**（尚未启动任何 VSPAERO 求解器；`solver_processes_started = 0`）
- 分支 / worktree：`research/d12d005-aero-fallback` @ `D:/RCAIDE-d12d005`
- 物理预算状态：A 类（VSPAERO7-thin-LF）cap 20，第一批 ≤6；**本轮使用 0/20**，`starts_used = 0`；D-12D-002/004 额度不结转
- 生成时间：2026-11-04T04:55:48Z 起（本 README 最后核对 2026-11-04T05:0xZ）

## 1. 本轮目的

D-12D-004 V1 的两次 VSPAERO 启动均出现非物理系数/发散，A0 需在**不消耗任何求解预算**的前提下回答三件事：

1. V1 失败的归档根因是什么（是数值问题、还是 setup 路线问题）？
2. 用于"标准可核对翼"的几何与设置族是否就绪、能否用解析/半解析预期判定？
3. 正式启动前的严格门禁（LD-002 解析器、目录/版本/回读/薄厚/坐标/尾迹设置、StopBeforeRun 证据）是否冻结？

结论：① V1 是在 **Uber_eCRM-002 全机模型**上跑的，"标准翼"设置族从未被验证 → 必须先跑真正的矩形标准翼；② 标准翼（AR=4 矩形、平板中弧线）已建成，六案 setup 全部生成并通过 17 字段回读；③ 独立校验脚本 163 项检查全过（0 失败）。**本轮不产生任何 CL/CD 数值。**

## 2. 零求解证据

| 证据 | 内容 |
| --- | --- |
| `evidence/a0/setup_generation.json` | `status = A0_SETUP_READY_NO_SOLVER`；每案 `readback` 17 项决定性断言（Mach/AoA/ReCref/Vinf/Rho/Sref/Cref/Bref/X_cg/Y_cg/Z_cg/Symmetry/Beta/NumWakeNodes/WakeIters/WakeRelax/FarDist）；`stop_before_run_readback = 1`；`solver_processes_started = 0`；无 `.adb/.history/.polar/.lod` 产物 |
| `evidence/a0/vspaero_v1_divergence_analysis.json` | 只读解析 d12d004 归档：`.vspaero`/`.polar`/`.history`/solver log/模型源 SHA，`solver_starts = 0` |
| `evidence/a0/a0_verification.json` | 独立校验：163 checks，0 failed；含"脚本内无 `subprocess`/`os.system`/`Popen`/`shell=True`"、"run 目录内无本地 `.vspgeom`" |
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

## 5. 六案矩阵（全部 NOT_RUN，等待 A5/A3/Lead 门禁）

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
- 每案目录 6 文件：`<case>_model.vsp3`、`<case>_model.vspaero`（**raw**，仍含 VSPAERO 三个默认值 ReCref=1e7 / Vinf=100 / Rho=0.002377）、`<case>_contract.vspaero`（17 断言 PASS）、`<case>_model.vkey`、`<case>_model.csf`、`geom_result_thin.csv`、`expected.json`。薄 `.vspgeom` 已外置：
  - std：284,327 B / sha256 `8363f8fb209d...`（5 个 std 案同几何同哈希）
  - 12D：224,357 B / sha256 `9fcda6d5...`（与 D-12D-004 V0 一致）
  - 外部根：`D:/RCAIDE/outputs/concorde_metaopt/d12d005-20261104T0430Z/raw_artifacts/a0_setup/`（`outside_git = true`）

## 6. A2 执行 bundle（门禁通过后照此启动，禁止自行改参数）

1. 新建 case 执行目录（不要直接改写 A0 证据目录）。
2. 复制：`<case>_model.vsp3`、`<case>_model.vkey`、`<case>_model.csf`、`<case>_contract.vspaero`（**用 contract 版，不要用 raw 版**）。
3. 把外置 thin `.vspgeom` 复制到执行目录，命名 `<base>.vspgeom`（base 与 contract 文件名主干一致）。
4. 改写 `.vkey` 第 2 行为该 `.vspgeom` 的**绝对路径**（D-12D-004 V1 两次失败的直接根因之一：缺 vkey/csf + vkey 内路径不对）。
5. 运行：`D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe -omp 4 <base>`，cwd = 执行目录；串行，≤4 核，≤16 GB，单次 ≤900 s。
6. 启动前：`python scripts/vspaero7_runner_v1frozen.py check-dir --dir <case_dir>`（v2 就绪后换 v2），必须 PASS。
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

当前状态：A1 的 v2 解析器**尚未交付**；本包的 `scripts/vspaero7_runner_v1frozen.py` 是 D-12D-004 V1 的冻结基线（`start_solver()` 恒 raise `SolverStartRefused`），只作 setup 注入/回读/负控制用途，其 polar 校验器对 7.2.2 **不可用**。

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

- 生成脚本：`scripts/a0_analyze_v1_divergence.py`（9,749 B）、`scripts/a0_generate_setups.py`（18,583 B）、`scripts/a0_verify_cases.py`（10,034 B）
- 冻结基线：`scripts/vspaero7_runner_v1frozen.py`（30,373 B / sha256 `b77b56526acab6ac03ee07838d06970f2bd98d298aae597997bf393474128a36`）、`scripts/test_vspaero7_runner_v1frozen.py`（8,199 B）
- 关键哈希：OpenVSP 3.55.0 / `vspaero.exe` sha256 `db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad`；12D 模型 sha256 `9a788b467095...`（完整值见 `setup_generation.json`）
- 完整 `data_manifest.json` 在本阶段**未生成**；A0 阶段的逐文件哈希在 `evidence/a0/setup_generation.json` 与 `evidence/a0/a0_verification.json` 内。整包 manifest 将在 A 线执行包冻结时统一生成（与 D-12D-004 V1 相同的 canonical-LF 约定）。

## 10. 明确不声明（non-claims）

- 本阶段**没有**启动任何 VSPAERO 求解器、没有消耗任何求解预算（A 0/20）。
- 本阶段**没有**产生任何 CL/CD/CDi/CM 数值结论；§4 的解析区间只是待验证的判据。
- 本阶段**没有**证明 VSPAERO 7.2.2 在超声速下不可用，也**没有**证明它可以；V1 的非物理只是"在错误的几何/设置路线上"的结果。
- 本阶段**没有**改变六门禁状态，**没有**签发 APPROVED_FOR_NEXT_STAGE，**没有**触碰 main / PR #3 / PR #6 / 旧 P5 文件。
- 面积律（Jones 型 Mach 切面）仍为 NOT_VALIDATED，不得注入 Mission 或用于 P4 训练标签。

## 11. 复现

```bat
cd D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -c "import sys; sys.path.insert(0, 'scripts'); import a0_verify_cases as v; print(v.main())"
```

- setup 生成（会调用 OpenVSP 3.55 API，但 StopBeforeRun=1，不启动求解器）：
  `D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/a0_generate_setups.py`
- 归档诊断（纯只读解析）：`D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/a0_analyze_v1_divergence.py`

## 12. 下一步（等待门禁）

1. A1 交付 v2 解析器（LD-002）+ 回归测试 → A5 复核。
2. A5 复核本 A0 包（setup/回读/负控制/零求解） → verdict `APPROVE_FOR_A_BATCH1` 或 `CHANGES_REQUESTED`。
3. A3 复核 worktree 隔离与提交（A0 baseline + delta）。
4. Lead 在上述通过后授权 **A 类第一批 ≤6**（S0–S5），由 A2 串行执行并逐案记账。
