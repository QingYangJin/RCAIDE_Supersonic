> **PROVENANCE（恢复声明）**：本回执由 A5 会话转录于 2026-11-10 工作区丢失后重放重建；原工作树与 P0/P1 真实证据已不可恢复，文中旧 SHA 无法在本机复核。历史签署结论不再构成对真实数据的当前有效签署；P1 重跑后以新 verdict 为准。

# A5 任务回执：D-REAL-001 独立复核（issue #9，2026-11-10）

- 任务：共享任务 task-10（D-REAL-001 A5 独立只读复核），角色 a5-review。
- 工作树：D:\RCAIDE\_recovery\a5\sandbox2；分支：research/dreal001-a5-review；基线 commit 683a868。
- 本地提交：32ba263140d98083532e0de5a0a3208724bf799f（交付件）＋本回执所在提交。未 push，未合并 main，未改写任何历史或冻结产物。
- **physical_call_count = 0**：本轮未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag/任何真实求解器；A5 侧 solver_starts_by_a5 = 0。
- 结论性质：本轮为只读审计与框架交付，P0/P1/P2 全部 NOT_ISSUED；A5 未对任何被审提交签 PASS，不以提交消息替代复现。

## 1. 交付文件

审计代码与测试：
- research/concorde_metaopt/reviews/dreal001/dreal_audit.py（只读审计脚本，纯 stdlib；A01–A13、B00/B01、C01–C03；--dnext-root/--out/--md；缺根退出码 3，存在 FAIL 退出码 2）。
- research/concorde_metaopt/reviews/dreal001/test_dreal_audit.py（11 项 pytest 单测）。

审查文档：
- docs/reviews/dreal001_a5_audit_framework_20261110.md：签署框架、状态语义、三层结论、门禁判定。
- docs/reviews/dreal001_a5_legacy_defect_transmission_20261110.md：Issue #8 遗留缺陷 T-01…T-08 传导审计 + 治理文档审查 G-01…G-09 + A4 本轮新发现。
- docs/reviews/dreal001_a5_m0_review_table_20261110.md：M0 合同最低条件 C-M0-01…12 与预启动检查 P-0…P-7（状态 NOT_RUN，A1 无产物）。
- docs/reviews/dreal001_a5_ab_gpu_replay_protocol_20261110.md：独立重放 R-1…R-7、公平性 F-1…F-10、GPU 精度 G-1…G-6、后端≠方法边界。
- docs/reviews/dreal001_a5_audit_sample.json / .md：本轮实跑示例审计输出（机器可读 + 中文渲染）。
- docs/reviews/dreal001_a5_verdict_20261110.json：机器可读 verdict（含每项检查状态、治理发现、限制与复现命令）。

## 2. 实际运行的命令与结果

1) 单元测试：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/reviews/dreal001 -q
   → 11 passed in 0.23s（覆盖：空树 fail-closed、台账守恒 PASS、重复 case 计两物理启动 FAIL、无批准但有台账 FAIL、PERF 旧命名→NOT_VALIDATED、tooling-only 参考量→NOT_VALIDATED、科学参考量不一致→FAIL、SHA256SUMS 逐件 PASS/FAIL、重复成功 FAIL、报告渲染 fail-closed、证据根缺失退出码 3）。

2) 审计实跑（对 D:\RCAIDE\dnext001 下 6 个 wt-real-* 工作树与 D:\RCAIDE-s3-dev 只读证据）：
   & D:\RCAIDE\envs\RCAIDE\python.exe research\concorde_metaopt\reviews\dreal001\dreal_audit.py --out docs\reviews\dreal001_a5_audit_sample.json --md docs\reviews\dreal001_a5_audit_sample.md
   → overall_decision=NOT_VALIDATED；P0=P0_NOT_READY、P1=P1_NOT_READY、P2=P2_NOT_READY；PASS 2 / NOT_VALIDATED 3 / NOT_RUN 12 / FAIL 0。
   - PASS：A01（6 工作树基于基线 683a868，未改写冻结前缀）、A11（13 个 D-REAL 代码文件未引用 S3 缺陷路径/成本口径符号）。
   - NOT_VALIDATED：A07（PERF_20261110_A4_01 命名不符合治理 §3，已作为已批准工具批次记例外，需 Lead 书面确认）、A13（仅 1 个 PERF/探针 .vspaero，自建最小翼，不计科学 TaskSpec 比对）、C03（仅文本、无结构化 summary，三层结论无法机器核验）。
   - NOT_RUN：A02/A03/A04/A05/A06/A09/A10/A12/B00/B01/C01/C02（A1–A3 产物与台账尚未交付）。

## 3. 关键审计结论（细节见文档）

- S3 遗留缺陷已逐条给出“证据 → 传导风险 → 新阶段检查 → 门槛 → 当前状态”；其中 A5 M2R 被 A7 替代、A3 独立仓库守护崩溃缺独立结论两项为 blocker 级治理问题，本阶段要求 A5 自身签署必须落盘。
- 治理文档需修订项：G-02（labels_visible_to_arm 语义，P2 前 blocker）、G-04（approval schema 无校验）、G-05（ENV_SMOKE 启动无 TOOLING 命名）、G-06（lift_rel_error 容差未定）；G-01 需 Lead 即时书面确认，否则 A07 维持 NOT_VALIDATED。
- A4 本轮新发现：PERF_20261110_A4_01 批准件缺 case_matrix_digest/solver.parallelism/references/stop_conditions；45 次启动台账 solver_attempts.jsonl 未提交，守恒/并发/重启幂等三项 NOT_RUN；探针参考量（Sref=0.282、Vinf=100、Rho=0.002377、ReCref=1e7）属工具环境，严禁进入科学评价数据。
- 三层结论：SOLVER_LOOP_VERIFIED / INTERNAL_AERO_OPTIMIZATION_GAIN / EXTERNAL_PHYSICS_SUPPORTED 均 NOT_RUN，fuel_burn_kg=null。

## 4. 未完成项与风险

- 未完成：P0 实审、P1 数值复核、P2 公平性复核均待 A1/A2/A3 产物与 A4 台账落地后执行；A4 45 次启动一旦提交，A5 将按台账守恒、并发≤批准、重启幂等三项独立复核（脚本 A04/A10/A12 已就绪）。
- 风险：A4 批准件命名与字段缺口若不补，后续批次将无法通过 A07；治理 G-02 若不在 P2 前澄清，标签泄漏判据会误判 BO 正常评价反馈；S3 的 wall_s=0 成本口径若被继承，任何“同预算”结论不可审计。
- 限制：A5 不启动真实求解器；不修改他人 worktree；不代签；所有 PASS 均需附可复跑命令与产物 sha。


---

## R5b 追加：A4 本批 corrections 复核与最终归档（2026-11-10 16:40 CST）

- 对象：A4 commit 58b811d 的 corrections 四件 + 本批最终归档结论；治理基准升级为 v2（wt-real-lead commit 588468e）。
- A5 侧 physical_call_count=0，solver_starts=0；未修改 A4 工作树。

