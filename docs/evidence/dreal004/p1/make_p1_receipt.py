
"""生成 Issue #14 P1 阶段中文回执草案，并把 P1 证据复制到 docs/evidence/dreal004/p1/。"""
from __future__ import annotations
import hashlib, json, shutil
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P1-20261122-02")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
OUTDIR = REPO / "docs/evidence/dreal004/p1"
RUN_REL = "research/concorde_metaopt/optimization_runs/DRECOVER001-P1-20261122-02"
HEAD = "8c1acc13d2c041c6ee966ce008ebb2b5572cf52b"
BRANCH = "research/dreal004-alpha-adaptive-meta-sampling"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


acc = json.loads((RUN / "p1_accounting.json").read_text(encoding="utf-8"))
met = json.loads((RUN / "p1_metrics.json").read_text(encoding="utf-8"))
res = json.loads((RUN / "p1_result.json").read_text(encoding="utf-8"))
ver = json.loads((RUN / "a5_review" / "verdict.json").read_text(encoding="utf-8"))
rver = json.loads((RUN / "a5_result_review" / "verdict.json").read_text(encoding="utf-8"))
audit = json.loads((RUN / "remote_retrieval" / "p1_remote_retrieval_audit.json").read_text(encoding="utf-8"))
up = json.loads((RUN / "upload_receipt.json").read_text(encoding="utf-8"))

OUTDIR.mkdir(parents=True, exist_ok=True)
copied = []
for src, dst in [
    (RUN / "p1_preregistration.json", "p1_preregistration.json"),
    (RUN / "p1_accounting.json", "p1_accounting.json"),
    (RUN / "p1_metrics.json", "p1_metrics.json"),
    (RUN / "p1_result.json", "p1_result.json"),
    (RUN / "p1_go_record.json", "p1_go_record.json"),
    (RUN / "p1_admitted_labels.csv", "p1_admitted_labels.csv"),
    (RUN / "a5_review" / "verdict.json", "a5_protocol_verdict.json"),
    (RUN / "a5_result_review" / "verdict.json", "a5_result_verdict.json"),
    (RUN / "p1_a5_dossier.md", "p1_a5_protocol_dossier.md"),
    (RUN / "p1_a5_result_dossier.md", "p1_a5_result_dossier.md"),
    (RUN / "remote_retrieval" / "p1_remote_retrieval_audit.json", "p1_remote_retrieval_audit.json"),
    (RUN / "upload_receipt.json", "p1_upload_receipt.json"),
]:
    if src.exists():
        shutil.copyfile(src, OUTDIR / dst)
        copied.append((dst, sha(OUTDIR / dst)))

