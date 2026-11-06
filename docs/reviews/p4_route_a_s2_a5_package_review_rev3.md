# 仓库归档副本（路径脱敏）

本文件由 Lead 从外部记忆区原件归档，仅替换本机绝对路径 token；原件 sha256=ff996b57004d4013c034fa2ef527b156db4635337e3d9cbf8a9a22afc7f4a80a。供 Issue #7 S2 复核链追溯。

# S2 证据包 rev3 独立复核报告（A5）

- **对象**：source-repo，branch research/p4-route-a-s2，HEAD=origin=12940c5（rev2 625d4b9 + rev3 12940c5；父 27c935e）。
- **复核工作树**：review-worktree（git worktree --detach 12940c5，HEAD 一致，git status 干净）。
- **最终判决**：**APPROVE_FOR_S2_RECEIPT_PACKAGE**；0 blocker / 0 major / 2 minor（均不阻断回执）。
- **边界**：只读复核；未修改仓库、未 commit/push/checkout/stash、未启动求解器/物理计算、未写 GitHub；仅用 primary-repo/envs/RCAIDE/python.exe 做哈希、JSON/CSV/PNG/文本解析与探针。

## 1. 限定 diff 与 payload 不变性

- `git -C review-worktree diff --name-status 27c935e..12940c5` 恰 3 个文件：PACKAGE_MANIFEST.json、README.md、SHA256SUMS.txt。
- 38 条 entries 中，包内 payload 37 条；除 README 外的 **36 个包内 payload** blob 与 27c935e 逐字节相同；仓库 docs/reviews 正式报告 31,771 B / f97b8eb5… 也未变。
- rev2（625d4b9）建立双哈希与 canonical-LF sums；rev3（12940c5）只修正 sanitized 标志、脱敏规则与 review_chain 互链；未改任何统计结果/图像/CSV 内容。
- 工作树 git status 为空；A5 未对仓库产生 tracked 写操作。

## 2. PACKAGE_MANIFEST / SHA256SUMS 双口径独立复算（全部 PASS）

在 12940c5 的干净 worktree 上，逐条执行：读取 manifest 的 38 条 entries；对每条取工作树 LF 字节与 `git cat-file blob HEAD:<path>` 的 blob 字节；按 eol 重建 raw 字节；与 SHA256SUMS 对照。结果：

| 检查项 | 结果 | 证据/说明 |
|---|---|---|
| PACKAGE_MANIFEST 自身 bytes/sha | PASS | 25,960 B / 907f2c5ad693b66a2c3915d829509c6eb1d48b51d11d4bd162fe10af616bfc69 |
| SHA256SUMS 自身 bytes/sha | PASS | 5,665 B / 63c661cb517414dafec6292638a48e37ef5dbac24095ae718d3fde7221120ac9 |
| entries 数 / sums 行数 | PASS | 38 / 38；path 集合完全一致，无重复、无额外 payload |
| 38 条 sha256_lf / bytes_lf 与 git blob | PASS | 38/38 与 `git cat-file blob HEAD:<path>` 逐字节一致 |
| 38 条 sha256_lf 与 SHA256SUMS | PASS | 38/38 一致；sums 为 canonical-LF 口径 |
| 38 条 raw 双哈希 | PASS | 38/38：7 条 CRLF 的 bytes_raw 由 LF 重建后与声明一致；31 条 LF 直接一致 |
| eol 计数 | PASS | CRLF 恰 7 条，LF 31 条；eol_summary.crlf_count=7，清单与实际一一对应 |
| 总字节 | PASS | 38 条 bytes_lf 合计与实际 LF 文件总字节一致；raw 合计 3,761,989 B，LF 合计 3,761,676 B（Δ313 B 为 7 文件 CRLF 数） |
| manifest 的 sha256sums 元数据 | PASS | entries=38、bytes=5,665、sha256=63c661cb…、hash_mode=git_blob_canonical_lf、coverage 明确不含 manifest 与自身 |
| 重复/缺失/额外 | PASS | 0 重复；0 缺失；0 额外；报告条目在仓库 docs/reviews 下，其余在包内 |

独立 probe：EXT/p4-route-a/a5/S2_package_review_rev3/probe.py；结果 probe_results.json：31 checks / 0 mismatch。

## 3. 脱敏标志与规则（B01/M01 关闭）

