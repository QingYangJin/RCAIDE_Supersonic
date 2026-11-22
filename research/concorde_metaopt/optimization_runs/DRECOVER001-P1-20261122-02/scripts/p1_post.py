
"""P1 后处理：CSV、指标、中文图与运行元数据（零新物理）。
读取 p1_state.json / p1_accounting.json，输出 tables/*.csv、metadata/*.json、figures/*.png、
figure_data.csv、p1_result.json 与 README.md。不启动任何求解器。
"""
from __future__ import annotations
import csv, json, statistics
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P1-20261122-02")
FIG = RUN / "figures"; TAB = RUN / "tables"
for d in (FIG, TAB):
    d.mkdir(parents=True, exist_ok=True)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

state = json.loads((RUN / "p1_state.json").read_text(encoding="utf-8"))
acc = json.loads((RUN / "p1_accounting.json").read_text(encoding="utf-8"))
runs = acc["runs"]  # accounting rows already carry the backfilled internal counts

labels, seen = [], set()
for r in runs:
    if r.get("admitted") and r.get("admission_id") not in seen:
        seen.add(r["admission_id"]); labels.append(r)

def wcsv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

wcsv(TAB / "all_evaluations.csv",
     ["case_id", "design", "round", "status", "physical_solver_starts", "internal_solver_cases",
      "wall_s", "match_rel_error", "matched_alpha_deg", "matched_cl", "admitted", "di_n",
      "failure_kind", "detail"], runs)

by_design = {}
for r in sorted(runs, key=lambda x: (x["design"], x["round"], x["case_id"])):
    by_design.setdefault(r["design"], []).append(r)
hist = []
for d, rs in sorted(by_design.items()):
    best = None
    for i, r in enumerate(rs, 1):
        if r.get("admitted") and r.get("di_n") is not None:
            best = r["di_n"] if best is None else min(best, r["di_n"])
        hist.append({"design": d, "evaluation_index": i, "case_id": r["case_id"],
                     "physical_solver_starts": r.get("physical_solver_starts"),
                     "internal_solver_cases": r.get("internal_solver_cases"),
                     "wall_s": r.get("wall_s"), "status": r.get("status"),
                     "admitted": bool(r.get("admitted")),
                     "di_n": r.get("di_n"), "best_feasible_di_n_so_far": best,
                     "failure_kind": r.get("failure_kind")})
wcsv(TAB / "optimization_history.csv",
     ["design", "evaluation_index", "case_id", "physical_solver_starts", "internal_solver_cases",
      "wall_s", "status", "admitted", "di_n", "best_feasible_di_n_so_far", "failure_kind"], hist)

per_design = []
for d in sorted(by_design):
    rs = by_design[d]
    internal = sum(int(r.get("internal_solver_cases") or 0) for r in rs)
    wall = sum(float(r.get("wall_s") or 0) for r in rs)
    adms = [r for r in rs if r.get("admitted")]
    per_design.append({"design": d, "starts": sum(1 for r in rs if r.get("physical_solver_starts") == 1),
                       "internal_solver_cases": internal, "wall_clock_s": round(wall, 3),
                       "unique_labels": len({r.get("admission_id") for r in adms}),
                       "di_n": min((r["di_n"] for r in adms), default=None)})
wcsv(FIG / "figure_data.csv",
     ["design", "starts", "internal_solver_cases", "wall_clock_s", "unique_labels", "di_n"], per_design)

