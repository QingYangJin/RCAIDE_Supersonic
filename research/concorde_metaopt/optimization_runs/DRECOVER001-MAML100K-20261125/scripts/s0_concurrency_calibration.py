"""S0 concurrency calibration: throughput and tail latency at 1/4/8/12/16 workers.

Workers are separate OS processes launched with subprocess and stdio=DEVNULL.
multiprocessing.Pool is unusable on this host: the sandbox denies the named pipe
that SimpleQueue creates (PermissionError WinError 5 on _winapi.CreateFile).

Each worker pins BLAS and torch to one thread before importing numpy, so the
measurement reflects one evaluation per core rather than an oversubscribed host.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIG = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
META = pathlib.Path(__file__).resolve().parents[1] / "metadata"
BASE_LIFT_N = 1344778.5
SEED = 20261125
THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "TORCH_NUM_THREADS")


def thread_env():
    env = dict(os.environ)
    for name in THREAD_VARS:
        env[name] = "1"
    return env


def design_batch(count, names, lower, upper):
    import numpy as np
    rng = np.random.default_rng(SEED)
    return [{name: float(lower[name] + rng.random() * (upper[name] - lower[name])) for name in names}
            for _ in range(count)]


def run_worker(job_path, out_path):
    job = json.loads(pathlib.Path(job_path).read_text(encoding="utf-8"))
    names = job["names"]
    from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend
    backend = SupersonicVLMBackend(REPO_ROOT, CONFIG, mach=2.02, altitude_m=18288.0,
                                   lift_target_mode="force", lift_target_n=BASE_LIFT_N,
                                   lattice=(20, 10), design_names=names,
                                   task_fingerprint="s0-concurrency")
    rows = []
    for design in job["designs"]:
        record = backend.evaluate(design)
        rows.append({"status": record["status"], "wall": record["wall_seconds"],
                     "objective": record.get("objective")})
    pathlib.Path(out_path).write_text(json.dumps(rows), encoding="utf-8")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 4, 8, 12, 16])
    parser.add_argument("--per-worker", type=int, default=4)
    parser.add_argument("--out", default=str(META / "concurrency_calibration.json"))
    parser.add_argument("--scratch", default=str(pathlib.Path(__file__).resolve().parents[1] / "_scratch"))
    parser.add_argument("--worker-job", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--worker-out", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker_job:
        return run_worker(args.worker_job, args.worker_out)

    subspace = json.loads((META / "active_subspace.json").read_text(encoding="utf-8"))
    names = subspace["active_names"]
    from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend
    probe = SupersonicVLMBackend(REPO_ROOT, CONFIG, mach=2.02, altitude_m=18288.0,
                                 lift_target_mode="force", lift_target_n=BASE_LIFT_N,
                                 lattice=(20, 10), design_names=names,
                                 task_fingerprint="s0-concurrency")
    lower, upper = {}, {}
    for name in names:
        variable = probe.space.variables[probe.space.names.index(name)]
        lower[name], upper[name] = float(variable.lower), float(variable.upper)

    scratch = pathlib.Path(args.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    designs = design_batch(max(args.workers) * args.per_worker, names, lower, upper)
    env = thread_env()
    rows = []
    for workers in args.workers:
        jobs, outs, handles = [], [], []
        for index in range(workers):
            chunk = designs[index * args.per_worker:(index + 1) * args.per_worker]
            job_path = scratch / ("job-%02d-%02d.json" % (workers, index))
            out_path = scratch / ("out-%02d-%02d.json" % (workers, index))
            job_path.write_text(json.dumps({"names": names, "designs": chunk}), encoding="utf-8")
            jobs.append(job_path)
            outs.append(out_path)
            handles.append(subprocess.Popen(
                [sys.executable, "-B", str(pathlib.Path(__file__).resolve()),
                 "--worker-job", str(job_path), "--worker-out", str(out_path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=env, cwd=str(REPO_ROOT)))
        started = time.perf_counter()
        codes = [handle.wait() for handle in handles]
        elapsed = time.perf_counter() - started
        results = []
        for out_path in outs:
            if out_path.exists():
                results.extend(json.loads(out_path.read_text(encoding="utf-8")))
        walls = [row["wall"] for row in results]
        valid = sum(row["status"] == "VALID" for row in results)
        rows.append({
            "workers": workers,
            "exit_codes": codes,
            "evaluations": len(results),
            "wall_seconds": round(elapsed, 2),
            "evaluations_per_minute": round(60.0 * len(results) / elapsed, 2) if elapsed else None,
            "mean_worker_wall_s": round(statistics.fmean(walls), 3) if walls else None,
            "p50_worker_wall_s": round(statistics.median(walls), 3) if walls else None,
            "p95_worker_wall_s": round(sorted(walls)[max(0, int(0.95 * len(walls)) - 1)], 3) if walls else None,
            "valid": valid,
            "status_counts": {s: sum(r["status"] == s for r in results) for s in set(r["status"] for r in results)},
        })
        print("%2d workers: %6.2f eval/min  p50=%.2fs p95=%.2fs valid=%d/%d"
              % (workers, rows[-1]["evaluations_per_minute"] or 0.0,
                 rows[-1]["p50_worker_wall_s"] or 0.0, rows[-1]["p95_worker_wall_s"] or 0.0,
                 valid, len(results)))
        sys.stdout.flush()

    payload = {
        "schema": "dreal006.concurrency_calibration.v1",
        "lattice": [20, 10],
        "per_worker_designs": args.per_worker,
        "process_model": "subprocess + stdio DEVNULL (multiprocessing.Pool is blocked by the sandbox)",
        "thread_limits": {name: "1" for name in THREAD_VARS},
        "cpu_count": os.cpu_count(),
        "rows": rows,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
