# RCAIDE-GUI 1.2.0 桌面应用验证报告

- **验证日期**：2026-10-21
- **验证环境**：Windows 10 (10.0.26200)，D:\RCAIDE\envs\RCAIDE
- **被验证对象**：RCAIDE-LEADS 1.5.0 + RCAIDE-GUI 1.2.0（PyQt6 桌面应用）
- **报告与脚本目录**：D:\RCAIDE\checks\gui-2026-10-21\
- **截图目录**：D:\RCAIDE\outputs\gui\
- **验证方式**：Qt 离屏模式（QT_QPA_PLATFORM=offscreen）+ 真实窗口，两种方式各跑一遍；逐页签 grab() 截图 + 控件树 JSON 导出 + 加载内置机型做端到端流程

---

## 1. 环境信息（实测）

| 项目 | 值 |
|---|---|
| Python | 3.11.17 (Anaconda) / D:\RCAIDE\envs\RCAIDE\python.exe |
| 平台 | Windows-10-10.0.26200-SP0 |
| rcaide-gui | **1.2.0** |
| RCAIDE-LEADS | **1.5.0** |
| PyQt6 | **6.11.0** |
| vtk | 9.7.1（GL vendor = **Intel**，非软件 Mesa） |
| pyvista / pyvistaqt | 0.49.1 / 0.13.1 |
| pyqtgraph | 0.14.0 |
| matplotlib / numpy | 3.11.2 / 2.4.6 |
| 字体族数量 | offscreen：0（Qt 找不到字体目录，见 §6.1）；设置 QT_QPA_FONTDIR=C:\Windows\Fonts 后：**293**；真实窗口：475 |

### 1.1 安装形态（与预期不同的重要事实）

GUI **不是**一个名为 RCAIDE_GUI 的包目录，而是以**扁平顶层模块**安装到 site-packages 根：

| 路径 | 说明 |
|---|---|
| D:\RCAIDE\envs\RCAIDE\Lib\site-packages\main.py | 279 行，App 主窗口（QMainWindow + QTabWidget 9 页签、File/Documentation 菜单） |
| ...\site-packages\rcaide_io.py | 1427 行，JSON ↔ RCAIDE 对象、全局状态（vehicle / rcaide_configs / rcaide_analyses / mission_data / rcaide_results） |
| ...\site-packages\tabs\ | 9 个页签子包：home, geometry, visualize_geometry, configurations, analysis, mission, performance, run_mission, results_viewer |
| ...\site-packages\common_widgets\ | DataEntryWidget / UnitPickerWidget / ColorPicker / ImageWidget / AnimatedToggle |
| ...\site-packages\app_data\aircraft\ | **20 架机型 JSON** + 翼型坐标 txt（不是 RCAIDE_GUI\app_data\） |
| ...\site-packages\app_data\images\ | logo.png、background.jpg、flowchart.png |
| ...\site-packages\app_data\style_sheets\rcaide_dark_theme.xml | qt-material 主题 |

