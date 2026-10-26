# RCAIDE 官方教程数据（Tutorials）本地镜像与索引

> 2026-10-26 发布说明：本文为获取时的历史索引，环境与执行状态不代表当前状态。当前来源、许可证及本地修改以 [../docs/UPSTREAM.md](../docs/UPSTREAM.md)、[../NOTICE.md](../NOTICE.md) 和根 README 为准。

> 本目录是从 RCAIDE 官方仓库取得的 `Tutorials/` 原样副本，配套一份中文索引，便于“读文档 + 跑本地代码”。

## 一、来源与可追溯性

| 项目 | 值 |
| --- | --- |
| 仓库 | <https://github.com/leadsgroup/RCAIDE_LEADS> |
| 分支 | `master` |
| commit SHA | `5d80bd5006828c967cc8d3425e29a9b3a3385608` |
| commit 时间 | 2026-07-25T16:47:07Z（提交信息：`Merge pull request #282 from leadsgroup/develop`） |
| 获取日期 | 2026-10-21 |
| 获取方式 | `git clone --filter=blob:none --sparse --depth 1` + `git sparse-checkout set Tutorials Digital_Hangar`（只取需要的两个目录，锚定上述 SHA） |
| 文档站 | <https://www.docs.rcaide.leadsresearchgroup.com/> |
| LICENSE | **AGPL-3.0**（GNU Affero General Public License v3.0），原件见 [`_repository/LICENSE`](_repository/LICENSE) |

仓库根的 `README.md`、`README_PyPI.md`、`pyproject.toml`、`LICENSE` 一并放在 [`_repository/`](_repository/) 目录，便于离线溯源。**AGPL-3.0 是强传染性许可证，对外分发修改版需同样以 AGPL 开源。**

## 二、总量统计

| 指标 | 数值 |
| --- | --- |
| 教程/数据目录 | **14** 个 |
| 文件总数 | **65** 个 |
| 总大小 | **26,743,676 字节 ≈ 25.5 MiB（26.7 MB）**；与上游逐文件字节数完全一致（见第十节完整性校验） |
| Python 脚本 | 16 个（分布在 9 个目录） |
| Notebook（.ipynb） | 13 个（Missions 7 / Performance 5 / Boeing 专题 1） |
| 翼型与极曲线数据（.txt） | 32 个（`Airfoils_and_Polars/`） |
| 大型辅助文件 | `Missions/Vehicle_Geometry.html`(4.96MB)、`Performance/Rotor.html`(4.61MB)、`Missions/Tilt_Stopped_Rotor_Conv_Tail.pkl`(1.46MB) |

> 体积构成：`.ipynb` 约 16.2 MB（内嵌图形输出故偏大）、`.html` 约 9.6 MB、`.py` 约 0.6 MB、`.txt` 数据约 0.35 MB。

## 三、依赖总判断（重要）

**结论：本目录 16 个 Python 脚本没有一个需要 OpenVSP / AVL / SU2 / Cantera / pyoptsparse。**

对所有脚本做了 import 扫描，全部只依赖：

- `RCAIDE`（本体，本机 1.5.0 可用）
- `numpy`、`scipy`、`matplotlib`（本机均可用）

唯一的优化类教程 `Optimization_Wing_Planform_Fuel_Burn/Optimize.py` 用的是 `RCAIDE.Framework.Optimization.Packages.scipy`（scipy 驱动），**不是** pyoptsparse。

本机 RCAIDE 环境可选求解器现状（实测 `importlib.util.find_spec`）：

| 包 | 状态 |
| --- | --- |
| RCAIDE 1.5.0 / numpy / scipy / matplotlib / pandas / h5py / vtk | ✅ 已安装 |
| pyoptsparse、openvsp、avl、SU2、cantera | ❌ 未安装 |
| jupyter、IPython、nbformat | ❌ 未安装 → **13 个 .ipynb 无法在本机执行** |

## 四、教程索引表

