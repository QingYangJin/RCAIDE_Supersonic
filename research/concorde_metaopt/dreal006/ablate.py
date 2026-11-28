"""Condition-shortcut ablation on the S1 validation tasks (no evaluator budget).

The M1 result is that appending four task-condition features (mach, q, lift
fraction, altitude) improves val rel-RMSE from ~0.50 to ~0.40 and collapses the
fine-tuning gain to 0.02-0.03.  Two explanations produce that pattern:

  H1 (useful conditioning): the network learns a smooth mapping from condition
     to the task's drag scale, which generalises to held-out tasks.
  H2 (identity shortcut): the condition vector is a 32-valued task id; the
     network memorises per-task offsets and support-based adaptation becomes
     redundant.

This script separates the two without spending any evaluation budget, using the
already-trained COND checkpoints:

  own            - reproduce the M1 evaluation protocol.
  cond_shift     - replace the condition block with another val task's condition
                   (same support/query designs, wrong identity).
  cond_zero      - zero condition vector (mach 2.0, q 20000, lift frac 1.0).
  cond_train_mean- mean condition over the 24 train tasks.
  identity_ols   - design-blind baseline: linear map condition -> train task mean
                   log-ratio, evaluated as a constant per val task.

A large degradation under cond_shift/cond_zero means the network relies on the
condition block (which is expected); the shortcut question is whether the
condition model beats a task-identity-only predictor by more than it beats the
12D design-only arm.  identity_ols is exactly that task-identity-only predictor.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import pathlib
import sys
import time

from . import common, train

COND_DIM = 4


def evaluate_cond_variant(model, arrays, val_ids, *, k, adapt_steps, seed, cond_values):
    """Evaluate with the condition block of every row replaced by cond_values[task_id]."""
    torch = train._require_torch()
    import numpy as np

    rng = np.random.default_rng(seed)
    per_task = {}
    all_true, all_pred = [], []
    for task_id in val_ids:
        task = arrays[task_id]
        X = np.array(task["X"], copy=True)
        X[:, 12:] = np.asarray(cond_values[task_id], dtype=np.float32)
        support_idx = rng.choice(task["n_fit"], size=min(k, task["n_fit"]), replace=False)
        Xs = torch.from_numpy(X[support_idx])
        ys = torch.from_numpy(task["y"][support_idx])
        adapted = copy.deepcopy(model)
        opt = torch.optim.SGD(adapted.parameters(), lr=0.01)
        for _ in range(adapt_steps):
            opt.zero_grad()
            loss = torch.mean((adapted(Xs).squeeze(-1) - ys) ** 2)
            loss.backward()
            opt.step()
        with torch.no_grad():
            pred = adapted(torch.from_numpy(X[task["n_fit"]:])).squeeze(-1).numpy()
        true = task["y"][task["n_fit"]:]
        cdi_true = task["j_ref"] * np.exp(true)
        cdi_pred = task["j_ref"] * np.exp(pred)
        rel = (cdi_pred - cdi_true) / cdi_true
        per_task[task_id] = {
            "rel_rmse": float(math.sqrt(float((rel ** 2).mean()))),
            "cdi_mape": float(abs(rel).mean()),
            "r2": float(1.0 - ((pred - true) ** 2).sum() / max(((true - true.mean()) ** 2).sum(), 1e-12)),
            "cond": [float(v) for v in np.asarray(cond_values[task_id])],
        }
        all_true.append(true)
        all_pred.append(pred)
    true = np.concatenate(all_true)
    pred = np.concatenate(all_pred)
    return {
        "per_task": per_task,
        "rel_rmse_mean": float(np.mean([m["rel_rmse"] for m in per_task.values()])),
        "r2": float(1.0 - ((pred - true) ** 2).sum() / max(((true - true.mean()) ** 2).sum(), 1e-12)),
    }


def identity_baseline(data, arrays, train_ids, val_ids):
    """Condition-only, design-blind predictor: condition -> train task mean log ratio."""
    import numpy as np

    tf = {t: np.asarray(arrays[t]["t"], dtype=np.float64) for t in train_ids + val_ids}
    y = {t: float(np.mean(arrays[t]["y"])) for t in train_ids + val_ids}
    Xtr = np.asarray([tf[t] for t in train_ids])
    ytr = np.asarray([y[t] for t in train_ids])
    # standardise condition columns for a numerically sane least-squares fit
    mu = Xtr.mean(axis=0)
    sd = Xtr.std(axis=0)
    sd[sd == 0] = 1.0
    A = np.concatenate([(Xtr - mu) / sd, np.ones((len(Xtr), 1))], axis=1)
    coef, *_ = np.linalg.lstsq(A, ytr, rcond=None)
    per_task = {}
    for t in val_ids:
        row = np.concatenate([(tf[t] - mu) / sd, [1.0]])
        pred_const = float(row @ coef)
        true = arrays[t]["y"][arrays[t]["n_fit"]:]
        pred = np.full_like(true, pred_const)
        cdi_true = arrays[t]["j_ref"] * np.exp(true)
        cdi_pred = arrays[t]["j_ref"] * np.exp(pred)
        rel = (cdi_pred - cdi_true) / cdi_true
        per_task[t] = {
            "rel_rmse": float(math.sqrt(float((rel ** 2).mean()))),
            "cdi_mape": float(abs(rel).mean()),
            "mean_log_ratio_pred": pred_const,
            "mean_log_ratio_true": float(np.mean(true)),
        }
    # nearest-train-task identity baseline for reference
    nn = {}
    for t in val_ids:
        d = np.linalg.norm(Xtr - tf[t], axis=1)
        src = train_ids[int(np.argmin(d))]
        pred_const = y[src]
        true = arrays[t]["y"][arrays[t]["n_fit"]:]
        cdi_true = arrays[t]["j_ref"] * np.exp(true)
        cdi_pred = arrays[t]["j_ref"] * np.exp(np.full_like(true, pred_const))
        rel = (cdi_pred - cdi_true) / cdi_true
        nn[t] = {"rel_rmse": float(math.sqrt(float((rel ** 2).mean()))), "source_task": src}
    return {
        "ols": {
            "per_task": per_task,
            "rel_rmse_mean": float(np.mean([m["rel_rmse"] for m in per_task.values()])),
            "coefficients": [float(c) for c in coef],
            "feature_mean": [float(v) for v in mu],
            "feature_std": [float(v) for v in sd],
        },
        "nearest_train_task": {
            "per_task": nn,
            "rel_rmse_mean": float(np.mean([m["rel_rmse"] for m in nn.values()])),
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", default="COND_SUPERVISED_16D,COND_FOMAML_16D")
    parser.add_argument("--seeds", default="7,19,43,71,101")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--adapt-steps", type=int, default=10)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    torch = train._require_torch()
    data, labels_manifest, _bounds = train.load_dataset()
    arrays = train.build_arrays(data, conditional=True, target_mode="log")
    train_ids = sorted([t for t in arrays if arrays[t]["split"] == "train"])
    val_ids = sorted([t for t in arrays if arrays[t]["split"] == "val"])
    conds = {t: arrays[t]["t"] for t in val_ids}
    train_mean = [float(v) for v in sum((arrays[t]["t"] for t in train_ids)) / len(train_ids)]
    shifts = {t: conds[val_ids[(i + 1) % len(val_ids)]] for i, t in enumerate(val_ids)}

    variants = {
        "own": {t: conds[t] for t in val_ids},
        "cond_shift": shifts,
        "cond_zero": {t: [0.0, 0.0, 0.0, 0.0] for t in val_ids},
        "cond_train_mean": {t: train_mean for t in val_ids},
    }

    report = {
        "schema": "dreal006.s1_condition_ablation.v1",
        "created_utc": common.utc_now(),
        "protocol": {"k": args.k, "adapt_steps": args.adapt_steps, "target": "log", "val_tasks": val_ids,
                     "note": "no evaluator budget spent; reuses S1 labels and M1 checkpoints"},
        "condition_variants": {name: {t: [float(x) for x in v] for t, v in vals.items()}
                               for name, vals in variants.items()},
        "identity_baseline": identity_baseline(data, arrays, train_ids, val_ids),
        "runs": [],
        "seeds": [int(s) for s in args.seeds.split(",")],
    }
    out_path = pathlib.Path(args.out) if args.out else (common.MODEL_DIR / "s1_initial" / "ablation_condition_shortcut.json")

    for arm in args.arms.split(","):
        for seed in report["seeds"]:
            pt = common.MODEL_DIR / "s1_initial" / ("%s_s%d.pt" % (arm, seed))
            if not pt.exists():
                raise SystemExit("missing checkpoint %s" % pt)
            payload = torch.load(pt, map_location="cpu")
            model = train.make_model(int(payload["input_dim"]))
            model.load_state_dict(payload["state_dict"])
            model.eval()
            entry = {"arm": arm, "seed": seed, "checkpoint": str(pt.relative_to(common.REPO_ROOT)),
                     "variants": {}}
            for name, values in variants.items():
                entry["variants"][name] = evaluate_cond_variant(
                    model, arrays, val_ids, k=args.k, adapt_steps=args.adapt_steps, seed=seed,
                    cond_values=values,
                )
            entry["variants"]["own_no_adapt"] = evaluate_cond_variant(
                model, arrays, val_ids, k=args.k, adapt_steps=0, seed=seed,
                cond_values={**{t: conds[t] for t in val_ids}},
            )
            report["runs"].append(entry)
            print("[%s s%d] own=%.4f shift=%.4f zero=%.4f mean=%.4f no_adapt=%.4f" % (
                arm, seed,
                entry["variants"]["own"]["rel_rmse_mean"],
                entry["variants"]["cond_shift"]["rel_rmse_mean"],
                entry["variants"]["cond_zero"]["rel_rmse_mean"],
                entry["variants"]["cond_train_mean"]["rel_rmse_mean"],
                entry["variants"]["own_no_adapt"]["rel_rmse_mean"],
            ), flush=True)

    # aggregate over seeds
    agg = {}
    for arm in args.arms.split(","):
        rows = [r for r in report["runs"] if r["arm"] == arm]
        agg[arm] = {}
        for name in rows[0]["variants"]:
            vals = [r["variants"][name]["rel_rmse_mean"] for r in rows]
            r2s = [r["variants"][name]["r2"] for r in rows]
            agg[arm][name] = {
                "mean": float(sum(vals) / len(vals)),
                "std": float((sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / len(vals)) ** 0.5),
                "r2_mean": float(sum(r2s) / len(r2s)),
            }
    report["aggregate"] = agg
    report["baseline_rel_rmse"] = {
        "identity_ols": report["identity_baseline"]["ols"]["rel_rmse_mean"],
        "identity_nearest_train_task": report["identity_baseline"]["nearest_train_task"]["rel_rmse_mean"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"aggregate": agg, "baseline_rel_rmse": report["baseline_rel_rmse"]}, indent=2))
    print("wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
