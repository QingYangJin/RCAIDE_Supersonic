# D-12D-005 A0：LD-002 polar 解析与算例目录门禁修复说明（vspaero7_runner_v2）

- 生成时间：2026-11-04（Asia/Shanghai）
- 角色：A1（a1-code-dev）
- 范围：D-12D-005 A0-aero 预检，**零求解器启动**（本文件所有验证均为静态解析/单测；未执行 vspaero/SU2/Mission）
- 基线：`scripts/vspaero7_runner_v1frozen.py`（只读，未修改）
- 产物：`scripts/vspaero7_runner_v2.py`、`scripts/test_vspaero7_runner_v2.py`、本说明、`evidence/a0/ld002_test_run.log`

## 1. 文件与校验和

| 文件 | 行数 | 字节 | sha256 |
| --- | --- | --- | --- |
| scripts/vspaero7_runner_v1frozen.py（基线，未改） | 837 | 30373 | b77b56526acab6ac03ee07838d06970f2bd98d298aae597997bf393474128a36 |
| scripts/vspaero7_runner_v2.py | 1227 | 50411 | 7cce34bcf210397008a8870f7064b60920cd50659127033ddf668a3207fde1b3 |
| scripts/test_vspaero7_runner_v2.py | 429 | 18824 | 66972b155cfcf6a1799926804f73837b4ba48b7dd4942bbbe8c02450327c2525 |
| evidence/a0/ld002_test_run.log | - | - | b59332cb8b7f2f2a4e677fc8d912329da824ffd5b87de6f04ab67e9ad2ac7100 |

SCHEMA_VERSION 由 `d12d004-runner-1` 升为 `d12d005-runner-2`；公共 API 保持向后兼容（parse_setup_text / read_setup_file / validate_setup_fields / inject_contract_fields / require_setup_success / validate_history_file / assert_new_format_only / assert_no_solver_artifacts / start_solver 等函数名与异常类名不变）。

## 2. 表头证据（为什么必须改 polar 解析）

### 2.1 VSPAERO 7.2.2 真实 polar（D-12D-004 归档实测）

- 文件：`D:/RCAIDE/outputs/concorde_metaopt/d12d004-vspaero72-lf-20261102T0500Z/raw_artifacts/cases/V7-00/v7_00_standard_wing_mach0p1.polar`
- 大小 3048 B，sha256 `2741d32ac33daf0fb88cd2793975cb36f2d7130c194f957970c30dce14506b6f`
- 第 1 行：分组标签 `Surface Integration Forces and Moments -->`
- 第 2 行：分组标签 `Surf-Surf-...`（超长单一 token）
- 第 3 行：真实表头，`awk 'NR==3{print NF}'` = **48**，列序为
  `Beta Mach AoA Re/1e6 CLo CLi CLtot CDo CDi CDtot CSo CSi CStot L/D E CMox CMoy CMoz CMix CMiy CMiz CMxtot CMytot CMztot CFox CFoy CFoz CFix CFiy CFiz CFxtot CFytot CFztot CLwtot CDwtot CSwtot CLiw CDiw CSiw CFwxtot CFwytot CFwztot CFiwx CFiwy CFiwz LoDw Ew StallFactor`
- 第 4 行起为数据行，12 位小数（V7-00 首行出现 CLi=-2795.92、CLtot=-2801.89 等发散值，与 A0 旧版分析结论一致，不用于几何验收）。

**结论**：7.2.2 没有 `CL`/`CMm` 列；旧 v1frozen 解析器按 `len>=8 且含 CL/AoA/Mach` 找表头，对 7.2.2 会找不到表头或错列读取，必须改为严格 48 token 匹配。

### 2.2 legacy VSPAERO 6.2 polar（必须显式拒绝）

- 文件：`D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/lf_raw/baseline/main_wing_baseline_DegenGeom.polar`
- 第 1 行即表头，20 token：`Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E CFx CFy CFz CMx CMy CMz CMl CMm CMn`
- 数据行使用 E 指数格式（21 个值）。