labels = res["admitted_labels"]
L = []
A = L.append
A("# Issue #14 P1 阶段回执草案（D-REAL-EXP-002 自适应迎角小批真实试验）")
A("")
A("状态：DRAFT / NOT POSTED（由 make_p1_receipt.py 生成）；这不是 P2/P3/MAML 授权，也不构成 R1 全面 PASS。")
A("")
A("## 一、结论摘要")
A("")
A("- P1 已完成：真实 VSPAERO 启动 " + str(met["physical_solver_starts_actual"]) + " 次（上限 12），全部 SOLVED，0 失败，0 重试，并行 1；内部 alpha 求解 case " + str(met["internal_solver_cases_actual"]) + " 个（上限 36）。")
A("- 产出 " + str(met["admitted_labels"]) + " 条唯一真实准入标签（" + str(met["admitted_rows"]) + " 行准入，按证书去重），容差 1e-3 未放宽，全部来自可远端回读的原始 .polar 行。")
A("- 自适应局部 bracket 把内部 solver case 从固定 49 点/设计扫描的 196 降到 " + str(met["internal_solver_cases_actual"]) + "（省 " + str(met["internal_saved_vs_fixed_sweep"]) + " 个，约 " + ("%.1f" % (100.0 * met["internal_saved_vs_fixed_sweep"] / 196)) + "%），单设计内部中位数 " + str(met["per_design_internal_median"]) + " 个。")
A("- 行级有效率 " + str(met["admitted_labels"]) + "/" + str(met["physical_solver_starts_completed"]) + " = " + ("%.2f%%" % (100 * met["valid_label_rate_over_completed_rows"])) + "，但样本 n=" + str(met["physical_solver_starts_completed"]) + "，判定 " + met["sample_size_verdict"] + "；不宣称 70% 目标稳健达成。")
A("- 本轮不产生任何 MAML 收益结论：P1 是 " + met["evaluation_mode"] + "，只有 " + str(met["admitted_labels"]) + " 条标签、单一 Mach，不足以训练或评测元学习。")
A("")
A("## 二、授权与预算")
A("")
A("- Owner 指令：" + acc["owner_instruction_ref"] + "；authorization_id " + acc["authorization_id"] + "；batch_id " + acc["batch_id"] + "；run_id " + acc["run_id"] + "。")
A("- 上限：12 design starts、每设计 3、每 start 3 个 alpha 读取点、36 internal、tol 1e-3、0 retry、parallel 1；实际使用：starts " + str(met["physical_solver_starts_actual"]) + "/12（剩余 " + str(12 - met["physical_solver_starts_actual"]) + "）、internal " + str(met["internal_solver_cases_actual"]) + "/36。")
A("- 停止：d00 在 3 次启动后触发 MAX_PER_DESIGN；每个设计都要把预测点附近窗口收敛到 <= 1e-3 才准入，否则 NULL。")
A("- 目标：DREAL004-M202（Mach 2.02，几何冻结 GBFREEZE2）；4 个设计 d00/d01/d04/d07。")
A("")
A("## 三、真实准入标签（同升力条件）")
A("")
A("| 设计 | case | D_i_N (N) | CL | alpha (deg) | rel err | 备注 |")
A("|---|---|---|---|---|---|---|")
notes = {"d00": "两次启动，按证书去重", "d01": "面积 +1%（Sref 361.8325）", "d04": "后掠 +1 度", "d07": "与 d00 coarse polar 字节相同"}
for lab in labels:
    A("| " + lab["design"] + " | " + lab["case_id"] + " | " + ("%.3f" % lab["di_n"]) + " | " + ("%.9f" % lab["cl"]) + " | " + ("%.6f" % lab["alpha_deg"]) + " | " + ("%.2e" % lab["rel_error"]) + " | " + notes.get(lab["design"], "") + " |")
