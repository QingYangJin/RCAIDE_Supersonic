#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D-12D-005 BATCH1B v1b evidence freezer (zero solver, data-only).

Builds evidence/v1b/data_manifest.json with dual hashing so a clean checkout can
replay every archived byte:

  * raw form          : bytes_raw / sha256_raw, exactly as archived on the A2 host.
  * canonical-LF form : UTF-8 text is decoded, CRLF -> LF, re-encoded; this equals
                        the committed git blob because .gitattributes is
                        '* text=auto eol=lf'. Binary files (strict UTF-8 decode
                        fails) record canonical_lf = null and are replayed as raw.

Modes
-----
  (default)            build + write data_manifest.json, then self-verify worktree.
  --verify             replay 100% from the selected source and fail closed.
  --source git         committed blobs: git cat-file blob <rev>:<path> (authoritative,
                       used by A2/A5 on a clean checkout; requires a commit).
  --source index       staged blobs (pre-commit check; canonical-LF blob comparison).
  --source worktree    files on disk (generation-time check).

Exit codes: 0 = pass; 2 = verification failure (all reasons printed); 1 = usage.

No solver is started, no raw evidence byte is rewritten, no git write is performed.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE.parent
V1B_DIR = RUN_DIR / "evidence" / "v1b"
DEFAULT_MANIFEST = V1B_DIR / "data_manifest.json"
RUN_ID = RUN_DIR.name
SCHEMA_VERSION = "d12d005-v1b-manifest-1"
ARTIFACT_KIND = "D12D005_V1B_DATA_MANIFEST"
SCOPE = "evidence/v1b/** minus data_manifest.json itself"
EXCLUDED = ["evidence/v1b/data_manifest.json"]
SOLVER = (
    "VSPAERO 7.2.2 thin, -omp 4, exe sha256 "
    "db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad"
)
HASH_MODE_DETAIL = (
    "every file is hashed twice: bytes_raw/sha256_raw (as archived on the A2 host) and "
    "bytes_canonical_lf/sha256_canonical_lf (UTF-8 decode, CRLF->LF, re-encode; equals the "
    "committed git blob because .gitattributes is '* text=auto' with eol=lf). The canonical "
    "form is authoritative for clean-checkout reproduction; the raw form preserves "
    "generation-host provenance. Binary files (strict UTF-8 decode fails) have "
    "canonical_lf=null and are replayed as raw bytes."
)
HASHING_POLICY = {
    "text_detection": "strict UTF-8 decode; a file that does not decode as UTF-8 is binary",
    "canonical_form": "text.replace('\\r\\n', '\\n').encode('utf-8')",
    "binary_form": "raw bytes; bytes_canonical_lf=null, sha256_canonical_lf=null",
    "authoritative": "sha256_canonical_lf for text, sha256_raw for binary",
}


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_lf(data):
    """Return canonical-LF bytes for UTF-8 text, or None for binary bytes."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.replace("\r\n", "\n").encode("utf-8")


def json_text(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_text(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


def repo_root():
    proc = subprocess.run(
        ["git", "-C", str(RUN_DIR), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("git rev-parse failed: " + proc.stderr.strip())
    return Path(proc.stdout.strip())


def run_dir_rel_repo(root):
    return RUN_DIR.resolve().relative_to(root.resolve()).as_posix()


def scope_prefix(root):
    return run_dir_rel_repo(root) + "/evidence/v1b"


def git_output(args, root):
    proc = subprocess.run(
        ["git", "-C", str(root)] + list(args),
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def git_blob_bytes(root, rev, repo_rel):
    code, out, err = git_output(["cat-file", "blob", "%s:%s" % (rev, repo_rel)], root)
    if code != 0:
        return None
    return out


def record_entry(rel, raw):
    entry = {
        "path": rel,
        "bytes_raw": len(raw),
        "sha256_raw": sha256_bytes(raw),
    }
    canon = canonical_lf(raw)
    if canon is None:
        entry.update(
            {
                "hash_mode": "raw",
                "bytes_canonical_lf": None,
                "sha256_canonical_lf": None,
                "bytes": len(raw),
                "sha256": entry["sha256_raw"],
                "eol": None,
            }
        )
    else:
        entry.update(
            {
                "hash_mode": "canonical_lf",
                "bytes_canonical_lf": len(canon),
                "sha256_canonical_lf": sha256_bytes(canon),
                "bytes": len(canon),
                "sha256": sha256_bytes(canon),
                "eol": "crlf" if raw != canon else "lf",
            }
        )
    return entry


def worktree_paths(manifest_path):
    return sorted(
        p.relative_to(RUN_DIR).as_posix()
        for p in V1B_DIR.rglob("*")
        if p.is_file() and p.resolve() != manifest_path.resolve()
    )


def build_manifest(manifest_path):
    if not V1B_DIR.is_dir():
        raise RuntimeError("evidence/v1b does not exist: %s" % V1B_DIR)
    paths = worktree_paths(manifest_path)
    if not paths:
        raise RuntimeError("evidence/v1b contains no files to freeze")
    files = [record_entry(rel, (RUN_DIR / rel).read_bytes()) for rel in paths]
    committed_mode_counts = {"canonical_lf": 0, "raw": 0, "not_committed": 0, "mismatch": 0}
    root = repo_root()
    rev = "HEAD"
    for entry in files:
        repo_rel = run_dir_rel_repo(root) + "/" + entry["path"]
        blob = git_blob_bytes(root, rev, repo_rel)
        if blob is None:
            entry["committed_blob_mode"] = "not_committed"
            entry["committed_blob_bytes"] = None
            entry["committed_blob_sha256"] = None
            committed_mode_counts["not_committed"] += 1
            continue
        blob_sha = sha256_bytes(blob)
        entry["committed_blob_bytes"] = len(blob)
        entry["committed_blob_sha256"] = blob_sha
        raw_match = len(blob) == entry["bytes_raw"] and blob_sha == entry["sha256_raw"]
        canon_match = False
        if entry["hash_mode"] == "canonical_lf":
            canon_match = (
                len(blob) == entry["bytes_canonical_lf"]
                and blob_sha == entry["sha256_canonical_lf"]
            )
        if entry["hash_mode"] == "raw":
            mode = "raw" if raw_match else "mismatch"
        elif canon_match:
            mode = "canonical_lf"
        elif raw_match:
            mode = "raw"
        else:
            mode = "mismatch"
        entry["committed_blob_mode"] = mode
        committed_mode_counts[mode] += 1
    counts = {
        "canonical_lf": sum(1 for f in files if f["hash_mode"] == "canonical_lf"),
        "raw": sum(1 for f in files if f["hash_mode"] == "raw"),
    }
    total_bytes = sum(int(f["bytes"]) for f in files)
    total_canonical = sum(
        int(f["bytes_canonical_lf"]) for f in files if f["hash_mode"] == "canonical_lf"
    )
    total_raw = sum(int(f["bytes_raw"]) for f in files)
    return {
        "artifact_kind": ARTIFACT_KIND,
        "schema_version": SCHEMA_VERSION,
        "revision": 2,
        "run_id": RUN_ID,
        "generated_utc": utcnow(),
        "status": "V1B_FROZEN",
        "hash_mode": "canonical_lf_for_text_else_raw",
        "hash_mode_detail": HASH_MODE_DETAIL,
        "hashing_policy": HASHING_POLICY,
        "scope": SCOPE,
        "excluded": EXCLUDED,
        "file_count": len(files),
        "hash_mode_counts": counts,
        "committed_blob_mode_counts": committed_mode_counts,
        "committed_blob_mode_policy": (
            "committed_blob_mode records how each file is actually stored in the frozen git blob: "
            "canonical_lf = stored LF form (sha256_canonical_lf authoritative); raw = stored "
            "CRLF/binary form preserved by git (sha256_raw authoritative; relevant for *.log files "
            "that git treats as -text). --verify --source git/index auto-detects the stored form "
            "and requires it to equal this field. Raw fields keep the generation-host bytes."
        ),
        "total_bytes": total_bytes,
        "total_bytes_canonical_lf": total_canonical,
        "total_bytes_raw": total_raw,
        "total_bytes_note": (
            "total_bytes = sum of the authoritative byte counts (canonical-LF bytes for text, "
            "raw bytes for binary) and is the sum a clean checkout reproduces; "
            "total_bytes_canonical_lf sums the text entries only; total_bytes_raw is the "
            "archived host sum."
        ),
        "solver": SOLVER,
        "solver_started_during_freeze": 0,
        "note": (
            "Generated by scripts/freeze_v1b_evidence.py (zero solver, data-only). "
            "Raw solver outputs were not rewritten; only derived manifests/summaries were added."
        ),
        "files": files,
    }


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def manifest_structure_errors(manifest):
    errors = []
    if manifest.get("artifact_kind") != ARTIFACT_KIND:
        errors.append(("VERIFY_MANIFEST_SCHEMA", "artifact_kind mismatch"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(("VERIFY_MANIFEST_SCHEMA", "schema_version mismatch"))
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append(("VERIFY_MANIFEST_SCHEMA", "files[] missing/empty"))
        return errors
    seen = set()
    for entry in files:
        path = entry.get("path")
        if not isinstance(path, str) or not path.startswith("evidence/v1b/"):
            errors.append(("VERIFY_PATH_INVALID", str(path)))
            continue
        if path in EXCLUDED or path.endswith("/data_manifest.json"):
            errors.append(("VERIFY_SELF_INCLUDED", path))
            continue
        if path in seen:
            errors.append(("VERIFY_DUPLICATE_PATH", path))
        seen.add(path)
    if seen and files != sorted(files, key=lambda e: e.get("path", "")):
        errors.append(("VERIFY_MANIFEST_SCHEMA", "files[] not sorted by path"))
    if manifest.get("file_count") != len(files):
        errors.append(
            ("VERIFY_MANIFEST_TOTALS", "file_count %r != %d" % (manifest.get("file_count"), len(files)))
        )
    total_bytes = 0
    total_canonical = 0
    total_raw = 0
    counts = {"canonical_lf": 0, "raw": 0}
    for entry in files:
        mode = entry.get("hash_mode")
        if mode not in counts:
            errors.append(("VERIFY_HASH_MODE", "%s: %r" % (entry.get("path"), mode)))
            continue
        counts[mode] += 1
        raw_bytes = entry.get("bytes_raw")
        raw_sha = entry.get("sha256_raw")
        if not isinstance(raw_bytes, int) or not isinstance(raw_sha, str):
            errors.append(("VERIFY_MANIFEST_TOTALS", "%s: missing raw fields" % entry.get("path")))
            continue
        total_raw += raw_bytes
        if mode == "raw":
            if entry.get("bytes_canonical_lf") is not None or entry.get("sha256_canonical_lf") is not None:
                errors.append(("VERIFY_HASH_MODE", "%s: binary entry has canonical fields" % entry.get("path")))
            if entry.get("bytes") != raw_bytes or entry.get("sha256") != raw_sha:
                errors.append(("VERIFY_MANIFEST_TOTALS", "%s: raw byte/sha mirror mismatch" % entry.get("path")))
            total_bytes += raw_bytes
        else:
            canonical_bytes = entry.get("bytes_canonical_lf")
            canonical_sha = entry.get("sha256_canonical_lf")
            if not isinstance(canonical_bytes, int) or not isinstance(canonical_sha, str):
                errors.append(("VERIFY_MANIFEST_TOTALS", "%s: missing canonical fields" % entry.get("path")))
                continue
            if entry.get("bytes") != canonical_bytes or entry.get("sha256") != canonical_sha:
                errors.append(("VERIFY_MANIFEST_TOTALS", "%s: canonical byte/sha mirror mismatch" % entry.get("path")))
            total_bytes += canonical_bytes
            total_canonical += canonical_bytes
    if manifest.get("hash_mode_counts") != counts:
        errors.append(("VERIFY_MANIFEST_TOTALS", "hash_mode_counts mismatch: %r != %r" % (manifest.get("hash_mode_counts"), counts)))
    if manifest.get("total_bytes") != total_bytes:
        errors.append(("VERIFY_MANIFEST_TOTALS", "total_bytes %r != %d" % (manifest.get("total_bytes"), total_bytes)))
    if manifest.get("total_bytes_canonical_lf") != total_canonical:
        errors.append(("VERIFY_MANIFEST_TOTALS", "total_bytes_canonical_lf %r != %d" % (manifest.get("total_bytes_canonical_lf"), total_canonical)))
    if manifest.get("total_bytes_raw") != total_raw:
        errors.append(("VERIFY_MANIFEST_TOTALS", "total_bytes_raw %r != %d" % (manifest.get("total_bytes_raw"), total_raw)))
    committed_counts = {"canonical_lf": 0, "raw": 0, "not_committed": 0, "mismatch": 0}
    for entry in files:
        mode = entry.get("committed_blob_mode")
        if mode not in committed_counts:
            errors.append(("VERIFY_COMMITTED_MODE", "%s: %r" % (entry.get("path"), mode)))
            continue
        committed_counts[mode] += 1
        if mode in ("canonical_lf", "raw"):
            if not isinstance(entry.get("committed_blob_bytes"), int) or not isinstance(entry.get("committed_blob_sha256"), str):
                errors.append(("VERIFY_COMMITTED_MODE", "%s: missing committed blob bytes/sha" % entry.get("path")))
    if manifest.get("committed_blob_mode_counts") != committed_counts:
        errors.append(("VERIFY_MANIFEST_TOTALS", "committed_blob_mode_counts mismatch: %r != %r" % (manifest.get("committed_blob_mode_counts"), committed_counts)))
    return errors


def source_paths(source, root, rev):
    prefix = scope_prefix(root)
    manifest_rel = prefix + "/data_manifest.json"
    if source == "worktree":
        return worktree_paths(DEFAULT_MANIFEST), None
    if source == "git":
        code, out, err = git_output(["ls-tree", "-r", "--name-only", rev, "--", prefix], root)
        if code != 0:
            return None, "VERIFY_GIT_ERROR: ls-tree %s failed: %s" % (rev, err.decode("utf-8", "replace").strip())
        repo_paths = [line for line in out.decode("utf-8").splitlines() if line.strip()]
        run_rel = run_dir_rel_repo(root) + "/"
        paths = sorted(p[len(run_rel):] for p in repo_paths if p != manifest_rel)
        has_manifest = manifest_rel in repo_paths
    else:  # index
        code, out, err = git_output(["ls-files", "-z", "--", prefix], root)
        if code != 0:
            return None, "VERIFY_GIT_ERROR: ls-files failed: %s" % err.decode("utf-8", "replace").strip()
        repo_paths = [p for p in out.decode("utf-8").split("\0") if p]
        run_rel = run_dir_rel_repo(root) + "/"
        paths = sorted(p[len(run_rel):] for p in repo_paths if p != manifest_rel)
        has_manifest = manifest_rel in repo_paths
    if not has_manifest:
        return paths, "VERIFY_MANIFEST_NOT_COMMITTED: %s missing from %s" % (manifest_rel, source)
    return paths, None


def read_source_bytes(source, root, rev, rel):
    repo_rel = run_dir_rel_repo(root) + "/" + rel
    if source == "worktree":
        target = RUN_DIR / rel
        if not target.is_file():
            return None, "VERIFY_FILE_MISSING"
        return target.read_bytes(), None
    if source == "git":
        code, out, err = git_output(["cat-file", "blob", "%s:%s" % (rev, repo_rel)], root)
    else:
        code, out, err = git_output(["show", ":" + repo_rel], root)
    if code != 0:
        return None, "VERIFY_FILE_MISSING: %s: %s" % (repo_rel, err.decode("utf-8", "replace").strip())
    return out, None


def verify_manifest(manifest, source, rev):
    errors = manifest_structure_errors(manifest)
    files = manifest.get("files") or []
    root = repo_root()
    paths, scope_error = source_paths(source, root, rev)
    if scope_error:
        errors.append(("VERIFY_SCOPE", scope_error))
        paths = []
    manifest_paths = [f.get("path") for f in files]
    path_set = set(manifest_paths)
    source_set = set(paths or [])
    for extra in sorted(source_set - path_set):
        errors.append(("VERIFY_EXTRA_FILES", extra))
    for missing in sorted(path_set - source_set):
        errors.append(("VERIFY_FILE_MISSING", missing))
    checked = 0
    blob_modes = {"raw": 0, "canonical_lf": 0}
    for entry in files:
        rel = entry.get("path")
        data, read_error = read_source_bytes(source, root, rev, rel)
        if read_error:
            errors.append((read_error.split(":", 1)[0], read_error))
            continue
        checked += 1
        if source == "worktree":
            if len(data) != entry.get("bytes_raw"):
                errors.append(("VERIFY_BYTES_MISMATCH", "%s: bytes_raw %d != %r" % (rel, len(data), entry.get("bytes_raw"))))
                continue
            if sha256_bytes(data) != entry.get("sha256_raw"):
                errors.append(("VERIFY_SHA_MISMATCH", "%s: sha256_raw mismatch" % rel))
                continue
            canon = canonical_lf(data)
            if entry.get("hash_mode") == "raw":
                if canon is not None:
                    errors.append(("VERIFY_HASH_MODE_MISMATCH", "%s: source is text but manifest says binary" % rel))
                continue
            if canon is None:
                errors.append(("VERIFY_HASH_MODE_MISMATCH", "%s: source is binary but manifest says text" % rel))
                continue
            if sha256_bytes(canon) != entry.get("sha256_canonical_lf"):
                errors.append(("VERIFY_CANONICAL_MISMATCH", "%s: sha256_canonical_lf mismatch" % rel))
            elif len(canon) != entry.get("bytes_canonical_lf"):
                errors.append(("VERIFY_CANONICAL_MISMATCH", "%s: bytes_canonical_lf %d != %r" % (rel, len(canon), entry.get("bytes_canonical_lf"))))
            continue
        # --source git / index: detect how each blob is actually stored. Repo
        # .gitattributes normalises most text to LF (canonical form), but git keeps
        # some files as -text (e.g. *.log, CRLF preserved). Both are accepted when they
        # match the recorded form; the effective mode must equal committed_blob_mode.
        if entry.get("committed_blob_mode") not in ("raw", "canonical_lf"):
            errors.append(("VERIFY_COMMITTED_MODE", "%s: committed_blob_mode %r" % (rel, entry.get("committed_blob_mode"))))
        blob_sha = sha256_bytes(data)
        raw_match = len(data) == entry.get("bytes_raw") and blob_sha == entry.get("sha256_raw")
        direct_canon_match = (
            entry.get("hash_mode") == "canonical_lf"
            and len(data) == entry.get("bytes_canonical_lf")
            and blob_sha == entry.get("sha256_canonical_lf")
        )
        # content consistency: blob text normalised CRLF->LF must equal the recorded
        # canonical form even when the stored blob preserved CRLF (effective mode raw).
        canon = canonical_lf(data)
        canon_content_match = (
            canon is not None
            and len(canon) == entry.get("bytes_canonical_lf")
            and sha256_bytes(canon) == entry.get("sha256_canonical_lf")
        )
        if entry.get("hash_mode") == "raw":
            effective = "raw" if raw_match else None
        elif direct_canon_match:
            effective = "canonical_lf"
        elif raw_match:
            effective = "raw"
        else:
            effective = None
        if effective == "raw" and entry.get("hash_mode") == "canonical_lf" and not canon_content_match:
            errors.append(("VERIFY_CANONICAL_MISMATCH", "%s: raw-form blob normalises to a different canonical hash" % rel))
        if effective is None:
            errors.append(("VERIFY_BLOB_MISMATCH", "%s: blob matches neither raw nor canonical-LF form" % rel))
        else:
            blob_modes[effective] += 1
            expected_mode = entry.get("committed_blob_mode")
            if expected_mode in ("raw", "canonical_lf") and expected_mode != effective:
                errors.append(("VERIFY_COMMITTED_MODE_MISMATCH", "%s: committed_blob_mode %s != actual %s" % (rel, expected_mode, effective)))
        if entry.get("committed_blob_bytes") is not None and entry.get("committed_blob_bytes") != len(data):
            errors.append(("VERIFY_COMMITTED_BLOB_MISMATCH", "%s: committed_blob_bytes %r != %d" % (rel, entry.get("committed_blob_bytes"), len(data))))
        if entry.get("committed_blob_sha256") is not None and entry.get("committed_blob_sha256") != blob_sha:
            errors.append(("VERIFY_COMMITTED_BLOB_MISMATCH", "%s: committed_blob_sha256 mismatch" % rel))
    return errors, checked, len(files), len(source_set), blob_modes


def main(argv=None):
    parser = argparse.ArgumentParser(description="Freeze/verify D-12D-005 BATCH1B evidence/v1b (zero solver).")
    parser.add_argument("--verify", action="store_true", help="replay the manifest instead of building it")
    parser.add_argument("--source", choices=("git", "index", "worktree"), default="git", help="replay source for --verify (default: git)")
    parser.add_argument("--rev", default="HEAD", help="git revision for --source git (default: HEAD)")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="manifest path (default: evidence/v1b/data_manifest.json)")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest).resolve()
    try:
        if not args.verify:
            manifest = build_manifest(manifest_path)
            write_text(manifest_path, json_text(manifest))
            print("MANIFEST_WRITTEN path=%s" % manifest_path)
            print(
                "entries=%d canonical_lf=%d raw=%d total_bytes=%d total_canonical_lf=%d total_raw=%d"
                % (
                    manifest["file_count"],
                    manifest["hash_mode_counts"]["canonical_lf"],
                    manifest["hash_mode_counts"]["raw"],
                    manifest["total_bytes"],
                    manifest["total_bytes_canonical_lf"],
                    manifest["total_bytes_raw"],
                )
            )
            errors, checked, expected, found, _ = verify_manifest(manifest, "worktree", args.rev)
            if errors:
                print("SELF_VERIFY_FAIL errors=%d" % len(errors))
                for code, detail in errors:
                    print("  FAIL %s: %s" % (code, detail))
                return 2
            print("SELF_VERIFY_OK checked=%d/%d source=worktree files_in_scope=%d" % (checked, expected, found))
            return 0

        if not manifest_path.is_file():
            print("VERIFY_FAIL manifest missing: %s" % manifest_path)
            return 2
        manifest = load_json(manifest_path)
        errors, checked, expected, found, blob_modes = verify_manifest(manifest, source=args.source, rev=args.rev)
        if errors:
            print("VERIFY_FAIL source=%s rev=%s errors=%d" % (args.source, args.rev if args.source == "git" else "-", len(errors)))
            for code, detail in errors:
                print("  FAIL %s: %s" % (code, detail))
            return 2
        print(
            "VERIFY_OK source=%s rev=%s entries=%d/%d files_in_scope=%d total_bytes=%d total_canonical_lf=%d raw_blobs=%d canonical_lf_blobs=%d"
            % (
                args.source,
                args.rev if args.source == "git" else "-",
                checked,
                expected,
                found,
                manifest["total_bytes"],
                manifest["total_bytes_canonical_lf"],
                blob_modes["raw"],
                blob_modes["canonical_lf"],
            )
        )
        return 0
    except RuntimeError as exc:
        print("ERROR %s" % exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
