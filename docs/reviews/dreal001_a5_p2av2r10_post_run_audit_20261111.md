# D-REAL-001 P2a v2 R10 真实执行 post-run 独立审计（A5）

- 审计 ID：**A5-P2AV2R10-POSTRUN-AUDIT-20261111**
- 审计人 / 角色：A5（独立复核与签署负责人）
- 审计对象：batch **DREAL001-P2-20261111-15** / run **DREAL001-P2A2R10-20261111-01**
- 窗口 / token：2026-11-11T18:30:00Z – 2026-11-12T04:00:00Z / WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z
- 执行：18:58:01Z 启动（launcher PID 27588，GATE=PASS），19:13:55Z 预注册科学自动停（约 15m54s）
- 治理依据：Lead 决策 **L-14**（ACCEPT_R10_SCIENTIFIC_AUTO_STOP_AND_CLOSE_R_EXECUTION，physical_authorization=false）、**L-15**（R10 记账 charged vs actual 双口径澄清）、L-13（post-GO launcher 条件数预检修复）、L-12（R10 internal 记账与最后尝试）、协议 D（L-09/L-10）。
- A5 约束：**physical_call_count = 0；solver_started = false；未启动任何 VSPAERO；未 push；只写 A5 工作树 docs/reviews；R1–R10 旧证据只读未改；未改 run dir。**
- **本审计不构成任何执行授权。**

## 1. 审计裁决

**裁决：R10_SCIENTIFIC_AUTO_STOP_VALID_UPHELD__SIX_ARM_PILOT_NOT_COMPLETED__NO_OPTIMIZATION_GAIN__EXTERNAL_PHYSICS_NOT_VALIDATED__R1_R10_EXCLUDED__NO_R11**

- A5 独立复核 **85/85 项检查 PASS**（0 FAIL），覆盖 run dir 全量字节、ledger、计数与守恒、预注册停止规则、身份字节、E1–E6 可用性、A1/R1–R9 不变量、治理文档与 D-11 披露。
- R10 停止由**已签署的预注册科学规则**触发（main_evaluations=48 时 invalid=13、27.08% > 25%），不是执行层故障、不是 solver 失败、不是硬件/窗口异常；无 retry、无 pending 修复、无隐藏 start、单 writer。
- P2a v2 六臂 pilot **NOT COMPLETED**：仅 BO 完成 32 次评估、DE 部分 16 次后停批，PSO/ABO/ADE/APSO 未启动（0 评估）。六臂 E1–E6 端点 **NOT_COMPUTABLE**；仅 BO/DE 单 seed 描述性统计可用。
- R1–R10 全部排除于 E1–E6 端点与优化结论；fuel_burn_kg = null；physical_validation_status = NOT_VALIDATED；无 winner、无显著性/CI、无跨族或跨臂合并比较。
- L-14 接受停批并关闭 R 线：**无 R11、不再进行任何真实求解、不复用 R10 approval**；caps 余量不允许新批次。A5 同意该裁决（无异议）。

## 2. 执行时间线与独立核验

| 时间 (UTC) | 事件 | 证据 |
|---|---|---|
| 18:51:14 | Lead 签署 R10 approval（57 conditions / refs 14） | approval.json 4e67eac5… / 84,140 B |
| 18:52:12 | post-approval dry-run 46/46 PASS、386 planned / 0 emitted、physical=0 | post_approval_dry_run.R10_20261111T185212Z.json e9f3471d… / 19,427 B |
| 18:55:34 | Lead GO：LEAD_GO_P2AV2R10_EXEC_20261111T185534Z | lead_go_r10_20261111T1856Z.json 260e284a… / 9,962 B |
| 18:56:53 | 首次启动被 launcher 预检拒绝（conditions 52 期望 vs 57），零物理 | executor_run.log 第 1 行 REFUSED；D-01 |
| 18:58:01 | 修复后重启，PID 27588，GATE=PASS / prefrozen gate PASS（119 static、A1 guard all_equal、6 triples） | executor_prestart.json 2808306b…；prestart_prefrozen_gate.json a87b0288… |
| 18:58:04–18:58:12 | preflight PRE-01/PRE-02 均 SOLVED_VALID、PASS_BYTE | preflight_result.json daf047e6… / 5,771 B |
| 18:58:12 起 | diagnostics DIAGNOSTICS_NOT_IN_MATRIX：0 starts / 0 internal、skipped、无 spawn | diagnostics.json 4976fda2… / 1,973 B |
| 18:58:12–19:13:55 | main：48 次评估（BO 32=23 valid/9 invalid；DE 16=12 valid/4 invalid） | evaluations.jsonl 01585d23… / 63,990 B |
| 19:13:55 | 触发 invalid-ratio 科学自动停，写 stop_report / batch_summary | stop_report.json a23964eb… / 802 B；batch_summary.json a4ea4840… / 100,838 B |

