# P4 路线A S0-2 正式冻结包（零物理）

- run_id：`p4ra-s0-2-freeze-20261105T072500Z`
- created_utc：`2026-11-05T07:25:00+00:00`
- git_sha：`766a59ce14c9edda7b9174b621eb0d6727bfe1b8`（S0-2 阶段一修复 commit X）
- code_sha：`c929609a1eb4d5c01cc4f94865ebdebb5fa7a1772fe8f4139a411cf7a8414f59`
- radius_base：`0.64`（A2 校准值，CALIBRATED）
- physical_call_count：`0`（未启动任何 VSPAERO/SU2/RCAIDE/求解器）

## 内容

| 文件 | 字节 | sha256（raw） |
|---|---|---|
| tasks.json | 340,295 | 33952fa6818bc6672b1e0f3de35b84ca09ac9d9f3cb07f669c05e33b3baaee7c |
| meta_task_split.json | 78,950 | 0594879bd90fcd9ac765b28aa51ee0dff62869afdb35c43c8fec5d92fffa9fd0 |
| v3_isolation_report.json | 3,463 | 7921f7d4c349cfefd66dc7fd890efeac467828a7a5736bf80e567e4bb85204ba |
| frozen_family.json | 9,689 | 46e94c189ccd0298426eea29f37903587ca4d9c9ea217f3b959df209f995bc9e |
| preregistration.json | 9,809 | 453657ebbe76f5952412a6e56859b464e8cb508f4b7129c4a14c413e4e19da9e |
| budget_fairness_report.json | 64,723 | 834398189899bc3644c6c2eac558b9a1c441d4a5611eac33e01e9ad8deb0dfc6 |
| digest_manifest.json | 2,074 | 68aaa106ac4473a71cb3d43da1c97efddd3ea7f11ec321de1d7390fe897c68dd |
| freeze_summary.json | 6,115 | 1b6309b6d2d385777d701ce4fccaa6d46d82f3e33216c3d45d0a2725436359ad |
| determinism_report.json | 4,948 | 5ea7ff81de087029174a1e88845f79cad471df7f8c517d49608ce560cd1d251e |

另含 `SHA256SUMS.txt`（本目录 9 个 JSON 的 sha256）。canonical-LF 哈希见 `freeze_summary.json` 与 `digest_manifest.json` 的 stored_sha256 字段。

## 生成方式与确定性

- 在 commit X 的干净 detached 工作树（生成前后 `git status` 为空）中，用 `make_freeze.py` 的参数化入口以同一 run_id/UTC/git_sha/radius_base 生成两遍（run1、run2，两个独立进程）。
- 8 个 payload 逐字节一致；`determinism_report.json` 记录 `all_payload_files_identical=true`、`rerun_count=2`、`independent_processes=true`，29/29 结构校验 true、`failed_checks` 空。
- 关键不变量：`family_version=p4ra-family-v3`、`family_id=F-QE-feasible-v3`、`family_fingerprint=e56e6921be6b94e6611a24618a6e331cd7e4417597926d089d71b00da8c1c0c3`、`split_hash=cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae`、split counts 60/20/20/10/10（120 任务）、`prereg_digest=6981f503fd6ea5a9fbe5de2d1825ae8993eb17e9fda5d2ff158e9248d88fd3df`、`analysis_plan_digest=37eee53c9018fce34e414fa553ad3986a2d1be87d10409bc28e4f697b63588df`。
- 隔离：v3 120 个 task_id 与 legacy 280 个 task_id 交集 0（PASS，SUBSTANTIVE）；legacy 侧无 task_fingerprint，故 fingerprint 交集判 `NOT_DETERMINABLE`，不伪称已验证。

## 边界（不构成放行）

- 本冻结包**不是** S1 formal 放行；在 A5 给出 `APPROVE_FOR_S1_FORMAL` 之前，禁止打开 meta_test/meta_test_ood/negative_control 做调参或评估。
- 旧 M2/M5/M6 冻结件未改动；main 未合并；本包不包含外部大文件。
- 复现入口：`<repo>/research/concorde_metaopt/meta_learning/family_v3.py` 与 `<EXT>/a1/s0_2_freeze_official/make_freeze.py`；证据原件在 `<EXT>/a1/s0_2_freeze_official/`。
