"""Frozen aerodynamic task contract for D-REAL-001 (single point).

This module is the single source of truth for the real-aerodynamics task that the
12D lifting-surface design space will be evaluated against.  It contains NO
solver result and makes NO physical claim: every number here is an input
contract, not evidence.

Contract decisions frozen on 2026-11-10 (Lead ruling, D-REAL-001):
  * lift requirement uses the single-cruise entry mass 136000 kg only;
    184880 kg is the geometric model mass and is disclosed but never used as
    the lift target.
  * solver geometry = main wing + vertical tail (two lifting surfaces);
    the fuselage is excluded and F01-F03 stay fixed and out of the 12D set.
  * reference point X_cg = 16.821978259514246 m (wing aerodynamic centre),
    reference_frame = WING_AC; moments are recorded but MUST NOT be used for
    trim or static-stability conclusions until the mass-CG contract is frozen.
  * Sref is design dependent: Sref(x) = designed exposed main-wing planform
    area; Cref and Bref are held at the baseline values.
  * ONE solver process start carries the fixed alpha grid written into .vspaero
    (AlphaStart/AlphaEnd/AlphaNpts, integer-typed); the default grid is
    (-2, 0, 2, 4, 6, 8, 10) deg and the solver is run WITHOUT -fs.  Lift matching by alpha
    interpolation; at most 2 refine starts per design.

All constants were derived from
  research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z
and the frozen cruise conditions quoted in the D-REAL-001 plan document.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Tuple

G0_M_S2 = 9.80665
ALTITUDE_M = 18288.0
MACH = 2.02
VINF_M_S = 596.0373972278921
RHO_KG_M3 = 0.1153178340089936
T_STATIC_K = 216.65
P_STATIC_PA = 7171.544888256813
A_SOUND_M_S = 295.0680184

MASS_CRUISE_ENTRY_KG = 136000.0
MASS_GEOMETRY_MODEL_KG = 184880.0
MASS_CONTRACT_STATUS = "PROVISIONAL_NOT_FROZEN"

CREF_M = 18.489893
BREF_M = 25.604638
RECREF = 89397005.8767656

XCG_M = 16.821978259514246   # wing aerodynamic centre (reference only)
WING_AC_X_M = 16.821978259514246
GEOMETRY_CG_X_M = 28.287395109126685
REFERENCE_FRAME = "WING_AC"
CM_TRIMMING_DISABLED = True

SREF_BASELINE_M2 = 358.25
L_REF_N = MASS_CRUISE_ENTRY_KG * G0_M_S2            # 1,333,704.4 N
Q_PA = 0.5 * RHO_KG_M3 * VINF_M_S * VINF_M_S        # 20,483.940233430174 Pa
LIFT_TOLERANCE_REL_INITIAL = 1.0e-3                 # refined after P1 repeatability
ALPHA_WINDOW_DEG = (-2.0, 10.0)
ALPHA_FIXED_LIST_DEG = (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)   # P1 main grid (uniform step 2)

SOLVER_GEOMETRY_COMPONENTS = ("main_wing", "vertical_tail")
SOLVER_INCLUDES_FUSELAGE = False
FIXED_GEOMETRY_VARIABLES = ("fuselage_length", "fuselage_fineness", "fuselage_height_width_ratio")
SREF_POLICY = "design dependent: exposed main-wing planform area Sref(x) = geometry.wing.area_m2"
DEFAULT_GEOMETRY_SET = "thin"                       # VLM; thick surface set is the P1 cross-check
W01_BASELINE_M2 = SREF_BASELINE_M2
W01_RANGE_M2 = (300.0, 420.0)
W01_VARIABLE_NAME = "wing_area"

REF_FLAG = 0
REFERENCE_INJECTION_POLICY = (
    "RefFlag=0: Sref/Cref/Bref/X_cg are injected manually from this contract and are "
    "verified line-by-line in the generated .vspaero before any solver start; the solver "
    "MUST NOT recompute reference quantities from component areas. Manual injection keeps "
    "the reference geometry fixed while the lifting-surface geometry is perturbed."
)
SREF_RECOMPUTE_RULE = (
    "Sref(x) = geometry.wing.area_m2 = exposed main-wing planform area, recomputed by "
    "aircraft/geometry_model.build_geometry for every 12D design vector x. W01 (wing_area) "
    "is the design variable that sets it. Sref is recomputed by the GEOMETRY BUILDER, never "
    "by VSPAERO (RefFlag=0). Cref=18.489893 m and Bref=25.604638 m stay frozen at the "
    "baseline reference lengths; ReCref stays frozen too. Every reported dimensional value "
    "is recomputed per design: L = q*Sref(x)*CLtot, D_i = q*Sref(x)*CDi, CL_req(x) = "
    "L_ref/(q*Sref(x)); only the coefficient-to-force conversion uses the design Sref."
)
W01_SENSITIVITY_NOTE = (
    "W01 wing_area changes Sref(x) and therefore the dimensional force scale: D_i = "
    "q*Sref*CDi has an explicit linear Sref factor on top of the induced-drag coefficient "
    "change. A W01 probe MUST report Sref, CL_req and CDi separately and MUST NOT read a "
    "D_i change as a pure efficiency change. Under matched lift, CL_req shrinks as Sref "
    "grows, so the same D_i can hide opposite CDi movements."
)

TASK_SPEC_SCHEMA = "dreal001.task_spec.v1"


@dataclass(frozen=True)
class TaskSpec:
    task_id: str = "concorde-fixed-cruise-dreal001-real-v1"
    schema: str = TASK_SPEC_SCHEMA
    status: str = "FROZEN_FOR_P0_P1"
    altitude_m: float = ALTITUDE_M
    mach: float = MACH
    vinf_m_s: float = VINF_M_S
    rho_kg_m3: float = RHO_KG_M3
    t_static_k: float = T_STATIC_K
    p_static_pa: float = P_STATIC_PA
    a_sound_m_s: float = A_SOUND_M_S
    g0_m_s2: float = G0_M_S2
    q_pa: float = Q_PA
    mass_cruise_entry_kg: float = MASS_CRUISE_ENTRY_KG
    mass_geometry_model_kg: float = MASS_GEOMETRY_MODEL_KG
    mass_contract_status: str = MASS_CONTRACT_STATUS
    l_ref_n: float = L_REF_N
    cref_m: float = CREF_M
    bref_m: float = BREF_M
    recref: float = RECREF
    sref_baseline_m2: float = SREF_BASELINE_M2
    sref_policy: str = SREF_POLICY
    ref_flag: int = REF_FLAG
    reference_injection_policy: str = REFERENCE_INJECTION_POLICY
    sref_recompute_rule: str = SREF_RECOMPUTE_RULE
    w01_sensitivity_note: str = W01_SENSITIVITY_NOTE
    xcg_m: float = XCG_M
    wing_ac_x_m: float = WING_AC_X_M
    geometry_cg_x_m: float = GEOMETRY_CG_X_M
    reference_frame: str = REFERENCE_FRAME
    cm_trimming_disabled: bool = CM_TRIMMING_DISABLED
    lift_tolerance_rel: float = LIFT_TOLERANCE_REL_INITIAL
    alpha_window_deg: Tuple[float, float] = ALPHA_WINDOW_DEG
    alpha_fixed_list_deg: Tuple[float, ...] = ALPHA_FIXED_LIST_DEG
    solver_geometry_components: Tuple[str, ...] = SOLVER_GEOMETRY_COMPONENTS
    solver_includes_fuselage: bool = SOLVER_INCLUDES_FUSELAGE
    fixed_geometry_variables: Tuple[str, ...] = FIXED_GEOMETRY_VARIABLES
    default_geometry_set: str = DEFAULT_GEOMETRY_SET
    objective: str = "minimize D_i = q * Sref(x) * CDi at matched lift L = L_ref"
    constraints: Tuple[str, ...] = (
        "L/q/Sref(x)/CLtot within lift_tolerance_rel of L_ref",
        "alpha in alpha_window_deg",
        "geometry bounds and cross constraints of design_space_12d_lifting_surfaces.yaml",
    )

    @property
    def cl_required_baseline(self) -> float:
        """CL needed at the baseline Sref to carry L_ref (diagnostic only)."""
        return self.l_ref_n / (self.q_pa * self.sref_baseline_m2)

    def cl_required(self, sref_m2: float) -> float:
        if sref_m2 <= 0.0:
            raise ValueError("Sref must be positive")
        return self.l_ref_n / (self.q_pa * sref_m2)

    def lift_matched(self, sref_m2: float, cltot: float, rel_tol: float | None = None) -> bool:
        target = self.l_ref_n
        lift = self.q_pa * sref_m2 * cltot
        tol = self.lift_tolerance_rel if rel_tol is None else float(rel_tol)
        return abs(lift - target) <= tol * abs(target)

    def reference_injection(self, sref_m2: float) -> Dict[str, Any]:
        """Explicit RefFlag=0 injection contract for one design Sref."""
        return {
            "ref_flag": int(self.ref_flag),
            "policy": self.reference_injection_policy,
            "solver_recomputes_references": False,
            "injected": {
                "Sref": float(sref_m2), "Cref": self.cref_m, "Bref": self.bref_m,
                "X_cg": self.xcg_m, "Y_cg": 0.0, "Z_cg": 0.0,
                "Mach": self.mach, "Vinf": self.vinf_m_s, "Rho": self.rho_kg_m3,
                "ReCref": self.recref,
            },
            "reference_frame": self.reference_frame,
            "verification": "every injected field is parsed back from the generated .vspaero "
                            "and compared against this contract before any solver start",
        }

    def force_breakdown(self, sref_m2: float, cltot: float,
                        cdi: float, cdtot: float | None = None) -> Dict[str, float]:
        """Dimensional forces at one design Sref; the ONLY allowed coefficients->force path."""
        if sref_m2 <= 0.0:
            raise ValueError("Sref must be positive")
        cl_total = self.q_pa * float(sref_m2) * float(cltot)
        d_i = self.q_pa * float(sref_m2) * float(cdi)
        payload = {
            "q_pa": self.q_pa, "sref_m2": float(sref_m2),
            "cltot": float(cltot), "cdi": float(cdi),
            "L_N": cl_total, "D_i_N": d_i,
            "CL_req": self.cl_required(float(sref_m2)),
            "lift_rel_error_vs_Lref": (cl_total - self.l_ref_n) / self.l_ref_n,
        }
        if cdtot is not None:
            payload["D_total_N"] = self.q_pa * float(sref_m2) * float(cdtot)
        return payload

    def w01_effect(self, sref_m2: float, cdi: float) -> Dict[str, float]:
        """W01 sensitivity decomposition: Sref factor reported separately from CDi."""
        return {
            "sref_m2": float(sref_m2), "sref_ratio_vs_baseline": float(sref_m2) / self.sref_baseline_m2,
            "cl_req": self.cl_required(float(sref_m2)),
            "cdi": float(cdi), "D_i_N": self.q_pa * float(sref_m2) * float(cdi),
            "note": self.w01_sensitivity_note,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["alpha_window_deg"] = list(self.alpha_window_deg)
        data["alpha_fixed_list_deg"] = list(self.alpha_fixed_list_deg)
        data["solver_geometry_components"] = list(self.solver_geometry_components)
        data["fixed_geometry_variables"] = list(self.fixed_geometry_variables)
        data["constraints"] = list(self.constraints)
        data["cl_required_baseline"] = self.cl_required_baseline
        data["reference_injection_contract"] = self.reference_injection(self.sref_baseline_m2)
        data["sref_recompute_contract"] = {
            "equation": self.sref_recompute_rule,
            "w01_variable": W01_VARIABLE_NAME,
            "w01_baseline_m2": W01_BASELINE_M2,
            "w01_range_m2": list(W01_RANGE_M2),
            "sref_design_dependent": True,
            "solver_recomputes_sref": False,
            "dimensional_force_rule": "L_N=q*Sref(x)*CLtot; D_i_N=q*Sref(x)*CDi; "
                                      "D_total_N=q*Sref(x)*CDtot",
        }
        data["w01_sensitivity_contract"] = self.w01_effect(self.sref_baseline_m2, 0.0)
        data["units"] = {
            "q_pa": "Pa", "l_ref_n": "N", "cref_m": "m", "bref_m": "m",
            "sref_m2": "m2", "xcg_m": "m", "vinf_m_s": "m/s", "rho_kg_m3": "kg/m3",
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskSpec":
        payload = dict(data)
        for key in ("alpha_window_deg", "alpha_fixed_list_deg", "solver_geometry_components",
                    "fixed_geometry_variables", "constraints", "units", "cl_required_baseline",
                    "reference_injection_contract", "sref_recompute_contract",
                    "w01_sensitivity_contract"):
            payload.pop(key, None)
        for key in list(payload):
            if key not in cls.__dataclass_fields__:
                payload.pop(key)
        for key in ("alpha_window_deg", "alpha_fixed_list_deg"):
            if key in data:
                payload[key] = tuple(float(v) for v in data[key])
        if "solver_geometry_components" in data:
            payload["solver_geometry_components"] = tuple(data["solver_geometry_components"])
        if "fixed_geometry_variables" in data:
            payload["fixed_geometry_variables"] = tuple(data["fixed_geometry_variables"])
        return cls(**payload)


TASK_SPEC = TaskSpec()

EVIDENCE_SPLIT = {
    "solver_loop_verified": "may be claimed after P0 replay + ENV_SMOKE + P1 numerics",
    "internal_aero_optimization_gain": "may be claimed only for VSPAERO-internal D_i reduction, wing model only",
    "external_physics_supported": "NOT claimable; no real fuel-burn or full-aircraft drag evidence",
    "fuel_burn_kg": None,
}


def validate_contract(tolerance: float = 1.0e-9) -> Dict[str, float]:
    """Assert the internally consistent numbers used across the whole programme."""
    q_check = 0.5 * RHO_KG_M3 * VINF_M_S ** 2
    if abs(q_check - Q_PA) > 1e-6 * abs(Q_PA):
        raise AssertionError("q mismatch: %r" % q_check)
    if abs(L_REF_N - MASS_CRUISE_ENTRY_KG * G0_M_S2) > 1e-9:
        raise AssertionError("L_ref mismatch")
    cl = TASK_SPEC.cl_required_baseline
    if abs(cl * Q_PA * SREF_BASELINE_M2 - L_REF_N) > 1e-6 * L_REF_N:
        raise AssertionError("CL_req consistency failed")
    if TASK_SPEC.ref_flag != 0:
        raise AssertionError("RefFlag must be 0 (manual injection)")
    breakdown = TASK_SPEC.force_breakdown(SREF_BASELINE_M2, cl, 0.0)
    if abs(breakdown["L_N"] - L_REF_N) > tolerance * L_REF_N:
        raise AssertionError("force_breakdown L_N mismatch")
    peaks = TASK_SPEC.alpha_fixed_list_deg
    steps = {round(peaks[i + 1] - peaks[i], 9) for i in range(len(peaks) - 1)}
    if len(steps) != 1:
        raise AssertionError("alpha_fixed_list_deg must be uniformly spaced for VSPAEROSweep")
    if TASK_SPEC.alpha_fixed_list_deg[0] < TASK_SPEC.alpha_window_deg[0] or \
            TASK_SPEC.alpha_fixed_list_deg[-1] > TASK_SPEC.alpha_window_deg[1]:
        raise AssertionError("alpha_fixed_list_deg outside alpha window")
    return {"q_pa": Q_PA, "l_ref_n": L_REF_N, "cl_required_baseline": cl,
            "ref_flag": TASK_SPEC.ref_flag, "force_breakdown_l_n": breakdown["L_N"]}


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_dump(obj: Any, level: int = 0) -> str:
    pad = "  " * level
    if isinstance(obj, dict):
        lines = []
        for key, value in obj.items():
            if isinstance(value, (dict, list)) and value:
                lines.append("%s%s:" % (pad, key))
                lines.append(_yaml_dump(value, level + 1))
            else:
                lines.append("%s%s: %s" % (pad, key, _yaml_dump(value, level + 1)))
        return "\n".join(lines) + ("\n" if level == 0 else "")
    if isinstance(obj, list):
        return pad + "[" + ", ".join(_yaml_scalar(item) if not isinstance(item, (dict, list))
                                     else json.dumps(item) for item in obj) + "]"
    return pad + _yaml_scalar(obj)


def write_task_spec_yaml(path: str | Path) -> Path:
    """Write the frozen task contract as YAML (configs/dreal001_task_fixed_cruise_REAL.yaml)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = TASK_SPEC.to_dict()
    payload["evidence_split"] = EVIDENCE_SPLIT
    header = ("# D-REAL-001 real-aerodynamics task contract (frozen 2026-11-10).\n"
              "# Generated by research/concorde_metaopt/dreal001/geometry/task_spec.py;\n"
              "# no solver result and no physical claim is stored here.\n")
    path.write_text(header + _yaml_dump(payload), encoding="utf-8")
    return path


def write_task_spec(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = TASK_SPEC.to_dict()
    payload["evidence_split"] = EVIDENCE_SPLIT
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(json.dumps({"task_spec": TASK_SPEC.to_dict(), "validate": validate_contract()}, indent=2))
