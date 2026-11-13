# G-M0R-ADMISSION-01 正式 A5 门禁

- gate_id: G-M0R-ADMISSION-01
- 状态: ISSUED
- verdict: READY_FOR_M1A_ADMISSION
- issued_by: a5-review；issued_at_utc: 2026-11-13T07:25:55Z
- 目标: A3 M0-R 正式包 commit 63e93564a7cd2266b9f25e5234155e56460146fb，family_sha256 98b84f5ecf6e18a7be90e21da41b243dccb664f09034366ea3b58d777f1c0311
- A5 physical_call_count: 0；未建 run dir/ledger/token/authorization；不启动 VSPAERO

## 1. 结论

A5 独立复核 M0-R 包（38/38 SUMS、19/19 validation、6 tasks、3/1/2 split、A1 0c51415/c5698a2/e659f15、零物理）后，判定 READY_FOR_M1A_ADMISSION。本 gate 不是 M1-A 执行授权，不签 admission，不改变旧 G-T0-ADMISSION-01 的 M0_BLOCKED 历史。

## 2. 计数

| 项 | 值 |
|---|---|
| checks | 60 = 51 PASS + 9 PASS_WITH_DISCLOSURE + 0 FAIL |
| conditions | 42 = 30 R + 12 G |
| package SUMS | 38/38 OK |
| validation | 19/19 PASS |
| family SHA | 98b84f5e...（独立复算一致） |
| A1 tests | 27 passed（A5 独立执行） |
| A3 M0-R tests | 13 passed（A5 独立执行） |
| M1-A/M1-B/M3-A/M3-B | 均未授权；M3-B NOT_AUTHORIZED |

## 3. 关键检查

