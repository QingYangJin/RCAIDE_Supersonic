# L-31 — 接受 A5 G-T0-ADMISSION-01（M0_BLOCKED）并启动 M0-R 准备

- 决策: lead；时间 2026-11-13T14:30+08:00（2026-11-13T06:30Z）
- 依据: A5 G-T0-ADMISSION-01（commit 24ccdb5643747b40361cb970b6645f49f9e51d24；gate json 422df1b5…/12,860B；requirements f8b70703…/16,397B/30 条）；A1 M0 复核 b4e4140；A3 D3 5bbca70；L-30 27f8d91；L-30-A01 30166a0。
- 裁决: 接受 A5 独立门禁 **M0_BLOCKED / PHYSICAL_TASK_FAMILY_BLOCKED**；当前 18-task 族不冻结、不启动 M1、不签 admission。旧 gate G-T0-ADMISSION-01 保持历史。M0-R 按 L-30 + L-30-A01 + A5 R01–R30 执行，新 gate 为 **G-M0R-ADMISSION-01**。
- M0-R 科学参数（冻结）: ATM-F1R2 q 单源；18,288 m；6 任务（3 train / 1 val / 2 blind test）；L_ref=q*SREF_REF*CL，SREF_REF 运行时由 post-fix 几何重算并 SHA 绑定；质量带 100–190 t；12D_ALL_ACTIVE，10D DEFERRED；预算 M1-A 15/105 caps 18/126、M1-B 66/462 caps 70/490、M3-A 34/238 caps 38/266、总 115/805 hard 126/882，labels 96，preflight 6，retry 0，M3-B 不授权。
- 分工: A1 task-56 交付 U1/U2（task-capable executor + 6 task deck + 独立 lift residual + 零物理 6 任务 dry-run）；A3 先做 M0-R pre-draft（task-60，不冻结），A1 接口冻结后 task-57 重冻包；A5 独立复核 M0-R 并签 G-M0R-ADMISSION-01；A2 继续 M1 runner 零物理准备；A4 standby。
- 边界: 本决策零物理；不创建 run dir/ledger/token/authorization；M0-R 通过前不得启动 solver；M1/M2/M3 各自新 authorization/approval/A5/Lead GO；不复用 #9/#10 token；fuel=null；外部物理 NOT_VALIDATED；不得 winner/显著性/跨族。
