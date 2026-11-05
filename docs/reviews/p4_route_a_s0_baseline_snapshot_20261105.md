# P4 路线A S0 基线快照与旧工件只读核验报告

> 状态：S0 交付物（Lead 执行 task-186），**不构成阶段放行**。S0 放行需 A5 审阅通过 + A3 只读隔离证明 + Lead 集成裁定。
> 日期：2026-11-05；工作树：本仓库（Git worktree），分支 research/p4-route-a-improvements，HEAD a331639e47015f1d07796e46dbe3f71beb97048c（= origin 同名分支）。
> 依据：Issue #7 D-P4-003 §2 S0/§4、Issue #4 D-12D-006、docs/planning/p4_route_a_stage_improvement_plan_20261105.md（commit a331639e，sha256 9790e3b72a2aaa0ea1b59f9b2a4e1d8830c18160db8b31e52a1ef3afb8a97274）。
> 配套文件：docs/reviews/p4_route_a_s0_baseline_snapshot_20261105.csv、docs/planning/p4_route_a_s1_statistical_plan_20261105.md、docs/planning/p4_route_a_s0_design_contract.md（A4）、docs/reviews/p4_route_a_s0_requirement_matrix.md（A4）、docs/reviews/p4_route_a_s0_risk_register.md（A4）。

## 0. 结论摘要

1. **旧工件完整性：PASS**。三个旧 run（M2/M5/M6）的 data_manifest 逐条校验 **92/92 文件全部匹配**（26/35/31），无缺失、无哈希不符；三份 manifest 均未把自身（及 M5/M6 的 SHA256SUMS.txt）计入 file_count，属既定口径。
2. **git_sha 可追溯：PASS**。三个 run_config 记录的 git_sha 全部存在于本仓库对象库，且全部是当前工作树 HEAD（a331639e）的祖先；M2 记录为干净工作树，M5/M6 记录为 -dirty（如实披露，但未留 diff 补丁）。
3. **冻结 digest 可复算：PASS**。M5 的 preregistration / frozen_family / meta_task_split 三个逻辑 digest（4f8a9a1f… / 5e7a9d1f… / 3c206ebb…）均可用规范 JSON 口径（去掉自哈希字段、键排序、紧凑分隔符、UTF-8）**独立复算命中**；它们不是文件原始字节哈希，二者不可混用。
4. **物理调用：PASS（0）**。M2/M5/M6 的 summary.physical_call_count 与 physics_guard 均为 0/PASS；M5 fairness.physical_call_count=0；D-12D-006 要求的“RCAIDE/SU2/Mission/WaveDrag 不新增调用”在旧 run 中未被违反。
5. **确定性：PASS（历史口径）**。三 run 均记录 determinism PASS、3 次重跑、0 mismatch；但 **M5 明确记录 raw_digest_manifest=NOT_STORED（A5-M5-07 遗留）**，新版本必须落盘 raw digest（见 F-02）。
6. **环境基线**：Python 3.11.17（CPython）、torch 2.8.0+cpu、Windows-10-10.0.26200-SP0、AMD64；路线A 工作树全量测试 **541 tests OK (skipped=1)**，耗时 38.056 s，EXIT=0（**该 541 为 A1 修复前的 HEAD a331639e 基线**；A1 修复后 546，S0-2 落地后 579，见 §10 与 A5 复审）。
7. **S0 尚未放行**，且存在 7 项新版本必须修正的旧版本缺陷/风险（F-01..F-07），全部只作用于新版本，旧冻结件一字不改（见 §6）。

## 1. 核验范围与方法