- MRC-01 [PASS] M0-R 包为全新 commit/目录，不修改旧 T0-4/A3 M0/F1/F2/R1-R10 字节；新 family_sha256 非 ada424cc、非 40fdd436。
- MRC-02 [PASS] M0-R 包内 SHA256SUMS 覆盖全部交付文件；A5 逐行复算全匹配。
- MRC-05 [PASS] M0-R 全程零物理：physical_call_count=0；无 run dir/ledger/token/authorization；无 solver spawn。
- MRC-06 [PASS] 任务族几何重绑 post-fix 546x480：baseline vspgeom 16da482a…/225,414B；openvsp_geometry d20ee7ad；F1R2 12D audit 7a90b977。
- MRC-09 [PASS] 6 任务 ID/因子与 L-30-A01 完全一致；alt 全 18,288 m；无 15/20 km 副本。
- MRC-10 [PASS] split 3 train/1 val/2 blind test；meta_test 盲、不在 M1/M2 运行、不揭盲。
- MRC-12 [PASS] q 单源 ATM-F1R2；p=7171.544888256813、T=216.65、R=287.05287、rho=0.1153178340089936、a=295.06801842964956、ReCref=89,397,005.8767656。
- MRC-13 [PASS] 6 任务 q 精确等于 20,483.940233430174（M2.02）/24,297.194081414087（M2.2）/16,265.063806566453（M1.8），rel≤1e-12。
- MRC-16 [PASS] L_ref=q*SREF_REF*CL_target；SREF_REF 运行时由 post-fix baseline 重算并 SHA 绑定；不得硬编码 358.25，不得 fallback。
- MRC-17 [PASS] 6 任务 L_ref/mass 精确匹配 L-30-A01：1,247,523.170066/127.211960；1,394,290.601839/142.178073；1,479,759.862543/150.893512；1,653,849.258137/168.645690；990,583.048479/101.011359；1,107,122.230653/112.895049。
- MRC-21 [PASS] 6 个 per-task .vspaero deck；deck SHA 进包；M2.02 deck 与 F1R2 参数（Mach 2.02/Vinf/Rho/ReCref/alpha）一致。
- MRC-23 [PASS] 零物理 dry-run 覆盖 6 任务×3 参考设计；spawn=[]、solver_outputs=[]、physical=0、无 run dir。
- MRC-24 [PASS] 设计空间同时绑 raw YAML 8b29d1e3…/10,846B 与 C01–C04 cross constraints。
- MRC-28 [PASS] 12D_ALL_ACTIVE；10D_ACTIVE_PLUS_2_INACTIVE=DEFERRED_TO_M1；不得声明 V01/V02 零效应。
- MRC-30 [PASS] M1-A CTX-A/B 预注册：4 任务×3 设计；效应量分离≥max(2U_within,1e-3)；Spearman n=3 仅描述性、无 p 值。
- MRC-32 [PASS_WITH_DISCLOSURE] M1-A 15/105 caps 18/126 retry0；4 任务×3 设计+1 exact repeat+2 preflight；repeat 预注册 task/design/deck SHA。
- MRC-35 [PASS] 总 115/805 hard 126/882 labels96 preflight6 retry0；M3-B NOT_AUTHORIZED。
- MRC-37 [PASS] admission=DEFERRED_TO_M1A_WITH_PRE_REGISTERED_CHECKS；M0/M0-R 不签 admission；首条真实 M1 标签按 validity/status/identity 判定，不按目标值。
- MRC-42 [PASS] q/L_ref/Sref 三重一致：q 由 deck 实际注入；L_ref=q*SREF_REF*CL；Sref(x) 逐设计；D_i=q*Sref(x)*CDi。
- MRC-44 [PASS] 任何 task/atmosphere/SREF/geometry/mass/q 校验失败必须 fail-closed；禁止回退 358.25/旧几何/ISO/旧 task/旧 token。
- MRC-46 [PASS] 不得宣称 winner/显著性/优化增益/跨族可比；fuel=null；外部物理 NOT_VALIDATED；单 seed 描述性；M3 任务级 n=2。
- MRC-51 [PASS] A3 M0-R 包由 task-57 正式冻结；task-60 pre-draft 不得被当作正式包/不得冻结。
- MRC-53 [PASS] A5 requirements R01–R30 逐条映射到本 checklist/conditions；无遗漏。
- MRC-56 [PASS] A5 独立执行：不修补 M0-R 包、不改 A1/A3 字节、不启动 solver、不建 run dir/ledger；physical=0。
- MRC-57 [PASS] gate 结果只可为 READY_FOR_M1A_ADMISSION 或 M0R_BLOCKED；不得写 admission signed/ready_for_real_meta_training=true。
- MRC-60 [PASS] 预算/账本算术独立复算：M1-A 15=12+1+2、105=7×15；M1-B 66、462=7×66；M3-A 34、238=7×34；总 115、805=7×115。

## 4. 关键绑定

- package commit: 63e93564a7cd2266b9f25e5234155e56460146fb
- package SUMS: 16a9a1e8cb15dc562b031c39cb993af77a3b4a13783b74efeae5e4bae6ca6653 / 3861 B / 38 entries
- validation: b0cfedae5262984fdfeaf537e32c6e6a7db25063b5f033ba13c386479a5fa1dd / 2445 B / 19/19 PASS
- task specs: bdac67b05d20dd2d351611f5c51a36d059029e6a2003c206d34e6416b92babff / 70622 B
- A1 code: 0c514151d989de716dbb855973b900a34615b5aa；freeze: c5698a218fad974e8e96b604573c5cc79b3abb32
- A1 clarification: 7731e9c8b6269e50b343f7e2fbb9ade9c123e14bb33db7e0a884a922cc83e948 / 7673 B
- A5 requirements: f8b70703bd6f6fb20849e8ca1e4e26200d9e3c3898df5ff16195c79b6d59fe61 / 16397 B / 30 条

## 5. 条件与后续

