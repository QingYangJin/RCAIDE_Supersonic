# D-12D-005 A0：LD-002 polar 解析与算例目录门禁修复说明（vspaero7_runner_v2）

- 生成时间：2026-11-04（Asia/Shanghai）
- 角色：A1（a1-code-dev）
- 范围：D-12D-005 A0-aero 预检，**零求解器启动**（本文件所有验证均为静态解析/单测；未执行 vspaero/SU2/Mission）
- 基线：`scripts/vspaero7_runner_v1frozen.py`（只读，未修改）
- 产物：`scripts/vspaero7_runner_v2.py`、`scripts/test_vspaero7_runner_v2.py`、本说明、`evidence/a0/ld002_test_run.log`（首版 38 tests）、`evidence/a0/v2rev2_test_run.log`（rev2 46 tests）、`evidence/a0/v2rev3_test_run.log`（rev3 51 tests）

## 1. 文件与校验和

| 文件 | 行数 | 字节 | sha256 |
| --- | --- | --- | --- |
| scripts/vspaero7_runner_v1frozen.py（基线，未改） | 837 | 30373 | b77b56526acab6ac03ee07838d06970f2bd98d298aae597997bf393474128a36 |
| scripts/vspaero7_runner_v2.py（rev3：主/派生列分离） | 1362 | 55115 | e5b3381ce0f72d587f725a5b400b51d1ef02e54dbde05c2c6ad285af9e849acf |
| scripts/test_vspaero7_runner_v2.py（rev3） | 575 | 25999 | a57526aa2c5689083fb2d2b427dcbab3f7567549d6bf3876d610d4a992d42f3f |
| evidence/a0/ld002_test_run.log（首版 38 tests） | - | 4345 | a34c9e282a9d8dd5c98561d24d042a7eb003a56f02b0e6cdbbc90eb4ca7f9705 |
| evidence/a0/v2rev2_test_run.log（rev2 46 tests） | - | 319 | 03757b371510dee2db6efe87ac7928324fe2b4dd8deb032b47c97ac50fe7748f |
| evidence/a0/v2rev3_test_run.log（rev3 51 tests） | - | 370 | 735f7d82b87ba37ece4661d1dcb335ca59aa382bdad68c20cc1c9407f964ffde |

注：`.log` 工作树形态为 CRLF，`.gitattributes`（`* text=auto eol=lf`）提交时归一化为 canonical-LF；上表按**提交 blob（canonical-LF）**记录，可从干净 checkout 逐字节复现。

SCHEMA_VERSION 由 `d12d004-runner-1` 升为 `d12d005-runner-2`，rev2 加固后升为 `d12d005-runner-3`，rev3（主/派生列分离）后升为 `d12d005-runner-4`；公共 API 保持向后兼容（parse_setup_text / read_setup_file / validate_setup_fields / inject_contract_fields / require_setup_success / validate_history_file / assert_new_format_only / assert_no_solver_artifacts / start_solver 等函数名与异常类名不变）。

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
6. rev2 新增：表头必须在第 3 行（前两行是分组标签），否则 `POLAR_HEADER_ROW_UNEXPECTED`；新增 `parse_polar_structure()` 做 structure-only 解析（48 列/行宽/非有限 token/前 5 行预览），返回 `PASS_STRUCTURE_ONLY` 且 `physical_validation = NOT_APPLIED`，不把非物理数值伪装成通过。
7. rev3 新增（A5 task-110 S3F-01）：把**主系数列**与**派生比列**分开。`validate_polar_file(..., allow_nonfinite_columns=...)` 支持一个显式、窄的白名单（当前只有 `("Ew",)`，即 `POLAR_DERIVED_NONFINITE_COLUMNS`）；白名单列的 NaN/IND/INF 只把报告降级为 `PASS_WITH_WARNINGS` 并写入 `derived_column_warnings`，其余任何列非有限仍报 `POLAR_NONFINITE`；主系数永不进入白名单，缺省行为仍是严格失败。S3 超声速标准翼的 `Ew = CLtot^2/(π·AR·CDiw)` 因 `CDiw=0` 为 `inf`，属于除零伪影（主系数 `CLtot=0.074251`、`CDi=0.002607`、`CDtot=0.013789` 均为有限且与线化理论区间 0.0673–0.0796 一致），allowlist 重跑 `verify-polar` 得 `PASS_WITH_WARNINGS`（见 `evidence/lead/s3_verify_polar_allowlisted.json`）。

### 3.2 严格 check-case-dir 门禁（新增 CLI 子命令）

对单算例目录逐项检查，任一项失败即 `CaseGateError`（错误码见 §4）：

