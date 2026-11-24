import sys, time, json
sys.path.insert(0, r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01/scripts")
import a0_data
from research.concorde_metaopt.dreal001.meta import real_a0_ablation as a0
built = a0_data.build_family_and_dataset()
ds = built["dataset"]
for k in (0, 1, 3):
    cfg = a0.AblationConfig(seed=7, max_steps=20)
    t = time.perf_counter()
    res = a0.run_arm(ds, config=cfg, k=k, eval_splits=("val", "test"))
    print("k", k, "wall", round(time.perf_counter()-t, 2))
    for arm, rows in res["scores"].items():
        mae = sum(r["mae_n"] for r in rows) / len(rows)
        print("  ", arm, "mean_mae", round(mae, 1), "n_tasks", len(rows),
              "best_step", res["checkpoint_selection"][arm]["best_step"],
              "inner_upd", res["cost"][arm]["inner_gradient_updates"])
print(json.dumps(res["scores"]["FOMAML_12D"][0], indent=1)[:600])
