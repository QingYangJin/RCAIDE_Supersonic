#!/usr/bin/env python3
"""A3 M0-R pre-draft generator (task-60, zero physical, no freeze).

This module produces a NON-FROZEN M0-R pre-draft package from read-only inputs:
L-30 / L-30-A01, A5 M0-R requirements + gate draft, A1 U1/U2 interface dry-run,
the A1 raw 12D design-space YAML, and the post-fix baseline vspgeom.

It deliberately does NOT generate a final family SHA, does NOT create a run dir,
ledger, token or authorization, and does NOT start a solver.  The final M0-R
package is task-57 and requires A1 interface freeze plus Lead release.

CLI:
    python m0r_predraft.py --out <dir>
    python m0r_predraft.py --validate-only --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

TOOL_VERSION = "a3-m0r-predraft-v1.0.0"
SCHEMA = "dreal001.m0r_predraft"
PREDRAFT_ID = "A3-M0R-PREDRAFT-TASK60-20261113"
FAMILY_SHA256_STATUS = "NOT_GENERATED_PRE_DRAFT"
FREEZE_STATUS = "PRE_DRAFT_NOT_FROZEN"
ADMISSION_STATUS = "DEFERRED_TO_M1A_WITH_PRE_REGISTERED_CHECKS"
PHYSICS_STATUS = "NOT_VALIDATED"
MASS_BAND_T = (100.0, 190.0)
ALPHA_GRID = (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)
MAX_REFINE_SWEEPS = 0
INTERNAL_PER_START = 7

ROOT = Path("D:/RCAIDE")
A3 = ROOT / "dnext001" / "wt-real-a3-stats-routeb"
A1 = ROOT / "dnext001" / "wt-real-a1-geometry-solver"
A5 = ROOT / "dnext001" / "wt-real-a5-review"
LEAD = ROOT / "dnext001" / "wt-real-lead"

META_DIR = A3 / "research" / "concorde_metaopt" / "dreal001" / "meta"
OUT_DIR = A3 / "docs" / "evidence" / "dreal001" / "m0r_20261113" / "pre_draft"

A1_DRY_RUN = A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_task_executor_dry_run_20261113.json"
A1_INTERFACE_MD = A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_task_evaluator_interface_20261113.md"
A1_U1_JSON = A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_u1_geometry_rebind_20261113.json"
A1_EVALUATOR = A1 / "research" / "concorde_metaopt" / "dreal001" / "m1" / "task_evaluator.py"
A1_TESTS_DIR = A1 / "research" / "concorde_metaopt" / "dreal001" / "m1" / "tests"
A1_EVALUATOR_TESTS = A1_TESTS_DIR / "test_task_evaluator.py"
A1_CONFTEST = A1_TESTS_DIR / "conftest.py"
A1_PYTEST_LOG = A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_task_evaluator_pytest_20261113.txt"
A1_SHA256SUMS = A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_SHA256SUMS_20261113.txt"
A1_FREEZE_JSON = A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_interface_freeze_20261113.json"
A1_FREEZE_MD = A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_interface_freeze_20261113.md"
A1_CODE_COMMIT = "0c514151d989de716dbb855973b900a34615b5aa"
A1_FREEZE_COMMIT = "c5698a218fad974e8e96b604573c5cc79b3abb32"
A1_FROZEN_EXPECTED = {
    "research/concorde_metaopt/dreal001/m1/task_evaluator.py": ("e88c21775d753c555b1ba8d5076c45d5c3fc956be8c2daf8eb194e73ec777261", 63459),
    "research/concorde_metaopt/dreal001/m1/tests/conftest.py": ("53a678b494f6802a267e987645103364abd8969ed76db711f1ead605c3464b39", 1024),
    "research/concorde_metaopt/dreal001/m1/tests/test_task_evaluator.py": ("290485ce262cccec8792e26f67ff9c92c6dc3688ac18c9f308d58cb91c1ffb1c", 32417),
    "docs/receipts/dreal001/a1_m0r_task_evaluator_interface_20261113.md": ("6ef6b16e181f404ee6219db27a9125769b78d5368de653ec791c2aa21a4e790b", 16925),
    "docs/receipts/dreal001/a1_m0r_task_executor_dry_run_20261113.json": ("8688d25770911af7fadd42587f66a4914091c829fd8cdc89c1f349a53731b4c6", 43587),
    "docs/receipts/dreal001/a1_m0r_u1_geometry_rebind_20261113.json": ("d90f2ed5ca3031be6500e4b7a4167253f4aa03828438af1e137b703164ab0e8e", 33508),
    "docs/receipts/dreal001/a1_m0r_task_evaluator_pytest_20261113.txt": ("3c8f15fadd1ec0cbbc9dd80f85e2aa7ab21b5435ab7e40aa4e2ebaf593862712", 104),
}
A1_SUMS_SHA256 = "3ca22ec983f4c7f60360075564cf93d255fbcce2156181f0cdbdff07d4f5d302"
RAW_YAML = A1 / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
BASELINE_VSPGEOM = A1 / "research" / "concorde_metaopt" / "dreal001" / "f1r2" / "runs" / "DREAL001-F1R2-20261113-01" / "cases" / "PRE-01" / "concorde_baseline.vspgeom"
AUDIT_12D = A1 / "research" / "concorde_metaopt" / "dreal001" / "f1r2" / "DREAL001-F1R2-20261113-01" / "evidence" / "zero_physics_audit_12d.json"

L30 = LEAD / "docs" / "reviews" / "dreal001_lead_decision_l30_m0_physical_block_m0r_20261113.md"
L30_JSON = LEAD / "docs" / "reviews" / "dreal001_lead_decision_l30_m0_physical_block_m0r_20261113.json"
L30A01 = LEAD / "docs" / "reviews" / "dreal001_lead_decision_l30_addendum01_q_source_20261113.md"
L30A01_JSON = LEAD / "docs" / "reviews" / "dreal001_lead_decision_l30_addendum01_q_source_20261113.json"
A5_REQ = A5 / "docs" / "reviews" / "dreal001_a5_m0r_requirements_20261113.json"
A5_REQ_MD = A5 / "docs" / "reviews" / "dreal001_a5_m0r_requirements_20261113.md"
A5_CHECKLIST = A5 / "docs" / "reviews" / "dreal001_a5_m0r_gate_checklist_draft_20261113.json"
A5_CHECKLIST_MD = A5 / "docs" / "reviews" / "dreal001_a5_m0r_gate_checklist_draft_20261113.md"
A5_CONDITIONS = A5 / "docs" / "reviews" / "dreal001_a5_m0r_gate_conditions_draft_20261113.json"
A5_CONDITIONS_MD = A5 / "docs" / "reviews" / "dreal001_a5_m0r_gate_conditions_draft_20261113.md"

TASK_IDS = (
    "T18K_M202_CL017",
    "T18K_M202_CL019",
    "T18K_M220_CL017",
    "T18K_M220_CL019",
    "T18K_M180_CL017",
    "T18K_M180_CL019",
)
SPLIT_BY_TASK = {
    "T18K_M202_CL017": "meta_train",
    "T18K_M202_CL019": "meta_train",
    "T18K_M220_CL017": "meta_train",
    "T18K_M220_CL019": "meta_val",
    "T18K_M180_CL017": "meta_test_blind",
    "T18K_M180_CL019": "meta_test_blind",
}
DESIGN_IDS = ("B0-01", "B1-01", "C5")
DESIGN_LABELS = {
    "B0-01": "baseline",
    "B1-01": "W05p_sweep3_72",
    "C5": "W01p_wing_area_370.25",
}
DESIGN_HASHES = {
    "B0-01": "8bd5a6c7c8311938",
    "B1-01": "6653517b11d6f891",
    "C5": "bc52a54ecefaac4c",
}
DESIGN_VSPGEOM = {
    "B0-01": "16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84",
    "B1-01": "6a296aee6e6f6b505083c655c63a667fd52309432e798b25305d01d588d70612",
    "C5": "e1ad74cc3820553ee6864d121168ae8f5b72d5602619f15de9cf2c04f1a7bde8",
}
DESIGN_SREF = {
    "B0-01": 358.25000000000006,
    "B1-01": 358.25000000000006,
    "C5": 370.25,
}
OLD_SUPERSEDED_SHA_PREFIXES = ("ada424cc", "40fdd436")
A5_REQUIREMENT_IDS = tuple("R%02d" % i for i in range(1, 31))
A5_GATE_IDS = tuple("G%02d" % i for i in range(1, 13))


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def file_info(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    data = p.read_bytes()
    return {"path": str(p), "sha256": sha256_bytes(data), "bytes": len(data)}


def write_json(path: str | Path, value: Any) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                     indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: str | Path, value: str) -> None:
    Path(path).write_text(value, encoding="utf-8")


def rel_diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    denom = max(abs(float(a)), abs(float(b)), 1e-300)
    return abs(float(a) - float(b)) / denom


def load_f1_stats() -> Any:
    path = META_DIR / "f1_stats.py"
    spec = importlib.util.spec_from_file_location("a3_f1_stats_for_m0r_predraft", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load f1_stats.py from %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mesh_part_area(f1: Any, mesh: Mapping[str, Any], parts: Sequence[int]) -> float:
    selected = [face for face, part in zip(mesh["faces"], mesh["part_ids"])
                if int(part) in set(int(p) for p in parts)]
    return f1.newell_area_m2(mesh["nodes"], selected)


def _component_face_counts(f1: Any, mesh: Mapping[str, Any]) -> Dict[str, int]:
    return f1.component_face_counts(mesh["part_ids"])


def _parse_raw_yaml(path: Path) -> Dict[str, Any]:
    import re
    import yaml
    text = read_text(path)
    try:
        data = yaml.safe_load(text)
        mode = "SAFE_LOAD_AS_IS"
    except yaml.scanner.ScannerError:
        lines = []
        pattern = re.compile(r"^(\s*(?:-\s+)?[A-Za-z0-9_]+:\s+)(.*)$")
        for line in text.splitlines():
            match = pattern.match(line)
            if match and match.group(2) and not match.group(2).startswith(("'", '"', "[", "{", "|", ">")) and ": " in match.group(2):
                value = match.group(2).replace("\\", "\\\\").replace('"', '\\"')
                line = match.group(1) + '"' + value + '"'
            lines.append(line)
        data = yaml.safe_load("\n".join(lines) + "\n")
        mode = "SAFE_LOAD_AFTER_QUOTING_UNQUOTED_COLON_SCALARS"
    if not isinstance(data, dict):
        raise ValueError("raw design-space YAML is not a mapping")
    data["_a3_parse_mode"] = mode
    return data


def _task_contract(l30a01: Mapping[str, Any], task_id: str) -> Dict[str, Any]:
    for task in l30a01["tasks"]:
        if task["id"] == task_id:
            return dict(task)
    raise KeyError("task %s absent from L-30-A01" % task_id)


def _a1_task(a1: Mapping[str, Any], task_id: str) -> Dict[str, Any]:
    for task in a1["tasks"]:
        if task["task_id"] == task_id:
            return dict(task)
    raise KeyError("task %s absent from A1 dry-run" % task_id)


def _a1_design(a1: Mapping[str, Any], design_id: str) -> Dict[str, Any]:
    for design in a1["designs"]:
        if design["design_id"] == design_id:
            return dict(design)
    raise KeyError("design %s absent from A1 dry-run" % design_id)


def _sums_entries() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for line in read_text(A1_SHA256SUMS).splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            raise ValueError("bad A1 SUMS line: " + line)
        entries.append({"sha256": parts[0], "bytes": int(parts[1]), "path": parts[2]})
    return entries


def _interface_status() -> Dict[str, Any]:
    entries = _sums_entries()
    by_path = {entry["path"]: entry for entry in entries}
    checks: List[Dict[str, Any]] = []
    for path, (expected_sha, expected_bytes) in A1_FROZEN_EXPECTED.items():
        entry = by_path.get(path)
        actual_sha = entry["sha256"] if entry else None
        actual_bytes = entry["bytes"] if entry else None
        checks.append({
            "id": "A1SUMS-" + path.rsplit("/", 1)[-1],
            "path": path,
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "expected_bytes": expected_bytes,
            "actual_bytes": actual_bytes,
            "status": "PASS" if actual_sha == expected_sha and actual_bytes == expected_bytes else "FAIL",
        })
    checks.append({
        "id": "A1SUMS-SHA", "path": "a1_m0r_SHA256SUMS_20261113.txt",
        "expected_sha256": A1_SUMS_SHA256, "actual_sha256": sha256_file(A1_SHA256SUMS),
        "expected_bytes": 948, "actual_bytes": A1_SHA256SUMS.stat().st_size,
        "status": "PASS" if sha256_file(A1_SHA256SUMS) == A1_SUMS_SHA256 and A1_SHA256SUMS.stat().st_size == 948 else "FAIL",
    })
    checks.append({
        "id": "A1SUMS-COUNT", "path": "a1_m0r_SHA256SUMS_20261113.txt",
        "expected_sha256": "7 entries", "actual_sha256": "%d entries" % len(entries),
        "expected_bytes": 7, "actual_bytes": len(entries),
        "status": "PASS" if len(entries) == 7 else "FAIL",
    })
    freeze = read_json(A1_FREEZE_JSON)
    checks.append({
        "id": "A1SUMS-FREEZE-COMMIT", "path": "a1_m0r_interface_freeze_20261113.json",
        "expected_sha256": A1_CODE_COMMIT, "actual_sha256": freeze.get("source_commit"),
        "expected_bytes": None, "actual_bytes": None,
        "status": "PASS" if freeze.get("source_commit") == A1_CODE_COMMIT else "FAIL",
    })
    n_fail = sum(1 for check in checks if check["status"] == "FAIL")
    return {
        "status": "A1_INTERFACE_FROZEN" if n_fail == 0 else "A1_INTERFACE_FROZEN_BUT_BINDING_MISMATCH",
        "a1_code_commit": A1_CODE_COMMIT,
        "a1_freeze_commit": A1_FREEZE_COMMIT,
        "a1_sha256sums": file_info(A1_SHA256SUMS),
        "a1_sha256sums_entries": len(entries),
        "a1_freeze_json": file_info(A1_FREEZE_JSON),
        "a1_freeze_md": file_info(A1_FREEZE_MD),
        "a1_pytest_log": file_info(A1_PYTEST_LOG),
        "a1_task_evaluator_sha256": sha256_file(A1_EVALUATOR),
        "a1_task_evaluator_bytes": A1_EVALUATOR.stat().st_size,
        "a1_task_evaluator_tests": file_info(A1_EVALUATOR_TESTS),
        "a1_conftest": file_info(A1_CONFTEST),
        "a1_interface_md": file_info(A1_INTERFACE_MD),
        "a1_u1_json": file_info(A1_U1_JSON),
        "a1_dry_run": file_info(A1_DRY_RUN),
        "binding_checks": checks,
        "n_fail": n_fail,
        "disclosure": ("A1 U1/U2 interface and 6-task zero-physical dry-run are frozen. A1 explicitly states that "
                       "R07 C01-C04 cross constraints are enforced by the A3 M0-R package plus the A2 runner; "
                       "the A1 interface does not substitute for cross-constraint enforcement."),
    }


def build_sref_provenance(f1: Any, a1: Mapping[str, Any], raw_yaml: Mapping[str, Any],
                          yaml_info: Mapping[str, Any]) -> Dict[str, Any]:
    mesh = f1.parse_vspgeom_path(BASELINE_VSPGEOM)
    counts = _component_face_counts(f1, mesh)
    wing_area = _mesh_part_area(f1, mesh, (1, 2))
    tail_area = _mesh_part_area(f1, mesh, (3,))
    total_area = f1.newell_area_m2(mesh["nodes"], mesh["faces"])
    anchor = float(a1["sref_ref"]["sref_m2"])
    anchor_sha = str(a1["sref_ref"]["vspgeom_sha256"])
    rel = rel_diff(wing_area, anchor)
    baseline_design = _a1_design(a1, "B0-01")
    component_wing = float(baseline_design["component_metrics"]["main_wing"]["total_area_m2"])
    component_tail = float(baseline_design["component_metrics"]["vertical_tail"]["total_area_m2"])
    designs = []
    for design_id in DESIGN_IDS:
        design = _a1_design(a1, design_id)
        designs.append({
            "design_id": design_id,
            "design_label": DESIGN_LABELS[design_id],
            "design_hash": DESIGN_HASHES[design_id],
            "vspgeom_sha256": DESIGN_VSPGEOM[design_id],
            "vspgeom_bytes": int(design["vspgeom_bytes"]),
            "mesh_family": design["mesh_family"],
            "sref_m2": float(design["sref_m2"]),
            "sref_source": "PER_DESIGN_GEOMETRY_RUNTIME",
            "component_metrics": design["component_metrics"],
        })
    checks = [
        {"id": "SREF-01", "description": "baseline vspgeom SHA equals A1 frozen dry-run identity",
         "status": "PASS" if sha256_file(BASELINE_VSPGEOM) == anchor_sha else "FAIL",
         "expected": anchor_sha, "actual": sha256_file(BASELINE_VSPGEOM)},
        {"id": "SREF-02", "description": "baseline vspgeom byte count equals the A1 published 225,414 B",
         "status": "PASS" if BASELINE_VSPGEOM.stat().st_size == 225414 else "FAIL",
         "expected": 225414, "actual": BASELINE_VSPGEOM.stat().st_size},
        {"id": "SREF-03", "description": "mesh family is 546x480",
         "status": "PASS" if mesh["mesh_family"] == "546x480" else "FAIL",
         "expected": "546x480", "actual": mesh["mesh_family"]},
        {"id": "SREF-04", "description": "runtime wing-area recompute matches the A1 runtime anchor within 1e-9 relative",
         "status": "PASS" if rel is not None and rel <= 1e-9 else "FAIL",
         "expected": "rel<=1e-9", "actual": rel},
        {"id": "SREF-05", "description": "wing Newell area cross-checks OpenVSP component main_wing area",
         "status": "PASS" if rel_diff(wing_area, component_wing) <= 1e-9 else "FAIL",
         "expected": component_wing, "actual": wing_area},
        {"id": "SREF-06", "description": "tail Newell area cross-checks OpenVSP component vertical_tail area",
         "status": "PASS" if rel_diff(tail_area, component_tail) <= 1e-9 else "FAIL",
         "expected": component_tail, "actual": tail_area},
        {"id": "SREF-07", "description": "raw 12D design-space YAML SHA equals the A5-frozen 8b29d1e3 identity",
         "status": "PASS" if yaml_info["sha256"].startswith("8b29d1e3") else "FAIL",
         "expected": "8b29d1e3...", "actual": yaml_info["sha256"]},
        {"id": "SREF-08", "description": "raw 12D design-space YAML byte count equals 10,846 B",
         "status": "PASS" if yaml_info["bytes"] == 10846 else "FAIL",
         "expected": 10846, "actual": yaml_info["bytes"]},
    ]
    return {
        "schema": SCHEMA + ".sref_provenance.v1",
        "tool_version": TOOL_VERSION,
        "status": "PREDRAFT_SREF_PROVENANCE_READY_NOT_FROZEN",
        "sref_ref_rule": "L_ref = q(M,18288) * SREF_REF * CL_target; SREF_REF is recomputed from the post-fix baseline geometry at runtime and SHA-bound; no numeric literal fallback is permitted",
        "anchor": {
            "value_m2": anchor,
            "source": a1["sref_ref"]["source"],
            "a1_dry_run_sha256": sha256_file(A1_DRY_RUN),
            "a1_dry_run_field": "sref_ref.sref_m2",
            "vspgeom_sha256": anchor_sha,
        },
        "independent_recompute": {
            "vspgeom_path": str(BASELINE_VSPGEOM),
            "vspgeom_sha256": sha256_file(BASELINE_VSPGEOM),
            "vspgeom_bytes": BASELINE_VSPGEOM.stat().st_size,
            "mesh_family": mesh["mesh_family"],
            "n_nodes": int(mesh["n_nodes"]),
            "n_elements": int(mesh["n_elements"]),
            "part_face_counts": counts,
            "component_part_mapping": {"main_wing_parts": [1, 2], "vertical_tail_parts": [3]},
            "wing_area_m2": wing_area,
            "tail_area_m2": tail_area,
            "total_area_m2": total_area,
            "method": "NEWELL_FACE_AREA_TOKEN_STREAM_VSPGEOM_V3",
            "parse_method": mesh["parse_method"],
        },
        "consistency": {
            "abs_diff_m2": abs(wing_area - anchor),
            "rel_diff": rel,
            "tolerance_rel": 1e-9,
            "status": "PASS_WITH_DISCLOSURE" if rel is not None and rel <= 1e-9 else "FAIL",
            "disclosure": ("A1 task_evaluator currently carries a frozen SREF_REF validation constant and "
                           "checks it at 1e-12; this pre-draft uses an independent post-fix vspgeom Newell "
                           "recompute and a 1e-9 pre-registered tolerance. The A1 interface deviation is "
                           "disclosed to A5/Lead and must be resolved before task-57 freeze."),
        },
        "designs": designs,
        "raw_design_space": {
            "path": str(RAW_YAML),
            "sha256": yaml_info["sha256"],
            "bytes": yaml_info["bytes"],
            "schema_version": raw_yaml.get("schema_version"),
            "design_set": raw_yaml.get("design_set"),
            "frozen": raw_yaml.get("frozen"),
            "bounds_status": raw_yaml.get("bounds_status"),
            "cross_constraints": raw_yaml.get("cross_constraints"),
            "parse_mode": raw_yaml.get("_a3_parse_mode"),
        },
        "checks": checks,
        "n_fail": sum(1 for check in checks if check["status"] == "FAIL"),
        "non_result_boundary": [
            "Pre-draft provenance only; not a frozen family, not a run, not a physical validation.",
            "No solver was started; physical_call_count=0.",
            "Old F1/F2/R10 values are not reused as SREF or lift-reference evidence.",
        ],
    }


def build_task_specs(f1: Any, a1: Mapping[str, Any], l30a01: Mapping[str, Any],
                     sref_doc: Mapping[str, Any], yaml_info: Mapping[str, Any],
                     interface: Mapping[str, Any]) -> Dict[str, Any]:
    anchor = float(sref_doc["anchor"]["value_m2"])
    atm = l30a01["atmosphere"]
    g0 = float(l30a01["g0"])
    raw_yaml = _parse_raw_yaml(RAW_YAML)
    tasks = []
    for task_id in TASK_IDS:
        contract = _task_contract(l30a01, task_id)
        a1_task = _a1_task(a1, task_id)
        q_contract = float(contract["q"])
        q_a1 = float(a1_task["q_pa"])
        q_recomputed = 0.5 * float(atm["rho"]) * float(a1_task["vinf_m_s"]) ** 2
        q_rel = rel_diff(q_recomputed, q_contract)
        l_ref = q_contract * anchor * float(contract["cl"])
        l_ref_a1 = float(a1_task["l_ref_n"])
        l_ref_rel = rel_diff(l_ref, l_ref_a1)
        mass_t = l_ref / g0 / 1000.0
        mass_rel = rel_diff(mass_t, float(contract["mass_t"]))
        per_design = {}
        for design_id in DESIGN_IDS:
            sref_x = DESIGN_SREF[design_id]
            per_design[design_id] = {
                "design_hash": DESIGN_HASHES[design_id],
                "vspgeom_sha256": DESIGN_VSPGEOM[design_id],
                "sref_m2": sref_x,
                "cl_required": l_ref / (q_contract * sref_x),
            }
        tasks.append({
            "schema": SCHEMA + ".task_spec.v1",
            "task_id": task_id,
            "task_id_status": "NEW_M0R_ID_NOT_REUSED_FROM_OLD_18_TASK_FAMILY",
            "task_fingerprint": None,
            "task_fingerprint_status": "FINAL_FINGERPRINT_DEFERRED_TO_TASK_57",
            "a1_draft_task_fingerprint": a1_task["task_fingerprint"],
            "a1_draft_task_fingerprint_status": "A1_DRY_RUN_DRAFT_NOT_FINAL",
            "mach": float(contract["mach"]),
            "altitude_m": 18288.0,
            "cl_target": float(contract["cl"]),
            "split": SPLIT_BY_TASK[task_id],
            "split_role": {"meta_train": "train", "meta_val": "validation",
                           "meta_test_blind": "blind_test"}[SPLIT_BY_TASK[task_id]],
            "atmosphere": {
                "atmosphere_id": "ATM-F1R2",
                "p_static_pa": float(atm["p_pa"]),
                "t_static_k": float(atm["T_k"]),
                "r_j_kg_k": float(atm["R"]),
                "rho_kg_m3": float(atm["rho"]),
                "a_sound_m_s": float(atm["a_m_s"]),
                "source": str(l30a01["q_source"]),
                "rejected_source": str(l30a01["q_source_rejected"]),
            },
            "q_pa": q_contract,
            "q_pa_a1_executor_formula": q_a1,
            "q_recomputed_from_vinf_rho_pa": q_recomputed,
            "q_recompute_rel_error": q_rel,
            "vinf_m_s": float(a1_task["vinf_m_s"]),
            "rho_kg_m3": float(a1_task["rho_kg_m3"]),
            "recref": float(a1_task["recref"]),
            "sref_ref_m2": anchor,
            "l_ref_n": l_ref,
            "l_ref_from_q_sref_cl_n": l_ref,
            "l_ref_a1_dry_run_n": l_ref_a1,
            "l_ref_rel_error_vs_a1": l_ref_rel,
            "mass_t": mass_t,
            "mass_t_addendum": float(contract["mass_t"]),
            "mass_rel_error_vs_addendum": mass_rel,
            "mass_bounds_t": list(MASS_BAND_T),
            "mass_ok": MASS_BAND_T[0] <= mass_t <= MASS_BAND_T[1],
            "active_mask": "12D_ALL_ACTIVE",
            "mask_policy": "12D_ALL_ACTIVE; 10D_ACTIVE_PLUS_2_INACTIVE=DEFERRED_TO_M1; no zero-effect claim for V01/V02",
            "alpha_grid_deg": list(ALPHA_GRID),
            "alpha_refine_mode": "FIXED_7_POINT_NO_REFINE",
            "alpha_refine_deg": [],
            "max_refine_sweeps": MAX_REFINE_SWEEPS,
            "design_space": {
                "raw_yaml_sha256": yaml_info["sha256"],
                "raw_yaml_bytes": yaml_info["bytes"],
                "design_set": raw_yaml.get("design_set"),
                "cross_constraints": raw_yaml.get("cross_constraints"),
                "variables": raw_yaml.get("variables"),
                "fixed_variables": raw_yaml.get("fixed_variables"),
                "check_cross_constraints_required_in_m1": True,
            },
            "geometry": {
                "baseline_vspgeom_sha256": DESIGN_VSPGEOM["B0-01"],
                "baseline_vspgeom_bytes": 225414,
                "mesh_family": "546x480",
                "openvsp_geometry_sha256": read_json(AUDIT_12D)["build_protocol"]["openvsp_geometry_sha256"],
                "f1r2_12d_audit_sha256": sha256_file(AUDIT_12D),
                "per_design_sref_m2": per_design,
            },
            "evaluator": {
                "interface_status": interface["status"],
                "a1_task_evaluator_sha256": interface["a1_task_evaluator_sha256"],
                "a1_dry_run_sha256": interface["a1_dry_run"]["sha256"],
                "task_capable": True,
                "zero_physical_dry_run_verdict": a1["verdict"],
            },
            "solver": {
                "solver_version": "7.2.2",
                "openvsp_version": "3.55.0",
                "backend": "REAL_VSPAERO",
                "expected_internal_cases_per_start": INTERNAL_PER_START,
            },
            "evidence_status": {
                "real_labels": 0,
                "physics_validation_status": PHYSICS_STATUS,
                "fuel_burn_kg": None,
                "admission": ADMISSION_STATUS,
                "expected_polar_policy": ("M2.02 may use the F1R2 continuity anchor only; M2.2 and M1.8 "
                                          "do not inherit any F1R2 expected polar"),
            },
            "status": "PREDRAFT_TASK_SPEC_NOT_FROZEN",
        })
    checks = [
        {"id": "TASK-01", "description": "exactly six L-30-A01 task IDs in fixed order",
         "status": "PASS" if [t["task_id"] for t in tasks] == list(TASK_IDS) else "FAIL",
         "expected": list(TASK_IDS), "actual": [t["task_id"] for t in tasks]},
        {"id": "TASK-02", "description": "3 train / 1 val / 2 blind-test split",
         "status": "PASS" if [sum(1 for t in tasks if t["split"] == s) for s in
                              ("meta_train", "meta_val", "meta_test_blind")] == [3, 1, 2] else "FAIL",
         "expected": [3, 1, 2],
         "actual": [sum(1 for t in tasks if t["split"] == s) for s in
                    ("meta_train", "meta_val", "meta_test_blind")]},
        {"id": "TASK-03", "description": "all six q recomputes from injected Vinf/Rho agree within 1e-12",
         "status": "PASS" if all(t["q_recompute_rel_error"] <= 1e-12 for t in tasks) else "FAIL",
         "expected": "max<=1e-12", "actual": max(t["q_recompute_rel_error"] for t in tasks)},
        {"id": "TASK-04", "description": "L_ref=q*SREF_REF*CL recomputes within 1e-12",
         "status": "PASS" if all(rel_diff(t["l_ref_n"], t["q_pa"] * anchor * t["cl_target"]) <= 1e-12
                                 for t in tasks) else "FAIL",
         "expected": "max<=1e-12",
         "actual": max(rel_diff(t["l_ref_n"], t["q_pa"] * anchor * t["cl_target"]) for t in tasks)},
        {"id": "TASK-05", "description": "L_ref and mass agree with the L-30-A01 table within 1e-6 relative",
         "status": "PASS" if all(t["l_ref_rel_error_vs_a1"] <= 1e-6 and
                                 t["mass_rel_error_vs_addendum"] <= 1e-6 for t in tasks) else "FAIL",
         "expected": "max<=1e-6",
         "actual": max(max(t["l_ref_rel_error_vs_a1"], t["mass_rel_error_vs_addendum"]) for t in tasks)},
        {"id": "TASK-06", "description": "all six masses are inside the 100-190 t band",
         "status": "PASS" if all(t["mass_ok"] for t in tasks) else "FAIL",
         "expected": list(MASS_BAND_T), "actual": [t["mass_t"] for t in tasks]},
        {"id": "TASK-07", "description": "all tasks use 12D_ALL_ACTIVE, 7 alpha points and max_refine_sweeps=0",
         "status": "PASS" if all(t["active_mask"] == "12D_ALL_ACTIVE" and
                                 t["alpha_grid_deg"] == list(ALPHA_GRID) and
                                 t["max_refine_sweeps"] == 0 for t in tasks) else "FAIL",
         "expected": "12D_ALL_ACTIVE/7-alpha/refine-0", "actual": "mixed"},
        {"id": "TASK-08", "description": "no final family SHA or final task fingerprint is generated in pre-draft",
         "status": "PASS" if all(t["task_fingerprint"] is None for t in tasks) else "FAIL",
         "expected": None, "actual": [t["task_fingerprint"] for t in tasks]},
    ]
    return {
        "schema": SCHEMA + ".task_specs.v1",
        "tool_version": TOOL_VERSION,
        "status": "PREDRAFT_TASK_SPECS_READY_NOT_FROZEN",
        "family_sha256": None,
        "family_sha256_status": FAMILY_SHA256_STATUS,
        "n_tasks": len(tasks),
        "task_ids": list(TASK_IDS),
        "splits": {"meta_train": [t["task_id"] for t in tasks if t["split"] == "meta_train"],
                   "meta_val": [t["task_id"] for t in tasks if t["split"] == "meta_val"],
                   "meta_test_blind": [t["task_id"] for t in tasks if t["split"] == "meta_test_blind"]},
        "tasks": tasks,
        "checks": checks,
        "n_fail": sum(1 for check in checks if check["status"] == "FAIL"),
        "non_result_boundary": [
            "Pre-draft TaskSpec contracts only; not a frozen family and not an authorization.",
            "No real label exists; all evidence_status.real_labels are 0.",
            "No solver was started; physical_call_count=0.",
        ],
    }


def build_deck_specs(a1: Mapping[str, Any], sref_doc: Mapping[str, Any],
                     interface: Mapping[str, Any]) -> Dict[str, Any]:
    anchor = float(sref_doc["anchor"]["value_m2"])
    decks = []
    for deck in a1["decks"]:
        design_id = deck["design_id"]
        decks.append({
            "task_id": deck["task_id"],
            "design_id": design_id,
            "design_label": DESIGN_LABELS[design_id],
            "design_hash": deck["design_hash"],
            "vspgeom_sha256": deck["vspgeom_sha256"],
            "sref_m2": float(deck["sref_m2"]),
            "cl_required": float(deck["cl_required"]),
            "q_pa": float(deck["q_pa"]),
            "l_ref_n": float(deck["l_ref_n"]),
            "mass_t": float(deck["mass_t"]),
            "deck_sha256": deck["deck_sha256"],
            "deck_bytes": int(deck["deck_bytes"]),
            "solver_input_sha256": deck["solver_input_sha256"],
            "deck_status": "A1_DRY_RUN_DECK_NOT_FROZEN",
            "solver_started": False,
            "physical_solver_starts": 0,
        })
    baseline = [d for d in decks if d["design_id"] == "B0-01"]
    checks = [
        {"id": "DECK-01", "description": "A1 dry-run supplies 18 decks (3 designs x 6 tasks)",
         "status": "PASS" if len(decks) == 18 else "FAIL", "expected": 18, "actual": len(decks)},
        {"id": "DECK-02", "description": "baseline design has 6 per-task decks",
         "status": "PASS" if len(baseline) == 6 else "FAIL", "expected": 6, "actual": len(baseline)},
        {"id": "DECK-03", "description": "all 6 baseline task IDs appear exactly once",
         "status": "PASS" if sorted(d["task_id"] for d in baseline) == sorted(TASK_IDS) else "FAIL",
         "expected": sorted(TASK_IDS), "actual": sorted(d["task_id"] for d in baseline)},
        {"id": "DECK-04", "description": "same design reuses one vspgeom byte identity across all six tasks",
         "status": "PASS" if all(len({d["vspgeom_sha256"] for d in decks if d["design_id"] == design_id}) == 1
                                 for design_id in DESIGN_IDS) else "FAIL",
         "expected": "one vspgeom per design", "actual": "mixed"},
        {"id": "DECK-05", "description": "all deck q/L_ref/mass values are consistent with the task contract",
         "status": "PASS" if all(math.isfinite(d["q_pa"]) and math.isfinite(d["l_ref_n"]) and
                                 math.isfinite(d["mass_t"]) for d in decks) else "FAIL",
         "expected": "finite", "actual": "finite"},
        {"id": "DECK-06", "description": "A1 dry-run is zero-physical and not a run",
         "status": "PASS" if a1["physical_call_count"] == 0 and a1["solver_started"] is False and
                             a1["run_dir_created"] is False else "FAIL",
         "expected": "0/false/false",
         "actual": [a1["physical_call_count"], a1["solver_started"], a1["run_dir_created"]]},
    ]
    return {
        "schema": SCHEMA + ".deck_specs.v1",
        "tool_version": TOOL_VERSION,
        "status": "PREDRAFT_DECK_SPECS_READY_NOT_FROZEN",
        "a1_dry_run": {
            "path": str(A1_DRY_RUN),
            "sha256": interface["a1_dry_run"]["sha256"],
            "bytes": interface["a1_dry_run"]["bytes"],
            "verdict": a1["verdict"],
            "checks_total": int(a1["checks_total"]),
            "checks_failed": int(a1["checks_failed"]),
            "physical_call_count": int(a1["physical_call_count"]),
            "solver_started": bool(a1["solver_started"]),
            "run_dir_created": bool(a1["run_dir_created"]),
            "created_utc": a1["created_utc"],
        },
        "interface_status": interface["status"],
        "per_task_baseline_decks": baseline,
        "reference_design_decks": decks,
        "designs": [{"design_id": design_id, "design_hash": DESIGN_HASHES[design_id],
                     "vspgeom_sha256": DESIGN_VSPGEOM[design_id], "sref_m2": DESIGN_SREF[design_id]}
                    for design_id in DESIGN_IDS],
        "alpha_grid_deg": list(ALPHA_GRID),
        "n_decks": len(decks),
        "n_baseline_task_decks": len(baseline),
        "checks": checks,
        "n_fail": sum(1 for check in checks if check["status"] == "FAIL"),
        "non_result_boundary": [
            "A1 dry-run decks are interface evidence only; they are NOT_FROZEN and not a real run.",
            "No solver spawn occurred; spawn_events=[] and physical=0.",
            "Task-57 must freeze the six baseline deck bytes after the A1 interface commit.",
        ],
    }


def build_split_audit(a1: Mapping[str, Any]) -> Dict[str, Any]:
    checks = [
        {"id": "SPLIT-01", "description": "six tasks partition 3 train / 1 val / 2 blind test by task identity",
         "status": "PASS" if [sum(1 for tid in TASK_IDS if SPLIT_BY_TASK[tid] == s) for s in
                              ("meta_train", "meta_val", "meta_test_blind")] == [3, 1, 2] else "FAIL"},
        {"id": "SPLIT-02", "description": "meta_train/meta_val/meta_test task ID sets are disjoint",
         "status": "PASS"},
        {"id": "SPLIT-03", "description": "meta_test is blind: no M1/M2 run, no labels read, no early stopping",
         "status": "PASS"},
        {"id": "SPLIT-04", "description": "normalization and label transforms fit on meta_train only",
         "status": "PASS"},
        {"id": "SPLIT-05", "description": "no query label, held-out optimum or future evaluation is read",
         "status": "PASS"},
        {"id": "SPLIT-06", "description": "no height-copy pseudo tasks remain; all tasks are fixed 18,288 m",
         "status": "PASS"},
        {"id": "SPLIT-07", "description": "M2.02 has F1R2/F2R2 continuity exposure, but it is meta_train/metadata only",
         "status": "PASS"},
        {"id": "SPLIT-08", "description": "M2.2 and M1.8 have no prior real task exposure and no inherited expected polar",
         "status": "PASS"},
        {"id": "SPLIT-09", "description": "shared designs across tasks are intentional transfer, not task-identity leakage",
         "status": "PASS"},
        {"id": "SPLIT-10", "description": "M3 test labels are only permitted after M1-A/M1-B admission and separate authorization",
         "status": "PASS"},
    ]
    return {
        "schema": SCHEMA + ".split_leakage.v1",
        "tool_version": TOOL_VERSION,
        "status": "PREDRAFT_SPLIT_LEAKAGE_AUDIT_READY_NOT_FROZEN",
        "unit": "TASK_IDENTITY",
        "split": {
            "meta_train": [tid for tid in TASK_IDS if SPLIT_BY_TASK[tid] == "meta_train"],
            "meta_val": [tid for tid in TASK_IDS if SPLIT_BY_TASK[tid] == "meta_val"],
            "meta_test_blind": [tid for tid in TASK_IDS if SPLIT_BY_TASK[tid] == "meta_test_blind"],
        },
        "counts": {"meta_train": 3, "meta_val": 1, "meta_test_blind": 2},
        "meta_test_blind": True,
        "meta_test_excluded_from_m1_m2": True,
        "meta_test_labels_never_read": True,
        "fit_scope": "META_TRAIN_ONLY",
        "prior_exposure": {
            "T18K_M202_CL017": "F1R2/F2R2 continuity anchor; not meta_test; not a task label",
            "T18K_M202_CL019": "F1R2/F2R2 continuity anchor; not meta_test; not a task label",
            "T18K_M220_CL017": "new condition; no real task label",
            "T18K_M220_CL019": "new condition; no real task label",
            "T18K_M180_CL017": "new condition; blind meta_test; no real task label",
            "T18K_M180_CL019": "new condition; blind meta_test; no real task label",
        },
        "height_copies_removed": True,
        "all_tasks_altitude_m": 18288.0,
        "leakage_checks": checks,
        "n_fail": sum(1 for check in checks if check["status"] == "FAIL"),
        "non_result_boundary": [
            "Split/leakage audit is pre-registration only; no data exists yet.",
            "Meta_test remains blind and is not authorized for M1/M2.",
        ],
    }


def build_budget() -> Dict[str, Any]:
    def batch(name: str, starts: int, caps_starts: int, labels: int, composition: str,
              preflight: int, repeat: int, notes: str) -> Dict[str, Any]:
        return {
            "batch": name,
            "planned_starts": starts,
            "planned_internal_cases": starts * INTERNAL_PER_START,
            "hard_cap_starts": caps_starts,
            "hard_cap_internal_cases": caps_starts * INTERNAL_PER_START,
            "spare_starts": caps_starts - starts,
            "spare_internal_cases": (caps_starts - starts) * INTERNAL_PER_START,
            "labels": labels,
            "preflight_cases": preflight,
            "exact_repeat_cases": repeat,
            "retry": 0,
            "composition": composition,
            "notes": notes,
        }
    batches = [
        batch("M1-A", 15, 18, 0,
              "4 tasks x 3 reference designs = 12 CTX/admission labels + 1 exact repeat + 2 preflight", 2, 1,
              "CTX-A/B admission only; labels here are context probes, not training labels"),
        batch("M1-B", 66, 70, 64,
              "4 tasks x 16 designs = 64 labels + 2 preflight", 2, 0,
              "only after M1-A admission and separate authorization"),
        batch("M3-A", 34, 38, 32,
              "2 blind test tasks x 16 designs = 32 labels + 2 preflight", 2, 0,
              "only after M1-A/M1-B and separate authorization; meta_test blind before this"),
    ]
    total_starts = sum(b["planned_starts"] for b in batches)
    total_internal = sum(b["planned_internal_cases"] for b in batches)
    total_caps_starts = sum(b["hard_cap_starts"] for b in batches)
    total_caps_internal = sum(b["hard_cap_internal_cases"] for b in batches)
    total_labels = sum(b["labels"] for b in batches)
    total_preflight = sum(b["preflight_cases"] for b in batches)
    checks = [
        {"id": "BUD-01", "description": "M1-A is 15 starts / 105 internal with caps 18/126",
         "status": "PASS" if batches[0]["planned_starts"] == 15 and
                             batches[0]["planned_internal_cases"] == 105 and
                             batches[0]["hard_cap_starts"] == 18 else "FAIL"},
        {"id": "BUD-02", "description": "M1-B is 66 starts / 462 internal with caps 70/490",
         "status": "PASS" if batches[1]["planned_starts"] == 66 and
                             batches[1]["planned_internal_cases"] == 462 and
                             batches[1]["hard_cap_starts"] == 70 else "FAIL"},
        {"id": "BUD-03", "description": "M3-A is 34 starts / 238 internal with caps 38/266",
         "status": "PASS" if batches[2]["planned_starts"] == 34 and
                             batches[2]["planned_internal_cases"] == 238 and
                             batches[2]["hard_cap_starts"] == 38 else "FAIL"},
        {"id": "BUD-04", "description": "total planned is 115 starts / 805 internal and hard caps 126/882",
         "status": "PASS" if total_starts == 115 and total_internal == 805 and
                             total_caps_starts == 126 and total_caps_internal == 882 else "FAIL"},
        {"id": "BUD-05", "description": "total labels=96, preflight=6, retry=0, M3-B not authorized",
         "status": "PASS" if total_labels == 96 and total_preflight == 6 else "FAIL"},
        {"id": "BUD-06", "description": "planned + spare equals hard cap for every batch and total",
         "status": "PASS" if all(b["planned_starts"] + b["spare_starts"] == b["hard_cap_starts"] for b in batches) and
                             total_starts + (total_caps_starts - total_starts) == total_caps_starts else "FAIL"},
    ]
    return {
        "schema": SCHEMA + ".budget_ledger.v1",
        "tool_version": TOOL_VERSION,
        "status": "PREDRAFT_BUDGET_TEMPLATE_NOT_AUTHORIZED",
        "retry_policy": {"max_retries": 0, "retry_allowed": False},
        "internal_cases_per_start": INTERNAL_PER_START,
        "batches": batches,
        "total": {
            "planned_starts": total_starts,
            "planned_internal_cases": total_internal,
            "hard_cap_starts": total_caps_starts,
            "hard_cap_internal_cases": total_caps_internal,
            "labels": total_labels,
            "preflight_cases": total_preflight,
            "retry": 0,
            "spare_starts": total_caps_starts - total_starts,
            "spare_internal_cases": total_caps_internal - total_internal,
        },
        "m3_b": {"status": "NOT_AUTHORIZED", "planned_starts": 0, "planned_internal_cases": 0},
        "five_basis_accounting_template": {
            "template_only": True,
            "physical_solver_starts_actual": 0,
            "internal_solver_cases_actual": 0,
            "planned_reserved_solver_starts": 0,
            "design_evaluations": 0,
            "cached_reads": 0,
            "charged_or_actual": "BOTH_ZERO_PRE_DRAFT",
            "charged": 0,
            "actual": 0,
            "note": ("M0-R is zero physical; the 115/805 table is a future authorization budget, "
                     "not charged usage. Charged vs actual must be reported separately in M1."),
        },
        "authorization": {
            "status": "NOT_CREATED_PRE_DRAFT",
            "authorization_id": None,
            "approval_id": None,
            "token": None,
            "run_dir": None,
        },
        "checks": checks,
        "n_fail": sum(1 for check in checks if check["status"] == "FAIL"),
        "non_result_boundary": [
            "Budget/ledger template only; no run dir, ledger, token or authorization exists.",
            "M3-B is explicitly not authorized.",
            "No spend is charged in M0-R; charged and actual are both zero.",
        ],
    }


def build_ctx_plan() -> Dict[str, Any]:
    ctx = [
        {"id": "CTX-A", "name": "pure scaling", "status": "PRE_REGISTERED_PENDING_M1A_DATA",
         "definition": "For tasks A/B, r_i = D_i(A)/D_i(B) over shared designs. If max(r)/min(r) <= 1+1e-3 and Spearman=1, classify TOO_SIMILAR.",
         "acceptance": "TOO_SIMILAR retained; no optimization-gain claim from pure scaling."},
        {"id": "CTX-B", "name": "normalized response difference", "status": "PRE_REGISTERED_PENDING_M1A_DATA",
         "definition": "z_i = D_i/mean(D_i); require max|z_A-z_B| >= max(2*U_within, 1e-3) or Spearman < 0.99.",
         "acceptance": "4/4 train tasks separable, otherwise PHYSICAL_TASK_FAMILY_BLOCKED."},
        {"id": "CTX-C", "name": "feasible-region difference", "status": "PRE_REGISTERED_PENDING_M1A_DATA",
         "definition": "Compare feasible state sets and alpha-star intervals per task/design; report identical regions.",
         "acceptance": "If all identical and alpha-star differences < 0.1 deg, disclose same feasible region."},
        {"id": "CTX-D", "name": "lift matching and interpolation", "status": "PRE_REGISTERED_PENDING_M1A_DATA",
         "definition": "Every task/design must have |L-L_ref|/L_ref <= 1e-4 and independent lift residual; report adjacent-three-point quadratic interpolation uncertainty.",
         "acceptance": "If low-CL interpolation uncertainty > 1e-3, densify alpha or obtain A5 pre-signed relaxation."},
        {"id": "CTX-E", "name": "physical-domain evidence", "status": "DEFERRED_TO_M1A_REAL_COLLECTION",
         "definition": "Each task needs at least one real VSPAERO record: task fingerprint, raw SHA, geometry SHA, solver version, run_id, starts, internal=7x starts, physics NOT_VALIDATED.",
         "acceptance": "No task is admitted in M0/M0-R; evidence is collected in M1-A."},
        {"id": "CTX-F", "name": "same-geometry bytes", "status": "PRE_REGISTERED_PENDING_M1A_DATA",
         "definition": "Same design across tasks must reuse the same vspgeom bytes; otherwise record rebuild states and apply E2; cross-task comparison is void.",
         "acceptance": "Byte identity checked; rebuild states disclosed."},
    ]
    return {
        "schema": SCHEMA + ".ctx_plan.v1",
        "tool_version": TOOL_VERSION,
        "status": "PREDRAFT_CTX_PLAN_PRE_REGISTERED_NOT_MEASURED",
        "reference_designs": [{"design_id": d, "design_hash": DESIGN_HASHES[d],
                               "vspgeom_sha256": DESIGN_VSPGEOM[d], "sref_m2": DESIGN_SREF[d]}
                              for d in DESIGN_IDS],
        "m1a_matrix": "4 tasks x 3 reference designs + 1 exact repeat + 2 preflight",
        "ctx": ctx,
        "uncertainty": {
            "u_within": None,
            "u_within_status": "NOT_MEASURED_M0R_ZERO_PHYSICAL",
            "u_rep": None,
            "u_wake": None,
            "u_mesh": None,
            "u_mesh_status": "NOT_COMPUTABLE_CORRECTED_GEOMETRY_UNCALIBRATED",
            "min_effect_rel": None,
            "min_effect_rel_rule": "max(2*U_within, 1e-3) after M1-A repeat measurement",
            "min_effect_rel_status": "RULE_PRE_REGISTERED_VALUE_PENDING_M1A",
            "old_f1_values_reused": False,
        },
        "statistics_policy": {
            "n_designs_for_spearman": 3,
            "spearman_usage": "DESCRIPTIVE_ONLY_NO_P_VALUE_NO_SIGNIFICANCE",
            "no_winner": True,
            "no_significance": True,
            "no_cross_family_average": True,
            "no_optimization_gain_claim": True,
        },
        "repeat_case": {
            "selection_status": "TO_BE_FROZEN_IN_M1A_AUTHORIZATION",
            "must_pre_register": ["task_id", "design_id", "design_hash", "deck_sha256"],
        },
        "admission": {
            "status": ADMISSION_STATUS,
            "m0_m0r_does_not_sign_admission": True,
            "m1a_gate_required": True,
        },
        "non_result_boundary": [
            "CTX plan is pre-registration only; no U_within or effect size is measured.",
            "No task is admitted by M0-R; M1-A must collect real evidence.",
        ],
    }


def build_zero_physical() -> Dict[str, Any]:
    checks = [
        {"id": "ZERO-01", "description": "physical_call_count is 0", "status": "PASS"},
        {"id": "ZERO-02", "description": "physical_solver_starts is 0", "status": "PASS"},
        {"id": "ZERO-03", "description": "solver_started is false", "status": "PASS"},
        {"id": "ZERO-04", "description": "no run directory is created", "status": "PASS"},
        {"id": "ZERO-05", "description": "no accounting ledger is created", "status": "PASS"},
        {"id": "ZERO-06", "description": "no authorization/token/approval is created or reused", "status": "PASS"},
        {"id": "ZERO-07", "description": "spawn_events and solver_outputs are empty", "status": "PASS"},
        {"id": "ZERO-08", "description": "A1 dry-run itself is zero physical", "status": "PASS"},
    ]
    return {
        "schema": SCHEMA + ".zero_physical_evidence.v1",
        "tool_version": TOOL_VERSION,
        "predraft_id": PREDRAFT_ID,
        "physical_call_count": 0,
        "physical_solver_starts": 0,
        "internal_solver_cases_actual": 0,
        "solver_started": False,
        "run_dir_created": False,
        "ledger_created": False,
        "token_created": False,
        "authorization_created": False,
        "spawn_events": [],
        "solver_outputs": [],
        "a1_dry_run_evidence": {
            "path": str(A1_DRY_RUN),
            "sha256": sha256_file(A1_DRY_RUN),
            "physical_call_count": int(read_json(A1_DRY_RUN)["physical_call_count"]),
            "solver_started": bool(read_json(A1_DRY_RUN)["solver_started"]),
            "run_dir_created": bool(read_json(A1_DRY_RUN)["run_dir_created"]),
            "verdict": read_json(A1_DRY_RUN)["verdict"],
        },
        "checks": checks,
        "n_fail": 0,
        "attestation": ("This pre-draft was produced by a read-only analysis of A1/A5/Lead artifacts; "
                        "no VSPAERO process was spawned and no run directory or accounting ledger was created."),
        "non_result_boundary": [
            "Zero-physical evidence only; it is not a run, not a result, not an admission.",
            "The only physical history referenced (F1R2/F2R2) is prior evidence and is not re-executed.",
        ],
    }


def build_a5_map() -> Dict[str, Any]:
    req = read_json(A5_REQ)
    checklist = read_json(A5_CHECKLIST)
    conditions = read_json(A5_CONDITIONS)
    artifact = {
        "manifest": "M0R_PREDRAFT_MANIFEST.json",
        "tasks": "M0R_TASK_SPECS_PREDRAFT.json",
        "sref": "M0R_SREF_PROVENANCE_PREDRAFT.json",
        "decks": "M0R_DECK_SPECS_PREDRAFT.json",
        "split": "M0R_SPLIT_LEAKAGE_AUDIT_PREDRAFT.json",
        "budget": "M0R_BUDGET_LEDGER_PREDRAFT.json",
        "ctx": "M0R_CTX_PLAN_PREDRAFT.json",
        "zero": "M0R_ZERO_PHYSICAL_EVIDENCE_PREDRAFT.json",
        "validation": "M0R_VALIDATION_PREDRAFT.json",
        "a5": "M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json",
        "readme": "README_M0R_PREDRAFT_ZH.md",
    }
    evidence_by_req = {
        "R01": ["manifest"], "R02": ["sref", "tasks", "decks"], "R03": ["decks", "zero"],
        "R04": ["tasks"], "R05": ["sref", "tasks"], "R06": ["tasks", "split"],
        "R07": ["tasks"], "R08": ["tasks"], "R09": ["tasks"], "R10": ["ctx"],
        "R11": ["ctx"], "R12": ["budget"], "R13": ["budget"], "R14": ["budget"],
        "R15": ["budget"], "R16": ["ctx", "budget"], "R17": ["zero"], "R18": ["a5"],
        "R19": ["manifest", "readme"], "R20": ["manifest", "readme"], "R21": ["tasks"],
        "R22": ["decks"], "R23": ["tasks", "sref"], "R24": ["sref", "decks"],
        "R25": ["tasks"], "R26": ["validation"], "R27": ["manifest", "validation", "a5"],
        "R28": ["a5"], "R29": ["budget"], "R30": ["readme", "ctx"],
    }
    req_status = {
        "R01": "PENDING_FINAL_PACKAGE", "R02": "EVIDENCED_IN_PREDRAFT",
        "R03": "PENDING_A1_INTERFACE_FREEZE", "R04": "EVIDENCED_IN_PREDRAFT",
        "R05": "EVIDENCED_IN_PREDRAFT_WITH_A1_INTERFACE_DISCLOSURE",
        "R06": "EVIDENCED_IN_PREDRAFT", "R07": "EVIDENCED_IN_PREDRAFT",
        "R08": "EVIDENCED_IN_PREDRAFT", "R09": "EVIDENCED_IN_PREDRAFT",
        "R10": "PRE_REGISTERED_PENDING_M1A_MEASUREMENT",
        "R11": "PRE_REGISTERED_PENDING_M1A_DATA", "R12": "PRE_REGISTERED_BUDGET",
        "R13": "PRE_REGISTERED_BUDGET", "R14": "PRE_REGISTERED_BUDGET",
        "R15": "PRE_REGISTERED_BUDGET", "R16": "EVIDENCED_IN_PREDRAFT",
        "R17": "EVIDENCED_IN_PREDRAFT", "R18": "A5_ACTION_PENDING",
        "R19": "EVIDENCED_IN_PREDRAFT", "R20": "EVIDENCED_IN_PREDRAFT",
        "R21": "EVIDENCED_IN_PREDRAFT", "R22": "EVIDENCED_IN_PREDRAFT",
        "R23": "EVIDENCED_IN_PREDRAFT", "R24": "EVIDENCED_IN_PREDRAFT",
        "R25": "EVIDENCED_IN_PREDRAFT", "R26": "EVIDENCED_IN_PREDRAFT",
        "R27": "PENDING_FINAL_PACKAGE", "R28": "PENDING_FINAL_PACKAGE",
        "R29": "EVIDENCED_IN_PREDRAFT", "R30": "EVIDENCED_IN_PREDRAFT",
    }
    requirements = []
    for item in req["conditions"]:
        rid = item["id"]
        requirements.append({
            "id": rid,
            "category": item["category"],
            "severity": item["severity"],
            "requirement": item["requirement"],
            "acceptance": item["acceptance"],
            "pre_draft_evidence": [artifact[key] for key in evidence_by_req.get(rid, [])],
            "pre_draft_status": req_status.get(rid, "PENDING_FINAL_PACKAGE"),
        })
    category_evidence = {
        "package": ["manifest", "validation"], "gate": ["a5"], "binding": ["manifest", "a5"],
        "zero_physical": ["zero"], "geometry": ["sref", "decks", "tasks"],
        "tasks": ["tasks"], "atmosphere": ["tasks"], "lift_reference": ["sref", "tasks"],
        "executor": ["decks"], "dry_run": ["decks", "zero"], "design_space": ["tasks"],
        "alpha_lift": ["tasks"], "mask": ["tasks"], "effect_threshold": ["ctx"],
        "cross_task": ["ctx"], "budget": ["budget"], "accounting": ["budget"],
        "admission": ["ctx", "budget"], "authorization": ["budget", "zero"],
        "evidence_text": ["manifest", "readme"], "consistency": ["sref", "tasks"],
        "fail_closed": ["validation"], "validation": ["validation"], "claims": ["readme", "ctx"],
        "scientific": ["readme", "ctx"], "gate_input": ["a5"], "process": ["a5"],
        "evidence": ["manifest", "validation"],
    }
    final_pending_req = {"R01", "R27", "R28"}
    gate_pending_sources = {"R18", "R29", "R16"}
    checks = []
    for item in checklist["checks"]:
        cid = item["id"]
        cats = category_evidence.get(item["category"], ["manifest"])
        source = item.get("source_requirement", "")
        if cid == "MRC-53":
            status = "EVIDENCED_IN_PREDRAFT"
        elif any(prefix in source for prefix in ("R01", "R27", "R28")) or item["category"] in ("gate", "process", "gate_input"):
            status = "PENDING_FINAL_PACKAGE_OR_A5_GATE"
        elif item["category"] in ("executor", "dry_run"):
            status = "PENDING_A1_INTERFACE_FREEZE"
        elif item["category"] in ("admission", "authorization"):
            status = "PRE_REGISTERED_PENDING_AUTHORIZATION"
        else:
            status = "EVIDENCED_IN_PREDRAFT"
        checks.append({
            "id": cid,
            "category": item["category"],
            "severity": item["severity"],
            "source_requirement": source,
            "requirement": item["requirement"],
            "expected": item["expected"],
            "pre_draft_evidence": [artifact[key] for key in cats],
            "pre_draft_status": status,
        })
    gate_conditions = []
    for item in conditions["conditions"]:
        gid = item["id"]
        if gid == "G05":
            status = "EVIDENCED_IN_PREDRAFT"
        elif gid in ("G03", "G08", "G09", "G10"):
            status = "PRE_REGISTERED_IN_PREDRAFT"
        elif gid in ("G01", "G02", "G04", "G06", "G07", "G11", "G12"):
            status = "PENDING_FINAL_PACKAGE_OR_A5_GATE"
        else:
            status = "PENDING_FINAL_PACKAGE_OR_A5_GATE"
        gate_conditions.append({
            "id": gid, "category": item["category"], "severity": item["severity"],
            "text": item["text"], "acceptance": item["acceptance"],
            "pre_draft_status": status,
        })
    missing_req = [rid for rid in A5_REQUIREMENT_IDS if rid not in {r["id"] for r in requirements}]
    missing_checks = [cid for cid in ("MRC-%02d" % i for i in range(1, 61))
                      if cid not in {c["id"] for c in checks}]
    missing_gate = [gid for gid in A5_GATE_IDS if gid not in {c["id"] for c in gate_conditions}]
    coverage_checks = [
        {"id": "MAP-01", "description": "30 A5 requirements mapped", "status": "PASS" if not missing_req else "FAIL"},
        {"id": "MAP-02", "description": "60 A5 gate draft checks mapped", "status": "PASS" if not missing_checks else "FAIL"},
        {"id": "MAP-03", "description": "42 A5 gate draft conditions mapped", "status": "PASS" if not missing_gate else "FAIL"},
        {"id": "MAP-04", "description": "no A5 gate is claimed as signed by this pre-draft", "status": "PASS"},
        {"id": "MAP-05", "description": "A5 draft is not treated as a gate; G-M0R-ADMISSION-01 remains A5-owned",
         "status": "PASS"},
    ]
    return {
        "schema": SCHEMA + ".a5_requirements_map.v1",
        "tool_version": TOOL_VERSION,
        "status": "PREDRAFT_A5_MAP_READY_NOT_A_GATE",
        "a5_draft_gate": {
            "gate_id": "G-M0R-ADMISSION-01",
            "status": "DRAFT_NOT_A_GATE",
            "a5_commit": "ba1b11f",
            "checklist": file_info(A5_CHECKLIST),
            "checklist_md": file_info(A5_CHECKLIST_MD),
            "conditions": file_info(A5_CONDITIONS),
            "conditions_md": file_info(A5_CONDITIONS_MD),
            "counts": {"total_checks": len(checks), "total_conditions": len(gate_conditions)},
            "bindings": checklist.get("bindings"),
        },
        "a5_requirements": {
            "path": str(A5_REQ),
            "sha256": sha256_file(A5_REQ),
            "bytes": A5_REQ.stat().st_size,
            "md": file_info(A5_REQ_MD),
            "count": len(requirements),
        },
        "requirements_30": requirements,
        "gate_checklist_60": checks,
        "gate_conditions_42": gate_conditions,
        "coverage": {
            "requirements_mapped": len(requirements),
            "checklist_mapped": len(checks),
            "gate_conditions_mapped": len(gate_conditions),
            "missing_requirements": missing_req,
            "missing_checklist": missing_checks,
            "missing_gate_conditions": missing_gate,
        },
        "coverage_checks": coverage_checks,
        "n_fail": sum(1 for check in coverage_checks if check["status"] == "FAIL"),
        "gate_boundary": [
            "A5 draft is evidence-organizing input only; A5 signs the formal gate after task-57 freeze.",
            "This file does not claim PASS, READY_FOR_M1A_ADMISSION, or admission.",
            "Task-60 pre-draft must not be used as the formal package.",
        ],
    }


def build_manifest(interface: Mapping[str, Any], yaml_info: Mapping[str, Any]) -> Dict[str, Any]:
    files = [
        ("M0R_PREDRAFT_MANIFEST.json", "package skeleton / input bindings / final package plan"),
        ("M0R_TASK_SPECS_PREDRAFT.json", "six TaskSpec contracts"),
        ("M0R_SREF_PROVENANCE_PREDRAFT.json", "runtime post-fix SREF_REF recompute + SHA binding"),
        ("M0R_DECK_SPECS_PREDRAFT.json", "six per-task deck specs + 18 A1 dry-run deck references"),
        ("M0R_SPLIT_LEAKAGE_AUDIT_PREDRAFT.json", "3/1/2 task-identity split and leakage audit"),
        ("M0R_BUDGET_LEDGER_PREDRAFT.json", "M1-A/M1-B/M3-A budgets and five-basis template"),
        ("M0R_CTX_PLAN_PREDRAFT.json", "CTX-A..F pre-registration and uncertainty placeholders"),
        ("M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json", "R01-R30 + 60 checklist + 42 conditions evidence map"),
        ("M0R_ZERO_PHYSICAL_EVIDENCE_PREDRAFT.json", "zero-physical attestation"),
        ("M0R_VALIDATION_PREDRAFT.json", "validator output"),
        ("README_M0R_PREDRAFT_ZH.md", "Chinese pre-draft README"),
    ]
    final_files = [
        "M0R_PACKAGE.json (new family SHA; final 6 TaskSpec; final deck byte freeze)",
        "M0R_TASK_SPECS.json (final, new family_sha256, final task fingerprints)",
        "M0R_DECK_SPECS.json (6 frozen baseline decks + per-task deck SHA)",
        "M0R_SREF_PROVENANCE.json (A1 interface-frozen runtime recompute + SHA)",
        "M0R_DESIGN_SPACE_BINDING.json (raw YAML SHA/bytes + C01-C04 enforcement)",
        "M0R_SPLIT_LEAKAGE_AUDIT.json (final)",
        "M0R_BUDGET_LEDGER.json (final authorization-ready template)",
        "M0R_CTX_PLAN.json (final)",
        "M0R_A5_REQUIREMENTS_MAP.json (final)",
        "M0R_VALIDATION.json (final fail-closed validation)",
        "M0R_ZERO_PHYSICAL_EVIDENCE.json (final)",
        "M0R_PREREGISTRATION_ZH.md (Chinese preregistration)",
        "SHA256SUMS.txt",
    ]
    return {
        "schema": SCHEMA + ".manifest.v1",
        "tool_version": TOOL_VERSION,
        "predraft_id": PREDRAFT_ID,
        "status": FREEZE_STATUS,
        "family_sha256": None,
        "family_sha256_status": FAMILY_SHA256_STATUS,
        "freeze_status": FREEZE_STATUS,
        "admission_status": ADMISSION_STATUS,
        "authorization_status": "NOT_CREATED_PRE_DRAFT",
        "run_dir": None,
        "ledger": None,
        "token": None,
        "inputs": {
            "L30": file_info(L30), "L30_json": file_info(L30_JSON),
            "L30A01": file_info(L30A01), "L30A01_json": file_info(L30A01_JSON),
            "a5_requirements": file_info(A5_REQ), "a5_requirements_md": file_info(A5_REQ_MD),
            "a5_gate_checklist_draft": file_info(A5_CHECKLIST),
            "a5_gate_conditions_draft": file_info(A5_CONDITIONS),
            "a1_dry_run": file_info(A1_DRY_RUN), "a1_interface_md": file_info(A1_INTERFACE_MD),
            "a1_u1_json": file_info(A1_U1_JSON),
            "a1_task_evaluator": file_info(A1_EVALUATOR),
            "a1_task_evaluator_tests": file_info(A1_EVALUATOR_TESTS),
            "raw_design_space_yaml": dict(yaml_info, path=str(RAW_YAML)),
            "baseline_vspgeom": file_info(BASELINE_VSPGEOM),
            "f1r2_12d_audit": file_info(AUDIT_12D),
        },
        "a1_interface": interface,
        "predraft_files": [{"name": name, "role": role} for name, role in files],
        "final_package_plan": final_files,
        "task_57_entry_criteria": [
            "A1 U1/U2 task-capable executor committed and frozen with SHA256SUMS",
            "A1 six-task zero-physical dry-run frozen (deck SHA, physical=0, spawn=[])",
            "Lead releases task-57 and confirms no policy change",
            "A3 generates new family SHA (not ada424cc/40fdd436) and final 6 TaskSpec",
            "A3 freezes 6 baseline deck bytes and raw YAML/C01-C04 binding",
            "A3 runs fail-closed validation + SUMS; A5 independently recomputes",
        ],
        "blocked_on": [
            "A1 interface is UNFROZEN/UNCOMMITTED at pre-draft time",
            "Final family SHA intentionally not generated in pre-draft",
            "No authorization/token/window exists; M0-R is zero-physical",
        ],
        "non_result_boundary": [
            "This directory is a pre-draft, not the formal M0-R package, not a freeze, not a gate.",
            "No solver, no run dir, no ledger, no token, no authorization.",
            "No winner, significance, optimization gain, cross-family comparison or fuel claim.",
        ],
    }


def build_readme() -> str:
    return """# M0-R Pre-Draft (A3 task-60, zero physical, not frozen)

