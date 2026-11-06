# 仓库归档副本（路径脱敏）

本文件由 Lead 从外部记忆区原件归档，仅替换本机绝对路径 token；原件 sha256=7df8d496c9059dae0219d7f5eb139ddbf8dd5f6c7e12ec13b109cef66ddceed5。供 Issue #7 S2 复核链追溯。

# S2 证据包 rev3（12940c5）双哈希/sanitized 标记 delta 审计

- 任务标识：task-257 rev49 / S2-PKG-A3 rev3：证据包 12940c5 双哈希/sanitized delta 审计
- 审计人：a3-repo-guard（A3，只读审计角色）
- 审计时间：2026-11-06T19:28:19Z 起（本地 2026-11-07 03:28 起），约 12 秒事实采集
- 审计对象：source-repo，branch research/p4-route-a-s2，HEAD=origin=12940c5a426e3a1215d53eeb4f41488d4da82926
- 对照基线：27c935e（rev1，前轮 PASS_WITH_WARNINGS）与 625d4b9（rev2，EOL 双哈希修复）
- 审计范围：限定 delta 27c935e..12940c5（及 625d4b9..12940c5）——拓扑、3 文件变更、双哈希/sums 复现、sanitized 与 review 互链、旧件/零物理边界；不评价统计结论

## §0 结论

**VERDICT：PASS_WITH_WARNINGS**

- 自动检查 27 项（C01–C27）全部 PASS，0 FAIL；告警 4 项（W01–W04，均为 info 级披露/口径事项，不阻断）。
- 拓扑：12940c5 单父 625d4b9，625d4b9 单父 27c935e；base..HEAD 恰 2 提交、无 merge；HEAD=upstream、worktree clean。主库 e5140fc、main ec65e5a、PR#3/#6 均未动。
- delta：27c935e..12940c5 恰 3 路径且全 M（README / PACKAGE_MANIFEST / SHA256SUMS，+272/−99）；36 个 payload 文件 git blob 与 27c935e 完全一致；docs 正式报告未变。
- 双哈希口径（B01）：SHA256SUMS 38/38 可由 `git cat-file blob HEAD:<path>` 独立复现（canonical LF）；工作树 raw 哈希与 manifest sha256_raw 38/38 一致；CRLF 恰 7 文件、Δ313 B；rev1 sums 对 7 个 CRLF 文件取的是 raw 字节（clone 不可复现），rev2/rev3 改为 LF 后 7/7 与 blob 一致。
- M01/M03 修复：manifest 5 个脱敏文件 sanitized=true、顶层 sanitization 块 files_count=5 且 numeric_structure_identical=true；review_chain.a5.minor_status_ref 互链 A5-S2R-01 与 A2 校正报告（sha 48e0a274…, §7.4）。rev2(625d4b9) 实测确为 sanitized 全 false、无 sanitization 块、无 minor_status_ref。
- 安全/边界：全包文本绝对路径 0；敏感词 5 处均为 A3 审计报告的扫描关键词枚举文字；19 处 solver token 均为文档说明；9/9 PNG 可解码；0 物理（语义随 36 个未变 payload 继承）；旧件 0 改动。

## §1 范围与方法

只读 delta 审计，未写仓库、未 commit/push、未启 solver、未做 GitHub 写。基于 27c935e 全量审计结论，仅复核本次变更引入的差异与其声明。

- git 只读：rev-parse、log --format、cat-file blob、diff --name-status/--numstat/--shortstat、ls-tree -r -l、ls-remote、status --porcelain。
- 逐文件独立复算：工作树 raw 字节 sha256、`git cat-file blob HEAD:<path>` canonical LF 字节 sha256、git blob sha1；sums 38 条逐条比对；manifest 38 条 bytes_raw/sha256_raw/bytes_lf/sha256_lf/eol 逐条复算。
- 结构核验：manifest schema/条目集合/sha256sums 块/sanitization 块/review_chain；README §8 命令与披露；rev2 快照对照（625d4b9 blob）。
- 安全/解码：绝对路径正则扫描（盘符:/Users、盘符路径、/c/Users、）、敏感词与 solver token 扫描、PNG 全量解码（Pillow 12.3.0）、UTF-8 解码。
- 事实文件：S2_package_isolation_12940c5_facts.json（37,366 B，sha256 ca5bfcd514a3c7d1ca950c386f7503e8683957a6fec8fec721ffd5dee139892a）。采集脚本为 STATE/scripts/a3_s2pkg_12940c5_audit.py（临时工装，非交付）。

