## D-REAL-001 P2a v2 — R10 真实执行 A5 签署最终回执（Lead 发布）

- 发布人：Lead；发布依据：Lead 决策 **L-14**（接受 R10 预注册科学自动停并关闭 R 线执行，physical_authorization=false）与 **L-15**（记账 charged vs actual 双口径澄清）。
- 批次 / run：**DREAL001-P2-20261111-15** / **DREAL001-P2A2R10-20261111-01**；窗口 2026-11-11T18:30:00Z – 2026-11-12T04:00:00Z。
- A5 回执（原文见下）：ID **A5-P2A-V2-R10-FINAL-RECEIPT-20261111**；MD SHA256 `af33d0844ae6e6340aff9b2ece78659ab660f21728bd845f5e56b2ae8fe58198`（17,238 B）；JSON SHA256 `7bfdb45f9ef2fdc78dc36c5dba2c10269e3be3bbf9edb20a9f836ab4052e0a3c`（12,412 B）；A5 树 commit `964a451a0b43c037e5a64f0c81a006a27eaa7058`。
- 配套独立审计：**A5-P2AV2R10-POSTRUN-AUDIT-20261111**（85/85 PASS；v2 commit `9ac700427ba92283894d147cc862ef7850d5dc77`，仅 main/total 措辞勘误）。
- 补充：A2 证据入库（run dir 2,228 文件 append-only，commit `f299ce22…`）、停止说明（`fbe92ef1…`）、记账双口径 addendum（`f639087e…`）；A3 描述性统计（`699ce2a…`）。
- **边界声明**：本回执不构成任何执行授权；R10 已按 L-14 关闭（无 R11、不再真实求解、approval 不复用）；R1–R10 全部排除于 E1–E6 端点与优化结论；不以任何方式宣称 P2 完成、优化增益或物理有效性。
- 记账口径：R10 实际 **91 starts / 637 internal**；累计实际 **153 / 1,083**；授权/charged（预留）累计 **448 / 3,148** vs caps 451/3,157（余 3/9）——不得把 448/3,148 写为已实际消耗。
- A5 约束：physical_call_count=0、solver_started=false、未 push、未改 R1–R10 证据字节。

---

# D-REAL-001 P2a v2 R10 真实执行：A5 签署最终回执（供 Issue #9 发布）

- **回执 ID：A5-P2A-V2-R10-FINAL-RECEIPT-20261111**
- 签发人 / 角色：A5（独立复核与签署负责人）
- 签发时间：2026-11-11（UTC）
- 批次 / run：**DREAL001-P2-20261111-15** / **DREAL001-P2A2R10-20261111-01**
- 窗口 / token：2026-11-11T18:30:00Z – 2026-11-12T04:00:00Z / **WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z**
- 治理依据：Lead 决策 **L-14**（接受 R10 科学自动停并关闭 R 线执行，physical_authorization=false）、**L-15**（R10 记账 charged vs actual 双口径澄清）、L-13（post-GO launcher 预检修复）、L-12（R10 internal 记账与最后尝试）、L-09/L-10（协议 D）；已签署 approval **4e67eac5…/84,140 B**；Lead GO **260e284a…/9,962 B**。
- 配套独立审计：**A5-P2AV2R10-POSTRUN-AUDIT-20261111**（v2 commit 9ac700427ba92283894d147cc862ef7850d5dc77（原始审计 563d95fe36f57bcee8312aab5ef878c9cd1f4b84；仅 §2.1 main/total 措辞勘误，结论/数字/证据不变））。
- **重要声明：本回执不构成任何执行授权。** R10 已按 L-14 关闭：无 R11、不再进行真实求解、approval 不复用。
- A5 约束遵守：**physical_call_count = 0；solver_started = false；未 push；只写 A5 工作树 docs/reviews 与 docs/receipts；R1–R10 证据与 run dir 全部只读未改。**

## 1. 总体结论

**R10 按预注册科学规则自动停止，停止合法、证据完整、账本闭合、无执行层违规；P2a v2 六臂 pilot NOT COMPLETED；E1–E6 端点 NOT_COMPUTABLE；无优化增益结论；外部物理 NOT_VALIDATED。R1–R10 全部排除于端点与优化结论，无 R11。**

