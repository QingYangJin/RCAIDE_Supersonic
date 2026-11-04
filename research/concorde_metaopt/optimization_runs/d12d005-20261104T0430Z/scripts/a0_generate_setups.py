
#!/usr/bin/env python
"""D-12D-005 A0: zero-solver setup generation for the A-line batch 1 (S0..S5).

Generates, for each case:
  <case>/<case>_model.vsp3        geometry (standard wing built via API, or the
                                  12D lifting-surface model copied from d12d004)
  <case>/<base>.vspgeom           thin VLM surface geometry (outside git; hashed)
  <case>/<base>.vkey / .csf       VSPAERO setup artifacts (must travel with .vspgeom)
  <case>/<base>.vspaero           RAW setup as written by VSPAEROSweep
  <case>/<case>_contract.vspaero  contract-injected setup, read back field by field
  <case>/expected.json            expected reference values + analytic sanity ranges

No solver is started.  VSPAEROSweep uses StopBeforeRun=1; every case directory is
asserted to contain no .adb/.history/.polar/.lod/.groups afterwards.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(r"D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z")
SETUP_ROOT = RUN_DIR / "evidence" / "a0" / "setup_gen"
RAW_ARTIFACTS = Path(r"D:/RCAIDE/outputs/concorde_metaopt/d12d005-20261104T0430Z/raw_artifacts/a0_setup")
RUNNER = RUN_DIR / "scripts" / "vspaero7_runner_v1frozen.py"
D12_MODEL_REF = Path(
    r"D:/RCAIDE-d12d004/research/concorde_metaopt/optimization_runs/"
    r"d12d004-vspaero72-lf-20261102T0500Z/evidence/v0/setup_gen/wing355_baseline.vsp3"
)
OPENVSP_ROOT = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64")
MU = 1.42161308e-05
RHO = 0.1153178340089936
A_SOUND = 295.0680184

D12_CONTRACT = {
    "Sref": 358.25, "Cref": 18.489893, "Bref": 25.604638,
    "X_cg": 16.821978259514246, "Y_cg": 0.0, "Z_cg": 0.0,
    "Mach": 2.02, "AoA": 2.0, "Beta": 0.0,
    "ReCref": 89397005.8767656, "Vinf": 596.0373972278921, "Rho": RHO,
    "Symmetry": 0, "NumWakeNodes": 8, "WakeIters": 5, "WakeRelax": 1.0, "FarDist": -1.0,
}

def std_contract(mach: float, wn: int, wi: int) -> dict:
    vinf = mach * A_SOUND
    return {
        "Sref": 4.0, "Cref": 1.0, "Bref": 4.0,
        "X_cg": 0.25, "Y_cg": 0.0, "Z_cg": 0.0,
        "Mach": mach, "AoA": 2.0, "Beta": 0.0,
        "ReCref": RHO * vinf * 1.0 / MU, "Vinf": vinf, "Rho": RHO,
        "Symmetry": 0, "NumWakeNodes": wn, "WakeIters": wi,
        "WakeRelax": 1.0, "FarDist": -1.0,
    }

CASES = [
    {"case_id": "S0_STD_M0p1_base", "kind": "std", "contract": std_contract(0.1, 8, 5),
     "note": "第1关 亚声速标准翼 基线（NumWakeNodes=8, WakeIters=5）"},
    {"case_id": "S1_STD_M0p1_wn128", "kind": "std", "contract": std_contract(0.1, 128, 5),
     "note": "第1关 单因素：仅 NumWakeNodes=128"},
    {"case_id": "S2_STD_M0p1_wi0", "kind": "std", "contract": std_contract(0.1, 8, 0),
     "note": "第1关 单因素：仅 WakeIters=0"},
    {"case_id": "S3_STD_M2p02_base", "kind": "std", "contract": std_contract(2.02, 8, 5),
     "note": "第2关 Mach2.02 标准薄翼 基线"},
    {"case_id": "S4_STD_M2p02_wn128", "kind": "std", "contract": std_contract(2.02, 128, 5),
     "note": "第2关 单因素：仅 NumWakeNodes=128"},
    {"case_id": "S5_D12_M2p02_base", "kind": "d12", "contract": dict(D12_CONTRACT),
     "note": "第3关 12D 主翼 thin 基线（合同参考量）"},
]

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def record(path: Path) -> dict:
    p = Path(path)
    return {"name": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}

def load_runner():
    spec = importlib.util.spec_from_file_location("vspaero7_runner_v1frozen", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def import_openvsp():
    root = str(OPENVSP_ROOT)
    os.add_dll_directory(root)
    for sub in ("python/openvsp", "python/degen_geom", "python/utilities", "python/openvsp_config"):
        p = os.path.join(root, sub)
        if p not in sys.path:
            sys.path.insert(0, p)
    import openvsp as vsp
    return vsp

def set_input(vsp, analysis: str, key: str, value) -> None:
    typ = vsp.GetAnalysisInputType(analysis, key)
    if typ == 2:
        vsp.SetDoubleAnalysisInput(analysis, key, [float(value)], 0)
    elif typ == 1:
        vsp.SetIntAnalysisInput(analysis, key, [int(value)], 0)
    elif typ == 3:
        vsp.SetStringAnalysisInput(analysis, key, [str(value)], 0)
    else:
        raise RuntimeError("unknown input type %r for %r" % (typ, key))

def build_std_wing(vsp, out_vsp3: Path) -> dict:
    vsp.ClearVSPModel()
    wid = vsp.AddGeom("WING")
    vsp.SetGeomName(wid, "STD_RECT_AR4")
    vsp.SetParmVal(vsp.FindParm(wid, "Sym_Planar_Flag", "Sym"), float(vsp.SYM_XZ))
    vsp.SetDriverGroup(wid, 1, vsp.SPAN_WSECT_DRIVER, vsp.TAPER_WSECT_DRIVER, vsp.ROOTC_WSECT_DRIVER)
    for name, value in (
        ("SectTess_U", 20), ("Span", 2.0), ("Taper", 1.0), ("Root_Chord", 1.0),
        ("Sweep", 0.0), ("Sweep_Location", 0.25),
    ):
        pid = vsp.FindParm(wid, name, "XSec_1")
        if not pid:
            raise RuntimeError("missing wing parm %s" % name)
        vsp.SetParmVal(pid, float(value))
    vsp.Update()
    metrics = {}
    for key in ("TotalSpan", "TotalArea", "TotalChord", "TotalAR"):
        pid = vsp.FindParm(wid, key, "WingGeom")
        metrics[key] = float(vsp.GetParmVal(pid)) if pid else None
    want = {"TotalSpan": 4.0, "TotalArea": 4.0, "TotalChord": 1.0, "TotalAR": 4.0}
    for key, expected in want.items():
        got = metrics.get(key)
        if got is None or abs(got - expected) > 1e-6:
            raise RuntimeError("standard wing metric %s expected %r got %r" % (key, expected, got))
    vsp.WriteVSPFile(str(out_vsp3), vsp.SET_ALL)
    return {"built": True, "geom_id": wid, "metrics": metrics, "expected_metrics": want,
            "sections": 2, "symmetry_flag": "SYM_XZ（镜像，全展为 Span 的 2 倍）",
            "airfoil": "OpenVSP 默认 4-series 对称翼型，Camber=0、ThickChord=0.10（VLM thin 使用中弧线=平板）"}

def generate_case(vsp, runner, case: dict) -> dict:
    case_id = case["case_id"]
    case_dir = SETUP_ROOT / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    cwd = os.getcwd()
    try:
        os.chdir(case_dir)
        if case["kind"] == "std":
            model_path = case_dir / (case_id + "_model.vsp3")
            geometry = build_std_wing(vsp, model_path)
        else:
            model_path = case_dir / "wing355_baseline.vsp3"
            shutil.copyfile(D12_MODEL_REF, model_path)
            geometry = {"built": False, "copied_from": str(D12_MODEL_REF), "source_sha256": sha256_file(D12_MODEL_REF)}
        base = model_path.stem
        # --- thin surface geometry (zero solver) ---
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(model_path))
        vsp.Update()
        vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
        set_input(vsp, "VSPAEROComputeGeometry", "GeomSet", vsp.SET_NONE)
        set_input(vsp, "VSPAEROComputeGeometry", "ThinGeomSet", vsp.SET_ALL)
        set_input(vsp, "VSPAEROComputeGeometry", "Symmetry", vsp.SYM_NONE)
        rid_geom = vsp.ExecAnalysis("VSPAEROComputeGeometry")
        geom_csv = case_dir / "geom_result_thin.csv"
        try:
            vsp.WriteResultsCSVFile(rid_geom, str(geom_csv))
        except Exception as exc:  # pragma: no cover - API variation
            geom_csv = None
            geom_csv_error = repr(exc)
        # --- setup generation only (StopBeforeRun=1) ---
        contract = case["contract"]
        vsp.SetAnalysisInputDefaults("VSPAEROSweep")
        sweep = {
            "GeomSet": vsp.SET_NONE, "ThinGeomSet": vsp.SET_ALL, "Symmetry": vsp.SYM_NONE,
            "RefFlag": vsp.MANUAL_REF, "MACFlag": 0,
            "Sref": contract["Sref"], "cref": contract["Cref"], "bref": contract["Bref"],
            "MachStart": contract["Mach"], "MachEnd": contract["Mach"], "MachNpts": 1,
            "AlphaStart": contract["AoA"], "AlphaEnd": contract["AoA"], "AlphaNpts": 1,
            "BetaStart": contract["Beta"], "BetaEnd": contract["Beta"], "BetaNpts": 1,
            "StopBeforeRun": 1, "RedirectFile": "stdout", "NCPU": 4,
            "Xcg": contract["X_cg"], "Ycg": contract["Y_cg"], "Zcg": contract["Z_cg"],
            "NumWakeNodes": contract["NumWakeNodes"], "WakeNumIter": contract["WakeIters"],
            "WakeRelax": contract["WakeRelax"], "FarDist": contract["FarDist"],
        }
        for key, value in sweep.items():
            set_input(vsp, "VSPAEROSweep", key, value)
        rid_sweep = vsp.ExecAnalysis("VSPAEROSweep")
        stop_readback = int(vsp.GetIntAnalysisInput("VSPAEROSweep", "StopBeforeRun")[0])
        if stop_readback != 1:
            raise RuntimeError("StopBeforeRun readback %r != 1" % stop_readback)
        raw_setup = Path(base + ".vspaero")
        if not raw_setup.is_file():
            raise RuntimeError("VSPAEROSweep did not write %s" % raw_setup)
        contract_setup = case_dir / (case_id + "_contract.vspaero")
        readback = runner.inject_contract_fields(
            raw_setup, contract_setup, contract,
            allow_legacy=True, expected_source="a0_generate_setups.py:%s" % case_id,
        )
        vspgeom = Path(base + ".vspgeom")
        if not vspgeom.is_file():
            raise RuntimeError("VSPAEROComputeGeometry did not write %s" % vspgeom)
        vkey = Path(base + ".vkey")
        csf = Path(base + ".csf")
        artifacts = sorted(p.name for p in case_dir.iterdir() if p.is_file())
        forbidden = [s for s in ("*.adb", "*.history", "*.polar", "*.lod", "*.groups", "*.fem") if list(case_dir.glob(s))]
        if forbidden:
            raise RuntimeError("solver artifacts present after setup generation: %r" % forbidden)
        # move .vspgeom outside git, keep hash/bytes in evidence
        RAW_ARTIFACTS.mkdir(parents=True, exist_ok=True)
        ext = RAW_ARTIFACTS / (case_id + ".vspgeom")
        shutil.copyfile(vspgeom, ext)
        vspgeom_rec = record(ext)
        vspgeom_rec["external_path"] = str(ext)
        vspgeom_rec["outside_git"] = True
        vspgeom_rec["local_copy"] = str(vspgeom)
        vspgeom.unlink()
        expected = {
            "schema_version": "d12d005-a0-expected-1",
            "case_id": case_id,
            "note": case["note"],
            "contract": contract,
            "readback_spec_source": str(RUNNER),
            "analytic_expectations": (std_analytic(contract["Mach"]) if case["kind"] == "std" else {
                "cl_expected_range": None,
                "note": "12D 主翼无独立解析参考；仅要求有限、符号/量级合理且与后续密度/扰动一致",
            }),
        }
        expected_path = case_dir / "expected.json"
        expected_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return {
            "case_id": case_id, "kind": case["kind"], "note": case["note"],
            "case_dir": str(case_dir), "model": record(model_path),
            "geometry": geometry,
            "thin_geometry": vspgeom_rec,
            "vkey": record(vkey) if vkey.is_file() else None,
            "csf": record(csf) if csf.is_file() else None,
            "raw_setup": record(raw_setup),
            "contract_setup": record(contract_setup),
            "expected": record(expected_path),
            "readback": readback,
            "geom_result_csv": record(geom_csv) if geom_csv and geom_csv.is_file() else None,
            "geom_result_csv_error": None if case["kind"] == "std" else locals().get("geom_csv_error"),
            "results": {"geom_result_id": str(rid_geom), "sweep_result_id": str(rid_sweep),
                        "stop_before_run_readback": stop_readback},
            "solver_artifacts_present": forbidden,
            "files_in_case_dir": sorted(p.name for p in case_dir.iterdir() if p.is_file()),
            "execution_bundle": {
                "note": "A2 执行时把 model.vsp3 + .vkey + .csf + contract.vspaero 复制到执行目录，并把 thin .vspgeom 从 external_path 复制为 <base>.vspgeom；随后把 .vkey 第 2 行改为该 .vspgeom 的绝对路径（D-12D-004 V1 根因修复），最后运行 vspaero.exe -omp 4 <base>",
                "model": model_path.name,
                "vspgeom_external_path": str(ext),
                "vspgeom_sha256": vspgeom_rec["sha256"],
                "vspgeom_bytes": vspgeom_rec["bytes"],
                "vkey": vkey.name if vkey.is_file() else None,
                "csf": csf.name if csf.is_file() else None,
                "setup": contract_setup.name,
            },
        }
    finally:
        os.chdir(cwd)

def std_analytic(mach: float) -> dict:
    ar = 4.0
    cl_alpha_rad = 2.0 * math.pi * ar / (math.sqrt(ar * ar + 4.0) + 2.0)
    cl_alpha_deg = cl_alpha_rad * math.pi / 180.0
    cl = cl_alpha_deg * 2.0
    cdi = cl * cl / (math.pi * ar)
    return {
        "theory": "Helmbold 有限翼展升力线近似 + 椭圆环量诱导阻力（e=1）",
        "AR": ar, "CL_alpha_per_rad": cl_alpha_rad, "CL_alpha_per_deg": cl_alpha_deg,
        "CL_at_2deg": cl,
        "CL_expected_range": [round(0.8 * cl, 6), round(1.2 * cl, 6)],
        "CDi_elliptic": cdi,
        "CDi_expected_range": [0.5 * cdi, 2.0 * cdi],
        "CDtot_expected_range": [0.4 * cdi, 3.0 * cdi],
        "gates": [
            "CL > 0 且落在 CL_expected_range（±20%）",
            "CDi > 0 且落在 CDi_expected_range（0.5x–2x 椭圆值）",
            "CDtot >= CDi > 0；无 NaN/IND/INF；|CL| < 1",
            "尾迹 |Gamma| 有界、末段残差为有限值且无 1e6 量级发散",
        ],
    }

def negative_controls(runner, case_id: str) -> dict:
    case_dir = SETUP_ROOT / case_id
    neg_dir = RUN_DIR / "evidence" / "a0" / "negative_controls" / case_id
    neg_dir.mkdir(parents=True, exist_ok=True)
    src = case_dir / (case_id + "_contract.vspaero")
    contract = next(c for c in CASES if c["case_id"] == case_id)["contract"]
    checks = []

    def rewrite_field(text: str, field: str, new_value: str) -> str:
        lines = []
        hit = False
        for raw in text.splitlines():
            if raw.strip().startswith(field + " =") or raw.strip().startswith(field + "="):
                lines.append("%s = %s" % (field, new_value))
                hit = True
            else:
                lines.append(raw)
        if not hit:
            raise RuntimeError("negative control field %s not found" % field)
        return "\n".join(lines) + "\n"

    bad_sref = neg_dir / "neg_wrong_sref.vspaero"
    text = src.read_text(encoding="utf-8")
    bad_sref.write_text(rewrite_field(text, "Sref", "100.0"), encoding="utf-8", newline="\n")
    try:
        runner.read_setup_file(bad_sref, contract)
        checks.append({"control": "wrong_sref", "result": "FAIL_NOT_REJECTED"})
    except runner.ContractViolation as exc:
        checks.append({"control": "wrong_sref", "result": "REJECTED", "detail": str(exc)[:200]})
    legacy = neg_dir / "neg_legacy.vspaero"
    legacy.write_text("Sref 4.0\nMach 0.1\n", encoding="utf-8", newline="\n")
    try:
        runner.read_setup_file(legacy, contract, require_canonical=True)
        checks.append({"control": "legacy_no_equals", "result": "FAIL_NOT_REJECTED"})
    except runner.SetupFormatError as exc:
        checks.append({"control": "legacy_no_equals", "result": "REJECTED", "detail": str(exc)[:200]})
    wake = neg_dir / "neg_wake_mismatch.vspaero"
    wake.write_text(rewrite_field(text, "NumWakeNodes", "999"), encoding="utf-8", newline="\n")
    try:
        runner.read_setup_file(wake, contract)
        checks.append({"control": "wake_node_mismatch", "result": "FAIL_NOT_REJECTED"})
    except runner.ContractViolation as exc:
        checks.append({"control": "wake_node_mismatch", "result": "REJECTED", "detail": str(exc)[:200]})
    return {"case_id": case_id, "checks": checks,
            "files": sorted(p.name for p in neg_dir.iterdir() if p.is_file()),
            "all_rejected": all(c["result"] == "REJECTED" for c in checks)}

def main() -> int:
    started = datetime.now(timezone.utc)
    vsp = import_openvsp()
    runner = load_runner()
    SETUP_ROOT.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema_version": "d12d005-a0-setup-generation-1",
        "artifact_kind": "D12D005_A0_SETUP_GENERATION",
        "generated_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": RUN_DIR.name,
        "openvsp": {"version": vsp.GetVSPVersion(), "root": str(OPENVSP_ROOT)},
        "solver_processes_started": 0,
        "stop_before_run": 1,
        "vspaero_install": str(OPENVSP_ROOT / "vspaero.exe"),
        "vspaero_sha256": sha256_file(OPENVSP_ROOT / "vspaero.exe"),
        "runner": record(RUNNER),
        "cases": [],
        "negative_controls": [],
    }
    for case in CASES:
        print("=== generating", case["case_id"], flush=True)
        rec = generate_case(vsp, runner, case)
        evidence["cases"].append(rec)
        print("  readback", rec["readback"]["status"], "assertions", rec["readback"].get("assertions"),
              "vspgeom", rec["thin_geometry"]["bytes"], flush=True)
    for case_id in ("S0_STD_M0p1_base", "S3_STD_M2p02_base"):
        evidence["negative_controls"].append(negative_controls(runner, case_id))
    cases_ok = all(c["readback"]["status"] == "PASS" and not c["solver_artifacts_present"] for c in evidence["cases"])
    neg_ok = all(n["all_rejected"] for n in evidence["negative_controls"])
    evidence["status"] = "A0_SETUP_READY_NO_SOLVER" if (cases_ok and neg_ok) else "A0_SETUP_FAILED"
    evidence["summary"] = {
        "case_count": len(evidence["cases"]),
        "readback_pass": cases_ok,
        "negative_controls_pass": neg_ok,
        "solver_starts": 0,
        "note": "全部 .vspaero 由 VSPAEROSweep StopBeforeRun=1 生成；thin .vspgeom 由 VSPAEROComputeGeometry 生成；本脚本不含任何 solver 启动路径",
    }
    out = RUN_DIR / "evidence" / "a0" / "setup_generation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("STATUS", evidence["status"], "->", out, flush=True)
    return 0 if evidence["status"] == "A0_SETUP_READY_NO_SOLVER" else 1

if __name__ == "__main__":
    raise SystemExit(main())
