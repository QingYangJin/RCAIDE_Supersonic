"""A0 five-arm mechanism ablation for Issue #15 (D-REAL-EXP-003).

This module fixes the defect disclosed in the Issue #15 body: the P2
"TASK_COND_PRETRAIN" arm in real_p2_arms.py calls maml.meta_train_step and is
therefore a *conditional FOMAML*, not a conditional supervised pretraining arm.
A0 therefore defines five separate arms:

  RANDOM_INIT           : freshly initialised 12D network, K-shot adaptation only
  POOLED_PRETRAIN_12D   : 12D ordinary supervised MSE on pooled train labels
  COND_SUPERVISED_16D   : 16D (12D design + 4D frozen task context) ordinary
                          supervised MSE -- it must NOT call meta_train_step
  FOMAML_12D            : 12D first-order MAML on train tasks
  COND_FOMAML_16D       : 16D first-order MAML (the core paired comparison)

Fairness contract enforced here:
- one label source (admitted certificates only in real mode), one network shape,
  one task split, one seed list, one evaluation budget for every arm;
- one frozen hyperparameter grid searched on train/val only, then locked;
- one frozen checkpoint-selection rule for every arm (minimum validation MAE at
  the frozen validation K); no arm may silently keep its last step;
- cost is reported as gradient updates, sample exposures and wall time; step
  counts are never claimed to be equal computation;
- K=5 is refused (four frozen support slots only), K=0 is a zero-shot diagnostic;
- the test split is historical reproduction only, never used for selection.

No physical solver is started by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

import numpy as np

from .meta_dataset import MetaDataset, TrainNormalizer
from .production import (ConditionalFeatureSpec, TaskContext, _append_context,
                         context_features)
from .task_spec import ContractError

ARM_NAMES = ("RANDOM_INIT", "POOLED_PRETRAIN_12D", "COND_SUPERVISED_16D",
             "FOMAML_12D", "COND_FOMAML_16D")
TRAINED_ARMS = ("POOLED_PRETRAIN_12D", "COND_SUPERVISED_16D", "FOMAML_12D",
                "COND_FOMAML_16D")
CONDITIONAL_ARMS = ("COND_SUPERVISED_16D", "COND_FOMAML_16D")
META_ARMS = ("FOMAML_12D", "COND_FOMAML_16D")
ELIGIBLE_K = (0, 1, 3)
REFERENCE_SREF_M2 = 358.25
DEFAULT_FEATURE_SPEC = ConditionalFeatureSpec(
    mach_reference=2.0, mach_scale=0.4, q_reference=20000.0,
    cl_reference=0.2, cl_scale=0.2, altitude_reference=18288.0)


def _maml():
    from ...meta_learning import maml
    return maml


def require_k(k: int) -> None:
    if type(k) is not int:
        raise ContractError("K must be an int")
    if k == 5:
        raise ContractError(
            "K=5 NOT_ELIGIBLE: the frozen protocol only has four independent support "
            "slots (d00-d03); query rows may not be borrowed as support")
    if k not in ELIGIBLE_K:
        raise ContractError("A0 evaluates K=0, K=1 and K=3 only")


@dataclass(frozen=True)
class AblationConfig:
    """Frozen per-arm training configuration (identical budget across arms)."""

    hidden_sizes: tuple = (32, 32)
    inner_lr: float = 0.05
    inner_steps: int = 5
    outer_lr: float = 0.01
    tasks_per_batch: int = 2
    max_steps: int = 60
    seed: int = 7
    validation_k: int = 1

    def __post_init__(self) -> None:
        if not self.hidden_sizes or any(type(v) is not int or v <= 0
                                        for v in self.hidden_sizes):
            raise ContractError("hidden_sizes must be positive ints")
        for name in ("inner_lr", "outer_lr"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ContractError(name + " must be finite and positive")
        if type(self.inner_steps) is not int or self.inner_steps < 0:
            raise ContractError("inner_steps must be a nonnegative int")
        if type(self.tasks_per_batch) is not int or self.tasks_per_batch <= 0:
            raise ContractError("tasks_per_batch must be a positive int")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 500:
            raise ContractError("max_steps must be 1..500")
        if type(self.seed) is not int:
            raise ContractError("seed must be an int")
        if self.validation_k not in ELIGIBLE_K:
            raise ContractError("validation_k must be 0, 1 or 3")

    def replace(self, **kwargs):
        payload = self.as_dict()
        payload["hidden_sizes"] = tuple(payload["hidden_sizes"])
        payload.update(kwargs)
        return AblationConfig(**payload)

    def as_dict(self) -> dict:
        return {
            "hidden_sizes": list(self.hidden_sizes), "inner_lr": self.inner_lr,
            "inner_steps": self.inner_steps, "outer_lr": self.outer_lr,
            "tasks_per_batch": self.tasks_per_batch, "max_steps": self.max_steps,
            "seed": self.seed, "validation_k": self.validation_k,
        }


def _maml_config(input_dim: int, cfg: AblationConfig):
    maml = _maml()
    return maml.MAMLConfig(
        input_dim=input_dim, output_dim=1, hidden_sizes=tuple(cfg.hidden_sizes),
        inner_lr=cfg.inner_lr, inner_steps=cfg.inner_steps, outer_lr=cfg.outer_lr,
        tasks_per_batch=cfg.tasks_per_batch, first_order=True, seed=cfg.seed,
        backend="torch", head_only=False)


def _forward_np(parameters, value: np.ndarray) -> np.ndarray:
    tensors = parameters.tensors
    out = value
    for index in range(0, len(tensors), 2):
        out = out @ tensors[index] + tensors[index + 1]
        if index + 2 < len(tensors):
            out = np.tanh(out)
    return out


def _forward_torch(tensors, value):
    import torch
    out = value
    for index in range(0, len(tensors), 2):
        out = out @ tensors[index] + tensors[index + 1]
        if index + 2 < len(tensors):
            out = torch.tanh(out)
    return out


def _support_rows(dataset: MetaDataset, task_id: str, k: int) -> tuple:
    """Deterministically ordered independent support rows (never query rows)."""
    rows = sorted(dataset.usable(task_id, "support"), key=lambda r: r.observation_id)
    if len(rows) < k:
        raise ContractError("task %s has %d support rows but K=%d"
                            % (task_id, len(rows), k))
    return tuple(rows[:k])


def _query_rows(dataset: MetaDataset, task_id: str) -> tuple:
    rows = sorted(dataset.usable(task_id, "query"), key=lambda r: r.observation_id)
    if not rows:
        raise ContractError("task %s has no independent query rows" % task_id)
    return tuple(rows)


def _adapt(parameters, normalizer: TrainNormalizer, support_rows, maml_config,
           context=None):
    """Adapt on the K support rows only (query rows are never shown)."""
    maml = _maml()
    sx, sy = normalizer.arrays(support_rows)
    if context is not None:
        sx = _append_context(sx, context)
    episode = maml.TaskEpisode(sx, sy, sx[:1], np.zeros((1, 1)), "support_only")
    adapted, _ = maml.inner_adapt(parameters, episode, maml_config)
    return adapted


def predict_rows(parameters, maml_config, normalizer: TrainNormalizer, support_rows,
                 query_rows, *, k: int, context=None) -> np.ndarray:
    """Predict query rows after adapting on (or skipping) the support rows."""
    require_k(k)
    base = parameters
    if k > 0:
        base = _adapt(parameters, normalizer, support_rows, maml_config, context)
    x, _ = normalizer.arrays(query_rows)
    if context is not None:
        x = _append_context(x, context)
    output = _forward_np(base, x)[:, 0] * normalizer.y_scale + normalizer.y_mean
    if not np.isfinite(output).all():
        raise ContractError("nonfinite arm prediction")
    return output


def task_errors(dataset: MetaDataset, parameters, maml_config,
                normalizer: TrainNormalizer, *, task_ids, k: int,
                feature_vectors=None) -> list:
    """Adapt on K support rows and score the independent query rows (in N)."""
    require_k(k)
    results = []
    for task_id in task_ids:
        support = _support_rows(dataset, task_id, k)
        query = _query_rows(dataset, task_id)
        context = None if feature_vectors is None else feature_vectors[task_id]
        prediction = predict_rows(parameters, maml_config, normalizer, support,
                                  query, k=k, context=context)
        target = np.asarray([row.di_n for row in query], dtype=np.float64)
        error = prediction - target
        results.append({
            "task_id": task_id, "k": k, "n_query": int(len(query)),
            "mae_n": float(np.mean(np.abs(error))),
            "rmse_n": float(np.sqrt(np.mean(error ** 2))),
            "predictions": [float(v) for v in prediction],
            "targets": [float(v) for v in target],
            "query_observation_ids": [row.observation_id for row in query],
            "support_observation_ids": [row.observation_id for row in support],
        })
    return results


def validation_score(dataset: MetaDataset, parameters, maml_config,
                     normalizer: TrainNormalizer, *, k: int,
                     feature_vectors=None) -> float:
    tasks = [t.task_id for t in dataset.tasks if t.split == "val"]
    if not tasks:
        raise ContractError("validation tasks required for arm selection")
    rows = task_errors(dataset, parameters, maml_config, normalizer,
                       task_ids=tasks, k=k, feature_vectors=feature_vectors)
    return float(np.mean([row["mae_n"] for row in rows]))


def _supervised_step(tensors, tx, ty, lr):
    import torch
    value = _forward_torch(tensors, tx)
    loss = torch.mean((value - ty) ** 2)
    grads = torch.autograd.grad(loss, tensors)
    if not torch.isfinite(loss) or not all(torch.isfinite(g).all() for g in grads):
        raise ContractError("nonfinite supervised training")
    updated = [(v - lr * g).detach().requires_grad_(True)
               for v, g in zip(tensors, grads)]
    return updated, float(loss.detach())


def _context_matrix(rows, normalizer: TrainNormalizer, contexts: dict,
                    features: dict) -> np.ndarray:
    """Normalized 12D design plus the frozen 4D task context (N,16)."""
    x, _ = normalizer.arrays(rows)
    context_column = np.stack([features[row.task_id] for row in rows]).astype(
        np.float64)
    matrix = np.concatenate([x, context_column], axis=1)
    if matrix.shape[1] != 16 or not np.isfinite(matrix).all():
        raise ContractError("supervised context features must be finite (N,16)")
    if contexts is None:
        raise ContractError("contexts are required for a conditional arm")
    return matrix


def train_supervised(dataset: MetaDataset, config: AblationConfig,
                     normalizer: TrainNormalizer, *, contexts=None,
                     features=None) -> dict:
    """Ordinary joint supervised MSE on pooled train labels (12D or 16D)."""
    import torch
    maml = _maml()
    conditional = contexts is not None
    if conditional and features is None:
        raise ContractError("conditional supervision requires context features")
    input_dim = 16 if conditional else 12
    maml_config = _maml_config(input_dim, config)
    train_ids = [t.task_id for t in dataset.tasks if t.split == "train"]
    rows = tuple(r for r in dataset.rows if r.task_id in train_ids
                 and r.status == "ok")
    if not rows:
        raise ContractError("no admitted train rows")
    params = maml.init_parameters(maml_config)
    tensors = [torch.tensor(v, dtype=torch.float64, requires_grad=True)
               for v in params.tensors]
    if conditional:
        x = _context_matrix(rows, normalizer, contexts, features)
    else:
        x, _ = normalizer.arrays(rows)
    _, y = normalizer.arrays(rows)
    tx = torch.tensor(x, dtype=torch.float64)
    ty = torch.tensor(y, dtype=torch.float64)
    started = time.perf_counter()
    history, best, best_params, best_step, losses = [], None, None, None, []
    for step in range(config.max_steps):
        tensors, loss = _supervised_step(tensors, tx, ty, config.outer_lr)
        losses.append(loss)
        now = maml.ParameterSet([v.detach().numpy().copy() for v in tensors])
        score = validation_score(dataset, now, maml_config, normalizer,
                                 k=config.validation_k,
                                 feature_vectors=features)
        history.append({"step": step + 1, "train_loss": loss, "val_mae_n": score})
        if best is None or score < best:
            best, best_params, best_step = score, now, step + 1
    wall_s = time.perf_counter() - started
    if best_params is None:
        raise ContractError("supervised training produced no checkpoint")
    return {
        "arm_family": "SUPERVISED",
        "parameters": best_params,
        "best_step": best_step,
        "best_val_mae_n": best,
        "history": history,
        "input_dim": input_dim,
        "conditional": conditional,
        "cost": {
            "outer_gradient_updates": config.max_steps,
            "supervised_gradient_updates": config.max_steps,
            "inner_gradient_updates": 0,
            "train_rows": int(len(rows)),
            "train_sample_exposures": int(len(rows) * config.max_steps),
            "validation_adaptations": config.max_steps,
            "wall_s": wall_s,
            "note": ("pooled supervision: one gradient update per step over all "
                     "train rows; no inner adaptation loop"),
        },
    }


def train_meta(dataset: MetaDataset, config: AblationConfig,
               normalizer: TrainNormalizer, *, contexts=None,
               features=None) -> dict:
    """First-order MAML on train tasks (12D or 16D features)."""
    maml = _maml()
    conditional = contexts is not None
    if conditional and features is None:
        raise ContractError("conditional meta-training requires context features")
    input_dim = 16 if conditional else 12
    maml_config = _maml_config(input_dim, config)
    train_tasks = [t.task_id for t in dataset.tasks if t.split == "train"]
    episodes = []
    for task_id in train_tasks:
        support = _support_rows(dataset, task_id, config.validation_k)
        query = _query_rows(dataset, task_id)
        sx, sy = normalizer.arrays(support)
        qx, qy = normalizer.arrays(query)
        if conditional:
            vector = features[task_id]
            sx, qx = _append_context(sx, vector), _append_context(qx, vector)
        episodes.append(maml.TaskEpisode(sx, sy, qx, qy, task_id))
    if not episodes:
        raise ContractError("meta-training needs at least one train task")
    support_total = sum(len(ep.support_features) for ep in episodes)
    query_total = sum(len(ep.query_features) for ep in episodes)
    rng = np.random.default_rng(config.seed)
    params = maml.init_parameters(maml_config)
    started = time.perf_counter()
    history, best, best_params, best_step = [], None, None, None
    for step in range(config.max_steps):
        indices = rng.integers(0, len(episodes), size=config.tasks_per_batch)
        batch = [episodes[int(i)] for i in indices]
        params, stats = maml.meta_train_step(params, batch, maml_config)
        if not math.isfinite(float(stats["outer_loss"])):
            raise ContractError("nonfinite meta outer loss")
        score = validation_score(dataset, params, maml_config, normalizer,
                                 k=config.validation_k, feature_vectors=features)
        history.append({"step": step + 1, "outer_loss": float(stats["outer_loss"]),
                        "val_mae_n": score})
        if best is None or score < best:
            best, best_params, best_step = score, params, step + 1
    wall_s = time.perf_counter() - started
    if best_params is None:
        raise ContractError("meta-training produced no checkpoint")
    return {
        "arm_family": "META",
        "parameters": best_params,
        "best_step": best_step,
        "best_val_mae_n": best,
        "history": history,
        "input_dim": input_dim,
        "conditional": conditional,
        "cost": {
            "outer_gradient_updates": config.max_steps,
            "supervised_gradient_updates": 0,
            "inner_gradient_updates": (config.max_steps * config.tasks_per_batch
                                       * config.inner_steps),
            "train_rows": int(support_total + query_total),
            "train_sample_exposures": int(
                config.max_steps * config.tasks_per_batch
                * (config.inner_steps * support_total + query_total)
                / max(1, len(episodes))),
            "validation_adaptations": config.max_steps,
            "wall_s": wall_s,
            "note": ("first-order MAML: one outer gradient per step plus "
                     "inner_steps inner updates per sampled task; inner and outer "
                     "update counts are not interchangeable"),
        },
    }


def train_arm(dataset: MetaDataset, config: AblationConfig,
              normalizer: TrainNormalizer, arm: str, *, built_contexts=None) -> dict:
    if arm not in TRAINED_ARMS:
        raise ContractError("unknown trained arm: %r" % (arm,))
    conditional = arm in CONDITIONAL_ARMS
    if conditional and built_contexts is None:
        raise ContractError("conditional arm requires frozen task-context features")
    kwargs = {}
    if conditional:
        kwargs = {"contexts": built_contexts["contexts"],
                  "features": built_contexts["features"]}
    if arm in META_ARMS:
        return train_meta(dataset, config, normalizer, **kwargs)
    return train_supervised(dataset, config, normalizer, **kwargs)


def build_contexts(dataset: MetaDataset) -> dict:
    """Frozen 4D task context from TaskSpec values only (never reads labels)."""
    contexts, features = {}, {}
    for task in dataset.tasks:
        cl_target = task.lift_target_n / (task.dynamic_pressure_pa * REFERENCE_SREF_M2)
        context = TaskContext(cl_target=cl_target)
        contexts[task.task_id] = context
        features[task.task_id] = context_features(task, context,
                                                  DEFAULT_FEATURE_SPEC)
    return {"contexts": contexts, "features": features,
            "feature_spec": DEFAULT_FEATURE_SPEC,
            "cl_target_sref_m2": REFERENCE_SREF_M2}


def run_arm(dataset: MetaDataset, *, config: AblationConfig, k: int,
            eval_splits=("val", "test"), mode: str = "real") -> dict:
    """Train every arm for one (seed, K) and score the requested splits once."""
    require_k(k)
    if mode == "real":
        dataset.require_real_admission()
    elif mode != "software_fixture":
        raise ContractError("unsupported execution mode")
    else:
        dataset.require_software_fixture()
    normalizer = TrainNormalizer.fit(dataset)
    built = build_contexts(dataset)
    eval_tasks = [t.task_id for t in dataset.tasks if t.split in eval_splits]
    if not eval_tasks:
        raise ContractError("no evaluation tasks in requested splits")
    payload = {}
    maml = _maml()
    for arm in ARM_NAMES:
        if arm == "RANDOM_INIT":
            input_dim = 16 if arm in CONDITIONAL_ARMS else 12
            params = maml.init_parameters(_maml_config(input_dim, config),
                                          seed=config.seed)
            payload[arm] = {
                "arm_family": "RANDOM",
                "parameters": params, "best_step": None, "best_val_mae_n": None,
                "history": [], "input_dim": input_dim, "conditional": False,
                "cost": {"outer_gradient_updates": 0,
                         "supervised_gradient_updates": 0,
                         "inner_gradient_updates": 0, "train_rows": 0,
                         "train_sample_exposures": 0,
                         "validation_adaptations": 0, "wall_s": 0.0,
                         "note": "no training; K-shot adaptation only"},
            }
            continue
        payload[arm] = train_arm(dataset, config, normalizer, arm,
                                 built_contexts=built)
    config12 = _maml_config(12, config)
    config16 = _maml_config(16, config)
    scores = {}
    for arm in ARM_NAMES:
        conditional = arm in CONDITIONAL_ARMS
        scores[arm] = task_errors(
            dataset, payload[arm]["parameters"],
            config16 if conditional else config12, normalizer,
            task_ids=eval_tasks, k=k,
            feature_vectors=built["features"] if conditional else None)
    return {
        "scope": ("REAL_META_TRAINING_EXECUTED" if mode == "real"
                  else "SOFTWARE_FIXTURE_TRAINING_ONLY"),
        "arms": list(ARM_NAMES), "k": k, "seed": config.seed,
        "config": config, "normalizer": normalizer,
        "feature_spec": DEFAULT_FEATURE_SPEC,
        "contexts": {task_id: {"cl_target": ctx.cl_target}
                     for task_id, ctx in built["contexts"].items()},
        "scores": scores,
        "histories": {arm: payload[arm]["history"] for arm in ARM_NAMES},
        "cost": {arm: payload[arm]["cost"] for arm in ARM_NAMES},
        "checkpoint_selection": {
            arm: {"best_step": payload[arm]["best_step"],
                  "best_val_mae_n": payload[arm]["best_val_mae_n"],
                  "rule": ("minimum validation MAE at validation_k=%d"
                           % config.validation_k)}
            for arm in ARM_NAMES},
        "attention": {
            "train_observation_ids": list(normalizer.fit_observation_ids),
            "test_used_for_selection": False,
            "selection_documents": ("frozen hyperparameters from a train/val grid; "
                                    "no test-time selection"),
        },
    }


def run_arm_for_arm(dataset: MetaDataset, *, config: AblationConfig, k: int,
                          arm: str, eval_splits=("val", "test"),
                          mode: str = "real") -> dict:
    """Train exactly one arm and score the requested splits (per-arm config).

    run_arm() trains every arm under a single shared config so the ablation is
    apples-to-apples inside one call. The locked-hyperparameter phase needs the
    mirror image: each arm uses its own grid-selected inner_lr/inner_steps, so we
    expose a single-arm entry point with the same selection rule and the same
    frozen normalizer/context definition.
    """
    require_k(k)
    if arm not in ARM_NAMES:
        raise ContractError("unknown arm: %r" % (arm,))
    if mode == "real":
        dataset.require_real_admission()
    elif mode != "software_fixture":
        raise ContractError("unsupported execution mode")
    else:
        dataset.require_software_fixture()
    normalizer = TrainNormalizer.fit(dataset)
    built = build_contexts(dataset)
    conditional = arm in CONDITIONAL_ARMS
    trained = None
    if arm == "RANDOM_INIT":
        maml = _maml()
        input_dim = 16 if conditional else 12
        parameters = maml.init_parameters(_maml_config(input_dim, config),
                                          seed=config.seed)
        cost = {"outer_gradient_updates": 0, "supervised_gradient_updates": 0,
                "inner_gradient_updates": 0, "train_rows": 0,
                "train_sample_exposures": 0, "validation_adaptations": 0,
                "wall_s": 0.0, "note": "no training; K-shot adaptation only"}
        best_step, best_val = None, None
        history = []
    else:
        trained = train_arm(dataset, config, normalizer, arm,
                            built_contexts=built)
        parameters = trained["parameters"]
        cost = dict(trained["cost"])
        best_step, best_val = trained["best_step"], trained["best_val_mae_n"]
        history = list(trained["history"])
    maml = _maml()
    maml_config = _maml_config(16 if conditional else 12, config)
    scores = {}
    for split in eval_splits:
        task_ids = [t.task_id for t in dataset.tasks if t.split == split]
        if not task_ids:
            continue
        scores[split] = task_errors(
            dataset, parameters, maml_config, normalizer, task_ids=task_ids, k=k,
            feature_vectors=built["features"] if conditional else None)
    test_rows = scores.get("test") or []
    mean_test = (float(np.mean([row["mae_n"] for row in test_rows]))
                 if test_rows else None)
    return {
        "arm": arm, "arms": [arm], "k": k, "seed": config.seed,
        "scope": ("REAL_META_TRAINING_EXECUTED" if mode == "real"
                  else "SOFTWARE_FIXTURE_TRAINING_ONLY"),
        "parameters": parameters, "best_step": best_step,
        "best_val_mae_n": best_val, "history": history,
        "cost": cost, "scores": scores, "mean_test_mae_n": mean_test,
        "config": config, "feature_spec": DEFAULT_FEATURE_SPEC,
        "normalizer_payload": {
            "x_mean": [float(v) for v in normalizer.x_mean],
            "x_scale": [float(v) for v in normalizer.x_scale],
            "y_mean": float(normalizer.y_mean),
            "y_scale": float(normalizer.y_scale),
            "fit_observation_ids": list(normalizer.fit_observation_ids),
            "fit_rule": "train split, status ok only; no validation or test rows",
        },
        "contexts": {task_id: {"cl_target": ctx.cl_target}
                     for task_id, ctx in built["contexts"].items()},
        "attention": {"train_observation_ids": list(normalizer.fit_observation_ids),
                      "test_used_for_selection": False},
    }


def paired_differences(result_a: list, result_b: list) -> list:
    """Per-task paired MAE difference b - a on the same split/K/seed."""
    index_a = {(row["task_id"], row["k"]): row for row in result_a}
    index_b = {(row["task_id"], row["k"]): row for row in result_b}
    if set(index_a) != set(index_b):
        raise ContractError("paired comparison requires identical task coverage")
    out = []
    for key in sorted(index_a):
        out.append({
            "task_id": key[0], "k": key[1],
            "mae_n_a": index_a[key]["mae_n"], "mae_n_b": index_b[key]["mae_n"],
            "delta_mae_n": index_b[key]["mae_n"] - index_a[key]["mae_n"],
            "rmse_n_a": index_a[key]["rmse_n"], "rmse_n_b": index_b[key]["rmse_n"],
        })
    return out