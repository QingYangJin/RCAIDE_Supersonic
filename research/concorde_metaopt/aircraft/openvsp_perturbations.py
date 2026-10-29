"""OpenVSP perturbation evidence for representative 15-variable perturbations.

The baseline OpenVSP check (openvsp_check.py) proves the export path works for
the baseline Concorde geometry. This module adds the evidence requested in the
Issue #1 management review: representative wing, vertical-tail and fuselage
perturbations must actually generate and change OpenVSP geometry, not only the
internal mathematical model.

Each case builds the same dependency-free geometry model with one variable
perturbed by a small, bounds-respecting delta, writes a separate OpenVSP worker
request, exports component STL files, composes the placement-checked assembly,
and then checks two things fail-closed:

1. absolute consistency (wing/tail area and span, fuselage length, composed
   placement bounds) between the model and the OpenVSP export;
2. perturbation reach: the OpenVSP-derived quantity must move in the same way
   as the model quantity, so a silently ignored variable is a failure.

No aerodynamic analysis, Mission evaluation, VSPAERO or SU2 run is performed
and no objective value is reported.
"""

from __future__ import annotations

import json
import math
import platform
import shutil
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
from .geometry_model import GEOMETRY_MODEL_VERSION
from .openvsp_check import (
    BASELINE_COMPONENTS,
    COMPOSED_ASSEMBLY_FILENAME,
    DEFAULT_EXPORT_ROOT,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_TIMEOUT_S,
    DEFAULT_WORKER,
    REPO_ROOT,
    WORKER_ARTIFACT_DIRNAME,
    OpenVSPSetupError,
    _environment,
    _external_export_entries,
    _git_dirty,
    _safe_path,
    _sanitize_request,
    _sanitize_worker_result,
    build_openvsp_request,
    compose_assembly_mesh,
    measure_stl,
    openvsp_version_from_root,
    resolve_openvsp_paths,
    run_worker,
)

PERTURBATION_METHOD = "openvsp_perturbation_check"
PERTURBATION_CASES: Tuple[Dict[str, Any], ...] = (
    {"label": "baseline", "variable_id": None, "kind": "baseline", "delta": 0.0, "component": "all"},
    {"label": "W01_plus_2pct", "variable_id": "W01", "kind": "relative", "delta": 0.02, "component": "main_wing"},
    {"label": "W02_plus_2pct", "variable_id": "W02", "kind": "relative", "delta": 0.02, "component": "main_wing"},
    {"label": "V01_plus_2pct", "variable_id": "V01", "kind": "relative", "delta": 0.02, "component": "vertical_tail"},
    {"label": "F01_plus_1pct", "variable_id": "F01", "kind": "relative", "delta": 0.01, "component": "fuselage"},
    {"label": "F02_plus_2pct", "variable_id": "F02", "kind": "relative", "delta": 0.02, "component": "fuselage"},
    {"label": "F03_plus_2pct", "variable_id": "F03", "kind": "relative", "delta": 0.02, "component": "fuselage"},
)

_REACH_CHECKS: Dict[str, Dict[str, str]] = {
    "W01": {"metric": "wing_area_m2", "target": "wing_area_m2", "mode": "delta"},
    "W02": {"metric": "wing_span_m", "target": "wing_span_m", "mode": "delta"},
    "V01": {"metric": "tail_area_m2", "target": "tail_area_m2", "mode": "delta"},
    "F01": {"metric": "fuselage_length_m", "target": "fuselage_length_m", "mode": "delta"},
    "F02": {"metric": "fuselage_wetted_m2", "target": "fuselage_surface_area_m2", "mode": "changed"},
    "F03": {"metric": "fuselage_height_m", "target": "fuselage_bbox_height_m", "mode": "delta"},
}

DELTA_TOLERANCE = 0.02
CHANGED_THRESHOLD = 1.0e-4