**结论**：6.2 表头与 7.2.2 表头不兼容；v2 遇到 `CL+CMm` 且无 `CLo/CLi/CLtot` 的行会直接抛 `POLAR_LEGACY_62_HEADER_REJECTED`，不允许把旧 `CL/CDi` 当作 `CLtot/CDtot` 使用。

## 3. v2 修复内容

### 3.1 polar 解析（LD-002 核心）

1. `_identify_polar_header()`：逐行扫描，只有在 token 集合同时包含 `CLtot/CDtot/Mach/AoA` 时才认定为 7.2.2 表头；遇到 legacy 6.2 特征行则给 `POLAR_LEGACY_62_HEADER_REJECTED`。
2. 表头 token 必须与 `POLAR_722_COLUMNS`（48 列）完全一致，否则 `POLAR_HEADER_TOKENS_UNEXPECTED`；列缺失给 `POLAR_COLUMNS_MISSING`。
3. 数据行必须与表头同宽，否则 `POLAR_ROW_WIDTH_INVALID`；NaN/IND/INF 给 `POLAR_NONFINITE`；无数据行给 `POLAR_NO_DATA_ROWS`。
4. 每行强制校验：`Re/1e6*1e6` 与合同 `ReCref` 相对误差 ≤1e-6（`POLAR_RE_MISMATCH`）；`Mach` 与合同相对误差 ≤1e-6（`POLAR_MACH_MISMATCH`）；`|CLtot|≤10`、`|CDtot|≤10`（`POLAR_NONPHYSICAL`，防 358 倍 Sref 放大等失控值直接进入验收）。
5. 返回结构含 `header_token_count=48`、逐行 `CLo/CLi/CLtot/CDo/CDi/CDtot/CMztot/Re` 与文件 sha256，供证据 JSON 直接引用。

### 3.2 严格 check-case-dir 门禁（新增 CLI 子命令）

对单算例目录逐项检查，任一项失败即 `CaseGateError`（错误码见 §4）：

1. `*_contract.vspaero` 存在，并按合同 17 字段回读（复用 `read_setup_file`，断言数必须等于合同字段数，12D 合同为 17）。
2. `*.vkey` 存在：首行须为 `# VSPGEOM v3 Tag Key File`，第 2 行为 vspgeom 路径。
3. `*.csf` 存在且内容为 `0 Control Surfaces`（20 B）。
4. `*geom_result*.csv` 存在，且记录必须是薄几何：`GeometrySet=-1` 且 `ThinGeometrySet=0`。
5. `.vspgeom` 存在性：优先算例目录内 `*.vspgeom`；否则从 setup-generation 证据的 `execution_bundle.vspgeom_external_path`/`thin_geometry.external_path` 解析，并核对记录中的 sha256/bytes。
6. `.vkey` 第 2 行指向的 vspgeom 文件名必须与解析出的 vspgeom 文件名一致（D-12D-004 V1 根因：vkey 指向不存在的本地 `_model.vspgeom`）。
7. StopBeforeRun 证据：`--evidence` JSON 顶层须有 `stop_before_run=1`、`solver_processes_started=0`（或算例目录内置 `setup_gen_report.json`）。
8. 禁止残留求解产物：`*.polar/*.history/*.lod/*.groups/*.group.*/*.adb/*.fem`。
9. `wrapper.wrapper_timeout_s`（若记录）不得小于 600 s（`config/run_config.json` 的 `max_wall_per_start_s`）。

### 3.3 外层包装器误杀判定（新增）

`validate_wrapper_outcome(record)`：仅使用记录字段（不启动 solver）判定
- `wrapper_timeout_s < 600` → `CASE_WRAPPER_TIMEOUT_TOO_SHORT`（D-12D-004 V1 的 120 s 外层包装器误杀根因）；
- `wall_seconds >= wrapper_timeout_s` → `CASE_WRAPPER_KILLED_AT_TIMEOUT`；
- `killed=True` 或 `returncode=None/<0` → `CASE_KILLED_BY_WRAPPER`；
- `completed=False` → `CASE_WRAPPER_OUTCOME_INCOMPLETE`。

