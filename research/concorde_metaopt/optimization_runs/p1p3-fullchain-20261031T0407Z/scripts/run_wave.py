
"""Run one WAVE area-rule analysis under the D-12D-002 budget ledger (ledger CLI)."""
import json
import subprocess
import sys
import time
from pathlib import Path

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
LEAD = EXT / "lead"
PY39 = r"D:/Anaconda/envs/SUAVE/python.exe"
PY311 = r"D:/RCAIDE/envs/RCAIDE/python.exe"
LEDGER = str(LEAD / "ledger.py")

def ledger(*args):
    proc = subprocess.run([PY311, "-E", "-s", "-B", LEDGER] + list(args), capture_output=True, text=True)
    print(proc.stdout.strip())
    if proc.returncode != 0:
        print(proc.stderr.strip())
    return proc.returncode

def main():
    case_id = sys.argv[1]
    case_dir = EXT / "wave" / case_id
    request = case_dir / "request.json"
    result = case_dir / "result.json"
    cmd = [PY39, str(EXT / "wave" / "wave_worker.py"), str(request), str(result)]
    description = "OpenVSP analysis single start (%s)" % case_id
    if ledger("start", "WAVE_AREA_RULE", case_id, description, " ".join(cmd)) != 0:
        print("REFUSED by ledger")
        return 2
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(case_dir), capture_output=True, text=True, timeout=900)
    wall = round(time.time() - t0, 3)
    (case_dir / "worker_stdout.log").write_text(proc.stdout, encoding="utf-8")
    (case_dir / "worker_stderr.log").write_text(proc.stderr, encoding="utf-8")
    status = "SOLVED" if proc.returncode == 0 and result.exists() else "FAILED"
    if result.exists():
        try:
            payload = json.loads(result.read_text(encoding="utf-8"))
            if payload.get("status") != "ok":
                status = "FAILED"
                (case_dir / "worker_traceback.txt").write_text(str(payload.get("traceback", "")), encoding="utf-8")
        except Exception:
            status = "FAILED"
    listing = []
    for p in sorted(case_dir.iterdir()):
        listing.append("%s:%d" % (p.name, p.stat().st_size) if p.is_file() else p.name + ":dir")
    ledger("finish", case_id, status, str(wall), str(proc.returncode), "--files", ";".join(listing),
           "--note", "case %s rc=%s" % (case_id, proc.returncode))
    print(json.dumps({"case_id": case_id, "status": status, "wall_s": wall, "returncode": proc.returncode}))
    return 0 if status == "SOLVED" else 1

if __name__ == "__main__":
    sys.exit(main())
