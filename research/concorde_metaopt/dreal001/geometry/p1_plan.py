"""D-REAL-001 P1 solver plan generator (zero physical solver starts).

Reads the eight zero-physics preflights written by p1_preflight.py, expands the 25-start
case matrix pre-registered in P1_PREREGISTRATION_v1.md (v1.3), estimates the disk budget,
and writes runs/<P1 run id>/plan.json with status PENDING_APPROVAL.

plan.json is the second link of the governance v3 SHA chain
(prereg sha256 -> plan.json -> approval.json). It is NEVER a permission to launch:
approved_by stays null, window_token stays null, solver_started is false and
physical_solver_starts is 0 until the Lead writes approval.json for a dated window.

CLI:

    <python> -m research.concorde_metaopt.dreal001.geometry.p1_plan \
        --run-dir research/concorde_metaopt/dreal001/geometry/runs/DREAL001-P1-20261110-01
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from research.concorde_metaopt.aircraft.design_space import load_design_space

from . import design_identity
from .mesh_identity import MAX_MESH_ATTEMPTS, TARGET_MESH_FAMILY, family_label
from .p1_preflight import DESIGN_SPACE_CONFIG, P1_CONFIGS, PREFLIGHT_INDEX_SCHEMA
from .task_spec import TASK_SPEC

PLAN_SCHEMA = "dreal001.solver_plan.v1"
DEFAULT_P1_RUN_ID = "DREAL001-P1-20261110-01"
PREREG_PATH = Path(__file__).resolve().parent / "P1R_PREREGISTRATION_v1.md"
REPO_ROOT = Path(__file__).resolve().parents[4]
TASK_SPEC_PATH = REPO_ROOT / "configs" / "dreal001_task_fixed_cruise_REAL.json"
FREEZE_ARTIFACT = Path(__file__).resolve().parent / "design_space_freeze.json"
FREEZE_DECISION_PATH = "docs/planning/dreal001_lead_decisions_20261110.md"
FREEZE_DECISION_COMMIT = "3624db7"
FREEZE_DECISION_ITEMS = ["L-01", "L-02", "L-03"]
SOLVER_PATH = Path(r"D:\OpenVSP-3.55.0\OpenVSP-3.55.0-win64\vspaero.exe")
SOLVER_SHA256 = "db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad"
SOLVER_VERSION = "VSPAERO v7.2.2 (compiled 2026-10-12)"

EXPECTED_STARTS = 25
MAX_STARTS = 26
EXPECTED_INTERNAL_CASES = 189
MAX_INTERNAL_CASES = 196
MAX_REFINE_STARTS = 1
MAX_REFINE_ATTEMPTS_PER_DESIGN = 2
ALPHA_LIST_DEG = (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)
TIMEOUT_SECONDS = 900
# A5 / Lead m04629 (zero-physics safety revision, 2026-11-10): P1-04c (thick 48x97) measured
# 889.697 s in the pre-incident batch, i.e. only 1.2 % below the 900 s default. A slightly
# slower machine would turn the most expensive case into an S1 timeout that discards the ten
# starts before it. Its per-case timeout is therefore 1200 s; every other case keeps the 900 s
# default, and budget caps (25/26 starts, 189/196 internal), case order and mesh are unchanged.
TIMEOUT_OVERRIDES = {"P1-04c": 1200}
TIMEOUT_OVERRIDE_RATIONALE = (
    "A5/Lead m04629: P1-04c (thick 48x97) measured 889.697 s against the 900 s default (1.2 % "
    "margin); its per-case timeout is raised to 1200 s. All other cases keep 900 s. No change to "
    "the scientific endpoint, budget caps 25/26 starts and 189/196 internal, case order or mesh.")


def timeout_for_case(case_id):
    """Per-case timeout: 900 s default, 1200 s for the P1-04c exception only."""
    return int(TIMEOUT_OVERRIDES.get(str(case_id), TIMEOUT_SECONDS))

OMP_THREADS = 1
CONCURRENCY = 1
FREE_DISK_FLOOR_GB = 50
WINDOW_REQUESTED = {
    "timezone": "Asia/Shanghai",
    "requested_start_local": "2026-11-10T23:50:00+08:00",
    "requested_end_local": "2026-11-11T03:50:00+08:00",
    "note": "request only (Lead m04713, superseding the 23:20-00:40 request); the window actually "
            "granted is the one in approval.json and the approval window governs. Four hours is the "
            "worst-case envelope (about 40-70 min expected, see prereg section 9); the governance S6 "
            "6 h wall-clock limit is unchanged. P0R (1 start) must be reviewed by A5 before P1R starts "
            "(L-12).",
}

def repo_relative(path: Path) -> str:
    """Return a repository-relative POSIX path (plan/policy documents never carry drive letters)."""
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


#: A5 B13 / Lead m03961 ruling: the 14 one-at-a-time probes are rebuilt to their OWN
#: selected mesh family (Lead L-09), so a probe is only comparable to the baseline when
#: its selected family equals the baseline (CFG-01) family.  The same/cross-family probe
#: lists are NOT hardcoded (A5 B24): per-probe family selection is sampling-dependent, so
#: they are derived from the measured feasibility artifact below and echoed in
#: probe_mesh_feasibility.per_probe_families.
BASELINE_MESH_FAMILY = (543, 472)

#: Base matrix (pre-registered v1.3 section 1). P1-07 is expanded separately.
BASE_CASES: List[Dict[str, Any]] = [
    {"case_id": "P1-00a", "config_id": "CFG-01-thin-12x25", "purpose": "repeatability R1 (baseline thin 12x25)"},
    {"case_id": "P1-00b", "config_id": "CFG-01-thin-12x25", "purpose": "repeatability R2 (baseline thin 12x25)"},
    {"case_id": "P1-00c", "config_id": "CFG-01-thin-12x25", "purpose": "repeatability R3 (baseline thin 12x25)"},
    {"case_id": "P1-02a", "config_id": "CFG-01-thin-12x25", "purpose": "panel density low, 12x25 (independent launch)"},
    {"case_id": "P1-02c", "config_id": "CFG-02-thin-24x49", "purpose": "panel density middle, 24x49"},
    {"case_id": "P1-02b", "config_id": "CFG-03-thin-48x97", "purpose": "panel density high, 48x97"},
    {"case_id": "P1-03", "config_id": "CFG-04-thin-12x25-wake128", "purpose": "wake node sensitivity, NumWakeNodes 128"},
    {"case_id": "P1-04", "config_id": "CFG-05-thick-12x25", "purpose": "thick NEGATIVE CONTROL only (never production)"},
    {"case_id": "P1-04b", "config_id": "CFG-07-thick-24x49", "purpose": "thick NEGATIVE CONTROL at middle panel density"},
    {"case_id": "P1-04c", "config_id": "CFG-08-thick-48x97", "purpose": "thick NEGATIVE CONTROL at fine panel density"},
    {"case_id": "P1-05", "config_id": "CFG-06-thin-12x25-mach-sweep", "purpose": "Mach trend 1.8/2.0/2.2 in one equal-spaced sweep"},
]

P1_07_VARIABLES = ("W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08", "W09",
                   "W10", "V01", "V02")
P1_07_WING_FRACTION = 0.10   # +10 % of the declared range
P1_07_TAIL_FRACTION = 0.10   # +/-10 % of the declared range, both signs

#: Disk estimate basis, disclosed in the plan. ENV_SMOKE produced a 28,383 B .polar for 32
#: internal cases (about 900 B per internal case); the per-case figure is rounded up.
POLAR_BYTES_PER_INTERNAL = 1200
HISTORY_BYTES_PER_INTERNAL = 1200
LOG_AND_RECORD_BYTES = 20000


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_preflights(run_dir: Path) -> Dict[str, Any]:
    """Load the preflight index plus every per-config preflight record."""
    index_path = run_dir / "preflight" / "index.json"
    if not index_path.is_file():
        raise SystemExit("missing preflight index: run p1_preflight.py first (%s)" % index_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("schema") != PREFLIGHT_INDEX_SCHEMA:
        raise SystemExit("unexpected preflight index schema: %r" % index.get("schema"))
    records: Dict[str, Dict[str, Any]] = {}
    for entry in index.get("configs", []):
        config_id = str(entry["config_id"])
        path = run_dir / "preflight" / config_id / "preflight.json"
        records[config_id] = json.loads(path.read_text(encoding="utf-8"))
    return {
        "index": index,
        "index_path": index_path,
        "index_sha256": sha256_file(index_path),
        "records": records,
    }


def probe_designs(space: Any) -> List[Dict[str, Any]]:
    """One-at-a-time probes: W01-W10 at +10 % of range, V01/V02 at +/-10 % of range."""
    by_id = {variable.id: variable for variable in space.variables}
    for variable_id in P1_07_VARIABLES:
        if variable_id not in by_id:
            raise SystemExit("design space is missing %s" % variable_id)
    baseline = dict(space.baseline_dict())
    probes: List[Dict[str, Any]] = []
    for variable_id in P1_07_VARIABLES:
        variable = by_id[variable_id]
        span = float(variable.upper) - float(variable.lower)
        base = float(baseline[variable.name])
        if variable_id.startswith("W"):
            directions = (("plus", base + P1_07_WING_FRACTION * span),)
        else:
            directions = (("plus", base + P1_07_TAIL_FRACTION * span),
                          ("minus", base - P1_07_TAIL_FRACTION * span))
        for sign, raw in directions:
            value = min(max(raw, float(variable.lower)), float(variable.upper))
            design = dict(baseline)
            design[variable.name] = value
            cross_problems = list(space.check_cross_constraints(design))
            x12 = [float(design[name]) for name in space.names]
            probes.append({
                "case_id": "P1-07-%s-%s" % (variable_id, sign),
                "x12": x12,
                "design_hash": design_identity.design_hash(x12),
                "variable_id": variable_id,
                "variable_name": variable.name,
                "sign": sign,
                "unit": variable.unit,
                "baseline_value": base,
                "probe_value": value,
                "clipped": bool(abs(value - raw) > 1.0e-12),
                "design": design,
                "cross_constraints_ok": not cross_problems,
                "cross_constraint_problems": list(cross_problems),
            })
    return probes


def case_disk_estimate(record: Mapping[str, Any], internal_cases: int) -> int:
    pieces = record["input_pieces"]
    fixed = sum(int(piece["bytes"]) for piece in pieces.values())
    if record.get("vsp3_model"):
        fixed += int(record["vsp3_model"]["bytes"])
    aux = internal_cases * (POLAR_BYTES_PER_INTERNAL + HISTORY_BYTES_PER_INTERNAL) \
        + LOG_AND_RECORD_BYTES
    return int(fixed + aux)


def mesh_identity_block(mesh: Mapping[str, Any], fallback_family: Optional[Sequence[int]] = None,
                        per_design: bool = False) -> Dict[str, Any]:
    """Describe the canonical mesh rule for a case (falls back for synthetic fixtures)."""
    family = mesh.get("family") if isinstance(mesh, Mapping) else None
    if family is None:
        family = family_label(fallback_family or TARGET_MESH_FAMILY)
    block: Dict[str, Any] = {
        "target_mesh_family": family,
        "expected_nodes": mesh.get("nodes") if isinstance(mesh, Mapping) else None,
        "expected_elements": mesh.get("elements") if isinstance(mesh, Mapping) else None,
        "expected_canonical_mesh_sha256": (mesh.get("canonical_mesh_sha256")
                                           if isinstance(mesh, Mapping) else None),
        "max_mesh_attempts": MAX_MESH_ATTEMPTS,
        "fail_closed": True,
    }
    if per_design:
        block["rebuild_per_design"] = True
        block["note"] = ("probe designs are rebuilt per start (no template .vspgeom copy); the "
                         "canonical topology hash of this design's mesh is recorded per start")
    else:
        block["note"] = ("P1R canonical identity: rebuild until the target family is obtained; "
                         "the canonical topology hash is reproducible where vspgeom bytes are not")
    return block


def probe_family_map(feasibility: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """A5 B13/B17: per-probe SELECTED family, taken from the measured feasibility record.

    The comparability label must never be a hardcoded list: probe families come from each
    probe's own rebuild samples and can differ from the baseline family (and between
    sampling sessions), so the map is read from the measured artifact.
    """
    return {str(item.get("case_id")): str(item.get("target_mesh_family"))
            for item in ((feasibility or {}).get("probes") or [])
            if item.get("ok") and item.get("target_mesh_family")}


def build_case_matrix(preflights: Mapping[str, Any], probes: Sequence[Mapping[str, Any]],
                      prereg_sha256: str, space: Any,
                      feasibility: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    records = preflights["records"]
    probe_families = probe_family_map(feasibility)
    baseline_family = family_label(BASELINE_MESH_FAMILY)
    cases: List[Dict[str, Any]] = []
    for spec in BASE_CASES:
        record = records[spec["config_id"]]
        cases.append({
            "case_id": spec["case_id"],
            "purpose": spec["purpose"],
            "config_id": spec["config_id"],
            "starts": 1,
            "expected_internal_cases": int(record["internal_solver_cases_expected"]),
            "internal_case_breakdown": {
                "mach_list": list(record["mach_list"]),
                "alpha_list_deg": list(record["alpha_list_deg"]),
                "beta_list_deg": [0.0],
                "counts": {
                    "mach": len(record["mach_list"]),
                    "alpha": len(record["alpha_list_deg"]),
                    "beta": 1,
                },
            },
            "preflight_config_id": spec["config_id"],
            "input_set_sha256": record["input_set_sha256"]["sha256"],
            "input_pieces": {label: entry["sha256"]
                             for label, entry in record["input_pieces"].items()},
            "mesh_identity": mesh_identity_block(record.get("mesh") or {},
                                                  spec.get("target_mesh_family")),
            "solver_argv": list(record["cli_flag_check"]["argv"]),
            "timeout_seconds": timeout_for_case(spec["case_id"]),
            "omp_threads": OMP_THREADS,
            "design": "baseline (12D baseline)",
            "x12": [float(value) for value in space.baseline_vector()],
            "design_hash": design_identity.design_hash(space.baseline_vector()),
            "design_hash_definition": design_identity.DESIGN_HASH_DEFINITION,
            "preregistration_sha256": prereg_sha256,
            "expected_disk_bytes": case_disk_estimate(record, int(record["internal_solver_cases_expected"])),
        })
    config = records["CFG-01-thin-12x25"]
    feasible = {item["case_id"]: item for item in (feasibility or {}).get("probes", [])}
    for probe in probes:
        probe_feas = feasible.get(probe["case_id"])
        if not probe_feas or not probe_feas.get("ok"):
            raise SystemExit("probe %s has no clean zero-physics family feasibility record"
                             % probe["case_id"])
        probe_mesh = {
            "family": probe_feas["target_mesh_family"],
            "target_family": probe_feas["target_mesh_family"],
            "nodes": probe_feas["nodes"], "elements": probe_feas["elements"],
            "canonical_mesh_sha256": probe_feas["canonical_mesh_sha256"],
        }
        cases.append({
            "case_id": probe["case_id"],
            "purpose": "one-at-a-time %s probe (%s %s of declared range)" % (
                probe["variable_id"], probe["sign"], probe["unit"]),
            "config_id": "CFG-01-thin-12x25",
            "starts": 1,
            "expected_internal_cases": int(config["internal_solver_cases_expected"]),
            "internal_case_breakdown": {
                "mach_list": list(config["mach_list"]),
                "alpha_list_deg": list(config["alpha_list_deg"]),
                "beta_list_deg": [0.0],
                "counts": {"mach": len(config["mach_list"]),
                           "alpha": len(config["alpha_list_deg"]), "beta": 1},
            },
            "preflight_config_id": "CFG-01-thin-12x25",
            "input_set_sha256": None,
            "input_set_sha256_note": "reuse of the CFG-01 solver configuration; the probe-specific "
                                     ".vspgeom SHA is recorded when this design's inputs are "
                                     "prepared (design changes, solver configuration does not)",
            "mesh_identity": mesh_identity_block(probe_mesh, per_design=True),
            "solver_argv": list(config["cli_flag_check"]["argv"]),
            "timeout_seconds": timeout_for_case(probe["case_id"]),
            "omp_threads": OMP_THREADS,
            "design": probe["design"],
            "x12": list(probe["x12"]),
            "design_hash": probe["design_hash"],
            "design_hash_definition": design_identity.DESIGN_HASH_DEFINITION,
            "design_variable_id": probe["variable_id"],
            "design_probe_sign": probe["sign"],
            "design_probe_value": probe["probe_value"],
            "design_probe_baseline": probe["baseline_value"],
            "design_probe_clipped": probe["clipped"],
            "design_cross_constraints_ok": probe["cross_constraints_ok"],
            "design_cross_constraint_problems": probe["cross_constraint_problems"],
            "sensitivity_comparability": (
                "SAME_FAMILY_COMPARABLE"
                if probe_families.get(str(probe["case_id"])) == baseline_family
                else "CROSS_FAMILY_NOT_COMPARABLE"
            ),
            "sensitivity_probe_family": probe_families.get(str(probe["case_id"])),
            "sensitivity_scope_note": (
                "A5 B13 / Lead m03961: only probes whose selected mesh family equals the "
                "baseline CFG-01 family may enter the intra-family sensitivity ranking; "
                "cross-family probes are still executed and archived but are excluded from "
                "the 12D_ACTIVE / variable-sensitivity conclusion"
            ),
            "preregistration_sha256": prereg_sha256,
            "expected_disk_bytes": case_disk_estimate(config, int(config["internal_solver_cases_expected"])),
        })
    return cases


def task_spec_canonical_sha256() -> str:
    """A5 B6 / A3: canonical TaskSpec digest (distinct from the raw file bytes)."""
    payload = json.dumps(TASK_SPEC.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def primary_solver_config_hash() -> str:
    """A5 B16: solver-config identity of the primary production configuration.

    Imported lazily so that plan generation does not require an OpenVSP session.
    """
    from .evaluator import solver_config_hash as _solver_config_hash

    return _solver_config_hash("thin", 12.0, 25.0, float(TIMEOUT_SECONDS), OMP_THREADS)


def probe_feasibility(run_dir: Path, openvsp_root: Optional[Any] = None) -> Dict[str, Any]:
    """A5 B7: zero-physics selected-family rebuild check for all 14 P1-07 probe designs.

    Each probe is rebuilt from its own x12 until the CFG-01 selected family is hit (<=12
    attempts). No solver is started; the per-probe attempt history is written to
    preflight/probes/feasibility.json and bound into plan.json. If any probe cannot reach
    the family the plan must not be written.
    """
    from . import openvsp_model

    run_dir = Path(run_dir)
    space = load_design_space(str(DESIGN_SPACE_CONFIG))
    probes = probe_designs(space)
    preflights = load_preflights(run_dir)
    config_id = "CFG-01-thin-12x25"
    selection_path = run_dir / "preflight" / config_id / "selection.json"
    if selection_path.is_file():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        parts = str(selection["target_mesh_family"]).lower().split("x")
        target = (int(parts[0]), int(parts[1]))
    else:
        target = tuple(TARGET_MESH_FAMILY)
    record = preflights["records"].get(config_id) or {}
    out_dir = run_dir / "preflight" / "probes"
    out_dir.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []
    all_ok = True
    for probe in probes:
        case_dir = out_dir / str(probe["case_id"])
        case_dir.mkdir(parents=True, exist_ok=True)
        x12 = [float(probe["design"][name]) for name in space.names]
        # A probe is a DIFFERENT design: its own topology families are not the baseline's
        # (e.g. 544x473 / 481x416 appear for some perturbations). Applying the per-configuration
        # baseline family to a probe is therefore infeasible by construction. The same L-09
        # selection rule is applied per probe design over its own rebuild samples, and the
        # resulting family is frozen per probe in plan.json.
        samples: List[Dict[str, Any]] = []
        error = None
        for attempt in range(1, MAX_MESH_ATTEMPTS + 1):
            geometry, _space = openvsp_model._geometry_from_design_vector(x12)
            try:
                built = openvsp_model.prepare_case(
                    geometry, case_dir / ("sample-%02d" % attempt), "concorde_baseline",
                    geometry_set=str(record.get("geometry_set") or "thin"),
                    alphas_deg=[float(value) for value in (record.get("alpha_list_deg")
                                                           or ALPHA_LIST_DEG)],
                    tess_u=float((record.get("tessellation") or {}).get("tess_u", 12)),
                    tess_w=float((record.get("tessellation") or {}).get("tess_w", 25)),
                    n_wake_nodes=int(record.get("num_wake_nodes") or 8),
                    write_vsp3=True,
                    mach_values=[float(value) for value in (record.get("mach_list") or [2.02])],
                    rebuild_strategy="direct",
                    max_mesh_attempts=1,
                )
            except Exception as exc:  # noqa: BLE001 - any build failure is infeasible
                error = "%s: %s" % (type(exc).__name__, exc)
                break
            mesh = built.get("mesh") or {}
            sample = {"attempt": attempt, "mesh_family": mesh.get("mesh_family"),
                      "nodes": mesh.get("nodes"), "elements": mesh.get("elements"),
                      "canonical_mesh_sha256": mesh.get("canonical_mesh_sha256"),
                      "vspgeom_sha256": mesh.get("vspgeom_sha256")}
            samples.append(sample)
            seen = [item["mesh_family"] for item in samples]
            if seen.count(sample["mesh_family"]) >= 2:
                break
        if error is not None or not samples:
            results.append({"case_id": probe["case_id"], "variable_id": probe["variable_id"],
                            "design_hash": probe["design_hash"], "ok": False,
                            "error": error or "no rebuild sample"})
            all_ok = False
            continue
        counts: Dict[str, int] = {}
        first_second: Dict[str, int] = {}
        for sample in samples:
            family = str(sample["mesh_family"])
            counts[family] = counts.get(family, 0) + 1
            if counts[family] == 2 and family not in first_second:
                first_second[family] = sample["attempt"]
        target_family = sorted(counts, key=lambda name: (-counts[name],
                                                         first_second.get(name, 10 ** 6),
                                                         name))[0]
        chosen = next(sample for sample in samples if sample["mesh_family"] == target_family)
        results.append({
            "case_id": probe["case_id"], "variable_id": probe["variable_id"],
            "design_hash": probe["design_hash"], "ok": True,
            "selection_rule": "per-design L-09: modal family over own rebuild samples, tie by "
                              "earliest second occurrence",
            "sample_count": len(samples),
            "frequency": counts,
            "target_mesh_family": target_family,
            "nodes": chosen["nodes"], "elements": chosen["elements"],
            "canonical_mesh_sha256": chosen["canonical_mesh_sha256"],
            "vspgeom_sha256": chosen["vspgeom_sha256"],
            "attempts_to_first_target": next(sample["attempt"] for sample in samples
                                            if sample["mesh_family"] == target_family),
            "samples": samples,
        })
    per_probe_families = {item["case_id"]: item.get("target_mesh_family")
                          for item in results if item.get("ok")}
    payload = {
        "schema": "dreal001.p1_probe_feasibility.v1",
        "config_id": config_id,
        "baseline_family_only": family_label(target),
        "target_mesh_family": None,
        "target_mesh_family_note": "A5 B17/B13: there is no single probe family. Each probe is a "
                                   "different design and is rebuilt from its own x12 until its OWN "
                                   "modal family appears (L-09 rule); baseline_family_only is only "
                                   "the CFG-01 comparability reference. Per-probe families are in "
                                   "per_probe_families and in every probe record below.",
        "per_probe_families": per_probe_families,
        "max_mesh_attempts": MAX_MESH_ATTEMPTS,
        "probe_count": len(results),
        "all_ok": all_ok,
        "physical_solver_starts": 0,
        "created_utc": utc_now(),
        "note": "zero-physics: VSPAEROComputeGeometry only; no solver start, no .polar, no objective",
        "probes": results,
    }
    path = out_dir / "feasibility.json"
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    payload["_written"] = {"path": str(path), "bytes": len(encoded),
                           "sha256": hashlib.sha256(encoded).hexdigest()}
    return payload


def build_plan(run_dir: Path, prereg_path: Optional[Path] = None,
               batch_id: Optional[str] = None,
               prereg_version: str = "v1.3") -> Dict[str, Any]:
    """Assemble the plan dictionary and write plan.json (no solver start)."""
    run_dir = Path(run_dir)
    prereg = Path(prereg_path) if prereg_path is not None else PREREG_PATH
    run_dir.mkdir(parents=True, exist_ok=True)
    if not TASK_SPEC_PATH.is_file():
        raise SystemExit("missing REAL task spec: %s (run p0_finalize/task_spec writer first)"
                         % TASK_SPEC_PATH)
    preflights = load_preflights(run_dir)
    records = preflights["records"]
    if not all(record.get("all_ok") for record in records.values()):
        raise SystemExit("preflight is not clean; fix it before writing plan.json")

    space = load_design_space(str(DESIGN_SPACE_CONFIG))
    probes = probe_designs(space)
    feasibility_path = run_dir / "preflight" / "probes" / "feasibility.json"
    if not feasibility_path.is_file():
        raise SystemExit("missing probe feasibility preflight: %s (A5 B7 requires the 14 probe "
                         "designs to reach the selected family before the plan is written; run "
                         "p1_plan.py --probe-feasibility first)" % feasibility_path)
    feasibility = json.loads(feasibility_path.read_text(encoding="utf-8"))
    # A5 B24: the E5 same/cross-family lists are computed from the MEASURED feasibility
    # artifact, never hardcoded, and are reported with their own counts in the rule text.
    baseline_family = family_label(BASELINE_MESH_FAMILY)
    feasibility_probes = feasibility.get("probes") or []
    same_family_probes = [item["case_id"] for item in feasibility_probes
                          if item.get("target_mesh_family") == baseline_family]
    cross_family_probes = [item["case_id"] for item in feasibility_probes
                           if item.get("target_mesh_family") != baseline_family]
    if not feasibility.get("all_ok"):
        raise SystemExit("probe feasibility preflight is not clean; refusing to write plan.json")
    if int(feasibility.get("probe_count") or 0) != len(probes):
        raise SystemExit("probe feasibility covers %s probes, expected %d"
                         % (feasibility.get("probe_count"), len(probes)))
    prereg_sha256 = sha256_file(prereg)
    cases = build_case_matrix(preflights, probes, prereg_sha256, space, feasibility)

    total_starts = sum(int(case["starts"]) for case in cases)
    total_internal = sum(int(case["expected_internal_cases"]) for case in cases)
    if total_starts != EXPECTED_STARTS:
        raise SystemExit("case matrix has %d starts, expected %d" % (total_starts, EXPECTED_STARTS))
    if total_internal != EXPECTED_INTERNAL_CASES:
        raise SystemExit("case matrix has %d internal cases, expected %d"
                         % (total_internal, EXPECTED_INTERNAL_CASES))
    if len(cases) != EXPECTED_STARTS:
        raise SystemExit("case matrix has %d rows, expected %d" % (len(cases), EXPECTED_STARTS))

    matrix_payload = json.dumps(
        [{"case_id": case["case_id"], "design_hash": case.get("design_hash"),
          "x12": case.get("x12"), "starts": case["starts"],
          "expected_internal_cases": case["expected_internal_cases"]} for case in cases],
        sort_keys=True, separators=(",", ":"))
    case_matrix_digest = hashlib.sha256(matrix_payload.encode("utf-8")).hexdigest()

    expected_disk = sum(int(case["expected_disk_bytes"]) for case in cases)
    refine_case_bytes = case_disk_estimate(records["CFG-01-thin-12x25"], 7)
    max_disk = expected_disk + MAX_REFINE_STARTS * refine_case_bytes
    max_disk = int(max_disk * 1.10)

    free_bytes = shutil.disk_usage(str(run_dir)).free if hasattr(shutil, "disk_usage") else 0
    plan: Dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "run_id": run_dir.name,
        "batch_id": batch_id or run_dir.name,
        "created_utc": utc_now(),
        "status": "PENDING_APPROVAL",
        "purpose": "P1 numerical validation of the VSPAERO 7.2.2 solver loop for the frozen 12D "
                   "design space: repeatability, panel-density chain, wake sensitivity, thick "
                   "negative control, Mach trend, and 12 one-at-a-time variable probes.",
        "layer_claim": {
            "supports": "SOLVER_LOOP_VERIFIED and VSPAERO-model-internal consistency only",
            "does_not_support": ["INTERNAL_AERO_OPTIMIZATION_GAIN", "EXTERNAL_PHYSICS_SUPPORTED",
                                 "any fuel_burn_kg or mission-level drag claim"],
            "fuel_burn_kg": None,
        },
        "preregistration": {
            "path": repo_relative(prereg),
            "sha256": prereg_sha256,
            "version": prereg_version,
            "note": "plan_sha256 is computed over the raw bytes of this file and reported to the "
                    "Lead, who writes approval.json; approval.json then carries plan_sha256.",
        },
        "frozen_design_space": {
            "config_path": repo_relative(DESIGN_SPACE_CONFIG),
            "config_sha256": sha256_file(DESIGN_SPACE_CONFIG),
            "frozen": bool(space.frozen),
            "bounds_status": space.bounds_status,
            "freeze_note": space.freeze_note,
            "freeze_decision": {
                "path": FREEZE_DECISION_PATH,
                "commit": FREEZE_DECISION_COMMIT,
                "items": ["L-01", "L-02", "L-03"],
            },
            "freeze_artifact": {
                "path": repo_relative(FREEZE_ARTIFACT),
                "sha256": sha256_file(FREEZE_ARTIFACT) if FREEZE_ARTIFACT.is_file() else None,
            },
            "baseline_design_hash": design_identity.design_hash(space.baseline_vector()),
            "design_hash_definition": design_identity.DESIGN_HASH_DEFINITION,
            "note": "the 12 geometry bounds are frozen by Lead decision L-03 (commit 3624db7); "
                    "freezing the geometry contract does not validate the aerodynamics "
                    "(VSPAERO internal coefficients remain VSPAERO_INTERNAL_ONLY), and the "
                    "wing AC 16.821978259514246 is still not the aircraft CG.",
        },
        "task_spec": {
            "path": repo_relative(TASK_SPEC_PATH),
            "raw_sha256": sha256_file(TASK_SPEC_PATH),
            "canonical_sha256": task_spec_canonical_sha256(),
            "hash_scope": {
                "raw_sha256": "sha256 of the bytes of configs/dreal001_task_fixed_cruise_REAL.json "
                              "(repo-relative path); this is the identity approval.json binds to",
                "canonical_sha256": "sha256 of json.dumps(TASK_SPEC.to_dict(), sort_keys=True, "
                                    "separators=(',', ':')) with no trailing newline",
                "comparability": "raw and canonical digests cover different byte strings and must "
                                 "never be compared with each other",
            },
            "note": "reference injection Sref(x)=wing.area_m2, Cref=18.489893, Bref=25.604638, "
                    "X_cg=16.821978259514246 (WING_AC reference, not the 28.287395109126685 geometric CG), "
                    "RefFlag=0, Mach=2.02, Vinf=596.0373972278921, rho=0.1153178340089936, "
                    "ReCref=89397005.8767656, L_ref=1,333,704.4 N.",
        },
        "solver": {
            "path": str(SOLVER_PATH),
            "sha256": SOLVER_SHA256,
            "version": SOLVER_VERSION,
            "command_template": "vspaero.exe -omp 1 <case basename>",
            "list_flags_allowed": False,
        },
        "solver_config_hash": primary_solver_config_hash(),
        "solver_config_hash_scope": {
            "definition": "a1_geometry.evaluator.solver_config_hash(geometry_set, tess_u, tess_w, "
                          "timeout_s, omp=1): sha256 over the canonical JSON of everything that can "
                          "change solver numbers except the geometry (geometry_set, tessellation, "
                          "alpha list, Mach/Vinf/rho/ReCref, Cref, Bref, X_cg, RefFlag=0, omp, "
                          "timeout_s, basename)",
            "value_covers": "the PRIMARY PRODUCTION configuration only: thin 12x25, 7 alpha, Mach "
                            "2.02, omp 1, timeout %d s, basename concorde_baseline" % TIMEOUT_SECONDS,
            "other_configs": "thick negative controls and the 24x49/48x97/wake128/Mach-sweep cases "
                             "have different config hashes; each case records its own config_id, "
                             "tessellation and solver_argv, and the per-start ledger carries the "
                             "actual .vspgeom SHA and solver_config_sha256",
            "p0r_relation": "P0R used the same function with timeout 600 s (solver_config_hash "
                            "139e9a70b162a42e30901b093cbe88c524d529fba43aa91208c041752341cae5); "
                            "the P1R value differs only because timeout_s is 900 s, which is "
                            "declared here rather than silently inherited",
            "binding": "recomputed from the plan bytes by binding_verification.json",
        },
        "budget": {
            "primary_budget": "physical_solver_starts",
            "expected_starts": EXPECTED_STARTS,
            "max_starts": MAX_STARTS,
            "expected_internal_cases": EXPECTED_INTERNAL_CASES,
            "max_internal_cases": MAX_INTERNAL_CASES,
            "max_refine_starts": MAX_REFINE_STARTS,
            "max_refine_attempts_per_design": MAX_REFINE_ATTEMPTS_PER_DESIGN,
            "semantics": "expected_internal_cases (189) covers the base matrix only (P1-00a/b/c, "
                         "P1-02a/c/b, P1-03, P1-04/04b/04c, P1-05 = 21, 14 x P1-07). One refine "
                         "start is pre-authorized for the whole batch: at most 2 refine attempts "
                         "per design, at most ONE refine start in total, 7 internal cases, so "
                         "max_internal_cases 196 = 189 + 7. Only actual internal cases > 196, "
                         "starts > 26 or an unapproved/over-budget refine stop the batch; "
                         "actual internal cases in (189, 196] are disclosed, not stopped (A5 X3, "
                         "L-06). Neither cap may be rewritten after the window opens.",
            "smaller_cap_wins": "if approval.json carries smaller caps, the smaller cap governs",
        },
        "concurrency": CONCURRENCY,
        "omp_threads": OMP_THREADS,
        "timeout_seconds_per_case": TIMEOUT_SECONDS,
        "timeout_overrides": {str(key): int(value) for key, value in sorted(TIMEOUT_OVERRIDES.items())},
        "timeout_override_rationale": TIMEOUT_OVERRIDE_RATIONALE,
        "retry_policy": {
            "automatic_numeric_retry": False,
            "infra_retry_allowed": 1,
            "infra_retry_condition": "exit != 0 or missing .polar with stdout/stderr evidence of a "
                                     "file/DLL/lock cause",
            "infra_retry_billing": "each retry is a new physical start with attempt_id and retry_of",
            "timeout_retry": "no automatic retry; the case fails and the batch stops per S1",
        },
        "alpha_policy": {
            "list_deg": list(ALPHA_LIST_DEG),
            "arithmetic": True,
            "start": ALPHA_LIST_DEG[0],
            "end": ALPHA_LIST_DEG[-1],
            "npts": len(ALPHA_LIST_DEG),
            "adaptive_search": False,
            "lift_match_tolerance_relative": 1.0e-3,
        },
        "probe_mesh_feasibility": {
            "path": feasibility_path.relative_to(run_dir).as_posix(),
            "sha256": sha256_file(feasibility_path),
            "all_ok": bool(feasibility.get("all_ok")),
            "probe_count": int(feasibility.get("probe_count") or 0),
            "baseline_family_only": family_label(BASELINE_MESH_FAMILY),
            "target_mesh_family": None,
            "target_mesh_family_note": "A5 B13 / Lead m03961: there is no single probe family. Each "
                                       "probe was rebuilt from its own x12 and its own selected family "
                                       "is recorded per probe below and in feasibility.json; the "
                                       "baseline family is only a reference for comparability",
            "per_probe_families": {
                item["case_id"]: item.get("target_mesh_family")
                for item in (feasibility.get("probes") or [])
            },
            "same_family_probes": [
                item["case_id"] for item in (feasibility.get("probes") or [])
                if item.get("target_mesh_family") == family_label(BASELINE_MESH_FAMILY)
            ],
            "cross_family_probes_not_comparable": [
                item["case_id"] for item in (feasibility.get("probes") or [])
                if item.get("target_mesh_family") != family_label(BASELINE_MESH_FAMILY)
            ],
            "comparability_rule": "same family as the CFG-01 baseline (543x472) = comparable; "
                                  "every other selected family = NOT_COMPARABLE. The lists are "
                                  "derived from the measured feasibility artifact, not hardcoded, "
                                  "because per-probe family selection is sampling-dependent.",
            "max_mesh_attempts": feasibility.get("max_mesh_attempts"),
            "physical_solver_starts": 0,
            "note": "A5 B7/B13: every P1-07 probe design rebuilt from its own x12 before this plan was "
                    "written; no solver start was made. Only same-family probes feed sensitivity.",
        },
        "case_matrix": cases,
        "case_count": len(cases),
        "starts_total": total_starts,
        "internal_cases_total": total_internal,
        "preflight": {
            "index_path": str(preflights["index_path"].relative_to(run_dir)),
            "index_sha256": preflights["index_sha256"],
            "physical_solver_starts": 0,
            "solver_started": False,
            "configs": [
                {
                    "config_id": entry["config_id"],
                    "all_ok": entry["all_ok"],
                    "input_set_sha256": entry["input_set_sha256"],
                    "input_set_sha256_reproducible": False,
                    "contract_digest": entry.get("contract_digest"),
                    "contract_digest_note": "historical field kept null per Lead L-08; it is NOT a "
                                            "gate. Binding is carried by plan sha256 + "
                                            "case_matrix_digest + preflight index sha256 + per-config "
                                            "canonical topology hash + per-config preflight record "
                                            "sha256 (identity_binding block below)",
                    "record_sha256": entry.get("record_sha256"),
                    "mesh": entry.get("mesh"),
                    "mesh_selection": entry.get("mesh_selection"),
                    "canonical_mesh_sha256": (entry.get("mesh") or {}).get("canonical_mesh_sha256"),
                    "input_pieces": entry["input_pieces"],
                    "solver_argv": entry["solver_invocation_argv"],
                    "internal_solver_cases_expected": entry["internal_solver_cases_expected"],
                    "preflight_record": "preflight/%s/preflight.json" % entry["config_id"],
                }
                for entry in preflights["index"]["configs"]
            ],
        },
        "disk": {
            "expected_disk_bytes": expected_disk,
            "max_disk_bytes": max_disk,
            "max_disk_gb": round(max_disk / (1024.0 ** 3), 3),
            "free_disk_bytes_at_planning": int(free_bytes),
            "free_disk_floor_gb": FREE_DISK_FLOOR_GB,
            "estimate_basis": "per case: .vsp3 + .vspgeom + .vspaero + .vkey + .csf (from preflight) "
                              "+ .polar/.history at 1200 B per internal case each + 20,000 B logs/"
                              "case records; max adds 3 refine starts and 10 % margin. T1 large "
                              "derived files are recorded in retention.jsonl and deleted, not kept.",
            "retention_policy": ".vspgeom/.vspaero/.vkey/.csf/.vsp3/.polar/.history/logs/case_*.json "
                                "are retained; .adb/.lod/.group.*/.case.*/.quad.cases are recorded with "
                                "SHA256 in retention.jsonl before deletion",
        },
        "stop_conditions": [
            {"id": "S1", "rule": "solver exit != 0 or missing .polar after the documented single infra "
                                 "retry on a case"},
            {"id": "S2a", "rule": "negative CDi < -1e-6 at |CL| > 0.05 on any thick negative-control case "
                                  "(P1-04, P1-04b, P1-04c: thick at 12x25, 24x49, 48x97) -> "
                                  "PHYSICS_RED_FLAG"},
            {"id": "S2b", "rule": "negative CDi < -1e-6 at |CL| > 0.05 on the thin production surface at "
                                  "any of the three panel densities (P1-02a/c/b) -> PHYSICS_RED_FLAG"},
            {"id": "S3", "rule": "repeatability max |delta CDi| > 1e-3 absolute or > 1 % relative between "
                                 "P1-00a/b/c -> nondeterminism probe first"},
            {"id": "S4", "rule": "dCL/dalpha <= 0 or outside [0.03, 0.30] per degree -> model inconsistency"},
            {"id": "S5", "rule": "starts > 26 or actual internal_solver_cases > 196 or start/end rows "
                                 "cannot be paired -> ACCOUNTING_MISMATCH, stop batch"},
            {"id": "S5b", "rule": "unapproved refine (no logged reason/alpha), more than 2 refine "
                                  "attempts on one design, or more than 1 refine start in the whole "
                                  "batch -> ACCOUNTING_MISMATCH"},
            {"id": "S6", "rule": "wall clock > 6 h, free disk < 50 GB, or Lead revokes the window"},
            {"id": "S7", "rule": "any CLI list flag (-fs/-mach/-alpha/-beta) or any adaptive alpha "
                                 "decision detected in run_config/argv"},
        ],
        "endpoints": [
            {"id": "E1", "rule": "valid .polar with positive CDi at matched lift on the THIN production "
                                 "surface, repeatable R1-R3; thick P1-04 cannot satisfy E1 alone"},
            {"id": "E2", "rule": "conditional and PER FAMILY, never a single global grid answer (A5 "
                                 "B11/B15, Lead m03961): compare 24x49 against 48x97 only when both "
                                 "were produced inside the same selected family (P1-02a 12x25 is "
                                 "CFG-01 543x472; P1-02c 24x49 is CFG-02 923x834; P1-02b 48x97 is CFG-03 "
                                 "1797x1660, so in this batch no two densities share a family). For a "
                                 "shared family: if |CDi(24/49)-CDi(48/97)|/CDi(48/97) <= 2 % and the "
                                 "canonical topology hashes match, the family is internally converged "
                                 "and the coarser grid may be quoted; cross-family difference > 0.5 % "
                                 "means NO POOLING and the density comparison is "
                                 "CROSS_FAMILY_NOT_COMPARABLE. Because no family is shared in this "
                                 "batch, E2 is reported as per-family single-density CDi/D_i and is "
                                 "NOT_VALIDATED as a grid-convergence statement; a global production "
                                 "grid declaration is forbidden."},
            {"id": "E3", "rule": "NOT_VALIDATED (A5 B12 / Lead m03961): P1-00a runs 543x472 while P1-03 "
                                 "(CFG-04 wake128) selected 483x418, so the wake comparison is confounded "
                                 "by mesh family. P1-03 is kept as an engineering/wall-clock observation "
                                 "case only; its CDi must not be used for a wake-effect conclusion"},
            {"id": "E4", "rule": "Mach trend uses ONLY 1.8/2.0/2.2 from P1-05 (one case, one family, "
                                 "equal-spaced sweep). The 2.02 point comes from P1-00a/b/c on the CFG-01 "
                                 "543x472 family and is reported SEPARATELY as NOT_COMPARABLE_WITH_P1_05 "
                                 "(A5 B14 / Lead m03961); it must not be merged into the trend line and a "
                                 "2.02 interpolation from P1-05 rows is forbidden"},
            {"id": "E5", "rule": (
                "intra-family sensitivity only, computed from the MEASURED per-probe families "
                "(A5 B13/B24, Lead m03961/m04380): rank |delta D_i|/D_i against the baseline for "
                "the %d probe(s) whose selected family equals the CFG-01 baseline family %s (%s); "
                "the remaining %d probe(s) (%s) are executed and archived but marked "
                "CROSS_FAMILY_NOT_COMPARABLE / NOT_MEASURED for sensitivity and excluded. These "
                "counts and lists are derived from probe_mesh_feasibility.per_probe_families, not "
                "hardcoded, because per-probe family selection is sampling-dependent. If the "
                "intra-family evidence cannot separate W01-W10 or V01/V02, then E6/V01/V02 = "
                "NOT_VALIDATED; only an evidence-supported outcome may be labelled "
                "10D_ACTIVE_PLUS_2_INACTIVE or 12D_ACTIVE"
                % (len(same_family_probes), baseline_family,
                   ", ".join(same_family_probes) or "none", len(cross_family_probes),
                   ", ".join(cross_family_probes) or "none"))},
            {"id": "E6", "rule": "P1 supports SOLVER_LOOP_VERIFIED only; INTERNAL_AERO_OPTIMIZATION_GAIN "
                                 "needs P2/P3; EXTERNAL_PHYSICS_SUPPORTED needs independent validation. "
                                 "In this batch 12D_ACTIVE / variable sensitivity is NOT_VALIDATED: "
                                 "only the probes whose MEASURED selected family equals the baseline "
                                 "family are intra-family comparable (see "
                                 "probe_mesh_feasibility.same_family_probes), and E3 is NOT_VALIDATED by "
                                 "family confounding (A5 B12/B13/B17, Lead m03961)"},
        ],
        "identity_binding": {
            "rule": "Lead L-08 replacement binding: plan raw sha256 + case_matrix_digest + preflight "
                    "index sha256 + per-config canonical mesh topology hash + per-config preflight "
                    "record sha256 jointly bind this batch; contract_digest stays null and is not a gate",
            "plan_sha256": None,
            "plan_sha256_note": "self-referential by construction: the raw SHA256 of this file is "
                                "reported to the Lead and copied into approval.json, which then binds it",
            "case_matrix_digest": case_matrix_digest,
            "preflight_index_sha256": preflights["index_sha256"],
            "probe_feasibility_sha256": sha256_file(feasibility_path),
            "per_config": [
                {
                    "config_id": entry["config_id"],
                    "record_sha256": entry.get("record_sha256"),
                    "canonical_mesh_sha256": (entry.get("mesh") or {}).get("canonical_mesh_sha256"),
                    "target_mesh_family": (entry.get("mesh") or {}).get("target_family")
                                          or (entry.get("mesh") or {}).get("family"),
                    "mesh_selection_path": (entry.get("mesh_selection") or {}).get("path"),
                    "mesh_selection_sha256": (entry.get("mesh_selection") or {}).get("sha256"),
                }
                for entry in preflights["index"]["configs"]
            ],
            "preregistration_sha256": prereg_sha256,
            "task_spec_raw_sha256": sha256_file(TASK_SPEC_PATH),
            "task_spec_canonical_sha256": task_spec_canonical_sha256(),
        },
        "window": dict(WINDOW_REQUESTED),
        "approval": {
            "approved_by": None,
            "approved_at_utc": None,
            "window_token": None,
            "plan_sha256": "reported to the Lead over the raw bytes of this file after writing",
            "approval_sha256": None,
            "status": "NOT_APPROVED",
            "note": "PENDING_APPROVAL is a document state, not a permission: no solver may start "
                    "until approval.json exists with a window token and caps 25/26 starts and "
                    "189/196 internal cases.",
        },
        "waiver_requests": [
            {
                "id": "X4",
                "subject": "P1-05 Mach values 1.8/2.0/2.2 deviate from governance 1.8/2.02/2.2",
                "reason": "VSPAERO .vspaero only accepts an equal-spacing MachStart/MachEnd/MachNpts "
                          "sweep; 1.8/2.02/2.2 is not equally spaced. Mach 2.02 is covered by "
                          "P1-00a/b/c and every other Mach-2.02 case.",
                "requested_values": [1.8, 2.0, 2.2],
                "governance_values": [1.8, 2.02, 2.2],
                "required_from_lead": "p1_05_mach_waiver {approved: true, approved_by, at_utc} in "
                                      "approval.json, otherwise P1-05 is skipped as SKIPPED_NO_WAIVER",
                "approval_field": "p1_05_mach_waiver",
                "approval_is_authoritative": True,
                "plan_asserts_approval": False,
                "status": "REQUESTED_PENDING_LEAD_APPROVAL",
                "status_semantics": "REQUESTED only: this plan never declares the waiver granted. The "
                                    "batch driver refuses P1-05 unless approval.json carries "
                                    "p1_05_mach_waiver.approved=true with approved_by and at_utc "
                                    "(A5 B16, Lead m04028/m04058).",
            }
        ],
        "disclosures": [
            "P1-05 Mach 1.8/2.0/2.2 (equal spacing requirement), exact 2.02 measured by P1-00a/b/c.",
            "P1-02a reuses the P1-00 solver configuration but is billed as its own start.",
            "P1-07 reuses the CFG-01 solver configuration; per-design .vspgeom SHA is recorded at "
            "input preparation, so the plan carries the configuration SHA only.",
            "P1-02c (24x49) exists because A5 checklist F2 requires the 12/25 -> 24/49 -> 48/97 chain.",
            "expected_internal_cases 189 excludes refine; max_internal_cases 196 = 189 + 1 refine "
            "start x 7 internal cases (L-06: one refine start for the whole batch).",
            "Reference X_cg=16.821978259514246 m is the WING_AC reference, NOT the geometric "
            "full-aircraft CG 28.287395109126685 m; VSPAERO internal coefficients are not whole-aircraft "
            "drag/fuel results.",
        ],
        "physical_solver_starts": 0,
        "solver_started": False,
        "generated_by": "research/concorde_metaopt/dreal001/geometry/p1_plan.py",
        "generator_git_note": "plan.json is committed after generation; its raw SHA256 is reported "
                              "to the Lead and must be copied into approval.json.",
    }
    out = run_dir / "plan.json"
    payload = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    payload_bytes = payload.encode("utf-8")
    # 必须写字节：Windows 文本模式会把 \n 换成 \r\n，导致自报 SHA 与磁盘字节不一致。
    out.write_bytes(payload_bytes)
    plan["_written"] = {"path": str(out), "bytes": len(payload.encode("utf-8")),
                        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}
    return plan


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P1 solver plan generator (zero solver starts)")
    default_run_dir = Path(__file__).resolve().parent / "runs" / DEFAULT_P1_RUN_ID
    parser.add_argument("--run-dir", default=str(default_run_dir))
    parser.add_argument("--prereg", default=None)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--prereg-version", default="v1.5")
    parser.add_argument("--probe-feasibility", action="store_true",
                        help="run the zero-physics 14-probe feasibility preflight, then the plan")
    args = parser.parse_args(argv)
    if args.probe_feasibility:
        feasibility = probe_feasibility(Path(args.run_dir))
        print(json.dumps({"probe_feasibility": {"all_ok": feasibility["all_ok"],
                                                "probe_count": feasibility["probe_count"],
                                                "written": feasibility["_written"]}}, indent=2))
        if not feasibility["all_ok"]:
            return 2
    plan = build_plan(Path(args.run_dir),
                      prereg_path=Path(args.prereg) if args.prereg else None,
                      batch_id=args.batch_id,
                      prereg_version=args.prereg_version)
    print(json.dumps({
        "run_dir": args.run_dir,
        "status": plan["status"],
        "case_count": plan["case_count"],
        "starts_total": plan["starts_total"],
        "internal_cases_total": plan["internal_cases_total"],
        "caps": {"max_starts": plan["budget"]["max_starts"],
                 "max_internal_cases": plan["budget"]["max_internal_cases"]},
        "disk": plan["disk"],
        "preregistration_sha256": plan["preregistration"]["sha256"],
        "preflight_index_sha256": plan["preflight"]["index_sha256"],
        "written": plan["_written"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
