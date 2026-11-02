# OpenVSP 3.55.0 API 兼容矩阵（task-36 / D-12D-003 Round-1 A1）

- 任务：NEW-API-COMPAT — 用侧装 OpenVSP 3.55.0 重建 12D 基线主翼（baseline + W10 tip_twist=+2°），验证几何导出/分析 API 是否可替代归档 3.26.1，并给出移植与回归风险。**零物理求解**（未启动 vspaero.exe / SU2 / RCAIDE Mission / DOE）。
- 侧装：D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64（vspaero.exe 811520 B，v7.2.2；archive sha256 f1fde65f…）
- 运行环境：D:/RCAIDE/envs/RCAIDE/python.exe 3.11.17；`os.add_dll_directory(root)` + `sys.path.insert(0, root/python/openvsp)` 以及 python/degen_geom、python/utilities、python/openvsp_config；`import openvsp` → "OpenVSP 3.55.0"（2176 个导出名）。
- 证据目录（OUT）：C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/d12d003/a1/
- 机器可读明细：`api_compat_checks.csv`（28 行 C01–C28，含 method/evidence/status/risk，本文件为其人类可读版）

## 结论摘要

1. **几何层完全兼容**：按归档 builder 映射重建的 baseline STL 与 3.26.1 归档 STL **顶点集逐点一致**（shared_xy=527、old_only=0、new_only=0、bbox delta=[0,0,0]、dArea=-2.27e-13 m²、dVol=+6.06e-11 m³）；仅 ASCII 顶点顺序/三角化不同导致 sha256 不同（centroid x 相差 1.7e-4 m）。Sref=358.25000000000006 m² 与 REF 358.25 一致到 <1e-13 相对（geometry_diff.json / logs_build_compare.txt）。
2. **分析管线发生破坏性变更（C04，blocker 级移植项）**：3.55 中 `ExecAnalysis("VSPAEROComputeGeometry")` 返回结果 id 且只写 Unnamed.csf(20 B)/Unnamed.vkey(251 B)/Unnamed.vspgeom(224357 B)，**不再写 Unnamed_DegenGeom.csv**；而归档 `lf_worker.py:50-55,66` 明确期望该 CSV 并以其存在作为 status=ok。（3.55 中改用 `ExecAnalysis("DegenGeom")` 可生成 Unnamed_DegenGeom.csv 503789 B + .m 509722 B — 移植时应改调该分析。）
3. **DegenGeom CSV 格式变更（C06，兼容风险）**：3.55 的 camber 节点行写满 14 字段（新增 xxCamber,xyCamber,xzCamber），3.26.1 只写 11 字段（且旧 CSV 与其自身 14 字段表头矛盾）；对应 CHANGELOG 3.35.0 "Fix missing fields in DegenGeom file."。任何按旧列数解析 CSV 的代码需同步；旧 VSPAERO 6.2.0 对 14 字段 CSV 的兼容性 **NOT_RUN**。
4. **结果捕获契约（C08）**：必须以 ExecAnalysis 返回的 id 调 GetAllDataNames/Get*Results；传分析名会返回空 tuple 并 stderr `Error Code: 15, Desc: GetAllDataNames::Invalid ID <name>`。归档 wave_worker.py:75 的 `FindLatestResultsID(aname)` 回退路径仍可用（存在性已验，未执行执行路径）。
5. **仓库现有 API 无真实缺失（C17）**：扫描 277 个 .py（research/concorde_metaopt 含 optimization_runs/scripts），38 个 vsp.* 名字中 35 个真实 API 在 3.55 全部存在；3 个"missing"均为误报（audit.py:64 是 vsp.exe 路径字符串、make_drag_component_ledger.py:131 是 dict.get、test_openvsp_geometry.py:84 是 mock.params）。openvsp_geometry.py:69 的 `GetNumXSec(surf)` 合约在 3.55 不变。
6. **顺序约束未复现（C23，单次探针，不作保证）**：归档 lf_worker.py:3-4 记录"VSPAEROComputeGeometry 必须先于 WriteVSPFile，否则第二次 ExecAnalysis 挂起"；3.55 单次探针 build → WriteVSPFile → ExecAnalysis 正常返回，但仅 1 次、非回归测试。
7. **零求解预算**：本任务 0 次空气动力求解启动，D-12D-002 预算（23/23）未消耗。

## 兼容矩阵（C01–C28 摘要，逐行证据见 api_compat_checks.csv）

