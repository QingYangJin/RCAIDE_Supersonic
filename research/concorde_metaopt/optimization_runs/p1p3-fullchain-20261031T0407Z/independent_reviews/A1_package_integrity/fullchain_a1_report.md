# FULLCHAIN-A1-PACKAGE-INTEGRITY-d80b4c4 — 包完整性复核报告

- 任务：task-25（A1=a1-code-dev），只读复核，不启动任何 solver / 物理计算（D-12D-002 预算 23/23 已耗尽）
- 被审运行包：`D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z`（60 files，约 1.3 MB）
- 复核工作树：`D:/RCAIDE-verify-fullchain-a1`，HEAD `d80b4c485d689082cd117f09ec6445a181dd458c`，`git status --porcelain` 空（detached）
- 主 checkout `D:/RCAIDE` 未触碰；仓库零写入；无 git add/commit/push；无 GitHub 写操作
- 复核时间：2026-10-31T18:01+08:00
- 结论：**PASS_WITH_WARNINGS** — 6 项必需检查全部通过；发现 1 处文档级台账瑕疵（WARN，不影响预算核算）；显式列出 1 项 NOT_RUN

## 1. 命令与退出码

| # | 命令 | 结果 |
|---|---|---|
| 1 | `cd D:/RCAIDE-verify-fullchain-a1 && D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m unittest discover -s research/concorde_metaopt/tests -t .` | **Ran 294 tests / OK (skipped=1) / EXIT=0**（29.885 s；无 FAIL/ERROR）；skip=`RealOpenVSPIntegrationTests.test_real_worker_composes_placement_checked_assembly`（缺 CONCORDE_OPENVSP_PYTHON/ROOT 环境，属预期 skip） |
| 2 | `D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B manifest_check.py <run_dir> --log manifest_check.log` | **CHECK_EXIT=0，RESULT=PASS_WITH_WARNINGS** |

日志与指纹：
- `full_suite.log` sha256 `b769114dd25ffc69a142b4acd03cac62900345d46593231aedaaf52ef66c50a2`（第3行 Ran 294，第5行 OK (skipped=1)，第220行 EXIT=0）
- `full_suite_verbose.log` sha256 `f578a8f344167a4a6c696cbd02ca3f7149ba8add1b9b16781acf59121ee95ff7`（第232行给出 skip 名称，第297/299行 Ran 294 / OK skipped=1）
- `manifest_check.py` / `manifest_check.log` sha256 `91513586b9a718cb4672acd08c749cd240c7f323804ae9e36d105eddb30dbab4`

## 2. 六项必需检查

| 检查 | 结果 | 关键证据 |
|---|---|---|
| (1) 提交版测试套件 | **PASS** | Ran 294 / OK (skipped=1) / EXIT=0，唯一 skip 有明确环境原因 |
| (2) 包内 JSON 全部可解析 | **PASS** | 60 files 中 14 JSON + 1 jsonl 全部 parse OK |
| (3) data_manifest.json 重哈希 | **PASS** | listed=59=file_count；sha256+bytes **mismatches=0**；重算 total_bytes=1181000=清单值；未列文件仅 data_manifest.json 自身（自排除） |
| (4) 计费行与预算台账 | **PASS** | evaluations.jsonl 23 行全为 billable numerical_analysis_start；分类 **VSPAERO_LF 6 / RCAIDE_LF 4 / WAVE_AREA_RULE 7 / SU2_HF 6**，与 ledger used 及 summary.budget 一致；ledger totals cap=23 used=23 remaining=0；ledger.numerical_analysis_events 23 条与 jsonl 逐行 case_id/category/status **1:1 一致（first_diff=None）**，command 前缀全一致 |
| (5) 7 张 PNG 图有效 | **PASS** | 7/7 签名+IHDR 有效、size>1000：drag_component_bookkeeping 68344 B/1275×630、lf_vspaero_density_sensitivity 113900/1650×510、mission_e2e_fuel_deltas 53962/1275×540、su2_wing_force_convergence 85200/1650×510、su2_wing_mesh_sensitivity 50517/1200×480、wave_area_rule_results 209303/2415×807、wave_area_rule_validation 191702/2574×758 |
| (6) 门禁无伪造 | **PASS** | gates 精确匹配：GEO-12D=PARTIAL、LF-M2.02=`NOT_VALIDATED / LF_PROVISIONAL`、HF-M2.02=PARTIAL、BODY-CORR=BLOCKED、MISSION-DATA=PARTIAL、BUDGET=EXHAUSTED；无多余 gate；summary.status=`EXECUTED_NO_GATE_APPROVED`；`APPROVED_FOR_NEXT_STAGE` 仅出现在 not_approved 列表（未授予）；无任何 gate status 含 APPROVED |

