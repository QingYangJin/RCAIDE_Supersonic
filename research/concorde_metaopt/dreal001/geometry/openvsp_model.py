"""OpenVSP 3.55 model build + VSPAERO 7.2.2 input generation (ZERO solver starts).

This module turns a ConcordeGeometry into the two files a VSPAERO 7.2.2 run needs
(<base>.vspgeom + <base>.vkey + <base>.vspaero) using the OpenVSP Python API only.
It never launches vspaero.exe: VSPAEROComputeGeometry does geometry processing and
VSPAEROSweep is called with StopBeforeRun=1 (source guard returns before ForkCmd,
see optimization_runs/openvsp355-remediation-20261102T014411Z/evidence).

Import order matters in this build: add_dll_directory(root) first, then insert
root/python/openvsp_config, root/python/openvsp, root/python/degen_geom,
root/python/utilities.  Inserting root/python makes "openvsp_config" resolve to a
namespace directory and breaks the import.

CLI (zero solver; writes a case directory and a case.json record)::

    <python> -m research.concorde_metaopt.dreal001.geometry.openvsp_model \
        --case-dir <dir> --basename concorde_baseline --geometry-set thin \
        --alphas -2 0 2 4 6 --tess-u 12 --tess-w 25
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .mesh_identity import (MAX_MESH_ATTEMPTS, MeshFamilyUnavailable, TARGET_MESH_FAMILY,
                            canonical_mesh_sha256, describe_mesh, mesh_family)
from .task_spec import TASK_SPEC

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OPENVSP_ROOT = os.environ.get(
    "DREAL_OPENVSP_ROOT", r"D:\OpenVSP-3.55.0\OpenVSP-3.55.0-win64")
OPENVSP_PY_SUBDIRS = (
    os.path.join("python", "openvsp_config"),
    os.path.join("python", "openvsp"),
    os.path.join("python", "degen_geom"),
    os.path.join("python", "utilities"),
)
EXPECTED_VSPAERO_VERSION = "VSPAERO v.7.2.2"
GEOMETRY_SET_CODES = {"thick": (0, -1), "thin": (-1, 0)}  # (GeomSet, ThinGeomSet)

COMPONENT_DEFS = {
    "main_wing": {
        "kind": "wing",
        "symmetric": True,
        "location": (14.0, 0.0, -0.8),
        "rotation": (0.0, 0.0, 0.0),
    },
    "vertical_tail": {
        "kind": "wing",
        "symmetric": False,
        "location": (42.0, 0.0, 1.0),
        "rotation": (90.0, 0.0, 0.0),
    },
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(paths: Sequence[str | Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(Path(path).name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def import_openvsp(openvsp_root: str | Path = DEFAULT_OPENVSP_ROOT):
    """Import the OpenVSP 3.55 Python bindings inside the RCAIDE py3.11 environment."""
    root = Path(openvsp_root)
    if not (root / "python" / "openvsp").is_dir():
        raise RuntimeError("OpenVSP root does not contain python/openvsp: %s" % root)
    os.add_dll_directory(str(root))
    for subdir in OPENVSP_PY_SUBDIRS:
        candidate = str(root / subdir)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    import openvsp as vsp  # noqa: F401
    return vsp


def _load_aircraft_geometry_module():
    """Load aircraft/openvsp_geometry.py by path (it imports openvsp only lazily)."""
    path = Path(__file__).resolve().parents[2] / "aircraft" / "openvsp_geometry.py"
    spec = importlib.util.spec_from_file_location("dreal001_openvsp_geometry_worker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def geometry_component_specs(
    geometry: Any,
    components: Sequence[str] = TASK_SPEC.solver_geometry_components,
) -> List[Dict[str, Any]]:
    """Convert a ConcordeGeometry into the worker component request schema."""
    specs: List[Dict[str, Any]] = []
    for name in components:
        if name == "vertical_tail":
            planform = geometry.vertical_tail
        elif name == "main_wing":
            planform = geometry.wing
        else:
            raise ValueError("unsupported solver geometry component: %s" % name)
        definition = COMPONENT_DEFS[name]
        specs.append({
            "kind": definition["kind"],
            "name": name,
            "symmetric": definition["symmetric"],
            "span_m": float(planform.span_m),
            "location": list(definition["location"]),
            "rotation": list(definition["rotation"]),
            "sections": [
                {
                    "percent_span_location": float(section.percent_span_location),
                    "chord_m": float(section.chord_m),
                    "leading_edge_x_m": float(section.leading_edge_x_m),
                    "twist_deg": float(section.twist_deg),
                }
                for section in planform.sections
            ],
        })
    return specs


def set_tessellation(vsp, geoms: Mapping[str, Any], tess_u: Optional[float],
                     tess_w: Optional[float]) -> Dict[str, Dict[str, float]]:
    """Set wing surface tessellation (Shape group Tess_U / Tess_W) when present."""
    applied: Dict[str, Dict[str, float]] = {}
    for name, geom in geoms.items():
        applied[name] = {}
        for parm_name, value in (("Tess_U", tess_u), ("Tess_W", tess_w)):
            if value is None:
                continue
            parm = vsp.GetParm(geom, parm_name, "Shape")
            if not parm:
                raise RuntimeError("component %s has no Shape/%s parameter" % (name, parm_name))
            vsp.SetParmVal(parm, float(value))
            applied[name][parm_name] = float(value)
    vsp.Update()
    return applied


def build_model(vsp, geometry: Any,
                components: Sequence[str] = TASK_SPEC.solver_geometry_components,
                tess_u: Optional[float] = None,
                tess_w: Optional[float] = None) -> Dict[str, Any]:
    worker = _load_aircraft_geometry_module()
    vsp.ClearVSPModel()
    geoms: Dict[str, Any] = {}
    for component in geometry_component_specs(geometry, components):
        if component["kind"] != "wing":
            raise RuntimeError("only wing components are supported by the D-REAL-001 solver geometry")
        geom = worker._add_wing(vsp, component)
        geoms[component["name"]] = geom
    vsp.Update()
    tessellation = set_tessellation(vsp, geoms, tess_u, tess_w)
    metrics = {name: worker._wing_metrics(vsp, geom, name) for name, geom in geoms.items()}
    return {"geoms": geoms, "metrics": metrics, "tessellation": tessellation}


def require_arithmetic_sequence(values_in: Sequence[float], label: str = "list") -> None:
    """VSPAEROSweep can only encode an arithmetic sweep grid (Start/End/Npts).

    VSPAERO 7.2.2 appends command-line -fs lists to the .vspaero lists instead of
    replacing them (ENV_SMOKE ran 32 internal cases instead of 5 because of that),
    so the solver command line must not carry -fs and every case list has to be
    expressible as start/end/npts inside .vspaero.
    """
    values = [float(value) for value in values_in]
    if len(values) < 1:
        raise ValueError("%s must not be empty" % label)
    if len(values) == 1:
        return
    step = (values[-1] - values[0]) / (len(values) - 1)
    for index, value in enumerate(values):
        expected = values[0] + step * index
        if abs(value - expected) > 1.0e-9 * max(1.0, abs(expected)):
            raise ValueError("%s %r is not an arithmetic sequence; VSPAEROSweep "
                             "cannot encode it as start/end/npts" % (label, values))


def require_arithmetic_alpha_list(alphas: Sequence[float]) -> None:
    """Backwards-compatible alpha-list guard (see require_arithmetic_sequence)."""
    require_arithmetic_sequence(alphas, "alpha list")


def _setup_alpha_list(raw: Optional[str]) -> List[float]:
    if raw is None:
        return []
    values = []
    for token in str(raw).replace(",", " ").split():
        try:
            values.append(float(token))
        except ValueError:
            return []
    return values


def _analysis_input_map(vsp, analysis: str) -> Dict[str, str]:
    return {name.lower(): name for name in vsp.GetAnalysisInputNames(analysis)}


def _set_int(vsp, analysis: str, names: Mapping[str, str], key: str, value: int) -> bool:
    actual = names.get(key.lower())
    if actual is None:
        return False
    vsp.SetIntAnalysisInput(analysis, actual, [int(value)], 0)
    return True


def _set_double(vsp, analysis: str, names: Mapping[str, str], key: str, value: float) -> bool:
    actual = names.get(key.lower())
    if actual is None:
        return False
    vsp.SetDoubleAnalysisInput(analysis, actual, [float(value)], 0)
    return True


def _write_results_csv(vsp, result_id: str, path: Path) -> bool:
    if not result_id:
        return False
    try:
        vsp.WriteResultsCSVFile(result_id, str(path))
    except Exception:  # noqa: BLE001 - OpenVSP raises in several ways on empty results
        return False
    return path.is_file() and path.stat().st_size > 0


def _vspgeom_header(path: Path) -> Dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(256)
    except OSError:
        return {"parsed": False}
    text = raw.replace(b"\r\n", b"\n").decode("utf-8", errors="replace")
    lines = text.split("\n")
    header: Dict[str, Any] = {"parsed": False, "lines": lines[:4]}
    try:
        counts = [int(value) for value in lines[2].split()]
        header.update({"parsed": True, "format": lines[0].strip(), "nodes": counts[0],
                       "elements": counts[1]})
    except (IndexError, ValueError):
        pass
    return header


def _setup_fields(path: Path) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            fields[key.strip()] = value.strip()
    return fields


def _read_int_input(vsp, analysis: str, names: Mapping[str, str], key: str) -> Optional[int]:
    actual = names.get(key.lower())
    if actual is None:
        return None
    try:
        return int(vsp.GetIntAnalysisInput(analysis, actual)[0])
    except Exception:  # noqa: BLE001 - readback must never abort the zero-solver build
        return None


def _read_double_input(vsp, analysis: str, names: Mapping[str, str], key: str) -> Optional[float]:
    actual = names.get(key.lower())
    if actual is None:
        return None
    try:
        return float(vsp.GetDoubleAnalysisInput(analysis, actual)[0])
    except Exception:  # noqa: BLE001
        return None


READBACK_INT_KEYS = ("RefFlag", "NCPU", "GeomSet", "ThinGeomSet", "StopBeforeRun",
                     "MachNpts", "AlphaNpts", "BetaNpts", "NumWakeNodes", "Symmetry")
READBACK_DOUBLE_KEYS = ("Sref", "Cref", "Bref", "Xcg", "Ycg", "Zcg", "MachStart",
                        "MachEnd", "AlphaStart", "AlphaEnd", "BetaStart", "BetaEnd",
                        "Vinf", "Rho", "ReCref")


def sweep_input_readback(vsp, analysis: str,
                         names: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Read back the VSPAEROSweep analysis inputs in force (no solver start).

    The .vspaero text file only carries the physical flow conditions; RefFlag, NCPU,
    GeomSet/ThinGeomSet and StopBeforeRun live in the analysis state and are read
    back through the API so preflight can evidence them line by line.
    """
    table = dict(names) if names is not None else _analysis_input_map(vsp, analysis)
    ints = {key: _read_int_input(vsp, analysis, table, key) for key in READBACK_INT_KEYS}
    doubles = {key: _read_double_input(vsp, analysis, table, key) for key in READBACK_DOUBLE_KEYS}
    return {
        "analysis": analysis,
        "inputs_int": ints,
        "inputs_double": doubles,
        "available_int_keys": sorted(key for key, value in ints.items() if value is not None),
        "available_double_keys": sorted(key for key, value in doubles.items() if value is not None),
    }


