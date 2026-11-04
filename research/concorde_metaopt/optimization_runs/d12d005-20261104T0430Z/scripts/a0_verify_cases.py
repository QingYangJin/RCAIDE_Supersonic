
#!/usr/bin/env python
"""D-12D-005 A0 independent verification (no OpenVSP, no solver).

Re-checks the A0 setup bundle from disk only:
  * evidence JSON self-consistency and recorded hashes/bytes;
  * canonical contract setup readback via the frozen v1 runner contract;
  * raw setup still carries VSPAERO defaults (proves injection is required);
  * single-factor wake settings between S0/S1/S2 and S3/S4;
  * standard-wing geometry metrics parsed from the .vsp3 XML;
  * 12D model copy equals the d12d004 reference byte-for-byte;
  * no solver artifacts, no local .vspgeom, external .vspgeom hashes;
  * negative controls are still rejected;
  * generator/analyzer scripts contain no process-spawn path.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(r"D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z")
EVIDENCE = RUN_DIR / "evidence" / "a0" / "setup_generation.json"
NEG_ROOT = RUN_DIR / "evidence" / "a0" / "negative_controls"
RUNNER = RUN_DIR / "scripts" / "vspaero7_runner_v1frozen.py"
D12_REF = Path(
    r"D:/RCAIDE-d12d004/research/concorde_metaopt/optimization_runs/"
    r"d12d004-vspaero72-lf-20261102T0500Z/evidence/v0/setup_gen/wing355_baseline.vsp3"
)
OUT = RUN_DIR / "evidence" / "a0" / "a0_verification.json"
SOLVER_GLOBS = ("*.adb", "*.history", "*.polar", "*.lod", "*.groups", "*.fem")


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_runner():
    spec = importlib.util.spec_from_file_location("vspaero7_runner_v1frozen", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def xml_parm(text: str, name: str) -> float | None:
    m = re.search(r'<%s Value="([-+0-9.eE]+)"' % re.escape(name), text)
    return float(m.group(1)) if m else None


def main() -> int:
    checks = []

    def check(name, ok, detail=None):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    runner = load_runner()
    check("evidence.status", ev.get("status") == "A0_SETUP_READY_NO_SOLVER", ev.get("status"))
    check("evidence.solver_processes_started", ev.get("solver_processes_started") == 0, ev.get("solver_processes_started"))
    check("evidence.case_count", len(ev.get("cases", [])) == 6, len(ev.get("cases", [])))
    check("evidence.stop_before_run", ev.get("stop_before_run") == 1)
    check("vspaero.binary.sha256", sha(Path(ev["vspaero_install"])) == ev["vspaero_sha256"])
    check("runner.sha256", sha(RUNNER) == ev["runner"]["sha256"])
    for script in ("a0_generate_setups.py", "a0_analyze_v1_divergence.py"):
        text = (RUN_DIR / "scripts" / script).read_text(encoding="utf-8")
        banned = [tok for tok in ("subprocess", "os.system", "os.popen", "Popen", "shell=True") if tok in text]
        check("script.no_process_spawn:%s" % script, not banned, banned or None)

    parsed_setups = {}
    for case in ev["cases"]:
        cid = case["case_id"]
        cdir = Path(case["case_dir"])
        prefix = "case[%s]" % cid
        check(prefix + ".dir", cdir.is_dir(), str(cdir))
        for rec_name in ("model", "raw_setup", "contract_setup", "expected"):
            rec = case.get(rec_name) or {}
            p = cdir / rec.get("name", "")
            check(prefix + ".%s.exists" % rec_name, p.is_file(), rec.get("name"))
            if p.is_file():
                check(prefix + ".%s.sha256" % rec_name, sha(p) == rec.get("sha256"), rec.get("sha256"))
                check(prefix + ".%s.bytes" % rec_name, p.stat().st_size == rec.get("bytes"), rec.get("bytes"))
        check(prefix + ".no_local_vspgeom", not list(cdir.glob("*.vspgeom")))
        check(prefix + ".no_solver_artifacts", not [g for g in SOLVER_GLOBS if list(cdir.glob(g))])
        for name in ("vkey", "csf"):
            rec = case.get(name) or {}
            p = cdir / rec.get("name", "")
            check(prefix + ".%s.exists" % name, p.is_file() and sha(p) == rec.get("sha256"))
        ext = case["thin_geometry"]
        p = Path(ext["external_path"])
        check(prefix + ".external_vspgeom", p.is_file() and sha(p) == ext["sha256"] and p.stat().st_size == ext["bytes"])
        check(prefix + ".bundle.vspgeom", case["execution_bundle"]["vspgeom_sha256"] == ext["sha256"])
        # contract setup readback (independent re-parse from disk)
        contract = json.loads((cdir / "expected.json").read_text(encoding="utf-8"))["contract"]
        report = runner.read_setup_file(cdir / case["contract_setup"]["name"], contract)
        parsed_setups[cid] = runner.parse_setup_text((cdir / case["contract_setup"]["name"]).read_text(encoding="utf-8"))["fields"]
        check(prefix + ".readback_17_assertions", report["status"] == "PASS" and report["assertions"] == 17, report["assertions"])
        # raw setup still contains defaults => injection is required, raw is never used directly
        raw_text = (cdir / case["raw_setup"]["name"]).read_text(encoding="utf-8")
        raw_fields = runner.parse_setup_text(raw_text)["fields"]
        defaults_present = (
            abs(float(raw_fields.get("Vinf", "nan")) - 100.0) < 1e-9
            and abs(float(raw_fields.get("Rho", "nan")) - 0.002377) < 1e-12
            and abs(float(raw_fields.get("ReCref", "nan")) - 1.0e7) < 1e-6
        )
        check(prefix + ".raw_has_vspaero_defaults", defaults_present)
        # expected.json analytic block for standard-wing cases
        expected = json.loads((cdir / "expected.json").read_text(encoding="utf-8"))
        if case["kind"] == "std":
            ana = expected["analytic_expectations"]
            check(prefix + ".analytic_Ar", abs(ana["AR"] - 4.0) < 1e-12, ana["AR"])
            check(prefix + ".analytic_CL_range", 0.09 < ana["CL_at_2deg"] < 0.20, ana["CL_at_2deg"])
            model_text = (cdir / case["model"]["name"]).read_text(encoding="utf-8", errors="replace")
            metrics = {k: xml_parm(model_text, k) for k in ("TotalSpan", "TotalArea", "TotalChord", "TotalAR")}
            check(prefix + ".vsp3_geometry_metrics",
                  metrics == {"TotalSpan": 4.0, "TotalArea": 4.0, "TotalChord": 1.0, "TotalAR": 4.0}, metrics)
            check(prefix + ".vsp3_sym_planar_xz", xml_parm(model_text, "Sym_Planar_Flag") == 2.0)

    # single-factor wake diffs
    def diff_fields(a, b):
        keys = set(a) | set(b)
        return {k: (a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)}

    d01 = diff_fields(parsed_setups["S0_STD_M0p1_base"], parsed_setups["S1_STD_M0p1_wn128"])
    check("diff.S0_S1.single_field_NumWakeNodes",
          list(d01) == ["NumWakeNodes"] and d01["NumWakeNodes"] == ("8", "128"), d01)
    d02 = diff_fields(parsed_setups["S0_STD_M0p1_base"], parsed_setups["S2_STD_M0p1_wi0"])
    check("diff.S0_S2.single_field_WakeIters",
          list(d02) == ["WakeIters"] and d02["WakeIters"] == ("5", "0"), d02)
    d34 = diff_fields(parsed_setups["S3_STD_M2p02_base"], parsed_setups["S4_STD_M2p02_wn128"])
    check("diff.S3_S4.single_field_NumWakeNodes",
          list(d34) == ["NumWakeNodes"] and d34["NumWakeNodes"] == ("8", "128"), d34)

    # 12D model copy byte-identical to the d12d004 reference
    s5 = next(c for c in ev["cases"] if c["case_id"] == "S5_D12_M2p02_base")
    check("d12.model.copy_from_d12d004", sha(Path(s5["model"]["name"]) if Path(s5["model"]["name"]).is_absolute() else Path(s5["case_dir"]) / s5["model"]["name"]) == sha(D12_REF))
    check("d12.external_vspgeom_matches_v0", s5["thin_geometry"]["sha256"] == "9fcda6d5d45300fbb0e20257c9ddc80540b44f5064a9566089d7ef85f9018d8e")

    # negative controls
    for neg in ev["negative_controls"]:
        cid = neg["case_id"]
        contract = json.loads((RUN_DIR / "evidence" / "a0" / "setup_gen" / cid / "expected.json").read_text(encoding="utf-8"))["contract"]
        results = {}
        for rel, exc_type in (("neg_wrong_sref.vspaero", runner.ContractViolation),
                              ("neg_legacy.vspaero", runner.SetupFormatError),
                              ("neg_wake_mismatch.vspaero", runner.ContractViolation)):
            p = NEG_ROOT / cid / rel
            try:
                runner.read_setup_file(p, contract)
                results[rel] = "NOT_REJECTED"
            except exc_type:
                results[rel] = "REJECTED"
            except runner.RunnerError as exc:
                results[rel] = "REJECTED_OTHER:%s" % type(exc).__name__
        check("neg.%s.rejected" % cid, all(v == "REJECTED" for v in results.values()), results)

    # repository text-only + no local vspgeom anywhere in the run dir
    binaries = []
    for p in RUN_DIR.rglob("*"):
        if p.is_file() and p.suffix not in (".png",):
            try:
                p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                binaries.append(str(p.relative_to(RUN_DIR)))
    check("run_dir.text_only", not binaries, binaries[:5])
    check("run_dir.no_vspgeom", not list(RUN_DIR.rglob("*.vspgeom")))

    ok = all(c["ok"] for c in checks)
    out = {
        "schema_version": "d12d005-a0-verification-1",
        "artifact_kind": "D12D005_A0_VERIFICATION",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if ok else "FAIL",
        "checks_total": len(checks),
        "checks_failed": sum(0 if c["ok"] else 1 for c in checks),
        "checks": checks,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("A0 VERIFICATION", out["status"], "checks", out["checks_total"], "failed", out["checks_failed"])
    for c in checks:
        if not c["ok"]:
            print("FAILED:", c["check"], c["detail"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
