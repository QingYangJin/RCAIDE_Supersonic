"""P1 geometry checks, effect matrix and run artifacts.

The checks are split into three groups:

* model checks: internal consistency of the dependency-free geometry model
  (area closure, breakpoint ordering, positive chords, fuselage volume, mass/CG
  sanity, design-space bounds and cross constraints);
* RCAIDE checks: the same geometry rebuilt as RCAIDE components and re-derived
  with RCAIDE's own wing_planform / segment_properties / fuselage_planform;
* source checks: documented deviations from the upstream Concorde.py declared
  values (root chord, wetted areas, tail span, ...), reported as warnings so a
  later reader sees exactly which upstream numbers are not reproducible.

A failed model or RCAIDE check marks the case invalid; it never invents an
objective value.  The effect matrix perturbs every one of the 15 variables by
10 percent of its current bound span (clamped to the bounds) and records the
resulting change of every derived quantity, so "the variable moved a YAML field
but the geometry did not change" is detectable.
"""

from __future__ import annotations

import csv
import json
import math
import platform
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .design_space import DesignSpace, load_design_space
from .geometry_model import (
    GEOMETRY_MODEL_VERSION,
    SOURCE_BASELINE,
    TAIL_ORIGIN_X_M,
    WING_ORIGIN_X_M,
    ConcordeGeometry,
    GeometryError,
    build_geometry,
)
from .geometry_builder import (
    GeometryBuilderError,
    build_geometry_vehicle,
    rcaide_derived_geometry,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"
DEFAULT_DELTA_FRACTION = 0.10
PASS = "pass"
FAIL = "fail"
WARN = "warn"
INFO = "info"
SKIP = "skip"


@dataclass
class CheckResult:
    check_id: str
    category: str
    subject: str
    status: str
    detail: str = ""
    model_value: Any = None
    reference_value: Any = None
    tolerance: Any = None
    delta: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "subject": self.subject,
            "status": self.status,
            "detail": self.detail,
            "model_value": self.model_value,
            "reference_value": self.reference_value,
            "tolerance": self.tolerance,
            "delta": self.delta,
        }