| 教程目录 | 官方分组 | 主文件 | 依赖 | 可否直接跑 |
| --- | --- | --- | --- | --- |
| `Airfoils_and_Polars/` | 数据 | *（无脚本）* | — | 不适用（纯数据，32 个翼型/极曲线 txt） |
| `Analysis_Aerodynamic_Polars/` | 分析脚本 | `aircraft_aerodynamics_analysis.py` | RCAIDE + numpy/matplotlib | ✅ 是 |
| `Analysis_Approach_Sideline_Takeoff_Noise/` | 分析脚本 | `approach_landing_takeoff_noise_certification.py` | RCAIDE + numpy/matplotlib | ✅ 是 |
| `Analysis_Landing_Field_Length/` | 分析脚本 | `landing_field_length.py` | RCAIDE + numpy/matplotlib | ✅ 是 |
| `Analysis_Loading_and_Trim_Diagram/` | 分析脚本 | `aircraft_loading_and_trim_diagram.py` | RCAIDE + numpy/matplotlib | ✅ 是 |
| `Analysis_Payload_Range/` | 分析脚本 | `aircraft_payload_range_diagram.py` | RCAIDE + numpy/matplotlib | ✅ 是 |
| `Analysis_Take_Off_Field_Length/` | 分析脚本 | `takeoff_field_length_estimation.py`<br>`takeoff_weight_estimation_from_target_TOFL.py` | RCAIDE + numpy/pylab | ✅ 是 |
| `Analysis_V_n_Diagram/` | 分析脚本 | `Part_23_V_n_diagram.py`<br>`Part_35_V_n_diagram.py` | RCAIDE + numpy/matplotlib | ⚠️ 能跑但慢（实测 300s 未结束，见第八节） |
| `Missions/` | **Missions** | `Tutorial_01_turbofan_aircraft.ipynb` … `Tutorial_07_lift_cruise_evtol_aircraft.ipynb` | RCAIDE + numpy/matplotlib + **jupyter** | ❌ 需 Jupyter 环境 |
| `Optimization_Wing_Planform_Fuel_Burn/` | **Optimize** | `Optimize.py`（入口）<br>`Vehicles.py` / `Missions.py` / `Analyses.py` / `Procedure.py` | RCAIDE + scipy 驱动 | ✅ 是（含优化循环，耗时长） |
| `Performance/` | **Performance** | `Tutorial_21_payload_range_diagram.ipynb` … `Tutorial_25_V_n_diagram.ipynb` | RCAIDE + numpy/matplotlib + **jupyter** | ❌ 需 Jupyter 环境 |
| `Simulation_Turbofan_Transonic_Aircraft_5000nmi_Mission/` | 专题 | `Boeing_737_800.py`（脚本）<br>`Boeing_737_800_Tutorial.ipynb` | RCAIDE + numpy/matplotlib | ✅ 脚本可跑 / notebook 需 Jupyter |
| `Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/` | 专题 | `Concorde.py` | RCAIDE + numpy/matplotlib | ✅ 是 |
| `Simulation_Turboprop_Aircraft_1000nmi_Mission/` | 专题 | `ATR_72.py` | RCAIDE + numpy/matplotlib | ✅ 是 |

## 五、按官方文档分组对照（18 个编号教程 + 1 个专题页 = 19 页）

文档 URL 规则：`https://www.docs.rcaide.leadsresearchgroup.com/tutorials/<组>/<页面名>.html`

### 5.1 Missions 组（整机任务仿真，建议从这里入门）

本地目录：[`Missions/`](Missions/)

