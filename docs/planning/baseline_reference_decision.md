# P1 基准几何参考模型决策（回应 Issue #1 管理方审阅 6468793958）

- 日期：2026-10-29（Asia/Shanghai）
- 状态：**提案，等待仓库负责人确认**（本文件不是 AI 记忆日记，属 Issue 允许的人工审核技术协议）
- 范围：Issue #1 Phase I 的 P1 几何门禁与 P2 单巡航评价器之间的基准物理参考模型
- 证据：
  - `research/concorde_metaopt/optimization_runs/geometry-check-p1-20261028T1835`（31 case + 7 项 source WARN）
  - `research/concorde_metaopt/optimization_runs/openvsp-check-p1-20261029T1557`（21 项 OpenVSP 导出检查）
  - `research/concorde_metaopt/optimization_runs/openvsp-cases-p1-20261029T1700`（7 case 实体扰动证据）
  - `research/concorde_metaopt/configs/task_fixed_cruise.yaml`（P2 冻结任务）
  - 源码：`tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py`（sha256 4c633e48…）

## 1. 管理方要求

Issue #1 评论 6468793958 第 2 点要求在目标 Mission 冻结前，对七项基准几何偏差做出书面决策，保留原数与依据、说明对阻力/燃油的影响，并由负责人确定物理参考模型。

## 2. 七项偏差原数（run geometry-check-p1-20261028T1835, checks.csv）

| 项目 | 上游 Concorde.py 声明 | P1/P2 计算一致值 | 相对偏差 | 原因 |
| --- | --- | --- | --- | --- |
| 主翼根弦 | 33.8 m | 29.901819 m | −11.53% | 上游声明互相矛盾：面积 358.25、展长 25.6 与分段弦比只能推出 29.902；用 33.8 会得面积约 404.7 m² |
| 主翼湿面积 | 601 m² | 717.575 m² | +19.40% | 上游为经验值；P1 用 RCAIDE 规则 2.003×暴露面积由几何积分得到 |
| 主翼暴露面积 | 326.5 m² | 358.25 m² | +9.72% | P1 未建模机翼-机身遮挡（unexposed span），暴露面积等于参考面积；已知限制 G10 |
| 垂尾展长 | 6.0 m | 5.009331 m | −16.51% | 面积 33.91 + 固定 AR 0.74 ⇒ 展长 5.009；用 6.0 会得面积约 26.6 m² |
| 垂尾根弦 | 14.5 m | 13.157616 m | −9.26% | 与同一段/弦比闭合一致 |
| 机身湿面积 | 442 m² | 488.922 m² | +10.62% | 8 站位截断椭圆锥积分 vs 上游经验值 |
| 机身迎风投影 | 11.9 m² | 7.509665 m² | −36.89% | 上游 11.9 无法由其自身宽高推出：π/4·2.88·3.32 = 7.510 |

## 3. 决策 D-P1-01（提案）

**P2 及其后的低保真评价采用“计算一致几何”（computed-consistent geometry）作为唯一物理参考模型；上游声明值保留为 provenance，不参与计算、不覆盖、不混用。**

采纳的具体参考量（`aircraft/geometry_model.py` + RCAIDE `wing_planform`/`fuselage_planform` 双路一致）：

- 主翼：Sref = 358.25 m²（保持上游声明，作为 CL/CD 归一化基准）、展长 25.604638 m、根弦 29.901819 m、MAC 18.489893 m、湿面积 717.57475 m²、暴露面积 358.25 m²（遮挡未建模）
- 垂尾：面积 33.91 m²（保持上游声明）、展长 5.009331 m、根弦 13.157616 m、MAC 8.124385 m
- 机身：长度 61.66 m、宽 2.88 m、高 3.32 m、nose 12.384 m、tail 18.432 m、cabin 30.844 m、湿面积 488.922 m²、迎风投影 7.509665 m²、等效直径 3.103905 m
- 质量/CG/SM：**PROVISIONAL_NOT_FROZEN**，不进入任何验收约束

