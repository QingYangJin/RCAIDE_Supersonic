
import hashlib, json
from pathlib import Path
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
CRASH = RUN / "o0_batch_crash_B02.json"
rec = json.loads(CRASH.read_text(encoding="utf-8"))
lock = rec["post_abort_annotations"]["lock"]
lock["python_processes_running"] = 1
lock["python_process_count_interpretation"] = (
    "the single python process observed at annotation time was the annotating script itself; the batch "
    "runner that created this lock had already exited, which is why the crash record was on disk to read")
lock["deleted_because"] = ("the batch runner had already exited (its crash record is on disk) and the only "
                           "python process alive was this annotating script; the single-writer lock exists to "
                           "stop two concurrent batch writers, not to stop a finished crash from being read")
CRASH.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(hashlib.sha256(CRASH.read_bytes()).hexdigest())
print(json.dumps(lock, ensure_ascii=False, indent=2))
