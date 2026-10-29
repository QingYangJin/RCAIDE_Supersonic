"""OpenVSP geometry-export check for the provisional 15-variable model.

The RCAIDE environment runs on Python 3.11 and cannot import the OpenVSP _vsp
extension, which is compiled for Python 3.9. This module therefore acts only as
the orchestrator: it builds a JSON request from the dependency-free geometry
model, executes the standalone worker openvsp_geometry.py with an external
Python 3.9 interpreter, measures the exported STL files with trimesh, and
compares the OpenVSP-derived quantities with the model.

This is a geometry-export check. It performs no aerodynamic or Mission
evaluation and reports no objective value. The known OpenVSP fuselage spline
overshoot is recorded as a warning rather than silently accepted.

Environment / CLI inputs (no machine paths are stored in committed artifacts):

    CONCORDE_OPENVSP_PYTHON   Python 3.9 interpreter that can import openvsp
    CONCORDE_OPENVSP_ROOT     OpenVSP installation root

Both may also be passed with --openvsp-python / --openvsp-root.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .design_space import DesignSpace, load_design_space
from .geometry_builder import build_geometry
from .geometry_checks import (
    _display_path,
    _git_sha,
    _software_versions,
    _write_csv,
    _write_json,
)
from .geometry_model import (
    GEOMETRY_MODEL_VERSION,
    TAIL_ORIGIN_X_M,
    WING_ORIGIN_X_M,
    ConcordeGeometry,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"
DEFAULT_EXPORT_ROOT = REPO_ROOT / "outputs" / "concorde_metaopt"
DEFAULT_WORKER = Path(__file__).with_name("openvsp_geometry.py")
DEFAULT_TIMEOUT_S = 900.0

WING_ORIGIN_M = (WING_ORIGIN_X_M, 0.0, -0.8)
TAIL_ORIGIN_M = (TAIL_ORIGIN_X_M, 0.0, 1.0)
TAIL_ROTATION_DEG = (90.0, 0.0, 0.0)

BASELINE_COMPONENTS = ("main_wing", "vertical_tail", "fuselage")


class OpenVSPSetupError(RuntimeError):
    """Raised when the external OpenVSP Python environment is not configured."""


def resolve_openvsp_paths(
    openvsp_python: Optional[str] = None,
    openvsp_root: Optional[str] = None,
) -> Tuple[Path, Path]:
    python_value = openvsp_python or os.environ.get("CONCORDE_OPENVSP_PYTHON")
    root_value = openvsp_root or os.environ.get("CONCORDE_OPENVSP_ROOT")
    if not python_value or not root_value:
        raise OpenVSPSetupError(
            "OpenVSP Python is not configured: pass --openvsp-python and "
            "--openvsp-root, or set CONCORDE_OPENVSP_PYTHON and "
            "CONCORDE_OPENVSP_ROOT."
        )
    python_path = Path(python_value).expanduser()
    root_path = Path(root_value).expanduser()
    if not python_path.is_file():
        raise OpenVSPSetupError("OpenVSP Python interpreter does not exist: %s" % python_path)
    if not (root_path / "python" / "openvsp").is_dir():
        raise OpenVSPSetupError(
            "OpenVSP root does not contain python/openvsp: %s" % root_path
        )
    return python_path, root_path


def openvsp_version_from_root(openvsp_root: Path) -> Optional[str]:
    match = re.search(r"OpenVSP-([0-9]+(?:\.[0-9]+)*)", Path(openvsp_root).name)
    return match.group(1) if match else None


def build_openvsp_request(
    geometry: ConcordeGeometry,
    export_directory: Path,
    basename: str = "concorde_full",
    formats: Sequence[str] = ("stl", "step", "vsp3"),
) -> Dict[str, Any]:
    def wing_sections(component) -> List[Dict[str, float]]:
        return [
            {
                "percent_span_location": float(section.percent_span_location),
                "chord_m": float(section.chord_m),
                "leading_edge_x_m": float(section.leading_edge_x_m),
            }
            for section in component.sections
        ]

    components: List[Dict[str, Any]] = [
        {
            "kind": "wing",
            "name": "main_wing",
            "symmetric": True,
            "span_m": float(geometry.wing.span_m),
            "location": list(WING_ORIGIN_M),
            "rotation": [0.0, 0.0, 0.0],
            "sections": wing_sections(geometry.wing),
        },
        {
            "kind": "wing",
            "name": "vertical_tail",
            "symmetric": False,
            "span_m": float(geometry.vertical_tail.span_m),
            "location": list(TAIL_ORIGIN_M),
            "rotation": list(TAIL_ROTATION_DEG),
            "sections": wing_sections(geometry.vertical_tail),
        },
        {
            "kind": "fuselage",
            "name": "fuselage",
            "length_m": float(geometry.fuselage.length_m),
            "location": [0.0, 0.0, 0.0],
            "stations": [
                {
                    "x_m": float(station.x_m),
                    "width_m": float(station.width_m),
                    "height_m": float(station.height_m),
                }
                for station in geometry.fuselage.stations
            ],
        },
    ]
    return {
        "openvsp_root": None,
        "export": {
            "directory": str(Path(export_directory).resolve()),
            "basename": basename,
            "formats": [fmt.lower() for fmt in formats],
        },
        "components": components,
    }


def _sha256(path: Path) -> Optional[str]:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _safe_path(value: Any) -> Any:
    if value is None:
        return None
    try:
        resolved = Path(str(value)).resolve()
        return resolved.relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return "<external>/" + Path(str(value)).name


def _sanitize_worker_result(result: Mapping[str, Any]) -> Dict[str, Any]:
    clean = json.loads(json.dumps(result))
    exports = clean.get("exports") or {}
    for section in ("assembly", "components"):
        entries = exports.get(section) or {}
        for entry in entries.values():
            if isinstance(entry, dict) and "path" in entry:
                entry["path"] = _safe_path(entry["path"])
    return clean


def _sanitize_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    clean = json.loads(json.dumps(request))
    clean["openvsp_root"] = "<openvsp_root>"
    clean["export"]["directory"] = "<export_directory>"
    return clean


def run_worker(
    worker_python: Path,
    worker_script: Path,
    request_path: Path,
    result_path: Path,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    command = [
        str(worker_python),
        "-s",
        "-B",
        str(worker_script),
        "--request",
        str(request_path),
        "--result",
        str(result_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd or REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "command": command,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": "worker timed out after %s s" % timeout_s,
            "command": command,
        }


def measure_stl(path: Path) -> Dict[str, Any]:
    import trimesh

    scene = trimesh.load(str(path), force="scene")
    geometry_items = list(scene.geometry.values())
    if not geometry_items:
        raise RuntimeError("STL contains no geometry: %s" % path)
    bounds = scene.bounds
    extents = scene.extents
    return {
        "path": _safe_path(path),
        "bounds_m": [[float(value) for value in row] for row in bounds],
        "extents_m": [float(value) for value in extents],
        "mesh_count": len(geometry_items),
        "vertices": int(sum(len(mesh.vertices) for mesh in geometry_items)),
        "faces": int(sum(len(mesh.faces) for mesh in geometry_items)),
    }


def measure_component_stls(
    component_exports: Mapping[str, Mapping[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    measured: Dict[str, Dict[str, Any]] = {}
    for name, entry in component_exports.items():
        path = entry.get("path")
        if path:
            measured[name] = measure_stl(Path(path))
    return measured


def _relative_delta(model_value: float, openvsp_value: float) -> Optional[float]:
    try:
        if abs(model_value) <= 1.0e-15:
            return None
        return (openvsp_value - model_value) / model_value
    except (TypeError, ValueError):
        return None


def _comparison(
    check_id: str,
    subject: str,
    model_value: Optional[float],
    openvsp_value: Optional[float],
    tolerance: float,
    warn_status: bool = False,
    detail: str = "",
) -> Dict[str, Any]:
    delta = None
    status = "skip"
    if model_value is not None and openvsp_value is not None:
        delta = _relative_delta(float(model_value), float(openvsp_value))
        if delta is not None:
            if abs(delta) <= tolerance:
                status = "pass"
            elif warn_status:
                status = "warn"
            else:
                status = "fail"
    return {
        "check_id": check_id,
        "subject": subject,
        "model_value": model_value,
        "openvsp_value": openvsp_value,
        "relative_delta": delta,
        "tolerance": tolerance,
        "status": status,
        "detail": detail,
    }


def compare_openvsp(
    geometry: ConcordeGeometry,
    worker_result: Mapping[str, Any],
    stl_metrics: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    metrics = worker_result.get("metrics") or {}
    rows: List[Dict[str, Any]] = []

    wing_metrics = metrics.get("main_wing") or {}
    tail_metrics = metrics.get("vertical_tail") or {}
    fuselage_metrics = metrics.get("fuselage") or {}

    rows.append(
        _comparison(
            "OV01_wing_area",
            "main_wing planform area (m2)",
            float(geometry.wing.area_m2),
            wing_metrics.get("total_area_m2"),
            0.005,
            detail="OpenVSP TotalArea versus model reference area",
        )
    )
    rows.append(
        _comparison(
            "OV02_wing_span",
            "main_wing span (m)",
            float(geometry.wing.span_m),
            wing_metrics.get("total_span_m"),
            0.005,
            detail="OpenVSP TotalSpan versus model projected span",
        )
    )
    rows.append(
        _comparison(
            "OV03_tail_area",
            "vertical_tail planform area (m2)",
            float(geometry.vertical_tail.area_m2),
            tail_metrics.get("total_area_m2"),
            0.005,
        )
    )
    rows.append(
        _comparison(
            "OV04_tail_span",
            "vertical_tail span (m)",
            float(geometry.vertical_tail.span_m),
            tail_metrics.get("total_span_m"),
            0.005,
        )
    )
    rows.append(
        _comparison(
            "OV05_fuselage_length",
            "fuselage length (m)",
            float(geometry.fuselage.length_m),
            fuselage_metrics.get("length_m"),
            1.0e-9,
        )
    )

    wing_mesh = stl_metrics.get("main_wing") or {}
    wing_extents = wing_mesh.get("extents_m") or []
    if len(wing_extents) == 3:
        rows.append(
            _comparison(
                "OV06_wing_mesh_span",
                "main_wing STL lateral extent (m)",
                float(geometry.wing.span_m),
                max(float(wing_extents[1]), float(wing_extents[2])),
                0.005,
                detail="Largest lateral STL extent for the symmetric wing",
            )
        )

    tail_mesh = stl_metrics.get("vertical_tail") or {}
    tail_extents = tail_mesh.get("extents_m") or []
    if len(tail_extents) == 3:
        rows.append(
            _comparison(
                "OV11_tail_mesh_span",
                "vertical_tail STL lateral extent (m)",
                float(geometry.vertical_tail.span_m),
                max(float(tail_extents[1]), float(tail_extents[2])),
                0.005,
                detail="Largest lateral STL extent for the rotated vertical tail",
            )
        )

    fuselage_mesh = stl_metrics.get("fuselage") or {}
    fuselage_extents = fuselage_mesh.get("extents_m") or []
    if len(fuselage_extents) == 3:
        rows.append(
            _comparison(
                "OV07_fuselage_mesh_length",
                "fuselage STL longitude extent (m)",
                float(geometry.fuselage.length_m),
                fuselage_extents[0],
                0.01,
            )
        )
        rows.append(
            _comparison(
                "OV08_fuselage_width",
                "fuselage STL width (m)",
                float(geometry.fuselage.width_m),
                fuselage_extents[1],
                0.02,
                warn_status=True,
                detail="Known OpenVSP spline overshoot; a warning, not an accepted value",
            )
        )
        rows.append(
            _comparison(
                "OV09_fuselage_height",
                "fuselage STL height (m)",
                float(geometry.fuselage.max_height_m),
                fuselage_extents[2],
                0.02,
                warn_status=True,
                detail="Known OpenVSP spline overshoot; height stays within 2% at baseline",
            )
        )

    assembly_mesh = stl_metrics.get("assembly") or {}
    assembly_extents = assembly_mesh.get("extents_m") or []
    if len(assembly_extents) == 3:
        rows.append(
            _comparison(
                "OV10_assembly_length",
                "assembly STL longitude extent (m)",
                float(geometry.fuselage.length_m),
                assembly_extents[0],
                0.01,
                detail="Wing trailing edge lies forward of the fuselage tail",
            )
        )
    return rows


def _status_from_comparisons(comparisons: Sequence[Mapping[str, Any]]) -> str:
    statuses = {row.get("status") for row in comparisons}
    if "fail" in statuses:
        return "openvsp_check_failed"
    if "warn" in statuses:
        return "openvsp_check_completed_with_warnings"
    return "openvsp_check_completed"


def _summary_base(
    identifier: str,
    design_space: DesignSpace,
    status: str,
    wall_seconds: float,
) -> Dict[str, Any]:
    return {
        "run_id": identifier,
        "stage": "P1",
        "task_id": design_space.task_id,
        "method": "openvsp_geometry_check",
        "seed": None,
        "git_sha": _git_sha(REPO_ROOT),
        "solver_versions": _software_versions(),
        "design_dim": len(design_space.variables),
        "status": status,
        "total_true_evaluations": 0,
        "low_fidelity_calls": 0,
        "su2_calls": 0,
        "invalid_count": 0,
        "failed_count": 0,
        "first_feasible_evaluation": None,
        "best_feasible_fuel_kg": None,
        "best_design_id": None,
        "wall_seconds": wall_seconds,
        "cpu_seconds_if_available": None,
        "artifacts": {},
    }


def _run_readme(summary: Mapping[str, Any]) -> str:
    openvsp = summary.get("openvsp") or {}
    comparisons = openvsp.get("comparisons") or []
    failures = [row for row in comparisons if row.get("status") == "fail"]
    warnings = [row for row in comparisons if row.get("status") == "warn"]
    lines = [
        "# P1 OpenVSP geometry check: %s" % summary["run_id"],
        "",
        "This run exports the provisional 15-variable Concorde-like geometry",
        "through OpenVSP 3 and compares the exported STL/product metrics with the",
        "dependency-free geometry model. It performs no aerodynamic or Mission",
        "evaluation and reports no objective value.",
        "",
        "- stage: %s" % summary["stage"],
        "- status: %s" % summary["status"],
        "- git_sha: %s" % summary["git_sha"],
        "- design_dim: %s" % summary["design_dim"],
        "- OpenVSP: %s (external Python %s)" % (openvsp.get("version"), openvsp.get("python_version")),
        "- components: %s" % ", ".join(openvsp.get("components") or []),
        "- comparisons: %s checks (%s pass, %s warn, %s fail)"
        % (
            len(comparisons),
            sum(1 for row in comparisons if row.get("status") == "pass"),
            len(warnings),
            len(failures),
        ),
        "- warning: %s"
        % (
            "; ".join(
                "%s (%+.2f%%)" % (row["check_id"], 100.0 * row["relative_delta"])
                for row in warnings
            )
            or "none"
        ),
        "- failure: %s" % ("; ".join(row["check_id"] for row in failures) or "none"),
        "- true evaluations: %s" % summary["total_true_evaluations"],
        "",
        "The exported STL/STEP/VSP3 files are under the git-ignored outputs",
        "directory; this run records their relative paths, sizes and SHA-256.",
        "",
        "Known limitation: OpenVSP fuselage surface uses spline interpolation",
        "between the eight stations and overshoots the declared maximum width near",
        "the tail; the comparison is recorded as a warning and must be resolved",
        "before OpenVSP-derived fuselage drag or volume is treated as validated.",
    ]
    return "\n".join(lines) + "\n"


def _environment(
    openvsp_python: Path,
    openvsp_root: Path,
    worker_version: Optional[str],
) -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "python_executable": _display_path(sys.executable),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "geometry_model_version": GEOMETRY_MODEL_VERSION,
        "packages": _software_versions(),
        "openvsp": {
            "version": openvsp_version_from_root(openvsp_root),
            "root_name": openvsp_root.name,
            "worker_python": worker_version,
            "worker_python_executable": "<external>/" + openvsp_python.name,
        },
    }


def run_openvsp_check(
    output_root: Optional[Path] = None,
    export_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    design_space: Optional[DesignSpace] = None,
    openvsp_python: Optional[str] = None,
    openvsp_root: Optional[str] = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    allow_existing: bool = False,
    delete_exports: bool = False,
) -> Dict[str, Any]:
    space = design_space if design_space is not None else load_design_space()
    geometry = build_geometry(space.names, space.baseline_vector())
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    exports_root = Path(export_root) if export_root is not None else DEFAULT_EXPORT_ROOT
    identifier = run_id or "openvsp-check-%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / identifier
    export_dir = exports_root / identifier / "openvsp"
    if run_dir.exists() and not allow_existing:
        raise FileExistsError("run directory already exists: %s" % run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    try:
        python_path, root_path = resolve_openvsp_paths(openvsp_python, openvsp_root)
    except OpenVSPSetupError as exc:
        summary = _summary_base(identifier, space, "openvsp_check_unavailable", time.perf_counter() - started)
        summary["error"] = str(exc)
        summary["openvsp"] = {"available": False, "error": str(exc)}
        _write_json(run_dir / "summary.json", summary, pretty=True)
        (run_dir / "README.md").write_text(
            "# P1 OpenVSP check unavailable\n\n" + str(exc) + "\n", encoding="utf-8"
        )
        return summary

    request = build_openvsp_request(geometry, export_dir)
    request["openvsp_root"] = str(root_path)
    request_path = export_dir / "request.json"
    _write_json(request_path, request, pretty=True)
    _write_json(run_dir / "openvsp_request.json", _sanitize_request(request), pretty=True)

    worker_result_path = export_dir / "worker_result.json"
    worker = run_worker(
        python_path,
        DEFAULT_WORKER,
        request_path,
        worker_result_path,
        timeout_s=timeout_s,
    )
    raw_result: Dict[str, Any] = {}
    if worker_result_path.is_file():
        try:
            raw_result = json.loads(worker_result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raw_result = {"status": "failed", "error": "invalid worker result JSON: %s" % exc}

    worker_failed = worker.get("returncode") != 0 or raw_result.get("status") != "ok"
    if worker_failed:
        summary = _summary_base(identifier, space, "openvsp_check_worker_failed", time.perf_counter() - started)
        summary["error"] = raw_result.get("error") or "worker did not report ok"
        summary["openvsp"] = {
            "available": True,
            "version": openvsp_version_from_root(root_path),
            "worker_returncode": worker.get("returncode"),
            "stderr_tail": worker.get("stderr"),
        }
        _write_json(run_dir / "worker_result.json", _sanitize_worker_result(raw_result), pretty=True)
        _write_json(run_dir / "summary.json", summary, pretty=True)
        (run_dir / "README.md").write_text(
            "# P1 OpenVSP worker failed\n\n" + str(summary["error"]) + "\n", encoding="utf-8"
        )
        return summary

    exports = raw_result.get("exports") or {}
    component_exports = exports.get("components") or {}
    try:
        stl_metrics = measure_component_stls(component_exports)
        assembly_path = (exports.get("assembly") or {}).get("stl", {}).get("path")
        if assembly_path:
            stl_metrics["assembly"] = measure_stl(Path(assembly_path))
        measurement_warnings: List[str] = []
    except Exception as exc:  # noqa: BLE001 - record the measurement failure
        stl_metrics = {}
        measurement_warnings = ["STL measurement failed: %s: %s" % (type(exc).__name__, exc)]

    comparisons = compare_openvsp(geometry, raw_result, stl_metrics)
    status = _status_from_comparisons(comparisons)
    if measurement_warnings and status == "openvsp_check_completed":
        status = "openvsp_check_completed_with_warnings"

    summary = _summary_base(identifier, space, status, time.perf_counter() - started)
    summary["solver_versions"].update(
        {
            "OpenVSP": openvsp_version_from_root(root_path),
            "OpenVSP_python": raw_result.get("python_version"),
            "trimesh": _package_version("trimesh"),
        }
    )
    failures = [row for row in comparisons if row["status"] == "fail"]
    warnings = [row for row in comparisons if row["status"] == "warn"]
    summary["failed_count"] = len(failures)
    summary["openvsp"] = {
        "available": True,
        "version": openvsp_version_from_root(root_path),
        "python_version": raw_result.get("python_version"),
        "worker_script": _safe_path(DEFAULT_WORKER),
        "components": [component["name"] for component in request["components"]],
        "metrics": raw_result.get("metrics"),
        "stl_metrics": stl_metrics,
        "comparisons": comparisons,
        "failures": [row["check_id"] for row in failures],
        "warnings": [row["check_id"] for row in warnings],
        "measurement_warnings": measurement_warnings,
        "limitations": [
            "OpenVSP fuselage spline overshoot is recorded as a warning.",
            "No VSPAERO or CFD analysis is run; aerodynamic applicability is not established.",
            "Surface twist is not applied to the OpenVSP wing sections.",
        ],
        "note": "Geometry export and consistency check only; no objective value is reported.",
    }
    summary["artifacts"] = {
        "summary": "summary.json",
        "run_config": "run_config.json",
        "environment": "environment.json",
        "openvsp_request": "openvsp_request.json",
        "worker_result": "worker_result.json",
        "openvsp_metrics": "openvsp_metrics.json",
        "openvsp_comparisons_csv": "openvsp_comparisons.csv",
    }

    export_entries: List[Dict[str, Any]] = []
    for section, label in (("assembly", "assembly"), ("components", "component")):
        for key, entry in (exports.get(section) or {}).items():
            path = entry.get("path") if isinstance(entry, dict) else None
            if not path:
                continue
            export_entries.append(
                {
                    "kind": label,
                    "name": key,
                    "path": _safe_path(path),
                    "bytes": entry.get("bytes"),
                    "sha256": _sha256(Path(path)),
                }
            )
    summary["external_artifacts"] = {
        "root": _safe_path(export_dir),
        "files": export_entries,
        "note": "Raw OpenVSP exports are git-ignored; paths are relative to the repository root.",
    }
    _write_json(run_dir / "worker_result.json", _sanitize_worker_result(raw_result), pretty=True)
    _write_json(
        run_dir / "openvsp_metrics.json",
        {"worker_metrics": raw_result.get("metrics"), "stl_metrics": stl_metrics},
        pretty=True,
    )
    _write_csv(run_dir / "openvsp_comparisons.csv", comparisons)
    _write_json(run_dir / "summary.json", summary, pretty=True)
    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": identifier,
            "stage": "P1",
            "method": "openvsp_geometry_check",
            "design_space_config": _display_path(space.config_path),
            "openvsp_version": openvsp_version_from_root(root_path),
            "openvsp_python": "<external>/" + python_path.name,
            "openvsp_root": root_path.name,
            "worker_script": _safe_path(DEFAULT_WORKER),
            "export_root": _safe_path(exports_root),
            "formats": request["export"]["formats"],
            "timeout_s": timeout_s,
            "command": "python -m research.concorde_metaopt.cli openvsp-check --run-id %s "
            "--openvsp-python <python3.9> --openvsp-root <OpenVSP root>" % identifier,
        },
        pretty=True,
    )
    _write_json(
        run_dir / "environment.json",
        _environment(python_path, root_path, raw_result.get("python_version")),
        pretty=True,
    )
    (run_dir / "README.md").write_text(_run_readme(summary), encoding="utf-8")
    return summary


def _package_version(name: str) -> Optional[str]:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--export-root", default=None)
    parser.add_argument("--openvsp-python", default=None)
    parser.add_argument("--openvsp-root", default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--allow-existing", action="store_true")
    args = parser.parse_args(argv)
    summary = run_openvsp_check(
        output_root=Path(args.output_root) if args.output_root else None,
        export_root=Path(args.export_root) if args.export_root else None,
        run_id=args.run_id,
        openvsp_python=args.openvsp_python,
        openvsp_root=args.openvsp_root,
        timeout_s=args.timeout,
        allow_existing=args.allow_existing,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["status"].startswith("openvsp_check_completed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
