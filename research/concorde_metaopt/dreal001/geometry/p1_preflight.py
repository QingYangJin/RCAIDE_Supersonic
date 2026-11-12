"""D-REAL-001 P1 pre-launch preflight: six unique solver configurations (ZERO solver starts).

For every unique P1 solver configuration this module builds the VSPAERO 7.2.2 input set
with the OpenVSP 3.55 Python API only (VSPAEROComputeGeometry + VSPAEROSweep with
StopBeforeRun=1), writes the four input pieces into
runs/<P1 run id>/preflight/<config_id>/ and then parses the generated .vspaero back so
the preflight can evidence, line by line:

  * the physical flow conditions (Sref/Cref/Bref/X_cg/Y_cg/Z_cg, Mach list, AoA list,
    Beta, ReCref, Vinf, Rho, NumWakeNodes, Symmetry);
  * the analysis-state inputs that never reach the text file (RefFlag=0, NCPU=1,
    GeomSet/ThinGeomSet, StopBeforeRun=1, MachNpts/AlphaNpts/BetaNpts) through the
    OpenVSP API readback;
  * SHA256 of the four pieces plus the solver argv, proving the command line carries
    no -fs / -mach / -alpha / -beta list flag.

The .vsp3 model is also saved in each preflight directory: VSPAEROComputeGeometry
derives the .vspgeom/.vkey names from the current model file, so an unsaved model would
write "Unnamed.*" into the process working directory instead of the case directory.

vspaero.exe is never launched: physical_solver_starts = 0 and solver_started = false in
every record.  Running this module is a zero-physics action and does not consume the P1
start or internal-case budget.

CLI:

    <python> -m research.concorde_metaopt.dreal001.geometry.p1_preflight \
        --run-dir research/concorde_metaopt/dreal001/geometry/runs/DREAL001-P1-20261110-01
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.aircraft.geometry_model import build_geometry

from . import openvsp_model
from .mesh_identity import MAX_MESH_ATTEMPTS, TARGET_MESH_FAMILY, family_label
from .openvsp_model import (
    DEFAULT_OPENVSP_ROOT,
    REPO_ROOT,
    TASK_SPEC,
    _setup_fields,
    prepare_case,
    solver_command,
)

PREFLIGHT_SCHEMA = "dreal001.p1_preflight.v1"
PREFLIGHT_INDEX_SCHEMA = "dreal001.p1_preflight_index.v1"
DEFAULT_P1_RUN_ID = "DREAL001-P1-20261110-01"
DESIGN_SPACE_CONFIG = (REPO_ROOT / "research" / "concorde_metaopt" / "configs" /
                       "design_space_12d_lifting_surfaces.yaml")
FORBIDDEN_CLI_FLAGS = ("-fs", "-mach", "-alpha", "-beta")
REQUIRED_FILE_FIELDS = ("Sref", "Cref", "Bref", "X_cg", "Y_cg", "Z_cg", "Mach", "AoA",
                        "Beta", "ReCref", "Vinf", "Rho", "NumWakeNodes", "Symmetry")
BASENAME = "concorde_baseline"

#: The eight unique P1 solver configurations required by governance v3 section 12.10.3.
#: P1-07 (12-variable probes) reuses CFG-01: only the planform changes, the solver
#: configuration (thin 12x25, wake 8, Mach 2.02, fixed 7-alpha list) is identical, and
#: every probe design gets its own .vspgeom SHA recorded when its inputs are prepared.
#: v1.3 (Lead decision L-06) adds thick 24x49 and thick 48x97 negative controls so that
#: stop condition S2a is testable at all three panel densities.
P1_CONFIGS: List[Dict[str, Any]] = [
    {
        "config_id": "CFG-01-thin-12x25",
        "target_mesh_family": [543, 472],
        "label": "baseline thin production grid, wake 8",
        "geometry_set": "thin", "tess_u": 12, "tess_w": 25,
        "n_wake_nodes": 8, "mach_values": [TASK_SPEC.mach],
        "case_keys": ["P1-00a", "P1-00b", "P1-00c", "P1-02a", "P1-07"],
        "expected_internal_cases_per_start": 7,
    },
    {
        "config_id": "CFG-02-thin-24x49",
        "target_mesh_family": [923, 834],
        "label": "middle panel density (A5-F2 grid chain)",
        "geometry_set": "thin", "tess_u": 24, "tess_w": 49,
        "n_wake_nodes": 8, "mach_values": [TASK_SPEC.mach],
        "case_keys": ["P1-02c"],
        "expected_internal_cases_per_start": 7,
    },
    {
        "config_id": "CFG-03-thin-48x97",
        "target_mesh_family": [2041, 1881],
        "label": "fine panel density (A5-F2 grid chain)",
        "geometry_set": "thin", "tess_u": 48, "tess_w": 97,
        "n_wake_nodes": 8, "mach_values": [TASK_SPEC.mach],
        "case_keys": ["P1-02b"],
        "expected_internal_cases_per_start": 7,
    },
    {
        "config_id": "CFG-04-thin-12x25-wake128",
        "target_mesh_family": [543, 472],
        "label": "wake-node sensitivity, 128 wake nodes",
        "geometry_set": "thin", "tess_u": 12, "tess_w": 25,
        "n_wake_nodes": 128, "mach_values": [TASK_SPEC.mach],
        "case_keys": ["P1-03"],
        "expected_internal_cases_per_start": 7,
    },
    {
        "config_id": "CFG-05-thick-12x25",
        "target_mesh_family": [999, 986],
        "label": "thick negative control (production surface cross-check)",
        "geometry_set": "thick", "tess_u": 12, "tess_w": 25,
        "n_wake_nodes": 8, "mach_values": [TASK_SPEC.mach],
        "case_keys": ["P1-04"],
        "expected_internal_cases_per_start": 7,
    },
    {
        "config_id": "CFG-06-thin-12x25-mach-sweep",
        "target_mesh_family": [543, 472],
        "label": "Mach trend 1.8/2.0/2.2 written into .vspaero",
        "geometry_set": "thin", "tess_u": 12, "tess_w": 25,
        "n_wake_nodes": 8, "mach_values": [1.8, 2.0, 2.2],
        "case_keys": ["P1-05"],
        "expected_internal_cases_per_start": 21,
    },
    {
        "config_id": "CFG-07-thick-24x49",
        "target_mesh_family": [1985, 1958],
        "label": "thick negative control at middle panel density (v1.3 L-06 / A5 X2)",
        "geometry_set": "thick", "tess_u": 24, "tess_w": 49,
        "n_wake_nodes": 8, "mach_values": [TASK_SPEC.mach],
        "case_keys": ["P1-04b"],
        "expected_internal_cases_per_start": 7,
    },
    {
        "config_id": "CFG-08-thick-48x97",
        "target_mesh_family": [3961, 3908],
        "label": "thick negative control at fine panel density (v1.3 L-06 / A5 X2)",
        "geometry_set": "thick", "tess_u": 48, "tess_w": 97,
        "n_wake_nodes": 8, "mach_values": [TASK_SPEC.mach],
        "case_keys": ["P1-04c"],
        "expected_internal_cases_per_start": 7,
    },
]

#: L-09 (Lead 2026-11-10): the target mesh family of a configuration is selected by
#: THIS batch's own zero-physics sampling. Six independent rebuilds are recorded per
#: configuration; the target family is the most frequent sample family, ties broken by
#: the family that reached two occurrences earliest. No claim about historical P1/P0
#: families is made.
SELECTION_SCHEMA = "dreal001.p1_mesh_selection.v1"
SELECTION_SAMPLES = 6
SELECTION_RULE = (
    "six zero-physics rebuild samples per configuration; target = most frequent "
    "(nodes, elements) family; tie -> the family that reached two occurrences earliest"
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def forbidden_flags_in_argv(argv: Sequence[str]) -> List[str]:
    """Return every forbidden list flag found in the solver argv (empty = clean)."""
    found: List[str] = []
    for token in list(argv)[1:]:
        lowered = str(token).strip().lower()
        for flag in FORBIDDEN_CLI_FLAGS:
            if lowered == flag or lowered.startswith(flag):
                found.append(lowered)
    return sorted(set(found))


def _parse_value(raw: Optional[str]) -> Any:
    if raw is None:
        return None
    text = str(raw).strip()
    if "," in text:
        values = []
        for token in text.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                values.append(float(token))
            except ValueError:
                return text
        return values
    try:
        return float(text)
    except ValueError:
        return text


def _scalar_ok(observed: Any, expected: float, rel_tol: float = 1.0e-9) -> bool:
    try:
        value = float(observed)
    except (TypeError, ValueError):
        return False
    return abs(value - float(expected)) <= rel_tol * max(1.0, abs(float(expected)))


def _list_ok(observed: Any, expected: Sequence[float], rel_tol: float = 1.0e-9) -> bool:
    if not isinstance(observed, list) or len(observed) != len(expected):
        return False
    return all(_scalar_ok(value, want, rel_tol) for value, want in zip(observed, expected))


def baseline_geometry():
    """Build the baseline 12D geometry (thin/thick is a solver GeomSet only)."""
    space = load_design_space(str(DESIGN_SPACE_CONFIG))
    names = [variable.name for variable in space.variables] + \
            [variable.name for variable in space.fixed_variables]
    values = dict(space.baseline_dict())
    for fixed in space.fixed_variables:
        values[fixed.name] = float(fixed.baseline)
    geometry = build_geometry(names, [float(values[name]) for name in names])
    x12 = [float(values[variable.name]) for variable in space.variables]
    return geometry, space, x12, names


def file_readback(setup_path: Path, expected: Mapping[str, Any]) -> Dict[str, Any]:
    """Parse the generated .vspaero and compare it with the contract line by line."""
    fields = _setup_fields(setup_path)
    entries: Dict[str, Any] = {}
    mismatches: List[str] = []
    for key in REQUIRED_FILE_FIELDS:
        observed = _parse_value(fields.get(key))
        want = expected.get(key)
        if isinstance(want, (list, tuple)):
            wanted = [float(value) for value in want]
            if len(wanted) == 1 and not isinstance(observed, (list, tuple)):
                # 单点扫描：VSPAERO 允许把 MachStart/MachEnd 写成同一个标量，回读按标量比较。
                ok = _scalar_ok(observed, wanted[0])
            else:
                ok = _list_ok(observed, wanted)
        else:
            ok = _scalar_ok(observed, float(want))
        entries[key] = {"expected": want, "observed": observed, "ok": bool(ok)}
        if not ok:
            mismatches.append(key)
    return {
        "schema": "dreal001.vspaero_file_readback.v1",
        "fields": entries,
        "raw_fields": {key: fields.get(key) for key in REQUIRED_FILE_FIELDS},
        "mismatches": sorted(mismatches),
        "ok": not mismatches,
    }


def expected_setup_values(sref_m2: float, alphas: Sequence[float],
                          machs: Sequence[float], n_wake_nodes: Optional[int]) -> Dict[str, Any]:
    """The frozen contract expected back in the .vspaero text file."""
    expected: Dict[str, Any] = {
        "Sref": float(sref_m2),
        "Cref": TASK_SPEC.cref_m,
        "Bref": TASK_SPEC.bref_m,
        "X_cg": TASK_SPEC.xcg_m,
        "Y_cg": 0.0,
        "Z_cg": 0.0,
        "Mach": [float(value) for value in machs],
        "AoA": [float(value) for value in alphas],
        "Beta": 0.0,
        "ReCref": TASK_SPEC.recref,
        "Vinf": TASK_SPEC.vinf_m_s,
        "Rho": TASK_SPEC.rho_kg_m3,
        "Symmetry": 0.0,
    }
    if n_wake_nodes is not None:
        expected["NumWakeNodes"] = int(n_wake_nodes)
    return expected


CONTRACT_DIGEST_SCHEMA = "dreal001.p1_contract_digest.v1"
CONTRACT_DIGEST_NOTE = (
    "sha256 over the semantic solver contract only (no OpenVSP object IDs, no timestamps, no "
    "absolute paths): reference values, case lists, GeomSet, tessellation, wake nodes, "
    "RefFlag/NCPU/StopBeforeRun, solver executable identity, design-space config SHA256 and the "
    "12 baseline design values at %.12g. This digest IS reproducible across preparations; the four "
    "input-piece SHA256s are NOT, because OpenVSP writes random 10-character object IDs into "
    ".vsp3/.vkey and the .vspgeom mesher is not byte-deterministic.")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def solver_sha256(openvsp_root: str | Path = DEFAULT_OPENVSP_ROOT) -> Optional[str]:
    exe = Path(openvsp_root) / "vspaero.exe"
    return sha256_path(exe) if exe.is_file() else None


def contract_core(config: Mapping[str, Any], record: Mapping[str, Any],
                  x12: Optional[Sequence[float]], openvsp_root: str | Path = DEFAULT_OPENVSP_ROOT) -> Dict[str, Any]:
    """The deterministic part of one P1 solver case contract (input for the contract digest).

    Deliberately excludes everything OpenVSP randomises at save time (object IDs, .vsp3 bytes)
    and everything the mesher produces non-deterministically (.vspgeom bytes / node counts).
    """
    alphas = [float(value) for value in (record.get("alpha_list_deg") or ())]
    machs = [float(value) for value in (record.get("mach_list") or ())]
    n_wake = config.get("n_wake_nodes")
    reference = expected_setup_values(float(record.get("sref_m2")), alphas, machs, n_wake)
    core: Dict[str, Any] = {
        "schema": CONTRACT_DIGEST_SCHEMA,
        "config_id": str(config.get("config_id")),
        "geometry_set": str(config.get("geometry_set")),
        "tessellation": {"Tess_U": float(config.get("tess_u")),
                         "Tess_W": float(config.get("tess_w"))},
        "num_wake_nodes": int(n_wake) if n_wake is not None else None,
        "reference": {key: value for key, value in reference.items()},
        "case_lists": {
            "alpha_list_deg": alphas,
            "mach_list": machs,
            "alpha_npts": len(alphas),
            "mach_npts": len(machs),
            "alpha_arithmetic": True,
            "mach_arithmetic": True,
        },
        "flags": {"RefFlag": 0, "NCPU": 1, "StopBeforeRun": 1},
        "task": {
            "task_id": getattr(TASK_SPEC, "task_id", None),
            "cl_required": record.get("cl_required"),
            "sref_rule": "Sref(x) = wing exposed/reference area = W01",
        },
        "solver": {
            "executable": "vspaero.exe",
            "version": openvsp_model.EXPECTED_VSPAERO_VERSION,
            "sha256": solver_sha256(openvsp_root),
            "argv": ["-omp", "1", BASENAME],
        },
        "design_space": {
            "config_sha256": sha256_path(DESIGN_SPACE_CONFIG),
            "x12_canonical": ["%.12g" % float(value) for value in (x12 or ())],
        },
        "vspaero_text_sha256": ((record.get("artifacts") or {}).get("vspaero") or {}).get("sha256"),
    }
    return core


def contract_digest(core: Mapping[str, Any]) -> str:
    payload = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mesh_observed(record: Mapping[str, Any], vspgeom: Mapping[str, Any]) -> Dict[str, Any]:
    header = record.get("vspgeom_header") or {}
    return {
        "nodes": header.get("nodes"),
        "elements": header.get("elements"),
        "bytes": vspgeom.get("bytes"),
        "sha256": vspgeom.get("sha256"),
        "reproducibility": "NOT_BYTE_REPRODUCIBLE",
        "note": "two zero-physics preparations of the identical CFG-01 contract produced 543/472 "
                "and 483/418 nodes/elements with different .vspgeom SHA256: OpenVSP assigns random "
                "object IDs at save time and its thin-geometry mesher is not byte-deterministic. "
                "Each start therefore pins the mesh it actually used; cross-start repeatability "
                "compares meshes that may differ by a few percent in panel count.",
    }


def preflight_config(config: Mapping[str, Any],
                     run_dir: str | Path,
                     geometry: Any,
                     x12: Optional[Sequence[float]] = None,
                     openvsp_root: str | Path = DEFAULT_OPENVSP_ROOT,
                     write_vsp3: bool = False) -> Dict[str, Any]:
    """Build one configuration's input set and write its preflight record (no solver)."""
    run_dir = Path(run_dir)
    config_id = str(config["config_id"])
    config_dir = run_dir / "preflight" / config_id
    config_dir.mkdir(parents=True, exist_ok=True)
    alphas = [float(value) for value in TASK_SPEC.alpha_fixed_list_deg]
    machs = [float(value) for value in config["mach_values"]]
    created = utc_now()
    started = time.perf_counter()

    record = prepare_case(
        geometry, config_dir, BASENAME,
        geometry_set=str(config["geometry_set"]),
        alphas_deg=alphas,
        mach_values=machs,
        tess_u=float(config["tess_u"]),
        tess_w=float(config["tess_w"]),
        openvsp_root=openvsp_root,
        n_wake_nodes=(int(config["n_wake_nodes"]) if config.get("n_wake_nodes") else None),
        write_vsp3=True,
        # The four pieces must already be in the target 543x472 family: the batch
        # starts on these exact files and is forbidden to switch family after the
        # fact. Roundtrip rejection sampling rebuilds from x12 until the target
        # family is reached; failure is FAIL_CLOSED before any start.
        rebuild_strategy="roundtrip",
        target_mesh_family=tuple(config.get("target_mesh_family") or TARGET_MESH_FAMILY),
        max_mesh_attempts=int(config.get("max_mesh_attempts") or MAX_MESH_ATTEMPTS),
    )
    mesh = record.get("mesh") or {}
    vsp3_model = config_dir / (BASENAME + ".vsp3")
    if not write_vsp3 and vsp3_model.is_file():
        # keep only when the caller asked for it; the file is required during compute
        vsp3_model.unlink()

    artifacts: Dict[str, Any] = {}
    for label in ("vspgeom", "vkey", "vspaero", "csf"):
        entry = record.get("artifacts", {}).get(label)
        if entry is None:
            raise RuntimeError("preflight for %s is missing the %s piece" % (config_id, label))
        path = Path(entry["path"])
        try:
            shown = str(path.relative_to(run_dir))
        except ValueError:
            shown = str(path)
        artifacts[label] = {
            "path": shown,
            "bytes": int(entry["bytes"]),
            "sha256": str(entry["sha256"]),
        }

    digest = hashlib.sha256()
    for label in ("csf", "vspaero", "vkey", "vspgeom"):
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(artifacts[label]["sha256"].encode("ascii"))
    core = contract_core(config, record, x12, openvsp_root=openvsp_root)
    contract = {
        "schema": CONTRACT_DIGEST_SCHEMA,
        "sha256": contract_digest(core),
        "note": CONTRACT_DIGEST_NOTE,
        "core": core,
    }
    mesh = mesh_observed(record, artifacts["vspgeom"])
    record_mesh = record.get("mesh") or {}
    input_set = {
        "definition": "sha256 over sorted [piece name, sha256] pairs of the four input pieces",
        "pieces": {label: artifacts[label]["sha256"]
                   for label in ("csf", "vspaero", "vkey", "vspgeom")},
        "sha256": digest.hexdigest(),
    }

    setup_path = config_dir / Path(artifacts["vspaero"]["path"]).name
    expected = expected_setup_values(record["sref_m2"], alphas, machs,
                                     config.get("n_wake_nodes"))
    readback = file_readback(setup_path, expected)
    sweep_readback = record.get("sweep_input_readback", {})
    sweep_check = record.get("sweep_readback_check", {"ok": False, "mismatches": ["missing"]})

    argv = list(record.get("solver_invocation", {}).get("argv") or
                solver_command(BASENAME, alphas))
    forbidden = forbidden_flags_in_argv(argv)
    flags_check = {
        "argv": argv,
        "forbidden_flags": list(FORBIDDEN_CLI_FLAGS),
        "forbidden_flags_present": forbidden,
        "lists_in_file_only": not forbidden,
        "ok": not forbidden,
    }
    side_effects = sorted(path.name for path in config_dir.iterdir()
                          if path.is_file() and path.suffix.lower() in (".polar", ".history"))
    checks = {
        "file_readback_ok": bool(readback["ok"]),
        "sweep_readback_ok": bool(sweep_check.get("ok")),
        "argv_no_forbidden_flags": bool(flags_check["ok"]),
        "no_polar_or_history": not side_effects,
        "ref_flag_zero": sweep_readback.get("inputs_int", {}).get("RefFlag") == 0,
        "ncpu_one": sweep_readback.get("inputs_int", {}).get("NCPU") == 1,
        "stop_before_run": sweep_readback.get("inputs_int", {}).get("StopBeforeRun") == 1,
        "mesh_family_target": str(record_mesh.get("mesh_family")) == family_label(config.get("target_mesh_family") or TARGET_MESH_FAMILY),
        "mesh_attempts_within_cap": int(record_mesh.get("mesh_attempts") or 0) <= int(config.get("max_mesh_attempts") or MAX_MESH_ATTEMPTS),
    }
    failures = sorted(key for key, ok in checks.items() if not ok)
    preflight = {
        "schema": PREFLIGHT_SCHEMA,
        "run_id": run_dir.name,
        "config_id": config_id,
        "label": config.get("label"),
        "case_keys": list(config.get("case_keys", [])),
        "created_utc": created,
        "physical_solver_starts": 0,
        "solver_started": False,
        "purpose": "governance v3 section 12.10.3 zero-physics preflight "
                   "(VSPAEROComputeGeometry + VSPAEROSweep StopBeforeRun=1 only)",
        "solver_executable": {
            "path": str(Path(openvsp_root) / "vspaero.exe"),
            "version_banner": openvsp_model.EXPECTED_VSPAERO_VERSION,
        },
        "geometry_set": str(config["geometry_set"]),
        "geometry_set_codes": openvsp_model.GEOMETRY_SET_CODES[str(config["geometry_set"])],
        "tessellation": {"Tess_U": float(config["tess_u"]), "Tess_W": float(config["tess_w"])},
        "num_wake_nodes": config.get("n_wake_nodes"),
        "alpha_list_deg": alphas,
        "mach_list": machs,
        "alpha_list_arithmetic": True,
        "mach_list_arithmetic": True,
        "sref_m2": record["sref_m2"],
        "cl_required": record.get("cl_required"),
        "internal_solver_cases_expected": int(len(alphas) * len(machs)),
        "input_pieces": artifacts,
        "input_set_sha256": input_set,
        "vspaero_file_readback": readback,
        "sweep_input_readback": sweep_readback,
        "sweep_readback_check": sweep_check,
        "mesh": {
            "target_family": family_label(config.get("target_mesh_family") or TARGET_MESH_FAMILY),
            "family": record_mesh.get("mesh_family"),
            "nodes": record_mesh.get("nodes"),
            "elements": record_mesh.get("elements"),
            "mesh_attempts": record_mesh.get("mesh_attempts"),
            "canonical_mesh_sha256": record_mesh.get("canonical_mesh_sha256"),
            "vspgeom_sha256": record_mesh.get("vspgeom_sha256"),
            "roundtrip_vsp3_sha256": record_mesh.get("roundtrip_vsp3_sha256"),
            "attempt_history": record_mesh.get("attempt_history"),
        },
        "cli_flag_check": flags_check,
        "checks": checks,
        "failures": failures,
        "all_ok": not failures,
        "side_effect_files": side_effects,
        "case_inputs_record": "case_inputs.json",
        "openvsp": {
            "root": str(openvsp_root),
            "version": record.get("openvsp_version"),
            "python_version": platform.python_version(),
        },
        "build_seconds": round(time.perf_counter() - started, 3),
        "note": "Zero physical solver starts: vspaero.exe was not executed. This record "
                "does not consume the P1 start or internal-case budget and makes no "
                "aerodynamic claim.",
    }
    out = config_dir / "preflight.json"
    out.write_text(json.dumps(preflight, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return preflight


def _family_stats(samples: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    order: List[str] = []
    counts: Dict[str, int] = {}
    second: Dict[str, int] = {}
    for index, sample in enumerate(samples, start=1):
        family = str(sample["mesh_family"])
        if family not in counts:
            order.append(family)
            counts[family] = 0
        counts[family] += 1
        if counts[family] == 2:
            second[family] = index
    target = None
    if counts:
        target = sorted(counts, key=lambda family: (-counts[family],
                                                   second.get(family, 10 ** 9),
                                                   order.index(family)))[0]
    return {"order": order, "counts": counts, "second_occurrence": second,
            "target_mesh_family": target,
            "tie_break": "family that reached two occurrences earliest"}


def select_mesh_family(config: Mapping[str, Any],
                       geometry: Any,
                       run_dir: str | Path,
                       samples: int = SELECTION_SAMPLES,
                       openvsp_root: str | Path = DEFAULT_OPENVSP_ROOT) -> Dict[str, Any]:
    """L-09: pick and freeze this configuration's target mesh family from 6 rebuilds."""
    run_dir = Path(run_dir)
    config_id = str(config["config_id"])
    selection_dir = run_dir / "preflight" / config_id / "selection"
    selection_dir.mkdir(parents=True, exist_ok=True)
    alphas = [float(value) for value in TASK_SPEC.alpha_fixed_list_deg]
    machs = [float(value) for value in config["mach_values"]]
    sample_rows: List[Dict[str, Any]] = []
    for index in range(1, int(samples) + 1):
        sample_dir = selection_dir / ("sample-%02d" % index)
        record = prepare_case(
            geometry, sample_dir, BASENAME,
            geometry_set=str(config["geometry_set"]),
            alphas_deg=alphas,
            mach_values=machs,
            tess_u=float(config["tess_u"]),
            tess_w=float(config["tess_w"]),
            openvsp_root=openvsp_root,
            n_wake_nodes=(int(config["n_wake_nodes"]) if config.get("n_wake_nodes") else None),
            write_vsp3=True,
            rebuild_strategy="direct",
            target_mesh_family=tuple(config.get("target_mesh_family") or TARGET_MESH_FAMILY),
        )
        mesh = record.get("mesh") or {}
        sample_rows.append({
            "sample": index,
            "nodes": int(mesh.get("nodes") or 0),
            "elements": int(mesh.get("elements") or 0),
            "mesh_family": str(mesh.get("mesh_family")),
            "canonical_mesh_sha256": mesh.get("canonical_mesh_sha256"),
            "vspgeom_sha256": (record.get("artifacts", {}).get("vspgeom") or {}).get("sha256"),
        })
    stats = _family_stats(sample_rows)
    target = str(stats["target_mesh_family"])
    target_row = next(row for row in sample_rows if str(row["mesh_family"]) == target)
    selection = {
        "schema": SELECTION_SCHEMA,
        "config_id": config_id,
        "sample_count": len(sample_rows),
        "samples": sample_rows,
        "frequency": dict(stats["counts"]),
        "order_of_first_appearance": list(stats["order"]),
        "second_occurrence_index": dict(stats["second_occurrence"]),
        "target_mesh_family": target,
        "target_nodes": target_row["nodes"],
        "target_elements": target_row["elements"],
        "target_canonical_mesh_sha256_examples": sorted({str(row["canonical_mesh_sha256"])
                                                          for row in sample_rows
                                                          if str(row["mesh_family"]) == target}),
        "selection_rule": SELECTION_RULE,
        "selected_at_utc": utc_now(),
        "physical_solver_starts": 0,
        "note": "selected by this batch's own zero-physics rebuild sampling; NOT a claim "
                "about historical P1/P0 mesh families",
    }
    path = selection_dir.parent / "selection.json"
    path.write_text(json.dumps(selection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    selection["path"] = str(path.relative_to(run_dir))
    selection["sha256"] = sha256_path(path)
    return selection


def run_preflight(run_dir: str | Path,
                  openvsp_root: str | Path = DEFAULT_OPENVSP_ROOT,
                  configs: Optional[Sequence[Mapping[str, Any]]] = None,
                  write_vsp3: bool = True) -> Dict[str, Any]:
    """Build every preflight configuration and write the index (no solver start)."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    geometry, _space, x12, _names = baseline_geometry()
    selected = list(configs) if configs is not None else list(P1_CONFIGS)
    records: List[Dict[str, Any]] = []
    for config in selected:
        config_id = str(config["config_id"])
        existing_path = run_dir / "preflight" / config_id / "preflight.json"
        existing = None
        if existing_path.is_file():
            try:
                candidate = json.loads(existing_path.read_text(encoding="utf-8"))
            except Exception:
                candidate = None
            if (candidate and candidate.get("all_ok")
                    and all((run_dir / "preflight" / config_id / Path(piece["path"]).name).is_file()
                            for piece in (candidate.get("input_pieces") or {}).values())):
                existing = candidate
        # L-09: the target family is selected by THIS batch's six zero-physics rebuilds,
        # never inherited from a historical claim; the selection is written to
        # preflight/<config>/selection.json and bound into the preflight record.
        selection = select_mesh_family(config, geometry, run_dir,
                                       openvsp_root=openvsp_root)
        effective = dict(config)
        effective["target_mesh_family"] = [int(part) for part in
                                          str(selection["target_mesh_family"]).split("x")]
        if existing is not None:
            # Resumable preflight: OpenVSP python is a process-wide singleton and a
            # second prepare_case in one process can inherit a loaded model; the
            # operator therefore builds one config per process and later runs need
            # only to aggregate the clean records.  A record whose mesh family differs
            # from the freshly selected target is rebuilt instead of reused.
            existing_mesh = existing.get("mesh") or {}
            if str(existing_mesh.get("mesh_family")) == family_label(effective["target_mesh_family"]):
                existing["mesh_selection"] = {
                    "path": selection["path"], "sha256": selection["sha256"],
                    "target_mesh_family": selection["target_mesh_family"],
                    "sample_count": selection["sample_count"],
                }
                existing_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False)
                                         + "\n", encoding="utf-8")
                records.append(existing)
                continue
        record = preflight_config(effective, run_dir, geometry, x12=x12,
                                  openvsp_root=openvsp_root,
                                  write_vsp3=write_vsp3)
        record["mesh_selection"] = {
            "path": selection["path"], "sha256": selection["sha256"],
            "target_mesh_family": selection["target_mesh_family"],
            "sample_count": selection["sample_count"],
        }
        (run_dir / "preflight" / config_id / "preflight.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        records.append(record)
    index = {
        "schema": PREFLIGHT_INDEX_SCHEMA,
        "run_id": run_dir.name,
        "created_utc": utc_now(),
        "physical_solver_starts": 0,
        "solver_started": False,
        "config_count": len(records),
        "configs": [
            {
                "config_id": record["config_id"],
                "case_keys": record["case_keys"],
                "all_ok": record["all_ok"],
                "failures": record["failures"],
                "input_set_sha256": record["input_set_sha256"]["sha256"],
                "input_pieces": {label: entry["sha256"]
                                 for label, entry in record["input_pieces"].items()},
                "solver_invocation_argv": record["cli_flag_check"]["argv"],
                "forbidden_flags_present": record["cli_flag_check"]["forbidden_flags_present"],
                "internal_solver_cases_expected": record["internal_solver_cases_expected"],
                "mesh": record.get("mesh"),
                "mesh_selection": record.get("mesh_selection"),
                "record_path": "preflight/%s/preflight.json" % record["config_id"],
                "record_sha256": sha256_path(run_dir / "preflight" / record["config_id"]
                                             / "preflight.json"),
            }
            for record in records
        ],
        "all_ok": all(record["all_ok"] for record in records),
        "note": "Zero-physics preflight only; see each preflight.json for the line-by-line "
                "readback evidence. No .polar/.history must exist in these directories.",
    }
    (run_dir / "preflight" / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="P1 zero-physics preflight for the eight unique solver configurations")
    default_run_dir = Path(__file__).resolve().parent / "runs" / DEFAULT_P1_RUN_ID
    parser.add_argument("--run-dir", default=str(default_run_dir))
    parser.add_argument("--openvsp-root", default=DEFAULT_OPENVSP_ROOT)
    parser.add_argument("--config-ids", nargs="*", default=None,
                        help="optional subset of config ids to rebuild")
    # VSPAEROComputeGeometry names the .vspgeom/.vkey after the CURRENT model file, so the
    # .vsp3 must be written before the geometry analysis; keeping it is therefore the
    # default and --no-vsp3 is only for throwaway probes.
    parser.add_argument("--no-vsp3", action="store_true",
                        help="do not keep the .vsp3 model (preflight still writes it during compute)")
    args = parser.parse_args(argv)
    configs = None
    if args.config_ids:
        wanted = set(args.config_ids)
        configs = [config for config in P1_CONFIGS if config["config_id"] in wanted]
        missing = sorted(wanted - {config["config_id"] for config in configs})
        if missing:
            raise SystemExit("unknown config ids: %s" % missing)
    index = run_preflight(args.run_dir, openvsp_root=args.openvsp_root,
                          configs=configs, write_vsp3=not args.no_vsp3)
    print(json.dumps({
        "run_dir": str(Path(args.run_dir).resolve()),
        "config_count": index["config_count"],
        "all_ok": index["all_ok"],
        "physical_solver_starts": index["physical_solver_starts"],
        "configs": [{"config_id": entry["config_id"], "all_ok": entry["all_ok"],
                     "input_set_sha256": entry["input_set_sha256"],
                     "internal_solver_cases_expected": entry["internal_solver_cases_expected"]}
                    for entry in index["configs"]],
    }, indent=2))
    return 0 if index["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
