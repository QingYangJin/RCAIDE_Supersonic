"""S0 lattice calibration on a pre-registered joint design set (contract 3.2).

72 designs are drawn before any solve: the baseline, the 32 corners of the
active 5D box, and 39 seeded space-filling points.  All 72 run at 20x10; a
pre-declared 24-design subset also runs at 30x15 and 45x25 so the coarse panel
can be judged against the finest one instead of against itself.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend

CONFIG = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
META = pathlib.Path(__file__).resolve().parents[1] / "metadata"
LATTICES = ((20, 10), (30, 15), (45, 25))
BASE_LIFT_N = 1344778.5
SEED = 20261125


def preregister(names, lower, upper, baseline):
    designs = [("baseline", dict(baseline))]
    # 2^5 corners, pre-declared in a fixed, reproducible order.
    for mask in range(32):
        design = {}
        for bit, name in enumerate(names):
            design[name] = float(upper[name] if (mask >> bit) & 1 else lower[name])
        designs.append(("corner-%02d" % mask, design))
    rng = np.random.default_rng(SEED)
    for index in range(39):
        design = {name: float(lower[name] + rng.random() * (upper[name] - lower[name])) for name in names}
        designs.append(("sobol-%02d" % index, design))
    subset = [designs[0]] + [designs[1 + 4 * i] for i in range(6)] + [designs[32 + i] for i in range(17)]
    return designs, subset


def spearman(a, b):
    ra = np.argsort(np.argsort(np.asarray(a))).astype(float)
    rb = np.argsort(np.argsort(np.asarray(b))).astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = float(np.sqrt((ra * ra).sum() * (rb * rb).sum()))
    return float((ra * rb).sum() / denom) if denom else float("nan")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(META / "lattice_calibration.json"))
    args = parser.parse_args(argv)

    subspace = json.loads((META / "active_subspace.json").read_text(encoding="utf-8"))
    names = subspace["active_names"]
    probe = SupersonicVLMBackend(REPO_ROOT, CONFIG, mach=2.02, altitude_m=18288.0,
                                 lift_target_mode="force", lift_target_n=BASE_LIFT_N,
                                 lattice=(20, 10), design_names=names,
                                 task_fingerprint="s0-lattice-calibration")
    lower, upper, baseline = {}, {}, {}
    for name in names:
        variable = probe.space.variables[probe.space.names.index(name)]
        lower[name], upper[name], baseline[name] = float(variable.lower), float(variable.upper), float(variable.baseline)

    designs, subset = preregister(names, lower, upper, baseline)
    subset_names = {label for label, _ in subset}
    results = {lattice: {} for lattice in LATTICES}
    timings = {lattice: [] for lattice in LATTICES}
    started = time.time()

    for lattice in LATTICES:
        backend = SupersonicVLMBackend(REPO_ROOT, CONFIG, mach=2.02, altitude_m=18288.0,
                                       lift_target_mode="force", lift_target_n=BASE_LIFT_N,
                                       lattice=lattice, design_names=names,
                                       task_fingerprint="s0-lattice-calibration")
        pool = designs if lattice == (20, 10) else subset
        for label, design in pool:
            record = backend.evaluate(design)
            results[lattice][label] = {
                "status": record["status"],
                "cdi": record.get("objective"),
                "alpha_deg": record.get("alpha_deg"),
                "lift_residual": record.get("lift_residual"),
                "sref_used_m2": record.get("sref_used_m2"),
            }
            timings[lattice].append(record["wall_seconds"])
        print("lattice %s done: %d designs, %.1fs" % (lattice, len(pool), time.time() - started))

    common = []
    for label, _ in subset:
        row = [results[lattice].get(label, {}).get("cdi") for lattice in LATTICES]
        if all(v is not None for v in row):
            common.append((label, row))
    coarse = np.array([row[0] for _, row in common])
    mid = np.array([row[1] for _, row in common])
    fine = np.array([row[2] for _, row in common])

    # Differences are what an optimiser actually consumes: consecutive pairs.
    diffs_coarse = np.array([coarse[i] - coarse[i - 1] for i in range(1, len(coarse))])
    diffs_fine = np.array([fine[i] - fine[i - 1] for i in range(1, len(fine))])
    resolution = float(np.median(np.abs(np.diff(np.sort(fine)))))
    resolvable = np.abs(diffs_fine) > resolution
    sign_agreement = float(np.mean(np.sign(diffs_coarse[resolvable]) == np.sign(diffs_fine[resolvable]))) if resolvable.any() else float("nan")

    payload = {
        "schema": "dreal006.lattice_calibration.v1",
        "purpose": "engineering screening of the panel resolution, not an external physical certification",
        "mach": 2.02,
        "altitude_m": 18288.0,
        "lift_target_mode": "force",
        "lift_target_n": BASE_LIFT_N,
        "active_names": names,
        "design_set": {"total": len(designs), "composition": "baseline + 32 corners + 39 seeded space-filling",
                       "seed": SEED, "fine_subset": len(subset), "fine_subset_labels": sorted(subset_names)},
        "lattices": list(LATTICES),
        "common_designs": len(common),
        "metrics": {
            "spearman_20x10_vs_45x25": spearman(coarse, fine),
            "spearman_30x15_vs_45x25": spearman(mid, fine),
            "spearman_20x10_vs_30x15": spearman(coarse, mid),
            "differential_sign_agreement_20x10_vs_45x25": sign_agreement,
            "resolution_median_gap_45x25": resolution,
            "resolvable_pairs": int(resolvable.sum()),
            "total_pairs": int(len(diffs_fine)),
            "status_counts_20x10": _counts(results[(20, 10)]),
            "status_counts_30x15": _counts(results[(30, 15)]),
            "status_counts_45x25": _counts(results[(45, 25)]),
            "mean_wall_seconds": {str(k): round(float(np.mean(v)), 3) for k, v in timings.items() if v},
            "p95_wall_seconds": {str(k): round(float(np.percentile(v, 95)), 3) for k, v in timings.items() if v},
        },
        "readings": {str(lattice): results[lattice] for lattice in LATTICES},
        "wall_seconds": round(time.time() - started, 2),
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for key, value in payload["metrics"].items():
        print("%-46s %s" % (key, value))
    return 0


def _counts(rows):
    counts = {}
    for row in rows.values():
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
