"""Low-fidelity fixed-cruise backend used by Phase I.

Each call builds a fresh tutorial vehicle, expands a 12D or 15D design into full geometry, freezes the
task mass contract, flies the single cruise segment and returns one evaluation
record. The backend never raises for a bad design: geometry errors, mission
failures and non-convergence are reported through the frozen status codes with a
null objective, so downstream optimization cannot treat them as fuel burn.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from ..aircraft.concorde_adapter import (
    AdapterError,
    apply_mass_contract,
    build_vehicle,
    evaluate_geometry_cross_check,
    file_sha256,
    load_template_module,
    resolve_tutorial_path,
)
from ..aircraft.design_space import DesignSpace, load_design_space
from ..aircraft.geometry_model import GeometryError, build_geometry
from ..tasks.task_spec import FixedCruiseTask, load_task_spec
from .contract import (
    OBJECTIVE_NAME,
    OBJECTIVE_UNIT,
    RESIDUAL_LIMIT,
    STATUS_GEOMETRY_INVALID,
    STATUS_GEOMETRY_MISMATCH,
    STATUS_INVALID_OR_MISSING_RESPONSE,
    STATUS_MISSION_BUILD_FAILED,
    STATUS_MISSION_FAILED,
    STATUS_MISSION_NOT_CONVERGED,
    STATUS_VALID,
    empty_constraints,
    evaluate_constraints,
    feasibility,
    new_call_accounting,
)
from .mission import (
    MissionBuildError,
    ObservationError,
    build_single_cruise_mission,
    extract_observations,
)

FIDELITY_SINGLE_CRUISE = "single_cruise"

WEIGHT_SETTINGS_TO_DISABLE = (
    "run_weights_analysis",
    "update_fuel_mass",
    "update_max_fuel_mass",
    "run_center_of_gravity_analysis",
    "run_moments_of_inertia_analysis",
    "print_weight_analysis_report",
)


def mission_converged(observations: Mapping[str, Any]) -> bool:
    """True only when mission, solver and residual acceptance all pass.

    The P2 contract requires a finite residual below RESIDUAL_LIMIT in addition
    to the two convergence flags; the backend status must not ignore the
    residual criterion even though the constraint bundle also encodes it.
    """
    try:
        residual = float(observations["residual_max"])
    except (KeyError, TypeError, ValueError):
        return False
    if not math.isfinite(residual) or residual > RESIDUAL_LIMIT:
        return False
    return bool(observations.get("converged")) and bool(observations.get("solver_converged"))


def _disable_weight_preprocessing(analysis: Any) -> Dict[str, Any]:
    """Turn off RCAIDE weight recomputation so the frozen contract survives."""
    settings = analysis.weights.settings
    applied: Dict[str, Any] = {}
    for name in WEIGHT_SETTINGS_TO_DISABLE:
        if hasattr(settings, name):
            setattr(settings, name, False)
            applied[name] = False
    return applied


class SingleCruiseBackend:
    """RCAIDE single-cruise evaluation backend for the frozen Phase I task."""

    def __init__(
        self,
        design_space: Optional[DesignSpace] = None,
        task: Optional[FixedCruiseTask] = None,
        repo_root: Optional[Path] = None,
        verify_tutorial_hash: bool = True,
    ) -> None:
        self.design_space = design_space if design_space is not None else load_design_space()
        self.task = task if task is not None else load_task_spec()
        self.repo_root = Path(repo_root) if repo_root is not None else None
        self.names = tuple(self.design_space.names)
        self.fidelity = FIDELITY_SINGLE_CRUISE
        self._template = load_template_module(self.repo_root, verify_hash=verify_tutorial_hash)
        self._tutorial_sha256 = file_sha256(resolve_tutorial_path(self.repo_root))
        self._template_hash_verified = bool(verify_tutorial_hash)
        self._weight_settings = None

    # -- protocol helpers -------------------------------------------------
    def baseline_design(self) -> Dict[str, float]:
        return dict(self.design_space.baseline_dict())

    def design_vector(self, design: Mapping[str, float]) -> Sequence[float]:
        names = list(self.names)
        missing = [name for name in names if name not in design]
        extra = [name for name in design if name not in names]
        if missing or extra:
            raise KeyError(
                "design keys do not match the %s space (missing=%s, extra=%s)"
                % (self.design_space.design_set, missing, extra)
            )
        return [float(design[name]) for name in names]

    def preflight(self) -> Dict[str, Any]:
        """Validate the template and task without launching a mission."""
        expanded = self.design_space.full_baseline_dict()
        geometry = build_geometry(tuple(expanded), tuple(expanded.values()))
        return {
            "physical_call_count": 0,
            "fidelity": self.fidelity,
            "task_id": self.task.task_id,
            "task_fingerprint": self.task.fingerprint(),
            "design_space_config": self.design_space.config_summary() if hasattr(self.design_space, "config_summary") else {},
            "tutorial_sha256": self._tutorial_sha256,
            "template_hash_verified": self._template_hash_verified,
            "baseline": {
                "wing_area_m2": geometry.wing.area_m2,
                "wing_span_m": geometry.wing.span_m,
                "tail_area_m2": geometry.vertical_tail.area_m2,
                "fuselage_length_m": geometry.fuselage.length_m,
            },
            "status": "PREFLIGHT_OK",
        }

    # -- evaluation -------------------------------------------------------
    def evaluate(
        self,
        design: Mapping[str, float],
        task: Optional[FixedCruiseTask] = None,
        fidelity: Optional[str] = None,
        purpose: str = "search",
    ) -> Dict[str, Any]:
        started = time.perf_counter()
        if task is not None:
            received = task.fingerprint() if hasattr(task, "fingerprint") else None
            expected = self.task.fingerprint()
            if received is None or received != expected:
                self.last_physical_call_count = 0
                self.last_call_accounting = new_call_accounting()
                self.last_call_accounting["request_rejected"] = 1
                self.last_call_accounting["failure_stage"] = "task_mismatch"
                raise ValueError(
                    "evaluation task does not match the frozen backend task "
                    "(expected fingerprint %s, received %s)" % (expected, received)
                )
        record: Dict[str, Any] = {
            "fidelity": fidelity or self.fidelity,
            "purpose": purpose,
            "design_dim": self.design_space.design_dim,
            "design_set": self.design_space.design_set,
            "task_id": self.task.task_id,
            "task_fingerprint": self.task.fingerprint(),
            "design": {name: float(design[name]) for name in self.names if name in design},
            "status": STATUS_MISSION_FAILED,
            "objective": None,
            "objective_name": OBJECTIVE_NAME,
            "objective_unit": OBJECTIVE_UNIT,
            "constraints": empty_constraints(),
            "feasible": False,
            "responses": {},
            "diagnostics": [],
            "physical_call_count": 0,
            "call_accounting": new_call_accounting(),
            "wall_seconds": 0.0,
        }
        acct = record["call_accounting"]
        # Conservative default if an unexpected exception escapes before any
        # solver attempt: the request is rejected and nothing is billable.
        self.last_physical_call_count = 0
        self.last_call_accounting = new_call_accounting()
        self.last_call_accounting["request_rejected"] = 1
        self.last_call_accounting["failure_stage"] = "backend_exception_before_accounting"

        def mark(stage: str, **flags: int) -> None:
            for name, value in flags.items():
                acct[name] = int(value)
            acct["failure_stage"] = stage

        def bill_solver_attempt(completed: int, stage: Optional[str]) -> None:
            acct["mission_solve_attempted"] = 1
            acct["mission_solve_completed"] = int(completed)
            acct["billable_physical_calls"] = 1
            acct["failure_stage"] = stage
            record["physical_call_count"] = 1
            self.last_physical_call_count = 1
            self.last_call_accounting = dict(acct)

        try:
            vector = self.design_vector(design)
        except (KeyError, TypeError, ValueError) as exc:
            mark("design_vector", request_rejected=1)
            record["status"] = STATUS_GEOMETRY_INVALID
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = ["design vector error: %s: %s" % (type(exc).__name__, exc)]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        violations = self.design_space.check_physical(
            {name: float(value) for name, value in zip(self.names, vector)}
        )
        if violations:
            mark("design_space", request_rejected=1)
            record["status"] = STATUS_GEOMETRY_INVALID
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = ["design space violation: %s" % str(item) for item in violations]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        try:
            expanded = self.design_space.expand(dict(zip(self.names, vector)))
            geometry = build_geometry(tuple(expanded), tuple(expanded.values()))
        except GeometryError as exc:
            mark("geometry_model", geometry_rejected=1)
            record["status"] = STATUS_GEOMETRY_INVALID
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = ["geometry error: %s" % exc]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        record["geometry_summary"] = {
            "wing_area_m2": geometry.wing.area_m2,
            "wing_span_m": geometry.wing.span_m,
            "wing_root_chord_m": geometry.wing.root_chord_m,
            "tail_area_m2": geometry.vertical_tail.area_m2,
            "fuselage_length_m": geometry.fuselage.length_m,
            "mass_model_status": geometry.mass_model_status,
        }

        try:
            _, vehicle = build_vehicle(geometry, module=self._template)
            configs = self._template.configs_setup(vehicle)
            analyses = self._template.analyses_setup(configs)
            analysis = analyses[self.task.cruise_config_tag]
            self._weight_settings = _disable_weight_preprocessing(analysis)
            mass_contract = apply_mass_contract(analysis.vehicle, self.task)
            record["mass_contract"] = mass_contract
        except (AdapterError, AttributeError, KeyError, TypeError) as exc:
            mark("analysis_build", mission_build_failed=1)
            record["status"] = STATUS_MISSION_BUILD_FAILED
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = [
                "analysis build error: %s: %s" % (type(exc).__name__, exc)
            ]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        try:
            mission, segment = build_single_cruise_mission(analyses, self.task)
        except MissionBuildError as exc:
            mark("mission_build", mission_build_failed=1)
            record["status"] = STATUS_MISSION_BUILD_FAILED
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = ["mission build error: %s" % exc]
            record["wall_seconds"] = time.perf_counter() - started
            return record
        except Exception as exc:
            mark("mission_build", mission_build_failed=1)
            record["status"] = STATUS_MISSION_BUILD_FAILED
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = [
                "mission build error: %s: %s" % (type(exc).__name__, exc)
            ]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        # From this point on the mission solver is actually invoked: even a
        # failed solve consumes one true evaluation.
        bill_solver_attempt(0, "mission_solve")
        try:
            mission.evaluate()
        except Exception as exc:
            record["status"] = STATUS_MISSION_FAILED
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = [
                "mission evaluation error: %s: %s" % (type(exc).__name__, exc)
            ]
            record["wall_seconds"] = time.perf_counter() - started
            return record
        acct["mission_solve_completed"] = 1
        acct["failure_stage"] = None
        self.last_call_accounting = dict(acct)

        try:
            # Observe real drag components when they are available in RCAIDE;
            # missing terms remain null (never synthesized from historical CD).
            aero_settings = getattr(getattr(analysis, "aerodynamics", None), "settings", None)
            observations = extract_observations(
                segment, self.task,
                reference_area_m2=geometry.wing.area_m2,
                trim_factor=getattr(aero_settings, "trim_drag_correction_factor", None),
            )
        except ObservationError as exc:
            mark("observation")
            record["status"] = STATUS_INVALID_OR_MISSING_RESPONSE
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = ["observation error: %s" % exc]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        try:
            cross_check = evaluate_geometry_cross_check(geometry, analysis.vehicle)
        except Exception as exc:
            mark("geometry_cross_check")
            record["status"] = STATUS_INVALID_OR_MISSING_RESPONSE
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = [
                "geometry cross-check error: %s: %s" % (type(exc).__name__, exc)
            ]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        record["geometry_cross_check"] = {
            "checked_count": cross_check["checked_count"],
            "failed_count": cross_check["failed_count"],
            "failures": cross_check["failures"],
        }
        record["responses"] = observations
        if cross_check["failed_count"] > 0:
            mark("geometry_mismatch")
            record["status"] = STATUS_GEOMETRY_MISMATCH
            record["constraints"] = empty_constraints(1.0)
            record["diagnostics"] = [
                "RCAIDE re-derived geometry differs from the requested design for %d checks"
                % cross_check["failed_count"]
            ]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        constraints = evaluate_constraints(self.task, observations)
        record["constraints"] = constraints
        if not mission_converged(observations):
            mark("mission_not_converged")
            record["status"] = STATUS_MISSION_NOT_CONVERGED
            record["objective"] = None
            record["feasible"] = False
            record["diagnostics"] = [
                "mission, solver or residual acceptance failed "
                "(converged=%s, solver_converged=%s, residual_max=%s); no objective is reported"
                % (
                    observations.get("converged"),
                    observations.get("solver_converged"),
                    observations.get("residual_max"),
                )
            ]
            record["wall_seconds"] = time.perf_counter() - started
            return record

        record["status"] = STATUS_VALID
        record["objective"] = float(observations["fuel_burn_kg"])
        record["feasible"] = feasibility(constraints)
        record["wall_seconds"] = time.perf_counter() - started
        return record
