# P4 路线A S0-7 正式冻结包（v4c 确证版，零物理）

- 状态：S0-7 正式（commit J 后重新生成）；依据 R-V4-11-01..04（S1R4b-B01 确证包 code_sha 漂移 fail-closed 后重新生成的确证包；S0-6 标记 SUPERSEDED_LEGACY）
- run_id：p4ra-s0-7-freeze-20261106T024200Z
- created_utc：2026-11-06T02:42:00+00:00
- git_sha：004156c232f31a450f7446c3b280772de47423df（commit J）
- code_sha：7304d32e524b0e1e28b0e83e7a2ed7822ce88fc14963ca4d769098841e6201ed（该干净 detached 工作树 family_v3.package_code_sha() 重算一致）
- family_id：F-QE-feasible-v3；family_version：p4ra-family-v4（包层）；任务参数层 p4ra-family-v3 / p4-task-family-v3
- holdout_seed：20261106（仅重播种 meta_test 20 + meta_test_ood 10）
- radius_base：0.64（A2 校准值，CALIBRATED）
- physical_call_count：0（未启动任何 VSPAERO/SU2/RCAIDE/求解器；未评估 meta_test/meta_test_ood）

## 内容

| 文件 | 字节 | sha256（raw） |
|---|---|---|
| tasks.json | 340,443 | 59f66a41f3579b9bb493e94d59e666c3175eb78d11272e77615865beb21334d6 |
| meta_task_split.json | 79,128 | 589f77e5ae3186c7705f6e0a8f5b4bdda954cb6a8eef91154d4cc3fb0767a31c |
| v3_isolation_report.json | 4,170 | fe80047d2ca75c199791db13d9a9307fb86f81c43c3705dd9539b94741cff74e |
| frozen_family.json | 10,259 | 246729d479918215d05f5828ea594500e8a9c031888585c59c9e3fb2733104c8 |
| preregistration.json | 12,368 | ffd33764aef3f348a3d3076c96963d81afcaa6c95db23797fa1777432a7b9306 |
| budget_fairness_report.json | 64,723 | f2033257c4041d3456f219f09b35828cf6932f0beadbaf0178a644b23e7c72f8 |
| determinism_report.json | 3,297 | dafba4f59eee6554ff527f522e9d68786e8a59c64fad530a0ff13a3c510eee66 |
| digest_manifest.json | 2,332 | 6cd0aa4c17f653525161cc798e76a7af6d148439da180852888c5e66e0a99329 |
| freeze_summary.json | 7,217 | ea1d7931dfd7b172486a19f148dc1a4fa82e6640f00dca1c026cc64e8be98086 |

另含 SHA256SUMS.txt（本目录 9 个 payload JSON 的 raw sha256，9/9 已复核；determinism_report 亦在内）。全部负载 raw 与入库 blob 逐字节相同；本包生成于 LF 环境，无 CRLF→LF 双形态问题。

## 生成方式与确定性

- 在 commit J（004156c232f31a450f7446c3b280772de47423df）的干净 detached 工作树中，用 <EXT>/p4-route-a/a1/s0_7_freeze_prep/s0_7_freeze.py 以同一 run_id/git_sha/code_sha/radius_base 生成两遍（run1、run2，两个独立进程）。
- 6 个内容载荷（tasks/split/isolation/frozen/prereg/fairness）逐字节一致；determinism_report 记录 schema p4ra-s0-7-determinism-report-1、status=PASS、rerun_count=2、independent_processes=true、6/6 file identical。
- finalize 后 run1/run2 最终 9 个文件逐字节一致；final_verify_report.json（sha256 ecee6971718dad53b5e83b45d103bf8bba1b831ed9bc904cd46765290f3c3054）15/15 检查 PASS、failed=[]。
- determinism_report.json 已进入 digest_manifest.json（7 个 artifacts）、freeze_summary.json（artifacts 7 项 + orchestration 的 determinism_report_sha256/determinism_report_canonical_sha256/status）与本目录 SHA256SUMS（9 行；R-V4-08-05/R-V4-09 要求）。
- 关键不变量：family_version=p4ra-family-v4、family_id=F-QE-feasible-v3、family_fingerprint=a1f9462c35ea641d0559485354c63b47eec2e6fb4696e86f94efa1f3d19daf2e、split_hash=cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae（与 S0-3/S0-4/S0-5 相同）、split counts 60/20/20/10/10（120 任务）、prereg_digest=3155de15cd80af9c4cbd37e56f1256e4aaad7bad734ce497871fc0c0a5b23ed2、analysis_plan_digest=5222af0dacd08c6cd37e40f7308b12347e67e19abbbd9fa4b5aef0a41430f0fa、frozen_family stored(canonical) sha256=1cfda5b88ef1679a691c93874a2eaacde5b0c46b0d8cbea15cf789ab83f6b5cb、preregistration stored(canonical) sha256=cba5bfd70b301f4f1fa05dc094b9e3bd32c89b129c4f763a3f386aa70c5538cf。
- confirmatory_eligible=true（frozen_family / preregistration / freeze_summary 三处）；prereg 含合同 §7 的 20 个必填字段与 v4c 三块（holdout_package / c5_policy / structural_identifiability）；holdout_package.run_id 等于本包 run_id、package_path 为本仓库相对路径、frozen_family_sha256 绑定上述 stored sha。

## 与 S0-6 的变化边界

- tasks.json、meta_task_split.json 与 S0-6 逐字节相同（tasks 59f66a41…、split 589f77e5…）；family_fingerprint、split_hash、radius_base、split counts、holdout_seed 均不变。
- 变化仅限：commit J 改变 meta_learning/*.py → code_sha 由 S0-6 的 1f244984ad0bddb09a820076a87caa5df2ca63fcd85f9f149aea3defc12fbd6d 变为 7304d32e524b0e1e28b0e83e7a2ed7822ce88fc14963ca4d769098841e6201ed；git_sha 由 48403e5d7a72a5c077e8f0c6c072c94628087fc3 变为 004156c232f31a450f7446c3b280772de47423df；run_id/created_utc 更新；frozen/prereg 因此出现新字节与 stored sha；determinism/verify 证据重新生成；prereg holdout_package 指向 S0-7 自身。
- S0-6 包按 R-V4-11-01..04 标记 SUPERSEDED_LEGACY（历史只读，不删除、不改写其提交）。

