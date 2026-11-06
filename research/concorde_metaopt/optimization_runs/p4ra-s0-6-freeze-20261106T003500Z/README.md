# P4 路线A S0-6 正式冻结包（v4c 确证版，零物理）

- 状态：S0-6 正式（commit G 后重新生成）；依据 R-V4-10-06（B01 pair 标签+M01 code_sha 修复后重新生成的确证包；S0-5 标记 SUPERSEDED_LEGACY）
- run_id：p4ra-s0-6-freeze-20261106T003500Z
- created_utc：2026-11-06T00:35:00+00:00
- git_sha：48403e5d7a72a5c077e8f0c6c072c94628087fc3（commit G）
- code_sha：1f244984ad0bddb09a820076a87caa5df2ca63fcd85f9f149aea3defc12fbd6d（该干净 detached 工作树 family_v3.package_code_sha() 重算一致）
- family_id：F-QE-feasible-v3；family_version：p4ra-family-v4（包层）；任务参数层 p4ra-family-v3 / p4-task-family-v3
- holdout_seed：20261106（仅重播种 meta_test 20 + meta_test_ood 10）
- radius_base：0.64（A2 校准值，CALIBRATED）
- physical_call_count：0（未启动任何 VSPAERO/SU2/RCAIDE/求解器；未评估 meta_test/meta_test_ood）

## 内容

| 文件 | 字节 | sha256（raw） |
|---|---|---|
| tasks.json | 340,443 | 59f66a41f3579b9bb493e94d59e666c3175eb78d11272e77615865beb21334d6 |
| meta_task_split.json | 79,128 | 589f77e5ae3186c7705f6e0a8f5b4bdda954cb6a8eef91154d4cc3fb0767a31c |
| v3_isolation_report.json | 4,170 | ee10aba9710cc72dd7e315552eeef7a842188d68b39453641dfc413d3d678b13 |
| frozen_family.json | 10,259 | 28ac2fb1b7420b7d375a0283ef7d17749e3f2a3e59e9603d8c36738e0ea6f4e8 |
| preregistration.json | 12,368 | 6c6db6f7f1629473be0c947b6373e041d066faa176fa30ba9497263698efe859 |
| budget_fairness_report.json | 64,723 | 8d6e35442cf097bcf07836729f6a2c6e5172a35060fb8a1c3c87d9452fe347e5 |
| determinism_report.json | 3,297 | d9b5dea04ae647046e718ef48425619edb66a7d1df0d76fa2dd64360dea53964 |
| digest_manifest.json | 2,332 | 011a03a54726101cd87bf1a158e279f45366cfd67c4d3a8c27503b73b102b70a |
| freeze_summary.json | 7,217 | a786d1ebc072fc1a2b042b46cd77cbe6d2aed7def2a619ff7457fdf21eebf687 |

另含 SHA256SUMS.txt（本目录 9 个 payload JSON 的 raw sha256，9/9 已复核；determinism_report 亦在内）。全部负载 raw 与入库 blob 逐字节相同；本包生成于 LF 环境，无 CRLF→LF 双形态问题。

## 生成方式与确定性

- 在 commit G（48403e5d7a72a5c077e8f0c6c072c94628087fc3）的干净 detached 工作树中，用 <EXT>/p4-route-a/a1/s0_6_freeze_prep/s0_6_freeze.py 以同一 run_id/git_sha/code_sha/radius_base 生成两遍（run1、run2，两个独立进程）。
- 6 个内容载荷（tasks/split/isolation/frozen/prereg/fairness）逐字节一致；determinism_report 记录 schema p4ra-s0-6-determinism-report-1、status=PASS、rerun_count=2、independent_processes=true、6/6 file identical。
- finalize 后 run1/run2 最终 9 个文件逐字节一致；final_verify_report.json（sha256 e42df3380c04a5f485684f7359730da39df7bb3bdd79ebc6555fcc527db95ace）15/15 检查 PASS、failed=[]。
- determinism_report.json 已进入 digest_manifest.json（7 个 artifacts）、freeze_summary.json（artifacts 7 项 + orchestration 的 determinism_report_sha256/determinism_report_canonical_sha256/status）与本目录 SHA256SUMS（9 行；R-V4-08-05/R-V4-09 要求）。
- 关键不变量：family_version=p4ra-family-v4、family_id=F-QE-feasible-v3、family_fingerprint=a1f9462c35ea641d0559485354c63b47eec2e6fb4696e86f94efa1f3d19daf2e、split_hash=cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae（与 S0-3/S0-4/S0-5 相同）、split counts 60/20/20/10/10（120 任务）、prereg_digest=44d6ff8053f63eaba6b8fcced65078f5552679e8f928d81170bcfbb7175d90a1、analysis_plan_digest=5222af0dacd08c6cd37e40f7308b12347e67e19abbbd9fa4b5aef0a41430f0fa、frozen_family stored(canonical) sha256=e5fb8e9878a9ff608a05cc543a69871e194b9f5ddc5ce1cbc3b33bf33c353b89、preregistration stored(canonical) sha256=6162ea079bd9614d0818dc64b04b7bdf055da1c12aab5b26121e41e55ec285f2。
- confirmatory_eligible=true（frozen_family / preregistration / freeze_summary 三处）；prereg 含合同 §7 的 20 个必填字段与 v4c 三块（holdout_package / c5_policy / structural_identifiability）；holdout_package.run_id 等于本包 run_id、package_path 为本仓库相对路径、frozen_family_sha256 绑定上述 stored sha。

## 与 S0-5 的变化边界

- tasks.json、meta_task_split.json 与 S0-5 逐字节相同（tasks 59f66a41…、split 589f77e5…）；family_fingerprint、split_hash、radius_base、split counts、holdout_seed 均不变。
- 变化仅限：commit G 改变 meta_learning/*.py → code_sha 由 S0-5 的 25f726f8feaacacbf8351ce987aa774241bee602d502f734d884d86fbea9717a 变为 1f244984ad0bddb09a820076a87caa5df2ca63fcd85f9f149aea3defc12fbd6d；git_sha 由 9f2f384e139d2e58ba64c9fb851971b8a8069275 变为 48403e5d7a72a5c077e8f0c6c072c94628087fc3；run_id/created_utc 更新；frozen/prereg 因此出现新字节与 stored sha；determinism/verify 证据重新生成；prereg holdout_package 指向 S0-6 自身。
- S0-5 包按 R-V4-10-06 标记 SUPERSEDED_LEGACY（历史只读，不删除、不改写其提交）。

