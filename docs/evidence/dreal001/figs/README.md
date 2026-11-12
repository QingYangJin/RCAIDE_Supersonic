# A4-P2AV2-R10-FINAL-20261111

**SIX_ARM_PILOT_NOT_COMPLETED / E1–E6 NOT_COMPUTABLE — NO PERFORMANCE DATA**

A4 R10 六臂基础设施/证据状态图与表（描述性；无性能结论）

## 内容

- figures/：6 图，每图 PNG（200 dpi）+ PDF（矢量）：
  - fig1_objective_distribution_trajectory
  - fig2_validity_and_invalid_reasons
  - fig3_endpoint_availability_e1_e6
  - fig4_accounting_two_bases
  - fig5_preflight_byte_identity
  - fig6_r1r10_timeline
- tables/：6 表 CSV（table1–table6，见 figure_notes_zh.md）
- figure_notes_zh.md：逐图/逐表说明、关键数字、禁止解读、来源清单
- data_sources.json：全部来源文件路径 + SHA256 + bytes + 角色
- evidence.json：证据收集与 fail-closed 校验的完整结构化记录
- final_summary.json：包级摘要（判定、计数、输出 SHA256）
- SHA256SUMS.txt：本包全部交付文件校验和

## 判定（截至 2026-11-11T20:14:06Z UTC）

- 六臂 pilot：NOT_COMPLETED（BO COMPLETED 32/23 valid；DE STOPPED_SCIENTIFIC_INVALID_RATIO 16/12 valid；PSO/ABO/ADE/APSO NOT_RUN）。
- 端点：E1–E6 六臂全部 NOT_COMPUTABLE（BO/DE 的 E1/E2/E4 仅有描述性计算，不构成端点结论）。
- 记账双口径：charged_projected 448/3,148（caps 451/3,157，余量 3/9）vs physical_actual 153/1,083（余量 298/2,074）；448/3,148 含计划预留，非实际消耗。
- fuel_burn_kg=null；EXTERNAL_PHYSICS_SUPPORTED=NOT_VALIDATED；R1–R10 永久排除出 E1–E6。
- A4 physical_call_count=0；A5 R10 审计+回执已签发（AUDIT_AND_RECEIPT_DELIVERED）；本包不并入 A5 签署回执。

## 复现

~~~bash
cd D:\RCAIDE\dnext001\wt-real-a4-perf-figs
D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.dreal001.figs_p2av2.r10_final_package
D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.dreal001.figs_p2av2.r10_final_package --verify
~~~
构建器对全部治理/A3/run dir/approval/stop/polar 证据做 SHA256+bytes 断言；任一不符即拒绝生成。

## 边界

- 本包是 A4 本地补充证据集：不并入 A5 签署回执，不作 Issue #9 回执正文图号。
- 不呈现任何性能/增益/收敛/排名/显著性/跨族 CDi 比较；单 seed=42 描述性。