### 命令与结果

1) A5 审计脚本单测（含新增 correction 用例）：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/reviews/dreal001 -q
   → 22 passed（新增：correction 合规 PASS、superseded SHA 被篡改 FAIL、旧批次尝试经 correction 关闭后 A04 PASS）。

2) A4 测试独立复跑（临时副本，不写 A4 树）：
   复制 research/concorde_metaopt/dreal001/perf 与 tests/test_dreal001_r4 到临时根，PYTHONPATH=临时根、PYTHONDONTWRITEBYTECODE=1
   & ...python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r4 -q -p no:cacheprovider
   → 31 passed in 2.02s（与 A4 自述一致）。

3) 审计实跑：
   & D:\RCAIDE\envs\RCAIDE\python.exe research/concorde_metaopt/reviews/dreal001/dreal_audit.py --dnext-root D:\RCAIDE\dnext001 --out docs\reviews\dreal001_a5_audit_sample.json --md docs\reviews\dreal001_a5_audit_sample.md
   → overall=NOT_VALIDATED，P0_NOT_READY / P1_NOT_READY / P2_NOT_VALIDATED，PASS 8 / FAIL 0 / NOT_VALIDATED 6 / NOT_RUN 4。
   → A04 PASS（manifest 矛盾由 correction_001 关闭、旧 attempt_id 由 correction_002 覆盖）；A08 PASS（4 件 correction 原 SHA 与盘上一致、已入独立清单）。

4) correction 复核结论：四件均 VALID（原证据字节与 SHA 未改；索引与 SHA256SUMS_corrections.txt 覆盖全件；旧清单未覆盖）。R-A4-01/02 关闭，R-A4-03/06/07 关闭为已披露前向修复。

### 新发现（未关闭）

- R-A4-11（FAIL，major）：fig6_resources_and_failures.png 在 gallery_index.json 标为 REAL_DATA，图内把被 Lead 永久禁用的 2130.59 case/分钟写成“并行有效吞吐”，并与 100% 失败率并列。correction_004 只声明 fig_perf_throughput 未生成，未覆盖 fig6 内嵌数字；证据不可改写，需 A4 追加 correction_005 撤回该图或 Lead 回执明文禁止引用并标注撤回。A5 不签该图。
- R-A4-12（FAIL，minor）：figures/fig_perf_throughput.png 实际存在且与 fig6 字节相同（SHA 1b606894…），未登记 gallery；A4 消息“未生成”在文件层面不准确。

### 本批最终结论

- 批次运行状态：FAIL_STOPPED_ARCHIVED_NOT_RUN（36 次批次未启动，剩余 37 次不结转）。
- 证据完整性：CLOSED_WITH_CORRECTIONS；图件完整性：FAIL_OPEN。
- overall=FAIL，pass_signed=false；三层结论全部 NOT_RUN，fuel_burn_kg=null。
- 结论文件：docs/reviews/dreal001_a5_a4_final_verdict_20261110.json；详细复核：docs/reviews/dreal001_a5_a4_amendment_review_20261110.md 第 9 节。

### 未完成项与风险

- P0 实审待 A1 产物（TaskSpec/冻结/TaskSpec 合同）；ENV_SMOKE 台账（1 次启动）落地后按 A04/A07/A12 复核。
- 风险：若 R-A4-11 不由 correction/Lead 裁定关闭，后续 PERF 图件均可能重复“禁用指标入图”的问题；A5 已将“图内数字须逐项对照禁用清单”纳入后续审计人工项。


### R5c 追加：ENV_SMOKE（DREAL001-P0-20261110-01）复核

- 被审证据：A1 r1-geometry 工作树，A1 HEAD c6aa0b4，证据审计时未跟踪；approval SHA 3ffe9c02…、plan SHA 57a14fdc…、台账 SHA e8dcd706…、评价 SHA 201d3ce0…。
- 执行事实：physical_solver_starts=1（A1 执行）、attempt-01、窗口 09:00–09:20Z 内、exit 0、wall 19.281 s、并发峰值 1；internal_solver_cases=32（2 Mach x 8 AoA x 2 Beta，-fs 与 .vspaero 列表合并）。
- 独立复算：q=20483.940233430174 Pa，alpha_match=5.516736998°，D_i=132401.55562456627 N，L 残差 0；B00 28 行 max_rel=3.81e-16。
- 门禁：A04/A07/A12/B00/A13 PASS；A02/A06/A09 NOT_VALIDATED；A03 NOT_RUN。overall=NOT_VALIDATED，P0_NOT_READY，PASS 11 / FAIL 0 / NV 5 / NR 2。
- G-07：按 Lead 与 governance v3 12.10 裁定为 DISCLOSED_PRE_V3_NOT_FAIL；P1 起强制 internal 双口径、StopBeforeRun=1 预检、禁 -fs/-cmd 扫描。
- P1 预注册 v0（commit 6177385）不满足 12.10：CHANGES_REQUESTED；基线内部子案估算 168，另需 refine 余量。
- 结论：ENV_SMOKE_LEDGER_PASS_WITH_CHANGES_REQUESTED；P0_SIGNED=false；本批为 TOOLING，不构成气动/油耗证据；三层结论 solver loop NOT_VALIDATED / gain NOT_RUN / external physics NOT_VALIDATED / fuel null。
- 文件：docs/reviews/dreal001_a5_env_smoke_audit_20261110.md；docs/reviews/dreal001_a5_env_smoke_verdict_20261110.json。
- 命令：pytest research/concorde_metaopt/reviews/dreal001 -q -p no:cacheprovider → 26 passed；dreal_audit.py --dnext-root D:\RCAIDE\dnext001 → 上述计数。
- A5 physical_call_count=0，solver_starts=0；未修改 A1 工作树；未 push。


### R6a 追加：A4 并行评价执行器预复核（commit 1c1067a）