def model_checks(
    geometry: ConcordeGeometry,
    design_space: DesignSpace,
    include_source_checks: bool = False,
) -> List[CheckResult]:
    requested = dict(zip(geometry.names, geometry.vector))
    wing = geometry.wing
    tail = geometry.vertical_tail
    fuselage = geometry.fuselage
    checks: List[CheckResult] = []

    checks.append(
        _compare(
            "G01_wing_area_closure",
            "model",
            "main_wing.area_m2",
            wing.area_m2,
            requested["wing_area"],
            1e-9,
            "sum of the four trapezoid sections equals the requested wing area",
        )
    )
    checks.append(
        _compare(
            "G02_wing_span_derivation",
            "model",
            "main_wing.span_m",
            wing.span_m,
            math.sqrt(requested["wing_area"] * requested["aspect_ratio"]),
            1e-9,
            "span = sqrt(wing_area * aspect_ratio)",
        )
    )
    checks.append(
        _compare(
            "G03_wing_aspect_ratio_closure",
            "model",
            "main_wing.aspect_ratio",
            wing.area_m2,
            wing.span_m * wing.span_m / requested["aspect_ratio"],
            1e-9,
            "area = span^2 / aspect_ratio",
        )
    )
    checks.append(
        _boolean(
            "G04_wing_root_chord_positive",
            "model",
            "main_wing.root_chord_m",
            wing.root_chord_m > 0.0,
            "root chord %.6f m" % wing.root_chord_m,
        )
    )
    checks.append(
        _boolean(
            "G05_wing_section_span_order",
            "model",
            "main_wing.sections.percent_span_location",
            _strictly_increasing([section.percent_span_location for section in wing.sections])
            and wing.sections[0].percent_span_location == 0.0
            and wing.sections[-1].percent_span_location == 1.0,
            "span fractions %s" % _fmt_list([section.percent_span_location for section in wing.sections]),
        )
    )
    chords = [section.chord_m for section in wing.sections]
    checks.append(
        _boolean(
            "G06_wing_chord_positive_monotonic",
            "model",
            "main_wing.sections.chord_m",
            all(chord > 0.0 for chord in chords) and _strictly_decreasing(chords),
            "chords %s" % _fmt_list(chords),
        )
    )
    sweeps = [section.quarter_chord_sweep_deg for section in wing.sections]
    checks.append(
        _boolean(
            "G07_wing_sweep_range",
            "model",
            "main_wing.sections.quarter_chord_sweep_deg",
            all(0.0 <= sweep <= 90.0 for sweep in sweeps),
            "sweeps %s" % _fmt_list(sweeps),
        )
    )
    tip_twist_variable = design_space.variable("tip_twist")
    checks.append(
        _boolean(
            "G08_wing_tip_twist_in_bounds",
            "model",
            "main_wing.sections.tip.twist_deg",
            tip_twist_variable.contains(wing.sections[-1].twist_deg),
            "tip twist %.6f deg" % wing.sections[-1].twist_deg,
        )
    )
    checks.append(
        _boolean(
            "G09_wing_wetted_area_positive",
            "model",
            "main_wing.wetted_area_m2",
            wing.wetted_area_m2 > wing.area_m2,
            "wetted %.3f m2 vs reference %.3f m2" % (wing.wetted_area_m2, wing.area_m2),
        )
    )
    exposed_ok = wing.exposed_area_m2 <= wing.area_m2 + 1e-9
    checks.append(
        _boolean(
            "G10_wing_exposed_le_reference",
            "model",
            "main_wing.exposed_area_m2",
            exposed_ok,
            "exposed %.3f m2 <= reference %.3f m2; wing-fuselage unexposed span is not modelled in P1"
            % (wing.exposed_area_m2, wing.area_m2),
            status_if_false=WARN,
        )
    )
    checks.append(
        _compare(
            "G11_tail_area_closure",
            "model",
            "vertical_stabilizer.area_m2",
            tail.area_m2,
            requested["vertical_tail_area"],
            1e-9,
            "tail planform area equals the requested vertical_tail_area",
        )
    )
    checks.append(
        _compare(
            "G12_tail_span_derivation",
            "model",
            "vertical_stabilizer.span_m",
            tail.span_m,
            math.sqrt(requested["vertical_tail_area"] * SOURCE_BASELINE["tail_aspect_ratio"]),
            1e-9,
            "tail span = sqrt(vertical_tail_area * 0.74)",
        )
    )
    tail_spans = [section.percent_span_location for section in tail.sections]
    tail_chords = [section.chord_m for section in tail.sections]
    checks.append(
        _boolean(
            "G13_tail_sections_positive_monotonic",
            "model",
            "vertical_stabilizer.sections",
            _strictly_increasing(tail_spans)
            and all(chord > 0.0 for chord in tail_chords)
            and _strictly_decreasing(tail_chords),
            "span fractions %s chords %s" % (_fmt_list(tail_spans), _fmt_list(tail_chords)),
        )
    )
    tail_sweeps = [section.quarter_chord_sweep_deg for section in tail.sections]
    checks.append(
        _boolean(
            "G14_tail_sweep_range",
            "model",
            "vertical_stabilizer.sections.quarter_chord_sweep_deg",
            all(0.0 <= sweep <= 90.0 for sweep in tail_sweeps),
            "sweeps %s" % _fmt_list(tail_sweeps),
        )
    )
    checks.append(
        _boolean(
            "G15_fuselage_cabin_positive",
            "model",
            "fuselage.cabin_length_m",
            fuselage.cabin_length_m > 0.0,
            "cabin %.6f m = total %.3f - nose %.3f - tail %.3f"
            % (
                fuselage.cabin_length_m,
                fuselage.length_m,
                fuselage.nose_length_m,
                fuselage.tail_length_m,
            ),
        )
    )
    stations = list(fuselage.stations)
    station_x = [station.x_m for station in stations]
    checks.append(
        _boolean(
            "G16_fuselage_station_order",
            "model",
            "fuselage.stations.x_m",
            _strictly_increasing(station_x)
            and station_x[0] >= 0.0
            and station_x[-1] <= fuselage.length_m + 1e-9,
            "x stations %s" % _fmt_list(station_x),
        )
    )
    tags = [station.tag for station in stations]
    checks.append(
        _boolean(
            "G17_fuselage_station_tags_unique",
            "model",
            "fuselage.stations.tag",
            len(set(tags)) == len(tags),
            "tags %s" % ", ".join(tags),
        )
    )
    volume_margin = fuselage.usable_volume_m3 - fuselage.required_volume_m3
    checks.append(
        _boolean(
            "G18_fuselage_volume_requirement",
            "constraint",
            "fuselage.usable_volume_m3",
            volume_margin >= 0.0,
            "usable %.3f m3, required %.3f m3, margin %.3f m3"
            % (fuselage.usable_volume_m3, fuselage.required_volume_m3, volume_margin),
            reference_value=fuselage.required_volume_m3,
            model_value=fuselage.usable_volume_m3,
        )
    )
    checks.append(
        _boolean(
            "G19_fuselage_wetted_front_positive",
            "model",
            "fuselage.wetted_area_m2",
            fuselage.wetted_area_m2 > 0.0 and fuselage.front_projected_area_m2 > 0.0,
            "wetted %.3f m2, front projected %.3f m2"
            % (fuselage.wetted_area_m2, fuselage.front_projected_area_m2),
        )
    )
    mass_values = [value for value in geometry.mass_kg.values() if math.isfinite(value)]
    checks.append(
        _boolean(
            "G20_mass_positive_finite",
            "model",
            "mass_kg",
            len(mass_values) == len(geometry.mass_kg) and all(value > 0.0 for value in mass_values),
            "operating empty %.1f kg, total takeoff %.1f kg"
            % (geometry.mass_kg["operating_empty"], geometry.mass_kg["total_takeoff"]),
        )
    )
    checks.append(
        _boolean(
            "G21_cg_inside_fuselage",
            "model",
            "cg_x_m",
            0.0 <= geometry.cg_x_m <= fuselage.length_m,
            "cg %.3f m, fuselage length %.3f m" % (geometry.cg_x_m, fuselage.length_m),
        )
    )
    checks.append(
        _boolean(
            "G22_static_margin_finite",
            "model",
            "static_margin",
            math.isfinite(geometry.static_margin),
            "static margin %.4f (provisional; excludes tail lift)" % geometry.static_margin,
            status_if_false=FAIL,
        )
    )
    physical = {name: value for name, value in zip(geometry.names, geometry.vector)}
    violations = design_space.check_physical(physical)
    checks.append(
        _boolean(
            "G23_design_space_bounds",
            "constraint",
            "design vector",
            not violations,
            "; ".join(violations) if violations else "within bounds and cross constraints",
        )
    )
    if include_source_checks:
        checks.extend(_source_checks(wing, tail, fuselage))
    return checks