def readback_checks(readback: Mapping[str, Any], expected_int: Mapping[str, Any],
                    expected_double: Mapping[str, Any],
                    rel_tol: float = 1.0e-9) -> Dict[str, Any]:
    """Compare an analysis readback with the frozen solver contract (no solver start)."""
    ints = readback.get("inputs_int") or {}
    doubles = readback.get("inputs_double") or {}
    mismatches: List[str] = []
    int_out: Dict[str, Any] = {}
    double_out: Dict[str, Any] = {}
    for key, expected in expected_int.items():
        observed = ints.get(key)
        ok = observed is not None and int(observed) == int(expected)
        int_out[key] = {"expected": int(expected), "observed": observed, "ok": bool(ok)}
        if not ok:
            mismatches.append("int:" + key)
    for key, expected in expected_double.items():
        observed = doubles.get(key)
        ok = (observed is not None and
              abs(float(observed) - float(expected))
              <= rel_tol * max(1.0, abs(float(expected))))
        double_out[key] = {"expected": float(expected), "observed": observed, "ok": bool(ok)}
        if not ok:
            mismatches.append("double:" + key)
    return {"schema": "dreal001.sweep_input_readback_check.v1", "ok": not mismatches,
            "int": int_out, "double": double_out, "mismatches": mismatches}

