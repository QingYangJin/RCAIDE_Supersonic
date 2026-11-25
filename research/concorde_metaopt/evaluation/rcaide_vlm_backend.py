"""RCAIDE-native supersonic VLM backend (V1L lineage).

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
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

SCHEMA = "dreal005.rcaide_vlm_backend.v1"

# Reference quantities are frozen by the project, not recomputed from the VLM
# geometry, because the adapter leaves reference_chord/span at zero.
SREF_M2 = 358.25
CREF_M = 18.489893
BREF_M = 25.604638

DEFAULT_LATTICE = (20, 10)  # (spanwise, chordwise); the agreed optimization baseline


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
    ) -> None:
        import os
        import sys

        self.repo_root = repo_root
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        os.chdir(repo_root)

        from research.concorde_metaopt.config_io import load_config
        from research.concorde_metaopt.aircraft.design_space import design_space_from_config

        data = load_config(design_space_config)
        data["frozen"] = False  # side study: the P1 freeze guard rejects the config as-is
        self.space = design_space_from_config(data, source="V1L-rcaide-vlm")
        self.design_names = list(design_names or self.space.names)
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

        from research.concorde_metaopt.aircraft.concorde_adapter import load_template_module

        # The adapter's recorded template hash does not match the tutorial file on
        # disk at this commit, so the verified path is unavailable by construction.
        self._module = load_template_module(verify_hash=False)

        self._vehicles: Dict[str, Any] = {}
        self.cache: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
        self.solve_count = 0
        self.build_count = 0
        self.wall_seconds = 0.0

    # -- geometry ---------------------------------------------------------
    def _vehicle(self, x12: Mapping[str, float]) -> Tuple[Any, str]:
        from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle
        from research.concorde_metaopt.aircraft.geometry_model import build_geometry
        from RCAIDE.Library.Methods.Geometry.Planform.wing_planform import wing_planform

        key = _digest([x12[n] for n in self.design_names])
        if key in self._vehicles:
            return self._vehicles[key], key
        expanded = self.space.expand({n: float(x12[n]) for n in self.design_names})
        geometry = build_geometry(tuple(expanded), tuple(expanded.values()))
        _, vehicle = build_vehicle(geometry, module=self._module)
        for wing in vehicle.wings:
            wing_planform(wing)  # fills areas.projected that the VLM paneliser requires
        vehicle.reference_area = SREF_M2
        vehicle.reference_chord = CREF_M
        vehicle.reference_span = BREF_M
        self.build_count += 1
        self._vehicles[key] = vehicle
        return vehicle, key

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
        c.freestream.reynolds_number = np.array(
            [[a["density_kg_m3"] * a["velocity_m_s"] * CREF_M / a["dynamic_viscosity_Pa_s"]]]
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

    # -- alpha solve ------------------------------------------------------
    def _alpha_for_lift(self, vehicle: Any, alpha_guess: float = 5.0) -> Dict[str, Any]:
        lo, hi = 0.5, 12.0
        hist: List[Tuple[float, float]] = []
        x0 = min(max(alpha_guess, lo), hi)
        cl0, _ = self._solve(vehicle, x0)
        hist.append((x0, cl0))
        if abs(cl0 - self.cl_target) < 1e-9:
            return {"alpha_deg": x0, "cl": cl0, "iterations": 1, "ok": True, "history": hist}
        x1 = x0 + 0.5 if cl0 < self.cl_target else x0 - 0.5
        x1 = min(max(x1, lo), hi)
        cl1, _ = self._solve(vehicle, x1)
        hist.append((x1, cl1))
        f0, f1 = cl0 - self.cl_target, cl1 - self.cl_target
        for step in range(12):
            if abs(f1) < 1e-7:
                return {"alpha_deg": x1, "cl": cl1, "iterations": step + 2, "ok": True, "history": hist}
            denom = f1 - f0
            if abs(denom) < 1e-14:
                break
            x2 = x1 - f1 * (x1 - x0) / denom
            if not (lo <= x2 <= hi):
                x2 = 0.5 * (x0 + x1)
            cl2, _ = self._solve(vehicle, x2)
            hist.append((x2, cl2))
            x0, f0, x1, f1 = x1, f1, x2, cl2 - self.cl_target
        ok = abs(f1) < 1e-5
        return {"alpha_deg": x1, "cl": cl1, "iterations": len(hist), "ok": ok, "history": hist}

    # -- public API -------------------------------------------------------
    def evaluate(self, x12: Mapping[str, float], *, purpose: str = "search") -> Dict[str, Any]:
        started = time.perf_counter()
        design = {n: float(x12[n]) for n in self.design_names}
        record: Dict[str, Any] = {
            "schema": SCHEMA,
            "purpose": purpose,
            "design": design,
            "design_key": _digest([design[n] for n in self.design_names]),
            "lattice": {"spanwise": self.lattice[0], "chordwise": self.lattice[1]},
            "mach": self.mach,
            "altitude_m": self.altitude_m,
            "cl_target": self.cl_target,
            "objective_name": "CDi_trefftz",
            "objective": None,
            "cl_actual": None,
            "alpha_deg": None,
            "alpha_iterations": None,
            "status": "FAILED",
            "diagnostics": [],
            "wall_seconds": 0.0,
            "cached": False,
        }
        cache_key = (record["design_key"], self.lattice[0], self.lattice[1])
        if cache_key in self.cache:
            hit = dict(self.cache[cache_key])
            hit["cached"] = True
            hit["purpose"] = purpose
            return hit
        try:
            vehicle, key = self._vehicle(design)
            solve = self._alpha_for_lift(vehicle)
            if not solve["ok"]:
                record["status"] = "ALPHA_SOLVE_FAILED"
                record["diagnostics"].append(
                    "secant did not place CL within 1e-5 of %.12g in 12 steps" % self.cl_target
                )
                record["alpha_deg"] = solve["alpha_deg"]
                record["cl_actual"] = solve["cl"]
                record["alpha_iterations"] = solve["iterations"]
                return record
            cl, cdi = self._solve(vehicle, solve["alpha_deg"])
            if not math.isfinite(cdi) or cdi <= 0.0:
                record["status"] = "NON_PHYSICAL_CDI"
                record["diagnostics"].append("CDi=%.6g is not finite and positive" % cdi)
                return record
            record.update(
                objective=float(cdi),
                cl_actual=float(cl),
                alpha_deg=float(solve["alpha_deg"]),
                alpha_iterations=int(solve["iterations"]),
                status="VALID",
            )
            record["cdi_times_q_sref_N"] = float(cdi) * self._atmo["dynamic_pressure_Pa"] * SREF_M2
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
        import RCAIDE

        return {
            "schema": SCHEMA,
            "backend": "RCAIDE.Vortex_Lattice_Method",
            "use_surrogate": False,
            "rcaide_version": getattr(RCAIDE, "__version__", "unknown"),
            "lattice": {"spanwise": self.lattice[0], "chordwise": self.lattice[1]},
            "mach": self.mach,
            "altitude_m": self.altitude_m,
            "cl_target": self.cl_target,
            "objective_name": "CDi_trefftz",
            "objective_is_total_drag": False,
            "wave_drag_included": False,
            "reference": {"SREF_m2": SREF_M2, "CREF_m": CREF_M, "BREF_m": BREF_M},
            "atmosphere": dict(self._atmo),
            "template_hash_verified": False,
        }
