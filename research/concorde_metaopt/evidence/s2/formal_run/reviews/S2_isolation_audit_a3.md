# S2 正式 Run 提交隔离与证据完整性只读审计报告

- 任务标识：task-257（revision 40，Lead 请求 m07517，board 满额亦不影响本任务）
- 审计者：A3（a3-repo-guard），只读审计角色
- 审计窗口：2026-11-06T18:24:21Z – 2026-11-06T18:41:16Z（本地 2026-11-07 02:24–02:41 +08:00）
- 审计对象：run_id = s2-formal-20261106T1810Z；源提交 source-repo @994cda8e0942060072d65eb50dde790c44d32194；执行 worktree source-repo-worktree（detached @994cda8）；run 根 EXT/p4-route-a/a2/s2_formal/s2-formal-20261106T1810Z；授权文件 S2-FORMAL-AUTH-20261106T1805Z
- 交付目录：EXT/p4-route-a/a3/
- 配套证据：S2_formal_run_isolation_audit_facts.json（114,341 B，sha256 = d5b0a8f988e32d410a3edb77bb88c8d281f1d232618b397254bacc0b758346c5）

## §0 结论

**VERDICT：PASS_WITH_WARNINGS**

- 20/20 项检查 PASS，0 FAIL，0 DISCLOSED（A3 检查项层面；run 内部 aggregate 有 1 项 DISCLOSED，见 §7/§11 W04）。
- 提交隔离、SHA256SUMS 完整性、预算/物理/资源、确定性、披露与边界保护全部符合 Lead 派单与授权要求。
- 物理调用 0（config/summary/fd_gate/aggregate 负控/data_manifest 五方交叉一致），无求解器进程、无求解器命令行、无仓库写、无 GitHub 写。
- 6 项 info 级告警 W01–W06（均为披露/措辞/既有漂移类，不影响 run 证据有效性）：见 §11。
- 本审计只读：0 仓库写、0 文件删除/移动、0 solver、0 GitHub 写；所有交付写入项目外 EXT 目录。

## §1 审计范围与方法

按 Lead 派单五方面逐项核对：①提交/隔离；②证据完整性（SHA256SUMS 60 条）；③预算/物理/资源；④确定性；⑤披露与结论口径。方法：

- 只读 git 命令（log/diff/ls-tree/rev-parse/status/ls-remote 只读），未做任何写操作；
- 对 run 树全部 61 个文件独立重算 sha256 与字节数，并独立解析、重算 SHA256SUMS.txt 全部 60 条；
- 独立解析 run_config/run_summary/run_records/aggregate/fd_gate/data_manifest/compare/figure_status/negative_controls 等 JSON/CSV；
- 独立按源码 s2_runner.records_core_sha256 口径重算 base/r1/r2 三跑核心记录摘要；
- 进程扫描（Get-Process）确认无求解器进程；
- 对旧冻结包逐文件校验 SHA256SUMS，并核对其 git tree 在 f4ab43f..994cda8 区间无改动。

边界声明：不评价统计结论正确性（A5 职责）；不启动任何求解器；不修改/移动/删除任何仓库文件；不读取 .agents/github Token.txt 内容。

## §2 提交与隔离（C01–C05）

### 2.1 源提交 994cda8

| 项 | 实测值 |
|---|---|
| HEAD | 994cda8e0942060072d65eb50dde790c44d32194 |
| 父提交 | f4ab43f141a265ada8e6d8ca0a80a307df3215e8（单父） |
| tree | 0992b011d78729ba2ea6699669186ce6c6351ba1 |
| 作者/时间 | QingYangJin <118662522+QingYangJin@users.noreply.github.com> / 2026-11-07T01:44:03+08:00 |
| subject | S2 prereg freeze: p4ra-s2-prereg-2751c162904d5a4f |
| f4ab43f..994cda8 diff | 仅 1 文件新增：A research/concorde_metaopt/evidence/s2/s2_preregistration.json（+1/−0） |
| merge commit 数 | 0；rev-list --left-right --count = 0/1 |
| 冻结 prereg | worktree 4,916 B，sha256 = fde3ef33bab53c67f5f595472a28538b13fbecbc5918903cdc6904c85ad692cd（与授权 prereg_raw_sha256 一致）；git blob sha1 = aa3e16e773efee8793dd5fd5524ac7502ab48b79 |

