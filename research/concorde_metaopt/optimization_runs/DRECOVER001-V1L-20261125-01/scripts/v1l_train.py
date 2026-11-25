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