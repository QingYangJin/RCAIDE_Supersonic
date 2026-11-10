# D-NEXT-001 A5 专项审计：S3 缺陷清单（可签署级）

- 审计人：A5（独立科学/代码审查；未实现、未修改被审算法）
- 审计对象：S3 分支 research/p4-route-a-s3 @ c7221fb（封账），归档证据根 D:\RCAIDE-s3-dev
- 基线：D-NEXT-001 计划文档 + 基线 commit ea8ad97833eb5ceab291faae643c141a2b219749（= S3 封账 c7221fb + 计划文档）
- 复核方式：只读静态复现 + 归档证据重算；physical_call_count=0、solver_processes_started=0
- 复核脚本：research/concorde_metaopt/reviews/a5_audit/a5_audit.py（检查项 A5-C01…C12）
- 示例审计输出：docs/reviews/dnext001_a5_sample_audit_output_20261110.json / .md
- 统一复跑命令（PowerShell，工作树 D:\RCAIDE\dnext001\wt-a5）：
    & D:\RCAIDE\envs\RCAIDE\python.exe research\concorde_metaopt\reviews\a5_audit\a5_audit.py --s3-root D:\RCAIDE-s3-dev --dnext-root D:\RCAIDE\dnext001 --out docs\reviews\dnext001_a5_sample_audit_output_20261110.json --md docs\reviews\dnext001_a5_sample_audit_output_20261110.md
- 状态语义：VALID = 本审计断言（缺陷存在/口径成立）已被复现；NOT_VALIDATED = 证据不足或外置不可复核；NOT_RUN = 未执行；FAIL = 断言被证伪或证据自相矛盾。本清单中 VALID 均表示缺陷已确认，不是给 S3 签 PASS。

## 0. 审计边界与既有事实（不得改写）

- S3_RUN=EXECUTED_M3；结果回执 PENDING；阶段放行 NOT_ISSUED；S4=NOT_APPROVED；approved_for_next_stage=false。
- 规模 3,780 runs / 362,880 evals / 17 件归档 312,310,937 B（外置 8 件原始记录流合计 312,310,937 B）；run_id=p4ra-s3-formal-20261109T1310Z。
- 四预注册检验全 NULL，overall_decision=NO_EVIDENCE，evidence_scope=DEVELOPMENT_VALIDATION_ONLY；ANIL_INCONCLUSIVE。
- 本清单不改变上面任何结论；新增的只是"这些结论在什么证据强度上成立、哪些地方 fail-closed 失效"。

## 1. F-01 validate 模型清单路径缺陷

| 项 | 内容 |
| --- | --- |
| 证据路径 | research/concorde_metaopt/meta_learning/s3_runner.py:2527-2531；research/concorde_metaopt/meta_learning/s3_prereg.py:641（S3_EVIDENCE_ROOT_RELPATH="research/concorde_metaopt/evidence/s3"）；evidence/s3/run/model_manifest.json（row.path 实测 "models/fomaml_meta_0.json"） |
| commit | research/p4-route-a-s3 @ c7221fb |
| 缺陷 | 校验器以 repo_root / row.path 解析模型文件，且回退仍是 Path(repo_root)/rel_path，缺 S3_EVIDENCE_ROOT_RELPATH 前缀；而模型清单记录的是证据包内相对路径。合法 run 因此得到 validation_ok=false。 |
| 复现 | 静态：校验块内 S3_EVIDENCE_ROOT_RELPATH 命中 0 次；路径反证：Path(repo)/"models/fomaml_meta_0.json" 不存在，Path(evidence/s3)/"models/fomaml_meta_0.json" 存在。脚本：A5-C03（status=VALID）。 |
| 影响 | 58/59 项 PASS、唯一失败项即 model_manifest_models；campaign 主进程 exit code=1、validation_ok=false。这是"位置错误导致的 fail-closed"，不是数据造假，但足以使门禁不可签署。 |
| 严重度 | MAJOR（阻断门禁，不阻断数据真实性） |
| 整改门槛 | G1：修前缀（或统一以证据包根解析）；只读重跑 validate，要求 validation_ok=true 且 59/59 PASS；重跑不产生新物理调用。修复后须由 A5 复审并给出独立 verdict，不得由提交消息代替。 |
| fail-closed 判据 | 修复后仍 validation_ok=false，或校验器改为"缺文件即跳过"、或把 model_manifest_models 从检查集移除 => 立即 FAIL，禁止进入 S4。 |

