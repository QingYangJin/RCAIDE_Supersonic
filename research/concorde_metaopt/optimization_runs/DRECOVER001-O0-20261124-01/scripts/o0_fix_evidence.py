"""Executed evidence that the two fixes in section 0b are really in the frozen code.

The A5 review of the previous dossier said, correctly, that the two fixes were only described in
prose: no log showed them running under the code SHAs the dossier lists. This script produces
that evidence with zero solver starts:

  1. it extracts the two changed functions verbatim from the files whose SHA256 the dossier lists,
     so the printed text and the hash cover the same bytes;
  2. it runs the regression tests that cover those two fixes and captures the pytest output;
  3. it replays the already-paid B01 baseline coarse rows through the fixed parse path and
     records the numbers, which is a real execution of the fixed code on real solver output.

Nothing here starts a solver, admits a label or writes a GO. It only reports what already
happened, and every artifact it writes is hashed into the dossier.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
PY = r"D:/Anaconda/envs/RCAIDE/python.exe"
OUT = RUN / "a5_support" / "fix_evidence"

EVAL = REPO / "research/concorde_metaopt/dreal001/ops/o0_short_bo.py"
GEOM_EVAL = RUN / "scripts" / "o0_eval.py"
TESTS = REPO / "research/concorde_metaopt/tests/test_recovery_o0_short_bo.py"
PROBE = RUN / "scripts" / "_probe_predict.py"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract(path: Path, start_marker: str) -> str:
    """Return the source text from start_marker to the next top-level def/class or EOF."""
    lines = path.read_text(encoding="utf-8").splitlines()
    begin = None
    for i, line in enumerate(lines):
        if line.startswith(start_marker):
            begin = i
            break
    if begin is None:
        raise SystemExit("marker not found in %s: %r" % (path, start_marker))
    indent = len(lines[begin]) - len(lines[begin].lstrip())
    body = [lines[begin]]
    for line in lines[begin + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent and not line.lstrip().startswith((")", "]", "}", ",", '"', "'")):
            break
        body.append(line)
    return "\n".join(body).rstrip() + "\n"


def run(cmd, log: Path, cwd: Path) -> dict:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=1800)
    text = "$ " + " ".join(cmd) + "\n\n" + (proc.stdout or "") + (proc.stderr or "")
    log.write_text(text, encoding="utf-8", newline="\n")
    tail = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()][-3:]
    return {"returncode": proc.returncode, "log": str(log),
            "log_sha256": sha_file(log), "log_bytes": log.stat().st_size,
            "tail": tail}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}

    # 1. verbatim excerpts of the two changed regions, tied to the hashed files
    for name, path, marker in (
        ("bracket_rows_excerpt.txt", GEOM_EVAL, "def bracket_rows("),
        ("evaluate_and_settle_excerpt.txt", EVAL, "    def evaluate_and_settle("),
    ):
        out = OUT / name
        out.write_text(extract(path, marker), encoding="utf-8", newline="\n")
        results[name.replace(".txt", "")] = {
            "source_file": str(path), "source_sha256": sha_file(path),
            "excerpt": str(out), "excerpt_sha256": sha_file(out),
            "excerpt_bytes": out.stat().st_size,
        }

    # 2. the regression tests that cover both fixes, executed now
    results["pytest_o0_short_bo"] = run(
        [PY, "-m", "pytest", "research/concorde_metaopt/tests/test_recovery_o0_short_bo.py",
         "-q"], OUT / "pytest_o0_short_bo.log", REPO)
    results["pytest_ledger"] = run(
        [PY, "-m", "pytest", "research/concorde_metaopt/tests/test_recovery_ledger.py",
         "-q"], OUT / "pytest_ledger.log", REPO)
    results["test_file"] = {"path": str(TESTS), "sha256": sha_file(TESTS),
                            "bytes": TESTS.stat().st_size}

    # 3. replay the paid B01 rows through the fixed parse path (real solver output, no new start)
    probe_log = OUT / "replay_paid_b01.log"
    probe = run([PY, "scripts/_probe_predict.py"], probe_log, RUN)
    results["replay_paid_b01"] = probe
    payload = None
    try:
        raw = probe_log.read_text(encoding="utf-8")
        payload = json.loads(raw[raw.index("{"):])
    except Exception as exc:  # noqa: BLE001
        results["replay_paid_b01"]["parse_error"] = "%s: %s" % (type(exc).__name__, exc)
    if payload is not None:
        (OUT / "replay_paid_b01.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        results["replay_paid_b01"]["json"] = str(OUT / "replay_paid_b01.json")
        results["replay_paid_b01"]["json_sha256"] = sha_file(OUT / "replay_paid_b01.json")
        results["replay_paid_b01"]["n_rows"] = payload.get("n_rows")
        results["replay_paid_b01"]["predict"] = (payload.get("predict") or {})

    evidence = {
        "schema": "dreal005.o0_fix_evidence.v1",
        "created_utc": now(),
        "why": ("the previous A5 review found that section 0b described the two fixes but showed "
                "no execution under the listed code SHAs; this file is that execution"),
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
        "admitted_labels_actual": 0,
        "note": ("zero solver starts: the replay consumes solver output that B01 already paid for; "
                 "the tests are pure unit tests on fixtures"),
        "results": results,
    }
    path = OUT / "fix_evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    print(json.dumps({"evidence": str(path), "sha256": sha_file(path),
                      "pytest_o0_short_bo_rc": results["pytest_o0_short_bo"]["returncode"],
                      "pytest_o0_short_bo_tail": results["pytest_o0_short_bo"]["tail"],
                      "pytest_ledger_rc": results["pytest_ledger"]["returncode"],
                      "pytest_ledger_tail": results["pytest_ledger"]["tail"],
                      "replay_rc": probe["returncode"],
                      "n_rows": results["replay_paid_b01"].get("n_rows")}, indent=2))
    ok = (results["pytest_o0_short_bo"]["returncode"] == 0
          and results["pytest_ledger"]["returncode"] == 0
          and probe["returncode"] == 0
          and results["replay_paid_b01"].get("n_rows") == 7)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
