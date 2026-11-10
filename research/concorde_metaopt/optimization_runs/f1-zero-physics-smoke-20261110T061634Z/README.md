# F1 零求解冒烟 run（20261110T061634Z）

本目录是 D-NEXT-001 F 线（真实评价抽象与航空约束）的最小垂直切片产物：

- 链路：12D 提升面设计 -> EvaluatorProtocol -> BudgetLedger -> BO/DE ask-tell -> run 产物。
- **physical_call_count = 0**：未启动任何 VSPAERO / SU2 / RCAIDE Mission / WaveDrag。
- bo/：maml_opt 约束贝叶斯优化 + 合成占位目标（SYNTHETIC_MOCK，physical_validation_status=NOT_APPLICABLE）。
- de/：自写 MiniDE（DE/rand/1/bin，可行性优先），同一合成占位目标。
- replay/：归档 replay（ARCHIVE_REPLAY，只读 geometry-check-p1-20261028T1835），返回 PHYSICS_NOT_VALIDATED 且 objective=null；
  归档索引未命中的设计返回 EVALUATOR_ERROR（fail-closed）。
- 合成目标的线性系数**没有物理含义**，不得据此得出阻力/油耗/配平结论。
- figures 目录为空并标注 NOT_RUN：无真实气动数据，不造假图。
- 物理门禁现状：VSPAERO LF-M2.02 = NOT_VALIDATED，BODY-CORR = BLOCKED，HF-M2.02 = PARTIAL；
  Tier0 真实 VSPAERO 启动预算仍只是**申请**，未获批（见 docs/planning/dnext001_f_tier0_budget_proposal.md）。