evidence/s2 目录在 994cda8 共 3 个文件：s2_fd_pilot_micro.json（blob ad1e9e2e）、s2_fd_pilot_full.json（blob 92bd986c）、s2_preregistration.json（blob aa3e16e7）。代码与已审计的 f4ab43f 逐字节一致（区间仅 1 文件新增）。

### 2.2 工作树与主库

| 工作树 | HEAD | 分支/状态 |
|---|---|---|
| source-repo | 994cda8e… | research/p4-route-a-s2；origin 同 SHA；status 0 行（clean）；无未合并提交 |
| source-repo-worktree | 994cda8e… | detached HEAD；status 0 行（clean） |
| primary-repo（主库） | e5140fc64d348f2d9dcf52962f1dcfc425099341 | research/concorde-metaopt；local main = origin main = ec65e5a9a723bc52df8075a395fcaf9e0fd0fc2b |

主库工作区为本阶段无关的既有漂移：status -uall 6,304 行（7 个 tracked M + 6,297 未跟踪），staged 为空；7 个 tracked M 精确为 research/concorde_metaopt/{README.md, cli.py, optimization_runs/index.json, reports/figures.py} 与 tutorials/Optimization_Wing_Planform_Fuel_Burn/{Differential_Evolution.py, README_DE.md, Save_Results.py}，diffstat = 7 files changed, +586/−123。A3 本轮未触碰。P5 受保护快照用官方口径重算 = 54 files / 7,976,412 B / agg sha256 66782c981aba3c609df1e4ea1e232e8425c640d30d790f63c233b08648fa5236，与基线一致。

### 2.3 远端 refs 与 PR（独立 ls-remote，只读，rc=0）

| ref | SHA |
|---|---|
| refs/heads/main | ec65e5a9a723bc52df8075a395fcaf9e0fd0fc2b |
| refs/heads/research/concorde-metaopt | e5140fc64d348f2d9dcf52962f1dcfc425099341 |
| refs/heads/research/p4-route-a-s2 | 994cda8e0942060072d65eb50dde790c44d32194 |
| refs/pull/3/head | e5140fc64d348f2d9dcf52962f1dcfc425099341 |
| refs/pull/3/merge | 51f32fc39e24c94e6af635f3c2e94a9503ce3122 |
| refs/pull/6/head | ff6280f7b1c0cb98ebcc31478ffd14858481b711 |
| refs/pull/6/merge | f6604958ff90f03c884ee526a7853a313e66d3ad |

main 与上一轮一致；PR#3/#6 未合并、未变动。

## §3 证据完整性（C06–C08）

### 3.1 SHA256SUMS.txt 独立复核

- 文件：run 根 SHA256SUMS.txt，6,570 B，sha256 = d7f68960a8b181f9c31f574e300a723d1031ec222dab04bb4a60bdd5559fac39，60 行（LF）。
- 独立重算：60/60 条全部匹配，bad = []；列出文件字节合计 8,166,179 B。
- 覆盖完整性：run 树实际 61 个文件；60 条正好覆盖除 SHA256SUMS.txt 自身以外的全部文件，无缺失、无多余（files_not_listed = ["SHA256SUMS.txt"]）。
- 首条 determinism/r1/data_manifest.json，末条 s2_formal_launcher.cmd。

### 3.2 run 主产物哈希（与 Lead 派单声明逐项一致）

