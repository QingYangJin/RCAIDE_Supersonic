# P1–P3 12D 修复卡实施记录（W10 OpenVSP + 12D 设计空间）

- 日期：2026-10-30（Asia/Shanghai）
- 分支：`research/concorde-metaopt`（PR #3 保持 open，未合并 main）
- 修复基线：`39c410c48388a5029975e999d475b460e6239f05`（首份静态审查包提交）
- 依据：Issue #4 D-12D-001 与负责人 2026-10-30 六项决策（①12D 变量集 ②固定机身取模型计算值 ③批准修复卡 ④批准仅机翼 VLM/CFD 预算 ⑤回执可发布 ⑥清理无关临时文件）
- 本记录只覆盖**非物理**代码修复与纯几何导出核验；**未运行任何 RCAIDE Mission / VSPAERO / SU2**，未消耗物理预算。

## 1. R-1 12D 设计空间配置与加载器

| 项 | 内容 |
| --- | --- |
| 新增文件 | `research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml`（241 行） |
| 变量集 | W01–W10 + V01–V02 共 12 个声明变量（id/单位/界/scale/target 与 15D 文件一致） |
| 固定项 | F01 `fuselage_length`=61.66 m、F02 `fuselage_fineness`=4.30、F03 `fuselage_height_width_ratio`=1.152778，写入 `fixed_variables` 块并记录 `source`（owner decision item 2，采用模型计算值而非上游教程声明值） |
| 兼容性 | 15D 文件未改动；`design_set` 缺省为 `15d`，旧配置与历史 run 不受影响 |
| 加载器 | `aircraft/design_space.py`：`DESIGN_SETS`(:83)、`FixedVariable`(:146)、`DesignSpace.design_set/fixed_variables`(:195)、`expand()`(:218，拒绝调用方传入固定变量，固定值永远取配置 baseline)、`full_baseline_dict()`(:245)、`check_cross_constraints()`(:300，先 expand)、loader 校验(:358–370)、`_build_fixed_variable`、`_validate_baseline_geometry`(:565，12D 先 expand 再校验，否则缺 fuselage_length 会 KeyError) |
| 回归测试 | `tests/test_design_space_12d.py`（16 tests：12 维/3 固定、expand 15 名顺序、固定值不可被调用方覆盖、缺/多/错序/未知 design_set 拒绝、15D 恒等、baseline_geometry 一致性） |

## 2. R-2 几何构建器 12D 入口

- `aircraft/geometry_builder.py::build_geometry_from_design_space()`(:83)：`physical` 缺省取 baseline；长度必须等于 `space.design_dim`（:93 错误信息）；对 12 个声明变量做 bounds/cross 校验后用 `space.expand(values)`(:100) 展开为 15 名，再调用既有的 15 值 `geometry_model.build_geometry()`。
- 15D 调用路径与行为不变；所有既有 15D 测试通过。

## 3. R-3 W10 tip_twist 进入 OpenVSP 导出表面（首个交付的 B-W10-OPENVSP 关闭项）

修复前：`build_openvsp_request()` 的 wing section 不含 twist；外部 worker `openvsp_geometry.py` 文档明确 “Surface twist is intentionally not modelled here”；因此 W10 只进入 RCAIDE VLM，不进入 OpenVSP/VSPAERO 表面，W10 的曲面证据无效。

修复（OpenVSP 3.26.1 实测 API，非猜测）：
- 3.26.1 无 `SetXSecTwist()`；但 XSec 存在参数 `Twist` 与 `Twist_Location`，可用 `vsp.GetXSecParm() + vsp.SetParmVal()` 读写（probe 记录在外部记忆 `fix-cards/probe_twist_api.py`）。
- `aircraft/openvsp_check.py:121` 为每个 wing section 增加 `twist_deg`；限制说明更新为 `:979`。
- `aircraft/openvsp_geometry.py`：`_add_wing` 读 `twist_deg`(:97)，逐 section 写入 `Twist`(:112) 并显式 `Twist_Location = 0`(:113)，即绕前缘扭转，与模型定义一致。
- `aircraft/openvsp_perturbations.py:590` 同步更新限制说明；`README.md` 两处（limitations、W10 映射表）同步。
- 回归测试：`tests/test_openvsp_geometry.py`（3 tests，FakeVSP 逐 section 断言 `Twist`=[0,0,0,2.0]、`Twist_Location` 全 0、缺省 0）；`tests/test_openvsp_check.py` 增 1 条 request 级断言。

