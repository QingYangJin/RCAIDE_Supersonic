# A5 独立预审 · Issue #13 G1 真实 VSPAERO 批次

## 0. 审查范围
- 只审查 G1 的授权、代码状态、24 个零物理 case 的精确计划 SHA256、会计/停机/上传控制。
- 不审查 G0 已 PASS 的历史原件上传；不审查 G2/G3；不替代人类签字。
- 本轮 A5 为 deepseek-flash 独立上下文单发只读审查。

## 1. Owner 授权
- message ref: m07992
- 原文：“继续执行，把G1阶段也完成，批准实际物理计算”
- 授权上限：24 starts、parallel=1、0 retry、单 case 1200s、每 mini-batch ≤8 starts 或 ≤60 分钟。
- 当前尚无任何 G1 solver 启动：24 个 case 目录均无 case_result.json、无 solver_attempts.jsonl、无 .polar。

## 2. 代码状态
- 分支 research/dreal003-expanded-aero-meta-20261120，base_commit 35d1f115637c3aa57521eec8458cef706944c4af。
- research/concorde_metaopt/dreal001/geometry/solver_runner.py SHA256 cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3
- research/concorde_metaopt/tests/test_recovery_solver_runner.py SHA256 7f29d21cc45cf7deb0469f6504145bb8065cc0d6f22eb59a4e934207a8481da1
- 定向测试 5 passed（日志在 g1 run 根 a1_targeted_tests.log）。
- A1 修复要点：按 case 的 task_spec.json / case_inputs.json 读取 per-case Mach/Rho/Vinf/q/Sref/lift，校验 q 与 0.5*rho*Vinf^2 一致，build_evaluation 使用 per-case 流场；不再使用全局 Mach 2.02/q=20483.94。
- code SHA 与 G0 A5 审查过的 SHA 相同，G1 未修改 solver_runner。

