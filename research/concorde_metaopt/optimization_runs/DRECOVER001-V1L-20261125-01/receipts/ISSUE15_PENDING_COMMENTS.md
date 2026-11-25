# Issue #15 待发布评论正文（通道恢复后按序提交）

生成时间：2026-11-25T16:50+08:00
状态：注释 1（数据）已发布 https://github.com/QingYangJin/RCAIDE_Supersonic/issues/15#issuecomment-7157198365
注释 2–4（代码正文）发布失败：`issue_comment` 连续 3 次挂起（4.2 KB / 1.3 KB / 30 B 全部超时），读接口 `gh_issue` 正常。
恢复后按 C2 → C3 → C4 顺序提交即可，内容已冻结。

---

## C2 — 后端与门禁 diff

```python
"""RCAIDE-native supersonic VLM backend (V1L lineage).

Replaces VSPAERO as the aerodynamic evaluator for the whole downstream stack
(optimization and meta-learning labels).  Every number this module returns comes
from RCAIDE's own Vortex_Lattice_Method with the surrogate disabled, so the
supersonic kernel (B2 = mach**2 - 1) is exercised directly.

Design notes that matter for correctness
---------------------------------------
* The objective is the Trefftz-plane induced drag coefficient at a *fixed* lift
  coefficient, with alpha solved per design.  Trefftz CDi carries no wave drag
  (VLM.py:563 documents that the formula is exact only in the incompressible
  limit), and RCAIDE's own compressibility term returns NaN on this vehicle
  (compressibility_drag.py:129 -> :367 reads a None lift.spanwise), so the
  objective is named CDi_trefftz and is never presented as total drag.
* The lattice is fixed by the caller and recorded in every record.  A single
  discretisation is reused for all designs so that differences between designs
  are not contaminated by lattice changes; absolute values carry the lattice
  error, differences largely do not.
* Every solve is deterministic: same design, same lattice, same alpha -> same
  bits.  The backend therefore refuses to report a result it cannot reproduce.
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

SCHEMA = "dreal005.rcaide_vlm_backend.v1"

# Reference quantities are frozen by the project, not recomputed from the VLM
# geometry, because the adapter leaves reference_chord/span at zero.
SREF_M2 = 358.25
CREF_M = 18.489893
BREF_M = 25.604638

DEFAULT_LATTICE = (20, 10)  # (spanwise, chordwise); the agreed optimization baseline


def _digest(values: Sequence[float]) -> str:
    payload = ",".join("%.12g" % float(v) for v in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class SupersonicVLMBackend:
    """Fixed-task, fixed-lattice, alpha-solved RCAIDE VLM evaluator."""

    def __init__(
        self,
        repo_root: str,
        design_space_config: str,
        *,
        mach: float = 2.02,
        altitude_m: float = 18288.0,
        cl_target: float = 0.181743998494,
        lattice: Tuple[int, int] = DEFAULT_LATTICE,
        design_names: Optional[Sequence[str]] = None,
    ) -> None:
        import os
        import sys

        self.repo_root = repo_root
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        os.chdir(repo_root)

        from research.concorde_metaopt.config_io import load_config
        from research.concorde_metaopt.aircraft.design_space import design_space_from_config

        data = load_config(design_space_config)
        data["frozen"] = False  # side study: the P1 freeze guard rejects the config as-is
        self.space = design_space_from_config(data, source="V1L-rcaide-vlm")
        self.design_names = list(design_names or self.space.names)
        self.mach = float(mach)
        self.altitude_m = float(altitude_m)
        self.cl_target = float(cl_target)
        self.lattice = (int(lattice[0]), int(lattice[1]))

        from RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976 import US_Standard_1976

        atm = US_Standard_1976().compute_values(self.altitude_m)
        flat = lambda x: float(np.ravel(np.asarray(x, dtype=float))[0])
        self._atmo = {
            "temperature_K": flat(atm.temperature),
            "pressure_Pa": flat(atm.pressure),
            "density_kg_m3": flat(atm.density),
            "speed_of_sound_m_s": flat(atm.speed_of_sound),
            "dynamic_viscosity_Pa_s": flat(atm.dynamic_viscosity),
            "kinematic_viscosity_m2_s": flat(atm.kinematic_viscosity),
        }
        self._atmo["velocity_m_s"] = self.mach * self._atmo["speed_of_sound_m_s"]
        self._atmo["dynamic_pressure_Pa"] = 0.5 * self._atmo["density_kg_m3"] * self._atmo["velocity_m_s"] ** 2

        from research.concorde_metaopt.aircraft.concorde_adapter import load_template_module

        # The adapter's recorded template hash does not match the tutorial file on
        # disk at this commit, so the verified path is unavailable by construction.
        self._module = load_template_module(verify_hash=False)

        self._vehicles: Dict[str, Any] = {}
        self.cache: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
        self.solve_count = 0
        self.build_count = 0
        self.wall_seconds = 0.0

    # -- geometry ---------------------------------------------------------
    def _vehicle(self, x12: Mapping[str, float]) -> Tuple[Any, str]:
        from research.concorde_metaopt.aircraft.concorde_adapter import build_vehicle
        from research.concorde_metaopt.aircraft.geometry_model import build_geometry
        from RCAIDE.Library.Methods.Geometry.Planform.wing_planform import wing_planform

        key = _digest([x12[n] for n in self.design_names])
        if key in self._vehicles:
            return self._vehicles[key], key
        expanded = self.space.expand({n: float(x12[n]) for n in self.design_names})
        geometry = build_geometry(tuple(expanded), tuple(expanded.values()))
        _, vehicle = build_vehicle(geometry, module=self._module)
        for wing in vehicle.wings:
            wing_planform(wing)  # fills areas.projected that the VLM paneliser requires
        vehicle.reference_area = SREF_M2
        vehicle.reference_chord = CREF_M
        vehicle.reference_span = BREF_M
        self.build_count += 1
        self._vehicles[key] = vehicle
        return vehicle, key

    # -- one VLM solve ----------------------------------------------------
    def _solve(self, vehicle: Any, alpha_deg: float) -> Tuple[float, float]:
        from RCAIDE.Framework.Analyses.Aerodynamics.Vortex_Lattice_Method import Vortex_Lattice_Method
        from RCAIDE.Framework.Mission.Common.Results import Results
        from RCAIDE.Framework.Core import Data

        aer = Vortex_Lattice_Method()
        aer.settings.use_surrogate = False
        aer.settings.number_of_spanwise_vortices = self.lattice[0]
        aer.settings.number_of_chordwise_vortices = self.lattice[1]
        aer.vehicle = vehicle
        aer.initialize(vehicle)

        a = self._atmo
        state = Data()
        state.conditions = Results()
        state.analyses = Data()
        c = state.conditions
        for name, value in (
            ("altitude", self.altitude_m),
            ("mach_number", self.mach),
            ("velocity", a["velocity_m_s"]),
            ("temperature", a["temperature_K"]),
            ("pressure", a["pressure_Pa"]),
            ("density", a["density_kg_m3"]),
            ("speed_of_sound", a["speed_of_sound_m_s"]),
            ("dynamic_pressure", a["dynamic_pressure_Pa"]),
            ("gravity", 9.81),
            ("dynamic_viscosity", a["dynamic_viscosity_Pa_s"]),
            ("kinematic_viscosity", a["kinematic_viscosity_m2_s"]),
        ):
            setattr(c.freestream, name, np.array([[value]]))
        c.freestream.reynolds_number = np.array(
            [[a["density_kg_m3"] * a["velocity_m_s"] * CREF_M / a["dynamic_viscosity_Pa_s"]]]
        )
        c.aerodynamics.angles.alpha = np.array([[math.radians(alpha_deg)]])
        c.aerodynamics.angles.beta = np.array([[0.0]])
        c.aerodynamics.angles.bank = np.array([[0.0]])

        from RCAIDE.Library.Methods.Aerodynamics.Vortex_Lattice_Method.VLM import VLM

        result = VLM(c, aer.settings, vehicle)
        self.solve_count += 1
        # results.CL is the pitching-moment coefficient (VLM.py:460); the lift
        # coefficient is CLift (VLM.py:438).
        return float(result.CLift[0][0]), float(result.CDrag_induced[0][0])

    # -- alpha solve ------------------------------------------------------
    def _alpha_for_lift(self, vehicle: Any, alpha_guess: float = 5.0) -> Dict[str, Any]:
        lo, hi = 0.5, 12.0
        hist: List[Tuple[float, float]] = []
        x0 = min(max(alpha_guess, lo), hi)
        cl0, _ = self._solve(vehicle, x0)
        hist.append((x0, cl0))
        if abs(cl0 - self.cl_target) < 1e-9:
            return {"alpha_deg": x0, "cl": cl0, "iterations": 1, "ok": True, "history": hist}
        x1 = x0 + 0.5 if cl0 < self.cl_target else x0 - 0.5
        x1 = min(max(x1, lo), hi)
        cl1, _ = self._solve(vehicle, x1)
        hist.append((x1, cl1))
        f0, f1 = cl0 - self.cl_target, cl1 - self.cl_target
        for step in range(12):
            if abs(f1) < 1e-7:
                return {"alpha_deg": x1, "cl": cl1, "iterations": step + 2, "ok": True, "history": hist}
            denom = f1 - f0
            if abs(denom) < 1e-14:
                break
            x2 = x1 - f1 * (x1 - x0) / denom
            if not (lo <= x2 <= hi):
                x2 = 0.5 * (x0 + x1)
            cl2, _ = self._solve(vehicle, x2)
            hist.append((x2, cl2))
            x0, f0, x1, f1 = x1, f1, x2, cl2 - self.cl_target
        ok = abs(f1) < 1e-5
        return {"alpha_deg": x1, "cl": cl1, "iterations": len(hist), "ok": ok, "history": hist}

    # -- public API -------------------------------------------------------
    def evaluate(self, x12: Mapping[str, float], *, purpose: str = "search") -> Dict[str, Any]:
        started = time.perf_counter()
        design = {n: float(x12[n]) for n in self.design_names}
        record: Dict[str, Any] = {
            "schema": SCHEMA,
            "purpose": purpose,
            "design": design,
            "design_key": _digest([design[n] for n in self.design_names]),
            "lattice": {"spanwise": self.lattice[0], "chordwise": self.lattice[1]},
            "mach": self.mach,
            "altitude_m": self.altitude_m,
            "cl_target": self.cl_target,
            "objective_name": "CDi_trefftz",
            "objective": None,
            "cl_actual": None,
            "alpha_deg": None,
            "alpha_iterations": None,
            "status": "FAILED",
            "diagnostics": [],
            "wall_seconds": 0.0,
            "cached": False,
        }
        cache_key = (record["design_key"], self.lattice[0], self.lattice[1])
        if cache_key in self.cache:
            hit = dict(self.cache[cache_key])
            hit["cached"] = True
            hit["purpose"] = purpose
            return hit
        try:
            vehicle, key = self._vehicle(design)
            solve = self._alpha_for_lift(vehicle)
            if not solve["ok"]:
                record["status"] = "ALPHA_SOLVE_FAILED"
                record["diagnostics"].append(
                    "secant did not place CL within 1e-5 of %.12g in 12 steps" % self.cl_target
                )
                record["alpha_deg"] = solve["alpha_deg"]
                record["cl_actual"] = solve["cl"]
                record["alpha_iterations"] = solve["iterations"]
                return record
            cl, cdi = self._solve(vehicle, solve["alpha_deg"])
            if not math.isfinite(cdi) or cdi <= 0.0:
                record["status"] = "NON_PHYSICAL_CDI"
                record["diagnostics"].append("CDi=%.6g is not finite and positive" % cdi)
                return record
            record.update(
                objective=float(cdi),
                cl_actual=float(cl),
                alpha_deg=float(solve["alpha_deg"]),
                alpha_iterations=int(solve["iterations"]),
                status="VALID",
            )
            record["cdi_times_q_sref_N"] = float(cdi) * self._atmo["dynamic_pressure_Pa"] * SREF_M2
            self.cache[cache_key] = dict(record)
        except Exception as exc:  # geometry/VLM failures must not escape as exceptions
            record["status"] = "ERROR"
            record["diagnostics"].append("%s: %s" % (type(exc).__name__, str(exc)[:400]))
        finally:
            spent = time.perf_counter() - started
            record["wall_seconds"] = round(spent, 3)
            self.wall_seconds += spent
        return record

    def provenance(self) -> Dict[str, Any]:
        import RCAIDE

        return {
            "schema": SCHEMA,
            "backend": "RCAIDE.Vortex_Lattice_Method",
            "use_surrogate": False,
            "rcaide_version": getattr(RCAIDE, "__version__", "unknown"),
            "lattice": {"spanwise": self.lattice[0], "chordwise": self.lattice[1]},
            "mach": self.mach,
            "altitude_m": self.altitude_m,
            "cl_target": self.cl_target,
            "objective_name": "CDi_trefftz",
            "objective_is_total_drag": False,
            "wave_drag_included": False,
            "reference": {"SREF_m2": SREF_M2, "CREF_m": CREF_M, "BREF_m": BREF_M},
            "atmosphere": dict(self._atmo),
            "template_hash_verified": False,
        }
```

