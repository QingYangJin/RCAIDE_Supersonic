
"""P1 real adaptive-alpha batch driver (Issue #14). Starts at most 12 real solver starts.

Requires: p1_preregistration.json, p1_a5_dossier.md, a5_review/verdict.json with
P1_PROTOCOL_AND_CODE_REVIEW_PASS, and p1_go_record.json binding those hashes.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math, os, re, shutil, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P1-20261122-02")
G2 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
PY = Path(r"D:/Anaconda/envs/RCAIDE/python.exe")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry  # noqa: E402
from research.concorde_metaopt.dreal001.geometry import openvsp_model, solver_runner as sr  # noqa: E402
from research.concorde_metaopt.dreal001.geometry.polar_rows import read_polar_rows  # noqa: E402
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec  # noqa: E402

RUN_ID = "DRECOVER001-P1-20261122-02"
BATCH_ID = "DRECOVER001-P1-20261122-02-B01"
AUTH = "AUTH-DREAL004-P1-20261122-01"
WINDOW_END = "2026-11-24T00:00:00Z"
GEOM = "5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15"
LIFT = 1333704.4
ALT = 18288.0
BASE_MACH = 2.02
BASE_VINF = 596.0373972278921
BASE_RHO = 0.1153178340089936
BASE_RECREF = 89397005.8767656
EXE = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe")
AUDIT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")
ADMIT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/scripts/admit_g1_case.py")
MAX_STARTS = 12
MAX_PER_DESIGN = 3
MAX_INTERNAL = 36
WALL_MAX = 3600.0
HALF_WIDTHS = [0.004, 0.002, 0.001]
brackets_cache = []

NAMES = ["wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3", "span_location_2",
         "span_location_3", "chord_ratio_2", "chord_ratio_3", "tip_twist",
         "vertical_tail_area", "vertical_tail_sweep_delta", "fuselage_length",
         "fuselage_fineness", "fuselage_height_width_ratio"]
BASELINE = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0,
            33.91, 0.0, 61.66, 4.30, 1.152778]
DES = {k: BASELINE[:] for k in ("d00", "d01", "d04", "d07")}
DES["d01"][0] = 361.8325
DES["d04"][2] = 66.5
DES["d07"][12] = 62.2766


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def canon(p) -> str:
    return hashlib.sha256(json.dumps(p, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def flow_for(mach: float):
    vinf = mach * (BASE_VINF / BASE_MACH)
    recref = BASE_RECREF * (vinf / BASE_VINF)
    q = 0.5 * BASE_RHO * vinf * vinf
    return vinf, recref, q


def gate_check(prereg) -> None:
    dossier = RUN / "p1_a5_dossier.md"
    verdict_p = RUN / "a5_review" / "verdict.json"
    go_p = RUN / "p1_go_record.json"
    for p in (dossier, verdict_p, go_p):
        if not p.exists():
            raise SystemExit("MISSING_GATE_FILE " + str(p))
    v = read_json(verdict_p)
    if v.get("verdict") != "P1_PROTOCOL_AND_CODE_REVIEW_PASS":
        raise SystemExit("A5 verdict is not PASS: %r" % v.get("verdict"))
    if v.get("dossier_sha256") != sha(dossier):
        raise SystemExit("A5 dossier sha mismatch")
    go = read_json(go_p)
    if go.get("a5_verdict_sha256") != sha(verdict_p):
        raise SystemExit("GO/A5 verdict mismatch")
    if go.get("a5_dossier_sha256") != sha(dossier):
        raise SystemExit("GO/dossier mismatch")
    if go.get("preregistration_sha256") != sha(RUN / "p1_preregistration.json"):
        raise SystemExit("GO/prereg mismatch")
    if not go.get("go_issued") or go.get("authorization_id") != AUTH:
        raise SystemExit("GO record invalid")
    script_map = {"scripts/p1_run.py": RUN / "scripts" / "p1_run.py",
                  "scripts/audit_real_case.py": AUDIT,
                  "scripts/admit_g1_case.py": ADMIT}
    for rel, want in prereg["code_shas"].items():
        p = script_map.get(rel) or (REPO / rel)
        if not p.exists():
            raise SystemExit("code file missing " + str(p))
        if sha(p) != want:
            raise SystemExit("code sha drift for " + rel)


def bracket_from_rows(rows, clt):
    rows = sorted(rows, key=lambda r: r[0])
    for (a1, c1), (a2, c2) in zip(rows, rows[1:]):
        if c1 <= clt <= c2:
            slope = (c2 - c1) / (a2 - a1)
            return a1, c1, a2, c2, slope
    return None


def make_case(design: str, rnd: int, alphas, alpha_center, cl_target, sref, q, split, partition):
    case_id = "p1-m202-%s-r%d" % (design, rnd)
    case_dir = RUN / "cases" / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    vals = DES[design][:]
    x12 = vals[:12]
    geom = build_geometry(NAMES, vals)
    sref_geom = float(geom.wing.area_m2)
    if abs(sref_geom - float(sref)) > 1e-6 * max(1.0, abs(sref_geom)):
        raise SystemExit("prereg sref disagrees with geometry for %s: %r vs %r" % (design, sref, sref_geom))
    sref = sref_geom
    vinf, recref, _q = flow_for(2.02)
    flow = {"vinf_m_s": vinf, "rho_kg_m3": BASE_RHO, "recref": recref}
    openvsp_model.prepare_case(geom, case_dir, case_id, geometry_set="thin", alphas_deg=alphas,
                               tess_u=12, tess_w=25, n_wake_nodes=8, mach_values=[2.02],
                               flow_conditions=flow)
    vspgeom = case_dir / (case_id + ".vspgeom")
    vkey = case_dir / (case_id + ".vkey")
    vspaero = case_dir / (case_id + ".vspaero")
    design_id = canon(x12)
    plan = {"schema": "dreal001.solver_plan.v1", "run_id": RUN_ID, "batch_id": BATCH_ID,
            "task_id": "DREAL004-M202", "case_id": case_id,
            "purpose": "D-REAL-EXP-002 P1 adaptive alpha round %d; design %s %s" % (rnd, design, partition),
            "solver": {"path": str(EXE), "sha256": sha(EXE), "cwd": str(case_dir),
                       "version_banner": openvsp_model.EXPECTED_VSPAERO_VERSION, "omp_threads": 1,
                       "timeout_s": 600, "solver_config_hash": sha(vspaero)},
            "command": {"argv": [str(EXE), "-omp", "1", case_id]},
            "geometry": {"files": {"vspgeom": {"path": str(vspgeom), "sha256": sha(vspgeom)},
                                   "vkey": {"path": str(vkey), "sha256": sha(vkey)},
                                   "vspaero": {"path": str(vspaero), "sha256": sha(vspaero)}},
                         "sref_m2": sref, "geometry_sha256": sha(vspgeom), "design_hash": design_id},
            "design": {"design_hash": design_id, "x12": x12},
            "budget": {"physical_solver_starts_max": 1, "expected_internal_cases": len(alphas),
                       "max_internal_cases": 16}}
    pb = json.dumps(plan, indent=2, ensure_ascii=False).encode() + b"\n"
    (case_dir / "plan.json").write_bytes(pb)
    t = datetime.now(timezone.utc)
    approval = {"schema": "dreal001.solver_approval.v1", "approved": True,
                "authorization_id": AUTH, "owner_message_ref": "m10191 批准真实评估",
                "run_id": RUN_ID, "batch_id": BATCH_ID, "case_id": case_id,
                "plan_sha256": hashlib.sha256(pb).hexdigest(), "max_starts": 1,
                "window": {"start_utc": (t - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "end_utc": WINDOW_END, "token": AUTH + "-WINDOW"},
                "window_token": AUTH + "-WINDOW"}
    (case_dir / "approval.json").write_text(json.dumps(approval, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    task = TaskSpec(task_id="DREAL004-M202", split=split, mach=2.02, altitude_m=ALT,
                    dynamic_pressure_pa=q, lift_target_n=LIFT, geometry_contract_sha256=GEOM,
                    lift_tolerance_rel=1e-3)
    spec = {"schema": "dreal001.r2_task_spec.v1", "task_id": "DREAL004-M202", "split": split,
            "partition": partition, "case_id": case_id, "design": design, "design_id": design_id,
            "x12": x12, "mach": 2.02, "altitude_m": ALT, "dynamic_pressure_pa": q,
            "lift_target_n": LIFT, "geometry_contract_sha256": GEOM, "lift_tolerance_rel": 1e-3,
            "flow_conditions": flow, "alpha_center_deg": alpha_center, "alpha_grid_deg": alphas,
            "cl_target": cl_target, "sref_m2": sref, "task_physics_sha256": task.physics_sha256,
            "stage": "p1_adaptive", "round": rnd}
    (case_dir / "task_spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    return case_id, case_dir, alphas


def internal_count(case_dir: Path):
    """Count independent internal solver cases for a finished case: alpha rows in the polar."""
    try:
        polar = next(case_dir.glob("*.polar"))
        rows = read_polar_rows(polar, mach=2.02)
        return len(rows) if rows else None
    except Exception:  # noqa: BLE001
        return None


def run_and_admit(case_id, case_dir, partition, split, timeout):
    attempt = "p1-" + case_id + "-01"
    t0 = time.time()
    try:
        r = sr.run_case(str(case_dir / "plan.json"), str(case_dir / "approval.json"),
                        attempt, dry_run=False, timeout_s=timeout)
    except Exception as e:  # noqa: BLE001
        r = {"status": "EXCEPTION", "error": type(e).__name__ + ": " + str(e)[:800],
             "physical_solver_starts": 0}
    wall = time.time() - t0
    proc = r.get("process") or {}
    res = case_dir / "case_result.json"
    internal = None
    started_utc = None
    if res.exists():
        try:
            cr = read_json(res)
            internal = cr.get("internal_solver_cases") or internal_count(case_dir)
            attempt_rec = cr.get("attempt") or {}
            started_utc = attempt_rec.get("start_ts_utc") or attempt_rec.get("ts_utc")
        except Exception:  # noqa: BLE001
            internal = None
    row = {"case_id": case_id, "attempt_id": attempt, "status": r.get("status"),
           "exit_code": proc.get("exit_code"), "timed_out": proc.get("timed_out"),
           "wall_s": round(wall, 3), "physical_solver_starts": r.get("physical_solver_starts"),
           "internal_solver_cases": internal if internal is not None else (r.get("internal") or {}).get("count"),
           "solver_started_utc": started_utc,
           "case_result": str(res) if res.exists() else None, "error": r.get("error")}
    return row


def best_match(case_dir, clt) -> dict | None:
    try:
        polar = next(case_dir.glob("*.polar"))
        rows = read_polar_rows(polar, mach=2.02)
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__ + ": " + str(e)[:300]}
    if not rows:
        return None
    scored = sorted(((abs(r.cl - clt) / clt, r.alpha_deg, r.cl, r.cdi) for r in rows))
    err, a, cl, cdi = scored[0]
    return {"rel_error": err, "alpha_deg": a, "cl": cl, "cdi": cdi,
            "rows": [(r.alpha_deg, r.cl) for r in rows]}


def admit(case_dir: Path, case_id: str, partition: str, split: str):
    audit_id = "p1-audit-" + case_id
    p = subprocess.run([str(PY), str(AUDIT), "--case-dir", str(case_dir),
                        "--audit-id", audit_id, "--reviewer", "lead-local-script",
                        "--reviewer-role", "SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5",
                        "--created-utc", now(), "--verdict", "ADMIT_REAL_LABEL"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if p.returncode != 0:
        return {"admitted": False, "stage": "AUDIT_FAILED", "detail": (p.stdout + p.stderr)[-600:]}
    result = read_json(case_dir / "case_result.json")
    started = (result.get("attempt") or {}).get("start_ts_utc") or (result.get("attempt") or {}).get("ts_utc") or now()
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", str(started))
    if m:
        started = m.group(1) + "Z"
    else:
        started = now()
    q = subprocess.run([str(PY), str(ADMIT), "--case-dir", str(case_dir),
                        "--admission-id", "p1-adm-" + case_id, "--audit-ref", audit_id,
                        "--evaluator-id", "vspaero-3.55.0-v7.2.2-omp1",
                        "--solver-started-utc", started, "--partition", partition,
                        "--split", split, "--task-spec", str(case_dir / "task_spec.json")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if q.returncode != 0:
        return {"admitted": False, "stage": "ADMIT_FAILED", "detail": (q.stdout + q.stderr)[-600:]}
    cert = read_json(case_dir / "admission_certificate.json")
    return {"admitted": True, "certificate": cert,
            "admission_manifest_sha256": sha(case_dir / "admission_manifest.json"),
            "certificate_sha256": sha(case_dir / "admission_certificate.json"),
            "audit_sha256": sha(case_dir / "audit.json")}


def upload(label: str, starts: int) -> bool:
    p = subprocess.run([str(PY), str(RUN / "scripts" / "p1_upload.py"), "--label", label,
                        "--total-starts", str(starts)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200)
    print("UPLOAD", label, "rc", p.returncode, flush=True)
    print((p.stdout or "")[-2500:], flush=True)
    if p.returncode != 0:
        print((p.stderr or "")[-1500:], flush=True)
    return p.returncode == 0


def backfill_internal(state) -> None:
    """Recover internal-case counts for rows recorded before the counter was wired."""
    for r in state["runs"]:
        if not r.get("internal_solver_cases"):
            cd = RUN / "cases" / r["case_id"]
            if cd.exists():
                n = internal_count(cd)
                if n:
                    r["internal_solver_cases"] = n


def write_tables(state) -> None:
    backfill_internal(state)
    tdir = RUN / "tables"
    tdir.mkdir(exist_ok=True)
    runs = state["runs"]
    fields = ["design", "round", "case_id", "status", "wall_s", "internal_solver_cases",
              "physical_solver_starts", "exit_code", "timed_out", "match_rel_error",
              "matched_alpha_deg", "matched_cl", "admitted", "failure_kind", "detail"]
    with (tdir / "p1_attempt_ledger.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in runs:
            w.writerow(r)
    hist = []
    for r in runs:
        for a, cl in (r.get("observed_rows") or []):
            hist.append({"design": r["design"], "round": r["round"], "case_id": r["case_id"],
                         "alpha_deg": a, "cl": cl})
    with (tdir / "p1_alpha_refinement_history.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["design", "round", "case_id", "alpha_deg", "cl"])
        w.writeheader()
        for h in hist:
            w.writerow(h)
    rows_admitted = [r for r in runs if r.get("admitted")]
    adm, seen_adm = [], set()
    for r in rows_admitted:
        aid = r.get("admission_id") or r["case_id"]
        if aid in seen_adm:
            continue
        seen_adm.add(aid)
        adm.append(dict(r, rel_error=r.get("match_rel_error")))
    with (tdir / "p1_admitted_labels.csv").open("w", encoding="utf-8", newline="") as fh:
        fl = ["design", "case_id", "round", "di_n", "q_pa", "sref_m2", "cl_target", "matched_alpha_deg",
              "matched_cl", "rel_error", "admission_id", "design_sha256", "raw_sha256", "artifact_sha256"]
        w = csv.DictWriter(fh, fieldnames=fl, extrasaction="ignore")
        w.writeheader()
        for r in adm:
            w.writerow(r)
    nulls = [r for r in runs if not r.get("admitted")]
    with (tdir / "p1_failed_or_null.csv").open("w", encoding="utf-8", newline="") as fh:
        fl = ["design", "round", "case_id", "status", "failure_kind", "detail", "match_rel_error"]
        w = csv.DictWriter(fh, fieldnames=fl, extrasaction="ignore")
        w.writeheader()
        for r in nulls:
            w.writerow(r)
    starts = sum(1 for r in runs if r.get("physical_solver_starts") == 1)
    internal = sum(int(r.get("internal_solver_cases") or 0) for r in runs)
    acc = {"schema": "dreal004.p1_accounting.v1", "run_id": RUN_ID, "batch_id": BATCH_ID,
           "authorization_id": AUTH, "owner_instruction_ref": "m10191 批准真实评估",
           "physical_solver_starts_actual": starts,
           "physical_solver_starts_completed": sum(1 for r in runs if r["status"] == "SOLVED"),
           "internal_solver_cases_actual": internal, "retries_actual": 0, "parallelism": 1,
           "admitted_labels": len(adm), "admitted_rows": len(rows_admitted),
           "unique_admission_certificates": len({r.get("admission_id") for r in rows_admitted}),
           "duplicate_attempt_rows": sorted({r["case_id"] for r in runs
                                             if sum(1 for x in runs if x["case_id"] == r["case_id"]) > 1}),
           "null_labels": len(nulls),
           "designs_hit": sorted({r["design"] for r in adm}),
           "valid_label_rate_over_completed": (len(adm) / max(1, sum(1 for r in runs if r["status"] == "SOLVED"))),
           "max_starts": MAX_STARTS, "max_starts_per_design": MAX_PER_DESIGN,
           "max_internal_solver_cases": MAX_INTERNAL,
           "fixed_sweep_internal_baseline": 4 * 49,
           "internal_saved_vs_fixed_sweep": 4 * 49 - internal,
           "wall_clock_s": round(sum(r.get("wall_s") or 0 for r in runs), 3),
           "stops": state.get("stops", []), "runs": runs, "generated_utc": now()}
    write_json(RUN / "p1_accounting.json", acc)
    write_json(tdir / "p1_accounting_copy.json", acc)
    # Explicit aliases required by the dossier and the upload package, plus root copies
    # of the table files so they are visible outside tables/ as well.
    all_ev = {"schema": "dreal004.p1_all_evaluations.v1", "run_id": RUN_ID,
              "note": "one row per charged solver start; null rows keep null objective",
              "rows": runs}
    write_json(tdir / "all_evaluations.json", all_ev)
    write_json(RUN / "all_evaluations.json", all_ev)
    ledger_rows = [{"case_id": r["case_id"], "design": r["design"], "round": r["round"],
                    "physical_solver_starts": r.get("physical_solver_starts"),
                    "internal_solver_cases": r.get("internal_solver_cases"),
                    "wall_s": r.get("wall_s"), "status": r.get("status"),
                    "admitted": bool(r.get("admitted")), "failure_kind": r.get("failure_kind")}
                   for r in runs]
    with (tdir / "actual_solver_ledger.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "design", "round", "physical_solver_starts",
                                           "internal_solver_cases", "wall_s", "status", "admitted",
                                           "failure_kind"])
        w.writeheader()
        for r in ledger_rows:
            w.writerow(r)
    for name in ("p1_attempt_ledger.csv", "p1_alpha_refinement_history.csv", "p1_admitted_labels.csv",
                 "p1_failed_or_null.csv", "actual_solver_ledger.csv"):
        src = tdir / name
        if src.exists():
            shutil.copy2(src, RUN / name)


def acquire_lock(force: bool) -> Path:
    """Prevent two driver processes from overlapping (each would double-spend starts)."""
    lock = RUN / "p1_run.lock"
    if lock.exists() and not force:
        age = time.time() - lock.stat().st_mtime
        if age < 7200:
            raise SystemExit("LOCK_HELD: %s age %.1fs; use --force only if no driver is running" % (lock, age))
    lock.write_text("%d %s\n" % (os.getpid(), now()), encoding="utf-8")
    return lock


def recover_pending_admissions(state) -> int:
    """Admit already-solved cases whose admission step failed, without any new solver start."""
    fixed = 0
    for row in state["runs"]:
        if row.get("admitted") or row.get("status") != "SOLVED":
            continue
        if row.get("failure_kind") not in ("ADMIT_FAILED", "AUDIT_FAILED", None):
            continue
        design_admitted = sum(1 for r in state["runs"]
                              if r.get("design") == row.get("design") and r.get("admitted"))
        if design_admitted >= MAX_PER_DESIGN:
            continue
        case_dir = RUN / "cases" / row["case_id"]
        if not case_dir.exists():
            continue
        b = next(x for x in brackets_cache if x["design"] == row["design"])
        clt = float(b["cl_target"])
        rm = best_match(case_dir, clt)
        if not rm or "error" in rm or rm.get("rel_error") is None or rm["rel_error"] > 1e-3:
            continue
        res = admit(case_dir, row["case_id"], b["partition"], "train")
        if not res.get("admitted"):
            row["failure_kind"] = res.get("stage")
            row["detail"] = res.get("detail")
            continue
        cert = res["certificate"]
        row.update(admitted=True, admission_id=cert.get("admission_id"), di_n=cert.get("di_n"),
                   q_pa=cert.get("q_pa"), sref_m2=cert.get("sref_m2"), cl_target=clt,
                   matched_alpha_deg=rm["alpha_deg"], matched_cl=rm["cl"], match_rel_error=rm["rel_error"],
                   design_sha256=cert.get("design_sha256"), raw_sha256=cert.get("raw_sha256"),
                   artifact_sha256=cert.get("artifact_sha256"),
                   admission_manifest_sha256=res.get("admission_manifest_sha256"),
                   certificate_sha256=res.get("certificate_sha256"), audit_sha256=res.get("audit_sha256"),
                   failure_kind=None, detail=None)
        state["designs"][row["design"]]["status"] = "HIT"
        fixed += 1
        print("READMITTED", row["case_id"], "di_n", row.get("di_n"), flush=True)
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore a stale run lock")
    a = ap.parse_args()
    prereg = read_json(RUN / "p1_preregistration.json")
    gate_check(prereg)
    state_p = RUN / "p1_state.json"
    if state_p.exists():
        state = read_json(state_p)
    else:
        state = {"schema": "dreal004.p1_state.v1", "runs": [], "stops": [],
                 "designs": {d: {"starts": 0, "status": "PENDING"} for d in ("d00", "d01", "d04", "d07")}}
    brackets = {b["design"]: b for b in prereg["designs"]}
    global brackets_cache
    brackets_cache = prereg["designs"]
    starts = sum(1 for r in state["runs"] if r.get("physical_solver_starts") == 1)
    internal = sum(int(r.get("internal_solver_cases") or 0) for r in state["runs"])
    wall = sum(r.get("wall_s") or 0 for r in state["runs"])
    consecutive = 0
    for r in reversed(state["runs"]):
        if r["status"] == "SOLVED" and r.get("physical_solver_starts") == 1:
            break
        consecutive += 1
        if consecutive >= 2:
            break
    if a.dry_run:
        print(json.dumps({"dry_run": True, "starts": starts, "internal": internal,
                          "wall": wall, "designs": state["designs"]}, ensure_ascii=False, indent=2))
        return 0
    lock = acquire_lock(a.force)
    try:
        fixed = recover_pending_admissions(state)
    finally:
        pass
    if fixed:
        write_json(state_p, state)
        write_tables(state)
        starts = sum(1 for r in state["runs"] if r.get("physical_solver_starts") == 1)
        internal = sum(int(r.get("internal_solver_cases") or 0) for r in state["runs"])
        wall = sum(r.get("wall_s") or 0 for r in state["runs"])
        print("RECOVERED_ADMISSIONS", fixed, flush=True)
    if internal + 3 > MAX_INTERNAL and any(state["designs"][d]["status"] == "PENDING" for d in state["designs"]):
        state["stops"].append({"reason": "MAX_INTERNAL", "internal": internal})
        write_json(state_p, state)
        write_tables(state)
        lock.unlink(missing_ok=True)
        return 8
    for design in ("d00", "d01", "d04", "d07"):
        dstate = state["designs"][design]
        if dstate["status"] in ("HIT", "NO_RAW_POINT", "NO_BRACKET"):
            continue
        b = brackets[design]
        clt = float(b["cl_target"])
        sref = float(b["sref_m2"])
        q = float(b["q_pa"])
        split = "train"
        partition = b["partition"]
        coarse_rows = read_polar_rows(Path(b["coarse_polar_path"]), mach=2.02)
        observed = [(r.alpha_deg, r.cl) for r in coarse_rows]
        dstate["status"] = "RUNNING"
        for rnd in range(1, MAX_PER_DESIGN + 1):
            if dstate["starts"] >= MAX_PER_DESIGN:
                dstate["status"] = "NO_RAW_POINT"
                state["stops"].append({"design": design, "reason": "MAX_PER_DESIGN", "round": rnd})
                break
            if starts >= MAX_STARTS:
                state["stops"].append({"design": design, "reason": "MAX_STARTS", "round": rnd})
                break
            if wall + 600 > WALL_MAX:
                state["stops"].append({"design": design, "reason": "WALL_STOP", "round": rnd})
                break
            if internal + 3 > MAX_INTERNAL:
                state["stops"].append({"design": design, "reason": "MAX_INTERNAL", "round": rnd})
                break
            if consecutive >= 2:
                state["stops"].append({"design": design, "reason": "CONSECUTIVE_FAILURE", "round": rnd})
                break
            br = bracket_from_rows(observed, clt)
            if br is None:
                dstate["status"] = "NO_BRACKET"
                state["stops"].append({"design": design, "reason": "NO_BRACKET", "round": rnd})
                break
            a1, c1, a2, c2, slope = br
            a_t = a1 + (clt - c1) / slope
            half = HALF_WIDTHS[min(rnd - 1, len(HALF_WIDTHS) - 1)]
            # VSPAEROSweep can only encode an arithmetic alpha list, so build the three probes as
            # an exact arithmetic triple in integer micro-degrees, clipped inside the raw bracket.
            lo_deg, hi_deg = min(a1, a2), max(a1, a2)
            lo_m = int(math.ceil((lo_deg + 1e-6) * 1e6))
            hi_m = int(math.floor((hi_deg - 1e-6) * 1e6))
            if hi_m - lo_m < 2:
                state["stops"].append({"design": design, "reason": "BRACKET_TOO_NARROW", "round": rnd})
                dstate["status"] = "NO_BRACKET"
                break
            half_m = max(1, min(int(round(half * 1e6)), (hi_m - lo_m) // 2))
            center_m = min(max(int(round(a_t * 1e6)), lo_m + half_m), hi_m - half_m)
            alphas = [(center_m - half_m) / 1e6, center_m / 1e6, (center_m + half_m) / 1e6]
            a_t = center_m / 1e6
            case_id, case_dir, alphas = make_case(design, rnd, alphas, a_t, clt, sref, q, split, partition)
            timeout = min(600.0, max(1.0, WALL_MAX - wall))
            row = run_and_admit(case_id, case_dir, partition, split, timeout)
            row["design"] = design
            row["round"] = rnd
            row["alphas"] = alphas
            rm = best_match(case_dir, clt) if row["status"] == "SOLVED" else None
            row["observed_rows"] = (rm or {}).get("rows") or []
            row["match_rel_error"] = (rm or {}).get("rel_error")
            row["matched_alpha_deg"] = (rm or {}).get("alpha_deg")
            row["matched_cl"] = (rm or {}).get("cl")
            starts += 1 if row.get("physical_solver_starts") == 1 else 0
            internal += int(row.get("internal_solver_cases") or 0)
            wall += row.get("wall_s") or 0
            dstate["starts"] += 1
            if row["status"] == "SOLVED" and row.get("physical_solver_starts") == 1:
                consecutive = 0
            else:
                consecutive += 1
            if row["status"] == "SOLVED" and rm and "error" not in rm and rm.get("rel_error") is not None:
                if rm["rel_error"] <= 1e-3:
                    res = admit(case_dir, case_id, partition, split)
                    if res.get("admitted"):
                        cert = res["certificate"]
                        row.update(admitted=True, admission_id=cert.get("admission_id"),
                                   di_n=cert.get("di_n"), q_pa=cert.get("q_pa"),
                                   sref_m2=cert.get("sref_m2"),
                                   cl_target=clt, design_sha256=cert.get("design_sha256"),
                                   raw_sha256=cert.get("raw_sha256"),
                                   artifact_sha256=cert.get("artifact_sha256"),
                                   admission_manifest_sha256=res.get("admission_manifest_sha256"),
                                   certificate_sha256=res.get("certificate_sha256"),
                                   audit_sha256=res.get("audit_sha256"))
                        row["failure_kind"] = None
                        dstate["status"] = "HIT"
                        observed.extend(rm["rows"])
                        state["runs"].append(row)
                        write_json(state_p, state)
                        write_tables(state)
                        print("ADMITTED", case_id, "di_n", row.get("di_n"), "internal", row.get("internal_solver_cases"), flush=True)
                        break
                    row["failure_kind"] = res.get("stage")
                    row["detail"] = res.get("detail")
                else:
                    row["failure_kind"] = "RAW_ROW_OUTSIDE_LIFT_TOLERANCE"
                    row["detail"] = "best rel error %.6e > 1e-3" % rm["rel_error"]
            elif row["status"] != "SOLVED":
                row["failure_kind"] = "SOLVER_" + str(row["status"])
                row["detail"] = row.get("error")
            else:
                row["failure_kind"] = "POLAR_UNREADABLE"
            observed.extend(rm["rows"] if (rm and "error" not in rm) else [])
            state["runs"].append(row)
            write_json(state_p, state)
            write_tables(state)
            print("RAN", json.dumps({k: row.get(k) for k in ("case_id", "status", "wall_s",
                  "internal_solver_cases", "match_rel_error", "failure_kind")}, ensure_ascii=False), flush=True)
            if starts > 0 and starts % 4 == 0 and not a.no_upload:
                if not upload("P1-B%02d" % (starts // 4), starts):
                    state["stops"].append({"design": design, "reason": "UPLOAD_READBACK_FAILED", "round": rnd})
                    write_json(state_p, state)
                    write_tables(state)
                    lock.unlink(missing_ok=True)
                    return 6
            if row["status"] == "REFUSED" or row["status"] == "EXCEPTION":
                state["stops"].append({"design": design, "reason": "SOLVER_REFUSED_OR_EXCEPTION", "round": rnd})
                write_json(state_p, state)
                write_tables(state)
                lock.unlink(missing_ok=True)
                return 7
        if dstate["status"] == "RUNNING":
            dstate["status"] = "NO_RAW_POINT"
        write_json(state_p, state)
        write_tables(state)
    state["final"] = {"starts": sum(1 for r in state["runs"] if r.get("physical_solver_starts") == 1),
                      "internal": sum(int(r.get("internal_solver_cases") or 0) for r in state["runs"]),
                      "admitted": sum(1 for r in state["runs"] if r.get("admitted")),
                      "completed_utc": now()}
    write_json(state_p, state)
    write_tables(state)
    if not a.no_upload:
        upload("P1-FINAL", state["final"]["starts"])
    lock.unlink(missing_ok=True)
    print("DONE", json.dumps(state["final"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