| ID | 项 | 3.55 结果 | 状态 | 风险/说明 |
|---|---|---|---|---|
| C01 | import 与版本 | "OpenVSP 3.55.0"，2176 导出名 | PASS | 需 DLL 目录 + 4 条 sys.path 配方 |
| C02 | ListAnalysis | 22 个分析名（含 VSPAERO* 7 个） | PASS | 名称清单与 3.26.1 无明显删减 |
| C03 | 分析名作为 module 函数 | 22/22 hasattr=False | CHANGED_BUT_OK | 只可经 ExecAnalysis 调用；仓库代码已如此 |
| C04 | VSPAEROComputeGeometry 执行 | exec OK（id NEDINKC），产 csf/vkey/vspgeom，**无 DegenGeom.csv** | **CHANGED（blocker 移植项）** | 归档 lf_worker.py:50-55,66 在 3.55 会 failed_no_degen_geom |
| C05 | DegenGeom 执行 | exec OK（id WPNQEZI），产 csv 503789 B + m 509722 B | PASS | 3.55 下生成 DegenGeom CSV 的正确入口 |
| C06 | DegenGeom CSV 字段 | camber 行 11→14 字段（xxCamber,xyCamber,xzCamber） | CHANGED | 旧解析器需改；对应 CHANGELOG 3.35.0 修复 |
| C07 | CSV GeomID | 逐 session 随机（YNUTMSSYKB→FNDBJWFVBR） | INFO | 禁止字节级 diff；需 mask ID |
| C08 | 结果捕获契约 | 用返回 id 可读；传名字 → Error Code 15 | PASS | 归档 wave_worker.py:75 回退可用 |
| C09 | VSPAEROComputeGeometry result names | Analysis_Duration_Sec/GeometrySet/Mesh_GeomID/ThinGeometrySet/VSPGeomFileName | PASS | 新增 vspgeom 文件名/网格 id 输出 |
| C10 | DegenGeom result names | Analysis_Duration_Sec/Degen_BlankGeoms/Degen_DegenGeoms（2 geom id） | PASS | 可按 geometry 取 degen 结果 |
| C11 | 分析 API 面 | 缺失 GetAnalysisName/GetAnalysisInputGroup/Unit/Default；其余存在 | PASS_WITH_GAPS | 仓库代码未引用缺失项 |
| C12 | VSPAEROComputeGeometry 输入名 | CullFrac,CullFracFlag,FindBodyWakesFlag,GeomSet,ModeID,NRef,SingleGeomID,Symmetry,ThinGeomSet,UseModeFlag | PASS | 与归档使用面一致 |
| C13 | DegenGeom 输入名 | ModeID,Set,UseModeFlag,WriteCSVFlag,WriteMFileFlag | PASS | — |
| C14 | WaveDrag 输入名（仅签名） | Mach,ModeID,NumRotSects,NumSlices,SSFlow_vec,Set,SymmFlag,UseModeFlag | PASS（未执行） | 物理分析 NOT_RUN（约束） |
| C15 | EmintonLord 输入名（仅签名） | Area_vec,X_vec | PASS（未执行） | 数组输入需 SetDoubleAnalysisInput(...,0) |
| C16 | SinglePoint/Sweep/DegenGeom 输入名 | SinglePoint=[]，VSPAERODegenGeom=[]，Sweep=45 名 | PASS（未执行） | 完整清单在 api_probe_inventory.json |
| C17 | 仓库 API 使用面 | 35 个真实 API 全存在；3 误报 | PASS | 无需改 openvsp_geometry.py |
| C18 | 几何复现 | 顶点集一致、dArea -2.27e-13、dVol +6.06e-11 | PASS | sha 不同仅因 ASCII 顺序 |
| C19 | STL 导出 | ASCII；baseline 650534 B / w10 650932 B | PASS | 与归档同格式同三角数 2160 |
| C20 | STEP 导出 | baseline 344294 B / w10 344805 B | PASS | 新能力（归档 LF worker 未导 STEP） |
| C21 | Tessellation | Tess_U=16/Tess_W=33 生效（parm id EJDCMAQWKVX/JWJJBWGHOOY） | PASS | 复现归档 medium 网格 |
| C22 | XSec API 合约 | GetXSecSurf(geom,0)→GetNumXSec(surf) 正常；传 geom 报 GetNumXSec::Can't Find XSecSurf | PASS | 与仓库代码一致 |
| C23 | 顺序探针 | build→WriteVSPFile→ExecAnalysis 返回 OK LKXKVET | PASS_SINGLE_PROBE | 3.26.1 的挂起约束未在 3.55 复现（仅 1 次） |
| C24 | Sref/参考量 | TotalArea 358.25000000000006，TotalSpan 25.604638251691824，TotalChord 10.512823436932134 | PASS | 与 run_lf_case.py:20 REF 一致 |
| C25 | W10 +2° 施加 | xsec3 Twist=2.0；dz 仅 tip 带 |y|≥12.1 m，old/new 完全一致 | PASS | 见下"W10 解读注意" |
| C26 | vspgeom | 224357 B；格式 v3（CHANGELOG 3.45.0） | INFO | VSPAERO 7.2.2 读取 **NOT_RUN**（禁求解） |
| C27 | panel 默认文件 | CHANGELOG 3.29.0：*.vspaero 默认 for panel models，DegenGeom 仍 thick-surface 默认 | INFO | 解释 3.55 新增 vspgeom 产物 |
| C28 | 预算 | 0 次 air-dynamics solver 启动 | PASS | D-12D-002 23/23 未动 |