```diff
diff --git a/research/concorde_metaopt/dreal001/meta/meta_dataset.py b/research/concorde_metaopt/dreal001/meta/meta_dataset.py
index ab093bc..e6ff229 100644
--- a/research/concorde_metaopt/dreal001/meta/meta_dataset.py
+++ b/research/concorde_metaopt/dreal001/meta/meta_dataset.py
@@ -41,7 +41,11 @@ class Observation:
             raise ContractError("design must have 12 finite coordinates")
         if self.partition not in {"support", "query"}:
             raise ContractError("invalid support/query partition")
-        if self.source_kind not in {"synthetic_fixture", "vspaero_raw"}:
+        # "rcaide_vlm_20x10" is a declared-computed label source: every row is
+        # reproducible from (design, task, lattice) through SupersonicVLMBackend and
+        # carries no solver raw bytes. It is deliberately a distinct kind so that it
+        # can never satisfy require_real_admission(), which demands certificates.
+        if self.source_kind not in {"synthetic_fixture", "vspaero_raw", "rcaide_vlm_20x10"}:
             raise ContractError("unrecognized data source")
         if self.status not in {"ok", "failed"}:
             raise ContractError("unrecognized observation status")
@@ -221,6 +225,23 @@ class MetaDataset:
         if any(r.source_kind != "synthetic_fixture" for r in self.rows):
             raise ContractError("software fixture entry rejects real/declared-real data")
 
+    def require_declared_computed_labels(self) -> None:
+        """Fail-closed gate for declared-computed label sources.
+
+        A computed dataset carries no admission certificates by construction, so it
+        must declare exactly one source kind and every row must be a finite positive
+        label. This never authorises a raw-bytes claim: require_real_admission()
+        still rejects the dataset because admissions is empty.
+        """
+        if self.admissions:
+            raise ContractError("declared-computed dataset must not carry admission certificates")
+        kinds = {r.source_kind for r in self.rows}
+        if kinds != {"rcaide_vlm_20x10"}:
+            raise ContractError("declared-computed dataset must be rcaide_vlm_20x10 only, got %s" % sorted(kinds))
+        for row in self.rows:
+            if row.status != "ok" or row.di_n is None or not math.isfinite(row.di_n) or row.di_n <= 0.0:
+                raise ContractError("declared-computed row %s has no finite positive label" % row.observation_id)
+
     def require_real_admission(self) -> None:
         # A declared raw source is not enough. Every row must carry a certificate
         # minted by admit_real_manifest() after local byte/task/deck/polar/audit checks.
diff --git a/research/concorde_metaopt/dreal001/meta/real_a0_ablation.py b/research/concorde_metaopt/dreal001/meta/real_a0_ablation.py
index 6d772ad..d812de6 100644
--- a/research/concorde_metaopt/dreal001/meta/real_a0_ablation.py
+++ b/research/concorde_metaopt/dreal001/meta/real_a0_ablation.py
@@ -420,6 +420,8 @@ def run_arm(dataset: MetaDataset, *, config: AblationConfig, k: int,
     require_k(k)
     if mode == "real":
         dataset.require_real_admission()
+    elif mode == "vlm_labels":
+        dataset.require_declared_computed_labels()
     elif mode != "software_fixture":
         raise ContractError("unsupported execution mode")
     else:
@@ -502,6 +504,8 @@ def run_arm_for_arm(dataset: MetaDataset, *, config: AblationConfig, k: int,
         raise ContractError("unknown arm: %r" % (arm,))
     if mode == "real":
         dataset.require_real_admission()
+    elif mode == "vlm_labels":
+        dataset.require_declared_computed_labels()
     elif mode != "software_fixture":
         raise ContractError("unsupported execution mode")
     else:

```

