"""Frozen-order 15D design space for the Concorde fixed-cruise problem.

Issue #1 fixes the variable order and identifiers; this module loads the
provisional P1 config, validates it and provides the small numerical helpers the
geometry, evaluation and optimisation code share.  Physical values are always
stored in SI units as declared by the config; normalisation is only a view.

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

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(variable.name for variable in self.variables)

    @property
    def ids(self) -> Tuple[str, ...]:
        return tuple(variable.id for variable in self.variables)

    def variable(self, name: str) -> DesignVariable:
        for candidate in self.variables:
            if candidate.name == name:
                return candidate
        raise DesignSpaceError("unknown design variable %r" % name)

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
        return _cross_constraint_violations(physical)

    def check_physical(self, physical: Mapping[str, float]) -> List[str]:
        return self.check_bounds(physical) + self.check_cross_constraints(physical)

    def config_summary(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "config_path": self.config_path,
            "frozen": self.frozen,
            "bounds_status": self.bounds_status,
            "design_dim": len(self.variables),
            "names": list(self.names),
            "ids": list(self.ids),
            "units": self.units,
        }


def load_design_space(path: Optional[str | Path] = None) -> DesignSpace:
    """Load and validate the 15D design-space config."""
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

    raw_variables = data["variables"]
    if not isinstance(raw_variables, list):
        raise DesignSpaceError("%s: variables must be a list" % source)
    if len(raw_variables) != len(EXPECTED_NAMES):
        raise DesignSpaceError(
            "%s: expected %d design variables, found %d" % (source, len(EXPECTED_NAMES), len(raw_variables))
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

    expected_pairs = tuple(zip(EXPECTED_IDS, EXPECTED_NAMES))
    actual_pairs = tuple((variable.id, variable.name) for variable in variables)
    if actual_pairs != expected_pairs:
        raise DesignSpaceError(
            "%s: variable order/identity differs from the frozen Issue #1 contract; expected %r, found %r"
            % (source, expected_pairs, actual_pairs)
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