## W10 解读注意（C25）

- 几何差异 **只** 出现在 tip band：|y|<12.0 m 的所有 span 带 dz 恒 0；|y|∈[12.0,14.0) 有 10/54 个 shared-xy 顶点 dz≠0，max_abs=0.043895999597 m，且 3.26.1 与 3.55 完全一致 → W10 确实施加，且 3.55 复现 3.26.1 的扭转行为。
- 该 0.0439 m **不能** 当作 tip TE 位移解读：shared-xy 仅 377/1082 顶点（扭转会把表面点的 x,y 一起挪动，固定 (x,y) 配对比较是采样伪影）；理论 tip TE 位移 = 0.9731361054965724 × tan2° = 0.03398266162414291 m，仅供量级对照。
- 结论：W10 变量 → 几何链 **CONFIRMED-APPLIED**（参数级 + 点集级），数值解读以参数/理论值为准。

## 移植影响与建议（供 L 决策，本任务不改代码）

1. lf_worker.py 若切 3.55：把 `ExecAnalysis("VSPAEROComputeGeometry")` + 期望 Unnamed_DegenGeom.csv 的路径（50-55、66）改为 `ExecAnalysis("DegenGeom")`（或两者都跑：ComputeGeometry 产 vspgeom 供 VSPAERO 7.2.2 面板模型用，DegenGeom 产 CSV 供旧 VSPAERO 6.2.0 厚表面用）——需 L 授权的修复卡，本任务只读。
2. 若沿用旧 VSPAERO 6.2.0：DegenGeom CSV 变成 14 字段，须验证 6.2.0 读取兼容性（**NOT_RUN**，需 L 授权的最小求解验证，会消耗预算）。
3. 回归测试建议见下节（非物理，可在 CI 跑）。

## 非物理回归测试建议（task-36 部分）

- R1：3.55 几何重建 vs 归档 STL：比对唯一顶点集（容差 1e-6 m），断言 shared_xy≥基线、old_only=new_only=0、bbox delta=0、|dArea|<1e-9 m²、|dVol|<1e-8 m³（本任务实测值可作基线）。
- R2：Sref 断言 TotalArea 与 request.json sections 梯形公式一致（rel<1e-12）。
- R3：W10 断言 xsec3 Twist==2.0 且 old/new dz 带内一致；禁止用单点 dz 做阈值。
- R4：API 面断言：`ListAnalysis()` 含 22 名；ExecAnalysis 返回 str id；GetAllDataNames(名字) 抛 Error Code 15（捕获断言）；GetAllDataNames(id) 非空。
- R5：CSV 格式断言：header 含 xxCamber/xyCamber/xzCamber，data 行字段数==header 字段数（防再出 3.26.1 的不一致）。
- R6：结果捕获断言：result names 集合与 api_probe_inventory.json 记录一致（VSPAEROComputeGeometry 5 名、DegenGeom 3 名）。
- 以上均不调用 solver，可在项目 python + 侧装 VSP 下跑。

## 证据文件（OUT 下）

geometry_diff.json；api_probe_inventory.json；api_usage_scan.json；exec_vspaerocomputegeom.json；exec_degengeom.json；api_compat_checks.csv；api_inventory.json；geometry/{baseline,w10_plus2}/{main_wing_*.stl,*.vsp3,*.step}；analysis_scratch/{vspaerocomputegeom,degengeom,order_write_then_analysis}/；logs_api_inventory.txt、logs_api_usage_scan.txt、logs_build_compare.txt、logs_exec_vspaerocomputegeom.txt、logs_exec_degengeom.txt、logs_capture_vspaerocomputegeom.txt、logs_capture_degengeom.txt、logs_order_test.txt、logs_cmp_degen_struct.txt、logs_diff_degen_csv.txt（后二者在 task-37 补充读取归档 CSV 时生成）。
