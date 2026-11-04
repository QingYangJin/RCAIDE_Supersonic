#!/usr/bin/env python
"""D-12D-005 A0 independent verification, revision 5 (no OpenVSP, no solver).

Re-checks the A0 setup bundle from disk only, from any checkout root:
  * evidence JSON self-consistency, dual raw/canonical-LF hashes, run-relative paths;
  * contract setup readback via the frozen v1 runner contract (17 assertions);
  * raw setup still carries the three VSPAERO defaults (injection is required);
  * single-factor wake settings between S0/S1/S2 and S3/S4;
  * standard-wing metrics parsed from the .vsp3 XML; 12D model equals D-12D-004 V0;
  * thermodynamic self-consistency of the reference quantities;
  * no solver artifacts, no local .vspgeom, external .vspgeom hashes;
  * negative controls are still rejected;
  * process-spawn scan over every non-test script (unittest CLI exception documented);
  * README documents the 7-file bundle and the canonical-LF convention.

Usage: python scripts/a0_verify_cases.py [--run-dir <root>] [--no-write]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SOLVER_GLOBS = ("*.adb", "*.history", "*.polar", "*.lod", "*.groups", "*.fem")
FORBIDDEN_IMPORT_MODULES = ("subprocess",)
FORBIDDEN_ATTR_CALLS = (
    ("os", "system"),
    ("os", "popen"),
    ("subprocess", "Popen"),
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_output"),
    ("subprocess", "check_call"),
)


def _scan_process_spawn(source_text: str) -> list:
    import ast as _ast

    try:
        tree = _ast.parse(source_text)
    except SyntaxError as error:
        return ["PARSE_ERROR: %s" % error]
    hits = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORT_MODULES:
                    hits.append("import %s" % alias.name)
        elif isinstance(node, _ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in FORBIDDEN_IMPORT_MODULES:
                hits.append("from %s import ..." % module)
        elif isinstance(node, _ast.Call):
            func = node.func
            if isinstance(func, _ast.Attribute) and isinstance(func.value, _ast.Name):
                if (func.value.id, func.attr) in FORBIDDEN_ATTR_CALLS:
                    hits.append("%s.%s(...)" % (func.value.id, func.attr))
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, _ast.Constant) and keyword.value.value is True:
                    hits.append("shell=True")
    return sorted(set(hits))
SPEED_OF_SOUND = 295.0680184
MU = 1.42161308e-05
RHO = 0.1153178340089936
D12D004_V0 = Path(
    r"D:/RCAIDE-d12d004/research/concorde_metaopt/optimization_runs/"
    r"d12d004-vspaero72-lf-20261102T0500Z/evidence/v0/setup_gen"
)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canon(p: Path) -> bytes:
    return Path(p).read_bytes().replace(b"\r\n", b"\n")


def xml_parm(text: str, name: str):
    m = re.search(r'<%s Value="([-+0-9.eE]+)"' % re.escape(name), text)
    return float(m.group(1)) if m else None


def load_runner(path: Path):
    spec = importlib.util.spec_from_file_location("vspaero7_runner_v1frozen", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_setup_kv(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            try:
                fields[k.strip()] = float(v.strip())
            except ValueError:
                pass
    return fields


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--no-write", action="store_true", help="verify only, do not rewrite tracked a0_verification.json")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve() if args.run_dir else Path(__file__).resolve().parent.parent
    evidence_path = run_dir / "evidence" / "a0" / "setup_generation.json"
    runner_path = run_dir / "scripts" / "vspaero7_runner_v1frozen.py"
    out_path = run_dir / "evidence" / "a0" / "a0_verification.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    runner = load_runner(runner_path)
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    # ---- A. evidence self-consistency -----------------------------------
    check("evidence.revision", evidence.get("revision") in (2, 3, 4, 5), evidence.get("revision"))
    check("evidence.schema", evidence.get("schema_version") == "d12d005-a0-setup-generation-2", evidence.get("schema_version"))
    check("evidence.status", evidence.get("status") == "A0_SETUP_READY_NO_SOLVER", evidence.get("status"))
    check("evidence.solver_processes_started", evidence.get("solver_processes_started") == 0, evidence.get("solver_processes_started"))
    check("evidence.stop_before_run", evidence.get("stop_before_run") == 1, evidence.get("stop_before_run"))
    cases = evidence.get("cases", [])
    check("evidence.case_count", len(cases) == 6, len(cases))
    hc = evidence.get("hashing_convention") or {}
    check("evidence.hashing_convention", len(hc.get("per_entry_fields", [])) == 5 and "canonical" in str(hc.get("text_files")), list(hc))
    rel = evidence.get("relocatability") or {}
    check("evidence.relocatability", "case_dir_relative" in str(rel.get("case_dir_field")), rel.get("case_dir_field"))
    scan = evidence.get("process_spawn_scan") or {}
    check("evidence.process_spawn_scope", "documented_exception" in scan and scan.get("mode") == "ast_import_and_call_scan", list(scan))
    notes = evidence.get("revision_notes") or {}
    check("evidence.revision_notes", all(k in notes for k in ("A5_F-A0-01", "A5_F-A0-02", "A5_F-A0-03", "A5_F-A0-04", "A5_F-A0-05")), sorted(notes))
    bundle = evidence.get("bundle_requirements") or []
    check("evidence.bundle_requirements", len(bundle) == 7 and any("expected.json" in b for b in bundle), len(bundle))
    runner_rec = evidence.get("runner") or {}
    check("evidence.runner_dual", runner_rec.get("hash_mode") == "dual" and "sha256_canonical_lf" in runner_rec, list(runner_rec))
    script_recs = evidence.get("scripts") or []
    check("evidence.script_records", len(script_recs) == 9 and all(s.get("hash_mode") == "dual" for s in script_recs), len(script_recs))

    # ---- B. per case ----------------------------------------------------
    file_keys = ("model", "raw_setup", "contract_setup", "vkey", "csf", "geom_result_csv", "expected")
    case_fields = {}
    for case in cases:
        cid = case["case_id"]
        wd = run_dir / case["case_dir_relative"]
        check("case.%s.dir" % cid, wd.is_dir(), str(wd))
        recorded = {}
        for key in file_keys:
            rec = case.get(key) or {}
            name = rec.get("name")
            p = wd / name
            recorded[name] = rec
            check("case.%s.%s.exists" % (cid, key), p.is_file(), str(p))
            if p.is_file():
                raw_bytes = p.read_bytes()
                raw_ok = p.stat().st_size == rec.get("bytes_raw") and sha(raw_bytes) == rec.get("sha256_raw")
                can = canon(p)
                canonical_ok = len(can) == rec.get("bytes_canonical_lf") and sha(can) == rec.get("sha256_canonical_lf")
                checkout_normalised = bool(canonical_ok and bytes([13]) not in raw_bytes)
                check("case.%s.%s.raw_hash" % (cid, key), raw_ok or checkout_normalised,
                      "checkout_normalised" if (checkout_normalised and not raw_ok) else [p.stat().st_size, rec.get("bytes_raw")])
                check("case.%s.%s.canonical_hash" % (cid, key), canonical_ok, [len(can), rec.get("bytes_canonical_lf")])
        present = sorted(p.name for p in wd.iterdir() if p.is_file())
        check("case.%s.file_set" % cid, present == sorted(recorded), present)
        check("case.%s.no_local_vspgeom" % cid, not list(wd.glob("*.vspgeom")), None)
        check("case.%s.no_solver_artifacts" % cid,
              not [str(g) for g in SOLVER_GLOBS if list(wd.glob(g))], None)
        raw_text = (wd / case["raw_setup"]["name"]).read_text(encoding="utf-8", errors="replace")
        raw = parse_setup_kv(raw_text)
        check("case.%s.raw_defaults" % cid,
              raw.get("Vinf") == 100.0 and abs(raw.get("Rho", 0) - 0.002377) <= 1e-15 and raw.get("ReCref") == 1e7,
              [raw.get("Vinf"), raw.get("Rho"), raw.get("ReCref")])
        contract = json.loads((wd / "expected.json").read_text(encoding="utf-8"))["contract"]
        case_fields[cid] = parse_setup_kv((wd / case["contract_setup"]["name"]).read_text(encoding="utf-8", errors="replace"))
        check("case.%s.contract_17_fields" % cid, len(contract) == 17, len(contract))
        try:
            rb = runner.read_setup_file(str(wd / case["contract_setup"]["name"]), contract)
            check("case.%s.readback" % cid, rb.get("assertions") == 17, rb.get("assertions"))
        except Exception as exc:  # noqa: BLE001 - verification must record, not crash
            check("case.%s.readback" % cid, False, "%s: %s" % (type(exc).__name__, exc))
        vinf = float(contract["Vinf"]); mach = float(contract["Mach"])
        rex = float(contract["ReCref"]); cref = float(contract["Cref"])
        check("case.%s.vinf_formula" % cid, abs(vinf - mach * SPEED_OF_SOUND) <= max(1e-9, vinf * 1e-9), [vinf, mach * SPEED_OF_SOUND])
        check("case.%s.re_formula" % cid, abs(rex - RHO * vinf * cref / MU) <= max(1e-3, rex * 1e-9), [rex, RHO * vinf * cref / MU])
        geom = (wd / "geom_result_thin.csv").read_text(encoding="utf-8", errors="replace")
        check("case.%s.thin_geometry_flags" % cid, "GeometrySet,-1" in geom and "ThinGeometrySet,0" in geom, geom.splitlines()[6:9])
        thin = case["thin_geometry"]
        ep = Path(thin["external_path"])
        if ep.is_file():
            check("case.%s.external_vspgeom" % cid,
                  sha(ep.read_bytes()) == thin.get("sha256_raw") and ep.stat().st_size == thin.get("bytes_raw") and thin.get("outside_git") is True,
                  [ep.stat().st_size, thin.get("bytes_raw")])
        else:
            check("case.%s.external_vspgeom_recorded" % cid, thin.get("hash_mode") == "raw_external" and thin.get("outside_git") is True, "external artifact absent on host; recorded form only")
        if case.get("kind") == "std":
            text = (wd / case["model"]["name"]).read_text(encoding="utf-8", errors="replace")
            metrics = {k: xml_parm(text, k) for k in ("TotalSpan", "TotalArea", "TotalChord", "TotalAR")}
            check("case.%s.xml_metrics" % cid,
                  metrics == {"TotalSpan": 4.0, "TotalArea": 4.0, "TotalChord": 1.0, "TotalAR": 4.0}, metrics)
            check("case.%s.sym_xz" % cid, xml_parm(text, "Sym_Planar_Flag") == 2.0, xml_parm(text, "Sym_Planar_Flag"))
        else:
            expected_model = "wing355_baseline.vsp3" if cid.startswith("S5") else cid + "_model.vsp3"
            check("case.%s.model_expected_name" % cid, case["model"]["name"] == expected_model, case["model"]["name"])

    byid = {c["case_id"]: c for c in cases}

    def field_diff(a, b):
        fa, fb = case_fields[a], case_fields[b]
        return {k: (fa.get(k), fb.get(k)) for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}

    check("single_factor.S0_S1", field_diff("S0_STD_M0p1_base", "S1_STD_M0p1_wn128") == {"NumWakeNodes": (8.0, 128.0)}, field_diff("S0_STD_M0p1_base", "S1_STD_M0p1_wn128"))
    check("single_factor.S0_S2", field_diff("S0_STD_M0p1_base", "S2_STD_M0p1_wi0") == {"WakeIters": (5.0, 0.0)}, field_diff("S0_STD_M0p1_base", "S2_STD_M0p1_wi0"))
    check("single_factor.S3_S4", field_diff("S3_STD_M2p02_base", "S4_STD_M2p02_wn128") == {"NumWakeNodes": (8.0, 128.0)}, field_diff("S3_STD_M2p02_base", "S4_STD_M2p02_wn128"))
    check("single_factor.S0_S3_mach_only", {k: v for k, v in field_diff("S0_STD_M0p1_base", "S3_STD_M2p02_base").items()} == {"Mach": (0.1, 2.02), "Vinf": (29.506801840000005, 596.0373971680001), "ReCref": (239352.08001331755, 4834912.016269014)}, sorted(field_diff("S0_STD_M0p1_base", "S3_STD_M2p02_base")))

    # ---- C. S5 / D-12D-004 V0 cross-check ------------------------------
    s5 = byid["S5_D12_M2p02_base"]
    s5_dir = run_dir / s5["case_dir_relative"]
    rv = s5.get("reference_velocity") or {}
    check("S5.reference_velocity_annotated", abs(rv.get("delta_relative", 1) - 1.0047e-10) < 1e-13 and "byte-identical" in str(rv.get("decision")), rv.get("delta_relative"))
    if D12D004_V0.is_dir():
        v0_contract = D12D004_V0 / "wing355_thin_v0_contract.vspaero"
        v0_model = D12D004_V0 / "wing355_baseline.vsp3"
        check("S5.contract_byte_identical_v0", sha(canon(s5_dir / s5["contract_setup"]["name"])) == sha(canon(v0_contract)), None)
        check("S5.model_byte_identical_v0", sha(canon(s5_dir / s5["model"]["name"])) == sha(canon(v0_model)), None)
    else:
        check("S5.v0_reference_recorded", "D-12D-004 V0" in str(rv.get("source")), rv.get("source"))
    check("S5.external_vspgeom_sha", s5["thin_geometry"]["sha256_raw"] == "9fcda6d5d45300fbb0e20257c9ddc80540b44f5064a9566089d7ef85f9018d8e", s5["thin_geometry"].get("sha256_raw"))

    # ---- D. negative controls ------------------------------------------
    neg_root = run_dir / "evidence" / "a0" / "negative_controls"
    expectations = {
        "neg_wrong_sref.vspaero": "ContractViolation",
        "neg_wake_mismatch.vspaero": "ContractViolation",
        "neg_legacy.vspaero": "SetupFormatError",
    }
    neg_groups = sorted(p for p in neg_root.iterdir() if p.is_dir())
    for gdir in neg_groups:
        grp_contract = json.loads((run_dir / byid[gdir.name]["case_dir_relative"] / "expected.json").read_text(encoding="utf-8"))["contract"]
        for name, want in expectations.items():
            p = gdir / name
            label = "negative_control.%s.%s" % (gdir.name, name)
            if not p.is_file():
                check(label, False, "missing")
                continue
            try:
                parsed = runner.parse_setup_text(p.read_text(encoding="utf-8", errors="replace"), source=str(p))
                runner.assert_canonical(parsed)
                runner.validate_setup_fields(parsed["fields"], grp_contract, source=str(p))
                got = "ACCEPTED"
            except Exception as exc:  # noqa: BLE001
                got = type(exc).__name__
            check(label, got == want, got)
    check("negative_control.count", len(list(neg_root.rglob("*.vspaero"))) == 6, len(list(neg_root.rglob("*.vspaero"))))

    # ---- E. scripts ----------------------------------------------------
    for rec in script_recs:
        p = run_dir / rec["path_relative"]
        check("script.%s.exists" % rec["name"], p.is_file(), str(p))
        if not p.is_file():
            continue
        check("script.%s.canonical_hash" % rec["name"], sha(canon(p)) == rec.get("sha256_canonical_lf"), None)
        if rec.get("kind") != "regression_test":
            text = p.read_text(encoding="utf-8", errors="replace")
            hits = _scan_process_spawn(text)
            check("script.%s.no_process_spawn" % rec["name"], not hits, hits)
    frozen_test = run_dir / "scripts" / "test_vspaero7_runner_v1frozen.py"
    if frozen_test.is_file():
        text = frozen_test.read_text(encoding="utf-8", errors="replace")
        check("test.v1frozen_import_fixed", "import vspaero7_runner_v1frozen as R" in text and 'vspaero7_runner_v1frozen.py' in text, None)
    test_log = run_dir / "evidence" / "a0" / "v1frozen_test_run.log"
    check("test.v1frozen_log", test_log.is_file() and "Ran 22 tests" in test_log.read_text(encoding="utf-8", errors="replace") and "OK" in test_log.read_text(encoding="utf-8", errors="replace"), str(test_log))

    # ---- F. run-dir hygiene -------------------------------------------
    all_files = [p for p in run_dir.rglob("*") if p.is_file()]
    check("run_dir.file_count", len(all_files) >= 60, len(all_files))
    check("run_dir.no_vspgeom", not list(run_dir.rglob("*.vspgeom")), None)
    # A0 itself must be solver-free; the authorized A-batch executions under
    # evidence/v1 are billable solver outputs recorded by the budget ledger and are
    # therefore allowed there (and only there) in the same run directory.
    solver_suffixes = (".adb", ".history", ".polar", ".lod", ".groups", ".fem")
    a0_solver = [
        str(p.relative_to(run_dir))
        for p in (run_dir / "evidence" / "a0").rglob("*")
        if p.is_file() and p.suffix.lower() in solver_suffixes
    ]
    check("a0_dir.no_solver_artifacts", not a0_solver, a0_solver[:5])
    outside_v1 = [
        str(p.relative_to(run_dir))
        for p in all_files
        if p.suffix.lower() in solver_suffixes and "evidence/v1" not in p.as_posix()
    ]
    check("run_dir.solver_artifacts_only_under_v1", not outside_v1, outside_v1[:5])
    binary = []
    for p in all_files:
        if b"\x00" in p.read_bytes():
            binary.append(str(p.relative_to(run_dir)))
    check("run_dir.text_only", not binary, binary[:5])

    # ---- G. README claims ---------------------------------------------
    readme = (run_dir / "evidence" / "a0" / "README.md").read_text(encoding="utf-8", errors="replace")
    check("readme.canonical_convention", "canonical LF" in readme or "canonical-LF" in readme, None)
    check("readme.seven_files", "7 个文件" in readme or "7 files" in readme, None)
    check("readme.expected_json_bundle", "expected.json" in readme, None)
    check(
        "readme.revision_ok",
        "revision 2" in readme or "revision 3" in readme or "revision 4" in readme or "revision 5" in readme or "v2" in readme,
        None,
    )

    failed = [c for c in checks if not c["ok"]]
    out = {
        "artifact_kind": "D12D005_A0_VERIFICATION",
        "schema_version": "d12d005-a0-verification-2",
        "status": "PASS" if not failed else "FAIL",
        "run_dir": str(run_dir),
        "evidence_path": str(evidence_path),
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks_total": len(checks),
        "checks_failed": len(failed),
        "checks": checks,
        "hashing_convention_used": "text=canonical LF (equals committed blob), external raw bytes",
        "solver_processes_started": 0,
        "note": "disk-only verification; no OpenVSP call and no solver start",
    }
    if args.no_write:
        print("A0 VERIFICATION %s checks %d failed %d (no-write)" % (out["status"], out["checks_total"], out["checks_failed"]))
    else:
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("A0 VERIFICATION %s checks %d failed %d" % (out["status"], out["checks_total"], out["checks_failed"]))
    for c in failed:
        print("FAILED:", c["check"], c["detail"])
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
