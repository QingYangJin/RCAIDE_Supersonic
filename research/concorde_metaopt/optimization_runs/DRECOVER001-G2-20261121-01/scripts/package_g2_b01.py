import hashlib, json, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
DEST = REPO / "research/concorde_metaopt/optimization_runs/DRECOVER001-G2-20261121-01"

def sha(p):
    h = hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def copy_tree(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src); t = dst / rel
            t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, t)

def main():
    m1 = json.loads((RUN / "g2_stage1_manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((RUN / "g2_stage2_manifest.json").read_text(encoding="utf-8"))
    started = []
    for c in m1["cases"] + m2["cases"]:
        d = RUN / "cases" / c["case_id"]
        if (d / "solver_attempts.jsonl").exists() or (d / "case_result.json").exists():
            started.append(c)
    if DEST.exists():
        shutil.rmtree(DEST)
    for c in started:
        copy_tree(RUN / "cases" / c["case_id"], DEST / "raw_cases" / c["case_id"])
    (DEST / "tables").mkdir(parents=True, exist_ok=True)
    tables = ["all_evaluations.csv", "admitted_labels.csv", "failed_or_null.csv",
              "attempt_ledger.csv", "batch_accounting.json", "null_labels.json",
              "g2_preregistration.json", "operator_authorization.json",
              "g2_stage1_manifest.json", "g2_stage2_manifest.json", "g2_batch_runs.json",
              "g2_go_record_b01.json", "g2_zero_physical_snapshot.json"]
    for name in tables:
        src = RUN / name
        if src.exists(): shutil.copy2(src, DEST / "tables" / name)
    copy_tree(RUN / "figures", DEST / "figures")
    (DEST / "audits").mkdir(parents=True, exist_ok=True)
    for src in RUN.glob("b01_*.log"):
        shutil.copy2(src, DEST / "audits" / src.name)
    for src, name in ((RUN / "a5_review/verdict.json", "a5_g2_review_verdict.json"),):
        if src.exists(): shutil.copy2(src, DEST / "audits" / name)
    for src in (REPO / "docs/evidence/dreal003/g2").glob("g2_a5_dossier*.md"):
        shutil.copy2(src, DEST / "audits" / src.name)
    # copy scripts (reproducibility)
    (DEST / "scripts").mkdir(parents=True, exist_ok=True)
    for src in (RUN / "scripts").glob("*.py"):
        shutil.copy2(src, DEST / "scripts" / src.name)
    (DEST / "metadata").mkdir(parents=True, exist_ok=True)
    tasks = []
    seen = set()
    for c in m1["cases"]:
        if c["task_id"] in seen: continue
        seen.add(c["task_id"])
        tasks.append({"task_id": c["task_id"], "split": c["split"], "mach": c["mach"],
                      "designs": [x["design"] for x in m1["cases"] if x["task_id"] == c["task_id"]]})
    (DEST / "metadata/task_family_split.json").write_text(json.dumps(
        {"schema": "dreal003.g2_task_family_split.v1", "tasks": tasks,
         "partition_rule": "support=d00-d03, query=d04-d07"}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    code = {"schema": "dreal003.g2_code_sha.v1", "base_commit": head, "files": {}}
    for rel in ("research/concorde_metaopt/dreal001/geometry/solver_runner.py",
                "research/concorde_metaopt/dreal001/meta/real_admission.py",
                "research/concorde_metaopt/dreal001/meta/task_spec.py",
                "research/concorde_metaopt/tests/test_recovery_solver_runner.py"):
        p = REPO / rel
        if p.exists(): code["files"][rel] = sha(p)
    (DEST / "metadata/code_sha.json").write_text(json.dumps(code, indent=2) + "\n", encoding="utf-8")
    gf = REPO / "docs/evidence/drecover001/geometry_freeze_v2.json"
    if gf.exists(): shutil.copy2(gf, DEST / "metadata/geometry_freeze.json")
    for src in (RUN / "README.md",):
        if src.exists(): shutil.copy2(src, DEST / src.name)
    entries = []
    for p in sorted(DEST.rglob("*")):
        if p.is_file() and p.name not in ("data_manifest.json", "SHA256SUMS.txt"):
            entries.append({"path": p.relative_to(DEST).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)})
    (DEST / "data_manifest.json").write_text(json.dumps({
        "schema": "dreal003.g2_data_manifest.v1", "generated_utc": now(),
        "run_id": m1["run_id"], "authorization_id": m1["authorization_id"], "batch_id": "B01",
        "case_count": len(started), "files": entries, "file_count": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries)}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (DEST / "SHA256SUMS.txt").write_text(
        "".join("%s  %s\n" % (e["sha256"], e["path"]) for e in entries), encoding="utf-8")
    print(json.dumps({"dest": str(DEST), "cases": len(started),
                      "files": len(entries), "bytes": sum(e["bytes"] for e in entries),
                      "data_manifest_sha256": sha(DEST / "data_manifest.json"),
                      "sha256sums_sha256": sha(DEST / "SHA256SUMS.txt")}, indent=2))

if __name__ == "__main__":
    main()
