"""Read-only model diagnostic, NEVER a design-space freeze or active-mask approval.

Reads numeric proposals directly; deliberately does not bypass or monkeypatch the
production loader. No DesignSpace is returned and no OpenVSP or solver is imported.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import yaml
from research.concorde_metaopt.aircraft.design_space import (
    DESIGN_SETS, FIXED_FUSELAGE_IDS, FIXED_FUSELAGE_NAMES,
    DesignSpaceError, load_design_space,
)
from research.concorde_metaopt.aircraft.geometry_model import build_geometry

CONFIG = ROOT / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def components(geometry):
    # No design variables or mass/CG in these signatures: that would tautologically
    # mark a variable effective merely because its input or mass estimate changed.
    return {"main_wing": geometry.wing.to_dict(),
            "vertical_tail": geometry.vertical_tail.to_dict(),
            "fuselage": geometry.fuselage.to_dict()}


def diagnose(config):
    proposed = copy.deepcopy(config)
    if proposed.get("design_set") != "12d_lifting_surfaces":
        raise ValueError("diagnostic requires 12D lifting-surface proposal")
    variables, fixed = proposed["variables"], proposed["fixed_variables"]
    ids, names = DESIGN_SETS["12d_lifting_surfaces"]
    if tuple((r["id"], r["name"]) for r in variables) != tuple(zip(ids, names)):
        raise ValueError("12D identity/order mismatch")
    if tuple((r["id"], r["name"]) for r in fixed) != tuple(zip(FIXED_FUSELAGE_IDS, FIXED_FUSELAGE_NAMES)):
        raise ValueError("fixed fuselage identity/order mismatch")
    all_names = [r["name"] for r in variables + fixed]
    baseline = [float(r["baseline"]) for r in variables + fixed]
    base_parts = components(build_geometry(all_names, baseline))
    probes = []
    for index, variable in enumerate(variables):
        low, high, value = (float(variable[key]) for key in ("lower", "upper", "baseline"))
        if not all(math.isfinite(v) for v in (low, high, value)) or not low <= value <= high or not low < high:
            raise ValueError("invalid proposed bounds")
        step = 0.10 * (high - low)
        trial = value + step if value + step <= high else value - step
        changed = list(baseline)
        changed[index] = trial
        parts = components(build_geometry(all_names, changed))
        changed_components = [name for name in parts if canonical_sha(parts[name]) != canonical_sha(base_parts[name])]
        expected = "main_wing" if index < 10 else "vertical_tail"
        probes.append({"id": variable["id"], "name": variable["name"],
                       "baseline": value, "probe": trial, "delta": trial - value,
                       "changed_components": changed_components, "expected_component": expected,
                       "expected_component_only": changed_components == [expected],
                       "component_sha256": {name: canonical_sha(p) for name, p in parts.items()}})
    return {"evidence_scope": "UNADMITTED_NUMERIC_GEOMETRY_DIAGNOSTIC_ONLY",
            "source_config_declares_frozen": proposed.get("frozen"),
            "freeze_issued": False, "aerodynamic_active_mask": "NOT_VALIDATED",
            "real_admission": False, "physical_solver_starts_actual": 0,
            "openvsp_builds": 0, "probes": probes,
            "expected_component_only_count": sum(p["expected_component_only"] for p in probes),
            "baseline_component_sha256": {name: canonical_sha(p) for name, p in base_parts.items()}}


def main():
    raw = CONFIG.read_bytes()
    result = diagnose(yaml.safe_load(raw))
    try:
        load_design_space(CONFIG)
    except DesignSpaceError as error:
        result["production_loader_status"] = "REJECTED"
        result["production_loader_error"] = str(error)
    else:
        result["production_loader_status"] = "ACCEPTED_BY_EXISTING_LOADER_NOT_THIS_DIAGNOSTIC"
    result["generated_utc"] = datetime.now(timezone.utc).isoformat()
    result["source_config_sha256"] = hashlib.sha256(raw).hexdigest()
    source = ROOT / "research/concorde_metaopt/aircraft/geometry_model.py"
    result["geometry_model_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    result["diagnostic_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output = Path(__file__).with_name("geometry_effect_diagnostic.json")
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("evidence_scope", "freeze_issued",
          "aerodynamic_active_mask", "expected_component_only_count", "production_loader_status")}))
    return 0 if result["expected_component_only_count"] == 12 else 1


if __name__ == "__main__":
    raise SystemExit(main())