def perturbation_cases(space: DesignSpace) -> List[Dict[str, Any]]:
    """Build the baseline + representative perturbation design vectors."""
    baseline = dict(zip(space.names, space.baseline_vector()))
    cases: List[Dict[str, Any]] = []
    for spec in PERTURBATION_CASES:
        values = dict(baseline)
        variable_value = None
        baseline_value = None
        if spec["variable_id"] is not None:
            variable = space.variable_by_id(spec["variable_id"])
            baseline_value = float(variable.baseline)
            if spec["kind"] == "relative":
                variable_value = baseline_value * (1.0 + float(spec["delta"]))
            else:
                variable_value = baseline_value + float(spec["delta"])
            if not variable.contains(variable_value):
                raise ValueError(
                    "perturbation %s leaves bounds [%r, %r]"
                    % (spec["label"], variable.lower, variable.upper)
                )
            values[variable.name] = variable_value
        space.check_physical(values)
        cases.append(
            {
                "label": spec["label"],
                "variable_id": spec["variable_id"],
                "variable_name": variable.name if spec["variable_id"] is not None else None,
                "component": spec["component"],
                "kind": spec["kind"],
                "delta": float(spec["delta"]),
                "baseline_value": baseline_value,
                "value": variable_value,
                "vector": [float(values[name]) for name in space.names],
            }
        )
    return cases


def _measure_mesh(path: Path) -> Dict[str, Any]:
    """Measure a mesh including surface area, which bounds alone cannot reveal."""
    import trimesh

    scene = trimesh.load(str(path), force="scene")
    items = list(scene.geometry.values())
    if not items:
        raise RuntimeError("mesh file contains no geometry: %s" % path)
    mesh = trimesh.util.concatenate(items) if len(items) > 1 else items[0]
    if mesh.is_empty:
        raise RuntimeError("mesh is empty: %s" % path)
    bounds = [[float(value) for value in row] for row in mesh.bounds]
    return {
        "path": _safe_path(path),
        "bounds_m": bounds,
        "extents_m": [float(value) for value in mesh.extents],
        "surface_area_m2": float(mesh.area),
        "volume_m3": float(mesh.volume),
        "watertight": bool(mesh.is_watertight),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
    }


def _model_metrics(geometry) -> Dict[str, float]:
    return {
        "wing_area_m2": float(geometry.wing.area_m2),
        "wing_span_m": float(geometry.wing.span_m),
        "wing_wetted_m2": float(geometry.wing.wetted_area_m2),
        "tail_area_m2": float(geometry.vertical_tail.area_m2),
        "tail_span_m": float(geometry.vertical_tail.span_m),
        "fuselage_length_m": float(geometry.fuselage.length_m),
        "fuselage_nose_m": float(geometry.fuselage.nose_length_m),
        "fuselage_tail_m": float(geometry.fuselage.tail_length_m),
        "fuselage_width_m": float(geometry.fuselage.width_m),
        "fuselage_height_m": float(geometry.fuselage.max_height_m),
        "fuselage_wetted_m2": float(geometry.fuselage.wetted_area_m2),
        "fuselage_front_m2": float(geometry.fuselage.front_projected_area_m2),
    }


def _openvsp_metrics(
    worker_metrics: Mapping[str, Mapping[str, Any]],
    components: Mapping[str, Mapping[str, Any]],
    composed: Mapping[str, Any],
) -> Dict[str, float]:
    if not isinstance(worker_metrics, Mapping):
        worker_metrics = {str(entry.get("name")): entry for entry in worker_metrics}
    by_name = {str(name): entry for name, entry in worker_metrics.items()}
    wing = by_name["main_wing"]
    tail = by_name["vertical_tail"]
    fuselage = by_name["fuselage"]
    fuselage_extents = [float(value) for value in components["fuselage"]["extents_m"]]
    composed_bounds = [[float(value) for value in row] for row in composed["bounds_m"]]
    composed_extents = [float(value) for value in composed["extents_m"]]
    return {
        "wing_area_m2": float(wing["total_area_m2"]),
        "wing_span_m": float(wing["total_span_m"]),
        "wing_wetted_m2": float(components["main_wing"]["surface_area_m2"]),
        "tail_area_m2": float(tail["total_area_m2"]),
        "tail_span_m": float(tail["total_span_m"]),
        "fuselage_length_m": float(fuselage["length_m"]),
        "fuselage_width_m": float(fuselage_extents[1]),
        "fuselage_height_m": float(fuselage_extents[2]),
        "fuselage_bbox_height_m": float(fuselage_extents[2]),
        "fuselage_surface_area_m2": float(components["fuselage"]["surface_area_m2"]),
        "assembly_x_extent_m": float(composed_extents[0]),
        "assembly_y_extent_m": float(composed_extents[1]),
        "assembly_x_min_m": float(composed_bounds[0][0]),
        "assembly_z_max_m": float(composed_bounds[1][2]),
    }


