# P4 路线A S1 v4b 并行执行裁定（R-V4-07）

状态：Lead 裁定，2026-11-05（Asia/Shanghai）。适用范围：S1 formal 21,000 runs（全合成、physical=0）。

## 0. 背景
A2 readiness v4b 实测 formal runner 无 `--workers`，串行 21,000 估算 36.99 h（36.4–38.1 h），不可在本次会话合理窗口内完成。runner CLI 已支持 `--meta-seeds`/`--opt-seeds`/arms/budgets/k-values 过滤，且 run 记录含全局唯一 `run_id`（含 meta_seed/opt_seed）。因此采用**分片并行 + 确定性合并**，不改变统计/分析合同。

## 1. 分片合同
- 分片维度：`meta_seed ∈ {0,1,2}` × `opt_seed 对 ∈ {(0,1),(2,3),(4,5),(6,7),(8,9)}`，共 **15 个分片**；每分片 1,400 runs（main 600 / secondary 400 / exploratory 400）。
- 所有分片使用**同一个顶层 run_id**：`p4ra-s1-formal-<UTC>`（如 `p4ra-s1-formal-20261105T1830Z`）；记录 `run_group_id` 相同，记录 `run_id` 由 arm/B/K/task/meta_seed/opt_seed 决定，跨分片唯一。
- 每分片命令（等价）：
  ```
  python -m research.concorde_metaopt.meta_learning.s1_runner run \
    --frozen <S0-3_PACKAGE> --artifacts-root <ARTIFACTS> \
    --outdir <FORMAL_ROOT>/shards/ms{m}_os{p}-{q} \
    --run-id <TOP_RUN_ID> --grid formal \
    --meta-seeds {m} --opt-seeds {p},{q}
  ```
- 分片目录彼此独立；不得共享 outdir；每个分片输出自己的 run_records.jsonl / identifiability_report.json / run_config.json / run_summary.json / manifest.json。

## 2. 合并合同（s1_runner merge 子命令）
新增 CLI：
```
python -m research.concorde_metaopt.meta_learning.s1_runner merge \
  --frozen <S0-3_PACKAGE> --artifacts-root <ARTIFACTS> \
  --shards-root <FORMAL_ROOT>/shards --outdir <FORMAL_ROOT>/merged \
  --run-id <TOP_RUN_ID>
```
必须（全部 fail-closed）：
1. 加载冻结包，重建**完整 formal plan**（默认 meta_test、5 臂、B/K 分层、meta_seeds 0..2、opt_seeds 0..9、20 任务），得到期望 run_id 集合与顺序；
2. 枚举 `shards-root` 下所有分片 `run_records.jsonl`；逐记录校验 identity（family_version/family_fingerprint/split_hash/prereg_digest/analysis_plan_digest 与冻结包一致）、`split=meta_test`、`grid_stratum` 与 (B,K) 一致、`billable_evals=B`、`initial_designs=8`、`bo_calls=B−8`、`physics.physical_call_count=0`、status/record_digest 合法；
3. 期望集合与分片并集**恰好相等**：missing=0、extra=0、duplicate run_id=0、duplicate (arm,B,K,task,ms,os)=0；记录数=21,000；分层计数 main 9,000 / secondary 6,000 / exploratory 6,000，`B128×K0=0`；
4. 按 formal plan 顺序排序（不是按分片拼接顺序），重算 `ranking_identifiability_report(records)`；
5. 用完整 plan 调 `build_grid_run_config` 生成合并 run_config，写合并 bundle（`run_records.jsonl`、`run_config.json`、`run_summary.json`、`identifiability_report.json`、`manifest.json`）；
6. 另写 `merge_manifest.json`：TOP run_id、期望/实际 run 数、missing/extra/duplicate 数、各分片 path + run_records sha256 + record_count + 过滤参数、分层计数、identity、合并 run_records sha256/canonical sha256、⾝份、physical 合计=0、K=0 CLONE 检查、status=PASS/FAIL 及 problems。
7. 合并必须**确定性**：同一组分片两次 merge 的 5 个产物逐字节一致；合并结果与“全量串行单进程”在同一缩小网格上逐字节一致（测试）。
8. 合并不得读取真实 meta_test/OOD 之外的敏感物；不启动 solver；不改变 analysis 合同（analysis 只消费合并 bundle）。

## 3. 验收
- A1 新增/修改代码仅 `s1_runner.py` + `tests/test_s1_runner.py`；新增测试至少覆盖：串行 vs 2 分片合并逐字节一致、missing/extra/overlap/duplicate/identity 漂移/预算不符/物理>0 fail-closed、merge 幂等、合并 manifest 字段完整。
- 全量测试必须 ≥829 tests 且 OK(skip=1)；A5 merge delta 复审通过前不得启动 21,000。
- A3 审计 merge 提交与 15 分片目录/合并产物；A2 执行分片与合并，逐分片 exit=0 后 merge PASS。
- 资源：15 进程串行单线程、峰值约 15×304MB≈4.6GB、16C/32T、磁盘约 69MB records + 开销；全部 physical=0、RCAIDE/SU2/WaveDrag LOCKED。

## 4. 边界
- 不合并 main、不新开 PR、仅 Lead 写 GitHub；不改变已冻结的端点/比较集/网格/任务。
- 若 merge 校验失败，整个 formal 作废并披露，不得手工修补记录。
