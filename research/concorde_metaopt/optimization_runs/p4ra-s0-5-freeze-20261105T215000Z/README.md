# P4 路线A S0-5 正式冻结包（v4c 确证版，零物理）

- 状态：S0-5 正式（commit E 后重新生成）；依据 R-V4-09（A6 analysis 修复后重新生成的确证包；S0-4 标记 SUPERSEDED_LEGACY）
- run_id：p4ra-s0-5-freeze-20261105T215000Z
- created_utc：2026-11-05T21:50:00+00:00
- git_sha：9f2f384e139d2e58ba64c9fb851971b8a8069275（commit E）
- code_sha：25f726f8feaacacbf8351ce987aa774241bee602d502f734d884d86fbea9717a（该干净 detached 工作树 family_v3.package_code_sha() 重算一致）
- family_id：F-QE-feasible-v3；family_version：p4ra-family-v4（包层）；任务参数层 p4ra-family-v3 / p4-task-family-v3
- holdout_seed：20261106（仅重播种 meta_test 20 + meta_test_ood 10）
- radius_base：0.64（A2 校准值，CALIBRATED）
- physical_call_count：0（未启动任何 VSPAERO/SU2/RCAIDE/求解器；未评估 meta_test/meta_test_ood）

## 内容

| 文件 | 字节 | sha256（raw） |
|---|---|---|
| tasks.json | 340,443 | 59f66a41f3579b9bb493e94d59e666c3175eb78d11272e77615865beb21334d6 |
| meta_task_split.json | 79,128 | 589f77e5ae3186c7705f6e0a8f5b4bdda954cb6a8eef91154d4cc3fb0767a31c |
| v3_isolation_report.json | 4,170 | a00d8f15b2a65c9b3bfaa04badb1ee696160d410f988f73719dc009af0f6ef21 |
| frozen_family.json | 10,259 | cb434363c79d8561b326629b7aea9c4c6fdb9b8efc3d8db9361d9486a2a4e402 |
| preregistration.json | 12,368 | 0894c2e4ca90cab55692f2dfcc3d2ec09ff3908c6000da418ab6fe8e05ca4464 |
| budget_fairness_report.json | 64,723 | 92ac06f57c8a554eacded7187bd63cf2f2b7de0063fae82092633db93cd6ce6d |
| determinism_report.json | 3,297 | 536e925a6d2eea3190d5ec5bf8b361fda6f022af45d2c5107da63b29318ca9f6 |
| digest_manifest.json | 2,332 | b19fb7e84bc3f2b040924e79222f59362918ead5828cf3cb85b210c67281ae57 |
| freeze_summary.json | 7,217 | ce44a60027946b8ca2d42f5d0d264b6c18b7743891e273b86d7289b6e5e06e32 |

另含 SHA256SUMS.txt（本目录 9 个 payload JSON 的 raw sha256，9/9 已复核；determinism_report 亦在内）。全部负载 raw 与入库 blob 逐字节相同；本包生成于 LF 环境，无 CRLF→LF 双形态问题。

## 生成方式与确定性

- 在 commit E（9f2f384e139d2e58ba64c9fb851971b8a8069275）的干净 detached 工作树中，用 <EXT>/p4-route-a/a1/s0_5_freeze_prep/s0_5_freeze.py 以同一 run_id/git_sha/code_sha/radius_base 生成两遍（run1、run2，两个独立进程）。
- 6 个内容载荷（tasks/split/isolation/frozen/prereg/fairness）逐字节一致；determinism_report 记录 schema p4ra-s0-5-determinism-report-1、status=PASS、rerun_count=2、independent_processes=true、6/6 file identical。
- finalize 后 run1/run2 最终 9 个文件逐字节一致；final_verify_report.json（sha256 fc84ce06a4e1c93aac7fb28f24ad0c74d63d35dbeb6a3638272fb31523eb9cb1）15/15 检查 PASS、failed=[]。
- determinism_report.json 已进入 digest_manifest.json（7 个 artifacts）、freeze_summary.json（artifacts 7 项 + orchestration 的 determinism_report_sha256/determinism_report_canonical_sha256/status）与本目录 SHA256SUMS（9 行；R-V4-08-05/R-V4-09 要求）。
- 关键不变量：family_version=p4ra-family-v4、family_id=F-QE-feasible-v3、family_fingerprint=a1f9462c35ea641d0559485354c63b47eec2e6fb4696e86f94efa1f3d19daf2e、split_hash=cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae（与 S0-3/S0-4 相同）、split counts 60/20/20/10/10（120 任务）、prereg_digest=54375c48b3274b3990964b5f3a5e6a2b8056179c615a26913d22376f61b63435、analysis_plan_digest=5222af0dacd08c6cd37e40f7308b12347e67e19abbbd9fa4b5aef0a41430f0fa、frozen_family stored(canonical) sha256=d30e7e523c7728f32af94daf5c6092d174c66d02f5d16507eb1d17164a6a67c7、preregistration stored(canonical) sha256=6fa5ce717339e6d25e1c6d39825a9e440ae89281445a852e755f4edd3acafe72。
- confirmatory_eligible=true（frozen_family / preregistration / freeze_summary 三处）；prereg 含合同 §7 的 20 个必填字段与 v4c 三块（holdout_package / c5_policy / structural_identifiability）；holdout_package.run_id 等于本包 run_id、package_path 为本仓库相对路径、frozen_family_sha256 绑定上述 stored sha。

## 与 S0-4 的变化边界

- tasks.json、meta_task_split.json 与 S0-4 逐字节相同（tasks 59f66a41…、split 589f77e5…）；family_fingerprint、split_hash、radius_base、split counts、holdout_seed 均不变。
- 变化仅限：commit E 改变 meta_learning/*.py → code_sha 由 S0-4 的 9c2a6ade3aff9dc3b4f60f9910253b1a21ee7a1153c697a58a35e01adaf5a197 变为 25f726f8feaacacbf8351ce987aa774241bee602d502f734d884d86fbea9717a；git_sha 由 3c1f6352189b9f6ffb791c2b81557f9dcd96f278 变为 9f2f384e139d2e58ba64c9fb851971b8a8069275；run_id/created_utc 更新；frozen/prereg 因此出现新字节与 stored sha；determinism/verify 证据重新生成；prereg holdout_package 指向 S0-5 自身。
- S0-4 包按 R-V4-09 标记 SUPERSEDED_LEGACY（历史只读，不删除、不改写其提交）。