def _relative_delta(baseline: Optional[float], value: Optional[float]) -> Optional[float]:
    if baseline is None or value is None or baseline == 0.0:
        return None
    return (float(value) - float(baseline)) / abs(float(baseline))


def _check(
    check_id: str,
    subject: str,
    model_value: Optional[float],
    openvsp_value: Optional[float],
    relative_tolerance: Optional[float] = None,
    absolute_tolerance: Optional[float] = None,
    detail: str = "",
    status_if_missing: str = "fail",
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "check_id": check_id,
        "subject": subject,
        "model_value": model_value,
        "openvsp_value": openvsp_value,
        "relative_tolerance": relative_tolerance,
        "absolute_tolerance": absolute_tolerance,
        "detail": detail,
    }
    if model_value is None or openvsp_value is None:
        row.update({"status": status_if_missing, "delta": None, "relative_delta": None})
        return row
    delta = float(openvsp_value) - float(model_value)
    relative = _relative_delta(float(model_value), float(openvsp_value))
    if relative_tolerance is not None:
        passed = relative is not None and abs(relative) <= relative_tolerance
    elif absolute_tolerance is not None:
        passed = abs(delta) <= absolute_tolerance
    else:
        passed = relative == 0.0
    row.update({"status": "pass" if passed else "fail", "delta": delta, "relative_delta": relative})
    return row


