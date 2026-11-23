"""生成 Issue #14 P2 阶段中文回执草案，并把 P2 证据复制到 docs/evidence/dreal004/p2/。"""
from __future__ import annotations
import hashlib, json, shutil
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
OUTDIR = REPO / "docs/evidence/dreal004/p2"
BRANCH = "research/dreal004-alpha-adaptive-meta-sampling"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


acc = json.loads((RUN / "p2_supplement_accounting.json").read_text(encoding="utf-8"))
ds = json.loads((RUN / "p2_dataset" / "p2_dataset.json").read_text(encoding="utf-8"))
diff = json.loads((RUN / "p2_dataset" / "p2_dataset_diff.json").read_text(encoding="utf-8"))
res = json.loads((RUN / "training" / "p2_training_result.json").read_text(encoding="utf-8"))
summ = json.loads((RUN / "training" / "p2_arm_summary.json").read_text(encoding="utf-8"))
norm = json.loads((RUN / "training" / "p2_normalizer.json").read_text(encoding="utf-8"))
proto = json.loads((RUN / "a5_review" / "verdict.json").read_text(encoding="utf-8"))
rver = json.loads((RUN / "a5_result_review" / "verdict.json").read_text(encoding="utf-8"))
audit = json.loads((RUN / "remote_retrieval" / "p2_remote_retrieval_audit.json").read_text(encoding="utf-8"))
up = json.loads((RUN / "upload_receipt.json").read_text(encoding="utf-8"))

OUTDIR.mkdir(parents=True, exist_ok=True)
PAIRS = [
    (RUN / "p2_preregistration.json", "p2_preregistration.json"),
    (RUN / "p2_go_record.json", "p2_go_record.json"),
    (RUN / "p2_supplement_plan.json", "p2_supplement_plan.json"),
    (RUN / "p2_supplement_accounting.json", "p2_supplement_accounting.json"),
    (RUN / "p2_dataset" / "p2_dataset.json", "p2_dataset.json"),
    (RUN / "p2_dataset" / "p2_dataset_diff.json", "p2_dataset_diff.json"),
    (RUN / "training" / "p2_training_result.json", "p2_training_result.json"),
    (RUN / "training" / "p2_arm_summary.json", "p2_arm_summary.json"),
    (RUN / "training" / "p2_normalizer.json", "p2_normalizer.json"),
    (RUN / "tables" / "p2_arm_metrics.csv", "p2_arm_metrics.csv"),
    (RUN / "tables" / "p2_predictions.csv", "p2_predictions.csv"),
    (RUN / "tables" / "p2_training_curves.csv", "p2_training_curves.csv"),
    (RUN / "p2_inventory.json", "p2_inventory.json"),
    (RUN / "a5_review" / "verdict.json", "a5_protocol_verdict.json"),
    (RUN / "a5_result_review" / "verdict.json", "a5_result_verdict.json"),
    (RUN / "p2_a5_dossier.md", "p2_a5_protocol_dossier.md"),
    (RUN / "p2_a5_result_dossier.md", "p2_a5_result_dossier.md"),
    (RUN / "remote_retrieval" / "p2_remote_retrieval_audit.json", "p2_remote_retrieval_audit.json"),
    (RUN / "upload_receipt.json", "p2_upload_receipt.json"),
]
copied = []
for src, dst in PAIRS:
    if src.exists():
        shutil.copyfile(src, OUTDIR / dst)
        copied.append((dst, sha(OUTDIR / dst)))

