"""S3: development-set online Bayesian-optimisation trials.

The protocol below is frozen before the first S3 evaluation:

* trial   = one (task, arm, repeat) sequence of exactly 64 charged evaluations;
* arms    = SOBOL_BO, COND_SUPERVISED_KSHOT_BO, COND_FOMAML_KSHOT_BO;
* tasks   = 4 validation tasks (two lift fractions x interior Machs);
* repeats = 4 paired repeats (model seeds 7/19/43/71) sharing support and pool;
* support = 5 shared designs, evaluated per arm/trial and charged;
* hot start = 3 arm-specific points: model-predicted best for the two learning
  arms, the first candidate-pool points for SOBOL_BO;
* BO      = 56 sequential expected-improvement steps on a frozen RBF GP fitted
  to log(CDi / J_ref) of valid observations only;
* failures are charged, recorded as NULL, and never enter the GP.

The candidate pool (8,192 scrambled-Sobol points over the frozen 5D active
subspace) is shared by every trial; a design is never re-proposed inside one
trial.  MAML adaptation happens only when choosing the three hot-start points;
the subsequent BO is identical across the learning arms.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import subprocess
import sys
import time
from typing import Any

ARMS = ("SOBOL_BO", "COND_SUPERVISED_KSHOT_BO", "COND_FOMAML_KSHOT_BO")
MODEL_ARMS = {
    "COND_SUPERVISED_KSHOT_BO": ("COND_SUPERVISED_16D", False),
    "COND_FOMAML_KSHOT_BO": ("COND_FOMAML_16D", True),
}
DEV_TASKS = (
    "DREAL006-VAL-M170-L0090",
    "DREAL006-VAL-M190-L0108",
    "DREAL006-VAL-M210-L0090",
    "DREAL006-VAL-M230-L0108",
)
TEST_TASKS = (
    "DREAL006-TEST-M160-L0085",
    "DREAL006-TEST-M160-L0115",
    "DREAL006-TEST-M166-L0088",
    "DREAL006-TEST-M166-L0112",
    "DREAL006-TEST-M186-L0088",
    "DREAL006-TEST-M186-L0112",
    "DREAL006-TEST-M206-L0088",
    "DREAL006-TEST-M206-L0112",
    "DREAL006-TEST-M226-L0088",
    "DREAL006-TEST-M226-L0112",
    "DREAL006-TEST-M240-L0085",
    "DREAL006-TEST-M240-L0115",
)
REPEAT_SEEDS = (7, 19, 43, 71)
S4_MODEL_SEEDS = (7, 19, 43, 71, 101)
S4_ENV_SEEDS = (20261125, 20261126)
K_SUPPORT = 5
HOT_START = 3
TRIAL_EVALS = 64
POOL_SIZE = 8192
POOL_SEED = 20261125
SUPPORT_SEED = 20261126
GP_XI = 0.01
BUDGET_MARKS = (5, 8, 11, 16, 32, 48, 64)
S4_EVALS = 192
S4_MARKS = (8, 16, 32, 64, 128, 192)
STATUSES = ("VALID", "LIFT_RESIDUAL_REJECTED", "NON_PHYSICAL_CDI", "ALPHA_SOLVE_FAILED", "ERROR")


def _worker_env(tmp_dir: pathlib.Path) -> None:
    """Pin thread counts and temp dirs *before* numpy/scipy/torch are imported."""
    os.environ["TMP"] = str(tmp_dir)
    os.environ["TEMP"] = str(tmp_dir)
    os.environ["TMPDIR"] = str(tmp_dir)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    os.environ.setdefault("PYTHONHASHSEED", "0")


GP_RULE = "fixed RBF length_scale=0.25 + WhiteKernel(1e-4), normalised y, no hyper-optimisation"
ACQ_RULE = "expected improvement, xi=0.01, minimising log(CDi/J_ref)"
FAILURE_RULE = "charged, recorded as NULL, excluded from the GP"

# One frozen protocol per online stage.  S3 is the development stage on 4 val
# tasks with 64 evaluations per trajectory; S4 is the main comparison on the 12
# sealed test tasks with 192 evaluations per trajectory, 5 model seeds x 2
# independent support/pool environments.
PHASE_PROTOCOLS = {
    "s3": {
        "schema": "dreal006.s3_protocol.v1",
        "tasks": DEV_TASKS,
        "task_split": "val",
        "j_ref_source": "data/s1/labels_manifest.json",
        "repeats": [{"model_seed": seed, "env_seed": POOL_SEED} for seed in REPEAT_SEEDS],
        "k_support": K_SUPPORT,
        "evals": TRIAL_EVALS,
        "marks": BUDGET_MARKS,
        "init_plan": {"SOBOL_BO": [["explore", HOT_START]], "LEARNING": [["guided", HOT_START]]},
        "pool_size": POOL_SIZE,
        "budget": 3072,
    },
    "s4": {
        "schema": "dreal006.s4_protocol.v1",
        "tasks": TEST_TASKS,
        "task_split": "test",
        "j_ref_source": "data/s2/labels_manifest.json",
        "repeats": [{"model_seed": model, "env_seed": env}
                    for env in S4_ENV_SEEDS for model in S4_MODEL_SEEDS],
        "k_support": K_SUPPORT,
        "evals": S4_EVALS,
        "marks": S4_MARKS,
        "init_plan": {
            "SOBOL_BO": [["explore", 3], ["order", 8]],
            "LEARNING": [["explore", 3], ["guided", 8]],
        },
        "pool_size": POOL_SIZE,
        "budget": 69120,
    },
}


def phase_protocol(phase: str) -> dict:
    if phase not in PHASE_PROTOCOLS:
        raise SystemExit("unknown online phase %r (choose s3 or s4)" % phase)
    return PHASE_PROTOCOLS[phase]


def protocol(phase: str = "s3") -> dict:
    cfg = phase_protocol(phase)
    init_learning = sum(count for _, count in cfg["init_plan"]["LEARNING"])
    return {
        "schema": cfg["schema"],
        "phase": phase,
        "tasks": list(cfg["tasks"]),
        "task_split": cfg["task_split"],
        "arms": list(ARMS),
        "repeats": [dict(item) for item in cfg["repeats"]],
        "k_support": cfg["k_support"],
        "init_plan": {arm: [list(pair) for pair in plan] for arm, plan in cfg["init_plan"].items()},
        "evals": cfg["evals"],
        "bo_steps": cfg["evals"] - cfg["k_support"] - init_learning,
        "marks": list(cfg["marks"]),
        "pool_size": cfg["pool_size"],
        "gp": GP_RULE,
        "acquisition": ACQ_RULE,
        "target": "log(CDi / J_ref); J_ref is the billed baseline anchor of the same task (%s)" % cfg["j_ref_source"],
        "hot_start_rule": "learning arms: model-predicted lowest means; SOBOL_BO: pool order; shared exploration points identical across arms",
        "failure_rule": FAILURE_RULE,
        "charge_per_trial": cfg["evals"],
        "budget": cfg["budget"],
    }


def _design_id(active_names: list[str], values: dict[str, float]) -> str:
    from . import common

    return common.sha256_text(common.canonical_json(
        [active_names, ["%.12g" % float(values[name]) for name in active_names]]
    ))[:16]


def _full_design(active_names: list[str], active_values: dict[str, float], bounds: dict) -> dict[str, float]:
    design = {}
    for name, spec in bounds.items():
        design[name] = float(active_values[name]) if name in active_values else float(spec["baseline"])
    return design


def build_pool(active_names: list[str], bounds: dict, n: int = POOL_SIZE, seed: int = POOL_SEED) -> list[dict]:
    import numpy as np
    from scipy.stats.qmc import Sobol

    sobol = Sobol(d=len(active_names), scramble=True, seed=seed)
    raw = sobol.random(n)
    pool = []
    for index, row in enumerate(raw.tolist()):
        active = {}
        for name, u in zip(active_names, row):
            lower = float(bounds[name]["lower"])
            upper = float(bounds[name]["upper"])
            active[name] = lower + (upper - lower) * float(u)
        pool.append({
            "design_index": index,
            "active": active,
            "x5": [active[name] for name in active_names],
            "design_id": _design_id(active_names, active),
        })
    return pool


def build_support(active_names: list[str], bounds: dict, k: int = K_SUPPORT, seed: int = SUPPORT_SEED) -> list[dict]:
    import numpy as np
    from scipy.stats.qmc import Sobol

    sobol = Sobol(d=len(active_names), scramble=True, seed=seed)
    raw = sobol.random(k)
    out = []
    for index, row in enumerate(raw.tolist()):
        active = {}
        for name, u in zip(active_names, row):
            lower = float(bounds[name]["lower"])
            upper = float(bounds[name]["upper"])
            active[name] = lower + (upper - lower) * float(u)
        out.append({
            "design_index": -1 - index,
            "active": active,
            "x5": [active[name] for name in active_names],
            "design_id": _design_id(active_names, active),
        })
    return out


def _load_model(arm: str, seed: int):
    from . import common
    from .train import make_model

    base_arm, _needs_adaptation = MODEL_ARMS[arm]
    import torch

    ckpt = common.MODEL_DIR / "s1_initial" / ("%s_s%d.pt" % (base_arm, seed))
    if not ckpt.exists():
        raise SystemExit("missing model checkpoint %s" % ckpt)
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    conditional = bool(payload.get("conditional", int(payload["input_dim"]) == 16))
    model = make_model(int(payload["input_dim"]))
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, conditional


def _model_input(task: dict, designs: list[dict], bounds: dict, names: list[str], conditional: bool):
    import numpy as np
    from .train import design_features, task_features

    X = np.asarray(
        [design_features(task, [d["active"][n] for n in names], bounds, names) for d in designs],
        dtype=np.float32,
    )
    if conditional:
        X = np.concatenate([X, np.tile(np.asarray(task_features(task), dtype=np.float32), (len(X), 1))], axis=1)
    return X


def _predict(model, task: dict, designs: list[dict], bounds: dict, names: list[str], conditional: bool):
    import torch

    X = _model_input(task, designs, bounds, names, conditional)
    with torch.no_grad():
        out = model(torch.from_numpy(X)).squeeze(-1).numpy()
    return out.astype("float64")


def _adapt(model, task: dict, support: list[dict], cdis: list[float], j_ref: float, bounds: dict,
           names: list[str], conditional: bool, steps: int = 10, lr: float = 0.01):
    import copy

    import numpy as np
    import torch

    adapted = copy.deepcopy(model)
    X = _model_input(task, support, bounds, names, conditional)
    y = np.log(np.asarray(cdis, dtype="float64") / j_ref).astype("float32")
    opt = torch.optim.SGD(adapted.parameters(), lr=lr)
    Xs = torch.from_numpy(X)
    ys = torch.from_numpy(y)
    for _ in range(steps):
        opt.zero_grad()
        loss = torch.mean((adapted(Xs).squeeze(-1) - ys) ** 2)
        loss.backward()
        opt.step()
    adapted.eval()
    return adapted


def _gp_fit(X, y):
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel

    kernel = (
        ConstantKernel(1.0, "fixed")
        * RBF(length_scale=0.25, length_scale_bounds="fixed")
        + WhiteKernel(noise_level=1e-4, noise_level_bounds="fixed")
    )
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, optimizer=None, random_state=0)
    gp.fit(X, y)
    return gp


def _ei_pick(X_obs, y_obs, X_pool, evaluated: set[int], fallback: int):
    import numpy as np

    if len(y_obs) < 2:
        return fallback, {"pred_mean": None, "pred_sd": None, "ei": None}
    from scipy.stats import norm

    gp = _gp_fit(X_obs, y_obs)
    mu, sd = gp.predict(X_pool, return_std=True)
    best = float(np.min(y_obs))
    sd = np.maximum(sd, 1e-9)
    z = (best - mu - GP_XI) / sd
    ei = (best - mu - GP_XI) * norm.cdf(z) + sd * norm.pdf(z)
    mask = np.array([i in evaluated for i in range(len(mu))])
    ei[mask] = -np.inf
    if not np.isfinite(ei).any():
        return fallback, {"pred_mean": None, "pred_sd": None, "ei": None}
    idx = int(np.argmax(ei))
    return idx, {"pred_mean": float(mu[idx]), "pred_sd": float(sd[idx]), "ei": float(ei[idx])}


def _build_backend(task: dict, active_names: list[str]) -> Any:
    from research.concorde_metaopt.evaluation.rcaide_vlm_backend import SupersonicVLMBackend

    from . import common

    backend = SupersonicVLMBackend(
        str(common.REPO_ROOT),
        str(common.DESIGN_SPACE_PATH),
        mach=task["mach"],
        altitude_m=task["altitude_m"],
        lattice=(20, 10),
        design_names=active_names,
        reference_mode="geometry",
        task_fingerprint=task["physics_sha256"],
        lift_target_n=task["lift_target_n"],
        lift_target_mode="force",
    )
    solve_state = {"used": 0}
    original = backend._solve

    def _guarded_solve(vehicle, alpha_deg):
        if solve_state["used"] >= common.MAX_INNER_SOLVES_PER_EVAL:
            raise RuntimeError("inner VLM solve budget %d exceeded" % common.MAX_INNER_SOLVES_PER_EVAL)
        solve_state["used"] += 1
        return original(vehicle, alpha_deg)

    backend._solve = _guarded_solve
    return backend, solve_state


def run_trial(spec: dict, tmp_dir: pathlib.Path) -> dict:
    _worker_env(tmp_dir)
    from . import common

    phase = str(spec.get("phase", "s3"))
    common.apply_phase(phase)
    cfg = phase_protocol(phase)
    repo_root = str(common.REPO_ROOT)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import numpy as np

    task = dict(spec["task"])
    task.setdefault("q", float(task["dynamic_pressure_pa"]))
    task.setdefault("lift_fraction", float(task["lift_fraction_of_base"]))
    task.setdefault("altitude", float(task["altitude_m"]))
    arm = spec["arm"]
    bounds = common.load_design_bounds()
    active_names = list(bounds)
    pool_seed = int(spec.get("pool_seed", POOL_SEED))
    support_seed = int(spec.get("support_seed", SUPPORT_SEED))
    k_support = int(spec.get("k_support", K_SUPPORT))
    evals = int(spec.get("evals", cfg["evals"]))
    marks = tuple(spec.get("marks", cfg["marks"]))
    init_plan = spec.get("init_plan", cfg["init_plan"])
    pool = build_pool(active_names, bounds, seed=pool_seed)
    support = build_support(active_names, bounds, k=k_support, seed=support_seed)
    backend, solve_state = _build_backend(task, active_names)
    j_ref = float(spec["j_ref"])

    out_path = pathlib.Path(spec["records_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    X_pool = np.asarray([d["x5"] for d in pool], dtype="float64")
    evaluated: set[int] = set()
    obs_x: list[list[float]] = []
    obs_y: list[float] = []
    sequence: list[dict] = []
    statuses = {status: 0 for status in STATUSES}
    inner_total = 0
    solve_hits = 0
    started = time.perf_counter()

    def evaluate_design(design: dict, phase: str, extra: dict | None = None) -> dict:
        nonlocal inner_total, solve_hits
        x12 = _full_design(active_names, design["active"], bounds)
        before = backend.solve_count
        solve_state["used"] = 0
        try:
            raw = backend.evaluate(x12, purpose="s3")
        except Exception as exc:  # backend normally returns a status instead
            raw = {
                "status": "ERROR",
                "diagnostics": ["%s: %s" % (type(exc).__name__, str(exc)[:400])],
                "objective": None,
                "cached": False,
                "wall_seconds": 0.0,
            }
        inner = int(backend.solve_count - before)
        inner_total += inner
        diagnostics = [str(item) for item in (raw.get("diagnostics") or [])]
        budget_hit = any("solve budget" in item for item in diagnostics)
        solve_hits += 1 if budget_hit else 0
        status = str(raw.get("status", "ERROR"))
        statuses[status] = statuses.get(status, 0) + 1
        cdi = raw.get("objective")
        record = {
            "step": len(sequence),
            "phase": phase,
            "design_id": design["design_id"],
            "design_index": design["design_index"],
            "active": {n: float(design["active"][n]) for n in active_names},
            "status": status,
            "cdi": float(cdi) if cdi is not None else None,
            "inner_solves": inner,
            "cached": bool(raw.get("cached", False)),
            "wall_seconds": float(raw.get("wall_seconds", 0.0) or 0.0),
            "alpha_deg": raw.get("alpha_deg"),
            "lift_residual": raw.get("lift_residual"),
            "solve_budget_hit": budget_hit,
            "diagnostics": diagnostics[:3],
        }
        if extra:
            record.update(extra)
        sequence.append(record)
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        if status == "VALID" and cdi is not None and math.isfinite(float(cdi)) and float(cdi) > 0:
            obs_x.append([float(v) for v in design["x5"]])
            obs_y.append(math.log(float(cdi) / j_ref))
        return record

    for design in support:
        evaluate_design(design, "support")

    # ---- initialisation (shared exploration + arm-specific guided points) --
    hot_start_ids = []
    predicted = None
    plan = init_plan.get(arm) or init_plan.get("LEARNING", [])
    if any(kind == "guided" for kind, _ in plan):
        model, conditional = _load_model(arm, spec["seed"])
        adapted = model
        if MODEL_ARMS[arm][1]:
            support_valid = [r for r in sequence if r["phase"] == "support" and r["status"] == "VALID"]
            if support_valid:
                by_id = {d["design_id"]: d for d in support}
                adapted = _adapt(
                    model, task, [by_id[r["design_id"]] for r in support_valid],
                    [float(r["cdi"]) for r in support_valid], j_ref, bounds, active_names, conditional,
                )
        predicted = _predict(adapted, task, pool, bounds, active_names, conditional)
    for kind, count in plan:
        for _ in range(int(count)):
            if kind == "guided":
                order = np.argsort(predicted)
                idx = next(int(i) for i in order.tolist() if int(i) not in evaluated)
                extra = {"selector": "model-predicted", "init_kind": "guided",
                         "pred_mean": float(predicted[idx])}
            else:
                idx = next(i for i in range(len(pool)) if i not in evaluated)
                extra = {"selector": "sobol-order" if kind == "explore" else "pool-order",
                         "init_kind": kind}
            evaluated.add(idx)
            evaluate_design(pool[idx], "hotstart", extra)
            hot_start_ids.append(pool[idx]["design_id"])

    # ---- BO loop ---------------------------------------------------------
    bo_steps = evals - len(sequence)
    for step in range(bo_steps):
        next_free = next(i for i in range(len(pool)) if i not in evaluated)
        X_obs = np.asarray(obs_x, dtype="float64").reshape(-1, len(active_names))
        y_obs = np.asarray(obs_y, dtype="float64")
        idx, info = _ei_pick(X_obs, y_obs, X_pool, evaluated, next_free)
        if idx in evaluated:
            idx = next_free
        evaluated.add(idx)
        evaluate_design(pool[idx], "bo", {
            "bo_step": step + 1,
            "selector": "ei",
            "pred_mean": info.get("pred_mean"),
            "pred_sd": info.get("pred_sd"),
            "ei": info.get("ei"),
        })

    wall = time.perf_counter() - started
    best_at = {}
    for mark in marks:
        if mark > len(sequence):
            continue
        valid = [r for r in sequence[:mark] if r["status"] == "VALID" and r["cdi"]]
        if valid:
            best = min(float(r["cdi"]) for r in valid)
            best_at[str(mark)] = {
                "best_cdi": best,
                "rel_improvement": (j_ref - best) / j_ref,
                "best_design_id": min(valid, key=lambda r: float(r["cdi"]))["design_id"],
            }
        else:
            best_at[str(mark)] = {"best_cdi": None, "rel_improvement": None, "best_design_id": None}
    summary = {
        "schema": "dreal006.%s_trial.v1" % phase,
        "phase": phase,
        "evals": evals,
        "pool_seed": pool_seed,
        "support_seed": support_seed,
        "trial_id": spec["trial_id"],
        "task_id": task["task_id"],
        "arm": arm,
        "repeat": spec["repeat"],
        "seed": spec["seed"],
        "j_ref": j_ref,
        "charged": len(sequence),
        "valid": sum(1 for r in sequence if r["status"] == "VALID"),
        "by_status": statuses,
        "inner_solves": inner_total,
        "max_inner_solves_per_eval": max((r["inner_solves"] for r in sequence), default=0),
        "solve_budget_hits": solve_hits,
        "cache_hits": sum(1 for r in sequence if r["cached"]),
        "wall_seconds": round(wall, 3),
        "hot_start_ids": hot_start_ids,
        "support_ids": [d["design_id"] for d in support],
        "order": [r["design_id"] for r in sequence],
        "best_at": best_at,
        "final_best": best_at.get(str(max(marks)), {}),
    }
    summary_path = pathlib.Path(spec["summary_path"])
    summary_path.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def _task_map() -> dict:
    from . import common

    family = json.loads(common.TASK_FAMILY_PATH.read_text(encoding="utf-8"))
    return {task["task_id"]: task for task in family["tasks"]}


def plan_trials(phase: str = "s3", tasks: list[str] | None = None, arms: list[str] | None = None,
                repeats: int | None = None) -> list[dict]:
    from . import common

    cfg = phase_protocol(phase)
    family = _task_map()
    labels_path = common.RUN_DIR / cfg["j_ref_source"]
    if not labels_path.exists():
        raise SystemExit("missing j_ref source %s" % labels_path)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    repeat_plan = list(cfg["repeats"])
    if repeats:
        repeat_plan = repeat_plan[: int(repeats)]
    chosen_tasks = [t for t in (tasks or cfg["tasks"]) if t in family]
    missing = sorted({str(t) for t in (tasks or cfg["tasks"])} - set(chosen_tasks))
    if missing:
        raise SystemExit("tasks not in the frozen family: %s" % missing)
    chosen_arms = [a for a in (arms or ARMS) if a in ARMS]
    trials = []
    for task_id in chosen_tasks:
        for arm in chosen_arms:
            for repeat, combo in enumerate(repeat_plan):
                model_seed = int(combo["model_seed"])
                env_seed = int(combo["env_seed"])
                if phase == "s3":
                    trial_id = "%s__%s__s%d" % (task_id, arm, model_seed)
                else:
                    trial_id = "%s__%s__m%d__e%d" % (task_id, arm, model_seed, env_seed)
                task = dict(family[task_id])
                task["q"] = float(task["dynamic_pressure_pa"])
                task["lift_fraction"] = float(task["lift_fraction_of_base"])
                task["altitude"] = float(task["altitude_m"])
                trials.append({
                    "trial_id": trial_id,
                    "phase": phase,
                    "task_id": task_id,
                    "arm": arm,
                    "repeat": repeat,
                    "seed": model_seed,
                    "model_seed": model_seed,
                    "env_seed": env_seed,
                    "task": task,
                    "j_ref": float(labels["per_task"][task_id]["j_ref"]),
                    "evals": int(cfg["evals"]),
                    "marks": list(cfg["marks"]),
                    "k_support": int(cfg["k_support"]),
                    "init_plan": cfg["init_plan"],
                    "pool_seed": env_seed,
                    "support_seed": env_seed + 1,
                })
    return trials


def _paths(trial: dict) -> tuple[pathlib.Path, pathlib.Path]:
    from . import common

    trials_dir = common.DATA_DIR / "trials"
    return (
        trials_dir / (trial["trial_id"] + ".jsonl"),
        trials_dir / (trial["trial_id"] + ".summary.json"),
    )


def aggregate(phase: str, summaries: list[dict]) -> dict:
    from . import common

    cfg = phase_protocol(phase)
    marks = tuple(cfg["marks"])
    counters = {
        "evaluation_attempts_charged": 0,
        "fresh_evaluator_attempts": 0,
        "vlm_inner_solves_actual": 0,
        "cache_hits": 0,
    }
    by_status: dict[str, int] = {}
    unique_labels: set[tuple[str, str]] = set()
    per_trial = []
    by_arm: dict[str, list[dict]] = {}
    for summary in summaries:
        counters["evaluation_attempts_charged"] += int(summary["charged"])
        counters["fresh_evaluator_attempts"] += int(summary["charged"])
        counters["vlm_inner_solves_actual"] += int(summary["inner_solves"])
        counters["cache_hits"] += int(summary["cache_hits"])
        for status, n in summary["by_status"].items():
            by_status[status] = by_status.get(status, 0) + int(n)
        for design_id in summary["order"]:
            unique_labels.add((summary["task_id"], design_id))
        by_arm.setdefault(summary["arm"], []).append(summary)
        per_trial.append({
            "trial_id": summary["trial_id"],
            "task_id": summary["task_id"],
            "arm": summary["arm"],
            "seed": summary["seed"],
            "charged": summary["charged"],
            "valid": summary["valid"],
            "inner_solves": summary["inner_solves"],
            "wall_seconds": summary["wall_seconds"],
            "best_at": summary["best_at"],
        })
    arm_stats = {}
    for arm, rows in sorted(by_arm.items()):
        arm_marks = {}
        for mark in marks:
            values = [r["best_at"].get(str(mark), {}).get("rel_improvement") for r in rows]
            values = [v for v in values if v is not None]
            arm_marks[str(mark)] = {
                "n": len(values),
                "mean_rel_improvement": float(sum(values) / len(values)) if values else None,
                "mean_best_cdi": (
                    float(sum(r["best_at"][str(mark)]["best_cdi"] for r in rows if r["best_at"].get(str(mark), {}).get("best_cdi")) / len(rows))
                    if all(r["best_at"].get(str(mark), {}).get("best_cdi") for r in rows) else None
                ),
            }
        arm_stats[arm] = {"trials": len(rows), "marks": arm_marks}
    charged = counters["evaluation_attempts_charged"]
    cap = int(cfg["budget"])
    smoke_path = common.META_DIR / ("%s_smoke_spend.json" % phase)
    smoke = 0
    if smoke_path.exists():
        smoke = int(json.loads(smoke_path.read_text(encoding="utf-8")).get("charged", 0))
    return {
        "schema": "dreal006.%s_ledger.v1" % phase,
        "phase": phase,
        "protocol": protocol(phase),
        "budget": {"charged": charged, "%s_attempts_cap" % phase: cap, "remaining": max(0, cap - charged)},
        "counters": {
            "evaluation_attempts_charged": charged,
            "fresh_evaluator_attempts": counters["fresh_evaluator_attempts"],
            "unique_task_design_labels": len(unique_labels),
            "vlm_inner_solves_actual": counters["vlm_inner_solves_actual"],
            "cache_hits": counters["cache_hits"],
        },
        "by_status": by_status,
        "pre_protocol_smoke_charged": smoke,
        "max_inner_solves_observed": max(
            (int(s.get("max_inner_solves_per_eval", 0)) for s in summaries), default=0),
        "per_arm": arm_stats,
        "per_trial": per_trial,
    }


def _status_payload(phase: str, planned: int, done: int, charged: int, workers: int) -> dict:
    from . import common

    return {
        "schema": "dreal006.%s_status.v1" % phase,
        "phase": phase,
        "planned_trials": planned,
        "completed_trials": done,
        "charged": charged,
        "workers": workers,
        "updated_utc": common.utc_now(),
    }


def _write_ledger(phase: str, summaries: list[dict]) -> dict:
    from . import common

    ledger = aggregate(phase, summaries)
    common.atomic_write_json(common.LEDGER_PATH, ledger)
    return ledger


def run_worker(spec_path: str, tmp_dir: str) -> int:
    from . import common

    spec = json.loads(pathlib.Path(spec_path).read_text(encoding="utf-8"))
    summary = run_trial(spec, pathlib.Path(tmp_dir))
    print(json.dumps({
        "trial": summary["trial_id"],
        "charged": summary["charged"],
        "valid": summary["valid"],
        "best": summary["final_best"],
    }, sort_keys=True))
    return 0


def _scheduler(args) -> int:
    from . import common

    phase = args.phase
    common.apply_phase(phase)
    cfg = phase_protocol(phase)
    common.LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if common.LOCK_PATH.exists():
        if not args.force_unlock:
            raise SystemExit("run lock present: %s (use --force-unlock if the run is dead)" % common.LOCK_PATH)
        common.LOCK_PATH.unlink()
    lock_fd = os.open(str(common.LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(lock_fd, str(os.getpid()).encode())
    os.close(lock_fd)

    tasks = list(cfg["tasks"])
    if args.task_limit:
        tasks = tasks[: args.task_limit]
    arms = [a for a in (args.arms.split(",") if args.arms else ARMS) if a]
    trials = plan_trials(phase, tasks, arms, args.repeats)
    if args.trial_limit:
        trials = trials[: args.trial_limit]
    plan = {
        "schema": "dreal006.%s_trial_plan.v1" % phase,
        "phase": phase,
        "created_utc": common.utc_now(),
        "protocol": protocol(phase),
        "trials": [{k: v for k, v in t.items() if k != "task"} for t in trials],
    }
    plan_payload = common.canonical_json(plan)
    plan["plan_sha256"] = common.sha256_text(plan_payload)
    common.atomic_write_json(common.MANIFEST_PATH, plan)

    trials_dir = common.DATA_DIR / "trials"
    trials_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = common.DATA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = common.RUN_DIR / "tmp" / phase
    tmp_dir.mkdir(parents=True, exist_ok=True)

    pending = []
    for trial in trials:
        records_path, summary_path = _paths(trial)
        if summary_path.exists():
            continue
        if records_path.exists():  # partial trial: restart it cleanly
            records_path.unlink()
        pending.append(trial)
    summaries = []
    for trial in trials:
        _, summary_path = _paths(trial)
        if summary_path.exists():
            summaries.append(json.loads(summary_path.read_text(encoding="utf-8")))
    total_planned = len(trials)
    charged = sum(int(s["charged"]) for s in summaries)
    print("plan %s trials=%d pending=%d already=%d charged=%d"
          % (plan["plan_sha256"][:16], total_planned, len(pending), len(summaries), charged), flush=True)
    common.atomic_write_json(common.STATUS_PATH,
                             _status_payload(phase, total_planned, len(summaries), charged, args.workers))

    running: dict[str, tuple[subprocess.Popen, dict, float]] = {}
    failures = []
    try:
        while pending or running:
            while pending and len(running) < args.workers:
                trial = pending.pop(0)
                records_path, summary_path = _paths(trial)
                spec = dict(trial)
                spec["records_path"] = str(records_path)
                spec["summary_path"] = str(summary_path)
                spec_path = common.RUN_DIR / "tmp" / phase / (trial["trial_id"] + ".spec.json")
                spec_path.write_text(json.dumps(spec), encoding="utf-8")
                log_path = logs_dir / (trial["trial_id"] + ".log")
                with log_path.open("w", encoding="utf-8") as log:
                    proc = subprocess.Popen(
                        [sys.executable, "-m", "research.concorde_metaopt.dreal006.online_bo",
                         "--worker-spec", str(spec_path), "--worker-tmp", str(tmp_dir)],
                        cwd=str(common.REPO_ROOT), stdin=subprocess.DEVNULL, stdout=log,
                        stderr=subprocess.STDOUT, env=os.environ.copy(),
                    )
                running[trial["trial_id"]] = (proc, trial, time.time())
            time.sleep(2.0)
            for trial_id in list(running):
                proc, trial, started = running[trial_id]
                if proc.poll() is None:
                    continue
                del running[trial_id]
                _, summary_path = _paths(trial)
                if summary_path.exists():
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    summaries.append(summary)
                    charged += int(summary["charged"])
                    best = summary["final_best"]
                    print("[%d/%d] %s valid=%d/%d inner=%d best_rel=%s wall=%.1fs"
                          % (len(summaries), total_planned, trial_id, summary["valid"], summary["charged"],
                             summary["inner_solves"],
                             ("%.4f" % best["rel_improvement"]) if best.get("rel_improvement") is not None else "NA",
                             summary["wall_seconds"]), flush=True)
                else:
                    failures.append({"trial_id": trial_id, "returncode": proc.returncode})
                    print("[fail] %s rc=%s" % (trial_id, proc.returncode), flush=True)
                common.atomic_write_json(common.STATUS_PATH,
                                         _status_payload(phase, total_planned, len(summaries), charged, args.workers))
        ledger = _write_ledger(phase, summaries)
        print(json.dumps(ledger["counters"], indent=1, sort_keys=True), flush=True)
        print("trials=%d failures=%d" % (len(summaries), len(failures)), flush=True)
        if failures:
            print(json.dumps(failures, indent=1), flush=True)
    finally:
        for proc, _, _ in running.values():
            proc.terminate()
        if common.LOCK_PATH.exists():
            common.LOCK_PATH.unlink()
    return 0


def analyze(phase: str = "s3") -> int:
    from . import common

    common.apply_phase(phase)
    cfg = phase_protocol(phase)
    marks = tuple(cfg["marks"])
    final_mark = max(marks)
    trials_dir = common.DATA_DIR / "trials"
    summaries = []
    for path in sorted(trials_dir.glob("*.summary.json")):
        summaries.append(json.loads(path.read_text(encoding="utf-8")))
    if not summaries:
        raise SystemExit("no %s trial summaries under %s" % (phase.upper(), trials_dir))
    ledger = aggregate(phase, summaries)
    common.atomic_write_json(common.DATA_DIR / "analysis.json", ledger)
    print("%-28s %-8s %s" % ("arm", "trials", " ".join("B=%d" % m for m in marks)))
    for arm, stats in ledger["per_arm"].items():
        row = []
        for mark in marks:
            value = stats["marks"][str(mark)]["mean_rel_improvement"]
            row.append("%6.3f" % value if value is not None else "    NA")
        print("%-28s %-8d %s" % (arm, stats["trials"], " ".join(row)))
    by_task = {}
    for summary in summaries:
        key = (summary["task_id"], summary["arm"])
        by_task.setdefault(key, []).append(summary["best_at"].get(str(final_mark), {}).get("rel_improvement"))
    print("\nper task (B=%d mean rel improvement over available repeats)" % final_mark)
    for (task_id, arm), values in sorted(by_task.items()):
        values = [v for v in values if v is not None]
        print("%-28s %-28s %s" % (task_id, arm,
                                   "%.3f (n=%d)" % (sum(values) / len(values), len(values)) if values else "NA"))
    return 0


def main(argv=None) -> int:
    global common
    from . import common as _common

    common = _common

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="s3", choices=["s3", "s4"])
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--trial-limit", type=int, default=0)
    parser.add_argument("--task-limit", type=int, default=0)
    parser.add_argument("--arms", default="")
    parser.add_argument("--repeats", type=int, default=0,
                        help="0 = the full repeat plan declared by the phase protocol")
    parser.add_argument("--force-unlock", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--worker-spec", default="")
    parser.add_argument("--worker-tmp", default="")
    args = parser.parse_args(argv)
    if args.worker_spec:
        return run_worker(args.worker_spec, args.worker_tmp or str(common.RUN_DIR / "tmp" / args.phase))
    if args.analyze:
        return analyze(args.phase)
    return _scheduler(args)


if __name__ == "__main__":
    raise SystemExit(main())
