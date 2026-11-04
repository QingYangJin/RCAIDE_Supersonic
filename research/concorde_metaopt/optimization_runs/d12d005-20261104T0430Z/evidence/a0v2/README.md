# D-12D-005 A0 v2：零求解器 VSPAERO 7 setups 生成（8 个修订 case）

本目录记录 A0 v2 的**零求解器** setup 生成证据。生成过程只调用 OpenVSP Python API 完成几何与
VSPAEROSweep 输入面写盘（StopBeforeRun=1），**未启动任何 VSPAERO/SU2/RCAIDE solver 进程**。

## 1. 目的与范围

- 修复 Gate2 registration：旧注册依赖亚声速 Helmbold 公式，在 Mach 2.02 下 band 错误（CLtot 0.0743
  远低于 [0.10844, 0.16266]，S3 shortfall 31.528%）。v2 以 A5 复核的 Ackeret 线化超声速公式
  重新注册 Gate2，并对 S3/S4 已观测值作 **post-hoc** 披露（不是独立确认）。
- 新增独立超声速确认 case：S6_STD_M2p02_aoa1（标准矩形翼，Mach 2.02，AoA=1deg），其预期 CL 带
  来自同一 Mach-aware 理论，且在该 case 运行前注册，因此可作为修复的独立确认。
- 新增 12D 主翼密度/扰动 setups（B2-01..B2-07），用于后续 A2/A5 的 thin 表面几何敏感性评估。
- 12D 主翼几何与 v1 归档 wing355_baseline.vsp3 做 parity（读回几何指标）+ thin vspgeom 字节 sha
  对照；B2-07 为 B2-03 的重复性检查。

## 2. Case 计划（8 个）

| case | kind | SectTess_U | 设计 | 说明 |
| --- | --- | --- | --- | --- |
| B2-01 | d12 | 3.0 | 12D baseline | 12D 主翼 thin 基线：每个 XSec SectTess_U=3（低密度） |
| B2-02 | d12 | 6.0 | 12D baseline | 12D 主翼 thin 基线：每个 XSec SectTess_U=6（与 v1 S5 同密度） |
| B2-03 | d12 | 12.0 | 12D baseline | 12D 主翼 thin 基线：每个 XSec SectTess_U=12（高密度） |
| B2-04 | d12 | 12.0 | {'wing_area': 376.1625} | 单因素扰动 W01 wing_area=376.1625（baseline 358.25 的 +5%），SectTess_U=12 |
| B2-05 | d12 | 12.0 | {'sweep_1': 69.0} | 单因素扰动 W03 sweep_1=69.0（baseline 67），SectTess_U=12 |
| B2-06 | d12 | 12.0 | {'tip_twist': 2.0} | 单因素扰动 W10 tip_twist=2.0（baseline 0），SectTess_U=12 |
| B2-07 | d12 | 12.0 | 12D baseline | B2-03 重建（repeatability check；SectTess_U=12） |
| S6_STD_M2p02_aoa1 | std | 20.0 | 12D baseline | 独立超声速确认 case：标准矩形翼 Mach 2.02 AoA=1deg（与 S3 同几何/合同，仅 AoA 减半） |

12D 合同（所有 d12 case）：Sref 358.25、Cref 18.489893、Bref 25.604638、Xcg 16.821978259514246、
Mach 2.02、AoA 2deg、ReCref 89397005.8767656、Vinf 596.0373972278921、Symmetry 0、NumWakeNodes 8、
WakeIters 5、WakeRelax 1.0、FarDist -1.0。标准翼合同：Sref 4、Cref 1、Bref 4、Xcg 0.25；S6 仅 AoA=1deg。

## 3. 结论（本阶段）

- status：A0V2_SETUP_READY_NO_SOLVER
- case 数：8；17/17 readback 通过：8；无 solver 产物：全部
- 12D 基线 parity（读回几何 vs v1 归档模型）：PASS；thin vspgeom 字节 parity：S5_D12_M2p02_base=PASS
- 标准翼 thin vspgeom 与 v1 S3 归档字节对照：PASS
- B2-07 重复性：PASS
- 负控制：全部按预期被拒绝
- solver 进程启动数：0；StopBeforeRun 强制为 1

## 4. 非结论 / 边界

- 本阶段**不产生**任何气动力/极线数值结论：没有 solver 运行，CDi/CDtot 数值带已废止，只保留定性门
  （CDi>0、CDtot>=CDi、全部有限）。
- Gate2 修复是 **post-hoc** 注册：S3/S4 的 CLtot 已在 v1 观测到，故该修复只作诊断；独立确认只有 S6。
- 12D 主翼 case 无独立解析参考，仅要求有限、符号/量级合理、与 baseline/扰动一致。
- vsp3 容器字节跨会话不可复现（同一几何两次写出 sha 不同、大小相同）；parity 以读回几何指标与 thin
  vspgeom 字节 sha 为准，不以 vsp3 sha 为准。
- thin .vspgeom 移出 git（external_path + sha256 + bytes + outside_git=true），仓库内只保留元数据。

## 5. 产物

- gate2_repair_registration.json：mach-aware Gate2 修复注册（schema、公式、推导、观测值、披露）
- setup_generation_v2.json：生成证据主文件（cases/parity/repeatability/negative_controls/summary）
- setup_gen/<case>/：模型、contract setup、expected_v2.json、readback 记录
- negative_controls/B2-03/：三种被破坏的 setup（wrong Sref / legacy 无等号 / NumWakeNodes 错配）

## 6. 复现

```
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/a0_generate_setups_v2.py
D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m unittest scripts/test_a0_generate_setups_v2.py
```