def rcaide_checks(
    geometry: ConcordeGeometry,
    airfoil_dir: Optional[Path] = None,
) -> Tuple[List[CheckResult], Dict[str, Any]]:
    """Rebuild the geometry with RCAIDE and compare derived values."""
    try:
        vehicle = build_geometry_vehicle(geometry, airfoil_dir)
        derived = rcaide_derived_geometry(vehicle)
    except Exception as exc:  # pragma: no cover - depends on the local RCAIDE install
        return [
            CheckResult(
                "R00_rcaide_available",
                "rcaide",
                "RCAIDE geometry adapter",
                SKIP,
                "%s: %s" % (type(exc).__name__, exc),
            )
        ], {}
    rc_wing = derived["main_wing"]
    rc_tail = derived["vertical_stabilizer"]
    rc_fus = derived["fuselage"]
    wing = geometry.wing
    tail = geometry.vertical_tail
    fuselage = geometry.fuselage
    checks: List[CheckResult] = [
        _boolean("R00_rcaide_available", "rcaide", "RCAIDE geometry adapter", True, "vehicle rebuilt")
    ]
    checks.append(
        _compare("R01_wing_area_match", "rcaide", "wing.area_m2", wing.area_m2, rc_wing["area_m2"], 1e-9)
    )
    checks.append(
        _compare("R02_wing_span_match", "rcaide", "wing.span_m", wing.span_m, rc_wing["span_m"], 1e-12)
    )
    checks.append(
        _compare(
            "R03_wing_root_chord_match",
            "rcaide",
            "wing.root_chord_m",
            wing.root_chord_m,
            rc_wing["root_chord_m"],
            1e-12,
        )
    )
    checks.append(
        _compare(
            "R04_wing_mac_match",
            "rcaide",
            "wing.mean_aerodynamic_chord_m",
            wing.mean_aerodynamic_chord_m,
            rc_wing["mean_aerodynamic_chord_m"],
            1e-6,
        )
    )
    checks.append(
        _compare(
            "R05_wing_wetted_match",
            "rcaide",
            "wing.wetted_area_m2",
            wing.wetted_area_m2,
            rc_wing["wetted_area_m2"],
            1e-4,
        )
    )
    checks.append(
        _compare(
            "R06_wing_exposed_match",
            "rcaide",
            "wing.exposed_area_m2",
            wing.exposed_area_m2,
            rc_wing["exposed_area_m2"],
            1e-4,
        )
    )
    checks.append(
        _abs_compare(
            "R07_wing_ac_match",
            "rcaide",
            "wing.aerodynamic_center_x_m",
            wing.aerodynamic_center_x_m,
            rc_wing["aerodynamic_center_local_x_m"],
            0.25,
            "model AC = LE(MAC) + 0.25 MAC, RCAIDE AC = area centroid - 0.25 MAC; both are "
            "equivalent for a single trapezoid but differ slightly for a multi-section planform, "
            "so a small difference is a diagnostic note, not a geometry error",
            status_if_false=WARN,
        )
    )
    le_mac_model = wing.aerodynamic_center_x_m - 0.25 * wing.mean_aerodynamic_chord_m
    le_mac_rcaide = rc_wing["leading_edge_mac_x_m"] - WING_ORIGIN_X_M
    checks.append(
        _abs_compare(
            "R08_wing_le_mac_match",
            "rcaide",
            "wing.leading_edge_mac_x_m",
            le_mac_model,
            le_mac_rcaide,
            0.01,
            "model LE(MAC) vs RCAIDE LEMAC minus wing origin",
        )
    )
    checks.append(
        _compare("R09_tail_area_match", "rcaide", "tail.area_m2", tail.area_m2, rc_tail["area_m2"], 1e-9)
    )
    checks.append(
        _compare("R10_tail_span_match", "rcaide", "tail.span_m", tail.span_m, rc_tail["span_m"], 1e-12)
    )
    checks.append(
        _compare(
            "R11_tail_mac_match",
            "rcaide",
            "tail.mean_aerodynamic_chord_m",
            tail.mean_aerodynamic_chord_m,
            rc_tail["mean_aerodynamic_chord_m"],
            1e-6,
        )
    )
    checks.append(
        _compare(
            "R12_fuselage_wetted_match",
            "rcaide",
            "fuselage.wetted_area_m2",
            fuselage.wetted_area_m2,
            rc_fus["wetted_area_m2"],
            1e-9,
        )
    )
    checks.append(
        _compare(
            "R13_fuselage_front_projected_match",
            "rcaide",
            "fuselage.front_projected_area_m2",
            fuselage.front_projected_area_m2,
            rc_fus["front_projected_area_m2"],
            1e-9,
        )
    )
    checks.append(
        _compare(
            "R14_fuselage_effective_diameter_match",
            "rcaide",
            "fuselage.effective_diameter_m",
            fuselage.effective_diameter_m,
            rc_fus["effective_diameter_m"],
            1e-9,
        )
    )
    checks.append(
        _compare(
            "R15_fuselage_lengths_match",
            "rcaide",
            "fuselage.lengths.total_m",
            fuselage.length_m,
            rc_fus["length_m"],
            1e-12,
        )
    )
    sweep_checks = _sweep_comparison(wing.sections, rc_wing["section_quarter_chord_sweeps_deg"])
    checks.extend(sweep_checks[0])
    tip_check = sweep_checks[1]
    checks.append(tip_check)
    declared_tc = wing.thickness_to_chord
    imported_tc = rc_wing["section_thickness_to_chord"][0] if rc_wing["section_thickness_to_chord"] else float("nan")
    checks.append(
        _abs_compare(
            "R17_airfoil_thickness_declared_vs_imported",
            "rcaide",
            "wing.section.thickness_to_chord",
            declared_tc,
            imported_tc,
            0.002,
            "RCAIDE replaces the declared t/c with the value read from the airfoil file; difference is reported",
            status_if_false=WARN,
        )
    )
    checks.append(
        _compare(
            "R18_wing_taper_match", "rcaide", "wing.taper_ratio", wing.taper_ratio, rc_wing["taper_ratio"], 1e-9
        )
    )
    return checks, derived