## 3. A1 修复 diff
```diff
﻿diff --git a/research/concorde_metaopt/dreal001/geometry/solver_runner.py b/research/concorde_metaopt/dreal001/geometry/solver_runner.py
index 8b5c6c0..9107974 100644
--- a/research/concorde_metaopt/dreal001/geometry/solver_runner.py
+++ b/research/concorde_metaopt/dreal001/geometry/solver_runner.py
@@ -79,6 +79,87 @@ def _verify_file_hashes(spec: Dict[str, Any], base_dir: Path, label: str,
     return result
 
 
+def _read_optional_json(path: Path) -> Optional[Dict[str, Any]]:
+    if not path.is_file():
+        return None
+    try:
+        return json.loads(path.read_text(encoding="utf-8"))
+    except (OSError, json.JSONDecodeError) as exc:
+        raise PreflightError("case metadata is not readable JSON: %s (%s)" % (path, exc)) from exc
+
+
+def _case_flow_conditions(cwd: Path, basename: str,
+                          geometry_sref_m2: Optional[float] = None) -> Dict[str, Any]:
+    """Resolve one case's physical reference from its own task_spec/case_inputs.
+
+    build_evaluation used to use the global TASK_SPEC.q_pa/mach for every case. A
+    Mach 1.6 case then computed L=q(2.02)*Sref*CL and CL_target=L_ref/(q(2.02)*Sref),
+    which is wrong for the actual deck. Prefer task_spec.json (authoritative), then
+    the .vspaero sweep readback in case_inputs.json, then the frozen default.
+    """
+    spec = _read_optional_json(cwd / "task_spec.json") or {}
+    inputs = _read_optional_json(cwd / "case_inputs.json") or {}
+    sweep = ((inputs.get("sweep_input_readback") or {}).get("inputs_double") or {})
+    flow = spec.get("flow_conditions") or {}
+
+    def first_present(*candidates: Any) -> Any:
+        for candidate in candidates:
+            if candidate is not None and candidate != "":
+                return candidate
+        return None
+
+    values: Dict[str, Any] = {
+        "mach": first_present(spec.get("mach"), sweep.get("MachStart")),
+        "q_pa": first_present(spec.get("dynamic_pressure_pa")),
+        "sref_m2": first_present(spec.get("sref_m2"), geometry_sref_m2, sweep.get("Sref")),
+        "lift_target_n": first_present(spec.get("lift_target_n")),
+        "rho_kg_m3": first_present(flow.get("rho_kg_m3"), sweep.get("Rho")),
+        "vinf_m_s": first_present(flow.get("vinf_m_s"), sweep.get("Vinf")),
+        "cref_m": first_present(spec.get("cref_m"), sweep.get("Cref")),
+        "bref_m": first_present(spec.get("bref_m"), sweep.get("Bref")),
+        "lift_tolerance_rel": first_present(spec.get("lift_tolerance_rel")),
+    }
+    source = "TASK_SPEC_FROZEN_DEFAULT"
+    if spec:
+        source = "CASE_TASK_SPEC"
+    elif sweep:
+        source = "CASE_INPUTS_SWEEP_READBACK"
+    rho = values["rho_kg_m3"]
+    vinf = values["vinf_m_s"]
+    if values["q_pa"] is None and rho is not None and vinf is not None:
+        values["q_pa"] = 0.5 * float(rho) * float(vinf) * float(vinf)
+    if values["q_pa"] is not None and rho is not None and vinf is not None:
+        derived = 0.5 * float(rho) * float(vinf) * float(vinf)
+        if abs(float(values["q_pa"]) - derived) > 1e-6 * max(1.0, abs(derived)):
+            raise PreflightError(
+                "case flow conditions disagree: task q=%.9f Pa but 0.5*rho*Vinf^2=%.9f Pa"
+                % (float(values["q_pa"]), derived))
+    defaults = {"mach": TASK_SPEC.mach, "q_pa": TASK_SPEC.q_pa,
+                "sref_m2": TASK_SPEC.sref_baseline_m2,
+                "lift_target_n": TASK_SPEC.l_ref_n,
+                "rho_kg_m3": TASK_SPEC.rho_kg_m3, "vinf_m_s": TASK_SPEC.vinf_m_s,
+                "cref_m": TASK_SPEC.cref_m, "bref_m": TASK_SPEC.bref_m,
+                "lift_tolerance_rel": TASK_SPEC.lift_tolerance_rel}
+    for name, default in defaults.items():
+        if values[name] is None:
+            values[name] = default
+    for name in ("mach", "q_pa", "sref_m2", "lift_target_n"):
+        values[name] = float(values[name])
+        if not math.isfinite(values[name]) or values[name] <= 0.0:
+            raise PreflightError("case flow %s must be finite and positive, got %r"
+                                 % (name, values[name]))
+    values["lift_tolerance_rel"] = float(values["lift_tolerance_rel"])
+    if not math.isfinite(values["lift_tolerance_rel"]) or values["lift_tolerance_rel"] <= 0.0:
+        raise PreflightError("case flow lift_tolerance_rel must be finite and positive, got %r"
+                             % (values["lift_tolerance_rel"],))
+    values["cl_target"] = float(values["lift_target_n"]) / (
+        float(values["q_pa"]) * float(values["sref_m2"]))
+    values["source"] = source
+    values["task_spec_path"] = str(cwd / "task_spec.json") if spec else None
+    values["case_inputs_path"] = str(cwd / "case_inputs.json") if inputs else None
+    return values
+
+
 def preflight(plan_path: Path, approval_path: Path, attempt_id: str) -> Dict[str, Any]:
     """Validate plan/approval/disk consistency without spawning anything."""
     plan, plan_sha, plan_bytes = _load_json(plan_path)
@@ -112,11 +193,14 @@ def preflight(plan_path: Path, approval_path: Path, attempt_id: str) -> Dict[str
         if not (cwd / (basename + suffix)).is_file():
             raise PreflightError("solver input missing: %s" % (cwd / (basename + suffix)))
     geometry_files = _verify_file_hashes((plan.get("geometry") or {}).get("files") or {}, cwd, "geometry", basename=basename)
+    case_flow = _case_flow_conditions(
+        cwd, basename, (plan.get("geometry") or {}).get("sref_m2"))
     return {
         "plan": plan, "plan_sha256": plan_sha, "plan_bytes": plan_bytes,
         "approval": approval, "approval_sha256": approval_sha, "approval_bytes": approval_bytes,
         "window": status, "exe": exe, "exe_sha256": exe_sha, "cwd": cwd,
         "argv": argv, "basename": basename, "geometry_files": geometry_files,
+        "case_flow": case_flow,
         "solver_config_sha256": geometry_files.get("vspaero", {}).get("sha256"),
         "geometry_sha256": geometry_files.get("vspgeom", {}).get("sha256"),
     }
@@ -296,8 +380,13 @@ def build_evaluation(preflight_record: Dict[str, Any], process: Dict[str, Any],
                      attempt_id: str, status: str) -> Dict[str, Any]:
     plan = preflight_record["plan"]
     geometry = plan.get("geometry") or {}
-    sref = float(geometry.get("sref_m2") or TASK_SPEC.sref_baseline_m2)
-    q = TASK_SPEC.q_pa
+    flow = preflight_record.get("case_flow") or {}
+    sref = float(flow.get("sref_m2") or geometry.get("sref_m2")
+                 or TASK_SPEC.sref_baseline_m2)
+    q = float(flow.get("q_pa") or TASK_SPEC.q_pa)
+    lift_target_n = float(flow.get("lift_target_n") or TASK_SPEC.l_ref_n)
+    lift_tolerance_rel = float(flow.get("lift_tolerance_rel")
+                               or TASK_SPEC.lift_tolerance_rel)
     rows_out: List[Dict[str, Any]] = []
     unique_rows = (polar.get("unique_case_rows") or polar["rows"]) if polar else []
     if polar:
@@ -318,11 +407,12 @@ def build_evaluation(preflight_record: Dict[str, Any], process: Dict[str, Any],
                 dtotal_n = q * sref * float(cdtot)
                 entry.update({
                     "L_N": lift_n, "D_i_N": di_n, "D_total_N": dtotal_n,
-                    "lift_rel_error_vs_Lref": (lift_n - TASK_SPEC.l_ref_n) / TASK_SPEC.l_ref_n,
-                    "lift_match_initial_tol": TASK_SPEC.lift_matched(sref, float(cl)),
+                    "lift_rel_error_vs_Lref": (lift_n - lift_target_n) / lift_target_n,
+                    "lift_match_initial_tol": abs(lift_n - lift_target_n)
+                    <= lift_tolerance_rel * abs(lift_target_n),
                 })
             rows_out.append(entry)
-    cl_target = TASK_SPEC.l_ref_n / (q * sref)
+    cl_target = lift_target_n / (q * sref)
     # Mach 扫描案（P1-05 的 1.8/2.0/2.2）没有 Mach 2.02 行：按最近的 Mach 取子集插值，
     # 绝不把不同 Mach 的行混在一起插值（P1-05 崩溃根因）。
     mach_values: List[float] = []
@@ -334,7 +424,7 @@ def build_evaluation(preflight_record: Dict[str, Any], process: Dict[str, Any],
     match_mach: Optional[float] = None
     match_rows: List[Dict[str, Any]] = []
     if mach_values:
-        target_mach = float(TASK_SPEC.mach)
+        target_mach = float(flow.get("mach") or TASK_SPEC.mach)
         match_mach = min(mach_values, key=lambda m: abs(m - target_mach))
         match_rows = [
             row for row in unique_rows
@@ -358,8 +448,8 @@ def build_evaluation(preflight_record: Dict[str, Any], process: Dict[str, Any],
     match["objective_scope"] = objective_scope
     if len(mach_values) > 1:
         match["lift_match_mach_note"] = (
-            "本 polar 为 Mach 扫描（多 Mach 行）；按离 TASK_SPEC.mach=2.02 最近的 Mach 取子集，"
-            "不增加任何求解器启动，也不跨 Mach 插值"
+            "本 polar 为 Mach 扫描（多 Mach 行）；按离本 case task_spec.mach=%.6g 最近的 Mach 取子集，"
+            "不增加任何求解器启动，也不跨 Mach 插值" % float(flow.get("mach") or TASK_SPEC.mach)
         )
     objective: Dict[str, Any] = {"name": "D_i_N_at_matched_lift", "value": None}
     constraints: Dict[str, Any] = {"lift_matched": False, "alpha_in_window": False,
@@ -430,11 +520,16 @@ def build_evaluation(preflight_record: Dict[str, Any], process: Dict[str, Any],
         "raw_artifacts": outputs,
         "tessellation": geometry.get("tessellation"),
         "reference": {
-            "sref_m2": sref, "cref_m": TASK_SPEC.cref_m, "bref_m": TASK_SPEC.bref_m,
+            "sref_m2": sref,
+            "cref_m": float(flow.get("cref_m") or TASK_SPEC.cref_m),
+            "bref_m": float(flow.get("bref_m") or TASK_SPEC.bref_m),
             "xcg_m": TASK_SPEC.xcg_m, "reference_frame": TASK_SPEC.reference_frame,
-            "mach": TASK_SPEC.mach, "vinf_m_s": TASK_SPEC.vinf_m_s,
-            "rho_kg_m3": TASK_SPEC.rho_kg_m3, "q_pa": q, "recref": TASK_SPEC.recref,
-            "l_ref_n": TASK_SPEC.l_ref_n, "cl_target": cl_target,
+            "mach": float(flow.get("mach") or TASK_SPEC.mach),
+            "vinf_m_s": float(flow.get("vinf_m_s") or TASK_SPEC.vinf_m_s),
+            "rho_kg_m3": float(flow.get("rho_kg_m3") or TASK_SPEC.rho_kg_m3),
+            "q_pa": q, "recref": TASK_SPEC.recref,
+            "l_ref_n": lift_target_n, "cl_target": cl_target,
+            "case_flow_source": flow.get("source"),
             "units": {"L_N": "N", "D_i_N": "N", "sref_m2": "m2", "q_pa": "Pa"},
         },
         "alpha_list_deg": geometry.get("alpha_list_deg") or (plan.get("command") or {}).get("alphas"),
@@ -450,7 +545,7 @@ def build_evaluation(preflight_record: Dict[str, Any], process: Dict[str, Any],
         },
         "rows": rows_out,
         "lift_match": match,
-        "lift_tolerance_rel": TASK_SPEC.lift_tolerance_rel,
+        "lift_tolerance_rel": lift_tolerance_rel,
         "physical_solver_starts": 1,
         "process": {key: process[key] for key in
                     ("exit_code", "timed_out", "wall_s", "stdout_sha256", "stderr_sha256")},
diff --git a/research/concorde_metaopt/tests/test_recovery_solver_runner.py b/research/concorde_metaopt/tests/test_recovery_solver_runner.py
new file mode 100644
index 0000000..37beeae
--- /dev/null
+++ b/research/concorde_metaopt/tests/test_recovery_solver_runner.py
@@ -0,0 +1,141 @@
+import math
+import unittest
+from pathlib import Path
+from unittest.mock import patch
+
+from research.concorde_metaopt.dreal001.geometry import solver_runner
+from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC
+
+
+def task_spec_payload(mach=1.6, q=12851.40843975621, sref=358.25,
+                      lift=1333704.4, rho=0.1153178340089936,
+                      vinf=472.1088294874393):
+    return {
+        "schema": "dreal001.r2_task_spec.v1",
+        "task_id": "fixture-m160",
+        "mach": mach,
+        "dynamic_pressure_pa": q,
+        "sref_m2": sref,
+        "lift_target_n": lift,
+        "lift_tolerance_rel": 0.001,
+        "cref_m": 18.489893,
+        "bref_m": 25.604638,
+        "flow_conditions": {"rho_kg_m3": rho, "vinf_m_s": vinf},
+    }
+
+
+def reader(task_spec=None, case_inputs=None):
+    def read(path):
+        if path.name == "task_spec.json":
+            return task_spec
+        if path.name == "case_inputs.json":
+            return case_inputs
+        return None
+    return read
+
+
+PROCESS = {"exit_code": 0, "timed_out": False, "wall_s": 0.0,
+           "stdout_sha256": "", "stderr_sha256": ""}
+
+
+def row(alpha, cl, cdi):
+    return {"Mach": 1.6, "AoA": alpha, "CLtot": cl, "CDi": cdi,
+            "CDtot": cdi + 0.01, "CDo": 0.01, "_invalid_tokens": {}}
+
+
+def preflight(case_flow):
+    return {
+        "plan": {
+            "run_id": "fixture", "case_id": "fixture-case", "task_id": "fixture-m160",
+            "purpose": "fixture", "solver": {}, "command": {},
+            "geometry": {"sref_m2": 358.25},
+        },
+        "case_flow": case_flow,
+        "exe_sha256": "0" * 64, "argv": [], "cwd": ".", "geometry_sha256": "1" * 64,
+    }
+
+
+class CaseFlowTests(unittest.TestCase):
+    def test_prefers_case_task_spec(self):
+        with patch.object(solver_runner, "_read_optional_json", reader(
+                task_spec=task_spec_payload(),
+                case_inputs={"sweep_input_readback": {"inputs_double": {
+                    "MachStart": 2.02, "Sref": 999.0,
+                    "Vinf": 596.0373972278921, "Rho": 0.1153178340089936}}})):
+            flow = solver_runner._case_flow_conditions(Path("/fixture"), "fixture")
+        self.assertEqual(flow["source"], "CASE_TASK_SPEC")
+        self.assertAlmostEqual(flow["mach"], 1.6)
+        self.assertAlmostEqual(flow["q_pa"], 12851.40843975621)
+        self.assertAlmostEqual(flow["sref_m2"], 358.25)
+        self.assertAlmostEqual(flow["lift_target_n"], 1333704.4)
+        self.assertAlmostEqual(flow["lift_tolerance_rel"], 0.001)
+        self.assertAlmostEqual(flow["cl_target"],
+                               1333704.4 / (12851.40843975621 * 358.25))
+
+    def test_falls_back_to_sweep_readback(self):
+        rho = 0.1153178340089936
+        vinf = math.sqrt(2.0 * 16265.063806566453 / rho)
+        with patch.object(solver_runner, "_read_optional_json", reader(
+                case_inputs={"sweep_input_readback": {"inputs_double": {
+                    "MachStart": 1.8, "Sref": 358.25, "Vinf": vinf, "Rho": rho,
+                    "Cref": 18.489893, "Bref": 25.604638}}})):
+            flow = solver_runner._case_flow_conditions(Path("/fixture"), "fixture")
+        self.assertEqual(flow["source"], "CASE_INPUTS_SWEEP_READBACK")
+        self.assertAlmostEqual(flow["mach"], 1.8)
+        self.assertAlmostEqual(flow["q_pa"], 16265.063806566453)
+        self.assertAlmostEqual(flow["sref_m2"], 358.25)
+        self.assertAlmostEqual(flow["lift_target_n"], TASK_SPEC.l_ref_n)
+
+    def test_rejects_inconsistent_q(self):
+        with patch.object(solver_runner, "_read_optional_json",
+                          reader(task_spec=task_spec_payload(q=999.0))):
+            with self.assertRaisesRegex(solver_runner.PreflightError,
+                                        "case flow conditions disagree"):
+                solver_runner._case_flow_conditions(Path("/fixture"), "fixture")
+
+
+class BuildEvaluationTests(unittest.TestCase):
+    def test_uses_case_flow_not_global(self):
+        cl_target = 1333704.4 / (12851.40843975621 * 358.25)
+        rows = [row(0.0, 0.10, 0.0100), row(5.0, 0.25, 0.0110),
+                row(10.0, 0.40, 0.0120)]
+        flow = {"mach": 1.6, "q_pa": 12851.40843975621, "sref_m2": 358.25,
+                "lift_target_n": 1333704.4, "lift_tolerance_rel": 0.001,
+                "rho_kg_m3": 0.1153178340089936, "vinf_m_s": 472.1088294874393,
+                "cref_m": 18.489893, "bref_m": 25.604638,
+                "cl_target": cl_target, "source": "CASE_TASK_SPEC"}
+        evaluation = solver_runner.build_evaluation(
+            preflight(flow), PROCESS, {}, {"unique_case_rows": rows},
+            "fixture-attempt", "SOLVED")
+        self.assertAlmostEqual(evaluation["reference"]["q_pa"], 12851.40843975621)
+        self.assertAlmostEqual(evaluation["reference"]["mach"], 1.6)
+        self.assertAlmostEqual(evaluation["reference"]["l_ref_n"], 1333704.4)
+        self.assertEqual(evaluation["reference"]["case_flow_source"], "CASE_TASK_SPEC")
+        self.assertAlmostEqual(evaluation["objective"]["sref_m2"], 358.25)
+        self.assertAlmostEqual(evaluation["objective"]["q_pa"], 12851.40843975621)
+        self.assertEqual(evaluation["lift_match_status"], "LIFT_MATCHED_BY_INTERPOLATION")
+        self.assertAlmostEqual(
+            evaluation["objective"]["value"],
+            12851.40843975621 * 358.25 * evaluation["objective"]["cdi_at_matched_lift"])
+        self.assertAlmostEqual(evaluation["lift_tolerance_rel"], 0.001)
+        self.assertEqual(evaluation["physical_solver_starts"], 1)
+
+    def test_marks_lift_within_case_tolerance(self):
+        cl_target = 1333704.4 / (12851.40843975621 * 358.25)
+        rows = [row(0.0, 0.0, 0.0100), row(6.0, cl_target, 0.0115),
+                row(10.0, 0.40, 0.0120)]
+        flow = {"mach": 1.6, "q_pa": 12851.40843975621, "sref_m2": 358.25,
+                "lift_target_n": 1333704.4, "lift_tolerance_rel": 0.001,
+                "source": "CASE_TASK_SPEC"}
+        evaluation = solver_runner.build_evaluation(
+            preflight(flow), PROCESS, {}, {"unique_case_rows": rows},
+            "fixture-attempt", "SOLVED")
+        matched = [item for item in evaluation["rows"]
+                   if abs(item["CLtot"] - cl_target) < 1e-12]
+        self.assertEqual(len(matched), 1)
+        self.assertTrue(matched[0]["lift_match_initial_tol"])
+        self.assertAlmostEqual(matched[0]["lift_rel_error_vs_Lref"], 0.0, places=12)
+
+
+if __name__ == "__main__":
+    unittest.main()

```

