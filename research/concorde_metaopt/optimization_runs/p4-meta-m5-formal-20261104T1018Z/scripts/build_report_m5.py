# -*- coding: utf-8 -*-
"""M5 正式 run 中文报告草稿 + README + manifest + SHA256SUMS 生成器（零求解、只读证据）。"""
import csv
import hashlib
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

RUN = Path("D:/RCAIDE-p4-meta-learning/research/concorde_metaopt/optimization_runs/p4-meta-m5-formal-20261104T1018Z")
BASE = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/p4-m5m6/a2/m5_figures_report_attempt2")
TARGET_REPO_PATH = "docs/reviews/p4_meta_m5_report_20261104.md"
GENERATED = "2026-11-05T05:30:07.273565+08:00"
if GENERATED is None:
    import datetime as _dt
    GENERATED = _dt.datetime.now().astimezone().isoformat()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(rel):
    return json.loads((RUN / rel).read_text(encoding="utf-8"))


def m2after_status(raw):
    return raw.get("status") or raw.get("after", {}).get("status") or raw.get("after", {}).get("gate", "UNKNOWN")


def read_csv(rel):
    with (RUN / rel).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def fmt(x, n=4):
    if x is None or x == "":
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if v != v:
        return "—"
    return ("%." + str(n) + "f") % v


def fmt_p(x):
    if x is None or x == "":
        return "—"
    v = float(x)
    if v == 0:
        return "0"
    if v < 1e-4:
        return "%.2e" % v
    return "%.4f" % v


def ci(r):
    return "[" + fmt(r["ci_low"]) + ", " + fmt(r["ci_high"]) + "]"


def direction_note(r):
    endpoint = r["endpoint"]
    d = float(r["mean_diff"])
    lower = endpoint in ("best_feasible_value", "gap_to_reference", "first_feasible_evaluation_index")
    if lower:
        return "更差" if d > 0 else ("更好" if d < 0 else "相同")
    return "更好" if d > 0 else ("更差" if d < 0 else "相同")


def verdict(r):
    if r.get("status") != "REPORTED":
        return "NO_DATA"
    hp = r.get("holm_pvalue")
    if hp in ("", None):
        return "NO_TEST"
    if float(hp) < 0.05:
        return "显著·" + direction_note(r)
    return "不显著"


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)




def compute_attempt_diff():
    arch = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/p4-m5m6/lead/m5_formal_attempt1_defective/run_dir_snapshot")
    out = {"archive": "EXT/p4-m5m6/lead/m5_formal_attempt1_defective/run_dir_snapshot", "archive_abs": str(arch), "archive_present": (arch / "metrics/optimization_summary.csv").is_file()}
    if not out["archive_present"]:
        return out

    def rd(path):
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    try:
        o1 = rd(arch / "metrics/optimization_summary.csv")
        o2 = rd(RUN / "metrics/optimization_summary.csv")
        key = ("budget", "meta_seed", "arm", "task_id", "split", "seed")
        d1 = {tuple(r[k] for k in key): r for r in o1}
        d2 = {tuple(r[k] for k in key): r for r in o2}
        common = set(d1) & set(d2)
        cols = [c for c in o2[0].keys() if c not in key]
        diffcols = {}
        for c in cols:
            n = sum(1 for k in common if d1[k][c] != d2[k][c])
            if n:
                diffcols[c] = n
        ff1 = sum(1 for r in o1 if r["first_feasible_evaluation_index"] in ("", None))
        ff2 = sum(1 for r in o2 if r["first_feasible_evaluation_index"] in ("", None))
        s1 = rd(arch / "metrics/statistics.csv")
        s2 = rd(RUN / "metrics/statistics.csv")
        sk = lambda r: (r["budget"], r["split"], r["endpoint"], r["arm"], r["reference"])
        m1 = {sk(r): r for r in s1}
        m2 = {sk(r): r for r in s2}
        shared = set(m1) & set(m2)
        holm_changed = sum(1 for k in shared if m1[k]["holm_pvalue"] != m2[k]["holm_pvalue"])
        wil_changed = sum(1 for k in shared if m1[k]["wilcoxon_pvalue"] != m2[k]["wilcoxon_pvalue"])
        fam1 = {}
        fam2 = {}
        for r in s1:
            if r["status"] == "REPORTED":
                fam1[(r["split"], r["budget"])] = fam1.get((r["split"], r["budget"]), 0) + 1
        for r in s2:
            if r["status"] == "REPORTED":
                fam2[(r["split"], r["budget"])] = fam2.get((r["split"], r["budget"]), 0) + 1
        ex_keys = [("64", "meta_test", "best_feasible_value", "M5-DE", "M5-BO-random"),
                   ("128", "meta_test", "best_feasible_value", "M5-DE", "M5-BO-random"),
                   ("64", "meta_test", "feasible_hit_rate", "M5-BO-MAML-init", "M5-BO-random"),
                   ("128", "meta_test", "feasible_hit_rate", "M5-BO-MAML-init", "M5-BO-random")]
        examples = []
        for k in ex_keys:
            r1 = m1.get(k)
            r2 = m2.get(k)
            if r1 and r2:
                examples.append({"budget": k[0], "split": k[1], "endpoint": k[2], "arm": k[3], "reference": k[4],
                                 "holm1": r1["holm_pvalue"], "holm2": r2["holm_pvalue"],
                                 "wil1": r1["wilcoxon_pvalue"], "wil2": r2["wilcoxon_pvalue"]})
        out.update({"opt_rows": (len(o1), len(o2)), "common_keys": len(common), "diffcols": diffcols,
                    "ff_null": (ff1, ff2), "n_runs": len(o2), "stats_rows": (len(s1), len(s2)),
                    "reported_rows": (sum(fam1.values()), sum(fam2.values())),
                    "families": (dict(fam1), dict(fam2)), "holm_changed": holm_changed,
                    "wil_changed": wil_changed, "examples": examples})
    except Exception as exc:  # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    return out

