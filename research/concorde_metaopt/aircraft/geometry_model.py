"""Dependency-free geometry model for the Concorde 15D Phase I design space.

This module turns the 15 physical variables into a self-consistent planform and
fuselage description.  It deliberately does not import RCAIDE: the RCAIDE
adapter (building the actual Vehicle objects) lives in geometry_builder.py and
cross-checks these numbers against RCAIDE's own planform routines.

Parameterization rules (all recorded in the P1 evidence run):

* W01 wing_area is the wing reference area.  The span is derived from
  sqrt(wing_area * aspect_ratio).  The root chord is solved from the piecewise
  trapezoid area of the four sections so that the section planform area equals
  wing_area exactly.  This replaces the upstream hard-coded root chord (33.8 m)
  which is inconsistent with the upstream declared area (358.25 m^2) and the
  four section chords (the literal trapezoid area is about 405 m^2).
* W06/W07 are the span fractions of sections 2 and 3; W08/W09 are their chords
  as fractions of the (derived) root chord.  The tip chord fraction is held at
  the upstream taper ratio 0.032544.
* W03/W04/W05 are quarter-chord sweeps of sections 1/2/3.  Wing planform code
  in RCAIDE forces the last (tip) segment sweep to the previous value; the model
  follows that convention and records it.
* W10 is the tip twist; sections 1-3 stay at zero twist (upstream values).
* V01 is the vertical-tail planform area, V02 a delta applied to the three tail
  section quarter-chord sweeps.  Tail span follows sqrt(V01 * 0.74); the root
  chord is solved from the tail area and the upstream chord ratios.
* F01 is fuselage total length, F02 the nose fineness (nose length = F02 *
  width), F03 the maximum height / width ratio (height = F03 * 2.88 m).  Tail
  fineness keeps the upstream 6.4 / 4.3 ratio.  Segment stations keep the
  upstream normalized distribution.
* Nacelles, landing gear positions and the propulsion contract are not part of
  the 15 variables and stay at their upstream values.

Every derived quantity that RCAIDE can recompute is recomputed here first; the
geometry_builder adapter re-derives the same values with RCAIDE's
wing_planform/segment_properties and fuselage_planform and the checks compare
both.  Mass/CG is a documented provisional estimate (component mass fractions
of the upstream operating empty weight), flagged NOT_FROZEN; no fuel-burn
conclusion may use it yet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

GEOMETRY_MODEL_VERSION = "p1-2026-10-28"

# Upstream (tutorial Concorde.py) declared values, used for baseline provenance
# and documented deltas.  They are NOT used to overwrite derived quantities.
SOURCE_BASELINE: Dict[str, Any] = {
    "wing_reference_area_m2": 358.25,
    "wing_span_m": 25.6,
    "wing_aspect_ratio": 1.83,
    "wing_root_chord_m": 33.8,
    "wing_tip_chord_m": 1.1,
    "wing_taper_ratio": 1.1 / 33.8,
    "wing_wetted_area_m2": 601.0,
    "wing_exposed_area_m2": 326.5,
    "wing_section_chord_ratios": (1.0, 13.8 / 33.8, 4.4 / 33.8, 1.1 / 33.8),
    "wing_section_span_fractions": (0.0, 12.3 / 25.6, 24.2 / 25.6, 1.0),
    "wing_section_sweeps_deg": (67.0, 48.0, 71.0, 0.0),
    "tail_area_m2": 33.91,
    "tail_span_m": 6.0,
    "tail_aspect_ratio": 0.74,
    "tail_root_chord_m": 14.5,
    "tail_tip_chord_m": 2.7,
    "tail_taper_ratio": 2.7 / 14.5,
    "tail_section_chord_ratios": (1.0, 7.5 / 14.5, 2.7 / 14.5),
    "tail_section_span_fractions": (0.0, 2.4 / 6.0, 1.0),
    "tail_section_sweeps_deg": (63.0, 40.0, 0.0),
    "fuselage_length_m": 61.66,
    "fuselage_width_m": 2.88,
    "fuselage_height_m": 3.32,
    "fuselage_nose_fineness": 4.3,
    "fuselage_tail_fineness": 6.4,
    "fuselage_wetted_area_m2": 442.0,
    "fuselage_front_projected_m2": 11.9,
    "fuselage_effective_diameter_m": 3.1,
    "nacelle_diameter_m": 1.3,
    "nacelle_length_m": 10.0,
    "nacelle_inlet_diameter_m": 1.1,
    "nacelle_wetted_area_m2": 30.0,
    "nacelle_origin_m": (37.0, 5.5, -1.6),
}

WING_THICKNESS_TO_CHORD = 0.03
TAIL_THICKNESS_TO_CHORD = 0.04
WING_ORIGIN_X_M = 14.0
TAIL_ORIGIN_X_M = 42.0
FUSELAGE_TAIL_OVER_NOSE_FINENESS = 6.4 / 4.3
NACELLE_COUNT = 2

# Fuselage station profiles read from the upstream file: station x positions are
# expressed as fractions of the nose / cabin / tail regions, and the local
# heights / widths are scaled from the upstream values.
_NOSE_STATION_FRACTIONS = (0.244560, 0.466250, 0.733105)
_TAIL_MID_STATION_FRACTION = 0.233690
_HEIGHT_PROFILE_M = (0.0, 1.4502, 2.356, 3.0581, 3.3200, 3.3200, 2.952, 0.001)
_WIDTH_PROFILE_M = (0.001, 1.567, 2.3429, 2.741, 2.8800, 2.8800, 2.8800, 0.001)
_SEGMENT_TAGS = (
    "segment_0",
    "segment_1",
    "segment_2",
    "segment_3",
    "segment_4",
    "segment_5",
    "segment_6",
    "segment_7",
)

# Provisional mass model (documented, NOT_FROZEN).  Component fractions sum to
# 1.0 of the upstream operating empty weight; positions are geometry derived.
PROVISIONAL_OEW_KG = 78700.0
PROVISIONAL_FUEL_KG = 95680.0
PROVISIONAL_PAYLOAD_KG = 9500.0
PROVISIONAL_CARGO_KG = 1000.0
_COMPONENT_FRACTIONS = {
    "wing": 0.20,
    "fuselage": 0.30,
    "vertical_tail": 0.03,
    "landing_gear": 0.08,
    "propulsion": 0.25,
    "systems": 0.14,
}
PASSENGER_COUNT = 100
VOLUME_PER_PASSENGER_M3 = 1.0
CARGO_VOLUME_M3 = 10.0


class GeometryError(ValueError):
    """Raised when a design vector cannot produce a valid Concorde geometry."""


@dataclass(frozen=True)
class WingSection:
    tag: str
    percent_span_location: float
    chord_m: float
    quarter_chord_sweep_deg: float
    twist_deg: float
    thickness_to_chord: float
    leading_edge_x_m: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag,
            "percent_span_location": _round(self.percent_span_location),
            "chord_m": _round(self.chord_m),
            "quarter_chord_sweep_deg": _round(self.quarter_chord_sweep_deg),
            "twist_deg": _round(self.twist_deg),
            "thickness_to_chord": _round(self.thickness_to_chord),
            "leading_edge_x_m": _round(self.leading_edge_x_m),
        }


@dataclass(frozen=True)
class WingPlanform:
    tag: str
    vertical: bool
    symmetric: bool
    area_m2: float
    aspect_ratio: float
    span_m: float
    root_chord_m: float
    tip_chord_m: float
    taper_ratio: float
    mean_aerodynamic_chord_m: float
    mean_geometric_chord_m: float
    wetted_area_m2: float
    exposed_area_m2: float
    thickness_to_chord: float
    sections: Tuple[WingSection, ...]
    total_length_m: float
    aerodynamic_center_x_m: float
    aerodynamic_center_y_m: float
    mac_span_location_m: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag,
            "vertical": self.vertical,
            "symmetric": self.symmetric,
            "area_m2": _round(self.area_m2),
            "aspect_ratio": _round(self.aspect_ratio),
            "span_m": _round(self.span_m),
            "root_chord_m": _round(self.root_chord_m),
            "tip_chord_m": _round(self.tip_chord_m),
            "taper_ratio": _round(self.taper_ratio),
            "mean_aerodynamic_chord_m": _round(self.mean_aerodynamic_chord_m),
            "mean_geometric_chord_m": _round(self.mean_geometric_chord_m),
            "wetted_area_m2": _round(self.wetted_area_m2),
            "exposed_area_m2": _round(self.exposed_area_m2),
            "thickness_to_chord": _round(self.thickness_to_chord),
            "sections": [section.to_dict() for section in self.sections],
            "total_length_m": _round(self.total_length_m),
            "aerodynamic_center_x_m": _round(self.aerodynamic_center_x_m),
            "aerodynamic_center_y_m": _round(self.aerodynamic_center_y_m),
            "mac_span_location_m": _round(self.mac_span_location_m),
        }


@dataclass(frozen=True)
class FuselageStation:
    tag: str
    percent_x_location: float
    x_m: float
    width_m: float
    height_m: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag,
            "percent_x_location": _round(self.percent_x_location),
            "x_m": _round(self.x_m),
            "width_m": _round(self.width_m),
            "height_m": _round(self.height_m),
        }


@dataclass(frozen=True)
class FuselageGeometry:
    length_m: float
    width_m: float
    max_height_m: float
    nose_length_m: float
    tail_length_m: float
    cabin_length_m: float
    nose_fineness: float
    tail_fineness: float
    wetted_area_m2: float
    front_projected_area_m2: float
    side_projected_area_m2: float
    effective_diameter_m: float
    usable_volume_m3: float
    required_volume_m3: float
    stations: Tuple[FuselageStation, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "length_m": _round(self.length_m),
            "width_m": _round(self.width_m),
            "max_height_m": _round(self.max_height_m),
            "nose_length_m": _round(self.nose_length_m),
            "tail_length_m": _round(self.tail_length_m),
            "cabin_length_m": _round(self.cabin_length_m),
            "nose_fineness": _round(self.nose_fineness),
            "tail_fineness": _round(self.tail_fineness),
            "wetted_area_m2": _round(self.wetted_area_m2),
            "front_projected_area_m2": _round(self.front_projected_area_m2),
            "side_projected_area_m2": _round(self.side_projected_area_m2),
            "effective_diameter_m": _round(self.effective_diameter_m),
            "usable_volume_m3": _round(self.usable_volume_m3),
            "required_volume_m3": _round(self.required_volume_m3),
            "stations": [station.to_dict() for station in self.stations],
        }


@dataclass(frozen=True)
class NacelleGeometry:
    count: int
    diameter_m: float
    length_m: float
    inlet_diameter_m: float
    wetted_area_m2: float
    origin_m: Tuple[float, float, float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "diameter_m": _round(self.diameter_m),
            "length_m": _round(self.length_m),
            "inlet_diameter_m": _round(self.inlet_diameter_m),
            "wetted_area_m2": _round(self.wetted_area_m2),
            "origin_m": [_round(value) for value in self.origin_m],
        }


@dataclass(frozen=True)
class ConcordeGeometry:
    names: Tuple[str, ...]
    vector: Tuple[float, ...]
    wing: WingPlanform
    vertical_tail: WingPlanform
    fuselage: FuselageGeometry
    nacelle: NacelleGeometry
    mass_kg: Mapping[str, float]
    cg_x_m: float
    static_margin: float
    baseline_comparison: Mapping[str, Any]
    model_version: str
    mass_model_status: str

    def to_dict(self, include_sections: bool = True) -> Dict[str, Any]:
        wing = self.wing.to_dict()
        tail = self.vertical_tail.to_dict()
        if not include_sections:
            wing.pop("sections", None)
            tail.pop("sections", None)
        return {
            "model_version": self.model_version,
            "design_variables": {name: _round(value) for name, value in zip(self.names, self.vector)},
            "main_wing": wing,
            "vertical_stabilizer": tail,
            "fuselage": self.fuselage.to_dict(),
            "nacelle": self.nacelle.to_dict(),
            "mass_kg": {key: _round(value) for key, value in self.mass_kg.items()},
            "cg_x_m": _round(self.cg_x_m),
            "static_margin": _round(self.static_margin),
            "mass_model_status": self.mass_model_status,
            "baseline_comparison": _round_tree(self.baseline_comparison),
        }


def build_geometry(names: Sequence[str], vector: Sequence[float]) -> ConcordeGeometry:
    """Build the geometry for a physical 15D design vector (SI units)."""
    if len(names) != 15 or len(vector) != 15:
        raise GeometryError("expected 15 variable names and 15 values")
    values = {str(name): float(value) for name, value in zip(names, vector)}
    for name, value in values.items():
        if not math.isfinite(value):
            raise GeometryError("design variable %s is not finite" % name)

    wing_area = _positive(values["wing_area"], "wing_area")
    aspect_ratio = _positive(values["aspect_ratio"], "aspect_ratio")
    tail_area = _positive(values["vertical_tail_area"], "vertical_tail_area")
    fuselage_length = _positive(values["fuselage_length"], "fuselage_length")
    fuselage_fineness = _positive(values["fuselage_fineness"], "fuselage_fineness")
    height_width_ratio = _positive(values["fuselage_height_width_ratio"], "fuselage_height_width_ratio")

    span_2 = _in_range(values["span_location_2"], "span_location_2")
    span_3 = _in_range(values["span_location_3"], "span_location_3")
    if not span_2 < span_3:
        raise GeometryError("span_location_2 must be smaller than span_location_3")
    chord_2 = _in_range(values["chord_ratio_2"], "chord_ratio_2")
    chord_3 = _in_range(values["chord_ratio_3"], "chord_ratio_3")
    if not chord_3 < chord_2 < 1.0:
        raise GeometryError("chord_ratio_3 < chord_ratio_2 < 1 required")

    wing = _wing_planform(
        tag="main_wing",
        vertical=False,
        area=wing_area,
        aspect_ratio=aspect_ratio,
        span_fractions=(0.0, span_2, span_3, 1.0),
        chord_fractions=(1.0, chord_2, chord_3, SOURCE_BASELINE["wing_taper_ratio"]),
        sweep_deg=(values["sweep_1"], values["sweep_2"], values["sweep_3"], values["sweep_3"]),
        twist_deg=(0.0, 0.0, 0.0, values["tip_twist"]),
        thickness_to_chord=WING_THICKNESS_TO_CHORD,
    )

    tail_sweep_delta = values["vertical_tail_sweep_delta"]
    tail_sweeps = tuple(
        _clamp_sweep(angle + tail_sweep_delta) for angle in SOURCE_BASELINE["tail_section_sweeps_deg"]
    )
    vertical_tail = _wing_planform(
        tag="vertical_stabilizer",
        vertical=True,
        area=tail_area,
        aspect_ratio=SOURCE_BASELINE["tail_aspect_ratio"],
        span_fractions=SOURCE_BASELINE["tail_section_span_fractions"],
        chord_fractions=SOURCE_BASELINE["tail_section_chord_ratios"],
        sweep_deg=tail_sweeps,
        twist_deg=(0.0, 0.0, 0.0),
        thickness_to_chord=TAIL_THICKNESS_TO_CHORD,
    )

    fuselage = _fuselage_geometry(
        length=fuselage_length,
        width=SOURCE_BASELINE["fuselage_width_m"],
        nose_fineness=fuselage_fineness,
        height_width_ratio=height_width_ratio,
    )

    nacelle = _nacelle_geometry()
    mass, cg_x, static_margin = _provisional_mass_and_cg(wing, vertical_tail, fuselage)

    comparison = _baseline_comparison(wing, vertical_tail, fuselage)
    return ConcordeGeometry(
        names=tuple(names),
        vector=tuple(float(value) for value in vector),
        wing=wing,
        vertical_tail=vertical_tail,
        fuselage=fuselage,
        nacelle=nacelle,
        mass_kg=mass,
        cg_x_m=cg_x,
        static_margin=static_margin,
        baseline_comparison=comparison,
        model_version=GEOMETRY_MODEL_VERSION,
        mass_model_status="PROVISIONAL_NOT_FROZEN",
    )


def _wing_planform(
    tag: str,
    vertical: bool,
    area: float,
    aspect_ratio: float,
    span_fractions: Sequence[float],
    chord_fractions: Sequence[float],
    sweep_deg: Sequence[float],
    twist_deg: Sequence[float],
    thickness_to_chord: float,
) -> WingPlanform:
    spans = [float(value) for value in span_fractions]
    ratios = [float(value) for value in chord_fractions]
    sweeps = [float(value) for value in sweep_deg]
    twists = [float(value) for value in twist_deg]
    if len(spans) != len(ratios) or len(spans) != len(sweeps) or len(spans) != len(twists):
        raise GeometryError("section arrays must have the same length")
    if len(spans) < 2:
        raise GeometryError("at least two sections are required")
    if not spans[0] == 0.0 or not spans[-1] == 1.0:
        raise GeometryError("wing sections must start at 0 and end at 1")
    for left, right in zip(spans, spans[1:]):
        if not left < right:
            raise GeometryError("wing span fractions must be strictly increasing")
    if not ratios[0] == 1.0:
        raise GeometryError("root chord fraction must be 1.0")
    for ratio in ratios:
        if not ratio > 0.0:
            raise GeometryError("chord fractions must be positive")
    for sweep in sweeps:
        if not (math.isfinite(sweep) and 0.0 <= sweep <= 90.0):
            raise GeometryError("section sweep must be within [0, 90] deg")
    if thickness_to_chord <= 0.0:
        raise GeometryError("thickness_to_chord must be positive")

    span = math.sqrt(area * aspect_ratio)
    symmetric = not vertical
    semispan = span / 2.0 if symmetric else span
    # Area closure: reference area = root_chord * span * K, so the root chord
    # follows from the requested area and the normalized section geometry.
    k = 0.0
    for index in range(len(spans) - 1):
        ds = spans[index + 1] - spans[index]
        k += 0.5 * ds * (ratios[index] + ratios[index + 1])
    if not k > 0.0:
        raise GeometryError("degenerate wing section geometry")
    root_chord = area / (span * k)
    chords = [ratio * root_chord for ratio in ratios]

    sections: List[WingSection] = []
    leading_edge = 0.0
    for index, span_fraction in enumerate(spans):
        if index > 0:
            delta_y = (spans[index] - spans[index - 1]) * semispan
            quarter_chord_sweep = math.radians(sweeps[index - 1])
            leading_edge += delta_y * math.tan(quarter_chord_sweep) - 0.25 * (
                chords[index] - chords[index - 1]
            )
        sections.append(
            WingSection(
                tag=_section_tag(index, len(spans)),
                percent_span_location=span_fraction,
                chord_m=chords[index],
                quarter_chord_sweep_deg=sweeps[index],
                twist_deg=twists[index],
                thickness_to_chord=thickness_to_chord,
                leading_edge_x_m=leading_edge,
            )
        )

    area_sum = 0.0
    signed_area = 0.0
    wetted = 0.0
    mac_integral = 0.0
    for index in range(len(spans) - 1):
        ds = spans[index + 1] - spans[index]
        segment_area = semispan * ds * 0.5 * (chords[index] + chords[index + 1])
        if symmetric:
            segment_area *= 2.0
        area_sum += segment_area
        signed_area += segment_area if not symmetric else segment_area
        exposed = semispan * ds * 0.5 * (chords[index] + chords[index + 1])
        if symmetric:
            exposed *= 2.0
        wetted += _segment_wetted_area(exposed, thickness_to_chord)
        mac_integral += _chord_squared_integral(chords[index], chords[index + 1], ds)
    if not area_sum > 0.0:
        raise GeometryError("computed wing area is not positive")
    mac = span * mac_integral / area_sum
    semispan = span / 2.0 if symmetric else span
    y_mac = _span_location_for_chord(sections, semispan, mac)
    y_mac_fraction = y_mac / semispan
    ac_x = _leading_edge_at(sections, y_mac_fraction) + 0.25 * mac

    return WingPlanform(
        tag=tag,
        vertical=vertical,
        symmetric=symmetric,
        area_m2=area_sum,
        aspect_ratio=span * span / area_sum,
        span_m=span,
        root_chord_m=root_chord,
        tip_chord_m=chords[-1],
        taper_ratio=chords[-1] / root_chord,
        mean_aerodynamic_chord_m=mac,
        mean_geometric_chord_m=area_sum / span,
        wetted_area_m2=wetted,
        exposed_area_m2=area_sum,
        thickness_to_chord=thickness_to_chord,
        sections=tuple(sections),
        total_length_m=leading_edge + chords[-1],
        aerodynamic_center_x_m=ac_x,
        aerodynamic_center_y_m=0.0 if symmetric else y_mac,
        mac_span_location_m=y_mac,
    )


def _fuselage_geometry(
    length: float,
    width: float,
    nose_fineness: float,
    height_width_ratio: float,
) -> FuselageGeometry:
    nose_length = nose_fineness * width
    tail_fineness = nose_fineness * FUSELAGE_TAIL_OVER_NOSE_FINENESS
    tail_length = tail_fineness * width
    cabin_length = length - nose_length - tail_length
    if not cabin_length > 0.0:
        raise GeometryError(
            "fuselage_length %.3f m leaves no cabin: nose %.3f m + tail %.3f m"
            % (length, nose_length, tail_length)
        )
    max_height = height_width_ratio * width
    height_scale = max_height / SOURCE_BASELINE["fuselage_height_m"]
    width_scale = width / SOURCE_BASELINE["fuselage_width_m"]

    x_positions = [
        0.0,
        _NOSE_STATION_FRACTIONS[0] * nose_length,
        _NOSE_STATION_FRACTIONS[1] * nose_length,
        _NOSE_STATION_FRACTIONS[2] * nose_length,
        nose_length,
        length - tail_length,
        length - tail_length + _TAIL_MID_STATION_FRACTION * tail_length,
        length,
    ]
    stations = []
    for index, x_position in enumerate(x_positions):
        stations.append(
            FuselageStation(
                tag=_SEGMENT_TAGS[index],
                percent_x_location=x_position / length,
                x_m=x_position,
                width_m=_WIDTH_PROFILE_M[index] * width_scale,
                height_m=_HEIGHT_PROFILE_M[index] * height_scale,
            )
        )

    wetted = 0.0
    side_projected = 0.0
    front_projected = 0.0
    for station, next_station in zip(stations, stations[1:]):
        delta_x = next_station.x_m - station.x_m
        if delta_x <= 0.0:
            raise GeometryError("fuselage stations are not strictly increasing")
        side_projected += 0.5 * (station.height_m + next_station.height_m) * delta_x
        wetted += _truncated_elliptic_cone_lateral_area(
            station.width_m / 2.0,
            station.height_m / 2.0,
            next_station.width_m / 2.0,
            next_station.height_m / 2.0,
            delta_x,
        )
        area_a = math.pi * station.width_m / 2.0 * station.height_m / 2.0
        area_b = math.pi * next_station.width_m / 2.0 * next_station.height_m / 2.0
        front_projected = max(front_projected, area_a, area_b)

    max_station = max(stations, key=lambda station: station.width_m * station.height_m)
    effective_diameter = _effective_diameter(max_station.width_m, max_station.height_m)

    usable_volume = _frustum_volume_between(stations, nose_length, length - tail_length)
    required_volume = PASSENGER_COUNT * VOLUME_PER_PASSENGER_M3 + CARGO_VOLUME_M3

    return FuselageGeometry(
        length_m=length,
        width_m=width,
        max_height_m=max_height,
        nose_length_m=nose_length,
        tail_length_m=tail_length,
        cabin_length_m=cabin_length,
        nose_fineness=nose_fineness,
        tail_fineness=tail_fineness,
        wetted_area_m2=wetted,
        front_projected_area_m2=front_projected,
        side_projected_area_m2=side_projected,
        effective_diameter_m=effective_diameter,
        usable_volume_m3=usable_volume,
        required_volume_m3=required_volume,
        stations=tuple(stations),
    )


def _frustum_volume_between(stations: Sequence[FuselageStation], start: float, end: float) -> float:
    volume = 0.0
    for station, next_station in zip(stations, stations[1:]):
        segment_start = station.x_m
        segment_end = next_station.x_m
        overlap_start = max(start, segment_start)
        overlap_end = min(end, segment_end)
        if not overlap_end > overlap_start:
            continue
        fraction_start = (overlap_start - segment_start) / (segment_end - segment_start)
        fraction_end = (overlap_end - segment_start) / (segment_end - segment_start)
        width_start = station.width_m + fraction_start * (next_station.width_m - station.width_m)
        height_start = station.height_m + fraction_start * (next_station.height_m - station.height_m)
        width_end = station.width_m + fraction_end * (next_station.width_m - station.width_m)
        height_end = station.height_m + fraction_end * (next_station.height_m - station.height_m)
        area_start = math.pi * width_start * height_start / 4.0
        area_end = math.pi * width_end * height_end / 4.0
        delta_x = overlap_end - overlap_start
        volume += delta_x / 3.0 * (area_start + area_end + math.sqrt(area_start * area_end))
    return volume


def _nacelle_geometry() -> NacelleGeometry:
    return NacelleGeometry(
        count=NACELLE_COUNT,
        diameter_m=SOURCE_BASELINE["nacelle_diameter_m"],
        length_m=SOURCE_BASELINE["nacelle_length_m"],
        inlet_diameter_m=SOURCE_BASELINE["nacelle_inlet_diameter_m"],
        wetted_area_m2=SOURCE_BASELINE["nacelle_wetted_area_m2"],
        origin_m=SOURCE_BASELINE["nacelle_origin_m"],
    )


def _provisional_mass_and_cg(
    wing: WingPlanform,
    tail: WingPlanform,
    fuselage: FuselageGeometry,
) -> Tuple[Dict[str, float], float, float]:
    oew = PROVISIONAL_OEW_KG
    wing_mass = oew * _COMPONENT_FRACTIONS["wing"] * wing.area_m2 / SOURCE_BASELINE["wing_reference_area_m2"]
    fuselage_mass = oew * _COMPONENT_FRACTIONS["fuselage"] * fuselage.length_m / SOURCE_BASELINE["fuselage_length_m"]
    tail_mass = oew * _COMPONENT_FRACTIONS["vertical_tail"] * tail.area_m2 / SOURCE_BASELINE["tail_area_m2"]
    gear_mass = oew * _COMPONENT_FRACTIONS["landing_gear"]
    propulsion_mass = oew * _COMPONENT_FRACTIONS["propulsion"]
    systems_mass = oew * _COMPONENT_FRACTIONS["systems"]

    wing_cg = WING_ORIGIN_X_M + 0.45 * wing.root_chord_m
    fuselage_cg = 0.45 * fuselage.length_m
    tail_cg = TAIL_ORIGIN_X_M + 0.25 * tail.root_chord_m
    gear_cg = 0.39 * fuselage.length_m
    propulsion_cg = 37.0
    systems_cg = 0.45 * fuselage.length_m
    fuel_cg = wing_cg
    payload_cg = 0.35 * fuselage.length_m
    cargo_cg = 0.30 * fuselage.length_m

    masses = {
        "wing": wing_mass,
        "fuselage": fuselage_mass,
        "vertical_tail": tail_mass,
        "landing_gear": gear_mass,
        "propulsion": propulsion_mass,
        "systems": systems_mass,
        "fuel": PROVISIONAL_FUEL_KG,
        "payload": PROVISIONAL_PAYLOAD_KG,
        "cargo": PROVISIONAL_CARGO_KG,
    }
    positions = {
        "wing": wing_cg,
        "fuselage": fuselage_cg,
        "vertical_tail": tail_cg,
        "landing_gear": gear_cg,
        "propulsion": propulsion_cg,
        "systems": systems_cg,
        "fuel": fuel_cg,
        "payload": payload_cg,
        "cargo": cargo_cg,
    }
    total_mass = sum(masses.values())
    if total_mass <= 0.0:
        raise GeometryError("provisional mass model returned a non-positive mass")
    cg_x = sum(masses[key] * positions[key] for key in masses) / total_mass
    wing_ac_x = WING_ORIGIN_X_M + wing.aerodynamic_center_x_m
    static_margin = (wing_ac_x - cg_x) / wing.mean_aerodynamic_chord_m
    result = dict(masses)
    result["total_takeoff"] = total_mass
    result["operating_empty"] = sum(
        masses[key]
        for key in ("wing", "fuselage", "vertical_tail", "landing_gear", "propulsion", "systems")
    )
    return result, cg_x, static_margin


def _baseline_comparison(
    wing: WingPlanform,
    tail: WingPlanform,
    fuselage: FuselageGeometry,
) -> Dict[str, Any]:
    def delta(key: str, value: float, source: float) -> Dict[str, Any]:
        return {
            "derived": _round(value),
            "source_declared": _round(source),
            "delta": _round(value - source),
            "relative_delta": _round((value - source) / source if source else 0.0),
        }

    return {
        "wing_area_m2": delta("wing_area_m2", wing.area_m2, SOURCE_BASELINE["wing_reference_area_m2"]),
        "wing_span_m": delta("wing_span_m", wing.span_m, SOURCE_BASELINE["wing_span_m"]),
        "wing_aspect_ratio": delta(
            "wing_aspect_ratio", wing.aspect_ratio, SOURCE_BASELINE["wing_aspect_ratio"]
        ),
        "wing_root_chord_m": delta(
            "wing_root_chord_m", wing.root_chord_m, SOURCE_BASELINE["wing_root_chord_m"]
        ),
        "wing_wetted_area_m2": delta(
            "wing_wetted_area_m2", wing.wetted_area_m2, SOURCE_BASELINE["wing_wetted_area_m2"]
        ),
        "wing_exposed_area_m2": delta(
            "wing_exposed_area_m2", wing.exposed_area_m2, SOURCE_BASELINE["wing_exposed_area_m2"]
        ),
        "tail_area_m2": delta("tail_area_m2", tail.area_m2, SOURCE_BASELINE["tail_area_m2"]),
        "tail_span_m": delta("tail_span_m", tail.span_m, SOURCE_BASELINE["tail_span_m"]),
        "tail_root_chord_m": delta(
            "tail_root_chord_m", tail.root_chord_m, SOURCE_BASELINE["tail_root_chord_m"]
        ),
        "fuselage_length_m": delta(
            "fuselage_length_m", fuselage.length_m, SOURCE_BASELINE["fuselage_length_m"]
        ),
        "fuselage_wetted_area_m2": delta(
            "fuselage_wetted_area_m2", fuselage.wetted_area_m2, SOURCE_BASELINE["fuselage_wetted_area_m2"]
        ),
        "fuselage_front_projected_m2": delta(
            "fuselage_front_projected_m2",
            fuselage.front_projected_area_m2,
            SOURCE_BASELINE["fuselage_front_projected_m2"],
        ),
        "fuselage_effective_diameter_m": delta(
            "fuselage_effective_diameter_m",
            fuselage.effective_diameter_m,
            SOURCE_BASELINE["fuselage_effective_diameter_m"],
        ),
    }


def _section_tag(index: int, count: int) -> str:
    if index == 0:
        return "section_1"
    if index == count - 1:
        return "tip"
    return "section_%d" % (index + 1)


def _span_location_for_chord(
    sections: Sequence[WingSection], semispan: float, chord: float
) -> float:
    for station, next_station in zip(sections, sections[1:]):
        chord_start = station.chord_m
        chord_end = next_station.chord_m
        if chord_start == chord_end:
            continue
        if min(chord_start, chord_end) <= chord <= max(chord_start, chord_end):
            fraction = (chord - chord_start) / (chord_end - chord_start)
            span_fraction = station.percent_span_location + fraction * (
                next_station.percent_span_location - station.percent_span_location
            )
            return span_fraction * semispan
    return 0.0 if chord >= sections[0].chord_m else semispan


def _leading_edge_at(sections: Sequence[WingSection], span_fraction: float) -> float:
    if span_fraction <= 0.0:
        return sections[0].leading_edge_x_m
    for station, next_station in zip(sections, sections[1:]):
        y_start = station.percent_span_location
        y_end = next_station.percent_span_location
        if y_start <= span_fraction <= y_end:
            fraction = 0.0 if y_end == y_start else (span_fraction - y_start) / (y_end - y_start)
            return station.leading_edge_x_m + fraction * (
                next_station.leading_edge_x_m - station.leading_edge_x_m
            )
    return sections[-1].leading_edge_x_m


def _chord_squared_integral(chord_start: float, chord_end: float, fraction_length: float) -> float:
    delta = chord_end - chord_start
    return fraction_length * (chord_start * chord_start + chord_start * delta + delta * delta / 3.0)


def _segment_wetted_area(exposed_area: float, thickness_to_chord: float) -> float:
    if thickness_to_chord < 0.05:
        return 2.003 * exposed_area
    return (1.977 + 0.52 * thickness_to_chord) * exposed_area


def _truncated_elliptic_cone_lateral_area(a: float, b: float, c: float, d: float, h: float) -> float:
    s_major = math.sqrt(h * h + (a - c) * (a - c))
    s_minor = math.sqrt(h * h + (b - d) * (b - d))
    return math.pi * ((a + c) / 2.0) * s_major + math.pi * ((b + d) / 2.0) * s_minor


def _effective_diameter(width: float, height: float) -> float:
    a = width / 2.0
    b = height / 2.0
    r = (a - b) / (a + b)
    return (a + b) * (64.0 - 3.0 * r ** 4) / (64.0 - 16.0 * r ** 2)


def _positive(value: float, name: str) -> float:
    number = float(value)
    if not (math.isfinite(number) and number > 0.0):
        raise GeometryError("%s must be a positive finite number, got %r" % (name, value))
    return number


def _in_range(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise GeometryError("%s must be finite, got %r" % (name, value))
    return number


def _clamp_sweep(value: float) -> float:
    return min(89.9, max(0.0, float(value)))


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 9)
    return value


def _round_tree(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _round_tree(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round_tree(item) for item in value]
    return _round(value)
