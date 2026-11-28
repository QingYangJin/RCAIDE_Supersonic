"""Pre-register the S1 design bank before any physical evaluation.

Task family (24 train + 8 val) x 256 joint designs.  Each task gets four
explicit shared anchors (baseline + three fixed boundary-ish points) plus 252
scrambled Sobol points over the frozen 5D active subspace.  The other seven
schema dimensions stay at their frozen baseline and are recorded once.

Ordering is part of the contract: indices 0..127 are the fit half and 128..255
are the per-task query half.  Both halves are written to the manifest before a
single solve, and the digest of the manifest is reported in the ledger.
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from . import common


def _design_id(active_names: list[str], values: dict[str, float]) -> str:
    payload = common.canonical_json([
        active_names,
        ["%.12g" % float(values[name]) for name in active_names],
    ])
    return common.sha256_text(payload)[:16]


def _full_design(active_names: list[str], active_values: dict[str, float], bounds: dict) -> dict[str, float]:
    design = {}
    for name, spec in bounds.items():
        design[name] = float(active_values[name]) if name in active_values else float(spec["baseline"])
    return design


def build_task_designs(task: dict, active_names: list[str], bounds: dict,
                        n_designs: int | None = None, fit_designs: int | None = None) -> list[dict]:
    import numpy as np
    from scipy.stats.qmc import Sobol

    n_designs = common.DESIGNS_PER_TASK if n_designs is None else int(n_designs)
    fit_designs = common.FIT_DESIGNS if fit_designs is None else int(fit_designs)
    lower = np.array([bounds[name]["lower"] for name in active_names], dtype=float)
    upper = np.array([bounds[name]["upper"] for name in active_names], dtype=float)
    baseline = np.array([bounds[name]["baseline"] for name in active_names], dtype=float)

    anchors = [
        ("anchor-baseline", np.zeros(5)),
        ("anchor-low", np.array([0.10, 0.10, 0.10, 0.10, 0.10])),
        ("anchor-high", np.array([0.90, 0.90, 0.90, 0.90, 0.90])),
        ("anchor-mixed", np.array([0.20, 0.80, 0.20, 0.80, 0.20])),
    ]
    rows = []
    for label, unit in anchors:
        values = lower + unit * (upper - lower)
        rows.append((label, values))
    sampler = Sobol(d=len(active_names), scramble=True,
                    seed=common.task_seed(task["task_id"], purpose="%s-designs-v1" % common.CURRENT_PHASE))
    points = sampler.random(n_designs)  # n_designs including the zero corner
    for index in range(len(rows), n_designs):
        rows.append(("sobol", lower + points[index] * (upper - lower)))

    designs = []
    seen = set()
    for index, (kind, values) in enumerate(rows):
        active = {name: float(values[i]) for i, name in enumerate(active_names)}
        design_id = _design_id(active_names, active)
        if design_id in seen:
            raise RuntimeError("duplicate design %s in %s" % (design_id, task["task_id"]))
        seen.add(design_id)
        designs.append({
            "index": index,
            "kind": kind,
            "design_id": design_id,
            "active": [float(active[name]) for name in active_names],
            "split": "fit" if index < fit_designs else "query",
        })
    if len(designs) != n_designs:
        raise RuntimeError("design count mismatch for %s" % task["task_id"])
    return designs


def build_manifest(splits: tuple[str, ...] | None = None, n_designs: int | None = None,
                   fit_designs: int | None = None) -> dict:
    family = common.load_task_family()
    subspace = common.load_active_subspace()
    bounds = common.load_design_bounds()
    active_names = list(subspace["active_names"])
    phase = common.CURRENT_PHASE
    splits = tuple(common.phase_config(phase)["splits"]) if splits is None else splits
    n_designs = common.DESIGNS_PER_TASK if n_designs is None else int(n_designs)
    fit_designs = common.FIT_DESIGNS if fit_designs is None else int(fit_designs)
    tasks = [t for t in family["tasks"] if t["split"] in splits]
    per_task = {}
    for task in tasks:
        designs = build_task_designs(task, active_names, bounds, n_designs, fit_designs)
        per_task[task["task_id"]] = {
            "task_id": task["task_id"],
            "split": task["split"],
            "mach": float(task["mach"]),
            "altitude_m": float(task["altitude_m"]),
            "dynamic_pressure_pa": float(task["dynamic_pressure_pa"]),
            "lift_target_n": float(task["lift_target_n"]),
            "lift_fraction_of_base": float(task["lift_fraction_of_base"]),
            "physics_sha256": task["physics_sha256"],
            "seed": common.task_seed(task["task_id"], purpose="%s-designs-v1" % phase),
            "designs": designs,
        }
    payload = {
        "schema": "dreal006.%s_design_manifest.v1" % phase,
        "created_utc": common.utc_now(),
        "run_id": common.RUN_ID,
        "task_family_sha256": common.sha256_file(common.TASK_FAMILY_PATH),
        "active_subspace_sha256": common.sha256_file(common.ACTIVE_SUBSPACE_PATH),
        "design_space_sha256": common.sha256_file(common.DESIGN_SPACE_PATH),
        "design_space_path": str(common.DESIGN_SPACE_PATH.relative_to(common.REPO_ROOT)).replace("\\", "/"),
        "lattice": list(common.LATTICE),
        "reference_mode": "geometry",
        "lift_target_mode": "force",
        "active_names": active_names,
        "schema_retained": "12d_lifting_surfaces",
        "held_at_baseline": {
            name: float(spec["baseline"]) for name, spec in bounds.items() if name not in active_names
        },
        "counts": {
            "tasks": len(per_task),
            "designs_per_task": n_designs,
            "total_attempts": len(per_task) * n_designs,
            "fit_per_task": fit_designs,
            "query_per_task": n_designs - fit_designs,
            "shared_anchors_per_task": 4,
        },
        "sampling": {
            "kind": "scrambled Sobol",
            "seed_rule": "sha256(task_id + '|%s-designs-v1')[:4 bytes]" % phase,
            "anchors": ["baseline", "low", "high", "mixed"],
            "split_rule": "index < %d fit, index >= %d query" % (fit_designs, fit_designs),
        },
        "tasks": per_task,
    }
    if phase == "s2":
        payload["sealed"] = True
        payload["protocol_note"] = (
            "S2 test queries are generated once and are independent of any online candidate set or support set"
        )
    payload["manifest_sha256"] = common.sha256_text(common.canonical_json(payload))
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("s1", "s2"), default="s1")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    cfg = common.apply_phase(args.phase)
    out = args.out or str(common.MANIFEST_PATH)
    manifest = build_manifest()
    common.atomic_write_json(out, manifest)
    counts = manifest["counts"]
    print("wrote %s" % out)
    print("phase=%s tasks=%d designs/task=%d attempts=%d" % (
        cfg["stage"], counts["tasks"], counts["designs_per_task"], counts["total_attempts"]))
    print("manifest_sha256=%s" % manifest["manifest_sha256"])
    if counts["total_attempts"] != common.BUDGET:
        raise SystemExit("%s attempts %d != budget %d" % (cfg["stage"], counts["total_attempts"], common.BUDGET))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
