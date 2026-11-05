# P4 路线A S0-3 正式冻结包（v4 holdout 重播种，零物理）

- run_id：`p4ra-s0-3-freeze-20261105T155925Z`
- created_utc：`2026-11-05T15:59:25+00:00`
- git_sha：`7c1e2ce9eb4aac1725003537fdbaf4a3425be5cb`（commit V4）
- code_sha：`c926653d83a57164b8b3079ea7cf2f8ae944dd92f7a971041d5b87208f67bf9e`（干净 LF checkout）
- family_version：`p4ra-family-v4`（包层）；任务参数层 `p4ra-family-v3` / `p4-task-family-v3`
- holdout_seed：`20261106`（仅重播种 meta_test 20 + meta_test_ood 10）
- radius_base：`0.64`（A2 校准值，CALIBRATED）
- physical_call_count：`0`（未启动任何 VSPAERO/SU2/RCAIDE/求解器；未评估 meta_test/meta_test_ood）

## 内容

| 文件 | 字节 | sha256（raw） |
|---|---|---|
| tasks.json | 340,443 | 59f66a41f3579b9bb493e94d59e666c3175eb78d11272e77615865beb21334d6 |
| meta_task_split.json | 79,128 | 589f77e5ae3186c7705f6e0a8f5b4bdda954cb6a8eef91154d4cc3fb0767a31c |
| v3_isolation_report.json | 4,170 | ce3fdb5f0803bc7ba60857e952684654db9a05359d98be3ebbeb06f2efbd2daa |
| frozen_family.json | 10,209 | 82ec384d3eaa729af682646d01a856464979738d9b3c025d00901c97f16700b9 |
| preregistration.json | 9,972 | f35c12086003a6ad4c217a870db5072c55f58625723f1d9811e4e9f681d2c5f3 |
| budget_fairness_report.json | 64,723 | bca9190ace2a783e2659edc4fd4791469b9bf2011281440f6e2056dc12644570 |
| digest_manifest.json | 2,075 | c4e01551da7b2a98b6a9963d9e8f9c77ec8678e3a99750cb6b8bd884a1699c75 |
| freeze_summary.json | 6,647 | 99bee2c2f88582469dc37e25263a8c5ccdfa01c4060c2b0b55bdbdee09225687 |
| determinism_report.json | 14,370（raw CRLF） | 53e7ecce0c040021bbc72c816716c5e56dbba3831074a4db1a37bf4f6baeea42（raw）；入库 canonical-LF 13,880 B / 33119c0b506a2c68b35daabf75cb2bd76304a4845733e048451c2256f09f1c7c |

另含 `SHA256SUMS.txt`（本目录 8 个 payload JSON 的 raw sha256，8/8 已复核）。8 个 payload 的 raw 与入库 blob 逐字节相同；`determinism_report.json` 在生成机为 CRLF raw，入库后被 git 规范化为 LF（表中同时给出两形态）。canonical-LF 哈希见 `freeze_summary.json` 与 `digest_manifest.json` 的 `stored_sha256` 字段。

## 生成方式与确定性

- 在 commit V4 的干净 detached 工作树（生成前后 `git status` 为空）中，用 `<EXT>/p4-route-a/a1/s1_v4_evidence/make_freeze_v4.py` 以同一 run_id/UTC/git_sha/radius_base 生成两遍（run1、run2，两个独立进程）。
- 8 个 payload 与 SHA256SUMS 逐字节一致；`determinism_report.json` 记录 schema `p4ra-s0-3-determinism-report-1`、status=PASS、`all_payload_files_identical=true`、`rerun_count=2`、`independent_processes=true`、77 项结构校验全 true、`failed_checks=[]`。
- 关键不变量：`family_version=p4ra-family-v4`、`family_id=F-QE-feasible-v3`、`family_fingerprint=a1f9462c35ea641d0559485354c63b47eec2e6fb4696e86f94efa1f3d19daf2e`、`split_hash=cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae`（与 v3 相同）、split counts 60/20/20/10/10（120 任务）、`prereg_digest=aa806767…`、`frozen_sha=6e5b357c04e0e40672560694c1b1ba3fecfdb1fd053789ac566643385e0c2769`、`prereg_sha=0c342934503079b4141401025470c73b235713d757aceef8f7c758c67b93fb50`、`analysis_plan_digest=37eee53c9018fce34e414fa553ad3986a2d1be87d10409bc28e4f697b63588df`。
- **v4 相对 v3 的变化边界**：meta_train 60 / meta_validation 20 / negative_control 10 共 90 个 task_fingerprint 与 v3 官方包逐项相同；meta_test 20 + meta_test_ood 10 共 30 个 task_fingerprint 全部变化；v4 holdout 30 个指纹与 v3 官方包 120 个指纹交集 0（PASS，SUBSTANTIVE）。
- 隔离：v4 120 个 task_id 与 legacy 280 个 task_id 交集 0（PASS，SUBSTANTIVE）；legacy 侧无 task_fingerprint，故 fingerprint 交集判 `NOT_DETERMINABLE`，不伪称已验证。
- 旧 S0-2（v3）/M2/M5/M6 冻结件只读保留，未被本包修改；v3 仅作为 legacy 只读验证路径。

## 边界（不构成放行）

- 本冻结包不是 S1 formal 放行；A5 phase3 给出 `APPROVE_FOR_S1_RUN` 且 Lead 书面授权前，禁止启动 21,000 formal run。
- 正式工件必须用本包在干净树中由 A2 以默认参数（maml 200 steps / pretrain 50 steps）重建并冻结 sha；A1 早期 2/3-step 工件仅诊断，不得进入正式 run。
- 物理调用保持 0；RCAIDE/SU2/WaveDrag 保持 LOCKED；不合并 main、不新开 PR。
- 复现入口：`<repo>/research/concorde_metaopt/meta_learning/family_v3.py` 与 `<EXT>/p4-route-a/a1/s1_v4_evidence/make_freeze_v4.py`；证据原件在 `<EXT>/p4-route-a/a1/s0_3_freeze_official/`。