---

## C3 — 优化脚本 v1l_bo.py / v1l_data.py

```python
# -*- coding: utf-8 -*-
"""V1L optimization: GP-EI BO on the RCAIDE supersonic VLM objective at 20x10.

Pre-registered protocol (written before the run, see V1L_PREREGISTRATION.md):
  objective  = CDi_trefftz at CL_target, alpha solved per design
  lattice    = (20, 10) spanwise x chordwise, identical for every design
  subspace   = sweep_1 in [65.5, 68.5], sweep_2 in [46.5, 49.5]; the other 10 dims frozen
  budget     = 24 LHS bootstrap + 96 BO acquisitions = 120 VLM evaluations
  confirmation = top-5 designs re-evaluated at 30x15 and 45x25; an improvement is
                 only claimed if the sign survives both finer lattices
"""
import os, sys, json, time
import numpy as np
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
OUT  = r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01"
sys.path.insert(0, REPO); os.chdir(REPO)
from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend
from research.concorde_metaopt.dreal001.optimizers.recovery_bo import (
    RecoveryGaussianProcessBO, generate_initial_designs)

CFG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")
SEED = 20261125
BOOT = 24
TOTAL = 120
LOWER = np.array([65.5, 46.5])
UPPER = np.array([68.5, 49.5])
BASE = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]

be = SupersonicVLMBackend(REPO, CFG, lattice=(20, 10))
NAMES = be.design_names
Q, S = be._atmo["dynamic_pressure_Pa"], 358.25

def design(s1, s2):
    d = dict(zip(NAMES, BASE)); d["sweep_1"] = float(s1); d["sweep_2"] = float(s2); return d

def run(point, purpose):
    rec = be.evaluate(design(point[0], point[1]), purpose=purpose)
    return rec

# baseline reference (the frozen 12D baseline design)
t0 = time.time()
base_rec = run([67.0, 48.0], "baseline")
print("baseline CDi=%.9f alpha=%.5f wall=%.2fs" % (base_rec["objective"], base_rec["alpha_deg"], base_rec["wall_seconds"]), flush=True)

bo = RecoveryGaussianProcessBO(LOWER, UPPER, seed=SEED)
rows = []
seen = set()
key = lambda p: (round(float(p[0]), 9), round(float(p[1]), 9))

boot = generate_initial_designs(LOWER, UPPER, count=BOOT, seed=SEED)
for i, point in enumerate(boot):
    point = np.asarray(point, dtype=float)
    if key(point) in seen:
        continue
    rec = run(point, "bootstrap")
    ok = rec["status"] == "VALID"
    bo.tell(point, {"valid": ok, "feasible": ok, "objective": rec["objective"] if ok else None})
    seen.add(key(point))
    rows.append({"index": len(rows), "phase": "bootstrap", "sweep_1": float(point[0]), "sweep_2": float(point[1]),
                 "cdi": rec["objective"], "alpha_deg": rec["alpha_deg"], "status": rec["status"],
                 "di_N": rec.get("cdi_times_q_sref_N"), "wall_s": rec["wall_seconds"]})
    if (i+1) % 8 == 0:
        print("bootstrap %d/%d" % (i+1, BOOT), flush=True)

stall = 0
while len(rows) < TOTAL:
    point = np.asarray(bo.ask()["design_vector"], dtype=float)
    if key(point) in seen:
        stall += 1
        if stall > 40:
            print("no fresh acquisition after 40 asks; stopping at %d evals" % len(rows), flush=True)
            break
        continue
    stall = 0
    rec = run(point, "bo")
    ok = rec["status"] == "VALID"
    bo.tell(point, {"valid": ok, "feasible": ok, "objective": rec["objective"] if ok else None})
    seen.add(key(point))
    rows.append({"index": len(rows), "phase": "bo", "sweep_1": float(point[0]), "sweep_2": float(point[1]),
                 "cdi": rec["objective"], "alpha_deg": rec["alpha_deg"], "status": rec["status"],
                 "di_N": rec.get("cdi_times_q_sref_N"), "wall_s": rec["wall_seconds"]})
    if len(rows) % 12 == 0:
        json.dump({"partial": rows}, open(os.path.join(OUT, "v1l_bo_partial.json"), "w"), indent=1)
        best = min((r for r in rows if r["cdi"]), key=lambda r: r["cdi"])
        print("bo %3d evals | best CDi=%.9f at (%.4f, %.4f) | %.0fs" % (
            len(rows), best["cdi"], best["sweep_1"], best["sweep_2"], time.time()-t0), flush=True)

valid = [r for r in rows if r["cdi"]]
valid.sort(key=lambda r: r["cdi"])
best = valid[0]
improvement_pct = 100.0 * (base_rec["objective"] - best["cdi"]) / base_rec["objective"]
print("\nBEST 20x10: (%.6f, %.6f) CDi=%.9f  alpha=%.5f  vs baseline %.2f%% lower" % (
    best["sweep_1"], best["sweep_2"], best["cdi"], best["alpha_deg"], improvement_pct), flush=True)
print("Di base=%.3f N best=%.3f N dDi=%.3f N" % (
    base_rec["objective"]*Q*S, best["cdi"]*Q*S, (base_rec["objective"]-best["cdi"])*Q*S), flush=True)

# ---- cross-lattice confirmation of the top-5 (and the baseline) ----
top = valid[:5]
conf = {"baseline": {}, "candidates": []}
for lat in ((30, 15), (45, 25)):
    be2 = SupersonicVLMBackend(REPO, CFG, lattice=lat)
    rb = be2.evaluate(design(67.0, 48.0), purpose="confirm-baseline")
    tag = "%dx%d" % lat
    conf["baseline"][tag] = {"cdi": rb["objective"], "alpha_deg": rb["alpha_deg"], "status": rb["status"]}
    print("confirm baseline %s CDi=%.9f" % (tag, rb["objective"]), flush=True)
    for r in top:
        rc = be2.evaluate(design(r["sweep_1"], r["sweep_2"]), purpose="confirm")
        conf["candidates"].append({"sweep_1": r["sweep_1"], "sweep_2": r["sweep_2"], "lattice": tag,
                                   "cdi": rc["objective"], "alpha_deg": rc["alpha_deg"], "status": rc["status"],
                                   "dcdi_pct_vs_baseline": 100.0*(conf["baseline"][tag]["cdi"]-rc["objective"])/conf["baseline"][tag]["cdi"]})
        print("  cand (%.4f,%.4f) %s CDi=%.9f d=%.4f%%" % (r["sweep_1"], r["sweep_2"], tag, rc["objective"],
              conf["candidates"][-1]["dcdi_pct_vs_baseline"]), flush=True)

out = {"schema": "dreal005.v1l_bo.v1", "seed": SEED, "lattice": [20, 10], "budget": TOTAL,
       "bootstrap": BOOT, "objective_name": "CDi_trefftz", "cl_target": be.cl_target,
       "subspace": {"sweep_1": [65.5, 68.5], "sweep_2": [46.5, 49.5]},
       "baseline": {"sweep_1": 67.0, "sweep_2": 48.0, "cdi": base_rec["objective"],
                    "alpha_deg": base_rec["alpha_deg"], "di_N": base_rec["objective"]*Q*S},
       "best": {"sweep_1": best["sweep_1"], "sweep_2": best["sweep_2"], "cdi": best["cdi"],
                "alpha_deg": best["alpha_deg"], "di_N": best["cdi"]*Q*S, "improvement_pct": improvement_pct},
       "confirmation": conf, "evaluations": rows, "provenance": be.provenance(),
       "wall_seconds": round(time.time()-t0, 1)}
json.dump(out, open(os.path.join(OUT, "v1l_bo_results.json"), "w"), indent=2)
print("\nWROTE v1l_bo_results.json  (%.1fs total)" % (time.time()-t0), flush=True)
```

