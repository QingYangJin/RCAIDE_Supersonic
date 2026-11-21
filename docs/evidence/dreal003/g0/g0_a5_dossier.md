# G0 独立审查材料（A5 复审版）

- 审查对象：Issue #13 G0 的 A1 代码修复、A3 真实准入内审、旧 24 次真实原件完整上传与远端回读。
- 分支：research/dreal003-expanded-aero-meta-20261120
- 最终数据 commit：bd8fa4a1f99627e184ea09e233955fa629dae727
- 最终数据 tree：953025e507a89c8924485b214bfdd3d46c0f2980
- parent：e71e25e9045a7be98e54aed0feac86e91f9a5374
- 本轮新增真实求解器启动：0。g0 上传的是历史批次原件，不是新物理。
- 上一轮 A5（deepseek-flash，单发只读）结论 G0_CHANGES_REQUIRED；本文件逐条回应 7 条 finding。

## 1. 对上一轮 findings 的处置

| # | 上一轮 finding | 处置 |
|---|---|---|
| 1 | 1,274 vs 1,344 文件数不一致 | 已上传原始 root 下全部 1,345 个文件，并生成 metadata/upload_file_mapping.json，逐文件 original_path→uploaded_path→bytes→SHA256→sha256_match；all_sha256_match=true。最终上传 1,384 个文件（含 curated 派生副本、README、SHA256SUMS）。 |
| 2 | 645 未对账 | 新增 645 分解：pilot 23 + 13 个完成 matrix case ×15 + 7 个 B01R repair case ×61 = 645；中断 m240-d01 内部 case 数未知且不计入。 |
| 3 | 远端回读缺 URL 与 7 文件哈希 | 第 5 节列出 7 个 commit-pinned URL、字节数与 SHA256；最终 commit 另抽查成功 case 证书逐字节一致。 |
| 4 | A1 缺 diff 与原始测试日志 | docs/evidence/dreal003/g0/a1_fix.diff（提交 4b6bff5→1f0bdd5 的 solver_runner.py 与测试 diff）与 g0_preflight.log（253 tests 原始 JSON）随证据提交；diff 全文见第 3 节。 |
| 5 | A3 只是 Lead 自审，不能当独立 A5 证据 | 已降级：A3 仅是输入材料，G0_CODE_PASS 必须由 A5 自己判断；A5 是独立 deepseek-flash 单发只读审查，非人类签名。 |
| 6 | 10 证书 vs 9 标签重复身份未解释 | baseline-admit-01 与 baseline-refine-01 是同一 task/design 的两次测量，两张证书都有效；admitted_labels.csv 按唯一 (task_id, design_sha256) 去重，保留 baseline-admit-01，refine 不重复计数。 |
| 7 | 每 case Sref/lift 未列全 | docs/evidence/dreal003/g0/a1_per_case_flow_table.csv 列出 24 case 的 Mach/q/Sref/lift/rho/Vinf/匹配状态。 |

## 2. 文件数/字节完整对账

原始 root：D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/

- 原始文件总数：1,345；总字节：209,935,206（映射文件逐项求和）。
- 其中 cases/ 下 24 个 case：1,249 个文件。
- 其中非 case 文件（authorization、batch_accounting、real_dataset_manifest、r2_gate_record、null_labels、pilot、scripts、flow_default_equivalence、preflight 快照、issue 文本等）：96 个文件。
- 1,249 + 96 = 1,345，全部上传：
  - cases/<rel> → raw_cases/<rel>（1,249 个）
  - 其他 <rel> → source_top_level/<rel>（96 个）
- 另加 curated 派生副本 36 个（inputs、tables、metadata、training、audits、figures）、metadata/upload_file_mapping.json、README.md、SHA256SUMS.txt。
- 最终上传：1,384 个文件，211,456,790 字节；其中原始 1,345 个、curated 36 个、mapping 1 个、README 1 个、SHA256SUMS 1 个。
- metadata/upload_file_mapping.json：original_file_count=1345，all_sha256_match=true。
- 映射文件 SHA256：fd93d194a2104b45f057dc249a8531774bf039e3b550d817dba9defa6e68f707
- 映射文件地址：https://github.com/QingYangJin/RCAIDE_Supersonic/blob/e71e25e9045a7be98e54aed0feac86e91f9a5374/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/metadata/upload_file_mapping.json

### 2.1 1,274 / 1,287 / 1,344 / 1,345 的差异来源

| 计数 | 含义 | 差异 |
|---|---|---|
| 1,274 | commit 1f0bdd5 首次上传的文件数 | .gitignore 的 *.log 规则漏掉 58 个 *.log 与 13 个顶层 *.build.log |
| 1,287 | commit 28f4c5f 补 13 个 build.log 后 | +13 |
| 1,344 | 早期 g0_survival_inventory.json 的 file_count | 清单写入 run root 之前统计，未包含它自己 |
| 1,345 | 当前原始文件数 | + g0_survival_inventory.json（8,618 字节） |

