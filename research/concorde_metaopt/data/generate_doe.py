"""P3 DOE candidate generation (geometry screening only, zero physics).

The P3 contract asks for batches of LHS/Sobol design vectors (32, 128, 512,
1500-2000) whose geometry is validated *before* any physical evaluation budget
is spent.  This module implements exactly that first half: it samples the frozen
15D box, screens each sample with the dependency-free geometry model and writes
a dataset whose manifest records provenance and zero real evaluations.

No Mission, VLM, VSPAERO or SU2 call happens here.  A candidate row never
carries an objective (see data/schema.py); physical evaluation of selected
candidates is a separate, budget-gated step.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..aircraft.design_space import (
    DesignSpace,
    DesignSpaceError,
    load_design_space,
)
from ..aircraft.geometry_checks import (
    FAIL,
    _display_path,
    _git_sha,
    _software_versions,
    _write_csv,
    _write_json,
    _write_jsonl,
    metrics as geometry_metrics,
)
from ..aircraft.geometry_model import GeometryError, build_geometry
from ..aircraft.geometry_checks import model_checks
from . import schema
from .validate_dataset import validate_dataset

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"
STAGE = "P3"
METHOD = "doe_screening"
DEFAULT_METHOD = "lhs"
DEFAULT_SEED = 42
MAX_TOTAL_CANDIDATES = 5000
MANIFEST_FILENAME = schema.MANIFEST_FILENAME
CANDIDATES_FILENAME = schema.CANDIDATES_FILENAME
CANDIDATES_CSV_FILENAME = schema.CANDIDATES_CSV_FILENAME
SUMMARY_FILENAME = schema.SUMMARY_FILENAME


class DoEError(RuntimeError):
    pass


def parse_batch_sizes(value: Any) -> List[int]:
    if isinstance(value, int):
        sizes = [value]
    elif isinstance(value, (list, tuple)):
        sizes = [int(item) for item in value]
    elif isinstance(value, str):
        cleaned = value.replace(" ", "")
        if not cleaned:
            raise DoEError("empty batch size specification")
        try:
            sizes = [int(item) for item in cleaned.split(",")]
        except ValueError as exc:
            raise DoEError("cannot parse batch sizes %r: %s" % (value, exc))
    else:
        raise DoEError("unsupported batch size specification %r" % (value,))
    if not sizes:
        raise DoEError("at least one batch is required")
    if any(size <= 0 for size in sizes):
        raise DoEError("batch sizes must be positive: %r" % (sizes,))
    total = sum(sizes)
    if total > MAX_TOTAL_CANDIDATES:
        raise DoEError(
            "requested %d candidates exceeds the guard %d; split the batches deliberately"
            % (total, MAX_TOTAL_CANDIDATES)
        )
    return sizes


def generate_unit_samples(method: str, seed: int, count: int, dimension: int) -> List[List[float]]:
    from scipy.stats import qmc

    if method == "lhs":
        engine = qmc.LatinHypercube(d=dimension, seed=int(seed))
        samples = engine.random(count)
    elif method == "sobol":
        engine = qmc.Sobol(d=dimension, scramble=True, seed=int(seed))
        samples = engine.random(count)
    else:
        raise DoEError("unknown DOE method %r (expected one of %r)" % (method, schema.METHODS))
    clipped = np.clip(np.asarray(samples, dtype=float), 1e-12, 1.0 - 1e-12)
    if clipped.shape != (count, dimension):
        raise DoEError("sampler returned shape %r, expected %r" % (clipped.shape, (count, dimension)))
    return [[float(value) for value in row] for row in clipped]


def screen_design(space: DesignSpace, design: Mapping[str, float]) -> Dict[str, Any]:
    started = time.perf_counter()
    violations = space.check_physical(dict(design))
    if violations:
        return {
            "status": schema.GEOMETRY_INVALID,
            "error": "design space violation: " + "; ".join(violations),
            "failed_checks": [],
            "warned_checks": [],
            "metrics": {},
            "wall_seconds": time.perf_counter() - started,
        }
    try:
        expanded = space.expand({name: float(design[name]) for name in space.names})
        geometry = build_geometry(tuple(expanded), tuple(expanded.values()))
    except GeometryError as exc:
        return {
            "status": schema.GEOMETRY_ERROR,
            "error": "%s: %s" % (type(exc).__name__, exc),
            "failed_checks": [],
            "warned_checks": [],
            "metrics": {},
            "wall_seconds": time.perf_counter() - started,
        }
    checks = model_checks(geometry, space)
    failed = [check.check_id for check in checks if check.status == FAIL]
    warned = [check.check_id for check in checks if check.status == "warn"]
    return {
        "status": schema.GEOMETRY_INVALID if failed else schema.GEOMETRY_VALID,
        "error": None,
        "failed_checks": failed,
        "warned_checks": warned,
        "metrics": geometry_metrics(geometry),
        "wall_seconds": time.perf_counter() - started,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_entry(path: Path, rows: Optional[int], role: str) -> Dict[str, Any]:
    return {
        "role": role,
        "name": path.name,
        "path": _display_path(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "rows": rows,
    }


def _design_space_record(space: DesignSpace) -> Dict[str, Any]:
    config_path = Path(space.config_path)
    record = space.config_summary()
    record["config_path"] = _display_path(space.config_path)
    record["config_sha256"] = _sha256_file(config_path) if config_path.is_file() else None
    record["bounds"] = {
        variable.id: {"name": variable.name, "lower": variable.lower, "upper": variable.upper, "unit": variable.unit}
        for variable in space.variables
    }
    return record


def _environment(space: DesignSpace) -> Dict[str, Any]:
    return {
        "python": sys.version,
        "python_executable": _display_path(sys.executable),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "numpy": getattr(np, "__version__", None),
        "packages": _software_versions(),
        "design_space_config": _display_path(space.config_path),
        "screening": "dependency-free geometry model (no RCAIDE Mission, no VLM, no CFD)",
    }


def _candidate_csv_row(row: Mapping[str, Any], space: DesignSpace) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "candidate_id": row["candidate_id"],
        "batch_id": row["batch_id"],
        "batch_index": row["batch_index"],
        "sample_index": row["sample_index"],
        "method": row["method"],
        "seed": row["seed"],
        "geometry_status": row["geometry_status"],
        "geometry_error": row["geometry_error"],
        "failed_checks": ";".join(row["failed_checks"]),
        "warned_checks": ";".join(row["warned_checks"]),
        "evaluation_status": row["evaluation_status"],
        "physical_call_count": row["physical_call_count"],
    }
    for name in space.names:
        output["design_" + name] = row["design"][name]
    for key, value in row["metrics"].items():
        output["metric_" + key] = value
    return output


def _summary_base(run_id: str, git_sha: Optional[str], space: DesignSpace, method: str, seed: int) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "stage": STAGE,
        "task_id": space.task_id,
        "method": METHOD,
        "seed": int(seed),
        "git_sha": git_sha,
        "solver_versions": _software_versions(),
        "design_dim": len(space.variables),
        "status": "doe_completed",
        "total_true_evaluations": 0,
        "low_fidelity_calls": 0,
        "su2_calls": 0,
        "invalid_count": 0,
        "failed_count": 0,
        "first_feasible_evaluation": None,
        "best_feasible_fuel_kg": None,
        "best_design_id": None,
        "wall_seconds": None,
        "cpu_seconds_if_available": None,
        "artifacts": {},
        "objective": {
            "direction": "minimize",
            "name": "fuel_burn_kg",
            "unit": "kg",
            "status": "not_evaluated_in_doe_screening",
        },
        "doe": {
            "method": method,
            "requested_candidates": 0,
            "written_candidates": 0,
            "duplicates_removed": 0,
            "batches": [],
            "note": "zero physical evaluations; geometry screening only",
        },
    }


def _run_readme(summary: Mapping[str, Any], manifest: Mapping[str, Any]) -> str:
    doe = summary["doe"]
    lines = [
        "# DOE screening run %s" % summary["run_id"],
        "",
        "Stage: %s | method: %s | git: %s | seed: %s" % (summary["stage"], summary["method"], summary["git_sha"], summary["seed"]),
        "",
        "This run only samples and screens geometry. It performs **zero** Mission,",
        "VLM, VSPAERO or SU2 calls; no candidate has an objective value.",
        "",
        "## Counts",
        "",
        "- requested candidates: %s" % doe["requested_candidates"],
        "- written candidates: %s" % doe["written_candidates"],
        "- duplicates removed: %s" % doe["duplicates_removed"],
        "- geometry valid: %s" % manifest["geometry"]["valid"],
        "- geometry invalid: %s" % manifest["geometry"]["invalid"],
        "- geometry errors: %s" % manifest["geometry"]["errors"],
        "- physical evaluations: 0 (this is not an optimisation run)",
        "",
        "## Files",
        "",
        "- candidates.jsonl / candidates.csv: one row per candidate",
        "- data_manifest.json: provenance, config hashes and file hashes",
        "- validation.json: independent re-validation report (if enabled)",
        "- run_config.json / environment.json / summary.json",
        "",
        "## Method",
        "",
        "Batches: %s" % ", ".join(
            "%s (%d samples, %s)" % (batch["batch_id"], batch["count"], batch["method"]) for batch in doe["batches"]
        ),
        "",
        "Sampling is scipy qmc (%s) over the frozen unit box, mapped through the" % doe["method"],
        "design-space config (%s, %sD). Geometry legality is screened with the same" % (
            manifest["design_space"].get("design_set", "15d"), manifest["design_dim"]
        ),
        "dependency-free model used by geometry-check; failed checks are recorded,",
        "never converted into a fake objective.",
        "",
        "## Limitations",
        "",
        "- bounds are still provisional_until_geometry_perturbation (frozen: false)",
        "- no aerodynamic or mission validity is claimed for any candidate",
        "- P3 physical evaluation of candidates requires an approved budget",
    ]
    return "\n".join(lines) + "\n"


def run_doe(
    output_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    batch_sizes: Any = (32,),
    method: str = DEFAULT_METHOD,
    seed: int = DEFAULT_SEED,
    design_space: Optional[DesignSpace] = None,
    allow_existing: bool = False,
    validate: bool = True,
    recompute_geometry: bool = False,
) -> Dict[str, Any]:
    started = time.perf_counter()
    sizes = parse_batch_sizes(batch_sizes)
    if method not in schema.METHODS:
        raise DoEError("unknown DOE method %r (expected one of %r)" % (method, schema.METHODS))
    space = design_space or load_design_space()
    root = Path(output_root) if output_root else DEFAULT_OUTPUT_ROOT
    identifier = run_id or "doe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_dir = root / identifier
    if run_dir.exists() and not allow_existing:
        raise FileExistsError("run directory already exists: %s" % run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    git_sha = _git_sha(REPO_ROOT)
    summary = _summary_base(identifier, git_sha, space, method, seed)
    batches: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    seen: Dict[str, str] = {}
    duplicates = 0
    requested_total = 0
    for batch_index, count in enumerate(sizes):
        requested_total += count
        batch_id = "batch-%03d" % batch_index
        batch_seed = int(seed) + batch_index
        fractions = generate_unit_samples(method, batch_seed, count, len(space.variables))
        written = 0
        for sample_index, fraction in enumerate(fractions):
            design = space.from_unit_interval(fraction)
            physical = {name: design[name] for name in space.names}
            key = schema.canonical_design(physical, space.names)
            if key in seen:
                duplicates += 1
                continue
            seen[key] = batch_id
            screening = screen_design(space, physical)
            row = schema.make_candidate_row(
                space,
                physical,
                batch_id=batch_id,
                batch_index=batch_index,
                sample_index=sample_index,
                method=method,
                seed=batch_seed,
                geometry_status=screening["status"],
                geometry_error=screening["error"],
                failed_checks=screening["failed_checks"],
                warned_checks=screening["warned_checks"],
                metrics=screening["metrics"],
                wall_seconds=screening["wall_seconds"],
            )
            rows.append(row)
            written += 1
        batches.append(
            {
                "batch_id": batch_id,
                "batch_index": batch_index,
                "count": written,
                "requested": count,
                "seed": batch_seed,
                "method": method,
            }
        )
    if not rows:
        raise DoEError("sampling produced no candidates")

    valid = sum(1 for row in rows if row["geometry_status"] == schema.GEOMETRY_VALID)
    invalid = sum(1 for row in rows if row["geometry_status"] == schema.GEOMETRY_INVALID)
    errors = sum(1 for row in rows if row["geometry_status"] == schema.GEOMETRY_ERROR)
    failed_histogram: Dict[str, int] = {}
    for row in rows:
        for check_id in row["failed_checks"]:
            failed_histogram[check_id] = failed_histogram.get(check_id, 0) + 1

    candidates_path = run_dir / CANDIDATES_FILENAME
    csv_path = run_dir / CANDIDATES_CSV_FILENAME
    _write_jsonl(candidates_path, rows)
    _write_csv(csv_path, [_candidate_csv_row(row, space) for row in rows])

    environment = _environment(space)
    environment_path = run_dir / "environment.json"
    _write_json(environment_path, environment, True)

    run_config = {
        "run_id": identifier,
        "stage": STAGE,
        "method": METHOD,
        "sampler": method,
        "seed": int(seed),
        "batch_sizes": sizes,
        "batches": batches,
        "design_dim": len(space.variables),
        "design_space": _design_space_record(space),
        "screening": {
            "geometry_model_only": True,
            "mission_calls": 0,
            "vlm_calls": 0,
            "cfd_calls": 0,
            "rcaide_rebuild": False,
        },
        "git_sha": git_sha,
        "note": "DOE screening only; physical evaluation requires a separate approved budget.",
    }
    run_config_path = run_dir / "run_config.json"
    _write_json(run_config_path, run_config, True)

    manifest = {
        "dataset_id": identifier,
        "schema_version": schema.SCHEMA_VERSION,
        "schema": schema.schema_summary(),
        "stage": STAGE,
        "task_id": space.task_id,
        "method": METHOD,
        "sampler": method,
        "seed": int(seed),
        "design_dim": len(space.variables),
        "git_sha": git_sha,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "design_space": _design_space_record(space),
        "batches": batches,
        "candidates": {
            "requested": requested_total,
            "written": len(rows),
            "duplicates_removed": duplicates,
            "valid": valid,
            "invalid": invalid,
            "errors": errors,
            "failed_check_histogram": failed_histogram,
        },
        "geometry": {
            "valid": valid,
            "invalid": invalid,
            "errors": errors,
            "screening": "geometry_model.build_geometry + model_checks (no RCAIDE)",
        },
        "evaluations": {
            "physical_call_count": 0,
            "objective_fields_present": False,
            "note": "no physical evaluation was performed; see P3 budget gate",
        },
        "files": [
            _file_entry(candidates_path, len(rows), "candidates"),
            _file_entry(csv_path, len(rows), "candidates_csv"),
            _file_entry(run_config_path, None, "run_config"),
            _file_entry(environment_path, None, "environment"),
        ],
        "limitations": [
            "design-space bounds are still provisional_until_geometry_perturbation (frozen: false)",
            "geometry legality does not imply aerodynamic or mission validity",
            "no low/high fidelity identity or CFD applicability has been established yet",
        ],
    }
    manifest_path = run_dir / MANIFEST_FILENAME
    _write_json(manifest_path, manifest, True)

    summary["doe"].update(
        {
            "requested_candidates": requested_total,
            "written_candidates": len(rows),
            "duplicates_removed": duplicates,
            "batches": batches,
            "geometry_valid": valid,
            "geometry_invalid": invalid,
            "geometry_errors": errors,
        }
    )
    summary["invalid_count"] = invalid
    summary["failed_count"] = errors
    summary["wall_seconds"] = time.perf_counter() - started
    summary["cpu_seconds_if_available"] = None
    summary["artifacts"] = {
        "candidates": _display_path(candidates_path),
        "candidates_csv": _display_path(csv_path),
        "data_manifest": _display_path(manifest_path),
        "run_config": _display_path(run_config_path),
        "environment": _display_path(environment_path),
        "summary": _display_path(run_dir / SUMMARY_FILENAME),
    }

    validation: Optional[Dict[str, Any]] = None
    if validate:
        validation = validate_dataset(run_dir, design_space=space, recompute_geometry=recompute_geometry)
        validation_path = run_dir / "validation.json"
        summary["artifacts"]["validation"] = _display_path(validation_path)
        summary["doe"]["validation_status"] = validation["status"]
        summary["doe"]["validation_checks"] = validation["checks"]

    (run_dir / "README.md").write_text(_run_readme(summary, manifest), encoding="utf-8")
    summary["artifacts"]["readme"] = _display_path(run_dir / "README.md")
    _write_json(run_dir / SUMMARY_FILENAME, summary, True)
    _update_index(run_dir, summary)
    return summary


def _index_summary(summary: Mapping[str, Any]) -> Dict[str, Any]:
    doe = summary.get("doe", {})
    return {
        "requested_candidates": doe.get("requested_candidates"),
        "written_candidates": doe.get("written_candidates"),
        "geometry_valid": doe.get("geometry_valid"),
        "geometry_invalid": doe.get("geometry_invalid"),
        "physical_evaluations": 0,
    }


def _update_index(run_dir: Path, summary: Mapping[str, Any]) -> Path:
    index_path = run_dir.parent / "index.json"
    payload: Dict[str, Any] = {"runs": [], "updated_at": None}
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("runs"), list):
                payload = existing
        except json.JSONDecodeError:
            payload = {"runs": [], "updated_at": None}
    entries = [entry for entry in payload.get("runs", []) if entry.get("run_id") != summary["run_id"]]
    entries.append(
        {
            "run_id": summary["run_id"],
            "stage": STAGE,
            "task_id": summary.get("task_id"),
            "method": METHOD,
            "git_sha": summary.get("git_sha"),
            "status": summary.get("status"),
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "path": run_dir.name,
            "summary": _index_summary(summary),
            "true_evaluations": 0,
        }
    )
    payload["runs"] = entries
    payload["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_json(index_path, payload, True)
    return index_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate and screen a P3 DOE candidate dataset")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--n", default="32", help="batch sizes, e.g. 32 or 32,128,512")
    parser.add_argument("--method", default=DEFAULT_METHOD, choices=list(schema.METHODS))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--allow-existing", action="store_true")
    parser.add_argument("--no-validate", action="store_true")
    parser.add_argument("--recompute-geometry", action="store_true")
    args = parser.parse_args(argv)
    summary = run_doe(
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        batch_sizes=args.n,
        method=args.method,
        seed=args.seed,
        allow_existing=args.allow_existing,
        validate=not args.no_validate,
        recompute_geometry=args.recompute_geometry,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
