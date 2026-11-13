#!/usr/bin/env python3
"""A3 M0-R formal package generator (task-57, zero physical).

Builds the formal M0-R package from the A1 frozen U1/U2 interface, the L-30 /
L-30-A01 task contract, the A5 M0-R requirements, and the A3 pre-draft.

New family SHA is computed from six new A3 TaskSpec identities; ada424cc and
40fdd436 are retired.  No run dir, ledger, token, authorization or solver start.

CLI:
    python m0r_package.py --build
    python m0r_package.py --validate-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import m0r_predraft as pd

TOOL_VERSION = "a3-m0r-package-v1.0.0"
SCHEMA = "dreal001.m0r_package.v1"
PACKAGE_ID = "DREAL001-M0R-20261113-01"
PACKAGE_STATUS = "M0R_PACKAGE_FROZEN_PENDING_A5_GATE"
FAMILY_SCHEMA = "dreal001.m0r_family.v1"
TASK_IDENTITY_SCHEMA = "dreal001.m0r_task_identity.v1"
A5_GATE_ID = "G-M0R-ADMISSION-01"
OLD_PREFIXES = ("ada424cc", "40fdd436")
A1_CLARIFY = pd.A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_interface_clarification_20261113.json"
A1_CLARIFY_MD = pd.A1 / "docs" / "receipts" / "dreal001" / "a1_m0r_interface_clarification_20261113.md"

FINAL_IDS = [
    "M0R-M202-CL017",
    "M0R-M202-CL019",
    "M0R-M220-CL017",
    "M0R-M220-CL019",
    "M0R-M180-CL017",
    "M0R-M180-CL019",
]

PACKAGE_DIR = pd.A3 / "docs" / "evidence" / "dreal001" / "m0r_20261113"
PRE = PACKAGE_DIR / "pre_draft"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                     indent=2, sort_keys=True) + "\n", encoding="utf-8")


def info(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    data = p.read_bytes()
    return {"path": str(p).replace("\\", "/"), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def finalize_tasks(pred: Mapping[str, Any]) -> Dict[str, Any]:
    tasks = []
    for index, source in enumerate(pred["tasks"]):
        task = json.loads(json.dumps(source, ensure_ascii=False))
        task["a1_task_id"] = task["task_id"]
        task["a1_interface_task_fingerprint"] = task.pop("a1_draft_task_fingerprint")
        task["a1_interface_task_fingerprint_status"] = (
            "A1_FROZEN_TEMPORARY_TASK_ID_FINGERPRINT_MAPPED_TO_A3_FINAL_ID")
        task["task_id"] = FINAL_IDS[index]
        task["task_id_status"] = "NEW_M0R_ID_NOT_REUSED_FROM_OLD_18_TASK_FAMILY"
        identity = {
            "schema": TASK_IDENTITY_SCHEMA,
            "task_id": task["task_id"],
            "mach": task["mach"],
            "altitude_m": task["altitude_m"],
            "cl_target": task["cl_target"],
            "q_pa": task["q_pa"],
            "vinf_m_s": task["vinf_m_s"],
            "rho_kg_m3": task["rho_kg_m3"],
            "recref": task["recref"],
            "sref_ref_m2": task["sref_ref_m2"],
            "l_ref_n": task["l_ref_n"],
            "mass_t": task["mass_t"],
            "alpha_grid_deg": task["alpha_grid_deg"],
            "max_refine_sweeps": task["max_refine_sweeps"],
            "active_mask": task["active_mask"],
            "solver_version": task["solver"]["solver_version"],
            "openvsp_version": task["solver"]["openvsp_version"],
            "baseline_vspgeom_sha256": task["geometry"]["baseline_vspgeom_sha256"],
            "openvsp_geometry_sha256": task["geometry"]["openvsp_geometry_sha256"],
            "raw_design_space_sha256": task["design_space"]["raw_yaml_sha256"],
            "a1_task_evaluator_sha256": task["evaluator"]["a1_task_evaluator_sha256"],
        }
        task["task_fingerprint"] = sha_text(canonical(identity))
        task["task_fingerprint_algorithm"] = (
            "sha256(canonical JSON of dreal001.m0r_task_identity.v1; split excluded)")
        task["task_fingerprint_status"] = "FROZEN_FINAL"
        task["sref_ref_role"] = "VALIDATION_ANCHOR_ONLY_NOT_A_RUNTIME_HARDCODE"
        task["runtime_sref_policy"] = {
            "runtime_recompute_required": True,
            "runtime_source": "post-fix baseline geometry.wing.area_m2 recomputed at runtime",
            "runtime_binding": "post-fix baseline vspgeom SHA256 + recomputed value SHA256",
            "hardcode_forbidden": True,
            "anchor_value_used_only_for_validation": task["sref_ref_m2"],
        }
        task["schema"] = SCHEMA + ".task_spec.v1"
        task["status"] = PACKAGE_STATUS
        tasks.append(task)
    family_payload = {
        "schema": FAMILY_SCHEMA,
        "n_tasks": len(tasks),
        "task_set": [{"task_id": t["task_id"], "task_fingerprint": t["task_fingerprint"]}
                     for t in tasks],
        "sref_ref_m2": tasks[0]["sref_ref_m2"],
        "baseline_vspgeom_sha256": tasks[0]["geometry"]["baseline_vspgeom_sha256"],
        "openvsp_geometry_sha256": tasks[0]["geometry"]["openvsp_geometry_sha256"],
        "raw_design_space_sha256": tasks[0]["design_space"]["raw_yaml_sha256"],
        "a1_task_evaluator_sha256": tasks[0]["evaluator"]["a1_task_evaluator_sha256"],
        "solver": {"solver_version": "7.2.2", "openvsp_version": "3.55.0"},
    }
    family_sha = sha_text(canonical(family_payload))
    splits = {
        "meta_train": [t["task_id"] for t in tasks if t["split"] == "meta_train"],
        "meta_val": [t["task_id"] for t in tasks if t["split"] == "meta_val"],
        "meta_test_blind": [t["task_id"] for t in tasks if t["split"] == "meta_test_blind"],
    }
    checks = [
        {"id": "M0R-TASK-01", "description": "six final tasks in L-30-A01 order",
         "status": "PASS" if len(tasks) == 6 else "FAIL"},
        {"id": "M0R-TASK-02", "description": "3 train / 1 val / 2 blind test",
         "status": "PASS" if [len(splits[k]) for k in ("meta_train", "meta_val", "meta_test_blind")] == [3, 1, 2] else "FAIL"},
        {"id": "M0R-TASK-03", "description": "q recomputes rel<=1e-12",
         "status": "PASS" if all(t["q_recompute_rel_error"] <= 1e-12 for t in tasks) else "FAIL"},
        {"id": "M0R-TASK-04", "description": "L_ref=q*SREF_REF*CL rel<=1e-12",
         "status": "PASS" if all(abs(t["l_ref_n"] - t["q_pa"] * t["sref_ref_m2"] * t["cl_target"]) /
                                 max(abs(t["l_ref_n"]), 1e-300) <= 1e-12 for t in tasks) else "FAIL"},
        {"id": "M0R-TASK-05", "description": "mass 100-190 t",
         "status": "PASS" if all(100.0 <= t["mass_t"] <= 190.0 for t in tasks) else "FAIL"},
        {"id": "M0R-TASK-06", "description": "7 alpha points and max_refine_sweeps=0",
         "status": "PASS" if all(t["alpha_grid_deg"] == list(pd.ALPHA_GRID) and
                                 t["max_refine_sweeps"] == 0 for t in tasks) else "FAIL"},
        {"id": "M0R-TASK-07", "description": "new family SHA, not old ada424cc/40fdd436",
         "status": "PASS" if len(family_sha) == 64 and not family_sha.startswith(OLD_PREFIXES) else "FAIL"},
        {"id": "M0R-TASK-08", "description": "task IDs are new M0-R IDs with A1 mapping",
         "status": "PASS" if all(t["task_id"] in FINAL_IDS and t["a1_task_id"] for t in tasks) else "FAIL"},
    ]
    return {
        "schema": SCHEMA + ".task_specs.v1",
        "tool_version": TOOL_VERSION,
        "package_id": PACKAGE_ID,
        "status": PACKAGE_STATUS,
        "family_sha256": family_sha,
        "family_sha256_algorithm": "sha256(canonical JSON of dreal001.m0r_family.v1)",
        "family_payload_sha256_input": family_payload,
        "family_sha256_status": "FROZEN_NEW_FAMILY_NOT_OLD",
        "old_family_sha256_retired": ["ada424cc...", "40fdd436..."],
        "n_tasks": len(tasks),
        "task_ids": [t["task_id"] for t in tasks],
        "splits": splits,
        "tasks": tasks,
        "checks": checks,
        "n_fail": sum(1 for c in checks if c["status"] == "FAIL"),
        "non_result_boundary": [
            "Frozen contract only; no real label, run, admission or physics validation.",
            "New family SHA; old 18-task family ada424cc and old geometry 40fdd436 retired.",
            "Zero physical: no solver was started.",
        ],
    }


def build_decks(pred_decks: Mapping[str, Any], tasks: Mapping[str, Any]) -> Dict[str, Any]:
    dry = read_json(pd.A1_DRY_RUN)
    out = PACKAGE_DIR / "decks"
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    checks = []
    baseline_by_final: Dict[str, Dict[str, Any]] = {}
    for deck in dry["decks"]:
        if deck["design_id"] != "B0-01":
            continue
        task_id = deck["task_id"]
        index = list(pd.TASK_IDS).index(task_id)
        final_id = FINAL_IDS[index]
        case_dir = Path(pd.A1) / deck["case_dir"].replace("\\", "/")
        src_deck = case_dir / "concorde_baseline.vspaero"
        src_meta = case_dir / "task_deck.json"
        dst = out / final_id
        dst.mkdir(parents=True, exist_ok=True)
        if not src_deck.exists() or not src_meta.exists():
            checks.append({"id": "M0R-DECK-" + final_id, "status": "FAIL",
                           "detail": "missing A1 deck source"})
            continue
        shutil.copy2(src_deck, dst / "concorde_baseline.vspaero")
        shutil.copy2(src_meta, dst / "task_deck.json")
        deck_sha = sha_file(dst / "concorde_baseline.vspaero")
        meta_sha = sha_file(dst / "task_deck.json")
        ok = deck_sha == deck["deck_sha256"] and (dst / "concorde_baseline.vspaero").stat().st_size == deck["deck_bytes"]
        checks.append({"id": "M0R-DECK-" + final_id, "status": "PASS" if ok else "FAIL",
                       "detail": {"a1_expected": deck["deck_sha256"], "package_actual": deck_sha,
                                  "bytes": (dst / "concorde_baseline.vspaero").stat().st_size}})
        entry = {
            "task_id": final_id,
            "a1_task_id": task_id,
            "design_id": deck["design_id"],
            "design_hash": deck["design_hash"],
            "vspgeom_sha256": deck["vspgeom_sha256"],
            "sref_m2": deck["sref_m2"],
            "q_pa": deck["q_pa"],
            "l_ref_n": deck["l_ref_n"],
            "mass_t": deck["mass_t"],
            "cl_required": deck["cl_required"],
            "a1_deck_sha256": deck["deck_sha256"],
            "a1_deck_bytes": deck["deck_bytes"],
            "package_deck_path": str((dst / "concorde_baseline.vspaero").relative_to(PACKAGE_DIR)).replace("\\", "/"),
            "package_deck_sha256": deck_sha,
            "package_deck_bytes": (dst / "concorde_baseline.vspaero").stat().st_size,
            "package_task_deck_path": str((dst / "task_deck.json").relative_to(PACKAGE_DIR)).replace("\\", "/"),
            "package_task_deck_sha256": meta_sha,
            "package_task_deck_bytes": (dst / "task_deck.json").stat().st_size,
            "solver_input_sha256": deck["solver_input_sha256"],
            "solver_input_sha256_role": "PATH_DEPENDENT_NOT_A_CROSS_PROCESS_EXPECTED",
            "cross_process_deck_identity": {
                "deck_sha256": deck["deck_sha256"],
                "vspgeom_sha256": deck["vspgeom_sha256"],
                "note": "vkey path is path-dependent; use deck_sha256 plus vspgeom_sha256 for cross-process identity",
            },
            "status": "FROZEN_IN_M0R_PACKAGE",
        }
        entries.append(entry)
        baseline_by_final[final_id] = entry

    design_order = ("B0-01", "B1-01", "C5")
    a1_to_final = {t["a1_task_id"]: t["task_id"] for t in tasks["tasks"]}
    final_to_split = {t["task_id"]: t["split"] for t in tasks["tasks"]}
    by_key = {(d["task_id"], d["design_id"]): d for d in dry["decks"]}
    expected_keys = {((a1_id, design_id)) for a1_id in pd.TASK_IDS for design_id in design_order}
    checks.append({"id": "M0R-DECK-SOURCE-18", "status": "PASS" if set(by_key) == expected_keys else "FAIL",
                   "detail": {"source_entries": len(by_key), "expected_keys": len(expected_keys),
                              "missing": sorted(str(k) for k in expected_keys - set(by_key))}})

    def family_entry(a1_id: str, final_id: str, design_id: str) -> Dict[str, Any]:
        d = by_key[(a1_id, design_id)]
        frozen = design_id == "B0-01"
        entry = {
            "task_id": final_id,
            "a1_task_id": a1_id,
            "task_split": final_to_split[final_id],
            "design_id": design_id,
            "design_hash": d["design_hash"],
            "vspgeom_sha256": d["vspgeom_sha256"],
            "deck_sha256": d["deck_sha256"],
            "deck_bytes": d["deck_bytes"],
            "frozen_status": "FROZEN_IN_M0R_PACKAGE_BASELINE" if frozen else "UNFROZEN_REFERENCE",
            "deck_sha256_status": "FROZEN_PACKAGE_BASELINE" if frozen else "REFERENCE_HASH_NOT_FROZEN",
        }
        if frozen:
            base = baseline_by_final[final_id]
            entry["package_deck_path"] = base["package_deck_path"]
            entry["package_deck_sha256"] = base["package_deck_sha256"]
            entry["package_deck_bytes"] = base["package_deck_bytes"]
        return entry

    full_family = []
    for design_id in design_order:
        for a1_id, final_id in zip(pd.TASK_IDS, FINAL_IDS):
            full_family.append(family_entry(a1_id, final_id, design_id))
    reference_unfrozen = [e for e in full_family if e["frozen_status"] == "UNFROZEN_REFERENCE"]

    m1a = []
    for a1_id, final_id in zip(pd.TASK_IDS, FINAL_IDS):
        split = final_to_split[final_id]
        if split not in ("meta_train", "meta_val"):
            continue
        for design_id in design_order:
            e = family_entry(a1_id, final_id, design_id)
            frozen = design_id == "B0-01"
            m1a.append({
                "task_id": final_id,
                "a1_task_id": a1_id,
                "task_split": split,
                "design_id": design_id,
                "design_hash": e["design_hash"],
                "deck_sha256": e["deck_sha256"],
                "vspgeom_sha256": e["vspgeom_sha256"],
                "frozen_status": "FROZEN_IN_M0R_PACKAGE" if frozen else "TO_BE_FROZEN_BEFORE_M1A_AUTHORIZATION",
                "freeze_deadline": "ALREADY_FROZEN" if frozen else "BEFORE_M1A_AUTHORIZATION",
                "deck_sha256_status": e["deck_sha256_status"],
            })

    m3a = []
    for a1_id, final_id in zip(pd.TASK_IDS, FINAL_IDS):
        split = final_to_split[final_id]
        if split != "meta_test_blind":
            continue
        for design_id in ("B1-01", "C5"):
            e = family_entry(a1_id, final_id, design_id)
            m3a.append({
                "task_id": final_id,
                "a1_task_id": a1_id,
                "task_split": split,
                "design_id": design_id,
                "design_hash": e["design_hash"],
                "deck_sha256": e["deck_sha256"],
                "vspgeom_sha256": e["vspgeom_sha256"],
                "frozen_status": "TO_BE_FROZEN_BEFORE_M3A",
                "freeze_deadline": "BEFORE_M3A",
                "deck_sha256_status": "REFERENCE_HASH_NOT_FROZEN",
            })

    n_m1a_b0 = sum(1 for e in m1a if e["frozen_status"] == "FROZEN_IN_M0R_PACKAGE")
    n_m1a_to_freeze = len(m1a) - n_m1a_b0
    checks.extend([
        {"id": "M0R-DECK-FAMILY-18", "status": "PASS" if len(full_family) == 18 else "FAIL",
         "detail": {"entries": len(full_family)}},
        {"id": "M0R-DECK-REFERENCE-12", "status": "PASS" if len(reference_unfrozen) == 12 else "FAIL",
         "detail": {"reference_entries": len(reference_unfrozen)}},
        {"id": "M0R-DECK-M1A-12", "status": "PASS" if len(m1a) == 12 and n_m1a_b0 == 4 and n_m1a_to_freeze == 8 else "FAIL",
         "detail": {"m1a_slots": len(m1a), "b0_frozen": n_m1a_b0, "to_freeze_before_m1a": n_m1a_to_freeze}},
        {"id": "M0R-DECK-M3A-4", "status": "PASS" if len(m3a) == 4 else "FAIL",
         "detail": {"m3a_reference_slots": len(m3a)}},
    ])
    return {
        "schema": SCHEMA + ".deck_freeze.v1",
        "tool_version": TOOL_VERSION,
        "package_id": PACKAGE_ID,
        "status": PACKAGE_STATUS,
        "revision": "r3",
        "revision_note": ("r3 minimal metadata revision: full family deck space is 18 = 3 designs x 6 tasks; "
                          "6 B0-01 baseline decks frozen; 12 B1-01/C5 reference entries unfrozen; "
                          "M1-A requires 12 slots = 4 M1 tasks x 3 designs (4 frozen B0 + 8 B1/C5 to freeze); "
                          "4 meta_test B1/C5 slots to freeze before M3-A. No deck byte changed."),
        "a1_interface": {
            "code_commit": pd.A1_CODE_COMMIT,
            "freeze_commit": pd.A1_FREEZE_COMMIT,
            "dry_run": info(pd.A1_DRY_RUN),
            "freeze_json": info(pd.A1_FREEZE_JSON),
            "dry_run_verdict": dry["verdict"],
            "checks_total": dry["checks_total"],
            "checks_failed": dry["checks_failed"],
            "physical_call_count": dry["physical_call_count"],
            "solver_started": dry["solver_started"],
            "run_dir_created": dry["run_dir_created"],
        },
        "n_package_baseline_decks": len(entries),
        "baseline_task_decks": entries,
        "n_full_family_deck_space_entries": len(full_family),
        "full_family_deck_space": full_family,
        "n_reference_design_deck_entries_unfrozen": len(reference_unfrozen),
        "reference_design_decks_unfrozen_reference": reference_unfrozen,
        "m1a_required_deck_set_label": "M1-A_REQUIRED_DECK_SET",
        "m1a_required_deck_set": m1a,
        "m3a_reference_deck_set": m3a,
        "freeze_boundary": {
            "full_family_designs": ["B0-01", "B1-01", "C5"],
            "full_family_design_count": 3,
            "full_family_task_count": 6,
            "full_family_deck_space_entries": 18,
            "baseline_design": "B0-01",
            "baseline_decks_frozen": 6,
            "reference_design_deck_entries": 12,
            "reference_design_deck_entries_frozen": 0,
            "reference_design_deck_entries_unfrozen": 12,
            "m1a_task_count": 4,
            "m1a_required_deck_slots": 12,
            "m1a_baseline_slots_already_frozen": 4,
            "m1a_reference_slots_to_freeze_before_authorization": 8,
            "m3a_meta_test_task_count": 2,
            "m3a_reference_slots_to_freeze_before_m3a": 4,
            "policy": ("18 = 3 designs (B0-01, B1-01, C5) x 6 tasks. The 6 B0-01 baseline decks are frozen "
                       "in this package. The 12 B1-01/C5 reference entries are unfrozen reference. M1-A "
                       "requires 12 deck slots = 4 M1 tasks (3 meta_train + 1 meta_val) x 3 designs; the 4 "
                       "B0-01 slots are already frozen, and the 8 B1-01/C5 slots must be frozen or "
                       "deterministically regenerated before M1-A authorization. The remaining 4 B1/C5 "
                       "meta_test slots must be frozen before M3-A. Unfrozen reference decks must not be "
                       "used for physical execution. No deck byte is changed by this metadata revision."),
        },
        "checks": checks,
        "n_fail": sum(1 for c in checks if c["status"] == "FAIL"),
        "non_result_boundary": [
            "Deck bytes frozen for A5 review, not executed.",
            "No VSPAERO start; only OpenVSP in-process geometry build happened in A1 dry-run.",
        ],
    }


def build_design_space(sref: Mapping[str, Any]) -> Dict[str, Any]:
    raw = sref["raw_design_space"]
    task_ds = read_json(PRE / "M0R_TASK_SPECS_PREDRAFT.json")["tasks"][0]["design_space"]
    variables = raw.get("variables") or task_ds.get("variables")
    fixed_variables = raw.get("fixed_variables") or task_ds.get("fixed_variables")
    checks = [
        {"id": "M0R-DS-01", "description": "raw YAML SHA 8b29d1e3",
         "status": "PASS" if str(raw.get("sha256", "")).startswith("8b29d1e3") else "FAIL"},
        {"id": "M0R-DS-02", "description": "raw YAML 10,846 bytes",
         "status": "PASS" if raw.get("bytes") == 10846 else "FAIL"},
        {"id": "M0R-DS-03", "description": "C01-C04 present",
         "status": "PASS" if [c.get("id") for c in raw.get("cross_constraints") or []] == ["C01", "C02", "C03", "C04"] else "FAIL"},
        {"id": "M0R-DS-04", "description": "12 design variables present",
         "status": "PASS" if len(variables or []) == 12 else "FAIL"},
        {"id": "M0R-DS-05", "description": "A1 interface does not substitute for C01-C04",
         "status": "PASS"},
    ]
    return {
        "schema": SCHEMA + ".design_space_binding.v1",
        "tool_version": TOOL_VERSION,
        "package_id": PACKAGE_ID,
        "status": PACKAGE_STATUS,
        "raw_yaml": {k: raw.get(k) for k in ("path", "sha256", "bytes", "schema_version",
                                             "design_set", "frozen", "bounds_status", "parse_mode")},
        "variables_12": variables,
        "fixed_variables": fixed_variables,
        "cross_constraints": raw.get("cross_constraints"),
        "enforcement": {
            "required_in_m1_sampler_and_executor": True,
            "a1_interface_does_not_substitute": True,
            "disclosure": ("A1 states explicitly that C01-C04 cross constraints are enforced by the A3 "
                           "M0-R package plus the A2 runner; the A1 task evaluator does not substitute for "
                           "cross-constraint enforcement."),
            "negative_case_required_in_m1": True,
        },
        "checks": checks,
        "n_fail": sum(1 for c in checks if c["status"] == "FAIL"),
        "non_result_boundary": ["Binding only; no design-space expansion or evaluation in M0-R."],
    }


def build_a1_binding() -> Dict[str, Any]:
    entries = []
    for line in Path(pd.A1_SHA256SUMS).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            raise ValueError("bad A1 SUMS line: " + line)
        entries.append({"sha256": parts[0], "bytes": int(parts[1]), "path": parts[2]})
    expected = {
        "evaluator": "e88c2177",
        "tests": "290485ce",
        "conftest": "53a678b4",
        "interface": "6ef6b16e",
        "dry_run": "8688d257",
        "u1": "d90f2ed5",
        "pytest_log": "3c8f15fa",
    }
    checks = [
        {"id": "M0R-A1-01", "description": "A1 SHA256SUMS 7 entries",
         "status": "PASS" if len(entries) == 7 else "FAIL"},
        {"id": "M0R-A1-02", "description": "A1 SHA256SUMS SHA 3ca22ec9",
         "status": "PASS" if sha_file(pd.A1_SHA256SUMS) == pd.A1_SUMS_SHA256 else "FAIL"},
        {"id": "M0R-A1-03", "description": "frozen expected digests present",
         "status": "PASS" if all(any(e["sha256"].startswith(prefix) for e in entries) for prefix in expected.values()) else "FAIL"},
        {"id": "M0R-A1-04", "description": "freeze json source commit 0c51415",
         "status": "PASS" if read_json(pd.A1_FREEZE_JSON).get("source_commit") == pd.A1_CODE_COMMIT else "FAIL"},
    ]
    return {
        "schema": SCHEMA + ".a1_interface_binding.v1",
        "tool_version": TOOL_VERSION,
        "package_id": PACKAGE_ID,
        "status": PACKAGE_STATUS,
        "a1_code_commit": pd.A1_CODE_COMMIT,
        "a1_freeze_commit": pd.A1_FREEZE_COMMIT,
        "a1_sha256sums": info(pd.A1_SHA256SUMS),
        "a1_sha256sums_entries": entries,
        "a1_freeze_json": info(pd.A1_FREEZE_JSON),
        "a1_freeze_md": info(pd.A1_FREEZE_MD),
        "a1_dry_run": info(pd.A1_DRY_RUN),
        "a1_interface_md": info(pd.A1_INTERFACE_MD),
        "a1_task_evaluator": info(pd.A1_EVALUATOR),
        "a1_task_evaluator_tests": info(pd.A1_EVALUATOR_TESTS),
        "a1_conftest": info(pd.A1_CONFTEST),
        "a1_pytest_log": info(pd.A1_PYTEST_LOG),
        "a1_clarification": {
            "commit": "e659f15d826de0c55bcfe02944a97a28ba50b824",
            "json": info(A1_CLARIFY),
            "md": info(A1_CLARIFY_MD),
            "covers": ["CL-1_SREF","CL-2_solver_input","CL-3_F1R2_continuity"],
            "sums_coverage": "original 7 frozen files only; clarification is an addendum, not part of SUMS",
            "frozen_bytes_unchanged": True,
            "a5_status": "A5_ACCEPTED_AUTHORITATIVE",
            "required_m0r_wording_zh": {
                "CL-1-SREF": "SREF_REF 以 post-fix baseline 几何运行时重算值为唯一来源（本次 358.25000000000006），冻结常量仅作 1e-12 校验锚；不得把 358.25 作为计算输入硬编码。",
                "CL-2-SOLVER-INPUT-SHA": "solver_input_sha256 含 path-dependent/random 的 .vkey，跨进程不可复现；确定性绑定只用 deck_sha256 + vspgeom_sha256（加 solver_sha256/task_fingerprint），vkey 与 input_sha 按 run 记录，不作跨进程 expected。",
                "CL-3-F1R2-CONTINUITY": "M2.02 仅物理条件与 F1R2 逐位连续（q=20483.940233430174，Mach/Vinf/Rho/ReCref/alpha 网格相同），deck 字节不相等（A1 943B/LF vs F1R2 985B/CRLF，43 行规范化后相同）；不继承 F1R2 expected polar，M1-A 重建 admission baseline。",
            },
        },
        "checks": checks,
        "n_fail": sum(1 for c in checks if c["status"] == "FAIL"),
        "task_id_mapping": {
            "policy": ("A1 used temporary T18K task IDs. A3 final IDs are new M0R IDs; each TaskSpec "
                       "keeps a1_task_id and the A1 interface fingerprint for traceability."),
        },
        "non_result_boundary": [
            "Binding is to A1 frozen interface bytes; no A1 source byte was modified by A3.",
        ],
    }


def build_a5(pred_a5: Mapping[str, Any], family_sha: str) -> Dict[str, Any]:
    doc = json.loads(json.dumps(pred_a5, ensure_ascii=False))
    for req in doc["requirements_30"]:
        rid = req["id"]
        if rid == "R28":
            req["pre_draft_status"] = "PENDING_A5_GATE"
        elif rid == "R18":
            req["pre_draft_status"] = "A5_ACTION_PENDING"
        elif rid in ("R10", "R11"):
            req["pre_draft_status"] = "PRE_REGISTERED_PENDING_M1A_MEASUREMENT"
        elif rid in ("R12", "R13", "R14", "R15"):
            req["pre_draft_status"] = "PRE_REGISTERED_BUDGET"
        else:
            req["pre_draft_status"] = "EVIDENCED_IN_FORMAL_PACKAGE"
    for check in doc["gate_checklist_60"]:
        if check.get("category") in ("gate", "process", "gate_input"):
            check["pre_draft_status"] = "PENDING_A5_GATE"
        else:
            check["pre_draft_status"] = "EVIDENCED_IN_FORMAL_PACKAGE"
    for cond in doc["gate_conditions_42"]:
        cond["pre_draft_status"] = ("EVIDENCED_IN_FORMAL_PACKAGE"
                                    if cond["id"] in ("G03", "G05", "G08", "G09", "G10")
                                    else "PENDING_A5_GATE")
    doc["status"] = PACKAGE_STATUS
    doc["package_id"] = PACKAGE_ID
    doc["family_sha256"] = family_sha
    doc["a5_draft_gate"]["status"] = "DRAFT_NOT_A_GATE_FORMAL_PACKAGE_READY"
    doc["gate_boundary"] = [
        "Formal package is frozen for A5 independent recomputation; A5 owns the gate.",
        "No A5 PASS or admission is claimed by A3.",
        "M1 remains unauthorized until A5 gate and Lead GO.",
    ]
    doc["a5_wording_corrections"] = {
        "sref_runtime_is_only_source": True,
        "sref_ref_frozen_is_anchor_constant_only": True,
        "solver_input_sha256_is_path_dependent_not_cross_process_expected": True,
        "cross_process_deck_identity": "deck_sha256 + vspgeom_sha256",
        "m202_continuity_is_q_physics_only_not_deck_bytes": True,
        "m202_does_not_inherit_f1r2_expected_polar": True,
        "m1a_rebuilds_admission_baseline": True,
        "evidence": ["M0R_SREF_PROVENANCE.json", "M0R_DECK_FREEZE.json",
                     "M0R_PREREGISTRATION_ZH.md", "README_ZH.md"],
    }
    doc["coverage_checks"] = doc.get("coverage_checks") or []
    doc["n_fail"] = sum(1 for c in doc["coverage_checks"] if c.get("status") == "FAIL")
    return doc


def build_stat() -> Dict[str, Any]:
    return {
        "schema": SCHEMA + ".stat_endpoints.v1",
        "tool_version": TOOL_VERSION,
        "package_id": PACKAGE_ID,
        "status": PACKAGE_STATUS,
        "primary_metric": {
            "id": "D_I_N",
            "name": "independent drag force per task/design",
            "formula": "D_i_N = q * Sref(x) * CDi(lift_matched)",
            "q_source": "ATM-F1R2 injected Vinf/Rho",
            "sref_source": "per-design geometry runtime recompute; frozen SREF_REF is validation anchor only",
            "sref_ref_anchor_role": "VALIDATION_ANCHOR_ONLY_NOT_A_RUNTIME_HARDCODE",
            "forbidden": ["0.5*(f1+f2)", "hardcoded Sref", "cross-family averaging"],
            "physical_validation_status": "NOT_VALIDATED",
            "fuel_burn_kg": None,
        },
        "endpoints": [
            {"id": "EP-01", "name": "per task/design D_i_N", "status": "PRE_REGISTERED_FOR_M1",
             "computation": "q*Sref*CDi at lift-matched alpha", "winner_claim_allowed": False},
            {"id": "EP-02", "name": "lift residual", "status": "PRE_REGISTERED_FOR_M1",
             "computation": "abs(L-L_ref)/L_ref <= 1e-4", "winner_claim_allowed": False},
            {"id": "EP-03", "name": "alpha-star and CL-alpha quality",
             "status": "PRE_REGISTERED_FOR_M1",
             "computation": "7 finite SOLVED points; OLS R2>=0.99; independent alpha-star",
             "winner_claim_allowed": False},
            {"id": "EP-04", "name": "feasible rate", "status": "PRE_REGISTERED_FOR_M1",
             "computation": "valid/SOLVED over attempted, by task and design",
             "winner_claim_allowed": False},
            {"id": "EP-05", "name": "within-task repeatability U_rep",
             "status": "PRE_REGISTERED_FOR_M1",
             "computation": "one exact repeat in M1-A; U_rep=max relative CDi difference",
             "winner_claim_allowed": False},
            {"id": "EP-06", "name": "CTX-A/B task separability",
             "status": "PRE_REGISTERED_FOR_M1",
             "computation": "4 tasks x 3 designs; effect>=max(2U,1e-3) or Spearman<0.99",
             "winner_claim_allowed": False},
        ],
        "e1_e6": {
            "status": "NOT_APPLICABLE_TO_M0R_ZERO_PHYSICAL",
            "note": ("M0-R is a contract/freeze package with no optimization arms and no physical run. "
                     "E1-E6 are not computed, not inherited from R10, and not claimed as results."),
            "not_reused_from_r10": True,
        },
        "claims_policy": {
            "single_seed": 42,
            "single_seed_note": "descriptive only; no statistical inference",
            "no_winner": True,
            "no_significance": True,
            "no_p_value": True,
            "no_confidence_interval_claim": True,
            "no_cross_family_average": True,
            "no_optimization_gain_claim": True,
            "fuel_burn_kg": None,
            "external_physics_supported": "NOT_VALIDATED",
        },
        "non_result_boundary": [
            "Endpoints pre-registered; no value computed in M0-R.",
            "No winner, ranking, significance, confidence interval or cross-family comparison.",
        ],
    }


def update_simple(doc: Mapping[str, Any], family_sha: str, schema_suffix: str) -> Dict[str, Any]:
    out = json.loads(json.dumps(doc, ensure_ascii=False))
    out["schema"] = SCHEMA + "." + schema_suffix
    out["tool_version"] = TOOL_VERSION
    out["package_id"] = PACKAGE_ID
    out["status"] = PACKAGE_STATUS
    out["family_sha256"] = family_sha
    return out


def write_sums() -> int:
    lines = []
    for path in sorted(PACKAGE_DIR.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        rel = str(path.relative_to(PACKAGE_DIR)).replace("\\", "/")
        lines.append("%s  %s" % (sha_file(path), rel))
    (PACKAGE_DIR / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def check_sums() -> Dict[str, Any]:
    sums = PACKAGE_DIR / "SHA256SUMS.txt"
    if not sums.exists():
        return {"id": "M0R-V-SUMS", "status": "FAIL", "detail": "missing SHA256SUMS.txt"}
    bad = []
    count = 0
    for line in sums.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            return {"id": "M0R-V-SUMS", "status": "FAIL", "detail": "bad line: " + line}
        count += 1
        path = PACKAGE_DIR / parts[1]
        if not path.exists() or sha_file(path) != parts[0]:
            bad.append(parts[1])
    return {"id": "M0R-V-SUMS", "status": "PASS" if count and not bad else "FAIL",
            "detail": {"entries": count, "bad": bad}}


def validate(docs: Mapping[str, Any]) -> Dict[str, Any]:
    tasks_doc = docs["tasks"]
    tasks = tasks_doc["tasks"]
    family_sha = tasks_doc["family_sha256"]
    family_payload = {
        "schema": FAMILY_SCHEMA,
        "n_tasks": len(tasks),
        "task_set": [{"task_id": t["task_id"], "task_fingerprint": t["task_fingerprint"]}
                     for t in tasks],
        "sref_ref_m2": tasks[0]["sref_ref_m2"],
        "baseline_vspgeom_sha256": tasks[0]["geometry"]["baseline_vspgeom_sha256"],
        "openvsp_geometry_sha256": tasks[0]["geometry"]["openvsp_geometry_sha256"],
        "raw_design_space_sha256": tasks[0]["design_space"]["raw_yaml_sha256"],
        "a1_task_evaluator_sha256": tasks[0]["evaluator"]["a1_task_evaluator_sha256"],
        "solver": {"solver_version": "7.2.2", "openvsp_version": "3.55.0"},
    }
    checks = [
        {"id": "M0R-V-01", "domain": "family",
         "status": "PASS" if len(family_sha) == 64 and not family_sha.startswith(OLD_PREFIXES) else "FAIL"},
        {"id": "M0R-V-02", "domain": "family",
         "status": "PASS" if sha_text(canonical(family_payload)) == family_sha else "FAIL"},
        {"id": "M0R-V-03", "domain": "tasks",
         "status": "PASS" if [t["task_id"] for t in tasks] == FINAL_IDS else "FAIL"},
        {"id": "M0R-V-04", "domain": "tasks",
         "status": "PASS" if [sum(1 for t in tasks if t["split"] == s) for s in
                              ("meta_train", "meta_val", "meta_test_blind")] == [3, 1, 2] else "FAIL"},
        {"id": "M0R-V-05", "domain": "tasks",
         "status": "PASS" if all(t["q_recompute_rel_error"] <= 1e-12 for t in tasks) else "FAIL"},
        {"id": "M0R-V-06", "domain": "tasks",
         "status": "PASS" if all(abs(t["l_ref_n"] - t["q_pa"] * t["sref_ref_m2"] * t["cl_target"]) /
                                 max(abs(t["l_ref_n"]), 1e-300) <= 1e-12 for t in tasks) else "FAIL"},
        {"id": "M0R-V-07", "domain": "tasks",
         "status": "PASS" if all(100.0 <= t["mass_t"] <= 190.0 for t in tasks) else "FAIL"},
        {"id": "M0R-V-08", "domain": "sref",
         "status": "PASS" if docs["sref"]["consistency"]["rel_diff"] <= 1e-9 else "FAIL"},
        {"id": "M0R-V-09", "domain": "geometry",
         "status": "PASS" if docs["sref"]["independent_recompute"]["vspgeom_sha256"].startswith("16da482a") and
                              docs["sref"]["independent_recompute"]["vspgeom_bytes"] == 225414 and
                              docs["sref"]["independent_recompute"]["mesh_family"] == "546x480" else "FAIL"},
        {"id": "M0R-V-10", "domain": "design_space",
         "status": "PASS" if docs["design_space"]["n_fail"] == 0 else "FAIL"},
        {"id": "M0R-V-11", "domain": "decks",
         "status": "PASS" if docs["decks"]["n_package_baseline_decks"] == 6 and
                              docs["decks"]["n_full_family_deck_space_entries"] == 18 and
                              len(docs["decks"]["reference_design_decks_unfrozen_reference"]) == 12 and
                              len(docs["decks"]["m1a_required_deck_set"]) == 12 and
                              len(docs["decks"]["m3a_reference_deck_set"]) == 4 and
                              docs["decks"]["freeze_boundary"]["m1a_baseline_slots_already_frozen"] == 4 and
                              docs["decks"]["freeze_boundary"]["m1a_reference_slots_to_freeze_before_authorization"] == 8 and
                              docs["decks"]["n_fail"] == 0 else "FAIL"},
        {"id": "M0R-V-12", "domain": "budget",
         "status": "PASS" if docs["budget"]["n_fail"] == 0 and docs["budget"]["total"]["planned_starts"] == 115 and
                              docs["budget"]["total"]["hard_cap_starts"] == 126 else "FAIL"},
        {"id": "M0R-V-13", "domain": "split",
         "status": "PASS" if docs["split"]["n_fail"] == 0 else "FAIL"},
        {"id": "M0R-V-14", "domain": "zero_physical",
         "status": "PASS" if docs["zero"]["physical_call_count"] == 0 and
                              docs["zero"]["solver_started"] is False and docs["zero"]["run_dir_created"] is False else "FAIL"},
        {"id": "M0R-V-15", "domain": "a5",
         "status": "PASS" if docs["a5"]["coverage"]["requirements_mapped"] == 30 and
                              docs["a5"]["coverage"]["checklist_mapped"] == 60 and
                              docs["a5"]["coverage"]["gate_conditions_mapped"] == 42 and
                              docs["a5"]["n_fail"] == 0 else "FAIL"},
        {"id": "M0R-V-16", "domain": "a1_interface",
         "status": "PASS" if docs["a1"]["n_fail"] == 0 and len(docs["a1"]["a1_sha256sums_entries"]) == 7 and
                              docs["a1"]["a1_sha256sums"]["sha256"] == pd.A1_SUMS_SHA256 else "FAIL"},
        {"id": "M0R-V-17", "domain": "package",
         "status": "PASS" if docs["package"]["authorization_status"] == "NOT_CREATED_M0R_ZERO_PHYSICAL" and
                              docs["package"]["run_dir"] is None and docs["package"]["token"] is None else "FAIL"},
        {"id": "M0R-V-18", "domain": "claims",
         "status": "PASS" if docs["stat"]["claims_policy"]["no_winner"] and
                              docs["stat"]["claims_policy"]["fuel_burn_kg"] is None and
                              docs["stat"]["claims_policy"]["external_physics_supported"] == "NOT_VALIDATED" else "FAIL"},
    ]
    checks.append(check_sums())
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    return {
        "schema": SCHEMA + ".validation.v1",
        "tool_version": TOOL_VERSION,
        "package_id": PACKAGE_ID,
        "validated_utc": pd.now_utc(),
        "package_dir": str(PACKAGE_DIR).replace("\\", "/"),
        "checks": checks,
        "checks_total": len(checks),
        "n_pass": sum(1 for c in checks if c["status"] == "PASS"),
        "n_fail": n_fail,
        "verdict": PACKAGE_STATUS if n_fail == 0 else "M0R_PACKAGE_INVALID",
        "is_result": False,
        "family_sha256": family_sha,
        "physical_call_count": 0,
        "a5_gate": {"gate_id": A5_GATE_ID, "status": "PENDING_A5_FORMAL_GATE"},
    }


def prereg_zh(docs: Mapping[str, Any]) -> str:
    rows = []
    for t in docs["tasks"]["tasks"]:
        rows.append("| %s | %s | %.2f | %.2f | %s | %.15g | %.13g | %.6f | %.6f |" % (
            t["task_id"], t["a1_task_id"], t["mach"], t["cl_target"], t["split"],
            t["q_pa"], t["vinf_m_s"], t["l_ref_n"], t["mass_t"]))
    return """# D-REAL-001 M0-R 物理任务族冻结包（中文预注册）