R01-R30 与 G01-G12 全量见 dreal001_a5_m0r_gate_issued_conditions_20261113.json。重点：
- G08：M1-A authorization 前冻结/重生成 12 reference decks；预注册 exact repeat task/design/deck SHA。
- G09：M1-B 的 meta_val 标签仅验证、不拟合；拟合只用 meta_train；M1-B/M3-A 各自授权。
- G10：CTX 4 任务 x 3 设计，min_effect_rel=max(2*U_within,1e-3)，Spearman n=3 仅描述性。
- G07/R29：M1-A 需新的 authorization/approval/A5 gate/Lead GO，不复用 #9/#10 token。

## 6. 披露

- D-M0R-01 M0R_A5_REQUIREMENTS_MAP.json 的 schema 字符串仍为 dreal001.m0r_predraft.a5_requirements_map.v1（历史命名）；其 coverage 30/60/42、status、family SHA 均为正式包值。A5 以本 gate 独立 checklist 为权威，不因该元数据字符串阻断。
- D-M0R-02 pre_draft/ 作为 task-60 历史附录保留在包内；其 SUMS 与文件不作为正式 gate 输入。正式 README/prereg 明确 pre_draft 不是正式包。
- D-M0R-03 M0-R 只冻结 6 个 baseline deck；12 个 reference deck 为 unfrozen_reference，必须按 G08 在 M1-A authorization 前冻结或确定性重生成，并记录 deck_sha256+vspgeom_sha256。
- D-M0R-04 M1-B 64 labels 覆盖 4 任务（含 1 meta_val）。M1-B 必须在 authorization 前显式规定 meta_val 标签仅验证、不参与拟合，拟合只用 meta_train；否则 M1-B 不得启动（G09）。
- D-M0R-05 A1 task_evaluator.py 保留 SREF_REF_FROZEN=358.25000000000006 作为 1e-12 校验锚；A1 clarification CL-1 明确运行时 post-fix baseline 重算值为唯一来源，禁止硬编码。A5 独立 Newell 复算 358.2500000223502，rel 6.2387e-11。
- D-M0R-06 M1-A CTX 只有 3 个 reference designs；Spearman n=3 仅描述性，禁止 p 值/显著性。CTX-B 接受 4/4 M1-A tasks separable 或 PHYSICAL_TASK_FAMILY_BLOCKED。
- D-M0R-07 A3 工作树存在预先未提交的 stats/p2a_v2.py 和 probes（非本包）；M0-R 包路径 git diff=0，旧 T0-4/task_spec 自 5832017 无 diff。
- D-M0R-08 q 单源 ATM-F1R2；与 ISO-1 q 相对差约 1.24e-5。M2.02 与 F1R2 仅物理条件连续，不继承 F1R2 expected polar；2.2/1.8 为新条件。
- D-M0R-09 A1 F-M0-02 事实更正：40fdd436=543x472/227,247B（F1 旧 L-20 缺陷几何）；199,997B/483x418 是 P1-05 58f63bfc，不是 40fd。阻断结论不变，旧 M0 已 M0_BLOCKED。
- D-M0R-10 M0-R 零物理；未创建 run dir/ledger/token/authorization；M1-A/M1-B/M3 均需新 authorization/approval/A5/Lead GO，不复用 #9/#10 token。
- D-M0R-11 M1-A exact repeat 的 task/design/deck SHA 尚未冻结；必须在 M1-A authorization 前预注册（G08）。
- D-M0R-12 M0-R 不计算 E1-E6，不签 admission；fuel_burn_kg=null；physics NOT_VALIDATED；单 seed 42 描述性；无 winner/显著性/跨族比较。

## 7. 边界

- 本 gate 不是 M1-A execution authorization。
- 不签 admission；ready_for_real_meta_training=false。
- M1-A 需新的 authorization/approval/A5 gate/Lead GO。
- M0-R 零物理；未见真实 VSPAERO 标签。
- fuel=null；physics NOT_VALIDATED；单 seed 描述性；无 winner/显著性/跨族。
