
import json, math, re
from pathlib import Path
import numpy as np

WAVE = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/wave")
src = (Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/lead") / "area_rule_recompute.py").read_text()
# reuse by exec of the two functions
ns = {}
exec(compile(src.split("def parse_txt")[0], "emlord_part", "exec"), ns)
emlord = ns["emlord"]

def parse_txt(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    thetas, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("Inlet Area:", "Exit Area:", "...Wave", "CDWave:", "Mach:", "Set Name:")):
            if line.startswith(("CDWave:", "Mach:", "Set Name:")):
                cur = None
            continue
        m = re.match(r"Theta:\s*([-\d.]+),\s*Start:\s*([-\d.]+),\s*End:\s*([-\d.]+)", line)
        if m:
            cur = {"theta_deg": float(m.group(1)), "start": float(m.group(2)), "end": float(m.group(3)), "x_norm": [], "area": []}
            thetas.append(cur)
            continue
        if cur is not None and "," in line:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                try:
                    cur["x_norm"].append(float(parts[0])); cur["area"].append(float(parts[1]))
                except ValueError:
                    pass
    return thetas

def profile_stats(case, want_theta):
    thetas = parse_txt(next((WAVE / case).glob("Unnamed_WaveDrag_M*.txt")))
    t = min(thetas, key=lambda r: abs(r["theta_deg"] - want_theta))
    s = np.array(t["area"], float)
    x = np.array(t["x_norm"], float)
    L = t["end"] - t["start"]
    donq = emlord(list(t["start"] + x * L), list(s))
    # residuals / conditioning of the EL matrix: rebuild pqq at this n
    n = len(s)
    # count of exactly-zero areas (outside the cut body) and largest jumps
    zeros = int(np.sum(np.abs(s) < 1e-9))
    d = np.diff(s)
    return {
        "case": case, "theta_deg": t["theta_deg"], "n_slices": n,
        "area_min": float(s.min()), "area_max": float(s.max()),
        "n_zero_area_slices": zeros,
        "n_negative_area_slices": int(np.sum(s < -1e-9)),
        "max_abs_jump_between_slices_m2": float(np.abs(d).max()),
        "n_jumps_gt_0p1m2": int(np.sum(np.abs(d) > 0.1)),
        "rms_second_difference": float(np.sqrt(np.mean(np.diff(s, 2) ** 2))),
        "donq_m2": donq,
        "nonzero_first_index": int(np.argmax(np.abs(s) > 1e-9)),
        "nonzero_last_index": n - 1 - int(np.argmax(np.abs(s[::-1]) > 1e-9)),
    }

diag = {
    "WAVE-05_theta73_52": profile_stats("WAVE-05", 73.52),
    "WAVE-05_theta0": profile_stats("WAVE-05", 0.0),
    "WAVE-02_theta56_57": profile_stats("WAVE-02", 56.57),
    "WAVE-02_theta0": profile_stats("WAVE-02", 0.0),
}

# condition number of the pqq matrix as a function of n on a uniform grid
def cond_el(n):
    # build matrix exactly like emlord for a synthetic smooth area distribution
    naxs = list(np.linspace(0.0, 1.0, n))
    sarea = list(4 * np.array(naxs) * (1 - np.array(naxs)))
    prts = n
    x = [0.0] * prts
    k = 0
    for i in range(prts):
        x[k] = naxs[i]
        if k == prts - 3:
            break
        k += 1
        if i == 0 or i == prts - 1:
            k -= 1
    m = prts - 2
    pqq = np.zeros((m, m))
    for i in range(m):
        nx = (x[i] - naxs[0]) / (naxs[-1] - naxs[0])
        for j in range(i, prts):
            ny = (x[j] - naxs[0]) / (naxs[-1] - naxs[0])
            e = (nx - ny) ** 2
            e1 = nx + ny - 2.0 * nx * ny
            e2 = 2.0 * math.sqrt(max(nx * ny * (1.0 - nx) * (1.0 - ny), 0.0))
            if i == j:
                v = e1 * e2
            elif e1 + e2 <= 0 or e1 - e2 <= 0:
                v = float("nan")
            else:
                v = 0.5 * e * math.log((e1 - e2) / (e1 + e2)) + e1 * e2
            if j < m:
                pqq[j, i] = v
                pqq[i, j] = v
    return float(np.linalg.cond(pqq))

diag["condition_number_vs_n"] = {str(n): cond_el(n) for n in (50, 100, 200, 400, 800)}
out = WAVE / "area_rule_diagnostics.json"
out.write_text(json.dumps(diag, indent=1), encoding="utf-8")
print(json.dumps(diag, indent=1))
