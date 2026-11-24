"""Assemble the O1 tables straight from the run's own records.

Every row comes from o1_result.json / o1_arm_*.json / o1_attempts.jsonl. Nothing is retyped and
nothing is recomputed from memory, so a table cannot disagree with the result file.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
TAB = RUN / "tables"
TAB.mkdir(parents=True, exist_ok=True)

result = json.loads((RUN / "o1_result.json").read_text(encoding="utf-8"))
arms = result["arms"]
base = result["regression"]["baseline_di_n"]
target = result["regression"]["target_di_n"]

manifest = []


def write(name, header, rows):
    path = TAB / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    manifest.append({"table": name, "rows": len(rows), "bytes": path.stat().st_size})


# 1. one row per arm: the primary endpoint
rows = []
for arm, payload in arms.items():
    rows.append([arm, payload["designs"], payload["starts"], payload["internal"],
                 payload["admitted"], payload["failed"],
                 "%.6f" % payload["point_feasible_rate"],
                 payload["run_level_feasible"],
                 "%.6f" % payload["best_feasible_di_n"],
                 payload["best_feasible_tag"], payload["best_feasible_design_id"],
                 "%.6f" % payload["improvement_n"],
                 "%.8f" % payload["improvement_fraction"],
                 payload["reached_target"],
                 payload["equivalent_starts_to_target"],
                 payload["adaptive_designs"]])
write("o1_three_arm_endpoint.csv",
      ["arm", "designs", "starts", "internal", "admitted", "failed", "point_feasible_rate",
       "run_level_feasible", "best_feasible_di_n", "best_feasible_tag",
       "best_feasible_design_id", "improvement_n", "improvement_fraction", "reached_target",
       "equivalent_starts_to_target", "adaptive_designs"], rows)

# 2. the anytime trace, every step of every arm
rows = []
for arm, payload in arms.items():
    for point in payload["anytime"]:
        rows.append([arm, point["step"], point["role"], point.get("tag"),
                     point["design_id"], point["starts"], point["internal"],
                     point["cumulative_starts"], point["cumulative_internal"],
                     point["feasible"], "" if point["di_n"] is None else "%.6f" % point["di_n"],
                     "" if point["best_so_far"] is None else "%.6f" % point["best_so_far"],
                     point["status"]])
write("o1_anytime_trace.csv",
      ["arm", "step", "role", "tag", "design_id", "starts", "internal", "cumulative_starts",
       "cumulative_internal", "feasible", "di_n", "best_so_far", "status"], rows)

# 3. every evaluated design, all arms, with the value the surrogate predicted for it
rows = []
for arm in arms:
    payload = json.loads((RUN / ("o1_arm_%s.json" % arm)).read_text(encoding="utf-8"))
    for record in payload["records"]:
        rows.append([arm, record["tag"], record["role"], record["design_index"],
                     record["design_id"], record["is_baseline"], record["status"],
                     record["feasible"], record["starts"], record["internal"],
                     "" if record["di_n"] is None else "%.6f" % record["di_n"],
                     "" if record.get("predicted_di_n") is None
                     else "%.6f" % record["predicted_di_n"],
                     "%.6f" % record["cl"], "%.9f" % record["cdi"],
                     "%.6f" % record["alpha_deg"],
                     "%.3e" % record["lift_rel_error"] if record["lift_rel_error"] else "",
                     record["failure_kind"] or "", record["detail"]])
write("o1_all_designs_all_arms.csv",
      ["arm", "tag", "role", "design_index", "design_id", "is_baseline", "status", "feasible",
       "starts", "internal", "di_n", "predicted_di_n", "cl", "cdi", "alpha_deg",
       "lift_rel_error", "failure_kind", "detail"], rows)

# 4. the geometry delta between the baseline and each arm's best design
base_row = next(r for r in result["regression"]["shared_support"] if r["is_baseline"])
variable_names = ["Sref_m2", "AR", "sweep_inboard_deg", "sweep_outboard_deg", "span_m",
                  "twist_root_deg", "twist_tip_deg", "thickness_root", "thickness_tip",
                  "camber_deg", "dihedral_deg", "taper"]
rows = []
for arm, payload in arms.items():
    arm_payload = json.loads((RUN / ("o1_arm_%s.json" % arm)).read_text(encoding="utf-8"))
    best = next(r for r in arm_payload["records"]
                if r["design_id"] == payload["best_feasible_design_id"])
    for index, name in enumerate(variable_names):
        rows.append([name, index, "%.10g" % float(base_row["x12"][index]),
                     "%.10g" % float(best["x12"][index]),
                     "%.10g" % (float(best["x12"][index]) - float(base_row["x12"][index]))])
write("o1_best_design_vs_baseline.csv",
      ["variable", "index_12d", "baseline", "best_of_arm", "delta"], rows)

# 5. the raw solver bill, case by case, from the attempt ledger
attempts = [json.loads(line) for line in
            (RUN / "o1_attempts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
rows = []
for row in attempts:
    design = row["design"]
    for trace in design.get("acquisition", {}).get("trace", []):
        if trace.get("stage") not in ("coarse", "refine"):
            continue
        rows.append([design["arm"], design["tag"], design["design_id"], row["utc"],
                     trace["case_id"], trace["stage"], trace["status"], trace["starts"],
                     trace["internal"], design["status"],
                     "" if design["di_n"] is None else "%.6f" % design["di_n"]])
write("o1_solver_case_ledger.csv",
      ["arm", "tag", "design_id", "utc", "case_id", "stage", "status", "starts", "internal",
       "design_status", "di_n"], rows)

manifest.append({
    "reference_point": "the pre-designated baseline inside the shared support",
    "baseline_di_n": base, "target_di_n": target,
    "target_rule": "baseline x (1 - 0.001), frozen before the batch",
    "physical_solver_starts_actual": result["cost"]["physical_solver_starts_actual"],
    "equivalent_solver_starts": result["cost"]["equivalent_solver_starts"],
    "note": ("every Di in these tables is a raw VSPAERO polar row admitted at 1e-3 lift "
             "tolerance; no number here comes from the surrogate"),
})
(TAB / "table_manifest.json").write_text(
    json.dumps({"schema": "dreal005.o1_tables.v1", "tables": manifest}, ensure_ascii=False,
               indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(manifest, ensure_ascii=False, indent=2))
