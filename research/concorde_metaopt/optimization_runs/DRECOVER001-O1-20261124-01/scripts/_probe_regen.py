
"""Probe: can the delivered design regenerate the exact .vspgeom that ran?"""
import hashlib, json, sys
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(RUN / "scripts"))

from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.dreal001.geometry import openvsp_model as om
from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0

CASE = RUN / "cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine"
plan = json.loads((CASE / "plan.json").read_text(encoding="utf-8"))
x12 = plan["design"]["x12"]
want = plan["geometry"]["geometry_sha256"]
for label, cid in (("sobol-d06", plan["design"]["design_hash"]),):
    print("design:", label, cid)
print("want vspgeom sha:", want)
print("solver components:", TASK_SPEC.solver_geometry_components)
print("default geometry set:", TASK_SPEC.default_geometry_set)

scratch = RUN / "a4_geometry" / "probe-regen"
scratch.mkdir(parents=True, exist_ok=True)
geom = build_geometry(list(o0.PHYSICAL_15_NAMES), o0.physical_15(x12))
info = om.prepare_case(geom, scratch, "regen", geometry_set="thin",
                       alphas_deg=[5.0, 5.05, 5.1], tess_u=12, tess_w=25,
                       n_wake_nodes=8, mach_values=[1.9])
got = hashlib.sha256((scratch / "regen.vspgeom").read_bytes()).hexdigest()
print("got  vspgeom sha:", got)
print("MATCH:", got == want)
print("mesh history:", json.dumps(info.get("mesh_attempt_history"), indent=1)[:900])
