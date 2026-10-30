"""Phase I P2 smoke run: baseline repeatability plus two real perturbations.

Five true single-cruise evaluations (about 80 s each): the frozen baseline three
times, then one wing-area perturbation and one tip-twist perturbation. The run
writes the P2 evidence bundle, and the figures are redrawn from the JSONL/CSV
artifacts only.
"""

from __future__ import annotations

import json
import math
import platform
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..aircraft.design_space import DesignSpace, load_design_space
from ..aircraft.geometry_checks import (
    _display_path,
    _git_sha,
    _software_versions,
    _write_csv,
    _write_json,
    _write_jsonl,
)
from ..aircraft.geometry_model import GEOMETRY_MODEL_VERSION
from ..tasks.task_spec import FixedCruiseTask, TASK_SPEC_VERSION, load_task_spec
from .contract import (
    CONSTRAINT_NAMES,
    FEASIBILITY_TOLERANCE,
    OBJECTIVE_NAME,
    OBJECTIVE_UNIT,
    RESIDUAL_LIMIT,
    empty_constraints,
    feasibility,
)
from .ledger import EvaluationLedger
from .low_fidelity import FIDELITY_SINGLE_CRUISE, SingleCruiseBackend
from ..run_paths import RunPathError, resolve_run_directory

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"

STAGE = "P2"
METHOD = "single_cruise_smoke"
SMOKE_BUDGET = 5
REPEAT_COUNT = 3
REPEATABILITY_RELATIVE_TOLERANCE = 1.0e-6
PERTURBATIONS = (
    {"label": "W01_plus_1pct", "variable": "W01", "kind": "relative", "delta": 0.01},
    {"label": "W10_plus_2deg", "variable": "W10", "kind": "absolute", "delta": 2.0},
)


class SmokeError(RuntimeError):
    pass


def _summary_base(run_id: str, git_sha: Optional[str]) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "stage": STAGE,
        "task_id": None,
        "method": METHOD,
        "seed": None,
        "git_sha": git_sha,
        "solver_versions": {},
        "design_dim": 15,
        "status": "smoke_failed",
        "total_true_evaluations": 0,
        "low_fidelity_calls": 0,
        "su2_calls": 0,
        "invalid_count": 0,
        "failed_count": 0,
        "first_feasible_evaluation": None,
        "best_feasible_fuel_kg": None,
        "best_design_id": None,
        "wall_seconds": 0.0,
        "cpu_seconds_if_available": None,
        "artifacts": {},
        "objective": {"name": OBJECTIVE_NAME, "unit": OBJECTIVE_UNIT, "direction": "minimize"},
        "constraints": {
            "names": list(CONSTRAINT_NAMES),
            "feasibility_tolerance": FEASIBILITY_TOLERANCE,
            "residual_limit": RESIDUAL_LIMIT,
            "all_g_le_zero": None,
            "all_g_le_zero_within_tolerance": None,
            "max_constraint_excess": None,
            "rows_checked": 0,
        },
    }


def _perturbed_design(space: DesignSpace, spec: Mapping[str, Any]) -> Dict[str, float]:
    design = dict(space.baseline_dict())
    variable = space.variable_by_id(str(spec["variable"]))
    baseline = float(design[variable.name])
    if spec["kind"] == "relative":
        value = baseline * (1.0 + float(spec["delta"]))
    else:
        value = baseline + float(spec["delta"])
    if not variable.contains(value):
        raise SmokeError(
            "perturbation %s produced %s=%s outside [%s, %s]"
            % (spec["label"], variable.name, value, variable.lower, variable.upper)
        )
    design[variable.name] = float(value)
    return design