completed = sum(1 for r in runs if r["status"] == "SOLVED")
starts = sum(1 for r in runs if r.get("physical_solver_starts") == 1)
internal_total = sum(int(r.get("internal_solver_cases") or 0) for r in runs)
raw_matched = sum(1 for r in runs if (r.get("match_rel_error") is not None and r["match_rel_error"] <= 1e-3))
ipl = [p["internal_solver_cases"] for p in per_design]
metrics = {
    "schema": "dreal004.p1_metrics.v1",
    "run_id": acc["run_id"], "batch_id": acc["batch_id"], "authorization_id": acc["authorization_id"],
    "physical_solver_starts_actual": starts, "physical_solver_starts_completed": completed,
    "internal_solver_cases_actual": internal_total, "retries_actual": 0, "parallelism": 1,
    "admitted_rows": acc["admitted_rows"], "unique_admission_certificates": acc["unique_admission_certificates"],
    "admitted_labels": len(labels), "null_labels": acc["null_labels"],
    "duplicate_attempt_rows": acc["duplicate_attempt_rows"],
    "valid_label_rate_over_completed_rows": round(len(labels) / max(1, completed), 6),
    "raw_point_match_rate_over_starts": round(raw_matched / max(1, starts), 6),
    "target_label_rate": 0.70, "target_label_rate_met_on_rows": (len(labels) / max(1, completed)) >= 0.70,
    "sample_size_verdict": "UNDERPOWERED_SMALL_SAMPLE",
    "sample_size_note": "6 starts / 5 unique raw labels; 70 percent 仅按行计算，样本过小，不宣称目标稳健达成",
    "internal_solver_cases_per_label": round(internal_total / max(1, len(labels)), 3),
    "per_design_internal_solver_cases": ipl,
    "per_design_internal_median": statistics.median(ipl) if ipl else None,
    "per_design_internal_q1": statistics.quantiles(ipl, n=4)[0] if len(ipl) > 1 else None,
    "per_design_internal_q3": statistics.quantiles(ipl, n=4)[2] if len(ipl) > 1 else None,
    "total_wall_clock_s": round(sum(float(r.get("wall_s") or 0) for r in runs), 3),
    "fixed_sweep_internal_baseline": 4 * 49,
    "internal_saved_vs_fixed_sweep": 4 * 49 - internal_total,
    "evaluation_mode": "PILOT_NOT_A_TRAINING_BATCH",
    "physical_validation": "NOT_PERFORMED",
    "fuel_burn_kg": None,
    "lf_m202": "NOT_VALIDATED",
    "label_scope": "LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED_SAME_HOST",
}
(RUN / "p1_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

designs = sorted(by_design)
fig, axes = plt.subplots(2, 2, figsize=(9.6, 7.0), dpi=170)
for ax, d in zip(axes.ravel(), designs):
    rs = by_design[d]
    pts = sorted((a, cl) for r in rs for a, cl in (r.get("observed_rows") or []))
    clt = rs[0].get("cl_target")
    if pts:
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", color="#1f77b4", ms=5, lw=1.0, label="真实 VSPAERO 行")
    if clt is not None:
        ax.axhline(clt, color="#d62728", ls="--", lw=1.0, label="目标 CL")
    ax.set_title("设计 " + d + "：" + str(sum(1 for r in rs if r.get("physical_solver_starts") == 1)) + " starts / "
                 + str(sum(int(r.get("internal_solver_cases") or 0) for r in rs)) + " 个内部 alpha 点", fontsize=9)
    ax.set_xlabel("迎角 alpha（度）", fontsize=8); ax.set_ylabel("CL", fontsize=8)
    ax.grid(True, alpha=0.3); ax.tick_params(labelsize=7); ax.legend(fontsize=6.5)
fig.suptitle("P1 自适应迎角：局部 bracket 仅需 3 个真实 alpha 点（固定扫描为每设计 49 点）", fontsize=10)
fig.tight_layout(rect=(0, 0, 1, 0.97)); fig.savefig(FIG / "cl_alpha_adaptive_vs_fixed.png"); plt.close(fig)

cats = ["实际启动", "完成求解", "原始行命中rel<=1e-3", "唯一准入标签", "NULL", "重复启动"]
vals = [starts, completed, raw_matched, len(labels), acc["null_labels"],
        sum(1 for r in runs if r["case_id"] == "p1-m202-d00-r1") - 1]
fig, ax = plt.subplots(figsize=(8.2, 4.2), dpi=170)
bars = ax.bar(cats, vals, color=["#4c78a8", "#72b7b2", "#54a24b", "#59a14f", "#e15759", "#f58518"])
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.08, str(v), ha="center", va="bottom", fontsize=9)
ax.set_ylabel("计数")
ax.set_title("P1 小批：" + str(starts) + " 次真实 start、" + str(completed) + " 完成、" + str(len(labels))
             + " 条唯一标签（行级 " + str(len(labels)) + "/" + str(completed) + "="
             + ("%.1f" % (100 * len(labels) / max(1, completed))) + "%，目标 70%，样本不足）", fontsize=9)
