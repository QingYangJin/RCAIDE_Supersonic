# -*- coding: utf-8 -*-
"""V1L labels: relabel the frozen A0 task/design grid with the RCAIDE supersonic VLM.

What is reused from A0 (unchanged, so the comparison is like-for-like):
  - the eight canonical tasks (mach, altitude, dynamic pressure, lift target);
  - the seven admitted designs and their support/query partition membership;
  - the frozen split: train M140/M160/M200/M202, val M180/M220, test M240/M260.

What is new here: every label (Di_N) is recomputed by SupersonicVLMBackend at
lattice (20, 10) with alpha solved to CL_target. No VSPAERO label is reused and
no solver is started. source_kind becomes "rcaide_vlm_20x10" so the dataset
cannot be mistaken for admitted raw bytes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "research/concorde_metaopt/optimization_runs/DRECOVER001-A0-20261124-01/scripts"))

import a0_data  # noqa: E402
from research.concorde_metaopt.dreal001.meta.meta_dataset import (  # noqa: E402
    MetaDataset, Observation)
from research.concorde_metaopt.evaluation.rcaide_vlm_backend import (  # noqa: E402
    SupersonicVLMBackend)

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01")
CFG = REPO / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
LATTICE = (20, 10)
SREF = 358.25
SOURCE_KIND = "rcaide_vlm_20x10"


def label_rows(verbose: bool = True):
    built = a0_data.build_family_and_dataset()
    source = built["dataset"]
    names = SupersonicVLMBackend(REPO, str(CFG), lattice=LATTICE).design_names
    baselines = {}
    cache = {}
    for task in source.tasks:
        cl_target = task.lift_target_n / (task.dynamic_pressure_pa * SREF)
        backend = SupersonicVLMBackend(REPO, str(CFG), mach=task.mach,
                                       altitude_m=task.altitude_m,
                                       cl_target=cl_target, lattice=LATTICE,
                                       design_names=names)
        for row in source.rows:
            if row.task_id != task.task_id:
                continue
            design = dict(zip(names, row.design))
            rec = backend.evaluate(design, purpose="v1l-label")
            key = (task.task_id, row.design_sha256)
            if rec["status"] != "VALID":
                raise SystemExit("VLM eval failed for %s %s: %s" % (key[0], key[1], rec["status"]))
            cache[key] = {"task_id": task.task_id, "design": list(row.design),
                          "partition": row.partition, "status": row.status,
                          "observation_id": row.observation_id,
                          "cdi": rec["objective"], "cl": rec["cl_actual"],
                          "alpha_deg": rec["alpha_deg"], "design_key": rec["design_key"],
                          "wall_seconds": rec["wall_seconds"],
                          "di_n": rec["objective"] * task.dynamic_pressure_pa * SREF}
        baselines[task.task_id] = {"mach": task.mach, "cl_target": cl_target,
                                   "q_pa": task.dynamic_pressure_pa,
                                   "provenance": backend.provenance()}
        if verbose:
            n = sum(1 for k in cache if k[0] == task.task_id)
            print("labelled %-16s M=%.2f rows=%d" % (task.task_id, task.mach, n), flush=True)

    # determinism gate: relabel three rows with a fresh backend and require bitwise match
    checks = []
    for task in source.tasks[:3]:
        cl_target = task.lift_target_n / (task.dynamic_pressure_pa * SREF)
        backend = SupersonicVLMBackend(REPO, str(CFG), mach=task.mach,
                                       altitude_m=task.altitude_m,
                                       cl_target=cl_target, lattice=LATTICE,
                                       design_names=names)
        row = next(r for r in source.rows if r.task_id == task.task_id)
        rec = backend.evaluate(dict(zip(names, row.design)), purpose="v1l-label-recheck")
        stored = cache[(task.task_id, row.design_sha256)]["cdi"]
        checks.append({"task_id": task.task_id, "stored_cdi": stored,
                       "recheck_cdi": rec["objective"],
                       "identical": bool(stored == rec["objective"])})
        if not checks[-1]["identical"]:
            raise SystemExit("non-deterministic VLM label for " + task.task_id)

    rows = []
    for task in source.tasks:
        for row in source.rows:
            if row.task_id != task.task_id:
                continue
            item = cache[(task.task_id, row.design_sha256)]
            rows.append(Observation(
                observation_id="V1L-" + item["design_key"] + "-" + task.task_id.replace("P2-CANON-", ""),
                task_id=task.task_id, design=tuple(row.design), partition=row.partition,
                source_kind=SOURCE_KIND, status=item["status"],
                di_n=float(item["di_n"]), q_pa=task.dynamic_pressure_pa, sref_m2=SREF,
                cdi=float(item["cdi"]), cl=float(item["cl"]),
                raw_sha256=item["design_key"], source_task_id=None))
    dataset = MetaDataset(tuple(source.tasks), tuple(rows), task_aliases=built["aliases"])
    return {"dataset": dataset, "source": source, "labels": cache,
            "baselines": baselines, "determinism_checks": checks,
            "aliases": built["aliases"], "design_names": list(names)}


def require_vlm_labels(dataset: MetaDataset) -> None:
    """Fail closed unless every row is a finite VLM label of the declared lattice."""
    if dataset.admissions:
        raise ContractError("VLM dataset must not carry VSPAERO admission certificates")
    for row in dataset.rows:
        if row.source_kind != SOURCE_KIND:
            raise ContractError("row %s is not a VLM label" % row.observation_id)
        if row.status != "ok" or row.di_n is None or not np.isfinite(row.di_n) or row.di_n <= 0.0:
            raise ContractError("row %s has no finite positive label" % row.observation_id)
        if row.cdi is None or not np.isfinite(row.cdi) or row.cdi <= 0.0:
            raise ContractError("row %s has no finite positive CDi" % row.observation_id)


from research.concorde_metaopt.dreal001.meta.task_spec import ContractError  # noqa: E402


def main() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    out = label_rows()
    ds = out["dataset"]
    require_vlm_labels(ds)
    payload = {"schema": "dreal005.v1l_labels.v1", "lattice": list(LATTICE),
               "source_kind": SOURCE_KIND, "sref_m2": SREF,
               "row_count": len(ds.rows),
               "labels": {("%s|%s" % k): v for k, v in out["labels"].items()},
               "task_baselines": out["baselines"],
               "determinism_checks": out["determinism_checks"],
               "note": ("Labels recomputed with RCAIDE supersonic VLM at 20x10; "
                        "CL matched per task; objective is Trefftz induced drag only "
                        "(wave drag excluded). No VSPAERO label is reused.")}
    (RUN / "v1l_labels.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("rows", len(ds.rows), "determinism", all(c["identical"] for c in out["determinism_checks"]))
    for row in ds.rows[:5]:
        print("  %-22s %s di=%.3f cdi=%.9f" % (row.task_id, row.partition, row.di_n, row.cdi))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def load_labels_payload() -> dict:
    return json.loads((RUN / "v1l_labels.json").read_text(encoding="utf-8"))


def build_family_and_dataset(verbose: bool = False):
    """Rebuild the VLM-labelled dataset from v1l_labels.json (no re-evaluation).

    Shares the function name/shape of a0_data.build_family_and_dataset so the
    frozen A0 driver can run against it unchanged, but no VSPAERO label is read:
    only the task family, the design membership and the frozen split are reused.
    """
    built = a0_data.build_family_and_dataset()
    source = built["dataset"]
    payload = load_labels_payload()
    labels = payload["labels"]
    rows = []
    for row in source.rows:
        key = "%s|%s" % (row.task_id, row.design_sha256)
        if key not in labels:
            raise SystemExit("missing VLM label for " + key)
        item = labels[key]
        rows.append(Observation(
            observation_id="V1L-" + item["design_key"] + "-" + row.task_id.replace("P2-CANON-", ""),
            task_id=row.task_id, design=tuple(item["design"]), partition=row.partition,
            source_kind=SOURCE_KIND, status="ok", di_n=float(item["di_n"]),
            q_pa=float(item["q_pa"] if "q_pa" in item else
                       next(t.dynamic_pressure_pa for t in source.tasks
                            if t.task_id == row.task_id)),
            sref_m2=SREF, cdi=float(item["cdi"]), cl=float(item["cl"]),
            raw_sha256=item["design_key"], source_task_id=None))
    dataset = MetaDataset(tuple(source.tasks), tuple(rows),
                          task_aliases=built["aliases"])
    require_vlm_labels(dataset)
    if verbose:
        print("family", [t.task_id for t in dataset.tasks])
        print("rows", len(dataset.rows), "vlm labels only")
    return {"family": tuple(source.tasks), "dataset": dataset,
            "aliases": built["aliases"], "labels_payload": payload,
            "source_rows": source,
            # provenance fields the frozen A0 driver reports; the VLM line has no
            # VSPAERO admissions to exclude, and the split is the frozen one.
            "excluded": [], "partition_conflicts": {}, "records": [],
            "source_map": {}}