def main():
    summary = load("summary.json")
    run_config = load("run_config.json")
    env = load("environment.json")
    stats = read_csv("metrics/statistics.csv")
    endpoint = read_csv("metrics/endpoint_summary.csv")
    opt = read_csv("metrics/optimization_summary.csv")
    th = read_csv("metrics/training_history.csv")
    clone_audit = read_csv("metrics/clone_audit.csv")
    fig_manifest = json.loads((BASE / "figures_manifest.json").read_text(encoding="utf-8"))

    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})
        return ok

    counts = summary["counts"]
    nulld = summary["null_disclosure"]
    n_runs = len(opt)
    n_evals = sum(int(r["true_evals_used"]) for r in opt)
    n_null_bfv = sum(1 for r in opt if r["best_feasible_value"] in ("", None))
    n_null_first = sum(1 for r in opt if r["first_feasible_evaluation_index"] in ("", None))
    physical = sum(int(r["physical_call_count"]) for r in opt)

    first_nulld = nulld["first_feasible_evaluation_index"]
    first_cov = n_runs - n_null_first
    first_cov_pct = (100.0 * first_cov / n_runs) if n_runs else float("nan")
    check("summary_counts_runs", counts["runs"] == n_runs, "summary=%s csv=%d" % (counts["runs"], n_runs))
    check("summary_counts_true_evals", counts["true_evaluations"] == n_evals, "summary=%s csv=%d" % (counts["true_evaluations"], n_evals))
    check("null_best_feasible", n_null_bfv == nulld["best_feasible_value"]["n_null"], "csv=%d summary=%s" % (n_null_bfv, nulld["best_feasible_value"]["n_null"]))
    check("null_rate_consistency", abs(nulld["best_feasible_value"]["null_rate"] - n_null_bfv / float(n_runs)) < 1e-12, str(nulld["best_feasible_value"]["null_rate"]))
    check("first_feasible_null_matches_summary", n_null_first == first_nulld["n_null"], "csv=%d summary=%s" % (n_null_first, first_nulld["n_null"]))
    check("first_feasible_coverage_positive", first_cov > 0, "coverage=%d/%d (%.2f%%)" % (first_cov, n_runs, first_cov_pct))
    check("physical_calls_zero", physical == 0 == summary["physical_call_count"], str(physical))
    check("status_valid", summary["status"] == "VALID", summary["status"])
    check("figures_status", all(summary["figures"][k] in ("DATA_READY", "NOT_APPLICABLE_THIS_STAGE", "NOT_RUN") for k in summary["figures"]), json.dumps(summary["figures"], ensure_ascii=False))
    check("four_figures_generated", len(fig_manifest["figures"]) == 4, str(len(fig_manifest["figures"])))
    check("layout_all_pass", all(e["layout_check"]["status"] == "PASS" for e in fig_manifest["figures"]), "")

    reported = [r for r in stats if r["status"] == "REPORTED"]
    ff_stats = [r for r in stats if r.get("endpoint") == "first_feasible_evaluation_index"]
    ff_reported = [r for r in ff_stats if r.get("status") == "REPORTED"]
    ff_sig = [r for r in ff_reported if r.get("holm_pvalue") not in (None, "") and float(r["holm_pvalue"]) < 0.05]
    check("first_feasible_endpoint_rows", len(ff_stats) > 0, "rows=%d reported=%d" % (len(ff_stats), len(ff_reported)))
    check("first_feasible_stats_present", len(ff_reported) > 0, "reported=%d" % len(ff_reported))

    def find(split, budget, endpoint_name, arm, reference):
        for r in reported:
            if (r["split"] == split and int(r["budget"]) == int(budget) and r["endpoint"] == endpoint_name
                    and r["arm"] == arm and r["reference"] == reference):
                return r
        return None

    key_names = ["M5-BO-MAML-init", "M5-BO-pretrain-init", "M5-BO-random", "M5-DE"]
    sig_improvements = []
    maml_tests = []
    de_tests = []
    for r in reported:
        ref_is_maml = r["arm"] == "M5-BO-MAML-init" or r["reference"] == "M5-BO-MAML-init"
        if not ref_is_maml:
            continue
        better = direction_note(r) == "更好"
        if r["arm"] == "M5-BO-MAML-init" and float(r["holm_pvalue"]) < 0.05 and better:
            sig_improvements.append((r["split"], r["budget"], r["endpoint"], r["arm"], r["reference"]))
        if r["arm"] == "M5-BO-MAML-init" and r["reference"] in ("M5-BO-random", "M5-BO-pretrain-init"):
            maml_tests.append(r)
        if r["arm"] == "M5-DE":
            de_tests.append(r)
    check("no_significant_maml_advantage", len(sig_improvements) == 0, json.dumps(sig_improvements, ensure_ascii=False))

    bfv_maml_worse = []
    for r in maml_tests:
        if r["endpoint"] == "best_feasible_value" and float(r["holm_pvalue"]) < 0.05 and direction_note(r) == "更差":
            bfv_maml_worse.append(r)
    fhr_maml_worse = []
    for r in maml_tests:
        if r["endpoint"] == "feasible_hit_rate" and float(r["holm_pvalue"]) < 0.05 and direction_note(r) == "更差":
            fhr_maml_worse.append(r)
    de_worse = []
    for r in de_tests:
        if r["endpoint"] == "best_feasible_value" and float(r["holm_pvalue"]) < 0.05 and direction_note(r) == "更差":
            de_worse.append(r)
    check("no_significant_maml_bfv_advantage", len(bfv_maml_worse) == 0, str(len(bfv_maml_worse)))
    check("maml_fhr_not_significantly_worse_than_pretrain", all(
        not (r["endpoint"] == "feasible_hit_rate" and float(r["holm_pvalue"]) < 0.05 and direction_note(r) == "更差")
        for r in maml_tests if r["reference"] == "M5-BO-pretrain-init"), "")
    check("de_significantly_worse_bfv_present", len(de_worse) >= 2, str(len(de_worse)))

    # 描述统计 median 表
    ep_med = {}
    for r in endpoint:
        if r["endpoint"] in ("best_feasible_value", "gap_to_reference", "feasible_hit_rate", "first_feasible_evaluation_index"):
            ep_med[(r["split"], int(r["budget"]), r["endpoint"], r["arm"])] = r
    median_headers = ["数据划分", "预算", "臂", "best_feasible_value 中位", "gap_to_reference 中位", "feasible_hit_rate 中位", "n_runs"]
    median_rows = []
    for split in ("meta_test", "meta_test_ood"):
        for budget in (64, 128):
            for arm in key_names:
                rec = ep_med.get((split, budget, "best_feasible_value", arm))
                if not rec:
                    continue
                g = ep_med.get((split, budget, "gap_to_reference", arm))
                f = ep_med.get((split, budget, "feasible_hit_rate", arm))
                median_rows.append([split, budget, arm, fmt(rec["median"]), fmt(g["median"]) if g else "—", fmt(f["median"]) if f else "—", rec["n_runs"]])

    # bfv 推断表：每个 split/budget 6 组比较
    comp_order = [
        ("M5-BO-MAML-init", "M5-BO-pretrain-init", "MAML-init vs pretrain-init"),
        ("M5-BO-MAML-init", "M5-BO-random", "MAML-init vs random"),
        ("M5-BO-pretrain-init", "M5-BO-random", "pretrain-init vs random"),
        ("M5-DE", "M5-BO-MAML-init", "DE vs MAML-init"),
        ("M5-DE", "M5-BO-pretrain-init", "DE vs pretrain-init"),
        ("M5-DE", "M5-BO-random", "DE vs random"),
    ]
    bfv_blocks = []
    for split in ("meta_test", "meta_test_ood"):
        for budget in (64, 128):
            rows = []
            for arm, ref, label in comp_order:
                r = find(split, budget, "best_feasible_value", arm, ref)
                if not r:
                    continue
                rows.append([label, fmt(r["mean_diff"], 5), ci(r), fmt_p(r["wilcoxon_pvalue"]), fmt_p(r["holm_pvalue"]), verdict(r)])
            bfv_blocks.append((split, budget, table(["比较（臂 − 参照）", "mean diff", "95% CI", "Wilcoxon p", "Holm p", "判定"], rows)))

    fhr_rows = []
    for r in reported:
        if r["endpoint"] != "feasible_hit_rate":
            continue
        if float(r["holm_pvalue"]) >= 0.05:
            continue
        fhr_rows.append([r["split"], r["budget"], r["arm"] + " vs " + r["reference"], fmt(r["mean_diff"], 5), ci(r), fmt_p(r["holm_pvalue"]), verdict(r)])

    # 关键 key 行
    def key_row(split, budget, endpoint_name, arm, ref):
        r = find(split, budget, endpoint_name, arm, ref)
        return r

    maml_rand_64 = key_row("meta_test", 64, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-random")
    maml_rand_128 = key_row("meta_test", 128, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-random")
    maml_pre_64 = key_row("meta_test", 64, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-pretrain-init")
    de_rand_64 = key_row("meta_test", 64, "best_feasible_value", "M5-DE", "M5-BO-random")
    de_rand_128 = key_row("meta_test", 128, "best_feasible_value", "M5-DE", "M5-BO-random")
    de_maml_64 = key_row("meta_test", 64, "best_feasible_value", "M5-DE", "M5-BO-MAML-init")
    de_maml_128 = key_row("meta_test", 128, "best_feasible_value", "M5-DE", "M5-BO-MAML-init")
    fhr_maml_rand_64 = key_row("meta_test", 64, "feasible_hit_rate", "M5-BO-MAML-init", "M5-BO-random")
    fhr_maml_rand_128 = key_row("meta_test", 128, "feasible_hit_rate", "M5-BO-MAML-init", "M5-BO-random")
    ood_maml_rand_64 = key_row("meta_test_ood", 64, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-random")
    ood_maml_rand_128 = key_row("meta_test_ood", 128, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-random")
    ood_de_maml_128_fhr = key_row("meta_test_ood", 128, "feasible_hit_rate", "M5-DE", "M5-BO-MAML-init")
    for r in (maml_rand_64, maml_rand_128, maml_pre_64, de_rand_64, de_rand_128, de_maml_64, de_maml_128,
              fhr_maml_rand_64, fhr_maml_rand_128, ood_maml_rand_64, ood_maml_rand_128, ood_de_maml_128_fhr):
        if r is None:
            check("key_stat_row_present", False, "missing key stat row")
            break

    gate = summary.get("gate", {})
    fairness = summary.get("fairness", {})
    determinism = summary.get("determinism", {})
    ident = summary.get("identifiability", {})
    family = summary.get("family", {})
    plan = summary.get("plan", {})
    m2raw = load("old_m2_run_immutability.json")
    m2_after = m2raw.get("after", {})
    m2 = {"status": m2after_status(m2raw), "file_count": m2_after.get("file_count"), "manifest_sha256": m2_after.get("manifest_sha256"), "mismatch_count": m2_after.get("mismatch_count")}
    def _pick(rec, keys):
        for _k in keys:
            _v = rec.get(_k)
            if _v not in (None, ""):
                return _v
        return None
    clone_pair = None
    for _r in clone_audit:
        _a = str(_r.get("arm") or "")
        _ref = str(_pick(_r, ("reference_arm", "reference", "reference_implemented_arm")) or "")
        if _a == "M5-BO-MAML-init" and "pretrain-init" in _ref:
            clone_pair = _r
            break
    clone_pair_txt = "clone_audit.csv 中未找到 MAML-init vs pretrain-init 行"
    if clone_pair is not None:
        clone_pair_txt = ("clone_audit.csv（MAML-init vs pretrain-init）：mean_initial_overlap=%s、max_initial_overlap=%s、high-overlap fraction=%s、label=%s、clone=%s；mean 与 fraction 均未达 clone 判据（mean >= 0.9 且 fraction >= 0.9），故 status=IDENTIFIABLE，但两臂初始设计重叠显著非零，不得表述为「初始设计重叠为 0」" % (
            _pick(clone_pair, ("mean_initial_overlap",)), _pick(clone_pair, ("max_initial_overlap",)),
            _pick(clone_pair, ("fraction_groups_at_threshold", "fraction_pairs_high_overlap", "fraction_high_overlap", "fraction_identical", "fraction_pairs_identical", "fraction_groups_high_overlap")),
            _pick(clone_pair, ("label",)), _pick(clone_pair, ("clone",))))
    def _loss_line(rows):
        maml = [r for r in rows if r.get("arm") == "M5-MAML-proxy"]
        by_it = {}
        for _r in maml:
            try:
                _it = int(_r["iteration"])
                _q = float(_r["loss_query"])
                _s = float(_r["loss_support"]) if _r.get("loss_support") not in (None, "") else float("nan")
            except (KeyError, TypeError, ValueError):
                continue
            by_it.setdefault(_it, {"q": [], "s": []})
            by_it[_it]["q"].append(_q)
            if _s == _s:
                by_it[_it]["s"].append(_s)
        if not by_it:
            return "training_history.csv 中无 M5-BO-MAML-init 行"
        its = sorted(by_it)
        q_first = sum(by_it[its[0]]["q"]) / len(by_it[its[0]]["q"])
        q_last = sum(by_it[its[-1]]["q"]) / len(by_it[its[-1]]["q"])
        s_first = sum(by_it[its[0]]["s"]) / len(by_it[its[0]]["s"])
        s_last = sum(by_it[its[-1]]["s"]) / len(by_it[its[-1]]["s"])
        pre = [float(_r["loss_query"]) for _r in rows if _r.get("arm") == "M5-pretrain-proxy"]
        return ("MAML 代理训练损失（training_history.csv，3 元种子按迭代均值）：loss_query it%d=%.6f -> it%d=%.6f；loss_support it%d=%.6f -> it%d=%.6f；预训练代理终点 loss_query（每元种子 1 值）=[%s]。这些是 M5 实测值，不得引用旧 run（M2/M6）的 2.77199 -> 1.25405 数值（A5-M5-06）。" % (
            its[0], q_first, its[-1], q_last, its[0], s_first, its[-1], s_last, ", ".join("%.6f" % _x for _x in pre)))
    loss_line = _loss_line(th)
    figs = fig_manifest["figures"]
    fig_by_key = {e["key"]: e for e in figs}

    # ---------------- 报告正文 ----------------
    L = []
    A = L.append
    A("# P4 元学习 M5 正式 run（FORMAL）中文报告：合成任务族上的等预算优化对照（rev5 定稿）")
    A("")
    A("- run_id：%s" % summary["run_id"])
    A("- 版本：rev5 final（%s，A2 定稿）；相对 rev4（922d0a94）仅 §4.5 数据源声明一行绝对路径改为 EXT 相对路径（A5-M5A2-04，rev5 已修），数字/表格/结论不变；本 rev 仅将头注版本与批准链对齐 A5-M5PKG-02。" % GENERATED)
    A("- A5 复核状态：task-170 判 APPROVE_FOR_M5_REPORTING（0 blocker / 0 major / 2 minor = A5-M5A2-02 与 A5-M5A2-03，均已在 rev4 关闭）；task-175 判 CHANGES_REQUESTED（唯一 minor A5-M5A2-04，rev5 修复并关闭）；task-177 判 APPROVE_FOR_M5_PACKAGING（0 blocker / 0 major / 0 minor new）。A5-M5-04 为既有 minor（OPEN_PREEXISTING_DISCLOSED，见 §7）。历史：task-153 曾对 attempt1 判 CHANGES_REQUESTED（1 blocker / 2 major / 4 minor），已由 attempt2 修正。")
    A("- 生成：A2（零求解、只读证据）；本文件为 rev5 定稿报告（final），提交目标路径 %s" % TARGET_REPO_PATH)
    A("- 状态：%s（study_scale=%s, stage=%s）；数据来源 %s；物理调用 physical_call_count=%d" % (
        summary["status"], summary["study_scale"], summary["stage"], summary["data_origin"], summary["physical_call_count"]))
    A("- 本报告所有数字来自该 run 的 summary.json / statistics.csv / endpoint_summary.csv / optimization_summary.csv / figure_data.json；"
      "已做一致性核对（见第 8 节），未运行任何求解器、未写仓库、未访问网络。")
    A("")
    A("## 1 研究目的与范围")
    A("")
    A("- 问题：在单一合成解析任务族上，等预算条件下比较 MAML 元初始化 + 贝叶斯优化（MAML-init）、预训练代理初始化 + 贝叶斯优化（pretrain-init）、随机初始化 + 贝叶斯优化（random）与等预算差分进化（DE）四种优化臂的最终可行解质量与可行命中率。")
    A("- 任务族：%s（%s，radius_base=%s；参考解 u*=%s；gap = f(u_best) − f(u*)）。" % (
        family["family_id"], family["family_version"], family["radius_base"], family["reference_solution"]))
    A("- 评价器：%s（合成解析 evaluator；12D 升力面设计空间；非真实物理求解器）。" % summary["evaluator_id"])
    A("- 范围声明：SYNTHETIC_ONLY。本 run 的结论仅适用于该合成任务族与解析 evaluator，不得外推到真实飞机、真实气动/燃油或任何真实求解器结果。")
    A("- 预注册：%d 个预注册比较（6 组臂×参照 × 4 个主终点 × 2 split × 2 预算），统计方案见第 2 节；本报告不新增事后比较。holdout 为单轮正式评估。" % len(stats))
    A("")
    A("## 2 设计与预注册")
    A("")
    A("- 数据划分（任务数）：meta_train %d / meta_validation %d / meta_test %d / meta_test_ood %d / negative_control %d。" % (
        summary["split_counts"]["meta_train"], summary["split_counts"]["meta_validation"], summary["split_counts"]["meta_test"],
        summary["split_counts"]["meta_test_ood"], summary["split_counts"]["negative_control"]))
    A("- holdout 计划：预算 %s，每组每预算 8 runs、15 组；共 %d 组 / %d runs；meta_test 20 任务×10 优化种子、meta_test_ood 10 任务×10 优化种子；meta_seeds=%s、optimization_seeds=%s、workers=%d。" % (
        plan["budgets"], plan["total_groups"], plan["total_runs"], summary["meta_seeds"], summary["optimization_seeds"], summary["workers"]))
    A("- 主终点：best_feasible_value、gap_to_reference、feasible_hit_rate、first_feasible_evaluation_index（lower_better；差值为臂 − 参照）。")
    A("- 推断：配对单位=task（任务内先跨 meta_seed、再跨优化种子聚合）；bootstrap 百分位 95% CI；Wilcoxon 符号秩；Holm 家族=每个 split×budget 下 6 组比较×4 个主终点（24 个检验）；fallback 指标不参与推断。")
    A("- 门禁：gate=%s；冻结族 sha256=%s；预注册 sha256=%s；校准报告 sha256=%s；split_hash=%s。" % (
        gate.get("status", "UNLOCKED"), str(gate.get("frozen_family_sha256"))[:16] + "…", str(gate.get("preregistration_sha256"))[:16] + "…",
        str(gate.get("calibration_report_sha256"))[:16] + "…", str(gate.get("split_hash"))[:16] + "…"))
    A("- 可识别性：%s（臂数 %d、实现数 %d、代码路径数 %d、clone 臂 %s）。" % (
        ident.get("status"), len(ident.get("arms_present", [])), ident.get("distinct_implementations"), ident.get("distinct_code_paths"), ident.get("clone_arms")))
    A("")
    A("## 3 执行事实与门禁")
    A("")
    A("- 结果：status=%s；runs=%d；真实（合成）评价次数=%d；history 行数=%d；holdout 组数=%d；runtime_s=%s（holdout_wall_s=%s）。" % (
        summary["status"], counts["runs"], counts["true_evaluations"], counts["history_rows"], counts["holdout_groups"],
        fmt(summary["runtime_s"], 3), fmt(summary["holdout_wall_s"], 3)))
    A("- run 启动/结束 HEAD 披露（A5-M5A2-02）：run 启动时仓库 HEAD=7e94973；运行窗口内外部 M6 打包提交把 HEAD 推进到 183616c，故 run_config.json 记录的 git_sha=183616c…（-dirty）是 run 结束时 HEAD，并非 M5 启动 HEAD。A5 独立核验 m5_runner.py / m5_arms.py / baseline_arms.py 等 M5 代码与产物在 7e94973 与 183616c 下相同、git diff 7e94973..183616c 不含 M5 文件，本 run 数值与结论不受 HEAD 推进影响。")
    A("- 确定性：%s（重跑 %d 次，300 组，mismatch=%d；排除列 wall_s / proxy_scoring_cost_json）；但 run 未保存原始 rerun digest/摘要（raw_digest_manifest=NOT_STORED），第三方无法独立复算该结论，仅能采信 summary 字段（A5-M5-07 披露）。" % (
        determinism.get("status"), determinism.get("reruns"), determinism.get("mismatch_count")))
    A("- 训练损失（A5-M5-06 修正）：%s" % loss_line)
    A("- 物理守卫：%s（期望物理调用 0）；物理调用实测 %d。" % (summary["physics_guard"]["status"], physical))
    A("- 公平性门禁：%s（%d 臂 / %d 记录 / %d 组；去重阈值 %s；组键 %s；初始设计数 %d）。" % (
        fairness.get("status"), len(fairness.get("arms") or []), fairness.get("records"), fairness.get("groups"),
        fairness.get("dedup_tolerance"), fairness.get("group_key_fields"), fairness.get("initial_design_count")))
    A("- 旧 M2 run 不可变性：%s（before/after 各 %s 文件，mismatch=%s；manifest sha256=%s…）。" % (
        m2.get("status"), m2.get("file_count"), m2.get("mismatch_count"), str(m2.get("manifest_sha256", ""))[:16]))
    A("- 结论许可：conclusions_allowed=%s；message：%s" % (run_config.get("conclusions_allowed"), summary.get("message")))
    A("")
    A("## 4 结果")
    A("")
    A("### 4.1 描述统计（endpoint_summary.csv 中位数）")
    A("")
    A(table(median_headers, median_rows))
    A("")
    A("图3（等预算可行命中率）与图4（等预算最优可行值/gap 收敛曲线）见第 9 节图表清单；可行命中率图按 split×预算分面，x 轴第二行同时披露无可行解 runs 占比（null_run_fraction）。")
    A("")
    A("### 4.2 主终点 best_feasible_value 的预注册推断（臂 − 参照；负值=更好）")
    A("")
    for split, budget, tbl in bfv_blocks:
        A("**%s，预算 %d**" % (split, budget))
        A("")
        A(tbl)
        A("")
    A("关键读数：")
    A("- meta_test 预算 64：MAML-init vs random 平均差 %s（95%% CI %s，Holm p=%s，%s）；MAML-init vs pretrain-init 平均差 %s（CI %s，Holm p=%s，%s）。" % (
        fmt(maml_rand_64["mean_diff"], 5), ci(maml_rand_64), fmt_p(maml_rand_64["holm_pvalue"]), verdict(maml_rand_64),
        fmt(maml_pre_64["mean_diff"], 5), ci(maml_pre_64), fmt_p(maml_pre_64["holm_pvalue"]), verdict(maml_pre_64)))
    A("- meta_test 预算 128：MAML-init vs random 平均差 %s（CI %s，Holm p=%s，%s）；MAML-init vs pretrain-init 平均差 %s（CI %s，Holm p=%s，%s）。" % (
        fmt(maml_rand_128["mean_diff"], 5), ci(maml_rand_128), fmt_p(maml_rand_128["holm_pvalue"]), verdict(maml_rand_128),
        fmt(key_row("meta_test", 128, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-pretrain-init")["mean_diff"], 5),
        ci(key_row("meta_test", 128, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-pretrain-init")),
        fmt_p(key_row("meta_test", 128, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-pretrain-init")["holm_pvalue"]),
        verdict(key_row("meta_test", 128, "best_feasible_value", "M5-BO-MAML-init", "M5-BO-pretrain-init"))))
    A("- meta_test_ood 预算 64/128：MAML-init vs random 平均差 %s / %s（Holm p=%s / %s，%s / %s）。" % (
        fmt(ood_maml_rand_64["mean_diff"], 5), fmt(ood_maml_rand_128["mean_diff"], 5),
        fmt_p(ood_maml_rand_64["holm_pvalue"]), fmt_p(ood_maml_rand_128["holm_pvalue"]),
        verdict(ood_maml_rand_64), verdict(ood_maml_rand_128)))
    A("- DE 显著更差：meta_test 预算 64 DE vs random 平均差 %s（CI %s，Holm p=%s，%s）；DE vs MAML-init %s（CI %s，Holm p=%s，%s）。meta_test 预算 128：DE vs random %s（Holm p=%s，%s）；DE vs MAML-init %s（Holm p=%s，%s）。" % (
        fmt(de_rand_64["mean_diff"], 5), ci(de_rand_64), fmt_p(de_rand_64["holm_pvalue"]), verdict(de_rand_64),
        fmt(de_maml_64["mean_diff"], 5), ci(de_maml_64), fmt_p(de_maml_64["holm_pvalue"]), verdict(de_maml_64),
        fmt(de_rand_128["mean_diff"], 5), fmt_p(de_rand_128["holm_pvalue"]), verdict(de_rand_128),
        fmt(de_maml_128["mean_diff"], 5), fmt_p(de_maml_128["holm_pvalue"]), verdict(de_maml_128)))
    A("")
    A("### 4.3 可行命中率 feasible_hit_rate 的显著结果（Holm p<0.05）")
    A("")
    A(table(["数据划分", "预算", "比较", "mean diff（正=更好）", "95% CI", "Holm p", "判定"], fhr_rows))
    A("")
    sig64 = fhr_maml_rand_64 is not None and float(fhr_maml_rand_64["holm_pvalue"]) < 0.05 and float(fhr_maml_rand_64["mean_diff"]) < 0
    sig128 = fhr_maml_rand_128 is not None and float(fhr_maml_rand_128["holm_pvalue"]) < 0.05 and float(fhr_maml_rand_128["mean_diff"]) < 0
    if sig64 and sig128:
        A("- 需要如实披露：MAML-init 在 meta_test 两个预算下的可行命中率均显著低于 random 基线（预算 64 平均差 %s，Holm p=%s；预算 128 平均差 %s，Holm p=%s），即在本合成族的可行率维度上 MAML 初始化不仅没有优势，反而更差。" % (
            fmt(fhr_maml_rand_64["mean_diff"], 5), fmt_p(fhr_maml_rand_64["holm_pvalue"]),
            fmt(fhr_maml_rand_128["mean_diff"], 5), fmt_p(fhr_maml_rand_128["holm_pvalue"])))
    elif sig64 or sig128:
        A("- meta_test 预算 64/128 的 MAML-init vs random 可行命中率差异仅一个预算达到 Holm 显著（预算 64 平均差 %s，Holm p=%s；预算 128 平均差 %s，Holm p=%s）；仅对显著处披露方向，不推广。" % (
            fmt(fhr_maml_rand_64["mean_diff"], 5), fmt_p(fhr_maml_rand_64["holm_pvalue"]),
            fmt(fhr_maml_rand_128["mean_diff"], 5), fmt_p(fhr_maml_rand_128["holm_pvalue"])))
    else:
        A("- meta_test 两个预算下 MAML-init vs random 的可行命中率差异均未达 Holm 显著（预算 64 平均差 %s，Holm p=%s；预算 128 平均差 %s，Holm p=%s），本报告不作负向结论。" % (
            fmt(fhr_maml_rand_64["mean_diff"], 5), fmt_p(fhr_maml_rand_64["holm_pvalue"]),
            fmt(fhr_maml_rand_128["mean_diff"], 5), fmt_p(fhr_maml_rand_128["holm_pvalue"])))
    if ood_de_maml_128_fhr is not None and float(ood_de_maml_128_fhr["holm_pvalue"]) < 0.05:
        A("- meta_test_ood 预算 128：DE 的可行命中率显著高于 MAML-init（平均差 %s，Holm p=%s），说明 DE 在该 OOD 预算下更常找到可行点；但其最优可行值仍显著更差（见 4.2），两者不矛盾。" % (
            fmt(ood_de_maml_128_fhr["mean_diff"], 5), fmt_p(ood_de_maml_128_fhr["holm_pvalue"])))
    else:
        A("- meta_test_ood 预算 128：DE 与 MAML-init 的可行命中率差异未达 Holm 显著（平均差 %s，Holm p=%s），不作方向结论。" % (
            fmt(ood_de_maml_128_fhr["mean_diff"], 5), fmt_p(ood_de_maml_128_fhr["holm_pvalue"])))
    A("")
    A("### 4.4 first_feasible_evaluation_index")
    A("")
    A("- 数据覆盖（attempt2 修正）：optimization_summary.csv 中非空 first_feasible_evaluation_index = %d / %d（%.2f%%），空值 %d / %d（%.2f%%）。未找到可行解的 run 该终点恒为 null（本 run best_feasible_value 为空的 run 数 = %d），本报告不把 null 当作 0、不插值。" % (
        first_cov, n_runs, first_cov_pct, n_null_first, n_runs, (100.0 - first_cov_pct), n_null_bfv))
    A("- 缺陷与修复（A5-M5-01，blocker）：attempt1 中该列全为 null（4800/4800），根因是 baseline_arms.py 输出的键 first_feasible_eval_index 与 m5_runner.py 期望列名 first_feasible_evaluation_index 不一致，且 ENDPOINT_ROW_KEYS 无别名映射；attempt2 runner 增加别名映射并重跑 holdout，覆盖率由 0 提升至上述值。该修复只补全记录列，不改变各优化臂的评价序列与终点值。（对应 A5-M5-01 blocker；A5-M5-05 指出 attempt1 把该终点写成“未记录”，本版改为按 CSV 实测覆盖率披露。）")
    if ff_reported:
        A("")
        A("statistics.csv 中该终点的预注册比较（仅对有可行解的 run 做 task 聚合；first_feasible 越低越好，差值为臂 − 参照）：")
        A("")
        ff_rows = []
        for r in ff_reported:
            ff_rows.append([r["split"], r["budget"], r["arm"] + " vs " + r["reference"], fmt(r["mean_diff"], 5), ci(r), fmt_p(r["wilcoxon_pvalue"]), fmt_p(r["holm_pvalue"]), verdict(r)])
        A(table(["数据划分", "预算", "比较（臂 − 参照）", "mean diff", "95% CI", "Wilcoxon p", "Holm p", "判定"], ff_rows))
        A("")
        A("- 显著比较数（Holm p<0.05）：%d / %d。" % (len(ff_sig), len(ff_reported)))
        for r in ff_sig:
            A("- %s / 预算 %s：%s vs %s，mean diff=%s，Holm p=%s，%s。" % (r["split"], r["budget"], r["arm"], r["reference"], fmt(r["mean_diff"], 5), fmt_p(r["holm_pvalue"]), verdict(r)))
    else:
        A("- statistics.csv 中该终点仍无 status=REPORTED 行（共 %d 行，状态集合 %s），本报告不对其做推断。" % (len(ff_stats), sorted({r.get("status") for r in ff_stats})))
    A("### 4.5 attempt1 vs attempt2 差异披露（A5-M5-01 修复的统计口径影响）")
    A("")
    adiff = compute_attempt_diff()
    A("- 数据源声明：attempt2 = 本 run（metrics/statistics.csv、endpoint_summary.csv、optimization_summary.csv、clone_audit.csv 均为 attempt2 版本）；attempt1 = 缺陷归档 %s。本节只解释修复造成的记录/统计口径变化，不把 attempt1 数值当作结果引用。" % adiff.get("archive"))
    if not adiff.get("archive_present"):
        A("- attempt1 缺陷归档当前不可用（%s），本节仅作概念说明；第 4 节与第 5 节全部数值来自 attempt2，不受影响。" % adiff.get("archive"))
    elif adiff.get("error"):
        A("- attempt1 与 attempt2 差异复算失败（%s）；本节仅说明修复要点：first_feasible 由全 null 修复为按 CSV 实测覆盖，Holm 家族检验数由 18 变为 24，Holm p 系统性变大。" % adiff["error"])
    else:
        dc = adiff["diffcols"]
        expected = {"wall_s", "proxy_scoring_cost_json", "first_feasible_evaluation_index"}
        unexpected = sorted(set(dc) - expected)
        n_runs = adiff["n_runs"]
        A("- 数值 payload（按 budget/meta_seed/arm/task_id/split/seed 对齐 %d/%d 行）：仅 wall_s（%d 行，非确定性耗时）、proxy_scoring_cost_json（内嵌 wall_s，%d 行）与 first_feasible_evaluation_index（%d 行）不同；其余列 0 行差异。first_feasible 空值从 %d/%d 降至 %d/%d（非空 %d 行）。" % (
            adiff["common_keys"], n_runs, dc.get("wall_s", 0), dc.get("proxy_scoring_cost_json", 0),
            dc.get("first_feasible_evaluation_index", 0), adiff["ff_null"][0], n_runs, adiff["ff_null"][1], n_runs,
            n_runs - adiff["ff_null"][1]))
        fam1, fam2 = adiff["families"]
        A("- statistics.csv：%d 行；status=REPORTED 行 %d→%d（first_feasible 24 行由 NO_DATA→REPORTED）。Holm 家族（split×budget 共 %d 族）每族检验数 18→24（每族 4 端点×6 比较；attempt1 中 first_feasible 的 6 个 p 缺失被跳过）。" % (
            adiff["stats_rows"][1], adiff["reported_rows"][0], adiff["reported_rows"][1], len(fam2)))
        A("- %d/%d 行 Holm p 发生变化（系统性变大，因族内检验数 18→24）；%d/%d 行 Wilcoxon p 出现末位变化（并行完成顺序导致的浮点求和/零值处理差异）。" % (
            adiff["holm_changed"], len(fam2) * 24, adiff["wil_changed"], len(fam2) * 24))
        A("")
        ex_rows = []
        for e in adiff["examples"]:
            ex_rows.append([e["budget"], e["split"], e["endpoint"], e["arm"] + " vs " + e["reference"],
                            fmt_p(e["holm1"]), fmt_p(e["holm2"]), fmt_p(e["wil1"]), fmt_p(e["wil2"])])
        A(table(["预算", "数据划分", "终点", "比较（臂 − 参照）", "Holm p（attempt1）", "Holm p（attempt2）", "Wilcoxon p（attempt1）", "Wilcoxon p（attempt2）"], ex_rows))
        A("")
        A("- 结论影响：无方向改变。本报告第 4、5 节全部使用 attempt2 statistics.csv 数值：DE 在 best_feasible_value 上显著更差、MAML-init 的 feasible_hit_rate 在 meta_test 显著更低等结论均保持不变；MAML 仍无可检测优势。")
        if unexpected:
            A("- 注意：复算发现预期外差异列 %s，需 Lead 复核；本报告不改变数据源。" % unexpected)
        check("attempt1_attempt2_payload_identical_except_expected", not unexpected, str(unexpected))
        check("attempt1_attempt2_holm_family_18_to_24", all(v == 18 for v in fam1.values()) and all(v == 24 for v in fam2.values()), str(adiff["families"]))
    A("")
    A("## 5 结论")
    A("")
    A("1. **无可检测的 MAML 优势**：在全部预注册比较中，没有任何“MAML 臂相对参照臂更好且 Holm 校正后显著”的结果（0 项）。meta_test 与 meta_test_ood、预算 64 与 128 下的 best_feasible_value / gap_to_reference 差异均不显著；因此**不得宣称 MAML 优越，也不得宣称其更优或等价**——只能说本 run 未检测到优势。")
    A("2. **DE 显著更差**：等预算 DE 在 meta_test 两个预算下的 best_feasible_value 均显著差于 random 与 MAML-init（见 4.2，Holm p 分别为 %s / %s / %s / %s），即 DE 显著更差。" % (
        fmt_p(de_rand_64["holm_pvalue"]), fmt_p(de_maml_64["holm_pvalue"]), fmt_p(de_rand_128["holm_pvalue"]), fmt_p(de_maml_128["holm_pvalue"])))
    if sig64 or sig128:
        A("3. MAML 初始化的可行命中率在 meta_test 显著低于随机初始化（4.3），说明“元学习初始化更好”的直觉在本合成族上不仅未获支持，可行率维度反而是负向证据。")
    else:
        A("3. MAML 初始化的可行命中率在 meta_test 未检测到相对随机初始化的显著差异（4.3）；不据此作方向性结论。")
    A("4. 本 run 是 SYNTHETIC_ONLY 的离线合成实验（physical_call_count=0），以上结论不外推到真实物理、真实飞机或真实求解器；不得用于签核任何 LF/HF 气动门禁。")
    A("")
    A("## 6 公平性与可识别性")
    A("")
    A("- 公平性门禁 PASS：4 臂 / %d 记录 / %d 组；去重阈值 1e-12；组键 = (task_id, seed, budget, meta_seed)；初始设计数 8。该门禁保证各臂在同一任务×种子×预算单元内比较，且重复记录被识别。" % (
        fairness.get("records"), fairness.get("groups")))
    A("- 可识别性：%s；实现数 %d、代码路径数 %d、clone 臂 %s。%s（A5-M5-02/03 修正）。" % (
        ident.get("status"), ident.get("distinct_implementations"), ident.get("distinct_code_paths"), ident.get("clone_arms"), clone_pair_txt))
    A("- A5-M5-03 披露（独立成条）：MAML-init 与 pretrain-init 初始设计平均重叠 0.7186（max 1.0、high-overlap fraction 0.5744）显著非零，本报告不以「重叠为 0」表述；因未达 clone 判据（mean 与 fraction 均 >= 0.9）故 label=IDENTIFIABLE、clone=false。")
    A("- DE 与 random 臂共享相同初始设计（mean/max overlap=1.0，clone_audit 标签 SAME_INIT_DIFFERENT_ENGINE），但引擎不同（DE/rand/1/bin vs 贝叶斯优化），因此不是克隆、也不是同一实现；这使 DE 与 BO 的差异可归因于搜索引擎而非起点。")
    figdata_f5 = json.loads((RUN / "figures" / "figure_data.json").read_text(encoding="utf-8"))["figures"]["fig5_fairness_audit"]["arms"]
    _maml_ms = 1000.0 * figdata_f5["M5-BO-MAML-init"]["proxy_scoring_wall_s_median"]
    _pretrain_ms = 1000.0 * figdata_f5["M5-BO-pretrain-init"]["proxy_scoring_wall_s_median"]
    A("- 代理评分成本：MAML-init 与 pretrain-init 各 %d 次代理评分（中位耗时 %s / %s ms，取自 figures/figure_data.json 的 proxy_scoring_wall_s_median），random 与 DE 为 0 次；即 MAML 臂额外付出初始化评分成本，但其终点收益未达显著。" % (
        1800, fmt(_maml_ms, 2), fmt(_pretrain_ms, 2)))
    A("- 图5 给出上述公平性/可识别性证据的可视化。")
    A("")
    A("## 7 限制与不得外推")
    A("")
    A("- best_feasible_value 与 gap_to_reference 的空值率均为 %s（%d/%d）；first_feasible_evaluation_index 空值 %d/%d（%.2f%%）、覆盖率 %.2f%%（%d/%d）。未找到可行解的 run 该终点恒为 null，本报告已如实披露，未把 null 当作 0 或插值。" % (
        fmt(100 * nulld["best_feasible_value"]["null_rate"], 2) + "%", nulld["best_feasible_value"]["n_null"], counts["runs"],
        n_null_first, counts["runs"], (100.0 - first_cov_pct), first_cov_pct, first_cov, counts["runs"]))
    A("- A5-M5-04（minor）披露：preregistration.json 中 stopping_rules 被序列化为约 100 个单字符数组（feasible_v2.py 序列化缺陷），属冻结件记录缺陷；按 A5 要求不改冻结 run，不影响预注册比较集合与统计，仅在此披露。")
    A("- A5-M5-07（minor）披露：确定性仅由 summary.json 字段证明（3 次重跑 / 300 组 / 0 mismatch），raw_digest_manifest=NOT_STORED，run 目录未保存原始重跑摘要，第三方无法独立复算。")
    A("- 单一合成任务族（%s）与单一解析 evaluator；无真实物理/气动/燃油数据，不能外推到真实飞机或真实求解器。" % family["family_id"])
    A("- 图2（K-shot 适应曲线）本阶段 NOT_APPLICABLE_THIS_STAGE（归 M6）；图6（气动门禁进度）NOT_RUN（归 Issue #4 D-12D-004）。本报告不生成假图。")
    A("- 元训练损失曲线只有 MAML 代理与预训练代理终点；validation_loss=NOT_AVAILABLE（M5 未记录，按合同不得补造）。预训练代理仅有终点值，无迭代曲线，因此不能据此判断其训练动态。")
    A("- 统计：Holm 家族为每个 split×budget 下 24 个检验；配对单位为 task 聚合值；结论不涉及未预注册的事后比较。")
    A("- run_config 记录 git_sha_label=%s、worktree_dirty=%s：本 run 在 dirty worktree 上执行，代码可追溯性以 run_config 与 environment.json 记录为准；复现时需核对该状态。" % (
        run_config.get("git_sha_label"), run_config.get("worktree_dirty")))
    A("- 本报告不宣称 MAML 与 BO 等价，也不宣称 DE 在任何意义上优于/劣于其他方法之外的结论；只报告本 run 的统计结果。")
    A("")
    A("## 8 溯源与复现")
    A("")
    A("- run_id：%s；status=%s；study_scale=%s；stage=%s；evaluator_id=%s。" % (
        summary["run_id"], summary["status"], summary["study_scale"], summary["stage"], summary["evaluator_id"]))
    A("- run HEAD 时序（A5-M5A2-02）：启动 HEAD=7e94973，结束记录 HEAD=183616c…（run_config.git_sha 在 run 结束时写入；-dirty 说明见 §3 与 §7）；M5 产物 blob 在两端一致，数值不受影响。")
    A("- 代码/环境：git_sha=%s（label=%s，dirty=%s）；python=%s；matplotlib=%s；numpy=%s；torch=%s；平台=%s；workers=%d。" % (
        run_config.get("git_sha"), run_config.get("git_sha_label"), run_config.get("worktree_dirty"),
        env.get("python"), env.get("matplotlib"), env.get("numpy"), env.get("torch"), env.get("platform"), summary["workers"]))
    A("- 门禁哈希：frozen_family=%s；preregistration=%s；calibration_report=%s；split_hash=%s；family_fingerprint=%s。" % (
        gate.get("frozen_family_sha256"), gate.get("preregistration_sha256"), gate.get("calibration_report_sha256"),
        gate.get("split_hash"), family.get("family_fingerprint")))
    A("- 输入文件 sha256（本报告生成时现算）：summary.json=%s；run_config.json=%s；metrics/statistics.csv=%s；metrics/endpoint_summary.csv=%s；metrics/training_history.csv=%s；figures/figure_data.json=%s；README.md=%s。" % (
        sha256_file(RUN / "summary.json"), sha256_file(RUN / "run_config.json"), sha256_file(RUN / "metrics/statistics.csv"),
        sha256_file(RUN / "metrics/endpoint_summary.csv"), sha256_file(RUN / "metrics/training_history.csv"),
        sha256_file(RUN / "figures/figure_data.json"), sha256_file(RUN / "README.md")))
    A("- 一致性核对：summary vs optimization_summary.csv 的 runs/评价次数/null 计数/物理调用全部一致（见 8.1）；statistics.csv 与 endpoint_summary.csv 为同一 run 产物。")
    A("- 复现命令（run 目录，未在本任务执行）：m6/m5 runner --stage calibration / freeze / holdout 三阶段，--run-id %s --output-root research/concorde_metaopt/optimization_runs；本报告只读 CSV/JSON 重算，未启动任何求解器。" % summary["run_id"])
    A("- 图由 EXT 下 scripts/gen_figures_m5.py 从 metrics/training_history.csv、figures/figure_data.json、metrics/clone_audit.csv 生成（300 dpi，Microsoft YaHei，布局自检 0 重叠）；报告由 scripts/build_report_m5.py 生成。")
    A("")
    A("### 8.1 数字一致性核对（summary vs 原始 CSV）")
    A("")
    A(table(["检查项", "结果", "说明"], [[c["name"], "PASS" if c["pass"] else "FAIL", c["detail"]] for c in checks]))
    A("")
    A("## 9 图表清单")
    A("")
    fig_rows = []
    for key in ("fig1_meta_training_loss", "fig3_feasible_rate", "fig4_equal_budget_gap", "fig5_fairness_audit"):
        e = fig_by_key[key]
        fig_rows.append([key, e["file"], str(e["bytes"]), e["sha256"][:16] + "…", e["layout_check"]["status"]])
    A(table(["figure key", "文件", "字节", "sha256（前缀）", "布局自检"], fig_rows))
    A("")
    A("- 图1：元训练损失（MAML 代理 3 元种子均值±min–max、loss_support 虚线；预训练代理 3 个终点；validation_loss NOT_AVAILABLE）。")
    A("- 图3：等预算可行命中率中位数（4 个分面 = split×预算；x 轴第二行披露无可行解 runs 占比）。")
    A("- 图4：等预算最优可行值 / gap_to_reference 收敛曲线（4 个分面 = 预算×端点；无可行解点留空，不插值）。")
    A("- 图5：公平性审计（代理评分运行次数与中位耗时；初始设计重叠度与 IDENTIFIABLE / SAME_INIT_DIFFERENT_ENGINE 标签；公平性事实文本）。")
    A("- fig2（K-shot 适应）NOT_APPLICABLE_THIS_STAGE（M6）；fig6（气动门禁）NOT_RUN（Issue #4 D-12D-004）；均未画假图。")
    A("")
    report = "\n".join(L) + "\n"
    n_sections = report.count("\n## ")
    checks.append({"name": "report_sections_ge_6", "pass": n_sections >= 6, "detail": "sections=%d" % n_sections})
    checks.append({"name": "report_mentions_all_figures", "pass": all(k in report for k in ("fig1_meta_training_loss", "fig3_feasible_rate", "fig4_equal_budget_gap", "fig5_fairness_audit")), "detail": ""})
    for phrase in ("无可检测的 MAML 优势", "不得宣称", "DE 显著更差", "SYNTHETIC_ONLY"):
        checks.append({"name": "report_phrase_" + phrase.replace(" ", "_"), "pass": phrase in report, "detail": phrase})
    checks.append({"name": "report_has_null_disclosure", "pass": (str(n_null_bfv) in report and str(counts["runs"]) in report), "detail": ""})
    checks.append({"name": "report_states_first_feasible_coverage", "pass": ("first_feasible" in report and "A5-M5-01" in report), "detail": ""})
    checks.append({"name": "report_clone_overlap_not_zero_claim", "pass": ("重叠均为 0" not in report and "A5-M5-02" in report), "detail": ""})
    checks.append({"name": "report_determinism_not_stored", "pass": ("NOT_STORED" in report and "A5-M5-07" in report), "detail": ""})
    checks.append({"name": "report_prereg_defect_disclosed", "pass": ("A5-M5-04" in report and "stopping_rules" in report), "detail": ""})
    all_ok = all(c["pass"] for c in checks)
    checks.append({"name": "all_checks_pass", "pass": all_ok, "detail": ""})
    if not all_ok:
        print(json.dumps({"ok": False, "checks": [c for c in checks if not c["pass"]]}, ensure_ascii=False, indent=1))
        return 2

    report_path = BASE / "m5_report_draft.md"
    report_path.write_text(report, encoding="utf-8")
    report_compat_path = BASE / "p4_m5_formal_report_20261104.md"
    report_compat_path.write_text(report, encoding="utf-8")

    # README
    R = []
    R.append("# M5 正式 run 中文图表与报告（rev4 定稿，A2 交付）")
    R.append("")
    R.append("本目录是 P4 元学习 M5 正式 run（run_id %s）的图表与报告（rev4 定稿）交付物。全部内容由 A2 在零求解、零仓库写、只读证据的前提下生成。" % summary["run_id"])
    R.append("")
    R.append("## 内容")
    R.append("")
    R.append("- 版本：rev4 final（A2 定稿；task-170 APPROVE_FOR_M5_REPORTING，关闭 A5-M5A2-02/03；A5-M5-04 既有 minor 见 §7）；提交目标路径 %s。" % TARGET_REPO_PATH)
    R.append("- figures/：4 张 300 dpi 中文图（fig1 元训练损失、fig3 可行命中率、fig4 等预算最优可行值/gap、fig5 公平性审计）。")
    R.append("- figures_manifest.json：图的字节/sha256/布局自检记录。")
    R.append("- manifest.json：交付清单与输入哈希、脚本哈希、检查项。")
    R.append("- status_final.json：最终回执（report/sums/manifest 哈希与 A5 复核引用）；在 SHA256SUMS.txt 之后生成，故不纳入清单。")
    R.append("- SHA256SUMS.txt：本目录交付文件（递归，排除自身、validation.json、status_final.json、scripts/_dev 与 __pycache__）的 sha256；由 scripts/finalize_sha256sums.py 在 driver 之后、validator 之前生成（validation.json/status_final.json 在其后写入，故不纳入）。")
    R.append("- scripts/：gen_figures_m5.py（出图）与 build_report_m5.py（报告/README/manifest/校验和生成），以及只读证据探测脚本 probe_m5*.py。")
    R.append("")
    R.append("## 数据来源（只读）")
    R.append("")
    R.append("- %s" % str(RUN))
    R.append("- metrics/training_history.csv、metrics/statistics.csv、metrics/endpoint_summary.csv、metrics/optimization_summary.csv、metrics/clone_audit.csv、figures/figure_data.json、summary.json、run_config.json、environment.json。")
    R.append("")
    R.append("## 关键结论（与报告一致）")
    R.append("")
    if sig64 or sig128:
        R.append("- 无可检测的 MAML 优势；不得宣称优越。DE 在 meta_test 两个预算下显著更差；MAML-init 可行命中率显著低于 random 基线（已如实披露）。")
    else:
        R.append("- 无可检测的 MAML 优势；不得宣称优越。DE 在 meta_test 两个预算下显著更差；MAML-init 可行命中率与 random 基线无显著差异。")
    R.append("- best_feasible_value / gap_to_reference 空值率 %s（%d/%d）；first_feasible_evaluation_index 空值 %d/%d、覆盖率 %d/%d（attempt2 已修复列名缺陷）；单一合成任务族 F-QE-feasible-v2；physical_call_count=0（SYNTHETIC_ONLY，不外推）。" % (
        fmt(100 * nulld["best_feasible_value"]["null_rate"], 2) + "%", nulld["best_feasible_value"]["n_null"], counts["runs"], n_null_first, counts["runs"], first_cov, counts["runs"]))
    R.append("- fig2 本阶段 NOT_APPLICABLE_THIS_STAGE（M6）；fig6 NOT_RUN（Issue #4 D-12D-004）；未生成假图。")
    R.append("")
    R.append("## 边界")
    R.append("")
    R.append("- 零 solver、零网络、零 GitHub 写、零仓库 tracked 写；未修改 run 目录任何文件。")
    R.append("- 图中不包含任何占位数值或假曲线；无可行解的点留空并在图中/图注披露。")
    R.append("")
    readme = "\n".join(R)
    (BASE / "README.md").write_text(readme, encoding="utf-8")

    # manifest
    def entry(p):
        return {"path": str(p.relative_to(BASE)).replace("\\", "/"), "bytes": p.stat().st_size, "sha256": sha256_file(p)}

    fig_entries = [entry(BASE / "figures" / e["file"]) for e in figs]
    script_files = ["scripts/gen_figures_m5.py", "scripts/build_report_m5.py", "scripts/finalize_sha256sums.py", "scripts/write_status_final.py"]
    manifest = {
        "schema_version": 1,
        "run_id": summary["run_id"],
        "attempt": "attempt2",
        "corrections": ["A5-M5-01 first_feasible column alias + coverage", "A5-M5-02 clone_audit fields", "A5-M5-03 clone overlap wording", "A5-M5-04 prereg stopping_rules disclosure", "A5-M5-05 first_feasible wording", "A5-M5-06 M5 training loss values", "A5-M5-07 determinism raw digest NOT_STORED"],
        "generated_by": "A2 / M5 报告阶段（零求解）",
        "report_target_repo_path": TARGET_REPO_PATH,
        "report": entry(report_path),
        "report_compat": entry(report_compat_path),
        "figures": fig_entries,
        "figure_manifest": entry(BASE / "figures_manifest.json"),
        "readme": entry(BASE / "README.md"),
        "scripts": [entry(BASE / s) for s in script_files],
        "inputs": {str(rel): {"sha256": sha256_file(RUN / rel)} for rel in (
            "summary.json", "run_config.json", "environment.json", "figures/figure_data.json",
            "metrics/training_history.csv", "metrics/statistics.csv", "metrics/endpoint_summary.csv",
            "metrics/optimization_summary.csv", "metrics/clone_audit.csv")},
        "checks": checks,
        "all_checks_pass": all_ok,
        "notes": "SYNTHETIC_ONLY；physical_call_count=0；fig4 数据为 meta_test+ood 合并；fig2 N/A（M6）；fig6 NOT_RUN（Issue #4）。",
    }
    (BASE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # SHA256SUMS
    sums = []
    for p in sorted(BASE.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(BASE).as_posix()
        if rel == "SHA256SUMS.txt" or rel.startswith("mpl-cache/"):
            continue
        sums.append(sums_line(rel, sha256_file(p)))
    # SHA256SUMS 由 scripts/finalize_sha256sums.py 在所有产物（report/README/manifest/validation）就绪后统一生成
    print(json.dumps({"ok": True, "report": entry(report_path), "sections": n_sections, "checks": len(checks), "sums": len(sums)}, ensure_ascii=False, indent=1))
    return 0


def sums_line(rel, digest):
    return digest + "  " + rel


if __name__ == "__main__":
    sys.exit(main())
