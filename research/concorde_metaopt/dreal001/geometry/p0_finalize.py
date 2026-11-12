"""P0 finalization: TaskSpec contract files, A02 declaration, A06 evaluations, A09 manifest.

Pure data/contract work: no OpenVSP model build and no solver start.  All fields are
re-derived from the immutable ENV_SMOKE case inputs and case_result.json.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict

from . import evidence_manifest, evaluation_reserialize, run_closeout
from .task_spec import TASK_SPEC, validate_contract, write_task_spec, write_task_spec_yaml

SETUP_FIELDS = ("Sref", "Cref", "Bref", "X_cg", "Y_cg", "Z_cg", "Mach", "AoA", "Beta",
                "ReCref", "Vinf", "Rho", "Symmetry")


def parse_setup_fields(text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def write_reference_declaration(run_dir: Path) -> Path:
    case_dirs = sorted(run_dir.glob("cases/*/inputs"))
    if len(case_dirs) != 1:
        raise RuntimeError("expected exactly one ENV_SMOKE case dir, found %d" % len(case_dirs))
    case_dir = case_dirs[0]
    case_inputs = json.loads((case_dir / "case_inputs.json").read_text(encoding="utf-8"))
    setup_path = next(case_dir.glob("*.vspaero"))
    setup_text = setup_path.read_text(encoding="utf-8")
    observed = parse_setup_fields(setup_text)
    sref = float(case_inputs["sref_m2"])
    contract = TASK_SPEC.reference_injection(sref)
    mismatches = []
    for key, expected in contract["injected"].items():
        if key not in observed:
            continue
        try:
            got = float(observed[key])
        except ValueError:
            continue
        if abs(got - float(expected)) > 1e-9 * max(1.0, abs(float(expected))):
            mismatches.append({"field": key, "expected": expected, "observed": observed[key]})
    payload = {
        "schema": "dreal001.reference_injection_declaration.v1",
        "run_id": case_inputs.get("run_id"),
        "case_id": case_inputs.get("case_id"),
        "source": "post-hoc declaration from immutable case_inputs.json + <base>.vspaero; "
                  "NO solver start and no input modification",
        "ref_flag": contract["ref_flag"],
        "policy": contract["policy"],
        "solver_recomputes_references": contract["solver_recomputes_references"],
        "injected_contract": contract["injected"],
        "observed_setup_fields": {key: observed.get(key) for key in SETUP_FIELDS},
        "field_mismatches": mismatches,
        "sref_recompute_contract": TASK_SPEC.to_dict()["sref_recompute_contract"],
        "w01_sensitivity_contract": TASK_SPEC.to_dict()["w01_sensitivity_contract"],
        "alpha_mach_beta": {
            "alpha_list_deg": case_inputs.get("alpha_list_deg"),
            "internal_solver_cases_expected": case_inputs.get("internal_solver_cases_expected"),
            "note": "alpha list is written into .vspaero; -fs is forbidden",
        },
        "physical_solver_starts_added": 0,
    }
    path = run_dir / "reference_injection_declaration.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="D-REAL-001 A1 P0 finalization (no solver)")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--configs-dir", default="configs")
    args = parser.parse_args()
    repo_root = Path.cwd()
    validation = validate_contract()
    configs = repo_root / args.configs_dir
    json_path = write_task_spec(configs / "dreal001_task_fixed_cruise_REAL.json")
    yaml_path = write_task_spec_yaml(configs / "dreal001_task_fixed_cruise_REAL.yaml")
    run_dir = Path(args.run_dir).resolve()
    declaration = write_reference_declaration(run_dir)
    evaluation = evaluation_reserialize.reserialize_run(run_dir)
    retention = evidence_manifest.record_retention(run_dir, delete=True)
    manifest = evidence_manifest.write_manifest(run_dir, retention_entries=retention)
    summary = {
        "validate": validation,
        "task_spec_json": str(json_path), "task_spec_yaml": str(yaml_path),
        "reference_declaration": str(declaration),
        "evaluations": evaluation,
        "retention_entries": len(retention),
        "manifest": manifest,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
