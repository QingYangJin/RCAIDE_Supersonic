# D-12D-005 BATCH2 执行报告（VSPAERO 7.2.2 thin-LF，A 类 8 次启动）

生成时间：2026-11-04T13:24:24Z；状态：BATCH2_COMPLETED；输出标签：VSPAERO_INTERNAL_ONLY / physical_validation=NOT_VALIDATED。

## 1. 授权与范围

- 授权文件：C:\Users\pc\AppData\Local\RCAIDE_Supersonic_agent_state\d12d005\lead\D12D005_BATCH2_AUTHORIZATION_20261104T130635Z.json
- 授权 sha256：fd02dd898c816ad702a49e408ca4f31ea193a806275b9ffe95aa9d28e8507ecc（与任务卡一致 = True）
- authorization_id：D12D005-BATCH2-20261104T130635Z；issued_utc：2026-11-04T13:06:35Z；授权 8 starts、0 retries、不允许 case substitution。
- A5 冻结计划 sha256：bc437267705d4df38cd214c1cb3c22d57245aaf5655f13d9f0a1e5e62c9fafd0；verdict：task-131 APPROVE_BATCH2_8（0 blocker / 0 major / 4 minor non-blocking）。
- 目标仓库：D:/RCAIDE-d12d005 @ HEAD c1168ec656160a3e35e5e157050e98ac1fde8cdf（branch research/d12d005-aero-fallback）；exe：D:\OpenVSP-3.55.0\OpenVSP-3.55.0-win64\vspaero.exe（sha256 db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad）。
- 执行方式：串行、-omp 4、单案上限 900 s、RSS 上限 16 GB；案序 S6_STD_M2p02_aoa1 → B2-01 → … → B2-07。
- A 类预算：批前 6/20 → 批后 14/20，剩余 6 关闭且未授权释放；B/C/D/E/P4 类 0 启动。

## 2. 执行摘要

8/8 次启动全部完成，rc=0，无超时、无重试、无停止规则触发；全部结果分类为 SOLVED_VALID_WITH_DERIVED_WARNINGS（唯一警告是派生效率列 Ew=inf，见 §7）。
S6 诊断带（CLtot∈[0.03,0.045]）PASS：CLtot=0.037164。总计 wall=9.846 s（最大单案 1.762 s），峰值 RSS 最大 0.294 GB。

## 3. 合同与 PC-09

- 每案启动前完成：auth/plan sha 校验、HEAD 校验、exe sha 校验、无其他 vspaero 进程、a0v2 evidence 的 stop_before_run==1 与 solver_processes_started==0、bundle 7 文件与 vkey 第 2 行本地路径、check-case-dir、17/17 contract readback、CSF=0 control surfaces。全部 8 案 prestart_checks.all_pass=true。
- PC-09：external thin .vspgeom 复制为 case-local 名（12D 案 wing355_baseline.vspgeom；S6 案 S6_STD_M2p02_aoa1_model.vspgeom），vkey 第 2 行改写为本地绝对路径；每案记录 external/local basename+sha256+bytes，且 external sha == evidence 记录 sha == local sha。
- 12D 合同：Sref=358.25、Cref=18.489893、Bref=25.604638、X_cg=16.821978259514246、Mach=2.02、AoA=2、Re=89397005.8767656、Vinf=596.0373972278921、Rho=0.1153178340089936、NumWakeNodes=8、WakeIters=5、Symmetry=0。
- S6 合同：Sref=4.0、Cref=1.0、Bref=4.0、X_cg=0.25、Mach=2.02、AoA=1、Re=4834912.016269014、Vinf=596.0373971680001、Rho=0.1153178340089936、NumWakeNodes=8、WakeIters=5、Symmetry=0。

## 4. 逐案结果（内部求解器系数，非物理验证）