## §2 提交拓扑与隔离

| 项 | 实测值 |
|---|---|
| HEAD | 12940c5a426e3a1215d53eeb4f41488d4da82926 |
| 12940c5 parent（单父） | 625d4b9a3e5e210d51e5d0d5512212e33225620f |
| 625d4b9 parent（单父） | 27c935e01211be866fced47eee9f6eb876337513 |
| 分支 / upstream | research/p4-route-a-s2 / origin/research/p4-route-a-s2 = 12940c5（HEAD=upstream） |
| author / date | QingYangJin <118662522+QingYangJin@users.noreply.github.com>，2026-11-07T03:24:20+08:00 |
| subject | S2 evidence package rev3: explicit sanitized flags, sanitization block, review link |
| worktree status / staged | 0 行 clean / 空 |
| base..HEAD 提交数 / merge | 2 / 无（rev1→rev2→rev3 单链） |

远端与主库隔离（审计时刻）：

| ref | SHA | 判定 |
|---|---|---|
| origin/main | ec65e5a9a723bc52df8075a395fcaf9e0fd0fc2b | 未动 |
| origin/research/concorde-metaopt | e5140fc64d348f2d9dcf52962f1dcfc425099341 | 未动 |
| origin/research/p4-route-a-s2 | 12940c5a426e3a1215d53eeb4f41488d4da82926 | = HEAD |
| refs/pull/3/head → merge | e5140fc… → 51f32fc39e24c94e6af635f3c2e94a9503ce3122 | PR#3 未动 |
| refs/pull/6/head → merge | ff6280f7b1c0cb98ebcc31478ffd14858481b711 → f6604958ff90f03c884ee526a7853a313e66d3ad | PR#6 未动 |

主库 primary-repo：HEAD=e5140fc，branch=research/concorde-metaopt，local main=origin/main=ec65e5a9；status --porcelain -uall 6,304 行（7 tracked M + 6,297 untracked），staged 空——与 27c935e 审计时一致，属既有基线漂移。

## §3 delta 文件与字节

27c935e..12940c5 恰 3 路径、全 M：

| 文件 | worktree bytes | sha256_raw | blob bytes(LF) | sha256_lf | git blob sha1 |
|---|---|---|---|---|---|
| README.md | 8,070 | 35d28b789dfe61021c92fa0a502f03c36226700ab47bf63b4d2c1b17960aec28 | 8,070 | 同 raw | 8e57512eecef71eab9ec969ef4d7f19e3fcc5bc8 |
| PACKAGE_MANIFEST.json | 25,960 | 907f2c5ad693b66a2c3915d829509c6eb1d48b51d11d4bd162fe10af616bfc69 | 25,960 | 同 raw | b52a376531b9aa02db2d582f629fd9b0885718a0 |
| SHA256SUMS.txt | 5,665 | 63c661cb517414dafec6292638a48e37ef5dbac24095ae718d3fde7221120ac9 | 5,665 | 同 raw | c5922365c896bc3c18bf0388c6f518f258512314 |

- diff 规模：27c935e..12940c5 = 3 files changed, +272/−99；625d4b9..12940c5（rev3 自身）= 3 files changed, +44/−17（manifest +38/−13、README +5/−3、sums +1/−1），与 Lead 声明一致。
- payload 36 文件（包内除上述 3 文件外全部）git blob sha1 与 27c935e **36/36 完全一致**；docs/reviews 正式报告未在 diff 中（31,771 B sha f97b8eb5…，与 base 同字节）。
- 包内 39 文件的 canonical LF 总量随修订增长：rev1 3,753,620 B → rev2 3,761,083 B → rev3 3,763,650 B；worktree raw 总量 rev3 = 3,763,963 B（Δ313 B 为 7 个 CRLF 文件）。README 5,950 → 7,347 → 8,070 B；manifest 18,050 → 24,116 → 25,960 B；sums 恒 5,665 B。

## §4 双哈希口径与 SHA256SUMS 复现（B01）

