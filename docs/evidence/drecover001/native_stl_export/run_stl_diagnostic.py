"""Production worker STL export, geometric placement and topology diagnostics only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
import traceback
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.aircraft.openvsp_check import build_openvsp_request


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measure(path):
    raw = path.read_bytes()
    n = int.from_bytes(raw[80:84], "little") if len(raw) >= 84 else -1
    if n > 0 and len(raw) == 84 + n * 50:
        dtype = np.dtype([("normal", "<f4", (3,)), ("points", "<f4", (3, 3)), ("attr", "<u2")])
        records = np.frombuffer(raw, dtype=dtype, offset=84, count=n)
        tri = records["points"].astype(np.float64)
        format_name = "binary"
    else:
        vertices = []
        for line in raw.decode("ascii", errors="strict").splitlines():
            fields = line.strip().split()
            if fields and fields[0].lower() == "vertex":
                if len(fields) != 4:
                    raise ValueError("malformed STL vertex")
                vertices.append([float(v) for v in fields[1:]])
        if not vertices or len(vertices) % 3:
            raise ValueError("missing/incomplete STL triangles")
        tri = np.asarray(vertices, dtype=np.float64).reshape(-1, 3, 3)
        format_name = "ascii"
    if not np.isfinite(tri).all():
        raise ValueError("nonfinite STL vertices")
    xyz = tri.reshape(-1, 3)
    doubled_area = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    # Quantization is diagnostic welding only, never a mesh repair or new export.
    _, inverse = np.unique(np.rint(xyz / 1e-8).astype(np.int64), axis=0, return_inverse=True)
    faces = inverse.reshape(-1, 3)
    collapsed = np.any(np.sort(faces, axis=1)[:, 1:] == np.sort(faces, axis=1)[:, :-1], axis=1)
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    sorted_edges = np.sort(edges, axis=1)
    _, multiplicity = np.unique(sorted_edges, axis=0, return_counts=True)
    _, face_counts = np.unique(np.sort(faces, axis=1), axis=0, return_counts=True)
    return {"sha256": sha(path), "bytes": len(raw), "format": format_name,
            "triangles": len(tri), "bounds_m": [xyz.min(axis=0).tolist(), xyz.max(axis=0).tolist()],
            "extents_m": np.ptp(xyz, axis=0).tolist(), "surface_area_m2": float(doubled_area.sum() / 2),
            "weld_tolerance_m": 1e-8, "zero_area_threshold_m2": 1e-12,
            "near_zero_area_triangles": int(np.sum(doubled_area <= 2e-12)),
            "collapsed_faces_after_quantization": int(collapsed.sum()),
            "duplicate_triangle_excess": int(np.sum(face_counts - 1)),
            "boundary_edges_after_quantization": int(np.sum(multiplicity == 1)),
            "nonmanifold_edges_after_quantization": int(np.sum(multiplicity > 2)),
            "min_triangle_area_m2": float(doubled_area.min() / 2)}


def main():
    out = Path(__file__).resolve().parent
    receipt = {"scope": "REAL_PRODUCTION_WORKER_STL_DIAGNOSTIC_ONLY", "status": "NOT_READY",
               "physical_solver_starts_actual": 0, "internal_solver_cases_actual": 0,
               "freeze_issued": False, "real_admission": False, "solver_mesh_validated": False,
               "generated_utc": datetime.now(timezone.utc).isoformat()}
    try:
        cfg = ROOT / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
        rows = yaml.safe_load(cfg.read_bytes())
        variables = rows["variables"] + rows["fixed_variables"]
        model = build_geometry([v["name"] for v in variables], [float(v["baseline"]) for v in variables])
        request = build_openvsp_request(model, out, basename="baseline_corrected", formats=("stl", "vsp3"))
        request["openvsp_root"] = "D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64"
        request_path, result_path = out / "worker_request.json", out / "worker_result.json"
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
        worker = ROOT / "research/concorde_metaopt/aircraft/openvsp_geometry.py"
        cmd = [sys.executable, "-s", "-B", str(worker), "--request", str(request_path), "--result", str(result_path)]
        receipt["command"] = cmd
        with (out / "worker_stdout.txt").open("w", encoding="utf-8") as stdout, (out / "worker_stderr.txt").open("w", encoding="utf-8") as stderr:
            process = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=120)
        receipt["worker_returncode"] = process.returncode
        result = json.loads(result_path.read_text())
        if process.returncode != 0 or result.get("status") != "ok":
            raise RuntimeError("production geometry worker failed: " + str(result.get("error")))
        exports = result["exports"]
        measured = {n: measure(Path(e["path"])) for n, e in exports["components"].items()}
        measured["assembly"] = measure(Path(exports["assembly"]["stl"]["path"]))
        receipt["meshes"] = measured
        low = np.min([r["bounds_m"][0] for n, r in measured.items() if n != "assembly"], axis=0)
        high = np.max([r["bounds_m"][1] for n, r in measured.items() if n != "assembly"], axis=0)
        tail, wing = measured["vertical_tail"], measured["main_wing"]
        lo, hi = np.asarray(tail["bounds_m"])
        ex, ey, ez = tail["extents_m"]
        checks = {"all_triangles_present_finite": all(m["triangles"] > 0 for m in measured.values()),
                  "tail_aft_x42": abs(lo[0] - 42.) < 1e-4,
                  "tail_z1_to_model_height": abs(lo[2] - 1.) < 1e-4 and abs(hi[2] - (1 + model.vertical_tail.span_m)) < 1e-4,
                  "tail_vertical_extent_exceeds_thickness": ez > 5 * ey,
                  "wing_span_matches_model": abs(wing["extents_m"][1] - model.wing.span_m) < 1e-4,
                  "assembly_bounds_equal_component_union": bool(np.allclose(np.array(measured["assembly"]["bounds_m"]), np.array([low, high]), rtol=0, atol=1e-4))}
        checks = {key: bool(value) for key, value in checks.items()}
        receipt["placement_checks"] = checks
        receipt["topology_checks"] = {n: {"no_near_zero_faces": m["near_zero_area_triangles"] == 0,
                  "no_duplicate_faces": m["duplicate_triangle_excess"] == 0,
                  "closed_two_manifold_edges": m["boundary_edges_after_quantization"] == 0 and m["nonmanifold_edges_after_quantization"] == 0}
                  for n, m in measured.items()}
        receipt["status"] = "STL_PLACEMENT_PASS_NOT_SOLVER_MESH" if all(checks.values()) else "STL_PLACEMENT_FAIL"
        receipt["vsp3_sha256"] = sha(Path(exports["assembly"]["vsp3"]["path"]))
        receipt["limitations"] = "One baseline tessellation; quantized edge checks are diagnostic, not repaired topology or CFD/VSPAERO mesh approval. Overlapping assembly surfaces are not boolean-unioned. No aerodynamic or Sref/AC/mass approval."
    except Exception as exc:
        receipt.update(status="ERROR", error=type(exc).__name__ + ": " + str(exc), traceback=traceback.format_exc())
    receipt["source_sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__), ROOT / "research/concorde_metaopt/aircraft/openvsp_geometry.py", ROOT / "research/concorde_metaopt/aircraft/openvsp_check.py")}
    (out / "stl_diagnostic_receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] == "STL_PLACEMENT_PASS_NOT_SOLVER_MESH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
