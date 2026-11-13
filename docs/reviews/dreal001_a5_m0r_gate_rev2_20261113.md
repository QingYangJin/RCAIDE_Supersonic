# G-M0R-ADMISSION-01（revision 2，正式）

- gate_id: G-M0R-ADMISSION-01；gate_revision: 2
- status: ISSUED；issued_by: a5-review；issued_at_utc: 2026-11-13T07:50:56Z
- verdict: **READY_FOR_M1A_ADMISSION**
- supersedes: 6eb0059c88f5102fde1ae5393aef85d44ef559a1（provisional）；supersedes_reason: A3_M0R_PACKAGE_MINIMAL_REVISION
- r2 56fba8bf6f47fa201b3abd6b5fe59e56adb3934c 仅历史中间修订，未签发
- 最终包: A3 commit **7128b911f7d8cb064ecd0b619b89f3af7abd27e3**（r3）；family_sha256 98b84f5ecf6e18a7be90e21da41b243dccb664f09034366ea3b58d777f1c0311
- A5 physical_call_count: 0；未建 run dir/ledger/token/authorization；不启动 VSPAERO

## 1. 结论

A5 独立复核 r3 包（40 files/493,766B；SUMS 38/38、488,818B、0 mismatch；validation 19/19 PASS；A3 tests 15 passed；6 tasks、3/1/2 split、A1 0c51415/c5698a2/e659f15、零物理）后维持 **READY_FOR_M1A_ADMISSION**。本 gate 不是 M1-A 执行授权，不签 admission，不改变旧 G-T0-ADMISSION-01（M0_BLOCKED）历史。

## 2. 计数

| 项 | 值 |
|---|---|
| checks | 60 = 51 PASS + 9 PASS_WITH_DISCLOSURE + 0 FAIL |
| conditions | 42 = 30 R + 12 G |
| package | 40 files/493,766B；SUMS 38/38/488,818B |
| validation | 19/19 PASS；M0R_PACKAGE_FROZEN_PENDING_A5_GATE |
| A3 tests | 15 passed/0 failed（A5 独立执行） |
| M1-A/M1-B/M3-A/M3-B | 均未授权；M3-B NOT_AUTHORIZED |

## 3. Deck 口径（G08）

- full family deck space = **18**（B0-01/B1-01/C5 × 6 tasks）；
- baseline_task_decks = **6**（B0-01 ×6，FROZEN_IN_M0R_PACKAGE；deck SHA 1614a964/、6a022882/、9e755cdd/）；
- reference_design_decks_unfrozen_reference = **12**（仅 B1-01/C5，UNFROZEN_REFERENCE）；
- M1-A_REQUIRED_DECK_SET = **12** = 4 M1 tasks × 3 designs；**4 个 B0 已冻 + 8 个 B1/C5 须在 M1-A authorization 前冻结/确定性重生成**；
- m3a_reference_deck_set = **4**（M180×B1-01/C5，M3-A 前冻结）；
- freeze_boundary 明列 18/6/12/12/4/8/4；decks/ 字节未改。

## 4. 关键绑定

- package commit: 7128b911f7d8cb064ecd0b619b89f3af7abd27e3
- package SUMS: 0bf7ce2d141f051e1aff6f607a495f28bf33c0b548ebd06ec8273538c8316800 / 3861 B / 38 entries
- validation: 3fc249fea06c96a974cf3ac275046a28d38a2571d701e4b2cb7a84975481ff00 / 2445 B / 19/19 PASS
- task specs: bdac67b05d20dd2d351611f5c51a36d059029e6a2003c206d34e6416b92babff / 70622 B（未改）
- deck freeze: cb933119a88136b3f10c177fb34487b5d7e01055009e65d0a21af2c43141f2d6 / 40496 B
- A1 code: 0c514151d989de716dbb855973b900a34615b5aa；freeze: c5698a218fad974e8e96b604573c5cc79b3abb32
- A1 clarification: 7731e9c8b6269e50b343f7e2fbb9ade9c123e14bb33db7e0a884a922cc83e948 / 7,673 B
- A3 generator: 78570aa67128490c60543155ed3565faccefb3241d710d38810d731647878f90 / 61223 B；tests: c35f2b2e5a53845706e86e300d82d7d0f8025631d0223e759d9c271ee2a07054 / 12664 B

## 5. 条件与后续

R01-R30 与 G01-G12 全量见 dreal001_a5_m0r_gate_rev2_conditions_20261113.json。重点：G08（M1-A 12 slots / 4+8 / M3-A 4）、G09（meta_val 仅验证）、G10（CTX 4×3、min_effect_rel、Spearman n=3 描述性）、G07/R29（M1-A 新授权，不复用 #9/#10 token）。

## 6. 披露

