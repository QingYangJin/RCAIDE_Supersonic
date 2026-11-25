"""RCAIDE-native supersonic VLM backend (V1L lineage, dreal006 backend v2).

Replaces VSPAERO as the aerodynamic evaluator for the whole downstream stack
(optimization and meta-learning labels).  Every number this module returns comes
from RCAIDE's own Vortex_Lattice_Method with the surrogate disabled, so the
supersonic kernel (B2 = mach**2 - 1) is exercised directly.

Design notes that matter for correctness
---------------------------------------
* The objective is the Trefftz-plane induced drag coefficient at a *fixed* lift
  coefficient, with alpha solved per design.  Trefftz CDi carries no wave drag
  (VLM.py:563 documents that the formula is exact only in the incompressible
  limit), and RCAIDE's own compressibility term returns NaN on this vehicle
  (compressibility_drag.py:129 -> :367 reads a None lift.spanwise), so the
  objective is named CDi_trefftz and is never presented as total drag.
* The lattice is fixed by the caller and recorded in every record.  A single
  discretisation is reused for all designs so that differences between designs
  are not contaminated by lattice changes; absolute values carry the lattice
  error, differences largely do not.
* Every solve is deterministic: same design, same lattice, same alpha -> same
  bits.  The backend therefore refuses to report a result it cannot reproduce.

Reference-quantity contract (dreal006-S0 fix)
--------------------------------------------
RCAIDE normalises lift by vehicle.reference_area (VLM.py:121, :438) and the
Trefftz induced drag by the same S_ref (VLM.py:441, :563).  The V1L backend
overwrote all three reference quantities with the *baseline* constants
(SREF 358.25 m^2, CREF 18.489893 m, BREF 25.604638 m) for every design.  With a
variable wing area that is a free lunch: a 420 m^2 wing produced 420 m^2 of lift
but was divided by 358.25 m^2, inflating CL by 1.172x, shrinking the alpha
needed for the target lift and systematically under-reporting CDi.  Version 2
therefore defaults to reference_mode="geometry": Sref/Cref/Bref come from the
evaluated geometry (wing planform area, MAC and span), the lift closure is
solved against that same Sref, and cdi_times_q_sref_N = q * Sref_used * CDi
uses it too.  The legacy reference_mode="frozen_baseline" is kept only so that
archived V1L evidence (which used the constant reference) can still be
reproduced bit for bit; it must never be used to rank designs with different
wing areas.
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

SCHEMA = "dreal006.rcaide_vlm_backend.v2"
BACKEND_VERSION = "2.0.0"


def rcaide_version_string() -> str:
    """Return the installed RCAIDE version without importing RCAIDE.

    Importing RCAIDE pulls in Framework.External_Interfaces.OpenVSP, whose
    module-level openvsp import runs CheckForVSPAERO and aborts the interpreter
    (exit 3, "Fatal Python error: Aborted").  Provenance only needs a version
    string, so read the VERSION file shipped next to RCAIDE/__init__.py and fall
    back to distribution metadata rather than paying for the import.
    """
    try:
        import importlib.util
        import os

        spec = importlib.util.find_spec("RCAIDE")
        if spec is not None and spec.origin:
            version_file = os.path.join(os.path.dirname(spec.origin), "VERSION")
            if os.path.exists(version_file):
                with open(version_file, "r", encoding="utf-8") as handle:
                    value = handle.read().strip()
                if value:
                    return value
    except (ImportError, OSError, ValueError):
        pass
    try:
        from importlib.metadata import version

        return version("RCAIDE")
    except Exception:
        return "unknown"


# Baseline reference quantities of the frozen 12D design space.  They are kept
# only as the historical V1L reference convention and as cross-check values; the
# default path recomputes Sref/Cref/Bref from the evaluated geometry.
SREF_M2 = 358.25
CREF_M = 18.489893
BREF_M = 25.604638

DEFAULT_LATTICE = (20, 10)  # (spanwise, chordwise); the agreed optimization baseline

REFERENCE_MODE_GEOMETRY = "geometry"
REFERENCE_MODE_FROZEN = "frozen_baseline"
REFERENCE_MODES = (REFERENCE_MODE_GEOMETRY, REFERENCE_MODE_FROZEN)

# One tolerance for the alpha secant and for the final lift-residual gate.  The
# V1L backend accepted 1e-7 on the normal exit and 1e-5 at the end of the loop,
# and returned a stale CL from the previous iteration.
ALPHA_TOL = 1.0e-7
MAX_ALPHA_STEPS = 30
# A task fixes the *lift force* it wants, not a CL: CL_target falls out of the
# per-design reference area as L_ref / (q * Sref_used).  Fixing CL instead would
# let a bigger wing fly a heavier aircraft and win the comparison by moving the
# goalposts.
LIFT_TARGET_MODES = ("coefficient", "force")
# The final re-solve must reproduce the target lift within this band, otherwise
# the label is rejected instead of being reported as VALID.
LIFT_RESIDUAL_TOL = 1.0e-6


def _digest(values: Sequence[float]) -> str:
    payload = ",".join("%.12g" % float(v) for v in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class SupersonicVLMBackend:
    """Fixed-task, fixed-lattice, alpha-solved RCAIDE VLM evaluator."""

    def __init__(
        self,
        repo_root: str,
        design_space_config: str,
        *,
        mach: float = 2.02,
        altitude_m: float = 18288.0,
        cl_target: float = 0.181743998494,
        lattice: Tuple[int, int] = DEFAULT_LATTICE,
        design_names: Optional[Sequence[str]] = None,
        reference_mode: str = REFERENCE_MODE_GEOMETRY,
        task_fingerprint: Optional[str] = None,
        lift_target_n: Optional[float] = None,
        lift_target_mode: str = "coefficient",
    ) -> None:
        import sys

        self.repo_root = repo_root
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        from research.concorde_metaopt.config_io import load_config
        from research.concorde_metaopt.aircraft import design_space as ds_module

        if reference_mode not in REFERENCE_MODES:
            raise ValueError(
                "reference_mode must be one of %s, got %r" % (list(REFERENCE_MODES), reference_mode)
            )
        if lift_target_mode not in LIFT_TARGET_MODES:
            raise ValueError(
                "lift_target_mode must be one of %s, got %r"
                % (list(LIFT_TARGET_MODES), lift_target_mode)
            )
        if lift_target_mode == "force":
            if lift_target_n is None:
                raise ValueError("lift_target_mode='force' needs lift_target_n")
            if not math.isfinite(float(lift_target_n)) or float(lift_target_n) <= 0.0:
                raise ValueError("lift_target_n must be finite and positive, got %r" % (lift_target_n,))
        self.reference_mode = reference_mode
        self.lift_target_mode = lift_target_mode
        self.lift_target_n = None if lift_target_n is None else float(lift_target_n)
        self.task_fingerprint = str(task_fingerprint) if task_fingerprint else "unset"

        # Load the design space through the real validator: no frozen bypass and
        # no os.chdir.  A frozen config must prove its freeze evidence and its
        # baseline hash, which the loader now checks.
        data = load_config(design_space_config)
        self.space = ds_module.design_space_from_config(data, source=str(design_space_config))
        self.design_space_fingerprint = hashlib.sha256(
            repr(sorted(self.space.config_summary().items())).encode("utf-8")
        ).hexdigest()[:16]
        self.design_names = list(design_names or self.space.names)
        self._declared_baseline = {
            variable.name: float(variable.baseline) for variable in self.space.variables
        }
        self.mach = float(mach)
        self.altitude_m = float(altitude_m)
        self.cl_target = float(cl_target)
        self.lattice = (int(lattice[0]), int(lattice[1]))

        from RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976 import US_Standard_1976

        atm = US_Standard_1976().compute_values(self.altitude_m)
        flat = lambda x: float(np.ravel(np.asarray(x, dtype=float))[0])
        self._atmo = {
            "temperature_K": flat(atm.temperature),
            "pressure_Pa": flat(atm.pressure),
            "density_kg_m3": flat(atm.density),
            "speed_of_sound_m_s": flat(atm.speed_of_sound),
            "dynamic_viscosity_Pa_s": flat(atm.dynamic_viscosity),
            "kinematic_viscosity_m2_s": flat(atm.kinematic_viscosity),
        }
        self._atmo["velocity_m_s"] = self.mach * self._atmo["speed_of_sound_m_s"]
        self._atmo["dynamic_pressure_Pa"] = 0.5 * self._atmo["density_kg_m3"] * self._atmo["velocity_m_s"] ** 2

        from research.concorde_metaopt.aircraft.concorde_adapter import (
            EXPECTED_SHA256,
            file_sha256,
            load_template_module,
            resolve_tutorial_path,
        )

        self._expected_template_sha256 = EXPECTED_SHA256
        self._template_path = str(resolve_tutorial_path(self.repo_root))
        self._template_sha256 = file_sha256(self._template_path)
        # Verified load: the adapter refuses a template whose bytes are not the
        # recorded baseline, and provenance reports the digest that was checked.
        self._module = load_template_module(self.repo_root, verify_hash=True)
        self._template_hash_verified = self._template_sha256 == EXPECTED_SHA256

        self._vehicles: Dict[str, Tuple[Any, Dict[str, float]]] = {}
        self.cache: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        self.solve_count = 0
        self.build_count = 0
        self.wall_seconds = 0.0

    # -- geometry ---------------------------------------------------------
    def _vehicle(self, x12: Mapping[str, float]) -> Tuple[Any, str, Dict[str, float]]:
        from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle
        from research.concorde_metaopt.aircraft.geometry_model import build_geometry

        key = _digest([x12[n] for n in self.design_names])
        if key in self._vehicles:
            cached_vehicle, cached_refs = self._vehicles[key]
            return cached_vehicle, key, dict(cached_refs)
        # A declared subspace may be narrower than the 12D schema.  Variables the
        # caller did not hand over stay at their frozen config baseline; they are
        # never read from the caller, so an active 5D search cannot perturb the
        # seven held dimensions by accident.
        subspace = {n: float(x12[n]) for n in self.design_names}
        full = dict(self._declared_baseline)
        full.update(subspace)
        expanded = self.space.expand(full)
        geometry = build_geometry(tuple(expanded), tuple(expanded.values()))
        _, vehicle = build_vehicle(geometry, module=self._module)
        if vehicle.wings:
            # Imported lazily and only when a wing exists: importing RCAIDE
            # geometry pulls in Framework.External_Interfaces.OpenVSP, and that
            # module-level openvsp import can abort the interpreter the first time
            # it runs in a process.  A stubbed vehicle with no wings never needs it.
            from RCAIDE.Library.Methods.Geometry.Planform.wing_planform import wing_planform

            for wing in vehicle.wings:
                wing_planform(wing)  # fills areas.projected that the VLM paneliser requires

        if self.reference_mode == REFERENCE_MODE_FROZEN:
            refs = {"Sref_m2": SREF_M2, "Cref_m": CREF_M, "Bref_m": BREF_M}
        else:
            refs = {
                "Sref_m2": float(geometry.wing.area_m2),
                "Cref_m": float(geometry.wing.mean_aerodynamic_chord_m),
                "Bref_m": float(geometry.wing.span_m),
            }
        for name, value in refs.items():
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("non-physical reference quantity %s=%r" % (name, value))
        # One reference convention for the whole chain: RCAIDE divides CL and CDi
        # by vehicle.reference_area, and the reported force uses the same Sref.
        vehicle.reference_area = refs["Sref_m2"]
        vehicle.reference_chord = refs["Cref_m"]
        vehicle.reference_span = refs["Bref_m"]
        self.build_count += 1
        self._vehicles[key] = (vehicle, dict(refs))
        return vehicle, key, dict(refs)

    # -- one VLM solve ----------------------------------------------------
    def _solve(self, vehicle: Any, alpha_deg: float) -> Tuple[float, float]:
        from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
        from RCAIDE.Framework.Mission.Common.Results import Results
        from RCAIDE.Framework.Core import Data

        aer = Vortex_Lattice_Method()
        aer.settings.use_surrogate = False
        aer.settings.number_of_spanwise_vortices = self.lattice[0]
        aer.settings.number_of_chordwise_vortices = self.lattice[1]
        aer.vehicle = vehicle
        aer.initialize(vehicle)

        a = self._atmo
        state = Data()
        state.conditions = Results()
        state.analyses = Data()
        c = state.conditions
        for name, value in (
            ("altitude", self.altitude_m),
            ("mach_number", self.mach),
            ("velocity", a["velocity_m_s"]),
            ("temperature", a["temperature_K"]),
            ("pressure", a["pressure_Pa"]),
            ("density", a["density_kg_m3"]),
            ("speed_of_sound", a["speed_of_sound_m_s"]),
            ("dynamic_pressure", a["dynamic_pressure_Pa"]),
            ("gravity", 9.81),
            ("dynamic_viscosity", a["dynamic_viscosity_Pa_s"]),
            ("kinematic_viscosity", a["kinematic_viscosity_m2_s"]),
        ):
            setattr(c.freestream, name, np.array([[value]]))
        cref = float(getattr(vehicle, "reference_chord", 0.0) or 0.0)
        if not math.isfinite(cref) or cref <= 0.0:
            raise ValueError("vehicle.reference_chord must be positive, got %r" % cref)
        c.freestream.reynolds_number = np.array(
            [[a["density_kg_m3"] * a["velocity_m_s"] * cref / a["dynamic_viscosity_Pa_s"]]]
        )
        c.aerodynamics.angles.alpha = np.array([[math.radians(alpha_deg)]])
        c.aerodynamics.angles.beta = np.array([[0.0]])
        c.aerodynamics.angles.bank = np.array([[0.0]])

        from RCAIDE.Library.Methods.Aerodynamics.Vortex_Lattice_Method.VLM import VLM

        result = VLM(c, aer.settings, vehicle)
        self.solve_count += 1
        # results.CL is the pitching-moment coefficient (VLM.py:460); the lift
        # coefficient is CLift (VLM.py:438).
        return float(result.CLift[0][0]), float(result.CDrag_induced[0][0])

    def cl_target_for(self, refs: Mapping[str, float]) -> float:
        """The CL this task asks of this design.

        In coefficient mode the task names a CL directly (legacy V1L behaviour).
        In force mode the task names a lift force and the CL follows from the
        design's own reference area, so two designs are compared at the same
        physical lift rather than at the same coefficient.
        """
        if self.lift_target_mode == "force":
            q = self._atmo["dynamic_pressure_Pa"]
            sref = float(refs["Sref_m2"])
            if not math.isfinite(q) or q <= 0.0 or not math.isfinite(sref) or sref <= 0.0:
                raise ValueError("cannot convert lift force: q=%r Sref=%r" % (q, sref))
            return self.lift_target_n / (q * sref)
        return self.cl_target

    # -- alpha solve ------------------------------------------------------
    def _alpha_for_lift(self, vehicle: Any, cl_target: float, alpha_guess: float = 5.0) -> Dict[str, Any]:
        """Secant solve for the angle of attack that hits cl_target.

        The returned cl is always the CL evaluated at the returned alpha_deg.
        V1L returned a stale cl1 from the previous iteration whenever the loop
        fell through, which made the lift residual meaningless.
        """
        lo, hi = 0.5, 12.0
        hist: List[Tuple[float, float]] = []
        x0 = min(max(alpha_guess, lo), hi)
        cl0, _ = self._solve(vehicle, x0)
        hist.append((x0, cl0))
        f0 = cl0 - cl_target
        if abs(f0) <= ALPHA_TOL:
            return {"alpha_deg": x0, "cl": cl0, "iterations": 1, "ok": True, "history": hist}
        x1 = min(max(x0 + 0.5 if cl0 < cl_target else x0 - 0.5, lo), hi)
        cl1, _ = self._solve(vehicle, x1)
        hist.append((x1, cl1))
        f1 = cl1 - cl_target
        for _step in range(MAX_ALPHA_STEPS):
            if abs(f1) <= ALPHA_TOL:
                break
            denom = f1 - f0
            if abs(denom) < 1e-14:
                break
            x2 = x1 - f1 * (x1 - x0) / denom
            if not (lo <= x2 <= hi):
                x2 = 0.5 * (x0 + x1)
            cl2, _ = self._solve(vehicle, x2)
            hist.append((x2, cl2))
            x0, cl0, f0 = x1, cl1, f1
            x1, cl1, f1 = x2, cl2, cl2 - cl_target
        return {
            "alpha_deg": x1,
            "cl": cl1,
            "iterations": len(hist),
            "ok": abs(f1) <= ALPHA_TOL,
            "history": hist,
        }

    # -- public API -------------------------------------------------------
    def _cache_key(self, design_key: str, refs: Mapping[str, float], cl_target: float) -> Tuple[Any, ...]:
        """Bind the cache entry to everything that can change the number.

        The V1L key was (design_key, spanwise, chordwise), so the same design
        evaluated at a different Mach, altitude, lift target, reference mode or
        geometry would silently return the old objective.
        """
        return (
            design_key,
            self.task_fingerprint,
            self.design_space_fingerprint,
            "%.12g" % self.mach,
            "%.9g" % self.altitude_m,
            "%.12g" % cl_target,
            self.lift_target_mode,
            "unset" if self.lift_target_n is None else "%.12g" % self.lift_target_n,
            self.reference_mode,
            "%.12g" % refs["Sref_m2"],
            "%.12g" % refs["Cref_m"],
            "%.12g" % refs["Bref_m"],
            self.lattice[0],
            self.lattice[1],
            BACKEND_VERSION,
        )

    def evaluate(self, x12: Mapping[str, float], *, purpose: str = "search") -> Dict[str, Any]:
        started = time.perf_counter()
        design = {n: float(x12[n]) for n in self.design_names}
        record: Dict[str, Any] = {
            "schema": SCHEMA,
            "backend_version": BACKEND_VERSION,
            "purpose": purpose,
            "design": design,
            "design_key": _digest([design[n] for n in self.design_names]),
            "lattice": {"spanwise": self.lattice[0], "chordwise": self.lattice[1]},
            "mach": self.mach,
            "altitude_m": self.altitude_m,
            "cl_target": None,
            "lift_target_n": self.lift_target_n,
            "lift_target_mode": self.lift_target_mode,
            "task_fingerprint": self.task_fingerprint,
            "design_space_fingerprint": self.design_space_fingerprint,
            "reference_mode": self.reference_mode,
            "sref_used_m2": None,
            "cref_used_m": None,
            "bref_used_m": None,
            "objective_name": "CDi_trefftz",
            "objective": None,
            "cl_actual": None,
            "alpha_deg": None,
            "alpha_iterations": None,
            "lift_residual": None,
            "lift_residual_tol": LIFT_RESIDUAL_TOL,
            "status": "FAILED",
            "diagnostics": [],
            "wall_seconds": 0.0,
            "cached": False,
        }
        try:
            vehicle, _key, refs = self._vehicle(design)
            record.update(
                sref_used_m2=float(refs["Sref_m2"]),
                cref_used_m=float(refs["Cref_m"]),
                bref_used_m=float(refs["Bref_m"]),
            )
            cl_target = self.cl_target_for(refs)
            record["cl_target"] = float(cl_target)
            cache_key = self._cache_key(record["design_key"], refs, cl_target)
            if cache_key in self.cache:
                hit = dict(self.cache[cache_key])
                hit["cached"] = True
                hit["purpose"] = purpose
                hit["wall_seconds"] = round(time.perf_counter() - started, 3)
                return hit

            solve = self._alpha_for_lift(vehicle, cl_target)
            record["alpha_deg"] = float(solve["alpha_deg"])
            record["cl_actual"] = float(solve["cl"])
            record["alpha_iterations"] = int(solve["iterations"])
            if not solve["ok"]:
                record["status"] = "ALPHA_SOLVE_FAILED"
                record["diagnostics"].append(
                    "secant did not place CL within %g of %.12g in %d steps"
                    % (ALPHA_TOL, cl_target, MAX_ALPHA_STEPS)
                )
                return record

            cl, cdi = self._solve(vehicle, solve["alpha_deg"])
            record["cl_actual"] = float(cl)
            residual = abs(cl - cl_target)
            record["lift_residual"] = residual
            if not math.isfinite(residual) or residual > LIFT_RESIDUAL_TOL:
                # A label whose lift closure is broken must not be reported as valid:
                # the CDi belongs to a different lift level than the task asked for.
                record["status"] = "LIFT_RESIDUAL_REJECTED"
                record["diagnostics"].append(
                    "final |CL - CL_target| = %.6g exceeds %g" % (residual, LIFT_RESIDUAL_TOL)
                )
                return record
            if not math.isfinite(cdi) or cdi <= 0.0:
                record["status"] = "NON_PHYSICAL_CDI"
                record["diagnostics"].append("CDi=%.6g is not finite and positive" % cdi)
                return record
            record.update(
                objective=float(cdi),
                status="VALID",
            )
            # L = q * Sref * CL and J = q * Sref * CDi must share one Sref.
            record["lift_times_q_sref_N"] = float(cl) * self._atmo["dynamic_pressure_Pa"] * refs["Sref_m2"]
            record["cdi_times_q_sref_N"] = float(cdi) * self._atmo["dynamic_pressure_Pa"] * refs["Sref_m2"]
            self.cache[cache_key] = dict(record)
        except Exception as exc:  # geometry/VLM failures must not escape as exceptions
            record["status"] = "ERROR"
            record["diagnostics"].append("%s: %s" % (type(exc).__name__, str(exc)[:400]))
        finally:
            spent = time.perf_counter() - started
            record["wall_seconds"] = round(spent, 3)
            self.wall_seconds += spent
        return record

    def provenance(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "backend_version": BACKEND_VERSION,
            "backend": "RCAIDE.Vortex_Lattice_Method",
            "use_surrogate": False,
            "rcaide_version": rcaide_version_string(),
            "lattice": {"spanwise": self.lattice[0], "chordwise": self.lattice[1]},
            "mach": self.mach,
            "altitude_m": self.altitude_m,
            "cl_target_mode": self.lift_target_mode,
            "cl_target": self.cl_target if self.lift_target_mode == "coefficient" else None,
            "lift_target_n": self.lift_target_n,
            "task_fingerprint": self.task_fingerprint,
            "design_names": list(self.design_names),
            "held_at_baseline": sorted(set(self._declared_baseline) - set(self.design_names)),
            "design_space": {
                "config_path": self.space.config_path,
                "design_set": self.space.design_set,
                "frozen": self.space.frozen,
                "bounds_status": self.space.bounds_status,
                "fingerprint": self.design_space_fingerprint,
            },
            "objective_name": "CDi_trefftz",
            "objective_is_total_drag": False,
            "wave_drag_included": False,
            "reference_mode": self.reference_mode,
            "reference": {
                "basis": "per-design wing planform" if self.reference_mode == REFERENCE_MODE_GEOMETRY else "frozen baseline constants",
                "baseline_SREF_m2": SREF_M2,
                "baseline_CREF_m": CREF_M,
                "baseline_BREF_m": BREF_M,
            },
            "alpha_tolerance": ALPHA_TOL,
            "max_alpha_steps": MAX_ALPHA_STEPS,
            "lift_residual_tolerance": LIFT_RESIDUAL_TOL,
            "atmosphere": dict(self._atmo),
            "template_path": self._template_path,
            "template_sha256": self._template_sha256,
            "template_expected_sha256": self._expected_template_sha256,
            "template_hash_verified": bool(self._template_hash_verified),
        }