- 窗口合规：全部物理事件（18:58:04Z–19:13:55Z）落在 18:30Z–04:00Z 批准窗口内；GO 授时早于启动；无窗口越界。
- 执行层无异常：timeout 60 s 从未触发；OMP=1、serial、单 writer PID 27588；无 pending start 修复、无 retry、无重复 case start。

## 3. 计数、账本与守恒（独立复核）

| 阶段 | starts | internal cases | 说明 |
|---|---:|---:|---|
| preflight | 2 | 14 | 2/2 PASS_BYTE，排除于 E1–E6，但计入物理预算 |
| diagnostics | 0 | 0 | NOT_IN_MATRIX，0/0，无 spawn |
| main | 89 | 623 | 48 次评估（35 valid + 13 INVALID_NUMERICAL） |
| **total** | **91** | **637** | **637 = 7 × 91（INTERNAL_PER_START_POLICY）** |

- ledger：solver_attempts.jsonl 182 行 = 91 start / 91 end；unique case 91；每 case 恰 1 start/1 end；未匹配 0；pending 0；单 writer PID 27588；first 18:58:04Z / last 19:13:55Z（= stop created_utc）。
- phase_conservation：preflight/diagnostic/main/total 全部 ok；internal_cases_policy = 7 × starts；accounting_conservation_ok = true。
- end 状态分布：SOLVED_VALID 78（含 preflight 2）/ LIFT_MATCH_FAILED 6 / SOLVER_FAILED 7。
- invalid 分解：13 行 = LIFT_MATCH_FAILED 6 + SOLVER_FAILED 7；按臂 BO 9（LIFT 4 / SOLVER 5）、DE 4（LIFT 2 / SOLVER 2）；单臂连续 invalid 最大 = 2（阈值 6，未触发）；累计 invalid 13 ≤ 64（未触发）。
- INVALID 行的族/角色归因由 ledger case_id 后缀复算：failed_family_slot f1 7 / f2 6；stages：f1-only single start 7、reached f2 two starts 6（D-03）。

## 4. 预注册自动停规则复核（非故障）

- 冻结常量（plan/approval/batch_summary 一致）：invalid_ratio_min_evaluations=48、invalid_ratio_max=0.25、invalid_consecutive_max=6、invalid_total_max=64、invalid_status=INVALID_NUMERICAL。
- 触发点：第 48 次 main 评估时累计 invalid=13，13/48 = **27.083% > 25%**，且样本量达最小值 48 → 规则按预注册文本精确触发；第 47 次时样本量未达 48（不触发），逻辑一致。
- stop_report：phase=scientific_auto_stop、arm_id=DE、message=ARM_STOPPED_STOPPED_SCIENTIFIC_INVALID_RATIO；batch_summary：status=STOPPED、scientific_stop=true、physical 91、fuel null、NOT_VALIDATED。
- 其余四臂 NOT_RUN 原因：预注册串行臂序 BO→DE→PSO→ABO→ADE→APSO，任一臂非 COMPLETED 即停；BO COMPLETED 后 DE 科学停批，故四臂 0 starts / 0 evaluations。不存在隐藏执行或跳过记录。
- 结论：该停止是科学结果的一部分（invalid 容忍规则），不构成执行错误；A5 支持 L-14 的接受与关闭决定。

## 5. 预算与双口径记账（L-15）

| 口径 | starts | internal | caps | headroom | 语义 |
|---|---:|---:|---:|---:|---|
| **CHARGED_PROJECTED（授权/caps 口径）** | **448** | **3,148** | 451 / 3,157 | **3 / 9** | 前序 charged 62/446 + R10 计划预留 386/2,702 |
| **PHYSICAL_ACTUAL（实际物理消耗）** | **153** | **1,083** | 451 / 3,157 | **298 / 2,074** | 前序实际 62/446 + R10 实际 91/637 |