| 顺序 | case | 类型 | 事件 | 结果 | wall/s | rc | CLtot | CDi | CDtot | E | L/D |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | S6_STD_M2p02_aoa1 | std | NA-D12D005C-001 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.762 | 0 | 0.037164223 | 0.000652722 | 0.011813973 | 0.168388 | 3.145785 |
| 2 | B2-01 | d12 | NA-D12D005C-002 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.259 | 0 | 0.068720124 | 0.002408677 | 0.009720833 | 0.341027 | 7.069366 |
| 3 | B2-02 | d12 | NA-D12D005C-003 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 0.521 | 0 | 0.070394960 | 0.002467158 | 0.009775138 | 0.349370 | 7.201429 |
| 4 | B2-03 | d12 | NA-D12D005C-004 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 1.759 | 0 | 0.068491960 | 0.002400696 | 0.009704726 | 0.339892 | 7.057588 |
| 5 | B2-04 | d12 | NA-D12D005C-005 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 1.511 | 0 | 0.071941630 | 0.002521957 | 0.010164783 | 0.356962 | 7.077537 |
| 6 | B2-05 | d12 | NA-D12D005C-006 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 1.511 | 0 | 0.067018850 | 0.002349255 | 0.009652284 | 0.332555 | 6.943315 |
| 7 | B2-06 | d12 | NA-D12D005C-007 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 1.761 | 0 | 0.068664188 | 0.002421414 | 0.009725748 | 0.338681 | 7.060041 |
| 8 | B2-07 | d12 | NA-D12D005C-008 | SOLVED_VALID_WITH_DERIVED_WARNINGS | 1.762 | 0 | 0.068491877 | 0.002399809 | 0.009703839 | 0.340017 | 7.058225 |

说明：8 案每案 polar 仅 1 行（S6 AoA=1，12D 案 AoA=2），history 均完成 5 次尾迹迭代（files: cases/<case>/bundle/），verify-polar 均为 PASS_WITH_WARNINGS、verify-history 均 PASS。

## 5. 门禁与停止规则

- S6 诊断带：PASS（0.037164 ∈ [0.03, 0.045]）。
- B2 定性门（CDi>0、CDtot≥CDi、有限、|CL|<1、|CDtot|<10）：8/8 全 PASS，gate_failures 均为空。
- 停止规则：未触发（state.stopped=false，stop_reason=null，stop_event_id=null）。
- 预算与并发门：8/8 starts、0 retries、串行、-omp 4、单案最大 wall=1.762 s < 900 s、峰值 RSS 最大 0.294 GB < 16 GB。

## 6. 扰动、重复性与密度 delta（相对 B2-03 基线，内部一致）

| 对比 | ΔCLtot | ΔCDi | ΔCDtot | ΔCLtot% | ΔCDi% | ΔCDtot% |
| --- | --- | --- | --- | --- | --- | --- |
| B2-04 vs B2-03 | +0.003449670 | +0.000121261 | +0.000460057 | +5.0366% | +5.0511% | +4.7405% |
| B2-05 vs B2-03 | -0.001473110 | -0.000051441 | -0.000052442 | -2.1508% | -2.1427% | -0.5404% |
| B2-06 vs B2-03 | +0.000172228 | +0.000020718 | +0.000021022 | +0.2515% | +0.8630% | +0.2166% |
| B2-07（重复 B2-03） | -0.000000083383 | -0.000000887105 | -0.000000886799 | -0.0001217% | -0.0369520% | -0.0091378% |

重复性：B2-07 与 B2-03 同几何同合同，ΔCLtot=-8.338e-08、ΔCDi=-8.871e-07、ΔCDtot=-8.868e-07（相对 -1.22e-04%），说明同一二进制/同输入下 run-to-run 差异在 1e-7 量级，仅说明内部可重复性，不代表物理精度。

密度三件套（同 12D 几何，仅 SectTess_U 不同；内部敏感性，非物理验证）：

| 对比（基准 → 目标） | 目标 CLtot | 目标 CDi | 目标 CDtot | ΔCLtot% | ΔCDi% | ΔCDtot% |
| --- | --- | --- | --- | --- | --- | --- |
| B2-01（Tess 3/3） → B2-02（Tess 6/6） | 0.070394960 | 0.002467158 | 0.009775138 | +2.4372% | +2.4279% | +0.5586% |
| B2-02（Tess 6/6） → B2-03（Tess 12/12） | 0.068491960 | 0.002400696 | 0.009704726 | -2.7033% | -2.6939% | -0.7203% |
| B2-01（Tess 3/3） → B2-03（Tess 12/12） | 0.068491960 | 0.002400696 | 0.009704726 | -0.3320% | -0.3313% | -0.1657% |

