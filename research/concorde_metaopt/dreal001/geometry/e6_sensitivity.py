"""E6 gap closure: prove the 12D design vector rebuilds geometry (zero solver starts).

P1-07 copied the same four solver input files for all 14 probes, so the probe
polar hashes were identical and variable sensitivity was NOT_MEASURED.  This
module rebuilds geometry from x12 through openvsp_model.prepare_case with
VSPAEROSweep StopBeforeRun=1: no vspaero.exe process is launched, but the
.vspgeom bytes, node/element counts and reference quantities are real.

CLI::

    <python> -m research.concorde_metaopt.dreal001.geometry.e6_sensitivity \
        --out-dir <dir> [--geometry-set thin]

Verdicts are computed from the raw evidence, not asserted:
- RESPONSIVE: .vspgeom sha256 changes and/or node/element counts change;
- NOT_RESPONSIVE: all four geometry outputs and reference quantities are
  bit-identical to the baseline, which would mean the 12D variable is inert in
  the current geometry builder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from . import openvsp_model
from .design_identity import design_hash as compute_design_hash
from .task_spec import TASK_SPEC

E6_SCHEMA = "dreal001.e6_sensitivity.v1"
DEFAULT_BASENAME = "concorde_baseline"
RANGE_FRACTION = 0.10
VARIABLES = {
    "W01": {"index": 0, "name": "wing_area", "unit": "m^2"},
    "W03": {"index": 2, "name": "sweep_1", "unit": "deg"},
    "W10": {"index": 9, "name": "tip_twist", "unit": "deg"},
    "V01": {"index": 10, "name": "vertical_tail_area", "unit": "m^2"},
    "V02": {"index": 11, "name": "vertical_tail_sweep_delta", "unit": "deg"},
}


def _space():
    from research.concorde_metaopt.aircraft.design_space import load_design_space

    config = (openvsp_model.REPO_ROOT / "research" / "concorde_metaopt" / "configs"
              / "design_space_12d_lifting_surfaces.yaml")
    return load_design_space(str(config))


def baseline_x12() -> List[float]:
    space = _space()
    baseline = space.baseline_dict()
    return [float(baseline[variable.name]) for variable in space.variables]


def perturbation_designs() -> List[Dict[str, Any]]:
    """Baseline plus +/-10% of the declared range for W01, W03, W10, V01, V02."""
    space = _space()
    base = baseline_x12()
    designs = [{"design_id": "baseline", "variable_id": None, "direction": "none",
                "x12": list(base), "design_hash": compute_design_hash(base)}]
    for variable_id, meta in VARIABLES.items():
        variable = space.variables[meta["index"]]
        delta = RANGE_FRACTION * (float(variable.upper) - float(variable.lower))
        for direction, sign in (("plus", 1.0), ("minus", -1.0)):
            x12 = list(base)
            x12[meta["index"]] = float(base[meta["index"]] + sign * delta)
            designs.append({"design_id": "%s-%s" % (variable_id, direction),
                            "variable_id": variable_id,
                            "variable_name": variable.name,
                            "direction": direction,
                            "delta": sign * delta,
                            "x12": x12,
                            "design_hash": compute_design_hash(x12)})
    return designs


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_one(design: Mapping[str, Any], out_dir: Path,
              geometry_set: str = TASK_SPEC.default_geometry_set) -> Dict[str, Any]:
    geometry, _space_obj = openvsp_model._geometry_from_design_vector(design["x12"])
    case_dir = out_dir / str(design["design_id"])
    case_dir.mkdir(parents=True, exist_ok=True)
    record = openvsp_model.prepare_case(
        geometry, case_dir, DEFAULT_BASENAME, geometry_set=geometry_set,
        alphas_deg=TASK_SPEC.alpha_fixed_list_deg,
        tess_u=12, tess_w=25,
    )
    geom_files = sorted(case_dir.glob("*.vspgeom"))
    vspgeom = geom_files[0] if geom_files else case_dir / (DEFAULT_BASENAME + ".vspgeom")
    return {
        "design_id": design["design_id"],
        "variable_id": design.get("variable_id"),
        "direction": design.get("direction"),
        "delta": design.get("delta"),
        "x12": [float(value) for value in design["x12"]],
        "design_hash": compute_design_hash(design["x12"]),
        "geometry_sha256": record.get("geometry_sha256"),
        "vspgeom_bytes": vspgeom.stat().st_size if vspgeom.is_file() else None,
        "vspgeom_sha256": _sha256(vspgeom) if vspgeom.is_file() else None,
        "vspgeom_header": record.get("vspgeom_header"),
        "sref_m2": record.get("sref_m2"),
        "cref_m": record.get("cref_m"),
        "bref_m": record.get("bref_m"),
        "xcg_m": record.get("xcg_m"),
        "setup_sweep_fields": record.get("setup_sweep_fields"),
        "readback": record.get("sweep_input_readback"),
        "readback_ok": (record.get("sweep_readback_check") or {}).get("ok"),
        "build_seconds": record.get("build_seconds"),
        "physical_solver_starts": 0,
    }


def analyze(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = records[0]
    base_sha = base["vspgeom_sha256"]
    base_nodes = (base["vspgeom_header"] or {}).get("nodes")
    base_elements = (base["vspgeom_header"] or {}).get("elements")
    base_sref = base["sref_m2"]
    table = []
    for record in records[1:]:
        header = record["vspgeom_header"] or {}
        changed = record["vspgeom_sha256"] != base_sha
        node_delta = (header.get("nodes") or 0) - (base_nodes or 0)
        element_delta = (header.get("elements") or 0) - (base_elements or 0)
        sref_delta = (record["sref_m2"] - base_sref
                      if record["sref_m2"] is not None and base_sref is not None else None)
        table.append({
            "design_id": record["design_id"],
            "variable_id": record["variable_id"],
            "direction": record["direction"],
            "delta": record["delta"],
            "design_hash": record["design_hash"],
            "geometry_sha256": record["geometry_sha256"],
            "vspgeom_sha256": record["vspgeom_sha256"],
            "geometry_sha_changed": changed,
            "nodes": header.get("nodes"),
            "elements": header.get("elements"),
            "node_delta_vs_baseline": node_delta,
            "element_delta_vs_baseline": element_delta,
            "sref_m2": record["sref_m2"],
            "sref_delta_m2": sref_delta,
            "cref_m": record["cref_m"],
            "bref_m": record["bref_m"],
            "xcg_m": record["xcg_m"],
            "geometry_responsive": bool(changed or node_delta or element_delta),
        })
    by_variable: Dict[str, Any] = {}
    for row in table:
        variable_id = str(row["variable_id"])
        by_variable.setdefault(variable_id, {"directions": {},
                                             "any_geometry_change": False,
                                             "any_node_change": False})
        by_variable[variable_id]["directions"][row["direction"]] = row
        by_variable[variable_id]["any_geometry_change"] |= bool(
            row["geometry_sha_changed"])
        by_variable[variable_id]["any_node_change"] |= bool(
            row["node_delta_vs_baseline"] or row["element_delta_vs_baseline"])
    for variable_id, entry in by_variable.items():
        if entry["any_geometry_change"] or entry["any_node_change"]:
            entry["verdict"] = "RESPONSIVE"
        else:
            entry["verdict"] = "NOT_RESPONSIVE"
    responsive = [key for key, value in by_variable.items() if value["verdict"] == "RESPONSIVE"]
    inactive = [key for key, value in by_variable.items() if value["verdict"] == "NOT_RESPONSIVE"]
    if inactive:
        label = "10D_ACTIVE_PLUS_2_INACTIVE" if len(responsive) == 10 else "PARTIAL_ACTIVITY"
    else:
        label = "12D_ACTIVE"
    return {"baseline": base, "table": table, "by_variable": by_variable,
            "responsive_variables": responsive,
            "inactive_variables": inactive,
            "activity_label": label}


def run(out_dir: Path, geometry_set: str = TASK_SPEC.default_geometry_set) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = [build_one(design, out_dir, geometry_set)
               for design in perturbation_designs()]
    analysis = analyze(records)
    payload = {"schema": E6_SCHEMA, "generated_by": "a1-aviation-f", "run_dir": str(out_dir),
               "geometry_set": geometry_set, "alphas_deg": list(TASK_SPEC.alpha_fixed_list_deg),
               "tessellation": {"u": 12, "w": 25},
               "physical_solver_starts": 0,
               "records": records, **analysis}
    (out_dir / "e6_sensitivity.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="E6 12D->geometry rebuild sensitivity (zero solver)")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--geometry-set", default=TASK_SPEC.default_geometry_set)
    args = parser.parse_args(argv)
    payload = run(Path(args.out_dir), args.geometry_set)
    summary = {"baseline": payload["baseline"]["design_id"],
               "baseline_geometry_sha256": payload["baseline"]["geometry_sha256"],
               "sref_m2": payload["baseline"]["sref_m2"],
               "activity_label": payload["activity_label"],
               "responsive": payload["responsive_variables"],
               "inactive": payload["inactive_variables"],
               "physical_solver_starts": 0,
               "rows": [{k: row[k] for k in ("design_id", "delta", "vspgeom_sha256",
                                             "nodes", "elements", "sref_m2",
                                             "sref_delta_m2", "geometry_responsive")}
                        for row in payload["table"]]}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
