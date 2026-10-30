"""Build and observe the single fixed-cruise mission.

One evaluation creates a fresh RCAIDE vehicle, mission and solver state so no
warm start or cached vehicle state can leak between design candidates.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .contract import RESIDUAL_LIMIT
from .drag_ledger import build_drag_ledger


class MissionBuildError(RuntimeError):
    """Raised when the fixed-cruise mission cannot be assembled."""


class ObservationError(RuntimeError):
    """Raised when a mission ran but did not return a complete finite history."""


def build_single_cruise_mission(analyses: Any, task: Any) -> Tuple[Any, Any]:
    """Build the one-segment constant-Mach constant-altitude cruise mission."""
    import RCAIDE

    segments_module = RCAIDE.Framework.Mission.Segments
    mission = RCAIDE.Framework.Mission.Sequential_Segments()
    mission.tag = "single_fixed_cruise"
    base_segment = segments_module.Segment()
    segment = segments_module.Cruise.Constant_Mach_Constant_Altitude(base_segment)
    segment.tag = "level_cruise"

    try:
        analysis = analyses[task.cruise_config_tag]
    except Exception as exc:  # KeyError, TypeError, or Container failure
        raise MissionBuildError(
            "analysis container misses config tag %r" % task.cruise_config_tag
        ) from exc
    segment.analyses.extend(analysis)

    segment.altitude = float(task.cruise_altitude_m)
    segment.mach_number = float(task.cruise_mach)
    segment.distance = float(task.cruise_distance_m)
    segment.flight_dynamics.force_x = True
    segment.flight_dynamics.force_z = True
    segment.assigned_control_variables.throttle.active = True
    segment.assigned_control_variables.throttle.assigned_propulsors = [
        list(task.propulsor_tags)
    ]
    segment.assigned_control_variables.pitch_angle.active = True
    segment.state.numerics.solver.print_output = False

    mission.append_segment(segment)
    return mission, segment


def _finite_array(value: Any, name: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ObservationError("%s is not numeric: %r" % (name, value)) from exc
    array = np.squeeze(array)
    if array.ndim == 0:
        array = array.reshape(1)
    if array.ndim != 1:
        raise ObservationError("%s has unexpected shape %s" % (name, array.shape))
    if array.size < 2:
        raise ObservationError("%s has fewer than two samples" % name)
    if not np.all(np.isfinite(array)):
        raise ObservationError("%s contains non-finite values" % name)
    return array


def _column(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    array = np.squeeze(array)
    if array.ndim == 0:
        array = array.reshape(1)
    if array.ndim == 2:
        if array.shape[1] == 3:
            array = array[:, 0]
        else:
            raise ObservationError("%s has unexpected shape %s" % (name, array.shape))
    if array.ndim != 1 or array.size < 1:
        raise ObservationError("%s has unexpected shape %s" % (name, np.shape(value)))
    if not np.all(np.isfinite(array)):
        raise ObservationError("%s contains non-finite values" % name)
    return array


def _last(value: Any, name: str) -> float:
    return float(_finite_array(value, name)[-1])


def extract_observations(
    segment: Any,
    task: Any,
    reference_area_m2: Optional[float] = None,
    trim_factor: Optional[float] = None,
) -> Dict[str, Any]:
    """Extract the frozen observation record from a completed cruise segment."""
    conditions = segment.state.conditions
    try:
        mass = _finite_array(conditions.weights.vehicle.mass, "weights.vehicle.mass")
        aircraft_range = _finite_array(
            conditions.frames.inertial.aircraft_range, "frames.inertial.aircraft_range"
        )
        time = _finite_array(conditions.frames.inertial.time, "frames.inertial.time")
    except AttributeError as exc:
        raise ObservationError("mission conditions miss a required history: %s" % exc) from exc

    if not (mass.size == aircraft_range.size == time.size):
        raise ObservationError(
            "history lengths differ: mass %d, range %d, time %d"
            % (mass.size, aircraft_range.size, time.size)
        )
    if mass[0] <= 0.0 or mass[-1] <= 0.0:
        raise ObservationError("mass history is not strictly positive")
    if mass[-1] > mass[0] * (1.0 + 1.0e-9):
        raise ObservationError(
            "mass increased during cruise: %r -> %r" % (mass[0], mass[-1])
        )
    if aircraft_range[-1] < aircraft_range[0] - 1.0e-6:
        raise ObservationError("aircraft range decreased during cruise")
    if time[-1] < time[0]:
        raise ObservationError("mission time decreased during cruise")

    try:
        residuals = np.asarray(segment.state.residuals.pack_array(), dtype=float)
        residual_max = float(np.max(np.abs(np.squeeze(residuals)))) if residuals.size else float("nan")
    except Exception as exc:
        raise ObservationError("residuals are unavailable: %s" % exc) from exc
    if not math.isfinite(residual_max):
        raise ObservationError("residual norm is not finite")

    propulsors: Dict[str, Any] = {}
    max_throttle = -math.inf
    max_fuel_flow = -math.inf
    max_thrust_x = -math.inf
    for tag in task.propulsor_tags:
        try:
            propulsor_conditions = conditions.energy.propulsors[tag]
        except Exception as exc:
            raise ObservationError("propulsor conditions miss %r" % tag) from exc
        throttle = _finite_array(propulsor_conditions.throttle, "throttle[%s]" % tag)
        fuel_flow = _finite_array(
            propulsor_conditions.fuel_mass_flow_rate, "fuel_mass_flow_rate[%s]" % tag
        )
        try:
            thrust = _column(propulsor_conditions.thrust, "thrust[%s]" % tag)
        except (ObservationError, AttributeError):
            try:
                thrust = _column(
                    propulsor_conditions.thrust_force, "thrust_force[%s]" % tag
                )
            except AttributeError as exc:
                raise ObservationError(
                    "propulsor %r has neither thrust nor thrust_force" % tag
                ) from exc
        if throttle.size != fuel_flow.size or thrust.size != fuel_flow.size:
            raise ObservationError("propulsor %r history lengths differ" % tag)
        max_throttle = max(max_throttle, float(np.max(throttle)))
        max_fuel_flow = max(max_fuel_flow, float(np.max(fuel_flow)))
        max_thrust_x = max(max_thrust_x, float(np.max(thrust)))
        propulsors[tag] = {
            "max_throttle": float(np.max(throttle)),
            "max_fuel_mass_flow_kg_s": float(np.max(fuel_flow)),
            "max_thrust_x_n": float(np.max(thrust)),
        }

    if not math.isfinite(max_throttle) or max_throttle < 0.0:
        raise ObservationError("maximum throttle is invalid: %r" % max_throttle)
    if not math.isfinite(max_fuel_flow) or max_fuel_flow <= 0.0:
        raise ObservationError("maximum fuel flow must be positive: %r" % max_fuel_flow)
    if not math.isfinite(max_thrust_x) or max_thrust_x <= 0.0:
        raise ObservationError("maximum thrust must be positive: %r" % max_thrust_x)

    try:
        alpha_end_deg = math.degrees(_last(conditions.aerodynamics.angles.alpha, "alpha"))
        cl_end = _last(conditions.aerodynamics.coefficients.lift.total, "lift.total")
        cd_end = _last(conditions.aerodynamics.coefficients.drag.total, "drag.total")
    except AttributeError as exc:
        raise ObservationError("aerodynamic history is incomplete: %s" % exc) from exc

    converged = bool(segment.converged)
    solver_converged = bool(segment.state.numerics.solver.converged)
    mass_start = float(mass[0])
    mass_end = float(mass[-1])
    fuel_burn = mass_start - mass_end

    return {
        "objective_name": task.objective_name,
        "objective_unit": task.objective_unit,
        "mass_start_kg": mass_start,
        "mass_end_kg": mass_end,
        "fuel_burn_kg": fuel_burn,
        "range_start_m": float(aircraft_range[0]),
        "range_end_m": float(aircraft_range[-1]),
        "range_span_m": float(aircraft_range[-1] - aircraft_range[0]),
        "time_start_s": float(time[0]),
        "time_end_s": float(time[-1]),
        "time_span_s": float(time[-1] - time[0]),
        "max_throttle": max_throttle,
        "max_fuel_mass_flow_kg_s": max_fuel_flow,
        "max_thrust_x_n": max_thrust_x,
        "alpha_end_deg": alpha_end_deg,
        "lift_coefficient_end": cl_end,
        "drag_coefficient_end": cd_end,
        "drag_ledger": build_drag_ledger(
            conditions, reference_area_m2=reference_area_m2,
            trim_factor=trim_factor,
        ),
        "converged": converged,
        "solver_converged": solver_converged,
        "residual_max": residual_max,
        "propulsors": propulsors,
        "history_samples": int(mass.size),
        "residual_limit": RESIDUAL_LIMIT,
    }