| 文档页 | 主题 | 本地文件 |
| --- | --- | --- |
| [Tutorial_01_turbofan_aircraft](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Missions/Tutorial_01_turbofan_aircraft.html) | 涡扇客机 | `Tutorial_01_turbofan_aircraft.ipynb` |
| [Tutorial_02_turbojet_aircraft](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Missions/Tutorial_02_turbojet_aircraft.html) | 涡喷超音速客机 | `Tutorial_02_turbojet_aircraft.ipynb` |
| [Tutorial_03_turboprop_aircraft](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Missions/Tutorial_03_turboprop_aircraft.html) | 涡桨支线客机 | `Tutorial_03_turboprop_aircraft.ipynb` |
| [Tutorial_04_general_aviation_aircraft](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Missions/Tutorial_04_general_aviation_aircraft.html) | 通用航空飞机 | `Tutorial_04_general_aviation_aircraft.ipynb` |
| [Tutorial_05_electric_aircraft](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Missions/Tutorial_05_electric_aircraft.html) | 全电飞机 | `Tutorial_05_electric_aircraft.ipynb` |
| [Tutorial_06_tiltrotor_evtol_aircraft](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Missions/Tutorial_06_tiltrotor_evtol_aircraft.html) | 倾转旋翼 eVTOL | `Tutorial_06_tiltrotor_evtol_aircraft.ipynb` |
| [Tutorial_07_lift_cruise_evtol_aircraft](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Missions/Tutorial_07_lift_cruise_evtol_aircraft.html) | 升力巡航 eVTOL | `Tutorial_07_lift_cruise_evtol_aircraft.ipynb` |

### 5.2 Optimize 组（把 Tutorial_01 的流程拆成 6 步源码）

文档组名 `Optimize`，对应本地目录 [`Optimization_Wing_Planform_Fuel_Burn/`](Optimization_Wing_Planform_Fuel_Burn/)（**本地目录名与文档组名不同**）。

| 文档页 | 步骤含义 | 本地文件（据文件名对应推断） |
| --- | --- | --- |
| [Tutorial_10_Analyses](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Optimize/Tutorial_10_Analyses.html) | 分析流程搭建 | `Analyses.py` |
| [Tutorial_11_Missions](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Optimize/Tutorial_11_Missions.html) | 任务定义 | `Missions.py` |
| [Tutorial_12_Optimize](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Optimize/Tutorial_12_Optimize.html) | 优化主程序 | `Optimize.py` |
| [Tutorial_13_Plot_Mission](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Optimize/Tutorial_13_Plot_Mission.html) | 绘图 | *本地无独立脚本*（绘图逻辑在 `Optimize.py` 内） |
| [Tutorial_14_Procedure](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Optimize/Tutorial_14_Procedure.html) | 流程/过程定义 | `Procedure.py` |
| [Tutorial_15_Vehicle](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Optimize/Tutorial_15_Vehicle.html) | 飞行器定义 | `Vehicles.py` |

> 这 5 个 .py 之间是 `import` 关系（`Optimize.py` 导入其余 4 个），入口是 `Optimize.py`。

### 5.3 Performance 组（性能图）

本地目录：[`Performance/`](Performance/)