## 4. G1 预注册（原文 JSON）
```json
{
  "schema": "dreal003.g1_preregistration.v1",
  "generated_utc": "2026-11-21T08:56:05Z",
  "owner_message_ref": "m07992",
  "authorization_id": "AUTH-DREAL003-G1-20261121-01",
  "run_id": "DRECOVER001-G1-20261121-01",
  "batch_id": "DRECOVER001-G1-20261121-01-B01",
  "branch": "research/dreal003-expanded-aero-meta-20261120",
  "base_commit": "35d1f115637c3aa57521eec8458cef706944c4af",
  "geometry_contract_sha256": "5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15",
  "solver": {
    "path": "D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe",
    "name": "vspaero-3.55.0-v7.2.2-omp1",
    "omp_threads": 1,
    "case_timeout_s": 1200,
    "parallelism": 1,
    "retries": 0,
    "planned_starts": 24,
    "mini_batch_max_starts": 8,
    "mini_batch_max_minutes": 60
  },
  "case_matrix": [
    {
      "case_id": "g1-m160-d00-support",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "support",
      "design": "d00",
      "mach": 1.6,
      "sref_m2": 358.25000000000006,
      "q_pa": 12851.40843975621,
      "cl_target": 0.2896827658750951,
      "alpha_center_deg": 8.319597607874748,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 8.0795976079,
      "alpha_max_deg": 8.5595976079,
      "x12": [
        358.25,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m160-d01-support",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "support",
      "design": "d01",
      "mach": 1.6,
      "sref_m2": 361.8324999999999,
      "q_pa": 12851.40843975621,
      "cl_target": 0.2868146196783122,
      "alpha_center_deg": 8.236207374653254,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 7.9962073747,
      "alpha_max_deg": 8.4762073747,
      "x12": [
        361.8325,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m160-d02-support",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "support",
      "design": "d02",
      "mach": 1.6,
      "sref_m2": 358.25000000000006,
      "q_pa": 12851.40843975621,
      "cl_target": 0.2896827658750951,
      "alpha_center_deg": 8.319597607874748,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 8.0795976079,
      "alpha_max_deg": 8.5595976079,
      "x12": [
        358.25,
        1.83,
        67.5,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m160-d03-query",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "query",
      "design": "d03",
      "mach": 1.6,
      "sref_m2": 354.66749999999996,
      "q_pa": 12851.40843975621,
      "cl_target": 0.29260885441928813,
      "alpha_center_deg": 8.404672492272443,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 8.1646724923,
      "alpha_max_deg": 8.6446724923,
      "x12": [
        354.6675,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m160-d04-query",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "query",
      "design": "d04",
      "mach": 1.6,
      "sref_m2": 358.25000000000006,
      "q_pa": 12851.40843975621,
      "cl_target": 0.2896827658750951,
      "alpha_center_deg": 8.319597607874748,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 8.0795976079,
      "alpha_max_deg": 8.5595976079,
      "x12": [
        358.25,
        1.83,
        66.5,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m160-d05-query",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "query",
      "design": "d05",
      "mach": 1.6,
      "sref_m2": 358.25000000000006,
      "q_pa": 12851.40843975621,
      "cl_target": 0.2896827658750951,
      "alpha_center_deg": 8.319597607874748,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 8.0795976079,
      "alpha_max_deg": 8.5595976079,
      "x12": [
        358.25,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        34.5882,
        0.0
      ]
    },
    {
      "case_id": "g1-m180-d00-support",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "support",
      "design": "d00",
      "mach": 1.8,
      "sref_m2": 358.25000000000006,
      "q_pa": 16265.063806566453,
      "cl_target": 0.22888514834575416,
      "alpha_center_deg": 6.551930565389395,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 6.3119305654,
      "alpha_max_deg": 6.7919305654,
      "x12": [
        358.25,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m180-d01-support",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "support",
      "design": "d01",
      "mach": 1.8,
      "sref_m2": 361.8324999999999,
      "q_pa": 16265.063806566453,
      "cl_target": 0.22661895875817253,
      "alpha_center_deg": 6.486041986053893,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 6.2460419861,
      "alpha_max_deg": 6.7260419861,
      "x12": [
        361.8325,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m180-d02-support",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "support",
      "design": "d02",
      "mach": 1.8,
      "sref_m2": 358.25000000000006,
      "q_pa": 16265.063806566453,
      "cl_target": 0.22888514834575416,
      "alpha_center_deg": 6.551930565389395,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 6.3119305654,
      "alpha_max_deg": 6.7919305654,
      "x12": [
        358.25,
        1.83,
        67.5,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m180-d03-query",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "query",
      "design": "d03",
      "mach": 1.8,
      "sref_m2": 354.66749999999996,
      "q_pa": 16265.063806566453,
      "cl_target": 0.2311971195411659,
      "alpha_center_deg": 6.619150227135721,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 6.3791502271,
      "alpha_max_deg": 6.8591502271,
      "x12": [
        354.6675,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m180-d04-query",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "query",
      "design": "d04",
      "mach": 1.8,
      "sref_m2": 358.25000000000006,
      "q_pa": 16265.063806566453,
      "cl_target": 0.22888514834575416,
      "alpha_center_deg": 6.551930565389395,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 6.3119305654,
      "alpha_max_deg": 6.7919305654,
      "x12": [
        358.25,
        1.83,
        66.5,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m180-d05-query",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "query",
      "design": "d05",
      "mach": 1.8,
      "sref_m2": 358.25000000000006,
      "q_pa": 16265.063806566453,
      "cl_target": 0.22888514834575416,
      "alpha_center_deg": 6.551930565389395,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 6.3119305654,
      "alpha_max_deg": 6.7919305654,
      "x12": [
        358.25,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        34.5882,
        0.0
      ]
    },
    {
      "case_id": "g1-m202-d00-support",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "support",
      "design": "d00",
      "mach": 2.02,
      "sref_m2": 358.25000000000006,
      "q_pa": 20483.940233430174,
      "cl_target": 0.18174391741992046,
      "alpha_center_deg": 5.181317642776557,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 4.9413176428,
      "alpha_max_deg": 5.4213176428,
      "x12": [
        358.25,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m202-d01-support",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "support",
      "design": "d01",
      "mach": 2.02,
      "sref_m2": 361.8324999999999,
      "q_pa": 20483.940233430174,
      "cl_target": 0.17994447269299063,
      "alpha_center_deg": 5.128999488417419,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 4.8889994884,
      "alpha_max_deg": 5.3689994884,
      "x12": [
        361.8325,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m202-d02-support",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "support",
      "design": "d02",
      "mach": 2.02,
      "sref_m2": 358.25000000000006,
      "q_pa": 20483.940233430174,
      "cl_target": 0.18174391741992046,
      "alpha_center_deg": 5.181317642776557,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 4.9413176428,
      "alpha_max_deg": 5.4213176428,
      "x12": [
        358.25,
        1.83,
        67.5,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m202-d03-query",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "query",
      "design": "d03",
      "mach": 2.02,
      "sref_m2": 354.66749999999996,
      "q_pa": 20483.940233430174,
      "cl_target": 0.18357971456557629,
      "alpha_center_deg": 5.234692729546996,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 4.9946927295,
      "alpha_max_deg": 5.4746927295,
      "x12": [
        354.6675,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m202-d04-query",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "query",
      "design": "d04",
      "mach": 2.02,
      "sref_m2": 358.25000000000006,
      "q_pa": 20483.940233430174,
      "cl_target": 0.18174391741992046,
      "alpha_center_deg": 5.181317642776557,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 4.9413176428,
      "alpha_max_deg": 5.4213176428,
      "x12": [
        358.25,
        1.83,
        66.5,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m202-d05-query",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "query",
      "design": "d05",
      "mach": 2.02,
      "sref_m2": 358.25000000000006,
      "q_pa": 20483.940233430174,
      "cl_target": 0.18174391741992046,
      "alpha_center_deg": 5.181317642776557,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 4.9413176428,
      "alpha_max_deg": 5.4213176428,
      "x12": [
        358.25,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        34.5882,
        0.0
      ]
    },
    {
      "case_id": "g1-m240-d00-support",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "support",
      "design": "d00",
      "mach": 2.4,
      "sref_m2": 358.25000000000006,
      "q_pa": 28915.66898945147,
      "cl_target": 0.12874789594448674,
      "alpha_center_deg": 3.6404789660017562,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 3.400478966,
      "alpha_max_deg": 3.880478966,
      "x12": [
        358.25,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m240-d01-support",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "support",
      "design": "d01",
      "mach": 2.4,
      "sref_m2": 361.8324999999999,
      "q_pa": 28915.66898945147,
      "cl_target": 0.12747316430147207,
      "alpha_center_deg": 3.603416640125536,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 3.3634166401,
      "alpha_max_deg": 3.8434166401,
      "x12": [
        361.8325,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m240-d02-support",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "support",
      "design": "d02",
      "mach": 2.4,
      "sref_m2": 358.25000000000006,
      "q_pa": 28915.66898945147,
      "cl_target": 0.12874789594448674,
      "alpha_center_deg": 3.6404789660017562,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 3.400478966,
      "alpha_max_deg": 3.880478966,
      "x12": [
        358.25,
        1.83,
        67.5,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m240-d03-query",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "query",
      "design": "d03",
      "mach": 2.4,
      "sref_m2": 354.66749999999996,
      "q_pa": 28915.66898945147,
      "cl_target": 0.13004837974190583,
      "alpha_center_deg": 3.6782900257340643,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 3.4382900257,
      "alpha_max_deg": 3.9182900257,
      "x12": [
        354.6675,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m240-d04-query",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "query",
      "design": "d04",
      "mach": 2.4,
      "sref_m2": 358.25000000000006,
      "q_pa": 28915.66898945147,
      "cl_target": 0.12874789594448674,
      "alpha_center_deg": 3.6404789660017562,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 3.400478966,
      "alpha_max_deg": 3.880478966,
      "x12": [
        358.25,
        1.83,
        66.5,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        33.91,
        0.0
      ]
    },
    {
      "case_id": "g1-m240-d05-query",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "query",
      "design": "d05",
      "mach": 2.4,
      "sref_m2": 358.25000000000006,
      "q_pa": 28915.66898945147,
      "cl_target": 0.12874789594448674,
      "alpha_center_deg": 3.6404789660017562,
      "alpha_points": 17,
      "alpha_step_deg": 0.03,
      "alpha_min_deg": 3.400478966,
      "alpha_max_deg": 3.880478966,
      "x12": [
        358.25,
        1.83,
        67.0,
        48.0,
        71.0,
        0.480469,
        0.945313,
        0.408284,
        0.130178,
        0.0,
        34.5882,
        0.0
      ]
    }
  ],
  "label_acceptance": {
    "denominator": "successful solver starts with a case_result and polar",
    "target_valid_label_rate": 0.7,
    "lift_tolerance_rel": 0.001,
    "admission": "RealAdmissionManifest + independent local audit per case; only LIFT_MATCHED rows admitted",
    "failed_cases": "objective=null, no rerun inside G1"
  },
  "stop_conditions": [
    "any start refused by accounting/window/plan validation",
    "any solver timeout or missing process result",
    "two consecutive non-SOLVED cases",
    "accounting ledger not conserved after a mini-batch",
    "any raw file hash mismatch or upload/readback mismatch"
  ],
  "upload": {
    "repository_dir": "research/concorde_metaopt/optimization_runs/DRECOVER001-G1-20261121-01",
    "raw_cases": "raw_cases/<case_id>/",
    "required_tables": [
      "all_evaluations.csv",
      "admitted_labels.csv",
      "failed_or_null.csv",
      "attempt_ledger.csv"
    ],
    "raw_extensions": [
      ".vspgeom",
      ".vspaero",
      ".polar",
      ".history",
      ".lod",
      ".adb",
      ".vsp3"
    ],
    "after_each_mini_batch": "upload raw+logs+accounting, then read back SHA256SUMS from remote before next mini-batch"
  },
  "a5_requirement": "independent deepseek-flash read-only review of this preregistration and exact case plan SHA256 manifest before first start",
  "physical_solver_starts_actual": 0,
  "status": "PRE_REGISTERED_PENDING_A5_AND_GO"
}

```