def _sweep_comparison(
    sections: Sequence[Any], rcaide_sweeps: Sequence[float]
) -> Tuple[List[CheckResult], CheckResult]:
    checks = []
    count = min(len(sections), len(rcaide_sweeps))
    for index in range(max(0, count - 1)):
        checks.append(
            _compare(
                "R16_%02d_section_sweep_match" % (index + 1),
                "rcaide",
                "wing.sections[%d].quarter_chord_sweep_deg" % index,
                sections[index].quarter_chord_sweep_deg,
                rcaide_sweeps[index],
                1e-9,
            )
        )
    tip_model = sections[-1].quarter_chord_sweep_deg
    tip_rcaide = rcaide_sweeps[-1]
    detail = (
        "RCAIDE wing_planform forces the last segment sweep to the previous segment "
        "(model tip %.3f deg, RCAIDE tip %.3f deg); this is an RCAIDE convention, not a model error"
        % (tip_model, tip_rcaide)
    )
    tip_check = CheckResult(
        "R16_tip_sweep_rcaide_convention",
        "rcaide",
        "wing.sections.tip.quarter_chord_sweep_deg",
        INFO,
        detail,
        model_value=tip_model,
        reference_value=tip_rcaide,
    )
    return checks, tip_check


def _source_checks(wing: Any, tail: Any, fuselage: Any) -> List[CheckResult]:
    pairs = (
        ("source_wing_root_chord", "wing.root_chord_m", wing.root_chord_m, SOURCE_BASELINE["wing_root_chord_m"]),
        ("source_wing_span", "wing.span_m", wing.span_m, SOURCE_BASELINE["wing_span_m"]),
        ("source_wing_wetted", "wing.wetted_area_m2", wing.wetted_area_m2, SOURCE_BASELINE["wing_wetted_area_m2"]),
        ("source_wing_exposed", "wing.exposed_area_m2", wing.exposed_area_m2, SOURCE_BASELINE["wing_exposed_area_m2"]),
        ("source_tail_span", "tail.span_m", tail.span_m, SOURCE_BASELINE["tail_span_m"]),
        ("source_tail_root_chord", "tail.root_chord_m", tail.root_chord_m, SOURCE_BASELINE["tail_root_chord_m"]),
        ("source_fuselage_wetted", "fuselage.wetted_area_m2", fuselage.wetted_area_m2, SOURCE_BASELINE["fuselage_wetted_area_m2"]),
        (
            "source_fuselage_front_projected",
            "fuselage.front_projected_area_m2",
            fuselage.front_projected_area_m2,
            SOURCE_BASELINE["fuselage_front_projected_m2"],
        ),
    )
    checks = []
    for check_id, subject, model_value, source_value in pairs:
        relative = (model_value - source_value) / source_value if source_value else 0.0
        status = WARN if abs(relative) > 0.05 else INFO
        checks.append(
            CheckResult(
                check_id,
                "source",
                subject,
                status,
                "upstream Concorde.py declares %.6f, the P1 geometry model derives %.6f (%.2f%%)"
                % (source_value, model_value, 100.0 * relative),
                model_value=model_value,
                reference_value=source_value,
                delta=model_value - source_value,
            )
        )
    return checks