- 209,926,588 是清单统计时的字节数；加入清单自身的 8,618 字节后为 209,935,206，与 upload_file_mapping.json 的 1,345 项逐项 bytes 求和一致。
- 1,345 originals + 36 curated + 1 mapping + README + SHA256SUMS = 1,384 uploaded files。

## 3. A1 代码 diff（完整）

代码文件：research/concorde_metaopt/dreal001/geometry/solver_runner.py
SHA256：cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3
测试文件：research/concorde_metaopt/tests/test_recovery_solver_runner.py
SHA256：7f29d21cc45cf7deb0469f6504145bb8065cc0d6f22eb59a4e934207a8481da1
diff 文件：docs/evidence/dreal003/g0/a1_fix.diff

```diff
diff --git a/research/concorde_metaopt/dreal001/geometry/solver_runner.py b/research/concorde_metaopt/dreal001/geometry/solver_runner.py
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

## 4. 253 项测试与 preflight 原始记录

- 原始日志：docs/evidence/dreal003/g0/g0_preflight.log
- run_id：DRECOVER001-SOFTWARE-20261120T121100Z
- tests_run：253；failures：0；errors：0；skipped：0；software_tests_status：PASS
- physical_solver_starts_actual_this_recovery：0
- 日志内记录 solver_runner.py 与 test_recovery_solver_runner.py 的 SHA256，与第 3 节一致。
- verify_a1_case_flow.py：24 cases，23 有 evaluation；6 条由 CL_TARGET_OUTSIDE_POLAR 变为 LIFT_MATCHED_BY_INTERPOLATION；12 条仍 outside；新增物理 0。结果文件 a1_per_case_flow_verification.json。
- 每 case 表：a1_per_case_flow_table.csv。

## 5. 远端回读：7 个文件、URL 与哈希

所有 URL 固定在 commit bd8fa4a1f99627e184ea09e233955fa629dae727（全量克隆已逐字节验证 1,345/1,345）。前缀：
https://github.com/QingYangJin/RCAIDE_Supersonic/blob/bd8fa4a1f99627e184ea09e233955fa629dae727/research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/

| 文件 | 字节 | SHA256 |
|---|---:|---|
| raw_cases/m160-d00-support-r1/task_spec.json | 1,742 | 58c46a28d0e1ddb6bb266602657811581cc779368f3d2a5888874f7406a63e8e |
| raw_cases/m160-d00-support-r1/case_inputs.json | 17,564 | 492eaacf0adc175092ca31440323f1e020098fa5a4f696875f7840979a620343 |
| raw_cases/m160-d00-support-r1/case_result.json | 228,876 | f887b24352516dc528069c93644cb601b1b8646beb0e1fbf7d3852132d2f7112 |
| raw_cases/m160-d00-support-r1/admission_certificate.json | 1,024 | 08cc414abc81f591390454bca51c9eda753049678d370d290a64b1f3c94ee1b6 |
| raw_cases/m160-d00-support-r1/m160_d00_support_r1.polar | 52,105 | 0f32d5f12ed2d87a0b63a616530d3f4757ffa86737561e16b31b3756ff9f6d93 |
| raw_cases/m240-d01-support/task_spec.json | 1,340 | af3c41c55fb25dda8c8c984f1015553b82f5de6640c1e7c514ab7f95dc906908 |
| raw_cases/m240-d01-support/m240_d01_support.vspaero | 1,252 | b101fb22f5b8e9511f4de1e3e3fa1fa6453c2b187f53a39728630dd88f40c93e |

- 1,345/1,345 与克隆对象逐字节一致，mismatch=[]（见 5.1）。
- 失败 case m240-d01-support 的 case_result.json 与 admission_certificate.json 在远端均 404；本地 case 目录仍有 31 个原始文件。
- 最终 commit bd8fa4a 的全量克隆已覆盖全部 1,345 个原件，不再依赖 7 文件抽样。
- 远端 tree 复核：commit bd8fa4a，tree 953025e…，git ls-tree 统计 1,384 文件 / 211,456,790 字节，与本地工作树一致。

## 5.1 全量远端复核（A5 上一轮 major 的直接回应）

- 方法：全新浅克隆远端分支 research/dreal003-expanded-aero-meta-20261120，固定到 commit bd8fa4a1f99627e184ea09e233955fa629dae727；从克隆对象库逐文件读取 blob，与 metadata/upload_file_mapping.json 的 1,345 项逐项比较字节数和 SHA256。
- 远端 ref SHA：bd8fa4a1f99627e184ea09e233955fa629dae727；commit_matches=true；remote_ref_matches=true。
- 原始文件：1,345 / 1,345 通过；bad=0；字节合计 209,935,206。
- 上传树文件：1,384；mapping 自身 SHA256：fd93d194a2104b45f057dc249a8531774bf039e3b550d817dba9defa6e68f707。
- 审计文件：docs/evidence/dreal003/g0/g0_full_remote_retrieval.json，SHA256 4c5c420ac9e23c70b732d75806c13e35ba4827367987662516f834e043198610。
- 本轮曾发现 3 个 __pycache__/*.pyc 被 .gitignore 排除而缺失，已在该 commit 中补齐并重新全量验证；这是 e71e25e 之后唯一的 payload 变化。
- 证据文件 SHA256：g0_preflight.log f31701000ba7ef0443f1e3866fbc0be5aa0fd22231f905540da722815b9252e7；a1_fix.diff 9479b2484139aa6ea3cdb21635356adcd1a9a93a9923f552bfe1dca1e36c1562。

## 6. 24 / 645 / 9 / null 账本对账

| 项目 | 数量 | 来源/查询 |
|---|---:|---|
| 真实 solver starts | 24 | batch_accounting.json physical_solver_starts_actual；cases/ 下 24 个目录 |
| 完成 | 23 | case_result.json 存在数 |
| 中断/超时 | 1 | m240-d01-support；无 case_result、无证书 |
| retries | 0 | batch_accounting.json retries_actual |
| internal solver cases | 645 | pilot 23 + 13 个完成 matrix case ×15 + 7 个 B01R repair case ×61 = 23+195+427；中断 case 内部数未知且不计 |
| 证书 | 10 | cases/*/admission_certificate.json |
| 去重标签 | 9 | admitted_labels.csv 行数；唯一 (task_id, design_sha256) |
| null/failed | 14 | failed_or_null.csv 行数 |
| 重复证书 | 2→1 | baseline-admit-01 与 baseline-refine-01 同 task/design；CSV 保留 admit，refine 不重复计数 |

样例查询：

```
Get-ChildItem D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases -Directory | Measure-Object
Get-Content .../cases/*/case_result.json
Import-Csv .../tables/admitted_labels.csv
Import-Csv .../tables/failed_or_null.csv
```

## 7. A3 输入（不是独立结论）

- admitted_labels.csv 9 行与 10 张证书逐字段一致；证书 di_n=q*sref*cdi（相对误差 1e-9）。
- 守卫测试：手写 AdmissionCertificate 被拒；无证书 MetaDataset 抛 REAL_ADMISSION_NOT_IMPLEMENTED；support/query 同设计泄漏被拒；failed observation 带 cl 被拒；RawFile ../escape 被拒。
- 源码 SHA256：real_admission.py 4322554e…；real_training.py 608f9b08…；meta_dataset.py 48e97dde…；task_spec.py 5413a1e8…；对应测试 test_recovery_real_admission.py 0b5f12b5…、test_recovery_real_training.py a8e70b3d…、test_recovery_meta_contracts.py d5028d57…。
- A3 自审 verdict=A3_INTERNAL_AUDIT_PASS，仅作为输入；G0_CODE_PASS 由 A5 独立判断。

## 8. 旧标签偏移披露

m160 证书 di_n=175533.59122875682（alpha=7.47）。A1 精确升力插值：alpha=7.472104416484619，di=175631.11677151572，相对差 5.56e-4。旧标签 pre-A1、未回写、未重标；两值都满足 di=q*Sref*CDi。

## 9. 不声称事项

- 新增真实物理 0；上传是历史原件。
- G1/G2/G3 未授权；NO_PHYSICAL_GO。
- 同机保存，不是异机故障域；Owner 已豁免。
- A5 是 deepseek-flash 独立单发只读审查，不是人类签名。

## 10. 请给出复审 JSON

{
  "reviewer": "deepseek-flash",
  "review_type": "independent_subagent_single_shot_read_only_dossier_reexamination",
  "reviewed_utc": "...",
  "prior_verdict": "G0_CHANGES_REQUIRED",
  "verdict": "G0_APPROVE" | "G0_CHANGES_REQUIRED" | "G0_REJECT",
  "gate_verdicts": {
    "G0_CODE_PASS": "PASS" | "PASS_WITH_DISCLOSURE" | "FAIL" | "UNVERIFIED",
    "G0_REMOTE_RAW_RETRIEVAL_PASS": "PASS" | "PASS_WITH_DISCLOSURE" | "FAIL" | "UNVERIFIED"
  },
  "finding_disposition": [{"finding": "...", "status": "ADDRESSED"|"PARTIAL"|"NOT_ADDRESSED", "evidence": "..."}],
  "findings": [{"severity": "major"|"minor", "claim": "...", "required_action": "..."}],
  "disclosures_required": ["..."],
  "residual_risks": ["..."],
  "human_signature": false
}

只输出 JSON。无法独立核验的项标 UNVERIFIED，不假设为真。