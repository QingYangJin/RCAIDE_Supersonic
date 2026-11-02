# task-37 旧 VSPAERO 诊断报告（VSPAERO 6.2.0 / OpenVSP 3.26.1 归档证据）

- 任务：D-12D-003 task-37 VSPAERO-OLD-DIAG（只读诊断，零求解器启动）
- 执行：A1（a1-code-dev），2026-11-02
- 证据根：`D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw`（既有归档，只读）
- 方法：静态解析 .vspaero 模板 / run_summary.json / .polar / .history / geom_probe.log / .lod / DegenGeom.csv；**未启动 vspaero、SU2、RCAIDE Mission 或任何物理求解**
- 证据 JSON：`C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/d12d003/a1/vspaero_old_evidence.json`
- 状态：**PARTIAL**（诊断完成；任何"修复后重跑验证"= NOT_RUN，D-12D-002 预算 23/23 已耗尽，禁止新求解启动）

## 0. 结论摘要

1. **W 组 3 个 case（w01/w03/w10）的 .vspaero 模板缺少 `=` 分隔符，VSPAERO 6.2.0 静默忽略 Sref/Cref/Mach/Vinf/Rho/ReCref 等关键行，按默认 Sref=1.0 计算，全部气动系数被放大约 358×**；三个 case 的 polar 结果整体作废（CDo=NaN(IND)，Re 为次正规数 ~1e-318）。这是本次审查发现的**最严重数据有效性缺陷**，直接导致 3/23 次预算作废。
2. 模板格式正常的 3 个 case（baseline、sens_coarse、sens_fine）虽系数未被缩放，但 **Trefftz 平面诱导阻力 CDi 随网格符号翻转**（coarse +3.435e-4 / medium −8.942e-4 / fine −2.261e-2），量级分别为椭圆理论值的 0.28×/0.67×/11.1×；medium AoA=6° 与 fine 多数行出现 **CDtot<0（负阻力）**。→ 旧 VSPAERO 管道的 CDi 不可用（major）。
3. **CL 随网格不收敛**：coarse 0.08387934 → medium 0.08781966（+4.70%）→ fine 0.1082826（相对 coarse **+29.09%**，相对 medium +23.30%）。→ 网格细化未收敛，旧管道不具备定量可信度（major）。
4. **护栏缺陷（blocker 级流程问题）**：5 个非 baseline case 的 `steps.vspaero_setup.returncode=1` 均未阻断后续 `vspaero_solve`；`template_mismatches=[]` 未检出格式差异；polar 结果无有限性/范围校验，NaN、次正规 Re、负阻力直接进入结果链并计账。→ setup 失败必须 fail-fast（少数几行改动即可，属 P 级修复，非物理）。

> 说明：本报告区分【证据】（cited）与【假设 HYPOTHESIS】（未证实机制）。所有数字均来自上列归档文件；未做任何新计算，仅做算术比较（乘除、百分比、与 CL²/(πAR) 比较）。

## 1. 关键证据：W 组模板缺 `=` 导致系数放大 358×

### 1.1 模板格式差异（决定性）
- baseline `baseline/main_wing_baseline_DegenGeom.vspaero:1` = `Sref = 358.250000`；:8 = `AoA = 1.000000`；:14 = `ReCref = 89397005.876766`；:18 = `Symmetry = NO`
- sens_coarse/sens_fine 同为 `key = value` 格式（仅 :8 `AoA = 5.000000`，被命令行 `-fs` 扫描覆盖，见 §5）
- w01_plus1pct `w01_plus1pct/main_wing_w01_plus1pct_DegenGeom.vspaero:1` = `Sref 358.25`（无 `=`）；:14 = `ReCref 89397005.8767656`（无 `=`）；w03/w10 相同
- 逐行统计（`vspaero_old_evidence.json` 字段 `template_no_equals_lines`）：
  - baseline：仅 `Clo2D` 无 `=`（VSPAERO 可容错）
  - sens_coarse / sens_fine：仅 `Clo2D`
  - **w01 / w03 / w10：Sref, Cref, Bref, X_cg, Y_cg, Z_cg, Mach, Vinf, Vref, Rho, ReCref, Clo2D 共 12 行无 `=`**