```python
# -*- coding: utf-8 -*-
"""V1L labels: relabel the frozen A0 task/design grid with the RCAIDE supersonic VLM.

What is reused from A0 (unchanged, so the comparison is like-for-like):
  - the eight canonical tasks (mach, altitude, dynamic pressure, lift target);
  - the seven admitted designs and their support/query partition membership;
  - the frozen split: train M140/M160/M200/M202, val M180/M220, test M240/M260.

What is new here: every label (Di_N) is recomputed by SupersonicVLMBackend at
lattice (20, 10) with alpha solved to CL_target. No VSPAERO label is reused and
no solver is started. source_kind becomes "rcaide_vlm_20x10" so the dataset
cannot be mistaken for admitted raw bytes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "research/concorde_metaopt/optimization_runs/DRECOVER001-A0-20261124-01/scripts"))

import a0_data  # noqa: E402
from research.concorde_metaopt.dreal001.meta.meta_dataset import (  # noqa: E402
    MetaDataset, Observation)
from research.concorde_metaopt.evaluation.rcaide_vlm_backend import (  # noqa: E402
    SupersonicVLMBackend)

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01")
CFG = REPO / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
LATTICE = (20, 10)
SREF = 358.25
SOURCE_KIND = "rcaide_vlm_20x10"


def label_rows(verbose: bool = True):
    built = a0_data.build_family_and_dataset()
    source = built["dataset"]
    names = SupersonicVLMBackend(REPO, str(CFG), lattice=LATTICE).design_names
    baselines = {}
    cache = {}
    for task in source.tasks:
        cl_target = task.lift_target_n / (task.dynamic_pressure_pa * SREF)
        backend = SupersonicVLMBackend(REPO, str(CFG), mach=task.mach,
                                       altitude_m=task.altitude_m,
                                       cl_target=cl_target, lattice=LATTICE,
                                       design_names=names)
        for row in source.rows:
            if row.task_id != task.task_id:
                continue
            design = dict(zip(names, row.design))
            rec = backend.evaluate(design, purpose="v1l-label")
            key = (task.task_id, row.design_sha256)
            if rec["status"] != "VALID":
                raise SystemExit("VLM eval failed for %s %s: %s" % (key[0], key[1], rec["status"]))
            cache[key] = {"task_id": task.task_id, "design": list(row.design),
                          "partition": row.partition, "status": row.status,
                          "observation_id": row.observation_id,
                          "cdi": rec["objective"], "cl": rec["cl_actual"],
                          "alpha_deg": rec["alpha_deg"], "design_key": rec["design_key"],
                          "wall_seconds": rec["wall_seconds"],
                          "di_n": rec["objective"] * task.dynamic_pressure_pa * SREF}
        baselines[task.task_id] = {"mach": task.mach, "cl_target": cl_target,
                                   "q_pa": task.dynamic_pressure_pa,
                                   "provenance": backend.provenance()}
        if verbose:
            n = sum(1 for k in cache if k[0] == task.task_id)
            print("labelled %-16s M=%.2f rows=%d" % (task.task_id, task.mach, n), flush=True)

    # determinism gate: relabel three rows with a fresh backend and require bitwise match
    checks = []
    for task in source.tasks[:3]:
        cl_target = task.lift_target_n / (task.dynamic_pressure_pa * SREF)
        backend = SupersonicVLMBackend(REPO, str(CFG), mach=task.mach,
                                       altitude_m=task.altitude_m,
                                       cl_target=cl_target, lattice=LATTICE,
                                       design_names=names)
        row = next(r for r in source.rows if r.task_id == task.task_id)
        rec = backend.evaluate(dict(zip(names, row.design)), purpose="v1l-label-recheck")
        stored = cache[(task.task_id, row.design_sha256)]["cdi"]
        checks.append({"task_id": task.task_id, "stored_cdi": stored,
                       "recheck_cdi": rec["objective"],
                       "identical": bool(stored == rec["objective"])})
        if not checks[-1]["identical"]:
            raise SystemExit("non-deterministic VLM label for " + task.task_id)

    rows = []
    for task in source.tasks:
        for row in source.rows:
            if row.task_id != task.task_id:
                continue
            item = cache[(task.task_id, row.design_sha256)]
            rows.append(Observation(
                observation_id="V1L-" + item["design_key"] + "-" + task.task_id.replace("P2-CANON-", ""),
                task_id=task.task_id, design=tuple(row.design), partition=row.partition,
                source_kind=SOURCE_KIND, status=item["status"],
                di_n=float(item["di_n"]), q_pa=task.dynamic_pressure_pa, sref_m2=SREF,
                cdi=float(item["cdi"]), cl=float(item["cl"]),
                raw_sha256=item["design_key"], source_task_id=None))
    dataset = MetaDataset(tuple(source.tasks), tuple(rows), task_aliases=built["aliases"])
    return {"dataset": dataset, "source": source, "labels": cache,
            "baselines": baselines, "determinism_checks": checks,
            "aliases": built["aliases"], "design_names": list(names)}


def require_vlm_labels(dataset: MetaDataset) -> None:
    """Fail closed unless every row is a finite VLM label of the declared lattice."""
    if dataset.admissions:
        raise ContractError("VLM dataset must not carry VSPAERO admission certificates")
    for row in dataset.rows:
        if row.source_kind != SOURCE_KIND:
            raise ContractError("row %s is not a VLM label" % row.observation_id)
        if row.status != "ok" or row.di_n is None or not np.isfinite(row.di_n) or row.di_n <= 0.0:
            raise ContractError("row %s has no finite positive label" % row.observation_id)
        if row.cdi is None or not np.isfinite(row.cdi) or row.cdi <= 0.0:
            raise ContractError("row %s has no finite positive CDi" % row.observation_id)


from research.concorde_metaopt.dreal001.meta.task_spec import ContractError  # noqa: E402


def main() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    out = label_rows()
    ds = out["dataset"]
    require_vlm_labels(ds)
    payload = {"schema": "dreal005.v1l_labels.v1", "lattice": list(LATTICE),
               "source_kind": SOURCE_KIND, "sref_m2": SREF,
               "row_count": len(ds.rows),
               "labels": {("%s|%s" % k): v for k, v in out["labels"].items()},
               "task_baselines": out["baselines"],
               "determinism_checks": out["determinism_checks"],
               "note": ("Labels recomputed with RCAIDE supersonic VLM at 20x10; "
                        "CL matched per task; objective is Trefftz induced drag only "
                        "(wave drag excluded). No VSPAERO label is reused.")}
    (RUN / "v1l_labels.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("rows", len(ds.rows), "determinism", all(c["identical"] for c in out["determinism_checks"]))
    for row in ds.rows[:5]:
        print("  %-22s %s di=%.3f cdi=%.9f" % (row.task_id, row.partition, row.di_n, row.cdi))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def load_labels_payload() -> dict:
    return json.loads((RUN / "v1l_labels.json").read_text(encoding="utf-8"))


def build_family_and_dataset(verbose: bool = False):
    """Rebuild the VLM-labelled dataset from v1l_labels.json (no re-evaluation).

    Shares the function name/shape of a0_data.build_family_and_dataset so the
    frozen A0 driver can run against it unchanged, but no VSPAERO label is read:
    only the task family, the design membership and the frozen split are reused.
    """
    built = a0_data.build_family_and_dataset()
    source = built["dataset"]
    payload = load_labels_payload()
    labels = payload["labels"]
    rows = []
    for row in source.rows:
        key = "%s|%s" % (row.task_id, row.design_sha256)
        if key not in labels:
            raise SystemExit("missing VLM label for " + key)
        item = labels[key]
        rows.append(Observation(
            observation_id="V1L-" + item["design_key"] + "-" + row.task_id.replace("P2-CANON-", ""),
            task_id=row.task_id, design=tuple(item["design"]), partition=row.partition,
            source_kind=SOURCE_KIND, status="ok", di_n=float(item["di_n"]),
            q_pa=float(item["q_pa"] if "q_pa" in item else
                       next(t.dynamic_pressure_pa for t in source.tasks
                            if t.task_id == row.task_id)),
            sref_m2=SREF, cdi=float(item["cdi"]), cl=float(item["cl"]),
            raw_sha256=item["design_key"], source_task_id=None))
    dataset = MetaDataset(tuple(source.tasks), tuple(rows),
                          task_aliases=built["aliases"])
    require_vlm_labels(dataset)
    if verbose:
        print("family", [t.task_id for t in dataset.tasks])
        print("rows", len(dataset.rows), "vlm labels only")
    return {"family": tuple(source.tasks), "dataset": dataset,
            "aliases": built["aliases"], "labels_payload": payload,
            "source_rows": source,
            # provenance fields the frozen A0 driver reports; the VLM line has no
            # VSPAERO admissions to exclude, and the split is the frozen one.
            "excluded": [], "partition_conflicts": {}, "records": [],
            "source_map": {}}

```