- manifest 38 条中 **5 条 sanitized=true**：analysis/aggregate.json、analysis/s2_prereg_echo.json、reviews/S2_result_review_a5.md、reviews/S2_result_review_a5_verdict.json、reviews/S2_isolation_audit_a3.md；其余 **33 条 sanitized=false**（含 README、报告、原始 run_config/run_summary/run_records/fd_gate/data_manifest、图像/CSV 等）。
- 顶层 sanitization 块包含 files（5 条）、files_count=5、rule、note、numeric_structure_identical=true、verification；与 per-file 标志、README.md:77 的披露三方一致。
- 5 个脱敏文件的实际内容与 EXT 原始文件相比只替换了路径字符串标记（EXT/…、source-repo、source-repo-worktree、primary-repo、USERPROFILE 等），JSON 数值/结构未见变化；这与 27c935e 阶段 A5 的递归 diff 结论一致，payload 未在 rev2/rev3 中改变。
- README.md:77 明确列出 5 个 sanitized=true 文件并说明其余 33 条 false；原 M01 已关闭。

## 4. review_chain 互链（M03 关闭，残留 1 minor）

- manifest.json:478-492 的 review_chain.a5_result_review 含 minor_id=A5-S2R-01、minor_status=closed_in_corrected_report、minor_status_ref 指向 reviews/S2_result_review_a5.md 与 docs/reviews/p4_route_a_s2_formal_run_report_20261107.md §7.4。
- 报告 docs/reviews 副本 31,771 B / f97b8eb5…，其 §7.4 含 A5-S2R-01 的 null 口径修正；A5 review 正文也明确引用该修正。原 M03“关闭状态无互链”已关闭。
- 残留 minor：minor_status_ref 内写“A2 corrected report sha 48e0a274…”，但该 sha 是 EXT 外部源报告（31,971 B），包内 docs/reviews 副本是 f97b8eb5（31,771 B，repo-ready）。ref 同时给出包内路径与外部 sha，未说明两者映射；详见第 7 节。

## 5. 报告、图像、0 物理

- 报告 docs/reviews/p4_route_a_s2_formal_run_report_20261107.md：31,771 B，sha256 f97b8eb5edf273145a497305a64e2edaa4f52dbcd79b5d699ac7c190617d3372；独立重算一致，正文无 盘符:/、盘符:/、USERPROFILE/、USERPROFILE/ 绝对路径。
- 9/9 PNG 均可解码：fig1 356,777 B (1243x742)；fig2 126,176 (1603x781)；fig3 127,104 (1261x789)；fig4 61,492 (1063x680)；fig5 77,583 (1280x756)；fig6 65,133 (1361x742)；fig7 132,155 (1843x781)；fig8 129,245 (1841x766)；fig9 155,922 (2023x826)。
- 9 个 support CSV 均可解析，行数 1201/41/33/6/11/9/27/12/44；figure_status.json 为 9 RENDERED / 0 NOT_RUN。
- run_config/run_summary/fd_gate/data_manifest 的 physical_call_count 均为 0；无 solver 启动痕迹；本复核本身也未启动任何求解器或物理计算。
- 全包文本扫描（38 条中非图像文件）无本机绝对路径；报告与 README 均使用相对标记。

## 6. fail-closed 探针（5/5 PASS）

探针脚本：EXT/p4-route-a/a5/S2_package_review_rev3/rev3_tamper_probes.py；结果：rev3_tamper_results.json。

- clean 副本：canonical / dual / presence / no_abs 四项全 true。
- 篡改 SHA256SUMS 中 run_config 行：canonical=false（被识别）。
- 篡改 manifest 的 run_config sha256_lf：canonical=false、dual=false。
- 篡改 manifest 的 compare_r1 sha256_raw：dual=false。
- 删除 fd_gate.json：presence=false（并连带 canonical/dual=false）。
- 向 README 注入 盘符:/secret/path：no_abs=false。
- 结论：5 种篡改均被拒绝；clean 副本全通过，符合 fail-closed。

## 7. Findings（2 minor，均不阻断）

### A5-S2PKG3-01（minor）raw/EOL 的复现说明与仓库 .gitattributes 不一致