SHA256SUMS.txt（rev3）：5,665 B，sha256=63c661cb517414dafec6292638a48e37ef5dbac24095ae718d3fde7221120ac9，38 行、LF（自身 CRLF=0）、38 唯一路径；不含 PACKAGE_MANIFEST.json 与自身。

- **canonical LF 复现 38/38**：对每条 `<sha>  <path>` 执行 `git cat-file blob HEAD:<path> | sha256sum`，逐条独立复算全部匹配（bad=0）。该口径与平台/autocrlf 无关，任何干净 clone 均可复现。
- **工作树 raw 38/38**：manifest 的 sha256_raw/bytes_raw 与当前 Windows 工作树逐文件一致，包括 7 个 CRLF 文件。
- **CRLF 恰 7 文件、Δ313 B**（均为原始 payload，无脱敏）：

| 文件 | bytes_raw | bytes_lf | Δ | sha256_raw 前 8 | sha256_lf 前 8 |
|---|---|---|---|---|---|
| analysis/s2_endpoint_tables.csv | 1,077 | 1,074 | 3 | 5a3dc849 | 5549716b |
| analysis/s2_holm_family.csv | 388 | 385 | 3 | 76ab520e | e72972fa |
| analysis/s2_negative_controls.csv | 3,217 | 3,202 | 15 | e7cd9d85 | d59d824c |
| analysis/s2_null_disclosure.csv | 1,188 | 1,179 | 9 | 0e57d31e | 5faece42 |
| analysis/s2_per_task_aggregates.csv | 25,757 | 25,476 | 281 | d8058d6d | b9e779fe |
| determinism/compare_r1.json | 214 | 213 | 1 | 7378b818 | e105e710 |
| determinism/compare_r2.json | 214 | 213 | 1 | 7378b818 | e105e710 |

B01 关闭证据（rev1 vs rev2/rev3）：

- rev1 sums（5,665 B，sha 7eee5c7c…）对上述 7 个文件使用的是工作树 raw 哈希：7/7 等于当前 worktree raw sha，且 7/7 不等于 git blob LF sha——在干净 clone（LF）上不可复现，即 B01 所指缺陷。
- rev2 sums（5,665 B，sha e21655c3…，取自 625d4b9 manifest.sha256sums 块）与 rev3 sums（63c661cb…）均改为 canonical LF：7/7 等于 blob LF sha。rev3 sums 相对 rev2 再变的原因是 README 字节变化（7,347→8,070，README 在 sums 覆盖内）；7 个 CRLF payload 的 LF 哈希在 rev2→rev3 间不变。

## §5 PACKAGE_MANIFEST 结构与 M01/M03 修复

manifest rev3：25,960 B，sha256=907f2c5ad693b66a2c3915d829509c6eb1d48b51d11d4bd162fe10af616bfc69，schema=p4ra-s2-evidence-package-3，created_utc=2026-11-07T03:33:00Z。

- 条目：files=38；每条含 bytes_raw/sha256_raw/bytes_lf/sha256_lf/eol/category/origin/sanitized（脱敏条目另有 sanitization_rule、numeric_structure_identical）；独立复算 **38/38 全一致、eol 字段 38/38 全对**（bad=0）。
- 集合一致性：manifest 条目集合 = sums 路径集合（38，含 docs 报告）；sha256sums 块 entries=38、bytes=5,665、sha256=63c661cb… 与提交后 sums blob 完全一致。
- **M01 修复（sanitized 显式标记）**：sanitized=true 恰 5 条——analysis/aggregate.json、analysis/s2_prereg_echo.json、reviews/S2_isolation_audit_a3.md、reviews/S2_result_review_a5.md、reviews/S2_result_review_a5_verdict.json；其余 33 条 false。顶层 sanitization 块：files_count=5、files 清单与 5 条一一对应、numeric_structure_identical=true，另含 rule/note/verification（替换 token 为 EXT/…、source-repo、source-repo-worktree、primary-repo、USERPROFILE 等相对标记）。
- **M03 修复（复核互链）**：review_chain.a5_result_review 含 minor_id=A5-S2R-01、minor_status=closed_in_corrected_report、minor_status_ref=“reviews/S2_result_review_a5.md; docs/reviews/p4_route_a_s2_formal_run_report_20261107.md (A2 corrected report sha 48e0a274…, §7.4 null-scope wording)”，同时保留 verdict=APPROVE_FOR_S2_RECEIPT、0 blocker/0 major/1 minor、independent_checks=140 PASS。
- **rev2 缺陷快照确认**：625d4b9 的 manifest（24,116 B）sanitized=true 计数=0、无 sanitization 块、a5 无 minor_status_ref；rev3 三项均已修复，证明 rev3 的 M01/M03 修复非空操作。
- review_chain.a3_isolation_audit：20/20 PASS / 0 FAIL、PASS_WITH_WARNINGS、6 warnings，与前轮 A3 结论一致。

