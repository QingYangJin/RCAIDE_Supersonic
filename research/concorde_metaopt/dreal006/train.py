"""Initial 2x2 comparison on the S1 labels (part of milestone M1).

Arms (same data, same network, same support/query protocol):

* POOLED_SUPERVISED_12D - one network on the 12D design schema, no task input.
* COND_SUPERVISED_16D   - same but with 4 task-condition features appended.
* FOMAML_12D            - first-order MAML, design-only input.
* COND_FOMAML_16D       - first-order MAML with task-condition input.

Every arm is evaluated with the same K-shot fine-tuning protocol on the eight
validation tasks, so the comparison is about the initialization and the input,
not about giving one arm a different adaptation budget.  Targets are relative:
r = (CDi - J_ref) / J_ref, with J_ref the CDi of that task's anchor-baseline
design.  Absolute-target training is a later ablation.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import pathlib
import sys
import time
from . import common

ACTIVE_FALLBACK = ["wing_area", "aspect_ratio", "sweep_1", "span_location_2", "chord_ratio_2"]
ARMS = ("POOLED_SUPERVISED_12D", "COND_SUPERVISED_16D", "FOMAML_12D", "COND_FOMAML_16D")


def _require_torch():
    import torch

    return torch


def load_dataset() -> tuple[dict, dict, dict]:
    labels_path = common.DATA_DIR / "labels.jsonl"
    manifest_path = common.DATA_DIR / "labels_manifest.json"
    if not labels_path.exists() or not manifest_path.exists():
        raise SystemExit("missing labels; run evaluate.py first")
    labels_manifest = common.read_json(manifest_path)
    bounds = common.load_design_bounds()
    names = [n for n in bounds]
    rows = common.read_jsonl(labels_path)

    tasks: dict[str, dict] = {}
    for row in rows:
        task = tasks.setdefault(row["task_id"], {
            "task_id": row["task_id"],
            "split": row["split"],
            "mach": row["mach"],
            "q": row["dynamic_pressure_pa"],
            "lift_fraction": row["lift_fraction_of_base"],
            "altitude": row["altitude_m"],
            "physics_sha256": row["physics_sha256"],
            "fit": [],
            "query": [],
        })
        entry = {
            "design_index": row["design_index"],
            "kind": row["design_kind"],
            "design": [float(row["x12"][n]) for n in names],
            "cdi": float(row["cdi"]),
        }
        task["fit" if row["design_split"] == "fit" else "query"].append(entry)

    for task_id, task in tasks.items():
        info = labels_manifest["per_task"].get(task_id, {})
        j_ref = info.get("j_ref")
        if j_ref is None:
            raise SystemExit("task %s has no valid baseline anchor; cannot define relative target" % task_id)
        task["j_ref"] = float(j_ref)
    return {"tasks": tasks, "bounds": bounds, "names": names, "rows": len(rows)}, labels_manifest, bounds


def task_features(task: dict) -> list[float]:
    return [
        (float(task["mach"]) - 2.0) / 0.4,
        float(task["q"]) / 20000.0,
        (float(task["lift_fraction"]) - 1.0) / 0.15,
        float(task["altitude"]) / 18288.0,
    ]


def design_features(task: dict, design: list[float], bounds: dict, names: list[str]) -> list[float]:
    out = []
    for name, value in zip(names, design):
        lower = bounds[name]["lower"]
        upper = bounds[name]["upper"]
        out.append((value - lower) / (upper - lower))
    return out


def build_arrays(data: dict, conditional: bool, target_mode: str = "log"):
    import numpy as np

    bounds = data["bounds"]
    names = data["names"]
    tasks = {}
    for task_id, task in data["tasks"].items():
        X = np.asarray([design_features(task, row["design"], bounds, names) for row in task["fit"] + task["query"]],
                       dtype=np.float32)
        ratio = np.asarray([row["cdi"] / task["j_ref"] for row in task["fit"] + task["query"]], dtype=np.float64)
        y = np.log(ratio) if target_mode == "log" else (ratio - 1.0)
        y = y.astype(np.float32)
        n_fit = len(task["fit"])
        tf = np.asarray(task_features(task), dtype=np.float32)
        if conditional:
            X = np.concatenate([X, np.tile(tf, (len(X), 1))], axis=1)
        tasks[task_id] = {
            "X": X, "y": y, "n_fit": n_fit, "n_query": len(task["query"]),
            "j_ref": task["j_ref"], "split": task["split"], "t": tf,
        }
    return tasks


def make_model(in_dim: int, hidden: tuple[int, int] = (64, 64)):
    torch = _require_torch()
    import torch.nn as nn

    return nn.Sequential(
        nn.Linear(in_dim, hidden[0]), nn.SiLU(),
        nn.Linear(hidden[0], hidden[1]), nn.SiLU(),
        nn.Linear(hidden[1], 1),
    )


def evaluate(model, tasks: dict, val_ids: list[str], k: int, adapt_steps: int, seed: int, conditional: bool,
             target_mode: str = "log"):
    torch = _require_torch()
    import numpy as np

    rng = np.random.default_rng(seed)
    metrics = {}
    all_true, all_pred = [], []
    for task_id in val_ids:
        task = tasks[task_id]
        support_idx = rng.choice(task["n_fit"], size=min(k, task["n_fit"]), replace=False)
        Xs = torch.from_numpy(task["X"][support_idx])
        ys = torch.from_numpy(task["y"][support_idx])
        adapted = copy.deepcopy(model)
        opt = torch.optim.SGD(adapted.parameters(), lr=0.01)
        for _ in range(adapt_steps):
            opt.zero_grad()
            loss = torch.mean((adapted(Xs).squeeze(-1) - ys) ** 2)
            loss.backward()
            opt.step()
        with torch.no_grad():
            pred = adapted(torch.from_numpy(task["X"][task["n_fit"]:])).squeeze(-1).numpy()
        true = task["y"][task["n_fit"]:]
        if target_mode == "log":
            cdi_true = task["j_ref"] * np.exp(true)
            cdi_pred = task["j_ref"] * np.exp(pred)
        else:
            cdi_true = task["j_ref"] * (1.0 + true)
            cdi_pred = task["j_ref"] * (1.0 + pred)
        rel = (cdi_pred - cdi_true) / cdi_true
        metrics[task_id] = {
            "rel_rmse": float(math.sqrt(float((rel ** 2).mean()))),
            "r2": float(1.0 - ((pred - true) ** 2).sum() / max(((true - true.mean()) ** 2).sum(), 1e-12)),
            "cdi_rmse": float(math.sqrt(float(((cdi_pred - cdi_true) ** 2).mean()))),
            "cdi_mape": float(abs(rel).mean()),
        }
        all_true.append(true)
        all_pred.append(pred)
    true = np.concatenate(all_true)
    pred = np.concatenate(all_pred)
    return {
        "per_task": metrics,
        "rel_rmse_mean": float(np.mean([m["rel_rmse"] for m in metrics.values()])),
        "cdi_mape_mean": float(np.mean([m["cdi_mape"] for m in metrics.values()])),
        "r2": float(1.0 - ((pred - true) ** 2).sum() / max(((true - true.mean()) ** 2).sum(), 1e-12)),
    }


def train_supervised(tasks: dict, train_ids: list[str], steps: int, batch: int, seed: int,
                     conditional: bool, log_every: int = 200):
    torch = _require_torch()
    import numpy as np

    torch.manual_seed(seed)
    np.random.seed(seed)
    X = np.concatenate([tasks[t]["X"][: tasks[t]["n_fit"]] for t in train_ids])
    y = np.concatenate([tasks[t]["y"][: tasks[t]["n_fit"]] for t in train_ids])
    model = make_model(X.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    Xt = torch.from_numpy(X)
    yt = torch.from_numpy(y)
    rng = np.random.default_rng(seed)
    started = time.time()
    for step in range(1, steps + 1):
        idx = rng.integers(0, len(Xt), size=batch)
        opt.zero_grad()
        loss = torch.mean((model(Xt[idx]).squeeze(-1) - yt[idx]) ** 2)
        loss.backward()
        opt.step()
        if step % log_every == 0 or step == steps:
            print("  step %d/%d loss=%.3e (%.1fs)" % (step, steps, float(loss.detach()), time.time() - started), flush=True)
    return model, {"labels_seen": steps * batch, "gradient_updates": steps, "wall_seconds": round(time.time() - started, 1)}


def train_fomaml(tasks: dict, train_ids: list[str], steps: int, meta_batch: int, k: int, q: int,
                 inner_lr: float, seed: int, conditional: bool, log_every: int = 200):
    torch = _require_torch()
    import numpy as np

    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    in_dim = tasks[train_ids[0]]["X"].shape[1]
    model = make_model(in_dim)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    names = [name for name, _ in model.named_parameters()]
    started = time.time()
    labels_seen = 0
    for step in range(1, steps + 1):
        opt.zero_grad()
        meta_loss = 0.0
        for task_id in rng.choice(train_ids, size=meta_batch, replace=False):
            task = tasks[task_id]
            idx = rng.choice(task["n_fit"], size=min(k + q, task["n_fit"]), replace=False)
            support_idx, query_idx = idx[:k], idx[k:]
            Xs = torch.from_numpy(task["X"][support_idx])
            ys = torch.from_numpy(task["y"][support_idx])
            Xq = torch.from_numpy(task["X"][query_idx])
            yq = torch.from_numpy(task["y"][query_idx])
            params = {name: parameter for name, parameter in zip(names, model.parameters())}
            support_loss = torch.mean((torch.func.functional_call(model, params, (Xs,)).squeeze(-1) - ys) ** 2)
            grads = torch.autograd.grad(support_loss, list(params.values()), create_graph=False)
            fast = {name: p - inner_lr * g for name, p, g in zip(names, params.values(), grads)}
            query_loss = torch.mean((torch.func.functional_call(model, fast, (Xq,)).squeeze(-1) - yq) ** 2)
            qgrads = torch.autograd.grad(query_loss, list(fast.values()))
            for parameter, grad in zip(model.parameters(), qgrads):
                parameter.grad = grad if parameter.grad is None else parameter.grad + grad
            meta_loss += float(query_loss.detach())
            labels_seen += k + q
        for parameter in model.parameters():
            parameter.grad = parameter.grad / meta_batch
        opt.step()
        if step % log_every == 0 or step == steps:
            print("  step %d/%d query_loss=%.3e (%.1fs)" % (step, steps, meta_loss / meta_batch, time.time() - started),
                  flush=True)
    return model, {"labels_seen": labels_seen, "gradient_updates": steps, "wall_seconds": round(time.time() - started, 1)}


def run_arm(arm: str, data: dict, arrays: dict, steps: int, seed: int, args) -> dict:
    torch = _require_torch()
    train_ids = sorted([t for t in arrays if arrays[t]["split"] == "train"])
    val_ids = sorted([t for t in arrays if arrays[t]["split"] == "val"])
    conditional = arm in ("COND_SUPERVISED_16D", "COND_FOMAML_16D")
    arrays = build_arrays(data, conditional=conditional, target_mode=args.target)
    print("[%s seed=%d] train=%d val=%d steps=%d" % (arm, seed, len(train_ids), len(val_ids), steps), flush=True)
    if "SUPERVISED" in arm:
        model, cost = train_supervised(arrays, train_ids, steps, 256, seed, conditional)
    else:
        model, cost = train_fomaml(arrays, train_ids, steps, args.meta_batch, args.k, args.q, 0.01, seed, conditional)
    metrics = evaluate(model, arrays, val_ids, args.k, args.adapt_steps, seed, conditional, args.target)
    base = evaluate(model, arrays, val_ids, args.k, 0, seed, conditional, args.target)
    return {
        "arm": arm,
        "seed": seed,
        "input_normalization": "design: fixed design-space bounds; task: fixed scales (mach 2.0/0.4, q/2e4, lift frac 1.0/0.15, h/18288)",
        "steps": steps,
        "target_mode": args.target,
        "conditional": conditional,
        "input_dim": int(arrays[train_ids[0]]["X"].shape[1]),
        "train_tasks": train_ids,
        "val_tasks": val_ids,
        "cost": cost,
        "val": metrics,
        "val_no_adapt": base,
        "params": int(sum(p.numel() for p in model.parameters())),
    }, model


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--seeds", default="7,19,43,71,101")
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--meta-batch", type=int, default=8)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--q", type=int, default=16)
    parser.add_argument("--adapt-steps", type=int, default=10)
    parser.add_argument("--target", choices=("log", "rel"), default="log",
                        help="log = log(CDi/J_ref); rel = (CDi-J_ref)/J_ref (heavy tail)")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args(argv)

    _require_torch()
    data, labels_manifest, _bounds = load_dataset()
    arrays = build_arrays(data, conditional=False, target_mode=args.target)
    family = common.load_task_family()
    splits = {t["task_id"]: t["split"] for t in family["tasks"]}
    expected = {t: s for t, s in splits.items() if s != "test"}
    missing = sorted(t for t in expected if t not in data["tasks"])
    if missing:
        raise SystemExit("labels are missing %d/%d declared train+val tasks: %s" % (len(missing), len(expected), missing))
    leaked = sorted(t for t in data["tasks"] if splits.get(t) == "test")
    if leaked:
        raise SystemExit("S1 labels must not contain test-split tasks: %s" % leaked)
    wrong_split = sorted(t for t, task in data["tasks"].items() if expected.get(t) != task["split"])
    if wrong_split:
        raise SystemExit("split mismatch for %s" % wrong_split)
    print("labels rows=%d tasks=%d manifest=%s" % (
        data["rows"], len(data["tasks"]), common.read_json(common.DATA_DIR / "labels_manifest.json")["labels_sha256"][:12]))

    out_dir = pathlib.Path(args.out_dir) if args.out_dir else (common.MODEL_DIR / "s1_initial")
    out_dir.mkdir(parents=True, exist_ok=True)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    results = []
    for arm in arms:
        if arm not in ARMS:
            raise SystemExit("unknown arm %s" % arm)
        for seed in seeds:
            result, model = run_arm(arm, data, arrays, args.steps, seed, args)
            result["labels_manifest_sha256"] = common.read_json(common.DATA_DIR / "labels_manifest.json")["labels_sha256"]
            path = out_dir / ("%s_s%d.json" % (arm, seed))
            common.atomic_write_json(path, result)
            torch = _require_torch()
            torch.save({
                "state_dict": model.state_dict(),
                "arm": arm,
                "seed": seed,
                "steps": args.steps,
                "input_dim": result["input_dim"],
                "conditional": result["conditional"],
                "labels_manifest_sha256": result["labels_manifest_sha256"],
            }, out_dir / ("%s_s%d.pt" % (arm, seed)))
            results.append(result)
            print("[%s seed=%d] val_rel_rmse=%.4f cdi_mape=%.4f r2=%.4f (no-adapt rel_rmse=%.4f)" % (
                arm, seed, result["val"]["rel_rmse_mean"], result["val"]["cdi_mape_mean"], result["val"]["r2"],
                result["val_no_adapt"]["rel_rmse_mean"]), flush=True)

    summary_path = out_dir / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["arm", "seed", "steps", "target", "val_rel_rmse", "val_cdi_mape", "val_r2",
                         "no_adapt_rel_rmse", "labels_seen", "wall_seconds", "params"])
        for result in results:
            writer.writerow([
                result["arm"], result["seed"], result["steps"], result["target_mode"],
                "%.6f" % result["val"]["rel_rmse_mean"],
                "%.6f" % result["val"]["cdi_mape_mean"],
                "%.6f" % result["val"]["r2"],
                "%.6f" % result["val_no_adapt"]["rel_rmse_mean"],
                result["cost"]["labels_seen"], result["cost"]["wall_seconds"], result["params"],
            ])
    print("wrote %s and %s" % (summary_path, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
