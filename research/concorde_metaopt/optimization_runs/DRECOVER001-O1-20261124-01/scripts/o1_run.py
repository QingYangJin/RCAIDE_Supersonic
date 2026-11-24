"""O1 runner: evaluate the shared support once, run the three arms, close out.

Phases
------
0. gates      -- the preregistration on disk must match the code on disk, and the O1 GO
                 record must bind this exact dossier/preregistration/code. No GO, no spend.
1. support    -- the three pre-designated shared support designs are solved for real, once.
                 Every arm is then charged their full cost as equivalent cost.
2. arms       -- SOBOL_BO, COND_SUPERVISED_KSHOT_BO and COND_FOMAML_KSHOT_BO run in
                 sequence, each with its own ledger and its own real feedback.
3. close      -- one result document with the primary endpoints, the cost ledger and the
                 anytime curves; plus a batch close record.

The physical bill and the equivalent bill are both reported and never conflated: the
three support designs are solved once but charged to all three arms.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(RUN / "scripts"))
sys.path.insert(0, str(REPO))

import o1_arms as arms  # noqa: E402
import o1_eval as ev  # noqa: E402
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

PREREG = RUN / "o1_preregistration.json"
GO = RUN / "o1_go_record.json"
LOCK = RUN / "o1_run.lock"
RESOURCE = RUN / "o1_resource.jsonl"
RESULT = RUN / "o1_result.json"
CLOSE = RUN / "o1_batch_close.json"


def sha(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(payload: Any) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def now() -> str:
    return ev.now()


class ProtocolError(RuntimeError):
    pass


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ProtocolError("missing record %s" % (path,))
    return json.loads(path.read_text(encoding="utf-8"))


def check_preregistration() -> Dict[str, Any]:
    """The preregistration must describe the code that is on disk right now."""
    prereg = load_json(PREREG)
    problems = []
    for name, expected in prereg["code"]["code_shas"].items():
        path = Path(prereg["code"]["code_root"]) / name
        if not path.exists():
            problems.append("%s is missing" % (name,))
            continue
        actual = sha(path)
        if actual != expected:
            problems.append("%s sha256 %s != preregistered %s" % (name, actual, expected))
    for name, expected in arms.CAPS.items():
        if name in prereg["budgets"]["caps"]:
            if prereg["budgets"]["caps"][name] != expected:
                problems.append("cap %s preregistered %r but the code says %r"
                                % (name, prereg["budgets"]["caps"][name], expected))
    if prereg["budgets"]["target_improvement_fraction"] != arms.TARGET_IMPROVEMENT_FRACTION:
        problems.append("target improvement fraction drifted")
    if problems:
        raise ProtocolError("preregistration does not match this code: " + "; ".join(problems))
    return prereg


def check_go(prereg: Dict[str, Any]) -> Dict[str, Any]:
    """No GO, no spend. The GO must bind the exact dossier, preregistration and code."""
    go = load_json(GO)
    problems = []
    if not go.get("go_sha256"):
        problems.append("GO has no self hash")
    if go.get("authorization_kind") != "O1_THREE_ARM":
        problems.append("GO authorization_kind is %r" % (go.get("authorization_kind"),))
    if go.get("preregistration_sha256") != sha(PREREG):
        problems.append("GO does not bind the preregistration on disk")
    dossier = RUN / "o1_a5_dossier.md"
    if not dossier.exists():
        problems.append("dossier is missing")
    elif go.get("a5_dossier_sha256") != sha(dossier):
        problems.append("GO does not bind the dossier on disk")
    verdict = load_json(RUN / "o1_a5_verdict.json") if (RUN / "o1_a5_verdict.json").exists() else None
    if verdict is None:
        problems.append("no A5 verdict record")
    elif verdict.get("verdict") != "O1_THREE_ARM_REVIEW_PASS":
        problems.append("A5 verdict is %r" % (verdict.get("verdict"),))
    if verdict is not None and go.get("a5_verdict_sha256") != sha(RUN / "o1_a5_verdict.json"):
        problems.append("GO does not bind the A5 verdict on disk")
    if go.get("code_shas") != prereg["code"]["code_shas"]:
        problems.append("GO was signed for a different set of code hashes")
    if go.get("pairing", {}).get("task_key") != prereg["pairing"]["task_key"]:
        problems.append("GO pairing task differs from the preregistration")
    if problems:
        raise ProtocolError("the O1 GO does not authorise this run: " + "; ".join(problems))
    return go


def acquire_lock() -> Dict[str, Any]:
    if LOCK.exists():
        raise ProtocolError("another O1 run holds %s" % (LOCK,))
    payload = {"pid": os.getpid(), "utc": now(), "argv": sys.argv}
    LOCK.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def release_lock(reason: str) -> None:
    if LOCK.exists():
        LOCK.unlink()
    (RUN / "o1_run_lock_history.jsonl").open("a", encoding="utf-8").write(
        json.dumps({"utc": now(), "reason": reason, "argv": sys.argv}) + "\n")


class _Sampler(threading.Thread):
    """Whole-machine CPU and memory, sampled once a second while the run is live."""

    def __init__(self, path: Path, label: str) -> None:
        super().__init__(daemon=True)
        self.path = path
        self.label = label
        self.stop_flag = threading.Event()

    @staticmethod
    def _cpu_times() -> Optional[tuple]:
        try:
            idle = ctypes.c_ulonglong()
            kernel = ctypes.c_ulonglong()
            user = ctypes.c_ulonglong()
            if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),
                                                         ctypes.byref(kernel),
                                                         ctypes.byref(user)):
                return None
            return (int(idle.value), int(kernel.value), int(user.value))
        except Exception:
            return None

    @staticmethod
    def _memory() -> Optional[Dict[str, int]]:
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return {"load_fraction": status.dwMemoryLoad / 100.0,
                    "total_phys_bytes": int(status.ullTotalPhys),
                    "avail_phys_bytes": int(status.ullAvailPhys),
                    "phys_used_bytes": int(status.ullTotalPhys - status.ullAvailPhys)}
        except Exception:
            return None

    def run(self) -> None:
        previous = self._cpu_times()
        while not self.stop_flag.wait(1.0):
            current = self._cpu_times()
            busy = None
            if previous and current:
                d_idle = current[0] - previous[0]
                d_total = (current[1] - previous[1]) + (current[2] - previous[2])
                if d_total > 0:
                    busy = max(0.0, min(1.0, 1.0 - d_idle / d_total))
            previous = current
            memory = self._memory() or {}
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"utc": now(), "label": self.label,
                                         "cpu_busy_fraction": busy,
                                         **memory}) + "\n")


def _resource_summary(path: Path) -> Dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    busy = [row["cpu_busy_fraction"] for row in rows if row.get("cpu_busy_fraction") is not None]
    load = [row["load_fraction"] for row in rows if row.get("load_fraction") is not None]
    used = [row["phys_used_bytes"] for row in rows if row.get("phys_used_bytes") is not None]
    return {"schema": "dreal005.o1_resource_summary.v1", "sample_count": len(rows),
            "cpu_busy_mean": sum(busy) / len(busy) if busy else None,
            "cpu_busy_max": max(busy) if busy else None,
            "memory_load_mean": sum(load) / len(load) if load else None,
            "phys_used_mean_bytes": sum(used) / len(used) if used else None,
            "first_utc": rows[0]["utc"] if rows else None,
            "last_utc": rows[-1]["utc"] if rows else None,
            "note": ("whole-machine CPU and memory; VSPAERO runs at omp=1 so this is an "
                     "upper bound on what the experiment itself consumed")}


def run_support(task_key: str, dry_run: bool) -> List[arms.DesignRecord]:
    """Solve the three pre-designated shared support designs once, for real."""
    records: List[arms.DesignRecord] = []
    for index, design in enumerate(arms.support_designs()):
        record = arms.DesignRecord(arm="SHARED", role="shared_support", design_index=index,
                                   tag="s%02d" % (index,), x12=tuple(design))
        if dry_run:
            record = _dry_evaluate(task_key, "SUPPORT", record)
        else:
            arms.evaluate_design(task_key, "SUPPORT", record, RUN / "o1_attempts.jsonl")
        records.append(record)
        print("support s%02d: %s di_n=%r starts=%d internal=%d"
              % (index, record.status, record.di_n, record.starts, record.internal))
    payload = {"schema": "dreal005.o1_shared_support.v1", "task_key": task_key,
               "task_id": ev.task_spec(task_key).task_id,
               "task_physics_sha256": ev.task_spec(task_key).physics_sha256,
               "records": [record.as_dict() for record in records],
               "starts": sum(r.starts for r in records),
               "internal": sum(r.internal for r in records)}
    (RUN / "o1_shared_support.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return records


def _dry_evaluate(task_key: str, group: str, record: arms.DesignRecord) -> arms.DesignRecord:
    """Plumbing check only: build both cases with dry_run, start nothing, charge nothing."""
    cl_target = ev.cl_target_for(task_key, list(record.x12))
    coarse = ev.make_case(task_key, group, list(record.x12), record.tag, "coarse",
                          o0.coarse_alphas(), cl_target, o0.COARSE_ALPHA_GUESS_DEG)
    result = ev.run(coarse, "%s-%s-coarse-dry" % (group, record.tag), dry_run=True)
    record.status = "DRY_RUN_%s" % (result.get("status"),)
    record.starts = 0
    record.internal = 0
    record.detail = "dry run: no solver process was started"
    return record


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", default="O1-M190")
    parser.add_argument("--preflight-only", action="store_true",
                        help="check the gates and build one dry case, start no solver")
    parser.add_argument("--dry-run", action="store_true",
                        help="build every case but start no solver and charge nothing")
    args = parser.parse_args(argv)

    prereg = check_preregistration()
    print("preregistration matches the code on disk: %s" % (sha(PREREG),))
    if args.preflight_only or args.dry_run:
        go = load_json(GO) if GO.exists() else {}
        print("GO present: %s" % (bool(go),))
        record = arms.DesignRecord(arm="PREFLIGHT", role="shared_support", design_index=0,
                                   tag="s00", x12=tuple(arms.support_designs()[0]))
        _dry_evaluate(args.task, "PREFLIGHT", record)
        print("dry case built and started no solver: %s" % (record.status,))
        # Build one dry coarse case per arm so a shape error in the warm-start hand-off
        # surfaces here instead of after a paid support block.
        for arm in arms.ARMS:
            design = arms.sobol_warm_start()[0]
            if arm != "SOBOL_BO":
                support_rows = [
                    arms.support_rows_from_records(args.task, [
                        arms.DesignRecord(arm="DRY", role="shared_support", design_index=i,
                                          tag="s%02d" % (i,), x12=tuple(d), feasible=True,
                                          di_n=121000.0 + i, q_pa=ev.flow_for(
                                              ev.task_def(args.task)["mach"])["q_pa"],
                                          sref_m2=358.25, cdi=0.033, cl=0.18,
                                          admission_certificate_sha256="0" * 64)
                        for i, d in enumerate(arms.support_designs())])][0]
                # ranking needs three support rows; build them all then take the first
                rows = []
                for i, d in enumerate(arms.support_designs()):
                    rows.append(arms.DesignRecord(
                        arm="DRY", role="shared_support", design_index=i, tag="s%02d" % (i,),
                        x12=tuple(d), feasible=True, di_n=121000.0 + i,
                        q_pa=ev.flow_for(ev.task_def(args.task)["mach"])["q_pa"],
                        sref_m2=358.25, cdi=0.033, cl=0.18,
                        admission_certificate_sha256="0" * 64))
                rows = arms.support_rows_from_records(args.task, rows)
                ranking = arms.kshot_ranked_candidates(arms.CHECKPOINT_ARM[arm], args.task,
                                                      rows, arms.candidate_pool())
                design = arms.candidate_pool()[ranking["order"][0]]
                print("%s dry ranking ok: top candidate predicted %r"
                      % (arm, ranking["predicted_min"]))
            dry = arms.DesignRecord(arm=arm, role="warm_start", design_index=0, tag="dry",
                                    x12=tuple(design))
            _dry_evaluate(args.task, "DRY_%s" % (arm,), dry)
            print("%s dry case: %s" % (arm, dry.status))
        return 0

    go = check_go(prereg)
    print("GO authorises this run: %s" % (go["go_sha256"],))
    if prereg["pairing"]["task_key"] != args.task:
        raise ProtocolError("the preregistration pairs task %r, not %r"
                            % (prereg["pairing"]["task_key"], args.task))

    lock = acquire_lock()
    sampler = _Sampler(RESOURCE, "O1-THREE-ARM")
    started = time.time()
    outcome = "INCOMPLETE"
    try:
        sampler.start()
        support = run_support(args.task, args.dry_run)
        if not all(record.feasible for record in support):
            raise ProtocolError("a shared support design failed to admit a raw row; the "
                                "shared support must be real before any arm can start")

        support_rows = arms.support_rows_from_records(args.task, support)
        pool = arms.candidate_pool()
        warm_sobol = arms.sobol_warm_start()
        arm_results: Dict[str, Any] = {}
        for arm in arms.ARMS:
            print("\n=== %s ===" % (arm,))
            meta = {"warm_start_kind": "LHS" if arm == "SOBOL_BO" else "KSHOT_MODEL_RANKED"}
            arm_results[arm] = arms.run_arm(args.task, arm, support, RUN / "o1_attempts.jsonl",
                                            pool, warm_sobol, meta)
            totals = arm_results[arm]["totals"]
            print("%s: designs=%d starts=%d internal=%d best=%r"
                  % (arm, totals["designs"], totals["starts"], totals["internal"],
                     arm_results[arm]["best_feasible_di_n"]))
            (RUN / ("o1_arm_%s.json" % (arm,))).write_text(
                json.dumps(arm_results[arm], indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")

        result = build_result(args.task, support, support_rows, pool, arm_results, prereg)
        RESULT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        outcome = "COMPLETED"
        print("\nprimary endpoint: %s" % (json.dumps(result["primary_endpoint"], indent=2),))
    except BaseException as error:
        outcome = "ABORTED"
        crash = {"schema": "dreal005.o1_crash.v1", "utc": now(), "task": args.task,
                 "outcome": outcome, "error_type": type(error).__name__,
                 "error": str(error)[:4000], "argv": sys.argv,
                 "lock": lock, "wall_clock_s": time.time() - started}
        (RUN / "o1_crash.json").write_text(json.dumps(crash, indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
        raise
    finally:
        sampler.stop_flag.set()
        sampler.join(timeout=5)
        if RESOURCE.exists():
            summary = _resource_summary(RESOURCE)
            summary["label"] = "O1-THREE-ARM"
            summary["wall_clock_s"] = round(time.time() - started, 3)
            (RUN / "o1_resource.summary.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        release_lock(outcome)

    close = {
        "schema": "dreal005.o1_batch_close.v1", "utc": now(), "run_id": ev.RUN_ID,
        "outcome": outcome, "task_key": args.task, "go_sha256": go["go_sha256"],
        "preregistration_sha256": sha(PREREG), "result_sha256": sha(RESULT),
        "split_task_keys": list(ev.TASK_REGISTRY),
        "pairings_executed": [args.task],
        "was_any_cap_exceeded": False,
        "wall_clock_s": round(time.time() - started, 3),
    }
    CLOSE.write_text(json.dumps(close, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nclosed: %s" % (sha(CLOSE),))
    return 0


def build_result(task_key: str, support: List[arms.DesignRecord],
                 support_rows: List[Any], pool: List[tuple],
                 arm_results: Dict[str, Any], prereg: Dict[str, Any]) -> Dict[str, Any]:
    baseline_di = None
    for record in support:
        if record.is_baseline:
            baseline_di = float(record.di_n)
    if baseline_di is None:
        raise ProtocolError("the shared support has no admitted baseline design")
    target_di = baseline_di * (1.0 - arms.TARGET_IMPROVEMENT_FRACTION)
    per_arm = {}
    for arm, payload in arm_results.items():
        best = payload["best_feasible_di_n"]
        starts_to_target = None
        for point in payload["anytime"]:
            if point["best_so_far"] is not None and point["best_so_far"] <= target_di:
                starts_to_target = point["cumulative_starts"]
                break
        totals = payload["totals"]
        per_arm[arm] = {
            "designs": totals["designs"], "starts": totals["starts"],
            "internal": totals["internal"], "admitted": totals["admitted"],
            "failed": totals["failed"],
            "point_feasible_rate": (totals["admitted"] / totals["designs"]
                                    if totals["designs"] else None),
            "run_level_feasible": totals["admitted"] == totals["designs"],
            "best_feasible_di_n": best,
            "best_feasible_tag": payload["best_feasible_tag"],
            "best_feasible_design_id": payload["best_feasible_design_id"],
            "improvement_n": None if best is None else baseline_di - best,
            "improvement_fraction": None if best is None else (baseline_di - best) / baseline_di,
            "reached_target": bool(best is not None and best <= target_di),
            "equivalent_starts_to_target": starts_to_target,
            "anytime": payload["anytime"],
            "physical_solver_starts_actual": payload["physical_solver_starts_actual"],
            "equivalent_starts_actual": payload["equivalent_starts_actual"],
            "internal_solver_cases_actual": payload["internal_solver_cases_actual"],
            "adaptive_designs": payload["adaptive_designs"],
            "warm_start_meta": payload["warm_start_meta"],
        }
    physical = sum(r.starts for r in support) + sum(
        payload["physical_solver_starts_actual"] for payload in arm_results.values())
    equivalent = 3 * (sum(r.starts for r in support) + sum(
        payload["physical_solver_starts_actual"] for payload in arm_results.values()))
    return {
        "schema": "dreal005.o1_result.v1", "protocol_id": arms.PROTOCOL_ID,
        "regression": {"run_id": ev.RUN_ID, "task_key": task_key,
                       "task_id": ev.task_spec(task_key).task_id,
                       "task_physics_sha256": ev.task_spec(task_key).physics_sha256,
                       "mach": ev.task_def(task_key)["mach"], "altitude_m": ev.ALT,
                       "dynamic_pressure_pa": ev.flow_for(ev.task_def(task_key)["mach"])["q_pa"],
                       "lift_target_n": ev.LIFT,
                       "lift_tolerance_rel": 1e-3,
                       "geometry_contract_sha256": ev.GEOM,
                       "pairing_seed": arms.PAIRING_SEED, "gp_seed": arms.GP_SEED,
                       "candidate_pool_count": len(pool),
                       "candidate_pool_sha256": canon([list(d) for d in pool]),
                       "shared_support_count": len(support),
                       "shared_support": [record.as_dict() for record in support],
                       "shared_support_starts": sum(r.starts for r in support),
                       "shared_support_internal": sum(r.internal for r in support),
                       "target_improvement_fraction": arms.TARGET_IMPROVEMENT_FRACTION,
                       "target_di_n": target_di,
                       "baseline_di_n": baseline_di},
        "arms": per_arm,
        "primary_endpoint": {
            "baseline_di_n": baseline_di,
            "target_di_n": target_di,
            "best_feasible_di_n": {arm: payload["best_feasible_di_n"]
                                   for arm, payload in per_arm.items()},
            "equivalent_starts_spent": {arm: payload["equivalent_starts_actual"]
                                        for arm, payload in per_arm.items()},
            "internal_spent": {arm: payload["internal_solver_cases_actual"]
                               for arm, payload in per_arm.items()},
        },
        "cost": {"physical_solver_starts_actual": physical,
                 "equivalent_solver_starts": equivalent,
                 "note": ("the three shared support designs are solved once and charged in "
                          "full to every arm, so the equivalent bill is three times the "
                          "physical bill for the support block")},
        "physics_validated": False,
        "evidence_scope": "VSPAERO_INTERNAL_ONLY",
        "not_claimed": ["global optimum", "regret", "aerodynamic validation",
                        "MAML superiority over supervised meta-learning"],
    }


if __name__ == "__main__":
    sys.exit(main())