| 项 | 结论 |
|---|---|
| 真实 VSPAERO 回路 | **部分验证**：preflight 2/2 PASS_BYTE（polar 字节等于 approval 期望）+ R10 全批 91 次真实物理 start（其中 main 89、preflight 2）；六臂优化循环未完成 |
| 内部气动优化增益 | **NOT_COMPUTABLE**（六臂 pilot 未完成；仅 BO/DE 单 seed 描述性观察，不构成增益/排名/winner/显著性） |
| 外部物理支持 | **NOT_VALIDATED**；fuel_burn_kg = null |
| 停止性质 | 预注册 invalid-ratio 科学自动停（48 次评估时 invalid 13 = 27.083% > 25%），非故障、非硬件/窗口问题 |
| 物理记账 | R10 实际 91 starts / 637 internal；累计实际 153/1,083；授权/charged 口径累计 448/3,148 vs caps 451/3,157（余 3/9） |
| R 线状态 | **已关闭**（L-14）：无 R11、无新批次、approval 不复用 |

## 2. 三层结论（严格分开，不得合并表述）

### 2.1 SOLVER_LOOP_VERIFIED = 部分（PARTIAL）

- **已验证**：真实 VSPAERO 调用链路 + preflight 回放字节级验证（PRE-01 polar 455082e2ac8029216a811c89aaa20b34fd9d73faa319eed23da5348e3de4bc87；PRE-02 0287afe0d7e5a91bc286c0b6cbd1ca5623d8aafe65110862fe263925129dd33f；各 7,933 B，与 approval 期望逐字节一致；2/2 PASS_BYTE）；R10 全批 91 次真实物理 start（其中 main 89、preflight 2）、35 次有效设计评估、ledger 91 start/91 end、单 writer PID 27588。
- **未验证**：六臂 main 优化循环（仅 BO 完整 32 次评估、DE 部分 16 次；13 次 INVALID_NUMERICAL；PSO/ABO/ADE/APSO 未启动）。
- 因此只能表述为「真实求解与回放链路部分可用」，**不得整体声称 SOLVER_LOOP_VERIFIED**。

### 2.2 INTERNAL_AERO_OPTIMIZATION_GAIN = NOT_COMPUTABLE

- 六臂 pilot 未完成；BO/DE 为单 seed（seed=42）、无重复、无 baseline 对照；DE 右删失（16/32 预算）。
- **不宣布 winner、不排名、不做显著性检验/置信区间、不报百分点改进、不合并跨臂或跨族数据。**
- 仅可报告 A5 与 A3 的 BO/DE 描述性统计（见 §6）。

### 2.3 EXTERNAL_PHYSICS_SUPPORTED = NOT_VALIDATED

- **fuel_burn_kg = null**；未进行外部物理校验；不声明物理有效性、燃油性能或真实飞行结论。

## 3. 门禁与签署链（全部经 A5 独立字节核验）

| 环节 | 交付 | 关键值 |
|---|---|---|
| G-P2AV2R10-PRE | A5 commit **48b91bf67b6b9f0f9e27e69fb6b5aca1fec3a15f** | 57/57 checks PASS（53 PASS + 4 PASS_WITH_DISCLOSURE）；57 conditions；refs_final 14 |
| Lead 签署 approval | **4e67eac5… / 84,140 B**，approved_at 2026-11-11T18:51:14Z | conditions 57；refs 14；supersedes R9 b502b484…/76,257 B/physical 62；amendment seq10 R10_INTERNAL_ACCOUNTING_FIX physical 62 |
| 真实 post-approval dry-run | **e9f3471d… / 19,427 B** | 46/46 PASS；386 planned / 0 emitted / internal 2,702；physical 0；窗口 open |
| C-P2AV2R10-02 | A5 commit **6f1498119c3a8e5d5283386dddda73ce0773c506** | 27/27 PASS；0 FAIL/0 REVIEW；PASS 不代表执行授权 |
| Lead GO | **260e284a… / 9,962 B**，token **LEAD_GO_P2AV2R10_EXEC_20261111T185534Z** | physical_call_count_at_go 0；授权 2 preflight + diagnostics NOT in matrix |
| 执行 | 18:58:01Z PID 27588 | GATE=PASS；prestart prefrozen gate PASS（79 checks、119 static、A1 guard all_equal、6 triples、physical 0） |
| 停止 | 19:13:55Z | scientific_auto_stop；ledger 91/91；pending 0；retry 0 |

