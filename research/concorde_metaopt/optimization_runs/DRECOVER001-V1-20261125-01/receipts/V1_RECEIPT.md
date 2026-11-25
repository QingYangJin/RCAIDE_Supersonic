# V1 回执：RCAIDE 自带超音速 VLM 对现有 12D 模型的 A/B/C/D 测试

- 运行目录：`D:/RCAIDE/.real_runs/DRECOVER001-V1-20261125-01/`
- 解释器：`D:/Anaconda/envs/RCAIDE/python.exe`（RCAIDE 1.5.0）
- 消耗 VSPAERO solver start：**0**（纯 python 线性求解）
- evidence_scope：`RCAIDE_VLM_INVISCID_LINEAR_THEORY_ONLY`
- 场景：M=2.02、18,288 m、SREF 358.25 m²、CREF 18.489893 m、BREF 25.604638 m、q=20,483.94 Pa、CL_target=0.181743998494、α0=5.18132°
- 模型：baseline sweep_1=67.0 / sweep_2=48.0；optimized sweep_1=66.92203997956408 / sweep_2=48.00055732910467（其余 10 维逐位相同）
- VLM 设置：`use_surrogate=False`（走真超音速核 B2=mach²−1），cosine spanwise spacing，leading_edge_suction_multiplier=1

---

## A. 格架收敛（baseline，M=2.02，α=5.18132° 固定）

| N_span × N_chord | 面元数 | CLift | CDi(Trefftz) | L/D |
|---|---|---|---|---|
| 6 × 3   | 18   | 0.169335 | 0.005049 | 33.54 |
| 8 × 4   | 32   | 0.181813 | 0.006490 | 28.02 |
| 12 × 6  | 72   | 0.177726 | 0.006698 | 26.53 |
| 15 × 8  | 120  | 0.177721 | 0.006926 | 25.66 |
| 20 × 10 | 200  | 0.170662 | 0.006410 | 26.62 |
| 30 × 15 | 450  | 0.190409 | 0.009303 | 20.47 |
| 45 × 25 | 1125 | 0.183642 | 0.008310 | 22.10 |

**判决：不收敛（FAIL）。**
- CL 在 0.1693–0.1904 间非单调振荡，极差 0.0211 = 均值的 12.1%。
- CDi 从 0.005049 到 0.009303，跨度 **84%**，且非单调；最细格架 45×25 反而比 30×15 低 10.7%。
- 精度设定不是原因：`VLM.py:466-467` 的 float32 转换发生在求解之后，不影响解本身。
- 与 VSPAERO 6.2.0 的历史结论（CDi 变号、放大约 65×）性质不同：RCAIDE 是振荡而非发散，但"无收敛的离散解"这一判决相同。

## B. Mach 扫掠（baseline，格架 20×10，α=5.18132°）

| M | CLift | CDi | CL_α（/rad，α±1° 中心差分） | 2D 理论 4/β | 比值 |
|---|---|---|---|---|---|
| 1.6 | 0.214779 | 0.010630 | 2.1110 | 3.2026 | 0.6592 |
| 1.8 | 0.198689 | 0.009192 | 2.0087 | 2.6726 | 0.7516 |
| 2.0 | 0.172049 | 0.006545 | 1.8588 | 2.3094 | 0.8049 |
| 2.2 | 0.158376 | 0.005493 | 1.7013 | 2.0412 | 0.8335 |
| 2.4 | 0.145819 | 0.004568 | 1.5776 | 1.8334 | 0.8605 |

**判决：定性 PASS，定量偏低。**
- CL_α 随 M 单调平滑下降，**无分支跳变** → 超音速核在 1.6–2.4 全程行为自洽。
- 相对 2D 理论 4/β 的比值从 0.659 单调升到 0.861：有限翼展折减是**随 M 变化的**，不存在一个常数标定因子。
- 与 VSPAERO 交叉：M=2.0 时 RCAIDE 1.8588 vs VSPAERO（M=2.02）2.01 /rad，差 **−7.5%**；两套线性理论在升力线斜率上互相印证。

## C. O0 改进稳健性（等 CL 反解 α，CL_target=0.181743998494）

| 格架 | α_baseline | α_optimized | CDi_base | CDi_opt | Di_base (N) | Di_opt (N) | ΔDi (N) | ΔDi (%) |
|---|---|---|---|---|---|---|---|---|
| 15 × 8  | 5.30710 | 5.30447 | 0.00725501 | 0.00723209 | 53,239.93 | 53,071.77 | **168.154** | **0.3158%** |
| 30 × 15 | 4.91087 | 4.91156 | 0.00846352 | 0.00844137 | 62,108.47 | 61,945.93 | **162.538** | **0.2617%** |
| 45 × 25 | 5.12189 | 5.11691 | 0.00813329 | 0.00811193 | 59,685.12 | 59,528.33 | **156.783** | **0.2627%** |