- 审核对象：A4 分支 research/dreal001-a4-perf-figs，commit 1c1067abbad8c8a72bac9f8cf7eff867a1c4227b，基线 3c0bf9b；只审已跟踪内容，未跟踪文件（corrections.py/dry_run.py/inputs.py/perf_runner.py/sampler.py/DRYRUN_R6A_A1_INTERFACE）不在结论内。
- 独立复跑：A4 测试 63 passed（r4+r6，临时副本，PYTHONPATH=临时根）；A5 审计单测 28 passed。
- MOCK 证据：summary SHA 8e351539…、manifest SHA f1e481b2…、verify ok 32 files；但 summary/manifest 与 ledger 均把 8 次 MOCK 尝试写成 physical_solver_starts=8，与 A4 消息“physical_solver_starts=0”冲突（physical_call_count=0 正确）。
- 独立复现 resume 缺陷：模板 GEOM-A 改为 GEOM-B-CHANGED 后 resume 仍 CACHED_SKIP（second starts=1 为累计值、未新增 solver_start、valid=0、cached=1、case_result 仍记录旧 GEOM-A SHA b001f15e…）。
- 主要发现：R-A4R6-01 MOCK 启动指标语义（blocker）；R-A4R6-02 resume 缓存键不含模板/几何/求解器/输入 SHA（major）；R-A4R6-03 REAL 先记账后预检且未调 A1 完整 preflight（blocker for REAL）；R-A4R6-04 manifest 仅覆盖 32 个小文件、case 状态全 UNKNOWN（major）；R-A4R6-05 A1 依赖未固定 commit/SHA、硬编码跨树路径（major）；R-A4R6-06 case/重试目录不隔离（major）；R-A4R6-07 停机条件命名不一致（minor）；R-A4R6-08 评价记录缺物理字段（PERF-only 可接受，P2 不可复用）；R-A4R6-09 MOCK 吞吐 15483.87 永久禁用；R-A4R6-10 测试自洽但固化了错误口径。
- 审计脚本修正：新增 SYNTHETIC_MARKERS/is_synthetic_artifact/row_source_kind，A04/A07/A12 排除 MOCK 台账；A06 识别 backend；同时把 tests/_tmp、_tmp、.pytest_cache 等单测夹具排除出证据索引，避免 A1 并行测试产物被误判为物理台账（曾导致 A04/A07/C02 假 FAIL）。pytest 28 passed；dreal_audit.py → overall=NOT_VALIDATED，PASS 14 / FAIL 0 / NV 3 / NR 1，P0_NOT_VALIDATED / P1_NOT_READY / P2_NOT_VALIDATED。
- 结论：A4 R6a = CHANGES_REQUESTED；pass_signed=false；不放行 REAL 启动；PERF_02 保持 PENDING_APPROVAL。三层结论全 NOT_RUN，fuel_burn_kg=null。
- 文件：docs/reviews/dreal001_a5_a4_r6a_review_20261110.md；docs/reviews/dreal001_a5_a4_r6a_verdict_20261110.json；research/concorde_metaopt/reviews/dreal001/dreal_audit.py；test_dreal_audit.py。
- A5 physical_call_count=0；A5 physical_solver_starts=0；未修改 A4 工作树；未 push。


### R6b 附加：A4 R6a 整改复审（HEAD cfb5759，2026-11-10 17:45 CST）

- 审核对象：A4 分支 research/dreal001-a4-perf-figs，修复主提交 3527015a3058ab09f331df194289a7a417a31399，追加回归提交 cfb575969dd3a225e664ac39b979e43a08046c82（HEAD，未 push，工作树干净）。
- 方法：git archive cfb5759 导出到 A5 工作树临时根，不写 A4 树；PYTHONPATH=临时根、PYTHONDONTWRITEBYTECODE=1 跑 A4 测试；只读重算证据 SHA、逐文件核 manifest、逐 case 读 case_result；A5 未启动任何 solver。

命令与结果：
1) A4 测试独立复跑（r4+r6）：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research\concorde_metaopt\tests\test_dreal001_r4 research\concorde_metaopt\tests\test_dreal001_r6 -q -p no:cacheprovider
   -> 93 passed in 4.74s（R4 36 + R6 57，与 A4 自述一致）。
2) A5 审计单测：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research\concorde_metaopt\reviews\dreal001 -q -p no:cacheprovider
   -> 28 passed in 0.50s。
3) A5 审计实跑：
   & D:\RCAIDE\envs\RCAIDE\python.exe research\concorde_metaopt\reviews\dreal001\dreal_audit.py --dnext-root D:\RCAIDE\dnext001 --out docs\reviews\dreal001_a5_audit_sample.json --md docs\reviews\dreal001_a5_audit_sample.md
   -> overall=NOT_VALIDATED；P0_NOT_VALIDATED / P1_NOT_READY / P2_NOT_VALIDATED；PASS 14 / FAIL 0 / NV 3 / NR 1。

证据 SHA 核验（全部与 A4 声明一致）：
- MOCK_R6A summary 1,180 B B41B1C47DBB7E7C29B221CA1D8F597DDD1A711DBC144932EB10ABF9B43CF5A03，physical 0/synthetic 8。
- MOCK_R6A data_manifest 12,940 B 6121D2ACEB5DBEEB2B503F18C64097942E4430C3B495C7BB2340BB99EC15E414，8 case/56 file/VALID:8。
- MOCK_R6A attempts 23,606 B 97EB774BCAB5528BF2BA917D6E86F52E3CF06F5294B94092D5D6955B8487C32F。
- MOCK_R6B perf_summary 9,570 B 193D597FD0F24C56B8E76641B5DEF9C331AC6AA912C040D5713EC8DE9B64B992，physical 0/synthetic 24/valid 24。
- MOCK_R6B data_manifest 38,115 B 655E039E26CBE6FD102D58F897FB6A633004A7585D83FCBF82B5114E95A83AC3，24 case/168 file/VALID:24。
- MOCK_R6B attempts 71,568 B 12C2C55E4217A1758010F890C5C7FB9F6EDC395A90A4FDF8AB5EFDC8E183673F，48 行=24 start+24 end，physical 行合计 0、synthetic 行合计 24。
- MOCK_R6B evaluations 71,018 B 8FE6077F5C6D2A56BE4F881259EE4A73F8306372932D95B7CD3089FF88396A45，24 条 SOLVED，accounting physical 全 0。
- interface_dryrun 7,645 B 28763DA663FF4C137C5FC0BD42D5C313D77A5B8A4D62F9EFF66069F17FB85E39；input_validation 8,833 B A424F8179EC440099EBEAB5173A2DCA6B2571D99E430EB4E22F5A9B3CBED2AAC。
- manifest 逐文件：168/168 bytes+SHA 一致，0 未列文件；24 个 case_result 全 VALID 且 cache_fingerprint.fingerprint_version=2；evaluations.case_id 集合=manifest.case 集合；无 preflight_failures、无 superseded。

7+1 项复审：
- R-A4R6-01 CLOSED_WITH_RESIDUAL：MOCK physical=0、synthetic 单列已在代码/证据/测试三处成立；残留 F-R6B-01/F-R6B-06。
- R-A4R6-02 CLOSED：CACHE_FINGERPRINT_VERSION=2 覆盖模板逐文件 SHA/size、geometry/solver_config/solver_exe SHA、basename、expected_internal、x12、design_hash；x12 变更测试会重跑并归档旧尝试。
- R-A4R6-03 CHANGES_REQUESTED：预检前置、预检失败不计费已验证；但 A1 完整 preflight 从 perf_runner 批次入口不可达（F-R6B-02）。
- R-A4R6-04 CLOSED：21 类 RAW_SUFFIXES、24 case/168 文件、168/168 SHA 对齐、status_counts VALID:24、unexpected 检测有测试。
- R-A4R6-05 CHANGES_REQUESTED：硬编码已去掉、A1 依赖已记录；但 dirty=true 只记录不拒绝（F-R6B-03），模板父目录推断会覆盖环境变量（F-R6B-02）。
- R-A4R6-06 CLOSED：superseded/<case>-aNN + superseded_index.json，测试验证归档与重跑。
- R-A4R6-07 CLOSED：max_disk_exceeded 统一，internal_cases_mismatch 入 plan/code，测试通过。
- R-A4R6-08 PARTIAL_ACCEPTED_PERF_ONLY：physics 字段已落盘，alpha_deg 仍 null；PERF-only 可接受，P2 复用前必须补齐。

