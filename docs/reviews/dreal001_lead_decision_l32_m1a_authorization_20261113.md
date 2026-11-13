# L-32：Issue #11 M0-R 通过后启动 M1-A 真实多任务标签准入批次

- 决策 ID：L-32
- 时间：2026-11-13T08:02:00Z
- 状态：ACTIVE
- 上游：Issue #10 完整中文汇报已发布（comment 6844814312）；Issue #11 D-META-REAL-001 M0/M0-R 已完成
- 权威门禁：A5 G-M0R-ADMISSION-01 revision 2，commit 881226fc059bdfbfbb03704b19845875179b54fa，gate json 810bf3d6c369a332d3a73f4519ec39e116d1522a2a364a2e7e08c6930453dbd2/69,299B，verdict READY_FOR_M1A_ADMISSION
- M0-R 包：A3 r3 commit 7128b911f7d8cb064ecd0b619b89f3af7abd27e3，SUMS 0bf7ce2d141f051e1aff6f607a495f28bf33c0b548ebd06ec8273538c8316800/38 entries，family_sha256 98b84f5ecf6e18a7be90e21da41b243dccb664f09034366ea3b58d777f1c0311
- deck freeze：A1 commit 092a31181cb12107f80bb65204f2469004793431，manifest fea23ea13df8f196993297c84e5ae657145431b00a0e8710eb35bfa3199f974f/77,984B，SUMS 13d1177bb50841cad877340840c4f3d19943b20fadfe5ad5631a5d16671ff733/10,000B/62 entries，12 slots×5 文件
- A1 代码冻结：code 0c514151d989de716dbb855973b900a34615b5aa、freeze c5698a218fad974e8e96b604573c5cc79b3abb32、clarification e659f15d826de0c55bcfe02944a97a28ba50b824

## 1. 决策

1. 接受 G-M0R-ADMISSION-01 rev2 为 **M1-A 准入依据**；旧 gate G-T0-ADMISSION-01（M0_BLOCKED）、provisional gate 6eb0059、A3 r2 56fba8b 均保留历史，不用于本授权链。
2. 启动 **M1-A 真实多任务标签准入批次**，唯一目的：用 4 个 meta_train 任务 × 3 个已冻结参考设计（B0-01/B1-01/C5）在真实 OpenVSP+VSPAERO 上验证任务可执行性、跨任务响应与预算/账本/失败分类，形成 M1-B 标签采集的准入证据。
3. M1-A **不训练**、不运行 meta_test（M180 两任务保持盲）、不生成正式训练数据集；本批不得用于任何增益/winner/显著性/跨族结论。
4. M1-A 通过后另立 **M1-B**（66 starts/462 internal、64 labels+2 preflight），再 M2 FOMAML、M3 盲留出；每期新 authorization/approval/A5 预审/Lead GO，不复用 #9 R10、#10 F1/F2 任何 token 或 approval。

## 2. 身份、窗口与预算（本批）

- authorization_id：**D-META-M1A-001**
- run_id：**DREAL001-M1A-20261113-01**
- window：**2026-11-13T08:30:00Z – 2026-11-13T18:00:00Z**
- token：**WINDOW_OK_DMETA_M1A_20261113T0830Z-20261113T1800Z**
- planned：**15 starts / 105 internal**（2 preflight + 12 design + 1 exact repeat）；caps：**18 starts / 126 internal / max_design_evals 15 / max_retries 0**；wall 3600s；solver 90s/case；case 180s；rebuild 60s；并发 1。
- 4 个 M1 任务：M0R-M202-CL017、M0R-M202-CL019、M0R-M220-CL017、M0R-M220-CL019；每任务 3 designs=B0-01/B1-01/C5；exact repeat 槽位由 A2 在包内预注册（建议 B0-01/M202_CL017，deck SHA 1614a964…/943B，vspgeom 16da482a…/225,414B），重复必须同 task/design/deck/进程 fresh，跨进程 CDi rel≤1e-9 或书面披露。
- M1-A 起五口径 charged=actual 分列；本批 planned 15/105、caps 18/126、retry 0；若出现 INFRA_ERROR 或 build/orientation/ledger/window 违规，硬停不重试，失败目标 null。

## 3. 预期与确定性边界

