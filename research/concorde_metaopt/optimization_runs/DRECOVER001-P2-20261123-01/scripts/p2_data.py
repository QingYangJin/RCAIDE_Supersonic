"""Rebuild the P2 real dataset from existing admitted cases (zero physical).

Every case is re-admitted through admit_real_manifest() against the local raw
bytes, so this is a byte-level replay, not a trust-the-old-certificate shortcut.
No solver is started and no historical file is modified.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
sys.path.insert(0, str(REPO))

from research.concorde_metaopt.dreal001.meta import real_admission as ra
from research.concorde_metaopt.dreal001.meta.meta_dataset import MetaDataset
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec, canonical_sha

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
CASE_ROOTS = (
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01/cases"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/cases"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/cases"),
)
# Frozen P2 split (Issue #14 P2 directive: train M140/M160/M200/M202, val M180/M220,
# test M240/M260; the task set may never be reshuffled based on arm performance).
CANONICAL = {
    "M140": ("P2-CANON-M140", "train"),
    "M160": ("P2-CANON-M160", "train"),
    "M200": ("P2-CANON-M200", "train"),
    "M202": ("P2-CANON-M202", "train"),
    "M180": ("P2-CANON-M180", "val"),
    "M220": ("P2-CANON-M220", "val"),
    "M240": ("P2-CANON-M240", "test"),
    "M260": ("P2-CANON-M260", "test"),
}
PRIORITY = {"DRECOVER001-P2": 4, "DRECOVER001-G2": 3,
            "DRECOVER001-G1": 2, "DRECOVER001-R2": 1}


def tag_for(mach: float) -> str:
    return "M%d" % int(round(mach * 100))


def _case_dirs():
    for root in CASE_ROOTS:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            manifest = child / "admission_manifest.json"
            if child.is_dir() and manifest.is_file():
                yield child


def load_manifests() -> list[dict]:
    records, seen = [], {}
    for case_dir in _case_dirs():
        payload = json.loads((case_dir / "admission_manifest.json").read_text(encoding="utf-8"))
        key = payload["admission_id"]
        if key in seen:
            continue
        seen[key] = payload
        payload["_case_dir"] = str(case_dir)
        records.append(payload)
    return records


def _manifest_object(payload: dict):
    files = tuple(ra.RawFile(item["kind"], item["path"], item["sha256"], int(item["bytes"]))
                  for item in payload["files"])
    binding = ra.ArtifactBinding(**payload["binding"])
    return ra.RealAdmissionManifest(
        admission_id=payload["admission_id"], run_id=payload["run_id"],
        task_id=payload["task_id"], design_id=payload["design_id"],
        design=tuple(payload["design"]), geometry_sha256=payload["geometry_sha256"],
        evaluator_id=payload["evaluator_id"],
        solver_returncode=int(payload["solver_returncode"]),
        solver_started_utc=payload["solver_started_utc"], outcome=payload["outcome"],
        partition=payload["partition"], files=files, binding=binding,
        independent_audit_ref=payload["independent_audit_ref"])


def build_family_and_dataset(*, verbose=False):
    records = load_manifests()
    tasks, certs, excluded = {}, [], []
    candidates = []
    for payload in records:
        mach = float(payload["task"]["mach"])
        tag = tag_for(mach)
        if tag not in CANONICAL:
            excluded.append({"admission_id": payload["admission_id"],
                             "reason": "mach outside the frozen P2 task set", "mach": mach})
            continue
        run_group = next((prefix for prefix in PRIORITY
                          if payload["run_id"].startswith(prefix)), None)
        candidates.append((PRIORITY.get(run_group, 0), payload, tag))

    # Deterministic preference: newer batch first, then admission_id.
    candidates.sort(key=lambda item: (-item[0], item[2], item[1]["admission_id"]))
    chosen: dict[tuple[str, str], dict] = {}
    partition_conflicts = {}
    for priority, payload, tag in candidates:
        canonical_id, split = CANONICAL[tag]
        design_id = payload["design_id"]
        key = (canonical_id, design_id)
        prior = chosen.get(key)
        if prior is None:
            chosen[key] = {"payload": payload, "tag": tag, "priority": priority,
                           "partitions": {payload["partition"]}}
            continue
        # A newer batch with its own audited partition wins; an equal-priority
        # disagreement is unresolvable and the whole design is dropped.
        if priority > prior["priority"]:
            excluded.append({"admission_id": prior["payload"]["admission_id"],
                             "reason": "superseded by newer batch for the same design",
                             "kept": payload["admission_id"]})
            chosen[key] = {"payload": payload, "tag": tag, "priority": priority,
                           "partitions": {payload["partition"]}}
        elif payload["partition"] in prior["partitions"]:
            excluded.append({"admission_id": payload["admission_id"],
                             "reason": "duplicate design within canonical task",
                             "kept": prior["payload"]["admission_id"]})
        else:
            partition_conflicts[key[0]] = partition_conflicts.get(key[0], 0) + 1
            excluded.append({"admission_id": payload["admission_id"],
                             "reason": "design appears in both support and query at the same priority"})
            excluded.append({"admission_id": prior["payload"]["admission_id"],
                             "reason": "design appears in both support and query at the same priority"})
            chosen.pop(key)
    for key, entry in list(chosen.items()):
        if len(entry["partitions"]) > 1:
            partition_conflicts[key[0]] = partition_conflicts.get(key[0], 0) + 1
            excluded.append({"admission_id": entry["payload"]["admission_id"],
                             "reason": "design appears in both support and query across batches"})
            chosen.pop(key)

    for key in sorted(chosen):
        entry = chosen[key]
        payload = entry["payload"]
        if len(entry["partitions"]) > 1:
            continue
        canonical_id, split = CANONICAL[entry["tag"]]
        task_payload = payload["task"]
        spec = TaskSpec(canonical_id, split, float(task_payload["mach"]),
                        float(task_payload["altitude_m"]),
                        float(task_payload["dynamic_pressure_pa"]),
                        float(task_payload["lift_target_n"]),
                        task_payload["geometry_contract_sha256"],
                        float(task_payload["lift_tolerance_rel"]))
        tasks.setdefault(canonical_id, spec)
        if tasks[canonical_id].physics_sha256 != spec.physics_sha256:
            raise SystemExit("inconsistent physics for canonical task " + canonical_id)
        # The certificate keeps the historical task_id it was audited with; the
        # explicit alias table maps it onto the frozen P2 canonical task.
        historical = TaskSpec(payload["task_id"], split, spec.mach, spec.altitude_m,
                              spec.dynamic_pressure_pa, spec.lift_target_n,
                              spec.geometry_contract_sha256, spec.lift_tolerance_rel)
        if historical.physics_sha256 != spec.physics_sha256:
            raise SystemExit("alias changes physics for " + payload["task_id"])
        manifest = _manifest_object(payload)
        cert = ra.admit_real_manifest(
            manifest=manifest, raw_root=entry["payload"]["_case_dir"], task=historical,
            design=manifest.design,
            expected_evaluator_id=manifest.evaluator_id,
            expected_audit_ref=manifest.independent_audit_ref)
        certs.append((cert, entry))

    aliases = {}
    for payload in records:
        tag = tag_for(float(payload["task"]["mach"]))
        if tag not in CANONICAL:
            continue
        aliases.setdefault(CANONICAL[tag][0], set()).add(payload["task_id"])
    alias_map = {canonical: sorted(names) for canonical, names in aliases.items()}
    family = tuple(tasks[key] for key in sorted(tasks))
    dataset = MetaDataset.from_admitted_certificates(
        family, tuple(cert for cert, _ in certs), task_aliases=alias_map)
    if verbose:
        print("family", [t.task_id for t in family])
        print("rows", len(dataset.rows), "certs", len(dataset.admissions))
    return {
        "family": family, "dataset": dataset, "aliases": alias_map,
        "records": records, "excluded": excluded,
        "partition_conflicts": partition_conflicts,
        "source_map": {cert.admission_id: {"case_dir": entry["payload"]["_case_dir"],
                                           "run_id": entry["payload"]["run_id"],
                                           "historical_task_id": cert.task_id}
                       for cert, entry in certs},
    }


def summary(built) -> dict:
    dataset = built["dataset"]
    tasks = []
    for task in built["family"]:
        support = dataset.usable(task.task_id, "support")
        query = dataset.usable(task.task_id, "query")
        tasks.append({
            "task_id": task.task_id, "split": task.split, "mach": task.mach,
            "dynamic_pressure_pa": task.dynamic_pressure_pa,
            "support": len(support), "query": len(query),
            "k3_support_ok": len(support) >= 3,
            "k3_query_ok": len(query) >= 1,
            "support_designs": sorted({r.design_sha256[:12] for r in support}),
            "query_designs": sorted({r.design_sha256[:12] for r in query}),
        })
    return {
        "schema": "dreal004.p2_dataset.v1",
        "generated_by": "p2_data.py (zero physical; replayed admit_real_manifest)",
        "family": [t.task_id for t in built["family"]],
        "task_aliases": built["aliases"],
        "rows": len(dataset.rows),
        "certificates": len(dataset.admissions),
        "tasks": tasks,
        "excluded": built["excluded"],
        "partition_conflicts": built["partition_conflicts"],
        "sources": built["source_map"],
        "physical_solver_starts_actual": 0,
    }


def _markdown(payload: dict) -> str:
    lines = ["# P2 数据清点与短缺矩阵（零物理重放）", "",
             "生成脚本：p2_data.py；所有行均通过 admit_real_manifest 对本地原始字节重新准入。",
             "物理求解器启动：0。", "",
             "| 任务 | 切分 | Mach | 独立 support | 独立 query | K=3 support |",
             "|---|---|---|---|---|---|"]
    for task in payload["tasks"]:
        lines.append("| %s | %s | %.2f | %d | %d | %s |" % (
            task["task_id"], task["split"], task["mach"], task["support"],
            task["query"], "是" if task["k3_support_ok"] else "否"))
    lines += ["", "任务别名（历史批次 -> 规范任务）：", ""]
    for canonical, names in payload["task_aliases"].items():
        lines.append("- %s: %s" % (canonical, ", ".join(names)))
    if payload["excluded"]:
        lines += ["", "被排除的记录（去重/冲突，均未计为独立样本）：", ""]
        for item in payload["excluded"]:
            lines.append("- %s: %s" % (item["admission_id"], item["reason"]))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(RUN / "p2_dataset"))
    args = parser.parse_args()
    built = build_family_and_dataset(verbose=True)
    payload = summary(built)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "p2_dataset.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "p2_dataset.md").write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("rows", "certificates")}, ensure_ascii=False))
    print("wrote", out / "p2_dataset.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