| 项 | 内容 |
|---|---|
| 核验对象 | 旧 P4 元学习三个正式 run（见 §3 表）；不重跑、不重算任何统计结论，只做只读完整性核验 |
| 核验脚本 | 外部记忆 p4-route-a/lead/s0_verify_old_runs.py（只读，未写仓库） |
| 核验输出 | 外部记忆 p4-route-a/lead/S0_lead_verify_old_runs.json |
| 文件哈希口径 | 文本：sha256(canonical LF bytes，CRLF→LF)；二进制（png）：sha256(raw bytes)；外部工件不进 file_count/total_bytes（沿用旧 manifest 的 schema 2.0.0 约定） |
| 逻辑 digest 口径 | sha256(canonical JSON：去掉自哈希字段、sort_keys=True、separators=(',',':')、ensure_ascii=False、UTF-8) |
| 只读保证 | 脚本只 open(read) 与 git 查询；未 stage/commit/push；未改动任何旧 run 文件 |

复算入口：

    python <EXT>/p4-route-a/lead/s0_verify_old_runs.py

（外部记忆根由本机配置提供；仅 Lead 本地使用，不入仓库。）

## 2. 环境基线

| 项 | 值 |
|---|---|
| 解释器 | envs/RCAIDE/python.exe，CPython 3.11.17 |
| torch | 2.8.0+cpu（无 CUDA） |
| OS / arch | Windows-10-10.0.26200-SP0 / AMD64 |
| 工作树 HEAD | a331639e47015f1d07796e46dbe3f71beb97048c（research/p4-route-a-improvements，= origin 同名分支） |
| 主库（本地仓库） | HEAD e5140fc64d348f2d9dcf52962f1dcfc425099341；main ec65e5a9a723bc52df8075a395fcaf9e0fd0fc2b（未动） |
| D12 工作树 | 独立 worktree，HEAD aef2cb71e07aa28abfc28e34b14bf9dc1579c2e3（research/d12d006-aero-improvements） |
| 测试命令 | envs/RCAIDE/python.exe -E -s -B -m unittest discover -s research/concorde_metaopt/tests -t . |
| 测试结果 | 541 tests OK (skipped=1)，38.056 s，EXIT=0（A1 修复前基线）；修复后 546、S0-2 后 579（均 skipped=1）；日志：外部记忆 p4-route-a/lead/S0_lead_baseline_tests.log；唯一 skip 为 RealOpenVSPIntegrationTests（缺环境，非本轮范围） |

## 3. 旧 run 完整性核验结果

| run_id | stage | 记录 git_sha | sha 存在 | 是 HEAD 祖先 | worktree_dirty | tracked/工作树文件 | manifest 文件数 / 字节 | manifest 校验 | physical | determinism | 既有状态 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| p4-meta-m2-offline-20261102T092828Z | P4 M2 离线 | 36d58918fc5f1002a599c45661e3cd389ce96c19 | 是 | 是 | false | 27 / 27 | 26 / 3,276,345 | 26/26 PASS | 0 | PASS, 3 reruns | VALID |
| p4-meta-m5-formal-20261104T1018Z | P4 M5 正式 holdout | 183616c7d69d277d16fca2f4b21839062cdbbab0 | 是 | 是 | true（-dirty） | 37 / 37 | 35 / 17,896,867 | 35/35 PASS | 0 | PASS, 3 reruns, 0 mismatch | VALID |
| p4-m6-formal-20261105T0118Z | P4 M6 跨任务 | c300d9532f3c354c71242adb720b3e5c1a958c40 | 是 | 是 | true（-dirty） | 33 / 33 | 31 / 4,578,799 | 31/31 PASS | 0 | PASS, 3 reruns | VALID |

逐项说明：

- **M2**：manifest 未收录 data_manifest.json 自身（27 tracked − 1 = 26），符合“manifest 不记录自身”的既定写法；其余文件全部匹配。finite_difference_check 为 PASS（epsilon=1e-5，n=5，max_relative_error=2.052996661561224e-11，tolerance=1e-4）。
- **M5**：37 tracked 中未进 manifest 的是 data_manifest.json 与 SHA256SUMS.txt（35 = 37 − 2），属打包口径而非缺失。old_m2_run_immutability 记录 M2 run 26 个文件“前后一致、0 mismatch”，与本报告独立核验结果一致。
- **M6**：33 tracked 中未进 manifest 的是 data_manifest.json 与 SHA256SUMS.txt（31 = 33 − 2）。
- 三 run 的 data_manifest.json / run_config.json / summary.json 文件级 sha256 已固定（见 §7 附录；raw 或 canonical-LF 逐行标注），用于后续复算与防改写。