1. 本批 **不继承 F1R2 expected polar**；preflight 由 M1-A 自建 baseline，2/2 通过后才进 main。
2. 几何/求解器确定性绑定只用 **deck_sha256 + vspgeom_sha256**；vkey/input_sha 含路径/随机 component ID，仅按 run 记录，不作 gate。
3. 12 deck 只能来自 A1 092a311 的 12 个 slot；B0 4 槽与 M0-R r3 一致，B1/C5 8 槽为 M1-A 前冻结。
4. 12D_ALL_ACTIVE；10D DEFERRED；不声称 V01/V02 零效应；fuel_burn_kg=null；physics NOT_VALIDATED；单 seed 42 描述性；无 winner/显著性/跨族比较。

## 4. 授权链（fail-closed）

A2 包（plan/prereg/case matrix/caps/identity/approval.DRAFT/checklist/SHA）→ A5 M1-A PRE gate → Lead 签 approval（仅 9 字段变化）→ A2 安装 + 窗口内 post-approval dry-run（真实治理检查、physical=0）→ A5 C-P2AV2M1A-02 → Lead GO（绑 approval/dry-run/gate/budget/assets/窗口）→ A2 执行 15 starts → A3 统计/A5 post-run → Lead 收口。

Approval 必须绑定：gate rev2 881226fc/810bf3d6、A3 r3 7128b91/SUMS 0bf7ce2d、A1 deck freeze 092a311/SUMS 13d1177b、A1 code 0c51415/freeze c5698a2/clarify e659f15、A2 runner/executor/ledger SHA、expected=null/self-established。GO 缺任一绑定/窗口外/physical>0 一律拒绝。

## 5. 明确不授权

- M1-B 标签采集、M2 FOMAML 训练、M3 盲留出揭盲与 K-shot 对照；
- 任何 meta_test（M180）标签读取/运行；
- 任何跨批 token/approval/run dir 复用；
- 任何增益/winner/显著性/跨族结论；
- 外部物理有效性声明。

## 6. 记账基线

Issue #10 累计（历史）：actual 65 starts/455 internal；charged 70 starts/490 internal。M1-A 为 Issue #11 首批，独立起算 charged/actual；本决策不修改 #10 历史数字。

## 7. L-32 修订 2（A5 addendum 02 与 G08 补充，2026-11-13T08:05Z）

- A5 addendum 02：commit **1f79fc007c50702d7d15c5051b4e709810483182**；json 4393d11e…/7,323B、md f987c503…/2,102B、SUMS b5ea994a…/232B。生效：gate 顶层 bindings.a3_task_57_commit=**7128b91**；63e9356 仅历史 superseded_package_commit；package_commit=7128b91 为唯一最终对象；package.a5_gate.status 为 PENDING_A5_FORMAL_GATE_AT_PACKAGE_FREEZE（冻结时点），实际 gate 状态以 rev2 gate JSON status=ISSUED + commit 881226fc 为准。gate 本体 6 文件+SUMS 字节未改。
- exact repeat 预注册（A5 G08）：task **M0R-M202-CL017** / design **B0-01**；deck **1614a964fc729d42bfa764025a2aa1d3915be8f20dbc6480b72862c15e0c59dc**/943B；vspgeom **16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84**/225,414B；task_deck dc64a0f2…/6,975B；同 task/design/deck/vspgeom、fresh 进程；CDi rel≤1e-9 或披露。
- CTX min_effect_rel：**max(2*U_within, 1e-3)**，预注册；U_within 取 M1-A exact repeat 或历史有效值 7.05e-8；不得据此宣称 BO 增益。
- 4 个 M1 tasks admission evidence schema 必含：source_kind=REAL_VSPAERO、7 行 finite polar、lift_residual、physical_solver_starts_actual、internal=7×starts、geometry_sha256（deck+vspgeom）、solver_version_sha256、task_fingerprint_sha256、objective_D_i_N finite 或 null、failure_class；缺失 fail-closed。
- M1-A 授权前前置：run dir 不存在/空；不复用 #9/#10 token/approval；A5/Lead 新签；A2 包绑 gate rev2+add02+r3+SUMS 0bf7ce2d+validation 3fc249fe+A1 task-61 freeze manifest fea23ea1/SUMS 13d1177b。