## 4. R10 执行事实与记账（独立复核）

| 阶段 | starts | internal | 说明 |
|---|---:|---:|---|
| preflight | 2 | 14 | 2/2 PASS_BYTE；计入物理但排除于 E1–E6 |
| diagnostics | 0 | 0 | DIAGNOSTICS_NOT_IN_MATRIX；0/0，无 spawn；引用 R9 诊断证据 |
| main | 89 | 623 | 48 次评估 = 35 SOLVED_VALID + 13 INVALID_NUMERICAL |
| **total** | **91** | **637** | **637 = 7 × 91（INTERNAL_PER_START_POLICY）** |

- ledger：solver_attempts.jsonl 182 行 = 91 start / 91 end；unique case 91；每 case 恰 1 start/1 end；单 writer PID 27588；first 18:58:04Z / last 19:13:55Z；pending 0；retry 0。
- end 状态：SOLVED_VALID 78（含 preflight 2）/ LIFT_MATCH_FAILED 6 / SOLVER_FAILED 7。
- invalid 13 = LIFT_MATCH_FAILED 6 + SOLVER_FAILED 7；按臂 BO 9（LIFT 4 / SOLVER 5）、DE 4（LIFT 2 / SOLVER 2）；单臂连续 invalid 最大 2（阈值 6）；累计 13（阈值 64）。
- phase_conservation 全 ok；accounting_conservation_ok=true；reserve_starts_used=0；voided_designs=[]；final_run_manifest 45 designs 全 PAIR_READY/usable/chain valid。

## 5. 预注册自动停（非故障）与预算双口径（L-15）

### 5.1 自动停规则

- 冻结常量：invalid_ratio_min_evaluations=48、invalid_ratio_max=0.25、invalid_consecutive_max=6、invalid_total_max=64、invalid_status=INVALID_NUMERICAL。
- 第 48 次 main 评估时 invalid 累计 13，13/48 = **27.083% > 25%**，且样本量达到最小值 48 → 精确触发；第 47 次样本不足不触发。
- 停止后：stop_report.phase=scientific_auto_stop、arm_id=DE、message=ARM_STOPPED_STOPPED_SCIENTIFIC_INVALID_RATIO；其余四臂按串行臂序 NOT_RUN（0 starts）。

### 5.2 预算双口径（必须分开呈报）

| 口径 | R10 阶段量 | 累计量 | caps 451/3,157 | 余量 |
|---|---|---|---|---|
| **授权/charged（计划预留）** | 386 starts / 2,702 internal | **448 / 3,148** | 该口径强制 | **3 / 9** |
| **实际物理消耗** | **91 / 637** | **153 / 1,083** | 451 / 3,157 | **298 / 2,074** |

- 448/3,148 = 前序 charged 62/446 + R10 计划预留 386/2,702；**它不是已消耗物理预算**。A2 停止说明与 L-14 中「累计 448/3,148」措辞应按 charged/授权口径阅读，属口径未标注（非事实错误，L-15 已澄清；A2 addendum 66f20f8b…/2,833 B 已提交）。
- 实际消耗以 ledger（91 start/91 end）与 batch_summary 分阶段字段为准；累计实际 153/1,083。
- 两口径均 ≤ caps；但授权口径余 3/9 无法支持任何有意义的新批次，这与 L-14 关闭决定一致。

## 6. E1–E6 可用性与描述性统计（R10 main only；R1–R9 与诊断排除）

