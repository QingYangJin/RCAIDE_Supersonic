# RCAIDE_Supersonic

基于 [RCAIDE-LEADS](https://github.com/leadsgroup/RCAIDE_LEADS) 的超声速飞机分析、教程与优化工作区。

本仓库包含官方教程、数字机库与本地优化扩展。RCAIDE 核心作为 Python 依赖安装；本仓库不是上游 RCAIDE 的完整源码镜像，也不是官方发行版。

## 版权、许可证与上游来源

本项目采用 **GNU Affero General Public License v3.0（AGPL v3）**。本地新增与修改部分采用 `AGPL-3.0-only`；原有文件中的具体许可证声明保持有效。

- 完整许可证：[LICENSE](LICENSE)。版权及第三方声明：[NOTICE.md](NOTICE.md)。
- 上游项目：[leadsgroup/RCAIDE_LEADS](https://github.com/leadsgroup/RCAIDE_LEADS)，由伊利诺伊大学厄巴纳-香槟分校 LEADS 实验室及上游贡献者开发。
- 原有版权与作者署名在相应源码及版权声明文件中保留；本地新增与修改内容的版权范围见第三方声明。
- 教程和数字机库的固定来源提交、本地修改及哈希见 [docs/UPSTREAM.md](docs/UPSTREAM.md)。修改文件带有日期说明，不再将它们称为未经修改的官方副本。
- 研究使用请遵循[上游引用说明](tutorials/_repository/README.md#citing-rcaide)。本仓库不代表上游机构认可本地修改或研究结果。

## 目录

| 目录 | 内容 |
| --- | --- |
| `examples/` | 官方标准大气示例、失速速度和性能接口示例 |
| `tutorials/` | 教程、翼型数据与本地差分进化优化扩展 |
| `digital_hangar/` | 上游数字机库与三维模型 |
| `installation/` | 环境检查器及历史安装资料 |
| `docs/` | 来源、环境范围与历史说明 |
| `.github/workflows/` | Windows 核心依赖与基础数值检查 |

本机环境 `envs/`、输出 `outputs/`、长时优化运行目录、日志、备份和临时抓取数据均不提交。

## Windows 上创建基础环境

需要 Python 3.11。在仓库根目录执行：

```powershell
python -m venv envs\RCAIDE
& '.\envs\RCAIDE\Scripts\python.exe' -m pip install -r requirements.txt
.\run_rcaide.cmd -m pip check
.\run_rcaide.cmd
.\run_rcaide.cmd examples\stall_speed_demo.py
```

已有 Conda 环境位于 `envs\RCAIDE\python.exe` 时，启动器会直接使用它；新建 venv 则使用 `envs\RCAIDE\Scripts\python.exe`。环境检查器随项目目录定位，不要求固定在 `D:\RCAIDE`。输出写入 `outputs/`。

`requirements.txt` 固定 RCAIDE-LEADS 1.5.0，由 pip 解析它的依赖。这是基础安装入口，**不是本机完整环境锁**。GUI、MAML、CPACS 和多保真扩展的来源及恢复边界见 [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)。本机实际版本清单另外保留，未声称已完成干净机器重建验收。

## 运行教程与优化

教程经常使用相对翼型路径，应先切换到相应目录；数字机库也应在机型目录运行。示例：

```powershell
Set-Location tutorials\Optimization_Wing_Planform_Fuel_Burn
& '..\..\run_rcaide.cmd' Optimize.py
```

当前优化入口是 `Optimize.py`，调用本地 `Differential_Evolution.py`，由 `Save_Results.py` 保存结果。运行前检查 `DE_OPTIONS`；当前设置最多请求 24 个工作进程，包含 Windows CPU 限制和内存余量控制。该优化可能耗时较长，不在基础 CI 中执行。

## 当前验证范围

2026-10-26 本机检查：`pip check`、标准大气 100 点四项误差阈值、三个高度失速速度公式核对，以及 VTK/GUI 主模块导入通过。修改后的启动器另经本机运行验证。

这些结果不等同于完整 GUI 交互、所有 Notebook 执行、真实飞机 Mission 工程验收、优化收敛、MAML S1 或研究训练完成。GitHub Actions 的实际状态应以仓库运行结果为准。此次未重新开展长时优化。

历史本机说明保存在 [docs/history/local-installation-20261021.md](docs/history/local-installation-20261021.md)，其中路径和验收记录仅代表当时快照。