新发现（未关闭）：
- F-R6B-01 major：perf/artifacts.py:168 用数值真值判断 source，台账证明的 0 被写 not_provided；MOCK_R6A/R6B manifest 均如此。
- F-R6B-02 blocker-for-REAL：executor/perf_runner.py:165 固定 a1_plan_path=None，executor/runners.py:336 因此永不调用 A1 solver_runner.preflight；perf_runner.py:161-164 用模板父目录推断 A1 geometry 且覆盖 DREAL001_A1_GEOMETRY_DIR，目录缺模块时启动即失败。
- F-R6B-03 major：interface_dryrun 记录 a1_git_commit=c6aa0b4、a1_git_dirty=true；runners.py:223-245 只记录 dirty，不 fail-closed。
- F-R6B-04 minor：根 summary.json 只代表最后一档（planned 8/valid 8），却含累计 synthetic 24；perf_summary.overall 才是全批 24。
- F-R6B-05 minor：gate_selfcheck plan_sha256_raw=558937fd... 与当前 PERF_02/plan.json 52aa89a9... 不符（改 plan 后未重生成）。
- F-R6B-06 minor：MOCK_R6B manifest 缺 synthetic_attempts；perf_runner.rebuild_manifest 只传 statuses/physical_call_count。

结论：
- overall=CHANGES_REQUESTED；pass_signed=false；real_batch_release=NOT_RELEASED；不签 PASS、不放行 REAL 启动。
- 93 passed 与全部证据 SHA 可复现，说明工程实现与 A4 自述自洽；但 R-A4R6-03/05 未关闭 + F-R6B-01/02/03，REAL 预检链路与 A1 依赖固定未闭环。
- PERF_02 仍 PENDING_APPROVAL / input_status=PENDING_A1_P0，approval 文件不存在，真实 24 starts NOT_RUN；MOCK 吞吐/内存/worker 数字永久禁用。
- 三层结论 SOLVER_LOOP_VERIFIED / INTERNAL_AERO_OPTIMIZATION_GAIN / EXTERNAL_PHYSICS_SUPPORTED 全 NOT_RUN；fuel_burn_kg=null。
- 新纳入模块（perf_runner/inputs/dry_run/sampler/corrections）仅接口/冒烟审阅，不构成逐行 PASS；后续提交必须重新复核。
- 文件：docs/reviews/dreal001_a5_a4_r6a_review_20261110.md 第 7 节；docs/reviews/dreal001_a5_a4_r6a_final_verdict_20261110.json。
- A5 physical_call_count=0；A5 physical_solver_starts=0；未启动 VSPAERO/SU2/Mission/WaveDrag；未修改 A4 工作树或台账；未 push。


## R5d. A1 P0_PASS 申请与 P1 预注册 v1.1 门禁复核（2026-11-10）

- 被审对象：A1 HEAD c72efc4bad066be9e1acf555974f7fbd892a8dc1（分支 research/dreal001-a1-geometry-solver，基线 683a868，工作树干净，未 push）。
- 方法：git archive c72efc4 到 A5 工作树临时根，不写 A1 树；PYTHONPATH=临时根、PYTHONDONTWRITEBYTECODE=1 独立跑 A1 测试；直接 import task_spec.py 调 validate_contract；逐件重算 P0 证据 SHA；A5 审计脚本扫描 6 个 wt-real-*；人工全文审阅 P1 预注册。A5 未启动任何 solver。

命令与结果：
1) A1 测试独立复跑：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research\concorde_metaopt\tests -q -k "dreal001 or geometry" -p no:cacheprovider
   -> 89 passed, 1739 deselected, 1 warning in 7.68s（与 A1 自述一致）。
2) A5 审计单测：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research\concorde_metaopt\reviews\dreal001 -q -p no:cacheprovider
   -> 28 passed in 0.45s。
3) A5 审计实跑：
   & D:\RCAIDE\envs\RCAIDE\python.exe research\concorde_metaopt\reviews\dreal001\dreal_audit.py --dnext-root D:\RCAIDE\dnext001 --out docs\reviews\dreal001_a5_audit_sample.json --md docs\reviews\dreal001_a5_audit_sample.md
   -> overall=FAIL；P0_FAIL / P1_NOT_READY / P2_NOT_READY；PASS 13 / FAIL 2 / NV 1 / NR 2。
   FAIL：A03 design_space_freeze 未冻结；A08 correction_001 缺 §12.7 字段且旧版不可检索。
   NV：C02（P2 未跑）；NR：B01、C01。

P0 结论：
- decision=P0_FAIL；pass_signed=false；p0_pass_issued=false。
- F-ENV-02/03/04/07 四项全部 CLOSED；但 P0-B1（12D 未冻结）为 blocker，P0-F-02（correction 合规/追溯）为 major FAIL；P0-F-03（TaskSpec hash_scope）、P0-F-04（design_hash 口径）、P0-F-05（CM 语义）为 major CHANGES_REQUESTED；P0-F-06 minor 披露。
- 关键证据：design_space_freeze.json 38,402 B SHA256 80f547c02941b3a2ce4146ce01f47edcadbd5fcc40c61972f8d824abe798401d；data_manifest 27,241 B 095e40d3…；evaluations 17,987 B d1307abd…；evaluation_summary 3,960 B ee64455d…；batch_summary 5,018 B 0322d634…；correction_001 1,690 B 40e19c13…。
- 文件：docs/reviews/dreal001_a5_p0_review_20261110.md；docs/reviews/dreal001_a5_p0_verdict_20261110.json。

P1 v1.1 结论：
- 预注册文件 14,753 B SHA256 d919a2c5721accedc08b8d5d4d2a51d07326f28eaf81e02ea035d2b16de72f32。
- G-P1-PRE=CHANGES_REQUESTED；P1_PREREG_APPROVED=false；P1 窗口不得开启。
- 数字层通过：23 expected starts / 26 max；175 expected internal / 196 max；24x49 P1-02c；7 alpha [-2,0,2,4,6,8,10]；禁 -fs/-mach/-alpha/-beta；StopBeforeRun=1；refine<=2。
- 4 项阻断/偏离：X1 production 面自相矛盾（thin production vs E1 thick production）；X2 S2 写 thick 三档密度但 P1-04 只有单密度；X3 refine 4×7=28 与 max 196=175+3×7 矛盾、S5 actual>expected 会停合法 refine；X4 P1-05 Mach 1.8/2.0/2.2 与治理 1.8/2.02/2.2 偏离需 Lead 豁免。另 X5 清单计数 30 vs 实际 35 ID。
- plan.json/approval.json/preflight 尚未创建，SHA 链后三环 NOT_RUN。
- 文件：docs/reviews/dreal001_a5_p1_prereg_review_20261110.md；docs/reviews/dreal001_a5_p1_prereg_verdict_20261110.json。

