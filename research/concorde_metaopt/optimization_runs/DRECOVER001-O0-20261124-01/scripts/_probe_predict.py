"""One-off probe: replay the paid B01 baseline coarse rows through the fixed bracket path."""
import json, sys

sys.path.insert(0, "D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01/scripts")
sys.path.insert(0, "D:/RCAIDE/.worktrees/dreal005-20261124")
import o0_eval as ev  # noqa: E402
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402

paid = ev.RUN / "cases" / "B01" / "o0-d00-coarse" / "case_result.json"
res = {"case_result": str(paid)}
rows = ev.bracket_rows(res)
cl_t = ev.cl_target_for(list(o0.BASELINE_X12))
pred = o0.predict_alpha(rows, cl_t)
out = {"paid_case_result": str(paid), "paid_case_result_exists": paid.is_file(),
       "n_rows": len(rows), "rows": rows, "cl_target": cl_t,
       "predict": {k: pred.get(k) for k in ("ok", "predicted_alpha_deg", "method", "reason")}}
if pred.get("ok"):
    center = float(pred["predicted_alpha_deg"])
    refine = o0.refine_alphas(center)
    out["refine"] = {"n": len(refine), "center": center,
                     "min": min(refine), "max": max(refine)}
    out["fit"] = pred.get("fit")
print(json.dumps(out, indent=1, ensure_ascii=False))
