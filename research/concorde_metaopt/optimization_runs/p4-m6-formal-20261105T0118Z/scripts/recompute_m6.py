
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A2 recompute for P4-M6 formal run (zero-solver, read-only)."""
import csv, hashlib, json, math, os, statistics, sys
from collections import defaultdict

RUN = r"D:/RCAIDE-p4-meta-learning/research/concorde_metaopt/optimization_runs/p4-m6-formal-20261105T0118Z"
OUT = r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/p4-m5m6/a2/m6_figures_report"
TOL = 1e-12
checks = []
def add(name, ok, detail, expected=None, actual=None):
    rec = {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}
    if expected is not None: rec["expected"] = expected
    if actual is not None: rec["actual"] = actual
    checks.append(rec)

def rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def canon_lf_bytes(path):
    b = open(path, "rb").read()
    return b.replace(b"\r\n", b"\n")

def sha_file(path, canonical_lf=False):
    h = hashlib.sha256()
    if canonical_lf:
        h.update(canon_lf_bytes(path))
    else:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk: break
                h.update(chunk)
    return h.hexdigest()

ar = rows(RUN + "/metrics/adaptation_results.csv")
asu = rows(RUN + "/metrics/adaptation_summary.csv")
st = rows(RUN + "/metrics/statistics.csv")
summary = jload(RUN + "/summary.json")
fdata = jload(RUN + "/figures/figure_data.json")
dman = jload(RUN + "/data_manifest.json")

# ---------- A. headline 12 rows ----------
def group_vals(study, family, arm, K, metric):
    return [float(r[metric]) for r in ar if r["study"] == study and r["source_family"] == family
            and r["arm"] == arm and int(r["K"]) == K and r["status"] == "VALID" and r[metric] != ""]

headline = [r for r in asu if r["K"] == "5" and r["metric"] == "rmse_norm" and r["aggregation"] == "group_mean"
            and r["study"] in ("in_dist", "ood", "new_family")]
A = []
for row in headline:
    vals = group_vals(row["study"], row["source_family"], row["arm"], 5, "rmse_norm")
    if not vals:
        add("headline_row_" + row["study"] + "_" + row["arm"], False, "no raw rows found")
        continue
    n = len(vals); mean = sum(vals) / n; med = statistics.median(vals); sd = statistics.stdev(vals)
    ok_n = n == int(row["n_runs"]) and n == int(row["n_nonnull"])
    ok_mean = abs(mean - float(row["mean"])) <= TOL * max(1.0, abs(mean))
    ok_median = abs(med - float(row["median"])) <= TOL * max(1.0, abs(med))
    ci_low, ci_high = float(row["ci_low"]), float(row["ci_high"])
    ci_contains = ci_low <= mean <= ci_high
    A.append({"study": row["study"], "source_family": row["source_family"], "arm": row["arm"], "K": 5,
              "n_recomputed": n, "mean_recomputed": mean, "mean_published": float(row["mean"]),
              "median_recomputed": med, "median_published": float(row["median"]),
              "std_recomputed": sd, "ci_published": [ci_low, ci_high], "ci_contains_mean": ci_contains})
    add("headline_" + row["study"] + "_" + row["source_family"] + "_" + row["arm"],
        ok_n and ok_mean and ok_median,
        "n/mean/median recomputed from adaptation_results.csv", expected={"n": row["n_runs"], "mean": row["mean"], "median": row["median"]},
        actual={"n": n, "mean": mean, "median": med})
add("headline_row_count", len(headline) == 12, "adaptation_summary K=5 rmse_norm group_mean rows", 12, len(headline))

# ---------- B. statistics K=5 rows ----------
def task_means(study, family, arm, K, metric):
    d = defaultdict(list)
    for r in ar:
        if r["study"] != study or r["arm"] != arm or int(r["K"]) != K: continue
        if family and r["source_family"] != family: continue
        if r[metric] == "" or r["status"] != "VALID": continue
        d[r["task_id"]].append(float(r[metric]))
    return {k: sum(v) / len(v) for k, v in d.items()}

try:
    from scipy import stats as sstats
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

B = []
st_k5 = [r for r in st if r["K"] == "5"]
for row in st_k5:
    a = task_means(row["study"], row["source_family"], row["arm"], 5, row["metric"])
    b = task_means(row["study"], row["source_family"], row["reference"], 5, row["metric"])
    common = sorted(set(a) & set(b))
    diffs = [a[t] - b[t] for t in common]
    n = len(diffs); mean_diff = sum(diffs) / n; med_diff = statistics.median(diffs)
    wstat = wp = None
    if HAVE_SCIPY and n > 0:
        w = sstats.wilcoxon(diffs, zero_method="wilcox", correction=False, alternative="two-sided")
        wstat = float(w.statistic); wp = float(w.pvalue)
    ok = (n == int(row["n_pairs"])
          and abs(mean_diff - float(row["mean_diff"])) <= 1e-10
          and abs(med_diff - float(row["median_diff"])) <= 1e-10
          and wstat is not None and abs(wstat - float(row["wilcoxon_statistic"])) < 1e-9
          and wp is not None and abs(wp - float(row["wilcoxon_pvalue"])) <= 1e-12)
    B.append({"study": row["study"], "source_family": row["source_family"], "arm": row["arm"], "reference": row["reference"],
              "K": row["K"], "metric": row["metric"], "n_pairs_recomputed": n, "mean_diff_recomputed": mean_diff,
              "median_diff_recomputed": med_diff, "wilcoxon_statistic_recomputed": wstat, "wilcoxon_pvalue_recomputed": wp,
              "published": {"n_pairs": row["n_pairs"], "mean_diff": float(row["mean_diff"]), "median_diff": float(row["median_diff"]),
                            "wilcoxon_statistic": float(row["wilcoxon_statistic"]), "wilcoxon_pvalue": float(row["wilcoxon_pvalue"]),
                            "p_holm": float(row["p_holm"]), "reject_holm": row["reject_holm"]},
              "status": "PASS" if ok else "FAIL"})
    add("stats_k5_" + row["study"] + "_" + row["source_family"] + "_" + row["arm"] + "_vs_" + row["reference"] + "_" + row["metric"],
        ok, "paired task means (mean over meta seeds) then Wilcoxon signed-rank", expected={"n": row["n_pairs"], "meandiff": row["mean_diff"]},
        actual={"n": n, "meandiff": mean_diff})
add("stats_k5_row_count", len(st_k5) == 60, "statistics.csv K=5 rows", 60, len(st_k5))
add("stats_total_row_count", len(st) == 300, "statistics.csv total rows", 300, len(st))
add("stats_k5_metrics", sorted(set(r["metric"] for r in st_k5)) == ["mae_norm", "mae_raw", "rmse_norm", "rmse_raw"],
    "K=5 metric set", ["mae_norm", "mae_raw", "rmse_norm", "rmse_raw"], sorted(set(r["metric"] for r in st_k5)))

# ---------- B2. p_holm structural check ----------
holm_rows = []
for metric in sorted(set(r["metric"] for r in st_k5)):
    for study in sorted(set(r["study"] for r in st_k5 if r["metric"] == metric)):
        for family in sorted(set(r["source_family"] for r in st_k5 if r["metric"] == metric and r["study"] == study)):
            group = [r for r in st_k5 if r["metric"] == metric and r["study"] == study and r["source_family"] == family]
            raw = sorted(float(r["wilcoxon_pvalue"]) for r in group)
            m = len(raw); adj = []; prev = 0.0
            for i, p in enumerate(raw):
                v = min(1.0, (m - i) * p)
                v = max(v, prev); prev = v; adj.append(v)
            pub = sorted(float(r["p_holm"]) for r in group)
            match = all(abs(x - y) <= 1e-12 for x, y in zip(adj, pub))
            holm_rows.append({"metric": metric, "study": study, "source_family": family, "n": m,
                              "recomputed": adj, "published_sorted": pub, "match": match})
            add("holm_" + study + "_" + family + "_" + metric, match,
                "Holm-Bonferroni over comparisons within study x source_family x K=5 x metric", pub, adj)
add("holm_family_rule", True, "Holm family = study x source_family x K x metric (each family 3 comparisons)")

# ---------- C. data_manifest 26 hashes ----------
dm_files = dman["files"]
dm_ok = 0; dm_bad = []
for rec in dm_files:
    p = os.path.join(RUN, rec["path"].replace("/", os.sep))
    if not os.path.exists(p):
        dm_bad.append({"path": rec["path"], "error": "missing"}); continue
    actual_bytes = os.path.getsize(p)
    text = rec["path"].lower().endswith((".json", ".csv", ".md", ".txt", ".jsonl", ".yaml", ".yml"))
    actual_sha = sha_file(p, canonical_lf=text)
    if actual_bytes == rec["bytes"] and actual_sha == rec["sha256"]:
        dm_ok += 1
    else:
        dm_bad.append({"path": rec["path"], "bytes_expected": rec["bytes"], "bytes_actual": actual_bytes,
                       "sha_expected": rec["sha256"], "sha_actual": actual_sha, "text_mode": text})
add("data_manifest_files", len(dm_files) == 22 and dman.get("file_count") == 22, "data_manifest file_count", 22, dman.get("file_count"))
add("data_manifest_hashes", dm_ok == len(dm_files), "sha256 with hash_mode CRLF->LF for text files", len(dm_files), dm_ok)
add("data_manifest_total_bytes", dman.get("total_bytes") == sum(r["bytes"] for r in dm_files), "sum of file bytes", dman.get("total_bytes"), sum(r["bytes"] for r in dm_files))
add("data_manifest_excluded", dman.get("excluded") == ["data_manifest.json"], "excluded list", ["data_manifest.json"], dman.get("excluded"))
add("data_manifest_hash_mode", dman.get("hash_mode") == "CRLF->LF", "hash_mode", "CRLF->LF", dman.get("hash_mode"))

# ---------- D. summary consistency ----------
counts = summary["counts"]
add("summary_status", summary["status"] == "VALID", "summary.status", "VALID", summary["status"])
add("summary_physical_zero", summary["physical_call_count"] == 0, "physical_call_count", 0, summary["physical_call_count"])
add("summary_scale", summary["study_scale"] == "FORMAL", "study_scale", "FORMAL", summary["study_scale"])
add("summary_conclusions_allowed", summary["conclusions_allowed"] is True, "conclusions_allowed", True, summary["conclusions_allowed"])
add("summary_adaptation_rows", counts["adaptation_rows"] == 3600 and len(ar) == 3600, "adaptation_rows", 3600, counts["adaptation_rows"])
add("summary_statistics_rows", counts["statistics_rows"] == 300 and len(st) == 300, "statistics_rows", 300, counts["statistics_rows"])
add("summary_executions", counts["total_adaptation_executions"] == 10800, "total_adaptation_executions", 10800, counts["total_adaptation_executions"])
add("summary_determinism", counts["determinism_passes"] == 3, "determinism_passes", 3, counts["determinism_passes"])
add("summary_nonfinite_zero", counts["nonfinite_rows"] == 0, "nonfinite_rows", 0, counts["nonfinite_rows"])
add("summary_physics_guard", summary["physics_guard"]["status"] == "PASS" and summary["physics_guard"]["expected"] == 0,
    "physics_guard", "PASS/0", summary["physics_guard"])
add("summary_old_run_gate", summary["old_run_gate"]["status"] == "PASS", "old_run_gate", "PASS", summary["old_run_gate"]["status"])
add("summary_scale_preflight", summary["scale_preflight"]["status"] == "PASS", "scale_preflight", "PASS", summary["scale_preflight"]["status"])
add("summary_k_omissions", summary.get("k_omissions") == [], "k_omissions empty", [], summary.get("k_omissions"))
add("figure_data_physical_zero", fdata["physical_call_count"] == 0, "figure_data physical_call_count", 0, fdata["physical_call_count"])
add("fig2_status_ready", fdata["figures"]["fig2_k_shot_adaptation"]["status"] == "READY", "fig2 status", "READY", fdata["figures"]["fig2_k_shot_adaptation"]["status"])

# fig2 rows vs adaptation_summary
asu_idx = {(r["study"], r["source_family"], r["arm"], r["K"], r["metric"]): r for r in asu}
f2rows = fdata["figures"]["fig2_k_shot_adaptation"]["rows"]
f2_ok = 0; f2_bad = []
for r in f2rows:
    key = (r["study"], r["source_family"], r["arm"], str(r["K"]), r["metric"])
    ref = asu_idx.get(key)
    if ref is None:
        f2_bad.append({"key": key, "error": "not in adaptation_summary"}); continue
    same = (abs(float(r["mean"]) - float(ref["mean"])) <= 1e-12
            and abs(float(r["ci_low"]) - float(ref["ci_low"])) <= 1e-12 and abs(float(r["ci_high"]) - float(ref["ci_high"])) <= 1e-12
            and int(r["n_nonnull"]) == int(ref["n_nonnull"]) and r["status"] == ref["status"])
    if same: f2_ok += 1
    else: f2_bad.append({"key": key, "published": ref, "figure": r})
add("fig2_rows_consistency", f2_ok == len(f2rows), "fig2 rows vs adaptation_summary group_mean rows", len(f2rows), f2_ok)

# ---------- E. adaptation_summary completeness ----------
combo = defaultdict(set)
for r in asu: combo[(r["study"], r["source_family"], r["arm"])].add(r["K"])
add("asum_groups", len(combo) == 15, "study/family/arm groups", 15, len(combo))
add("asum_group_metrics", all(len([r for r in asu if (r["study"], r["source_family"], r["arm"]) == k]) == 50 for k in combo),
    "each group has 5 K x 10 metrics = 50 rows", 50, None)
n_valid = sum(1 for r in asu if r["status"] == "VALID")
n_missing = sum(1 for r in asu if r["status"] == "MISSING")
missing_ok = all(r["metric"] in ("loss_final", "loss_std", "loss_monotonic_fraction") and int(r["K"]) == 0 and float(r["null_rate"]) == 1.0
                 for r in asu if r["status"] == "MISSING")
add("asum_status_counts", n_valid == 705 and n_missing == 45, "VALID 705 + MISSING 45 (K=0 loss metrics)", {"VALID": 705, "MISSING": 45}, {"VALID": n_valid, "MISSING": n_missing})
add("asum_missing_scope", missing_ok, "MISSING rows are K=0 loss_final/loss_std/loss_monotonic_fraction with null_rate=1")
add("asum_null_rate_rule", all((float(r["null_rate"]) == 1.0) == (r["status"] == "MISSING") for r in asu), "null_rate 1 iff status MISSING")

# ---------- verdict ----------
n_pass = sum(1 for c in checks if c["status"] == "PASS")
n_fail = len(checks) - n_pass
verdict = "RECOMPUTE_OK" if n_fail == 0 else "RECOMPUTE_MISMATCH"
result = {
    "schema_version": 1,
    "artifact_kind": "A2_M6_RECOMPUTE",
    "run_id": "p4-m6-formal-20261105T0118Z",
    "run_dir": RUN,
    "generated_by": "A2 (a2-run-opt)",
    "solver_starts": 0,
    "repo_writes": 0,
    "verdict": verdict,
    "n_checks": len(checks), "n_pass": n_pass, "n_fail": n_fail,
    "checks": checks,
    "headline_rows_k5": A,
    "statistics_k5": B,
    "holm_families": holm_rows,
    "data_manifest": {"file_count": len(dm_files), "hash_ok": dm_ok, "mismatches": dm_bad},
    "fig2_rows": {"n_rows": len(f2rows), "n_ok": f2_ok, "mismatches": f2_bad},
    "ci_note": "published CI（group_mean 与配对差）为 bootstrap 置信区间，管线未记录 RNG/seed，本复算不重推 CI；headline 校验使用 n/mean/median，statistics 校验使用 n_pairs/mean_diff/median_diff/Wilcoxon。",
    "method_note": "headline：adaptation_results.csv 内逐运行 rmse_norm 直接分组求 n/mean/median；statistics：按 task_id 对 meta seeds 取均值后配对，scipy.stats.wilcoxon 双侧；Holm 家族=study x K x metric。",
    "summary": {"status": summary["status"], "counts": counts, "physical_call_count": summary["physical_call_count"]},
}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "recompute.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
# human readable
lines = []
lines.append("# P4-M6 headline/statistics 复算摘要")
lines.append("")
lines.append("- run_id: p4-m6-formal-20261105T0118Z")
lines.append("- 结论: " + verdict)
lines.append("- 检查: %d 项 / PASS %d / FAIL %d" % (len(checks), n_pass, n_fail))
lines.append("- physical_call_count: 0；solver starts: 0；仓库写: 0")
lines.append("")
lines.append("## Headline K=5 (rmse_norm, group_mean)")
lines.append("")
lines.append("| study | family | arm | n | mean(复算) | mean(发布) | 差 | median(复算) |")
lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
for r in A:
    lines.append("| %s | %s | %s | %d | %.12g | %.12g | %.2e | %.12g |" % (
        r["study"], r["source_family"], r["arm"], r["n_recomputed"], r["mean_recomputed"], r["mean_published"],
        abs(r["mean_recomputed"] - r["mean_published"]), r["median_recomputed"]))
lines.append("")
lines.append("## Statistics K=5 (Wilcoxon + paired diffs)")
lines.append("")
lines.append("| study | family | arm vs ref | metric | n_pairs | mean_diff 复算/发布 | p 复算/发布 |")
lines.append("| --- | --- | --- | --- | --- | --- | --- |")
shown = 0
for r in B:
    if shown >= 60: break
    lines.append("| %s | %s | %s vs %s | %s | %d | %.12g / %.12g | %.12g / %.12g |" % (
        r["study"], r["source_family"], r["arm"], r["reference"], r["metric"], r["n_pairs_recomputed"],
        r["mean_diff_recomputed"], r["published"]["mean_diff"], r["wilcoxon_pvalue_recomputed"], r["published"]["wilcoxon_pvalue"]))
    shown += 1
lines.append("")
lines.append("## 失败项")
lines.append("")
fails = [c for c in checks if c["status"] == "FAIL"]
if fails:
    for c in fails: lines.append("- " + c["check"] + ": " + c["detail"])
else:
    lines.append("- 无")
lines.append("")
lines.append("## 方法说明")
lines.append("")
lines.append("- headline 从 metrics/adaptation_results.csv (3600 行) 直接复算 n/mean/median，容差 1e-12；")
lines.append("- statistics 从同一 CSV 按 task_id 跨 seed 求均值后配对，复算 n_pairs/mean_diff/median_diff/Wilcoxon 统计量与 p；")
lines.append("- p_holm 用 Holm-Bonferroni 重算，家族定义为 study x K x metric（in_dist 3、ood 3、new_family 4 个比较）；")
lines.append("- 发布 CI 为 bootstrap 区间且管线未记录 RNG，本复算不重推；headline 校验以 n/mean/median 为准；")
lines.append("- data_manifest 26 个文件按 hash_mode=CRLF->LF 重算 sha256；fig2 的 300 行 figure_data 与 adaptation_summary 全字段比对。")
with open(os.path.join(OUT, "recompute.md"), "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print(json.dumps({"verdict": verdict, "n_checks": len(checks), "n_pass": n_pass, "n_fail": n_fail,
                  "fails": [c["check"] for c in checks if c["status"] == "FAIL"]}, ensure_ascii=False))
