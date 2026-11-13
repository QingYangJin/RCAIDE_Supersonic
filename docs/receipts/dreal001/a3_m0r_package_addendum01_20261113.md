# A3 M0-R 正式包修订 r2 回执（SREF disclosure 对齐 CL-1）

- 日期：2026-11-13
- 角色：A3（a3-stats）
- 任务：task-57 / task-60 的正式 M0-R 包最小修订
- 性质：**formal package revision**；不是 gate、不是 admission、不是 M1 授权；零物理。

## 1. 修订原因

commit 63e9356 的正式包中，M0R_SREF_PROVENANCE.json 的 consistency.disclosure 保留了 pre-draft 模板句：

> this pre-draft uses an independent post-fix vspgeom Newell recompute ... The A1 interface deviation is disclosed to A5/Lead and must be resolved before task-57 freeze.

该句在正式包中已过期：A1 clarification addendum commit e659f15（json 7731e9c8.../7,673 B）已被 A5 m04225 接受，CL-1 明确 SREF_REF 以运行时 post-fix 重算值为唯一来源，冻结常量仅作 1e-12 校验锚。为避免 A5 门禁把该句读成未解决偏差，做最小文本修订。

## 2. 修改范围（仅 4 个文件）

1. docs/evidence/dreal001/m0r_20261113/M0R_SREF_PROVENANCE.json
   - consistency.disclosure 改为 CL-1 已绑定的正式表述；
   - consistency.status 由 PASS_WITH_DISCLOSURE 改为 PASS_WITH_DISCLOSURE_CL1_BOUND；
   - 新 SHA256：12071810c481fcad89d6beafabb5f08f86c05d7f1859a9ab195f1451fd1c071e / 10,505 B。
2. docs/evidence/dreal001/m0r_20261113/M0R_VALIDATION.json
   - 仅 validated_utc 更新为 2026-11-13T07:23:05Z；verdict 仍 M0R_PACKAGE_FROZEN_PENDING_A5_GATE，n_pass=19/n_fail=0；
   - 新 SHA256：b0cfedae5262984fdfeaf537e32c6e6a7db25063b5f033ba13c386479a5fa1dd / 2,445 B。
3. docs/evidence/dreal001/m0r_20261113/SHA256SUMS.txt
   - 仅更新上述两文件的 SHA 行；38 entries；
   - 新 SHA256：16a9a1e8cb15dc562b031c39cb993af77a3b4a13783b74efeae5e4bae6ca6653 / 3,861 B。
4. research/concorde_metaopt/dreal001/meta/m0r_package.py
   - 新增上述 disclosure/status 覆写，保证重建可复现；
   - 新 SHA256：f3c77519c84a24f2a0d666a60858a53cb9b6ed8dc3ff0d4f8229e6216e1fe217 / 53,569 B。

## 3. 未改动（逐项核对）

- family_sha256：**98b84f5ecf6e18a7be90e21da41b243dccb664f09034366ea3b58d777f1c0311**（不变）。
- 6 TaskSpec：task_id/fingerprint/q/L_ref/mass/split/geometry/solver 均不变。
- M0R_TASK_SPECS.json SHA：bdac67b05d20dd2d351611f5c51a36d059029e6a2003c206d34e6416b92babff（不变）。
- M0R_PACKAGE.json SHA：2ea90cd69814ef324e46805c8fff075a4d30cf5437c64b7ec1ab48731c8377c6（不变）。
- 预算/五口径、3/1/2 split、6 baseline decks、12 reference deck 边界、CTX、统计端点、A5 map、zero-physical 证据均不变。
- 未改 A1 冻结文件、T0-4/M0 DRAFT 旧字节、F1/F2/R1-R10 run dir。

## 4. 零物理与验证

- physical_call_count = 0；solver_started = false；run_dir_created = false；未建 token/approval/authorization/ledger。
- 重建：D:\Anaconda\\python.exe m0r_package.py -> 19/19 PASS，verdict M0R_PACKAGE_FROZEN_PENDING_A5_GATE，family_sha256 不变。
- 测试：D:\Anaconda\\python.exe -m pytest research\concorde_metaopt\\tests\\test_dreal001_m0r_package.py -q -p no:cacheprovider -> **13 passed / 0 failed**（仅本文件，不声称全仓）。

## 5. 门禁对象

- 本修订 commit（见提交后报告）取代 63e9356 作为 A5 G-M0R-ADMISSION-01 的门禁对象；63e9356 为历史修订。
- A5 请以新 commit + 新 SHA256SUMS.txt（38 entries）为对象复算。
- 本回执不是 gate/admission/M1 授权；A5 独立裁决，最终 verdict 由 A5 签发。