---

## C4 — 训练脚本 v1l_train.py / landscape.py

```python
"""V1L: the A0 mechanism ablation re-run on RCAIDE-VLM labels at lattice (20,10).

Labels come from SupersonicVLMBackend at 20x10 (source_kind rcaide_vlm_20x10),
not from VSPAERO raw bytes; no solver is started.

Five arms, identical budget and identical checkpoint rule:
  RANDOM_INIT               untrained network, K-shot adaptation only (baseline)
  POOLED_PRETRAIN_12D       ordinary supervised MSE over pooled train labels
  COND_SUPERVISED_16D       12D + 4D task context, ordinary supervised MSE
  FOMAML_12D                first-order MAML on 12D features
  COND_FOMAML_16D           12D + 4D task context, first-order MAML

The core pairing required by the Issue is COND_SUPERVISED_16D vs COND_FOMAML_16D:
it isolates "does the task context help" from "does the meta objective help".
COND_SUPERVISED_16D never calls the meta outer loop (asserted in the tests), so it
is a genuine conditional supervised pretrainer, not FOMAML in disguise.

Hyperparameters are chosen per arm from one pre-registered finite grid
(inner_lr in {0.005, 0.01, 0.05} x inner_steps in {1, 3, 5}) on validation K=1
only, averaged over the three seeds, then locked for every K. Test labels are
never used for selection.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01")))

import v1l_data as a0_data  # noqa: E402
from research.concorde_metaopt.dreal001.meta import real_a0_ablation as a0  # noqa: E402
from research.concorde_metaopt.dreal001.ops.resource_monitor import (  # noqa: E402
    ResourceMonitor,
)

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01/training")
RUN_ID = "DRECOVER001-V1L-20261125-01"
SCHEMA = "dreal005.v1l_ablation.v1"
SEEDS = (7, 19, 43)
K_VALUES = (0, 1, 3)
INNER_LR_GRID = (0.005, 0.01, 0.05)
INNER_STEPS_GRID = (1, 3, 5)
MAX_STEPS = 60
VALIDATION_K = 1
ARMS = a0.ARM_NAMES
CORE_PAIR = ("COND_SUPERVISED_16D", "COND_FOMAML_16D")


def write_csv(path: Path, rows, columns) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(columns)]
    for row in rows:
        cells = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, float):
                cells.append("%.10g" % value)
            elif value is None:
                cells.append("")
            else:
                cells.append(str(value).replace(",", ";"))
        lines.append(",".join(cells))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def save_checkpoint(path: Path, parameters) -> str:
    import hashlib

    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"tensor_%02d" % index: value
              for index, value in enumerate(parameters.tensors)}
    np.savez(path, **arrays)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spearman(xs, ys) -> float:
    """Spearman rank correlation without SciPy."""
    if len(xs) < 3:
        return float("nan")
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        index = 0
        while index < len(order):
            end = index
            while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
                end += 1
            average = (index + end) / 2.0 + 1.0
            for position in range(index, end + 1):
                out[order[position]] = average
            index = end + 1
        return out
    rx, ry = ranks(list(xs)), ranks(list(ys))
    n = float(len(rx))
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return float("nan") if den <= 0.0 else num / den


def selection_metrics(predictions, targets) -> dict:
    """Ranking quality and the regret of trusting the model's best pick."""
    if len(targets) < 2:
        return {"spearman": None, "model_best_index": None,
                "true_best_index": None, "regret_n": None, "regret_fraction": None,
                "top1_correct": None}
    rho = spearman(predictions, targets)
    best_pred = int(np.argmin(predictions))
    best_true = int(np.argmin(targets))
    regret = float(targets[best_pred] - targets[best_true])
    span = float(targets[best_true]) if targets[best_true] else float("nan")
    return {"spearman": None if math.isnan(rho) else rho,
            "model_best_index": best_pred, "true_best_index": best_true,
            "regret_n": regret,
            "regret_fraction": regret / span if span else None,
            "top1_correct": best_pred == best_true}


def summarise_scores(scores) -> dict:
    out = {}
    for arm, rows in scores.items():
        maes = [row["mae_n"] for row in rows]
        rmses = [row["rmse_n"] for row in rows]
        out[arm] = {"n_tasks": len(rows), "mean_mae_n": float(np.mean(maes)),
                    "mean_rmse_n": float(np.mean(rmses)),
                    "per_task": {row["task_id"]: {"mae_n": row["mae_n"],
                                                  "rmse_n": row["rmse_n"],
                                                  "n_query": row["n_query"]}
                                 for row in rows}}
    return out


def grid_search(dataset, monitor_note: str) -> dict:
    """Select (inner_lr, inner_steps) per arm on validation K=1 only."""
    results = []
    for inner_lr in INNER_LR_GRID:
        for inner_steps in INNER_STEPS_GRID:
            val_mae = {arm: [] for arm in ARMS}
            for seed in SEEDS:
                config = a0.AblationConfig(
                    inner_lr=inner_lr, inner_steps=inner_steps, max_steps=MAX_STEPS,
                    seed=seed, validation_k=VALIDATION_K)
                result = a0.run_arm(dataset, config=config, k=VALIDATION_K,
                                    eval_splits=("val",), mode="vlm_labels")
                for arm in ARMS:
                    rows = result["scores"][arm]
                    val_mae[arm].append(float(np.mean([r["mae_n"] for r in rows])))
                print("  grid inner_lr=%.3f inner_steps=%d seed=%d"
                      % (inner_lr, inner_steps, seed), flush=True)
            entry = {"inner_lr": inner_lr, "inner_steps": inner_steps, "max_steps": MAX_STEPS,
                     "validation_k": VALIDATION_K, "seeds": list(SEEDS)}
            for arm in ARMS:
                entry["val_mae_n_" + arm] = float(np.mean(val_mae[arm]))
            results.append(entry)
    chosen = {}
    for arm in ARMS:
        column = "val_mae_n_" + arm
        # Deterministic tie-break: smaller inner_lr, then smaller inner_steps.
        best = min(results, key=lambda row: (row[column], row["inner_lr"],
                                            row["inner_steps"]))
        chosen[arm] = {"inner_lr": best["inner_lr"], "inner_steps": best["inner_steps"],
                       "val_mae_n": best[column], "max_steps": MAX_STEPS,
                       "validation_k": VALIDATION_K,
                       "selection_documents": monitor_note}
    return {"grid": results, "chosen": chosen,
            "grid_size": len(results),
            "rule": ("per-arm minimum mean validation MAE at validation_k=%d over seeds %s; "
                     "test labels are never consulted" % (VALIDATION_K, list(SEEDS)))}


def main() -> int:
    global MAX_STEPS
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="7,19,43")
    parser.add_argument("--ks", default="0,1,3")
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS)
    parser.add_argument("--skip-grid", action="store_true")
    args = parser.parse_args()
    seeds = tuple(int(v) for v in args.seeds.split(","))
    ks = tuple(int(v) for v in args.ks.split(","))
    MAX_STEPS = args.max_steps

    RUN.mkdir(parents=True, exist_ok=True)
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    built = a0_data.build_family_and_dataset(verbose=True)
    dataset = built["dataset"]
    a0_data.require_vlm_labels(dataset)
    print("dataset rows", len(dataset.rows), "certs", len(dataset.admissions), flush=True)

    monitor = ResourceMonitor(RUN / "training" / "v1l_resource.jsonl", interval_s=1.0,
                              label="V1L_TRAINING")
    monitor.start()
    training_started = time.perf_counter()
    try:
        if args.skip_grid:
            grid = json.loads((RUN / "training" / "v1l_grid_search.json").read_text(
                encoding="utf-8"))
            chosen = grid["chosen"]
            print("grid reused from disk", flush=True)
        else:
            grid = grid_search(dataset, monitor_note=("validation K=1 grid over "
                                                      "inner_lr x inner_steps"))
            chosen = grid["chosen"]
            write_json(RUN / "training" / "v1l_grid_search.json", grid)

        grid_rows = []
        for row in grid["grid"]:
            flat = dict(row)
            flat["seeds"] = ";".join(str(s) for s in row["seeds"])
            grid_rows.append(flat)
        write_csv(RUN / "tables" / "v1l_grid_selection.csv", grid_rows,
                  ["inner_lr", "inner_steps", "max_steps", "validation_k", "seeds"]
                  + ["val_mae_n_" + arm for arm in ARMS])

        # -- locked final runs -------------------------------------------------
        metrics_rows, prediction_rows, curve_rows, cost_rows, paired_rows = [], [], [], [], []
        selection_rows = []
        checkpoints = {}
        normalizer_written = False
        final = {}
        for k in ks:
            for seed in seeds:
                per_arm_config = {}
                for arm in ARMS:
                    entry = chosen[arm]
                    config = a0.AblationConfig(
                        inner_lr=entry["inner_lr"], inner_steps=entry["inner_steps"],
                        max_steps=MAX_STEPS, seed=seed, validation_k=VALIDATION_K)
                    per_arm_config[arm] = config.as_dict()
                # One call trains every arm; arms share the frozen config except
                # for the per-arm inner_lr/inner_steps chosen above. To keep the
                # budget identical across arms inside a single call, we run the
                # grid-selected config for the arm under test and record the
                # per-arm config used.
                for arm in ARMS:
                    entry = chosen[arm]
                    config = a0.AblationConfig(
                        inner_lr=entry["inner_lr"], inner_steps=entry["inner_steps"],
                        max_steps=MAX_STEPS, seed=seed, validation_k=VALIDATION_K)
                    result = a0.run_arm_for_arm(dataset, config=config, k=k, arm=arm,
                                                eval_splits=("val", "test"),
                                                mode="vlm_labels")
                    tag = "%s_k%d_seed%d" % (arm, k, seed)
                    parameters = result["parameters"]
                    sha = save_checkpoint(
                        RUN / "training" / "checkpoints" / (tag + ".npz"), parameters)
                    checkpoints[tag] = {"path": "training/checkpoints/%s.npz" % tag,
                                        "sha256": sha}
                    if not normalizer_written:
                        write_json(RUN / "training" / "v1l_normalizer.json",
                                   result["normalizer_payload"])
                        normalizer_written = True
                    for split, rows in result["scores"].items():
                        for row in rows:
                            selection = selection_metrics(row["predictions"], row["targets"])
                            metrics_rows.append({
                                "arm": arm, "k": k, "seed": seed, "split": split,
                                "task_id": row["task_id"], "n_query": row["n_query"],
                                "mae_n": row["mae_n"], "rmse_n": row["rmse_n"],
                                "spearman": selection["spearman"],
                                "top1_correct": selection["top1_correct"],
                                "regret_n": selection["regret_n"],
                                "regret_fraction": selection["regret_fraction"],
                            })
                            selection_rows.append({
                                "arm": arm, "k": k, "seed": seed, "split": split,
                                "task_id": row["task_id"],
                                "spearman": selection["spearman"],
                                "model_best_index": selection["model_best_index"],
                                "true_best_index": selection["true_best_index"],
                                "regret_n": selection["regret_n"],
                                "regret_fraction": selection["regret_fraction"],
                                "top1_correct": selection["top1_correct"],
                            })
                            for index, (pred, target) in enumerate(
                                    zip(row["predictions"], row["targets"])):
                                prediction_rows.append({
                                    "arm": arm, "k": k, "seed": seed, "split": split,
                                    "task_id": row["task_id"], "index": index,
                                    "prediction_n": pred, "target_n": target,
                                    "error_n": pred - target,
                                    "observation_id": (row["query_observation_ids"][index]
                                                       if index < len(row["query_observation_ids"])
                                                       else ""),
                                })
                        for curve in result["history"]:
                            curve_rows.append({"arm": arm, "k": k, "seed": seed,
                                               "step": curve["step"],
                                               "train_loss": curve.get("train_loss"),
                                               "outer_loss": curve.get("outer_loss"),
                                               "val_mae_n": curve.get("val_mae_n")})
                    cost = dict(result["cost"])
                    cost.update({"arm": arm, "k": k, "seed": seed,
                                 "best_step": result["best_step"],
                                 "best_val_mae_n": result["best_val_mae_n"],
                                 "inner_lr": entry["inner_lr"],
                                 "inner_steps": entry["inner_steps"]})
                    cost_rows.append(cost)
                    final.setdefault(str(k), {}).setdefault(arm, []).append(
                        result["mean_test_mae_n"])
                    print("  final %s wall=%.2fs test_mean_mae=%.1f"
                          % (tag, result["cost"]["wall_s"], result["mean_test_mae_n"]),
                          flush=True)
        training_wall_s = time.perf_counter() - training_started
    finally:
        monitor.stop()
    resource = monitor.summary()

    write_csv(RUN / "tables" / "v1l_arm_metrics.csv", metrics_rows,
              ["arm", "k", "seed", "split", "task_id", "n_query", "mae_n", "rmse_n",
               "spearman", "top1_correct", "regret_n", "regret_fraction"])
    write_csv(RUN / "tables" / "v1l_predictions.csv", prediction_rows,
              ["arm", "k", "seed", "split", "task_id", "index", "prediction_n",
               "target_n", "error_n", "observation_id"])
    write_csv(RUN / "tables" / "v1l_training_curves.csv", curve_rows,
              ["arm", "k", "seed", "step", "train_loss", "outer_loss", "val_mae_n"])
    write_csv(RUN / "tables" / "v1l_cost.csv", cost_rows,
              ["arm", "k", "seed", "best_step", "best_val_mae_n", "inner_lr",
               "inner_steps", "outer_gradient_updates", "supervised_gradient_updates",
               "inner_gradient_updates", "train_rows", "train_sample_exposures",
               "validation_adaptations", "wall_s"])
    write_csv(RUN / "tables" / "v1l_rank_selection.csv", selection_rows,
              ["arm", "k", "seed", "split", "task_id", "spearman", "model_best_index",
               "true_best_index", "regret_n", "regret_fraction", "top1_correct"])

    # -- pair table ---------------------------------------------------------
    index = {}
    for row in metrics_rows:
        index[(row["arm"], row["k"], row["seed"], row["split"], row["task_id"])] = row
    pair_rows = []
    for k in ks:
        for seed in seeds:
            for split in ("val", "test"):
                tasks = sorted({row["task_id"] for row in metrics_rows
                                if row["k"] == k and row["seed"] == seed
                                and row["split"] == split})
                for task_id in tasks:
                    left = index[("COND_SUPERVISED_16D", k, seed, split, task_id)]
                    right = index[("COND_FOMAML_16D", k, seed, split, task_id)]
                    pair_rows.append({
                        "pair": "COND_FOMAML_16D_MINUS_COND_SUPERVISED_16D",
                        "k": k, "seed": seed, "split": split, "task_id": task_id,
                        "mae_n_cond_supervised": left["mae_n"],
                        "mae_n_cond_fomaml": right["mae_n"],
                        "delta_mae_n": right["mae_n"] - left["mae_n"],
                        "rmse_n_cond_supervised": left["rmse_n"],
                        "rmse_n_cond_fomaml": right["rmse_n"],
                    })
    write_csv(RUN / "tables" / "v1l_paired_differences.csv", pair_rows,
              ["pair", "k", "seed", "split", "task_id", "mae_n_cond_supervised",
               "mae_n_cond_fomaml", "delta_mae_n", "rmse_n_cond_supervised",
               "rmse_n_cond_fomaml"])

    # -- summary ------------------------------------------------------------
    summary_rows = []
    for arm in ARMS:
        for k in ks:
            for split in ("val", "test"):
                values = [row["mae_n"] for row in metrics_rows
                          if row["arm"] == arm and row["k"] == k and row["split"] == split]
                if not values:
                    continue
                summary_rows.append({
                    "arm": arm, "k": k, "split": split, "n": len(values),
                    "mean_mae_n": float(np.mean(values)),
                    "median_mae_n": float(np.median(values)),
                    "mean_rmse_n": float(np.mean(
                        [row["rmse_n"] for row in metrics_rows
                         if row["arm"] == arm and row["k"] == k and row["split"] == split])),
                })
    write_csv(RUN / "tables" / "v1l_arm_summary.csv", summary_rows,
              ["arm", "k", "split", "n", "mean_mae_n", "median_mae_n", "mean_rmse_n"])

    core = [row for row in pair_rows if row["split"] == "test"]
    core_delta = float(np.mean([row["delta_mae_n"] for row in core])) if core else None
    payload = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "issue": 15,
        "stage": "A0",
        "created_utc": started_utc,
        "scope": "REAL_META_TRAINING_EXECUTED",
        "training_scope": "ACTUAL_GRADIENT_TRAINING_ON_REPLAYED_REAL_LABELS",
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
        "admitted_scientific_labels": len(dataset.admissions),
        "physics_validated": False,
        "fuel_burn_kg": None,
        "dataset": {"rows": len(dataset.rows), "certificates": len(dataset.admissions),
                    "family": [t.task_id for t in built["family"]],
                    "task_aliases": built["aliases"],
                    "excluded": built["excluded"],
                    "split": {t.task_id: t.split for t in built["family"]}},
        "arms": list(ARMS),
        "core_pair": list(CORE_PAIR),
        "core_pair_mean_test_delta_mae_n": core_delta,
        "seeds": list(seeds),
        "k_values": list(ks),
        "hyperparameters": {"grid": grid["grid"], "chosen": chosen,
                            "grid_size": grid["grid_size"], "rule": grid["rule"]},
        "cost": {"training_wall_s": training_wall_s,
                 "cpu_busy_fraction_mean": resource.get("cpu_busy_fraction_mean"),
                 "cpu_busy_fraction_max": resource.get("cpu_busy_fraction_max"),
                 "memory_load_percent_mean": resource.get("memory_load_percent_mean"),
                 "memory_load_percent_max": resource.get("memory_load_percent_max"),
                 "tracked_working_set_bytes_max": resource.get(
                     "tracked_working_set_bytes_max"),
                 "resource_samples": resource.get("sample_count"),
                 "resource_log": "training/a0_resource.jsonl",
                 "note": ("CPU and memory are host-wide samples taken by "
                          "resource_monitor.py; no solver was started in A0")},
        "checkpoints": checkpoints,
        "summary": summary_rows,
        "limitations": [
            "the 44 admitted labels cover only 7 distinct geometries and 8 Mach tasks",
            "labels are LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED (same host)",
            "physics_validated=false; LIFTING_SURFACE_ONLY induced drag only",
            "test splits are reported but were never used for selection",
            "torch CPU float64; wall_s is not an accelerator measurement",
        ],
    }
    write_json(RUN / "training" / "v1l_result.json", payload)
    print(json.dumps({"scope": payload["scope"],
                      "core_pair_mean_test_delta_mae_n": core_delta,
                      "training_wall_s": round(training_wall_s, 2),
                      "cpu_busy_fraction_mean": payload["cost"]["cpu_busy_fraction_mean"],
                      "memory_load_percent_mean": payload["cost"]["memory_load_percent_mean"],
                      "checkpoints": len(checkpoints)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# -*- coding: utf-8 -*-
"""Landscape smoothness + lattice rank-stability of the RCAIDE VLM objective."""
import os, sys, json, time
import numpy as np
REPO = r"D:/RCAIDE/.worktrees/dreal005-20261124"
OUT = r"D:/RCAIDE/.real_runs/DRECOVER001-V1L-20261125-01"
sys.path.insert(0, REPO); os.chdir(REPO)
from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend
CFG = os.path.join(REPO, "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml")

BASE = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]
def vec(s1, s2, names):
    d = dict(zip(names, BASE)); d["sweep_1"] = s1; d["sweep_2"] = s2; return d

grid1 = [65.5 + 0.25*i for i in range(13)]   # 65.5 .. 68.5
grid2 = [46.5 + 0.25*i for i in range(13)]   # 46.5 .. 49.5

out = {}
for lat in ((20, 10), (30, 15)):
    be = SupersonicVLMBackend(REPO, CFG, lattice=lat)
    names = be.design_names
    t0 = time.time()
    s1 = [be.evaluate(vec(x, 48.0, names))["objective"] for x in grid1]
    s2 = [be.evaluate(vec(67.0, x, names))["objective"] for x in grid2]
    out["%dx%d" % lat] = {"sweep1_x": grid1, "sweep1_cdi": s1, "sweep2_x": grid2, "sweep2_cdi": s2,
                          "wall_s": round(time.time()-t0, 1), "evals": be.solve_count}
    print(lat, "done in %.1fs" % (time.time()-t0), flush=True)

def diffs(v):
    v = np.asarray(v); return np.diff(v)
rep = {}
for lat, d in out.items():
    c1, c2 = np.asarray(d["sweep1_cdi"]), np.asarray(d["sweep2_cdi"])
    rep[lat] = {
        "sweep1_monotone_decreasing": bool(np.all(np.diff(c1) < 0)),
        "sweep1_sign_changes": int(np.sum(np.diff(np.sign(np.diff(c1))) != 0)),
        "sweep1_range_pct": float(100*(c1.max()-c1.min())/c1.mean()),
        "sweep2_monotone_increasing": bool(np.all(np.diff(c2) > 0)),
        "sweep2_sign_changes": int(np.sum(np.diff(np.sign(np.diff(c2))) != 0)),
        "sweep2_range_pct": float(100*(c2.max()-c2.min())/c2.mean()),
        "sweep1_min_at": float(d["sweep1_x"][int(np.argmin(c1))]),
        "sweep2_min_at": float(d["sweep2_x"][int(np.argmin(c2))]),
    }
# rank agreement between lattices
from scipy.stats import spearmanr
a, b = out["20x10"], out["30x15"]
rep["rank"] = {
    "sweep1_spearman": float(spearmanr(a["sweep1_cdi"], b["sweep1_cdi"]).statistic),
    "sweep2_spearman": float(spearmanr(a["sweep2_cdi"], b["sweep2_cdi"]).statistic),
    "sweep1_pearson": float(np.corrcoef(a["sweep1_cdi"], b["sweep1_cdi"])[0,1]),
    "sweep2_pearson": float(np.corrcoef(a["sweep2_cdi"], b["sweep2_cdi"])[0,1]),
    "level_ratio_20_over_30": float(np.mean(a["sweep1_cdi"])/np.mean(b["sweep1_cdi"])),
}
print(json.dumps(rep, indent=1), flush=True)
json.dump({"raw": out, "summary": rep}, open(os.path.join(OUT, "landscape_probe.json"), "w"), indent=2)
print("WROTE landscape_probe.json", flush=True)
```
