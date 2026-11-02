# D-12D-004 V0 pre-gate evidence builder (zero solver starts).
#
# Stage 1: run the runner unit-test suite (unittest; 22 tests, 5 LD-001 branches).
# Stage 2: generate a fresh VSPAERO 7.2.2 setup with the OpenVSP 3.55.0 API using
#          VSPAEROSweep(StopBeforeRun=1); the source analysis forks no solver.
# Stage 3: inject the frozen 12D contract fields with the runner and read them back.
# Stage 4: negative controls (legacy format, default leak, setup rc, solver refusal,
#          solver-artifact scan) recorded as machine-checkable evidence.
# Stage 5: write evidence/v0_preflight_evidence.json and append a tooling event.
#
# No vspaero.exe / SU2 / RCAIDE Mission process is started by this script.
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
SCRIPTS = RUN / "scripts"
EVID = RUN / "evidence" / "v0"
SETUP_DIR = EVID / "setup_gen"
TESTS_DIR = EVID / "tests"
for p in (SETUP_DIR, TESTS_DIR):
    p.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SCRIPTS))
import vspaero7_runner as R  # noqa: E402

MODEL = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/lead/d12d003/setup355b/_model/wing355_baseline.vsp3")
OPENVSP_ROOT = Path("D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64")
VSPAERO_EXE = OPENVSP_ROOT / "vspaero.exe"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_unittest():
    log_path = TESTS_DIR / "test_vspaero7_runner.log"
    cmd = [sys.executable, "-m", "unittest", "test_vspaero7_runner", "-v"]
    proc = subprocess.run(cmd, cwd=str(SCRIPTS), capture_output=True, text=True)
    log_path.write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8", newline="\n")
    ran = None
    for line in proc.stderr.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            ran = int(line.split()[1])
    ok = proc.returncode == 0 and ran is not None and proc.stderr.strip().endswith("OK")
    return {
        "status": "PASS" if ok else "FAIL",
        "command": " ".join(cmd),
        "workdir": str(SCRIPTS),
        "returncode": proc.returncode,
        "tests_ran": ran,
        "log_path": str(log_path.resolve()),
        "log_sha256": sha256(log_path),
    }


def set_input(name, key, value):
    typ = vsp.GetAnalysisInputType(name, key)
    if typ == 2:
        vsp.SetDoubleAnalysisInput(name, key, [float(value)], 0)
    elif typ == 1:
        vsp.SetIntAnalysisInput(name, key, [int(value)], 0)
    elif typ == 3:
        vsp.SetStringAnalysisInput(name, key, [str(value)], 0)
    else:
        raise RuntimeError("unsupported analysis input type %r for %r" % (typ, key))