- R10 本批次实际：91 starts / 637 internal（preflight 2/14 + diagnostics 0/0 + main 89/623）；plan 计划预留 386/2,702，实际未用 295 starts / 2,065 internal。
- **重要口径澄清（L-15）**：batch_summary 的 cumulative_charged_* = 448/3,148 是 **CHARGED_PROJECTED**（前序 charged 62/446 + R10 计划预留 386/2,702），不是实际消耗；A2 stop note/L-14 中“累计（含 R10 实际消耗）448/3,148”的措辞不精确（charged vs actual 口径未标注，非事实错误）。A5 在本审计与最终回执中采用双口径，并引用 L-15。
- 两种口径均 ≤ 签署 caps 451/3,157；但只有 CHARGED_PROJECTED 是授权上限口径（余 3/9，无法再支持任何有意义的新批次），这与 L-14 的关闭决定一致。

## 6. E1–E6 可用性（冻结定义，R10 main only；R1–R9 与诊断排除）

| 端点 | 冻结定义 | 可用性 | 事实 |
|---|---|---|---|
| E1 | per-design primary = 0.5 × CDi(f1) + 0.5 × CDi(f2)（within-design） | **六臂 NOT_COMPUTABLE**；BO 描述可算、DE 部分 | BO n=23、DE n=12 valid；PSO/ABO/ADE/APSO 0 |
| E2 | best-at-budget（每臂预算 B=32） | **NOT_COMPUTABLE** | BO 32/32 完成，best 描述性；DE 16/32 右删失，仅 observed best-so-far；不得作 at-budget 端点 |
| E3 | starts-to-baseline（达到基线目标所需 starts） | **NOT_COMPUTABLE** | 包内无冻结 objective baseline（approval 的 62/446 仅为 accounting baseline） |
| E4 | feasible rate = valid/evaluations | **六臂比较 NOT_COMPUTABLE**；BO/DE 描述可算 | BO 23/32=71.875%；DE 12/16=75.0%；预算不等、右删失、单 seed → 禁止比较/排名 |
| E5 | SINGLE_SEED_42 稳定性/重复性 | **NOT_COMPUTABLE** | seed=42、重复 0、无重复设计评估 |
| E6 | cold-start 配对增益 | **NOT_COMPUTABLE** | 无冷启动 baseline、无配对对照 |

### 6.1 BO/DE 描述性统计（仅事实，不构成比较或 winner）

| 指标 | BO（n=23） | DE（n=12，部分） | 全部 valid（n=35） |
|---|---:|---:|---:|
| primary mean | 0.016824488533 | 0.016841321638 | 0.016830259883 |
| primary median | 0.016228040309 | 0.015326776729 | 0.016228040309 |
| primary min | 0.010006880012 | 0.012894807420 | 0.010006880012 |
| primary max | 0.023250790543 | 0.024885243083 | 0.024885243083 |

- 说明：primary/secondary 数值仅作 BO/DE 单 seed 描述性观察；**不得**解释为优化增益、排名或 winner；DE 为右删失部分数据。
- A3 独立统计（commit 699ce2a；r10_stats_20261111.json 5705269b…/md 0728ccae…/csv 007e1a9b…）与 A5 复核的评估级计数一致（BO 32=23/9、DE 16=12/4；BO median 0.01622804、DE median 0.015326777；invalid 13 = LIFT 6 + SOLVER 7）；A5 未运行 A3 工具（D-11）。
- 3 个预冻结设计（design15 d51866f7d3c49303、design16 eb00b7ad545243e6、design17 dc96d2438a6dddc3）在 BO/DE 两臂各评估一次，故 48 次评估对应 45 个 distinct designs；E1 的 per-design 口径按冻结定义处理，**不做跨臂/跨族合并**。

## 7. 三层结论（审计视图，与 L-14 一致）

### 7.1 SOLVER_LOOP_VERIFIED = 部分
- 已验证：真实 VSPAERO 调用 + preflight 回放链路字节级验证（PRE-01 455082e2…、PRE-02 0287afe0…，各 7,933 B，= approval expected；2/2 PASS_BYTE），以及 R10 全批 91 starts（其中 main 89、preflight 2）的真实物理执行与 35 次有效设计评估。
- 未验证：六臂 main 优化循环（只有 BO 完整、DE 部分；13 次 INVALID_NUMERICAL；PSO/ABO/ADE/APSO 未启动）。**不得整体声称 SOLVER_LOOP_VERIFIED。**

### 7.2 INTERNAL_AERO_OPTIMIZATION_GAIN = NOT_COMPUTABLE（六臂 pilot）
- 六臂 pilot 未完成；只有 BO/DE 单 seed 描述性观察，无有效六臂端点、无 baseline 对照、无重复/配对；**不宣布 winner、排名、显著性、百分比改进或优化增益**。