## 2. F-02 聚合校验口径（模型 sha 绑定）

| 项 | 内容 |
| --- | --- |
| 证据路径 | research/concorde_metaopt/meta_learning/s3_runner.py:1635-1661（_model_block_summary 丢弃 bytes）；research/concorde_metaopt/meta_learning/s3_analysis.py:2221-2249（:2243 直接比聚合 sha）；evidence/s3/run/run_config.json 与 s3_preregistration.json 的 models 段 |
| 数值 | fomaml：run e90a05c5234e82f0e9052c6726811264aa8043299746f3c13d30ba965a306336 vs prereg 731a699872b0e8d0d42d3833abb5705bc894b1c092fdc92fe86591f368294a8d；anil：run 9b421cce88db4d27bad876a0b019d1c7b4c9e43d20acc7dde27f807e5777d8ff vs prereg 3dfe78a318ad1ea983b1ad573ddee3660bc2afaec1154bd1756c21d8856b5d52 |
| 缺陷 | 两侧聚合口径不同：prereg 行含 bytes 且路径为仓库相对路径 + kind/config_note；run 行无 bytes、路径为 models/<kind>_meta_<seed>.json。逐模型 sha 完全一致（6/6）但聚合不等 => fail-closed 误报。 |
| 复现 | 脚本 A5-C04（status=VALID）：去 bytes + 路径归一后，归一化聚合 sha 与 run 侧逐 kind 精确相等；6 个逐模型 sha 与磁盘模型文件 sha 全部一致。命令同统一复跑命令。 |
| 影响 | M4/M5 阶段任何"模型绑定失败"结论都不可直接采信；需人工判定是口径差异还是篡改。 |
| 严重度 | MAJOR（门禁可复现性；数据未发现篡改） |
| 整改门槛 | G2：在 s3_analysis 或校验器中统一聚合口径（同字段集、同路径规范），重算后逐 kind 相等；补一条负向测试（篡改任一模型文件必须 FAIL）。缺少负向测试 => 不得签 PASS。 |
| fail-closed 判据 | 归一化后仍不等、或为"让比较通过"而放宽为子集比较/丢弃 sha => FAIL。 |

## 3. F-03 OOD 正式分析未接入

| 项 | 内容 |
| --- | --- |
| 证据路径 | research/concorde_metaopt/meta_learning/s3_analysis.py:4601-4606（build_ood_rows 只筛 endpoints.split=="meta_test_ood"，从不读 run.record_streams.ood）；evidence/s3/analysis/s3_ood_descriptives.csv；evidence/s3/analysis/ood_supplementary_descriptives.csv；evidence/s3/analysis/analysis_disclosures.json（A5-S3M5-01） |
| 输入证据 | run 侧 ood_records.jsonl 28,800 行 / 300 runs / 10 tasks / 22,430,606 B / sha e8372903b82e5a2730bdc3b557d5d367d3ebe5d90b5d1d1d204be4415f2539ba |
| 缺陷 | 正式 OOD 描述全行 NOT_RUN，reason="run 产物不含 OOD 段"，与磁盘存在 28,800 条 OOD 记录直接矛盾；侧车 ood_supplementary_descriptives.csv 100 行为 Lead 辅助产物（label=LEAD_AUXILIARY_NOT_FROM_FROZEN_ANALYZER），非正式分析。 |
| 复现 | 静态：build_ood_rows 体内 record_streams / ood_records 命中 0；脚本 A5-C05（status=VALID）。 |
| 严重度 | MAJOR（预注册 OOD 端点缺失；不改变主检验 NULL 结论，但使 OOD 方向的"无显著"不可引用） |
| 整改门槛 | G3：把独立 OOD 记录流接入冻结分析器并重算描述与（若预注册）端点；正式产物与侧车产物在文件名/字段上不得混用；侧车不得被引用为正式 OOD 结论。 |
| fail-closed 判据 | 用侧车替代正式 OOD 分析、或在报告中把侧车称"OOD 已验证" => 立即 FAIL；fig7 仍为 NOT_RUN 却签发 OOD 相关 PASS => FAIL。 |

## 4. ANIL 成本 wall_s=0 不可审计（A5-S3M5-03）

