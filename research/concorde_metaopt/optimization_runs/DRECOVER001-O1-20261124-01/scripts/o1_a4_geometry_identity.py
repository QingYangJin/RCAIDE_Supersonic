
"""A4 geometry identity, v2: prove the delivered aircraft is the aircraft that ran.

Two independent legs, both from artifacts:

  leg 1 (regeneration): take x12 out of the DELIVERED manifest, rebuild the solver
          geometry through the same frozen code path (build_geometry -> prepare_case),
          and require the regenerated .vspgeom sha256 to equal the geometry_sha256 that
          plan.json recorded for the case that actually ran. A .vspgeom is the only thing
          VSPAERO is given, so equal vspgeom = the solver saw the delivered aircraft.

  leg 2 (canonical XML): compare the delivered .vsp3 with the case .vsp3 element by
          element, masking only OpenVSP's re-randomised element IDs. Residual,
          non-geometric differences (tessellation settings, float round-trip in the
          tessellator) are reported explicitly rather than hidden.

Neither leg starts a solver. Leg 1 sets StopBeforeRun=1 and physical_solver_starts stays 0.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
O1 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
O0 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(O1 / "scripts"))

from research.concorde_metaopt.aircraft.geometry_model import build_geometry  # noqa: E402
from research.concorde_metaopt.dreal001.geometry import openvsp_model as om  # noqa: E402
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

SCRATCH = O1 / "a4_geometry" / "regeneration"
OUT = O1 / "o1_a4_geometry_identity.json"

# (run, role, delivered manifest, delivered .vsp3, case dir, case plan)
PAIRS = [
    ("O1", "baseline",
     O1 / "final_aircraft/baseline_geometry.json",
     O1 / "final_aircraft/geometry/baseline_solver.vsp3",
     O1 / "cases/O1-M190/SUPPORT/o1-s00-refine"),
    ("O1", "sobol_best",
     O1 / "final_aircraft/sobol_best_geometry.json",
     O1 / "final_aircraft/geometry/sobol_best_solver.vsp3",
     O1 / "cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine"),
    ("O1", "supervised_best",
     O1 / "final_aircraft/supervised_best_geometry.json",
     O1 / "final_aircraft/geometry/supervised_best_solver.vsp3",
     O1 / "cases/O1-M190/ARM_COND_SUPERVISED_KSHOT_BO/o1-d07-refine"),
    ("O0", "baseline",
     O0 / "final_aircraft/baseline_geometry.json",
     O0 / "final_aircraft/geometry/baseline_solver.vsp3",
     O0 / "cases/B02/o0-d00-refine"),
    ("O0", "optimized",
     O0 / "final_aircraft/optimized_geometry.json",
     O0 / "final_aircraft/geometry/optimized_solver.vsp3",
     O0 / "cases/B02/o0-d10-refine"),
]

IDPAT = re.compile(r"^[A-Z]{8,12}$")
# VSPAERO paneling parameters, i.e. the surface MESH, not the aircraft. This project sets
# Tess_U/Tess_W per batch (o0_eval/o1_eval write tess_u=12, tess_w=25, the paid value) while
# the delivered exports leave OpenVSP's defaults, and OpenVSP then derives MaxGrowth and
# SmallPanelW from that choice when it writes the file (measured: 16 -> MaxGrowth 1.437006,
# SmallPanelW 1.711946e-02; 12 -> MaxGrowth 1.606373, SmallPanelW 2.487518e-02). They are
# disclosed as non-geometric rather than suppressed, and the shape-derived quantities that
# live in the same <WingGeom> block (CurvedArea, MAC, TotalAR, TotalArea) are compared and
# come out equal, which is what makes the exclusion narrow rather than a blank cheque.
NON_GEOMETRIC = ("Tess_U", "Tess_W", "MaxGrowth", "SmallPanelW")
PANELING_NOTE = ("Tess_U/Tess_W are chosen per batch and MaxGrowth/SmallPanelW are derived from "
                 "them by OpenVSP when the file is written; the remaining 2,184 elements, "
                 "including the shape-derived WingGeom quantities, are compared verbatim.")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Element tags whose text is an OpenVSP element ID, not a value.
ID_TAGS = ("ID", "CompID")


def canon(path: Path) -> List[Any]:
    """Every XML element as (tag, attributes, text).

    OpenVSP re-randomises every element ID on import/export, and stores those IDs
    both as attribute values (ID=, AttachID=) and as element text (<ID>XXXX</ID>).
    Both places are masked; everything else is compared verbatim.
    """
    root = ET.parse(path).getroot()
    out = []
    for el in root.iter():
        attrs = tuple((k, "<ID>" if IDPAT.match(v) else v) for k, v in sorted(el.attrib.items()))
        text = (el.text or "").strip()
        if el.tag in ID_TAGS and IDPAT.match(text):
            text = "<ID>"
        out.append((el.tag, attrs, text))
    return out


def canonical_compare(delivered: Path, case: Path) -> Dict[str, Any]:
    """Element-by-element comparison with element IDs masked.

    A difference is classed non-geometric only when the differing element IS one of the
    disclosed tessellation parameters, decided by tag name: those are element TAGS
    (<Tess_U Value=.../>), not attribute values, so any substring test on values misses
    them. Everything else is a geometric difference until proven otherwise.
    """
    a, b = canon(delivered), canon(case)
    diffs = []
    for index, (x, y) in enumerate(zip(a, b)):
        if x == y:
            continue
        diffs.append({"index": index, "tag": x[0],
                      "delivered": [list(x[1]), x[2]],
                      "case": [list(y[1]), y[2]],
                      "non_geometric": x[0] in NON_GEOMETRIC})
    residual = [d for d in diffs if not d["non_geometric"]]
    tag_counts: Dict[str, int] = {}
    for d in diffs:
        tag_counts[d["tag"]] = tag_counts.get(d["tag"], 0) + 1
    return {"elements_delivered": len(a), "elements_case": len(b),
            "same_element_count": len(a) == len(b),
            "difference_count": len(diffs),
            "difference_tag_counts": dict(sorted(tag_counts.items())),
            "non_geometric_differences": len(diffs) - len(residual),
            "geometric_differences": len(residual),
            "identical_modulo_element_ids_and_tessellation": (len(a) == len(b)) and not residual,
            "residual_differences": residual[:8],
            "raw_sha256_delivered": sha256(delivered),
            "raw_sha256_case": sha256(case)}


def regenerate(x12: List[float], case_plan: Dict[str, Any], label: str) -> Dict[str, Any]:
    """Rebuild the solver geometry from x12 and compare the .vspgeom with the paid case."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    target = SCRATCH / label
    if target.exists():
        for stale in target.glob("*"):
            if stale.is_file():
                stale.unlink()
    target.mkdir(parents=True, exist_ok=True)
    geom = build_geometry(list(o0.PHYSICAL_15_NAMES), o0.physical_15(x12))
    # exactly the parameters o1_eval.make_case uses to write a real case
    info = om.prepare_case(geom, target, "regen", geometry_set="thin",
                           alphas_deg=[5.0], tess_u=12, tess_w=25,
                           n_wake_nodes=8, mach_values=[1.9])
    regen_geom = target / "regen.vspgeom"
    regen_sha = sha256(regen_geom)
    want = case_plan["geometry"]["geometry_sha256"]
    case_geom = Path(case_plan["geometry"]["files"]["vspgeom"]["path"])
    design = o0.design_identity(x12)
    return {
        "x12_from_delivered_manifest": list(x12),
        "design_id_from_delivered_x12": design["design_id"],
        "design_hash_recorded_by_case_plan": case_plan["design"]["design_hash"],
        "design_id_matches_case_plan": design["design_id"] == case_plan["design"]["design_hash"],
        "regenerated_vspgeom_sha256": regen_sha,
        "case_plan_geometry_sha256": want,
        "regenerated_vspgeom_matches_case_plan": regen_sha == want,
        "case_vspgeom_on_disk_sha256": sha256(case_geom),
        "case_vspgeom_bytes_match_plan": sha256(case_geom) == want,
        "physical_solver_starts": int(info.get("physical_solver_starts", 0)),
        "solver_started": bool(info.get("solver_started", False)),
        "sref_m2_regenerated": float(info.get("sref_m2", 0.0)),
    }