### 7.3 EXTERNAL_PHYSICS_SUPPORTED = NOT_VALIDATED
- fuel_burn_kg = null；未进行外部物理校验；不声明任何物理有效性、气动性能或燃油结论。

## 8. 政策、身份与不变量（独立字节核验）

- A1 冻结字节未变：evaluator f74a4752… / freeze_api 31d78182… / openvsp_model c40b11df… / design_space 8f9b893c… / config 8b29d1e3… / bundle_manifest 995bb12f…。
- 包/执行字节：plan ba6eaa49… / 52,774 B；approval 4e67eac5… / 84,140 B；identity 7e339188…；executor ed0f2324… / 99,591 B；prestart gate a87b0288…；执行时 launcher 23106df2… / 29,361 B（D-11 后）；pre-D11 launcher 476481e6… / 29,361 B 字节保留。
- R1–R9 approval 9/9 字节未变（r1 9e5c29b0… 至 r9 b502b484…）；R10 run dir 全量 2,228 文件与 A2 sums 清单 2,228/2,228 逐字节匹配、无缺失/多余；git 状态 clean（HEAD fbe92ef1），停止后唯一新增为 A2 说明记录（19:16:35Z，合法披露）。
- 无 push、无改写旧证据；A5 未写入 run dir、未改 approval/包/executor/A1/plan；A5 physical=0。

## 9. 披露项

| ID | 级别 | 披露 |
|---|---|---|
| D-01 (D-11/L-13) | 流程 | post-GO 后 launcher 预检条件数 52→57 单行修复（476481e6… → 23106df2…，同 29,361 B；原字节保留；已由 L-13 追认、A5 复核并同意继续）。C gate 6f14981 锚定旧 launcher；本审计同时记录新旧锚点，traceability 保留；执行期间无其他执行层字节变更。 |
| D-02 | 记录 | batch_summary.arms.DE.valid_designs=11 vs evaluations.jsonl DE valid=12：stop-path 先 append 评估后返回停批，未自增 valid_designs；评估级以 evaluations.jsonl 为权威；不影响停批规则（用累计 invalid/main evals）。 |
| D-03 | 记录 | INVALID 行 failed_family/per_family 字段不完整；族/角色只能由 ledger case_id 后缀复算（A5 复算与 A2 分解一致）。计数不变，建议后续批次补字段。 |
| D-04 | 记录 | preflight_result case-level polar_sha256=null；A5 独立重算 PRE-01/02 polar 文件 SHA 与 approval expected 逐字节相等，PASS_BYTE 结论成立；引用时同时引 approval expected SHA。 |
| D-05 | **重要** | 448/3,148 为 CHARGED_PROJECTED（授权口径，含 R10 计划预留 386/2,702），不是实际物理消耗；实际累计 153/1,083（headroom 298/2,074）。A2 stop note 与 L-14 的“含实际消耗”措辞不精确（L-15 已澄清）；本审计与回执采用双口径。 |
| D-06 | 记录 | final_run_manifest physical_call_count=0 指 manifest builder 自身未 solver；run 物理计数以 ledger/batch_summary/stop_report=91 为准。 |
| D-07 | 记录 | executor_run.log 为两次启动合流：首行 REFUSED（18:56:53，零物理），其余为 18:58:01 正式启动；物理只取 canonical ledger event==start=91。 |
| D-08 | 记录 | run dir 内 A2_R10_STOP_NOTE.md 为停止后 19:16:35Z 追加的披露说明（v1，6ab120fa…/7,492 B）；v2 说明在 A2 docs/evidence（fc0e81ef…/12,243 B）；均非执行产物，不改变记账。 |
| D-09 | 记录 | 48 次评估/45 distinct designs：3 个预冻结设计在两臂各评一次（见 §6.1），已按冻结 per-design 定义处理，不做跨臂/跨族合并。 |
| D-10 | 流程 | C-P2AV2R10-02（6f14981）由 A5 在 D-11 前发出，锚 old launcher；L-13 已裁定无需重签；本审计保留旧锚并更新执行锚点。 |
| D-11 | 记录 | A3 统计（commit 699ce2a）为外部独立交付，A5 已核其 3 文件字节/commit 并交叉核对评估级计数与端点可用性；A5 未运行 A3 工具；A3 工作树其他未提交文件不在 R10 证据范围。 |
| D-12 | 记录 | stop_report.internal_solver_cases=null（A1 ledger 仅审计 physical）；internal 按 7×starts 政策推导并由 batch_summary 记录为 637；不接受 ledger internal 0 读数作为实际 internal。 |
| D-13 | 治理 | L-14/L-15 关闭 R 线：无 R11、无新执行授权、approval 不复用；本审计不构成执行授权。 |

