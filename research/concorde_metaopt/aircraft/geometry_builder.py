"""RCAIDE adapter for the Concorde 15D geometry model (P1).

The dependency-free model in geometry_model.py owns the parameterization.  This
module mirrors it into real RCAIDE component objects, assembles a geometry-only
Vehicle (wing, vertical stabilizer, fuselage, landing gear; the powertrain is a
P2 concern) and then re-derives planform quantities with RCAIDE's own
wing_planform / segment_properties / fuselage_planform routines.

The derived values returned by rcaide_derived_geometry() are what the P1 checks
compare against the model.  A mismatch is a finding, not something to overwrite:
RCAIDE's airfoil import replaces the declared segment thickness-to-chord with
the thickness read from the coordinate file, which is exactly the kind of
inconsistency P1 must surface before the design space is frozen.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .design_space import DesignSpace, load_design_space
from .geometry_model import (
    PASSENGER_COUNT,
    SOURCE_BASELINE,
    TAIL_ORIGIN_X_M,
    TAIL_THICKNESS_TO_CHORD,
    WING_ORIGIN_X_M,
    WING_THICKNESS_TO_CHORD,
    ConcordeGeometry,
    GeometryError,
    build_geometry,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AIRFOIL_DIR = REPO_ROOT / "tutorials" / "Airfoils_and_Polars"
WING_AIRFOIL_FILE = "NACA65_203.txt"
TAIL_AIRFOIL_FILE = "supersonic_tail.txt"

# Upstream landing gear / fuselage layout values that are not design variables.
_MAIN_GEAR = {
    "origin": [[17.0, 0.0, -11.0]],
    "tire_diameter": 47.0,
    "rim_diameter": 22.1,
    "tire_width": 15.75,
    "strut_length": 12.0,
    "wheels": 8,
    "number_of_gear_types_in_tandem": 2,
    "number_of_wheels_in_gear_type": 2,
    "xz_plane_symmetric": True,
}
_NOSE_GEAR = {
    "origin": [[35.0, 0.0, -11.0]],
    "tire_diameter": 31.0,
    "rim_diameter": 14.0,
    "tire_width": 10.75,
    "strut_length": 12.0,
    "wheels": 2,
}
_CONTROL_SURFACES = (
    ("Slat", "slat", 0.2, 0.963, 0.075, None),
    ("Flap", "flap", 0.42, 0.62, 0.14, "single_slotted"),
    ("Aileron", "aileron", 0.62, 0.83, 0.22, None),
    ("Elevator", "elevator", 0.08, 0.24, 0.1, None),
)
_FUSELAGE_Z_FRACTIONS = {
    0: -0.61 / 61.66,
    1: -0.3583 / 61.66,
    2: -0.15 / 61.66,
    5: 0.0,
    6: 0.1 / 61.66,
}
# Upstream vehicle-level constants that P2's TaskSpec must re-audit; they are
# kept here so the P1 vehicle matches the tutorial's intended configuration.
_UPSTREAM_MAX_CROSS_SECTION_M2 = 13.9
_UPSTREAM_DIFFERENTIAL_PRESSURE_PA = 7.4e4


class GeometryBuilderError(RuntimeError):
    """Raised when the RCAIDE adapter cannot build or re-derive the geometry."""


def build_geometry_from_design_space(
    design_space: Optional[DesignSpace] = None,
    physical: Optional[Sequence[float]] = None,
) -> ConcordeGeometry:
    """Validate a physical design vector against the config and build the model."""
    space = design_space if design_space is not None else load_design_space()
    names = list(space.names)
    if physical is None:
        vector = list(space.baseline_vector())
    else:
        vector = [float(value) for value in physical]
        if len(vector) != len(names):
            raise GeometryError("expected %d physical values, got %d" % (len(names), len(vector)))
    violations = space.check_physical({name: value for name, value in zip(names, vector)})
    if violations:
        raise GeometryError("; ".join(str(item) for item in violations))
    return build_geometry(names, vector)


def build_geometry_vehicle(
    geometry: ConcordeGeometry,
    airfoil_dir: Optional[Path] = None,
) -> Any:
    """Build a geometry-only RCAIDE Vehicle that mirrors the model."""
    RCAIDE = _import_rcaide()
    directory = _resolve_airfoil_dir(airfoil_dir)
    vehicle = RCAIDE.Vehicle()
    vehicle.tag = "Concorde_metaopt"
    vehicle.mass_properties.max_takeoff = 185000.0
    vehicle.mass_properties.operating_empty = 78700.0
    vehicle.mass_properties.takeoff = 185000.0
    vehicle.mass_properties.cargo = 1000.0
    vehicle.mass_properties.max_zero_fuel = 92000.0
    vehicle.mass_properties.max_fuel = 95680.0
    vehicle.flight_envelope.design_cruise_altitude = 40000.0 * RCAIDE.Framework.Core.Units.feet
    vehicle.flight_envelope.design_dynamic_pressure = 55169.0
    vehicle.flight_envelope.design_mach_number = 2.05
    vehicle.flight_envelope.ultimate_load = 5.7
    vehicle.flight_envelope.limit_load = 3.8
    vehicle.flight_envelope.positive_limit_load = 2.5
    vehicle.flight_envelope.design_range = 4488.0 * RCAIDE.Framework.Core.Units.nmi
    vehicle.reference_area = geometry.wing.area_m2
    vehicle.number_of_passengers = PASSENGER_COUNT
    vehicle.systems.control = "fully powered"
    vehicle.systems.accessories = "sst"
    vehicle.maximum_cross_sectional_area = _UPSTREAM_MAX_CROSS_SECTION_M2
    vehicle.total_length = geometry.fuselage.length_m
    vehicle.design_mach_number = 2.02
    vehicle.design_range = 4505.0 * RCAIDE.Framework.Core.Units.miles
    vehicle.design_cruise_alt = 60000.0 * RCAIDE.Framework.Core.Units.ft

    _append_landing_gear(vehicle, RCAIDE)
    vehicle.append_component(_build_main_wing(geometry, RCAIDE, directory))
    vehicle.append_component(_build_vertical_tail(geometry, RCAIDE, directory))
    vehicle.append_component(_build_fuselage(geometry, RCAIDE))
    return vehicle


def rcaide_derived_geometry(vehicle: Any) -> Dict[str, Any]:
    """Run RCAIDE planform routines on the built vehicle and return the values."""
    from RCAIDE.Library.Methods.Geometry.Planform.wing_planform import wing_planform
    from RCAIDE.Library.Methods.Geometry.Planform.fuselage_planform import fuselage_planform

    wing = vehicle.wings["main_wing"]
    tail = vehicle.wings["vertical_stabilizer"]
    fuselage = vehicle.fuselages["fuselage"]
    wing_planform(wing)
    wing_planform(tail)
    fuselage_planform(fuselage)
    return {
        "main_wing": _planform_values(wing),
        "vertical_stabilizer": _planform_values(tail),
        "fuselage": {
            "length_m": float(fuselage.lengths.total),
            "nose_length_m": float(fuselage.lengths.nose),
            "tail_length_m": float(fuselage.lengths.tail),
            "cabin_length_m": float(fuselage.lengths.cabin),
            "width_m": float(fuselage.width),
            "max_height_m": float(fuselage.heights.maximum),
            "wetted_area_m2": float(fuselage.areas.wetted),
            "front_projected_area_m2": float(fuselage.areas.front_projected),
            "side_projected_area_m2": float(fuselage.areas.side_projected),
            "effective_diameter_m": float(fuselage.effective_diameter),
            "stations": [
                {
                    "tag": segment.tag,
                    "percent_x_location": float(segment.percent_x_location),
                    "x_m": float(segment.percent_x_location) * float(fuselage.lengths.total),
                    "width_m": float(segment.width),
                    "height_m": float(segment.height),
                }
                for segment in [fuselage.segments[key] for key in fuselage.segments.keys()]
            ],
        },
    }


def _planform_values(wing: Any) -> Dict[str, Any]:
    segments = [wing.segments[key] for key in wing.segments.keys()]
    return {
        "tag": wing.tag,
        "area_m2": float(wing.areas.reference),
        "projected_area_m2": float(wing.areas.projected),
        "wetted_area_m2": float(wing.areas.wetted),
        "exposed_area_m2": float(sum(float(segment.areas.exposed) for segment in segments)),
        "span_m": float(wing.spans.projected),
        "aspect_ratio": float(wing.aspect_ratio),
        "root_chord_m": float(wing.chords.root),
        "tip_chord_m": float(wing.chords.tip),
        "mean_aerodynamic_chord_m": float(wing.chords.mean_aerodynamic),
        "mean_geometric_chord_m": float(wing.chords.mean_geometric),
        "taper_ratio": float(wing.taper),
        "tip_trailing_edge_x_m": float(wing.total_length),
        "aerodynamic_center_local_x_m": float(wing.aerodynamic_center[0]),
        "leading_edge_mac_x_m": float(getattr(wing, "LEMAC", float("nan"))),
        "section_span_locations": [float(segment.percent_span_location) for segment in segments],
        "section_chords_m": [float(wing.chords.root) * float(segment.root_chord_percent) for segment in segments],
        "section_quarter_chord_sweeps_deg": [
            math.degrees(float(segment.sweeps.quarter_chord)) for segment in segments
        ],
        "section_thickness_to_chord": [float(segment.thickness_to_chord) for segment in segments],
        "segment_wetted_area_m2": [float(segment.areas.wetted) for segment in segments],
        "segment_exposed_area_m2": [float(segment.areas.exposed) for segment in segments],
    }


def _build_main_wing(geometry: ConcordeGeometry, RCAIDE: Any, airfoil_dir: Path) -> Any:
    wing = RCAIDE.Library.Components.Wings.Main_Wing()
    planform = geometry.wing
    wing.tag = "main_wing"
    wing.aspect_ratio = planform.aspect_ratio
    wing.thickness_to_chord = WING_THICKNESS_TO_CHORD
    wing.taper = planform.taper_ratio
    wing.spans.projected = planform.span_m
    wing.chords.root = planform.root_chord_m
    wing.chords.tip = planform.tip_chord_m
    wing.chords.mean_aerodynamic = planform.mean_aerodynamic_chord_m
    wing.total_length = planform.tip_trailing_edge_x_m
    wing.areas.reference = planform.area_m2
    wing.areas.wetted = planform.wetted_area_m2
    wing.areas.exposed = planform.exposed_area_m2
    wing.areas.affected = 0.6 * planform.area_m2
    wing.twists.root = 0.0
    wing.twists.tip = math.radians(planform.sections[-1].twist_deg)
    wing.origin = [[WING_ORIGIN_X_M, 0.0, -0.8]]
    wing.aerodynamic_center = [WING_ORIGIN_X_M + planform.aerodynamic_center_x_m, 0.0, 0.0]
    wing.vertical = False
    wing.xz_plane_symmetric = True
    wing.vortex_lift = True
    wing.high_mach = True
    wing.dynamic_pressure_ratio = 1.0

    airfoil_file = airfoil_dir / WING_AIRFOIL_FILE
    for section in planform.sections:
        segment = RCAIDE.Library.Components.Wings.Segments.Segment()
        segment.tag = section.tag
        segment.percent_span_location = section.percent_span_location
        segment.twist = math.radians(section.twist_deg)
        segment.root_chord_percent = section.chord_m / planform.root_chord_m
        segment.dihedral_outboard = 0.0
        segment.sweeps.quarter_chord = math.radians(section.quarter_chord_sweep_deg)
        segment.thickness_to_chord = section.thickness_to_chord
        segment.append_airfoil(_airfoil(RCAIDE, airfoil_file))
        wing.append_segment(segment)
    _append_control_surfaces(wing, RCAIDE)
    return wing


def _build_vertical_tail(geometry: ConcordeGeometry, RCAIDE: Any, airfoil_dir: Path) -> Any:
    wing = RCAIDE.Library.Components.Wings.Vertical_Tail()
    planform = geometry.vertical_tail
    wing.tag = "vertical_stabilizer"
    wing.aspect_ratio = planform.aspect_ratio
    wing.thickness_to_chord = TAIL_THICKNESS_TO_CHORD
    wing.taper = planform.taper_ratio
    wing.spans.projected = planform.span_m
    wing.chords.root = planform.root_chord_m
    wing.chords.tip = planform.tip_chord_m
    wing.chords.mean_aerodynamic = planform.mean_aerodynamic_chord_m
    wing.total_length = planform.tip_trailing_edge_x_m
    wing.areas.reference = planform.area_m2
    wing.areas.wetted = planform.wetted_area_m2
    wing.areas.exposed = planform.exposed_area_m2
    wing.areas.affected = planform.area_m2
    wing.twists.root = 0.0
    wing.twists.tip = 0.0
    wing.origin = [[TAIL_ORIGIN_X_M, 0.0, 1.0]]
    wing.aerodynamic_center = [TAIL_ORIGIN_X_M + planform.aerodynamic_center_x_m, 0.0, 0.0]
    wing.vertical = True
    wing.xz_plane_symmetric = False
    wing.t_tail = False
    wing.high_mach = True
    wing.dynamic_pressure_ratio = 1.0

    airfoil_file = airfoil_dir / TAIL_AIRFOIL_FILE
    for section in planform.sections:
        segment = RCAIDE.Library.Components.Wings.Segments.Segment()
        segment.tag = section.tag
        segment.percent_span_location = section.percent_span_location
        segment.twist = math.radians(section.twist_deg)
        segment.root_chord_percent = section.chord_m / planform.root_chord_m
        segment.dihedral_outboard = 0.0
        segment.sweeps.quarter_chord = math.radians(section.quarter_chord_sweep_deg)
        segment.thickness_to_chord = section.thickness_to_chord
        segment.append_airfoil(_airfoil(RCAIDE, airfoil_file))
        wing.append_segment(segment)
    return wing


def _build_fuselage(geometry: ConcordeGeometry, RCAIDE: Any) -> Any:
    fuselage_geometry = geometry.fuselage
    fuselage = RCAIDE.Library.Components.Fuselages.Fuselage()
    fuselage.tag = "fuselage"
    fuselage.seats_abreast = 4
    fuselage.seat_pitch = 38.0 * RCAIDE.Framework.Core.Units.inches
    fuselage.fineness.nose = fuselage_geometry.nose_fineness
    fuselage.fineness.tail = fuselage_geometry.tail_fineness
    fuselage.lengths.total = fuselage_geometry.length_m
    fuselage.width = fuselage_geometry.width_m
    fuselage.heights.maximum = fuselage_geometry.max_height_m
    fuselage.heights.at_quarter_length = fuselage_geometry.max_height_m
    fuselage.heights.at_wing_root_quarter_chord = fuselage_geometry.max_height_m
    fuselage.heights.at_three_quarters_length = fuselage_geometry.max_height_m
    fuselage.supersonic = True
    fuselage.areas.wetted = fuselage_geometry.wetted_area_m2
    fuselage.areas.front_projected = fuselage_geometry.front_projected_area_m2
    fuselage.effective_diameter = fuselage_geometry.effective_diameter_m
    fuselage.differential_pressure = _UPSTREAM_DIFFERENTIAL_PRESSURE_PA
    for index, station in enumerate(fuselage_geometry.stations):
        segment = RCAIDE.Library.Components.Fuselages.Segments.Segment()
        segment.tag = station.tag
        segment.percent_x_location = station.x_m / fuselage_geometry.length_m
        segment.percent_z_location = _FUSELAGE_Z_FRACTIONS.get(index, 0.0)
        segment.height = station.height_m
        segment.width = station.width_m
        fuselage.append_segment(segment)
    return fuselage


def _append_landing_gear(vehicle: Any, RCAIDE: Any) -> None:
    Units = RCAIDE.Framework.Core.Units
    main_gear = RCAIDE.Library.Components.Landing_Gear.Main_Landing_Gear()
    for key, value in _MAIN_GEAR.items():
        setattr(main_gear, key, value)
    main_gear.tire_diameter = _MAIN_GEAR["tire_diameter"] * Units.inches
    main_gear.rim_diameter = _MAIN_GEAR["rim_diameter"] * Units.inches
    main_gear.tire_width = _MAIN_GEAR["tire_width"] * Units.inches
    main_gear.strut_length = _MAIN_GEAR["strut_length"] * Units.ft
    vehicle.append_component(main_gear)

    nose_gear = RCAIDE.Library.Components.Landing_Gear.Nose_Landing_Gear()
    for key, value in _NOSE_GEAR.items():
        setattr(nose_gear, key, value)
    nose_gear.tire_diameter = _NOSE_GEAR["tire_diameter"] * Units.inches
    nose_gear.rim_diameter = _NOSE_GEAR["rim_diameter"] * Units.inches
    nose_gear.tire_width = _NOSE_GEAR["tire_width"] * Units.inches
    nose_gear.strut_length = _NOSE_GEAR["strut_length"] * Units.ft
    vehicle.append_component(nose_gear)


def _append_control_surfaces(wing: Any, RCAIDE: Any) -> None:
    Units = RCAIDE.Framework.Core.Units
    for class_name, tag, span_start, span_end, chord_fraction, configuration in _CONTROL_SURFACES:
        control = getattr(RCAIDE.Library.Components.Wings.Control_Surfaces, class_name)()
        control.tag = tag
        control.span_fraction_start = span_start
        control.span_fraction_end = span_end
        control.deflection = 0.0 * Units.deg
        control.chord_fraction = chord_fraction
        if configuration is not None:
            control.configuration_type = configuration
        wing.append_control_surface(control)


def _airfoil(RCAIDE: Any, coordinate_file: Path) -> Any:
    airfoil = RCAIDE.Library.Components.Airfoils.Airfoil()
    airfoil.coordinate_file = str(coordinate_file)
    return airfoil


def _resolve_airfoil_dir(airfoil_dir: Optional[Path]) -> Path:
    directory = Path(airfoil_dir) if airfoil_dir is not None else DEFAULT_AIRFOIL_DIR
    missing = [name for name in (WING_AIRFOIL_FILE, TAIL_AIRFOIL_FILE) if not (directory / name).is_file()]
    if missing:
        raise GeometryBuilderError(
            "airfoil files missing in %s: %s" % (directory, ", ".join(missing))
        )
    return directory


def _import_rcaide() -> Any:
    try:
        import RCAIDE
    except Exception as exc:
        raise GeometryBuilderError("RCAIDE is not importable: %s" % exc)
    return RCAIDE