def metrics(geometry: ConcordeGeometry) -> Dict[str, Any]:
    wing = geometry.wing
    tail = geometry.vertical_tail
    fuselage = geometry.fuselage
    return {
        "wing_area_m2": wing.area_m2,
        "wing_span_m": wing.span_m,
        "wing_aspect_ratio": wing.aspect_ratio,
        "wing_root_chord_m": wing.root_chord_m,
        "wing_tip_chord_m": wing.tip_chord_m,
        "wing_mac_m": wing.mean_aerodynamic_chord_m,
        "wing_wetted_area_m2": wing.wetted_area_m2,
        "wing_exposed_area_m2": wing.exposed_area_m2,
        "wing_total_length_m": wing.total_length_m,
        "wing_ac_x_m": wing.aerodynamic_center_x_m,
        "wing_span_location_2": wing.sections[1].percent_span_location,
        "wing_span_location_3": wing.sections[2].percent_span_location,
        "wing_chord_ratio_2": wing.sections[1].chord_m / wing.root_chord_m,
        "wing_chord_ratio_3": wing.sections[2].chord_m / wing.root_chord_m,
        "wing_tip_twist_deg": wing.sections[-1].twist_deg,
        "wing_sweep_1_deg": wing.sections[0].quarter_chord_sweep_deg,
        "wing_sweep_2_deg": wing.sections[1].quarter_chord_sweep_deg,
        "wing_sweep_3_deg": wing.sections[2].quarter_chord_sweep_deg,
        "tail_area_m2": tail.area_m2,
        "tail_span_m": tail.span_m,
        "tail_root_chord_m": tail.root_chord_m,
        "tail_mac_m": tail.mean_aerodynamic_chord_m,
        "tail_wetted_area_m2": tail.wetted_area_m2,
        "tail_ac_x_m": tail.aerodynamic_center_x_m,
        "tail_total_length_m": tail.total_length_m,
        "tail_sweep_1_deg": tail.sections[0].quarter_chord_sweep_deg,
        "tail_sweep_2_deg": tail.sections[1].quarter_chord_sweep_deg,
        "tail_sweep_3_deg": tail.sections[2].quarter_chord_sweep_deg,
        "fuselage_length_m": fuselage.length_m,
        "fuselage_nose_length_m": fuselage.nose_length_m,
        "fuselage_tail_length_m": fuselage.tail_length_m,
        "fuselage_cabin_length_m": fuselage.cabin_length_m,
        "fuselage_wetted_area_m2": fuselage.wetted_area_m2,
        "fuselage_front_projected_m2": fuselage.front_projected_area_m2,
        "fuselage_effective_diameter_m": fuselage.effective_diameter_m,
        "fuselage_usable_volume_m3": fuselage.usable_volume_m3,
        "fuselage_required_volume_m3": fuselage.required_volume_m3,
        "fuselage_volume_margin_m3": fuselage.usable_volume_m3 - fuselage.required_volume_m3,
        "cg_x_m": geometry.cg_x_m,
        "static_margin": geometry.static_margin,
        "mass_operating_empty_kg": geometry.mass_kg["operating_empty"],
        "mass_total_takeoff_kg": geometry.mass_kg["total_takeoff"],
    }


def planform_geometry(geometry: ConcordeGeometry) -> Dict[str, Any]:
    wing_points = []
    for section in geometry.wing.sections:
        wing_points.append(
            {
                "span_fraction": section.percent_span_location,
                "leading_edge_x_m": section.leading_edge_x_m,
                "trailing_edge_x_m": section.leading_edge_x_m + section.chord_m,
            }
        )
    tail_points = []
    for section in geometry.vertical_tail.sections:
        tail_points.append(
            {
                "span_fraction": section.percent_span_location,
                "leading_edge_x_m": section.leading_edge_x_m,
                "trailing_edge_x_m": section.leading_edge_x_m + section.chord_m,
            }
        )
    fuselage_profile = [
        {"x_m": station.x_m, "half_height_m": 0.5 * station.height_m, "half_width_m": 0.5 * station.width_m}
        for station in geometry.fuselage.stations
    ]
    return {
        "wing": wing_points,
        "vertical_tail": tail_points,
        "fuselage": fuselage_profile,
        "wing_origin_x_m": WING_ORIGIN_X_M,
        "tail_origin_x_m": TAIL_ORIGIN_X_M,
        "wing_span_m": geometry.wing.span_m,
        "tail_span_m": geometry.vertical_tail.span_m,
        "fuselage_length_m": geometry.fuselage.length_m,
    }


def run_case(
    design_space: DesignSpace,
    physical: Mapping[str, float],
    case_id: str,
    use_rcaide: bool,
    include_source_checks: bool = False,
    is_baseline: bool = False,
) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        geometry = build_geometry(design_space.names, [physical[name] for name in design_space.names])
    except GeometryError as exc:
        return {
            "case_id": case_id,
            "is_baseline": is_baseline,
            "status": "invalid",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "checks": [],
            "metrics": {},
            "rcaide_metrics": {},
            "wall_seconds": time.perf_counter() - started,
        }
    checks = model_checks(geometry, design_space, include_source_checks=include_source_checks)
    rcaide_metrics: Dict[str, Any] = {}
    if use_rcaide:
        rc_checks, derived = rcaide_checks(geometry)
        checks.extend(rc_checks)
        if derived:
            rcaide_metrics = {
                "wing_area_m2": derived["main_wing"]["area_m2"],
                "wing_span_m": derived["main_wing"]["span_m"],
                "wing_root_chord_m": derived["main_wing"]["root_chord_m"],
                "wing_mac_m": derived["main_wing"]["mean_aerodynamic_chord_m"],
                "wing_wetted_area_m2": derived["main_wing"]["wetted_area_m2"],
                "wing_exposed_area_m2": derived["main_wing"]["exposed_area_m2"],
                "wing_ac_x_m": derived["main_wing"]["aerodynamic_center_local_x_m"],
                "tail_area_m2": derived["vertical_stabilizer"]["area_m2"],
                "tail_span_m": derived["vertical_stabilizer"]["span_m"],
                "tail_mac_m": derived["vertical_stabilizer"]["mean_aerodynamic_chord_m"],
                "fuselage_wetted_area_m2": derived["fuselage"]["wetted_area_m2"],
                "fuselage_front_projected_m2": derived["fuselage"]["front_projected_area_m2"],
                "fuselage_effective_diameter_m": derived["fuselage"]["effective_diameter_m"],
            }
    failed = [check for check in checks if check.status == FAIL]
    warned = [check for check in checks if check.status == WARN]
    status = "invalid" if failed else "ok"
    return {
        "case_id": case_id,
        "is_baseline": is_baseline,
        "status": status,
        "error": None,
        "checks": checks,
        "failed_checks": [check.check_id for check in failed],
        "warned_checks": [check.check_id for check in warned],
        "metrics": metrics(geometry),
        "rcaide_metrics": rcaide_metrics,
        "planform": planform_geometry(geometry),
        "physical": {name: physical[name] for name in design_space.names},
        "wall_seconds": time.perf_counter() - started,
    }