真实 OpenVSP 导出核验（纯几何，外部 Python 3.9 worker，`/d/Anaconda/envs/SUAVE/python.exe`，OpenVSP 3.26.1 win64）：
- 用 12D 配置生成 baseline 与 `w10_plus_2deg`（W10=+2°）两份 request，两次 worker 均 `exit=0`。
- 机翼 STL 改变、垂尾与机身 STL sha256 逐字节相同 → 修复只作用于机翼。
- 1082 个机翼顶点：内侧 0–90% 半展长 |dz|=0，最外 90–100% 带 max |dz| = 0.033961960305 m，与 `sin(2°) × 0.973136 m = 0.033962 m` 吻合到 1e-6；|dy|=0（绕前缘、无展向位移）。
- 结果文件（项目外证据目录）：`%LOCALAPPDATA%\RCAIDE_Supersonic_agent_state\fix-cards\openvsp-w10\{measurements.json, vertex_displacement.json}`。
- 边界：这只证明**几何导出**正确；扭转的气动效应未验证（W10 气动证据仍需 LF/HF 验证矩阵），历史 P1 OpenVSP run 早于本修复，不得被引用为 W10 曲面证据。

## 4. 测试与仓库状态

- 定向测试：88 tests，`OK (skipped=1)`（skip 为需要外部 Python 3.9 的 OpenVSP worker 集成测试）。
- 全量（当前工作区）：`envs/RCAIDE/python.exe -E -s -B -m unittest discover -s research/concorde_metaopt/tests -t .` → `Ran 347 tests in 27.986s`，`OK (skipped=1)`。其中 79 个是**未提交**的 P5 工作区测试；本身份（本提交）可复现的套件为 268 tests（HEAD 的 248 + 本次 20 个回归测试）。
- 日志：`%LOCALAPPDATA%\RCAIDE_Supersonic_agent_state\fix-cards\{targeted_tests.log, full_suite.log}`（EXIT=0）。
- README 测试计数（A5 F-04）在本提交内更新为 268（17 audit + 56 design space + 23 geometry + 32 OpenVSP + 31 task/evaluation + 38 budget/cache + 23 DOE + 15 BO toy + 11 DE toy + 11 analytic functions + 11 report）；工作区中未提交的 P5 测试不计入本提交的 README 声明。
- 提交卫生：本修复只提交与修复卡相关的文件；工作区中原有的 P5 未提交改动（README/cli.py/index.json/figures.py 的 P5 段落与 P5 相关文件）**不在**本提交内，保持 P4/P5 冻结。

## 5. 未做与下一步（不冒充完成）

- 未运行 LF/HF 验证矩阵（owner 已批准预算，但属于下一步）：`validation_matrix_and_budget_proposal.json` 中 LFV-00..05 / HFS-00..04 尚未执行；计划实现 wing-only RCAIDE VLM 探针（12D baseline + 代表扰动，Mach 2.02，记录 CL/CDi/CM、网格密度与收敛），并如实标注 `lifting_surfaces-only`；HF 若不能生成机翼-only 封闭网格则标 `NOT_IMPLEMENTED_FOR_CONCORDE`。
- 未冻结设计空间：`frozen: false`、`bounds_status: provisional_until_geometry_perturbation` 保持不变，需负责人另行批准。
- 门禁状态不变：GEO-12D / LF-M2.02 / HF-M2.02 / BODY-CORR / MISSION-DATA / BUDGET 均未通过验收；本修复只是解除部分阻塞项，不构成 APPROVED_FOR_NEXT_STAGE。
