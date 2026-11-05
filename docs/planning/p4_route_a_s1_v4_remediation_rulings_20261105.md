# P4 路线A S1 v4 整改 Lead 裁定（2026-11-05）

依据：A5 task-228 rev2 复审 verdict=CHANGES_REQUESTED（2 blocker / 4 major / 6 minor），
报告 `EXT/p4-route-a/a5/S1_code_review_rev2.md` sha256
`d5a0979ac83009e4217bf9848fc3c9cdca7216c3a87f899ed143195678a5f795`。
本文件为 Lead 在 Issue #7 D-P4-003 授权内的技术裁定，不改变 physical_call_count=0、
不合并 main、不新开 PR、仅 Lead 写 GitHub 的边界；owner 可随时书面否决。

## R-V4-01 holdout 污染整改：选 H1（新独立 v4 holdout）

- 事实：36 个 run_records.jsonl / 608 条记录全部 split=meta_test，涉及 TE-000/TE-001/TE-003
  3/20 任务；另有 TE-000..007 被读入内存（A2 readiness、A6 smoke、A1 确定性、Lead 诊断、A5 探针）。
- 裁定：采用 H1，但**只重播种 holdout 两类集合**（meta_test 20 + meta_test_ood 10），
  保留 meta_train 60 / meta_validation 20 / negative_control 10 逐位不变；因此
  radius_base=0.64 校准证据与 meta_train/meta_validation 上的工件训练仍然有效。
- 新 holdout 种子：`V4_HOLDOUT_SEED = 20261106`。
- 新族身份：`family_version = "p4ra-family-v4"`；`family_id` 仍为 `F-QE-feasible-v3`
  （解析分布未变，仅 holdout 重采样；不得把 v4 说成新公式族）。task_id 字面量可沿用
  `p4ra-FQE3-v3-<split>-<idx>`（A5 接受 bump family_version 作为替代），但每条 run record、
  run_config、frozen_family、prereg 必须携带并校验 `family_version`，禁止跨版本混用；
  v4 holdout 的 task_fingerprint 与 v3 官方包 120 个 task_fingerprint 零交集（断言）；对 legacy 280 个 task_id 仅做 task_id 零交集。
- 旧 `p4ra-family-v3` 冻结包保持只读可验证（legacy 白名单），不得被改写、不得用于
  S1 确证性 formal；旧包只可用于历史复现/负控。
- 新冻结包命名：`p4ra-s0-3-freeze-<UTC>Z`；产物、run_id、git_sha、code_sha、holdout_seed
  必须写入 frozen_family/prereg/freeze_summary/digest_manifest。
- 验收不变量：meta_train/meta_validation/negative_control 的 task_id→task_fingerprint
  映射与 S0-2 包逐项相同；meta_test/meta_test_ood 的 task_fingerprint 全部变化；
  五集合 task_id 仍两两互斥；120 任务计数 60/20/20/10/10 不变；
  v4 holdout task_fingerprint 与 v3 官方包 120 个 task_fingerprint 零交集；legacy 280 个 task_id 只做 task_id 零交集。
- 不做事后任务剔除；主统计仍为 meta_test 20 个任务。

## R-V4-02 C5 结构性不可辨识：选 C5-B（预注册不可辨识，不做 benefit/harm 推断）

- 事实：正式 200/50 工件下，K=5 时 ZERO==KSHOT 初始设计 22/24（meta0 8/8、meta1 7/8、
  meta2 7/8）；meta0 K=5 B64 的 8/8 任务 64 观测历史逐字节相同。机制：BO 在 8 个初始点后
  只用观测拟合，不再使用 meta 工件；初始点相同 ⇒ 全历史相同。