ax.tick_params(axis="x", labelsize=7); fig.tight_layout(); fig.savefig(FIG / "p1_outcome_overview.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.8, 4.2), dpi=170)
sel = [p for p in per_design if p["di_n"] is not None]
names = [p["design"] for p in sel]
ys = [p["di_n"] / 1000.0 for p in sel]
bars = ax.bar(names, ys, color="#4c78a8", width=0.55)
for b, p, y in zip(bars, sel, ys):
    ax.text(b.get_x() + b.get_width() / 2, y - 0.25, "%.3f kN\n(p1 %d starts)" % (y, p["starts"]),
            ha="center", va="top", fontsize=7, color="white")
lo = min(ys) - 1.2; hi = max(ys) + 1.2
ax.set_ylim(lo, hi)
ax.set_xlabel("12D 设计（Mach 2.02，同升力目标）")
ax.set_ylabel("匹配升力下的诱导阻力 D_i (kN)")
ax.set_title("P1 真实准入标签：同升力下 Di_N 随设计变化（纵轴已放大至 %.1f-%.1f kN；仅翼面诱导阻力，非整机阻力/油耗）" % (lo, hi), fontsize=9)
ax.grid(True, axis="y", alpha=0.3); fig.tight_layout(); fig.savefig(FIG / "di_n_by_design.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.8, 4.2), dpi=170)
x = [p["design"] for p in per_design]
vals = [p["internal_solver_cases"] for p in per_design]
bars = ax.bar(x, vals, color="#72b7b2", width=0.55, label="本设计实际内部 alpha 求解 case 数")
ax.axhline(49, color="#e15759", ls="--", lw=1.2, label="固定 49 点扫描/设计（基线）")
for b, p, v in zip(bars, per_design, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.4, "%d 点\n%.2f 秒" % (v, p["wall_clock_s"]),
            ha="center", va="bottom", fontsize=7)
ax.set_ylim(0, 56)
ax.set_ylabel("内部 alpha solver cases / 设计"); ax.set_xlabel("设计")
ax.legend(fontsize=7.5, loc="upper right")
ax.set_title("P1 内部求解成本：自适应局部 bracket 仅 3 点/设计（d00 因两次启动+两轮为 9 点），总 18 个内部 case vs 固定 196 个", fontsize=9)
ax.grid(True, axis="y", alpha=0.3); fig.tight_layout(); fig.savefig(FIG / "internal_cost_by_design.png"); plt.close(fig)

(RUN / "run_config.json").write_text(json.dumps({
    "schema": "dreal004.p1_run_config.v1",
    "run_id": acc["run_id"], "batch_id": acc["batch_id"], "authorization_id": acc["authorization_id"],
    "owner_instruction_ref": "m10191 批准真实评估",
    "target_task": "DREAL004-M202", "mach": 2.02, "altitude_m": 18288.0,
    "designs": designs, "max_starts": 12, "max_starts_per_design": 3,
    "max_alpha_probes_per_start": 3, "max_internal_solver_cases": 36,
    "cl_tolerance_rel": 1e-3, "cl_tolerance_relaxed": False,
    "half_widths_deg": [0.004, 0.002, 0.001],
    "bracket_source": "G2 stage1 M202 coarse polar raw rows (zero new physics for bracket)",
    "solver": "VSPAERO 3.55.0 omp1", "parallelism": 1, "retries": 0,
    "alpha_points_per_start": 3, "label_evidence_scope": "SAME_HOST_NOT_AUTHENTICATED",
    "physical_validation": "NOT_PERFORMED", "fuel_burn_kg": None,
    "notes": [
        "P1 是 pilot，不是训练批次；不据此训练正式 MAML",
        "插值结果不进入严格 raw 训练集",
        "重复启动 p1-m202-d00-r1 两次均计费，标签按证书去重",
    ],
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

(RUN / "task_family_split.json").write_text(json.dumps({
    "schema": "dreal004.p1_task_family_split.v1",
    "status": "PILOT_SINGLE_TASK_ONLY_NOT_A_TRAINING_FAMILY",
    "tasks": [{"task_id": "DREAL004-M202", "split": "pilot", "mach": 2.02,
               "altitude_m": 18288.0, "q_pa": 20483.94023343017,
               "cl_target_12d_baseline": 0.18174391741992046}],
    "train_val_test_split": None,
    "note": "P1 仅一个 Mach 2.02 任务族 pilot；跨任务 train/val/test 冻结属于 P2，须另行 A5 审查与 GO",
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

geo = Path(r"D:/RCAIDE/.worktrees/drecover001-20261117/docs/evidence/drecover001/geometry_freeze_v2.json")
geo_ref = {"schema": "dreal004.p1_geometry_freeze_ref.v1",
           "source": "docs/evidence/drecover001/geometry_freeze_v2.json",
           "note": "P1 复用 GBFREEZE2 几何合同，未重新冻结几何"}
if geo.exists():
    g = json.loads(geo.read_text(encoding="utf-8"))
    geo_ref.update({"freeze_id": g.get("freeze_id"), "geometry_contract_sha256": g.get("geometry_contract_sha256")})
(RUN / "geometry_freeze.json").write_text(json.dumps(geo_ref, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

admissions = []
for r in labels:
    cert = RUN / "cases" / r["case_id"] / "admission_certificate.json"
    if cert.exists():
        c = json.loads(cert.read_text(encoding="utf-8"))
        admissions.append({"case_id": r["case_id"], "design": r["design"],
                           "admission_id": c.get("admission_id"), "di_n": c.get("di_n"),
                           "q_pa": c.get("q_pa"), "sref_m2": c.get("sref_m2"),
                           "cl": c.get("cl"), "cdi": c.get("cdi"),
                           "evidence_scope": c.get("evidence_scope"),
                           "certificate_sha256": r.get("certificate_sha256")})
(RUN / "metadata").mkdir(exist_ok=True)
(RUN / "metadata" / "admission_manifest_index.json").write_text(json.dumps({
    "schema": "dreal004.p1_admission_index.v1", "count": len(admissions),
    "admissions": admissions,
    "identity_check": "D_i_N = q * Sref * CDi 在每张证书内复核",
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

result = {
    "schema": "dreal004.p1_result.v1",
    "run_id": acc["run_id"], "batch_id": acc["batch_id"], "authorization_id": acc["authorization_id"],
    "metrics": metrics, "per_design": per_design,
    "admitted_labels": [{"design": r["design"], "case_id": r["case_id"], "di_n": r["di_n"],
                         "cl": r.get("matched_cl"), "alpha_deg": r.get("matched_alpha_deg"),
                         "rel_error": r.get("match_rel_error"), "admission_id": r.get("admission_id")}
                        for r in labels],
    "null_labels_detail": [{"case_id": r["case_id"], "failure_kind": r.get("failure_kind")}
                           for r in runs if not r.get("admitted")],
    "figures": [str(FIG / n) for n in ("cl_alpha_adaptive_vs_fixed.png", "p1_outcome_overview.png",
                                       "di_n_by_design.png", "internal_cost_by_design.png")],
    "disclosures": [
        "P1 是 pilot，不是训练批次；5 条标签不足以训练可靠 MAML",
        "p1-m202-d00-r1 被重复启动两次（两个进程重叠），两次均按真实 start 计费；标签按证书去重",
        "自适应搜索先用 G2 stage1 的 M202 coarse polar 原始行建立 bracket，该部分零新物理",
        "tol=1e-3 未放宽，插值只用于估计，不进入严格 raw 标签",
        "同机保存、未做异机认证；未做风洞/物理验证；fuel_burn_kg=null；LF-M2.02=NOT_VALIDATED",
    ],
}
(RUN / "p1_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

lines = ["# DRECOVER001-P1-20261122-02（P1 自适应迎角小批真实试验）", "",
         "性质：Issue #14 P1 pilot，不是训练批次，不据此训练正式跨任务 MAML。", "",
         "## 预算与记账", "",
         "- 真实 design starts：" + str(starts) + " / 上限 12（每设计 <=3）；完成求解 " + str(completed) + "；重试 0；并行 1。",
         "- 内部 alpha solver cases：" + str(internal_total) + "（每 start 3 个局部 alpha 点），上限 36；相对固定 49 点/设计扫描节省 " + str(4 * 49 - internal_total) + " 个内部 case。",
         "- 唯一真实准入标签：" + str(len(labels)) + " 条（另有 " + str(acc["admitted_rows"]) + " 行已准入；p1-m202-d00-r1 重复启动两次，标签按证书去重）。",
         "- 行级有效率：" + str(len(labels)) + "/" + str(completed) + " = " + ("%.1f" % (100 * len(labels) / max(1, completed))) + "%（目标 70%；样本过小 UNDERPOWERED，不宣称目标稳健达成）。",
         "- 每设计内部 case 中位数 " + str(metrics["per_design_internal_median"]) + "，总墙钟 " + str(metrics["total_wall_clock_s"]) + " 秒。",
         "", "## 标签（真实 raw 行，rel CL <= 1e-3，未放宽）", ""]
for r in labels:
    lines.append("- " + r["design"] + "：" + r["case_id"] + "，D_i_N=" + "%.3f" % r["di_n"]
                 + " N，CL=" + str(r.get("matched_cl")) + "，alpha=" + str(r.get("matched_alpha_deg"))
                 + "，rel=" + ("%.2e" % r.get("match_rel_error")))
lines += ["", "## 边界", "",
          "- 同机保存，未做异机认证；LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED。",
          "- 未做风洞/物理验证；fuel_burn_kg=null；LF-M2.02=NOT_VALIDATED。",
          "- 只报告翼面诱导阻力 D_i_N = q * Sref * CDi，不称整机总阻力或真实油耗。",
          "", "## 文件", "",
          "- raw_cases/：每个 case 的 .vspgeom/.vspaero/.polar/.history/.adb、deck、plan/approval/task_spec、审计与准入证书、stdout/stderr。",
          "- tables/：all_evaluations.csv、admitted_labels.csv、failed_or_null.csv、alpha_refinement_history.csv、actual_solver_ledger.csv、optimization_history.csv。",
          "- figures/：中文 PNG 4 张 + figure_data.csv。",
          "- metadata/、run_config.json、task_family_split.json、geometry_freeze.json、p1_result.json、p1_accounting.json、p1_metrics.json。"]
(RUN / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

print(json.dumps({"metrics": metrics, "labels": len(labels),
                  "figures": [str(p) for p in sorted(FIG.glob("*.png"))],
                  "result": str(RUN / "p1_result.json")}, ensure_ascii=False, indent=2))
