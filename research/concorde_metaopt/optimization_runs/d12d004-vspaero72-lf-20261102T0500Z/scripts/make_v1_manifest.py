#!/usr/bin/env python
"""Regenerate data_manifest.json for the D-12D-004 V1 run directory.

Policy (A5 V1 review F-01):
- every entry must exist as a committed blob at freeze commit;
- text entries record both raw working-tree hash/bytes and canonical-LF hash/bytes
  (committed blobs are canonical LF under core.autocrlf);
- binary entries record raw bytes only;
- ignored artifacts excluded: __pycache__/*.pyc and data_manifest.json itself;
- evidence .log files are force-added to git so they count as committed evidence.

Usage: python make_v1_manifest.py
"""
import hashlib
import io
import json
import os
import sys
import time

RUN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(RUN_DIR, "data_manifest.json")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def classify(data):
    if b"\x00" in data:
        return "binary"
    try:
        data.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


def main():
    old_raw = None
    if os.path.exists(MANIFEST):
        with io.open(MANIFEST, encoding="utf-8") as fh:
            prev = json.load(fh)
        old_raw = prev.get("raw_artifacts_referenced")
        prev_run_id = prev.get("run_id")
    else:
        prev_run_id = None

    entries = []
    for root, dirs, files in os.walk(RUN_DIR):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, RUN_DIR).replace("\\", "/")
            if rel == "data_manifest.json":
                continue
            with io.open(full, "rb") as fh:
                data = fh.read()
            kind = classify(data)
            entry = {
                "path": rel,
                "hash_mode": kind,
                "bytes_raw": len(data),
                "sha256_raw": sha256_bytes(data),
            }
            if kind == "text":
                canonical = data.replace(b"\r\n", b"\n")
                entry["bytes_canonical_lf"] = len(canonical)
                entry["sha256_canonical_lf"] = sha256_bytes(canonical)
            entries.append(entry)

    entries.sort(key=lambda e: e["path"])
    total_raw = sum(e["bytes_raw"] for e in entries)
    text_entries = [e for e in entries if e["hash_mode"] == "text"]
    binary_entries = [e for e in entries if e["hash_mode"] == "binary"]
    manifest = {
        "schema_version": "1.1.0",
        "artifact_kind": "D12D004_V1_DATA_MANIFEST",
        "run_id": prev_run_id or "d12d004-vspaero72-lf-20261102T0500Z",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hash_mode": (
            "per-entry policy in field hash_mode: text = both raw working-tree hash/bytes "
            "and canonical_lf hash/bytes (canonical = CRLF->LF, identical to the committed git blob); "
            "binary = raw bytes only. file_count counts entries excluding this manifest file."
        ),
        "file_count": len(entries),
        "total_bytes_raw": total_raw,
        "text_file_count": len(text_entries),
        "binary_file_count": len(binary_entries),
        "exclusions": {
            "data_manifest.json": "not self-hashed",
            "__pycache__/ and *.pyc": "ignored bytecode, removed from working tree before freezing",
        },
        "notes": (
            "Evidence .log files (evidence/v0/run_full.log, evidence/v0/tests/test_vspaero7_runner.log, "
            "evidence/v1/setup_gen/run.log) are force-added to git because .gitignore line '*.log' would "
            "otherwise exclude them; their hashes are part of this manifest."
        ),
        "files": entries,
    }
    if old_raw is not None:
        manifest["raw_artifacts_referenced"] = old_raw

    with io.open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")

    print(json.dumps({
        "file_count": manifest["file_count"],
        "total_bytes_raw": manifest["total_bytes_raw"],
        "text": len(text_entries),
        "binary": len(binary_entries),
        "manifest_sha256_canonical_lf": sha256_bytes(
            io.open(MANIFEST, "rb").read().replace(b"\r\n", b"\n")),
    }, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