- 包 ID：%s
- 状态：%s
- 新 family SHA256：%s
- A1 code commit：%s
- A1 freeze commit：%s
- A5 gate：%s（PENDING；A3 不签 gate、不宣布 admission）
- 零物理：physical_call_count=0，solver_started=false，run_dir/ledger/token/authorization 均未创建。

## 1. 范围与边界

M0-R 是零物理的物理任务族重冻包。它只定义 6 个任务、3/1/2 split、预算模板、CTX-A..F
预注册、泄漏审计、统计端点与 A5 证据映射；不是 run，不是结果，不是验收通过，不是 M1
授权。fuel_burn_kg=null；外部物理 NOT_VALIDATED；单 seed=42 仅描述性；无 winner / 排名 /
显著性 / p 值 / 置信区间 / 跨族或跨 Mach 平均 / 优化增益声明。

## 2. 六个任务（L-30-A01，ATM-F1R2，固定 18,288 m）

| A3 task_id | A1 temp id | Mach | CL | split | q (Pa) | Vinf (m/s) | L_ref (N) | mass (t) |
|---|---|---|---|---|---|---|---|---|
%s

全部任务：12D_ALL_ACTIVE；alpha 7 点 (-2,0,2,4,6,8,10)；max_refine_sweeps=0；
V01/V02 不声称零效应，10D 掩码 DEFERRED 到 M1。