| 端点 | 冻结定义 | 可用性 / 事实 |
|---|---|---|
| E1 | per-design primary = 0.5×CDi(f1) + 0.5×CDi(f2)（within-design） | 六臂端点 **NOT_COMPUTABLE**；BO n=23、DE n=12 仅描述性；四臂 0 |
| E2 | best-at-budget（每臂 B=32） | **NOT_COMPUTABLE**；BO 32/32 描述 best；DE 16/32 右删失仅 observed-best；不得作 at-budget 端点 |
| E3 | starts-to-baseline | **NOT_COMPUTABLE**；无冻结 objective baseline（62/446 只是 accounting baseline） |
| E4 | feasible rate = valid/evaluations | 六臂比较 **NOT_COMPUTABLE**；BO 23/32=71.875%、DE 12/16=75.0%，预算不等/右删失/单 seed，禁止比较 |
| E5 | SINGLE_SEED_42 稳定性/重复性 | **NOT_COMPUTABLE**；重复 0 |
| E6 | cold-start 配对增益 | **NOT_COMPUTABLE**；无冷启动 baseline/配对 |

### 6.1 BO/DE 描述性统计（仅事实，不构成比较或 winner）

| 指标 | BO（n=23） | DE（n=12，部分） | 全部 valid（n=35） |
|---|---:|---:|---:|
| primary mean | 0.016824488533 | 0.016841321638 | 0.016830259883 |
| primary median | 0.016228040309 | 0.015326776729 | 0.016228040309 |
| primary min | 0.010006880012 | 0.012894807420 | 0.010006880012 |
| primary max | 0.023250790543 | 0.024885243083 | 0.024885243083 |

- 仅 BO/DE 单 seed 描述性观察；**禁止**解读为优化增益、排名、winner 或显著性；DE 为右删失部分数据。
- 48 次评估对应 45 个 distinct designs：3 个预冻结设计（d51866f7d3c49303/eb00b7ad545243e6/dc96d2438a6dddc3）在 BO/DE 各评估一次；按冻结 per-design 定义处理，不做跨臂/跨族合并。
- A3 独立统计（commit 699ce2abfcbeef3a47934bfa88bb173ec00ac489；r10_stats_20261111.json 5705269b…、.md 0728ccae…、.csv 007e1a9b…）作附录：21 项检查 20 PASS/1 FAIL（A17：batch_summary DE valid_designs=11 vs evaluations 12，评估级权威）；A3 披露 D1–D5 与 A5 一致（双口径、D2 DE 11 vs12、D3 INVALID 行族字段不完整、D4 preflight case polar_sha256=null 但字节一致、D5 manifest builder 计数）。

## 7. R1–R10 排除与不变量

| 轮次 | 结果 | 记账（starts/internal） | 处置 |
|---|---|---|---|
| R1 | preflight 2/2 SOLVER_FAILED，main NOT_RUN | 2/14 | 永久排除 |
| R2 | preflight non-SOLVED replay，main NOT_RUN | 2/14 | 永久排除 |
| R3 | main setup PermissionError，停 | 2/14 | 永久排除 |
| R4 | UNIT_BOX_VECTOR_NOT_ACCEPTED，停 | 2/14 | 永久排除 |
| R5 | launcher import/setup abort | 0/0 | 永久排除 |
| R6 | main S1 NaN / LIFT_MATCH_FAILED | 3/21 | 永久排除 |
| R7 | main FROZEN_BYTES_SHA_MISMATCH（诊断 4/28 已跑） | 6/42 | 永久排除 |
| R8 | setup PREFROZEN_GEOM_MISSING | 0/0 | 永久排除 |
| R9 | diagnostics ACCOUNTING_INCONSISTENT，main NOT_RUN | 6/42 | 永久排除 |
| R10 | 预注册科学自动停（BO 完成、DE 部分） | 91/637 | 排除于 E1–E6/优化结论；按 L-14 关闭 |

- 排除口径：以上轮次证据只读保留，均不得进入 E1–E6 端点、优化增益、winner 或 pooled 统计；前序累计实际 62/446 已按 charged/actual 双口径披露于 §5.2。
- 身份不变量（A5 实算）：A1 evaluator f74a4752…/58,291、freeze_api 31d78182…/27,288、bundle 995bb12f…；plan ba6eaa49…/52,774；approval 4e67eac5…/84,140；executor ed0f2324…/99,591；launcher 执行时 23106df2…/29,361（post-D-11）、pre-D11 476481e6…/29,361 字节保留；R1–R9 approval 9/9 字节未变；R10 run dir 2,228 文件与 A2 sums 清单逐项匹配（2,228/2,228），无缺失/多余。