L = []
A = L.append
A("# Issue #14 P2 阶段回执草案（真实 VSPAERO 标签扩充 + 四臂 MAML 公平对照）")
A("")
A("状态：DRAFT / NOT POSTED（由 make_p2_receipt.py 生成）；不是 P3/MAML 授权，也不构成 R1 全面 PASS。")
A("")
A("## 一、结论摘要")
A("")
A("- P2 补采已完成：真实 VSPAERO 启动 " + str(acc["physical_solver_starts_actual"]) + " 次（本批上限 16，P2 累计 16/240），完成 " + str(acc["physical_solver_starts_completed"]) + "，失败 0，重试 " + str(acc["retries_actual"]) + "，并行 " + str(acc["parallelism"]) + "；内部 alpha 求解 case " + str(acc["internal_solver_cases_actual"]) + " 个。")
A("- 本批产出 " + str(acc["admitted_labels"]) + " 条唯一真实准入标签，NULL " + str(acc["null_labels"]) + "，行级有效率 " + ("%.2f%%" % (100 * acc["valid_label_rate_over_completed"])) + "，容差 1e-3 未放宽，全部来自可远端回读的原始 .polar 行。")
A("- 合并 R2/G1/G2 只读复用标签后，数据集为 " + str(ds["rows"]) + " 行 / " + str(ds["certificates"]) + " 张证书、8 个固定任务、44 条独立标签；K=5 因只有 d00–d03 四个独立 support 槽位判 NOT_ELIGIBLE（不以 query 充数）。")
A("- 四臂对照（FOMAML / 普通联合预训练 / 任务条件预训练 / 随机初始化）在 K=1、3 与种子 7/19/43 上完成；任务条件预训练最好，FOMAML 在 K=3 明显退化（负结果原样保留）。")
A("- 结论仅限 " + str(ds["rows"]) + " 行、2 个留出任务（M240/M260）的样本范围，不宣称统计显著或跨任务泛化；P3（BO/DE 预算对照）未授权。")
A("")
A("## 二、批次身份与授权链")
A("")
A("- run_id：" + acc["run_id"] + "；batch_id：" + acc["batch_id"] + "；authorization_id：" + acc["authorization_id"])
A("- Owner 指令：Issue #14 评论 7103901506（P2 执行指令）；P2 物理上限 240 starts，本批预注册上限 16 starts / 48 internal cases")
A("- 预注册 SHA256：" + sha(RUN / "p2_preregistration.json"))
A("- GO 记录 SHA256：" + sha(RUN / "p2_go_record.json") + "（绑定预注册、协议卷宗、协议 A5 verdict 与全部 source_code_sha256）")
A("- 协议 A5：" + str(proto.get("verdict")) + "（" + str(proto.get("reviewer")) + "，" + str(proto.get("reviewed_utc")) + "，非人类签署，human_signature=" + str(proto.get("human_signature")) + "）")
A("- 结果 A5：" + str(rver.get("verdict")) + "（" + str(rver.get("reviewer")) + "，" + str(rver.get("reviewed_utc")) + "，非人类签署）")
A("")
A("## 三、真实启动与内部成本")
A("")
A("| 口径 | 本批 | 上限 | 说明 |")
A("| --- | --- | --- | --- |")
A("| physical_solver_starts_actual | " + str(acc["physical_solver_starts_actual"]) + " | " + str(acc["max_starts"]) + " | 16 个设计 case，每 case 1 次真实启动 |")
A("| physical_solver_starts_completed | " + str(acc["physical_solver_starts_completed"]) + " | " + str(acc["max_starts"]) + " | 全部 SOLVED |")
A("| internal_solver_cases_actual | " + str(acc["internal_solver_cases_actual"]) + " | " + str(acc["max_internal_solver_cases"]) + " | 每 start 3 个局部迎角探针 |")
A("| retries | " + str(acc["retries_actual"]) + " | 0 | 失败不重跑 |")
A("| admitted_labels | " + str(acc["admitted_labels"]) + " | — | 原始 polar 行升力相对误差 <= 1.4e-4 |")
A("| null_labels | " + str(acc["null_labels"]) + " | — | 无 NULL 标签 |")
A("")
A("- 求解墙钟合计 " + str(acc["wall_clock_s"]) + " s；停止条件触发：" + str(acc["stops"]))
A("")
A("## 四、数据集、切分与去重披露")
A("")
A("- 数据集 SHA256：" + sha(RUN / "p2_dataset" / "p2_dataset.json") + "；行 " + str(ds["rows"]) + "，证书 " + str(ds["certificates"]) + "，excluded " + str(len(ds["excluded"])) + " 条")
A("- 任务族固定：train M140/M160/M200/M202；val M180/M220；test M240/M260（未因算法表现换任务）")
A("")
A("| 任务 | split | Mach | support | query | K=3 可行 |")
A("| --- | --- | --- | --- | --- | --- |")
for t in ds["tasks"]:
    A("| " + t["task_id"] + " | " + t["split"] + " | " + str(t["mach"]) + " | " + str(t["support"]) + " | " + str(t["query"]) + " | " + ("是" if (t["k3_support_ok"] and t["k3_query_ok"]) else "否") + " |")
