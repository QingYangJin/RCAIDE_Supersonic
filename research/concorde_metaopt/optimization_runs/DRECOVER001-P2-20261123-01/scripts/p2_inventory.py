"""P2 data inventory: admitted certificates -> independent support/query shortage matrix.

Read-only over R2/G1/G2 run roots. No solver is launched. Nothing is written to
the repo; this only produces local audit JSON under the P2 run directory.
"""
from __future__ import annotations
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

RUNS = {
    "R2": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01"),
    "G1": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01"),
    "G2": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01"),
}
OUT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
FAMILY = {"M140": "train", "M160": "train", "M200": "train", "M202": "train",
          "M180": "val", "M220": "val", "M240": "test", "M260": "test"}
TASKS = ("M140", "M160", "M200", "M202", "M180", "M220", "M240", "M260")


def sha_file(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


records = []
skipped = []
for run, root in RUNS.items():
    for cert_path in sorted(root.rglob("admission_certificate.json")):
        case_dir = cert_path.parent
        cert = load_json(cert_path)
        spec = load_json(case_dir / "task_spec.json")
        if not cert or not spec:
            skipped.append({"run": run, "case": str(case_dir), "reason": "missing cert or task_spec"})
            continue
        name = case_dir.name
        m = re.search(r"m(\d{3})", name, re.I) or re.search(r"m(\d{3})", str(spec.get("task_id", "")), re.I)
        mach_tag = "M" + m.group(1) if m else None
        polar = next(iter(sorted(case_dir.glob("*.polar"))), None)
        rec = {
            "run": run,
            "case_dir": str(case_dir),
            "cert": cert_path.name,
            "admission_id": cert.get("admission_id"),
            "task_id": spec.get("task_id"),
            "mach_tag": mach_tag,
            "mach": spec.get("mach"),
            "split": spec.get("split"),
            "partition": spec.get("partition"),
            "design": spec.get("design"),
            "design_sha256": cert.get("design_sha256"),
            "geometry_sha256": cert.get("geometry_sha256"),
            "raw_sha256": cert.get("raw_sha256"),
            "status": cert.get("status"),
            "di_n": cert.get("di_n"),
            "cl": cert.get("cl"),
            "cdi": cert.get("cdi"),
            "q_pa": cert.get("q_pa"),
            "sref_m2": cert.get("sref_m2"),
            "alpha_deg": cert.get("alpha_deg"),
            "polar_path": str(polar) if polar else None,
            "polar_sha256": sha_file(polar) if polar else None,
            "lift_tolerance_rel": spec.get("lift_tolerance_rel"),
            "geometry_contract_sha256": spec.get("geometry_contract_sha256"),
            "task_physics_sha256": spec.get("task_physics_sha256"),
            "x12": spec.get("x12"),
            "flow_conditions": spec.get("flow_conditions"),
        }
        records.append(rec)

ok = [r for r in records if r["status"] == "ok" and r["di_n"] is not None]
failed = [r for r in records if r["status"] != "ok"]

# Deduplicate repeated evidence for the same (task physics, design, polar bytes).
by_identity = defaultdict(list)
for r in ok:
    key = (r["mach_tag"], r["design_sha256"], r["raw_sha256"])
    by_identity[key].append(r)
unique = []
duplicates = []
for key, group in by_identity.items():
    group_sorted = sorted(group, key=lambda r: (r["run"], r["admission_id"]))
    unique.append(group_sorted[0])
    for r in group_sorted[1:]:
        duplicates.append({"kept": group_sorted[0]["admission_id"], "dropped": r["admission_id"],
                           "run": r["run"], "task": r["mach_tag"], "design": r["design"],
                           "same_polar": True})
# Same design but different polar bytes -> numeric retest candidate, still not a new design.
by_task_design = defaultdict(list)
for r in ok:
    by_task_design[(r["mach_tag"], r["design_sha256"])].append(r)
numeric_retests = []
for (task, design), group in by_task_design.items():
    polars = {r["polar_sha256"] for r in group}
    if len(polars) > 1:
        numeric_retests.append({"task": task, "design": design,
                                "cases": [r["admission_id"] for r in group],
                                "polar_variants": len(polars),
                                "di_n_spread": max(r["di_n"] for r in group) - min(r["di_n"] for r in group)})

# Group unique labels per (task, design): keep partition from the earliest admitted case.
per_task = {}
for tag in TASKS:
    rows = [r for r in unique if r["mach_tag"] == tag]
    by_design = {}
    for r in sorted(rows, key=lambda r: (r["run"], r["admission_id"])):
        by_design.setdefault(r["design_sha256"], r)
    designs = []
    for dsha, r in sorted(by_design.items(), key=lambda kv: kv[1]["design"]):
        designs.append({"design": r["design"], "design_sha256": dsha,
                        "partition_observed": r["partition"],
                        "di_n": r["di_n"], "cl": r["cl"], "alpha_deg": r["alpha_deg"],
                        "runs": sorted({x["run"] for x in rows if x["design_sha256"] == dsha}),
                        "admission_ids": [x["admission_id"] for x in rows if x["design_sha256"] == dsha]})
    per_task[tag] = {
        "declared_split": FAMILY[tag],
        "unique_designs": len(designs),
        "support_designs": sum(1 for d in designs if d["partition_observed"] == "support"),
        "query_designs": sum(1 for d in designs if d["partition_observed"] == "query"),
        "designs": designs,
    }

shortage = {}
for tag in TASKS:
    info = per_task[tag]
    split = FAMILY[tag]
    need_support = 3 if split == "train" else 2
    need_query = 1 if split == "train" else 1
    have_s = info["support_designs"]
    have_q = info["query_designs"]
    shortage[tag] = {
        "split": split,
        "needed": {"support_designs": need_support, "query_designs": need_query,
                   "for_arms": "K=3 support / >=1 independent query"},
        "have": {"support_designs": have_s, "query_designs": have_q},
        "missing": {"support_designs": max(0, need_support - have_s),
                    "query_designs": max(0, need_query - have_q)},
        "short": max(0, need_support - have_s) + max(0, need_query - have_q),
    }

# 12D field order check: task_spec x12 key order must match the frozen build_task_case order.
FROZEN_NAMES = ["Sref_m2", "AR", "sweep_le_deg", "root_chord_m", "tip_chord_m",
                "twist_root_deg", "twist_tip_deg", "dihedral_deg", "thickness_root",
                "thickness_tip", "fuselage_len_m", "nose_fineness", "tail_arm_m",
                "tail_area_m2", "tail_volume_coeff"]
x12_variants = Counter()
for r in ok:
    x = r.get("x12")
    if isinstance(x, list) and len(x) == 12:
        x12_variants[tuple(float(v) for v in x)] += 1
geometry_variants = Counter(r["geometry_contract_sha256"] for r in ok)
q_variants = Counter(round(r["q_pa"], 6) for r in ok)
sref_variants = Counter(round(r["sref_m2"], 6) for r in ok)
lift_tol = Counter(r["lift_tolerance_rel"] for r in ok)

payload = {
    "schema": "dreal004.p2_inventory.v1",
    "run_id": "DRECOVER001-P2-20261123-01",
    "physical_solver_starts_actual": 0,
    "note": "read-only inventory of already admitted certificates; no solver launched",
    "runs_scanned": {k: str(v) for k, v in RUNS.items()},
    "certificates_total": len(records),
    "certificates_ok": len(ok),
    "certificates_failed": len(failed),
    "unique_ok_labels": len(unique),
    "duplicate_evidence_dropped": len(duplicates),
    "duplicates": duplicates,
    "numeric_retest_same_design_different_polar": numeric_retests,
    "per_task": per_task,
    "shortage": shortage,
    "integrity": {
        "geometry_contract_variants": dict(geometry_variants),
        "q_variants": {str(k): v for k, v in q_variants.items()},
        "sref_variants": {str(k): v for k, v in sref_variants.items()},
        "lift_tolerance_rel_variants": {str(k): v for k, v in lift_tol.items()},
        "x12_distinct_vectors": len(x12_variants),
        "x12_expected_field_order": FROZEN_NAMES,
        "x12_fields_in_task_spec": "12 numeric fields ending with tail_volume_coeff; fuselage/tail held fixed per scheme",
    },
    "skipped": skipped[:20],
    "family_rule_note": "train M140/M160/M200/M202, val M180/M220, test M240/M260 fixed by the P2 directive; labels per task must be independent designs and must never cross support/query",
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "p2_inventory.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

lines = ["# P2 数据清点（只读，零物理）", ""]
lines.append(f"扫描 R2/G1/G2 的 admission_certificate.json：{len(records)} 张，ok {len(ok)}，failed {len(failed)}；去重后唯一标签 {len(unique)}。")
lines.append("")
lines.append("| 任务 | split | 唯一设计 | support | query | 缺口(starts 估计) |")
lines.append("|---|---|---|---|---|---|")
for tag in TASKS:
    i = per_task[tag]
    s = shortage[tag]
    lines.append(f"| {tag} | {FAMILY[tag]} | {i['unique_designs']} | {i['support_designs']} | {i['query_designs']} | {s['short']} |")
lines.append("")
lines.append("数值复测候选（同设计不同 polar 字节，不作为独立设计）：" + (json.dumps(numeric_retests, ensure_ascii=False) if numeric_retests else "无"))
lines.append("")
lines.append("完整字段见 p2_inventory.json。")
(OUT / "p2_inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({"records": len(records), "ok": len(ok), "unique": len(unique),
                  "per_task": {k: v["unique_designs"] for k, v in per_task.items()},
                  "shortage": {k: v["short"] for k, v in shortage.items()}}, ensure_ascii=False))