## 4. 冻结 digest 复算（M5）

| digest | 记录值 | 复算 | 说明 |
|---|---|---|---|
| preregistration_sha256 | 4f8a9a1fd05f0648646da58dc669524de81c2c11c38b81d72f28b0be42e565fe | 命中 | = sha256(canonical JSON of preregistration.json 去掉 sha256 字段)，与文件内 sha256 字段一致 |
| frozen_family_sha256 | 5e7a9d1f2acd32a482195d0ae6255205310d4d5cf4bb38562e05265c4c9da20b | 命中 | = sha256(canonical JSON of frozen_family.json 去掉 sha256 字段) |
| split_hash | 3c206ebbe35e848a5137b433d7bc9ca022eb28b4b310ab3ccb9d89c989f33f8a | 命中 | = sha256(canonical JSON of meta_task_split.json 去掉 split_hash 字段) |

注意：上述逻辑 digest 与文件原始字节哈希不同（preregistration.json 文件 canonical-LF sha256 = c5abd30e811c93766002d6a3f0a25b8def1b5f4be0985b2a7e7999b120750c5d；frozen_family.json = 81e86dd5d1ec00f3416b10e19ff7725f854e1d7a988a99b6b578618bffd56ffc；meta_task_split.json = 5cb9452bff2b2392888d2d30303d11fe8598df322b08999004bd3f957e43729a）。新版本应同时记录“逻辑 digest”与“文件 digest”，并在 run_config 中显式写明口径，避免审计歧义。

补充（A2 独立复核 C-1）：M6 run 目录内有两份 `meta_task_split` —— 根目录研究级 split（文件 sha256=67ae1182…，逻辑 split_hash=3bc0f47b139601106530454b10dd8465c2fbf84826a9d634fbfed5903e5275d6）与 `gate/` 下 M5 split 的逐字节副本（文件 5cb9452b…，逻辑 split_hash=3c206ebb…）；两者不是同一文件，引用时须写明路径。

## 5. 旧 run 结果基线（仅引用，未重跑）

| run | 规模 | 关键结论/状态 | 图状态 |
|---|---|---|---|
| M2 | 750 runs / 48,000 次合成评价（B=64，5 臂，其中 2 臂为 CLONE） | status=VALID；FD PASS 2.05e-11；主终点 best_feasible_value 多数 null → INCONCLUSIVE；仅 fallback 指标可用；K=5 M−P = -0.013730479463645154，95% CI [-0.01808574719479586, -0.0036721320542072444]，Holm p=0.005580902099609375；K=0 M−P p=0.0758514404296875 不显著 | summary.figures 记录 5 张历史图为 NOT_RUN，但 figures/figure_status.json 记录 4 张 GENERATED（PNG/sha 可对）；旧 run 内部状态矛盾，本轮不冒充、不修复旧件 |
| M5 | 4,800 runs / 460,800 次评价（B∈{64,128}，4 臂；20 meta_test + 10 ood + 60 train + 20 val + 10 NC；meta_seeds=3，opt_seeds=10，radius_base=0.75） | status=VALID；conclusions_allowed=true；fairness PASS、physical=0；determinism PASS；runtime 8,960.33 s；主终点以 best_feasible_value 为主、null 率披露；4 张图 DATA_READY、fig2 NOT_APPLICABLE、fig6 NOT_RUN | 4 张 PNG 已存在（fig1/fig3/fig4/fig5） |
| M6 | 3,600 adaptation runs / 10,800 次适应执行；evaluation_units=80；3 个 family；K∈{0,1,5,10,20}；physical=0；runtime 73.12 s | status=VALID；三层结论：L1 bo_sample_efficiency=NOT_EVALUATED_IN_M6；L2 surrogate_error_advantage=NO_SIGNIFICANT_ADVANTAGE；L3 ood_generalization=OOD_NO_SIGNIFICANT_ADVANTAGE（diagnostics=CONFOUNDED，difficulty_matching=POOR_MATCH） | 图键与文件名存在历史漂移（见 F-04） |