| 文件 | 字节 | sha256 |
|---|---|---|
| run_config.json | 3,939 | 9522d467f6b6fcc0bdd75694966d111f36a0ec4ae6c02eb4b98367fc5a6853e0 |
| run_records.jsonl | 2,186,063 | 32fbd2c65b6eb6e50e1bb3ca338a0b7da0a90e196242721961c73f344e0a9a25 |
| run_summary.json | 3,908 | 77d10cd62bc7295dc5d9d2477bed02bb9d83c627448356d421e8c657c652335e |
| fd_gate.json | 8,795 | 7950bcb05d322a41b0688e752b270ac47df6c97ed912b9fd83dd7023a8d5dec6 |
| data_manifest.json | 2,603 | 8809813911478c6287dfe45727b4d7f6ac0b70e5cfc50eaa37ddbc8ef887ecef |
| analysis/aggregate.json | 45,846 | 16d7a4d3eca2b4e59e92d66cfbfaa3a543f4a2d0503dcd1acaf7eb7384af8463 |
| analysis/figure_status.json | 1,482 | 7c216ba3db35c88cc5b4a8d7dd3f4606e906afc13785b0d2f716495cc3672fae |
| logs/timeline.txt | 210 | 4096c97cb37309a140bf689e66a1792275decadfed18f1df09b85b7a1d893209 |
| s2_formal_launcher.cmd | 2,678 | dd33468baa881aa5a073ad757c6c8c877d379e00be7db9483e37503d7a981d05 |
| s2_formal_facts.json（A2 侧事实） | 48,584 | 78f3d80ca6720ea2fa4ddffd11e74bf2c0779cd90e4ebaf66aef138b1704373b |

determinism r1：run_config 3,939 B/9522d467；run_summary 3,922 B/88be3322…；run_records 2,186,357 B/fefa6c07…；fd_gate 8,795 B/7950bcb0；data_manifest 2,603 B/88098139。r2：run_config 同；run_summary 3,911 B/931d5576…；run_records 2,186,421 B/5ca9dab4…；fd_gate/data_manifest 同（完整清单见 facts JSON inventory 61 条）。

### 3.3 A2 报告/授权/A5 判决

| 文件 | 字节 | sha256 | 说明 |
|---|---|---|---|
| STATE/p4-route-a/a2/S2_formal_run_report.md | 31,383 | 20ee8874cc7831c53e96d0c27b9761d4ac2b95998f0c9f5e591c9d58f02a0cb2 | 361 行，rev1，与 Lead 声明一致 |
| STATE/p4-route-a/lead/S2_FORMAL_RUN_AUTHORIZATION.json | 4,762 | eb1fd0ee7fd87a51c3c31ea0a5a6a5a84de61a99f2ac9a92ccc6991ef76c9d0a | id S2-FORMAL-AUTH-20261106T1805Z，issued 2026-11-06T18:05:56Z |
| STATE/p4-route-a/lead/S2_FORMAL_RUN_AUTHORIZATION.md | 2,310 | 67425ca39ee0a8ff5b1aa3ddae16f28a5281fa917d79561f23d84779a0198f2b | 授权 MD |
| STATE/p4-route-a/a5/S2_prereg_verification/verdict.json | 3,322 | 282984a05e23fa7342ce7e0639210608637cd3382d84d221e147a86769b5de1e | task-256 rev44，APPROVE_FOR_S2_RUN，21 gates 全 PASS，0B/0M/1 minor+3 obs |
| STATE/p4-route-a/a5/S2_delta_verdict.json | 1,764 | 18467e0bf92436c1bab75100e974ccd1e851efc236a0ded65de15ebc7a9362b1 | task-256 rev40，APPROVE_FOR_S2_FORMAL，0B/0M/3 minor；1,174 tests OK skipped=1，471.5 s |

A2 报告 §14 及正文 22 项字节+sha 声称（run 5 文件、aggregate、6 个 CSV、prereg echo、figure_status、timeline/stdout/compare 日志、launcher、facts json、9 图字节）与磁盘实测 0 mismatch。

授权约束核对：run_mode FORMAL；预算 arms 2 × train 1200 + eval 4800 = 6000；seeds [0,1,2]；outer_steps 200；K [0,1,5,10] × draws 10 × 20 tasks；资源 caps 7,200 s / 每 seed 1,200 s / 峰值 8,192 MB；physical 0；solver 0；allowed splits 仅 meta_train/meta_validation；holdout_rows 0；repo_write / commit_or_push / github_write / merge_main 均 false。以上均在 run_config/run_summary/aggregate/manifest 中逐项成立（§4/§5）。

