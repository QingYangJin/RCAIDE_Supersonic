
import hashlib, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
DEST=REPO/"research/concorde_metaopt/optimization_runs/DRECOVER001-G1-20261121-01"
def sha(p):
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def copy_tree(src,dst):
    dst.mkdir(parents=True,exist_ok=True)
    for p in src.rglob("*"):
        if p.is_file():
            rel=p.relative_to(src); t=dst/rel; t.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,t)
def main():
    man=json.loads((RUN/"g1_case_manifest.json").read_text(encoding="utf-8"))
    started=[]
    for c in man["cases"]:
        d=RUN/"cases"/c["case_id"]
        if (d/"solver_attempts.jsonl").exists() or (d/"case_result.json").exists():
            started.append(c)
    if DEST.exists():
        shutil.rmtree(DEST)
    copied=[]
    for c in started:
        src=RUN/"cases"/c["case_id"]; dst=DEST/"raw_cases"/c["case_id"]
        copy_tree(src,dst); copied.append(c["case_id"])
    for name in ("all_evaluations.csv","admitted_labels.csv","failed_or_null.csv","attempt_ledger.csv","batch_accounting.json","null_labels.json","g1_preregistration.json","operator_authorization.json","g1_case_manifest.json","g1_batch_runs.json","g1_go_record.json"):
        src=RUN/name
        if src.exists():
            t=DEST/"tables"/name; t.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,t)
    (DEST/"audits").mkdir(parents=True,exist_ok=True)
    for src in (RUN.glob("g1_batch_*.log")):
        shutil.copy2(src,DEST/"audits"/src.name)
    a5=RUN/"a5_review/verdict.json"
    if a5.exists(): shutil.copy2(a5,DEST/"audits"/"a5_g1_review_verdict.json")
    (DEST/"scripts").mkdir(parents=True,exist_ok=True)
    for src in (RUN/"scripts").glob("*.py"):
        shutil.copy2(src,DEST/"scripts"/src.name)
    (DEST/"metadata").mkdir(parents=True,exist_ok=True)
    tasks=[]; seen=set()
    for c in man["cases"]:
        if c["task_id"] in seen: continue
        seen.add(c["task_id"])
        tasks.append({"task_id":c["task_id"],"split":c["split"],
                      "mach":c["mach"],
                      "designs":[x["design"] for x in man["cases"] if x["task_id"]==c["task_id"]]})
    (DEST/"metadata/task_family_split.json").write_text(json.dumps({"schema":"dreal003.g1_task_family_split.v1","tasks":tasks},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    code={"schema":"dreal003.g1_code_sha.v1","base_commit":"35d1f115637c3aa57521eec8458cef706944c4af",
          "files":{}}
    for rel in ("research/concorde_metaopt/dreal001/geometry/solver_runner.py",
                "research/concorde_metaopt/tests/test_recovery_solver_runner.py"):
        p=REPO/rel
        if p.exists(): code["files"][rel]=sha(p)
    (DEST/"metadata/code_sha.json").write_text(json.dumps(code,indent=2)+"\n",encoding="utf-8")
    gf=REPO/"docs/evidence/drecover001/geometry_freeze_v2.json"
    if gf.exists(): shutil.copy2(gf,DEST/"metadata/geometry_freeze.json")
    # manifest + sums
    entries=[]
    for p in sorted(DEST.rglob("*")):
        if p.is_file() and p.name not in ("data_manifest.json","SHA256SUMS.txt"):
            entries.append({"path":p.relative_to(DEST).as_posix(),"bytes":p.stat().st_size,"sha256":sha(p)})
    (DEST/"data_manifest.json").write_text(json.dumps({"schema":"dreal003.g1_data_manifest.v1",
        "generated_utc":now(),"run_id":man["run_id"],"batch_id":man["batch_id"],
        "case_count":len(copied),"files":entries,"file_count":len(entries),
        "total_bytes":sum(e["bytes"] for e in entries)},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (DEST/"SHA256SUMS.txt").write_text("".join("%s  %s\n"%(e["sha256"],e["path"]) for e in entries),encoding="utf-8")
    print(json.dumps({"dest":str(DEST),"cases":len(copied),"case_ids":copied,
                      "files":len(entries),"bytes":sum(e["bytes"] for e in entries),
                      "data_manifest_sha256":sha(DEST/"data_manifest.json"),
                      "sha256sums_sha256":sha(DEST/"SHA256SUMS.txt")},indent=2))
if __name__=="__main__": raise SystemExit(main())