## 8. 披露项

| ID | 级别 | 披露 |
|---|---|---|
| D-01 / D-11 / L-13 | 流程 | post-GO 后 launcher 预检条件数 52→57 单行修复（476481e6→23106df2，同 29,361 B；原字节保留；L-13 追认，A5 复核同意继续，零物理）。C gate 6f14981 锚定旧 launcher；本回执同时记录新旧锚点。任何后续执行层字节变更=硬停（已无后续执行）。 |
| D-02 | 记录 | batch_summary.arms.DE.valid_designs=11 vs evaluations.jsonl DE valid=12（stop-path 计数）；评估级以 evaluations 为权威；不影响停批判定。 |
| D-03 | 记录 | INVALID 行 failed_family/per_family 字段不完整；族/角色由 ledger case_id 后缀复算；计数不变。 |
| D-04 | 记录 | preflight_result case-level polar_sha256=null；A5 重算 polar 文件 SHA 与 approval expected 一致，PASS_BYTE 成立。 |
| D-05 | **重要** | 448/3,148 为 CHARGED_PROJECTED（授权/预留），不是已消耗物理预算；实际累计 153/1,083（余 298/2,074）。A2 停止说明/L-14 措辞未标注口径，属披露性瑕疵（非事实错误）；L-15 与 A2 addendum 66f20f8b…/2,833 B 已澄清。 |
| D-06 | 记录 | final_run_manifest physical_call_count=0 是 builder 计数；run 物理以 ledger/batch_summary/stop_report=91 为准。 |
| D-07 | 记录 | executor_run.log 为两次启动合流（首行 REFUSED 18:56:53，零物理；正式启动 18:58:01）；物理只取 canonical ledger start 事件 91。 |
| D-08 | 记录 | run dir 内 A2_R10_STOP_NOTE.md 为停止后 19:16:35Z 追加披露（非执行产物）；v2 说明在 A2 docs/evidence（fc0e81ef…/12,243 B）。 |
| D-09 | 记录 | 48 评估/45 distinct designs，3 预冻结设计两臂各评一次；按冻结 per-design 定义，不做跨臂/跨族合并。 |
| D-10 | 流程 | C-P2AV2R10-02 在 D-11 前发出并锚 old launcher；L-13 裁定无需重签；A5 保留溯源。 |
| D-11 | 记录 | A3 统计为外部独立交付（commit 699ce2a），A5 已核其字节并交叉核对计数/端点可用性；A5 未运行 A3 工具。 |
| D-12 | 记录 | stop_report.internal_solver_cases=null；internal 按 7×starts 政策推导并记录 637；不接受 ledger internal 0 读数。 |
| D-13 | 治理 | L-14/L-15 关闭 R 线：无 R11、无新执行授权、approval 不复用；本回执不构成授权。 |

## 9. 证据索引（A5 实算）