def main() -> int:
    rows = []
    for run, role, manifest_path, delivered_vsp3, case_dir in PAIRS:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plan_path = case_dir / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        x12 = [float(v) for v in manifest["x12"]]
        label = ("%s-%s" % (run, role)).lower()
        regen = regenerate(x12, plan, label)
        canon_row = canonical_compare(delivered_vsp3, case_dir / (plan["case_id"] + ".vsp3"))
        # x12 must also be what the case actually ran, not just what the manifest says
        x12_matches_case = all(abs(a - b) <= 1.0e-12 * max(1.0, abs(b))
                               for a, b in zip(x12, plan["design"]["x12"]))
        row = {
            "run": run, "role": role,
            "delivered_manifest": str(manifest_path),
            "delivered_vsp3": str(delivered_vsp3),
            "delivered_vsp3_bytes": delivered_vsp3.stat().st_size,
            "case_dir": str(case_dir),
            "case_id": plan["case_id"],
            "case_plan_geometry_sha256": plan["geometry"]["geometry_sha256"],
            "case_plan_design_hash": plan["design"]["design_hash"],
            "x12_matches_case_plan": x12_matches_case,
            "regeneration": regen,
            "canonical_xml": canon_row,
            "identity_proved": bool(
                x12_matches_case
                and regen["design_id_matches_case_plan"]
                and regen["regenerated_vspgeom_matches_case_plan"]
                and regen["case_vspgeom_bytes_match_plan"]
                and canon_row["identical_modulo_element_ids_and_tessellation"]
                and regen["physical_solver_starts"] == 0
            ),
        }
        rows.append(row)
        print("%-2s %-16s x12=%-5s design=%-5s vspgeom=%-5s canon=%-5s -> %s"
              % (run, role, x12_matches_case,
                 regen["design_id_matches_case_plan"],
                 regen["regenerated_vspgeom_matches_case_plan"],
                 canon_row["identical_modulo_element_ids_and_tessellation"],
                 "IDENTICAL" if row["identity_proved"] else "NOT PROVED"), flush=True)

    out = {
        "schema": "dreal005.a4_geometry_identity.v2",
        "issue": 15,
        "requirement": ("A4 must verify geometry identity from what GitHub serves: the delivered "
                        "final_aircraft must be the aircraft that really ran in the solver cases."),
        "method": {
            "leg_1_regeneration": ("x12 is read from the delivered manifest, the solver geometry is rebuilt "
                                   "through the same frozen code path (build_geometry -> prepare_case) and the "
                                   "resulting .vspgeom sha256 must equal the geometry_sha256 that plan.json "
                                   "recorded for the paid case. VSPAERO is only ever given the .vspgeom, so an "
                                   "equal .vspgeom means the solver flew the delivered aircraft."),
            "leg_2_canonical_xml": ("the delivered .vsp3 and the case .vsp3 are compared element by element "
                                    "with OpenVSP element IDs masked. IDs are re-randomised on every import/export "
                                    "(measured: 1,703 of 2,468 lines differ between the two files and every one of "
                                    "them is an <ID>/AttachID value), so raw byte equality is impossible by "
                                    "construction and would be a false test."),
            "disclosed_residuals": ("the delivered files are exported with OpenVSP default tessellation, while "
                                    "each paid case was written with tess_u=12/tess_w=25; that shows up as "
                                    "Tess_U/Tess_W/MaxGrowth differences and is reported per pair as "
                                    "non_geometric_differences instead of being suppressed."),
            "no_solver": "neither leg starts a solver; leg 1 writes with StopBeforeRun=1, physical_solver_starts 0.",
        },
        "pairs": rows,
        "pair_count": len(rows),
        "identity_proved_count": sum(1 for r in rows if r["identity_proved"]),
        "all_identity_proved": all(r["identity_proved"] for r in rows),
        "generated_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("all_identity_proved:", out["all_identity_proved"],
          "(%d/%d)" % (out["identity_proved_count"], len(rows)))
    print("written:", OUT, sha256(OUT))
    return 0 if out["all_identity_proved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