## 3. 几何与设计空间

- post-fix baseline vspgeom SHA256 16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84，
  225,414 B，546x480；openvsp_geometry d20ee7adc38286c7da3ef3ea5aa5be8204596d491d6601b9a635b0ae5213dc56。
- 旧 40fdd436 / 543x472 与旧 family ada424cc 已 retired，不在 active family。
- raw 12D design-space YAML 8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e，
  10,846 B；C01-C04 交叉约束必须由 M1 sampler/executor 在 build 前强制。A1 interface 不代替
  cross-constraint 强制（A1 已书面明确）。
- SREF 唯一来源是 runtime post-fix baseline 重算；358.25000000000006 仅是 anchor 校验常量，
  不得直接当作 SREF_REF 输入，也不得硬编码。运行时需记录重算值、vspgeom 16da482a 与绑定
  SHA。预注册容差 1e-9，实测 Newell 重算 358.2500000223502 vs anchor 358.25000000000006，
  rel=6.2387e-11。A1 的实现中存在该 anchor 常量（task_evaluator.py:56）与 :300-303 校验；
  :1169 仍从 post-fix baseline build 取 runtime sref，M0-R 以 runtime 值为唯一 SREF 来源。
- deck determinism：solver_input_sha256 含 path-dependent .vkey（绝对路径+随机 component
  object-ID），不是跨进程 expected；确定性绑定用 deck_sha256 + vspgeom_sha256。vkey 按 run
  记录并可披露非确定性；A2 runner 不得以 solver_input_sha256 做 gate。
