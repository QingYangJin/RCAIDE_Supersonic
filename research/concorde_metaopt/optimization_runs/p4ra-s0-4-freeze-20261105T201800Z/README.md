# P4 路线A S0-4 正式冻结包（v4c 确证版，零物理）

- run_id：p4ra-s0-4-freeze-20261105T201800Z
- created_utc：2026-11-05T20:18:00+00:00
- git_sha：3c1f6352189b9f6ffb791c2b81557f9dcd96f278（commit C）
- code_sha：9c2a6ade3aff9dc3b4f60f9910253b1a21ee7a1153c697a58a35e01adaf5a197（commit C 干净 detached 工作树重算 = family_v3.package_code_sha()）
- family_version：p4ra-family-v4（包层）；任务参数层 p4ra-family-v3 / p4-task-family-v3
- holdout_seed：20261106（仅重播种 meta_test 20 + meta_test_ood 10）
- radius_base：0.64（A2 校准值，CALIBRATED）
- physical_call_count：0（未启动任何 VSPAERO/SU2/RCAIDE/求解器；未评估 meta_test/meta_test_ood）

## 内容

| 文件 | 字节 | sha256（raw） |
|---|---|---|
| tasks.json | 340,443 | 59f66a41f3579b9bb493e94d59e666c3175eb78d11272e77615865beb21334d6 |
| meta_task_split.json | 79,128 | 589f77e5ae3186c7705f6e0a8f5b4bdda954cb6a8eef91154d4cc3fb0767a31c |
| v3_isolation_report.json | 4,170 | bb073cd860efd735448e0e10a63b3e5b8e0108f5cc18a75edea6a4adc3f13693 |
| frozen_family.json | 10,259 | 06126715a234ce56fa1698c1ce2854f00a48fa00d193190b3c8b347ac5ce8f37 |
| preregistration.json | 12,368 | 7e2fafc081398553732037244669a7ca17e821b6650f258fea5a44bdf4833f82 |
| budget_fairness_report.json | 64,723 | 06b33039caec7c9e52a0d1a156bb70e2681fffaf8a7256a78a4c844a95b0cef7 |
| digest_manifest.json | 2,332 | 348689bbe64c253c4d0dcefe7e101c1963704620b269f1aa609253ff1cc06a9e |
| freeze_summary.json | 7,217 | 2ef1b6a21614088323fb18fbb5605c50fbc8f86cbb5678687bd0a10da0768312 |
| determinism_report.json | 3,297 | 899c280153bbe77a7f32c606f9a2ae71d5a3c0a0bc803c380af8a0f0208ba13f |

另含 SHA256SUMS.txt（本目录 9 个 payload JSON 的 raw sha256，9/9 已复核；determinism_report 亦在内）。全部负载 raw 与入库 blob 逐字节相同；本包生成于 LF 环境，无 CRLF→LF 双形态问题。

## 生成方式与确定性

