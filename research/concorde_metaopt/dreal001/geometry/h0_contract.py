"""H0 geometry contract for the D-REAL-EXP-003 optimization work.

Issue #15 requires the real 12D geometry input order, units, bounds, active mask,
geometry hashes and the frozen fuselage to be frozen *before* any new physical
evaluation, and it records that the historical freeze is not reusable as-is.

This module never edits the YAML design-space file and never flips its
`frozen: true` semantics. It builds the executable contract from two already
frozen sources plus a fresh, zero-physical reproduction check:

* docs/evidence/drecover001/geometry_freeze_v2.json  (design + reference contract)
* research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml
  (read as raw YAML so the provisional-design-space guard is not bypassed)

The known conflict is recorded, not hidden: `design_space.load_design_space()`
refuses this YAML because it declares `frozen: true` while carrying
`stage: P1`, so production paths that call it cannot load the 12D space. The
contract therefore carries its own copy of the executable numbers and the
optimizer path builds geometry with `build_geometry()` directly.

physical_solver_starts_actual stays 0: nothing here starts VSPAERO.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[4]

FREEZE_V2 = ROOT / "docs/evidence/drecover001/geometry_freeze_v2.json"
DESIGN_YAML = ROOT / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"

SCHEMA = "dreal005.h0_geometry_contract.v1"
CONTRACT_ID = "H0GEOM-20261124"

# Order is contractual: it is the order of the 12D design vector everywhere.
VARIABLE_ORDER: Tuple[str, ...] = (
    "wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3",
    "span_location_2", "span_location_3", "chord_ratio_2", "chord_ratio_3",
    "tip_twist", "vertical_tail_area", "vertical_tail_sweep_delta",
)
VARIABLE_IDS: Tuple[str, ...] = (
    "W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08", "W09", "W10",
    "V01", "V02",
)
FIXED_ORDER: Tuple[str, ...] = (
    "fuselage_length", "fuselage_fineness", "fuselage_height_width_ratio",
)
PHYSICAL_ORDER: Tuple[str, ...] = VARIABLE_ORDER + FIXED_ORDER

# Measured on existing raw rows by docs/evidence/dreal004/p0/12d_variable_response_audit.json
# (zero-physical audit of 56 raw pairs). max|dCDi| per variable.
MEASURED_RESPONSE_MAX_ABS_DCDI: Dict[str, float] = {
    "wing_area": 1.45e-10,
    "aspect_ratio": 0.0,
    "sweep_1": 1.707e-3,
    "sweep_2": 6.977e-4,
    "sweep_3": 0.0,
    "span_location_2": 0.0,
    "span_location_3": 0.0,
    "chord_ratio_2": 0.0,
    "chord_ratio_3": 0.0,
    "tip_twist": 0.0,
    "vertical_tail_area": 0.0,
    "vertical_tail_sweep_delta": None,
}
# Variables whose measured response is above the raw polar resolution floor.
RESPONSIVE_VARIABLES: Tuple[str, ...] = ("sweep_1", "sweep_2")
# The local optimization subspace actually offered to the O0 optimizer.
OPTIMIZATION_SUBSPACE: Tuple[str, ...] = ("sweep_1", "sweep_2")


class ContractError(RuntimeError):
    """Raised when the frozen contract cannot be reproduced from disk."""


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canonical_sha(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha_bytes(text.encode("utf-8"))


def geometry_hash(vector: Sequence[float]) -> str:
    """Design identity used by admission certificates (canonical 12D sha256)."""
    return canonical_sha([float(value) for value in vector])


def design_id(vector: Sequence[float]) -> str:
    """Short design hash used for directory naming and de-duplication."""
    from research.concorde_metaopt.dreal001.geometry.design_identity import design_hash

    return design_hash([float(value) for value in vector])


def _close(measured: float, declared: Any, rel_tol: float = 1e-6) -> bool:
    """Compare a computed quantity against its rounded published value."""
    declared_value = float(declared)
    return abs(float(measured) - declared_value) <= rel_tol * max(1.0, abs(declared_value))


def load_raw_yaml() -> Dict[str, Any]:
    """Read the YAML as data; the provisional-design-space guard is not used."""
    payload = yaml.safe_load(DESIGN_YAML.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ContractError("design space YAML did not parse to a mapping")
    return payload


def load_freeze_v2() -> Dict[str, Any]:
    if not FREEZE_V2.is_file():
        raise ContractError("missing geometry_freeze_v2.json: %s" % FREEZE_V2)
    return json.loads(FREEZE_V2.read_text(encoding="utf-8"))


def probe_production_loader() -> Dict[str, Any]:
    """Record what the production loader does with the frozen YAML, without fixing it."""
    from research.concorde_metaopt.aircraft import design_space

    try:
        design_space.load_design_space(DESIGN_YAML)
    except Exception as exc:  # noqa: BLE001 - the failure is the evidence
        return {
            "loader": "research.concorde_metaopt.aircraft.design_space.load_design_space",
            "loaded": False,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "disposition": "DO_NOT_BYPASS_SILENTLY; optimizer builds geometry via build_geometry()",
        }
    return {
        "loader": "research.concorde_metaopt.aircraft.design_space.load_design_space",
        "loaded": True,
        "exception_type": None,
        "exception_message": None,
        "disposition": "loaded",
    }


def build_contract() -> Dict[str, Any]:
    """Assemble the executable H0 contract from the frozen sources."""
    from research.concorde_metaopt.aircraft.geometry_model import (
        GEOMETRY_MODEL_VERSION,
        build_geometry,
    )

    freeze = load_freeze_v2()
    design = freeze["design_contract"]
    reference = freeze["reference_contract"]

    frozen_names = tuple(item["name"] for item in design["design_variables"])
    if frozen_names != VARIABLE_ORDER:
        raise ContractError(
            "frozen design variable order %r does not match the contractual order %r"
            % (frozen_names, VARIABLE_ORDER))
    frozen_ids = tuple(item["id"] for item in design["design_variables"])
    if frozen_ids != VARIABLE_IDS:
        raise ContractError("frozen design variable ids do not match the contract")

    fixed = {item["name"]: float(item["baseline"]) for item in design["fixed_variables"]}
    if tuple(fixed) != FIXED_ORDER:
        raise ContractError("frozen fixed-variable order changed: %r" % (tuple(fixed),))

    baseline_x12 = [float(value) for value in design["baseline_x12"]]
    if len(baseline_x12) != 12:
        raise ContractError("baseline_x12 must have 12 entries")
    for name, value in zip(VARIABLE_ORDER, baseline_x12):
        declared = next(item for item in design["design_variables"] if item["name"] == name)
        if abs(float(declared["baseline"]) - value) > 0.0:
            raise ContractError("baseline mismatch for %s: %r != %r"
                                % (name, declared["baseline"], value))

    names = list(PHYSICAL_ORDER)
    baseline_physical = [baseline_x12[i] for i in range(12)] + [fixed[name] for name in FIXED_ORDER]
    geometry = build_geometry(names, baseline_physical)

    yaml_payload = load_raw_yaml()
    yaml_variables = yaml_payload.get("variables") or []
    yaml_names = tuple(item["name"] for item in yaml_variables)
    if yaml_names != VARIABLE_ORDER:
        raise ContractError("YAML variable order %r does not match the contract" % (yaml_names,))
    yaml_bounds = {
        item["name"]: (float(item["lower"]), float(item["upper"])) for item in yaml_variables
    }
    for item in design["design_variables"]:
        name = item["name"]
        declared = yaml_bounds[name]
        frozen = (float(item["lower"]), float(item["upper"]))
        if declared != frozen:
            raise ContractError("bounds mismatch for %s: YAML %r vs freeze %r"
                                % (name, declared, frozen))

    source_hashes = {}
    for rel_path, expected in freeze["source"]["source_sha256"].items():
        path = ROOT / rel_path
        if not path.is_file():
            raise ContractError("frozen source file is missing: %s" % rel_path)
        digest = sha_file(path)
        if digest != expected:
            raise ContractError(
                "frozen source %s changed: %s != %s" % (rel_path, digest, expected))
        source_hashes[rel_path] = digest

    baseline_span = float(geometry.wing.span_m)
    baseline_mac = float(geometry.wing.mean_aerodynamic_chord_m)
    baseline_area = float(geometry.wing.area_m2)
    reproduction: Dict[str, Any] = {
        "wing_area_m2": baseline_area,
        "wing_span_m": baseline_span,
        "wing_mac_m": baseline_mac,
        "vertical_tail_area_m2": float(geometry.vertical_tail.area_m2),
        "vertical_tail_span_m": float(geometry.vertical_tail.span_m),
        "geometry_model_version": GEOMETRY_MODEL_VERSION,
        "matches_frozen_reference": {
            "sref_m2": _close(baseline_area, reference["sref_m2"]),
            "bref_m": _close(baseline_span, reference["bref_m"]),
            "cref_m": _close(baseline_mac, reference["cref_m"]),
        },
        "reference_rounding_note": (
            "reference_contract carries the rounded published values; the comparison uses a "
            "1e-6 relative tolerance because the frozen JSON stores 6 decimal places"),
    }
    if not all(reproduction["matches_frozen_reference"].values()):
        raise ContractError("baseline geometry does not reproduce the frozen reference: %r"
                            % (reproduction["matches_frozen_reference"],))

    bounds = {
        item["name"]: {"id": item["id"], "unit": item["unit"],
                       "baseline": float(item["baseline"]),
                       "lower": float(item["lower"]), "upper": float(item["upper"])}
        for item in design["design_variables"]
    }
    subspace = {}
    for name in OPTIMIZATION_SUBSPACE:
        entry = dict(bounds[name])
        entry["measured_max_abs_delta_cdi"] = MEASURED_RESPONSE_MAX_ABS_DCDI[name]
        entry["active"] = True
        entry["reason"] = (
            "measured on existing raw rows above the polar resolution floor; "
            "variable is a genuine aerodynamic freedom"
            if MEASURED_RESPONSE_MAX_ABS_DCDI[name]
            else "measured response is at the raw polar resolution floor")
        subspace[name] = entry

    inactive = {}
    for name in VARIABLE_ORDER:
        if name in OPTIMIZATION_SUBSPACE:
            continue
        inactive[name] = {
            "frozen_value": bounds[name]["baseline"],
            "held_fixed": True,
            "measured_max_abs_delta_cdi": MEASURED_RESPONSE_MAX_ABS_DCDI[name],
            "reason": ("measured response at or below the raw polar resolution floor"
                       if MEASURED_RESPONSE_MAX_ABS_DCDI[name] is not None
                       else "response not measured yet (P1 probe pending)"),
        }

    contract = {
        "schema": SCHEMA,
        "contract_id": CONTRACT_ID,
        "issue": 15,
        "plan_document": "docs/planning/dreal005_task_conditioned_maml_real_optimization_20261124.md",
        "scope": "H0 geometry contract for zero-physical freeze and the O0 real short BO",
        "variable_order_12d": list(VARIABLE_ORDER),
        "variable_ids_12d": list(VARIABLE_IDS),
        "baseline_x12": baseline_x12,
        "fixed_variables": {name: fixed[name] for name in FIXED_ORDER},
        "physical_parameter_order_15": list(PHYSICAL_ORDER),
        "baseline_physical_15": baseline_physical,
        "bounds": bounds,
        "cross_constraints": [
            {"id": entry.get("id"), "expression": entry.get("expression")}
            for entry in (yaml_payload.get("cross_constraints") or [])
        ],
        "optimization_subspace": subspace,
        "held_fixed_variables": inactive,
        "reference_contract": {
            key: reference[key] for key in (
                "sref_m2", "cref_m", "bref_m", "reference_frame", "xcg_m",
                "lift_reference_N", "q_pa", "lift_tol_rel")
            if key in reference
        },
        "baseline_geometry_hash": geometry_hash(baseline_x12),
        "baseline_design_id": design_id(baseline_x12),
        "contract_sha256": None,
        "geometry_contract_sha256_freeze_v2": freeze["geometry_contract_sha256"],
        "freeze_v2_id": freeze["freeze_id"],
        "source_file_sha256": source_hashes,
        "baseline_geometry_reproduction": reproduction,
        "production_loader_probe": probe_production_loader(),
        "freeze_conflict": {
            "summary": (
                "design_space_12d_lifting_surfaces.yaml declares stage: P1 with frozen: true; "
                "design_space._validate_space raises for any frozen space, so "
                "load_design_space() cannot load the 12D YAML from the production path"),
            "yaml_stage": yaml_payload.get("stage"),
            "yaml_frozen": yaml_payload.get("frozen"),
            "yaml_bounds_status": yaml_payload.get("bounds_status"),
            "resolution": (
                "keep YAML semantics unchanged; the executable contract above is the frozen copy "
                "and the optimizer builds geometry with build_geometry() directly"),
            "silently_flipped_yaml": False,
            "touches_main": False,
        },
        "aerodynamic_active_mask_status": (
            "VALIDATED_FOR_SWEEP_SUBSPACE_ON_EXISTING_RAW_ROWS; the full 12D mask remains "
            "NOT_VALIDATED because 9 of 12 variables show no measurable CDi response"),
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
        "physics_validated": False,
        "limitations": [
            "response magnitudes are measured on historical raw polar rows (d00-d07 single-variable perturbations) and are not a solver-side sensitivity study",
            "VSPAERO runs in LIFTING_SURFACE_ONLY mode: the fuselage is not part of the evaluated aerodynamic model",
            "the local subspace optimizes induced drag at fixed lift for one fixed Mach/altitude task; it is not a full-aircraft or full-mission optimization",
        ],
    }
    contract["contract_sha256"] = canonical_sha(
        {key: value for key, value in contract.items() if key != "contract_sha256"})
    return contract


def verify_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute the contract from disk and compare it with the supplied payload."""
    fresh = build_contract()
    checks: List[Dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    record("schema", fresh["schema"] == contract.get("schema"), fresh["schema"])
    record("contract_sha256", fresh["contract_sha256"] == contract.get("contract_sha256"),
           fresh["contract_sha256"])
    record("variable_order_12d",
           fresh["variable_order_12d"] == contract.get("variable_order_12d"),
           "12D order identity")
    record("baseline_x12", fresh["baseline_x12"] == contract.get("baseline_x12"),
           "baseline vector identity")
    record("bounds", fresh["bounds"] == contract.get("bounds"), "bounds identity")
    record("subspace", fresh["optimization_subspace"] == contract.get("optimization_subspace"),
           "optimization subspace identity")
    record("baseline_design_id",
           fresh["baseline_design_id"] == contract.get("baseline_design_id"),
           fresh["baseline_design_id"])
    record("freeze_conflict_recorded",
           bool(contract.get("freeze_conflict", {}).get("summary")),
           "freeze conflict is disclosed, not hidden")
    record("zero_physical_at_freeze",
           contract.get("physical_solver_starts_actual") == 0
           and fresh["physical_solver_starts_actual"] == 0,
           "physical_solver_starts_actual == 0")
    return {
        "schema": "dreal005.h0_geometry_contract_verification.v1",
        "check_count": len(checks),
        "failure_count": sum(1 for item in checks if not item["ok"]),
        "checks": checks,
        "contract_sha256": fresh["contract_sha256"],
        "status": ("H0_GEOMETRY_CONTRACT_REPRODUCIBLE"
                   if all(item["ok"] for item in checks) else "H0_GEOMETRY_CONTRACT_DRIFT"),
    }