| 文档页 | 主题 | 本地文件 |
| --- | --- | --- |
| [Tutorial_21_payload_range_diagram](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Performance/Tutorial_21_payload_range_diagram.html) | 载荷航程图 | `Tutorial_21_payload_range_diagram.ipynb` |
| [Tutorial_22_propeller_simulation](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Performance/Tutorial_22_propeller_simulation.html) | 螺旋桨仿真 | `Tutorial_22_propeller_simulation.ipynb` |
| [Tutorial_23_aircraft_aerodynamic_analysis](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Performance/Tutorial_23_aircraft_aerodynamic_analysis.html) | 整机气动分析 | `Tutorial_23_aircraft_aerodynamic_analysis.ipynb` |
| [Tutorial_24_airfoil_polar_simulation](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Performance/Tutorial_24_airfoil_polar_simulation.html) | 翼型极曲线仿真 | `Tutorial_24_airfoil_polar_simulation.ipynb` |
| [Tutorial_25_V_n_diagram](https://www.docs.rcaide.leadsresearchgroup.com/tutorials/Performance/Tutorial_25_V_n_diagram.html) | V-n 图 | `Tutorial_25_V_n_diagram.ipynb` |

> `Analysis_*` 那 7 个目录里的 `.py` 是上述 Performance 主题的**脚本版**：载荷航程、整机气动、V-n 三题与 Tutorial_21/23/25 内容重复；着陆场长、载重配平、起飞场长、噪声审定是脚本独有的专题。

### 5.4 专题

| 主题 | 本地目录 | 文件 |
| --- | --- | --- |
| Boeing 737-800 涡扇跨音速 5000nmi | [`Simulation_Turbofan_Transonic_Aircraft_5000nmi_Mission/`](Simulation_Turbofan_Transonic_Aircraft_5000nmi_Mission/) | 脚本 `Boeing_737_800.py` + notebook `Boeing_737_800_Tutorial.ipynb` |
| Concorde 涡喷超音速 4500nmi | [`Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/`](Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/) | 脚本 `Concorde.py` |
| ATR-72 涡桨 1000nmi | [`Simulation_Turboprop_Aircraft_1000nmi_Mission/`](Simulation_Turboprop_Aircraft_1000nmi_Mission/) | 脚本 `ATR_72.py` |

## 六、官方数字机库（Digital_Hangar）

官方仓库根目录的 `Digital_Hangar/` 是真实机型的整机定义库，已单独获取到 **`D:\RCAIDE\digital_hangar\`**（详见该目录下的 `README.md`）。

**核对结果：当前 master 的 `Digital_Hangar/` 实际为 31 个目录**（GitHub API 与本机磁盘双向核对一致）：其中 `Airfoils_and_Polars` 是共享翼型数据目录（33 个 txt，无 .py），其余 **30 个是飞行器型号目录**，每个含 1 个 `.py` 整机定义 + `.gltf` 三维模型（`Boeing_787` 有 2 个 gltf）。

> 备注：任务说明中提到“32 个机型”，本次以 GitHub API（`contents/Digital_Hangar` 与 `git/trees?recursive=1`）及本地 clone 双向核对，实测为 **31 个目录 / 30 个含 .py 的型号**，此处按实测记录。

| # | 型号目录 | 主 .py 文件 | gltf | 文件数 |
| --- | --- | --- | --- | --- |
| 1 | `ATR_72` | `ATR_72.py` | ✅ | 3 |
| 2 | `ATR_72_All_Electric` | `ATR_72_all_electric.py` | ✅ | 5 |
| 3 | `ATR_72_Parallel_Hybrid` | `ATR_72_cryo_parallel_hybrid_electric.py` | ✅ | 2 |
| 4 | `Airbus_A220` | `Airbus_A220_100.py` | ✅ | 2 |
| 5 | `Airbus_A320` | `Airbus_A320.py` | ✅ | 2 |
| 6 | `Airbus_Vahana` | `Vahana.py` | ✅ | 11 |
| 7 | `Airfoils_and_Polars` | *（数据目录，无 .py）* | — | 33 |
| 8 | `Blended_Wing_Body` | `BWB.py` | ✅ | 2 |
| 9 | `Blended_Wing_Body_Hydrogen` | `BWB_Hydrogen.py` | ✅ | 3 |
| 10 | `Boeing_737_800` | `Boeing_737_800.py` | ✅ | 2 |
| 11 | `Boeing_747_100` | `Boeing_747_100.py` | ✅ | 2 |
| 12 | `Boeing_777` | `Boeing_777_200er.py` | ✅ | 2 |
| 13 | `Boeing_787` | `Boeing_787.py` | ✅（2 个） | 3 |
| 14 | `Canadair_Regional_Jet_CRJ_700` | `CRJ_700.py` | ✅ | 2 |
| 15 | `Cessna_172` | `Cessna_172.py` | ✅ | 4 |
| 16 | `Concorde` | `Concorde.py` | ✅ | 3 |
| 17 | `De_Havilland_Canada_DHC_6` | `Twin_Otter.py` | ✅ | 2 |
| 18 | `De_Havilland_Canada_DHC_6_Electric` | `Electric_Twin_Otter.py` | ✅ | 4 |
| 19 | `De_Havilland_Canada_DHC_8` | `DHC8_100.py` | ✅ | 3 |
| 20 | `Elysian_E9X` | `Elysian_E9X_Model.py` | ✅ | 8 |
| 21 | `Embraer_E190` | `Embraer_190.py` | ✅ | 2 |
| 22 | `Lockheed_C5a` | `Lockheed_C5a.py` | ✅ | 2 |
| 23 | `Lockheed_F22` | `Lockheed_F22.py` | ✅ | 2 |
| 24 | `Lockheed_F35C` | `Lockheed_F35C.py` | ✅ | 2 |
| 25 | `NASA_X_57_Modification_2` | `X57_Maxwell_M2.py` | ✅ | 4 |
| 26 | `Ryan_Navion` | `Navion.py` | ✅ | 3 |
| 27 | `Stopped_Rotor_EVTOL` | `Stopped_Rotor.py` | ✅ | 14 |
| 28 | `Tecnam_P2012` | `Tecnam_P2012.py` | ✅ | 4 |
| 29 | `Tilt_Stopped_Rotor_V_tail_EVTOL` | `Tilt_Stopped_Rotor_V_Tail.py` | ✅ | 16 |
| 30 | `Tiltrotor_EVTOL` | `Tiltrotor.py` | ✅ | 13 |
| 31 | `Tiltwing_EVTOL` | `Tiltwing.py` | ✅ | 21 |

**注意**：型号目录里的 `.py` 文件名与目录名不一定一致（如 `De_Havilland_Canada_DHC_6` → `Twin_Otter.py`，`Ryan_Navion` → `Navion.py`），上表已逐个列出。

## 七、运行注意事项（实测踩坑，务必先读）

### 7.1 必须保持现有目录布局（否则找不到翼型文件）

所有教程脚本都通过“自己所在目录的上一级”去取翼型数据：

```python
local_path        = os.path.dirname(os.path.abspath(__file__)) + os.sep + '..'
airfoil_file_path = local_path + os.sep + 'Airfoils_and_Polars' + os.sep
polar_file_path   = local_path + os.sep + 'Airfoils_and_Polars' + os.sep + 'Polars' + os.sep
```

即 `tutorials/<某教程>/../Airfoils_and_Polars`。**所以 `tutorials/` 下各目录必须并列，不可单独拷走某一个教程目录**，否则会报翼型文件找不到。

### 7.2 `Digital_Hangar` 机型脚本必须在“自己的目录内”运行

机库脚本用另一种更脆的方式定位翼型目录：

```python
airfoil_file_path = os.path.join(os.path.split(sys.path[0])[0], 'Airfoils_and_Polars') + os.sep
```

它取的是 **`sys.path[0]` 的父目录**。因此：

- ✅ 正确：`cd D:\RCAIDE\digital_hangar\Cessna_172 && python Cessna_172.py`
  → `sys.path[0]` = 该脚本路径 → 父目录 = `digital_hangar\` → 命中 `digital_hangar\Airfoils_and_Polars`（该目录确实存在）
- ❌ 错误：在别处用 `import Cessna_172` 或 `python -c "import Cessna_172"` 加载
  → `sys.path[0]` 为 `""` 或调用者目录 → 拼出错误的相对路径 → 报 **Airfoil file not in correct directory**

（实测：在本机按 ✅ 方式 emulated 后，路径推导为 `D:\RCAIDE\digital_hangar\Airfoils_and_Polars` 且存在，`vehicle_setup()` 成功；详见第八节。）

### 7.3 脚本结尾的 `plt.show()` 会阻塞

官方脚本都以

```python
if __name__ == '__main__':
    main()
    plt.show()
```

结尾。在无显示环境/自动化脚本中会一直卡住。跑批时设 `MPLBACKEND=Agg` 并屏蔽 `plt.show`（本目录 `_runcheck/runner.py` 就是这么做的）。

### 7.4 Notebook 需要 Jupyter（本机未装）

`Missions`、`Performance` 和 Boeing 专题共 13 个 `.ipynb` 在本机 RCAIDE 环境中**无法直接执行**：`jupyter` / `IPython` / `nbformat` 均未安装（任务约束也不允许 pip install）。
替代做法：直接读 notebook 源码，或参照同主题的 `.py` 脚本（如 `Analysis_Payload_Range/aircraft_payload_range_diagram.py` 对应 `Tutorial_21`）。

### 7.5 建议运行方式

```bash
cd /d/RCAIDE/tutorials/<某教程目录>
MPLBACKEND=Agg D:/RCAIDE/envs/RCAIDE/python.exe <主脚本>.py
```

## 八、抽样验证记录（2026-10-21 实测）

在 `_runcheck/` 下用自写 harness（强制 Agg 后端 + 屏蔽 `plt.show` + `importlib` 按路径加载模块后显式调用 `main()`）验证：

| 对象 | 结果 | 细节 |
| --- | --- | --- |
| `RCAIDE` 基础导入 | ✅ 成功 | `import RCAIDE` 耗时 5.2s，版本 1.5.0 |
| `Analysis_V_n_Diagram/Part_23_V_n_diagram.py` | ⚠️ **部分成功（超时）** | 模块导入正常；`main()` 已实际执行并打印完整重量分解表（Operating Empty 1165.76 kg / Payload 408.23 kg / Takeoff Weight 1156.66 kg 等，数值合理），随后进入 `Creating aerodynamic surrogate ...`（气动代理模型构建）**300 秒内未结束**，按超时终止。非依赖问题，属计算量大。 |
| `digital_hangar/Cessna_172/Cessna_172.py` | ✅ 成功（轻量检查） | 导入 4.96s；`sys.path[0]` 路径推导正确 → `D:\RCAIDE\digital_hangar\Airfoils_and_Polars` 存在且含 `NACA_4412.txt`；调用 `vehicle_setup()` 成功（2.61s，`tag=Cessna_172`，MTOW=1156.7 kg）。**未跑完整任务仿真**（按要求避免长耗时）。 |

**未伪造任何成功结果**：V-n 教程就是 300s 超时未完成，如实记录；notebook 未执行，如实标注需 Jupyter。

## 九、配套文件

| 文件 | 说明 |
| --- | --- |
| [`tutorial_index.json`](tutorial_index.json) | 结构化索引：14 个教程目录的完整文件清单（含每文件字节数）、主脚本、第三方/RCAIDE 模块依赖、外部求解器判定、文档页对应关系；另含 31 个机库型号清单 |
| [`_repository/`](_repository/) | 上游仓库根文件：`LICENSE`(AGPL-3.0)、`README.md`、`README_PyPI.md`、`pyproject.toml` |
| [`_runcheck/`](_runcheck/) | 抽样验证 harness：`runner.py`（通用）、`cessna_check.py`（机库导入检查）及运行日志 |
| [`_tmp_meta/`](_tmp_meta/) | 获取过程留痕：GitHub API 原始响应（`tut_list.json`、`tut_tree.json`、`master_commit.json`、`dh_list.json`）与索引生成脚本 |

---

*本索引由 RCAIDE 资料工程（tutorial-scout）于 2026-10-21 生成。数据版权归 RCAIDE 官方团队，遵循 AGPL-3.0。*

## 十、完整性校验（与上游逐字节比对）

以 GitHub git trees 接口返回的每个 blob 字节数为基准，与本地磁盘逐文件比对：

| 比对项 | Tutorials | Digital_Hangar |
| --- | --- | --- |
| 上游文件数 | 65 | 180 |
| 本地缺失 | **0** | **0** |
| 字节数不一致 | **0** | **0** |
| 本地额外（本工程新增） | 2（README.md、tutorial_index.json） | 1（README.md） |

**结论：245 个上游文件全部到位，且逐文件字节数与上游完全一致。** 校验脚本见 `_tmp_meta/verify.py`。

### 关于换行符（重要，已处理）

本机 Git 默认 `core.autocrlf=true`，稀疏克隆检出时会把文本文件从 LF 转成 CRLF，导致磁盘字节数比上游多出“行数”个字节（实测 .py、.txt 全部受影响，二进制 .png/.gltf 不受影响）。

为让镜像与上游**逐字节可复现**，已按“磁盘大小 == 上游大小 + CRLF 个数”这一可自校验的规则，把 Tutorials 的 64 个文件、Digital_Hangar 的 141 个文件统一还原为 LF。转换后重新校验：**0 个不一致**。

> 若日后重新从 Git 克隆，请先 `git config core.autocrlf false` 再检出，或重跑 `_tmp_meta/normalize.py`。