未完成项与风险：
- task-11 仍 blocked_by task-6、ready=false，A5 无法 claim；P0 签署无法正式落 task 记录。
- A1 修订 P1 v1.2 与补齐 plan/approval/preflight 后需重新复核，不复用本结论。
- A4 R6 第二轮（5f8e6e8，102 passed）仍未复审，Lead 允许延后。
- P0-B1 未关闭前 P1 不得开启；P0-F-02 未关闭前 P0 不得 PASS。

边界：
- A5 physical_call_count=0；A5 physical_solver_starts=0；未启动 VSPAERO/SU2/Mission/WaveDrag；未修改 A1 工作树或证据；未 push。
- 不替未审阅提交签 PASS；不用提交消息代替复现。

### R6c 追加：A4 R6 第二轮复审（HEAD 5f8e6e8，2026-11-10 18:25 CST）

- 对象：A4 分支 research/dreal001-a4-perf-figs，HEAD 5f8e6e83c3a1d76055d950aae2ee4e537c38902e（相对 cfb5759 为 65 files、+1,451/−613，工作树干净，未 push）。
- 方法：git archive 到 A5 工作树临时根，两种 EOL 口径独立复跑 A4 的 test_dreal001_r4 + test_dreal001_r6；只读核验新增 MOCK/DRYRUN 证据 SHA；未写 A4 树、未启动 solver。

命令与结果：
1) 默认导出（继承 A4 core.autocrlf=true）：
   git -C D:\RCAIDE\dnext001\wt-real-a4-perf-figs archive 5f8e6e8
   pytest research/concorde_metaopt/tests/test_dreal001_r4 research/concorde_metaopt/tests/test_dreal001_r6 -q -p no:cacheprovider
   -> 99 passed, 3 failed in 5.78s。
2) 规范 LF 导出：
   git -c core.autocrlf=false -C D:\RCAIDE\dnext001\wt-real-a4-perf-figs archive 5f8e6e8
   -> 101 passed, 1 failed。
3) A4 自述 102 passed 只在 A4 本地混合 EOL 工作树成立；任何统一 checkout 口径都不能复现 102。

六项整改复核：
- F-R6B-01 CLOSED：manifest physical_solver_starts=0/source=ledger_zero，extra.synthetic_attempts=24。
- F-R6B-02 CLOSED（代码/测试层）：perf_runner.py:54 resolve_a1_dependency，a1_plan_path 缺失即 SystemExit/BackendNotReady；新增 A1 preflight 调用测试通过；真实批次仍 NOT_RUN。
- F-R6B-03 CLOSED（代码层）：allow_dirty_a1 默认 False，dirty=true 拒绝；例外须 run_config 记录 + digest；verify_dependency 比对 commit/逐文件 SHA。
- F-R6B-04 CLOSED：perf_summary root_summary_scope=LAST_LEVEL_ONLY + root_summary_note。
- F-R6B-05 CLOSED：gate_selfcheck plan_sha256_raw=52aa89a9... 与当前 PERF_02 plan 一致；ok=false、issues 10 项。
- F-R6B-06 CLOSED：manifest extra.synthetic_attempts=24；attempts 24 start + 24 end，physical 行合计 0。