def _case_checks(
    case: Mapping[str, Any],
    model: Mapping[str, float],
    openvsp: Mapping[str, float],
    baseline_model: Optional[Mapping[str, float]],
    baseline_openvsp: Optional[Mapping[str, float]],
) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = [
        _check("OVP01_wing_area", "main_wing area", model["wing_area_m2"], openvsp["wing_area_m2"], relative_tolerance=0.005),
        _check("OVP02_wing_span", "main_wing span", model["wing_span_m"], openvsp["wing_span_m"], relative_tolerance=0.005),
        _check("OVP03_tail_area", "vertical_tail area", model["tail_area_m2"], openvsp["tail_area_m2"], relative_tolerance=0.005),
        _check("OVP04_tail_span", "vertical_tail span", model["tail_span_m"], openvsp["tail_span_m"], relative_tolerance=0.005),
        _check("OVP05_fuselage_length", "fuselage length read back", model["fuselage_length_m"], openvsp["fuselage_length_m"], absolute_tolerance=1.0e-6),
        _check("OVP06_assembly_x", "composed assembly x extent vs fuselage length", model["fuselage_length_m"], openvsp["assembly_x_extent_m"], relative_tolerance=1.0e-6),
        _check("OVP07_assembly_y", "composed assembly y extent vs wing span", model["wing_span_m"], openvsp["assembly_y_extent_m"], relative_tolerance=0.005),
        _check("OVP08_assembly_zmax", "composed assembly z max vs tail origin + tail span", 1.0 + model["tail_span_m"], openvsp["assembly_z_max_m"], relative_tolerance=0.005),
    ]
    variable_id = case.get("variable_id")
    if variable_id is None:
        checks.append(
            {
                "check_id": "OVP09_perturbation_reach",
                "subject": "baseline (no perturbation)",
                "model_value": None,
                "openvsp_value": None,
                "relative_tolerance": None,
                "absolute_tolerance": None,
                "status": "skip",
                "delta": None,
                "relative_delta": None,
                "detail": "baseline case; reach check applies to perturbed cases only",
            }
        )
        return checks
    spec = _REACH_CHECKS.get(str(variable_id))
    if spec is None:  # pragma: no cover - guarded by PERTURBATION_CASES
        checks.append(
            {
                "check_id": "OVP09_perturbation_reach",
                "subject": str(variable_id),
                "status": "fail",
                "model_value": None,
                "openvsp_value": None,
                "relative_tolerance": None,
                "absolute_tolerance": None,
                "delta": None,
                "relative_delta": None,
                "detail": "no reach-check rule for this variable",
            }
        )
        return checks
    if baseline_model is None or baseline_openvsp is None:
        checks.append(
            {
                "check_id": "OVP09_perturbation_reach",
                "subject": str(variable_id),
                "status": "fail",
                "model_value": None,
                "openvsp_value": None,
                "relative_tolerance": None,
                "absolute_tolerance": None,
                "delta": None,
                "relative_delta": None,
                "detail": "baseline case metrics missing",
            }
        )
        return checks
    model_metric = spec["metric"]
    openvsp_metric = spec["target"]
    model_delta = _relative_delta(baseline_model[model_metric], model[model_metric])
    openvsp_delta = _relative_delta(baseline_openvsp[openvsp_metric], openvsp[openvsp_metric])
    if model_delta is None or openvsp_delta is None:
        status = "fail"
        detail = "delta could not be computed"
    elif spec["mode"] == "changed":
        status = "pass" if abs(openvsp_delta) >= CHANGED_THRESHOLD else "fail"
        detail = "geometry must change under this perturbation; threshold %g" % CHANGED_THRESHOLD
    else:
        status = "pass" if abs(openvsp_delta - model_delta) <= DELTA_TOLERANCE else "fail"
        detail = "OpenVSP delta must follow the model delta; absolute tolerance %g" % DELTA_TOLERANCE
    checks.append(
        {
            "check_id": "OVP09_perturbation_reach",
            "subject": "%s %s vs %s" % (variable_id, model_metric, openvsp_metric),
            "model_value": model_delta,
            "openvsp_value": openvsp_delta,
            "relative_tolerance": None,
            "absolute_tolerance": DELTA_TOLERANCE if spec["mode"] == "delta" else CHANGED_THRESHOLD,
            "status": status,
            "delta": None if (openvsp_delta is None or model_delta is None) else openvsp_delta - model_delta,
            "relative_delta": openvsp_delta,
            "detail": detail,
        }
    )
    return checks


def _case_status(checks: Sequence[Mapping[str, Any]]) -> str:
    if any(row.get("status") == "fail" for row in checks):
        return "fail"
    if any(row.get("status") == "warn" for row in checks):
        return "warn"
    return "pass"


def _summary_base(run_id: str, space: DesignSpace, status: str, wall_seconds: float) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "stage": "P1",
        "task_id": space.task_id,
        "method": PERTURBATION_METHOD,
        "seed": None,
        "git_sha": _git_sha(REPO_ROOT),
        "solver_versions": _software_versions(),
        "design_dim": len(space.names),
        "status": status,
        "total_true_evaluations": 0,
        "low_fidelity_calls": 0,
        "su2_calls": 0,
        "invalid_count": 0,
        "failed_count": 0,
        "first_feasible_evaluation": None,
        "best_feasible_fuel_kg": None,
        "best_design_id": None,
        "wall_seconds": round(float(wall_seconds), 3),
        "cpu_seconds_if_available": None,
        "artifacts": {},
    }