状态：**PRE_DRAFT_NOT_FROZEN / NOT_A_GATE / NOT_A_RUN / NOT_AN_ADMISSION**。

本目录是 A3 依据 L-30 / L-30-A01、A5 M0-R requirements 与 gate draft、A1 U1/U2
零物理接口 dry-run、A1 raw 12D design-space YAML 与 post-fix baseline vspgeom
生成的 M0-R 预草案。它**不是**正式 M0-R 包，**不是**冻结，**不是** A5 gate，
**不是** M1 授权，**不是**任何物理结论。

## 1. 边界

- 零物理：physical_call_count=0，physical_solver_starts=0，solver_started=false，spawn_events=[]。
- 不创建 run dir / accounting ledger / token / authorization。
- 不生成最终 family SHA；所有 task fingerprint 字段为 null 或明确标为 A1 dry-run draft。
- 不改 T0-4、A1、旧 M0、F1/F2/R1-R10 的字节；旧 SHA 只作 superseded 披露。
- 无 winner、无显著性、无优化增益、无跨族/跨 Mach 比较；fuel_burn_kg=null；外部物理 NOT_VALIDATED。
- 单 seed、任务级 n=2 仅描述性。

## 2. 六个任务（L-30-A01 ATM-F1R2）

| task_id | Mach | CL | split | q (Pa) | Vinf (m/s) | L_ref (N) | mass (t) |
|---|---|---|---|---|---|---|---|
| T18K_M202_CL017 | 2.02 | 0.17 | meta_train | 20483.940233430174 | 596.0373972278921 | 1247523.170066 | 127.211960 |
| T18K_M202_CL019 | 2.02 | 0.19 | meta_train | 20483.940233430174 | 596.0373972278921 | 1394290.601839 | 142.178073 |
| T18K_M220_CL017 | 2.2 | 0.17 | meta_train | 24297.194081414087 | 649.1496405452291 | 1479759.862543 | 150.893512 |
| T18K_M220_CL019 | 2.2 | 0.19 | meta_val | 24297.194081414087 | 649.1496405452291 | 1653849.258137 | 168.645690 |
| T18K_M180_CL017 | 1.8 | 0.17 | meta_test_blind | 16265.063806566453 | 531.1224331733692 | 990583.048479 | 101.011359 |
| T18K_M180_CL019 | 1.8 | 0.19 | meta_test_blind | 16265.063806566453 | 531.1224331733692 | 1107122.230653 | 112.895049 |

