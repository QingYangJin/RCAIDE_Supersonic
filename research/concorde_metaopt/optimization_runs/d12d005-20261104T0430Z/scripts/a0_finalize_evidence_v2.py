#!/usr/bin/env python
"""D-12D-005 A0 evidence revision 4 (zero-solver, documentation/evidence only).

Responds to A5 task-97 findings:
  F-A0-01 (MAJOR): per-file hash evidence was recorded pre-commit (CRLF); the
    committed blobs are canonical LF because .gitattributes uses text=auto/eol=lf.
    Every text file record now carries BOTH forms explicitly:
    bytes_raw/sha256_raw and bytes_canonical_lf/sha256_canonical_lf (+hash_mode).
  F-A0-05 (MINOR): S5 reference velocity inheritance is annotated with the
    frozen-contract source and the formula delta.
F-A0-02/03/04 are closed by the fixed frozen test, README counts and the
explicit process-spawn scan scope recorded here.
Adds relocatable run-relative paths and per-script dual-form hashes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parent.parent
EVIDENCE = RUN_DIR / "evidence" / "a0" / "setup_generation.json"
FILE_KEYS = ("model", "raw_setup", "contract_setup", "vkey", "csf", "geom_result_csv")
SCRIPTS = (
    "a0_analyze_v1_divergence.py",
    "a0_finalize_evidence_v2.py",
    "a0_generate_setups.py",
    "a0_verify_cases.py",
    "vspaero7_runner_v1frozen.py",
    "vspaero7_runner_v2.py",
    "test_vspaero7_runner_v1frozen.py",
    "test_vspaero7_runner_v2.py",
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def kind_of(name: str) -> str:
    if name.startswith("test_"):
        return "regression_test"
    if "runner" in name:
        return "frozen_runner"
    return "generator_or_verifier"


def enrich_file_record(path: Path, name: str) -> dict:
    raw = path.read_bytes()
    canon = raw.replace(b"\r\n", b"\n")
    rec = {
        "name": name,
        "path_relative": path.relative_to(RUN_DIR).as_posix(),
        "bytes_raw": len(raw),
        "sha256_raw": sha(raw),
        "bytes_canonical_lf": len(canon),
        "sha256_canonical_lf": sha(canon),
        "hash_mode": "dual",
        "eol": "crlf" if raw != canon else "lf",
    }
    rec["bytes"] = rec["bytes_canonical_lf"]
    rec["sha256"] = rec["sha256_canonical_lf"]
    return rec


def main() -> int:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    cases = data["cases"]
    for case in cases:
        wd = Path(case["case_dir"]) if case.get("case_dir") else RUN_DIR / case["case_dir_relative"]
        if not wd.is_dir():
            wd = RUN_DIR / case["case_dir_relative"]
        case["case_dir_relative"] = wd.relative_to(RUN_DIR).as_posix()
        case["case_dir_abs_at_generation"] = str(wd)
        case.pop("case_dir", None)
        for key in FILE_KEYS:
            rec = case.get(key)
            if not isinstance(rec, dict) or "name" not in rec:
                continue
            case[key] = enrich_file_record(wd / rec["name"], rec["name"])
        exp_name = (case.get("expected") or {}).get("name") or "expected.json"
        if (wd / exp_name).is_file():
            case["expected"] = enrich_file_record(wd / exp_name, exp_name)
        thin = case.get("thin_geometry")
        if isinstance(thin, dict) and thin.get("external_path"):
            ep = Path(thin["external_path"])
            if ep.is_file():
                b = ep.read_bytes()
                thin.update(
                    {
                        "bytes_raw": len(b),
                        "sha256_raw": sha(b),
                        "hash_mode": "raw_external",
                        "path_relative": None,
                        "outside_git": True,
                        "note": "thin .vspgeom lives outside the repo; hashed as raw bytes (never git-normalised)",
                    }
                )
            else:
                thin["note"] = "external artifact not present on this host; recorded sha retained"
    for case in cases:
        if case["case_id"] == "S5_D12_M2p02_base":
            case["reference_velocity"] = {
                "Vinf": 596.0373972278921,
                "source": "frozen 12D contract inherited byte-for-byte from D-12D-004 V0 (wing355_thin_v0_contract.vspaero)",
                "formula_with_a_295_0680184": 596.0373971680001,
                "delta_m_s": 596.0373972278921 - 596.0373971680001,
                "delta_relative": abs(596.0373972278921 - 596.0373971680001) / 596.0373972278921,
                "decision": "keep the frozen value so S5 stays byte-identical to the already-reviewed V0 contract; the delta is 1.0e-10 relative and physically irrelevant",
            }
    runner = data.get("runner") or {}
    runner_path = RUN_DIR / "scripts" / runner.get("name", "vspaero7_runner_v1frozen.py")
    data["runner"] = enrich_file_record(runner_path, runner_path.name)
    data["scripts"] = []
    for name in SCRIPTS:
        p = RUN_DIR / "scripts" / name
        if not p.is_file():
            continue
        rec = enrich_file_record(p, name)
        rec["kind"] = kind_of(name)
        rec["process_spawn_allowed"] = kind_of(name) == "regression_test"
        data["scripts"].append(rec)
    data["schema_version"] = "d12d005-a0-setup-generation-2"
    data["revision"] = 4
    data["revision_history"] = [2, 3, 4]
    data["generated_utc"] = utcnow()
    data["hashing_convention"] = {
        "text_files": "sha256 over canonical LF bytes (CRLF->LF) — equals the committed git blob content, because .gitattributes is '* text=auto' with eol=lf",
        "external_artifacts": "sha256 over raw bytes (outside git)",
        "per_entry_fields": ["bytes_raw", "sha256_raw", "bytes_canonical_lf", "sha256_canonical_lf", "hash_mode"],
        "legacy_fields": "bytes/sha256 alias the canonical-LF form for older readers",
    }
    data["relocatability"] = {
        "case_dir_field": "case_dir_relative (run-dir relative, posix); case_dir_abs_at_generation is informational only",
        "verifier": "scripts/a0_verify_cases.py --run-dir <root> resolves every path from the run-dir root",
        "reason": "A5 F-A0-01 follow-up: a clean checkout must reproduce the evidence without the original absolute root",
    }
    data["bundle_requirements"] = [
        "model .vsp3 (copy of the generated model)",
        ".vkey (rewrite line 2 to the absolute path of the copied .vspgeom)",
        ".csf",
        "<base>_contract.vspaero (contract form, never the raw VSPAERO-default form)",
        "geom_result_thin.csv",
        "expected.json (required: the case-dir gate falls back to the 12D contract without it)",
        "thin .vspgeom copied from the external artifact root",
    ]
    data["process_spawn_scan"] = {
        "mode": "ast_import_and_call_scan",
        "covered": "every scripts/*.py record except regression_test kind",
        "forbidden_modules": ["subprocess"],
        "forbidden_calls": ["os.system", "os.popen", "subprocess.Popen", "subprocess.run", "subprocess.call", "shell=True"],
        "documented_exception": "the two regression_test files launch the runner CLI as a child process for smoke tests only; neither launches vspaero.exe",
    }
    data["revision_notes"] = {
        "A5_F-A0-01": "dual raw/canonical-LF per-file hash evidence; run-relative paths; verified from a relocated copy and from a clean checkout",
        "A5_F-A0-02": "scripts/test_vspaero7_runner_v1frozen.py import/path fixed to the frozen module; 22 tests OK (evidence/a0/v1frozen_test_run.log)",
        "A5_F-A0-03": "README file-count corrected to 7",
        "A5_F-A0-04": "process-spawn scan now covers every non-test script; the unittest's subprocess CLI call is documented as a permitted exception",
        "A5_F-A0-05": "S5 reference_velocity block records inheritance source and the 6.0e-8 m/s formula delta",
        "A5_A0R2_rev3": "revision 3: v2 runner rev2 hardening (V2-M01/M02/M03), LD-002 structure-only parser, verifier --no-write, 6/6 negative controls, real 12D-model check",
        "A5_S3F-01_rev4": "revision 4: v2 runner rev3 splits primary vs derived non-finite columns; Ew is the only allowlisted derived column (--allow-nonfinite-derived), non-allowlisted non-finite tokens still fail, and S3 verify-polar now reports PASS_WITH_WARNINGS (evidence/v1/s3_verify_polar_allowlisted.json). Zero solver; batch-1 starts stay 4/6.",
        "A5_A0R2-01": "clean-checkout replay log regenerated and records both raw and canonical-LF forms",
        "A5_A0R2-02": "replay log records checks_failed=0 explicitly, never null",
        "A5_A0R2-03": "verifier replays all 6 negative controls (S0 and S3 groups), not just S0",
        "A5_A0R2-04": "model_is_12d_wing replaced by a real expected-model-name check per case",
        "A5_A0R2-05": "verifier --no-write avoids mutating tracked evidence; absolute provenance fields are informational only",
    }
    data["zero_solver_statement"] = "no solver started in any revision; v2 runner start_solver() always refuses"
    EVIDENCE.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("ENRICHED cases=%d scripts=%d bytes=%d" % (len(cases), len(data["scripts"]), EVIDENCE.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