## §4 run 产物结构

run 树共 61 个文件，合计约 8,172,749 B（60 条 SHA256SUMS 列出 8,166,179 B + sums 自身 6,570 B）：

| 区域 | 文件数 | 内容 |
|---|---|---|
| run 根 | 5 | run_config / run_records / run_summary / fd_gate / data_manifest |
| determinism/r1、r2 | 10 | 每次 5 文件（run_config / run_records / run_summary / fd_gate / data_manifest） |
| analysis/ | 26 | aggregate、6 CSV、prereg echo、figure_status、9 图 |
| logs/ | 15 | 5 个步骤 stdout（base/r1/r2/validate/analysis）、7 个 stderr（5 步骤 + compare×2，全部 0 B）、compare_r1/r2.json、timeline.txt |
| run 根辅助 | 5 | extract_s2_facts.py、make_sums.py、s2_formal_facts.json、s2_formal_launcher.cmd、SHA256SUMS.txt |

run_config（p4ra-s2-run-config-v2）关键字段均与授权一致：run_mode FORMAL、physical_call_count 0、counts train 1200/eval 4800/total 6000（expected 与 actual 相等）、training_budget seeds [0,1,2]/outer_steps 200、evaluation_grid K [0,1,5,10]/draws 10/tasks 20、arms FULL_MAML（first_order=false）与 FOMAML（first_order=true）其余超参完全相同、data_boundary holdout_rows_used 0/holdout_metrics_read false、determinism fail_closed true/reruns 2、fd_gate 32/497 mode full max_rel 1.14476e-09 tolerance 1e-6 status PASS、frozen_package S0-7 code_sha 7304d32e…/git_sha 004156c2…/sums 59aa81cd…、resource_limits 8192/1200/7200、evidence_scope DEVELOPMENT_VALIDATION_ONLY、scope_notes lifting_surfaces_only = NOT_APPLICABLE（S2 无 VLM/CFD）。

## §5 预算、物理与资源（C09–C11）

- 记录数：train 1,200（expected 1,200）+ eval 4,800（expected 4,800）= 6,000；status：train OK 1200 / FAILED 0，eval OK 4800 / FAILED 0；failures = []，resource_stop = null。
- 物理：run_config.physical_call_count = 0、run_summary.physical_call_count = 0、fd_gate.physical_call_count = 0、aggregate 负控 NC-01 PASS（prereg=0;run_config=0）、data_manifest holdout_rows_used = 0 / holdout_metrics_read = false。五方交叉一致，物理 0 成立。
- 资源（summary.resources）：base run_wall_s = 25.67694490007125；wrapper 总墙钟由 timeline START→ALL_DONE = 101.57 s（2026-11-07 02:10:35.70 → 02:12:17.27 +08，即 18:10:35.70Z→18:12:17.27Z）；单 (arm, meta_seed) 训练墙钟最大 3.713840300333686 s（FULL_MAML seed1，限额 1,200 s，占 0.31%）；单 arm 峰值内存最大 261.57421875 MB（FOMAML，限额 8,192 MB，占 3.19%）；总限额 7,200 s。
- 时间线：timeline.txt 记录 START 与 7 个步骤退出码（BASE/R1/R2/VALIDATE/COMPARE_R1/COMPARE_R2/ANALYSIS_EXIT=0）及 ALL_DONE；7 个 stderr 日志全部 0 B；无 RESOURCE_LIMIT、无重试、无人工干预。
- 环境：python 3.11.17 / numpy 2.4.6 / torch 2.8.0+cpu / Windows-10-10.0.26200。

## §6 确定性（C12）

