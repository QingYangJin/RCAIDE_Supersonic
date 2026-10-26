# RCAIDE 本机安装与使用

2026-10-21 补充完成：**RCAIDE-GUI 图形界面使用指南**与**官方教程数据**落地。
- 图形界面与教程数据使用：[RCAIDE_GUI_使用指南.md](/D:/RCAIDE/RCAIDE_GUI_使用指南.md)
- 教程数据目录：[`tutorials/`](/D:/RCAIDE/tutorials)（官方 Tutorials，含 13 个 notebook + 17 个脚本）
- 官方数字机库：[`digital_hangar/`](/D:/RCAIDE/digital_hangar)（32 架真实机型定义）

2026-10-13 已重新检查基础可用情况。Python 库使用说明见
[RCAIDE 使用说明](/D:/RCAIDE/RCAIDE_USER_GUIDE.md)，本次证据见
[可用情况检查](/D:/RCAIDE/RCAIDE_AVAILABILITY_2026-10-13.md)。
下面保留首次安装说明与 2026-10-12 的验收记录。

安装完成日期：2026-10-12（Asia/Shanghai）。

已通过 Anaconda 创建 RCAIDE 环境，并通过该环境内的 pip 安装
RCAIDE-LEADS 1.5.0。官方 PyPI 在 2026-10-12 19:40:31 的查询结果为
1.5.0，已安装版本与之相同，安装包 SHA-256 也与官方元数据一致。

## 环境与入口

| 项目 | 本机配置 |
| --- | --- |
| 工作目录 | `D:\RCAIDE` |
| 环境名称 | `RCAIDE` |
| 环境路径 | `D:\RCAIDE\envs\RCAIDE` |
| Python | `3.11.17` |
| Python 解释器 | `D:\RCAIDE\envs\RCAIDE\python.exe` |
| 启动器 | `D:\RCAIDE\run_rcaide.ps1` |
| 分析输出 | `D:\RCAIDE\outputs` |

RCAIDE 是 Python 分析库。使用下列启动器运行本项目脚本，启动器会固定环境、
检查解释器与库的实际路径，并使用 `-E -s` 隔离 Python 环境变量和用户包目录。
自带示例还会在执行分析前再次检查环境。启动器不依赖终端是否事先激活环境。

## 运行

在 PowerShell 中运行官方标准大气验收示例：

```powershell
Set-Location -LiteralPath 'D:\RCAIDE'
.\run_rcaide.ps1
```

运行飞机失速速度接口示例：

```powershell
.\run_rcaide.ps1 'D:\RCAIDE\examples\stall_speed_demo.py'
```

运行 Python 模块或交互终端：

```powershell
.\run_rcaide.ps1 -PythonArgs @('-m', 'pip', 'check')
.\run_rcaide.ps1 -PythonArgs @('-i')
```

运行自己的脚本时，将脚本绝对路径作为启动器参数传入。
如需在新脚本中复用环境检查，可参照
`D:\RCAIDE\examples\stall_speed_demo.py` 的开头。

需要手动激活时，在 Anaconda Prompt 中执行：

```text
conda activate D:\RCAIDE\envs\RCAIDE
```

环境保存在自定义位置，新终端中应使用完整路径激活，避免名称搜索路径造成混淆。
VS Code 已在本项目设置中指定上述解释器及终端启动参数；
编辑器界面中的实际选择尚未通过 GUI 验证。

## 已通过的验收

- `pip check`：没有损坏的依赖关系。
- 版本检查：已安装 1.5.0，与上述查询时点的 PyPI 最新正式版一致。
- 来源检查：安装包 SHA-256 与官方 PyPI 元数据一致。
- 路径检查：Python 和 RCAIDE 包均位于 `D:\RCAIDE\envs\RCAIDE`。
- 官方标准大气示例：100 个高度点计算完成，四项结果的最大绝对误差均通过原参考阈值。
- 本地失速速度示例：三个高度的接口计算完成，并与该方法的升力公式核对。
- 环境保护：Anaconda base 解释器在导入 RCAIDE 前被检查器拒绝。
- 启动器：忽略注入的 PYTHONPATH，禁用用户包目录，并正确传递测试退出码 7。

官方示例输出：
`D:\RCAIDE\outputs\official_atmosphere.png`、
`D:\RCAIDE\outputs\official_atmosphere.json`。
官方源文件按提交固定保留，来源与许可证位于
`D:\RCAIDE\examples\official`。

失速速度示例采用假设的轻型飞机参数，仅证明接口和对应公式可运行。
本次没有验证完整飞机任务、多学科优化及 OpenVSP、AVL、SU2 等可选外部工具。

## 安装记录与恢复

`D:\RCAIDE\installation` 中保留：

- `verification.json`：实际版本、路径、依赖版本与安装包哈希。
- `pypi-version-check.json`、`pypi-metadata.json`：官方版本查询时间与元数据。
- `pip-install-report.json`：pip 记录的下载来源及各安装包哈希。
- `environment.yml`：命名为 RCAIDE、包含 pip 依赖的环境快照。
- `requirements-lock.txt`：根据已安装包的结构化清单生成的版本固定清单。
- `requirements-freeze-raw.txt`：原始 pip freeze，含 Conda 构建机本地路径，仅用于溯源。
- `conda-explicit.txt`：同平台 Conda 包构建的精确清单，不含 pip 安装包。
- 安装、示例、环境拦截与启动器验证日志。

`requirements-lock.txt` 是版本快照，不是带全部依赖哈希的跨平台锁文件；
恢复时先用 Conda 恢复 Python 与基础环境，再处理 pip 依赖并重新验收。

安装时遇到 Conda 证书错误，已通过导出 Windows 受信任公共证书生成
`D:\RCAIDE\installation\windows-ca-bundle.pem`，并在该次安装命令中显式使用它。
HTTPS 校验始终保留，未修改全局 Conda 配置。
证书包不含私钥；换机器或信任链变化时应重新生成。

后续向该环境安装依赖，可使用：

```powershell
.\run_rcaide.ps1 -PythonArgs @(
    '-m', 'pip', '--isolated', 'install',
    '--cert', 'D:\RCAIDE\installation\windows-ca-bundle.pem',
    '--index-url', 'https://pypi.org/simple',
    'PACKAGE_NAME'
)
```

将 `PACKAGE_NAME` 替换为所需包名。升级后重新运行 `pip check`、
代表性分析示例，并刷新安装记录与依赖快照。