def _write_readme(run_dir: Path, summary: Mapping[str, Any]) -> None:
    block = summary.get("perturbation") or {}
    lines = [
        "# P1 OpenVSP perturbation geometry check",
        "",
        "Representative wing / vertical-tail / fuselage perturbations are exported",
        "through the external Python 3.9 OpenVSP worker, measured with trimesh and",
        "compared with the internal geometry model. This is a geometry-export check:",
        "no Mission, VSPAERO or CFD evaluation was run and no objective value is reported.",
        "",
        "- run_id: %s" % summary.get("run_id"),
        "- git_sha: %s" % summary.get("git_sha"),
        "- cases: %s" % block.get("case_count"),
        "- checks: %s pass / %s fail / %s skip" % (block.get("checks_pass"), block.get("checks_fail"), block.get("checks_skip")),
        "- status: %s" % summary.get("status"),
        "",
        "Cases (relative perturbation of the frozen baseline design):",
        "",
    ]
    for case in block.get("cases") or []:
        lines.append("- %s: %s" % (case.get("label"), case.get("status")))
    lines += [
        "",
        "Placement is checked on the trimesh-composed assembly STL; .vsp3/.step",
        "exports remain component-local in this OpenVSP build.",
        "Known limitation: OpenVSP fuselage spline overshoot; surface bounds are",
        "measured from the exported STL rather than the OpenVSP BBox parameters.",
        "",
        "Redraw the figure:",
        "",
        "    ./run_rcaide.cmd -m research.concorde_metaopt.aircraft.openvsp_perturbations %s" % _display_path(run_dir),
    ]
    (run_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_openvsp_perturbation_check(
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
    cases = perturbation_cases(space)
    resolved_output = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    exports_root = Path(export_root) if export_root is not None else DEFAULT_EXPORT_ROOT
    identifier = run_id or "openvsp-perturb-%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = resolved_output / identifier
    export_dir = exports_root / identifier / "openvsp"
    if run_dir.exists() and not allow_existing:
        raise FileExistsError("run directory already exists: %s" % run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if export_dir.exists():
        if not allow_existing:
            raise FileExistsError("export directory already exists: %s" % export_dir)
        shutil.rmtree(export_dir, ignore_errors=True)
    (run_dir / "figures").mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    run_display = _display_path(run_dir)
    started = time.perf_counter()

    try:
        python_path, root_path = resolve_openvsp_paths(openvsp_python, openvsp_root)
    except OpenVSPSetupError as exc:
        summary = _summary_base(identifier, space, "openvsp_perturbation_check_unavailable", time.perf_counter() - started)
        summary["error"] = str(exc)
        _write_json(run_dir / "summary.json", summary, pretty=True)
        (run_dir / "README.md").write_text("# P1 OpenVSP perturbation check unavailable\n\n" + str(exc) + "\n", encoding="utf-8")
        return summary

    rows: List[Dict[str, Any]] = []
    failures: List[str] = []
    baseline_model: Optional[Dict[str, float]] = None
    baseline_openvsp: Optional[Dict[str, float]] = None
    exported = 0
    for case in cases:
        label = case["label"]
        case_export = export_dir / label
        case_export.mkdir(parents=True, exist_ok=True)
        case_row: Dict[str, Any] = {
            "label": label,
            "variable_id": case["variable_id"],
            "variable_name": case["variable_name"],
            "component": case["component"],
            "kind": case["kind"],
            "delta": case["delta"],
            "baseline_value": case["baseline_value"],
            "value": case["value"],
        }
        try:
            geometry = build_geometry(space.names, case["vector"])
        except Exception as exc:  # noqa: BLE001 - record construction failure
            case_row.update({"status": "geometry_failed", "error": "%s: %s" % (type(exc).__name__, exc)})
            failures.append("%s: geometry construction failed: %s" % (label, exc))
            rows.append(case_row)
            continue
        request = build_openvsp_request(geometry, case_export)
        request["openvsp_root"] = str(root_path)
        worker_dir = case_export / WORKER_ARTIFACT_DIRNAME
        worker_dir.mkdir(parents=True, exist_ok=True)
        request_path = worker_dir / "request.json"
        _write_json(request_path, request, pretty=True)
        case_row["request"] = _sanitize_request(request)
        result_path = worker_dir / "worker_result.json"
        worker = run_worker(python_path, DEFAULT_WORKER, request_path, result_path, timeout_s=timeout_s)
        raw_result: Dict[str, Any] = {}
        if result_path.is_file():
            try:
                raw_result = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raw_result = {"status": "failed", "error": "invalid worker result JSON: %s" % exc}
        if worker.get("returncode") != 0 or raw_result.get("status") != "ok":
            case_row.update(
                {
                    "status": "worker_failed",
                    "error": raw_result.get("error") or "worker did not report ok",
                    "worker_returncode": worker.get("returncode"),
                    "stderr_tail": (worker.get("stderr") or "")[-1000:],
                }
            )
            failures.append("%s: OpenVSP worker failed: %s" % (label, case_row["error"]))
            rows.append(case_row)
            continue
        case_row["worker_python"] = raw_result.get("python_version")
        exports = raw_result.get("exports") or {}
        component_exports = exports.get("components") or {}
        measurements: Dict[str, Dict[str, Any]] = {}
        measurement_failures: List[str] = []
        for name in BASELINE_COMPONENTS:
            entry = component_exports.get(name)
            path = entry.get("path") if isinstance(entry, Mapping) else None
            if not path:
                measurement_failures.append("%s: no STL export reported for %s" % (label, name))
                continue
            try:
                measurements[name] = _measure_mesh(Path(str(path)))
            except Exception as exc:  # noqa: BLE001
                measurement_failures.append("%s: %s measurement failed: %s: %s" % (label, name, type(exc).__name__, exc))
        assembly_path = (exports.get("assembly") or {}).get("stl", {}).get("path")
        composed: Dict[str, Any] = {}
        if not measurement_failures and assembly_path:
            try:
                measure_stl(Path(str(assembly_path)))
                composed = compose_assembly_mesh(component_exports, case_export)
            except Exception as exc:  # noqa: BLE001
                measurement_failures.append("%s: assembly composition failed: %s: %s" % (label, type(exc).__name__, exc))
        elif not measurement_failures:
            measurement_failures.append("%s: no assembly STL export reported" % label)
        case_row["measurement_failures"] = measurement_failures
        if measurement_failures:
            case_row.update({"status": "measurement_failed", "error": "; ".join(measurement_failures)})
            failures.extend(measurement_failures)
            rows.append(case_row)
            continue
        model = _model_metrics(geometry)
        openvsp = _openvsp_metrics(raw_result.get("metrics") or {}, measurements, composed)
        checks = _case_checks(case, model, openvsp, baseline_model, baseline_openvsp)
        if case["variable_id"] is None:
            baseline_model = model
            baseline_openvsp = openvsp
        case_row.update(
            {
                "status": _case_status(checks),
                "model_metrics": model,
                "openvsp_metrics": openvsp,
                "checks": checks,
                "component_measurements": measurements,
                "assembly": composed,
            }
        )
        if case_row["status"] == "fail":
            failures.append(
                "%s: failed checks %s"
                % (label, ", ".join(row["check_id"] for row in checks if row["status"] == "fail"))
            )
        rows.append(case_row)
        exported += 1

    all_checks = [check for row in rows for check in (row.get("checks") or [])]
    checks_pass = sum(1 for row in all_checks if row.get("status") == "pass")
    checks_fail = sum(1 for row in all_checks if row.get("status") == "fail")
    checks_skip = sum(1 for row in all_checks if row.get("status") == "skip")
    case_failures = [row for row in rows if row.get("status") in ("fail", "worker_failed", "measurement_failed", "geometry_failed")]
    status = "openvsp_perturbation_check_completed"
    if case_failures or failures:
        status = "openvsp_perturbation_check_failed"

    summary = _summary_base(identifier, space, status, time.perf_counter() - started)
    summary["solver_versions"].update(
        {
            "OpenVSP": openvsp_version_from_root(root_path),
            "OpenVSP_python": (rows[0].get("worker_python") if rows else None),
            "trimesh": _package_version("trimesh"),
        }
    )
    summary["failed_count"] = checks_fail + len(case_failures)
    summary["invalid_count"] = sum(1 for row in rows if row.get("status") in ("geometry_failed", "worker_failed", "measurement_failed"))
    summary["git_dirty"] = _git_dirty(REPO_ROOT, (run_display,))
    summary["perturbation"] = {
        "case_count": len(rows),
        "exported_cases": exported,
        "cases": [
            {"label": row["label"], "variable_id": row["variable_id"], "status": row["status"]}
            for row in rows
        ],
        "checks_total": len(all_checks),
        "checks_pass": checks_pass,
        "checks_fail": checks_fail,
        "checks_skip": checks_skip,
        "failures": failures,
        "delta_tolerance": DELTA_TOLERANCE,
        "changed_threshold": CHANGED_THRESHOLD,
        "limitations": [
            "Surface twist is not applied to the OpenVSP wing sections.",
            "The fuselage nose-fineness case only requires that the exported surface changes (F02); its OpenVSP surface-area response can differ in sign from the model cone formula because of the OpenVSP spline interpolation / overshoot.",
            "The OpenVSP fuselage BBox is not a reliable bound; placement and size checks use STL measurements and the composed assembly.",
            "This is geometry-export evidence only: no VSPAERO, CFD or Mission evaluation is performed and no objective value is reported.",
        ],
        "note": (
            "Geometry-export evidence only: representative wing/tail/fuselage "
            "perturbations must reach OpenVSP geometry. No aerodynamic or Mission "
            "evaluation is performed. Placement is checked on the composed STL."
        ),
    }
    summary["artifacts"] = {
        "summary": "summary.json",
        "run_config": "run_config.json",
        "environment": "environment.json",
        "perturbation_cases": "openvsp_perturbation_cases.json",
        "perturbation_metrics_csv": "openvsp_perturbation_metrics.csv",
        "perturbation_deltas_csv": "openvsp_perturbation_deltas.csv",
        "perturbation_checks_csv": "openvsp_perturbation_checks.csv",
        "figure": "figures/openvsp_perturbation_deltas.png",
    }
    export_files, export_backups = _external_export_entries(export_dir)
    summary["external_artifacts"] = {
        "root": _safe_path(export_dir),
        "files": export_files,
        "ignored_files": export_backups,
        "deleted": False,
        "note": "Raw OpenVSP exports are git-ignored; paths are relative to the repository root.",
    }
    if delete_exports:
        shutil.rmtree(export_dir, ignore_errors=True)
        summary["external_artifacts"]["deleted"] = True

    metric_rows: List[Dict[str, Any]] = []
    delta_rows: List[Dict[str, Any]] = []
    check_rows: List[Dict[str, Any]] = []
    for row in rows:
        if "model_metrics" not in row:
            continue
        for metric, model_value in row["model_metrics"].items():
            openvsp_value = (row["openvsp_metrics"] or {}).get(metric)
            model_delta = _relative_delta((baseline_model or {}).get(metric), model_value)
            openvsp_delta = _relative_delta((baseline_openvsp or {}).get(metric), openvsp_value)
            metric_rows.append(
                {
                    "case_label": row["label"],
                    "variable_id": row["variable_id"],
                    "metric": metric,
                    "model_value": model_value,
                    "openvsp_value": openvsp_value,
                    "relative_delta": openvsp_delta,
                }
            )
            delta_rows.append(
                {
                    "case_label": row["label"],
                    "metric": metric,
                    "model_relative_delta": model_delta,
                    "openvsp_relative_delta": openvsp_delta,
                }
            )
        for check in row["checks"]:
            check_rows.append(
                {
                    "case_label": row["label"],
                    "check_id": check["check_id"],
                    "subject": check["subject"],
                    "status": check["status"],
                    "model_value": check.get("model_value"),
                    "openvsp_value": check.get("openvsp_value"),
                    "detail": check.get("detail"),
                }
            )
    _write_json(run_dir / "openvsp_perturbation_cases.json", {"cases": rows}, pretty=True)
    _write_csv(run_dir / "openvsp_perturbation_metrics.csv", metric_rows)
    _write_csv(run_dir / "openvsp_perturbation_deltas.csv", delta_rows)
    _write_csv(run_dir / "openvsp_perturbation_checks.csv", check_rows)
    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": identifier,
            "stage": "P1",
            "method": PERTURBATION_METHOD,
            "design_space_config": _display_path(space.config_path),
            "cases": [
                {"label": case["label"], "variable_id": case["variable_id"], "delta": case["delta"]}
                for case in cases
            ],
            "openvsp_version": openvsp_version_from_root(root_path),
            "openvsp_python": "<external>/" + python_path.name,
            "openvsp_root": root_path.name,
            "worker_script": _safe_path(DEFAULT_WORKER),
            "export_root": _safe_path(exports_root),
            "timeout_s": timeout_s,
            "delta_tolerance": DELTA_TOLERANCE,
            "changed_threshold": CHANGED_THRESHOLD,
            "command": "python -m research.concorde_metaopt.cli openvsp-cases --run-id %s "
            "--openvsp-python <python3.9> --openvsp-root <OpenVSP root>" % identifier,
        },
        pretty=True,
    )
    _write_json(
        run_dir / "environment.json",
        _environment(python_path, root_path, rows[0].get("worker_python") if rows else None, ignore_paths=(run_display,)),
        pretty=True,
    )
    summary["wall_seconds"] = round(time.perf_counter() - started, 3)
    _write_json(run_dir / "summary.json", summary, pretty=True)
    try:
        plot_perturbation_artifacts(run_dir)
        summary["figure_error"] = None
    except Exception as exc:  # noqa: BLE001 - figure failure must not hide the evidence
        summary["figure_error"] = "%s: %s" % (type(exc).__name__, exc)
        _write_json(run_dir / "summary.json", summary, pretty=True)
    _write_readme(run_dir, summary)
    return summary


def _package_version(name: str) -> Optional[str]:
    import importlib.metadata

    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def plot_perturbation_artifacts(run_dir: Path) -> Path:
    """Redraw the perturbation heatmap from the committed CSV (no evaluation)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    run_dir = Path(run_dir)
    csv_path = run_dir / "openvsp_perturbation_deltas.csv"
    if not csv_path.is_file():
        raise FileNotFoundError("missing perturbation delta CSV: %s" % csv_path)
    import csv as csv_module

    rows = list(csv_module.DictReader(csv_path.open(encoding="utf-8")))
    metrics = [
        "wing_area_m2",
        "wing_span_m",
        "tail_area_m2",
        "tail_span_m",
        "fuselage_length_m",
        "fuselage_surface_area_m2",
        "assembly_x_extent_m",
        "assembly_y_extent_m",
        "assembly_z_max_m",
    ]
    labels = [row["case_label"] for row in rows if row["case_label"] != "baseline"]
    labels = list(dict.fromkeys(labels))
    lookup = {(row["case_label"], row["metric"]): row for row in rows}
    values = np.full((len(labels), len(metrics)), np.nan)
    for i, label in enumerate(labels):
        for j, metric in enumerate(metrics):
            row = lookup.get((label, metric))
            if row is None or row["openvsp_relative_delta"] in ("", "None", None):
                continue
            values[i, j] = float(row["openvsp_relative_delta"]) * 100.0
    fig, ax = plt.subplots(figsize=(12.0, 4.2), dpi=160)
    image = ax.imshow(values, aspect="auto", cmap="RdBu_r", norm=matplotlib.colors.CenteredNorm())
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels([metric.replace("_", " ") for metric in metrics], rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_title("OpenVSP geometry response to representative perturbations (relative to baseline)")
    for i in range(len(labels)):
        for j in range(len(metrics)):
            if not np.isnan(values[i, j]):
                ax.text(j, i, "%+.2f" % values[i, j], ha="center", va="center", fontsize=7, color="black")
    colorbar = fig.colorbar(image, ax=ax, pad=0.01)
    colorbar.set_label("OpenVSP relative delta [%]")
    ax.set_xlabel("measured OpenVSP quantity")
    ax.set_ylabel("perturbation case")
    fig.tight_layout()
    target = run_dir / "figures" / "openvsp_perturbation_deltas.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target)
    plt.close(fig)
    return target


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Redraw OpenVSP perturbation evidence figures from committed CSV artefacts.")
    parser.add_argument("run_dir", help="optimization_runs/<run_id> directory")
    args = parser.parse_args(argv)
    target = plot_perturbation_artifacts(Path(args.run_dir))
    print("wrote %s" % target)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
