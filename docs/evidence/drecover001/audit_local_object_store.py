"""Audit local Git object store for dangling/unreachable objects (zero physical).

This supplements the reachable-history audit: even if a file is absent from all
reachable trees, a dangling blob could still preserve its bytes.  The audit is
local-object-store evidence only; it is not a remote re-audit and starts no solver.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("r0_local_object_store_audit.json")


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False,
    )


def _parse_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() and value.strip().isdigit():
            counts[key.strip()] = int(value.strip())
    return counts


head = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
refs = [line.strip() for line in _run(
    ["git", "for-each-ref", "--format=%(refname)"]).stdout.splitlines() if line.strip()]
tags = [line for line in refs if line.startswith("refs/tags/")]
counts_proc = _run(["git", "count-objects", "-v"])
counts = _parse_counts(counts_proc.stdout)
fsck = _run(["git", "fsck", "--full", "--unreachable", "--no-reflogs"])
unreachable = [line.strip() for line in fsck.stdout.splitlines() if line.strip()]
warnings = [line.strip() for line in fsck.stderr.splitlines() if line.strip()]
count_warnings = [line.strip() for line in counts_proc.stderr.splitlines() if line.strip()]
if unreachable:
    conclusion = "UNREACHABLE_OBJECTS_PRESENT_REQUIRES_AUDIT"
else:
    conclusion = ("NO_UNREACHABLE_GIT_OBJECTS; missing critical paths are not recoverable "
                  "from dangling local objects")
result = {
    "schema": "drecover001.r0_local_object_store_audit.v1",
    "scope": "LOCAL_GIT_OBJECT_STORE_ONLY_NOT_REMOTE_REAUDIT",
    "head": head,
    "refs_total": len(refs),
    "tags_total": len(tags),
    "count_objects": counts,
    "command": "git fsck --full --unreachable --no-reflogs",
    "fsck_returncode": int(fsck.returncode),
    "unreachable_objects": len(unreachable),
    "unreachable_lines": unreachable,
    "warning_lines": warnings,
    "count_objects_warning_lines": count_warnings,
    "fsck_output_sha256": hashlib.sha256(
        (fsck.stdout + "\n---STDERR---\n" + fsck.stderr).encode("utf-8")).hexdigest(),
    "conclusion": conclusion,
    "physical_solver_starts_actual": 0,
    "network_used": False,
    "limitation": ("A local fsck cannot prove the remote server has no hidden refs; "
                   "the reachable-history audit covers the 20 API-verified remote heads."),
}
raw = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
OUT.write_bytes(raw.encode("utf-8"))
print(str(OUT))
print("sha256=" + hashlib.sha256(raw.encode("utf-8")).hexdigest())
print("unreachable_objects=" + str(len(unreachable)))
