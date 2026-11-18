"""Native finite geometric response only; never a freeze or aerodynamic active mask."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import time
import traceback
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from research.concorde_metaopt.aircraft import openvsp_geometry as worker
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.openvsp_check import build_openvsp_request


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = Path(__file__).resolve().parent
    start = time.monotonic()
    result = {"scope": "REAL_NATIVE_12D_GEOMETRIC_RESPONSE_ONLY", "status": "NOT_READY",
              "physical_solver_starts_actual": 0, "internal_solver_cases_actual": 0,
              "aerodynamic_active_mask": "NOT_VALIDATED", "freeze_issued": False,
              "real_admission": False, "native_builds_actual": 0,
              "generated_utc": datetime.now(timezone.utc).isoformat(),
              "limits": {"build_cap": 14, "wall_seconds": 180, "samples_per_surface": 289,
                         "response_threshold_m": 1e-8, "unchanged_tolerance_m": 1e-10}}
    samples = {}
    try:
        install = Path("D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64")
        vsp = worker.import_openvsp(install)
        result["runtime_binary_sha256"] = sha(install / "python/openvsp/openvsp/_vsp.pyd")
        config_path = ROOT / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
        config = yaml.safe_load(config_path.read_bytes())
        variables = config["variables"] + config["fixed_variables"]
        names = [r["name"] for r in variables]
        baseline = [float(r["baseline"]) for r in variables]
        if len(config["variables"]) != 12 or len(variables) != 15:
            raise ValueError("12 proposed and 3 fixed variables required")
        result["config_sha256"] = sha(config_path)

        def build(label, vector):
            if time.monotonic() - start > 180 or result["native_builds_actual"] >= 14:
                raise RuntimeError("native diagnostic cap reached")
            model = build_geometry(names, vector)
            specs = build_openvsp_request(model, out, formats=("vsp3",))["components"]
            vsp.ClearVSPModel()
            result["native_builds_actual"] += 1
            handles = {s["name"]: worker._add_component(vsp, s)[1] for s in specs}
            vsp.Update()
            rows, arrays = {}, {}
            for name, geom in handles.items():
                points = []
                for surface in range(vsp.GetTotalNumSurfs(geom)):
                    for u in np.linspace(0., 1., 17):
                        for w in np.linspace(0., 1., 17):
                            pt = vsp.CompPnt01(geom, surface, float(u), float(w))
                            points.append((pt.x(), pt.y(), pt.z()))
                array = np.asarray(points, dtype=np.float64)
                if array.ndim != 2 or array.shape[1] != 3 or not np.isfinite(array).all():
                    raise RuntimeError("invalid native surface coordinates")
                arrays[name] = array
                samples[label + "__" + name] = array
                row = {"samples": len(array), "coordinate_sha256": hashlib.sha256(array.astype("<f8").tobytes()).hexdigest(),
                       "extent_xyz_m": np.ptp(array, axis=0).tolist()}
                if name != "fuselage":
                    pure = model.wing if name == "main_wing" else model.vertical_tail
                    area = float(vsp.GetParmVal(geom, "TotalArea", "WingGeom"))
                    span = float(vsp.GetParmVal(geom, "TotalSpan", "WingGeom"))
                    expected_area = float(pure.area_m2)
                    row.update(native_area_m2=area, model_area_m2=expected_area,
                               relative_area_error=abs(area - expected_area) / expected_area,
                               native_span_m=span)
                rows[name] = row
            return arrays, rows

        base, base_rows = build("baseline", baseline)
        repeat, repeat_rows = build("baseline_repeat", baseline)
        result["baseline"] = base_rows
        result["baseline_repeat_max_abs_delta_m"] = {n: float(np.max(np.abs(base[n] - repeat[n]))) for n in base}
        result["baseline_deterministic"] = all(v <= 1e-10 for v in result["baseline_repeat_max_abs_delta_m"].values())
        probes = []
        for index, variable in enumerate(config["variables"]):
            low, high, value = (float(variable[k]) for k in ("lower", "upper", "baseline"))
            if not all(np.isfinite([low, high, value])) or not low <= value <= high or not low < high:
                raise ValueError("invalid numeric bounds")
            step = .1 * (high - low)
            trial = value + step if value + step <= high else value - step
            vector = list(baseline)
            vector[index] = trial
            arrays, rows = build("probe_%02d" % index, vector)
            deltas = {n: float(np.max(np.abs(arrays[n] - base[n]))) if arrays[n].shape == base[n].shape else None for n in base}
            expected = "main_wing" if index < 10 else "vertical_tail"
            changed = [n for n, delta in deltas.items() if delta is None or delta > 1e-8]
            isolated = changed == [expected] and all(deltas[n] is not None and deltas[n] <= 1e-10 for n in base if n != expected)
            probes.append({"id": variable["id"], "name": variable["name"], "baseline": value,
                           "probe": trial, "expected_component": expected, "changed_components": changed,
                           "native_coordinate_max_abs_delta_m": deltas, "expected_component_only": isolated,
                           "native_metrics": rows})
        result["probes"] = probes
        result["expected_component_only_count"] = sum(r["expected_component_only"] for r in probes)
        result["native_model_area_agreement_max_relative_error"] = max(
            r["relative_area_error"] for rows in [base_rows] + [p["native_metrics"] for p in probes]
            for r in rows.values() if "relative_area_error" in r)
        result["status"] = "NATIVE_RESPONSE_PASS_NOT_FREEZE" if result["baseline_deterministic"] and result["expected_component_only_count"] == 12 else "NATIVE_RESPONSE_FAIL"
        result["limitations"] = "Finite one-sided 10%-range perturbations at one baseline; sparse surface positions, not STL/solver mesh or aerodynamic sensitivity. Native TotalArea is diagnostic only, not approved solver Sref. No mass/AC/atmosphere/run provenance approval."
    except Exception as exc:
        result.update(status="ERROR", error=type(exc).__name__ + ": " + str(exc), traceback=traceback.format_exc())
    if samples:
        path = out / "native_coordinate_samples.npz"
        np.savez_compressed(path, **samples)
        result["sample_archive"] = {"name": path.name, "sha256": sha(path), "bytes": path.stat().st_size}
    result["elapsed_seconds"] = time.monotonic() - start
    result["source_sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in (
        Path(__file__), Path(worker.__file__), ROOT / "research/concorde_metaopt/aircraft/openvsp_check.py",
        ROOT / "research/concorde_metaopt/aircraft/geometry_model.py")}
    (out / "native_response_receipt.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in result if k not in ("probes", "baseline", "traceback")}, indent=2))
    return 0 if result["status"] == "NATIVE_RESPONSE_PASS_NOT_FREEZE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