- deck 冻结边界：full family deck 空间 = 3 个设计（B0-01/B1-01/C5）×6 个任务 = 18 个条目；
  其中 6 个 B0-01 baseline deck 已在本包冻结，12 个 B1-01/C5 reference 条目未冻结。M1-A 需要
  12 个 deck 槽位（4 个 M1 任务 ×3 个设计）：4 个 B0-01 槽位已冻结，8 个 B1-01/C5 槽位必须在
  M1-A 授权前冻结或确定性重生成；剩余 4 个 B1-01/C5 meta_test 槽位必须在 M3-A 前冻结。
  M0R_DECK_FREEZE.json 的 m1a_required_deck_set 逐条列出 12 个槽位的 task_id、design_id、
  deck_sha256、vspgeom_sha256 与 frozen_status。未冻结的 reference deck 不得直接用于物理执行。

## 3.1 A1/A5 三项权威口径（原文，必须照录）

- CL-1-SREF：SREF_REF 以 post-fix baseline 几何运行时重算值为唯一来源（本次 358.25000000000006），冻结常量仅作 1e-12 校验锚；不得把 358.25 作为计算输入硬编码。
- CL-2-SOLVER-INPUT-SHA：solver_input_sha256 含 path-dependent/random 的 .vkey，跨进程不可复现；确定性绑定只用 deck_sha256 + vspgeom_sha256（加 solver_sha256/task_fingerprint），vkey 与 input_sha 按 run 记录，不作跨进程 expected。
- CL-3-F1R2-CONTINUITY：M2.02 仅物理条件与 F1R2 逐位连续（q=20483.940233430174，Mach/Vinf/Rho/ReCref/alpha 网格相同），deck 字节不相等（A1 943B/LF vs F1R2 985B/CRLF，43 行规范化后相同）；不继承 F1R2 expected polar，M1-A 重建 admission baseline。

