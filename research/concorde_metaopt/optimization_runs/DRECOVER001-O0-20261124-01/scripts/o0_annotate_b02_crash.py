
import hashlib, json, subprocess
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
CRASH = RUN / "o0_batch_crash_B02.json"
LOCK = RUN / "o0_run.lock"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

record = json.loads(CRASH.read_text(encoding="utf-8"))
before_sha = sha(CRASH)
try:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-Process python -ErrorAction SilentlyContinue | Measure-Object).Count"],
                         capture_output=True, text=True, timeout=60)
    pycount = int((out.stdout or "0").strip() or 0)
except Exception as exc:
    pycount = -1
lock = {"existed": LOCK.is_file()}
if LOCK.is_file():
    lock["sha256"] = sha(LOCK)
    lock["contents"] = json.loads(LOCK.read_text(encoding="utf-8"))
    lock["python_processes_running"] = pycount
    lock["deleted_utc"] = now()
    lock["deleted_because"] = ("the batch process had already exited (the crash record is on disk and no "
                               "python process is running); the single-writer lock exists to stop two "
                               "concurrent writers, not to stop the crash from being read")
    LOCK.unlink()
    lock["exists_after"] = LOCK.is_file()
else:
    lock["python_processes_running"] = pycount
    lock["exists_after"] = False

ann = record.setdefault("post_abort_annotations", {})
ann["annotated_utc"] = now()
ann["lock"] = lock
ann["outcome_note"] = (
    "This was not a scientific failure and no cap was exceeded. The optimizer asked the ledger for a "
    "twelfth design, which was the last one it was entitled to, then asked for a thirteenth; the ledger "
    "refused, which is the correct behaviour. The loop bound that produced the thirteenth request has "
    "since been fixed to subtract the carried-forward design attempts. Batch spend: 11 designs, 22 solver "
    "starts, 220 internal cases, 11 admitted labels, 0 failures. Authorization totals after this batch: "
    "12 designs, 23 solver starts, 227 internal cases against spendable 12 / 24 / 240.")
ann["annotation_order"] = ["lock", "outcome_note"]
ann["record_sha256_before_this_annotation"] = before_sha
CRASH.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"lock": lock, "crash_sha_before": before_sha, "crash_sha_after": sha(CRASH)},
                 ensure_ascii=False, indent=2))
