#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build data_manifest.json for the P4-M2 official offline run.

Convention (same as D-12D-004 V1 package):
* text files: sha256 over canonical LF bytes (CRLF -> LF), bytes = canonical length;
* binary files (PNG): sha256 over raw bytes;
* large artifacts moved outside git: sha256 over raw bytes, absolute+relative path recorded,
  outside_git=true, and NOT counted in file_count/total_bytes (they are listed separately).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parent.parent
MANIFEST_NAME = "data_manifest.json"
TEXT_SUFFIXES = {
    ".md", ".json", ".jsonl", ".csv", ".txt", ".yaml", ".yml", ".py", ".log", ".cfg", ".ini",
}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf", ".gz", ".zip"}

DEFAULT_EXTERNAL = {
    "evaluations.jsonl": "evaluations.jsonl",
    "archive/p4-meta-m2-offline-20261102T092828Z-m1/observations.jsonl":
        "archive/p4-meta-m2-offline-20261102T092828Z-m1/observations.jsonl",
    "metrics/optimization_history.csv": "metrics/optimization_history.csv",
}


def hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_lf(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n")


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in BINARY_SUFFIXES:
        return "binary"
    return "text"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", default=str(RUN_DIR))
    parser.add_argument("--external-root", default=None)
    parser.add_argument("--allow-missing-external", action="store_true")
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    external_root = (
        Path(args.external_root).resolve()
        if args.external_root
        else Path(r"D:/RCAIDE/outputs/concorde_metaopt").resolve()
        / run_dir.name
        / "raw_artifacts"
    )

    files = []
    skipped = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        if rel in {MANIFEST_NAME, "__pycache__", "archive"} or "/__pycache__/" in rel:
            if path.name == MANIFEST_NAME and rel == MANIFEST_NAME:
                continue
            if "__pycache__" in rel:
                continue
        if rel == MANIFEST_NAME:
            continue
        if rel.startswith("archive/") and rel.endswith(".jsonl"):
            continue
        if rel in DEFAULT_EXTERNAL:
            continue
        raw = path.read_bytes()
        if classify(path) == "binary":
            files.append({
                "path": rel,
                "hash_mode": "raw",
                "bytes": len(raw),
                "sha256": hash_bytes(raw),
            })
        else:
            canon = canonical_lf(raw)
            files.append({
                "path": rel,
                "hash_mode": "canonical_lf",
                "bytes": len(canon),
                "sha256": hash_bytes(canon),
            })

    ext_entries = []
    for rel, ext_rel in DEFAULT_EXTERNAL.items():
        source = run_dir / rel
        target = external_root / ext_rel
        payload_path = target if target.is_file() else source
        if not payload_path.is_file():
            if args.allow_missing_external:
                ext_entries.append({"path": rel, "status": "MISSING", "external_path": str(target)})
                continue
            print(f"ERROR external artifact missing: {payload_path}", file=sys.stderr)
            return 2
        payload = payload_path.read_bytes()
        ext_entries.append({
            "path": rel,
            "hash_mode": "raw",
            "bytes": len(payload),
            "sha256": hash_bytes(payload),
            "external_path": str(target).replace("\\", "/"),
            "outside_git": True,
            "location": "external_outputs_gitignored",
        })

    total_bytes = sum(entry["bytes"] for entry in files)
    manifest = {
        "schema_version": "2.0.0",
        "run_id": run_dir.name,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hashing_convention": (
            "text: sha256 over canonical LF bytes (CRLF normalized), bytes=canonical length; "
            "binary (png): sha256 over raw bytes; external artifacts: sha256 over raw bytes and "
            "not counted in file_count/total_bytes"
        ),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "binary_file_count": sum(1 for entry in files if entry["hash_mode"] == "raw"),
        "files": files,
        "external_artifacts": {
            "outside_git": True,
            "root": str(external_root).replace("\\", "/"),
            "note": (
                "evaluations.jsonl / archive observations / optimization_history.csv were moved "
                "outside the git checkout to keep the repository small; sha256 over raw bytes is "
                "recorded here so reviewers can verify the external copies"
            ),
            "file_count": len([entry for entry in ext_entries if entry.get("status") != "MISSING"]),
            "total_bytes": sum(entry.get("bytes", 0) for entry in ext_entries if entry.get("status") != "MISSING"),
            "files": ext_entries,
        },
    }
    out_path = run_dir / MANIFEST_NAME
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "manifest": str(out_path),
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "external_file_count": manifest["external_artifacts"]["file_count"],
        "external_total_bytes": manifest["external_artifacts"]["total_bytes"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