A("")
A("- post-GO 数据构建器修复（已披露）：pre_fix " + str(diff["pre_fix"]["rows"]) + " 行 / excluded " + str(diff["pre_fix"]["excluded_count"]) + "（sha256 " + diff["pre_fix"]["sha256"] + "）→ post_fix " + str(diff["post_fix"]["rows"]) + " 行 / excluded " + str(diff["post_fix"]["excluded_count"]) + "（sha256 " + diff["post_fix"]["sha256"] + "）。")
A("- 新增准入记录 " + str(len(diff["added_admission_ids"])) + " 条，移除 " + str(len(diff["removed_admission_ids"])) + " 条；逐任务变化见 p2_dataset_diff.json。")
A("- 修复原因（中文）：R2 的低优先级 query 记录与 P2 补采 support 记录落在同一设计上，旧分支把双方同时剔除；修复后只剔除低优先级记录、保留高优先级记录。物理影响：不改变已发生的 16 次真实启动与 16 条标签，只影响样本分配。")
A("- 原始字段：" + diff["cause"] + "；" + diff["physical_effect"])
A("- K=5：NOT_ELIGIBLE（冻结协议仅 d00–d03 四个独立 support 槽位；禁止 query 充数或重复采样）。")
A("")
A("## 五、四臂协议与结果")
A("")
A("- 臂：" + ", ".join(res["arms"]) + "；K=" + str(res["k_values"]) + "；种子 " + str(res["seeds"]) + "；CPU float64")
A("- 容量与预算：隐藏层 [32,32]，最大 60 步，inner_lr 0.05、inner_steps 5、outer_lr 0.01、tasks_per_batch 2；四臂共享同一标签、同一归一化（仅 train 行 " + str(len(norm["fit_observation_ids"])) + " 条拟合）、同一种子与预算")
A("- 归一化参数 SHA256：" + res["normalizer"]["sha256"] + "；checkpoint 共 " + str(len(res["checkpoints"])) + " 个 npz（每臂 × K × 种子），逐文件 SHA 见 p2_training_result.json")
A("- val 只用于选参与早停，test 只评一次；训练过程物理启动 0 次")
A("")
A("| 方案 | val MAE (N) | val RMSE (N) | test MAE (N) | test RMSE (N) |")
A("| --- | --- | --- | --- | --- |")
rows_by = {}
for r in summ["rows"]:
    rows_by.setdefault(r["arm"], {})[r["split"]] = r
for arm in res["arms"]:
    v = rows_by.get(arm, {}).get("val", {})
    t = rows_by.get(arm, {}).get("test", {})
    A("| " + arm + " | " + ("%.1f" % v.get("mean_mae_n", float("nan"))) + " | " + ("%.1f" % v.get("mean_rmse_n", float("nan"))) + " | " + ("%.1f" % t.get("mean_mae_n", float("nan"))) + " | " + ("%.1f" % t.get("mean_rmse_n", float("nan"))) + " |")