- 证据：README.md:51 称 bytes_raw 为“工作树原始字节”；README.md:78 称“7 个 payload 文件在 Windows 工作树为 CRLF”；README.md:89-90 给出工作树 raw 校验命令；PACKAGE_MANIFEST.json:14 的 eol_summary.note 称“Windows core.autocrlf: 工作树 CRLF”。
- 实际：本仓库 .gitattributes:1 为 `* text=auto eol=lf`，`git check-attr eol` 对 7 个文件均返回 `eol: lf`；干净 checkout 中 7 个文件都是 LF（0 个 CRLF，bytes 1,074/385/3,202/1,179/25,476/213/213），与 manifest 的 bytes_lf 一致，而与 bytes_raw（1,077/388/3,217/1,188/25,757/214/214）不一致。raw 值实际对应打包源 EXT 工作树的 CRLF，不是本仓库 checkout 的字节。
- 影响：双哈希数据本身自洽（raw 与源一致、LF 与 git blob 一致，已在第 2 节验证）；但按 README §8 的 raw 命令在干净 checkout 上执行会得到 lf 值，读者会误以为 package 校验失败。canonical-LF 主路径不受影响。
- 建议：把 raw 定义为“打包源 EXT 工作树原始字节”，明确“干净 git checkout 不能直接复现 raw；raw 仅用于对照源工作树”；或删除 raw 命令中的 autocrlf 断言，保留 canonical-LF 作为唯一可复现口径。

### A5-S2PKG3-02（minor）review_chain 引用外部源报告 sha 48e0a274，但包内副本为 f97b8eb5，未说明映射

- 证据：PACKAGE_MANIFEST.json:490 的 minor_status_ref 同时写 `docs/reviews/p4_route_a_s2_formal_run_report_20261107.md (A2 corrected report sha 48e0a274…)`；README.md:56 也把 48e0a274 称为关闭依据；但包内该路径文件为 31,771 B / f97b8eb5，README.md:52 明确称其为 repo-ready 副本。
- 外部源报告存在：EXT/p4-route-a/a2/S2_formal_run_report.md 为 31,971 B / 48e0a274…；repo-ready 副本为 31,771 B / f97b8eb5…。两者是同一报告的不同副本，但 ref 未区分“外部源 sha”与“包内副本 sha”。
- 影响：读者按 ref 的 48e0a274 在包内找不到对应文件，需额外推断；不影响 §7.4 结论、统计结果或回执判决。
- 建议：在 minor_status_ref 中同时写 `source_report_sha=48e0a274… (external)` 与 `packaged_copy_sha=f97b8eb5… (repo-ready)`，或把 README §4/§5 的对应关系补一行。

## 8. 已关闭项

- **A5-S2PKG-01（blocker，EOL 口径）CLOSED**：38/38 canonical-LF sums 可由 `git cat-file blob HEAD:<path>` 复现；双哈希 raw/lf 均在 manifest 中，7 CRLF/31 LF 计数正确；原 27c935e 的 7 条 CRLF 声明失败已消除。
- **A5-S2PKG-02（major，sanitized 标志）CLOSED**：5 true / 33 false，与 README 及实际内容三方一致；顶层 sanitization 块包含清单、规则、numeric_structure_identical=true。
- **A5-S2PKG-03（minor，review_chain 互链）CLOSED**：minor_status_ref 已含报告路径与 §7.4；残留仅为 A5-S2PKG3-02 的 sha 映射说明。
- 27c935e 的 B01 仅影响清单口径，不影响统计结果；rev2/rev3 未改动 36 个 payload 与正式报告，原 S2 结果结论不受影响。

## 9. 最终判决

**APPROVE_FOR_S2_RECEIPT_PACKAGE**（0 blocker / 0 major / 2 minor）。

- 该包可以作为 S2 正式运行证据包回执的输入；canonical-LF 38/38 可复现，EOL 双哈希、sanitized 标志、review_chain 互链均已达到回执要求。
- 两个 minor 均为可复现/说明性文档问题，不影响证据完整性、统计结论或 0 物理事实；建议在后续文档维护中修正，不要求本轮重新打 rev4。
- 本报告不批准新 run、不批准 B/C 类 fallback、不改变 S2 的 DEVELOPMENT_VALIDATION_ONLY 边界，也不替代 owner/Lead 的 Issue 回执决策。

## 10. 复核环境

- Python：primary-repo/envs/RCAIDE/python.exe；仅标准库 + Pillow 用于 PNG 解码。
- worktree：review-worktree @ 12940c5；git status 干净。
- 未执行：任何求解器、物理计算、DOE/BO/DE/MAML 训练、GitHub 写操作、仓库写操作。