| 项 | 内容 |
| --- | --- |
| 证据路径 | research/concorde_metaopt/meta_learning/s3_runner.py:1035（逐点 "wall_s": 0.0）；research/concorde_metaopt/meta_learning/s3_analysis.py:4113-4116（adaptation_cost=wall_s+budget、total_cost=wall_s）；evidence/s3/analysis/s3_cost_table.csv；aggregate.json 的 anil_audit |
| 数值 | cost_table 10 行 total_cost_median_s 全 0；adaptation_cost_mean 恒等于 budget（64/128）；anil_audit.cost_ratio=1.0、cost_ratio_max=0.75、margin=0.02、decision=ANIL_INCONCLUSIVE |
| 缺陷 | 成本口径退化为"预算比"：cost_ratio=1.0 表示 ANIL 与 FOMAML 预算相同，而非计算成本相同；因此"ANIL 成本不高于 FOMAML×0.75"的门禁无法审计。 |
| 复现 | 脚本 A5-C06（status=VALID）。 |
| 严重度 | MAJOR（结论层：成本-效率类判断不可签发） |
| 整改门槛 | G4：引入可复核成本量（逐次评价墙钟或 FLOPs 估计），并区分"预算成本"与"计算成本"两个字段；重算 cost_ratio 且给出不确定区间；标注成本口径修订前的所有成本结论为 NOT_VALIDATED。 |
| fail-closed 判据 | 继续用 budget 冒充 wall_s、或用 cost_ratio=1.0 支持任何"效率"结论 => FAIL。 |

## 5. NC 补丁仅 sidecar / NC-15 未计算（A5-S3M5-02）

| 项 | 内容 |
| --- | --- |
| 证据路径 | research/concorde_metaopt/meta_learning/s3_analysis.py:4573-4587（缺三键即 status=DISCLOSED）；evidence/s3/run/negative_control_summary.json（1,680 B，sha 1a17774d5fa310c8…）；evidence/s3/analysis/s3_negative_controls.csv |
| 数值 | 缺键 shuffled_con_minus_obj_feasible_hit_rate / shuffled_con_minus_obj / con_minus_obj_shuffled；10 组 28,800 条；9 组方向一致，S3-DE B64=0.44895833333333335 异常（B128=0.6098958333333333） |
| 缺陷 | NC-15 未计算而是"披露即通过"；负控侧车复算（CON−OBJ B64 +0.016146、B128 +0.009895，与主任务绝对比 1.6757/2.9457）不产生 p/CI/decision，却容易被引用为证据。 |
| 复现 | 脚本 A5-C07（status=VALID）。 |
| 严重度 | MAJOR（负控完整性；单组异常未归因） |
| 整改门槛 | G5：补齐三键并计算 NC-15；对 S3-DE B64 异常给出归因（实现缺陷/任务难度/随机性）与是否触发排除规则；侧车复算必须标 DESC_ONLY 且不得进入 decision。 |
| fail-closed 判据 | 以侧车数值替代 NC-15、或异常组被静默剔除而无预注册规则 => FAIL。 |

## 6. 图件 4/10 NOT_RUN

| 项 | 内容 |
| --- | --- |
| 证据路径 | evidence/s3/analysis/figure_status.json（6 RENDERED：fig3/4/5/6/8/9；4 NOT_RUN：fig1_train_loss、fig2_kshot、fig7_ood、fig10_vspaero_gate）；figure_generation_summary.json（cjk_font=Microsoft YaHei、physical_call_count=0） |
| 缺陷 | 4 张图缺数据：fig1 无 train record、fig2 无 K∈{0,1,3,5} 记录、fig7 OOD 未接入、fig10 无 VSPAERO 门归档。fig7 的旧 reason"run 产物不含 OOD 段"已被 analysis_disclosures.json 更正。 |
| 复现 | 脚本 A5-C08（status=VALID）。 |
| 严重度 | MINOR（不造假图、已披露；但读者易把缺图当"无差异"） |
| 整改门槛 | G6：每张 NOT_RUN 图在报告与图目录同时标注"未运行+原因+所需数据"；fig7 必须与 G3 联动；不得以占位图/合成数据补图。 |
| fail-closed 判据 | 出现无数据来源的图、或 fig7 标 RENDERED 但无 OOD 记录流接入 => FAIL。 |

## 7. A5 M2R 门未重新签发、由 A7 替代（S3-GOV-01）