| 证据 | SHA256 | bytes |
|---|---|---:|
| run dir inventory（2,228 文件） | digest 105f3bc9363d11227a9de39cbc77c1ae6fb289b1863ad648540ceb08bee5bbea | 207,718,755 |
| batch_summary.json | a4ea4840ccdeea0e00cc8496c5fc8c69aea901afcabe9884394d3064285a36a9 | 100,838 |
| stop_report.json | a23964eba50a15a703bfb1f736ad97c6d7b8a040844ef23f70a84eca4c35db8b | 802 |
| solver_attempts.jsonl | 0614c0182958a50b6fdac2b463141afd005c6551498174514424b063eb840409 | 68,461 |
| evaluations.jsonl | 01585d23e0b00403bd83eddfdad9499f3373decef851686922da08630f5a431a | 63,990 |
| preflight_result.json | daf047e62e043ce193aad5c0fc84e0ec8561d823f9893037e9c440b65aea3e47 | 5,771 |
| diagnostics.json | 4976fda2d9ea3b903ac7353802f2492400dd92aead2f829aeff1f69315341613 | 1,973 |
| final_run_manifest.json | 2522f951f91c01c7b8c82294d94abb3d58dc36878cbdb424d112a7cfc2404cca | 203,583 |
| executor_run.log | a0c9c9dba45989f587d8f047c644597dc05334e807940d9d6c29f39400f614f7 | 1,773 |
| prestart_prefrozen_gate.json | a87b0288e633f3e010568a27cf7a575c61393ba479cb534c7e55b9ca8bc15952 | 37,480 |
| runtime/family_pair_manifest.append_only.jsonl | 36bbc3851e7296c7400ef15a61279b0a10736d0fec207fbcf7ae40d4ee6db0b6 | 211,393 |
| approval.json | 4e67eac52833d8dfab8b8027a0838b68de15f26d9a072edb0515ece22414068c | 84,140 |
| plan.json | ba6eaa49e181b2cacc048362dd00e57458ceba73165b68f1776ae4f3af43b4d4 | 52,774 |
| post_approval_dry_run.json | e9f3471dcd4d6b89e3cf0daf7e6d8a6236741225f3867e4b4cedd7fee2c3cec1 | 19,427 |
| lead_go_r10_20261111T1856Z.json | 260e284a5c9939b9be2ee08e9a2e986d43345818e682ce34ecff91926a91b83a | 9,962 |
| L-14 md | e13435d3f16eb5ac0d33c19681f99dcf595e56a4ab521382fdfd8e2e350ea395 | 4,966 |
| L-15 md | 1c76a34d95db8c29e92e53bcde6d023181f42b4b9a0010434be06fa83e3f7976 | 2,819 |
| A2 stop note v2 | fc0e81ef273b4c272359ba72002ff229199002b649a139c9b8fd6321a15f671f | 12,243 |
| A2 L-15 addendum | 66f20f8b3004acff8ddce0fbba146f66c6a3d37ac63ffe9a8e2706a3fa9c0950 | 2,833 |
| A3 stats json | 5705269ba2bb7015f703fb2c9bb24da2f300bda0e7c2d83848a369e8d562daf9 | — |

- 证据 commit：R10 run dir 全量 f299ce22f0ea7cc0b082e795a34a35f980a4beed；A2 停止说明 v2/decomposition/pre-D11 launcher fbe92ef1c75f8e85a59e3455cbeaf577b450006f；A2 L-15 addendum f639087e470ede85af6a0f3fa789623f975655da；A3 统计 699ce2abfcbeef3a47934bfa88bb173ec00ac489；Lead L-14 d064af0、L-15 596d932、GO 记录。
- A5 交付：G-P2AV2R10-PRE 48b91bf、C-P2AV2R10-02 6f14981、post-run 审计 563d95fe、本回执（下一 commit）。

## 10. A5 签署块

- 回执裁决：**A5-P2A-V2-R10-FINAL-RECEIPT / R10_SCIENTIFIC_AUTO_STOP_VALID_UPHELD / SIX_ARM_PILOT_NOT_COMPLETED / E1-E6_NOT_COMPUTABLE / NO_OPTIMIZATION_GAIN / EXTERNAL_PHYSICS_NOT_VALIDATED / R1-R10_EXCLUDED / NO_R11 / R-LINE_CLOSED**
- 签发人：A5（独立复核与签署负责人）；签发日期：2026-11-11（UTC）
- A5 physical_call_count：**0**；solver_started：**false**；push：**false**
- 签署声明：本回执基于 A5 独立字节核验与独立审计（85/85 PASS）；不宣布 pilot 完成、不宣布优化增益、不做 winner/显著性/跨族比较、fuel=null、物理 NOT_VALIDATED；引用 L-14 与 L-15 双口径；**本回执不构成任何新的执行授权**，R10 已关闭，无 R11。
- 关联审计：A5-P2AV2R10-POSTRUN-AUDIT-20261111（v2 commit 9ac700427ba92283894d147cc862ef7850d5dc77（原始审计 563d95fe36f57bcee8312aab5ef878c9cd1f4b84；仅 §2.1 main/total 措辞勘误，结论/数字/证据不变））。
