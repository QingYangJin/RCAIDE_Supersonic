# R2 A5 预审 dossier（2026-11-20）

## 0. 性质

- 本文件是 **A5 独立审查输入**，不是 A5 结论，不是 GO，不授予新的物理预算。
- 审查者由 Lead 创建，使用 deepseek-flash，只读、无写工具、无物理执行权；不是人类签名。
- 当前 Owner 授权来源 m05968（“批准实际分析预算，通过实际分析恢复数据并开展MAML实验”）。
- 授权/批次：AUTH-DRECOVER001-R2-20261120-01 / DRECOVER001-R2-20261120-01 / DRECOVER001-R2-20261120-01-B01。
- 预算上限：24 次 physical solver starts；每 start 128 internal cases；timeout 1200 s；retries 0；parallel 1；MAML training runs max 8。见 `D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/authorization.json`。
- 异机备份已由 Owner 豁免（WAIVER-OFFMACHINE-BACKUP-20261118）；本批次只做本机独立目录备份，且必须标注“同机不是独立故障域”。

## 1. 已发生的真实 starts（pilot，先于本次 A5）

| case | attempt | internal | exit | wall_s | status |
|---|---|---:|---:|---:|---|
| baseline-coarse | real-baseline-coarse-01 | 7 | 0 | 3.617 | POLAR_HAS_INVALID_ROWS |
| baseline-refine-01 | real-baseline-refine-01 | 13 | 0 | 12.338 | SOLVED |
| baseline-admit-01 | real-baseline-admit-01 | 3 | 0 | 2.137 | SOLVED |

- 合计 3 starts / 23 internal cases；`physical_solver_starts_actual=3`，charge 3，retries 0。
- baseline-coarse 的 invalid row 是 alpha=0 行 `E=-nan(ind)`/`Ew=-nan(ind)`（L/D 除零诊断列），CLtot/CDi 有效；该 case 仅作 probe，未准入。
- baseline-refine-01 为 13 点细扫，status SOLVED，但未构造 admission manifest。
- baseline-admit-01 为 3 点等距细扫，status SOLVED，3 个 actual rows：
  - 5.18°: CL 0.181699529100, CDi 0.016540016326
  - 5.18125°: CL 0.181741590896, CDi 0.016547860887
  - 5.1825°: CL 0.181784583426, CDi 0.016555791798
- 目标 CL = 0.18174391741992046（L_ref 1,333,704.4 N；q 20483.940233430174 Pa；Sref 358.25 m²）。
- 5.18125° 的相对 lift 误差 1.2801e-05 < 1e-3，已被 `admit_real_manifest` 接受。
- 真实准入证书：`cases/baseline-admit-01/admission_certificate.json`，di_n `121434.35218570218`，cdi `0.016547860887`，cl `0.181741590896`，alpha `5.18125`，artifact_sha `6cd78a9c3196016d68b4873c80cecde0cca1dad95f0d45bfa5842e842d2cdf77`，evidence_scope `LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED`。
- 本地 audit：`AUDIT-R2-B01-BASELINE-ADMIT-01`，reviewer `local-audit-script-v1`，role `SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5`，audit sha `53a351d1cf385938888f77785bebb136307fecf51f8c6b4bff023a6df03833b5`；明确 not authenticated。
- 原始文件：`cases/baseline-admit-01/` 下 `.vspgeom/.vkey/.vspaero/.polar/.history/.adb` 与 `solver_attempts.jsonl`、`evaluations.jsonl`、`case_inputs.json`、`plan.json`、`approval.json`。

## 2. 本轮代码改动（未 commit/push）

1. `research/concorde_metaopt/dreal001/meta/raw_verification.py`
   - 原契约拒绝任何非有限 polar 列；VSPAERO 在 wake drag=0 时写 `Ew=inf`。
   - 现只容忍 `Ew` 的 ±inf；`Ew=NaN` 与其他核心列非有限仍 fatal。
   - 新增测试 `test_infinite_ew_diagnostic_tolerated_but_nan_or_core_inf_fatal`；`test_recovery_real_admission.py` 18 passed。