- 3 份 run_config（base、r1、r2）字节完全一致，sha256 均为 9522d467…。
- run_summary.run_records_core_sha256 = c9460daedbf1868b44e7f2cb5456d6d95da2cbeb64cd692f94e1a5050dafb08f；A3 独立按源码 s2_runner.records_core_sha256 口径（排除 wall_s、peak_memory_mb；canonical JSON sort_keys、separators=(',',':')、ensure_ascii=False + 换行）对 base/r1/r2 三份 run_records 重算，三跑均等于 c9460dae…（MATCH）。
- logs/compare_r1.json 与 compare_r2.json（各 214 B）7 个字段全 true：episode_bank_sha256_equal、fd_gate_sha256_equal、ok、record_counts_equal、run_config_byte_identical、run_records_core_equal、run_records_core_sha256_equal。
- r1/r2 整文件 run_records sha（fefa6c07…/5ca9dab4…）与 base（32fbd2c6…）不同，仅因 wall_s/peak_memory_mb 计时字段波动；核心记录摘要三跑一致，确定性成立。
- aggregate.integrity.determinism 按 NOT_VERIFIABLE_IN_ANALYSIS 披露（分析层不伪造 PASS），由 run 层 compare + A3 独立重算承载（见 §11 W06）。

## §7 FD gate、负控与图（C13–C15）

- fd_gate.json（8,795 B，7950bcb0…）：mode full，n_checked 32，32/32 PASS，max relative_error 1.144759989428372e-09 < tolerance 1e-06，physical_call_count 0；pilots micro（1db9d7d6…，n=32，max_rel 1.2780446719818776e-09）与 full（e8f425ad…，n=8，max_rel 3.975211759696654e-10）sha 均已核验。
- 负控 s2_negative_controls.csv：14 行，13 PASS + 1 DISCLOSED（NC-10 determinism：分析层不可从输入验证，按披露而非 PASS）。其余 NC-01..09、11..14 全 PASS。
- 图：figure_status.json（p4ra-s2-figure-status-1，generated 2026-11-06T18:12:17+00:00）n_figures=9 / n_rendered=9 / n_not_run=0 / n_not_applicable=0；9 个 PNG 均存在且字节与 A2 报告声明一致（fig1 356,777 B … fig9 155,922 B，完整清单见 facts JSON figures 段）。

## §8 结论口径与披露（C16）

- aggregate.overall：decision = SUPPORTED_HARM；primary_endpoint = post_adaptation_rmse_raw_k5；secondary k10 = SUPPORTED_HARM；development_set = meta_validation；evidence_scope = DEVELOPMENT_VALIDATION_ONLY。
- 端点数值（与 A2 报告逐字段一致）：

| 端点 | FULL_MAML mean / median | FOMAML mean / median | 中位差 | 95% CI | Holm p | 相对改善 | n_pairs |
|---|---|---|---|---|---|---|---|
| k5（primary） | 1.0096595945946287 / 0.9541571205352783 | 0.9589177466107437 / 0.9228326803629854 | 0.03132444017229297 | [0.04110944269599093, 0.05986980980200832] | 3.814697265625e-06 | −0.03394379158741091（FULL 更差） | 20 |
| k10（secondary） | 0.9097952349242538 / 0.9102146042296693 | 0.9003567157566167 / 0.8957137631101255 | 0.01450084111954375 | [0.007323951140872326, 0.011701881656536987] | 3.814697265625e-06 | −0.016189146261628796（FULL 更差） | 20 |

- Holm 族唯一（s2-primary-secondary-2tests，family_size=2）；null_rate 全 0；coverage complete = true；negative_controls 全 PASS。
- A2 报告披露一致性（独立计数）：A5-S2PR-01 出现 4 次、OBS-01 3 次、OBS-02 2 次、DEVELOPMENT_VALIDATION_ONLY 2 次、"不可外推" 1 次、holdout 15 次、SUPPORTED_HARM 8 次；含 101.57 / 261.57 / 3.7138 / 6000 等关键资源数字。报告明确 "仅 meta_validation 开发集、不可外推、负结果"，未夸大 benefit，符合 Lead 要求。

## §9 旧证据与冻结件保护（C19–C20）

在 s2-dev worktree（994cda8）按包内 SHA256SUMS.txt 逐文件独立复核；并核对 git diff f4ab43f..994cda8 对这些优化包目录无改动：

