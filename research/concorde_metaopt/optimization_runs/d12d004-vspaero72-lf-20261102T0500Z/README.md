# d12d004-vspaero72-lf-20261102T0500Z — D-12D-004 A 类 LF VSPAERO 7.2.2 薄翼验证 run（骨架）

- **状态：SKELETON / NOT_RUN / 0 求解器启动**（本目录目前只有配置骨架与预检占位，尚无任何求解证据）
- 授权：Issue #4 评论 **6569140757**（2026-11-02，D-12D-004），**仅批准 A 类 A-VSPAERO7-thin-LF 最多 10 次启动**。
- 被拒绝类别（额度恒为 0，禁止借用/转换）：B VSPAERO Thick=0、C OpenVSP WaveDrag=0、D SU2 Euler=0、E RCAIDE Mission=0、P4 真实 BO/MAML=0。
- 分支/worktree：`research/d12d004-vspaero7` @ `D:/RCAIDE-d12d004`，base SHA `e5140fc64d348f2d9dcf52962f1dcfc425099341`。**不合并 main**，不触碰主库 D:/RCAIDE 的 P5 脏文件。
- 报告语言：简体中文；图表中文。

## 1. 硬约束（逐条来自授权评论）

1. 串行执行，单并发；CPU ≤4 核；RAM ≤8 GB；无付费云。
2. 单次启动墙钟 ≤600 s；整轮（准备+运行）≤6 h。
3. 每一次 `vspaero.exe` 进程启动都计费：失败、超时、被中止、setup 失败后仍启动均计 1 次；每案最多 1 次重试且占用同一 cap。
4. `starts_used >= 10` 立即强制停止，剩余案例保持 `NOT_RUN`。
5. 门禁未过不得启动：A1（runner 修复+测试）/ A5（独立复核）/ A3（二进制与 worktree 隔离）通过后才允许，A2 配置与账本已在本目录就位。
6. 新版 `.vspaero` 必须逐字段写入并回读断言（13 条，见 `config/run_config.json`），禁止默认值 Vinf=100 / Rho=0.002377 / ReCref=1e7 进入真实求解。
7. 进程退出码 0 不等于物理通过；零升力 CDi≈0 不算失败，但升力非零时负总阻力为严重警报。
8. 与 P4 仅通过 `evaluator_id / fidelity / physics_validation_status` 数据合同交接；物理验证不通过不阻塞 P4。

## 2. 目录与文件

| 路径 | 用途 | 当前状态 |
|---|---|---|
| `README.md` | 本说明 | 已写（A2 骨架） |
| `config/run_config.json` | 运行配置：授权、合同工况、参考量、13 条回读断言、账本与输出 | SKELETON，`runner_commit=null` 待 A1 填 |
| `config/actual_solver_budget.json` | D-12D-004 独立预算账本：cap 10 / used 0 / B–E=0 / no_carryover / 门禁表 | UNUSED_AT_ZERO_STARTS |
| `config/solver_case_matrix.csv` | 10 案矩阵：S2→M3→P3→D2（含 1 次重试余量），全部 `status=NOT_RUN` | 骨架 |
| `evidence/preflight/` | 启动前三门禁证据占位（A1/A5/A3） | 空占位 |
| `figures/`、`lf_vspaero_results.json`、`summary.json`、`data_manifest.json` | 运行后才产生的证据 | 不存在（NOT_RUN） |

raw 产物（gitignored）将写入 `D:/RCAIDE/outputs/concorde_metaopt/d12d004-vspaero72-lf-20261102T0500Z/`；`scripts/` 由 A1 负责，A2 不触碰。

## 3. 合同工况（冻结，来自 `configs/task_fixed_cruise.yaml` 与 12D 约定）

Mach 2.02；高度 18288 m（T=216.65 K, p=7171.544888256813 Pa, rho=0.1153178340089936 kg/m³, a=295.0680184 m/s）；Vinf=596.0373972278921 m/s；ReCref=89397005.8767656；Sref=358.25 m²；Cref=18.489893 m；Bref=25.604638 m；AoA=2°；CG x=16.821978259514246（**PROVISIONAL_NOT_FROZEN**）；Symmetry=NO；WakeNodes=8、WakeIters=5。

## 4. 10 次启动的执行排序与含义

1. **S 组（2 次）**：V7-00 标准薄翼亚音速（运行器/解析自洽）、V7-01 标准薄翼 Mach2.02（适用性探针）。V7-01 若负阻力/NaN → 停止大翼链。
2. **M 组（3 次）**：12D 仅主翼粗 8/17 → 中 16/33（主判据）→ 细 32/65（收敛判据，中→细相对差 <15%）。
3. **P 组（3 次）**：W01 +1%（361.8325）、W03 +1°（68.0）、W10 +2°（2.0），仅中网格，几何断言 + 趋势自洽。
4. **D 组（2 次）**：V7-08 α=0/2/4 机理诊断；V7-09 唯一重试/尾迹敏感性余量（启动前必须写明假设与准则，否则保持 NOT_RUN）。

全部案例只算 **lifting surfaces only**（无机身、无垂尾），不得据此宣称全机阻力/航程。

## 5. 当前事实（诚实声明）

- `starts_used=0`、`starts_remaining=10`、`billable_events=0`、`mesh_generation_events=0`。
- 未启动 VSPAERO / SU2 / RCAIDE Mission / OpenVSP WaveDrag 等任何求解器；未产生 polar/history/coefficients。
- 所有案例 `status=NOT_RUN`；任何"结果"都不存在，禁止引用本目录推断物理结论。
- 本 run 不改变 `LF-M2.02 = NOT_VALIDATED` 的现状；只有完成门禁并执行后，才由证据决定是否升级。

## 6. A1 接管清单（启动前必须完成）

1. 修复 LD-001（`.vspaero` 模板缺 `=`、setup 返回码、polar NaN、Sref/Re 注入），提交 runner 并把 40 位 SHA 填入 `config/run_config.json:code.runner_commit` 与 `git_sha_required_at_run_start`。
2. 按 `config/solver_case_matrix.csv` 生成每案 `.vspgeom`/`.vspaero`，逐字段回读 13 条断言。
3. 把 A1 测试日志、A5 独立复核结论、A3 隔离检查放入 `evidence/preflight/`，更新 `preflight_gates` 全为 true 后才允许第一次启动。
4. 每次启动前写账本 pending 事件（`NA-D12D004-001..010`），完成后写结果并自增 `starts_used`；结束断言 `starts_used+starts_remaining==10` 且 `billable_events==starts_used`。