- 同一管道出现两种模板写法 → 模板生成有两条代码路径（见 §6 建议 R37-2 加回归测试）。

### 1.2 后果量化（证明 Sref 被当作 1.0）
W 组 polar（AoA=2° 行，`*.polar:4`）：
| case | CL | CDo | CDi | Re/1e6 | CL/Sref_case |
|---|---|---|---|---|---|
| w01_plus1pct | 31.77605 | NaN(IND) | -0.3248574 | 5.05857e-318 | 31.77605/361.8325=**0.08782** |
| w03_plus1deg | 31.32113 | NaN(IND) | -0.2599315 | 4.15674e-318 | 31.32113/358.25=**0.08743** |
| w10_plus2 | 31.4877 | NaN(IND) | -0.3189243 | 9.10276e-319 | 31.4877/358.25=**0.08789** |

- 三个 case 的 `CL_printed / (case Sref)` = 0.08782 / 0.08743 / 0.08789，与格式正常 baseline 的 CL(2°)=0.08781966 一致（偏差 ≤0.45%）→ **VSPAERO 实际使用 Sref=1.0，打印系数 = 物理系数 × case Sref**（W 组 CDi/CDtot/CFx 亦同比例放大；w03 打印 CDi=-0.2599，与 baseline CDi 放大值 -0.3204 同号同量级，差异来自 W 组几何/尾涡离散，未逐项复核）。
- Re/1e6 = 5.06e-318 / 4.16e-318 / 9.10e-319 为**次正规数**（≈1e-312 量级）→ ReCref/Vinf/Rho 未被读入；机制未能 100% 确证（可能是默认 0 相乘），标 HYPOTHESIS。
- 另：W 组 `CMm`=-716.43（w03 polar:4 第19列）、`CS`=1.299889e-07（baseline CMm=-2.582589e-02、CS=-5.058147e-10），同属系数放大/参数缺失的次生表现。
- **影响**：W01/W03/W10 三个 case 的全部气动输出**不可用于任何验收/回归判定**；应标记 INVALID 并从证据链剔除。

## 2. CDi 符号随网格翻转（major）

### 2.1 三档网格同工况对比（AoA=2°，`*.polar:4`）
| case | Tess (nXsecs×nPnts) | CL | CDo | CDi | CDtot | E | CL 相对 coarse |
|---|---|---|---|---|---|---|---|
| sens_coarse | 16×17 | 0.08387934 | 0.005076806 | **+0.0003435104** | 0.005420316 | +3.562618 | — |
| baseline (medium) | 16×33 | 0.08781966 | 0.005082831 | **-0.0008942229** | 0.004188608 | -1.500157 | +4.70% |
| sens_fine | 16×65 | 0.1082826 | 0.005168573 | **-0.02260794** | -0.01743937 | -0.09021015 | +29.09% |

- 符号 +/−/−；|CDi| 与椭圆值 CL²/(πAR)（AR=1.83015，πAR=5.7495）之比：coarse 0.281×、medium −0.667×、fine −11.09×。
- `*.history:23` 表头含 `CDtrefftz`；每 case 5 次迭代，`CDtrefftz` 列与 polar `CDi` **逐位相等**（baseline history:28 = -8.942229E-04；coarse/fine 同构）→ **CDi 就是 Trefftz 平面线积分的诱导阻力**，问题定位到 VLM 尾涡/Trefftz 积分环节，而非粘性项。
- history:3-14 给出求解器实际使用的 Sref_=358.25 / Cref_=18.489893 / Bref_=25.604638 / Xcg_=16.821978 / Mach_=2.02 / Rho_=0.1153178 / Vinf_=596.0374 —— 说明格式正常 case 的参考量解析**正确**，排除"参考量错"这一解释。
- E 列在各 AoA 恒定（baseline 恒 -1.500157、coarse 恒 +3.562618、fine 恒 -0.09021015），满足 CDi = CL²/(πAR·E)（三档均精确成立，残差 <1e-4）→ 误差是**与网格绑定的固定乘性因子**（尾涡/网格离散），非随机噪声。
- 负阻力证据：`baseline/*.polar:6`（AoA=6°）CDtot=-2.472157e-03；`sens_fine/*.polar:4` CDtot=-1.743937e-02；`sens_coarse/*.polar` AoA=-2° 行 CL=-0.08387934 而 CDi=+3.435104e-04（负升力仍正诱导阻力）。
- 物理上 E>1（coarse 3.56）不可能；提示 Trefftz 阻力偏小甚至反向。