1. `*_contract.vspaero` 存在，并按合同 17 字段回读（复用 `read_setup_file`，断言数必须等于合同字段数，12D 合同为 17）。
2. `*.vkey` 存在：首行须为 `# VSPGEOM v3 Tag Key File`，第 2 行为 vspgeom 路径。
3. `*.csf` 存在且内容为 `0 Control Surfaces`（20 B）。
4. `*geom_result*.csv` 存在，且记录必须是薄几何：`GeometrySet=-1` 且 `ThinGeometrySet=0`。
5. `.vspgeom` 存在性：优先算例目录内 `*.vspgeom`（必须与证据记录 sha256/bytes 一致，否则 `CASE_VSPGEOM_SHA_MISMATCH`/`CASE_VSPGEOM_BYTES_MISMATCH`，并标记 `evidence_record_verified`）；否则从 setup-generation 证据的 `execution_bundle.vspgeom_external_path`/`thin_geometry.external_path` 解析并核对记录。
6. `.vkey` 第 2 行必须是绝对路径，`resolve(strict=True)` 后与解析出的 vspgeom **全路径相等**（只比 basename 不够；D-12D-004 V1 根因：vkey 指向不存在的本地 `_model.vspgeom`）。
7. StopBeforeRun / 求解进程证据：`--evidence` JSON 顶层须有 `stop_before_run=1`，且 `solver_processes_started` / `solver_starts` 键必须存在并等于 0；键缺失即 `CASE_SOLVER_PROCESS_EVIDENCE_MISSING`（fail-closed，禁止“缺字段=放行”）。
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
| CASE_SOLVER_PROCESS_EVIDENCE_MISSING | 证据缺 `solver_processes_started`/`solver_starts` 键（fail-closed） |
| POLAR_HEADER_ROW_UNEXPECTED | 表头不在第 3 行（前两行应为分组标签） |
| CASE_WRAPPER_TIMEOUT_TOO_SHORT | 包装器超时 < 600 s |
| CASE_KILLED_BY_WRAPPER / CASE_WRAPPER_KILLED_AT_TIMEOUT / CASE_WRAPPER_TIMEOUT_MISSING | 包装器误杀/缺超时字段 |
| CASE_READBACK_ASSERTION_COUNT | 回读断言数 != 合同字段数 |
| POLAR_ALLOWLIST_UNKNOWN_COLUMNS | `allow_nonfinite_columns` 含 48 列表头中不存在的列名（防误用） |

注：structure-only 状态 `PASS_STRUCTURE_ONLY` 不是错误，只声明结构可解析；其 `physical_validation = NOT_APPLIED`，不能用于数值验收。`PASS_WITH_WARNINGS` 仅表示“主系数全部有限、个别派生列被显式豁免”，不是物理验收通过，也不能作为 `CDtot` 可用的依据。

## 5. CLI 用法

