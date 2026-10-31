"""Lead LF geometry worker: wing-only OpenVSP model -> VSPAERO DegenGeom CSV + vsp3/stl.

Order matters in this OpenVSP build: the VSPAEROComputeGeometry ExecAnalysis must
run BEFORE WriteVSPFile/ExportFile, otherwise the second ExecAnalysis hangs.
Geometry-only; no aerodynamic solve.
"""
import importlib.util
import json
import sys
import traceback
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    request_path = Path(sys.argv[1]).resolve()
    result_path = Path(sys.argv[2]).resolve()
    result = {"status": "failed", "python": sys.version.split()[0]}
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        ovg = load_module("openvsp_geometry", "D:/RCAIDE/research/concorde_metaopt/aircraft/openvsp_geometry.py")
        vsp = ovg.import_openvsp(request["openvsp_root"])
        vsp.ClearVSPModel()
        vsp.Update()
        geom_ids = {}
        for component in request["components"]:
            kind, geom = ovg._add_component(vsp, component)
            geom_ids[component["name"]] = geom
        vsp.Update()
        tessellation = request.get("tessellation") or {}
        if tessellation:
            name = tessellation.get("component", "main_wing")
            geom = geom_ids[name]
            for parm_name, value in tessellation.get("parameters", {}).items():
                vsp.SetParmVal(geom, parm_name, "Shape", float(value))
            vsp.Update()
        export = request["export"]
        directory = Path(export["directory"])
        directory.mkdir(parents=True, exist_ok=True)
        basename = export.get("basename", "model")
        # 1) DegenGeom first (second ExecAnalysis after exports hangs in this build).
        vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
        res = vsp.ExecAnalysis("VSPAEROComputeGeometry")
        produced = Path("Unnamed_DegenGeom.csv")
        degen_target = directory / (basename + "_DegenGeom.csv")
        if produced.is_file():
            if degen_target.exists():
                degen_target.unlink()
            produced.replace(degen_target)
        # 2) model file and surface export.
        vsp3 = directory / (basename + ".vsp3")
        vsp.WriteVSPFile(str(vsp3), vsp.SET_ALL)
        stl = directory / (basename + ".stl")
        vsp.ExportFile(str(stl), vsp.SET_ALL, vsp.EXPORT_STL)
        files = {}
        for path in sorted(directory.iterdir()):
            if path.is_file():
                files[path.name] = path.stat().st_size
        result = {
            "status": "ok" if degen_target.is_file() else "failed_no_degen_geom",
            "python": sys.version.split()[0],
            "analysis_result": res,
            "files": files,
        }
    except Exception:
        result["traceback"] = traceback.format_exc()
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "traceback"}, indent=1))


if __name__ == "__main__":
    main()
