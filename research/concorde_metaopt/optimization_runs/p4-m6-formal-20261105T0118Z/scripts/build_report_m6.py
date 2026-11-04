
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build A2 M6 Chinese report draft, README and SHA256SUMS (zero-solver)."""
import hashlib, json, os

OUT = r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/p4-m5m6/a2/m6_figures_report"
RUN = r"D:/RCAIDE-p4-meta-learning/research/concorde_metaopt/optimization_runs/p4-m6-formal-20261105T0118Z"

def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b: break
            h.update(b)
    return h.hexdigest()

summary = jload(RUN + "/summary.json")
recompute = jload(OUT + "/recompute.json")
figman = jload(OUT + "/figures_manifest.json")
tlc = summary["three_layer_conclusions"]["layers"]

def fmt(x, nd=10):
    return ("%%.%dg" % nd) % float(x)

head = recompute["headline_rows_k5"]
labeled = []
for r in head:
    fam = r["source_family"]
    study = r["study"]
    name = {"in_dist": "同分布 meta_test", "ood": "OOD 参数外推"}.get(study)
    if name is None:
        name = "新函数族 " + fam
    labeled.append((name, fam, r))

L = []
A = L.append
A("# P4-M6 快速适应正式 run 报告（A2 独立出图与复算）")
A("")
A("> 状态：**APPROVE_FOR_M6_REPORTING**（A5 task-160 verdict：0 blocker / 0 major / 5 minor；本文件已按 A5-M6-02/03/05 修订，为报告定稿候选）。")
A("> 数据来源：SYNTHETIC_ONLY（全部标签为解析合成任务族真值）；physical_call_count = 0；未调用任何真实求解器，无网络。")
A("> run：p4-m6-formal-20261105T0118Z；创建于 2026-11-04T17:23:16Z；summary.status = VALID；runtime_s = 73.1186564998934。")
A("> 结论约束：不得宣称 MAML 优越或与基线等价；K-shot 代理误差不得外推为 BO 样本效率；OOD 因难度混杂不得作为泛化结论。")
A("")
A("## 1. 目的与范围")
A("")
A("本报告对应 D-P4-002（M6）：在冻结的合成任务族上比较三种快速适应 harness —— M（MAML 一阶元学习）、P（监督预训练后微调）、R（随机初始化）——的同预算代理误差。三层结论严格分离，且禁止跨层推断：")
A("")
A("1. **代理快速适应误差**（surrogate error advantage）：M6 可评估；")
A("2. **BO 样本效率**（bo sample efficiency）：**NOT_EVALUATED_IN_M6**，必须引用 M5 holdout 统计（当前 m5_reference = PENDING_M5_ACCEPTANCE；M5 已执行但成果仍在修复/复核中）；")
A("3. **OOD 泛化**：仅当 H1–H5 诊断全部通过且难度匹配时才能条件性表述；本次诊断为 CONFOUNDED，不得表述。")
A("")
A("**不适用范围（non-claims）**：真实跨任务元训练与真实低/高保真标签（需 P4-REAL-LF / P4-MULTIFIDELITY-REAL 授权）；MAML 参数级等价性（backend 为自写一阶实现，equivalence_claimed=false）；由代理误差直接推断 BO 样本效率；真实飞机油耗 / Mach 2.02 物理改进；VSPAERO 结果（NOT_RUN，归 Issue #4 D-12D-004）。")
A("")
A("## 2. 设计")
A("")
A("- 三臂：**M** = MAML 一阶元训练；**P** = 监督预训练后微调；**R** = 随机初始化；同结构、同评估预算、同 support/query。")
A("- K 网格：K ∈ {0, 1, 5, 10, 20}；support 池 128，query 64，微调步数 50，元训练步数 200。")
A("- 评估研究：同分布 meta_test（20 任务）、OOD meta_test_ood（10 任务）、新函数族 F-LIN / F-MF（各 20 任务）、负控制（10 任务，单列不进入主终点）。")
A("- 元训练 seeds = [0, 1, 2]；确定性重跑 3 次；每 meta seed × 任务 × 臂 × K 各一条 adaptation 记录 → 3600 行；总 adaptation executions = 10,800（3 次确定性重跑）。")
A("- 冻结门禁：family = F-QE-feasible-v2（v2，fingerprint 2b78ec7b…），split_hash = 3c206ebb…，preregistration sha256 = c5abd30e…；门禁 status = PASS；scale preflight = PASS（80 units / 3600 rows / 10,800 executions / physical 0）。")
A("- meta_test 调参策略：禁止使用 meta_test / meta_test_ood 的任何信息调参、选半径、选臂或选终点；frozen gate + preregistration 校验通过后一次性评估。")
A("- evaluator：synthetic__analytic__12d_lifting_surfaces__v1（解析合成，12D 工程，仅机翼升力面）；stage = P4-CODE；study_scale = FORMAL；conclusions_allowed = true。")
A("")
A("## 3. 执行事实")
A("")
A("| 项目 | 值 | 来源 |")
A("| --- | --- | --- |")
A("| run_id | p4-m6-formal-20261105T0118Z | summary.json |")
A("| status / study_scale | VALID / FORMAL | summary.json |")
A("| 运行时长 | 73.1186564998934 s | summary.json:runtime_s |")
A("| adaptation 行 / statistics 行 / training 行 | 3600 / 300 / 750 | summary.json:counts |")
A("| 总 adaptation executions | 10,800 | summary.json:counts |")
A("| 非有限行 | 0 | summary.json:counts |")
A("| physical_call_count | 0 | summary.json / run_config.json |")
A("| 确定性重跑 | 3 次全部一致 | summary.json:determinism（PASS） |")
A("| 旧 M2 run 不变性 | PASS（26 文件，manifest sha acaab106…，0 mismatch） | summary.json:old_run_gate |")
A("| 冻结门禁 / split 校验 | PASS（120 任务逐项 PASS） | summary.json:frozen_gate / frozen_split_verification |")
A("| git_sha | c300d9532f3c354c71242adb720b3e5c1a958c40（git_sha_label 带 -dirty；worktree_dirty = true） | run_config.json |")
A("| A2 独立复算 | %d/%d 项 PASS（headline 12 行 + statistics K=5 60 行 + data_manifest 22 文件 + fig2 300 行） | recompute.json |" % (recompute["n_pass"], recompute["n_checks"]))
A("| A5 结果复核 | **APPROVE_FOR_M6_REPORTING**（task-160：0 blocker / 0 major / 5 minor；A5-M6-02/03/05 已按 findings 修订） | a5/m6_results_review/verdict.txt |")
A("")
A("执行期未启动任何 solver：vspaero / SU2 / RCAIDE Mission 均未调用；无网络；本报告的全部图表与复算均为只读离线处理。")
A("")
A("## 4. 结果（主终点：meta_test K=5 query RMSE）")
A("")
A("### 4.1 headline K=5（rmse_norm，group_mean，发布值；A2 已从 adaptation_results.csv 复算 n/mean/median 全部一致）")
A("")
A("| 研究 | 族 | 臂 | n_runs | mean rmse_norm | median | 95% CI（发布） |")
A("| --- | --- | --- | --- | --- | --- | --- |")
for name, fam, r in labeled:
    A("| %s | %s | %s | %d | %s | %s | [%s, %s] |" % (name, fam, r["arm"], r["n_recomputed"], fmt(r["mean_recomputed"], 10), fmt(r["median_recomputed"], 10), fmt(r["ci_published"][0], 8), fmt(r["ci_published"][1], 8)))
A("")
A("### 4.2 三层结论（summary.three_layer_conclusions，禁止跨层推断）")
A("")
A("- **L1 代理快速适应误差**：%s。K=5 in_dist（原训练族）M vs P median_diff = 0.01803237774931271（MAML 误差更高方向），CI [0.000908288798144752, 0.028150164167499568]，p_holm = 0.012662887573242188；M vs R median_diff = -0.01166786654265974，CI [-0.041442803976626495, 0.011940230307713389]，p_holm = 0.17685317993164062。新函数族：F-LIN M−R p_holm = 0.4610252380371094、P−R p_holm = 0.42871856689453125；F-MF M−R p_holm = 0.7011814117431641、P−R p_holm = 0.4610252380371094；均 reject_holm = false。**没有任何一项支持 MAML 相对预训练/随机基线的显著优势。** 补充（A5-M6-02）：in_dist K=5 的 M−P median_diff = +0.01803237774931271、p_holm = 0.012662887573242188（reject_holm = true），即 MAML 误差在该比较上**显著更高（更差方向）**；M−R p_holm = 0.17685317993164062 不显著。该方向不可解读为等价或更优；run README 第 48 行需由 Lead 打包时同步一句（A5-M6-02）。" % tlc["surrogate_error_advantage"]["status"])
A("- **L2 BO 样本效率**：%s；m5_reference = PENDING_M5_ACCEPTANCE（M5 holdout 已执行，但成果仍在修复/复核中，A5 task-153 曾判 CHANGES_REQUESTED）；M6 的 K-shot 代理误差不得用于推断 BO 样本效率（A5-M6-05）。" % tlc["bo_sample_efficiency"]["status"])
A("- **L3 OOD 泛化**：%s；diagnostics = %s，conclusion_allowed = false，difficulty_matching = %s，negative_control = %s；attribution 规则：只有 H1 通过且难度匹配为 MATCHED 才允许 OOD 方向表述。" % (tlc["ood_generalization"]["status"], tlc["ood_generalization"]["diagnostics_status"], tlc["ood_generalization"]["difficulty_matching_status"], tlc["ood_generalization"]["negative_control_status"]))
A("- 跨层约束：cross_layer_inference_forbidden = true；禁止由 L1 的 K=5 RMSE 差异推断 BO 样本效率或 OOD 泛化。")
A("")
A("### 4.3 K 扫描与图 2 / 图 7")
A("")
A("- 图 2（figures/fig2_K_shot_rmse.png）：K=0/1/5/10/20 × 4 个研究面（同分布、OOD、F-LIN、F-MF）× 3 臂的 rmse_norm 中位数与 95% CI。K=0 时 R 显著更差；K≥1 后三臂迅速接近，K=5 与 K=10/20 差异很小。")
A("- 图 7（figures/fig7_k_sweep_delta.png）：K 扫描下的 M−R 与 P−R 均值差。K=0 时 M/P 相对 R 的显著负差主要反映初始化差异（不代表快速适应优势）；K=5 主比较中 MAML 相对预训练无显著优势；K=10/20 两端所有配对差接近 0。")
A("")
A("## 5. 负控制与 OOD 混杂诊断")
A("")
A("- OOD 诊断状态 = CONFOUNDED，conclusion_allowed = false；H1 = **CONFOUND_SUSPECTED**，H2–H5 = PASS。")
A("- 难度匹配 = **POOR_MATCH**（tolerance = 1.0）：imbalance 中 |radius| = 2.113340974815672 超出容差（OOD 半径 mean 0.5509698037029749 vs in-dist 0.7467844298029109，相对差 26.2%）；其余 query_objective_std 0.1649、mean_curvature -0.2119、context_shift_norm 1.1346。")
A("- 因此 OOD 方向只能报告“无显著优势（NO_SIGNIFICANT_ADVANTAGE）”，不得解释为泛化失败或泛化成功；图 6 左/中面板展示该诊断。")
A("- 负控制 status = PASS：NC1 label-shuffle 后 MAML 优势回落（in-dist 优势 0.01166786654265974 → 负控制优势 -0.01733762524571018，shrink_fraction 2.4859293412656736，paired_tasks 10）；NC2 K=0 随机臂最差（rmse_norm M 1.6301459884133385 / P 1.4515609019354394 / R 3.1070488983088262）。")
A("- 图 6（figures/fig6_ood_negative_control.png）：左 = OOD 难度相对差异（±20% 容差带），中 = K=5 配对差森林图（12 个比较，含负控制单列），右 = NC1/NC2 数值与 R 基准。")
A("")
A("## 6. 限制与不确定度")
A("")
A("1. 全部数据为合成解析任务族（SYNTHETIC_ONLY）；不得外推到真实飞机、油耗、VSPAERO/SU2 物理结论。")
A("2. M6 只评估代理快速适应误差；BO 样本效率必须等 M5 holdout 验收（当前 PENDING_M5_ACCEPTANCE：M5 已执行但成果仍在修复/复核中；A5-M6-05）。")
A("3. OOD 诊断 CONFOUNDED 且 difficulty_matching POOR_MATCH，OOD 方向不可归因，不得作为泛化结论。")
A("4. 元训练只使用 meta_train（未做 validation 早停），该点已由 run 自身 notes 披露。")
A("5. MAML backend 为自写一阶实现，参数级等价性 equivalence_claimed=false。")
A("6. 运行记录 git_sha = c300d953…-dirty（worktree_dirty=true）；如验收要求干净工作树，需在独立 worktree 复跑（另需授权，本次未做）。")
A("7. 本报告按 A5 task-160 verdict = APPROVE_FOR_M6_REPORTING（0 blocker / 0 major / 5 minor）修订；剩余 minor 中 A5-M6-01（prereg stopping_rules 序列化，pre-existing）与 A5-M6-04（run_config 缺 determinism_reruns 字段）不改动本报告数字，留待 Lead 打包与后续整理。")
A("8. CI 可复现性（A5-M6-03）：seed 未显式写入 run 产物（由代码确定性派生：m6_study.py:800-802 的 stable_int 与 :884-885 的 seed 派生）；A2 未重推 CI（只复算 n/mean/median 与统计量）；A5 已按 stable_int 确定性 seed 精确重放 300/300 行 CI/p/Holm 至 1e-12。")
A("")
A("## 7. 溯源与复现")
A("")
A("- run 目录：D:/RCAIDE-p4-meta-learning/research/concorde_metaopt/optimization_runs/p4-m6-formal-20261105T0118Z/")
A("- summary.json / run_config.json / preflight/formal_scale_preflight.json / gate/{frozen_gate,frozen_family,meta_task_split,preregistration}.json / data_manifest.json（22 文件、CRLF->LF 哈希约定）")
A("- run_config.json：git_sha = c300d9532f3c354c71242adb720b3e5c1a958c40；meta_seeds = [0,1,2]；study_scale = FORMAL；stage = P4-CODE；physical_guard_expected = 0。")
A("- 复现命令（run README 记录，需在授权环境中执行）：D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m research.concorde_metaopt.meta_learning.m6_study --run-id p4-m6-formal-20261105T0118Z --output-root <OUT> --frozen-run-dir research/concorde_metaopt/optimization_runs/p4-meta-m5-formal-20261104T1018Z --old-run-output-root research/concorde_metaopt/optimization_runs --ks 0,1,5,10,20 --meta-seeds 0,1,2 --determinism-reruns 3")
A("- 本目录离线复算命令：D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/recompute_m6.py；出图：scripts/gen_figures_m6.py（只读 run 目录，MPLCONFIGDIR 指向本目录缓存）。")
A("")
A("## 8. 产物清单")
A("")
for r in figman["figures"]:
    A("- figures/%s：%d B，sha256 = %s，layout = %s" % (r["file"], r["bytes"], r["sha256"], r["layout_check"]["status"]))
A("- figures_manifest.json：%d 图，all_layout_checks_pass = %s，DPI = %d，字体 = %s（%d 字符覆盖检查通过）" % (figman["n_figures"], str(figman["all_layout_checks_pass"]).lower(), figman["dpi"], figman["font"]["family"], figman["font"]["chars_checked"]))
A("- recompute.json / recompute.md：%d 项检查，%d PASS / %d FAIL，verdict = %s" % (recompute["n_checks"], recompute["n_pass"], recompute["n_fail"], recompute["verdict"]))
A("- README.md、SHA256SUMS.txt、scripts/{recompute_m6.py, gen_figures_m6.py, probe*.py}")
A("")
A("## 9. A5 复核状态与下一步")
A("")
A("- A5 已批准的先行 verdict：m6_pre_run_review = APPROVE_FOR_FORMAL_M6（target 8bf27257…，A5M6R-01..04 CLOSED）；m6_integration_delta = APPROVE_TO_START_FORMAL_M6（target c300d953…，minor 1）。")
A("- **A5 结果复核（task-160）verdict = APPROVE_FOR_M6_REPORTING**（0 blocker / 0 major / 5 minor；A5 独立复算 12 条 headline 与 300 条 statistics 行至 1e-12，无需重跑）。本报告状态 = APPROVE_FOR_M6_REPORTING（已按 A5-M6-02/03/05 修订）。")
A("- 由 Lead 决定是否合并到 docs/reviews/ 并提交；A2 不 commit / 不 push / 不写 GitHub。A5-M6-01/04 属冻结件序列化与 run_config 字段问题，由 Lead 打包时处理。")
A("")
A("---")
A("生成者：A2（a2-run-opt）；生成方式：只读 run 目录 + 本目录脚本离线复算与出图；0 solver、0 仓库写、0 GitHub 写。")

report = "\n".join(L) + "\n"
report_path = os.path.join(OUT, "p4_m6_formal_report_20261105.md")
with open(report_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(report)

R = []
R.append("# A2 M6 图表与报告草稿目录")
R.append("")
R.append("本目录为 A2 基于 P4-M6 正式 run 的独立图表、复算与中文报告草稿（零求解、只读 run 目录、未写仓库）。")
R.append("")
R.append("- run：p4-m6-formal-20261105T0118Z（VALID，runtime 73.1186564998934 s，physical_call_count = 0）")
R.append("- run 目录：D:/RCAIDE-p4-meta-learning/research/concorde_metaopt/optimization_runs/p4-m6-formal-20261105T0118Z/")
R.append("- 报告草稿：p4_m6_formal_report_20261105.md（状态 DRAFT / PENDING_A5_REVIEW）")
R.append("- 图：figures/fig2_K_shot_rmse.png、figures/fig6_ood_negative_control.png、figures/fig7_k_sweep_delta.png（300 dpi，微软雅黑，布局自检全 PASS）")
R.append("- 复算：recompute.json / recompute.md（%d 项检查，%d PASS / %d FAIL，verdict = %s）" % (recompute["n_checks"], recompute["n_pass"], recompute["n_fail"], recompute["verdict"]))
R.append("- 图的哈希/字体/布局：figures_manifest.json；文件清单哈希：SHA256SUMS.txt")
R.append("")
R.append("## 复现")
R.append("")
R.append("    cd C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/p4-m5m6/a2/m6_figures_report")
R.append("    D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/recompute_m6.py")
R.append("    MPLCONFIGDIR=./.mplcache D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/gen_figures_m6.py")
R.append("")
R.append("## 边界")
R.append("")
R.append("- SYNTHETIC_ONLY：合成解析任务，无真实物理数据；不得宣称 MAML 优越/等价，不得把 K-shot 误差外推为 BO 样本效率或 OOD 泛化。")
R.append("- A5 结果复核（task-160）未落盘前，报告保持 DRAFT；若 CHANGES_REQUESTED 则标 DRAFT_BLOCKED。")
with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(R) + "\n")

records = []
for root, dirs, files in os.walk(OUT):
    dirs[:] = [d for d in dirs if d not in (".mplcache", "__pycache__")]
    for fn in sorted(files):
        p = os.path.join(root, fn)
        rel = os.path.relpath(p, OUT).replace("\\", "/")
        if rel == "SHA256SUMS.txt":
            continue
        records.append((sha256_file(p), rel))
sums = "\n".join("%s  %s" % (h, r) for h, r in sorted(records, key=lambda x: x[1])) + "\n"
with open(os.path.join(OUT, "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\n") as f:
    f.write(sums)

print(json.dumps({"report_lines": len(L), "report_bytes": os.path.getsize(report_path),
                  "report_sha256": sha256_file(report_path), "readme_sha256": sha256_file(os.path.join(OUT, "README.md")),
                  "sums_entries": len(records), "sums_sha256": sha256_file(os.path.join(OUT, "SHA256SUMS.txt"))}, ensure_ascii=False))