### 2.2 机制假设（HYPOTHESIS，未证实）
- baseline 求解 stdout（`baseline/geom_probe.log`）：
  - :39 `Number Of Surfaces: 2`，:48/:53 `NumberOfKuttaNodes: 32`（偶极子面 2 片×16 Kutta 节点）
  - :92/:108/:124 `Found a TE node that is common between vortex sheets: 1 and 2` → **两片镜像升力面在对称面根部共享同一 TE 节点/尾涡起点**
  - :55 `Minimum loop area constraint set to: 358.250000`（恰好等于总参考面积/总面元面积，可疑）
  - :61-76 `NumberOfGridLevels_: 3`，agglomeration 960→556→200→**66 loops**（`baseline/setup.log:21-24`），`Starting at level: 3`、`Level: 3 has MaxLoops of: 18`
  - :72 `Model type: VLM`，:6 `VSPAERO v.6.2.0 Compiled Jan 6 2022`，:54 `Total surface area: 358.250000`
- H2（主假设）：两片镜像升力面 + 根弦共享 TE 节点 → 两片尾涡在对称面重叠，Trefftz 线积分对尾涡节点分布极敏感；网格 agglomeration 后（66 loops）涡片穿越/重排导致积分符号翻转、量级失控。
- H3（并列假设）：`Minimum loop area constraint = 358.25`（等于全机面积）使粗化约束失效 → 实际求解极粗（66 loops），VLM 不收敛；CL 网格漂移 +29.09% 与此一致。
- 判别方式（未来，需预算审批，本轮 NOT_RUN）：同 Tess 下 `Symmetry=YES`（单侧机翼由求解器镜像）vs 现有 `Symmetry=NO`（两片镜像件）对比 CDi 符号；或固定网格等级做 only-agglomeration 敏感性。

## 3. 网格不收敛（major）

- 同几何、同 Mach/Re/AoA 仅改 Tess：CL(2°) = 0.08387934 (8/17) → 0.08781966 (16/33) → 0.1082826 (32/65)，相对变化 +4.70% / +23.30% / **+29.09%**（coarse→fine），无收敛趋势。
- CDi 由 +3.4e-4 变到 -2.3e-2（符号与量级均不收敛）。
- 结论：旧 VSPAERO 管道给出的 CDi/CL 不应作为任何 gate 判定依据；历史上若据此做过 CDi 结论，应标记为不可信并重做（重做需新预算，不得自行启动）。

## 4. 流程/护栏缺陷（blocker 级，非物理，可低成本修复）

| ID | 缺陷 | 证据 | 影响 | 建议 |
|---|---|---|---|---|
| D1 | setup 失败不阻断 | `w01_plus1pct/run_summary.json` steps.vspaero_setup.returncode=1 且 template_exists=true，随后 vspaero_solve 仍执行并 status=SOLVED（5/5 非 baseline case 同构） | 失败 setup 后的无效求解被计账 | solve 前断言 setup rc==0；失败即 fail-fast 并标记 case INVALID |
| D2 | 模板格式未校验 | 同文件 template_mismatches=[]（空），但模板实际缺 `=` | 静默产生 358× 错标定数据 | 模板生成后逐行 regex 校验 `^\s*key\s*=\s*value`；或改用求解器 echo 回读 Sref_/Cref_/Mach_/ReCref 断言 |
| D3 | polar 无物理合理性校验 | W 组 CDo=NaN(IND)、Re=5e-318、CDtot<0 直接写入结果 | 无效数据进入证据链/计账 | 校验：np.isfinite、Re>1e5、|CL|<5、CDi>=0、CDtot>0、E 在 (0,1.2] |
| D4 | 结果与预算计账无有效性联动 | 3 个 W case 计为 3 次 NA 启动（D-12D-002 total 23） | 23/23 预算中 3 次产出不可用 | ledger 增加 status=INVALID_DATA 分类；无效数据不计入科学结论（仍计入预算消耗） |
| D5 | 两份模板/两套写盘路径 | 格式差异本身 | 同类问题可复发 | 单一模板生成函数 + 单元测试锁定格式 |