```
# 校验 7.2.2 polar（48 列严格解析 + 数值验收；主系数必须有限）
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/vspaero7_runner_v2.py verify-polar --polar <case>.polar

# 显式允许派生列 Ew 非有限（只降级为 PASS_WITH_WARNINGS；主系数仍必须有限）
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/vspaero7_runner_v2.py verify-polar \
  --polar <case>.polar --expect <case>/expected.json --allow-nonfinite-derived

# 只做结构解析（不验收数值）
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/vspaero7_runner_v2.py polar-structure --polar <case>.polar

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

- 结果：**Ran 51 tests / OK / 退出码 0**（约 0.53 s；rev2 46 tests 见 `v2rev2_test_run.log`，首版 38 tests 见 `ld002_test_run.log`）
- 全量日志：`evidence/a0/v2rev3_test_run.log`（370 B / sha256 735f7d82b87ba37ece4661d1dcb335ca59aa382bdad68c20cc1c9407f964ffde）
- 覆盖：LD-001 缺 '=' 检测/规范化/严格拒绝、17 字段回读、默认值泄漏（ReCref=1e7、Vinf=100）、错误 Sref、setup 返回码非 0、缺 vkey/csf、薄几何记录、缺 vspgeom、StopBeforeRun=0/缺失、vkey-vspgeom 不一致、120 s 包装器误杀、包装器字段缺失、残留 polar 产物、7.2.2 48 列正确解析、legacy 6.2 拒绝、缺列、NaN/IND、错误 Re、错误 Mach、非物理 CLtot、无数据行、缺表头、CLI 三条用例。
- 另：Lead 的 `scripts/a0_verify_cases.py` 在 v2 rev3 落盘后复跑 **PASS 264/264（revision 4）**（v1frozen 未被改动、公共 API 兼容）。rev3 新增 5 个测试：默认拒绝 Ew=inf、allowlist 放行 Ew=inf 且 CLtot 仍有限、主系数 NaN 即使有 allowlist 仍拒绝、未知 allowlist 列拒绝、CLI `--allow-nonfinite-derived` 端到端。
- 注意：本套测试用临时目录合成 fixture，不读取/不修改 A0 真实 setup 包；未启动任何求解器。

## 7. 与 v1frozen 的差异

- 保留：所有 v1frozen 函数/异常/CLI 子命令名与行为（read_setup_file、validate_history_file、inject_contract_fields、require_setup_success、assert_new_format_only 等）。
- 替换：`_polar_header_and_rows`/`validate_polar_file`（旧 9 列宽松解析 → 48 列严格解析 + legacy 拒绝 + 非物理/Re/Mach 检查）。
- 新增：`POLAR_722_COLUMNS`(48)、`LEGACY_62_POLAR_COLUMNS`、`MIN_WRAPPER_TIMEOUT_S=600`、`CaseGateError`/`WrapperGateError`、`check_case_dir`、`validate_thin_geometry_record`、`validate_vkey`、`validate_csf`、`parse_geom_result_csv`、`resolve_case_vspgeom`、`validate_wrapper_outcome`、`_recorded_vspgeom`、`parse_polar_structure`、CLI `check-case-dir`、CLI `polar-structure`。
- 扩大：`SOLVER_ARTIFACT_GLOBS` 增加 `*.group.*`（VSPAERO 7.2.2 实际产物名）。

## 8. 限制与 NOT_RUN

- NOT_RUN：任何 VSPAERO/SU2/RCAIDE Mission 启动、真实 7.2.2 求解、真实 polar 数值验收。polar 解析仅用合成 fixture 验证；真实 48 列结构以 §2.1 归档文件表头+行宽核对为准。
- PARTIAL：`check-case-dir` 对 A0 真实包的完整 PASS 需 A2 先完成 vkey 第 2 行改写（见 §5）。
- 提交：v2 首版随 A0-aero 提交 `ab29a0c`；rev2 加固与 evidence revision 3 同批提交（Lead 执行，A1 交付）；rev3 主/派生列分离与 evidence revision 4 同批提交（Lead 执行，回应 A5 task-110 S3F-01，零求解）。
## 9. rev2 修订记录（A5 task-103）

A5 对 v2 delta 给 CHANGES_REQUESTED（0 blocker / 3 major / 5 minor），rev2 逐项处置：

| 编号 | 处置 |
| --- | --- |
| V2-M01 | vkey 绝对路径 + `resolve(strict=True)` + 与解析出的 vspgeom 全路径相等 |
| V2-M02 | 本地 vspgeom 与证据记录 sha256/bytes 校验 |
| V2-M03 | solver 进程证据键缺失 fail-closed |
| minor: csf | 精确匹配 `0 control surfaces` |
| minor: 表头行号 | 强制表头为第 3 行 |
| minor: structure-only | 新增 `polar-structure` 子命令 |
| minor: 旧数值 | §1 表按 canonical-LF 值更新 |
| minor: 未 commit 表述 | §8 已更新 |

新增回归测试 `CaseGateHardeningTests`（8 项）：vkey 不存在 / 同 basename 异目录 / 本地 vspgeom 篡改 / 本地匹配记录 PASS / 缺 solver 证据键 / csf 尾随内容 / 表头前移 / structure-only 接受非物理值。合计 **46 tests OK**。

## 10. rev3 修订记录（A5 task-110 S3F-01，A 批 S3 停止后的零求解修复）

A 批第 4 次启动（S3 标准翼 Mach 2.02）返回 `rc=0`、主系数全部有限，但 polar 派生列 `Ew=inf` 触发 v2 的 `POLAR_NONFINITE`，A2 按 `stop_rule_1` 保守停批（S4/S5 NOT_RUN）。A5 独立复核判定 `Ew` 为除零伪影、主系数未发散（`STOP_CONFIRMED=false`），条件性建议继续 S4/S5。rev3 处置：

| 编号 | 处置 |
| --- | --- |
| S3F-01 | 新增派生列白名单 `POLAR_DERIVED_NONFINITE_COLUMNS=("Ew",)` + `--allow-nonfinite-derived`；主系数仍严格，报告降级为 `PASS_WITH_WARNINGS` 并列出 `derived_column_warnings` |
| S3F-02 | 文档明确 `CDo/CDtot` 属 VSPAERO 内部寄生估算，不能当作真实阻力或优化目标；S4/S5 证据标 `VSPAERO_INTERNAL_ONLY` / `physical_validation=NOT_VALIDATED` |
| S3F-04 | S3 重新以 allowlist 复核 `PASS_WITH_WARNINGS`（1 行、48 列、唯一非有限 token 为 Ew），不改变 A2 的 "保守停批正确" 结论 |

本次修订**零求解**：只跑静态解析与 51 项回归测试；A 批启动计数保持 4/6，剩余 2 次须 Lead 重新书面授权后由 A2 执行（见 `evidence/lead/batch1b_reauthorization.md`）。
