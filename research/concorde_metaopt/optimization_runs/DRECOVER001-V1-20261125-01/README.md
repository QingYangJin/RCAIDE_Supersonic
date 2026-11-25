# DRECOVER001-V1-20261125-01 — RCAIDE 超音速 VLM 作为低保真评估器的 A/B/C/D 审计

状态：**COMPLETED（本地）** · 上游 Issue：[#15](https://github.com/QingYangJin/RCAIDE_Supersonic/issues/15)
物理求解器启动：0 次 VSPAERO。本包回答的问题是"能不能把低保真气动整体换成 RCAIDE 自带超音速 VLM"。

## 四项测试与判决

| 项 | 内容 | 判决 | 关键数字 |
|---|---|---|---|
| A | 格架收敛（M=2.02，α=5.18132° 固定，baseline） | **FAIL** | CL 极差 12.1%（0.169335–0.190409），CDi 跨度 84%（0.005049–0.009303），非单调振荡 |
| B | Mach 扫掠 1.6–2.4（格架 20×10） | **PASS（定性）** | CLα 2.1110→1.5776 单调平滑，为 2D 理论 4/β 的 0.659–0.861 倍，无分支跳变 |
| C | O0 改进稳健性（等 CL 反解 α，三档格架） | **PASS** | ΔDi 168.154 / 162.538 / 156.783 N（0.3158% / 0.2617% / 0.2627%），三档同号，vs VSPAERO 0.2394% |
| D | 与 VSPAERO 逐点交叉对照 | **不能作验证** | RCAIDE CL 0.190409 vs VSPAERO 0.18174（×1.048）；CDi 0.009303 vs 0.016548 —— 二者不是同一物理量 |

## D 项的根因

RCAIDE 全链路阻力账在 M=2.02 时 `drag.compressible.total = NaN`，导致 `drag.total = NaN`。
根因链：`compressibility_drag.py:129` 在 M>1 时仍调用 `transonic_lift_wave_drag`，后者在 `compressibility_drag.py:367` 读 `conditions.aerodynamics.coefficients.lift.spanwise`；独立调用时为 None → `TypeError`；在 evaluate 流程中变为 NaN。
这同时给出审计中 LF-R3 的实证：Trefftz 诱导阻力与 JAXA 升力波阻存在双重计数风险，因此 **0.009303 不能被读作"比 VSPAERO 低估 44%"**。

## 关键副产品（C 项）

即便格架不收敛，**差分量**是稳健的：ΔDi 跨格架散布（±10%）远小于绝对 CL（±12%）与 CDi（84%）的散布。
⇒ O0 在 VSPAERO 上得到的改进（290.754 N，0.2394%）不是 VSPAERO 的假象，RCAIDE VLM 独立给出同向、同量级（0.26–0.32%）的结果。
注意绝对量级不可比：RCAIDE 侧 Di 约 5.3–6.2×10⁴ N，VSPAERO 约 1.21×10⁵ N。

## 目录

```
scripts/   v1_abcd.py（A/B/C/D 主脚本）、d_full.py（全链路阻力账）、d_ledger.py、d_wave.py、
           probe_vlm.py + probe2..6.py（接口与 NaN 根因探针）
data/      v1_rcaide_vlm_results.json（A/B/C 全部原始点）、
           v1_d_full_pipeline.json（D 项全链路分量）、v1_d_ledger.json
receipts/  V1_RECEIPT.md（完整回执）
logs/      d_full.log
```

## 顺带发现的复现性缺陷（未修）

`research/concorde_metaopt/aircraft/concorde_adapter.py:41` 的 `EXPECTED_SHA256 = 4c633e48…` 与磁盘上
`tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py` 的实际哈希 `50bf69be…` 不一致
⇒ HEAD 上 `load_template_module()` 必抛 `AdapterError: tutorial template hash mismatch`。
本包全部结果在调用侧用 `verify_hash=False` 绕过；该缺陷已在 Issue #15 中披露，等待上游决定是否更新哈希。