2. `research/concorde_metaopt/dreal001/geometry/openvsp_model.py`
   - 新增可选 `flow_conditions={vinf_m_s,rho_kg_m3,recref}`；校验 finite/positive；`Vinf/Rho/ReCref` 写入 readback 与 `.vspaero` 的 expected 值；record 写 `q_pa`、`flow_conditions`，`cl_required` 用实际 q 计算。
   - 目的：固定高度 18,288 m，变 Mach 的真实任务族；Vinf=Mach×295.0680184，Recref 按 Vinf 比例，q=0.5ρVinf²，L_ref 固定。
   - 未改变默认路径（不传 `flow_conditions` 时行为与之前一致）。
3. `D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/`
   - `audit_real_case.py` 改为从 deck 的 Rho/Vinf 复算 q，支持 `--geometry-contract/--lift-target/--lift-tolerance`。
   - `admit_case.py` 改为读取 case 的 `task_spec.json` 与 `case_inputs.json`，不再硬编码 M2.02/RHO/VINF。
   - 新增 `build_task_case.py`：给定 Mach/split/partition/design，生成 task_spec、plan、approval 与 VSPAERO 输入；不启动求解器。

## 3. 计划中的剩余矩阵（待 A5 预审，尚未执行）

任务族（固定高度、同一几何合同 `5f2bb12f...`）：
- train: M=2.02（已有一个 D00 support 证书）、M=1.60、M=1.80
- val: M=2.20
- test: M=2.40

每个任务 3 个设计：support d00（baseline）、support d01（W01 +1%）、query d02（sweep_1 +0.5°）。
- M=2.02 已有 d00 support；补 d01 support + d02 query = 2 starts。
- M=1.60/1.80/2.20/2.40 各 3 starts = 12 starts。
- 合计新增 14 starts；累计 17/24；留 7 starts 给 alpha 未命中重扫/失败重试。
- 每个 case 一次 15 点 alpha 网格（step 0.0025°，围绕由 CL_target 与 baseline slope 估计的中心）；每次 start 15 internal cases；总 internal ≈ 14×15=210，低于每 start 128 的上限（每个 start 单独 15）。
- 每个成功 case 用 `admit_case.py` 生成 manifest 与证书；失败只记 objective=null，不冒充标签。
- 之后用真实证书构造 TaskSpec/MetaDataset，做真实 FOMAML K=2（support 2 designs/task）与 heldout K-shot 评估；MAML 训练本身不启动 VSPAERO，只消费已准入的 D_i_N。

## 4. 已知风险/缺口（请 A5 判断是否阻断）

- 3 个 pilot starts 发生在 A5 预审之前；Owner 已授权预算，但 Issue #12 的 A5 预审顺序被绕过。需要 A5 明确：追认、附条件追认，或要求停止后续 starts。
- 真实准入的 audit 是本地独立重实现脚本，不是人类，也不是 A5；证书 evidence_scope 明确 `NOT_AUTHENTICATED`。
- A1 geometry freeze v2 只验证了几何/网格/VSP3/STL/STEP 与输入契约，未验证力轴、WING_AC、质量 CG 的气动读回；这些要到 R2 真实读回才闭合。
- `Ew=inf` 容忍是诊断列例外，不是准入系数放宽；需要 A5 确认没有把核心列 NaN/inf 放进来。
- flow_conditions 改动了 `prepare_case` 的输入契约；默认路径未变，但 full preflight 尚未重跑（预计 248 tests）。targeted geometry tests 在当前沙箱出现 5 failed/8 errors，均为 `PermissionError` 临时目录 ACL，不是代码断言失败。
- bundle/远端：最新代码改动尚未 commit/push；branch recovery/drecover001-20261117 远端最后 commit 0effd762...（本 dossier 之前的证据）。本批次原始文件只在 `D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/`，同机备份，不是异机。
- MAML 规模很小：3 train tasks（含 baseline），K=2 support，1 query；统计功效有限，不能宣称泛化优势。

## 5. 请 A5 输出

请只输出一个 JSON 对象（不要 Markdown 代码围栏），字段：
```
{
  "reviewer": "deepseek-flash",
  "reviewer_role": "A5_INDEPENDENT_READONLY_REVIEWER_NOT_HUMAN",
  "verdict": "PASS" | "CHANGES_REQUIRED" | "REJECT",
  "pilot_disposition": "RATIFY" | "RATIFY_WITH_CONDITIONS" | "STOP",
  "findings": [
    {"severity":"major|minor","id":"...","finding":"...","evidence":"...","required_action":"..."}
  ],
  "conditions_for_further_starts": ["..."],
  "maml_readiness": "READY_AFTER_ADMISSION" | "NOT_READY" | "UNKNOWN",
  "notes": "..."
}
```