A("")
A("说明：q = " + "20483.94023" + " Pa，Sref 358.25 m2（d01 为 361.8325 m2）；D_i_N = q*Sref*CDi 只含机翼诱导阻力，不是整机阻力，也不含配平/粘性/波阻，更不是油耗。")
A("")
A("## 四、内部成本与自适应方法")
A("")
A("- 方法：用 G2 stage1 M202 的粗极曲线（零新物理）给出 alpha 初始 bracket 与预测点，每次真实启动只在预测点附近解 3 个 alpha；残差 >1e-3 时按斜率再细化一轮（最多 3 轮/设计），仍未收敛则 NULL。")
A("- 每设计内部 case：" + json.dumps(met["per_design_internal_solver_cases"], ensure_ascii=False) + "；总墙钟 " + str(met["total_wall_clock_s"]) + " 秒（不含排队与上传）。")
A("- 对照：固定 49 点极曲线扫描需 4 设计 x 49 = 196 个内部 case；P1 用 " + str(met["internal_solver_cases_actual"]) + " 个（每个唯一标签 " + str(met["internal_solver_cases_per_label"]) + " 个内部 case）。这是成本结论，不是精度结论。")
A("")
A("## 五、A5 独立审查")
A("")
A("- 协议复审：" + str(ver.get("verdict")) + "（子智能体 deepseek-flash 单发只读，非人类签署）。")
A("- 结果复审：" + str(rver.get("verdict")) + "；gates: " + json.dumps(rver.get("gate_verdicts", {}), ensure_ascii=False))
A("- A5 结果复审给出的 minor 项：重复启动根因未彻底解释；CL 侧比对是自洽校验（独立信息来自 alpha→CDi→D_i_N 复算）；6 次 start 跨多版 driver/GO 增加溯源复杂度。这些项已在第七节如实披露，未用 A5 结论关闭。")
A("- A5 结论不等于人类签署，也不等于 R1 全部代码 PASS；A5 指出的限制见其 limitations 字段与下文披露。")
A("")
A("## 六、远端证据与回读")
A("")
A("- 分支 " + BRANCH + "，P1 目录 " + RUN_REL + "，commit " + HEAD + "。")
A("- 上传 " + str(up.get("file_count")) + " 文件 / " + str(up.get("total_bytes")) + " 字节；回读 checked " + str(up["readback"]["checked"]) + "，missing " + str(up["readback"]["missing"]) + "，bad " + str(up["readback"]["bad"]) + "。")
A("- A4 远端复核（GitHub blob API 按原始字节读回后逐字节核对 + 独立复算）：manifest 文件 " + str(audit["manifest_files_checked"]) + "/" + str(audit["manifest_file_count"]) + " 通过，bad " + str(audit["manifest_bad"]) + "，not_ok " + str(audit["manifest_not_ok"]) + "；成功 case 复算 " + str(audit["success_cases_ok"]) + "/" + str(len(audit["success_case_recompute"])) + "；失败样本 " + str(audit["failure_case"]["path"]).split("/")[-1] + " 预期不存在（404=" + str(audit["failure_case"]["no_polar_as_expected"]) + "）；A4 判据 = " + str(audit["a4_criteria_met"]) + "。")
A("- 复算恒等式：D_i_N = q*Sref*CDi（CDi/CL 取远端 .polar 原始行中与报告 alpha 匹配的那一行），rel_di <= 1e-6；CL 相对误差均 <= 1e-3。")
A("- 目录：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/" + HEAD + "/" + RUN_REL)
A("- 图表（仓库内）：" + RUN_REL + "/figures/ 下 cl_alpha_adaptive_vs_fixed.png、p1_outcome_overview.png、di_n_by_design.png、internal_cost_by_design.png，配 figure_data.csv。")
A("")
A("## 七、偏差、缺陷与披露")
A("")
A("- 重复启动：p1-m202-d00-r1 被两个进程重叠启动两次，两次均计费（计入 6 次 starts），标签按证书去重，只算 1 条唯一标签；随后把 run lock 和每设计上限作为硬检查加入执行器。")
A("- 首批准入失败：第一批 3 个 start 已 SOLVED，但准入步骤因时间戳格式错误失败（ADMIT_FAILED）；修复后离线重新审计并准入，未增加物理启动。")
A("- 协议迭代：执行器在批次内修改过 4 次，每次重新预注册、重新 A5 复审并重签 Lead GO；6 次 start 分布在多版 GO 下，最终 GO 绑定最终代码，历史 GO 记录保留在 RUN 目录。")
A("- d07 与 d00 的 coarse polar 字节相同：因此 d07 标签数值与 d00 相同，不能当作独立设计的独立证据。")
A("- 没有失败求解样本：P1 的 6 次启动全部 SOLVED，A4 失败样本借用 G1 的 NO_RESULT case（无 .polar，404），不冒充 P1 数据。")
A("- 边界：同机保存、未异机认证；未做风洞/物理验证；fuel_burn_kg=null；LF-M2.02=NOT_VALIDATED；标签是本地 raw 字节 + 审计绑定的标签，不是独立可信执行环境认证的标签。")
A("- 缩水声明：P1 只证明自适应局部 bracket 能在 1e-3 容差下产出真实标签并显著降低内部成本，不证明精度提升、不证明泛化、不证明 MAML 有效。")
A("")
A("## 八、下一门禁（未授权）")
A("")
A("- P2/P3/MAML 均需新的预注册 + A5 独立审查 + 新的 Lead GO；本回执不授权任何新物理。")
A("- P2 草案（Issue #14 预注册已写）：扩展到多 Mach 任务族（>= 8 任务，<= 240 starts），在真实标签上做 K=1/3/5 FOMAML 与普通预训练对照；理由：现有 5 条标签不足以支撑任何元学习结论。")
A("")
A("## 九、关键文件（本仓库）")
A("")
for name, h in copied:
    A("- docs/evidence/dreal004/p1/" + name + "：sha256 " + h)
A("- 原始数据与表格：" + RUN_REL + "/（raw_cases/、p1_admitted_labels.csv、p1_accounting.json、p1_metrics.json、p1_result.json、figures/、SHA256SUMS.txt）")
A("")
receipt = "\n".join(L) + "\n"
(OUTDIR / "p1_receipt_draft_20261122.md").write_text(receipt, encoding="utf-8", newline="\n")
print("receipt chars", len(receipt))
print("receipt sha256", sha(OUTDIR / "p1_receipt_draft_20261122.md"))
for name, h in copied:
    print(name, h)
