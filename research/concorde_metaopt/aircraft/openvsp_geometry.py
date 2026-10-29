"""Geometry worker executed by the external OpenVSP Python 3.9 interpreter.

The RCAIDE environment (Python 3.11) cannot import the OpenVSP _vsp extension,
so geometry construction is isolated in this standalone script. The script is
deliberately dependency-free apart from OpenVSP itself and communicates through
JSON request/result files.

Request schema (JSON)::

    {
      "openvsp_root": "<OpenVSP installation directory>",
      "export": {"directory": "<absolute path>", "basename": "concorde_full",
                 "formats": ["stl", "step", "vsp3"]},
      "components": [
        {"kind": "wing", "name": "main_wing", "symmetric": true,
         "span_m": 25.6046, "location": [14.0, 0.0, -0.8],
         "rotation": [0.0, 0.0, 0.0],
         "sections": [{"percent_span_location": 0.0, "chord_m": 29.9018,
                        "leading_edge_x_m": 0.0}, ...]},
        {"kind": "fuselage", "name": "fuselage", "length_m": 61.66,
         "location": [0.0, 0.0, 0.0],
         "stations": [{"x_m": 0.0, "width_m": 0.001, "height_m": 0.001}, ...]}
      ]
    }

The wing section mapping reproduces the OpenVSP convention verified during the
P1 probe: section 0 span is ignored, an interior section's Root_Chord is the
chord at the previous station, and the final section's Tip_Chord is the tip
chord. Surface twist is intentionally not modelled here (the wing model has a
single tip twist that OpenVSP would apply only as a rotation).

Usage::

    <SUAVE python 3.9> openvsp_geometry.py --request request.json --result result.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
from pathlib import Path

OPENVSP_PYTHON_SUBDIRS = ("python", os.path.join("python", "openvsp"),
                          os.path.join("python", "degen_geom"),
                          os.path.join("python", "utilities"))


def import_openvsp(openvsp_root):
    root = Path(openvsp_root)
    for subdir in OPENVSP_PYTHON_SUBDIRS:
        candidate = str(root / subdir)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    import openvsp as vsp  # noqa: F401  (import is the availability test)
    return vsp


def _set(vsp, parm_id, value):
    vsp.SetParmVal(parm_id, float(value))
    vsp.Update()


def _require_xsec_count(vsp, surf, expected, name):
    actual = vsp.GetNumXSec(surf)
    if actual != expected:
        raise RuntimeError("component %s: expected %d XSecs, OpenVSP has %d"
                           % (name, expected, actual))


def _add_wing(vsp, spec):
    name = spec["name"]
    sections = spec["sections"]
    if len(sections) < 2:
        raise RuntimeError("wing %s needs at least two sections" % name)
    geom = vsp.AddGeom("WING")
    vsp.SetGeomName(geom, name)
    for index in range(1, len(sections) - 1):
        vsp.InsertXSec(geom, index, vsp.XS_FOUR_SERIES)
    vsp.Update()
    surf = vsp.GetXSecSurf(geom, 0)
    _require_xsec_count(vsp, surf, len(sections), name)

    semispan = float(spec["span_m"])
    if spec.get("symmetric", True):
        semispan = semispan / 2.0
    chords = [float(section["chord_m"]) for section in sections]
    fractions = [float(section["percent_span_location"]) for section in sections]
    # OpenVSP quirk: an interior section's Root_Chord applies to the station at
    # the inboard end of the previous segment. The verified mapping is
    # roots = [c0, c0, c1, ..., c_(n-1)] and final Tip_Chord = c_n.
    roots = [chords[0]] + chords[:-1]
    for index, section in enumerate(sections):
        xsec = vsp.GetXSec(surf, index)
        if index == 0:
            span = 0.0
            sweep = 0.0
        else:
            span = (fractions[index] - fractions[index - 1]) * semispan
            if span <= 0.0:
                raise RuntimeError("wing %s: non-increasing percent span" % name)
            delta_x = float(section["leading_edge_x_m"]) - float(sections[index - 1]["leading_edge_x_m"])
            sweep = math.degrees(math.atan2(delta_x, span))
        _set(vsp, vsp.GetXSecParm(xsec, "Span"), span)
        _set(vsp, vsp.GetXSecParm(xsec, "Root_Chord"), roots[index])
        _set(vsp, vsp.GetXSecParm(xsec, "Sweep"), sweep)
    _set(vsp, vsp.GetXSecParm(vsp.GetXSec(surf, len(sections) - 1), "Tip_Chord"), chords[-1])

    location = spec.get("location", [0.0, 0.0, 0.0])
    rotation = spec.get("rotation", [0.0, 0.0, 0.0])
    for axis, value in zip(("X", "Y", "Z"), location):
        vsp.SetParmVal(geom, axis + "_Location", "XForm", float(value))
    for axis, value in zip(("X", "Y", "Z"), rotation):
        vsp.SetParmVal(geom, axis + "_Rotation", "XForm", float(value))
    if not spec.get("symmetric", True):
        vsp.SetParmVal(geom, "Sym_Planar_Flag", "Sym", 0.0)
    vsp.Update()
    return geom


def _fuselage_station_positions(stations, length):
    positions = [float(station["x_m"]) / length for station in stations]
    if positions[0] != 0.0 or positions[-1] != 1.0:
        raise RuntimeError("fuselage stations must start at x=0 and end at x=length")
    for previous, current in zip(positions, positions[1:]):
        if current <= previous:
            raise RuntimeError("fuselage station x values must be strictly increasing")
    return positions


def _add_fuselage(vsp, spec):
    name = spec["name"]
    length = float(spec["length_m"])
    stations = spec["stations"]
    positions = _fuselage_station_positions(stations, length)
    geom = vsp.AddGeom("FUSELAGE")
    vsp.SetGeomName(geom, name)
    default_sections = 5
    insert_count = len(stations) - default_sections
    if insert_count < 0:
        raise RuntimeError("fuselage %s needs at least %d stations" % (name, default_sections))
    for index in range(1, insert_count + 1):
        vsp.InsertXSec(geom, index, vsp.XS_ELLIPSE)
    vsp.Update()
    surf = vsp.GetXSecSurf(geom, 0)
    _require_xsec_count(vsp, surf, len(stations), name)
    _set(vsp, vsp.GetParm(geom, "Length", "Design"), length)

    for index, station in enumerate(stations):
        xsec = vsp.GetXSec(surf, index)
        _set(vsp, vsp.GetXSecParm(xsec, "XLocPercent"), positions[index])
        if index not in (0, len(stations) - 1):
            _set(vsp, vsp.GetXSecParm(xsec, "Ellipse_Width"), station["width_m"])
            _set(vsp, vsp.GetXSecParm(xsec, "Ellipse_Height"), station["height_m"])
    # Verify that OpenVSP accepted every position. Silent rejections are a known
    # failure mode when a target violates section ordering.
    for index in range(len(stations)):
        xsec = vsp.GetXSec(surf, index)
        actual = vsp.GetParmVal(vsp.GetXSecParm(xsec, "XLocPercent"))
        if abs(actual - positions[index]) > 1.0e-9:
            raise RuntimeError("fuselage %s: section %d position rejected (%r != %r)"
                               % (name, index, actual, positions[index]))
    return geom


def _wing_metrics(vsp, geom, name):
    return {
        "name": name,
        "total_area_m2": vsp.GetParmVal(geom, "TotalArea", "WingGeom"),
        "total_span_m": vsp.GetParmVal(geom, "TotalSpan", "WingGeom"),
        "bbox_m": [vsp.GetParmVal(geom, key, "BBox") for key in ("X_Len", "Y_Len", "Z_Len")],
    }


def _fuselage_metrics(vsp, geom, name):
    # Read the length back from OpenVSP instead of echoing the request value, so
    # the comparison can actually fail if the Design.Length parameter is ignored.
    length = vsp.GetParmVal(vsp.GetParm(geom, "Length", "Design"))
    return {
        "name": name,
        "length_m": length,
        "bbox_m": [vsp.GetParmVal(geom, key, "BBox") for key in ("X_Len", "Y_Len", "Z_Len")],
        "bbox_note": "OpenVSP FUSELAGE BBox is not a reliable surface bound; STL bounds are measured by the caller.",
    }


def _check_written(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("OpenVSP did not write %s" % path)


def _add_component(vsp, component):
    kind = component["kind"].lower()
    if kind == "wing":
        return "wing", _add_wing(vsp, component)
    if kind == "fuselage":
        return "fuselage", _add_fuselage(vsp, component)
    raise RuntimeError("unsupported component kind: %s" % kind)


def _export_assembly(vsp, export_spec):
    directory = Path(export_spec["directory"])
    directory.mkdir(parents=True, exist_ok=True)
    basename = export_spec.get("basename", "concorde_full")
    formats = export_spec.get("formats", ["stl", "step", "vsp3"])
    exports = {}
    for fmt in formats:
        fmt = fmt.lower()
        if fmt == "vsp3":
            path = directory / (basename + ".vsp3")
            vsp.WriteVSPFile(str(path), vsp.SET_ALL)
        elif fmt == "stl":
            path = directory / (basename + ".stl")
            vsp.ExportFile(str(path), vsp.SET_ALL, vsp.EXPORT_STL)
        elif fmt == "step":
            path = directory / (basename + ".step")
            vsp.ExportFile(str(path), vsp.SET_ALL, vsp.EXPORT_STEP)
        else:
            raise RuntimeError("unsupported export format: %s" % fmt)
        _check_written(path)
        exports[fmt] = {"path": str(path), "bytes": path.stat().st_size}
    return exports


def _export_component_stls(vsp, export_spec, components):
    # ExportFile accepts a geometry set, not a single geometry id. Rebuilding one
    # component in a cleared model and exporting SET_ALL is the reliable
    # single-component path in this OpenVSP build; user sets are ignored by the
    # STL writer (verified: a user set exported only the wing).
    directory = Path(export_spec["directory"])
    basename = export_spec.get("basename", "concorde_full")
    exports = {}
    for component in components:
        vsp.ClearVSPModel()
        kind, _geom = _add_component(vsp, component)
        vsp.Update()
        path = directory / (basename + "_" + component["name"] + ".stl")
        vsp.ExportFile(str(path), vsp.SET_ALL, vsp.EXPORT_STL)
        _check_written(path)
        exports[component["name"]] = {
            "kind": kind,
            "path": str(path),
            "bytes": path.stat().st_size,
        }
    return exports


def build_model(request):
    vsp = import_openvsp(request["openvsp_root"])
    vsp.ClearVSPModel()
    components = request["components"]
    geoms = {}
    for component in components:
        kind, geom = _add_component(vsp, component)
        geoms[component["name"]] = (kind, geom, component)
    vsp.Update()

    metrics = {}
    for name, (kind, geom, component) in geoms.items():
        if kind == "wing":
            metrics[name] = _wing_metrics(vsp, geom, name)
        else:
            metrics[name] = _fuselage_metrics(vsp, geom, name)
    exports = {"assembly": _export_assembly(vsp, request["export"]), "components": {}}
    formats = [fmt.lower() for fmt in request["export"].get("formats", ["stl", "step", "vsp3"])]
    if "stl" in formats:
        exports["components"] = _export_component_stls(vsp, request["export"], components)
    return {
        "status": "ok",
        "python_version": sys.version.split()[0],
        "openvsp_module": "openvsp (external Python 3.9)",
        "components": {name: {"kind": kind} for name, (kind, _geom, _component) in geoms.items()},
        "metrics": metrics,
        "exports": exports,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)
    result = {"status": "failed"}
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        result = build_model(request)
    except Exception as exc:  # noqa: BLE001 - report every failure to the caller
        result = {
            "status": "failed",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc(),
        }
    Path(args.result).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
