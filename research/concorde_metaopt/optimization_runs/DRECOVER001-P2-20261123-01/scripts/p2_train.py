"""P2 four-arm real training driver (Issue #14 P2 directive).

Composes the A5-reviewed primitives in research.concorde_metaopt.dreal001.meta.real_p2_arms
(run_arms body) and saves every model checkpoint, normalizer, and per-query prediction.
No physical solver is invoked here. CPU float64 is the reproducible reference.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(RUN / "scripts"))

from research.concorde_metaopt.dreal001.meta import real_p2_arms as arms_mod  # noqa: E402
from research.concorde_metaopt.dreal001.meta.meta_dataset import TrainNormalizer  # noqa: E402
import p2_data  # noqa: E402

K_VALUES = (1, 3)
SEEDS = (7, 19, 43)
OUT = RUN / "training"
TABLES = RUN / "tables"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dump_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def save_checkpoint(path: Path, parameters) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"tensor_%02d" % i: np.asarray(t, dtype=np.float64) for i, t in enumerate(parameters.tensors)}
    np.savez(path, **arrays)
    return {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size,
            "tensors": len(arrays), "shape": [list(a.shape) for a in arrays.values()]}


def train_one(dataset, config, k: int, normalizer):
    maml = arms_mod._maml()
    contexts, feature_vectors = arms_mod.build_contexts(dataset)
    feature_spec = arms_mod.ConditionalFeatureSpec(
        mach_reference=2.0, mach_scale=0.4, q_reference=20000.0,
        cl_reference=0.2, cl_scale=0.2, altitude_reference=18288.0)
    config12 = arms_mod._config(12, config)
    config16 = arms_mod._config(16, config)
    random_params = maml.init_parameters(config12, seed=config.seed)
    pooled = arms_mod._train_pooled(dataset, config12, config.max_steps, normalizer)
    conditional = arms_mod._train_conditional(dataset, config16, config.max_steps,
                                              normalizer, feature_vectors, k)
    fomaml = arms_mod._train_fomaml(dataset, config12, config.max_steps, normalizer, k)
    arms = {"RANDOM_INIT": {"parameters": random_params, "history": []},
            "POOLED_PRETRAIN": pooled,
            "TASK_COND_PRETRAIN": conditional,
            "FOMAML": fomaml}
    return arms, {"config12": config12, "config16": config16,
                  "contexts": {t: {"cl_target": c.cl_target} for t, c in contexts.items()},
                  "feature_spec": feature_spec, "feature_vectors": feature_vectors}


def score_arms(dataset, arms, k: int, eval_tasks, configs, normalizer):
    config12, config16 = configs["config12"], configs["config16"]
    out = {}
    for name, payload in arms.items():
        if name == "TASK_COND_PRETRAIN":
            out[name] = arms_mod.task_errors(dataset, payload["parameters"], config16, normalizer,
                                             task_ids=eval_tasks, k=k,
                                             contexts=configs["feature_vectors"])
        else:
            out[name] = arms_mod.task_errors(dataset, payload["parameters"], config12, normalizer,
                                             task_ids=eval_tasks, k=k)
    return out


def main() -> int:
    built = p2_data.build_family_and_dataset(verbose=True)
    dataset = built["dataset"]
    dataset.require_real_admission()
    OUT.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    eval_tasks = [t.task_id for t in dataset.tasks if t.split in ("val", "test")]
    train_tasks = [t.task_id for t in dataset.tasks if t.split == "train"]
    normalizer = TrainNormalizer.fit(dataset)
    norm_payload = {
        "schema": "dreal004.p2_normalizer.v1",
        "x_mean": normalizer.x_mean.tolist(), "x_scale": normalizer.x_scale.tolist(),
        "y_mean": normalizer.y_mean, "y_scale": normalizer.y_scale,
        "fit_observation_ids": list(normalizer.fit_observation_ids),
        "fit_time_used_train_rows_only": True,
        "note": "12D design x; target di_n (N); statistics computed from train split only",
    }
    dump_json(OUT / "p2_normalizer.json", norm_payload)
    (OUT / "p2_normalizer.sha256").write_text(norm_payload_sha(norm_payload), encoding="utf-8")

    pred_rows, metric_rows, curve_rows, checkpoints = [], [], [], {}
    for k in K_VALUES:
        for seed in SEEDS:
            config = arms_mod.ArmConfig(seed=seed)
            arms, configs = train_one(dataset, config, k, normalizer)
            scores = score_arms(dataset, arms, k, eval_tasks, configs, normalizer)
            for name, payload in arms.items():
                checkpoints["%s_k%d_seed%d" % (name, k, seed)] = save_checkpoint(
                    OUT / "checkpoints" / ("%s_k%d_seed%d.npz" % (name, k, seed)),
                    payload["parameters"])
                for step_row in payload["history"]:
                    curve_rows.append(dict(k=k, seed=seed, arm=name, **step_row))
                for result in scores[name]:
                    for qid, pred, target in zip(result["query_observation_ids"],
                                                 result["predictions"], result["targets"]):
                        pred_rows.append({"task_id": result["task_id"], "k": k, "seed": seed,
                                          "arm": name, "query_observation_id": qid,
                                          "prediction_n": pred, "target_n": target,
                                          "error_n": pred - target})
                    metric_rows.append({"task_id": result["task_id"], "k": k, "seed": seed,
                                        "arm": name, "n_query": result["n_query"],
                                        "mae_n": result["mae_n"], "rmse_n": result["rmse_n"]})
            print("TRAINED k=%d seed=%d" % (k, seed), flush=True)
    write_csv(TABLES / "p2_predictions.csv", pred_rows)
    write_csv(TABLES / "p2_arm_metrics.csv", metric_rows)
    write_csv(TABLES / "p2_training_curves.csv", curve_rows)
    summary = summarize(metric_rows, dataset)
    dump_json(OUT / "p2_arm_summary.json", summary)
    write_csv(TABLES / "p2_arm_summary.csv", summary["rows"])
    dump_json(OUT / "p2_offline_selection.json", offline_selection(pred_rows))
    result = {
        "schema": "dreal004.p2_training_result.v1",
        "run_id": RUN.name,
        "created_utc": now(),
        "status": "REAL_META_TRAINING_EXECUTED",
        "scope": "real admitted labels only; no physical solver invoked by this script",
        "k_values": list(K_VALUES), "seeds": list(SEEDS),
        "k5": "NOT_ELIGIBLE (frozen four support slots; query rows never borrowed as support)",
        "arms": list(arms_mod.ARM_NAMES),
        "task_family": {"train": train_tasks,
                        "val": [t.task_id for t in dataset.tasks if t.split == "val"],
                        "test": [t.task_id for t in dataset.tasks if t.split == "test"]},
        "rows": len(dataset.rows), "certificates": len(dataset.admissions),
        "normalizer": {"path": str(OUT / "p2_normalizer.json"),
                       "sha256": sha(OUT / "p2_normalizer.json")},
        "checkpoints": checkpoints,
        "train_rows_only_for_normalization": True,
        "validation_only_for_selection": True,
        "test_scored_once": True,
        "environment": environment(),
        "code_shas": code_shas(),
        "physical_solver_starts_actual": 0,
    }
    dump_json(OUT / "p2_training_result.json", result)
    print(json.dumps({"status": result["status"], "checkpoints": len(checkpoints),
                      "metrics_rows": len(metric_rows)}, ensure_ascii=False))
    return 0


def norm_payload_sha(payload: dict) -> str:
    return hashlib.sha256((json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()).hexdigest()


def write_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize(metric_rows, dataset) -> dict:
    means = {}
    for row in metric_rows:
        means.setdefault(row["arm"], []).append(row["mae_n"])
    rows = []
    for arm in arms_mod.ARM_NAMES:
        arm_rows = [r for r in metric_rows if r["arm"] == arm]
        for split in ("val", "test"):
            split_tasks = {t.task_id for t in dataset.tasks if t.split == split}
            selected = [r for r in arm_rows if r["task_id"] in split_tasks]
            if not selected:
                continue
            rows.append({"arm": arm, "split": split,
                         "mean_mae_n": float(np.mean([r["mae_n"] for r in selected])),
                         "mean_rmse_n": float(np.mean([r["rmse_n"] for r in selected])),
                         "n_task_k_seed": len(selected)})
    return {"schema": "dreal004.p2_arm_summary.v1",
            "metric": "MAE/RMSE in N over independent query rows after K-shot adaptation",
            "rows": rows,
            "k5": "NOT_ELIGIBLE"}


def offline_selection(pred_rows) -> dict:
    by_key = {}
    for row in pred_rows:
        key = (row["task_id"], row["k"], row["seed"], row["arm"])
        by_key.setdefault(key, []).append(row)
    rows = []
    for (task, k, seed, arm), items in sorted(by_key.items()):
        preds = [r["prediction_n"] for r in items]
        targets = [r["target_n"] for r in items]
        best_true = min(range(len(targets)), key=lambda i: targets[i])
        best_pred = min(range(len(preds)), key=lambda i: preds[i])
        rows.append({"task_id": task, "k": k, "seed": seed, "arm": arm,
                     "n_query": len(items),
                     "chosen_query_id": items[best_pred]["query_observation_id"],
                     "chosen_prediction_n": preds[best_pred],
                     "chosen_true_n": targets[best_pred],
                     "true_best_query_id": items[best_true]["query_observation_id"],
                     "true_best_n": targets[best_true],
                     "selection_regret_n": preds[best_pred] * 0 + (targets[best_pred] - targets[best_true]),
                     "note": "offline candidate-ranking diagnostic only; not online optimization"})
    return {"schema": "dreal004.p2_offline_selection.v1",
            "scope": "offline diagnostic on already-evaluated query rows; not BO/DE and not P3",
            "rows": rows}


def environment() -> dict:
    import platform
    import torch
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "torch": torch.__version__, "torch_cuda": torch.cuda.is_available(),
            "dtype": "float64", "device": "cpu",
            "note": "CPU float64 is the reproducible reference; CUDA was not used"}


def code_shas() -> dict:
    files = {
        "research/concorde_metaopt/dreal001/meta/real_p2_arms.py": REPO / "research/concorde_metaopt/dreal001/meta/real_p2_arms.py",
        "research/concorde_metaopt/dreal001/meta/meta_dataset.py": REPO / "research/concorde_metaopt/dreal001/meta/meta_dataset.py",
        "research/concorde_metaopt/meta_learning/maml.py": REPO / "research/concorde_metaopt/meta_learning/maml.py",
        "scripts/p2_train.py": RUN / "scripts" / "p2_train.py",
        "scripts/p2_data.py": RUN / "scripts" / "p2_data.py",
    }
    return {name: sha(path) for name, path in files.items()}


if __name__ == "__main__":
    raise SystemExit(main())
