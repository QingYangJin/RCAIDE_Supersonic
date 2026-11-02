"""Rebuild a run report from stored artefacts (no Mission and no CFD calls).

The reporter never re-runs physics.  It reads the committed run directory and
recomputes the headline numbers from the raw per-evaluation log, so a mismatch
between summary.json and evaluations.jsonl becomes visible instead of being
trusted.  Consistency checks cover the true-evaluation count, the best feasible
objective, the first feasible evaluation, cache hits, artefact presence and
absolute paths.  Figures are redrawn only from stored CSV/JSON artefacts.

Usage::

    python -m research.concorde_metaopt.reports.summarize --run-id <run_id>
    python -m research.concorde_metaopt.reports.summarize --run-id <run_id> --compare-run <other_run_id>
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"
REPORT_FILENAME = "report.md"
REPORT_JSON_FILENAME = "report.json"
COMPARISON_FILENAME = "comparison.csv"
COMPARISON_JSON_FILENAME = "comparison.json"
STATUS_VALID = "VALID"
RELATIVE_TOLERANCE = 1.0e-9
STATUS_COMPLETED = "report_completed"
STATUS_WITH_WARNINGS = "report_completed_with_warnings"


class ReportError(RuntimeError):
    """Raised when a run directory cannot be reported at all."""


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not Path(path).exists():
        return rows
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        loaded = json.loads(line)
        if isinstance(loaded, Mapping):
            rows.append(dict(loaded))
    return rows


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _relative_difference(reference: Optional[float], actual: Optional[float]) -> Optional[float]:
    if reference is None or actual is None:
        return None
    scale = max(abs(reference), 1.0e-12)
    return abs(actual - reference) / scale


def _display_path(value: Any) -> str:
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value:
        return str(value)
    try:
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        return candidate.as_posix()
    except (ValueError, OSError):
        return str(value)


def _is_absolute_path(value: str) -> bool:
    return os.path.isabs(value) or bool(Path(value).drive)


def _resolve_artifact(entry: str, run_dir: Path) -> Path:
    candidate = Path(entry)
    if candidate.is_absolute():
        return candidate
    run_relative = run_dir / candidate
    if run_relative.exists():
        return run_relative
    return REPO_ROOT / candidate


def recompute_from_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Recompute headline numbers from the raw per-evaluation rows."""
    status_counts: Dict[str, int] = {}
    physical_calls = 0
    cache_hits = 0
    best_objective: Optional[float] = None
    best_design_id: Optional[str] = None
    first_feasible: Optional[int] = None
    feasible_rows = 0
    valid_rows = 0
    for position, row in enumerate(rows, start=1):
        status = str(row.get("status") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
        calls = _finite_number(row.get("physical_call_count"))
        if calls is not None and calls > 0:
            physical_calls += int(calls)
        if bool(row.get("cache_hit")):
            cache_hits += 1
        if status != STATUS_VALID:
            continue
        valid_rows += 1
        feasible = bool(row.get("feasible"))
        if not feasible:
            continue
        feasible_rows += 1
        iteration = _finite_number(row.get("iteration"))
        if first_feasible is None:
            first_feasible = int(iteration) if iteration is not None else position
        objective = _finite_number(row.get("objective"))
        if objective is None:
            continue
        if best_objective is None or objective < best_objective:
            best_objective = objective
            design = row.get("design_id")
            best_design_id = design if isinstance(design, str) else None
    return {
        "rows": len(rows),
        "true_evaluations": physical_calls,
        "cache_hits": cache_hits,
        "status_counts": status_counts,
        "valid_rows": valid_rows,
        "feasible_rows": feasible_rows,
        "first_feasible_evaluation": first_feasible,
        "best_feasible_objective": best_objective,
        "best_design_id": best_design_id,
    }


def _check(
    check_id: str,
    subject: str,
    summary_value: Any,
    recomputed_value: Any,
    tolerance: Optional[float],
    note: str = "",
) -> Dict[str, Any]:
    if summary_value is None and recomputed_value is None:
        status = "skip"
    elif isinstance(summary_value, (int, float)) and isinstance(recomputed_value, (int, float)):
        delta = _relative_difference(float(summary_value), float(recomputed_value))
        status = "pass" if delta is not None and delta <= (tolerance or 0.0) else "fail"
        return {
            "check_id": check_id,
            "subject": subject,
            "summary_value": summary_value,
            "recomputed_value": recomputed_value,
            "relative_delta": delta,
            "tolerance": tolerance,
            "status": status,
            "note": note,
        }
    else:
        status = "pass" if summary_value == recomputed_value else "fail"
    return {
        "check_id": check_id,
        "subject": subject,
        "summary_value": summary_value,
        "recomputed_value": recomputed_value,
        "relative_delta": None,
        "tolerance": tolerance,
        "status": status,
        "note": note,
    }


def consistency_checks(summary: Mapping[str, Any], recomputed: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    checks.append(_check(
        "R01", "total_true_evaluations", summary.get("total_true_evaluations"),
        recomputed.get("true_evaluations"), 0.0,
        "sum of physical_call_count over stored rows",
    ))
    checks.append(_check(
        "R02", "best_feasible_fuel_kg", summary.get("best_feasible_fuel_kg"),
        recomputed.get("best_feasible_objective"), RELATIVE_TOLERANCE,
        "minimum objective over VALID feasible rows",
    ))
    checks.append(_check(
        "R03", "first_feasible_evaluation", summary.get("first_feasible_evaluation"),
        recomputed.get("first_feasible_evaluation"), None,
        "iteration of the first VALID feasible row",
    ))
    checks.append(_check(
        "R04", "best_design_id", summary.get("best_design_id"),
        recomputed.get("best_design_id"), None,
        "design id of the best objective row",
    ))
    return checks


def artifact_checks(summary: Mapping[str, Any], run_dir: Path) -> Dict[str, Any]:
    artifacts = summary.get("artifacts") or {}
    present: List[str] = []
    missing: List[Dict[str, Any]] = []
    absolute: List[str] = []
    entries: List[Tuple[str, str]] = []
    if isinstance(artifacts, Mapping):
        for key, value in artifacts.items():
            if isinstance(value, (list, tuple)):
                for item in value:
                    entries.append((str(key), str(item)))
            elif value is not None:
                entries.append((str(key), str(value)))
    for key, entry in entries:
        if _is_absolute_path(entry):
            absolute.append(entry)
            continue
        path = _resolve_artifact(entry, run_dir)
        if path.exists():
            present.append(entry)
        else:
            missing.append({"artifact": key, "path": entry})
    return {
        "total": len(entries),
        "present": present,
        "missing": missing,
        "absolute_paths": absolute,
    }


def _figure_targets(run_dir: Path) -> Dict[str, str]:
    """Return the redrawable figure set detected in the run directory."""
    targets: Dict[str, str] = {}
    if (run_dir / "geometry_effect_delta.csv").exists() and (run_dir / "geometry_planforms.json").exists():
        targets["geometry"] = "geometry_effect_heatmap.png + wing_planform_comparison.png"
    if (run_dir / "smoke_cases.csv").exists() and (run_dir / "evaluations.jsonl").exists():
        targets["smoke"] = "repeatability.png + perturbation_sensitivity.png"
    if (run_dir / "opt_trace.jsonl").exists() and (run_dir / "summary.json").exists():
        targets["optimizer"] = "convergence.png + feasibility_rate.png"
    if (run_dir / "openvsp_perturbation_deltas.csv").exists():
        targets["openvsp_perturbation"] = "openvsp_perturbation_deltas.png"
    return targets


def regenerate_figures(run_dir: Path) -> Dict[str, Any]:
    from . import figures

    generated: Dict[str, str] = {}
    errors: List[str] = []
    detectors = (
        (
            lambda: (run_dir / "geometry_effect_delta.csv").exists()
            and (run_dir / "geometry_planforms.json").exists(),
            figures.plot_geometry_artifacts,
        ),
        (
            lambda: (run_dir / "smoke_cases.csv").exists() and (run_dir / "evaluations.jsonl").exists(),
            figures.plot_smoke_artifacts,
        ),
        (
            lambda: (run_dir / "opt_trace.jsonl").exists() and (run_dir / "summary.json").exists(),
            figures.plot_optimizer_trace_artifacts,
        ),
        (
            lambda: (run_dir / "openvsp_perturbation_deltas.csv").exists(),
            getattr(figures, "plot_perturbation_artifacts", None),
        ),
    )
    for detector, plotter in detectors:
        if plotter is None:
            continue
        try:
            if not detector():
                continue
            paths = plotter(run_dir)
            for name, path in (paths or {}).items():
                generated[str(name)] = _display_path(path)
        except Exception as error:  # noqa: BLE001 - report must never crash on figures
            errors.append("%s: %s" % (type(error).__name__, error))
    return {"generated": generated, "errors": errors}


def load_run(run_dir: Path) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise ReportError("run directory %s has no summary.json" % run_dir)
    summary = _read_json(summary_path)
    if not isinstance(summary, Mapping):
        raise ReportError("summary.json in %s is not a JSON object" % run_dir)
    rows = _read_jsonl(run_dir / "evaluations.jsonl")
    trace = _read_jsonl(run_dir / "opt_trace.jsonl")
    best_design_path = run_dir / "best_design.json"
    best_design = _read_json(best_design_path) if best_design_path.exists() else None
    return {
        "run_dir": run_dir,
        "summary": dict(summary),
        "rows": rows,
        "trace": trace,
        "best_design": best_design,
    }


def _comparison_row(loaded: Mapping[str, Any]) -> Dict[str, Any]:
    summary = loaded["summary"]
    run_dir = loaded["run_dir"]
    recomputed = recompute_from_rows(loaded["rows"])
    return {
        "run_id": summary.get("run_id") or Path(run_dir).name,
        "stage": summary.get("stage"),
        "method": summary.get("method"),
        "status": summary.get("status"),
        "git_sha": summary.get("git_sha"),
        "seed": summary.get("seed"),
        "true_evaluations": summary.get("total_true_evaluations"),
        "recomputed_true_evaluations": recomputed["true_evaluations"],
        "valid_rows": recomputed["valid_rows"],
        "feasible_rows": recomputed["feasible_rows"],
        "first_feasible_evaluation": summary.get("first_feasible_evaluation"),
        "best_feasible_fuel_kg": summary.get("best_feasible_fuel_kg"),
        "recomputed_best_feasible_fuel_kg": recomputed["best_feasible_objective"],
        "best_design_id": summary.get("best_design_id"),
        "wall_seconds": summary.get("wall_seconds"),
        "path": _display_path(run_dir),
    }


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> List[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        cells = []
        for value in row:
            if value is None:
                cells.append("null")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _summary_notes(summary: Mapping[str, Any]) -> List[str]:
    notes: List[str] = []
    for key in ("status", "note", "limitations"):
        value = summary.get(key)
        if isinstance(value, str) and value:
            notes.append(value)
        elif isinstance(value, (list, tuple)):
            notes.extend(str(item) for item in value)
    return notes


def build_report(loaded: Mapping[str, Any], figures_block: Mapping[str, Any], comparison: Sequence[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    summary = loaded["summary"]
    run_dir = loaded["run_dir"]
    rows = loaded["rows"]
    recomputed = recompute_from_rows(rows)
    checks = consistency_checks(summary, recomputed)
    artifacts = artifact_checks(summary, run_dir)
    failures = [check for check in checks if check["status"] == "fail"]
    warnings = list(figures_block.get("errors") or [])
    if artifacts["missing"]:
        warnings.append("%d recorded artefact(s) are missing" % len(artifacts["missing"]))
    if artifacts["absolute_paths"]:
        warnings.append("%d recorded artefact path(s) are absolute" % len(artifacts["absolute_paths"]))
    status = STATUS_WITH_WARNINGS if (failures or warnings) else STATUS_COMPLETED
    report = {
        "run_id": summary.get("run_id") or Path(run_dir).name,
        "stage": summary.get("stage"),
        "method": summary.get("method"),
        "task_id": summary.get("task_id"),
        "experiment_status": summary.get("status"),
        "report_status": status,
        "git_sha": summary.get("git_sha"),
        "branch": summary.get("branch"),
        "seed": summary.get("seed"),
        "design_dim": summary.get("design_dim"),
        "recomputed": recomputed,
        "consistency": checks,
        "consistency_failures": [check["check_id"] for check in failures],
        "artifacts": artifacts,
        "figures": figures_block,
        "figure_targets": _figure_targets(run_dir),
        "comparison": [dict(row) for row in comparison],
        "notes": _summary_notes(summary),
        "report_note": "recomputed from stored artefacts; no Mission, CFD or OpenVSP call was executed",
    }
    report["report_path"] = _display_path(run_dir / REPORT_FILENAME)
    report["report_json_path"] = _display_path(run_dir / REPORT_JSON_FILENAME)
    return report


def render_markdown(report: Mapping[str, Any], loaded: Mapping[str, Any]) -> str:
    summary = loaded["summary"]
    recomputed = report["recomputed"]
    lines: List[str] = []
    lines.append("# Run report: %s" % report["run_id"])
    lines.append("")
    lines.append("Rebuilt from the stored run artefacts; no Mission, CFD or OpenVSP call was executed.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.extend(_md_table(
        ("field", "value"),
        (
            ("stage", report["stage"]),
            ("method", report["method"]),
            ("task_id", report["task_id"]),
            ("experiment status", report["experiment_status"]),
            ("report status", report["report_status"]),
            ("git sha", report["git_sha"]),
            ("branch", report["branch"]),
            ("seed", report["seed"]),
            ("design_dim", report["design_dim"]),
        ),
    ))
    lines.append("")
    lines.append("## Recomputed headline numbers")
    lines.append("")
    status_rows = sorted(recomputed["status_counts"].items())
    lines.extend(_md_table(
        ("quantity", "recomputed", "stored in summary.json"),
        (
            ("stored rows", recomputed["rows"], None),
            ("true evaluations (sum of physical_call_count)", recomputed["true_evaluations"], summary.get("total_true_evaluations")),
            ("cache hits", recomputed["cache_hits"], None),
            ("VALID rows", recomputed["valid_rows"], None),
            ("feasible rows", recomputed["feasible_rows"], None),
            ("first feasible evaluation", recomputed["first_feasible_evaluation"], summary.get("first_feasible_evaluation")),
            ("best feasible objective (kg fuel burn)", recomputed["best_feasible_objective"], summary.get("best_feasible_fuel_kg")),
            ("best design id", recomputed["best_design_id"], summary.get("best_design_id")),
        ),
    ))
    lines.append("")
    lines.extend(_md_table(("status", "rows"), status_rows))
    lines.append("")
    lines.append("## Consistency checks")
    lines.append("")
    lines.extend(_md_table(
        ("check", "subject", "summary", "recomputed", "relative delta", "status"),
        (
            (check["check_id"], check["subject"], check["summary_value"], check["recomputed_value"],
             check["relative_delta"], check["status"])
            for check in report["consistency"]
        ),
    ))
    lines.append("")
    constraints = summary.get("constraints")
    if isinstance(constraints, Mapping):
        lines.append("## Constraint gate")
        lines.append("")
        lines.extend(_md_table(
            ("field", "value"),
            (
                ("constraint names", ", ".join(str(name) for name in (constraints.get("names") or [])) or None),
                ("all g <= 0 (strict)", constraints.get("all_g_le_zero")),
                ("all g <= 0 within tolerance", constraints.get("all_g_le_zero_within_tolerance")),
                ("max constraint excess", constraints.get("max_constraint_excess")),
                ("feasibility tolerance", constraints.get("feasibility_tolerance")),
                ("positive offenders", len(constraints.get("positive_constraint_offenders") or [])),
            ),
        ))
        lines.append("")
    best_design = loaded.get("best_design")
    if isinstance(best_design, Mapping):
        lines.append("## Best design")
        lines.append("")
        lines.extend(_md_table(
            ("field", "value"),
            (
                ("best feasible objective (kg)", _first_present(best_design, "best_feasible_objective", "best_feasible_fuel_kg", "fuel_burn_kg", "objective")),
                ("best design id", _first_present(best_design, "best_design_id", "design_id")),
                ("baseline objective (kg)", _first_present(best_design, "baseline_objective", "baseline_fuel_burn_kg")),
                ("improvement (kg)", _first_present(best_design, "improvement_kg", "improvement")),
                ("first feasible evaluation", _first_present(best_design, "first_feasible_evaluation", "first_feasible")),
                ("feasible", best_design.get("feasible")),
            ),
        ))
        lines.append("")
    lines.append("## Artefacts")
    lines.append("")
    lines.extend(_md_table(
        ("check", "value"),
        (
            ("recorded artefacts", report["artifacts"]["total"]),
            ("present", len(report["artifacts"]["present"])),
            ("missing", len(report["artifacts"]["missing"])),
            ("absolute paths", len(report["artifacts"]["absolute_paths"])),
        ),
    ))
    if report["artifacts"]["missing"]:
        lines.append("")
        lines.append("Missing artefacts:")
        lines.append("")
        for entry in report["artifacts"]["missing"]:
            lines.append("- %s: %s" % (entry["artifact"], entry["path"]))
    if report["artifacts"]["absolute_paths"]:
        lines.append("")
        lines.append("Absolute artefact paths (must not be committed):")
        lines.append("")
        for entry in report["artifacts"]["absolute_paths"]:
            lines.append("- %s" % entry)
    lines.append("")
    lines.append("## Figures")
    lines.append("")
    targets = report["figure_targets"]
    if targets:
        generated = report["figures"].get("generated") or {}
        for name, description in sorted(targets.items()):
            lines.append("- %s: %s%s" % (name, description, (" (redrawn as " + generated[name] + ")") if name in generated else ""))
        lines.append("")
        lines.append("Redraw command: python -m research.concorde_metaopt.reports.figures <run_dir>")
    else:
        lines.append("- no figure artefact detected for this run")
    if report["figures"].get("errors"):
        lines.append("")
        lines.append("Figure errors:")
        lines.append("")
        for error in report["figures"]["errors"]:
            lines.append("- %s" % error)
    lines.append("")
    if report.get("comparison"):
        lines.append("## Method comparison")
        lines.append("")
        lines.extend(_md_table(
            ("run_id", "stage", "method", "status", "true evals", "feasible rows", "best kg", "wall s"),
            (
                (row.get("run_id"), row.get("stage"), row.get("method"), row.get("status"),
                 row.get("true_evaluations"), row.get("feasible_rows"),
                 row.get("best_feasible_fuel_kg"), row.get("wall_seconds"))
                for row in report["comparison"]
            ),
        ))
        lines.append("")
        lines.append("Comparison written to %s and %s." % (COMPARISON_FILENAME, COMPARISON_JSON_FILENAME))
        lines.append("")
    if report["notes"]:
        lines.append("## Notes")
        lines.append("")
        for note in report["notes"]:
            lines.append("- %s" % note)
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("Report status: %s. Consistency failures: %s. Artefact gaps: %d."
                 % (report["report_status"], ", ".join(report["consistency_failures"]) or "none",
                    len(report["artifacts"]["missing"])))
    lines.append("")
    return "\n".join(lines)


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)


def _write_json(path: Path, data: Any) -> None:
    Path(path).write_text(
        json.dumps(_json_ready(data), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_comparison(rows: Sequence[Mapping[str, Any]], run_dir: Path) -> Optional[Dict[str, str]]:
    if len(rows) < 2:
        return None
    csv_path = run_dir / COMPARISON_FILENAME
    json_path = run_dir / COMPARISON_JSON_FILENAME
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key)) for key in fieldnames})
    _write_json(json_path, list(rows))
    return {"csv": _display_path(csv_path), "json": _display_path(json_path)}


def run_report(
    run_id: Optional[str] = None,
    output_root: Optional[Path] = None,
    run_dir: Optional[Path] = None,
    compare_run_ids: Sequence[str] = (),
    rewrite_figures: bool = True,
) -> Dict[str, Any]:
    if run_dir is None:
        if not run_id:
            raise ReportError("either run_id or run_dir is required")
        root = Path(output_root) if output_root else DEFAULT_OUTPUT_ROOT
        run_dir = root / run_id
    run_dir = Path(run_dir)
    loaded = load_run(run_dir)
    figures_block = regenerate_figures(run_dir) if rewrite_figures else {"generated": {}, "errors": []}
    comparison: List[Dict[str, Any]] = []
    if compare_run_ids:
        root = run_dir.parent
        for compare_id in compare_run_ids:
            compare_dir = root / compare_id
            try:
                comparison.append(_comparison_row(load_run(compare_dir)))
            except (ReportError, OSError, ValueError):
                comparison.append({"run_id": compare_id, "status": "unavailable", "path": _display_path(compare_dir)})
        comparison.insert(0, _comparison_row(loaded))
        written = _write_comparison(comparison, run_dir)
    else:
        written = None
    report = build_report(loaded, figures_block, comparison)
    report["comparison_files"] = written
    markdown = render_markdown(report, loaded)
    (run_dir / REPORT_FILENAME).write_text(markdown, encoding="utf-8")
    _write_json(run_dir / REPORT_JSON_FILENAME, report)
    return {"report": report, "run_dir": run_dir}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild a run report from stored artefacts.")
    parser.add_argument("--run-id", required=True, help="committed run id")
    parser.add_argument("--output-root", default=None, help="default: research/concorde_metaopt/optimization_runs")
    parser.add_argument("--compare-run", action="append", default=[], help="additional run id for the comparison table")
    parser.add_argument("--no-figures", action="store_true", help="do not redraw figures")
    arguments = parser.parse_args(argv)
    try:
        result = run_report(
            run_id=arguments.run_id,
            output_root=Path(arguments.output_root) if arguments.output_root else None,
            compare_run_ids=tuple(arguments.compare_run),
            rewrite_figures=not arguments.no_figures,
        )
    except (ReportError, OSError, ValueError) as error:
        print(json.dumps({"status": "report_failed", "error": str(error)}, indent=2, ensure_ascii=False))
        return 1
    report = result["report"]
    print(json.dumps({
        "run_id": report["run_id"],
        "report_status": report["report_status"],
        "consistency_failures": report["consistency_failures"],
        "missing_artifacts": len(report["artifacts"]["missing"]),
        "figures": report["figures"]["generated"],
        "report": report["report_path"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["report_status"].startswith(STATUS_COMPLETED) else 1


if __name__ == "__main__":
    raise SystemExit(main())
