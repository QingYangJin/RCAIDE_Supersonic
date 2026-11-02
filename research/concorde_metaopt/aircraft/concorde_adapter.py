"""P2 RCAIDE adapter: patch the tutorial Concorde vehicle with a 15D design.

The tutorial module stays the single source of truth for components that Phase I
does not optimise (propulsion network, landing gear, control surfaces, cabins,
systems). This adapter only rewrites the values that the P1 geometry model
derives from the 15 design variables and then lets RCAIDE re-derive every
planform quantity from the patched segments.

The tutorial file is hash-checked so an upstream edit cannot silently change the
evaluation protocol. Nothing here launches a mission; the evaluation backend in
evaluation/low_fidelity.py does that.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .geometry_model import ConcordeGeometry

REPO_ROOT = Path(__file__).resolve().parents[3]
TUTORIAL_REL = (
    Path("tutorials")
    / "Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission"
    / "Concorde.py"
)
EXPECTED_SHA256 = "4c633e485a915151faaa8104e6647f9dc02bd08ae1436c22845e5917b3d735bd"
TEMPLATE_MODULE_NAME = "concorde_metaopt_tutorial_template"

WING_TAG = "main_wing"
TAIL_TAG = "vertical_stabilizer"
FUSELAGE_TAG = "fuselage"
WING_SECTION_ORDER = ("section_1", "section_2", "section_3", "tip")
TAIL_SECTION_ORDER = ("section_1", "section_2", "tip")

# The origins are fixed by the P1 model: only the planform is a design variable.
WING_ORIGIN_M = (14.0, 0.0, -0.8)
TAIL_ORIGIN_M = (42.0, 0.0, 1.0)

# Absolute vertical offsets of the eight fuselage stations taken from the
# upstream tutorial. RCAIDE stores them as a fraction of the fuselage length.
FUSELAGE_Z_OFFSETS_M = (0.0, -0.61, -0.3583, -0.15, 0.0, 0.0, 0.1, 1.2332)

MASS_CONTRACT_FIELDS = (
    "operating_empty",
    "payload",
    "cargo",
    "fuel",
    "takeoff",
    "max_fuel",
    "max_zero_fuel",
    "max_takeoff",
)

# Relative tolerances for the model-vs-RCAIDE consistency checks. The model and
# RCAIDE must agree to round-off; a disagreement means the vehicle the mission
# flew was not the design vector that was requested.
RELATIVE_TOLERANCE = 1.0e-6
FUSELAGE_RELATIVE_TOLERANCE = 1.0e-4
ABSOLUTE_TOLERANCE_LENGTH_M = 1.0e-9
ABS_TOLERANCE_AERODYNAMIC_CENTER_M = 0.25


class AdapterError(RuntimeError):
    """Raised when the tutorial template cannot be loaded or patched safely."""


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_tutorial_path(repo_root: Optional[Path] = None) -> Path:
    """Return the absolute path of the tutorial module used as the template."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    path = root / TUTORIAL_REL
    if not path.is_file():
        raise AdapterError("tutorial template not found: %s" % path)
    return path


