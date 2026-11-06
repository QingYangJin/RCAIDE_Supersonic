# S1 v4e 整改裁定（A5 phase4 CHANGES_REQUESTED 关闭口径）

- 文档编号：R-V4-10
- 版本：v1.0
- 日期：2026-11-06
- 状态：生效；本文件纳入 commit G（父 F = fe8bdc9）
- 依据：A5 S1 phase4 终审报告（EXT/p4-route-a/a5/S1_phase4_review.md，sha256 c162cdc4…）1 blocker / 4 major / 5 minor
- 边界：physical_call_count=0、不合并 main、不新开 PR、仅 Lead 写 GitHub、旧 M2/M5/M6/S0-2/S0-3/S0-4/S0-5 只读

## R-V4-10-01 pair 标签唯一规范（关闭 S1R4-B01 blocker）

- 唯一规范：把两臂名按 Python 字符串字典序排序后以单竖线连接，即 "<lex_smaller>|<lex_larger>"。
- runner 侧：s1_runner.py 必须只用一个函数生成 pair 标签，供 pairs / pair_status_counts / excluded_pair_counts / structural 排除计数 / merge 重算使用；禁止再出现 required-order 拼接。
- analysis 侧：s1_analysis.py 加载 identifiability_report 时，对每个 pair 键 split("|") 后排序归一；非法格式（非 2 段、空段、未知 arm 名、重复 arm）fail-closed。
- 一致性：归一后必须与实际 pairwise 观测计数严格相等；不等即 fail-closed（保留既有错误语义）。
- 回归要求：真实 runner 产物直接进入 analysis 必须 exit0；merge 产物同样；K=0 CLONE 与 STRUCTURALLY_IDENTICAL 路径不得回归。

## R-V4-10-02 冻结包 code_sha 绑定（关闭 M01 的 runner 侧）

- runner 的 grid / run / merge 在 load_frozen_package 之后必须比较：包内 code_sha 与当前代码 package_code_sha()。
- 不一致：默认 fail-closed，抛 S1_FROZEN_CODE_SHA_DRIFT（错误信息含包内 sha、当前 sha、重生成提示）。
- 逃生口：仅当显式 --allow-code-delta 且包为 exploratory 时放行；run_config/summary 必须写 code_sha_delta_allowed=true 与两个 sha。确证（confirmatory）包禁止逃生，必须重生成。
- 负控测试：匹配通过、不匹配拒绝、escape 放行三态。

## R-V4-10-03 真实 runner→analysis 端到端（关闭 M02）

- 测试与 readiness 的 G05 必须使用真实 s1_runner 产物（极小样本：B64、K∈{0,3}、2 任务、单 meta/opt seed、2 臂、0 物理），不得使用手工合成 identifiability_report。
- 覆盖串行产物与 merge 产物两条链路，analysis 均须 exit0 且 structural 计数一致。
- synthetic report 仅允许用于冻结包布局/负控单测，不得作为放行证据。

## R-V4-10-04 launcher 预检绑定（关闭 M01 launcher 侧）

- run_shards.sh 启动前必须逐项 PASS，否则拒绝执行：
  1) 冻结包目录 = 授权书绑定的 S0-6 路径（拒绝 S0-4/S0-5 及任何其他包）；
  2) SHA256SUMS.txt 9/9 校验；
  3) 包内 code_sha = 当前 HEAD 的 package_code_sha()；
  4) git HEAD = commit H；
  5) artifacts 根与 expected_identity.json 的 sha 与 readiness 记录一致；
  6) TOP run_id、15 分片过滤参数、总 run 数 21,000 与 dry-run 计划一致。
- launcher 必须支持 --dry-run 并输出预检报告；任何一项失败 exit 非 0 且不启动任何 run。

## R-V4-10-05 B128 资源实测（关闭 M04）

- A2 在 readiness v4e 中必须实测 B128×K=3 的 4–6 个 run（真实 runner、0 物理），记录墙钟、单进程峰值内存、records 字节。
- 若实测墙钟或内存超过 v3 因子外推值 20% 以上，须调整 15 分片窗口（建议 3.5–4.5 h）或内存上限，并在 readiness 中披露。
- 未实测前不得把 15 片并行窗口写成确定值。

## R-V4-10-06 S0-6 重生成与放行链

- 顺序：A1/A6 修复 → Lead 独立全量测试 → commit G → A1 在 G 干净 detached worktree 两独立进程生成 S0-6（run_id p4ra-s0-6-freeze-<UTC>Z；code_sha = G 的 package_code_sha()）→ Lead 入库 commit H → A2 readiness v4e → A4 文档同步 → A3 审计 → A5 phase4b 终审。
- S0-6 与 S0-5 的差异仅限：run_id、git_sha、code_sha、时间戳、prereg holdout_package 元数据、calibration 文案；任务族/五 split/计数/holdout_seed=20261106/family_fingerprint/split_hash/radius=0.64 必须保持不变。
- S0-5 与 S0-4 在 S0-6 入库后标记 SUPERSEDED_LEGACY，只读。
- 放行：A5 出 APPROVE_FOR_S1_RUN 后，Lead 发布书面授权，必须显式绑定 S0-6 包路径、SHA256SUMS 哈希、run_id、15 分片过滤参数、4.5 h 硬上限与失败停跑规则。

## R-V4-10-07 merge 确定性与清单口径（m02）

- manifest/README 必须区分“记录级字节”与“canonical 子集”：serial 与 merged 的 records 仅 cost.total_wall_s 与 record_digest 允许不同；比较 canonical 子集（去掉 record_digest/total_wall_s）须逐字节一致。
- analysis 的 merge 校验必须使用 canonical 子集口径，并在报告中写明。

## R-V4-10-08 边界（不变）

- physical_call_count 必须为 0；不得启动任何真实求解器；不得读取真实 holdout（meta_test/meta_test_ood）直到 Lead 书面授权 21,000。
- 不合并 main、不新开 PR、不修改旧 M2/M5/M6/S0-2/S0-3/S0-4/S0-5 工件；仅 Lead 写 GitHub。