def prepare_case(
    geometry: Any,
    case_dir: str | Path,
    basename: str,
    geometry_set: str = TASK_SPEC.default_geometry_set,
    alphas_deg: Sequence[float] = TASK_SPEC.alpha_fixed_list_deg,
    tess_u: Optional[float] = None,
    tess_w: Optional[float] = None,
    openvsp_root: str | Path = DEFAULT_OPENVSP_ROOT,
    sym_max_deg: float = 0.0,
    n_wake_nodes: Optional[int] = None,
    solver_overrides: Optional[Mapping[str, float]] = None,
    write_vsp3: bool = True,
    mach_values: Optional[Sequence[float]] = None,
    rebuild_strategy: str = "direct",
    target_mesh_family: Optional[Sequence[int]] = None,
    max_mesh_attempts: int = MAX_MESH_ATTEMPTS,
) -> Dict[str, Any]:
    """Build the model and write .vspgeom/.vkey/.vspaero. Performs NO solver start."""
    if geometry_set not in GEOMETRY_SET_CODES:
        raise ValueError("geometry_set must be one of %s" % sorted(GEOMETRY_SET_CODES))
    case_dir = Path(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    alphas = [float(alpha) for alpha in alphas_deg]
    if not alphas:
        raise ValueError("alphas_deg must not be empty")
    low, high = TASK_SPEC.alpha_window_deg
    for alpha in alphas:
        if not (low <= alpha <= high):
            raise ValueError("alpha %r outside preregistered window %r" % (alpha, TASK_SPEC.alpha_window_deg))

    sref = float(geometry.wing.area_m2)
    vinf = TASK_SPEC.vinf_m_s
    rho = TASK_SPEC.rho_kg_m3
    recref = TASK_SPEC.recref
    machs = [float(value) for value in
             (mach_values if mach_values is not None else [TASK_SPEC.mach])]
    if not machs:
        raise ValueError("mach_values must not be empty")
    require_arithmetic_sequence(machs, "mach list")
    mach = machs[0]
    internal_cases_expected = int(len(alphas) * len(machs))
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()

    if rebuild_strategy not in ("direct", "roundtrip"):
        raise ValueError("rebuild_strategy must be 'direct' or 'roundtrip'")
    target_family = tuple(int(value) for value in (target_mesh_family or TARGET_MESH_FAMILY))
    if rebuild_strategy == "roundtrip" and not write_vsp3:
        raise ValueError("roundtrip rebuild requires write_vsp3=True (the .vsp3 is loaded back)")

    vsp = import_openvsp(openvsp_root)
    # The OpenVSP python module is a process-wide singleton: a previous prepare_case
    # call (or a previous configuration in the same preflight process) may still hold a
    # model.  Clear it first, otherwise the new wing/tail are appended to the old model
    # and the mesh family becomes 923x834 / 1043x942 instead of 543x472 / 483x418.
    try:
        vsp.ClearVSPModel()
        vsp.Update()
    except Exception:
        pass
    built = build_model(vsp, geometry, TASK_SPEC.solver_geometry_components, tess_u, tess_w)
    geoms = built["geoms"]

    vsp3_path = case_dir / (basename + ".vsp3")
    if write_vsp3:
        vsp.WriteVSPFile(str(vsp3_path), vsp.SET_ALL)
        if not vsp3_path.is_file():
            raise RuntimeError("OpenVSP did not write %s" % vsp3_path)

    geom_set, thin_set = GEOMETRY_SET_CODES[geometry_set]
    geometry_analysis = "VSPAEROComputeGeometry"
    vspgeom_path = case_dir / (basename + ".vspgeom")
    vkey_path = case_dir / (basename + ".vkey")
    csf_path = case_dir / (basename + ".csf")
    mesh_attempt_history: List[Dict[str, Any]] = []
    geom_result_id = None
    geom_csv_written = False

    def compute_geometry_once() -> Any:
        vsp.SetAnalysisInputDefaults(geometry_analysis)
        geom_inputs = _analysis_input_map(vsp, geometry_analysis)
        for key, value in (("GeomSet", geom_set), ("ThinGeomSet", thin_set),
                           ("Symmetry", 0), ("CullFracFlag", 0)):
            _set_int(vsp, geometry_analysis, geom_inputs, key, value)
        result_id = vsp.ExecAnalysis(geometry_analysis)
        vsp.Update()
        return result_id

    if rebuild_strategy == "roundtrip":
        # Rejection sampling of the mesh topology family. Every attempt rebuilds the
        # geometry from x12, saves a fresh .vsp3, loads it back (ClearVSPModel +
        # ReadVSPFile) and only then runs VSPAEROComputeGeometry; the first sample whose
        # (nodes, elements) equals the target family is kept, otherwise FAIL_CLOSED.
        # The .vsp3 round-trip removes the in-memory-object-ID dependence that makes a
        # direct compute alternate between 543/472 and 483/418 for the same x12.
        for attempt in range(1, max(int(max_mesh_attempts), 1) + 1):
            if attempt > 1:
                # Fresh rebuild: the previous attempt left the model loaded from its
                # .vsp3, so clear it before adding the wing/tail again; otherwise each
                # attempt would stack duplicate components and inflate the topology
                # (observed families 923x834 / 1043x942 instead of 543x472 / 483x418).
                vsp.ClearVSPModel()
                vsp.Update()
                built = build_model(vsp, geometry, TASK_SPEC.solver_geometry_components,
                                    tess_u, tess_w)
                geoms = built["geoms"]
            if not write_vsp3:
                raise ValueError("roundtrip rebuild requires write_vsp3=True")
            vsp.WriteVSPFile(str(vsp3_path), vsp.SET_ALL)
            if not vsp3_path.is_file():
                raise RuntimeError("OpenVSP did not write %s" % vsp3_path)
            vsp.ClearVSPModel()
            vsp.ReadVSPFile(str(vsp3_path))
            vsp.Update()
            for stale in (vspgeom_path, vkey_path, csf_path):
                if stale.exists():
                    stale.unlink()
            geom_result_id = compute_geometry_once()
            if not vspgeom_path.is_file():
                raise RuntimeError("VSPAEROComputeGeometry did not write %s" % vspgeom_path.name)
            described = describe_mesh(vspgeom_path)
            mesh_attempt_history.append({
                "attempt": attempt,
                "mesh_family": described["mesh_family"],
                "nodes": described["nodes"],
                "elements": described["elements"],
                "vspgeom_sha256": described["vspgeom_sha256"],
                "vspgeom_bytes": described["vspgeom_bytes"],
                "canonical_mesh_sha256": described["canonical_mesh_sha256"],
                "vsp3_sha256": (sha256_file(vsp3_path) if vsp3_path.is_file() else None),
            })
            if (described["nodes"], described["elements"]) == target_family:
                break
        else:
            raise MeshFamilyUnavailable(target_family, mesh_attempt_history)
    else:
        geom_result_id = compute_geometry_once()
        if vspgeom_path.is_file():
            described = describe_mesh(vspgeom_path)
            mesh_attempt_history.append({
                "attempt": 1,
                "mesh_family": described["mesh_family"],
                "nodes": described["nodes"],
                "elements": described["elements"],
                "vspgeom_sha256": described["vspgeom_sha256"],
                "vspgeom_bytes": described["vspgeom_bytes"],
                "canonical_mesh_sha256": described["canonical_mesh_sha256"],
            })

    geom_csv = case_dir / (basename + "_vspaero_geom.csv")
    geom_csv_written = _write_results_csv(vsp, geom_result_id, geom_csv)

    missing = [path.name for path in (vspgeom_path, vkey_path) if not path.is_file()]
    if missing:
        raise RuntimeError("VSPAEROComputeGeometry did not write %s" % ", ".join(missing))

    sweep_analysis = "VSPAEROSweep"
    vsp.SetAnalysisInputDefaults(sweep_analysis)
    sweep_inputs = _analysis_input_map(vsp, sweep_analysis)
    required = ["Sref", "Cref", "Bref", "Xcg", "Ycg", "Zcg", "MachStart", "MachEnd",
                "MachNpts", "AlphaStart", "AlphaEnd", "AlphaNpts", "BetaStart",
                "BetaEnd", "BetaNpts", "RefFlag", "Symmetry", "StopBeforeRun",
                "Vinf", "Rho", "ReCref"]
    missing_inputs = [name for name in required if name.lower() not in sweep_inputs]
    if missing_inputs:
        raise RuntimeError("VSPAEROSweep is missing contract inputs: %s" % missing_inputs)

    overrides = dict(solver_overrides or {})
    # VSPAEROSweep's *Npts inputs are integer-typed (api_compat_355.json type 1);
    # setting them through SetDoubleAnalysisInput silently keeps the default of 3,
    # which is how the ENV_SMOKE setup ended up with "AoA = 2, 2, 2".
    require_arithmetic_alpha_list(alphas)
    double_inputs = {
        "Sref": sref, "Cref": TASK_SPEC.cref_m, "Bref": TASK_SPEC.bref_m,
        "Xcg": TASK_SPEC.xcg_m, "Ycg": 0.0, "Zcg": 0.0,
        "MachStart": machs[0], "MachEnd": machs[-1],
        "AlphaStart": alphas[0], "AlphaEnd": alphas[-1],
        "BetaStart": 0.0, "BetaEnd": 0.0,
        "Vinf": vinf, "Rho": rho, "ReCref": recref,
    }
    double_inputs.update({key: float(value) for key, value in overrides.items()})
    applied: Dict[str, Any] = {}
    for key, value in double_inputs.items():
        applied[key] = _set_double(vsp, sweep_analysis, sweep_inputs, key, value)
    for key, value in (("RefFlag", 0), ("Symmetry", 0), ("StopBeforeRun", 1), ("NCPU", 1),
                       ("MachNpts", len(machs)), ("AlphaNpts", len(alphas)), ("BetaNpts", 1)):
        applied[key] = _set_int(vsp, sweep_analysis, sweep_inputs, key, value)
    for key, value in (("GeomSet", geom_set), ("ThinGeomSet", thin_set)):
        applied[key] = _set_int(vsp, sweep_analysis, sweep_inputs, key, value)
    if n_wake_nodes is not None:
        if not _set_int(vsp, sweep_analysis, sweep_inputs, "NumWakeNodes", int(n_wake_nodes)):
            _set_int(vsp, sweep_analysis, sweep_inputs, "WakeNumIter", int(n_wake_nodes))
    not_applied = sorted(key for key, ok in applied.items() if not ok)
    if not_applied:
        raise RuntimeError("VSPAEROSweep inputs could not be set: %s" % not_applied)

    sweep_result_id = vsp.ExecAnalysis(sweep_analysis)
    vsp.Update()
    readback = sweep_input_readback(vsp, sweep_analysis)
    expected_int_inputs: Dict[str, int] = {
        "RefFlag": 0, "NCPU": 1, "GeomSet": int(geom_set), "ThinGeomSet": int(thin_set),
        "StopBeforeRun": 1, "MachNpts": len(machs), "AlphaNpts": len(alphas), "BetaNpts": 1,
    }
    if n_wake_nodes is not None:
        expected_int_inputs["NumWakeNodes"] = int(n_wake_nodes)
    expected_double_inputs = {
        "Sref": sref, "Cref": TASK_SPEC.cref_m, "Bref": TASK_SPEC.bref_m,
        "Xcg": TASK_SPEC.xcg_m, "Ycg": 0.0, "Zcg": 0.0,
        "MachStart": machs[0], "MachEnd": machs[-1],
        "AlphaStart": alphas[0], "AlphaEnd": alphas[-1],
        "BetaStart": 0.0, "BetaEnd": 0.0,
        "Vinf": vinf, "Rho": rho, "ReCref": recref,
    }
    readback_check = readback_checks(readback, expected_int_inputs, expected_double_inputs)
    if not readback_check["ok"]:
        raise RuntimeError("VSPAEROSweep readback does not match the contract: %s"
                           % readback_check["mismatches"])
    setup_path = case_dir / (basename + ".vspaero")
    if not setup_path.is_file():
        raise RuntimeError("VSPAEROSweep did not write %s" % setup_path)

    fields = _setup_fields(setup_path)
    expected_setup = {
        "Sref": sref, "Cref": TASK_SPEC.cref_m, "Bref": TASK_SPEC.bref_m,
        "X_cg": TASK_SPEC.xcg_m, "Vinf": vinf, "Rho": rho,
        "ReCref": recref,
    }
    setup_check: Dict[str, Any] = {}
    for key, expected in expected_setup.items():
        raw = fields.get(key)
        try:
            observed = float(raw) if raw is not None else None
        except ValueError:
            observed = raw
        ok = observed is not None and abs(float(observed) - expected) <= 1.0e-9 * max(1.0, abs(expected))
        setup_check[key] = {"expected": expected, "observed": observed, "ok": ok}
    observed_machs = _setup_alpha_list(fields.get("Mach"))
    if len(machs) == 1:
        mach_list_ok = (len(observed_machs) == 1 and
                        abs(observed_machs[0] - machs[0]) <= 1.0e-9 * max(1.0, abs(machs[0])))
    else:
        mach_list_ok = len(observed_machs) == len(machs) and all(
            abs(observed - expected) <= 1.0e-9 * max(1.0, abs(expected))
            for observed, expected in zip(observed_machs, machs))
    setup_check["Mach_list"] = {"expected": [float(m) for m in machs],
                                "observed": observed_machs, "ok": bool(mach_list_ok)}
    bad = [key for key, entry in setup_check.items() if not entry["ok"]]
    if bad:
        raise RuntimeError("written .vspaero does not carry the frozen contract: %s" % bad)

    observed_alphas = _setup_alpha_list(fields.get("AoA"))
    alpha_list_ok = len(observed_alphas) == len(alphas) and all(
        abs(observed - expected) <= 1.0e-9 * max(1.0, abs(expected))
        for observed, expected in zip(observed_alphas, alphas))
    setup_check["AoA_list"] = {"expected": [float(a) for a in alphas],
                               "observed": observed_alphas, "ok": bool(alpha_list_ok)}
    if not alpha_list_ok:
        raise RuntimeError("written .vspaero AoA list %r does not equal requested %r"
                           % (observed_alphas, [float(a) for a in alphas]))

    artifacts = {}
    for label, path in (("vspgeom", vspgeom_path), ("vkey", vkey_path),
                        ("vspaero", setup_path), ("csf", csf_path), ("vsp3", vsp3_path)):
        if path.is_file():
            artifacts[label] = {"path": str(path), "bytes": path.stat().st_size,
                                "sha256": sha256_file(path)}
    if not geom_csv_written:
        artifacts.pop("geom_csv", None)
    else:
        artifacts["geom_csv"] = {"path": str(geom_csv), "bytes": geom_csv.stat().st_size,
                                 "sha256": sha256_file(geom_csv)}
    geometry_sha = artifacts["vspgeom"]["sha256"]
    input_sha = sha256_tree([vspgeom_path, setup_path])
    header = _vspgeom_header(vspgeom_path)
    record = {
        "schema": "dreal001.vspaero_case_inputs.v1",
        "case_id": basename,
        "task_id": "TOOLING" if "ENV_SMOKE" in basename.upper() else "P0_INPUT_PREP",
        "generated_utc": timestamp,
        "openvsp_root": str(openvsp_root),
        "openvsp_version": str(vsp.GetVSPVersion()),
        "python_version": platform.python_version(),
        "solver_started": False,       # VSPAEROComputeGeometry + StopBeforeRun=1 only
        "physical_solver_starts": 0,
        "geometry_set": geometry_set,
        "geometry_set_codes": {"GeomSet": geom_set, "ThinGeomSet": thin_set},
        "solver_geometry_components": list(TASK_SPEC.solver_geometry_components),
        "solver_includes_fuselage": TASK_SPEC.solver_includes_fuselage,
        "tessellation": built["tessellation"],
        "component_metrics": built["metrics"],
        "sref_m2": sref,
        "cref_m": float(TASK_SPEC.cref_m),
        "bref_m": float(TASK_SPEC.bref_m),
        "xcg_m": float(TASK_SPEC.xcg_m),
        "sweep_input_readback": readback,
        "sweep_readback_check": readback_check,
        "cl_required": TASK_SPEC.cl_required(sref),
        "reference_injection": TASK_SPEC.reference_injection(sref),
        "design_variable_identification": {
            "W01": {"name": "wing_area", "role": "sets Sref",
                    "baseline_m2": TASK_SPEC.sref_baseline_m2,
                    "range_m2": [300.0, 420.0],
                    "sref_recompute_rule": TASK_SPEC.sref_recompute_rule},
            "sref_recompute_rule": TASK_SPEC.sref_recompute_rule,
        },
        "solver_invocation": {
            "argv": solver_command(basename, alphas),
            "fs_cli_used": False,
            "one_process_one_start": True,
            "internal_solver_cases_expected": int(internal_cases_expected),
            "note": "case lists live in .vspaero; -fs/-mach are forbidden (7.2.2 appends them)",
        },
        "alpha_list_deg": alphas,
        "mach_list": machs,
        "alpha_in_one_process_note": "alpha/mach/beta lists are written into .vspaero "
                                     "(AlphaStart/AlphaEnd/AlphaNpts, integer-typed); the solver "
                                     "is invoked WITHOUT -fs because VSPAERO 7.2.2 appends -fs "
                                     "lists to the file lists instead of replacing them",
        "internal_solver_cases_expected": int(internal_cases_expected),
        "setup_sweep_fields": {key: fields.get(key) for key in
                               ("Mach", "AoA", "AlphaStart", "AlphaNpts", "Vinf", "Rho", "ReCref")},
        "setup_contract_check": setup_check,
        "sweep_result_id": sweep_result_id,
        "geometry_result_id": geom_result_id,
        "vspgeom_header": header,
        "artifacts": artifacts,
        "geometry_sha256": geometry_sha,
        "geometry_sha256_definition": "sha256(raw bytes of <base>.vspgeom)",
        "vspaero_input_sha256": input_sha,
        "vspaero_input_sha256_definition": "sha256 over [<base>.vspgeom, <base>.vspaero] name+sha256 pairs",
        "build_seconds": round(time.perf_counter() - started, 3),
    }
    last_mesh = mesh_attempt_history[-1] if mesh_attempt_history else {}
    record["mesh"] = {
        "schema": "dreal001.mesh_identity.v1",
        "rebuild_strategy": rebuild_strategy,
        "target_mesh_family": "%dx%d" % (target_family[0], target_family[1]),
        "max_mesh_attempts": int(max_mesh_attempts),
        "mesh_attempts": len(mesh_attempt_history),
        "mesh_family": last_mesh.get("mesh_family"),
        "nodes": last_mesh.get("nodes"),
        "elements": last_mesh.get("elements"),
        "vspgeom_sha256": last_mesh.get("vspgeom_sha256"),
        "vspgeom_bytes": last_mesh.get("vspgeom_bytes"),
        "canonical_mesh_sha256": last_mesh.get("canonical_mesh_sha256"),
        "roundtrip_vsp3_sha256": (sha256_file(vsp3_path) if vsp3_path.is_file() else None),
        "attempt_history": mesh_attempt_history,
        "note": "byte SHA varies across rebuilds even in the target family; canonical_mesh_sha256 "
                "removes object-ID/ordering bytes but keeps per-node geometry (occasional ~1e-2 m "
                "single-node jitter is disclosed, not normalised away).",
    }
    record_path = case_dir / "case_inputs.json"
    record_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def solver_command(basename: str, alphas_deg: Sequence[float],
                   mach: float = TASK_SPEC.mach, omp: int = 1,
                   vspaero_path: Optional[str] = None,
                   use_command_line_lists: bool = False) -> List[str]:
    """Canonical VSPAERO 7.2.2 argv; one process = one physical solver start.

    Default argv carries NO -fs/-mach: the case lists live in .vspaero (see
    require_arithmetic_alpha_list) so one start solves exactly the preregistered
    internal case matrix.  VSPAERO 7.2.2 merges -fs lists with the file lists,
    which turned the ENV_SMOKE 5-case matrix into 32 internal cases.
    """
    path = vspaero_path or str(Path(DEFAULT_OPENVSP_ROOT) / "vspaero.exe")
    alphas = [float(alpha) for alpha in alphas_deg]
    if not use_command_line_lists:
        return [path, "-omp", str(int(omp)), basename]
    argv = [path, "-omp", str(int(omp)), "-fs", "%.10g" % mach, "END"]
    argv += ["%.10g" % alpha for alpha in alphas]
    argv += ["END", "0", "END", basename]
    return argv


def _geometry_from_design_vector(values: Sequence[float]):
    from research.concorde_metaopt.aircraft.design_space import load_design_space
    from research.concorde_metaopt.aircraft.geometry_model import build_geometry

    config = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
    space = load_design_space(str(config))
    names = [variable.name for variable in space.variables] + \
            [variable.name for variable in space.fixed_variables]
    if len(values) != len(space.variables):
        raise ValueError("expected %d design values, got %d" % (len(space.variables), len(values)))
    baseline = dict(space.baseline_dict())
    for fixed in space.fixed_variables:
        baseline[fixed.name] = float(fixed.baseline)
    baseline_input = [float(baseline[name]) for name in names]
    for index, variable in enumerate(space.variables):
        baseline_input[names.index(variable.name)] = float(values[index])
    return build_geometry(names, baseline_input), space


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare VSPAERO inputs (zero solver starts)")
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--basename", required=True)
    parser.add_argument("--geometry-set", default=TASK_SPEC.default_geometry_set,
                        choices=sorted(GEOMETRY_SET_CODES))
    parser.add_argument("--alphas", type=float, nargs="+", default=list(TASK_SPEC.alpha_fixed_list_deg))
    parser.add_argument("--tess-u", type=float, default=None)
    parser.add_argument("--tess-w", type=float, default=None)
    parser.add_argument("--design-json", default=None,
                        help="optional JSON list of 12 design-variable values (default: baseline)")
    parser.add_argument("--openvsp-root", default=DEFAULT_OPENVSP_ROOT)
    args = parser.parse_args(argv)

    if args.design_json:
        values = json.loads(Path(args.design_json).read_text(encoding="utf-8"))
        geometry, space = _geometry_from_design_vector(values)
        design = {"x12": [float(value) for value in values],
                  "names": [variable.name for variable in space.variables],
                  "source": args.design_json}
    else:
        from research.concorde_metaopt.aircraft.design_space import load_design_space

        config = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
        space = load_design_space(str(config))
        baseline = space.baseline_dict()
        x12 = [float(baseline[variable.name]) for variable in space.variables]
        geometry, space = _geometry_from_design_vector(x12)
        design = {"x12": x12,
                  "names": [variable.name for variable in space.variables],
                  "source": "design_space baseline"}
    record = prepare_case(
        geometry, args.case_dir, args.basename, geometry_set=args.geometry_set,
        alphas_deg=args.alphas, tess_u=args.tess_u, tess_w=args.tess_w,
        openvsp_root=args.openvsp_root,
    )
    record["design"] = design
    Path(args.case_dir, "case_inputs.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "case_inputs": str(Path(args.case_dir, "case_inputs.json")),
        "geometry_sha256": record["geometry_sha256"],
        "vspgeom_header": record["vspgeom_header"],
        "sref_m2": record["sref_m2"],
        "setup_sweep_fields": record["setup_sweep_fields"],
        "command": solver_command(args.basename, args.alphas),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