def effect_cases(
    design_space: DesignSpace,
    delta_fraction: float = DEFAULT_DELTA_FRACTION,
) -> List[Dict[str, Any]]:
    baseline = design_space.baseline_dict()
    cases = [
        {
            "case_id": "baseline",
            "variable_id": None,
            "variable_name": None,
            "direction": 0,
            "delta": 0.0,
            "physical": dict(baseline),
            "is_baseline": True,
        }
    ]
    for variable in design_space.variables:
        magnitude = delta_fraction * (variable.upper - variable.lower)
        for direction in (1.0, -1.0):
            value = variable.baseline + direction * magnitude
            value = min(variable.upper, max(variable.lower, value))
            actual_delta = value - variable.baseline
            if actual_delta == 0.0:
                continue
            physical = dict(baseline)
            physical[variable.name] = value
            cases.append(
                {
                    "case_id": "%s_%s" % (variable.id, "plus" if direction > 0 else "minus"),
                    "variable_id": variable.id,
                    "variable_name": variable.name,
                    "direction": int(direction),
                    "delta": actual_delta,
                    "physical": physical,
                    "is_baseline": False,
                }
            )
    return cases


def run_geometry_check(
    output_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    design_space: Optional[DesignSpace] = None,
    use_rcaide: bool = True,
    delta_fraction: float = DEFAULT_DELTA_FRACTION,
    allow_existing: bool = False,
) -> Dict[str, Any]:
    space = design_space if design_space is not None else load_design_space()
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    identifier = run_id or "geometry-check-%s" % datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / identifier
    if run_dir.exists() and not allow_existing:
        raise FileExistsError("run directory already exists: %s" % run_dir)
    (run_dir / "figures").mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    baseline_id = "baseline"
    case_specs = effect_cases(space, delta_fraction)
    case_records: List[Dict[str, Any]] = []
    for index, spec in enumerate(case_specs):
        record = run_case(
            space,
            spec["physical"],
            spec["case_id"],
            use_rcaide=use_rcaide,
            include_source_checks=spec["case_id"] == baseline_id,
            is_baseline=spec["is_baseline"],
        )
        record.update(
            {
                "iteration": index,
                "variable_id": spec["variable_id"],
                "variable_name": spec["variable_name"],
                "direction": spec["direction"],
                "requested_delta": spec["delta"],
                "is_baseline": spec["is_baseline"],
            }
        )
        case_records.append(record)
    baseline = next(record for record in case_records if record["is_baseline"])
    baseline_metrics = baseline["metrics"]
    check_rows = _check_rows(case_records)
    effect_rows = _effect_matrix_rows(case_records, baseline_metrics)
    delta_rows = _effect_delta_rows(case_records, baseline_metrics)
    _write_csv(run_dir / "checks.csv", check_rows)
    _write_csv(run_dir / "geometry_effect_matrix.csv", effect_rows)
    _write_csv(run_dir / "geometry_effect_delta.csv", delta_rows)
    _write_json(run_dir / "baseline_geometry.json", baseline["metrics"], pretty=True)
    _write_json(run_dir / "geometry_planforms.json", {record["case_id"]: record["planform"] for record in case_records}, pretty=False)
    _write_jsonl(run_dir / "geometry_cases.jsonl", [_case_line(record) for record in case_records])
    rcaide_available = bool(baseline.get("rcaide_metrics"))
    failed_cases = [record["case_id"] for record in case_records if record["status"] == "invalid"]
    failed_checks = [
        "%s:%s" % (check.check_id, check.subject)
        for record in case_records
        for check in record["checks"]
        if check.status == FAIL
    ]
    summary = {
        "run_id": identifier,
        "stage": "P1",
        "task_id": space.task_id,
        "method": "geometry_check",
        "seed": None,
        "git_sha": _git_sha(REPO_ROOT),
        "solver_versions": _software_versions(),
        "design_dim": len(space.variables),
        "status": "geometry_check_completed" if not failed_cases else "geometry_check_invalid_cases",
        "total_true_evaluations": 0,
        "low_fidelity_calls": 0,
        "su2_calls": 0,
        "invalid_count": len(failed_cases),
        "failed_count": 0,
        "first_feasible_evaluation": None,
        "best_feasible_fuel_kg": None,
        "best_design_id": None,
        "wall_seconds": time.perf_counter() - started,
        "cpu_seconds_if_available": None,
        "artifacts": {
            "summary": "summary.json",
            "run_config": "run_config.json",
            "environment": "environment.json",
            "baseline_geometry": "baseline_geometry.json",
            "checks_csv": "checks.csv",
            "geometry_cases": "geometry_cases.jsonl",
            "geometry_effect_matrix_csv": "geometry_effect_matrix.csv",
            "geometry_effect_delta_csv": "geometry_effect_delta.csv",
            "geometry_planforms": "geometry_planforms.json",
            "figures": ["figures/geometry_effect_heatmap.png", "figures/wing_planform_comparison.png"],
        },
        "geometry": {
            "geometry_model_version": GEOMETRY_MODEL_VERSION,
            "bounds_status": space.bounds_status,
            "frozen": space.frozen,
            "cases": len(case_records),
            "baseline_case": baseline_id,
            "baseline_status": baseline["status"],
            "failed_cases": failed_cases,
            "failed_checks": failed_checks,
            "rcaide_cross_checks": rcaide_available,
            "delta_fraction": delta_fraction,
            "note": "These are geometry checks, not Mission or CFD evaluations; no objective value is reported.",
        },
        "design_space_config": _display_path(space.config_path),
    }
    run_config = {
        "run_id": identifier,
        "stage": "P1",
        "method": "geometry_check",
        "design_space_config": _display_path(space.config_path),
        "design_space_summary": dict(
            space.config_summary(), config_path=_display_path(space.config_path)
        ),
        "delta_fraction": delta_fraction,
        "use_rcaide": use_rcaide,
        "cases": [case["case_id"] for case in case_specs],
        "seed": None,
        "command": "python -m research.concorde_metaopt.cli geometry-check --run-id %s%s"
        % (identifier, "" if use_rcaide else " --no-rcaide"),
    }
    _write_json(run_dir / "run_config.json", run_config, pretty=True)
    _write_json(run_dir / "environment.json", _environment(), pretty=True)
    from ..reports.figures import plot_geometry_artifacts

    plot_geometry_artifacts(run_dir)
    _write_json(run_dir / "summary.json", summary, pretty=True)
    (run_dir / "README.md").write_text(_run_readme(summary), encoding="utf-8")
    return summary