上述数值只作为 S1 设计输入与历史对照，**不构成对 S1 新方法的结论**；S1 主结论只能来自新任务族的独立 meta_test（见统计计划）。

## 6. S0 发现的旧版本缺陷与风险（新版本必须修正，旧件不改）

| ID | 严重度 | 证据 | 影响 | 新版本要求 / 承接 |
|---|---|---|---|---|
| F-01 | major | M5 preregistration.json 的 stopping_rules 实际为“单字符数组”（list 元素均为 1 字符）；根因在 HEAD a331639e 的 research/concorde_metaopt/meta_learning/feasible_v2.py（STOPPING_RULES 单字符串 + list() 序列化） | 预注册的停止规则不可读、不可程序化执行 | A1（task-185）：改为 list[str]，增加序列化+反序列化类型校验与非空校验，补负控测试；旧 run 不改 |
| F-02 | major | M5 summary.determinism.raw_digest_manifest="NOT_STORED" | 无法从 raw digest 独立复算确定性 | 新版本每 run 落盘 raw_digest_manifest（含各产品文件 sha256 与规范化口径），并做 3 次重跑比对 |
| F-03 | major | M5/M6 run_config 的 git_sha_label 为 "-dirty"，但未记录 dirty diff/patch digest；M5 family.design_config_path 为绝对路径（含本机 worktree 前缀） | 复算环境不可完全重建；审计者无法确认跑的到底是哪份代码/配置 | 新 run 必须：干净工作树（否则 fail-closed），或记录 patch sha256；配置路径改为仓库相对路径 |
| F-04 | minor | M6 figures 状态键（fig1/fig2/...）与实际文件名（fig2_K_shot_rmse.png、fig6_ood_negative_control.png、fig7_k_sweep_delta.png）不一致 | 图与状态无法机器对账 | 新版本固定 7 张中文图的规范键 + 文件名 + figure_status.json，键名与文件一一对应 |
| F-05 | major | 旧任务 id 只存在于 meta_task_split/tasks.json 内部，无显式“与旧任务族零交集”检查 | S1 新任务族可能无意复用旧任务 | A1/A4：新 family v3 生成时输出 task_id 清单与旧 M2/M5/M6 清单的交集报告（必须为空），并纳入 fail-closed（FC-06） |
| F-06 | minor | M2 的 summary.figures 全为 NOT_RUN，但 figures/figure_status.json 有 4 张 GENERATED 且 PNG/sha 命中（旧 run 内部状态矛盾）；M5 的 fig6 为 NOT_RUN；历史报告曾出现“图已生成”的歧义 | 若直接复用旧图表会误导 | 新版本报告中不得把历史 NOT_RUN 图算作 S1 成果；S1 必须生成自己的一手图 |
| F-07 | major | S1 核心机制缺口（A4 已只读核实）：m5_arms.score_m5_init_designs（HEAD a331639e 第 504-514 行）无 support 参数，run_m5_bo_arm（第 636-644 行）调用时未传 k_shot/support | K-shot 未闭环，S1 无法成立 | A1/A6：加参数、显式传支持集与 k_shot（K=0 兼容旧行为），支持评价计入 B，各臂评价次数严格相等；由 A5 复核 |

另：A4 的需求矩阵/设计合同/风险清单已覆盖合同层（task-188），本报告只补“旧工件事实 + 缺陷清单”，不重复其字段定义。

## 7. 附录：关键文件哈希（文件级 sha256；raw 或 canonical-LF，逐行标注口径）

