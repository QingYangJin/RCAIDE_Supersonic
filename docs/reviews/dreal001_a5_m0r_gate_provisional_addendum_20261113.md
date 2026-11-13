# G-M0R-ADMISSION-01 ADD-01（临时/待替换）

- addendum_id: G-M0R-ADMISSION-01-ADD-01
- status: PROVISIONAL_SUPERSEDED_PENDING_A3_REVISION
- 旧 gate commit: 6eb0059c88f5102fde1ae5393aef85d44ef559a1（2026-11-13T07:2xZ，基于 A3 63e9356）
- 旧 gate verdict: READY_FOR_M1A_ADMISSION；60 checks=51 PASS+9 PWD；42 conditions

## 原因

Lead m11577 通知：A3 在 63e9356 之后正在做最小修订（SREF provenance disclosure 与 A1 CL-1/e659f15 对齐 + validated_utc + 对应 SHA256SUMS 行；不改 6 任务数值/预算/split/deck/family），并要求以 A3 新正式包 revision commit/SUMS 为正式门禁对象，先不要基于 63e9356 签发最终 gate。该通知在旧 gate 已 commit 后到达。

## 处置

1. 旧 gate 6eb0059 **只作临时/历史**，不得用于 M1-A authorization、admission 或 Issue #11 发布；
2. 旧 gate 与旧 A3 包字节不改、不覆盖；
3. A5 等 A3 新 commit/SUMS 到后，以新对象重出正式 gate（新产物/commit/SHA）；
4. 若新 diff 超出 SREF disclosure/validated_utc/SUMS 行，先报 Lead 裁定；
5. A5 physical_call_count=0；未启动 solver/未建 run dir/ledger/token。

## 边界

本 addendum 不是 admission，不是 M1-A 授权，不改变旧 G-T0-ADMISSION-01（24ccdb5/M0_BLOCKED）历史。