## 5. 24 个 case 的精确计划清单
- 4 个任务：M160 train、M180 val、M202 train、M240 test；每任务 6 个设计（3 support / 3 query）。
- 每个 case 17 个迎角点、步长 0.03°，围绕由升力目标反算的 alpha center，±0.24° 余量；升力容差 1e-3。
- 24 个 case 均已生成 plan.json / approval.json / task_spec.json / case_inputs.json / .vspgeom / .vspaero，未生成 .polar。
- 每 case budget.physical_solver_starts_max=1，approval.max_starts=1；全局 24 由 batch runner 强制。
```json
{
  "schema": "dreal003.g1_case_manifest.v1",
  "run_id": "DRECOVER001-G1-20261121-01",
  "batch_id": "DRECOVER001-G1-20261121-01-B01",
  "authorization_id": "AUTH-DREAL003-G1-20261121-01",
  "case_count": 24,
  "cases": [
    {
      "case_id": "g1-m160-d00-support",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "support",
      "design": "d00",
      "mach": 1.6,
      "plan_sha256": "29eca877ed13d0d176008247024f49ea682a747f0adcca692ac4e7ed9e216f43",
      "approval_sha256": "5a5e372592bdff2d936fc35d93b67e30c2a70fbc75f682638531a72c3f58f97d",
      "task_spec_sha256": "0bf60403f6dc50f6067fd57bdaf08b98f907e155a01866c38ca92abbb919afa3",
      "vspgeom_sha256": "f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34",
      "vspaero_sha256": "3ac64d37d71c327263235221fbe3b21aa8272087d17b7e14352f7e2e6df0cbce",
      "vkey_sha256": "ad19606f60bb49d79e5557881f06ab073ad537e902a26ae263a0cf5c3d357495",
      "case_inputs_sha256": "1854065880a59d0bf963369c373492b6dc484d1ba658efb84ec486b11f1e984f",
      "audit_sha256": null,
      "alpha_grid_deg": [
        8.0795976079,
        8.1095976079,
        8.1395976079,
        8.1695976079,
        8.1995976079,
        8.2295976079,
        8.2595976079,
        8.2895976079,
        8.3195976079,
        8.3495976079,
        8.3795976079,
        8.4095976079,
        8.4395976079,
        8.4695976079,
        8.4995976079,
        8.5295976079,
        8.5595976079
      ]
    },
    {
      "case_id": "g1-m160-d01-support",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "support",
      "design": "d01",
      "mach": 1.6,
      "plan_sha256": "0d7e4c78c23fe95ceae3124fe0dfc4f86670fb590b8539c963b0703b203a6df4",
      "approval_sha256": "8d411691d654052f828aef25c072239fb459404a0055e6d318a042e9eb65bbfe",
      "task_spec_sha256": "f53bdf6a05b3518e9237aef63880b66d395dad16d3eb1dcab4f8b1d789f0bfc1",
      "vspgeom_sha256": "31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9",
      "vspaero_sha256": "b79cf707438435b2013e136a1b4bce5c48705ab916afac69c27ac787f615e164",
      "vkey_sha256": "2a6389f5011d1da0b01b9d28840c14a4c3fb8a4a1d86e36caead70f576ca8fa6",
      "case_inputs_sha256": "7929b0d3d7a5d2ddb331953b8a5b56655b23163ff6b48a13ed83f7b3ae75eb02",
      "audit_sha256": null,
      "alpha_grid_deg": [
        7.9962073747,
        8.0262073747,
        8.0562073747,
        8.0862073747,
        8.1162073747,
        8.1462073747,
        8.1762073747,
        8.2062073747,
        8.2362073747,
        8.2662073747,
        8.2962073747,
        8.3262073747,
        8.3562073747,
        8.3862073747,
        8.4162073747,
        8.4462073747,
        8.4762073747
      ]
    },
    {
      "case_id": "g1-m160-d02-support",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "support",
      "design": "d02",
      "mach": 1.6,
      "plan_sha256": "8c547c2d93f091a6e7c90e29fbcedc4ea84910e01aca77a380b346584291c669",
      "approval_sha256": "87ab3e72dcf0b0724a302b3c31e915143359760cee0cae6e60cbc146d9a49beb",
      "task_spec_sha256": "e4bfe77388ddb74840168d9cce83caf11c489a1c205128646db12d41fa4bcdb2",
      "vspgeom_sha256": "6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05",
      "vspaero_sha256": "3ac64d37d71c327263235221fbe3b21aa8272087d17b7e14352f7e2e6df0cbce",
      "vkey_sha256": "9a6c73c0a1082f1832f33b08aa51ca1060f9e38fc03a2fa3fe5e172f313c0368",
      "case_inputs_sha256": "eb7024fb330d5f8edafbd6acd0f782a1af6ee6520f1cd522e8fef2a3ae56185d",
      "audit_sha256": null,
      "alpha_grid_deg": [
        8.0795976079,
        8.1095976079,
        8.1395976079,
        8.1695976079,
        8.1995976079,
        8.2295976079,
        8.2595976079,
        8.2895976079,
        8.3195976079,
        8.3495976079,
        8.3795976079,
        8.4095976079,
        8.4395976079,
        8.4695976079,
        8.4995976079,
        8.5295976079,
        8.5595976079
      ]
    },
    {
      "case_id": "g1-m160-d03-query",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "query",
      "design": "d03",
      "mach": 1.6,
      "plan_sha256": "80bd4b689059e6ebbdbf4b48e383f4aed7fcf8ac4031c17a161b5687943e790f",
      "approval_sha256": "e176843e863d97f888398594de8723f84e17e4265ab91f39ceef7e381aa3a6e3",
      "task_spec_sha256": "ff7ed366bb8b44663d172f073e671a84d40314cc68c5b17a9fa3aacd42ba8842",
      "vspgeom_sha256": "78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12",
      "vspaero_sha256": "7e55cc2556d4c846c27ade4485743a098dd7a93fdd3920335d39c5794f2f4b0b",
      "vkey_sha256": "0eb00ee98f0d1a0933e0869e0f89dde50cdab193099c2f794bd0600b2e215a39",
      "case_inputs_sha256": "22d09eb9a128c1b4eb5e6aa0a03d2e9cd4d365baa22cd5facacc70489750d81c",
      "audit_sha256": null,
      "alpha_grid_deg": [
        8.1646724923,
        8.1946724923,
        8.2246724923,
        8.2546724923,
        8.2846724923,
        8.3146724923,
        8.3446724923,
        8.3746724923,
        8.4046724923,
        8.4346724923,
        8.4646724923,
        8.4946724923,
        8.5246724923,
        8.5546724923,
        8.5846724923,
        8.6146724923,
        8.6446724923
      ]
    },
    {
      "case_id": "g1-m160-d04-query",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "query",
      "design": "d04",
      "mach": 1.6,
      "plan_sha256": "a6bf2a16643e3bfdfe868aefef48c345c581d2de21a5fdf81c0483ef75af2972",
      "approval_sha256": "8e8b6eb2d5fdf36a3d30ec540d96ddbcab1330ae1b7b970d092ca6615d5f4170",
      "task_spec_sha256": "adc0eef419465594e025b449f0db5a3731e6d8dca83e6a18e08ea4c1f7112e31",
      "vspgeom_sha256": "2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2",
      "vspaero_sha256": "3ac64d37d71c327263235221fbe3b21aa8272087d17b7e14352f7e2e6df0cbce",
      "vkey_sha256": "c19ec60c5fee23718251b66c9d9ad38a453abcc0a7c5f8465996590f0f490eb6",
      "case_inputs_sha256": "75e2b21c9ed82a880ce7140105a387a8058835a763710ac46c1b2b2e736887a7",
      "audit_sha256": null,
      "alpha_grid_deg": [
        8.0795976079,
        8.1095976079,
        8.1395976079,
        8.1695976079,
        8.1995976079,
        8.2295976079,
        8.2595976079,
        8.2895976079,
        8.3195976079,
        8.3495976079,
        8.3795976079,
        8.4095976079,
        8.4395976079,
        8.4695976079,
        8.4995976079,
        8.5295976079,
        8.5595976079
      ]
    },
    {
      "case_id": "g1-m160-d05-query",
      "task_id": "DREAL003-G1-M160",
      "split": "train",
      "partition": "query",
      "design": "d05",
      "mach": 1.6,
      "plan_sha256": "cbd9d2830fb644655e600768da5e92eb170a498ca69831dfd26bac225e8abfeb",
      "approval_sha256": "0912c9f07d85589b5dbce04e720a252f7e364a0a050a683247e2d76ca2b48c81",
      "task_spec_sha256": "8c45ea0302e42afd6f7fdcaca93ea0bf9c56572a19c9d84c7905d5694a885da5",
      "vspgeom_sha256": "0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55",
      "vspaero_sha256": "3ac64d37d71c327263235221fbe3b21aa8272087d17b7e14352f7e2e6df0cbce",
      "vkey_sha256": "2e1bacb04de189f219aa26f0b98cb720cc8b224e48092e64d2167c09bcc42674",
      "case_inputs_sha256": "6cf86ec555cb443bfeb5d05af90500600caabd1fc79549d489de4ab1d73d2deb",
      "audit_sha256": null,
      "alpha_grid_deg": [
        8.0795976079,
        8.1095976079,
        8.1395976079,
        8.1695976079,
        8.1995976079,
        8.2295976079,
        8.2595976079,
        8.2895976079,
        8.3195976079,
        8.3495976079,
        8.3795976079,
        8.4095976079,
        8.4395976079,
        8.4695976079,
        8.4995976079,
        8.5295976079,
        8.5595976079
      ]
    },
    {
      "case_id": "g1-m180-d00-support",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "support",
      "design": "d00",
      "mach": 1.8,
      "plan_sha256": "7be03707ac0b4f82b1c3ca51e0733ed02381b715ac618cc6158b85350275004e",
      "approval_sha256": "d3f2a0a78825e790accf0b98823a6a5b1729f96fd99ea95407e349c46239aee2",
      "task_spec_sha256": "f7a509a92c9a65f0a90d892f8b25edbf170f6b0fac112b57b0e9ca7d4df8db5d",
      "vspgeom_sha256": "f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34",
      "vspaero_sha256": "848af60fe321a5b4457687140d6bcb0b13856bd73e10ff230c3da2cf6bb6fb51",
      "vkey_sha256": "c3d1f59077c65974aaaa5a8a36e461b0c4dcc68516a8c6ff3e7cdd8024ceb922",
      "case_inputs_sha256": "6ee45716eb4a0c202350ceaaa3702fe9d5324058edb045e6ef7f386b9896ed6a",
      "audit_sha256": null,
      "alpha_grid_deg": [
        6.3119305654,
        6.3419305654,
        6.3719305654,
        6.4019305654,
        6.4319305654,
        6.4619305654,
        6.4919305654,
        6.5219305654,
        6.5519305654,
        6.5819305654,
        6.6119305654,
        6.6419305654,
        6.6719305654,
        6.7019305654,
        6.7319305654,
        6.7619305654,
        6.7919305654
      ]
    },
    {
      "case_id": "g1-m180-d01-support",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "support",
      "design": "d01",
      "mach": 1.8,
      "plan_sha256": "b5d41fcec85b694bf13c85dd8cd597bb4fcf8ff16fa72b022c600eaf8cf469cf",
      "approval_sha256": "cd46f4efd7d52f81713b7f167a3bc93f52af9766d46e78d0713a1b48d1cdc114",
      "task_spec_sha256": "c34fec3c1f626323ef522bfbd4ce85ada465a7525da30a0cffcd610379e5f20b",
      "vspgeom_sha256": "31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9",
      "vspaero_sha256": "d107d35e017271b850fd02a18eeb289c339898f510ec9df454cdd6734d56cfb5",
      "vkey_sha256": "db58ef15eaa5a45e134401ece15d0f46653e42124b4d99b7d412abc1fc209b29",
      "case_inputs_sha256": "bc8262c0fb09c74e23802aa8acbceff9ba33577e8bc5f67e0d4cfeeefe516f0c",
      "audit_sha256": null,
      "alpha_grid_deg": [
        6.2460419861,
        6.2760419861,
        6.3060419861,
        6.3360419861,
        6.3660419861,
        6.3960419861,
        6.4260419861,
        6.4560419861,
        6.4860419861,
        6.5160419861,
        6.5460419861,
        6.5760419861,
        6.6060419861,
        6.6360419861,
        6.6660419861,
        6.6960419861,
        6.7260419861
      ]
    },
    {
      "case_id": "g1-m180-d02-support",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "support",
      "design": "d02",
      "mach": 1.8,
      "plan_sha256": "8d5dfb12085dd0a47e57a85b41b202f1d121c994f684303799bd1a6c0ef4f83f",
      "approval_sha256": "c00f9cb178dc06a2a2ffbe604fe137d6358fcaf38f2c676723318f8e2519be2b",
      "task_spec_sha256": "06d956b29e87029320b38f6f5b10fd13bd8c33cfe8ba6037027e6e07ef2252b6",
      "vspgeom_sha256": "6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05",
      "vspaero_sha256": "848af60fe321a5b4457687140d6bcb0b13856bd73e10ff230c3da2cf6bb6fb51",
      "vkey_sha256": "cbfee6264dcad6a833af184e09ea90863f6b26116b09836cd0409fadb89bc855",
      "case_inputs_sha256": "e36559e78ef02c1b935c92e9a04c12e52718711c689f97df15aab10164514b1c",
      "audit_sha256": null,
      "alpha_grid_deg": [
        6.3119305654,
        6.3419305654,
        6.3719305654,
        6.4019305654,
        6.4319305654,
        6.4619305654,
        6.4919305654,
        6.5219305654,
        6.5519305654,
        6.5819305654,
        6.6119305654,
        6.6419305654,
        6.6719305654,
        6.7019305654,
        6.7319305654,
        6.7619305654,
        6.7919305654
      ]
    },
    {
      "case_id": "g1-m180-d03-query",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "query",
      "design": "d03",
      "mach": 1.8,
      "plan_sha256": "c70df05b770ac912fb4a900f8cf1fde5ffb36e6ba1600041e204aa6f7665ed18",
      "approval_sha256": "dad6c65022c6103ff6b40a2f16822d566eb8c86643bbbd29bd0eac97ee66e1dc",
      "task_spec_sha256": "0d1e5ef191b28e1ed1b2eca6e0aeb8d37e671cff84210499de5105c8d65ce265",
      "vspgeom_sha256": "78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12",
      "vspaero_sha256": "e03abd6b3a1002427d8099ab71803d3211419cc5513fe054bc86bb85a079cc38",
      "vkey_sha256": "0e0351dd09a85c68c0e84d60b501a9f5917d17c833c5c27c742b4fd918c44bda",
      "case_inputs_sha256": "1ccb1d38c4855a3eb57a5d84f1983758afd33ba7ffc670751f13c30bcb8a7227",
      "audit_sha256": null,
      "alpha_grid_deg": [
        6.3791502271,
        6.4091502271,
        6.4391502271,
        6.4691502271,
        6.4991502271,
        6.5291502271,
        6.5591502271,
        6.5891502271,
        6.6191502271,
        6.6491502271,
        6.6791502271,
        6.7091502271,
        6.7391502271,
        6.7691502271,
        6.7991502271,
        6.8291502271,
        6.8591502271
      ]
    },
    {
      "case_id": "g1-m180-d04-query",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "query",
      "design": "d04",
      "mach": 1.8,
      "plan_sha256": "ff67356f70b2ca0821e6c2b13195dc2249574409912553f9291d6986967de589",
      "approval_sha256": "1102614c0ed53637ec126f1a7dce2c41b4635352f76be5e903ec4ba3794bf894",
      "task_spec_sha256": "2dcd6d3614474ac0a6ee162d6e1a9eeef789156ee4d7fbf85f7ee6eccaac03a7",
      "vspgeom_sha256": "2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2",
      "vspaero_sha256": "848af60fe321a5b4457687140d6bcb0b13856bd73e10ff230c3da2cf6bb6fb51",
      "vkey_sha256": "12bd302ce4838f9867e43738c32c4279c9fdd168ae49712ff3b8148c2f585f20",
      "case_inputs_sha256": "8504fafb993d72c6845ec5c2f287f2b9548d6fc640d86276d4a83b1608e27506",
      "audit_sha256": null,
      "alpha_grid_deg": [
        6.3119305654,
        6.3419305654,
        6.3719305654,
        6.4019305654,
        6.4319305654,
        6.4619305654,
        6.4919305654,
        6.5219305654,
        6.5519305654,
        6.5819305654,
        6.6119305654,
        6.6419305654,
        6.6719305654,
        6.7019305654,
        6.7319305654,
        6.7619305654,
        6.7919305654
      ]
    },
    {
      "case_id": "g1-m180-d05-query",
      "task_id": "DREAL003-G1-M180",
      "split": "val",
      "partition": "query",
      "design": "d05",
      "mach": 1.8,
      "plan_sha256": "6057afbb3b6fc2b06675b7a797e82af079abd7e92c28eab187b3f1396e0deb38",
      "approval_sha256": "6e0ab447f5a6fa737d3312446202f2d5133c1853ac105beed237b8aa1f2645d9",
      "task_spec_sha256": "55ffdb86411e9288a036e637638a43ef18acd9a2c4ff6aaa0c52436db821fa33",
      "vspgeom_sha256": "0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55",
      "vspaero_sha256": "848af60fe321a5b4457687140d6bcb0b13856bd73e10ff230c3da2cf6bb6fb51",
      "vkey_sha256": "7ff779b09a53bd7f281db936ae44264cacb8691cd40d633656e5bffa59e526ca",
      "case_inputs_sha256": "7a939f6a9e004d41bdd7f0f1c59cdf62019a0b523ebeb6d4727d1e6f12167be8",
      "audit_sha256": null,
      "alpha_grid_deg": [
        6.3119305654,
        6.3419305654,
        6.3719305654,
        6.4019305654,
        6.4319305654,
        6.4619305654,
        6.4919305654,
        6.5219305654,
        6.5519305654,
        6.5819305654,
        6.6119305654,
        6.6419305654,
        6.6719305654,
        6.7019305654,
        6.7319305654,
        6.7619305654,
        6.7919305654
      ]
    },
    {
      "case_id": "g1-m202-d00-support",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "support",
      "design": "d00",
      "mach": 2.02,
      "plan_sha256": "13e24b464ea773e542bd97e6f8827a881f48879d765636a68e20b81baadcb007",
      "approval_sha256": "d3fde9ccfbe7bc1340b79b449383bf3b4a3c514ee1d39c0780a62a94ad712dd6",
      "task_spec_sha256": "514d34438e7557160b0b04c271a1089bf1f04e65c9384c483bbcd68a6858bb17",
      "vspgeom_sha256": "f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34",
      "vspaero_sha256": "a59f6421979d4e25357450286b5cc127a3a2677bca5fc5b397e12c3f7157c8d8",
      "vkey_sha256": "eaf52b615b46fe89928279e857e93ef5e4e201aebc2c9cd4ad60dccd26e500d9",
      "case_inputs_sha256": "72e1bf44d2ca2f4ae9606b31650f4a878ea4b601f1a6c28ea8898da8a3b435f2",
      "audit_sha256": null,
      "alpha_grid_deg": [
        4.9413176428,
        4.9713176428,
        5.0013176428,
        5.0313176428,
        5.0613176428,
        5.0913176428,
        5.1213176428,
        5.1513176428,
        5.1813176428,
        5.2113176428,
        5.2413176428,
        5.2713176428,
        5.3013176428,
        5.3313176428,
        5.3613176428,
        5.3913176428,
        5.4213176428
      ]
    },
    {
      "case_id": "g1-m202-d01-support",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "support",
      "design": "d01",
      "mach": 2.02,
      "plan_sha256": "81f1b8a1cd6b53ff0dcacaf48acc928273d9125452c767d9eda20bc108ffac14",
      "approval_sha256": "ba40cc5fbc9c0637740fe746483e75fae22d83f377ab39de538eeaeb39b255ec",
      "task_spec_sha256": "8e16e1080f1f6c64a14ac1f2c80f4a65ceec9db03c4a99bee7b29dc725ba9da2",
      "vspgeom_sha256": "31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9",
      "vspaero_sha256": "b00dd5128528b56a35aaedf2abeb230f868ac53232e36ea9f58c4b2537b1ede7",
      "vkey_sha256": "7e48ac3cbd2d3c0f0b006ac5631c13efb921932b5236d209c843fe56f88f5b7b",
      "case_inputs_sha256": "e7b4a8b2d7c9316c24744694ba35301c51351779dbdd28eb369ea1b1c0e674d2",
      "audit_sha256": null,
      "alpha_grid_deg": [
        4.8889994884,
        4.9189994884,
        4.9489994884,
        4.9789994884,
        5.0089994884,
        5.0389994884,
        5.0689994884,
        5.0989994884,
        5.1289994884,
        5.1589994884,
        5.1889994884,
        5.2189994884,
        5.2489994884,
        5.2789994884,
        5.3089994884,
        5.3389994884,
        5.3689994884
      ]
    },
    {
      "case_id": "g1-m202-d02-support",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "support",
      "design": "d02",
      "mach": 2.02,
      "plan_sha256": "7f48950e99314b2f35c0cc2697889fee4b45b2b494778886906ee078c173b305",
      "approval_sha256": "be7d5cfe66251e5683d0d010b96ee8482121b3635fc8e2aa7570fa121d0e7c85",
      "task_spec_sha256": "236821601fe9ff96087134a3ee8c746c85ac6181a5bcb36b69b7579d7073d203",
      "vspgeom_sha256": "6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05",
      "vspaero_sha256": "a59f6421979d4e25357450286b5cc127a3a2677bca5fc5b397e12c3f7157c8d8",
      "vkey_sha256": "1bb432e37beabc6a76271e8d1ee7b88cf943b9a389647089becbab8e66e7bd69",
      "case_inputs_sha256": "b35207534dfc69f30063c0b865e2320be36a6d9f33137c2d41de1a49d19335d3",
      "audit_sha256": null,
      "alpha_grid_deg": [
        4.9413176428,
        4.9713176428,
        5.0013176428,
        5.0313176428,
        5.0613176428,
        5.0913176428,
        5.1213176428,
        5.1513176428,
        5.1813176428,
        5.2113176428,
        5.2413176428,
        5.2713176428,
        5.3013176428,
        5.3313176428,
        5.3613176428,
        5.3913176428,
        5.4213176428
      ]
    },
    {
      "case_id": "g1-m202-d03-query",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "query",
      "design": "d03",
      "mach": 2.02,
      "plan_sha256": "dbaee0d73847b2d6881d810804fa10dcc2409e9fd4f55127ec65ccda21794c4a",
      "approval_sha256": "02995acc005a2cd3cf0a57a6f41b97c1b48925892981ecbd547f178ac684f1a0",
      "task_spec_sha256": "f7898713d10ed15cfae4d473641d503ffac73f7c2d00ce7418d01643606684c7",
      "vspgeom_sha256": "78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12",
      "vspaero_sha256": "301d4be9727466edfa0a1bd864a3fd68a0d9291a8ee26bcafed37af4a448cc60",
      "vkey_sha256": "5b13b095ea659ef5fffdf8aa50600494c43eeb8048749b5725f4794408539ae7",
      "case_inputs_sha256": "b8ceda008330ad4642e9767998dbe71f6ab492ab8747bb3a25d0d1ef2943eb6c",
      "audit_sha256": null,
      "alpha_grid_deg": [
        4.9946927295,
        5.0246927295,
        5.0546927295,
        5.0846927295,
        5.1146927295,
        5.1446927295,
        5.1746927295,
        5.2046927295,
        5.2346927295,
        5.2646927295,
        5.2946927295,
        5.3246927295,
        5.3546927295,
        5.3846927295,
        5.4146927295,
        5.4446927295,
        5.4746927295
      ]
    },
    {
      "case_id": "g1-m202-d04-query",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "query",
      "design": "d04",
      "mach": 2.02,
      "plan_sha256": "21e8154f7ed4e712b0c7c176d68499be1cd16a821e4f9ed4e347504fd11dffcf",
      "approval_sha256": "fc6cba061fcf5c3f7b808c2f7101e83dc3af6990d4813ca95e691203dfb29231",
      "task_spec_sha256": "02b12f2fda633c9a7a32332ec24045b4feeb2038aaecab070fb216d456cbe0e4",
      "vspgeom_sha256": "2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2",
      "vspaero_sha256": "a59f6421979d4e25357450286b5cc127a3a2677bca5fc5b397e12c3f7157c8d8",
      "vkey_sha256": "5e2742a87c0080db5a488f19b693bedc99605fa3616ebcf179a1644a68015901",
      "case_inputs_sha256": "af188935b866b8b574150af5804b15afb38d4bb1a30e4a3ae8c502ca04fd56bf",
      "audit_sha256": null,
      "alpha_grid_deg": [
        4.9413176428,
        4.9713176428,
        5.0013176428,
        5.0313176428,
        5.0613176428,
        5.0913176428,
        5.1213176428,
        5.1513176428,
        5.1813176428,
        5.2113176428,
        5.2413176428,
        5.2713176428,
        5.3013176428,
        5.3313176428,
        5.3613176428,
        5.3913176428,
        5.4213176428
      ]
    },
    {
      "case_id": "g1-m202-d05-query",
      "task_id": "DREAL003-G1-M202",
      "split": "train",
      "partition": "query",
      "design": "d05",
      "mach": 2.02,
      "plan_sha256": "1663a475fe032408c0e242f52079f6a09c831972d3fc6aeccd2125d971b2f31d",
      "approval_sha256": "7b6e9f3cd09a1ee2ba07f1b7bcd52b8fa5d3aa006353405a080bee64b934e092",
      "task_spec_sha256": "95b5de4d43894ed7872abcd38be0ae19b7f17c6b345098370255fe69b856579c",
      "vspgeom_sha256": "0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55",
      "vspaero_sha256": "a59f6421979d4e25357450286b5cc127a3a2677bca5fc5b397e12c3f7157c8d8",
      "vkey_sha256": "c3098c3a2d436dd964f496325d02fbbd552a8c52397493be24127647af1fa7f9",
      "case_inputs_sha256": "8e769a89451c1292f4471542d44992d031e6d0f66df3122f8f0c359b1c34f812",
      "audit_sha256": null,
      "alpha_grid_deg": [
        4.9413176428,
        4.9713176428,
        5.0013176428,
        5.0313176428,
        5.0613176428,
        5.0913176428,
        5.1213176428,
        5.1513176428,
        5.1813176428,
        5.2113176428,
        5.2413176428,
        5.2713176428,
        5.3013176428,
        5.3313176428,
        5.3613176428,
        5.3913176428,
        5.4213176428
      ]
    },
    {
      "case_id": "g1-m240-d00-support",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "support",
      "design": "d00",
      "mach": 2.4,
      "plan_sha256": "6cc64caeeb8be6251f36cbbcb2a8a0178c4c40fff8a27bec7ce8f8f7e200e784",
      "approval_sha256": "129ca3465b026f18c166c2da9f378e75de6ffe3ab79f8f0e5779b02661d34976",
      "task_spec_sha256": "3d2383a844019ba048f3160371a0f20a944a99fa64ae64096e9affd13beefbf3",
      "vspgeom_sha256": "f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34",
      "vspaero_sha256": "688d2cd5cf24ca31b420b90e69ccacbb19e05f1fa68f016aea42cf307cc4c424",
      "vkey_sha256": "18fa9cd90d4cf1fe62844eb198450664f4a04a681d5c743c5fb159c561639c82",
      "case_inputs_sha256": "fd0dbd5e4ecf289ea31bdd26f09be9c8640ed39ae3855c9f2df4f1611f667a4c",
      "audit_sha256": null,
      "alpha_grid_deg": [
        3.400478966,
        3.430478966,
        3.460478966,
        3.490478966,
        3.520478966,
        3.550478966,
        3.580478966,
        3.610478966,
        3.640478966,
        3.670478966,
        3.700478966,
        3.730478966,
        3.760478966,
        3.790478966,
        3.820478966,
        3.850478966,
        3.880478966
      ]
    },
    {
      "case_id": "g1-m240-d01-support",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "support",
      "design": "d01",
      "mach": 2.4,
      "plan_sha256": "09f46ed178a4fcf1e52a51cb2907c7596fe2d511654f64e4479be2032735c96d",
      "approval_sha256": "24ffcace5bdba942991f73085ceedd51790c22dbf1a34bc2bc91b779ef645920",
      "task_spec_sha256": "dc71bf40de631e21faa57002cf0378c841bc07fc6bd8220c2da3055df1360c3d",
      "vspgeom_sha256": "31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9",
      "vspaero_sha256": "407e5ee6d1a014169d4104aa30b2349e8132049a85c88dec47ec9300f1fbb980",
      "vkey_sha256": "1090d7f9377055c5080b205e2cfb1506d24a2c4e28797882e3d286445ac83488",
      "case_inputs_sha256": "dd7b26b6be50a8a56fea337c89214afd49d799937e30a67a72cbf10665d81f87",
      "audit_sha256": null,
      "alpha_grid_deg": [
        3.3634166401,
        3.3934166401,
        3.4234166401,
        3.4534166401,
        3.4834166401,
        3.5134166401,
        3.5434166401,
        3.5734166401,
        3.6034166401,
        3.6334166401,
        3.6634166401,
        3.6934166401,
        3.7234166401,
        3.7534166401,
        3.7834166401,
        3.8134166401,
        3.8434166401
      ]
    },
    {
      "case_id": "g1-m240-d02-support",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "support",
      "design": "d02",
      "mach": 2.4,
      "plan_sha256": "255411aa0b5f475c6caa107046c23722c2810cd7dd3dfec68d10807196f4f6ca",
      "approval_sha256": "b644c59c65bdc7b7814d92849dbc028f9b0e4d9deab1bedb9526744aadbd8337",
      "task_spec_sha256": "7ed343ee2af5390aba118f4a599b6c2253c8a8c20b776805de911ae9e413bacd",
      "vspgeom_sha256": "6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05",
      "vspaero_sha256": "688d2cd5cf24ca31b420b90e69ccacbb19e05f1fa68f016aea42cf307cc4c424",
      "vkey_sha256": "6efbf18b830ff55e918731fcd4b99c35dd530cac2f2730d6e336e12afe065cfc",
      "case_inputs_sha256": "1d54d4818d73f0348d5082afda104e7a96da1e9177bc92b009dd9ac434f744b1",
      "audit_sha256": null,
      "alpha_grid_deg": [
        3.400478966,
        3.430478966,
        3.460478966,
        3.490478966,
        3.520478966,
        3.550478966,
        3.580478966,
        3.610478966,
        3.640478966,
        3.670478966,
        3.700478966,
        3.730478966,
        3.760478966,
        3.790478966,
        3.820478966,
        3.850478966,
        3.880478966
      ]
    },
    {
      "case_id": "g1-m240-d03-query",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "query",
      "design": "d03",
      "mach": 2.4,
      "plan_sha256": "cd088a90c349abac2d3b654b3057f18ff17dc246a700053ee3d47dbcec4bf8b2",
      "approval_sha256": "32037dcec96a76050d5d7ed94cd23f302bee6e81534aeb5ac8d4b312c794c651",
      "task_spec_sha256": "f499fd9e4efa284d5f228f64155a1e98ed41d3880ff3171f323952db67d335dc",
      "vspgeom_sha256": "78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12",
      "vspaero_sha256": "e046b98bca10221aa62b399f49d9699731f2bff305735ff8e2fe8d1abb12423b",
      "vkey_sha256": "ca1b3bb68e9112ff006915cfca89335008155201a404b38e7f26b72266d4a99d",
      "case_inputs_sha256": "c93f0f51b3df51ff9d02146f836604d458f6abdc9325a7c3f58c0876674df91f",
      "audit_sha256": null,
      "alpha_grid_deg": [
        3.4382900257,
        3.4682900257,
        3.4982900257,
        3.5282900257,
        3.5582900257,
        3.5882900257,
        3.6182900257,
        3.6482900257,
        3.6782900257,
        3.7082900257,
        3.7382900257,
        3.7682900257,
        3.7982900257,
        3.8282900257,
        3.8582900257,
        3.8882900257,
        3.9182900257
      ]
    },
    {
      "case_id": "g1-m240-d04-query",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "query",
      "design": "d04",
      "mach": 2.4,
      "plan_sha256": "86eddc06685ff57b3e5575181109b3482cf89d6a4c3c299607aeae537452f9b0",
      "approval_sha256": "c7b2d1e72a4211cf34ac9ebe45a4bebb068dbce5454140bc6a28c8b112b4ab50",
      "task_spec_sha256": "c7dbad201fc09c1230ca62762d6fb116c718fc446a589c5a932412642e67bd7d",
      "vspgeom_sha256": "2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2",
      "vspaero_sha256": "688d2cd5cf24ca31b420b90e69ccacbb19e05f1fa68f016aea42cf307cc4c424",
      "vkey_sha256": "f9c601317167a42aed2dcb652a8281721592d52628fc1dd5b772481349e3df5d",
      "case_inputs_sha256": "4800e1d5d83e8c2324ddcacd5d095a69b9c7245a4fd085c7fe0b298a238a602a",
      "audit_sha256": null,
      "alpha_grid_deg": [
        3.400478966,
        3.430478966,
        3.460478966,
        3.490478966,
        3.520478966,
        3.550478966,
        3.580478966,
        3.610478966,
        3.640478966,
        3.670478966,
        3.700478966,
        3.730478966,
        3.760478966,
        3.790478966,
        3.820478966,
        3.850478966,
        3.880478966
      ]
    },
    {
      "case_id": "g1-m240-d05-query",
      "task_id": "DREAL003-G1-M240",
      "split": "test",
      "partition": "query",
      "design": "d05",
      "mach": 2.4,
      "plan_sha256": "f1b3a45b421c62b48e0981b56678d3350e59571500150f94b15a02363df890b5",
      "approval_sha256": "fc3e744d899b5545a93662ce72c24f3daf426432a0df36cd042dd0b06b882926",
      "task_spec_sha256": "961444c145b0847a5eb466fa1feb5df7e8360c82330b967bab3eab4afd987320",
      "vspgeom_sha256": "0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55",
      "vspaero_sha256": "688d2cd5cf24ca31b420b90e69ccacbb19e05f1fa68f016aea42cf307cc4c424",
      "vkey_sha256": "b31a3bb1f56ee3a97b517621b7042fac7c3e86ff84d8c6a9be8bbeaf3fade52c",
      "case_inputs_sha256": "bbe2bc778d32bbc2f9318ccc9e3cc0f0a46cfaf1d191316f01ebc012dbfdf02e",
      "audit_sha256": null,
      "alpha_grid_deg": [
        3.400478966,
        3.430478966,
        3.460478966,
        3.490478966,
        3.520478966,
        3.550478966,
        3.580478966,
        3.610478966,
        3.640478966,
        3.670478966,
        3.700478966,
        3.730478966,
        3.760478966,
        3.790478966,
        3.820478966,
        3.850478966,
        3.880478966
      ]
    }
  ],
  "preregistration_sha256": "08a6d1b24f48ce3c54609f0d90381a683c593bab6c73d819b547e02c21d3f66e"
}

```

