import json, re, math, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
CASES = ROOT / "cases"
L_REF = 1333704.4
RHO = 0.1153178340089936
V_BASE = 596.0373972278921
REC_BASE = 89397005.8767656

def parse_deck(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    out = {}
    for key in ("Sref","Mach","ReCref","Vinf","Rho"):
        m = re.search(rf"^{key}\s*=\s*([^\s,]+)", text, re.M)
        if m: out[key] = float(m.group(1))
    m = re.search(r"^AoA\s*=\s*(.+)$", text, re.M)
    out["AoA"] = [float(x) for x in m.group(1).split(",")] if m else []
    return out

def close(a, b, rel=1e-9):
    return abs(a-b) <= rel*max(abs(a), abs(b), 1.0)

checks=[]; rows=[]
for case_dir in sorted(p for p in CASES.iterdir() if p.is_dir() and (p/"task_spec.json").is_file()):
    spec = json.loads((case_dir/"task_spec.json").read_text(encoding="utf-8"))
    plan = json.loads((case_dir/"plan.json").read_text(encoding="utf-8"))
    appr = json.loads((case_dir/"approval.json").read_text(encoding="utf-8"))
    cin = json.loads((case_dir/"case_inputs.json").read_text(encoding="utf-8"))
    basename = plan["command"]["argv"][-1]
    deck = parse_deck(case_dir / (basename + ".vspaero"))
    vinf = spec["mach"] * (V_BASE/2.02)
    rec = REC_BASE * (vinf/V_BASE)
    q = 0.5*RHO*vinf*vinf
    cl = L_REF/(q*spec["geometry"].get("sref_m2", 358.25) if "geometry" in spec else 358.25)
    expected_cl = L_REF/(q*cin["sref_m2"])
    checks += [
      ("deck_sref", close(deck.get("Sref",0), cin["sref_m2"])),
      ("deck_mach", close(deck.get("Mach",0), spec["mach"])),
      ("deck_vinf", close(deck.get("Vinf",0), vinf)),
      ("deck_rho", close(deck.get("Rho",0), RHO)),
      ("deck_recref", close(deck.get("ReCref",0), rec)),
      ("case_inputs_q", close(cin["q_pa"], q)),
      ("case_inputs_cl", close(cin["cl_required"], expected_cl)),
      ("plan_sha", appr["plan_sha256"] == plan["_plan_sha256"] if "_plan_sha256" in plan else True),
      ("no_solver_started", cin.get("solver_started") is False and cin.get("physical_solver_starts")==0),
      ("alpha_count", len(deck["AoA"]) == len(cin["alpha_list_deg"])),
      ("alpha_first", close(deck["AoA"][0], cin["alpha_list_deg"][0]) if deck["AoA"] else False),
      ("alpha_last", close(deck["AoA"][-1], cin["alpha_list_deg"][-1]) if deck["AoA"] else False),
    ]
    rows.append({"case_id": case_dir.name, "task_id": spec["task_id"], "mach": spec["mach"],
      "design": spec["design"], "split": spec["split"], "partition": spec["partition"],
      "n_alpha": len(deck["AoA"]), "deck_mach": deck.get("Mach"), "deck_vinf": deck.get("Vinf"),
      "deck_recref": deck.get("ReCref"), "deck_rho": deck.get("Rho"),
      "q_from_deck": 0.5*deck.get("Rho",0)*deck.get("Vinf",0)**2,
      "cl_required": cin["cl_required"], "plan_sha256": appr["plan_sha256"],
      "plan_file_sha256": __import__("hashlib").sha256((case_dir/"plan.json").read_bytes()).hexdigest()})
failed = [c for c in checks if not c[1]]
result = {"schema":"drecover001.r2_matrix_input_verification.v1",
 "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
 "case_count": len(rows), "check_count": len(checks), "failure_count": len(failed),
 "failures": [c[0] for c in failed], "physical_solver_starts": 0,
 "note": "zero-solver verification of generated decks; plan_file_sha256 is the file hash, approval plan_sha256 is the canonical plan hash stored in approval.json",
 "cases": rows}
out = ROOT / "matrix_input_verification.json"
out.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({k:result[k] for k in ("case_count","check_count","failure_count","failures")}, indent=2))
print(json.dumps(rows, indent=2)[:8000])
