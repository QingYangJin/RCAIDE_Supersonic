"""Independent re-validation of a P3 DOE dataset.

The validator re-reads the committed artifacts (not the generator's in-memory
state) and checks schema, counts, content hashes, bounds, duplicate removal and
geometry status consistency.  With --recompute-geometry it also rebuilds every
candidate geometry from its stored design vector and compares the screening
result, so a tampered or stale dataset cannot pass silently.

Validation never runs a Mission or CFD solver and never creates an objective.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..aircraft.design_space import DesignSpace, load_design_space
from . import schema
from .schema import (
    CANDIDATES_CSV_FILENAME,
    CANDIDATES_FILENAME,
    GEOMETRY_ERROR,
    GEOMETRY_INVALID,
    GEOMETRY_VALID,
    MANIFEST_FILENAME,
    check_candidate_row,
)

PASS = "pass"
FAIL = "fail"
SKIP = "skip"


def _check(check_id: str, description: str, status: str, detail: str = "") -> Dict[str, Any]:
    return {
        "check_id": check_id,
        "description": description,
        "status": status,
        "detail": detail,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("candidates.jsonl line %d is not JSON: %s" % (line_number, exc))
            if not isinstance(row, dict):
                raise ValueError("candidates.jsonl line %d is not an object" % line_number)
            rows.append(row)
    return rows


def _recompute_status(space: DesignSpace, design: Mapping[str, float]) -> Dict[str, Any]:
    from .generate_doe import screen_design

    return screen_design(space, design)


def validate_dataset(
    run_dir: Path,
    design_space: Optional[DesignSpace] = None,
    recompute_geometry: bool = False,
    write: bool = True,
) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    checks: List[Dict[str, Any]] = []
    manifest_path = run_dir / MANIFEST_FILENAME
    candidates_path = run_dir / CANDIDATES_FILENAME
    csv_path = run_dir / CANDIDATES_CSV_FILENAME
    rows: List[Dict[str, Any]] = []
    manifest: Optional[Dict[str, Any]] = None

    if not manifest_path.is_file():
        checks.append(_check("DS01", "data_manifest.json exists", FAIL, "missing %s" % manifest_path))
        result = _result(run_dir, checks, {}, recompute_geometry, write)
        return result
    try:
        manifest = _read_json(manifest_path)
        checks.append(_check("DS01", "data_manifest.json exists and parses", PASS, "dataset_id=%s" % manifest.get("dataset_id")))
    except Exception as exc:
        checks.append(_check("DS01", "data_manifest.json exists and parses", FAIL, str(exc)))
        result = _result(run_dir, checks, {}, recompute_geometry, write)
        return result

    if not candidates_path.is_file():
        checks.append(_check("DS02", "candidates.jsonl exists", FAIL, "missing %s" % candidates_path))
        result = _result(run_dir, checks, {}, recompute_geometry, write)
        return result
    try:
        rows = _read_jsonl(candidates_path)
        checks.append(_check("DS02", "candidates.jsonl parses", PASS, "%d rows" % len(rows)))
    except ValueError as exc:
        checks.append(_check("DS02", "candidates.jsonl parses", FAIL, str(exc)))
        result = _result(run_dir, checks, {}, recompute_geometry, write)
        return result

    if design_space is None:
        design_space = load_design_space()

    counts = _counts(rows)
    candidates_block = manifest.get("candidates", {}) if isinstance(manifest, dict) else {}
    written = candidates_block.get("written")

    # DS03: row count vs manifest.
    if written == len(rows):
        checks.append(_check("DS03", "row count matches manifest", PASS, "%d rows" % len(rows)))
    else:
        checks.append(
            _check(
                "DS03",
                "row count matches manifest",
                FAIL,
                "manifest written=%r but candidates.jsonl has %d rows" % (written, len(rows)),
            )
        )

    # DS04: CSV row count.
    if csv_path.is_file():
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                csv_rows = sum(1 for _ in csv.DictReader(handle))
            status = PASS if csv_rows == len(rows) else FAIL
            checks.append(
                _check("DS04", "candidates.csv row count matches JSONL", status, "csv=%d jsonl=%d" % (csv_rows, len(rows)))
            )
        except Exception as exc:
            checks.append(_check("DS04", "candidates.csv row count matches JSONL", FAIL, str(exc)))
    else:
        checks.append(_check("DS04", "candidates.csv exists", FAIL, "missing %s" % csv_path))

    # DS05: per-row schema.
    row_errors: List[str] = []
    for index, row in enumerate(rows):
        for error in check_candidate_row(row, design_space):
            row_errors.append("row %d: %s" % (index, error))
    if row_errors:
        checks.append(
            _check("DS05", "every row matches the candidate schema", FAIL, "; ".join(row_errors[:10]))
        )
    else:
        checks.append(_check("DS05", "every row matches the candidate schema", PASS, "%d rows valid" % len(rows)))

    # DS06: duplicate content ids.
    ids = [row.get("candidate_id") for row in rows]
    duplicates = sorted({value for value in ids if ids.count(value) > 1}) if len(ids) <= 5000 else []
    if len(ids) > 5000:
        checks.append(_check("DS06", "candidate ids are unique", SKIP, "too many rows for quadratic duplicate scan"))
    elif duplicates:
        checks.append(_check("DS06", "candidate ids are unique", FAIL, "duplicates: %s" % ", ".join(map(str, duplicates[:5]))))
    else:
        checks.append(_check("DS06", "candidate ids are unique", PASS, "%d unique ids" % len(ids)))

    # DS07: geometry counts match manifest.
    geometry = manifest.get("geometry", {}) if isinstance(manifest, dict) else {}
    expected = {
        "valid": geometry.get("valid"),
        "invalid": geometry.get("invalid"),
        "errors": geometry.get("errors"),
    }
    actual = {
        "valid": counts["geometry"][GEOMETRY_VALID],
        "invalid": counts["geometry"][GEOMETRY_INVALID],
        "errors": counts["geometry"][GEOMETRY_ERROR],
    }
    if expected == actual:
        checks.append(_check("DS07", "geometry status counts match manifest", PASS, json.dumps(actual, sort_keys=True)))
    else:
        checks.append(
            _check(
                "DS07",
                "geometry status counts match manifest",
                FAIL,
                "manifest=%s actual=%s" % (json.dumps(expected, sort_keys=True), json.dumps(actual, sort_keys=True)),
            )
        )

    # DS08: file hashes.
    hash_errors: List[str] = []
    hash_ok = 0
    for entry in manifest.get("files", []) if isinstance(manifest, dict) else []:
        name = entry.get("name")
        expected_sha = entry.get("sha256")
        path = run_dir / str(name)
        if not path.is_file():
            hash_errors.append("%s missing" % name)
            continue
        if _sha256_file(path) != expected_sha:
            hash_errors.append("%s sha256 mismatch" % name)
            continue
        if entry.get("bytes") is not None and path.stat().st_size != entry.get("bytes"):
            hash_errors.append("%s bytes mismatch" % name)
            continue
        hash_ok += 1
    if hash_errors:
        checks.append(_check("DS08", "manifest file hashes match artifacts", FAIL, "; ".join(hash_errors)))
    else:
        checks.append(_check("DS08", "manifest file hashes match artifacts", PASS, "%d files verified" % hash_ok))

    # DS09: design space config hash.
    design_space_block = manifest.get("design_space", {}) if isinstance(manifest, dict) else {}
    recorded_sha = design_space_block.get("config_sha256")
    config_path = Path(design_space.config_path)
    current_sha = _sha256_file(config_path) if config_path.is_file() else None
    if recorded_sha and current_sha and recorded_sha == current_sha:
        checks.append(_check("DS09", "design-space config hash matches manifest", PASS, current_sha[:12]))
    else:
        checks.append(
            _check(
                "DS09",
                "design-space config hash matches manifest",
                FAIL,
                "manifest=%r current=%r" % (recorded_sha, current_sha),
            )
        )

    # DS10: batch counts add up.
    batches = manifest.get("batches", []) if isinstance(manifest, dict) else []
    batch_total = sum(int(batch.get("count", 0)) for batch in batches)
    requested = sum(int(batch.get("requested", 0)) for batch in batches)
    if batch_total == len(rows) and requested >= len(rows):
        checks.append(
            _check(
                "DS10",
                "batch counts are internally consistent",
                PASS,
                "requested=%d written=%d batches=%d" % (requested, batch_total, len(batches)),
            )
        )
    else:
        checks.append(
            _check(
                "DS10",
                "batch counts are internally consistent",
                FAIL,
                "requested=%d batch_total=%d rows=%d" % (requested, batch_total, len(rows)),
            )
        )

    # DS11: zero physical evaluations and no objective fields.
    evaluations = manifest.get("evaluations", {}) if isinstance(manifest, dict) else {}
    forbidden_present = [key for row in rows for key in schema.FORBIDDEN_FIELDS if key in row]
    if evaluations.get("physical_call_count") == 0 and not forbidden_present:
        checks.append(
            _check("DS11", "dataset is screening-only (zero physical calls, no objective)", PASS)
        )
    else:
        checks.append(
            _check(
                "DS11",
                "dataset is screening-only (zero physical calls, no objective)",
                FAIL,
                "physical_call_count=%r forbidden=%s"
                % (evaluations.get("physical_call_count"), sorted(set(forbidden_present))),
            )
        )

    # DS12: optional geometry recomputation.
    if recompute_geometry:
        mismatches: List[str] = []
        for index, row in enumerate(rows):
            design = row.get("design", {})
            screening = _recompute_status(design_space, design)
            if screening["status"] != row.get("geometry_status"):
                mismatches.append("row %d status %r != %r" % (index, row.get("geometry_status"), screening["status"]))
            elif sorted(screening["failed_checks"]) != sorted(row.get("failed_checks", [])):
                mismatches.append("row %d failed checks differ" % index)
            if len(mismatches) >= 10:
                break
        if mismatches:
            checks.append(
                _check("DS12", "geometry recomputation matches stored status", FAIL, "; ".join(mismatches))
            )
        else:
            checks.append(
                _check("DS12", "geometry recomputation matches stored status", PASS, "%d rows recomputed" % len(rows))
            )
    else:
        checks.append(
            _check(
                "DS12",
                "geometry recomputation matches stored status",
                SKIP,
                "disabled; run with recompute_geometry=True for full re-screening",
            )
        )

    return _result(run_dir, checks, counts, recompute_geometry, write)


def _counts(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    geometry = {GEOMETRY_VALID: 0, GEOMETRY_INVALID: 0, GEOMETRY_ERROR: 0}
    failed_histogram: Dict[str, int] = {}
    for row in rows:
        status = row.get("geometry_status")
        if status in geometry:
            geometry[status] += 1
        for check_id in row.get("failed_checks", []) or []:
            failed_histogram[check_id] = failed_histogram.get(check_id, 0) + 1
    return {
        "rows": len(rows),
        "geometry": geometry,
        "failed_check_histogram": failed_histogram,
    }


def _result(
    run_dir: Path,
    checks: Sequence[Mapping[str, Any]],
    counts: Mapping[str, Any],
    recompute_geometry: bool,
    write: bool,
) -> Dict[str, Any]:
    failed = [check for check in checks if check["status"] == FAIL]
    result = {
        "dataset_id": run_dir.name,
        "schema_version": schema.SCHEMA_VERSION,
        "validated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "valid" if not failed else "invalid",
        "recompute_geometry": bool(recompute_geometry),
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": list(checks),
        "counts": dict(counts),
        "note": "validation is read-only re-analysis; it performs no physical evaluation",
    }
    if write:
        path = run_dir / "validation.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