- 在 commit C（3c1f635）的干净 detached 工作树中，用 <EXT>/p4-route-a/a1/s0_4_freeze_official/s0_4_freeze.py（sha256 f6273e469870196a4c6a97ea5c842d2cdd29fd958aa4ff7a169a129f62746d01）以同一 run_id/git_sha/code_sha/radius_base 生成两遍（run1、run2，两个独立进程）。
- 6 个内容载荷（tasks/split/isolation/frozen/prereg/fairness）逐字节一致；determinism_report 记录 schema p4ra-s0-4-determinism-report-1、status=PASS、all_content_payloads_byte_identical=true、rerun_count=2、independent_processes=true、6/6 file identical。
- finalize 后 run1/run2 最终 9 个文件逐字节一致；final_verify_report.json（sha256 47efffc6a882a9bf24db6d75679bb5c719e2127d7b745115a582c17396b59b4f）15/15 检查 PASS、failed=[]。
- determinism_report.json 已进入 digest_manifest.json（artifacts）、freeze_summary.json（artifacts + orchestration 的 determinism_report_sha256 / determinism_report_canonical_sha256）与本目录 SHA256SUMS（R-V4-08-05 m03 关闭）。
- 关键不变量：family_version=p4ra-family-v4、family_id=F-QE-feasible-v3、family_fingerprint=a1f9462c35ea641d0559485354c63b47eec2e6fb4696e86f94efa1f3d19daf2e、split_hash=cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae（与 S0-3 相同）、split counts 60/20/20/10/10（120 任务）、prereg_digest=2ea60ba7f903978407e6d156e7b3f390dbd70bf759725152327be15487a7bd8f、analysis_plan_digest=5222af0dacd08c6cd37e40f7308b12347e67e19abbbd9fa4b5aef0a41430f0fa、frozen_family stored(canonical) sha256=18d5d62ee84ebe713881c1493ce832ac5198fc538efd91d14ef72bb8158d9e58、preregistration stored(canonical) sha256=6103f265c3e96addb94e176e05bf62bbde1e97a44844dfaf7cd3274f808bbdf4。
- confirmatory_eligible=true（frozen_family 与 preregistration 双处）；prereg 含合同 §7 的 20 个必填字段与 v4c 三块（holdout_package / c5_policy / structural_identifiability）；holdout_package.run_id 等于本包 run_id、package_path 为本仓库相对路径、frozen_family_sha256 绑定上述 stored sha。

## v4c 相对 S0-3 的变化边界

- tasks.json、meta_task_split.json 与 S0-3 逐字节相同（tasks 59f66a41…、split 589f77e5…）；family_fingerprint、split_hash、radius_base、split counts、holdout_seed 均不变。
- 变化仅限：prereg 增加 v4c 三块与 Holm 唯一族文本（prereg_digest 2ea60ba7…、analysis_plan_digest 5222af0d…；S0-3 为 aa806767… / 37eee53c…）；frozen_family/preregistration 对应出现新字节与 stored sha；freeze_summary 的 run_id/git_sha/code_sha/时间戳与 calibration note；determinism_report 进入 payload 链；隔离报告登记 holdout 证据。
- 旧 S0-3/S0-2/M2/M5/M6 冻结件只读保留，未被本包修改；S0-2/S0-3 在 v4c 下仅可作为 exploratory legacy 输入，formal 入口会 fail-closed 拒绝。

## 隔离

- v4 holdout 30 个 task_fingerprint 与 v3 官方包 120 个 task_fingerprint 交集 0（PASS，SUBSTANTIVE）。
- 本包 120 个 task_id 与 legacy M2/M5/M6 280 个 task_id 交集 0（PASS，SUBSTANTIVE）；legacy 侧无 task_fingerprint，故指纹交集判 NOT_DETERMINABLE，不伪称已验证。

## 边界（不构成放行）

- 本冻结包不是 S1 formal 放行；A5 phase4 给出 APPROVE_FOR_S1_RUN 且 Lead 书面授权前，禁止启动 21,000 formal run（15 分片、全合成、physical=0）。
- 正式工件必须由 A2 基于本包在干净树中、以默认参数（maml 200 steps / pretrain 50 steps）重建并冻结 sha；任何早期诊断工件不得进入正式 run。
- 本包生成后不得再修改 research/concorde_metaopt/meta_learning/*.py，否则 code_sha 漂移将使本包失效并须重生成。
- 物理调用保持 0；RCAIDE/SU2/WaveDrag 保持 LOCKED；不合并 main、不新开 PR。
- 复现入口：<repo>/research/concorde_metaopt/meta_learning/family_v3.py 与 <EXT>/p4-route-a/a1/s0_4_freeze_official/s0_4_freeze.py；证据原件在 <EXT>/p4-route-a/a1/s0_4_freeze_official/（run1/run2、determinism/final_verify 报告）与 S0_4_official_freeze_report.md（sha256 ace6b86d68ed226ea00fa247d93c7574fbc57e9dc38ef9c6e2d0aaa6d4fef202）。
