# D-12D-005 Batch2 中文图表与报告草稿（A2，零求解）

本目录为 task-145 交付：基于已完成 Batch2 证据的**只读**复算、中文图（300 dpi）与报告草稿。零求解器、零仓库工作树写入。

## 内容

| 路径 | 说明 |
| --- | --- |
| `docs/reviews/d12d005_batch2_report_20261104.md` | 中文报告草稿（提交目标路径），根目录另有同内容副本 |
| `d12d005_batch2_report_20261104.md` | 报告草稿副本（同 sha256） |
| `figures/fig1_budget_and_scope.png` | fig1（209695 B） |
| `figures/fig2_case_coefficients.png` | fig2（372259 B） |
| `figures/fig3_density_sensitivity.png` | fig3（208607 B） |
| `figures/fig4_perturbation_delta.png` | fig4（169150 B） |
| `figures/fig5_repeatability.png` | fig5（215350 B） |
| `figures_manifest.json` | 图清单（字节 / sha256 / 布局自检） |
| `recompute_batch2.py` / `recompute.json` / `recompute.md` | 零求解复算脚本与结果（对照 task-145 卡值） |
| `gen_figures.py` | 出图脚本（Microsoft YaHei，300 dpi，含文本 bbox 无重叠自检） |
| `SHA256SUMS.txt` | 本目录全部文件校验 |

## 关键结论

- 8 案数值、预算（8 starts / 0 retry / A 6→14/20）与卡值 **60/60 项一致、0 不一致**。
- 5 张图 300 dpi、中文无乱码、文本 bbox 自检 0 重叠（见 `figures_manifest.json`）。
- 标签保持 VSPAERO_INTERNAL_ONLY / physical_validation=NOT_VALIDATED；CDtot 不作真实阻力、LF-M2.02 未签核。

