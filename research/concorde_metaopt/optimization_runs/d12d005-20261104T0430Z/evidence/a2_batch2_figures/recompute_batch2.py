# -*- coding: utf-8 -*-
"""Recompute D-12D-005 Batch2 numbers from raw evidence and compare with task-145 card values."""
import hashlib
import json
import math
import re
from pathlib import Path

RUN = Path("D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z")
B2 = RUN / "evidence" / "batch2"
OUT = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/a2/batch2_figures")
OUT.mkdir(parents=True, exist_ok=True)

CASES = ["S6_STD_M2p02_aoa1", "B2-01", "B2-02", "B2-03", "B2-04", "B2-05", "B2-06", "B2-07"]
POLAR_NAME = {
    "S6_STD_M2p02_aoa1": "S6_STD_M2p02_aoa1_model.polar",
}
AOAS = {"S6_STD_M2p02_aoa1": 1.0}
CARD = {
    "S6_STD_M2p02_aoa1": (0.037164, 0.000652722, 0.011813973),
    "B2-01": (0.068720, 0.002408677, 0.009720833),
    "B2-02": (0.070395, 0.002467158, 0.009775138),
    "B2-03": (0.068492, 0.002400696, 0.009704726),
    "B2-04": (0.071942, 0.002521957, 0.010164783),
    "B2-05": (0.067019, 0.002349255, 0.009652284),
    "B2-06": (0.068664, 0.002421414, 0.009725748),
    "B2-07": (0.068492, 0.002399809, 0.009703839),
}
CARD_EXTRA = {
    "density_cdi_3_to_6_pct": 2.43,
    "density_cdi_6_to_12_pct": -2.69,
    "w01_cltot_pct": 5.04,
    "w03_cltot_pct": -2.15,
    "w10_cltot_pct": 0.25,
    "repeat_dcltot": -8.34e-8,
    "repeat_dcdtot": -8.87e-7,
    "starts": 8,
    "retries": 0,
    "class_a_used_before": 6,
    "class_a_used_after": 14,
    "class_a_cap": 20,
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parse_polar(path, aoa):
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    header = None
    hidx = None
    for i, line in enumerate(lines):
        toks = line.split()
        if "Beta" in toks and "Mach" in toks and "AoA" in toks and "CLtot" in toks:
            header = toks
            hidx = i
            break
    if header is None:
        raise RuntimeError("no 48-column header in " + str(path))
    rows = []
    for line in lines[hidx + 1:]:
        t = line.split()
        if len(t) != len(header):
            continue
        try:
            vals = [float(x) for x in t]
        except ValueError:
            continue
        d = dict(zip(header, vals))
        if abs(d.get("AoA", 999.0) - aoa) < 1e-9:
            rows.append(d)
    if not rows:
        raise RuntimeError("no polar row at AoA %s in %s" % (aoa, path))
    return rows[0], header, rows


def recompute_cases():
    out = {}
    for cid in CASES:
        aoa = AOAS.get(cid, 2.0)
        name = POLAR_NAME.get(cid, "wing355_baseline.polar")
        p = B2 / "cases" / cid / "bundle" / name
        row, header, rows = parse_polar(p, aoa)
        ana = B2 / "cases" / cid / "results" / "analysis.json"
        ana_d = json.load(open(ana, encoding="utf-8"))
        out[cid] = {
            "polar_path": str(p),
            "polar_sha256": sha(p),
            "polar_bytes": p.stat().st_size,
            "polar_header_columns": len(header),
            "polar_rows": len(rows),
            "AoA": row["AoA"],
            "CLtot": row["CLtot"],
            "CDi": row["CDi"],
            "CDtot": row["CDtot"],
            "CLo": row["CLo"],
            "CDo": row["CDo"],
            "analysis_primary_values": ana_d.get("primary_values"),
            "analysis_outcome_class": ana_d.get("outcome_class"),
            "analysis_event_id": ana_d.get("event_id"),
        }
    return out


def recompute_accounting(cases):
    led = [json.loads(x) for x in (B2 / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    comp = [r for r in led if r.get("record_type") == "COMPLETED"]
    pend = [r for r in led if r.get("record_type") == "PENDING"]
    budget = json.load(open(B2 / "budget_ledger.json", encoding="utf-8"))
    state = json.load(open(B2 / "batch_state.json", encoding="utf-8"))
    a = budget["counters"]
    return {
        "ledger_rows": len(led),
        "pending_rows": len(pend),
        "completed_rows": len(comp),
        "event_ids": sorted({r.get("event_id") for r in led}),
        "starts": state.get("starts_used"),
        "retries": state.get("retries_used"),
        "all_billable": all(bool(r.get("billable")) for r in comp),
        "class_a_used_before": a.get("class_A_used_before"),
        "class_a_used_after": a.get("class_A_used_total_after"),
        "class_a_cap": a.get("class_A_cap"),
        "class_a_remaining_after": a.get("class_A_remaining_after"),
        "billable_events": a.get("billable_events"),
        "wall_total": round(sum((c.get("wall_seconds") or 0) for c in cases.values()), 6),
        "outcome_classes": sorted({c["analysis_outcome_class"] for c in cases.values()}),
    }


def pct(a, b):
    return (b - a) / a * 100.0


def recompute_deltas(cases):
    b = cases["B2-03"]
    d = {}
    for cid in ["B2-04", "B2-05", "B2-06", "B2-07"]:
        c = cases[cid]
        d[cid] = {k: c[k] - b[k] for k in ("CLtot", "CDi", "CDtot")}
        d[cid].update({k + "_pct": pct(b[k], c[k]) for k in ("CLtot", "CDi", "CDtot")})
    d["density_3_to_6"] = {"CDi_pct": pct(cases["B2-01"]["CDi"], cases["B2-02"]["CDi"]),
                            "CDtot_pct": pct(cases["B2-01"]["CDtot"], cases["B2-02"]["CDtot"]),
                            "CLtot_pct": pct(cases["B2-01"]["CLtot"], cases["B2-02"]["CLtot"])}
    d["density_6_to_12"] = {"CDi_pct": pct(cases["B2-02"]["CDi"], cases["B2-03"]["CDi"]),
                             "CDtot_pct": pct(cases["B2-02"]["CDtot"], cases["B2-03"]["CDtot"]),
                             "CLtot_pct": pct(cases["B2-02"]["CLtot"], cases["B2-03"]["CLtot"])}
    return d


def compare(cases, acc, deltas):
    mism = []
    rows = []
    for cid in CASES:
        c = cases[cid]
        for i, key in enumerate(("CLtot", "CDi", "CDtot")):
            card = CARD[cid][i]
            got = c[key]
            diff = got - card
            ok = abs(diff) <= 1e-6
            rows.append({"id": "%s.%s" % (cid, key), "card": card, "recomputed": got, "diff": diff, "ok": ok})
            if not ok:
                mism.append(rows[-1])
    checks = [
        ("density_cdi_3_to_6_pct", CARD_EXTRA["density_cdi_3_to_6_pct"], deltas["density_3_to_6"]["CDi_pct"], 0.01),
        ("density_cdi_6_to_12_pct", CARD_EXTRA["density_cdi_6_to_12_pct"], deltas["density_6_to_12"]["CDi_pct"], 0.01),
        ("w01_cltot_pct", CARD_EXTRA["w01_cltot_pct"], deltas["B2-04"]["CLtot_pct"], 0.01),
        ("w03_cltot_pct", CARD_EXTRA["w03_cltot_pct"], deltas["B2-05"]["CLtot_pct"], 0.01),
        ("w10_cltot_pct", CARD_EXTRA["w10_cltot_pct"], deltas["B2-06"]["CLtot_pct"], 0.01),
        ("repeat_dcltot", CARD_EXTRA["repeat_dcltot"], deltas["B2-07"]["CLtot"], 1e-9),
        ("repeat_dcdtot", CARD_EXTRA["repeat_dcdtot"], deltas["B2-07"]["CDtot"], 1e-9),
        ("starts", CARD_EXTRA["starts"], acc["starts"], 0),
        ("retries", CARD_EXTRA["retries"], acc["retries"], 0),
        ("class_a_used_before", CARD_EXTRA["class_a_used_before"], acc["class_a_used_before"], 0),
        ("class_a_used_after", CARD_EXTRA["class_a_used_after"], acc["class_a_used_after"], 0),
        ("class_a_cap", CARD_EXTRA["class_a_cap"], acc["class_a_cap"], 0),
    ]
    for name, card, got, tol in checks:
        ok = abs(got - card) <= tol
        rows.append({"id": name, "card": card, "recomputed": got, "diff": got - card, "ok": ok})
        if not ok:
            mism.append(rows[-1])
    # analysis.json cross-check
    for cid in CASES:
        pv = cases[cid]["analysis_primary_values"] or {}
        for k in ("CLtot", "CDi", "CDtot"):
            d = pv.get(k, 0.0) - cases[cid][k]
            ok = abs(d) <= 1e-12
            rows.append({"id": "analysis_crosscheck.%s.%s" % (cid, k), "card": pv.get(k), "recomputed": cases[cid][k], "diff": d, "ok": ok})
            if not ok:
                mism.append(rows[-1])
    return rows, mism


def main():
    cases = recompute_cases()
    acc = recompute_accounting(cases)
    deltas = recompute_deltas(cases)
    rows, mism = compare(cases, acc, deltas)
    result = {
        "schema_version": "d12d005-batch2-recompute-1",
        "generated_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_root": str(B2),
        "card_source": "task-145 description (Lead)",
        "cases": cases,
        "accounting": acc,
        "deltas": deltas,
        "comparisons": rows,
        "n_comparisons": len(rows),
        "n_mismatch": len(mism),
        "mismatches": mism,
        "all_consistent": len(mism) == 0,
    }
    (OUT / "recompute.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    lines = ["# Batch2 数值复算（对照 task-145 卡值）", "", "生成：%s" % result["generated_utc"], "",
             "证据根：%s" % B2, "", "复算方式：直接解析每案 bundle 内 VSPAERO 7.2.2 48 列 polar 文件（AoA 单点行），"
             "预算/重试从 ledger.jsonl（16 行）与 budget_ledger.json 复算；所有百分比与 delta 由复算值计算。", "",
             "总比较项：%d；不一致：%d。" % (result["n_comparisons"], result["n_mismatch"]), ""]
    if mism:
        lines += ["## 不一致项", "", "| id | 卡值 | 复算值 | 差 |", "| --- | --- | --- | --- |"]
        for m in mism:
            lines.append("| %s | %r | %r | %r |" % (m["id"], m["card"], m["recomputed"], m["diff"]))
        lines += ["", "注意：以上不一致仅报告，未改写任何原始证据。"]
    else:
        lines += ["全部 %d 项比较在容差内一致（6 位小数卡值容差 1e-6；百分比容差 0.01 pp；重复性 delta 容差 1e-9；预算计数精确相等）。" % result["n_comparisons"]]
    lines += ["", "## 8 案复算值", "", "| case | CLtot | CDi | CDtot | AoA | polar sha256 |", "| --- | --- | --- | --- | --- | --- |"]
    for cid in CASES:
        c = cases[cid]
        lines.append("| %s | %.9f | %.9f | %.9f | %.1f | %s… |" % (cid, c["CLtot"], c["CDi"], c["CDtot"], c["AoA"], c["polar_sha256"][:16]))
    lines += ["", "## 预算与账本复算", "", "- starts=%d，retries=%d，billable=%d，ledger=%d 行（PENDING %d + COMPLETED %d）" % (
        acc["starts"], acc["retries"], acc["billable_events"], acc["ledger_rows"], acc["pending_rows"], acc["completed_rows"]),
        "- A 类 %d→%d/%d，剩余 %d" % (acc["class_a_used_before"], acc["class_a_used_after"], acc["class_a_cap"], acc["class_a_remaining_after"]),
        "- 结果分类：%s" % ", ".join(acc["outcome_classes"]), ""]
    (OUT / "recompute.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"n_comparisons": len(rows), "n_mismatch": len(mism), "mismatches": mism, "all_consistent": len(mism) == 0}, ensure_ascii=False, indent=1))
    print(json.dumps({"starts": acc["starts"], "retries": acc["retries"], "class_a": [acc["class_a_used_before"], acc["class_a_used_after"], acc["class_a_cap"]], "wall_total": acc["wall_total"], "ledger_rows": acc["ledger_rows"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