S6 与 batch1 S3 的跨 AoA 参考（AoA=1 vs 2，同为标准矩形翼；仅内部线性 sanity check，不是物理对比）：{"reference": "RUN/evidence/v1/per_case_conclusions.json (batch1 S3_STD_M2p02_base, AoA 2, Tess 12/12)", "s6": {"AoA": 1.0, "CLtot": 0.037164223289, "CDi": 0.000652721593, "CDtot": 0.011813972653}, "s3": {"AoA": 2.0, "CLtot": 0.074251031783, "CDi": 0.002606540227, "CDtot": 0.013789407924}, "cltot_ratio_s6_over_s3": 0.5005213045067592, "cltot_ratio_over_linear_expectation_0p5": 1.0010426090135185, "note": "same standard rectangular wing (S3_STD_M2p02_base vs S6_STD_M2p02_aoa1), AoA 1 vs 2; CLtot ratio ~0.5 is a near-linear internal consistency check only, NOT physical validation"}

## 7. 派生列 Ew 警告

8 案 polar 均出现 Ew=inf（第 47 列），属于派生效率量的除零伪影：CLwtot≈CLo≈−2.5e-4 近零、CDwtot 非零有限，Ew 定义中的 wake 升力分母导致溢出。主系数（CLo/CLi/CLtot/CDo/CDi/CDtot/CMytot/CMztot）在 8 案中全部有限；按授权，派生列非有限仅记 WARNING，不触发停止规则（与 batch1 S3 的 fail-closed 判定不同，本轮采用授权显式允许的 allow-nonfinite-derived 策略）。

## 8. 标签与 Gate3 披露

- 所有结果标签：VSPAERO_INTERNAL_ONLY；physical_validation=NOT_VALIDATED。
- CDtot 是内部求解器输出，不是经物理验证的真实阻力；不得据此签核 LF-M2.02 门禁、不得注入 body correction、不得作为 validated fuel label 依据。
- Gate3（thin-surface VSPAERO 在 Mach 2.02 的物理有效性）在本方法下不可达：本批只证明内部一致性与可重复性，以及 VSPAERO 7.2.2 可稳定运行小区间。

## 9. 预算与账本

| 项 | 值 |
| --- | --- |
| 本批授权 starts | 8 |
| 已用 starts | 8 |
| retries | 0 |
| billable events | 8 |
| A 类批前 / 批后 / cap | 6 / 14 / 20 |
| A 类剩余（关闭，未授权） | 6 |
| ledger 行数 | 16（8 PENDING + 8 COMPLETED） |

## 10. 证据与复现

- run 目录：D:\RCAIDE-d12d005\research\concorde_metaopt\optimization_runs\d12d005-20261104T0430Z
- evidence/batch2/：run_start.json、batch_state.json、budget_ledger.json、ledger.jsonl、batch2_results.json、batch2_report.md、final_checks.json、process_before.csv、process_after_*.csv、cases/<case>/{bundle,results,pc09_bundle_prep.json}。
- EXT 镜像：C:\Users\pc\AppData\Local\RCAIDE_Supersonic_agent_state\d12d005\a2\batch2（batch2_report.md、results_summary.json、commands.log、SHA256SUMS.txt）。
- 每案 bundle 保留：.vsp3/.vkey/.csf/.vspaero/.vspgeom（本地复制）、expected_v2.json、geom_result_thin.csv、solver_stdout.log、solver_stderr.log、.polar、.history、.lod、.adb。
- final_checks.json：36 项检查，全部通过（True）。

## 11. 局限

- VSPAERO thin-LF 为内部求解器，此结果不能用于物理验收、不能替代 SU2/风洞；Mach 2.02 下该方法本身未通过物理验证。
- polar 仅单 AoA 点（S6 AoA=1，12D AoA=2），无升阻极曲线斜率/配平信息。
- 12D 案只含主翼（lifting-surfaces-only），不含机身/垂尾/翼身干扰；S6 为矩形标准翼。
- Ew 派生列非有限，说明该效率量不可用；E/L/D 仍为内部量。
- 峰值 RSS 由 0.25 s 轮询采样，可能低估瞬时峰值（最大 0.294 GB，远低于 16 GB 上限）。
- 本批未授权任何重试；剩余 6 次 A 类配额关闭，不得重分配或结转。

