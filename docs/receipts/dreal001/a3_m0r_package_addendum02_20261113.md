# A3 M0-R 正式包 r3 最小元数据修订回执（2026-11-13）

- 任务：task-57（M0-R 正式包）/ Lead r3 指令；零物理，未启动 solver，未建 run dir/ledger/token/authorization。
- 修订对象：`M0R_DECK_FREEZE.json` 计数/语义不一致；**未改任何 deck 字节、6 个任务、预算、split、family**。
- family_sha256：`98b84f5ecf6e18a7be90e21da41b243dccb664f09034366ea3b58d777f1c0311`（与 r2 相同）。
- 包校验：19/19 PASS，verdict `M0R_PACKAGE_FROZEN_PENDING_A5_GATE`；A3 不签 gate、不宣布 admission。
- physical_call_count=0，solver_started=false，run_dir_created=false。

## 1. r3 修正后的 deck 口径

- full family deck 空间 = 3 designs（B0-01, B1-01, C5）× 6 tasks = **18 entries**；
- **6** 个 B0-01 baseline deck 已冻结：`1614a964…/943B`（M202）、`6a022882…/957B`（M220）、`9e755cdd…/942B`（M180）；
- **12** 个 B1-01/C5 reference entries 未冻结，单独列在 `reference_design_decks_unfrozen_reference`；
- **M1-A 12 个 slot** = 4 个 M1 tasks（3 meta_train + 1 meta_val）× 3 designs：4 个 B0 slot 已冻结 + **8 个 B1-01/C5 slot 必须在 M1-A 授权前冻结/确定性重生成**；
- **M3-A 4 个 slot** = 2 个 meta_test task × 2 个 B1-01/C5 design，必须在 M3-A 前冻结；
- `m1a_required_deck_set` 12 条逐项含 task_id、design_id、deck_sha256、vspgeom_sha256、frozen_status；`m1a_required_deck_set_label = M1-A_REQUIRED_DECK_SET`。

## 2. 改动文件 SHA256/bytes（本机重算）

| 文件 | SHA256 | bytes |
|---|---|---|
| docs/evidence/dreal001/m0r_20261113/M0R_DECK_FREEZE.json | CB933119A88136B3F10C177FB34487B5D7E01055009E65D0A21AF2C43141F2D6 | 40,496 |
| docs/evidence/dreal001/m0r_20261113/M0R_PACKAGE.json | D51AF8983CD6FFCCCE05AE9120A2F6CE06A895A019DC31708DD0853A6D86039F | 6,052 |
| docs/evidence/dreal001/m0r_20261113/M0R_PREREGISTRATION_ZH.md | 2FF78996D1BB5581AF414C25E7ECCCDF6163262F489294EA4758CAE192AAB799 | 7,291 |
| docs/evidence/dreal001/m0r_20261113/M0R_VALIDATION.json | 3FC249FEA06C96A974CF3AC275046A28D38A2571D701E4B2CB7A84975481FF00 | 2,445 |
| docs/evidence/dreal001/m0r_20261113/README_ZH.md | A0E1EE352FD5965517AC74FE2D5BED02DA000C14BF21862D4518EC93E7B1CFCD | 1,972 |
| docs/evidence/dreal001/m0r_20261113/SHA256SUMS.txt | 0BF7CE2D141F051E1AFF6F607A495F28BF33C0B548EBD06EC8273538C8316800 | 3,861（38 entries） |
| research/concorde_metaopt/dreal001/meta/m0r_package.py | 78570AA67128490C60543155ED3565FACCEFB3241D710D38810D731647878F90 | 61,223 |
| research/concorde_metaopt/tests/test_dreal001_m0r_package.py | C35F2B2E5A53845706E86E300D82D7D0F8025631D0223E759D9C271EE2A07054 | 12,664 |

r2 旧值（仅历史）：M0R_DECK_FREEZE `f09c6ac0…/23,581`；README `d268dc2f…/1,584`；PREREG `2f5eaebc…/6,960`；PACKAGE `2ea90cd6…/5,894`；SUMS `16a9a1e8…/3,861`。

## 3. 验证与边界

- 测试：`D:\Anaconda\python.exe -m pytest research\concorde_metaopt\tests\test_dreal001_m0r_package.py -q -p no:cacheprovider` → **15 passed / 0 failed**（仅本文件，不声称全仓）。
- 新增测试覆盖：18/6/12/12/4/8/4 计数、m1a_required_deck_set 12 条、README/prereg 边界文案。
- 未改：`M0R_TASK_SPECS.json`、`M0R_BUDGET_LEDGER.json`、`M0R_SPLIT_LEAKAGE_AUDIT.json`、`M0R_SREF_PROVENANCE.json`、6 个 deck 文件（git status 无 deck 变更）。
- 本修订不是新 gate、不是 admission、不是 run、不是结果；A5 复核并签 G-M0R-ADMISSION-01（revised gate 绑定 r3）后才可能进入 M1-A 授权链。
- fuel_burn_kg=null；physics NOT_VALIDATED；无 winner/显著性/跨族/增益声明。

## 4. 上游绑定不变

- A1 code commit `0c514151d989de716dbb855973b900a34615b5aa`；freeze `c5698a218fad974e8e96b604573c5cc79b3abb32`；7 文件 SUMS `3ca22ec983f4c7f60360075564cf93d255fbcce2156181f0cdbdff07d4f5d302`。
- A1 澄清 addendum commit `e659f15d826de0c55bcfe02944a97a28ba50b824`（json `7731e9c8…/7,673`、md `444fda5b…/4,294`，A5 已接受为权威口径）。
- A5 gate 草稿 commit `ba1b11f`，60 checks / 42 conditions；正式 gate 未出。