| 包 | 文件数 | sums 条目/通过 | sums sha256（前 16） | git tree（前 16） |
|---|---|---|---|---|
| p4ra-s0-2-freeze-20261105T072500Z | 11 | 8/8 | 06a45b2ac3e90e3b | c23669792913c09b |
| p4ra-s0-3-freeze-20261105T155925Z | 11 | 8/8 | 64d85389320b356e | 9fe56f8347861684 |
| p4ra-s0-4-freeze-20261105T201800Z | 11 | 9/9 | 6315e4e132ad5fc6 | 0252b3a731a5f995 |
| p4ra-s0-5-freeze-20261105T215000Z | 11 | 9/9 | c71228675aacd01d | f92f2940a144b8cf |
| p4ra-s0-6-freeze-20261106T003500Z | 11 | 9/9 | 4c12927dff0189a5 | 7a210483569c95ca |
| p4ra-s0-7-freeze-20261106T024200Z | 11 | 9/9 | 59aa81cdc1f1abdc | cd06ed972a7c31fb |
| p4-meta-m2-offline-20261102T092828Z | 27（git） | 无 SHA256SUMS（已知限制） | — | 2b840a6f496c44d1 |
| p4-meta-m5-formal-20261104T1018Z | 37（git） | 36 条 = 35 通过 + 1 行文件头注释 | c5ab020d1d197a91 | 2d38c1c27c4fd6c4 |
| p4-m6-formal-20261105T0118Z | 33（git） | 31/31 | 535946e17588616f | 34b6125f65c980b4 |

S1 正式产物（merged 6 + analysis 14 = 20 文件）与 EXT/p4-route-a/a3/S1_att3_final2_facts.json 中记录的期望 sha256 逐文件比对：20/20 匹配，0 mismatch，未改动。

## §10 安全与边界（C17–C18）

- 求解器 token 扫描（VSPAERO/SU2/Gmsh/OpenVSP/WaveDrag/Mission）：run 树 0 命中；"CFD" 仅出现在 run_config/run_summary 的 scope_notes 说明（"S2 无 VLM/CFD"），base/r1/r2 各 1 次。
- 敏感词扫描（BEGIN PRIVATE KEY/ghp_/github_pat/AKIA/password/api_key/secret/token/credential 等）：0 命中。
- 本机绝对路径：仅 3 个辅助脚本各含 1 次 USERPROFILE（extract_s2_facts.py、make_sums.py、s2_formal_launcher.cmd），不含凭据（W03）。
- 进程扫描：审计时系统 287 个进程 / 104 类，solver_like = {}，python 进程 1 个（即 A3 审计脚本自身）；run 结束后无 solver 进程（A2 报告亦声明）。
- 本审计边界：0 仓库写、0 commit/push、0 GitHub 写、0 solver 调用、0 文件删除/移动；仅向 EXT 目录写入 3 个交付文件。

## §11 告警（W01–W06，均为 info 级）

- W01 路径前缀：Lead 消息写 run 根 EXT/p4-route-a/a2/s2_formal/，实测在 STATE/p4-route-a/a2/s2_formal/（STATE = EXT）。属既有约定差异，非本次产物问题。
- W02 报告计数措辞：A2 报告 §2 L261 称 "执行命令仅 8 条 python -m 调用"，但枚举为 7 条（run×3 + validate×1 + compare×2 + analysis×1）；timeline.txt 仅 7 个 *_EXIT 行；执行前 preflight（报告 §2 L46，EXIT=0）单独执行且其日志未归档于 run/logs/。"8" 可能指 7 步 + wrapper 自身退出码，建议回执中校准措辞。
- W03 本机绝对路径：3 个辅助脚本各含 USERPROFILE 路径（与 P4-M5 同类已知披露），不含凭据；归档/发布时建议注明。
- W04 aggregate 1 项 DISCLOSED：run_records_core_sha256 口径未在接口文档定义，分析层不伪造 PASS，按 DISCLOSED 披露；A3 已独立重算三跑一致，属可接受披露。
- W05 主库既有漂移：primary-repo status -uall 6,304 行（7 tracked M + tools/ 等未跟踪）为历史工作，与本阶段无关；A3 未触碰，P5 保护快照与基线一致。
- W06 分析层确定性口径：aggregate.integrity.determinism = NOT_VERIFIABLE_IN_ANALYSIS（不伪造 PASS），确定性由 run 层 compare + A3 独立重算合取成立。