理由：

1. 上游七个声明值彼此不自洽（见上表），无法同时满足面积-展长-弦长闭合；混用会导致参考面积、AR、MAC 定义漂移，使 15 维优化目标不可比。
2. RCAIDE 独立重算（R00–R18）复现上述全部数值，OpenVSP 实体导出（21 项检查 + 7 case 扰动）复现面积/展长/长度，说明这些值是几何闭合的唯一解，不是实现错误。
3. 偏差集中在湿面积/迎风面积/遮挡等阻力建账量，以及垂尾展长/根弦；参考面积（目标函数归一化基准）与任务质量契约（固定 TaskSpec）均未受影响。

## 4. 对 P2 目标函数的影响（为什么现在不阻塞）

- VLM 气动路径（RCAIDE Vortex_Lattice_Method）：阻力 = 涡格诱导阻力 + 各剖面翼型极曲线阻力（含压缩性修正）；不使用全机湿面积、迎风投影面积或上游经验尾翼数据。因此 7 项偏差不进入 P2 目标函数的阻力主通道。
- P2 质量契约由 TaskSpec 显式冻结（OEW 78700 / payload 9500 / cargo 1000 / fuel 46800 / start 136000 kg），不读取 P1 的 provisional 质量缩放；因此 CG/SM provisional 不影响 P2 的 fuel_burn_kg。
- 受影响的只是不低于一定量级的垂尾升力/诱导阻力与未来阻力建账；P2 结果按“算法级低保真评价”发布，不作为物理验收。
- 结论：**不阻塞 P2 软件/算法验收；阻塞 P3 及以后的高保真物理结论。**

## 5. 关闭条件（进入 P3/SU2 前必须完成）

1. 负责人二选一并签字：
   - (A) 维持计算一致几何，并在上游来源说明中注明 Concorde.py 声明值不可闭合（本文件默认方案）；或
   - (B) 显式引入遮挡/尾翼面积/迎风面积经验模型，使 601/326.5/6.0/14.5/442/11.9 可复现，再重跑 P1 检查。
2. 冻结 CFD 参考量并写入 TaskSpec 版本：Sref 358.25 m²、cref 18.489893 m、bref 25.604638 m、力矩参考点；SU2 网格与 VSPAERO 必须使用同一组参考量。
3. 阻力建账前给出湿面积/迎风面积来源与敏感性预算（例如湿面积 +19.4% 对 CD0 的贡献范围），区分模型积分值与经验值。
4. 质量/CG/SM 用 RCAIDE 质量模型 + OpenVSP mass props 替代 provisional 缩放；在冻结前不得声明“已验收配平/稳定约束”。
5. P3 报告中逐项引用本文件的决策编号，禁止静默混用两套数值。

## 6. 风险与备选

- 采用方案 (A) 的风险：上游声明若代表真实 Concorde 数据（33.8 m 根弦等），计算一致几何会在湿面积/阻力上偏离真实飞机；但 P2 只做软件验收与算法对比，且偏差已量化记录，可接受。
- 备选 (B) 的成本：需要引入遮挡模型（unexposed span）、尾翼面积-展长映射、机身迎风面积经验修正，并重审 31 case/OpenVSP 检查；预计 P3 前期 1–2 天工作量，可推迟到 SU2 网格冻结前执行。
- 决策未确认期间：所有 P2 结果继续标注 low-fidelity、provisional-geometry、不得作为物理结论。

## 7. 复现

```bash
./run_rcaide.cmd -m research.concorde_metaopt.cli geometry-check \
  --run-id <run_id> --output-root research/concorde_metaopt/optimization_runs
# 查看 checks.csv 中 source_* WARN 与 G10 行
python -c "import csv; [print(r) for r in csv.DictReader(open('research/concorde_metaopt/optimization_runs/geometry-check-p1-20261028T1835/checks.csv')) if r['status']=='warn']"
```