## §6 README 修订核验

README.md：8,070 B，sha256=35d28b789dfe61021c92fa0a502f03c36226700ab47bf63b4d2c1b17960aec28，96 行。

- §8 哈希口径与校验存在，含 canonical LF 复现命令（`git cat-file blob HEAD:... | sha256sum`）与工作树 raw 校验命令。
- 披露齐全：5 个 sanitized=true 文件清单与替换规则、7 个 CRLF 文件与 Δ313 B、rev3 修订说明（revision 3 / sanitized 标记 / 复核互链）、零物理与不合并 main 边界。
- A3 告警 W03（3 个辅助脚本在 EXT 原始树含本机路径、不在包内）在 §7 保留披露。

## §7 安全扫描与可解码性

对包内 40 路径（39 包文件 + docs 报告）的 HEAD blob 全量扫描：

| 项 | 结果 |
|---|---|
| 文本/二进制 | 31 文本 + 9 PNG |
| 本机绝对路径（盘符:/Users、盘符路径、/c/Users、） | **0 命中** |
| 敏感词（BEGIN PRIVATE KEY/password/api_key/secret/credential） | 5 处，全部在 reviews/S2_isolation_audit_a3.md 同 1 行的扫描关键词枚举文字，非真实凭据 |
| solver token（vspaero/su2/openvsp/gmsh/vsp 等） | 19 处，全部为 README/reviews 的“未调用/无”说明文字，无 import/调用 |
| PNG 解码 | 9/9 可解码（Pillow 12.3.0） |
| 文本 UTF-8 | 全部可解码 |

## §8 语义继承（payload 未变 → 27c935e 已审语义不变）

36 个 payload 文件 blob 完全未变，故零物理/零 holdout 语义按位继承；抽查关键字段：

- run_config：run_id=s2-formal-20261106T1810Z，run_mode=FORMAL，physical_call_count=0，counts train/eval/total=1200/4800/6000（expected 同）。
- run_summary：physical_call_count=0，record_counts 1200/4800/6000，failures=[]，resource_stop=null，fd_gate_sha256=7950bcb0…。
- fd_gate：physical_call_count=0，backend=torch，32/32 checks PASS。
- aggregate：overall.decision=SUPPORTED_HARM，primary_decision=SUPPORTED_HARM，evidence_scope=DEVELOPMENT_VALIDATION_ONLY，checks 19 条（18 PASS + 1 DISCLOSED，desc 口径）。
- data_manifest：holdout_rows_used=0、holdout_metrics_read=false、physical_call_count=0。
- manifest.source_run：physical_call_count=0、failed_records=0、holdout_rows_used=0、source_commit=994cda8、parent=f4ab43f。

## §9 旧冻结件与进程边界

- 27c935e..12940c5 diff 路径全部在包内 + 报告之外为 0（diff_outside_package=[]）；无删除/重命名。
- S0-7 冻结包树在 base 与 HEAD 同 tree sha（cd06ed972a7c31fb8144759b2d2d12106ca8b4bd），SHA256SUMS 9/9 OK，sums sha256=59aa81cd…。
- 冻结 prereg 未变：4,916 B，sha256=fde3ef33bab53c67f5f595472a28538b13fbecbc5918903cdc6904c85ad692cd。
- S0-2..S0-6、M2/M5/M6、S1 正式产物均不在 diff 中。
- 进程扫描：288 进程，solver_like=[]；本审计只读，无新物理计算。

## §10 告警（info 级，不阻断）

