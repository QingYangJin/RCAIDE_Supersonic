# G-M0R-ADMISSION-01 rev2 — Addendum 03：A1 task-61 G08 deck freeze 独立复核

- addendum_id: G-M0R-ADMISSION-01-ADD-03；status: ISSUED；issued_by: a5-review；issued_at_utc: 2026-11-13T08:06:48Z
- 对象：A1 task-61 commit **092a31181cb12107f80bb65204f2469004793431**
- 结论：**A5_INDEPENDENT_DECK_FREEZE_VERIFICATION_PASS**；不是 M1-A 执行授权/approval/GO

## 1. 独立核验结果

| 检查 | 结果 |
|---|---|
| A1 commit/tree | 092a311，task-61 路径 clean |
| manifest / receipt / SUMS | fea23ea1…/77,984B、1f8620ba…/3,988B、13d1177b…/10,000B/62 |
| SUMS 62/62 | **PASS，0 mismatch** |
| 12 slots | **PASS**，4 M1 tasks × 3 designs；4 B0 + 8 B1/C5 |
| deck/vspgeom/design_hash | **12/12、12/12、12/12 PASS** |
| 60/60 payload | **PASS**，5 files/slot，SHA 与源一致 |
| A3 r3 未改 | SUMS 38/38、M0R_DECK_FREEZE cb9331/40,496B 未变 |
| exact repeat | M0R-M202-CL017/B0-01，deck 1614a964/943B，vspgeom 16da482a/225,414B，task_deck dc64a0f2/6,975B |
| 零物理 | copy-only；openvsp/vspaero=false、rebuilt=false、run_dir=false、physical=0 |
| A1 checks | 18/18 PASS |

## 2. 关键槽位事实

- B0-01（4 slots）：deck 1614a964（M202, 943B）/6a022882（M220, 957B），vspgeom 16da482a（225,414B），design_hash 8bd5a6c7c8311938。
- B1-01（4 slots）：deck 同 Mach 的 B0 值，vspgeom 6a296aee（225,414B），design_hash 6653517b11d6f891。
- C5（4 slots）：deck 1253fa5f（M202, 931B）/d5d9104e（M220, 945B），vspgeom e1ad74cc（225,414B），design_hash bc52a54ecefaac4c。
- 全部 12 slots 仅含 meta_train 3 tasks + meta_val 1 task；无 meta_test/M180。

## 3. M1A-PRE-01 绑定要求

- 必须绑定本 addendum 03 json/SHA + A1 task-61 commit 092a311 + manifest fea23ea1 + SUMS 13d1177b。
- M1-A authorization 只允许引用这 12 个已核验槽位，不得引用未冻结 reference。
- M1-A 仍需 A2 包 → A5 M1A-PRE-01 → Lead approval → post-approval dry-run → A5 C-P2AV2M1A-02 → Lead GO。

## 4. 披露

- D-ADD03-01：A1 B0-01 slots 的 vspaero/task_deck 来自 A3 r3 M0-R 冻结 baseline，vspgeom/vkey/csf 来自 A1 U1 dry-run build；B1-01/C5 全部来自 A1 U1 dry-run。
- D-ADD03-02：vkey 含路径相关字段，仅记录 SHA；跨进程确定性身份使用 deck_sha256+vspgeom_sha256。
- D-ADD03-03：本 addendum 不是 M1-A 执行授权/approval/GO；不签 admission；不改变 G-M0R-ADMISSION-01 rev2 的 60 checks/42 conditions。
- D-ADD03-04：A1 manifest 使用 task_id=T18K_* 与 a3_task_id=M0R-* 双标识；A5 核验两者与 M0-R 4 tasks 对应，授权链应以 M0R-* task_id 为主键。

## 5. 边界

- A5 physical_call_count=0；未建 run dir/ledger/token/authorization；未启动 solver。
- M1-A 仍需新 authorization/approval/Lead GO；M1-B/M2/M3 不授权。
- fuel_burn_kg=null；physics NOT_VALIDATED；不产生 winner/显著性/跨族结论。
