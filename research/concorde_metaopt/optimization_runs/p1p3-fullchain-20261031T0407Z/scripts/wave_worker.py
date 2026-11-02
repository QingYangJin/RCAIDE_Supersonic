
"""Generic OpenVSP area-rule worker (Lead). Builds requested model, runs one
analysis (WaveDrag or EmintonLord), records results and any files written.

ExecAnalysis is called before any WriteVSPFile/ExportFile because that order is
required in this OpenVSP build (see LF worker notes).
"""
import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def safe(obj):
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return repr(obj)

def main():
    request_path = Path(sys.argv[1]).resolve()
    result_path = Path(sys.argv[2]).resolve()
    result = {"status": "failed", "python": sys.version.split()[0], "cwd": os.getcwd()}
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        ovg = load_module("openvsp_geometry", "D:/RCAIDE/research/concorde_metaopt/aircraft/openvsp_geometry.py")
        vsp = ovg.import_openvsp(request["openvsp_root"])
        vsp.ClearVSPModel()
        vsp.Update()
        geom_ids = {}
        for component in request.get("components") or []:
            kind, geom = ovg._add_component(vsp, component)
            geom_ids[component["name"]] = geom
        vsp.Update()
        result["geometry_ids"] = safe(geom_ids)
        analysis = request["analysis"]
        aname = analysis["name"]
        before = set(os.listdir("."))
        vsp.SetAnalysisInputDefaults(aname)
        applied = {}
        for parm, value in (analysis.get("inputs") or {}).items():
            atype = vsp.GetAnalysisInputType(aname, parm)
            if isinstance(value, list):
                if all(isinstance(v, int) and not isinstance(v, bool) for v in value) and atype == 0 and len(value) == 1:
                    vsp.SetIntAnalysisInput(aname, parm, value, 0)
                else:
                    vsp.SetDoubleAnalysisInput(aname, parm, [float(v) for v in value], 0)
            elif isinstance(value, int) and not isinstance(value, bool):
                vsp.SetIntAnalysisInput(aname, parm, [value], 0)
            elif isinstance(value, float):
                vsp.SetDoubleAnalysisInput(aname, parm, [value], 0)
            elif isinstance(value, str):
                vsp.SetStringAnalysisInput(aname, parm, [value], 0)
            else:
                raise ValueError("unsupported input type for %s: %r" % (parm, value))
            applied[parm] = value
        result["inputs_applied"] = applied
        result["input_names"] = list(vsp.GetAnalysisInputNames(aname))
        raw = vsp.ExecAnalysis(aname)
        result["exec_result_type"] = type(raw).__name__
        result["exec_result_raw"] = safe(raw)
        rid = None
        try:
            if isinstance(raw, str):
                rid = raw
            else:
                rid = vsp.FindLatestResultsID(aname)
        except Exception as exc:
            result["find_results_error"] = repr(exc)
        result["results_id"] = safe(rid)
        collected = {}
        if rid:
            try:
                import io
                from contextlib import redirect_stdout
                buf = io.StringIO()
                try:
                    with redirect_stdout(buf):
                        vsp.PrintResults(rid)
                except Exception as exc:
                    buf.write("PrintResults error: %r" % (exc,))
                collected["print_results"] = buf.getvalue()
            except Exception as exc:
                collected["print_results_error"] = repr(exc)
            for suffix in ("", "_area", "_cdwave"):
                pass
            try:
                csv_path = Path("results_%s.csv" % rid).resolve()
                vsp.WriteResultsCSVFile(rid, str(csv_path))
                if csv_path.exists():
                    collected["results_csv"] = {
                        "path": str(csv_path),
                        "bytes": csv_path.stat().st_size,
                        "text": csv_path.read_text(encoding="utf-8", errors="replace")[:200000],
                    }
            except Exception as exc:
                collected["write_results_csv_error"] = repr(exc)
            # enumerate every result name and try typed getters
            entries = []
            try:
                nres = vsp.GetNumResults()
                collected["num_results"] = nres
                for i in range(min(int(nres), 200)):
                    name = None
                    for fn in ("GetResultsName", "GetResultsType"):
                        pass
                    try:
                        name = vsp.GetResultsName(i)
                    except Exception:
                        break
                    entry = {"index": i, "name": safe(name)}
                    for kind, getter in (("double", vsp.GetDoubleResults), ("int", vsp.GetIntResults),
                                         ("string", vsp.GetStringResults), ("vec3d", vsp.GetVec3dResults)):
                        try:
                            entry[kind] = safe(getter(rid, name))
                        except Exception:
                            pass
                    entries.append(entry)
            except Exception as exc:
                collected["enumerate_results_error"] = repr(exc)
            collected["results_entries"] = entries
        result["results"] = collected
        after = set(os.listdir("."))
        new_files = sorted(after - before)
        result["new_files"] = new_files
        file_info = {}
        for name in new_files:
            p = Path(name)
            try:
                size = p.stat().st_size
            except Exception:
                continue
            entry = {"bytes": size}
            if size <= 2_000_000 and p.is_file():
                try:
                    entry["text"] = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            file_info[name] = entry
        result["new_file_info"] = file_info
        result["status"] = "ok"
    except Exception:
        result["status"] = "failed"
        result["traceback"] = traceback.format_exc()
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "exec_result": result.get("exec_result"), "new_files": result.get("new_files")}))

if __name__ == "__main__":
    main()