## 5. 其他观察（次要，不影响主要结论）

- 所有非 baseline 模板 :8 为 `AoA = 5.000000`，但求解用命令行 `-fs 2.02 END -2 0 2 4 6 END 0 END`（`run_lf_case.py` 111-124 行附近）覆盖扫描 → polar AoA 行 -2/0/2/4/6 正常；模板 AoA 值仅为遗留噪声，但**易误导审阅者**，建议模板写 0 或注释。
- baseline polar:3（AoA=0°）CL=6.13e-16、CDi=-4.71e-30 → 零升力点数值上正常（非缺陷）。
- baseline CFx 与 CDtot 不严格相等（AoA=2°：CFx=-0.00395854 vs -CDtot=-0.004188608，差 2.3e-4）→ 力分量投影/符号约定需在 freeze_conventions.md 中明确（已在该文件覆盖）。
- `sens_coarse` 与 `sens_fine` 的 `.vspaero` 均正确解析（history 显示 Sref 358.25），故 §2 的 CDi 问题不是参数解析问题，而是尾涡/Trefftz 离散问题。
- .lod strip 表中部分 strip 的 Cd 为负（与 CDi 负值同源）。

## 6. 非物理回归测试建议（R37-1..R37-6，供 regression_test_plan.md 收录）

- R37-1：模板格式单测——对所有 case 生成的 .vspaero 逐行断言 `^s*[A-Za-z_]+s*=s*S+`（除白名单 `Clo2D`? 或统一加 `=`），失败即测试红。
- R37-2：双路径一致性单测——模板生成函数唯一入口；若存在几何覆盖路径（case_geometry.json），与 baseline 路径生成结果字段级相等。
- R37-3：run_summary 护栏单测——构造 setup rc!=0 的 fake summary，断言流水线抛错/标记 INVALID 而非继续 solve（用 mock，不真跑求解器）。
- R37-4：polar 合理性单测——给含 NaN/负阻力/次正规 Re/|CL|>5 的 fake polar，断言校验器拒绝。
- R37-5：参考量回读单测——从 .history 解析 Sref_/Cref_/Bref_/Mach_，断言与请求 REF 一致（容差 1e-6 相对）。本报告使用的就是该手法（history:3-14）。
- R37-6：DegenGeom CSV 结构单测——行 4 component 数=2；LIFTING_SURFACE 行 23 字段；第二片 SurfNdx=1/SymCopyNdx=1/t11=-1；camber 行字段数按 OpenVSP 版本断言（3.26.1=11 列、3.55=14 列），**禁止按字节 diff**（GeomID 随 session 随机）。

## 7. 证据文件清单（全部只读）

- 模板：`{case}/{base}_DegenGeom.vspaero`（基线 6 个 case）
- 汇总：`{case}/run_summary.json`（5 个非 baseline；baseline 无）
- 求解日志：`baseline/setup.log`、`baseline/geom_probe.log`、`baseline/lfv00_stdout.log`
- 结果：`{case}/{base}_DegenGeom.polar`、`{case}/{base}_DegenGeom.history`、`{case}/{base}_DegenGeom.lod`
- 几何：`{case}/{base}_DegenGeom.csv`、`{case}/request.json`、`w01_plus1pct/case_geometry.json`（w03/w10 同）
- 本报告证据 JSON：`C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/d12d003/a1/vspaero_old_evidence.json`
- 本报告依据的旧管道源码：`D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z/scripts/lf_worker.py`（48-55 行 VSPAEROComputeGeometry/期望 DegenGeom.csv）、`run_lf_case.py`（16 行 vspaero.exe 路径、20-22 REF、111-124 模板与命令）

## 8. 状态与限制

- 本诊断 = **PARTIAL**：静态证据充分，机制部分为 HYPOTHESIS（H2/H3）；无任何新求解。
- 修复后验证 = **NOT_RUN**（D-12D-002 预算 23/23 耗尽；需 owner 批新预算后按 R37-1..6 + 单 case 复跑验证）。
- 未修改仓库任何文件；本报告与证据均写入外部记忆目录 `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/d12d003/a1`。
