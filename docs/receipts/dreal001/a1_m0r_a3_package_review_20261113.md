# A1 M0-R A3 r3 包只读独立复核

- review_id: A1-M0R-A3-R3-REVIEW-20261113
- 复核者: a1-geometry
- created_utc: 2026-11-13T08:06:59Z
- 目标包: D:\RCAIDE\dnext001\wt-real-a3-stats-routeb\docs\evidence\dreal001\m0r_20261113
- 目标 commit: 7128b911f7d8cb064ecd0b619b89f3af7abd27e3 (r3)
- 取代: 56fba8bf6f47fa201b3abd6b5fe59e56adb3934c (r2)
- **verdict: FAIL**
- 摘要: A3 r3 包在任务数值、12D 设计空间、M1-A deck freeze、SREF provenance 与边界声明上通过只读核查；唯一需更正的是一处 SREF provenance 的旧边界文本，属文本级、非科学阻断。

## 1. 结论
五项核查中 Q1、Q2、Q3、Q5 为 PASS；Q4 的科学数值与 CL-1 引用 PASS，但 M0R_SREF_PROVENANCE.json 的 non_result_boundary[0] 仍是旧 pre-draft 文本，判 CORRECTION_REQUIRED（文本级，非科学阻断）。

检查统计: total=29, {"PASS": 24, "FAIL": 1, "PASS_WITH_DISCLOSURE": 1, "CORRECTION_REQUIRED": 1, "OBSERVATION": 2}

## 2. 五项逐项

### Q1 6 任务数值（PASS）

A3 的 6 个任务的 q/Vinf/L_ref/mass 与 A1 ATM-F1R2 + post-fix 几何推出的值一致；M180 的 q 有 1.118e-16 的浮点差（A1 16265.063806566455 vs A3 16265.063806566453），在 1e-12 容差内。A1/A3 task_id 与 fingerprint 6/6 一一对应。

| A3 task | Mach | CL | q Pa | Vinf m/s | L_ref N | mass t | split A3 |
|---|---:|---:|---:|---:|---:|---:|---|
| T18K_M202_CL017 | 2.02 | 0.17 | 20483.940233430174 | 596.0373972278921 | 1247523.1700664815 | 127.21196025824125 | meta_train |
| T18K_M202_CL019 | 2.02 | 0.19 | 20483.940233430174 | 596.0373972278921 | 1394290.6018390087 | 142.17807322979905 | meta_train |
| T18K_M220_CL017 | 2.2 | 0.17 | 24297.194081414087 | 649.1496405452291 | 1479759.862543322 | 150.89351231494157 | meta_train |
| T18K_M220_CL019 | 2.2 | 0.19 | 24297.194081414087 | 649.1496405452291 | 1653849.2581366538 | 168.6456902343465 | meta_val |
| T18K_M180_CL017 | 1.8 | 0.17 | 16265.063806566453 | 531.1224331733692 | 990583.0484794137 | 101.01135948355594 | meta_test_blind |
| T18K_M180_CL019 | 1.8 | 0.19 | 16265.063806566453 | 531.1224331733692 | 1107122.2306534622 | 112.89504883456249 | meta_test_blind |

A3 split: meta_train 3 / meta_val 1 / meta_test_blind 2，与 L-30 3/1/2 一致；A1 用 meta_test 标签，属待补的 split-label crosswalk（O01）。

### Q2 12D 设计空间（PASS）

raw YAML SHA 8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e / 10,846 B 与 A1 冻结 YAML 一致；12 个变量（W01-W10, V01-V02）的 baseline/bounds 与 A1 一致；F01/F02/F03 固定值 61.66/4.30/1.152778；C01-C04 存在且明确由 M1 sampler/executor 强制，A1 interface 不替代；active_mask=12D_ALL_ACTIVE，V01/V02 未被误关；10D deferred 是 M1 后续动作，不是当前 mask 误写。

### Q3 M1-A deck freeze（PASS）