def _run_readme(summary: Mapping[str, Any]) -> str:
    geometry = summary["geometry"]
    lines = [
        "# P1 geometry-check run %s" % summary["run_id"],
        "",
        "This run checks the provisional 15-variable geometry model and the RCAIDE",
        "vehicle adapter. It is **not** a Mission or CFD evaluation and reports no",
        "objective value.",
        "",
        "- stage: %s" % summary["stage"],
        "- status: %s" % summary["status"],
        "- git_sha: %s" % summary["git_sha"],
        "- design_dim: %s" % summary["design_dim"],
        "- cases: %s (baseline + 15 variables x 2 directions)" % geometry["cases"],
        "- delta: %s of each variable bound span" % geometry["delta_fraction"],
        "- invalid cases: %s" % (", ".join(geometry["failed_cases"]) or "none"),
        "- RCAIDE cross-checks: %s" % geometry["rcaide_cross_checks"],
        "- true evaluations: %s" % summary["total_true_evaluations"],
        "- wall_seconds: %.3f" % summary["wall_seconds"],
        "",
        "Artefacts: summary.json, run_config.json, environment.json,",
        "baseline_geometry.json, checks.csv, geometry_cases.jsonl,",
        "geometry_effect_matrix.csv, geometry_effect_delta.csv,",
        "geometry_planforms.json and figures/.",
        "",
        "Known unresolved upstream-declaration deviations are reported as WARN rows in",
        "checks.csv (source_* checks); they are not repaired or hidden. Mass and CG are",
        "PROVISIONAL_NOT_FROZEN and must not be used as frozen constraints before P2.",
        "",
    ]
    return "\n".join(lines)