- 裁定：不重设计臂、不改 BO 机制；在 v4 prereg/analysis plan 中预注册：
  1. 每个 (task, budget_B, K, meta_seed) 组内，对每个臂对计算初始设计行 digest 的
     overlap_rate；`overlap_rate >= 0.90` 判该臂对在该组 `STRUCTURALLY_IDENTICAL`。
  2. 该臂对该组不进入 benefit/harm 推断，只作描述性记录；不做事后任务剔除。
  3. C5（FOMAML-KSHOT-BO vs FOMAML-ZERO-BO）**不进入任何 benefit/harm 推断与 Holm 族**，
     只报告结构克隆率/描述性数值；若可推断组覆盖任务数 < 10，总结论固定为
     `NOT_ESTIMABLE_STRUCTURAL_IDENTIFIABILITY`，不得声称适应增益/损害。
  4. 其他比较（C1/C2/C3/C4 等）按同一 pair-level 规则排除结构同组后计算；排除率必须披露。
- 旧 A1 10/24 数字仅诊断（2/3-step 工件），不得引用为可辨识证据；M04 用正式工件重建。

## R-V4-03 正式工件

- 在 v4 代码提交后的干净 worktree 用 `s1_runner prepare-artifacts --frozen <v4 package>
  --meta-seeds 0,1,2` **默认参数**（maml 200 steps / pretrain 50 steps）重建。
- 冻结 artifact sha256 写入 A2 readiness 报告与 run_config；与 v3 旧工件 sha 不同/相同都
  必须显式记录，不得复用旧 run 的 run_config。
- 旧 A2 readiness 报告标注 `BASELINE_989FC0A`，不得作为 v4 formal 就绪证据；A2 在 v4 提交后重跑。

## R-V4-04 可辨识性报告 schema（A1 实现 runner，A6 消费 analysis）

`identifiability_report.json` 增加：
- 每组 `pairwise` 元素增加 `pair_identifiable: bool`、`structural_status:
  "IDENTIFIABLE"|"STRUCTURALLY_IDENTICAL"`、`threshold`；
- 顶层增加 `pair_status_counts`（按 "arm_a|arm_b" 聚合的 IDENTIFIABLE/STRUCTURALLY_IDENTICAL 计数）；
- 保留 group-level `ranking_status` 仅作描述，不作为推断依据。
- 分析脚本必须加载每个 source run 的 identifiability_report.json，校验 schema/组覆盖/
  与 run_records 的 (task,B,K,meta_seed,arm) 一致；formal 模式缺失即 fail-closed；
  在 aggregate.json/CSV 输出 `structural_exclusion_counts` 与 C5 可估计任务数。
- 不做事后剔除；排除规则在读取数据前固定。

## R-V4-05 冻结与阶段门

1. A1/A6 修复 → Lead 提交 commit V4 → push。
2. A1 在干净 detached worktree 生成 v4 冻结包（两独立进程 run1/run2 逐字节一致）。
3. Lead 将冻结包写入仓库并提交。
4. A2 重建正式工件 + readiness + K=5 正式工件克隆率复核。
5. A5 phase3 审阅：v4 包 + 正式工件 + pair-level 报告/分析 + C5-B + M01/M02/M04 关闭。
   所有 readiness/诊断（A1/A2/A6/A5）**不得读取新 meta_test/meta_test_ood**；
   label-shuffle 与克隆率诊断只能用 meta_train/meta_validation。
6. A3 隔离审计。
7. 只有 A5 给出 APPROVE_FOR_S1_RUN 且 Lead 书面授权后，A2 才可启动 21,000 formal run。
8. physical_call_count 全程 0；RCAIDE/SU2/WaveDrag LOCKED；不合并 main。

## R-V4-06 文档与回执

- 合同/统计计划/执行计划/需求矩阵统一写：family_version=p4ra-family-v4、holdout_seed=20261106、
  S0-3 冻结包、C5-B、pair-level 规则、旧 S0-2 包只读且不得用于确证 S1。
- Issue #7 回执必须披露：holdout 污染事实、H1 选择理由、C5 结构性不可辨识数字、
  旧 APPROVE_FOR_S1_FORMAL 范围收窄（A5-M03）、0 物理、未合并 main。