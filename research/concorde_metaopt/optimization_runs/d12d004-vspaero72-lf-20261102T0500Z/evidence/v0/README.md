# D-12D-004 V0 零求解预检证据（V0_PREGATE_PASS）

本目录是 Issue #4 批准评论 6569140757（D-12D-004，A-VSPAERO7-thin-LF，最多 10 次真实启动）的**前置门禁 V0** 证据包。
V0 是零求解预检：**未启动任何 VSPAERO 求解算例、未消耗 10 次预算中的任何一次**（`solver_cases_started=0`、
`billable_numerical_analysis_starts=0`、`v1_starts_used_so_far=0`）。

## 阶段与结果

| 阶段 | 内容 | 结果 |
|---|---|---|
| stage 1 | `scripts/test_vspaero7_runner.py`（unittest 22 个用例：LD-001 严格拒绝、重复键、畸形行、setup rc≠0、polar NaN/Re/Sref 校验、默认值泄漏、热力学不一致、solver 拒绝、legacy .vspaero 隔离、CLI smoke） | PASS（Ran 22 tests OK） |
| stage 2 | OpenVSP 3.55.0 API 生成 Setup：`VSPAEROComputeGeometry`（ThinGeometrySet=SET_ALL）+ `VSPAEROSweep(StopBeforeRun=1)` | PASS；产出 `setup_gen/wing355_baseline.vspaero`（930 B，含 VSPAERO 默认值）与 thin .vspgeom（224,357 B，已移出仓库） |
| stage 3 | 合同值注入 + 落盘重读 13 项断言（Mach=2.02、Vinf=596.0373972278921、Rho=0.1153178340089936、ReCref≈89397005.8767656、Sref=358.25、Cref=18.489893、Bref≈25.604638、X_cg=16.821978259514246、AoA=2、Symmetry=0 等） | PASS；产出 `setup_gen/wing355_thin_v0_contract.vspaero`（847 B，17 个字段） |
| stage 4 | 负控制：raw 默认值泄漏必须被拒、错误 Sref 必须被拒、`start-solver` 必须被拒、legacy 模板（无 ` = `）必须被拒 | PASS（`raw_default_leak_rejected` / `wrong_sref_rejected` / `start_solver_refused` / `legacy_template_strict_rejected`） |
| stage 5 | 预算账本初始态：cap 10 / used 0 / remaining 10 | PASS |

汇总文件：`v0_preflight_evidence.json`（状态 `V0_PREGATE_PASS`，sha256 `c669821e99729fa2602ac6fc106f432aec575d1ca62f2de99a0a35aa9bbc8ad8`）；
setup 生成原始记录：`setup_generation_raw.json`。

## 关键实现事实与限制

1. **StopBeforeRun=1 不 fork 求解器**：`VSPAEROSweep.ExecAnalysis` 会在 stdout 打印一行形如
   `<openvsp_root>\vspaero.exe -omp 4 <base>` 的预告命令，但 `stop_before_run_readback=1`、未生成
   `.history/.polar/.adb/.lod`、无 `vspaero.exe` 进程；该打印来自 OpenVSP 管理器的命令组装，不是求解器启动。
   `VSPAEROSweep` 的 analysis result id 为空字符串是正常现象（无求解结果）。
2. **本地模型副本**：`VSPAEROComputeGeometry` 会把 `.vspgeom` 写到被加载模型所在目录；若直接加载外部模型路径，
   会写回外部目录且不在当前工作目录生成 `.vspaero` setup。因此先把源模型复制到 `setup_gen/`
   （`wing355_baseline.vsp3`，111,816 B，sha256 与源模型一致，见 `setup_generation_raw.json`）再加载。
3. **`.vspgeom` 出仓库**：thin `.vspgeom`（224,357 B）是二进制生成物，已移到
   `D:/RCAIDE/outputs/concorde_metaopt/d12d004-vspaero72-lf-20261102T0500Z/raw_artifacts/`，路径与 sha256 记录在证据 JSON 中。
4. **进程级证明限制**：V0 只能证明「零求解算例、零计费数值分析」，无法给出「任意 solver 进程从未存在」的进程级证明
   （本机无 4688/USN/ETW 可用）；与 Round-1 同类限制一致，已如实记录。
5. V0 首版曾因未复制模型而生成失败（`V0_PREGATE_FAIL`，未启动求解器、未消耗预算）；修复后重跑得到本 PASS 证据。

## 复现

```
# 工作目录：D:/RCAIDE-d12d004/research/concorde_metaopt/optimization_runs/d12d004-vspaero72-lf-20261102T0500Z
D:/RCAIDE/envs/RCAIDE/python.exe scripts/v0_preflight.py
```

依赖：OpenVSP 侧装 3.55.0（`D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64`，vspaero 7.2.2）、
源模型 `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/lead/d12d003/setup355b/_model/wing355_baseline.vsp3`。
