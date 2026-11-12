"""TaskSpec for the D-REAL-001 fixed cruise / lift-matched D_i objective."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .constants import (
    ALPHA_PRIMARY_DEG,
    ALPHA_REFINE_DEG,
    BREF_M,
    CREF_M,
    LIFT_TOL_REL,
    L_REF_N,
    MAX_LAUNCHES_PER_DESIGN,
    MAX_REFINE_SWEEPS,
    Q_PA_DEFAULT,
    REFERENCE_FRAME,
    SREF_BASELINE_M2,
    XCG_M,
)
from .records import canonical_json, sha256_bytes, solver_config_hash


def isa_atmosphere(altitude_m: float) -> Dict[str, float]:
    """ISA 1976 up to 20 km (sufficient for the 18.288 km cruise)."""
    h = float(altitude_m)
    if not (0.0 <= h <= 20000.0):
        raise ValueError("ISA layer implemented for 0..20000 m, got %r" % (h,))
    g0 = 9.80665
    r_specific = 287.05287
    if h <= 11000.0:
        temperature = 288.15 - 0.0065 * h
        pressure = 101325.0 * (temperature / 288.15) ** (g0 / (r_specific * 0.0065))
    else:
        temperature = 216.65
        pressure_11 = 22632.06
        pressure = pressure_11 * math.exp(-g0 * (h - 11000.0) / (r_specific * temperature))
    rho = pressure / (r_specific * temperature)
    sound = math.sqrt(1.4 * r_specific * temperature)
    return {"temperature_k": temperature, "pressure_pa": pressure, "rho_kg_m3": rho, "sound_m_s": sound}


def isa_q_pa(mach: float, altitude_m: float) -> float:
    atmosphere = isa_atmosphere(altitude_m)
    velocity = float(mach) * atmosphere["sound_m_s"]
    return 0.5 * atmosphere["rho_kg_m3"] * velocity * velocity


DEFAULT_SOLVER_CONFIG: Dict[str, Any] = {
    "solver": "vspaero",
    "version": "7.2.2",
    "openvsp_version": "3.55.0",
    "mach": 2.02,
    "geom_set": "thick",
    "sref_policy": "design_dependent_from_geometry",
    "cref_m": CREF_M,
    "bref_m": BREF_M,
    "xcg_m": XCG_M,
    "reference_frame": REFERENCE_FRAME,
    "reference_area": "main_wing_reference",
    "alpha_primary_deg": list(ALPHA_PRIMARY_DEG),
    "alpha_refine_deg": list(ALPHA_REFINE_DEG),
    "max_refine_sweeps": MAX_REFINE_SWEEPS,
    "num_wake_nodes": 32,
    "wake_iters": 3,
    "tess_u": 20,
    "tess_w": 20,
    "omp_threads": 1,
    "flags": ["-omp", "1"],
    "status": "PROVISIONAL_P0_P1_PENDING",
}


@dataclass(frozen=True)
class DRealTaskSpec:
    task_id: str
    version: str
    description: str
    mach: float
    altitude_m: float
    rho_kg_m3: float
    speed_of_sound_m_s: float
    velocity_m_s: float
    q_Pa: float
    q_source: str
    lift_reference_N: float
    lift_tol_rel: float
    sref_baseline_m2: float
    alpha_primary_deg: Tuple[float, ...]
    alpha_refine_deg: Tuple[float, ...]
    max_refine_sweeps: int
    max_launches_per_design: int
    reference_frame: str
    xcg_m: float
    cref_m: float
    bref_m: float
    solver_config: Mapping[str, Any] = field(default_factory=dict)
    solver_config_sha256: str = ""
    source_kind: str = "MOCK"
    notes: str = ""

    def cl_required(self, sref_m2: float) -> float:
        return float(self.lift_reference_N) / (float(self.q_Pa) * float(sref_m2))

    def task_context(self) -> Tuple[float, float]:
        """2-D context consumed by warm_start surrogate features."""
        return (float(self.mach), float(self.altitude_m) / 1000.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "dreal001.task_spec.v1",
            "task_id": self.task_id,
            "version": self.version,
            "description": self.description,
            "mach": self.mach,
            "altitude_m": self.altitude_m,
            "rho_kg_m3": self.rho_kg_m3,
            "speed_of_sound_m_s": self.speed_of_sound_m_s,
            "velocity_m_s": self.velocity_m_s,
            "q_Pa": self.q_Pa,
            "q_source": self.q_source,
            "lift_reference_N": self.lift_reference_N,
            "lift_tol_rel": self.lift_tol_rel,
            "sref_baseline_m2": self.sref_baseline_m2,
            "alpha_primary_deg": list(self.alpha_primary_deg),
            "alpha_refine_deg": list(self.alpha_refine_deg),
            "max_refine_sweeps": int(self.max_refine_sweeps),
            "max_launches_per_design": int(self.max_launches_per_design),
            "reference_frame": self.reference_frame,
            "xcg_m": self.xcg_m,
            "cref_m": self.cref_m,
            "bref_m": self.bref_m,
            "solver_config": dict(self.solver_config),
            "solver_config_sha256": self.solver_config_sha256,
            "source_kind": self.source_kind,
            "notes": self.notes,
            "objective": {
                "name": "D_i_N",
                "definition": "q*Sref(x)*CDi at matched lift",
                "constraint": "abs(q*Sref(x)*CLtot - L_ref)/L_ref <= lift_tol_rel",
                "fuel_burn_kg": None,
            },
        }

    def fingerprint(self) -> str:
        return sha256_bytes(canonical_json(self.to_dict()).encode("utf-8"))

    def with_solver_config(self, config: Mapping[str, Any]) -> "DRealTaskSpec":
        frozen = dict(config)
        return replace_task(self, solver_config=frozen, solver_config_sha256=solver_config_hash(frozen))

    def with_source_kind(self, source_kind: str) -> "DRealTaskSpec":
        return replace_task(self, source_kind=str(source_kind))


def replace_task(task: DRealTaskSpec, **changes: Any) -> DRealTaskSpec:
    payload = dict(task.__dict__)
    payload.update(changes)
    return DRealTaskSpec(**payload)


def build_task(
    *,
    task_id: str = "concorde_fixed_cruise_12d",
    version: str = "p2-dreal001-v1",
    description: str = (
        "Concorde fixed supersonic cruise (Mach 2.02, 18288 m); objective is the "
        "lifting-surface induced drag D_i = q*Sref(x)*CDi at matched lift L_ref, "
        "not fuel burn."
    ),
    mach: float = 2.02,
    altitude_m: float = 18288.0,
    q_Pa: Optional[float] = None,
    lift_reference_N: float = L_REF_N,
    lift_tol_rel: float = LIFT_TOL_REL,
    sref_baseline_m2: float = SREF_BASELINE_M2,
    alpha_primary_deg: Sequence[float] = ALPHA_PRIMARY_DEG,
    alpha_refine_deg: Sequence[float] = ALPHA_REFINE_DEG,
    max_refine_sweeps: int = MAX_REFINE_SWEEPS,
    max_launches_per_design: int = MAX_LAUNCHES_PER_DESIGN,
    solver_config: Optional[Mapping[str, Any]] = None,
    source_kind: str = "MOCK",
    notes: str = "",
) -> DRealTaskSpec:
    atmosphere = isa_atmosphere(altitude_m)
    velocity = float(mach) * atmosphere["sound_m_s"]
    if q_Pa is None:
        dynamic_pressure = Q_PA_DEFAULT
        q_source = "A1_EVALUATOR_API_v0.1_D5 (Lead/Owner confirmation pending)"
    else:
        dynamic_pressure = float(q_Pa)
        q_source = "explicit"
    config = dict(DEFAULT_SOLVER_CONFIG if solver_config is None else solver_config)
    config.setdefault("mach", float(mach))
    config.setdefault("alpha_primary_deg", list(alpha_primary_deg))
    config.setdefault("alpha_refine_deg", list(alpha_refine_deg))
    return DRealTaskSpec(
        task_id=str(task_id),
        version=str(version),
        description=str(description),
        mach=float(mach),
        altitude_m=float(altitude_m),
        rho_kg_m3=float(atmosphere["rho_kg_m3"]),
        speed_of_sound_m_s=float(atmosphere["sound_m_s"]),
        velocity_m_s=float(velocity),
        q_Pa=float(dynamic_pressure),
        q_source=str(q_source),
        lift_reference_N=float(lift_reference_N),
        lift_tol_rel=float(lift_tol_rel),
        sref_baseline_m2=float(sref_baseline_m2),
        alpha_primary_deg=tuple(float(value) for value in alpha_primary_deg),
        alpha_refine_deg=tuple(float(value) for value in alpha_refine_deg),
        max_refine_sweeps=int(max_refine_sweeps),
        max_launches_per_design=int(max_launches_per_design),
        reference_frame=REFERENCE_FRAME,
        xcg_m=XCG_M,
        cref_m=CREF_M,
        bref_m=BREF_M,
        solver_config=config,
        solver_config_sha256=solver_config_hash(config),
        source_kind=str(source_kind),
        notes=str(notes),
    )
