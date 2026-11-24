"""Rebuild the frozen real label dataset for the D-REAL-EXP-003 A0 ablation.

Zero physical: every historical case is re-admitted through admit_real_manifest()
against its local raw bytes, so the dataset is a byte-level replay of the audited
raw files (not a trust-the-old-certificate shortcut). No solver is started.

Run split is the frozen P2 split (train M140/M160/M200/M202, val M180/M220,
test M240/M260); Issue #15 forbids reshaping the split based on arm performance.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))

from research.concorde_metaopt.dreal001.meta import real_admission as ra  # noqa: E402
from research.concorde_metaopt.dreal001.meta.meta_dataset import MetaDataset  # noqa: E402
from research.concorde_metaopt.dreal001.meta.task_spec import (  # noqa: E402
    TaskSpec,
)

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01")
CASE_ROOTS = (
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01/cases"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/cases"),
    Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01/cases"),
)
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
SCHEMA = "dreal005.a0_dataset.v1"


def tag_for(mach: float) -> str:
    return "M%d" % int(round(mach * 100))


def _case_dirs():
    for root in CASE_ROOTS:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "admission_manifest.json").is_file():
                yield child


def load_manifests():
    records, seen = [], set()
    for case_dir in _case_dirs():
        payload = json.loads((case_dir / "admission_manifest.json").read_text(encoding="utf-8"))
        key = payload["admission_id"]
        if key in seen:
            continue
        seen.add(key)
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


def build_family_and_dataset(*, verbose: bool = False):
    records = load_manifests()
    tasks, certs, excluded = {}, [], []
    candidates = []
    for payload in records:
        mach = float(payload["task"]["mach"])
        tag = tag_for(mach)
        if tag not in CANONICAL:
            excluded.append({"admission_id": payload["admission_id"],
                             "reason": "mach outside the frozen task set", "mach": mach})
            continue
        group = next((p for p in PRIORITY if payload["run_id"].startswith(p)), None)
        candidates.append((PRIORITY.get(group, 0), payload, tag))
    candidates.sort(key=lambda item: (-item[0], item[2], item[1]["admission_id"]))

    chosen, conflicts = {}, {}
    for priority, payload, tag in candidates:
        canonical_id, _ = CANONICAL[tag]
        key = (canonical_id, payload["design_id"])
        prior = chosen.get(key)
        if prior is None:
            chosen[key] = {"payload": payload, "tag": tag, "priority": priority,
                           "partitions": {payload["partition"]}}
            continue
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
        elif priority < prior["priority"]:
            excluded.append({"admission_id": payload["admission_id"],
                             "reason": "lower-priority batch contradicts the higher-priority partition",
                             "kept": prior["payload"]["admission_id"]})
        else:
            conflicts[key[0]] = conflicts.get(key[0], 0) + 1
            excluded.append({"admission_id": payload["admission_id"],
                             "reason": "design appears in both support and query at equal priority"})
            excluded.append({"admission_id": prior["payload"]["admission_id"],
                             "reason": "design appears in both support and query at equal priority"})
            chosen.pop(key)

    for key in sorted(chosen):
        entry = chosen[key]
        payload = entry["payload"]
        if len(entry["partitions"]) > 1:
            continue
        canonical_id, split = CANONICAL[entry["tag"]]
        tp = payload["task"]
        spec = TaskSpec(canonical_id, split, float(tp["mach"]), float(tp["altitude_m"]),
                        float(tp["dynamic_pressure_pa"]), float(tp["lift_target_n"]),
                        tp["geometry_contract_sha256"], float(tp["lift_tolerance_rel"]))
        tasks.setdefault(canonical_id, spec)
        if tasks[canonical_id].physics_sha256 != spec.physics_sha256:
            raise SystemExit("inconsistent physics for canonical task " + canonical_id)
        historical = TaskSpec(payload["task_id"], split, spec.mach, spec.altitude_m,
                              spec.dynamic_pressure_pa, spec.lift_target_n,
                              spec.geometry_contract_sha256, spec.lift_tolerance_rel)
        if historical.physics_sha256 != spec.physics_sha256:
            raise SystemExit("alias changes physics for " + payload["task_id"])
        manifest = _manifest_object(payload)
        cert = ra.admit_real_manifest(
            manifest=manifest, raw_root=entry["payload"]["_case_dir"], task=historical,
            design=manifest.design, expected_evaluator_id=manifest.evaluator_id,
            expected_audit_ref=manifest.independent_audit_ref)
        certs.append((cert, entry))

    aliases = {}
    for payload in records:
        tag = tag_for(float(payload["task"]["mach"]))
        if tag in CANONICAL:
            aliases.setdefault(CANONICAL[tag][0], set()).add(payload["task_id"])
    alias_map = {canonical: sorted(names) for canonical, names in aliases.items()}
    family = tuple(tasks[key] for key in sorted(tasks))
    dataset = MetaDataset.from_admitted_certificates(
        family, tuple(cert for cert, _ in certs), task_aliases=alias_map)
    if verbose:
        print("family", [t.task_id for t in family])
        print("rows", len(dataset.rows), "certs", len(dataset.admissions))
    return {"family": family, "dataset": dataset, "aliases": alias_map,
            "records": records, "excluded": excluded, "partition_conflicts": conflicts,
            "source_map": {cert.admission_id: {
                "case_dir": entry["payload"]["_case_dir"],
                "run_id": entry["payload"]["run_id"],
                "historical_task_id": cert.task_id}
                for cert, entry in certs}}


def summary(built) -> dict:
    dataset = built["dataset"]
    tasks = []
    for task in built["family"]:
        support = dataset.usable(task.task_id, "support")
        query = dataset.usable(task.task_id, "query")
        tasks.append({
            "task_id": task.task_id, "split": task.split, "mach": task.mach,
            "altitude_m": task.altitude_m,
            "dynamic_pressure_pa": task.dynamic_pressure_pa,
            "lift_target_n": task.lift_target_n,
            "physics_sha256": task.physics_sha256,
            "support": len(support), "query": len(query),
            "k3_support_ok": len(support) >= 3,
            "k5_support_ok": len(support) >= 5,
            "support_designs": sorted({r.design_sha256 for r in support}),
            "query_designs": sorted({r.design_sha256 for r in query}),
        })
    return {"schema": SCHEMA,
            "generated_by": "a0_data.py (zero physical; replayed admit_real_manifest)",
            "family": [t.task_id for t in built["family"]],
            "task_aliases": built["aliases"],
            "rows": len(dataset.rows),
            "certificates": len(dataset.admissions),
            "tasks": tasks,
            "excluded": built["excluded"],
            "partition_conflicts": built["partition_conflicts"],
            "sources": built["source_map"],
            "physical_solver_starts_actual": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(RUN / "dataset"))
    args = parser.parse_args()
    built = build_family_and_dataset(verbose=True)
    payload = summary(built)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "a0_dataset.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("rows", "certificates")}, ensure_ascii=False))
    print("wrote", out / "a0_dataset.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