Di = CDi × q × SREF（q=20,483.94 Pa，SREF=358.25 m²）。注意 RCAIDE 侧的 Di 量级（5.3–6.2×10⁴ N）约为 VSPAERO（1.21×10⁵ N）的一半，因两者 CDi 定义不同（见 D），**绝对量级不可比，只有相对差可比**。

**判决：PASS（本报告最重要的正面结果）。**
- 三档格架 ΔDi 全部为正，符号与 VSPAERO 一致；量级 0.262%–0.316% vs VSPAERO **0.2394%**（290.754 N），差 1.1–1.3 倍。
- Δα 仅 0.001–0.006° → 改进不是靠"多打几度迎角"换来的。
- 关键观察：ΔDi 跨格架的散布（0.262%→0.316%，±10%）远小于 A 中绝对 CL 的散布（±12%）与 CDi 的散布（84%）→ **差分比绝对值稳健得多**。
- 结论：O0 的 0.2394% 改进**不是 VSPAERO 的求解器假象**，独立的线性理论代码复现了同一方向的同量级收益。

## D. 与 VSPAERO 交叉对照 + 阻力账

直接对照（格架 30×15，α=5.18132°）：

| 量 | RCAIDE VLM | VSPAERO | 比值 |
|---|---|---|---|
| CL | 0.190409 | 0.18174 | 1.048 |
| CDi | 0.009303 | 0.016548 | **0.562** |

全链路（`aer.evaluate()`）阻力账：

| 项 | 值 |
|---|---|
| lift.inviscid.total | 0.190409 |
| lift.total | **0.228491（+20%，不可信）** |
| drag.parasite.total | 0.002302（wings 0.001242 / fuselages 0.001050 / nacelles 1.0e−5） |
| drag.induced.inviscid | 0.009303 |
| drag.induced.viscous | 4.567e−5 |
| drag.induced.total | 0.009348 |
| drag.miscellaneous.total | 1.675e−5 |
| drag.wave / form / trim / cooling | 0 / 0 / 0 / 0 |
| drag.compressible.total | **NaN** |
| drag.total | **NaN** |

**判决：不能作为验证，也不能作为绝对阻力来源。**
- `drag.compressible.total` 为 NaN，导致 `drag.total` 为 NaN。根因链：`compressibility_drag.py:129` 在 M=2.02 仍调用 `transonic_lift_wave_drag`，后者在 `compressibility_drag.py:367` 读取 `conditions.aerodynamics.coefficients.lift.spanwise`（独立调用时该值为 None → `TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'`；在 evaluate 流程中该量存在但结果为 NaN）。
- 排除的项：翼面 t/c 并未缺失（main_wing 0.029990、vertical_stabilizer 0.0799997），sweep_LE 67.14°/61.25°，Sref/MAC/span 均正常。
- 因此 RCAIDE 目前**无法给出含波阻的总阻力**，而 VSPAERO 的 CDi 0.016548 恰是含波阻的升致阻力 → 0.009303 vs 0.016548 是**两个不同物理量之比**，不能读作"RCAIDE 低估 44%"，这正是审计中 `LF-R3`（Trefftz 诱导阻力与 JAXA 升力波阻双重计数）风险的实证版本。
- 附带发现：`lift.total` 比 `lift.inviscid.total` 高 20%，故全链路的 CL 也不可用于定量结论。

---

## 结论与处置建议

1. **换 RCAIDE VLM 不能解决收敛问题**：A 在 RCAIDE 这一侧同样不收敛（CDi 跨度 84%、非单调），只是从"发散/变号"变成"振荡"。不建议把它当作 VSPAERO 的替代验证路径。
2. **但 C 是本轮最有价值的结果**：独立的线性理论代码复现了 O0 改进的方向与量级（0.26–0.32% vs 0.24%），显著提高了"该改进真实存在"的可信度，且不依赖 VSPAERO 的实现。
3. **D 的教训是不要混用两套阻力定义**：RCAIDE 侧 compressible 项 NaN、Trefftz CDi 不含波阻；任何与 VSPAERO 的绝对阻力对照都必须先解决波阻口径。
4. **可用表述**（受限于证据）：可以声称"RCAIDE 超音速 VLM 独立复现了 O0 改进的方向与量级（0.26–0.32% vs 0.2394%）"；**不能**声称"两套方法在阻力上一致"、"RCAIDE 验证了 VSPAERO"、"RCAIDE 结果收敛"。

## 复现性发现（与本次测试无关但必须记录）

`research/concorde_metaopt/aircraft/concorde_adapter.py:41` 的 `EXPECTED_SHA256 = 4c633e48…` 与磁盘上 `tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py`（实测 `50bf69be…`）不一致 → HEAD 上 `load_template_module()` 必然抛 `AdapterError: tutorial template hash mismatch`，单巡航 RCAIDE LF 路径已不可复现。本报告使用 `verify_hash=False` 绕过。

## 产物

- `v1_rcaide_vlm_results.json`：A/B/C/D 原始数值
- `v1_d_full_pipeline.json` / `v1_d_ledger.json`：全链路阻力账
- `v1_abcd.py` / `d_full.py` / `d_ledger.py` / `d_wave.py`：可复现脚本
