"""F-ENV-03/A09 evidence manifest and large-artifact retention (D-REAL-001).

Governance v3 section 12.11: large DERIVED solver artifacts are not versioned.  They are
SHA256-recorded in retention.jsonl BEFORE deletion; every other run file is listed in
data_manifest.json and SHA256SUMS.txt.  physical_solver_starts is COMPUTED FROM THE
LEDGER start events, never typed by hand.

Excluded/derived (record then delete):
  *.adb, *.lod, *.case.*.dat, *.quad.cases, *.group.*
Kept and versioned:
  approval.json, plan.json, case_inputs.json, case_result.json, logs/*, solver_attempts.jsonl,
  evaluations.jsonl, *.vspaero, *.polar, *.history, *.vspgeom, *.vkey, *.csf, *.vsp3,
  *.adb.cases (small; needed for internal-case accounting), retention.jsonl,
  data_manifest.json, SHA256SUMS.txt
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

MANIFEST_SCHEMA = "dreal001.data_manifest.v1"
RETENTION_SCHEMA = "dreal001.retention.v1"
DERIVED_LARGE_PATTERNS = (
    "*.adb", "*.lod", "*.case.*.dat", "*.quad.cases", "*.group.*",
)
# *.adb.cases must stay reproducible for internal case accounting; it is small (KB).
RETENTION_KEEP_PATTERNS = ("*.adb.cases",)
MANIFEST_FILENAMES = ("data_manifest.json", "SHA256SUMS.txt")


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def is_derived_large(relative: str) -> bool:
    name = Path(relative).name
    if any(fnmatch.fnmatch(name, pattern) for pattern in RETENTION_KEEP_PATTERNS):
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in DERIVED_LARGE_PATTERNS)


def adb_case_count(root: Optional[str | Path], case_id: Optional[str]) -> Optional[int]:
    """Fallback internal-case count from <case>.adb.cases (one line per solved case)."""
    if root is None or not case_id:
        return None
    candidates = list((Path(root) / "cases" / str(case_id) / "inputs").glob("*.adb.cases"))
    if len(candidates) != 1:
        return None
    lines = [line for line in candidates[0].read_text(encoding="utf-8",
                                                     errors="replace").splitlines()
             if line.strip()]
    return len(lines) or None


def ledger_totals(ledger_path: str | Path, root: Optional[str | Path] = None) -> Dict[str, Any]:
    """Count physical starts and internal cases from the ledger (start/end events)."""
    ledger_path = Path(ledger_path)
    starts: List[Dict[str, Any]] = []
    ends: Dict[str, Dict[str, Any]] = {}
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("event") == "start":
                starts.append(entry)
            elif entry.get("event") == "end":
                ends[str(entry.get("attempt_id"))] = entry
    details = []
    total_internal = 0
    for start in starts:
        attempt_id = str(start.get("attempt_id"))
        end = ends.get(attempt_id) or {}
        internal = end.get("internal_solver_cases")
        internal_source = "ledger_end"
        if internal is None:
            internal = adb_case_count(root, start.get("case_id"))
            internal_source = "derived_from_adb_cases" if internal is not None else "MISSING"
        total_internal += int(internal or 0)
        details.append({
            "attempt_id": attempt_id,
            "case_id": start.get("case_id"),
            "physical_solver_starts": 1,
            "internal_solver_cases": int(internal or 0),
            "internal_solver_cases_source": internal_source,
            "unique_flow_conditions": end.get("unique_flow_conditions"),
            "status": end.get("status"),
            "exit_code": end.get("exit_code"),
            "wall_s": end.get("wall_s"),
        })
    return {
        "physical_solver_starts": len(starts),
        "internal_solver_cases": total_internal,
        "attempts": details,
        "ledger_sha256": sha256_file(ledger_path) if ledger_path.is_file() else None,
        "source": "sum of event=start lines (physical_solver_starts) and matching event=end "
                  "internal_solver_cases; computed, never hand-typed",
    }


def record_retention(root: str | Path, delete: bool = True) -> List[Dict[str, Any]]:
    """SHA256-record every derived large artifact, then delete it (default)."""
    root = Path(root)
    entries: List[Dict[str, Any]] = []
    recorded_utc = iso_utc()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = relpath(path, root)
        if not is_derived_large(relative):
            continue
        entries.append({
            "schema": RETENTION_SCHEMA,
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "classification": "DERIVED_LARGE_ARTIFACT_NOT_VERSIONED",
            "governance": "docs/planning/dreal001_execution_governance_20261110.md section 12.11",
            "disposition": "DELETED_AFTER_SHA_RECORD" if delete else "RECORDED_NOT_DELETED",
            "recorded_utc": recorded_utc,
        })
    retention_path = root / "retention.jsonl"
    if not retention_path.is_file():
        # The journal exists even when this run has no derived-large artifacts, so
        # downstream verification never has to treat "absent" as "unchecked".
        retention_path.write_text("", encoding="utf-8", newline="\n")
    if entries:
        existing = retention_path.read_text(encoding="utf-8") if retention_path.is_file() else ""
        with open(retention_path, "unlink" if False else "a", encoding="utf-8", newline="\n") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if delete:
            for entry in entries:
                target = root / entry["path"]
                if target.is_file() and sha256_file(target) == entry["sha256"]:
                    target.unlink()
                else:
                    raise RuntimeError("refusing to delete changed file: %s" % entry["path"])
    return entries


def read_retention(root: str | Path) -> List[Dict[str, Any]]:
    """Read every retention entry ever recorded for this run (append-only journal)."""
    retention_path = Path(root) / "retention.jsonl"
    if not retention_path.is_file():
        return []
    entries: List[Dict[str, Any]] = []
    for line in retention_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def build_manifest(root: str | Path, ledger_path: Optional[str | Path] = None,
                   approval_path: Optional[str | Path] = None,
                   plan_path: Optional[str | Path] = None,
                   retention_entries: Optional[Sequence[Dict[str, Any]]] = None,
                   extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(root).resolve()
    ledger_path = Path(ledger_path) if ledger_path else root / "solver_attempts.jsonl"
    approval_path = Path(approval_path) if approval_path else root / "approval.json"
    plan_path = Path(plan_path) if plan_path else root / "plan.json"
    totals = ledger_totals(ledger_path, root)
    files: List[Dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = relpath(path, root)
        if is_derived_large(relative) or relative in MANIFEST_FILENAMES:
            continue
        files.append({"path": relative, "bytes": path.stat().st_size,
                      "sha256": sha256_file(path)})
    payload: Dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "generated_utc": iso_utc(),
        "run_root": str(root),
        "physical_solver_starts": totals["physical_solver_starts"],
        "internal_solver_cases": totals["internal_solver_cases"],
        "internal_solver_cases_provenance": "per attempt: ledger end event when present, "
                                             "otherwise line count of <case>.adb.cases",
        "solver_starts": totals["attempts"],
        "ledger_sha256": totals["ledger_sha256"],
        "ledger_accounting_source": totals["source"],
        "approval_sha256": sha256_file(approval_path) if approval_path.is_file() else None,
        "plan_sha256": sha256_file(plan_path) if plan_path.is_file() else None,
        "excluded_derived_artifacts": list(retention_entries or []),
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
        "note": "physical_solver_starts and internal_solver_cases are computed from "
                "solver_attempts.jsonl; derived large artifacts are SHA256-recorded in "
                "retention.jsonl and deleted before git commit (governance section 12.11)",
    }
    if extra:
        payload.update(extra)
    return payload


def write_manifest(root: str | Path, ledger_path: Optional[str | Path] = None,
                   approval_path: Optional[str | Path] = None,
                   plan_path: Optional[str | Path] = None,
                   retention_entries: Optional[Sequence[Dict[str, Any]]] = None,
                   extra: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    root = Path(root).resolve()
    manifest = build_manifest(root, ledger_path, approval_path, plan_path,
                              retention_entries, extra)
    manifest_path = root / "data_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    sums_path = root / "SHA256SUMS.txt"
    lines = ["%s  %s" % (item["sha256"], item["path"]) for item in manifest["files"]]
    sums_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {"data_manifest": str(manifest_path), "sha256sums": str(sums_path),
            "physical_solver_starts": str(manifest["physical_solver_starts"]),
            "internal_solver_cases": str(manifest["internal_solver_cases"])}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="D-REAL-001 evidence manifest (no solver)")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--delete-derived", action="store_true",
                        help="record SHA256 in retention.jsonl then delete derived large files")
    parser.add_argument("--no-delete", action="store_true",
                        help="record retention only; keep derived files on disk")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(args.run_dir).resolve()
    retention: List[Dict[str, Any]] = []
    if args.delete_derived:
        retention = record_retention(root, delete=not args.no_delete)
    else:
        # still record retention for files already removed / to be removed
        retention_path = root / "retention.jsonl"
        if retention_path.is_file():
            retention = [json.loads(line) for line in
                         retention_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = write_manifest(root, retention_entries=retention)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
