"""Design-space contract for the Concorde fixed-cruise problem.

Two declared variable sets share this loader:

* '15d' (the P1 history, configs/design_space_15d.yaml):
  W01-W10 + V01-V02 + F01-F03.  The order and identifiers are frozen by
  Issue #1; the P1 config stays provisional and is never rewritten by the
  12D work.
* '12d_lifting_surfaces' (decision D-12D-001,
  configs/design_space_12d_lifting_surfaces.yaml):
  W01-W10 + V01-V02 only.  The fuselage is fixed to the owner-approved
  computed geometry (F01-F03 baselines recorded under fixed_variables)
  and is expanded back to the full 15-name vector by DesignSpace.expand
  before any geometry consumer sees it.

The P2/P3 pipeline accepts an explicit design-space config (smoke and DOE
take --design-space-config); a 12D space is expanded to the full 15-name
vector before any geometry consumer sees it, with the fuselage fixed.  The
default remains the 15D set until the owner freezes the 12D bounds.  Physical
values are always stored in SI units as declared by the config; normalisation
is only a view.

The loader intentionally knows nothing about RCAIDE.  It answers three
questions: which variables exist, what their legal ranges are, and whether a
physical design vector is inside the declared box and cross constraints.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from research.concorde_metaopt.config_io import ConfigError, load_config


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "design_space_15d.yaml"

EXPECTED_IDS: Tuple[str, ...] = (
    "W01",
    "W02",
    "W03",
    "W04",
    "W05",
    "W06",
    "W07",
    "W08",
    "W09",
    "W10",
    "V01",
    "V02",
    "F01",
    "F02",
    "F03",
)

EXPECTED_NAMES: Tuple[str, ...] = (
    "wing_area",
    "aspect_ratio",
    "sweep_1",
    "sweep_2",
    "sweep_3",
    "span_location_2",
    "span_location_3",
    "chord_ratio_2",
    "chord_ratio_3",
    "tip_twist",
    "vertical_tail_area",
    "vertical_tail_sweep_delta",
    "fuselage_length",
    "fuselage_fineness",
    "fuselage_height_width_ratio",
)

# Decision D-12D-001: the first-stage supersonic acceptance case freezes the
# fuselage and keeps only the lifting-surface variables.  The 15D order is
# preserved for history; the 12D set is the leading prefix of it.
LIFTING_SURFACE_IDS: Tuple[str, ...] = EXPECTED_IDS[:12]
LIFTING_SURFACE_NAMES: Tuple[str, ...] = EXPECTED_NAMES[:12]
FIXED_FUSELAGE_IDS: Tuple[str, ...] = EXPECTED_IDS[12:]
FIXED_FUSELAGE_NAMES: Tuple[str, ...] = EXPECTED_NAMES[12:]

# The loader rejects any pair not exactly equal to one of these ordered sets.
DESIGN_SETS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...]]] = {
    "15d": (EXPECTED_IDS, EXPECTED_NAMES),
    "12d_lifting_surfaces": (LIFTING_SURFACE_IDS, LIFTING_SURFACE_NAMES),
}

EXPECTED_UNITS: Dict[str, str] = {
    "wing_area": "m^2",
    "aspect_ratio": "dimensionless",
    "sweep_1": "deg",
    "sweep_2": "deg",
    "sweep_3": "deg",
    "span_location_2": "dimensionless",
    "span_location_3": "dimensionless",
    "chord_ratio_2": "dimensionless",
    "chord_ratio_3": "dimensionless",
    "tip_twist": "deg",
    "vertical_tail_area": "m^2",
    "vertical_tail_sweep_delta": "deg",
    "fuselage_length": "m",
    "fuselage_fineness": "dimensionless",
    "fuselage_height_width_ratio": "dimensionless",
}

_POSITIVE_VARIABLES = ("wing_area", "aspect_ratio", "vertical_tail_area", "fuselage_length")
_SWEEP_VARIABLES = ("sweep_1", "sweep_2", "sweep_3")


class DesignSpaceError(ValueError):
    """Raised when a design-space config violates the Phase I contract."""


@dataclass(frozen=True)
class DesignVariable:
    id: str
    name: str
    unit: str
    baseline: float
    lower: float
    upper: float
    scale: float
    target: str

    @property
    def bounds(self) -> Tuple[float, float]:
        return (self.lower, self.upper)

    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper

    def normalize(self, value: float) -> float:
        return (value - self.baseline) / self.scale

    def denormalize(self, normalized: float) -> float:
        return self.baseline + normalized * self.scale

    def to_unit_interval(self, value: float) -> float:
        return (value - self.lower) / (self.upper - self.lower)

    def from_unit_interval(self, fraction: float) -> float:
        return self.lower + fraction * (self.upper - self.lower)


@dataclass(frozen=True)
class FixedVariable:
    """A physical variable held constant by the 12D acceptance case.

    Fixed variables do not carry bounds or a scale: they are not optimised and
    the loader rejects any attempt to vary them.  source records why the value
    is fixed (owner decision and, later, the frozen decision document).
    """

    id: str
    name: str
    unit: str
    baseline: float
    target: str
    source: str

    def __post_init__(self) -> None:
        for label, value in (
            ("id", self.id),
            ("name", self.name),
            ("unit", self.unit),
            ("target", self.target),
            ("source", self.source),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("fixed variable %s must be a non-empty string" % label)
        if not math.isfinite(self.baseline):
            raise ValueError("fixed variable %r baseline is not finite" % self.name)

    @property
    def value(self) -> float:
        return self.baseline


@dataclass(frozen=True)
class DesignSpace:
    schema_version: str
    stage: str
    task_id: str
    units: str
    frozen: bool
    bounds_status: str
    source: Dict[str, Any]
    variables: Tuple[DesignVariable, ...]
    derived_rules: Tuple[Dict[str, Any], ...]
    cross_constraints: Tuple[Dict[str, Any], ...]
    baseline_geometry: Dict[str, Any]
    evaluation_target: Dict[str, Any]
    freeze_requires: Tuple[str, ...]
    config_path: str
    design_set: str = "15d"
    fixed_variables: Tuple[FixedVariable, ...] = ()

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(variable.name for variable in self.variables)

    @property
    def ids(self) -> Tuple[str, ...]:
        return tuple(variable.id for variable in self.variables)

    @property
    def design_dim(self) -> int:
        return len(self.variables)

    @property
    def fixed_names(self) -> Tuple[str, ...]:
        return tuple(variable.name for variable in self.fixed_variables)

    @property
    def fixed_dict(self) -> Dict[str, float]:
        return {variable.name: variable.baseline for variable in self.fixed_variables}

    def expand(self, physical: Mapping[str, float]) -> Dict[str, float]:
        """Merge a declared-variable vector with the fixed values.

        The result is the full 15-name physical mapping the geometry model and
        the RCAIDE adapter consume.  Missing declared variables and undeclared
        extra keys both raise DesignSpaceError: a 15-name vector must not be
        passed to a 12D space and silently lose its fuselage values.  Fixed
        values are never taken from the caller, so a 12D workflow cannot
        silently perturb the fuselage.
        """
        declared = set(self.names)
        unexpected = sorted(set(physical) - declared)
        if unexpected:
            raise DesignSpaceError(
                "expand() got undeclared variables: %s" % ", ".join(repr(name) for name in unexpected)
            )
        expanded: Dict[str, float] = {}
        for variable in self.variables:
            expanded[variable.name] = _require_number(physical, variable.name)
        for variable in self.fixed_variables:
            if variable.name in expanded:
                raise DesignSpaceError(
                    "variable %r is both declared and fixed" % variable.name
                )
            expanded[variable.name] = variable.baseline
        return expanded

    def full_baseline_dict(self) -> Dict[str, float]:
        """Baseline of the full 15-name physical vector (declared + fixed)."""
        return self.expand(self.baseline_dict())

    def variable(self, name: str) -> DesignVariable:
        for candidate in self.variables:
            if candidate.name == name:
                return candidate
        raise DesignSpaceError("unknown design variable %r" % name)

    def variable_by_id(self, identifier: str) -> DesignVariable:
        for candidate in self.variables:
            if candidate.id == identifier:
                return candidate
        raise DesignSpaceError("unknown design variable id %r" % identifier)

    def baseline_vector(self) -> Tuple[float, ...]:
        return tuple(variable.baseline for variable in self.variables)

    def baseline_dict(self) -> Dict[str, float]:
        return {variable.name: variable.baseline for variable in self.variables}

    def to_normalized(self, physical: Mapping[str, float]) -> Tuple[float, ...]:
        return tuple(self.variable(name).normalize(_require_number(physical, name)) for name in self.names)

    def from_normalized(self, normalized: Sequence[float]) -> Dict[str, float]:
        values = _require_length(normalized, len(self.variables), "normalized design vector")
        return {
            variable.name: variable.denormalize(float(value))
            for variable, value in zip(self.variables, values)
        }

    def to_unit_interval(self, physical: Mapping[str, float]) -> Tuple[float, ...]:
        return tuple(self.variable(name).to_unit_interval(_require_number(physical, name)) for name in self.names)

    def from_unit_interval(self, fractions: Sequence[float]) -> Dict[str, float]:
        values = _require_length(fractions, len(self.variables), "unit-interval design vector")
        return {
            variable.name: variable.from_unit_interval(float(value))
            for variable, value in zip(self.variables, values)
        }

    def check_bounds(self, physical: Mapping[str, float]) -> List[str]:
        violations: List[str] = []
        for variable in self.variables:
            value = _require_number(physical, variable.name)
            if not math.isfinite(value):
                violations.append("%s (%s) is not finite: %r" % (variable.name, variable.id, value))
            elif not variable.contains(value):
                violations.append(
                    "%s (%s) = %r is outside [%r, %r]"
                    % (variable.name, variable.id, value, variable.lower, variable.upper)
                )
        return violations

    def check_cross_constraints(self, physical: Mapping[str, float]) -> List[str]:
        for name in self.names:
            if name not in physical:
                raise DesignSpaceError("design vector is missing variable %r" % name)
        return _cross_constraint_violations(self.expand(physical))

    def check_physical(self, physical: Mapping[str, float]) -> List[str]:
        return self.check_bounds(physical) + self.check_cross_constraints(physical)

    def config_summary(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "config_path": self.config_path,
            "frozen": self.frozen,
            "bounds_status": self.bounds_status,
            "design_set": self.design_set,
            "design_dim": self.design_dim,
            "geometry_dim": self.design_dim + len(self.fixed_variables),
            "names": list(self.names),
            "ids": list(self.ids),
            "fixed_names": list(self.fixed_names),
            "units": self.units,
        }


def load_design_space(path: Optional[str | Path] = None) -> DesignSpace:
    """Load and validate a design-space config (15d or 12d_lifting_surfaces)."""
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        data = load_config(config_path)
    except ConfigError as error:
        raise DesignSpaceError("cannot load design space %s: %s" % (config_path, error)) from error
    return design_space_from_config(data, source=str(config_path))


def design_space_from_config(data: Any, source: str = "<memory>") -> DesignSpace:
    """Validate a parsed config mapping and build a DesignSpace."""
    if not isinstance(data, Mapping):
        raise DesignSpaceError("%s: top level must be a mapping" % source)
    required_keys = (
        "schema_version",
        "stage",
        "task_id",
        "units",
        "frozen",
        "bounds_status",
        "source",
        "variables",
        "derived_rules",
        "cross_constraints",
        "baseline_geometry",
        "evaluation_target",
    )
    missing = [key for key in required_keys if key not in data]
    if missing:
        raise DesignSpaceError("%s: missing top-level keys: %s" % (source, ", ".join(missing)))

    design_set = str(data.get("design_set", "15d"))
    if design_set not in DESIGN_SETS:
        raise DesignSpaceError(
            "%s: unsupported design_set %r; expected one of %s"
            % (source, design_set, sorted(DESIGN_SETS))
        )
    expected_ids, expected_names = DESIGN_SETS[design_set]

    raw_variables = data["variables"]
    if not isinstance(raw_variables, list):
        raise DesignSpaceError("%s: variables must be a list" % source)
    if len(raw_variables) != len(expected_names):
        raise DesignSpaceError(
            "%s: design_set %r expects %d design variables, found %d"
            % (source, design_set, len(expected_names), len(raw_variables))
        )

    variables: List[DesignVariable] = []
    seen_ids = set()
    seen_names = set()
    for position, raw in enumerate(raw_variables, start=1):
        if not isinstance(raw, Mapping):
            raise DesignSpaceError("%s: variable #%d must be a mapping" % (source, position))
        variable = _build_variable(raw, position, source)
        if variable.id in seen_ids:
            raise DesignSpaceError("%s: duplicate variable id %r" % (source, variable.id))
        if variable.name in seen_names:
            raise DesignSpaceError("%s: duplicate variable name %r" % (source, variable.name))
        seen_ids.add(variable.id)
        seen_names.add(variable.name)
        variables.append(variable)

    expected_pairs = tuple(zip(expected_ids, expected_names))
    actual_pairs = tuple((variable.id, variable.name) for variable in variables)
    if actual_pairs != expected_pairs:
        raise DesignSpaceError(
            "%s: variable order/identity differs from the %r contract; expected %r, found %r"
            % (source, design_set, expected_pairs, actual_pairs)
        )

    fixed_variables: List[FixedVariable] = []
    raw_fixed = data.get("fixed_variables", [])
    if not isinstance(raw_fixed, list):
        raise DesignSpaceError("%s: fixed_variables must be a list" % source)
    if design_set == "15d":
        if raw_fixed:
            raise DesignSpaceError("%s: the 15d set declares every variable and cannot fix any of them" % source)
    else:
        if len(raw_fixed) != len(FIXED_FUSELAGE_NAMES):
            raise DesignSpaceError(
                "%s: design_set %r requires exactly %d fixed variables, found %d"
                % (source, design_set, len(FIXED_FUSELAGE_NAMES), len(raw_fixed))
            )
        fixed_seen_ids = set()
        fixed_seen_names = set()
        for position, raw in enumerate(raw_fixed, start=1):
            if not isinstance(raw, Mapping):
                raise DesignSpaceError("%s: fixed variable #%d must be a mapping" % (source, position))
            fixed = _build_fixed_variable(raw, position, source)
            if fixed.id in fixed_seen_ids or fixed.name in fixed_seen_names:
                raise DesignSpaceError("%s: duplicate fixed variable %r" % (source, fixed.name))
            if fixed.id in seen_ids or fixed.name in seen_names:
                raise DesignSpaceError("%s: fixed variable %r collides with a declared variable" % (source, fixed.name))
            fixed_seen_ids.add(fixed.id)
            fixed_seen_names.add(fixed.name)
            fixed_variables.append(fixed)
        fixed_pairs = tuple((fixed.id, fixed.name) for fixed in fixed_variables)
        expected_fixed_pairs = tuple(zip(FIXED_FUSELAGE_IDS, FIXED_FUSELAGE_NAMES))
        if fixed_pairs != expected_fixed_pairs:
            raise DesignSpaceError(
                "%s: fixed-variable order/identity differs from the D-12D-001 contract; expected %r, found %r"
                % (source, expected_fixed_pairs, fixed_pairs)
            )

    for key in ("derived_rules", "cross_constraints"):
        if not isinstance(data[key], list):
            raise DesignSpaceError("%s: %s must be a list" % (source, key))
    for key in ("source", "baseline_geometry", "evaluation_target"):
        if not isinstance(data[key], Mapping):
            raise DesignSpaceError("%s: %s must be a mapping" % (source, key))

    space = DesignSpace(
        schema_version=str(data["schema_version"]),
        stage=str(data["stage"]),
        task_id=str(data["task_id"]),
        units=str(data["units"]),
        frozen=bool(data["frozen"]),
        bounds_status=str(data["bounds_status"]),
        source=dict(data["source"]),
        variables=tuple(variables),
        derived_rules=tuple(dict(rule) for rule in data["derived_rules"]),
        cross_constraints=tuple(dict(rule) for rule in data["cross_constraints"]),
        baseline_geometry=dict(data["baseline_geometry"]),
        evaluation_target=dict(data["evaluation_target"]),
        freeze_requires=tuple(str(item) for item in data.get("freeze_requires", ())),
        config_path=source,
        design_set=design_set,
        fixed_variables=tuple(fixed_variables),
    )
    _validate_space(space, source)
    return space


def _build_variable(raw: Mapping[str, Any], position: int, source: str) -> DesignVariable:
    required = ("id", "name", "unit", "baseline", "lower", "upper", "scale", "target")
    missing = [key for key in required if key not in raw]
    if missing:
        raise DesignSpaceError(
            "%s: variable #%d is missing keys: %s" % (source, position, ", ".join(missing))
        )
    identifier = str(raw["id"])
    name = str(raw["name"])
    unit = str(raw["unit"])
    try:
        baseline = float(raw["baseline"])
        lower = float(raw["lower"])
        upper = float(raw["upper"])
        scale = float(raw["scale"])
    except (TypeError, ValueError) as error:
        raise DesignSpaceError("%s: variable %r has a non-numeric value: %s" % (source, name, error)) from error
    for label, value in (("baseline", baseline), ("lower", lower), ("upper", upper), ("scale", scale)):
        if not math.isfinite(value):
            raise DesignSpaceError("%s: variable %r has a non-finite %s" % (source, name, label))
    if not lower < upper:
        raise DesignSpaceError("%s: variable %r requires lower < upper" % (source, name))
    if not lower <= baseline <= upper:
        raise DesignSpaceError(
            "%s: variable %r baseline %r is outside [%r, %r]" % (source, name, baseline, lower, upper)
        )
    if scale <= 0:
        raise DesignSpaceError("%s: variable %r requires scale > 0" % (source, name))
    expected_unit = EXPECTED_UNITS[name]
    if unit != expected_unit:
        raise DesignSpaceError(
            "%s: variable %r uses unit %r but Issue #1 declares %r"
            % (source, name, unit, expected_unit)
        )
    return DesignVariable(
        id=identifier,
        name=name,
        unit=unit,
        baseline=baseline,
        lower=lower,
        upper=upper,
        scale=scale,
        target=str(raw["target"]),
    )


def _build_fixed_variable(raw: Mapping[str, Any], position: int, source: str) -> FixedVariable:
    required = ("id", "name", "unit", "baseline", "target", "source")
    missing = [key for key in required if key not in raw]
    if missing:
        raise DesignSpaceError(
            "%s: fixed variable #%d is missing keys: %s" % (source, position, ", ".join(missing))
        )
    name = str(raw["name"])
    unit = str(raw["unit"])
    if name not in FIXED_FUSELAGE_NAMES:
        raise DesignSpaceError("%s: fixed variable #%d name %r is not a fuselage variable" % (source, position, name))
    try:
        baseline = float(raw["baseline"])
    except (TypeError, ValueError) as error:
        raise DesignSpaceError("%s: fixed variable %r has a non-numeric baseline: %s" % (source, name, error)) from error
    if not math.isfinite(baseline):
        raise DesignSpaceError("%s: fixed variable %r has a non-finite baseline" % (source, name))
    expected_unit = EXPECTED_UNITS[name]
    if unit != expected_unit:
        raise DesignSpaceError(
            "%s: fixed variable %r uses unit %r but the contract declares %r"
            % (source, name, unit, expected_unit)
        )
    return FixedVariable(
        id=str(raw["id"]),
        name=name,
        unit=unit,
        baseline=baseline,
        target=str(raw["target"]),
        source=str(raw["source"]),
    )


def _validate_space(space: DesignSpace, source: str) -> None:
    if not space.units.upper() == "SI":
        raise DesignSpaceError("%s: Phase I design space must declare SI units" % source)
    if space.frozen:
        raise DesignSpaceError(
            "%s: the P1 design space is provisional and must not be loaded as frozen before "
            "the geometry perturbation checks are complete" % source
        )
    allowed_cross = {"C01", "C02", "C03", "C04"}
    declared_cross = {str(rule.get("id")) for rule in space.cross_constraints}
    missing_cross = sorted(allowed_cross - declared_cross)
    unexpected_cross = sorted(declared_cross - allowed_cross)
    if missing_cross or unexpected_cross:
        raise DesignSpaceError(
            "%s: cross constraints must be exactly %s (missing=%s unexpected=%s)"
            % (source, sorted(allowed_cross), missing_cross, unexpected_cross)
        )
    derived_names = [str(rule.get("name")) for rule in space.derived_rules]
    if len(set(derived_names)) != len(derived_names):
        raise DesignSpaceError("%s: duplicate derived-rule names" % source)
    violations = space.check_physical(space.baseline_dict())
    if violations:
        raise DesignSpaceError("%s: baseline design violates its own contract: %s" % (source, "; ".join(violations)))
    _validate_baseline_geometry(space, source)


def _validate_baseline_geometry(space: DesignSpace, source: str) -> None:
    """Reject a baseline_geometry block that contradicts its own derived rules.

    The loader must not silently accept stale numbers: the P1 draft declared a
    33.8 m root chord next to a formula that derives 27.10 m, and a validator
    that ignored the block let that conflict through.  Every relation checked
    here is independent of the geometry model module so the config remains a
    genuine second source.
    """
    geometry = space.baseline_geometry
    for key in ("status", "main_wing", "vertical_stabilizer", "fuselage"):
        if key not in geometry:
            raise DesignSpaceError("%s: baseline_geometry is missing %r" % (source, key))
    if not isinstance(geometry["status"], str) or not geometry["status"].strip():
        raise DesignSpaceError("%s: baseline_geometry.status must be a non-empty string" % source)
    for key in ("main_wing", "vertical_stabilizer", "fuselage"):
        if not isinstance(geometry[key], Mapping):
            raise DesignSpaceError("%s: baseline_geometry.%s must be a mapping" % (source, key))
    wing = geometry["main_wing"]
    tail = geometry["vertical_stabilizer"]
    fuselage = geometry["fuselage"]
    baseline = space.expand(space.baseline_dict())

    wing_span = _require_positive_number(wing, "projected_span_m", source, "baseline_geometry.main_wing")
    wing_root = _require_positive_number(wing, "root_chord_m", source, "baseline_geometry.main_wing")
    wing_tip = _require_positive_number(wing, "tip_chord_m", source, "baseline_geometry.main_wing")
    wing_taper = _require_positive_number(wing, "taper_ratio", source, "baseline_geometry.main_wing")
    for key in ("mean_aerodynamic_chord_m", "wetted_area_m2", "exposed_area_m2"):
        _require_positive_number(wing, key, source, "baseline_geometry.main_wing")
    wing_spans = _require_sequence(wing, "section_span_fractions", 4, source, "baseline_geometry.main_wing")
    wing_ratios = _require_sequence(wing, "section_chord_ratios", 4, source, "baseline_geometry.main_wing")
    _require_sequence(wing, "section_quarter_chord_sweeps_deg", 4, source, "baseline_geometry.main_wing")
    expected_span = math.sqrt(baseline["wing_area"] * baseline["aspect_ratio"])
    _require_close(wing_span, expected_span, 1e-4, source, "main_wing.projected_span_m")
    _require_ordered(wing_spans, source, "main_wing.section_span_fractions")
    _require_ordered(list(reversed(wing_ratios)), source, "main_wing.section_chord_ratios")
    wing_k = _segment_area_factor(wing_spans, wing_ratios)
    expected_root = baseline["wing_area"] / (wing_span * wing_k)
    _require_close(wing_root, expected_root, 1e-3, source, "main_wing.root_chord_m")
    _require_close(wing_tip, wing_root * wing_ratios[-1], 1e-3, source, "main_wing.tip_chord_m")
    _require_close(wing_taper, wing_ratios[-1] / wing_ratios[0], 1e-6, source, "main_wing.taper_ratio")
    _require_close(
        wing["exposed_area_m2"],
        baseline["wing_area"],
        1e-6,
        source,
        "main_wing.exposed_area_m2",
    )

    tail_span = _require_positive_number(tail, "projected_span_m", source, "baseline_geometry.vertical_stabilizer")
    tail_root = _require_positive_number(tail, "root_chord_m", source, "baseline_geometry.vertical_stabilizer")
    tail_tip = _require_positive_number(tail, "tip_chord_m", source, "baseline_geometry.vertical_stabilizer")
    tail_taper = _require_positive_number(tail, "taper_ratio", source, "baseline_geometry.vertical_stabilizer")
    for key in ("mean_aerodynamic_chord_m", "wetted_area_m2"):
        _require_positive_number(tail, key, source, "baseline_geometry.vertical_stabilizer")
    tail_spans = _require_sequence(tail, "section_span_fractions", 3, source, "baseline_geometry.vertical_stabilizer")
    tail_ratios = _require_sequence(tail, "section_chord_ratios", 3, source, "baseline_geometry.vertical_stabilizer")
    _require_sequence(tail, "section_quarter_chord_sweeps_deg", 3, source, "baseline_geometry.vertical_stabilizer")
    _require_close(
        tail_span, math.sqrt(baseline["vertical_tail_area"] * 0.74), 1e-4, source, "vertical_stabilizer.projected_span_m"
    )
    _require_ordered(tail_spans, source, "vertical_stabilizer.section_span_fractions")
    _require_ordered(list(reversed(tail_ratios)), source, "vertical_stabilizer.section_chord_ratios")
    tail_k = _segment_area_factor(tail_spans, tail_ratios)
    _require_close(
        tail_root, baseline["vertical_tail_area"] / (tail_span * tail_k), 1e-3, source, "vertical_stabilizer.root_chord_m"
    )
    _require_close(tail_tip, tail_root * tail_ratios[-1], 1e-3, source, "vertical_stabilizer.tip_chord_m")
    _require_close(tail_taper, tail_ratios[-1] / tail_ratios[0], 1e-6, source, "vertical_stabilizer.taper_ratio")

    for key in ("length_m", "width_m", "height_m", "nose_fineness", "tail_fineness"):
        _require_positive_number(fuselage, key, source, "baseline_geometry.fuselage")
    for key in ("wetted_area_m2", "front_projected_area_m2", "effective_diameter_m"):
        _require_positive_number(fuselage, key, source, "baseline_geometry.fuselage")
    _require_close(fuselage["length_m"], baseline["fuselage_length"], 1e-9, source, "fuselage.length_m")
    _require_close(fuselage["height_m"], baseline["fuselage_height_width_ratio"] * fuselage["width_m"], 1e-4, source, "fuselage.height_m")
    _require_close(fuselage["nose_fineness"], baseline["fuselage_fineness"], 1e-6, source, "fuselage.nose_fineness")
    _require_close(fuselage["tail_fineness"], baseline["fuselage_fineness"] * 6.4 / 4.3, 1e-6, source, "fuselage.tail_fineness")

    upstream = geometry.get("upstream_declared")
    if upstream is not None:
        if not isinstance(upstream, Mapping):
            raise DesignSpaceError("%s: baseline_geometry.upstream_declared must be a mapping" % source)
        for key, value in upstream.items():
            if key in ("main_wing", "vertical_stabilizer", "fuselage") and not isinstance(value, Mapping):
                raise DesignSpaceError(
                    "%s: baseline_geometry.upstream_declared.%s must be a mapping" % (source, key)
                )


def _require_positive_number(mapping: Mapping[str, Any], key: str, source: str, label: str) -> float:
    if key not in mapping:
        raise DesignSpaceError("%s: %s is missing %r" % (source, label, key))
    try:
        value = float(mapping[key])
    except (TypeError, ValueError) as error:
        raise DesignSpaceError("%s: %s.%s is not numeric: %r" % (source, label, key, mapping[key])) from error
    if not math.isfinite(value) or value <= 0.0:
        raise DesignSpaceError("%s: %s.%s must be finite and positive, found %r" % (source, label, key, value))
    return value


def _require_sequence(mapping: Mapping[str, Any], key: str, length: int, source: str, label: str) -> List[float]:
    if key not in mapping:
        raise DesignSpaceError("%s: %s is missing %r" % (source, label, key))
    raw = mapping[key]
    if not isinstance(raw, (list, tuple)) or len(raw) != length:
        raise DesignSpaceError("%s: %s.%s must be a list of %d numbers" % (source, label, key, length))
    try:
        values = [float(item) for item in raw]
    except (TypeError, ValueError) as error:
        raise DesignSpaceError("%s: %s.%s contains a non-numeric entry" % (source, label, key)) from error
    if any(not math.isfinite(value) for value in values):
        raise DesignSpaceError("%s: %s.%s contains a non-finite entry" % (source, label, key))
    return values


def _require_ordered(values: Sequence[float], source: str, label: str) -> None:
    if any(left >= right for left, right in zip(values, values[1:])):
        raise DesignSpaceError("%s: %s must be strictly increasing" % (source, label))


def _require_close(actual: float, expected: float, tolerance: float, source: str, label: str) -> None:
    if expected == 0.0:
        if abs(actual) > tolerance:
            raise DesignSpaceError("%s: %s=%r deviates from the derived value %r" % (source, label, actual, expected))
        return
    relative = abs(actual - expected) / abs(expected)
    if relative > tolerance:
        raise DesignSpaceError(
            "%s: %s=%r deviates from the derived value %r by %.3g (tolerance %g)"
            % (source, label, actual, expected, relative, tolerance)
        )


def _segment_area_factor(span_fractions: Sequence[float], chord_ratios: Sequence[float]) -> float:
    return sum(
        0.5 * (span_fractions[index + 1] - span_fractions[index]) * (chord_ratios[index] + chord_ratios[index + 1])
        for index in range(len(span_fractions) - 1)
    )


def _cross_constraint_violations(physical: Mapping[str, float]) -> List[str]:
    violations: List[str] = []

    span_2 = float(physical["span_location_2"])
    span_3 = float(physical["span_location_3"])
    if not span_2 < span_3:
        violations.append("C01: span_location_2=%r must be < span_location_3=%r" % (span_2, span_3))

    chord_2 = float(physical["chord_ratio_2"])
    chord_3 = float(physical["chord_ratio_3"])
    if not chord_3 < chord_2 < 1.0:
        violations.append(
            "C02: chord_ratio_3=%r < chord_ratio_2=%r < 1.0 violated" % (chord_3, chord_2)
        )

    for name in _POSITIVE_VARIABLES:
        value = float(physical[name])
        if not value > 0.0:
            violations.append("C03: %s=%r must be positive" % (name, value))

    for name in _SWEEP_VARIABLES:
        value = float(physical[name])
        if not 0.0 <= value <= 90.0:
            violations.append("C04: %s=%r must be within [0, 90] deg" % (name, value))

    return violations


def _require_number(physical: Mapping[str, float], name: str) -> float:
    if name not in physical:
        raise DesignSpaceError("design vector is missing variable %r" % name)
    try:
        return float(physical[name])
    except (TypeError, ValueError) as error:
        raise DesignSpaceError("design variable %r is not numeric: %r" % (name, physical[name])) from error


def _require_length(values: Sequence[float], expected: int, label: str) -> Sequence[float]:
    if len(values) != expected:
        raise DesignSpaceError("%s must have %d entries, found %d" % (label, expected, len(values)))
    return values