| 项 | 内容 |
| --- | --- |
| 证据路径 | docs/reviews/p4_route_a_s3_requirement_matrix.md L142（S3-GOV-01 = DEVIATION）、L221（A5_M2R_REVIEW=NOT_RECORDED）；evidence/s3/reviews/ 下 a5_m2r / a7_m2r verdict 均为 0 件（仅有 S3_m5_a5_verdict.json、S3_m4_a7_verdict.json） |
| 缺陷 | A5 对 M2 给 CHANGES_REQUESTED（m3_start_allowed=false），M3 实际由 A7 M2R=APPROVE_FOR_S3_RUN 替代放行；A5 M2R 与 A5 结果复核均未落盘最终 verdict。任务合法执行，但"独立复核门"在 M2R 节点缺失。 |
| 复现 | 脚本 A5-C11（status=VALID，判定为"已记录偏离但门禁完整性 NOT_VALIDATED"）。 |
| 严重度 | BLOCKER（治理层：不得据此宣称 S3 已通过独立双签） |
| 整改门槛 | G7：负责人裁定（a）补签 A5 M2R 追溯 verdict，或（b）在 S4 计划中显式登记该偏离与补偿性复核（A5 对 M3/M4 产物出独立 verdict）；两者都必须落盘具名文件；不得以 A7 替代件充当 A5 独立结论。 |
| fail-closed 判据 | 任何 S4 放行材料把"A7 M2R"写成"A5 M2R"、或声称"S3 双人独立复核通过" => FAIL。 |

## 8. A3 独立仓库守护代理崩溃、缺独立 A3 结论

| 项 | 内容 |
| --- | --- |
| 证据路径 | docs/planning/dnext001_real_concorde_route_a_b_gpu_plan_20261110.md L12（A3 独立仓库守护代理崩溃列为已知缺陷）与 L94（A3 若任代码开发须由 Lead+A4 重建隔离检查、A5 独立审计，不能把过去崩溃当已解决）；requirement matrix L63（S3-M0-04 PARTIAL）、L64（S3-M0-05 PARTIAL） |
| 缺陷 | A3 的仓库隔离审计仅覆盖 M2R 区间（378768c→987751d→691f554）；M3/M4 的 run/analysis 未跟踪目录未审计；A3 崩溃后无独立 A3 结论落盘。因此"零改写冻结资产"仅有 13 个 evidence 文件的局部声明，不是全仓隔离证明。 |
| 复现 | 文档比对 + 证据目录清单（脚本 A5-C11 的 a3_coverage_partial 指标）；本机不可重放 A3 进程，故进程级 NOT_RUN。 |
| 严重度 | MAJOR（证据守护链缺口；与 F-01/F-02 叠加放大） |
| 整改门槛 | G8：在 S4 前由 Lead+A4 重建隔离检查（基线 commit 固定、全仓 git status 干净、冻结目录逐文件 sha 对照），A5 对该次检查出独立 verdict；A3 若要继续担任守护/开发，必须先在独立 worktree 复跑成功并留日志。 |
| fail-closed 判据 | 用"S3 期间未观察到改写"的口头结论替代全仓隔离审计、或把 A3 崩溃视为已解决 => FAIL。 |

## 9. 追加发现（本次审计新增，均只读复现）

### 9.1 F-04 analysis plan digest 重算过严（MINOR）
- 证据：research/concorde_metaopt/meta_learning/s3_analysis.py:1309/1344（_validate_endpoints_section 返回对象比 prereg 多 comparator/c1_tests/c2_tests 三个顶层键）、:1740-1745 传入 analysis_plan_digest。
- 数值：原始三段复算 31ac71d730cfc58a1ff669488ca431dcb930cc8f6861418504e11ffc5f799c05（与声明相等）；经校验器对象后 d5b2ac24f8f614f2b641466b3d7f92e77f23d3e9090996f7f29cc08a0ad04ec1（不等）。
- 结论：--verify-analysis-plan-digest 必然失败，属口径过严而非篡改；复现状态 VALID（缺陷确认）。整改：digest 计算前冻结为原始预注册结构，或把派生键显式排除。严重度 MINOR。