## §12 检查清单汇总

| 检查 | 方面 | 内容 | 结果 |
|---|---|---|---|
| C01 | 提交隔离 | 994cda8 单父、仅新增冻结 prereg 1 文件 | PASS |
| C02 | 提交隔离 | s2-dev HEAD=origin 且 clean、无新提交 | PASS |
| C03 | 提交隔离 | a2formal worktree detached @994cda8 且 clean | PASS |
| C04 | 提交隔离 | 主库 e5140fc / main=origin main=ec65e5a 未动，7 tracked M 为本阶段无关既有项 | PASS |
| C05 | 提交隔离 | PR#3/#6 refs 未动、未合并 main | PASS |
| C06 | 证据 | SHA256SUMS 60 条独立重算全匹配、覆盖完整 | PASS |
| C07 | 证据 | run 5 个主产物字节/sha 与声明一致 | PASS |
| C08 | 证据 | A2 报告/授权/A5 判决哈希记录且存在 | PASS |
| C09 | 预算 | 1,200+4,800=6,000，0 FAILED，无 failures/resource_stop | PASS |
| C10 | 预算 | physical_call_count = 0（五方交叉）、holdout 0 读取 | PASS |
| C11 | 预算 | 资源上限内：101.57 s / 261.57 MB / 3.7138 s | PASS |
| C12 | 确定性 | r1/r2 compare 全 true、3 份 config 字节一致、core sha 三跑一致（独立重算） | PASS |
| C13 | FD gate | 32/32 PASS、max_rel 1.14e-09 < 1e-06、mode full | PASS |
| C14 | 负控 | 14 项 = 13 PASS + 1 DISCLOSED（NC-10） | PASS |
| C15 | 图 | 9/9 RENDERED、0 NOT_RUN | PASS |
| C16 | 披露 | A5-S2PR-01/OBS-01/OBS-02、DEVELOPMENT_VALIDATION_ONLY、负结果、不可外推 | PASS |
| C17 | 安全 | 无 solver token、无敏感词、仅 3 脚本含本机路径 | PASS |
| C18 | 边界 | 0 solver 进程、0 仓库写、0 GitHub 写 | PASS |
| C19 | 冻结件 | S0-2..S0-7 与 M2/M5/M6 校验通过、git tree 未变 | PASS |
| C20 | 冻结件 | S1 正式产物 20 文件未改（20/20 匹配历史期望） | PASS |

## §13 交付文件

均位于 EXT/p4-route-a/a3/：

| 文件 | 字节 | sha256 |
|---|---|---|
| S2_formal_run_isolation_audit.md（本报告） | 见 SHA256SUMS.txt | 见 SHA256SUMS.txt |
| S2_formal_run_isolation_audit_facts.json | 114,341 | d5b0a8f988e32d410a3edb77bb88c8d281f1d232618b397254bacc0b758346c5 |
| SHA256SUMS.txt | 见文件 | 见文件 |

SHA256SUMS.txt 为 2 行 LF 格式，覆盖本报告与 facts JSON；A3 已独立校验 2/2 OK。审计中间脚本位于 STATE/scripts/（a3_s2formal_audit*.py、a3_s2formal_facts_builder.py），非交付物。

## §14 声明与限制

1. 本审计为只读审计：未修改、新建（除 EXT 交付）、删除或移动任何仓库文件；未 git add/commit/push/checkout/stash；未做 GitHub 写操作。
2. 未启动任何求解器、未做任何新物理计算；未评价统计结论正确性（A5 职责），仅核对执行事实与产物完整性/一致性。
3. 快照时点：2026-11-06T18:24:21Z–18:41:16Z；此后文件变化不在本报告范围。
4. 未读取 .agents/github Token.txt 内容，仅确认其不在本 run 产物与交付范围内。
5. 本报告所有数字均可由 facts JSON 的 inventory/key_files/checks/warnings 段及所列路径+字段复核。

VERDICT: PASS_WITH_WARNINGS