- D-M0R-01 M0R_A5_REQUIREMENTS_MAP.json 的 schema 字符串仍为 dreal001.m0r_predraft.a5_requirements_map.v1（历史命名）；其 coverage 30/60/42、status、family SHA 均为正式包值。A5 以本 gate 独立 checklist 为权威，不因该元数据字符串阻断。
- D-M0R-02 pre_draft/ 作为 task-60 历史附录保留在包内；其 SUMS 与文件不作为正式 gate 输入。正式 README/prereg 明确 pre_draft 不是正式包。
- D-M0R-03 M0-R 只冻结 6 个 B0-01 baseline deck；full family deck space=18（3 designs×6 tasks），其中 12 个 B1-01/C5 entries 为 unfrozen_reference。M1-A_REQUIRED_DECK_SET=12（4 M1 tasks×3 designs：4 B0 已冻 + 8 B1/C5 须在 M1-A authorization 前冻结或确定性重生成）；M3-A 前还需冻结 4 个 M180×B1/C5 meta_test reference decks。记录 deck_sha256+vspgeom_sha256；unfrozen reference 不得用于物理执行。
- D-M0R-04 M1-B 64 labels 覆盖 4 任务（含 1 meta_val）。M1-B 必须在 authorization 前显式规定 meta_val 标签仅验证、不参与拟合，拟合只用 meta_train；否则 M1-B 不得启动（G09）。
- D-M0R-05 A1 task_evaluator.py 保留 SREF_REF_FROZEN=358.25000000000006 作为 1e-12 校验锚；A1 clarification CL-1 明确运行时 post-fix baseline 重算值为唯一来源，禁止硬编码。A5 独立 Newell 复算 358.2500000223502，rel 6.2387e-11。
- D-M0R-06 M1-A CTX 只有 3 个 reference designs；Spearman n=3 仅描述性，禁止 p 值/显著性。CTX-B 接受 4/4 M1-A tasks separable 或 PHYSICAL_TASK_FAMILY_BLOCKED。
- D-M0R-07 A3 工作树存在预先未提交的 stats/p2a_v2.py 和 probes（非本包）；M0-R 包路径 git diff=0，旧 T0-4/task_spec 自 5832017 无 diff。
- D-M0R-08 q 单源 ATM-F1R2；与 ISO-1 q 相对差约 1.24e-5。M2.02 与 F1R2 仅物理条件连续，不继承 F1R2 expected polar；2.2/1.8 为新条件。
- D-M0R-09 A1 F-M0-02 事实更正：40fdd436=543x472/227,247B（F1 旧 L-20 缺陷几何）；199,997B/483x418 是 P1-05 58f63bfc，不是 40fd。阻断结论不变，旧 M0 已 M0_BLOCKED。
- D-M0R-10 Gate revision 2（7128b911f7d8cb064ecd0b619b89f3af7abd27e3）supersedes provisional gate 6eb0059（基于 63e9356）；r2 56fba8b 为历史中间修订，未签发。旧 gate 与旧包字节保留，不用于 M1-A 授权链。M0-R 零物理；M1-A/M1-B/M3 均需新 authorization/approval/A5/Lead GO，不复用 #9/#10 token。
- D-M0R-11 M1-A exact repeat 的 task/design/deck SHA 尚未冻结；M1-A_REQUIRED_DECK_SET 12 中的 8 个 B1/C5 slots 也须在 M1-A authorization 前冻结/确定性重生成。M3-A 前冻结 4 个 M180×B1/C5。
- D-M0R-12 M0-R 不计算 E1-E6，不签 admission；fuel_burn_kg=null；physics NOT_VALIDATED；单 seed 42 描述性；无 winner/显著性/跨族比较。
- D-M0R-13 r3（7128b91）为 A3 最小元数据修订：DECK_FREEZE 精确化 18/6/12/12/4/8/4 + M1-A_REQUIRED_DECK_SET，SREF disclosure 绑 A1 CL-1/e659f15、validation validated_utc、README/prereg/SUMS；decks/、TASK_SPECS、BUDGET、SPLIT、family、6 task 数值均未变。r2（56fba8b）仅 SREF 过渡修订，未签发。
- D-M0R-14 A3 生成器 m0r_package.py（78570aa6…/61,223B）与测试 test_dreal001_m0r_package.py（c35f2b2e…/12,664B）随 r3 更新；A5 独立运行 15 passed。生成器/测试不是冻结科学字节，gate 以包字节与 A1 冻结契约为判据；M1-A 执行前如需重生成 deck，须用同版本生成器并记录 SHA。

## 7. 边界

- 本 gate 不是 M1-A execution authorization。
- 不签 admission；ready_for_real_meta_training=false。
- M1-A 需新的 authorization/approval/A5 gate/Lead GO。
- M0-R 零物理；未见真实 VSPAERO 标签。
- fuel=null；physics NOT_VALIDATED；单 seed 描述性；无 winner/显著性/跨族。