A("")
A("- 每格为 12 个任务×K×种子组合的平均；逐任务逐种子明细见 p2_arm_metrics.csv，逐 query 预测见 p2_predictions.csv，训练曲线见 p2_training_curves.csv 与 figures/p2_training_curves.png")
A("- 离线候选排序诊断（非在线优化）：按预测最小 Di_N 选设计相对真实最优的遗憾，M180 约 0.67k/0.33k/0/1.8k N，M240 约 1.86k/1.86k/0.87k/1.86k N；M220/M260 各只有 1 个 query，遗憾恒为 0，不可用于比较")
A("")
A("## 六、负结果与诊断（不隐藏）")
A("")
A("- FOMAML 在 K=3 明显退化：部分种子的外循环损失后段从约 0.22 升到 0.43，K=3 留出 MAE 反而高于随机初始化；本轮 FOMAML 超参数未调（未用 test/val 反调），负结果原样保留。")
A("- 任务条件预训练在所有 split 上最好；普通联合预训练次之；随机初始化居中偏弱。")
A("- 未把 P1 的 196 对 18 内部工况差异记作 MAML 收益；本批未做该比较。")
A("- 不因训练器允许两任务就宣称验收：所有结论限制在 44 行标签、8 任务、2 个留出任务的范围内。")
A("")
A("## 七、产物上传与远端独立复核（A4）")
A("")
A("- 上传 commit：" + str(up.get("remote_head") or up.get("local_commit")) + "（分支 " + BRANCH + "，目录 research/concorde_metaopt/optimization_runs/DRECOVER001-P2-20261123-01）")
A("- 文件 " + str(up.get("file_count")) + " 个，共 " + str(up.get("total_bytes")) + " 字节；回读 checked=" + str((up.get("readback") or {}).get("checked")) + "，missing=" + str((up.get("readback") or {}).get("missing")) + "，bad=" + str((up.get("readback") or {}).get("bad")))
A("- data_manifest SHA256：" + str((up.get("readback") or {}).get("manifest_sha256")) + "；SHA256SUMS SHA256：" + str((up.get("readback") or {}).get("sha256sums_sha256")))
A("- 说明：A4 独立复核针对数据提交 " + str(audit["remote_head"]) + "；最终提交 " + str(up.get("remote_head") or up.get("local_commit")) + " 只追加 A5 审查产物与数据集 diff，已复核的 raw 字节未改变，最终包回读 380/380 通过。")
A("- 远端独立复核（GitHub blob API 原始字节）：remote head " + str(audit["remote_head"]) + "，复核 case " + str(audit.get("remote_case_count")) + " 个，通过 " + str(audit.get("cases_ok")) + " 个，bad=" + str(len(audit.get("bad") or [])) + "，A4 判据成立=" + str(audit.get("a4_criteria_met")))
A("- 复核方法：" + audit["method"])
A("- 每个 case 均校验证书 raw_sha256 等于远端 polar 字节 SHA256，并按证书 alpha 从远端原始行重算 CL/CDi 与 Di_N=q·Sref·CDi 恒等式。")
A("")
A("## 八、A5 独立审查范围与边界")
A("")
A("- 协议 A5（GO 前）：" + str(proto.get("verdict")) + "，审查预注册、补采矩阵、bracket 来源、预算与停止条件；不是人类签署。")
A("- 结果 A5（上传回读后）：" + str(rver.get("verdict")) + "，gate：" + json.dumps(rver.get("gate_verdicts"), ensure_ascii=False))
A("- A5 为 deepseek-flash 单发只读审查，非人类签署；不构成 R1 全面 PASS，也不授权 P3/MAML。")
A("- 唯一 minor：post-GO 去重修复已披露并已补逐项 diff；A5 复审 PASS。")
A("")
A("## 九、边界与披露")
A("")
for d in [
    "标签同机保存（Owner 已豁免异机独立故障域备份）；未做风洞/物理验证；physics_validated=false；fuel_burn_kg=null。",
    "目标为同升力（容差 1e-3）下翼面诱导阻力 Di_N=q·Sref·CDi；不含整机阻力/油耗；LF-M2.02 未验证。",
    "样本量小（44 行、2 个留出任务）；不宣称统计显著或普遍泛化；不把种子当独立任务。",
    "P1 仅为单任务 pilot，其 6 次启动未作为 P2 训练样本。",
    "M140 迎角接近 G2 stage-1 极曲线上界（9.52–9.76°），补采探针已夹紧在 bracket 内；本批 1.0 标签率不构成对其他 Mach 的保证。",
    "post-GO 代码变更：p2_data.py 去重优先级修复、p2_upload.py 远端校验改为逐层 tree 下钻（规避 recursive tree 截断）、新增 p2_train/p2_figures/p2_metadata/verify_p2_remote 脚本；这些变更不新增物理、不改变已发生的 16 次启动。",
]:
    A("- " + d)
A("")
A("## 十、下一门禁与未授权范围")
A("")
A("- P2 物理已用 16/240；后续批次需新的预注册 amendment、A5 审查与新 GO，不得沿用本批 GO。")
A("- P3（BO/DE 预算对照、在线优化）未预注册、未审查、未授权；MAML 的 claim 需要更多任务与独立 support/query 才能检验。")
A("- R1 全面 PASS、R2/#11 门禁状态不因本回执改变。")
A("")
A("## 附：证据文件 SHA256")
A("")
for name, h in copied:
    A("- " + name + "：" + h)
receipt = "\n".join(L) + "\n"
rp = OUTDIR / "p2_receipt_draft_20261123.md"
rp.write_text(receipt, encoding="utf-8", newline="\n")
print("receipt", len(receipt), sha(rp))
bad = []
for name, h in copied:
    if sha(OUTDIR / name) != h or (h not in receipt):
        bad.append(name)
print("listed", len(copied), "bad", bad)