- 入口点：D:\RCAIDE\envs\RCAIDE\Scripts\rcaide-gui.exe → \`main:main\`（gui_scripts）
- 因此 \`import main\` / \`import tabs\` 即可，**没有 RCAIDE_GUI 这个包名**。

---

## 2. 启动方式（三种，均实测可用）

### 2.1 正常启动（真实窗口，推荐给用户）

\`\`\`bat
D:\RCAIDE\envs\RCAIDE\Scripts\rcaide-gui.exe
\`\`\`

### 2.2 命令行启动（查看控制台打印，排错用）

\`\`\`bat
D:\RCAIDE\envs\RCAIDE\python.exe -c "import main; main.main()"
\`\`\`

### 2.3 无显示器 / 自动化（离屏）

\`\`\`bat
set QT_QPA_PLATFORM=offscreen
set QT_QPA_FONTDIR=C:\Windows\Fonts
D:\RCAIDE\envs\RCAIDE\python.exe D:\RCAIDE\checks\gui-2026-10-21\gui_smoke.py capture --load Cessna_172
\`\`\`

- 离屏模式**能正常构造主窗口、9 个页签、抓控件树、grab() 截图**，但 3D 视口（QtInteractor/QOpenGLWidget）报 \`QOpenGLWidget is not supported on this platform\`，3D 区域为空白 → **3D 截图必须用真实窗口**。
- 启动后 Home 页签有约 4.2 s 的 logo 淡入/淡出开场动画，须 \`processEvents\` 泵 ≥5 s 再截图（见 §6.2）。

---

## 3. 9 个页签逐项说明（用途 / 控件 / 操作顺序）

> 页签顺序与 \`main.py\` 中 \`self.tabs.addTab\` 顺序一致：Home → Vehicle Setup → Visualize Geometry → Configurations → Analyses Setup → Mission Setup → Performance → Run Mission → Results Viewer。

### 3.1 Home（tab_01）

- **用途**：欢迎页 + 入口。顶部 4 个外链按钮（Website / GitHub / Documentation / Community，打开浏览器）；中部横幅图；左下方 \"USING GUI / START FROM SCRATCH\" 流程图（图片）；右下 \"Get Started\" 面板。
- **关键控件**（实测 7 个可交互）：
  - \`QPushButton\` \"Website\" / \"GitHub\" / \"Documentation\" / \"Community\"
  - \`QPushButton\` **\"Load Aircraft and Mission\"** → 调 \`window().load_all()\`，弹 \`QFileDialog\`（起始目录 app_data\aircraft，过滤 \*.json）
  - \`QComboBox\` **\"— Load aircraft —\"** → 扫描 \`app_data\aircraft\*.json\` 自动生成 **20 个机型 + 1 个占位项 = 21 项**；选中即调 \`window().load_file(path)\`，**无需文件对话框**
  - \`QPushButton\` \"Start from Scratch\" → 跳到 Vehicle Setup 页签
- **用户操作顺序（最短路径）**：
  1. 启动 GUI，等首页动画结束（~2-4 s）
  2. 在 \"Get Started\" 面板的**下拉框**里选一个机型（如 Cessna 172）
  3. 程序自动加载：Vehicle Setup 填充、3D 几何生成、Configurations/Analyses/Mission 全部就绪
  4. 直接去 Run Mission 点 \"Simulate Mission\"（见 §4）
- **注意**：\"Load Aircraft and Mission\" 按钮会弹系统文件对话框；自动化脚本里没有下拉框方便，建议用下拉框。
- 截图：\`outputs\gui\startup_01_Home.png\`（离屏，文字为方块）、\`real2_01_Home.png\` / \`real_01_Home.png\`（真实窗口，文字正常，含下拉框）

### 3.2 Vehicle Setup（tab_02，类 GeometryWidget）

- **用途**：整机与各部件参数输入；左侧部件树 + 右侧表单 + 左下 3D 预览。
- **控件**（实测 298 个可交互控件，是全部页签里最多的）：
  - \`QLineEdit\` \"Vehicle Name\"
  - \`QComboBox\` 添加下拉：\`Add Vehicle Component / Add Boom / Add Cargo Bay / Add Fuselage / Add Landing Gear / Add Powertrain / Add Wing\`
  - \`QTreeWidget\` \"Component Tree\"（顶层 Vehicle）
  - 右侧 \`QScrollArea\` 内 6 个 frame（Vehicle / Boom / Cargo Bay / Fuselage / Landing Gear / Powertrain / Wings）
  - Vehicle 表单 44 个字段（Reference Area、Passengers、Max Takeoff Weight、Operating Empty Weight、最大零燃油、Moment of Inertia、Ultimate Load、Positive/Negative Limit Load、Design Dynamic Pressure/Mach/Altitude/Range、V2/VS、Max/Min Lift Coefficient、Maneuver 系列 6 项、Control Systems）+ 3 个下拉（Aircraft Category / FAR Part Classification / Aircraft Service Type）+ 顶部 \"Save\"
  - 左下 \"Aircraft Preview\"（内嵌 VisualizeGeometryWidget，工具栏已隐藏）
- **必填项（要跑通分析所需的最小集）**：Vehicle Name、Reference Area、Max Takeoff Weight / Takeoff Weight、Operating Empty Weight（或 Payload/Passengers 让 FLOPS 质量分析算）、Center of Gravity、Design Mach/Altitude、Max Lift Coefficient。
- **操作顺序**：
  1. 载入机型（Home 下拉框）或 \"Start from Scratch\"
  2. 点左侧部件树顶层 \"Vehicle\" → 右侧填整机参数 → 点 \"Save\"
  3. 下拉框选 \"Add Wing\" / \"Add Fuselage\" / … → 点左侧树中新出现的部件节点 → 右侧改几何 → \"Save\"
  4. Powerplant 在 \"Add Powertrain\"（里面有 Distributors / Propulsors / Systems / Converters / Connections 子页）
  5. 参数改完看左下 3D 预览是否更新
- 截图：\`outputs\gui\loaded_02_Vehicle_Setup.png\`（**真实窗口 + 已加载 Cessna 172**，推荐引用）、\`real2_02_Vehicle_Setup.png\`（未加载，空表单）、\`cessna172_02_Vehicle_Setup.png\`（离屏、已加载、文字为方块但结构完整）

### 3.3 Visualize Geometry（tab_03，类 VisualizeGeometryWidget）

- **用途**：独立 3D 几何查看器（VTK/pyvista），可选部件着色、透明、测量、蓝图对照、截图导出。
- **控件**（39 个可交互 + 大量颜色/透明度控件）：
  - 工具栏按钮：**Display**（生成几何）、Pan、Zoom In、Zoom Out、Front、Side、Top、Isometric、🌄 Background、360° View、📏 Measure（+ Undo / Clear）、📷 Export View（存 PNG）、✈️ Drag Aircraft、📐 Blueprint（+ Adjustor）、\`QCheckBox\` \"Show Gridlines\"
  - 左侧/右侧部件树（点部件可单独调颜色与 Transparency 滑块）
- **操作顺序**：
  1. 先在 Vehicle Setup 准备好几何（或载入机型）
  2. 切到本页签 → 点 **Display** 生成 3D
  3. 用 Front/Side/Top/Isometric 定位，滚轮缩放
  4. 需要留档：📷 Export View；需要叠图纸：📐 Blueprint → 选图片 → 调透明度/缩放
- **实测**：真实窗口下 Cessna 172 三维渲染**正常**（机身+机翼+尾翼+螺旋桨+起落架），GL vendor = Intel，未见远程桌面退化；离屏模式下 3D 区域空白（Qt 平台限制，非程序缺陷）。
- 截图：\`outputs\gui\loaded_03_Visualize_Geometry.png\`、\`real_03_Visualize_Geometry.png\`（真实窗口 3D）；\`cessna172_03_Visualize_Geometry.png\`（离屏，仅控件）

### 3.4 Configurations（tab_04，类 AircraftConfigsWidget）

- **用途**：管理\"飞行构型\"（configs）——每个构型是一套操纵面偏角 / 螺旋桨启用 / 起落架收放状态。
- **控件**：\`QTreeWidget\` \"Configuration Tree\"；右侧滚动区每个构型一个 \`QGroupBox\`（含 Config Name 输入、Control Surfaces 偏角、Propulsors 启用、\"Landing Gear Deployed\" 复选框）；底部 3 个按钮 **New Config** / **Save Config** / **Delete Config**。
- **重要行为**：构型**来自已加载 JSON 的 config_data**（\`build_rcaide_configs_from_geometry()\` 只是把现有 \`rcaide_configs\` 取回来，不会从几何\"推导\"构型）。所以\"从零开始\"时此页签基本是空的，只有载入机型后才有内容。\`New Config\` 会弹 \`QInputDialog\` 输入名字。
- **实测（Cessna_172.json）**：**7 个构型** base、cruise、takeoff、cutback、descent、landing、short_field_takeoff；每个构型显示 2 个操纵面偏角（默认 0.0 / 0.01745 rad = 1°）、构型下拉含 base…short_field_takeoff 全部 7 项。
- **操作顺序**：载入机型 → 在树里点构型 → 改偏角/起落架 → **Save Config**（会弹\"Aircraft configurations saved.\"）→ 后面 Analyses Setup / Mission Setup 的构型下拉才会用新值。
- 截图：\`cessna172_04_Configurations.png\`（离屏）、\`real_04_Configurations.png\`

### 3.5 Analyses Setup（tab_05，类 AnalysisWidget 内嵌 MissionAnalysisWidget）

- **用途**：给**每个构型**挂分析方法（RCAIDE 分析容器）。
- **控件**：\`QGroupBox \"Analyses Setup\"\`、\`QTreeWidget\` 表头 \`Analysis / Enabled\`（10 个分析类目，勾选启用）、各部类子控件（\`AerodynamicsWidget\` 含分析下拉 \"Vortex Lattice Method\"、\`AtmosphereWidget\`（\"1976 US Standard Atmosphere\" / \"Constant Temperature\"）、\`PlanetsWidget\`、\`WeightsWidget\`、\`GeometryWidget\`、\`EnergyWidget\`、\`PropulsionWidget\`、\`CostsWidget\`、\`AeroacousticsWidget\`、\`StabilityWidget\`），底部 **Save Analyses** 按钮。
- **实测（载入 Cessna_172 后）**：
  - 树里 10 个类目：Aerodynamics、Atmospheric、Planets、Weights、Geometry、Energy、Propulsion、Costs、Aeroacoustics、Stability
  - 每个构型（7 个）实际挂的分析：\`Vortex_Lattice_Method\`(aero) + \`U.S. Standard Atmosphere (1976)\` + \`energy\` + \`geometry\` + \`Earth\` + \`Vortex_Lattice_Method\`(stability) + \`weights\`(FLOPS)
- **操作顺序**：载入机型 → 在树里勾选需要的分析类目 → 填子参数 → **Save Analyses** → 去 Mission Setup。
- **⚠️ 已验证的真实缺陷（静默失败，不崩溃）**：点 **Save Analyses 必然抛 \`NameError: name 'values' is not defined\`**（\`tabs\mission\widgets\mission_analysis_widget.py:134\`，\`save_analyses()\` 第一行就引用未定义全局 \`values\`）。后果：
  - 分析**不会**被真正写回 \`rcaide_io.rcaide_analyses\`（函数在入口即崩）
  - 绿色的 \"Analyses saved successfully…\" 提示永不出现
  - 控制台打印 traceback，但**应用不崩溃**：PyQt 吞掉槽函数异常后继续运行，界面上**没有任何错误提示**，属于“点了没反应”的静默失败（用户容易以为已保存成功）
  - 同理 \`tabs\analysis\analysis.py:57\` 也引用未定义 \`values\`（即使修好前一处，这里还会再抛一次）
  - **结论：GUI 内无法修改/保存分析方法；只能使用 JSON 里已有的分析设置**（载入机型时由 \`import_data.analyses_setup\` 建好，所以 Run Mission 仍然能跑）
- 截图：\`cessna172_05_Analyses_Setup.png\`、\`real_05_Analyses_Setup.png\`

### 3.6 Mission Setup（tab_06，类 MissionWidget）

- **用途**：编排任务航段（segment）序列，并生成 RCAIDE mission。
- **控件**：\`QGroupBox \"Mission Setup\"\`（Segment Name 输入框 + **➕ Add Segment** + **💾 Save All Data**）、\`QTreeWidget\` \"Mission Segments\"、**Disable / Enable**、**🗑 Clear Selected**；\`QGroupBox \"Mission Overview\"\`（MissionProfileWidget 航段剖面图 + MissionSummaryTable 表：Segment/Type/Config/Ctrl Pts/Unknowns）；\`QGroupBox \"Segment Details\"\` 里每个航段一个可折叠 \`CollapsiblePanel\`，内含 \`MissionSegmentWidget\`：航段类型下拉（\`Climb / Cruise / Descent / Ground / Single_Point / Vertical Flight\`）、子类型下拉（\`Constant Acceleration-Constant Altitude\`…\`Constant Speed-Constant Altitude\` 共 8 种）、构型下拉（base…short_field_takeoff）、Control Points、Root/Optimize Solver 单选、Altitude、Velocity、Range 等。
- **实测（Cessna_172.json）**：加载后树里已有 **1 个 \"Cruise\" 航段**（子类型 Constant Speed-Constant Altitude，构型 base，16 个控制点；JSON 中 altitude=762.0 m、distance=10000.0 m、angle_of_attack=1°、true_course=0°，UI 速度框显示 51.4444 m/s），右侧 Segment Details 自动展开。
- **操作顺序**：载入机型 → 检查/编辑已有航段 → 需要新航段时填 Segment Name 后 **Add Segment** → 在新面板里选类型/子类型/构型与参数 → **Save All Data**（会打印 \"[Mission Data Saved]\" 并在分析已存在时构建 \`rcaide_io.rcaide_mission\`）→ 去 Run Mission。
- **UI 问题（实测）**：\"➕ Add Segment\" / \"💾 Save All Data\" 两个按钮在浅色状态下深底浅字、对比度偏低（lead 已独立确认）；\`Disable/Enable\`、\`Clear Selected\` 正常。
- 截图：\`loaded_06_Mission_Setup.png\`（真实窗口 + 已加载）、\`cessna172_06_Mission_Setup.png\`（离屏 + 已加载）、\`real2_06_Mission_Setup.png\`（未加载，空态）

### 3.7 Performance（tab_07，类 MultiDisciplinaryWidget）

- **用途**：不跑完整任务，直接做单项气动/性能分析并出图。
- **控件**：\"Analysis:\" 下拉（**7 种**：Take-Off Field Length、Landing Field Length、Stall Speed、V-n Diagram、Payload-Range Diagram、Aerodynamic Polars、Load & Trim Diagram）、\"Configuration:\" 下拉（7 个构型）、\"Parameters:\" 动态参数区、**Run Analysis** 按钮、\"Clear\"、结果表 \`QTableWidget\`（初始 0×3）、绘图区（pyqtgraph）、外加一整套 \"Plot Parameters\"（Line Width/Style/Color、Markers、Autoscale、Axis Font Size、Grid、Legend、**Save Plots**）。
- **依赖校验（源码 \`_validate_prerequisites\`）**：部分分析需要已保存的 analyses（\"Save analyses in the Analyses Setup tab first.\"），Payload-Range / Load & Trim 还需要 mission。**由于 Save Analyses 有 bug（§3.5），在\"从零开始\"场景下这些提示会反复出现；载入机型后因为 analyses 来自 JSON，校验可通过。**
- **操作顺序**：载入机型 → 选 Analysis → 选 Configuration → 填参数 → Run Analysis → 看表/图 → Save Plots。
- 截图：\`cessna172_07_Performance.png\`、\`real_07_Performance.png\`

### 3.8 Run Mission（tab_08，类 SolveWidget）

- **用途**：执行 RCAIDE 任务求解并出 20+ 张结果图。
- **控件**：**\"Simulate Mission\"** 大按钮；\`QTreeWidget\` \"Plot Options / Enabled\"（4 个类目：**Aerodynamics、Energy、Mission、Stability**，每个下面若干可勾选绘图项，如 Plot Aircraft Velocities / Aerodynamic Coefficients / Drag Components / Lift Distribution / Flight Conditions / Flight Trajectory / Longitudinal & Lateral Stability 等）；右侧绘图滚动区（初始 4 个 PlotWidget：TAS/EAS/Mach/CAS）；\"Plot Parameters\" 面板（线宽/线型/颜色/标记/Autoscale/字号/网格/Legend/Save Plots）。
- **行为**：点击 → 禁用其它页签 + 弹模态 \`QProgressDialog\`（\"Running mission simulation… Close this window to cancel.\"）→ 后台 QThread 里 \`mission.evaluate()\` → 完成后写 \`rcaide_io.rcaide_results\` 并按勾选项渲染图；失败则弹 \"Mission Simulation Failed\" 对话框（\`QDialog.exec()\`，**模态阻塞**）。
- **实测结论**：**能真正进入求解器**（控制台依次打印质量分解表 → \`Performing Weights Analysis\` → \`Creating aerodynamic surrogate ...\`），但**默认设置下在 ~27 分钟内未完成**（见 §4 详述）。
- 截图：\`cessna172_08_Run_Mission.png\`、\`real_08_Run_Mission.png\`

### 3.9 Results Viewer（tab_09，类 ResultsViewerWidget）

- **用途**：树形浏览/导出/绘图查看求解结果。
- **控件**：\"Source:\" 下拉（**Mission Results / Performance Analysis**）、**Refresh**、**Copy Shown Path / Copy Shown Value**、**Export Shown / Export All**、搜索框（占位符 \"Search fields: altitude, velocity, mass, lift, throttle...\"）、路径检查框（占位符 \`rcaide_results.segments[0].conditions.freestream.altitude\`）+ **Inspect Path**、结果树（Name/Class-Size/Value，初始 0 项，空态提示 \"No results loaded.\"）、右侧详情面板、绘图区（X axis 下拉：Time (s) / Range (m) / Altitude (m) / Mach / Index）+ **Plot / Add / Clear Plot**。
- **操作顺序**：Run Mission 跑完（或 Performance 出结果）→ 切到本页签 → 点 **Refresh** → 展开树找字段（或用搜索框/Inspect Path 直接跳）→ 需要留档就 Export Shown / Export All，需要曲线就选 X 轴后 Plot。
- 截图：\`cessna172_09_Results_Viewer.png\`、\`real_09_Results_Viewer.png\`

---

## 4. 端到端最小流程验证（真实结果）

### 4.1 走通的部分（含实测数据）

自动化脚本 \`gui_smoke.py\`（离屏）驱动**真实 GUI 控件**：

| 步骤 | 操作 | 结果 |
|---|---|---|
| 1 | \`main.App()\` 构造主窗口 | ✅ 9 页签齐全，标题 \"RCAIDE GUI\" |
| 2 | Home → 机型下拉框（21 项，第 14 项 = Cessna 172）→ \`setCurrentIndex\` | ✅ 触发 \`_load_example\` → \`window.load_file(...Cessna_172.json)\`，**0.7 s 完成**，下拉框自动复位为 \"— Load aircraft —\" |
| 3 | 读 \`rcaide_io\` 状态 | ✅ vehicle.tag=\`Cessna_172\`；wings=\`main_wing, horizontal_stabilizer, vertical_stabilizer\`；fuselages=\`fuselage\`；landing_gears=\`main_gear, nose_gear\`；networks=\`fuel\`；reference_area=**16.165 m²**；passengers=**4**；MTOW=**1156.66 kg** |
| 4 | Configurations | ✅ 7 构型（base/cruise/takeoff/cutback/descent/landing/short_field_takeoff）渲染成 7 个 GroupBox |
| 5 | Analyses Setup | ✅ 7 套分析容器，每套含 aero VLM + 1976 大气 + energy + geometry + Earth + stability VLM + weights(FLOPS) |
| 6 | Mission Setup | ✅ 1 个 \"Cruise\" 航段（Constant Speed-Constant Altitude，构型 base，16 ctrl pts，altitude 762.0 m / distance 10000.0 m / AoA 1°） |
| 7 | Performance | ✅ 分析下拉 7 项、构型下拉 7 项就绪 |
| 8 | Run Mission 点 \"Simulate Mission\" | ⚠️ 见 4.2 |
| 9 | Results Viewer | ⚠️ 无结果可看（因第 8 步未产出） |

### 4.2 未走通的部分（失败点，如实记录）

- 点 \"Simulate Mission\"（等价于直接调 \`rcaide_io.rcaide_mission.evaluate()\`）后：**求解器确实启动了**，控制台依次输出
  1. 质量分解表（Operating Empty 1164.12 kg / Payload 408.23 kg / Takeoff 1156.66 kg …）
  2. \`Performing Weights Analysis\` → FLOPS
  3. \`Creating aerodynamic surrogate ...\`
- 随后**卡在气动代理模型训练阶段 ~27 分钟未返回**，被我主动终止（未得到结果，不伪造）。
- **原因（已定位到源码）**：Cessna_172.json 的 aero 分析使用 \`Vortex_Lattice_Method\`，默认 \`settings.use_surrogate = True\`（\`Vortex_Lattice_Method.py\` 的 initialize 调 \`train_AVL_surrogates\`），训练网格默认很大：攻角 \`[-2,0,2,5,8,12,45]°\` × Mach \`[0.1,0.3,0.5,0.65,0.85,0.9,1.3,1.5,2,2.5,3.5]\`（7×11=77 基态）再做扰动组合（\`angle/speed/rate/control_surface purtubation\`、sideslip/aileron/elevator/rudder/flap/slat、u/v/w、p/q/r 等多维采样），单个算例是 30(展向)×15(弦向)=450 涡格的 VLM。这是**算法规模问题，不是 GUI 卡死**。
- **可行的绕过办法（供用户选择，已由源码确认机制）**：
  1. 在 Analyses Setup 里把 Aerodynamics → Vortex Lattice Method 的 **use_surrogate 关掉**（单点 VLM 直接算，秒级~分钟级）；或打开 \`reuse_training_data\` 复用已生成的 \`...training\` pickle（第 2 次起秒开）。
  2. 减小 \`number_of_spanwise_vortices / number_of_chordwise_vortices\`（30×15 → 15×8）。
  3. 改用轻量机型（DHC8_100 / Navion）或只做 Performance 单项分析。
  4. **注意**：因 §3.5 的 Save Analyses bug，方案 1、2 在本版 GUI 里**改不动**（改完点保存会 NameError）。可行的替代是用 File → \"Open RCAIDE JSON...\" 打开一份**预先改好 settings 的 JSON**（可先用文本编辑器改 \`analysis_data\` 里的 \`use_surrogate\`/\`vortices\`），再载入运行。
  5. 或者不依赖 GUI：直接用 RCAIDE 本体（\`objective\` 脚本方式）跑，GUI 只做几何查看。

### 4.3 端到端结论

> **\"启动 → 载入内置机型 → 各页签数据联动 → 进入求解\"这条链路是通的（实测）；\"求解返回结果 → Results Viewer 看图\"在默认 Cessna_172 配置下因 VLM 代理训练规模过大而在 ~27 min 内未完成，属性能/配置问题，不是崩溃。**
>
> 另有两个**确定性缺陷**会挡住\"从零开始\"的用户：① Save Analyses 静默失败（NameError），导致 GUI 内无法建立/修改分析且无任何提示；② Configurations 不会从几何推导构型，只回显 JSON 中的构型。因此**推荐使用\"从内置机型库加载\"而不是\"Start from Scratch\"**。

---

## 5. 推荐的最短上手路径（可直接写进中文使用指南）

1. 双击 \`D:\RCAIDE\envs\RCAIDE\Scripts\rcaide-gui.exe\` 启动（首次等 3-5 s 首页动画）。
2. **Home 页签** → 右下 \"Get Started\" → 下拉框选 **Cessna 172**（下拉项显示为 \"Cessna 172\"，实际文件 app_data\aircraft\Cessna_172.json）。
3. 自动跳到 **Visualize Geometry** 并显示 3D 整机；用 Front/Side/Top/Isometric + 滚轮检查外形，必要时 📷 Export View 存图。
4. **Vehicle Setup**：左侧部件树（Vehicle / Wings / Fuselages / Landing Gears / Powertrain）逐项点开核对数据（44 个整机字段已自动填好）。
5. **Configurations**：确认 7 个构型（base / cruise / takeoff / cutback / descent / landing / short_field_takeoff），需要时改偏角与起落架状态 → Save Config。
6. **Analyses Setup**：只**看**不改（本版保存有 bug）；确认每构型挂着 VLM 气动 + 1976 大气 + FLOPS 质量等。
7. **Mission Setup**：确认已有 \"Cruise\" 航段参数（高度/速度/构型）→ 需要多航段就 Add Segment → **Save All Data**。
8. **Performance**（可选，快）：选 Take-Off Field Length / Stall Speed / V-n Diagram 等 → Run Analysis 先看单项结果。
9. **Run Mission**：勾选想看的 Plot Options → 点 **Simulate Mission**；**先做好等待几分钟~几十分钟的准备**，或按 §4.2 关掉 surrogate（需改 JSON 后重新载入）。
10. **Results Viewer** → Refresh → 树里找 \`segments[i].conditions.*\`（或直接 Inspect Path）→ Export / Plot。
11. 保存工作：File → \"Save RCAIDE JSON...\"（存整机+构型+分析+任务，不含求解结果）；File → \"Open RCAIDE JSON...\" 载入。
12. VSP 互操作：File → Import VSP / Export VSP（需 \`openvsp\` 包，本环境**未安装**，会弹 \"OpenVSP Not Available\" 提示）。

---

## 6. 已知限制与注意事项

### 6.1 离屏截图的字体假象（不是真实缺陷）
- \`QT_QPA_PLATFORM=offscreen\` 下 Qt 报 \`QFontDatabase: Cannot find font directory .../PyQt6/Qt6/lib/fonts\`，**字体族 = 0**，截图里所有文字变成方框（tofu）。
- 解法：设 \`QT_QPA_FONTDIR=C:\Windows\Fonts\` → 字体族 **293**，文字正常（本报告 §1 已实测）。
- 真实窗口模式字体族 475、默认 Microsoft YaHei UI，中文正常。**给用户看的截图请用真实窗口。**

### 6.2 Home 页签异步渲染
- 窗口 \`show()\` 后需 1-2 s 才绘制完整首页；且启动有 4.2 s 的 logo 淡入淡出。自动化截图必须 \`processEvents\` 泵 ≥5 s，否则只能抓到 logo。

### 6.3 离屏下 3D 不可用
- offscreen 平台不支持 QOpenGLWidget：\`QOpenGLWidget is not supported on this platform\` / \`Failed to create context\`，Visualize Geometry 与 Vehicle Setup 的预览区为空白。**3D 必须真实窗口**。
- 本机真实窗口下 GL vendor = **Intel**，Cessna 172 渲染正常，未见远程桌面（GameViewer 虚拟显示）导致的退化。若用户经远程/串流使用出现黑屏或极慢，请本地直连显示器再试。

### 6.4 GUI 代码缺陷（1.2.0 实测）
| 位置 | 问题 | 影响 |
|---|---|---|
| \`tabs/mission/widgets/mission_analysis_widget.py:134\` | \`save_analyses()\` 引用未定义全局 \`values\` | **Save Analyses 静默失败**：抛 NameError 但被 Qt 吞掉——控制台有 traceback、界面无任何错误提示、绿色成功提示不出现、分析未保存、进程不退出 |
| \`tabs/analysis/analysis.py:57\` | 同样引用未定义 \`values\` | 即使修好上一处，这里仍会抛错 |
| \`tabs/configurations/configurations.py:282\` | \`build_rcaide_configs_from_geometry()\` 只回显已有 configs | \"从零开始\"时 Configurations 页签无构型可编辑 |
| \`tabs/run_mission/run_mission.py:421\` | 失败时 \`QDialog.exec()\` 模态阻塞 | 自动化/无人值守场景会卡住；求解失败必须人工点 OK |

### 6.5 求解性能
- 默认 VLM \`use_surrogate=True\` + 30×15 涡格 + 7×11 训练网格 → 首次 evaluate 可能 >30 min。
- 第二次运行若 \`reuse_training_data\` 打开（pickle 已生成）会快很多；也可降网格或关 surrogate（须改 JSON，见 §4.2）。
- Run Mission 期间其它页签被禁用、显示模态进度框，**关闭进度框 = 取消**。

### 6.6 其它
- \`app_data\` 位于 **site-packages 根**（不是 RCAIDE_GUI 包内），自定义机型 JSON 可直接放进 \`app_data\aircraft\`，重启后出现在 Home 下拉框。
- Import/Export VSP 依赖 \`openvsp\` Python 包，本环境未安装。
- 9 页签截图与控件清单 JSON 命名规则：\`outputs\gui\<tag>_NN_<TabName>.png\` 与 \`checks\gui-2026-10-21\<tag>_NN_<TabName>.json\`（\`tag\` = startup / cessna172）。

---

## 7. 产物清单

### 7.1 截图（D:\RCAIDE\outputs\gui\）
| 文件 | 说明 |
|---|---|
| \`startup_01_Home.png\` … \`startup_09_Results_Viewer.png\` | 离屏、未加载机型（文字为方块，仅作控件结构证据） |
| \`cessna172_01_Home.png\` … \`cessna172_09_Results_Viewer.png\` | 离屏、**已加载 Cessna 172**（文字为方块，布局与数据可见） |
| \`loaded_02_Vehicle_Setup.png\` | **真实窗口 + 已加载**，44 字段已填（推荐） |
| \`loaded_03_Visualize_Geometry.png\` | **真实窗口 + 3D 整机**（推荐） |
| \`loaded_06_Mission_Setup.png\` | **真实窗口 + Cruise 航段详情**（推荐） |
| \`real_01..09_*.png\` / \`real2_01,02,06_*.png\` | 真实窗口、未加载机型（空态对照） |

### 7.2 控件清单 JSON（D:\RCAIDE\checks\gui-2026-10-21\）
- \`startup_01..09_*.json\`、\`cessna172_01..09_*.json\`：每个页签完整控件树（\`tree\`）+ 类型统计与可交互控件摘要（\`summary\`）。
  - 交互控件数量实测：Home 7、Vehicle Setup 298、Visualize Geometry 39、Configurations 4→172（加载后）、Analyses Setup 83、Mission Setup 9→49（加载后）、Performance 25、Run Mission 17、Results Viewer 15。

### 7.3 脚本与日志
- \`gui_smoke.py\`：离屏冒烟 + 截图 + 控件树导出 + 端到端驱动（用法见文件头注释；\`capture\` / \`simulate\`、\`--load <机型>\`、\`--tag\`、\`--real\`、\`--direct\`）。
- \`gui_smoke.log\`、\`run_cessna.log\`：上述两次运行的完整控制台输出（含 [GL]/[FONT]/[STATE]/[PROBE] 与求解器打印，可复查 27 min 超时的原始证据）。
