"""S0 screening: which of the ten wing variables actually move the objective.

One-at-a-time perturbation of every candidate variable to its declared lower
and upper bound at the 20x10 lattice, at the frozen M2.02 task force.  The
result justifies the 4-6 dimensional active subspace instead of asserting it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend

CONFIG = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
WING_VARS = ("wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3",
             "span_location_2", "span_location_3", "chord_ratio_2", "chord_ratio_3",
             "tip_twist")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lattice", nargs=2, type=int, default=(20, 10))
    parser.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parents[1] / "metadata" / "subspace_screen.json"))
    parser.add_argument("--lift-mode", default="force", choices=("coefficient", "force"))
    args = parser.parse_args(argv)

    backend = SupersonicVLMBackend(
        REPO_ROOT, CONFIG,
        mach=2.02, altitude_m=18288.0,
        cl_target=0.181743998494,
        lift_target_mode=args.lift_mode,
        lift_target_n=0.181743998494 * 358.25 * 20483.940233430174,
        lattice=tuple(args.lattice),
        task_fingerprint="s0-subspace-screen",
    )
    space = backend.space
    baseline = {name: float(space.variables[space.names.index(name)].baseline) for name in space.names}

    started = time.time()
    base_record = backend.evaluate(baseline)
    if base_record["status"] != "VALID":
        raise SystemExit("baseline did not solve: %s" % base_record["status"])
    base_cdi = base_record["objective"]

    rows = []
    for name in WING_VARS:
        variable = space.variables[space.names.index(name)]
        probes = {}
        for label, value in (("lower", variable.lower), ("upper", variable.upper)):
            design = dict(baseline)
            design[name] = float(value)
            record = backend.evaluate(design)
            probes[label] = {
                "value": float(value),
                "status": record["status"],
                "cdi": record.get("objective"),
                "cl_actual": record.get("cl_actual"),
                "alpha_deg": record.get("alpha_deg"),
                "lift_residual": record.get("lift_residual"),
            }
        deltas = [p["cdi"] - base_cdi for p in probes.values() if p["cdi"] is not None]
        span = abs(variable.upper - variable.lower)
        rows.append({
            "name": name,
            "unit": variable.unit,
            "baseline": float(variable.baseline),
            "lower": float(variable.lower),
            "upper": float(variable.upper),
            "cdi_delta_lower": (probes["lower"]["cdi"] - base_cdi) if probes["lower"]["cdi"] is not None else None,
            "cdi_delta_upper": (probes["upper"]["cdi"] - base_cdi) if probes["upper"]["cdi"] is not None else None,
            "max_abs_cdi_delta": max((abs(d) for d in deltas), default=0.0),
            "relative_to_baseline": max((abs(d) for d in deltas), default=0.0) / base_cdi,
            "probes": probes,
        })

    ranked = sorted(rows, key=lambda r: r["relative_to_baseline"], reverse=True)
    payload = {
        "schema": "dreal006.subspace_screen.v1",
        "lattice": list(args.lattice),
        "lift_target_mode": args.lift_mode,
        "lift_target_n": 0.181743998494 * 358.25 * 20483.940233430174,
        "baseline_cdi": base_cdi,
        "baseline_status": base_record["status"],
        "baseline_lift_residual": base_record.get("lift_residual"),
        "sref_used_m2": base_record.get("sref_used_m2"),
        "cl_target_at_baseline": base_record.get("cl_target"),
        "evaluations": backend.solve_count,
        "wall_seconds": round(time.time() - started, 3),
        "ranked": [r["name"] for r in ranked],
        "rows": rows,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in ranked:
        print("%-16s rel=%7.4f%%  dlo=%+9.3e  dhi=%+9.3e  status=%s/%s" % (
            row["name"], 100.0 * row["relative_to_baseline"],
            row["cdi_delta_lower"] or 0.0, row["cdi_delta_upper"] or 0.0,
            row["probes"]["lower"]["status"], row["probes"]["upper"]["status"]))
    print("baseline CDi=%.9f  wall=%.2fs" % (base_cdi, time.time() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
