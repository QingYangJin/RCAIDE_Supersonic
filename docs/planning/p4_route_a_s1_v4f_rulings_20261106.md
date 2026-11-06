# P4 路线A S1 v4f 整改裁定（A5 phase4b blocker 收敛）

> 状态：v4f 裁定（2026-11-06，Lead），依据 A5 task-256 phase4b 终审（verdict=CHANGES_REQUESTED，1 blocker/0 major/4 minor；报告 EXT/p4-route-a/a5/S1_phase4b_review.md sha256 def5c059afd7ffd5e7b8c8a858fa676ccd7a5aff6c21d81e48f94c5cc6b98438）。本文件随 commit J 入库，不构成 S1 formal 授权。

## R-V4-11-01 确证包 code_sha 绝对 fail-closed（关闭 S1R4b-B01）

- 对 `confirmatory_eligible=true`（evaluation_mode=confirmatory）的冻结包，任何命令（grid/run/merge）在 code_sha 与当前 `fv3.package_code_sha()` 不一致时必须抛出 `S1_FROZEN_CODE_SHA_DRIFT`，**即使传入 `--allow-code-delta` 也不得放行**。
- `--allow-code-delta` 仅对非确证（legacy/exploratory）包有效；放行时仍须在 run_config/run_summary/manifest/merge_manifest/grid 记录 frozen/current 双 sha、code_sha_match=false、code_sha_delta_allowed=true、evaluation_mode=exploratory。
- 禁止任何“确证包 + delta 放行 + evaluation_mode=confirmatory”的组合；该组合一旦出现即视为合同违反（FC-17）。
- 与 R-V4-10-02 一致；R-V4-10-02 的“仅 exploratory 可 --allow-code-delta”是唯一解释，不存在 deviation 空间。

## R-V4-11-02 测试要求

- 更新 tests/test_s1_runner.py:2070/:2122 中反向固化旧语义的用例。
- 新增负控：对 S0-5（code_sha 25f726f8…，confirmatory=true）与 S0-6（1f244984…，confirmatory=true）分别执行 grid/run/merge + `--allow-code-delta`，必须非 0 退出且错误码含 `S1_FROZEN_CODE_SHA_DRIFT`；不得产生 run bundle/merged 产物。
- 新增正控：非确证/legacy 包（如 S0-2/S0-3，confirmatory_eligible=false）在 delta 下仍可按 exploratory 放行并记录双 sha。
- 全量测试数必须 ≥948 且 OK(skipped=1)。

## R-V4-11-03 文档/报告修正

- A1 修正 EXT/p4-route-a/a1/S1_v4e_b01_fix_report.md 中“仅显式 --allow-code-delta 即可放行”的措辞，明确 exploratory/legacy 前置条件（A5 m02）。
- A4 更新 S1 需求矩阵：phase4 M01=OPEN_UNTIL_S0-7→CLOSED_AFTER_PHASE4C、M02/M04=CLOSED、B01 映射到 R-V4-11；合同 v1.5/执行计划 v1.6 同步“确证包禁止 delta 逃生”。
- 文档不得声称 S1 已放行；S1_RUN 仍为 NOT_APPROVED。

## R-V4-11-04 S0-7 重生成（新 code_sha）

- 修复改变 meta_learning/*.py → package_code_sha 改变 → S0-6 的 code_sha 失效；必须在 commit J 的干净 detached worktree 生成 S0-7 确证包：run_id `p4ra-s0-7-freeze-<UTC>Z`；git_sha=J；code_sha=J 的 package_code_sha()；5 split/计数/holdout_seed 20261106/family_fingerprint a1f9462c…/split_hash cd597d01…/radius 0.64 与 S0-6 相同；9 payload + README + SHA256SUMS；determinism 两独立进程；final_verify 全 PASS；physical=0。
- S0-6 标 SUPERSEDED_LEGACY 只读；旧包（S0-2..S0-6、M2/M5/M6）一律只读。
- S0-7 由 Lead 入库 commit K；A2 readiness v4f、A3 审计、A5 phase4c 均绑定同一 S0-7（run_id/SHA256SUMS sha/code_sha/路径）。

## R-V4-11-05 放行链（不放宽）

A1 修复 → Lead commit J（含本裁定）→ A1 生成 S0-7 → Lead 入库 commit K → A2 readiness v4f → A3 审计 J/K/S0-7/readiness → A5 phase4c 终审（含 B01 负控复现、947+ tests、真实 runner e2e）→ A5 `APPROVE_FOR_S1_RUN` → Lead 书面授权（显式绑定 S0-7 路径/SHA256SUMS/run_id/15 片/3.5h 上限）→ A2 启动 15 片 21,000。

## R-V4-11-06 边界（不变）

physical_call_count=0；RCAIDE/SU2/VSPAERO/WaveDrag LOCKED；不合并 main；不新开 PR；仅 Lead 写 GitHub；旧冻结件只读；A5 不得以“书面 deviation”替代修复（A5 已明确不建议）。
