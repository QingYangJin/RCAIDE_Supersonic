import json, hashlib, re, shutil
from pathlib import Path
import sys

ROOT = Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
sys.path.insert(0, str(ROOT))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.dreal001.geometry.openvsp_model import prepare_case

names = ["wing_area","aspect_ratio","sweep_1","sweep_2","sweep_3","span_location_2","span_location_3","chord_ratio_2","chord_ratio_3","tip_twist","vertical_tail_area","vertical_tail_sweep_delta","fuselage_length","fuselage_fineness","fuselage_height_width_ratio"]
values = [358.25,1.83,67.0,48.0,71.0,0.480469,0.945313,0.408284,0.130178,0.0,33.91,0.0,61.66,4.30,1.152778]
geometry = build_geometry(names, values)
base = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/flow_default_equivalence")
if base.exists(): shutil.rmtree(base)
out = {}
for label, flow in (("default", None), ("explicit", {"vinf_m_s":596.0373972278921,"rho_kg_m3":0.1153178340089936,"recref":89397005.8767656})):
    d = base / label
    d.mkdir(parents=True)
    rec = prepare_case(geometry, d, basename="equiv", alphas_deg=(0.0,), geometry_set="thin", tess_u=12, tess_w=25, write_vsp3=True, mach_values=[2.02], flow_conditions=flow)
    deck = (d/"equiv.vspaero").read_text(encoding="utf-8")
    keys = {}
    for key in ("Sref","Mach","AoA","ReCref","Vinf","Rho"):
        m = re.search(rf"^{key}\s*=\s*(.+)$", deck, re.M)
        keys[key] = m.group(1).strip() if m else None
    cin = json.loads((d/"case_inputs.json").read_text(encoding="utf-8"))
    out[label] = {"vspgeom_sha256": hashlib.sha256((d/"equiv.vspgeom").read_bytes()).hexdigest(),
                  "deck_keys": keys, "q_pa": cin["q_pa"], "cl_required": cin["cl_required"],
                  "flow_conditions": cin.get("flow_conditions"),
                  "reference_injection": cin.get("reference_injection"),
                  "reference_injection_note": cin.get("reference_injection_note")}
same_deck = out["default"]["deck_keys"] == out["explicit"]["deck_keys"]
same_mesh = out["default"]["vspgeom_sha256"] == out["explicit"]["vspgeom_sha256"]
result = {"schema":"drecover001.flow_default_equivalence.v1",
          "same_vspgeom_sha256": same_mesh, "same_deck_key_lines": same_deck,
          "default": out["default"], "explicit": out["explicit"],
          "verdict":"DEFAULT_PATH_EQUIVALENT" if (same_deck and same_mesh) else "DEFAULT_PATH_DIFFERS",
          "physical_solver_starts": 0}
(base/"verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2)[:8000])