## 4. Split 与泄漏

3 meta_train（M2.02 CL0.17 / M2.02 CL0.19 / M2.2 CL0.17）、1 meta_val（M2.2 CL0.19）、
2 meta_test_blind（M1.8 CL0.17 / M1.8 CL0.19）。按 task identity 切分，不按样本；meta_test
在 M1/M2 期间不读标签、不参与归一化/标签变换/early stopping；无高度副本；同设计跨 task
复用同一 vspgeom 字节属于有意迁移，不是 task-identity 泄漏。M2.02 与 F1R2 的连续性只是
q/物理条件逐位连续，不是 deck 字节连续，也不继承 F1R2 expected polar；M1-A 会重建 admission
 baseline。

## 5. 预算（未来授权模板，不是已计费）

- M1-A：15 starts / 105 internal，caps 18/126，retry 0；4 任务 x 3 设计=12 + 1 exact repeat + 2 preflight。
- M1-B：66/462，caps 70/490；4x16=64 labels + 2 preflight。
- M3-A：34/238，caps 38/266；2x16=32 labels + 2 preflight。
- 总：115/805，hard 126/882，labels 96，preflight 6，retry 0；M3-B NOT_AUTHORIZED。
- 五口径：M0-R 全零；M1 起 charged 与 actual 分列，禁止混写。