def _repeatability_metrics(values: List[float]) -> Dict[str, Any]:
    finite = [float(value) for value in values]
    if not finite:
        return {"count": 0, "objective_values": [], "relative_spread": None, "passed": False}
    low = min(finite)
    high = max(finite)
    mean = sum(finite) / len(finite)
    spread = 0.0 if mean == 0.0 else (high - low) / abs(mean)
    return {
        "count": len(finite),
        "objective_values": finite,
        "objective_max": high,
        "objective_min": low,
        "objective_mean": mean,
        "relative_spread": spread,
        "tolerance": REPEATABILITY_RELATIVE_TOLERANCE,
        "passed": spread <= REPEATABILITY_RELATIVE_TOLERANCE,
    }


def _constraint_delta(first: Mapping[str, float], second: Mapping[str, float]) -> Optional[float]:
    if not first or not second:
        return None
    keys = [name for name in first if name in second]
    if not keys:
        return None
    return max(abs(float(first[name]) - float(second[name])) for name in keys)


def _constraint_gate(rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Strict and tolerance-aware audit of the g <= 0 contract over the rows.

    The strict flag is exactly "every recorded constraint value is <= 0"; the
    tolerance-aware flag uses FEASIBILITY_TOLERANCE so numerical round-off in a
    converged mission is visible instead of silently claimed as feasible. Missing
    or non-finite constraint values fail both flags.
    """
    offenders: List[Dict[str, Any]] = []
    missing: List[str] = []
    max_excess: Optional[float] = None
    strict = True
    tolerant = True
    for row in rows:
        constraints = row.get("constraints")
        if not isinstance(constraints, Mapping) or not constraints:
            strict = False
            tolerant = False
            missing.append(str(row.get("design_id")))
            continue
        for name, value in constraints.items():
            if value is None:
                strict = False
                tolerant = False
                missing.append("%s:%s" % (row.get("design_id"), name))
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                strict = False
                tolerant = False
                missing.append("%s:%s" % (row.get("design_id"), name))
                continue
            if not math.isfinite(numeric):
                strict = False
                tolerant = False
                missing.append("%s:%s" % (row.get("design_id"), name))
                continue
            if max_excess is None or numeric > max_excess:
                max_excess = numeric
            if numeric > 0.0:
                strict = False
                offenders.append(
                    {
                        "design_id": row.get("design_id"),
                        "constraint": str(name),
                        "value": numeric,
                    }
                )
            if numeric > FEASIBILITY_TOLERANCE:
                tolerant = False
    return {
        "all_g_le_zero": bool(strict and rows),
        "all_g_le_zero_within_tolerance": bool(tolerant and rows),
        "max_constraint_excess": max_excess,
        "rows_checked": len(rows),
        "positive_constraint_offenders": offenders[:50],
        "missing_constraint_entries": missing[:50],
        "strict_note": (
            "strict compares every constraint value against 0.0; the tolerance-aware "
            "flag uses feasibility_tolerance for numerical round-off"
        ),
    }


def _cross_check_summary(record: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Compact geometry cross-check block from a backend record, if present."""
    if not record:
        return None
    cross = record.get("geometry_cross_check")
    if not isinstance(cross, Mapping):
        return None
    return {
        "checked_count": cross.get("checked_count"),
        "failed_count": cross.get("failed_count"),
        "failures": list(cross.get("failures") or []),
    }


def _violated_constraints(constraints: Mapping[str, Any]) -> List[str]:
    return [
        name
        for name, value in constraints.items()
        if value is not None and float(value) > FEASIBILITY_TOLERANCE
    ]


def _sanitized_config_summary(space: DesignSpace) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(space.config_summary()) if hasattr(space, "config_summary") else {}
    config_path = data.get("config_path")
    if config_path:
        data["config_path"] = _display_path(config_path)
    return data


def _sanitize_preflight(preflight: Mapping[str, Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(preflight)
    config_summary = data.get("design_space_config")
    if isinstance(config_summary, Mapping):
        summary = dict(config_summary)
        if summary.get("config_path"):
            summary["config_path"] = _display_path(summary["config_path"])
        data["design_space_config"] = summary
    return data


def _index_summary(summary: Mapping[str, Any]) -> str:
    smoke = summary.get("smoke") or {}
    repeat = smoke.get("repeatability") or {}
    baseline = smoke.get("baseline") or {}
    violated = _violated_constraints(baseline.get("constraints") or {})
    text = (
        "P2 single-cruise smoke: status %s, %s true evaluations, baseline objective %s kg, "
        "repeatability spread %s (passed=%s)"
        % (
            summary.get("status"),
            summary.get("total_true_evaluations"),
            baseline.get("objective"),
            repeat.get("relative_spread"),
            repeat.get("passed"),
        )
    )
    if violated:
        text += "; baseline constraint violations: " + ", ".join(violated)
    return text


def _environment(task: FixedCruiseTask, space: DesignSpace) -> Dict[str, Any]:
    packages = _software_versions()
    return {
        "python": platform.python_version(),
        "python_executable": _display_path(__import__("sys").executable),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "geometry_model_version": GEOMETRY_MODEL_VERSION,
        "task_spec_version": TASK_SPEC_VERSION,
        "task_id": task.task_id,
        "packages": packages,
        "design_space_config": _display_path(space.config_path) if getattr(space, "config_path", None) else None,
        "task_config": _display_path(task.config_path) if getattr(task, "config_path", None) else None,
    }


def _smoke_cases_csv(
    rows: List[Mapping[str, Any]],
    repeats: int,
    labels: List[str],
    metas: List[Optional[Mapping[str, Any]]],
) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        label = labels[index] if index < len(labels) else "unknown"
        meta = metas[index] if index < len(metas) and metas[index] is not None else {}
        constraints = row.get("constraints") or {}
        cases.append(
            {
                "iteration": row["iteration"],
                "design_id": row["design_id"],
                "case_label": label,
                "case_kind": "baseline_repeat" if index < repeats else "perturbation",
                "status": row["status"],
                "objective": row["objective"],
                "feasible": row["feasible"],
                "max_throttle": constraints.get("max_throttle"),
                "violated_constraints": ";".join(meta.get("violated_constraints") or []),
                "geometry_cross_check_failed": meta.get("geometry_cross_check_failed"),
                "physical_call_count": row["physical_call_count"],
            }
        )
    return cases


def _format_mass(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, (int, float)):
        return "%g" % value
    return str(value)


def _mass_contract_line(contract: Any) -> str:
    if not isinstance(contract, Mapping):
        return "Frozen mass contract: not recorded"
    applied = contract.get("applied") if isinstance(contract.get("applied"), Mapping) else contract
    readback = contract.get("readback") if isinstance(contract.get("readback"), Mapping) else None
    start = applied.get("takeoff", applied.get("start_mass_kg"))
    fuel = applied.get("fuel", applied.get("fuel_loaded_kg"))
    oew = applied.get("operating_empty", applied.get("operating_empty_kg"))
    payload = applied.get("payload", applied.get("payload_kg"))
    cargo = applied.get("cargo", applied.get("cargo_kg"))
    zfw = None
    if None not in (oew, payload, cargo):
        zfw = float(oew) + float(payload) + float(cargo)
    else:
        zfw = applied.get("zero_fuel_mass_kg", applied.get("zero_fuel_mass"))
    line = "Frozen mass contract: start %s kg, loaded fuel %s kg, ZFW %s kg" % (
        _format_mass(start),
        _format_mass(fuel),
        _format_mass(zfw),
    )
    if readback is not None:
        rb_start = readback.get("takeoff", readback.get("start_mass_kg"))
        rb_fuel = readback.get("fuel", readback.get("fuel_loaded_kg"))
        if rb_start is not None and start is not None and abs(float(rb_start) - float(start)) > 1e-9:
            line += " (readback start %s kg)" % _format_mass(rb_start)
        if rb_fuel is not None and fuel is not None and abs(float(rb_fuel) - float(fuel)) > 1e-9:
            line += " (readback fuel %s kg)" % _format_mass(rb_fuel)
    return line


def _run_readme(summary: Mapping[str, Any]) -> str:
    smoke = summary.get("smoke", {})
    repeat = smoke.get("repeatability", {})
    constraints = summary.get("constraints", {})
    lines = [
        "# P2 single-cruise smoke run",
        "",
        "Run id: %s" % summary.get("run_id"),
        "Status: %s" % summary.get("status"),
        "Git: %s on %s" % (summary.get("git_sha"), summary.get("branch")),
        "Task: %s (frozen mass contract)" % summary.get("task_id"),
        "Fidelity: single_cruise (RCAIDE mission, no CFD)",
        "",
        "True evaluations: %s (budget %s)" % (
            summary.get("total_true_evaluations"), smoke.get("budget")
        ),
        _mass_contract_line(smoke.get("mass_contract")),
        "Baseline repeats: %s (%s/%s valid rows), relative spread %s (tolerance %s), passed=%s" % (
            repeat.get("count"),
            repeat.get("valid_rows"),
            repeat.get("required_rows"),
            repeat.get("relative_spread"),
            repeat.get("tolerance"),
            repeat.get("passed"),
        ),
        "Constraint gate: strict all g<=0=%s, within tolerance %s=%s, max excess %s over %s rows" % (
            constraints.get("all_g_le_zero"),
            constraints.get("feasibility_tolerance"),
            constraints.get("all_g_le_zero_within_tolerance"),
            constraints.get("max_constraint_excess"),
            constraints.get("rows_checked"),
        ),
        "",
        "Cases:",
    ]
    for case in smoke.get("perturbations", []):
        lines.append(
            "- %s: %s %s -> objective %s (status %s, feasible %s)"
            % (
                case.get("label"),
                case.get("variable"),
                case.get("value"),
                case.get("objective"),
                case.get("status"),
                case.get("feasible"),
            )
        )
    lines += [
        "",
        "This run evaluates the RCAIDE single cruise segment only. It says nothing",
        "about full-mission fuel burn, SU2/CFD fidelity or MAML benefit. The three",
        "baseline repeats were executed with the cache disabled to measure true",
        "repeatability; only valid evaluations are cached by the ledger.",
        "",
    ]
    artifacts = summary.get("artifacts") or {}
    artifact_names = [
        "summary.json",
        "run_config.json",
        "environment.json",
        "best_design.json",
        "evaluations.jsonl",
    ]
    detail_note = []
    if "evaluations_detail" in artifacts:
        artifact_names.append("evaluations_detail.jsonl")
        detail_note = [
            "The detail file repeats every true evaluation with the full backend",
            "record (mission responses and geometry cross-check); the compact",
            "evaluations.jsonl keeps the Issue schema.",
        ]
    artifact_names += ["smoke_cases.csv", "figures/"]
    lines.append("Artifacts: " + ", ".join(artifact_names) + ".")
    if detail_note:
        lines += [""] + detail_note
    return "\n".join(lines) + "\n"


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
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "path": run_dir.name,
            "summary": _index_summary(summary),
            "true_evaluations": summary.get("total_true_evaluations"),
        }
    )
    payload["runs"] = entries
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(index_path, payload, True)
    return index_path


def run_smoke(
    output_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    seed: int = 42,
    budget: int = SMOKE_BUDGET,
    task: Optional[FixedCruiseTask] = None,
    design_space: Optional[DesignSpace] = None,
    backend: Any = None,
    allow_existing: bool = False,
    verify_tutorial_hash: bool = True,
) -> Dict[str, Any]:
    """Run the P2 smoke evidence bundle and return its summary."""
    started = time.perf_counter()
    cpu_started = time.process_time()
    if budget < SMOKE_BUDGET:
        raise SmokeError("smoke budget must be at least %d true evaluations" % SMOKE_BUDGET)

    space = design_space if design_space is not None else load_design_space()
    frozen_task = task if task is not None else load_task_spec()
    backend = backend if backend is not None else SingleCruiseBackend(
        design_space=space, task=frozen_task, verify_tutorial_hash=verify_tutorial_hash
    )
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    generated = (
        time.strftime("smoke-p2-%Y%m%dT%H%M%S", time.gmtime())
        if run_id is None
        else run_id
    )
    try:
        run_dir = resolve_run_directory(root, generated, allow_existing=allow_existing)
    except RunPathError as exc:
        raise SmokeError(str(exc)) from exc
    (run_dir / "figures").mkdir(exist_ok=True)

    git_sha = _git_sha(REPO_ROOT)
    summary = _summary_base(generated, git_sha)
    summary["design_dim"] = space.design_dim
    summary["design_set"] = space.design_set
    summary["task_id"] = frozen_task.task_id
    summary["seed"] = int(seed)
    summary["branch"] = None
    import subprocess

    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if branch.returncode == 0:
            summary["branch"] = branch.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        summary["branch"] = None

    preflight = _sanitize_preflight(backend.preflight())
    ledger = EvaluationLedger(budget=budget, run_dir=run_dir, cache_enabled=False)
    baseline = dict(space.baseline_dict())
    repeat_rows: List[Dict[str, Any]] = []
    repeat_records: List[Mapping[str, Any]] = []
    failures: List[str] = []
    for repeat in range(REPEAT_COUNT):
        try:
            row = ledger.evaluate(backend, baseline, frozen_task, fidelity=FIDELITY_SINGLE_CRUISE)
        except Exception as exc:
            failures.append("baseline repeat %d failed: %s: %s" % (repeat + 1, type(exc).__name__, exc))
            break
        repeat_rows.append(row)
        if ledger.records:
            repeat_records.append(ledger.records[-1])

    repeat_values = [row["objective"] for row in repeat_rows if row["objective"] is not None]
    repeatability = _repeatability_metrics(repeat_values)
    repeatability["constraint_max_abs_delta"] = (
        _constraint_delta(repeat_rows[0]["constraints"], repeat_rows[-1]["constraints"])
        if len(repeat_rows) >= 2
        else None
    )
    valid_repeats = [
        row for row in repeat_rows if row["status"] == "VALID" and row["objective"] is not None
    ]
    repeatability["rows_recorded"] = len(repeat_rows)
    repeatability["valid_rows"] = len(valid_repeats)
    repeatability["required_rows"] = REPEAT_COUNT
    if len(repeat_rows) != REPEAT_COUNT or len(valid_repeats) != REPEAT_COUNT:
        repeatability["passed"] = False
        repeatability["reason"] = (
            "expected %d VALID baseline repeats, recorded %d rows with %d valid objectives"
            % (REPEAT_COUNT, len(repeat_rows), len(valid_repeats))
        )
    elif repeatability.get("relative_spread") is None:
        repeatability["passed"] = False
        repeatability["reason"] = "no usable baseline objective values";

    perturbation_cases: List[Dict[str, Any]] = []
    perturbation_rows: List[Dict[str, Any]] = []
    perturbation_metas: List[Mapping[str, Any]] = []
    baseline_row = repeat_rows[0] if repeat_rows else None
    labels = ["baseline_repeat_%d" % (index + 1) for index in range(len(repeat_rows))]
    for spec in PERTURBATIONS:
        labels.append(spec["label"])
        try:
            design = _perturbed_design(space, spec)
            row = ledger.evaluate(backend, design, frozen_task, fidelity=FIDELITY_SINGLE_CRUISE)
            perturbation_rows.append(row)
            case_record = ledger.records[-1] if ledger.records else None
            case_cross_check = _cross_check_summary(case_record)
            base_objective = baseline_row["objective"] if baseline_row else None
            variable = space.variable_by_id(str(spec["variable"]))
            case = {
                "label": spec["label"],
                "variable": spec["variable"],
                "variable_name": variable.name,
                "kind": spec["kind"],
                "delta": spec["delta"],
                "value": design[variable.name],
                "baseline_value": baseline[variable.name],
                "design_id": row["design_id"],
                "status": row["status"],
                "objective": row["objective"],
                "feasible": row["feasible"],
                "violated_constraints": _violated_constraints(row["constraints"]),
                "max_throttle": row["constraints"].get("max_throttle"),
                "geometry_cross_check": case_cross_check,
                "geometry_cross_check_failed": bool((case_cross_check or {}).get("failed_count")),
                "objective_delta": (
                    None
                    if base_objective is None or row["objective"] is None
                    else row["objective"] - base_objective
                ),
                "objective_relative_delta": (
                    None
                    if base_objective in (None, 0.0) or row["objective"] is None
                    else (row["objective"] - base_objective) / base_objective
                ),
                "constraints": dict(row["constraints"]),
            }
            perturbation_cases.append(case)
            perturbation_metas.append(
                {
                    "violated_constraints": case["violated_constraints"],
                    "geometry_cross_check_failed": case["geometry_cross_check_failed"],
                }
            )
        except Exception as exc:
            failures.append("%s failed: %s: %s" % (spec["label"], type(exc).__name__, exc))
            perturbation_cases.append(
                {"label": spec["label"], "variable": spec["variable"], "status": "SMOKE_CASE_ERROR", "error": str(exc)}
            )

    case_metas: List[Optional[Mapping[str, Any]]] = []
    for row, record in zip(repeat_rows, repeat_records):
        case_metas.append(
            {
                "violated_constraints": _violated_constraints(row["constraints"]),
                "geometry_cross_check_failed": bool((_cross_check_summary(record) or {}).get("failed_count")),
            }
        )
    case_metas.extend(perturbation_metas)
    cases = _smoke_cases_csv(repeat_rows + perturbation_rows, len(repeat_rows), labels, case_metas)
    _write_csv(run_dir / "smoke_cases.csv", cases)

    counts = ledger.summary()
    summary["constraints"].update(_constraint_gate(ledger.rows))
    summary.update(
        {
            "total_true_evaluations": int(counts["total_true_evaluations"]),
            "low_fidelity_calls": int(counts["total_true_evaluations"]),
            "su2_calls": 0,
            "invalid_count": int(counts["invalid_count"]),
            "failed_count": int(counts["failed_count"]),
            "first_feasible_evaluation": counts["first_feasible_evaluation"],
            "best_feasible_fuel_kg": counts["best_feasible_fuel_kg"],
            "best_design_id": counts["best_design_id"],
            "wall_seconds": round(time.perf_counter() - started, 3),
            "cpu_seconds_if_available": round(time.process_time() - cpu_started, 3),
        }
    )
    if summary["best_design_id"]:
        for row in ledger.rows:
            if row["design_id"] == summary["best_design_id"] and row["feasible"]:
                _write_json(
                    run_dir / "best_design.json",
                    {
                        "run_id": generated,
                        "design_id": summary["best_design_id"],
                        "objective_name": OBJECTIVE_NAME,
                        "objective_unit": OBJECTIVE_UNIT,
                        "fuel_burn_kg": row["objective"],
                        "feasible": True,
                        "design": row["x"],
                        "constraints": row["constraints"],
                        "fidelity": row["fidelity"],
                        "task_id": frozen_task.task_id,
                    },
                    True,
                )
                break
    else:
        _write_json(
            run_dir / "best_design.json",
            {"run_id": generated, "feasible": False, "design": None},
            True,
        )

    summary["smoke"] = {
        "budget": int(budget),
        "preflight": preflight,
        "repeat_count": REPEAT_COUNT,
        "repeatability": repeatability,
        "baseline": {
            "design_id": baseline_row["design_id"] if baseline_row else None,
            "status": baseline_row["status"] if baseline_row else None,
            "objective": baseline_row["objective"] if baseline_row else None,
            "feasible": baseline_row["feasible"] if baseline_row else None,
            "constraints": dict(baseline_row["constraints"]) if baseline_row else {},
            # Sanitised ledger rows only: the raw backend record may still carry
            # an objective for a failed status, which must never be written into
            # the summary as if it were an evaluation result.
            "records": [
                {
                    "iteration": row["iteration"],
                    "design_id": row["design_id"],
                    "status": row["status"],
                    "objective": row["objective"],
                    "feasible": row["feasible"],
                    "constraints": dict(row["constraints"]),
                    "fidelity": row["fidelity"],
                    "cache_hit": row["cache_hit"],
                    "physical_call_count": row["physical_call_count"],
                    "wall_seconds": row["wall_seconds"],
                    "diagnostics": list(row["diagnostics"]),
                }
                for row in repeat_rows
            ],
            "mass_contract": repeat_records[0].get("mass_contract") if repeat_records else None,
            "geometry_cross_check": _cross_check_summary(repeat_records[0] if repeat_records else None),
        },
        "mass_contract": repeat_records[0].get("mass_contract") if repeat_records else None,
        "geometry_cross_check": _cross_check_summary(repeat_records[0] if repeat_records else None),
        "perturbations": perturbation_cases,
        "case_file": "smoke_cases.csv",
        "failures": failures,
        "ledger": counts,
        "note": "single_cruise RCAIDE mission only; no full mission, no CFD, no MAML",
    }

    if not repeatability.get("passed", False):
        summary["status"] = "smoke_repeatability_failed"
    elif failures or counts["failed_count"] or baseline_row is None or not baseline_row["feasible"]:
        summary["status"] = "smoke_completed_with_failures"
    else:
        summary["status"] = "smoke_completed"

    summary["solver_versions"] = {
        "RCAIDE-LEADS": _software_versions().get("RCAIDE-LEADS"),
        "numpy": _software_versions().get("numpy"),
        "scipy": _software_versions().get("scipy"),
        "matplotlib": _software_versions().get("matplotlib"),
        "RCAIDE_module": _software_versions().get("RCAIDE_module"),
    }
    summary["artifacts"] = {
        "summary": "summary.json",
        "run_config": "run_config.json",
        "environment": "environment.json",
        "best_design": "best_design.json",
        "evaluations": "evaluations.jsonl",
        "evaluations_detail": "evaluations_detail.jsonl",
        "smoke_cases": "smoke_cases.csv",
        "figures": ["figures/repeatability.png", "figures/perturbation_sensitivity.png"],
        "readme": "README.md",
        "task_config": _display_path(frozen_task.config_path) if getattr(frozen_task, "config_path", None) else None,
        "design_space_config": _display_path(space.config_path) if getattr(space, "config_path", None) else None,
    }

    _write_json(run_dir / "task_spec.json", frozen_task.run_record(), True)
    _write_json(run_dir / "environment.json", _environment(frozen_task, space), True)
    _write_jsonl(run_dir / "evaluations.jsonl", ledger.rows)
    _write_json(
        run_dir / "run_config.json",
        {
            "run_id": generated,
            "stage": STAGE,
            "method": METHOD,
            "git_sha": git_sha,
            "branch": summary.get("branch"),
            "seed": summary["seed"],
            "budget": int(budget),
            "repeat_count": REPEAT_COUNT,
            "repeatability_relative_tolerance": REPEATABILITY_RELATIVE_TOLERANCE,
            "perturbations": [dict(spec) for spec in PERTURBATIONS],
            "task": frozen_task.run_record(),
            "task_fingerprint": frozen_task.fingerprint(),
            "design_space": _sanitized_config_summary(space),
            "cache_enabled": False,
            "fidelity": FIDELITY_SINGLE_CRUISE,
            "note": "cache disabled so the three baseline repeats are genuine physical calls",
        },
        True,
    )
    _write_json(run_dir / "summary.json", summary, True)
    (run_dir / "README.md").write_text(_run_readme(summary), encoding="utf-8")

    try:
        from ..reports.figures import plot_smoke_artifacts

        plot_smoke_artifacts(run_dir)
    except Exception as exc:  # figures are evidence, not the primary result
        summary.setdefault("smoke", {})["figure_error"] = "%s: %s" % (type(exc).__name__, exc)

    _update_index(run_dir, summary)
    return summary