## 4. 错误码表（v2 新增/显式化）

| 错误码 | 触发条件 |
| --- | --- |
| POLAR_LEGACY_62_HEADER_REJECTED | 旧 6.2 表头（CL/CMl/CMm，无 CLo/CLi/CLtot） |
| POLAR_HEADER_MISSING | 找不到 7.2.2 表头 |
| POLAR_HEADER_TOKENS_UNEXPECTED | 表头 token 列表与 48 列合约不一致 |
| POLAR_ROW_WIDTH_INVALID | 数据行列数 != 48 |
| POLAR_NONFINITE | 数据含 NAN/IND/INF |
| POLAR_RE_MISMATCH | Re/1e6 与合同 ReCref 相对误差 >1e-6 |
| POLAR_MACH_MISMATCH | Mach 与合同相对误差 >1e-6 |
| POLAR_NONPHYSICAL | \|CLtot\|>10 或 \|CDtot\|>10 |
| POLAR_NO_DATA_ROWS | 表头后无数据行 |
| POLAR_COLUMNS_MISSING | 48 列合约中必要列缺失 |
| CASE_SETUP_MISSING / CASE_VKEY_MISSING / CASE_CSF_MISSING / CASE_GEOM_RESULT_MISSING | 对应必需文件缺失 |
| CASE_SETUP/VKEY/CSF/GEOM_RESULT_AMBIGUOUS | 同模式文件多于 1 个 |
| CASE_VSPGEOM_MISSING | 本地与证据均无 vspgeom |
| CASE_VSPGEOM_SHA_MISMATCH / CASE_VSPGEOM_BYTES_MISMATCH | 外部 vspgeom 与记录不一致 |
| CASE_VKEY_INVALID | vkey 首行/第 2 行格式非法 |
| CASE_VKEY_GEOM_MISMATCH | vkey 指向的 vspgeom 与实际解析结果不一致 |
| CASE_CSF_INVALID | csf 非 `0 Control Surfaces` |
| CASE_THIN_GEOMETRY_MISSING / CASE_THIN_GEOMETRY_MISMATCH | 缺 GeometrySet/ThinGeometrySet，或不是 -1/0 薄翼记录 |
| CASE_STOP_BEFORE_RUN_EVIDENCE_MISSING / CASE_STOP_BEFORE_RUN_MISSING | 缺 StopBeforeRun 证据或不为 1 |
| CASE_SOLVER_PROCESS_RECORDED | 证据记录到非 0 求解进程 |
| CASE_WRAPPER_TIMEOUT_TOO_SHORT | 包装器超时 < 600 s |
| CASE_KILLED_BY_WRAPPER / CASE_WRAPPER_KILLED_AT_TIMEOUT / CASE_WRAPPER_TIMEOUT_MISSING | 包装器误杀/缺超时字段 |
| CASE_READBACK_ASSERTION_COUNT | 回读断言数 != 合同字段数 |

## 5. CLI 用法

```
# 校验 7.2.2 polar（48 列严格解析）
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/vspaero7_runner_v2.py verify-polar --polar <case>.polar

# 严格算例目录门禁（推荐：A2 执行前的唯一入口检查）
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/vspaero7_runner_v2.py check-case-dir \
  --dir evidence/a0/setup_gen/<case> --evidence evidence/a0/setup_generation.json --case-id <case>

# 外层包装器结果判定（读记录，不跑 solver）
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -c "import sys;sys.path.insert(0,'scripts');import vspaero7_runner_v2 as R;print(R.validate_wrapper_outcome({'wrapper_timeout_s':600,'wall_seconds':120.5,'returncode':0}))"

# 原有命令保持：normalize / readback / verify-history / check-dir / setup-gate / start-solver
```

真实 A0 证据上的演示（**预期失败**，证明门禁能在启动前拦住 V1 根因）：

