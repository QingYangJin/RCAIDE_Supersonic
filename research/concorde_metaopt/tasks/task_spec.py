"""Frozen single-cruise TaskSpec for the Concorde Phase I optimisation problem.

The Issue freezes one task for Phase I: a Concorde-class fixed topology, a
single fixed supersonic cruise segment, and a fixed engine / loading / starting
mass contract, with only the 15 geometry variables free.  This module freezes
that contract, validates it, and exposes it to the evaluation and learning
layers.  It contains no simulation code.

The frozen objective is the segment fuel burn in kg:

    fuel_burn_kg = mass_start_kg - mass_end_kg

The mass contract was calibrated against the real RCAIDE mission on
2026-10-29 (see the freeze evidence recorded in
configs/task_fixed_cruise.yaml).  The upstream tutorial takeoff mass of
185000 kg starts the cruise so heavy that the required throttle is 1.2708,
which is physically infeasible, so it cannot serve as the frozen Phase I
contract.  A 145000 kg point looked feasible when extrapolated from the
tutorial geometry, but the P1 planform closure gives a shorter root chord
(29.90 m versus the declared 33.8 m), and the measured throttle at 145000 kg is
1.0163, so that contract is infeasible too.  The frozen contract is therefore
136000 kg (zero-fuel mass 89200 kg, loaded fuel 46800 kg): the measured
baseline throttle is 0.9455, a 5.5 percent margin, and every declared mass
constraint is feasible.

TaskSpec versions are immutable: any change to a value, bound, propulsor list or
mission setting must bump the version string, which changes the fingerprint and
therefore every run directory, dataset manifest and MAML task identity.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ..config_io import ConfigError, load_config

TASK_SPEC_VERSION = "p2-2026-10-29b"

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
DEFAULT_TASK_CONFIG_PATH = CONFIG_DIR / "task_fixed_cruise.yaml"

REQUIRED_OBJECTIVE_NAME = "fuel_burn_kg"
REQUIRED_OBJECTIVE_UNIT = "kg"
ALLOWED_MASS_CONTRACT_STATUS = ("frozen",)
MACH_LIMITS = (0.5, 5.0)
ALTITUDE_LIMITS_M = (1000.0, 30000.0)
MASS_BALANCE_RELATIVE_TOLERANCE = 1e-9


class TaskSpecError(ValueError):
    """Raised when a task contract is missing, malformed or inconsistent."""


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TaskSpecError("%s must be a number, got %r" % (name, value))
    number = float(value)
    if not math.isfinite(number):
        raise TaskSpecError("%s must be finite, got %r" % (name, value))
    return number


def _positive(value: Any, name: str) -> float:
    number = _number(value, name)
    if not number > 0.0:
        raise TaskSpecError("%s must be positive, got %r" % (name, value))
    return number


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskSpecError("%s must be a non-empty string, got %r" % (name, value))
    return value.strip()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TaskSpecError("%s must be a mapping, got %r" % (name, type(value).__name__))
    return value


def _sequence_of_text(value: Any, name: str) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise TaskSpecError("%s must be a non-empty sequence of strings" % name)
    items = tuple(_text(item, "%s[%d]" % (name, index)) for index, item in enumerate(value))
    if len(set(items)) != len(items):
        raise TaskSpecError("%s must not contain duplicates: %r" % (name, list(items)))
    return items


@dataclass(frozen=True)
class FixedCruiseTask:
    """Immutable Phase I task contract for the single Concorde cruise segment.

    All masses are kg, the altitude is m, the distance is m and the Mach number
    is dimensionless.  The derived zero-fuel mass is operating empty plus
    payload plus cargo; the starting mass must equal zero-fuel mass plus loaded
    fuel.  No fuel-burn evaluation may run against a task whose contract is not
    internally consistent.
    """

    task_id: str
    version: str
    description: str
    cruise_altitude_m: float
    cruise_mach: float
    cruise_distance_m: float
    operating_empty_kg: float
    payload_kg: float
    cargo_kg: float
    fuel_loaded_kg: float
    start_mass_kg: float
    max_fuel_kg: float
    max_zero_fuel_kg: float
    max_takeoff_kg: float
    propulsor_tags: Tuple[str, ...]
    cruise_config_tag: str = "cruise"
    objective_name: str = REQUIRED_OBJECTIVE_NAME
    objective_unit: str = REQUIRED_OBJECTIVE_UNIT
    mass_contract_status: str = "frozen"
    freeze_evidence: str = ""
    created_utc: str = "2026-10-29T00:00:00Z"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "propulsor_tags",
            tuple(self.propulsor_tags) if isinstance(self.propulsor_tags, (list, tuple)) else self.propulsor_tags,
        )
        self.check_consistency()

    # ------------------------------------------------------------------
    # derived values
    # ------------------------------------------------------------------
    @property
    def zero_fuel_mass_kg(self) -> float:
        return self.operating_empty_kg + self.payload_kg + self.cargo_kg

    @property
    def takeoff_margin_kg(self) -> float:
        return self.max_takeoff_kg - self.start_mass_kg

    @property
    def fuel_margin_kg(self) -> float:
        return self.max_fuel_kg - self.fuel_loaded_kg

    @property
    def zero_fuel_margin_kg(self) -> float:
        return self.max_zero_fuel_kg - self.zero_fuel_mass_kg

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------
    def check_consistency(self) -> None:
        task_id = _text(self.task_id, "task_id")
        _text(self.version, "version")
        _text(self.description, "description")
        _text(self.cruise_config_tag, "cruise_config_tag")
        _text(self.created_utc, "created_utc")

        altitude = _positive(self.cruise_altitude_m, "cruise_altitude_m")
        if not (ALTITUDE_LIMITS_M[0] <= altitude <= ALTITUDE_LIMITS_M[1]):
            raise TaskSpecError(
                "cruise_altitude_m %.6g m outside the supported Phase I range %r"
                % (altitude, ALTITUDE_LIMITS_M)
            )
        mach = _positive(self.cruise_mach, "cruise_mach")
        if not (MACH_LIMITS[0] <= mach <= MACH_LIMITS[1]):
            raise TaskSpecError(
                "cruise_mach %.6g outside the supported Phase I range %r" % (mach, MACH_LIMITS)
            )
        _positive(self.cruise_distance_m, "cruise_distance_m")

        masses = {
            "operating_empty_kg": self.operating_empty_kg,
            "payload_kg": self.payload_kg,
            "cargo_kg": self.cargo_kg,
            "fuel_loaded_kg": self.fuel_loaded_kg,
            "start_mass_kg": self.start_mass_kg,
            "max_fuel_kg": self.max_fuel_kg,
            "max_zero_fuel_kg": self.max_zero_fuel_kg,
            "max_takeoff_kg": self.max_takeoff_kg,
        }
        for name, value in masses.items():
            _positive(value, name)

        zero_fuel = self.operating_empty_kg + self.payload_kg + self.cargo_kg
        expected_start = zero_fuel + self.fuel_loaded_kg
        difference = abs(self.start_mass_kg - expected_start)
        if difference > MASS_BALANCE_RELATIVE_TOLERANCE * max(1.0, self.start_mass_kg):
            raise TaskSpecError(
                "start_mass_kg %.6f does not equal operating_empty + payload + cargo + fuel_loaded = %.6f"
                % (self.start_mass_kg, expected_start)
            )
        for label, limit, required in (
            ("max_zero_fuel_kg", self.max_zero_fuel_kg, zero_fuel),
            ("max_fuel_kg", self.max_fuel_kg, self.fuel_loaded_kg),
            ("max_takeoff_kg", self.max_takeoff_kg, self.start_mass_kg),
        ):
            if limit < required - 1e-6:
                raise TaskSpecError("%s %.6f kg is below the frozen contract value %.6f kg" % (label, limit, required))

        _sequence_of_text(self.propulsor_tags, "propulsor_tags")

        if self.objective_name != REQUIRED_OBJECTIVE_NAME:
            raise TaskSpecError(
                "objective_name must be %r, got %r" % (REQUIRED_OBJECTIVE_NAME, self.objective_name)
            )
        if self.objective_unit != REQUIRED_OBJECTIVE_UNIT:
            raise TaskSpecError(
                "objective_unit must be %r, got %r" % (REQUIRED_OBJECTIVE_UNIT, self.objective_unit)
            )
        if self.mass_contract_status not in ALLOWED_MASS_CONTRACT_STATUS:
            raise TaskSpecError(
                "mass_contract_status must be one of %r, got %r"
                % (list(ALLOWED_MASS_CONTRACT_STATUS), self.mass_contract_status)
            )
        if not isinstance(self.freeze_evidence, str) or not self.freeze_evidence.strip():
            raise TaskSpecError("freeze_evidence must explain how the contract was measured")
        if not task_id:
            raise TaskSpecError("task_id must not be empty")

    # ------------------------------------------------------------------
    # serialisation and identity
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "version": self.version,
            "created_utc": self.created_utc,
            "description": self.description,
            "cruise": {
                "altitude_m": self.cruise_altitude_m,
                "mach_number": self.cruise_mach,
                "distance_m": self.cruise_distance_m,
            },
            "masses": {
                "operating_empty_kg": self.operating_empty_kg,
                "payload_kg": self.payload_kg,
                "cargo_kg": self.cargo_kg,
                "fuel_loaded_kg": self.fuel_loaded_kg,
                "start_mass_kg": self.start_mass_kg,
                "max_fuel_kg": self.max_fuel_kg,
                "max_zero_fuel_kg": self.max_zero_fuel_kg,
                "max_takeoff_kg": self.max_takeoff_kg,
            },
            "propulsion": {
                "config_tag": self.cruise_config_tag,
                "propulsor_tags": list(self.propulsor_tags),
            },
            "objective": {"name": self.objective_name, "unit": self.objective_unit},
            "mass_contract": {
                "status": self.mass_contract_status,
                "evidence": self.freeze_evidence,
            },
            "derived": {
                "zero_fuel_mass_kg": self.zero_fuel_mass_kg,
                "takeoff_margin_kg": self.takeoff_margin_kg,
                "fuel_margin_kg": self.fuel_margin_kg,
                "zero_fuel_margin_kg": self.zero_fuel_margin_kg,
            },
        }

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def run_record(self) -> Dict[str, Any]:
        record = self.to_dict()
        record["task_fingerprint"] = self.fingerprint()
        record["task_spec_version"] = TASK_SPEC_VERSION
        return record

    # ------------------------------------------------------------------
    # cross-layer conversions
    # ------------------------------------------------------------------
    def maml_context(self) -> Dict[str, float]:
        """Flat numeric task context for maml_opt.contracts.TaskSpec."""
        return {
            "cruise_altitude_m": self.cruise_altitude_m,
            "cruise_mach": self.cruise_mach,
            "cruise_distance_m": self.cruise_distance_m,
            "operating_empty_kg": self.operating_empty_kg,
            "payload_kg": self.payload_kg,
            "cargo_kg": self.cargo_kg,
            "fuel_loaded_kg": self.fuel_loaded_kg,
            "start_mass_kg": self.start_mass_kg,
            "max_fuel_kg": self.max_fuel_kg,
            "max_zero_fuel_kg": self.max_zero_fuel_kg,
            "max_takeoff_kg": self.max_takeoff_kg,
        }

    def to_maml_task_spec(self) -> Any:
        """Convert to the maml_opt TaskSpec used by P4/P5.

        The import is local so the P2 evaluation path does not depend on the
        learning package being importable.
        """
        from maml_opt.contracts import TaskSpec as MamlTaskSpec  # local import

        model_config = {
            "aircraft": "Concorde",
            "mission_contract": "single-fixed-cruise-p2-v1",
            "objective": self.objective_name,
            "objective_unit": self.objective_unit,
            "propulsor_tags": list(self.propulsor_tags),
            "cruise_config_tag": self.cruise_config_tag,
            "task_spec_version": TASK_SPEC_VERSION,
            "task_fingerprint": self.fingerprint(),
        }
        return MamlTaskSpec(task_id=self.task_id, context=self.maml_context(), model_config=model_config)

    @classmethod
    def from_config(cls, config: Any) -> "FixedCruiseTask":
        data = _mapping(config, "task config")
        cruise = _mapping(data.get("cruise"), "cruise")
        masses = _mapping(data.get("masses"), "masses")
        propulsion = _mapping(data.get("propulsion"), "propulsion")
        objective = _mapping(data.get("objective"), "objective")
        mass_contract = _mapping(data.get("mass_contract"), "mass_contract")
        try:
            return cls(
                task_id=_text(data.get("task_id"), "task_id"),
                version=_text(data.get("version"), "version"),
                description=_text(data.get("description"), "description"),
                cruise_altitude_m=_positive(cruise.get("altitude_m"), "cruise.altitude_m"),
                cruise_mach=_positive(cruise.get("mach_number"), "cruise.mach_number"),
                cruise_distance_m=_positive(cruise.get("distance_m"), "cruise.distance_m"),
                operating_empty_kg=_positive(masses.get("operating_empty_kg"), "masses.operating_empty_kg"),
                payload_kg=_positive(masses.get("payload_kg"), "masses.payload_kg"),
                cargo_kg=_positive(masses.get("cargo_kg"), "masses.cargo_kg"),
                fuel_loaded_kg=_positive(masses.get("fuel_loaded_kg"), "masses.fuel_loaded_kg"),
                start_mass_kg=_positive(masses.get("start_mass_kg"), "masses.start_mass_kg"),
                max_fuel_kg=_positive(masses.get("max_fuel_kg"), "masses.max_fuel_kg"),
                max_zero_fuel_kg=_positive(masses.get("max_zero_fuel_kg"), "masses.max_zero_fuel_kg"),
                max_takeoff_kg=_positive(masses.get("max_takeoff_kg"), "masses.max_takeoff_kg"),
                propulsor_tags=_sequence_of_text(propulsion.get("propulsor_tags"), "propulsion.propulsor_tags"),
                cruise_config_tag=_text(propulsion.get("config_tag", "cruise"), "propulsion.config_tag"),
                objective_name=_text(objective.get("name", REQUIRED_OBJECTIVE_NAME), "objective.name"),
                objective_unit=_text(objective.get("unit", REQUIRED_OBJECTIVE_UNIT), "objective.unit"),
                mass_contract_status=_text(mass_contract.get("status"), "mass_contract.status"),
                freeze_evidence=_text(mass_contract.get("evidence"), "mass_contract.evidence"),
                created_utc=_text(data.get("created_utc", "2026-10-29T00:00:00Z"), "created_utc"),
            )
        except KeyError as error:  # pragma: no cover - defensive
            raise TaskSpecError("task config is missing section %s" % error) from error


def load_task_spec(path: Optional[Path] = None) -> FixedCruiseTask:
    """Load and validate a frozen task contract from YAML/JSON."""
    config_path = Path(path) if path is not None else DEFAULT_TASK_CONFIG_PATH
    try:
        config = load_config(config_path)
    except ConfigError as error:
        raise TaskSpecError(str(error)) from error
    task = FixedCruiseTask.from_config(config)
    # `config_path` is provenance, not part of the frozen identity: attaching it
    # lets run evidence record which YAML file produced the contract without
    # changing the fingerprint (the field is not in to_dict()).
    object.__setattr__(task, "config_path", config_path)
    return task
