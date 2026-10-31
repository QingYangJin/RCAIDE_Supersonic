"""Run one LF case end to end: OpenVSP geometry -> DegenGeom -> VSPAERO setup -> solve -> polar parse.

Counts exactly one numerical analysis start in the D-12D-002 ledger (unless --dry-geometry).
"""
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

EXT = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
LEAD = EXT / "lead"
PY39 = r"D:/Anaconda/envs/SUAVE/python.exe"
VSPAERO = r"D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64/vspaero.exe"
PY311 = r"D:/RCAIDE/envs/RCAIDE/python.exe"
LEDGER = LEAD / "ledger.py"

REF = {"Sref": 358.25, "Cref": 18.489893, "Bref": 25.604638, "Mach": 2.02,
       "Vinf": 596.0373972278921, "Rho": 0.1153178340089936, "ReCref": 89397005.8767656,
       "X_cg": 16.821978259514246}


def run(cmd, cwd=None, timeout=600):
    start = time.time()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr, time.time() - start


def patch_template(template_path):
    lines = template_path.read_text(encoding="utf-8").splitlines()
    keys = {"Sref": "Sref", "Cref": "Cref", "Bref": "Bref", "Mach": "Mach",
            "X_cg": "X_cg", "Y_cg": "Y_cg", "Z_cg": "Z_cg",
            "Vinf": "Vinf", "Vref": "Vref", "Rho": "Rho", "ReCref": "ReCref"}
    mapped = {"Y_cg": 0.0, "Z_cg": 0.0, "Vref": REF["Vinf"]}
    out, mismatches = [], []
    for line in lines:
        m = re.match(r"^(\w+)\s+(.*)$", line)
        if m and m.group(1) in keys:
            token = keys[m.group(1)]
            value = mapped.get(token, REF.get(token))
            if value is None:
                out.append(line)
                continue
            out.append("%s = %s" % (token, value))
        else:
            out.append(line)
    template_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    # verify
    text = template_path.read_text(encoding="utf-8")
    for token in ("Sref", "Cref", "Bref", "Mach", "X_cg", "Vinf", "Rho", "ReCref"):
        if token not in text:
            mismatches.append(token)
    return mismatches


def parse_polar(polar_path):
    lines = [l for l in polar_path.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    header = re.split(r"[\s,]+", lines[0].strip())
    rows = []
    for line in lines[1:]:
        toks = re.split(r"[\s,]+", line.strip())
        if len(toks) < len(header):
            continue
        record = {}
        for i, name in enumerate(header):
            try:
                record[name] = float(toks[i])
            except ValueError:
                record[name] = toks[i]
        if len(toks) > len(header):
            record["_extra_unlabeled"] = [float(t) for t in toks[len(header):] if _is_num(t)]
        rows.append(record)
    return {"header": header, "rows": rows}


def _is_num(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def ledger(cmd_args):
    return run([PY311, "-E", "-s", "-B", str(LEDGER)] + cmd_args, cwd=str(LEAD), timeout=120)


def main():
    case = sys.argv[1]
    dry = "--dry-geometry" in sys.argv
    cdir = EXT / "lf" / case
    request_path = cdir / "request.json"
    if not request_path.is_file():
        raise SystemExit("missing request: %s" % request_path)
    basename = json.loads(request_path.read_text(encoding="utf-8"))["export"]["basename"]
    summary = {"case": case, "basename": basename, "steps": []}
    # geometry + DegenGeom
    rc, out, err, wall = run([PY39, "-u", str(LEAD / "lf_worker.py"), str(request_path),
                              str(cdir / "worker_result.json")], cwd=str(cdir), timeout=300)
    summary["steps"].append({"step": "openvsp_geometry", "returncode": rc, "wall_s": round(wall, 3),
                             "stderr_tail": err[-500:]})
    if rc != 0:
        print(json.dumps(summary, indent=1))
        return 1
    if dry:
        summary["dry_geometry_only"] = True
        print(json.dumps(summary, indent=1))
        return 0
    # VSPAERO setup template
    rc, out, err, wall = run([VSPAERO, "-setup", "-sref", "358.25", "-bref", "25.604638",
                              "-cref", "18.489893", "-cg", "0", "0", "0", "-mach", "2.02",
                              "-aoa", "1.0", "END", "-beta", "0", "END", basename + "_DegenGeom"],
                             cwd=str(cdir), timeout=300)
    template = cdir / (basename + "_DegenGeom.vspaero")
    summary["steps"].append({"step": "vspaero_setup", "returncode": rc, "template_exists": template.is_file()})
    if not template.is_file():
        print(json.dumps(summary, indent=1))
        return 1
    mismatches = patch_template(template)
    summary["template_mismatches"] = mismatches
    # ledger start
    command_text = "vspaero -omp 4 -fs 2.02 END -2 0 2 4 6 END 0 END %s_DegenGeom" % basename
    rc, out, err, wall = ledger(["start", "VSPAERO_LF", case,
                                 "VSPAERO thin-surface LF polar, main wing only, Mach 2.02, alpha -2..6 deg",
                                 command_text])
    summary["steps"].append({"step": "ledger_start", "returncode": rc, "stdout": out.strip()})
    if rc != 0:
        print(json.dumps(summary, indent=1))
        return 1
    # solve
    rc, out, err, wall = run([VSPAERO, "-omp", "4", "-fs", "2.02", "END", "-2", "0", "2", "4", "6",
                              "END", "0", "END", basename + "_DegenGeom"], cwd=str(cdir), timeout=900)
    status = "SOLVED" if rc == 0 else "FAILED"
    polar = cdir / (basename + "_DegenGeom.polar")
    rc2, out2, err2, wall2 = ledger(["finish", case, status, "%.3f" % wall, str(rc),
                                     "--files", ";".join("%s:%d" % (p.name, p.stat().st_size)
                                                         for p in sorted(cdir.iterdir())
                                                         if p.is_file())])
    summary["steps"].append({"step": "vspaero_solve", "returncode": rc, "wall_s": round(wall, 3),
                             "status": status, "polar_exists": polar.is_file(),
                             "stderr_tail": err[-800:]})
    summary["ledger_finish"] = {"returncode": rc2, "stdout": out2.strip()}
    if polar.is_file():
        parsed = parse_polar(polar)
        (cdir / "polar_parsed.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        (EXT / "lead" / "runs").mkdir(parents=True, exist_ok=True)
        (EXT / "lead" / "runs" / (case + "_polar.json")).write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        summary["polar_rows"] = len(parsed["rows"])
        summary["polar_header"] = parsed["header"]
    (cdir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0 if status == "SOLVED" else 1


if __name__ == "__main__":
    sys.exit(main())