| run | data_manifest.json | run_config.json | summary.json | 其他 |
|---|---|---|---|---|
| M2 | acaab106388f834266b6b7a168d3611c7f74b498456abcf821ea71a764e07f66 | efd9f3cb5746cbbe687d0a53b56ef9cc1e8c2baee5ed31081226a443966579f2 | 444796d06cd36fe7395dc2f52dab2194b8fe37dae57e2e4fd68062b3a48a68fe | — |
| M5 | c44e9a075ebf1171b03e51e005e3418d9587b5a1161cfa77ce8c38d618defac6 | a55aa75d494e02d8ac1c987de82a1a8de8bc28e167b07a93074eaf505050e5f0 | 86e6afe15ba6f539eea2a410a123c366b5660a80374fd13bfc07f6edf49e8746 | SHA256SUMS c5ab020d…；prereg 文件 c5abd30e…；frozen 81e86dd5…；split 5cb9452b… |
| M6 | a9c3d822877af16509311a81bae70041334a592eb158c03c386ac7fd778e727e | d2a31a71fb384eeaca58364749f2dcf34aa46c8faeaca7ad112793c354a62809 | 85a1d21b7b511981bb78bcfc7e6203bdef97d8510022a7da98018dfec7759b4b | SHA256SUMS 535946e1…；meta_task_split 文件 67ae1182…；逻辑 split_hash 3bc0f47b… |

口径说明（A2 复核 D-1）：本表“M5 data_manifest.json、M5 SHA256SUMS.txt、M6 run_config.json”三项为 canonical-LF 值（磁盘为 CRLF，按提交/规范 LF 字节计算）；其余各项为 raw 磁盘字节。

## 8. 复算命令（可直接粘贴）

    cd <repo-worktree>
    git rev-parse HEAD
    envs/RCAIDE/python.exe -E -s -B <EXT>/p4-route-a/lead/s0_verify_old_runs.py
    envs/RCAIDE/python.exe -E -s -B -m unittest discover -s research/concorde_metaopt/tests -t .

## 9. 未覆盖范围与限制

1. 本报告不核验 D-12D-005 归档 run 与外部大文件（属 Issue #4 线，A1/A3 在 D12 工作树另行审计）。
2. 本报告不重跑旧 run 的统计（只读引用 summary/prereg 已有结论）；旧 run 的压强/阻力等物理值不在 #7 范围。
3. M5/M6 的 -dirty 工作树意味着历史代码状态不可完全还原；本报告如实披露，不做“事后补 patch”的伪造。
4. 旧图的 NOT_RUN 与图键漂移未被修复（不回写旧件），只作为新版本约束。

## 10. 与 S1 的衔接（放行前置条件）

- [x] A1：F-01（prereg 序列化/校验）已修复，全量 546 tests OK(skip=1)、EXIT=0（Lead 独立复跑 35.212 s，日志 EXT/p4-route-a/lead/S0_lead_full_tests_after_a1.log）；F-07（K-shot 闭环）属 S1 代码实现，尚未开始。
- [x] A2：独立复核 PASS（4/4 核验点、92/92 manifest 文件；D-1/D-2/C-1 已按本报告修正；其未复跑 541 tests 项由 Lead 复跑替代）。
- [x] A4：设计合同/需求矩阵/风险清单已交付（task-188），待 A5 审阅确认。
- [x] A3：旧 M2/M5/M6 + D-12D-005 工件只读证明 PASS（task-187/194，0 仓库写/0 git 写/0 solver）。
- [ ] A5：S0 审阅（task-189）给出 APPROVE_FOR_S1_PREP 或 CHANGES_REQUESTED；统计计划与预注册 schema 一并审阅。
- [ ] Lead：S0 集成裁定（task-190），签发 S0 完成结论后再启动 S1 正式训练/评估；physical_call_count 恒为 0。

S0 状态（截至本报告）：**待 A5 审阅；未放行**。
