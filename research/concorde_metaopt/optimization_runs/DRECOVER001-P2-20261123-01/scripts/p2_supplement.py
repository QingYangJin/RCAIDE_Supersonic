
"""P2 supplement batch driver (Issue #14 P2). Hard cap: 16 real solver starts.

Gate: p2_preregistration.json + p2_a5_dossier.md + a5_review/verdict.json
(P2_PROTOCOL_AND_CODE_REVIEW_PASS) + p2_go_record.json binding those hashes.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
PY = Path(r"D:/Anaconda/envs/RCAIDE/python.exe")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry  # noqa: E402
from research.concorde_metaopt.dreal001.geometry import openvsp_model, solver_runner as sr  # noqa: E402
from research.concorde_metaopt.dreal001.geometry.polar_rows import read_polar_rows  # noqa: E402
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec  # noqa: E402

RUN_ID = "DRECOVER001-P2-20261123-01"
BATCH_ID = "DRECOVER001-P2-20261123-01-B01"
AUTH = "AUTH-DREAL004-P2-20261123-01"
WINDOW_END = "2026-11-25T00:00:00Z"
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
MAX_STARTS = 16
MAX_INTERNAL = 48
WALL_MAX = 9600.0
UPLOAD_EVERY = 8
NAMES = ["wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3", "span_location_2",
         "span_location_3", "chord_ratio_2", "chord_ratio_3", "tip_twist",
         "vertical_tail_area", "vertical_tail_sweep_delta", "fuselage_length",
         "fuselage_fineness", "fuselage_height_width_ratio"]
BASELINE = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0,
            33.91, 0.0, 61.66, 4.30, 1.152778]
DES = {k: BASELINE[:] for k in ("d00", "d01", "d02", "d03")}
DES["d01"][0] = 361.8325
DES["d02"][2] = 67.5
DES["d03"][0] = 354.6675


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


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
    dossier = RUN / "p2_a5_dossier.md"
    verdict_p = RUN / "a5_review" / "verdict.json"
    go_p = RUN / "p2_go_record.json"
    for p in (dossier, verdict_p, go_p):
        if not p.exists():
            raise SystemExit("MISSING_GATE_FILE " + str(p))
    v = read_json(verdict_p)
    if v.get("verdict") != "P2_PROTOCOL_AND_CODE_REVIEW_PASS":
        raise SystemExit("A5 verdict is not PASS: %r" % v.get("verdict"))
    if v.get("dossier_sha256") != sha(dossier):
        raise SystemExit("A5 dossier sha mismatch")
    go = read_json(go_p)
    if go.get("a5_verdict_sha256") != sha(verdict_p):
        raise SystemExit("GO/A5 verdict mismatch")
    if go.get("a5_dossier_sha256") != sha(dossier):
        raise SystemExit("GO/dossier mismatch")
    if go.get("preregistration_sha256") != sha(RUN / "p2_preregistration.json"):
        raise SystemExit("GO/prereg mismatch")
    if not go.get("go_issued") or go.get("authorization_id") != AUTH:
        raise SystemExit("GO record invalid")
    code_shas = prereg.get("code_shas") or prereg["source_code_sha256"]
    script_map = {rel: RUN / "scripts" / Path(rel).name for rel in code_shas
                  if rel.startswith("scripts/p2_")}
    script_map.update({"scripts/audit_real_case.py": AUDIT,
                       "scripts/admit_g1_case.py": ADMIT})
    for rel, want in code_shas.items():
        p = script_map.get(rel) or (REPO / rel)
        if not p.exists():
            raise SystemExit("code file missing " + str(p))
        if sha(p) != want:
            raise SystemExit("code sha drift for " + rel)


def make_case(item: dict) -> tuple[Path, str]:
    mach = item["mach"] / 100.0
    tag = item["tag"]
    design = item["design"]
    case_id = "p2-%s-%s" % (tag, design)
    case_dir = RUN / "cases" / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    vals = DES[design][:]
    x12 = vals[:12]
    geom = build_geometry(NAMES, vals)
    sref = float(geom.wing.area_m2)
    if abs(sref - float(item["sref_m2"])) > 1e-6 * max(1.0, abs(sref)):
        raise SystemExit("plan sref disagrees with geometry for %s: %r vs %r"
                         % (case_id, item["sref_m2"], sref))
    vinf, recref, _q = flow_for(mach)
    flow = {"vinf_m_s": vinf, "rho_kg_m3": BASE_RHO, "recref": recref}
    alphas = item["alpha_grid_deg"]
    openvsp_model.prepare_case(geom, case_dir, case_id, geometry_set="thin", alphas_deg=alphas,
                               tess_u=12, tess_w=25, n_wake_nodes=8, mach_values=[mach],
                               flow_conditions=flow)
    vspgeom = case_dir / (case_id + ".vspgeom")
    vkey = case_dir / (case_id + ".vkey")
    vspaero = case_dir / (case_id + ".vspaero")
    design_id = hashlib.sha256(json.dumps(x12, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    plan = {"schema": "dreal001.solver_plan.v1", "run_id": RUN_ID, "batch_id": BATCH_ID,
            "task_id": item["task_id"], "case_id": case_id,
            "purpose": ("D-REAL-EXP-002 P2 supplement; task %s design %s %s"
                        % (item["task_id"], design, item["partition"])),
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
                       "max_internal_cases": 4}}
    pb = json.dumps(plan, indent=2, ensure_ascii=False).encode() + b"\n"
    (case_dir / "plan.json").write_bytes(pb)
    t = datetime.now(timezone.utc)
    approval = {"schema": "dreal001.solver_approval.v1", "approved": True,
                "authorization_id": AUTH,
                "owner_message_ref": "m10841 + Issue #14 comment 7103901506 (P2 directive)",
                "run_id": RUN_ID, "batch_id": BATCH_ID, "case_id": case_id,
                "plan_sha256": hashlib.sha256(pb).hexdigest(), "max_starts": 1,
                "window": {"start_utc": (t - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "end_utc": WINDOW_END, "token": AUTH + "-WINDOW"},
                "window_token": AUTH + "-WINDOW"}
    (case_dir / "approval.json").write_text(json.dumps(approval, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    task = TaskSpec(task_id=item["task_id"], split=item["split"], mach=mach, altitude_m=ALT,
                    dynamic_pressure_pa=float(item["q_pa"]), lift_target_n=LIFT,
                    geometry_contract_sha256=GEOM, lift_tolerance_rel=1e-3)
    spec = {"schema": "dreal001.r2_task_spec.v1", "task_id": item["task_id"], "split": item["split"],
            "partition": item["partition"], "case_id": case_id, "design": design,
            "design_id": design_id, "x12": x12, "mach": mach, "altitude_m": ALT,
            "dynamic_pressure_pa": float(item["q_pa"]), "lift_target_n": LIFT,
            "geometry_contract_sha256": GEOM, "lift_tolerance_rel": 1e-3,
            "flow_conditions": flow, "alpha_center_deg": item["alpha_target_deg"],
            "alpha_grid_deg": alphas, "cl_target": item["cl_target"], "sref_m2": sref,
            "task_physics_sha256": task.physics_sha256, "stage": "p2_supplement"}
    (case_dir / "task_spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    return case_dir, case_id


def internal_count(case_dir: Path, mach: float):
    try:
        polar = next(case_dir.glob("*.polar"))
        rows = read_polar_rows(polar, mach=mach)
        return len(rows) if rows else None
    except Exception:  # noqa: BLE001
        return None


def run_case_once(case_id: str, case_dir: Path, mach: float, timeout: float) -> dict:
    attempt = "p2-" + case_id + "-01"
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
    internal, started_utc = None, None
    if res.exists():
        try:
            cr = read_json(res)
            internal = cr.get("internal_solver_cases") or internal_count(case_dir, mach)
            arec = cr.get("attempt") or {}
            started_utc = arec.get("start_ts_utc") or arec.get("ts_utc")
        except Exception:  # noqa: BLE001
            internal = None
    return {"case_id": case_id, "attempt_id": attempt, "status": r.get("status"),
            "exit_code": proc.get("exit_code"), "timed_out": proc.get("timed_out"),
            "wall_s": round(wall, 3), "physical_solver_starts": r.get("physical_solver_starts"),
            "internal_solver_cases": internal if internal is not None else (r.get("internal") or {}).get("count"),
            "solver_started_utc": started_utc,
            "case_result": str(res) if res.exists() else None, "error": r.get("error")}


def best_match(case_dir: Path, clt: float, mach: float):
    try:
        polar = next(case_dir.glob("*.polar"))
        rows = read_polar_rows(polar, mach=mach)
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__ + ": " + str(e)[:300]}
    if not rows:
        return None
    scored = sorted(((abs(r.cl - clt) / clt, r.alpha_deg, r.cl, r.cdi) for r in rows))
    err, a, cl, cdi = scored[0]
    return {"rel_error": err, "alpha_deg": a, "cl": cl, "cdi": cdi,
            "rows": [(r.alpha_deg, r.cl) for r in rows]}


def admit(case_dir: Path, case_id: str, partition: str, split: str):
    audit_id = "p2-audit-" + case_id
    p = subprocess.run([str(PY), str(AUDIT), "--case-dir", str(case_dir),
                        "--audit-id", audit_id, "--reviewer", "lead-local-script",
                        "--reviewer-role", "SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5",
                        "--created-utc", now(), "--verdict", "ADMIT_REAL_LABEL"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if p.returncode != 0:
        return {"admitted": False, "stage": "AUDIT_FAILED", "detail": (p.stdout + p.stderr)[-600:]}
    result = read_json(case_dir / "case_result.json")
    arec = result.get("attempt") or {}
    started = arec.get("start_ts_utc") or arec.get("ts_utc") or now()
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", str(started))
    started = (m.group(1) + "Z") if m else now()
    q = subprocess.run([str(PY), str(ADMIT), "--case-dir", str(case_dir),
                        "--admission-id", "p2-adm-" + case_id, "--audit-ref", audit_id,
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
    p = subprocess.run([str(PY), str(RUN / "scripts" / "p2_upload.py"), "--label", label,
                        "--total-starts", str(starts)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200)
    print("UPLOAD", label, "rc", p.returncode, flush=True)
    print((p.stdout or "")[-2500:], flush=True)
    if p.returncode != 0:
        print((p.stderr or "")[-1500:], flush=True)
    return p.returncode == 0


def write_tables(state) -> None:
    tdir = RUN / "tables"
    tdir.mkdir(exist_ok=True)
    runs = state["runs"]
    with (tdir / "p2_attempt_ledger.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = ["task_id", "design", "partition", "case_id", "status", "wall_s",
                  "internal_solver_cases", "physical_solver_starts", "exit_code", "timed_out",
                  "match_rel_error", "matched_alpha_deg", "matched_cl", "admitted",
                  "failure_kind", "detail"]
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in runs:
            w.writerow(r)
    hist = []
    for r in runs:
        for a, cl in (r.get("observed_rows") or []):
            hist.append({"task_id": r["task_id"], "design": r["design"], "case_id": r["case_id"],
                         "alpha_deg": a, "cl": cl})
    with (tdir / "p2_alpha_rows.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["task_id", "design", "case_id", "alpha_deg", "cl"])
        w.writeheader()
        for h in hist:
            w.writerow(h)
    adm = [r for r in runs if r.get("admitted")]
    with (tdir / "p2_admitted_labels.csv").open("w", encoding="utf-8", newline="") as fh:
        fl = ["task_id", "design", "partition", "case_id", "di_n", "q_pa", "sref_m2", "cl_target",
              "matched_alpha_deg", "matched_cl", "match_rel_error", "admission_id",
              "design_sha256", "raw_sha256", "artifact_sha256"]
        w = csv.DictWriter(fh, fieldnames=fl, extrasaction="ignore")
        w.writeheader()
        for r in adm:
            w.writerow(r)
    nulls = [r for r in runs if not r.get("admitted")]
    with (tdir / "p2_failed_or_null.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["task_id", "design", "case_id", "status",
                                           "failure_kind", "detail", "match_rel_error"],
                           extrasaction="ignore")
        w.writeheader()
        for r in nulls:
            w.writerow(r)
    starts = sum(1 for r in runs if r.get("physical_solver_starts") == 1)
    internal = sum(int(r.get("internal_solver_cases") or 0) for r in runs)
    acc = {"schema": "dreal004.p2_supplement_accounting.v1", "run_id": RUN_ID,
           "batch_id": BATCH_ID, "authorization_id": AUTH,
           "owner_instruction_ref": "m10841 + Issue #14 comment 7103901506",
           "physical_solver_starts_actual": starts,
           "physical_solver_starts_completed": sum(1 for r in runs if r["status"] == "SOLVED"),
           "internal_solver_cases_actual": internal, "retries_actual": 0, "parallelism": 1,
           "admitted_labels": len(adm), "null_labels": len(nulls),
           "valid_label_rate_over_completed": len(adm) / max(1, sum(1 for r in runs if r["status"] == "SOLVED")),
           "max_starts": MAX_STARTS, "max_internal_solver_cases": MAX_INTERNAL,
           "wall_clock_s": round(sum(r.get("wall_s") or 0 for r in runs), 3),
           "stops": state.get("stops", []), "runs": runs, "generated_utc": now()}
    write_json(RUN / "p2_supplement_accounting.json", acc)
    write_json(tdir / "p2_supplement_accounting.json", acc)
    all_ev = {"schema": "dreal004.p2_supplement_all_evaluations.v1", "run_id": RUN_ID,
              "note": "one row per charged solver start; null rows keep null objective",
              "rows": runs}
    write_json(tdir / "all_evaluations.json", all_ev)
    write_json(RUN / "all_evaluations.json", all_ev)
    for name in ("p2_attempt_ledger.csv", "p2_admitted_labels.csv", "p2_failed_or_null.csv",
                 "p2_alpha_rows.csv", "all_evaluations.json"):
        src = tdir / name
        if src.exists():
            shutil.copy2(src, RUN / name)


def acquire_lock(force: bool) -> Path:
    lock = RUN / "p2_run.lock"
    if lock.exists() and not force:
        age = time.time() - lock.stat().st_mtime
        if age < 7200:
            raise SystemExit("LOCK_HELD: %s age %.1fs" % (lock, age))
    lock.write_text("%d %s\n" % (os.getpid(), now()), encoding="utf-8")
    return lock


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=MAX_STARTS)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    prereg = read_json(RUN / "p2_preregistration.json")
    plan = read_json(RUN / "p2_supplement_plan.json")
    gate_check(prereg)
    items = plan["starts_plan"]
    state_p = RUN / "p2_supplement_state.json"
    state = read_json(state_p) if state_p.exists() else {
        "schema": "dreal004.p2_supplement_state.v1", "runs": [], "stops": [], "started_utc": now()}
    done = {r["case_id"] for r in state["runs"]}
    starts = sum(1 for r in state["runs"] if r.get("physical_solver_starts") == 1)
    internal = sum(int(r.get("internal_solver_cases") or 0) for r in state["runs"])
    wall = sum(r.get("wall_s") or 0 for r in state["runs"])
    if a.dry_run:
        print(json.dumps({"dry_run": True, "starts": starts, "internal": internal, "wall": wall,
                          "pending": [i["task_id"] + "/" + i["design"] for i in items
                                      if "p2-%s-%s" % (i["tag"], i["design"]) not in done]},
                         ensure_ascii=False, indent=2))
        return 0
    lock = acquire_lock(a.force)
    try:
        consecutive = 0
        ran = 0
        for item in items:
            case_id = "p2-%s-%s" % (item["tag"], item["design"])
            if case_id in done:
                continue
            if a.only and a.only not in case_id:
                continue
            if starts >= MAX_STARTS or ran >= a.limit:
                state["stops"].append({"reason": "MAX_STARTS_OR_LIMIT", "starts": starts})
                break
            if internal + 3 > MAX_INTERNAL:
                state["stops"].append({"reason": "MAX_INTERNAL", "internal": internal})
                break
            if wall + 600 > WALL_MAX:
                state["stops"].append({"reason": "WALL_STOP", "wall_s": wall})
                break
            if consecutive >= 2:
                state["stops"].append({"reason": "CONSECUTIVE_SOLVER_FAILURE", "case_id": case_id})
                break
            case_dir, case_id = make_case(item)
            timeout = min(600.0, max(1.0, WALL_MAX - wall))
            mach = item["mach"] / 100.0
            row = run_case_once(case_id, case_dir, mach, timeout)
            row.update(task_id=item["task_id"], design=item["design"], partition=item["partition"],
                       split=item["split"], cl_target=item["cl_target"], alphas=item["alpha_grid_deg"])
            internal += int(row.get("internal_solver_cases") or 0)
            wall += row.get("wall_s") or 0
            ran += 1
            if row.get("physical_solver_starts") == 1:
                starts += 1
            rm = best_match(case_dir, float(item["cl_target"]), mach) if row["status"] == "SOLVED" else None
            row["observed_rows"] = (rm or {}).get("rows") or []
            row["match_rel_error"] = (rm or {}).get("rel_error")
            row["matched_alpha_deg"] = (rm or {}).get("alpha_deg")
            row["matched_cl"] = (rm or {}).get("cl")
            if row["status"] == "SOLVED" and rm and "error" not in rm and rm.get("rel_error") is not None:
                if rm["rel_error"] <= 1e-3:
                    res = admit(case_dir, case_id, item["partition"], item["split"])
                    if res.get("admitted"):
                        cert = res["certificate"]
                        row.update(admitted=True, admission_id=cert.get("admission_id"),
                                   di_n=cert.get("di_n"), q_pa=cert.get("q_pa"),
                                   sref_m2=cert.get("sref_m2"), design_sha256=cert.get("design_sha256"),
                                   raw_sha256=cert.get("raw_sha256"),
                                   artifact_sha256=cert.get("artifact_sha256"),
                                   admission_manifest_sha256=res.get("admission_manifest_sha256"),
                                   certificate_sha256=res.get("certificate_sha256"),
                                   audit_sha256=res.get("audit_sha256"))
                        row["failure_kind"] = None
                        print("ADMITTED", case_id, "di_n", row.get("di_n"), flush=True)
                    else:
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
            if row["status"] == "SOLVED" and row.get("physical_solver_starts") == 1:
                consecutive = 0
            elif row["status"] != "SOLVED":
                consecutive += 1
            state["runs"].append(row)
            write_json(state_p, state)
            write_tables(state)
            print("RAN", json.dumps({k: row.get(k) for k in ("case_id", "status", "wall_s",
                  "internal_solver_cases", "match_rel_error", "failure_kind")}, ensure_ascii=False), flush=True)
            if starts > 0 and starts % UPLOAD_EVERY == 0 and not a.no_upload:
                if not upload("P2-B%02d" % (starts // UPLOAD_EVERY), starts):
                    state["stops"].append({"reason": "UPLOAD_READBACK_FAILED", "starts": starts})
                    write_json(state_p, state)
                    write_tables(state)
                    return 6
            if row["status"] in ("REFUSED", "EXCEPTION"):
                state["stops"].append({"reason": "SOLVER_REFUSED_OR_EXCEPTION", "case_id": case_id})
                write_json(state_p, state)
                write_tables(state)
                return 7
        state["final"] = {"starts": sum(1 for r in state["runs"] if r.get("physical_solver_starts") == 1),
                          "internal": sum(int(r.get("internal_solver_cases") or 0) for r in state["runs"]),
                          "admitted": sum(1 for r in state["runs"] if r.get("admitted")),
                          "completed_utc": now()}
        write_json(state_p, state)
        write_tables(state)
        if not a.no_upload:
            upload("P2-FINAL", state["final"]["starts"])
        print("DONE", json.dumps(state["final"], ensure_ascii=False), flush=True)
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