```
$ ... check-case-dir --dir evidence/a0/setup_gen/S5_D12_M2p02_base \
    --evidence evidence/a0/setup_generation.json --case-id S5_D12_M2p02_base
{"status": "FAIL", "error_type": "CaseGateError",
 "message": "CASE_VKEY_GEOM_MISMATCH: vkey points at '.../evidence/a0/setup_gen/S5_D12_M2p02_base/wing355_baseline.vspgeom' but the resolved vspgeom is 'D:/RCAIDE/outputs/concorde_metaopt/d12d005-20261104T0430Z/raw_artifacts/a0_setup/S5_D12_M2p02_base.vspgeom'"}
GATE_EXIT=2
```

结论：A0 setup 包在 A2 执行前必须把 `*.vkey` 第 2 行改写为 external vspgeom 绝对路径（execution_bundle 的既定步骤），否则 v2 门禁会拒绝——这是预期行为，不是 v2 缺陷。

## 6. 测试日志摘要

命令（在 `D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z` 下）：

```
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m unittest discover -s scripts -p "test_vspaero7_runner_v2.py" -v
```

- 结果：**Ran 38 tests / OK / 退出码 0**（约 0.33 s）
- 全量日志：`evidence/a0/ld002_test_run.log`（sha256 b59332cb8b7f2f2a4e677fc8d912329da824ffd5b87de6f04ab67e9ad2ac7100）
- 覆盖：LD-001 缺 '=' 检测/规范化/严格拒绝、17 字段回读、默认值泄漏（ReCref=1e7、Vinf=100）、错误 Sref、setup 返回码非 0、缺 vkey/csf、薄几何记录、缺 vspgeom、StopBeforeRun=0/缺失、vkey-vspgeom 不一致、120 s 包装器误杀、包装器字段缺失、残留 polar 产物、7.2.2 48 列正确解析、legacy 6.2 拒绝、缺列、NaN/IND、错误 Re、错误 Mach、非物理 CLtot、无数据行、缺表头、CLI 三条用例。
- 另：Lead 的 `scripts/a0_verify_cases.py` 在 v2 落盘后仍 **PASS 163/163**（v1frozen 未被改动，公共 API 兼容）。
- 注意：本套测试用临时目录合成 fixture，不读取/不修改 A0 真实 setup 包；未启动任何求解器。

## 7. 与 v1frozen 的差异

- 保留：所有 v1frozen 函数/异常/CLI 子命令名与行为（read_setup_file、validate_history_file、inject_contract_fields、require_setup_success、assert_new_format_only 等）。
- 替换：`_polar_header_and_rows`/`validate_polar_file`（旧 9 列宽松解析 → 48 列严格解析 + legacy 拒绝 + 非物理/Re/Mach 检查）。
- 新增：`POLAR_722_COLUMNS`(48)、`LEGACY_62_POLAR_COLUMNS`、`MIN_WRAPPER_TIMEOUT_S=600`、`CaseGateError`/`WrapperGateError`、`check_case_dir`、`validate_thin_geometry_record`、`validate_vkey`、`validate_csf`、`parse_geom_result_csv`、`resolve_case_vspgeom`、`validate_wrapper_outcome`、CLI `check-case-dir`。
- 扩大：`SOLVER_ARTIFACT_GLOBS` 增加 `*.group.*`（VSPAERO 7.2.2 实际产物名）。

## 8. 限制与 NOT_RUN

- NOT_RUN：任何 VSPAERO/SU2/RCAIDE Mission 启动、真实 7.2.2 求解、真实 polar 数值验收。polar 解析仅用合成 fixture 验证；真实 48 列结构以 §2.1 归档文件表头+行宽核对为准。
- PARTIAL：`check-case-dir` 对 A0 真实包的完整 PASS 需 A2 先完成 vkey 第 2 行改写（见 §5）。
- 本文件与 v2 代码未做 git commit；d12d005 run 目录仍为 untracked，由 Lead 决定归档提交。