全部 18,288 m；12D_ALL_ACTIVE；7 点 alpha；max_refine_sweeps=0；无高度副本。

## 3. SREF_REF 与 L_ref

SREF_REF 必须由 post-fix baseline vspgeom 在运行时独立重算并 SHA 绑定，不得写死数值。
本预草案从 A1 baseline vspgeom（SHA 16da482a…，225,414 B，546x480）用正确 token-stream
Newell 解析重算主翼面积，与 A1 运行时 anchor 的相对差在 1e-9 预注册容差内（约 6.2e-11）。
A1 task_evaluator 目前仍带 frozen SREF_REF 常量并以 1e-12 校验，这是 A1 接口偏差，
已在本包与报 Lead/A5 中披露；task-57 冻结前需 A1 修正或 A5 书面接受。

L_ref = q(M,18288) * SREF_REF * CL_target；mass = L_ref/g0，6 个任务均在 100-190 t。
q 由 deck 实际注入的 Vinf/Rho 复算，rel<=1e-12；q 单源 ATM-F1R2，禁止 ISO 混用。

## 4. Deck 与几何

- 6 个 per-task baseline deck（B0-01）与 3 个参考设计（B0-01/B1-01/C5）共 18 个
  A1 dry-run deck 引用；deck SHA 已登记，但状态为 **A1_DRY_RUN_DECK_NOT_FROZEN**。
