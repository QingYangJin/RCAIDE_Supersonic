# RCAIDE 官方数字机库（Digital_Hangar）本地镜像

> 2026-10-26 发布说明：本文为获取时的历史索引，环境与执行状态不代表当前状态。当前来源、许可证及本地修改以 [../docs/UPSTREAM.md](../docs/UPSTREAM.md)、[../NOTICE.md](../NOTICE.md) 和根 README 为准。

> 官方仓库 `Digital_Hangar/` 的原样副本：真实机型的整机定义（`.py`）+ 三维模型（`.gltf`），是“飞机设计优化”示例数据的核心。

## 一、来源与可追溯性

| 项目 | 值 |
| --- | --- |
| 仓库 | <https://github.com/leadsgroup/RCAIDE_LEADS> |
| 分支 | `master` |
| commit SHA | `5d80bd5006828c967cc8d3425e29a9b3a3385608` |
| commit 时间 | 2026-07-25T16:47:07Z |
| 获取日期 | 2026-10-21 |
| 获取方式 | `git clone --filter=blob:none --sparse --depth 1` + `git sparse-checkout set Tutorials Digital_Hangar` |
| 原路径 | `Digital_Hangar/`（仓库根目录） |
| 本地路径 | `D:\RCAIDE\digital_hangar\` |
| LICENSE | **AGPL-3.0**（GNU Affero General Public License v3.0），原件见 [`_repository/LICENSE`](_repository/LICENSE) |

仓库根 `README.md`、`README_PyPI.md`、`pyproject.toml`、`LICENSE` 一并存放于 [`_repository/`](_repository/)。**AGPL-3.0 为强传染性许可证，分发修改版需同样以 AGPL 开源。**

## 二、总量统计

| 指标 | 数值 |
| --- | --- |
| 目录总数 | **31** 个 |
| 其中飞行器型号目录 | **30** 个（各含 1 个 `.py` 整机定义） |
| 其中数据目录 | 1 个（`Airfoils_and_Polars/`，33 个翼型/极曲线 txt，无 .py） |
| 文件总数 | **180** 个 |
| 总大小 | **60,252,541 字节 ≈ 57.5 MiB（60.3 MB）**；与上游逐文件字节数完全一致 |
| `.gltf` 三维模型 | 31 个（30 个型号 + `Boeing_787` 额外 1 个共 2 个） |
| `.py` 整机定义 | 30 个 |
| 其它 | 72 个 `.bem`、33 个 `.txt`、11 个 `.res`、3 个 `.png` |

> **文件数/体积与任务描述的差异说明**：任务说明中提及“32 个机型”，经 GitHub API（`contents/Digital_Hangar`、`git/trees?recursive=1`）与本机磁盘双向核对，master 实际为 **31 个目录 / 30 个含 .py 的型号**。此处按实测记录，未凑数。

## 三、机型清单（31 个目录）

| # | 型号目录 | 主 .py 文件 | gltf | 文件数 | 大小 |
| --- | --- | --- | --- | --- | --- |
| 1 | `ATR_72` | `ATR_72.py` | ✅ | 3 | 0.6 MB |
| 2 | `ATR_72_All_Electric` | `ATR_72_all_electric.py` | ✅ | 5 | 1.9 MB |
| 3 | `ATR_72_Parallel_Hybrid` | `ATR_72_cryo_parallel_hybrid_electric.py` | ✅ | 2 | 0.7 MB |
| 4 | `Airbus_A220` | `Airbus_A220_100.py` | ✅ | 2 | 1.1 MB |
| 5 | `Airbus_A320` | `Airbus_A320.py` | ✅ | 2 | 1.0 MB |
| 6 | `Airbus_Vahana` | `Vahana.py` | ✅ | 11 | 4.0 MB |
| 7 | `Airfoils_and_Polars` | *（数据目录，无 .py）* | — | 33 | 0.9 MB |
| 8 | `Blended_Wing_Body` | `BWB.py` | ✅ | 2 | 1.4 MB |
| 9 | `Blended_Wing_Body_Hydrogen` | `BWB_Hydrogen.py` | ✅ | 3 | 1.9 MB |
| 10 | `Boeing_737_800` | `Boeing_737_800.py` | ✅ | 2 | 1.0 MB |
| 11 | `Boeing_747_100` | `Boeing_747_100.py` | ✅ | 2 | 2.1 MB |
| 12 | `Boeing_777` | `Boeing_777_200er.py` | ✅ | 2 | 1.4 MB |
| 13 | `Boeing_787` | `Boeing_787.py` | ✅（2 个 gltf） | 3 | 2.4 MB |
| 14 | `Canadair_Regional_Jet_CRJ_700` | `CRJ_700.py` | ✅ | 2 | 1.0 MB |
| 15 | `Cessna_172` | `Cessna_172.py` | ✅ | 4 | 0.5 MB |
| 16 | `Concorde` | `Concorde.py` | ✅ | 3 | 0.8 MB |
| 17 | `De_Havilland_Canada_DHC_6` | `Twin_Otter.py` | ✅ | 2 | 0.4 MB |
| 18 | `De_Havilland_Canada_DHC_6_Electric` | `Electric_Twin_Otter.py` | ✅ | 4 | 1.0 MB |
| 19 | `De_Havilland_Canada_DHC_8` | `DHC8_100.py` | ✅ | 3 | 0.5 MB |
| 20 | `Elysian_E9X` | `Elysian_E9X_Model.py` | ✅ | 8 | 3.8 MB |
| 21 | `Embraer_E190` | `Embraer_190.py` | ✅ | 2 | 1.0 MB |
| 22 | `Lockheed_C5a` | `Lockheed_C5a.py` | ✅ | 2 | 2.3 MB |
| 23 | `Lockheed_F22` | `Lockheed_F22.py` | ✅ | 2 | 0.5 MB |
| 24 | `Lockheed_F35C` | `Lockheed_F35C.py` | ✅ | 2 | 0.5 MB |
| 25 | `NASA_X_57_Modification_2` | `X57_Maxwell_M2.py` | ✅ | 4 | 0.9 MB |
| 26 | `Ryan_Navion` | `Navion.py` | ✅ | 3 | 0.4 MB |
| 27 | `Stopped_Rotor_EVTOL` | `Stopped_Rotor.py` | ✅ | 14 | 5.3 MB |
| 28 | `Tecnam_P2012` | `Tecnam_P2012.py` | ✅ | 4 | 0.9 MB |
| 29 | `Tilt_Stopped_Rotor_V_tail_EVTOL` | `Tilt_Stopped_Rotor_V_Tail.py` | ✅ | 16 | 7.3 MB |
| 30 | `Tiltrotor_EVTOL` | `Tiltrotor.py` | ✅ | 13 | 5.1 MB |
| 31 | `Tiltwing_EVTOL` | `Tiltwing.py` | ✅ | 21 | 5.3 MB |

**注意**：`.py` 文件名与目录名不一定一致，逐个对照如下：

- `ATR_72_All_Electric` → `ATR_72_all_electric.py`
- `ATR_72_Parallel_Hybrid` → `ATR_72_cryo_parallel_hybrid_electric.py`
- `Airbus_A220` → `Airbus_A220_100.py`
- `Airbus_Vahana` → `Vahana.py`
- `Blended_Wing_Body` → `BWB.py`
- `Blended_Wing_Body_Hydrogen` → `BWB_Hydrogen.py`
- `Boeing_777` → `Boeing_777_200er.py`
- `Canadair_Regional_Jet_CRJ_700` → `CRJ_700.py`
- `De_Havilland_Canada_DHC_6` → `Twin_Otter.py`
- `De_Havilland_Canada_DHC_6_Electric` → `Electric_Twin_Otter.py`
- `De_Havilland_Canada_DHC_8` → `DHC8_100.py`
- `Elysian_E9X` → `Elysian_E9X_Model.py`
- `Embraer_E190` → `Embraer_190.py`
- `NASA_X_57_Modification_2` → `X57_Maxwell_M2.py`
- `Ryan_Navion` → `Navion.py`
- `Stopped_Rotor_EVTOL` → `Stopped_Rotor.py`
- `Tilt_Stopped_Rotor_V_tail_EVTOL` → `Tilt_Stopped_Rotor_V_Tail.py`
- `Tiltrotor_EVTOL` → `Tiltrotor.py`
- `Tiltwing_EVTOL` → `Tiltwing.py`

## 四、运行方式（关键坑，必读）

### 4.1 必须在“该机型自己的目录内”运行

机库脚本用以下方式定位共享翼型目录：

```python
airfoil_file_path = os.path.join(os.path.split(sys.path[0])[0], 'Airfoils_and_Polars') + os.sep
polar_file_path   = os.path.join(os.path.join(os.path.split(sys.path[0])[0], 'Airfoils_and_Polars'), 'Polars') + os.sep
```

它取 **`sys.path[0]` 的父目录** 再拼 `Airfoils_and_Polars`。因此：

| 方式 | 结果 |
| --- | --- |
| ✅ `cd D:\RCAIDE\digital_hangar\Cessna_172` 然后 `python Cessna_172.py` | 正常。`sys.path[0]` = 脚本路径 → 父目录 = `D:\RCAIDE\digital_hangar` → 命中 `digital_hangar\Airfoils_and_Polars` |
| ❌ 在其它目录 `import Cessna_172` / `python -c "import Cessna_172"` / 用 importlib 从别处按路径加载 | 报错 **Airfoil file not in correct directory**。因为此时 `sys.path[0]` 是 `""` 或调用者目录，拼出的路径不存在 |

**结论：不要用 importlib 从其它目录加载机库脚本去跑 `main()`；要跑就 `cd` 进机型目录执行。**

（说明：仅做 `import` 本身不会报错——路径是在 `vehicle_setup()` 调用时才计算的；报错发生在真正构建飞行器时。）

### 4.2 脚本结尾 `plt.show()` 会阻塞

机库脚本同样以 `if __name__ == '__main__': main(); plt.show()` 结尾，批处理时需 `MPLBACKEND=Agg`。

### 4.3 正确跑法示例

```bash
cd /d/RCAIDE/digital_hangar/Cessna_172
MPLBACKEND=Agg D:/RCAIDE/envs/RCAIDE/python.exe Cessna_172.py
```

## 五、依赖判断

30 个机型脚本均**只依赖 RCAIDE 本体**（外加 numpy/matplotlib/scipy），已用 import 扫描确认：

**无需 OpenVSP / AVL / SU2 / Cantera / pyoptsparse。**

本机环境（`D:\RCAIDE\envs\RCAIDE\python.exe`，Python 3.11.17，RCAIDE 1.5.0）已满足上述依赖。

## 六、抽样验证记录（2026-10-21 实测）

对 `Cessna_172` 做**轻量检查**（不跑完整任务仿真）：

| 检查项 | 结果 |
| --- | --- |
| `import Cessna_172` | ✅ 成功（4.96s） |
| `sys.path[0]` 推导 | `D:\RCAIDE\digital_hangar\Cessna_172` |
| `os.path.split(sys.path[0])[0]` | `D:\RCAIDE\digital_hangar` |
| 翼型目录存在性 | ✅ `D:\RCAIDE\digital_hangar\Airfoils_and_Polars` 存在，含 `NACA_4412.txt` |
| `vehicle_setup()` 调用 | ✅ 成功（2.61s），`tag=Cessna_172`，MTOW = 1156.7 kg（≈2550 lb，与真实 Cessna 172 相符） |
| 总计 | 7.57s |

**未跑完整任务仿真**（按要求避免长耗时），也**未伪造结果**。

## 七、配套文件

| 文件 | 说明 |
| --- | --- |
| [`_repository/`](_repository/) | 上游仓库根文件：`LICENSE`(AGPL-3.0)、`README.md`、`README_PyPI.md`、`pyproject.toml` |
| [`../tutorials/README.md`](../tutorials/README.md) | 教程索引（含“官方数字机库”一节，与本文件互为补充） |
| [`../tutorials/tutorial_index.json`](../tutorials/tutorial_index.json) | 结构化索引，`digital_hangar.models` 字段含全部 31 个目录的完整文件清单与字节数 |

---

*本索引由 RCAIDE 资料工程（tutorial-scout）于 2026-10-21 生成。数据版权归 RCAIDE 官方团队，遵循 AGPL-3.0。*
## 八、完整性校验

以 GitHub git trees 接口返回的字节数为基准逐文件比对：**180 个上游文件全部到位，缺失 0，字节数不一致 0**（本地额外 1 个文件为本 README）。

> 本机 Git 默认 `core.autocrlf=true`，检出时文本文件被转成 CRLF，会使字节数比上游多出“行数”个字节。已按“磁盘大小 == 上游大小 + CRLF 个数”的自校验规则把 141 个文件还原为 LF，确保与上游逐字节一致。