def _check_rows(case_records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for record in case_records:
        for check in record["checks"]:
            rows.append(
                {
                    "case_id": record["case_id"],
                    "check_id": check.check_id,
                    "category": check.category,
                    "subject": check.subject,
                    "status": check.status,
                    "model_value": _csv_value(check.model_value),
                    "reference_value": _csv_value(check.reference_value),
                    "tolerance": _csv_value(check.tolerance),
                    "delta": _csv_value(check.delta),
                    "detail": check.detail,
                }
            )
    return rows


def _effect_matrix_rows(
    case_records: Sequence[Mapping[str, Any]], baseline_metrics: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    metric_names = list(baseline_metrics.keys())
    rows = []
    for record in case_records:
        row = {
            "case_id": record["case_id"],
            "variable_id": record["variable_id"] or "",
            "variable_name": record["variable_name"] or "",
            "direction": record["direction"],
            "requested_delta": record["requested_delta"],
            "status": record["status"],
        }
        for name in metric_names:
            row[name] = record["metrics"].get(name)
        rows.append(row)
    return rows


def _effect_delta_rows(
    case_records: Sequence[Mapping[str, Any]], baseline_metrics: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    rows = []
    for record in case_records:
        if record["is_baseline"]:
            continue
        for name, value in record["metrics"].items():
            base = baseline_metrics.get(name)
            if isinstance(base, (int, float)) and isinstance(value, (int, float)):
                delta = value - base
                relative = delta / base if base else None
            else:
                delta = None
                relative = None
            rows.append(
                {
                    "case_id": record["case_id"],
                    "variable_id": record["variable_id"],
                    "variable_name": record["variable_name"],
                    "direction": record["direction"],
                    "metric": name,
                    "value": value,
                    "baseline": base,
                    "delta": delta,
                    "relative_delta": relative,
                }
            )
    return rows


def _case_line(record: Mapping[str, Any]) -> Dict[str, Any]:
    checks = record["checks"]
    return {
        "iteration": record["iteration"],
        "design_id": record["case_id"],
        "x": record["physical"],
        "status": record["status"],
        "variable_id": record["variable_id"],
        "direction": record["direction"],
        "requested_delta": record["requested_delta"],
        "failed_checks": record["failed_checks"],
        "warned_checks": record["warned_checks"],
        "metrics": record["metrics"],
        "rcaide_metrics": record["rcaide_metrics"],
        "objective": None,
        "constraints": {
            "usable_volume_m3": record["metrics"].get("fuselage_usable_volume_m3"),
            "required_volume_m3": record["metrics"].get("fuselage_required_volume_m3"),
            "volume_margin_m3": record["metrics"].get("fuselage_volume_margin_m3"),
        },
        "feasible": record["status"] == "ok",
        "fidelity": "geometry",
        "cache_hit": False,
        "physical_call_count": 0,
        "wall_seconds": record["wall_seconds"],
        "cumulative_calls": 0,
        "best_feasible_objective": None,
        "check_count": len(checks),
        "error": record["error"],
    }


def _display_path(value: Any) -> str:
    try:
        resolved = Path(str(value)).resolve()
        return resolved.relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return str(value)


def _environment() -> Dict[str, Any]:
    return {
        "python": sys.version,
        "python_executable": _display_path(sys.executable),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "geometry_model_version": GEOMETRY_MODEL_VERSION,
        "packages": _software_versions(),
    }


def _software_versions() -> Dict[str, Any]:
    versions: Dict[str, Any] = {}
    try:
        from importlib.metadata import version

        for name in ("RCAIDE-LEADS", "numpy", "scipy", "matplotlib"):
            try:
                versions[name] = version(name)
            except Exception:
                versions[name] = None
    except Exception:
        pass
    try:
        import RCAIDE

        versions["RCAIDE_module"] = getattr(RCAIDE, "__version__", None)
    except Exception:
        versions["RCAIDE_module"] = None
    return versions


def _git_sha(repo_root: Path) -> Optional[str]:
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    git_dir = repo_root / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            ref_file = git_dir / ref
            if ref_file.is_file():
                return ref_file.read_text(encoding="utf-8").strip()
            packed = git_dir / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + ref):
                        return line.split()[0]
        else:
            return head
    except Exception:
        return None
    return None


def _compare(
    check_id: str,
    category: str,
    subject: str,
    model_value: float,
    reference_value: float,
    relative_tolerance: float,
    detail: str = "",
) -> CheckResult:
    delta = model_value - reference_value
    relative = delta / reference_value if reference_value else None
    passed = abs(delta) <= relative_tolerance * abs(reference_value) + 1e-12
    return CheckResult(
        check_id,
        category,
        subject,
        PASS if passed else FAIL,
        detail if passed else "%s; delta %.6g exceeds relative tolerance %g" % (detail, delta, relative_tolerance),
        model_value=model_value,
        reference_value=reference_value,
        tolerance=relative_tolerance,
        delta=delta,
    )


def _abs_compare(
    check_id: str,
    category: str,
    subject: str,
    model_value: float,
    reference_value: float,
    absolute_tolerance: float,
    detail: str = "",
    status_if_false: str = FAIL,
) -> CheckResult:
    delta = model_value - reference_value
    passed = abs(delta) <= absolute_tolerance
    return CheckResult(
        check_id,
        category,
        subject,
        PASS if passed else status_if_false,
        detail if passed else "%s; delta %.6g exceeds absolute tolerance %g" % (detail, delta, absolute_tolerance),
        model_value=model_value,
        reference_value=reference_value,
        tolerance=absolute_tolerance,
        delta=delta,
    )


def _boolean(
    check_id: str,
    category: str,
    subject: str,
    passed: bool,
    detail: str,
    status_if_false: str = FAIL,
    model_value: Any = None,
    reference_value: Any = None,
) -> CheckResult:
    return CheckResult(
        check_id,
        category,
        subject,
        PASS if passed else status_if_false,
        detail,
        model_value=model_value,
        reference_value=reference_value,
    )


def _strictly_increasing(values: Sequence[float]) -> bool:
    return all(left < right for left, right in zip(values, values[1:]))


def _strictly_decreasing(values: Sequence[float]) -> bool:
    return all(left > right for left, right in zip(values, values[1:]))


def _fmt_list(values: Sequence[float]) -> str:
    return "[" + ", ".join("%.6g" % value for value in values) + "]"


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def _write_json(path: Path, data: Any, pretty: bool) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2 if pretty else None, sort_keys=True)
        handle.write("\n")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