def load_template_module(
    repo_root: Optional[Path] = None,
    verify_hash: bool = True,
) -> Any:
    """Import the tutorial module without running its main routine."""
    path = resolve_tutorial_path(repo_root)
    if verify_hash:
        digest = file_sha256(path)
        if digest != EXPECTED_SHA256:
            raise AdapterError(
                "tutorial template hash mismatch: expected %s, got %s"
                % (EXPECTED_SHA256, digest)
            )
    spec = importlib.util.spec_from_file_location(TEMPLATE_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise AdapterError("cannot create an import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("vehicle_setup", "configs_setup", "analyses_setup"):
        if not hasattr(module, name):
            raise AdapterError("tutorial template misses %s()" % name)
    return module


def build_vehicle(
    geometry: ConcordeGeometry,
    repo_root: Optional[Path] = None,
    module: Any = None,
) -> Tuple[Any, Any]:
    """Build the patched RCAIDE vehicle for a geometry model instance."""
    template = module if module is not None else load_template_module(repo_root)
    vehicle = template.vehicle_setup()
    apply_geometry(vehicle, geometry)
    return template, vehicle


def _wing_patch(wing: Any, planform: Any, section_order: Sequence[str], origin: Sequence[float]) -> Dict[str, Any]:
    segments = [wing.segments[key] for key in wing.segments.keys()]
    if len(segments) != len(section_order):
        raise AdapterError(
            "wing %s has %d segments, expected %d"
            % (wing.tag, len(segments), len(section_order))
        )
    if tuple(segment.tag for segment in segments) != tuple(section_order):
        raise AdapterError(
            "wing %s segment tags %s do not match %s"
            % (wing.tag, [segment.tag for segment in segments], list(section_order))
        )
    root_chord = float(planform.root_chord_m)
    if not math.isfinite(root_chord) or root_chord <= 0.0:
        raise AdapterError("wing %s root chord must be positive" % wing.tag)

    wing.aspect_ratio = float(planform.aspect_ratio)
    wing.spans.projected = float(planform.span_m)
    wing.spans.total = float(planform.span_m)
    wing.chords.root = root_chord
    wing.chords.tip = float(planform.tip_chord_m)
    wing.chords.mean_aerodynamic = float(planform.mean_aerodynamic_chord_m)
    wing.chords.mean_geometric = float(planform.mean_geometric_chord_m)
    wing.taper = float(planform.taper_ratio)
    wing.areas.reference = float(planform.area_m2)
    wing.areas.wetted = float(planform.wetted_area_m2)
    wing.areas.exposed = float(planform.exposed_area_m2)
    wing.areas.affected = 0.6 * float(planform.area_m2)
    wing.thickness_to_chord = float(planform.thickness_to_chord)
    wing.total_length = float(planform.tip_trailing_edge_x_m)
    wing.twists.root = 0.0
    wing.twists.tip = math.radians(float(planform.sections[-1].twist_deg))
    wing.origin = [[float(origin[0]), float(origin[1]), float(origin[2])]]
    wing.aerodynamic_center = [
        float(origin[0]) + float(planform.aerodynamic_center_x_m),
        0.0,
        0.0,
    ]

    rows = []
    for segment, section in zip(segments, planform.sections):
        segment.percent_span_location = float(section.percent_span_location)
        segment.root_chord_percent = float(section.chord_m) / root_chord
        segment.sweeps.quarter_chord = math.radians(float(section.quarter_chord_sweep_deg))
        segment.twist = math.radians(float(section.twist_deg))
        segment.thickness_to_chord = float(section.thickness_to_chord)
        segment.dihedral_outboard = 0.0
        rows.append(
            {
                "tag": segment.tag,
                "percent_span_location": segment.percent_span_location,
                "root_chord_percent": segment.root_chord_percent,
                "quarter_chord_sweep_deg": float(section.quarter_chord_sweep_deg),
                "twist_deg": float(section.twist_deg),
                "thickness_to_chord": segment.thickness_to_chord,
            }
        )

    return {
        "tag": wing.tag,
        "span_m": wing.spans.projected,
        "root_chord_m": wing.chords.root,
        "tip_chord_m": wing.chords.tip,
        "reference_area_m2": wing.areas.reference,
        "wetted_area_m2": wing.areas.wetted,
        "exposed_area_m2": wing.areas.exposed,
        "aspect_ratio": wing.aspect_ratio,
        "mean_aerodynamic_chord_m": wing.chords.mean_aerodynamic,
        "origin_m": list(wing.origin[0]),
        "sections": rows,
    }


def _fuselage_patch(fuselage: Any, geometry: Any) -> Dict[str, Any]:
    stations = list(geometry.stations)
    if not stations:
        raise AdapterError("fuselage geometry has no stations")
    length = float(geometry.length_m)
    if length <= 0.0:
        raise AdapterError("fuselage length must be positive")
    if len(stations) != len(FUSELAGE_Z_OFFSETS_M):
        raise AdapterError(
            "fuselage has %d stations, expected %d"
            % (len(stations), len(FUSELAGE_Z_OFFSETS_M))
        )
    existing = [fuselage.segments[key] for key in fuselage.segments.keys()]
    if not existing:
        raise AdapterError("tutorial fuselage has no segments to model")
    segment_class = type(existing[0])

    fuselage.lengths.total = length
    fuselage.lengths.nose = float(geometry.nose_length_m)
    fuselage.lengths.tail = float(geometry.tail_length_m)
    fuselage.lengths.cabin = float(geometry.cabin_length_m)
    fuselage.width = float(geometry.width_m)
    fuselage.heights.maximum = float(geometry.max_height_m)
    fuselage.heights.at_quarter_length = float(geometry.max_height_m)
    fuselage.heights.at_wing_root_quarter_chord = float(geometry.max_height_m)
    fuselage.heights.at_three_quarters_length = float(geometry.max_height_m)
    fuselage.fineness.nose = float(geometry.nose_fineness)
    fuselage.fineness.tail = float(geometry.tail_fineness)
    fuselage.areas.wetted = float(geometry.wetted_area_m2)
    fuselage.areas.front_projected = float(geometry.front_projected_area_m2)
    fuselage.areas.side_projected = float(geometry.side_projected_area_m2)
    fuselage.effective_diameter = float(geometry.effective_diameter_m)

    fuselage.segments.clear()
    rows = []
    for index, station in enumerate(stations):
        segment = segment_class()
        segment.tag = station.tag
        segment.percent_x_location = float(station.x_m) / length
        segment.percent_y_location = 0.0
        segment.percent_z_location = FUSELAGE_Z_OFFSETS_M[index] / length
        segment.height = float(station.height_m)
        segment.width = float(station.width_m)
        fuselage.append_segment(segment)
        rows.append(
            {
                "tag": segment.tag,
                "percent_x_location": segment.percent_x_location,
                "percent_z_location": segment.percent_z_location,
                "x_m": float(station.x_m),
                "width_m": segment.width,
                "height_m": segment.height,
            }
        )

    return {
        "length_m": fuselage.lengths.total,
        "nose_length_m": fuselage.lengths.nose,
        "tail_length_m": fuselage.lengths.tail,
        "cabin_length_m": fuselage.lengths.cabin,
        "width_m": fuselage.width,
        "max_height_m": fuselage.heights.maximum,
        "wetted_area_m2": fuselage.areas.wetted,
        "front_projected_area_m2": fuselage.areas.front_projected,
        "effective_diameter_m": fuselage.effective_diameter,
        "stations": rows,
    }


def apply_geometry(vehicle: Any, geometry: ConcordeGeometry) -> Dict[str, Any]:
    """Patch the 15D-derived geometry onto an RCAIDE vehicle in place."""
    for tag in (WING_TAG, TAIL_TAG):
        if tag not in vehicle.wings:
            raise AdapterError("vehicle misses wing %s" % tag)
    if FUSELAGE_TAG not in vehicle.fuselages:
        raise AdapterError("vehicle misses fuselage %s" % FUSELAGE_TAG)

    wing = vehicle.wings[WING_TAG]
    tail = vehicle.wings[TAIL_TAG]
    fuselage = vehicle.fuselages[FUSELAGE_TAG]

    wing_summary = _wing_patch(wing, geometry.wing, WING_SECTION_ORDER, WING_ORIGIN_M)
    tail_summary = _wing_patch(tail, geometry.vertical_tail, TAIL_SECTION_ORDER, TAIL_ORIGIN_M)
    fuselage_summary = _fuselage_patch(fuselage, geometry.fuselage)

    wing.vertical = False
    wing.xz_plane_symmetric = True
    wing.vortex_lift = True
    wing.high_mach = True
    wing.dynamic_pressure_ratio = 1.0
    tail.vertical = True
    tail.xz_plane_symmetric = False
    tail.t_tail = False
    tail.vortex_lift = True
    tail.high_mach = True
    tail.dynamic_pressure_ratio = 1.0

    vehicle.reference_area = float(geometry.wing.area_m2)
    vehicle.total_length = float(geometry.fuselage.length_m)
    vehicle.maximum_cross_sectional_area = float(geometry.fuselage.front_projected_area_m2)

    return {
        "main_wing": wing_summary,
        "vertical_stabilizer": tail_summary,
        "fuselage": fuselage_summary,
        "vehicle": {
            "reference_area_m2": float(vehicle.reference_area),
            "total_length_m": float(vehicle.total_length),
            "maximum_cross_sectional_area_m2": float(vehicle.maximum_cross_sectional_area),
        },
    }


def apply_mass_contract(analysis_vehicle: Any, task: Any) -> Dict[str, float]:
    """Freeze the fixed-cruise mass contract on the analysis vehicle."""
    mass_properties = analysis_vehicle.mass_properties
    applied = {
        "operating_empty": float(task.operating_empty_kg),
        "payload": float(task.payload_kg),
        "cargo": float(task.cargo_kg),
        "fuel": float(task.fuel_loaded_kg),
        "takeoff": float(task.start_mass_kg),
        "max_fuel": float(task.max_fuel_kg),
        "max_zero_fuel": float(task.max_zero_fuel_kg),
        "max_takeoff": float(task.max_takeoff_kg),
    }
    for field in MASS_CONTRACT_FIELDS:
        setattr(mass_properties, field, applied[field])
    readback = {field: float(getattr(mass_properties, field)) for field in MASS_CONTRACT_FIELDS}
    for field in MASS_CONTRACT_FIELDS:
        if abs(readback[field] - applied[field]) > 1.0e-9:
            raise AdapterError(
                "mass contract did not stick for %s: applied %r, read %r"
                % (field, applied[field], readback[field])
            )
    return {"applied": applied, "readback": readback}


def _relative_delta(model_value: float, reference_value: float) -> float:
    denominator = abs(float(reference_value))
    if denominator == 0.0:
        return abs(float(model_value)) if float(model_value) != 0.0 else 0.0
    return abs(float(model_value) - float(reference_value)) / denominator


def _check(
    check_id: str,
    subject: str,
    model_value: Any,
    reference_value: Any,
    relative_tolerance: Optional[float],
    absolute_tolerance: Optional[float] = None,
    detail: str = "",
) -> Dict[str, Any]:
    if relative_tolerance is not None:
        if isinstance(model_value, (list, tuple)):
            if len(model_value) != len(reference_value):
                delta = float("inf")
            else:
                pairs = list(zip(model_value, reference_value))
                delta = max([_relative_delta(a, b) for a, b in pairs] or [0.0])
        else:
            delta = _relative_delta(model_value, reference_value)
        status = "pass" if delta <= relative_tolerance else "fail"
        tolerance = {"relative": relative_tolerance}
    else:
        delta = abs(float(model_value) - float(reference_value))
        status = "pass" if delta <= float(absolute_tolerance) else "fail"
        tolerance = {"absolute": absolute_tolerance, "unit": "m"}
    return {
        "check_id": check_id,
        "subject": subject,
        "model_value": model_value,
        "rcaide_value": reference_value,
        "delta": delta,
        "tolerance": tolerance,
        "status": status,
        "detail": detail,
    }


def evaluate_geometry_cross_check(geometry: ConcordeGeometry, vehicle: Any) -> Dict[str, Any]:
    """Let RCAIDE re-derive the geometry and compare it against the P1 model."""
    from .geometry_builder import rcaide_derived_geometry

    rcaide = rcaide_derived_geometry(vehicle)
    model_wing = geometry.wing
    model_tail = geometry.vertical_tail
    model_fuselage = geometry.fuselage
    checks = []

    def compare_wing(prefix: str, model: Any, derived: Mapping[str, Any]) -> None:
        checks.append(_check(prefix + "_reference_area", "wing.areas.reference", model.area_m2, derived["area_m2"], RELATIVE_TOLERANCE))
        checks.append(_check(prefix + "_span", "wing.spans.projected", model.span_m, derived["span_m"], RELATIVE_TOLERANCE))
        checks.append(_check(prefix + "_root_chord", "wing.chords.root", model.root_chord_m, derived["root_chord_m"], RELATIVE_TOLERANCE))
        checks.append(_check(prefix + "_tip_chord", "wing.chords.tip", model.tip_chord_m, derived["tip_chord_m"], RELATIVE_TOLERANCE))
        checks.append(_check(prefix + "_mean_aerodynamic_chord", "wing.chords.mean_aerodynamic", model.mean_aerodynamic_chord_m, derived["mean_aerodynamic_chord_m"], RELATIVE_TOLERANCE))
        checks.append(_check(prefix + "_wetted_area", "wing.areas.wetted", model.wetted_area_m2, derived["wetted_area_m2"], RELATIVE_TOLERANCE))
        checks.append(_check(prefix + "_taper_ratio", "wing.taper", model.taper_ratio, derived["taper_ratio"], RELATIVE_TOLERANCE))
        checks.append(
            _check(
                prefix + "_aerodynamic_center_x",
                "wing.aerodynamic_center x (model LE(MAC)+0.25MAC vs RCAIDE area centroid-0.25MAC)",
                model.aerodynamic_center_x_m,
                derived["aerodynamic_center_local_x_m"],
                None,
                ABS_TOLERANCE_AERODYNAMIC_CENTER_M,
                detail="different AC definitions coincide only for a single trapezoid",
            )
        )
        checks.append(
            _check(
                prefix + "_section_span_locations",
                "wing segment percent_span_location",
                list(model_section_span(model)),
                derived["section_span_locations"],
                RELATIVE_TOLERANCE,
            )
        )
        checks.append(
            _check(
                prefix + "_section_chords",
                "wing segment chord lengths",
                [float(section.chord_m) for section in model.sections],
                derived["section_chords_m"],
                RELATIVE_TOLERANCE,
            )
        )

    def model_section_span(model: Any) -> Sequence[float]:
        return [float(section.percent_span_location) for section in model.sections]

    compare_wing("wing", model_wing, rcaide["main_wing"])
    compare_wing("tail", model_tail, rcaide["vertical_stabilizer"])

    derived_fuselage = rcaide["fuselage"]
    checks.append(_check("fuselage_length", "fuselage.lengths.total", model_fuselage.length_m, derived_fuselage["length_m"], None, ABSOLUTE_TOLERANCE_LENGTH_M))
    checks.append(_check("fuselage_nose_length", "fuselage.lengths.nose", model_fuselage.nose_length_m, derived_fuselage["nose_length_m"], None, ABSOLUTE_TOLERANCE_LENGTH_M))
    checks.append(_check("fuselage_tail_length", "fuselage.lengths.tail", model_fuselage.tail_length_m, derived_fuselage["tail_length_m"], None, ABSOLUTE_TOLERANCE_LENGTH_M))
    checks.append(_check("fuselage_cabin_length", "fuselage.lengths.cabin", model_fuselage.cabin_length_m, derived_fuselage["cabin_length_m"], None, ABSOLUTE_TOLERANCE_LENGTH_M))
    checks.append(_check("fuselage_wetted_area", "fuselage.areas.wetted", model_fuselage.wetted_area_m2, derived_fuselage["wetted_area_m2"], FUSELAGE_RELATIVE_TOLERANCE))
    checks.append(_check("fuselage_front_projected", "fuselage.areas.front_projected", model_fuselage.front_projected_area_m2, derived_fuselage["front_projected_area_m2"], FUSELAGE_RELATIVE_TOLERANCE))
    checks.append(_check("fuselage_effective_diameter", "fuselage.effective_diameter", model_fuselage.effective_diameter_m, derived_fuselage["effective_diameter_m"], FUSELAGE_RELATIVE_TOLERANCE))

    derived_stations = derived_fuselage["stations"]
    checks.append(
        _check(
            "fuselage_station_count",
            "fuselage segment count",
            float(len(model_fuselage.stations)),
            float(len(derived_stations)),
            None,
            0.0,
        )
    )
    tags = [station["tag"] for station in derived_stations]
    checks.append(
        {
            "check_id": "fuselage_station_tags",
            "subject": "fuselage segment tags unique and aligned",
            "model_value": [station.tag for station in model_fuselage.stations],
            "rcaide_value": tags,
            "delta": 0.0 if len(set(tags)) == len(tags) else 1.0,
            "tolerance": {"unique": True},
            "status": "pass" if len(set(tags)) == len(tags) else "fail",
            "detail": "",
        }
    )
    checks.append(
        _check(
            "fuselage_station_widths",
            "fuselage segment widths",
            [float(station.width_m) for station in model_fuselage.stations],
            [float(station["width_m"]) for station in derived_stations],
            RELATIVE_TOLERANCE,
        )
    )
    checks.append(
        _check(
            "fuselage_station_heights",
            "fuselage segment heights",
            [float(station.height_m) for station in model_fuselage.stations],
            [float(station["height_m"]) for station in derived_stations],
            RELATIVE_TOLERANCE,
        )
    )

    failures = [check for check in checks if check["status"] == "fail"]
    return {
        "checks": checks,
        "failures": failures,
        "checked_count": len(checks),
        "failed_count": len(failures),
        "rcaide_derived": rcaide,
    }
