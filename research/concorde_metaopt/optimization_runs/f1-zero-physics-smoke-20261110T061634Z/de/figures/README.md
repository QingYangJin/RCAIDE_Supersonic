本 run 的 figures 目录为空：

- 本 run 为 F1 零求解软件闭环，physical_call_count=0，没有任何真实气动数据。
- 因此所有计划中的物理图（阻力极曲线、配平曲线、收敛历史等）状态均为 NOT_RUN。
- 这里不生成占位图或伪造数据点（禁止造假图）。
- 若后续 Tier0 真实 VSPAERO 启动获批，再按 Issue #8 合同补图并标注来源。