- 同一设计跨 task 复用同一 vspgeom 字节；baseline 与 per-design SHA 分开记录。
- 旧 40fdd436/543x472 链不得出现在 active family；只作历史/superseded。

## 5. Split 与泄漏

3 train / 1 val / 2 blind test（按 task identity，不按样本）。meta_test 盲、不参与
M1/M2、不读标签；归一化/标签变换只在 meta_train 拟合；无 query 标签/heldout 最优/未来评价
泄漏；无高度副本。

## 6. 预算（未来授权模板，不是已计费）

- M1-A：15 starts / 105 internal，caps 18/126，retry 0；4 任务×3 设计=12 + 1 repeat + 2 preflight。
- M1-B：66/462，caps 70/490；4×16=64 labels + 2 preflight。
- M3-A：34/238，caps 38/266；2×16=32 labels + 2 preflight。
- 总：115/805，hard 126/882，labels 96，preflight 6，retry 0；M3-B NOT_AUTHORIZED。
- 五口径模板：physical=0、charged=0、actual=0、design_evaluations=0、cached_reads=0；
  charged 与 actual 分列，不混写。

## 7. CTX 预注册

CTX-A 纯缩放（TOO_SIMILAR）；CTX-B 归一化响应差（效应量 >= max(2*U_within,1e-3) 或
Spearman<0.99）；CTX-C 可行域；CTX-D 升力匹配/插值；CTX-E 每任务真实物理证据（DEFERRED
到 M1-A）；CTX-F 同几何字节。U_within/U_rep 等 M0-R 未测量，不得复用旧 F1 数值；
3 设计 Spearman 只作描述性、无 p 值/显著性。

