"""P1 geometry figures.

Every figure is produced only from files stored in the run directory
(geometry_effect_delta.csv and geometry_planforms.json), so it can be redrawn
without rerunning the geometry checks::

    python -m research.concorde_metaopt.reports.figures <run_dir>

The heat map shows, per design variable, the largest relative change of a
selected derived metric under the +delta and -delta perturbation.  The planform
panel overlays the baseline geometry with the perturbations of the wing, tail
and fuselage variables.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HEATMAP_METRICS: List[Tuple[str, str]] = [
    ("wing_span_m", "wing span"),
    ("wing_root_chord_m", "wing root chord"),
    ("wing_mac_m", "wing MAC"),
    ("wing_wetted_area_m2", "wing wetted area"),
    ("wing_ac_x_m", "wing AC x"),
    ("tail_span_m", "tail span"),
    ("tail_root_chord_m", "tail root chord"),
    ("tail_ac_x_m", "tail AC x"),
    ("fuselage_length_m", "fuselage length"),
    ("fuselage_wetted_area_m2", "fuselage wetted area"),
    ("fuselage_usable_volume_m3", "fuselage usable volume"),
    ("cg_x_m", "CG x"),
    ("static_margin", "static margin"),
    ("mass_total_takeoff_kg", "takeoff mass"),
]

WING_CASES = ("W01_plus", "W01_minus", "W02_plus", "W02_minus")
TAIL_CASES = ("V01_plus", "V01_minus", "V02_plus", "V02_minus")
FUSELAGE_CASES = ("F01_plus", "F01_minus", "F02_plus", "F02_minus", "F03_plus", "F03_minus")


def plot_geometry_artifacts(run_dir: Path) -> Dict[str, str]:
    """Create the two P1 figures; returns paths keyed by artifact name."""
    run_dir = Path(run_dir)
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    delta_rows = _read_delta_rows(run_dir / "geometry_effect_delta.csv")
    planforms = json.loads((run_dir / "geometry_planforms.json").read_text(encoding="utf-8"))
    heatmap_path = figures_dir / "geometry_effect_heatmap.png"
    planform_path = figures_dir / "wing_planform_comparison.png"
    _plot_heatmap(delta_rows, heatmap_path)
    _plot_planforms(planforms, planform_path)
    return {
        "geometry_effect_heatmap": str(heatmap_path.relative_to(run_dir)),
        "wing_planform_comparison": str(planform_path.relative_to(run_dir)),
    }


def _read_delta_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _plot_heatmap(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    variables = sorted({row["variable_id"] for row in rows if row["variable_id"]})
    variable_names = {row["variable_id"]: row["variable_name"] for row in rows}
    matrix = np.zeros((len(HEATMAP_METRICS), len(variables)))
    for row in rows:
        if row["variable_id"] not in variables:
            continue
        try:
            relative = abs(float(row["relative_delta"]))
        except (TypeError, ValueError):
            continue
        row_index = next(
            (index for index, (metric, _) in enumerate(HEATMAP_METRICS) if metric == row["metric"]), None
        )
        if row_index is None:
            continue
        column_index = variables.index(row["variable_id"])
        matrix[row_index, column_index] = max(matrix[row_index, column_index], relative)
    figure, axis = plt.subplots(figsize=(15.5, 7.4))
    image = axis.imshow(matrix, aspect="auto", cmap="viridis")
    axis.set_xticks(range(len(variables)))
    axis.set_xticklabels(
        ["%s %s" % (identifier, variable_names.get(identifier, "")) for identifier in variables],
        rotation=45,
        ha="right",
        fontsize=8,
    )
    axis.set_yticks(range(len(HEATMAP_METRICS)))
    axis.set_yticklabels([label for _, label in HEATMAP_METRICS], fontsize=9)
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = matrix[row_index, column_index]
            if value > 0.0:
                axis.text(
                    column_index,
                    row_index,
                    "%.2f" % value,
                    ha="center",
                    va="center",
                    color="white" if value < 0.6 * matrix.max() else "black",
                    fontsize=6.5,
                )
    colorbar = figure.colorbar(image, ax=axis, fraction=0.025, pad=0.02)
    colorbar.set_label("max |relative change| under +-delta perturbation")
    axis.set_title(
        "P1 geometry effect matrix: each design variable versus derived geometry metrics\n"
        "(delta = 10 percent of the variable bound span; values are |delta / baseline|)"
    )
    axis.set_xlabel("design variable")
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)


def _plot_planforms(planforms: Mapping[str, Any], path: Path) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(15.0, 9.0))
    wing_axis, tail_axis = axes[0][0], axes[0][1]
    fuselage_height_axis, fuselage_width_axis = axes[1][0], axes[1][1]
    colors = {
        "baseline": ("black", "-", 2.2),
        "W01_plus": ("#d62728", "-", 1.6),
        "W01_minus": ("#1f77b4", "--", 1.6),
        "W02_plus": ("#ff7f0e", "-.", 1.4),
        "W02_minus": ("#2ca02c", ":", 1.4),
        "V01_plus": ("#d62728", "-", 1.6),
        "V01_minus": ("#1f77b4", "--", 1.6),
        "V02_plus": ("#ff7f0e", "-.", 1.4),
        "V02_minus": ("#2ca02c", ":", 1.4),
        "F01_plus": ("#d62728", "-", 1.6),
        "F01_minus": ("#1f77b4", "--", 1.6),
        "F02_plus": ("#ff7f0e", "-.", 1.4),
        "F02_minus": ("#2ca02c", ":", 1.4),
        "F03_plus": ("#9467bd", "-", 1.2),
        "F03_minus": ("#8c564b", "--", 1.2),
    }
    for case_id in ("baseline",) + WING_CASES:
        if case_id not in planforms:
            continue
        color, linestyle, width = colors[case_id]
        _draw_wing(wing_axis, planforms[case_id], color, linestyle, width, _legend_label(case_id))
    wing_axis.set_title("Main wing planform (baseline vs W01/W02 perturbations)")
    wing_axis.set_xlabel("body station x [m]")
    wing_axis.set_ylabel("semi-span y [m]")
    wing_axis.legend(fontsize=7, loc="upper right")
    wing_axis.grid(True, alpha=0.3)
    wing_axis.set_aspect("equal", adjustable="datalim")

    for case_id in ("baseline",) + TAIL_CASES:
        if case_id not in planforms:
            continue
        color, linestyle, width = colors[case_id]
        _draw_tail(tail_axis, planforms[case_id], color, linestyle, width, _legend_label(case_id))
    tail_axis.set_title("Vertical tail planform (baseline vs V01/V02 perturbations)")
    tail_axis.set_xlabel("body station x [m]")
    tail_axis.set_ylabel("height z [m]")
    tail_axis.legend(fontsize=7, loc="upper right")
    tail_axis.grid(True, alpha=0.3)

    for case_id in ("baseline",) + FUSELAGE_CASES:
        if case_id not in planforms:
            continue
        color, linestyle, width = colors[case_id]
        _draw_fuselage(
            fuselage_height_axis,
            fuselage_width_axis,
            planforms[case_id],
            color,
            linestyle,
            width,
            _legend_label(case_id),
        )
    fuselage_height_axis.set_title("Fuselage side profile (half height)")
    fuselage_height_axis.set_xlabel("body station x [m]")
    fuselage_height_axis.set_ylabel("half height [m]")
    fuselage_height_axis.legend(fontsize=7, loc="upper right")
    fuselage_height_axis.grid(True, alpha=0.3)
    fuselage_width_axis.set_title("Fuselage plan profile (half width)")
    fuselage_width_axis.set_xlabel("body station x [m]")
    fuselage_width_axis.set_ylabel("half width [m]")
    fuselage_width_axis.legend(fontsize=7, loc="upper right")
    fuselage_width_axis.grid(True, alpha=0.3)
    figure.suptitle(
        "P1 geometry comparison: baseline and single-variable perturbations "
        "(delta = 10 percent of the variable bound span)",
        fontsize=11,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(path, dpi=140)
    plt.close(figure)


def _legend_label(case_id: str) -> str:
    if case_id == "baseline":
        return "baseline"
    identifier, direction = case_id.rsplit("_", 1)
    return "%s %s" % (identifier, "+delta" if direction == "plus" else "-delta")


def _draw_wing(axis: Any, planform: Mapping[str, Any], color: str, linestyle: str, width: float, label: str) -> None:
    sections = planform["wing"]
    origin_x = planform["wing_origin_x_m"]
    half_span = 0.5 * planform["wing_span_m"]
    leading = [(origin_x + section["leading_edge_x_m"], section["span_fraction"] * half_span) for section in sections]
    trailing = [
        (origin_x + section["trailing_edge_x_m"], section["span_fraction"] * half_span) for section in sections
    ]
    polygon = leading + list(reversed(trailing))
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    axis.plot(xs + [xs[0]], ys + [ys[0]], color=color, linestyle=linestyle, linewidth=width, label=label)


def _draw_tail(axis: Any, planform: Mapping[str, Any], color: str, linestyle: str, width: float, label: str) -> None:
    sections = planform["vertical_tail"]
    origin_x = planform["tail_origin_x_m"]
    span = planform["tail_span_m"]
    leading = [(origin_x + section["leading_edge_x_m"], section["span_fraction"] * span) for section in sections]
    trailing = [
        (origin_x + section["trailing_edge_x_m"], section["span_fraction"] * span) for section in sections
    ]
    polygon = leading + list(reversed(trailing))
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    axis.plot(xs + [xs[0]], ys + [ys[0]], color=color, linestyle=linestyle, linewidth=width, label=label)


def _draw_fuselage(
    height_axis: Any,
    width_axis: Any,
    planform: Mapping[str, Any],
    color: str,
    linestyle: str,
    width: float,
    label: str,
) -> None:
    stations = planform["fuselage"]
    stations = sorted(stations, key=lambda station: station["x_m"])
    xs = [station["x_m"] for station in stations]
    heights = [station["half_height_m"] for station in stations]
    widths = [station["half_width_m"] for station in stations]
    height_axis.plot(xs, heights, color=color, linestyle=linestyle, linewidth=width, label=label)
    width_axis.plot(xs, widths, color=color, linestyle=linestyle, linewidth=width, label=label)


SMOKE_REPEAT_LABEL = "baseline_repeat"


def plot_smoke_artifacts(run_dir: Path) -> Dict[str, str]:
    """Create the P2 smoke figures from the stored evaluations and case CSV."""
    run_dir = Path(run_dir)
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    evaluations = _read_jsonl(run_dir / "evaluations.jsonl")
    cases = _read_csv_rows(run_dir / "smoke_cases.csv")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    reliability_path = figures_dir / "repeatability.png"
    perturbation_path = figures_dir / "perturbation_sensitivity.png"
    _plot_repeatability(evaluations, cases, summary, reliability_path)
    _plot_perturbations(evaluations, cases, summary, perturbation_path)
    return {
        "repeatability": str(reliability_path.relative_to(run_dir)),
        "perturbation_sensitivity": str(perturbation_path.relative_to(run_dir)),
    }


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _case_kind(case: Mapping[str, Any]) -> str:
    return str(case.get("case_kind", ""))


def _smoke_baseline_rows(
    evaluations: Sequence[Mapping[str, Any]], cases: Sequence[Mapping[str, Any]]
) -> List[Mapping[str, Any]]:
    baseline_ids = {
        str(case["design_id"]) for case in cases if _case_kind(case) == "baseline_repeat"
    }
    selected = [row for row in evaluations if str(row.get("design_id")) in baseline_ids]
    return selected or list(evaluations[:3])


def _smoke_perturbation_rows(
    evaluations: Sequence[Mapping[str, Any]], cases: Sequence[Mapping[str, Any]]
) -> List[Mapping[str, Any]]:
    labels = {
        str(case["design_id"]): str(case.get("case_label", ""))
        for case in cases
        if _case_kind(case) == "perturbation"
    }
    return [row for row in evaluations if str(row.get("design_id")) in labels]


def _constraint_names(evaluations: Sequence[Mapping[str, Any]]) -> List[str]:
    for row in evaluations:
        constraints = row.get("constraints") or {}
        if constraints:
            return list(constraints.keys())
    return []


def _plot_repeatability(
    evaluations: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    path: Path,
) -> None:
    rows = _smoke_baseline_rows(evaluations, cases)
    repeat = (summary.get("smoke") or {}).get("repeatability") or {}
    tolerance = float(repeat.get("tolerance", 1.0e-6))
    objectives = [row.get("objective") for row in rows]
    figure, axes = plt.subplots(1, 2, figsize=(14.0, 5.6))
    objective_axis, constraint_axis = axes[0], axes[1]

    valid = [float(value) for value in objectives if value is not None]
    positions = list(range(1, len(rows) + 1))
    plotted = [float(value) if value is not None else np.nan for value in objectives]
    objective_axis.bar(positions, plotted, color="#1f77b4", width=0.55, label="fuel burn per repeat")
    if valid:
        mean = sum(valid) / len(valid)
        objective_axis.axhline(mean, color="black", linewidth=1.0, label="mean")
        objective_axis.axhspan(mean * (1.0 - tolerance), mean * (1.0 + tolerance), color="grey", alpha=0.25, label="+-%.0e band" % tolerance)
        for position, value in zip(positions, objectives):
            if value is not None:
                objective_axis.text(position, float(value), "%.3f" % float(value), ha="center", va="bottom", fontsize=8)
    objective_axis.set_xticks(positions)
    objective_axis.set_xticklabels(["repeat %d" % position for position in positions])
    objective_axis.set_ylabel("fuel burn [kg]")
    objective_axis.set_title(
        "Baseline repeatability: spread %s, tolerance %.0e, passed=%s"
        % (repeat.get("relative_spread"), tolerance, repeat.get("passed"))
    )
    objective_axis.grid(True, axis="y", alpha=0.3)
    objective_axis.legend(fontsize=8)

    names = _constraint_names(rows)
    if names and rows:
        baseline_constraints = rows[0].get("constraints") or {}
        values = [float(baseline_constraints.get(name, np.nan)) for name in names]
        constraint_axis.bar(range(len(names)), values, color="#ff7f0e", width=0.6)
        constraint_axis.axhline(0.0, color="black", linewidth=1.0)
        constraint_axis.set_xticks(range(len(names)))
        constraint_axis.set_xticklabels(names, rotation=60, ha="right", fontsize=7)
        constraint_axis.set_ylabel("normalized constraint value (g <= 0)")
        constraint_axis.set_title("Baseline constraints (feasible means all <= 0)")
        constraint_axis.grid(True, axis="y", alpha=0.3)
    else:
        constraint_axis.axis("off")
    figure.suptitle("P2 single-cruise smoke: baseline repeatability (RCAIDE mission only)", fontsize=11)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(path, dpi=140)
    plt.close(figure)


def _plot_perturbations(
    evaluations: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    path: Path,
) -> None:
    rows = _smoke_perturbation_rows(evaluations, cases)
    labels = {
        str(case["design_id"]): str(case.get("case_label", ""))
        for case in cases
        if _case_kind(case) == "perturbation"
    }
    baseline_rows = _smoke_baseline_rows(evaluations, cases)
    baseline_objective = None
    for row in baseline_rows:
        if row.get("objective") is not None:
            baseline_objective = float(row["objective"])
            break
    figure, axes = plt.subplots(1, 2, figsize=(14.0, 5.6))
    objective_axis, constraint_axis = axes[0], axes[1]

    names = [labels.get(str(row.get("design_id")), "case %d" % (index + 1)) for index, row in enumerate(rows)]
    deltas: List[float] = []
    for row in rows:
        objective = row.get("objective")
        if objective is None or baseline_objective is None:
            deltas.append(np.nan)
        else:
            deltas.append(float(objective) - baseline_objective)
    positions = list(range(len(rows)))
    objective_axis.bar(positions, deltas, color="#9467bd", width=0.5)
    objective_axis.axhline(0.0, color="black", linewidth=1.0)
    for position, value in zip(positions, deltas):
        if not np.isnan(value):
            objective_axis.text(position, value, "%+.2f kg" % value, ha="center", va="bottom" if value >= 0 else "top", fontsize=8)
    objective_axis.set_xticks(positions)
    objective_axis.set_xticklabels(names, rotation=20, ha="right", fontsize=8)
    objective_axis.set_ylabel("fuel burn change versus baseline [kg]")
    objective_axis.set_title("Perturbation sensitivity: objective change (lower is better)")
    objective_axis.grid(True, axis="y", alpha=0.3)

    constraint_names = _constraint_names(rows) or _constraint_names(baseline_rows)
    if constraint_names and rows:
        width = 0.8 / (len(rows) + 1)
        for series_index, (label, row) in enumerate(
            [("baseline", baseline_rows[0] if baseline_rows else None)] + list(zip(names, rows))
        ):
            if row is None:
                continue
            constraints = row.get("constraints") or {}
            values = [float(constraints.get(name, np.nan)) for name in constraint_names]
            offset = (series_index - 0.5 * len(rows)) * width
            constraint_axis.bar(
                np.arange(len(constraint_names)) + offset,
                values,
                width=width,
                label=label,
            )
        constraint_axis.axhline(0.0, color="black", linewidth=1.0)
        constraint_axis.set_xticks(range(len(constraint_names)))
        constraint_axis.set_xticklabels(constraint_names, rotation=60, ha="right", fontsize=7)
        constraint_axis.set_ylabel("normalized constraint value (g <= 0)")
        constraint_axis.set_title("Constraint response to the same perturbations")
        constraint_axis.legend(fontsize=7)
        constraint_axis.grid(True, axis="y", alpha=0.3)
    else:
        constraint_axis.axis("off")
    figure.suptitle("P2 single-cruise smoke: single-variable perturbation effect (RCAIDE mission only)", fontsize=11)
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(path, dpi=140)
    plt.close(figure)


def plot_baseline_bo_artifacts(run_dir: Path) -> Dict[str, str]:
    """Create the P4 baseline BO figures from opt_trace.jsonl and summary.json."""
    run_dir = Path(run_dir)
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    trace = _read_jsonl(run_dir / "opt_trace.jsonl")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    best_path = run_dir / "best_design.json"
    best = json.loads(best_path.read_text(encoding="utf-8")) if best_path.exists() else {}
    convergence_path = figures_dir / "convergence.png"
    feasibility_path = figures_dir / "feasibility_rate.png"
    _plot_bo_convergence(trace, best, summary, convergence_path)
    _plot_bo_feasibility(trace, summary, feasibility_path)
    return {
        "convergence": str(convergence_path.relative_to(run_dir)),
        "feasibility_rate": str(feasibility_path.relative_to(run_dir)),
    }


def _trace_cumulative_calls(trace: Sequence[Mapping[str, Any]]) -> List[float]:
    cumulative = 0.0
    values: List[float] = []
    for row in trace:
        try:
            calls = float(row.get("analysis_calls") or 0)
        except (TypeError, ValueError):
            calls = 0.0
        cumulative += calls
        values.append(cumulative)
    return values


def _plot_bo_convergence(
    trace: Sequence[Mapping[str, Any]],
    best: Mapping[str, Any],
    summary: Mapping[str, Any],
    path: Path,
) -> None:
    cumulative = _trace_cumulative_calls(trace)
    feasible_points: List[Tuple[float, float]] = []
    for index, row in enumerate(trace):
        objective = row.get("objective")
        if row.get("feasible") and objective is not None:
            try:
                feasible_points.append((cumulative[index], float(objective)))
            except (TypeError, ValueError):
                continue
    figure, axis = plt.subplots(figsize=(9.6, 4.6))
    if feasible_points:
        xs = [point[0] for point in feasible_points]
        ys = [point[1] for point in feasible_points]
        axis.scatter(xs, ys, s=28, color="#4C72B0", alpha=0.7, label="feasible evaluation")
        best_xs: List[float] = []
        best_ys: List[float] = []
        running = None
        for x, y in feasible_points:
            running = y if running is None else min(running, y)
            best_xs.append(x)
            best_ys.append(running)
        axis.step(best_xs, best_ys, where="post", color="#C44E52", linewidth=1.8, label="best feasible so far")
        best_objective = best.get("best_feasible_objective")
        if best_objective is not None:
            axis.axhline(float(best_objective), color="#C44E52", linestyle=":", linewidth=1.0)
            axis.annotate(
                "best = %.3f kg" % float(best_objective),
                xy=(best_xs[-1], float(best_objective)),
                xytext=(-140, 14),
                textcoords="offset points",
                fontsize=8,
                color="#C44E52",
            )
    else:
        axis.text(0.5, 0.5, "no feasible design was found", transform=axis.transAxes,
                  ha="center", va="center", fontsize=11)
    baseline_objective = best.get("baseline_objective")
    if baseline_objective is not None:
        axis.axhline(float(baseline_objective), color="#555555", linestyle="--", linewidth=1.2,
                     label="baseline (seed design)")
    axis.set_xlabel("cumulative true mission evaluations")
    axis.set_ylabel("single-cruise fuel burn (kg)")
    axis.set_title("P4 ordinary constrained BO convergence (%s)" % summary.get("run_id"))
    axis.grid(True, alpha=0.3)
    axis.legend(fontsize=8, loc="best")
    figure.tight_layout()
    figure.savefig(path, dpi=140)
    plt.close(figure)


def _plot_bo_feasibility(
    trace: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    path: Path,
) -> None:
    figure, (rate_axis, status_axis) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    feasible_flags = [1.0 if row.get("feasible") else 0.0 for row in trace]
    iterations = list(range(1, len(trace) + 1))
    if feasible_flags:
        cumulative = np.cumsum(feasible_flags)
        running_rate = cumulative / np.asarray(iterations, dtype=float)
        rate_axis.plot(iterations, running_rate, color="#55A868", linewidth=1.6,
                       label="cumulative feasible rate")
        overall = float(cumulative[-1]) / float(len(trace))
        rate_axis.axhline(overall, color="#555555", linestyle="--", linewidth=1.0,
                          label="overall %.3f" % overall)
        rate_axis.set_ylim(-0.02, 1.02)
    rate_axis.set_xlabel("evaluation index")
    rate_axis.set_ylabel("feasible fraction")
    rate_axis.set_title("Feasibility discovery")
    rate_axis.grid(True, alpha=0.3)
    rate_axis.legend(fontsize=8, loc="best")

    categories = {
        "feasible": 0,
        "valid infeasible": 0,
        "geometry invalid": 0,
        "failed": 0,
    }
    for row in trace:
        status = str(row.get("status", ""))
        if row.get("feasible"):
            categories["feasible"] += 1
        elif status == "VALID":
            categories["valid infeasible"] += 1
        elif status.startswith("GEOMETRY"):
            categories["geometry invalid"] += 1
        else:
            categories["failed"] += 1
    labels = list(categories)
    values = [categories[label] for label in labels]
    colors = ["#55A868", "#C44E52", "#8172B2", "#937860"]
    bars = status_axis.bar(labels, values, color=colors)
    for bar, value in zip(bars, values):
        status_axis.text(bar.get_x() + bar.get_width() / 2.0, bar.get_height(),
                         str(value), ha="center", va="bottom", fontsize=9)
    status_axis.set_ylabel("evaluations")
    status_axis.set_title("Evaluation outcomes (%d total)" % len(trace))
    status_axis.tick_params(axis="x", rotation=15)
    status_axis.grid(True, axis="y", alpha=0.3)

    figure.suptitle("P4 ordinary constrained BO: feasibility diagnostics (%s, %s evaluations)"
                    % (summary.get("run_id"), summary.get("total_true_evaluations")), fontsize=10)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(path, dpi=140)
    plt.close(figure)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Redraw P1/P2 figures from stored run artifacts.")
    parser.add_argument("run_dir", help="path to the optimization_runs/<run_id> directory")
    arguments = parser.parse_args(argv)
    run_dir = Path(arguments.run_dir)
    paths: Dict[str, str] = {}
    if (run_dir / "geometry_effect_delta.csv").exists() and (run_dir / "geometry_planforms.json").exists():
        paths.update(plot_geometry_artifacts(run_dir))
    if (run_dir / "smoke_cases.csv").exists() and (run_dir / "evaluations.jsonl").exists():
        paths.update(plot_smoke_artifacts(run_dir))
    if (run_dir / "opt_trace.jsonl").exists() and (run_dir / "summary.json").exists():
        paths.update(plot_baseline_bo_artifacts(run_dir))
    if not paths:
        parser.error("no drawable artifacts found in %s" % run_dir)
    for name, path in paths.items():
        print("%s: %s" % (name, path))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