r3 元数据语义为 full family 18 = 3 designs x 6 tasks；6 个 B0-01 baseline decks 冻结；12 个 B1-01/C5 reference entries 未冻结；M1-A 需要 12 slots = 4 M1 tasks x 3 designs（4 B0 已冻 + 8 B1/C5 待冻）；M3-A 前再冻 4 个 meta_test B1/C5 slots。A3 r3 M1-A 12 槽位与 A1 commit 092a311 的 12 槽位 deck SHA、vspgeom SHA、design_hash 12/12 全等；6 个 baseline deck/task_deck 包内文件字节与记录一致。r3 n_fail=0。

### Q4 SREF provenance（PASS_WITH_CORRECTION）

anchor = 358.25000000000006 m2（A1 runtime post-fix baseline geometry；vspgeom 16da482a…/225,414 B）；独立 Newell wing_area = 358.2500000223502 m2，rel 6.238702072197911e-11 <= 1e-9；task 使用 anchor 而非 Newell；A1 clarification 7731e9c8…/7,673 B 被正确引用为 CL-1（runtime SREF 唯一来源，anchor 仅校验）。

需更正: M0R_SREF_PROVENANCE.json 的 non_result_boundary[0] 仍为旧文本: Pre-draft provenance only; not a frozen family, not a run, not a physical validation.。它与 M0R_PACKAGE.non_result_boundary[0] 的正式边界文本矛盾；只需文本替换，不影响任何数值/字节。

### Q5 包边界（PASS）

M0R_PACKAGE.status=M0R_PACKAGE_FROZEN_PENDING_A5_GATE；G-M0R-ADMISSION-01 状态 PENDING_A5_FORMAL_GATE；authorization_status=NOT_CREATED_M0R_ZERO_PHYSICAL；无 M1 authorization/GO。claims: fuel_burn_kg=null、physics_status=NOT_VALIDATED、no_winner/no_significance/no_cross_family_average=true。未发现把 M0-R 表述成 gate PASS、admission 或 M1 授权的越界声明；包内反而明确写明 gate PASS 不授权 M1。

## 3. Findings

- **A1-M0R-R3-C01** [CORRECTION_REQUIRED]: Replace with formal frozen-package wording, aligned with M0R_PACKAGE.non_result_boundary[0].
  - impact: No scientific, geometry, deck or accounting value changes; A5 gate may accept as errata/addendum.
- **A1-M0R-R3-O01** [OBSERVATION]: A3 label meta_test_blind vs A1 meta_test; mapping is explicit via a1_task_id and fingerprint 6/6.
- **A1-M0R-R3-O02** [OBSERVATION]: double v1 suffix; no data impact.

## 4. 证据与交叉引用

- A3 包: 40 files；SHA256SUMS 38/38 行全部匹配；未覆盖的仅 SHA256SUMS.txt 自身与历史 pre_draft/SHA256SUMS.txt。
- family_sha256 98b84f5e… 独立复算与包内 6 处引用一致（按 sort_keys=True/compact JSON/ensure_ascii=False canonical 哈希）。
- A3 M0R_VALIDATION 19/19 检查无 FAIL；M0R_A5_REQUIREMENTS_MAP n_fail=0（60 checklist / 42 conditions / 30 requirements mapped）。
- A1 M1-A payload: commit 092a31181cb12107f80bb65204f2469004793431；manifest SHA256 fea23ea13df8f196993297c84e5ae657145431b00a0e8710eb35bfa3199f974f / 77984 B；12/12 slots 与 A3 r3 对齐。
- A1 U1 dry-run: D:\RCAIDE\dnext001\wt-real-a1-geometry-solver\docs\receipts\dreal001\a1_m0r_task_executor_dry_run_20261113.json，verdict PASS，checks 50/0。

## 5. 声明

本复核为零物理只读：未启动 OpenVSP/VSPAERO，未建 run dir，未修改 A3 包或 A1 frozen 字节，physical_call_count=0。所有 SHA/bytes 均为本次实测。

## 6. Open items

- A3 to replace M0R_SREF_PROVENANCE.json non_result_boundary[0] with formal frozen-package text (text-only correction).
- A5 to decide whether C01 is folded into G-M0R-ADMISSION-01 errata or a package metadata addendum.
- A3 to add explicit M180 split-label crosswalk (meta_test_blind vs meta_test) in a future metadata revision.