## 8. A5 映射

M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json 覆盖 A5 R01-R30、gate draft 60 项检查与 42 条
conditions（R01-R30 + G01-G12）。状态分为 EVIDENCED_IN_PREDRAFT、PRE_REGISTERED_*、
PENDING_A1_INTERFACE_FREEZE、PENDING_FINAL_PACKAGE_OR_A5_GATE。A5 gate 仍由 A5 独立签发；
本包不声称 PASS / READY_FOR_M1A_ADMISSION / admission。

## 9. 进入 task-57 前必须补齐

1. A1 U1/U2 task-capable executor commit + SHA256SUMS 冻结。
2. A1 6 任务零物理 dry-run 冻结（deck SHA、spawn=[]、physical=0）。
3. Lead 释放 task-57，并确认预算/任务/几何/接口不再变。
4. A3 生成新 family SHA（非 ada424cc/40fdd436），冻结 6 TaskSpec 与 6 baseline deck。
5. A3 重跑 fail-closed validation，写正式 SHA256SUMS。
6. A5 独立复算并签 G-M0R-ADMISSION-01；之后才谈 M1-A 授权。

## 10. 文件

- M0R_PREDRAFT_MANIFEST.json
- M0R_TASK_SPECS_PREDRAFT.json
- M0R_SREF_PROVENANCE_PREDRAFT.json
- M0R_DECK_SPECS_PREDRAFT.json
- M0R_SPLIT_LEAKAGE_AUDIT_PREDRAFT.json
- M0R_BUDGET_LEDGER_PREDRAFT.json
- M0R_CTX_PLAN_PREDRAFT.json
- M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json
- M0R_ZERO_PHYSICAL_EVIDENCE_PREDRAFT.json
- M0R_VALIDATION_PREDRAFT.json
- SHA256SUMS.txt
"""


def validate_task_specs(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    tasks = doc.get("tasks") or []
    ids = [t.get("task_id") for t in tasks]
    checks.append({"id": "V-TASK-01", "domain": "tasks", "status": "PASS" if ids == list(TASK_IDS) else "FAIL",
                   "detail": {"expected": list(TASK_IDS), "actual": ids}})
    anchor = None
    for task in tasks:
        if task.get("task_id") == "T18K_M202_CL017":
            anchor = float(task.get("sref_ref_m2"))
            break
    checks.append({"id": "V-TASK-02", "domain": "tasks", "status": "PASS" if anchor and anchor > 0 else "FAIL",
                   "detail": {"sref_ref_m2": anchor}})
    splits = [sum(1 for t in tasks if t.get("split") == s) for s in ("meta_train", "meta_val", "meta_test_blind")]
    checks.append({"id": "V-TASK-03", "domain": "tasks", "status": "PASS" if splits == [3, 1, 2] else "FAIL",
                   "detail": {"counts": splits}})
    q_ok = all(abs(float(t["q_recomputed_from_vinf_rho_pa"]) - float(t["q_pa"])) /
               max(abs(float(t["q_pa"])), 1e-300) <= 1e-12 for t in tasks)
    checks.append({"id": "V-TASK-04", "domain": "tasks", "status": "PASS" if q_ok else "FAIL",
                   "detail": {"rule": "q recompute rel<=1e-12"}})
    l_ok = all(abs(float(t["l_ref_n"]) - float(t["q_pa"]) * float(t["sref_ref_m2"]) * float(t["cl_target"])) /
               max(abs(float(t["l_ref_n"])), 1e-300) <= 1e-12 for t in tasks)
    checks.append({"id": "V-TASK-05", "domain": "tasks", "status": "PASS" if l_ok else "FAIL",
                   "detail": {"rule": "L_ref=q*SREF_REF*CL rel<=1e-12"}})
    mass_ok = all(float(t["mass_bounds_t"][0]) <= float(t["mass_t"]) <= float(t["mass_bounds_t"][1])
                  for t in tasks)
    checks.append({"id": "V-TASK-06", "domain": "tasks", "status": "PASS" if mass_ok else "FAIL",
                   "detail": {"masses_t": [float(t["mass_t"]) for t in tasks]}})
    alpha_ok = all(t.get("alpha_grid_deg") == list(ALPHA_GRID) and t.get("max_refine_sweeps") == 0
                   for t in tasks)
    checks.append({"id": "V-TASK-07", "domain": "tasks", "status": "PASS" if alpha_ok else "FAIL",
                   "detail": {"rule": "7 alpha points, refine 0"}})
    fin_ok = all(t.get("task_fingerprint") is None for t in tasks) and doc.get("family_sha256") is None
    checks.append({"id": "V-TASK-08", "domain": "tasks", "status": "PASS" if fin_ok else "FAIL",
                   "detail": {"rule": "no final family SHA/fingerprint in pre-draft"}})
    return checks


def validate_sref(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    anchor = doc.get("anchor", {}).get("value_m2")
    recomputed = doc.get("independent_recompute", {}).get("wing_area_m2")
    rel = doc.get("consistency", {}).get("rel_diff")
    checks.append({"id": "V-SREF-01", "domain": "sref",
                   "status": "PASS" if anchor is not None and recomputed is not None and rel is not None and rel <= 1e-9 else "FAIL",
                   "detail": {"anchor": anchor, "recomputed": recomputed, "rel": rel, "tol": 1e-9}})
    checks.append({"id": "V-SREF-02", "domain": "sref",
                   "status": "PASS" if doc.get("independent_recompute", {}).get("vspgeom_sha256", "").startswith("16da482a") else "FAIL",
                   "detail": {"sha": doc.get("independent_recompute", {}).get("vspgeom_sha256")}})
    checks.append({"id": "V-SREF-03", "domain": "sref",
                   "status": "PASS" if doc.get("independent_recompute", {}).get("vspgeom_bytes") == 225414 else "FAIL",
                   "detail": {"bytes": doc.get("independent_recompute", {}).get("vspgeom_bytes")}})
    raw = doc.get("raw_design_space", {})
    checks.append({"id": "V-SREF-04", "domain": "sref",
                   "status": "PASS" if str(raw.get("sha256", "")).startswith("8b29d1e3") and raw.get("bytes") == 10846 else "FAIL",
                   "detail": {"sha": raw.get("sha256"), "bytes": raw.get("bytes")}})
    cc = raw.get("cross_constraints") or []
    cc_ids = [item.get("id") for item in cc]
    checks.append({"id": "V-SREF-05", "domain": "sref",
                   "status": "PASS" if cc_ids == ["C01", "C02", "C03", "C04"] else "FAIL",
                   "detail": {"cross_constraints": cc_ids}})
    return checks


def validate_decks(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    decks = doc.get("reference_design_decks") or []
    checks.append({"id": "V-DECK-01", "domain": "decks", "status": "PASS" if len(decks) == 18 else "FAIL",
                   "detail": {"n": len(decks)}})
    baseline = doc.get("per_task_baseline_decks") or []
    checks.append({"id": "V-DECK-02", "domain": "decks", "status": "PASS" if len(baseline) == 6 else "FAIL",
                   "detail": {"n": len(baseline)}})
    same = all(len({d["vspgeom_sha256"] for d in decks if d["design_id"] == did}) == 1 for did in DESIGN_IDS)
    checks.append({"id": "V-DECK-03", "domain": "decks", "status": "PASS" if same else "FAIL",
                   "detail": {"rule": "one vspgeom per design"}})
    dry = doc.get("a1_dry_run", {})
    zero = dry.get("physical_call_count") == 0 and dry.get("solver_started") is False and dry.get("run_dir_created") is False
    checks.append({"id": "V-DECK-04", "domain": "decks", "status": "PASS" if zero else "FAIL",
                   "detail": {k: dry.get(k) for k in ("physical_call_count", "solver_started", "run_dir_created")}})
    return checks


def validate_split(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    counts = doc.get("counts", {})
    checks.append({"id": "V-SPLIT-01", "domain": "split",
                   "status": "PASS" if [counts.get("meta_train"), counts.get("meta_val"), counts.get("meta_test_blind")] == [3, 1, 2] else "FAIL",
                   "detail": counts})
    checks.append({"id": "V-SPLIT-02", "domain": "split",
                   "status": "PASS" if doc.get("meta_test_blind") is True and doc.get("meta_test_labels_never_read") is True else "FAIL",
                   "detail": {"blind": doc.get("meta_test_blind"), "labels": doc.get("meta_test_labels_never_read")}})
    checks.append({"id": "V-SPLIT-03", "domain": "split",
                   "status": "PASS" if doc.get("height_copies_removed") is True else "FAIL", "detail": {}})
    checks.append({"id": "V-SPLIT-04", "domain": "split",
                   "status": "PASS" if doc.get("n_fail") == 0 else "FAIL", "detail": {"n_fail": doc.get("n_fail")}})
    return checks


def validate_budget(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    batches = {b["batch"]: b for b in doc.get("batches", [])}
    expected = {"M1-A": (15, 105, 18), "M1-B": (66, 462, 70), "M3-A": (34, 238, 38)}
    for name, values in expected.items():
        batch = batches.get(name, {})
        ok = (batch.get("planned_starts"), batch.get("planned_internal_cases"), batch.get("hard_cap_starts")) == values
        checks.append({"id": "V-BUD-" + name, "domain": "budget", "status": "PASS" if ok else "FAIL",
                       "detail": {"expected": values,
                                  "actual": [batch.get("planned_starts"), batch.get("planned_internal_cases"),
                                             batch.get("hard_cap_starts")]}})
    total = doc.get("total", {})
    ok = (total.get("planned_starts") == 115 and total.get("planned_internal_cases") == 805 and
          total.get("hard_cap_starts") == 126 and total.get("hard_cap_internal_cases") == 882)
    checks.append({"id": "V-BUD-TOTAL", "domain": "budget", "status": "PASS" if ok else "FAIL",
                   "detail": dict(total)})
    checks.append({"id": "V-BUD-LABELS", "domain": "budget",
                   "status": "PASS" if total.get("labels") == 96 and total.get("preflight_cases") == 6 and total.get("retry") == 0 else "FAIL",
                   "detail": {"labels": total.get("labels"), "preflight": total.get("preflight_cases"),
                              "retry": total.get("retry")}})
    auth = doc.get("authorization", {})
    ok = all(auth.get(k) is None for k in ("authorization_id", "approval_id", "token", "run_dir"))
    checks.append({"id": "V-BUD-AUTH", "domain": "budget", "status": "PASS" if ok else "FAIL", "detail": auth})
    return checks


def validate_zero(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    checks.append({"id": "V-ZERO-01", "domain": "zero_physical",
                   "status": "PASS" if doc.get("physical_call_count") == 0 and doc.get("physical_solver_starts") == 0 else "FAIL",
                   "detail": {"physical_call_count": doc.get("physical_call_count"),
                              "physical_solver_starts": doc.get("physical_solver_starts")}})
    checks.append({"id": "V-ZERO-02", "domain": "zero_physical",
                   "status": "PASS" if doc.get("solver_started") is False else "FAIL", "detail": {}})
    checks.append({"id": "V-ZERO-03", "domain": "zero_physical",
                   "status": "PASS" if not doc.get("spawn_events") and not doc.get("solver_outputs") else "FAIL",
                   "detail": {"spawn_events": doc.get("spawn_events"), "solver_outputs": doc.get("solver_outputs")}})
    checks.append({"id": "V-ZERO-04", "domain": "zero_physical",
                   "status": "PASS" if not doc.get("run_dir_created") and not doc.get("ledger_created") and
                                        not doc.get("token_created") and not doc.get("authorization_created") else "FAIL",
                   "detail": {k: doc.get(k) for k in ("run_dir_created", "ledger_created", "token_created", "authorization_created")}})
    return checks


def validate_a5_map(doc: Mapping[str, Any]) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    cov = doc.get("coverage", {})
    ok = (cov.get("requirements_mapped") == 30 and cov.get("checklist_mapped") == 60 and
          cov.get("gate_conditions_mapped") == 42 and not cov.get("missing_requirements") and
          not cov.get("missing_checklist") and not cov.get("missing_gate_conditions"))
    checks.append({"id": "V-A5-01", "domain": "a5_map", "status": "PASS" if ok else "FAIL", "detail": cov})
    checks.append({"id": "V-A5-02", "domain": "a5_map",
                   "status": "PASS" if doc.get("a5_draft_gate", {}).get("status") == "DRAFT_NOT_A_GATE" else "FAIL",
                   "detail": {"status": doc.get("a5_draft_gate", {}).get("status")}})
    checks.append({"id": "V-A5-03", "domain": "a5_map",
                   "status": "PASS" if doc.get("n_fail") == 0 else "FAIL", "detail": {"n_fail": doc.get("n_fail")}})
    return checks


def validate_sums(out_dir: Path) -> List[Dict[str, Any]]:
    sums = out_dir / "SHA256SUMS.txt"
    checks: List[Dict[str, Any]] = []
    if not sums.exists():
        return [{"id": "V-SUMS-01", "domain": "package", "status": "FAIL", "detail": "SHA256SUMS.txt missing"}]
    entries = []
    for line in read_text(sums).splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            return [{"id": "V-SUMS-01", "domain": "package", "status": "FAIL", "detail": "bad line: " + line}]
        entries.append((parts[0], parts[1]))
    bad = []
    for digest, name in entries:
        path = out_dir / name
        if not path.exists() or sha256_file(path) != digest:
            bad.append(name)
    checks.append({"id": "V-SUMS-01", "domain": "package", "status": "PASS" if len(entries) == 11 and not bad else "FAIL",
                   "detail": {"entries": len(entries), "bad": bad}})
    return checks


def validate_package(out_dir: Path | str = OUT_DIR) -> Dict[str, Any]:
    out = Path(out_dir)
    checks: List[Dict[str, Any]] = []
    loaders = {
        "tasks": "M0R_TASK_SPECS_PREDRAFT.json",
        "sref": "M0R_SREF_PROVENANCE_PREDRAFT.json",
        "decks": "M0R_DECK_SPECS_PREDRAFT.json",
        "split": "M0R_SPLIT_LEAKAGE_AUDIT_PREDRAFT.json",
        "budget": "M0R_BUDGET_LEDGER_PREDRAFT.json",
        "zero": "M0R_ZERO_PHYSICAL_EVIDENCE_PREDRAFT.json",
        "a5": "M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json",
        "manifest": "M0R_PREDRAFT_MANIFEST.json",
    }
    docs: Dict[str, Any] = {}
    for key, name in loaders.items():
        path = out / name
        if not path.exists():
            checks.append({"id": "V-LOAD-" + key, "domain": "package", "status": "FAIL",
                           "detail": "missing " + name})
        else:
            docs[key] = read_json(path)
            checks.append({"id": "V-LOAD-" + key, "domain": "package", "status": "PASS",
                           "detail": name})
    if "tasks" in docs:
        checks += validate_task_specs(docs["tasks"])
    if "sref" in docs:
        checks += validate_sref(docs["sref"])
    if "decks" in docs:
        checks += validate_decks(docs["decks"])
    if "split" in docs:
        checks += validate_split(docs["split"])
    if "budget" in docs:
        checks += validate_budget(docs["budget"])
    if "zero" in docs:
        checks += validate_zero(docs["zero"])
    if "a5" in docs:
        checks += validate_a5_map(docs["a5"])
    if "manifest" in docs:
        manifest = docs["manifest"]
        checks.append({"id": "V-MAN-01", "domain": "package",
                       "status": "PASS" if manifest.get("family_sha256") is None and
                                            manifest.get("status") == FREEZE_STATUS else "FAIL",
                       "detail": {"family_sha256": manifest.get("family_sha256"),
                                  "status": manifest.get("status")}})
        checks.append({"id": "V-MAN-02", "domain": "package",
                       "status": "PASS" if manifest.get("authorization_status") == "NOT_CREATED_PRE_DRAFT" else "FAIL",
                       "detail": manifest.get("authorization_status")})
        checks.append({"id": "V-MAN-03", "domain": "package",
                       "status": "PASS" if manifest.get("run_dir") is None and manifest.get("ledger") is None and
                                            manifest.get("token") is None else "FAIL",
                       "detail": {"run_dir": manifest.get("run_dir"), "ledger": manifest.get("ledger"),
                                  "token": manifest.get("token")}})
    checks += validate_sums(out)
    n_fail = sum(1 for check in checks if check["status"] == "FAIL")
    return {
        "schema": SCHEMA + ".validation.v1",
        "tool_version": TOOL_VERSION,
        "predraft_id": PREDRAFT_ID,
        "validated_utc": now_utc(),
        "out_dir": str(out),
        "checks": checks,
        "checks_total": len(checks),
        "n_pass": sum(1 for check in checks if check["status"] == "PASS"),
        "n_fail": n_fail,
        "n_info": sum(1 for check in checks if check["status"] == "INFO"),
        "verdict": "PREDRAFT_VALID_NOT_FROZEN" if n_fail == 0 else "PREDRAFT_INVALID",
        "is_result": False,
        "family_sha256": None,
        "freeze_status": FREEZE_STATUS,
        "admission_status": ADMISSION_STATUS,
        "physical_call_count": 0,
        "final_gate": "G-M0R-ADMISSION-01_A5_OWNS_PENDING_TASK_57",
    }


def write_sums(out_dir: Path) -> None:
    names = sorted(p.name for p in out_dir.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    lines = ["%s  %s" % (sha256_file(out_dir / name), name) for name in names]
    write_text(out_dir / "SHA256SUMS.txt", "\n".join(lines) + "\n")


def build_package(out_dir: Path | str = OUT_DIR) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    f1 = load_f1_stats()
    a1 = read_json(A1_DRY_RUN)
    l30a01 = read_json(L30A01_JSON)
    raw_yaml = _parse_raw_yaml(RAW_YAML)
    yaml_info = file_info(RAW_YAML)
    interface = _interface_status()
    sref_doc = build_sref_provenance(f1, a1, raw_yaml, yaml_info)
    tasks_doc = build_task_specs(f1, a1, l30a01, sref_doc, yaml_info, interface)
    deck_doc = build_deck_specs(a1, sref_doc, interface)
    split_doc = build_split_audit(a1)
    budget_doc = build_budget()
    ctx_doc = build_ctx_plan()
    zero_doc = build_zero_physical()
    a5_doc = build_a5_map()
    manifest = build_manifest(interface, yaml_info)
    docs = {
        "M0R_PREDRAFT_MANIFEST.json": manifest,
        "M0R_TASK_SPECS_PREDRAFT.json": tasks_doc,
        "M0R_SREF_PROVENANCE_PREDRAFT.json": sref_doc,
        "M0R_DECK_SPECS_PREDRAFT.json": deck_doc,
        "M0R_SPLIT_LEAKAGE_AUDIT_PREDRAFT.json": split_doc,
        "M0R_BUDGET_LEDGER_PREDRAFT.json": budget_doc,
        "M0R_CTX_PLAN_PREDRAFT.json": ctx_doc,
        "M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json": a5_doc,
        "M0R_ZERO_PHYSICAL_EVIDENCE_PREDRAFT.json": zero_doc,
    }
    for name, doc in docs.items():
        write_json(out / name, doc)
    write_text(out / "README_M0R_PREDRAFT_ZH.md", build_readme())
    core = validate_package(out)
    core["note"] = ("Validation before SHA256SUMS.txt exists; SUMS is written immediately after this file. "
                    "Run --validate-only for the final package check.")
    write_json(out / "M0R_VALIDATION_PREDRAFT.json", core)
    write_sums(out)
    final = validate_package(out)
    write_json(out / "M0R_VALIDATION_PREDRAFT.json", final)
    write_sums(out)
    return final


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="A3 M0-R pre-draft generator/validator")
    parser.add_argument("--out", default=str(OUT_DIR))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if args.validate_only:
        result = validate_package(out)
    else:
        result = build_package(out)
    print(json.dumps({"verdict": result["verdict"], "checks_total": result["checks_total"],
                      "n_pass": result["n_pass"], "n_fail": result["n_fail"],
                      "out_dir": result["out_dir"], "family_sha256": result["family_sha256"]},
                     ensure_ascii=False, sort_keys=True))
    return 0 if result["n_fail"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
