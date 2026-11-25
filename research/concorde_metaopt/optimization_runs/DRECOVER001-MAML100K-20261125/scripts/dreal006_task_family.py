"""Dreal006 task family: 24 train + 8 val + 12 test physical tasks (Issue 16).

One task is a (Mach, lift force) pair at the frozen 18,288 m condition.  The
lift force is the requirement; the coefficient follows from each design own
reference area, so a bigger wing cannot pass by carrying a heavier aircraft.

The module is pure geometry-free bookkeeping: it writes the family, proves that
no two tasks share a physics digest, and refuses to reuse a physics identity
that any earlier run already spent.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.concorde_metaopt.dreal001.meta.task_spec import (
    TaskSpec,
    canonical_sha,
    validate_task_family,
)

ALTITUDE_M = 18288.0
SCHEMA = "dreal006.task_family.v1"
SPLIT_MACHS = {
    "train": (1.65, 1.75, 1.85, 1.95, 2.05, 2.15, 2.25, 2.35),
    "val": (1.70, 1.90, 2.10, 2.30),
    "test": (1.66, 1.86, 2.06, 2.26, 1.60, 2.40),
}
# Fractions of the baseline lift demand, spanning the 0.85-1.15 band.
SPLIT_LIFT_FRACTIONS = {
    "train": (0.86, 1.00, 1.14),
    "val": (0.90, 1.08),
    "test": (0.88, 1.12, 0.85, 1.15),
}
# The last four test tasks are the corners of the (Mach, lift) box: they sit on
# the declared boundary and extrapolate the joint demand, which is what the
# blind split is meant to probe.
CORNER_MACH = (1.60, 1.60, 2.40, 2.40)
CORNER_FRACTION = (0.85, 1.15, 0.85, 1.15)


def dynamic_pressure(mach: float) -> dict[str, float]:
    """q from the same 1976 atmosphere the VLM backend actually solves in."""
    import numpy as np
    from RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976 import US_Standard_1976

    atm = US_Standard_1976().compute_values(ALTITUDE_M)
    flat = lambda x: float(np.ravel(np.asarray(x, dtype=float))[0])
    rho = flat(atm.density)
    a = flat(atm.speed_of_sound)
    vinf = float(mach) * a
    return {
        "density_kg_m3": rho,
        "speed_of_sound_m_s": a,
        "vinf_m_s": vinf,
        "q_pa": 0.5 * rho * vinf * vinf,
    }


def geometry_contract(design_space_path: pathlib.Path, active_names: list[str]) -> dict:
    """The single geometry identity shared by every task of the family."""
    import hashlib

    design_space_sha = hashlib.sha256(design_space_path.read_bytes()).hexdigest()
    return {
        "schema": "dreal006.geometry_contract.v1",
        "origin": "REGENERATED_FROM_SPEC",
        "altitude_m": ALTITUDE_M,
        "design_space_path": str(design_space_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "design_space_sha256": design_space_sha,
        "active_names": list(active_names),
        "active_dim": len(active_names),
        "reference_basis": "per-design geometry: Sref=wing.area_m2",
        "note": ("Digest only. No mesh was rebuilt; the VLM panel is rebuilt per design."),
    }


def build_family(base_lift_n: float, contract_sha: str) -> list[TaskSpec]:
    tasks: list[TaskSpec] = []
    for split, machs in SPLIT_MACHS.items():
        fractions = SPLIT_LIFT_FRACTIONS[split]
        if split == "test":
            for index, mach in enumerate(machs[:4]):
                for fraction in (fractions[0], fractions[1]):
                    tasks.append(_task(split, index, mach, fraction, base_lift_n, contract_sha))
            for index, (mach, fraction) in enumerate(zip(CORNER_MACH, CORNER_FRACTION)):
                tasks.append(_task(split, 4 + index, mach, fraction, base_lift_n, contract_sha))
        else:
            for index, mach in enumerate(machs):
                for fraction in fractions:
                    tasks.append(_task(split, index, mach, fraction, base_lift_n, contract_sha))
    return tasks


def _task(split: str, index: int, mach: float, fraction: float, base_lift_n: float,
          contract_sha: str) -> TaskSpec:
    atm = dynamic_pressure(mach)
    tag = "M%03d" % round(mach * 100)
    lift = round(fraction * base_lift_n, 1)
    task_id = "DREAL006-%s-%s-L%04d" % (split.upper(), tag, round(fraction * 100))
    return TaskSpec(
        task_id=task_id,
        split=split,
        mach=float(mach),
        altitude_m=ALTITUDE_M,
        dynamic_pressure_pa=atm["q_pa"],
        lift_target_n=lift,
        geometry_contract_sha256=contract_sha,
    )


def historical_physics() -> tuple[set[str], list[dict]]:
    """Every task physics identity any earlier run already spent.

    Digests alone are not enough: this family uses a new geometry contract, so a
    renamed copy of an old task would still receive a new digest.  The physical
    key (mach, lift) is therefore checked separately.
    """
    digests: set[str] = set()
    conditions: list[dict] = []
    for path in REPO_ROOT.rglob("task_spec.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        digest = payload.get("task_physics_sha256") or payload.get("physics_sha256")
        if isinstance(digest, str) and len(digest) == 64:
            digests.add(digest)
        mach, lift = payload.get("mach"), payload.get("lift_target_n")
        if isinstance(mach, (int, float)) and isinstance(lift, (int, float)):
            conditions.append({
                "task_id": payload.get("task_id"),
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "mach": float(mach),
                "lift_target_n": float(lift),
                "altitude_m": payload.get("altitude_m"),
            })
    return digests, conditions


def nearest_spent(task: TaskSpec, conditions: list[dict]) -> dict:
    """Closest already-spent (mach, lift) pair, in relative Mach-distance."""
    best = None
    for row in conditions:
        if row["altitude_m"] is not None and abs(float(row["altitude_m"]) - task.altitude_m) > 1e-9:
            continue
        dm = abs(row["mach"] - task.mach) / task.mach
        dl = abs(row["lift_target_n"] - task.lift_target_n) / task.lift_target_n
        score = max(dm, dl)
        if best is None or score < best["max_relative_distance"]:
            best = {
                "task_id": row["task_id"],
                "mach": row["mach"],
                "lift_target_n": row["lift_target_n"],
                "max_relative_distance": score,
                "d_mach_rel": dm,
                "d_lift_rel": dl,
            }
    return best or {"task_id": None, "max_relative_distance": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parents[1] / "metadata" / "task_family.json"))
    args = parser.parse_args(argv)

    design_space = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
    active = json.loads((pathlib.Path(__file__).resolve().parents[1] / "metadata" / "active_subspace.json").read_text(encoding="utf-8"))["active_names"]
    contract = geometry_contract(design_space, active)
    contract_sha = canonical_sha(contract)

    q_ref = dynamic_pressure(2.02)["q_pa"]
    sref_ref = 358.25
    cl_ref = 0.181743998494
    base_lift = q_ref * sref_ref * cl_ref

    tasks = build_family(base_lift, contract_sha)
    validate_task_family(tuple(tasks))

    spent, conditions = historical_physics()
    clashes = [t.task_id for t in tasks if t.physics_sha256 in spent]
    if clashes:
        raise SystemExit("task physics digest already spent by an earlier run: %s" % clashes)
    # A renamed old task would keep its physical condition; require real distance.
    MIN_RELATIVE_DISTANCE = 1.0e-3
    too_close = []
    proximity = {}
    for task in tasks:
        nearest = nearest_spent(task, conditions)
        proximity[task.task_id] = nearest
        if nearest["max_relative_distance"] is not None and nearest["max_relative_distance"] < MIN_RELATIVE_DISTANCE:
            too_close.append((task.task_id, nearest))
    if too_close:
        raise SystemExit("test tasks reproduce an already-spent physical condition: %s" % (too_close,))

    counts = {split: sum(t.split == split for t in tasks) for split in ("train", "val", "test")}
    payload = {
        "schema": SCHEMA,
        "created_utc": "2026-11-25",
        "altitude_m": ALTITUDE_M,
        "base_lift_n": base_lift,
        "base_lift_definition": "q(M2.02)*Sref_ref*CL_ref, Sref_ref=358.25 m2, CL_ref=0.181743998494",
        "lift_fraction_band": [0.85, 1.15],
        "mach_band": [1.60, 2.40],
        "geometry_contract": contract,
        "geometry_contract_sha256": contract_sha,
        "counts": counts,
        "history_scan": {
            "task_spec_files_with_physics": len(conditions),
            "distinct_physics_digests": len(spent),
            "minimum_relative_distance_required": 1.0e-3,
            "minimum_relative_distance_observed": min(
                p["max_relative_distance"] for p in proximity.values()
                if p["max_relative_distance"] is not None
            ),
        },
        "tasks": [
            {
                "task_id": t.task_id,
                "split": t.split,
                "mach": t.mach,
                "altitude_m": t.altitude_m,
                "dynamic_pressure_pa": t.dynamic_pressure_pa,
                "lift_target_n": t.lift_target_n,
                "lift_fraction_of_base": t.lift_target_n / base_lift,
                "lift_tolerance_rel": t.lift_tolerance_rel,
                "physics_sha256": t.physics_sha256,
                "cl_at_sref_ref": t.lift_target_n / (t.dynamic_pressure_pa * sref_ref),
                "historical_physics_digests_scanned": len(spent),
                "historical_conditions_scanned": len(conditions),
                "nearest_spent_condition": proximity[t.task_id],
            }
            for t in tasks
        ],
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote %s: %d tasks %s" % (out, len(tasks), counts))
    print("base_lift_n = %.1f N" % base_lift)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
