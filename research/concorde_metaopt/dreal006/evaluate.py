"""S1 evaluation driver: 32 tasks x 256 pre-registered designs.

Design choices that matter for the receipt:

* The manifest is written before the first solve; this driver refuses to add a
  design that is not in it, and refuses to exceed the S1 budget of 8192.
* Raw records are append-only per task (data/s1/raw/<task>.jsonl).  A resumed
  run skips designs already recorded, so a crash costs at most the in-flight
  task's unsaved work, not its whole budget.
* Every record carries the delta of backend.solve_count so the fourth counter
  (inner VLM solves) is measured, not estimated.  A design whose delta exceeds
  the 16-solve cap is flagged.
* The five counters and per-task counts live in one ledger JSON; the label view
  and the 512-record gzip shards are rebuilt deterministically from the raw
  files.

Run with the campaign interpreter from the worktree root::

    D:/Anaconda/envs/RCAIDE/python.exe -m research.concorde_metaopt.dreal006.evaluate --workers 8
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Any

from . import common

STATUSES = ("VALID", "LIFT_RESIDUAL_REJECTED", "NON_PHYSICAL_CDI", "ALPHA_SOLVE_FAILED", "ERROR", "FAILED")


def _worker_env(tmp_dir: pathlib.Path) -> None:
    """Pin thread counts and temp dirs *before* numpy/scipy are imported."""
    os.environ["TMP"] = str(tmp_dir)
    os.environ["TEMP"] = str(tmp_dir)
    os.environ["TMPDIR"] = str(tmp_dir)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    os.environ.setdefault("PYTHONHASHSEED", "0")


def _run_task(payload: dict) -> dict:
    tmp_dir = pathlib.Path(payload["tmp_dir"])
    tmp_dir.mkdir(parents=True, exist_ok=True)
    _worker_env(tmp_dir)
    repo_root = payload["repo_root"]
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend

    task = payload["task"]
    active_names = payload["active_names"]
    held = payload["held_at_baseline"]
    backend = SupersonicVLMBackend(
        repo_root,
        payload["design_space_config"],
        mach=task["mach"],
        altitude_m=task["altitude_m"],
        lattice=tuple(payload["lattice"]),
        design_names=active_names,
        reference_mode="geometry",
        task_fingerprint=task["physics_sha256"],
        lift_target_n=task["lift_target_n"],
        lift_target_mode="force",
    )
    # Hard per-design guard: the campaign contract allows at most 16 inner VLM
    # solves per charged design (angle search plus the final recompute).  The
    # frozen backend's secant can spend up to 32 probes on a pathological
    # design; the guard stops it at the contract limit and the design is kept
    # as a charged ERROR, never as a label.
    solve_state = {"used": 0}
    original_solve = backend._solve

    def _guarded_solve(vehicle, alpha_deg):
        if solve_state["used"] >= common.MAX_INNER_SOLVES_PER_EVAL:
            raise RuntimeError(
                "inner VLM solve budget %d exceeded" % common.MAX_INNER_SOLVES_PER_EVAL
            )
        solve_state["used"] += 1
        return original_solve(vehicle, alpha_deg)

    backend._solve = _guarded_solve

    out_path = pathlib.Path(payload["out_path"])
    status_path = pathlib.Path(payload["status_path"])
    designs = payload["designs"]
    counts = {status: 0 for status in STATUSES}
    counts.update(attempted=0, inner_solves=0, budget_violations=0, cached=0, wall_seconds=0.0)
    started = time.perf_counter()

    with out_path.open("a", encoding="utf-8") as handle:
        for i, design in enumerate(designs, 1):
            x12 = dict(held)
            x12.update({name: float(value) for name, value in zip(active_names, design["active"])})
            before = backend.solve_count
            solve_state["used"] = 0
            try:
                raw = backend.evaluate(x12, purpose="s1")
            except Exception as exc:  # evaluate() already catches; keep the worker alive if not
                raw = {
                    "status": "ERROR",
                    "diagnostics": ["%s: %s" % (type(exc).__name__, str(exc)[:400])],
                    "objective": None,
                    "cached": False,
                    "wall_seconds": 0.0,
                    "design_key": design["design_id"],
                }
            inner = int(backend.solve_count - before)
            diagnostics = raw.get("diagnostics", []) or []
            solve_budget_hit = any("solve budget" in str(item) for item in diagnostics)
            record = {
                "schema": "dreal006.s1_raw_record.v1",
                "recorded_utc": common.utc_now(),
                "run_id": common.RUN_ID,
                "stage": "S1",
                "task_id": task["task_id"],
                "task_split": task["split"],
                "physics_sha256": task["physics_sha256"],
                "mach": task["mach"],
                "altitude_m": task["altitude_m"],
                "dynamic_pressure_pa": task["dynamic_pressure_pa"],
                "lift_target_n": task["lift_target_n"],
                "lift_fraction_of_base": task["lift_fraction_of_base"],
                "design_id": design["design_id"],
                "design_index": design["index"],
                "design_kind": design["kind"],
                "design_split": design["split"],
                "active_names": active_names,
                "active_values": [float(v) for v in design["active"]],
                "x12": {name: float(x12[name]) for name in x12},
                "inner_solves": inner,
                "budget_violation": inner > common.MAX_INNER_SOLVES_PER_EVAL,
                "solve_budget_hit": solve_budget_hit,
                "status": raw.get("status", "ERROR"),
                "objective_cdi": raw.get("objective"),
                "cached": bool(raw.get("cached", False)),
                "wall_seconds": raw.get("wall_seconds"),
                "cl_actual": raw.get("cl_actual"),
                "cl_target": raw.get("cl_target"),
                "alpha_deg": raw.get("alpha_deg"),
                "lift_residual": raw.get("lift_residual"),
                "sref_used_m2": raw.get("sref_used_m2"),
                "cref_used_m": raw.get("cref_used_m"),
                "bref_used_m": raw.get("bref_used_m"),
                "lattice": raw.get("lattice"),
                "backend_version": raw.get("backend_version"),
                "diagnostics": diagnostics,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            counts["attempted"] += 1
            counts["inner_solves"] += inner
            counts["wall_seconds"] += float(raw.get("wall_seconds") or 0.0)
            counts["cached"] += int(record["cached"])
            counts["budget_violations"] += int(record["budget_violation"])
            counts[record["status"]] = counts.get(record["status"], 0) + 1
            if i % 16 == 0 or i == len(designs):
                common.atomic_write_json(status_path, {
                    "task_id": task["task_id"],
                    "pid": os.getpid(),
                    "attempted": counts["attempted"],
                    "total": len(designs),
                    "valid": counts["VALID"],
                    "inner_solves": counts["inner_solves"],
                    "wall_seconds": round(counts["wall_seconds"], 1),
                    "updated_utc": common.utc_now(),
                })
    elapsed = time.perf_counter() - started
    return {
        "task_id": task["task_id"],
        "split": task["split"],
        "attempted": counts["attempted"],
        "counts": {status: counts[status] for status in STATUSES},
        "inner_solves": counts["inner_solves"],
        "cached": counts["cached"],
        "budget_violations": counts["budget_violations"],
        "wall_seconds": round(elapsed, 2),
        "evals_per_min": round(counts["attempted"] / elapsed * 60.0, 1) if elapsed > 0 else 0.0,
    }


def _raw_path(task_id: str) -> pathlib.Path:
    return common.RAW_DIR / ("%s.jsonl" % task_id)


def collect_records() -> list[dict]:
    records = []
    for path in sorted(common.RAW_DIR.glob("*.jsonl")):
        records.extend(common.read_jsonl(path))
    return records


def build_labels(records: list[dict]) -> dict:
    valid = [r for r in records if r.get("status") == "VALID" and r.get("objective_cdi") is not None]
    labels_path = common.DATA_DIR / "labels.jsonl"
    tmp = labels_path.with_suffix(".jsonl.tmp")
    by_task: dict[str, dict] = {}
    with tmp.open("w", encoding="utf-8") as handle:
        for record in sorted(valid, key=lambda r: (r["task_id"], r["design_index"])):
            row = {
                "task_id": record["task_id"],
                "split": record["task_split"],
                "design_id": record["design_id"],
                "design_index": record["design_index"],
                "design_kind": record["design_kind"],
                "design_split": record["design_split"],
                "active_names": record["active_names"],
                "active_values": record["active_values"],
                "x12": record["x12"],
                "cdi": record["objective_cdi"],
                "mach": record["mach"],
                "altitude_m": record["altitude_m"],
                "dynamic_pressure_pa": record["dynamic_pressure_pa"],
                "lift_target_n": record["lift_target_n"],
                "lift_fraction_of_base": record["lift_fraction_of_base"],
                "physics_sha256": record["physics_sha256"],
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            task = by_task.setdefault(record["task_id"], {"n": 0, "fit": 0, "query": 0, "j_ref": None})
            task["n"] += 1
            task["fit" if record["design_split"] == "fit" else "query"] += 1
            if record["design_kind"] == "anchor-baseline":
                task["j_ref"] = record["objective_cdi"]
                task["j_ref_design_id"] = record["design_id"]
    os.replace(tmp, labels_path)
    missing_jref = sorted(t for t, info in by_task.items() if info["j_ref"] is None)
    manifest = {
        "schema": "dreal006.%s_labels.v1" % common.CURRENT_PHASE,
        "created_utc": common.utc_now(),
        "rows": len(valid),
        "tasks": len(by_task),
        "fit_rows": sum(info["fit"] for info in by_task.values()),
        "query_rows": sum(info["query"] for info in by_task.values()),
        "j_ref_rule": "CDi of the anchor-baseline design of the same task",
        "max_inner_solves_per_eval": common.MAX_INNER_SOLVES_PER_EVAL,
        "solve_guard": "hard guard around SupersonicVLMBackend._solve",
        "missing_j_ref_tasks": missing_jref,
        "per_task": by_task,
        "labels_sha256": common.sha256_file(labels_path),
    }
    common.atomic_write_json(common.DATA_DIR / "labels_manifest.json", manifest)
    return manifest


def build_shards(records: list[dict]) -> dict:
    if common.SHARD_DIR.exists():
        shutil.rmtree(common.SHARD_DIR)
    common.SHARD_DIR.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: (r["task_id"], r["design_index"]))
    shards = []
    for start in range(0, len(ordered), common.SHARD_SIZE):
        chunk = ordered[start:start + common.SHARD_SIZE]
        name = "%s_shard_%05d.jsonl.gz" % (common.CURRENT_PHASE, start // common.SHARD_SIZE)
        path = common.SHARD_DIR / name
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            for record in chunk:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        shards.append({
            "file": name,
            "records": len(chunk),
            "bytes": path.stat().st_size,
            "sha256": common.sha256_file(path),
            "first": [chunk[0]["task_id"], chunk[0]["design_index"]],
            "last": [chunk[-1]["task_id"], chunk[-1]["design_index"]],
        })
    manifest = {
        "schema": "dreal006.%s_shards.v1" % common.CURRENT_PHASE,
        "created_utc": common.utc_now(),
        "records": len(ordered),
        "shard_size": common.SHARD_SIZE,
        "shards": shards,
        "total_bytes": sum(s["bytes"] for s in shards),
    }
    common.atomic_write_json(common.SHARD_DIR / "manifest.json", manifest)
    return manifest


def refresh_derived(records: list[dict] | None = None, shards: bool = True) -> dict:
    records = collect_records() if records is None else records
    labels = build_labels(records)
    shard_manifest = build_shards(records) if shards else None
    return {"labels": labels, "shards": shard_manifest}


def write_ledger(records: list[dict], per_task: dict, labels: dict | None, shards: dict | None) -> dict:
    counts = {status: 0 for status in STATUSES}
    for record in records:
        counts[record.get("status", "ERROR")] = counts.get(record.get("status", "ERROR"), 0) + 1
    phase = common.CURRENT_PHASE
    ledger = {
        "schema": "dreal006.%s_ledger.v1" % phase,
        "run_id": common.RUN_ID,
        "stage": common.phase_config(phase)["stage"],
        "updated_utc": common.utc_now(),
        "budget": {
            "%s_attempts_cap" % phase: common.BUDGET,
            "charged": len(records),
            "remaining": common.BUDGET - len(records),
        },
        "protocol": {
            "lattice": list(common.LATTICE),
            "reference_mode": "geometry",
            "lift_target_mode": "force",
            "max_inner_solves_per_eval": common.MAX_INNER_SOLVES_PER_EVAL,
            "solve_guard": "hard guard around SupersonicVLMBackend._solve",
        },
        "counters": {
            "evaluation_attempts_charged": len(records),
            "fresh_evaluator_attempts": sum(1 for r in records if not r.get("cached")),
            "unique_task_design_labels": len({(r["task_id"], r["design_id"]) for r in records}),
            "vlm_inner_solves_actual": sum(int(r.get("inner_solves") or 0) for r in records),
            "cache_hits": sum(1 for r in records if r.get("cached")),
        },
        "by_status": counts,
        "budget_violations": sum(1 for r in records if r.get("budget_violation")),
        "solve_budget_hits": sum(1 for r in records if r.get("solve_budget_hit")),
        "max_inner_solves_observed": max([int(r.get("inner_solves") or 0) for r in records] or [0]),
        "per_task": per_task,
        "labels": None if labels is None else {
            "rows": labels["rows"],
            "fit_rows": labels["fit_rows"],
            "query_rows": labels["query_rows"],
            "missing_j_ref_tasks": labels["missing_j_ref_tasks"],
            "labels_sha256": labels["labels_sha256"],
        },
        "shards": None if shards is None else {
            "records": shards["records"],
            "shard_count": len(shards["shards"]),
            "total_bytes": shards["total_bytes"],
        },
        "manifest_sha256": None,
    }
    if common.MANIFEST_PATH.exists():
        ledger["manifest_sha256"] = common.read_json(common.MANIFEST_PATH).get("manifest_sha256")
    common.atomic_write_json(common.LEDGER_PATH, ledger)
    return ledger


def update_status(phase: str, **extra: Any) -> None:
    payload = {"schema": "dreal006.%s_status.v1" % common.CURRENT_PHASE, "phase": phase,
               "updated_utc": common.utc_now()}
    payload.update(extra)
    common.atomic_write_json(common.STATUS_PATH, payload)


def _read_task_progress(task_id: str) -> tuple[set[str], int]:
    path = _raw_path(task_id)
    common.repair_jsonl(path)
    rows = common.read_jsonl(path)
    return {row["design_id"] for row in rows}, len(rows)


def _acquire_lock(force: bool) -> None:
    if common.LOCK_PATH.exists():
        if not force:
            raise SystemExit(
                "run lock exists: %s\nIf no evaluation is running, pass --force-unlock." % common.LOCK_PATH
            )
        common.LOCK_PATH.unlink()
    common.LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(common.LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"pid": os.getpid(), "started_utc": common.utc_now(), "argv": sys.argv}))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("s1", "s2"), default="s1",
                        help="S1 = train+val design bank; S2 = sealed test queries (1536 attempts)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--task-limit", type=int, default=0, help="only the first N manifest tasks (smoke)")
    parser.add_argument("--design-limit", type=int, default=0, help="only the first N missing designs per task (smoke)")
    parser.add_argument("--max-attempts", type=int, default=0, help="hard cap for this invocation")
    parser.add_argument("--force-unlock", action="store_true")
    parser.add_argument("--no-shards", action="store_true")
    parser.add_argument("--rebuild-only", action="store_true", help="rebuild labels/shards/ledger, no evaluation")
    parser.add_argument("--allow-partial", action="store_true", help="do not warn when S1 is incomplete")
    parser.add_argument("--worker-task", default="", help=argparse.SUPPRESS)
    parser.add_argument("--worker-summary", default="", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    cfg = common.apply_phase(args.phase)

    common.DATA_DIR.mkdir(parents=True, exist_ok=True)
    common.RAW_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = common.RUN_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    _worker_env(tmp_dir)

    if args.worker_task:
        manifest = common.read_json(common.MANIFEST_PATH)
        if args.worker_task not in manifest["tasks"]:
            raise SystemExit("unknown task %s" % args.worker_task)
        task = manifest["tasks"][args.worker_task]
        done, _ = _read_task_progress(task["task_id"])
        todo = [d for d in task["designs"] if d["design_id"] not in done]
        if args.design_limit:
            todo = todo[: args.design_limit]
        payload = {
            "repo_root": str(common.REPO_ROOT),
            "design_space_config": str(common.DESIGN_SPACE_PATH),
            "active_names": manifest["active_names"],
            "held_at_baseline": manifest["held_at_baseline"],
            "lattice": manifest["lattice"],
            "task": task,
            "designs": todo,
            "out_path": str(_raw_path(task["task_id"])),
            "status_path": str(common.RAW_DIR / ("%s.status.json" % task["task_id"])),
            "tmp_dir": str(tmp_dir),
        }
        summary = _run_task(payload)
        common.atomic_write_json(args.worker_summary, summary)
        print(json.dumps(summary))
        return 0

    if args.rebuild_only:
        records = collect_records()
        labels = build_labels(records)
        shards = build_shards(records) if not args.no_shards else None
        ledger = write_ledger(records, {}, labels, shards)
        print(json.dumps(ledger["counters"], indent=2))
        print("labels rows=%d fit=%d query=%d" % (labels["rows"], labels["fit_rows"], labels["query_rows"]))
        return 0

    _acquire_lock(args.force_unlock)
    try:
        if not common.MANIFEST_PATH.exists():
            raise SystemExit("missing manifest %s; run design_bank first" % common.MANIFEST_PATH)
        manifest = common.read_json(common.MANIFEST_PATH)
        tasks = list(manifest["tasks"].values())
        if args.task_limit:
            tasks = tasks[: args.task_limit]

        planned = []
        existing_total = 0
        for task in tasks:
            done, n = _read_task_progress(task["task_id"])
            existing_total += n
            todo = [d for d in task["designs"] if d["design_id"] not in done]
            if args.design_limit:
                todo = todo[: args.design_limit]
            if n + len(todo) > len(task["designs"]):
                raise SystemExit("task %s would exceed %d designs" % (task["task_id"], len(task["designs"])))
            if todo:
                planned.append((task, todo))

        if existing_total > common.BUDGET:
            raise SystemExit("already recorded %d > budget %d" % (existing_total, common.BUDGET))
        todo_total = sum(len(todo) for _, todo in planned)
        remaining = common.BUDGET - existing_total
        cap = remaining if args.max_attempts <= 0 else min(remaining, args.max_attempts)
        if todo_total > cap:
            raise SystemExit("planned %d attempts exceeds allowed %d (budget remaining %d)" % (todo_total, cap, remaining))

        print("manifest %s" % manifest["manifest_sha256"])
        print("tasks=%d already=%d todo=%d cap=%d workers=%d" % (len(tasks), existing_total, todo_total, cap, args.workers))
        update_status("evaluating", planned_attempts=todo_total, already_recorded=existing_total,
                      manifest_sha256=manifest["manifest_sha256"], workers=args.workers)

        payloads = []
        for task, todo in planned:
            payloads.append({
                "repo_root": str(common.REPO_ROOT),
                "design_space_config": str(common.DESIGN_SPACE_PATH),
                "active_names": manifest["active_names"],
                "held_at_baseline": manifest["held_at_baseline"],
                "lattice": manifest["lattice"],
                "task": task,
                "designs": todo,
                "out_path": str(_raw_path(task["task_id"])),
                "status_path": str(common.RAW_DIR / ("%s.status.json" % task["task_id"])),
                "tmp_dir": str(tmp_dir),
            })

        per_task = {}
        for task in tasks:
            per_task[task["task_id"]] = {"planned": len(task["designs"]), "recorded": 0}
        for path in common.RAW_DIR.glob("*.jsonl"):
            task_id = path.stem
            if task_id in per_task:
                per_task[task_id]["recorded"] = len(common.read_jsonl(path))

        completed = 0
        started = time.time()
        processes = []
        pending = [(task, todo) for task, todo in planned]
        logs_dir = common.RAW_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        while pending or processes:
            while pending and len(processes) < max(1, args.workers):
                task, todo = pending.pop(0)
                summary_path = common.RAW_DIR / ("%s.summary.json" % task["task_id"])
                if summary_path.exists():
                    summary_path.unlink()
                log_path = logs_dir / ("%s.log" % task["task_id"])
                command = [
                    sys.executable, "-m", "research.concorde_metaopt.dreal006.evaluate",
                    "--phase", args.phase,
                    "--worker-task", task["task_id"], "--worker-summary", str(summary_path),
                ]
                if args.design_limit:
                    command += ["--design-limit", str(args.design_limit)]
                log_handle = log_path.open("ab")
                proc = subprocess.Popen(
                    command,
                    cwd=str(common.REPO_ROOT),
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=os.environ.copy(),
                )
                processes.append({"proc": proc, "task": task, "summary": summary_path,
                                  "log": log_handle, "log_path": log_path})
            time.sleep(2)
            still_running = []
            for item in processes:
                code = item["proc"].poll()
                if code is None:
                    still_running.append(item)
                    continue
                item["log"].close()
                completed += 1
                elapsed = time.time() - started
                summary = common.read_json(item["summary"]) if item["summary"].exists() else None
                if code != 0 or summary is None:
                    tail = ""
                    try:
                        tail = item["log_path"].read_text(encoding="utf-8", errors="replace")[-800:]
                    except OSError:
                        pass
                    print("FAILED %s exit=%s log=%s\n%s" % (
                        item["task"]["task_id"], code, item["log_path"], tail), flush=True)
                    per_task[item["task"]["task_id"]]["failed"] = True
                else:
                    per_task[summary["task_id"]].update(summary)
                    print("[%d/%d] %s %s valid=%d solves=%d %.1fs (%.1f eval/min, wall %.0fs)" % (
                        completed, len(payloads), summary["task_id"], summary["split"],
                        summary["counts"]["VALID"], summary["inner_solves"], summary["wall_seconds"],
                        summary["evals_per_min"], elapsed,
                    ), flush=True)
                records = collect_records()
                write_ledger(records, per_task, None, None)
                update_status("evaluating", completed_tasks=completed, total_tasks=len(payloads),
                              charged=len(records), elapsed_seconds=round(elapsed, 1))
            processes = still_running

        records = collect_records()
        labels = build_labels(records)
        shards = build_shards(records) if not args.no_shards else None
        ledger = write_ledger(records, per_task, labels, shards)
        print(json.dumps(ledger["counters"], indent=2))
        print("labels rows=%d fit=%d query=%d missing_j_ref=%s" % (
            labels["rows"], labels["fit_rows"], labels["query_rows"], labels["missing_j_ref_tasks"]))
        if shards:
            print("shards=%d records=%d bytes=%d" % (
                len(shards["shards"]), shards["records"], shards["total_bytes"]))
        update_status("complete", charged=len(records), labels_rows=labels["rows"],
                      missing_j_ref_tasks=labels["missing_j_ref_tasks"], ledger=ledger["counters"])
        if not args.allow_partial and len(records) < common.BUDGET and todo_total + existing_total < common.BUDGET:
            print("NOTE: %s is not complete (%d/%d); rerun to continue." % (
                cfg["stage"], len(records), common.BUDGET))
        return 0
    finally:
        try:
            common.LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
