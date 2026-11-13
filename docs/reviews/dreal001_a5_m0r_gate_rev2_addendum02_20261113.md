# G-M0R-ADMISSION-01 revision 2 — Addendum 02

- addendum_id: G-M0R-ADMISSION-01-ADD-02；status: ISSUED；issued_by: a5-review；issued_at_utc: 2026-11-13T07:59:41Z
- gate: G-M0R-ADMISSION-01 revision 2；gate commit 881226fc059bdfbfbb03704b19845875179b54fa；verdict READY_FOR_M1A_ADMISSION 不变
- gate 本体 6 文件 + SUMS **字节未改**；本 addendum 仅更正字段读取语义

## 1. 更正事项

| 字段 | 冻结时/旧值 | 生效值 | 处理 |
|---|---|---|---|
| bindings.a3_task_57_commit | 63e9356… | **7128b91…** | 生效值以本 addendum 为准；63e9356 仅历史 |
| package.a5_gate.status | PENDING_A5_FORMAL_GATE | **PENDING_A5_FORMAL_GATE_AT_PACKAGE_FREEZE** | 仅表示包冻结时点；实际 gate 状态为 ISSUED |
| package.a5_gate.a5_commit | null | **881226fc059bdfbfbb03704b19845875179b54fa** | null 为冻结时点值，不是“gate 未签发” |
| validation.a5_gate.status | PENDING_A5_FORMAL_GATE | **PENDING_A5_FORMAL_GATE_AT_PACKAGE_FREEZE** | 同上 |

## 2. 权威读取顺序

1. bindings.package_commit = **7128b91…**（唯一最终包）
2. bindings.a3_r3_commit = 7128b91…；bindings.package_revision = r3
3. bindings.a3_task_57_commit = **7128b91…**（本 addendum 生效；63e9356 历史）
4. bindings.package_sums.sha256 = 0bf7ce2d…；bindings.package_validation.sha256 = 3fc249fe…
5. 本 addendum 02

## 3. M1-A authorization 必须绑定

- gate revision 2 commit 881226fc059bdfbfbb03704b19845875179b54fa + gate json 810bf3d6c369a332d3a73f4519ec39e116d1522a2a364a2e7e08c6930453dbd2
- 本 addendum 02（commit/SHA 签发后回填）
- A3 r3 7128b91 + SUMS 0bf7ce2d… + validation 3fc249fe…
- package_commit 7128b91 为唯一最终对象；63e9356 仅历史披露
- G08 12-deck freeze payload（A1 task-61 commit 092a3118…）经 A5 独立核验后绑定

## 4. 未变

verdict READY_FOR_M1A_ADMISSION；checks 60 = 51 PASS + 9 PWD + 0 FAIL；conditions 42 = 30 R + 12 G；gate 字节未改。本 addendum 不是 M1-A 执行授权；M1-A 仍需新 authorization/approval/Lead GO。A5 physical=0，未建 run dir/ledger/token。