## 10. 证据索引（A5 实算）

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
| executor_prestart.json | 2808306b342917e6d66c87127fd166545aa0f9b285aa936708b8a51720941806 | 12,569 |
| runtime/prefrozen_reuse_gate.json | ccf33400e46d4eeb602e2e15d8322407e5c5bbdbc95f6c67eca710049272ee9c | 10,236 |
| runtime/family_pair_manifest.append_only.jsonl | 36bbc3851e7296c7400ef15a61279b0a10736d0fec207fbcf7ae40d4ee6db0b6 | 211,393 |
| approval.json | 4e67eac52833d8dfab8b8027a0838b68de15f26d9a072edb0515ece22414068c | 84,140 |
| plan.json | ba6eaa49e181b2cacc048362dd00e57458ceba73165b68f1776ae4f3af43b4d4 | 52,774 |
| post_approval_dry_run.json | e9f3471dcd4d6b89e3cf0daf7e6d8a6236741225f3867e4b4cedd7fee2c3cec1 | 19,427 |
| lead_go_r10_20261111T1856Z.json | 260e284a5c9939b9be2ee08e9a2e986d43345818e682ce34ecff91926a91b83a | 9,962 |
| L-14 md | e13435d3f16eb5ac0d33c19681f99dcf595e56a4ab521382fdfd8e2e350ea395 | 4,966 |
| L-15 md | 1c76a34d95db8c29e92e53bcde6d023181f42b4b9a0010434be06fa83e3f7976 | 2,819 |
| A2 stop note v2 | fc0e81ef273b4c272359ba72002ff229199002b649a139c9b8fd6321a15f671f | 12,243 |
| A2 launcher diff | b198c8a964b961bfb1959efe7c8d29c27ca81e54a78f6d598b724168710c64e3 | 1,000 |
| A2 sums list | 64bc78863da1a96939aaa479a17e89dcb1b0e4366c5c2f01b224716f175cc50c | 289,537 |

- run dir 全量：2,228 文件 / 207,718,755 B / inventory_digest 105f3bc9…；与 A2 sums 清单逐项匹配 2,228/2,228，无缺失/多余。
- A2 证据 commit：f299ce22f0ea7cc0b082e795a34a35f980a4beed（run dir 全量）、fbe92ef1c75f8e85a59e3455cbeaf577b450006f（stop note v2 + 分解 + pre-D11 launcher）。
- 治理：L-14 e13435d3…/4,966 B、L-15 1c76a34d…/2,819 B、GO 260e284a…/9,962 B、approval 4e67eac5…、dry-run e9f3471d…、C gate 6f14981；A5 G gate 48b91bf；A3 stats commit 699ce2a。

## 11. A5 结论与限制

1. R10 停止合法、证据完整、账本闭合、无执行层违规；停止原因属预注册科学规则。
2. 六臂 pilot 未完成；E1–E6 端点 NOT_COMPUTABLE；仅 BO/DE 单 seed 描述性事实可用于报告。
3. R1–R10 全部排除于端点与优化结论；fuel=null、物理 NOT_VALIDATED；无 winner/显著性/跨族比较。
4. 累计记账按双口径披露：授权口径 448/3,148（余 3/9）、物理实际 153/1,083（余 298/2,074）。
5. 本审计与随附 A5 签署中文回执供 Lead 发布 Issue #9；两者均**不构成**任何新的执行授权。

## 12. A5 签署块（审计）

- 审计裁决：**A5-P2AV2R10-POSTRUN-AUDIT-PASS__R10-SCIENTIFIC-AUTO-STOP-VALID__SIX-ARM-PILOT-NOT-COMPLETED__NO-OPTIMIZATION-GAIN__EXTERNAL-PHYSICS-NOT-VALIDATED__R1-R10-EXCLUDED__NO-R11**
- 签发日期：2026-11-11（UTC）
- A5 physical_call_count：**0**；solver_started：**false**
- 检查：85/85 PASS，0 FAIL；审计 JSON 与 MD 同批提交。
- 关联：A5 G-P2AV2R10-PRE（48b91bf）、C-P2AV2R10-02（6f14981）、FAIL-09（859008d）、本审计、A5 最终回执。