补充事实（summary.json）：run_id=`p1p3-fullchain-20261031T0407Z`；base_commit=`048ef2e55f389b0ae52e8872131dcfcf0c91a1eb`；branch `research/concorde-metaopt`；PR #3 open 未合并；started 2026-10-31T04:07:14Z / finished 09:44:53Z；冻结 mach 2.02 / alt 18288 m / Re_cref 89397005.8767656。23 次启动中状态分布：SOLVED 20、FAILED 1（HFS-01，rc=1）、FAILED_CONFIG_PARSE 1（HFS-SETUP-01，rc=None）、SOLVED_VOID_CONVERGENCE 1（HFS-SETUP-02，rc=None）。包内 review a1–a5 记录均 PENDING。

## 3. 唯一 WARN（额外发现，非必需项）

`approval_and_budget_ledger.json` 的 `categories[*].case_ids` 是**过期的计划 ID**，与实跑事件不符：
- VSPAERO_LF 列 `LFV-00, LFV-01, LFV-02, LFV-03, LFV-SENS-A, LFV-SENS-B`；实跑 `LFV-00, w01_plus1pct, w03_plus1deg, w10_plus2, sens_coarse, sens_fine`
- WAVE_AREA_RULE 列 `WAVE-00..WAVE-06`；实跑 `WAVE-00, WAVE-00R, WAVE-01..WAVE-05`
- SU2_HF 列 `HFS-00, HFS-00R, HFS-01..HFS-04`；实跑 `HFS-SETUP-01, HFS-SETUP-02, HFS-00, HFS-01, HFS-02, HFS-03`

影响评估：`used` 计数（6/4/7/6）与 totals（23/23/0）**正确**，事件级 `numerical_analysis_events` 与 evaluations.jsonl **完全一致**，README 第56行也采用实跑 ID；故仅属台账文档陈旧，**不影响预算核算与验收结论**。建议后续（下阶段，非本轮）用实跑 case_id 回填 categories[*].case_ids。

## 4. NOT_RUN / 未覆盖项（如实声明）

- 原始产物目录 `D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/` 未逐文件复核：raw_artifacts_manifest.json 声明 raw_file_count=195 / raw_total_bytes=108824422；本轮仅校验包内 59 个 manifest 文件。**NOT_RUN**（非本任务必需项，且属 ignored 大目录）。
- 包内 5 份 review 记录（a1–a5）状态 PENDING，本轮不代替评审意见。**NOT_RUN**
- 未运行任何物理求解/优化（预算耗尽 + 任务禁止）。所有结论均来自静态解析与重哈希。

## 5. 产物

- `C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/a1/fullchain_a1_report.md`（本报告）
- `.../fullchain/a1/full_suite.log`、`full_suite_verbose.log`
- `.../fullchain/a1/manifest_check.py`、`manifest_check.log`

**最终判定：包完整性 PASS_WITH_WARNINGS —— 可接受，无门禁伪造，无预算超支，无损坏文件；唯一瑕疵为 ledger categories case_ids 陈旧（文档级）。**
