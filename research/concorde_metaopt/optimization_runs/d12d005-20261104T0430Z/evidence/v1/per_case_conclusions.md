# D-12D-005 A 类第一批（S0..S5）逐案结论

run_id: d12d005-20261104T0430Z；状态: BATCH1_STOPPED_ABORT_FINAL_FREEZE；starts 4/6（remaining 2 关闭，不重分配、不重试、不结转）。

| 案 | 状态 | 事件 | 墙钟 s | CLtot | CDtot | CDi | E | 说明 |
|---|---|---|---|---|---|---|---|---|
| S0 | SOLVED_VALID | NA-D12D005-001 | 4.045 | 0.126545398398 | 0.020946562364 | 0.001314258293 | 0.969621451468 | 见下 |
| S1 | SOLVED_VALID | NA-D12D005-002 | 6.012 | 0.134634955743 | 0.021167612993 | 0.001522504678 | 0.947430266105 | 见下 |
| S2 | SOLVED_VALID | NA-D12D005-003 | 0.507 | 0.126555050502 | 0.020946858130 | 0.001314544617 | 0.969558142981 | 见下 |
| S3 | FAILED_INVALID_POLAR | NA-D12D005-004 | 1.008 | 0.074251031783 | 0.013789407924 | 0.002606540227 | 0.168318084604 | 见下 |
| S4 | NOT_RUN_AFTER_ABORT | - | - | None | None | None | None | 见下 |
| S5 | NOT_RUN_AFTER_ABORT | - | - | None | None | None | None | 仅机翼；见下 |

## S0 S0_STD_M0p1_base

标准矩形翼 M0.10 基线 SOLVED_VALID：rc=0，polar 单行 AoA=2，CLtot=0.126545, CDtot=0.020947；history 5 次迭代未完全平台（末步 dCLtot=-1.37e-5），但 v2 verify-polar/verify-history 均 PASS。作为 wake 敏感性参照可用。

## S1 S1_STD_M0p1_wn128

仅 NumWakeNodes 8->128 SOLVED_VALID：CLtot +6.4%、CDi +15.8% vs S0，history 5 次迭代达平台（末步 dCLtot=-1.98e-7），peak RSS 1.057 GB。说明 8 节点尾迹不足以收敛，wake 节点数是可测量敏感参数。

相对 S0：CLtot 6.393 %，CDi 15.845 %，CDtot 1.055 %。

## S2 S2_STD_M0p1_wi0

仅 WakeIters 5->0 SOLVED_VALID：仅 1 次迭代（冻结初始尾迹），CLtot/CDi 与 S0 相差 7.6e-6/2.9e-7，墙钟 0.507 s。证明 S0 的收敛主要来自 wake 迭代，且零迭代时结果退化为初值尾迹解。

相对 S0：CLtot 0.008 %，CDi 0.022 %，CDtot 0.001 %。

## S3 S3_STD_M2p02_base

标准矩形翼 M2.02 FAILED_INVALID_POLAR：rc=0、history 有限且残差单调下降（L2 1.11->-2.75），CLtot=0.074251、CDi=0.002607 有限，但 polar 第 47 列 Ew=inf 触发 fail-closed。列诊断判定为派生效率列退化伪影（CDwtot=0.011183 非零、CLwtot=-3.905e-4 近零），非数值发散。Ew=inf 仍使该 polar 不可作为物理证据；VSPAERO 7.2.2 thin 在 M2.02 仍 NOT_VALIDATED。

相对 S0：CLtot -41.325 %，CDi 98.328 %，CDtot -34.169 %。

## S4 S4_STD_M2p02_wn128

NOT_RUN_AFTER_ABORT：S3 触发停止规则后未启动（未计费，starts 未消耗）。

## S5 S5_D12_M2p02_base

NOT_RUN_AFTER_ABORT：S3 触发停止规则后未启动（未计费，starts 未消耗）。

## 合并观察

- S0/S1/S2（M0.10 标准矩形翼 thin VSPGEOM）全部 fail-closed PASS：说明 v2 runner、17 字段回读、VSPGEOM thin 路径与 -omp 4 直接调用链路在本批是可用的。
- S1 vs S0 与 S2 vs S0 均为单因素对照：NumWakeNodes 8->128 改变 CLtot +6.4%、CDi +15.8% 并改善收敛；WakeIters 5->0 只做 1 次迭代、与 S0 差 <1e-5，证明收敛来自 wake 迭代。
- S3（M2.02）数值稳定但 polar 含 Ew=inf 派生列，按 fail-closed 规则判 INVALID 并停止后续 S4/S5；VSPAERO 7.2.2 thin 超声速仍 NOT_VALIDATED。
- 与 D-12D-004 V1 对照：V1 在 M2.02 为数值发散，本批 S3 为派生列退化，两种失败模式独立；V1 在 M0.10 的异常在本批未复现，支持 V1 M0.10 异常归因于 setup/几何模式而非流动物理。
- 文档缺陷 DOC-1/DOC-2（矩阵 acceptance 5 行条款、reference_condition rev2 旧值）已在 stop_decision.json 记录，未越权改矩阵非状态列；建议由矩阵 owner 修正。