## 6. 零物理证据
- case 目录数 24；case_result.json=0；solver_attempts.jsonl=0；.polar=0；总文件 240。
- 无 vspaero.exe 进程启动记录；本轮 A5 前 physical_solver_starts_actual=0。

## 7. 执行与会计控制
- 三个 mini-batch，每批 8 starts；每批完成后必须把原始文件/CSV/PNG/账本上传 GitHub，并从远端回读 SHA256SUMS 成功后才可下一批。
- 任一 start 被会计/窗口/计划校验拒绝；任一超时或缺少进程结果；连续两个非 SOLVED；账本不守恒；任一批上传/回读不一致 → 立即停止，剩余预算作废。
- 失败 case objective=null，不重跑；只有 polar 中存在满足 1e-3 升力容差的实际行才可生成 admission certificate。
- 新增物理只允许 24 starts；不得用 G0 旧标签替代 G1 标签；不得把 mock/replay 当真实。

## 8. 请 A5 判断
1. 这份 G1 授权、代码 SHA、24 case 计划 SHA 清单、预算/停机/上传控制是否足以放行第一批真实 starts？
2. 有无必须先修的 critical/major 问题？
3. 若放行，请明确“只放行 G1 ≤24 starts，不构成 R2/G2/G3 或人类签字”。

只返回 JSON：
{
 "reviewer":"deepseek-flash",
 "review_type":"independent_single_shot_dossier_review",
 "reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ",
 "dossier_sha256":"<dossier sha>",
 "verdict":"G1_APPROVE"|"G1_CHANGES_REQUIRED"|"G1_REJECT",
 "gate_verdicts":{"G1_PREREGISTRATION":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL",
   "G1_CODE_STATE":"...","G1_CASE_PLAN":"...","G1_CONTROLS":"...","G1_ZERO_PHYSICAL":"..."},
 "evidence_checked":["..."],
 "findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],
 "limitations":["..."],
 "scope":"what this review covers and does not cover",
 "signature":"deepseek-flash independent A5 review; not a human signature"
}
At most 6 findings, each <=240 chars. No Markdown.