新发现（未关闭）：
- F-R6C-01（major）：.gitattributes 的 runs/** -text 不覆盖 dreal001/executor/runs 与 dreal001/perf/runs；146/284 件证据的工作树字节与 git 规范内容 SHA 不同（executor 140/252、perf 6/32）。公布的 perf_summary 0F916590...、run_config 9547295A...、interface 2EFA0DBA...、input C6250AA2...、gate 4D7AE0B7... 均为工作树 CRLF 哈希，规范内容分别为 DA64102B...、0A4C8700...、E3C83012...、9390B8F3...、3BC8AC92...。测试断言又绑定工作树哈希，导致结果随 checkout 口径变化。
- F-R6C-02（major）：correction_005 的 registered_in.sha256=999E2392...67BD1 是工作树 CRLF 哈希（2,960 B、59 CRLF）；规范内容为 2,901 B、86E8A076...9CF0。correction_005 的“旧 gallery 未改写”在 git blob 层面成立，但登记的 SHA 不能由仓库内容复核；test_correction_005...:131 把本地口径固化进测试。
- 整改方向：新增覆盖嵌套 runs 的 .gitattributes（至少 **/runs/** -text），不改旧证据；追加 correction_006 披露 999E2392 为工作树口径、86E8A076 为规范内容 SHA256；测试改比规范/归一化摘要；复核协议固定 git -c core.autocrlf=false archive。

结论：
- A4 R6 第二轮 overall=CHANGES_REQUESTED；pass_signed=false；不签 PASS；real_batch_release=NOT_RELEASED。
- PERF_02 仍 PENDING_APPROVAL、input_status=PENDING_A1_P0、approval 缺失；真实 24 starts NOT_RUN；A1 P0 未签署，A4 REAL 仍不得启动。
- 三层结论全 NOT_RUN；fuel_burn_kg=null；MOCK 吞吐/内存/worker/wall_s 数字继续永久禁用。
- 文件：docs/reviews/dreal001_a5_a4_r6a_review_20261110.md 第 8 节；docs/reviews/dreal001_a5_a4_r6b_final_verdict_20261110.json。

边界：A5 physical_call_count=0；A5 physical_solver_starts=0；未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag；未修改 A4 工作树或台账；未 push；不以提交消息代替复现；不替未审阅提交签 PASS。


---

## R5e 追加：P0 复签与 P1 v1.3 预注册门禁（2026-11-10 19:05 CST）

- 对象：A1 commit 3bc9cc8（分支 research/dreal001-a1-geometry-solver，未 push，基线 683a868）。
- 结论：P0_SIGNED=false（P0 gate=CHANGES_REQUESTED，唯一阻断 P0-B2）；G-P1-PRE=CHANGES_REQUESTED（P1-B1、P1-B2）；p1_prereg_approved=false；P1 不得开启 solver 窗口。
- A5 side physical_call_count=0，a5_solver_starts=0；未修改 A1 或其他工作树；未 push。

### 命令与结果

1) A5 审计单测：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research\concorde_metaopt\reviews\dreal001 -q -p no:cacheprovider
   -> 28 passed in 0.41s。

2) A5 全量只读审计：
   & D:\RCAIDE\envs\RCAIDE\python.exe research\concorde_metaopt\reviews\dreal001\dreal_audit.py --dnext-root D:\RCAIDE\dnext001 --out docs\reviews\dreal001_a5_audit_sample.json --md docs\reviews\dreal001_a5_audit_sample.md
   -> overall=NOT_VALIDATED；P0=P0_PASS（脚本 A01-A13 无 FAIL）；PASS 15 / FAIL 0 / NOT_VALIDATED 1 / NOT_RUN 2。
   说明：脚本 P0 PASS 不等于 A5 签署；人工物理口径复核发现 P0-B2，因此 P0_SIGNED=false。

3) A1 独立测试（git archive 3bc9cc8 到 A5 临时目录，不写 A1 树）：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research\concorde_metaopt\tests -q -k "dreal001 or geometry or design_space"
   -> 183 passed, 1680 deselected, 1 warning in 8.27s。

### P0 结论

- P0-B2（blocker，OPEN）：design_space_freeze.json 的 reference_quantities.Xcg_m=28.287395109126685 是几何全机 CG，但同段 Xcg_interpretation 说 Xcg 是机翼 AC；TaskSpec/ENV_SMOKE .vspaero 实际 X_cg=16.821978259514246。冻结件同时断言两个互斥值，存在把全机 CG 当 X_cg 注入的风险。
  整改：拆成 wing_ac_x_m=16.821978259514246 与 geometry_cg_x_m=28.287395109126685，重新生成 freeze/json 与 SHA 链，A5 重审 A03/A09 后复签；无需物理启动。
- P0 其余条件 VALID：12D 冻结（6cb7647f...）、TaskSpec 三口径（canonical dca981e2...，raw 028086a5...）、几何探针零物理、ENV_SMOKE 1 start/32 internal 台账（e8dcd706...）、data_manifest 30 files/1,440,795 B 与 SHA256SUMS 30/30、correction_001（2,903 B/484d5152...；旧 16,075 B NOT_RETAINED，21,537 B 从 b5dcbbc 可恢复）。
- P0-F-02 CLOSED_WITH_DISCLOSURE；P0-F-03/05 CLOSED；P0-F-04 CLOSED_WITH_NOTE（design_hash 是 12 浮点数组不是 object）；P0-F-06/07 DISCLOSED minor。

### P1 v1.3 结论

- plan：65,409 B，SHA256 0cbd8d93...；prereg v1.3：14,753 B，SHA256 f28c24c6...；数字层 25/26、189/196、25 个 case、8 个 preflight、7 alpha、无 CLI 列表 flag、thin 生产面/thick 负控、P1-05 三 Mach 豁免均已核对通过。
- P1-B1（blocker）：plan.task_spec.path 指向不存在的 A1 工作树绝对路径 ...dreal001/configs/dreal001_task_fixed_cruise_REAL.json；正确文件是 repo 根 configs/dreal001_task_fixed_cruise_REAL.json（6,144 B/028086a5...）；plan.task_spec.raw_sha256=null。根因 p1_plan.py:37 与 :328。整改：repo 相对路径 + raw SHA，重生成 plan，报告新 SHA。
- P1-B2（blocker）：prereg 第 97-100 行“actual > expected or > max 即停”与 S5 第 155-158 行“actual > 189 不是停机条件，只要 <=196 且有批准的 refine”及 S5b 冲突；合法 refine（196）会被误停机。整改：仅超 196/超 26/未批准 refine 才停，>189 仅披露；重算 prereg SHA，重生成 plan。
- 四件套 input SHA 不可复现：ACCEPT_WITH_CONDITIONS（contract_digest 为可复现身份；每次 start 记录实际 .vspgeom SHA + node/element；跨 run 比较用实际网格；S2/S3 先报网格差）。
- 其它 minor：max_refine_attempts_per_design=2 与 max_refine_starts=1 的口径需一句话对齐；plan.preregistration.path 的相对基准需说明；requested_by=null；approval 字段 null 属批准前预期。
- 三层结论：SOLVER_LOOP_VERIFIED 仅 ENV_SMOKE 工具链；INTERNAL_AERO_OPTIMIZATION_GAIN=NOT_RUN；EXTERNAL_PHYSICS_SUPPORTED=NOT_RUN；fuel_burn_kg=null。

### 文件

- docs/reviews/dreal001_a5_p0_signing_review_20261110.md
- docs/reviews/dreal001_a5_p0_signing_verdict_20261110.json
- docs/reviews/dreal001_a5_p1_v13_signing_review_20261110.md
- docs/reviews/dreal001_a5_p1_v13_signing_verdict_20261110.json
- docs/reviews/dreal001_a5_audit_sample.json / .md（重新生成）

### 边界

- A5 未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag；A5 physical_call_count=0；a5_solver_starts=0。
- A1 工作树在评审后出现未提交改动（solver_runner.py 修改；p1_batch.py、test_dreal001_r1_p1_batch.py 未跟踪），本结论只覆盖 commit 3bc9cc8；后续提交必须重审。
- 不以提交消息代替复现；不替未审阅提交签 PASS。


---

## R6c 追加：A4 R6 第三轮（F-R6C-01/02）复核（2026-11-10 19:15 CST）

- 对象：A4 commit 14d0de6（分支 research/dreal001-a4-perf-figs，未 push）；上一轮 5f8e6e8。
- 结论：ACCEPT_WITH_DISCLOSURES；pass_signed=false；不签 PASS；real_batch_release=NOT_RELEASED；PERF_02 仍 PENDING_APPROVAL、真实 0 starts。
- A5 physical_call_count=0、physical_solver_starts=0；未改 A4 树；未 push。

### 命令与结果

1) A5 独立测试（git archive 14d0de6，PYTHONPATH=解包根，PYTHONDONTWRITEBYTECODE=1）：
   默认导出：107 passed, 1 skipped in 5.67s。
   git -c core.autocrlf=false 导出：107 passed, 1 skipped in 5.66s。
   两种统一口径一致；A4 报告的 archive 106+1 与独立复跑差 1 项（F-R6C-04 minor）。

2) 证据字节：
   dreal001/executor/runs + dreal001/perf/runs + gpu/runs 共 322 件，git hash-object --no-filters 与 14d0de6 blob OID 逐件比对：322/322 相等，missing=0、mismatch=0。
   5f8e6e8..14d0de6 共 168 files changed；--ignore-cr-at-eol 后仅 9 件真实内容变化，其余 159 件纯 EOL。

3) corrections：
   correction_006.json 6,068 B / 59C84C6F…E218；correction_index.json 2,725 B / 2996CA4B…5E20（6 件）；SHA256SUMS_corrections.txt 594 B / 41EBC9A1…00D0（6 行）。
   correction_006 targets：gallery_index.json 2,960 B / 999E2392…67BD1；correction_005.json 5,635 B / 2EFD1CAB…98FE。
   旧 3c0bf9b 的 gallery blob 仍为 2,901 B / 86E8A076…9CF0，证明旧证据字节未改写。
   gate_selfcheck plan_sha256_raw = 52AA89A9…CE22 = 当前 PERF_02/plan.json SHA。

### 结论

- F-R6C-01、F-R6C-02 CLOSED_WITH_DISCLOSURE；F-R6B-01..06 维持 CLOSED。
- 新增 F-R6C-03（minor）：correction_006 中文 title/findings 为 mojibake，JSON 与 SHA 字段正常；建议 correction_007 或 README 给 UTF-8 摘要，不改原字节。
- 新增 F-R6C-04（minor）：A4 报告“archive 106 passed +1 skipped”与 A5 独立复跑“107 passed +1 skipped”差 1 项；测试无失败，属计数披露不一致。
- 三层结论全 NOT_RUN；fuel_burn_kg=null；MOCK 吞吐/内存/worker/wall_s 继续永久禁用。
- 文件：docs/reviews/dreal001_a5_a4_r6a_review_20261110.md 第 9 节；docs/reviews/dreal001_a5_a4_r6c_final_verdict_20261110.json。

### 边界

- A5 未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag；未修改 A4 工作树、台账或证据；未 push；不以提交消息代替复现；不替未审阅提交签 PASS。


---

## R5f 追加：A1 P0 复签与 P1 v1.3.1 预注册复签（2026-11-10 19:10 CST）

- 对象：A1 HEAD 85ceb830d3abdf5b5c817402dac6ab5548d15761（分支 research/dreal001-a1-geometry-solver，基线 683a868，工作树干净，未 push）。上一轮 A5 结论 498faca。
- 结论：
  - **P0_SIGNED=TRUE；gate=P0_PASS**；上一轮唯一阻断 P0-B2（freeze 的 Xcg_m 把机翼 AC 与几何全机 CG 混为同一字段）CLOSED；F-ENV-02/03/04/07 全部 CLOSED。
  - **G-P1-PRE=PREREG_PASS；p1_prereg_approved=true**；P1-B1（task_spec 路径/raw SHA）、P1-B2（actual>expected 误停批）均 CLOSED。
  - 不签 P1 执行/SOLVER_INTERNAL_PASS；P1 首启仍需 Lead approval.json；三层结论仍 NOT_RUN；fuel_burn_kg=null。
- A5 physical_call_count=0、a5_solver_starts=0；未修改 A1 或任何其他工作树；未创建 approval.json；未 push。

### 命令与结果

1) A1 测试（git archive 85ceb83 到 A5 临时根，PYTHONPATH=临时根，PYTHONDONTWRITEBYTECODE=1）：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests -q -k "dreal001 or geometry or design_space" -p no:cacheprovider
   → **202 passed, 1680 deselected, 1 warning in 10.94s**（与 A1 自述一致）。

2) A5 审计单测与审计：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/reviews/dreal001 -q -p no:cacheprovider
   → **28 passed in 0.60s**。
   & D:\RCAIDE\envs\RCAIDE\python.exe research\concorde_metaopt\reviews\dreal001\dreal_audit.py --dnext-root D:\RCAIDE\dnext001 --out docs\reviews\dreal001_a5_audit_sample.json --md docs\reviews\dreal001_a5_audit_sample.md
   → overall=NOT_VALIDATED；**P0=P0_PASS**、P1=P1_NOT_READY、P2=P2_NOT_READY；PASS 15 / FAIL 0 / NOT_VALIDATED 1 / NOT_RUN 2。

3) 关键字节与 SHA（A5 本机重算）：
   - design_space_freeze.json：40,432 B / **79b36591acee3e298c4d7ff761d8a41b2037897141bb5306819a954046d11e5f**；wing_ac_x_m=16.821978259514246、geometry_cg_x_m=28.287395109126685、无 Xcg_m 键；差 11.465416849612439 m。
   - freeze 配置源：56503a5512bb9d75656d1a0913936fc7505903ae5b46f1e0fa477ef3165feef7（未变）。
   - TaskSpec：6,144 B / 028086a56f466c1639432218f6928deb6d479160a13db597fef1aa7284e1f0f7。
   - P0 approval：4,337 B / 3ffe9c02a751f523082e284a05c634fc24777b845d45f2d1787c7db70f0166de（未变）。
   - P0 plan：5,473 B / 57a14fdc8908d2c8814db1195c6c777e063e2b6dd041f77ebd256e6886819f95（未变）。
   - P0 ledger：6,858 B / e8dcd706a0ef051687e8d34a344754535bb5c727003dfb683e5fc50dddd3e934（1 start / 32 internal）。
   - P0 evaluations：19,622 B / 6756d61f96d279f4de68059656c4e2307032901c4f5fe14b0689266bc2a293a6。
   - P0 data_manifest：27,241 B / e35719a60dd60f95ac56989a02451c9601c32fe159058430977c7cbc75f8af9c（30 files / 1,440,795 B）。
   - P0 SHA256SUMS：3,787 B / 336dc23aaf848d485f94990bbc1a3ca62fb41181043bf061e2180d4dc27ba5c7（30/30 重算相等）。
   - correction_001：2,903 B / 484d5152f72e9589c04f92099fa0e2ce6eaf0a478663df4d4fb120866e6d7087。
   - P1 plan：65,910 B / **8dcfad573c73b856809a04173778013241c1624692dad0e29a98f0dc3fa85bae**；25 cases / 25 starts / 189 internal；25/26、189/196；max refine 1 / attempts 2；approval.json 不存在；solver_started=false；physical_solver_starts=0。
   - P1 prereg：23,134 B / **3d7bfdc51c6b398c9cbce4d9531431cd02817316091fc6185b87d53b56b0351b**（v1.3.1）。
   - P1 preflight index：10,223 B / 585cd463ae6e89046fc34bec47a5ac86524f431695d31271ca7274e8316f81c6；8 configs 全 all_ok=true；8/8 StopBeforeRun=1、physical 0。
   - 8 个 contract_digest：eb0384eb…ef6c / 2e0c934a…8c4 / 68b631c6…2f05 / 579e794b…39e6 / e7aae821…05b6 / 195e6749…7021 / b46f52e3…803f / 1a0cc956…d1ef（与上一轮一致，未漂移）。

### 仍披露、不阻断的事项

- M-01（minor）：预注册标题/Status 仍写 v1.3，§11.4 与 plan 为 v1.3.1；数值、停批语义和绑定 SHA 均为 v1.3.1，要求下次内容修订时修正标题，不阻断本次签署。
- M-02（minor，ACCEPT_WITH_CONDITIONS）：preflight input_set_sha256 仅 as-prepared，跨 run 用实际 .vspgeom SHA 与 node/element，approval 绑 contract_digest。
- M-03（minor）：P1 请求窗口 18:45–21:30 CST；若审批前耗尽须重新申请，禁止窗口外首启。
- P0-F-06（minor，DISCLOSED）：ENV_SMOKE 36 个 Infinity 与 alpha=0 CDi=0 已披露，P1 统计不得当 0 或删除。
- P0-F-07：P0 plan.status 陈旧，approval SHA 为权威。

### 文件

- docs/reviews/dreal001_a5_p0_resign_review_20261110.md
- docs/reviews/dreal001_a5_p0_resign_verdict_20261110.json
- docs/reviews/dreal001_a5_p1_v131_resign_review_20261110.md
- docs/reviews/dreal001_a5_p1_v131_resign_verdict_20261110.json
- docs/reviews/dreal001_a5_audit_sample.json / .md（已重跑）

### 边界

- A5 未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag；未修改 A1 或其他工作树；未创建/修改 approval.json；未 push；不以提交消息代替复现；不替未审阅提交签 PASS。


## R5h. E6 网格确定性独立复核与 P2 前置（A1 b338544，2026-11-10）

### 结论

- **E6-GAP-01 根因 VALID**：OpenVSP 3.55 thin 网格器对同一 x12 拓扑级非确定，出现 543/472 与 483/418 两族；族内 canonical 节点/面一致，raw SHA 可变。
- **E6 原 12D_ACTIVE NOT_VALIDATED**：仅 W01 Sref 解析响应 VALID；W03/W10/V01/V02 的响应无法与同设计随机网格差异区分。
- **P2 草案“E6 缺口已关闭” FAIL**：必须撤回。
- **P2A-CAL 12 starts CONDITIONAL_COMPLIANT**；**P2a 400 starts CONDITIONAL_COMPLIANT**；G-P2-PRE=CHANGES_REQUESTED；P2 launch 未授权。
- A5 physical_call_count=0、A5 solver_starts=0；未启动 VSPAERO/OpenVSP solver；未写 A1 树。

### 命令与结果

1) A1 测试独立复跑（git archive b338544 到 A5 临时根，PYTHONPATH=临时根，PYTHONDONTWRITEBYTECODE=1）：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests -q -k "dreal001 or geometry"
   → **155 passed, 1741 deselected, 1 warning in 36.82s**。

2) A5 E6 审计单测：
   & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/reviews/dreal001/test_e6_determinism_audit.py -q -p no:cacheprovider
   → **6 passed in 0.06s**。

3) A5 E6 只读审计：
   & D:\RCAIDE\envs\RCAIDE\python.exe research/concorde_metaopt/reviews/dreal001/e6_determinism_audit.py --a1-root D:\RCAIDE\dnext001\wt-real-a1-geometry-solver --out docs/reviews/dreal001_a5_e6_audit_sample.json --md docs/reviews/dreal001_a5_e6_audit_sample.md
   → overall=FAIL；E6-01 VALID、E6-02 VALID、E6-03 NOT_VALIDATED、E6-04 FAIL、E6-05 VALID、E6-06 NOT_VALIDATED、E6-07 VALID。

### 关键证据

- e6_sensitivity.json：50,838 B / 5729dbd084bef984df7873885a5afcc2dbff51a35838ad2a8c218915c35b2149；baseline 483/418 / 58f63bfc...
- determinism_probe.json：2,089 B / c1cc8f32044c649236cb094f18bb44f0f9c5120dc20cbf4290bc0dc7dfd3ece6；baseline 5 次 3×543/472 + 2×483/418。
- determinism_probe2.json：3,404 B / 869afc1c2a310801ef82bdcdf99d739ff0204f456000085bae49e20d596ecaff；fresh baseline 3×543/472。
- roundtrip_multi.json：1,117 B / bca271f2a0e9f7585a645b478c9573680042d8b3d5ffc01e91248f288ad0933f；同进程 5×543/472，raw SHA 4 种，跨进程 NOT_RUN。
- P2 草案：6,679 B / 274252b7529dc0008f7567f5fd90ae3d6ba69d7eea2652ab259b231f680d4344。
- canonical 543 族：node d4aaf416...，face 90a85368...；483 族：node 08ffa96b...，face 912ff6fb...。
- 独立完整重跑 E6 3 次：33 design×run 中 17 拓扑匹配、15 raw SHA 匹配；baseline 依次 483/418、543/472、543/472。

### 文件

- docs/reviews/dreal001_a5_e6_determinism_review_20261110.md
- docs/reviews/dreal001_a5_e6_verdict_20261110.json
- docs/reviews/dreal001_a5_e6_audit_sample.json / .md
- docs/reviews/dreal001_a5_p2_prereg_review_checklist_20261110.md（v2 增补 H-01..H-16）
- research/concorde_metaopt/reviews/dreal001/e6_determinism_audit.py
- research/concorde_metaopt/reviews/dreal001/test_e6_determinism_audit.py

### 边界

- 未重跑 P2A-CAL（无批准），只给预注册合规意见；P2 批准权在 Lead。
- 不签 E6 12D_ACTIVE，不签 P2 预注册，不为未审阅提交签 PASS。
- 不以提交消息代替复现。

## R5g 追加：P1 数值验证复核与签署（被审 A1 HEAD c964e12，2026-11-10 21:05 CST）——由转录恢复

> 本节在恢复时按会话记录补写；原提交 f65fe94 与原始文件字节已随工作区丢失，原 verdict SHA 9e5b0e4b… 不可复核。

### 命令与结果
- 独立复跑 A1 测试（git archive c964e12 临时根，PYTHONPATH=临时根，PYTHONDONTWRITEBYTECODE=1）：pytest research/concorde_metaopt/tests -q -k "dreal001 or geometry" => 151 passed, 1741 deselected, 1 warning in 13.89s。
- & D:\RCAIDE\envs\RCAIDE\python.exe research/concorde_metaopt/reviews/dreal001/p1_result_audit.py --run-dir <A1 P1 run> --out … => overall=PASS，PASS 15 / FAIL 0 / NV 1 / NR 0；p1_verdict=SOLVER_INTERNAL_PASS_WITH_INCIDENT，p1_signed=true。

### 结论
- 权威计数：physical_solver_starts=25、ledger_start_rows=26（1 次 DRY_RUN 假启动 P1-07-W01-plus-a01，由 correction_001 关闭）、internal=189、evaluations=189、case=25、attempt_rows=26。
- E1/E2/E3/E5 VALID；E4 TREND_ONLY（升力匹配口径 CDi 随 Mach 上升、固定 α=6° 口径下降，符号不一致，禁外推，M2.0≠M2.02）；E6 NOT_MEASURED（14 个探针 .vspgeom 全同，V01/V02 敏感性不可判）。
- E2：|CDi(24x49)-CDi(48x97)|/CDi(48x97)=2.4618e-2 > 2% => 生产网格取 48x97；E3：wake8 vs 128 相对差 5.1745e-4 < 2% => 选 8；P1-04c thick 48x97 wall=889.697 s / timeout 900 s（98.9%），P2 须 ≥1200 s 或限网格。
- 三层结论：SOLVER_LOOP_VERIFIED=PASS_WITH_INCIDENT；INTERNAL_AERO_OPTIMIZATION_GAIN=NOT_CLAIMED；EXTERNAL_PHYSICS_SUPPORTED=NOT_CLAIMED；fuel_burn_kg=null。
- 边界：A5 physical_call_count=0、solver_starts=0；不放行 P2 真实批次，P2 预注册仍需 Lead 批准。