## 6. CTX 预注册（不测值）

CTX-A 纯缩放（TOO_SIMILAR）；CTX-B 归一化响应差（效应量 >= max(2*U_within,1e-3) 或
Spearman<0.99）；CTX-C 可行域；CTX-D 升力匹配/插值；CTX-E 每任务真实物理证据（DEFERRED
到 M1-A）；CTX-F 同几何字节。M1-A 只有 3 个参考设计，Spearman 仅描述性，无 p 值。

## 7. 统计端点

主指标 D_i_N=q*Sref(x)*CDi(lift_matched)，按 task/design 分报；禁止 0.5*(f1+f2)、硬编码
Sref、跨 family 平均。EP-01..EP-06 见 M0R_STAT_ENDPOINTS.json。M0-R 零物理，E1-E6
不计算、不继承 R10，不构成绩效结论。

## 8. A5 证据

本包映射 A5 R01-R30、gate draft 60 checks、42 conditions（R01-R30 + G01-G12）。A5 独立
复算并签 G-M0R-ADMISSION-01；A3 不声称 PASS、READY_FOR_M1A_ADMISSION 或 admission。
A1 interface 冻结绑定：code 0c51415、freeze c5698a2、7 文件 SUMS 3ca22ec9。

## 9. 未授权事项

不创建 run dir / ledger / token / authorization；不启动 VSPAERO；不复用旧 #9/#10
authorization；M1-A 通过后仍需 A5 预审 + Lead 单独 authorization/GO。
""" % (PACKAGE_ID, PACKAGE_STATUS, docs["tasks"]["family_sha256"], pd.A1_CODE_COMMIT,
       pd.A1_FREEZE_COMMIT, A5_GATE_ID, "\n".join(rows))


def readme_zh(docs: Mapping[str, Any]) -> str:
    return """# M0-R Formal Package (A3 task-57, zero physical, not a gate)

Status: %s.

- New family SHA256: %s
- A1 code commit: %s
- A1 freeze commit: %s
- A5 gate: %s PENDING (A5 owns it)
- Zero physical: physical=0, solver_started=false, no run dir/ledger/token/authorization
- fuel_burn_kg=null; physics NOT_VALIDATED; single seed descriptive;
  no winner/significance/cross-family.