def generate_setup():
    os.add_dll_directory(str(OPENVSP_ROOT))
    for sub in ("python/openvsp", "python/deegeom_placeholder", "python/utilities", "python/openvsp_config"):
        pass
    for sub in ("python/openvsp", "python/degen_geom", "python/utilities", "python/openvsp_config"):
        p = str(OPENVSP_ROOT / sub)
        if p not in sys.path:
            sys.path.insert(0, p)
    global vsp
    import openvsp as vsp

    out_dir = SETUP_DIR
    old_cwd = os.getcwd()
    os.chdir(out_dir)
    try:
        local_model = out_dir / MODEL.name
        shutil.copyfile(MODEL, local_model)
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(local_model))
        vsp.Update()
        vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
        for k, v in {"GeomSet": vsp.SET_NONE, "ThinGeomSet": vsp.SET_ALL, "Symmetry": vsp.SYM_NONE}.items():
            set_input("VSPAEROComputeGeometry", k, v)
        rid_geom = vsp.ExecAnalysis("VSPAEROComputeGeometry")
        geom_csv = out_dir / "geom_result_thin.csv"
        try:
            vsp.WriteResultsCSVFile(rid_geom, str(geom_csv))
        except Exception as exc:  # noqa: BLE001 - evidence must record failures
            geom_csv.write_text("WriteResultsCSVFile failed: %r" % (exc,), encoding="utf-8")

        vsp.SetAnalysisInputDefaults("VSPAEROSweep")
        sweep = {
            "GeomSet": vsp.SET_NONE,
            "ThinGeomSet": vsp.SET_ALL,
            "Symmetry": vsp.SYM_NONE,
            "RefFlag": vsp.MANUAL_REF,
            "MACFlag": 0,
            "Sref": 358.25,
            "cref": 18.489893,
            "bref": 25.604638,
            "MachStart": 2.02,
            "MachEnd": 2.02,
            "MachNpts": 1,
            "AlphaStart": 2.0,
            "AlphaEnd": 2.0,
            "AlphaNpts": 1,
            "BetaStart": 0.0,
            "BetaEnd": 0.0,
            "BetaNpts": 1,
            "StopBeforeRun": 1,
            "RedirectFile": "stdout",
            "NCPU": 4,
            "Xcg": 16.821978259514246,
            "Ycg": 0.0,
            "Zcg": 0.0,
        }
        for k, v in sweep.items():
            set_input("VSPAEROSweep", k, v)
        try:
            stop_readback = vsp.GetIntAnalysisInput("VSPAEROSweep", "StopBeforeRun")[0]
        except Exception:  # noqa: BLE001 - report whichever API shape this build exposes
            stop_readback = vsp.GetDoubleAnalysisInput("VSPAEROSweep", "StopBeforeRun")[0]
        rid_sweep = vsp.ExecAnalysis("VSPAEROSweep")

        setups = sorted(out_dir.glob("*.vspaero"))
        geoms = sorted(out_dir.glob("*.vspgeom"))
        external_vspgeom = None
        if geoms:
            raw_dir = Path("D:/RCAIDE/outputs/concorde_metaopt") / RUN.name / "raw_artifacts"
            raw_dir.mkdir(parents=True, exist_ok=True)
            target = raw_dir / geoms[0].name
            shutil.move(str(geoms[0]), str(target))
            external_vspgeom = {
                "path": str(target.resolve()),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
                "outside_git": True,
            }
            geoms = []
        artifacts = {}
        for p in sorted(out_dir.iterdir()):
            if p.is_file():
                artifacts[p.name] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
        report = {
            "status": "PASS" if setups and external_vspgeom else "FAIL",
            "stage": "V0_SETUP_GENERATION_VSPAERO_7_2_2",
            "utc": utc_now(),
            "openvsp_version": vsp.GetVSPVersion(),
            "openvsp_root": str(OPENVSP_ROOT),
            "vspaero_exe": {"path": str(VSPAERO_EXE), "bytes": VSPAERO_EXE.stat().st_size, "sha256": sha256(VSPAERO_EXE)},
            "source_model": {"path": str(MODEL), "bytes": MODEL.stat().st_size, "sha256": sha256(MODEL)},
            "stop_before_run_expected": 1,
            "stop_before_run_readback": stop_readback,
            "solver_start_path": "VSPAEROSweep(StopBeforeRun=1) stops before VSPAERO fork (source: VSPAEROMgr.cpp guard before ForkCmd)",
            "analysis_result_ids": {"VSPAEROComputeGeometry": str(rid_geom), "VSPAEROSweep": str(rid_sweep)},
            "source_model_local_copy": {"path": str((out_dir / MODEL.name).resolve()), "bytes": (out_dir / MODEL.name).stat().st_size, "sha256": sha256(out_dir / MODEL.name)},
            "setup_file": str(setups[0].resolve()) if setups else None,
            "vspgeom_file": None,
            "vspgeom_external": external_vspgeom,
            "files": artifacts,
            "solver_artifacts_found": [s for s in ("*.adb", "*.history", "*.polar", "*.lod", "*.groups") if list(out_dir.glob(s))],
            "solver_processes_started": 0,
            "billable_numerical_analysis_starts": 0,
        }
        (EVID / "setup_generation_raw.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        return report
    finally:
        os.chdir(old_cwd)


def main():
    evidence = {
        "schema_version": "d12d004-v0-preflight-1",
        "utc": utc_now(),
        "run_id": RUN.name,
        "run_dir": str(RUN.resolve()),
        "authority": {
            "issue": "#4",
            "approval_comment_id": 6569140757,
            "category": "A-VSPAERO7-thin-LF (setup gate only)",
            "approved_v1_starts_max": 10,
            "v1_starts_used_so_far": 0,
            "note": "V0 is a zero-solver pre-gate; the 10-start budget is untouched.",
        },
        "solver_cases_started": 0,
        "billable_numerical_analysis_starts": 0,
    }

    evidence["stage_1_runner_tests"] = run_unittest()

    gen = generate_setup()
    evidence["stage_2_setup_generation"] = gen

    raw_setup = Path(gen["setup_file"]) if gen["setup_file"] else None
    negative = {}
    if raw_setup:
        # The raw VSPAEROSweep output carries VSPAERO defaults (Vinf/Rho/ReCref); it must
        # never be accepted as a contract case.
        try:
            R.read_setup_file(raw_setup)
            raw_verdict = {"rejected": False, "detail": "UNEXPECTED: raw default setup passed readback"}
        except R.ContractViolation as exc:
            kinds = sorted({v.get("kind") for v in getattr(exc, "violations", []) if isinstance(v, dict)})
            raw_verdict = {"rejected": True, "violation_count": len(getattr(exc, "violations", [])), "kinds": kinds}
        negative["raw_default_leak_rejected"] = raw_verdict

        contract_setup = SETUP_DIR / "wing355_thin_v0_contract.vspaero"
        inject = R.inject_contract_fields(raw_setup, contract_setup)
        evidence["stage_3_contract_injection"] = {
            "status": inject["status"],
            "assertions": inject["assertions"],
            "legacy_lines_normalized": inject["legacy_lines_normalized"],
            "target_path": str(contract_setup.resolve()),
            "target_bytes": contract_setup.stat().st_size,
            "target_sha256": sha256(contract_setup),
            "fields_checked": [c["field"] for c in inject["fields_checked"]],
        }
        # readback again from disk (not from memory) after injection
        evidence["stage_3_contract_injection"]["readback_from_disk"] = R.read_setup_file(contract_setup)["status"]

        # negative control: wrong Sref is rejected
        bad = (SETUP_DIR / "neg_wrong_sref.vspaero")
        bad.write_text(contract_setup.read_text(encoding="utf-8").replace("Sref = 358.25", "Sref = 400.0"), encoding="utf-8", newline="\n")
        try:
            R.read_setup_file(bad)
            negative["wrong_sref"] = {"rejected": False}
        except R.ContractViolation:
            negative["wrong_sref"] = {"rejected": True}
        # negative control: setup rc != 0 is a hard gate
        try:
            R.require_setup_success(1, contract_setup)
            negative["setup_rc_nonzero"] = {"rejected": False}
        except R.SetupCommandError:
            negative["setup_rc_nonzero"] = {"rejected": True}
        # negative control: no solver start path
        try:
            R.start_solver()
            negative["start_solver"] = {"rejected": False}
        except R.SolverStartRefused:
            negative["start_solver"] = {"rejected": True}
        # negative control: solver-artifact scan on the fresh setup dir
        try:
            R.assert_no_solver_artifacts(SETUP_DIR)
            negative["solver_artifacts_absent"] = {"status": "PASS"}
        except R.DataQualityError:
            negative["solver_artifacts_absent"] = {"status": "FAIL"}
        # negative control: legacy 'key value' lines are detected and normalized, strict mode rejects
        legacy = SETUP_DIR / "neg_legacy.vspaero"
        legacy.write_text("Mach 2.02\nSref 358.25\n", encoding="utf-8", newline="\n")
        try:
            R.inject_contract_fields(legacy, SETUP_DIR / "neg_legacy_out.vspaero", allow_legacy=True)
            legacy_ok = True
        except Exception:  # noqa: BLE001
            legacy_ok = False
        try:
            R.inject_contract_fields(legacy, SETUP_DIR / "neg_legacy_out_strict.vspaero", allow_legacy=False)
            strict_rejected = False
        except R.SetupFormatError:
            strict_rejected = True
        negative["legacy_format"] = {"normalized": legacy_ok, "strict_mode_rejected": strict_rejected}
    evidence["stage_4_negative_controls"] = negative

    # zero-solver bookkeeping: exactly one unbillable setup-generation event
    event = {
        "event_id": "V0-SETUP-001",
        "kind": "openvsp_api_setup_generation",
        "tool": "OpenVSP 3.55.0 Python API (VSPAEROSweep StopBeforeRun=1 + VSPAEROComputeGeometry)",
        "solver_processes_started": 0,
        "billable": False,
        "numerical_analysis": False,
        "utc": evidence["utc"],
        "evidence": "evidence/v0/setup_generation_raw.json",
        "note": "setup/mesh generation only; no vspaero.exe process, no solver case, budget untouched",
    }
    evidence["tooling_events"] = [event]
    evidence["limitations"] = [
        "Process-level proof of zero solver processes is not available on this host (no Procmon/4688/ETW/USN in this environment); the evidence is code-path + artifact based.",
        "The V0 setup uses the external wing-only VSP model asset (sha256 recorded); paired V1 cases must use single-version geometry.",
        "Raw VSPAEROSweep output contains VSPAERO defaults (Vinf=100, Rho=0.002377, ReCref=1e7); the runner rejects them unless contract-injected and read back.",
    ]
    evidence["stage_5_budget"] = {
        "v1_approved_starts": 10,
        "v1_starts_used": 0,
        "starts_remaining": 10,
        "preflight_only": True,
    }

    all_ok = (
        evidence["stage_1_runner_tests"]["status"] == "PASS"
        and gen["status"] == "PASS"
        and evidence.get("stage_3_contract_injection", {}).get("status") == "PASS"
        and evidence.get("stage_3_contract_injection", {}).get("readback_from_disk") == "PASS"
        and all(v.get("rejected", True) is not False for k, v in negative.items() if k != "legacy_format")
    )
    evidence["status"] = "V0_PREGATE_PASS" if all_ok else "V0_PREGATE_FAIL"
    out = EVID / "v0_preflight_evidence.json"
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": evidence["status"], "out": str(out), "sha256": sha256(out), "stage1": evidence["stage_1_runner_tests"]["status"], "gen": gen["status"]}, ensure_ascii=False))
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