| ID | 内容 |
|---|---|
| W01 | delta 仅 3 文件；36 个 payload 与 docs 报告字节未变；包 canonical LF 总量 rev1→rev3 增 10,030 B（README +2,120、manifest +7,910，sums 不变） |
| W02 | sums/工作树双哈希口径差异仅来自 7 个 CRLF 文件（Δ313 B）；manifest 同时记录两套哈希，属预期 |
| W03 | 5 个脱敏文件“绝对路径→相对标记”已显式 sanitized=true，数值/结构不变（numeric_structure_identical=true）；脱敏 token 清单按 manifest 说明不在包内 |
| W04 | 主库 primary-repo 既有 6,304 行 status 漂移（7 M + 6,297 untracked）与本包无关，属既有基线 |

## §11 检查清单（C01–C27，27/27 PASS）

| ID | 检查项 | 结果 |
|---|---|---|
| C01 | 12940c5 单父=625d4b9，625d4b9 单父=27c935e | PASS |
| C02 | HEAD=origin=12940c5 且 worktree clean | PASS |
| C03 | base..HEAD 恰 2 提交、无 merge | PASS |
| C04 | 主库 e5140fc / main ec65e5a / 无 staged | PASS |
| C05 | PR#3/#6 head/merge 与基线一致（未动） | PASS |
| C06 | 27c935e..12940c5 恰 3 路径且全 M | PASS |
| C07 | rev2→rev3 两跳 3 文件、+44/−17 | PASS |
| C08 | 3 个变更文件 bytes/sha 与 Lead 声明一致 | PASS |
| C09 | payload 36 文件 git blob 与 27c935e 完全一致 | PASS |
| C10 | docs 正式报告未变（31,771 B / f97b8eb5…） | PASS |
| C11 | SHA256SUMS 38 条 canonical-LF 逐条由 git blob 复现 | PASS |
| C12 | sums 覆盖恰 38 唯一路径、无 manifest/自身 | PASS |
| C13 | 工作树 CRLF 恰 7 文件（与 manifest eol_summary 一致） | PASS |
| C14 | manifest 38 条双哈希字段独立复算全一致 | PASS |
| C15 | manifest eol 字段 38/38 与实际一致 | PASS |
| C16 | manifest 条目集合 = sums 路径集合 | PASS |
| C17 | manifest.sha256sums 块与提交后 sums blob 一致 | PASS |
| C18 | M01：5 文件 sanitized=true = sanitization.files、numeric_structure_identical=true | PASS |
| C19 | M03：review_chain.a5.minor_status_ref 互链 A5-S2R-01 与校正报告 | PASS |
| C20 | rev2 确有 M01/M03 缺陷、rev3 已修 | PASS |
| C21 | README §8 命令与 5/7/rev3 披露齐全 | PASS |
| C22 | 全包文本无本机绝对路径 | PASS |
| C23 | PNG 9/9 可解码 | PASS |
| C24 | 零物理/零 holdout 语义与 27c935e 一致 | PASS |
| C25 | 旧件 0 改动（S0-7 树与 sums、prereg 未变） | PASS |
| C26 | 无求解器进程（288 进程扫描） | PASS |
| C27 | B01 关闭：rev1 raw sums 对 7 CRLF 文件不可复现、rev3 canonical LF 7/7 可复现 | PASS |

## §12 交付文件

均写入项目外目录 EXT/p4-route-a/a3/：

| 文件 | 字节 | sha256 |
|---|---|---|
| S2_package_isolation_12940c5.md（本报告） | 见 SHA256SUMS.txt | 见 SHA256SUMS.txt |
| S2_package_isolation_12940c5_facts.json | 37,366 | ca5bfcd514a3c7d1ca950c386f7503e8683957a6fec8fec721ffd5dee139892a |
| SHA256SUMS.txt | 见文件 | 见文件（2 行 LF，覆盖报告与 facts） |

## §13 声明与限制

- 只读：未修改/新建/删除任何仓库文件，未 git add/commit/push/checkout/stash，未 GitHub 写、未评论、未合并 PR。
- 零物理：未启动任何 solver（Mission/VSPAERO/SU2/Gmsh/DOE/BO/DE/MAML 训练），timeline 与 27c935e 一致。
- 本报告为限定 delta 审计，不重复 27c935e 全量结论；统计结论评价属 A5 职责。
- 30 分钟内完成，符合 Lead 时限。
