"""Keep retrying the A5 dossier review until a verdict lands or the budget runs out.

The upstream tunnel is intermittently returning 503 for chat completions even though
/model listing works, so the review is retried with a long backoff rather than relaunched
by hand. Nothing else in this repo depends on this process.
"""
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
SCRIPT = RUN / "scripts/o0_a5_review.py"
VERDICT = RUN / "a5_review/verdict.json"
LOG = RUN / "o0_a5_retry.log"
DEADLINE_S = 3600


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write("%s %s\n" % (stamp, message))


started = time.time()
if VERDICT.exists():
    VERDICT.unlink()
attempt = 0
while time.time() - started < DEADLINE_S:
    attempt += 1
    log("attempt %d" % attempt)
    done = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                          cwd=str(RUN))
    if VERDICT.exists():
        log("VERDICT_WRITTEN after %d attempts" % attempt)
        raise SystemExit(0)
    tail = ((done.stdout or "") + (done.stderr or "")).strip().splitlines()
    log("failed rc=%s tail=%s" % (done.returncode, " || ".join(tail[-4:])[:600]))
    time.sleep(min(300, 30 * attempt))
log("GAVE_UP after %d attempts" % attempt)
raise SystemExit(9)