### 9.2 record_digest 两套口径（MINOR）
- 证据：s3_runner.py:119-120 排除 (wall_s, peak_memory_mb, record_digest)；s3_analysis.py:3608 调 sp.record_digest(dict(record))，而 s3_prereg.py:388-390 只排除 record_digest 自身；s3_analysis.py:3536-3538 的另一函数正确排除三字段。
- 数值：首条 eval record 冻结 digest 9fd5b7bf5e56fad05c36dea5f7904a8d9c59ae86e5a566c50aae1ccf4c7c0971；sp.record_digest=35edae4a2a80077403e1205bad9eca59fe36e4c7abe1810512b976b33ac914a1（不匹配）；runner 口径 9fd5b7bf…（匹配）。
- 结论：VALID（缺陷确认）；整改：单一 digest 实现 + 三字段排除常量复用 + 单测。MINOR。

### 9.3 execution_report 时间戳陈旧（MINOR，A7-F-05）
- 证据：evidence/s3/run/execution_report.json 的 created_utc=14:07:08Z，早于 campaign END 14:17:54Z。属陈旧字段，不影响数据；整改：报告时间改为 ended_utc 或重生成。

### 9.4 无 __main__ 守卫 / 仓库外 launcher（INFO，A7-F-07）
- 证据：s3_runner.py 无 __main__ guard；实际执行用仓库外 launcher（500 B，sha 9b66b007…）。
- 结论：VALID（事实），但可执行入口不可审计 => 建议入仓 launcher 并固定 sha。

### 9.5 记录级确定性 NOT_RUN（NOT_RUN，非缺陷）
- 证据：evidence/s3/run/determinism_check.json（record_core_sha256 三次均为 645e9f9c471269be37a8d219a88a1d9154824ba5458f1dbfbfc80b423315d4d8；subset_run_keys_sha256=0704a23ead63533f3659148b1167c6a81063089724e0015f3b9b1c43ec78ae5c；排除字段正确）。
- 限制：6 个 externalized 记录流（run_records.jsonl 等，合计 312,310,937 B）不在本机（external_path_token=<STATE_ROOT>/p4-route-a/s3_runs/…），无法按原始记录流重算 => 记录级确定性只能 NOT_RUN，仅登记其声明。
- 整改：将外置记录流归档到可复核位置或提供可验证的分布式校验方案。

## 10. 汇总表与阶段建议

| 编号 | 缺陷 | 严重度 | 状态 | 整改门槛 |
| --- | --- | --- | --- | --- |
| F-01 | validate 模型清单路径 | MAJOR | VALID | G1 |
| F-02 | 聚合校验口径 | MAJOR | VALID | G2 |
| F-03 | OOD 正式分析未接入 | MAJOR | VALID | G3 |
| A5-S3M5-03 | wall_s=0 成本不可审计 | MAJOR | VALID | G4 |
| A5-S3M5-02 | NC-15 未计算/仅 sidecar | MAJOR | VALID | G5 |
| — | 4/10 图 NOT_RUN | MINOR | VALID | G6 |
| S3-GOV-01 | A5 M2R 未签发、A7 替代 | BLOCKER | VALID | G7 |
| S3-M0-04/05 | A3 隔离缺口/崩溃无结论 | MAJOR | VALID（文档与矩阵）/NOT_RUN（进程级） | G8 |
| F-04 | plan digest 过严 | MINOR | VALID | 冻结结构后重算 |
| — | record_digest 两套口径 | MINOR | VALID | 单一实现+单测 |
| A7-F-05 | created_utc 陈旧 | MINOR | VALID | 重生成 |
| A7-F-07 | launcher 不入仓 | INFO | VALID | 入仓+固定 sha |
| — | 记录级确定性 | 非缺陷 | NOT_RUN | 外置流可复核 |

阶段建议（A5 立场）：
1. F-01/F-02 是"纯离线、零物理"的修复与重跑，应作为 S4 前置 G1/G2 的最小动作。
2. G7（门禁替代裁定）必须先于任何"S3 已复核"表述；否则 S4 计划书不得引用 S3 为独立双签通过。
3. G3/G4/G5 涉及结论层口径，S4 可以带病启动设计，但不得把 OOD/成本/负控结论带进 S4 的动机证据。
4. 本清单不构成 S3 阶段放行；S3_STAGE_ACCEPTANCE 仍为 NOT_ISSUED，S4 仍为 NOT_APPROVED。

## 11. 声明

- physical_call_count=0；未启动 VSPAERO/SU2/RCAIDE Mission/WaveDrag；所有数值来自归档只读重算或静态代码复现。
- 未替任何未审阅的提交签 PASS；未用提交消息代替复现。
- 审计人未修改 S3 冻结产物、未改写历史、未写其它工作树。