A5 wording corrections applied explicitly:

1. SREF runtime value from post-fix baseline is the only source. 358.25000000000006 is
   a validation anchor constant only; it must not be used as the runtime SREF input.
2. solver_input_sha256 contains a path-dependent .vkey and is not a cross-process
   expected value. Deterministic binding is deck_sha256 + vspgeom_sha256. A2 runner must
   not gate on solver_input_sha256.
3. M2.02 continuity with F1R2 is q/physical-condition continuity only; decks are not
   byte-continuous and F1R2 expected polar is not inherited. M1-A rebuilds the admission
   baseline.
4. Deck freeze boundary: the full family deck space is 3 designs (B0-01, B1-01, C5) x 6 tasks = 18
   entries. The 6 B0-01 baseline decks are frozen here. The 12 B1-01/C5 reference entries are
   unfrozen reference. M1-A requires 12 deck slots (4 M1 tasks x 3 designs): the 4 B0-01 slots are
   already frozen, and the 8 B1-01/C5 slots must be frozen or deterministically regenerated before
   M1-A authorization. The remaining 4 B1-01/C5 meta_test slots must be frozen before M3-A. The
   M1-A_REQUIRED_DECK_SET in M0R_DECK_FREEZE.json lists all 12 slots with frozen_status.

pre_draft/ is retained as the historical task-60 appendix. It is not the formal
package and must not be used as A5 gate input. See M0R_PREREGISTRATION_ZH.md for
the Chinese preregistration.
""" % (PACKAGE_STATUS, docs["tasks"]["family_sha256"], pd.A1_CODE_COMMIT,
       pd.A1_FREEZE_COMMIT, A5_GATE_ID)


def build() -> Dict[str, Any]:
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    pred_tasks = read_json(PRE / "M0R_TASK_SPECS_PREDRAFT.json")
    pred_sref = read_json(PRE / "M0R_SREF_PROVENANCE_PREDRAFT.json")
    pred_decks = read_json(PRE / "M0R_DECK_SPECS_PREDRAFT.json")
    pred_split = read_json(PRE / "M0R_SPLIT_LEAKAGE_AUDIT_PREDRAFT.json")
    pred_budget = read_json(PRE / "M0R_BUDGET_LEDGER_PREDRAFT.json")
    pred_ctx = read_json(PRE / "M0R_CTX_PLAN_PREDRAFT.json")
    pred_a5 = read_json(PRE / "M0R_A5_REQUIREMENTS_MAP_PREDRAFT.json")
    pred_zero = read_json(PRE / "M0R_ZERO_PHYSICAL_EVIDENCE_PREDRAFT.json")

    tasks = finalize_tasks(pred_tasks)
    family_sha = tasks["family_sha256"]
    decks = build_decks(pred_decks, tasks)
    sref = update_simple(pred_sref, family_sha, "sref_provenance.v1")
    sref["a1_interface"] = {"code_commit": pd.A1_CODE_COMMIT,
                            "freeze_commit": pd.A1_FREEZE_COMMIT,
                            "dry_run": info(pd.A1_DRY_RUN)}
    sref["anchor_role"] = "VALIDATION_ANCHOR_ONLY_NOT_A_RUNTIME_HARDCODE"
    sref["runtime_recompute_required"] = True
    sref["a1_clarification"] = info(A1_CLARIFY)
    runtime_binding_sha = sha_text(canonical({
        "vspgeom_sha256": sref["independent_recompute"]["vspgeom_sha256"],
        "sref_m2": sref["independent_recompute"]["wing_area_m2"],
        "source": "post-fix baseline geometry.wing.area_m2 recomputed at runtime",
    }))
    sref["runtime_binding_sha256"] = runtime_binding_sha
    sref["runtime_binding"] = {
        "runtime_source": "post-fix baseline geometry.wing.area_m2 recomputed at runtime",
        "baseline_vspgeom_sha256": sref["independent_recompute"]["vspgeom_sha256"],
        "binding_sha256": runtime_binding_sha,
        "binding_note": "A3-derived deterministic binding from A1 runtime sref and post-fix vspgeom SHA",
        "hardcode_forbidden": True,
        "disclosure": ("358.25000000000006 is the frozen validation anchor only. The runtime SREF must be "
                       "recomputed from the post-fix baseline and SHA-bound; it must not be hardcoded. "
                       "L_ref uses the frozen reference only as the pre-registered task contract value."),
    }
    sref["consistency"]["disclosure"] = (
        "A1 task_evaluator carries a frozen SREF_REF validation constant and checks it at 1e-12; "
        "A1 clarification CL-1 (commit e659f15, A5-accepted) defines that constant as a validation "
        "anchor only. The runtime SREF is recomputed from the post-fix baseline geometry and "
        "SHA-bound; no unresolved interface deviation remains. The independent Newell cross-check "
        "(358.2500000223502 m2, rel 6.238702072197911e-11 vs the A1 runtime value) is a disclosure; "
        "L_ref uses the A1 runtime-recomputed 358.25000000000006 m2 with the pre-registered 1e-9 "
        "cross-check tolerance."
    )
    sref["consistency"]["status"] = "PASS_WITH_DISCLOSURE_CL1_BOUND"
    split = update_simple(pred_split, family_sha, "split_leakage.v1")
    a1_to_final = {t["a1_task_id"]: t["task_id"] for t in tasks["tasks"]}
    split["split"] = tasks["splits"]
    split["task_id_scheme"] = "M0R_FINAL_IDS_AUTHORITATIVE"
    split["a1_task_id_map"] = dict(sorted(a1_to_final.items()))
    split["prior_exposure"] = {a1_to_final[k]: v for k, v in split.get("prior_exposure", {}).items()}
    budget = update_simple(pred_budget, family_sha, "budget_ledger.v1")
    budget["authorization"]["status"] = "NOT_CREATED_M0R_ZERO_PHYSICAL"
    ctx = update_simple(pred_ctx, family_sha, "ctx_plan.v1")
    ctx["m1a_matrix"] = ("4 M1-A tasks (3 meta_train + 1 meta_val) x 3 reference designs + "
                         "1 exact repeat + 2 preflight")
    ctx["m1a_tasks"] = [t["task_id"] for t in tasks["tasks"] if t["split"] in ("meta_train", "meta_val")]
    for entry in ctx["ctx"]:
        if entry["id"] == "CTX-B":
            entry["acceptance"] = ("4/4 M1-A tasks (3 meta_train + 1 meta_val) separable, otherwise "
                                   "PHYSICAL_TASK_FAMILY_BLOCKED.")
    ctx["uncertainty"]["min_effect_rel_floor"] = 0.001
    ctx["uncertainty"]["min_effect_rel_floor_basis"] = (
        "A5 R10 absolute floor; actual min_effect_rel = max(2*U_within, 1e-3) after M1-A repeat")
    zero = update_simple(pred_zero, family_sha, "zero_physical_evidence.v1")
    zero.pop("predraft_id", None)
    zero["tool_version"] = TOOL_VERSION
    zero["attestation"] = ("This formal package was produced by a read-only analysis of A1/A5/Lead "
                           "artifacts; no VSPAERO process was spawned and no run directory or accounting "
                           "ledger was created.")
    design = build_design_space(sref)
    a1 = build_a1_binding()
    a5 = build_a5(pred_a5, family_sha)
    stat = build_stat()

    package = {
        "schema": SCHEMA + ".package.v1",
        "tool_version": TOOL_VERSION,
        "package_id": PACKAGE_ID,
        "status": PACKAGE_STATUS,
        "family_sha256": family_sha,
        "family_sha256_status": "FROZEN_NEW_FAMILY",
        "old_family_sha256_retired": ["ada424cc...", "40fdd436..."],
        "n_tasks": 6,
        "split": {"meta_train": 3, "meta_val": 1, "meta_test_blind": 2},
        "budget": {"planned_starts": 115, "planned_internal_cases": 805,
                   "hard_cap_starts": 126, "hard_cap_internal_cases": 882,
                   "labels": 96, "preflight": 6, "retry": 0, "m3_b": "NOT_AUTHORIZED"},
        "a1_interface": {"code_commit": pd.A1_CODE_COMMIT,
                         "freeze_commit": pd.A1_FREEZE_COMMIT,
                         "sha256sums": info(pd.A1_SHA256SUMS),
                         "dry_run": info(pd.A1_DRY_RUN),
                         "interface": info(pd.A1_INTERFACE_MD),
                         "evaluator": info(pd.A1_EVALUATOR),
                         "clarification": info(A1_CLARIFY),
                         "clarification_commit": "e659f15d826de0c55bcfe02944a97a28ba50b824",
                         "clarification_a5_status": "A5_ACCEPTED_AUTHORITATIVE",
                         "required_m0r_wording_zh": {
                             "CL-1-SREF": "SREF_REF 以 post-fix baseline 几何运行时重算值为唯一来源（本次 358.25000000000006），冻结常量仅作 1e-12 校验锚；不得把 358.25 作为计算输入硬编码。",
                             "CL-2-SOLVER-INPUT-SHA": "solver_input_sha256 含 path-dependent/random 的 .vkey，跨进程不可复现；确定性绑定只用 deck_sha256 + vspgeom_sha256（加 solver_sha256/task_fingerprint），vkey 与 input_sha 按 run 记录，不作跨进程 expected。",
                             "CL-3-F1R2-CONTINUITY": "M2.02 仅物理条件与 F1R2 逐位连续（q=20483.940233430174，Mach/Vinf/Rho/ReCref/alpha 网格相同），deck 字节不相等（A1 943B/LF vs F1R2 985B/CRLF，43 行规范化后相同）；不继承 F1R2 expected polar，M1-A 重建 admission baseline。",
                         },
                         "n_sums_entries": 7},
        "a5_gate": {"gate_id": A5_GATE_ID, "status": "PENDING_A5_FORMAL_GATE",
                    "a5_commit": None,
                    "a5_draft_reference": {"commit": "ba1b11f", "status": "DRAFT_NOT_A_GATE"},
                    "gate_input_status": "FORMAL_PACKAGE_FROZEN_PENDING_A5_FORMAL_GATE"},
        "a5_wording_corrections": {
            "sref_runtime_is_only_source": True,
            "sref_ref_frozen_is_anchor_constant_only": True,
            "sref_anchor_must_not_be_used_as_runtime_input": True,
            "solver_input_sha256_is_path_dependent_not_cross_process_expected": True,
            "cross_process_deck_identity": "deck_sha256 + vspgeom_sha256",
            "vkey_must_be_recorded_per_run_and_may_be_disclosed_nondeterministic": True,
            "a2_runner_must_not_gate_on_solver_input_sha256": True,
            "m202_continuity_is_q_physics_only_not_deck_bytes": True,
            "m202_does_not_inherit_f1r2_expected_polar": True,
            "m1a_rebuilds_admission_baseline": True,
        },
        "continuity_disclosure": {
            "m2_02_continuity": "q/physical conditions are continuous with the F1R2 anchor",
            "deck_byte_continuity": False,
            "inherits_f1r2_expected_polar": False,
            "m1a_rebuilds_admission_baseline": True,
            "note": ("A1 f1r2_continuity m2_02 is_byte_continuous_with_f1r2=true is an overstatement: "
                     "the M202 deck is 943 B/LF while the F1R2 same-content deck is 985 B/CRLF; "
                     "content is the same but bytes are not equal."),
        },
        "authorization_status": "NOT_CREATED_M0R_ZERO_PHYSICAL",
        "run_dir": None, "ledger": None, "token": None, "approval": None,
        "physical_call_count": 0, "solver_started": False,
        "files": ["M0R_PACKAGE.json", "M0R_TASK_SPECS.json", "M0R_DECK_FREEZE.json",
                  "M0R_SREF_PROVENANCE.json", "M0R_DESIGN_SPACE_BINDING.json",
                  "M0R_SPLIT_LEAKAGE_AUDIT.json", "M0R_BUDGET_LEDGER.json",
                  "M0R_CTX_PLAN.json", "M0R_STAT_ENDPOINTS.json",
                  "M0R_A1_INTERFACE_BINDING.json", "M0R_A5_REQUIREMENTS_MAP.json",
                  "M0R_ZERO_PHYSICAL_EVIDENCE.json", "M0R_VALIDATION.json",
                  "M0R_PREREGISTRATION_ZH.md", "README_ZH.md", "SHA256SUMS.txt",
                  "pre_draft/ (historical appendix)",
                  "decks/ (6 frozen B0-01 baseline decks; full family deck space 18 = 3 designs x 6 tasks; 12 B1-01/C5 reference entries unfrozen; M1-A 12 slots = 4 M1 tasks x 3 designs (4 frozen B0 + 8 B1/C5 to freeze before authorization); 4 meta_test B1/C5 slots to freeze before M3-A)"],
        "claims": {"fuel_burn_kg": None, "physics_status": "NOT_VALIDATED",
                   "no_winner": True, "no_significance": True,
                   "no_cross_family_average": True},
        "non_result_boundary": [
            "Formal M0-R package only; not a run, result, admission or gate.",
            "A5 independently recomputes and signs G-M0R-ADMISSION-01; M1 not authorized.",
            "Zero physical; no solver started.",
        ],
    }
    docs = {"tasks": tasks, "decks": decks, "sref": sref, "design_space": design,
            "split": split, "budget": budget, "ctx": ctx, "stat": stat,
            "a1": a1, "a5": a5, "zero": zero, "package": package}

    write_json(PACKAGE_DIR / "M0R_TASK_SPECS.json", tasks)
    write_json(PACKAGE_DIR / "M0R_DECK_FREEZE.json", decks)
    write_json(PACKAGE_DIR / "M0R_SREF_PROVENANCE.json", sref)
    write_json(PACKAGE_DIR / "M0R_DESIGN_SPACE_BINDING.json", design)
    write_json(PACKAGE_DIR / "M0R_SPLIT_LEAKAGE_AUDIT.json", split)
    write_json(PACKAGE_DIR / "M0R_BUDGET_LEDGER.json", budget)
    write_json(PACKAGE_DIR / "M0R_CTX_PLAN.json", ctx)
    write_json(PACKAGE_DIR / "M0R_STAT_ENDPOINTS.json", stat)
    write_json(PACKAGE_DIR / "M0R_A1_INTERFACE_BINDING.json", a1)
    write_json(PACKAGE_DIR / "M0R_A5_REQUIREMENTS_MAP.json", a5)
    write_json(PACKAGE_DIR / "M0R_ZERO_PHYSICAL_EVIDENCE.json", zero)
    write_json(PACKAGE_DIR / "M0R_PACKAGE.json", package)
    (PACKAGE_DIR / "M0R_PREREGISTRATION_ZH.md").write_text(prereg_zh(docs), encoding="utf-8")
    (PACKAGE_DIR / "README_ZH.md").write_text(readme_zh(docs), encoding="utf-8")
    write_sums()
    result = validate(docs)
    write_json(PACKAGE_DIR / "M0R_VALIDATION.json", result)
    write_sums()
    result = validate(docs)
    write_json(PACKAGE_DIR / "M0R_VALIDATION.json", result)
    write_sums()
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if args.validate_only:
        docs = {
            "tasks": read_json(PACKAGE_DIR / "M0R_TASK_SPECS.json"),
            "decks": read_json(PACKAGE_DIR / "M0R_DECK_FREEZE.json"),
            "sref": read_json(PACKAGE_DIR / "M0R_SREF_PROVENANCE.json"),
            "design_space": read_json(PACKAGE_DIR / "M0R_DESIGN_SPACE_BINDING.json"),
            "split": read_json(PACKAGE_DIR / "M0R_SPLIT_LEAKAGE_AUDIT.json"),
            "budget": read_json(PACKAGE_DIR / "M0R_BUDGET_LEDGER.json"),
            "ctx": read_json(PACKAGE_DIR / "M0R_CTX_PLAN.json"),
            "stat": read_json(PACKAGE_DIR / "M0R_STAT_ENDPOINTS.json"),
            "a1": read_json(PACKAGE_DIR / "M0R_A1_INTERFACE_BINDING.json"),
            "a5": read_json(PACKAGE_DIR / "M0R_A5_REQUIREMENTS_MAP.json"),
            "zero": read_json(PACKAGE_DIR / "M0R_ZERO_PHYSICAL_EVIDENCE.json"),
            "package": read_json(PACKAGE_DIR / "M0R_PACKAGE.json"),
        }
        result = validate(docs)
    else:
        result = build()
    print(json.dumps({"verdict": result["verdict"], "checks_total": result["checks_total"],
                      "n_pass": result["n_pass"], "n_fail": result["n_fail"],
                      "family_sha256": result["family_sha256"]},
                     ensure_ascii=False, sort_keys=True))
    return 0 if result["n_fail"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
